"""Lines of an Inducks index (.dbi) per Bolderbast (xh7111_DBIReader): one definition of the
columns, used to read (parse_entry, split_blocks), write (code_and_pages) and compare
(compare_blocks) index lines.

Ligne d'en-tête : « h » en position 14, niveau (1, 2, 3) en 15, code sur les positions 1-12.
Ligne d'entrée : entrycode 1-12, storycode 13-26, pages 27-28, brokpg 29, pagel 30-31,
plot 33-36, writ 37-40, art 41-44, ink 45-48, hero 49-52, titre à partir de 53. Un champ trop long
pour sa colonne est écrit en balise ([pages:104], [entrycode:…] avec « -> » dans la colonne).
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

TAG = re.compile(r"\[([^:\]\[]+):([^\]]*)\]")
COLUMNS = {  # (début, fin) en indices Python
    "entrycode": (0, 12), "storycode": (12, 26), "pages": (26, 28), "brokpg": (28, 29),
    "pagel": (29, 31), "plot": (32, 36), "writ": (36, 40), "art": (40, 44), "ink": (44, 48),
    "hero": (48, 52),
}
COMPARED = ("storycode", "pages", "brokpg", "pagel", "plot", "writ", "art", "ink", "hero", "title", "part")


def norm(text: str) -> str:
    """Espaces réduits : « LTB  609 » = « LTB 609 »."""
    return re.sub(r"\s+", " ", text or "").strip()


def is_header(line: str) -> bool:
    return len(line) >= 15 and line[13] == "h" and line[14] in "123"


def is_comment(line: str) -> bool:
    return not line.strip() or line.startswith(" ") or "^^" in line


def tags_of(text: str) -> Dict[str, str]:
    """Balises [nom:valeur], noms tels qu'écrits (« desc-de », « Real Places »)."""
    return dict(TAG.findall(text))


def header_code(line: str) -> str:
    code = line[:12].strip()
    if code == "->":
        code = {k.lower(): v for k, v in tags_of(line).items()}.get("entrycode", "")
    return norm(code)


@dataclass(eq=False)
class Block:
    """Un numéro (ligne h3 et ses entrées) ; code vide pour ce qui n'en est pas (h1, h2, commentaires)."""
    code: str
    lines: List[str] = field(default_factory=list)

    @property
    def header(self) -> str:
        return self.lines[0] if self.code and self.lines else ""

    def entries(self) -> List[Dict[str, str]]:
        return [parse_entry(line) for line in self.lines[1:] if not is_comment(line) and not is_header(line)]


def split_blocks(lines: List[str], strip_trailing_blanks: bool = False) -> List[Block]:
    """Découpe un fichier en blocs ; joints bout à bout, ils redonnent le fichier (sauf, avec
    strip_trailing_blanks, les lignes vides qui séparent les numéros d'un index généré)."""
    blocks: List[Block] = []
    current: Optional[Block] = None
    for line in lines:
        if is_header(line):
            level = line[14]
            current = Block(header_code(line) if level == "3" else "", [line])
            blocks.append(current)
        elif current is None:
            current = Block("", [line])
            blocks.append(current)
        else:
            current.lines.append(line)
    for block in blocks if strip_trailing_blanks else ():
        while block.code and len(block.lines) > 1 and not block.lines[-1].strip():
            block.lines.pop()
    return blocks


def parse_entry(line: str) -> Dict[str, str]:
    values = {name: line[a:b].strip() for name, (a, b) in COLUMNS.items()}
    rest = line[52:] if len(line) > 52 else ""
    tags = {k.lower(): v for k, v in tags_of(rest).items()}
    for name in COLUMNS:
        if name in tags:
            values[name] = tags[name].strip()
    first = rest.find("[")
    values["title"] = (rest[:first] if first >= 0 else rest).strip()
    values["part"] = tags.get("part", "")
    return values


def publication(issue_code: str) -> str:
    m = re.match(r"[A-Za-z]+", norm(issue_code))
    return m.group(0).upper() if m else ""


def natural_key(code: str):
    parts = re.split(r"(\d+)", norm(code).lower())
    return [(0, int(p)) if p.isdigit() else (1, p) for p in parts]


def belongs(code: str, issue: str) -> bool:
    """« de/LTB 613p005 » appartient à « de/LTB 613 » ; « de/LTB 6130 » et « de/LTB 613A » non."""
    code, issue = norm(code), norm(issue)
    if code == issue:
        return True
    return code.startswith(issue) and code[len(issue)].islower()


def compare_blocks(generated: Block, official: Block) -> List[str]:
    """Différences lisibles entre un numéro généré et l'index officiel du même numéro."""
    diffs = []
    gen_tags, off_tags = tags_of(generated.header), tags_of(official.header)
    for name in ("issdate", "price", "pages", "isstrans"):
        if gen_tags.get(name, "") != off_tags.get(name, ""):
            diffs.append(f"en-tête [{name}] : généré « {gen_tags.get(name, '')} », officiel « {off_tags.get(name, '')} »")
    def suffix(block: Block, entry: Dict[str, str]) -> str:
        """Code d'entrée sans le numéro : « p005 » ; rapproche aussi LTB 609p005 de LTB 609Ap005."""
        code = norm(entry["entrycode"])
        return code[len(block.code):] if code.startswith(block.code) else code

    gen = {suffix(generated, e): e for e in generated.entries()}
    off = {suffix(official, e): e for e in official.entries()}
    for key in sorted(set(gen) | set(off), key=natural_key):
        code = (gen.get(key) or off[key])["entrycode"]
        if key not in gen:
            o = off[key]
            diffs.append(f"{code} manque (officiel : {o['storycode'] or '?'} {o['pages']} p. « {o['title']} »)")
        elif key not in off:
            g = gen[key]
            diffs.append(f"{code} en trop (généré : {g['storycode'] or '?'} {g['pages']} p. « {g['title']} »)")
        else:
            changed = [f"{name} « {gen[key][name]} » au lieu de « {off[key][name]} »"
                       for name in COMPARED if gen[key][name] != off[key][name]]
            if changed:
                diffs.append(f"{code} : " + " ; ".join(changed))
    return diffs


def code_and_pages(story_code: str, pages: str):
    """Story code (positions 13-26) and pages (27-28) columns; a value too long for its column
    goes into a tag ([storycode:…] with "->" in the column, [pages:…]) instead of spilling over."""
    tags = []
    story_code, pages = (story_code or "").strip(), str(pages or "").strip()
    if len(story_code) > 14:
        tags.append(f"[storycode:{story_code}]")
        story_code = "->"
    if len(pages) > 2:
        tags.append(f"[pages:{pages}]")
        pages = ""
    return story_code.ljust(14), pages.rjust(2), tags

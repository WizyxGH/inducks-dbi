"""Story formatting for Inducks story databases per Bolderbast documentation:
- FSB format (xh7125_FsbReader): used for Italian (I-coded) story files in stories/fsb/
- DBS format (xh7121_DBSReader): used for international story databases in stories/*.dbs
"""
import re
from typing import Dict, List, Optional, Union


def format_fsb_story(
    story_code: str,
    title: str,
    pages: Union[int, str],
    creation_date: str = "",
    part: str = "",
    plot: str = "",
    writ: str = "",
    art: str = "",
    ink: str = "",
    hero: str = "",
    characters: Union[List[str], str] = "",
    description: str = "",
    series: str = "",
    color: str = "",
    color_supervision: str = "",
    printed_code: str = "",
    super_code: str = "",
    rows_per_page: str = "",
    extra_tags: Optional[Dict[str, str]] = None,
) -> str:
    """Format a story record into the official Bolderbast FSB format (xh7125).

    Line structure:
    1: <code> (<creation_date>)
    2: <title> [<part>]
    3: <plot>/<writ>/<art>/<ink>/
    4: <pages>/<desc>/<hero>;<characters>
    5+: [tag:value] (e.g. [colore: ...], [serie: ...], [codice: ...], [supercodice: ...], [strisce: ...])
    """
    code = (story_code or "").strip()
    cdate = (creation_date or "").strip()
    line1 = f"{code} ({cdate})" if cdate else code

    t = (title or "").strip()
    p = (part or "").strip()
    line2 = f"{t} [{p}]" if p else t

    # Line 3: Plot/Writ/Art/Ink/
    # If plot is empty: /{writ}/{art}/ (or /{writ}/{art}/{ink}/)
    p_plot = (plot or "").strip()
    p_writ = (writ or "").strip()
    p_art = (art or "").strip()
    p_ink = (ink or "").strip()

    if p_plot or p_ink:
        line3 = f"{p_plot}/{p_writ}/{p_art}/{p_ink}/"
    else:
        line3 = f"/{p_writ}/{p_art}/"

    # Line 4: Pages/Desc/Hero;Characters
    pg = str(pages).strip() if pages else ""
    desc = (description or "").strip()
    h = (hero or "").strip()

    if isinstance(characters, (list, tuple, set)):
        chars_str = ", ".join(filter(None, (c.strip() for c in characters)))
    else:
        chars_str = (characters or "").strip()

    line4 = f"{pg}/{desc}/{h};{chars_str}"

    lines = [line1, line2, line3, line4]

    # Extra tags
    if color:
        lines.append(f"[colore: {color.strip()}]")
    if color_supervision:
        lines.append(f"[supervisione colore: {color_supervision.strip()}]")
    if series:
        lines.append(f"[serie: {series.strip()}]")
    if printed_code:
        lines.append(f"[codice: {printed_code.strip()}]")
    if super_code:
        lines.append(f"[supercodice: {super_code.strip()}]")
    if rows_per_page:
        lines.append(f"[strisce: {rows_per_page.strip()}]")

    if extra_tags:
        for k, v in extra_tags.items():
            if v and str(v).strip():
                lines.append(f"[{k.strip()}: {str(v).strip()}]")

    return "\n".join(lines)


def format_dbs_story(
    story_code: str,
    title: str,
    pages: Union[int, str],
    plot: str = "",
    writ: str = "",
    art: str = "",
    ink: str = "",
    hero: str = "",
    characters: Union[List[str], str] = "",
    brokpg: str = "",
    pagel: str = "",
    series: str = "",
    description: str = "",
    extra_tags: Optional[Dict[str, str]] = None,
) -> str:
    """Format a story record into the official Bolderbast 41+ column DBS line (xh7121).

    Positions:
    1-14: Code (14 chars)
    15-16: Pages (2 chars, right-aligned)
    17: BrokPg (1 char)
    18-19: PageL (2 chars)
    20: Space
    21-24: Plot (4 chars)
    25-28: Writ (4 chars)
    29-32: Art (4 chars)
    33-36: Ink (4 chars)
    37-40: Hero (4 chars)
    41+: Title and tags ([xapp:...], [desc:...], [ser:...], etc.)
    """
    code_field = (story_code or "").strip().ljust(14)
    pg_field = str(pages).strip().rjust(2) if pages else "  "
    bp_field = (brokpg or " ").strip().ljust(1) if brokpg else " "
    pl_field = (pagel or "  ").strip().ljust(2) if pagel else "  "
    sp = " "
    plot_field = (plot or "").strip()[:4].ljust(4)
    writ_field = (writ or "").strip()[:4].ljust(4)
    art_field = (art or "").strip()[:4].ljust(4)
    ink_field = (ink or "").strip()[:4].ljust(4)
    hero_field = (hero or "").strip()[:4].ljust(4)

    prefix = (
        f"{code_field}{pg_field}{bp_field}{pl_field}{sp}"
        f"{plot_field}{writ_field}{art_field}{ink_field}{hero_field}"
    )

    t = (title or "").strip()
    tags = []
    if isinstance(characters, (list, tuple, set)):
        chars_str = ", ".join(filter(None, (c.strip() for c in characters)))
    else:
        chars_str = (characters or "").strip()

    if chars_str:
        tags.append(f"[xapp:{chars_str}]")
    if description:
        tags.append(f"[desc:{description.strip()}]")
    if series:
        tags.append(f"[ser:{series.strip()}]")

    if extra_tags:
        for k, v in extra_tags.items():
            if v and str(v).strip():
                tags.append(f"[{k.strip()}:{str(v).strip()}]")

    tag_str = " ".join(tags)
    rest = f"{t} {tag_str}".strip() if tag_str else t
    return f"{prefix} {rest}".rstrip() if rest else prefix.rstrip()

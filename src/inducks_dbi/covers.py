"""Cover -> story code: find which known Inducks cover an issue reprints, from the cover image.

Many covers are not new: a German LTB reuses the Egmont cover the Nordic pocket books printed
(LTB 610a = D 28817 = dk/JB 561a), with another logo and crop. Comparing the image against every
Inducks scan is impossible, so the candidates are only the covers of the issues that print the
same stories (``cover_candidates``); the closest one is kept when it is clearly closer than the
rest (``best_match``). The same works for a story from the image of its first page
(``find_story_code``, e.g. the publisher's preview pages), among the stories of those issues.

Images are compared with a difference hash (dHash, the one InducksScansManager uses) of the
artwork area, below the logo band. A story code keeps its best match over all of its printings:
foreign editions crop and letter the same drawing differently.

``query(sql, params) -> rows`` reads the Inducks ISV tables ``inducks_entry``,
``inducks_storyversion`` and ``inducks_entryurl``; ``fetch(url) -> bytes | None`` downloads an
image. Pillow is needed for the hashes (imported only here).
"""
import io



def scan_url(path: str) -> str:
    """A "webusers" scan as Inducks serves it without an account, at screen size (~40 KB)."""
    return f"https://inducks.org/hr.php?image=https://outducks.org/webusers/webusers/{path}&normalsize=1"

# Below the title/logo band, inside the side margins: the drawing, not the trade dress.
ARTWORK = (0.1, 0.3, 0.9, 0.9)
# Measured on 15 Egmont covers (D 28816 A, D 28817, IC TL 3630/3376/3557) in 7 countries:
# same drawing 0.02-0.37 for the closest printing, different drawings 0.40-0.52.
MAX_DISTANCE = 0.30
MIN_MARGIN = 0.10


def dhash(image_bytes: bytes, box=ARTWORK, size: int = 16) -> list[int] | None:
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(image_bytes)).convert("L")
    except Exception:
        return None
    w, h = im.size
    im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    im = ImageOps.equalize(im).resize((size + 1, size), Image.BILINEAR)
    px = im.load()
    return [1 if px[x, y] > px[x + 1, y] else 0 for y in range(size) for x in range(size)]


def distance(a: list[int], b: list[int]) -> float:
    return sum(x != y for x, y in zip(a, b)) / len(a)


def _same_issue(entrycode: str, issue: str) -> bool:
    """'de/LTB 610a' is in 'de/LTB 610' (its own scan, when the issue is already on Inducks),
    'de/LTB 6101a' is not."""
    return bool(issue) and entrycode.startswith(issue) and not entrycode[len(issue):len(issue) + 1].isdigit()


def cover_candidates(query, story_codes, own_issue: str = "", issues: int = 12) -> dict[str, list[str]]:
    """Cover story codes of the issues printing the most of ``story_codes`` (at least two, or the
    only one given), each with the scan URLs of all its printings but ``own_issue``'s:
    {storycode: [url, ...]}."""
    return _candidates(query, story_codes, own_issue, issues, covers=True)


def page_candidates(query, story_codes, own_issue: str = "", issues: int = 12) -> dict[str, list[str]]:
    """Same for the stories (not the covers) of those issues: the scan of their first page."""
    return _candidates(query, story_codes, own_issue, issues, covers=False)


def _candidates(query, story_codes, own_issue: str, issues: int, covers: bool) -> dict[str, list[str]]:
    codes = sorted({c for c in story_codes if c})
    if not codes:
        return {}
    marks = ", ".join("?" * len(codes))
    rows = query(
        "SELECT e.issuecode, COUNT(DISTINCT v.storycode) AS n FROM inducks_entry e "
        "JOIN inducks_storyversion v ON v.storyversioncode = e.storyversioncode "
        f"WHERE v.storycode IN ({marks}) AND e.issuecode <> ? GROUP BY e.issuecode "
        "HAVING n >= ? ORDER BY n DESC LIMIT ?", (*codes, own_issue, min(2, len(codes)), issues)) or []
    found: dict[str, list[str]] = {}
    for issuecode, _ in rows:
        for (code,) in query(
                "SELECT v.storycode FROM inducks_entry e JOIN inducks_storyversion v "
                f"ON v.storyversioncode = e.storyversioncode WHERE e.issuecode = ? AND e.position {'=' if covers else '<>'} 'a'",
                (issuecode,)) or []:
            if code and code not in found:
                found[code] = [scan_url(url) for entrycode, url in query(
                    "SELECT entrycode, url FROM inducks_entryurl WHERE storycode = ? AND sitecode = 'webusers' "
                    "AND pagenumber = '1'", (code,)) or [] if not _same_issue(entrycode, own_issue)]
    return {code: urls for code, urls in found.items() if urls}


# Hash of each scan already downloaded in this process: the candidates of the stories of one
# issue are mostly the same issues' scans, fetched once instead of once per page.
_HASHES: dict[str, list[int] | None] = {}


def _scan_hash(url: str, fetch) -> list[int] | None:
    if url not in _HASHES:
        try:
            data = fetch(url)
        except Exception:  # a scan that times out counts as missing
            data = None
        _HASHES[url] = dhash(data) if data else None
    return _HASHES[url]


def best_match(image_bytes: bytes, candidates: dict[str, list[str]], fetch,
               max_images: int = 6) -> tuple[str | None, list[tuple[float, str]]]:
    """(story code or None, [(distance, code), ...] closest first). A code is returned only when
    its best printing is close (MAX_DISTANCE) and clearly closer than any other code (MIN_MARGIN)."""
    mine = dhash(image_bytes)
    if mine is None:
        return None, []
    scores = []
    for code, urls in candidates.items():
        best = None
        for url in urls[:max_images]:
            other = _scan_hash(url, fetch)
            if other is not None:
                d = distance(mine, other)
                best = d if best is None else min(best, d)
        if best is not None:
            scores.append((round(best, 3), code))
    scores.sort()
    if scores and scores[0][0] <= MAX_DISTANCE and (len(scores) == 1 or scores[1][0] - scores[0][0] >= MIN_MARGIN):
        return scores[0][1], scores
    return None, scores


def find_cover_code(query, cover_bytes: bytes, story_codes, fetch, own_issue: str = "", log=print):
    """Story code of the reprinted cover, or None (new cover, or no clear match)."""
    candidates = cover_candidates(query, story_codes, own_issue)
    if not candidates:
        return None
    code, scores = best_match(cover_bytes, candidates, fetch)
    log(f"  [cover] {'reprint of ' + code if code else 'no clear match'} ({_shown(scores)})")
    return code


def find_story_code(query, page_bytes: bytes, story_codes, fetch, own_issue: str = "", log=print):
    """Story code of a story from the image of its first page (a publisher's preview), among the
    stories of the issues printing ``story_codes``; None when no clear match. Measured on the
    LTB 606-613 previews: 46 of 67 found, none wrong (the Italian first pages are lettered
    differently, so the distances are higher than for covers)."""
    candidates = page_candidates(query, story_codes, own_issue)
    if not candidates:
        return None
    code, scores = best_match(page_bytes, candidates, fetch)
    log(f"  [page] {'story ' + code if code else 'no clear match'} ({_shown(scores)})")
    return code


def _shown(scores) -> str:
    return ", ".join(f"{c} {d:.2f}" for d, c in scores[:4])


best_cover_code = best_match  # 0.1.0 name

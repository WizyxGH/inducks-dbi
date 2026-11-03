"""Story rules taken from the Inducks data (never guessed) for a DBI skeleton whose source gives
each story's code, start page and length, such as lustiges-taschenbuch.de:

- story code: a code the source invented (e.g. ``1WTOPO3683``) is replaced by the one an
  equivalent, already indexed issue prints on the same page with the same neighbours;
- serials: a story Inducks knows in N parts gets one entry per part, with ``[part:k]``. The parts
  come from the issue itself when other stories sit inside the story's span (the free gaps are its
  chapters), otherwise from the part lengths other printings of the same story agree on;
- strips per page (pagel): the story's ``rowsperpage`` when the printing keeps its page count.

Every rule reads the ``inducks_entry`` and ``inducks_storyversion`` tables of the Inducks ISV
dump through ``query(sql, params) -> rows``, the caller's database access (local SQLite, Turso…);
without those tables the stories are returned unchanged (no part, no pagel).
"""
import re
from collections import Counter


def tables_present(query) -> bool:
    try:
        rows = query("SELECT name FROM sqlite_master WHERE type='table' AND name IN "
                     "('inducks_entry', 'inducks_storyversion')", ())
        return len(rows or []) == 2
    except Exception:
        return False


def _int(value) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _page_of(position: str) -> int | None:
    m = re.fullmatch(r"p0*(\d+)", (position or "").strip())
    return int(m.group(1)) if m else None


def known_story(query, code: str) -> dict | None:
    """Pages and strips per page of the story's own version (its storyversion of the same code)."""
    if not code:
        return None
    rows = query("SELECT entirepages, rowsperpage FROM inducks_storyversion "
                    "WHERE storycode = ? AND storyversioncode = ?", (code, code))
    if not rows:
        return None
    return {"pages": _int(rows[0][0]), "rowsperpage": _int(rows[0][1])}


def part_lengths(query, code: str, total: int) -> list[int] | None:
    """Part lengths, in part order, that the printings of the story in several parts agree on,
    kept only when they add up to `total` (the length the source gives for the whole story)."""
    rows = query(
        "SELECT e.issuecode, e.part, sv.entirepages FROM inducks_entry e "
        "JOIN inducks_storyversion sv ON sv.storyversioncode = e.storyversioncode "
        "WHERE sv.storycode = ? AND e.part != ''", (code,))
    by_issue: dict[str, dict[int, int]] = {}
    for issue, part, pages in rows or []:
        by_issue.setdefault(issue, {})[_int(part)] = _int(pages)
    votes = Counter()
    for parts in by_issue.values():
        numbers = sorted(parts)
        if len(numbers) > 1 and numbers == list(range(1, len(numbers) + 1)):
            lengths = tuple(parts[n] for n in numbers)
            if sum(lengths) == total and all(lengths):
                votes[lengths] += 1
    if votes:
        (best, count), *rest = votes.most_common()
        if not (rest and rest[0][1] == count):
            return list(best)

    # Cross-issue fallback: When a story originally ran across multiple weekly issues
    # (e.g. Topolino 3086, 3087, 3088, 3089), each issue only contains one part.
    # We aggregate the agreed page counts per part number across all issues.
    by_part: dict[int, Counter] = {}
    for issue, part, pages in rows or []:
        p_num = _int(part)
        p_pages = _int(pages)
        if p_num > 0 and p_pages > 0:
            by_part.setdefault(p_num, Counter())[p_pages] += 1

    if by_part:
        max_p = max(by_part.keys())
        if sorted(by_part.keys()) == list(range(1, max_p + 1)) and max_p > 1:
            candidate_lengths = [by_part[p].most_common(1)[0][0] for p in range(1, max_p + 1)]
            if sum(candidate_lengths) == total and all(candidate_lengths):
                return candidate_lengths

    return None


def _equivalent_code(query, stories: list[dict], index: int) -> str | None:
    """Story code an equivalent issue prints at the same page: an issue where every other story
    with a known code also starts on the same page (at least two of them)."""
    target = stories[index]
    anchors = [(s["story_code"], s["start_page"]) for i, s in enumerate(stories)
               if i != index and s.get("story_code") and s.get("start_page") is not None
               and known_story(query, s["story_code"])]
    if len(anchors) < 2 or target.get("start_page") is None:
        return None
    candidates = None
    for code, page in anchors:
        rows = query(
            "SELECT e.issuecode, e.position FROM inducks_entry e "
            "JOIN inducks_storyversion sv ON sv.storyversioncode = e.storyversioncode "
            "WHERE sv.storycode = ?", (code,))
        issues = {issue for issue, position in rows or [] if _page_of(position) == page}
        candidates = issues if candidates is None else candidates & issues
        if not candidates:
            return None
    codes = set()
    for issue in candidates or ():
        rows = query(
            "SELECT sv.storycode, e.position FROM inducks_entry e "
            "JOIN inducks_storyversion sv ON sv.storyversioncode = e.storyversioncode "
            "WHERE e.issuecode = ?", (issue,))
        codes |= {code for code, position in rows or [] if _page_of(position) == target["start_page"]}
    return codes.pop() if len(codes) == 1 else None


def _gaps(start: int, length: int, others: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The first `length` pages from `start` that no other story takes, as (start, count) runs."""
    taken = set()
    for s, n in others:
        taken.update(range(s, s + n))
    runs, free, page = [], 0, start
    limit = start + length + len(taken)
    while free < length and page <= limit:
        if page not in taken:
            if runs and runs[-1][0] + runs[-1][1] == page:
                runs[-1] = (runs[-1][0], runs[-1][1] + 1)
            else:
                runs.append((page, 1))
            free += 1
        page += 1
    return runs


def apply_story_rules(stories: list[dict], query, log=print) -> list[dict]:
    """Stories with start_page and pages -> entries (one per part), each possibly carrying
    "part" and "pagel". Stories are never dropped; a rule that cannot decide changes nothing."""
    if not stories or not tables_present(query):
        return stories
    stories = [dict(s) for s in stories]
    for i, story in enumerate(stories):
        code = (story.get("story_code") or "").strip()
        if code and not known_story(query, code):
            found = _equivalent_code(query, stories, i)
            if found:
                log(f"  [DBI] {code!r} is not an Inducks code; an equivalent issue prints {found!r} on page {story['start_page']}")
                story["story_code"] = found
            else:
                log(f"  [DBI] {code!r} is not an Inducks code; story code left empty")
                story["story_code"] = ""

    placed = [(s["start_page"], _int(s.get("pages"))) for s in stories
              if s.get("start_page") is not None and _int(s.get("pages"))]
    entries = []
    for story in stories:
        code, start, total = story.get("story_code") or "", story.get("start_page"), _int(story.get("pages"))
        info = known_story(query, code) if code else None
        lengths = part_lengths(query, code, total) if code and total else None
        parts = None
        if start is not None and total:
            inside = [(s, n) for s, n in placed if start < s < start + total]
            if inside:  # other stories printed between its chapters: the gaps are the chapters
                gaps = _gaps(start, total, [(s, n) for s, n in placed if s > start])
                if sum(n for _, n in gaps) == total and (lengths is None or [n for _, n in gaps] == lengths):
                    parts = gaps
            elif lengths:
                parts, page = [], start
                for n in lengths:
                    parts.append((page, n))
                    page += n
        if parts and len(parts) > 1:
            for k, (page, n) in enumerate(parts, start=1):
                entry = dict(story, start_page=page, pages=n, part=str(k))
                if info and info["rowsperpage"] and lengths == [x for _, x in parts]:
                    entry["pagel"] = str(info["rowsperpage"])
                entries.append(entry)
            continue
        entry = dict(story)
        if info and info["rowsperpage"] and total and total == info["pages"] and not lengths:
            entry["pagel"] = str(info["rowsperpage"])
        entries.append(entry)
    entries.sort(key=lambda e: (e.get("start_page") is None, e.get("start_page") or 0))
    return entries

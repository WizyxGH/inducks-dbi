# inducks-dbi

Small, dependency-free Python package shared by the tools that write [Inducks](https://inducks.org)
index files (`.dbi`):

- **`inducks_dbi.lines`**: one definition of the DBI columns from the Bolderbast documentation
  (xh7111): `parse_entry`, `split_blocks`, `compare_blocks`, and `code_and_pages`, which writes the
  story code and pages columns and moves a value that does not fit into a tag (`[pages:104]`).
- **`inducks_dbi.story_rules`**: `apply_story_rules(stories, query)` turns a list of stories
  (code, start page, length) into index entries using only the Inducks data: a serial gets one
  entry per part with `[part:k]`, strips per page come from the story's `rowsperpage` when the
  length is kept, and a code Inducks does not know is replaced by the one an equivalent issue
  prints on the same page (or left empty). `query(sql, params)` is your database access to the
  public ISV dump tables `inducks_entry` and `inducks_storyversion`.

- **`inducks_dbi.covers`**: `find_cover_code(query, cover_bytes, story_codes, fetch)` tells
  which known cover an issue reprints. Candidates are the covers of the issues printing the same
  stories (table `inducks_entryurl` for their scans); the artwork area is compared by difference
  hash, and a code is kept only when it is clearly the closest. Needs Pillow (`[covers]` extra).

## Install

```bash
pip install "inducks-dbi[covers] @ git+https://github.com/WizyxGH/inducks-dbi@v0.1.0"
```

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests use invented data only.

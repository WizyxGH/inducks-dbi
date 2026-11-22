"""Read, write and check Inducks index (.dbi) lines per Bolderbast, format story records
for story databases (.fsb, .dbs), and derive story facts from the public Inducks ISV dump."""
from inducks_dbi.lines import format_entry, format_header, parse_entry, split_blocks, compare_blocks, code_and_pages
from inducks_dbi.stories import format_fsb_story, format_dbs_story

__version__ = "0.2.1"
__all__ = [
    "format_entry",
    "format_header",
    "parse_entry",
    "split_blocks",
    "compare_blocks",
    "code_and_pages",
    "format_fsb_story",
    "format_dbs_story",
]


"""OCR text de-duplication against extracted tables.

Goal: When we include both page OCR text and tables in the same Markdown, OCR often
repeats the same numbers again as a "dump" (labels and numeric lines).

This module removes only the obvious duplicates:
- Lines containing 2+ Finnish amounts where all amounts appear in the page tables.

Policy: never remove normal narrative text.
"""

from __future__ import annotations

import re
from typing import Iterable, List


_AMOUNT_RE = re.compile(r"-?\d{1,3}(?:\s?\d{3})*,\d{2}")


def filter_ocr_text_against_tables(*, ocr_text: str, table_markdowns: Iterable[str]) -> str:
    """Remove numeric-heavy OCR lines that duplicate table contents."""
    text = (ocr_text or "").strip()
    if not text:
        return ""

    amounts: set[str] = set()
    for md in table_markdowns:
        for a in _AMOUNT_RE.findall((md or "").replace("?", "")):
            amounts.add(a.replace("\u00a0", " ").strip())

    if not amounts:
        return text

    keep: List[str] = []
    for line in text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        amts = [a.replace("\u00a0", " ").strip() for a in _AMOUNT_RE.findall(ln)]
        if len(amts) >= 2 and all(a in amounts for a in amts):
            # A table-number dump line -> drop.
            continue
        keep.append(ln)

    return "\n".join(keep).strip()



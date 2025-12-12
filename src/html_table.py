"""HTML table utilities.

This module intentionally uses only stdlib so it can be used in both the
comprehensive PP-Structure path and the single-page visual table path.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Dict, List, Optional


def _norm_text(text: str) -> str:
    # Normalize whitespace for matching OCR tokens to table cells.
    return " ".join(text.replace("\u00a0", " ").strip().split())


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_td: bool = False
        self._in_tr: bool = False
        self._cur_cell: List[str] = []
        self._cur_row: List[str] = []
        self.rows: List[List[str]] = []
        self._cur_colspan: int = 1

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._in_tr = True
            self._cur_row = []
        if tag.lower() in {"td", "th"}:
            self._in_td = True
            self._cur_cell = []
            self._cur_colspan = 1
            for k, v in attrs:
                if k.lower() == "colspan" and v:
                    try:
                        self._cur_colspan = max(1, int(v))
                    except ValueError:
                        self._cur_colspan = 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"}:
            self._in_td = False
            cell_text = _norm_text(unescape("".join(self._cur_cell)))
            # Respect colspan by duplicating the same cell text; this is not ideal
            # for all tables, but it preserves a rectangular grid without inventing data.
            for _ in range(self._cur_colspan):
                self._cur_row.append(cell_text)
            self._cur_cell = []
            self._cur_colspan = 1
        if tag.lower() == "tr":
            self._in_tr = False
            if self._cur_row:
                self.rows.append(self._cur_row)
            self._cur_row = []

    def handle_data(self, data: str) -> None:
        if self._in_td and data:
            self._cur_cell.append(data)


def html_table_to_rows(html: str) -> List[List[str]]:
    """Parse the first HTML table found into a row/column string grid."""
    parser = _TableHTMLParser()
    parser.feed(html)
    return parser.rows


def build_confidence_by_text(rec_texts: List[str], rec_scores: List[float]) -> Dict[str, float]:
    """Build a best-effort lookup from normalized OCR token text -> confidence (min score)."""
    out: Dict[str, float] = {}
    for t, s in zip(rec_texts, rec_scores, strict=False):
        nt = _norm_text(str(t))
        try:
            fs = float(s)
        except Exception:
            continue
        if not nt:
            continue
        if nt in out:
            out[nt] = min(out[nt], fs)
        else:
            out[nt] = fs
    return out


@dataclass(frozen=True)
class LowConfidenceCell:
    row: int
    col: int
    text: str
    confidence: float


def rows_to_markdown(
    rows: List[List[str]],
    confidence_by_text: Optional[Dict[str, float]] = None,
    low_conf_threshold: float = 0.90,
) -> tuple[str, List[LowConfidenceCell]]:
    """Convert a rectangular string grid into markdown table.

    - Uses the first row as header.
    - Marks cells with confidence < threshold by appending '?'.
    """
    if not rows:
        return "", []

    max_cols = max((len(r) for r in rows), default=0)
    if max_cols == 0:
        return "", []

    padded: List[List[str]] = [r + [""] * (max_cols - len(r)) for r in rows]

    low: List[LowConfidenceCell] = []

    def cell_with_flag(text: str, r: int, c: int) -> str:
        if not confidence_by_text:
            return text
        nt = _norm_text(text)
        conf = confidence_by_text.get(nt)
        if conf is None:
            return text
        if conf < low_conf_threshold:
            low.append(LowConfidenceCell(row=r, col=c, text=text, confidence=conf))
            return f"{text}?"
        return text

    # Header
    header = [cell_with_flag(t, 0, j) for j, t in enumerate(padded[0])]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * max_cols) + " |",
    ]
    # Body
    for i, row in enumerate(padded[1:], start=1):
        body = [cell_with_flag(t, i, j) for j, t in enumerate(row)]
        lines.append("| " + " | ".join(body) + " |")

    return "\n".join(lines), low



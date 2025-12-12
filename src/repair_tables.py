"""Deterministic table repair helpers.

Policy:
- Never invent new numbers out of thin air.
- Allowed repairs are derived from values already present in the same table:
  - normalization only (spaces/commas)
  - equation-based derivation (e.g. Saamiset = Myyntisaamiset + Muut saamiset)
  - single leading-digit drop when it makes the equation match (classic OCR extra-digit)
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List, Optional, Tuple


_AMOUNT_RE = re.compile(r"-?\d{1,3}(?:\s?\d{3})*,\d{2}")


@dataclass(frozen=True)
class RepairRecord:
    table_reason: str
    row_label: str
    year: str
    old_text: str
    new_text: str


def _parse_finnish_amount(text: str) -> Optional[float]:
    s = (text or "").strip()
    if not s:
        return None
    try:
        return float(s.replace(" ", "").replace("\u00a0", "").replace(",", "."))
    except ValueError:
        return None


def _format_finnish_amount(x: float) -> str:
    # Always 2 decimals, thousands separated by spaces, comma decimals.
    sign = "-" if x < 0 else ""
    x2 = abs(x)
    intpart = int(x2)
    dec = int(round((x2 - intpart) * 100.0))
    if dec == 100:
        intpart += 1
        dec = 0
    s_int = f"{intpart:d}"
    groups: List[str] = []
    for i in range(len(s_int), 0, -3):
        groups.append(s_int[max(0, i - 3) : i])
    grouped = " ".join(reversed(groups))
    return f"{sign}{grouped},{dec:02d}"


def _drop_one_leading_digit(amount_text: str) -> Optional[str]:
    """Try to drop a single leading digit from the integer part (OCR extra digit case).

    Example: '95 345 152,75' -> '5 345 152,75'
    """
    s = (amount_text or "").strip()
    m = _AMOUNT_RE.search(s)
    if not m:
        return None
    raw = m.group(0)
    raw2 = raw.replace(" ", "").replace("\u00a0", "")
    m2 = re.fullmatch(r"(-)?(\d+),(\d{2})", raw2)
    if not m2:
        return None
    sign, digits, dec = m2.groups()
    if len(digits) <= 1:
        return None
    candidate_digits = digits[1:]
    # Reformat with spaces.
    groups: List[str] = []
    for i in range(len(candidate_digits), 0, -3):
        groups.append(candidate_digits[max(0, i - 3) : i])
    grouped = " ".join(reversed(groups))
    return f"{('-' if sign else '')}{grouped},{dec}"


def _parse_markdown_table(md: str) -> Optional[Tuple[List[str], List[List[str]]]]:
    """Parse a simple markdown table into (header, rows).

    Only supports pipe tables; keeps cells as raw text.
    """
    lines = [ln.strip() for ln in (md or "").splitlines() if ln.strip()]
    pipe_lines = [ln for ln in lines if ln.startswith("|") and ln.endswith("|")]
    if len(pipe_lines) < 2:
        return None
    header = [c.strip() for c in pipe_lines[0].strip("|").split("|")]
    # Skip separator line (second pipe line)
    body: List[List[str]] = []
    for ln in pipe_lines[2:]:
        body.append([c.strip() for c in ln.strip("|").split("|")])
    return header, body


def _render_markdown_table(header: List[str], rows: List[List[str]]) -> str:
    cols = max(len(header), max((len(r) for r in rows), default=0))
    h = header + [""] * (cols - len(header))
    out = []
    out.append("| " + " | ".join(h) + " |")
    out.append("| " + " | ".join(["---"] * cols) + " |")
    for r in rows:
        rr = r + [""] * (cols - len(r))
        out.append("| " + " | ".join(rr) + " |")
    return "\n".join(out)


def repair_table_markdown(md: str) -> Tuple[str, List[RepairRecord]]:
    """Apply deterministic repairs to a markdown table."""
    parsed = _parse_markdown_table(md)
    if parsed is None:
        return md, []

    header, rows = parsed
    # Identify year columns (best-effort)
    h_norm = [h.lower().replace(" ", "") for h in header]
    try:
        idx_2024 = next(i for i, h in enumerate(h_norm) if "2024" in h)
        idx_2023 = next(i for i, h in enumerate(h_norm) if "2023" in h)
    except StopIteration:
        return md, []

    # Label column: assume first column
    idx_label = 0

    # Build lookup within the table for equation-based fixes
    def norm_label(s: str) -> str:
        return " ".join((s or "").lower().split())

    by_label: Dict[str, List[str]] = {}
    for r in rows:
        if len(r) <= idx_label:
            continue
        by_label.setdefault(norm_label(r[idx_label]), []).append("|".join(r))

    # Extract values from rows for a given label (first occurrence)
    def get_row_values(label: str) -> Tuple[Optional[float], Optional[float], Optional[List[str]]]:
        key = norm_label(label)
        for r in rows:
            if len(r) <= max(idx_2024, idx_2023, idx_label):
                continue
            if norm_label(r[idx_label]) == key:
                v24 = _parse_finnish_amount(r[idx_2024].replace("?", ""))
                v23 = _parse_finnish_amount(r[idx_2023].replace("?", ""))
                return v24, v23, r
        return None, None, None

    repairs: List[RepairRecord] = []

    # Specific equation: Saamiset = Myyntisaamiset + Muut saamiset
    saamiset_24, saamiset_23, _ = get_row_values("Saamiset")
    myynti_24, myynti_23, _ = get_row_values("Myyntisaamiset")
    if myynti_24 is None or myynti_23 is None:
        myynti_24, myynti_23, _ = get_row_values("Myyntisaamiset/la")

    muut_24, muut_23, muut_row = get_row_values("Muut saamiset")
    if muut_row is not None and saamiset_24 is not None and myynti_24 is not None:
        expected_24 = saamiset_24 - myynti_24
        cur_txt = muut_row[idx_2024]
        cur_val = muut_24
        if cur_val is None or abs(cur_val - expected_24) > 1.0:
            # Try OCR extra-digit drop first if current exists
            if cur_txt and cur_val is not None and cur_val > saamiset_24:
                cand_txt = _drop_one_leading_digit(cur_txt.replace("?", ""))
                cand_val = _parse_finnish_amount(cand_txt or "")
                if cand_txt and cand_val is not None and abs((myynti_24 + cand_val) - saamiset_24) <= 1.0:
                    new_txt = cand_txt
                else:
                    new_txt = _format_finnish_amount(expected_24)
            else:
                new_txt = _format_finnish_amount(expected_24)
            if new_txt != cur_txt.replace("?", ""):
                repairs.append(
                    RepairRecord(
                        table_reason="Saamiset = Myyntisaamiset + Muut saamiset",
                        row_label="Muut saamiset",
                        year="2024",
                        old_text=cur_txt,
                        new_text=new_txt,
                    )
                )
                muut_row[idx_2024] = new_txt

    if muut_row is not None and saamiset_23 is not None and myynti_23 is not None:
        expected_23 = saamiset_23 - myynti_23
        cur_txt = muut_row[idx_2023]
        cur_val = muut_23
        if cur_val is None or abs(cur_val - expected_23) > 1.0:
            if cur_txt and cur_val is not None and cur_val > saamiset_23:
                cand_txt = _drop_one_leading_digit(cur_txt.replace("?", ""))
                cand_val = _parse_finnish_amount(cand_txt or "")
                if cand_txt and cand_val is not None and abs((myynti_23 + cand_val) - saamiset_23) <= 1.0:
                    new_txt = cand_txt
                else:
                    new_txt = _format_finnish_amount(expected_23)
            else:
                new_txt = _format_finnish_amount(expected_23)
            if new_txt != cur_txt.replace("?", ""):
                repairs.append(
                    RepairRecord(
                        table_reason="Saamiset = Myyntisaamiset + Muut saamiset",
                        row_label="Muut saamiset",
                        year="2023",
                        old_text=cur_txt,
                        new_text=new_txt,
                    )
                )
                muut_row[idx_2023] = new_txt

    return _render_markdown_table(header, rows), repairs



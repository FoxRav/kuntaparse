"""Post-processing for PaddleOCR PPStructureV3 outputs.

Goal: turn PPStructure table outputs into stable 3-column tables for Finnish
financial statements: | erä | 2024 | 2023 |

This is a functional core module: pure functions, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# Relaxed amount finder: allows missing thousand separators and '.' decimals.
_AMOUNT_FIND_RE = re.compile(r"-?\d[\d \u00a0]*[,.]\d{2}")


@dataclass(frozen=True)
class OCRToken:
    text: str
    confidence: float
    # box: x1, y1, x2, y2
    box: Tuple[float, float, float, float]

    @property
    def x_center(self) -> float:
        return (self.box[0] + self.box[2]) / 2.0

    @property
    def y_center(self) -> float:
        return (self.box[1] + self.box[3]) / 2.0

    @property
    def width(self) -> float:
        return max(0.0, self.box[2] - self.box[0])


@dataclass(frozen=True)
class Row3:
    label: str
    v2024: str
    v2023: str
    conf2024: Optional[float]
    conf2023: Optional[float]


def _norm_ws(s: str) -> str:
    return " ".join(s.replace("\u00a0", " ").strip().split())


def _normalize_amount_text(raw: str) -> Optional[str]:
    """Normalize OCR amount to Finnish format with spaces as thousand separators.

    Keeps digits identical; only normalizes separators/spaces.
    """
    s = _norm_ws(raw)
    if not s:
        return None
    # Remove internal spaces for parsing.
    s2 = s.replace(" ", "").replace("\u00a0", "")
    m = re.fullmatch(r"(-)?(\d+)([,.])(\d{2})", s2)
    if not m:
        return None
    sign, intpart, _sep, dec = m.groups()
    # Group int part by 3 from right
    groups: List[str] = []
    for i in range(len(intpart), 0, -3):
        groups.append(intpart[max(0, i - 3) : i])
    grouped = " ".join(reversed(groups))
    return f"{('-' if sign else '')}{grouped},{dec}"


def _extract_amounts(s: str) -> List[str]:
    """Extract and normalize Finnish amounts from a string."""
    raw = _norm_ws(s)
    if not raw:
        return []
    out: List[str] = []
    for m in _AMOUNT_FIND_RE.findall(raw):
        norm = _normalize_amount_text(m)
        if norm is not None:
            out.append(norm)
    return out


def _is_amount(s: str) -> bool:
    raw = _norm_ws(s)
    amts = _extract_amounts(raw)
    if len(amts) != 1:
        return False
    # Consider it an amount if the entire token is just that amount (allow spacing variants).
    return _normalize_amount_text(raw) is not None


def _tokenize_amounts(tokens: Sequence[OCRToken]) -> List[OCRToken]:
    """Split tokens containing two amounts into two tokens (same bbox/conf)."""
    out: List[OCRToken] = []
    for t in tokens:
        amounts = _extract_amounts(t.text)
        if len(amounts) == 2:
            out.append(OCRToken(text=amounts[0], confidence=t.confidence, box=t.box))
            out.append(OCRToken(text=amounts[1], confidence=t.confidence, box=t.box))
        else:
            # Normalize single amount tokens for consistent downstream parsing.
            if len(amounts) == 1:
                out.append(OCRToken(text=amounts[0], confidence=t.confidence, box=t.box))
            else:
                out.append(t)
    return out


def _cluster_two_columns(xs: List[float]) -> Optional[Tuple[float, float, float]]:
    """Return (col_left, col_right, split_x)."""
    if len(xs) < 4:
        return None
    xs_sorted = sorted(xs)
    # Find the largest gap; assume it separates the two columns.
    best_gap = 0.0
    best_i = 0
    for i in range(1, len(xs_sorted)):
        gap = xs_sorted[i] - xs_sorted[i - 1]
        if gap > best_gap:
            best_gap = gap
            best_i = i
    if best_gap <= 1.0:
        return None
    left = xs_sorted[:best_i]
    right = xs_sorted[best_i:]
    if not left or not right:
        return None
    col_left = sum(left) / len(left)
    col_right = sum(right) / len(right)
    split_x = (max(left) + min(right)) / 2.0
    return col_left, col_right, split_x


def _group_by_rows(tokens: Sequence[OCRToken], y_tol: float = 10.0) -> List[List[OCRToken]]:
    """Group tokens into visual rows by y center."""
    if not tokens:
        return []
    toks = sorted(tokens, key=lambda t: (t.y_center, t.x_center))
    rows: List[List[OCRToken]] = []
    cur: List[OCRToken] = [toks[0]]
    cur_y = toks[0].y_center
    for t in toks[1:]:
        if abs(t.y_center - cur_y) <= y_tol:
            cur.append(t)
        else:
            rows.append(sorted(cur, key=lambda x: x.x_center))
            cur = [t]
            cur_y = t.y_center
    rows.append(sorted(cur, key=lambda x: x.x_center))
    return rows


def try_balance_sheet_3col(
    tokens: Sequence[OCRToken],
    *,
    low_conf_threshold: float = 0.90,
) -> Optional[Tuple[str, List[Dict]]]:
    """Try to reconstruct Vesihuoltolaitoksen tase into a 3-column markdown table.

    Returns:
      (markdown, low_confidence_cells) or None if heuristics don't match.
    """
    if not tokens:
        return None

    joined = " ".join(_norm_ws(t.text).lower() for t in tokens if t.text)
    if "vesihuoltolaitoksen" not in joined or "tase" not in joined:
        return None
    if "vastaavaa" not in joined or "vastattavaa" not in joined:
        return None

    toks = _tokenize_amounts(tokens)

    # Identify numeric tokens and derive column centers from non-wide numeric tokens.
    numeric = [t for t in toks if _is_amount(t.text)]
    if len(numeric) < 6:
        return None

    xs = [t.x_center for t in numeric if t.width < 250.0]
    cols = _cluster_two_columns(xs) if xs else None
    if cols is None:
        # Fallback: use percentile-based split
        xs2 = sorted(t.x_center for t in numeric)
        mid = xs2[len(xs2) // 2]
        left = [x for x in xs2 if x <= mid]
        right = [x for x in xs2 if x > mid]
        if not left or not right:
            return None
        col_left = sum(left) / len(left)
        col_right = sum(right) / len(right)
        split_x = (col_left + col_right) / 2.0
    else:
        col_left, col_right, split_x = cols

    rows = _group_by_rows(toks, y_tol=10.0)
    out_rows: List[Row3] = []

    for r in rows:
        label_parts: List[str] = []
        v2024: str = ""
        v2023: str = ""
        c2024: Optional[float] = None
        c2023: Optional[float] = None

        # Split into label tokens and numeric tokens.
        nums: List[OCRToken] = []
        for t in r:
            if _is_amount(t.text):
                nums.append(t)
            else:
                # Put most text into label; ignore standalone year headers here
                nt = _norm_ws(t.text)
                if nt and nt not in {"2024", "2023"}:
                    label_parts.append(nt)

        # Special case: two amounts split out of one wide token share the same box/x.
        if len(nums) >= 2 and abs(nums[0].x_center - nums[1].x_center) < 5.0 and nums[0].width > 300.0:
            v2024 = _norm_ws(nums[0].text)
            v2023 = _norm_ws(nums[1].text)
            c2024 = nums[0].confidence
            c2023 = nums[1].confidence
        else:
            # Assign numeric tokens to columns by x position.
            for t in nums:
                if t.x_center <= split_x:
                    # 2024 column (left numeric)
                    if not v2024:
                        v2024 = _norm_ws(t.text)
                        c2024 = t.confidence
                    else:
                        # If already present, keep the first and ignore extras (table noise)
                        c2024 = min(c2024 or 1.0, t.confidence)
                else:
                    # 2023 column (right numeric)
                    if not v2023:
                        v2023 = _norm_ws(t.text)
                        c2023 = t.confidence
                    else:
                        c2023 = min(c2023 or 1.0, t.confidence)

        label = _norm_ws(" ".join(label_parts))
        if not label and not v2024 and not v2023:
            continue

        out_rows.append(Row3(label=label, v2024=v2024, v2023=v2023, conf2024=c2024, conf2023=c2023))

    # Filter out obvious garbage rows (e.g. repeated single amount lines without a label)
    cleaned: List[Row3] = []
    for r in out_rows:
        if not r.label and r.v2024 and not r.v2023:
            # usually a continuation artifact
            continue
        cleaned.append(r)

    if len(cleaned) < 8:
        return None

    # Build markdown and low confidence report
    low_cells: List[Dict] = []

    def fmt(val: str, conf: Optional[float], row_i: int, col: int) -> str:
        if not val:
            return ""
        if conf is not None and conf < low_conf_threshold:
            low_cells.append({"row": row_i, "col": col, "text": val, "confidence": conf})
            return f"{val}?"
        return val

    lines = [
        "| erä | 2024 | 2023 |",
        "| --- | --- | --- |",
    ]
    for i, r in enumerate(cleaned, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    r.label,
                    fmt(r.v2024, r.conf2024, i, 1),
                    fmt(r.v2023, r.conf2023, i, 2),
                ]
            )
            + " |"
        )

    return "\n".join(lines), low_cells



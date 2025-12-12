"""Utilities for fixing Finnish financial tables."""

import re
from typing import Tuple

import pandas as pd

# Regex for Finnish currency amounts: "13 294 125,84" format
AMOUNT_RE = re.compile(r"-?\d{1,3}(?: \d{3})*,\d{2}")


def split_two_amounts(cell: str) -> Tuple[str | None, str, str] | None:
    """
    Split a cell containing two Finnish currency amounts.
    
    Args:
        cell: Cell content that may contain two amounts
        
    Returns:
        Tuple of (text_part, amount1, amount2) if exactly 2 amounts found,
        None otherwise
    """
    if not isinstance(cell, str):
        return None

    amounts = AMOUNT_RE.findall(cell)
    if len(amounts) != 2:
        return None

    # Remove amounts from text to get remaining text part
    text_part = AMOUNT_RE.sub("", cell).strip()
    return text_part or None, amounts[0], amounts[1]


def fix_finnish_amount_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fix cells where two Finnish currency amounts ended up in the same cell.
    
    This typically happens with balance sheet tables (VASTAAVAA/VASTATTAVAA)
    where 2024 and 2023 columns get merged.
    
    Args:
        df: DataFrame with potentially merged amount columns
        
    Returns:
        DataFrame with amounts split into separate columns
    """
    new_df = df.copy()

    # Find year columns or create them
    year_cols = [c for c in new_df.columns if isinstance(c, str) and c.strip().isdigit()]
    
    if len(year_cols) >= 2:
        col_2024, col_2023 = year_cols[-2], year_cols[-1]
    else:
        # Fallback: add new columns if not found
        col_2024, col_2023 = "2024", "2023"
        if col_2024 not in new_df.columns:
            new_df[col_2024] = None
        if col_2023 not in new_df.columns:
            new_df[col_2023] = None

    for col in new_df.columns:
        for i, val in enumerate(new_df[col].astype(str)):
            res = split_two_amounts(val)
            if res is None:
                continue
            text_part, a2024, a2023 = res
            # Write amounts to correct columns
            new_df.at[i, col_2024] = a2024
            new_df.at[i, col_2023] = a2023
            # Leave only text part in original cell
            new_df.at[i, col] = text_part or ""

    return new_df


from __future__ import annotations

from src.repair_tables import repair_table_markdown


def test_repair_tables_drops_extra_leading_digit_when_equation_matches() -> None:
    md = (
        "| erä | 2024 | 2023 |\n"
        "| --- | --- | --- |\n"
        "| Saamiset | 6 208 195,63 | 6 536 165,00 |\n"
        "| Myyntisaamiset/la | 1 209 819,24 | 1 191 012,25 |\n"
        "| Muut saamiset | 4 998 376,39 | 95 345 152,75 |\n"
    )
    new_md, repairs = repair_table_markdown(md)

    assert "| Muut saamiset | 4 998 376,39 | 5 345 152,75 |" in new_md
    assert any(r.row_label == "Muut saamiset" and r.year == "2023" for r in repairs)


def test_repair_tables_noop_when_no_year_columns() -> None:
    md = (
        "| erä | arvo |\n"
        "| --- | --- |\n"
        "| Muut saamiset | 95 345 152,75 |\n"
    )
    new_md, repairs = repair_table_markdown(md)
    assert new_md == md
    assert repairs == []



from __future__ import annotations

from src.ocr_dedup import filter_ocr_text_against_tables


def test_ocr_dedup_removes_numeric_dump_lines_present_in_table() -> None:
    table_md = (
        "| erä | 2024 | 2023 |\n"
        "| --- | --- | --- |\n"
        "| OMA PAAOMA | 12 328 273,74 | 12 451 946,30 |\n"
        "| VASTATTAVAA | 19 502 321,47 | 19 525 668,40 |\n"
    )
    ocr = (
        "VASTATTAVAA\n"
        "OMA PAAOMA 12 328 273,74 12 451 946,30\n"
        "VASTATTAVAA 19 502 321,47 19 525 668,40\n"
        "Tämä on normaalia tekstiä ilman numeroita.\n"
    )

    out = filter_ocr_text_against_tables(ocr_text=ocr, table_markdowns=[table_md])

    assert "OMA PAAOMA 12 328 273,74 12 451 946,30" not in out
    assert "VASTATTAVAA 19 502 321,47 19 525 668,40" not in out
    assert "Tämä on normaalia tekstiä ilman numeroita." in out



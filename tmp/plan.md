## Current state (problem)

- `--comprehensive` completes but produces `total_tables=0` (no extracted tables).
- Visual table extraction code claims “PP-Structure”, but implementation uses plain `PaddleOCR` OCR output grouping.
- Installed `paddleocr==3.3.2` does not expose legacy `PPStructure`; PP-Structure in v3 is `PPStructureV3` and requires `paddlex[ocr]` extras.
- `--visual-tables` path calls `process_table_page_visually(..., lang='fin')` even though Finnish model isn’t supported in this stack and the project mostly uses `lang='en'`.
- Console output can crash on Windows if it prints non-CP1252 characters (UnicodeEncodeError).

## Target state

- Both `--visual-tables` and `--comprehensive` use the same PP-Structure pipeline (`paddleocr.PPStructureV3`) for table recognition.
- `*.tables.json` contains extracted tables (HTML + Markdown + cell confidences when available).
- `*.md` is generated from OCR output only (no invented values); low-confidence cells (<0.90) are marked with `?` and reported.
- Dependencies are consistent with the installed/required PaddleOCR v3 stack.

## Files to change

- `src/comprehensive_table_parser.py`
- `src/table_image_builder.py`
- `src/pipeline.py`
- `requirements.txt`
- `pyproject.toml`

## Checklist

- [ ] Implement a thin PP-Structure wrapper using `PPStructureV3.predict(...)`.
- [ ] Convert `pred_html` -> Markdown table without inventing data.
- [ ] Propagate confidence scores (best-effort mapping) and mark low-confidence cells.
- [ ] Fix `--visual-tables` to use `lang='en'` and PP-Structure.
- [ ] Make Windows console output safe (avoid printing raw HTML).
- [ ] Run a single-page repro (page 150) and confirm `total_tables > 0`.


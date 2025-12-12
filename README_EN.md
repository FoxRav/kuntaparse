# PDF to Markdown/JSON Parser (pdf2md)

This project converts Finnish financial statement PDFs into **LLM-friendly**:
- a **single Markdown document** (page images + OCR text + tables), and
- **structured JSON** for tables + validation reports.

Core principles:
- Table extraction is **visual-first**: **PDF → raster images (`pdf2image`)**.
- No invented numbers. Low-confidence OCR cells are flagged and reported.
- Accounting equations are used as sanity checks and for deterministic repairs (where safe).

## Step-by-step usage

See **`KÄYTTÖOHJE.md`** (Finnish) for a detailed runbook with monitoring commands and the “fail fast” checks.

## Architecture (high level)

### Comprehensive visual mode (`--comprehensive`) — recommended

1. Render all pages to PNG with `pdf2image` (typically 300 DPI)
2. Draw table grids (OpenCV) and run PaddleOCR **PP-StructureV3**
3. Post-process difficult columnar tables into a stable 3-column shape (label/2024/2023)
4. Deterministic repair pass (equation-driven, no guessing)
5. OCR text de-duplication against tables (remove obvious “table dumps”)
6. Validation + reports
7. Write outputs (`.md`, `.tables.json`, `.validation.json`)

### Standard mode (default, not comprehensive)

Uses PyMuPDF prepass + MinerU/Docling/pdfplumber + post-processing.

## Installation (Windows)

### Virtual environment

```powershell
cd <repo_root>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Poppler (required for pdf2image)

Make sure Poppler `bin` is in PATH (see `INSTALL_POPPLER.md`):

```powershell
# Example (adjust to your installation):
$env:Path += ";C:\poppler\Library\bin"
```

### Recommended environment variables (Windows)

```powershell
$env:DISABLE_MODEL_SOURCE_CHECK="True"
$env:HUGGINGFACE_HUB_DISABLE_OFFLINE="1"
$env:HF_HUB_OFFLINE="1"
$env:PYTHONIOENCODING="utf-8"
```

## Usage

### Full document (recommended)

```powershell
.\.venv\Scripts\python.exe -m src.cli data\input.pdf -o out\run_name --comprehensive
```

### Debug / smoke run (single PDF page)

```powershell
.\.venv\Scripts\python.exe -m src.cli data\input.pdf -o out\smoke --comprehensive --comprehensive-start-page 151 --comprehensive-max-pages 1
```

Note: The printed page number inside the PDF may not match the PDF page index. The CLI expects **PDF pages (1-indexed)**.

## Outputs

After a successful run, `out/<run_name>/` contains:
- `<pdf_stem>.md` (single readable document)
- `<pdf_stem>.tables.json` (tables + per-page blocks)
- `<pdf_stem>.validation.json` (low confidence cells + equation checks + applied repairs)

Work artifacts:
- `work/page_images/page_XXXX.png` (rendered pages)
- `work/extracted_tables/*grid.png` (gridded table regions)
- `work/progress.json` (checkpoint during run)

## Quality gates (“did it succeed?”)

### Fast post-run check (seconds, no OCR)

```powershell
.\.venv\Scripts\python.exe -m src.quick_check out\run_name
```

### Definition of “100%”

In practice:
- no low-confidence OCR cells, and
- no accounting equation errors

If either exists, they are listed in `*.validation.json`.

## Monitoring (Windows PowerShell)

Rendered pages:

```powershell
(Get-ChildItem out\run_name\work\page_images\*.png -ErrorAction SilentlyContinue).Count
```

Latest grid image (progress signal during PP-Structure stage):

```powershell
$last=(Get-ChildItem out\run_name\work\extracted_tables\*grid.png -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
"last_grid=$($last.Name) @ $($last.LastWriteTime)"
```

Checkpoint:

```powershell
Get-Content out\run_name\work\progress.json
```



"""Marker-based PDF parser - better for complex tables."""

import subprocess
from pathlib import Path

from .text_cleanup import cleanup_parsed_text


def parse_with_marker(
    pdf_path: Path, 
    out_dir: Path,
    force_ocr: bool = True,
) -> tuple[str, Path | None]:
    """
    Parse PDF using Marker - better for complex tables and Finnish documents.
    
    Marker uses a different approach than Docling and often produces
    better results for multi-column tables like balance sheets.

    Args:
        pdf_path: Path to the input PDF file
        out_dir: Directory for output files
        force_ocr: Force OCR even for text PDFs (recommended for scanned docs)

    Returns:
        Tuple of (markdown_text, output_path)

    Raises:
        FileNotFoundError: If PDF file does not exist
        RuntimeError: If Marker conversion fails
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Marker command - uses marker_single for single file processing
    cmd = [
        "marker_single",
        str(pdf_path),
        str(out_dir),
        "--langs", "Finnish",
    ]
    
    if force_ocr:
        cmd.append("--force_ocr")

    try:
        result = subprocess.run(
            cmd, 
            check=True, 
            capture_output=True, 
            text=True,
            timeout=1800,  # 30 min timeout
        )
        print(f"Marker output: {result.stdout}")
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Marker timed out after 30 minutes: {e}") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Marker conversion failed: {e.stderr}") from e
    except FileNotFoundError:
        raise RuntimeError(
            "Marker CLI not found. Install with: pip install marker-pdf"
        ) from None

    # Marker creates output in subdirectory named after the PDF
    # Structure: out_dir/pdf_name/pdf_name.md
    pdf_name = pdf_path.stem
    
    # Look for markdown file - Marker puts it in a subdirectory
    md_candidates = list(out_dir.rglob("*.md"))
    
    if not md_candidates:
        raise RuntimeError(f"Marker produced no output for {pdf_path}")

    # Get the main markdown file (usually the first/only one)
    md_path = md_candidates[0]
    
    # Read and clean up the markdown
    md_text = md_path.read_text(encoding="utf-8")
    md_text = cleanup_parsed_text(md_text)
    
    return md_text, md_path

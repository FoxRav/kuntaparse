"""MinerU-based PDF parser - state-of-the-art PDF to Markdown conversion."""

import subprocess
from pathlib import Path
import json


def parse_with_mineru(
    pdf_path: Path,
    out_dir: Path,
    use_gpu: bool = True,
) -> tuple[str, Path]:
    """
    Parse PDF using MinerU (magic-pdf) - high-quality table and layout parsing.
    
    MinerU uses PDF-Extract-Kit models for:
    - Layout detection
    - Table structure recognition  
    - OCR
    - Formula detection
    
    Args:
        pdf_path: Path to the input PDF file
        out_dir: Directory for output files
        use_gpu: Whether to use CUDA GPU acceleration
        
    Returns:
        Tuple of (markdown_text, output_directory)
        
    Raises:
        FileNotFoundError: If PDF file does not exist
        RuntimeError: If MinerU conversion fails
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # MinerU command
    cmd = [
        "magic-pdf",
        "-p", str(pdf_path),
        "-o", str(out_dir),
        "-m", "auto",  # auto mode: tries OCR if needed
    ]
    
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
            cwd=str(out_dir.parent),
        )
        print(f"MinerU output: {result.stdout}")
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"MinerU timed out after 1 hour: {e}") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"MinerU conversion failed: {e.stderr}") from e
    except FileNotFoundError:
        raise RuntimeError(
            "MinerU CLI (magic-pdf) not found. Install with: pip install magic-pdf[full]"
        ) from None
    
    # MinerU creates output in structure: out_dir/pdf_name/auto/pdf_name.md
    pdf_name = pdf_path.stem
    
    # Look for markdown file
    md_candidates = list(out_dir.rglob("*.md"))
    
    if not md_candidates:
        raise RuntimeError(f"MinerU produced no markdown output for {pdf_path}")
    
    # Get the main markdown file
    md_path = md_candidates[0]
    md_text = md_path.read_text(encoding="utf-8")
    
    return md_text, md_path.parent


def parse_mineru_with_api(
    pdf_path: Path,
    out_dir: Path,
) -> str:
    """
    Parse PDF using MinerU Python API directly.
    
    This provides more control over the parsing process.
    """
    try:
        from magic_pdf.data.data_reader_writer import FileBasedDataWriter
        from magic_pdf.pipe.UNIPipe import UNIPipe
        from magic_pdf.pipe.OCRPipe import OCRPipe
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError(f"MinerU modules not available: {e}") from e
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Read PDF bytes
    pdf_bytes = pdf_path.read_bytes()
    
    # Create output writer
    image_dir = out_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    
    image_writer = FileBasedDataWriter(str(image_dir))
    
    # Try UNIPipe first (unified pipeline), fallback to OCRPipe
    try:
        # Determine if PDF needs OCR by checking if it has extractable text
        doc = fitz.open(str(pdf_path))
        has_text = False
        for page in doc:
            if page.get_text().strip():
                has_text = True
                break
        doc.close()
        
        if has_text:
            # Use unified pipeline for text PDFs
            pipe = UNIPipe(pdf_bytes, [], image_writer)
        else:
            # Use OCR pipeline for scanned PDFs
            pipe = OCRPipe(pdf_bytes, [], image_writer)
        
        # Run the pipeline
        pipe.pipe_classify()
        pipe.pipe_analyze()
        pipe.pipe_parse()
        
        # Get markdown output
        md_content = pipe.pipe_mk_markdown(str(image_dir))
        
        return md_content
        
    except Exception as e:
        raise RuntimeError(f"MinerU API parsing failed: {e}") from e


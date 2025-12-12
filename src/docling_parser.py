"""Docling-based PDF parser with GPU support - single file output."""

from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
    TableFormerMode,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

from .config import (
    DEFAULT_OCR_LANG,
    IMAGE_SUBDIR,
    NUM_THREADS,
    TABLE_ACCURATE_MODE,
    TABLE_CELL_MATCHING,
)


def build_converter(use_gpu: bool = True) -> DocumentConverter:
    """
    Build DocumentConverter with GPU support and accurate table settings.
    
    Args:
        use_gpu: Whether to use CUDA GPU acceleration
        
    Returns:
        Configured DocumentConverter
    """
    device = AcceleratorDevice.CUDA if use_gpu else AcceleratorDevice.CPU
    
    accelerator_options = AcceleratorOptions(
        device=device,
        num_threads=NUM_THREADS,
    )

    pipeline_options = PdfPipelineOptions(
        accelerator_options=accelerator_options,
        do_ocr=True,
        do_table_structure=True,
    )
    
    # Finnish OCR
    pipeline_options.ocr_options.lang = [DEFAULT_OCR_LANG]

    # Table structure settings - prevent column merging
    pipeline_options.table_structure_options.do_cell_matching = TABLE_CELL_MATCHING
    if TABLE_ACCURATE_MODE:
        pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    return converter


def parse_with_docling(
    pdf_path: Path, 
    out_dir: Path,
    use_gpu: bool = True,
) -> tuple[str, list[Path]]:
    """
    Parse PDF using Docling - outputs single markdown with all content inline.

    Args:
        pdf_path: Path to the input PDF file
        out_dir: Directory for output files
        use_gpu: Whether to use CUDA GPU acceleration

    Returns:
        Tuple of (markdown_text, list_of_image_paths)
        Markdown includes all text, tables, and image references inline.

    Raises:
        FileNotFoundError: If PDF file does not exist
        RuntimeError: If Docling conversion fails
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir = out_dir / IMAGE_SUBDIR
    img_dir.mkdir(parents=True, exist_ok=True)

    converter = build_converter(use_gpu=use_gpu)

    try:
        result = converter.convert(str(pdf_path))
        doc = result.document
    except Exception as e:
        raise RuntimeError(f"Docling conversion failed for {pdf_path}: {e}") from e

    # Build markdown from document elements
    md_parts: list[str] = []
    
    # Export text content
    try:
        # Try markdown export first
        md_text = doc.export_to_markdown()
    except (ModuleNotFoundError, ImportError):
        # Fallback to text export if markdown fails
        md_text = doc.export_to_text()
    
    md_parts.append(md_text)
    
    # Export tables separately if available
    if hasattr(doc, 'tables') and doc.tables:
        md_parts.append("\n\n## Extracted Tables\n")
        for idx, table in enumerate(doc.tables, start=1):
            try:
                df = table.export_to_dataframe()
                if not df.empty:
                    table_md = df.to_markdown(index=False)
                    md_parts.append(f"\n### Table {idx}\n\n{table_md}\n")
            except Exception:
                continue

    full_md = "\n".join(md_parts)

    # Extract and save images
    image_paths: list[Path] = []
    if hasattr(doc, 'iterate_items'):
        for element_idx, element in enumerate(doc.iterate_items()):
            if hasattr(element, "image") and element.image is not None:
                try:
                    pil_image = element.image.pil_image
                    page_no = getattr(element, "page_no", 0)
                    fname = f"{page_no:03d}_{element_idx:04d}.png"
                    out_path = img_dir / fname
                    pil_image.save(out_path)
                    image_paths.append(out_path)
                except Exception:
                    continue

    return full_md, image_paths

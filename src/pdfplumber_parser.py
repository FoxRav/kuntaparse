"""pdfplumber parser for text-based PDFs with complex table structures.

pdfplumber excels at extracting tables from text-based PDFs where
tables have clear cell boundaries. It preserves table structure
better than OCR-based parsers for native PDFs.
"""

from pathlib import Path
from typing import List, Tuple

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def parse_with_pdfplumber(
    pdf_path: Path,
    out_dir: Path,
    use_gpu: bool = False,  # pdfplumber doesn't use GPU
) -> Tuple[str, List[Path]]:
    """
    Parse PDF using pdfplumber, focusing on table extraction.
    
    Args:
        pdf_path: Path to PDF file
        out_dir: Output directory (not heavily used, kept for consistency)
        use_gpu: Ignored (pdfplumber doesn't use GPU)
        
    Returns:
        Tuple of (markdown_text, image_paths)
    """
    if pdfplumber is None:
        raise ImportError(
            "pdfplumber not installed. Install with: pip install pdfplumber"
        )
    
    out_dir.mkdir(parents=True, exist_ok=True)
    
    markdown_parts = []
    image_paths: List[Path] = []
    
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # Extract text
            text = page.extract_text()
            if text:
                markdown_parts.append(f"\n## Page {page_num}\n\n{text}\n")
            
            # Extract tables
            tables = page.extract_tables()
            if tables:
                markdown_parts.append(f"\n### Tables on page {page_num}\n\n")
                
                for table_idx, table in enumerate(tables, start=1):
                    if not table:
                        continue
                    
                    # Convert table to markdown
                    md_table = _table_to_markdown(table)
                    markdown_parts.append(f"\n#### Table {table_idx}\n\n{md_table}\n\n")
            
            # Extract images (if any)
            # pdfplumber doesn't directly extract images, but we can note their positions
            # For actual image extraction, we'd need to use PyMuPDF or similar
    
    markdown_text = "\n".join(markdown_parts)
    
    return markdown_text, image_paths


def _table_to_markdown(table: List[List]) -> str:
    """Convert pdfplumber table (list of lists) to Markdown table."""
    if not table:
        return ""
    
    # Find header row (usually first row)
    header = table[0] if table else []
    
    # Clean header cells
    header_clean = [_clean_cell(cell) for cell in header]
    
    # Build markdown table
    lines = []
    
    # Header
    lines.append("| " + " | ".join(header_clean) + " |")
    lines.append("| " + " | ".join(["---"] * len(header_clean)) + " |")
    
    # Data rows
    for row in table[1:]:
        if row:  # Skip empty rows
            row_clean = [_clean_cell(cell) for cell in row]
            # Pad row if needed
            while len(row_clean) < len(header_clean):
                row_clean.append("")
            # Truncate if too long
            row_clean = row_clean[:len(header_clean)]
            lines.append("| " + " | ".join(row_clean) + " |")
    
    return "\n".join(lines)


def _clean_cell(cell) -> str:
    """Clean a table cell value."""
    if cell is None:
        return ""
    
    # Convert to string and strip
    text = str(cell).strip()
    
    # Replace newlines with spaces
    text = text.replace("\n", " ")
    
    # Normalize multiple spaces
    import re
    text = re.sub(r"\s+", " ", text)
    
    return text


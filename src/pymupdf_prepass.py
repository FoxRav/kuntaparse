"""PyMuPDF-based layout preprocessing for table detection.

Uses PyMuPDF to detect table regions in PDF before passing to MinerU/Docling.
This provides accurate bounding boxes for tables that can be used to:
1. Crop tables to separate images for focused parsing
2. Guide table replacement in post-processing
"""

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


@dataclass
class TableRegion:
    """A detected table region in the PDF."""
    page: int
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    source: str = "pymupdf_heuristic"
    label: str = ""  # Optional: detected label like "Vesihuoltolaitoksen tase"


def detect_table_regions(
    pdf_path: Path,
    min_rows: int = 3,
    min_numeric_ratio: float = 0.3,
) -> List[TableRegion]:
    """
    Detect table regions in PDF using PyMuPDF layout analysis.
    
    Args:
        pdf_path: Path to PDF file
        min_rows: Minimum number of rows to consider a block a table
        min_numeric_ratio: Minimum ratio of numeric content in lines
        
    Returns:
        List of detected table regions
    """
    if fitz is None:
        raise ImportError("PyMuPDF not installed. Install with: pip install pymupdf")
    
    doc = fitz.open(str(pdf_path))
    regions: List[TableRegion] = []
    
    # Known table labels to help detection
    table_labels = [
        r'vesihuoltolaitoksen\s+tase',
        r'taloustiedot\s+\d{4}',
        r'tuloslaskelma',
        r'rahoituslaskelma',
        r'vastaavaa',
        r'vastattavaa',
    ]
    
    for page_index, page in enumerate(doc):
        # Get text blocks with coordinates
        blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
        
        # Group blocks by vertical position (rows)
        row_blocks: dict[float, List[Tuple]] = {}
        
        for block in blocks:
            if len(block) < 5:
                continue
            x0, y0, x1, y1, text, *_rest = block
            
            if not text or not text.strip():
                continue
            
            # Round y0 to group nearby blocks into rows
            row_key = round(y0, 1)
            if row_key not in row_blocks:
                row_blocks[row_key] = []
            row_blocks[row_key].append((x0, y0, x1, y1, text))
        
        # Analyze rows for table-like structure
        numeric_rows = 0
        total_rows = len(row_blocks)
        table_start_y = None
        table_end_y = None
        table_x0 = float('inf')
        table_x1 = 0
        detected_label = ""
        
        for y_pos, blocks_in_row in sorted(row_blocks.items()):
            row_text = ' '.join(block[4] for block in blocks_in_row)
            
            # Check for table labels
            for pattern in table_labels:
                if re.search(pattern, row_text, re.IGNORECASE):
                    detected_label = row_text.strip()
                    table_start_y = y_pos
                    break
            
            # Count numeric content
            numeric_chars = sum(1 for c in row_text if c.isdigit())
            total_chars = len(row_text.replace(' ', ''))
            
            if total_chars > 0:
                numeric_ratio = numeric_chars / total_chars
                if numeric_ratio >= min_numeric_ratio:
                    numeric_rows += 1
                    if table_start_y is None:
                        table_start_y = y_pos
                    table_end_y = y_pos
                    
                    # Expand bounding box
                    for x0, y0, x1, y1, _ in blocks_in_row:
                        table_x0 = min(table_x0, x0)
                        table_x1 = max(table_x1, x1)
        
        # If we found a table-like region, add it
        if numeric_rows >= min_rows and table_start_y is not None:
            # Add some padding
            padding = 20
            bbox = (
                max(0, table_x0 - padding),
                max(0, table_start_y - padding),
                min(page.rect.width, table_x1 + padding),
                min(page.rect.height, (table_end_y or table_start_y) + padding + 50),
            )
            
            regions.append(
                TableRegion(
                    page=page_index,
                    bbox=bbox,
                    label=detected_label or f"Table on page {page_index + 1}",
                )
            )
    
    doc.close()
    return regions


def save_table_regions(pdf_path: Path, out_dir: Path) -> Path:
    """
    Detect and save table regions to JSON.
    
    Args:
        pdf_path: Path to PDF file
        out_dir: Output directory for JSON file
        
    Returns:
        Path to saved JSON file
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    regions = detect_table_regions(pdf_path)
    
    out_json = out_dir / f"{pdf_path.stem}.tables.json"
    
    # Convert to JSON-serializable format
    data = []
    for r in regions:
        d = asdict(r)
        d['bbox'] = list(d['bbox'])  # Convert tuple to list
        data.append(d)
    
    out_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_json


def crop_table_images(
    pdf_path: Path,
    regions_json: Path,
    crop_dir: Path,
    dpi: int = 150,
) -> List[Tuple[int, Path]]:
    """
    Crop table regions from PDF to separate PNG images.
    
    Args:
        pdf_path: Path to source PDF
        regions_json: Path to JSON with table regions
        crop_dir: Directory for cropped images
        dpi: Resolution for output images
        
    Returns:
        List of (page_index, image_path) tuples
    """
    if fitz is None:
        raise ImportError("PyMuPDF not installed. Install with: pip install pymupdf")
    
    crop_dir.mkdir(parents=True, exist_ok=True)
    
    doc = fitz.open(str(pdf_path))
    regions_data = json.loads(regions_json.read_text(encoding="utf-8"))
    
    out_paths: List[Tuple[int, Path]] = []
    
    for idx, r in enumerate(regions_data):
        page_index = r["page"]
        bbox = r["bbox"]
        
        page = doc[page_index]
        rect = fitz.Rect(*bbox)
        
        # Create matrix for desired DPI
        zoom = dpi / 72  # 72 is default PDF DPI
        mat = fitz.Matrix(zoom, zoom)
        
        # Get pixmap of the region
        pix = page.get_pixmap(matrix=mat, clip=rect)
        
        # Save as PNG
        out_path = crop_dir / f"{pdf_path.stem}_table_{idx+1:03d}_p{page_index+1}.png"
        pix.save(str(out_path))
        out_paths.append((page_index, out_path))
    
    doc.close()
    return out_paths


"""Comprehensive table parser for all pages using visual detection + PaddleOCR.

Processes entire PDF page by page:
1. Render each page to image
2. Detect and draw table grid lines
3. Extract tables with PaddleOCR PP-Structure
4. Convert to structured JSON + Markdown
5. Validate accounting equations
"""

import os
import sys

# Set environment variables BEFORE ANY imports
os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['HUGGINGFACE_HUB_DISABLE_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'

from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import json
import numpy as np

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import paddleocr as paddleocr_mod
except ImportError:
    paddleocr_mod = None

from .table_image_builder import draw_table_grid
from .html_table import html_table_to_rows, rows_to_markdown, build_confidence_by_text
from .paddle_device import configure_paddle_device
from .ppstructure_postprocess import OCRToken, try_balance_sheet_3col


def _group_text_lines_from_ocr(
    rec_texts: List[str],
    rec_boxes: Any,
    *,
    y_tol: float = 12.0,
) -> str:
    """Build reading-order text from OCR tokens using y/x coordinates.

    Uses only OCR output (no PDF text). Keeps text as-is (no invention).
    """
    try:
        boxes_list = list(rec_boxes)
    except Exception:
        return "\n".join(t for t in rec_texts if str(t).strip())

    items: List[Tuple[float, float, str]] = []
    for txt, b in zip(rec_texts, boxes_list, strict=False):
        s = str(txt).strip()
        if not s:
            continue
        try:
            x1, y1, x2, y2 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
            xc = (x1 + x2) / 2.0
            yc = (y1 + y2) / 2.0
            items.append((yc, xc, s))
        except Exception:
            items.append((0.0, 0.0, s))

    items.sort(key=lambda t: (t[0], t[1]))

    lines: List[str] = []
    cur: List[str] = []
    cur_y: Optional[float] = None
    for yc, _xc, s in items:
        if cur_y is None:
            cur_y = yc
            cur = [s]
            continue
        if abs(yc - cur_y) <= y_tol:
            cur.append(s)
        else:
            lines.append(" ".join(cur))
            cur_y = yc
            cur = [s]
    if cur:
        lines.append(" ".join(cur))

    return "\n".join(lines).strip()


def get_pdf_page_count(pdf_path: Path) -> int:
    """Get total number of pages in PDF using pdf2image."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError("pdf2image not installed")
    
    try:
        # Convert just first page to get page count
        images = convert_from_path(str(pdf_path), dpi=72, first_page=1, last_page=1)
        if not images:
            return 0
        
        # Use pdfinfo if available, otherwise estimate
        # For now, we'll render all pages and count them
        # This is inefficient but ensures accuracy
        all_images = convert_from_path(str(pdf_path), dpi=72)
        return len(all_images) if all_images else 0
    except Exception:
        # Fallback to PyMuPDF if available
        if fitz is not None:
            doc = fitz.open(str(pdf_path))
            count = len(doc)
            doc.close()
            return count
        raise


def render_all_pages(
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 300,
    max_pages: Optional[int] = None,
    start_page: int = 1,
) -> List[Tuple[int, Path]]:
    """
    Render all PDF pages to images using pdf2image library.
    
    Returns:
        List of (page_number, image_path) tuples
    """
    try:
        from pdf2image import convert_from_path, pdfinfo_from_path
    except ImportError:
        raise ImportError(
            "pdf2image not installed. Install with: pip install pdf2image\n"
            "Also requires poppler-utils. On Windows:\n"
            "1. Download from: https://github.com/oschwartz10612/poppler-windows/releases\n"
            "2. Extract to C:\\poppler or similar\n"
            "3. Add to PATH or set poppler_path parameter"
        )
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        page_images = []

        info = pdfinfo_from_path(str(pdf_path))
        total_pages = int(info.get("Pages", 0))
        if total_pages <= 0:
            return []

        safe_start = max(1, int(start_page))
        if safe_start > total_pages:
            return []

        remaining = total_pages - safe_start + 1
        limit = min(remaining, max_pages) if max_pages is not None else remaining

        # Render one page at a time (mandated) to keep memory stable on large PDFs.
        # If the PNG already exists, reuse it (allows resume without re-render).
        for page_num in range(safe_start, safe_start + limit):
            image_path = output_dir / f"page_{page_num:04d}.png"
            if image_path.exists():
                page_images.append((page_num, image_path))
                continue
            images = convert_from_path(
                str(pdf_path),
                dpi=dpi,
                fmt="png",
                first_page=page_num,
                last_page=page_num,
            )
            if not images:
                continue
            image = images[0]
            image.save(image_path, 'PNG')
            page_images.append((page_num, image_path))
        
        return page_images
    except Exception as e:
        raise RuntimeError(f"Failed to render PDF pages with pdf2image: {e}") from e


def detect_table_regions_in_image(image_path: Path) -> List[Dict]:
    """
    Detect potential table regions in an image using OpenCV.
    
    Returns:
        List of bounding boxes (x, y, width, height) for table regions
    """
    if cv2 is None:
        return []
    
    image = cv2.imread(str(image_path))
    if image is None:
        return []
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    
    # Detect horizontal lines (rows)
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    detect_horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
    
    # Detect vertical lines (columns)
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 30))
    detect_vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
    
    # Combine
    grid = cv2.add(detect_horizontal, detect_vertical)
    
    # Find contours
    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    regions = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > 100 and h > 50:  # Minimum table size
            regions.append({
                'x': int(x),
                'y': int(y),
                'width': int(w),
                'height': int(h),
            })
    
    return regions


def process_page_for_tables(
    page_num: int,
    image_path: Path,
    work_dir: Path,
    pp_engine: Optional[Any] = None,
    use_gpu: bool = True,
) -> tuple[List[Dict], Any]:
    """
    Process a single page to extract all tables.
    
    Returns:
        List of table dictionaries with structure, markdown, and metadata
    """
    # Lazy initialization of PP-Structure engine (PaddleOCR v3: PPStructureV3)
    if pp_engine is None:
        if paddleocr_mod is None or not hasattr(paddleocr_mod, "PPStructureV3"):
            raise ImportError(
                "PP-Structure engine not available. Required stack:\n"
                "- paddleocr==3.3.2\n"
                "- paddlex[ocr]==3.3.11\n"
                "Install in venv: pip install \"paddleocr==3.3.2\" \"paddlex[ocr]==3.3.11\""
            )

        print(f"  Initializing PPStructureV3 (first use on page {page_num})...")
        try:
            configure_paddle_device(use_gpu=use_gpu)
            # Disable optional pipelines we don't need for financial statements.
            pp_engine = paddleocr_mod.PPStructureV3(
                lang="en",
                use_table_recognition=True,
                use_region_detection=False,
                use_doc_unwarping=False,
                use_seal_recognition=False,
                use_formula_recognition=False,
                use_chart_recognition=False,
            )
            print("  PPStructureV3 initialized!")
        except Exception as e:
            print(f"  PPStructureV3 initialization failed: {e}")
            raise
    
    tables: List[Dict] = []
    
    # Load image
    image = cv2.imread(str(image_path))
    if image is None:
        return tables, pp_engine
    
    # Convert BGR to RGB
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    # Detect table regions
    regions = detect_table_regions_in_image(image_path)
    
    if not regions:
        # If no regions detected, try processing entire page
        regions = [{'x': 0, 'y': 0, 'width': image.shape[1], 'height': image.shape[0]}]
    
    for region_idx, region in enumerate(regions):
        # Crop region
        x, y, w, h = region['x'], region['y'], region['width'], region['height']
        cropped = image_rgb[y:y+h, x:x+w]
        
        # Draw grid lines
        grid_image = draw_table_grid(cropped)
        
        # Save grid image for debugging
        grid_path = work_dir / f"page_{page_num:04d}_table_{region_idx}_grid.png"
        cv2.imwrite(str(grid_path), cv2.cvtColor(grid_image, cv2.COLOR_RGB2BGR))
        
        # Run PP-Structure on the gridded image. We avoid printing raw HTML to console
        # to prevent Windows encoding issues.
        try:
            # PPStructureV3 returns a list of page results
            pp_out = pp_engine.predict(
                str(grid_path),
                use_wireless_table_cells_trans_to_html=True,
                use_wired_table_cells_trans_to_html=True,
            )

            if not pp_out:
                continue

            page_res = pp_out[0]
            table_res_list = page_res.get("table_res_list") or []
            if not table_res_list:
                continue

            for table_idx, t in enumerate(table_res_list):
                html = t.get("pred_html") or ""
                if not isinstance(html, str) or not html.strip():
                    continue

                rows = html_table_to_rows(html)
                if not rows:
                    continue

                conf_by_text: Optional[Dict[str, float]] = None
                table_ocr_pred = t.get("table_ocr_pred")
                if isinstance(table_ocr_pred, dict):
                    rec_texts = table_ocr_pred.get("rec_texts")
                    rec_scores = table_ocr_pred.get("rec_scores")
                    rec_boxes = table_ocr_pred.get("rec_boxes")
                    # rec_scores is typically a numpy array in PaddleOCR v3
                    if isinstance(rec_texts, list) and rec_scores is not None:
                        try:
                            rec_scores_list = [float(x) for x in list(rec_scores)]
                            conf_by_text = build_confidence_by_text(rec_texts, rec_scores_list)
                        except Exception:
                            conf_by_text = None

                    # Try domain-specific 3-column reconstruction for balance sheet-like tables.
                    try:
                        if (
                            isinstance(rec_texts, list)
                            and rec_scores is not None
                            and rec_boxes is not None
                            and len(rec_texts) == len(list(rec_scores))
                            and len(rec_texts) == len(list(rec_boxes))
                        ):
                            toks = [
                                OCRToken(
                                    text=str(txt),
                                    confidence=float(sc),
                                    box=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                                )
                                for txt, sc, b in zip(rec_texts, list(rec_scores), list(rec_boxes), strict=False)
                                if str(txt).strip()
                            ]
                            bs = try_balance_sheet_3col(toks)
                            if bs is not None:
                                markdown, low_cells = bs
                                tables.append(
                                    {
                                        "page": page_num,
                                        "region": region_idx,
                                        "table_index": table_idx,
                                        "grid_image": str(grid_path),
                                        "html": html,
                                        "markdown": markdown,
                                        "rows": [],
                                        "low_confidence_cells": low_cells,
                                    }
                                )
                                continue
                    except Exception:
                        # Fall back to HTML-based conversion below.
                        pass

                markdown, low_cells = rows_to_markdown(rows, confidence_by_text=conf_by_text)
                if not markdown.strip():
                    continue

                tables.append(
                    {
                        "page": page_num,
                        "region": region_idx,
                        "table_index": table_idx,
                        "grid_image": str(grid_path),
                        "html": html,
                        "markdown": markdown,
                        "rows": rows,
                        "low_confidence_cells": [
                            {
                                "row": lc.row,
                                "col": lc.col,
                                "text": lc.text,
                                "confidence": lc.confidence,
                            }
                            for lc in low_cells
                        ],
                    }
                )
        except Exception as e:
            print(f"  Error processing table on page {page_num}, region {region_idx}: {e}")
            continue
    
    return tables, pp_engine


def extract_table_structure_from_ocr(ocr_result: List, page_num: int, region_idx: int) -> Optional[Dict]:
    """
    Extract structured table data from PaddleOCR result.
    
    Returns:
        Dict with 'rows', 'columns', 'cells', 'confidence_scores'
    """
    if not ocr_result:
        return None
    
    # PaddleOCR returns: [[[[x1,y1], [x2,y2], [x3,y3], [x4,y4]], (text, confidence)], ...]
    # or sometimes nested differently
    
    # Group detections by row (y-coordinate)
    rows_dict: Dict[int, List[Tuple[float, str, float]]] = {}
    
    for detection in ocr_result:
        try:
            # Handle different result formats
            if not detection or len(detection) < 2:
                continue
            
            # Get bbox - can be detection[0] or nested
            bbox = detection[0]
            if not bbox or not isinstance(bbox, (list, tuple)):
                continue
            
            # Ensure bbox has at least 4 points
            if len(bbox) < 4:
                continue
            
            # Get text info - can be detection[1] or nested
            text_info = detection[1]
            
            # Parse text and confidence
            if isinstance(text_info, tuple):
                if len(text_info) >= 1:
                    text = str(text_info[0]) if text_info[0] else ""
                else:
                    text = ""
                confidence = float(text_info[1]) if len(text_info) > 1 else 1.0
            elif isinstance(text_info, str):
                text = text_info
                confidence = 1.0
            else:
                text = str(text_info) if text_info else ""
                confidence = 1.0
            
            # Skip empty text
            if not text or not text.strip():
                continue
            
            # Validate bbox points
            try:
                # Calculate center coordinates
                valid_points = [p for p in bbox if isinstance(p, (list, tuple)) and len(p) >= 2]
                if len(valid_points) < 4:
                    continue
                
                y_center = sum(float(point[1]) for point in valid_points) / len(valid_points)
                x_center = sum(float(point[0]) for point in valid_points) / len(valid_points)
                
                # Round y to group into rows (10 pixel tolerance)
                y_key = int(y_center / 10) * 10
                
                if y_key not in rows_dict:
                    rows_dict[y_key] = []
                
                rows_dict[y_key].append((x_center, text, confidence))
            except (IndexError, TypeError, ValueError) as e:
                continue
        except (IndexError, TypeError, ValueError, AttributeError) as e:
            # Skip malformed detections
            continue
    
    # Sort rows by y, cells by x
    sorted_rows = sorted(rows_dict.items())
    
    if not sorted_rows:
        return None
    
    # Build table structure
    table_rows = []
    max_cols = max(len(row[1]) for row in sorted_rows)
    
    for y_key, cells in sorted_rows:
        # Sort cells by x-coordinate
        cells_sorted = sorted(cells, key=lambda x: x[0])
        
        row_data = {
            'cells': [],
            'min_confidence': min(c[2] for c in cells_sorted) if cells_sorted else 1.0,
        }
        
        for x_center, text, confidence in cells_sorted:
            row_data['cells'].append({
                'text': text,
                'confidence': confidence,
                'x_center': float(x_center),
            })
        
        # Pad to max_cols
        while len(row_data['cells']) < max_cols:
            row_data['cells'].append({
                'text': '',
                'confidence': 1.0,
                'x_center': 0.0,
            })
        
        table_rows.append(row_data)
    
    return {
        'rows': table_rows,
        'num_rows': len(table_rows),
        'num_cols': max_cols,
    }


def table_to_markdown(table_data: Dict, table_title: str = "") -> str:
    """
    Convert table structure to Markdown format.
    
    Format:
    ### Table Title
    
    | Column 1 | Column 2 | Column 3 |
    |----------|----------|----------|
    | Value 1  | Value 2  | Value 3  |
    
    Args:
        table_data: Table structure dict with 'rows'
        table_title: Optional title for the table
        
    Returns:
        Markdown table string
    """
    if not table_data or 'rows' not in table_data:
        return ""
    
    rows = table_data['rows']
    if not rows:
        return ""
    
    lines = []
    
    # Add title if provided
    if table_title:
        lines.append(f"### {table_title}\n")
    
    # Header row (use first row as header)
    if rows:
        header_cells = rows[0]['cells']
        header_texts = [cell['text'] for cell in header_cells]
        lines.append("| " + " | ".join(header_texts) + " |")
        lines.append("| " + " | ".join(["---"] * len(header_texts)) + " |")
    
    # Data rows
    for row in rows[1:]:
        cell_texts = []
        for cell in row['cells']:
            text = cell['text']
            # Add ? if confidence is low (< 0.90)
            if cell.get('confidence', 1.0) < 0.90:
                text = text + "?"
            cell_texts.append(text)
        lines.append("| " + " | ".join(cell_texts) + " |")
    
    return "\n".join(lines)


def process_all_pages_comprehensive(
    pdf_path: Path,
    work_dir: Path,
    dpi: int = 300,
    max_pages: Optional[int] = None,
    start_page: int = 1,
    use_gpu: bool = True,
) -> Dict:
    """
    Process entire PDF comprehensively: all pages, all tables.
    
    Returns:
        Dict with 'tables', 'pages_processed', 'total_tables'
    """
    print(f"Processing all pages from {pdf_path.name}...")
    
    # Step 1: Render all pages
    print("Step 1: Rendering all pages to images...")
    images_dir = work_dir / "page_images"
    page_images = render_all_pages(
        pdf_path,
        images_dir,
        dpi=dpi,
        max_pages=max_pages,
        start_page=start_page,
    )
    print(f"  Rendered {len(page_images)} pages")
    
    # Step 2: Initialize PP-Structure engine once (lazy initialization - only when needed)
    print("Step 2: PP-Structure (PPStructureV3) will be initialized when processing first table...")
    pp_engine = None  # Initialize lazily
    
    # Step 3: Process each page
    print("Step 3: Processing pages for tables...")
    all_tables = []
    pages_out: List[Dict[str, Any]] = []
    tables_dir = work_dir / "extracted_tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    progress_path = work_dir / "progress.json"
    
    for idx, (page_num, image_path) in enumerate(page_images, start=1):
        print(f"  Processing page {page_num} ({idx}/{len(page_images)})...")

        # Extract OCR text for the whole page (for full-document output).
        page_text = ""
        try:
            configure_paddle_device(use_gpu=use_gpu)
            if pp_engine is None:
                # Let the table path initialize it (ensures consistent settings)
                pass
            # If engine is already initialized, use it to OCR the raw page image as well.
            if pp_engine is not None:
                raw_out = pp_engine.predict(str(image_path))
                if raw_out and isinstance(raw_out, list):
                    overall = raw_out[0].get("overall_ocr_res") if isinstance(raw_out[0], dict) else None
                    if isinstance(overall, dict):
                        rec_texts = overall.get("rec_texts") or []
                        rec_boxes = overall.get("rec_boxes")
                        if isinstance(rec_texts, list) and rec_boxes is not None:
                            page_text = _group_text_lines_from_ocr(rec_texts, rec_boxes)
        except Exception:
            page_text = ""

        page_tables, pp_engine = process_page_for_tables(
            page_num,
            image_path,
            tables_dir,
            pp_engine=pp_engine,
            use_gpu=use_gpu,
        )

        # If engine got initialized inside process_page_for_tables, we can now OCR the page as well.
        if not page_text and pp_engine is not None:
            try:
                raw_out = pp_engine.predict(str(image_path))
                if raw_out and isinstance(raw_out, list):
                    overall = raw_out[0].get("overall_ocr_res") if isinstance(raw_out[0], dict) else None
                    if isinstance(overall, dict):
                        rec_texts = overall.get("rec_texts") or []
                        rec_boxes = overall.get("rec_boxes")
                        if isinstance(rec_texts, list) and rec_boxes is not None:
                            page_text = _group_text_lines_from_ocr(rec_texts, rec_boxes)
            except Exception:
                page_text = ""

        pages_out.append(
            {
                "page": page_num,
                "page_image": str(image_path),
                "text": page_text,
            }
        )
        
        if page_tables:
            print(f"    Found {len(page_tables)} table(s)")
            all_tables.extend(page_tables)
        else:
            print("    No tables found")

        # Write a small checkpoint so a crash doesn't lose the entire run.
        try:
            progress_path.write_text(
                json.dumps(
                    {
                        "pdf": str(pdf_path),
                        "dpi": dpi,
                        "start_page": start_page,
                        "max_pages": max_pages,
                        "last_processed_page": page_num,
                        "pages_done": idx,
                        "pages_total": len(page_images),
                        "tables_so_far": len(all_tables),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
    
    print(f"\nTotal tables extracted: {len(all_tables)}")
    
    return {
        "pages": pages_out,
        'tables': all_tables,
        'pages_processed': len(page_images),
        'total_tables': len(all_tables),
    }


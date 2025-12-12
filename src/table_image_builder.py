"""Visual table structure detection using OpenCV and PaddleOCR.

Renders PDF pages as images, draws grid lines between text blocks,
and uses PaddleOCR PP-Structure to extract structured tables.
"""

import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None

# Must be set before importing paddleocr to avoid slow network checks / hanging.
os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("HUGGINGFACE_HUB_DISABLE_OFFLINE", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

try:
    import paddleocr as paddleocr_mod
except ImportError:
    paddleocr_mod = None

from .html_table import html_table_to_rows, rows_to_markdown, build_confidence_by_text
from .paddle_device import configure_paddle_device
from .ppstructure_postprocess import OCRToken, try_balance_sheet_3col


def pdf_page_to_image(pdf_path: Path, page_number: int, dpi: int = 300) -> Optional[np.ndarray]:
    """
    Render PDF page to image.
    
    Uses pdf2image as mandated (requires Poppler).
    
    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        dpi: Resolution for rendering
        
    Returns:
        Image as numpy array (RGB) or None if failed
    """
    if convert_from_path is not None:
        try:
            images = convert_from_path(
                str(pdf_path),
                dpi=dpi,
                first_page=page_number,
                last_page=page_number,
            )
            if images:
                return np.array(images[0])
        except Exception as e:
            print(f"  Error rendering PDF page {page_number} with pdf2image: {e}")
            return None
    else:
        raise ImportError(
            "pdf2image not available. Install with: pip install pdf2image"
        )
    
    return None


def draw_table_grid(image: np.ndarray) -> np.ndarray:
    """
    Draw grid lines between text rows and columns using OpenCV.
    
    Uses morphological operations to detect text regions and draws
    horizontal and vertical lines to create a visual table structure.
    
    Improved version: Detects gaps between text rows/columns automatically
    using morphological analysis.
    
    Args:
        image: Input image (RGB numpy array)
        
    Returns:
        Image with grid lines drawn
    """
    if cv2 is None:
        raise ImportError("opencv-python not installed. Install with: pip install opencv-python-headless")
    
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    
    # Binary threshold - invert so text is white
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
    
    # Detect horizontal lines (rows) - use larger kernel for better detection
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (image.shape[1] // 3, 1))
    detect_horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
    
    # Detect vertical lines (columns) - use adaptive kernel size
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, image.shape[0] // 10))
    detect_vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
    
    # Dilate to connect nearby lines
    horizontal_dilated = cv2.dilate(detect_horizontal, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1)), iterations=1)
    vertical_dilated = cv2.dilate(detect_vertical, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5)), iterations=1)
    
    # Combine horizontal and vertical
    grid = cv2.add(horizontal_dilated, vertical_dilated)
    
    # Draw lines on original image
    result = image.copy()
    
    # Draw horizontal lines (row separators)
    h_contours, _ = cv2.findContours(horizontal_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in h_contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w > image.shape[1] * 0.3:  # At least 30% of image width
            # Draw horizontal line
            cv2.line(result, (0, y + h // 2), (image.shape[1], y + h // 2), (0, 0, 0), 2)
    
    # Draw vertical lines (column separators)
    v_contours, _ = cv2.findContours(vertical_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in v_contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if h > image.shape[0] * 0.2:  # At least 20% of image height
            # Draw vertical line
            cv2.line(result, (x + w // 2, 0), (x + w // 2, image.shape[0]), (0, 0, 0), 2)
    
    return result


def run_paddleocr_table(
    image_path_or_np: Any, lang: str = "en", use_gpu: bool = True
) -> Optional[List[Dict[str, Any]]]:
    """
    Run PaddleOCR v3 PP-Structure (PPStructureV3) to extract table structure.
    
    Args:
        image_path_or_np: Image path (preferred) or numpy array
        lang: Language code (default: 'en')
        
    Returns:
        List of table result dicts (table_res_list) or None if failed
    """
    if paddleocr_mod is None or not hasattr(paddleocr_mod, "PPStructureV3"):
        raise ImportError(
            "PP-Structure engine not available. Required stack:\n"
            "- paddleocr==3.3.2\n"
            "- paddlex[ocr]==3.3.11\n"
            "Install: pip install \"paddleocr==3.3.2\" \"paddlex[ocr]==3.3.11\""
        )
    
    try:
        configure_paddle_device(use_gpu=use_gpu)
        pp_engine = paddleocr_mod.PPStructureV3(
            lang=lang,
            use_table_recognition=True,
            use_region_detection=False,
            use_doc_unwarping=False,
            use_seal_recognition=False,
            use_formula_recognition=False,
            use_chart_recognition=False,
        )
        pp_out = pp_engine.predict(
            image_path_or_np,
            use_wireless_table_cells_trans_to_html=True,
            use_wired_table_cells_trans_to_html=True,
        )
        if not pp_out:
            return None
        page_res = pp_out[0]
        table_res_list = page_res.get("table_res_list") or []
        return table_res_list if table_res_list else None
    except Exception as e:
        print(f"  PaddleOCR error: {e}")
        return None


def extract_table_from_paddleocr_result(result: List[Dict[str, Any]]) -> Optional[str]:
    """
    Extract table structure from PP-Structure result and convert to Markdown.
    
    Args:
        result: PaddleOCR result list
        
    Returns:
        Markdown table string or None
    """
    if not result:
        return None

    first = result[0]
    html = first.get("pred_html") if isinstance(first, dict) else None
    if not isinstance(html, str) or not html.strip():
        return None

    rows = html_table_to_rows(html)
    if not rows:
        return None

    conf_by_text: Optional[Dict[str, float]] = None
    table_ocr_pred = first.get("table_ocr_pred") if isinstance(first, dict) else None
    if isinstance(table_ocr_pred, dict):
        rec_texts = table_ocr_pred.get("rec_texts")
        rec_scores = table_ocr_pred.get("rec_scores")
        if isinstance(rec_texts, list) and rec_scores is not None:
            try:
                rec_scores_list = [float(x) for x in list(rec_scores)]
                conf_by_text = build_confidence_by_text(rec_texts, rec_scores_list)
            except Exception:
                conf_by_text = None

    # Try domain-specific 3-column reconstruction if we have token boxes.
    try:
        if isinstance(table_ocr_pred, dict):
            rec_texts = table_ocr_pred.get("rec_texts")
            rec_scores = table_ocr_pred.get("rec_scores")
            rec_boxes = table_ocr_pred.get("rec_boxes")
            if rec_texts is not None and rec_scores is not None and rec_boxes is not None:
                toks = [
                    OCRToken(
                        text=str(txt),
                        confidence=float(sc),
                        box=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                    )
                    for txt, sc, b in zip(list(rec_texts), list(rec_scores), list(rec_boxes), strict=False)
                    if str(txt).strip()
                ]
                bs = try_balance_sheet_3col(toks)
                if bs is not None:
                    markdown, _low_cells = bs
                    return markdown if markdown.strip() else None
    except Exception:
        pass

    markdown, _low = rows_to_markdown(rows, confidence_by_text=conf_by_text)
    return markdown if markdown.strip() else None


def process_table_page_visually(
    pdf_path: Path,
    page_number: int,
    output_dir: Path,
    lang: str = 'en',
    use_gpu: bool = True,
) -> Optional[str]:
    """
    Process a single PDF page visually to extract table structure.
    
    Workflow:
    1. Render PDF page to image
    2. Draw grid lines between text blocks
    3. Run PaddleOCR with structure detection
    4. Extract table as Markdown
    
    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        output_dir: Directory for intermediate images
        lang: Language code for OCR
        
    Returns:
        Markdown table string or None
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Render PDF page
    print(f"  Rendering page {page_number} to image...")
    image = pdf_page_to_image(pdf_path, page_number, dpi=300)
    
    if image is None:
        return None
    
    # Step 2: Draw grid lines
    print(f"  Drawing grid lines...")
    grid_image = draw_table_grid(image)
    
    # Save intermediate image for debugging
    grid_path = output_dir / f"page_{page_number}_grid.png"
    cv2.imwrite(str(grid_path), cv2.cvtColor(grid_image, cv2.COLOR_RGB2BGR))
    print(f"  Saved grid image: {grid_path}")
    
    # Step 3: Run PaddleOCR
    print(f"  Running PaddleOCR with structure detection...")
    # Prefer passing the saved file path to PPStructureV3
    result = run_paddleocr_table(str(grid_path), lang=lang, use_gpu=use_gpu)
    
    if result is None:
        return None
    
    # Step 4: Extract table
    print(f"  Extracting table structure...")
    markdown_table = extract_table_from_paddleocr_result(result)
    
    return markdown_table


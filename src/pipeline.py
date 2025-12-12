"""PDF processing pipeline - PyMuPDF prepass + MinerU/Docling + table fixes."""

import json
from pathlib import Path
from typing import List, Dict

from .config import DEFAULT_OUT_DIR
from .pymupdf_prepass import save_table_regions, crop_table_images
from .table_fixer import fix_parsed_tables
from .text_cleanup import cleanup_parsed_text
from .validate_financials import validate_all_financials, format_validation_report, add_validation_comments_to_markdown
from .repair_tables import repair_table_markdown, RepairRecord
from .ocr_dedup import filter_ocr_text_against_tables


def process_pdf(
    pdf_path: Path,
    out_dir: Path | None = None,
    use_mineru: bool = True,
    use_gpu: bool = True,
    validate_with_second_parser: bool = False,
    use_visual_table_detection: bool = False,
    visual_table_pages: List[int] | None = None,
    comprehensive_mode: bool = False,
    comprehensive_max_pages: int | None = None,
    comprehensive_start_page: int = 1,
) -> Path:
    """
    Process a single PDF file with PyMuPDF prepass + MinerU/Docling + fixes.

    Workflow:
    1. PyMuPDF detects table regions and creates cropped images
    2. MinerU/Docling parses full PDF + table images
    3. Post-processing fixes tables using accounting formulas

    Args:
        pdf_path: Path to the input PDF file
        out_dir: Directory for output files (defaults to DEFAULT_OUT_DIR)
        use_mineru: Use MinerU as primary parser (recommended for tables)
        use_gpu: Whether to use CUDA GPU acceleration

    Returns:
        Path to the generated markdown file

    Raises:
        FileNotFoundError: If PDF file does not exist
        RuntimeError: If parsing fails
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    out_dir = out_dir or DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    
    work_dir = out_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Comprehensive mode: process ALL pages with visual detection
    if comprehensive_mode:
        print("=" * 70)
        print("COMPREHENSIVE MODE: Processing all pages with visual table detection")
        print("=" * 70)
        
        try:
            from .comprehensive_table_parser import process_all_pages_comprehensive
            # validate_financials functions are imported at module level; don't re-import here
            # to avoid local-variable shadowing if comprehensive mode fails and falls back.
            
            # Process all pages
            result = process_all_pages_comprehensive(
                pdf_path,
                work_dir,
                dpi=300,
                max_pages=comprehensive_max_pages,
                start_page=comprehensive_start_page,
                use_gpu=use_gpu,
            )

            # Repair pass (deterministic, equation-based) on extracted tables.
            repairs: List[Dict] = []
            for table in result.get("tables", []):
                md = table.get("markdown") or ""
                if not md:
                    continue
                new_md, rep = repair_table_markdown(md)
                if rep:
                    table["markdown"] = new_md
                    for r in rep:
                        repairs.append(
                            {
                                "page": table.get("page", 0),
                                "region": table.get("region", 0),
                                "reason": r.table_reason,
                                "row_label": r.row_label,
                                "year": r.year,
                                "old": r.old_text,
                                "new": r.new_text,
                            }
                        )

            # Build comprehensive markdown
            md_parts = []
            md_parts.append(f"# {pdf_path.stem}\n\n")
            md_parts.append(f"*Comprehensive extraction: pages (image+OCR text) + tables*\n\n")

            # Index tables by page for quick lookup
            tables_by_page: Dict[int, List[Dict]] = {}
            for table in result.get("tables", []):
                page = int(table.get("page", 0) or 0)
                tables_by_page.setdefault(page, []).append(table)

            # Emit ALL pages in order (not only pages with tables)
            for page_item in result.get("pages", []):
                page_num = int(page_item.get("page", 0) or 0)
                md_parts.append(f"\n## Page {page_num}\n\n")

                # Page image reference (keeps original visual context)
                page_image = page_item.get("page_image")
                if page_image:
                    md_parts.append(f"![Page {page_num}]({page_image})\n\n")

                # OCR text (reading order best-effort)
                text_block = (page_item.get("text") or "").strip()
                page_tables = tables_by_page.get(page_num, [])
                text_block = filter_ocr_text_against_tables(
                    ocr_text=text_block,
                    table_markdowns=[t.get("markdown") or "" for t in page_tables],
                )
                if text_block:
                    md_parts.append("### OCR text\n\n")
                    md_parts.append(text_block)
                    md_parts.append("\n\n")

                # Tables
                page_tables = tables_by_page.get(page_num, [])
                if page_tables:
                    md_parts.append("### Tables\n\n")
                    for table_idx, table in enumerate(page_tables):
                        if table.get("markdown"):
                            md_parts.append(f"#### Table {table_idx + 1}\n\n")
                            md_parts.append(table["markdown"])
                            md_parts.append("\n\n")
            
            md_text = "".join(md_parts)
            
            # Save tables as JSON
            tables_json_path = out_dir / f"{pdf_path.stem}.tables.json"
            with open(tables_json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\nSaved tables JSON: {tables_json_path}")
            
            # Validate financial equations
            print("\nValidating financial equations...")
            validations = validate_all_financials(md_text)
            
            # Add validation comments to markdown
            md_text = add_validation_comments_to_markdown(md_text, validations)
            
            # Collect low confidence cells from all tables
            low_confidence_cells = []
            for table in result['tables']:
                if 'low_confidence_cells' in table:
                    for cell in table['low_confidence_cells']:
                        low_confidence_cells.append({
                            'page': table.get('page', 0),
                            'region': table.get('region', 0),
                            'row': cell['row'],
                            'col': cell['col'],
                            'text': cell['text'],
                            'confidence': cell['confidence'],
                        })
            
            # Save validation report
            validation_report_path = out_dir / f"{pdf_path.stem}.validation.json"
            validation_data = {
                'pdf': str(pdf_path),
                'pages_processed': result['pages_processed'],
                'total_tables': result['total_tables'],
                'repairs': repairs,
                'low_confidence': {
                    'total_cells': len(low_confidence_cells),
                    'cells': low_confidence_cells,
                },
                'validations': {
                    'balance_sheet': [
                        {
                            'type': v.type,
                            'equation': v.equation,
                            'expected': v.expected,
                            'actual': v.actual,
                            'difference': v.difference,
                            'context': v.context,
                        }
                        for v in validations['balance_sheet']
                    ],
                    'income_statement': [
                        {
                            'type': v.type,
                            'equation': v.equation,
                            'expected': v.expected,
                            'actual': v.actual,
                            'difference': v.difference,
                            'context': v.context,
                        }
                        for v in validations['income_statement']
                    ],
                },
            }
            
            with open(validation_report_path, 'w', encoding='utf-8') as f:
                json.dump(validation_data, f, indent=2, ensure_ascii=False)
            print(f"Saved validation report: {validation_report_path}")
            
            # Save markdown
            md_path = out_dir / f"{pdf_path.stem}.md"
            md_path.write_text(md_text, encoding="utf-8")
            
            print(f"\nDone: {md_path}")
            print(f"Total tables extracted: {result['total_tables']}")
            print(f"Pages processed: {result['pages_processed']}")
            
            return md_path
            
        except ImportError as e:
            print(f"Comprehensive mode failed: {e}")
            print("Falling back to standard mode...")
            comprehensive_mode = False
        except Exception as e:
            print(f"Comprehensive mode error: {e}")
            print("Falling back to standard mode...")
            comprehensive_mode = False
    
    if comprehensive_mode:
        return  # Already processed above

    # Step 0: Visual table detection for problematic pages (optional)
    visual_tables: Dict[int, str] = {}
    if use_visual_table_detection:
        print("Step 0: Visual table detection for problematic pages...")
        try:
            from .table_image_builder import process_table_page_visually
            
            # Default: process page 37 (Vesihuoltolaitoksen tase) if not specified
            pages_to_process = visual_table_pages or [37]
            
            for page_num in pages_to_process:
                print(f"  Processing page {page_num} visually...")
                table_md = process_table_page_visually(
                    pdf_path,
                    page_num,
                    work_dir / "visual_tables",
                    lang='en',  # Use English models (works well for numbers/tables)
                    use_gpu=use_gpu,
                )
                if table_md:
                    visual_tables[page_num] = table_md
                    print(f"  Extracted table from page {page_num}")
        except ImportError as e:
            print(f"  Visual table detection not available: {e}")
            print("  Install: pip install opencv-python-headless pdf2image paddleocr")
        except Exception as e:
            print(f"  Visual table detection failed: {e}")
            print("  Continuing with standard parsing...")
    
    # Step 1: PyMuPDF prepass - detect table regions
    print("\nStep 1: PyMuPDF prepass - detecting table regions...")
    try:
        regions_json = save_table_regions(pdf_path, work_dir / "regions")
        print(f"  Found table regions, saved to: {regions_json}")
        
        # Crop table images for focused parsing
        table_images = crop_table_images(
            pdf_path,
            regions_json,
            work_dir / "tables",
            dpi=150,
        )
        print(f"  Cropped {len(table_images)} table images")
    except Exception as e:
        print(f"  PyMuPDF prepass failed: {e}")
        print("  Continuing without prepass...")
        regions_json = None
        table_images = []

    # Step 2: Parse with MinerU or Docling
    md_text: str = ""
    second_parser_text: str = ""

    if use_mineru:
        print("\nStep 2: Using MinerU parser (state-of-the-art for tables)...")
        try:
            from .mineru_parser import parse_with_mineru
            md_text, _ = parse_with_mineru(pdf_path, work_dir / "mineru", use_gpu=use_gpu)
            print(f"  MinerU parsing successful: {len(md_text):,} characters")
        except Exception as e:
            print(f"  MinerU failed: {e}")
            print("  Falling back to Docling...")
            use_mineru = False

    if not use_mineru or not md_text:
        print("\nStep 2: Using Docling parser...")
        try:
            from .docling_parser import parse_with_docling
            raw_text, image_paths = parse_with_docling(pdf_path, work_dir / "docling", use_gpu=use_gpu)
            md_text = raw_text
            print(f"  Docling parsing successful: {len(md_text):,} characters")
            if image_paths:
                print(f"  Extracted {len(image_paths)} images")
        except Exception as e:
            raise RuntimeError(f"All parsers failed: {e}") from e
    
    # Optional: Cross-validate with second parser
    if validate_with_second_parser:
        print("\nStep 2b: Cross-validation with second parser...")
        try:
            if use_mineru:
                # Use Docling as second parser
                from .docling_parser import parse_with_docling
                second_parser_text, _ = parse_with_docling(pdf_path, work_dir / "docling_validate", use_gpu=use_gpu)
                second_parser_name = "Docling"
            else:
                # Use pdfplumber as second parser (if text-based PDF)
                from .pdfplumber_parser import parse_with_pdfplumber
                second_parser_text, _ = parse_with_pdfplumber(pdf_path, work_dir / "pdfplumber_validate", use_gpu=False)
                second_parser_name = "pdfplumber"
            
            if second_parser_text:
                from .validation import compare_parsers, validate_accounting_equations
                
                discrepancies = compare_parsers(
                    parser1_text=md_text,
                    parser2_text=second_parser_text,
                    parser1_name="Primary",
                    parser2_name=second_parser_name,
                )
                
                if discrepancies:
                    print(f"  Found {sum(len(d) for d in discrepancies.values())} discrepancies")
                    for table, diffs in discrepancies.items():
                        print(f"    {table}: {len(diffs)} differences")
                else:
                    print("  No discrepancies found - parsers agree!")
                
                # Validate accounting equations
                validations = validate_accounting_equations(md_text)
                if validations:
                    print(f"  Found {len(validations)} accounting equation errors")
                    for v in validations:
                        print(f"    {v['equation']}: diff = {v['difference']:.2f}")
                else:
                    print("  Accounting equations validated - all correct!")
        except Exception as e:
            print(f"  Cross-validation failed: {e}")
            print("  Continuing with primary parser only...")

    # Step 3: Integrate visual tables if available
    if visual_tables:
        print("\nStep 3a: Integrating visually extracted tables...")
        # Replace problematic sections with visual table results
        # This is a placeholder - in practice, you'd match page numbers to sections
        for page_num, table_md in visual_tables.items():
            # Find section in markdown and replace with visual table
            # For now, just append as a note
            md_text += f"\n\n<!-- Visual table extracted from page {page_num} -->\n{table_md}\n"
        print(f"  Integrated {len(visual_tables)} visual tables")
    
    # Step 3: Post-processing
    print("\nStep 3: Post-processing...")
    
    # Apply text cleanup (merged words, number spacing)
    md_text = cleanup_parsed_text(md_text)
    print("  Applied text cleanup")

    # Apply all table fixes including domain-specific balance sheet corrections
    # Pass regions_json for potential coordinate-based fixes
    md_text = fix_parsed_tables(md_text)
    print("  Applied table fixes and balance sheet validation")
    
    # Validate financial equations
    validations = validate_all_financials(md_text)
    if any(validations.values()):
        # Add validation comments to markdown
        md_text = add_validation_comments_to_markdown(md_text, validations)
        
        report = format_validation_report(validations)
        # Save validation report
        validation_report_path = out_dir / f"{pdf_path.stem}.validation.txt"
        validation_report_path.write_text(report, encoding="utf-8")
        print(f"  Financial validation: {sum(len(v) for v in validations.values())} issues found")
        print(f"  Validation report: {validation_report_path}")
    else:
        print("  Financial validation: All equations validated correctly!")

    # Step 4: Save final output
    md_path = out_dir / f"{pdf_path.stem}.md"
    md_path.write_text(md_text, encoding="utf-8")

    print(f"\nDone: {md_path}")
    print(f"Final content: {len(md_text):,} characters")
    
    if regions_json:
        print(f"Table regions: {regions_json}")
    if table_images:
        print(f"Table images: {work_dir / 'tables'}")

    return md_path

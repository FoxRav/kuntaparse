#!/usr/bin/env python
"""Test comprehensive mode directly."""
import os
import sys

# Set environment variables BEFORE ANY imports
os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['HUGGINGFACE_HUB_DISABLE_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'

from pathlib import Path
from src.comprehensive_table_parser import process_all_pages_comprehensive

if __name__ == '__main__':
    print("=" * 70)
    print("TESTING COMPREHENSIVE MODE")
    print("=" * 70)
    
    pdf_path = Path('data/Lapua-Tilinpaatos-2024.pdf')
    work_dir = Path('out/lapua_2024/work')
    
    print(f"PDF: {pdf_path}")
    print(f"Work dir: {work_dir}")
    print()
    
    try:
        result = process_all_pages_comprehensive(pdf_path, work_dir, dpi=72)
        print()
        print("=" * 70)
        print("SUCCESS!")
        print(f"Pages processed: {result['pages_processed']}")
        print(f"Total tables: {result['total_tables']}")
        print("=" * 70)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


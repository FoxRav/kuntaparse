"""Golden truth tests for PDF parser.

Tests parser output against manually verified "golden truth" data.
"""

import json
from pathlib import Path
import pytest

# Golden truth data for known tables
GOLDEN_TRUTH = {
    "Lapua-Tilinpaatos-2024": {
        "Vesihuoltolaitoksen tase": {
            "rows": [
                {
                    "label": "VASTAAVAA",
                    "value_2024": 19502321.47,
                    "value_2023": 19525668.40,
                },
                {
                    "label": "OMA PÄÄOMA",
                    "value_2024": 12328273.74,
                    "value_2023": 12451946.30,
                },
                {
                    "label": "Peruspääoma",
                    "value_2024": 207755.92,
                    "value_2023": 207755.92,
                },
                {
                    "label": "Edellisten tilikausien yli-/alijäämä",
                    "value_2024": 12244190.38,
                    "value_2023": 11927203.58,
                },
                {
                    "label": "Tilikauden yli-/alijäämä",
                    "value_2024": -123672.56,
                    "value_2023": 316986.80,
                },
                {
                    "label": "VIERAS PÄÄOMA",
                    "value_2024": 7174047.73,
                    "value_2023": 7073722.10,
                },
                {
                    "label": "VAIHTUVAT VASTAAVAT",
                    "value_2024": 6536165.00,
                    "value_2023": 6536165.00,
                },
                {
                    "label": "Myyntisaamiset",
                    "value_2024": 1191012.25,
                    "value_2023": 1191012.25,
                },
                {
                    "label": "Muut saamiset",
                    "value_2024": 4998376.39,
                    "value_2023": 5345152.75,  # Corrected value (not 95345152.75)
                },
            ]
        }
    }
}


def parse_finnish_amount(text: str) -> float | None:
    """Convert Finnish format number to float."""
    if not text:
        return None
    try:
        clean = text.strip().replace(' ', '').replace(',', '.')
        return float(clean)
    except ValueError:
        return None


def extract_table_from_markdown(markdown_text: str, table_label: str) -> list[dict]:
    """
    Extract table rows from markdown text.
    
    Returns:
        List of dicts with 'label', 'value_2024', 'value_2023'
    """
    import re
    
    # Find table section
    pattern = rf'(?i){re.escape(table_label)}'
    match = re.search(pattern, markdown_text)
    
    if not match:
        return []
    
    # Extract table (next 200 lines or until next ## header)
    start = match.start()
    end_match = re.search(r'\n##\s+', markdown_text[start + 200:])
    if end_match:
        end = start + 200 + end_match.start()
    else:
        end = min(start + 2000, len(markdown_text))
    
    table_section = markdown_text[start:end]
    
    # Parse table rows
    rows = []
    amount_re = re.compile(r'-?\d{1,3}(?:\s?\d{3})*,\d{2}')
    
    for line in table_section.split('\n'):
        if '|' not in line:
            continue
        
        # Extract row
        cells = [c.strip() for c in line.split('|') if c.strip()]
        if len(cells) < 2:
            continue
        
        # First cell is label, rest are values
        label = cells[0]
        values = []
        
        for cell in cells[1:]:
            amounts = amount_re.findall(cell)
            if amounts:
                values.extend(amounts[:2])  # Take first two amounts
        
        if values:
            row = {
                'label': label,
                'value_2024': parse_finnish_amount(values[0]) if len(values) > 0 else None,
                'value_2023': parse_finnish_amount(values[1]) if len(values) > 1 else None,
            }
            rows.append(row)
    
    return rows


def compare_table_to_golden(parsed_rows: list[dict], golden_rows: list[dict], tolerance: float = 1.0) -> list[dict]:
    """
    Compare parsed table rows to golden truth.
    
    Returns:
        List of discrepancies found
    """
    discrepancies = []
    
    # Build lookup dicts
    parsed_dict = {r['label']: r for r in parsed_rows}
    golden_dict = {r['label']: r for r in golden_rows}
    
    # Check all golden rows
    for golden_row in golden_rows:
        label = golden_row['label']
        
        if label not in parsed_dict:
            discrepancies.append({
                'label': label,
                'issue': 'missing',
                'expected': golden_row,
                'actual': None,
            })
            continue
        
        parsed_row = parsed_dict[label]
        
        # Compare 2024
        if golden_row.get('value_2024') is not None:
            if parsed_row.get('value_2024') is None:
                discrepancies.append({
                    'label': label,
                    'field': '2024',
                    'issue': 'missing_value',
                    'expected': golden_row['value_2024'],
                    'actual': None,
                })
            else:
                diff = abs(golden_row['value_2024'] - parsed_row['value_2024'])
                if diff > tolerance:
                    discrepancies.append({
                        'label': label,
                        'field': '2024',
                        'issue': 'value_mismatch',
                        'expected': golden_row['value_2024'],
                        'actual': parsed_row['value_2024'],
                        'difference': diff,
                    })
        
        # Compare 2023
        if golden_row.get('value_2023') is not None:
            if parsed_row.get('value_2023') is None:
                discrepancies.append({
                    'label': label,
                    'field': '2023',
                    'issue': 'missing_value',
                    'expected': golden_row['value_2023'],
                    'actual': None,
                })
            else:
                diff = abs(golden_row['value_2023'] - parsed_row['value_2023'])
                if diff > tolerance:
                    discrepancies.append({
                        'label': label,
                        'field': '2023',
                        'issue': 'value_mismatch',
                        'expected': golden_row['value_2023'],
                        'actual': parsed_row['value_2023'],
                        'difference': diff,
                    })
    
    return discrepancies


@pytest.fixture
def parsed_markdown():
    """Load parsed markdown from output file."""
    md_path = Path(__file__).parent.parent / "out" / "lapua_2024" / "Lapua-Tilinpaatos-2024.md"
    
    if not md_path.exists():
        pytest.skip(f"Parsed markdown not found: {md_path}")
    
    return md_path.read_text(encoding="utf-8")


def test_vesihuolto_tase_golden_truth(parsed_markdown):
    """Test Vesihuoltolaitoksen tase against golden truth."""
    pdf_name = "Lapua-Tilinpaatos-2024"
    table_name = "Vesihuoltolaitoksen tase"
    
    if pdf_name not in GOLDEN_TRUTH:
        pytest.skip(f"No golden truth for {pdf_name}")
    
    if table_name not in GOLDEN_TRUTH[pdf_name]:
        pytest.skip(f"No golden truth for {table_name}")
    
    golden_rows = GOLDEN_TRUTH[pdf_name][table_name]["rows"]
    parsed_rows = extract_table_from_markdown(parsed_markdown, table_name)
    
    assert len(parsed_rows) > 0, "No rows extracted from parsed markdown"
    
    discrepancies = compare_table_to_golden(parsed_rows, golden_rows, tolerance=1.0)
    
    if discrepancies:
        # Format error message
        error_msg = f"\nFound {len(discrepancies)} discrepancies in {table_name}:\n"
        for disc in discrepancies:
            error_msg += f"  - {disc['label']} ({disc.get('field', 'all')}): "
            if disc['issue'] == 'missing':
                error_msg += f"Missing row (expected: {disc['expected']})\n"
            elif disc['issue'] == 'missing_value':
                error_msg += f"Missing value (expected: {disc['expected']})\n"
            elif disc['issue'] == 'value_mismatch':
                error_msg += f"Expected {disc['expected']:.2f}, got {disc['actual']:.2f}, diff: {disc['difference']:.2f}\n"
        
        pytest.fail(error_msg)


def test_balance_sheet_equations(parsed_markdown):
    """Test that balance sheet equations hold."""
    from src.validate_financials import validate_balance_sheet_equations
    
    results = validate_balance_sheet_equations(parsed_markdown)
    
    errors = [r for r in results if r.type == 'error']
    
    if errors:
        error_msg = f"\nFound {len(errors)} balance sheet equation errors:\n"
        for err in errors:
            error_msg += f"  - {err.equation}: Expected {err.expected:,.2f}, Actual {err.actual:,.2f}, Diff: {err.difference:,.2f}\n"
        
        pytest.fail(error_msg)


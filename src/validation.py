"""Cross-validation and quality checks for parsed tables.

Compares results from multiple parsers and flags discrepancies.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

# Finnish amount regex
AMOUNT_RE = re.compile(r'-?\d{1,3}(?:\s?\d{3})*,\d{2}')


def parse_finnish_amount(text: str) -> Optional[float]:
    """Convert Finnish format number to float."""
    if not text:
        return None
    try:
        clean = text.strip().replace(' ', '').replace(',', '.')
        return float(clean)
    except ValueError:
        return None


def extract_table_values(markdown_text: str, table_label: str) -> List[Dict[str, Optional[float]]]:
    """
    Extract numeric values from a specific table in markdown.
    
    Args:
        markdown_text: Full markdown text
        table_label: Label to identify table (e.g., "Vesihuoltolaitoksen tase")
        
    Returns:
        List of dicts with row labels and 2024/2023 values
    """
    # Find table section
    pattern = rf'(?i){re.escape(table_label)}'
    match = re.search(pattern, markdown_text)
    
    if not match:
        return []
    
    # Extract table (next 100 lines or until next ## header)
    start = match.start()
    end_match = re.search(r'\n##\s+', markdown_text[start + 100:])
    if end_match:
        end = start + 100 + end_match.start()
    else:
        end = min(start + 2000, len(markdown_text))
    
    table_section = markdown_text[start:end]
    
    # Parse table rows
    rows = []
    lines = table_section.split('\n')
    
    for line in lines:
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
            amounts = AMOUNT_RE.findall(cell)
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


def compare_parsers(
    parser1_text: str,
    parser2_text: str,
    parser1_name: str = "Parser 1",
    parser2_name: str = "Parser 2",
    table_labels: Optional[List[str]] = None,
) -> Dict[str, List[Dict]]:
    """
    Compare results from two parsers and flag discrepancies.
    
    Args:
        parser1_text: Markdown from first parser
        parser2_text: Markdown from second parser
        parser1_name: Name of first parser
        parser2_name: Name of second parser
        table_labels: List of table labels to compare (None = all tables)
        
    Returns:
        Dict with discrepancies found
    """
    if table_labels is None:
        table_labels = [
            "Vesihuoltolaitoksen tase",
            "TALOUSTIEDOT",
            "Rahoituslaskelma",
            "Tuloslaskelma",
        ]
    
    discrepancies = {}
    
    for label in table_labels:
        rows1 = extract_table_values(parser1_text, label)
        rows2 = extract_table_values(parser2_text, label)
        
        if not rows1 or not rows2:
            continue
        
        # Match rows by label
        rows1_dict = {r['label']: r for r in rows1}
        rows2_dict = {r['label']: r for r in rows2}
        
        # Find common rows
        common_labels = set(rows1_dict.keys()) & set(rows2_dict.keys())
        
        diffs = []
        for lbl in common_labels:
            r1 = rows1_dict[lbl]
            r2 = rows2_dict[lbl]
            
            # Compare 2024
            if r1['value_2024'] is not None and r2['value_2024'] is not None:
                diff_2024 = abs(r1['value_2024'] - r2['value_2024'])
                if diff_2024 > 1.0:  # More than 1 euro difference
                    diffs.append({
                        'label': lbl,
                        'field': '2024',
                        f'{parser1_name}': r1['value_2024'],
                        f'{parser2_name}': r2['value_2024'],
                        'difference': diff_2024,
                    })
            
            # Compare 2023
            if r1['value_2023'] is not None and r2['value_2023'] is not None:
                diff_2023 = abs(r1['value_2023'] - r2['value_2023'])
                if diff_2023 > 1.0:
                    diffs.append({
                        'label': lbl,
                        'field': '2023',
                        f'{parser1_name}': r1['value_2023'],
                        f'{parser2_name}': r2['value_2023'],
                        'difference': diff_2023,
                    })
        
        if diffs:
            discrepancies[label] = diffs
    
    return discrepancies


def validate_accounting_equations(markdown_text: str) -> List[Dict]:
    """
    Validate accounting equations in parsed tables.
    
    Checks:
    - VAIHTUVAT VASTAAVAT = Myyntisaamiset + Muut saamiset
    - VASTATTAVAA = OMA PÄÄOMA + VIERAS PÄÄOMA
    
    Returns:
        List of validation results (errors/warnings)
    """
    rows = extract_table_values(markdown_text, "Vesihuoltolaitoksen tase")
    
    if not rows:
        return []
    
    # Build row dict
    rows_dict = {r['label']: r for r in rows}
    
    validations = []
    
    # Check: VAIHTUVAT VASTAAVAT = Myyntisaamiset + Muut saamiset
    if all(k in rows_dict for k in ['VAIHTUVAT VASTAAVAT', 'Myyntisaamiset', 'Muut saamiset']):
        total = rows_dict['VAIHTUVAT VASTAAVAT']
        myynti = rows_dict['Myyntisaamiset']
        muut = rows_dict['Muut saamiset']
        
        for year in ['2024', '2023']:
            total_val = total.get(f'value_{year}')
            myynti_val = myynti.get(f'value_{year}')
            muut_val = muut.get(f'value_{year}')
            
            if all(v is not None for v in [total_val, myynti_val, muut_val]):
                expected_total = myynti_val + muut_val
                diff = abs(total_val - expected_total)
                
                if diff > 1.0:
                    validations.append({
                        'type': 'error',
                        'equation': f'VAIHTUVAT VASTAAVAT = Myyntisaamiset + Muut saamiset ({year})',
                        'expected': expected_total,
                        'actual': total_val,
                        'difference': diff,
                    })
    
    # Check: VASTATTAVAA = OMA PÄÄOMA + VIERAS PÄÄOMA
    if all(k in rows_dict for k in ['VASTATTAVAA', 'OMA PÄÄOMA', 'VIERAS PÄÄOMA']):
        total = rows_dict['VASTATTAVAA']
        oma = rows_dict['OMA PÄÄOMA']
        vieras = rows_dict['VIERAS PÄÄOMA']
        
        for year in ['2024', '2023']:
            total_val = total.get(f'value_{year}')
            oma_val = oma.get(f'value_{year}')
            vieras_val = vieras.get(f'value_{year}')
            
            if all(v is not None for v in [total_val, oma_val, vieras_val]):
                expected_total = oma_val + vieras_val
                diff = abs(total_val - expected_total)
                
                if diff > 1.0:
                    validations.append({
                        'type': 'error',
                        'equation': f'VASTATTAVAA = OMA PÄÄOMA + VIERAS PÄÄOMA ({year})',
                        'expected': expected_total,
                        'actual': total_val,
                        'difference': diff,
                    })
    
    return validations


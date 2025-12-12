"""Financial statement validation using accounting equations.

Validates balance sheet equations and flags discrepancies.
Does NOT auto-correct, only logs warnings/errors for manual review.
"""

import re
from typing import Dict, List, Optional
from dataclasses import dataclass

# Finnish amount regex
AMOUNT_RE = re.compile(r'-?\d{1,3}(?:\s?\d{3})*,\d{2}')


@dataclass
class ValidationResult:
    """Result of a financial validation check."""
    type: str  # 'error', 'warning', 'info'
    equation: str
    expected: float
    actual: float
    difference: float
    context: str = ""  # Additional context (e.g., year, table name)


def parse_finnish_amount(text: str) -> Optional[float]:
    """Convert Finnish format number to float."""
    if not text:
        return None
    try:
        clean = text.strip().replace(' ', '').replace(',', '.')
        return float(clean)
    except ValueError:
        return None


def extract_table_row_values(markdown_text: str, row_label: str) -> Dict[str, Optional[float]]:
    """
    Extract values for a specific row from markdown tables.
    
    Args:
        markdown_text: Full markdown text
        row_label: Label to find (e.g., "VAIHTUVAT VASTAAVAT")
        
    Returns:
        Dict with 'value_2024' and 'value_2023' (or None if not found)
    """
    # Find row in markdown table
    pattern = rf'(?i)\|.*?{re.escape(row_label)}.*?\|'
    match = re.search(pattern, markdown_text)
    
    if not match:
        return {'value_2024': None, 'value_2023': None}
    
    # Extract amounts from the matched line
    line = match.group(0)
    amounts = AMOUNT_RE.findall(line)
    
    result = {
        'value_2024': parse_finnish_amount(amounts[0]) if len(amounts) > 0 else None,
        'value_2023': parse_finnish_amount(amounts[1]) if len(amounts) > 1 else None,
    }
    
    return result


def validate_balance_sheet_equations(markdown_text: str) -> List[ValidationResult]:
    """
    Validate balance sheet accounting equations.
    
    Checks:
    1. VAIHTUVAT VASTAAVAT = Myyntisaamiset + Muut saamiset
    2. VASTATTAVAA = OMA PÄÄOMA + VIERAS PÄÄOMA
    3. VASTAAVAA = PYSYVÄT VASTAAVAT + VAIHTUVAT VASTAAVAT
    4. VASTATTAVAA = OMA PÄÄOMA + VIERAS PÄÄOMA (detailed)
    
    Returns:
        List of validation results (errors/warnings)
    """
    results: List[ValidationResult] = []
    
    # Helper to get row values
    def get_row(label: str) -> Dict[str, Optional[float]]:
        return extract_table_row_values(markdown_text, label)
    
    # Equation 1: VAIHTUVAT VASTAAVAT = Myyntisaamiset + Muut saamiset
    vaihtuvat = get_row("VAIHTUVAT VASTAAVAT")
    myynti = get_row("Myyntisaamiset")
    muut_saamiset = get_row("Muut saamiset")
    
    for year in ['2024', '2023']:
        key = f'value_{year}'
        if all(r.get(key) is not None for r in [vaihtuvat, myynti, muut_saamiset]):
            total = vaihtuvat[key]
            expected = myynti[key] + muut_saamiset[key]
            diff = abs(total - expected)
            
            if diff > 1.0:  # More than 1 euro difference
                results.append(ValidationResult(
                    type='error',
                    equation=f'VAIHTUVAT VASTAAVAT = Myyntisaamiset + Muut saamiset ({year})',
                    expected=expected,
                    actual=total,
                    difference=diff,
                    context=f'Balance sheet - {year}',
                ))
    
    # Equation 2: VASTATTAVAA = OMA PÄÄOMA + VIERAS PÄÄOMA
    vastattavaa = get_row("VASTATTAVAA")
    oma_paaoma = get_row("OMA PÄÄOMA")
    vieras_paaoma = get_row("VIERAS PÄÄOMA")
    
    for year in ['2024', '2023']:
        key = f'value_{year}'
        if all(r.get(key) is not None for r in [vastattavaa, oma_paaoma, vieras_paaoma]):
            total = vastattavaa[key]
            expected = oma_paaoma[key] + vieras_paaoma[key]
            diff = abs(total - expected)
            
            if diff > 1.0:
                results.append(ValidationResult(
                    type='error',
                    equation=f'VASTATTAVAA = OMA PÄÄOMA + VIERAS PÄÄOMA ({year})',
                    expected=expected,
                    actual=total,
                    difference=diff,
                    context=f'Balance sheet - {year}',
                ))
    
    # Equation 3: VASTAAVAA = PYSYVÄT VASTAAVAT + VAIHTUVAT VASTAAVAT
    vastaavaa = get_row("VASTAAVAA")
    pysyvat = get_row("PYSYVÄT VASTAAVAT")
    vaihtuvat_vastaavaa = get_row("VAIHTUVAT VASTAAVAT")
    
    for year in ['2024', '2023']:
        key = f'value_{year}'
        if all(r.get(key) is not None for r in [vastaavaa, pysyvat, vaihtuvat_vastaavaa]):
            total = vastaavaa[key]
            expected = pysyvat[key] + vaihtuvat_vastaavaa[key]
            diff = abs(total - expected)
            
            if diff > 1.0:
                results.append(ValidationResult(
                    type='error',
                    equation=f'VASTAAVAA = PYSYVÄT VASTAAVAT + VAIHTUVAT VASTAAVAT ({year})',
                    expected=expected,
                    actual=total,
                    difference=diff,
                    context=f'Balance sheet - {year}',
                ))
    
    # Equation 4: Detailed OMA PÄÄOMA breakdown
    # OMA PÄÄOMA = Peruspääoma + Edellisten tilikausien yli-/alijäämä + Tilikauden yli-/alijäämä
    oma_paaoma_detailed = get_row("OMA PÄÄOMA")
    peruspaaoma = get_row("Peruspääoma")
    edellisten = get_row("Edellisten tilikausien yli-/alijäämä")
    tilikauden = get_row("Tilikauden yli-/alijäämä")
    
    for year in ['2024', '2023']:
        key = f'value_{year}'
        if all(r.get(key) is not None for r in [oma_paaoma_detailed, peruspaaoma, edellisten, tilikauden]):
            total = oma_paaoma_detailed[key]
            expected = peruspaaoma[key] + edellisten[key] + tilikauden[key]
            diff = abs(total - expected)
            
            if diff > 1.0:
                results.append(ValidationResult(
                    type='warning',  # Warning, as this might be more complex
                    equation=f'OMA PÄÄOMA = Peruspääoma + Edellisten tilikausien yli-/alijäämä + Tilikauden yli-/alijäämä ({year})',
                    expected=expected,
                    actual=total,
                    difference=diff,
                    context=f'Balance sheet - detailed breakdown - {year}',
                ))
    
    return results


def validate_income_statement_equations(markdown_text: str) -> List[ValidationResult]:
    """
    Validate income statement equations.
    
    Checks:
    1. Operating result = Operating income - Operating expenses
    2. Net result = Operating result + Financial result + Extraordinary items
    
    Returns:
        List of validation results
    """
    results: List[ValidationResult] = []
    
    # This is a placeholder - expand based on actual income statement structure
    # For now, return empty list as income statement validation needs
    # specific knowledge of the document structure
    
    return results


def validate_all_financials(markdown_text: str) -> Dict[str, List[ValidationResult]]:
    """
    Run all financial validations.
    
    Returns:
        Dict with 'balance_sheet' and 'income_statement' keys
    """
    return {
        'balance_sheet': validate_balance_sheet_equations(markdown_text),
        'income_statement': validate_income_statement_equations(markdown_text),
    }


def add_validation_comments_to_markdown(markdown_text: str, validations: Dict[str, List[ValidationResult]]) -> str:
    """
    Add HTML comments to markdown for rows with sum errors.
    
    Format: <!-- SUMMA VIRHE: equation, expected, actual, difference -->
    
    Args:
        markdown_text: Original markdown text
        validations: Validation results dict
        
    Returns:
        Markdown text with validation comments added
    """
    import re
    
    # Combine all validation errors
    all_errors = []
    for category_results in validations.values():
        for result in category_results:
            if result.type == 'error':
                all_errors.append(result)
    
    if not all_errors:
        return markdown_text
    
    # Find rows in markdown that match error equations
    lines = markdown_text.split('\n')
    result_lines = []
    
    for line in lines:
        result_lines.append(line)
        
        # Check if this line contains a row label from an error
        for error in all_errors:
            # Extract row label from equation (e.g., "VAIHTUVAT VASTAAVAT" from "VAIHTUVAT VASTAAVAT = ...")
            equation_parts = error.equation.split(' = ')
            if len(equation_parts) > 0:
                row_label = equation_parts[0].split(' (')[0]  # Remove year suffix
                
                # Check if line contains this label
                if row_label.lower() in line.lower() and '|' in line:
                    # Add comment after the line
                    comment = f"<!-- SUMMA VIRHE: {error.equation}, Expected: {error.expected:,.2f}, Actual: {error.actual:,.2f}, Difference: {error.difference:,.2f} -->"
                    result_lines.append(comment)
                    break  # Only add one comment per line
    
    return '\n'.join(result_lines)


def format_validation_report(validations: Dict[str, List[ValidationResult]]) -> str:
    """
    Format validation results as a readable report.
    
    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 70)
    lines.append("FINANCIAL STATEMENT VALIDATION REPORT")
    lines.append("=" * 70)
    lines.append("")
    
    for category, results in validations.items():
        if not results:
            continue
        
        lines.append(f"\n{category.upper().replace('_', ' ')}:")
        lines.append("-" * 70)
        
        errors = [r for r in results if r.type == 'error']
        warnings = [r for r in results if r.type == 'warning']
        infos = [r for r in results if r.type == 'info']
        
        if errors:
            lines.append(f"\n  ERRORS ({len(errors)}):")
            for r in errors:
                lines.append(f"    ✗ {r.equation}")
                lines.append(f"      Expected: {r.expected:,.2f}, Actual: {r.actual:,.2f}, Diff: {r.difference:,.2f}")
                if r.context:
                    lines.append(f"      Context: {r.context}")
        
        if warnings:
            lines.append(f"\n  WARNINGS ({len(warnings)}):")
            for r in warnings:
                lines.append(f"    ⚠ {r.equation}")
                lines.append(f"      Expected: {r.expected:,.2f}, Actual: {r.actual:,.2f}, Diff: {r.difference:,.2f}")
                if r.context:
                    lines.append(f"      Context: {r.context}")
        
        if infos:
            lines.append(f"\n  INFO ({len(infos)}):")
            for r in infos:
                lines.append(f"    ℹ {r.equation}")
    
    lines.append("\n" + "=" * 70)
    
    return "\n".join(lines)


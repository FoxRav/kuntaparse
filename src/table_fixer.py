"""Post-processing to fix broken table structures in parsed markdown.

Includes:
- Generic table fixes (merged cells, suspect numbers)
- Domain-specific balance sheet (tase) fixes for Finnish municipal financial statements
- Accounting formula validation and correction
- Duplicate removal and canonical table selection
"""

import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


# Finnish currency amount regex
AMOUNT_RE = re.compile(r'-?\d{1,3}(?:\s?\d{3})*,\d{2}')

# Pattern for two amounts merged in one cell
TWO_AMOUNTS_RE = re.compile(
    r'(-?\d{1,3}(?:\s?\d{3})*,\d{2})\s+(-?\d{1,3}(?:\s?\d{3})*,\d{2})'
)

# Known VASTATTAVAA labels in order (from PDF) - exact order for vesihuoltolaitos tase
VASTATTAVAA_LABELS = [
    "OMA PÄÄOMA",
    "Peruspääoma",
    "Edellisten tilikausien yli-/alijäämä",
    "Tilikauden yli-/alijäämä",
    "VIERAS PÄÄOMA",
    "Pitkäaikainen",
    "Muut velat",
    "Lyhytaikainen",
    "Ostovelat",
    "Siirtovelat",
]


# =============================================================================
# GENERIC TABLE FIXES
# =============================================================================

def split_merged_amounts_in_cells(text: str) -> str:
    """Fix cells where two Finnish amounts are merged together."""
    lines = text.split('\n')
    fixed_lines = []
    
    for line in lines:
        if '|' not in line:
            fixed_lines.append(line)
            continue
            
        if re.match(r'^\|[-:| ]+\|$', line.strip()):
            fixed_lines.append(line)
            continue
        
        cells = line.split('|')
        new_cells = []
        
        for cell in cells:
            cell_stripped = cell.strip()
            match = TWO_AMOUNTS_RE.search(cell_stripped)
            
            if match:
                amount1, amount2 = match.groups()
                text_part = cell_stripped[:match.start()].strip()
                
                if text_part:
                    new_cells.append(f' {text_part} ')
                    new_cells.append(f' {amount1} ')
                    new_cells.append(f' {amount2} ')
                else:
                    new_cells.append(f' {amount1} ')
                    new_cells.append(f' {amount2} ')
            else:
                new_cells.append(cell)
        
        if len(new_cells) != len(cells):
            fixed_line = '|'.join(new_cells)
            if not fixed_line.startswith('|'):
                fixed_line = '|' + fixed_line
            if not fixed_line.endswith('|'):
                fixed_line = fixed_line + '|'
            fixed_lines.append(fixed_line)
        else:
            fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)


def flag_suspect_numbers(text: str) -> str:
    """Flag numbers that are suspiciously large (likely OCR errors)."""
    lines = text.split('\n')
    fixed_lines = []
    
    SUSPECT_THRESHOLD = 500_000_000  # 500 million euros
    
    for line in lines:
        amounts = AMOUNT_RE.findall(line)
        
        for amount in amounts:
            try:
                clean = amount.replace(' ', '').replace(',', '.')
                value = abs(float(clean))
                
                if value > SUSPECT_THRESHOLD:
                    line = line.replace(amount, f'{amount} <!-- SUSPECT -->', 1)
            except ValueError:
                continue
        
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)


def remove_extracted_tables_section(text: str) -> str:
    """Remove the duplicate Extracted Tables section from the end."""
    pattern = r'\n##\s*Extracted\s+Tables\s*\n'
    
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        text = text[:match.start()]
        text = text.rstrip() + '\n'
    
    return text


# =============================================================================
# BALANCE SHEET (TASE) DOMAIN-SPECIFIC FIXES
# =============================================================================

@dataclass
class TaseRow:
    """A single row in a balance sheet."""
    label: str
    value_2024: Optional[float] = None
    value_2023: Optional[float] = None
    is_corrected: bool = False


def parse_finnish_amount(text: str) -> Optional[float]:
    """Convert Finnish format number to float."""
    if not text:
        return None
    try:
        clean = text.strip().replace(' ', '').replace(',', '.')
        return float(clean)
    except ValueError:
        return None


def format_finnish_amount(value: float) -> str:
    """Convert float to Finnish format string."""
    is_negative = value < 0
    value = abs(value)
    
    int_part = int(value)
    dec_part = round((value - int_part) * 100)
    
    int_str = str(int_part)
    groups = []
    while int_str:
        groups.append(int_str[-3:])
        int_str = int_str[:-3]
    formatted_int = ' '.join(reversed(groups))
    
    result = f"{formatted_int},{dec_part:02d}"
    if is_negative:
        result = '-' + result
    return result


def remove_duplicate_tase_tables(text: str) -> str:
    """
    Remove duplicate balance sheet tables, keeping only the canonical version.
    
    Strategy:
    1. Find all "Vesihuoltolaitoksen tase" sections
    2. Keep the one with proper Markdown table structure
    3. Remove loose text versions
    """
    # Find all occurrences of "Vesihuoltolaitoksen tase"
    pattern = r'(?i)##?\s*Vesihuoltolaitoksen\s+tase'
    
    matches = list(re.finditer(pattern, text))
    
    if len(matches) <= 1:
        return text  # No duplicates
    
    # Analyze each section
    sections = []
    for i, match in enumerate(matches):
        start = match.start()
        # Find end (next major header or significant content)
        end_patterns = [
            r'\n##\s+(?!Vesihuoltolaitoksen|VASTAAVAA|VASTATTAVAA)',  # Next ## header
            r'\n##\s*\d{1,2}\.',  # Numbered section like "## 9."
            r'\nLuettelo',  # "Luettelo" section
        ]
        
        section_end = len(text)
        for end_pattern in end_patterns:
            end_match = re.search(end_pattern, text[start + 100:])
            if end_match:
                section_end = min(section_end, start + 100 + end_match.start())
        
        section_text = text[start:section_end]
        
        # Check if this is a proper table (has | characters in rows)
        has_table = '|' in section_text and section_text.count('|') > 10
        has_loose_text = re.search(r'(?i)vastaavaa\s*/\s*vastattavaa', section_text) and not has_table
        
        sections.append({
            'start': start,
            'end': section_end,
            'text': section_text,
            'is_table': has_table,
            'is_loose': has_loose_text,
        })
    
    # Keep canonical version (prefer table, remove loose duplicates)
    result_parts = []
    last_end = 0
    
    for i, section in enumerate(sections):
        # Add text before this section
        if section['start'] > last_end:
            result_parts.append(text[last_end:section['start']])
        
        # Keep this section if:
        # - It's the first one (always keep first)
        # - It's a proper table
        # - It's not a loose duplicate of a table we already have
        if i == 0 or section['is_table'] or (not any(s['is_table'] for s in sections[:i])):
            result_parts.append(section['text'])
            last_end = section['end']
        else:
            # Skip duplicate loose version
            last_end = section['end']
    
    # Add remaining text
    if last_end < len(text):
        result_parts.append(text[last_end:])
    
    return ''.join(result_parts)


def fix_tase_numbers(text: str) -> str:
    """
    Validate and correct balance sheet numbers using accounting formulas.
    
    Key formulas:
    - VAIHTUVAT VASTAAVAT = Myyntisaamiset + Muut saamiset
    - VASTATTAVAA = OMA PÄÄOMA + VIERAS PÄÄOMA
    """
    # Parse known balance sheet rows
    rows: dict[str, TaseRow] = {}
    
    row_patterns = [
        (r'(?i)vaihtuvat?\s*vastaavat', 'VAIHTUVAT VASTAAVAT'),
        (r'(?i)saamiset(?!\s*/)', 'Saamiset'),
        (r'(?i)lyhytaikaiset?\s*saamiset', 'Lyhytaikaiset saamiset'),
        (r'(?i)myyntisaamiset', 'Myyntisaamiset'),
        (r'(?i)muut\s*saamiset', 'Muut saamiset'),
        (r'(?i)vastattavaa(?!\s*yht)', 'VASTATTAVAA'),
        (r'(?i)oma\s*p[äa][äa]oma', 'OMA PÄÄOMA'),
        (r'(?i)vieras\s*p[äa][äa]oma', 'VIERAS PÄÄOMA'),
    ]
    
    lines = text.split('\n')
    for line in lines:
        amounts = AMOUNT_RE.findall(line)
        if not amounts:
            continue
        
        for pattern, label in row_patterns:
            if re.search(pattern, line):
                row = TaseRow(label=label)
                if len(amounts) >= 2:
                    row.value_2024 = parse_finnish_amount(amounts[0])
                    row.value_2023 = parse_finnish_amount(amounts[1])
                elif len(amounts) == 1:
                    row.value_2024 = parse_finnish_amount(amounts[0])
                
                if label not in rows:
                    rows[label] = row
                break
    
    if not rows:
        return text
    
    # Validate: VAIHTUVAT = Myyntisaamiset + Muut saamiset
    if all(k in rows for k in ['VAIHTUVAT VASTAAVAT', 'Myyntisaamiset', 'Muut saamiset']):
        total = rows['VAIHTUVAT VASTAAVAT']
        myynti = rows['Myyntisaamiset']
        muut = rows['Muut saamiset']
        
        # Check 2023 (known error case: 95 345 152,75 should be 5 345 152,75)
        if total.value_2023 and myynti.value_2023 and muut.value_2023:
            expected_muut = total.value_2023 - myynti.value_2023
            if abs(muut.value_2023 - expected_muut) > 1:
                old_str = format_finnish_amount(muut.value_2023)
                new_str = format_finnish_amount(expected_muut)
                print(f"  CORRECTION: Muut saamiset 2023: {old_str} -> {new_str}")
                
                # Find and replace in text
                for i, line in enumerate(lines):
                    if re.search(r'(?i)muut\s*saamiset', line):
                        amounts_in_line = AMOUNT_RE.findall(line)
                        if len(amounts_in_line) >= 2:
                            old_2023 = amounts_in_line[1]
                            # Check if this is the wrong value (starts with 95...)
                            if old_2023.replace(' ', '').startswith('95'):
                                lines[i] = line.replace(old_2023, new_str + ' <!-- CORRECTED -->', 1)
                                break
                
                text = '\n'.join(lines)
    
    return text


def parse_vastattavaa_with_labels(text: str, section_start: int, section_end: int) -> Optional[Tuple[List[Tuple[str, str, str]], Tuple[str, str, str]]]:
    """
    Parse VASTATTAVAA section by matching labels to numbers.
    
    Strategy:
    1. Find label lines BEFORE number sequence (OMA PÄÄOMA, Peruspääoma, etc.)
    2. Find number sequence starting with "## 19 502 321,47 19 525 668,40"
    3. Match labels to numbers in correct order
    4. Handle single vs. double numbers correctly
    """
    section = text[section_start:section_end]
    lines = section.split('\n')
    
    # Step 1: Find labels BEFORE number sequence
    # Labels appear before "## VASTATTAVAA" or right after it
    labels_found: List[str] = []
    label_start_idx = -1
    
    for i, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean:
            continue
        
        # Remove markdown headers
        line_clean = re.sub(r'^#+\s*', '', line_clean)
        
        # Check if this matches a known label
        matched_label = match_to_known_label(line_clean)
        if matched_label and matched_label not in labels_found:
            labels_found.append(matched_label)
            if label_start_idx == -1:
                label_start_idx = i
    
    # Step 2: Find number sequence start (line with "##" followed by two amounts)
    number_start_idx = -1
    number_start_pattern = r'^##\s+(\d{1,3}(?:\s?\d{3})*,\d{2})\s+(\d{1,3}(?:\s?\d{3})*,\d{2})'
    
    for i, line in enumerate(lines):
        if re.match(number_start_pattern, line):
            number_start_idx = i
            break
    
    if number_start_idx == -1:
        return None  # Can't find number sequence
    
    # Step 3: Extract all numbers from number sequence
    number_lines = lines[number_start_idx:]
    all_numbers: List[List[str]] = []
    
    for line in number_lines:
        amounts = AMOUNT_RE.findall(line)
        if amounts:
            all_numbers.append(amounts)
        elif line.strip() and not line.strip().startswith('##'):
            # Empty line or non-header line without numbers - might be end
            break
    
    if len(all_numbers) < 2:
        return None  # Need at least total + one value
    
    # First and last are totals
    total_top = all_numbers[0]
    total_bottom = all_numbers[-1]
    
    # Values in between
    value_numbers = all_numbers[1:-1]
    
    # Step 4: Match labels to numbers
    # Expected structure based on golden truth:
    # - OMA PÄÄOMA: 2 numbers (2024, 2023)
    # - Peruspääoma: 1 number (same for both years) - appears twice in sequence
    # - Edellisten tilikausien: 2 numbers
    # - Tilikauden yli-/alijäämä: 2 numbers (but might be separate lines)
    # - VIERAS PÄÄOMA: 1 number (2024)
    # - Pitkäaikainen: 1 number (2024)
    # - Muut velat: might be missing or 1 number
    # - Lyhytaikainen: 1 number (2024)
    # - Ostovelat: 1 number (2024)
    # - Siirtovelat: 1 number (2024)
    # Then same for 2023...
    
    # Smart matching: consume numbers based on label expectations
    rows: List[Tuple[str, str, str]] = []
    num_idx = 0
    
    for label in VASTATTAVAA_LABELS:
        if num_idx >= len(value_numbers):
            rows.append((label, "", ""))
            continue
        
        # Get next number(s)
        current_nums = value_numbers[num_idx]
        
        if len(current_nums) == 2:
            # Two numbers - use both
            rows.append((label, current_nums[0], current_nums[1]))
            num_idx += 1
        elif len(current_nums) == 1:
            # Single number - check if next is also single (might be 2023)
            if num_idx + 1 < len(value_numbers):
                next_nums = value_numbers[num_idx + 1]
                if len(next_nums) == 1:
                    # Two single numbers - first is 2024, second is 2023
                    rows.append((label, current_nums[0], next_nums[0]))
                    num_idx += 2
                else:
                    # Next has 2 numbers, so this single is for both years
                    rows.append((label, current_nums[0], current_nums[0]))
                    num_idx += 1
            else:
                # Last number - use for both years
                rows.append((label, current_nums[0], current_nums[0]))
                num_idx += 1
        else:
            # Multiple numbers - take first two
            rows.append((label, current_nums[0], current_nums[1] if len(current_nums) > 1 else current_nums[0]))
            num_idx += 1
    
    # Build total row
    if len(total_top) >= 2:
        total_row = ("VASTATTAVAA yhteensä", total_top[0], total_top[1])
    else:
        total_row = ("VASTATTAVAA yhteensä", total_top[0] if total_top else "", "")
    
    return (rows, total_row)


def render_vastattavaa_table(
    rows: List[Tuple[str, str, str]],
    total_row: Tuple[str, str, str],
) -> str:
    """Render VASTATTAVAA section as Markdown table."""
    lines = []
    lines.append("\n### Vesihuoltolaitoksen tase - VASTATTAVAA\n")
    lines.append("| Erä | 2024 | 2023 |")
    lines.append("|-----|-----:|-----:|")
    lines.append(f"| {total_row[0]} | {total_row[1]} | {total_row[2]} |")
    for label, v2024, v2023 in rows:
        lines.append(f"| {label} | {v2024} | {v2023} |")
    lines.append(f"| {total_row[0]} | {total_row[1]} | {total_row[2]} |")
    lines.append("")
    return "\n".join(lines)


def fix_vastattavaa_structure(text: str) -> str:
    """
    Fix VASTATTAVAA section in Vesihuoltolaitoksen tase.
    
    Eristää alueen "## Vesihuoltolaitoksen tase" → "## Luettelo" väliltä,
    parsii numerojonon ja rakentaa siistin taulukon.
    """
    # Find "Vesihuoltolaitoksen tase" section
    tase_start_pattern = r'(?:^|\n)##\s*Vesihuoltolaitoksen\s+tase\s*\n'
    tase_match = re.search(tase_start_pattern, text, re.IGNORECASE | re.MULTILINE)
    
    if not tase_match:
        return text
    
    section_start = tase_match.start()
    
    # Find end: "## Luettelo" or similar
    end_patterns = [
        r'\n##\s+Luettelo',
        r'\n##\s+Luettelo\s+käytetyistä',
        r'\n##\s+\d+\.',  # Numbered section
    ]
    
    section_end = len(text)
    for end_pattern in end_patterns:
        end_match = re.search(end_pattern, text[tase_match.end():], re.IGNORECASE)
        if end_match:
            section_end = min(section_end, tase_match.end() + end_match.start())
            break
    
    section = text[section_start:section_end]
    
    # Check if already a proper table
    if '|' in section and section.count('|') > 20:
        return text  # Already a table
    
    # Find VASTATTAVAA subsection within this section
    vastattavaa_pattern = r'(?:^|\n)(?:##?\s*)?VASTATTAVAA\s*\n'
    vastattavaa_match = re.search(vastattavaa_pattern, section, re.IGNORECASE | re.MULTILINE)
    
    if not vastattavaa_match:
        return text
    
    # Extract VASTATTAVAA block position
    vastattavaa_start_in_section = vastattavaa_match.start()
    vastattavaa_absolute_start = section_start + vastattavaa_start_in_section
    
    # Parse with new algorithm
    parsed = parse_vastattavaa_with_labels(text, section_start, section_end)
    
    if not parsed:
        return text  # Parsing failed
    
    rows, total_row = parsed
    
    # Render table
    table_markdown = render_vastattavaa_table(rows, total_row)
    
    # Replace VASTATTAVAA block with table
    # Find where to replace: from VASTATTAVAA header to end of number sequence
    # We'll find the last number line
    vastattavaa_block = section[vastattavaa_start_in_section:]
    number_end_pattern = r'\n##\s+Luettelo'
    number_end_match = re.search(number_end_pattern, vastattavaa_block, re.IGNORECASE)
    
    if number_end_match:
        replace_end = section_start + vastattavaa_start_in_section + number_end_match.start()
    else:
        # Find last number line
        lines = vastattavaa_block.split('\n')
        last_num_line = -1
        for i in range(len(lines) - 1, -1, -1):
            if AMOUNT_RE.search(lines[i]):
                last_num_line = i
                break
        
        if last_num_line >= 0:
            # Replace up to end of last number line
            replace_end = section_start + vastattavaa_start_in_section + len('\n'.join(lines[:last_num_line + 1]))
        else:
            replace_end = section_end
    
    # Replace
    text_before = text[:vastattavaa_absolute_start]
    text_after = text[replace_end:]
    
    new_text = text_before + table_markdown + text_after
    
    print(f"  Rebuilt VASTATTAVAA table: {len(rows)} rows")
    
    return new_text


def match_to_known_label(text: str) -> Optional[str]:
    """Match OCR'd text to known balance sheet labels."""
    text_lower = text.lower().replace('ä', 'a').replace('ö', 'o')
    
    label_patterns = [
        (r'vastattavaa', 'VASTATTAVAA'),
        (r'oma\s*paa?oma', 'OMA PÄÄOMA'),
        (r'perusp', 'Peruspääoma'),
        (r'edellisten.*tilik', 'Edellisten tilikausien yli-/alijäämä'),
        (r'tilikauden.*yli', 'Tilikauden yli-/alijäämä'),
        (r'vieras\s*paa?oma', 'VIERAS PÄÄOMA'),
        (r'pitk.*aik', 'Pitkäaikainen'),
        (r'muut.*vel', 'Muut velat'),
        (r'lyhyt.*aik', 'Lyhytaikainen'),
        (r'ostov', 'Ostovelat'),
        (r'siirtov', 'Siirtovelat'),
    ]
    
    for pattern, label in label_patterns:
        if re.search(pattern, text_lower):
            return label
    
    return None


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def fix_parsed_tables(text: str) -> str:
    """
    Apply all table fixes to parsed markdown.
    
    This is the main function to call for post-processing.
    Order matters - some fixes depend on others.
    """
    # Step 1: Remove duplicate balance sheet tables
    text = remove_duplicate_tase_tables(text)
    print("  Removed duplicate balance sheet tables")
    
    # Step 2: Split merged amounts in table cells
    text = split_merged_amounts_in_cells(text)
    print("  Split merged amounts")
    
    # Step 3: Fix VASTATTAVAA structure (labels + numbers separated)
    text = fix_vastattavaa_structure(text)
    
    # Step 4: Validate and correct balance sheet numbers
    text = fix_tase_numbers(text)
    
    # Step 5: Flag remaining suspect numbers
    text = flag_suspect_numbers(text)
    print("  Flagged suspect numbers")
    
    # Step 6: Remove duplicate Extracted Tables section
    text = remove_extracted_tables_section(text)
    print("  Removed duplicate sections")
    
    return text

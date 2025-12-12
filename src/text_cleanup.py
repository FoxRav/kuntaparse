"""Post-processing utilities for fixing OCR/parsing errors."""

import re

# Known OCR errors and their corrections
OCR_REPLACEMENTS = {
    # Common Finnish financial terms
    r'Likeylijaama': 'Liikeylijäämä',
    r'Muutsaamiset': 'Muut saamiset',
    r'Kayttoomaisuus': 'Käyttöomaisuus',
    r'Kayttotalous': 'Käyttötalous',
    r'Peruspaaoma': 'Peruspääoma',
    r'OMAPAAOMA': 'OMA PÄÄOMA',
    r'VIERASPAAOMA': 'VIERAS PÄÄOMA',
    r'Edellistentilikausien': 'Edellisten tilikausien',
    r'Tilikaudenyli': 'Tilikauden yli',
    r'yli-?/?alij[äa]m[äa]': 'yli-/alijäämä',
    r'Muutvelat': 'Muut velat',
    r'Pitkaaikainen': 'Pitkäaikainen',
    r'Lyhytaikainen': 'Lyhytaikainen',
    r'Kiinteatrakenteet': 'Kiinteät rakenteet',
    r'Koneetjakalusto': 'Koneet ja kalusto',
    r'Rahatjapankkisaamiset': 'Rahat ja pankkisaamiset',
    r'Siirtosaamiset': 'Siirtosaamiset',
    r'Siirtovelat': 'Siirtovelat',
    r'Ostovelat': 'Ostovelat',
    r'Myyntisaamiset': 'Myyntisaamiset',
    r'Aineellisethyodykkeet': 'Aineelliset hyödykkeet',
    r'Suunnitelmanmukaisetpoistot': 'Suunnitelman mukaiset poistot',
    r'Liketoiminnan': 'Liiketoiminnan',
    r'Lyhytaikaistensaamistenmuutokset': 'Lyhytaikaisten saamisten muutokset',
    r'Korottomienpitkä-jalyhytaikaistenvelkojenmuutos': 'Korottomien pitkä- ja lyhytaikaisten velkojen muutos',
}


def fix_merged_words(text: str) -> str:
    """
    Fix common Finnish word merging issues from OCR/parsing.
    
    Adds spaces before uppercase letters that follow lowercase letters,
    which is a common OCR error pattern.
    """
    # Pattern: lowercase letter followed by uppercase letter (likely merged words)
    text = re.sub(r'([a-zäöå])([A-ZÄÖÅ])', r'\1 \2', text)
    
    return text


def fix_ocr_replacements(text: str) -> str:
    """
    Fix known OCR errors using replacement dictionary.
    
    Args:
        text: Raw parsed text with potential OCR errors
        
    Returns:
        Text with OCR errors corrected
    """
    for pattern, replacement in OCR_REPLACEMENTS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    return text


def fix_number_spacing(text: str) -> str:
    """
    Fix incorrect number spacing in Finnish format.
    
    Finnish numbers use space as thousand separator: 1 234 567,89
    OCR sometimes loses spaces: 1234567,89 or adds wrong: 1234 567,89
    """
    def format_finnish_number(match: re.Match[str]) -> str:
        num_str = match.group(0)
        # Remove existing spaces
        num_str = num_str.replace(' ', '')
        
        # Split integer and decimal parts
        if ',' in num_str:
            integer_part, decimal_part = num_str.split(',', 1)
        else:
            integer_part = num_str
            decimal_part = None
        
        # Add thousand separators to integer part
        formatted = ''
        for i, digit in enumerate(reversed(integer_part)):
            if i > 0 and i % 3 == 0:
                formatted = ' ' + formatted
            formatted = digit + formatted
        
        if decimal_part:
            return f"{formatted},{decimal_part}"
        return formatted
    
    # Match numbers with at least 4 digits (with or without spaces/decimals)
    # Pattern matches: 1234, 1234,56, 1 234, 1234 567, etc.
    pattern = r'\b\d[\d ]{3,}(?:,\d{2})?\b'
    
    return re.sub(pattern, format_finnish_number, text)


def remove_duplicate_sections(text: str) -> str:
    """
    Remove obvious duplicate sections (same paragraph appearing twice).
    """
    lines = text.split('\n')
    seen_paragraphs: set[str] = set()
    result_lines: list[str] = []
    
    current_paragraph: list[str] = []
    
    for line in lines:
        stripped = line.strip()
        
        # Empty line = end of paragraph
        if not stripped:
            if current_paragraph:
                paragraph_text = '\n'.join(current_paragraph)
                # Only add if not seen before (and long enough to be meaningful)
                if len(paragraph_text) < 100 or paragraph_text not in seen_paragraphs:
                    result_lines.extend(current_paragraph)
                    seen_paragraphs.add(paragraph_text)
                current_paragraph = []
            result_lines.append(line)
        else:
            current_paragraph.append(line)
    
    # Don't forget last paragraph
    if current_paragraph:
        paragraph_text = '\n'.join(current_paragraph)
        if len(paragraph_text) < 100 or paragraph_text not in seen_paragraphs:
            result_lines.extend(current_paragraph)
    
    return '\n'.join(result_lines)


def cleanup_parsed_text(text: str) -> str:
    """
    Apply all text cleanup fixes.
    
    Args:
        text: Raw parsed text
        
    Returns:
        Cleaned text
    """
    # Step 1: Fix known OCR replacements first
    text = fix_ocr_replacements(text)
    
    # Step 2: Fix merged words
    text = fix_merged_words(text)
    
    # Step 3: Fix number spacing
    text = fix_number_spacing(text)
    
    # Step 4: Remove duplicates
    text = remove_duplicate_sections(text)
    
    return text

"""Configuration for PDF parser."""

from pathlib import Path

# Default output directory
DEFAULT_OUT_DIR: Path = Path("out")

# OCR language hint for Finnish documents
DEFAULT_OCR_LANG: str = "fin"

# Subdirectory for extracted images
IMAGE_SUBDIR: str = "images"

# Minimum markdown length threshold for fallback trigger
MIN_MD_LENGTH_THRESHOLD: int = 2000

# GPU/CPU settings
NUM_THREADS: int = 8

# Table processing settings
TABLE_ACCURATE_MODE: bool = True
TABLE_CELL_MATCHING: bool = False  # Disable to prevent column merging

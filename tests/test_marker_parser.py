"""Tests for Marker parser."""

from pathlib import Path

import pytest

from src.marker_parser import parse_with_marker


TEST_PDF = Path("data/Lapua-Tilinpaatos-2024.pdf")
TEST_OUT = Path("out/test_marker")


def test_marker_file_not_found() -> None:
    """Test that FileNotFoundError is raised for missing PDF."""
    with pytest.raises(FileNotFoundError):
        parse_with_marker(Path("nonexistent.pdf"), TEST_OUT)


@pytest.mark.skipif(not TEST_PDF.exists(), reason="Test PDF not available")
def test_marker_creates_output_dir() -> None:
    """Test that output directory is created even if Marker fails."""
    # This may return None if Marker isn't installed
    parse_with_marker(TEST_PDF, TEST_OUT)
    assert TEST_OUT.exists()


"""Tests for Docling parser."""

from pathlib import Path

import pytest

from src.docling_parser import parse_with_docling


TEST_PDF = Path("data/Lapua-Tilinpaatos-2024.pdf")
TEST_OUT = Path("out/test_docling")


@pytest.fixture(autouse=True)
def cleanup() -> None:
    """Clean up test output before and after tests."""
    # Setup: nothing needed
    yield
    # Teardown: could clean up test files here if needed


def test_docling_file_not_found() -> None:
    """Test that FileNotFoundError is raised for missing PDF."""
    with pytest.raises(FileNotFoundError):
        parse_with_docling(Path("nonexistent.pdf"), TEST_OUT)


@pytest.mark.skipif(not TEST_PDF.exists(), reason="Test PDF not available")
def test_docling_basic() -> None:
    """Test basic Docling parsing produces markdown output."""
    md_text, images = parse_with_docling(TEST_PDF, TEST_OUT)

    # Should produce substantial markdown output
    assert len(md_text) > 1000, f"Markdown too short: {len(md_text)} chars"

    # Images list should be a list (may be empty)
    assert isinstance(images, list)

    # Output directory should exist
    assert TEST_OUT.exists()


@pytest.mark.skipif(not TEST_PDF.exists(), reason="Test PDF not available")
def test_docling_creates_image_dir() -> None:
    """Test that image subdirectory is created."""
    parse_with_docling(TEST_PDF, TEST_OUT)
    img_dir = TEST_OUT / "images"
    assert img_dir.exists()


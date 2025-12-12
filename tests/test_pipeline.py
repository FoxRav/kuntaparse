"""Tests for PDF processing pipeline."""

from pathlib import Path

import pytest

from src.pipeline import process_pdf


TEST_PDF = Path("data/Lapua-Tilinpaatos-2024.pdf")
TEST_OUT = Path("out/test_pipeline")


def test_pipeline_file_not_found() -> None:
    """Test that FileNotFoundError is raised for missing PDF."""
    with pytest.raises(FileNotFoundError):
        process_pdf(Path("nonexistent.pdf"), TEST_OUT)


@pytest.mark.skipif(not TEST_PDF.exists(), reason="Test PDF not available")
def test_pipeline_runs() -> None:
    """Test that pipeline completes and produces output."""
    md_path = process_pdf(TEST_PDF, out_dir=TEST_OUT, use_marker_fallback=False)

    assert md_path.exists(), "Markdown file should exist"
    content = md_path.read_text(encoding="utf-8")
    assert len(content) > 0, "Markdown file should not be empty"


@pytest.mark.skipif(not TEST_PDF.exists(), reason="Test PDF not available")
def test_pipeline_output_naming() -> None:
    """Test that output file is named correctly."""
    md_path = process_pdf(TEST_PDF, out_dir=TEST_OUT, use_marker_fallback=False)

    expected_name = f"{TEST_PDF.stem}.md"
    assert md_path.name == expected_name


@pytest.mark.skipif(not TEST_PDF.exists(), reason="Test PDF not available")
def test_pipeline_with_fallback_flag() -> None:
    """Test that pipeline runs with marker fallback enabled."""
    # This tests that the fallback logic doesn't crash
    # even if Marker isn't installed
    md_path = process_pdf(TEST_PDF, out_dir=TEST_OUT, use_marker_fallback=True)

    assert md_path.exists()


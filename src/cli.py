"""CLI interface for PDF parser."""

from pathlib import Path
import os
import sys
from datetime import datetime

# Guard (module-level): prevent accidental duplicate self-launch with global Python on Windows.
# Some third-party tooling may spawn a second interpreter using the system Python.
_allow_global = os.environ.get("PDF_PARSER_ALLOW_GLOBAL_PYTHON") == "1"
_repo_root = Path(__file__).resolve().parents[1]
_venv_python = _repo_root / ".venv" / "Scripts" / "python.exe"
try:
    if not _allow_global and _venv_python.exists():
        if Path(sys.executable).resolve() != _venv_python.resolve():
            sys.stderr.write(
                f"Error: This project must be run with the venv interpreter: {_venv_python}. "
                f"Current interpreter: {sys.executable}.\n"
                "Set PDF_PARSER_ALLOW_GLOBAL_PYTHON=1 to override (not recommended).\n"
            )
            raise SystemExit(3)
except Exception:
    # If path resolution fails, don't hard-block; the out_dir lock still prevents duplicates.
    pass

import click


@click.command()
@click.argument(
    "pdf_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--out-dir",
    "-o",
    type=click.Path(dir_okay=True, path_type=Path),
    default="out",
    help="Output directory for markdown and images.",
)
@click.option(
    "--use-docling",
    is_flag=True,
    help="Use Docling instead of MinerU (MinerU is default, better for tables).",
)
@click.option(
    "--no-gpu",
    is_flag=True,
    help="Disable GPU acceleration (use CPU only).",
)
@click.option(
    "--visual-tables",
    is_flag=True,
    help="Use visual table detection (OpenCV + PaddleOCR) for problematic pages.",
)
@click.option(
    "--visual-pages",
    type=str,
    default=None,
    help="Comma-separated list of page numbers for visual processing (e.g., '37,38').",
)
@click.option(
    "--comprehensive",
    is_flag=True,
    default=False,
    help="Comprehensive mode: process ALL pages with visual table detection (100%% accuracy).",
)
@click.option(
    "--comprehensive-max-pages",
    type=int,
    default=None,
    help="Limit pages in comprehensive mode (debug/smoke runs). Default: all pages.",
)
@click.option(
    "--comprehensive-start-page",
    type=int,
    default=1,
    help="Start page in comprehensive mode (1-indexed). Default: 1.",
)
def main(
    pdf_path: Path,
    out_dir: Path,
    use_docling: bool,
    no_gpu: bool,
    visual_tables: bool,
    visual_pages: str,
    comprehensive: bool,
    comprehensive_max_pages: int | None,
    comprehensive_start_page: int,
) -> None:
    """
    Parse a PDF file and convert to LLM-friendly markdown.

    By default uses MinerU parser (state-of-the-art for tables).
    Use --use-docling flag to switch to Docling parser.

    PDF_PATH: Path to the input PDF file.

    Example:
        python -m src.cli data/Lapua-Tilinpaatos-2024.pdf -o out/lapua_2024
    """
    use_mineru = not use_docling
    use_gpu = not no_gpu

    # Ensure a single active run per output directory (prevents accidental duplicate runs on Windows).
    out_dir.mkdir(parents=True, exist_ok=True)
    lock_path = out_dir / ".pdf_parser_run.lock"
    try:
        # Exclusive create is atomic on Windows/Unix.
        with lock_path.open("x", encoding="utf-8") as f:
            f.write(
                "\n".join(
                    [
                        f"pid={os.getpid()}",
                        f"started_utc={datetime.utcnow().isoformat()}Z",
                        f"argv={' '.join(os.sys.argv)}",
                    ]
                )
                + "\n"
            )
    except FileExistsError as e:
        click.echo(
            f"Error: Another run is already in progress for out_dir={out_dir}. "
            f"If this is stale, delete: {lock_path}",
            err=True,
        )
        raise SystemExit(2) from e

    # Import heavy pipeline only after acquiring the lock (prevents double-start races).
    from .pipeline import process_pdf

    click.echo(f"Processing: {pdf_path}")
    click.echo(f"Output dir: {out_dir}")
    if comprehensive:
        click.echo("Mode: COMPREHENSIVE (all pages, visual table detection)")
    else:
        click.echo(f"Parser: {'MinerU' if use_mineru else 'Docling'}")
        click.echo(f"GPU: {'enabled' if use_gpu else 'disabled'}")

    # Parse visual pages if provided
    visual_pages_list = None
    if visual_pages:
        try:
            visual_pages_list = [int(p.strip()) for p in visual_pages.split(',')]
        except ValueError:
            click.echo(f"Warning: Invalid page numbers: {visual_pages}", err=True)
            visual_pages_list = None
    
    try:
        md_path = process_pdf(
            pdf_path,
            out_dir=out_dir,
            use_mineru=use_mineru,
            use_gpu=use_gpu,
            use_visual_table_detection=visual_tables,
            visual_table_pages=visual_pages_list,
            comprehensive_mode=comprehensive,
            comprehensive_max_pages=comprehensive_max_pages,
            comprehensive_start_page=comprehensive_start_page,
        )
        click.echo(f"Success: {md_path}")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1) from e
    except RuntimeError as e:
        click.echo(f"Processing failed: {e}", err=True)
        raise SystemExit(1) from e
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            # Best-effort cleanup; stale lock can be removed manually.
            pass


if __name__ == "__main__":
    main()

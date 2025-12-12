"""Fast post-run checks for a parsed output directory.

Runs in seconds and does NOT re-run OCR. Intended to fail fast.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import List

import click


_AMOUNT_RE = re.compile(r"-?\d{1,3}(?:\s?\d{3})*,\d{2}")


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _check_files(out_dir: Path) -> List[CheckResult]:
    md = out_dir / "Lapua-Tilinpaatos-2024.md"
    tables = out_dir / "Lapua-Tilinpaatos-2024.tables.json"
    val = out_dir / "Lapua-Tilinpaatos-2024.validation.json"
    res: List[CheckResult] = []
    for p in [md, tables, val]:
        res.append(CheckResult(ok=p.exists(), message=f"exists: {p}"))
    return res


def _check_tase_muut_saamiset(md_text: str) -> CheckResult:
    # Must contain correct value at least once in a table row.
    target = "| Muut saamiset | 4 998 376,39 | 5 345 152,75 |"
    return CheckResult(ok=(target in md_text), message="tase: Muut saamiset corrected in table")


def _check_no_known_bad_amount(md_text: str) -> CheckResult:
    return CheckResult(ok=("95 345 152,75" not in md_text), message="no known bad OCR amount 95 345 152,75")


def _check_pages(md_text: str) -> CheckResult:
    pages = len(re.findall(r"^## Page\s+\d+\s*$", md_text, flags=re.M))
    return CheckResult(ok=(pages == 154), message=f"md pages: {pages} (expected 154)")


@click.command()
@click.argument("out_dir", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path))
def main(out_dir: Path) -> None:
    """Run fast checks against an existing output directory."""
    results: List[CheckResult] = []
    results.extend(_check_files(out_dir))

    md_path = out_dir / "Lapua-Tilinpaatos-2024.md"
    if md_path.exists():
        md_text = _read_text(md_path)
        results.append(_check_pages(md_text))
        results.append(_check_no_known_bad_amount(md_text))
        results.append(_check_tase_muut_saamiset(md_text))

    ok = all(r.ok for r in results)
    payload = {"ok": ok, "checks": [{"ok": r.ok, "message": r.message} for r in results]}
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if ok else 2)


if __name__ == "__main__":
    main()



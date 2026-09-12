#!/usr/bin/env python3
"""Build a portable research-directory shell from the input folder."""

from __future__ import annotations

import argparse
import html
import shutil
import tempfile
from pathlib import Path


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a portable research directory from input files."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def discover_files(input_directory: Path) -> list[Path]:
    if not input_directory.exists():
        input_directory.mkdir(parents=True)
        return []
    return sorted(
        path
        for path in input_directory.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    )


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_report(files: list[Path], input_directory: Path) -> str:
    rows = "".join(
        "<tr><td><code>"
        + html.escape(str(file.relative_to(input_directory)).replace("\\", "/"))
        + "</code></td><td>Skipped</td><td>Content import is not available yet.</td></tr>"
        for file in files
    )
    if not rows:
        rows = "<tr><td colspan=\"3\">No input files were found.</td></tr>"

    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Ingestion report</title><link rel="stylesheet" href="../assets/site.css"></head>
<body><main><p><a href="../index.html">← Directory</a></p><h1>Ingestion report</h1>
<p>Processed: {len(files)} files. Published: 0 resources. Skipped: {len(files)} files.</p>
<table><thead><tr><th>Input file</th><th>Status</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table>
</main></body></html>"""


def build_site(temporary_output: Path, files: list[Path], input_directory: Path) -> None:
    write_file(
        temporary_output / "index.html",
        """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Research Directory</title><link rel="stylesheet" href="assets/site.css"></head>
<body><main><h1>Research Directory</h1><p>Your portable directory is ready.</p><p>No resources have been imported yet.</p><p><a href="reports/ingestion-report.html">View ingestion report</a></p></main></body></html>""",
    )
    write_file(
        temporary_output / "assets" / "site.css",
        """body { background: #f8fafc; color: #172033; font-family: system-ui, sans-serif; line-height: 1.5; margin: 0; } main { margin: 0 auto; max-width: 72rem; padding: 2rem; } a { color: #155eef; } table { background: white; border-collapse: collapse; width: 100%; } th, td { border: 1px solid #d0d5dd; padding: .75rem; text-align: left; }""",
    )
    write_file(temporary_output / "reports" / "ingestion-report.html", build_report(files, input_directory))
    write_file(
        temporary_output / "README.md",
        f"""# Generated Research Directory

## Open locally

Open `index.html` in a modern browser.

## Deploy

Upload the complete contents of this folder to any static hosting provider. Do not upload only `index.html`; `assets/` and `reports/` are required.

## Build summary

- Sources processed: {len(files)}
- Resources published: 0
- Files skipped: {len(files)}

## Review data issues

Open `reports/ingestion-report.html`.
""",
    )


def replace_output(root: Path, files: list[Path], input_directory: Path) -> None:
    output_directory = root / "output"
    with tempfile.TemporaryDirectory(dir=root, prefix=".output-") as temporary_directory:
        temporary_output = Path(temporary_directory) / "output"
        temporary_output.mkdir()
        build_site(temporary_output, files, input_directory)

        backup_directory = root / ".output-previous"
        if backup_directory.exists():
            shutil.rmtree(backup_directory)
        if output_directory.exists():
            output_directory.rename(backup_directory)
        temporary_output.rename(output_directory)
        if backup_directory.exists():
            shutil.rmtree(backup_directory)


def main() -> int:
    root = parse_arguments().root.resolve()
    input_directory = root / "input"
    files = discover_files(input_directory)
    replace_output(root, files, input_directory)
    print(f"Processed: {len(files)} files")
    print("Published: 0 resources")
    print(f"Skipped: {len(files)} files")
    print(f"Open: {root / 'output' / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

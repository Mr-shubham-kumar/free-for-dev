#!/usr/bin/env python3
"""Build a portable research directory from files placed in input."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt"}
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
MARKDOWN_RESOURCE_PATTERN = re.compile(
    r"^\s*(?:[-*+]|\d+[.)])\s+\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)\s*(?:[-–—:]\s*)?(.*)$"
)
TEXT_RESOURCE_PATTERN = re.compile(r"^\s*([^|]+?)\s*\|\s*(https?://[^|\s]+)\s*(?:\|\s*(.*))?$")


@dataclass(frozen=True)
class Resource:
    identifier: str
    name: str
    url: str
    description: str
    category: str
    tags: tuple[str, ...]
    source_path: str
    source_line: int


@dataclass(frozen=True)
class FileReport:
    source_path: str
    status: str
    reason: str


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


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "resource"


def safe_url(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    return None


def resource_identifier(name: str, source_path: str, source_line: int) -> str:
    seed = f"{source_path}:{source_line}:{name}".encode("utf-8")
    return f"{slugify(name)}-{hashlib.sha256(seed).hexdigest()[:8]}"


def extract_tags(description: str) -> tuple[str, ...]:
    return tuple(sorted({match.group(1).lower() for match in re.finditer(r"(?<!\w)#([a-zA-Z0-9-]+)", description)}))


def extract_resources(file: Path, input_directory: Path) -> tuple[list[Resource], list[FileReport]]:
    source_path = str(file.relative_to(input_directory)).replace("\\", "/")
    category = "Uncategorized"
    resources: list[Resource] = []
    warnings: list[FileReport] = []

    for line_number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
        heading = HEADING_PATTERN.match(line)
        if heading:
            category = heading.group(1).strip()
            continue

        match = MARKDOWN_RESOURCE_PATTERN.match(line)
        if not match and file.suffix.lower() == ".txt":
            match = TEXT_RESOURCE_PATTERN.match(line)
        if not match:
            continue

        name, candidate_url, description = (part.strip() for part in match.groups(default=""))
        location = f"{source_path}:{line_number}"
        if not name:
            warnings.append(FileReport(location, "Review", "Missing resource name; not published."))
            continue
        url = safe_url(candidate_url)
        if not url:
            warnings.append(FileReport(location, "Review", "Unsafe or invalid URL; not published."))
            continue
        if not description:
            warnings.append(FileReport(location, "Review", "Missing description."))
        if category == "Uncategorized":
            warnings.append(FileReport(location, "Review", "Ambiguous classification: no heading category."))
        if re.search(r"<[^>]+>", f"{name} {description}"):
            warnings.append(FileReport(location, "Review", "Potentially unsafe markup was escaped."))
        resources.append(
            Resource(
                identifier=resource_identifier(name, source_path, line_number),
                name=name,
                url=url,
                description=description,
                category=category,
                tags=extract_tags(description),
                source_path=source_path,
                source_line=line_number,
            )
        )

    return resources, warnings


def canonical_url(value: str) -> str:
    parsed = urlparse(value)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}?{parsed.query}"


def duplicate_reports(resources: list[Resource]) -> list[FileReport]:
    first_by_url: dict[str, Resource] = {}
    reports: list[FileReport] = []
    for resource in resources:
        key = canonical_url(resource.url)
        first = first_by_url.setdefault(key, resource)
        if first is not resource:
            reports.append(
                FileReport(
                    f"{resource.source_path}:{resource.source_line}",
                    "Review",
                    f"Duplicate candidate of {first.source_path}:{first.source_line}; both sources were retained.",
                )
            )
    return reports


def import_resources(files: list[Path], input_directory: Path) -> tuple[list[Resource], list[FileReport]]:
    resources: list[Resource] = []
    reports: list[FileReport] = []
    for file in files:
        source_path = str(file.relative_to(input_directory)).replace("\\", "/")
        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            reports.append(FileReport(source_path, "Skipped", "Unsupported file type."))
            continue
        try:
            extracted, warnings = extract_resources(file, input_directory)
        except UnicodeDecodeError:
            reports.append(FileReport(source_path, "Skipped", "File is not readable text."))
            continue
        resources.extend(extracted)
        reports.extend(warnings)
        if extracted:
            reports.append(FileReport(source_path, "Published", f"Published {len(extracted)} resource(s)."))
        else:
            reports.append(FileReport(source_path, "Review", "No supported resource entries found."))
    reports.extend(duplicate_reports(resources))
    return resources, reports


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def escaped(value: str) -> str:
    return html.escape(value, quote=True)


def tag_list(resource: Resource) -> str:
    if not resource.tags:
        return ""
    return "<ul class=\"tags\">" + "".join(f"<li>{escaped(tag)}</li>" for tag in resource.tags) + "</ul>"


def resource_card(resource: Resource) -> str:
    description = f"<p>{escaped(resource.description)}</p>" if resource.description else ""
    return f"""<article class="resource-card" data-resource-id="{escaped(resource.identifier)}">
<h2><a href="resources/{escaped(resource.identifier)}.html">{escaped(resource.name)}</a></h2>
<p class="category">{escaped(resource.category)}</p>{tag_list(resource)}{description}
<p class="source">Source: {escaped(resource.source_path)}:{resource.source_line}</p>
</article>"""


def resource_page(resource: Resource) -> str:
    description = f"<p>{escaped(resource.description)}</p>" if resource.description else ""
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{escaped(resource.name)} · Research Directory</title><link rel="stylesheet" href="../assets/site.css"></head>
<body><main><p><a href="../index.html">← Directory</a></p><article><h1>{escaped(resource.name)}</h1>
<p class="category">{escaped(resource.category)}</p>{tag_list(resource)}{description}
<p><a href="{escaped(resource.url)}" rel="noopener noreferrer">Visit resource</a></p>
<p class="source">Source: {escaped(resource.source_path)}:{resource.source_line}</p></article></main></body></html>"""


def build_report(reports: list[FileReport], published_count: int, processed_count: int) -> str:
    rows = "".join(
        f"<tr><td><code>{escaped(report.source_path)}</code></td><td>{escaped(report.status)}</td><td>{escaped(report.reason)}</td></tr>"
        for report in reports
    )
    if not rows:
        rows = "<tr><td colspan=\"3\">No input files were found.</td></tr>"
    skipped_count = sum(report.status == "Skipped" for report in reports)
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Ingestion report</title><link rel="stylesheet" href="../assets/site.css"></head>
<body><main><p><a href="../index.html">← Directory</a></p><h1>Ingestion report</h1>
<p>Processed: {processed_count} files. Published: {published_count} resources. Skipped: {skipped_count} files.</p>
<table><thead><tr><th>Input file</th><th>Status</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table>
</main></body></html>"""


def search_records(resources: list[Resource]) -> str:
    records = [
        {
            "id": resource.identifier,
            "name": resource.name,
            "description": resource.description,
            "category": resource.category,
            "tags": list(resource.tags),
        }
        for resource in resources
    ]
    return json.dumps(records, ensure_ascii=False).replace("<", "\\u003c")


def select_options(values: list[str], label: str) -> str:
    return "".join(f'<option value="{escaped(value)}">{escaped(label)}: {escaped(value)}</option>' for value in values)


def build_site(
    temporary_output: Path, resources: list[Resource], reports: list[FileReport], processed_count: int
) -> None:
    cards = "".join(resource_card(resource) for resource in resources)
    directory_content = cards or "<p>No resources have been imported yet.</p>"
    categories = sorted({resource.category for resource in resources})
    tags = sorted({tag for resource in resources for tag in resource.tags})
    write_file(
        temporary_output / "index.html",
        f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Research Directory</title><link rel="stylesheet" href="assets/site.css"></head>
<body><main><h1>Research Directory</h1><p>Your portable directory is ready.</p>
<form role="search" class="filters"><label for="search">Search resources</label><input id="search" type="search" aria-label="Search resources" autocomplete="off"><label for="category">Category</label><select id="category"><option value="">All categories</option>{select_options(categories, "Category")}</select><label for="tag">Tag</label><select id="tag"><option value="">All tags</option>{select_options(tags, "Tag")}</select></form>
<p id="result-count" aria-live="polite"></p><section aria-label="Resources">{directory_content}</section><p><a href="reports/ingestion-report.html">View ingestion report</a></p></main><script src="assets/directory.js"></script></body></html>""",
    )
    write_file(
        temporary_output / "assets" / "site.css",
        """body { background: #f8fafc; color: #172033; font-family: system-ui, sans-serif; line-height: 1.5; margin: 0; } main { margin: 0 auto; max-width: 72rem; padding: 2rem; } a { color: #155eef; } .filters { display: grid; gap: .5rem; grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr)); } input, select { font: inherit; padding: .5rem; } .resource-card { background: white; border: 1px solid #d0d5dd; border-radius: .5rem; margin: 1rem 0; padding: 1rem; } .resource-card h2 { margin-top: 0; } .category, .source { color: #475467; } .tags { display: flex; flex-wrap: wrap; gap: .5rem; list-style: none; padding: 0; } .tags li { background: #e0eaff; border-radius: 1rem; padding: .125rem .5rem; } table { background: white; border-collapse: collapse; width: 100%; } th, td { border: 1px solid #d0d5dd; padding: .75rem; text-align: left; }""",
    )
    write_file(
        temporary_output / "assets" / "directory.js",
        f"""const resources = {search_records(resources)};
const search = document.querySelector('#search');
const category = document.querySelector('#category');
const tag = document.querySelector('#tag');
const count = document.querySelector('#result-count');
const parameters = new URLSearchParams(window.location.search);
search.value = parameters.get('q') || '';
category.value = parameters.get('category') || '';
tag.value = parameters.get('tag') || '';
function applyFilters() {{
  const query = search.value.trim().toLowerCase();
  let visible = 0;
  for (const resource of resources) {{
    const searchable = [resource.name, resource.description, resource.category, ...resource.tags].join(' ').toLowerCase();
    const matches = (!query || searchable.includes(query)) && (!category.value || resource.category === category.value) && (!tag.value || resource.tags.includes(tag.value));
    document.querySelector(`[data-resource-id="${{resource.id}}"]`).hidden = !matches;
    if (matches) visible += 1;
  }}
  count.textContent = `${{visible}} resource${{visible === 1 ? '' : 's'}} shown`;
}}
for (const control of [search, category, tag]) {{
  control.addEventListener('input', applyFilters);
  control.addEventListener('change', applyFilters);
}}
applyFilters();
""",
    )
    for resource in resources:
        write_file(temporary_output / "resources" / f"{resource.identifier}.html", resource_page(resource))
    write_file(
        temporary_output / "reports" / "ingestion-report.html",
        build_report(reports, len(resources), processed_count),
    )
    skipped_count = sum(report.status == "Skipped" for report in reports)
    write_file(
        temporary_output / "README.md",
        f"""# Generated Research Directory

## Open locally

Open `index.html` in a modern browser.

## Deploy

Upload the complete contents of this folder to any static hosting provider. Do not upload only `index.html`; `assets/`, `resources/`, and `reports/` are required.

## Build summary

- Sources processed: {processed_count}
- Resources published: {len(resources)}
- Files skipped: {skipped_count}

## Review data issues

Open `reports/ingestion-report.html`.
""",
    )


def replace_output(
    root: Path, resources: list[Resource], reports: list[FileReport], processed_count: int
) -> None:
    output_directory = root / "output"
    with tempfile.TemporaryDirectory(dir=root, prefix=".output-") as temporary_directory:
        temporary_output = Path(temporary_directory) / "output"
        temporary_output.mkdir()
        build_site(temporary_output, resources, reports, processed_count)

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
    resources, reports = import_resources(files, input_directory)
    replace_output(root, resources, reports, len(files))
    skipped_count = sum(report.status == "Skipped" for report in reports)
    print(f"Processed: {len(files)} files")
    print(f"Published: {len(resources)} resources")
    print(f"Skipped: {skipped_count} files")
    print(f"Open: {root / 'output' / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_COMMAND = PROJECT_ROOT / "program" / "build.py"


class BuildContractTests(unittest.TestCase):
    def run_build(self, workspace: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BUILD_COMMAND), "--root", str(workspace)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_build_creates_a_portable_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            workspace = Path(temp_directory)
            (workspace / "input").mkdir()

            result = self.run_build(workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Processed: 0 files", result.stdout)
            self.assertTrue((workspace / "output" / "index.html").is_file())
            self.assertTrue((workspace / "output" / "assets" / "site.css").is_file())
            self.assertTrue(
                (workspace / "output" / "reports" / "ingestion-report.html").is_file()
            )
            self.assertIn(
                "Open `index.html`",
                (workspace / "output" / "README.md").read_text(encoding="utf-8"),
            )

    def test_build_ignores_the_input_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            workspace = Path(temp_directory)
            input_directory = workspace / "input"
            input_directory.mkdir()
            (input_directory / ".gitkeep").touch()

            result = self.run_build(workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Processed: 0 files", result.stdout)
            report = (workspace / "output" / "reports" / "ingestion-report.html").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(".gitkeep", report)

    def test_build_reports_unsupported_files_and_replaces_stale_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            workspace = Path(temp_directory)
            input_directory = workspace / "input"
            input_directory.mkdir()
            source_file = input_directory / "research.bin"
            source_file.write_bytes(b"unreadable research")
            stale_file = workspace / "output" / "stale.txt"
            stale_file.parent.mkdir()
            stale_file.write_text("remove me", encoding="utf-8")

            result = self.run_build(workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(source_file.read_bytes(), b"unreadable research")
            self.assertFalse(stale_file.exists())
            report = (workspace / "output" / "reports" / "ingestion-report.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("research.bin", report)
            self.assertIn("Skipped", report)

    def test_build_publishes_markdown_resources_with_source_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            workspace = Path(temp_directory)
            input_directory = workspace / "input"
            input_directory.mkdir()
            (input_directory / "research.md").write_text(
                "## Hosting\n\n- [Example Host](https://host.example) - Static hosting.\n",
                encoding="utf-8",
            )

            result = self.run_build(workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Published: 1 resources", result.stdout)
            index = (workspace / "output" / "index.html").read_text(encoding="utf-8")
            self.assertIn("Example Host", index)
            self.assertIn("Static hosting.", index)
            detail_pages = list((workspace / "output" / "resources").glob("*.html"))
            self.assertEqual(len(detail_pages), 1)
            detail = detail_pages[0].read_text(encoding="utf-8")
            self.assertIn("Example Host", detail)
            self.assertIn("Source: research.md:3", detail)

    def test_build_publishes_pipe_delimited_plain_text_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            workspace = Path(temp_directory)
            input_directory = workspace / "input"
            input_directory.mkdir()
            (input_directory / "research.txt").write_text(
                "Text Host | https://text-host.example | Plain-text hosting.\n",
                encoding="utf-8",
            )

            result = self.run_build(workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            index = (workspace / "output" / "index.html").read_text(encoding="utf-8")
            self.assertIn("Text Host", index)
            self.assertIn("Plain-text hosting.", index)
            detail = next((workspace / "output" / "resources").glob("*.html")).read_text(
                encoding="utf-8"
            )
            self.assertIn("Source: research.txt:1", detail)

    def test_build_generates_accessible_search_and_reliable_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            workspace = Path(temp_directory)
            input_directory = workspace / "input"
            input_directory.mkdir()
            (input_directory / "research.md").write_text(
                "## Hosting\n\n- [Example Host](https://host.example) - Static hosting for #frontend.\n",
                encoding="utf-8",
            )

            result = self.run_build(workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            index = (workspace / "output" / "index.html").read_text(encoding="utf-8")
            script = (workspace / "output" / "assets" / "directory.js").read_text(
                encoding="utf-8"
            )
            self.assertIn('role="search"', index)
            self.assertIn('aria-label="Search resources"', index)
            self.assertIn("Hosting", index)
            self.assertIn("frontend", index)
            self.assertIn('src="assets/directory.js"', index)
            self.assertIn("Example Host", script)

    def test_build_reports_invalid_unsafe_and_duplicate_resources_without_hiding_valid_ones(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            workspace = Path(temp_directory)
            input_directory = workspace / "input"
            input_directory.mkdir()
            (input_directory / "research.md").write_text(
                "## Hosting\n\n"
                "- [Valid](https://host.example) - A valid resource.\n"
                "- [Duplicate](https://host.example/) - A duplicate resource.\n"
                "- [Unsafe](javascript:alert) - Unsafe URL.\n"
                "- [](https://missing-name.example) - Missing name.\n"
                "- [Markup](https://markup.example) - <script>unsafe</script>.\n",
                encoding="utf-8",
            )

            result = self.run_build(workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Published: 3 resources", result.stdout)
            report = (workspace / "output" / "reports" / "ingestion-report.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("Duplicate candidate", report)
            self.assertIn("Unsafe or invalid URL", report)
            self.assertIn("Missing resource name", report)
            self.assertIn("Potentially unsafe markup", report)
            index = (workspace / "output" / "index.html").read_text(encoding="utf-8")
            self.assertIn("Valid", index)
            self.assertIn("&lt;script&gt;unsafe&lt;/script&gt;", index)

    def test_build_publishes_csv_json_and_yaml_resources_from_nested_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            workspace = Path(temp_directory)
            input_directory = workspace / "input" / "structured"
            input_directory.mkdir(parents=True)
            (input_directory / "services.csv").write_text(
                "name,url,description,category,tags\nCSV Host,https://csv.example,CSV hosting,Hosting,frontend\n",
                encoding="utf-8",
            )
            (input_directory / "services.json").write_text(
                '[{"name":"JSON Host","url":"https://json.example","description":"JSON hosting","category":"Hosting","tags":["backend"]}]',
                encoding="utf-8",
            )
            (input_directory / "services.yaml").write_text(
                "- name: YAML Host\n  url: https://yaml.example\n  description: YAML hosting\n  category: Hosting\n  tags: docs\n",
                encoding="utf-8",
            )
            (input_directory / "broken.json").write_text("{not valid json", encoding="utf-8")

            result = self.run_build(workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Published: 3 resources", result.stdout)
            index = (workspace / "output" / "index.html").read_text(encoding="utf-8")
            self.assertIn("CSV Host", index)
            self.assertIn("JSON Host", index)
            self.assertIn("YAML Host", index)
            self.assertIn("frontend", index)
            self.assertIn("backend", index)
            self.assertIn("docs", index)
            report = (workspace / "output" / "reports" / "ingestion-report.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("broken.json", report)
            self.assertIn("Malformed structured data", report)

    def test_build_publishes_extractable_docx_and_pdf_resources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            workspace = Path(temp_directory)
            input_directory = workspace / "input"
            input_directory.mkdir()
            document_xml = """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>DOCX Host | https://docx.example | DOCX hosting</w:t></w:r></w:p></w:body></w:document>"""
            with zipfile.ZipFile(input_directory / "services.docx", "w") as document:
                document.writestr("word/document.xml", document_xml)
            (input_directory / "services.pdf").write_bytes(
                b"%PDF-1.4\n(PDF Host | https://pdf.example | PDF hosting) Tj\n"
            )
            (input_directory / "unreadable.pdf").write_bytes(b"not a text PDF")

            result = self.run_build(workspace)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Published: 2 resources", result.stdout)
            index = (workspace / "output" / "index.html").read_text(encoding="utf-8")
            self.assertIn("DOCX Host", index)
            self.assertIn("PDF Host", index)
            report = (workspace / "output" / "reports" / "ingestion-report.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("unreadable.pdf", report)
            self.assertIn("No extractable document resource entries found", report)

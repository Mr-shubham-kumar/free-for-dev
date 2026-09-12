from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
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

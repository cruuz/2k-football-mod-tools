"""Beta 74: the parent Studio reads back the receipts a real child build wrote.

Coach Edwards, 2026-09-20 13:05: "The texture receipt is missing or exceeds its
size bound." The receipts are written by the child build tool into the stage's
build-artifacts folder and read back by the parent after the child exits. No
test drove that real chain for an equipment edit: the one end-to-end build test
used a fake runner that wrote the receipts itself. This runs the real child
(``visual_mod_project.py build`` over the synthetic disc) and the real readback
(``verified_build_texture_lines``), then reproduces the two Windows shapes of
the failure on the real artifact folder:

* the receipt is genuinely gone: the refusal must name the file and list what
  the folder holds, so the report is diagnosable from the dialog;
* the receipt is briefly unavailable after the child exits (a scanner or sync
  client holding a just-written file): the bounded retry must succeed.

Synthetic disc only; no retail bytes.
"""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

from mod_editor.core import equipment_reporting
from mod_editor.core.equipment_reporting import verified_build_texture_lines
from mod_editor.core.errors import ValidationError
from test_b721_equipment_build_refit import run_cli_build, tight_fixture, built_equipment
import b661_build_fixture as build_fixture


class RealChildReceiptReadbackTests(unittest.TestCase):
    def _real_build(self, root):
        (root / "equipment").mkdir()
        fixture, rgba = tight_fixture(root / "equipment", family=8)
        build_fixture.create(root, equipment=fixture)
        asset_id, png = fixture.png(rgba=rgba)
        completed = run_cli_build(root, [dict(kind="uniform_equipment_texture", asset_id=asset_id,
                                              png=str(png))])
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("NFL2K5_VISUAL_MOD_BUILD_PASS edits=1", completed.stdout)
        # The receipt the parent will read is the one the child named in the manifest.
        report, _span = built_equipment(root)
        self.assertTrue(report)
        return root / "receipt.json"

    def _receipt_path(self, manifest):
        import json
        value = json.loads(manifest.read_text(encoding="utf-8"))
        row = next(e for e in value["edits"] if e["kind"] == "uniform_equipment_texture")
        return Path(value["output"]["artifact_directory"]) / row["import_report"]["file_name"]

    def test_parent_reads_the_receipt_the_real_child_wrote(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = self._real_build(Path(folder).resolve())
            lines = verified_build_texture_lines(manifest)
            self.assertTrue(lines)
            self.assertTrue(any("shoes01" in line for line in lines), lines)
            receipt = self._receipt_path(manifest)
            self.assertTrue(receipt.is_file())
            # Equipment receipts are numbered per edit: 00000_import.json.
            self.assertTrue(receipt.name.endswith("_import.json"), receipt.name)

    def test_missing_receipt_names_the_file_and_the_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = self._real_build(Path(folder).resolve())
            receipt = self._receipt_path(manifest)
            receipt.unlink()
            # Keep the test fast: the backoff is a module constant for exactly this.
            with patch.object(equipment_reporting, "RECEIPT_READ_BACKOFF", (0.001, 0.001)):
                with self.assertRaises(ValidationError) as caught:
                    verified_build_texture_lines(manifest)
            text = str(caught.exception)
            self.assertIn("texture receipt is missing or exceeds its size bound", text)
            self.assertIn(str(receipt), text)
            self.assertIn("does not exist", text)
            self.assertIn("The artifact folder holds:", text)
            # The folder still holds the child's copy of the source PNG, so the
            # listing proves the folder itself survived and only the receipt is gone.
            listed = text.split("The artifact folder holds:", 1)[1]
            self.assertIn("shoes01.png", listed)
            self.assertNotIn(receipt.name, listed)

    def test_briefly_unavailable_receipt_is_read_on_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = self._real_build(Path(folder).resolve())
            receipt = self._receipt_path(manifest)
            aside = receipt.with_name(receipt.name + ".held")
            os.rename(receipt, aside)

            def restore():
                time.sleep(0.15)
                os.rename(aside, receipt)

            thread = threading.Thread(target=restore, daemon=True)
            with patch.object(equipment_reporting, "RECEIPT_READ_BACKOFF", (0.05, 0.1, 0.2, 0.4)):
                thread.start()
                lines = verified_build_texture_lines(manifest)
            thread.join(2)
            self.assertTrue(lines)
            self.assertTrue(receipt.is_file())

    def test_oversized_receipt_is_refused_without_waiting(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = self._real_build(Path(folder).resolve())
            receipt = self._receipt_path(manifest)
            with patch.object(equipment_reporting, "RECEIPT_SIZE_BOUND", 16):
                started = time.monotonic()
                with self.assertRaises(ValidationError) as caught:
                    verified_build_texture_lines(manifest)
                elapsed = time.monotonic() - started
            self.assertIn("outside 1..16", str(caught.exception))
            # An oversized file cannot become smaller by waiting; no full backoff.
            self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()

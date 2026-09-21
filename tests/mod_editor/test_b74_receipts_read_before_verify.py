"""Beta 74: texture receipts are read when the builder exits, not after the verifier.

Coach Edwards, 2026-09-20 13:05, Windows: "The texture receipt is missing or
exceeds its size bound" on a build whose verifier had just passed. The
verifier checks the artifact folder FIRST and then hashes two 6 GB discs, so
a receipt present when it started could be gone minutes later when the parent
read it for the summary; the verifier's closing identity check covers the
folder, not its files. Whatever holds or removes files in that window on his
machine, the parent now reads and hash-checks every receipt the moment the
builder exits, holds them, and requires the manifest it reads after
verification to hash the same as the one those receipts were bound to.

Synthetic fixture and the fake backend runner; no retail bytes.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

from mod_editor.core import equipment_reporting
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_build_service import Nfl2k5BuildError, Nfl2k5BuildService
from test_b70_a3_integration import TextureReceiptRunner
import test_nfl2k5_build_service as build_fixtures

RECEIPT = "uniform_equipment_texture.json"


class VanishingReceiptRunner(TextureReceiptRunner):
    """The fake backend, plus what something on his machine did between the passes."""

    def __init__(self, *, vanish_during=None, rewrite_manifest=False):
        super().__init__()
        self.vanish_during = vanish_during
        self.rewrite_manifest = rewrite_manifest

    def run(self, argv, cwd):
        artifact_dir = self._argument(tuple(argv), "--artifact-dir")
        if argv[2] == "verify" and self.vanish_during == "verify":
            # Gone while the verifier hashes the discs; its artifact check
            # already ran at its start, so the child pass still passes.
            (artifact_dir / RECEIPT).unlink()
        result = super().run(argv, cwd)
        if argv[2] == "build" and self.vanish_during == "build":
            (artifact_dir / RECEIPT).unlink()
        if argv[2] == "verify" and self.rewrite_manifest:
            manifest = self._argument(tuple(argv), "--manifest")
            value = json.loads(manifest.read_text())
            value["note"] = "rewritten after the build"
            manifest.write_text(json.dumps(value))
        return result


class ReceiptsReadBeforeVerifyTests(unittest.TestCase):
    def test_a_receipt_removed_during_verification_does_not_fail_a_verified_build(self):
        with tempfile.TemporaryDirectory(prefix="b74-vanish-") as directory:
            fixture = build_fixtures.SyntheticFixture(Path(directory))
            runner = VanishingReceiptRunner(vanish_during="verify")
            result = Nfl2k5BuildService(runner=runner).build(
                fixture.cache, fixture.project, fixture.output)
            self.assertTrue(fixture.output.is_file())
            self.assertEqual([call[2] for call in runner.calls], ["build", "verify"])
            self.assertEqual(result.texture_summary[0],
                             "Equipment socks00 (05A0, 05H0): fitted at 64 x 64, 16 colours.")
            self.assertEqual(len(result.texture_summary), 2)
            self.assertEqual(fixture.stage_paths(), [])

    def test_a_receipt_missing_when_the_builder_exits_fails_before_verification(self):
        with tempfile.TemporaryDirectory(prefix="b74-vanish-") as directory:
            fixture = build_fixtures.SyntheticFixture(Path(directory))
            runner = VanishingReceiptRunner(vanish_during="build")
            with patch.object(equipment_reporting, "RECEIPT_READ_BACKOFF", (0.001, 0.001)):
                with self.assertRaises(ValidationError) as caught:
                    Nfl2k5BuildService(runner=runner).build(
                        fixture.cache, fixture.project, fixture.output)
            text = str(caught.exception)
            self.assertIn("The texture receipt is missing or exceeds its size bound", text)
            self.assertIn(RECEIPT, text)
            self.assertIn("does not exist", text)
            self.assertIn("stadium_texture.json", text.split("The artifact folder holds:", 1)[1])
            # The minutes of verification are not spent on a build that cannot finish.
            self.assertEqual([call[2] for call in runner.calls], ["build"])
            self.assertFalse(fixture.output.exists())
            kept = sorted(fixture.output.parent.glob(f".{fixture.output.name}.2k5mod-failed-*"))
            self.assertEqual(len(kept), 1, kept)
            # The service names the kept folder from its resolved output path; on the
            # Windows runner the temp dir is an 8.3 short name (RUNNER~1) that the
            # message spells out in full, so the folder NAME is what is compared.
            self.assertIn(kept[0].name, text)
            self.assertTrue((kept[0] / "build-manifest.json").is_file())
            self.assertTrue((kept[0] / "build-artifacts" / "stadium_texture.json").is_file())

    def test_a_manifest_rewritten_after_the_build_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="b74-vanish-") as directory:
            fixture = build_fixtures.SyntheticFixture(Path(directory))
            runner = VanishingReceiptRunner(rewrite_manifest=True)
            with self.assertRaisesRegex(Nfl2k5BuildError,
                                        "changed between the build and its safety check"):
                Nfl2k5BuildService(runner=runner).build(
                    fixture.cache, fixture.project, fixture.output)
            self.assertFalse(fixture.output.exists())


if __name__ == "__main__":
    unittest.main()

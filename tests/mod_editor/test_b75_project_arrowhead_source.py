"""Beta 75: a project build's Arrowhead pass reads the disc the user chose.

Smuzz built a texture project with a preset on 2026-09-21 and got "Couldn't
make the disc. [Errno 2] No such file or directory:
'E:\\...\\.studio-build-aqijzioj\\project\\source.iso'", a folder he correctly
said he never set. ``build`` gives the project builder a private
``<stage>/project/source.iso``, and since beta 74 the copy step CONSUMES that
file (``os.replace`` onto the output instead of a second 6 GB copy). The
combined colour-plus-Arrowhead pass then reopened it by name to read the
retail stadium bundles, which is both gone and, on a texture project, the
wrong bytes to call retail.

The stand-ins below keep the shape of the real modules (the colour pass writes
the sidecar receipt that sends Arrowhead down its combined path; Arrowhead
opens ``retail_source`` exactly as ``OuterImage`` does) without the retail
bundle pins, which no synthetic disc can satisfy.
"""
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(Path(__file__).parent)]
from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_modern_color as colour
from test_mod_build_performance import synthetic_disc, SyntheticProject


def _colour_receipt(settings=None):
    """A receipt the real reader accepts, with no bundle work behind it."""
    normalized = colour.normalize_settings(settings)
    return {"schema": colour.RECEIPT_SCHEMA, "settings": normalized,
            "settings_sha256": colour.settings_id(normalized), "state": "applied",
            "label": "colour", "bundles": 0, "already_applied": 0, "rewritten": 0,
            "bundle_pins": {}, "edits": {}}


class ProjectArrowheadSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="b75-arrowhead-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "retail.iso"
        synthetic_disc(self.source)
        self.original = self.source.read_bytes()
        self.service = SyntheticProject(self.source)
        self.retail_reads: list[str] = []

    # -- stand-ins ---------------------------------------------------------
    def _colour_module(self):
        def apply_to_image(target, *, progress=None, workers=None, settings=None, source_receipt=None):
            receipt = _colour_receipt(settings)
            colour._save_image_receipt(target, receipt)
            return receipt

        return types.SimpleNamespace(
            read_image_receipt=colour.read_image_receipt, receipt_path=colour.receipt_path,
            _save_image_receipt=colour._save_image_receipt, normalize_settings=colour.normalize_settings,
            settings_id=colour.settings_id, RECEIPT_SCHEMA=colour.RECEIPT_SCHEMA,
            xbe_status=lambda payload, settings=None: "retail",
            check_image_request=lambda source, settings=None, *, receipt=None: "retail",
            apply=lambda payload, *, enabled=True, settings=None, previous_settings=None: (payload, {"state": "applied"}),
            verify=lambda payload, *, enabled=True, settings=None: None,
            apply_to_image=apply_to_image)

    def _arrowhead_module(self, *, reach_for_the_consumed_copy=False):
        def apply_to_image(target, *, progress=None, retail_source=None):
            self.retail_reads.append(str(retail_source))
            if reach_for_the_consumed_copy:
                retail_source = Path(target).parent / "project" / "source.iso"
            if colour.read_image_receipt(target) is not None:
                # nfl2k5_modern_arrowhead.apply_combined_to_image opens the
                # retail source through OuterImage, whose os.open is what
                # produced "[Errno 2] No such file or directory".
                os.close(os.open(retail_source, os.O_RDONLY | getattr(os, "O_BINARY", 0)))
            return {"state": "applied", "label": "arrowhead", "bundles": [], "edits": []}

        return types.SimpleNamespace(image_status=lambda source: "retail",
                                     verify=lambda source, *, enabled=True: None,
                                     apply_to_image=apply_to_image)

    def _modules(self, **kwargs):
        real = mod_build._core_module
        stand_ins = {"nfl2k5_modern_color": self._colour_module(),
                     "nfl2k5_modern_arrowhead": self._arrowhead_module(**kwargs)}
        return mock.patch.object(mod_build, "_core_module",
                                 side_effect=lambda name: stand_ins.get(name) or real(name))

    def _plan(self, name):
        return mod_build.BuildPlan(str(self.source), str(self.root / name), modern_color=True,
                                   modern_arrowhead=True, catch_slider=True, draft_ai=True)

    # -- tests -------------------------------------------------------------
    def test_combined_arrowhead_reads_the_chosen_disc_not_the_consumed_copy(self):
        target = self.root / "project.iso"
        # A FileNotFoundError naming a missing .iso is turned into a SKIP by
        # tests/conftest.py (game data absent), which is exactly the shape this
        # bug had, so the regression is caught here and re-raised outside the
        # handler. Raising inside it would attach the original as __context__
        # and the hook would skip this test instead of failing it.
        lost = None
        receipt = None
        with self._modules():
            try:
                receipt = mod_build.build_with_project(self._plan(target.name), self.service, None, None)
            except FileNotFoundError as exc:
                lost = str(exc)
        if lost is not None:
            self.fail(f"a build step read a file the copy pass had consumed: {lost}")
        # Resolved on both sides: the build resolves the chosen disc, and the
        # runners' temp folders are symlinks (/private/var on macOS) or 8.3
        # short names (RUNNER~1 on Windows).
        self.assertEqual([Path(p).resolve() for p in self.retail_reads], [Path(self.source).resolve()])
        self.assertEqual(receipt["result"]["modern_arrowhead"], "applied")
        self.assertTrue(target.is_file())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(list(self.root.glob(mod_build.STAGE_PREFIX + "*")))

    def test_a_plain_build_still_reads_its_own_source(self):
        target = self.root / "plain.iso"
        with self._modules():
            mod_build.build(self._plan(target.name))
        self.assertEqual([Path(p).resolve() for p in self.retail_reads], [Path(self.source).resolve()])
        self.assertTrue(target.is_file())

    def test_a_missing_step_input_names_the_step_and_the_role(self):
        private = self.root / (mod_build.STAGE_PREFIX + "aqijzioj") / "project" / "source.iso"
        with self.assertRaises(ValueError) as caught:
            mod_build.require_step_source(private, "Modern Arrowhead")
        message = str(caught.exception)
        self.assertIn("Modern Arrowhead", message)
        self.assertIn("the project build's private copy of the disc", message)
        self.assertNotIn(mod_build.STAGE_PREFIX, message)
        with self.assertRaises(ValueError) as chosen:
            mod_build.require_step_source(self.root / "gone.iso", "Modern Arrowhead")
        self.assertIn("gone.iso", str(chosen.exception))
        self.assertIn("no longer on this computer", str(chosen.exception))

    def test_a_lost_private_file_is_reported_in_words_not_as_a_temp_path(self):
        """Any later step that loses a staged file gets a sentence, not [Errno 2]."""
        target = self.root / "lost.iso"
        with self._modules(reach_for_the_consumed_copy=True):
            with self.assertRaises(ValueError) as caught:
                mod_build.build_with_project(self._plan(target.name), self.service, None, None)
        message = str(caught.exception)
        self.assertIn("Modern Arrowhead: stadium packages", message)
        self.assertIn("the project build's private copy of the disc", message)
        self.assertNotIn(mod_build.STAGE_PREFIX, message)
        self.assertNotIn("Errno", message)
        self.assertFalse(target.exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_the_words_carry_a_fix_hint(self):
        from mod_editor.gui.ux_text import fix_hint
        private = self.root / (mod_build.STAGE_PREFIX + "aqijzioj") / "project" / "source.iso"
        with self.assertRaises(ValueError) as caught:
            mod_build.require_step_source(private, "Modern Arrowhead")
        self.assertIsNotNone(fix_hint(str(caught.exception)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

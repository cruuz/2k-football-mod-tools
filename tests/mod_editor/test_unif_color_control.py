"""The facemask colour has to be pickable, stageable, and buildable.

Every previous attempt at this lane stopped one layer short. The writer could
only paint magenta, so it was a proof rather than a feature. Then it took a
colour but only from a terminal. Then the composed build understood the edit
but nothing could create one. A control that stages an edit the build cannot
consume, or a build route nothing can reach, is worth nothing to a modder.

So these assertions walk the whole chain in the order the bytes travel:

    colour picker -> session -> canonical project -> composed build

and the two ends are checked against each other, because that join is where
this kind of feature dies.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_unif_color_writer as colour  # noqa: E402

_SESSION = (_REPO_ROOT / "mod_editor" / "studio" / "session.py").read_text(
    encoding="utf-8"
)
_FACADE = (_REPO_ROOT / "mod_editor" / "studio" / "facade.py").read_text(
    encoding="utf-8"
)
_STUDIO = (_REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py").read_text(
    encoding="utf-8"
)
_PROJECT = (_REPO_ROOT / "tools" / "nfl2k5_visual_mod_project.py").read_text(
    encoding="utf-8"
)


class ColourParsingTests(unittest.TestCase):
    def test_both_accepted_spellings_agree(self) -> None:
        self.assertEqual(colour.parse_color("FF1A1A1A"), 0xFF1A1A1A)
        self.assertEqual(colour.parse_color("#1A1A1A"), 0xFF1A1A1A)
        self.assertEqual(colour.parse_color("1a1a1a"), 0xFF1A1A1A)

    def test_junk_is_refused(self) -> None:
        for bad in ("", "nope", "#12345", "GGGGGG", "FF1A1A1A1A"):
            with self.subTest(bad=bad):
                with self.assertRaises(colour.UnifColorWriterError):
                    colour.parse_color(bad)


class WriterTests(unittest.TestCase):
    def test_one_choice_touches_both_packs(self) -> None:
        built = colour.build_unif_color_imports(
            {"kind": "unif_color", "facemask": "FF1A1A1A", "turtleneck": "FFB0B0B0"}
        )
        self.assertEqual(len(built), 2)
        packs = {record["xiso_pack_path"] for _r, _p, _rep, _s, record in built}
        self.assertEqual(packs, {"vc_53450030/A", "vc_53450030/B"})

    def test_every_replacement_is_exactly_the_two_colour_words(self) -> None:
        built = colour.build_unif_color_imports(
            {"kind": "unif_color", "facemask": "FF1A1A1A", "turtleneck": "FFB0B0B0"}
        )
        for replacement, _previews, _report, _selector, record in built:
            self.assertEqual(len(replacement), 8)
            self.assertEqual(record["span_size"], 8)

    def test_selectors_are_distinct_so_the_build_can_tell_them_apart(self) -> None:
        built = colour.build_unif_color_imports(
            {"kind": "unif_color", "facemask": "FF1A1A1A", "turtleneck": "FFB0B0B0"}
        )
        selectors = [selector for *_rest, selector, _record in built]
        self.assertEqual(len(selectors), len(set(selectors)))

    def test_choosing_the_retail_colours_is_refused(self) -> None:
        retail = colour.targets()[0].expected_bytes
        facemask = f"{int.from_bytes(retail[:4], 'little'):08X}"
        turtleneck = f"{int.from_bytes(retail[4:], 'little'):08X}"
        with self.assertRaises(colour.UnifColorWriterError):
            colour.build_unif_color_imports(
                {"kind": "unif_color", "facemask": facemask,
                 "turtleneck": turtleneck}
            )


class ChainTests(unittest.TestCase):
    """The joins between layers, which is where this feature kept dying."""

    def test_the_session_can_stage_and_clear_a_colour(self) -> None:
        for member in ("def set_unif_colors", "def clear_unif_colors",
                       "def unif_colors"):
            self.assertIn(member, _SESSION)

    def test_a_staged_colour_counts_as_a_pending_edit(self) -> None:
        """Otherwise Build Modded XISO would refuse with 'nothing to build'."""
        self.assertIn("(1 if self._unif_colors is not None else 0)", _SESSION)
        self.assertIn("and self._unif_colors is None", _SESSION)

    def test_revert_all_clears_it(self) -> None:
        self.assertIn("self._unif_colors = None", _SESSION)

    def test_the_session_emits_exactly_the_fields_the_build_validates(self) -> None:
        """The join that matters: producer and consumer must agree."""
        self.assertIn('"kind": "unif_color",', _SESSION)
        for field in ("facemask", "turtleneck"):
            self.assertIn(f'"{field}": {field},', _SESSION)
        self.assertIn(
            'UNIF_COLOR_FIELDS = {"kind", "facemask", "turtleneck"}', _PROJECT
        )

    def test_the_build_knows_the_kind_and_dispatches_it(self) -> None:
        self.assertIn('UNIF_COLOR_KIND = "unif_color"', _PROJECT)
        self.assertIn("build_unif_color_imports", _PROJECT)
        self.assertIn('"project sets the Unif colours more than once"', _PROJECT)

    def test_a_colourless_edit_is_not_asked_for_a_png(self) -> None:
        """Two places assume every non-audio edit pins a file; both were fixed."""
        self.assertIn("UNIF_COLOR_KIND,\n        }:\n            names = []", _PROJECT)
        self.assertIn("UNIVERSAL_FIXED_TEXT_KIND, UNIF_COLOR_KIND}", _PROJECT)

    def test_the_facade_exposes_the_control_surface(self) -> None:
        for member in ("def set_unif_colors", "def clear_unif_colors",
                       "def unif_colors"):
            self.assertIn(member, _FACADE)

    def test_the_gui_has_a_real_control_not_a_card(self) -> None:
        self.assertIn("def _build_colors_page", _STUDIO)
        self.assertIn("QColorDialog", _STUDIO)
        for label in ("Facemask colour", "Turtleneck colour",
                      "Apply to project"):
            self.assertIn(label, _STUDIO)

    def test_the_colours_tab_mounts_the_control(self) -> None:
        mount = _STUDIO.index("if category == ProductCategory.UNIFORMS_EQUIPMENT:")
        window = _STUDIO[mount:mount + 2400]
        self.assertIn("_build_colors_page(section)", window)


if __name__ == "__main__":
    unittest.main()

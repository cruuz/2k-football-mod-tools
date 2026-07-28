"""Every browsable asset must decode, and its export name must be legal.

All Textures shipped listing 3,024 targets that could not be previewed or
exported. Two separate defects, both mine, both found by a modder within a day:

**The preview and export had no decoder.** The browser's list comes from the
catalog, but every preview and Export PNG goes through
``_decode_original``, whose per-kind dispatch had no ``p8_texture`` branch and
raised out of it. So the list populated and selecting anything did nothing.

**The suggested filename was illegal on Windows.** Export PNG proposed
``p8:386:endzone_north_left.png`` and Windows answered "The file name is not
valid.", because ``:`` is reserved there. The old code only replaced ``.``,
which was enough for the dot-separated ids that existed before and for nothing
else. An identifier is not a filename.

The rules are asserted, not the symptoms: every kind the catalog publishes must
have a decoder branch, and no suggested name may contain a character Windows
rejects.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core.nfl2k5_extended_visual_catalog import (  # noqa: E402
    load_nfl2k5_extended_visual_catalog,
)
from mod_editor.gui.studio_qt import _suggested_png_name  # noqa: E402

_IO_SOURCE = (
    _REPO_ROOT / "mod_editor" / "core" / "nfl2k5_extended_visual_io.py"
).read_text(encoding="utf-8")

# Reserved on Windows in any path component.
_ILLEGAL = set('<>:"/\\|?*')


class SuggestedFilenameTests(unittest.TestCase):
    def test_the_exact_name_that_windows_rejected(self) -> None:
        name = _suggested_png_name("p8:386:endzone_north_left")
        self.assertEqual(name, "p8-386-endzone_north_left.png")
        self.assertFalse(_ILLEGAL & set(name))

    def test_no_catalog_asset_suggests_an_illegal_name(self) -> None:
        catalog = load_nfl2k5_extended_visual_catalog()
        for asset in catalog.assets:
            name = _suggested_png_name(asset.asset_id)
            with self.subTest(asset_id=asset.asset_id):
                self.assertFalse(
                    _ILLEGAL & set(name),
                    f"{asset.asset_id} would be rejected by Windows as {name}",
                )
                self.assertTrue(name.endswith(".png"))
                self.assertFalse(name[:-4].endswith((" ", ".")))

    def test_reserved_device_names_are_escaped(self) -> None:
        for reserved in ("CON", "PRN", "AUX", "NUL", "COM1", "LPT9"):
            with self.subTest(reserved=reserved):
                self.assertEqual(_suggested_png_name(reserved), f"_{reserved}.png")

    def test_control_characters_and_empties_are_handled(self) -> None:
        self.assertEqual(_suggested_png_name(""), "asset.png")
        self.assertNotIn("\x01", _suggested_png_name("a\x01b"))

    def test_existing_dot_separated_ids_keep_their_old_shape(self) -> None:
        """The kinds that already worked must not change filename."""
        self.assertEqual(
            _suggested_png_name("scene.texture0002"), "scene-texture0002.png"
        )


class DecoderCoverageTests(unittest.TestCase):
    def test_every_published_kind_has_a_decoder_branch(self) -> None:
        """The defect: a kind in the catalog with no branch in the dispatch."""
        catalog = load_nfl2k5_extended_visual_catalog()
        kinds = {asset.kind for asset in catalog.assets}
        self.assertIn("p8_texture", kinds)
        for kind in sorted(kinds):
            with self.subTest(kind=kind):
                self.assertIn(
                    f'if asset.kind == "{kind}":', _IO_SOURCE,
                    f"{kind} is browsable but has no decoder, so selecting one "
                    "shows nothing and Export PNG fails",
                )

    def test_the_p8_decoder_parses_the_real_descriptor(self) -> None:
        self.assertIn("def _decode_p8_texture", _IO_SOURCE)
        self.assertIn("parse_texture(target.decoded, target.chunk)", _IO_SOURCE)
        self.assertIn("texture_to_rgba(target.decoded, target.chunk, info)", _IO_SOURCE)

    def test_an_unknown_kind_still_fails_closed(self) -> None:
        self.assertIn(
            "Export is not implemented for asset kind", _IO_SOURCE,
            "a kind with no decoder must raise rather than return nothing",
        )


class PreviewFailureVisibilityTests(unittest.TestCase):
    """A preview that cannot be produced must say so, not spin forever."""

    def test_the_preview_task_reports_its_failure(self) -> None:
        source = (
            _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
        ).read_text(encoding="utf-8")
        start = source.index("def _load_visual_preview")
        block = source[start:start + 2200]
        self.assertIn("on_error=failed", block)
        self.assertIn("Preview unavailable", block)
        self.assertIn("set_empty", block)


if __name__ == "__main__":
    unittest.main()

"""A fixed VC-LZ span must fit the art down, not refuse it anonymously.

Reported against Beta 40, on a build with many staged edits::

    The modded XISO could not be built. VC-LZ stream needs more than the
    34416-byte bound
    Nothing was changed in your source XISO.

34,416 is the stored size of a live helmet TXTR. Two things were wrong.

**The importer gave up.** ``quantize_levels_to_vc_lz_bound`` has shipped for a
while and is what the sleeve, digit, all-texture and Crib importers use: it
tries palettes from 256 down to 2 and returns the first that fits the retail
span. Four importers that compress into a bounded span still called the plain
256-entry quantizer and hard-failed -- live helmet, jersey, scorebug, and the
compressed create-team field art. The ladder starts at 256, so art that already
fit is byte-for-byte unchanged; only art that used to fail now steps down.

**The build did not say which edit.** ``build_one_import`` knows the edit's kind
and selector and did not attach either, so the message above names no team, no
slot, and no image in a build carrying dozens of edits.

The three P8 importers that write *uncompressed* fixed spans -- team select
card, player portrait, Crib team photo -- have no VC-LZ bound to overflow and
are deliberately left on the plain quantizer.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE / "tools") not in sys.path:
    sys.path.insert(0, str(WORKSPACE / "tools"))

import nfl2k5_visual_mod_project as backend  # noqa: E402
import nfl_tset_png_import as palette_tools  # noqa: E402
from nfl_txtr import TxtrError  # noqa: E402


#: Importers whose every target compresses into a fixed VC-LZ span. None of
#: them may reach the plain quantizer at all.
ALWAYS_COMPRESSED_IMPORTERS = (
    "nfl_live_helmet_txtr_png_import",
    "nfl_jersey_tset_png_import",
    "nfl_scorebug_png_import",
    "nfl_sleeve_tset_png_import",
    "nfl_live_numbers_nameplate_png_import",
)

#: Create-team field art has both compressed and uncompressed targets, so it
#: keeps the plain quantizer for the uncompressed branch on purpose.
CONDITIONAL_IMPORTERS = ("nfl_create_team_field_art_png_import",)

BOUNDED_IMPORTERS = ALWAYS_COMPRESSED_IMPORTERS + CONDITIONAL_IMPORTERS

#: Importers that write an uncompressed fixed span. Nothing to overflow, so
#: wiring the bounded quantizer here would change output for no reason.
UNCOMPRESSED_IMPORTERS = (
    "nfl_team_select_card_png_import",
    "nfl_player_portrait_png_import",
    "nfl_crib_team_photo_png_import",
)


def _source(module_name: str) -> str:
    return (WORKSPACE / "tools" / f"{module_name}.py").read_text(encoding="utf-8")


class BoundedQuantizerWiringTests(unittest.TestCase):
    def test_every_compressing_importer_uses_the_bounded_quantizer(self) -> None:
        for name in BOUNDED_IMPORTERS:
            with self.subTest(importer=name):
                self.assertIn("quantize_levels_to_vc_lz_bound", _source(name))

    @staticmethod
    def _plain_calls(text: str) -> list[str]:
        return [
            line.strip() for line in text.splitlines()
            if "quantize_levels(" in line
            and "quantize_levels_to_vc_lz_bound" not in line
            and "def quantize_levels" not in line
        ]

    def test_an_always_compressed_importer_never_hard_quantizes_at_256(self) -> None:
        """A leftover plain call is exactly how this bug shipped."""

        for name in ALWAYS_COMPRESSED_IMPORTERS:
            with self.subTest(importer=name):
                self.assertEqual(
                    self._plain_calls(_source(name)),
                    [],
                    f"{name} still calls the unbounded quantizer",
                )

    def test_the_conditional_importer_keeps_one_uncompressed_branch(self) -> None:
        """Its plain call is deliberate, and must stay behind the compressed test."""

        for name in CONDITIONAL_IMPORTERS:
            with self.subTest(importer=name):
                text = _source(name)
                self.assertEqual(len(self._plain_calls(text)), 1)
                bounded_at = text.index("quantize_levels_to_vc_lz_bound(")
                guard_at = text.rindex('if bool(target["compressed"]):', 0, bounded_at)
                plain_at = text.index("palette_tools.quantize_levels(mips)")
                else_at = text.index("    else:", guard_at)
                self.assertLess(guard_at, bounded_at)
                self.assertLess(else_at, plain_at)

    def test_uncompressed_importers_are_left_alone(self) -> None:
        for name in UNCOMPRESSED_IMPORTERS:
            with self.subTest(importer=name):
                text = _source(name)
                self.assertNotIn("rebuild_compressed_chunk_fixed_span", text)
                self.assertNotIn("quantize_levels_to_vc_lz_bound", text)


class BoundedQuantizerBehaviourTests(unittest.TestCase):
    """The ladder's contract, so a switched importer cannot change good output."""

    def _level(self, colours: int) -> palette_tools.MipLevel:
        pixels = bytearray()
        for index in range(64 * 64):
            value = (index * 7) % max(1, colours)
            pixels += bytes((value * 4 % 256, value * 9 % 256, value * 13 % 256, 255))
        return palette_tools.MipLevel(0, 64, 64, bytes(pixels))

    def test_a_generous_bound_returns_the_plain_256_quantization(self) -> None:
        """Art that already fits must be byte-for-byte what it always was."""

        level = self._level(200)
        plain_palette, plain_levels, _ = palette_tools.quantize_levels([level])
        bounded = palette_tools.quantize_levels_to_vc_lz_bound(
            [level],
            lambda palette, levels: b"".join(levels)
            + palette_tools.palette_bytes(palette),
            stream_tag=1,
            offset_bits=12,
            max_encoded_size=1 << 20,
        )
        self.assertEqual(bounded.palette, plain_palette)
        self.assertEqual(bounded.index_levels, plain_levels)
        self.assertEqual(len(bounded.attempts), 1)
        self.assertEqual(bounded.attempts[0]["result"], "fit")

    def test_a_tight_bound_steps_down_instead_of_refusing(self) -> None:
        level = self._level(200)
        generous = palette_tools.quantize_levels_to_vc_lz_bound(
            [level],
            lambda palette, levels: b"".join(levels)
            + palette_tools.palette_bytes(palette),
            stream_tag=1, offset_bits=12, max_encoded_size=1 << 20,
        )
        tight = palette_tools.quantize_levels_to_vc_lz_bound(
            [level],
            lambda palette, levels: b"".join(levels)
            + palette_tools.palette_bytes(palette),
            stream_tag=1, offset_bits=12,
            max_encoded_size=len(generous.compressed) - 512,
        )
        self.assertLess(len(tight.palette), len(generous.palette))
        self.assertLessEqual(len(tight.compressed), len(generous.compressed) - 512)
        self.assertTrue(
            any(item["result"] == "vc_lz_overflow" for item in tight.attempts)
        )

    def test_an_impossible_bound_says_what_to_do(self) -> None:
        with self.assertRaises(TxtrError) as caught:
            palette_tools.quantize_levels_to_vc_lz_bound(
                [self._level(200)],
                lambda palette, levels: b"".join(levels)
                + palette_tools.palette_bytes(palette),
                stream_tag=1, offset_bits=12, max_encoded_size=64,
            )
        message = str(caught.exception)
        self.assertIn("two-color", message)
        self.assertIn("simplify the image", message)


class FailingEditIsNamedTests(unittest.TestCase):
    def test_an_importer_failure_names_its_edit(self) -> None:
        edit = {"kind": "live_helmet", "selector": "live-helmet:NE:home:0:helmet00"}
        with self.assertRaises(backend.ProjectError) as caught:
            with backend._naming_the_failing_edit(edit):
                raise backend.ProjectError(
                    "VC-LZ stream needs more than the 34416-byte bound"
                )
        message = str(caught.exception)
        self.assertIn("live_helmet", message)
        self.assertIn("live-helmet:NE:home:0:helmet00", message)
        self.assertIn("34416-byte bound", message)

    def test_a_non_project_error_is_still_named(self) -> None:
        with self.assertRaises(backend.ProjectError) as caught:
            with backend._naming_the_failing_edit({"kind": "torso"}):
                raise ValueError("decoder blew up")
        self.assertIn("torso", str(caught.exception))
        self.assertIn("decoder blew up", str(caught.exception))

    def test_an_already_named_message_is_not_doubled(self) -> None:
        edit = {"kind": "scorebug", "selector": "down"}
        with self.assertRaises(backend.ProjectError) as caught:
            with backend._naming_the_failing_edit(edit):
                raise backend.ProjectError("scorebug down: already named")
        self.assertEqual(str(caught.exception).count("scorebug down"), 1)

    def test_an_edit_without_a_selector_still_names_its_kind(self) -> None:
        self.assertEqual(backend.describe_edit({"kind": "unif_color"}), "unif_color")
        self.assertEqual(
            backend.describe_edit({"kind": "p8_texture", "selector": "p8:1:2"}),
            "p8_texture p8:1:2",
        )

    def test_the_dispatcher_actually_wraps_the_importer(self) -> None:
        import inspect

        source = inspect.getsource(backend.build_project_imports) \
            if hasattr(backend, "build_project_imports") else _source(
                "nfl2k5_visual_mod_project")
        self.assertIn("_naming_the_failing_edit", source)


if __name__ == "__main__":
    unittest.main()

"""PS2 save lane: identity, source recognition, registry wiring, save writer.

Covers the PlayStation 2 (SLUS-20919) support added to the editors — the game
identity plumbs through, the retail ISO/boot ELF are recognized by hash, the
capability registry exposes the save writer as an editable surface, and the
writer/verifier pair enforces its fail-closed rules. No game data is required.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core.capabilities import CapabilityRegistryLoader
from mod_editor.core.model import GameId
from mod_editor.core.sources import KNOWN_FINGERPRINTS

import nfl2k5_ps2_save as save_lib
import nfl2k5_ps2_save_verify as verify_lib


class Ps2IdentityTests(unittest.TestCase):
    def test_gameid_has_ps2_member_with_display_name(self) -> None:
        self.assertEqual(GameId.NFL2K5_PS2.value, "nfl2k5_ps2")
        self.assertIn("PlayStation 2", GameId.NFL2K5_PS2.display_name)

    def test_ps2_retail_iso_and_elf_are_pinned(self) -> None:
        by_kind = {
            fp.kind: fp for fp in KNOWN_FINGERPRINTS if fp.game == GameId.NFL2K5_PS2
        }
        self.assertEqual(
            by_kind["ps2-iso"].sha256,
            "f1300699ab445ad04b1e27f6e2df87f7a4d1d080d06c7d73499e1be9618a4ebe",
        )
        self.assertEqual(
            by_kind["ps2-elf"].sha256,
            "e8c3ba9a3224d567e3abb50c91e9d6fdd9820138226c05e525f9dbf34a47d8aa",
        )


class Ps2RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CapabilityRegistryLoader().load(check_files=False)

    def test_registry_exposes_the_ps2_game(self) -> None:
        self.assertIn(GameId.NFL2K5_PS2, self.registry.game_metadata)

    def test_save_writer_is_an_editable_surface(self) -> None:
        ps2 = [c for c in self.registry.capabilities if c.game == GameId.NFL2K5_PS2]
        self.assertTrue(ps2, "PS2 must expose at least one capability")
        writers = [c for c in ps2 if c.raw["backend"]["operation"] == "write"]
        self.assertTrue(writers, "the PS2 save writer must be registered")
        for capability in writers:
            # This writer takes field edits, not a replacement file, so it is
            # exposed as an editable surface without a file-drop affordance.
            self.assertEqual(capability.classification.value, "offline-writer-proved")
            self.assertEqual(capability.raw["gui"]["mode"], "edit")
            self.assertIs(capability.raw["gui"]["expose"], True)
            self.assertEqual(capability.surface, "saves")


class Ps2SaveWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.save = save_lib._synthetic_save()

    def test_extra_is_the_crc32_of_the_payload(self) -> None:
        self.assertTrue(self.save.crc_is_valid())
        self.assertEqual(
            self.save.stored_crc, zlib.crc32(self.save.payload) & 0xFFFFFFFF
        )

    def test_edit_requires_reseal_and_then_verifies(self) -> None:
        save_lib.set_player_name(self.save, 0, "first", "Delta")
        self.assertFalse(self.save.crc_is_valid(), "stale EXTRA must not validate")
        self.save.reseal()
        self.assertTrue(self.save.crc_is_valid())

    def test_oversized_name_is_refused(self) -> None:
        with self.assertRaises(save_lib.SaveError):
            save_lib.set_player_name(self.save, 0, "first", "FarTooLongForThisSlot")

    def test_arena_tables_survive_an_edit(self) -> None:
        before = save_lib.parse_roster(self.save)["tables"]
        save_lib.set_player_name(self.save, 0, "first", "Delta")
        self.save.reseal()
        after = save_lib.parse_roster(self.save)["tables"]
        self.assertEqual(
            {k: v["count"] for k, v in before.items()},
            {k: v["count"] for k, v in after.items()},
        )

    def test_psu_round_trip_preserves_every_file(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as work:
            out = Path(work) / "save.psu"
            save_lib.write_psu(self.save, out)
            again = save_lib.read_psu(out)
            self.assertEqual(again.directory, self.save.directory)
            self.assertEqual(again.files, self.save.files)


class Ps2SaveVerifierTests(unittest.TestCase):
    def test_verifier_selftest_passes(self) -> None:
        self.assertEqual(verify_lib.selftest(), 0)

    def test_undeclared_edit_is_rejected(self) -> None:
        original = save_lib._synthetic_save()
        edited = save_lib._synthetic_save()
        declared = save_lib.set_player_name(edited, 0, "first", "Delta")
        save_lib.set_player_name(edited, 1, "first", "Echo")  # not declared
        edited.reseal()
        with self.assertRaises(verify_lib.VerifyError):
            verify_lib.verify(original, edited, [declared])


if __name__ == "__main__":
    unittest.main()

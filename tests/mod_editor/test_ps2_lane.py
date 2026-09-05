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
        save_writers = [c for c in writers if c.surface == "saves"]
        self.assertEqual(
            [c.raw["id"] for c in save_writers], ["nfl2k5ps2.saves.roster_name_writer"]
        )
        for capability in save_writers:
            # This writer takes field edits, not a replacement file, so it is
            # exposed as an editable surface without a file-drop affordance.
            self.assertEqual(capability.classification.value, "offline-writer-proved")
            self.assertEqual(capability.raw["gui"]["mode"], "edit")
            self.assertIs(capability.raw["gui"]["expose"], True)

    def test_disc_writers_are_proved_offline_and_surface_in_the_disc_studio(self) -> None:
        # The six on-disc PS2 writers (text, playbooks, colours, roster, stadium
        # positions, AUDO sounds) are bounded writers with independent verifiers
        # and a real-disc trial each, so they are offline-writer-proved -- and
        # the registry binds that class to an edit surface. None has a window
        # yet, so every one stays hidden and says why.
        disc_writers = [
            c for c in self.registry.capabilities
            if c.game == GameId.NFL2K5_PS2
            and c.raw["backend"]["operation"] == "write"
            and c.surface != "saves"
        ]
        self.assertEqual(len(disc_writers), 6)
        heard = {"nfl2k5ps2.audio.audo_exact_slot_replace"}
        for capability in disc_writers:
            self.assertEqual(capability.raw["gui"]["mode"], "edit")
            # Each is a tab of the PS2 Disc Studio; stadium is off by default
            # because its steps take tens of minutes and one scene is proved.
            self.assertIs(capability.raw["gui"]["expose"], True)
            self.assertIs(capability.raw["gui"]["default_enabled"],
                          capability.raw["id"] != "nfl2k5ps2.stadiums.position_lanes")
            self.assertIn("PS2 NFL 2K5 Studio", capability.raw["gui"]["reason"])
            self.assertTrue(capability.raw["validation_command"])
            if capability.raw["id"] in heard:
                # One AUDO slot was heard on a cold boot (menu-appear_01); the
                # row is runtime-proved for that recorded selector only.
                self.assertEqual(capability.classification.value, "runtime-proved")
                self.assertEqual(capability.raw["runtime"]["status"], "visible-proved")
                self.assertTrue(capability.raw["runtime"]["evidence"])
            else:
                self.assertEqual(capability.classification.value, "offline-writer-proved")
                self.assertEqual(capability.raw["runtime"]["status"], "not-tested")


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


class OutputReservationTests(unittest.TestCase):
    """No write may land on an input or on an existing file, on either lane."""

    def setUp(self) -> None:
        import tempfile

        self._temp = tempfile.TemporaryDirectory(prefix="ps2-output-")
        self.root = Path(self._temp.name)
        self.save = save_lib._synthetic_save()
        self.source = self.root / "source.psu"
        save_lib.write_psu(self.save, self.source)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_writing_onto_an_existing_file_is_refused(self) -> None:
        victim = self.root / "victim.bin"
        victim.write_bytes(b"PRECIOUS USER DATA")
        with self.assertRaisesRegex(save_lib.SaveError, "Refusing to overwrite"):
            save_lib.write_psu(self.save, victim)
        self.assertEqual(victim.read_bytes(), b"PRECIOUS USER DATA")

    def test_writing_onto_a_declared_input_is_refused(self) -> None:
        before = self.source.read_bytes()
        with self.assertRaisesRegex(save_lib.SaveError, "input file"):
            save_lib.write_psu(self.save, self.source, forbid=(self.source,))
        self.assertEqual(self.source.read_bytes(), before)

    def test_a_second_input_is_protected_even_when_it_is_not_the_base(self) -> None:
        # --into-card wins the base-card choice, so --input must still be
        # named as forbidden or it goes unprotected.
        other = self.root / "other.psu"
        save_lib.write_psu(self.save, other)
        before = other.read_bytes()
        with self.assertRaisesRegex(save_lib.SaveError, "input file"):
            save_lib.write_psu(self.save, other, forbid=(self.source, other))
        self.assertEqual(other.read_bytes(), before)

    def test_a_fresh_destination_still_writes(self) -> None:
        fresh = self.root / "fresh.psu"
        save_lib.write_psu(self.save, fresh, forbid=(self.source,))
        self.assertEqual(save_lib.read_psu(fresh).files, self.save.files)

    def test_a_failed_write_leaves_no_stray_output(self) -> None:
        # A reservation that fails mid-write must unlink the path it created,
        # rather than leaving a zero-length or half-written file behind.
        target = self.root / "aborted.psu"
        real_commit = save_lib._commit_reserved

        def explode(path, reservation, data):
            raise save_lib.SaveError("simulated disk failure")

        save_lib._commit_reserved = explode
        try:
            with self.assertRaisesRegex(save_lib.SaveError, "simulated disk failure"):
                save_lib.write_psu(self.save, target)
        finally:
            save_lib._commit_reserved = real_commit
        self.assertFalse(target.exists(), "a failed write left a stray file")


if __name__ == "__main__":
    unittest.main()

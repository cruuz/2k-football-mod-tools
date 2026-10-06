"""Commentary follows the actual jersey; exact surname reuse and field-scoped native repair."""
from pathlib import Path
import os
import struct
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests" / "mod_editor", ROOT / "tools"):
    sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_roster_records as rr
from test_nfl2k5_roster_records import synthetic_body, SAMPLE
from nfl2k5_team_2026_roster import pbp_for


class CommentaryNumbersTests(unittest.TestCase):
    def fixture(self):
        body = bytearray(synthetic_body())
        doc = rr.load_body(bytes(body))
        for p in doc.players:
            struct.pack_into("<H", body, p.offset + 4, 9100 if p.teams else 0)
        return bytes(body)

    def test_repairs_all_teams_free_agents_and_named_draft_players(self):
        before = self.fixture()
        after, receipt = rr.repair_commentary_body(before)
        doc = rr.load_body(after)
        for p in doc.players:
            bank = rr.recorded_surname_ids().get(rr.commentary_surname(p.last))
            self.assertEqual(p.record.get("pbp_id"), bank or 9000 + p.record.get("jersey"))
        self.assertEqual(receipt["players_changed"], len(SAMPLE))
        permitted = {p.offset + n for p in doc.players for n in (4, 5)}
        self.assertTrue(all(a == b or i in permitted for i, (a, b) in enumerate(zip(before, after))))
        self.assertEqual(rr.repair_commentary_body(after)[0], after)
        self.assertEqual(rr.repair_commentary_body(after)[1]["players_changed"], 0)

    def test_nonidentity_edits_preserve_scope_and_build_replay_repairs_commentary(self):
        doc = rr.load_body(self.fixture())
        for p in doc.players:
            p.record.set("height", p.record.get("height") + 1)
        before = bytearray(doc.original)
        for p in doc.players:
            before[p.offset:p.offset + rr.PLAYER_SIZE] = p.record.encode()
        before = bytes(before)
        expected, _ = rr.repair_commentary_body(before)
        self.assertEqual(doc.to_body(), before)
        edits = [{"pool": p.pool, "index": p.index, "fields": {"height": p.record.get("height")}}
                 for p in doc.players]
        replay, _ = rr.apply_body(self.fixture(), {"schema": rr.EDITS_SCHEMA, "edits": edits})
        self.assertEqual(replay, before)
        self.assertEqual(rr.repair_commentary_body(replay)[0], expected)

    def test_unedited_codec_is_lossless(self):
        before = self.fixture()
        self.assertEqual(rr.load_body(before).to_body(), before)

    def test_field_scoped_writer_defers_commentary_without_losing_final_repair(self):
        before = self.fixture()
        doc = rr.load_body(before)
        player = doc.players[6]
        player.record.set("photo_id", 1234)
        scoped = doc.to_body(normalise_commentary=False)
        permitted = {player.offset + 6, player.offset + 7}
        self.assertTrue(all(a == b or i in permitted
                            for i, (a, b) in enumerate(zip(before, scoped))))
        self.assertEqual(rr.load_body(scoped).players[6].record.get("pbp_id"), 0)
        final, receipt = rr.repair_commentary_body(scoped)
        self.assertEqual(receipt["players_changed"], len(SAMPLE))
        self.assertEqual(rr.load_body(final).players[6].record.get("photo_id"), 1234)
        self.assertEqual(rr.load_body(final).players[6].record.get("pbp_id"), 9024)
        ordinary = doc.to_body()
        self.assertEqual(ordinary, scoped)
        self.assertEqual(rr.repair_commentary_body(ordinary)[0], final)

    def test_field_scoped_csv_defers_preview_apply_and_renumbering_until_full_save(self):
        doc = rr.load_body(self.fixture())
        player = doc.players[6]
        player.record.set("pbp_id", 9003)
        before = doc.to_body(normalise_commentary=False)
        doc = rr.load_body(before)
        sheet = f"pool,index,jersey\n{player.pool},{player.index},7\n"
        preview = rr.preview_csv(doc, sheet, normalise_commentary=False)
        self.assertEqual(rr.load_body(preview.after).players[6].record.get("pbp_id"), 9003)
        self.assertEqual(doc.to_body(normalise_commentary=False), before)
        rr.apply_csv_preview(doc, preview)
        scoped = doc.to_body(normalise_commentary=False)
        self.assertEqual(scoped, preview.after)
        spec = rr.FIELD_BY_NAME["jersey"]
        allowed = set(range(player.offset + spec.offset, player.offset + spec.offset + spec.size))
        self.assertTrue(all(a == b or i in allowed for i, (a,b) in enumerate(zip(before,scoped))))
        final, _ = rr.repair_commentary_body(doc.to_body())
        self.assertEqual(rr.load_body(final).players[6].record.get("pbp_id"), 9007)
        ordinary = rr.load_body(before)
        rr.import_csv(ordinary, sheet)
        self.assertEqual(ordinary.players[6].record.get("pbp_id"), 9007)

    @unittest.skipUnless(os.environ.get("B765_F1_V04_BODY"), "optional pinned v0.4 roster body")
    def test_actual_free_agent_native_writer_keeps_its_scope_and_composes_with_commentary(self):
        from tools.b765 import f1_repair
        before = Path(os.environ["B765_F1_V04_BODY"]).read_bytes()
        self.assertEqual(f1_repair.sha(before), f1_repair.BODY_BEFORE)
        added, receipt = f1_repair.repair_body(before)
        self.assertEqual(f1_repair.sha(added), f1_repair.BODY_AFTER)
        self.assertTrue(receipt["scope"]["outside_scope_identical"])
        final, _ = rr.repair_commentary_body(added)
        replay, _ = f1_repair.repair_body(
            final, approved_input_sha256=(f1_repair.sha(final),))
        self.assertEqual(replay, final)
        commentary_first, _ = rr.repair_commentary_body(before)
        reverse, _ = f1_repair.repair_body(
            commentary_first, approved_input_sha256=(f1_repair.sha(commentary_first),))
        self.assertEqual(rr.repair_commentary_body(reverse)[0], final)

    def test_actual_disc_writer_repairs_untouched_legacy_records_in_build_inputs(self):
        before = self.fixture()
        resource = b"ROST" + bytes(28) + before
        class Archive:
            entries = [None] * 5 + [SimpleNamespace(size=len(resource), virtual_offset=4096)]
            stored = resource
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, offset, size): return self.stored
            def write(self, offset, data):
                self.stored = data
                return len(data)
        archive = Archive()
        with patch.object(rr, "_outer_image", return_value=lambda *a, **kw: archive), \
             patch("mod_editor.core.nfl2k5_college_refs.verify_table_edit"):
            result = rr.apply("private-copy", {"schema": rr.EDITS_SCHEMA, "edits": []})
        self.assertEqual(archive.stored[32:], rr.repair_commentary_body(before)[0])
        self.assertEqual(result["commentary"]["players_changed"], len(SAMPLE))

    def test_native_pack_repair_is_composable_and_hash_guard_refuses_foreign_inputs(self):
        from tools.b765 import c1_repair as native
        import tempfile
        before = self.fixture()
        pack = bytearray(native.ROSTER_PACK_OFFSET + rr.RESOURCE_SIZE + 32)
        struct.pack_into("<3I", pack, 0, 6, 0, 1)
        struct.pack_into("<3I", pack, 0x9C + 5 * 12, 123, rr.RESOURCE_SIZE,
                         native.ROSTER_PACK_OFFSET // 0x800)
        pack[native.ROSTER_PACK_OFFSET:native.ROSTER_PACK_OFFSET + 32] = b"ROST" + bytes(28)
        pack[native.ROSTER_PACK_OFFSET + 32:native.ROSTER_PACK_OFFSET + rr.RESOURCE_SIZE] = before
        pack[-1] = 0xAB  # another job's byte, beyond the roster
        fixed, receipt = native.repair_pack_zero(bytes(pack))
        self.assertEqual(fixed[-1], 0xAB)
        self.assertTrue(receipt["outside_scope_identical"])
        self.assertEqual(native.repair_pack_zero(fixed)[0], fixed)
        corrupt = bytearray(fixed)
        corrupt[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "outside declared scope"):
            native.scope_receipt(bytes(pack), bytes(corrupt),
                                 [(s["offset"], s["size"]) for s in receipt["scope"]])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "foreign"
            path.write_bytes(b"unexpected")
            with self.assertRaisesRegex(ValueError, "unexpected input hash"):
                native.checked_input(path, None, (native.V04_PACK_SHA256, native.FIXED_PACK_SHA256))

    def test_real_zero_is_zero_and_never_double_zero(self):
        p = rr.load_body(self.fixture()).players[0]
        p.record.set("jersey", 0)
        p.last = "Mahomes"
        rr.normalise_player_commentary(p)
        self.assertEqual(p.record.get("pbp_id"), 9000)
        for number in range(100):
            self.assertEqual(pbp_for("Mahomes", number, {})[0], 9000 + number)

    def test_exact_surname_suffix_and_punctuation_boundaries(self):
        bank = rr.recorded_surname_ids()
        self.assertEqual(pbp_for("Jefferson III", 17, bank)[0], bank["jefferson"])
        self.assertEqual(pbp_for("Harrison Jr.", 18, bank)[0], bank["harrison"])
        self.assertEqual(pbp_for("Mc-Bride", 85, bank)[0], 9085)
        self.assertEqual(pbp_for("Rodger", 8, bank)[0], 9008)
        self.assertEqual(pbp_for("Mascarenas-Arnold", 52, {"mascarenas": 9450})[0], 9052)
        self.assertEqual(pbp_for("Zdyrko", 42, bank)[0], 9042)
        self.assertEqual(pbp_for("Navarro", 42, bank)[0], 9042)
        self.assertEqual(len(bank), 483)

    def test_ambiguous_surname_bank_uses_number(self):
        with patch("mod_editor.core.nfl2k5_prospect_names.RETAIL_LASTS", ("Jones", "Jones III")):
            bank = rr.recorded_surname_ids()
        self.assertNotIn("jones", bank)
        self.assertEqual(pbp_for("Jones", 42, bank)[0], 9042)

    def test_existing_name_choice_survives_and_numeric_cue_tracks_renumbering(self):
        doc = rr.load_body(self.fixture())
        player = doc.players[0]
        player.record.set("pbp_id", 3593)
        player.record.set("jersey", 3)
        self.assertFalse(rr.normalise_player_commentary(player))
        self.assertEqual(player.record.get("pbp_id"), 3593)
        player.record.set("pbp_id", 9018)
        player.record.set("jersey", 8)
        self.assertEqual(player.record.get("pbp_id"), 9008)
        player.record.values["jersey"] = 15  # imported raw record values use the final writer too
        self.assertTrue(rr.normalise_player_commentary(player, sync_numbers=True))
        self.assertEqual(player.record.get("pbp_id"), 9015)

    def test_blank_created_slots_and_templates_are_preserved(self):
        doc = rr.load_body(self.fixture())
        p = doc.players[0]
        p.first = p.last = ""
        p.record.set("pbp_id", 0)
        self.assertFalse(rr.normalise_player_commentary(p))
        p.first = p.last = "****************"
        self.assertFalse(rr.normalise_player_commentary(p))
        self.assertEqual(p.record.get("pbp_id"), 0)

    def test_absent_retail_name_selection_uses_exact_surname_or_current_number(self):
        p = rr.load_body(self.fixture()).players[0]
        p.last = "Robinson"
        p.record.set("pbp_id", 5221)  # Terrence Robinson's retail record has no recorded cue.
        self.assertTrue(rr.normalise_player_commentary(p))
        self.assertEqual(p.record.get("pbp_id"), rr.recorded_surname_ids()["robinson"])
        p.last = "Humphrey"
        p.record.set("pbp_id", 3787)
        self.assertTrue(rr.normalise_player_commentary(p))
        self.assertEqual(p.record.get("pbp_id"), 9018)

    def test_free_agent_addition_and_other_owners_fields_compose(self):
        body = bytearray(self.fixture())
        doc = rr.load_body(bytes(body))
        p = doc.players[6]
        body[p.offset + 6:p.offset + 8] = b"\x34\x12"  # f1 photo owner
        body[p.offset + 0x52] = 0x40  # depth/other owner
        body[p.offset + 0x53] = 0x81  # ability/star owner
        before = bytes(body)
        after, _ = rr.repair_commentary_body(before)
        self.assertEqual(after[p.offset + 6:p.offset + 8], b"\x34\x12")
        self.assertEqual(after[p.offset + 0x52:p.offset + 0x54], b"\x40\x81")
        self.assertEqual(rr.load_body(after).players[6].record.get("pbp_id"), 9024)

    def test_invalid_number_refuses(self):
        for invalid in (-1, 100, True, "15"):
            with self.assertRaises(rr.RosterRecordError):
                rr.number_commentary_id(invalid)


if __name__ == "__main__":
    unittest.main()

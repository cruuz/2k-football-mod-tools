"""Missing historical clubs, explicit evidence, sparse pools and signed CLI output."""
import datetime as dt
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import nfl2k5_franchise_upgrade as up
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_franchise_upgrade_io as service
from mod_editor.core import nfl2k5_save_rost as sr
from tests.mod_editor.test_nfl2k5_team_history import synthetic_body, entry
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_save_v0
from tests.mod_editor.test_franchise_upgrade import signed_folder


def fixture():
    players = [{"first": "Test", "last": "Player", "birth": dt.date(2000, 1, 2),
                "position": 0, "count": 2,
                "stream": [entry(1, 0, 17), entry(1, 87, 31, end=True)]},
               {"first": "Other", "last": "Player", "birth": dt.date(2000, 2, 3),
                "position": 3, "count": 2, "stream": [entry(1, 0, 12, end=True)]}]
    disc = bytearray(synthetic_body(players))
    struct.pack_into("<i", disc, 0x14, 0x2D)
    disc = bytes(disc)
    players[0]["count"] = 3
    players[0]["stream"] = [entry(1, 0, 17), entry(2, 0, 16), entry(2, 8, 321),
                            entry(2, 87, 7, deleted=True), entry(3, 0, 1, post=True, end=True)]
    players[1]["count"] = 3
    body = synthetic_body(players)
    suffix = synthetic_franchise(year_field=1)[0x91320:]
    return synthetic_save_v0(body, suffix=suffix), disc


def evidence(payload):
    doc = sr.decode(payload, base_year=2026)
    player = doc.players[0]
    return {"schema": up.TEAM_EVIDENCE_SCHEMA,
            "sources": {"test": {"description": "Synthetic season club record", "sha256": "a" * 64}},
            "rows": [{"first": player.first, "last": player.last,
                      "birth_date": str(player.record.birth_date), "season": 2026, "team": "BUF",
                      "stats_sha256": up.season_stats_sha256(doc.history_words[player.key], 2),
                      "source": "test"}]}


class TeamHistoryUpgradeTests(unittest.TestCase):
    def test_wrapped_event_ring_reads_past_cursor_and_skips_cleared_slots(self):
        payload = bytearray(synthetic_franchise())
        office = fs.FranchiseSave(payload).front_office_block
        struct.pack_into("<I", payload, office + fs.F_LEDGER_CURSOR, 1)
        # A draft survives beyond the cursor. A cleared release retains its
        # old reference, but the native iterator must not expose it as active.
        struct.pack_into("<IHHB", payload, office + fs.F_LEDGER + 599 * 12,
                         0x80000004 | (6 << 5) | (31 << 21), 0, 0, 30)
        struct.pack_into("<IHHB", payload, office + fs.F_LEDGER + 598 * 12,
                         0x80000000, 0, 0, 30)
        rows = fs.FranchiseSave(payload).ledger()
        self.assertEqual([r["index"] for r in rows], [0, 599])
        self.assertEqual((rows[1]["kind"], rows[1]["argument_1"], rows[1]["argument_2"]), (4, 6, 31))
        self.assertTrue(rows[1]["last_in_group"])

    def test_draft_signing_and_no_visible_move_do_not_prove_a_completed_season(self):
        before, disc = fixture()
        for kind in (1, 4, 7, 8, 9, 10, 12):
            payload = bytearray(before)
            office = fs.FranchiseSave(payload).front_office_block
            payload[office + fs.F_LEDGER:office + fs.F_LEDGER + 600 * 12] = bytes(600 * 12)
            struct.pack_into("<I", payload, office + fs.F_LEDGER_CURSOR, 1)
            struct.pack_into("<IHHB", payload, office + fs.F_LEDGER + 599 * 12,
                             0x80000000 | kind, 0, 0, 30)
            with self.subTest(kind=kind):
                after, receipt = up.upgrade_team_history(bytes(payload), disc)
                self.assertEqual([c["season"] for c in receipt["changes"]], [2025])
                row = next(r for r in receipt["unresolved"] if r["season"] == 2026)
                self.assertEqual(row["native_event_slots"], [599])
                self.assertEqual(row["reason"], "retained_events_without_season_coverage")
                self.assertFalse(receipt["native_evidence"]["full_season_coverage_proved"])
                self.assertEqual(up.upgrade_team_history(after, disc)[0], after)

    def test_empty_log_is_not_evidence_of_an_unchanged_season_club(self):
        before, disc = fixture()
        payload = bytearray(before)
        office = fs.FranchiseSave(payload).front_office_block
        payload[office + fs.F_LEDGER:office + fs.F_LEDGER + 600 * 12] = bytes(600 * 12)
        _, receipt = up.upgrade_team_history(bytes(payload), disc)
        self.assertEqual(receipt["unresolved_by_reason"], {
            "no_retained_player_event_or_season_coverage": 1,
            "pre_franchise_source_missing_or_mismatched": 1})

    def test_disc_restores_imported_season_but_never_infers_played_season(self):
        before, disc = fixture()
        after, receipt = up.upgrade_team_history(before, disc)
        self.assertEqual([(c["season"], c["after"]) for c in receipt["changes"]], [(2025, "TEN")])
        self.assertEqual({r["season"] for r in receipt["unresolved"]}, {2025, 2026})
        self.assertTrue(receipt["outside_declared_fields_identical"])
        a, b = sr.decode(before), sr.decode(after)
        self.assertEqual(b.history_words[a.players[0].key][1:], a.history_words[a.players[0].key])
        self.assertEqual(b.history_words[a.players[1].key], a.history_words[a.players[1].key])
        self.assertEqual(receipt["used_after"], receipt["used_before"] + 1)
        self.assertEqual(up.upgrade_team_history(after, disc)[0], after)

    def test_evidenced_season_is_added_once_without_changing_any_existing_word(self):
        before, disc = fixture()
        claims = evidence(before)
        after, receipt = up.upgrade_team_history(before, disc, claims)
        self.assertEqual([(c["season"], c["after"]) for c in receipt["changes"]], [(2025, "TEN"), (2026, "BUF")])
        a, b = sr.decode(before), sr.decode(after)
        self.assertEqual(b.history_words[a.players[0].key][2:], a.history_words[a.players[0].key])
        again, replay = up.upgrade_team_history(after, disc, claims)
        self.assertEqual(after, again)
        self.assertEqual(replay["changed_bytes"], 0)
        self.assertEqual(replay["changes"], [])

    def test_identity_counters_source_team_and_season_must_match(self):
        before, disc = fixture()
        for field, value, message in [("last", "SomeoneElse", "identity"),
                                       ("birth_date", "2001-01-02", "identity"),
                                       ("stats_sha256", "0" * 64, "counters"),
                                       ("source", "missing", "hashed source"),
                                       ("team", "FA", "club"),
                                       ("season", 2027, "completed")]:
            claims = evidence(before)
            claims["rows"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(up.UpgradeRefused, message):
                up.upgrade_team_history(before, disc, claims)
        claims = evidence(before)
        claims["rows"] *= 2
        with self.assertRaisesRegex(up.UpgradeRefused, "duplicate"):
            up.upgrade_team_history(before, disc, claims)

    def test_conflicting_recorded_club_refuses_and_existing_disc_conflict_is_preserved(self):
        before, disc = fixture()
        after, _ = up.upgrade_team_history(before, disc, evidence(before))
        claims = evidence(before)
        claims["rows"][0]["team"] = "TEN"
        with self.assertRaisesRegex(up.UpgradeRefused, "conflicts"):
            up.upgrade_team_history(after, disc, claims)
        changed_disc = bytearray(disc)
        source = sr.decode(disc, preamble=0)
        struct.pack_into("<I", changed_disc, source.history_offsets[source.players[0].key] + 4,
                         entry(1, 87, 1, end=True))
        self.assertEqual(up.upgrade_team_history(after, bytes(changed_disc))[0], after)

    def test_recycled_identity_cannot_inherit_disc_history(self):
        before, disc = fixture()
        doc = sr.decode(before, base_year=2026)
        doc.edit_player("primary", 0, {"birth_day": 9})
        changed = doc.to_bytes()
        self.assertEqual(up.upgrade_team_history(changed, disc)[0], changed)

    def test_disc_with_different_season_counters_cannot_supply_a_club(self):
        before, disc = fixture()
        doc = sr.decode(disc, preamble=0)
        changed = bytearray(disc)
        struct.pack_into("<I", changed, doc.history_offsets[doc.players[0].key], entry(1, 0, 12))
        self.assertEqual(up.upgrade_team_history(before, bytes(changed))[0], before)

    def test_malformed_evidence_refuses(self):
        before, disc = fixture()
        for claims in ([], {}, {"schema": up.TEAM_EVIDENCE_SCHEMA, "rows": [{}]},
                       {"schema": up.TEAM_EVIDENCE_SCHEMA, "rows": None}):
            with self.subTest(claims=claims), self.assertRaises(up.UpgradeRefused):
                up.upgrade_team_history(before, disc, claims)

    def test_native_holes_and_shared_tail_stay_intact(self):
        before, disc = fixture()
        doc = sr.decode(before, base_year=2026)
        changed = bytearray(before)
        pointer = doc.players[1].offset + 0x2C
        target = doc.history_offsets[doc.players[0].key] + 4
        struct.pack_into("<i", changed, pointer, target - pointer + 1)
        changed = bytes(changed)
        after, _ = up.upgrade_team_history(changed, disc, evidence(changed))
        a, b = sr.decode(changed), sr.decode(after)
        self.assertEqual(b.history_words[a.players[1].key], a.history_words[a.players[1].key])
        self.assertEqual(after[a.pool:a.pool + 4*a.pool_used], changed[a.pool:a.pool + 4*a.pool_used])

    def test_unused_native_slots_can_contain_stale_words(self):
        before, disc = fixture()
        doc = sr.decode(before)
        changed = bytearray(before)
        changed[doc.pool + doc.pool_used * 4] = 1
        after, receipt = up.upgrade_team_history(bytes(changed), disc)
        self.assertEqual(len(receipt["changes"]), 1)
        self.assertEqual(after, up.upgrade_team_history(before, disc)[0])

    def test_capacity_refuses_before_any_output(self):
        before, disc = fixture()
        doc = sr.decode(before)
        changed = bytearray(before)
        struct.pack_into("<I", changed, doc.layout.root + 0x40, doc.pool_capacity)
        with self.assertRaisesRegex(up.UpgradeRefused, "capacity"):
            up.upgrade_team_history(bytes(changed), disc)

    def test_other_table_in_unused_pool_refuses(self):
        before, disc = fixture()
        doc = sr.decode(before)
        changed = bytearray(before)
        target = doc.pool + doc.pool_used * 4
        field = doc.layout.root + 0x3C  # free-agent table pointer
        struct.pack_into("<Ii", changed, field - 4, 1, target - field + 1)
        struct.pack_into("<i", changed, target, doc.players[0].offset - target + 1)
        with self.assertRaisesRegex(up.UpgradeRefused, "overlap a roster table"):
            up.upgrade_team_history(bytes(changed), disc)

    def test_folded_games_do_not_create_a_season_or_team(self):
        before, disc = fixture()
        doc = sr.decode(before)
        changed = bytearray(before)
        at = doc.history_offsets[doc.players[0].key]
        struct.pack_into("<I", changed, at, entry(1, 0, 17, folded=True))
        after, receipt = up.upgrade_team_history(bytes(changed), disc)
        self.assertEqual(after, bytes(changed))
        self.assertEqual(receipt["changes"], [])

    def test_signed_service_and_cli_share_the_same_output(self):
        from tools import nfl2k5_franchise_upgrade as cli
        before, body = fixture()
        expected, _ = up.upgrade_team_history(before, body, evidence(before))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = signed_folder(root / "source", before)
            disc = root / "disc.iso"
            disc.write_bytes(b"synthetic disc")
            claims = root / "evidence.json"
            claims.write_text(json.dumps(evidence(before)), newline="\n")
            output = root / "output"
            receipt = root / "receipt.json"
            with patch.object(service, "load_disc", return_value=(body, {})), \
                 patch.object(up, "validate_save", return_value={"findings": []}):
                self.assertEqual(cli.main(["team-history", "--input", str(source), "--disc", str(disc),
                                          "--output", str(output), "--receipt", str(receipt),
                                          "--team-history", str(claims)]), 0)
            self.assertEqual(service.load_container(output).savegame, expected)
            self.assertEqual(service.load_container(source).savegame, before)
            self.assertEqual(json.loads(receipt.read_text())["changed_fields"], 2)


if __name__ == "__main__":
    unittest.main()

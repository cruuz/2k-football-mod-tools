"""Portable full-capacity FA writer checks; fixtures contain no retail bytes."""
from __future__ import annotations

import copy
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests/mod_editor"), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_free_agents as fa
from test_nfl2k5_roster_records import (
    synthetic_body, PLAYERS_OFF, FREE_AGENTS_OFF, NAME_STRINGS_OFF, TEAMS_OFF,
)

ACTIVE_POSITIONS = set(range(17)) - {10}
# Non-art identity/position metadata from the dated v0.4 FA census. The
# synthetic fixture uses these eight QB positions to test the combined quota.
EXISTING_QBS = {
    1697: ("Bailey", "Zappe"), 1711: ("Adrian", "Martinez"),
    1779: ("Jake", "Haener"), 1802: ("Austin", "Reed"),
    1843: ("Cam", "Miller"), 1895: ("Connor", "Bazelak"),
    1907: ("Hunter", "Dekkers"), 1927: ("Mark", "Gronowski"),
}


def fixture(data):
    """Use the existing synthetic roster's layout with all native-sized tables."""
    body = bytearray(synthetic_body())

    def rel(field, target):
        struct.pack_into("<i", body, field, target - field + 1)

    base = rr.decode_record(body[PLAYERS_OFF:PLAYERS_OFF + rr.PLAYER_SIZE])
    old = {(r.get("pool", "primary"), r["index"]): r for r in data["existing"]}
    body[PLAYERS_OFF:FREE_AGENTS_OFF] = bytes(FREE_AGENTS_OFF - PLAYERS_OFF)
    struct.pack_into("<I", body, rr.POOL_FIELDS["primary"][0], 2479)
    struct.pack_into("<I", body, rr.POOL_FIELDS["secondary"][0], 68)
    rel(rr.POOL_FIELDS["secondary"][1], PLAYERS_OFF + 2479 * rr.PLAYER_SIZE)
    cursor = NAME_STRINGS_OFF
    shared = {}

    def name(text, separate=False):
        nonlocal cursor
        if not separate and text in shared:
            return shared[text]
        offset = cursor
        raw = text.encode("utf-16-le") + b"\0\0"
        body[offset:offset + len(raw)] = raw
        cursor += len(raw)
        if not separate:
            shared[text] = offset
        return offset

    for number in range(2547):
        pool, index = ("primary", number) if number < 2479 else ("secondary", number - 2479)
        offset = PLAYERS_OFF + number * rr.PLAYER_SIZE
        values = dict(base)
        values.update(player_type=4, unknown_09=0xA5, unknown_0d=0x6B, unknown_1f_high=3,
                      pbp_id=37, photo_id=509, position=0, contract_value=432, star_tag=1)
        for key in rr.POINTER_FIELDS:
            values[key] = 0
        row = old.get((pool, index))
        first, last = (row["first"], row["last"]) if row else ("Fixed", "Player")
        trailing = pool == "primary" and fa.FIRST_TRAILING_SLOT <= index <= fa.LAST_TRAILING_SLOT
        if trailing:
            first = last = "****************"
            values["player_type"] = 1
        elif pool == "primary" and 1944 <= index < 2324:
            values["player_type"] = 0
        if row:
            label = row.get("position")
            code = row.get("position_code", row.get("fields", {}).get("position"))
            if code is None and label:
                code = next((i for i in ACTIVE_POSITIONS if rr.position_name(i, "one_pool") == label), 0)
            if code is None:
                code = 0 if index in EXISTING_QBS else sorted(ACTIVE_POSITIONS - {0})[index % 15]
            values["position"] = code
        body[offset:offset + rr.PLAYER_SIZE] = rr.encode_record(values)
        rel(offset + 0x10, name(first, trailing))
        rel(offset + 0x14, name(last, trailing))
    assert cursor < 0x8B7D0, "synthetic player names exceed the original layout"
    # Keep team strings separate from player names and provide two legal clubs.
    team_cursor = 0x78F00
    owned = [i for i in range(1944) if ("primary", i) not in old][:88]
    for i in range(3):
        offset = TEAMS_OFF + i * rr.TEAM_SIZE
        body[offset:offset + rr.TEAM_SIZE] = bytes(rr.TEAM_SIZE)
        for relative, text in ((rr.TEAM_ABBREVIATION, ["IND", "ATL", "SF"][i]),
                               (rr.TEAM_NICKNAME, "Team"), (rr.TEAM_CITY, "City")):
            raw = text.encode("utf-16-le") + b"\0\0"
            body[team_cursor:team_cursor + len(raw)] = raw
            rel(offset + relative, team_cursor)
            team_cursor += len(raw)
        players = owned[i * 44:(i + 1) * 44] if i < 2 else []
        body[offset + rr.TEAM_PLAYER_COUNT] = len(players)
        for slot, index in enumerate(players):
            rel(offset + slot * 4, PLAYERS_OFF + index * rr.PLAYER_SIZE)
    struct.pack_into("<I", body, rr.FREE_AGENT_COUNT_FIELD, len(data["existing"]))
    for slot, row in enumerate(data["existing"]):
        assert row.get("pool", "primary") == "primary"
        rel(FREE_AGENTS_OFF + slot * 4, PLAYERS_OFF + row["index"] * rr.PLAYER_SIZE)
    return bytes(body)


class DatedDataTests(unittest.TestCase):
    def test_dated_real_identity_evidence_and_full_position_depth(self):
        data = fa.load_data()
        self.assertEqual((data["schema"], data["as_of"]), (fa.SCHEMA, "2026-10-05"))
        self.assertEqual(len(data["existing"]), 239)
        self.assertEqual(len(data["added"]), 140)
        self.assertEqual(len(data["removed"]), 2)
        self.assertEqual(data["rating_model"], "r1-ratings-v2.4")
        removed = {r["index"] for r in data["removed"]}
        rows = [r for r in data["existing"] if r["index"] not in removed] + data["added"]
        identities = [(r["first"].casefold(), r["last"].casefold()) for r in rows]
        self.assertEqual(len(set(identities)), len(identities))
        for row in data["added"]:
            self.assertEqual(row["status"], "unsigned_not_retired")
            self.assertTrue(row["sources"], row["first"] + " " + row["last"])
            self.assertEqual(row["commentary_number"], row["jersey"])
            self.assertEqual(set(row["ratings"]), set(rr.RATING_BYTE_ORDER))
            self.assertEqual(set(row["rating_basis"]), set(rr.RATING_BYTE_ORDER))
            self.assertIn("completed_seasons_out", row["inactivity"])
            self.assertEqual(set(row["appearance"]), set(fa.APPEARANCE_FIELDS))
        for row in data["removed"]:
            self.assertTrue(row["sources"])
        by_index = {row["index"]: row for row in data["existing"]}
        for index, identity in EXISTING_QBS.items():
            self.assertEqual((by_index[index]["first"], by_index[index]["last"]), identity)
        body, receipt = fa.apply_body(fixture(data), data)
        counts = receipt["by_position"]
        self.assertGreaterEqual(counts["QB"], 15)
        self.assertEqual({rr.position_name(i, "one_pool") for i in ACTIVE_POSITIONS}, set(counts))
        self.assertEqual(receipt["free_agents"], 377)


class FreeAgentWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fa.load_data()
        cls.body = fixture(cls.data)

    def test_only_existing_appearance_and_new_slots_change_with_exact_scope(self):
        before = rr.load_body(self.body, scheme="one_pool")
        output, receipt = fa.apply_body(self.body, self.data)
        after = rr.load_body(output, scheme="one_pool")
        self.assertEqual((len(after.by_pool("primary")), len(after.by_pool("secondary"))), (2479, 68))
        self.assertEqual((receipt["added"], receipt["removed"], receipt["free_agents"]), (140, 2, 377))
        old = {(r.get("pool", "primary"), r["index"]): r for r in self.data["existing"]}
        new = {r["index"]: r for r in self.data["added"]}
        scope = [(rr.FREE_AGENT_COUNT_FIELD, rr.FREE_AGENT_COUNT_FIELD + 4),
                 (before.free_agent_list, before.free_agent_list + 4 * 377),
                 (before.names.start, before.names.end)]
        for p, q in zip(before.players, after.players):
            key = (p.pool, p.index)
            if key in old:
                expected = rr.PlayerRecord.decode(p.record.encode())
                for field, value in old[key]["appearance"].items():
                    expected.set(field, value)
                self.assertEqual(expected.encode(), q.record.encode(), key)
                scope.append((p.offset, p.offset + rr.PLAYER_SIZE))
                self.assertEqual((p.first, p.last), (q.first, q.last))
            elif p.pool == "primary" and p.index in new:
                row = new[p.index]
                self.assertEqual((q.first, q.last), (row["first"], row["last"]))
                self.assertEqual(q.record.get("pbp_id"), 9000 + row["jersey"])
                self.assertEqual(q.record.get("star_tag"), 0)
                self.assertEqual(q.record.get("unknown_09"), 0)
                self.assertEqual(q.record.get("history_pointer"), 0)
                for field, value in {**row["fields"], **row["ratings"], **row["appearance"]}.items():
                    self.assertEqual(q.record.get(field), value, (q.display, field))
                scope.append((p.offset, p.offset + rr.PLAYER_SIZE))
            else:
                self.assertEqual(p.record.encode(), q.record.encode(), key)
                self.assertEqual((p.first, p.last), (q.first, q.last), key)
        for a, b in zip(before.teams, after.teams):
            self.assertEqual(self.body[a.offset:a.offset + rr.TEAM_SIZE], output[b.offset:b.offset + rr.TEAM_SIZE])
        for index, (a, b) in enumerate(zip(self.body, output)):
            if a != b:
                self.assertTrue(any(start <= index < end for start, end in scope), hex(index))
        self.assertEqual(len(output), len(self.body))
        self.assertEqual([p.index for p in after.players if p.group == "draft_class"], list(range(1944, 2324)))
        removed = {r["index"] for r in self.data["removed"]}
        self.assertFalse(removed & {after.by_offset[o].index for o in after.free_agents})

    def test_replay_preserves_peer_commentary_contract_and_all_other_bits(self):
        output, _ = fa.apply_body(self.body, self.data)
        self.assertEqual(fa.apply_body(output, self.data)[0], output)
        doc = rr.load_body(output, scheme="one_pool")
        player = doc.by_pool("primary")[self.data["added"][0]["index"]]
        for field, value in {"pbp_id": 9014, "contract_value": 777, "unknown_09": 0xE1,
                             "speed": 93, "star_tag": 1}.items():
            player.record.set(field, value)
        changed = doc.to_body()
        self.assertEqual(fa.apply_body(changed, self.data)[0], changed)

    def test_occupied_slot_existing_identity_membership_and_draft_window_refuse(self):
        for failure in ("occupied", "existing_name", "extra_fa", "draft_window", "team_owner"):
            doc = rr.load_body(self.body, scheme="one_pool")
            if failure == "occupied":
                doc.players[self.data["added"][0]["index"]].record.set("player_type", 4)
            elif failure == "existing_name":
                doc.set_name(doc.players[self.data["existing"][0]["index"]], "first", "Other")
            elif failure == "extra_fa":
                doc.free_agents.append(doc.players[100].offset)
            elif failure == "draft_window":
                doc.players[1944].record.set("player_type", 4)
            else:
                team = doc.teams[2]
                team.slots.append(doc.players[self.data["added"][0]["index"]].offset)
            raw = doc.to_body()
            with self.subTest(failure=failure), self.assertRaises(rr.RosterRecordError):
                fa.apply_body(raw, self.data)
            self.assertEqual(doc.to_body(), raw)

    def test_capacity_bad_date_raw_pointers_duplicates_and_bad_evidence_refuse_transactionally(self):
        with patch.object(rr.RosterDocument, "_measure_free_agent_capacity", return_value=239):
            with self.assertRaisesRegex(rr.RosterRecordError, "pointer buffer is full"):
                fa.apply_body(self.body, self.data)
        too_many = copy.deepcopy(self.data)
        too_many["added"] = (too_many["added"] * 2)[:156]
        with self.assertRaisesRegex(rr.RosterRecordError, "plan capacity"):
            fa.apply_body(self.body, too_many)
        for failure in ("date", "raw_pointer", "duplicate", "evidence", "number", "name_space"):
            data = copy.deepcopy(self.data)
            if failure == "date":
                data["as_of"] = "2025-10-05"
            elif failure == "raw_pointer":
                data["added"][0]["fields"]["history_pointer"] = 123
            elif failure == "duplicate":
                data["added"][1]["first"] = data["added"][0]["first"]
                data["added"][1]["last"] = data["added"][0]["last"]
            elif failure == "evidence":
                data["added"][0]["sources"] = []
            elif failure == "name_space":
                data["added"][0]["first"] = "AnUnallocatableOverlongGivenName"
            else:
                data["added"][0]["commentary_number"] = 0 if data["added"][0]["jersey"] else 1
            original = bytearray(self.body)
            with self.subTest(failure=failure), self.assertRaises((rr.RosterRecordError, rr.RosterPoolFull)):
                fa.apply_body(original, data)
            self.assertEqual(bytes(original), self.body)

    def test_native_geometry_and_pack_input_recognition_are_strict(self):
        self.assertTrue(fa.is_pack_input({"fr_free_agents": {"date": "2026-09-29", "selected": 236,
                                                              "source": "roster_2026.csv"},
                                          "free_agent_pool": [{}] * 239}))
        self.assertFalse(fa.is_pack_input({}))
        self.assertFalse(fa.is_pack_input({"free_agent_pool": [{}] * 239}))
        with self.assertRaisesRegex(rr.RosterRecordError, "2479/68"):
            fa.apply_body(synthetic_body(), self.data)
        stale = {"fr_free_agents": {"date": "2026-09-28", "selected": 236, "source": "roster_2026.csv"},
                 "free_agent_pool": [{}] * 239}
        self.assertFalse(fa.is_pack_input(stale))


if __name__ == "__main__":
    unittest.main()

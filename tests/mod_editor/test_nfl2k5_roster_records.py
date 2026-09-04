"""The roster record codec, the string pools, the save container and the ROST write.

Offline tests build a synthetic ROST body in the retail shape (object at +0x40, 0x54 player records,
0x1F4 team records, an 8-byte college table, a solidly packed name pool) so they run anywhere.  The
byte-exactness proof, the field semantics and the digest-gate order run against the real retail
roster and are skipped when the private extraction is absent.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

RETAIL_EXTRACTION = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
RETAIL_XBE = RETAIL_EXTRACTION / "default.xbe"
HAVE_RETAIL = (RETAIL_EXTRACTION / "vc_53450030" / "0").is_file()

D = dt.date

# --------------------------------------------------------------------------------------------- fixture
COLLEGE_STRINGS_OFF = 0x79F5C
COLLEGE_TABLE_OFF = 0xA758
NAME_STRINGS_OFF = 0x7B970
PLAYERS_OFF = 0xAFA8
TEAMS_OFF = 0x41C8
FREE_AGENTS_OFF = 0x3F364

COLLEGES = ("Tennessee", "Michigan", "Virginia Tech", "Marshall", "Penn State")
SAMPLE = [
    # first, last, position, jersey, years pro, weight, height, birth, college, speed, team
    ("Peyton", "Manning", 0, 18, 7, 230, 77, D(1976, 3, 24), 0, 66, 0),
    ("Marvin", "Harrison", 3, 88, 8, 185, 72, D(1972, 8, 25), 0, 88, 0),
    ("Edgerrin", "James", 7, 32, 5, 219, 72, D(1978, 8, 1), 0, 85, 0),
    ("Michael", "Vick", 0, 7, 4, 215, 72, D(1980, 6, 28), 2, 93, 1),
    ("Warrick", "Dunn", 7, 28, 8, 180, 69, D(1975, 1, 5), 1, 88, 1),
    ("Randy", "Moss", 3, 84, 7, 200, 76, D(1977, 2, 13), 3, 91, 1),
    ("Free", "Agent", 4, 24, 3, 190, 71, D(1979, 5, 9), 4, 80, None),
    ("Draft", "Prospect", 15, 99, 0, 300, 75, D(1983, 4, 2), 4, 60, None),
]
TEAM_ABBRS = ("IND", "ATL", "SF")


def synthetic_body(players=SAMPLE, *, size: int = rr.BODY_SIZE) -> bytes:
    """A ROST body in the retail shape, with the name pool packed solid (no free bytes)."""

    body = bytearray(size)
    body[0x0C:0x10] = b"ROST"
    struct.pack_into("<I", body, 0x10, 17)
    obj = rr.OBJ_OFF

    def rel(field_off: int, target: int) -> None:
        struct.pack_into("<i", body, field_off, target - field_off + 1)

    struct.pack_into("<i", body, 0x14, obj - 0x14 + 1)

    cursor = COLLEGE_STRINGS_OFF
    college_string = {}
    for index, name in enumerate(COLLEGES):
        raw = name.encode("utf-16-le") + b"\0\0"
        body[cursor: cursor + len(raw)] = raw
        college_string[index] = cursor
        cursor += len(raw)
    struct.pack_into("<I", body, obj + 0x20, len(COLLEGES))
    rel(obj + 0x24, COLLEGE_TABLE_OFF)
    for index in range(len(COLLEGES)):
        record = COLLEGE_TABLE_OFF + index * rr.COLLEGE_SIZE
        rel(record, college_string[index])
        struct.pack_into("<I", body, record + 4, index)

    names = NAME_STRINGS_OFF

    def put_name(text: str) -> int:
        nonlocal names
        raw = text.encode("utf-16-le") + b"\0\0"
        at = names
        body[at: at + len(raw)] = raw
        names += len(raw)           # solid: no padding, exactly like the retail pool
        return at

    struct.pack_into("<I", body, obj + 0x00, len(players))
    rel(obj + 0x04, PLAYERS_OFF)
    struct.pack_into("<I", body, obj + 0x08, 0)
    rel(obj + 0x0C, PLAYERS_OFF + len(players) * rr.PLAYER_SIZE)
    for index, row in enumerate(players):
        first, last, position, jersey, years, weight, height, birth, college, speed, _team = row
        off = PLAYERS_OFF + index * rr.PLAYER_SIZE
        rel(off + 0x10, put_name(first))
        rel(off + 0x14, put_name(last))
        rel(off + 0x00, COLLEGE_TABLE_OFF + college * rr.COLLEGE_SIZE)
        struct.pack_into("<H", body, off + 0x04, 1000 + index)
        struct.pack_into("<H", body, off + 0x06, 1000 + index)
        body[off + 0x08] = 0 if row[10] is None and position == 15 else 4
        struct.pack_into("<H", body, off + 0x0A, 200 + index * 37)
        body[off + 0x18] = 0x02                                  # right handed
        body[off + 0x19] = (birth.month << 4)
        body[off + 0x1A] = birth.day | (((birth.year - 1900) & 0x7) << 5)
        body[off + 0x1B] = ((birth.year - 1900) >> 3) & 0xF
        struct.pack_into("<I", body, off + 0x20, jersey << 3)
        body[off + 0x24] = 3
        body[off + 0x25] = years
        body[off + 0x26] = 0x12
        body[off + 0x27] = 4
        struct.pack_into("<H", body, off + 0x28, (index % 4) << 10)
        body[off + 0x2A] = weight - 150
        body[off + 0x2B] = height
        body[off + 0x35] = position
        for rating in range(0x36, 0x52):
            body[off + rating] = 40 + (index * 3 + rating) % 50
        body[off + 0x36] = speed

    struct.pack_into("<I", body, obj + 0x18, len(TEAM_ABBRS))
    rel(obj + 0x1C, TEAMS_OFF)
    for index, abbr in enumerate(TEAM_ABBRS):
        team = TEAMS_OFF + index * rr.TEAM_SIZE
        rel(team + rr.TEAM_ABBREVIATION, put_name(abbr))
        rel(team + rr.TEAM_NICKNAME, put_name(f"Team{index}"))
        rel(team + rr.TEAM_CITY, put_name(f"City{index}"))
        slots = [k for k, row in enumerate(players) if row[10] == index]
        body[team + rr.TEAM_PLAYER_COUNT] = len(slots)
        for slot, player_index in enumerate(slots):
            rel(team + slot * 4, PLAYERS_OFF + player_index * rr.PLAYER_SIZE)

    free = [k for k, row in enumerate(players) if row[10] is None and row[2] != 15]
    struct.pack_into("<I", body, obj + 0x38, len(free))
    rel(obj + 0x3C, FREE_AGENTS_OFF)
    for slot, player_index in enumerate(free):
        rel(FREE_AGENTS_OFF + slot * 4, PLAYERS_OFF + player_index * rr.PLAYER_SIZE)
    return bytes(body)


def synthetic_resource(body: bytes | None = None) -> bytes:
    payload = body if body is not None else synthetic_body()
    header = b"ROST" + struct.pack("<II", rr.BODY_SIZE, rr.BODY_SIZE) + bytes(rr.RESOURCE_HEADER_SIZE - 12)
    return header + payload


def retail_body() -> bytes:
    with rr._outer_image()(RETAIL_EXTRACTION) as archive:
        entry = rr._entry(archive)
        return archive.read(entry.virtual_offset, entry.size)[rr.RESOURCE_HEADER_SIZE:]


# --------------------------------------------------------------------------------------------- codec
class RecordCodecTests(unittest.TestCase):
    def test_the_field_table_claims_every_bit_of_the_record(self) -> None:
        coverage = rr.field_coverage()
        self.assertEqual(len(coverage), rr.PLAYER_SIZE)
        self.assertEqual(sorted(set(coverage)), [8], "every byte of the 0x54 record is claimed exactly once")

    def test_decode_encode_round_trips_arbitrary_bytes(self) -> None:
        import random

        random.seed(2005)
        for _ in range(200):
            raw = bytes(random.randrange(256) for _ in range(rr.PLAYER_SIZE))
            self.assertEqual(rr.encode_record(rr.decode_record(raw)), raw)

    def test_encode_refuses_a_value_that_does_not_fit(self) -> None:
        values = rr.decode_record(bytes(rr.PLAYER_SIZE))
        values["jersey"] = 200                                    # 7 bits hold 0..127
        with self.assertRaises(rr.RosterRecordError):
            rr.encode_record(values)
        record = rr.PlayerRecord(rr.decode_record(bytes(rr.PLAYER_SIZE)))
        with self.assertRaises(rr.RosterRecordError):
            record.set("jersey", 200)
        with self.assertRaises(rr.RosterRecordError):
            record.set("not_a_field", 1)

    def test_composites_split_and_rejoin(self) -> None:
        record = rr.PlayerRecord(rr.decode_record(bytes(rr.PLAYER_SIZE)))
        record.skin = 21
        self.assertEqual((record.values["skin_low"], record.values["skin_high"]), (1, 10))
        self.assertEqual(record.skin, 21)
        record.birth_date = D(1976, 3, 24)
        self.assertEqual(record.birth_date, D(1976, 3, 24))
        record.birth_date = D(2001, 12, 31)
        self.assertEqual(record.birth_date, D(2001, 12, 31))
        record.weight = 305
        self.assertEqual((record.values["weight_raw"], record.weight), (155, 305))
        record.left_glove = 9
        self.assertEqual((record.values["left_glove_low"], record.values["left_glove_high"]), (1, 2))
        self.assertEqual(record.left_glove, 9)
        with self.assertRaises(rr.RosterRecordError):
            record.weight = 500

    def test_the_three_style_channels(self) -> None:
        """Power Run Style, the Scramble parity bit and Kicking Style (2026-09-04 study, section 1)."""

        record = rr.PlayerRecord(rr.decode_record(bytes(rr.PLAYER_SIZE)))
        # +0x4D: the game's own thresholds and the three values its cycler writes
        for value, bucket in ((0, 0), (32, 0), (33, 1), (50, 1), (65, 1), (66, 2), (99, 2)):
            record.values["power_run_style"] = value
            self.assertEqual(record.power_run_style_bucket, bucket, value)
            self.assertEqual(rr.POWER_RUN_STYLES[bucket],
                             ("Finesse", "Balanced", "Power")[bucket])
        for index, expected in enumerate(rr.POWER_RUN_STYLE_VALUES):
            record.power_run_style_bucket = index
            self.assertEqual(record.values["power_run_style"], expected)
        self.assertEqual(rr.POWER_RUN_STYLE_VALUES, (1, 50, 99))
        self.assertEqual(rr.POWER_RUN_STYLE_THRESHOLDS, (33, 66))
        with self.assertRaises(rr.RosterRecordError):
            record.power_run_style_bucket = 3
        # +0x4F: parity and magnitude move independently
        record.values["scramble"] = 53
        self.assertEqual(record.throw_style, 1)
        record.throw_style = 0
        self.assertEqual((record.values["scramble"], record.throw_style), (52, 0))
        record.throw_style = 1
        self.assertEqual(record.values["scramble"], 53)
        record.set_scramble_magnitude(90)
        self.assertEqual((record.values["scramble"], record.throw_style), (91, 1),
                         "the magnitude moves and the style bit survives")
        record.throw_style = 0
        record.set_scramble_magnitude(10)
        self.assertEqual(record.values["scramble"], 10)
        with self.assertRaises(rr.RosterRecordError):
            record.throw_style = 2
        # the engine's second test: 0.01*Scramble + 0.01*Agility > 1.5 picks the mobile family
        record.values["scramble"], record.values["agility"] = 97, 90
        self.assertTrue(record.mobile_quarterback)
        record.values["scramble"] = 5
        self.assertFalse(record.mobile_quarterback)
        # +0x4B is a named style channel now, and it is a rating byte like the others
        self.assertEqual(rr.RATING_OFFSETS["kicking_style"], 0x4B)
        self.assertEqual(rr.RATING_OFFSETS["power_run_style"], 0x4D)
        self.assertEqual(rr.RATING_OFFSETS["scramble"], 0x4F)
        self.assertEqual(rr.STYLE_RATINGS, ("power_run_style", "scramble", "kicking_style"))
        self.assertEqual([value for _label, value in rr.KICKING_STYLE_PRESETS], [1, 49, 99])
        self.assertEqual([value for _label, value in rr.SCRAMBLE_PRESETS], [10, 50, 90])

    def test_contract_and_derived_readouts(self) -> None:
        record = rr.PlayerRecord(rr.decode_record(bytes(rr.PLAYER_SIZE)))
        record.set("contract_value", 377)
        record.set("contract_bonus", 5)
        self.assertAlmostEqual(record.contract_millions, 3.77)
        self.assertAlmostEqual(record.contract_penalty_millions, 1.885)
        record.set("injured_reserve", 0xEE)
        self.assertTrue(record.on_injured_reserve)
        record.set("player_type", 4)
        self.assertTrue(record.pbp_last_name_only)


# --------------------------------------------------------------------------------------------- document
class DocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = synthetic_body()
        self.document = rr.load_body(self.body)

    def test_parses_players_teams_colleges_and_pools(self) -> None:
        summary = self.document.summary()
        self.assertEqual(summary["players"], len(SAMPLE))
        self.assertEqual(summary["teams"], len(TEAM_ABBRS))
        self.assertEqual(summary["colleges"], len(COLLEGES))
        self.assertEqual(summary["free_agents"], 1)
        self.assertEqual(summary["draft_class"], 1)
        self.assertEqual([p.abbreviation for p in self.document.teams], list(TEAM_ABBRS))
        manning = self.document.players[0]
        self.assertEqual((manning.first, manning.last, manning.college), ("Peyton", "Manning", "Tennessee"))
        self.assertEqual(manning.record.position_name, "QB")
        self.assertEqual(manning.record.values["jersey"], 18)
        self.assertEqual(manning.record.birth_date, D(1976, 3, 24))
        self.assertEqual(manning.record.weight, 230)
        self.assertEqual(manning.record.height_text, "6'5\"")
        self.assertEqual([p.display for p in self.document.team_players(0)],
                         ["Peyton Manning", "Marvin Harrison", "Edgerrin James"])
        self.assertEqual([p.display for p in self.document.group_players("free_agent")], ["Free Agent"])
        self.assertEqual([p.display for p in self.document.group_players("draft_class")], ["Draft Prospect"])

    def test_body_round_trips_byte_identically_when_nothing_changes(self) -> None:
        self.assertEqual(self.document.to_body(), self.body)

    def test_edits_survive_a_reload(self) -> None:
        player = self.document.players[0]
        player.record.set("speed", 55)
        player.record.set("face_mask", 12)
        player.record.weight = 240
        again = rr.load_body(self.document.to_body()).players[0]
        self.assertEqual(again.record.values["speed"], 55)
        self.assertEqual(again.record.values["face_mask"], 12)
        self.assertEqual(again.record.weight, 240)

    def test_depth_reorder_is_the_team_pointer_list(self) -> None:
        self.assertTrue(self.document.move_in_depth(0, 0, 1))
        self.assertEqual([p.display for p in self.document.team_players(0)],
                         ["Marvin Harrison", "Peyton Manning", "Edgerrin James"])
        reloaded = rr.load_body(self.document.to_body())
        self.assertEqual([p.display for p in reloaded.team_players(0)],
                         ["Marvin Harrison", "Peyton Manning", "Edgerrin James"])
        self.assertFalse(self.document.move_in_depth(0, 0, -1))

    def test_college_is_a_pick_from_the_roster_s_own_table(self) -> None:
        player = self.document.players[0]
        self.document.set_college(player, COLLEGES.index("Michigan"))
        self.assertEqual(player.college, "Michigan")
        self.assertEqual(rr.load_body(self.document.to_body()).players[0].college, "Michigan")
        with self.assertRaises(rr.RosterRecordError):
            self.document.set_college(player, 99)


# --------------------------------------------------------------------------------------------- pool
class NamePoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = synthetic_body()
        self.document = rr.load_body(self.body)

    def test_the_retail_shaped_pool_starts_with_no_free_bytes(self) -> None:
        pool = self.document.names
        self.assertEqual(pool.free_bytes, 0)
        self.assertEqual(pool.capacity_bytes, sum(block.capacity for block in pool.blocks.values()))

    def test_an_existing_string_is_shared_rather_than_copied(self) -> None:
        vick = next(p for p in self.document.players if p.last == "Vick")
        receipt = self.document.set_name(vick, "first", "Randy")     # Randy Moss already has one
        self.assertEqual(receipt["mode"], "shared")
        moss = next(p for p in self.document.players if p.last == "Moss")
        self.assertEqual(self.document._pointer_target(vick.offset, "first_name_pointer"),
                         self.document._pointer_target(moss.offset, "first_name_pointer"))
        self.assertEqual(rr.load_body(self.document.to_body()).players[3].first, "Randy")

    def test_a_shorter_name_frees_its_tail_and_a_longer_one_can_use_it(self) -> None:
        player = next(p for p in self.document.players if p.last == "Harrison")
        self.document.set_name(player, "last", "Ali")                # 16 bytes -> 8, frees 8
        self.assertGreaterEqual(self.document.names.free_bytes, 8)
        self.document.set_name(player, "last", "Wayne")              # 12 bytes, fits the freed block
        self.assertEqual(rr.load_body(self.document.to_body()).players[1].last, "Wayne")

    def test_a_full_pool_refuses_rather_than_overrunning(self) -> None:
        player = self.document.players[0]
        with self.assertRaises(rr.RosterPoolFull) as ctx:
            self.document.set_name(player, "last", "Manningham")
        self.assertIn("full", str(ctx.exception))
        self.assertEqual(self.document.to_body(), self.body, "a refusal changes nothing")

    def test_names_are_validated_before_they_reach_the_pool(self) -> None:
        player = self.document.players[0]
        for bad in ("", "   ", "A" * 16, "Bad;Name"):
            with self.assertRaises(rr.RosterRecordError, msg=bad):
                self.document.set_name(player, "last", bad)

    def test_pool_blocks_coalesce_so_two_short_names_make_room_for_one_long_one(self) -> None:
        first = next(p for p in self.document.players if p.last == "Harrison")
        second = next(p for p in self.document.players if p.last == "James")
        # "Harrison" (18 B) and "Edgerrin" (18 B) are adjacent neither side of "Marvin"; free both
        self.document.set_name(first, "last", "Ali")
        self.document.set_name(second, "first", "Ed")
        self.assertGreater(self.document.names.free_bytes, 0)
        self.document.set_name(first, "last", "Vanderjagt")
        self.assertEqual(rr.load_body(self.document.to_body()).players[1].last, "Vanderjagt")


# --------------------------------------------------------------------------------------------- passes
class PassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = synthetic_body()
        self.document = rr.load_body(self.body)

    def test_global_edit_preview_then_apply(self) -> None:
        preview = rr.global_edit_preview(self.document, attribute="speed", mode="add", value=5,
                                         positions=["QB"])
        self.assertEqual({row["name"] for row in preview}, {"Peyton Manning", "Michael Vick"})
        self.assertEqual([(row["before"], row["after"]) for row in preview], [(66, 71), (93, 98)])
        self.assertEqual(rr.global_edit_apply(self.document, preview, "speed"), 2)
        self.assertEqual(self.document.players[0].record.values["speed"], 71)
        capped = rr.global_edit_preview(self.document, attribute="speed", mode="equal", value=140,
                                        maximum=rr.RATING_MAX)
        self.assertTrue(all(row["after"] == 99 for row in capped))
        rookies = rr.global_edit_preview(self.document, attribute="speed", mode="add", value=1,
                                         rookies_only=True)
        self.assertEqual([row["name"] for row in rookies], ["Draft Prospect"])
        with self.assertRaises(rr.RosterRecordError):
            rr.global_edit_preview(self.document, attribute="nope", mode="add", value=1)

    def test_a_global_edit_can_target_the_style_channels_with_a_condition(self) -> None:
        """Finn never had this: "every QB with Speed >= 80 -> throw style B"."""

        for player in self.document.players:
            player.record.throw_style = 0
        preview = rr.global_edit_preview(self.document, attribute="throw_style", mode="equal",
                                         value=1, positions=["QB"], where=("speed", ">=", 80))
        self.assertEqual([row["name"] for row in preview], ["Michael Vick"])
        self.assertEqual(rr.global_edit_apply(self.document, preview, "throw_style"), 1)
        vick = next(p for p in self.document.players if p.last == "Vick")
        self.assertEqual(vick.record.throw_style, 1)
        self.assertEqual(vick.record.values["scramble"] % 2, 1)
        # "all HBs with Break Tackle >= 40 -> Power"
        for player in self.document.players:
            player.record.power_run_style_bucket = 0
        preview = rr.global_edit_preview(self.document, attribute="power_run_style_bucket",
                                         mode="equal", value=2, positions=["HB"],
                                         where=("break_tackle", ">=", 40))
        self.assertTrue(preview)
        rr.global_edit_apply(self.document, preview, "power_run_style_bucket")
        for row in preview:
            player = next(p for p in self.document.players
                          if (p.pool, p.index) == (row["pool"], row["index"]))
            self.assertEqual(player.record.values["power_run_style"], 99)
        with self.assertRaises(rr.RosterRecordError):
            rr.global_edit_preview(self.document, attribute="speed", mode="equal", value=1,
                                   where=("speed", "~=", 1))
        with self.assertRaises(rr.RosterRecordError):
            rr.global_edit_preview(self.document, attribute="speed", mode="equal", value=1,
                                   where=("nope", ">=", 1))

    def test_copy_paste_modes(self) -> None:
        source = self.document.players[0]
        target = self.document.players[3]
        before_photo = target.record.values["photo_id"]
        rr.copy_player(source.record, target.record, mode="attributes")
        self.assertEqual(target.record.ratings(), source.record.ratings())
        self.assertEqual(target.record.values["photo_id"], before_photo, "attributes only")
        self.assertNotEqual(target.record.values["jersey"], source.record.values["jersey"])
        rr.copy_player(source.record, target.record, mode="photo")
        self.assertEqual(target.record.values["photo_id"], source.record.values["photo_id"])
        rr.copy_player(source.record, target.record, mode="all")
        self.assertEqual(target.record.values["jersey"], source.record.values["jersey"])
        self.assertNotEqual(target.record.values["first_name_pointer"],
                            source.record.values["first_name_pointer"], "names never travel")
        self.assertEqual(target.first, "Michael")

    def test_advance_years_pro_stops_at_the_field_width(self) -> None:
        self.assertEqual(rr.advance_years_pro(self.document), len(SAMPLE))
        self.assertEqual(self.document.players[0].record.values["years_pro"], 8)
        self.document.players[0].record.values["years_pro"] = 31
        self.assertEqual(rr.advance_years_pro(self.document, [self.document.players[0]]), 0)

    def test_restore_measurements_puts_the_shipped_values_back(self) -> None:
        baseline = rr.load_body(self.body)
        player = self.document.players[0]
        player.record.weight = 300
        player.record.birth_date = D(1990, 1, 1)
        self.assertEqual(rr.restore_measurements(self.document, baseline, [player]), 1)
        self.assertEqual(player.record.weight, 230)
        self.assertEqual(player.record.birth_date, D(1976, 3, 24))
        self.assertEqual(rr.restore_measurements(self.document, baseline, [player]), 0)

    def test_validation_flags_jerseys_ratings_and_headless_models(self) -> None:
        player = self.document.players[0]
        player.record.set("jersey", 88)                 # a QB in the 80s
        player.record.set("speed", 120)
        player.record.set("headless", 1)
        checks = {item["check"] for item in rr.validate(self.document, [player])}
        self.assertEqual(checks, {"jersey", "rating", "headless", "name pool"})


# --------------------------------------------------------------------------------------------- csv
class CsvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = synthetic_body()
        self.document = rr.load_body(self.body)

    def test_export_import_round_trip_changes_nothing(self) -> None:
        text = rr.export_csv(self.document)
        receipt = rr.import_csv(self.document, text)
        self.assertEqual(receipt["log"], [])
        self.assertEqual(receipt["rows"], len(SAMPLE))
        self.assertEqual((receipt["changed"], receipt["fields"]), (0, 0),
                         "re-importing an unchanged export is a no-op")
        self.assertEqual(self.document.to_body(), self.body)

    def test_edited_cells_come_back_in(self) -> None:
        text = rr.export_csv(self.document)
        text = text.replace("Peyton,Manning,QB,18,7", "Peyton,Manning,QB,12,9")
        receipt = rr.import_csv(self.document, text)
        self.assertEqual((receipt["rows"], receipt["changed"]), (len(SAMPLE), 1))
        self.assertEqual(self.document.players[0].record.values["jersey"], 12)
        self.assertEqual(self.document.players[0].record.values["years_pro"], 9)

    def test_a_semicolon_export_in_finn_s_shape_is_read(self) -> None:
        text = "last;first;speed\nManning;Peyton;42\n"
        receipt = rr.import_csv(self.document, text)
        self.assertEqual((receipt["rows"], receipt["fields"]), (1, 1))
        self.assertEqual(self.document.players[0].record.values["speed"], 42)

    def test_enums_are_accepted_by_label_or_number_and_bad_ones_are_logged(self) -> None:
        text = "last;first;body;position;hand\nManning;Peyton;Large;RB;Left\n"
        rr.import_csv(self.document, text)
        self.assertEqual(self.document.players[0].record.values["body"], rr.BODIES.index("Large"))
        self.assertEqual(self.document.players[0].record.position_name, "HB")
        self.assertEqual(self.document.players[0].record.values["hand"], 0)
        receipt = rr.import_csv(self.document, "last;first;body\nManning;Peyton;Enormous\n")
        self.assertTrue(any("Enormous" in line for line in receipt["log"]))

    def test_unmatched_rows_are_reported_not_guessed(self) -> None:
        receipt = rr.import_csv(self.document, "last;first;speed\nNobody;At;50\n")
        self.assertEqual(receipt["rows"], 0)
        self.assertTrue(any("no roster record matches" in line for line in receipt["log"]))


# --------------------------------------------------------------------------------------------- edits
class EditsDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = synthetic_body()
        self.document = rr.load_body(self.body)

    def test_a_document_replays_onto_a_fresh_roster_byte_for_byte(self) -> None:
        player = self.document.players[0]
        player.record.set("speed", 55)
        player.record.set("contract_value", 999)
        player.record.set("position", rr.POSITIONS.index("WR"))
        self.document.set_name(player, "first", "Randy")
        self.document.set_college(player, COLLEGES.index("Michigan"))
        document = rr.edits_document(self.document, name="unit")
        self.assertEqual(document["schema"], rr.EDITS_SCHEMA)
        self.assertEqual(len(document["edits"]), 1)
        self.assertEqual(document["edits"][0]["first"], "Peyton", "the identity is the name we loaded")
        self.assertEqual(document["edits"][0]["names"], {"first": "Randy", "college": "Michigan"})
        replayed, receipt = rr.apply_body(self.body, document)
        self.assertEqual(receipt["log"], [])
        self.assertEqual(receipt["players_changed"], 1)
        self.assertEqual(replayed, self.document.to_body())

    def test_diff_reports_text_not_pointers(self) -> None:
        player = self.document.players[0]
        self.document.set_name(player, "first", "Randy")
        entry = self.document.diff()[0]
        self.assertEqual(entry["texts"]["first"], ("Peyton", "Randy"))
        self.assertNotIn("first_name_pointer", entry["changes"])

    def test_a_bad_document_is_refused_and_stray_entries_are_logged(self) -> None:
        with self.assertRaises(rr.RosterRecordError):
            rr.read_edits({"schema": "something/else", "edits": []})
        _out, receipt = rr.apply_body(self.body, {
            "schema": rr.EDITS_SCHEMA, "edits": [
                {"pool": "primary", "index": 999, "fields": {"speed": 1}},
                {"pool": "primary", "index": 0, "last": "Elway", "fields": {"nope": 1, "speed": 200}},
                {"pool": "primary", "index": 0, "fields": {"first_name_pointer": 5}},
            ]})
        self.assertEqual(len(receipt["log"]), 4)
        self.assertTrue(any("no such roster record" in line for line in receipt["log"]))
        self.assertTrue(any("Elway" in line for line in receipt["log"]))
        self.assertTrue(any("unknown field" in line for line in receipt["log"]))
        self.assertTrue(any("pointer" in line for line in receipt["log"]))

    def test_edits_between_recovers_the_document_from_two_rosters(self) -> None:
        self.document.players[0].record.set("speed", 12)
        document = rr.edits_between(self.body, self.document.to_body())
        self.assertEqual(document["edits"], [{"pool": "primary", "index": 0, "last": "Manning",
                                              "first": "Peyton", "fields": {"speed": 12}}])


# --------------------------------------------------------------------------------------------- saves
class SaveContainerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = synthetic_body()
        self.savegame = self.body + bytes(224)      # a roster save is the body plus a short tail

    def _zip(self, directory: Path, *, extra: bytes | None = None) -> Path:
        path = directory / "BaseRoster.zip"
        signature = rr.sign_save(self.savegame) if extra is None else extra
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("53450030/4A6F686E0001/SAVEGAME.DAT", self.savegame)
            archive.writestr("53450030/4A6F686E0001/EXTRA", signature)
            archive.writestr("53450030/4A6F686E0001/SaveMeta.xbx", b"META" * 16)
            archive.writestr("53450030/4A6F686E0001/TYPE", b"\x01")
            archive.writestr("53450030/TitleImage.xbx", b"IMAGE" * 8)
        return path

    def test_extra_is_hmac_sha1_of_the_whole_savegame(self) -> None:
        import hmac

        self.assertEqual(rr.sign_save(self.savegame),
                         hmac.new(rr.SIG_KEY, self.savegame, hashlib.sha1).digest())
        self.assertEqual(len(rr.sign_save(self.savegame)), rr.EXTRA_SIZE)
        self.assertTrue(rr.verify_extra(self.savegame, rr.sign_save(self.savegame)))
        self.assertFalse(rr.verify_extra(self.savegame, bytes(20)))
        self.assertFalse(rr.verify_extra(self.savegame, rr.sign_save(self.savegame)[:19]))

    def test_a_zip_container_loads_edits_and_re_signs_a_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = self._zip(tmp)
            container = rr.SaveContainer.load(source)
            self.assertTrue(container.verified)
            document = container.document()
            self.assertEqual(document.base, 0)
            document.players[0].record.set("speed", 41)
            receipt = rr.save_document(document, tmp / "edited.zip")
            self.assertTrue(receipt["signed"])
            self.assertEqual(sorted(receipt["members_copied_byte_for_byte"]),
                             ["53450030/4A6F686E0001/SaveMeta.xbx", "53450030/4A6F686E0001/TYPE",
                              "53450030/TitleImage.xbx"])
            again = rr.SaveContainer.load(tmp / "edited.zip")
            self.assertTrue(again.verified)
            self.assertEqual(again.document().players[0].record.values["speed"], 41)
            with zipfile.ZipFile(source) as before, zipfile.ZipFile(tmp / "edited.zip") as after:
                self.assertEqual(before.namelist(), after.namelist())
                for name in before.namelist():
                    if name.endswith(("SAVEGAME.DAT", "EXTRA")):
                        continue
                    self.assertEqual(before.read(name), after.read(name), name)

    def test_a_directory_container_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "save"
            (source / "53450030" / "0001").mkdir(parents=True)
            (source / "53450030" / "0001" / "SAVEGAME.DAT").write_bytes(self.savegame)
            (source / "53450030" / "0001" / "EXTRA").write_bytes(rr.sign_save(self.savegame))
            (source / "53450030" / "0001" / "SaveMeta.xbx").write_bytes(b"META")
            document = rr.load_save(source)
            document.players[0].record.set("speed", 7)
            rr.save_document(document, tmp / "out")
            self.assertTrue(rr.SaveContainer.load(tmp / "out").verified)
            self.assertEqual((tmp / "out" / "53450030" / "0001" / "SaveMeta.xbx").read_bytes(), b"META")

    def test_a_save_whose_signature_does_not_verify_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            broken = self._zip(tmp, extra=bytes(20))
            with self.assertRaises(rr.RosterRecordError) as ctx:
                rr.SaveContainer.load(broken)
            self.assertIn("does not match", str(ctx.exception))
            container = rr.SaveContainer.load(broken, require_signature=False)
            self.assertFalse(container.verified)

    def test_a_franchise_shaped_arena_is_found_at_its_own_offset(self) -> None:
        arena = bytes(rr.FRANCHISE_BLOCK_OFFSET) + self.body + bytes(0x400)
        self.assertEqual(rr.find_block_base(arena), rr.FRANCHISE_BLOCK_OFFSET)
        document = rr.RosterDocument(arena, base=rr.FRANCHISE_BLOCK_OFFSET)
        self.assertEqual(len(document.players), len(SAMPLE))
        self.assertEqual(document.to_body(), arena)
        with self.assertRaises(rr.RosterRecordError):
            rr.find_block_base(bytes(0x2000))

    def test_writing_over_the_source_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = self._zip(tmp)
            document = rr.SaveContainer.load(source).document()
            with self.assertRaises(rr.RosterRecordError):
                rr.save_document(document, source)


# --------------------------------------------------------------------------------------------- image
class ImageWriterTests(unittest.TestCase):
    def test_apply_writes_the_resource_inside_a_disc_copy(self) -> None:
        from nfl2k5_xiso_fixture import SyntheticXiso

        resource = synthetic_resource()
        document = rr.load_body(synthetic_body())
        document.players[0].record.set("speed", 33)
        edits = rr.edits_document(document)
        with tempfile.TemporaryDirectory() as tmp:
            dummies = [(100 + k, b"DUMY" + bytes(0x100)) for k in range(5)]
            fixture = SyntheticXiso(Path(tmp), dummies + [(5, resource), (200, b"TAIL" + bytes(0x100))],
                                    pack_sizes=(0xA0000,), pack_sectors=(64,))
            self.assertEqual(rr.status(fixture.path), "edited")     # synthetic, so not the retail sha
            receipt = rr.apply(fixture.path, edits)
            self.assertEqual(receipt["fields_written"], 1)
            with rr._outer_image()(fixture.path) as archive:
                entry = rr._entry(archive)
                written = archive.read(entry.virtual_offset, entry.size)
            self.assertEqual(written, resource[:rr.RESOURCE_HEADER_SIZE] + document.to_body())
            again = rr.apply(fixture.path, edits)
            self.assertTrue(again.get("already_applied"))

    def test_share_recognises_the_edit_and_packs_the_document(self) -> None:
        import os
        import shutil

        from mod_editor.core import modpack
        from nfl2k5_xiso_fixture import SyntheticXiso

        body = synthetic_body()
        document = rr.load_body(body)
        document.players[0].record.set("speed", 33)
        document.set_name(document.players[0], "first", "Randy")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dummies = [(100 + k, b"DUMY" + bytes(0x100)) for k in range(5)]
            base = SyntheticXiso(tmp, dummies + [(5, synthetic_resource(body)),
                                                 (200, b"TAIL" + bytes(0x100))],
                                 pack_sizes=(0xA0000,), pack_sectors=(64,))
            patched = tmp / "patched.iso"
            shutil.copyfile(base.path, patched)
            rr.apply(patched, rr.edits_document(document))
            size = os.path.getsize(base.path)
            base_fd, patched_fd = os.open(str(base.path), os.O_RDONLY), os.open(str(patched), os.O_RDONLY)
            try:
                found = modpack.recognise_recipe(base_fd, patched_fd, size, Path(base.path), patched)
            finally:
                os.close(base_fd)
                os.close(patched_fd)
        self.assertEqual(found["detected"]["roster_edits"]["players_edited"], 1)
        operations = [op for op in found["operations"] if op["op"] == "roster_edits"]
        self.assertEqual(operations[0]["edits_asset"], "assets/text/roster_edits.json")
        assets = [a for a in found["auto_assets"] if a.get("role") == "roster_edits.json"]
        self.assertEqual(assets[0]["member"], "assets/text/roster_edits.json")
        recovered = json.loads(assets[0]["data"].decode("utf-8"))
        self.assertEqual(recovered["edits"][0]["fields"], {"speed": 33})
        self.assertEqual(recovered["edits"][0]["names"], {"first": "Randy"})
        self.assertIn("1 player ", modpack.describe_operation(operations[0]))

    def test_a_foreign_resource_is_refused(self) -> None:
        self.assertEqual(rr.resource_status(b"NOPE" + bytes(rr.RESOURCE_SIZE - 4)), "foreign")
        self.assertEqual(rr.resource_status(synthetic_resource()), "edited")
        broken = bytearray(synthetic_resource())
        broken[rr.RESOURCE_HEADER_SIZE + 0x0C: rr.RESOURCE_HEADER_SIZE + 0x10] = b"XXXX"
        self.assertEqual(rr.resource_status(bytes(broken)), "foreign")


# --------------------------------------------------------------------------------------------- retail
@unittest.skipUnless(HAVE_RETAIL, "the retail extraction is not present")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.body = retail_body()
        cls.document = rr.load_body(cls.body)
        cls.by_name = {(p.first, p.last): p for p in cls.document.players}

    def test_the_retail_body_is_the_pinned_one(self) -> None:
        self.assertEqual(hashlib.sha256(self.body).hexdigest(), rr.RETAIL_BODY_SHA256)
        self.assertEqual(rr.status(RETAIL_EXTRACTION), "retail")

    def test_every_retail_record_round_trips_byte_identically(self) -> None:
        self.assertEqual(len(self.document.players),
                         rr.RETAIL_PRIMARY_COUNT + rr.RETAIL_SECONDARY_COUNT)
        for player in self.document.players:
            raw = self.body[player.offset: player.offset + rr.PLAYER_SIZE]
            self.assertEqual(rr.encode_record(rr.decode_record(raw)), raw,
                             f"{player.pool} #{player.index} {player.display}")
        self.assertEqual(self.document.to_body(), self.body, "the whole body round trips")

    def test_the_retail_tables_are_the_documented_ones(self) -> None:
        summary = self.document.summary()
        self.assertEqual(summary["primary"], rr.RETAIL_PRIMARY_COUNT)
        self.assertEqual(summary["secondary"], rr.RETAIL_SECONDARY_COUNT)
        self.assertEqual(summary["teams"], rr.RETAIL_TEAM_COUNT)
        self.assertEqual(summary["colleges"], rr.RETAIL_COLLEGE_COUNT)
        self.assertEqual(summary["free_agents"], rr.RETAIL_FREE_AGENT_COUNT)
        self.assertEqual(summary["draft_class"], 380)
        self.assertEqual((self.document.names.start, self.document.names.end), (0x7B970, 0x8B7D0))
        self.assertEqual(self.document.names.free_bytes, 0, "the retail name pool is packed solid")
        self.assertEqual(len(self.document.names.blocks), 5094)
        self.assertEqual([t.abbreviation for t in self.document.teams[:4]], ["SF", "CHI", "CIN", "BUF"])
        self.assertEqual(len(self.document.teams[0].slots), 53)

    def test_the_field_semantics_hold_on_real_players(self) -> None:
        """Every value here is from the Flying Finn / Bad_AL report, section 4.3 and 14."""

        manning = self.by_name[("Peyton", "Manning")].record
        self.assertEqual(manning.birth_date, D(1976, 3, 24))
        self.assertEqual((manning.values["height"], manning.weight), (77, 230))
        self.assertEqual(self.by_name[("Peyton", "Manning")].college, "Tennessee")
        self.assertEqual(manning.position_name, "QB")
        self.assertEqual(manning.values["jersey"], 18)
        self.assertEqual(rr.HELMETS[manning.values["helmet"]], "Revolution")
        self.assertEqual(manning.values["pass_accuracy"], 96)
        self.assertEqual(manning.values["pass_read_coverage"], 98)
        self.assertEqual(self.by_name[("Tom", "Brady")].record.birth_date, D(1977, 8, 3))
        self.assertEqual(rr.HANDS[self.by_name[("Michael", "Vick")].record.values["hand"]], "Left")
        moss = self.by_name[("Randy", "Moss")].record
        self.assertEqual(moss.birth_date, D(1977, 2, 13))
        self.assertEqual(moss.values["eye_black"], 1)
        self.assertEqual(moss.values["power_run_style"], 99)
        self.assertEqual(self.by_name[("Ray", "Lewis")].record.birth_date, D(1975, 5, 15))
        vinatieri = self.by_name[("Adam", "Vinatieri")].record
        self.assertEqual((vinatieri.values["kick_power"], vinatieri.values["kick_accuracy"]), (95, 97))
        self.assertEqual(vinatieri.values["kicking_style"], 99, "+0x4B is 99 for a kicker")
        # the contract block -- the thing only Finn's editor ever had
        barlow = self.by_name[("Kevan", "Barlow")].record
        self.assertAlmostEqual(barlow.contract_millions, 20.00)
        self.assertEqual(rr.CONTRACT_TYPES[barlow.values["contract_type"]], "Front Load")
        self.assertEqual(rr.CONTRACT_BONUSES[barlow.values["contract_bonus"]], "10%")
        self.assertEqual((barlow.values["contract_length"], barlow.values["contract_remaining"]), (5, 5))
        adams = self.by_name[("Anthony", "Adams")].record
        self.assertAlmostEqual(adams.contract_millions, 3.77)
        self.assertEqual(rr.CONTRACT_TYPES[adams.values["contract_type"]], "Back Load")
        self.assertEqual(rr.CONTRACT_BONUSES[adams.values["contract_bonus"]], "50%")
        self.assertEqual((adams.values["contract_length"], adams.values["contract_remaining"]), (4, 3))
        self.assertEqual((adams.values["pbp_id"], adams.values["photo_id"]), (5015, 5015))

    def test_the_retail_distributions_match_the_report(self) -> None:
        from collections import Counter

        primary = self.document.by_pool("primary")
        self.assertEqual(Counter(p.record.values["player_type"] for p in primary),
                         Counter({4: 1937, 0: 380, 1: 155, 68: 7}))
        hands = Counter(p.record.values["hand"] for p in primary)
        self.assertEqual((hands[0], hands[1]), (557, 1922))
        self.assertEqual(sum(1 for p in primary if p.record.values["helmet"]), 174)
        shields = Counter(p.record.values["face_shield"] for p in primary)
        self.assertEqual((shields[1], shields[2]), (42, 18))
        bodies = Counter(p.record.values["body"] for p in primary)
        self.assertEqual([bodies[k] for k in range(4)], [652, 1493, 319, 15])

    def test_the_signing_key_is_the_one_the_studio_derives_from_the_xbe(self) -> None:
        from mod_editor.core import nfl2k5_save_writer as sw

        self.assertEqual(sw.derive_sig_key(RETAIL_XBE.read_bytes()), rr.SIG_KEY)

    def test_digest_gate_order_with_the_other_roster_passes(self) -> None:
        """Our pass runs LAST: it changes what the reclassify gate hashes, and nothing that the
        team-history, prospect-name or star-tag gates look at."""

        import nfl2k5_roster_reclassify as reclassify
        from mod_editor.core import nfl2k5_player_tags as tags
        from mod_editor.core import nfl2k5_prospect_names as names
        from mod_editor.core import nfl2k5_team_history as history

        document = rr.load_body(self.body)
        player = document.players[0]
        player.record.set("speed", 41)
        player.record.set("position", rr.POSITIONS.index("WR"))
        player.record.set("depth_rank", 5)
        document.set_name(player, "first", "Randy")
        edited = document.to_body()
        self.assertNotEqual(edited, self.body)

        self.assertEqual(tags.body_status(edited), tags.body_status(self.body),
                         "the star bit at +0x53 is untouched")
        self.assertEqual(history.body_status(edited), history.body_status(self.body),
                         "the season-stat pool and the +0x2C pointers are untouched")
        self.assertEqual(names.body_status(edited), names.body_status(self.body),
                         "the generated-name pool is untouched")

        # the reclassify pass hashes the record area, which our position/depth writes change:
        # that is exactly why roster_edits runs after it in mod_build.build
        with rr._outer_image()(RETAIL_EXTRACTION) as archive:
            main = reclassify.load_resources(archive, historic=False)[0]
        import dataclasses

        patched = dataclasses.replace(main, body=edited)
        self.assertNotEqual(reclassify.record_digest([patched]), reclassify.record_digest([main]))

        # and the earlier passes leave our own edits alone: replaying the document onto a
        # star-tagged body reproduces the same records
        tagged, _receipt = tags.apply_body(self.body, [player.index])
        replayed, receipt = rr.apply_body(tagged, rr.edits_document(document))
        self.assertEqual(receipt["log"], [])
        self.assertEqual(tags.body_status(replayed), "applied")
        replayed_player = rr.load_body(replayed).players[player.index]
        self.assertEqual(replayed_player.record.values["speed"], 41)
        self.assertEqual(replayed_player.first, "Randy")

    def test_the_build_plan_carries_the_step_and_it_runs_last(self) -> None:
        from mod_editor.core import mod_build

        plan = mod_build.BuildPlan(source="x", target="y")
        self.assertEqual(plan.roster_edits, "")
        self.assertIn("roster_edits", plan.to_recipe())
        self.assertTrue(mod_build.availability()["roster_edits"])
        source = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        order = [source.index(f"if plan.{name}:") for name in
                 ("position_pools", "season_2026", "team_history", "prospect_names", "player_tags",
                  "roster_edits")]
        self.assertEqual(order, sorted(order), "roster_edits is the last ROST pass in build()")


if __name__ == "__main__":
    unittest.main()

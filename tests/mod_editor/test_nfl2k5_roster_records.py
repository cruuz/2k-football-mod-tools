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

# Front-seven fixtures for the position-scheme tests.  A retail roster carries OLB (10); a roster
# put through tools/nfl2k5_roster_reclassify carries none at all -- its 3-4 outside backers have
# become EDGE (16) and its off-ball backers LB (11).  Both sit on team 2, which the default sample
# leaves empty, so the existing fixtures are untouched.
FRONT_RETAIL = [
    ("Ray", "Lewis", 11, 52, 8, 250, 73, D(1975, 5, 15), 1, 80, 2),
    ("Peter", "Boulware", 10, 58, 7, 255, 76, D(1974, 12, 18), 1, 78, 2),
    ("Adalius", "Thomas", 10, 96, 4, 270, 74, D(1977, 7, 25), 2, 76, 2),
    ("Kelly", "Gregg", 15, 97, 5, 310, 71, D(1976, 11, 3), 3, 60, 2),
    ("Terrell", "Suggs", 16, 55, 0, 260, 75, D(1982, 10, 11), 2, 82, 2),
]
FRONT_ONE_POOL = [
    ("Ray", "Lewis", 11, 52, 8, 250, 73, D(1975, 5, 15), 1, 80, 2),
    ("Peter", "Boulware", 16, 58, 7, 255, 76, D(1974, 12, 18), 1, 78, 2),
    ("Adalius", "Thomas", 16, 96, 4, 270, 74, D(1977, 7, 25), 2, 76, 2),
    ("Kelly", "Gregg", 15, 97, 5, 310, 71, D(1976, 11, 3), 3, 60, 2),
    ("Terrell", "Suggs", 16, 55, 0, 260, 75, D(1982, 10, 11), 2, 82, 2),
]
RETAIL_FRONT_SAMPLE = SAMPLE + FRONT_RETAIL
ONE_POOL_SAMPLE = SAMPLE + FRONT_ONE_POOL


def retail_front_body() -> bytes:
    return synthetic_body(RETAIL_FRONT_SAMPLE)


def one_pool_body() -> bytes:
    return synthetic_body(ONE_POOL_SAMPLE)


LEAGUE_CLUB_SIZE = 44


def league_sample(club_size: int = LEAGUE_CLUB_SIZE) -> list:
    """Two clubs big enough for Finn's 42-man rule plus three free agents and one prospect."""

    rows = []
    for team in (0, 1):
        for n in range(club_size):
            code = (n * 7) % len(rr.POSITIONS)
            if code == 15:                              # 15 with no team is the fixture's draft-class marker
                code = 16
            rows.append((f"F{team}{n}", f"Last{team}{n}", code, 1 + n, n % 12, 200 + n, 70 + n % 8,
                         D(1975 + n % 10, 1 + n % 12, 1 + n % 28), n % len(COLLEGES), 50 + n % 40, team))
    rows.append(("Free", "AgentOne", 4, 24, 3, 190, 71, D(1979, 5, 9), 4, 80, None))
    rows.append(("Free", "AgentTwo", 0, 9, 3, 210, 74, D(1978, 5, 9), 4, 70, None))
    rows.append(("Free", "AgentThree", 3, 81, 1, 185, 72, D(1981, 2, 2), 4, 88, None))
    rows.append(("Draft", "Prospect", 15, 99, 0, 300, 75, D(1983, 4, 2), 4, 60, None))
    return rows


def league_body(club_size: int = LEAGUE_CLUB_SIZE) -> bytes:
    return synthetic_body(league_sample(club_size))


def reclassified_retail_body() -> bytes:
    """The retail ROST body put through the shipped reclassify pass, in memory.

    Nothing is written: the pass is planned against the retail pack and applied to a copy of the
    body, which is exactly what ``tools/nfl2k5_roster_reclassify.py apply`` does inside a disc copy.
    ``schemes={}`` leaves the playbooks unread; every retail team carries a scheme word (0/1/2), so
    the book fallback is never reached.
    """

    import nfl2k5_roster_reclassify as reclassify

    with reclassify.OuterImage(RETAIL_EXTRACTION) as archive:
        resource = reclassify.load_resources(archive, historic=False)[0]
    body = bytearray(resource.body)
    moves, _schemes = reclassify.plan_resource(resource, {})
    reclassify.apply_moves(body, moves)
    return bytes(body)


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
        self.assertEqual(checks, {"jersey", "rating", "headless", "name pool", "roster size", "free agents"})


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


# ---------------------------------------------------------------------------------------- membership
class MembershipTests(unittest.TestCase):
    """Finn's release / sign / swap as pointer-list edits, with his thresholds and refusals."""

    def setUp(self) -> None:
        self.body = league_body()
        self.document = rr.load_body(self.body)
        self.ind, self.atl = self.document.teams[0], self.document.teams[1]
        self.free_agents = self.document.group_players("free_agent")
        self.prospect = self.document.group_players("draft_class")[0]

    def names(self, team_index: int) -> list[str]:
        return [p.display for p in self.document.team_players(team_index)]

    def test_release_and_sign_are_the_pointer_lists_and_the_counts(self) -> None:
        player = self.document.team_players(0)[5]
        receipt = self.document.release(player)
        self.assertEqual((receipt["from"]["team"], receipt["from"]["slot"], receipt["to"]["kind"]), ("IND", 5, "free_agent"))
        self.assertEqual((len(self.ind.slots), len(self.document.free_agents)), (LEAGUE_CLUB_SIZE - 1, 4))
        self.assertEqual(player.group, "free_agent")
        self.assertNotIn(player.display, self.names(0))
        self.assertEqual(self.document.membership_text(player), "Free Agents")
        reloaded = rr.load_body(self.document.to_body())
        self.assertEqual(reloaded.teams[0].player_count, LEAGUE_CLUB_SIZE - 1, "the +0x11C count byte moved")
        self.assertEqual(len(reloaded.teams[0].slots), LEAGUE_CLUB_SIZE - 1)
        self.assertEqual(reloaded.by_offset[reloaded.free_agents[-1]].display, player.display)
        self.assertEqual(reloaded.u32(reloaded.obj_base + rr.FREE_AGENT_COUNT_FIELD), 4)
        # the tail slot the list gave up is zero, exactly as Finn's IR diff showed the game keeps it
        tail = self.ind.offset + (LEAGUE_CLUB_SIZE - 1) * 4
        self.assertEqual(reloaded.body[tail: tail + 4], b"\0\0\0\0")
        # signing him back at his old slot puts every byte back
        back = self.document.sign(player, 0, slot=5)
        self.assertEqual((back["to"]["team"], back["to"]["slot"]), ("IND", 5))
        self.assertEqual(self.document.membership_text(player), f"IND (6 of {LEAGUE_CLUB_SIZE})")
        self.assertEqual(self.document.diff(), [] if not back["depth"]["depth_rank"][0] != back["depth"]["depth_rank"][1] else self.document.diff())
        player.record.values["depth_rank"], player.record.values["depth_side"] = back["depth"]["depth_rank"][0], back["depth"]["depth_side"][0]
        self.assertEqual(self.document.to_body(), self.body)
        self.assertEqual(self.document.diff(), [])

    def test_a_signed_player_lands_at_the_bottom_of_his_positions_chain(self) -> None:
        free_agent = self.free_agents[0]                    # a CB
        same = [p for p in self.document.team_players(0) if p.record.values["position"] == 4]
        receipt = self.document.sign(free_agent, 0)
        self.assertEqual(receipt["to"]["slot"], LEAGUE_CLUB_SIZE, "appended to the list")
        self.assertEqual(free_agent.record.values["depth_rank"], min(len(same), rr.DEPTH_ROW_CAP))
        self.assertEqual(free_agent.record.values["depth_side"],
                         rr.DEPTH_SIDE_FOR_RANK.get(min(len(same), 7), min(len(same), 7)))
        self.assertNotIn(free_agent.offset, self.document.free_agents)
        self.assertEqual(self.document.depth_slot(0, free_agent), (len(same) + 1, len(same) + 1))

    def test_finns_thresholds_and_refusals(self) -> None:
        small = rr.load_body(league_body(rr.TEAM_MIN_PLAYERS))
        with self.assertRaisesRegex(rr.MembershipRefused, "must maintain at least 42"):
            small.release(small.team_players(0)[0])
        with self.assertRaisesRegex(rr.MembershipRefused, "Max players reached"):
            self.document.sign(self.free_agents[0], 0, maximum=LEAGUE_CLUB_SIZE)
        self.document.free_agent_capacity = len(self.document.free_agents)
        with self.assertRaisesRegex(rr.MembershipRefused, "Max free agents reached"):
            self.document.release(self.document.team_players(0)[0])
        for operation in (lambda: self.document.release(self.prospect),
                          lambda: self.document.sign(self.prospect, 0),
                          lambda: self.document.swap(self.prospect, self.document.team_players(0)[0]),
                          lambda: self.document.transfer(self.prospect, 1)):
            with self.assertRaisesRegex(rr.MembershipRefused, "Invalid operation on a draft class"):
                operation()
        with self.assertRaisesRegex(rr.MembershipRefused, "move him"):
            self.document.sign(self.document.team_players(0)[0], 1)
        with self.assertRaisesRegex(rr.MembershipRefused, "cannot be placed on Injured Reserve"):
            self.document.check_operation(self.free_agents[0], "injured_reserve")
        self.assertEqual(self.document.to_body(), self.body, "a refusal touches nothing")

    def test_transfer_and_swap_keep_the_counts(self) -> None:
        mover = self.document.team_players(0)[3]
        receipt = self.document.transfer(mover, 1)
        self.assertEqual((receipt["from"]["team"], receipt["to"]["team"], receipt["to"]["slot"]),
                         ("IND", "ATL", LEAGUE_CLUB_SIZE))
        self.assertEqual((len(self.ind.slots), len(self.atl.slots)), (LEAGUE_CLUB_SIZE - 1, LEAGUE_CLUB_SIZE + 1))
        self.assertEqual(mover.teams, [1])
        a, b = self.document.team_players(0)[2], self.document.team_players(1)[7]
        swap = self.document.swap(a, b)
        self.assertEqual((swap["first"]["to"], swap["second"]["to"]), ("ATL", "IND"))
        self.assertIs(self.document.team_players(0)[2], b)
        self.assertIs(self.document.team_players(1)[7], a)
        self.assertEqual((len(self.ind.slots), len(self.atl.slots)), (LEAGUE_CLUB_SIZE - 1, LEAGUE_CLUB_SIZE + 1))
        reloaded = rr.load_body(self.document.to_body())
        self.assertEqual([p.display for p in reloaded.team_players(1)][7], a.display)
        self.assertEqual(reloaded.teams[1].player_count, LEAGUE_CLUB_SIZE + 1)

    def test_the_diff_and_the_edits_document_carry_moves_that_replay_byte_for_byte(self) -> None:
        released = self.document.team_players(0)[1]
        self.document.release(released)
        self.document.sign(self.free_agents[1], 1, slot=2)
        self.document.swap(self.document.team_players(0)[4], self.document.team_players(1)[9])
        self.document.transfer(self.document.team_players(1)[0], 0)
        entries = {e["name"]: e for e in self.document.diff()}
        self.assertEqual(entries[released.display]["membership"], (f"IND (2 of {LEAGUE_CLUB_SIZE})", "Free Agents"))
        self.assertEqual(entries[self.free_agents[1].display]["membership"][0], "Free Agents")
        self.assertTrue(entries[self.free_agents[1].display]["membership"][1].startswith("ATL (2 of"), "the transfer out of ATL slot 0 moved him up one")
        document = rr.edits_document(self.document, name="moves")
        self.assertEqual(len(document["moves"]), 5)
        by_name = {f"{m['first']} {m['last']}": m for m in document["moves"]}
        self.assertEqual(by_name[released.display]["to_teams"], [])
        self.assertTrue(by_name[released.display]["free_agent"])
        self.assertEqual(by_name[self.free_agents[1].display]["to_teams"][0]["team"], "ATL")
        replayed, receipt = rr.apply_body(self.body, json.loads(json.dumps(document)))
        self.assertEqual(receipt["log"], [])
        self.assertEqual(receipt["players_moved"], 5)
        self.assertEqual(replayed, self.document.to_body())
        recovered = rr.edits_between(self.body, replayed)
        self.assertEqual(len(recovered["moves"]), 5)

    def test_a_replay_that_would_break_the_rules_leaves_the_lists_alone_and_says_so(self) -> None:
        for player in list(self.document.team_players(0))[:3]:
            self.document.release(player, minimum=0)          # 44 -> 41, only possible by force here
        self.document.team_players(1)[0].record.set("speed", 11)
        document = rr.edits_document(self.document)
        replayed, receipt = rr.apply_body(self.body, document)
        self.assertEqual(receipt["players_moved"], 0)
        self.assertTrue(any("moves skipped" in line and "minimum 42" in line for line in receipt["log"]), receipt["log"])
        target = rr.load_body(replayed)
        self.assertEqual(len(target.teams[0].slots), LEAGUE_CLUB_SIZE, "the target's lists are untouched")
        self.assertEqual(target.team_players(1)[0].record.values["speed"], 11, "the fields still landed")
        with_missing = rr.edits_document(self.document)
        with_missing["moves"] = [{"pool": "primary", "index": 0, "to_teams": [{"team": "XXX"}], "free_agent": False}]
        _out, receipt = rr.apply_body(self.body, with_missing)
        self.assertTrue(any("no team 'XXX'" in line for line in receipt["log"]), receipt["log"])

    def test_the_csv_team_column_moves_players(self) -> None:
        text = rr.export_csv(self.document)
        mover, cut = self.document.team_players(1)[2], self.document.team_players(0)[6]
        edited = (text.replace(f"primary,{mover.index},ATL,", f"primary,{mover.index},IND,")
                      .replace(f"primary,{cut.index},IND,", f"primary,{cut.index},free_agent,")
                      .replace(f"primary,{self.prospect.index},draft_class,", f"primary,{self.prospect.index},IND,")
                      .replace(f"primary,{self.free_agents[2].index},free_agent,", f"primary,{self.free_agents[2].index},atl,"))
        receipt = rr.import_csv(self.document, edited)
        self.assertEqual(receipt["changed"], 3)
        self.assertEqual(mover.teams, [0])
        self.assertEqual(cut.group, "free_agent")
        self.assertEqual(self.free_agents[2].teams, [1])
        self.assertTrue(any("Invalid operation on a draft class" in line for line in receipt["log"]), receipt["log"])
        self.assertEqual(self.prospect.group, "draft_class")
        again = rr.import_csv(rr.load_body(self.body), rr.export_csv(self.document))
        self.assertEqual(again["changed"], 3)

    def test_snapshot_and_restore_put_every_list_and_depth_bit_back(self) -> None:
        before = self.document.membership_snapshot()
        self.document.release(self.document.team_players(0)[0])
        self.document.sign(self.free_agents[0], 1)
        self.document.swap(self.document.team_players(0)[1], self.document.team_players(1)[1])
        self.assertNotEqual(self.document.to_body(), self.body)
        self.document.restore_membership(before)
        self.assertEqual(self.document.to_body(), self.body)
        self.assertEqual(self.document.membership_changes(), [])
        self.assertEqual([p.group for p in self.free_agents], ["free_agent"] * 3)

    def test_validation_reports_roster_sizes_and_the_free_agent_list(self) -> None:
        small = rr.load_body(league_body(rr.TEAM_MIN_PLAYERS - 1))
        checks = [f for f in rr.validate_membership(small) if f["check"] == "roster size"]
        self.assertEqual(len(checks), 2)
        self.assertIn("41 players", checks[0]["detail"])
        free = [f for f in rr.validate(self.document) if f["check"] == "free agents"][0]
        self.assertTrue(free["detail"].startswith("3 of "))
        big = self.document
        for player in list(self.free_agents):
            big.sign(player, 0, maximum=99)
        self.assertEqual(len(big.teams[0].slots), LEAGUE_CLUB_SIZE + 3)
        big.free_agent_capacity = 0
        with self.assertRaisesRegex(rr.RosterRecordError, "pointer"):
            big.release(big.team_players(0)[0])

    def test_a_save_arena_moves_players_through_the_same_lists(self) -> None:
        savegame = synthetic_save_v0(self.body)
        document = rr.RosterDocument(savegame, base=0x300, source="save")
        self.assertEqual(document.free_agent_capacity, rr.load_body(self.body).free_agent_capacity)
        player = document.team_players(0)[0]
        document.release(player)
        reloaded = rr.RosterDocument(document.to_body(), base=0x300)
        self.assertEqual(len(reloaded.teams[0].slots), LEAGUE_CLUB_SIZE - 1)
        self.assertEqual(reloaded.by_offset[reloaded.free_agents[-1]].display, player.display)


# ----------------------------------------------------------------------------------------- templates
class TemplateTests(unittest.TestCase):
    """The game's create-a-player templates, applied the way FUN_00343460 applies them."""

    def test_the_slot_map_covers_every_rating_byte_once(self) -> None:
        self.assertEqual(len(rr.CREATE_PLAYER_TEMPLATE_SLOT_OFFSETS), 28)
        self.assertEqual(sorted(rr.CREATE_PLAYER_TEMPLATE_SLOT_OFFSETS), list(range(0x36, 0x52)))
        self.assertEqual(rr.CREATE_PLAYER_TEMPLATE_SLOTS[7], "power_run_style")
        self.assertEqual(rr.CREATE_PLAYER_TEMPLATE_SLOTS[21], "scramble")
        self.assertEqual(rr.CREATE_PLAYER_TEMPLATE_SLOTS[0], "speed")
        self.assertEqual(rr.CREATE_PLAYER_TEMPLATE_SLOTS[25], "kicking_style")
        self.assertEqual(rr.CREATE_PLAYER_TEMPLATE_SLOTS[27], "aggressiveness")

    def test_the_retail_table_reads_as_the_game_lays_it_out(self) -> None:
        templates = rr.create_player_templates()
        self.assertEqual(len(templates), 36)
        self.assertEqual([t.label for t in templates[:3]], ["Pocket QB", "Scrambling QB", "Balanced QB"])
        self.assertEqual([t.position_name for t in templates[::3]],
                         ["QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB"])
        pocket, scrambling, balanced = templates[:3]
        self.assertEqual((pocket.ratings()["scramble"], scrambling.ratings()["scramble"], balanced.ratings()["scramble"]),
                         (10, 90, 50))
        finesse, power, balanced_hb = rr.templates_for_position(rr.POSITIONS.index("HB"))
        self.assertEqual((finesse.label, power.label, balanced_hb.label), ("Finesse HB", "Power HB", "Balanced HB"))
        self.assertEqual((finesse.ratings()["power_run_style"], power.ratings()["power_run_style"],
                          balanced_hb.ratings()["power_run_style"]), (1, 99, 50))
        self.assertEqual(rr.templates_for_position(rr.POSITIONS.index("DE")), ())
        self.assertEqual(rr.templates_for_position(rr.POSITIONS.index("C")), ())
        speed_wr = rr.templates_for_position(rr.POSITIONS.index("WR"))[0]
        self.assertEqual(speed_wr.slots[25], -1, "the WR/HB/FB/TE templates leave slot 25 at -1")
        self.assertEqual(speed_wr.ratings()["kicking_style"], rr.CREATE_PLAYER_TEMPLATE_DEFAULT,
                         "which the routine writes as 75 (mov bl,0x4B), not 'leave alone'")
        self.assertEqual(speed_wr.ratings()["speed"], 90)
        self.assertEqual(speed_wr.ratings()["catch"], 70)
        self.assertEqual(speed_wr.ratings()["run_route"], 75)
        self.assertEqual(rr.templates_for_position(0)[0].ratings()["pass_accuracy"], 85)
        self.assertEqual(rr.templates_for_position(0)[1].ratings()["pass_arm_strength"], 85)

    def test_apply_writes_the_28_bytes_with_the_games_own_clamps(self) -> None:
        document = rr.load_body(synthetic_body())
        manning = document.players[0]
        odd = rr.CreatePlayerTemplate(99, "Clamp", tuple([-1, 150, -7] + [50] * 25))
        changes = rr.apply_template(manning.record, odd)
        self.assertEqual(manning.record.values["speed"], 75)
        self.assertEqual(manning.record.values["agility"], 100)
        self.assertEqual(manning.record.values["pass_accuracy"], 0)
        self.assertEqual(manning.record.values["aggressiveness"], 50)
        self.assertEqual(changes["speed"], (66, 75))
        self.assertEqual(rr.apply_template(manning.record, odd), {}, "a second application changes nothing")
        pocket = rr.create_player_templates()[0]
        rr.apply_template(manning.record, pocket)
        self.assertEqual(manning.record.ratings(), pocket.ratings())
        self.assertEqual(manning.record.throw_style, 0, "Pocket QB writes Scramble 10: an even value")


# --------------------------------------------------------------------------------------- .PlayerData
class PlayerDataTests(unittest.TestCase):
    """Finn's backup container: 150-byte entries, matched back by name + play-by-play index."""

    def setUp(self) -> None:
        self.body = synthetic_body()
        self.document = rr.load_body(self.body)

    def test_export_is_finns_shape(self) -> None:
        data = rr.export_player_data(self.document)
        primary = self.document.by_pool("primary")
        self.assertEqual(len(data), rr.PLAYER_DATA_ENTRY_SIZE * len(primary))
        first = data[:rr.PLAYER_DATA_ENTRY_SIZE]
        player = primary[0]
        self.assertEqual(first[:rr.PLAYER_SIZE], self.body[player.offset: player.offset + rr.PLAYER_SIZE],
                         "the raw record, pointers included")
        self.assertEqual(first[0x54:0x64], b"Peyton" + bytes(10))
        self.assertEqual(first[0x64:0x74], b"Manning" + bytes(9))
        self.assertEqual(first[0x74:0x94], b"Tennessee" + bytes(23))
        self.assertEqual(struct.unpack_from("<H", first, 0x94)[0], 7)
        entries = rr.read_player_data(data)
        self.assertEqual([(e.first, e.last, e.college, e.pbp_id) for e in entries[:2]],
                         [("Peyton", "Manning", "Tennessee", 1000), ("Marvin", "Harrison", "Tennessee", 1001)])

    def test_restoring_an_untouched_export_changes_nothing(self) -> None:
        data = rr.export_player_data(self.document)
        receipt = rr.import_player_data(self.document, data)
        self.assertEqual((receipt["entries"], receipt["matched"], receipt["changed"], receipt["fields"], receipt["log"]),
                         (len(SAMPLE), len(SAMPLE), 0, 0, []))
        self.assertEqual(self.document.to_body(), self.body)

    def test_a_backup_puts_edited_values_back_and_respects_the_identity_rules(self) -> None:
        backup = rr.export_player_data(self.document)
        manning = self.document.players[0]
        manning.record.set("speed", 12)
        manning.record.set("contract_value", 1)
        manning.record.set("star_tag", 1)
        manning.record.set("pbp_id", 4242)                               # the index differs: name alone
        self.document.set_college(manning, COLLEGES.index("Michigan"))
        receipt = rr.import_player_data(self.document, backup)
        self.assertEqual(receipt["changed"], 1)
        self.assertEqual((manning.record.values["speed"], manning.record.values["contract_value"]), (66, 200))
        self.assertEqual(manning.record.values["pbp_id"], 1000, "the play-by-play index is data and comes back")
        self.assertEqual(manning.record.values["star_tag"], 1, "the studio's own bit is never overwritten")
        self.assertEqual(manning.college, "Tennessee", "the college comes back by name")
        self.assertTrue(any("matched by name alone" in line for line in receipt["log"]), receipt["log"])
        self.assertEqual(manning.record.values["first_name_pointer"],
                         rr.PlayerRecord.decode(self.body[manning.offset: manning.offset + 0x54]).values["first_name_pointer"])

    def test_attributes_only_and_unmatched_entries(self) -> None:
        backup = bytearray(rr.export_player_data(self.document))
        backup[0x36] = 99                                                  # Manning's speed in the file
        backup[0x0A] = 0xFF                                                # and his contract value
        stranger = bytes(rr.PLAYER_SIZE) + b"Nobody".ljust(16, b"\0") + b"Here".ljust(16, b"\0") + bytes(32) + struct.pack("<H", 7)
        receipt = rr.import_player_data(self.document, bytes(backup) + stranger, mode="attributes")
        self.assertEqual((receipt["entries"], receipt["matched"], receipt["changed"], receipt["fields"]),
                         (len(SAMPLE) + 1, len(SAMPLE), 1, 1))
        self.assertEqual(self.document.players[0].record.values["speed"], 99)
        self.assertEqual(self.document.players[0].record.values["contract_value"], 200, "attributes only")
        self.assertTrue(any("Nobody Here" in line and "no roster record" in line for line in receipt["log"]))
        with self.assertRaisesRegex(rr.RosterRecordError, "whole 150-byte entries"):
            rr.read_player_data(bytes(backup)[:-1])
        bad = bytearray(backup)
        struct.pack_into("<H", bad, 0x94, 9)
        with self.assertRaisesRegex(rr.RosterRecordError, "trailer word is 9"):
            rr.read_player_data(bytes(bad))
        college_missing = bytearray(rr.export_player_data(self.document))
        college_missing[0x74:0x94] = b"Nowhere State".ljust(32, b"\0")
        receipt = rr.import_player_data(self.document, bytes(college_missing))
        self.assertTrue(any("Nowhere State" in line and "not in this roster's table" in line for line in receipt["log"]))

    def test_a_duplicate_name_without_its_index_is_skipped_not_guessed(self) -> None:
        twin = self.document.players[1]
        self.document.set_name(twin, "first", "Peyton")
        self.document.set_name(twin, "last", "Manning")
        backup = bytearray(rr.export_player_data(self.document))
        struct.pack_into("<H", backup, 4, 5555)                            # entry 0's index matches nobody now
        backup[0x36] = 1
        receipt = rr.import_player_data(self.document, bytes(backup))
        self.assertTrue(any("2 records carry this name" in line for line in receipt["log"]), receipt["log"])
        self.assertEqual(self.document.players[0].record.values["speed"], 66)
        self.assertEqual(receipt["matched"], len(SAMPLE) - 1)


# ------------------------------------------------------------------------------------------ repairs
def damaged_body() -> bytes:
    """The synthetic roster with the faults Check & repair knows: a headless bit, a team whose count
    byte overstates its list, and a team that lists one player twice."""

    body = bytearray(synthetic_body())
    body[PLAYERS_OFF + 0x0C] |= 0x80                                          # Manning: headless
    team1 = TEAMS_OFF + 1 * rr.TEAM_SIZE
    body[team1 + rr.TEAM_PLAYER_COUNT] = 4                                     # says 4, slot 3 is null
    team0 = TEAMS_OFF
    first = struct.unpack_from("<i", body, team0)[0]
    struct.pack_into("<i", body, team0 + 12, first - 12)                       # slot 3 = slot 0 again
    body[team0 + rr.TEAM_PLAYER_COUNT] = 4
    return bytes(body)


class RepairTests(unittest.TestCase):
    def test_a_clean_roster_has_nothing_to_repair(self) -> None:
        document = rr.load_body(synthetic_body())
        self.assertEqual(rr.plan_repairs(document), [])
        self.assertEqual(rr.apply_repairs(document)["summary"], "Nothing to repair.")
        self.assertEqual(document.to_body(), synthetic_body())

    def test_the_faults_are_planned_not_applied_then_applied_with_a_receipt(self) -> None:
        body = damaged_body()
        document = rr.load_body(body)
        self.assertFalse(document.teams[1].clean_parse)
        self.assertEqual(len(document.teams[0].slots), 4)
        plans = rr.plan_repairs(document)
        self.assertEqual([p["kind"] for p in plans], ["headless", "duplicate_slot", "team_count"])
        self.assertIn("Peyton Manning", plans[0]["detail"])
        self.assertIn("0x80", plans[0]["detail"])
        self.assertEqual(document.to_body(), body, "planning changes nothing")
        with self.assertRaisesRegex(rr.MembershipRefused, "count byte"):
            document.release(document.team_players(1)[0], 1, minimum=0)
        receipt = rr.apply_repairs(document, plans)
        self.assertEqual(receipt["applied"], 3)
        self.assertTrue(receipt["summary"].startswith("Repaired 1 headless player;"))
        self.assertEqual(len(receipt["lines"]), 3)
        self.assertEqual(document.players[0].record.values["headless"], 0)
        self.assertEqual(len(document.teams[0].slots), 3)
        self.assertEqual((document.teams[1].player_count, document.teams[1].clean_parse), (3, True))
        repaired = rr.load_body(document.to_body())
        self.assertEqual([t.player_count for t in repaired.teams], [3, 3, 0])
        self.assertTrue(all(t.clean_parse for t in repaired.teams))
        self.assertEqual(repaired.body[PLAYERS_OFF + 0x0C], synthetic_body()[PLAYERS_OFF + 0x0C])
        team0 = TEAMS_OFF
        self.assertEqual(repaired.body[team0 + 12: team0 + 16], b"\0\0\0\0", "the duplicate slot is zeroed")
        self.assertEqual(rr.plan_repairs(repaired), [])
        self.assertEqual(repaired.to_body(), document.to_body())

    def test_a_retired_position_code_is_a_planned_repair_under_one_pool(self) -> None:
        document = rr.load_body(retail_front_body(), scheme="one_pool")
        plans = [p for p in rr.plan_repairs(document) if p["kind"] == "retired_position"]
        self.assertEqual({p["player"] for p in plans}, {"Peter Boulware", "Adalius Thomas"})
        self.assertEqual({(p["from"], p["to"]) for p in plans}, {(rr.ENUM_OLB, rr.ENUM_ILB)})
        rr.apply_repairs(document, plans)
        self.assertEqual(document.position_census("primary")[rr.ENUM_OLB], 0)
        self.assertEqual(rr.plan_repairs(document), [])

    def test_a_duplicate_free_agent_entry_is_dropped(self) -> None:
        body = bytearray(synthetic_body())
        first = struct.unpack_from("<i", body, FREE_AGENTS_OFF)[0]
        struct.pack_into("<i", body, FREE_AGENTS_OFF + 4, first - 4)
        struct.pack_into("<I", body, rr.OBJ_OFF + 0x38, 2)
        document = rr.load_body(bytes(body))
        self.assertEqual(len(document.free_agents), 2)
        plans = rr.plan_repairs(document)
        self.assertEqual([p["kind"] for p in plans], ["duplicate_free_agent"])
        rr.apply_repairs(document, plans)
        reloaded = rr.load_body(document.to_body())
        self.assertEqual(len(reloaded.free_agents), 1)
        self.assertEqual(reloaded.u32(rr.OBJ_OFF + 0x38), 1)


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


# --------------------------------------------------------------------------------------- schemes
@unittest.skipUnless(HAVE_RETAIL, "retail extraction not present")
class RetailMembershipTests(unittest.TestCase):
    """The membership rules against the real 52-team roster (private extraction)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.body = retail_body()

    def setUp(self) -> None:
        self.document = rr.load_body(self.body)

    def team(self, abbreviation: str) -> rr.TeamRecord:
        return next(t for t in self.document.teams if t.abbreviation == abbreviation)

    def test_the_free_agent_list_capacity_is_measured_at_2500(self) -> None:
        self.assertEqual(self.document.free_agent_list, 0x3F364)
        self.assertEqual(len(self.document.free_agents), rr.RETAIL_FREE_AGENT_COUNT)
        self.assertEqual(self.document.free_agent_capacity, 2500)
        self.assertEqual(self.document.free_agent_list + 2500 * 4, self.document.rel(self.document.obj_base + rr.OBJ_OFF + 0x44),
                         "the list runs exactly up to the season-stat pool")
        self.assertEqual(rr.FREE_AGENT_LIST_CAP, 2500, "the game's own append cap (0x242560)")
        self.assertTrue(all(t.clean_parse for t in self.document.teams))
        self.assertEqual(sum(1 for p in self.document.players if len([t for t in p.teams if t < rr.CLUB_TEAM_COUNT]) > 1), 0)

    def test_the_template_table_and_its_apply_routine_are_the_pinned_retail_bytes(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        from mod_editor.core.nfl2k5_rdata_sites import offset_of
        table = offset_of(payload, rr.CREATE_PLAYER_TEMPLATES_RDATA)
        self.assertEqual(hashlib.sha256(payload[table: table + 36 * 0x74]).hexdigest(), rr.CREATE_PLAYER_TEMPLATES_SHA256)
        routine = offset_of(payload, rr.CREATE_PLAYER_TEMPLATE_APPLY_VA)
        span = rr.CREATE_PLAYER_TEMPLATE_APPLY_END_VA - rr.CREATE_PLAYER_TEMPLATE_APPLY_VA
        self.assertEqual(hashlib.sha256(payload[routine: routine + span]).hexdigest(), rr.CREATE_PLAYER_TEMPLATE_APPLY_SHA256)
        self.assertEqual(payload[offset_of(payload, 0x34349F): offset_of(payload, 0x34349F) + 2], b"\xb3\x4b",
                         "mov bl,0x4B: the value a -1 slot writes")
        self.assertEqual(payload[offset_of(payload, 0x3434AE): offset_of(payload, 0x3434AE) + 3], b"\x80\xf9\x64",
                         "cmp cl,0x64: the clamp")
        # the unrolled routine: slot k is read at [eax+4+4k] and written at record+OFFSETS[k]
        code = payload[routine: routine + span]
        for slot, offset in enumerate(rr.CREATE_PLAYER_TEMPLATE_SLOT_OFFSETS):
            read = b"\x8b\x48" + bytes([4 + 4 * slot]) if 4 + 4 * slot < 0x80 else None
            if read is not None:
                self.assertIn(read, code, f"slot {slot}: mov ecx,[eax+0x{4 + 4 * slot:x}]")
            written = (b"\x88\x4a" + bytes([offset]), b"\x88\x42" + bytes([offset]))     # ...,cl  or  ...,al (slot 27)
            self.assertTrue(any(pattern in code for pattern in written), f"slot {slot}: mov [edx+0x{offset:x}],cl/al")
        self.assertEqual(rr.read_templates(payload), rr.create_player_templates())

    def test_the_retail_disc_itself_has_exactly_one_headless_player(self) -> None:
        plans = rr.plan_repairs(self.document)
        self.assertEqual([(p["kind"], p["player"]) for p in plans], [("headless", "Carlos Joseph")])
        self.assertEqual(self.document.body[self.document.players[1718].offset + 0x0C], 0xB6)
        receipt = rr.apply_repairs(self.document)
        self.assertTrue(receipt["summary"].startswith("Repaired 1 headless player"), receipt["summary"])
        self.assertEqual(self.document.to_body()[self.document.players[1718].offset + 0x0C], 0x36,
                         "the byte Finn's own diff showed: 0xB6 -> 0x36")
        self.assertEqual(rr.plan_repairs(self.document), [])

    def test_release_sign_swap_and_finns_limits_on_the_real_clubs(self) -> None:
        sf, afc, brp = self.team("SF"), self.team("AFC"), self.team("BRP")
        self.assertEqual((len(sf.slots), len(afc.slots), len(brp.slots)), (53, 43, 54))
        player = self.document.team_players(sf.index)[10]
        alumni = [t for t in player.teams if t != sf.index]
        receipt = self.document.release(player, sf.index)
        self.assertEqual((receipt["team_players"], receipt["free_agents"]), (52, 242))
        self.assertEqual(sorted(player.teams), sorted(alumni), "an all-star side keeps him")
        self.document.release(self.document.team_players(afc.index)[0], afc.index)
        with self.assertRaisesRegex(rr.MembershipRefused, "AFC AFC must maintain at least 42"):
            self.document.release(self.document.team_players(afc.index)[0], afc.index)
        with self.assertRaisesRegex(rr.MembershipRefused, "Max players reached"):
            self.document.sign(player, brp.index)
        chi = self.team("CHI")
        a, b = self.document.team_players(sf.index)[0], self.document.team_players(chi.index)[0]
        self.document.swap(a, b)
        self.assertIn(chi.index, a.teams)
        self.assertIn(sf.index, b.teams)
        centers = next(p for p in self.document.players if p.display == "Larry Centers")
        self.assertTrue(self.document.is_free_agent(centers) and centers.teams, "retail lists him on ASW and as a free agent")
        self.document.release(centers, centers.teams[0])
        self.assertEqual(len(self.document.free_agents), 243, "already a free agent: the list does not grow")
        reloaded = rr.load_body(self.document.to_body())
        self.assertEqual(len(reloaded.teams[sf.index].slots), 52)
        self.assertEqual(reloaded.teams[sf.index].player_count, 52)
        self.assertEqual(len(reloaded.free_agents), 243)
        self.assertEqual([p.display for p in reloaded.team_players(chi.index)][0], a.display)
        document = rr.edits_document(self.document)
        replayed, receipt = rr.apply_body(self.body, document)
        self.assertEqual(receipt["log"], [])
        self.assertEqual(replayed, self.document.to_body())
        for prospect in self.document.group_players("draft_class")[:1]:
            with self.assertRaisesRegex(rr.MembershipRefused, "regenerates the draft class"):
                self.document.sign(prospect, sf.index)


class PositionSchemeTests(unittest.TestCase):
    """What a position code MEANS follows the disc's patches, not the retail table."""

    def test_a_scheme_only_renames_and_never_moves_a_code(self) -> None:
        for scheme in rr.POSITION_SCHEMES:
            names = rr.position_names(scheme)
            self.assertEqual(len(names), len(rr.POSITIONS))
            for code in range(len(rr.POSITIONS)):
                # the code a name resolves to is the code it was read from, in every scheme
                self.assertEqual(rr.position_code(names[code], scheme), code)
        self.assertEqual(rr.position_names("retail"), rr.POSITIONS)
        self.assertEqual(rr.position_name(16, "edge"), "EDGE")
        self.assertEqual(rr.position_name(11, "edge"), "ILB", "the EDGE rename moves no linebacker")
        self.assertEqual(rr.position_name(16, "one_pool"), "EDGE")
        self.assertEqual(rr.position_name(11, "one_pool"), "LB")
        self.assertEqual(rr.position_name(15, "one_pool"), "DT")
        self.assertIn("interior", rr.position_long_name(15, "one_pool"))
        self.assertEqual(rr.position_name(10, "one_pool"), "OLB",
                         "the retired code keeps its retail name, the way the game still prints it")

    def test_names_resolve_both_ways_whatever_the_loaded_scheme(self) -> None:
        for scheme in rr.POSITION_SCHEMES:
            self.assertEqual(rr.position_code("EDGE", scheme), 16)
            self.assertEqual(rr.position_code("DE", scheme), 16)
            self.assertEqual(rr.position_code("LB", scheme), 11)
            self.assertEqual(rr.position_code("ILB", scheme), 11)
            self.assertEqual(rr.position_code("OLB", scheme), 10)
            self.assertEqual(rr.position_code("RB", scheme), 7)
            self.assertEqual(rr.position_code("hb", scheme), 7)
            self.assertEqual(rr.position_code(" 15 ", scheme), 15)
        with self.assertRaises(rr.RosterRecordError):
            rr.position_code("NOSE TACKLE")
        with self.assertRaises(rr.RosterRecordError):
            rr.normalise_scheme("three-four")

    def test_the_retired_code_is_named_refused_and_has_a_replacement(self) -> None:
        self.assertEqual(rr.retired_position_codes("retail"), ())
        self.assertEqual(rr.retired_position_codes("edge"), ())
        self.assertEqual(rr.retired_position_codes("one_pool"), (10,))
        self.assertNotIn(10, rr.live_position_codes("one_pool"))
        self.assertIn(10, rr.live_position_codes("retail"))
        self.assertEqual(rr.replacement_position_code(10, "one_pool"), 11)
        self.assertEqual(rr.replacement_position_code(10, "retail"), 10)
        rr.check_position_code(10, "retail")
        rr.check_position_code(11, "one_pool")
        with self.assertRaises(rr.RosterRecordError) as raised:
            rr.check_position_code(10, "one_pool")
        self.assertIn("retired", str(raised.exception))
        self.assertIn("LB", str(raised.exception))

    def test_the_chips_group_by_code_and_one_pool_gains_an_edge_chip(self) -> None:
        self.assertNotIn("EDGE", rr.chip_order("retail"))
        self.assertIn("EDGE", rr.chip_order("one_pool"))
        self.assertEqual(rr.position_groups("retail")["DL"], (15, 16))
        self.assertEqual(rr.position_groups("one_pool")["DL"], (15,))
        self.assertEqual(rr.position_groups("one_pool")["EDGE"], (16,))
        # a stray retired OLB still has a chip that finds him: the game treats enum 10 as an LB
        self.assertEqual(rr.position_groups("one_pool")["LB"], (10, 11))

    def test_detection_reads_one_pool_from_an_empty_olb_code(self) -> None:
        document = rr.load_body(one_pool_body())
        found = rr.detect_scheme_from_data(document)
        self.assertEqual(found["scheme"], "one_pool")
        self.assertEqual(found["confidence"], "high")
        self.assertEqual(found["census"][10], 0)
        self.assertGreater(found["census"][11], 0)
        self.assertGreater(found["census"][16], 0)
        self.assertIn("OLB", found["why"])

    def test_detection_says_retail_while_olb_is_populated_and_admits_the_blind_spot(self) -> None:
        document = rr.load_body(retail_front_body())
        found = rr.detect_scheme_from_data(document)
        self.assertEqual(found["scheme"], "retail")
        self.assertEqual(found["confidence"], "low")
        self.assertEqual(found["census"][10], 2)
        # the EDGE rename is text in the executable and in the historic ROST names, so a roster
        # body cannot show it and the heuristic has to say so rather than guess
        self.assertIn("EDGE rename", found["why"])

    def test_the_secondary_templates_do_not_hide_the_signal(self) -> None:
        document = rr.load_body(one_pool_body())
        # the reclassify pass deliberately leaves the class-generator templates keyed per enum,
        # so counting every pool would find an OLB on a reclassified roster
        self.assertEqual(document.position_census("primary")[10], 0)
        self.assertEqual(document.position_census(None)[10], 0)      # synthetic body has no templates
        self.assertEqual(sum(document.position_census("primary").values()), len(ONE_POOL_SAMPLE))

    def test_detection_reads_a_discs_own_patch_states(self) -> None:
        pools = rr.detect_scheme_from_states({"position_pools": "applied", "edge_rename": "applied",
                                              "scheme_labels": "applied"})
        self.assertEqual(pools["scheme"], "one_pool")
        edge = rr.detect_scheme_from_states({"position_pools": "retail", "edge_rename": "applied",
                                             "scheme_labels": "applied"})
        self.assertEqual(edge["scheme"], "edge")
        disc_only = rr.detect_scheme_from_states({"position_pools": "retail", "edge_rename": "retail",
                                                  "edge_rename_disc": {"status": "applied"}})
        self.assertEqual(disc_only["scheme"], "edge")
        retail = rr.detect_scheme_from_states({"position_pools": "retail", "edge_rename": "retail",
                                               "scheme_labels": "retail"})
        self.assertEqual(retail["scheme"], "retail")
        self.assertEqual(retail["confidence"], "high")
        unknown = rr.detect_scheme_from_states({})
        self.assertEqual(unknown["scheme"], "retail")
        self.assertEqual(unknown["confidence"], "low")

    def test_detection_reports_a_disagreement_instead_of_hiding_it(self) -> None:
        # an executable carrying the pools over a roster nobody reclassified is a real broken state
        half = rr.detect_scheme(rr.load_body(retail_front_body()),
                                states={"position_pools": "applied", "edge_rename": "applied"})
        self.assertEqual(half["scheme"], "one_pool")
        self.assertIn("retired OLB code", half["note"])
        # and the other way round: the roster is reclassified, the executable is not
        other = rr.detect_scheme(rr.load_body(one_pool_body()),
                                 states={"position_pools": "retail", "edge_rename": "retail"})
        self.assertEqual(other["scheme"], "one_pool")
        self.assertIn("follow the roster", other["note"])
        agreed = rr.detect_scheme(rr.load_body(one_pool_body()),
                                  states={"position_pools": "applied", "edge_rename": "applied"})
        self.assertEqual(agreed["scheme"], "one_pool")
        self.assertEqual(agreed["note"], "")

    def test_a_document_reads_its_codes_through_the_scheme_it_is_given(self) -> None:
        document = rr.load_body(one_pool_body(), scheme="one_pool")
        self.assertEqual(document.scheme, "one_pool")
        names = {p.display: p.record.position_name for p in document.players}
        self.assertEqual(names["Ray Lewis"], "LB")
        self.assertEqual(names["Terrell Suggs"], "EDGE")
        self.assertEqual(names["Kelly Gregg"], "DT")
        document.set_scheme("retail")
        self.assertEqual(document.players[0].record.scheme, "retail")
        names = {p.display: p.record.position_name for p in document.players}
        self.assertEqual(names["Ray Lewis"], "ILB")
        self.assertEqual(names["Terrell Suggs"], "DE")
        self.assertEqual(document.summary()["scheme"], "retail")

    def test_ratings_stay_keyed_by_the_code(self) -> None:
        # the game's per-position rating labels come from the enum, so renaming must not move a
        # player onto another position's weighting
        self.assertEqual(rr.rating_profile(11), "ILB")
        self.assertEqual(rr.rating_profile(16), "DE")
        self.assertEqual(rr.OVERALL_WEIGHTS_BY_CODE[11], rr.OVERALL_WEIGHTS["ILB"])
        self.assertEqual(rr.OVERALL_WEIGHTS_BY_CODE[16], rr.OVERALL_WEIGHTS["DE"])
        self.assertEqual(rr.OVERALL_WEIGHTS_BY_CODE[10], rr.OVERALL_WEIGHTS["OLB"])
        self.assertIn("pass_rush", rr.key_ratings(16))
        self.assertIn("tackle", rr.key_ratings(11))
        retail = rr.load_body(one_pool_body())
        one_pool = rr.load_body(one_pool_body(), scheme="one_pool")
        for a, b in zip(retail.players, one_pool.players):
            self.assertEqual(a.record.overall(), b.record.overall(),
                             "the OVR estimate is the same number under either label")

    def test_jersey_ranges_and_validation_follow_the_code(self) -> None:
        self.assertEqual(rr.jersey_range(16), (50, 99))
        self.assertEqual(rr.jersey_range(11), (40, 59))
        self.assertEqual(rr.JERSEY_RANGES["DE"], rr.JERSEY_RANGES_BY_CODE[16])
        document = rr.load_body(one_pool_body(), scheme="one_pool")
        suggs = next(p for p in document.players if p.last == "Suggs")
        findings = rr.validate(document, [suggs])
        self.assertFalse([f for f in findings if f["check"] == "jersey"],
                         "#55 is legal for an EDGE because the range is keyed by code 16")
        suggs.record.set("jersey", 12)
        detail = [f for f in rr.validate(document, [suggs]) if f["check"] == "jersey"]
        self.assertEqual(len(detail), 1)
        self.assertIn("EDGE", detail[0]["detail"])

    def test_validation_flags_a_player_parked_on_the_retired_code(self) -> None:
        document = rr.load_body(retail_front_body(), scheme="one_pool")
        stray = next(p for p in document.players if p.last == "Boulware")
        findings = [f for f in rr.validate(document, [stray]) if f["check"] == "position"]
        self.assertEqual(len(findings), 1)
        self.assertIn("retired", findings[0]["detail"])
        clean = rr.load_body(retail_front_body(), scheme="retail")
        self.assertFalse([f for f in rr.validate(clean) if f["check"] == "position"])

    def test_the_document_refuses_to_write_a_retired_code(self) -> None:
        document = rr.load_body(one_pool_body(), scheme="one_pool")
        player = next(p for p in document.players if p.last == "Lewis")
        with self.assertRaises(rr.RosterRecordError):
            document.set_position(player, "OLB")
        self.assertEqual(player.record.values["position"], 11)
        self.assertEqual(document.set_position(player, "EDGE"), 16)
        self.assertEqual(player.record.values["position"], 16)
        retail = rr.load_body(retail_front_body(), scheme="retail")
        self.assertEqual(retail.set_position(retail.players[0], "OLB"), 10)

    def test_the_depth_chart_is_per_code(self) -> None:
        document = rr.load_body(one_pool_body(), scheme="one_pool")
        chart = document.depth_chart(2)
        self.assertEqual(sorted(chart), [11, 15, 16])
        self.assertEqual([p.last for p in chart[16]],
                         [p.last for p in sorted(chart[16], key=lambda q: q.record.values["depth_rank"])])
        suggs = next(p for p in document.players if p.last == "Suggs")
        nth, of = document.depth_slot(2, suggs)
        self.assertEqual(of, 3)
        self.assertTrue(1 <= nth <= 3)

    def test_a_global_edit_selects_positions_by_code(self) -> None:
        document = rr.load_body(one_pool_body(), scheme="one_pool")
        by_new_name = rr.global_edit_preview(document, attribute="speed", mode="equal", value=70,
                                             positions=["EDGE"])
        by_old_name = rr.global_edit_preview(document, attribute="speed", mode="equal", value=70,
                                             positions=["DE"])
        self.assertTrue(by_new_name)
        self.assertEqual([row["name"] for row in by_new_name], [row["name"] for row in by_old_name])
        self.assertTrue(all(row["position"] == "EDGE" for row in by_new_name))
        with self.assertRaises(rr.RosterRecordError):
            rr.global_edit_preview(document, attribute="position", mode="equal", value=10)

    def test_a_roster_edit_never_writes_the_retired_code_into_a_reclassified_roster(self) -> None:
        source = rr.load_body(retail_front_body(), scheme="retail")
        lewis = next(p for p in source.players if p.last == "Lewis")
        lewis.record.set("position", 10)                       # authored against a retail roster
        document = rr.edits_document(source, name="retail edit")
        self.assertEqual(document["edits"][0]["fields"]["position"], 10)

        body, receipt = rr.apply_body(one_pool_body(), document)
        landed = rr.load_body(body)
        moved = next(p for p in landed.players if p.last == "Lewis")
        self.assertEqual(moved.record.values["position"], 11,
                         "the target roster is reclassified, so the OLB code is mapped to LB")
        self.assertEqual(len([line for line in receipt["log"] if "retired" in line]), 1)

        # and onto a roster that still uses the retail codes it writes exactly what was authored
        body, receipt = rr.apply_body(retail_front_body(), document)
        kept = next(p for p in rr.load_body(body).players if p.last == "Lewis")
        self.assertEqual(kept.record.values["position"], 10)
        self.assertEqual(receipt["log"], [])
        # an explicit scheme wins over the detection
        body, receipt = rr.apply_body(one_pool_body(), document, scheme="retail")
        forced = next(p for p in rr.load_body(body).players if p.last == "Lewis")
        self.assertEqual(forced.record.values["position"], 10)

    def test_a_csv_round_trips_under_each_scheme(self) -> None:
        for scheme, expected in (("retail", "ILB"), ("edge", "ILB"), ("one_pool", "LB")):
            document = rr.load_body(one_pool_body(), scheme=scheme)
            text = rr.export_csv(document)
            positions = [line.split(",")[5] for line in text.splitlines()[1:]]
            self.assertIn(expected, positions, f"{scheme} names its own codes in the CSV")
            reloaded = rr.load_body(one_pool_body(), scheme=scheme)
            receipt = rr.import_csv(reloaded, text)
            self.assertEqual(receipt["fields"], 0, "an unedited export changes nothing on import")
            self.assertEqual(receipt["log"], [])
            self.assertEqual(reloaded.to_body(), document.to_body())

    def test_a_csv_written_on_a_retail_disc_loads_onto_a_one_pool_roster(self) -> None:
        source = rr.load_body(retail_front_body(), scheme="retail")
        text = rr.export_csv(source)
        self.assertIn("OLB", text)
        target = rr.load_body(one_pool_body(), scheme="one_pool")
        receipt = rr.import_csv(target, text)
        moved = {p.last: p.record.values["position"] for p in target.players}
        self.assertEqual(moved["Boulware"], 11, "an OLB row lands on LB, not on the retired code")
        self.assertEqual(moved["Thomas"], 11)
        notes = [line for line in receipt["log"] if "retired" in line]
        self.assertEqual(len(notes), 2, "and the receipt says so for every row it moved")
        self.assertIn("LB (code 11)", notes[0])
        # the EDGE / LB names of a one-pool export read straight back onto a retail roster
        back = rr.load_body(retail_front_body(), scheme="retail")
        receipt = rr.import_csv(back, rr.export_csv(rr.load_body(one_pool_body(), scheme="one_pool")))
        self.assertEqual(receipt["log"], [])
        self.assertEqual(back.players[len(SAMPLE) + 1].record.values["position"], 16)


@unittest.skipUnless(HAVE_RETAIL, "the retail extraction is not mounted")
class RetailPositionSchemeTests(unittest.TestCase):
    """The detection heuristic against the real roster, before and after the shipped pass."""

    def test_the_retail_roster_detects_as_retail_with_the_measured_census(self) -> None:
        document = rr.load_body(retail_body())
        found = rr.detect_scheme_from_data(document)
        self.assertEqual(found["scheme"], "retail")
        self.assertEqual(found["census"], rr.RETAIL_PRIMARY_POSITION_CENSUS)
        self.assertEqual(found["census"][10], 191)

    def test_the_reclassified_roster_detects_as_one_pool(self) -> None:
        body = reclassified_retail_body()
        self.assertNotEqual(body, retail_body())
        document = rr.load_body(body)
        found = rr.detect_scheme_from_data(document)
        self.assertEqual(found["scheme"], "one_pool")
        self.assertEqual(found["confidence"], "high")
        census = found["census"]
        self.assertEqual(census[10], 0, "the pass empties the OLB code")
        self.assertEqual(census[11], 305)
        self.assertEqual(census[15], 208)
        self.assertEqual(census[16], 196)
        self.assertEqual(sum(census.values()), rr.RETAIL_PRIMARY_COUNT)
        # the templates the pass leaves alone still carry an OLB, which is why the census is
        # primary-pool only
        self.assertEqual(document.position_census("secondary")[10], 4)

    def test_the_detector_reads_the_real_executables_own_patch_states(self) -> None:
        from mod_editor.core import nfl2k5_edge_rename as edge_rename
        from mod_editor.core import nfl2k5_modern_positions as modern_positions
        from mod_editor.core import nfl2k5_position_pools as position_pools

        xbe = RETAIL_XBE.read_bytes()

        def states(payload: bytes) -> dict[str, str]:
            return {"edge_rename": edge_rename.status(payload),
                    "scheme_labels": modern_positions.status(payload),
                    "position_pools": position_pools.status(payload)}

        self.assertEqual(rr.detect_scheme_from_states(states(xbe))["scheme"], "retail")
        edged, _receipt = edge_rename.apply(xbe)
        self.assertEqual(rr.detect_scheme_from_states(states(edged))["scheme"], "edge")
        labelled, _receipt = modern_positions.apply(edged, three_four_line=True)
        self.assertEqual(rr.detect_scheme_from_states(states(labelled))["scheme"], "edge",
                         "the depth-chart slot labels never move a roster code")
        pooled, _receipt = position_pools.apply(labelled)
        self.assertEqual(rr.detect_scheme_from_states(states(pooled))["scheme"], "one_pool")
        # and the two halves of a real one-pool disc agree, so nothing is flagged
        whole = rr.detect_scheme(rr.load_body(reclassified_retail_body()), states=states(pooled))
        self.assertEqual(whole["scheme"], "one_pool")
        self.assertEqual(whole["note"], "")
        # while the executable alone, over an un-reclassified roster, is called out
        half = rr.detect_scheme(rr.load_body(retail_body()), states=states(pooled))
        self.assertEqual(half["scheme"], "one_pool")
        self.assertIn("191", half["note"])

    def test_inspect_states_reads_a_real_executable_through_mod_build(self) -> None:
        found = rr.inspect_states(RETAIL_XBE)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(sorted(found), ["edge_rename", "edge_rename_disc", "position_pools",
                                         "scheme_labels"])
        self.assertEqual(found["edge_rename"], "retail")
        self.assertEqual(found["scheme_labels"], "retail")
        self.assertEqual(rr.detect_scheme_from_states(found)["scheme"], "retail")
        # a pack folder has no executable to read, and detection must fall back rather than raise
        self.assertIsNone(rr.inspect_states(RETAIL_EXTRACTION))
        fallback = rr.detect_scheme(rr.load_body(reclassified_retail_body()),
                                    source=RETAIL_EXTRACTION)
        self.assertEqual(fallback["scheme"], "one_pool")
        self.assertEqual(fallback["source"], "roster data")

    def test_the_reclassified_roster_reads_and_writes_under_the_one_pool_names(self) -> None:
        document = rr.load_body(reclassified_retail_body(), scheme="one_pool")
        names = {p.record.position_name for p in document.by_pool("primary")}
        self.assertIn("EDGE", names)
        self.assertIn("LB", names)
        self.assertNotIn("ILB", names)
        self.assertNotIn("DE", names)
        edge = next(p for p in document.by_pool("primary") if p.record.position_name == "EDGE")
        self.assertEqual(edge.record.rating_profile, "DE", "an EDGE keeps the defensive-end card set")
        with self.assertRaises(rr.RosterRecordError):
            document.set_position(edge, "OLB")
        text = rr.export_csv(document, document.by_pool("primary")[:50])
        self.assertNotIn(";OLB;", text)
        reloaded = rr.load_body(reclassified_retail_body(), scheme="one_pool")
        receipt = rr.import_csv(reloaded, text)
        self.assertEqual(receipt["log"], [])
        self.assertEqual(receipt["fields"], 0)


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------------------------- version-0 saves
def synthetic_save_v0(body: bytes | None = None, *, suffix: bytes = bytes(0x1000)) -> bytes:
    """The runtime-arena layout every real SAVEGAME.DAT carries (found by GPT-6 Astra, 2026-09-04).

    File-relative: a 0x20-byte wrapper at 0x2E0 (``ROST`` + declared length 0x91020), the ROST preamble at
    0x300 with version 0 and a relative pointer to the object at 0x320, then the 0x91000-byte arena.  The
    object is the disc object moved 0x20 bytes closer to the preamble; every pointer inside it is field-
    relative, so the bytes after the object are the disc body's bytes after ITS object.
    """

    body = synthetic_body() if body is None else body
    arena = bytearray(body[rr.OBJ_OFF:]) + bytes(0x91000 - (len(body) - rr.OBJ_OFF))
    preamble = bytes(12) + b"ROST" + struct.pack("<Ii", 0, 0x20 - 0x14 + 1) + bytes(8)      # 0x20 bytes
    wrapper = b"ROST" + struct.pack("<I", 0x20 + 0x91000) + bytes(0x18)
    return bytes(0x2E0) + wrapper + preamble + bytes(arena) + suffix


class VersionZeroSaveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = synthetic_body()
        self.savegame = synthetic_save_v0(self.body)

    def test_find_block_base_lands_on_the_real_save_preamble(self) -> None:
        self.assertEqual(rr.find_block_base(self.savegame), 0x300)
        self.assertEqual(rr.find_block_base(self.body + bytes(224)), 0)          # the disc-layout save still works

    def test_the_document_reads_the_arena_like_the_disc_body(self) -> None:
        document = rr.RosterDocument(self.savegame, base=0x300, source="save")
        disc = rr.RosterDocument(self.body)
        self.assertEqual(document.version, 0)
        self.assertEqual(disc.version, 17)
        self.assertEqual([(p.first, p.last) for p in document.players], [(p.first, p.last) for p in disc.players])
        self.assertEqual([t.abbreviation for t in document.teams], [t.abbreviation for t in disc.teams])
        self.assertEqual(document.to_body(), self.savegame)
        self.assertEqual(document.diff(), [])

    def test_unknown_versions_are_refused(self) -> None:
        bad = bytearray(self.savegame)
        struct.pack_into("<I", bad, 0x310, 3)
        with self.assertRaisesRegex(rr.RosterRecordError, "version 3"):
            rr.RosterDocument(bytes(bad), base=0x300)
        with self.assertRaisesRegex(rr.RosterRecordError, "no ROST block"):
            rr.find_block_base(bytes(bad))

    def test_edit_rename_and_resign_a_version_zero_save(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "src" / "53450030" / "0001"
            source.mkdir(parents=True)
            (source / "SAVEGAME.DAT").write_bytes(self.savegame)
            (source / "EXTRA").write_bytes(rr.sign_save(self.savegame))
            (source / "SaveMeta.xbx").write_bytes(b"meta")
            document = rr.load_save(source.parent.parent)
            self.assertEqual(document.version, 0)
            player = document.players[0]
            player.record.set("speed", 88)
            document.set_name(player, "last", "Zed")
            target = Path(td) / "out"
            receipt = rr.save_document(document, target)
            self.assertTrue(receipt["signed"])
            back = rr.load_save(target)
            self.assertEqual(back.container.verified, True)
            self.assertEqual((back.players[0].record.values["speed"], back.players[0].last), (88, "Zed"))
            self.assertEqual((target / "53450030" / "0001" / "SaveMeta.xbx").read_bytes(), b"meta")
            written = (target / "53450030" / "0001" / "SAVEGAME.DAT").read_bytes()
            self.assertEqual(len(written), len(self.savegame))
            self.assertEqual(written[:0x320], self.savegame[:0x320])              # wrapper + preamble untouched


REAL_SAVES = Path(os.environ.get("NFL2K5_SAVE_FIXTURES", str(Path.home() / "Desktop" / "2K5-8 Editors" / "save_fixtures")))


def _carries_roster_arena(path: Path) -> bool:
    """Only franchise / roster saves hold the ROST arena; the team, profile and settings saves in the
    same fixture folder are other formats and are not this module's business."""

    try:
        rr.find_block_base(path.read_bytes())
    except (rr.RosterRecordError, OSError):
        return False
    return True


REAL_SAVE_FILES = ([path for path in sorted(REAL_SAVES.glob("*/UDATA/53450030/*/SAVEGAME.DAT"))
                    if _carries_roster_arena(path)] if REAL_SAVES.is_dir() else [])


@unittest.skipUnless(REAL_SAVE_FILES, "no real signed saves (set NFL2K5_SAVE_FIXTURES to a folder of <name>/UDATA/...)")
class RealSaveTests(unittest.TestCase):
    """Every real HMAC-verified save on this machine loads, round-trips and re-signs (private fixtures)."""

    def test_every_real_save_round_trips_and_resigns(self) -> None:
        for path in REAL_SAVE_FILES:
            with self.subTest(save=path.parts[-5]):
                document = rr.load_save(path, detect=True)
                self.assertEqual(document.version, 0)
                self.assertEqual(document.base, 0x300)
                self.assertGreaterEqual(len(document.players), 2000)
                self.assertEqual(len(document.teams), 52)
                self.assertEqual(document.to_body(), path.read_bytes())
                self.assertEqual(document.diff(), [])
                player = document.players[0]
                player.record.set("speed", 88)
                with tempfile.TemporaryDirectory() as td:
                    rr.save_document(document, Path(td) / "copy")
                    back = rr.load_save(Path(td) / "copy")
                    self.assertTrue(back.container.verified)
                    self.assertEqual(back.players[0].record.values["speed"], 88)

    def test_membership_moves_survive_a_real_save_round_trip(self) -> None:
        for path in REAL_SAVE_FILES:
            with self.subTest(save=path.parts[-5]):
                document = rr.load_save(path)
                self.assertEqual(document.free_agent_capacity, 2500, "the runtime arena keeps the same 2,500-slot list")
                prospects = document.group_players("draft_class")
                self.assertGreater(len(prospects), 0, "the runtime's prospect flag (+0x08 bit 4) reads as the draft class")
                self.assertTrue(all(p.record.values["player_type"] & rr.FLAG_PROSPECT or p.record.values["player_type"] == 0
                                    for p in prospects))
                # a franchise off-season can carry a club above the 54 cap, so pick the smallest club
                club = min(document.teams[:32], key=lambda t: len(t.slots))
                before = len(club.slots)
                player = document.team_players(club.index)[-1]
                document.release(player, club.index)
                signed = document.by_offset[document.original_free_agents[0]]
                document.sign(signed, club.index)
                with tempfile.TemporaryDirectory() as td:
                    rr.save_document(document, Path(td) / "copy")
                    back = rr.load_save(Path(td) / "copy")
                    self.assertTrue(back.container.verified)
                    self.assertEqual(len(back.teams[club.index].slots), before)
                    self.assertEqual(back.teams[club.index].player_count, before)
                    self.assertEqual(back.team_players(club.index)[-1].display, signed.display)
                    self.assertEqual(back.by_offset[back.free_agents[-1]].display, player.display)
                    self.assertEqual(len(back.free_agents), len(document.original_free_agents))

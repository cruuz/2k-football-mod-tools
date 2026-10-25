"""b778-eq1: a created player takes his position's template gear, never the zero (kicker) mask."""

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_equipment_fit as equip  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
import test_nfl2k5_roster_records as fixture  # noqa: E402

# One gear set per template.  The values are in every field's range and differ template to template,
# so a test can tell which of the position's four records a player took.
GEAR = (
    {"helmet": 1, "face_mask": 23, "face_shield": 0, "mouthpiece": 0, "eye_black": 0,
     "turtleneck": 0, "sleeves": 0, "neck_roll": 0, "left_glove": 8, "right_glove": 8,
     "left_wrist": 1, "right_wrist": 1, "left_elbow": 0, "right_elbow": 0, "left_shoe": 1,
     "right_shoe": 1},
    {"helmet": 0, "face_mask": 15, "face_shield": 1, "mouthpiece": 1, "eye_black": 1,
     "turtleneck": 1, "sleeves": 1, "neck_roll": 1, "left_glove": 7, "right_glove": 6,
     "left_wrist": 3, "right_wrist": 4, "left_elbow": 2, "right_elbow": 3, "left_shoe": 2,
     "right_shoe": 3},
    {"helmet": 1, "face_mask": 12, "face_shield": 2, "mouthpiece": 0, "eye_black": 0,
     "turtleneck": 2, "sleeves": 2, "neck_roll": 2, "left_glove": 5, "right_glove": 4,
     "left_wrist": 5, "right_wrist": 6, "left_elbow": 4, "right_elbow": 5, "left_shoe": 4,
     "right_shoe": 5},
    {"helmet": 0, "face_mask": 17, "face_shield": 0, "mouthpiece": 1, "eye_black": 1,
     "turtleneck": 3, "sleeves": 3, "neck_roll": 3, "left_glove": 3, "right_glove": 2,
     "left_wrist": 7, "right_wrist": 8, "left_elbow": 6, "right_elbow": 7, "left_shoe": 6,
     "right_shoe": 0},
)


def with_templates(body: bytes, *positions: int) -> bytes:
    """Append four secondary templates per position to a synthetic body."""

    raw = bytearray(body)
    count_field, table_field = rr.POOL_FIELDS["secondary"]
    relative = struct.unpack_from("<i", raw, table_field)[0]
    table = table_field + relative - 1 if relative else fixture.PLAYERS_OFF + len(fixture.SAMPLE) * rr.PLAYER_SIZE
    struct.pack_into("<I", raw, count_field, len(positions) * len(GEAR))
    if not relative:
        struct.pack_into("<i", raw, table_field, table - table_field + 1)
    for position_index, position in enumerate(positions):
        for slot, gear in enumerate(GEAR):
            offset = table + (position_index * len(GEAR) + slot) * rr.PLAYER_SIZE
            record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE), scheme="one_pool", reference_year=2026)
            record.set("position", position)
            record.set("player_type", rr.FLAG_NFL_PLAYER)
            for name, value in gear.items():
                record.set(name, value)
            raw[offset:offset + rr.PLAYER_SIZE] = record.encode()
    return bytes(raw)


def zero_player(document, index: int, position: int):
    """A primary record created the way the pipeline creates one: decoded from zero."""

    player = document.players[index]
    player.record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE), scheme="one_pool", reference_year=2026)
    player.record.set("position", position)
    player.record.set("player_type", rr.FLAG_NFL_PLAYER)
    return player


class EquipmentFitTests(unittest.TestCase):
    def test_the_field_list_is_the_games_gear_not_identity(self) -> None:
        for name in equip.EQUIPMENT_FIELDS:
            self.assertTrue(name in rr.FIELD_BY_NAME or name in rr.COMPOSITE_FIELDS, name)
            self.assertNotIn(name, equip.NOT_EQUIPMENT)
        # the kicker look this job fixes is Face Mask 1 (raw 0) plus the empty gear around it
        self.assertEqual(rr.FACE_MASKS[0], "Face Mask 1")
        self.assertIn("face_mask", equip.EQUIPMENT_FIELDS)
        self.assertIn("face_shield", equip.EQUIPMENT_FIELDS)

    def test_a_created_receiver_takes_receiver_gear_not_the_kicker_mask(self) -> None:
        body = with_templates(fixture.synthetic_body(), rr.POSITIONS.index("WR"))
        document = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
        player = zero_player(document, 0, rr.POSITIONS.index("WR"))
        self.assertEqual(player.record.get("face_mask"), 0)
        changed = equip.fill_created_player(document, player)
        expected = GEAR[0 % len(GEAR)]
        for name, value in expected.items():
            self.assertEqual(player.record.get(name), value, name)
            if value:
                self.assertEqual(changed[name], value, name)
        self.assertEqual(set(changed), {name for name, value in expected.items() if value})
        self.assertEqual(document.by_pool("secondary")[0].record.get("face_mask"), 23)
        # and skin, face, body, hair, hand and the portrait stay with the appearance pipeline
        for name in equip.NOT_EQUIPMENT:
            self.assertEqual(player.record.get(name), 0, name)

    def test_the_stable_index_picks_among_the_positions_four_templates(self) -> None:
        body = with_templates(fixture.synthetic_body(), rr.POSITIONS.index("WR"))
        document = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
        seen = set()
        for index in range(4):
            player = zero_player(document, index, rr.POSITIONS.index("WR"))
            equip.fill_created_player(document, player)
            mask = player.record.get("face_mask")
            self.assertEqual(mask, GEAR[index % len(GEAR)]["face_mask"])
            seen.add(mask)
        self.assertEqual(len(seen), 4, "the four position templates must not collapse to one look")

    def test_a_kicker_gets_the_kicker_template_gear(self) -> None:
        body = with_templates(fixture.synthetic_body(), rr.POSITIONS.index("K"))
        document = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
        player = zero_player(document, 2, rr.POSITIONS.index("K"))
        equip.fill_created_player(document, player)
        self.assertEqual(player.record.get("face_mask"), GEAR[2]["face_mask"])

    def test_a_row_that_names_its_own_gear_keeps_it(self) -> None:
        body = with_templates(fixture.synthetic_body(), rr.POSITIONS.index("WR"))
        document = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
        player = zero_player(document, 0, rr.POSITIONS.index("WR"))
        player.record.set("face_mask", 7)
        player.record.set("sleeves", 3)
        changed = equip.fill_created_player(document, player, supplied={"face_mask": 7, "sleeves": 3})
        self.assertEqual(player.record.get("face_mask"), 7)
        self.assertEqual(player.record.get("sleeves"), 3)
        self.assertNotIn("face_mask", changed)
        self.assertNotIn("sleeves", changed)
        self.assertEqual(player.record.get("left_glove"), GEAR[0]["left_glove"])

    def test_a_body_without_the_secondary_table_is_left_alone(self) -> None:
        document = rr.RosterDocument(fixture.synthetic_body(), scheme="one_pool", reference_year=2026)
        self.assertEqual(document.by_pool("secondary"), [])
        before = player = document.players[0]
        raw = before.record.encode()
        self.assertEqual(equip.fill_created_player(document, player), {})
        self.assertEqual(player.record.encode(), raw)

    def test_named_created_records_are_filled_in_place_and_replay_is_empty(self) -> None:
        body = with_templates(fixture.synthetic_body(), rr.POSITIONS.index("WR"))
        document = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
        for index in range(4):
            zero_player(document, index, rr.POSITIONS.index("WR"))
        filled = equip.fill_created_players(document, range(3))
        self.assertEqual(sorted(filled), [0, 1, 2])
        self.assertEqual(document.players[3].record.get("face_mask"), 0)
        result = document.to_body()
        again = rr.RosterDocument(result, scheme="one_pool", reference_year=2026)
        self.assertEqual(equip.fill_created_players(again, range(3)), {})

    def test_the_native_class_generator_copies_these_gear_fields_from_the_templates(self):
        # The generator (FUN_000E6780) is what gives a generated rookie his position look.  Its rewritten
        # table loop must still copy every gear field the kicker look depends on; face_mask, visor, sleeves,
        # mouthpiece, gloves, wrists, elbows, turtleneck, eye black and shoes are all in the table.
        from mod_editor.core import nfl2k5_alien_prospect as alien
        start = alien.SYMBOLS["table"] - alien.CODE_VA
        end = alien.SYMBOLS["table_end"] - alien.CODE_VA
        table = alien.CODE[start:end]
        self.assertEqual(len(table), 17 * 6, "the generator still makes 17 coin blocks")
        covered = set()
        for index in range(0, len(table), 6):
            mask, offset, _flags = struct.unpack_from("<IBB", table, index)
            for field in rr.FIELDS:
                if offset <= field.offset and field.offset + field.size <= offset + 4:
                    bits = ((1 << field.width) - 1) << ((field.offset - offset) * 8 + field.shift)
                    if mask & bits == bits:
                        covered.add(field.name)
        for name in ("face_mask", "face_shield", "sleeves", "mouthpiece", "eye_black", "turtleneck",
                     "left_glove_low", "left_glove_high", "right_glove", "left_wrist_low", "left_wrist_high",
                     "right_wrist", "left_elbow_low", "left_elbow_high", "right_elbow",
                     "left_shoe", "right_shoe"):
            self.assertIn(name, covered)

    def test_the_retail_templates_give_kickers_the_two_bar_and_receivers_an_open_mask(self):
        if not fixture.HAVE_RETAIL:
            self.skipTest("private USA retail roster archive is absent")
        document = rr.RosterDocument(fixture.retail_body(), scheme="retail")
        kickers = equip.templates_for_position(document, rr.POSITIONS.index("K"))
        receivers = equip.templates_for_position(document, rr.POSITIONS.index("WR"))
        self.assertEqual((len(kickers), len(receivers)), (4, 4))
        self.assertTrue(any(t.record.get("face_mask") == 0 for t in kickers),
                        "the retail kicker template proves raw 0 is the two-bar kicker mask")
        self.assertFalse(any(t.record.get("face_mask") == 0 for t in receivers),
                         "the retail receiver templates do not use the kicker mask")


if __name__ == "__main__":
    unittest.main()

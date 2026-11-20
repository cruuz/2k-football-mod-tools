"""b81 lane finn-r2: Heal Player(s) (Finn's HealAction, parity row E8) and Paste Exact Copy (E3).

Heal writes exactly what the game's own recovery routine 0xE6680 writes (RE_FACTS section 2; the receipt
game-tick.json holds the retail routine run on real records), not Finn's two bytes.  Paste exact copy is Paste
plus names (through the shared name pool), college, play-by-play id and photo id, with the target's slot state,
injury and own career-history link kept.

Offscreen Qt on synthetic rosters, plus the signed SOFTDRINK franchise and roster saves when they are present.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_player_health as ph  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402
from test_nfl2k5_roster_records import synthetic_body  # noqa: E402

SOFTDRINK_ROSTER_SAVE = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_ROSTER_SAVE",
    "/media/noah/Storage/2K5-project/beta81/isolated-data/FC3-native-roster.zip"))
SOFTDRINK_FRANCHISE_SIGNED = Path(os.environ.get(
    "NFL2K5_SOFTDRINK_FRANCHISE_SIGNED",
    "/media/noah/Storage/2K5-project/beta81/cpu-sim/catalog-disc-128-dynasty-signed/2026"))
GAME_TICK = Path(os.environ.get(
    "NFL2K5_FINN_R2_GAME_TICK",
    "/home/noah/2k-worktrees/.b77-scratch/b81/finn-r2/re/game-tick.json"))

INJURY_BYTES = {0x22, 0x23, 0x27, 0x28, 0x29}


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def raw_record(document: rr.RosterDocument, player: rr.Player) -> bytes:
    return bytes(document.to_body()[player.offset: player.offset + rr.PLAYER_SIZE])


def with_injury(record: rr.PlayerRecord, w20: int, w24: int, w28: int) -> rr.PlayerRecord:
    """A copy of ``record`` whose three injury dwords are exactly these (through the real encoder/decoder)."""

    raw = bytearray(record.encode())
    struct.pack_into("<I", raw, 0x20, w20)
    struct.pack_into("<I", raw, 0x24, w24)
    struct.pack_into("<H", raw, 0x28, w28)
    return rr.PlayerRecord.decode(bytes(raw), record.scheme)


def game_clear(raw: bytes, franchise: bool) -> bytes:
    """An independent byte-level statement of the game's 0xE6680 (and of the roster-save bit 30 rule)."""

    out = bytearray(raw)
    w20, w24 = struct.unpack_from("<II", raw, 0x20)
    (w28,) = struct.unpack_from("<H", raw, 0x28)
    w20 = (w20 & 0x003FFFFF) | (0x40000000 if franchise else 0)
    struct.pack_into("<I", out, 0x20, w20)
    struct.pack_into("<I", out, 0x24, w24 & 0x8FFFFFFF)
    struct.pack_into("<H", out, 0x28, w28 & 0xFC00)
    return bytes(out)


class _Synthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()
        self.panel.load_document(rr.load_body(synthetic_body()), label="synthetic")
        self.application.processEvents()
        self.document = self.panel.document
        self.by_last = {p.last: p for p in self.document.players}

    def tearDown(self) -> None:
        self.panel.close()
        self.panel.deleteLater()
        self.application.processEvents()

    def hurt(self, player: rr.Player, *, weeks: int = 5, status: int = 4, injury_id: int = 0x187,
             known: bool = False, depth: int = 0x24, b27_bit7: int = 0) -> None:
        values = player.record.values
        values["unknown_20_high"] = 0x200 | (0x100 if known else 0) | weeks
        values["unknown_27_high"] = status | (b27_bit7 << 3)
        values["injured_reserve"] = injury_id & 0xFF
        values["unknown_29_low"] = injury_id >> 8
        values["depth_rank"] = depth & 7
        values["depth_side"] = (depth >> 3) & 7


# ------------------------------------------------------------------------------------------------ heal: core rule
class HealCoreTests(_Synthetic):
    def test_the_fields_are_what_the_record_map_says(self) -> None:
        for name, (offset, bit, width) in {"unknown_20_high": (0x20, 22, 10), "unknown_27_high": (0x27, 4, 4),
                                           "injured_reserve": (0x28, 0, 8), "unknown_29_low": (0x28, 8, 2)}.items():
            field = rr.FIELD_BY_NAME[name]
            self.assertEqual((field.offset, field.shift, field.width), (offset, bit, width), name)

    def test_hurt_means_any_of_the_four_signs(self) -> None:
        player = self.by_last["Manning"]
        self.assertFalse(ph.hurt(player.record))
        for key, value in (("unknown_20_high", 0x200), ("unknown_20_high", 3), ("unknown_27_high", 4),
                           ("injured_reserve", 9), ("unknown_29_low", 2)):
            with self.subTest(key=key, value=value):
                record = player.record.copy()
                record.values[key] = value
                self.assertTrue(ph.hurt(record))
        record = player.record.copy()
        record.values["unknown_20_high"] = 0x100              # bit 30 alone is "injury known", not an injury
        record.values["unknown_27_high"] = 8                  # +0x27 bit 7 alone is not a status
        self.assertFalse(ph.hurt(record))

    def test_franchise_sets_bit_30_and_a_roster_save_does_not(self) -> None:
        self.hurt(self.by_last["Manning"], weeks=17, status=4, injury_id=0x2F4, known=False)
        record = self.by_last["Manning"].record
        self.assertEqual(ph.heal_values(record, True)["unknown_20_high"], 0x100)
        self.assertEqual(ph.heal_values(record, False)["unknown_20_high"], 0)
        for franchise in (True, False):
            values = ph.heal_values(record, franchise)
            self.assertEqual((values["injured_reserve"], values["unknown_29_low"]), (0, 0))
            self.assertEqual(values["unknown_27_high"], 0)

    def test_bit_7_of_plus_0x27_and_the_depth_bits_are_kept(self) -> None:
        self.hurt(self.by_last["Manning"], status=7, b27_bit7=1, depth=0x2D, injury_id=0x3FF)
        record = self.by_last["Manning"].record
        self.assertEqual(record.values["unknown_27_high"], 0xF)
        self.assertEqual(ph.heal_values(record, True)["unknown_27_high"], 0x8)
        raw = record.encode()
        healed = record.copy()
        healed.values.update(ph.heal_values(record, True))
        after = healed.encode()
        self.assertEqual(after[0x28:0x2A], struct.pack("<H", struct.unpack_from("<H", raw, 0x28)[0] & 0xFC00))
        self.assertEqual(after[0x24:0x28], struct.pack("<I", struct.unpack_from("<I", raw, 0x24)[0] & 0x8FFFFFFF))
        self.assertEqual(after[0x27] & 0x80, 0x80, "+0x27 bit 7 (+0x24 bit 31) stays")

    def test_the_result_matches_the_game_routine_on_random_records_and_only_five_bytes_move(self) -> None:
        rng = random.Random(0xE6680)
        base = self.by_last["Manning"].record
        for _ in range(400):
            franchise = rng.random() < 0.5
            record = with_injury(base, rng.getrandbits(32), rng.getrandbits(32), rng.getrandbits(16))
            raw = record.encode()
            healed = record.copy()
            healed.values.update(ph.heal_values(record, franchise))
            after = healed.encode()
            expected = game_clear(raw, franchise)
            # the two words' non-injury bits and every other byte are the record's own
            self.assertEqual(after, expected, (raw.hex(), franchise))
            self.assertLessEqual({i for i in range(rr.PLAYER_SIZE) if raw[i] != after[i]}, INJURY_BYTES)

    def test_refusals_say_why(self) -> None:
        player = self.by_last["Manning"]
        self.assertEqual(ph.heal_refusal(player.record), ph.REASON_HEALTHY)
        self.hurt(player)
        self.assertEqual(ph.heal_refusal(player.record), "")
        self.assertEqual(ph.heal_refusal(player.record, on_listed_ir=True), ph.REASON_IR)
        player.record.values["injured_reserve"] = ph.IR_MARKER
        self.assertEqual(ph.heal_refusal(player.record), ph.REASON_IR)
        self.assertIn("Franchise > Injured Reserve > Activate", ph.REASON_IR)
        self.assertNotIn("—", ph.REASON_IR + ph.REASON_HEALTHY)


# ------------------------------------------------------------------------------------------------ heal: panel
class HealPanelTests(_Synthetic):
    def menu(self) -> dict[str, object]:
        return {a.text(): a for a in self.panel.grid_menu().actions() if a.text()}

    def test_the_menu_offers_heal_only_for_a_hurt_player_and_says_why_not(self) -> None:
        player = self.by_last["Manning"]
        self.panel.select_player(player)
        action = self.menu()["Heal player"]
        self.assertFalse(action.isEnabled())
        self.assertEqual(action.toolTip(), ph.REASON_HEALTHY)
        self.hurt(player)
        self.assertTrue(self.menu()["Heal player"].isEnabled())
        player.record.values["injured_reserve"] = ph.IR_MARKER
        action = self.menu()["Heal player"]
        self.assertFalse(action.isEnabled())
        self.assertIn("Franchise > Injured Reserve > Activate", action.toolTip())

    def test_heal_one_in_a_roster_save_writes_the_game_clear_with_bit_30_clear_and_undoes(self) -> None:
        player = self.by_last["Manning"]
        self.hurt(player, weeks=9, status=4, injury_id=0x2F4, depth=0x2D)
        self.panel.select_player(player)
        before = raw_record(self.document, player)
        self.assertEqual(self.panel.heal_players([player]), 1)
        after = raw_record(self.document, player)
        self.assertEqual(after, game_clear(before, False))
        self.assertEqual(player.record.values["unknown_20_high"], 0)
        self.assertEqual({i for i in range(rr.PLAYER_SIZE) if before[i] != after[i]} - INJURY_BYTES, set())
        self.assertFalse(ph.hurt(player.record))
        self.assertEqual(self.panel.undo_stack._done[-1].label, "Peyton Manning: heal")
        self.panel.undo()
        self.assertEqual(raw_record(self.document, player), before)
        self.panel.redo()
        self.assertEqual(raw_record(self.document, player), after)

    def test_a_franchise_panel_sets_bit_30(self) -> None:
        player = self.by_last["Manning"]
        self.hurt(player)
        with mock.patch.object(type(self.panel.franchise_panel), "active", new_callable=mock.PropertyMock,
                               return_value=True):
            self.assertEqual(self.panel.heal_players([player]), 1)
        self.assertEqual(player.record.values["unknown_20_high"], 0x100)

    def test_ir_and_healthy_players_are_refused_with_the_reason_and_nothing_changes(self) -> None:
        healthy = self.by_last["Manning"]
        before = raw_record(self.document, healthy)
        self.assertEqual(self.panel.heal_players([healthy]), 0)
        self.assertEqual(self.panel.status_label.text().splitlines()[0], ph.REASON_HEALTHY)
        marker = self.by_last["Harrison"]
        self.hurt(marker)
        marker.record.values["injured_reserve"] = ph.IR_MARKER
        listed = self.by_last["James"]
        self.hurt(listed)
        before_all = {p.last: raw_record(self.document, p) for p in (marker, listed)}
        self.assertEqual(self.panel.heal_players([marker]), 0)
        self.assertIn("Franchise > Injured Reserve > Activate", self.panel.status_label.text())
        with mock.patch.object(self.panel, "listed_ir_indices", return_value={listed.index}):
            self.assertEqual(self.panel.heal_players([listed]), 0)
            self.assertIn("Franchise > Injured Reserve > Activate", self.panel.status_label.text())
            self.assertEqual(self.panel.heal_reason(listed), ph.REASON_IR)
        self.assertEqual(raw_record(self.document, healthy), before)
        self.assertEqual({p.last: raw_record(self.document, p) for p in (marker, listed)}, before_all)
        self.assertFalse(self.panel.undo_stack.can_undo())

    def test_free_agents_may_be_healed(self) -> None:
        agent = self.by_last["Agent"]
        self.assertIsNone(self.document.club_of(agent))
        self.hurt(agent)
        self.assertEqual(self.panel.heal_reason(agent), "")
        self.assertEqual(self.panel.heal_players([agent]), 1)
        self.assertFalse(ph.hurt(agent.record))

    def test_heal_all_shown_is_one_undo_entry_and_skips_ir(self) -> None:
        names = ("Manning", "Harrison", "James")
        for last in names:
            self.hurt(self.by_last[last])
        self.by_last["James"].record.values["injured_reserve"] = ph.IR_MARKER
        self.panel.refresh_grid()
        shown = self.panel.visible_players()
        wanted = [p for p in shown if p.last in ("Manning", "Harrison")]
        self.assertEqual(len(wanted), 2)
        action = next(a for a in self.panel.grid_menu().actions() if a.text().startswith("Heal all"))
        self.assertEqual(action.text(), f"Heal all {len(self.panel.hurt_players_shown())} hurt players shown")
        self.assertTrue(action.isEnabled())
        before = {p.last: raw_record(self.document, p) for p in shown}
        healed = self.panel.heal_players(self.panel.hurt_players_shown())
        self.assertEqual(healed, len(self.panel.hurt_players_shown()) + healed)   # nobody hurt is left
        for p in shown:
            if p.last == "James":
                self.assertEqual(raw_record(self.document, p), before["James"])
            elif p.last in names:
                self.assertFalse(ph.hurt(p.record))
        self.assertEqual(self.panel.undo_stack._done[-1].label, f"heal {healed} hurt players")
        self.panel.undo()
        self.assertEqual({p.last: raw_record(self.document, p) for p in shown}, before)

    def test_show_my_changes_names_it_in_plain_words(self) -> None:
        player = self.by_last["Manning"]
        self.hurt(player, weeks=9, status=4, injury_id=0x2F4)
        self.document.original = bytes(self.document.to_body())        # as if the roster loaded already hurt
        self.panel._baseline = None
        self.panel.heal_players([player])
        self.panel.refresh_diff()
        text = self.panel.report.toPlainText()
        self.assertIn("Injury: 9 weeks left, status 4, injury id 756 -> healthy (healed the game's way)", text)
        self.assertNotIn("Unknown +0x2", text)


# ------------------------------------------------------------------------------------------------ heal: real saves
@unittest.skipUnless(SOFTDRINK_FRANCHISE_SIGNED.exists(), f"signed franchise absent: {SOFTDRINK_FRANCHISE_SIGNED}")
class HealFranchiseSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = _app()

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()
        self.assertTrue(self.panel.load_save(SOFTDRINK_FRANCHISE_SIGNED))
        self.document = self.panel.document

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()

    def test_it_is_a_franchise_save_with_hurt_players_and_an_ir_list(self) -> None:
        self.assertTrue(self.panel.franchise_panel.active)
        self.assertTrue(any(ph.hurt(p.record) for p in self.document.players))
        self.assertTrue(self.panel.listed_ir_indices())

    def test_heal_one_through_the_panel_reaches_the_signed_copy_and_nothing_else_moves(self) -> None:
        listed = self.panel.listed_ir_indices()
        player = next(p for p in self.document.players
                      if p.pool == "primary" and p.index not in listed and p.display == "Ryan Neuzil" and ph.hurt(p.record))
        before_state = ph.injury_state(player.record)
        self.assertEqual((before_state["injured"], before_state["weeks"]), (1, 1))
        original = rr.SaveContainer.load(SOFTDRINK_FRANCHISE_SIGNED, require_signature=False).savegame
        raw_before = raw_record(self.document, player)
        self.assertEqual(self.panel.heal_players([player]), 1)
        with tempfile.TemporaryDirectory() as folder:
            receipt = self.panel.write_copy_to(Path(folder) / "copy")
            self.assertTrue(receipt["signed"])
            self.assertTrue(receipt["readback_verified"])
            written = rr.SaveContainer.load(Path(folder) / "copy").savegame
            back = rr.load_save(Path(folder) / "copy")
        moved = [i for i in range(len(original)) if original[i] != written[i]]
        record_range = range(player.offset, player.offset + rr.PLAYER_SIZE)
        self.assertTrue(moved)
        self.assertTrue(all(i in record_range for i in moved), "only his record bytes changed in the whole save")
        self.assertLessEqual({i - player.offset for i in moved}, INJURY_BYTES)
        after = bytes(written[player.offset: player.offset + rr.PLAYER_SIZE])
        self.assertEqual(after, game_clear(raw_before, True))
        reloaded = back.by_offset[player.offset]
        self.assertEqual(ph.injury_state(reloaded.record), {"injured": 0, "known": 1, "weeks": 0, "status": 0,
                                                            "injury_id": 0})
        self.assertFalse(ph.hurt(reloaded.record))
        self.assertEqual(reloaded.record.values["depth_rank"], player.record.values["depth_rank"])

    def test_the_games_own_recovery_on_real_records_gives_the_same_words(self) -> None:
        if not GAME_TICK.is_file():
            self.skipTest(f"receipt absent: {GAME_TICK}")
        receipt = json.loads(GAME_TICK.read_text())
        by_name = {p.display: p for p in self.document.players if p.pool == "primary"}
        checked = 0
        for case in receipt["cases"]:
            player = by_name[case["player"]]
            raw = bytearray(raw_record(self.document, player))
            if case["arm"] == "after Finn Heal":
                if not raw[0x28]:
                    continue
                raw[0x27] = (raw[0x27] - 0x10) & 0xFF          # Finn's own two bytes first (heal-finn.json)
                raw[0x28] = 0
            elif case["arm"] != "as saved":
                continue
            record = rr.PlayerRecord.decode(bytes(raw), player.record.scheme)
            before = case["before"]
            self.assertEqual(hex(struct.unpack_from("<I", raw, 0x20)[0]), before["w20"], case["player"])
            self.assertEqual(hex(struct.unpack_from("<I", raw, 0x24)[0]), before["w24"], case["player"])
            record.values.update(ph.heal_values(record, True))
            healed = record.encode()
            game = case["clear 0xE6680"]["after"]
            with self.subTest(player=case["player"], arm=case["arm"]):
                self.assertEqual(hex(struct.unpack_from("<I", healed, 0x20)[0]), game["w20"])
                self.assertEqual(hex(struct.unpack_from("<I", healed, 0x24)[0]), game["w24"])
                self.assertEqual(hex(struct.unpack_from("<H", healed, 0x28)[0]), game["w28"])
                changed = [hex(i) for i in range(rr.PLAYER_SIZE) if healed[i] != raw[i]]
                self.assertEqual(changed, case["clear 0xE6680"]["changed"])
            checked += 1
        self.assertGreaterEqual(checked, 6)

    def test_ir_players_are_refused_in_a_franchise_save(self) -> None:
        listed = self.panel.listed_ir_indices()
        player = next(p for p in self.document.players if p.pool == "primary" and p.index in listed)
        self.assertEqual(self.panel.heal_reason(player), ph.REASON_IR)
        before = raw_record(self.document, player)
        self.assertEqual(self.panel.heal_players([player]), 0)
        self.assertEqual(raw_record(self.document, player), before)

    def test_heal_all_leaves_listed_ir_players_alone(self) -> None:
        listed = self.panel.listed_ir_indices()
        one = next(p for p in self.document.players if p.pool == "primary" and p.index not in listed
                   and self.document.club_of(p) is not None and ph.hurt(p.record) and not ph.on_ir_marker(p.record))
        self.assertTrue(self.panel.go_to_player(one))
        hurt = self.panel.hurt_players_shown()
        self.assertIn(one, hurt)
        self.assertTrue(all(p.index not in listed for p in hurt if p.pool == "primary"))
        ir_players = [p for p in self.panel.visible_players() if p.pool == "primary" and p.index in listed]
        before = {p.index: raw_record(self.document, p) for p in ir_players}
        self.assertEqual(self.panel.heal_players(hurt), len(hurt))
        self.assertEqual({p.index: raw_record(self.document, p) for p in ir_players}, before)
        self.assertEqual(self.panel.hurt_players_shown(), [])


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file() and SOFTDRINK_FRANCHISE_SIGNED.exists(),
                     "the SOFTDRINK fixture saves are absent")
class BitThirtyOnTheFixturesTests(unittest.TestCase):
    """RE_FACTS section 2 says every healthy player of a roster save has +0x20 bit 30 clear.  Checked here."""

    def test_roster_save_players_all_have_bit_30_clear_and_a_franchise_has_it_on_most(self) -> None:
        roster = rr.load_save(SOFTDRINK_ROSTER_SAVE)
        franchise = rr.load_save(SOFTDRINK_FRANCHISE_SIGNED)
        roster_known = sum(1 for p in roster.players if p.record.values["unknown_20_high"] & ph.KNOWN_BIT)
        franchise_known = sum(1 for p in franchise.players if p.record.values["unknown_20_high"] & ph.KNOWN_BIT)
        self.assertEqual(roster_known, 0, "roster save: bit 30 is clear on every player, healthy or hurt")
        self.assertGreater(franchise_known, len(franchise.players) // 2, "franchise: the weekly pass has set it")


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class HealRosterSaveTests(unittest.TestCase):
    def test_a_roster_save_heal_keeps_bit_30_clear_and_survives_a_signed_copy(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            self.assertFalse(panel.franchise_panel.active)
            player = next(p for p in panel.document.players if p.pool == "primary" and ph.hurt(p.record)
                          and not ph.on_ir_marker(p.record))
            before = raw_record(panel.document, player)
            self.assertEqual(panel.heal_players([player]), 1)
            self.assertEqual(player.record.values["unknown_20_high"], 0)
            self.assertEqual(raw_record(panel.document, player), game_clear(before, False))
            with tempfile.TemporaryDirectory() as folder:
                receipt = panel.write_copy_to(Path(folder) / "copy.zip")
                self.assertTrue(receipt["signed"])
                back = rr.load_save(Path(folder) / "copy.zip")
            self.assertFalse(ph.hurt(back.by_offset[player.offset].record))
        finally:
            panel.deleteLater()
            application.processEvents()


# ------------------------------------------------------------------------------------------------ paste exact copy
class PasteExactTests(_Synthetic):
    def setUp(self) -> None:
        super().setUp()
        self.source = self.by_last["Vick"]           # QB on club 1, college Virginia Tech
        self.target = self.by_last["Dunn"]           # RB on club 1, college Michigan
        self.source.record.values["jersey"] = 7

    def paste_exact(self) -> int:
        self.assertTrue(self.panel.go_to_player(self.source))
        self.assertTrue(self.panel.copy_player())
        self.assertTrue(self.panel.go_to_player(self.target))
        return self.panel.paste_player("exact")

    def test_the_mode_is_all_plus_pbp_and_photo(self) -> None:
        self.assertIn("exact", rr.COPY_MODES)
        a, b = self.source.record.copy(), self.target.record.copy()
        c = self.target.record.copy()
        rr.copy_player(a, b, mode="all")
        rr.copy_player(a, c, mode="exact")
        differing = {k for k in b.values if b.values[k] != c.values[k]}
        self.assertEqual(differing, {"pbp_id", "photo_id"})
        self.assertEqual((c.values["pbp_id"], c.values["photo_id"]), (a.values["pbp_id"], a.values["photo_id"]))
        self.assertEqual(c.values["history_pointer"], self.target.record.values["history_pointer"])

    def test_names_college_pbp_and_photo_arrive_and_the_slot_injury_and_history_stay(self) -> None:
        self.source.record.values["position"] = self.target.record.values["position"]   # a position change re-seats him
        self.hurt(self.target, weeks=4, status=2, injury_id=0x1B5, depth=0x1A)
        keep_keys = rr.PASTE_KEEPS_TARGET + ("history_pointer", "unknown_52")
        keep = {k: self.target.record.values[k] for k in keep_keys}
        self.assertGreater(self.paste_exact(), 5)
        self.assertEqual((self.target.first, self.target.last), ("Michael", "Vick"))
        self.assertEqual((self.target.college, self.target.college_index), ("Virginia Tech", 2))
        self.assertEqual(self.target.record.values["pbp_id"], self.source.record.values["pbp_id"])
        self.assertEqual(self.target.record.values["photo_id"], self.source.record.values["photo_id"])
        self.assertEqual(self.target.record.values["speed"], self.source.record.values["speed"])
        self.assertEqual({k: self.target.record.values[k] for k in keep_keys}, keep)
        self.assertEqual(ph.injury_state(self.target.record)["weeks"], 4)
        status = self.panel.status_label.text()
        self.assertIn("career history", status)
        self.assertIn("one stats stream", status)
        # the body agrees with the record values (a stale pointer would show in a written copy)
        written = rr.load_body(self.document.to_body())
        again = written.by_offset[self.target.offset]
        self.assertEqual((again.first, again.last, again.college), ("Michael", "Vick", "Virginia Tech"))

    def test_the_players_own_history_link_is_not_aliased(self) -> None:
        before = (self.source.record.values["history_pointer"], self.target.record.values["history_pointer"])
        self.paste_exact()
        self.assertEqual((self.source.record.values["history_pointer"], self.target.record.values["history_pointer"]),
                         before)

    def test_plain_paste_still_leaves_names_college_pbp_and_photo(self) -> None:
        before = (self.target.first, self.target.last, self.target.college, self.target.record.values["pbp_id"],
                  self.target.record.values["photo_id"])
        self.assertTrue(self.panel.go_to_player(self.source))
        self.panel.copy_player()
        self.assertTrue(self.panel.go_to_player(self.target))
        self.assertGreater(self.panel.paste_player("all"), 0)
        self.assertEqual((self.target.first, self.target.last, self.target.college, self.target.record.values["pbp_id"],
                          self.target.record.values["photo_id"]), before)

    def test_undo_and_redo_put_the_names_back_too(self) -> None:
        raw_before = raw_record(self.document, self.target)
        names_before = (self.target.first, self.target.last, self.target.college)
        self.paste_exact()
        raw_after = raw_record(self.document, self.target)
        self.assertEqual(self.panel.undo_stack._done[-1].label, f"paste exact copy onto {self.target.display}")
        self.panel.undo()
        self.assertEqual((self.target.first, self.target.last, self.target.college), names_before)
        self.assertEqual(raw_record(self.document, self.target), raw_before)
        self.panel.redo()
        self.assertEqual((self.target.first, self.target.last, self.target.college), ("Michael", "Vick", "Virginia Tech"))
        self.assertEqual(raw_record(self.document, self.target), raw_after)
        self.panel.undo()
        self.assertEqual((self.target.first, self.target.last), names_before[:2])
        self.assertFalse(self.panel._dirty & {(self.target.pool, self.target.index)}, "back to the loaded roster")

    def test_a_shared_name_string_stays_with_the_other_players(self) -> None:
        # give Moss and Dunn one shared last-name string, then paste Vick's exact copy onto Dunn
        other, target = self.by_last["Moss"], self.target
        self.document.set_name(other, "last", "Dunn")
        self.assertEqual(self.document.name_refs[self.document._pointer_target(other.offset, "last_name_pointer")], 2)
        self.paste_exact()
        self.assertEqual(target.last, "Vick")
        self.assertEqual(other.last, "Dunn", "the other player who shared the string is not renamed")
        again = rr.load_body(self.document.to_body())
        self.assertEqual((again.by_offset[other.offset].last, again.by_offset[target.offset].last), ("Dunn", "Vick"))

    def test_a_bad_position_or_name_refuses_the_whole_paste(self) -> None:
        self.assertTrue(self.panel.go_to_player(self.source))
        self.panel.copy_player()
        self.panel._clipboard_identity = {"first": "Mich@el", "last": "Vick", "college": "Virginia Tech"}
        self.assertTrue(self.panel.go_to_player(self.target))
        before = raw_record(self.document, self.target)
        names = (self.target.first, self.target.last, self.target.college)
        self.assertEqual(self.panel.paste_player("exact"), 0)
        self.assertIn("Nothing was pasted", self.panel.status_label.text())
        self.assertEqual(raw_record(self.document, self.target), before)
        self.assertEqual((self.target.first, self.target.last, self.target.college), names)
        self.assertFalse(self.panel.undo_stack.can_undo())

    def test_a_college_missing_from_this_roster_leaves_the_college_and_says_so(self) -> None:
        self.assertTrue(self.panel.go_to_player(self.source))
        self.panel.copy_player()
        self.panel._clipboard_identity["college"] = "Nowhere State"
        self.assertTrue(self.panel.go_to_player(self.target))
        self.assertGreater(self.panel.paste_player("exact"), 0)
        self.assertEqual(self.target.college, "Michigan")
        self.assertIn("not in this roster's college list", self.panel.status_label.text())

    def test_both_menus_carry_the_entry_next_to_the_other_pastes(self) -> None:
        text = "Paste exact copy (names, college, PBP, photo too)"
        self.assertIn(text, [a.text() for a in self.panel.paste_button.menu().actions()])
        grid = [a.text() for a in self.panel.grid_menu().actions()]
        self.assertEqual(grid[grid.index("Paste photo only") + 1], text)
        action = next(a for a in self.panel.grid_menu().actions() if a.text() == text)
        self.assertFalse(action.isEnabled(), "nothing copied yet")
        self.assertTrue(self.panel.go_to_player(self.source))
        self.panel.copy_player()
        action = next(a for a in self.panel.grid_menu().actions() if a.text() == text)
        self.assertTrue(action.isEnabled())

    def test_paste_now_keeps_the_whole_injury_state(self) -> None:
        # the fix this lane made: weeks and the injured bit (+0x22/+0x23) and the status nibble (+0x27) stay with
        # the target, like the injury id at +0x28 did before
        self.assertLessEqual({"unknown_20_high", "unknown_27_high", "injured_reserve", "unknown_29_low"},
                             set(rr.PASTE_KEEPS_TARGET))
        self.hurt(self.source, weeks=12, status=4, injury_id=0x2F4)
        target_state = ph.injury_state(self.target.record)
        for mode in ("all", "exact"):
            with self.subTest(mode=mode):
                self.assertTrue(self.panel.go_to_player(self.source))
                self.panel.copy_player()
                self.assertTrue(self.panel.go_to_player(self.target))
                self.panel.paste_player(mode)
                self.assertEqual(ph.injury_state(self.target.record), target_state)

    def test_restore_player_data_spot_group_names_the_injury_fields_too(self) -> None:
        self.assertLessEqual({"unknown_20_high", "unknown_27_high"}, set(rr.PLAYER_DATA_GROUPS["spot"]))


@unittest.skipUnless(SOFTDRINK_ROSTER_SAVE.is_file(), f"SOFTDRINK roster save absent: {SOFTDRINK_ROSTER_SAVE}")
class PasteExactRosterSaveTests(unittest.TestCase):
    def test_an_exact_copy_survives_a_signed_copy_and_a_reload_and_a_shared_last_name_stays(self) -> None:
        application = _app()
        panel = RosterEditorPanel()
        try:
            self.assertTrue(panel.load_save(SOFTDRINK_ROSTER_SAVE))
            document = panel.document
            primary = [p for p in document.players if p.pool == "primary"]
            by_last: dict[str, list[rr.Player]] = {}
            for p in primary:
                by_last.setdefault(p.last, []).append(p)
            shared = next(group for group in by_last.values() if len(group) >= 3 and group[0].last == "Johnson")
            target, others = shared[0], shared[1:]
            source = next(p for p in primary if len(by_last[p.last]) == 1 and p.college and p.college != target.college
                          and p.record.values["position"] == target.record.values["position"] and p is not target)
            self.assertTrue(panel.go_to_player(source))
            self.assertTrue(panel.copy_player())
            self.assertTrue(panel.go_to_player(target))
            keep_keys = rr.PASTE_KEEPS_TARGET + ("history_pointer", "unknown_52")
            keep = {k: target.record.values[k] for k in keep_keys}
            other_names = [(o.first, o.last) for o in others]
            old_first = target.first
            self.assertGreater(panel.paste_player("exact"), 0)
            self.assertEqual((target.first, target.last, target.college), (source.first, source.last, source.college))
            self.assertEqual([(o.first, o.last) for o in others], other_names)
            self.assertEqual({k: target.record.values[k] for k in keep_keys}, keep)
            with tempfile.TemporaryDirectory() as folder:
                receipt = panel.write_copy_to(Path(folder) / "copy.zip")
                self.assertTrue(receipt["signed"])
                back = rr.load_save(Path(folder) / "copy.zip")
            again = back.by_offset[target.offset]
            self.assertEqual((again.first, again.last, again.college), (source.first, source.last, source.college))
            self.assertEqual((again.record.values["pbp_id"], again.record.values["photo_id"]),
                             (source.record.values["pbp_id"], source.record.values["photo_id"]))
            self.assertEqual({k: again.record.values[k] for k in keep_keys}, keep)
            self.assertEqual([(back.by_offset[o.offset].first, back.by_offset[o.offset].last) for o in others],
                             other_names)
            self.assertNotEqual(old_first, "")
            panel.undo()
            self.assertEqual((target.first, target.last), (old_first, "Johnson"))
        finally:
            panel.deleteLater()
            application.processEvents()


if __name__ == "__main__":
    unittest.main()

"""b780 hunt5: the Studio keeps the six specialist slot bytes on their players, the way the game does.

A team record holds six slot indexes into its own 65-pointer list at +0x194..+0x199: holder, kick returner 1 and 2,
kicker, long snapper and punt returner (0xFF = nobody). The depth-chart builder 0xE7C50 fields KR1, KR2 and PR straight
from them (0xE7CAD..0xE7F4B), and the holder at 0xE8009. The game's removal handler 0xC3A90 keeps them right when it
takes a player out of a list: a role on the removed slot is cleared and the roles on later slots move up one place.

Before this fix the Studio's release, trade, signing into a slot, swap and the Rosters arrows changed the list and left
the six bytes alone, so a release above the specialists made the next man down the punt returner (on the v0.8 roster:
a tackle), and the Franchise tab's Place on IR did the same through Finn's byte-for-byte mode.

The removal rule itself is proved against the game's own code: with the retail executable present (NFL2K5_RETAIL_XBE)
the test runs 0xC3A90 in Unicorn on a team record and compares all six bytes for every removed slot. Everything else
runs on synthetic rosters anywhere.
"""

from __future__ import annotations

import hashlib
import os
import random
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage  # noqa: E402
from test_nfl2k5_roster_records import league_body, synthetic_body  # noqa: E402

try:
    import unicorn
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover - the native proof is optional
    unicorn = None

RETAIL_XBE = Path(os.environ.get("NFL2K5_RETAIL_XBE", "/nonexistent/default.xbe"))
ROLES = tuple(rr.SPECIAL_TEAM_OFFSETS)
REMOVE_VA, REMOVE_END_VA = 0xC3A90, 0xC3BCF          # the whole handler, through its `ret`
REMOVE_SHA256 = "aa939c6d8fccc4223bc53f22410a6ffe9885e43e42f03885809e610bd5711acb"   # retail 0xC3A90..0xC3BCF
# Its role half (0xC3AE1..0xC3BCF) is byte-identical in retail, SOFTDRINK v0.8 and the v0.9 RC; the practice squad
# patches only the list compaction before it (0xC3ABE, 0xC3AC7, 0xC3AD3).
ROLE_PART_VA, ROLE_PART_SHA256 = 0xC3AE1, "78d246634678fad3e8717a7a19ac798ecf5ea46240ed0ccd5efad203d7d88841"


def roles_of(document: rr.RosterDocument, team_index: int) -> list[int]:
    team = document.teams[team_index]
    return [document.body[team.offset + rr.SPECIAL_TEAM_OFFSETS[role]] for role in ROLES]


def set_roles(document: rr.RosterDocument, team_index: int, values) -> None:
    team = document.teams[team_index]
    for role, value in zip(ROLES, values):
        document.body[team.offset + rr.SPECIAL_TEAM_OFFSETS[role]] = value


def who(document: rr.RosterDocument, team_index: int) -> list[int | None]:
    """The player (record offset) each role names, None for nobody."""

    slots = document.teams[team_index].slots
    return [slots[v] if v < len(slots) else None for v in roles_of(document, team_index)]


class NativeRemoval:
    """The game's own 0xC3A90 in Unicorn: eax = team record, ecx = slot; returns the six bytes it leaves."""

    TEAM, PLAYERS, STACK, STOP = 0x200000, 0x210000, 0x300000, 0x400000

    def __init__(self, xbe: bytes) -> None:
        image = XbeImage(xbe)
        code = image.read(REMOVE_VA, REMOVE_END_VA + 1 - REMOVE_VA)
        self.code_sha256 = hashlib.sha256(code).hexdigest()
        self.role_part_sha256 = hashlib.sha256(image.read(ROLE_PART_VA, REMOVE_END_VA + 1 - ROLE_PART_VA)).hexdigest()
        self.uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        page = REMOVE_VA & ~0xFFF
        self.uc.mem_map(page, 0x2000)
        self.uc.mem_write(REMOVE_VA, code)
        for base in (self.TEAM, self.PLAYERS, self.STACK, self.STOP):
            self.uc.mem_map(base, 0x10000)

    def run(self, roles, count: int, slot: int) -> list[int]:
        team = bytearray(rr.TEAM_SIZE)
        for i in range(count):
            struct.pack_into("<I", team, i * 4, self.PLAYERS + i * rr.PLAYER_SIZE)
        team[rr.TEAM_PLAYER_COUNT] = count
        team[0x194:0x19A] = bytes(roles)
        self.uc.mem_write(self.TEAM, bytes(team))
        self.uc.mem_write(self.PLAYERS, bytes(65 * rr.PLAYER_SIZE))
        esp = self.STACK + 0x8000
        self.uc.mem_write(esp, struct.pack("<I", self.STOP))
        self.uc.reg_write(x86.UC_X86_REG_ESP, esp)
        self.uc.reg_write(x86.UC_X86_REG_EAX, self.TEAM)
        self.uc.reg_write(x86.UC_X86_REG_ECX, slot)
        self.uc.emu_start(REMOVE_VA, self.STOP, count=100000)
        after = bytes(self.uc.mem_read(self.TEAM, rr.TEAM_SIZE))
        assert after[rr.TEAM_PLAYER_COUNT] == count - 1
        return list(after[0x194:0x19A])


@unittest.skipUnless(unicorn is not None and RETAIL_XBE.is_file(), "Unicorn and NFL2K5_RETAIL_XBE required")
class GameRemovalHandlerTests(unittest.TestCase):
    """The Studio's rule is the game's: every removed slot, every kind of role value."""

    @classmethod
    def setUpClass(cls) -> None:
        raw = RETAIL_XBE.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == RETAIL_SHA256
        cls.native = NativeRemoval(raw)

    def test_the_handler_is_the_pinned_retail_code(self) -> None:
        self.assertEqual(self.native.code_sha256, REMOVE_SHA256)
        self.assertEqual(self.native.role_part_sha256, ROLE_PART_SHA256)

    def test_model_equals_0xc3a90_for_every_slot(self) -> None:
        rng = random.Random(780)
        cases = 0
        for count in (2, 42, 53, 65):
            for slot in range(count):
                fixed = [slot, max(slot - 1, 0), min(slot + 1, count - 1), 0xFF, count - 1, 0]
                for roles in [fixed] + [[rng.choice([0xFF, rng.randrange(count), rng.randrange(0x80, 0xFF)])
                                         for _ in ROLES] for _ in range(3)]:
                    self.assertEqual(rr.specialists_after_removal(roles, slot), self.native.run(roles, count, slot),
                                     (count, slot, roles))
                    cases += 1
        self.assertGreater(cases, 600)


class RosterOperationTests(unittest.TestCase):
    """Rosters page operations, on a synthetic two-club league (44 players each)."""

    def setUp(self) -> None:
        self.document = rr.RosterDocument(league_body())
        # holder 5, KR1 10, KR2 20, K 30, LS 40, PR 43 (the last slot); the second club the same
        for team in (0, 1):
            set_roles(self.document, team, [5, 10, 20, 30, 40, 43])

    def assert_round_trip(self, team_index: int) -> None:
        again = rr.RosterDocument(self.document.to_body())
        self.assertEqual(roles_of(again, team_index), roles_of(self.document, team_index))
        self.assertEqual(who(again, team_index), who(self.document, team_index))

    def test_release_above_the_specialists_is_the_games_removal(self) -> None:
        before, names = roles_of(self.document, 0), who(self.document, 0)
        player = self.document.by_offset[self.document.teams[0].slots[2]]
        self.document.release(player, 0)
        self.assertEqual(roles_of(self.document, 0), rr.specialists_after_removal(before, 2))
        self.assertEqual(who(self.document, 0), names)                 # every role still names the same man
        self.assert_round_trip(0)

    def test_release_of_the_kick_returner_clears_only_his_role(self) -> None:
        before = roles_of(self.document, 0)
        player = self.document.by_offset[self.document.teams[0].slots[10]]
        self.document.release(player, 0)
        after = roles_of(self.document, 0)
        self.assertEqual(after, rr.specialists_after_removal(before, 10))
        self.assertEqual(after[ROLES.index("kr1")], 0xFF)
        self.assertEqual(after[ROLES.index("h")], 5)
        self.assert_round_trip(0)

    def test_trade_removes_from_one_club_and_appends_to_the_other(self) -> None:
        before_a, before_b, names_b = roles_of(self.document, 0), roles_of(self.document, 1), who(self.document, 1)
        player = self.document.by_offset[self.document.teams[0].slots[0]]
        receipt = self.document.transfer(player, 1, from_team=0)
        self.assertEqual(receipt["to"]["slot"], len(self.document.teams[1].slots) - 1)
        self.assertEqual(roles_of(self.document, 0), rr.specialists_after_removal(before_a, 0))
        self.assertEqual(roles_of(self.document, 1), before_b)        # an append moves nobody
        self.assertEqual(who(self.document, 1), names_b)
        self.assert_round_trip(0)
        self.assert_round_trip(1)

    def test_sign_into_a_slot_moves_the_later_roles_with_their_players(self) -> None:
        self.document.release(self.document.by_offset[self.document.teams[0].slots[1]], 0)
        names = who(self.document, 0)
        free_agent = self.document.by_offset[self.document.free_agents[0]]
        receipt = self.document.sign(free_agent, 0, slot=3)
        self.assertEqual(receipt["to"]["slot"], 3)
        self.assertEqual(who(self.document, 0), names)
        self.assertEqual(roles_of(self.document, 0), [5, 10, 20, 30, 40, 43])   # release of slot 1, then sign at 3
        self.assert_round_trip(0)

    def test_swap_between_clubs_clears_the_departed_roles(self) -> None:
        names_a, names_b = who(self.document, 0), who(self.document, 1)
        first = self.document.by_offset[self.document.teams[0].slots[10]]     # club 0's KR1
        second = self.document.by_offset[self.document.teams[1].slots[11]]
        self.document.swap(first, second)
        after = roles_of(self.document, 0)
        self.assertEqual(after[ROLES.index("kr1")], 0xFF)
        self.assertEqual([n for r, n in zip(ROLES, who(self.document, 0)) if r != "kr1"],
                         [n for r, n in zip(ROLES, names_a) if r != "kr1"])
        self.assertEqual(who(self.document, 1), names_b)               # club 1 lost nobody with a role
        self.assert_round_trip(0)
        self.assert_round_trip(1)

    def test_swap_inside_one_club_and_the_arrows_keep_every_role(self) -> None:
        names = who(self.document, 0)
        team = self.document.teams[0]
        self.document.swap(self.document.by_offset[team.slots[5]], self.document.by_offset[team.slots[43]])
        self.assertEqual(who(self.document, 0), names)
        self.assertTrue(self.document.move_in_depth(0, 10, -1))         # the up arrow on the kick returner
        self.assertEqual(who(self.document, 0), names)
        self.assertEqual(roles_of(self.document, 0)[ROLES.index("kr1")], 9)
        self.assertTrue(self.document.move_in_depth(0, 9, 1))           # and back: the bytes are the loaded ones
        self.assertTrue(self.document.move_in_depth(0, 20, 1))
        self.assertTrue(self.document.move_in_depth(0, 21, -1))
        self.assertEqual(who(self.document, 0), names)
        self.assert_round_trip(0)

    def test_a_swap_inside_one_club_never_benches_a_starter(self) -> None:
        # the Swap dialog lists every team, the player's own included; before b780 hunt5 both players were re-ranked to
        # the bottom of their chains (on the v0.8 roster SF's starting QB became QB3) and lost their locks
        team = self.document.teams[0]
        a, b = (self.document.by_offset[o] for o in (team.slots[4], team.slots[17]))
        before = [(p.record.values["depth_rank"], p.record.values["depth_side"], p.record.values["unknown_52"])
                  for p in (a, b)]
        receipt = self.document.swap(a, b)
        self.assertEqual(receipt["depth"], {})
        self.assertEqual([(p.record.values["depth_rank"], p.record.values["depth_side"], p.record.values["unknown_52"])
                          for p in (a, b)], before)
        self.assertEqual((team.slots[4], team.slots[17]), (b.offset, a.offset))

    def test_project_replay_keeps_roles_and_records_no_specialist_edits(self) -> None:
        base = self.document.to_body()
        loaded = rr.RosterDocument(base)
        loaded.release(loaded.by_offset[loaded.teams[0].slots[0]], 0)
        loaded.transfer(loaded.by_offset[loaded.teams[1].slots[3]], 0, from_team=1)
        expected = loaded.to_body()
        document = rr.edits_document(loaded, name="hunt5")
        self.assertNotIn("special_teams", document)                    # the moves carry the roles themselves
        replayed, receipt = rr.apply_body(base, document)
        self.assertEqual(receipt["players_moved"], 2)
        again = rr.RosterDocument(replayed)
        for team in (0, 1):
            self.assertEqual(roles_of(again, team), list(expected[loaded.teams[team].offset + 0x194:
                                                                  loaded.teams[team].offset + 0x19A]))

    def test_a_replayed_player_who_ends_where_he_started_keeps_his_role(self) -> None:
        # replay takes every mover off every list first and puts him back second; a player whose document entry
        # leaves him on a team (an all-star squad next to his new club) must not lose his role there
        team = self.document.teams[0]
        returner = self.document.by_offset[team.slots[10]]                 # club 0's KR1
        before, names = roles_of(self.document, 0), who(self.document, 0)
        log: list[str] = []
        moved = rr.replay_moves(self.document, [{
            "pool": returner.pool, "index": returner.index, "first": returner.first, "last": returner.last,
            "to_teams": [{"team": team.abbreviation, "team_index": 0, "slot": 10}], "free_agent": False}], log)
        self.assertEqual((moved, log), (1, []))
        self.assertEqual(roles_of(self.document, 0), before)
        self.assertEqual(who(self.document, 0), names)

    def test_a_chosen_role_is_still_recorded(self) -> None:
        loaded = rr.RosterDocument(self.document.to_body())
        loaded.release(loaded.by_offset[loaded.teams[0].slots[0]], 0)
        team = loaded.teams[0]
        loaded.body[team.offset + rr.SPECIAL_TEAM_OFFSETS["pr"]] = 12  # somebody picks a new punt returner
        document = rr.edits_document(loaded, name="hunt5")
        chosen = loaded.by_offset[team.slots[12]]
        self.assertEqual(document["special_teams"], [{"team_index": 0, "team": team.abbreviation, "roles": {
            "pr": {"pool": chosen.pool, "index": chosen.index, "first": chosen.first, "last": chosen.last}}}])


class FranchiseInjuredReserveTests(unittest.TestCase):
    """Franchise tab > Place on IR uses the game's rule; Finn's byte-for-byte mode stays for parity only."""

    def setUp(self) -> None:
        from test_nfl2k5_franchise_save import synthetic_franchise
        self.payload = bytearray(synthetic_franchise())
        save = fs.FranchiseSave(bytes(self.payload), source="synthetic")
        self.team = save.team_offset(0)
        # team 0 lists three players; holder slot 2, KR1 slot 1, KR2 nobody, K slot 2, LS slot 0, PR slot 1
        self.payload[self.team + 0x194:self.team + 0x19A] = bytes([2, 1, 0xFF, 2, 0, 1])
        self.victim = save.player_index(save._team_slots(0)[1][0])

    def roles(self, save: fs.FranchiseSave) -> list[int]:
        return list(save.buffer[self.team + 0x194:self.team + 0x19A])

    def test_default_follows_the_removal_handler(self) -> None:
        save = fs.FranchiseSave(bytes(self.payload), source="synthetic")
        save.place_on_injured_reserve(0, self.victim)
        self.assertEqual(self.roles(save), rr.specialists_after_removal([2, 1, 0xFF, 2, 0, 1], 0))
        self.assertEqual(self.roles(save), [1, 0, 0xFF, 1, 0xFF, 0])

    def test_finn_parity_mode_keeps_finns_bytes(self) -> None:
        save = fs.FranchiseSave(bytes(self.payload), source="synthetic")
        save.place_on_injured_reserve(0, self.victim, finn_roles=True)
        self.assertEqual(self.roles(save), [2, 1, 0xFF, 2, 0, 1])

    def test_the_franchise_tab_uses_the_games_rule(self) -> None:
        try:
            from mod_editor.gui.franchise_panel_qt import FranchiseEdit
        except ImportError as exc:  # pragma: no cover - PyQt5 absent
            self.skipTest(f"PyQt5 required: {exc}")
        save = fs.FranchiseSave(bytes(self.payload), source="synthetic")
        FranchiseEdit("ir_place", "IR", {"team": 0, "player": self.victim}).apply(save)
        expected = fs.FranchiseSave(bytes(self.payload), source="synthetic")
        expected.place_on_injured_reserve(0, self.victim)
        self.assertEqual(save.to_bytes(), expected.to_bytes())
        self.assertEqual(self.roles(save), [1, 0, 0xFF, 1, 0xFF, 0])


if __name__ == "__main__":
    unittest.main()

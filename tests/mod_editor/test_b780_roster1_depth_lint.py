"""b780 roster1: the dated refresh leaves no depth-chart row empty, and a lint of the pack's 32 clubs.

The injured-reserve pass (b4-economy D6, new in beta-80) releases the lowest-rated player at a position above its
minimum to make room for an injured player, and that player can hold a locked row of the dated depth chart. On the
v0.9 RC disc that left 38 position charts on 24 clubs with a row no player holds (CAR and MIN left guard, HOU MIKE,
GB right guard and right defensive tackle, LAC right defensive tackle, LV right corner ...); v0.8 had none.
nfl2k5_roster_refresh now gives the released player's place to the next player the dated chart lists at his slot.

The lint reads a whole roster the way the game's formations need it: 42 to 53 active players and at most 12 reserves
per club, the position floors, every position's chart in the refresh's native rank/side pairs (no empty row, no player
in two starting rows) and row 0 of every position the club carries held, the special-teams bytes on rostered players
at a position that can fill them, no player on two lists, no jersey number twice on a club, every club player signed
and with a college, and (on a disc image) no two players sharing a portrait id. KNOWN lists the problems this release
leaves for a decision; anything else fails, and a KNOWN item that has been fixed is fine.

Private data (skipped without it): NFL2K5_V08_ROST_BODY + NFL2K5_V08_ROSTER_EDITS (the released v0.8 disc roster and
the roster-edits document the v0.8 and v0.9 recipes load; the refresh is replayed on it as the build runs it), and
optionally NFL2K5_PACK_LINT_IMAGE, a built disc image to lint as it is (for example the final v0.9 disc).
"""
from __future__ import annotations

import collections
import copy
import hashlib
import json
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests/mod_editor"), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_roster_refresh as refresh  # noqa: E402

V08_ROST = Path(os.environ.get("NFL2K5_V08_ROST_BODY", "") or "missing")
V08_PLAN = Path(os.environ.get("NFL2K5_V08_ROSTER_EDITS", "") or "missing")
# b780-int: the release roster edits (RST2, room_policy "ir"); the beta-79 file above has no IR policy
RELEASE_PLAN = Path(os.environ.get("NFL2K5_RELEASE_ROSTER_EDITS", "") or "missing")
V08_ROST_SHA256 = "526291e894e40ea92b3d5f0611b6a246d5c1ade2e7603d89b59cb24ecad6b048"
LINT_IMAGE = Path(os.environ.get("NFL2K5_PACK_LINT_IMAGE", "") or "missing")

POSITIONS = rr.SCHEME_POSITION_NAMES["one_pool"]
# Floors a club needs to field the game's formations (offense, 4-3, 3-4, nickel, dime, kicking).
FLOORS = {"QB": ("QB",), "K": ("K",), "P": ("P",), "C": ("C",), "G": ("G",) * 2, "T": ("T",) * 2,
          "WR": ("WR",) * 3, "TE": ("TE",), "HB": ("HB",), "DT": ("DT",) * 2, "EDGE": ("EDGE",) * 2,
          "LB": ("LB",) * 3, "CB": ("CB",) * 3, "S": ("FS/SS",) * 2}
ELIGIBLE = {"h": {"P", "K", "QB"}, "k": {"K"}, "ls": {"C", "TE", "G", "T"},
            "kr1": {"WR", "CB", "FS", "SS", "HB", "FB"}, "kr2": {"WR", "CB", "FS", "SS", "HB", "FB"},
            "pr": {"WR", "CB", "FS", "SS", "HB"}}
# Left for a decision in this release (b780 roster1 report; BETA81_QUEUE.md), or fixed by another job.
KNOWN = {
    ("LAR", "floor K"): "no kicker: the 10/14 refresh has Harrison Mevis CUT (the 11/03 refresh signs Joshua Karty)",
    ("LAR", "special k"): "same",
    ("LAR", "chart K"): "same",
    ("NO", "special ls"): "no long snapper: Zach Wood on injured reserve with no record, Cal Adomitis CUT (10/14)",
    ("CLE", "special kr2"): "the dated chart lists one kick returner",
    ("DAL", "special kr2"): "the dated chart lists one kick returner",
    ("SEA", "special kr2"): "the dated chart lists one kick returner",
    ("LAR", "jersey twice"): "nflverse 11/03 lists Brandon McManus and the injured Blake Grupe, both kickers, as #19",
}


def starts_on_ir(doc, player):
    """b780 IR1: the player's record says he is injured four or more weeks (+0x20 bit 31, weeks in bits 22..29, +0x24 status
    Out): a modern-IR franchise start puts him on his club's injured reserve, off the 53."""
    word20, word24 = struct.unpack_from("<II", doc.body, player.offset + 0x20)
    return bool(word20 & 0x80000000) and ((word20 >> 22) & 0xFF) >= 4 and (word24 >> 28) & 7 == 4


def lint(doc, *, portraits=False):
    """{(club, check): detail} for the 32 clubs of a one-pool roster document."""
    found = {}
    lists = collections.defaultdict(list)
    for team in doc.teams[:32]:
        for player in doc.team_players(team.index):
            lists[player.index].append(team.abbreviation)
        for index in doc.reserves.get(team.index, ()):
            lists[index].append(team.abbreviation + " reserves")
    for offset in doc.free_agents:
        lists[doc.by_offset[offset].index].append("free agents")
    for index, where in lists.items():
        if len(where) > 1:
            found[(where[0], "two lists")] = f"{doc.by_pool('primary')[index].display}: {where}"
    for team in doc.teams[:32]:
        club = team.abbreviation
        roster = [doc.by_offset[o] for o in team.slots]
        names = [POSITIONS[p.record.get("position")] for p in roster]
        # b780 IR1: players who start the franchise on injured reserve are off the 53; the club's list holds the 53, them and
        # the practice squad within 65
        healthy = [p for p in roster if not starts_on_ir(doc, p)]
        if not rr.TEAM_MIN_PLAYERS <= len(healthy) <= 53:         # the game's 42 and the 53-man active limit
            found[(club, "active count")] = len(healthy)
        if len(roster) + len(doc.reserves.get(team.index, ())) > 65:
            found[(club, "list count")] = len(roster) + len(doc.reserves.get(team.index, ()))
        if len(doc.reserves.get(team.index, ())) > 12:
            found[(club, "reserves count")] = len(doc.reserves[team.index])
        have = collections.Counter("FS/SS" if n in ("FS", "SS") else n
                                   for n, p in zip(names, roster) if not starts_on_ir(doc, p))
        for key, need in FLOORS.items():
            if have[need[0]] < len(need):
                found[(club, f"floor {key}")] = have[need[0]]
        charts = collections.defaultdict(list)
        for player in roster:
            values = player.record.values
            if values["depth_rank"] < refresh.OVERFLOW_DEPTH_ROW:
                charts[POSITIONS[values["position"]]].append((values["depth_rank"], values["depth_side"]))
        # the locked chart of every position in the native pairs, and row 0 of every position the club carries held
        # (an injured player who rejoined as the club's only fullback takes it, unlocked)
        for position, pairs in charts.items():
            native = [refresh.native_depth_pair(n) for n in range(len(pairs))]
            if position in ("HB", "WR"):
                # b780 sub1: the default third-down back (RB side row 1) and gadget (WR side row 3) reorder the side rows,
                # so they are a permutation of the native ones
                ok = [r for r, _s in sorted(pairs)] == [r for r, _s in native] and \
                    sorted(side for _r, side in pairs) == sorted(side for _r, side in native)
            else:
                ok = sorted(pairs) == native
            if not ok:
                found[(club, f"chart {position}")] = sorted(pairs)
        for position in set(names) - {"OLB"}:
            if not any(n == position and p.record.get("depth_rank") == 0 for n, p in zip(names, roster)):
                found[(club, f"row 0 {position}")] = [p.display for n, p in zip(names, roster) if n == position]
        for key, offset in rr.SPECIAL_TEAM_OFFSETS.items():
            slot = doc.body[team.offset + offset]
            if slot >= len(roster):
                found[(club, f"special {key}")] = slot
            elif names[slot] not in ELIGIBLE[key]:
                found[(club, f"special {key}")] = f"{roster[slot].display} ({names[slot]})"
        numbers = collections.Counter(p.record.get("jersey") for p in roster)
        if any(v > 1 for v in numbers.values()):
            found[(club, "jersey twice")] = sorted(k for k, v in numbers.items() if v > 1)
        for player in roster + doc.reserve_players(team.index):
            values = player.record.values
            if not (values["contract_length"] >= 1 and values["contract_value"] >= 1
                    and 1 <= values["contract_remaining"] <= values["contract_length"]):
                found[(club, f"contract {player.display}")] = (values["contract_value"], values["contract_length"])
            if player.college_index is None:
                found[(club, f"college {player.display}")] = None
            if not player.first or not player.last or "*" in player.first + player.last:
                found[(club, f"name {player.index}")] = player.display
    if portraits:
        owners = collections.defaultdict(list)
        for index, where in lists.items():
            player = doc.by_pool("primary")[index]
            owners[player.record.get("photo_id")].append((where[0], player.display))
        for photo, who in owners.items():
            if photo and photo != 7100 and len(who) > 1:            # 7100: the refresh's no-photo selector
                for club, name in who:
                    found[(club, f"portrait {photo}")] = who
    return found


def unexpected(found):
    return {k: v for k, v in found.items() if k not in KNOWN}


# ------------------------------------------------------------------------------------------------ synthetic
def _sample():
    import test_roster_refresh as fixture
    return fixture.sample()


def _set(body, changes):
    doc = rr.RosterDocument(body, scheme="one_pool", reference_year=2026)
    for index, fields in changes.items():
        record = doc.by_pool("primary")[index].record
        for key, value in fields.items():
            record.set(key, value)
    return doc.to_body()


class ReleasedStarterTests(unittest.TestCase):
    """Club T0 at 53 with four guards on the dated chart (LG1, RG1, LG2, RG2); an injured player rejoins, and the
    left starter, the weakest player on a small deal, is released for room.

    b780 rst2 (Q43): the release policy now protects a charted starter, so these tests force the old victim: what they
    test is how the writer closes a chart after a locked-row player leaves, whoever the policy picks."""

    @staticmethod
    def releasing(victim):
        from unittest import mock

        def make_room(club, active, keep, position, minimums, ranks, big_deal, overall, limit):
            if victim in active and len(active) > limit:
                active.remove(victim)
                return [victim]
            return []

        return mock.patch.object(refresh, "_make_room", make_room)

    @classmethod
    def setUpClass(cls):
        cls.body, cls.plan = _sample()

    def _club(self, slots):
        plan = copy.deepcopy(self.plan)
        extra = plan["free_agents"][:11]
        for index in extra:
            plan["free_agents"].remove(index)
        plan["teams"][0]["active"] += extra                       # 53
        injured = plan["free_agents"].pop(0)
        row = next(r for r in plan["players"] if r["index"] == injured)
        row.update(status="RES", team="T0")
        guards = plan["teams"][0]["active"][:4]
        for order, (index, slot) in enumerate(zip(guards, slots)):
            row = next(r for r in plan["players"] if r["index"] == index)
            rank, side = refresh.native_depth_pair(order)
            row["fields"] = {"position": 13, "depth_rank": rank, "depth_side": side}
            if slot:
                row["depth_source"] = {"pos_abb": slot[0], "pos_rank": str(slot[1])}
        weak = {k: 5 for k in rr.RATING_BYTE_ORDER}
        body = _set(self.body, {guards[0]: {**weak, "contract_value": 20, "contract_length": 1,
                                            "contract_remaining": 1}})
        return body, plan, guards, injured

    def _chart(self, out, guards):
        doc = rr.RosterDocument(out, scheme="one_pool", reference_year=2026)
        primary = doc.by_pool("primary")
        return doc, {i: (primary[i].record.get("depth_rank"), primary[i].record.get("depth_side"),
                         primary[i].record.depth_locks["rank"], primary[i].record.depth_locks["side"])
                     for i in guards if doc.club_of(primary[i]) == 0}

    def test_the_next_player_listed_at_his_slot_takes_his_place(self):
        body, plan, (lg1, rg1, lg2, rg2), injured = self._club([("LG", 1), ("RG", 1), ("LG", 2), ("RG", 2)])
        with self.releasing(lg1):
            out, receipt = refresh.apply_body(body, plan)
        doc, chart = self._chart(out, (lg1, rg1, lg2, rg2))
        self.assertEqual(receipt["injured_reserve"]["released_players"], [doc.by_pool("primary")[lg1].display])
        self.assertIn(doc.by_pool("primary")[lg1].offset, doc.free_agents)
        # LG2 starts at left guard, RG1 stays the right guard, RG2 is next
        self.assertEqual(chart, {lg2: (0, 2, True, True), rg1: (1, 0, True, True), rg2: (2, 1, True, True)})
        self.assertEqual(receipt["injured_reserve"]["reseated_rows"], 2)
        self.assertEqual(unexpected({k: v for k, v in lint(doc).items() if k[0] == "T0" and "chart" in k[1]}), {})
        with self.releasing(lg1):
            self.assertEqual(refresh.apply_body(out, plan)[0], out)

    def test_with_no_one_listed_at_his_slot_the_chart_closes_up(self):
        body, plan, (lg1, rg1, lg2, rg2), _ = self._club([("LG", 1), None, None, None])
        with self.releasing(lg1):
            out, receipt = refresh.apply_body(body, plan)
        _doc, chart = self._chart(out, (lg1, rg1, lg2, rg2))
        self.assertEqual(chart, {rg1: (0, 2, True, True), lg2: (1, 0, True, True), rg2: (2, 1, True, True)})
        self.assertEqual(receipt["injured_reserve"]["reseated_rows"], 3)
        with self.releasing(lg1):
            self.assertEqual(refresh.apply_body(out, plan)[0], out)

    def test_negative_control_without_the_reseat_the_left_guard_row_is_empty(self):
        body, plan, guards, _ = self._club([("LG", 1), ("RG", 1), ("LG", 2), ("RG", 2)])
        keep = refresh._reseat_chains
        refresh._reseat_chains = lambda *args: []
        try:
            with self.releasing(guards[0]):
                out, _receipt = refresh.apply_body(body, plan)
        finally:
            refresh._reseat_chains = keep
        doc, chart = self._chart(out, guards)
        self.assertNotIn(0, {rank for rank, _side, _r, _s in chart.values()})
        self.assertIn(("T0", "chart G"), lint(doc))

    def test_an_injured_player_who_is_his_clubs_only_fullback_holds_row_0(self):
        """NE 11/03: Reggie Gilliam, the only fullback, rejoins from injured reserve; the FB row 0 is his (unlocked),
        while an injured receiver joining receivers stays at the overflow row for the weekly sort."""
        plan = copy.deepcopy(self.plan)
        fullback, receiver = plan["free_agents"][0], plan["free_agents"][1]
        for index in (fullback, receiver):
            plan["free_agents"].remove(index)
            next(r for r in plan["players"] if r["index"] == index).update(status="RES", team="T5")
        next(r for r in plan["players"] if r["index"] == fullback)["fields"] = {"position": 8}
        out, receipt = refresh.apply_body(self.body, plan)
        doc = rr.RosterDocument(out, scheme="one_pool", reference_year=2026)
        fb, wr = doc.by_pool("primary")[fullback], doc.by_pool("primary")[receiver]
        self.assertEqual((fb.record.get("depth_rank"), fb.record.get("depth_side")), refresh.native_depth_pair(0))
        self.assertEqual((wr.record.get("depth_rank"), wr.record.get("depth_side")), (7, 7))
        self.assertFalse(any(fb.record.depth_locks.values()))
        self.assertEqual(receipt["injured_reserve"]["lone_rejoined_seated"], [fb.display])
        self.assertNotIn(("T5", "row 0 FB"), lint(doc))
        self.assertEqual(refresh.apply_body(out, plan)[0], out)

    def test_a_chart_that_lost_no_one_does_not_move(self):
        body, plan, guards, injured = self._club([("LG", 1), ("RG", 1), ("LG", 2), ("RG", 2)])
        plan["teams"][0]["active"].remove(plan["teams"][0]["active"][-1])     # room for the injured player: 52
        plan["free_agents"].append(self.plan["free_agents"][10])
        out, receipt = refresh.apply_body(body, plan)
        _doc, chart = self._chart(out, guards)
        self.assertEqual(receipt["injured_reserve"]["released_for_room"], 0)
        self.assertEqual(receipt["injured_reserve"]["reseated_rows"], 0)
        self.assertEqual([chart[i][:2] for i in guards], [refresh.native_depth_pair(n) for n in range(4)])


# ------------------------------------------------------------------------------------------------ portraits
class _Rec:
    def __init__(self, photo, month, day):
        self.values = {"photo_id": photo}
        self._f = {"birth_month": month, "birth_day": day}

    def get(self, name):
        return self._f.get(name)


class _P:
    def __init__(self, first, last, photo, month, day, offset):
        self.pool, self.first, self.last, self.offset = "primary", first, last, offset
        self.record = _Rec(photo, month, day)


class _Doc:
    def __init__(self, players):
        self.players = players


class WrongFaceTests(unittest.TestCase):
    """A real player who holds the stock portrait of the record he took over gets the no-photo card."""

    def manifest(self):
        from mod_editor.core import nfl2k5_real_portraits as rp
        doc = rp.load_manifest()
        return {"portraits": [{"id": 30000, "first": "Has", "last": "Headshot", "birth_month": 2, "birth_day": 2}],
                "wrong_faces": doc["wrong_faces"] + [
                    {"first": "Has", "last": "Headshot", "birth_month": 2, "birth_day": 2, "photo_id": 1234}]}

    def test_the_shipped_list_names_kage_casey_only_and_thorson_and_masses_have_their_own_pictures(self):
        from mod_editor.core import nfl2k5_real_portraits as rp
        manifest = rp.load_manifest()
        rows = {(r["first"], r["last"]): r["photo_id"] for r in manifest["wrong_faces"]}
        self.assertEqual(rows, {("Kage", "Casey"): 2661})        # no headshot exists for him (b780 rst2, Q46)
        pictured = {(r["first"], r["last"]) for r in manifest["portraits"]}
        self.assertIn(("Brett", "Thorson"), pictured)
        self.assertIn(("Hezekiah", "Masses"), pictured)

    def test_only_that_player_holding_that_stock_id_is_reset_and_a_real_portrait_wins(self):
        from mod_editor.core import nfl2k5_real_portraits as rp
        doc = _Doc([_P("Kage", "Casey", 2661, 10, 10, 0x1000),            # Hamilton's headshot: reset
                    _P("DaVon", "Hamilton", 2661, 2, 1, 0x2000),          # his own headshot: kept
                    _P("Brett", "Thorson", 4321, 1, 6, 0x3000),           # a user re-pictured him: kept
                    _P("Kage", "Casey", 2661, 10, 11, 0x4000),            # another birthday: not him
                    _P("Has", "Headshot", 1234, 2, 2, 0x5000)])           # listed portrait wins over the reset
        plan = rp.plan_assignments(doc, self.manifest())
        self.assertEqual(sorted(plan["writes"]), [(0x1000 + rp.PHOTO_FIELD, rp.NO_PHOTO_REFRESH, "Kage Casey"),
                                                  (0x5000 + rp.PHOTO_FIELD, 30000, "Has Headshot")])
        self.assertEqual(plan["no_photo"], ["Kage Casey"])
        reset = _Doc([_P("Kage", "Casey", rp.NO_PHOTO_REFRESH, 10, 10, 0x1000)])
        self.assertEqual(rp.plan_assignments(reset, self.manifest())["writes"], [])

    def test_a_wrong_face_row_must_name_a_stock_portrait_and_whose_face_it_is(self):
        import tempfile
        from mod_editor.core import nfl2k5_real_portraits as rp
        doc = json.loads(rp.MANIFEST.read_text(encoding="utf-8"))
        for bad in ({"photo_id": rp.NO_PHOTO_REFRESH}, {"photo_id": 30001}, {"shows": ""}):
            broken = copy.deepcopy(doc)
            broken["wrong_faces"][0].update(bad)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "portraits.json"
                path.write_text(json.dumps(broken), encoding="utf-8")
                with self.assertRaises(rp.RealPortraitsError, msg=bad):
                    rp.load_manifest(path)


# ------------------------------------------------------------------------------------------------ pack data
@unittest.skipUnless(V08_ROST.is_file() and RELEASE_PLAN.is_file(),
                     "NFL2K5_RELEASE_ROSTER_EDITS (the release roster edits, room_policy ir) or the v0.8 disc roster is not set")
class ReleaseRosterInjuredReserveTests(unittest.TestCase):
    """b780-int: the release roster edits (RST2, room_policy "ir") replayed on the released v0.8 disc roster, as the
    v0.9 build runs them. NFL2K5_V08_ROSTER_EDITS stays the beta-79 file the other pack tests expect."""

    @classmethod
    def setUpClass(cls):
        body = V08_ROST.read_bytes()
        if hashlib.sha256(body).hexdigest() != V08_ROST_SHA256:
            raise unittest.SkipTest("v0.8 disc roster pin differs")
        cls.document = json.loads(RELEASE_PLAN.read_text(encoding="utf-8"))
        cls.plan = cls.document["roster_refresh"]
        cls.out, cls.receipt = refresh.apply_body(body, cls.plan)
        cls.doc = rr.RosterDocument(cls.out, scheme="one_pool", reference_year=2026)

    def test_every_injured_player_the_plan_keeps_starts_on_injured_reserve(self):
        """b780 IR1 (room_policy "ir"): the plan's injured players stay on their clubs, marked out 8 weeks (17 when out
        since week 4), and nobody is released for room."""
        self.assertEqual(self.plan.get("room_policy"), "ir")
        injured = {r["index"]: r for r in self.plan["players"] if r["status"] == "RES" and r["team"]}
        self.assertEqual(self.receipt["injured_reserve"]["released_for_room"], 0)
        marked = [self.doc.by_pool("primary")[i] for i in injured if self.doc.club_of(self.doc.by_pool("primary")[i]) is not None]
        self.assertEqual(len(marked), self.receipt["injured_reserve"]["rejoined"])
        for player in marked:
            self.assertTrue(starts_on_ir(self.doc, player), player.display)
            weeks = (struct.unpack_from("<I", self.doc.body, player.offset + 0x20)[0] >> 22) & 0xFF
            self.assertIn(weeks, (8, 17), player.display)
        for team in self.doc.teams[:32]:
            on_ir = [p for p in self.doc.team_players(team.index) if starts_on_ir(self.doc, p)]
            self.assertLessEqual(len(self.doc.team_players(team.index)) + len(self.doc.reserves.get(team.index, ())), 65)
            self.assertLessEqual(len(self.doc.team_players(team.index)) - len(on_ir), 53)


@unittest.skipUnless(V08_ROST.is_file() and V08_PLAN.is_file(), "private v0.8 disc roster / b779 roster edits absent")
class PackRosterLintTests(unittest.TestCase):
    """The pack's dated refresh replayed on the released v0.8 disc roster, as the v0.9 build runs it."""

    @classmethod
    def setUpClass(cls):
        body = V08_ROST.read_bytes()
        if hashlib.sha256(body).hexdigest() != V08_ROST_SHA256:
            raise unittest.SkipTest("v0.8 disc roster pin differs")
        cls.document = json.loads(V08_PLAN.read_text(encoding="utf-8"))
        cls.plan = cls.document["roster_refresh"]
        cls.out, cls.receipt = refresh.apply_body(body, cls.plan)
        cls.doc = rr.RosterDocument(cls.out, scheme="one_pool", reference_year=2026)

    def test_every_club_fields_its_formations_and_specialists(self):
        self.assertEqual(unexpected(lint(self.doc)), {})

    def test_no_depth_row_is_left_empty_by_the_release_for_room(self):
        charts = {k: v for k, v in lint(self.doc).items() if k[1].startswith("chart") and k not in KNOWN}
        self.assertEqual(charts, {})
        if self.plan.get("room_policy") != "ir":
            self.assertGreater(self.receipt["injured_reserve"]["released_for_room"], 0)

    def test_the_release_for_room_never_takes_a_charted_starter(self):
        """b780 rst2 (Q43): Aiden Fisher HOU WLB1, Corey Bullock CAR LG1, Travis Glover GB RG1, Hezekiah Masses LV RCB1,
        RJ Harvey DEN RB2 and Theo Johnson NYG TE2 were released for room under the lowest-rated rule."""
        rows = {r["index"]: r for r in self.plan["players"]}
        final = {i for t in self.doc.teams[:32] for i in (self.doc.by_offset[o].index for o in t.slots)}
        released = [i for t in self.plan["teams"] for i in t["active"] if i not in final]
        self.assertEqual(len(released), self.receipt["injured_reserve"]["released_for_room"])
        starters = [f"{rows[i]['first']} {rows[i]['last']} ({rows[i]['team']})" for i in released
                    if str((rows[i].get("depth_source") or {}).get("pos_rank")) == "1"]
        self.assertEqual(starters, [])

    def test_the_specialists_are_active_players_of_their_club(self):
        rows = {r["index"]: r for r in self.plan["players"]}
        for team in self.plan["teams"]:
            for key, index in team["specialists"].items():
                if index is None:
                    self.assertIn((team["team"], f"special {key}"), KNOWN, team["team"])
                    continue
                self.assertIn(index, team["active"], (team["team"], key))
                self.assertIn(rows[index]["status"], ("ACT", "INA"), (team["team"], key))     # on the club's 53

    def test_no_free_agent_carries_a_contract(self):
        """b780 rst2 (Q44): unsigned contracts are zero, as retail's free agents."""
        for offset in self.doc.free_agents:
            record = self.doc.by_offset[offset].record
            self.assertEqual([record.get(k) for k in refresh.CONTRACT_FIELDS], [0] * 5, self.doc.by_offset[offset].display)

    def test_the_refresh_replays_to_itself(self):
        self.assertEqual(refresh.apply_body(self.out, self.plan)[0], self.out)


@unittest.skipUnless(LINT_IMAGE.is_file(), "NFL2K5_PACK_LINT_IMAGE (a built SOFTDRINK disc image) not set")
class PackImageLintTests(unittest.TestCase):
    def test_the_built_roster_passes_the_lint(self):
        doc = rr.load_image(LINT_IMAGE, scheme="one_pool", reference_year=2026)
        self.assertEqual(unexpected(lint(doc, portraits=True)), {})


if __name__ == "__main__":
    unittest.main()

"""The roster team-history writer: CSV parsing and era codes, matching, the pool rebuild
invariants, the digest gate order with the other roster passes, the image write, and the shipped
team-column getter reading the written entries under unicorn.

Offline tests use a synthetic ROST body (the retail layout: object at +0x40, 0x54 records, 0x1F4
team records, a 50,000-dword pool at 0x41A74).  Tests on the retail roster run only when the
private extraction (loose packs) is present; unicorn tests also need the retail default.xbe.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import modpack  # noqa: E402
from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_team_column as tc  # noqa: E402
from mod_editor.core import nfl2k5_team_history as th  # noqa: E402

RETAIL_EXTRACTION = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
RETAIL_XBE = RETAIL_EXTRACTION / "default.xbe"
HAVE_RETAIL = (RETAIL_EXTRACTION / "vc_53450030" / "0").is_file()
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None

D = dt.date


# --------------------------------------------------------------------------------------------- synthetic body
PLAYERS_OFF = 0xAFA8
TEAMS_OFF = 0x41C8
POOL_OFF = 0x41A74
STRINGS_OFF = 0x7B970
TEAM_ABBRS = ("SF", "CHI", "CIN", "BUF", "DEN", "CLE", "TB", "ARZ", "SD", "KC", "IND", "DAL", "MIA", "PHI", "ATL", "NYG",
              "JAX", "NYJ", "DET", "GB", "CAR", "NE", "OAK", "STL", "BAL", "WAS", "NO", "SEA", "PIT", "HOU", "TEN", "MIN",
              "USER1", "USER2", "HIST")


def entry(slot: int, field: int, value: int, *, end: bool = False, deleted: bool = False, post: bool = False, folded: bool = False) -> int:
    word = (slot << 23) | (field << 16) | (value & 0xFFFF)
    return word | (0x80000000 if end else 0) | (0x10000000 if deleted else 0) | (0x20000000 if post else 0) | (0x40000000 if folded else 0)


def games(slots, *, extra=()) -> list[int]:
    """A stream with a games entry (field 0) per slot plus optional extra entries; bit 31 on the last."""

    words = [entry(s, 0, 16) for s in slots] + list(extra)
    words[-1] |= 0x80000000
    return words


def synthetic_body(players: list[dict], *, pool_used_pad: int = 0) -> bytes:
    """players: dicts with first, last, birth (date|None), position (int), count (int), stream (list[int]|None)."""

    body = bytearray(th.BODY_SIZE)
    body[0x0C:0x10] = b"ROST"
    struct.pack_into("<I", body, 0x10, 17)
    obj = th.OBJ_OFF

    def rel(field_off: int, target: int) -> None:
        struct.pack_into("<i", body, field_off, target - field_off + 1)

    strings = STRINGS_OFF

    def put_string(text: str) -> int:
        nonlocal strings
        at = strings
        raw = text.encode("utf-16-le") + b"\0\0"
        body[at: at + len(raw)] = raw
        strings += len(raw) + (len(raw) % 4)
        return at

    struct.pack_into("<I", body, obj + 0x18, len(TEAM_ABBRS))
    rel(obj + 0x1C, TEAMS_OFF)
    for k, abbr in enumerate(TEAM_ABBRS):
        rel(TEAMS_OFF + k * th.TEAM_SIZE + 0x108, put_string(abbr))
    struct.pack_into("<I", body, obj + 0x00, len(players))
    rel(obj + 0x04, PLAYERS_OFF)
    rel(obj + 0x44, POOL_OFF)
    at = POOL_OFF
    for index, p in enumerate(players):
        off = PLAYERS_OFF + index * th.PLAYER_SIZE
        rel(off + 0x10, put_string(p["first"]))
        rel(off + 0x14, put_string(p["last"]))
        birth = p.get("birth")
        word18 = ((birth.year - 1900) << 21 | birth.day << 16 | birth.month << 12) if birth else 0
        struct.pack_into("<I", body, off + 0x18, word18)
        struct.pack_into("<I", body, off + 0x24, 0x06310004 | (p["count"] << 8))
        body[off + 0x35] = p["position"]
        stream = p.get("stream")
        if stream:
            rel(off + 0x2C, at)
            for word in stream:
                struct.pack_into("<I", body, at, word)
                at += 4
    used = (at - POOL_OFF) // 4
    if pool_used_pad:
        # fill the pool up to a chosen used count with one more player-less dead stream is not possible
        # (streams must belong to players), so the last player's stream is padded with deleted entries
        last = players[-1]
        assert last.get("stream"), "padding needs a last player with a stream"
        struct.pack_into("<I", body, at - 4, struct.unpack_from("<I", body, at - 4)[0] & 0x7FFFFFFF)
        for _ in range(pool_used_pad):
            struct.pack_into("<I", body, at, entry(1, 5, 1, deleted=True))
            at += 4
        struct.pack_into("<I", body, at - 4, struct.unpack_from("<I", body, at - 4)[0] | 0x80000000)
        used = (at - POOL_OFF) // 4
    struct.pack_into("<I", body, obj + 0x40, used)
    return bytes(body)


def sample_players() -> list[dict]:
    return [
        {"first": "Joey", "last": "Harrington", "birth": D(1978, 10, 21), "position": 0, "count": 3, "stream": games([1, 2])},
        {"first": "Christopher", "last": "McAlister", "birth": D(1977, 6, 14), "position": 4, "count": 6, "stream": games([1, 2, 3, 5])},
        {"first": "Terrell", "last": "Owens", "birth": D(1973, 12, 7), "position": 3, "count": 9, "stream": games([2, 3, 4, 5, 6, 7, 8])},
        {"first": "Chris", "last": "Watson", "birth": D(1977, 6, 30), "position": 4, "count": 5, "stream": games([2, 3])},
        {"first": "Chris", "last": "Watson", "birth": D(1977, 6, 30), "position": 4, "count": 5, "stream": games([2, 3])},
        {"first": "Jerry", "last": "Rice", "birth": D(1962, 10, 13), "position": 3, "count": 20, "stream": games(list(range(1, 20)))},
        {"first": "Al", "last": "Rookie", "birth": D(1981, 1, 1), "position": 7, "count": 1, "stream": None},
        {"first": "Pat", "last": "Nodob", "birth": None, "position": 1, "count": 4, "stream": games([1, 2, 3])},
    ]


CSV_HEAD = "# comment line\nlast_name,first_name,birth_date,season,team,position,roster_index\n"


class CsvAndCodeTests(unittest.TestCase):
    def test_era_codes_map_to_the_2004_abbreviations(self) -> None:
        cases = {("HOU", 1990): "TEN", ("HOU", 1996): "TEN", ("HOU", 2003): "HOU", ("STL", 1985): "ARZ", ("STL", 1987): "ARZ",
                 ("STL", 1999): "STL", ("STL", 1993): "STL", ("BAL", 1980): "IND", ("BAL", 2000): "BAL", ("RAI", 1985): "OAK",
                 ("RAM", 1990): "STL", ("SL", 2003): "STL", ("PHX", 1990): "ARZ", ("ARI", 1999): "ARZ", ("ARZ", 2003): "ARZ",
                 ("BLT", 2003): "BAL", ("CLV", 2003): "CLE", ("HST", 2003): "HOU", ("CLE", 1994): "CLE", ("TEN", 1998): "TEN",
                 ("oak", 2003): "OAK", (" gb ", 2001): "GB"}
        for (code, season), want in cases.items():
            self.assertEqual(th.resolve_team(code, season)[0], want, (code, season))
        self.assertEqual(th.resolve_team("HOU", 1990)[1], "Houston Oilers")
        for code, season in (("LA", 1990), ("XYZ", 2000), ("", 2000)):
            with self.assertRaises(th.TeamHistoryError):
                th.resolve_team(code, season)

    def test_names_and_dates(self) -> None:
        self.assertEqual(th.normalise_name("O'Neal Jr."), "oneal")
        self.assertEqual(th.normalise_name("Smith III"), "smith")
        self.assertEqual(th.normalise_name("  De La  Cruz "), "delacruz")
        self.assertEqual(th.normalise_name("Ñíguez"), "niguez")
        self.assertEqual(th.parse_birth_date("1978-10-21"), D(1978, 10, 21))
        self.assertEqual(th.parse_birth_date("10/21/1978"), D(1978, 10, 21))
        self.assertIsNone(th.parse_birth_date(""))
        with self.assertRaises(th.TeamHistoryError):
            th.parse_birth_date("21-10-1978")
        self.assertEqual(th.decode_birth(0x09D5A80E), D(1978, 10, 21))     # Harrington's retail word

    def test_csv_parsing_and_errors(self) -> None:
        rows = th.read_csv(CSV_HEAD + "Harrington,Joey,1978-10-21,2002,DET,,\nOwens,Terrell,1973-12-07,1996,SF,WR,\n")
        self.assertEqual([(r.last, r.season, r.team, r.position) for r in rows], [("Harrington", 2002, "DET", None), ("Owens", 1996, "SF", "WR")])
        self.assertEqual(rows[0].birth, D(1978, 10, 21))
        for bad, message in (("last_name,first_name,season,team\nA,B,2000,SF\n", "lacks the columns"),
                             (CSV_HEAD + "A,B,2000-13-01,2000,SF,,\n", "bad birth date"),
                             (CSV_HEAD + "A,B,2000-01-01,two,SF,,\n", "bad season"),
                             (CSV_HEAD + "A,B,2000-01-01,2000,XYZ,,\n", "unknown team code"),
                             (CSV_HEAD + "A,B,2000-01-01,1990,LA,,\n", "ambiguous"),
                             (CSV_HEAD + ",B,2000-01-01,2000,SF,,\n", "empty last name"),
                             ("# only comments\n", "no rows")):
            with self.assertRaises(th.TeamHistoryError, msg=bad) as ctx:
                th.read_csv(bad)
            self.assertIn(message, str(ctx.exception))


class MatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body = synthetic_body(sample_players())
        self.roster = th.parse_body(self.body)

    def test_parse_reads_identities_streams_and_teams(self) -> None:
        r = self.roster
        self.assertEqual(r.player_count, 8)
        self.assertEqual(r.teams[:3], ["SF", "CHI", "CIN"])
        self.assertEqual(r.team_index("DET"), 18)
        h = r.players[0]
        self.assertEqual((h.first, h.last, h.birth, h.position, h.count), ("Joey", "Harrington", D(1978, 10, 21), 0, 3))
        self.assertEqual(h.games_slots(), {1, 2})
        self.assertIsNone(r.players[6].stream)
        self.assertEqual(r.used, sum(len(p.entries) for p in r.players))
        self.assertEqual(th.body_status(self.body), "foreign", "a synthetic pool is neither retail nor applied")

    def test_match_tiers_and_row_gates(self) -> None:
        text = CSV_HEAD + "\n".join([
            "Harrington,Joey,1978-10-21,2002,DET,,",            # exact
            "Harrington,Joey,1978-10-21,2003,DET,,",            # exact
            "Harrington,Joey,1978-10-21,2003,DET,,",            # duplicate row
            "Harrington,Joey,1978-10-21,2004,DET,,",            # the current season: outside (>= base year)
            "Harrington,Joey,1978-10-21,1999,DET,,",            # outside the record's seasons
            "McAlister,Chris,1977-06-14,2003,BLT,,",            # last name + DOB fallback (Chris vs Christopher)
            "McAlister,Chris,1977-06-14,2002,BLT,,",            # no games entry for slot 4 -> row would not show
            "Owens,Terrell,,1997,SF,WR,",                       # no DOB: name + position fallback (warned); slot 2
            "Watson,Chris,1977-06-30,2002,DEN,,",               # two identical records -> ambiguous
            "Watson,Chris,1977-06-30,2002,DEN,CB,3",            # pinned by roster_index
            "Rice,Jerry,1962-10-13,1986,SF,,",                  # 18 seasons back: never displayed
            "Rice,Jerry,1962-10-13,2000,SF,,",                  # exact, slot 16 -> displayed
            "Nobody,Joe,1970-01-01,2003,SF,,",                  # none
            "Nodob,Pat,,2002,KC,K,",                            # no DOB in the record either: name + position
        ]) + "\n"
        rows = th.read_csv(text)
        additions, log = th.match_rows(self.roster, rows)
        self.assertEqual(additions[0], {1: 18, 2: 18})
        self.assertEqual(additions[1], {5: 24})
        self.assertEqual(additions[2], {2: 0})
        self.assertEqual(additions[3], {3: 4})
        self.assertEqual(additions[5], {16: 0})
        self.assertEqual(additions[7], {2: 9})
        self.assertNotIn(4, additions)
        self.assertEqual((log.exact, log.fallback_dob, log.fallback_position, log.ambiguous, log.none), (3, 1, 2, 1, 1))
        self.assertEqual((log.seasons_written, log.would_not_show, log.never_displayed, log.outside_career, log.duplicate_rows),
                         (7, 1, 1, 2, 1))
        self.assertTrue(any("WARNING" in line and "Owens" in line for line in log.lines))
        self.assertTrue(any("row would not show" in line and "McAlister" in line for line in log.lines))
        self.assertTrue(any("several records" in line and "Watson" in line for line in log.lines))
        # a second pass over the written body finds the entries present and writes nothing new
        patched = th.rebuild(self.roster, additions)
        again, log2 = th.match_rows(th.parse_body(patched), rows)
        self.assertEqual(again, {})
        self.assertEqual(log2.already_present, 7)


class RebuildTests(unittest.TestCase):
    def test_rebuild_inserts_at_head_keeps_every_entry_and_touches_nothing_else(self) -> None:
        players = sample_players()
        body = synthetic_body(players)
        roster = th.parse_body(body)
        additions = {0: {1: 18, 2: 18}, 2: {2: 0, 8: 13}}
        out = th.rebuild(roster, additions)
        after = th.parse_body(out)
        self.assertEqual(after.used, roster.used + 4)
        for before_p, after_p in zip(roster.players, after.players):
            adds = additions.get(before_p.index, {})
            self.assertEqual(after_p.entries[len(adds):], before_p.entries, before_p.index)
            self.assertEqual([(w >> 23) & 0x1F for w in after_p.entries[:len(adds)]], sorted(adds))
            for word in after_p.entries[:len(adds)]:
                self.assertEqual((word >> 16) & 0x7F, tc.TEAM_FIELD)
                self.assertEqual((word & 0xFFFF) - 1, adds[(word >> 23) & 0x1F])
                self.assertFalse(word & 0x70000000)
            if after_p.entries:
                self.assertTrue(after_p.entries[-1] & 0x80000000)
                self.assertFalse(any(w & 0x80000000 for w in after_p.entries[:-1]))
        # +0x2C targets re-resolve to the first live entry of the same player, streams stay contiguous
        at = after.pool
        for p in sorted((p for p in after.players if p.stream is not None), key=lambda p: p.stream):
            self.assertEqual(p.stream, at)
            at += len(p.entries) * 4
        self.assertEqual(at, after.pool + after.used * 4)
        # nothing outside the pool region, the +0x2C words and the used count changed
        allowed = set(range(roster.pool, roster.pool + th.POOL_CAPACITY * 4)) | set(range(th.OBJ_OFF + 0x40, th.OBJ_OFF + 0x44))
        for p in roster.players:
            allowed.update(range(p.offset + 0x2C, p.offset + 0x30))
        changed = {i for i, (a, b) in enumerate(zip(body, out)) if a != b}
        self.assertTrue(changed <= allowed)
        self.assertEqual(th.body_status(out), "applied-custom")
        self.assertEqual(th.summary(out)["team_entries"], 4)

    def test_capacity_and_streamless_players_are_refused(self) -> None:
        body = synthetic_body(sample_players(), pool_used_pad=th.POOL_CAPACITY - 40)
        roster = th.parse_body(body)
        self.assertGreater(roster.used, th.POOL_CAPACITY - 10)
        with self.assertRaises(th.TeamHistoryError):
            th.rebuild(roster, {0: {1: 18}, 2: {s: 0 for s in range(2, 9)}, 5: {s: 0 for s in range(1, 20)}})
        with self.assertRaises(th.TeamHistoryError):
            th.rebuild(th.parse_body(synthetic_body(sample_players())), {6: {1: 0}})
        with self.assertRaises(th.TeamHistoryError):
            th.rebuild(th.parse_body(synthetic_body(sample_players())), {0: {1: 40}})


class ShippedDataTests(unittest.TestCase):
    def test_shipped_csv_is_pinned_attributed_and_parses(self) -> None:
        self.assertTrue(th.SHIPPED_CSV.is_file())
        data = th.SHIPPED_CSV.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), th.SHIPPED_CSV_SHA256)
        text = data.decode("utf-8")
        self.assertIn("nflverse", text.splitlines()[1])
        self.assertIn("CC-BY-4.0", text)
        rows, provenance = th.load_rows("retail")
        self.assertEqual(provenance["source"], "retail")
        self.assertGreater(len(rows), 5000)
        self.assertTrue(all(r.team in th.RETAIL_TEAM_INDEX for r in rows), "the shipped CSV uses 2004 abbreviations only")
        self.assertTrue(all(1982 <= r.season <= 2003 and r.birth is not None for r in rows))
        self.assertTrue((th.SHIPPED_CSV.parent / "nfl2k5_retail_team_history.match.log").is_file())
        self.assertIn("team_history", mod_build.availability())

    def test_build_plan_presets_and_pack_description(self) -> None:
        self.assertEqual(mod_build.PRESETS["softdrink_basic"]["team_history"], "")
        self.assertEqual(mod_build.PRESETS["softdrink_advanced"]["team_history"], "retail")
        self.assertEqual(mod_build.PRESETS["softdrink_experimental"]["team_history"], "retail")
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_advanced")
        self.assertEqual(plan.team_history, "retail")
        self.assertIn("team_history", plan.to_recipe())
        self.assertFalse(mod_build.BuildPlan(source="s", target="t", team_history="retail").wants_xbe_patch())
        self.assertIn("nflverse", modpack.describe_operation({"op": "team_history", "source": "retail"}))
        self.assertIn("custom", modpack.describe_operation({"op": "team_history", "source": "custom"}))
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "default.xbe"
            src.write_bytes(b"XBEH" + bytes(64))
            with self.assertRaises(ValueError):
                mod_build.build(mod_build.BuildPlan(source=str(src), target=str(Path(tmp) / "out.xbe"), team_history="retail"))

    def test_build_panel_carries_the_toggle_and_the_csv_field(self) -> None:
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui.build_panel_qt import BuildPanel

        app = QApplication.instance() or QApplication([])   # noqa: F841
        panel = BuildPanel()
        try:
            panel.apply_state({"path": "x.iso", "container": "xiso", "team_history": "retail", "throw": None})
            self.assertTrue(panel.team_history_check.isEnabled())
            panel.apply_state({"path": "default.xbe", "container": "xbe", "team_history": "n/a", "throw": None})
            self.assertFalse(panel.team_history_check.isEnabled())
            panel.apply_state({"path": "x.iso", "container": "xiso", "team_history": "retail", "throw": None})
            self.assertEqual(panel.plan().team_history, "")
            panel.team_history_check.setChecked(True)
            self.assertEqual(panel.plan().team_history, "retail")
            panel.team_history_field.setText("/tmp/my_history.csv")
            self.assertEqual(panel.plan().team_history, "/tmp/my_history.csv")
            self.assertTrue(panel.has_work())
        finally:
            panel.deleteLater()


@unittest.skipUnless(HAVE_RETAIL, "private retail extraction not present")
class RetailRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with th._outer_image()(RETAIL_EXTRACTION) as archive:
            entry = th._entry(archive)
            cls.resource = archive.read(entry.virtual_offset, entry.size)
        cls.body = cls.resource[th.RESOURCE_HEADER_SIZE:]
        cls.roster = th.parse_body(cls.body)
        cls.rows, _prov = th.load_rows("retail")
        cls.patched, cls.receipt = th.apply_body(cls.body, cls.rows)
        cls.after = th.parse_body(cls.patched)

    def test_retail_pool_and_status(self) -> None:
        self.assertEqual((self.roster.used, self.roster.pool), (th.RETAIL_POOL_USED, 0x41A74))
        self.assertEqual(th.pool_digest(self.roster), th.RETAIL_POOL_SHA256)
        self.assertEqual(th.body_status(self.body), "retail")
        self.assertEqual(th.resource_status(self.resource), "retail")
        self.assertEqual(th.status(RETAIL_EXTRACTION), "retail")
        self.assertEqual(th.summary(self.body), {"players_with_history": 1325, "seasons_with_games": 5867, "team_entries": 0,
                                                 "pool_used": 36866, "pool_free": 13134})

    def test_round_trip_on_the_retail_roster(self) -> None:
        receipt = self.receipt
        matches = receipt["matches"]
        self.assertEqual(receipt["pool_used_before"], 36866)
        self.assertEqual(receipt["pool_used_after"],
                         36866 + matches["seasons_written"] + matches["seasons_inferred"])
        self.assertLessEqual(receipt["pool_used_after"], th.POOL_CAPACITY)
        self.assertEqual(matches["none"], 0)
        self.assertEqual(matches["ambiguous"], 0)
        self.assertEqual(matches["would_not_show"], 0)
        self.assertGreater(matches["seasons_written"], 5000)
        self.assertEqual(th.body_status(self.patched), "applied")
        self.assertEqual(th.pool_digest(self.after), th.SHIPPED_POOL_SHA256)
        by_index = {p.index: p for p in self.after.players}
        for before in self.roster.players:
            after = by_index[before.index]
            team_words = [w for w in after.entries if ((w >> 16) & 0x7F) == tc.TEAM_FIELD]
            self.assertEqual(after.entries[len(team_words):], before.entries, before.index)
            self.assertEqual(after.games_slots(), before.games_slots())
            self.assertTrue(after.team_slots() <= before.games_slots(), before.index)
            for word in team_words:
                self.assertFalse(word & 0x70000000)
                self.assertTrue(1 <= (word & 0xFFFF) <= 32)
        changed = {i for i, (a, b) in enumerate(zip(self.body, self.patched)) if a != b}
        allowed = set(range(self.roster.pool, self.roster.pool + th.POOL_CAPACITY * 4)) | set(range(th.OBJ_OFF + 0x40, th.OBJ_OFF + 0x44))
        for p in self.roster.players:
            allowed.update(range(p.offset + 0x2C, p.offset + 0x30))
        self.assertTrue(changed <= allowed)
        # Harrington: 2002 and 2003 with Detroit
        h = by_index[512]
        self.assertEqual((h.first, h.last), ("Joey", "Harrington"))
        self.assertEqual({(w >> 23) & 0x1F: (w & 0xFFFF) - 1 for w in h.entries if ((w >> 16) & 0x7F) == tc.TEAM_FIELD}, {1: 18, 2: 18})
        # idempotent: a second application of the shipped CSV adds nothing
        again, receipt2 = th.apply_body(self.patched, self.rows)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt2["matches"]["seasons_written"], 0)
        self.assertEqual(receipt2["matches"]["seasons_inferred"], 0)

    def test_every_shown_season_gets_a_team_except_the_free_agents(self) -> None:
        """The TEAM column is consistent: the CSV where it matched, the 2004 club everywhere else."""

        receipt, matches = self.receipt, self.receipt["matches"]
        self.assertEqual(matches["displayable_seasons"], 5838)          # 5,867 games entries, 29 past the 15-row window
        self.assertEqual(matches["seasons_written"], 5042)              # the shipped nflverse CSV
        self.assertEqual(matches["seasons_inferred"], 704)              # filled with the player's own 2004 club
        self.assertEqual(matches["players_inferred"], 185)
        self.assertEqual(matches["seasons_no_team"], 92)                # 2004 free agents: on no club, nothing to infer
        self.assertEqual(matches["players_no_team"], 41)
        self.assertEqual(receipt["seasons_with_a_team"], 5746)
        self.assertEqual(receipt["seasons_without_a_team"], 92)
        self.assertEqual(th.summary(self.patched)["team_entries"], 5746)
        self.assertTrue(receipt["infer_current_team"])
        self.assertTrue(any("inferred" in line for line in receipt["log"]))
        self.assertTrue(any("keep \"--\"" in line for line in receipt["log"]))
        # every displayable season of a player who has a 2004 club now carries a team
        after = {p.index: p for p in self.after.players}
        for before in self.roster.players:
            shown = {s for s in before.games_slots() if 1 <= s < before.count and before.count - s <= th.MAX_DISPLAY_AGE}
            if self.roster.current_team.get(before.index) is None:
                continue
            self.assertEqual(after[before.index].team_slots(), shown, before.index)
        # and an inferred entry names the player's own 2004 club
        club = self.roster.current_team
        for index, player in after.items():
            for word in player.entries:
                if ((word >> 16) & 0x7F) == tc.TEAM_FIELD:
                    self.assertLess((word & 0xFFFF) - 1, th.NFL_TEAM_COUNT, index)
        self.assertIn(512, club)

    def test_the_fill_can_be_turned_off(self) -> None:
        out, receipt = th.apply_body(self.body, self.rows, infer_current_team=False)
        self.assertEqual(receipt["matches"]["seasons_inferred"], 0)
        self.assertEqual(receipt["matches"]["seasons_no_team"], 0)
        self.assertEqual(receipt["pool_used_after"], 36866 + receipt["matches"]["seasons_written"])
        self.assertEqual(th.summary(out)["team_entries"], receipt["matches"]["seasons_written"])

    def test_the_roster_knows_every_players_2004_club(self) -> None:
        club = self.roster.current_team
        self.assertEqual(len(club), 1696)                     # every player listed by one of the 32 club records
        self.assertTrue(all(0 <= k < th.NFL_TEAM_COUNT for k in club.values()))
        self.assertEqual(self.roster.teams[club[512]], "DET")  # Joey Harrington, Detroit in 2004
        with_games = {p.index for p in self.roster.players if p.games_slots()}
        self.assertEqual(len(with_games - set(club)), 170)     # the retail free agents

    def test_digest_gate_order_with_the_reclassify_and_schedule_passes(self) -> None:
        import nfl2k5_franchise_schedule as fs
        import nfl2k5_roster_reclassify as rr

        # the reclassify gate hashes the header (used count) and the records (+0x2C): our pass changes both,
        # so it must come after; its own edits (position / order words) leave our digest alone
        import dataclasses

        self.assertEqual(rr.status(RETAIL_EXTRACTION)["status"], "retail")
        with th._outer_image()(RETAIL_EXTRACTION) as archive:
            main = rr.load_resources(archive, historic=False)[0]
        patched_main = dataclasses.replace(main, body=self.patched) if dataclasses.is_dataclass(main) else None
        if patched_main is not None:
            self.assertNotEqual(rr.record_digest([patched_main]), rr.record_digest([main]), "our pass changes the reclassify digest: run after it")
        moved = bytearray(self.body)
        for p in self.roster.players[:50]:
            moved[p.offset + rr.PLAYER_POSITION] ^= 0x01            # what the reclassify pass writes
            struct.pack_into("<H", moved, p.offset + rr.PLAYER_ORDER_WORD, 0x155)
        self.assertEqual(th.body_status(bytes(moved)), "retail", "the reclassify edits do not touch our digest")
        out, _r = th.apply_body(bytes(moved), self.rows)
        self.assertEqual(th.body_status(out), "applied")
        # the schedule pass writes the tail and the header pair at ROST+0x60 (obj[0xA]/[0xB]); our pool
        # rewrite keeps its status, and its rewrite keeps ours
        pack = bytearray(self.resource)
        fake = bytearray(fs.PACK_ROST_OFFSET) + pack
        self.assertEqual(fs.pack_status(bytes(fake))["state"], "retail")
        fake_after_ours = bytearray(fs.PACK_ROST_OFFSET) + self.resource[:th.RESOURCE_HEADER_SIZE] + self.patched
        self.assertEqual(fs.pack_status(bytes(fake_after_ours))["state"], "retail")
        doc = __import__("json").loads((ROOT / "data" / "nfl_2026_schedule.json").read_text(encoding="utf-8"))
        template, _info = fs.encode_schedule(doc)
        preseason, _pinfo = fs.encode_preseason(doc) if hasattr(fs, "encode_preseason") else (b"", {})
        scheduled, _rec = fs.apply_pack(bytes(fake), template, preseason=preseason)
        self.assertEqual(fs.pack_status(scheduled)["state"], "applied")
        body_after_schedule = scheduled[fs.PACK_ROST_OFFSET + th.RESOURCE_HEADER_SIZE: fs.PACK_ROST_OFFSET + th.RESOURCE_SIZE]
        self.assertEqual(th.body_status(body_after_schedule), "retail", "the schedule pass leaves the pool alone")
        ours, _r = th.apply_body(body_after_schedule, self.rows)
        both = scheduled[: fs.PACK_ROST_OFFSET + th.RESOURCE_HEADER_SIZE] + ours + scheduled[fs.PACK_ROST_OFFSET + th.RESOURCE_SIZE:]
        self.assertEqual(fs.pack_status(both)["state"], "applied", "our pass keeps the schedule applied")
        self.assertEqual(th.body_status(ours), "applied")

    def test_apply_through_the_image_writer(self) -> None:
        from nfl2k5_xiso_fixture import SyntheticXiso

        with tempfile.TemporaryDirectory() as tmp:
            dummies = [(100 + k, b"DUMY" + bytes(0x100)) for k in range(5)]
            # a trailing dummy absorbs the fixture's end-of-pack padding so entry 5 keeps its exact size
            fixture = SyntheticXiso(Path(tmp), dummies + [(5, self.resource), (200, b"TAIL" + bytes(0x100))], pack_sizes=(0xA0000,), pack_sectors=(64,))
            self.assertEqual(th.status(fixture.path), "retail")
            receipt = th.apply(fixture.path, "retail")
            self.assertEqual(receipt["status"], "applied")
            self.assertEqual(receipt["pool_used_after"], self.receipt["pool_used_after"])
            self.assertEqual(th.status(fixture.path), "applied")
            with th._outer_image()(fixture.path) as archive:
                entry = th._entry(archive)
                written = archive.read(entry.virtual_offset, entry.size)
            self.assertEqual(written, self.resource[:th.RESOURCE_HEADER_SIZE] + self.patched)
            again = th.apply(fixture.path, "retail")
            self.assertTrue(again.get("already_applied"))
            # a foreign pool (used count no longer matches the streams) is refused
            with th._outer_image()(fixture.path, writable=True) as archive:
                entry = th._entry(archive)
                archive.write(entry.virtual_offset + th.RESOURCE_HEADER_SIZE + th.OBJ_OFF + 0x40,
                              struct.pack("<I", receipt["pool_used_after"] + 1))
            self.assertEqual(th.status(fixture.path), "foreign")
            with self.assertRaises(th.TeamHistoryError):
                th.apply(fixture.path, "retail")

    def test_custom_csv_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "mine.csv"
            csv_path.write_text(CSV_HEAD + "Harrington,Joey,1978-10-21,2002,HOU,,\n", encoding="utf-8")
            rows, provenance = th.load_rows(csv_path)
            self.assertEqual(provenance["source"], "custom")
            out, receipt = th.apply_body(self.body, rows, infer_current_team=False)
            self.assertEqual(receipt["matches"]["seasons_written"], 1)
            h = th.parse_body(out).players[512]
            self.assertEqual({(w & 0xFFFF) - 1 for w in h.entries if ((w >> 16) & 0x7F) == tc.TEAM_FIELD}, {29})
            self.assertEqual(th.body_status(out), "applied-custom")


@unittest.skipUnless(HAVE_RETAIL and RETAIL_XBE.is_file() and HAVE_UNICORN, "retail extraction, default.xbe and unicorn needed")
class UnicornGetterTests(unittest.TestCase):
    """The shipped TEAM-column getter (retail code + cave) reads the entries this module wrote."""

    SCRATCH = 0x00F00000

    @classmethod
    def setUpClass(cls) -> None:
        cls.patched_xbe, _r = tc.apply(RETAIL_XBE.read_bytes())
        with th._outer_image()(RETAIL_EXTRACTION) as archive:
            entry = th._entry(archive)
            body = archive.read(entry.virtual_offset, entry.size)[th.RESOURCE_HEADER_SIZE:]
        rows, _p = th.load_rows("retail")
        cls.body, _receipt = th.apply_body(body, rows)
        cls.roster = th.parse_body(cls.body)

    def _machine(self):
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0x00010000, 0x00E61000 - 0x00010000)
        for section in strength._sections(self.patched_xbe):
            if section.virtual_address in (0x11000, 0x4E3AE0, 0xA69980):
                uc.mem_write(section.virtual_address, self.patched_xbe[section.raw_offset: section.raw_offset + section.raw_size])
        # the roster body at SCRATCH with the pointers the getter follows made absolute (the game's relocation)
        base = self.SCRATCH
        relocated = bytearray(self.body)
        obj = th.OBJ_OFF

        def absolute(field_off: int) -> None:
            value = struct.unpack_from("<i", relocated, field_off)[0]
            if value:
                struct.pack_into("<I", relocated, field_off, base + field_off + value - 1)

        absolute(obj + 0x1C)
        absolute(obj + 0x44)
        absolute(obj + 0x04)
        teams_off = th._rel(self.body, obj + 0x1C)
        for k in range(len(self.roster.teams)):
            absolute(teams_off + k * th.TEAM_SIZE + 0x108)
        for p in self.roster.players:
            absolute(p.offset + 0x2C)
        uc.mem_map(base, 0xB0000)
        uc.mem_write(base, bytes(relocated))
        uc.mem_write(tc.ROSTER_GLOBAL, struct.pack("<I", base + obj))
        uc.mem_write(tc.CLASS_GLOBAL, struct.pack("<I", 0))
        return uc

    def _getter(self, uc, player_off: int, bank: int) -> str:
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP

        stack_top, sentinel = self.SCRATCH + 0xAF000, self.SCRATCH + 0xAF800
        uc.mem_write(tc.PLAYER_GLOBAL, struct.pack("<I", self.SCRATCH + player_off))
        uc.mem_write(stack_top - 4, struct.pack("<I", sentinel))
        uc.reg_write(UC_X86_REG_ESP, stack_top - 4)
        uc.reg_write(UC_X86_REG_ECX, bank)
        uc.emu_start(tc.GETTER_VA, sentinel, count=200_000)
        pointer = uc.reg_read(UC_X86_REG_EAX)
        return bytes(uc.mem_read(pointer, 24)).decode("utf-16-le").split("\0")[0]

    def test_getter_resolves_written_seasons_to_abbreviations(self) -> None:
        uc = self._machine()
        harrington = self.roster.players[512]
        self.assertEqual(self._getter(uc, harrington.offset, 12), "DET")     # bank 12 = slot 2 = 2003
        self.assertEqual(self._getter(uc, harrington.offset, 13), "DET")     # bank 13 = slot 1 = 2002
        self.assertEqual(self._getter(uc, harrington.offset, 14), "--")      # slot 0 does not exist
        self.assertEqual(self._getter(uc, harrington.offset, 9), "")
        # a player with two clubs across the written seasons
        mover = None
        for p in self.roster.players:
            teams = {(w & 0xFFFF) - 1 for w in p.entries if ((w >> 16) & 0x7F) == tc.TEAM_FIELD}
            if len(teams) >= 2 and {p.count - 1, p.count - 2} <= p.team_slots():
                mover = p
                break
        self.assertIsNotNone(mover)
        by_slot = {(w >> 23) & 0x1F: (w & 0xFFFF) - 1 for w in mover.entries if ((w >> 16) & 0x7F) == tc.TEAM_FIELD}
        self.assertEqual(self._getter(uc, mover.offset, 12), self.roster.teams[by_slot[mover.count - 1]])
        self.assertEqual(self._getter(uc, mover.offset, 13), self.roster.teams[by_slot[mover.count - 2]])


if __name__ == "__main__":
    unittest.main()

"""Stale per-team and per-stadium booth lines (b81 sb-booth, audit parts 2 and 4, review fixes). No emulator.

Retail-free tests check the rule table against the pinned retail context lists and the decisions on synthetic disc
facts. Retail tests (skipped without the user-owned USA disc folder) read the real ``lines`` speech index and
executable: every rule key uses exactly its pinned lists, no other key shares them, the patch changes only rule
contexts, a second patch changes nothing, a foreign list refuses, the user's own recordings are left reachable, a
synthetic disc carrying the real speech index round-trips, the handler kinds match the executable's handler table, and
the line each key plays after the edit (the handler and resolver model) is pinned against transcripts of the retail
recordings (faster-whisper small.en on the retail streams, job sb-venue).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import build_steps  # noqa: E402
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_stale_speech as s  # noqa: E402
from mod_editor.core import nfl2k5_stadium_welcome as w  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", ROOT / "extracted")) / "ESPN NFL 2K5 (USA)" / "vc_53450030"
HAVE_RETAIL = (RETAIL / "0").is_file()
RETAIL_XBE = RETAIL.parent / "default.xbe"
#: SHA-256 of the modelled functions in the retail executable: 0x1398E0 (0x90 bytes), 0x138200 (0x27), 0x2B3B90 (0x7A)
MODELLED = {(0x1398E0, 0x90): "6160d8be6d4b47759006bec73a8d782ca5af65cb1fa3e16863b1b84af04599f2",
            (0x138200, 0x27): "e64caede6b746c98f6f1c287de1900fadc1377f4cf3ea32c2e50413dbca742a5",
            (0x2B3B90, 0x7A): "8da0b94b25f762c53c9576f205b322e4d3ed3ed0fec82e8e1ab7a6933fd57849"}
#: What Washington (speech id 29) hears, per key and side: (retail streams, streams after the edit), one per speaker
#: variant (None = the phrase is dropped). The text is the transcript of the stream (retail ISO, small.en). The second
#: speaker's touchdown and safety calls (9424/9426 v1) carry the stadium music after the call, 25 to 50 s, for every
#: club alike.
WASHINGTON = {
    512: {"home": ((15525,), (None,)), "visitor": ((15525,), (None,))},       # "ball at the red skin" -> dropped
    1201: {"home": ((15626,), (15641,)),                                       # "The Redskins have it." ->
           "visitor": ((15626,), (15642,))},                                   # "The home team has it." / "The visiting team has it!"
    9405: {"home": ((16884,), (16899,)),                                       # "Ball at the Redskins." -> "Ball at the home team."
           "visitor": ((16884,), (16900,))},                                   # "Ball at the visiting team."
    9413: {"home": ((17013,), (17028,)),                                       # "kicking off with a red skin." ->
           "visitor": ((17013,), (17029,))},                                   # "kicking off for the home / visiting team."
    9414: {"home": ((14498, 14498), (14502, 14502))},                          # "It's time for Redskins football." -> "It's time for football!"
    9424: {"home": ((14532, 14622), (14638, 14638)),                           # "Touchdown, Redskins!" -> "Touchdown home team!"
           "visitor": ((14532, 14622), (14547, 14639))},                       # "Touchdown visiting team." / "Touchdown!"
    9425: {"home": ((14926, 15016), (15032, 15032)),                           # "First down, Redskins." -> "First down, home team."
           "visitor": ((14926, 15016), (14941, 14941))},                       # "first down visiting team."
    9426: {"home": ((15117, 15207), (15223, 15223)),                           # "Safety Redskins" -> "Safety home team"
           "visitor": ((15117, 15207), (15132, 15132))},                       # "Safety Visiting Team."
    9427: {"home": ((15298, 15343), (15358, 15358)),                           # "Interception, Redskins." -> "Interception, home team."
           "visitor": ((15298, 15343), (15313, 15313))},                       # "Interception visiting team."
    9456: {"home": ((29983,), (29997,)), "visitor": ((29983,), (29997,))},   # "And now your redskins!" -> "And now, your very own team."
    9467: {"home": ((17508,), (17525,))},                                      # "your washington redskins" -> "Your home team."
    9468: {"visitor": ((17555,), (17572,))},                                   # "the washington redskins" -> "The visiting team."
    9474: {"visitor": ((17806,), (None,))},                                    # "The Redskins." -> dropped
    9475: {"home": ((17840,), (None,))},                                       # "your redskins" -> dropped
    9476: {"visitor": ((17874,), (None,))},                                    # "The Redskins." -> dropped
    38247: {"visitor": ((19607,), (19627,))},                                  # "RED SKINS!" -> "Away, team!"
    38248: {"home": ((19658,), (19677,))},                                     # "Red Skins!" -> "Home team."
    38803: {"home": ((20659,), (None,)), "visitor": ((20659,), (None,))},      # the Washington blurb -> dropped
    38851: {"visitor": ((20847,), (None,))},                                   # "SKINS!" -> dropped
    38852: {"home": ((20868,), (None,))},                                      # "SKINS!" -> dropped
    38853: {"visitor": ((20898,), (20925,))},                                  # "RED SKINS!" -> "Away, team!"
    38854: {"home": ((20956,), (20982,))},                                     # "Red Skins!" -> "Home team."
    38859: {"visitor": ((21114,), (None,))},                                   # "Washington Redskins." -> dropped
    38860: {"home": ((21155,), (None,))},                                      # "Washington Redskins" -> dropped
    50020: {"home": ((27438,), (27440,)), "visitor": ((27438,), (27440,))},  # "Let's go Skins, I'll play some D!" ->
}                                                                              # "Let's get some penetration, come on, they're running all over you!"
#: the stadium and storyline keys, for one removed context: key -> (context, streams after the edit, either side)
OTHERS = {
    9453: (1, (17429,)),          # -> "visiting us for the game."
    38506: (1, (19869,)),         # -> "over in the stadium we had"
    38550: (4, (20264,)),         # "Erikson Stadium." -> "the stadium"
    38502: (20, (19734,)),        # "On the east side of the bay in Oakland" -> "in the big city we had"
    38800: (26, (None,)),         # "... the beautiful new stadium ..." -> dropped
    38803: (3, (None,)),          # the Bills' "wedding party" blurb -> dropped
    13850: (0, (None,)),          # the 2004 head-coach intro -> dropped
    9455: (0, (None,)),           # "And now, your 2004 <club>!" -> dropped (999 is gone too)
}


def retail_facts() -> dict:
    teams = {c: {"city": s.RETAIL_PLACES.get(c, "Somewhere"), "nickname": s.RETAIL_NICKNAMES.get(c, "Team"),
                 "coach": s.RETAIL_COACHES[c]} for c in s.TEAMS_2004}
    rows = {n: name for n, name in s.RETAIL_ROWS.items()}
    return {"rows": rows, "teams": teams}


def modern_facts(season_2026: bool = True) -> dict:
    """The standard 2026 disc: every row renamed, every coach changed, the relocations and Washington's new name."""
    facts = retail_facts()
    facts["season_2026"] = season_2026
    facts["rows"] = {n: f"Renamed {n}" for n in s.RETAIL_ROWS}
    for c, team in facts["teams"].items():
        team["coach"] = f"Coach {c}"
    facts["teams"][20]["city"] = "Las Vegas"
    facts["teams"][23]["city"] = "Los Angeles"
    facts["teams"][24]["city"] = "Los Angeles"
    facts["teams"][29]["nickname"] = "Commanders"
    return facts


class Table(unittest.TestCase):
    def test_every_rule_context_is_in_its_retail_lists(self):
        for key, rule in s.RULES.items():
            values = set()
            for index in s._LIST_KEYS[key]:
                values |= set(s.retail_values(index))
            self.assertEqual(sorted(set(rule) - values), [], key)
            if key != 9455:                                               # only 9455 must drop its generic
                self.assertNotIn(999, rule)
        self.assertEqual(s.RULES[38506], s.RULES[38550])                  # one shared list
        self.assertEqual(sorted(s.RULES[13850]), sorted(s.TEAMS_2004))
        self.assertEqual(set(s.RULES) | {14039}, set(s.HANDLERS))          # every rule key has a modelled handler
        self.assertEqual(set(s.RULES), set(s._LIST_KEYS))

    def test_review_coverage(self):
        """Review S3 / N3 / N4: Ericsson Stadium, the Bills' blurb, the dated lines; Houston's line stays."""
        self.assertEqual((s.RULES[38506][4], s.RULES[38550][4]), (s.A, s.A))        # "Erikson Stadium."
        self.assertEqual(s.RULES[38803][3], s.C)                                    # "problems even joining ..."
        self.assertEqual(s.RULES[38803][9], s.C)                                    # "finally ... turn the corner"
        self.assertEqual(s.RULES[38800][26], s.S)                                   # "the beautiful new stadium"
        for key in (38506, 38550, 38800):
            self.assertEqual(s.RULES[key][29], s.S, key)                            # "Raljon, Maryland"
        self.assertNotIn(37, s.RULES[38800])                                        # Houston, still true
        self.assertEqual(set(s.RULES[9455].values()), {s.S})                        # the 2026 season, not the coaches

    def test_washington_keeps_its_correct_calls(self):
        """No PA 'Washington' key is touched; the recaps and the franchise news stay (review M1)."""
        for key in (9003, 9012, 9015, 9017, 9018, 9051, 9213, 9252, 9333, 9335, 9336, 9400, 38502):
            self.assertNotIn(29, s.RULES.get(key, {}), key)
        for key in (9454, 38507, 38540, 38541, 38503, 38539, 38583, 38585):
            self.assertNotIn(key, s.RULES)                                # LATER
        for key in (38996, 38997, 38998, 38999, 39360, 39361, 39362, 39363, 53051, 53052,   # list 5602: recaps
                    51010, 51112, 51155, 51161):                                           # list 11166: news
            self.assertNotIn(key, s.RULES)                                # "the visitors" would be a false statement
        self.assertFalse({5602, 11166} & set(s.RETAIL_LISTS))
        shared = (9405, 9413, 9424, 9425, 9426, 9474, 9475, 9476, 38851, 38852, 38859, 38860, 38247, 38248, 38853,
                  38854)
        for key in shared:                                                # shared lists, all "Redskins" lines
            self.assertEqual(s.RULES[key], {29: s.N}, key)

    def test_decisions_follow_the_disc(self):
        retail = s.decide(retail_facts())
        self.assertEqual({k: sorted(v) for k, v in retail.items()},
                         {9453: [2, 4, 16, 21, 22, 25], 38506: [4, 25], 38550: [4, 25]})      # only 'always'
        modern = s.decide(modern_facts())
        self.assertEqual(sorted(modern[13850]), sorted(s.TEAMS_2004))
        self.assertEqual(sorted(modern[38502]), [20, 23, 24])
        for key in (512, 1201, 9414, 9427, 9444, 9456, 9467, 9468, 50020, 9424, 38859, 38247, 38854):
            self.assertEqual(sorted(modern[key]), [29])
        self.assertIn(29, modern[38800])                                  # "Raljon, Maryland" (review N4)
        self.assertNotIn(20, modern[38803])                               # the Raiders' blurb names no city: kept
        no_season = s.decide(modern_facts(season_2026=False))
        self.assertNotIn(9455, no_season)
        self.assertNotIn(29, no_season[38800])
        self.assertEqual(sorted(s.decide({**retail_facts(), "season_2026": True})[9455]), sorted(s.RULES[9455]))

    def test_renames_ignore_spaces_and_case(self):
        """Review N8: a normalised display name is not a rename."""
        facts = retail_facts()
        facts["rows"][23] = "Edward Jones Dome"                           # retail "Edward Jones Dome "
        facts["rows"][24] = "Qualcomm  Stadium"                           # retail "QUALCOMM Stadium"
        self.assertEqual((s.RULES[9453][23], s.RULES[9453][24]), (s.R, s.R))
        self.assertNotIn(23, s.decide(facts)[9453])
        self.assertNotIn(24, s.decide(facts)[9453])
        facts["rows"][23] = "The Dome at America's Center"
        self.assertIn(23, s.decide(facts)[9453])

    def test_the_2004_team_intro_is_skipped_for_real_clubs_only(self):
        modern = s.decide(modern_facts())[9455]
        self.assertTrue(set(s.TEAMS_2004) <= set(modern))
        self.assertIn(999, modern)                                         # else they would fall back to "created team"
        self.assertFalse({c for c in modern if 100 <= c <= 168})           # the dated classic teams keep their intro
        self.assertNotIn(9455, s.decide(retail_facts()))
        self.assertNotIn(9455, s.decide(modern_facts(season_2026=False)))  # the coaches alone are not the signal

    def test_list_state(self):
        index = 2302
        retail = s.retail_values(index)
        self.assertEqual(s.list_state(index, retail), "retail")
        applied = tuple(s.SKIP if v in (1, 3) else v for v in retail)
        self.assertEqual(s.list_state(index, applied), "applied")
        foreign = tuple(s.SKIP if v == 9 else v for v in retail)          # Ford Field is not a rule context
        self.assertEqual(s.list_state(index, foreign), "foreign")


class BuildWiring(unittest.TestCase):
    def test_step_runs_after_the_welcome_on_every_disc_build(self):
        source = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        call = [i for i, line in enumerate(lines) if '_optional(receipt, target, progress, "stale_speech")' in line]
        welcome = [i for i, line in enumerate(lines) if '_optional(receipt, target, progress, "stadium_welcome")' in line]
        self.assertEqual((len(call), len(welcome)), (1, 1))
        self.assertLess(welcome[0], call[0])
        gate = max(i for i in range(call[0]) if re.match(r"    if \S", lines[i]))
        self.assertEqual(lines[gate].strip(), "if tt.is_disc_image(target):")
        self.assertIn("stale_speech", mod_build.OPTIONAL_STEPS)
        self.assertIn("stale_speech", build_steps.STEP_LABELS)
        self.assertTrue(build_steps.KEPT["stale_speech"].startswith("Your "))

    def test_user_recordings_and_final_checks(self):
        """Review S2 and S5: the three booth steps get the user's own lines streams and the season, and each is
        checked on the finished disc after the final archive pass."""
        plan = mod_build.BuildPlan(source="in.iso", target="out.iso", commentary=[
            mod_build.CommentarySwap("lines:1479", "a.wav"), mod_build.CommentarySwap("lines:18047", "b.wav"),
            mod_build.CommentarySwap("players:1479", "c.wav")])
        self.assertEqual(mod_build._user_lines_streams(plan), frozenset({1479, 18047}))
        self.assertEqual(mod_build._user_lines_streams(mod_build.BuildPlan(source="a", target="b")), frozenset())
        source = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        for name in ("booth", "welcome", "stale"):
            call = re.search(rf"{name}_receipt = {name}\.apply_to_image\(target,(.*?)progress=", source, re.S)
            self.assertIsNotNone(call, name)
            self.assertIn("keep_streams=_user_lines_streams(plan)", call.group(1), name)
        self.assertIn("season_2026=bool(plan.season_2026)", re.search(
            r"stale_receipt = stale\.apply_to_image\(target,(.*?)progress=", source, re.S).group(1))
        compact = source.index("compacted = _compact_build_disc(target")
        for message in ("the Super Bowl booth lines did not survive the final passes",
                        "the pregame welcome for renamed stadiums did not survive the final passes",
                        "the stale team and stadium booth lines did not survive the final passes"):
            self.assertGreater(source.index(message), compact, message)


@unittest.skipUnless(HAVE_RETAIL, "needs the user-owned USA disc folder")
class Retail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_position_recode import OuterImage
        with OuterImage(RETAIL) as archive:
            cls.outer3 = archive.read_entry(w.SPCI_OUTER_INDEX)
        at = w.find_spci(cls.outer3)
        cls.at = at
        cls.body = cls.outer3[at + 0x20:at + 0x20 + w.SPCI_STORED]

    def test_handler_kinds_match_the_executable(self):
        """Every modelled key's row in the handler table at 0x4FC850 names a handler of its kind; 9444 has none; the
        modelled functions are the retail bytes."""
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(RETAIL_XBE.read_bytes())
        for (address, size), digest in MODELLED.items():
            self.assertEqual(hashlib.sha256(image.read(address, size)).hexdigest(), digest, hex(address))
        raw = image.read(0x4FC850, 0x4FD3AC - 0x4FC850)
        rows = [struct.unpack_from("<III", raw, i) for i in range(0, len(raw) - 11, 12)]
        for key, kind in s.HANDLERS.items():
            handlers = [h for lo, hi, h in rows if lo <= key <= hi]
            if kind == s.CALLER:
                self.assertEqual(handlers, [], key)
            else:
                self.assertEqual(len(handlers), 1, key)
                self.assertIn(handlers[0], s.HANDLER_ADDRESSES[kind], key)

    def test_what_washington_hears(self):
        """Review S1: the line each Washington key plays after the edit, from the handler and resolver model."""
        once, receipt = s.patch_body(self.body, s.decide(modern_facts()))
        self.assertEqual({int(k) for k in receipt["now_plays"]} >= set(WASHINGTON), True)
        for key, by_side in WASHINGTON.items():
            for side, (was, now) in by_side.items():
                self.assertEqual(tuple(s.spoken(self.body, key, 29, side)[1]), was, (key, side))
                self.assertEqual(tuple(s.spoken(once, key, 29, side)[1]), now, (key, side))
            self.assertEqual(set(s.sides(key)), set(by_side), key)
            if key != 38803:
                self.assertEqual({k: tuple(v) for k, v in receipt["now_plays"][str(key)].items() if k in by_side},
                                 {side: now for side, (_was, now) in by_side.items()}, key)
        self.assertIsNone(s.spoken(once, 9444, 29, "home"))                          # review N7: untraced
        self.assertIn("untraced", receipt["now_plays"]["9444"])
        for key, (ctx, now) in OTHERS.items():
            for side in s.sides(key):
                self.assertEqual(tuple(s.spoken(once, key, ctx, side)[1]), now, (key, side))
        # a club the edit leaves alone still hears its own line
        self.assertEqual(s.spoken(once, 1201, 18, "home"), s.spoken(self.body, 1201, 18, "home"))

    def test_the_users_own_recordings_stay_reachable(self):
        """Review S2: a (list, context) whose recording the user replaced keeps its value."""
        decisions = s.decide(modern_facts())
        first = s.first_streams(self.body)
        mine = s.stream_of(first[9424], 9424, 0, 29)                              # list 1234 (shared by 9425/9426)
        self.assertEqual(mine, 14532)
        once, receipt = s.patch_body(self.body, decisions, keep_streams={mine})
        self.assertEqual(receipt["kept_for_user_recordings"],
                         [{"key": k, "list": 1234, "context": 29, "streams": [14532]} for k in (9424, 9425, 9426)])
        _by_key, _users, lists = s.context_lists(once)
        self.assertIn(29, s.list_values(once, lists, 1234))
        self.assertNotIn(29, s.list_values(once, lists, 1325))                     # 9424's other speaker list: edited
        # the first speaker says the user's recording; the second one's own Washington line is gone, so its 999
        # ("Touchdown!") comes before the first speaker's list in the resolver's order
        self.assertEqual(s.spoken(once, 9424, 29, "home")[1], [14532, 14639])
        full, _ = s.patch_body(self.body, decisions)
        self.assertEqual(sum(1 for a, b in zip(once, full) if a != b), 2)
        welcome_stream = w.stream_of(18)
        self.assertEqual(welcome_stream, s.first_streams(self.body)[w.KEY] + w.RETAIL_VALUES.index(18))

    def test_pinned_lists_and_ownership(self):
        plan = s.plan_lists(self.body)
        self.assertEqual(sorted(plan), sorted({i for v in s._LIST_KEYS.values() for i in v}))
        for index, values in plan.items():
            self.assertEqual(values, s.retail_values(index))

    def test_patch_is_idempotent_and_touches_only_rule_contexts(self):
        decisions = s.decide(modern_facts())
        once, receipt = s.patch_body(self.body, decisions)
        self.assertEqual(receipt["changed_bytes"], 364)
        self.assertEqual(s.patch_body(self.body, s.decide(modern_facts(season_2026=False)))[1]["changed_bytes"], 272)
        self.assertEqual(s.patch_body(self.body, s.decide(retail_facts()))[1]["changed_bytes"], 16)
        by_key, _users, lists = s.context_lists(once)
        for index in s.plan_lists(once):
            touched = any(c in s.retail_values(index) for key, ctxs in decisions.items()
                          if index in s._LIST_KEYS[key] for c in ctxs)
            self.assertEqual(s.list_state(index, s.list_values(once, lists, index)),
                             "applied" if touched else "retail", index)   # 9414's first-variant list has no 29
        changed = [i for i, (a, b) in enumerate(zip(self.body, once)) if a != b]
        self.assertTrue(all(once[i] == 0xFF for i in changed))
        twice, receipt = s.patch_body(once, decisions)
        self.assertEqual(twice, once)

    def test_refuses_a_foreign_list(self):
        _by_key, _users, lists = s.context_lists(self.body)
        out = bytearray(self.body)
        at = lists + 2 * 2302 + 2 + 2 * s.retail_values(2302).index(9)  # Ford Field, not a rule context
        struct.pack_into("<H", out, at, 77)
        with self.assertRaises(s.StaleSpeechError):
            s.plan_lists(bytes(out))

    def test_round_trip_on_a_synthetic_disc(self):
        from nfl2k5_xiso_fixture import SyntheticXiso
        with tempfile.TemporaryDirectory() as tmp:
            entries = [(0, b"\x00" * 16), (1, b"\x01" * 16), (2, b"\x02" * 16), (3, self.outer3), (4, b"\x04" * 16)]
            size = 0x800 * 8 + len(self.outer3)
            size += -size % 0x800
            image = SyntheticXiso(Path(tmp), entries, pack_sizes=(size,), pack_sectors=(64,))
            before = image.path.read_bytes()
            with mock.patch.object(s, "disc_facts", return_value=modern_facts(season_2026=False)):
                self.assertEqual(s.pending_bytes(image.path, season_2026=True), 364)      # failing first
                receipt = s.apply_to_image(image.path, season_2026=True)
                self.assertEqual((receipt["state"], receipt["changed_bytes"]), ("applied", 364))
                after = image.path.read_bytes()
                self.assertEqual(sum(1 for x, y in zip(before, after) if x != y), 364)
                self.assertEqual(s.apply_to_image(image.path, season_2026=True)["changed_bytes"], 0)
                self.assertEqual(s.pending_bytes(image.path, season_2026=True), 0)
            with mock.patch.object(s, "disc_facts", side_effect=ValueError("no roster")):
                self.assertEqual(s.apply_to_image(image.path)["state"], "skipped")
            self.assertEqual(image.path.read_bytes(), after)


if __name__ == "__main__":
    unittest.main()

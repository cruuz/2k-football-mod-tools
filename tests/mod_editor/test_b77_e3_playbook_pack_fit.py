"""E3: a customized SOFTDRINK build must not die minutes in on playbook packs that no longer fit.

The reported "not a canonical build recipe" failure was fixed in 76.5 (job d1). Replaying the reported build
(the published SOFTDRINK v0.4 sources, 114 selected options, a repacked image) on the 76.5 tree showed the next
refusal behind it: d2b's deep-back flat repair changed the compiled complete offenses, so the 32 custom defense
packs, which record the SHA-256 of the offense-composed book they were authored on, no longer matched
("Custom defense source changed"), minutes into the preflight, or after the whole project build.

* :class:`CanaryTests`, :class:`RefusalWordsTests` and :class:`RebaseLogicTests` need no game data.
* :class:`RetailPackFitTests` is gated on the retail XISO (read only) and is the one that fails on a stale
  ``data/playbooks`` set: it compiles real offense + defense pairs.
"""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77"), str(Path(__file__).parent)]

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as pk  # noqa: E402
import e3_defense_pack_rebase as rebase_tool  # noqa: E402
from test_mod_build_performance import synthetic_disc  # noqa: E402

ISO = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
EXTRACT = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)")
os.environ.setdefault("NFL2K5_SCORING_XBE", str(EXTRACT))
PLAYBOOKS = ROOT / "data" / "playbooks"


def offense(team: str) -> Path:
    return PLAYBOOKS / f"softdrink_{team.lower()}_modern.2k5book"


def defense(team: str) -> Path:
    return PLAYBOOKS / f"softdrink_{team.lower()}_defense.2k5book"


class CanaryTests(unittest.TestCase):
    def test_a_stale_defense_pack_is_named_with_its_cause_and_fix(self):
        stale = pk.PlaybookPackError("Custom defense source changed ('NFL 2K28 ARZ Defense': ARZ's book is aaaa)")
        with mock.patch.object(mod_build, "_preview_play_intents", side_effect=stale) as preview:
            with self.assertRaises(ValueError) as caught:
                mod_build.check_playbook_pack_fit(
                    Path("source.iso"), [offense("ARZ"), defense("ARZ"), offense("KC"), defense("KC")])
        text = str(caught.exception)
        for needle in ("ARZ's defense pack", "NFL 2K28 ARZ Defense", "older Studio", "SOFTDRINK pack released with this Studio",
                       "Nothing was written", "Custom defense source changed"):
            self.assertIn(needle, text)
        preview.assert_called_once_with(Path("source.iso"), [offense("ARZ"), defense("ARZ")], progress=None)

    def test_other_refusals_keep_their_own_words(self):
        other = pk.PlaybookPackError("Complete offense source fingerprint/team changed; regenerate and review")
        with mock.patch.object(mod_build, "_preview_play_intents", side_effect=other):
            with self.assertRaisesRegex(ValueError, "^Complete offense source fingerprint/team changed") as caught:
                mod_build.check_playbook_pack_fit(Path("source.iso"), [offense("KC"), defense("KC")])
        self.assertNotIn("older Studio", str(caught.exception))

    def test_a_fitting_pair_passes_and_says_which_team_it_checked(self):
        seen = []
        with mock.patch.object(mod_build, "_preview_play_intents", return_value=[]) as preview:
            team = mod_build.check_playbook_pack_fit(
                Path("source.iso"), [defense("DAL"), offense("DAL"), offense("KC")], lambda *row: seen.append(row))
        self.assertEqual(team, "DAL")
        self.assertEqual(seen, [("Checking that DAL's defense pack fits its offense book", 0, 0)])
        preview.assert_called_once()
        self.assertTrue(callable(preview.call_args.kwargs["progress"]), "the pack installer's team messages must reach the status line")

    def test_a_defense_without_its_offense_is_skipped_and_nothing_is_composed(self):
        with mock.patch.object(mod_build, "_preview_play_intents", side_effect=AssertionError("composed")):
            self.assertIsNone(mod_build.check_playbook_pack_fit(Path("s.iso"), [defense("ARZ"), offense("KC")]))
            self.assertIsNone(mod_build.check_playbook_pack_fit(Path("s.iso"), [offense("ARZ")]))
            self.assertIsNone(mod_build.check_playbook_pack_fit(Path("s.iso"), []))

    def test_option_and_preset_packs_are_never_the_canary(self):
        seed = PLAYBOOKS / "modern_gun_core.2k5book"          # an option pack, authored on a stock seed
        preset = PLAYBOOKS / "softdrink_modern_defense.2k5book"  # a built-in recipe, regenerated per book
        with mock.patch.object(mod_build, "_preview_play_intents", side_effect=AssertionError("composed")):
            self.assertIsNone(mod_build.check_playbook_pack_fit(Path("s.iso"), [seed, preset, offense("ATL")]))

    def test_build_checks_the_packs_before_any_of_the_slow_source_checks(self):
        class Fired(ValueError):
            pass
        with tempfile.TemporaryDirectory() as td:
            source, target = Path(td) / "source.iso", Path(td) / "out.iso"
            synthetic_disc(source)
            plan = mod_build.BuildPlan(str(source), str(target),
                                       playbook_packs=(str(offense("ARZ")), str(defense("ARZ"))))
            with mock.patch.object(mod_build, "check_playbook_pack_fit", side_effect=Fired("canary")) as canary, \
                    mock.patch.object(mod_build, "_preview_play_intents", side_effect=AssertionError("full preview ran")), \
                    mock.patch.object(mod_build, "_xbe_bytes", side_effect=AssertionError("slow source check ran")):
                with self.assertRaisesRegex(Fired, "canary"):
                    mod_build.preflight_plan(plan)
            self.assertEqual(canary.call_args.args[:2], (source, plan.playbook_packs))


class RefusalWordsTests(unittest.TestCase):
    BODY = bytes(pk.BODY_SIZE)

    def test_same_team_mismatch_names_both_books_and_the_cause(self):
        pack = pk.load_pack(defense("ARZ"))
        with self.assertRaises(pk.PlaybookPackError) as caught:
            pk.retarget_defense_pack(pack, "ARZ", None, self.BODY)
        text = str(caught.exception)
        self.assertTrue(text.startswith("Custom defense source changed"))
        for needle in (repr(pack.book.name), pack.base.book_fingerprint[:12], pk.book_fingerprint(self.BODY)[:12],
                       "complete offense compiled by a different Studio release", "automatic slot guesses are refused"):
            self.assertIn(needle, text)

    def test_another_team_is_still_refused_and_says_so(self):
        with self.assertRaisesRegex(pk.PlaybookPackError, "authored for ARZ, not KC"):
            pk.retarget_defense_pack(pk.load_pack(defense("ARZ")), "KC", None, self.BODY)

    def test_the_exact_book_still_loads_unchanged(self):
        pack = replace(pk.load_pack(defense("ARZ")),
                       base=replace(pk.load_pack(defense("ARZ")).base, book_fingerprint=pk.book_fingerprint(self.BODY)))
        self.assertEqual(pk.retarget_defense_pack(pack, "ARZ", None, self.BODY), (pack, ()))


class RebaseLogicTests(unittest.TestCase):
    """What the re-stamp tool checks before it touches one base field (the real checks need a book)."""

    def setUp(self):
        self.pack = pk.load_pack(defense("ARZ"))
        formations = ["x"] * self.pack.base.donor_formation_count
        plays = ["x"] * self.pack.base.donor_play_count
        for f in self.pack.formations:
            formations[f.replace_index] = f.replace_name
            formations[f.donor.index] = f.donor.name
        for p in self.pack.plays:
            plays[p.replace_index] = p.replace_name
        self.book = SimpleNamespace(formations=[SimpleNamespace(name=n) for n in formations],
                                    plays=[SimpleNamespace(name=n) for n in plays], node_count=4321)
        self.body = bytes(pk.BODY_SIZE)
        patcher = mock.patch.object(pk, "validate_defense_pack_play")
        self.validate = patcher.start()
        self.addCleanup(patcher.stop)

    def test_only_the_base_fingerprint_and_node_count_change(self):
        rebased = rebase_tool.rebase(self.pack, self.book, self.body)
        self.assertEqual(rebased.base.book_fingerprint, pk.book_fingerprint(self.body))
        self.assertEqual(rebased.base.donor_node_count, 4321)
        self.assertEqual(replace(rebased, base=self.pack.base), self.pack)
        self.assertEqual(self.validate.call_count, len(self.pack.plays))
        self.assertEqual(rebased.dumps().count("\n"), self.pack.dumps().count("\n"))

    def test_a_book_with_other_counts_is_refused(self):
        self.book.plays.append(SimpleNamespace(name="extra"))
        with self.assertRaisesRegex(ValueError, "formations and 271 plays"):
            rebase_tool.rebase(self.pack, self.book, self.body)

    def test_a_moved_or_renamed_formation_is_refused(self):
        f = self.pack.formations[0]
        self.book.formations[f.replace_index] = SimpleNamespace(name="renamed by another patch")
        with self.assertRaisesRegex(ValueError, "no longer replaces a formation named"):
            rebase_tool.rebase(self.pack, self.book, self.body)

    def test_a_play_another_pack_already_replaced_is_refused(self):
        p = self.pack.plays[3]
        self.book.plays[p.replace_index] = SimpleNamespace(name="a pack's custom name")
        with self.assertRaisesRegex(ValueError, f"play {p.id} no longer replaces a defense play named"):
            rebase_tool.rebase(self.pack, self.book, self.body)

    def test_a_donor_whose_shape_changed_is_refused(self):
        self.validate.side_effect = pk.PlaybookPackError("Defense donor signature changed")
        with self.assertRaisesRegex(ValueError, "play d0: Defense donor signature changed"):
            rebase_tool.rebase(self.pack, self.book, self.body)

    def test_a_pack_with_an_appended_play_is_refused(self):
        appended = replace(self.pack.plays[0], replace_index=None)
        with self.assertRaisesRegex(ValueError, "no longer replaces a defense play"):
            rebase_tool.rebase(replace(self.pack, plays=(appended, *self.pack.plays[1:])), self.book, self.body)


@unittest.skipUnless(ISO.is_file() and (EXTRACT / "vc_53450030" / "0").is_file(), "retail XISO / extracted archive missing")
class RetailPackFitTests(unittest.TestCase):
    TEAMS = ("ARZ", "KC", "DAL")

    def test_every_checked_defense_pack_installs_on_its_own_offense_book(self):
        for team in self.TEAMS:
            with self.subTest(team=team):
                heard = []
                pairs = mod_build._preview_play_intents(ISO, [offense(team), defense(team)],
                                                        progress=lambda *row: heard.append(row))
                self.assertEqual(len(pairs), 2)
                # one status message per pack installed, so a minutes-long preview never looks hung
                self.assertEqual([(m, a, b) for m, a, b in heard],
                                 [(f"Installing \u201c{pk.load_pack(path).book.name}\u201d into {team}", 0, 0)
                                  for path in (offense(team), defense(team))])

    def test_the_canary_passes_on_the_repo_packs(self):
        self.assertEqual(mod_build.check_playbook_pack_fit(ISO, [offense("ARZ"), defense("ARZ")]), "ARZ")

    def test_a_pack_authored_on_the_previous_compile_is_refused_in_seconds_with_a_plain_message(self):
        # 604b2b87... is the book fingerprint the published v0.2-v0.4 ARZ defense pack records
        pack = pk.load_pack(defense("ARZ"))
        old = replace(pack, base=replace(pack.base, book_fingerprint="604b2b8703b074b322793243e4bdc0eff222ed820dc536801f865cd10113de98",
                                         donor_node_count=1410))
        with tempfile.TemporaryDirectory() as td:
            path = pk.save_pack(old, Path(td) / "softdrink_arz_defense.2k5book")
            with self.assertRaisesRegex(ValueError, "do not fit each other.*older Studio.*Nothing was written"):
                mod_build.check_playbook_pack_fit(ISO, [offense("ARZ"), path])

    def test_the_rebase_tool_finds_the_checked_teams_current(self):
        for team in ("ARZ", "KC"):
            with self.subTest(team=team):
                row = rebase_tool.check_team((str(ISO), team, str(offense(team)), str(defense(team)), False))
                self.assertEqual(row["status"], "current", row)


if __name__ == "__main__":
    unittest.main()

"""``python -m mod_editor.games lane``: one lane step, alone, with no window.

Driven on the scaffolded example lane's own synthetic slot file, in a scratch
repository root: no game data, nothing written into this tree.  What is proved
is what the studio depends on -- the four steps chain through the JSON they
write, a verifier that fails exits 1, and every refusal is the lane's own
sentence on stderr instead of a traceback.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
for _candidate in (ROOT, ROOT / "tests" / "mod_editor"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import mod_editor.games as games  # noqa: E402
from mod_editor.games import contract, lane_cli, scaffold  # noqa: E402
from games_fakes import cli_command  # noqa: E402

GAME_ID = "demo_ps2"
LANE_ID = "example.slots"


class LaneStepTests(unittest.TestCase):
    """The four steps, in the order the studio runs them."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(tempfile.mkdtemp(prefix="lane-cli-repo-")).resolve()
        scaffold.scaffold(GAME_ID, "Demo Game (PlayStation 2)", "PlayStation 2", "SLUS-00000",
                          console="PS2", game="Demo", year="1", repo_root=cls.repo)
        cls.games_root = cls.repo / "mod_editor" / "games"
        cls.work = cls.repo / "work"
        cls.work.mkdir()
        game = games.load(GAME_ID, cls.games_root)
        cls.lane = game.lane(LANE_ID)
        cls.source = Path(cls.lane.synthetic_source(cls.work))
        recipe = cls.lane.compose_recipe(cls.lane.conformance_edits(cls.lane.build_catalogue(cls.source)))
        cls.recipe = cls.work / "recipe.json"
        cls.recipe.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8", newline="\n")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.repo, ignore_errors=True)

    def setUp(self) -> None:
        self.room = Path(tempfile.mkdtemp(prefix="lane-cli-", dir=self.work)).resolve()
        self.addCleanup(shutil.rmtree, self.room, True)

    def _run(self, *arguments: str) -> tuple[int, str]:
        lines: list[str] = []
        code, verdict = lane_cli.run(
            GAME_ID, LANE_ID, arguments[0],
            games_root=self.games_root,
            progress=lines.append,
            **dict(zip(arguments[1::2], (Path(value) for value in arguments[2::2]))),
        )
        self.assertTrue(lines, "every step reports progress before its verdict")
        return code, verdict

    def test_catalogue_plan_build_verify_chain_through_their_json(self) -> None:
        catalogue = self.room / "catalogue.json"
        code, verdict = self._run("catalogue", "source", str(self.source), "out", str(catalogue))
        self.assertEqual(code, 0)
        self.assertIn("LANE_CATALOGUE ok", verdict)
        self.assertIn("targets=4", verdict)
        self.assertIn("page=menus", verdict, "the verdict says which studio page hosts the lane")
        document = json.loads(catalogue.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], lane_cli.CATALOGUE_SCHEMA)
        self.assertEqual(document["game"], GAME_ID)
        reread = lane_cli.catalogue_from_json(document)
        self.assertEqual([target.key for target in reread.targets],
                         [target.key for target in self.lane.build_catalogue(self.source).targets])

        plan = self.room / "plan.json"
        code, verdict = self._run("plan", "source", str(self.source), "recipe", str(self.recipe),
                                  "catalogue", str(catalogue), "out", str(plan))
        self.assertEqual(code, 0)
        self.assertIn("LANE_PLAN ok", verdict)
        self.assertIn("declared_bytes=32", verdict)
        self.assertEqual(json.loads(plan.read_text(encoding="utf-8"))["target_keys"], ["slot:1"])

        destination = self.room / "built.slot"
        receipt = self.room / "receipt.json"
        code, verdict = self._run("build", "source", str(self.source), "destination", str(destination),
                                  "recipe", str(self.recipe), "catalogue", str(catalogue),
                                  "work_dir", str(self.room), "receipt", str(receipt))
        self.assertEqual(code, 0)
        self.assertIn("LANE_BUILD ok", verdict)
        self.assertIn("ranges=1", verdict)
        self.assertTrue(destination.is_file())
        self.assertEqual(self.source.read_bytes(), Path(self.lane.synthetic_source(self.room)).read_bytes(),
                         "the source is never written")

        verdict_path = self.room / "verdict.json"
        code, verdict = self._run("verify", "source", str(self.source), "destination", str(destination),
                                  "receipt", str(receipt), "out", str(verdict_path))
        self.assertEqual(code, 0)
        self.assertIn("LANE_VERIFY pass", verdict)
        self.assertTrue(json.loads(verdict_path.read_text(encoding="utf-8"))["passed"])

    def test_verify_of_a_tampered_build_fails_with_code_one(self) -> None:
        catalogue = self.room / "catalogue.json"
        self._run("catalogue", "source", str(self.source), "out", str(catalogue))
        destination = self.room / "built.slot"
        receipt = self.room / "receipt.json"
        self._run("build", "source", str(self.source), "destination", str(destination),
                  "recipe", str(self.recipe), "catalogue", str(catalogue), "receipt", str(receipt))
        tampered = bytearray(destination.read_bytes())
        tampered[-1] ^= 0xFF
        (self.room / "tampered.slot").write_bytes(bytes(tampered))
        code, verdict = self._run("verify", "source", str(self.source),
                                  "destination", str(self.room / "tampered.slot"),
                                  "receipt", str(receipt), "out", str(self.room / "verdict.json"))
        self.assertEqual(code, 1)
        self.assertIn("LANE_VERIFY FAIL", verdict)

    def test_every_failure_is_one_refusal_sentence(self) -> None:
        with self.assertRaisesRegex(contract.Refusal, "has no lane 'no.such.lane'"):
            lane_cli.run(GAME_ID, "no.such.lane", "catalogue", source=self.source,
                         out=self.room / "x.json", games_root=self.games_root)
        with self.assertRaisesRegex(contract.Refusal, "No hosted game"):
            lane_cli.run("absent_game", LANE_ID, "catalogue", source=self.source,
                         out=self.room / "x.json", games_root=self.games_root)
        (self.room / "not.json").write_text("{oops", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(contract.Refusal, "not valid JSON"):
            lane_cli.run(GAME_ID, LANE_ID, "plan", source=self.source, recipe=self.room / "not.json",
                         catalogue=self.room / "not.json", out=self.room / "x.json",
                         games_root=self.games_root)
        stale = self.room / "stale.json"
        stale.write_text(json.dumps({"schema": "something/else"}) + "\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(contract.Refusal, "Rebuild it with"):
            lane_cli.run(GAME_ID, LANE_ID, "plan", source=self.source, recipe=self.recipe,
                         catalogue=stale, out=self.room / "x.json", games_root=self.games_root)

    def test_a_target_keeps_its_editor_fields_across_the_json(self) -> None:
        target = contract.Target(
            "slot:0", "Slot 0", budget="32 characters",
            fields=(contract.Field("text", "text", "Display text", help="32 characters",
                                   maximum=32, read_only=False),),
        )
        again = lane_cli.target_from_json(lane_cli.target_json(target))
        self.assertEqual(again, target)


class LaneCommandLineTests(unittest.TestCase):
    """The same steps as a child process: exit codes and one verdict line."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(tempfile.mkdtemp(prefix="lane-cli-child-")).resolve()
        scaffold.scaffold(GAME_ID, "Demo Game (PlayStation 2)", "PlayStation 2", "SLUS-00000",
                          console="PS2", game="Demo", year="1", repo_root=cls.repo)
        cls.games_root = cls.repo / "mod_editor" / "games"
        cls.work = cls.repo / "work"
        cls.work.mkdir()
        lane = games.load(GAME_ID, cls.games_root).lane(LANE_ID)
        cls.source = Path(lane.synthetic_source(cls.work))
        cls.recipe = cls.work / "recipe.json"
        cls.recipe.write_text(
            json.dumps(lane.compose_recipe(lane.conformance_edits(lane.build_catalogue(cls.source)))) + "\n",
            encoding="utf-8", newline="\n",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.repo, ignore_errors=True)

    def _cli(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            cli_command("--games-root", str(self.games_root), "lane", GAME_ID, LANE_ID, *arguments),
            cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        )

    def test_a_build_runs_end_to_end_in_a_child_process(self) -> None:
        room = Path(tempfile.mkdtemp(prefix="lane-child-", dir=self.work)).resolve()
        self.addCleanup(shutil.rmtree, room, True)
        catalogue = room / "catalogue.json"
        built = self._cli("catalogue", "--source", str(self.source), "--out", str(catalogue))
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        self.assertIn("LANE_CATALOGUE ok", built.stdout.splitlines()[-1])

        receipt = room / "receipt.json"
        completed = self._cli("build", "--source", str(self.source), "--destination", str(room / "out.slot"),
                              "--recipe", str(self.recipe), "--catalogue", str(catalogue),
                              "--work-dir", str(room), "--receipt", str(receipt))
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("LANE_BUILD ok", completed.stdout.splitlines()[-1])
        self.assertTrue((room / "out.slot").is_file())

        verified = self._cli("verify", "--source", str(self.source), "--destination", str(room / "out.slot"),
                             "--receipt", str(receipt), "--out", str(room / "verdict.json"))
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertIn("LANE_VERIFY pass", verified.stdout.splitlines()[-1])

    def test_a_refusal_is_a_sentence_and_never_a_traceback(self) -> None:
        room = Path(tempfile.mkdtemp(prefix="lane-child-refusal-", dir=self.work)).resolve()
        self.addCleanup(shutil.rmtree, room, True)
        completed = self._cli("catalogue", "--source", str(room / "absent.slot"), "--out", str(room / "c.json"))
        self.assertEqual(completed.returncode, 1)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertTrue(completed.stderr.startswith("error: "), completed.stderr)
        self.assertFalse((room / "c.json").exists(), "a refusal leaves no output behind")

    def test_an_unknown_step_is_refused_by_the_parser(self) -> None:
        completed = self._cli("teleport", "--source", str(self.source))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("catalogue", completed.stderr)


if __name__ == "__main__":
    unittest.main()

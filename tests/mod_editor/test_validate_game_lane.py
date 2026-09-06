"""One validator, parameterised, instead of one copied script per lane.

Fifteen lane validators across two game modules ran the same four steps and
differed in two: which sources they compiled, and which sentence they echoed.
``tools/validate_game_lane.py`` holds the steps; each game's
``validators.json`` holds what differs; each ``validate_<game>_<lane>.sh``
is a wrapper that names the two.

These tests hold that arrangement together: every wrapper points at a lane the
manifest declares, every lane the manifest declares has a wrapper, every path a
manifest names exists, and the pass token stays derivable from the file name --
that last one is what lets a new game's validators be generated rather than
written.

No disc, no fixture, no retail file.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DRIVER = ROOT / "tools" / "validate_game_lane.py"
#: The games whose validators delegate to the driver.
MIGRATED = ("madden09_ps2", "ncaa09_ps2", "nfl2k5_ps2")

#: Shipped validators that still run ``python -m unittest`` and therefore still
#: exit 1 in a release stage.  Both belong to the Xbox NFL 2K5 lanes, whose
#: assertions have not been moved into their tools yet.  The list is asserted
#: to be exactly this, so a new offender fails and a fixed one has to be
#: removed here rather than quietly forgiven.
KNOWN_UNMIGRATED = (
    "tools/validate_nfl_all_texture_lane.sh",
    "tools/validate_nfl_coach_roster_name.sh",
)

sys.path.insert(0, str(ROOT / "tools"))
import validate_game_lane as driver  # noqa: E402


def manifests() -> dict:
    return {game: json.loads((ROOT / "mod_editor" / "games" / game / "validators.json")
                             .read_text(encoding="utf-8"))
            for game in MIGRATED}


class Manifests(unittest.TestCase):
    def test_every_declared_path_exists(self) -> None:
        for game, document in manifests().items():
            for lane, spec in document["lanes"].items():
                for relative in spec["compile"]:
                    with self.subTest(game=game, lane=lane, path=relative):
                        self.assertTrue((ROOT / relative).is_file(), relative)
                for entry in spec["selftest"]:
                    with self.subTest(game=game, lane=lane, selftest=entry):
                        if "script" in entry:
                            self.assertTrue((ROOT / entry["script"]).is_file(), entry)
                        else:
                            module = ROOT / (entry["module"].replace(".", "/") + ".py")
                            self.assertTrue(module.is_file(), entry)

    def test_the_manifest_says_which_game_it_is_in(self) -> None:
        for game, document in manifests().items():
            self.assertEqual(document["game_id"], game)
            self.assertEqual(document["schema"], driver.SCHEMA)

    def test_the_manifest_ships(self) -> None:
        allowlist = (ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8")
        self.assertIn("tools/validate_game_lane.py", allowlist.splitlines())
        for game in MIGRATED:
            self.assertIn(f"mod_editor/games/{game}/validators.json", allowlist.splitlines())


class Wrappers(unittest.TestCase):
    def wrappers(self, game: str, document: dict):
        """The wrappers of the lanes this game's manifest declares.

        NFL 2K5's other validators are standalone scripts that already run in a
        shipped tree, so they are not globbed in: a game may have both kinds
        while its module is being migrated lane by lane.
        """
        return [ROOT / f"tools/validate_{game}_{lane}.sh"
                for lane in sorted(document["lanes"])]

    def test_every_wrapper_names_a_lane_the_manifest_declares(self) -> None:
        for game, document in manifests().items():
            for path in self.wrappers(game, document):
                text = path.read_text(encoding="utf-8")
                match = re.search(r"--game (\S+) --lane (\S+)", text)
                with self.subTest(path=path.name):
                    self.assertIsNotNone(match, f"{path.name} does not call the driver")
                    self.assertEqual(match.group(1), game)
                    self.assertIn(match.group(2), document["lanes"])
                    self.assertEqual(path.stem, f"validate_{game}_{match.group(2)}",
                                     "the wrapper's name and its --lane disagree")

    def test_every_lane_has_both_wrappers(self) -> None:
        for game, document in manifests().items():
            for lane in document["lanes"]:
                with self.subTest(game=game, lane=lane):
                    self.assertTrue((ROOT / f"tools/validate_{game}_{lane}.sh").is_file())
                    self.assertTrue((ROOT / f"tools/validate_{game}_{lane}.bat").is_file())

    def test_no_wrapper_imports_a_test_framework(self) -> None:
        """tests/ is not shipped, so a validator that runs unittest cannot pass."""

        for game, document in manifests().items():
            for lane in document["lanes"]:
                for suffix in (".sh", ".bat"):
                    path = ROOT / f"tools/validate_{game}_{lane}{suffix}"
                    with self.subTest(path=path.name):
                        self.assertNotIn("unittest", path.read_text(encoding="utf-8"))

    def test_no_validator_the_release_ships_runs_a_test_framework(self) -> None:
        """The rule, checked where it bites: every staged validator.

        Four validators ran ``python -m unittest`` against files under
        ``tests/``, which the release allowlist does not carry, so they passed
        in a checkout and exited 1 in a shipped tree.  This is the check that
        stops a fifth, and it reads the allowlist rather than a list kept here.
        """
        staged = [line.strip() for line
                  in (ROOT / "packaging/release-allowlist.txt")
                  .read_text(encoding="utf-8").splitlines()
                  if line.strip() and not line.strip().startswith("#")]
        validators = [name for name in staged
                      if "validate" in name and name.endswith((".sh", ".bat"))]
        self.assertGreater(len(validators), 20, "the allowlist ships no validators?")
        offenders = sorted(name for name in validators
                           if "unittest" in (ROOT / name).read_text(encoding="utf-8"))
        self.assertEqual(offenders, sorted(KNOWN_UNMIGRATED),
                         "a shipped validator gained a test-framework step, or one "
                         "of the known two lost it -- shrink KNOWN_UNMIGRATED")

    def test_the_bat_wrappers_keep_crlf(self) -> None:
        for game in MIGRATED:
            for path in sorted(ROOT.glob(f"tools/validate_{game}_*.bat")):
                with self.subTest(path=path.name):
                    raw = path.read_bytes()
                    self.assertNotIn(b"\n", raw.replace(b"\r\n", b""),
                                     "a bare LF in a .bat cmd.exe has to read")

    def test_registry_rows_still_name_these_scripts(self) -> None:
        registry = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json")
                              .read_text(encoding="utf-8"))
        for row in registry["capabilities"]:
            if row["game"] in MIGRATED:
                command = row["validation_command"]
                with self.subTest(row=row["id"]):
                    self.assertTrue(command.startswith("bash "), command)
                    named = ROOT / command.split()[1]
                    self.assertTrue(named.is_file(), command)
                    # A row may name a module-local validator (NFL 2K5's code
                    # patches do); what it may not do is name a lane wrapper
                    # whose file is not there.
                    self.assertIn(named.suffix, (".sh", ".bat"), command)


class TokenDerivation(unittest.TestCase):
    def test_both_wrappers_name_the_token_they_promise(self) -> None:
        """A lane's own test suite reads the validator file and looks for its
        pass line; a wrapper that delegates still has to say which line it is."""

        for game, document in manifests().items():
            for lane in document["lanes"]:
                token = driver.pass_token(game, lane)
                for suffix in (".sh", ".bat"):
                    path = ROOT / f"tools/validate_{game}_{lane}{suffix}"
                    with self.subTest(game=game, lane=lane, suffix=suffix):
                        self.assertIn(token, path.read_text(encoding="utf-8"))

    def test_it_is_the_shape_every_other_validator_uses(self) -> None:
        self.assertEqual(driver.pass_token("madden09_ps2", "uniform_disc_art"),
                         "MADDEN09_PS2_UNIFORM_DISC_ART_VALIDATION_PASS")


class Refusals(unittest.TestCase):
    def run_driver(self, *args: str):
        return subprocess.run([sys.executable, str(DRIVER), *args],
                              cwd=str(ROOT), capture_output=True, text=True, check=False)

    def test_an_unknown_lane_is_refused_by_name(self) -> None:
        result = self.run_driver("--game", "madden09_ps2", "--lane", "no_such_lane")
        self.assertEqual(result.returncode, 1)
        self.assertIn("has no lane validator called 'no_such_lane'", result.stderr)
        self.assertIn("uniform_art", result.stderr, "the refusal should name the lanes there are")

    def test_a_game_without_a_manifest_is_refused_with_the_fix(self) -> None:
        result = self.run_driver("--game", "no_such_game_ps2", "--lane", "text")
        self.assertEqual(result.returncode, 1)
        self.assertIn("has no lane-validator manifest", result.stderr)
        self.assertIn("validators.json", result.stderr)

    def test_naming_no_lane_is_refused(self) -> None:
        result = self.run_driver("--game", "madden09_ps2")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--all", result.stderr)

    def test_list_prints_every_lane_with_its_token(self) -> None:
        result = self.run_driver("--game", "ncaa09_ps2", "--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        lanes = [line.split("\t")[0] for line in result.stdout.strip().splitlines()]
        self.assertEqual(lanes, sorted(manifests()["ncaa09_ps2"]["lanes"]))
        self.assertIn("NCAA09_PS2_TEXTURES_VALIDATION_PASS", result.stdout)


class CompileStep(unittest.TestCase):
    def test_it_leaves_no_pycache_in_the_tree(self) -> None:
        """A shipped tree that gains files fails the release check."""

        target = ROOT / "mod_editor/games/_formats/mmap_art.py"
        cache = target.parent / "__pycache__"
        before = {path.name for path in cache.glob("*.pyc")} if cache.is_dir() else set()
        driver.compile_sources(["mod_editor/games/_formats/mmap_art.py"], ROOT)
        after = {path.name for path in cache.glob("*.pyc")} if cache.is_dir() else set()
        self.assertEqual(before, after)

    def test_a_missing_source_is_refused_with_the_fix(self) -> None:
        with self.assertRaises(driver.ValidatorError) as caught:
            driver.compile_sources(["mod_editor/games/madden09_ps2/not_a_file.py"], ROOT)
        self.assertIn("drop it from the lane's compile list", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)

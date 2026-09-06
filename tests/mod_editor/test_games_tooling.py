"""The game-module tooling: ``new`` scaffolds a conforming module; ``fragments`` keeps mirrors true.

Everything runs in a scratch repository root, so nothing is written into this
tree.  No game data.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import py_compile
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
from mod_editor.games import conformance, contract, fragments, registry_merge, scaffold  # noqa: E402
from games_fakes import cli_command  # noqa: E402

GAME_ID = "demo_ps2"


class ScaffoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(tempfile.mkdtemp(prefix="scaffold-repo-"))
        cls.written = scaffold.scaffold(GAME_ID, "Demo Game (PlayStation 2)", "PlayStation 2", "SLUS-00000",
                                        console="PS2", game="Demo", year="1", repo_root=cls.repo)
        cls.package = cls.repo / "mod_editor" / "games" / GAME_ID
        cls.games_root = cls.repo / "mod_editor" / "games"
        cls.report = games.discover(cls.games_root)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.repo, ignore_errors=True)

    def test_the_files_written_are_the_package_and_its_test(self) -> None:
        names = sorted(path.name for path in self.written if path.parent == self.package)
        self.assertEqual(names, sorted(scaffold.PACKAGE_FILES))
        self.assertIn(self.repo / "tests" / "mod_editor" / f"test_{GAME_ID}_module.py", self.written)
        for path in self.written:
            if path.suffix == ".py":
                py_compile.compile(str(path), doraise=True)
        bat = (self.package / "validate_example.bat").read_bytes()
        self.assertIn(b"\r\n", bat, ".bat files are CRLF in this repository")
        sh = (self.package / "validate_example.sh").read_bytes()
        self.assertNotIn(b"\r", sh)
        self.assertTrue(os.access(self.package / "validate_example.sh", os.X_OK))
        for path in self.written:
            if path.suffix != ".bat":
                self.assertNotIn(b"\r", path.read_bytes(), f"{path.name} must be LF")

    def test_the_module_is_discovered_and_conforms(self) -> None:
        self.assertEqual(self.report.game_ids, (GAME_ID,), [(r.directory, r.reason) for r in self.report.refused])
        game = self.report.game(GAME_ID)
        self.assertEqual(game.identity.serials, ("SLUS-00000",))
        self.assertEqual(game.version, "0.1.0")
        result = conformance.run(game, self.repo / "work", repo_root=self.repo)
        self.assertTrue(result.passed, "\n".join(check.line() for check in result.failures))
        self.assertGreaterEqual(len(result.checks), 40, "the example lane exercises the behavioural half")

    def test_the_scaffolded_studio_is_the_core_shell(self) -> None:
        game = self.report.game(GAME_ID)
        self.assertEqual(game.manifest.studio_label, "PS2 Demo 1 Studio")
        self.assertEqual(game.studio_window, "studio")
        self.assertEqual([window.window_id for window in game.windows], ["studio"])
        self.assertEqual(game.studio.flag, "demo-ps2-studio")
        self.assertNotIn(game.manifest.studio_label,
                         (self.package / "__init__.py").read_text(encoding="utf-8"),
                         "the scaffold never types the label it is given")
        dialog = None
        try:
            dialog = game.studio.factory()
        except ImportError:  # PyQt5 is not installed here
            self.skipTest("PyQt5 is not installed")
        try:
            self.assertEqual(dialog.windowTitle(), "PS2 Demo 1 Studio")
            self.assertEqual(len(dialog.page_ids()), 14)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_the_example_lane_selftest_and_boundary(self) -> None:
        probe = sys.modules[f"_mod_editor_games_probe.{GAME_ID}.example_lane"]
        self.assertEqual(probe.selftest(), 0)
        checks = conformance.check_boundary(self.package, f"mod_editor.games.{GAME_ID}")
        self.assertTrue(all(check.passed for check in checks), [check.detail for check in checks])

    def test_the_registry_fragment_is_a_complete_row(self) -> None:
        fragment = json.loads((self.package / "registry.fragment.json").read_text(encoding="utf-8"))
        registry_merge.validate_fragment(fragment)
        [row] = fragment["capabilities"]
        from mod_editor.capabilities import validate_registry

        self.assertEqual(set(row), validate_registry.CAPABILITY_KEYS)
        self.assertEqual(row["classification"], "offline-writer-proved")
        self.assertIn("PLACEHOLDER", row["summary"])

    def test_refusals(self) -> None:
        fields = dict(console="PS2", game="Demo", year="1")
        with self.assertRaisesRegex(contract.ContractError, "already exists"):
            scaffold.scaffold(GAME_ID, "Again", "PlayStation 2", repo_root=self.repo, **fields)
        with self.assertRaisesRegex(contract.ContractError, "must be lowercase"):
            scaffold.scaffold("Bad-Id", "Bad", "PlayStation 2", repo_root=self.repo, **fields)
        with self.assertRaisesRegex(contract.ContractError, "non-empty"):
            scaffold.scaffold("other_game", "", "PlayStation 2", repo_root=self.repo, **fields)
        with self.assertRaisesRegex(contract.ContractError, "1 to 8 characters"):
            scaffold.scaffold("other_game", "Other", "PlayStation 2", repo_root=self.repo,
                              console="PlayStation 2", game="Demo", year="1")
        self.assertFalse((self.repo / "mod_editor" / "games" / "other_game").exists())

    def test_the_command_line_scaffolds_too(self) -> None:
        with tempfile.TemporaryDirectory(prefix="scaffold-cli-") as other:
            completed = subprocess.run(
                cli_command("new", "madden08_ps2", "--title", "Madden NFL 08 (USA, PlayStation 2)",
                            "--platform", "PlayStation 2", "--console", "PS2", "--game", "Madden",
                            "--year", "08", "--serial", "SLUS-21638", "--repo-root", other),
                cwd=str(ROOT), capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("SCAFFOLDED game=madden08_ps2 files=10", completed.stdout)
            self.assertIn("studio='PS2 Madden 08 Studio'", completed.stdout)
            self.assertTrue((Path(other) / "mod_editor" / "games" / "madden08_ps2" / "game.json").is_file())


class FragmentsTests(unittest.TestCase):
    """Mirrors regenerate from the canonical files, and drift is reported by name."""

    def setUp(self) -> None:
        self.repo = Path(tempfile.mkdtemp(prefix="fragments-repo-"))
        self.addCleanup(shutil.rmtree, self.repo, True)
        scaffold.scaffold(GAME_ID, "Demo Game (PlayStation 2)", "PlayStation 2",
                          console="PS2", game="Demo", year="1", repo_root=self.repo)
        self.games_root = self.repo / "mod_editor" / "games"
        self.package = self.games_root / GAME_ID

    def test_without_canonical_files_the_fragments_are_authoritative(self) -> None:
        _manifest, changes, notes = fragments.plan(GAME_ID, repo_root=self.repo, games_root=self.games_root)
        self.assertEqual(len(notes), 2, notes)
        self.assertEqual([path.name for path, expected in changes.items() if expected is not None], ["pins.json"])
        self.assertEqual(fragments.check(GAME_ID, repo_root=self.repo, games_root=self.games_root), [])

    def test_with_canonical_files_the_mirrors_are_reproduced_and_drift_is_caught(self) -> None:
        # A canonical registry and allowlist that carry the scaffolded game, as after its PR.
        fragment = json.loads((self.package / "registry.fragment.json").read_text(encoding="utf-8"))
        canonical = json.loads((ROOT / fragments.REGISTRY_RELATIVE).read_text(encoding="utf-8"))
        merged = registry_merge.merge(canonical, [fragment])
        registry_path = self.repo / fragments.REGISTRY_RELATIVE
        registry_path.parent.mkdir(parents=True)
        registry_path.write_bytes(registry_merge.canonical_bytes(merged))
        allowlist_path = self.repo / fragments.ALLOWLIST_RELATIVE
        allowlist_path.parent.mkdir(parents=True)
        allowlist_path.write_bytes(
            (ROOT / fragments.ALLOWLIST_RELATIVE).read_bytes()
            + b"# demo\n" + b"".join(f"{line}\n".encode() for line in
                                   [l for l in (self.package / "allowlist.fragment.txt").read_text().splitlines() if l and not l.startswith("#")])
        )
        self.assertEqual(fragments.check(GAME_ID, repo_root=self.repo, games_root=self.games_root), [])

        (self.package / "registry.fragment.json").write_bytes(b'{"schema": "wrong"}\n')
        (self.package / "allowlist.fragment.txt").write_text("# header\nmod_editor/games/demo_ps2/game.json\n", encoding="utf-8", newline="\n")
        (self.package / "pins.json").write_bytes(b'{"schema": "vc_game_module_pins/v1", "game_id": "demo_ps2"}\n')
        problems = fragments.check(GAME_ID, repo_root=self.repo, games_root=self.games_root)
        self.assertEqual(sorted(problems), sorted([
            "registry.fragment.json differs from the canonical files",
            "allowlist.fragment.txt differs from the canonical files",
            "pins.json differs from the canonical files",
        ]))
        written = fragments.write(GAME_ID, repo_root=self.repo, games_root=self.games_root)
        self.assertEqual(sorted(path.name for path in written), ["allowlist.fragment.txt", "pins.json", "registry.fragment.json"])
        self.assertEqual(fragments.check(GAME_ID, repo_root=self.repo, games_root=self.games_root), [])
        regenerated = json.loads((self.package / "registry.fragment.json").read_text(encoding="utf-8"))
        self.assertEqual(regenerated, fragment, "the mirror is exactly the split of the canonical registry")
        self.assertIn("# demo", allowlist_path.read_text(), "the canonical allowlist itself is never rewritten")

    def test_the_ps2_module_is_in_step_with_the_canonical_files(self) -> None:
        self.assertEqual(fragments.check("nfl2k5_ps2"), [])
        completed = subprocess.run(
            cli_command("fragments", "nfl2k5_ps2", "--check"),
            cwd=str(ROOT), capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("FRAGMENTS_OK game=nfl2k5_ps2", completed.stdout)

    def test_patterns_match_case_insensitively(self) -> None:
        self.assertTrue(fragments.matches("tools/nfl2k5_PS2_save.py", ["*ps2*"]))
        self.assertTrue(fragments.matches("docs/product/PS2_PHASE2_TEXT.md", ["*ps2*"]))
        self.assertFalse(fragments.matches("tools/nfl_outer.py", ["*ps2*", "*xxh3*"]))


if __name__ == "__main__":
    unittest.main()

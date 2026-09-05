"""tools/registry_add_rows.py moves every count pin with the rows it adds, on a scratch copy.

The scratch copy holds the registry, the validator and every file that pins a
count; after the tool runs, the scratch validator itself must accept the
scratch registry.  Nothing in this tree is written.  No game data.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import registry_add_rows as tool  # noqa: E402

COPIED = (
    tool.REGISTRY, tool.VALIDATOR, tool.CAPABILITIES, tool.MODEL, tool.REGISTRY_SCHEMA, tool.PROJECT_SCHEMA,
    tool.RUNTIME_GATE, tool.APF_RUNTIME_GATE, tool.INSTALLER_TEST, tool.PACKAGING_TEST, tool.VALIDATE_ALL,
    tool.APF_README, tool.APF_STATUS, tool.GETTING_STARTED, tool.STATUS, tool.CHANGELOG, tool.PACKAGE_INIT,
    tool.FREEZE_TEST, tool.ALLOWLIST, "mod_editor/core/errors.py",
)


def _scratch() -> Path:
    root = Path(tempfile.mkdtemp(prefix="add-rows-"))
    for relative in COPIED:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return root


def _validator(root: Path):
    spec = importlib.util.spec_from_file_location("scratch_validate_registry", root / tool.VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _registry(root: Path) -> dict:
    return json.loads((root / tool.REGISTRY).read_text(encoding="utf-8"))


def _row_like(root: Path, source_id: str, **changes) -> dict:
    [row] = [item for item in _registry(root)["capabilities"] if item["id"] == source_id]
    row = json.loads(json.dumps(row))
    row.update(changes)
    return row


class ExistingGameRowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _scratch()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.before = tool.counts(_registry(self.root)["capabilities"])

    def _write_row(self, name: str, row: dict) -> Path:
        path = self.root / name
        path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8", newline="\n")
        return path

    def test_one_row_moves_every_count_pin_and_the_validator_accepts_the_result(self) -> None:
        row = self._write_row("row.json", _row_like(
            self.root, "nfl2k5ps2.colors.unif_words",
            id="nfl2k5ps2.colors.zz_probe", title="Probe row", validation_command="bash tools/validate_zz_probe.sh",
        ))
        plan = tool.apply(self.root, game="nfl2k5_ps2", rows=[row], modules=["zz_probe_module"])
        rows, covered, validators, k = self.before
        registry = _registry(self.root)
        self.assertEqual(tool.counts(registry["capabilities"]), (rows + 1, covered + 1, validators + 1, k))
        self.assertEqual([r["id"] for r in registry["capabilities"]], sorted(r["id"] for r in registry["capabilities"]))
        raw = (self.root / tool.REGISTRY).read_bytes()
        self.assertEqual(raw, tool.canonical(registry).encode("utf-8"), "the registry stays canonical")
        _validator(self.root).validate_data(registry, check_files=False)
        for relative, needle in (
            (tool.VALIDATE_ALL, f"EXPECTED_CAPABILITIES = {rows + 1}"),
            (tool.VALIDATE_ALL, f"EXPECTED_COVERED_CAPABILITIES = {covered + 1}"),
            (tool.VALIDATE_ALL, f"EXPECTED_UNIQUE_VALIDATORS = {validators + 1}"),
            (tool.RUNTIME_GATE, f"require(len(registry.capabilities) == {rows + 1},"),
            (tool.RUNTIME_GATE, f'"registry={rows + 1} sections=12 nfl2k5_capabilities={k} "'),
            (tool.RUNTIME_GATE, '        "zz_probe_module",\n    )'),
            (tool.APF_RUNTIME_GATE, f"len(registry.capabilities) == {rows + 1}"),
            (tool.INSTALLER_TEST, f'"len(registry.capabilities) == {rows + 1}"'),
            (tool.PACKAGING_TEST, f'"registry has {rows + 1} cross-title rows"'),
            (tool.PACKAGING_TEST, f'"registry={rows + 1} sections=12 nfl2k5_capabilities={k}"'),
            (tool.APF_README, f"APF capabilities ({rows + 1} across all three"),
            (tool.APF_STATUS, f"contains {rows + 1} records globally"),
            (tool.GETTING_STARTED, f"The current registry has {rows + 1} cross-title rows"),
            (tool.STATUS, f"| Capability registry | {rows + 1} rows total;"),
        ):
            with self.subTest(site=(relative, needle)):
                self.assertIn(needle, (self.root / relative).read_text(encoding="utf-8"))
        self.assertEqual(len(plan.pending), 10, sorted(path.name for path in plan.pending))
        for path in plan.pending:
            self.assertNotIn(b"\r", path.read_bytes())

    def test_dry_run_writes_nothing_and_refusals_leave_the_tree_untouched(self) -> None:
        snapshot = {relative: (self.root / relative).read_bytes() for relative in COPIED}
        row = self._write_row("row.json", _row_like(self.root, "nfl2k5ps2.colors.unif_words", id="nfl2k5ps2.colors.zz_dry"))
        plan = tool.apply(self.root, game="nfl2k5_ps2", rows=[row], dry_run=True)
        self.assertGreaterEqual(len(plan.pending), 10)
        for relative, payload in snapshot.items():
            self.assertEqual((self.root / relative).read_bytes(), payload, relative)
        duplicate = self._write_row("dup.json", _row_like(self.root, "nfl2k5ps2.colors.unif_words"))
        with self.assertRaisesRegex(tool.ApplyError, "already in the registry"):
            tool.apply(self.root, game="nfl2k5_ps2", rows=[duplicate])
        wrong_game = self._write_row("wrong.json", _row_like(self.root, "nfl2k5ps2.colors.unif_words", id="x.y.z", game="nfl2k5_xbox"))
        with self.assertRaisesRegex(tool.ApplyError, "row game is"):
            tool.apply(self.root, game="nfl2k5_ps2", rows=[wrong_game])
        placeholder = self._write_row("todo.json", _row_like(self.root, "nfl2k5ps2.colors.unif_words", id="x.y.todo", summary="TODO fill"))
        with self.assertRaisesRegex(tool.ApplyError, "unfilled placeholder"):
            tool.apply(self.root, game="nfl2k5_ps2", rows=[placeholder])
        with self.assertRaisesRegex(tool.ApplyError, "already widened"):
            tool.apply(self.root, game="nfl2k5_ps2", rows=[row], widen_surfaces=["colors"], dry_run=True)
        for relative, payload in snapshot.items():
            self.assertEqual((self.root / relative).read_bytes(), payload, relative)

    def test_allowlist_lines_append_once(self) -> None:
        fragment = self.root / "allowlist.fragment.txt"
        fragment.write_text("# header\nmod_editor/games/zz/__init__.py\nmod_editor/games/zz/game.json\n",
                            encoding="utf-8", newline="\n")
        tool.apply(self.root, game="zz_game", rows=[], allowlist_fragment=fragment)
        text = (self.root / tool.ALLOWLIST).read_text(encoding="utf-8")
        self.assertTrue(text.endswith("# zz_game: shipped by the game module (mod_editor/games/zz_game/allowlist.fragment.txt).\n"
                                      "mod_editor/games/zz/__init__.py\nmod_editor/games/zz/game.json\n"))
        with self.assertRaisesRegex(tool.ApplyError, "already lists"):
            tool.apply(self.root, game="zz_game", rows=[], allowlist_fragment=fragment)

    def test_widening_a_surface_lands_with_its_row(self) -> None:
        # portraits_faces has no PS2 row today; a PS2 row there needs the widening.
        registry = _registry(self.root)
        self.assertFalse(any(r["game"] == "nfl2k5_ps2" and r["surface"] == "portraits_faces" for r in registry["capabilities"]))
        before = tuple(_validator(self.root).SURFACE_GAMES["portraits_faces"])
        self.assertNotIn("nfl2k5_ps2", before)
        row = self._write_row("row.json", _row_like(
            self.root, "nfl2k5ps2.textures.disc_inventory",
            id="nfl2k5ps2.portraits.zz_inventory", surface="portraits_faces", title="Probe",
        ))
        tool.apply(self.root, game="nfl2k5_ps2", rows=[row], widen_surfaces=["portraits_faces"])
        validator = _validator(self.root)
        # The game joins the surface's rule and everything already on it stays: a
        # module that widened the same surface first is not un-widened, and no
        # newcomer is demanded of the others. Read from the tree rather than
        # spelled out, because which games a surface already carries is exactly
        # what a second module changes.
        self.assertEqual(validator.SURFACE_GAMES["portraits_faces"], before + ("nfl2k5_ps2",))
        validator.validate_data(_registry(self.root), check_files=False)

    def test_a_row_on_an_uncovered_surface_without_widening_fails_the_scratch_validator(self) -> None:
        row = self._write_row("row.json", _row_like(
            self.root, "nfl2k5ps2.textures.disc_inventory",
            id="nfl2k5ps2.portraits.zz_inventory", surface="portraits_faces", title="Probe",
        ))
        tool.apply(self.root, game="nfl2k5_ps2", rows=[row])
        validator = _validator(self.root)
        with self.assertRaisesRegex(validator.RegistryError, "incomplete game/surface coverage"):
            validator.validate_data(_registry(self.root), check_files=False)


class NewGameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _scratch()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_another_game_registers_everywhere_and_validates(self) -> None:
        entry = {
            "id": "demo_ps2", "platform": "PlayStation 2", "title": "Demo Game (USA, PlayStation 2)",
            "public_input": "User supplies a legally obtained image; nothing is bundled.",
            "retail_identity": {"content_sha256": "1" * 64, "executable_sha256": "2" * 64},
        }
        entry_path = self.root / "entry.json"
        entry_path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8", newline="\n")
        menus_row = _row_like(self.root, "nfl2k5ps2.menus.text_banks", id="demo_ps2.menus.text", game="demo_ps2",
                              title="Demo text", validation_command="bash tools/validate_demo_text.sh")
        portraits_row = _row_like(self.root, "nfl2k5ps2.textures.disc_inventory", id="demo_ps2.portraits.view",
                                  game="demo_ps2", surface="portraits_faces", title="Demo portraits")
        rows = []
        for name, row in (("menus.json", menus_row), ("portraits.json", portraits_row)):
            path = self.root / name
            path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8", newline="\n")
            rows.append(path)
        before = _validator(self.root)
        with self.assertRaisesRegex(tool.ApplyError, "pass --widen"):
            tool.apply(self.root, game="demo_ps2", rows=rows, new_game=entry_path, display_name="Demo Game (PS2)")
        tool.apply(self.root, game="demo_ps2", rows=rows, new_game=entry_path, display_name="Demo Game (PS2)",
                   widen_surfaces=["menus", "portraits_faces"])
        validator = _validator(self.root)
        # Relative to whatever the fixture already registers (today: four games, madden09_ps2 the first newcomer).
        self.assertEqual(validator.GAMES, tuple(sorted(before.GAMES + ("demo_ps2",))))
        self.assertEqual(validator._ESTABLISHED_GAMES, before._ESTABLISHED_GAMES, "a later newcomer never changes the established set")
        self.assertEqual(validator.SURFACE_GAMES["saves"], validator._ESTABLISHED_GAMES, "GAMES-wide rules no longer demand the newcomer")
        self.assertEqual(validator.SURFACE_GAMES["menus"], before.SURFACE_GAMES["menus"] + ("demo_ps2",))
        self.assertEqual(validator.SURFACE_GAMES["portraits_faces"], before.SURFACE_GAMES.get("portraits_faces", validator._LEGACY_GAMES) + ("demo_ps2",))
        registry = _registry(self.root)
        self.assertEqual([g["id"] for g in registry["games"]], list(validator.GAMES))
        validator.validate_data(registry, check_files=False)
        model = (self.root / tool.MODEL).read_text(encoding="utf-8")
        self.assertIn('    DEMO_PS2 = "demo_ps2"\n', model)
        self.assertIn('GameId.DEMO_PS2: "Demo Game (PS2)",', model)
        capabilities = (self.root / tool.CAPABILITIES).read_text(encoding="utf-8")
        self.assertIn('"demo_ps2": GameId.DEMO_PS2,', capabilities)
        self.assertRegex(capabilities, r'required = \{[^}]*"demo_ps2"[^}]*\}')
        self.assertIn('{"id": "demo_ps2", "title": "Demo Game (USA, PlayStation 2)"},', capabilities)
        schema = json.loads((self.root / tool.REGISTRY_SCHEMA).read_text(encoding="utf-8"))
        self.assertEqual(schema["$defs"]["capability"]["properties"]["game"]["enum"], list(validator.GAMES))
        self.assertEqual(schema["$defs"]["game"]["properties"]["id"]["enum"], list(validator.GAMES))
        project = json.loads((self.root / tool.PROJECT_SCHEMA).read_text(encoding="utf-8"))
        self.assertIn("demo_ps2", project["properties"]["game"]["enum"])
        import py_compile

        for relative in (tool.MODEL, tool.CAPABILITIES, tool.VALIDATOR):
            py_compile.compile(str(self.root / relative), doraise=True)


if __name__ == "__main__":
    unittest.main()

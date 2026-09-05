"""The game-module contract: frozen surface, discovery, registry merge, boundary.

Core-owned tests.  They pin the public surface of ``mod_editor.games.contract``
so an accidental rename fails here before it reaches a game team, prove that
discovery fails closed per package, prove the per-game registry fragment
convention is lossless against the canonical registry the validator already
accepts, and prove the plugin boundary in both directions -- today's upstream
modules import nothing from ``mod_editor.games`` and a game imports the core
only through the contract.  No game data is required.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
for _candidate in (ROOT, ROOT / "tests" / "mod_editor"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import mod_editor.games as games  # noqa: E402
from mod_editor.games import conformance, contract, registry_merge  # noqa: E402
from mod_editor.capabilities import validate_registry  # noqa: E402

REGISTRY_PATH = ROOT / "mod_editor" / "capabilities" / "registry.v1.json"
ALLOWLIST_PATH = ROOT / "packaging" / "release-allowlist.txt"
ADAPTER_DIR = ROOT / "mod_editor" / "games" / "nfl2k5_ps2"

#: The v1 surface.  Changing this table is a contract event, not a refactor:
#: a minor bump may add entries; removing or renaming one is a major bump.
EXPECTED_SURFACE = {
    "ALLOWED_CORE_IMPORTS": ("constant",),
    "ArtLane": ("decode_png", "encode", "replacement_identity"),
    "Artifact": ("path", "sha256", "kind"),
    "AudioLane": ("decode_wav",),
    "CONTRACT_MAJOR": ("constant",),
    "CONTRACT_MINOR": ("constant",),
    "CONTRACT_SCHEMA": ("constant",),
    "CONTRACT_VERSION": ("constant",),
    "Catalogue": ("schema", "lane_id", "source", "targets", "document"),
    "CodePatch": ("patch_id", "title", "surface", "parameters", "host_site", "note"),
    "CodePatchLane": ("emit_pnach", "patches", "translation", "verify_pnach"),
    "ContractError": ("exception",),
    "DeclaredRange": ("start", "length", "reason"),
    "Edit": ("target_key", "values", "note"),
    "EncodedArt": ("png", "width", "height", "note"),
    "Field": ("key", "kind", "label", "help", "choices", "minimum", "maximum", "read_only"),
    "GAME_ATTRIBUTE": ("constant",),
    "GameIdentity": ("game_id", "title", "platform", "serials", "executable_sha256", "content_sha256"),
    "GameManifest": (
        "schema", "game_id", "package", "title", "platform", "console", "game", "year",
        "version", "contract",
        "registry_fragment", "allowlist_fragment", "pins", "product_modules", "tool_modules", "root",
        "allowlist_patterns", "page_notes",
    ),
    "GameModule": (
        "contract", "identity", "identifier", "lanes", "windows", "manifest", "package",
        "studio_window",
    ),
    "Lane": (
        "build", "build_catalogue", "capability_id", "check_edit", "classification",
        "compose_recipe", "conformance_edits", "fixed_allocation", "lane_id", "plan",
        "recipe_schema", "surface", "synthetic_source", "title", "validators", "verify",
    ),
    "MANIFEST_NAME": ("constant",),
    "MANIFEST_SCHEMA": ("constant",),
    "PAGE_ORDER": ("constant",),
    "MipsPatch": ("patch_id", "words", "elf_identity", "parameters", "note"),
    "MipsWord": ("address", "original", "replacement"),
    "PINS_SCHEMA": ("constant",),
    "Plan": ("lane_id", "target_keys", "declared_ranges", "document"),
    "REGISTRY_FRAGMENT_SCHEMA": ("constant",),
    "ReadOnlyLane": ("read_only",),
    "Receipt": ("schema", "lane_id", "source", "destination", "declared_ranges", "document", "artifacts"),
    "Refusal": ("exception",),
    "SHARED_FORMATS_PACKAGE": ("constant",),
    "SURFACE_PAGES": ("constant",),
    "SourceIdentifier": ("accepted_suffixes", "identify"),
    "SourceIdentity": (
        "kind", "path", "size_bytes", "serial", "executable_sha256",
        "serial_matches", "retail_executable", "headline", "details",
    ),
    "Target": ("key", "label", "detail", "budget", "searchable", "raw", "fields"),
    "Verdict": ("passed", "summary", "document"),
    "WindowSpec": ("window_id", "menu_label", "tooltip", "flag", "factory", "needs_studio_session"),
    "accepts_contract": ("function",),
    "contract_surface": ("function",),
    "lane_page": ("function",),
    "load_manifest": ("function",),
    "parse_contract": ("function",),
    "require": ("function",),
}

from games_fakes import (  # noqa: E402
    OK_GAME_SOURCE as GOOD_GAME_SOURCE,
    SHA,
    manifest as _manifest,
    write_fake_game,
)


class FrozenSurfaceTests(unittest.TestCase):
    def test_public_surface_is_pinned(self) -> None:
        self.assertEqual(contract.contract_surface(), EXPECTED_SURFACE)

    def test_contract_version_acceptance(self) -> None:
        self.assertEqual(contract.CONTRACT_SCHEMA, "vc_game_module/v1")
        self.assertTrue(contract.accepts_contract("vc_game_module/v1"))
        self.assertTrue(contract.accepts_contract("vc_game_module/v1.0"))
        self.assertFalse(contract.accepts_contract("vc_game_module/v1.7"), "a newer minor is refused")
        self.assertFalse(contract.accepts_contract("vc_game_module/v2"))
        self.assertFalse(contract.accepts_contract("something/else"))
        self.assertEqual(contract.parse_contract("vc_game_module/v1.2"), (1, 2))
        with self.assertRaises(contract.ContractError):
            contract.parse_contract("v1")

    def test_refusal_is_a_validation_error(self) -> None:
        from mod_editor.core.errors import ValidationError

        self.assertTrue(issubclass(contract.Refusal, ValidationError))
        self.assertTrue(issubclass(contract.Refusal, contract.ContractError))


class StudioVocabularyTests(unittest.TestCase):
    """The studio label, the pages, and where a lane lands on them."""

    def test_every_page_is_named_once_in_the_studio_order(self) -> None:
        ids = [page_id for page_id, _title in contract.PAGE_ORDER]
        titles = [title for _page_id, title in contract.PAGE_ORDER]
        self.assertEqual(len(ids), 14)
        self.assertEqual(len(set(ids)), 14)
        self.assertTrue(all(title.strip() for title in titles))
        self.assertEqual(ids[0], "uniforms", "the Xbox studio's first page is first here")
        self.assertEqual(ids[-1], "build", "Build & Share is last")

    def test_every_registry_surface_has_a_page(self) -> None:
        pages = {page_id for page_id, _title in contract.PAGE_ORDER}
        self.assertEqual(set(contract.SURFACE_PAGES) , set(validate_registry.SURFACES),
                         "a surface without a page would leave its lanes nowhere")
        self.assertTrue(set(contract.SURFACE_PAGES.values()) <= pages)

    def test_lane_page_reads_the_lane_first_then_its_surface(self) -> None:
        colours = type("L", (), {"surface": "colors"})()
        self.assertEqual(contract.lane_page(colours), "identity")
        named = type("L", (), {"surface": "colors", "page": "field_art"})()
        self.assertEqual(contract.lane_page(named), "field_art")
        unmapped = type("L", (), {"surface": "no_such_surface"})()
        self.assertEqual(contract.lane_page(unmapped), "textures", "always somewhere reachable")

    def test_a_field_names_a_shape_and_refuses_an_unknown_kind(self) -> None:
        item = contract.Field("text", "text", "Display text", help="9 characters")
        self.assertFalse(item.read_only)
        target = contract.Target("t", "T", fields=(item,))
        self.assertEqual(target.fields[0].label, "Display text")
        with self.assertRaisesRegex(contract.ContractError, "is not one of"):
            contract.Field("k", "spreadsheet", "K")
        with self.assertRaisesRegex(contract.ContractError, "two fields claim one key"):
            contract.Target("t", "T", fields=(item, contract.Field("text", "int", "Again")))

    def test_encoded_art_carries_bytes_and_a_size(self) -> None:
        art = contract.EncodedArt(b"\x89PNG...", 64, 32, note="scaled 2x")
        self.assertEqual((art.width, art.height), (64, 32))
        with self.assertRaisesRegex(contract.ContractError, "non-empty PNG"):
            contract.EncodedArt(b"", 64, 32)
        with self.assertRaisesRegex(contract.ContractError, "positive width"):
            contract.EncodedArt(b"png", 0, 32)

    def test_the_lane_sub_protocols_are_runtime_checkable_and_distinct(self) -> None:
        game = games.load("nfl2k5_ps2")
        writer = game.lane("colors.unif_words")
        self.assertIsInstance(writer, contract.Lane)
        self.assertNotIsInstance(writer, contract.ArtLane)
        self.assertNotIsInstance(writer, contract.AudioLane)
        self.assertNotIsInstance(writer, contract.ReadOnlyLane,
                                 "a writer must not answer the read-only protocol")


class DataclassValidationTests(unittest.TestCase):
    def test_identity_rejects_bad_ids_and_digests(self) -> None:
        with self.assertRaises(contract.ContractError):
            contract.GameIdentity("Bad Id", "t", "p")
        with self.assertRaises(contract.ContractError):
            contract.GameIdentity("okgame", "t", "p", executable_sha256=("nothex",))
        with self.assertRaises(contract.ContractError):
            contract.GameIdentity("okgame", "t", "p", serials=("A", "A"))
        identity = contract.GameIdentity("okgame", "t", "p", ("S-1",), (SHA,), ())
        self.assertEqual(identity.serials, ("S-1",))

    def test_values_are_read_only_mappings(self) -> None:
        edit = contract.Edit("k", {"a": 1})
        with self.assertRaises(TypeError):
            edit.values["a"] = 2  # type: ignore[index]
        catalogue = contract.Catalogue("s/v1", "lane", "src", (contract.Target("k", "K"),), {"x": 1})
        self.assertEqual(catalogue.target("k").label, "K")
        with self.assertRaisesRegex(contract.Refusal, "not a target"):
            catalogue.target("zz")
        with self.assertRaises(contract.ContractError):
            contract.Catalogue("s/v1", "lane", "src", (contract.Target("k", "K"), contract.Target("k", "K2")))

    def test_declared_range_and_verdict_shapes(self) -> None:
        self.assertEqual(contract.DeclaredRange(4, 8).end, 12)
        with self.assertRaises(contract.ContractError):
            contract.DeclaredRange(4, 0)
        with self.assertRaises(contract.ContractError):
            contract.Verdict(True, "")
        with self.assertRaises(contract.ContractError):
            contract.WindowSpec("w", "L", "T", "Bad Flag", lambda **_: None)


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="games-manifest-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_the_studio_label_is_composed_from_the_three_fields(self) -> None:
        directory = write_fake_game(self.root, "labelled", GOOD_GAME_SOURCE,
                                    _manifest("labelled", console="PS2", game="Madden", year="09"))
        manifest = contract.load_manifest(directory)
        self.assertEqual(manifest.studio_label, "PS2 Madden 09 Studio")
        self.assertEqual((manifest.console, manifest.game, manifest.year), ("PS2", "Madden", "09"))

    def test_a_manifest_without_the_display_fields_is_refused_by_name(self) -> None:
        for absent in ("console", "game", "year"):
            with self.subTest(absent=absent):
                document = _manifest(f"no{absent}")
                document.pop(absent)
                directory = write_fake_game(self.root, f"no{absent}", GOOD_GAME_SOURCE, document)
                with self.assertRaises(contract.ContractError) as caught:
                    contract.load_manifest(directory)
                self.assertIn(absent, str(caught.exception))
                self.assertIn("<console> <game> <year> Studio", str(caught.exception))

    def test_page_notes_must_name_real_pages(self) -> None:
        good = write_fake_game(self.root, "noted", GOOD_GAME_SOURCE,
                               _manifest("noted", page_notes={"uniforms": "EA FSH inside BIG; no console write yet."}))
        self.assertEqual(contract.load_manifest(good).page_note("uniforms"),
                         "EA FSH inside BIG; no console write yet.")
        self.assertEqual(contract.load_manifest(good).page_note("audio"), "")
        bad = write_fake_game(self.root, "misnoted", GOOD_GAME_SOURCE,
                              _manifest("misnoted", page_notes={"no_such_page": "…"}))
        with self.assertRaisesRegex(contract.ContractError, "not studio"):
            contract.load_manifest(bad)

    def test_manifest_loads_and_rejects_drift(self) -> None:
        directory = write_fake_game(self.root, "okgame", GOOD_GAME_SOURCE, _manifest("okgame"))
        manifest = contract.load_manifest(directory)
        self.assertEqual(manifest.version, "2.3.4")
        self.assertEqual(manifest.pins_path, directory / "pins.json")
        for bad in (
            {"contract": "vc_game_module/v9"},
            {"version": "one"},
            {"package": "mod_editor.games.other"},
            {"registry_fragment": "../escape.json"},
            {"schema": "wrong"},
            {"console": "PS 2"},
            {"year": " 2K5"},
            {"game": "a" * 25},
        ):
            with self.subTest(bad=bad):
                other = write_fake_game(self.root, f"bad{len(bad)}{list(bad)[0]}", GOOD_GAME_SOURCE,
                                        _manifest(f"bad{len(bad)}{list(bad)[0]}", **bad))
                with self.assertRaises(contract.ContractError):
                    contract.load_manifest(other)
        extra = _manifest("extra")
        extra["surprise"] = 1
        with self.assertRaisesRegex(contract.ContractError, "keys differ"):
            contract.load_manifest(write_fake_game(self.root, "extra", GOOD_GAME_SOURCE, extra))


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="games-root-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_discovery_fails_closed_per_package(self) -> None:
        write_fake_game(self.root, "okgame", GOOD_GAME_SOURCE, _manifest("okgame"))
        write_fake_game(self.root, "oldgame", GOOD_GAME_SOURCE,
                        _manifest("oldgame", contract="vc_game_module/v9"))
        write_fake_game(self.root, "crashgame", "import a_dependency_nobody_has\n",
                        _manifest("crashgame"))
        write_fake_game(self.root, "nogame", "GAME = None\n", _manifest("nogame"))
        write_fake_game(self.root, "notagame", "X = 1\n", None)  # no manifest: ignored
        (self.root / "_formats").mkdir()
        (self.root / "_formats" / "__init__.py").write_text("", encoding="utf-8", newline="\n")
        report = games.discover(self.root)
        self.assertEqual(report.game_ids, ("okgame",), [(item.directory, item.reason) for item in report.refused])
        refused = {item.directory: item for item in report.refused}
        self.assertEqual(set(refused), {"oldgame", "crashgame", "nogame"})
        self.assertIn("vc_game_module/v9", refused["oldgame"].reason)
        self.assertEqual(refused["oldgame"].title, "oldgame title", "display fields survive a refusal")
        self.assertIn("a_dependency_nobody_has", refused["crashgame"].reason)
        self.assertIn("exposes no module-level GAME", refused["nogame"].reason)
        with self.assertRaisesRegex(contract.ContractError, "vc_game_module/v9"):
            games.manifests(self.root)  # a gate reading manifests fails closed, it never skips
        shutil.rmtree(self.root / "oldgame")
        self.assertEqual([m.game_id for m in games.manifests(self.root)], ["crashgame", "nogame", "okgame"])

    def test_duplicate_game_ids_are_refused(self) -> None:
        write_fake_game(self.root, "okgame", GOOD_GAME_SOURCE, _manifest("okgame"))
        write_fake_game(self.root, "twin", GOOD_GAME_SOURCE, _manifest("twin"))
        # ``twin``'s code claims the id ``okgame`` (its manifest says twin).
        report = games.discover(self.root)
        self.assertEqual(report.game_ids, ("okgame",), [(item.directory, item.reason) for item in report.refused])
        self.assertTrue(any("manifest says" in item.reason for item in report.refused))

    def test_discovery_works_through_a_symlinked_or_aliased_root(self) -> None:
        """macOS gives /var/... for /private/var/...; Windows gives short names. Both must load."""

        real = self.root / "real"
        write_fake_game(real, "okgame", GOOD_GAME_SOURCE, _manifest("okgame"))
        alias = self.root / "alias"
        try:
            os.symlink(real, alias, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:  # no symlink privilege here
            self.skipTest(f"cannot create a symlink on this host: {exc}")
        report = games.discover(alias)
        self.assertEqual(report.game_ids, ("okgame",), [(item.directory, item.reason) for item in report.refused])
        self.assertEqual(games.load("okgame", alias).identity.title, "OK Game")
        self.assertEqual([m.game_id for m in games.manifests(alias)], ["okgame"])

    def test_load_names_the_reason_for_a_refused_game(self) -> None:
        write_fake_game(self.root, "oldgame", GOOD_GAME_SOURCE,
                        _manifest("oldgame", contract="vc_game_module/v9"))
        with self.assertRaisesRegex(contract.Refusal, "could not be hosted"):
            games.load("oldgame", self.root)
        with self.assertRaisesRegex(contract.Refusal, "No hosted game"):
            games.load("absent", self.root)

    def test_the_real_root_hosts_the_ps2_adapter(self) -> None:
        report = games.discover()
        self.assertEqual(report.refused, ())
        self.assertIn("nfl2k5_ps2", report.game_ids)
        game = report.game("nfl2k5_ps2")
        self.assertEqual(game.identity.serials, ("SLUS-20919",))
        self.assertEqual(game.version, "0.1.0")
        self.assertEqual([window.flag for window in game.windows],
                         ["ps2-studio", "ps2-disc-studio", "ps2-save", "ps2-disc", "ps2-export"])
        self.assertEqual(game.manifest.studio_label, "PS2 NFL 2K5 Studio")
        self.assertEqual(game.studio_window, "studio")
        self.assertIs(game.studio, game.windows[0])
        # Every page the studio cannot fill yet says why in the module's own
        # words; a page with a lane must not also carry a note, or the note
        # would be prose nobody ever reads.
        pages_with_lanes = {contract.lane_page(lane) for lane in game.lanes}
        self.assertTrue(set(game.manifest.page_notes), "the empty pages carry the game's reason")
        self.assertEqual(set(game.manifest.page_notes) & pages_with_lanes, set())
        # One lane per registry row the fragment carries: the six on-disc
        # writers, the read-only inventory and the executable patches (whose
        # row arrived on 2026-09-05).  The set is asserted rather than the
        # order, which is the module's to choose and the build queue's to follow.
        self.assertEqual({lane.lane_id for lane in game.lanes},
                         {"colors.unif_words", "menus.text_banks", "players.disc_roster",
                          "scripts.director_playbook", "stadiums.position_lanes",
                          "audio.audo_exact_slot_replace", "textures.disc_inventory", "uniforms.art",
                          "gameplay.executable_patches"})
        rows = {row["id"] for row in game.manifest.registry_document()["capabilities"]}
        self.assertTrue({lane.capability_id for lane in game.lanes} <= rows,
                        "a lane is a claim on a registry row; every one it claims exists")


class RegistryFragmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = REGISTRY_PATH.read_bytes()
        cls.document = json.loads(cls.raw)

    def test_split_then_merge_reproduces_the_canonical_registry_byte_for_byte(self) -> None:
        for game_id in [game["id"] for game in self.document["games"]]:
            with self.subTest(game=game_id):
                core, fragment = registry_merge.split(self.document, game_id)
                merged = registry_merge.merge(core, [fragment])
                self.assertEqual(registry_merge.canonical_bytes(merged), self.raw)

    def test_every_game_as_a_fragment_still_reproduces_the_registry(self) -> None:
        fragments = []
        core = dict(self.document)
        for game_id in [game["id"] for game in self.document["games"]]:
            core, fragment = registry_merge.split(core, game_id)
            fragments.append(fragment)
        self.assertEqual(core["games"], [])
        self.assertEqual(core["capabilities"], [])
        merged = registry_merge.merge(core, reversed(fragments))
        self.assertEqual(registry_merge.canonical_bytes(merged), self.raw)
        validate_registry.validate_data(merged, check_files=False)

    def test_the_merged_document_passes_the_upstream_validator_unchanged(self) -> None:
        core, fragment = registry_merge.split(self.document, "nfl2k5_ps2")
        validate_registry.validate_data(registry_merge.merge(core, [fragment]), check_files=False)

    def test_derived_coverage_equals_the_hand_maintained_surface_games_table(self) -> None:
        derived = registry_merge.coverage(self.document)
        expected = {surface: tuple(sorted(games_)) for surface, games_ in validate_registry.SURFACE_GAMES.items()}
        self.assertEqual(derived, expected)

    def test_the_committed_ps2_fragment_is_the_split_of_the_canonical_registry(self) -> None:
        committed = (ADAPTER_DIR / "registry.fragment.json").read_bytes()
        fresh = registry_merge.fragment_for(self.document, "nfl2k5_ps2")
        self.assertEqual(committed, registry_merge.canonical_bytes(fresh),
                         "the fragment drifted from registry.v1.json; regenerate it or move the row")
        ps2_surfaces = sorted(s for s, g in validate_registry.SURFACE_GAMES.items() if "nfl2k5_ps2" in g)
        self.assertEqual(fresh["surfaces"], ps2_surfaces,
                         "the fragment's declared surfaces are exactly the validator's PS2 widenings")

    def test_merge_refuses_conflicts_and_undeclared_surfaces(self) -> None:
        core, fragment = registry_merge.split(self.document, "nfl2k5_ps2")
        with self.assertRaisesRegex(contract.ContractError, "declared by the core and by a fragment"):
            registry_merge.merge(self.document, [fragment])
        with self.assertRaisesRegex(contract.ContractError, "appears twice"):
            registry_merge.merge(core, [fragment, dict(fragment, game=dict(fragment["game"], id="other"),
                                                       capabilities=[dict(r, game="other") for r in fragment["capabilities"]])])
        lying = dict(fragment, surfaces=[s for s in fragment["surfaces"] if s != "colors"])
        with self.assertRaisesRegex(contract.ContractError, "covers exactly the surfaces it declares"):
            registry_merge.merge(core, [lying])


class GameOwnedPinsTests(unittest.TestCase):
    """The counts test_ps2_lane.py hard-codes live in the game's own pins.json here."""

    def setUp(self) -> None:
        self.game = games.load("nfl2k5_ps2")
        self.pins = self.game.manifest.pins_document()
        self.fragment = self.game.manifest.registry_document()

    def test_pins_match_the_fragment(self) -> None:
        rows = self.fragment["capabilities"]
        self.assertEqual(self.pins["capability_rows"], len(rows))
        self.assertEqual(self.pins["surfaces"], self.fragment["surfaces"])
        hidden = [r for r in rows if r["backend"]["operation"] == "write" and r["surface"] != "saves"]
        self.assertEqual(self.pins["hidden_disc_writers"], len(hidden))
        self.assertEqual(self.pins["save_writer_ids"],
                         [r["id"] for r in rows if r["backend"]["operation"] == "write" and r["surface"] == "saves"])
        self.assertEqual(self.pins["retail_identity"], self.fragment["game"]["retail_identity"])
        self.assertEqual(self.pins["windows"], len(self.game.windows))
        self.assertEqual(self.pins["lanes_on_contract"], len(self.game.lanes))
        self.assertEqual(self.pins["product_modules"], len(self.game.manifest.product_modules))

    def test_allowlist_fragment_mirrors_the_upstream_allowlist(self) -> None:
        fragment = self.game.manifest.allowlist_lines()
        self.assertEqual(self.pins["shipped_files"], len(fragment))
        upstream = [line.strip() for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#")]
        self.assertTrue(set(fragment) <= set(upstream), sorted(set(fragment) - set(upstream)))
        ps2_lines = [line for line in upstream
                     if any(token in line.casefold() for token in ("ps2", "xxh3", "spu_adpcm"))]
        self.assertEqual(list(fragment), ps2_lines, "the fragment is exactly today's PS2 lines, in order")
        for line in fragment:
            self.assertTrue((ROOT / line).is_file(), line)

    def test_runtime_modules_mirror_the_runtime_gate(self) -> None:
        gate = (ROOT / "packaging" / "check_2k5_mod_studio_runtime.py").read_text(encoding="utf-8")
        for name in self.game.manifest.product_modules:
            self.assertIn(f'"{name}",', gate, f"{name} is not in the runtime gate's product_modules")
        product, tools = games.runtime_modules()
        self.assertEqual(len(product), len(self.game.manifest.product_modules))
        self.assertEqual(tools, ())


class BoundaryTests(unittest.TestCase):
    def test_the_adapter_stays_inside_the_contract(self) -> None:
        checks = conformance.check_boundary(ADAPTER_DIR, "mod_editor.games.nfl2k5_ps2")
        self.assertTrue(all(check.passed for check in checks), [c.detail for c in checks])

    def test_a_package_reaching_past_the_contract_is_refused(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="games-boundary-"))
        self.addCleanup(shutil.rmtree, root, True)
        directory = root / "leaky"
        directory.mkdir()
        (directory / "__init__.py").write_text(
            "from mod_editor.games.contract import Refusal\n"
            "import mod_editor.core.providers\n"
            "from mod_editor.gui.studio_qt import launch_studio\n"
            "from mod_editor.games.nfl2k5_ps2 import GAME as OTHER\n"
            "try:\n    from PyQt5.QtWidgets import QDialog\nexcept ImportError:\n    QDialog = None\n"
            "from mod_editor.games._formats.ps2_disc import Ps2DiscIdentifier\n"
            "from . import helper\n",
            encoding="utf-8", newline="\n",
        )
        (directory / "helper.py").write_text("def x():\n    import mod_editor.core.providers\n",
                                             encoding="utf-8", newline="\n")
        [check] = conformance.check_boundary(directory, "mod_editor.games.leaky")
        self.assertFalse(check.passed)
        self.assertIn("mod_editor.core.providers", check.detail)
        self.assertIn("mod_editor.gui.studio_qt", check.detail)
        self.assertIn("mod_editor.games.nfl2k5_ps2", check.detail, "a sibling game is not a format package")
        self.assertIn("PyQt5", check.detail)
        self.assertNotIn("_formats", check.detail, "shared format packages are the sanctioned reuse path")
        self.assertNotIn("helper", check.detail, "function-level imports are lazy and allowed")

    HOOKS = {
        # The File menu's two actions -- the PS2 game's studio and "Select
        # other games…" -- and their handlers.  The studio entry asks the core
        # for the label it shows (chooser.studio_menu_label) and for the window
        # it opens (chooser.open_studio over discover()); it names no module.
        "mod_editor/gui/studio_qt.py": {
            "mod_editor.games",
            "mod_editor.games.chooser",
            "mod_editor.games.chooser_qt",
        },
        # The one command-line seam: --game / --window / --games-chooser.
        "mod_editor/__main__.py": {"mod_editor.games.__main__"},
    }

    def test_upstream_reaches_the_games_package_only_through_the_two_hooks(self) -> None:
        """Passivity, measured: exactly two upstream files import mod_editor.games,
        each importing exactly one core-owned module, lazily.  Every game the
        studio will ever host goes through these two lines; no game is named."""

        found: dict[str, set[str]] = {}
        for path in sorted((ROOT / "mod_editor").rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            if relative.startswith("mod_editor/games/"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module if node.level == 0 else "mod_editor." + node.module]
                for name in names:
                    if name == "mod_editor.games" or name.startswith("mod_editor.games."):
                        found.setdefault(relative, set()).add(name)
                        self.assertNotIn(node, tree.body, f"{relative}:{node.lineno} imports the games package eagerly")
        self.assertEqual(found, self.HOOKS)
        for relative, modules in self.HOOKS.items():
            for module in modules:
                self.assertFalse(module.split(".")[-1].startswith(("nfl2k5", "apf", "madden", "ncaa", "mvp", "nba")),
                                 f"{relative} names a game; the hooks are game-blind")


if __name__ == "__main__":
    unittest.main()

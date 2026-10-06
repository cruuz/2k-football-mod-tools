"""Adversarial integrity gates for the provider execution boundary."""

from __future__ import annotations

# Standalone invocation must not depend on a caller's PYTHONPATH.
import sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]

import ast
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.providers import (
    Apf2k8HelmetColorProvider,
    Apf2k8JerseyColorProvider,
    Apf2k8PantsColorProvider,
    Apf2k8ShoulderColorProvider,
    Nfl2k5ScorebugProvider,
    Nfl2k5UnifiedVisualProvider,
    ProviderError,
    _pinned_execution_bundle,
)
from tests.mod_editor.test_providers import (
    PINNED_SOURCE_SHA,
    apf_request,
    request,
    scorebug_request,
    clean_provider_workspace,
)


WORKSPACE = Path(__file__).resolve().parents[2]


_DEFERRED_BACKEND_IMPORT_SITES = frozenset({
    (
        "mod_editor/core/nfl2k5_audio_catalog.py",
        "replacement_provider",
        "mod_editor.core.nfl_audio_provider",
    ),
})


def _local_module_path(name: str) -> str | None:
    """Resolve a product-package or legacy bare-tools module without init files."""

    product = WORKSPACE.joinpath(*name.split(".")).with_suffix(".py")
    if product.is_file():
        return product.relative_to(WORKSPACE).as_posix()
    if "." not in name:
        tool = WORKSPACE / "tools" / f"{name}.py"
        if tool.is_file():
            return tool.relative_to(WORKSPACE).as_posix()
    return None


def _is_type_checking(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
    ) or (
        isinstance(test, ast.Attribute)
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
        and test.attr == "TYPE_CHECKING"
    )


class _RuntimeImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: list[str] = []
        self.rows: list[tuple[ast.Import | ast.ImportFrom, str | None]] = []

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        if _is_type_checking(node.test):
            for item in node.orelse:
                self.visit(item)
            return
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        self.rows.append((node, self.functions[-1] if self.functions else None))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        self.rows.append((node, self.functions[-1] if self.functions else None))


def _module_name(relative: str) -> str:
    path = Path(relative)
    if path.parts[0] == "mod_editor":
        return ".".join(path.with_suffix("").parts)
    return path.stem


def _absolute_import_names(
    relative: str,
    node: ast.Import | ast.ImportFrom,
) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if node.level == 0:
        if node.module is None:
            return ()
        return (node.module,) + tuple(
            f"{node.module}.{alias.name}"
            for alias in node.names
            if alias.name != "*"
        )

    package = _module_name(relative).rpartition(".")[0]
    parts = package.split(".") if package else []
    keep = len(parts) - (node.level - 1)
    if keep < 0:
        return ()
    base = ".".join(parts[:keep])
    if node.module is not None:
        return ((f"{base}.{node.module}").strip("."),)
    return tuple(
        (f"{base}.{alias.name}").strip(".")
        for alias in node.names
        if alias.name != "*"
    )


def local_import_closure(
    *entries: str,
    exact_path_entries: frozenset[str] = frozenset(),
) -> set[str]:
    """Return the recursive executable local closure, intentionally init-free."""

    pending = [(relative, relative in exact_path_entries) for relative in entries]
    closure: set[str] = set()
    visited: set[tuple[str, bool]] = set()
    while pending:
        relative, exact_path_mode = pending.pop()
        if (relative, exact_path_mode) in visited:
            continue
        visited.add((relative, exact_path_mode))
        closure.add(relative)
        tree = ast.parse((WORKSPACE / relative).read_text(encoding="utf-8"))
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        for node, function in visitor.rows:
            if exact_path_mode and isinstance(node, ast.ImportFrom) and node.level:
                # These four adapters are loaded with a top-level synthetic
                # module name. Their guarded relative product imports cannot
                # resolve; each file's reviewed standalone fallback executes.
                continue
            for name in _absolute_import_names(relative, node):
                if (relative, function, name) in _DEFERRED_BACKEND_IMPORT_SITES:
                    continue
                parts = name.split(".")
                for count in range(len(parts), 0, -1):
                    candidate = _local_module_path(".".join(parts[:count]))
                    if candidate is not None:
                        if (candidate, False) not in visited:
                            pending.append((candidate, False))
                        break
    return closure


class ProviderIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provider_workspace = clean_provider_workspace(cls)
        cls.registry = CapabilityRegistryLoader().load(
            allow_sample_fallback=False, check_files=False
        )

    def test_colour_defaults_load_inside_the_isolated_provider_bundle(self):
        import subprocess
        import sys
        provider = Nfl2k5UnifiedVisualProvider()
        with _pinned_execution_bundle(self.provider_workspace, {**provider.module_pins, **provider.data_pins},
                                      provider.backend_module, "colour settings") as module:
            result = subprocess.run([sys.executable, "-I", "-c",
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from mod_editor.core.nfl2k5_build_settings import build_settings; "
                "from mod_editor.core.nfl2k5_modern_color import default_settings; "
                "assert build_settings({'modern_color_settings': default_settings()})['modern_color_settings']['values']['turf.value_lift'] == 2.8",
                str(module.parents[1])], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_external_writer_and_verifier_import_closures_are_exactly_pinned(self) -> None:
        providers = (
            Nfl2k5UnifiedVisualProvider(),
            Nfl2k5ScorebugProvider(),
            Apf2k8JerseyColorProvider(),
            Apf2k8PantsColorProvider(),
            Apf2k8HelmetColorProvider(),
            Apf2k8ShoulderColorProvider(),
        )
        self.assertEqual(
            [len(provider.module_pins) for provider in providers],
            # The reviewed closure includes the original visual adapters and
            # the integrated music, scorebug, animation and gameplay compilers.
            # The unified visual provider includes standalone/SCNE Crib
            # textures, bounded Crib/Stadium geometry, stock PLAY route copy,
            # formation/play clone writer, fixed-slot audio, the fail-closed
            # AUDO family-label loader, package-local equipment, and every
            # local module in those exact import closures.
            [390, 10, 8, 9, 8, 9]  # dn: + the resource load guard module; cl: + the college references module; mk2: + the official marks module (its catalog is a data pin); ht: + the historic season-roster module and its phase-2 import; b75: + the Edit Player elbow-pad and lineman-rating option patches.
            # b765 integration: + fixed-size spare-capacity owner for dated FA/historic composition.
            # b765-a1: + the Anniversary archive pack, field compiler and their 38 existing venue-tool dependencies.
            # b765-s2: + two explicitly selected field owners and their complete reviewed 38-module source closure.
            # b76-pk3: + the file-pack reader/writer imported by modpack.
            # b76-sd2: + the finite lineup iterator and final disc-extent guard.
            # b76-e2p3: + the historic moment venue names.
            # b76 p1: + the GAMEDATA presentation inventory (typed p8:346 marks).
            # b76-z2: + the xemu display-list stability fix.
            # b76-h1: + historic teams in Quick Game and its generated code.
            # b76-m1: + 25 more Anniversary moments, its generated code and the One-pool reclassify it reuses.
            # b76-vb3: + the 25th Anniversary kickoff gate and the two readers of the disc's retail special-teams
            # data it imports (the core return-play module and the kickoff alignment tool).
            # b76-k1: + 128 MB memory (K128) and the roster block in the extra heap.
            # b76-vb3 E1: + the kickoff return blocking rule the gate carries.
            # b76-vb3 D2: + the 4:3 widescreen menus owner.
            # b76-u3 A: + the 2026 team names module (the scorebug guard recognizes its colour rows).
            # b76-hm: + Modern helmets (the Guardian collection and the historic rosters read its states).
            # DESIGN: fc adds the guarded economy owner and its original generated code.
            # b76-pb (ig): + the complete-offense compiler, the authored-screen D pins and the native play-scoring gate.
            # b76-fc3 (ig): + the roster-fill composition module the economy and the practice squad share.
            # b76-pf P1: + the team-logo swap owner (the field swap's eighth pair).
            # b76 G (ig): pc + the play-call layout the scorebug runtime imports; ed2 + the roster snapshot reader and the
            # save writer it imports; fr + the franchise history owner and the career-stats module it imports; ed1 + the
            # project manifest budget/recovery reader the project archive imports.
        )
        for provider in providers:
            entries = [provider.backend_module]
            verifier = getattr(provider, "verifier_module", None)
            if verifier:
                entries.append(verifier)
            expected_closure = local_import_closure(*entries)
            if isinstance(provider, Nfl2k5UnifiedVisualProvider):
                # The backend directly imports reviewed product audio modules
                # and dynamically loads the reviewed adapters by exact path.
                # Both package init files stay absent so their unrelated eager
                # GUI/provider imports cannot escape the finite pin closure.
                adapters = frozenset({
                    "mod_editor/core/nfl2k5_anniversary_pack.py",
                    # Studio dynamically selects these reviewed field owners after surface compilation.
                    "mod_editor/core/nfl2k5_midfield_art.py",
                    "mod_editor/core/nfl2k5_split_endzone_art.py",
                    "mod_editor/core/nfl2k5_momentum.py",
                    "mod_editor/core/nfl2k5_momentum_code.py",
                    "mod_editor/core/nfl2k5_defensive_try.py",
                    "mod_editor/core/nfl2k5_zone_drop.py",

                    "mod_editor/core/nfl2k5_guardian_cap.py",
                    "mod_editor/core/nfl2k5_animation.py",
                    "mod_editor/core/nfl2k5_animation_math.py",
                    "mod_editor/core/nfl2k5_scorebug_runtime.py",
                    "mod_editor/core/nfl2k5_scorebug_resources.py",
                    "mod_editor/core/nfl2k5_scorebug_ingame.py",
                    "mod_editor/core/nfl2k5_music_policy.py",
                    "mod_editor/core/nfl2k5_music_catalog.py",
                    "mod_editor/core/nfl2k5_music_build.py",
                    "mod_editor/core/nfl2k5_music_banks.py",
                    "mod_editor/core/nfl2k5_music_metadata.py",
                    "mod_editor/core/nfl2k5_music_storage.py",
                    "mod_editor/core/nfl2k5_music_archive.py",
                    "mod_editor/core/nfl2k5_xbe_space.py",
                    "mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py",
                    "mod_editor/core/nfl2k5_season_cap.py",
                    "mod_editor/core/nfl2k5_screen_timing.py",

                    "mod_editor/core/nfl2k5_audo_fixed_slots.py",
                    "mod_editor/core/nfl2k5_safe_text_banks.py",
                    "mod_editor/core/nfl2k5_scorebug_unified_adapter.py",
                    "mod_editor/core/nfl2k5_stadium_texture_writer.py",
                    "mod_editor/core/nfl2k5_p8_texture_writer.py",
                    "mod_editor/core/nfl2k5_unif_color_writer.py",
                    "mod_editor/core/nfl2k5_uniform_equipment_writer.py",
                })
                expected_closure.update(local_import_closure(
                    *adapters, exact_path_entries=frozenset({
                        "mod_editor/core/nfl2k5_audo_fixed_slots.py",
                        "mod_editor/core/nfl2k5_safe_text_banks.py",
                        "mod_editor/core/nfl2k5_scorebug_unified_adapter.py",
                        "mod_editor/core/nfl2k5_stadium_texture_writer.py",
                        "mod_editor/core/nfl2k5_p8_texture_writer.py",
                        "mod_editor/core/nfl2k5_unif_color_writer.py",
                        "mod_editor/core/nfl2k5_uniform_equipment_writer.py",
                    })
                ))
                self.assertNotIn("mod_editor/__init__.py", expected_closure)
                self.assertNotIn("mod_editor/core/__init__.py", expected_closure)
                self.assertNotIn("mod_editor/core/providers.py", expected_closure)
                self.assertEqual(len(provider.module_pins), len(expected_closure))
            self.assertEqual(set(provider.module_pins), expected_closure)
            for relative, expected in provider.module_pins.items():
                path = WORKSPACE / relative
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.stat().st_nlink, 1)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

        unified = providers[0]
        self.assertEqual(
            unified.data_pins,
            {
                "mod_editor/data/nfl2k5_free_agents_2026.v1.json": "c89b19a91e01677c250f0827034c19129251b04cdd30cf84c3524f1aac92c443",
                "data/espn25_previews_2026.json": "8ae83e55f9ad9cc5a9fa1f5ed0efe4c0802522b7332c5ef3e3b594ca472e287c",
                "data/nfl2k5_moment_venues.json": "960f1f61f5395ce65117b32840f38f28dcb31fbbc1e793eda9dc39c7853b5fb0",
                "data/nfl2k5_era_rules.json": "fab269783f2f4524b01e031a15de8156629a6728d86249b9402822594778d1e4",
                "data/nfl2k5_stock_books.json": "87d779bb2be3c4b20b901c4afa0a620bb4b0aae29ef833bc4440a38c396417fd",
                "data/nfl2k5_modern_color_pins.json": "cf61e48211eba21152501bee6b20666f24663b0d18cfc0d2b2975dd8c45afacf",
                "data/nfl2k5_modern_helmets/geometry.json": "3bd4a970dd27a614040c307fcca3f66e4a83fef6d008a8efa1384e4b76ef0c7a",
                "data/nfl2k5_modern_helmets/pins.json": "6f4c8816369aec0087b52df23b2ae62a2fe1312817a118eeaade5ab52bd51a28",
                "data/nfl2k5_presentation_standalone.json": "69e6589ffbdda17fc3a5f3b9201ffc206bd0c347e54596b38a88cfeb1d454f36",
                "data/nfl2k5_official_marks_catalog.json": "36f83b0ef43441c834c7abc17834d70b426e704d4cc8c9b77044d2b685698cf3",
                "mod_editor/data/nfl2k5_crib_catalog.v1.json": "c78801144df2f070e003ba458c5affa15a52cc00221cc1a3d9983f1fbf172cd8",
                "mod_editor/data/nfl2k5_equipment_chain_pins.v1.json": "1057ef17a6680edf64d83ce563f168e5c6850c63c7b212423d70486838591295",
                "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json": "fa2c9ca9bcc267b6981735347bf6daf6243d6ab8b83fba268804c280cfd94173",
                "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json": "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa",
                "reports/specs/nfl2k5_crib_static_position_targets.v1.json": "90f955166c8582f7041bd0d936bacbef1f44b3869487f71535acec1caeb44b4f",
                "data/nfl2k5_ratings_forty_sources.json": "39cc65634bfafab8b37817129be309e85f73f35ef7eb5f1f0b2472e5632d5817",
                "data/nfl2k5_espn25_more_teams/teams.json": "0484cc4ea617f4d250571ac3551f820368a15456c444326203d31c98eebd8cd3",
                "data/nfl2k5_espn25_more_teams/manifest.json": "e95e94e6e0a6b4cb23ceaefe565911ef313c0b817d55fc7da6ea4795403c05f9",
                "data/nfl2k5_espn25_more_moments_appearance.json": "2397399d6681a1c05f7e1287d3e4e83ff710e4fdc40b759621593a296643e3f3",
                "data/nfl2k5_espn25_more_moments.json": "3bc2a20c68cbc262b105b0bde11c6c8d1c39e6d21bed84cba9514af00c689870",
                "data/nfl2k5_espn25_fields/source/nfl_2008.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/source/nfl_2008_source.png": "6b8162747a0a58998b342a3a351ba5efbe70cb6ce1350889db9656e74514b119",
                "data/nfl2k5_espn25_fields/source/manifest.json": "8b1addd0e0b8c392519b40cf661e3a65cfcaa4e3267c1c4a326ff316bfec6588",
                "data/nfl2k5_espn25_fields/source/den_wordmark_1968_1996.png": "45249c2c87f229cd89d513a5e009d0a0a967dbb15f076637e8a1343257ad833c",
                "data/nfl2k5_espn25_fields/source/den_1968_1996.png": "4e8cd3f37ee15539b086f157a6835b9986e648f8124fac4a8368579a11777030",
                "data/nfl2k5_espn25_fields/row51/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row51/endzone_S.png": "7d3eb92c5b89ea2c4ba0df1b9fc6031742110f4c84ad9fff4dfeb57a1b2baec1",
                "data/nfl2k5_espn25_fields/row51/endzone_N.png": "7d3eb92c5b89ea2c4ba0df1b9fc6031742110f4c84ad9fff4dfeb57a1b2baec1",
                "data/nfl2k5_espn25_fields/row51/center_logo.png": "faa151e8d922c6dfbb37394b0b6d5b556dccbf02002cd11e57fadc6b0caed840",
                "data/nfl2k5_espn25_fields/row50/playoff_logo.png": "035321f7b260488a6ecaba93cc54814649ac7f1bfa7d3d53dd090de233aab1a4",
                "data/nfl2k5_espn25_fields/row50/endzone_S.png": "ad3ebe4d1bd9682f34dfba8a75f9072021fcdc3122daee16cf9242e4ac6ecae9",
                "data/nfl2k5_espn25_fields/row50/endzone_N.png": "b4e3b58d35b03ac6699a2c1240682348eb44869af21def2a4ced00daa2d18706",
                "data/nfl2k5_espn25_fields/row50/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/row49/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row49/endzone_S.png": "fd330f882c387324a911944fbdcd79b3b79b4d25c11e7b555045f06e99aec912",
                "data/nfl2k5_espn25_fields/row49/endzone_N.png": "fd330f882c387324a911944fbdcd79b3b79b4d25c11e7b555045f06e99aec912",
                "data/nfl2k5_espn25_fields/row49/center_logo.png": "7b0b9bfd168c22f023133e6def7c0140d335a6c45ed099d00586235b78ee0d32",
                "data/nfl2k5_espn25_fields/row48/playoff_logo.png": "571c2e2fbad7c51f10bf7807afce6f0ce929d6461b2c339cd100507296b1b8cb",
                "data/nfl2k5_espn25_fields/row48/endzone_S.png": "d3a999474e89240e6bdc96ad77a5a0a87a0820c97ab4b50c7e7c7106ee928bd9",
                "data/nfl2k5_espn25_fields/row48/endzone_N.png": "956e4ef615779c0fccba65d6983ac709130820732e06325f1299852a5b4b9499",
                "data/nfl2k5_espn25_fields/row48/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/row47/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row47/endzone_S.png": "c6852cd5f76a924924875a1e0f1d026d753cf3b4fe033317d4fc8d0382bdb328",
                "data/nfl2k5_espn25_fields/row47/endzone_N.png": "618858132efada63436afbf3f10bd8af2df65e128fcd1deaaa26b6da790d5596",
                "data/nfl2k5_espn25_fields/row47/center_logo.png": "4d4f617af92995f9d93102a1f572419d6738763ac0376070f08ebceb17da8e0b",
                "data/nfl2k5_espn25_fields/row46/playoff_logo.png": "d2135e57222ad2f0df936dc9a748994f41b74e3011abe5efaf27878ff1484b03",
                "data/nfl2k5_espn25_fields/row46/endzone_S.png": "50a719f19e985acb0f5e6ffae446d989278567577bca634d53f8479da584aa1a",
                "data/nfl2k5_espn25_fields/row46/endzone_N.png": "06ba6c33051b188c72229cad481880f532c92406c8ab0d21983a2a4c73e97844",
                "data/nfl2k5_espn25_fields/row46/center_logo.png": "22c0a79706a3642e580d5a36bd5ce3c20301aefbe64c50dca2561f566d07811f",
                "data/nfl2k5_espn25_fields/row45/playoff_logo.png": "be22410453acbbeff81e09de8b548c943e4d35a8a3cc8f586f6eca8f0a706df3",
                "data/nfl2k5_espn25_fields/row45/endzone_S.png": "af98b4fcf27929e1b59c9b849d0fdeb7ca2a5c6e2efd3e1bc7eb14a5f29011e3",
                "data/nfl2k5_espn25_fields/row45/endzone_N.png": "7c573abe809a76663b89b03ca24f81f091e3bb4e516b9f62a38bb86176fc29c2",
                "data/nfl2k5_espn25_fields/row45/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/row44/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row44/endzone_S.png": "3e89cce2a482a9b8e2b014f03d080680ad7cc0dccf2efbf8c203345a1880d3e5",
                "data/nfl2k5_espn25_fields/row44/endzone_N.png": "c78b63e95e668741132f8887afe25970ac2290abe56d93bf08bc7e1e68660f21",
                "data/nfl2k5_espn25_fields/row44/center_logo.png": "7b0b9bfd168c22f023133e6def7c0140d335a6c45ed099d00586235b78ee0d32",
                "data/nfl2k5_espn25_fields/row43/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row43/endzone_S.png": "ecd56f8f93af9a056156797b7c97ad2dba9185b918e5529d99d26a2cb645bbce",
                "data/nfl2k5_espn25_fields/row43/endzone_N.png": "ecd56f8f93af9a056156797b7c97ad2dba9185b918e5529d99d26a2cb645bbce",
                "data/nfl2k5_espn25_fields/row43/center_logo.png": "659161efd63caad98b98095c58c0feda8ba9d99ddf99b0f061704240d245c2e2",
                "data/nfl2k5_espn25_fields/row42/playoff_logo.png": "bd8d10d6bd2ee0ed7a6206f3ca84941e93915cc854218a9bddd9f36ed8d3f729",
                "data/nfl2k5_espn25_fields/row42/endzone_S.png": "b464c1af50b1fac10dda0ccd7eef841e505ea81c0947ba9a83189f04f4564b0f",
                "data/nfl2k5_espn25_fields/row42/endzone_N.png": "9892b7209497c580ea413484c0c567e1b7bc87f40062a93bd29360b6cdae3f15",
                "data/nfl2k5_espn25_fields/row42/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/row41/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row41/endzone_S.png": "8f308c45ae9bb0e2de5ced49400ac7c3293994d6299bbfab9c615c9f40796a73",
                "data/nfl2k5_espn25_fields/row41/endzone_N.png": "42d424e1ad75b5196a60e8aa6bb7a1fcab4c1e0e3af289a2838f65cbaa669364",
                "data/nfl2k5_espn25_fields/row41/center_logo.png": "e708e2111962c122369974fa58ea20d2016011419753354dbef917917c33ef39",
                "data/nfl2k5_espn25_fields/row40/playoff_logo.png": "09d50edbcb46ed497c9a5797779e88ab7f43dc0880a51e1d58a8fd68a2091eeb",
                "data/nfl2k5_espn25_fields/row40/endzone_S.png": "0ef7eb9986c436918e67a7a86c4a090db7395e2fa48cdcaa93f45f9b536b27d5",
                "data/nfl2k5_espn25_fields/row40/endzone_N.png": "0e45d24a19d3e0ed0293e66055d37f1e7f3e247a8a6730f043d9339a78cdd65b",
                "data/nfl2k5_espn25_fields/row40/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/row39/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row39/endzone_S.png": "a01e17bec7bebb0acdc3686f7cd489743ffafb17b5f0c318ddc60712731d1d94",
                "data/nfl2k5_espn25_fields/row39/endzone_N.png": "7d3e884df42ebaf738328c8be1d2b2256277d51ab7f75d89eaf372c21c15330f",
                "data/nfl2k5_espn25_fields/row39/center_logo.png": "1a9a1b499ada786b67122e7e54b1d71cacc1e11693f2848d9e652c389877fc77",
                "data/nfl2k5_espn25_fields/row38/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row38/endzone_S.png": "75d87dd14b8f824f34f246ea0ba2b0057e3c2a6614cbc6f6fb70003abe40019c",
                "data/nfl2k5_espn25_fields/row38/endzone_N.png": "d18dd00877c7be5f2097b1c56b8b599192e38942069a807ba80d7a5b7d96ad0d",
                "data/nfl2k5_espn25_fields/row38/center_logo.png": "6d6c95a7a16b664da3797b20985352ea06a7e1ffe10dbb35b7a74b0cfcd8ca02",
                "data/nfl2k5_espn25_fields/row37/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row37/endzone_S.png": "51911f4f533b030699729faec5ae1bab4939876415510f529b1302e393c576f9",
                "data/nfl2k5_espn25_fields/row37/endzone_N.png": "51911f4f533b030699729faec5ae1bab4939876415510f529b1302e393c576f9",
                "data/nfl2k5_espn25_fields/row37/center_logo.png": "03bf5a691e88e919520a1ecc40b975cf3196437764a69c0742fb9a90fafe78a5",
                "data/nfl2k5_espn25_fields/row36/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row36/endzone_S.png": "1fee175614c51ff839de63d583d4d9c91c621ade4d2eca88dd2116b003ff9ba6",
                "data/nfl2k5_espn25_fields/row36/endzone_N.png": "1fee175614c51ff839de63d583d4d9c91c621ade4d2eca88dd2116b003ff9ba6",
                "data/nfl2k5_espn25_fields/row36/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/row35/playoff_logo.png": "57ec2ba76d21f89f36baac87d28f7cffa92fa25a8e660045a666e115e5ce79c3",
                "data/nfl2k5_espn25_fields/row35/endzone_S.png": "f76c0a982017212d7ca5a5c387dac5c22f700712b51035b5263eac82c08110f3",
                "data/nfl2k5_espn25_fields/row35/endzone_N.png": "a3b5117e5d22b0a75eac01d9440069179e8ba99dd4f8a50e277f76177e9fa6a0",
                "data/nfl2k5_espn25_fields/row35/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/row34/playoff_logo.png": "8f9999e96b5bc292baa8569b362878be17092ccde7600d23d04fb3f0520ba10b",
                "data/nfl2k5_espn25_fields/row34/endzone_S.png": "9977ce085702a660d2179b351f47c1f769b0f10fb774a2adb4b3cad19352e77e",
                "data/nfl2k5_espn25_fields/row34/endzone_N.png": "bc09b4b44e39f100a94621b4daa1fe09e44ed4a93e020c2da631602646570af1",
                "data/nfl2k5_espn25_fields/row34/center_logo.png": "8795cf7d2e2314e41389ec6f9c19518d907e641da3c4c581c96a6db44f2e34e7",
                "data/nfl2k5_espn25_fields/row33/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row33/endzone_S.png": "9ce33fb27005df9209e329d4858c64043777cc93e64c0a67a213c6e4c5d0ab96",
                "data/nfl2k5_espn25_fields/row33/endzone_N.png": "4c55fcad6beed6e7e41edebb4c7a8ad0e4d30583e69c4c5d7bd67fa916f988cc",
                "data/nfl2k5_espn25_fields/row33/center_logo.png": "ee725a47f32d9127a24b7bfd8414a20aabe0ace5ead9f266d2b5330fe2c76bc2",
                "data/nfl2k5_espn25_fields/row32/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row32/endzone_S.png": "e5e59b90790ad84dc90ecff2aa02c5f94dd66bbcf746081936b8f9f52ff7149b",
                "data/nfl2k5_espn25_fields/row32/endzone_N.png": "116659760ce5ecc7bf8367125ca48510bb8db428e7e59db2dc7f0c44cfb24db1",
                "data/nfl2k5_espn25_fields/row32/center_logo.png": "5632834fda06dc6e611e64d1ab914ba9bdd28b19173f9d91fa03cccdaefffd31",
                "data/nfl2k5_espn25_fields/row31/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row31/endzone_S.png": "3cbc6957f97a3e8895a7e68e6df6c4af77ae1321f65d5e79c253b726acb811dc",
                "data/nfl2k5_espn25_fields/row31/endzone_N.png": "3cbc6957f97a3e8895a7e68e6df6c4af77ae1321f65d5e79c253b726acb811dc",
                "data/nfl2k5_espn25_fields/row31/center_logo.png": "4cc83cb4a3d044a48cd48693936d119c2a94c606a7d677c8663d54b66f565678",
                "data/nfl2k5_espn25_fields/row30/playoff_logo.png": "2d08eb5dc662bcfbb7d821039125d31cab6ff9527b8f4716cf325944251940fb",
                "data/nfl2k5_espn25_fields/row30/endzone_S.png": "b603e57c8870a9c2f63b4bd6d60b991e4b36399cf2144e111e8598fbd0b0f530",
                "data/nfl2k5_espn25_fields/row30/endzone_N.png": "0fd248e8435ae24caa00cb5db803991e42ac44e57274c8cf92b40b4fb3d9efd9",
                "data/nfl2k5_espn25_fields/row30/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/row29/playoff_logo.png": "a8a872758f2f970c21fd7ec606002715613406a1e8fa15b0bcbbea2514e58bb8",
                "data/nfl2k5_espn25_fields/row29/endzone_S.png": "d496174600b16f8090aaebb3d4bb7493d11596f8c7a011df9b5fd52304d6805a",
                "data/nfl2k5_espn25_fields/row29/endzone_N.png": "0e102f9f9787490dcbe7ca69f53adcddce99243af94e5647e72cd753d8771ac2",
                "data/nfl2k5_espn25_fields/row29/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/row28/playoff_logo.png": "8745e73577c0ffcf315ea4a73d38b44745e8ccf39b2d8ffa2f5f8cf70d42e935",
                "data/nfl2k5_espn25_fields/row28/endzone_S.png": "c939a90032ad4d4471531e6331827d61809633060f3a7a9a624f133dadc0f53a",
                "data/nfl2k5_espn25_fields/row28/endzone_N.png": "68b9b03fccd9513c4c017cbf849621c21a48e39d5f88390dbd6f54c957a57cbd",
                "data/nfl2k5_espn25_fields/row28/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
                "data/nfl2k5_espn25_fields/row27/playoff_logo.png": "6e894eb32b38230931a622e992aa03a06f7f40590ca44a0371189bc590a7cfe5",
                "data/nfl2k5_espn25_fields/row27/endzone_S.png": "190a4c9c61361b2b4fbaea07eb76984afda78d16401b7e2311c3c22addc8ae10",
                "data/nfl2k5_espn25_fields/row27/endzone_N.png": "efeca1f6d55386370276893f7125282228ed5fb622f60ca84b6047a5c3876ab5",
                "data/nfl2k5_espn25_fields/row27/center_logo.png": "8795cf7d2e2314e41389ec6f9c19518d907e641da3c4c581c96a6db44f2e34e7",
                "data/nfl2k5_espn25_fields/row26/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row26/endzone_S.png": "f79d84a6b1af61d9ba4120918b2d8bd3bf3cdc0645cd455f93a896c0c91724e2",
                "data/nfl2k5_espn25_fields/row26/endzone_N.png": "19c06c07cd3d065350404b7290a983205e6010408f34ffaa5672463dab3be630",
                "data/nfl2k5_espn25_fields/row26/center_logo.png": "3a313ff9757e05cccffc4c35f864df76480d8431a4d3419f353cd570f86adf33",
                "data/nfl2k5_espn25_fields/row25/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row25/endzone_S.png": "688d7a50a6b99c9571c069213579148d43d85fd44bf1cc48cad642a04ece99a6",
                "data/nfl2k5_espn25_fields/row25/endzone_N.png": "688d7a50a6b99c9571c069213579148d43d85fd44bf1cc48cad642a04ece99a6",
                "data/nfl2k5_espn25_fields/row25/center_logo.png": "4305f33bb9eb01e314d944a0a9fdb6f45a9109bd2c3ae1f983d69b6b664e1b62",
                "data/nfl2k5_espn25_fields/row24/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row24/endzone_S.png": "98bdeb7e258ff0fedbd32a41969bd1a68d1452042ffdb92ce52f9a554307d5ac",
                "data/nfl2k5_espn25_fields/row24/endzone_N.png": "98bdeb7e258ff0fedbd32a41969bd1a68d1452042ffdb92ce52f9a554307d5ac",
                "data/nfl2k5_espn25_fields/row24/center_logo.png": "6d6c95a7a16b664da3797b20985352ea06a7e1ffe10dbb35b7a74b0cfcd8ca02",
                "data/nfl2k5_espn25_fields/row23/playoff_logo.png": "53e7d8a3488bec7ddb88e8fbcdd618d3c1e3b918b2ed3fbef45bbaf65ec10b5f",
                "data/nfl2k5_espn25_fields/row23/endzone_S.png": "cd55dd7948c3ddebee8b96b27ba183a114f35f57c757e319e1bdb6787739e2a0",
                "data/nfl2k5_espn25_fields/row23/endzone_N.png": "e828bcc77f166efd379ff7c3b9244b4505595d64c6322cf018855f6fa4172214",
                "data/nfl2k5_espn25_fields/row23/center_logo.png": "4041219e07916001f1fa1f1276ca8995c021e53057dee6579c1373a18c607947",
                "data/nfl2k5_espn25_fields/row22/playoff_logo.png": "59bd9acecf82110a85ea42a836745822c3b8fe187260ed9f6cec7120e264d7fc",
                "data/nfl2k5_espn25_fields/row22/endzone_S.png": "aa8c70cc1824f59330e6b9d12802be50e0492a2451ebd85ff91df0af6b1e8fe9",
                "data/nfl2k5_espn25_fields/row22/endzone_N.png": "52a759c5f8bc972085e8fc673f50b6e913dcbb97214bdc47e9ef872d699b2426",
                "data/nfl2k5_espn25_fields/row22/center_logo.png": "7b53b041f70897eb02b6d6830cc1be105b39ec32b54a587ea456a7e0c2b33769",
                "data/nfl2k5_espn25_fields/row21/playoff_logo.png": "1458018501bc5d4967ec5442b0d6510eb1481047d055d18abf89d000b282b5de",
                "data/nfl2k5_espn25_fields/row21/endzone_S.png": "cfd689926a1df35948c10b4d08ee5e8b77f496444e44694da2638f53d93b2035",
                "data/nfl2k5_espn25_fields/row21/endzone_N.png": "29be3b298b4e221f85a5d81ba3387d7ebdcfe59a2e369b80ebb3a8d9f0df9a23",
                "data/nfl2k5_espn25_fields/row21/center_logo.png": "92cb3644b95a4e52eb713f16fff8cd6b0f3b505a9c0d2a07f234262d1106b141",
                "data/nfl2k5_espn25_fields/row20/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row20/endzone_S.png": "c0b088ff52d722f4cb261dec97fe776acdba87a76dbfe6c3f4eaf28985da7f07",
                "data/nfl2k5_espn25_fields/row20/endzone_N.png": "ed526e17094387b211bf42973922b926902597c0c0d194940e909b4b46591873",
                "data/nfl2k5_espn25_fields/row20/center_logo.png": "2c096e8848378b195ae33e86efbac90cc45d77148205680e429d7fa3940b5397",
                "data/nfl2k5_espn25_fields/row19/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row19/endzone_S.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
                "data/nfl2k5_espn25_fields/row19/endzone_N.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
                "data/nfl2k5_espn25_fields/row19/center_logo.png": "c956057054db08e1bb6f64ba376df5c04d2b6b5b1647e22bf40157235e9583cd",
                "data/nfl2k5_espn25_fields/row18/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row18/endzone_S.png": "c0b088ff52d722f4cb261dec97fe776acdba87a76dbfe6c3f4eaf28985da7f07",
                "data/nfl2k5_espn25_fields/row18/endzone_N.png": "ed526e17094387b211bf42973922b926902597c0c0d194940e909b4b46591873",
                "data/nfl2k5_espn25_fields/row18/center_logo.png": "2c096e8848378b195ae33e86efbac90cc45d77148205680e429d7fa3940b5397",
                "data/nfl2k5_espn25_fields/row17/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row17/endzone_S.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
                "data/nfl2k5_espn25_fields/row17/endzone_N.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
                "data/nfl2k5_espn25_fields/row17/center_logo.png": "c956057054db08e1bb6f64ba376df5c04d2b6b5b1647e22bf40157235e9583cd",
                "data/nfl2k5_espn25_fields/row16/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row16/endzone_S.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
                "data/nfl2k5_espn25_fields/row16/endzone_N.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
                "data/nfl2k5_espn25_fields/row16/center_logo.png": "c956057054db08e1bb6f64ba376df5c04d2b6b5b1647e22bf40157235e9583cd",
                "data/nfl2k5_espn25_fields/row15/playoff_logo.png": "bd1f3db9f201822293f52dc0929d6e2fd62d6c06b391789f4b122b58f82ab42d",
                "data/nfl2k5_espn25_fields/row15/endzone_S.png": "26004ccd163f9e20014fb68cf094bfa1449c9869989ac43b3e9fb6750b81caa5",
                "data/nfl2k5_espn25_fields/row15/endzone_N.png": "7ed33ab918ee2275f84d7fb57cba68bcf3de5515d9c391f03ee1fbdf7e36c60f",
                "data/nfl2k5_espn25_fields/row15/center_logo.png": "609b9479ef1033e4c361df7edb28272c789fb45c0a7a8b7f429bd9be1a7d5122",
                "data/nfl2k5_espn25_fields/row14/playoff_logo.png": "73067442898187e2fe0e01bd154266897b1b7b48bd71177dfc0f1bb33851ad74",
                "data/nfl2k5_espn25_fields/row14/endzone_S.png": "88959788326a55e07943abc9b10f206402078e4fd7e110c35a71af3d3ee70304",
                "data/nfl2k5_espn25_fields/row14/endzone_N.png": "26f2900788884f66ab13ecd7f3638e6ab6a3baee99c28e14a3049b6c295bbb86",
                "data/nfl2k5_espn25_fields/row14/center_logo.png": "8795cf7d2e2314e41389ec6f9c19518d907e641da3c4c581c96a6db44f2e34e7",
                "data/nfl2k5_espn25_fields/row13/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row13/endzone_S.png": "94f9d868b85b78746e176b47fbc476422df63f0a05be559629f46d3bd91d33b6",
                "data/nfl2k5_espn25_fields/row13/endzone_N.png": "94f9d868b85b78746e176b47fbc476422df63f0a05be559629f46d3bd91d33b6",
                "data/nfl2k5_espn25_fields/row13/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/row12/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row12/endzone_S.png": "14a115bdaa4d5957b4c5ffeefb17733de3ecdfa67e845e8f6db753379d58b844",
                "data/nfl2k5_espn25_fields/row12/endzone_N.png": "14a115bdaa4d5957b4c5ffeefb17733de3ecdfa67e845e8f6db753379d58b844",
                "data/nfl2k5_espn25_fields/row12/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/row11/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row11/endzone_S.png": "2b1aab048e8775d954ecf404bda54da9289a0de4427fcd2340a05cb0fdd1f292",
                "data/nfl2k5_espn25_fields/row11/endzone_N.png": "322eefd24e0fa8f201ec3f4ff0d7f6b339d52383d81508cc108109473337b24a",
                "data/nfl2k5_espn25_fields/row11/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/row10/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row10/endzone_S.png": "ef01cb09f101c5d36b67d907721827958eabfe107604525d991dc50bbf48c199",
                "data/nfl2k5_espn25_fields/row10/endzone_N.png": "ef01cb09f101c5d36b67d907721827958eabfe107604525d991dc50bbf48c199",
                "data/nfl2k5_espn25_fields/row10/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/row09/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row09/endzone_S.png": "cb3be6e910723f61f98b590d7aa776e45de85a6cb923393190e21ef517af84f2",
                "data/nfl2k5_espn25_fields/row09/endzone_N.png": "3e2898d4d793483906ae8b7a88552137f2097d3b9641377855ed4795ceafa439",
                "data/nfl2k5_espn25_fields/row09/center_logo.png": "4124084c42bd24cc6af2919b80b1c77e4d4bf62b8fc3c9b9bf3f07e18b1135a5",
                "data/nfl2k5_espn25_fields/row08/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row08/endzone_S.png": "c03c94821d6c561b6a636d92fce0de6d81a42c02139d365d52559b8af9245577",
                "data/nfl2k5_espn25_fields/row08/endzone_N.png": "c03c94821d6c561b6a636d92fce0de6d81a42c02139d365d52559b8af9245577",
                "data/nfl2k5_espn25_fields/row08/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/row07/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row07/endzone_S.png": "26954570a83d7df4bf3631cecc53877b191aac991f3d6ea5d13a067ad87c2425",
                "data/nfl2k5_espn25_fields/row07/endzone_N.png": "26954570a83d7df4bf3631cecc53877b191aac991f3d6ea5d13a067ad87c2425",
                "data/nfl2k5_espn25_fields/row07/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/row06/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row06/endzone_S.png": "8708e20aaef8baf8aad45b38839290da0e660da8c495fd055f30ed4143f2643d",
                "data/nfl2k5_espn25_fields/row06/endzone_N.png": "487d4f827ca5bed40fd332e10cd1d93a80a503da03453f28cede8ee0bd441ff8",
                "data/nfl2k5_espn25_fields/row06/center_logo.png": "1427e0e1a617bf3e0d2ab0804dc8697bc60e1601d0248e9e31407fa4c9df1aa8",
                "data/nfl2k5_espn25_fields/row05/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row05/endzone_S.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
                "data/nfl2k5_espn25_fields/row05/endzone_N.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
                "data/nfl2k5_espn25_fields/row05/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/row04/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row04/endzone_S.png": "d663ac7e95f6f10900421707723971b839539de9593b1771610d43262324138e",
                "data/nfl2k5_espn25_fields/row04/endzone_N.png": "3bc7d4419a3e7f2c5b80e04e4cbfd07300a706cc174fdc4d09b23a1f2f5766a5",
                "data/nfl2k5_espn25_fields/row04/center_logo.png": "912db95cd096b6199ac3c21500cc5b3fd3554ff241c729bd71fc8f89a0a572b9",
                "data/nfl2k5_espn25_fields/row03/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row03/endzone_S.png": "a8d9521e6aaee5eb8024e8323850bb3547e580cac29818445293ddded6b78f1c",
                "data/nfl2k5_espn25_fields/row03/endzone_N.png": "ebebbe97f639a91083adc740cc6dcac2d95606813fb09933e5e84662ce1ce071",
                "data/nfl2k5_espn25_fields/row03/center_logo.png": "f9559b5717fe3aaa4d4a8374c548ef12a33b5016bef5de7f5a2c5eabdb165732",
                "data/nfl2k5_espn25_fields/row02/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row02/endzone_S.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
                "data/nfl2k5_espn25_fields/row02/endzone_N.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
                "data/nfl2k5_espn25_fields/row02/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/row01/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row01/endzone_S.png": "bbc041dff4441c99eb2323161cca7eb2a5c4bb103036e7d0b382b71928790d2d",
                "data/nfl2k5_espn25_fields/row01/endzone_N.png": "bbc041dff4441c99eb2323161cca7eb2a5c4bb103036e7d0b382b71928790d2d",
                "data/nfl2k5_espn25_fields/row01/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/manifest.json": "f0702f9f6b9758a632a308e86310b1ad0b853d8a64752c77753a46233ad8b141",
                "data/nfl2k5_espn25_fields/source/nfl100.png": "e5492f431984e885ba5e927e747a6716f39755ae3f078e3ac3714ca84b3dd41b",
                "data/nfl2k5_espn25_fields/source/row03_center.png": "add4deaffc840b722d98c7bd91cb6286a165a8de922d160c601823e556f6f53e",
                "data/nfl2k5_espn25_fields/source/row03_endzone_N.png": "f3c15f0bb902d97950f48de236c30a911012d60a5fbb03f0ef9ce09a0107fe14",
                "data/nfl2k5_espn25_fields/source/row03_endzone_S.png": "aec7eafc5c01bc99a389e3b59c3098f0b045f3fb51d58ac61ddf3808e08a9e96",
                "data/nfl2k5_espn25_fields/source/row04_center.png": "b86a10f3569bd9f91f0ceed8c3a1a4ded49e5e3323ab25a19037d482b9cd4d3b",
                "data/nfl2k5_espn25_fields/source/row04_endzone_N.png": "e109b337b8364015b9edc9410787e4a0a5fdb2fc19e20afb129a967dbe9087ca",
                "data/nfl2k5_espn25_fields/source/row04_endzone_S.png": "a178d41eb5db399f9846447708569a7f87c442fbcd7b7cf42757a6f860d02ca9",
                "data/nfl2k5_espn25_fields/source/row06_endzone_N.png": "a4de783fddd78f91073a7436abada3ba7051a02020c8e05912ef165b755ecf2d",
                "data/nfl2k5_espn25_fields/source/row06_endzone_S.png": "2acc161b38279f97e1f04218ecc94a575ed9ce633e72563a6ae5afeabe133b2a",
                "data/nfl2k5_espn25_fields/source/row09_center.png": "0dcf00e16a79fdac977df59358af2a6b4dbca194a4bb969694f84e419ee42fe4",
                "data/nfl2k5_espn25_fields/source/row09_endzone_N.png": "778c702aaf18b98fd3663cdba1568d48f241db9d560da834eae1bd2a75440672",
                "data/nfl2k5_espn25_fields/source/row09_endzone_S.png": "20dae6541e87e3d80a7cd3e8829a1608a16667dd6fd4a302fb97c83ee7dd2361",
                "data/nfl2k5_espn25_fields/source/row11_endzone_N.png": "c9fa1f2b428414637d6215dca913a5db6d2ca80f7e5f49536e3241a02c57ae38",
                "data/nfl2k5_espn25_fields/source/row11_endzone_S.png": "ba9ef9f3aca98914aed5cbe829a0808405ea646412c28854132399a42c204113",
                "data/nfl2k5_espn25_fields/source/row14_endzone_N.png": "887a4dff5d12f3573c79f8b62f791fe838bc650f7306712340715a2002f6fe0e",
                "data/nfl2k5_espn25_fields/source/row14_endzone_S.png": "dd69cc073bec1f05027b508c8cbf9c6af937f3c33f35b78a3430ddc40e148f97",
                "data/nfl2k5_espn25_fields/source/row15_endzone_N.png": "a7e2700cd933518560624b003da064559db86b688be21c1fa8a768440f965f86",
                "data/nfl2k5_espn25_fields/source/row15_endzone_S.png": "dc0f4c49783ffa62b5bfb43999a78b618af6b9c0b3734d401ea6383a3b738dc0",
                "data/nfl2k5_espn25_fields/source/row18_center.png": "834a0e19d205eee21a07031c0c4b91243f362972fdc5ec06aeebf18da330c148",
                "data/nfl2k5_espn25_fields/source/row18_endzone_N.png": "c112679090ba3c8341ff7da3e1e2fb7e62e65a3302b1cd4f29c30d27fb53851e",
                "data/nfl2k5_espn25_fields/source/row18_endzone_S.png": "634fbdfab33c53caee73ba232812c4e9ca743d11c872b544789a94c57406f703",
                "data/nfl2k5_espn25_fields/source/row20_center.png": "834a0e19d205eee21a07031c0c4b91243f362972fdc5ec06aeebf18da330c148",
                "data/nfl2k5_espn25_fields/source/row20_endzone_N.png": "c112679090ba3c8341ff7da3e1e2fb7e62e65a3302b1cd4f29c30d27fb53851e",
                "data/nfl2k5_espn25_fields/source/row20_endzone_S.png": "634fbdfab33c53caee73ba232812c4e9ca743d11c872b544789a94c57406f703",
                "data/nfl2k5_espn25_fields/source/row21_endzone_N.png": "21822f04efc28392230ee99ab305747bd3e5f09a45860c5f21a3bed9c331ee21",
                "data/nfl2k5_espn25_fields/source/row21_endzone_S.png": "84da5c9e01dad05dcb7083ee951aae63ed160c1e6c48526e11edd7fe3fa750bb",
                "data/nfl2k5_espn25_fields/source/row22_endzone_N.png": "4eb6c71c40a82a1f8f5d5210322217bf02ab6d8ff6c2bb90045596c24816ee37",
                "data/nfl2k5_espn25_fields/source/row22_endzone_S.png": "79bb6f7a6f7e16e5823e383f874ba8dc3544baba4ea539f8a012f30da4d0f0fd",
                "data/nfl2k5_espn25_fields/source/row23_endzone_N.png": "355ccf53e403c233f397e94a49c000216f476fc28875c865ac5ddf291e38dbb6",
                "data/nfl2k5_espn25_fields/source/row23_endzone_S.png": "e40eb7d509c65bb693583eda0b341634e05ed7b38513c3d5f3ed43dbac95c375",
                "data/nfl2k5_espn25_fields/source/row26_center.png": "f2c0011ee24b63ff23aaa1460852f890a6c08dccac9f2408f8c9975dba329add",
                "data/nfl2k5_espn25_fields/source/row26_endzone_N.png": "65b0034bea84b28fe6f94d4b166015e7320249f1442992160fff12ad686c0402",
                "data/nfl2k5_espn25_fields/source/row26_endzone_S.png": "f51c54e5ca7a15fccbb0ec1c3b69dfa5397787246c6413ddb2bbc465daa5aeec",
                "data/nfl2k5_espn25_fields/source/row27_endzone_N.png": "a200be78183df8f5aa9e6c17df604e18106af3e5887d5d4cf5209a652c1fea6c",
                "data/nfl2k5_espn25_fields/source/row27_endzone_S.png": "25c5d80fb696442ebe0b1eb115310a757498a650d50e0289bae602f09ef7715b",
                "data/nfl2k5_espn25_fields/source/row28_endzone_N.png": "24a23f2cd6f329346803a7df853d189b714cf493b4c7e219cf9dd44bbb381b2a",
                "data/nfl2k5_espn25_fields/source/row28_endzone_S.png": "55c4045010eb808020dbff51edea7b6deae3fe2e7f69d9141579a1013db5dc0a",
                "data/nfl2k5_espn25_fields/source/row29_endzone_N.png": "01014a66dfa53906922f29425d29919ae1c1ad616a15733059f49f48f0d62e7f",
                "data/nfl2k5_espn25_fields/source/row29_endzone_S.png": "3373f4fd5ec434312fb8f77eff46c98421947283bb873afceeefb6cbc86cbe16",
                "data/nfl2k5_espn25_fields/source/row30_endzone_N.png": "8405405495d3995a5c44ac12f75ce5bc0ea77477f248fa89f76a2848650171e7",
                "data/nfl2k5_espn25_fields/source/row30_endzone_S.png": "73e68031a0ca11ed0239e4d25bb6f983718ecaf5511f861c2312e766bda78b4b",
                "data/nfl2k5_espn25_fields/source/row32_endzone_N.png": "61a42d28f0e377978fcc7ce7c82d06ef70b067745494374fa70ce95a05f896d4",
                "data/nfl2k5_espn25_fields/source/row32_endzone_S.png": "380e0e013a4f24e46a0dc560175b9f425f146073f7d09e557c21bc104795145b",
                "data/nfl2k5_espn25_fields/source/row33_endzone_N.png": "30fe1ae29857d9e2995fed755ad70567d004765240f5e1c8dd1b51198cbab870",
                "data/nfl2k5_espn25_fields/source/row33_endzone_S.png": "93c8fd44276757b1369f9b68ff8addbfcd658ac2658917b6b884fd43e12f0f1a",
                "data/nfl2k5_espn25_fields/source/row34_endzone_N.png": "b14bb4d9937ee223cbe74eb4bd1c5970a7a183bb68c4f0a0880a91a7399e5999",
                "data/nfl2k5_espn25_fields/source/row34_endzone_S.png": "4093e5d072c13de93b9452aa7217b834ee79f2808eab7084bad63d372de1bceb",
                "data/nfl2k5_espn25_fields/source/row35_endzone_N.png": "cb0c520d40447e951262695d4de67fc20cba5d96c3abea47634c859f27a7ccb7",
                "data/nfl2k5_espn25_fields/source/row35_endzone_S.png": "3581dc024173ed9158a1ce5048bf27d449e0c989535d60151588aca8bfa82186",
                "data/nfl2k5_espn25_fields/source/row38_endzone_N.png": "289845b1611c0a13e0cd11550da291da61e7282686fba0671cb8de16c15522d7",
                "data/nfl2k5_espn25_fields/source/row38_endzone_S.png": "c3573dc69e8079e9bd927f8aec5ef5440ccc93c2dfc396b29b1b0e76f2768969",
                "data/nfl2k5_espn25_fields/source/row39_endzone_N.png": "f58582f43246e201bac463959c9e77d65037a7bcea07e01bcb223f8aafb3ed64",
                "data/nfl2k5_espn25_fields/source/row39_endzone_S.png": "ea4eb7e856afb8c7f04c340f25d97094caf318737dcc3deb12a8b91c7124edc7",
                "data/nfl2k5_espn25_fields/source/row40_endzone_N.png": "a651c098b6b7af3d8d0db5a002ba2a3f9b934cb321657125ca3017c51e155c6d",
                "data/nfl2k5_espn25_fields/source/row40_endzone_S.png": "8a614473dc7da4b2e809c6c301612d1ca0214132b22f628b7fd21029896cd049",
                "data/nfl2k5_espn25_fields/source/row41_endzone_N.png": "4c8792f87a516667c2354b8e9ef1bcf4f926d19532c9ffc80d08e52915fc5579",
                "data/nfl2k5_espn25_fields/source/row41_endzone_S.png": "43fb0c5cff08a9b7456b5e4f6b17958e6936773692e67e7f430846bce01ed029",
                "data/nfl2k5_espn25_fields/source/row42_endzone_N.png": "098412ad8aa221c03fa2d17feba8a6efb17cf57feff85ad1439fa4ea72b9a56b",
                "data/nfl2k5_espn25_fields/source/row42_endzone_S.png": "bea9dc2c556e35af2d313e9d072b797dc683d18084c70e83f87d6bcc62202930",
                "data/nfl2k5_espn25_fields/source/row44_endzone_N.png": "c92cdf18a8a21b3de202e3b89f32cd488dfb88708ed2adc55636cbbb413616af",
                "data/nfl2k5_espn25_fields/source/row44_endzone_S.png": "1b293c6b04937cc4636d5cec77a6d07305ecd14454d0824463da771dfa9fc3c2",
                "data/nfl2k5_espn25_fields/source/row45_endzone_N.png": "627fae2596925204839560e340a51f554ebd51e67c3aaee94df0a9165004f903",
                "data/nfl2k5_espn25_fields/source/row45_endzone_S.png": "e993ec613694f9e76b4dc2bd7410d344e663639b301d62220fa581a67f81d7dd",
                "data/nfl2k5_espn25_fields/source/row46_endzone_N.png": "da1222e48ac1ae391c83c26ca863edfe9229b4dcf60da785d0920fb163b77283",
                "data/nfl2k5_espn25_fields/source/row46_endzone_S.png": "14b19a35816552db46fe53291fbf8ac12b7c9ca04b4b0cb01a6f7176ccd341f9",
                "data/nfl2k5_espn25_fields/source/row47_endzone_N.png": "6813b905e67e920dc0b4d145fb9dc30f5af786ca5cd6a7669f265ee2e567b4de",
                "data/nfl2k5_espn25_fields/source/row47_endzone_S.png": "dba4ff0420a954a2b6c22f133ef8830f2f72d9ae389f15ef18658d40b12380aa",
                "data/nfl2k5_espn25_fields/source/row48_endzone_N.png": "2c8d077c83bd3363a8daee06565fe409024fd0412bc3fd77afc58cd28cab4a16",
                "data/nfl2k5_espn25_fields/source/row48_endzone_S.png": "ba7f05ccb064912713b70ca999210eb0e7f9e8be360a79e5515073de8eab8ad2",
                "data/nfl2k5_espn25_fields/source/row50_endzone_N.png": "911e23977aee3d90823857449ccd7238850cab4771c26b84ef53a0289c686048",
                "data/nfl2k5_espn25_fields/source/row50_endzone_S.png": "a947362a380a50c70925e07f7041ce6e594fe1010703cbdd38e2e5ce2db25725",
                "data/nfl2k5_espn25_fields/source/sb25.png": "19e1ded7316192392eeb993a8ce0f74a0801cc50d1d4ed433b3d9f9c3cf4d130",
                "data/nfl2k5_espn25_fields/source/sb25.svg": "da93e4a9d1bd685d8b1aab9fc7a90150e9e9e8a3c9fe2f4413338f78c7ba3442",
                "data/nfl2k5_espn25_fields/source/sb32.png": "5e25faaf1d4cb612ca3c21aaa6081c56baa98d25d2bcfb5b9036697d5bf83280",
                "data/nfl2k5_espn25_fields/source/sb34.png": "9aeea8a326ed302273d9c5d97cb5024a6ea2b73dd5b9a146a58440ed888ccfee",
                "data/nfl2k5_espn25_fields/source/sb36.png": "3f861a3253574e4d0f447365ee34c487fc1e493a74e08abd95330599a8c798e0",
                "data/nfl2k5_espn25_more_teams/steelers_2025.csv": "0a5abc4ca06f2765e0ff95f6e8dfae9d5f8d761d9831eac0923b82fef7cb3b0c",
                "data/nfl2k5_espn25_more_teams/bengals_2025.csv": "9cd4f343905739c468c980cf384bafd63e22cb8605418980f2ebc9954f4702ac",
                "data/nfl2k5_espn25_v04_profile.json": "3f1f60561c14a2a09fd23dae09d0fad6dbc5f2b49cf14cc171c4cb1a3ad5351d",
                "data/nfl2k5_espn25_unc_bowl.json": "2ad8c32bed29352ae2407350c1301646634914baa2e841cc4e9e1a96cba041e5",
                "data/nfl2k5_espn25_fields.json": "4d17dc285178ca60f5b0e8281790f0de601578f4aabcb79b53346c453db08834"
            },
        )
        for relative, expected in unified.data_pins.items():
            path = WORKSPACE / relative
            self.assertLess(path.stat().st_size, 8 * 1024 * 1024)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

        for provider in providers[1:]:
            schema = WORKSPACE / provider.recipe_schema_file
            self.assertEqual(
                hashlib.sha256(schema.read_bytes()).hexdigest(),
                provider.recipe_schema_file_sha256,
            )

    def test_unified_bundle_is_init_free_and_executes_help_and_visual_validate(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider()
        environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        with tempfile.TemporaryDirectory() as temporary:
            job = request(Path(temporary))
            with _pinned_execution_bundle(
                self.provider_workspace,
                {**provider.module_pins, **provider.data_pins},
                provider.backend_module,
                "NFL unified visual backend",
            ) as entry:
                bundle_root = entry.parents[1]
                self.assertFalse((bundle_root / "mod_editor/__init__.py").exists())
                self.assertFalse((bundle_root / "mod_editor/core/__init__.py").exists())
                help_result = subprocess.run(
                    (sys.executable, "-B", os.fspath(entry), "--help"),
                    cwd=Path("/"),
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    shell=False,
                    check=False,
                )
                self.assertEqual(help_result.returncode, 0, help_result.stderr)
                self.assertIn("{validate,build,verify}", help_result.stdout)

                validate_result = subprocess.run(
                    (
                        sys.executable,
                        "-B",
                        os.fspath(entry),
                        "validate",
                        "--project",
                        os.fspath(job.backend_project),
                    ),
                    cwd=Path("/"),
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    shell=False,
                    check=False,
                )
                self.assertEqual(
                    validate_result.returncode, 0, validate_result.stderr
                )
                report = json.loads(validate_result.stdout)
                self.assertEqual(report["kind_counts"], {"team_identity": 1})
                self.assertTrue(report["schema_and_png_pins_valid"])

    def test_unified_registry_authorization_is_an_exact_contract(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider()
        capability = self.registry.get("nfl2k5.uniforms.all_visual")
        with tempfile.TemporaryDirectory() as temporary:
            job = request(Path(temporary))
            provider._validate_capability(job, capability)
            provider._validate_capability(
                replace(job, capability_id="nfl2k5.crib.assets"),
                self.registry.get("nfl2k5.crib.assets"),
            )
            provider._validate_capability(
                replace(job, capability_id="nfl2k5.audio.fixed_audo_wav"),
                self.registry.get("nfl2k5.audio.fixed_audo_wav"),
            )
            provider._validate_capability(
                replace(
                    job, capability_id="nfl2k5.audio.ausb_fixed_range_wav"
                ),
                self.registry.get("nfl2k5.audio.ausb_fixed_range_wav"),
            )

            mutations = []
            raw = copy.deepcopy(capability.raw)
            raw["backend"]["command"] += " --unreviewed"
            mutations.append(replace(capability, raw=raw))
            raw = copy.deepcopy(capability.raw)
            raw["backend"]["extra"] = True
            mutations.append(replace(capability, raw=raw))
            raw = copy.deepcopy(capability.raw)
            raw["source_container"]["hash_pins"].append("0" * 64)
            mutations.append(replace(capability, raw=raw))
            raw = copy.deepcopy(capability.raw)
            raw["selectors"]["fields"].append(
                {"allowed": "anything", "name": "raw_offset", "required": False}
            )
            mutations.append(replace(capability, raw=raw))
            raw = copy.deepcopy(capability.raw)
            raw["classification"] = Classification.RUNTIME_PROVED.value
            mutations.append(replace(capability, raw=raw))
            mutations.append(
                replace(capability, classification=Classification.RUNTIME_PROVED)
            )

            for altered in mutations:
                with self.subTest(altered=altered):
                    with self.assertRaisesRegex(ProviderError, "does not authorize"):
                        provider._validate_capability(job, altered)

    def test_unified_source_record_identity_is_exact(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider(
            source_hasher=lambda path, progress: (PINNED_SOURCE_SHA, path.stat().st_size)
        )
        capability = self.registry.get("nfl2k5.uniforms.all_visual")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = request(root)
            forged = (
                replace(job.source, fingerprint_id="another-retail-disc"),
                replace(job.source, kind="directory"),
                replace(job.source, inspected_path=str(root / "missing.iso")),
            )
            for source in forged:
                with self.subTest(source=source):
                    with self.assertRaises(ProviderError):
                        provider.preflight(
                            replace(job, source=source), capability, lambda event: None
                        )

    def test_provider_owned_inputs_reject_hardlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            unified = request(root)
            os.link(unified.backend_project, root / "project-alias.json")
            with self.assertRaisesRegex(ProviderError, "singly-linked"):
                Nfl2k5UnifiedVisualProvider()._read_project_header(
                    unified.backend_project
                )

            scorebug = scorebug_request(root)
            scorebug_provider = Nfl2k5ScorebugProvider()
            project = scorebug_provider._read_project(scorebug.backend_project)
            scorebug_png = root / "score_buga.png"
            os.link(scorebug_png, root / "scorebug-alias.png")
            with self.assertRaises(ProviderError):
                scorebug_provider._pin_project_pngs(project)

            apf_root = root / "apf"
            apf_root.mkdir()
            apf = apf_request(apf_root)
            os.link(apf.backend_project, apf_root / "recipe-alias.json")
            with self.assertRaisesRegex(ProviderError, "singly-linked"):
                Apf2k8JerseyColorProvider()._read_recipe(apf.backend_project)

            source = root / "source.bin"
            source.write_bytes(b"source")
            os.link(source, root / "source-alias.bin")
            with self.assertRaisesRegex(ProviderError, "singly-linked"):
                Nfl2k5UnifiedVisualProvider._regular_non_symlink(source, "source")

    def test_private_bundle_executes_hashed_bytes_after_workspace_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            tools = workspace / "tools"
            tools.mkdir()
            main = tools / "main.py"
            dependency = tools / "dependency.py"
            main.write_text("import dependency\nprint(dependency.VALUE)\n", encoding="utf-8")
            dependency.write_text("VALUE = 'PINNED'\n", encoding="utf-8")
            pins = {
                "tools/main.py": hashlib.sha256(main.read_bytes()).hexdigest(),
                "tools/dependency.py": hashlib.sha256(dependency.read_bytes()).hexdigest(),
            }

            with _pinned_execution_bundle(
                workspace, pins, "tools/main.py", "test backend"
            ) as staged:
                main.write_text("print('FORGED MAIN')\n", encoding="utf-8")
                dependency.write_text("VALUE = 'FORGED DEPENDENCY'\n", encoding="utf-8")
                result = subprocess.run(
                    (sys.executable, os.fspath(staged)),
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    shell=False,
                    check=False,
                )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "PINNED\n")

    def test_private_bundle_rejects_hardlinked_modules_and_post_stage_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            tools = workspace / "tools"
            tools.mkdir()
            module = tools / "main.py"
            module.write_text("print('safe')\n", encoding="utf-8")
            digest = hashlib.sha256(module.read_bytes()).hexdigest()
            os.link(module, tools / "alias.py")
            with self.assertRaisesRegex(ProviderError, "singly-linked"):
                with _pinned_execution_bundle(
                    workspace, {"tools/main.py": digest}, "tools/main.py", "test backend"
                ):
                    pass

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            tools = workspace / "tools"
            tools.mkdir()
            module = tools / "main.py"
            module.write_text("print('safe')\n", encoding="utf-8")
            digest = hashlib.sha256(module.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ProviderError, "bundle changed"):
                with _pinned_execution_bundle(
                    workspace, {"tools/main.py": digest}, "tools/main.py", "test backend"
                ) as staged:
                    staged.chmod(0o600)
                    staged.write_text("print('forged')\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

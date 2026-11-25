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

    def test_colour_and_uniform_resources_load_inside_the_isolated_provider_bundle(self):
        import subprocess
        import sys
        provider = Nfl2k5UnifiedVisualProvider()
        with _pinned_execution_bundle(self.provider_workspace, {**provider.module_pins, **provider.data_pins},
                                      provider.backend_module, "colour settings") as module:
            result = subprocess.run([sys.executable, "-I", "-c",
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "from mod_editor.core.nfl2k5_build_settings import build_settings; "
                "from mod_editor.core.nfl2k5_modern_color import default_settings; "
                "from mod_editor.core.nfl2k5_unc_bowl_uniforms import PINS; "
                "import json; assert json.loads(PINS.read_text())['schema'] == 'nfl2k5_unc_bowl_uniforms/v1'; "
                "from mod_editor.core.nfl2k5_era_kits import pins as era_pins; assert len(era_pins()['kits']) == 10; "
                "from mod_editor.core.nfl2k5_moment_kits import pins as kit_pins; assert len(kit_pins()['packages']) == 26; "
                "from mod_editor.core.nfl2k5_nyg_numbers import pins; assert len(pins()['digits']) == 10; "
                "from mod_editor.core.nfl2k5_kit_fixes_2026 import spec; assert len(spec()['textures']) == 58; "   # b81-retail-free-art: dead rows deleted by ruling
                "from mod_editor.core.nfl2k5_kit_fixes_2026 import alternates; assert len(alternates()['textures']) == 534; "
                "from mod_editor.core.nfl2k5_kit_fixes_2026 import finish; assert len(finish()['textures']) > 0; "
                "from mod_editor.core.nfl2k5_pants_hem_2026 import spec as hem; assert len(hem()['textures']) == 491; "
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
            # Number of imported writer and verifier modules for each real provider.
            [613, 10, 8, 9, 8, 9]
            # b81-seamen: 613 = 611 + the classic crowd owner (its fixed page; throw_tuning imports it for the cave
            # manifest recorder) and the 2026 fans writer it refits its spans with.
            # b81-seamen: 611 = 609 + the frozen revision 18 scorebug engine (the owner's recognition of 18 and 17) and
            # the abilities editor (its tier capacities check the classic teams' authored player tags).
            # b81 helmet-sides: 609 = 607 + the helmet side numbers owner (loaded by name, imported by throw_tuning for
            # the cave manifest recorder) + Number kerning, whose state the owner reads.
            # b81 integration (qb34 trades merge): 607 = 605 (next lines) + the quarterback trades owner and its generated
            # page template (the room owner loads it for stage bit 16; the lane counted 604 = 602 + those two).
            # b81 integration (qb34 E head merge): 605 = 604 (art merge, next lines) + qb34 C21's frozen floor + D1 + D2
            # hand-over page template (a fifth "previous" revision; the lane counted 602 = 601 + 1).
            # b81 integration (retail-free art merge): 604 = 601 + the build-time kit rules the kit fixes import by name
            # (nfl2k5_kit_rule_emblem, _fill, _recolour; the lane counted 593 = 590 + 3 on 3a789811e).
            # b81 combined + qb34 merge: 601 = 598 (qb34's merge, next line) + the combined branch's three (stability's
            # frozen slice 3 module, scoring's simulated scoring module and CPU kick aim owner; see 595 below).
            # b81 merge (qb34 + slices 2 and 3): 598 = 592 (slices 2 and 3, below) + qb34's six (above).
            # b81 qb34: 596 = 595 + the frozen floor review page template (66d8a7e1b; a fourth "previous" revision).
            # b81 qb34: 595 = 594 + the frozen D1 + D2 handover page template (a third "previous" revision).
            # b81 qb34: 594 = 592 + the room owner's two frozen earlier page templates (pages it reads as "previous").
            # b81 qb34: 592 = 590 + the quarterback room owner and its generated page template (loaded by name).
            # b81 slice 2: 591 = 590 + the frozen slice 1 quarterback code module (the settings module reads and
            # reverses a slice 1 install through it). b81 slice 3: 592 = 591 + the frozen slice 2 code module (read to
            # reverse a slice 2 install). b81 stability: + the frozen slice 3 code module (read to reverse a slice 3 install).
            # b81 scoring: + the in-place simulated scoring module (imported by the simulator option) and the CPU kick aim
            # owner (imported by throw_tuning). 595 = 592 + 1 + 2.
            # b778-ss2: 482 = 481 + the classic kit art module (atlas finishing and authored facemask words, imported by the moment kit composer); b778-sd4: 481 = 480 + the LED clock owner; b778-cb1: 480 = 479 + the cornerback tackle owner; b778-cr1: 479 = 478 + the Contracts null-college guard; b778-pg2: 478 = 475 + the Player Progress screen, its progression codec and the trophy-room module; b778-pg1: 477 = 475 + the Player Progress screen and its progression codec; b778-pg1: 476 = 475 + the Player Progress screen owner; b778-pg1: 475 = 474 + the weekly progression owner; b778-dr1: 474 = 473 + the franchise draft clock owner; b778-sc2: 473 = 472 + the SportsCenter identity lookup (in place); b778-st2: 472 = 470 + the star career owner and its generated code (imported by throw_tuning); b778-ai5: 470 = 469 + the CPU ball-carrier owner (imported by throw_tuning); b778-pi1: 469 = 468 + the practice injuries owner (imported by throw_tuning); b778-fa1: 468 = 467 + the star retention owner (imported by throw_tuning); b778-uf2: 467 = 466 + the 2026 nameplate fixes module; b778-ss1: 466 = 463 + the classic art, classic face and classic field modules; b778-pc3: 463 = + the inbox standings owner and its club-history helper (pointer-only build edit); b778-xs1: 462 = + the module loader prototype and the Crib Trophy Room cut (imported by the Crib rebuild) (imported by MyCareer and the Contracts editor guards); b778-fo1: 460 = + the modern sideline catch owner (imported by throw_tuning); b777-int7 (tp1 merge): 459 = rb2 + tp1 together; b777-tp1: + the formation art spacing owner (imported by throw_tuning); b777-rb2: 458 = + the RB rename owner (imported by throw_tuning); b777-int7: 457 = ar1 + ol1 + qb3 + st1 together; b777-st1: + the loader wake-up owner (imported by throw_tuning; st1 did not update this count); b777-qb3: + the QB accuracy owner and its generated code (imported by throw_tuning; qb3 did not update this count); b777-ol1: + the run blocking owner and its generated code (imported by throw_tuning); b777-ar1: + the midfield centring module the modern venues and the Anniversary field compiler import; b776-int2: + pb1 (b776-pb1: + the modern offense catalog the concept engine imports); + ns1 (b776-ns1: + the per-kit jersey number size owner, a late xbe_space owner); + pa2 (b776-pa2: + the play art routes owner, imported by throw_tuning); + ku1 (b776-ku1: + the Chiefs menu card palette module); + ai2 (b776-ai2: + the CPU QB reads and defender ball-play owners and their generated code, imported by throw_tuning); fn2 + fs1 + pb2 + de2 together (pb2: + the coach ring diversity module nfl2k5_vip imports; de2: + the front schemes module the roster passes import); b776-fs1: + the moment face scans module; b776-fn2: + the 2026 glyph fixes module (Bears/Chiefs nameplate letters, Titans 7); b775-int1: sb1 + mo2 + ek1 + ui1 + ct1 + hs1 + fast2 together; b775-fast2: + the late-steps worker/cache module; b775-hs1: + the hair styles owner (imported by throw_tuning so the cave manifest recorder observes it); b775-ct1: + the classic teams module (an allocator owner the space union imports); b775-ui1: + the MyCareer Career Home module and its generated code (imported by throw_tuning); b775-ek1: + the Anniversary moment kits stage (new game-accurate kit slots); b775-mo2: + the moment context owner; b775-sb1: + the Super Bowl field flank module the Anniversary field compiler imports and the franchise Super Bowl hosts module the build calls after Broadcast greens; b773-i4: + the Anniversary era kits stage (a5k compiler) before the Unc Bowl finish; b773-gr1: + the Broadcast greens module the build calls after the last field writer; b773-me1: + the Super Bowl event walls module the Anniversary field compiler imports and the era ball module the moment-venue owner imports; b772-vt1: + the automatic coach AI owner, its generated code template and the coach VIP profile module; b772-sp1: + the ordinary tap-burst module the abilities runtime imports; b77-st1: + the stadium shadow module the MetLife model imports; b772-ny1: + the Giants shoulder-number module; b772-uf1: + the 2026 kit art fixes module; b77-f5: + the honors page module and its history module; b77-v1b: + the period goalposts module (an allocator owner imported by throw_tuning); b77-p48d: + the defense formation linter the pack checker imports (stage 5); b77-p48o: + the modern offense concept engine the play library imports; b77-q1: + the QB Throw Power roster-edits step; b77-h1: + the punter holder module (imported by throw_tuning); b77-a4: + the moment shotgun-weight module; b77-f4b: + the progression row module; b77-p13: + the playbook execution linter imported by the complete-offense compiler; b77-k1: + the player-name keyboard patch module; dn: + the resource load guard module; cl: + the college references module; mk2: + the official marks module (its catalog is a data pin); ht: + the historic season-roster module and its phase-2 import; b75: + the Edit Player elbow-pad and lineman-rating option patches.
            # b773-sp2: + the human tap-burst compiler imported by the abilities runtime.
            # b773-ic1: + the exact pinned menu-icon orientation repair.
            # b773-mo1: + moment coaches and its newly reached scenarios and modern-coaches dependencies.
            # b775-mo2: + the Anniversary moment context (Super Bowl game type and moment stats), imported by the moment coaches.
            # b773-hu1: + Washington menu helmet compiler.
            # b773-uf3: + the exact pinned Pittsburgh miniature correction.
            # b773-pa1: + the 2026 pants hem pass (its kit document is a data pin).
            # b771-v1g: + the Unc Bowl compiler and its archive helper; the owned-span document is a data pin.
            # b765 integration: + fixed-size spare-capacity owner for dated FA/historic composition.
            # b765-a1: + the Anniversary archive pack, field compiler and their 38 existing venue-tool dependencies.
            # b765-s2: + two explicitly selected field owners and their complete reviewed 38-module source closure.
            # b76-pk3: + the file-pack reader/writer imported by modpack.
            # b77-f4: + the letter grades owner and its generated code template (a late allocator owner, imported by the build).
            # b77-f5: + the honors owner and its generated code template (a late allocator owner, imported by the build; the honors history writer is loaded by name, like the other roster steps).
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
                    "mod_editor/core/nfl2k5_menu_icon_orientation.py",
                    "mod_editor/core/nfl2k5_menu_icon_uf3.py",
                    "mod_editor/core/nfl2k5_pants_hem_2026.py",
                    "mod_editor/core/nfl2k5_glyph_fixes_2026.py",
                    "mod_editor/core/nfl2k5_nameplate_fixes_2026.py",
                    "mod_editor/core/nfl2k5_menu_chiefs_2026.py",
                    "mod_editor/core/nfl2k5_menu_helmet_w2026.py",
                    "mod_editor/core/nfl2k5_era_kits.py",
                    "mod_editor/core/nfl2k5_moment_kits.py",
                    "mod_editor/core/nfl2k5_unc_bowl_uniforms.py",
                    "mod_editor/core/nfl2k5_nyg_numbers.py",
                    "mod_editor/core/nfl2k5_kit_fixes_2026.py",
                    # b81-retail-free-art: build-time rules nfl2k5_kit_fixes_2026.paint imports by name
                    "mod_editor/core/nfl2k5_kit_rule_emblem.py",
                    "mod_editor/core/nfl2k5_kit_rule_fill.py",
                    "mod_editor/core/nfl2k5_kit_rule_recolour.py",
                    "mod_editor/core/nfl2k5_relief_2026.py",
                    "mod_editor/core/nfl2k5_anniversary_pack.py",
                    # Studio dynamically selects these reviewed field owners after surface compilation.
                    "mod_editor/core/nfl2k5_midfield_art.py",
                    "mod_editor/core/nfl2k5_split_endzone_art.py",
                    # b773-gr1: the last field pass, called after every field writer.
                    "mod_editor/core/nfl2k5_broadcast_greens.py",
                    # b775-sb1: the franchise Super Bowl hosts, called after Broadcast greens.
                    "mod_editor/core/nfl2k5_super_bowl_hosts.py",
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
                    # sc2: mod_build selects this reviewed late writer by module name.
                    "mod_editor/core/nfl2k5_sportscenter_lineup.py",
                    # b81 qb34: mod_build selects the quarterback room owner by name; it imports its page template.
                    "mod_editor/core/nfl2k5_qb_room.py",
                    "mod_editor/core/nfl2k5_qb_room_code.py",

                    "mod_editor/core/nfl2k5_audo_fixed_slots.py",
                    "mod_editor/core/nfl2k5_safe_text_banks.py",
                    "mod_editor/core/nfl2k5_scorebug_unified_adapter.py",
                    "mod_editor/core/nfl2k5_stadium_texture_writer.py",
                    "mod_editor/core/nfl2k5_p8_texture_writer.py",
                    "mod_editor/core/nfl2k5_unif_color_writer.py",
                    "mod_editor/core/nfl2k5_uniform_equipment_writer.py",
                    # b778-pc3: the inbox standings setup the build calls (pointer-only edit).
                    "mod_editor/core/nfl2k5_inbox_standings.py",
                    # b778-cr1: the Contracts null-college guard the build calls.
                    "mod_editor/core/nfl2k5_contract_college_guard.py",
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
                "data/nfl2k5_modern_venues_2026/numbers/manifest.json": "fa9ca79e6175b4b50fb624841b4cb6aea47f9a9f910e891723de1fdf9cfed089",
                "data/nfl2k5_modern_venues_2026/numbers/block.png": "1a6e2517c6f5f745a0a98712c4f19870ae964c8f81563d99351f2a1948d56718",
                "data/nfl2k5_super_bowl_logos/manifest.json": "66193ac79c75a1da67f44948392f4a3885f31733e255448905f410409d1a28a8",
                "data/nfl2k5_super_bowl_logos/brands/abc.png": "40089deda13e1be30afd5c0c7d07dccc5c9918507541497c6575f2d67c71896a",
                "data/nfl2k5_super_bowl_logos/brands/cbs.png": "7b7b3482fcfbe90b783800457d85404949d717a6ff8ba1534576015609193ccc",
                "data/nfl2k5_super_bowl_logos/brands/espn.png": "89dc92e83232b12e19e0efcac3d44e2ed61c3a38b4f06d82384a8802cb430679",
                "data/nfl2k5_super_bowl_logos/brands/fox.png": "845daec20b134a879a8e9e1662c4e909277271d0814810907e788e3ae928ac6b",
                "data/nfl2k5_super_bowl_logos/brands/nbc.png": "79763cd0c5f72ea741875e3c6e353b79dc67e5a4f8a05f90e7caff08a7afaba4",
                "data/nfl2k5_super_bowl_logos/super_bowl/LI.png": "35d9ceb588c55bcdb5b01a1e8d86e0b1c82df1d5d765299a11833b628a772cda",
                "data/nfl2k5_super_bowl_logos/super_bowl/LII.png": "4d29dc721ef89c2557c5fd5d6827d6daca27ec9197bd50fe67cba496f31e7f33",
                "data/nfl2k5_super_bowl_logos/super_bowl/LIV.png": "5fd1a4ea668e38570f7659a6ab2944b9234d227728c0b90180cef39e113a5a82",
                "data/nfl2k5_super_bowl_logos/super_bowl/LVI.png": "97fc8e02cc63059aaeac49deab4281da5bc96a8eba9fa506e250323fd67fa28d",
                "data/nfl2k5_super_bowl_logos/super_bowl/LVIII.png": "0e581e17c81fff5aca3d796155e6bf51ba485a9bd3806c1d33f89c1577b6f46a",
                "data/nfl2k5_super_bowl_logos/super_bowl/XLII.png": "16f8f8a31110b95ff134e38b850246fe234e96fc2df9a63ae004ad31d9acd4a8",
                "data/nfl2k5_super_bowl_logos/super_bowl/XLIII.png": "7dd945a696a03d435f48ba52f6731c938ffc55f5d891eae31af104d73ace7e94",
                "data/nfl2k5_super_bowl_logos/super_bowl/XLIV.png": "260a7d63a99f1aab41a29a90918afd37a2d64843a579a11ea47771c5b0056c82",
                "data/nfl2k5_super_bowl_logos/super_bowl/XLIX.png": "b19dfb80f755903da9f2eef5fb21eb13628364b0e98849d41de7e515659eca9c",
                "data/nfl2k5_super_bowl_logos/super_bowl/XLVI.png": "04c1f3e83de84cd8710ae35eb9d1feec0bd77c2089c2c2e4ae0fe5fc7b7f0ffe",
                "data/nfl2k5_super_bowl_logos/super_bowl/XLVII.png": "2d54985087ffe8ebb8133db8760ab1daab8762eddc20ec6ae20b2d66dab4fac5",
                "data/nfl2k5_super_bowl_logos/super_bowl/XXIII.png": "130f5e2405c2c23789e1810f7650dec47b7a31e2b64eb01d88365d9aa87c16f3",
                "data/nfl2k5_super_bowl_logos/super_bowl/XXV.png": "85f2451c355d842f98eaace1a02d708856a644e620b40e0481c6de78baff1c88",
                "data/nfl2k5_super_bowl_logos/super_bowl/XXXII.png": "bc42798dfc53c7373bbbe8b0dad65216fbb248c260a256782116c2e69ce939ac",
                "data/nfl2k5_super_bowl_logos/super_bowl/XXXIV.png": "de5bb748d5dd335625baff3bf887aeac6df85f5a31dcea19fd359d798d0ed327",
                "data/nfl2k5_super_bowl_logos/super_bowl/XXXVI.png": "8915b4f6a5b523cea6020e47614ea969b53ca9926029b52052e24a71b7916819",
                "data/nfl2k5_super_bowl_logos/teams/CIN_1988.png": "6d382e567a2188ae78de7520b1dcccd14e4a858af27f085bb91064a41216c636",
                "data/nfl2k5_super_bowl_logos/teams/NYG_1990.png": "a43168ac74d9a9cf8e04f739a331086f3797aeeeafe2652b2cd2d4373d9ee0e2",
                "data/nfl2k5_super_bowl_logos/teams/STL_1999.png": "ed4fbc293ede71dc5f39fa7f9db6c4928c117e8abd1faaeb7cba19b2cacd566a",
                "data/nfl2k5_super_bowl_logos/teams/STL_2001.png": "8bfd3de6c9c804ccfca5b356359e7125475b4040d0730b53da4f47e21ffad1dd",
                "data/nfl2k5_front_schemes.json": "1026ff34b0de28362b25f1019c5ef2ccd8b706bbee41f6ce77b26b6efc07a626",
                "data/nfl2k5_moment_era_kits.json": "6f7095e05cc31ece037aa40cf2d5b315c45566482f7b4a1a6a855067d087ac76",
                "data/nfl2k5_era_kits_pins.json": "de18bdf5f1b32067b286c72c275641a6e3498791f852b6bbe48ea2c80ad0db90",
                "data/nfl2k5_moment_kits.json": "e2fcbb93f376f266f6973626a48e2244521df1f529f3fbe67ec28cfdc7565c18",
                "data/nfl2k5_moment_kits_pins.json": "0931360ad914f68f7e0240a21d6e8247799589be36e2e6fb4f46331a960469b4",
                "data/nfl2k5_release_gates.json": "12b1146cdedd09e72fc532b712b4726cf744ee9f1bfa360c4e6ffd13b1209285",
                "data/nfl2k5_unc_bowl_uniforms_pins.json": "84dc131eebe5188fbfc18eee5187abc8ac5aba572b3796a35d2cd905a2769fe0",
                "data/nfl2k5_nyg_numbers_pins.json": "e1d34f4a340820f6569f362a91e7a1a5f5f96fd74c3a46644d656500a392f2da",
                "data/nfl2k5_kit_fixes_2026.json": "d33818434feb3f30e5d2515eaae1b186f97bfc6344bd477298550885bce96156",
                "data/nfl2k5_kit_fixes_2026_alts.json": "8a15681861c8abbe4c66c25e27fae776e3d37495f8e0ecf68fa4ffc6660ed7f5",
                "data/nfl2k5_kit_fixes_2026_uf3.json": "f4a2cbc1368de99d800498ea969041d29bb0e195fe6ae6d32f2213c4174c71fa",
                "data/nfl2k5_kit_fixes_2026_sea1.json": "a313792e54018305ee69026e06e1227f4998e7bfe33b95d2a55d27821fd4da62",
                "data/nfl2k5_kit_fixes_2026_ov1.json": "506d9592290de13e4aeb17a23a0febf147e4392b985646ef9c0df5e15765c9c4",
                "data/nfl2k5_pants_hem_2026.json": "c85ecadefb53337ab7b97996b36b9c36d2119e4745f64e1bab34e321162aa9ca",
                "data/nfl2k5_glyph_fixes_2026.json": "a709d39b5fb5ab4a6f6793e6626d36771197c6a196c410b8057e58f899148387",
                "data/nfl2k5_nameplate_fixes_2026.json": "535f690f05dfb40a53239ca007fef42bdc4eaaa9611fcf4b74b1496b62980200",
                "data/nfl2k5_glyph_fixes_2026/TEN_28A0_digit_arm_7.png": "01252bae05b33caa13780327eafd8add37303d54bc27d46429cef61230a292d5",
                "data/nfl2k5_glyph_fixes_2026/TEN_28A0_digit_jersey_7.png": "5da1a357b81632f469e23f506155ff43af10b2fad036a3de285145e7b694c713",
                "data/nfl2k5_glyph_fixes_2026/TEN_28H0_digit_arm_7.png": "078b28a7a0ae54e18d08b4580155ba6fa49fe566932305c7decd795a96f6d17b",
                "data/nfl2k5_glyph_fixes_2026/TEN_28H0_digit_jersey_7.png": "25727ec3a92a703131e11766c4da6a781a63855be44d10a0a961e451cad02de6",
                "data/nfl2k5_kit_fixes_2026_ku1.json": "9227fb1ef129725bcf72cc8c208a0433eb45b69af14fe5b8a1f99d3c381f62cb",
                "data/nfl2k5_kit_fixes_2026_sw1.json": "857e2cc360d95f830840bf2db620dfb5499e92eb4e12e0c319fcff205102f459",
                "data/nfl2k5_kit_fixes_2026_names.json": "cb354c62aa6b6e8de0ff01e9f25937f0a2e54169bfc37932bd689599529693fb",
                "data/nfl2k5_glyph_fixes_2026_b81u.json": "dd6c4f44b78e1176b954aee7afd7a072f3ed7d6fe7f5eb0a583004062a4db5f4",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_0.png": "26d9a687f3d5b42b484cee12564b93815034384654dcc5e137e69957f89e20c9",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_1.png": "6388edb77bb69daddeebda1b96d96b2cf0532b7314a02492ea5f78290cff195c",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_2.png": "5dc0b5217b5df5da541acb6e87b9a9bbe4d953d7c505db3753f09124901b9ca8",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_3.png": "06b923bbc3f0ef44f2e3a87e2d0c69bd5a33d8f9e5a63fd6fb2812224827118f",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_4.png": "ec60757a89eec56eb4cb51296d1279dcb48165d981a8e4390712dd65490d971e",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_5.png": "0007ea69c17c4aa5f5ea826527de17280ca9e0716855d2161d01f5262857b3ed",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_6.png": "0c8ebbb3b2fdde5db4d21ef558cb1f44c8137a3acafcbcc3b6a91e8281f115c8",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_7.png": "aea9b035bc6002a1fc8edacbd90bf92efbbe7d45f89a78431abdf2dc1cfa14ac",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_8.png": "af14b2106f6660fa732d7f81db9f527a9cd9391bdd13b76b2ef3dbc26887b88d",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_9.png": "1ae468d59da7633fb677373729d2df4a2f31cb5701d5799893e8cf4dd20e38a8",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_names.png": "3e9ebb153c98e87789d4af4fe38536fd0f63cb951ecd496e37113066d9e156f8",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_0.png": "09f227a1463e3d3e07c0b8ed96383c16e40c575f7772d452643eeebc6acd2acd",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_1.png": "c08191d18d99abe876117a12253c73623b5fd9f30688e6c2f1db9523cf5842ee",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_2.png": "322d2a8d0cfa36059ccb5cc40e429d44dc1efe0926b1903640ae9512ce4ad208",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_3.png": "033230579b3a60ff8f05a0a8bbd28e2e99280935d3156feaf29763e815a814c5",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_4.png": "080799f8c2149dff351d098c735dbcd420aaeb49e5cbe61c75ca4d17f3ac4162",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_5.png": "8ca26204d08dea440b6df16e9c799a4bad70a9be9130bc6fbb8a1cedf2c1a4ef",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_6.png": "3c4724ac12b20e524f19d6a85479c88bf1537b7f56602a4f7869283b49eb1300",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_7.png": "fa0712421aaac076cdd7e2b118c02e4e072a9473226b657de435889c0670251f",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_8.png": "02644868de5a98b9cfbfc0664ed438f933acc44fe514900a0af51fa5a78fa12e",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_9.png": "14692c0b48a2dd55dfab879ec17e4a77da77a324996e2fcd35d9e4a289f88126",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_0.png": "a6d6bda51977a867ec996d373a2cfcb87a3e580062acda7652ac63ab3cf6d695",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_1.png": "9584deda3afb984cade02e04c98498d48b74d1896afd788a5b8bf4113227eaba",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_2.png": "1f39c157d2b84aa27315a1764f102bfa4bda9e134f1289183b2d8159a97087b6",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_3.png": "aa67380b3dbb2f7c8fb4ca650329725b455cc867d01b9a6da0282530d77d026b",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_4.png": "ee8e48efc1c022b6a39f6044f66fc497e8d17813301790d33651640719c21db5",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_5.png": "3d58a4e266b667414390fb816e4224ad68e840d4083c9b8cfcbdc8851eb06537",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_6.png": "5e283dc43f81aae07001535dc0a9f378c11f60207d36080055bc62020adef510",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_7.png": "169bcb26af7ee1616ca306329781145a2fc8ea8e7c878bd9ebd271a1aec7e745",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_8.png": "cad9475458bb6594dad79becfac37dbb71f80bcf58c5ec38f879802d4da4622a",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_9.png": "2111dbed90563a3c2b5743ecdae254795d0c6ad223d726a8198a718803b48400",
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_names.png": "4a9dfcfbb5130175d671d38ea92c314a079d4c4b88d0eb90ed620971f9dc8084",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A9_names.png": "ef7150b4981adffaa52ab28979e503446a460778c46cad619a375aaacf347773",
                "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02H0_names.png": "7c92873ffa51961497ad79519d9f2da8928d379ca944c358d77cd4167e24dfef",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_0.png": "4e1b612ff355170a68ad41dcc67571a3921ff4632bec0b41c13033543d27e88d",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_1.png": "1be4533843283c071646b6bda9fbaa01877b9b0c85b1fdce602d48f5f411888b",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_2.png": "f2cec0e12d01030ee2fd3e3a3315951199ff0f283a9c97e9652df8af01e41452",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_3.png": "50f1a9f41ba822befda6bc32d3b2a56b5ef3d06da71988ef8f5bd2efca7f6808",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_4.png": "b20b49da83f608e1ac31bf47b7ec0da89f0f2b1b2742bbbfea555a5696897be8",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_5.png": "886899f8fb796bc1c1fa4553caad08b4e78381d570eccc1766fa9d384c150150",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_6.png": "5c01afdb3d453b2b4bfd62245965d776579a1db6ec640253a1f34d01b9a42b7a",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_7.png": "2fc24d8e51628b1fabc14e536b7dab94fa52772b89ee4b31e3a20ecc2cacca00",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_8.png": "e8e71c700598ba45cdf07efde346cbaa67fbab2b013fb59939bfddf345d870ff",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_9.png": "f6e2900abf01fd4b1a3982812c53e55c999b48513f2a1d89e51abbe0bc9c6c25",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_0.png": "64f073fa8987707e40703d62ad08b59d1c62384fefc8bc589acc0dc4f9b780ae",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_1.png": "e9c0161b60d67905cd1754b2720358c12f981b445b264343585614703a94ebda",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_2.png": "9d8896c96bcb9b13a30c82065f184d584c8aa9a2d9e922ec311ecc7f3f14a2d2",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_3.png": "b4568658ae1a3f944bc8eea526d78f4cdb53c19352b58f121c0ff5c63696c8ec",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_4.png": "45f54bb77475f2fe03342173a7f3fab40b307ecde333b11cbc22d127fcd74cf3",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_5.png": "c57f268ffa400a958223ba388f28a9cc000bca5e2859ebae99baceac7e72d8cd",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_6.png": "89544f3a907f1358c878323e7f2f978b9c51f1281072d9649aeb8808787787ca",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_7.png": "69ea06ceab43d66134c038844baed2b5e4caf41ed2c6d30582f7fdc1323d74ed",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_8.png": "b0a52e487df2780e63f4b3f272ca6836c396e968bef6af4ba1af8fa9a43ad289",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_9.png": "d2bb58a7d7480c43eb5513a460aa4047323928c6d5b035ca15ec1addac368455",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_0.png": "67e88d4aba890f79449c760999a720d507f84d35c738d2a1445f8cf6730e25a0",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_1.png": "f70a4694990db70a8594d5ca35b81f4bf431d3fe8caf695f1cdbbf434418e4fa",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_2.png": "ef4deb36ede2cf2fb0bbb4967bc3aa077fd5451aa231e66fa7d4da5dc66dc840",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_3.png": "ff22e18643a1a2e325e469fcf51c40652f3f862f0c545e222d1e6f16e4a7dc20",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_4.png": "1e1548bad01ae08eca3e4b158e7a27365309e89f0063e491af7a7fe0b366ef45",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_5.png": "9da49f2b6e6c8feff90c2cb9af1b82c806548aee815adeac8a39e61b97e42ca5",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_6.png": "453b0afdc536ff0b1f0fe6cb1366fb0296d2bcd13e8374ec7e3afe49dc65f9d8",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_7.png": "7d5e3613ecc953c611ba0d9ee5b861b5e39f258a0c12812e0bedcf62bef4d39b",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_8.png": "8002666a08c4c4fca048d162b1bba4def6eb9cb54624c16553b07ef0f91e791f",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_9.png": "ecc60d06a059712845203465143fdf2bdddff409aca391996427c00ea6e14556",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_names.png": "984e38cefdb74e6f2d3f2813bcc53f1c60ac682cb7b98a9fb0b262da4c6b80a4",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A4_names.png": "878203c70a53f773abe4d498d902aeb29c656506af095ef2c4e82d5c55957a3d",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_0.png": "f90a52f074f8eabc78d24ef2fcc908358c1761d938783afa6d2e82a29b22728c",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_1.png": "22e360031f7b86a7d062e4211a3888e60e28cef6f89d114cae6743a92add0c50",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_2.png": "8982eba2316206eb3646bd92072ef4527fd35848e42df2c58c5ea514e3d9c309",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_3.png": "45977a8720abbfcc031582e0e974435bdc8ff72223ae03d4987ce409948c80c7",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_4.png": "83f897256eac0ee6224cdf76a9552e0d6cda1ccf4dca407cacb80a74fd1d29fa",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_5.png": "5464f2adfd2c239573c8baa4450c421b99c08d1b03834c3bb173f3513578b5e3",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_6.png": "4fcae551d99890b51b29ed6c759984af84819ca11da473c37e94550e998d1bb9",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_7.png": "e92b3c715797cf18b7103a4292f33af0c3ca3ccd53416628d368899a4d935de2",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_8.png": "d6b344c48be9fdab22c0ef42c677125b77a75b9edead0a35a52c4cd8db823ca3",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_9.png": "fe2b01056596363b0d94903b61c50106b42833144a6e4b81f261b1d53c29edc9",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_0.png": "cb41b4bc2dee5bcbe3b99ea1b1baf358fd5675a17ce78cd59a850fdd67a29e8d",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_1.png": "5f90d02ee52de8451e7e533ed1cf79b3a5ae7f20a788854432e9a99b3ec65b21",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_2.png": "e280eb6b4732a86fbb0f85627b8f3e5be235f75400fa887c131a4605942c3fff",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_3.png": "fb9c1737a110128637bc11c9fb1db5ffd5832cda669d9eed417587c7889144d5",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_4.png": "b3d647bedfa451c1e30d9cfd5c942e59f63be452f21624591f6fbadcf9578eb4",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_5.png": "94315f0e8891a0524772e63324560b572ffcaa3be691baf2095e1b58ea101f78",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_6.png": "a333d402986396a7e87c94de6d40211343445d62026c7f065675c34e0f6913af",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_7.png": "6328121511c2e0cd5dcf890771b09c8d0efd95ae6d5e1e974bfe4649b57ebf99",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_8.png": "ed6227aec8297228d3aefba71fb064ccbbcde1f49797e4a7fb3e6159f364b48e",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_9.png": "eca7b850edd4756b0806f69cee7e2f972bac1cd915aec37f38b40cda564eb830",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_0.png": "efa81f56a2e92cf563a3630e6d064533c4af84971474f54f8f6ca160789ff265",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_1.png": "aa0c44cc91698e05aa5b008e9f7e0e3dd6d1637a0c7bf94975f06952588d5789",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_2.png": "2073a2aef87fbf0f06ef7efda1ff6d978a788877a0f215f13fa985c4b9fca1b2",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_3.png": "75f684ca4ff90e14c5c38dd44df87d4ec3fe6a5a34843cff79d7c8d70f57f33a",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_4.png": "1b52f6529fa25e26c8cfe50e890249db3c8e88064961da80e7a62a635dabc91e",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_5.png": "c1d6b4750b1f72185291aef4695a4398cb318f4c3fcce7c4462039465828935c",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_6.png": "8bd786a68260915a67236a8ca2500583b0317f12234bbee49c5bfaca9ccf7033",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_7.png": "3b403075cd67327b5f6e25aa0bce3e7a858ae0fd360efaae1bb8c27d71900bbb",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_8.png": "98d841237d395c4248b555fc57910452d034da9f43a66ce71e5a4ef892a77094",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_9.png": "455b8d996d1b7e555857c69c23c04c466668acbf4d55d0d60686e31cc8387839",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09H2_digit_arm_7.png": "e8aa701b948e5668cab133fce6dfd4566ebaeb77ad7d5e9d480e16363d7dcde8",
                "data/nfl2k5_glyph_fixes_2026_b81u/DET_09H2_digit_jersey_7.png": "a772a53be2788b16a985c59a95f68ad1f7f6c4d849dafa3f4462c9d0241bca18",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_names.png": "067984292236ef1c3ac36e33977586e874f4bb5f0ad8b940d613d1e7a91c9708",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A3_names.png": "18d1ebe9316a8d88bdbf5f55c1fcc6f673a8c3c02ba23ff5e3ce117cf81a1260",
                "data/nfl2k5_glyph_fixes_2026_b81u/JAX_12H0_names.png": "d143fe34ceca0e3cd387b6fd8774bcbb217947738d448566a4a7ae1360d85bcf",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_0.png": "9700cbc5867fbc92c2d74b48a7d763f6a2bd6f8d81c355966b6ff74fb3f4827f",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_1.png": "b8dc64a931a02383abb9a0e45522e1f68186ad8280ff3bd1aea9b1451154a1c4",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_2.png": "82bcba6a69f5b775752f5f8e48bd61b8f9155bc09adf59cb374077914e564f5f",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_3.png": "68a06a0660b228d8c6c3969d40d054d5c13c034a20ca0a54b666f4019f816705",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_4.png": "2317bbd2aa2ba68c1c4400eaef3b58cbb735a90f19719854a7660b77a99dfc26",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_5.png": "a81b815ee12ccca17b56ddbf0ce7511f542c4d348c89b21370298ba7b9856f5d",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_6.png": "caf9193b8a2d2e13cf8485ca6f435863eda9c50c77085e48e5c5c2f4821b8fb9",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_7.png": "09aeb69a77161ded4a8b62a080f0a83d6c7aa6a82f74b276ba8e5ae0df9b32e0",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_8.png": "abe397d895eee5396a1f5b140d68f93fb643a4efcf82d2da0d517b90ea441954",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_9.png": "9bf8bf05148f104274356037d6acb1953aa43526f2d203a05b9aef4bf86f926c",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_0.png": "88a51bd17650b4e3096a98a1de87d68ad9b0f37b864c66b7c2c08ec3fd5f1367",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_1.png": "1bb55a0e58f39f8625b183d1c5f0b95f63ef792dcb60741145b03eccf6ace5bf",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_2.png": "d88d0f7a742a441d859a5ee59fea72f6b814a982b25b184a2c5bf684838a40b2",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_3.png": "63183997f7a4d0f09ba48df20596b65fe6cd2bb172929ce4ecc10a66d043981a",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_4.png": "3edbf07fced3e963099f46d31a08b355e9b62ba537cce0aaf49a14358ffe7273",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_5.png": "b2637bbf5dd851cc61d038f74a057ae4d820e51b699b5760fa43a110b5992cf7",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_6.png": "8e9a85c5c5ef395aabc8b5215b72e2db77a8fc9a4e54e006fa7512988ead0211",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_7.png": "6daa94efb9631b3ef17d568e2e3f937e91719b480f722238eddc97e566297135",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_8.png": "30e73d1bf7cbdfc04861e8a67901f80c7b3a76e506c66de2bd0a3ea9223dad73",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_9.png": "cf1f91c2b811ceb12bcad08a10f9de47ce7796e63c473f618cb59bda81fe3708",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_0.png": "90bd565b16ec8194249784bfbc111290973d794f318c0b8504d7f4f35f98988f",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_1.png": "ebd174dea9b315978f63f55db1551d56bcceeae04d3f2067160c4a8666f229f2",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_2.png": "ee4ac50208c7a4ea1291d10da1e293ef4a49799aa39f0e3be5e7236e388af67b",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_3.png": "0aded205b3432e7be583851342b8d9536e91d2214a60993caa1689ecdc227795",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_4.png": "47fa972193f97cb841cd363f699c27cee58637f589a0988f5a580b875db73880",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_5.png": "88e4ca4928506c1b88db51c878ba335c2f217ab57d9715da3c41c9d727fe8456",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_6.png": "9aed328b17c7906baaa03df72b10c05598c676e7f88e31ac6f42bc9b885e3826",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_7.png": "7595f88660ba16a4c1d1dafcdb2fe1461824eea04763ea572c5a593a8a6895c9",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_8.png": "e67f840185a86ccf86dace33391a7f1c983f18fedb8471c43614a474d15032fd",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_9.png": "407be29cfa6347ca09cfb4a553b2aefa44e877de11bfe680eb080cc1da003ead",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_0.png": "7454e424721defc3d66b2604e27565dbdc919899b1c599b42e72eb626ebe3a92",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_1.png": "f75309cc844030d515a6c7daa183761be73a56660153f08ed0f4399dcb51a3bc",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_2.png": "97c028d788958cbcb88c01cabb61810c28f018a53cefdfc737b67987daa8b0cc",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_3.png": "e55bfe2476f6365484b7cab21ec647e183f27d67ea9262e74f364f8da17b2756",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_4.png": "3e0b987ec89e57e21d637d4b3141a48058f95d1334c274460e0115d277160d90",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_5.png": "7beb2e583862bb74ec9fb34cb9ba782803b1946cf900c6f8e69140a68e927c31",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_6.png": "39c3ce203899b25c93fa799284a7bb8cf95882bc23dfdcbf4efda5ccf558bf7a",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_7.png": "5e47ea14159581e34e5287ebd340fdbe220def8765926e08c494c7817ff48102",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_8.png": "940a092d5a2776bce8eb123f504939288d12a6d6727b23d0a72a961468fbf4b4",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_9.png": "4d0cb29b471686cb30b899348b2ef9dc545efbde6408b8c7c3d4338db68d94ad",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_0.png": "14d7bc9ce2ea84c8274f883b9bf3df7dce7d0dfca44c65c1c11edb81b5ad3de0",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_1.png": "84c16129ffa3dd301bb4a68ef1f05929d68366e2cbc6ea354ad58e9346203827",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_2.png": "6a63705c0dcc114305620b11b55cc28a1d617a68826c986f7588adb4306cf35e",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_3.png": "28af6973adb17015e752a575428959703d01d1afdda7dcec3d9940067f3da860",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_4.png": "749b78896bff567c55b52ae43ba4b926795bb379e5077c54756c6352b76b4f50",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_5.png": "07a45a13455ba19e7d663eacbdd87ce9fafe74261e883a2a55362589c804a3bb",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_6.png": "cd505b51852c91e35cdb71778b65330c3037ddb64a429723515d1a4ffaf66639",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_7.png": "34f8248e262c4ea3d8874fcdeb9f7d71762e39f899ef9c5b03983578a650bedf",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_8.png": "07e3e0203bbf73b75875ed36daef65ad62ceb272f3551d74e5cf225c3a77bb3d",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_9.png": "e4850068561851c9d088231c9dcabe4b1e1500a38321256a0a052bfca4002ed8",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_0.png": "9221970ed7e83c00c7421d0114de9ed4fe70c3b4db51cd2fc63c1dd0c9dce112",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_1.png": "6169a54d73b6b63a555cb50b48dd668b2e8469cd12903f44f75b52750809df03",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_2.png": "7814d5955592bac35b85edb8c962a469e500bd24bde2917e0d3fda5a851142bf",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_3.png": "6e36e970cefe6520cc8e8932627e0314ddd13c30e6354ae03cb5a3a0a2dc4b53",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_4.png": "38c6f937ed0194d60fb47a73632b206b6de3bb66ebf9464936b03eba620f2346",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_5.png": "5d863be30d5ac25da79ccce5525a8f6a6f1f6b640acbb9ec9f94c8eab9c3414b",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_6.png": "cb9899775442c027c9b93d7e93cfb94a828d9d4284f72d537d2a2fbeae1156eb",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_7.png": "8e536f6829a6a0d526df94191c8d45886932685fbf8ef19215df19e26a6918e7",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_8.png": "8eafecc103bccdc8eae30914dcbd2407b05211f718f41dcccf8a22f48630cfff",
                "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_9.png": "e75452eb6951aae52b7bc894efdee112bf105534f98a42d9b4a22a03d8e35887",
                "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_names.png": "b654602b173cb9cfbd30c29abcf77e7382e1d071f19073b7f2204a0b25bd8010",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_names.png": "abaf4243785a5f6f0b715323e91f713c118120c79dee39f9afe325f5a568c2a6",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_2.png": "d0fed3bb15c042590817430138497a70df7ace7c56163d32044afcf503ad2fef",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_2.png": "8e472e5e68e0aefbff4aff04c3e75cb3439d9e40af6a8ae3e7ba797308954ff5",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_names.png": "a076b14e9f2a5c4c80124083477c1b176c58e6168d77a95e4bbc766586b86986",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_2.png": "30b5d5c522f0c98bd5a08fc32e77f1b6fd73597bdcb9ad22523b03ce4debac3d",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_2.png": "4f028b55a539218e791db196e5e96b89f183f24a1336f83e220f2db61f0da4c5",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_2.png": "bd2db48b4fee62302330357d048cedb586a12d8b647ccfd8d140bf93c9884f2f",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_2.png": "65bbaf358df77e73d73665ff23c3783a74af3d57c0b7c868265cf7245de5402f",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A0_digit_jersey_0.png": "4e1b612ff355170a68ad41dcc67571a3921ff4632bec0b41c13033543d27e88d",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A0_digit_jersey_1.png": "1be4533843283c071646b6bda9fbaa01877b9b0c85b1fdce602d48f5f411888b",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A0_digit_jersey_2.png": "f2cec0e12d01030ee2fd3e3a3315951199ff0f283a9c97e9652df8af01e41452",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A0_digit_jersey_3.png": "50f1a9f41ba822befda6bc32d3b2a56b5ef3d06da71988ef8f5bd2efca7f6808",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A0_digit_jersey_4.png": "b20b49da83f608e1ac31bf47b7ec0da89f0f2b1b2742bbbfea555a5696897be8",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A0_digit_jersey_5.png": "886899f8fb796bc1c1fa4553caad08b4e78381d570eccc1766fa9d384c150150",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A0_digit_jersey_6.png": "5c01afdb3d453b2b4bfd62245965d776579a1db6ec640253a1f34d01b9a42b7a",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A0_digit_jersey_7.png": "2fc24d8e51628b1fabc14e536b7dab94fa52772b89ee4b31e3a20ecc2cacca00",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A0_digit_jersey_8.png": "e8e71c700598ba45cdf07efde346cbaa67fbab2b013fb59939bfddf345d870ff",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A0_digit_jersey_9.png": "f6e2900abf01fd4b1a3982812c53e55c999b48513f2a1d89e51abbe0bc9c6c25",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A6_digit_jersey_0.png": "64f073fa8987707e40703d62ad08b59d1c62384fefc8bc589acc0dc4f9b780ae",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A6_digit_jersey_1.png": "e9c0161b60d67905cd1754b2720358c12f981b445b264343585614703a94ebda",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A6_digit_jersey_2.png": "9d8896c96bcb9b13a30c82065f184d584c8aa9a2d9e922ec311ecc7f3f14a2d2",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A6_digit_jersey_3.png": "b4568658ae1a3f944bc8eea526d78f4cdb53c19352b58f121c0ff5c63696c8ec",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A6_digit_jersey_4.png": "45f54bb77475f2fe03342173a7f3fab40b307ecde333b11cbc22d127fcd74cf3",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A6_digit_jersey_5.png": "c57f268ffa400a958223ba388f28a9cc000bca5e2859ebae99baceac7e72d8cd",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A6_digit_jersey_6.png": "89544f3a907f1358c878323e7f2f978b9c51f1281072d9649aeb8808787787ca",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A6_digit_jersey_7.png": "69ea06ceab43d66134c038844baed2b5e4caf41ed2c6d30582f7fdc1323d74ed",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A6_digit_jersey_8.png": "b0a52e487df2780e63f4b3f272ca6836c396e968bef6af4ba1af8fa9a43ad289",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_CIN_06A6_digit_jersey_9.png": "d2bb58a7d7480c43eb5513a460aa4047323928c6d5b035ca15ec1addac368455",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_arm_0.png": "88a51bd17650b4e3096a98a1de87d68ad9b0f37b864c66b7c2c08ec3fd5f1367",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_arm_1.png": "1bb55a0e58f39f8625b183d1c5f0b95f63ef792dcb60741145b03eccf6ace5bf",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_arm_2.png": "d88d0f7a742a441d859a5ee59fea72f6b814a982b25b184a2c5bf684838a40b2",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_arm_3.png": "63183997f7a4d0f09ba48df20596b65fe6cd2bb172929ce4ecc10a66d043981a",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_arm_4.png": "3edbf07fced3e963099f46d31a08b355e9b62ba537cce0aaf49a14358ffe7273",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_arm_5.png": "b2637bbf5dd851cc61d038f74a057ae4d820e51b699b5760fa43a110b5992cf7",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_arm_6.png": "8e9a85c5c5ef395aabc8b5215b72e2db77a8fc9a4e54e006fa7512988ead0211",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_arm_7.png": "6daa94efb9631b3ef17d568e2e3f937e91719b480f722238eddc97e566297135",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_arm_8.png": "30e73d1bf7cbdfc04861e8a67901f80c7b3a76e506c66de2bd0a3ea9223dad73",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_arm_9.png": "cf1f91c2b811ceb12bcad08a10f9de47ce7796e63c473f618cb59bda81fe3708",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_jersey_0.png": "90bd565b16ec8194249784bfbc111290973d794f318c0b8504d7f4f35f98988f",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_jersey_1.png": "ebd174dea9b315978f63f55db1551d56bcceeae04d3f2067160c4a8666f229f2",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_jersey_2.png": "ee4ac50208c7a4ea1291d10da1e293ef4a49799aa39f0e3be5e7236e388af67b",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_jersey_3.png": "0aded205b3432e7be583851342b8d9536e91d2214a60993caa1689ecdc227795",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_jersey_4.png": "47fa972193f97cb841cd363f699c27cee58637f589a0988f5a580b875db73880",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_jersey_5.png": "88e4ca4928506c1b88db51c878ba335c2f217ab57d9715da3c41c9d727fe8456",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_jersey_6.png": "9aed328b17c7906baaa03df72b10c05598c676e7f88e31ac6f42bc9b885e3826",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_jersey_7.png": "7595f88660ba16a4c1d1dafcdb2fe1461824eea04763ea572c5a593a8a6895c9",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_jersey_8.png": "e67f840185a86ccf86dace33391a7f1c983f18fedb8471c43614a474d15032fd",
                "data/nfl2k5_glyph_fixes_2026_b81u/P2_MIA_14A10_digit_jersey_9.png": "407be29cfa6347ca09cfb4a553b2aefa44e877de11bfe680eb080cc1da003ead",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_0.png": "36c444dd9dee827e1a4ad72922ca182cf1fc0c60ea6f6bbab59a20e12e221661",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_1.png": "786873650107e86a357e5fde7149e73db3ac587f92be6b5e653f61841e75803d",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_2.png": "6f33559ab0101c6fb0147cd94dea94cc878f55a4c8a33561d3f125d2a80d34b3",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_3.png": "4a03284b68b1c91892c05a596e24bd966fb4657c3278a886f9f344920493f71e",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_4.png": "91819b14b493e34e36fdd971bd7b91ee7da549a87a30cfbad3bdec749210ba73",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_5.png": "6a528b873cdd0dd91fa47222eab1166b1201b592fb2501439582e579b3a2f9f5",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_6.png": "7e595fe39327990de270b3231e5912a50e02fa341b2c5b577eceab1cb0f289e0",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_7.png": "356ebb00828c98c969615dd02290557a598babe442efdd3832ef8a497663aadf",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_8.png": "0a4d10272792cd4756481b07aef25e045981fb294e7222ae763d8ff5b2cb6bbb",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_9.png": "f1fa6f3aeab6ca2ee77a12cba075895e3dcfd6fe636ad48da30d7dab570e7c89",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_0.png": "224ce36677900dbf90ab78013556b0536a3537ea1ef9d90bfa54a249a0e14a83",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_1.png": "97b4bf9f589ed85809d424521373e8aa89c15abe2d9ddc86f3f5c46bd3f34124",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_2.png": "ce5f1fa3ef3da744297e0f1274e6a56c44491dee6e6e8270008e6739c8d20e3e",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_3.png": "13aa5e89bfeda627116cc3cb637af7ca92b90c0e4fc0738f313b847de5a3fb95",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_4.png": "0307e749f20043c7d6b5748449d41ac8d537e8128d0d032f690709ae7b0fbfc4",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_5.png": "c3fd8bb3460a502fd27f89dcb82a2ad7838998feab3c486331d4f7ecaf7f70ba",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_6.png": "417f6bfafbf4ddcc019b73b641ffbacbcfa602a0522eb755ee8a73154ae39ad9",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_7.png": "8f961d4ab6b4f32793ea9edb50573b88487b582c1570fa2ab21098240e0fbaf4",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_8.png": "f3870c1edff1a13a764d4af4f899e41829fa0d043d2971120169de9bfe1eca0d",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_9.png": "ecfeab28195b27c20219bd9353e55be58560f28222f085b3ef52d894dbfb84bb",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_0.png": "891e4d0645aca00b91b1fe6a308445467a978711b82f5256b47f0814e12d2c54",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_1.png": "15fd02429d8c881254d33cb567f4dfa36b880cfddd687f3252e754a67d0d0cec",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_2.png": "f2947f4d0674cc51528f848f2a2e4306f35c65066ae75f22ecd9416f073c189d",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_3.png": "c519e11a879d7b000608237dd32a9def57065779834215f667fa01fdb6dd29f8",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_4.png": "9543b6eba7f37fdc58af469eb52e2124645f24225bc204a994bd347b9b8a3f3b",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_5.png": "5fb68b1f8f2979ab1ac2e6686f8c9ba0034936a5679a3e308a2da5f02d240daf",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_6.png": "c455a918c11e199e750d71c9ed09eb9c40594b2760e9388f335b962df19395a7",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_7.png": "a2c0d3bddaa4118019ae7424433020c9304bcecafcde95552005908c9bbb83b3",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_8.png": "a43057a5781aa22f9c501800dd9d367ac86a0f5061ae0ff32b968c2aa58c1e54",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_9.png": "cc3ccb2d8925db2d28f66a98a87f4645b2f9ffadce4ac4408860ba03a27aaac8",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_0.png": "b799cd20012a45628ee4c2c1a1373bc30c09bdbfbceac9ae0e1ebed1e7a5995e",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_1.png": "8760526e4751c50e04ac1ac2573ed39ad5b2c53f8905bb519c62be6d860f7b7a",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_2.png": "7fe000e44b8ddfd418f8b8579f9cb5ba1c87099c53fd50f521e701316799d1c7",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_3.png": "f85f6f478150c37cf8f9c3ae1eb029e9492287a52c1765a81cca51d0e7d49606",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_4.png": "dfa888c450f1b963d9d17ec33dd57f8eb685b1584e31511d801652dd4e53a7fe",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_5.png": "7adedb21664547504fa4eba995b821799bffb1626c664d6721364659f83b3277",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_6.png": "b7fd5476540dc9e194f4fcd9eb60e14629e93675e82140733fdaae545e42457f",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_7.png": "96893120593042089f6ad2a2e97c5739ee5f53f6a5d65a7e92dee4029667febc",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_8.png": "5834598c952b7258eaca3aba78f21a54fb191fc3e5cc92f7212edf3700c681d1",
                "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_9.png": "cfc4e6fdc39e8101c77ec81dd524665e3909772d77d8e572c4a65a1bf58dbaf0",
                "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_names.png": "3865b3c9a807267820d78b99a297046baaf10581e0d64e1cfdfa5f821aafc139",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_0.png": "6aa01acc5a56e677cdbcdc72da1b28ea516c97e1a9ced5d245702016edf8ebb7",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_1.png": "64fd06af6bb93bc40b7df2bb5fd1054b9944e7c0ae25be42f1eadab0d8ad94d1",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_2.png": "94af7fef0df5af8927e649ff0cad3cdeb9eed269fe668c1d32f9203cad2f6bc2",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_3.png": "c8c0247de22449de33370d03979984b72bf14633ce771b6824d29dd4c8476135",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_4.png": "6940c97d59e6afbc359cb3b5160450884d9f5b473ccf522a76b2ef9dbd80bcad",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_5.png": "1714febcf1e12de93c7deb92f2c1314077d41e46a12a0325261b6b45033317ad",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_6.png": "3c24484eaee1593bd3816fb7b3b6b92d84ac5a06c12bd705d7881dd934f41c1b",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_7.png": "05f6edd7aa8ac85aa00a958f4103eac28cfe7e04871cd7c9ffbe07e11eabde83",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_8.png": "82a45cb22b7d7da34afeacc1497ee048ce170325b878ceb3f89d9e18a7e24c5a",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_9.png": "7ada4d852ee5b84106294425387973457f13cc02311802e0a2a05478798353d3",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_0.png": "a2d641093d145247f216de24083b7d1438dc871ed27dd577e9181c042c043914",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_1.png": "83a530465269c88986635f3e7ee0713332148ad16094628d299b952f9f70f9b4",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_2.png": "e1aad4fad0034f4e42c14d16add8f09b5626bf9a47b49b489456ee5ef45cc4dd",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_3.png": "8742d99fb28cdb9a73be8c26a46175d95572c5ef08a2ff75874f94cc8036422e",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_4.png": "1d1fa9e4d5bc779add22fdb6730a570787ba54ce29e8a9efe025920a891aea63",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_5.png": "ab86fb70d41064d0c01a74a491b4116def644e5d65bbef6593ab0dbde424afde",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_6.png": "c13bf9cddb161ab75bdbfa1375969d55b8ea0acc370b34db63c40eaa4da01ed4",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_7.png": "34fc69d02c88c01d0d63d01821885e4e8ce5387e44378169ff72166c596dc87f",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_8.png": "5c1385b458f26e11bc5d04bf9884ca1936f74fbe42144c0a0f7a03c4fdeb93ec",
                "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_9.png": "c75073a37930a06be156832835ba4c8bf6821a5cb4342f3514b288d40c316add",
                "data/nfl2k5_kit_fixes_2026_b81.json": "d2a9e3239050947bc69a4ade58491b3578e3859d841831749dfd163ef24d2da7",
                "data/nfl2k5_kit_fixes_2026_b81u.json": "9195c523e9d8188aa90bd10fe30d0c83c35c604f4b66bb2916dbd65a8e259587",
                "data/nfl2k5_sideline_2026_b81u.json": "5ab2db190a2658d0e6d8be6569b1ee3930fcd1a9ee6abdc80cb19c7b12352ef6",
                "data/nfl2k5_relief_2026_b81u.json": "b4a07b3efbcba1d8e63fc2af19be3f659b7503dce027b4445ae33f6dda17b043",
                "data/nfl2k5_relief_2026_b81u/difference_jersey.png": "f4d24e2c69457b2b08c9ffb9fd9e3c023bea9d41e342842907b8286323f28387",
                "data/nfl2k5_relief_2026_b81u/difference_sleeve.png": "31bb10e5979ee53b022816f1311b4d53d949c606d888186ac85103104b1a7983",
                "data/nfl2k5_relief_2026_b81u/jersey_08692d8525216e39.png": "83de69541844bb9855916ae0c42cd42c006832a7df90d14a94b29a9e4c9fd8a4",
                "data/nfl2k5_relief_2026_b81u/jersey_0b8d56aabd0f8354.png": "f446e07f1392406683bba1a1f3534580d9b3a1d55001695bd8f09a0093bcf03a",
                "data/nfl2k5_relief_2026_b81u/jersey_0ba7a3e6d1c29068.png": "fd95bef1d517f2ba2050407639c5f27c37cac2293f55044a43ee2af9d6a3355f",
                "data/nfl2k5_relief_2026_b81u/jersey_0d21204f5c3849c3.png": "059ac18032b4ed3ab18afc57be8c554e0125c18ad61a16c4e0c6ea53eb455532",
                "data/nfl2k5_relief_2026_b81u/jersey_0eb216a3513e479a.png": "2c8157e254fde93a00e603391267515589d655989961f008c1e0a61c55566cbd",
                "data/nfl2k5_relief_2026_b81u/jersey_12de006ac81dc5c6.png": "77446def5f08837e66fd46ed189c761971eca60ed9da018fd359b385eb57c2b6",
                "data/nfl2k5_relief_2026_b81u/jersey_131b6886dc0f5f18.png": "1ebdc48fc64cb73c7acb8bd40df15133a02248e2ee3d95e59ce92db247ccedf8",
                "data/nfl2k5_relief_2026_b81u/jersey_140fb7b1f9f97f4d.png": "cf9671b82ab24153d1e39e5f25d6b721790f8ad22326142e7936236c7daa7c07",
                "data/nfl2k5_relief_2026_b81u/jersey_14e5040f10a441ef.png": "be07a96ee806e048cec7663b6078c7d18c41504579041b7eda7ef8d2182f5e32",
                "data/nfl2k5_relief_2026_b81u/jersey_16826bc7e52e00a4.png": "4ca77721612f2103e2ddf4183f5b63c16a1e80c2168c8a8357605c7e60580d22",
                "data/nfl2k5_relief_2026_b81u/jersey_18516cd4b1a96ca6.png": "2089b8550fa77fe11a7e44c5969924e99a368052a13f371eebb73578f74460dd",
                "data/nfl2k5_relief_2026_b81u/jersey_18989c0dacb5150c.png": "b56d09a20b7512d91aa8af2d67535e31635e0c9b37a4f03651d8d316730c27ce",
                "data/nfl2k5_relief_2026_b81u/jersey_19b9ed41c01633f8.png": "fefb8748276e57e2dcf56197a26dad1d7888bd650d0e8e716e2818c0bfd8a3ff",
                "data/nfl2k5_relief_2026_b81u/jersey_1ef55d30f6acf6d9.png": "74acaaf643fadf7702f967c636cb10824b8e193fb1fbd3a0fd29a02e2956ada4",
                "data/nfl2k5_relief_2026_b81u/jersey_22b824c01d021eab.png": "0f71596d2c4225c48476e1e89a47e55901436c39bb4db9327cfc7ba9bb5097f7",
                "data/nfl2k5_relief_2026_b81u/jersey_244f0201ac6384be.png": "351249e2cc40ad7f432e314a09122f4497d7ec5c281b0c1ca5a3cb615a6ab3c6",
                "data/nfl2k5_relief_2026_b81u/jersey_2c6e0134b164f8cc.png": "544260a747b05b11822de8982dc61d9863de88f482efe24a32399afbd942f5e3",
                "data/nfl2k5_relief_2026_b81u/jersey_2cf31cd760243619.png": "de99bae4696466b925dc80ae32f83acf2f1d09915c6c38adbf4d8c7a10249b5a",
                "data/nfl2k5_relief_2026_b81u/jersey_2d8277456186c227.png": "7d26087b034f775dd9489c9a83ecef50361bdd38d02f1d16e00a5f10712ee243",
                "data/nfl2k5_relief_2026_b81u/jersey_384e4b887440dff4.png": "a01809417fe1942df7ce76a9587d3b462ef4c02ab4d9e04e2da6bafe316788ed",
                "data/nfl2k5_relief_2026_b81u/jersey_3948f848caecb780.png": "3d575cdfa6c145cd8b48ae15bc45c7e6f2b126eec2421025353d18616104803c",
                "data/nfl2k5_relief_2026_b81u/jersey_3e22a07846126ecd.png": "16344fd6160801b49cb4e24f29d4984175242b6824b531205c8c816a82ce3fc8",
                "data/nfl2k5_relief_2026_b81u/jersey_3e713ba1b55e838d.png": "6e6cbdc2dbc0374c877b473de87d13a8f5b0cba2eca6dddc2f6ce0b3cd34474a",
                "data/nfl2k5_relief_2026_b81u/jersey_41d83fdc3a78fa2f.png": "1838eef88586a8ac6e7c5c22e62d73a56a21fe62c868cceb15a76b3b08ff9f61",
                "data/nfl2k5_relief_2026_b81u/jersey_461ac369e3dcb21c.png": "53500bb36fa3e4abc2fa09465e86fef8434f8a0519b2c07c5c5dc65c327795cd",
                "data/nfl2k5_relief_2026_b81u/jersey_4726bbd20e019079.png": "8520f633dbc33e55e42ad1177eee8f6ac13f00c74ecf3dbe32f93126e01e0182",
                "data/nfl2k5_relief_2026_b81u/jersey_4c6cd8beee2e6267.png": "05238b3d5542e2601ec9207fb3ca1544e4be7aa0e1b322120a3aeafabc134ead",
                "data/nfl2k5_relief_2026_b81u/jersey_5082c749b41055eb.png": "77874c83d059678ccad5c5aedd3c6b668c3ddcce76b3e411d72d8621ff62cced",
                "data/nfl2k5_relief_2026_b81u/jersey_5e48e191aea80550.png": "b4737607b7e543e476fa79c1113463a83af2e8f016030ab980f4ee35ee71409d",
                "data/nfl2k5_relief_2026_b81u/jersey_6d0cdd7cec29664f.png": "e6c6659617d28f0b0fd8c93c29eabbcbace996b3752cbdab3b634250e59a473f",
                "data/nfl2k5_relief_2026_b81u/jersey_736cc9431ce86755.png": "b2492704215af0af65266a34670f2a89e0b93b07169d495977a054bc213630a3",
                "data/nfl2k5_relief_2026_b81u/jersey_7408142d920e1f4b.png": "2b919791045ffef66c31415b02f30834f88d5b469864a9c4eca5bed5bb1d8170",
                "data/nfl2k5_relief_2026_b81u/jersey_77e4974464b42d48.png": "2d3cfff639cf4d93e381338d65d001eabc3acc3d3720d503c054730226f36448",
                "data/nfl2k5_relief_2026_b81u/jersey_7b41ddd869297400.png": "a760fec25172752548bce8e802b3b47d51f198fbb0ff9a697abc94fbd7464ac3",
                "data/nfl2k5_relief_2026_b81u/jersey_82a495e1861f6c8a.png": "547c1c7db0047dc90a1bdcbb48c60cc98e120b8c2cd542562abbed4abc7ff3b2",
                "data/nfl2k5_relief_2026_b81u/jersey_8b222bbd9dc9783d.png": "e53a9bcf4a3acf363bfeeffe4c1345aaa5b521da31e81f55f548cd071ce52c27",
                "data/nfl2k5_relief_2026_b81u/jersey_8c564671b7b541b8.png": "7c1dd45aa94b4fde006a06d9b082242cc10aaa28b3af522e694dd1248184ae61",
                "data/nfl2k5_relief_2026_b81u/jersey_8fd3161f301cd916.png": "e3a868879ad56b20e2bc1e837f559a4e78d2c40d072aeb802e443f65a7b73fe8",
                "data/nfl2k5_relief_2026_b81u/jersey_92d27871d7a6867f.png": "ec83d1bd95dcdd1fe22d85de030d7e9283b0b15fbc076672473ef3be2e7e7513",
                "data/nfl2k5_relief_2026_b81u/jersey_9790a6c43112c18d.png": "9e928b1ecdad1affa3dd6f7d10688515ca855a3c108dde0afff6de48b09f4a90",
                "data/nfl2k5_relief_2026_b81u/jersey_9dcaf7ebd3674e85.png": "95318cf2429790141183eb45e63a6147b1cbf5347a1e2a312bb4571bd0f9c203",
                "data/nfl2k5_relief_2026_b81u/jersey_a561ebc9412ab5c1.png": "ff46ef835507321526696244236511123ac9a51ab753098267f1463c6676a260",
                "data/nfl2k5_relief_2026_b81u/jersey_ab25a27ee05818f1.png": "0aa67a0e142389c8caa227966e283dd29cccf9dd80fd440eef24c41f9026eae9",
                "data/nfl2k5_relief_2026_b81u/jersey_ad5fb03606e3394d.png": "e4e6b213d386b8779c1f8e2da64c37e6775363644ad9f3a2d7845323ed0e9b00",
                "data/nfl2k5_relief_2026_b81u/jersey_af59448ec91c9f16.png": "35dc1a939225bdb5690c12eb986e5f894eac481b6229b43c1b43ca20750c4768",
                "data/nfl2k5_relief_2026_b81u/jersey_b042398fa43cb6a2.png": "7dd5eb9a90c6e1240c6c0c6fdbfb8be2a7cf8ca21ff2845735fe56dea96f0593",
                "data/nfl2k5_relief_2026_b81u/jersey_b053e944ef9dd7af.png": "e6f9b5599564821ae38cd991b5585fb8a41712528145074a23bd4b444fe54432",
                "data/nfl2k5_relief_2026_b81u/jersey_b154879c850ece81.png": "8bccbbf0af99e9f51c1064ba5b3df256798f672adb8244250d51e3b5448ba49f",
                "data/nfl2k5_relief_2026_b81u/jersey_b3b835b3b6b37e88.png": "95563673e21586f0df5066dbbaea2fe4a0b78b1ba5035593a28153dede69ffe5",
                "data/nfl2k5_relief_2026_b81u/jersey_b78c9e5dd7bdf949.png": "bf44d0a96c9c8fdd96ed0b704940779dc493b8725eeb65d95526e5ff1bd61e54",
                "data/nfl2k5_relief_2026_b81u/jersey_b9c3cc83469e54c3.png": "dec1279b3e1755ce13218ac94351b79c33cb2e065a9e5032b417b6bb3788d616",
                "data/nfl2k5_relief_2026_b81u/jersey_bf5eea286cc8b60f.png": "2d5c7942a50c0230b793a80b3cef82dfdc227e900d7ff23d672431d12fec3123",
                "data/nfl2k5_relief_2026_b81u/jersey_bf95f005f2aae3fa.png": "ec93099d2ac9918237b7b31cd500586dea6baabaa1c440746aac6a4d5bb73d78",
                "data/nfl2k5_relief_2026_b81u/jersey_c080279fb66c2095.png": "878af510dc3fa3637c9d01a30a2f3ccc3a7227bbaaee34e8bc0ce88076efa32c",
                "data/nfl2k5_relief_2026_b81u/jersey_cab3c2d38af44be7.png": "649fade05c6ada8926273c39b766c11de91f0ced09dff53c7ca3188c448e8e7d",
                "data/nfl2k5_relief_2026_b81u/jersey_caea56ea9e36e2f8.png": "c87d807ee511e7da418588880e21e2db81181566a1736641540c40cf68e01e87",
                "data/nfl2k5_relief_2026_b81u/jersey_cda2033cea659c2d.png": "5ddf74cf733b2a3dc6c171094997797ff5e0763c6f0614aa18dbba4f26b0e3ee",
                "data/nfl2k5_relief_2026_b81u/jersey_cedc13e8672f341c.png": "a416a2f54d0861a25323e275d517888cb0fab32f36d3c2238c61bcf103239b23",
                "data/nfl2k5_relief_2026_b81u/jersey_d6bd4fcd200880b9.png": "9aea6a2fd005871d7a3ccbd7bca1f8a434e6576f8482ec7fb35635a72c91c8bf",
                "data/nfl2k5_relief_2026_b81u/jersey_d7892f3ec43f37ae.png": "5c7bbe83e05c839b08acf114ef17d8aa1458e53da907973adda8ecbabebd3258",
                "data/nfl2k5_relief_2026_b81u/jersey_da9e396ab9e4aab2.png": "9b66f4fdb0e72ba66c9ee6d8fa2a744fd8d1b6d0bed85b7409e48ac5ced7e2ad",
                "data/nfl2k5_relief_2026_b81u/jersey_dabc0ecf69e73826.png": "902046f7975b9bebcaff78ba0b77059c91b36cec27c41f7a0430a674689fa1ed",
                "data/nfl2k5_relief_2026_b81u/jersey_df00cf5771c47901.png": "33f3d263e9305eadcc18cabc567e0e7fc7d66fb5dcbfa2bdb87267ebe5ef13d2",
                "data/nfl2k5_relief_2026_b81u/jersey_df32c3595bcf208a.png": "293a2a097c63fba292ae4dbf211d20c46d7e296f9c5e716337db835d6e36e938",
                "data/nfl2k5_relief_2026_b81u/jersey_e195a0de3ece9c53.png": "2489e1807deae1c3fcef1f32e5edccef800968e3a24cbdf6fcf6e0a0daecb4c0",
                "data/nfl2k5_relief_2026_b81u/jersey_e52aceef5be0387e.png": "425ccbd3f53f5da90bc74b718686e8e444b42f34a41c518e53730f2889211729",
                "data/nfl2k5_relief_2026_b81u/jersey_ec4fb0e9601298c4.png": "536aea9b59b71cf190511cf153ba1166aee43849edf2735f7a7d4448876298a0",
                "data/nfl2k5_relief_2026_b81u/jersey_f943fbe2833ac088.png": "bc126a18096cf36b7818be62cc3af6e8300a4f0894f84fa90633ae1a784c20e1",
                "data/nfl2k5_relief_2026_b81u/pants_1411994e5bb854ab.png": "4edc24bad262bcc187f52aff21b6e293734396ce7532652e462977857bb3d286",
                "data/nfl2k5_relief_2026_b81u/pants_1555626dd3db073a.png": "14f903d96d3536f5fa261972f771ec1160d79cf01d4e3f1c61a58b41c43519ac",
                "data/nfl2k5_relief_2026_b81u/pants_178fc03d1e379755.png": "d6cf2577a89ffede5c0ef93bcd569c18987bcbf26db0bd2ccc0a9577694e7db4",
                "data/nfl2k5_relief_2026_b81u/pants_1ef2c1a114131279.png": "898f5a24c0ca1bb58741c5163bcdf1769ae6a79736a957e056313dd7919cc4b6",
                "data/nfl2k5_relief_2026_b81u/pants_2dcb91c3595d2845.png": "e26ba83403bdbd76cdc929bfa4d04005b6a391ab921ecaa563824d0ef5085128",
                "data/nfl2k5_relief_2026_b81u/pants_30e2233a0551b7c9.png": "8f140260a106ca8e8f4b15178610f7b631e9283d773581d060b68e77164df0e1",
                "data/nfl2k5_relief_2026_b81u/pants_322f9f8e9370e3fe.png": "361b2876826eeb2c7d28aefa9ec1acd38dd9908cf0efa048847c2b3a409efe00",
                "data/nfl2k5_relief_2026_b81u/pants_3cdf334575f2f3e4.png": "9f43da6d77dd86674b4d2691636f995a58aa8592b35e2a491d78583e18e6d5d0",
                "data/nfl2k5_relief_2026_b81u/pants_4b7536c685a24068.png": "bb074af332d5097b9c0161a908ccc3246cd4c3f38544f37b66ebbc6dea35f787",
                "data/nfl2k5_relief_2026_b81u/pants_4ba635e1366c75e3.png": "02471ff26e88ec3b6b53fd231808a5cf32a1c7a146852243548eac5666b8b104",
                "data/nfl2k5_relief_2026_b81u/pants_4cd526126a2c14be.png": "ac76ba8a7a68f677a92fd4e279a804faef897116a59b90eee10bc2b36f75c21d",
                "data/nfl2k5_relief_2026_b81u/pants_6000ee94ca2bbeea.png": "b410cfb8e520db1b9ff931e304592b1f549c9e120f3378b3ca88007199058c67",
                "data/nfl2k5_relief_2026_b81u/pants_6de22667d7875b69.png": "14d9ad6e3562569a9e4301b61aaf963a969aaf54b17385cde1f42a3093f13f94",
                "data/nfl2k5_relief_2026_b81u/pants_75847d3c3f0471b6.png": "a439456941fc4fa9e6149561d91da2bd4ebfafc04865c8e57ae188c0cdd8679e",
                "data/nfl2k5_relief_2026_b81u/pants_7d969eeb03d6ff88.png": "ad61cf9b090dfcf55a38a3ea3183e1273d297ccba94292111c5c13dd5b9bf03a",
                "data/nfl2k5_relief_2026_b81u/pants_8daa16090c56086a.png": "a0632bcc9d71a5dab06955ac87f2f84e98c2842b304648eeb33b77d7f794490c",
                "data/nfl2k5_relief_2026_b81u/pants_8e504d76ee1e5bc8.png": "57c8e518fb5a1e275771000920b41d45ff76ed3ba979818263afb2f5e7a0e5fe",
                "data/nfl2k5_relief_2026_b81u/pants_9ab60e414e773e37.png": "1e39171df921f20abd69b92bd7ad6b73aa0eb1eff9456dc2d466381df8d7b8b5",
                "data/nfl2k5_relief_2026_b81u/pants_b2e21f26231984e8.png": "63cf6bfa7295966cb032e24cf2570bcaf7d32df8236e331705dc810e87ccb76d",
                "data/nfl2k5_relief_2026_b81u/pants_b5aeecfdf31c47aa.png": "0eca9baa66d6126f8afbad78ea414d5f9bdc060201a0f0b547118d06e5c6acaf",
                "data/nfl2k5_relief_2026_b81u/pants_c3d724c12f92c711.png": "bb5070622c73a161eb03f6e61e3eb55708c73589c5b945b5c93f613963f5612c",
                "data/nfl2k5_relief_2026_b81u/pants_c9af6728914a8540.png": "108568b5e45ae068b78ffd78f6fa2efbfd3177d2cf16178a5a943fd804cbad91",
                "data/nfl2k5_relief_2026_b81u/pants_cf6f939940d9ea82.png": "42577622dc0a9ac719feef112d87e8f570112fe121a09dc46dac6ae72b3ed0aa",
                "data/nfl2k5_relief_2026_b81u/pants_d0ac9f3e4c4460d1.png": "fbe19ae66ad2200871bd3542ba5a486d39051690f85da28993ff300243c43061",
                "data/nfl2k5_relief_2026_b81u/pants_d5af3eb466a3449c.png": "86f3f7f88c38cd5f81661125b7df988a9bc77ed8c16912bdcd40e91d584fa3f7",
                "data/nfl2k5_relief_2026_b81u/pants_e53d20841b96af46.png": "ca314ad7679a9facd251c47dc16d249fafb1475820f80d96318987ac75aa8012",
                "data/nfl2k5_relief_2026_b81u/pants_e5ee9c2b46eb8b5f.png": "b87a79f444aa8f72682f5c064d15f9ef498feb7faf546c4a09ed128d89e7adf4",
                "data/nfl2k5_relief_2026_b81u/pants_e99b20458c7d11c1.png": "58e145d937021a174139fca407be147be0321786529abd0f617d296e945de6db",
                "data/nfl2k5_relief_2026_b81u/pants_edbd8e96194309ff.png": "1cac0f863bc703b46553157ee05a76d94d03da0cada27f345bb80a5c170f801d",
                "data/nfl2k5_relief_2026_b81u/pants_ee4e23ee718e55b2.png": "82be4befd5611d799c2910f4c883149ab849ee7f2cbfe9c53d056ad46170cbaf",
                "data/nfl2k5_relief_2026_b81u/pants_f13e4152edb77a81.png": "01ec9cbfe6a44063739ed5195ad20d266f6c749e6f2a68c182a0fcefebd6b9e2",
                "data/nfl2k5_relief_2026_b81u/pants_f7c5c027a600889c.png": "0c03f1c01e24c185b151e8640d25ac7e6dd0b22233e006e81ef2f4b34fce9972",
                "data/nfl2k5_relief_2026_b81u/pants_fc27aaf9d3d32732.png": "d88f83bc34e39bf68fd7c1cee098a47b1da28f29bbe6a71e69cea0cc1131f6b5",
                "data/nfl2k5_relief_2026_b81u/pants_fd2661399a5a3975.png": "3da5c7fe008508fdf14075acf716eb001acf0669be3dd622659d289dd8eeba76",
                "data/nfl2k5_relief_2026_b81u/sleeve_0374b17fa6b479b5.png": "ce0a86ddd2e2f385996001b90b9d8ec8c2083dd81db7eeb12c43df9d503d7794",
                "data/nfl2k5_relief_2026_b81u/sleeve_03fc94aa1c403d7a.png": "e268d4618479976b57858fad20666084a038156c312eeed92a613c74c67b8678",
                "data/nfl2k5_relief_2026_b81u/sleeve_07eadc1c75d1d45f.png": "dea2e4d2bf8b0485fb7e5c68a71da5951c05632d095fbfb2b7c03d1474d93c4b",
                "data/nfl2k5_relief_2026_b81u/sleeve_09fb74a53cbd2d0d.png": "0e88dfcf5dee0aea72e1d62cf31a4ea88cee279403004ba9a4a977b18c356ea5",
                "data/nfl2k5_relief_2026_b81u/sleeve_13bb28b56671dc09.png": "cb542d623ffececf719659e0fef298904732b81628c5788a16f86c5c40892a07",
                "data/nfl2k5_relief_2026_b81u/sleeve_158b9c53ecf6741d.png": "ae282445e42a4c2d45e808f0ffbce48b22dbe39e2055b4b04a562b7f44174ec3",
                "data/nfl2k5_relief_2026_b81u/sleeve_2914c1be6dd62322.png": "69cf4e7380af726829012c01612bb86c4edf702ae8074cbe9f4bf417dff09cfa",
                "data/nfl2k5_relief_2026_b81u/sleeve_2c0fc7efce985e6b.png": "231ba0c0b8d0430cb433e67702beaeea1029463e2e27f9d5781db97fbb5f506f",
                "data/nfl2k5_relief_2026_b81u/sleeve_30d2990df11270fa.png": "cbe0c47d2b9bfc866dfc7dddf2d1215f81f1fbaab9b2ec8622089663c0e64365",
                "data/nfl2k5_relief_2026_b81u/sleeve_3c3b7fd4b1255738.png": "34c9b2b5358e11237d37437d3a973599338b79dd8e44bbfc5261738404e60dd9",
                "data/nfl2k5_relief_2026_b81u/sleeve_3e005454b26a78ff.png": "657f5a3118644cc188f44bf5a5282e0e0040b315bbf9584f7dbd6558f8cea280",
                "data/nfl2k5_relief_2026_b81u/sleeve_3f36ff5c03516dc4.png": "3a063b5479af773f770f6cd5c873bdd4f55fe5d2f5ccd66a0f0e15363737118c",
                "data/nfl2k5_relief_2026_b81u/sleeve_4075d7efeecb3e61.png": "3bc448c9dabd45f1c892338d116904a50b16f87497ecd84f693c0a7816f67c25",
                "data/nfl2k5_relief_2026_b81u/sleeve_4829cd928f65b3dc.png": "6ca118e9bc4706c9f2a6184ae71d7529ba5035beb71b174f950030621bfe45ce",
                "data/nfl2k5_relief_2026_b81u/sleeve_493e471a7250cb4e.png": "44be105d43c6c2ece83afc0a15ee1a595bd8bf732c4412f4a804cba30c162ba7",
                "data/nfl2k5_relief_2026_b81u/sleeve_49ca4cdfe5bff8c0.png": "9e48cae7ac7b2178c82e0fbacffa421eb2936ceb7bc2c618ad84522b86b34632",
                "data/nfl2k5_relief_2026_b81u/sleeve_4a3d4696df40b40d.png": "61db59b9e17f25ea3d5b00c29a1384068df68b096d6b3bd7fee8771df43ff263",
                "data/nfl2k5_relief_2026_b81u/sleeve_50f177a9a0c965a5.png": "38723e0fa66dbc994fe5ffd24ffb9b09ac8fc61bb49043b1647867d866d02888",
                "data/nfl2k5_relief_2026_b81u/sleeve_527792b0e073c74e.png": "051ea8006f6f95cb1e3fa97a9a6338ca301e0ec26f2d16d8782d20cfe7cb41a4",
                "data/nfl2k5_relief_2026_b81u/sleeve_5963b98385b838d0.png": "597cafaf34cb7f696eadb49121494bd90d273244b7926d99a04c4da7f92ed503",
                "data/nfl2k5_relief_2026_b81u/sleeve_5f445f0ce96c35aa.png": "0c8795a0c2408c376f79851d6e39c9c271fdbb9d82ab491bb4256874981546d1",
                "data/nfl2k5_relief_2026_b81u/sleeve_65a655ca657c8695.png": "a21d8548837bd8805390ddc0740c5078c1d8e2c0c00f7ef29733cf5dc03a7702",
                "data/nfl2k5_relief_2026_b81u/sleeve_65ea0ccb1356d723.png": "e0742322e9adf26c1c8875da685b5843905288cbef48c5aeabd6c33a60634622",
                "data/nfl2k5_relief_2026_b81u/sleeve_69d8b4f0b06e300c.png": "7f629fa1669b5f0d6463ac683f241621a4076ff175842b70603da1f2cca845e5",
                "data/nfl2k5_relief_2026_b81u/sleeve_7fc74e56d5840fb1.png": "8ad14b8158c43144f50008d1571ee552e32f45fa23dcc1697b01a7fac2b4a8ec",
                "data/nfl2k5_relief_2026_b81u/sleeve_854cf38dbbbc33fc.png": "7410d142c7dc5a78e1256afb1c0de0680e3e8ea23ca273ae6efdc45c51e3a1f1",
                "data/nfl2k5_relief_2026_b81u/sleeve_8992fc8a8940e640.png": "dac5284faa0212f7b98af5dcc3c2219fc92e66ede219785a6f6d0ddc7613bde6",
                "data/nfl2k5_relief_2026_b81u/sleeve_95bd7da6e3342283.png": "2716dfbb2156f61a31df73fd39c9519f8f0eac6761f6f9113301db65d8b626c7",
                "data/nfl2k5_relief_2026_b81u/sleeve_9763a09bac19428c.png": "31e69fbbbd0fc3b34102833a8f4fba16f9320c4f3eeee8c85a2c9a8662b7a18b",
                "data/nfl2k5_relief_2026_b81u/sleeve_9d56584a6e003663.png": "184ce8b94aca17a9c91d5ff432606fa1b532232ff009b7a1edb96fb654ffd002",
                "data/nfl2k5_relief_2026_b81u/sleeve_a94bac78330bca54.png": "459a07a4d7ed2811b96379227e3ceed266c60c36d0a7489c11e6bae29dcd81c9",
                "data/nfl2k5_relief_2026_b81u/sleeve_aa995d8bad5a175a.png": "a6135c5eab1f88321e6deba93ed8a7e7fbbf8cf211954f5201caac881ffd18e5",
                "data/nfl2k5_relief_2026_b81u/sleeve_c103284c58897bba.png": "19d03d2bd16497d93ea2e60f8da86afa85d56cce2b621d2862d8f7772400fd4c",
                "data/nfl2k5_relief_2026_b81u/sleeve_c2526fa7bfd55e99.png": "3a0bac8087d2339e1fb6b752838f7015de772cd9e25db028338e4ca4896529ab",
                "data/nfl2k5_relief_2026_b81u/sleeve_d2fe5151099cfcbf.png": "85654412476ae96f1e024811807a4c7f2c4eba52a66dade26851f7f5706440a8",
                "data/nfl2k5_relief_2026_b81u/sleeve_d490ad9edd64e09a.png": "22785bbe474caa6d02f3625234fa99f287619872a1fdb11e76a6c38269ddab35",
                "data/nfl2k5_relief_2026_b81u/sleeve_da452b5f9f2393d0.png": "aeffbf140326923f7fc09cbf43003e8870195c460fee7b994fec39dc10e996cf",
                "data/nfl2k5_relief_2026_b81u/sleeve_e32d6e79dad95f92.png": "e297ab64800a437b045f3d157d6c64c061dfd39e32a8403cdf03b8dbf1ceed20",
                "data/nfl2k5_relief_2026_b81u/sleeve_e473d30c9c2785ec.png": "bebd90bbc4873276ae0263a568c49f6756c0a5d7083de72317e82fa9c397cd0d",
                "data/nfl2k5_relief_2026_b81u/sleeve_e662bc0e2a5f5d0e.png": "8574c54468ae8173e342febf3f5c5279585188297aef66f43c1f028662b70d80",
                "data/nfl2k5_relief_2026_b81u/sleeve_e9642e24fde03ca5.png": "706d68b3caca15a953d178535169a151af441aeffa7ff1f91092a2d366289d67",
                "data/nfl2k5_relief_2026_b81u/sleeve_eae5c711e253e301.png": "878f8d84705101af177d13278c67433552991642c619272729ea023b74bf13a1",
                "data/nfl2k5_relief_2026_b81u/sleeve_eb08218b66c6e7f1.png": "4ab2631364ba4891311a873e8707f8a50f47584ac2450798f63de986060c97ca",
                "data/nfl2k5_relief_2026_b81u/sleeve_f12d3e250fe3c759.png": "d46bb449dafdd821aaffcfb587ffae3d092f1bbefbc6bc26f4b29c590819edcb",
                "data/nfl2k5_relief_2026_b81u/sleeve_f4f6b4077064fe27.png": "6c2dfeac50ba2140721c10f829487d5bd5be393cf181908081bbde4c8cddf46d",
                "data/nfl2k5_menu_chiefs_2026.json": "8b4a86d2bb6893d6e23546ebddc3ff1626e029fcf3b8ed4a14fbee6fd1748eb2",
                "data/nfl2k5_menu_helmet_w2026.json": "ae19a9a2d032d25312fea3114ae530b137a0f437629f56c5ff484f08ac5626b6",
                "data/nfl2k5_indicator_names/atlas.png": "2693d6044962f9f59f4390b3e578d3575d9d3f0c081ae668510c83399c3197f7",
                "data/nfl2k5_indicator_names/metrics.json": "2bebe47d2fb50e36a5c3a736d95677c06c780addf88463c2b5b266111af4a129",
                "mod_editor/data/nfl2k5_free_agents_2026.v1.json": "39cf9602756dcf8742e90654a43fecf10c86f24db61a915074ccef094a6f7ad8",
                "mod_editor/data/nfl2k5_refresh_appearance_2026.v1.json": "867624f428dad0d32eba16b6e05d4d2f104266c5fe37c3c0d9ab43ce7797e204",
                "data/espn25_previews_2026.json": "8ae83e55f9ad9cc5a9fa1f5ed0efe4c0802522b7332c5ef3e3b594ca472e287c",
                "data/nfl2k5_moment_venues.json": "960f1f61f5395ce65117b32840f38f28dcb31fbbc1e793eda9dc39c7853b5fb0",
                "data/nfl2k5_moment_goalposts.json": "256d15573650a24a24b83953d627d0bede614aff6587c16c3eb060ad48329acf",  # b77-v1b
                "data/nfl2k5_era_rules.json": "fab269783f2f4524b01e031a15de8156629a6728d86249b9402822594778d1e4",
                "data/nfl2k5_stock_books.json": "87d779bb2be3c4b20b901c4afa0a620bb4b0aae29ef833bc4440a38c396417fd",
                "data/nfl2k5_moment_coaches.json": "3b38c524f4a861ac100e96f847939f8d12ffe62c6eef3aba93e7f33144e9148b",
                "data/nfl2k5_moment_stats.json": "1aea510df6cd581b7d992b640f3c0be0b07a89308592f691cda6c87dde052cc2",
                "data/nfl2k5_moment_playbook_eras.json": "756d99acac597ceb86026264c23e67ab038fd765de19692ccfdbdc65f3ca61c9",
                "data/nfl2k5_modern_color_pins.json": "670a9f1df1abe67c12d373318e4bca0c388e9e7a3c54d42e44ad37f52981719d",
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
                "data/vip/coach_sources_2026.json": "54fac5e396a2d76c574d63b94217261c58ef2dbfa4f1906fbbade6e7951c9b63",
                "data/vip/coach_portraits_2026.json": "aa398aa7b0e695c73b4a809ba5886bb7df95d1c4173adb00f542d6fd0ccfebe1",
                "data/vip/defense_identity_2026.json": "12e2bcc1b7ede02dcac2d2f43351c7985e88ab4a62ad908d900168b4009a55e7",  # b779 dp1
                "data/vip/coaches/ARI.json": "f05194553bd87ea58fd07e8c32a0f6c127ab72c84b337ce23fb28e88adf6bb25",
                "data/vip/coaches/ATL.json": "47b81905bbcf74fd0fb3e70098e81191d17a47f0c332a2a2f7f9fc2f41f81713",
                "data/vip/coaches/BAL.json": "3fb8a696df304884656d0c291ef07cc0ec3d29779433e2b2678cf2a2868db404",
                "data/vip/coaches/BUF.json": "da4cb5baaf325761e3348c56bcdbe5bac43c32eb1be0e9ebe6eb0b7faf18c6dc",
                "data/vip/coaches/CAR.json": "798f94047b3b14bf8125b101cfa82f334605551d3160f98fb30bdc66a1c4ee28",
                "data/vip/coaches/CHI.json": "40fa7f7a9ec3365928daa61aa100a106ec424b66031fe8f0c73e795b0c9d8cbb",
                "data/vip/coaches/CIN.json": "b30981f746a96d80bdd123887a1b02eff23ae2448a9f365956edeaf286bd4eaa",
                "data/vip/coaches/CLE.json": "721689ead13c3fc10548fc5f81340ba60038729ee65a165103ed15c53317c845",
                "data/vip/coaches/DAL.json": "fe6d1cefe369f4c8bfd527a2103dba4f38681a68607b69bb75654b4a9ac4d2ad",
                "data/vip/coaches/DEN.json": "2153ab654d1e5225e7ec0028c7516d55e4fc8450931a8ea5900d8e418a3863a4",
                "data/vip/coaches/DET.json": "bc91c0d3925209919b5b42c7a8f8d636827cdcefbbbf1a7fe724deab523b6474",
                "data/vip/coaches/GB.json": "489428faad98e0b90a29d7c79acc63a44a29f68669d758bb7862bfb9797d4ada",
                "data/vip/coaches/HOU.json": "d30d7c17a2f54c709e65150a3c1f5f7b3787813bdbee8cea87896a55bf4e5bfd",
                "data/vip/coaches/IND.json": "232fa74ecb56dd02aed9968f35fae349aba6d8081d4e559eb5370bcabde10932",
                "data/vip/coaches/JAX.json": "5d2d5c5393247cf1fa81ee0acb99e0da9b752d59a8ffa7d6edc819af01ac3a68",
                "data/vip/coaches/KC.json": "f82aad77da6c424bdf2e2909be3b1d2cd9c5841eefa537792ae7c51227b2d6ed",
                "data/vip/coaches/LAC.json": "6418953333be5652fc32da4ba72e09e46d4ba2a047b584880c6aece21361f8da",
                "data/vip/coaches/LAR.json": "396d16b9fbaaf205e1a3b30754e99df50f4c3eb4dbfb4394ef5fb4dc1acdf2b4",
                "data/vip/coaches/LV.json": "06ccb5edb5fc048201726149e73ca35ef0f4c2bd461a5a243f0f8997252af6ca",
                "data/vip/coaches/MIA.json": "ca1eaa093d0931f7cb0dcac699ea3d2e06236cd5a5eddd073aa48e7d92c2e1de",
                "data/vip/coaches/MIN.json": "0679b1718eec1327711876aa8213c89bdf0f159dff77013252f8d9d55a4e3dcc",
                "data/vip/coaches/NE.json": "24d671a0e130aae21edd1d2b8fc35c3c6928d49123c73701dccb254b0820f4dc",
                "data/vip/coaches/NO.json": "85f8a3f98d5b3f2e556d626937fdaf76814e157c3e4de1fd4a8935d639e4fce3",
                "data/vip/coaches/NYG.json": "aa2fc658e75f65c20c26f07794289d31571ecd84397e0be3c307b816eecbbb0d",
                "data/vip/coaches/NYJ.json": "b3f0c507de82070779956a1fce4e767dd0214deb4e529a4d9744e6531d2185f8",
                "data/vip/coaches/PHI.json": "881f09f1b31df26633889bbc3e20fe53bb0356bf72f66f1209da602e24ee3890",
                "data/vip/coaches/PIT.json": "1d0e71ad1a9b9a34adf91062b62acb739a24758c09408680a1eb835420d87c05",
                "data/vip/coaches/SEA.json": "5e131b080819369335d3edef136e1d509154af25ae15c7519c8863ef8861e578",
                "data/vip/coaches/SF.json": "002e71db711aef0896f4219f80fa578f23cd59c304da3e2ccd2b1bb41225c34b",
                "data/vip/coaches/TB.json": "2f1626c3a8047afff41f6fa7a7cad359e9db96c92356a83ed8bc38368057057b",
                "data/vip/coaches/TEN.json": "34a02ba96970f7b88597cd0a129394e908317f92154e0cb20332a85af831419f",
                "data/vip/coaches/WAS.json": "a3975b14cc02719a2152b8f6764d80d091ad4c3a987ee6fb6ff6a157f6544b28",
                "data/nfl2k5_espn25_more_teams/manifest.json": "1aefb229e40d438e32210669eb62459bb71aa056bfe23c460dcc86eb0fbc95ba",
                "data/nfl2k5_espn25_more_moments_appearance.json": "d129d17eb71eac0f2bb5a5c3bbcec3a82ff256437dc06a104f14e60afae7232c",
                "data/nfl2k5_moment_scans.json": "c95a90c155fe170d6a312acdf659b3bffd04c028b3d930ab1fdc13d6a8971627",
                "data/nfl2k5_espn25_moment_rosters/appearance.json": "2349e073097edced764fe790d449ef8223f444363711494cfe9996a19678296c",
                "data/nfl2k5_classic_teams/teams.json": "bbe46a3c6d87a9c7a8d2e1c95a63cece0495a7c069a132fd5253cd9ecca668ca",
                "data/nfl2k5_classic_teams/manifest.json": "93e82081f2036b2196ae78ba9a71df138c205bae8e9269b596a60e2ea588de35",
                "data/nfl2k5_classic_teams/appearance.json": "8b2607c2ceb4e70682991b0980736b3be9726fbdb1fbe440d812a48ef30b711c",
                "data/nfl2k5_classic_teams/classic.json": "667d431a6ff15ea9d4cb022490a1f34f66993822ee3a4849921c819369b9d40a",
                "data/nfl2k5_classic_teams/honours.json": "9430c474ede71ea59077476a01c051fc2675a032e864e84cf77312d25d52d184",
                "data/nfl2k5_espn25_more_moments.json": "53b5667960d0720ab75d127804f152d9513d681648525b958228db16bf12bafd",
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
                "data/nfl2k5_espn25_fields/row10/lettering.png": "7baf59cda0fde5793f976ff484008341da764cc8dfac96c26e875c44d2d731e2",
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
                "data/nfl2k5_espn25_fields/row05/lettering.png": "0aac0ba56ad51c2107386e06a8fc727527be93eff31e5662505834d89a6d28ed",
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
                "data/nfl2k5_espn25_fields/row02/lettering.png": "0aac0ba56ad51c2107386e06a8fc727527be93eff31e5662505834d89a6d28ed",
                "data/nfl2k5_espn25_fields/row02/endzone_S.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
                "data/nfl2k5_espn25_fields/row02/endzone_N.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
                "data/nfl2k5_espn25_fields/row02/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/row01/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
                "data/nfl2k5_espn25_fields/row01/endzone_S.png": "bbc041dff4441c99eb2323161cca7eb2a5c4bb103036e7d0b382b71928790d2d",
                "data/nfl2k5_espn25_fields/row01/endzone_N.png": "bbc041dff4441c99eb2323161cca7eb2a5c4bb103036e7d0b382b71928790d2d",
                "data/nfl2k5_espn25_fields/row01/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
                "data/nfl2k5_espn25_fields/manifest.json": "9f7e0cfc607f9068b143eeb7d44f68209b7a324ef3fe4857fa9dda676a588006",
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
                "data/nfl2k5_espn25_more_teams/steelers_2025.csv": "518c1cdb418ce402f6cab0e4c42532c0dfa55c991d4eef9724649fe6a7e2521a",
                "data/nfl2k5_espn25_more_teams/bengals_2025.csv": "23211f988adc97ea41c377f8c3c7bc2fe5f3f12e9d92ce42352dfdce0960a5db",
                "data/nfl2k5_espn25_v04_profile.json": "3f1f60561c14a2a09fd23dae09d0fad6dbc5f2b49cf14cc171c4cb1a3ad5351d",
                "data/nfl2k5_espn25_unc_bowl.json": "4a632282beb8cde62ffaa5e896ea22bc89eb67b54ba49a2e19a694c02abb9b18",
                "data/nfl2k5_espn25_fields.json": "da73bb1f1a838fe642d8537596565600bd6febb1771b0829eb6e977bc056da4f"
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

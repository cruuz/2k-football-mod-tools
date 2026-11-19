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
                "from mod_editor.core.nfl2k5_kit_fixes_2026 import spec; assert len(spec()['textures']) == 60; "
                "from mod_editor.core.nfl2k5_kit_fixes_2026 import alternates; assert len(alternates()['textures']) == 544; "
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
            # Beta 81 adds the offset toss and six frozen beta 80 gameplay modules.
            [583, 10, 8, 9, 8, 9]  # b81-uniforms: 583 = 582 + the 2026 jersey relief (nfl2k5_relief_2026, loaded by name like the glyph passes); b780 mc1: 575 = 574 + the boot save-list type guard owner (imported by throw_tuning); b780-int (pres2 9b9d86f38): 574 = 572 + the two frozen sprite engines of scorebug owner revisions 16 and 15 (nfl2k5_scorebug_sprite_code_r16/_r15); b780-int (mc1 290936cd1): 572 = 571 + the Franchise load user-team guard owner (imported by throw_tuning); b780-int (modes2 0a6570d1a): 571 = 570 + the frozen beta-63 .. v0.9 RC weekly prep code (nfl2k5_weekly_prep_code_b779); b780-int (01:1x batch): 570 = 565 + modes2's three frozen previous revisions (nfl2k5_historic_teams_quick_game_code_b778, nfl2k5_coin_defer_code_b779, nfl2k5_decided_clock_code_b779) + season1's later-season schedule owner (nfl2k5_later_schedule) + rst2's default special rows owner (nfl2k5_third_down_back, imported by nfl2k5_roster_refresh); b780-int (hist1 643f5c859): 565 = 563 + the history pool owner and its generated code (imported by throw_tuning and honors); b780-int (IR1 042631341): 563 = 560 + the modern injured reserve owner, its generated runtime and its save codec (imported by throw_tuning and nfl2k5_franchise_save); b780-int (mem1 3c20d2f36): 560 = 559 + the intro auto-skip owner (nfl2k5_intro_autoskip, imported by throw_tuning for the build union); b780-int (sub1 d62eed757): 559 = 558 + the situational lineup roles late owner (nfl2k5_lineup_roles, imported by throw_tuning); b780-int (studio1 ff4d2d3c4): 558 = 557 + the released-disc list reader the disc identity imports (nfl2k5_disc_check); b780-int (gen1mc): 557 = 556 + rookie faces (nfl2k5_my_career_mode's draft-signing context imports it for the draft-number byte); b780-int (studio1): 556 = 555 + the disc read's validation memo (studio_inspection, imported by mod_build.inspect); b780-m64b: 555 = 554 + the console memory target (nfl2k5_console_memory, imported by mod_build.validate_plan); b780 hunt1: 554 = 553 + the frozen beta-79 RB injury roll (nfl2k5_sim_rb_injuries_b779, previous state); b780-int: 553 = 552 + the frozen beta-79 cornerback tackle tail (nfl2k5_sim_cb_tackles_b779, after n3); b780-int (n6-champprev): 552 = 544 + the frozen beta-79 modules n6 keeps for 'previous' recognition (camera, K128, MyCareer mode/legacy/home, Player Progress, pass rush, scorebug, sim realism); b780-int (p3-legend): 540 = 539 + 1 (b780-p3: 505 = 504 + the audible panel legend owner (imported by throw_tuning for the build union)); b780-int (p1-slide): 539 = 537 + 2 (b780 p1-slide: 506 = 504 + the protection calls owner and its generated code (imported by throw_tuning)); b780-int (cv7-scramble): 537 = 535 + the scramble blocking owner and its generated code; b780-int (cv5-speed): 535 = 533 + 2 (b780-cv5: 506 = 504 + the speed separation owner and its generated code (imported by throw_tuning)); b780-int (cv4-pick): 533 = 532 + 1 (b780-cv4: 505 = 504 + the defender catch snap limit owner (imported by throw_tuning)); b780-int (counted at cv3, the real closure): 532 = 522 + j6's Hall of Fame rule and the champions history (now pinned: j23 imports them) + c5's owner model (now pinned: the carousel imports it at module level) + the modules c2, c4, c5, c6, j4, j6 and cv3 pinned without a count; b780-int (cv2-runner): 522 = 521 + 1 (b780 cv2-runner: 505 = 504 + the CPU ball carrier vision owner (imported by throw_tuning)); b780-int (cv1-brake): 521 = 520 + 1 (b780-cv1: 505 = 504 + the coverage_trail moving arrival brake template (nfl2k5_coverage_hitch_code, imported by nfl2k5_coverage_trail)); b780-int (a-passer): 520 = 518 + 2 (b780 a-passer: 506 = 504 + the CPU passer owner and its generated code (imported by throw_tuning)); b780-int (c-release): 518 = 517 + 1 (b780-c-release: 505 = 504 + the in-place quicker deep and rollout throws owner (imported by throw_tuning)); b780-int (j1-standings): 517 = 515 + 2 (b780-j1: 506 = 504 + the Team Standings records owner and its generated code (imported by throw_tuning)); b780-int (j23-footer): 515 = 510 + 5 (b780 j23: 509 = 504 + the franchise extension format, the footer host and the history capture with their two generated code modules); b780-int (b1-draft): 510 = 509 + 1 (b780 b1-draft: 505 = 504 + the draft class owner (imported by throw_tuning)); b791-int: 509 = 508 + 1 (h3: the build step context and optional-step journal, imported by mod_build and the 2026 kit passes); 508 = 507 (h4) + 1 (h6 project-stage cache); b791-h4: 507 = 504 + the stadium dry run, the edit-survival audit and the practice facility the dry run imports by name); b780-int (first-pass reservations): 544 = 542 + j4's History screen and its generated code (now imported by throw_tuning); b780-int (n6): 542 = 541 + the beta-79 champions code kept for in-place upgrades (nfl2k5_champions_code_b779); b780-int (coach_career_fix wiring): 541 = 540 + c1's coach career counter fix (imported by throw_tuning); b780-int (p3-legend): 540 = 539 + 1 (b780-p3: 505 = 504 + the audible panel legend owner (imported by throw_tuning for the build union)); b780-int (p1-slide): 539 = 537 + 2 (b780 p1-slide: 506 = 504 + the protection calls owner and its generated code (imported by throw_tuning)); b780-int (cv7-scramble): 537 = 535 + the scramble blocking owner and its generated code; b780-int (cv5-speed): 535 = 533 + 2 (b780-cv5: 506 = 504 + the speed separation owner and its generated code (imported by throw_tuning)); b780-int (cv4-pick): 533 = 532 + 1 (b780-cv4: 505 = 504 + the defender catch snap limit owner (imported by throw_tuning)); b780-int (counted at cv3, the real closure): 532 = 522 + j6's Hall of Fame rule and the champions history (now pinned: j23 imports them) + c5's owner model (now pinned: the carousel imports it at module level) + the modules c2, c4, c5, c6, j4, j6 and cv3 pinned without a count; b780-int (cv2-runner): 522 = 521 + 1 (b780 cv2-runner: 505 = 504 + the CPU ball carrier vision owner (imported by throw_tuning)); b780-int (cv1-brake): 521 = 520 + 1 (b780-cv1: 505 = 504 + the coverage_trail moving arrival brake template (nfl2k5_coverage_hitch_code, imported by nfl2k5_coverage_trail)); b780-int (a-passer): 520 = 518 + 2 (b780 a-passer: 506 = 504 + the CPU passer owner and its generated code (imported by throw_tuning)); b780-int (c-release): 518 = 517 + 1 (b780-c-release: 505 = 504 + the in-place quicker deep and rollout throws owner (imported by throw_tuning)); b780-int (j1-standings): 517 = 515 + 2 (b780-j1: 506 = 504 + the Team Standings records owner and its generated code (imported by throw_tuning)); b780-int (j23-footer): 515 = 510 + 5 (b780 j23: 509 = 504 + the franchise extension format, the footer host and the history capture with their two generated code modules); b780-int (b1-draft): 510 = 509 + 1 (b780 b1-draft: 505 = 504 + the draft class owner (imported by throw_tuning)); b791-int: 509 = 508 + 1 (h3: the build step context and optional-step journal, imported by mod_build and the 2026 kit passes); 508 = 507 (h4) + 1 (h6 project-stage cache); b791-h4: 507 = 504 + the stadium dry run, the edit-survival audit and the practice facility the dry run imports by name; b779-int1: 504 = 503 + the preseason warning owner
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
                "data/nfl2k5_moment_kits_pins.json": "514dd6891d97b7102d7c3f85bf355840faaeefe13e7a296edaa34a0ef176a342",
                "data/nfl2k5_release_gates.json": "12b1146cdedd09e72fc532b712b4726cf744ee9f1bfa360c4e6ffd13b1209285",
                "data/nfl2k5_unc_bowl_uniforms_pins.json": "84dc131eebe5188fbfc18eee5187abc8ac5aba572b3796a35d2cd905a2769fe0",
                "data/nfl2k5_nyg_numbers_pins.json": "e1d34f4a340820f6569f362a91e7a1a5f5f96fd74c3a46644d656500a392f2da",
                "data/nfl2k5_kit_fixes_2026.json": "96551c07e3f12661d1c6ddd9a5df2d2da9a3a39d1f8aabce85f03c90958741e9",
                "data/nfl2k5_kit_fixes_2026_alts.json": "dfbec6c519228abe0e23983d907463ffe12cf57fd848e8c35ebd7a68ae1f4698",
                "data/nfl2k5_kit_fixes_2026_uf3.json": "a1911b169c1a4bb8fe130575586563e1ac9c9567e490a7d753f7c017f492747c",
                "data/nfl2k5_kit_fixes_2026_sea1.json": "507ea2233b31a41e5301427367186cca3c0f116be6b2f31172068b8dc9f34e35",
                "data/nfl2k5_kit_fixes_2026_ov1.json": "506d9592290de13e4aeb17a23a0febf147e4392b985646ef9c0df5e15765c9c4",
                "data/nfl2k5_pants_hem_2026.json": "c85ecadefb53337ab7b97996b36b9c36d2119e4745f64e1bab34e321162aa9ca",
                "data/nfl2k5_glyph_fixes_2026.json": "a709d39b5fb5ab4a6f6793e6626d36771197c6a196c410b8057e58f899148387",
                "data/nfl2k5_nameplate_fixes_2026.json": "535f690f05dfb40a53239ca007fef42bdc4eaaa9611fcf4b74b1496b62980200",
                "data/nfl2k5_glyph_fixes_2026/TEN_28A0_digit_arm_7.png": "01252bae05b33caa13780327eafd8add37303d54bc27d46429cef61230a292d5",
                "data/nfl2k5_glyph_fixes_2026/TEN_28A0_digit_jersey_7.png": "5da1a357b81632f469e23f506155ff43af10b2fad036a3de285145e7b694c713",
                "data/nfl2k5_glyph_fixes_2026/TEN_28H0_digit_arm_7.png": "078b28a7a0ae54e18d08b4580155ba6fa49fe566932305c7decd795a96f6d17b",
                "data/nfl2k5_glyph_fixes_2026/TEN_28H0_digit_jersey_7.png": "25727ec3a92a703131e11766c4da6a781a63855be44d10a0a961e451cad02de6",
                "data/nfl2k5_kit_fixes_2026_ku1.json": "2811ee1e688df9b388544d335106df651eedef26e4bedf69c0e3b914a8d08c97",
                "data/nfl2k5_kit_fixes_2026_sw1.json": "4f7052e03fd8d23dceef19de010459e552d3f4b63fd2335e575d13bd1e0de18e",
                "data/nfl2k5_kit_fixes_2026_names.json": "cb354c62aa6b6e8de0ff01e9f25937f0a2e54169bfc37932bd689599529693fb",
                "data/nfl2k5_kit_fixes_2026_b81.json": "cfdb20ed4b2f5757590f1179703eb240d71a4af9326ae782f5ceea25498fc646",
                "data/nfl2k5_kit_fixes_2026_b81u.json": "89e3ad8f4af0bc1b30e768ecc3e116ec0ab787a2375addf6d29b098c61f31218",
                "data/nfl2k5_glyph_fixes_2026_b81u.json": "46ac0521c54cdd1f46e33932d27822ba5798d16ef1707c6aadb5eb0a98ae36b0",
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
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_names.png": "c7c86cea517436f4638c7a9bd60e317835810b2fb135b5ad1050d9b214178158",
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
                "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_names.png": "a6259d3a059663c282b48f71f7f14ff76f572ce802fab605fd2a5d8b89cc4906",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_0.png": "7c3fb48feb6e6480fbf744c5c0bfc154bbf3fafda84c8263ecaf2f04bf9c4149",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_1.png": "e4640a7373c0ba2e62aeda635f1258360f6e26a29b652c8aaead0d9332df704c",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_2.png": "337b9eb1b206df48964a422d0944ade9632b7e4826c46b76daad880bed58ba59",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_3.png": "2fa0be382626d61438abbf7a32d77da01f86b28fda222c814598e68da98b44e2",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_4.png": "8019ebbfda672c4aac4426bf7ff6a65369f77c93f38578814fe07b5de16dc160",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_5.png": "1a8180d458fe91bcbffc600c7f1578e6b8a55051fe33bec018225413b4180c39",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_6.png": "a326e1603b276057083eaadc51d3b4bf41db807c823d90a4e19ee35e92f611f9",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_7.png": "075fd2507cd18438075e3799478bc848f8f38712bb6efb58e559426a7daf0fa4",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_8.png": "ff7f83e7d21c9f0aaa66a1dee9a0ce79dbb370e7b505f710ec7276a55a6cb672",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_9.png": "68f46d4905f9b311419f3916228814a33a9bfe18cde2385ff457169e4b1565be",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_0.png": "bcb2adf17bba979cfec68040598a5985731b08ad24573ba6edbda2ebbd30cfc6",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_1.png": "5376522be2fa0f22877b8c184cf95621aeece6e76b5cc550c82d1088540593be",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_2.png": "3b8e9edf21fd3134626b7ee4be228537f1336c0cd68f2ae2096f9cc1af5c5d82",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_3.png": "4525f5054b0e75bc28bf9ca04578926b6a4d902351945079921e93549b5efb5d",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_4.png": "9cab4abb576a0cfd1a46971bff686aff15be32bd834e53f0513ca6e709797628",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_5.png": "2ae9d765544da06f84f908a3bf56f79252136e05fdfdce3bc9a70024a7aba15f",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_6.png": "88b31457034133ebb817bba8ead4c97d335c0c1351e91f15f0140cd87e4d0478",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_7.png": "990242dfcf1d6ae005529b552395b517397e73edbc4937585a47867ebfa7e4d3",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_8.png": "995ac7a99ff340d7d68979de8e16a547d4c56a0985ced838bba00f885cf180ec",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_9.png": "736123f280f441d770e9616396c1fba73934f3fc92598e7cb2fa61a25cfee22b",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A9_names.png": "2cf3c06d4f0a4b05565ebe63c70b0c470eda0273f43574d0286bb0c748b50b1a",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_0.png": "388d52adab164b1405dabcf2dcc5166bc75b7d8a463df58a6d1b4b139bced813",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_1.png": "7e9f50520338a94e98614fab5001344ac6a9cf66f557e751e9c3c91e10e031c5",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_2.png": "5ba6685c3519cf82cc0192b30c9503e5e8b002519eab0728d96eaeeb812f3b44",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_3.png": "5fdb6ee0ad5419ac5bbc5a9d0ba8a76480075dd644e69072d18663646724bd1e",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_4.png": "2fb1a3053b8aeb6ae64f1124afd28b9b32e118201ed9bec80b65c0b4f82f5bd7",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_5.png": "dda26ea19fdb40fe6cccf600d656f552be351b68b91ab9ffad8c8637a802d02d",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_6.png": "0deae7e063d4ef545e67f0202ec85a0365c337779f08b90b49e68329ef1767ad",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_7.png": "04f77779d69a79335747553074c9ef4f753a60e8079467b06a0f650ee2565496",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_8.png": "68fd036a98ec42cdec9d9f2e93867dfd5b5c64d0bc1dbf5ac25f7c19cc8cfe1b",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_9.png": "3adc476de43dca022c0b3b4ac150581cb879d5948e531e117fb4344453320a16",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_0.png": "5400c59dd8179d7bbb0e198c43e3574939291f778f565915edbcec23c243d2ca",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_1.png": "9a9ba2888d66e365e201cc9d6c28ca3573b783c381f7cdcb6b0ba85883abc410",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_2.png": "389ddfd589b89c6f279cb6c68c5227e98762f7fb3af92241b7592151ddd70be7",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_3.png": "3659e3d034a0c1c5a8352da04c3e5d3106f5be6f301bf0cd375bf5b5dd275c31",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_4.png": "c44edb53e9829308b888978cf6165fd21bee79e01c50db837364e1882d8240e9",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_5.png": "8cb249662869e69e8cbacf23b511ce6a512aa0dca8be6d5b95f89488fb338e2f",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_6.png": "b2ddbc80df58e583e43f3497bb990116b77872cc44d645dc6a148893475d33fc",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_7.png": "518e2fb3a422522d8988469d80035130206e00c5e607c6d51ac3132be55f3af8",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_8.png": "0c907841ea5e07af4572d54541e51123c8a0037bf3fcedc9801248861e49bdc7",
                "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_9.png": "22bb6b31501e2efc6b83c6f5d937a94843740ba2f34dc0110bfdb162f3dff130",
                "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02H0_names.png": "7336813b2fe924f2a041e9e40fd289f7acc913c7be1f82935081b9aa12551057",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_0.png": "9962a0f9f62d821e2110065e0c672c3c1d23f80cee329e66b532c5dd02549c31",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_1.png": "510847c5ed44ba6758fa3b38a936cf96beebb66f3631685d0b54f3c1fb3d026d",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_2.png": "24c4d272a2c2ed6661c93103752a02d9b5b141baaf82a005767352457837119c",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_3.png": "83c4165dad5fb865dac9bfbe956a62dd8f83261e04b60e678cbd1b321d165e19",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_4.png": "09a699554a18dc33ab63969f4a23a73c577b5dc977af2f9e2afd044adb176972",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_5.png": "6ca2ab3e8f0554327caef98c8e7cf5564b77ee710c84502f5ebf8dfdecf042b4",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_6.png": "905c1ea29525ef2d254f5b4eff7e60dd91ff9b5d5c68f83dc0b2cedd1c6b2d19",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_7.png": "2d8e07734d2ea3cf3e8649e7b232b1fc407c41ac0f20bb50a1b083891d06c79d",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_8.png": "f691bc4e2697237c142836da187c6025295bdd16e5c15ad3c572873d413242c3",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05A0_digit_arm_9.png": "f22b191850cd901944b4d71275e68353c7528aa4192d4b6b77870ba74704d724",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_0.png": "c2a7d5aab04a7c46b62ffcbfa2d12467281c46cd93de02c2f3ce6f1e86ec6f39",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_1.png": "0d9af191249d99e6f94a4a420c3e7e74c6a6679cf9f9654d56b46e64b22b1389",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_2.png": "2fc4d7fb9d4dd621905b2f75d0ca677e9f75bc4ed65cc72c6079c75c4e148152",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_3.png": "f08c3e02c4de0d596206e3a0b0687e72982cff6fb40813a9fb36550f13ffd417",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_4.png": "7593fc2b8b6007f6fe2ea99616d48e1e0e5582cb213b6ae694ba7893e727289f",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_5.png": "688a48a7eff49413cbb130dbd6774385c968bd0dcd5fa6f2444bbe57d1cab038",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_6.png": "a4bcb30988ac7dc7efd0c07fba2edfa4a34e7d7741ee3b88e6944d7267242574",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_7.png": "e49861b61600285aaf802bc4090cd3a4398a9fbf1d4bb450f9ed45583623889c",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_8.png": "08760fa83ee21e9057589148295054f5d6023ab40df866ca1f9686822c34a3c7",
                "data/nfl2k5_glyph_fixes_2026_b81u/CHI_05H0_digit_arm_9.png": "4071d93780aa2655979494cbb1d36f4b1988450efd022344c34b734846583ce3",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_0.png": "61e9da3ab8ce47fd9a890cc4d52a2c908f2879cb4e27d95c2354177c4dc4d85f",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_1.png": "0a8c6bc62019b01b4305aca62a58172d79f0e709653002851432f35e06e5a605",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_2.png": "507e919d33fcc7bca5a4c2f4219e7514d9ed1a6d80c5ec76bb908b790b4e7716",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_3.png": "93f2b2e0f069307bdfaeacde7aa57388132e4220b487e2861aad99b321dd4a07",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_4.png": "8d9e91694ea2669c851c6535d20be2bc2487ac4c7e5388bdf90a79e6d4d60b82",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_5.png": "2215d3a226d052e06af9edc28a50bcc37ae802100c9d7f35157a7365dc1c1003",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_6.png": "96c1c3442ecaf830eb8604e0eccda36adcd065c1a06f4be91c6d98fb72144ed7",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_7.png": "4e37e04eca4f20c1954807109455ab6ae73b72ed6733237a62367ca2db986566",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_8.png": "e8cfeb929dd6f7a02f5735caa2175384c4bad21e488cf72eb6e4bd907d7e73b3",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_9.png": "53a00b7580e29273056eee83c9c80c57ea9de64aaef02ae01d9bcd8dc2d82d4a",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_0.png": "b5718082f98c797a7fa898206ba16d9cdebc90f7ded9882d95f83b68f7afba08",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_1.png": "274d448e230b332b23dd28a75e52c236d434232685f5a10641e2678188b2e1f7",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_2.png": "187a49149dc9258f8c7f561fea586c49c36649b35dddae7cd2ac0f2a767a225a",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_3.png": "e7fc4a827f9eb992ba0adb82a8ec6b1eed1bc3bf3cfc9dc165ba69e25423b805",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_4.png": "4570e803f941f61a5600791d73d6e2348b2eb1cf03c6e1f8b03c8d4b6e4a8072",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_5.png": "eb2ff73767c8178138119c077cd5b99d18684962b051e221672bb4434fd50e36",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_6.png": "c3988982ab65b2d64e9a5100f8c2a72a8802f5de4f2b727b5283ef0a927d2fed",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_7.png": "689be4f67880e1a0daac08742b14769dc19e89b154439316609e4a7fa6c438fb",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_8.png": "90d4382bddfcd3bf1abe18873f6055e10e94f8d68630d53f2b9af460a7aeb482",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_9.png": "bd30d6dc0aa9809b541a02cead224ba1c1be27512a6a6ca10dd498d01e45cca0",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_0.png": "d597388ea3e36cd969f07f5bf840061b807ba009300eb46ff96d834488b30bc0",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_1.png": "475d73a0255c53cd55db99932baeb9ab5d53f3e4d320e609eefe2f57a5116001",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_2.png": "e1c030b881a7a2567b3863d30d06240ea0c7a52274d9fc2f3c491c6184bf417d",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_3.png": "1c40d008a39c9bc4b4d8ac18776cba77073401264a35593dfcf4d8ed5b40e9dc",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_4.png": "c73e7f3f79f83cc3fe0636e1a0d73e9219ecfb377e88a8505e6062dc81fc8d95",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_5.png": "4d33a106f7b343d1c269ca9ed4242c174dbb2421db7d9a30056df8c4f284d8c4",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_6.png": "5323f273946798c07752e0ca5b2330bc602643a3ca983f84e1f7cf9669d7faa8",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_7.png": "1045f20f28d463c3d552b7cd8d5bc21921690c79f1c444046fbdd943b14a3436",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_8.png": "ab28eb6c42358ed32e908c22fd4f0832766f3c805199418069b23092d8da3a17",
                "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_9.png": "805172b0bcb36e9292d0eda74161876aed5293ac60e5fda5d779c5711015109d",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_0.png": "d3fbdb4f1740218554ad72d60070c82403d5db1560a527604023f1602238edf9",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_1.png": "71f0e8979b7038ea6cb4ecede7dd726763ce7237ed2b54aef6babc864ecc526d",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_2.png": "4e2f8146a7931674c5e4d2feb553182f5f7fa1cba4178b152b3945a303c169ab",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_3.png": "cf92ea82ffa9431bffffd2a32ac3bc78964302b72653e64ae7e3ba14ec180c0c",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_4.png": "07cc40c62d1c9264ba799f1230268612af714bb9eed9531abbbf240aa0d54d1d",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_5.png": "03efff4e8a02f81ff037ff251aee0209737bd8cef1f530c54c47b6cb276e5143",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_6.png": "4b06716b5c29bf84a4cf8d987ec8e4f8c0838f32be590cb1692b2dc1d3b6707c",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_7.png": "952a01c37a2396c230aadee41dea5892ef04638682a7aec53cdc3d59873cf836",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_8.png": "6c8b9d20c08170df70b26e5d712ad289a8e4bf8cb21523613a25dc765ed6bd9c",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_9.png": "01ad940d0377ef7b1976b62ab59bf71a912261d7fdf50f8ed1215dd65126a1d4",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_jersey_7.png": "82d1edba666b61de43fdf38a65b983d267ff0ca8209b1c3a5a569fd9f08b799e",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_0.png": "a416d97958375a8d58174841ce26ac0788ee220ca938583ee46bc309d3f4c7cc",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_1.png": "1c31c3ed12ddcfb4131015e1427a2e01fd9041846a76ae61073933e583924279",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_2.png": "0d5139910d02c57d15a79d3de473295160d5ceb5b3c8f168a5c451da700e4d2e",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_3.png": "cbcc2a9307dd7bfc0002c60f75795b28138aa168bf62b3b829fe36487b1f3429",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_4.png": "a2617d53698860bf182316c98d3c827543fb5c45506fbc788b61c2341dd5b48a",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_5.png": "4be3802af88352c775ceeb3e05085022bddbc75c5f4a8fd7e36bdad15689e3e9",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_6.png": "68d2b9b76c47997ab2c6f8c95b09cb157add5ca6c49fa0815f01f0b3796ec6ff",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_7.png": "5d22200ac32961d1285576cdc46a507964ef5a6113fe5b7558407b9b6ea26b18",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_8.png": "8dd716f8547bacc55120b43e96dbcda118128897406dc6fdc773ae1f761bb01c",
                "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_9.png": "659c919ac0fe52f2d304c6199cfc288fe031a938fced3ac84e6fffa5770d941c",
                "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_0.png": "1125288e9973f4c5eb281425ba65133392b87822b092913284c0eebff6feed22",
                "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_1.png": "169701b339a975f3cbc4c9855d52f3c07aee3f47a358462bed2a3e740d0b07ed",
                "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_2.png": "af91e0dc5ab1bbcb5d66c5b1aebf4b03a467940a806df9b269c27e9f3c97a6a9",
                "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_3.png": "fbd37a949f108d42793a7a6723dc04e857b5fb150826b5c4c9f5629808dd4837",
                "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_4.png": "773138ab4d5bcd194e5098204ab5c2880378316544249aa981a8b4c83fd27f1b",
                "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_5.png": "180ce771f46f7b2a077b8a73834cbfa279f298977a6a8eb2e26c2bc7e617073a",
                "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_6.png": "08b9333cf99a4b123bda877e9c25a1418ece2abd6580ed55d342828f3784d6ad",
                "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_7.png": "90f1cfc20ba430612560949e9abecaf58bfc3247dc49fe0b1c7a1fc163b6e749",
                "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_8.png": "b5ca0c360470c227413664abae6130062800b74ff463ceb1104951bcd9d42b47",
                "data/nfl2k5_glyph_fixes_2026_b81u/DAL_07H0_digit_arm_9.png": "449ca01cf797f32ca77412c3c6a339b1ba7f100c60a085aa71ba6e7923a8dbfa",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_0.png": "6f0f017ed10b02f39a8d3e2f00f506554b157b3f15fb2d837313047dce29cecc",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_1.png": "398afa1b21343d7b0180e7e050d298e2caccd3b356e636b96090c92eb5d875cc",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_2.png": "43b6f5e4a09e0e942290a67c768027daf2844882c93c7bab33d98a8fb044922b",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_3.png": "5a02d4159dc9e270d28adb164bd68625b35be538194146c841cb84f1686d4657",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_4.png": "c43db61ccd315cd4af7283fdf10231f5eebb03f1bcd232109f22d257b18b92f7",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_5.png": "797ba17c0e68f7ee3351f5735a0655d06b80d595bdf4271776ccef24361d4077",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_6.png": "b732288575d6ea488874bfb0695fbfbdbff7830989187c96d6eafd3604fb1ce0",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_7.png": "00f98a0b1543acda87258f45c8ee5aa49e70a6551b32191ac09124aa4752a75f",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_8.png": "487d7b0bd5631166e67a3393ca8d5175dbc5b3ebdbd6402642a9c232659abcb6",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_9.png": "48d35cddad6dcf680a645a811d60f30a3fed300496d44282b0616602fde956a2",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_0.png": "356707bf751f14b5562ee63c609786b0dbd4a6e30ad2d730056eb611f61fc183",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_1.png": "9ca3b703130062fb82ed362f5c59883960f1870cf5c7279bb01845a87bea84e2",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_2.png": "58986bfe4953a90518ded7624a1cfe31cd5775c1d5e965571dd5e62c8956747c",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_3.png": "ededef44e83b31ab7a45373f782b3199ad7e797c36829a8a1dd2340f6fcc825e",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_4.png": "1e2c0eda0df750cdfe81cc94c081052d42570f3cfdd8c26797e7f75ff42a4e66",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_5.png": "2d8bb1543358c2233442e3ae01ed56b70a20c410073bd1dd82c2347c4cf868c5",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_6.png": "756a48146b244ab9d8c1e41454356babb338ab33fea0add0238ce97354348ed9",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_7.png": "e994f3f01511cdb6a43dc561894675f47b0faa274f472b0b4b145746583c9793",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_8.png": "0d7a07e20a2a72642aef817e8d987a390f6fa6a257dc1d526ae5c1fad52b9a9a",
                "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_9.png": "f3adf550497bf40962291275edc4fd05a1db57b77e256756d560c07fb1266f35",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_0.png": "00f692c74f4a03a3938af6840f6716ff866f21943769431a797ee258a8e445e9",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_1.png": "936cbf4eae76b955505ecfd9dad2aeac372fc7bd1b31bb45036c29ca0d966a39",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_2.png": "bb5fe595333823d9e3469ea9c05220597e29aea79dfc2858ed9c350b54f6425e",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_3.png": "fff8e94498d5fd848c8a37540347a19486f647f84ee4ca506c69184c7c4f4a26",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_4.png": "2a38840c69763e1d836dc3f7c780be14ce59cf03a23fdec0cdd35e93c816d30f",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_5.png": "82b779d793f33f93fd1fd2a49e2a1a0118822f9976f50343944f9ce76a468c14",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_6.png": "733afd9ded172a625de6118f662704a7bd4b6bffbd93342437472e8bff098090",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_7.png": "79d7d0724a003ed70e6c9984cce6bee92c138e230c5295b76d4567c4fe15cfac",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_8.png": "ccef34e903397a87cb29e6377845860a66882c5e452de2341ff78d402262b38d",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_digit_arm_9.png": "81ea03c171c53fca20283ef607b15d0fc30420fb3622a810a1431916d23ff084",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_names.png": "105fc446ecf9168f0ba01e0baae141ff9b4aba910df95327e23c9f60bdae31ce",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A3_names.png": "4a723c3c1a1dd9f635ecef88135ad1ac49a553ef218d0bb045b0e7ca78686d7b",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_0.png": "0dcde67ab6ac486b29d83f0db385ca36e23dbaa312dafc77396f037da717a8dc",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_1.png": "4907c76ee94f16abd68f61f6465a90208aaabd4a7c14807f4218d15c2a16c9e7",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_2.png": "52017d49172b8bf3715c4282268abe1f88ef512b1a3e715f93103d543a293ebf",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_3.png": "3767635fc7ca44c905ca8e3724cad5664b14c747d078c0c950d0affcfe8816dd",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_4.png": "1277519b6d41eeb6665aa452ebb9bd215871efdbee6eaa8af7ab6fd8028b081d",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_5.png": "383be7dfce478245c0436783eda541a050f7dd2e22274d3cf5d5c99ce5297c5b",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_6.png": "7b43de0b3236ce734bacc8d4689f24382ba35d632e7ed85a044c2ebd7f660772",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_7.png": "8f5ab3f8a509f0c93ebc4d43beeb11e51710cd09634c71a2aab2fdc0adbeff7a",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_8.png": "1a6f9b3e73993b0ea08d5e9156f625f5b49e82983bd44366d9e27b8d5dca9c7e",
                "data/nfl2k5_glyph_fixes_2026_b81u/IND_11H0_digit_arm_9.png": "ded5ed0f319fe175a02164c7c190788d274676cdfb8c4dddc3cfd09d7967c31c",
                "data/nfl2k5_glyph_fixes_2026_b81u/JAX_12A0_names.png": "88b01fa90f250376b8e2daee12db5327dd7715d4e5e93f1d894ef3757da7744f",
                "data/nfl2k5_glyph_fixes_2026_b81u/JAX_12H0_names.png": "a3e1801c762755899fc9915b77af70dd23b6753262bf34ffe72439805f4cb90d",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_0.png": "c7e9c2ad6f6627e218ac20b7a48eda7e399024f0bf69503eadffaf26313c377d",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_1.png": "f0bc47f43dfd489a4cc395949d54b22649da075b0252ccd1c63007ad36eb1430",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_2.png": "e3c85317a9e7b68ed1dd23f3550a4f9e37dcbf83ee5fe25e7a792dee31657894",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_3.png": "ba1ef3c3f52b55b54442f7c21624bbe022643588b0ff33ec426284bb85595505",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_4.png": "3a8073698f9386db6ed665bd10c48992b8a4b0ed5675370032e54f2d26328307",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_5.png": "640f61c426a28285f80a4e461e125a30bd861df3030419e36bc9ed63d87da9d2",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_6.png": "df2f8e75d7fd710b6549fa71616337bfcb3ea40c73c83bb76a70592d94c0fecc",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_7.png": "174da3383a812e8863bf3af06a2624c580fe08b8ccbd0789bb8c2889d060a096",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_8.png": "816cd56c016040df21b91d0672a9aade28267ed5bc9487b6934993f8c318b122",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_9.png": "e49547aa7122169d2279cb5d1851029c78d4fbf9c5e2888a38b6d748c21f44cd",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_0.png": "30e5f82f6f66acb8a2750217bdf0d892d55e004e87146dde2976d97d8643d57d",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_1.png": "4e857a7bc4e95fab93de87f7eeaa5dc2f6781ff02c65647b74410a7ba32ecb66",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_2.png": "e970b7c8dc23dd2fff48ba660d11a76097a21b280bb1f89183abec45023e2ecc",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_3.png": "d7489b7fb45398bce4e291762fe3a5eda324aac67e4005e8e25956cd2ea93131",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_4.png": "8b4bceb268da3adac44458fd8a8084091f0bf5e0f1ba99975fb4f636857c4c65",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_5.png": "440b380bf807c9305404816725a73473b825eafebd6c75aab67fb09d807dd9b4",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_6.png": "aa31841208f13c29a35cd814a8e6c0111305c08fd36d60ff0978072228ea13f0",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_7.png": "3ef47d4cddf8711ace37a71e0f9e7e2496b159f325962ddc6ca3a0f6fe2591a2",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_8.png": "8ae02d7d511e1d947a54fdd50067d3f12b500043351db6afba84514a5fb855b0",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_9.png": "a025cdc1426d68e0f3111dec784c9a0071131711c4776046a4eeea27e9e388dd",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_0.png": "04d33386eba32921c5128dc22ab7d092809f8d20d3368e34cc07c85e7745a865",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_1.png": "ba003fc0d1211593809df3ee979bb383b6ad7919e0895a9329ab03ba074c6cc9",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_2.png": "e0c718124b172600aaf604ee69d88953899acbdc278a1f0a191d3f189a7374f8",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_3.png": "040b2ca0f6dabfa1c16b4fc887b55eb36a6a651d05281b9304ed5f0d57f9dc59",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_4.png": "81b9cc4a49734b3a3e9ac404f2babf263119835f4a3e3bf1203ae7bcddb76736",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_5.png": "5db922ee79541c352726fb1fac961281f2b46fc6bb249d2455e657497e46d0fe",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_6.png": "688d76dfc90cd8e495bc476394c427cef2159e5f041ec816dc5c05799ea1e635",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_7.png": "ca1da35bbf9f4c504f93eae4a63f0f50a3c1e4cef660039fe823d28fc0afeb5f",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_8.png": "7470db6e31a5d7bf0a4646f1d7a6aa3ff81b48ef5d9545ce8b562a1d9d318fe9",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_9.png": "0076e6280cdaffc7aa2bd3847312c9a498f4447af36f089e7b5f9aca9e90d0a4",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_0.png": "b745bf3e187db7a8ee0218394c169c6f47fee649444ab91b056d6ffed25a85f1",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_1.png": "b6d9485d036b614e1f8e5bc647d5acb3cc51fea843bbd393574357e8390a8ad5",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_2.png": "0f4b4a17970cb683f02ec44024ae0336ce021f8758173ac4e7280b3e197b7c7c",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_3.png": "244396e1ceae798f82719b280abafe606ca94e4c2d43483b5aa7dd3f4af8960e",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_4.png": "41a351809a1e58feb3c1628dac78054f2d8bd016dd9aa76add548754de10dd9b",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_5.png": "878e06f4cbe30d9e0068dc5c03eae3a81ebe38e6560cc2cd9edc7d582dad7466",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_6.png": "2a114c64ce213d6335eb025c426503fa52e386fd0fb279fd65e2349389b29ea3",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_7.png": "f0bce44ad4f7c2dd835cc00a2fb7745292695baa37a18c926b572c47865ad37b",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_8.png": "ee61670689d5a6ab91cc54c81951b4e991edada28e22f9662670d24abd9fdc5a",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_9.png": "eacd48b39ff514c6cc36ad47fbec8c6f15d68bf17166ac8c81b75ee262760ff1",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_0.png": "f6dfc0659b04bf1321d5349d450351d4a703d2eb2bc94db4a0b06bb5d9cdc06c",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_1.png": "9878e2094173792e57936a6c07d2bd0a094e1c674be1bf495e2540074629c8d9",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_2.png": "005011530c34aab6a99d125c1a4cd2d0203e092bdcedefe61ff45d0e6182d781",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_3.png": "8f8049059f43fd7440fbf5cb0cfeaa073791c56e2b6fe9efbfe5b0927922823d",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_4.png": "aa1b5e9ca147ceb36a8d779499ee2a6d9bfe5f8a693a845ed2a7295b58c6b9a5",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_5.png": "ed09c31bc5420d2d5589bdd12e89681fc0988668245ad5aeb58e4bb81b7627d9",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_6.png": "f411b5b6edff08c8ef0ca57fa0bbee4d99eeac2131e5994ba9a02b63b258591f",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_7.png": "1a65c061bfe4d2a8d162d4f2b95a44fa364bc050a2023d707b8aa04de611c477",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_8.png": "2ec43fa6f2154312e867c07b3da30b6b016ad3d3f00a3594cb236a1c4dc6234c",
                "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_9.png": "328646455fb499e693005c36654b9ba0f850525a97465f1c01084d99ac8cb9ff",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_0.png": "df30c08289246a6e105082d0ff92dd64296dc942b2839dde9ac85347ac55f0b3",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_1.png": "582fda688af42947136b2f28c736557372a225db64317ae07d1413d7e1765f4a",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_2.png": "676940567e5f2966d1d0963f6e57b26e961acd6c0b6ea80ebd49cad5de9b0b62",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_3.png": "72850693bccdf09040724524cde133f7a85f06b4368fa47fa33e8e326a1f60d5",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_4.png": "65f7f8b602fa538acd678b524d717aa4042c54f6b60418e8af9adcc0c33c3a52",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_5.png": "052710e271f82e248fd40534423de2550dcabf2e142d8b425a0b2c7a1d40e416",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_6.png": "529f4a9b0671ed57defe64db2f9c1222df73b7bdbcf3a0795a8a4ce39508dcc7",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_7.png": "c33c20fc31071d7adb4deb92d9bae973926dc48d47ed3de5e04193eb3d2224ec",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_8.png": "99159e9f8692cec8c14d20b242f36a163633bec6666802db9cfe47e765088889",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_9.png": "05bace00b1bf59690dfd09266a03c2b0b81f8df15cc81edb2da2f0cf4e606942",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_0.png": "79c27fcac02295e0d9b6e12c64084d8aa96834fc29cc73f4a8571ef7d270a741",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_1.png": "d33f93cd409003d5491a201b71805571bc0e119c65e94885a53ff50c366bef5b",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_2.png": "c36498e49d7325c7d8287f1e4ce7c11fd431920b2bf7f7e3b429077f3ca7b825",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_3.png": "6d738c37655dd9687ac92d1e6417215a1bd7a9e5e9108bebd3b4c0d93e07e540",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_4.png": "528b34b0ddeeb3f63177294b8147f30a01dc03f9655feaf6363bf818e6b962d6",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_5.png": "f3b2932a9cb8bc49e2ddb2fbdfeffbe2d5f18594921da7c5b9f1c34f5979fe9d",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_6.png": "870c3fbd0e8ae2fc77e4b4737957152a17f0d2aa250d10f07712e606a2a1e1f6",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_7.png": "3f6d2536d47e67e58e13dbec013b9a6b09fae12ce467747abe58325aaea399bd",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_8.png": "e180371cf9055760753377f678f4e7e3f6064fb982c85843825803c3959f92a2",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_9.png": "209ecd834a389f6affe39069fcc6dcc0ba535681c19435b120f2a84285f72739",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_0.png": "798047099ea9567df15357d59ea49b170f2a6d10416226905ddb58b92dc22593",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_1.png": "7b2afd39c1c5001ff380de7f919dbe33854a9fdc39b1ef91a79008138b01d144",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_2.png": "fb0993ae0f4fdb2a3a970208156dfcc89bc2353a94cebe356735567e6ec3ac6f",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_3.png": "727f18bc633ad1c4e5a00c6487375eb98640eb93bfa58ee6eca34d3eb5da7741",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_4.png": "78f30b94836db615dbe4ec0177959db094b651e71be0342921feaaa0297e41c1",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_5.png": "9993b755f53a1ac61960721c0bd9474bdf39882b397b487ef61dd8539e70b38f",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_6.png": "583faedd0ac7b6279427c94c56045404812986ab2cebdc81ad68c1869ed40875",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_7.png": "30f2f2f5a6bc77ef5caab74b5891effcb5e7681b08899e0feb2086889b4ee8fc",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_8.png": "01c9f06ea6e706d6a7360464fd3871d727e9f2829b58fd91742c41767ab36d99",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_9.png": "1f4a7e4f109abdbd4b9f6e3f75431ed4961512937c80b49ac95dd1f7a948674d",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_0.png": "99cfa85fa74913c9f36306e1479cb7058d16c5cc188102c5105250b8a3ef66c4",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_1.png": "1caf83398bf8e49574792a3ef76b1a03b2144a8bbbfcd1550caeed5a47a22b87",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_2.png": "b455dc62952803db1df4a401ddb00bb2fb7bd5ffa7ca2e65742c4c336e721be2",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_3.png": "ff4ccfe390b84081a52a690187c4438654c5614116f45004dddba3bf1c0b7cdf",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_4.png": "f42b979abd993139887fac033415ba94e46d151c6ae136d068802e7603e255b5",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_5.png": "b0c26390b23dd258dfacb58ac012f067ed9a0268021c3e9e307b4095db7cf38d",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_6.png": "e4c468be954bccf283227858c37455e1f9ae4aded723c54a4f2075e907809c20",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_7.png": "754f8ee1b7fa4ce4ca1fc74a26d9ca7b0919472dee584a538608551ebf8bf653",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_8.png": "0996e6a6174a93a955a6b53fa55bbfcf3a7438b052557b82abf7dce235b4bb31",
                "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_9.png": "d3bae739e0900d2174aa75a1815f75c9ae85fbfab7b18e6e0cda049fdc2a91c4",
                "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_names.png": "0ea0b1b33bb2990f60786670b08022be2f3b22790068c864eed713b90e562b38",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_0.png": "546a433a34f78c175f50baf4b835b0d8918ce556e705b22d48b03f85e4b329d4",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_1.png": "4bb2c66f0d4b3c01e7c06abb9112f388f1d111abed60fe646e954b5457ba4f91",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_2.png": "20735c1214a0d04b0badd0e313f82712bb188ef3c71ea3258f8ded62318bc54d",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_3.png": "82a03d13a3ceedf17cffe6f6129548840c14439dbc257276b756e3d458c70fa2",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_4.png": "753adc235364c104a670c9dd85aa5ac150db774820fb37085173985d2e0bd3e4",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_5.png": "6a2e0e8107169999e3fa32faa3594c47c7cbed7c8c311a74b28b82dab284e1f5",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_6.png": "ca710b697f5d57fa32b72baeccaa6e7391e38006b6cd52f721351c347301ebb1",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_7.png": "0a09d349ebce80b62dd28a2f635113c79d6852a37b014adfa58a9d71c07c8999",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_8.png": "21867fdf11888b63a33ce0f145f6efc114920d5ed7cb39c4bf251ce84e04c0df",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A0_digit_arm_9.png": "47681ebf5756863fed88443196fdf0ade4bbac7d262639c7dca223b0265847b8",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_0.png": "60055df548d6e3805465164af9457ba883943b2f27c01625225ba34881cc1b3e",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_1.png": "3fe5a82d46596ec5066e9620211994c7a93c3693be59f46096d331963e896f53",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_2.png": "241112df04f92d5dfc5cd679e8d8f89d1cd7561bfaf46ecb35aab669f90f7aef",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_3.png": "f015c2b115ee922841ca214605f7e9a94065bc2a3d9f1757a7d81d609fd66862",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_4.png": "8d1a2f422662e429e5564e2bbb43effb6255d76d57efe887e579e2eb4308c695",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_5.png": "1e7248d6c79b13815d05c82613d36e87fe77a036d147a77cd41743fe2806e7b6",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_6.png": "18fe5e42d95c9e9608c806d4eee4ff79384a3eb40bfdad1549c15795af95c84b",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_7.png": "5e0eaa977a41ed783c8cbecd8896128150526a678105e573dbed211122e382db",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_8.png": "3a9a03f247c0a2fa00ddba2bf9fc2c1da19c9c21bbb47c6c170d253e53531d40",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_digit_arm_9.png": "f15ce082a741ce82dc3ca703c977e2c0a518a5bfc7cddfc1277b16fa25aeff36",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_names.png": "25ddb97de1d977bf31ce46ab0fc2092466b88442cd1e43e558ced81bd5b49860",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_0.png": "a8672fde56cae624c9a5abb4a3e5a8b96179c21492f1f43d974a8d66c860747f",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_1.png": "f12e1d92436b3176269c4caee48e75440cd2faf27d5a381db2c87dbe8415ecee",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_2.png": "ccd6a29f297dc4ab39459b0712de84c6c9438ca6c4bfe78a16b988c49cd74f68",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_3.png": "90535802893dbc6cab551d3c89890d48c507bf9a20c964f1f447bde3c9629509",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_4.png": "f153e3ecc0047b9ed98c36f6f3dfdaabac9d6cab27c7a8a20582efe32fc8dca1",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_5.png": "8983a3c7ecb7554c4078587810ea0f2e26b2f937fa295a75d69ee9a365c97b36",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_6.png": "01457322a6124fa81489d7040fa796b065039692d8aa210f897a8bf0ddd26fb9",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_7.png": "3a5f5fa82127899cf015df7b6900f117ce16bf0248e32bacdd9b694a995f4087",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_8.png": "dd9bc04983684662a4c3775220593c8ec9ca00b464c623888478638e1ef2378f",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18H0_digit_arm_9.png": "b2dbf7971f0ec5715a0d8fa83dcc9b5d8a591e6a69dd03f7098b34e76e1e79b1",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_0.png": "d8c71476316d4c2962cca23b97697d6df1174f0334081afd2ce15cc1ea5a5ade",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_1.png": "185aac0f5bb0bfe8f9e268289776e84e4c899b1ca6b654a05da8164b333a3169",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_2.png": "9c74362d2669472415232f8aa89ec94204f0003a936157c2b53df44a962a4773",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_3.png": "1cf755a0471513cb91a9188cfdd3355577b35e883cd91930582c9fabbebaa2ea",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_4.png": "f87f6931ef812b2595ebbbc1016d34b5d3fb52eecd7c30ed31b6de0bd4d1bb02",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_5.png": "d4c418f2ce363cb30ae4eb4fb3f285e96457ee9c0588f41e1ccc90319828bb91",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_6.png": "74fa19896c718353631c1828be0a1735d8d47a4326748fde76cfb719317433fe",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_7.png": "a20f4920eef5e1b02d4bb2dfb9c8852200c6b4d29e8d43bf1aa010cbf80c236f",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_8.png": "2200371e3e2639e0536b4110271413e287dfde6f16a602f931a6cd84d1394d95",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_9.png": "1d6e012cb70806ffdb548e00c5e94b30767f2857ea17145d0ebd56a25110fbbf",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_0.png": "976668f370c0075514ec8b13d79eba669c52593d8f77658370685c278d09a261",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_1.png": "95a32b2529ee3228e3c5edf899640d82c38711c55bd03c5a67c7e6831267df0d",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_2.png": "34248988b4d7d2a059281b1ba1b32f25666f6911d05682ff0387bd0d7f79878d",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_3.png": "32f4dd515a5154eec565159632c643d4457ed8f04eeacae177b87faa5289cdb9",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_4.png": "b7298ec077051b0f76abb1a5317e7699fb842aaf421713a55d421619a639f98b",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_5.png": "4afa8f5b09895635c4b1095ee99c4e4e21a4d5bdb5f4a324fe16b5c7f6f0950a",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_6.png": "9d3e2c9b9d19cb10bfb73b31832586eac5fe83bc8d25b1daaf792633a1e614c4",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_7.png": "6fbd9ebe200b105139b8b5a836d0395d59f96082ca638da1d2e759c95d68f228",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_8.png": "9a5ec63e8ffdf684e06ed3b370ee7571b54670c8149a15a6c71c82ab1f8c0ed6",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_9.png": "7c7807d85767e5fe74f1c5010f4ec9ef0e59deedeaf8ec40a89a8002fb1b7596",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_names.png": "451db8b57f45e39014cdc6c567dc104ec2433ee38b69f61b9cfff72ff19bf0f5",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_0.png": "defc5a4913ec3c5d3669a4a5c303fe300ada7e315383df2c799690802f025892",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_1.png": "c2bb4b22afbb86ecf38af8b91dd982ab1dacfe19c84efdd04fefbcecd4313d08",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_2.png": "f44453e04c035395a883b9f5a1cff0d29a38f240d3f1a7398b9d6e6e272214ec",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_3.png": "8ff3b9211228d4d3696c1ce644146783eb4138f2118459878a92f11101cad47a",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_4.png": "be0409e9b4c6912c01d818d264965678d8270a2b9ed9bedbf5cabb7df2217fdd",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_5.png": "4f3d4e0f0d7d0bdf5b566f4640ab0c3d604cfce76eef1c63e8897a0efe5fad99",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_6.png": "21a8c50e3208e05f9bfbef1db6b4ab4be26140d61f822c04732b7c82dfdcda52",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_7.png": "8b6241eedc4278e7c0a00c3424f1421df137cc271d0b892d8f9141b837301f7e",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_8.png": "eaf03cc9bf43a544b74f4f075f7a38a9bdbb24bdd8c7df02c6276399f3ebb665",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_9.png": "8c7c11ad05ec95b28efc81815904a8957d1bc526197d9832716d37498efe19c1",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_0.png": "d2efc95238eb0c4ebfa08f00fb4e22515205991542d8006c0040778f5bca1070",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_1.png": "55b8fe8fa5892fc16540e7874b70e1d1b153476b938151d1cef899b566655a93",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_2.png": "e5295329d5174fb4236d5b672bfdac0812950f51225bfc614e1bfae2f9b551b8",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_3.png": "05197e1124c1364bf22e71cb72363b5ef9e6baf8a03092af1be66f98336c1a1b",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_4.png": "b4b9d42bf01e8a27ca32864407e511f0d12bf349204bd593e7413a1c96afe30d",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_5.png": "7518cea0798df82f54f84047e7bde5972163fa0193737a619f8b6c03f42fb028",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_6.png": "6b7385d4cd059aa88c895d3ab6dbac6494a13615647f895f16336e6709093c32",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_7.png": "06e7a73524cd3a4c3b022fdee34a44922a16954f8d8dcd168cf1125276d4545e",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_8.png": "3a73b3f81956ac4f4ebf7d231bf44473464611f16f7d498d2bbd4ab18f7d2249",
                "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_9.png": "9de7ea8bf0816ca3dcf76413a818f6a6445dcdd98d3348d0269177be2d693e53",
                "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_names.png": "928ee9dac1d2a42c060ae59d0d6635e989e718c1cd5915c66b30109ef15fa0e2",
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
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_0.png": "517d0c0798829bcaa7a31e13e7f77d663356718d006da8138f4ed9fd7a97cc4d",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_1.png": "b96e8237b8769518cc78a1c166a229a8675b6e294e14610cb6b114934063039e",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_2.png": "131d8c696d96f669e0ef5448b9df71bd87f5071aefb9b592b4182244e3010729",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_3.png": "3b3f233abd7130cb15c15f92d8f2e9ea1997b8332505cf602933870a854b0d40",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_4.png": "fef01e5275a31c680e70f25468559b4b303d9d5b8454f8350cfd0b2bc828ec89",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_5.png": "1a6d70afb744292345e396b08b81c087247dd4b7187469c7382d8e45744e95ca",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_6.png": "4816cb256d9cb06a8ef47ca860071e88194acd5f99277ee816bbe3125e99928d",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_7.png": "b9ddc66aef7858dfd59910baee71e4d638f4775e24ccd68d7f528d5f04cd89f0",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_8.png": "916a9e94505ba4d7b0b13484d53baa8f92d5d5c7ddc8847cb5f658b41afd38cd",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29A0_digit_arm_9.png": "68e4b466d4680c22943b19c3b795958436601ba2e93ffbb3406a318af18fbded",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_0.png": "30ff99c88e1261d6773e5850a89962a85adae2ee91724e79ec7a051f7bd49d12",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_1.png": "527c5cf11242390bbbed0f86656180f525b8d68ecf12e67e127f5c04a9433854",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_2.png": "d166139cee837e91f88822db447b4e188edaeb6979e0e827f2916b8fba2dee69",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_3.png": "2569241469ba4c5d4f9135990da88bf67d1349657168d089eff8458744798f95",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_4.png": "752a787b1b1cdb4c94112e50cafbac5de1cfb69377875a5f14e9747737076ce5",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_5.png": "71bed9e6ea039ee25200435649ce4835ef37d531f2bad8f8e6a2da7fd288333e",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_6.png": "53fd7fb9a8127caed544040603bb2e5b6ebbc34a240534aa847c58379a5cad04",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_7.png": "6a2dea672b3cd2db50b19dd856702e00c5cd61d656cdc6efa450c12a5cb98f6d",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_8.png": "05c727681b33b8666b2416b75e5b5774a31c44c880e676a8e14f0d590b6ab266",
                "data/nfl2k5_glyph_fixes_2026_b81u/WSH_29H0_digit_arm_9.png": "51cd74bd3634716544a044af9dee863f8bed2352b99eab29322f8207e329ce17",
                "data/nfl2k5_relief_2026_b81u.json": "72008c5b3dd33fecbd49415e2e39b933f0516823565931a517e4e555200a6a01",
                "data/nfl2k5_relief_2026_b81u/jersey_07455b0dd674a0c7.png": "210cd1b39674be73cf77f263270cf8aa12747392450c78f22a9192d30982f8c8",
                "data/nfl2k5_relief_2026_b81u/jersey_077652704ac938c0.png": "283c5051208549c001756dfb3da7324682c787baa8ca1d8211ee84e759f44b50",
                "data/nfl2k5_relief_2026_b81u/jersey_07a20df0345cdc24.png": "2428a6fac855c1a3b100b783d899da872be2ce498e3563ffa862fe5448e9038b",
                "data/nfl2k5_relief_2026_b81u/jersey_1043b438bdb75289.png": "dcdbe2e568a7f17d8db833df58b7faab821a0f4a398c0cc0b9099132be881e6a",
                "data/nfl2k5_relief_2026_b81u/jersey_1d6982d4a0cc85dd.png": "e5d3fc19f20a416693f693e4916926d63b7258bcf25562786631570e88ddac88",
                "data/nfl2k5_relief_2026_b81u/jersey_1e1cdd0261e09580.png": "8abb55bf5e0ca83e1ea7dc9d3c609580046ca9abf8d4c27cf29f23b8171a4d2e",
                "data/nfl2k5_relief_2026_b81u/jersey_20220b9b7d68f915.png": "0238645cee79ec1e8d4b77af9d711fa3c3a8366083f128d03b9d92c25785b5b2",
                "data/nfl2k5_relief_2026_b81u/jersey_218e003a4937fdfc.png": "4b1651bed2c7540e4430633335b28d63e436360ed5eebbb46953d04fbc362878",
                "data/nfl2k5_relief_2026_b81u/jersey_22b7f7f5025f4fbb.png": "3603158bd1dbfc26418b18b61d543382171c3f715855c7009f6dd10e5bf4d884",
                "data/nfl2k5_relief_2026_b81u/jersey_2ae50a650c13dc8e.png": "7516e83c27fde64f87161171eb278d6fad9c2403a37a9893e2ef2b44cf26c1d8",
                "data/nfl2k5_relief_2026_b81u/jersey_2e0aed0cd2e3aac2.png": "5bfc529bfc7131ab8eccb46a79f3a7103c67bbd0c19167c3c5a769f53e341164",
                "data/nfl2k5_relief_2026_b81u/jersey_2fed80204366d356.png": "34374da8b330b0a78068af9f853d6959b14a948edf6c411d14d02449234972a6",
                "data/nfl2k5_relief_2026_b81u/jersey_36ade052be1b6250.png": "6ea34728d76b73299751164342d1680286ee294846a130434efaa1af4a6cf2df",
                "data/nfl2k5_relief_2026_b81u/jersey_3cfac5be1520555c.png": "2dc78e915499263916e51057f30b05c299269f347cfd65e8fe0cd44f8c02e11b",
                "data/nfl2k5_relief_2026_b81u/jersey_3d9057672aab03c6.png": "5fdf4b86f00040356ff8fd2f350610924b91db67070d6ce2c76dcf2c7819dfac",
                "data/nfl2k5_relief_2026_b81u/jersey_3fb2d1173d4b5cb6.png": "2225afd83b150d9f787b130f993b4e553b5fb53c4f70e6dd1fd7687e88a2b04f",
                "data/nfl2k5_relief_2026_b81u/jersey_45acec62c4c7dd89.png": "c81c865b953ecfe8bf3eb1983d321c674feb7dd5fa3e9e7d56c19c8a20344db8",
                "data/nfl2k5_relief_2026_b81u/jersey_4704d79ed733c5c6.png": "4d3bc95dbee59ae4a10bb699d42ca64088856efa2305a008b957438a60429c1b",
                "data/nfl2k5_relief_2026_b81u/jersey_506cf0e07089a05f.png": "9b439653ea24d484f55b06164f024e59f57ac296f456d9cfc946cf3c4d9b5a57",
                "data/nfl2k5_relief_2026_b81u/jersey_59b4b555eac13e96.png": "c968a75962cc6865bd21afb7807bf4577ceaca084af81e34f93d1bd18a6e22ec",
                "data/nfl2k5_relief_2026_b81u/jersey_607260403a67a6ea.png": "458768016ecdca20ea9c4b2ab58d2866ac2a34aa2bd191c2580298bffc7010e3",
                "data/nfl2k5_relief_2026_b81u/jersey_653280ffbba98677.png": "7042cef10e411882e3daf241ccfd579846401af50c088211a1005dcb01fe7cab",
                "data/nfl2k5_relief_2026_b81u/jersey_66fb04c99f042064.png": "9b8044dfc5bf30eb8533c092e5a778a0ad4bd43928417363b2aa1a779d8d2510",
                "data/nfl2k5_relief_2026_b81u/jersey_75cff8d2263787e5.png": "324525b602087834a235df5dd63059c4262c06ea787f4cf3130350939dd4ef60",
                "data/nfl2k5_relief_2026_b81u/jersey_79bad7a4bc1913ac.png": "d9a1534fe9d657678d515e83d3256d73c05a8b005e125d4f4e74f932fa78ce13",
                "data/nfl2k5_relief_2026_b81u/jersey_7b00dca8ea85b550.png": "4e6983cb0ab338b40eff22258a2c2ceb28b85da34bd2f2c864d017cb43cae82e",
                "data/nfl2k5_relief_2026_b81u/jersey_81b8fff879373c3f.png": "e0b099e11d8be16faca8dee965427e745cf63de835bae6d06cbdaecd137cd04a",
                "data/nfl2k5_relief_2026_b81u/jersey_846e6169f662a865.png": "1da9182bfdaadee1491649370a15db095dded5b6cbab9a304d7fd8523314890c",
                "data/nfl2k5_relief_2026_b81u/jersey_87283372455da936.png": "032351d1194b20a21db372a621e0bccbf67f9837a016aafd4d9b06694c286e0a",
                "data/nfl2k5_relief_2026_b81u/jersey_8b3abdfd5aa2a1c6.png": "43073a261e8d3c7f3f15291129d23c00ecef826ca3e6861f0b6ab4bc3c532710",
                "data/nfl2k5_relief_2026_b81u/jersey_903f40a225ac089c.png": "2f3dc0ee5c2e18c5a7c1a18bd21922f3f949691c0c91e150121b21e7481d5c53",
                "data/nfl2k5_relief_2026_b81u/jersey_916322296ce3ca11.png": "236683b78f622845835b85be4a432ace2f7adda8d7ce03f54eec3dc4a0427544",
                "data/nfl2k5_relief_2026_b81u/jersey_94d3517ee0e225a1.png": "1ef77d001cecb8d2f51b8f62028fd8a8fe1489b1d5019e3afc23a813d4e59a07",
                "data/nfl2k5_relief_2026_b81u/jersey_9a37d42ee64777a8.png": "daf5ecfa3afecd2cc432e6bde86e17b217a16abf444f5616c6fb0bf4b301c716",
                "data/nfl2k5_relief_2026_b81u/jersey_9afc6cf8ca462e24.png": "02fa2e7ea9eb326ded6eb3439417c7479f0db3fe614f668690bf8f61618b218b",
                "data/nfl2k5_relief_2026_b81u/jersey_a1a1663d7a49784d.png": "f43691cf6732013244ffc0573b7d96c1310001bee0b1b57f4348dae3ff00c75e",
                "data/nfl2k5_relief_2026_b81u/jersey_a87d064a7e740bf7.png": "71c425254c3e708a50a62ba512268f109db3d68b19640e955f6e322d3ddef22d",
                "data/nfl2k5_relief_2026_b81u/jersey_aa4b94f08dbbacc9.png": "6a8d1c5b500bfcd851c41f066ed35731592ef5e2445b957ba23ea43ececb788a",
                "data/nfl2k5_relief_2026_b81u/jersey_aac2997da6002b8a.png": "634fcf18e70bbdb138445ce3fcc3d47c936d4e815622743f638faa4091a02693",
                "data/nfl2k5_relief_2026_b81u/jersey_af55342f87d0fa90.png": "99202c4f431b752bb02ba625e41341ac745c015c1385fc0b3178d24410c91f3f",
                "data/nfl2k5_relief_2026_b81u/jersey_b13108b1f2ca82bd.png": "3f0fea5866f992f2571afa6afda4ff8bad4ca54eaffea911c1d8cb8bdf8a034e",
                "data/nfl2k5_relief_2026_b81u/jersey_b266a22096caeeef.png": "b7207b72cf16c2ae732a2823081f326196c524669d33c81c14580c99fb07ef01",
                "data/nfl2k5_relief_2026_b81u/jersey_b3e814dbe4da607a.png": "05d39a0f9ad94fcc5c22da8d83fb6b07a3502d53806232c92ff63a7bf4043c66",
                "data/nfl2k5_relief_2026_b81u/jersey_b4ccbeb021700f48.png": "d434e6d149fc0248fd227d1f2d0a010825a08c9460a4be3b01e9583c8d0bbdb6",
                "data/nfl2k5_relief_2026_b81u/jersey_befd1d3672ed4d82.png": "b2de3c1a6a716d73f7710d9443ee3d1fad64cbe5eb4cd8f9d56838366089bb79",
                "data/nfl2k5_relief_2026_b81u/jersey_c2c01c46e7f6be8e.png": "08e16832ac5e562b8080b2077323a0f990e05417805eaf9bf606ac8d9d6af651",
                "data/nfl2k5_relief_2026_b81u/jersey_c9fddbf8b7171c66.png": "17703d81c3f47259c1bf6ac390f8ae3ca5450043ebe4b185bbcfa618a987fdee",
                "data/nfl2k5_relief_2026_b81u/jersey_d5199e9d21d741e2.png": "6962d523430fb2e09ed5e078984054a3321b63b6d2e89a5fd9f5bb97c886b0f3",
                "data/nfl2k5_relief_2026_b81u/jersey_d655836553bc4d4e.png": "556b58aa17b103ad5da06eda06c5136afc5827a2f1af17ee40aa537fe9ea3cc1",
                "data/nfl2k5_relief_2026_b81u/jersey_da152345df861226.png": "66a8e6cd7094b955ab1b27b10b48cb354d99cffa02790021ce33ff8516167336",
                "data/nfl2k5_relief_2026_b81u/jersey_de821007e8d3a6f0.png": "a8e6d85335d954e7726fd17bbc4bfd820860fa5f5fc3d984e4046817fa7570ee",
                "data/nfl2k5_relief_2026_b81u/jersey_e0aba02d3c3ace1a.png": "cd49923b5097448b60ee5bd1b50eee07322a4200cd8012d806eb4096ceb8f568",
                "data/nfl2k5_relief_2026_b81u/jersey_e0b7c840866d4b7b.png": "65a72eda87e48d8da5e71d803010f99416d0fbd2ed7bdb81686c3684a9a7b82a",
                "data/nfl2k5_relief_2026_b81u/jersey_e173be245727935e.png": "f588d39ebcc6535c7dc3e67f2daebd4c4e56f0cb8748cc956eff1e5eeb1492ca",
                "data/nfl2k5_relief_2026_b81u/jersey_e50358ef1b035d2e.png": "076ab7fca0ce9b644fe0eedf5684c79daa1cfdab0919d413046ecfa2911ae214",
                "data/nfl2k5_relief_2026_b81u/jersey_e5272a3e12e20c2c.png": "431aaa50ebf5f40f94d36fcd0ea447560425ae3919e3e53fa16fd3f58a6472e4",
                "data/nfl2k5_relief_2026_b81u/jersey_e52bee8b28b5b6ad.png": "769f232efdd26717d45612c0a010fad10596719021d4aa5e1b869672c03e7a95",
                "data/nfl2k5_relief_2026_b81u/jersey_e63736ac5c9186e3.png": "2a13fea884ab2f7ccf79ef64fb9ed0fc49d17c645e28dc9abdbb4f743a434e2c",
                "data/nfl2k5_relief_2026_b81u/jersey_e67229e6bc318f0a.png": "7918e138e2c013db1f2ff770cd3b8ad504cc5ee7957248cab478982f4c04b698",
                "data/nfl2k5_relief_2026_b81u/jersey_e896e591252c0dac.png": "4397b7b6b4ca166b27e599f929815acbbd6b9323b5459006a1ba3a44ae6bf22a",
                "data/nfl2k5_relief_2026_b81u/jersey_ec8d79c2a2f724b3.png": "bc82b90c2cfef496c108ad22b2085becb985ffbd1938eca0dd65cc96142edd30",
                "data/nfl2k5_relief_2026_b81u/jersey_f1c18d500a39a549.png": "3699684596e474161a27400f7993ed18c07b0fb5eef0f68a3b242d2b15f9ca26",
                "data/nfl2k5_relief_2026_b81u/jersey_f44770301bbfc028.png": "bbe415b77aa04359aff0566ab6888b86448438bd6b84c36e0c2e6b6444191151",
                "data/nfl2k5_relief_2026_b81u/jersey_f4862170137874d3.png": "26f4585493bbe73ee063e0c914334a522a484acd49da978d586e0bd35f4bbc04",
                "data/nfl2k5_relief_2026_b81u/jersey_f5147d3d64580ce4.png": "b09e1806982b8969ea5cd9daaa54301dd14714c56d7c1b4d906e6dc752f6ef28",
                "data/nfl2k5_relief_2026_b81u/jersey_fb44d33d0cfe7409.png": "849f2df101cfb7d030acf890a47a0753f3987b8bcac49f8695d9566669781051",
                "data/nfl2k5_relief_2026_b81u/jersey_fbf0dd5fdaeabfb0.png": "0a4416a1c1a706d429fadbe2f35bd39ecfac9e399552df8c501a1718758de383",
                "data/nfl2k5_relief_2026_b81u/jersey_ff031f8c87b962eb.png": "a5d3d65e05c849c3223fd5737312a25cff9fa7c22aac384475e18bb836b7f928",
                "data/nfl2k5_relief_2026_b81u/master_jersey.png": "c8f1909507dccf81715aaf9cc26441e19b6f5e036d2e746ead11c8da9e21f2c4",
                "data/nfl2k5_relief_2026_b81u/master_sleeve.png": "ee78c8b5597d5c88aba14061ae992ad82f9e1404a1c246797ec46f3689aeef22",
                "data/nfl2k5_relief_2026_b81u/pants_0662230fd4721e1f.png": "46181df006a4f2e914c2eb51a6417a2a2d7c052542a4225b5746cb5e5cafb236",
                "data/nfl2k5_relief_2026_b81u/pants_0825b54701266a2e.png": "f1ff4caf168f98d384fc4cd3c2eedfa15798583eca84f0c76f104e24576b5565",
                "data/nfl2k5_relief_2026_b81u/pants_0b06dcd40320eb2e.png": "435ace187942fafa8029ac6badc386b1029d4408120256a8d2f4304fa64d04ac",
                "data/nfl2k5_relief_2026_b81u/pants_0c90730f3399faa1.png": "f7ac3bde54e07b026d06e8f8f19a9280d11892b27159c704986c80ea600e916c",
                "data/nfl2k5_relief_2026_b81u/pants_0cccb0a706f2f86e.png": "b4138952b19c886395ed691fbe49db704122c82dc90a9b9aefcceffd647e8ace",
                "data/nfl2k5_relief_2026_b81u/pants_0d641c77f5ea00d3.png": "1bb4312d4f959e8eeedfe81aade6de0fce0de2379e1211738aa5e61466639014",
                "data/nfl2k5_relief_2026_b81u/pants_0f094f9abc939e0c.png": "d3bbc7e9a0b0e9516d9a9565dfb96e108087ff5b5e804a316a82d3ae7a0079f4",
                "data/nfl2k5_relief_2026_b81u/pants_172802cf7c436500.png": "ead34d414eef92e137d82c21a9b2c31193d3067832ff2d41dbf8a32d66624d3f",
                "data/nfl2k5_relief_2026_b81u/pants_1b405ab26322a41e.png": "7471a072677ef8cee4fa760d6aadcc6ead873d081478a02a6dee0ae58ee20418",
                "data/nfl2k5_relief_2026_b81u/pants_1d8f27ed523e7729.png": "3b274c33a4f10c457a13ce09241e531a767c4438386d35de2b276f2594c31866",
                "data/nfl2k5_relief_2026_b81u/pants_1fef022cc2d97f5d.png": "7052c721b6566921e233d62f76043d2b1217b2e3798f5994e868d773634bb266",
                "data/nfl2k5_relief_2026_b81u/pants_234111ede140fde0.png": "9fcb0b6381dddf03268b08a86941b906c167234c263d0d225e992ccb52ae3dde",
                "data/nfl2k5_relief_2026_b81u/pants_2403c17006c51dcc.png": "6bfa300746b2d92e5cb984d5e4d20a6917935f14c038a44e4e320f167f334609",
                "data/nfl2k5_relief_2026_b81u/pants_2425e429d0acc806.png": "29ff8e7a6b93b486ebc6cc8a0d4fabfe0b0cf881371abe34adb05a59971e45d8",
                "data/nfl2k5_relief_2026_b81u/pants_246838e8f8520ae2.png": "4950ead8e0c0f02cf43bd1d0c3766b04f3357dec2ceb802adc78f670a927d8fa",
                "data/nfl2k5_relief_2026_b81u/pants_27b83a4755b90c11.png": "8fc3d8f8908626de4f36ee399f589c4bb663124d46d04192cc25b2b8a7aa1bbd",
                "data/nfl2k5_relief_2026_b81u/pants_2caff720cfd90f5b.png": "a7db61f3232b36d1d4b3afafd8df04360dbbb6fa02f19f82f23ab567cc7b0d2f",
                "data/nfl2k5_relief_2026_b81u/pants_2f92df1bf1c443e8.png": "3ab17ef68e38440021f896d5d696ac5ca3541783ebf8534ed7188ac486d4033d",
                "data/nfl2k5_relief_2026_b81u/pants_303367a6534a2943.png": "a5ef25bbd37195ed2ae7c381de6a984ea2334c28d43bd8ce5d9d84c4bcc30c52",
                "data/nfl2k5_relief_2026_b81u/pants_361b08ecbf59f9c5.png": "55f877acef83f516568ee8d078b3480ca65db0d3f2e993cce244ee985235d381",
                "data/nfl2k5_relief_2026_b81u/pants_3716a7b24451fda7.png": "f9affe28d08c384fac4f82e2c76d8b924e372f4663c8ff72f4e1c81597acec24",
                "data/nfl2k5_relief_2026_b81u/pants_373d11d641f0ffd4.png": "f875534f6c337949b78b07c629ec62eca45efc6dc916e993a499965b1a69e8d5",
                "data/nfl2k5_relief_2026_b81u/pants_4119d66ca80fa1ce.png": "46155a82c674851dc8f12fa7a2fca2aed0f3be4631e10bf3aa5bc7f91e7d43c9",
                "data/nfl2k5_relief_2026_b81u/pants_52505f67d7130c29.png": "13ac10c21f742076857a4f7d713dbe8036ac3724d09668d78dd626871baa1fb0",
                "data/nfl2k5_relief_2026_b81u/pants_550d89f4d631d223.png": "4dff4522b3d5cc9bb0fa5b9840e77c1e45716e2c8339196fc48a9c9cef904508",
                "data/nfl2k5_relief_2026_b81u/pants_5a5541ef5e7ed062.png": "796ed01a41421b1ba9146dd119fbc5692870f1dd49634ad0d0d7e7391108b90e",
                "data/nfl2k5_relief_2026_b81u/pants_69e96c9ad38ac4c3.png": "c82b68422d4add75763cdca0735921a8cc0132df214d12a3b6fca57af8879b28",
                "data/nfl2k5_relief_2026_b81u/pants_6b38c1b08055d8ed.png": "6e31088b13d93d78e1be4e98c360923b890eb2f2ba84c9f1647dd9e0dc03b77d",
                "data/nfl2k5_relief_2026_b81u/pants_6d16e178b839223f.png": "7482d143a997d093dfd7a46474a0e12cedea1231edca2a8384441df814553305",
                "data/nfl2k5_relief_2026_b81u/pants_745132c53afe0aae.png": "37c6a46c6bc5569416504fce82f6ff9208404d38ceee439105d6522c969e8a1b",
                "data/nfl2k5_relief_2026_b81u/pants_749c4e99240cf615.png": "0fcab479e662e46542f727c02a89c03072a0a2416da4870974ad8dbd209ed810",
                "data/nfl2k5_relief_2026_b81u/pants_750f121982e3e868.png": "48b7e0203cca1b555bf29b648c53261ee361022d31a45d2a462786891b6dbffd",
                "data/nfl2k5_relief_2026_b81u/pants_7839a13680b5f6e7.png": "a303fee317eee3dbf147d07a5d6336bb3c6972589fec1084fb602de0720eb06f",
                "data/nfl2k5_relief_2026_b81u/pants_78d7cb7b621914a4.png": "d1fefa96b8aa18f612c1ac07ec1fb6ac6462f2577c34d4d49931cb784a068319",
                "data/nfl2k5_relief_2026_b81u/pants_83f1c7d5ddab730a.png": "fe163726bd050c7508f7c4cfedd0ae63378a885a09347ab211f13c7409d6befc",
                "data/nfl2k5_relief_2026_b81u/pants_86ff7e30d9a659e0.png": "23de52580d257cb0532713531e0075c989ed230cfbcc2a89c64d316fa5abd02f",
                "data/nfl2k5_relief_2026_b81u/pants_889748f3a05a0d90.png": "ba7846f168301a3835c94132c625e176abfc0e23392c5dcec9df0ac8bab06a80",
                "data/nfl2k5_relief_2026_b81u/pants_89d36d6feb11db63.png": "0e3c953bc47d5b2eacf558e57f2b307267dafbad178ac0c8243e433e47b82a30",
                "data/nfl2k5_relief_2026_b81u/pants_965099449dc4405c.png": "b5e910250e2cfdb72f177644241e7c711d102ffe43fcffbf83cc7e4879234027",
                "data/nfl2k5_relief_2026_b81u/pants_a5d8710528614507.png": "e8c865954db7dfed874ecf1368dc077eb0813ac0b1784e3bababa05dba5270ce",
                "data/nfl2k5_relief_2026_b81u/pants_a8013d92cf59751e.png": "f198848baada2b511a9e4e6a507d570889f53b9acc2bdc395e915d560a85ec11",
                "data/nfl2k5_relief_2026_b81u/pants_a818230f35d70896.png": "315afacf888a11a9e7a976b7226ffcb3a0b9cf6abf5a10db49336f7fbce7714d",
                "data/nfl2k5_relief_2026_b81u/pants_aa493ca56e3a4e38.png": "9c608f9d33ac65bba42dd6113a19a75d45fdb12321934dce11488973e84fa3d0",
                "data/nfl2k5_relief_2026_b81u/pants_b2bb3d3583a77200.png": "44f619c04834d539e95c56f3ac59b127984781883c6da5a40dafd848155e57fa",
                "data/nfl2k5_relief_2026_b81u/pants_b2ee5d754df4b695.png": "7d947701c379bea146d3f45ad4f2a7f20d9e43f1768820257f0ebca1e71d3c0a",
                "data/nfl2k5_relief_2026_b81u/pants_b8aadf226dac57e9.png": "e4e63e00cf0439e80277f86b70316bba32acc618347bdf41418ae73636ed25a6",
                "data/nfl2k5_relief_2026_b81u/pants_bdde69a7c53cbe36.png": "eb03804c2cb3e0844945481798aa8b3f5013154130564fa2b855c8dc2b4ca87a",
                "data/nfl2k5_relief_2026_b81u/pants_bef2e85478c82396.png": "64bf3b67e4a32d1f5a54041bbe02fe8f6cb9b75c26c4d7bb7f435704da94b8fb",
                "data/nfl2k5_relief_2026_b81u/pants_c5a5f6f752b074bd.png": "f6fb062c95b1f31d714b01baf06454ecaef17c12219bb4ccc02cd182146261a8",
                "data/nfl2k5_relief_2026_b81u/pants_caee74fa982b6209.png": "cb44a9dbc42baaae8b4ae71776709e779d670d143c2910d7cac015e17ecb53c5",
                "data/nfl2k5_relief_2026_b81u/pants_d32d642882af3581.png": "c947c0935631bdc8fc43a10ae0d4cfb707420da03884b55cafb3a14f9e0944b7",
                "data/nfl2k5_relief_2026_b81u/pants_dbe670c848a68292.png": "e90d79faf4b19d94b832d28a2de33d7275500757e0ef8b92c579128843555a4c",
                "data/nfl2k5_relief_2026_b81u/pants_e84919aa93c0c165.png": "fe38f3efa7051ff0cd95093b39e2362cc4ab2ec58e8162b02026dca780d375e9",
                "data/nfl2k5_relief_2026_b81u/pants_eb9fae8fca7ba4c7.png": "b1447277ba2045b58345ea5298c494c24e7866458982f216fad0e12bc2de0edd",
                "data/nfl2k5_relief_2026_b81u/pants_edb6ac6338c46ebd.png": "c38895761fc03c2883eec45bb37bb27a10ec31d3223cc2f7003ac9227e4f389d",
                "data/nfl2k5_relief_2026_b81u/pants_eed9b3ce6040619e.png": "fa115da75048145d1dd7e838a8ccff94d7a96bb9c822da892901bd0a3e444a57",
                "data/nfl2k5_relief_2026_b81u/pants_f3c7d51a60aff8dd.png": "29c9719fdd8cda8670f705e55df0f8572728f801ed5dff996ba5752ae26272ec",
                "data/nfl2k5_relief_2026_b81u/pants_f6a51e19e14e3c38.png": "d2dd063863e3e3b4021fb5c248fa6540500e4c9b1447d0bc50983adf44bfa326",
                "data/nfl2k5_relief_2026_b81u/pants_f7bcb784c3f5c2a4.png": "bb081e1fde9679db93fb8b74c4c9deff78245a8c29028bc6e4639e21748d67d2",
                "data/nfl2k5_relief_2026_b81u/pants_f8c59e6382bbcf97.png": "e32e4516e71723defd1839e2c10fded87ae635890c611ce239ca9faf6eb27101",
                "data/nfl2k5_relief_2026_b81u/sleeve_034935d35d8205b0.png": "81a3eb448501c0cb9527e12899f3b3ff3af83ed737b88db285e243e7d24349ae",
                "data/nfl2k5_relief_2026_b81u/sleeve_066db47a4c768a3a.png": "23e21e02dd944d20ee223694059747abac4e493c972b5658944ab71b8538e74b",
                "data/nfl2k5_relief_2026_b81u/sleeve_0a4b31e623406fb0.png": "3ec287b33a096769f72c1345cf762cba579f886853265588a82d1064df3f9a47",
                "data/nfl2k5_relief_2026_b81u/sleeve_13f6354aa2d9a553.png": "8fbd930a6ef15ccb799091963ff4bf53ccb866ce81934878cc22d496d41610e0",
                "data/nfl2k5_relief_2026_b81u/sleeve_1a25bdc5893e7ec4.png": "706427e1f747a0abe0ef1a47626143ebe8212d7696ba80e4b98bacdfe7da71bd",
                "data/nfl2k5_relief_2026_b81u/sleeve_1c9a65c4b1de791b.png": "a146922af839cb4cb0e5dddad64a5f4a9c7fbc9450a290f3f56c1bf7b6e8150e",
                "data/nfl2k5_relief_2026_b81u/sleeve_1f4beae5d4860085.png": "cb4c9aea33fa6dc552b5089d724e00df3d2f14f7666afd5aee8f06841999b46c",
                "data/nfl2k5_relief_2026_b81u/sleeve_1feadbacb9b1dc27.png": "68a41e7feb3bda472853805ec8f311261d370733c1c77903a92fada11038500d",
                "data/nfl2k5_relief_2026_b81u/sleeve_21643279944b2ac4.png": "732d7b5fcbc59fc5b1748becc5cc9c4baa52a170778ce40d1bb7bec3d3bdf980",
                "data/nfl2k5_relief_2026_b81u/sleeve_2879f7e7d25217e6.png": "55791dd55e5eff3d1870008bacd218e4de400088ae5bacc31c3dab33a03c63a0",
                "data/nfl2k5_relief_2026_b81u/sleeve_2bb691965a3b4703.png": "9fc3a1f8dfff13cf803d596f78cc377a8942c2d3cd93f0ccbbceb494bdea5a77",
                "data/nfl2k5_relief_2026_b81u/sleeve_305714b9c53b3f72.png": "8db1c052533e0ffab09367d94f4731a75af415445e8e12f0aee316582fdf1ee3",
                "data/nfl2k5_relief_2026_b81u/sleeve_37e3d2063ba7fedc.png": "ed36c3e01d82a2abfb0f470621f86a1b184ef491b08977fc4b585be544dbf6a2",
                "data/nfl2k5_relief_2026_b81u/sleeve_3d36f62e90949bbe.png": "7afb229613c36e4c15e85685fbe8166e784e5f1dbf2145bc673b90e7c6bdf40b",
                "data/nfl2k5_relief_2026_b81u/sleeve_3dcecc1a697f1fb5.png": "a81e9cbe4c644f3931f256244a02ae5ed8d52191f35d8bf2cb6e87d2bb151d15",
                "data/nfl2k5_relief_2026_b81u/sleeve_4f4883c32f242925.png": "b33380779d23ef5a817d7d13e22b3a628d2546680e9eca672385be872a66cf3d",
                "data/nfl2k5_relief_2026_b81u/sleeve_5902ec006c112dbf.png": "aa14d676d9367c562a54b1cfa7e64e3433a6fcd276a0ad02f70ea1a47a70a2c0",
                "data/nfl2k5_relief_2026_b81u/sleeve_5fa4286b34a9fdff.png": "627bc86a83ded2c3bea07717c6865fe0a1f2d48cd4eb981929c5711812d944d8",
                "data/nfl2k5_relief_2026_b81u/sleeve_624185844b4d8d96.png": "67764e94b73aa774d562436b7e07640e98fa10cdee42d6fcca3c74db22cdeabf",
                "data/nfl2k5_relief_2026_b81u/sleeve_64e27a3fa8f1ad33.png": "d7c98d97c590f6a4d77dd3f084e9eb764816189e9f3290653a913c8ffa2ada02",
                "data/nfl2k5_relief_2026_b81u/sleeve_68eb29401eae2a38.png": "2100d06fa922ee17df09c1153772e72c407cba4c502ab0236edd724ebf9e55d2",
                "data/nfl2k5_relief_2026_b81u/sleeve_6d2cc59a2eca635a.png": "4d1637857f7daa477c388a0178495d29d289c25f7bde0f726f5fb3399278d578",
                "data/nfl2k5_relief_2026_b81u/sleeve_6da3309ddbfa10c7.png": "e8b7e14344b23311473cfa480a3c23b9a7350dd0f7de4229ade202ff07b7bb66",
                "data/nfl2k5_relief_2026_b81u/sleeve_829d762723594404.png": "7af1439b2385cd9064236d6107f8b15832c1c509b04bc57697d301c7163c0b85",
                "data/nfl2k5_relief_2026_b81u/sleeve_88196c94c92abb8c.png": "075e625716827f40488cf63c615192c7d60e4a7646c1ba6af13ff1256e678156",
                "data/nfl2k5_relief_2026_b81u/sleeve_8991fea5ebd1edbe.png": "c15c05fa3e8b9fe9008f0e61ea873043de0f4286f3621649e0e6e61d2e4f2bb9",
                "data/nfl2k5_relief_2026_b81u/sleeve_9953ebfbdb0f43f2.png": "9c9d51aab24497d9ddb8406c4c446ee6ec8266b15dc2d28a252082fd8cc0e345",
                "data/nfl2k5_relief_2026_b81u/sleeve_9a0512a9e2c1671a.png": "5b838dc2e16dd9a04bcc70de15813b35791888cf0ca7fbdd3ee00c713a15e793",
                "data/nfl2k5_relief_2026_b81u/sleeve_9e3556cf6e86dc2b.png": "d57420384e15a7230865a984e4b11208eda5119bb66bfb5897260e6e76e49f6a",
                "data/nfl2k5_relief_2026_b81u/sleeve_a29cde9d570c3ebf.png": "410b1f3a4d255e85af99c2b7d970dc46cd851540d419408e87be649b263e234f",
                "data/nfl2k5_relief_2026_b81u/sleeve_a61082c93923d7c1.png": "28f1b30fac81307151bc7750d5b5e028d38946e39c174e52d395e4b1aa9e7d96",
                "data/nfl2k5_relief_2026_b81u/sleeve_a85b1a9b5508ed2e.png": "9736c1df5d3a32ef84506bd2951ff6db2b3f4a34948c47a57ed675b91ef591b1",
                "data/nfl2k5_relief_2026_b81u/sleeve_ab7c3cfeaefcae58.png": "b92a4a33fb983738186d716c3116704a96fcdaa94491663fd6b554179fd11625",
                "data/nfl2k5_relief_2026_b81u/sleeve_b780340070578096.png": "ca76781b780a13f560c6037a4078d9324772ae2b0e259017e724badaad1d6000",
                "data/nfl2k5_relief_2026_b81u/sleeve_bb065d90a136f944.png": "e093e7c34f118fcea67a485c9d35c0f6336456ab434792a7c6125a0a89ccd3e3",
                "data/nfl2k5_relief_2026_b81u/sleeve_c7b9c36b8faaa180.png": "854db5c29d6f9c7b5c59b0491ff1129e38e8f35ba0e8adeafe7882d5d293a5f3",
                "data/nfl2k5_relief_2026_b81u/sleeve_c8a019674382bd16.png": "5ec8229f2dd2061ac956eeadd4c87d2bda7df5f8afd51bd2a03f2840e09701df",
                "data/nfl2k5_relief_2026_b81u/sleeve_cc226823dd57d860.png": "a723830de0dc68d52714944bc1f6cfa0c2f4a5314e314d4ec46c14832becd742",
                "data/nfl2k5_relief_2026_b81u/sleeve_cd469f1e30851d89.png": "14118f113c5c4840a2d976af619b738d365769ad471b01608c2ccfd170af9f1b",
                "data/nfl2k5_relief_2026_b81u/sleeve_d39627bdfbc31c57.png": "b8083e04bddab338624beb2dabc6895d7dd4c0deb491f12a4f5aa486ec04931b",
                "data/nfl2k5_relief_2026_b81u/sleeve_eae54a8eb135d8aa.png": "d3830965fff27289cb0e7529b0787857e860be74c03da514f4a1a2b6278813fa",
                "data/nfl2k5_relief_2026_b81u/sleeve_eb29507a617e8eca.png": "3fb6d123e5f62243dc3e6c97a41362706d0946bed92e06cdeac6ecdd300a8663",
                "data/nfl2k5_relief_2026_b81u/sleeve_f3d45cd59f18cb6f.png": "48e47df105f849e7633b71cf5864222dcfd7b0e19a979a28e44702ea940a15f4",
                "data/nfl2k5_relief_2026_b81u/sleeve_fe4f6e8cfc26c931.png": "0095d323c66ed167bb2056c7a110d4e3c0ebbb39a9aef658b6580bf95d40ebba",
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
                "data/nfl2k5_classic_teams/classic.json": "defcc410cb3ca1bec867f0a05fe8ecd599d727e9107426cfa2fa709473cf4b69",
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

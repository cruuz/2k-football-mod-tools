"""Historic teams in Quick Game: the owner, its Build wiring and a bounded native Team Select proof.

Retail-free classes check the generated code, the six call sites, the allocator budget and the Build wiring.
Retail-backed classes skip without the private USA default.xbe (and its extracted disc folder); they install
the owner, refuse mixed bytes, compose it with the practice squad, and run the real Team Select handlers,
C2300, C1030 (the practice squad's ps_import) and the ESPN 25th Anniversary loader under Unicorn
(tests/nfl2k5_historic_quick_game_native.py names every substituted boundary). EXPERIMENTAL / UNWITNESSED.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as saved  # noqa: E402
from mod_editor.core import nfl2k5_historic_teams_quick_game as patch  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

KEY = "historic_teams_quick_game"
# Retail step functions each call site reaches today (the six calls this option retargets).
RETAIL_TARGETS = {"home_next": 0x2C18D0, "away_next": 0x2C1910, "home_prev": 0x2C18F0,
                  "away_prev": 0x2C1930, "home_random": 0x2C18D0, "away_random": 0x2C1910}


def reseal(payload, va, value):
    result = bytearray(payload)
    at = XbeImage(payload).offset(va, len(value))
    result[at:at + len(value)] = value
    for section in _sections(result):
        result[section.header_offset + 36:section.header_offset + 56] = section_digest(result, section)
    return bytes(result)


class WiringTests(unittest.TestCase):
    """Retail-free."""

    def test_requests_are_in_every_owner_union_and_the_budget(self):
        self.assertEqual(patch.REQUESTS, ((patch.OWNER, "code", 1280, 16), (patch.OWNER, "data", 16, 16)))
        self.assertLessEqual(len(patch.assembly.CODE), patch.CODE_SIZE)
        rows = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([tuple(r) for r in rows if r[0] == patch.OWNER], list(patch.REQUESTS))
        from tests.nfl2k5_allocator_stack import REQUESTS
        self.assertTrue(set(patch.REQUESTS) <= set(REQUESTS))
        self.assertTrue(set(patch.REQUESTS) <= set(space.dormant_union()))
        self.assertEqual(tt._selected_space_requests(historic_teams_quick_game=True), patch.REQUESTS)
        self.assertEqual(tt._selected_space_requests(), ())

    def test_the_six_call_sites_replace_calls_of_the_retail_step_functions(self):
        self.assertEqual(len(patch.HOOKS), 6)
        for label, va, pin, entry in patch.HOOKS:
            raw = bytes.fromhex(pin)
            self.assertEqual(raw[0], 0xE8, label)
            self.assertEqual(va + 5 + struct.unpack("<i", raw[1:])[0], RETAIL_TARGETS[label], label)
            self.assertIn(entry, patch.assembly.LABELS)
        for label, va, before, after in patch.sites(0x1000000):
            self.assertEqual(after[0], 0xE8)
            self.assertEqual(va + 5 + struct.unpack("<i", after[1:])[0],
                             0x1000000 + patch.assembly.LABELS[dict((h[0], h[3]) for h in patch.HOOKS)[label]])

    def test_relocations_name_only_retail_functions_and_the_state(self):
        names = {symbol for _offset, _kind, symbol, _value in patch.assembly.RELOCATIONS}
        self.assertEqual(names - set(patch.SYMBOLS), {"state"})
        self.assertEqual(patch.SYMBOLS["team_release"], 0xC2300)
        self.assertEqual(patch.SYMBOLS["team_import"], 0xC1030)
        code = patch.code_for(0x14DA000, 0x14F2000)
        self.assertEqual(len(code), patch.CODE_SIZE)
        self.assertEqual(code[len(patch.assembly.CODE):], b"\xcc" * (patch.CODE_SIZE - len(patch.assembly.CODE)))

    def test_template_reproduces(self):
        from _gnu_elf32_as import gnu_elf32_as
        if not shutil.which("as") or not gnu_elf32_as():
            self.skipTest("GNU as with ELF32 output is required for template reproduction")
        subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_historic_teams_quick_game_assemble.py"), "--check"],
                       cwd=ROOT, check=True, capture_output=True, text=True)

    def test_build_option_is_wired_like_the_other_allocator_rows(self):
        from mod_editor.gui import beta62_options as r62_ui
        self.assertIn(KEY, tt.R62_SPACE_KEYS)
        self.assertIn(KEY, tt.R62_RUNTIME_KEYS)
        self.assertIs(mod_build.BuildPlan("", "").historic_teams_quick_game, False)
        self.assertIn(KEY, saved.FEATURE_KEYS)
        self.assertIn(KEY, r62_ui.KEYS)
        self.assertTrue(mod_build.availability()[KEY])
        self.assertTrue(mod_build.BuildPlan("", "", historic_teams_quick_game=True).wants_xbe_patch())
        for name in ("softdrink_basic", "softdrink_advanced"):
            self.assertIs(mod_build.PRESETS[name][KEY], False, name)
        self.assertIn(KEY, mod_build.PRESETS["softdrink_experimental"])
        self.assertIn(KEY, tt._deferred_r62_options({key: None for key in tt.R62_RUNTIME_KEYS}, True))

    def test_the_caption_names_the_local_modes_and_protects_created_teams(self):
        text = patch.HELP_TEXT
        self.assertIn("EXPERIMENTAL / UNWITNESSED", text)
        self.assertIn("Quick Game", text)
        self.assertIn("Practice and First Person Football", text)
        self.assertIn("created team is never touched", text)
        self.assertNotIn("\u2014", text + patch.UI_LABEL + patch.BUILD_CAPTION + (patch.__doc__ or ""))

    def test_registry_entry(self):
        registry = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json").read_text())
        entry = next(c for c in registry["capabilities"] if c["id"] == "nfl2k5.menus.historic_teams_quick_game")
        self.assertEqual(entry["backend"]["module"], "mod_editor/core/nfl2k5_historic_teams_quick_game.py")
        self.assertEqual(entry["selectors"]["fields"][0]["name"], KEY)
        self.assertEqual(entry["validation_command"], "python3 -m tests.mod_editor.test_nfl2k5_historic_teams_quick_game")


class ManifestModelWiringTests(unittest.TestCase):
    """Retail-free: the cave manifest model installs this owner in its dormant-owner probe and lists it."""

    def test_the_dormant_owner_probe_reserves_and_applies_the_owner(self):
        import ast
        import inspect
        from mod_editor.core import nfl2k5_cave_manifest as model
        source = inspect.getsource(model.build_manifest)
        self.assertIn("from . import nfl2k5_historic_teams_quick_game as historic_quick_game", source)
        self.assertIn("+ historic_quick_game.REQUESTS", source)                  # in the complete allocation union
        self.assertIn("final, _ = historic_quick_game.apply(final)", source)     # observed on the probe image
        self.assertIn("historic_teams_quick_game=False", source)                 # never twice: off in the probe build
        wrapped, owners = [], []
        for node in ast.walk(ast.parse(source)):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "modules"):
                wrapped += [ast.unparse(element) for comp in ast.walk(node) if isinstance(comp, ast.comprehension)
                            and isinstance(comp.iter, ast.Tuple) for element in comp.iter.elts]
            if isinstance(node, ast.Dict):
                owners += [ast.unparse(element) for key, value in zip(node.keys, node.values)
                           if isinstance(key, ast.Constant) and key.value == "extra_owners" for element in value.elts]
        self.assertIn("historic_quick_game", wrapped)      # its apply is wrapped, so the Recorder observes it
        self.assertIn("historic_quick_game.OWNER", owners)
        self.assertLess(source.index("final, _ = arena_growth.apply(final"),
                        source.index("final, _ = historic_quick_game.apply(final)"))


def _retail():
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes
    return retail_bytes()


class OwnerTests(unittest.TestCase):
    """The pinned USA retail default.xbe."""

    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.patched, cls.receipt = patch.apply(cls.retail)
        cls.code, cls.data = patch.allocations(cls.patched)

    def test_status_apply_and_replay(self):
        self.assertEqual(patch.status(self.retail), "retail")
        self.assertEqual(patch.status(self.patched), "applied")
        self.assertEqual(self.receipt["status"], "applied")
        again, receipt = patch.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)
        # Alone it takes the two-page layout: the code after the boot logo, the state on the data page.
        self.assertEqual((self.code["va"], self.data["va"]), (0x14BA2C0, 0x14BB000))

    def test_only_the_six_call_sites_change_in_retail_sections(self):
        image, retail = XbeImage(self.patched), XbeImage(self.retail)
        changed = []
        for section in retail.sections:
            size = min(section.size, section.raw_size)
            before, after = retail.read(section.start, size), image.read(section.start, size)
            changed += [section.start + i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        sites = {va + i for _label, va, before, _after in patch.sites(self.code["va"]) for i in range(len(before))}
        self.assertTrue(set(changed) <= sites)
        # The team iterator and filter are the retail bytes: Franchise and season lists do not change.
        for va, size in ((0x778C0, 0x117), (0x77090, 0xB8), (0xE2E50, 0xB4)):
            self.assertEqual(image.read(va, size), retail.read(va, size))
        for label, va, _before, after in patch.sites(self.code["va"]):
            self.assertEqual(image.read(va, 5), after, label)

    def test_every_call_site_and_the_owned_code_refuse_mixed_bytes(self):
        for label, va, before, _after in patch.sites(self.code["va"]):
            broken = reseal(self.patched, va, before)
            self.assertEqual(patch.status(broken), "foreign", label)
            with self.assertRaises(ValueError):
                patch.apply(broken)
        broken = reseal(self.patched, self.code["va"] + 7, b"\x90")
        self.assertEqual(patch.status(broken), "foreign")

    def test_a_foreign_prerequisite_refuses(self):
        # One byte of the flow mask jump table (a pinned guard) changed: refuse.
        broken = reseal(self.retail, 0x2C0D7C, b"\x00")
        self.assertEqual(patch.status(broken), "foreign")
        with self.assertRaises(ValueError):
            patch.apply(broken)

    def test_the_build_pass_composes_it_with_the_practice_squad_and_scale_out_owners(self):
        alone, receipt = tt._apply_all(self.retail, None, catch_slider=False, practice_squad=True,
                                       historic_teams_quick_game=True)
        self.assertEqual(patch.status(alone), "applied")
        self.assertEqual(tt.espn25_rosters_patch.xbe_status(alone), "applied")   # the release repair rides along
        self.assertEqual(receipt["historic_teams_quick_game_patch"]["status"], "applied")
        grown, _ = tt._apply_all(self.retail, None, catch_slider=False, practice_squad=True,
                                 historic_teams_quick_game=True, coin_defer=True, camera=True)
        self.assertEqual(patch.status(grown), "applied")
        self.assertTrue(space.is_scaleout(grown))
        code, data = patch.allocations(grown)
        self.assertEqual(code["size"], patch.CODE_SIZE)
        self.assertEqual(tt._grown_status_fields(grown)[KEY], "applied")
        with self.assertRaisesRegex(ValueError, "rebuild from a verified base"):
            tt._check_installed_runtime_settings(grown, {**{k: False for k in tt.R62_RUNTIME_KEYS},
                                                         "cpu_money_downs": "retail", "cpu_scrambles": "retail",
                                                         "accelerated_clock_minimum_seconds": 20,
                                                         "decided_clock_margin": 17, "decided_clock_seconds": 60,
                                                         "coin_defer": True, KEY: False})


class ManifestReservationTests(unittest.TestCase):
    """The manifest Recorder attributes every byte this owner writes and the cave oracle then refuses its sites."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        cls.retail = _retail()
        recorder = Recorder(cls.retail)
        allocated, receipt = space.apply(cls.retail, patch.REQUESTS)
        recorder.observe(space, "apply", cls.retail, allocated, receipt)
        cls.final = recorder.wrapper(patch, "apply")(allocated)[0]
        cls.rows = recorder.finish(cls.final)               # raises on any unattributed changed byte
        cls.code, cls.data = patch.allocations(cls.final)

    def test_every_call_site_and_both_allocations_are_reserved(self):
        declared = {(int(r["start"], 0), int(r["end"], 0), r["basis"]) for r in self.rows
                    if r["owner"] == patch.OWNER and r["basis"].startswith("declared edit: ")}
        self.assertEqual(declared, {(va, va + 5, "declared edit: " + label) for label, va, _pin, _entry in patch.HOOKS})
        for allocation in (self.code, self.data):
            self.assertTrue(any(r["owner"] == patch.OWNER and int(r["start"], 0) == allocation["va"]
                                and r["size"] == allocation["size"] for r in self.rows), allocation)

    def test_no_allocation_can_land_on_or_across_a_call_site(self):
        from mod_editor.core.nfl2k5_cave_oracle import (MANIFEST_SCHEMA, CaveOracle, OracleError,
                                                        ReservationManifest)
        document = {"schema": MANIFEST_SCHEMA, "retail_sha256": hashlib.sha256(self.retail).hexdigest(),
                    "complete": True, "spans": [r for r in self.rows if int(r["start"], 0) < space.CODE_VA]}
        oracle = CaveOracle(self.retail, manifest=ReservationManifest(document, XbeImage(self.retail)),
                            instruction_budget=1, reference_budget=1)
        for label, va, _pin, _entry in patch.HOOKS:
            for start, size in [(at, 1) for at in range(va, va + 5)] + [(va, 5), (va - 8, 16)]:
                with self.subTest(site=label, start=hex(start), size=size):
                    self.assertEqual(oracle.assess(start, size)["verdict"], "reserved")
                    with self.assertRaisesRegex(OracleError, "reserved"):
                        oracle.require_cave(start, size)


class NativeTeamSelectTests(unittest.TestCase):
    """The real Team Select handlers on retail + practice squad + release repair + this option."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import XBE
        retail = _retail()
        if not (XBE.parent / "vc_53450030/0").is_file():
            raise unittest.SkipTest("private retail roster archive is absent")
        from mod_editor.core import nfl2k5_espn25_rosters as rosters, nfl2k5_practice_squad as ps
        from nfl2k5_historic_quick_game_native import disc_evidence
        payload, _ = ps.apply(retail)
        payload, _ = rosters.apply_xbe(payload)
        cls.payload, _ = patch.apply(payload)
        cls.evidence = disc_evidence(XBE.parent)
        cls.names = [d["filename"] for d in cls.evidence[1]["descriptors"]]

    def cpu(self):
        from nfl2k5_historic_quick_game_native import TeamSelectCPU
        return TeamSelectCPU(self.payload, *self.evidence)

    def test_home_steps_into_the_list_through_twelve_entries_and_back_out(self):
        cpu = self.cpu()
        user1, _user2 = cpu.spare_slots()[:2]
        last = cpu.last_resident()
        start = cpu.pool()["used"]
        cpu.team_select(last, cpu.team(15))
        forward = [cpu.press("home", +1) for _ in range(12)]
        back = [cpu.press("home", -1) for _ in range(12)]
        self.assertEqual([s["loaded"] for s in forward], [[name] for name in self.names[:12]])
        self.assertEqual([s["loaded"] for s in back[:11]], [[name] for name in self.names[10::-1]])
        for step in forward + back[:11]:
            self.assertEqual(step["home"]["index"], cpu.index(user1))
            self.assertEqual((step["home"]["category"], step["home"]["players"]), (4, 53))
            self.assertEqual(step["pool"]["used"], start + 53)       # cleared before every import: no leak
        out = back[11]
        self.assertEqual((out["home"]["index"], out["loaded"]), (cpu.index(last), []))
        self.assertEqual(out["pool"]["used"], start)                 # leaving the list returns the players
        self.assertEqual(cpu.view(user1)["category"], 2)
        self.assertEqual(cpu.view(user1)["identity"], 90)
        self.assertEqual(cpu.import_body, 0x374114)                  # the practice squad's ps_import ran
        self.assertEqual(cpu.import_runs, 23)

    def test_both_directions_wrap_through_the_list_to_the_first_nfl_team(self):
        cpu = self.cpu()
        cpu.team_select(cpu.team(0), cpu.team(15))
        back = cpu.press("home", -1)
        self.assertEqual(back["loaded"], [self.names[-1]])
        forward = cpu.press("home", +1)
        self.assertEqual((forward["home"]["index"], forward["loaded"]), (0, []))

    def test_the_away_side_uses_user2_and_home_never_offers_it(self):
        cpu = self.cpu()
        user1, user2 = cpu.spare_slots()[:2]
        cpu.team_select(cpu.team(21), cpu.last_resident())
        away = cpu.press("away", +1)
        self.assertEqual((away["away"]["index"], away["loaded"]), (cpu.index(user2), [self.names[0]]))
        seen = [cpu.press("home", +1) for _ in range(60)]
        self.assertNotIn(cpu.index(user2), [s["home"]["index"] for s in seen])
        self.assertIn(cpu.index(user1), [s["home"]["index"] for s in seen])
        self.assertEqual(cpu.pool()["used"], 106)

    def test_a_created_team_is_never_touched_and_that_side_skips_the_list(self):
        cpu = self.cpu()
        user1, user2 = cpu.spare_slots()[:2]
        resources, context, _ids = self.evidence
        cpu.write(0x2200000, resources[context["descriptors"][5]["outer"]][32:])
        self.assertEqual(cpu.run(0xC1030, ecx=0x2200040, edx=user1), 1)
        cpu.write(user1 + 0x128, struct.pack("<I", 2))                # what Create a Team's teams carry
        cpu.write(user1 + 0x118, struct.pack("<H", 90))
        before = hashlib.sha256(cpu.read(user1, 500) + b"".join(
            cpu.read(cpu.r(user1 + 4 * i), 84) for i in range(53))).hexdigest()
        cpu.team_select(cpu.last_resident(), cpu.team(15))
        wrap = cpu.press("home", +1)
        self.assertEqual((wrap["home"]["index"], wrap["loaded"]), (0, []))
        lap = [cpu.press("home", +1) for _ in range(55)]
        self.assertFalse(any(s["loaded"] for s in lap))
        self.assertIn(cpu.index(user1), [s["home"]["index"] for s in lap])   # still offered, as retail
        cpu.team_select(cpu.team(21), cpu.last_resident())
        self.assertEqual(cpu.press("away", +1)["away"]["index"], cpu.index(user2))
        after = hashlib.sha256(cpu.read(user1, 500) + b"".join(
            cpu.read(cpu.r(user1 + 4 * i), 84) for i in range(53))).hexdigest()
        self.assertEqual(after, before)

    def test_other_team_select_flows_keep_the_retail_steps(self):
        from unicorn import UC_HOOK_CODE
        for flow in (4, 6, 8, 9):
            cpu = self.cpu()
            cpu.team_select(cpu.last_resident(), cpu.team(15), flow=flow)
            delegated = []
            target = patch.SYMBOLS['retail_home_next']
            def retail():
                delegated.append(cpu.reg('edx'))
                cpu.ret(0)
            cpu.BOUNDARIES = cpu.BOUNDARIES | {target}
            cpu.stubs[target] = retail
            cpu.uc.hook_add(UC_HOOK_CODE, cpu._hook, begin=target, end=target)
            code, _ = patch.allocations(self.payload)
            cpu.run(code['va'] + patch.assembly.LABELS['home_next'], edx=0x19)
            self.assertEqual(delegated, [0x19], flow)
            self.assertFalse(cpu.queued, flow)

    def test_practice_and_first_person_import_both_historic_sides(self):
        for flow in (3, 7):
            cpu = self.cpu()
            cpu.team_select(cpu.team(0), cpu.team(15), flow=flow)
            # Walk backward from the first resident. The real flow mask chooses
            # the end of its own list; no Quick Game-only Alumni assumption.
            home = cpu.press('home', -1)
            self.assertEqual(home['loaded'], [self.names[-1]], flow)
            cpu.team_select(cpu.r(0xACF63C), cpu.team(0), flow=flow)
            away = cpu.press('away', -1)
            self.assertEqual(away['loaded'], [self.names[-1]], flow)
            self.assertEqual((away['home']['players'], away['away']['players']), (53, 53))
            self.assertEqual(cpu.pool()['used'], 106)
            for draw in (0, 20, 100):
                self.assertEqual(cpu.random_step('home', draw)['loaded'], [])

    def test_a_network_session_keeps_the_retail_list(self):
        cpu = self.cpu()
        cpu.w(0xBB7F4C, 1)                                             # 128C70 reads it: Live or system link
        cpu.team_select(cpu.last_resident(), cpu.team(15))
        step = cpu.press("home", +1)
        self.assertEqual((step["home"]["index"], step["loaded"]), (0, []))
        back = cpu.press("home", -1)
        self.assertEqual((back["home"]["index"], back["loaded"]), (cpu.index(cpu.last_resident()), []))

    def test_the_random_spin_stays_on_the_resident_teams(self):
        cpu = self.cpu()
        cpu.team_select(cpu.last_resident(), cpu.team(0))
        cpu.press("home", +1)
        cpu.press("away", -1)
        for draw in range(0, 140, 7):
            home = cpu.random_step("home", draw)
            away = cpu.random_step("away", draw + 3)
            self.assertNotEqual(home["home"]["category"], 4)
            self.assertNotEqual(away["away"]["category"], 4)
            self.assertFalse(home["loaded"] or away["loaded"])

    def test_moment_quit_quick_game_historic_teams_then_a_moment_again(self):
        cpu = self.cpu()
        before = len(cpu.imports)
        cpu.select(0)                                                  # THE ICE BOWL
        self.assertEqual([i.get("result") for i in cpu.imports[before:]], [1, 1])
        self.assertEqual(cpu.match()["export_players"], 106)
        cpu.run(0x20C3C0)                                              # quit: the details screen's exit event
        cpu.team_select(cpu.last_resident(), cpu.team(15))
        for _ in range(6):
            home = cpu.press("home", +1)                               # entry 5, the '85 Bears
        cpu.team_select(cpu.r(0xACF63C), cpu.team(0))
        away = cpu.press("away", -1)                                   # the last entry
        self.assertEqual(home["loaded"], ["h-05-1985-bears-1.iff"])
        self.assertEqual(away["loaded"], [self.names[-1]])
        match = cpu.match()
        self.assertEqual(match["export_players"], 106)
        self.assertEqual(match["sides"]["home"]["kit"], "05h1.iff")
        before = len(cpu.imports)
        cpu.select(14)                                                 # WIDE RIGHT, over the Quick Game teams
        self.assertEqual([i.get("result") for i in cpu.imports[before:]], [1, 1])
        selected = cpu.selected()
        self.assertNotEqual(selected["home"]["team"], selected["away"]["team"])
        self.assertEqual(cpu.match()["export_players"], 106)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

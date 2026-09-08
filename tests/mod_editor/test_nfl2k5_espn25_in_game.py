"""Standalone regression of the bn re-entry bug and the paired native repair."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / "tools", ROOT / "tests"):
    sys.path.insert(0, str(directory))
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_bump_strength as strength
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_espn25_rosters import RETAIL
import nfl2k5_espn25_exact_lineups as exact
try:
    from nfl2k5_espn25_in_game import LiveCPU, evidence, BN_IMAGE, BN_XBE_SHA256, BN_CONTEXT, XBE_SHA256
    NATIVE_ERROR = None
except ImportError as exc:
    NATIVE_ERROR = str(exc)


class PublicationTests(unittest.TestCase):
    def test_unresolved_freeze_blocks_every_build_entry_before_io_or_compilation(self):
        self.assertIn("Wide Right", e.BUILD_BLOCK_REASON)
        with patch.object(e, "_compile_resources", side_effect=AssertionError("must not compile")), \
                patch.object(e, "read_resources", side_effect=AssertionError("must not read")):
            for call in (lambda: e.apply({}), lambda: e.apply_resources({}),
                         lambda: e.apply_to_image("absent.iso"), lambda: e.preflight_image("absent.iso"),
                         lambda: e.build_image("absent.iso", "also-absent.iso")):
                with self.subTest(entry=call), self.assertRaisesRegex(e.Espn25RostersError, "Wide Right"):
                    call()

    def test_actual_build_plan_refuses_bn_style_and_full_experimental_before_copy(self):
        from mod_editor.core import mod_build as build, nfl2k5_throw_tuning as tuning
        from mod_editor.core import nfl2k5_scorebug_ingame as scorebar
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "source.iso", Path(folder) / "result.iso"
            source.write_bytes(b"synthetic preflight boundary")
            preset = build.apply_preset(build.BuildPlan(str(source), str(target)), "softdrink_experimental")
            full = replace(preset, espn25_rosters=True)
            bn = replace(full, position_pools=False, position_pools_keep_olb=False, depth_roles=False,
                         edge_rename=False, depth_chart_rows=False)
            with patch.object(tuning, "is_disc_image", return_value=True), \
                    patch.object(tuning, "_naming_source_preflight", return_value=None), \
                    patch.object(scorebar, "image_plan", return_value={}), \
                    patch.object(tuning, "write_copy", side_effect=AssertionError("must not copy")), \
                    patch.object(build.shutil, "copyfile", side_effect=AssertionError("must not copy")), \
                    patch.object(e, "read_resources", return_value={}):
                for plan, message in ((bn, "Wide Right"), (full, "retail position layout")):
                    with self.subTest(configuration=message), self.assertRaisesRegex(ValueError, message):
                        build.build(plan)
            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), b"synthetic preflight boundary")
            self.assertFalse(list(Path(folder).glob(".studio-build-*")))


class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RETAIL / "default.xbe").is_file():
            raise unittest.SkipTest("user-owned USA default.xbe evidence absent")
        cls.retail = e.read_bounded(RETAIL / "default.xbe", 16 * 1024**2)
        if e.sha(cls.retail) != "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9":
            raise unittest.SkipTest("USA default.xbe evidence pin differs")

    def test_exact_in_place_patch_idempotence_digests_and_foreign_refusal(self):
        output, receipt = e.apply_xbe(self.retail)
        self.assertEqual(e.xbe_status(output), "applied")
        self.assertEqual(e.apply_xbe(output)[0], output)
        self.assertEqual(e.apply_xbe(output)[1]["changed_bytes"], 0)
        self.assertEqual(len(output), len(self.retail))
        self.assertEqual(e.REQUESTS, ())
        image = XbeImage(output)
        start = image.offset(e.XBE_SITE_VA, 12)
        allowed = set(range(start, start + 12))
        for section in strength._sections(output):
            self.assertEqual(strength.section_digest(output, section), section.stored_digest)
            allowed.update(range(section.header_offset + 36, section.header_offset + 56))
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(self.retail, output)) if a != b))
        self.assertEqual(len(receipt["edits"]), 1)
        for original in (self.retail, output):
            for va in (e.XBE_SITE_VA, e.XBE_SITE_VA + 11, 0xC2300, 0xC2314, 0xC2403, 0xBFF93):
                bad = bytearray(original)
                bad[image.offset(va, 1)] ^= 0x40
                before = bytes(bad)
                self.assertEqual(e.xbe_status(bad), "foreign")
                with self.assertRaises(e.Espn25RostersError):
                    e.apply_xbe(bad)
                self.assertEqual(bytes(bad), before)
        for n in (0, 4, 0x120, 0x10000):
            self.assertEqual(e.xbe_status(output[:n]), "foreign")

    def test_practice_squad_composes_before_and_after_the_repair(self):
        from mod_editor.core import nfl2k5_practice_squad as ps
        first = ps.apply(e.apply_xbe(self.retail)[0])[0]
        last = e.apply_xbe(ps.apply(self.retail)[0])[0]
        self.assertEqual(first, last)
        self.assertEqual(ps.status(first), "applied")
        self.assertEqual(e.xbe_status(first), "applied")


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if NATIVE_ERROR:
            raise unittest.SkipTest("Unicorn unavailable: " + NATIVE_ERROR)
        for path in (BN_IMAGE, RETAIL / "default.xbe", RETAIL / "vc_53450030/0"):
            if not path.is_file():
                raise unittest.SkipTest("private native evidence absent: " + str(path))
        cls.bn_xbe = e.read_xbe(BN_IMAGE)
        cls.retail_xbe = e.read_xbe(RETAIL)
        if e.sha(cls.bn_xbe) != BN_XBE_SHA256 or e.sha(cls.retail_xbe) != XBE_SHA256:
            raise unittest.SkipTest("bn or retail executable evidence pin differs")
        cls.resources, cls.context, cls.ids = evidence(BN_IMAGE)
        if any(e.sha(cls.resources[i]) != digest for i, digest in BN_CONTEXT.items()):
            raise unittest.SkipTest("bn main ROST or SITU evidence pin differs")
        cls.manifest, cls.sheets = e.dataset()
        cls.targets = {t["outer"]: t for t in cls.manifest["resources"]}
        if e.status({i: cls.resources[i] for i in cls.targets}) != "applied":
            raise unittest.SkipTest("bn historic resource pins differ from the exact-lineup dataset")

    def cpu(self, patched=True, retail=False):
        payload = self.retail_xbe if retail else self.bn_xbe
        if patched:
            payload = e.apply_xbe(payload)[0]
        return LiveCPU(payload, self.resources, self.context, self.ids)

    def test_reproduces_stale_team_reentry_and_the_import_refusal(self):
        cpu = self.cpu(False)
        cpu.select(0)
        first = cpu.match()
        self.assertEqual([first["sides"][s]["quarterback"]["last"] for s in ("home", "away")], ["Starr", "Meredith"])
        self.assertEqual([first["sides"][s]["quarterback"]["jersey"] for s in ("home", "away")], [15, 17])
        backups = {s: cpu.field_player(s, "QB", 0, assigned=(first["sides"][s]["quarterback"]["pointer"],))
                   for s in ("home", "away")}
        self.assertEqual([(backups[s]["last"], backups[s]["jersey"]) for s in ("home", "away")],
                         [("Bratkowski", 12), ("Morton", 14)])
        cpu.select(14)
        sides = cpu.selected()
        self.assertEqual([sides[s]["name"] for s in ("home", "away")], ["Cowboys '71"] * 2)
        self.assertEqual(sides["home"]["team"], sides["away"]["team"])
        self.assertEqual([r["result"] for r in cpu.imports], [1, 1, 0, 0])
        self.assertEqual([(r["active_after"], r["pointers_after"]) for r in cpu.releases], [(0, 53)])
        # The newly empty destination is exactly what reserve_count rejects.
        self.assertEqual(cpu.run(0x3D1E9C, eax=cpu.releases[-1]["team"]), 0xFFFFFFFF)
        aliased_match = cpu.match()
        self.assertEqual(aliased_match["export_players"], 106)
        self.assertTrue(all(s["kit_exists"] for s in aliased_match["sides"].values()))
        self.write_receipt("failure", {"imports": cpu.imports, "releases": cpu.releases,
            "fresh_ice_bowl": first, "wide_right_after_ice_bowl": sides,
            "backups_with_starters_explicitly_excluded": backups, "aliased_match": aliased_match,
            "load_music_loop_reproduced": False})

    def test_fixed_native_eviction_preserves_every_other_team_byte(self):
        # Same native input, with and without the twelve-byte loop replacement.
        before, after = self.cpu(False, True), self.cpu(True, True)
        for cpu in (before, after):
            cpu.select(0)
            cpu.run(0xC2300, ecx=cpu.run(0x77B00))
        team = before.releases[-1]["team"]
        old, new = before.read(team, 500), after.read(team, 500)
        self.assertEqual(old[53 * 4:], new[53 * 4:])
        self.assertNotEqual(old[:53 * 4], bytes(53 * 4))
        self.assertEqual(new[:65 * 4], bytes(65 * 4))
        self.assertEqual(before.read(before.MAIN + 0x9000, 0x70000), after.read(after.MAIN + 0x9000, 0x70000))

    def test_all_25_bn_moments_in_one_arena_with_native_starters_names_kits_and_export(self):
        cpu = self.cpu()
        results = []
        for index in (*range(25), 0, 14, 0):
            with self.subTest(moment=index):
                event_start = len(cpu.events)
                cpu.select(index)
                moment = self.manifest["moments"][index]
                self.assertEqual([x["outer"] for x in cpu.events[event_start:]],
                                 [moment["sides"][s]["outer"] for s in ("home", "away")])
                self.assertEqual([r["result"] for r in cpu.imports[-2:]], [1, 1])
                result = cpu.match()
                self.assertNotEqual(result["sides"]["home"]["team"], result["sides"]["away"]["team"])
                self.assertTrue(result["export_root"])
                self.assertEqual(result["export_players"], 106)
                for side in ("home", "away"):
                    info = result["sides"][side]
                    self.assertTrue(info["kit_exists"], info["kit"])
                    bound = moment["sides"][side]
                    doc = rr.RosterDocument(self.resources[bound["outer"]][32:])
                    self.assertEqual(info["name"], doc.teams[0].nickname)
                    self.assertEqual(info["quarterback"], cpu.role_player(side, "QB", 0))
                    for i, source in enumerate(doc.team_players(0)):
                        p = cpu.person(cpu.r(info["match_team"] + 4 * i))
                        self.assertEqual((p["first"], p["last"], p["jersey"], p["position"]),
                                         (source.first, source.last, source.record.values["jersey"], source.record.position_name))
                    checks = []
                    rows = self.sheets[bound["outer"]]
                    for starter in bound["starters"]:
                        resolved = False
                        if starter["present"]:
                            row = rows[starter["slot"]]
                            pos = row["position"]
                            if pos in exact.positions(starter["position"], starter=True):
                                same_role = sum(pos in exact.positions(s["position"], starter=True) for s in bound["starters"])
                                if pos in exact.PAIRED:
                                    limit = (same_role + 1) // 2
                                    parity = (0,) if starter["position"] in exact.LEFT else (1,) if starter["position"] in exact.RIGHT else (0, 1)
                                    ordinals = [2 * i + p for i in range(limit) for p in parity]
                                else:
                                    ordinals = range(same_role)
                                for ordinal in ordinals:
                                    selected = cpu.role_player(side, pos, ordinal)
                                    if selected:
                                        self.assertEqual(selected, cpu.field_player(side, pos, ordinal),
                                                         (index, side, pos, ordinal))
                                    resolved |= bool(selected and (selected["first"], selected["last"]) == (row["first"], row["last"]))
                        self.assertEqual(resolved, starter["at_starting_depth"], (index, side, starter["name"]))
                        checks.append({"name": starter["name"], "native_starting_depth": resolved})
                    info["starters"] = checks
                    info["boxscore_quarterback"] = next(s["name"] for s in bound["starters"] if s["position"] == "QB")
                result.update(moment=index, title=moment["title"])
                results.append(result)
        self.assertEqual(len(results), 28, "failed subtests must not publish a partial success receipt")
        self.assertTrue(all(r["pointers_after"] == 0 for r in cpu.releases))
        self.write_receipt("bn_fixed", {"moments": results, "imports": cpu.imports, "releases": cpu.releases})

    @staticmethod
    def write_receipt(name, result):
        destination = os.environ.get("ESPN25_IN_GAME_RECEIPTS")
        if destination:
            folder = Path(destination).resolve()
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (name + ".json")).write_text(json.dumps({"evidence": e.EVIDENCE,
                "bn_xbe_sha256": BN_XBE_SHA256, "dataset_sha256": e.DATASET_SHA256,
                "instruction_budget_per_call": 40000000, "gameplay_witnessed": False,
                **result}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

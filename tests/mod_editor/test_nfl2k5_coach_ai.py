"""Automatic-coach build contract and foreign/stale-resource refusal.

Private native assets are opt-in; none are included in the repository.
"""
from pathlib import Path
import hashlib
import json
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_coach_ai as ai
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_vip as vip
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES


class BuildContract(unittest.TestCase):
    def test_release_preset_enabled_and_opt_out_roundtrips(self):
        from mod_editor.core.mod_build import PRESETS, BuildPlan, _validated_r62_plan_options
        self.assertFalse(settings.defaults()["coach_ai"])
        self.assertTrue(settings.build_settings({"coach_ai": True})["coach_ai"])
        self.assertTrue(PRESETS["softdrink_experimental"]["coach_ai"])
        self.assertFalse(PRESETS["softdrink_basic"]["coach_ai"])
        self.assertFalse(PRESETS["softdrink_advanced"]["coach_ai"])
        enabled = {key: value for key, value in PRESETS["softdrink_experimental"].items()
                   if key in settings.FEATURE_KEYS}
        self.assertTrue(settings.build_settings(enabled)["coach_ai"])
        opted_out = settings.build_settings({**enabled, "coach_ai": False})
        self.assertFalse(settings.build_settings(json.loads(json.dumps(opted_out)))["coach_ai"])
        with self.assertRaises(ValueError):
            settings.build_settings({"coach_ai": 1})
        plan = BuildPlan("source.xiso.iso", "new.xiso.iso", coach_ai=True)
        self.assertTrue(plan.wants_xbe_patch())
        self.assertEqual(_validated_r62_plan_options(plan)["cpu_money_downs"], "modern2")

    def test_compaction_retains_compiler_inputs_and_provenance(self):
        value = json.loads((ROOT / "data/vip/coaches/NYG.json").read_text())
        full = dict(value, situations=[{"unused": 42}], fourth_down_situations=[1])
        compact = ai.compact_tendency(full)
        self.assertNotIn("situations", compact)
        self.assertNotIn("fourth_down_situations", compact)
        self.assertEqual(ai.compact_tendency(compact), compact)
        for key in ("native_offense_pools", "native_statistics", "native_decision_projections",
                    "overall", "defense", "provenance", "sources"):
            self.assertEqual(compact[key], full[key])

    def test_all_team_portrait_identities_are_unique_and_bounded(self):
        rows = ai.portrait_rows()
        self.assertEqual(len(rows), 32)
        self.assertEqual(len({r["legacy_identity"] for r in rows}), 32)
        self.assertEqual(len({r["identity"] for r in rows}), 32)
        for row in rows:
            self.assertLessEqual(len(row["name"].encode("utf-16le")), 24)
            self.assertEqual(row["identity"], vip.coach_identity(row["team"], row["name"]))
        self.assertEqual({r["team"]: r["alternate_portrait"] for r in rows if "alternate_portrait" in r},
                         {"DAL": 7031, "WAS": 7034})


class PrivateResources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get("NFL2K5_COACH_AI_IMAGE")
        if not path:
            raise unittest.SkipTest("Set NFL2K5_COACH_AI_IMAGE for compiled-resource checks")
        with OuterImage(path) as archive:
            cls.book = archive.read_entry(BOOK_ENTRIES["NYG"])
            cls.roster = archive.read_entry(5)
        cls.target = json.loads((ROOT / "data/vip/coaches/NYG.json").read_text())
        cls.tagged, cls.receipt = ai.build_profile(cls.book, cls.target)

    def test_exact_fixed_span_idempotence_and_packed_history(self):
        tagged, receipt = self.tagged, self.receipt
        lo = 32 + ai.PROFILE_OFFSET
        self.assertEqual(len(tagged), len(self.book))
        self.assertEqual(tagged[:lo], self.book[:lo])
        self.assertEqual(tagged[lo + ai.PROFILE_SIZE:], self.book[lo + ai.PROFILE_SIZE:])
        info = ai.inspect_profile(tagged)
        self.assertEqual(info["book_sha256"], hashlib.sha256(self.book).hexdigest())
        self.assertEqual(info["book_index"], 15)
        self.assertEqual(ai.build_profile(tagged, self.target)[0], tagged)
        payload = ai.expand_profile(tagged)
        self.assertEqual(payload[0x3C:0xA3C], bytes.fromhex(receipt["context_offense_hex"]))
        self.assertEqual(payload[0xA3C:0xDDE], bytes.fromhex(receipt["context_defense_hex"]))
        self.assertEqual(payload[0xE90:0xE98], bytes.fromhex(receipt["decision_counts_hex"]))

    def test_foreign_tail_and_stale_book_are_refused(self):
        lo = 32 + ai.PROFILE_OFFSET
        foreign = bytearray(self.book)
        foreign[lo + 67] = 1
        with self.assertRaises(ai.CoachAIError):
            ai.build_profile(bytes(foreign), self.target)
        for offset in (32 + 0x3400, lo + 11, lo + 128 + 7):
            stale = bytearray(self.tagged)
            stale[offset] ^= 1
            with self.assertRaises(ai.CoachAIError):
                ai.inspect_profile(bytes(stale))
            with self.assertRaises(ai.CoachAIError):
                ai.build_profile(bytes(stale), self.target)

    def test_declared_strings_must_leave_reserved_tail_unused(self):
        foreign = bytearray(self.book)
        struct.pack_into("<I", foreign, 32 + 0x1083C, (ai.PROFILE_OFFSET - 0x10840) // 2 + 1)
        with self.assertRaises(ai.CoachAIError):
            ai.build_profile(bytes(foreign), self.target)

    def test_overall_counts_keep_the_source_ratio_below_independent_decay(self):
        context = ai.expand_profile(self.tagged)
        passed, run = struct.unpack_from("<HH", context, 0x20B8)
        self.assertLessEqual(max(passed, run), 253)
        raw = self.target["native_statistics"]
        self.assertAlmostEqual(passed / (passed + run),
                               raw["pass_calls"] / (raw["pass_calls"] + raw["run_calls"]), delta=.003)

    def test_wrong_roster_coach_refuses_before_any_book_is_compiled(self):
        from unittest.mock import patch
        from mod_editor.core import nfl2k5_roster_records as rr, nfl2k5_playbook_pack as packs
        raw = bytearray(self.roster)
        roster = rr.RosterDocument(raw[32:])
        names = rr._coach_tool()
        at = names.relative_target(roster.body, roster.teams[0].coach_offset, "first coach")
        raw[32 + at:32 + at + 2] = b"X\0"
        calls = []
        class Archive:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def read_entry(self, index):
                calls.append(index)
                if index != 5:
                    raise AssertionError("Read a playbook before rejecting the wrong coach")
                return bytes(raw)
        with patch.object(packs._outer_image(), "OuterImage", return_value=Archive()):
            with self.assertRaisesRegex(ai.CoachAIError, "roster coach"):
                ai.plan_profiles("bounded roster fixture")
        self.assertEqual(calls, [5])

    def test_co1_portrait_aliases_keep_the_exact_same_profile_payloads(self):
        from unittest.mock import patch
        from mod_editor.core import nfl2k5_roster_records as rr, nfl2k5_playbook_pack as packs
        raw = bytearray(self.roster)
        roster = rr.RosterDocument(raw[32:])
        for row in ai.portrait_rows():
            if "alternate_portrait" in row:
                at = 32 + roster.teams[row["book_index"]].coach_offset + 0x40
                struct.pack_into("<H", raw, at, row["alternate_portrait"])
        with OuterImage(os.environ["NFL2K5_COACH_AI_IMAGE"]) as source:
            class Archive:
                def __enter__(self):
                    return self
                def __exit__(self, *_):
                    pass
                def read_entry(self, index):
                    return bytes(raw) if index == 5 else source.read_entry(index)
            with patch.object(packs._outer_image(), "OuterImage", return_value=Archive()):
                prepared = ai.plan_profiles("bounded co1 roster fixture")
        selected = {r[3]["team"]: r for r in prepared if r[3]["team"] in ("DAL", "WAS")}
        for team, photo in (("DAL", 7031), ("WAS", 7034)):
            _, before, after, receipt = selected[team]
            target = json.loads((ROOT / f"data/vip/coaches/{team}.json").read_text())
            self.assertEqual(after, ai.build_profile(before, target)[0])
            self.assertEqual(receipt["roster_portrait"], photo)


class NativeInstallation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("NFL2K5_COACH_AI_XBE")
        if not source:
            raise unittest.SkipTest("Set NFL2K5_COACH_AI_XBE to the private VIP-aware v0.6.1 XBE")
        cls.source = Path(source).read_bytes()
        cls.patched, cls.receipt = ai.apply(cls.source)

    def test_controller_rebind_waits_for_native_ownership_refresh(self):
        image = os.environ.get("NFL2K5_COACH_AI_IMAGE")
        if not image:
            self.skipTest("Set NFL2K5_COACH_AI_IMAGE for controller transition checks")
        from tools.b77.vp2_native import audit_lifecycle
        from mod_editor.core import nfl2k5_roster_records as rr
        with OuterImage(image) as archive:
            raw = archive.read_entry(BOOK_ENTRIES["DAL"])
            roster = rr.RosterDocument(archive.read_entry(5)[32:])
        target = json.loads((ROOT / "data/vip/coaches/DAL.json").read_text())
        tagged, receipt = ai.build_profile(raw, target)
        at = roster.teams[receipt["book_index"]].coach_offset
        result = audit_lifecycle(self.patched, tagged, receipt, roster.body[at:at + 0xA8])
        self.assertTrue(result["passed"])
        self.assertTrue(result["humans_cleared"])
        self.assertTrue(result["cpu_rebound"])
        self.assertTrue(result["explicit_choice_survived"])

    def test_disc_resource_callback_validates_before_relocation(self):
        image = os.environ.get("NFL2K5_COACH_AI_IMAGE")
        if not image:
            self.skipTest("Set NFL2K5_COACH_AI_IMAGE for native resource loading")
        from tools.b77.vp2_native import AutoWorld
        from mod_editor.core import nfl2k5_play_scoring as scoring
        with OuterImage(image) as archive:
            raw = archive.read_entry(BOOK_ENTRIES["PHI"])
        target = json.loads((ROOT / "data/vip/coaches/PHI.json").read_text())
        tagged, _ = ai.build_profile(raw, target)
        for route in ("resource", "copy"):
            with self.subTest(route=route):
                world = AutoWorld(self.patched, load_route=route)
                world.load(tagged)
                self.assertEqual(world.get(scoring.BOOK + ai.PROFILE_OFFSET + 28), 0x314B4F43,
                                 world.loader_witness)
                # A changed play byte must stay unvalidated on both paths.
                stale = bytearray(tagged)
                stale[32 + 0x3400] ^= 1
                world = AutoWorld(self.patched, load_route=route)
                world.load(bytes(stale))
                self.assertEqual(world.get(scoring.BOOK + ai.PROFILE_OFFSET + 28), 0)

    def test_fixed_size_seals_permissions_and_replay(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(ai.status(self.patched), "applied")
        self.assertEqual(space.status(self.patched), "applied")
        self.assertEqual(ai.apply(self.patched)[0], self.patched)
        self.assertTrue(all(r in space.layout(self.patched)["allocations"] for r in space.layout(self.source)["allocations"]))
        owned = ai.allocations(self.patched)
        image = XbeImage(self.patched)
        self.assertFalse(image.runtime_writable(owned["code"]["va"], ai.CODE_SIZE))
        self.assertTrue(image.runtime_writable(owned["data"]["va"], ai.DATA_SIZE))

    def test_foreign_prerequisite_and_mixed_hooks_refuse_after_valid_reseal(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        for address, before in ((0xF7B31, None), (0x1569C1, None), (0xF6E9D, bytes.fromhex(ai.HOOKS[1][2])),
                                (ai.allocations(self.patched)["code"]["va"] + 200, None)):
            payload = bytearray(self.patched)
            offset = XbeImage(payload).offset(address, len(before) if before else 1)
            if before:
                payload[offset:offset + len(before)] = before
            else:
                payload[offset] ^= 1
            space._seal_scaleout(payload, space._read_scale_directory(self.patched))
            for section in _sections(payload):
                payload[section.header_offset + 36:section.header_offset + 56] = section_digest(payload, section)
            self.assertEqual(space.status(bytes(payload)), "applied")
            self.assertEqual(ai.status(bytes(payload)), "foreign")
            with self.assertRaises(ai.CoachAIError):
                ai.apply(bytes(payload))

    def test_full_union_preserves_every_preexisting_owner_address(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        requests = space.dormant_union()
        old = space._scale_allocations([r for r in requests if r[0] != ai.OWNER])
        new = space._scale_allocations(requests)
        self.assertTrue(all(r in new for r in old))
        self.assertEqual(len([r for r in new if r["owner"] == ai.OWNER]), 2)

    def test_native_repair_includes_policy_and_is_idempotent(self):
        from tools.b77.vp2_repair import repair_xbe
        result, report = repair_xbe(self.source, approved=[hashlib.sha256(self.source).hexdigest()])
        self.assertEqual(result, self.patched)
        self.assertTrue(report["idempotent"])
        self.assertEqual(repair_xbe(result)[0], result)

    def test_manifest_records_all_hooks_and_zero_initialized_capacity(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.source)
        recorder.observe(ai, "apply", self.source, self.patched, self.receipt)
        spans = recorder.finish(self.patched)
        owned = [r for r in spans if r["owner"] == ai.OWNER]
        expected = [(va, len(bytes.fromhex(pin))) for _, va, pin, _ in ai.HOOKS]
        expected += [(row["va"], row["size"]) for row in ai.allocations(self.patched).values()]
        for address, size in expected:
            self.assertTrue(any(int(r["start"], 0) <= address and
                                int(r["end"], 0) >= address + size for r in owned), hex(address))


class NativeComposition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("NFL2K5_COACH_AI_RETAIL_XBE")
        if not source:
            raise unittest.SkipTest("Set NFL2K5_COACH_AI_RETAIL_XBE for native composition checks")
        cls.retail = Path(source).read_bytes()

    def test_shared_loader_and_unload_neighbors_compose_in_both_orders(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core import nfl2k5_cpu_money_downs as money
        from mod_editor.core import nfl2k5_playbook_pair as pair
        from mod_editor.core import nfl2k5_screen_hooks as screen
        from mod_editor.core import nfl2k5_qb_spy_runtime as spy
        from mod_editor.core import nfl2k5_read_option_runtime as read
        owners = (ai, pair, screen, spy, read)
        requests = money.REQUESTS + tuple(r for owner in owners for r in owner.REQUESTS)
        base = space.apply(self.retail, requests, scaleout=True)[0]
        base = money.apply(base, level="modern2")[0]
        results = []
        for order in (owners, tuple(reversed(owners))):
            result = base
            for owner in order:
                result = owner.apply(result)[0]
            for owner in owners:
                self.assertEqual(owner.status(result), "applied", owner.OWNER)
                self.assertEqual(owner.apply(result)[0], result, owner.OWNER)
            results.append(result)
        self.assertEqual(results[0], results[1])

    def test_studio_native_dispatch_installs_required_modern2(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        from mod_editor.core import nfl2k5_cpu_money_downs as money
        result, receipt = tt._apply_all(self.retail, None, False, coach_ai=True)
        self.assertEqual(ai.status(result), "applied")
        self.assertEqual(money.read_settings(result)["level"], "modern2")
        self.assertIn("coach_ai_patch", receipt)


if __name__ == "__main__":
    unittest.main()

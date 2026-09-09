"""Standalone Senior Bowl host policy, codec, input, install and ownership checks."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_senior_bowl as bowl
from mod_editor.core import nfl2k5_senior_bowl_code as assembly
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from tests.nfl2k5_senior_bowl_fixture import prospects, event, XBE, SAVE_PATHS


class SquadTests(unittest.TestCase):
    def test_three_position_schemes_all_starters_and_specialists(self):
        for scheme in bowl.SCHEMES:
            teams = bowl.select_squads(prospects(scheme), scheme=scheme)
            self.assertEqual(list(map(len, teams)), [53, 53])
            self.assertEqual(len({p.index for t in teams for p in t}), 106)
            for team in teams:
                self.assertEqual(tuple(sum(p.position == pos for p in team) for pos in range(17)), bowl.quotas(scheme))
                for pos in (0, 1, 2, 3, 7, 8, 9, 12, 13, 14, 15, 16):
                    self.assertTrue(any(p.position == pos for p in team))

    def test_whole_pool_not_initial_window_and_repeatable_seed(self):
        rows = prospects(extras=5)
        a = bowl.select_squads(rows, seed=0xFFFFFFFF)
        self.assertEqual(a, bowl.select_squads(reversed(rows), seed=0xFFFFFFFF))
        self.assertNotEqual(a, bowl.select_squads(rows, seed=1))
        self.assertLess(max(p.index for team in a for p in team), 1937)

    def test_veterans_drafted_unallocated_and_all_owners_are_excluded(self):
        rows = list(prospects(extras=6))
        for pos in range(17):
            positions = [i for i, p in enumerate(rows) if p.position == pos]
            for at, flags, owned in ((positions[0], 4, False), (positions[1], 0x34, False),
                                     (positions[2], 0x10, False), (positions[3], 0x14, True)):
                rows[at] = replace(rows[at], flags=flags, owned=owned)
        selected = {p.index for team in bowl.select_squads(rows) for p in team}
        self.assertFalse(selected.intersection(p.index for p in rows if not p.eligible))

    def test_shortages_refuse_instead_of_filling_with_veterans(self):
        rows = tuple(p for p in prospects() if p.position != 2)
        with self.assertRaisesRegex(ValueError, "P: need 2, found 0"):
            bowl.select_squads(rows)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            bowl.select_squads(prospects() + prospects()[:1])
        with self.assertRaisesRegex(ValueError, "retired OLB"):
            bowl.select_squads(prospects(), scheme="one_pool")

    def test_bad_types_bounds_and_capacity(self):
        for kwargs in ({"index": -1}, {"index": 4096}, {"position": 17}, {"flags": True}, {"owned": 1}):
            with self.assertRaises(ValueError):
                bowl.current_class((replace(prospects()[0], **kwargs),))
        with self.assertRaisesRegex(ValueError, "512"):
            bowl.current_class(tuple(bowl.Prospect(i, 0, 0x14) for i in range(513)))
        for seed in (-1, True, 1.5, 1<<32):
            with self.assertRaises(ValueError):
                bowl.select_squads(prospects(), seed=seed)

    def test_fingerprint_is_order_independent_and_identity_sensitive(self):
        rows = prospects()
        self.assertEqual(bowl.class_fingerprint(rows), bowl.class_fingerprint(reversed(rows)))
        changed = (replace(rows[0], identity=b"recycled index"),) + rows[1:]
        self.assertNotEqual(bowl.class_fingerprint(rows), bowl.class_fingerprint(changed))
        changed = (replace(rows[0], name="Other name"),) + rows[1:]
        self.assertNotEqual(bowl.class_fingerprint(rows), bowl.class_fingerprint(changed))

    def test_kit_defaults_and_explicit_evidence_limits(self):
        self.assertEqual((bowl.Settings().away.package, bowl.Settings().home.package), ("50A0.IFF", "51H0.IFF"))
        for kit in (bowl.Kit(90, "H"), bowl.Kit(50, "H", 1), bowl.Kit(50, "X"), bowl.Kit(True, "H")):
            with self.assertRaises(ValueError):
                kit.validate()
        with self.assertRaises(ValueError):
            bowl.Settings(home=bowl.Kit(50, "A")).validate()


class EventTests(unittest.TestCase):
    def test_stage_preamble_day_one_exactly_once_without_time_mutation(self):
        e = event()
        for stage in (1, 2, 3):
            self.assertEqual(bowl.stage_preamble(e, year=7, stage=stage), (e, False))
        self.assertEqual(bowl.stage_preamble(e, year=7, stage=4), (e, True))
        terminal = bowl.skip_event(e)
        for stage in range(1, 10):
            again, gate = bowl.stage_preamble(terminal, year=7, stage=stage, class_hash=b"changed by draft")
            self.assertEqual(again, terminal)
            self.assertFalse(gate)
        with self.assertRaisesRegex(ValueError, "new season"):
            bowl.stage_preamble(e, year=8, stage=4)
        self.assertEqual(event(year=8).state, "pending")

    def test_legacy_mid_combine_skip_days_and_partial_hours(self):
        for days, untouched in ((3, True), (0, True), (4, False)):
            e = event(stage=4, days=days, untouched_hours=untouched)
            self.assertEqual(e.state, "skipped")
            self.assertEqual(e.lines, ())
            self.assertFalse(bowl.stage_preamble(e, year=7, stage=4, days=days, untouched_hours=untouched)[1])
        self.assertEqual(event(stage=5).state, "skipped")

    def test_codec_pending_completed_skipped_and_interrupted(self):
        for state in ("pending", "running", "complete", "skipped"):
            e = replace(event(), state=state)
            raw = e.to_bytes()
            self.assertEqual(len(raw), 16384)
            loaded = bowl.Event.from_bytes(raw, franchise_id=e.franchise_id, class_hash=e.class_hash, year=7)
            self.assertEqual(loaded, replace(e, state="pending") if state == "running" else e)
            self.assertEqual(bowl.Event.from_bytes(raw, recover=False), e)

    def test_foreign_identity_length_version_crc_and_repinned_corruption_refuse(self):
        e = event()
        for args in ({"franchise_id": b"x"*16}, {"class_hash": b"x"*32}, {"year": 8}):
            with self.assertRaises(ValueError):
                bowl.Event.from_bytes(e.to_bytes(), **args)
        for offset in (0, 4, 8, 12, 16, 20, 28, 80, 82, 84, 90, 216, 256+3, bowl.ROWS_OFFSET+3, bowl.ROWS_OFFSET+76, 16383):
            damaged = bytearray(e.to_bytes())
            damaged[offset] ^= 0x80
            if offset != 12:
                struct.pack_into("<I", damaged, 12, zlib.crc32(damaged[16:]))
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                bowl.Event.from_bytes(bytes(damaged))
        for value in (b"", e.to_bytes()[:-1], e.to_bytes()+b"0"):
            with self.assertRaises(ValueError):
                bowl.Event.from_bytes(value)

    def test_duplicate_missing_specialist_and_changed_seed_refuse(self):
        e = event()
        for broken in (replace(e, lines=e.lines[:-1]), replace(e, lines=(e.lines[1],) + e.lines[1:]),
                       replace(e, seed=999), replace(e, class_rows=e.class_rows[::-1])):
            with self.assertRaises(ValueError):
                broken.to_bytes()

    def test_saved_score_is_separate_and_nonparticipants_have_no_line(self):
        e = event()
        stats = [0] * len(bowl.PLAYER_STATS)
        stats[:5] = [20, 12, 144, 1, 0]
        row = replace(e.lines[0], stats=tuple(stats))
        # Synthetic captured-result fixture, never presented as retail sim output.
        e = replace(e, state="complete", lines=(row,)+e.lines[1:], quarters=(7, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                    totals=((7, 8, 144, 20, 164, 0, 0, 0, 600, 1, 0, 0), (0,)*12))
        loaded = bowl.Event.from_bytes(e.to_bytes())
        self.assertEqual(loaded.scouting_line(row.index)["pass_yards"], 144)
        self.assertIsNone(loaded.scouting_line(4095))
        self.assertIsNone(event().scouting_line(row.index))
        with self.assertRaises(ValueError):
            replace(e, state="pending").to_bytes()

    def test_no_fabricated_simulation_or_activation(self):
        e = event()
        before = e.to_bytes()
        with self.assertRaisesRegex(ValueError, "No game was simulated"):
            bowl.simulate(e)
        self.assertEqual(before, e.to_bytes())
        self.assertFalse(bowl.NATIVE_EVENT_AVAILABLE)

    def test_small_atomic_event_and_project_roundtrip_failure_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            e = event()
            path = Path(temp).resolve() / "event.sbn"
            receipt = bowl.save_event(path, e)
            self.assertFalse(receipt["native_save"])
            self.assertEqual(bowl.load_event(path), e)
            p = path.with_suffix(".2k5senior")
            bowl.atomic_write(p, bowl.project_bytes(e.settings, e.seed, "source.dat", e))
            self.assertEqual(bowl.read_project(p), (e.settings, e.seed, "source.dat", e))
            before = path.read_bytes()
            with patch.object(bowl.os, "replace", side_effect=OSError("injected replace failure")):
                with self.assertRaises(OSError):
                    bowl.save_event(path, bowl.skip_event(e))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(set(x.name for x in path.parent.iterdir()), {path.name, p.name})
            for name in ("SAVEGAME.DAT", "EXTRA", "default.xbe"):
                with self.assertRaises(ValueError):
                    bowl.atomic_write(path.with_name(name), b"bad")

    def test_project_duplicate_keys_unknown_settings_and_large_input_refuse(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "project.2k5senior"
            for value in (b'{"schema":0,"schema":1}', b" "*131073):
                p.write_bytes(value)
                with self.assertRaises(ValueError):
                    bowl.read_project(p)
        for value in ({}, {"scheme": "retail", "away": {}, "home": {}}, {**bowl.Settings().to_dict(), "enable": True}):
            with self.assertRaises(ValueError):
                bowl.Settings.from_dict(value)


class PublicTests(unittest.TestCase):
    def test_budget_fixture_and_union_match_actual_requests(self):
        requests = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([r for r in requests if r[0] == bowl.OWNER], [list(r) for r in bowl.REQUESTS])
        self.assertLess(len(assembly.CODE), bowl.CODE_SIZE)
        space.plan(requests)
        from tests.nfl2k5_allocator_stack import REQUESTS
        self.assertTrue(set(bowl.REQUESTS) <= set(REQUESTS))

    def test_foreign_payloads_refuse(self):
        for value in (b"", b"XBEH" + bytes(4092)):
            self.assertEqual(bowl.status(value), "foreign")
            with self.assertRaises(ValueError):
                bowl.apply(value)

    def test_capability_row_and_module_commands(self):
        from mod_editor.capabilities.validate_registry import validate_data
        registry = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json").read_text())
        row = json.loads((ROOT / "docs/mod_editor/nfl2k5_senior_bowl_capability.json").read_text())[0]
        if not any(r["id"] == row["id"] for r in registry["capabilities"]):  # merged in beta 62
            registry["capabilities"] = sorted(registry["capabilities"] + [row], key=lambda r: r["id"])
        validate_data(registry, check_files=False)
        for p in (row["backend"]["module"], *row["evidence"]):
            self.assertTrue((ROOT / p).is_file(), p)
        self.assertTrue(row["backend"]["command"].startswith("python3 -m mod_editor.core.nfl2k5_senior_bowl "))
        self.assertTrue(row["validation_command"].startswith("python3 -m "))
        self.assertFalse(row["gui"]["default_enabled"])

    def test_template_reproduction(self):
        from _gnu_elf32_as import gnu_elf32_as
        if not gnu_elf32_as():
            self.skipTest("template reproduction requires GNU i386 as producing ELF32")
        subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_senior_bowl_assemble.py"), "--check"], check=True)


@unittest.skipUnless(XBE.is_file(), "private pinned USA default.xbe extraction is absent")
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != bowl.RETAIL_SHA256:
            raise unittest.SkipTest("extraction is not the pinned USA retail XBE")
        cls.patched, cls.receipt = bowl.apply(cls.retail)
        cls.image = XbeImage(cls.patched)
        cls.allocs = bowl.allocations(cls.patched)

    def test_dormant_install_is_exact_replay_and_no_retail_hook(self):
        self.assertEqual(bowl.status(self.retail), "retail")
        self.assertEqual(bowl.status(self.patched), "applied")
        result, receipt = bowl.apply(self.patched)
        self.assertEqual(result, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(self.receipt["retail_hooks"], 0)
        self.assertFalse(self.receipt["native_event_available"])
        old = XbeImage(self.retail)
        text = old.section(0x11000)
        self.assertEqual(self.image.read(text.start, text.raw_size), old.read(text.start, text.raw_size))
        for s in _sections(self.patched):
            self.assertEqual(s.stored_digest, section_digest(self.patched, s))

    def test_owned_allocation_permissions_seals_and_dirty_state(self):
        code, data = self.allocs["code"], self.allocs["data"]
        self.assertFalse(self.image.runtime_writable(code["va"], code["size"]))
        self.assertTrue(self.image.runtime_writable(data["va"], data["size"]))
        self.assertEqual(self.image.read(data["va"], data["size"]), bytes(data["size"]))
        for va in (code["va"], data["va"], bowl.GUARDS[0][0]):
            changed = bytearray(self.patched)
            changed[self.image.offset(va, 1)] ^= 1
            for s in _sections(changed):
                changed[s.header_offset+36:s.header_offset+56] = section_digest(changed, s)
            before = bytes(changed)
            self.assertEqual(bowl.status(changed), "foreign")
            with self.assertRaises(ValueError):
                bowl.apply(changed)
            self.assertEqual(bytes(changed), before)

    def test_union_missing_owner_refuses_before_mutation(self):
        wrong = space.apply(self.retail, (("other", "code", 32, 16),), scaleout=True)[0]
        with self.assertRaisesRegex(ValueError, "union"):
            bowl.apply(wrong)

    def test_manifest_records_full_allocations_and_zero_hooks(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        recorder.observe(bowl, "apply", self.retail, self.patched, self.receipt)
        spans = recorder.finish(self.patched)
        for allocation in self.allocs.values():
            self.assertTrue(any(r["owner"] == bowl.OWNER and int(r["start"], 0) <= allocation["va"]
                                and int(r["end"], 0) >= allocation["va"]+allocation["size"] for r in spans))


class SaveEvidenceTests(unittest.TestCase):
    def test_all_three_signed_classes_and_source_unchanged(self):
        for source in SAVE_PATHS:
            if not source.is_file():
                self.skipTest(f"private signed franchise fixture absent: {source}")
        for source, expected in zip(SAVE_PATHS, (380, 380, 317)):
            with self.subTest(source=source):
                before = hashlib.sha256(source.read_bytes()).digest()
                document, players = bowl.read_franchise(source)
                self.assertEqual(len(bowl.current_class(players)), expected)
                self.assertEqual(list(map(len, bowl.select_squads(players))), [53, 53])
                self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), before)
                self.assertEqual(bytes(document.body), document.original)
        self.assertTrue(any(p.index < 1937 for p in bowl.current_class(players)))

    def test_signed_reader_refuses_wrong_size_and_signature(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "SAVEGAME.DAT"
            p.write_bytes(b"0")
            with self.assertRaisesRegex(ValueError, "unsupported franchise save size"):
                bowl.read_franchise(p)
            p.write_bytes(bytes(720044))
            p.with_name("EXTRA").write_bytes(bytes(20))
            with self.assertRaisesRegex(ValueError, "EXTRA"):
                bowl.read_franchise(p)


if __name__ == "__main__":
    unittest.main()

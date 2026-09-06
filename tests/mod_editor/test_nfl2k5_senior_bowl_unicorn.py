"""Bounded execution of dormant policy/select/codec components, not native MVP."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_senior_bowl as bowl
from tests.nfl2k5_senior_bowl_fixture import Machine, prospects, event


class NativeComponents(Machine):
    def test_native_squad_selection_matches_host_all_schemes_and_seeds(self):
        for scheme in bowl.SCHEMES:
            for seed in (0, 1, 42, 0xFFFFFFFF):
                with self.subTest(scheme=scheme, seed=seed):
                    rows = prospects(scheme)
                    settings = bowl.Settings(scheme=scheme)
                    e = event(settings=settings, seed=seed)
                    live = self.state()
                    count, out = self.select(rows, seed=seed, scheme=scheme, df=True)
                    self.assertEqual(count, len(rows))
                    self.assertEqual(out[80:84], e.to_bytes()[80:84])
                    self.assertEqual(out[256:], e.to_bytes()[256:])
                    self.assertEqual(self.state(), live)

    def test_scan_filters_veterans_drafted_unallocated_owned_records(self):
        rows = list(prospects(extras=8))
        for pos in range(17):
            offsets = [i for i, p in enumerate(rows) if p.position == pos]
            for offset, flags, owned in ((offsets[0], 4, False), (offsets[1], 0x34, False),
                                         (offsets[2], 0x10, False), (offsets[3], 0x14, True)):
                rows[offset] = replace(rows[offset], flags=flags, owned=owned)
        e = bowl.prepare_event(rows, year=7, franchise_id=b"f"*16)
        result, out = self.select(rows)
        self.assertEqual(result, len(e.class_rows))
        self.assertEqual(out[256:], e.to_bytes()[256:])

    def test_shortage_duplicate_bounds_and_no_live_state_mutation(self):
        original = event().to_bytes()
        self.uc.mem_write(self.state_va, original)
        for rows, count in ((tuple(p for p in prospects() if p.position != 1), 0xFFFFFFFE),
                            ((prospects()[0],)*2, 0xFFFFFFFF),
                            ((replace(prospects()[0], index=4096),), 0xFFFFFFFF),
                            ((replace(prospects()[0], position=17),), 0xFFFFFFFF)):
            self.assertEqual(self.select(rows)[0], count)
            self.assertEqual(self.state(), original)
        self.assertEqual(self.call("sb_select", self.INPUT, 4097, 1, 0, self.state_va+0x4000), 0xFFFFFFFF)

    def test_crc_matches_host_on_event_payload(self):
        raw = event().to_bytes()
        self.uc.mem_write(self.INPUT, raw)
        self.assertEqual(self.call("sb_crc", self.INPUT+16, len(raw)-16, df=True), zlib.crc32(raw[16:]))

    def test_stage_policy_without_week_day_hour_writes(self):
        for stage in range(1, 10):
            for days, untouched in ((4, True), (3, True), (4, False)):
                e = event()
                self.put_event(e)
                expected, hold = bowl.stage_preamble(e, year=7, stage=stage, days=days, untouched_hours=untouched)
                result = self.call("sb_gate", self.state_va, 7, stage, days, int(untouched), df=True)
                self.assertEqual(result, int(hold))
                self.assertEqual(self.state(), expected.to_bytes())
                self.assertFalse(any(self.INPUT <= va < self.INPUT+0x30000 for va, _ in self.writes))

    def test_terminal_once_per_year_and_stale_year_refusal(self):
        for state in ("complete", "skipped"):
            e = replace(event(), state=state)
            self.put_event(e)
            self.assertEqual(self.call("sb_gate", self.state_va, 7, 4, 4, 1), 0)
            self.assertEqual(self.state(), e.to_bytes())
        self.put_event(event())
        original = self.state()
        self.assertEqual(self.call("sb_gate", self.state_va, 8, 4, 4, 1), 0xFFFFFFFF)
        self.assertEqual(self.state(), original)

    def test_component_export_reload_and_interrupted_run_seed_retained(self):
        for state in ("pending", "running", "complete", "skipped"):
            e = replace(event(), state=state)
            self.put_event(e)
            self.assertEqual(self.call("sb_save", self.OUTPUT, bowl.EVENT_SIZE, df=True), 1)
            self.assertEqual(bytes(self.uc.mem_read(self.OUTPUT, bowl.EVENT_SIZE)), e.to_bytes())
            self.uc.mem_write(self.state_va, bytes(bowl.EVENT_SIZE))
            self.assertEqual(self.call("sb_load", self.OUTPUT, bowl.EVENT_SIZE, self.IDENTITY, 7, df=True), 1)
            expected = replace(e, state="pending") if state == "running" else e
            self.assertEqual(self.state(), expected.to_bytes())

    def test_reload_rejects_identity_year_size_crc_and_foreign_schema_atomically(self):
        e = event()
        self.put_event(e)
        self.uc.mem_write(self.OUTPUT, e.to_bytes())
        original = self.state()
        for args in ((self.OUTPUT, bowl.EVENT_SIZE-1, self.IDENTITY, 7),
                     (self.OUTPUT, bowl.EVENT_SIZE, self.IDENTITY, 8),
                     (self.OUTPUT, bowl.EVENT_SIZE, self.IDENTITY+16, 7),
                     (self.state_va, bowl.EVENT_SIZE, self.IDENTITY, 7)):
            self.assertEqual(self.call("sb_load", *args), 0)
            self.assertEqual(self.state(), original)
        for offset in (0, 4, 8, 12, 81):
            damaged = bytearray(e.to_bytes())
            damaged[offset] ^= 0xFF
            if offset != 12:
                struct.pack_into("<I", damaged, 12, zlib.crc32(damaged[16:]))
            self.uc.mem_write(self.OUTPUT, bytes(damaged))
            self.assertEqual(self.call("sb_load", self.OUTPUT, bowl.EVENT_SIZE, self.IDENTITY, 7), 0)
            self.assertEqual(self.state(), original)

    def test_simulator_component_refuses_without_calls_or_nonstack_writes(self):
        self.put_event(event())
        before = bytes(self.uc.mem_read(self.state_va, bowl.DATA_SIZE))
        self.assertEqual(self.call("sb_simulate", df=True, limit=3), 0xFFFFFFFA)
        self.assertEqual(bytes(self.uc.mem_read(self.state_va, bowl.DATA_SIZE)), before)
        self.assertFalse(self.writes)


if __name__ == "__main__":
    unittest.main()

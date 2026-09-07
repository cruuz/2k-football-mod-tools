"""Calendar patch pins, ownership, refusal and composition. Plain standalone unittest."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_calendar_engine as c, nfl2k5_season_length as season
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"


def repin(payload, va, data):
    image = XbeImage(payload)
    s = image.section(va)
    out = bytearray(payload)
    at = s.raw + va - s.start
    out[at:at + len(data)] = data
    for section in _sections(payload):
        if section.virtual_address == s.start:
            off = section.header_offset + 36
            out[off:off + 20] = section_digest(bytes(out), section)
    return bytes(out)


class PureTests(unittest.TestCase):
    def test_tables_are_gregorian_and_fit_exact_budget(self):
        for base in c.SUPPORTED_BASE_YEARS:
            ro = c.read_only_for(base)
            self.assertEqual(len(ro), 2048)
            starts = struct.unpack_from("<357i", ro, c.YEAR_TABLE_OFFSET)
            for y in range(1900, 2256):
                self.assertEqual(starts[y - 1900], (dt.date(y, 1, 1) - c.EPOCH).days)
                self.assertEqual(starts[y + 1 - 1900] - starts[y - 1900], 366 if dt.date(y, 12, 31).timetuple().tm_yday == 366 else 365)
            self.assertEqual(starts[2000 - 1900], 0)
        self.assertLessEqual(len(c.assembly.CODE), 1024)
        self.assertFalse(any(row[1] == "data" for row in c.REQUESTS))
        plan = space.plan(c.REQUESTS)
        self.assertTrue(plan)

    def test_assembly_reproduces_committed_code(self):
        assembler = shutil.which("as")
        if not assembler:
            self.skipTest("GNU x86 as absent; generated runtime template needs no assembler")
        version = subprocess.run([assembler, "--version"], capture_output=True, text=True)
        if version.returncode or "GNU assembler" not in version.stdout or not any(
                arch in version.stdout for arch in ("x86_64", "i386", "i486", "i586", "i686")):
            self.skipTest("as is not GNU x86 as; ELF32 byte reproduction requires that development tool")
        subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_calendar_engine_assemble.py"), "--check"], check=True)

    def test_foreign_input_and_unsupported_base_refuse(self):
        for payload in (b"", b"XBEH" + bytes(4096)):
            self.assertEqual(c.status(payload), "foreign")
            with self.assertRaises(ValueError):
                c.apply(payload)
        with self.assertRaises(ValueError):
            c.read_only_for(2053)


@unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe absent")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise AssertionError("retail default.xbe digest differs")
        cls.base, _ = season.apply(cls.retail)
        cls.patched, cls.receipt = c.apply(cls.base)

    def test_idempotence_exact_receipt_and_dependencies(self):
        self.assertEqual(c.status(self.retail), "retail")
        self.assertEqual(c.status(self.base), "retail")
        self.assertEqual(c.status(self.patched), "applied")
        self.assertEqual(season.read_year(self.patched), 2026)
        for group in season.GROUPS:
            self.assertEqual(season.group_status(self.patched, group), "applied", group)
        result, receipt = c.apply(self.patched)
        self.assertEqual(result, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(receipt["edits"], [])
        self.assertEqual(self.receipt["changed_bytes"], sum(a != b for a, b in zip(self.base, self.patched)) + len(self.patched) - len(self.base))
        self.assertEqual(self.receipt["after_sha256"], hashlib.sha256(self.patched).hexdigest())
        self.assertEqual(self.receipt["persistent_data_bytes"], 0)

    def test_retail_2004_auto_dependencies_and_year_status(self):
        out, _ = c.apply(self.retail)
        self.assertEqual(c.status(out), "applied")
        self.assertEqual(season.read_year(out), 2004)
        for group in season.GROUPS:
            self.assertEqual(season.group_status(out, group, year=2004), "applied")
        self.assertEqual(c.apply(out)[0], out)

    def test_every_partial_hook_and_table_refused_even_with_resealed_digest(self):
        a = c._allocations(self.patched)
        for name, va, before, after in c.sites(a["code"]["va"], a["read_only"]["va"], 2026):
            if before == after:
                continue
            broken = repin(self.patched, va, before)
            with self.subTest(name=name):
                self.assertEqual(c.status(broken), "foreign")
                with self.assertRaises(ValueError):
                    c.apply(broken)
        for kind in ("code", "read_only"):
            va = a[kind]["va"]
            broken = repin(self.patched, va + a[kind]["size"] - 1, b"\xa5")
            self.assertEqual(c.status(broken), "foreign")
            with self.assertRaises(ValueError):
                c.apply(broken)
        for va, size, _ in c.GUARDS:
            at = va + size - 1
            old = XbeImage(self.base).read(at, 1)[0]
            broken = repin(self.base, at, bytes([old ^ 1]))
            self.assertEqual(c.status(broken), "foreign", hex(at))

    def test_lifecycle_and_shared_formats_are_preserved(self):
        before, after = XbeImage(self.base), XbeImage(self.patched)
        for va, size in ((0x247B40, 0x1D0), (0x2BCF90, 0x2A0), (0x2BD980, 0x180),
                         (0x2BE6F0, 0x1D0), (0x14EFE0, 0x240), (0x116550, 0x110),
                         (0x13ECA0, 0xA0), (0x260A80, 18), (0xA8E548, 24),
                         (0xEAD010, 10), (0xEB9494, 10), (0x1C1A90, 0x80)):
            self.assertEqual(before.read(va, size), after.read(va, size), hex(va))

    def test_incomplete_request_union_refuses(self):
        allocated, _ = space.apply(self.base, (("different_owner", "code", 16, 16),), scaleout=True)
        with self.assertRaisesRegex(ValueError, "complete owner union"):
            c.apply(allocated)

    def test_manifest_recorder_covers_complete_hooks_and_allocations(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        recorder.observe(c, "apply", self.base, self.patched, self.receipt)
        for edit in self.receipt["edits"]:
            start = int(edit["va"], 0)
            self.assertTrue(any(int(r["start"], 0) <= start and int(r["end"], 0) >= start + edit["bytes"]
                                for r in recorder.spans), edit["label"])
        spans = space.reservations(self.patched)
        for kind, alloc in c._allocations(self.patched).items():
            self.assertTrue(any(r["owner"] == c.OWNER and int(r["start"], 0) == alloc["va"] and r["size"] == alloc["size"] for r in spans), kind)
        self.assertEqual(len(recorder.covered), len(self.patched))


if __name__ == "__main__":
    unittest.main()

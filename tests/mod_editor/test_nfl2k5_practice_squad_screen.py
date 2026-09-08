"""Standalone pins, composition, budgets, exact menu and manifest ownership."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.nfl2k5_practice_squad_screen_fixture import XBE, composed
from mod_editor.core import nfl2k5_practice_squad_screen as screen
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_practice_reserves as pr
from mod_editor.core import nfl2k5_franchise_practice as fp
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest


class PublicTests(unittest.TestCase):
    def test_budget_plans_with_every_beta62_owner(self):
        requests = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([r for r in requests if r[0] == screen.OWNER], [list(r) for r in screen.REQUESTS])
        from tests.nfl2k5_allocator_stack import REQUESTS
        keys = {(r[0], r[1]) for r in requests}
        requests += [list(r) for r in REQUESTS if (r[0], r[1]) not in keys]
        space.plan(requests)
        self.assertLess(len(screen.assembly.CODE), screen.CODE_SIZE)
        self.assertEqual(screen.DATA_SIZE, 256)

    def test_foreign_shapes_fail_closed(self):
        for data in (b"", b"XBEH" + bytes(4092)):
            self.assertEqual(screen.status(data), "foreign")
            with self.assertRaises(ValueError):
                screen.apply(data)

    def test_capability_handoff_schema_and_new_evidence_paths(self):
        from mod_editor.capabilities.validate_registry import validate_data
        registry = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json").read_text())
        entry = json.loads((ROOT / "docs/mod_editor/nfl2k5_practice_squad_screen_capability.json").read_text())[0]
        registry["capabilities"] = [row for row in registry["capabilities"] if row["id"] != entry["id"]] + [entry]  # merged since integration 2
        registry["capabilities"].sort(key=lambda row: row["id"])
        # Unrelated registry evidence is private/absent in lean worktrees.
        validate_data(registry, check_files=False)
        for path in (entry["backend"]["module"], *entry["evidence"]):
            self.assertTrue((ROOT / path).is_file(), path)
        self.assertFalse(entry["gui"]["default_enabled"])
        self.assertEqual(entry["runtime"]["status"], "not-tested")

    @unittest.skipUnless(shutil.which("as"), "GNU as is not available for development-template reproduction")
    def test_assembly_template_is_reproducible(self):
        # Apple's assembler does not implement GNU --32 and MinGW's emits COFF; runtime never needs as.
        from _gnu_elf32_as import gnu_elf32_as
        if not gnu_elf32_as():
            self.skipTest("template reproduction requires GNU i386 as producing ELF32")
        subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_practice_squad_screen_assemble.py"), "--check"], check=True)


@unittest.skipUnless(XBE.is_file(), "private pinned USA default.xbe extraction is absent")
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != ps.RETAIL_SHA256:
            raise unittest.SkipTest("extracted XBE is not the pinned USA retail image")
        cls.base = composed(cls.retail)
        cls.patched, cls.receipt = screen.apply(cls.base)
        cls.code, cls.data = screen.allocations(cls.patched)
        cls.blob, cls.labels = screen.code_for(cls.patched, cls.code["va"], cls.data["va"])
        cls.image = XbeImage(cls.patched)

    def test_dependency_status_and_idempotent_replay(self):
        self.assertEqual(screen.status(self.retail), "retail")
        self.assertEqual(screen.status(self.base), "retail")
        for p in (self.retail, ps.apply(self.retail)[0], fp.apply(ps.apply(self.retail)[0])[0]):
            with self.assertRaisesRegex(ValueError, "first"):
                screen.apply(p)
        for module in (screen, ps, fp, pr):
            self.assertEqual(module.status(self.patched), "applied")
            self.assertEqual(module.apply(self.patched)[0], self.patched)
            self.assertEqual(module.apply(self.patched)[1]["changed_bytes"], 0)
        self.assertFalse(self.receipt["runtime_witnessed"])
        self.assertFalse(self.receipt["poaching"])
        self.assertFalse(self.receipt["protection"])
        self.assertEqual(len(self.patched), 12300288)
        for s in _sections(self.patched):
            self.assertEqual(s.stored_digest, section_digest(self.patched, s))

    def test_composed_menu_clones_binding_columns_and_main_menu_crib(self):
        rows = fp.read_rows(self.patched)
        self.assertEqual(len(rows), 13)
        self.assertEqual([r["label"] for r in rows[:6]],
                         ["Schedule", "Playoff Schedule", "Super Bowl Schedule", "Off-Season Schedule", "Practice", "Practice Squad"])
        self.assertEqual([r["label"] for r in rows[6:12]],
                         ["Front Office", "Gameplan", "ESPN.com", "Features", "Options", "Quit"])
        self.assertEqual(rows[4]["activate"], hex(fp.ROW_CALLBACK_VA))
        old_rows = fp.read_rows(self.base)
        self.assertEqual([r["visibility"] for r in rows[:4]], [r["visibility"] for r in old_rows[:4]])
        self.assertEqual(self.image.read(self.labels["menu"] + 13 * 52, 52), bytes(52))
        # Main menu has its own label and callback (Coach's Desk uses different
        # addresses). Preserve the complete row and its actual destination stub.
        old = XbeImage(self.retail)
        self.assertEqual(self.image.read(0x515528, 52), old.read(0x515528, 52))
        self.assertEqual(self.image.read(0x24D440, 0x4C), old.read(0x24D440, 0x4C))
        self.assertEqual(self.image.read(0x515550, 4), struct.pack("<I", 0x24D440))
        for name in ("active_page", "reserve_page"):
            page = self.labels[name]
            self.assertEqual(self.image.read(page + 0x9c, 124), old.read(0x554b58 + 0x9c, 124))
            self.assertEqual(self.image.read(page + 0x94, 4), bytes(4))
            self.assertEqual(self.image.read(page + 0x20, 4), struct.pack("<I", 17))
        self.assertEqual(self.image.read(self.labels["sheet"] + 0xc8, 4), bytes.fromhex("1d030300"))
        self.assertEqual(self.image.read(self.labels["descriptor"] + 8, 4), struct.pack("<I", 0xf40f0))

    def test_exact_write_extents_and_permission_correct_allocations(self):
        # All retail sections stay byte-identical except the one delegated dword.
        old = XbeImage(self.base)
        for section in old.sections:
            before = bytearray(old.read(section.start, section.raw_size))
            if section.start <= fp.COACH_DESK_ROWS_PTR_VA < section.end:
                off = fp.COACH_DESK_ROWS_PTR_VA - section.start
                before[off:off+4] = struct.pack("<I", self.labels["menu"])
            if section.name == ".XTLID":
                # Allocator's existing loader-logo relocation is independent.
                continue
            self.assertEqual(self.image.read(section.start, section.raw_size), bytes(before), section.name)
        self.assertEqual(self.image.read(self.code["va"], screen.CODE_SIZE), self.blob)
        self.assertFalse(self.image.runtime_writable(self.code["va"], screen.CODE_SIZE))
        self.assertTrue(self.image.runtime_writable(self.data["va"], screen.DATA_SIZE))
        self.assertEqual(self.image.read(self.data["va"], screen.DATA_SIZE), bytes(screen.DATA_SIZE))
        self.assertLessEqual(self.labels["content_end"] - self.code["va"], screen.CODE_SIZE)
        if importlib.util.find_spec("capstone"):
            for write in absolute_writes(self.patched, [(self.code["va"], self.code["va"] + len(screen.assembly.CODE))]):
                if write["target"] is not None:
                    self.assertTrue(write["writable"], write)

    def test_foreign_pin_code_table_pointer_and_rw_refuse_without_mutation(self):
        addresses = [0x555098, 0x554b88, 0x52208c, fp.COACH_DESK_ROWS_PTR_VA,
                     self.code["va"], self.labels["menu"], self.labels["promote_menu"], self.data["va"]]
        for va in addresses:
            with self.subTest(va=hex(va)):
                data = bytearray(self.patched)
                off = self.image.offset(va, 1)
                data[off] ^= 1
                # Section SHA-1 repinning cannot bless tampered owner contents.
                for sec in _sections(data):
                    data[sec.header_offset + 36:sec.header_offset + 56] = section_digest(data, sec)
                before = bytes(data)
                self.assertEqual(screen.status(data), "foreign")
                with self.assertRaises(ValueError):
                    screen.apply(data)
                self.assertEqual(bytes(data), before)
        allocated, _ = space.apply(self.base, screen.REQUESTS)
        code, data = screen.allocations(allocated)
        mixed, _ = space.install_code(allocated, screen.OWNER, screen.code_for(allocated, code["va"], data["va"])[0])
        self.assertEqual(screen.status(mixed), "foreign")
        with self.assertRaises(ValueError):
            screen.apply(mixed)
        wrong_union, _ = space.apply(self.base, (("unrelated", "code", 16, 16),))
        with self.assertRaisesRegex(ValueError, "union"):
            screen.apply(wrong_union)

    def test_relocated_at_different_union_address_and_complete_owner_replay(self):
        from tests.nfl2k5_allocator_stack import compose, REQUESTS
        first, _ = compose(self.base)
        last, _ = compose(self.base, reverse=True)
        self.assertEqual(first, last)
        self.assertNotEqual(screen.allocations(first)[0]["va"], self.code["va"])
        for module in (screen, ps, fp, pr):
            self.assertEqual(module.status(first), "applied")
        self.assertEqual(space.apply(first, REQUESTS)[0], first)

    def test_manifest_records_entire_pointer_and_both_allocations(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.base)
        result, receipt = screen.apply(self.base)
        recorder.observe(screen, "apply", self.base, result, receipt)
        spans = recorder.finish(result)
        for va, size in ((fp.COACH_DESK_ROWS_PTR_VA, 4), (self.code["va"], screen.CODE_SIZE),
                         (self.data["va"], screen.DATA_SIZE)):
            self.assertTrue(any(r["owner"] == screen.OWNER and int(r["start"], 0) <= va
                                and int(r["end"], 0) >= va + size for r in spans), hex(va))


if __name__ == "__main__":
    unittest.main()

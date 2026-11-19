"""beta 81 review M1: the 64 MB edition's save messages for a franchise saved by the 128 MB edition.

The delete prompt formats the save and device names. The load error uses the save name and the controller button
token. Static checks cover both string slots, their references and the native reservation inventory. The 64 MB
profile enables the messages. The standard build step preserves the entire executable. The game's own formatter
at 0x4A400 renders both messages in the private retail Unicorn test. Optional NFL2K5_V010_64_XBE and
NFL2K5_V010_128_XBE inputs check the writer's complete output on the archived editions.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_edition_save_notes as notes  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, XBE  # noqa: E402

V010 = {"64": os.environ.get("NFL2K5_V010_64_XBE", ""), "128": os.environ.get("NFL2K5_V010_128_XBE", "")}


def _formats(text: str) -> list[str]:
    return re.findall(r"%[a-z]|\|[A-Z_]+\|", text)


class StaticTests(unittest.TestCase):
    def test_cave_inventory_covers_complete_strings_and_their_guarded_references(self):
        manifest_path = Path(os.environ.get("NFL2K5_CAVE_MANIFEST", ROOT / "data/nfl2k5_cave_reservations.json"))
        inventory = json.loads(manifest_path.read_bytes())
        self.assertIn(notes.OWNER, inventory["extra_owners"])
        calls = [step for step in inventory["steps"] if step["owner"] == notes.OWNER]
        self.assertTrue(any(call["function"] == "apply" and call["changed_bytes"] > 0 for call in calls))
        owned = [row for row in inventory["spans"] if row["owner"] == notes.OWNER]
        expected = {(va, va + len(after), "declared edit: " + label) for label, va, _, after in notes.SITES}
        refs = {(va, va + len(code), "guarded string reference: " + label) for label, va, code in notes.DEPENDENCIES}
        declared = {(int(row["start"], 0), int(row["end"], 0), row["basis"]) for row in owned
                    if row["basis"] != "observed byte diff"}
        self.assertEqual(declared, expected | refs)
        observed = {address for row in owned if row["basis"] == "observed byte diff"
                    for address in range(int(row["start"], 0), int(row["end"], 0))}
        for label, start, before, after in notes.SITES:
            changes = {start + i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]}
            with self.subTest(slot=label):
                self.assertEqual(observed.intersection(range(start, start + len(after))), changes)
        for start, end, label in refs:
            with self.subTest(reference=label):
                self.assertTrue(observed.isdisjoint(range(start, end)))

    def test_texts_keep_the_arguments_and_fit_their_slots(self):
        expected = {"delete confirmation text": (["%s", "%s"], ["%s", "%s"]),
                    "load failure text": (["%s", "%s", "|CROSS|"], ["%s", "|CROSS|"])}   # the device is not named
        for label, va, before, after in notes.SITES:
            with self.subTest(label):
                self.assertEqual(len(before), len(after))
                self.assertTrue(after.endswith(b"\0\0"))
                old = before.decode("utf-16-le").split("\0")[0]
                new = after.decode("utf-16-le").split("\0")[0]
                self.assertEqual((_formats(old), _formats(new)), expected[label])
                self.assertTrue(all(32 <= ord(c) < 127 or c == "\n" for c in new))
                self.assertIn("128 MB", new)

    def test_on_only_in_the_64_mb_profile(self):
        from mod_editor.core import mod_build, nfl2k5_memory_budget as mb
        self.assertIn("edition_save_notes", mb.PROFILE_64_ON)
        self.assertIs(mb.profile_64_plan(None).get("edition_save_notes"), True)
        for name, preset in mod_build.PRESETS.items():
            self.assertFalse(preset.get("edition_save_notes", False), name)
        self.assertIs(mod_build.BuildPlan(Path("in.iso"), Path("out.iso")).edition_save_notes, False)


@unittest.skipUnless(XBE.is_file(), "pinned USA retail XBE required")
class ApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        cls.retail = retail_bytes()

    def test_apply_is_in_place_idempotent_and_refuses_a_moved_reference(self):
        self.assertEqual(notes.status(self.retail), "retail")
        patched, receipt = notes.apply(self.retail)
        self.assertEqual(notes.status(patched), "applied")
        self.assertEqual(len(patched), len(self.retail))
        self.assertEqual(notes.apply(patched)[0], patched)
        changed = [i for i, (a, b) in enumerate(zip(self.retail, patched)) if a != b]
        slots = [(rdata.offset_of(self.retail, va), rdata.offset_of(self.retail, va) + len(before))
                 for _label, va, before, _after in notes.SITES]
        header = [(s.header_offset + 36, s.header_offset + 56) for s in rdata._sections(self.retail)]
        self.assertTrue(all(any(lo <= i < hi for lo, hi in slots + header) for i in changed))
        moved = bytearray(self.retail)
        for label, va, raw in notes.DEPENDENCIES:
            start = rdata.offset_of(self.retail, va)
            for index in range(len(raw)):
                with self.subTest(reference=label, byte=index):
                    moved[start + index] ^= 0x10
                    foreign = bytes(moved)
                    moved[start + index] ^= 0x10
                    self.assertEqual(notes.status(foreign), "foreign")
                    with self.assertRaises(ValueError):
                        notes.apply(foreign)

    def test_the_build_step_leaves_the_standard_edition_byte_identical(self):
        from mod_editor.core import mod_build
        with tempfile.TemporaryDirectory() as folder:
            for plan_values, expect in ((mod_build.PRESETS["softdrink_experimental"], "retail"),
                                        ({"edition_save_notes": True}, "applied")):
                target = Path(folder) / "default.xbe"
                target.write_bytes(self.retail)
                plan = mod_build.BuildPlan(Path("in.iso"), target)
                plan.edition_save_notes = bool(plan_values.get("edition_save_notes", False))
                receipt = {"steps": [], "result": {}}
                mod_build._apply_edition_save_notes(plan, target, receipt, lambda *a: None)
                self.assertEqual(notes.status(target.read_bytes()), expect)
                if expect == "retail":
                    self.assertEqual(target.read_bytes(), self.retail)
                    self.assertEqual(receipt, {"steps": [], "result": {}})

    @unittest.skipUnless(HAVE_UC, "Unicorn required")
    def test_the_game_formats_both_messages(self):
        import unicorn as u
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        patched = notes.apply(self.retail)[0]
        img = XbeImage(patched)
        uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        lo = min(s.start for s in img.sections)
        top = max(s.start + s.size for s in img.sections)
        uc.mem_map(lo & ~0xFFF, (top - lo + 0x1FFF) & ~0xFFF)
        for s in img.sections:
            uc.mem_write(s.start, img.read(s.start, min(s.size, s.raw_size)))
        heap, stack, stop = 0x5000000, 0x6000000, 0x7000000
        for base in (heap, stack - 0x10000, stop):
            uc.mem_map(base, 0x10000)
        uc.mem_write(stop, b"\xc3")
        name, device, out, args = heap, heap + 0x100, heap + 0x1000, heap + 0x200
        uc.mem_write(name, "Franchise1\0".encode("utf-16-le"))
        uc.mem_write(device, "Xbox Hard Disk\0".encode("utf-16-le"))
        uc.mem_write(args, struct.pack("<2I", name, device))
        rendered = {}
        for label, va, _before, _after in notes.SITES:
            sp = stack - 0x100
            uc.mem_write(sp, struct.pack("<2I", stop, args))
            uc.reg_write(UC_X86_REG_ESP, sp)
            uc.reg_write(UC_X86_REG_ECX, out)
            uc.reg_write(UC_X86_REG_EDX, va)
            uc.emu_start(0x4A400, stop, count=2_000_000)
            raw = bytes(uc.mem_read(out, 0x200))
            rendered[label] = raw.decode("utf-16-le").split("\0")[0]
        self.assertEqual(rendered["delete confirmation text"], "Delete Franchise1 from Xbox Hard Disk? A 128 MB save "
                                                              "shows Damaged here but loads there. Continue?")
        self.assertEqual(rendered["load failure text"], "Can't load Franchise1. 128 MB save?\nPress |CROSS| to continue.")


class ShippedEditionTests(unittest.TestCase):
    """The shipped v0.10 executables (private; set NFL2K5_V010_64_XBE and NFL2K5_V010_128_XBE)."""

    def test_text_writer_changes_only_the_two_strings_and_their_digest_on_each_shipped_edition(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        found = {k: Path(v) for k, v in V010.items() if v and Path(v).is_file()}
        if not found:
            self.skipTest("shipped v0.10 executables not configured")
        for edition, path in found.items():
            with self.subTest(edition):
                payload = path.read_bytes()
                self.assertIn(notes.status(payload), ("retail", "applied"))
                patched = notes.apply(payload)[0]
                self.assertEqual(notes.status(patched), "applied")
                image = XbeImage(payload)
                section = image.section(notes.DELETE_VA)
                self.assertIsNotNone(section)
                expected = bytearray(payload)
                for _, va, _, text in notes.SITES:
                    self.assertEqual(image.section(va, len(text)), section)
                    offset = image.offset(va, len(text))
                    expected[offset:offset + len(text)] = text
                section_bytes = expected[section.raw:section.raw + section.raw_size]
                digest = hashlib.sha1(struct.pack("<I", section.raw_size) + section_bytes, usedforsecurity=False).digest()
                expected[section.header + 36:section.header + 56] = digest
                self.assertTrue(patched == expected, "unexpected bytes outside the two strings and their section digest")


if __name__ == "__main__":
    unittest.main()

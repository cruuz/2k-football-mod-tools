"""7-on-7 practice mode: the executable patch (fifth Practice Type + practice-book loader + rush
gates) and the practice-book content.

Layers:
* static -- site shapes, no overlaps, the cave fits, the tables and the name are where the code says;
* synthetic -- status / apply / idempotent / foreign on the shared synthetic XBE seeded with the
  retail spans (no private data needed);
* retail (needs the private default.xbe) -- status/apply on the real executable, order independence
  with the returner fix and the draft AI, and (with unicorn) the patched Practice Type switch, the
  book loader and the two Power Pocket gates run for real;
* book (needs the private extracted packs) -- the 7-on-7 practice book round trip: capacity, eleven
  slots with the parked linemen on the retail idle chain, the 4-second timer rusher, every play
  through the ported game validator, the AI-excluded flag on the retail plays, the wrapper untouched,
  and the archive write path against a fake archive.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build, modpack  # noqa: E402
from mod_editor.core import nfl2k5_draft_ai as draft  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_returner_fix as returner  # noqa: E402
from mod_editor.core import nfl2k5_seven_on_seven as s7  # noqa: E402
from mod_editor.core import nfl2k5_seven_on_seven_book as book  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402
from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402

RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
RETAIL_PACKS = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030")
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None
IMAGE_BASE = 0x10000
BOOK_OBJECTS = (0xB307D0, 0xB30810)


def _seed(payload: bytes) -> bytes:
    """The synthetic XBE with every 7-on-7 site holding its retail bytes."""

    buf = bytearray(payload)
    for _label, va, before, _after in s7.sites():
        off = s7._offset(payload, va)
        buf[off: off + len(before)] = before
    return bytes(buf)


class StaticTests(unittest.TestCase):
    def test_sites_are_well_formed_and_disjoint(self) -> None:
        spans = []
        for label, va, before, after in s7.sites():
            self.assertEqual(len(before), len(after), label)
            self.assertNotEqual(before, after, label)
            spans.append((va, va + len(before), label))
        spans.sort()
        for (a0, a1, la), (b0, _b1, lb) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0, f"{la} overlaps {lb}")
        self.assertEqual(len(s7.sites()), 9)
        self.assertEqual(len(s7.RETAIL_CAVE), s7.CAVE_SIZE)

    def test_cave_layout(self) -> None:
        cave = s7.cave_bytes()
        self.assertEqual(len(cave), s7.CAVE_SIZE)
        self.assertEqual(cave[s7.FLAG_OFFSET], 0)
        strings = struct.unpack_from("<5I", cave, s7.STRING_TABLE_OFFSET)
        self.assertEqual(strings[:4], s7.RETAIL_STRINGS)
        self.assertEqual(strings[4], s7.NAME_VA)
        name = cave[s7.NAME_OFFSET: s7.NAME_OFFSET + 14]
        self.assertEqual(name, "7-On-7".encode("utf-16le") + b"\0\0")
        labels = s7.cave_labels()
        jumps = struct.unpack_from("<5I", cave, s7.JUMP_TABLE_OFFSET)
        self.assertEqual(jumps, tuple(labels[f"stub{k}"] for k in range(5)))
        for k in range(5):
            self.assertGreaterEqual(labels[f"stub{k}"], s7.CODE_VA)
        report = s7.code_report()
        self.assertLessEqual(report["code_bytes"], report["code_capacity"])
        self.assertFalse(report["runtime_verified"])

    def test_site_bytes_point_into_the_cave(self) -> None:
        sites = {label: after for label, _va, _before, after in s7.sites()}
        self.assertEqual(sites["practice_type_max"][-1], 3)
        self.assertEqual(struct.unpack_from("<I", sites["practice_type_wrap"], 6)[0], 4)
        self.assertEqual(sites["practice_type_register"], b"\x68" + struct.pack("<I", s7.STRING_TABLE_VA) + b"\x6a\x04")
        self.assertEqual(struct.unpack_from("<I", sites["practice_type_text"], 3)[0], s7.STRING_TABLE_VA)
        self.assertEqual(struct.unpack_from("<I", sites["practice_type_switch"], 3)[0], s7.JUMP_TABLE_VA)
        labels = s7.cave_labels()
        loader = sites["book_loader"]
        self.assertEqual(loader[0], 0xE9)
        self.assertEqual(s7.LOADER_SITE_VA + 5 + struct.unpack_from("<i", loader, 1)[0], labels["loader"])
        self.assertEqual(loader[5:], b"\x90" * 4)
        gate = sites["rush_gate"]
        self.assertEqual(s7.RUSH_GATE_SITE_VA + 5 + struct.unpack_from("<i", gate, 1)[0], labels["rush_gate"])
        shed = sites["shed_gate"]
        self.assertEqual(s7.SHED_GATE_SITE_VA + 5 + struct.unpack_from("<i", shed, 1)[0], labels["shed_gate"])
        self.assertEqual(shed[5], 0x90)

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_cave_code_decodes_and_targets_the_retail_stubs(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        size = s7.code_report()["code_bytes"]
        code = s7.cave_bytes()[s7.CODE_OFFSET: s7.CODE_OFFSET + size]
        decoded = list(md.disasm(code, s7.CODE_VA))
        self.assertEqual(sum(i.size for i in decoded), size)
        jumps = [int(i.op_str, 16) for i in decoded if i.mnemonic == "jmp"]
        for stub in s7.RETAIL_STUBS + (s7.LOADER_PRACTICE_VA, s7.LOADER_TEAMS_VA):
            self.assertIn(stub, jumps)
        self.assertNotIn(s7.KICK_WORD_VA, [int(x, 16) for i in decoded for x in i.op_str.replace("[", " ").replace("]", " ").split() if x.startswith("0x")])


class SyntheticTests(unittest.TestCase):
    def test_status_apply_idempotent_and_foreign(self) -> None:
        seeded = _seed(_build_synthetic_xbe())
        self.assertEqual(s7.status(_build_synthetic_xbe()), "retail")     # the shared fixture now models the sites
        self.assertEqual(s7.status(bytes(len(seeded))), "foreign")
        self.assertEqual(s7.status(seeded), "retail")
        patched, receipt = s7.apply(seeded)
        self.assertEqual(s7.status(patched), "applied")
        self.assertEqual(receipt["practice_type_value"], 4)
        self.assertEqual(len(receipt["edits"]), 9)
        with self.assertRaises(s7.SevenOnSevenError):
            s7.apply(patched)
        for section in _sections(patched):
            if section.index in receipt["sections_repinned"]:
                self.assertEqual(patched[section.header_offset + 36: section.header_offset + 56], section_digest(patched, section))
        broken = bytearray(patched)
        broken[s7._offset(patched, s7.CAVE_VA + s7.CODE_OFFSET)] ^= 0xFF
        self.assertEqual(s7.status(bytes(broken)), "foreign")
        half = bytearray(seeded)
        off = s7._offset(seeded, s7.LOADER_SITE_VA)
        half[off: off + 9] = dict((l, a) for l, _v, _b, a in s7.sites())["book_loader"]
        self.assertEqual(s7.status(bytes(half)), "foreign")

    def test_build_plan_and_presets_know_the_toggle(self) -> None:
        self.assertFalse(mod_build.BuildPlan(source="s", target="t").seven_on_seven)
        self.assertEqual(mod_build.PRESETS["softdrink_experimental"]["seven_on_seven"], mod_build.SEVEN_ON_SEVEN_RELEASED)
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["seven_on_seven"])
        self.assertFalse(mod_build.PRESETS["softdrink_advanced"]["seven_on_seven"])
        self.assertTrue(mod_build.BuildPlan(source="s", target="t", seven_on_seven=True).wants_xbe_patch())
        self.assertIn("seven_on_seven", mod_build.availability())
        self.assertIn("7-on-7", modpack.describe_operation({"op": "seven_on_seven", "enabled": True}))
        with self.assertRaises(ValueError):
            mod_build.build(mod_build.BuildPlan("a.xbe", "b.xbe", seven_on_seven=True))


@unittest.skipUnless(RETAIL_XBE.exists(), "private retail XBE missing")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = RETAIL_XBE.read_bytes()
        cls.patched, cls.receipt = s7.apply(cls.retail)

    def test_status_and_apply_on_the_retail_executable(self) -> None:
        self.assertEqual(s7.status(self.retail), "retail")
        self.assertEqual(s7.status(self.patched), "applied")
        self.assertEqual(self.receipt["sections_repinned"], [0])
        self.assertLess(self.receipt["changed_bytes"], 400)

    def test_order_independence_with_returner_fix_and_draft_ai(self) -> None:
        a, _ = returner.apply(self.retail)
        a, _ = draft.apply(a)
        a, _ = s7.apply(a)
        b, _ = s7.apply(self.retail)
        b, _ = draft.apply(b)
        b, _ = returner.apply(b)
        self.assertEqual(a, b)
        self.assertEqual((s7.status(a), returner.status(a), draft.status(a)), ("applied", "applied", "applied"))

    # -- unicorn ----------------------------------------------------------------------------------
    STACK, SENTINEL = 0x7FF00000, 0x0BADF000

    def _load(self, payload: bytes):
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(IMAGE_BASE, 0xEC0000 - IMAGE_BASE)
        uc.mem_write(IMAGE_BASE, payload[: struct.unpack_from("<I", payload, 0x108)[0]])
        for s in _sections(payload):
            if s.virtual_address + s.raw_size <= 0xEC0000:
                uc.mem_write(s.virtual_address, payload[s.raw_offset: s.raw_offset + s.raw_size])
        uc.mem_map(self.STACK - 0x100000, 0x200000)
        uc.mem_map(self.SENTINEL & ~0xFFF, 0x1000)
        return uc

    def _run(self, uc, entry: int, stop_at=()) -> list[int]:
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_ESP

        esp = self.STACK - 0x1000
        uc.mem_write(esp, struct.pack("<I", self.SENTINEL))
        uc.reg_write(UC_X86_REG_ESP, esp)
        hit: list[int] = []
        handle = uc.hook_add(UC_HOOK_CODE, lambda u, a, _s, _d: (hit.append(a), u.emu_stop()) if a in stop_at else None)
        uc.emu_start(entry, self.SENTINEL, count=200_000)
        uc.hook_del(handle)
        return hit

    @staticmethod
    def _u32(uc, va: int) -> int:
        return struct.unpack("<I", bytes(uc.mem_read(va, 4)))[0]

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_practice_type_switch(self) -> None:
        from unicorn.x86_const import UC_X86_REG_EIP

        for value in range(5):
            for payload, label in ((self.patched, "patched"), (self.retail, "retail")):
                if value == 4 and label == "retail":
                    continue
                uc = self._load(payload)
                uc.mem_write(s7.PRACTICE_TYPE_VA, struct.pack("<I", value))
                uc.mem_write(s7.MODE_VA, struct.pack("<I", 9))
                uc.mem_write(s7.KICK_WORD_VA, struct.pack("<I", 9))
                if label == "patched":
                    uc.mem_write(s7.FLAG_VA, b"\x01")          # stale flag from a previous pick must be cleared
                self._run(uc, s7.SWITCH_SITE_VA - 0xF)          # FUN_000e33f0
                self.assertEqual(uc.reg_read(UC_X86_REG_EIP), self.SENTINEL, f"{label} value {value} did not return")
                mode, kick = self._u32(uc, s7.MODE_VA), self._u32(uc, s7.KICK_WORD_VA)
                expected = {0: (0, 4), 1: (1, 4), 2: (2, 4), 3: (1, 2), 4: (1, 4)}[value]
                self.assertEqual((mode, kick), expected, f"{label} value {value}")
                if label == "patched":
                    self.assertEqual(bytes(uc.mem_read(s7.FLAG_VA, 1))[0], 1 if value == 4 else 0, f"flag after value {value}")

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_book_loader_selects_the_practice_book_only_with_the_flag(self) -> None:
        practice = "PRACTICE-pb.iff".encode("utf-16le")

        def loader(payload: bytes, mode: int, flag: int) -> tuple[list[int], list[bool]]:
            uc = self._load(payload)
            uc.mem_write(s7.MODE_VA, struct.pack("<I", mode))
            if payload is self.patched:
                uc.mem_write(s7.FLAG_VA, bytes([flag]))
            hit = self._run(uc, s7.LOADER_SITE_VA, stop_at=(0x62D47, s7.LOADER_TEAMS_VA))
            names = [practice in bytes(uc.mem_read(obj, 0x80)) for obj in BOOK_OBJECTS]
            return hit, names

        self.assertEqual(loader(self.retail, 3, 0), ([0x62D47], [True, True]))        # Basic Training, retail
        self.assertEqual(loader(self.patched, 3, 0), ([0x62D47], [True, True]))       # Basic Training, patched
        self.assertEqual(loader(self.patched, 1, 1), ([0x62D47], [True, True]))       # 7-On-7: both teams get the practice book
        self.assertEqual(loader(self.patched, 1, 0), ([s7.LOADER_TEAMS_VA], [False, False]))   # Full Scrimmage: per team
        self.assertEqual(loader(self.patched, 2, 1), ([s7.LOADER_TEAMS_VA], [False, False]))   # a stale flag never leaks into Offense Only
        self.assertEqual(loader(self.patched, 4, 1), ([s7.LOADER_TEAMS_VA], [False, False]))   # ... or a real game

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_power_pocket_gates_follow_the_flag(self) -> None:
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EFLAGS, UC_X86_REG_ESI

        labels = s7.cave_labels()
        for flag, option, expected in ((0, 0, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1)):
            uc = self._load(self.patched)
            uc.mem_write(s7.FLAG_VA, bytes([flag]))
            uc.mem_write(s7.POWER_POCKET_VA, struct.pack("<I", option))
            self._run(uc, labels["rush_gate"])
            self.assertEqual(uc.reg_read(UC_X86_REG_EAX), expected, f"rush gate flag={flag} option={option}")
            uc = self._load(self.patched)
            uc.mem_write(s7.FLAG_VA, bytes([flag]))
            uc.mem_write(s7.POWER_POCKET_VA, struct.pack("<I", option))
            uc.reg_write(UC_X86_REG_ESI, 0)
            self._run(uc, labels["shed_gate"])
            zero_flag = (uc.reg_read(UC_X86_REG_EFLAGS) >> 6) & 1
            self.assertEqual(zero_flag, 0 if expected else 1, f"shed gate flag={flag} option={option}")


class _FakeEntry:
    def __init__(self, index: int, size: int) -> None:
        self.index, self.name_id, self.virtual_offset, self.size = index, 0, index * 0x20000, size


class _FakeArchive:
    """Enough of the outer archive for the practice-book write path."""

    store: bytearray = bytearray()

    def __init__(self, path, *, writable: bool = False) -> None:
        self.writable = writable
        self.entries = [_FakeEntry(i, 0x20) for i in range(334)] + [_FakeEntry(334, book.RESOURCE_SIZE)]

    def read(self, virtual_offset: int, size: int) -> bytes:
        start = virtual_offset - 334 * 0x20000
        return bytes(self.store[start: start + size])

    def write(self, virtual_offset: int, data: bytes) -> int:
        assert self.writable
        start = virtual_offset - 334 * 0x20000
        self.store[start: start + len(data)] = data
        return len(data)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None


@unittest.skipUnless((RETAIL_PACKS / "0").exists(), "private extracted packs missing")
class BookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        recode = importlib.import_module("nfl2k5_playbook_position_recode")
        with recode.OuterImage(RETAIL_PACKS) as archive:
            cls.retail = archive.read_entry(book.PRACTICE_OUTER_INDEX)
        cls.built, cls.report = book.build_replacement(cls.retail)

    def test_retail_resource_is_recognised(self) -> None:
        self.assertEqual(book.resource_status(self.retail), "retail")
        self.assertEqual(len(self.retail), book.RESOURCE_SIZE)
        with self.assertRaises(book.SevenOnSevenBookError):
            book.build_replacement(bytes(len(self.retail)))

    def test_round_trip_counts_capacity_and_wrapper(self) -> None:
        self.assertEqual(book.resource_status(self.built), "applied")
        self.assertEqual(self.built[:0x20], self.retail[:0x20])
        self.assertEqual(len(self.built), len(self.retail))
        self.assertEqual((self.report["formation_count"], self.report["play_count"], self.report["category_count"]), (28, 42, 16))
        cap = self.report["capacity"]
        self.assertLessEqual(self.report["formation_count"], cap["formations"])
        self.assertLessEqual(self.report["play_count"], cap["plays"])
        self.assertLessEqual(self.report["category_count"], cap["categories"])
        self.assertLessEqual(self.report["node_count"], cap["nodes"])
        self.assertEqual(self.report["new_node_count"], self.report["node_count"])
        again, _ = book.build_replacement(self.retail)
        self.assertEqual(again, self.built)

    def test_every_new_formation_has_eleven_slots_with_parked_idle_linemen(self) -> None:
        body = self.built[0x20:]
        parsed = parse_playbook_resource(self.built, asset_id="PRACTICE")
        for entry in self.report["formations"]:
            record = lib.formation_record(body, entry["index"])
            self.assertEqual(len(record.slots), 11)
            self.assertEqual(len(entry["parked_slots"]), 4 if entry["name"].startswith("7-On-7 T") or "Spread" in entry["name"] or "Ace" in entry["name"] else 3)
            for slot in record.slots:
                self.assertLess(abs(slot.x[0]), 2438)
            for play_index in entry["plays"]:
                _flags, chains = lib.play_chains(body, play_index)
                for slot in entry["parked_slots"]:
                    self.assertEqual([n[0] for n in chains[slot][1]], [0x01, 0x01], (entry["name"], play_index, slot))
                    self.assertEqual(chains[slot][1][0], bytes.fromhex("0100000001034080"))
                    self.assertEqual(chains[slot][1][1], bytes.fromhex("0106000004004080"))
        offence = [f for f in parsed.formations if f.name.startswith("7-On-7") and "Cover" not in f.name and "Nickel" not in f.name]
        self.assertEqual([f.name for f in offence], ["7-On-7 Trips", "7-On-7 Spread", "7-On-7 Ace"])
        for formation in offence:
            self.assertEqual(lib.formation_record(body, formation.index).qb_alignment, 1)   # under centre

    def test_defensive_sets_carry_the_timer_rusher(self) -> None:
        body = self.built[0x20:]
        for entry in self.report["formations"]:
            if "Cover" not in entry["name"] and "Nickel" not in entry["name"]:
                continue
            record = lib.formation_record(body, entry["index"])
            self.assertEqual((record.slots[0].x[0], record.slots[0].z[0]), book.RUSHER_POSITION)
            self.assertEqual(len(entry["plays"]), 6)
            for play_index in entry["plays"]:
                _flags, chains = lib.play_chains(body, play_index)
                self.assertEqual([n[0] for n in chains[0][1]], [0x1B, 0x0B])
                delay = codec.decode_operands(0x0B, struct.unpack_from("<I", chains[0][1][1], 4)[0])[2]
                self.assertAlmostEqual(delay, 4.0, places=3)
                self.assertFalse(any(n[0] in (0x0B, 0x0C) for slot in range(1, 11) for n in chains[slot][1]))

    def test_every_play_validates_and_retail_plays_are_ai_excluded(self) -> None:
        body = self.built[0x20:]
        parsed = parse_playbook_resource(self.built, asset_id="PRACTICE")
        for play in parsed.plays:
            flags, chains = lib.play_chains(body, play.index)
            self.assertIsNone(codec.validate_play(flags, chains), play.name)
        self.assertTrue(all(p.flags_or_id & 0x400000 for p in parsed.plays[:27]))
        self.assertFalse(any(p.flags_or_id & 0x400000 for p in parsed.plays[27:]))
        retail_parsed = parse_playbook_resource(self.retail, asset_id="PRACTICE")
        for before, after in zip(retail_parsed.plays, parsed.plays[:27]):
            self.assertEqual(before.name, after.name)
            self.assertEqual(before.flags_or_id | 0x400000, after.flags_or_id)
        self.assertEqual([c.name for c in parsed.categories[11:]], [name for name, _i, _r in book.CATEGORIES])
        self.assertEqual(len([p for p in parsed.plays if p.name.startswith("7v7")]), 15)

    def test_foreign_and_applied_books_are_told_apart(self) -> None:
        broken = bytearray(self.built)
        broken[0x20 + 0x33FC + 27 * 0x60 + 4] ^= 0x40
        self.assertEqual(book.resource_status(bytes(broken)), "foreign")
        self.assertEqual(book.resource_status(self.retail[:100]), "foreign")

    def test_archive_write_path_refuses_and_verifies(self) -> None:
        original = book._outer_image
        _FakeArchive.store = bytearray(self.retail)
        book._outer_image = lambda: _FakeArchive
        try:
            self.assertEqual(book.status("fake.iso"), "retail")
            receipt = book.apply("fake.iso")
            self.assertEqual(receipt["status"], "applied")
            self.assertEqual(bytes(_FakeArchive.store), self.built)
            self.assertEqual(book.status("fake.iso"), "applied")
            self.assertTrue(book.apply("fake.iso").get("already_applied"))
            _FakeArchive.store[0x20 + 0x33FC + 4] ^= 0x40          # a retail play loses its AI-excluded flag: foreign
            with self.assertRaises(book.SevenOnSevenBookError):
                book.apply("fake.iso")
        finally:
            book._outer_image = original


if __name__ == "__main__":
    unittest.main()

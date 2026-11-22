"""b81 helmet sides (b): the late owner nfl2k5_helmet_side_numbers (kit helmet-number route 5 binds set E).

Pure cases need no game files: the owner's table, string, sites, requests and memory-budget rows. The executable cases
skip without the pinned USA retail default.xbe (NFL2K5_RETAIL_EXTRACTION) or the beta 81 base build bda1e4a4
(NFL2K5_B81_BASE_XBE, else $NFL2K5_B81_STABILITY_FIXTURES/default.xbe); game binaries are never copied into git.

The emulated cases run the game's own code in Unicorn on the plain and the patched executable: the registration loop
0x909C7..0x90AB6 (its sprintf 0x4A410 and name compare 0x30C40 included) over a synthetic model whose materials are
named NUMBER_*, NUMBER_helmet_D_* and, or not, NUMBER_helmet_E_*, then the player builder's helmet-number block
0x8F02E..0x8F062 (route call 0x8E830, the selector 0x8E910 and the binder, retail or Number kerning's) for routes 1..5.
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_helmet_side_numbers as hsn  # noqa: E402
from mod_editor.core import nfl2k5_memory_budget as mb  # noqa: E402
from mod_editor.core import nfl2k5_number_kerning as nk  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage  # noqa: E402

try:
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_WRITE
    from unicorn import x86_const as X
except ImportError:  # pragma: no cover - the emulator is optional on lean hosts
    Uc = None

BASE_SHA256 = "bda1e4a408f19cc30f0916e03b158b0accc46e0ccb6a39e134c1ce79ba3ab6ea"   # b81 base build at d8ceb91e3
RETAIL_ROUTE_ROWS = (1, 1, 2, 3, 4, 0)                                            # [0x4EF874..0x4EF88C) in retail
ROWS_VA, ROWS_END = 0xA86D68, 0xA86E48                                            # row records 0..13


def _read_pinned(path: Path, digest: str) -> bytes | None:
    if not path.is_file() or path.stat().st_size > 16 * 1024 ** 2:
        return None
    payload = path.read_bytes()
    return payload if hashlib.sha256(payload).hexdigest() == digest else None


def retail_xbe() -> bytes:
    roots = [os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"),
             str(ROOT / "extracted")]
    for root in roots:
        payload = _read_pinned(Path(root) / "ESPN NFL 2K5 (USA)" / "default.xbe", RETAIL_SHA256)
        if payload:
            return payload
    raise unittest.SkipTest("the pinned USA retail default.xbe is absent")


def base_xbe() -> bytes:
    named = os.environ.get("NFL2K5_B81_BASE_XBE", "")
    fixtures = os.environ.get("NFL2K5_B81_STABILITY_FIXTURES", "")
    for candidate in (named, fixtures and str(Path(fixtures) / "default.xbe")):
        if candidate:
            payload = _read_pinned(Path(candidate), BASE_SHA256)
            if payload:
                return payload
    raise unittest.SkipTest("the b81 base default.xbe bda1e4a4 is absent (NFL2K5_B81_BASE_XBE)")


def repin(payload: bytes, va: int, content: bytes) -> bytes:
    """Rewrite native bytes and keep every section digest valid (a foreign but well-formed executable)."""
    out = bytearray(payload)
    at = XbeImage(payload).offset(va, len(content))
    out[at:at + len(content)] = content
    for section in _sections(out):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(out, section)
    return bytes(out)


def read(payload: bytes, va: int, size: int) -> bytes:
    return XbeImage(payload).read(va, size)


# ------------------------------------------------------------------------------------------------ pure


class OwnerShapeTests(unittest.TestCase):

    def test_identity_and_requests(self):
        self.assertEqual(hsn.OWNER, "nfl2k5_helmet_side_numbers")
        self.assertEqual(hsn.ROUTE, 5)
        self.assertEqual(hsn.ROW_FORMAT, "NUMBER_helmet_E_%c")
        self.assertEqual(hsn.REQUESTS, ((hsn.OWNER, "code", hsn.CODE_SIZE, 16), (hsn.OWNER, "data", hsn.DATA_SIZE, 16)))
        self.assertIn(hsn.OWNER, space.LATE_OWNERS)
        self.assertEqual(space.LATE_OWNERS[-1], hsn.OWNER)          # after every other late owner: it moves none

    def test_row_record_address(self):
        for data_va in (0x14F2000, 0x14F2FE0, 0x152D0C0):
            row = hsn.row_va(data_va)
            self.assertEqual(row, data_va + 8)
            self.assertEqual(row % 16, ROWS_VA % 16)
            self.assertGreater(row, 0xA86E38)                        # the loop's signed bound falls out after it
            self.assertEqual(hsn.row_index(row) * 16 + ROWS_VA, row)
            self.assertGreater(hsn.row_index(row), 13)
        with self.assertRaises(ValueError):
            hsn.row_va(0x14F2008)                                    # the data allocation is 16-aligned

    def test_table_string_and_cave(self):
        code_va, data_va = 0x14DA100, 0x14F2010
        code = hsn.code_for(code_va, data_va)
        self.assertEqual(len(code), hsn.CODE_SIZE)
        table = struct.unpack_from("<6I", code, hsn.table_va(code_va) - code_va)
        k = hsn.row_index(hsn.row_va(data_va))
        self.assertEqual(table[:5], RETAIL_ROUTE_ROWS[:5])           # routes 0..4 map exactly as in retail
        self.assertEqual(table[5], k)
        self.assertNotEqual(table[5], 0)                             # route 5 never maps to row 0 (NUMBER_%c)
        at = hsn.format_va(code_va) - code_va
        self.assertEqual(code[at:at + 38], "NUMBER_helmet_E_%c\0".encode("utf-16le"))
        # the cave: first fall-out -> our row, re-entering the retail loop body; second -> the displaced push
        self.assertEqual(code[:9], bytes.fromhex("8b442418" "3d486ea800"))
        self.assertIn(b"\xc7\x44\x24\x18" + struct.pack("<I", hsn.row_va(data_va)), code)
        self.assertIn(b"\x8d\x84\x40" + struct.pack("<I", hsn.row_va(data_va) + 4), code)
        self.assertIn(bytes.fromhex("681056e600"), code)

    def test_sites(self):
        code_va = 0x14DA100
        sites = {label: (va, before, after) for label, va, before, after in hsn.sites(code_va)}
        self.assertEqual(set(sites), {"route_table", "registration_tail"})
        va, before, after = sites["route_table"]
        self.assertEqual((va, before), (0x8F041, bytes.fromhex("8b0c8d74f84e00")))
        self.assertEqual(after, bytes.fromhex("8b0c8d") + struct.pack("<I", hsn.table_va(code_va)))
        va, before, after = sites["registration_tail"]
        self.assertEqual((va, before), (0x90AB1, bytes.fromhex("681056e600")))
        self.assertEqual(after, b"\xe9" + struct.pack("<i", code_va - 0x90AB6))
        # 0x4EF888 (route 5's retail row, also the first dword of the table read at 0x8F8D6) is never written
        self.assertFalse(any(v <= 0x4EF888 < v + len(b) for v, b, _a in sites.values()))

    def test_memory_budget_rows(self):
        key = hsn.OWNER[len("nfl2k5_"):]
        self.assertEqual(mb.LEGACY_REQUESTS[key], tuple(r[1:] for r in hsn.REQUESTS))
        self.assertEqual(mb.OWNER_BYTES[key], (hsn.CODE_SIZE, 0, 0, 0, hsn.DATA_SIZE))
        self.assertEqual(mb.OWNER_FIELDS[key], (hsn.BUILD_KEY,))
        self.assertNotIn(key, mb.owners(mb.rc_plan()))               # the v0.9 pack plan does not carry it


# ------------------------------------------------------------------------------------------------ bytes


class RetailExecutableTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.applied, cls.receipt = hsn.apply(cls.retail)

    def test_retail_status_and_apply(self):
        self.assertEqual(hsn.status(self.retail), "retail")
        self.assertEqual(hsn.status(self.applied), "applied")
        self.assertEqual(space.status(self.applied), "applied")
        self.assertEqual(nk.status(self.applied), "retail")
        found = hsn.allocation(self.applied)
        code_va, data_va = found["code"]["va"], found["data"]["va"]
        row = hsn.row_va(data_va)
        self.assertEqual(read(self.applied, code_va, hsn.CODE_SIZE), hsn.code_for(code_va, data_va))
        self.assertEqual(read(self.applied, data_va, hsn.DATA_SIZE), bytes(hsn.DATA_SIZE))   # zero-initialised data
        self.assertEqual(read(self.applied, 0x8F041, 7), bytes.fromhex("8b0c8d") + struct.pack("<I", hsn.table_va(code_va)))
        self.assertEqual(read(self.applied, 0x4EF874, 24), read(self.retail, 0x4EF874, 24))  # retail table untouched
        self.assertEqual(struct.unpack("<6I", read(self.applied, hsn.table_va(code_va), 24)),
                         (1, 1, 2, 3, 4, hsn.row_index(row)))
        settings = hsn.read_settings(self.applied)
        self.assertEqual((settings["status"], settings["route"], settings["row"]), ("applied", 5, hsn.row_index(row)))
        self.assertEqual(self.receipt["status"], "applied")
        self.assertFalse(self.receipt["already_applied"])
        self.assertEqual(self.receipt["row_va"], hex(row))
        self.assertTrue(XbeImage(self.applied).section(data_va, hsn.DATA_SIZE).flags & 1)    # writable at run time

    def test_only_the_two_sites_change_in_the_retail_sections(self):
        plain, _ = space.apply(self.retail, hsn.REQUESTS, scaleout=True)         # the same reservation, empty
        self.assertEqual(hsn.status(plain), "retail")
        applied, _ = hsn.apply(plain)
        self.assertEqual(applied, self.applied)                                  # reserve-then-fill = one step
        image = XbeImage(plain)
        changed = []
        for section in image.sections:
            if section.start >= 0x14B0000 or not section.raw_size:
                continue
            a, b = read(plain, section.start, section.raw_size), read(applied, section.start, section.raw_size)
            changed += [section.start + i for i in range(len(a)) if a[i] != b[i]]
        self.assertTrue(changed)
        self.assertTrue(all(0x8F044 <= va < 0x8F048 or 0x90AB1 <= va < 0x90AB6 for va in changed), [hex(v) for v in changed])

    def test_idempotent(self):
        again, receipt = hsn.apply(self.applied)
        self.assertEqual(again, self.applied)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(receipt["changed_bytes"], 0)

    def test_remove_is_the_exact_inverse_of_the_fill(self):
        plain, _ = space.apply(self.retail, hsn.REQUESTS, scaleout=True)
        removed, receipt = hsn.remove(self.applied)
        self.assertEqual(removed, plain)                                         # byte-exact, allocation kept
        self.assertEqual(hsn.status(removed), "retail")
        self.assertFalse(receipt["already_retail"])
        self.assertEqual(hsn.remove(plain)[0], plain)
        self.assertEqual(hsn.remove(self.retail)[0], self.retail)
        self.assertEqual(hsn.apply(removed)[0], self.applied)

    def test_guards_refuse_foreign_bytes(self):
        cases = {
            "route table site": (0x8F044, struct.pack("<I", 0x4EF870)),
            "registration hook site": (0x90AB1, bytes.fromhex("90" * 5)),
            "loop body": (0x90A00, bytes.fromhex("8b4c2410")),
            "loop bound": (0x90A9F, struct.pack("<I", 0xA86E28)),
            "helmet family": (0x8F059, b"\x0e"),
            "helmet route call": (0x8F02E, bytes.fromhex("e9000000")),      # a Guardian-style bind hook
            "route getter": (0x8E837, bytes.fromhex("8b4108")),
            "retail route rows": (0x4EF878, struct.pack("<I", 2)),
            "letters": (0x4EEF60, "X".encode("utf-16le")),
            "selector immediate": (0x8E95B, struct.pack("<I", 0xA86D6E)),
        }
        for name, (va, content) in cases.items():
            with self.subTest(name):
                foreign = repin(self.retail, va, content)
                self.assertEqual(hsn.status(foreign), "foreign")
                with self.assertRaises(ValueError):
                    hsn.apply(foreign)
        # installed: a foreign cave byte, table entry or site
        found = hsn.allocation(self.applied)
        code_va = found["code"]["va"]
        for name, (va, content) in {"cave": (code_va + 1, b"\x00"),
                                    "table": (hsn.table_va(code_va) + 20, struct.pack("<I", 0)),
                                    "string": (hsn.format_va(code_va) + 30, b"F"),
                                    "hook": (0x90AB2, b"\x00")}.items():
            with self.subTest(name):
                self.assertEqual(hsn.status(repin(self.applied, va, content)), "foreign")

    def test_commutes_with_number_kerning(self):
        kerned, _ = nk.apply(self.retail)
        one, _ = hsn.apply(kerned)
        two, _ = nk.apply(self.applied)
        self.assertEqual(one, two)
        self.assertEqual((hsn.status(one), nk.status(one)), ("applied", "applied"))

    def test_after_hair_styles_and_number_scale(self):
        from mod_editor.core import nfl2k5_hair_styles as hs
        from mod_editor.core import nfl2k5_team_number_scale as ns
        payload, _ = hs.apply(self.retail)
        payload, _ = ns.apply(payload, {"13H0": 1.08})
        payload, _ = nk.apply(payload)
        result, _ = hsn.apply(payload)
        self.assertEqual((hs.status(result), ns.status(result), nk.status(result), hsn.status(result)),
                         ("applied", "applied", "applied", "applied"))
        before = [a for a in space.layout(payload)["allocations"] if a["owner"] != space.DIRECTORY_OWNER]
        after = [a for a in space.layout(result)["allocations"] if a["owner"] != space.DIRECTORY_OWNER]
        self.assertTrue(all(a in after for a in before))                         # nothing moved


class BaseExecutableTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.base = base_xbe()
        cls.applied, cls.receipt = hsn.apply(cls.base)

    def test_apply_on_the_installed_base(self):
        from mod_editor.core import nfl2k5_hair_styles as hs
        from mod_editor.core import nfl2k5_team_number_scale as ns
        self.assertEqual(hsn.status(self.base), "retail")
        self.assertEqual(hsn.status(self.applied), "applied")
        for owner in (hs, ns, nk):                                               # each keeps its own state
            self.assertEqual(owner.status(self.applied), owner.status(self.base), owner.__name__)
        self.assertEqual((ns.status(self.applied), nk.status(self.applied)), ("applied", "applied"))
        before = [a for a in space.layout(self.base)["allocations"] if a["owner"] != space.DIRECTORY_OWNER]
        after = [a for a in space.layout(self.applied)["allocations"] if a["owner"] != space.DIRECTORY_OWNER]
        self.assertTrue(all(a in after for a in before))                         # every existing owner stays put
        added = [a for a in after if a not in before]
        self.assertEqual(sorted((a["owner"], a["kind"]) for a in added), [(hsn.OWNER, "code"), (hsn.OWNER, "data")])
        found = hsn.allocation(self.applied)
        section = XbeImage(self.applied).section(found["data"]["va"], hsn.DATA_SIZE)
        self.assertTrue(section.flags & 1, "the row record must be in a writable section")
        self.assertEqual(hsn.apply(self.applied)[0], self.applied)
        removed, _ = hsn.remove(self.applied)
        self.assertEqual(hsn.status(removed), "retail")
        self.assertEqual(hsn.apply(removed)[0], self.applied)


# ------------------------------------------------------------------------------------------------ emulated

WORK, WORK_SIZE = 0x3000000, 0x200000
STACK, STACK_SIZE = 0x3400000, 0x40000
MODEL, RECORD, UNIF, MATS, NAMES = WORK + 0x100, WORK + 0x200, WORK + 0x300, WORK + 0x1000, WORK + 0x100000
TEXTURE = 0x70000000
SENTINEL = struct.pack("<8xI20x4fI", 0x80000001, 1.5, 1.5, 0.25, 0.25, 0x11111111)
LO_BODY = ["BODY", "NUMBER_L", "NUMBER_M", "NUMBER_R", "NECKROLL4_NUMBER_M", "NUMBER_helmet_D_L", "NUMBER_helmet_D_M",
           "NUMBER_helmet_D_R", "SKIN", "NUMBER_helmet_E_M", "NUMBER_helmet_E_R", "NUMBER_helmet_E_L"]
HI_HEAD = ["HEAD", "FACEMASK"] + [f"NUMBER_helmet_{s}_{c}" for s in "ABCD" for c in "LMR"] + [
    "HAIR_dreads", "NUMBER_helmet_E_R", "NUMBER_helmet_E_L", "NUMBER_helmet_E_M"]
REG_START, REG_STOP = 0x909C7, 0x90AB6
HELMET_START, HELMET_STOP = 0x8F02E, 0x8F062
REGS = ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP", "ESP")
COMPARED = ("EAX", "ECX", "EDX", "ESI", "EBP", "ESP")


class Machine:
    """The executable's sections at their addresses, a synthetic model and player, and a stack."""

    def __init__(self, payload: bytes, names: list[str]):
        image = XbeImage(payload)
        self.mu = mu = Uc(UC_ARCH_X86, UC_MODE_32)
        end = (image.base + image.image_size + 0xFFFF) & ~0xFFFF
        mu.mem_map(0x10000, end - 0x10000)
        mu.mem_write(0x10000, payload[:image.headers_size])
        for s in image.sections:
            if s.raw_size:
                mu.mem_write(s.start, payload[s.raw:s.raw + min(s.raw_size, s.size)])
        mu.mem_map(WORK, WORK_SIZE)
        mu.mem_map(STACK, STACK_SIZE)
        for fam in range(3):                         # a distinct texture handle per (family, digit, slot)
            for digit in range(10):                  # (slot 2 of the last digit would be row 0's format pointer)
                for slot in range(2):
                    mu.mem_write(0xA86C04 + 4 * (3 * (fam * 10 + digit) + slot),
                                 struct.pack("<I", TEXTURE + fam * 1000 + digit * 10 + slot))
        self.names = names
        at = NAMES
        for i, name in enumerate(names):
            mu.mem_write(at, (name + "\0").encode("utf-16le"))
            mu.mem_write(MATS + 0x80 * i, struct.pack("<I", at) + SENTINEL[4:].ljust(0x7C, b"\0"))
            at += 0x100
        mu.mem_write(MODEL + 0x1C, struct.pack("<II", len(names), MATS))
        mu.mem_write(0xB652B0, struct.pack("<I", UNIF))
        self.writes: list[tuple[int, int]] = []
        mu.hook_add(UC_HOOK_MEM_WRITE, lambda _u, _a, address, size, _v, _d: self.writes.append((address, size)))

    def reg(self, name):
        return self.mu.reg_read(getattr(X, "UC_X86_REG_" + name))

    def outside(self, *ranges):
        """Writes that land outside the stack and the given [start, end) ranges."""
        allowed = [(STACK, STACK + STACK_SIZE), *ranges]
        return sorted({hex(a) for a, n in self.writes if not any(lo <= a and a + n <= hi for lo, hi in allowed)})

    def register(self, model_row: int):
        """Run the retail registration loop (and the owner's cave) for one model row; return the exit state."""
        mu = self.mu
        esp = STACK + 0x20000
        mu.mem_write(esp, bytes(0x200))
        mu.mem_write(esp + 0x20, struct.pack("<I", model_row))
        for name, value in zip(REGS, (0xAAAA0001, 0xBBBB0002, 0xCCCC0003, 0xDDDD0004, MODEL, 0xEEEE0006, 0xFFFF0007, esp)):
            mu.reg_write(getattr(X, "UC_X86_REG_" + name), value)
        self.writes.clear()
        mu.emu_start(REG_START, REG_STOP, count=2_000_000)
        self.assert_at(REG_STOP)
        esp = self.reg("ESP")
        return {name: self.reg(name) for name in REGS}, bytes(mu.mem_read(esp, 0x5C))

    def helmet(self, model_row: int, number: int, route: int):
        """Run the player builder's helmet-number block for slot 0; return the materials afterwards."""
        mu = self.mu
        mu.mem_write(MATS, b"".join(bytes(mu.mem_read(MATS + 0x80 * i, 4)) + SENTINEL[4:].ljust(0x7C, b"\0")
                                    for i in range(len(self.names))))
        mu.mem_write(UNIF + 0x0C, struct.pack("<I", route))
        mu.mem_write(RECORD + 0x20, struct.pack("<I", number << 3))
        ebp = STACK + 0x30000
        mu.mem_write(ebp - 0x40, bytes(0x80))
        mu.mem_write(ebp + 8, struct.pack("<I", model_row))
        for name, value in (("EBP", ebp), ("ESP", ebp - 0x100), ("EBX", RECORD), ("EDI", MODEL)):
            mu.reg_write(getattr(X, "UC_X86_REG_" + name), value)
        self.writes.clear()
        mu.emu_start(HELMET_START, HELMET_STOP, count=10_000)
        self.assert_at(HELMET_STOP)
        return [bytes(mu.mem_read(MATS + 0x80 * i, 0x80)) for i in range(len(self.names))]

    def assert_at(self, va):
        if self.reg("EIP") != va:
            raise AssertionError(f"emulation stopped at {self.reg('EIP'):#x}, not {va:#x}")


def _bound(record: bytes, digit: int) -> bool:
    flags, su, sv, tex = struct.unpack_from("<I", record, 8)[0], *struct.unpack_from("<2f", record, 0x20), \
        struct.unpack_from("<I", record, 0x30)[0]
    return not flags & 1 and (su, sv) == (4.0, 2.0) and tex == TEXTURE + 1000 + digit * 10


@unittest.skipIf(Uc is None, "unicorn is not installed")
class EmulatedTests(unittest.TestCase):
    """Registration and binding on retail and on the base (Number kerning, Jersey number sizes, Hair styles on)."""

    def payloads(self):
        out = []
        for label, loader in (("retail", retail_xbe), ("base", base_xbe)):
            try:
                plain = loader()
            except unittest.SkipTest:
                continue
            out.append((label, plain, hsn.apply(plain)[0]))
        if not out:
            self.skipTest("neither the retail nor the base default.xbe is present")
        return out

    def check(self, label, plain, patched, names, model_row):
        with_e = any(n.startswith("NUMBER_helmet_E_") for n in names)
        settings = hsn.read_settings(patched)
        row_va = int(settings["row_va"], 16)
        a, b = Machine(plain, names), Machine(patched, names)
        # the other model rows first, so the row under test is registered last and the earlier ones must survive it
        for other in (r for r in (0, 1, 2) if r != model_row):
            a.register(other), b.register(other)
        state_a, frame_a = a.register(model_row)
        state_b, frame_b = b.register(model_row)
        # ebx and edi hold the last name search's scratch (rewritten at 0x90AE6/0x90AEA/0x90AF1 before any read)
        self.assertEqual({r: state_a[r] for r in COMPARED}, {r: state_b[r] for r in COMPARED}, f"{label}: exit registers")
        self.assertEqual(frame_a, frame_b, f"{label}: exit frame below the name buffer")
        rows_a = bytes(a.mu.mem_read(ROWS_VA, ROWS_END - ROWS_VA))
        rows_b = bytes(b.mu.mem_read(ROWS_VA, ROWS_END - ROWS_VA))
        self.assertEqual(rows_a, rows_b, f"{label}: rows 0..13")
        self.assertEqual(a.outside((ROWS_VA, ROWS_END)), [])
        self.assertEqual(b.outside((ROWS_VA, ROWS_END), (row_va, row_va + 16)), [])
        record = bytes(b.mu.mem_read(row_va, 16))
        self.assertEqual(struct.unpack_from("<I", record)[0], int(settings["format_va"], 16))
        cells = record[4:]
        for m in range(4):
            got = cells[3 * m:3 * m + 3]
            if m <= 2:                                                   # registered (the same synthetic model)
                want = bytes(names.index(f"NUMBER_helmet_E_{c}") if with_e else 0xFF for c in "LMR")
            else:
                want = b"\xff\xff\xff"                                   # never registered: unbound, not material 0
            self.assertEqual(got, want, f"{label}: E cells of model row {m}")
        # binding: routes 1..4 exactly as retail; route 5 binds E only (or nothing), never a row-0 material
        e_index = {c: names.index(f"NUMBER_helmet_E_{c}") for c in "LMR" if f"NUMBER_helmet_E_{c}" in names}
        for number in (7, 87, 10):
            for route in (1, 2, 3, 4):
                self.assertEqual(a.helmet(model_row, number, route), b.helmet(model_row, number, route),
                                 f"{label}: route {route} number {number}")
            after = b.helmet(model_row, number, 5)
            self.assertEqual(b.outside((MATS, MATS + 0x80 * len(names))), [])
            digits = {"M": number} if number < 10 else {"L": number // 10, "R": number % 10}
            want = {e_index[c]: d for c, d in digits.items() if c in e_index}
            for i, rec in enumerate(after):
                untouched = rec[4:] == SENTINEL[4:].ljust(0x7C, b"\0")
                if i in want:
                    self.assertTrue(_bound(rec, want[i]), f"{label}: {names[i]} bound for {number}")
                else:
                    self.assertTrue(untouched, f"{label}: route 5 wrote {names[i]} for {number}")
            plain_after = a.helmet(model_row, number, 5)
            if model_row == 0 and number < 10:                           # retail's route 5: the jersey number cell
                self.assertTrue(_bound(plain_after[names.index("NUMBER_M")], number))

    def test_route5_binds_set_e(self):
        for label, plain, patched in self.payloads():
            for model_row, names in ((0, LO_BODY), (2, HI_HEAD)):
                with self.subTest(label=label, model_row=model_row, e=True):
                    self.check(label, plain, patched, names, model_row)
                bare = [n for n in names if not n.startswith("NUMBER_helmet_E_")]
                with self.subTest(label=label, model_row=model_row, e=False):
                    self.check(label, plain, patched, bare, model_row)


if __name__ == "__main__":
    unittest.main()

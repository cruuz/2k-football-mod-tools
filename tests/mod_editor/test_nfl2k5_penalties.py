"""Penalties at NFL rates + the Chop Block toggle: profile shape, retail round trip, emulation, cave rules.

Shape tests need nothing; the retail tests read the extracted default.xbe; the emulation tests run the
game's own curve interpolator (FUN_001b0ae0) and the penalty enable pass (FUN_000b1440) under unicorn on
the retail and the patched executable."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mod_editor.core import nfl2k5_penalties as pen  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
BASE = 0x10000
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


class ShapeTests(unittest.TestCase):
    def test_every_profile_keeps_every_count_and_every_x(self) -> None:
        for name in pen.PROFILES:
            pairs = pen.profile_pairs(name)
            self.assertEqual(set(pairs), set(pen.RETAIL_PAIRS))
            for key, knots in pairs.items():
                retail = pen.RETAIL_PAIRS[key]
                self.assertEqual(len(knots), len(retail), key)
                self.assertEqual(len(knots), pen.TABLE_COUNTS[key], key)
                xs = [x for x, _y in knots]
                self.assertEqual(xs, sorted(xs), key)
                self.assertEqual(len(set(xs)), len(xs), f"{key}: x must be strictly ascending")
                self.assertEqual([_f32(x) for x in xs], [x for x, _y in retail], f"{key}: x must stay retail")
                self.assertTrue(all(y >= 0 for _x, y in knots), key)

    def test_the_nfl_profile_moves_the_default_knot_the_right_way(self) -> None:
        new, old = pen.profile_pairs("nfl"), pen.RETAIL_PAIRS

        def at(table, pairs, x):
            return next(y for kx, y in pairs[table] if abs(kx - x) < 1e-6)

        self.assertAlmostEqual(at("off_holding", new, 0.5), 0.20)                       # x2 at the default
        self.assertLess(at("def_holding", new, 0.5), at("def_holding", old, 0.5))
        self.assertLess(at("clipping", new, 0.5), at("clipping", old, 0.5))
        self.assertLess(at("face_mask", new, 0.5), at("face_mask", old, 0.5))
        self.assertLess(at("roughing", new, 0.5), at("roughing", old, 0.5))               # shorter grace window
        self.assertLess(at("late_hit", new, 0.5), at("late_hit", old, 0.5))
        self.assertAlmostEqual(at("inel_downfield", new, 0.5), 274.32)                    # 3 yd
        # end knots keep the retail extremes so the slider still spans a range
        for key in ("off_holding", "def_holding", "clipping", "roughing", "late_hit", "inel_downfield"):
            self.assertEqual(_f32(new[key][0][1]), old[key][0][1], key)
            self.assertEqual(_f32(new[key][-1][1]), old[key][-1][1], key)
        # windows and thresholds never loosen as the slider rises
        for key in ("roughing", "late_hit", "inel_downfield", "face_mask"):
            ys = [y for _x, y in new[key]]
            self.assertEqual(ys, sorted(ys, reverse=True), key)
        for key in ("dpi", "dpi_radius", "nzi"):
            self.assertEqual(new[key], old[key], f"{key} is kept")

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_the_stub_reads_the_toggle_and_jumps_to_the_store(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        text = [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(pen.PATCHED_HOST, pen.HOST_VA)]
        self.assertEqual(text[:2], [f"mov eax, dword ptr [0x{pen.CHOP_BLOCK_TOGGLE_VA:x}]", f"jmp 0x{pen.STORE_VA:x}"])
        self.assertEqual(text[2:], ["int3"] * (pen.HOST_SIZE - pen.STUB_SIZE))
        self.assertEqual(pen.STUB_SIZE, 10)
        self.assertEqual(pen.HOST_SIZE, 16)
        self.assertEqual(pen.PATCHED_CASE10_ENTRY, struct.pack("<I", pen.HOST_VA))
        self.assertEqual(pen.RETAIL_CASE10_ENTRY, struct.pack("<I", pen.RETAIL_CASE10_TARGET))
        self.assertEqual(pen.CASE10_ENTRY_VA, pen.ENABLE_JUMP_TABLE_VA + (pen.IDX_CHOP_BLOCK - 1) * 4)

    def test_validate_profile_refuses_bad_shapes(self) -> None:
        good = {"late_hit": [(0.0, 2.0), (0.5, 0.8), (1.0, 0.1)]}
        self.assertEqual(pen.validate_profile(good)["late_hit"], ((0.0, 2.0), (0.5, 0.8), (1.0, 0.1)))
        for bad in ({"late_hit": [(0.0, 2.0), (1.0, 0.1)]},               # count
                    {"late_hit": [(0.0, 2.0), (0.6, 0.8), (1.0, 0.1)]},   # x moved
                    {"late_hit": [(0.0, 2.0), (0.5, -0.8), (1.0, 0.1)]},  # negative
                    {"late_hit": [(0.0, 2.0), (0.5, float("nan")), (1.0, 0.1)]},
                    {"holding": [(0.0, 0.0)]}):                            # unknown table
            with self.assertRaises(pen.PenaltiesError):
                pen.validate_profile(bad)
        with self.assertRaises(pen.PenaltiesError):
            pen.load_profile("madden")

    def test_a_json_profile_loads_and_only_its_tables_become_sites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mine.json"
            path.write_text(json.dumps({"name": "mine", "tables": {"late_hit": [[0.0, 2.0], [0.5, 0.5], [1.0, 0.1]]}}))
            name, tables = pen.load_profile(path)
            self.assertEqual((name, set(tables)), ("mine", {"late_hit"}))
            labels = [label for label, _va, _b, _a in pen.sites(path)]
            self.assertEqual(labels, ["curve_late_hit", "incidental_facemask_yards", "chop_block_case_entry", "chop_block_stub_host"])
            self.assertEqual(len(pen.kept_tables(path)), len(pen.TABLES) - 1)
            path.write_text(json.dumps({"tables": {}}))
            with self.assertRaises(pen.PenaltiesError):
                pen.load_profile(path)

    def test_a_payload_without_sections_is_foreign(self) -> None:
        self.assertEqual(pen.status(b"XBEH" + b"\0" * 0x200), "foreign")
        with self.assertRaises(pen.PenaltiesError):
            pen.apply(b"XBEH" + b"\0" * 0x200)


@unittest.skipUnless(XBE.is_file(), "retail extraction not present")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = pen.apply(cls.retail)

    def _off(self, va: int) -> int:
        return rdata.offset_of(self.retail, va)

    def test_decode_round_trip_is_byte_exact(self) -> None:
        decoded = pen.decode_tables(self.retail)
        self.assertEqual(decoded, dict(pen.RETAIL_PAIRS))
        for key, _label, va, _unit, hexpairs in pen.TABLES:
            off = self._off(va)
            self.assertEqual(self.retail[off - 4: off + len(decoded[key]) * 8],
                             struct.pack("<I", len(decoded[key])) + bytes.fromhex(hexpairs), key)
            self.assertEqual(pen._encode_pairs(decoded[key]), bytes.fromhex(hexpairs), key)

    def test_status_apply_idempotent_and_foreign(self) -> None:
        self.assertEqual(pen.status(self.retail), "retail")
        self.assertEqual(pen.status(self.patched), "applied")
        self.assertEqual(self.receipt["changed_bytes"], sum(1 for a, b in zip(self.retail, self.patched) if a != b))
        self.assertGreater(self.receipt["changed_bytes"], 0)
        self.assertEqual(self.receipt["profile"], "nfl")
        self.assertTrue(self.receipt["estimated"])
        again, receipt2 = pen.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt2.get("already_applied"))
        for label, va, _before, _after in pen.sites():          # a byte off in any site: foreign, refused
            for base in (self.retail, self.patched):
                tampered = bytearray(base)
                tampered[self._off(va) + 1] ^= 0x01
                self.assertEqual(pen.status(bytes(tampered)), "foreign", label)
        with self.assertRaises(pen.PenaltiesError):
            pen.apply(bytes(tampered))
        for label, va, before, _same in pen.kept_tables():       # a kept table or a count word off: foreign too
            tampered = bytearray(self.retail)
            tampered[self._off(va)] ^= 0x01
            self.assertEqual(pen.status(bytes(tampered)), "foreign", label)
        tampered = bytearray(self.retail)
        tampered[self._off(pen.TABLE_VAS["nzi"]) - 4] = 2
        self.assertEqual(pen.status(bytes(tampered)), "foreign")

    def test_the_patched_executable_carries_the_profile_and_nothing_else(self) -> None:
        wanted = {key: tuple((_f32(x), _f32(y)) for x, y in knots) for key, knots in pen.profile_pairs("nfl").items()}
        self.assertEqual(pen.decode_tables(self.patched), wanted)
        for key, _label, va, _unit, _hex in pen.TABLES:
            off = self._off(va)
            self.assertEqual(self.patched[off - 4: off], self.retail[off - 4: off], f"{key} count word")
        for label, va, before, _same in pen.kept_tables():
            off = self._off(va)
            self.assertEqual(self.patched[off: off + len(before)], before, label)
        yards = self._off(pen.FACEMASK_YARDS_VA)
        self.assertEqual(struct.unpack_from("<f", self.retail, yards)[0], _f32(457.2))
        self.assertEqual(struct.unpack_from("<f", self.patched, yards)[0], _f32(1371.6))
        # the personal-foul record (idx 24) already carried 15 yards: the new value is byte-identical to it
        self.assertEqual(self.patched[yards: yards + 4], self.retail[self._off(pen.record_va(24, pen.RECORD_YARDS_OFFSET)):][:4])
        entry = self._off(pen.CASE10_ENTRY_VA)
        self.assertEqual(struct.unpack_from("<I", self.retail, entry)[0], pen.RETAIL_CASE10_TARGET)
        self.assertEqual(struct.unpack_from("<I", self.patched, entry)[0], pen.HOST_VA)
        self.assertEqual(self.patched[entry - 4: entry], self.retail[entry - 4: entry])      # idx 9 keeps the shared case
        host = self._off(pen.HOST_VA)
        self.assertEqual(self.retail[host: host + pen.HOST_SIZE], pen.RETAIL_HOST)
        self.assertEqual(self.patched[host: host + pen.HOST_SIZE], pen.PATCHED_HOST)
        # every changed byte is inside a declared site or a section digest
        sites = {(self._off(va), self._off(va) + len(after)) for _l, va, _b, after in pen.sites()}
        digests = {(s.header_offset + 36, s.header_offset + 56) for s in _sections(self.retail)}
        for i, (a, b) in enumerate(zip(self.retail, self.patched)):
            if a != b:
                self.assertTrue(any(lo <= i < hi for lo, hi in sites | digests), hex(i))

    def test_section_digests_are_recomputed(self) -> None:
        for section in _sections(self.patched):
            d = section.header_offset + 36
            self.assertEqual(self.patched[d: d + 20], section_digest(self.patched, section), section.index)
        self.assertEqual(sorted(self.receipt["sections_repinned"]), [0, 12, 13])   # .text, .rdata, .data

    def test_order_independence_with_the_other_xbe_patches(self) -> None:
        from mod_editor.core import nfl2k5_position_row as row
        from mod_editor.core import nfl2k5_probowl_order as pb
        from mod_editor.core import nfl2k5_returner_fix as returner
        from mod_editor.core import nfl2k5_team_column as team_column
        from mod_editor.core import nfl2k5_throw_tuning as tt

        a, receipt = tt._apply_all(self.retail, None, catch_slider=False, returner_fix=True, team_column=True,
                                   position_row=True, probowl_order=True, penalties="nfl")
        self.assertEqual(receipt["penalties_patch"]["profile"], "nfl")
        b, _ = pen.apply(self.retail)
        b, _ = pb.apply(b)
        b, _ = team_column.apply(b)
        b, _ = row.apply(b)
        b, _ = returner.apply(b)
        self.assertEqual(a, b)
        self.assertEqual(pen.status(a), "applied")
        again, receipt2 = tt._apply_all(a, None, catch_slider=False, returner_fix=True, team_column=True,
                                        position_row=True, probowl_order=True, penalties="nfl")
        self.assertEqual(again, a)
        self.assertTrue(receipt2["penalties_patch"].get("already_applied"))
        off, _ = tt._apply_all(self.retail, None, catch_slider=False, returner_fix=True, penalties="")
        self.assertEqual(pen.status(off), "retail")

    # -- cave rules ---------------------------------------------------------------------------------
    def _text(self) -> tuple[int, int]:
        text = next(s for s in _sections(self.retail) if s.index == 0)
        return text.virtual_address, text.virtual_address + text.raw_size

    def test_the_stub_host_is_unreferenced_in_the_retail_image(self) -> None:
        """The same scan as tests/mod_editor/test_xbe_patch_cave_references.py, on the whole dead routine: no
        rel32 call/jump target, no push/mov immediate and no aligned .rdata/.data pointer lands on any byte of
        FUN_000b4a60 (0xB4A60..0xB4A8E), entry included."""

        lo, hi = pen.HOST_VA, 0x000B4A8E
        data = self.retail
        text_lo, text_hi = self._text()
        hits = []
        for off in range(text_lo - BASE, text_hi - BASE - 5):
            op = data[off]
            if op in (0xE8, 0xE9):
                tgt = (BASE + off + 5 + struct.unpack_from("<i", data, off + 1)[0]) & 0xFFFFFFFF
            elif op == 0x0F and 0x80 <= data[off + 1] <= 0x8F:
                tgt = (BASE + off + 6 + struct.unpack_from("<i", data, off + 2)[0]) & 0xFFFFFFFF
            else:
                continue
            if lo <= tgt < hi:
                hits.append(("rel", hex(BASE + off), hex(tgt)))
        for section in _sections(data):
            if section.index not in (0, 12, 13):
                continue
            step = 1 if section.index == 0 else 4
            raw, size = section.raw_offset, section.raw_size
            for off in range(raw, raw + size - 4, step):
                v = struct.unpack_from("<I", data, off)[0]
                if not (lo <= v < hi):
                    continue
                if section.index == 0:
                    prev = data[off - 1]
                    if not (prev == 0x68 or 0xB8 <= prev <= 0xBF or (data[off - 2] == 0xC7 and prev == 0x05)
                            or (data[off - 6] == 0xC7 and data[off - 5] == 0x05)):
                        continue
                hits.append(("ptr", section.index, hex(off), hex(v)))
        self.assertEqual(hits, [])
        # the routine really ends at 0xB4A8B (`ret 8`) with nop padding to the next one at 0xB4A90
        self.assertEqual(data[self._off(0xB4A8B): self._off(0xB4A90)], bytes.fromhex("c208009090"))

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_no_neighbouring_instruction_jumps_into_the_host_and_the_stub_writes_nothing(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_IMM, X86_OP_MEM

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        # the routine before the host (0xB4A30..0xB4A52) decoded properly: its `mov esi,[esp+8]` carries a 0x74
        # byte that a byte-granular rel8 sweep would misread as `je +0x24` onto the host
        lo, hi = pen.HOST_VA, pen.HOST_VA + pen.HOST_SIZE
        for insn in md.disasm(self.retail[self._off(0xB4A30): self._off(pen.HOST_VA)], 0xB4A30):
            for op in insn.operands:
                if op.type == X86_OP_IMM and insn.group(1):      # CS_GRP_JUMP
                    self.assertFalse(lo <= op.imm < hi, f"{insn.address:#x} {insn.mnemonic} {insn.op_str}")
        writes = []
        for insn in md.disasm(pen.PATCHED_HOST, pen.HOST_VA):
            if insn.operands and insn.operands[0].type == X86_OP_MEM and insn.mnemonic != "int3":
                writes.append(f"{insn.mnemonic} {insn.op_str}")
        self.assertEqual(writes, [])

    # -- unicorn ------------------------------------------------------------------------------------
    STACK, SENTINEL, SCRATCH = 0x7FF00000, 0x0BADF000, 0x0BADE000

    def _load(self, payload: bytes):
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(BASE, 0xEC0000 - BASE)
        uc.mem_write(BASE, payload[: struct.unpack_from("<I", payload, 0x108)[0]])
        for s in _sections(payload):
            if s.virtual_address + s.raw_size <= 0xEC0000:
                uc.mem_write(s.virtual_address, payload[s.raw_offset: s.raw_offset + s.raw_size])
        uc.mem_map(self.STACK - 0x100000, 0x200000)
        uc.mem_map(self.SCRATCH, 0x2000)
        return uc

    def _interpolate(self, payload: bytes, table: str, x: float) -> float:
        """Call FUN_001b0ae0 exactly as the detectors do: ecx = pairs, edx = count, push x; fstp the result."""
        from unicorn.x86_const import UC_X86_REG_ESP

        uc = self._load(payload)
        code = (b"\xb9" + struct.pack("<I", pen.TABLE_VAS[table])                       # mov ecx, table
                + b"\xba" + struct.pack("<I", pen.TABLE_COUNTS[table])                  # mov edx, count
                + b"\x68" + struct.pack("<f", x))                                       # push x
        call_at = self.SENTINEL + len(code)
        code += b"\xe8" + struct.pack("<i", pen.INTERPOLATOR_VA - (call_at + 5))        # call FUN_001b0ae0
        code += b"\xd9\x1d" + struct.pack("<I", self.SCRATCH)                           # fstp dword [scratch]
        end = self.SENTINEL + len(code)
        uc.mem_write(self.SENTINEL, code)
        uc.reg_write(UC_X86_REG_ESP, self.STACK - 0x1000)
        uc.emu_start(self.SENTINEL, end, count=10_000)
        return struct.unpack("<f", bytes(uc.mem_read(self.SCRATCH, 4)))[0]

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_interpolator_returns_the_new_default_knot(self) -> None:
        self.assertAlmostEqual(self._interpolate(self.retail, "off_holding", 0.5), 0.10, places=6)
        self.assertAlmostEqual(self._interpolate(self.patched, "off_holding", 0.5), 0.20, places=6)
        self.assertAlmostEqual(self._interpolate(self.patched, "off_holding", 0.625), 0.275, places=5)   # lerp 0.5..0.75
        self.assertAlmostEqual(self._interpolate(self.patched, "off_holding", 0.0), 0.0, places=6)
        self.assertAlmostEqual(self._interpolate(self.patched, "off_holding", 1.0), 0.5, places=6)
        self.assertAlmostEqual(self._interpolate(self.patched, "off_holding", 7.0), 0.5, places=6)      # clamps to the end knot
        self.assertAlmostEqual(self._interpolate(self.retail, "face_mask", 0.5), 0.015, places=6)
        self.assertAlmostEqual(self._interpolate(self.patched, "face_mask", 0.5), 0.006, places=6)
        self.assertAlmostEqual(self._interpolate(self.patched, "inel_downfield", 0.6), 274.32, places=2)
        self.assertAlmostEqual(self._interpolate(self.retail, "inel_downfield", 0.6), 457.2, places=2)
        self.assertAlmostEqual(self._interpolate(self.patched, "nzi", 0.5), 0.92, places=6)             # kept

    def _enable_pass(self, payload: bytes, mode: int, chop_toggle: int, clipping: float) -> list[int]:
        """Run FUN_000b1440 and return the 26 runtime enable words."""
        from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP

        uc = self._load(payload)
        uc.mem_write(pen.MODE_VA, struct.pack("<I", mode))
        uc.mem_write(pen.CHOP_BLOCK_TOGGLE_VA, struct.pack("<I", chop_toggle))
        uc.mem_write(pen.CLIPPING_SLIDER_VA, struct.pack("<f", clipping))
        for key in ("false_start", "delay_of_game"):
            uc.mem_write(pen.SETTINGS[key], struct.pack("<I", 1))
        uc.mem_write(pen.SETTINGS["offensive_holding"], struct.pack("<f", 0.5))
        esp = self.STACK - 0x1000
        uc.mem_write(esp, struct.pack("<I", self.SENTINEL))
        uc.mem_write(self.SENTINEL, b"\xf4")                                              # hlt: never reached
        uc.reg_write(UC_X86_REG_ESP, esp)
        uc.emu_start(pen.ENABLE_PASS_VA, self.SENTINEL, count=50_000)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), self.SENTINEL)
        return [struct.unpack("<I", bytes(uc.mem_read(pen.record_va(i, pen.RECORD_ENABLE_OFFSET), 4)))[0]
                for i in range(pen.RECORD_COUNT)]

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_enable_pass_case_10_reads_the_chop_block_toggle(self) -> None:
        idx9, idx10, idx15, idx7 = pen.IDX_CLIPPING, pen.IDX_CHOP_BLOCK, 15, 7
        # retail: chop block follows the Clipping slider, the toggle is ignored
        retail_on = self._enable_pass(self.retail, 4, 0, 0.5)
        retail_off = self._enable_pass(self.retail, 4, 1, 0.0)
        self.assertEqual((retail_on[idx9], retail_on[idx10]), (1, 1))
        self.assertEqual((retail_off[idx9], retail_off[idx10]), (0, 0))
        # patched: chop block follows its own toggle; clipping still follows the slider
        toggle_on = self._enable_pass(self.patched, 4, 1, 0.0)
        toggle_off = self._enable_pass(self.patched, 4, 0, 0.5)
        self.assertEqual((toggle_on[idx9], toggle_on[idx10]), (0, 1))
        self.assertEqual((toggle_off[idx9], toggle_off[idx10]), (1, 0))
        # every other record is decided exactly as retail (same inputs -> same words)
        for retail_words, patched_words in ((retail_on, self._enable_pass(self.patched, 4, 1, 0.5)),
                                            (retail_off, self._enable_pass(self.patched, 4, 0, 0.0))):
            for i in range(pen.RECORD_COUNT):
                if i != idx10:
                    self.assertEqual(patched_words[i], retail_words[i], pen.RECORD_NAMES[i])
        self.assertEqual((toggle_on[idx15], toggle_on[idx7]), (1, 1))            # false start toggle, holding slider
        # practice (mode < 4) still disables everything, toggle or not
        self.assertEqual(self._enable_pass(self.patched, 3, 1, 0.5)[1:], [0] * (pen.RECORD_COUNT - 1))


if __name__ == "__main__":
    unittest.main()

"""b780 st1: an empty kick or punt returner byte no longer reads the neighbouring club's record.

The depth chart reads a team's returner bytes (+0x195 KR1, +0x196 KR2, +0x199 PR, each a roster slot) through
FUN_00242a60 with ``mov eax,[team + slot*4]`` and no check. An empty byte (0xFF, written by the game's own
roster-removal handler 0xC3A90 when the KR1/KR2/PR player is cut or traded, and shipped for three clubs' KR2 in the
v0.8 and v0.9 pack rosters) reads the dword in front of the team record, the previous club's +0x1F0. Retail rosters
keep 0 there ("no player"); the practice-squad metadata (+0x1F2 count, +0x1F3 marker 0xA5) makes it 0xA5NN0000.
The Special Teams page and the KR list then dereference a pointer to nowhere (a page fault: the game freezes), and
the depth re-rank 0x243790 stores roster slot 0 as the returner.

The returner fix's second site rewrites FUN_00242a60 in place: identical results for every valid slot, no player
for a byte that is not a roster slot of the team. Everything below runs the game's own code under Unicorn on the
retail executable, the released v0.8 one and the v0.9 RC (the last two when their fixtures are configured).
"""
from __future__ import annotations

import hashlib
import itertools
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_returner_fix as returner  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402

try:
    from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_UNMAPPED, UC_PROT_ALL
    from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EIP)
    HAVE_UC = True
except ImportError:  # pragma: no cover
    HAVE_UC = False

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XBE", "/nonexistent"))
RELEASED = {"v0.8": os.environ.get("NFL2K5_V08_XBE", ""), "v0.9 RC": os.environ.get("NFL2K5_B780_RC_XBE", "")}

TEAMS, PLAYERS, STACK, OBJ, STOP = 0x02000000, 0x02100000, 0x03000000, 0x02200000, 0x01000000
TEAM_SIZE, PLAYER_SIZE = 0x1F4, 0x54
POSITION = {"QB": 0, "K": 1, "P": 2, "WR": 3, "CB": 4, "FS": 5, "SS": 6, "RB": 7}
ROSTER = ("QB", "CB", "WR", "WR", "RB", "FS", "SS", "CB", "WR", "K")   # slot 0 a quarterback, as franchise rosters often are
PS_TAIL = 0xA5010000          # the previous club's +0x1F0 dword: practice-squad count 1, marker 0xA5
NO_PLAYER_TEXT = 0xE88994     # the depth chart rows' "no player" string
KR, PR = 0xFE, 0xFD
GET_ROW, RERANK, KR_PHOTO, ROW_NAME, ROW_NUMBER = 0x242AE0, 0x243790, 0x242D10, 0x243AC0, 0x243B00
NTH_ROW = 0x242BB0
# return addresses of the row getter's callers: the depth chart draw callbacks and the edit paths (rerank, input)
COLUMN_TEXT = 0x24353E
DRAW_CALLERS = (0x242D48, 0x242E3C, COLUMN_TEXT, 0x24370E)
EDIT_CALLERS = (0x242BBE, 0x242BDB, 0x242C47, 0x242C61, 0x242C78, 0x242C93, 0x2442C3)


def _read(path) -> bytes | None:
    try:
        return Path(path).read_bytes() if path else None
    except OSError:
        return None


class _Machine:
    """The executable's sections, two club records back to back (as in the roster arena) and ten players each.
    One Unicorn instance per executable (mapping it is the slow part); ``reset`` rewrites the whole fixture."""

    _cache: dict = {}

    def __new__(cls, payload: bytes, tail: int, specials: bytes):
        key = hashlib.sha256(payload).hexdigest()
        machine = cls._cache.get(key)
        if machine is None:
            machine = super().__new__(cls)
            machine._map(payload)
            cls._cache[key] = machine
        machine.reset(tail, specials)
        return machine

    def __init__(self, payload: bytes, tail: int, specials: bytes) -> None:
        pass

    def _map(self, payload: bytes) -> None:
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        pages = set()
        sections = _sections(payload)
        for s in sections:
            vsize = struct.unpack_from("<I", payload, s.header_offset + 8)[0]
            pages.update(range(s.virtual_address & ~0xFFF, (s.virtual_address + max(vsize, s.raw_size) + 0xFFF) & ~0xFFF, 0x1000))
        for base, size in ((TEAMS, 0x10000), (PLAYERS, 0x10000), (STACK - 0x10000, 0x20000), (OBJ, 0x1000), (STOP, 0x1000)):
            pages.update(range(base, base + size, 0x1000))
        start = prev = None
        for page in sorted(pages):                  # one mapping per contiguous run of pages
            if start is None:
                start = prev = page
            elif page == prev + 0x1000:
                prev = page
            else:
                uc.mem_map(start, prev + 0x1000 - start, UC_PROT_ALL)
                start = prev = page
        uc.mem_map(start, prev + 0x1000 - start, UC_PROT_ALL)
        for s in sections:
            uc.mem_write(s.virtual_address, payload[s.raw_offset:s.raw_offset + s.raw_size])
        uc.mem_write(STOP, b"\xf4")

    def reset(self, tail: int, specials: bytes) -> None:
        uc = self.uc
        uc.mem_write(TEAMS, bytes(0x10000))
        uc.mem_write(PLAYERS, bytes(0x10000))
        uc.mem_write(OBJ, bytes(0x1000))
        self.players = {}
        for club in range(2):
            team = TEAMS + club * TEAM_SIZE
            for slot, pos in enumerate(ROSTER):
                p = PLAYERS + (club * 16 + slot) * PLAYER_SIZE
                rec = bytearray(PLAYER_SIZE)
                rec[0x35] = POSITION[pos]
                struct.pack_into("<H", rec, 0x28, (1 << 10) | (1 << 13))      # backups: rank 1, side 1
                struct.pack_into("<H", rec, 6, 1000 + club * 100 + slot)      # the face id the photo loader reads
                struct.pack_into("<I", rec, 0x20, (40 + slot) << 3)           # jersey number field
                uc.mem_write(p, bytes(rec))
                uc.mem_write(team + 4 * slot, struct.pack("<I", p))
                self.players[(club, slot)] = p
            uc.mem_write(team + 0x11C, bytes([len(ROSTER)]))
            uc.mem_write(team + 0x194, bytes([0, 2, 3, 9, 1, 3]))         # H, KR1, KR2, K, LS, PR
        self.team = TEAMS + TEAM_SIZE
        uc.mem_write(self.team + 0x194, specials)
        uc.mem_write(TEAMS + 0x1F0, struct.pack("<I", tail))
        # a stale pointer past the player count, as a shrunk slot list can leave
        uc.mem_write(self.team + 4 * 40, struct.pack("<I", self.players[(0, 2)]))
        # depth chart state: page 3 (special teams), scroll 0, this team
        for va, value in ((0xC174B8, 3), (0xC17478, 0), (0xC17480, 0), (0xC1749C, self.team)):
            uc.mem_write(va, struct.pack("<I", value))

    def call(self, va: int, regs: dict, args=()):
        """('returned', eax) or ('fault', address)."""
        uc = self.uc
        esp = STACK - 0x200
        uc.mem_write(esp, struct.pack("<I", STOP) + b"".join(struct.pack("<I", a) for a in args))
        uc.reg_write(UC_X86_REG_ESP, esp)
        for reg, value in regs.items():
            uc.reg_write(reg, value)
        fault = []

        def unmapped(_uc, _access, address, _size, _value, _data):
            fault.append(address)
            return False

        hook = uc.hook_add(UC_HOOK_MEM_UNMAPPED, unmapped)
        try:
            uc.emu_start(va, STOP, count=2_000_000)
            if uc.reg_read(UC_X86_REG_EIP) != STOP:
                return ("budget", uc.reg_read(UC_X86_REG_EIP))
            return ("returned", uc.reg_read(UC_X86_REG_EAX))
        except UcError:
            return ("fault", fault[0] if fault else None)
        finally:
            uc.hook_del(hook)

    def set_specials(self, specials: bytes) -> None:
        self.uc.mem_write(self.team + 0x194, specials)

    def row(self, position: int, rank: int):
        return self.call(GET_ROW, {UC_X86_REG_EDX: self.team}, (rank, position, 0))

    def row_from(self, caller: int, position: int, rank: int):
        """The row getter entered from a real caller's return address (the game decides by it what a row shows)."""
        uc = self.uc
        esp = STACK - 0x200
        uc.mem_write(esp, struct.pack("<4I", caller, rank, position, 0))
        uc.reg_write(UC_X86_REG_ESP, esp)
        uc.reg_write(UC_X86_REG_EDX, self.team)
        uc.emu_start(GET_ROW, caller, count=2_000_000)
        if uc.reg_read(UC_X86_REG_EIP) != caller:
            raise AssertionError("returner row failed to reach its native caller")
        return uc.reg_read(UC_X86_REG_EAX)

    def fielded_rows(self) -> list[int]:
        """Read KR1, KR2 and PR via the native lineup constructor and match personnel reader."""
        def native(address, regs, args=()):
            status, result = self.call(address, regs, args)
            if status != "returned":
                raise AssertionError(f"native returner routine {address:#x} stopped at {result!r}: {status}")
            return result

        native(0xE80D0, {UC_X86_REG_ECX: self.team, UC_X86_REG_EDX: OBJ}, (0, 0))
        players = []
        for kind, rank in ((26, 0), (26, 1), (27, 0)):
            count = native(0xE75A0, {UC_X86_REG_ECX: kind, UC_X86_REG_EDX: OBJ})
            player = native(0xE7810, {UC_X86_REG_EAX: kind, UC_X86_REG_ECX: 0}, (OBJ, rank)) if rank < count else 0
            players.append(player)
        return players

    def specials(self) -> list[int]:
        return list(self.uc.mem_read(self.team + 0x194, 6))


def _legacy(retail: bytes) -> bytes:
    """A beta-79-style image: the returner loop applied, the getter still retail, the .text digest recomputed."""
    buf = bytearray(retail)
    off = returner._offset(retail, returner.SITE_VA)
    buf[off:off + returner.SITE_SIZE] = returner.site_bytes()
    for s in _sections(bytes(buf)):
        if s.virtual_address <= returner.SITE_VA < s.virtual_address + s.raw_size:
            buf[s.header_offset + 36:s.header_offset + 56] = section_digest(bytes(buf), s)
    return bytes(buf)


def _diff_runs(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """Changed byte runs of two equal-length images (4 KB blocks compared first, then bytes)."""
    assert len(a) == len(b)
    runs, start = [], None
    for block in range(0, len(a), 0x1000):
        if a[block:block + 0x1000] == b[block:block + 0x1000]:
            if start is not None:
                runs.append((start, block))
                start = None
            continue
        for i in range(block, min(block + 0x1000, len(a))):
            if a[i] != b[i] and start is None:
                start = i
            elif a[i] == b[i] and start is not None:
                runs.append((start, i))
                start = None
    if start is not None:
        runs.append((start, len(a)))
    return runs


@unittest.skipUnless(RETAIL.is_file(), "the retail default.xbe is not configured (NFL2K5_RETAIL_XBE)")
class ReturnerGetterStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        cls.applied = returner.apply(cls.retail)[0]

    def test_retail_bytes_are_the_pinned_getter(self):
        off = returner._offset(self.retail, returner.GETTER_VA)
        self.assertEqual(self.retail[off:off + returner.GETTER_SIZE], returner.RETAIL_GETTER)
        self.assertEqual(returner.status(self.retail), "retail")
        self.assertEqual(returner.status(self.applied), "applied")

    def test_new_getter_fits_and_ends_in_int3(self):
        code, helper = returner._getter_code(), returner._lineup_helper_code()
        self.assertLessEqual(len(code), 96)
        self.assertEqual(len(helper), 32)           # the site holds both, exactly 128 bytes
        self.assertEqual(returner.getter_bytes(), code.ljust(96, b"\xcc") + helper)
        self.assertEqual((code[-1:], helper[-1:]), (b"\xc3", b"\xc3"))
        v1 = returner.getter_bytes_v1()                                  # the first st1 form upgrades in place
        self.assertEqual(len(v1), returner.GETTER_SIZE)
        self.assertEqual(v1[98:], b"\xcc" * 30)

    def test_both_previous_beta81_display_versions_upgrade_and_foreign_lookup_refuses(self):
        # Original standard and its subsequent draw/edit dispatch fix shared the same fixed-offset list lookup.
        previous = returner.PREVIOUS["returner_lookup"][0]
        self.assertEqual(hashlib.sha256(previous).hexdigest(), "1dac7fe757cac8407a9d6901a31193c81f79212805ec8dadb41261749a35c459")
        historical_chart = returner.PREVIOUS["returner_chart"][0]
        self.assertEqual(hashlib.sha256(historical_chart).hexdigest(), "4a8eed1f56d098193c651e310ff96a2fe42d22f03729ca8f5e6103b2dbaa8487")
        for chart in returner.PREVIOUS["returner_chart"]:
            old = bytearray(self.applied)
            for va, body in ((returner.ROW_LABEL_VA, chart), (returner.SUMMARY_TAIL_VA, returner.RETAIL_SUMMARY_TAIL),
                             (returner.FN_NTH_RETURNER, previous)):
                offset = returner._offset(self.applied, va)
                old[offset:offset + len(body)] = body
            self.assertEqual(returner.status(bytes(old)), "legacy")
            self.assertEqual(returner.apply(bytes(old))[0], self.applied)
            old[offset + len(previous) - 1] ^= 1
            self.assertEqual(returner.status(bytes(old)), "foreign")

    def test_only_the_owned_sites_and_the_text_digest_change(self):
        text = next(s for s in _sections(self.retail) if s.virtual_address <= returner.GETTER_VA < s.virtual_address + s.raw_size)
        allowed = [(text.header_offset + 36, text.header_offset + 56)]
        for va, size in ((returner.SITE_VA, returner.SITE_SIZE), (returner.GETTER_VA, returner.GETTER_SIZE),
                         (returner.SUMMARY_TAIL_VA, len(returner.RETAIL_SUMMARY_TAIL)),
                         (returner.ROW_LABEL_VA, returner.ROW_LABEL_SIZE), (returner.FN_NTH_RETURNER, returner.NTH_SIZE),
                         (returner.LINEUP_HOOK_VA, 7), (returner.EXCHANGE_VA, returner.EXCHANGE_SIZE),
                         (returner.ALL_STAR_CALL_VA, 5)):
            off = returner._offset(self.retail, va)
            allowed.append((off, off + size))
        for start, end in _diff_runs(self.retail, self.applied):
            self.assertTrue(all(any(lo <= offset < hi for lo, hi in allowed) for offset in range(start, end)), hex(start))

    def test_legacy_image_upgrades_to_the_fresh_install(self):
        legacy = _legacy(self.retail)
        self.assertEqual(returner.status(legacy), "legacy")
        upgraded, receipt = returner.apply(legacy)
        self.assertEqual(upgraded, self.applied)
        self.assertEqual(receipt["upgraded_from"], "legacy")
        self.assertEqual([e["label"] for e in receipt["edits"]],
                         ["returner_chart", "returner_summary", "returner_lookup", "returner_getter",
                          "lineup_slot_check", "exchange_store", "all_star_skip"])
        # the first b780 st1 install (loop + 98-byte getter) upgrades the same way
        first = bytearray(legacy)
        off = returner._offset(legacy, returner.GETTER_VA)
        first[off:off + returner.GETTER_SIZE] = returner.getter_bytes_v1()
        self.assertEqual(returner.status(bytes(first)), "legacy")
        self.assertEqual(returner.apply(bytes(first))[0][off:off + returner.GETTER_SIZE], returner.getter_bytes())
        with self.assertRaises(returner.ReturnerFixError):
            returner.apply(upgraded)

    def test_mixed_or_foreign_getters_are_refused(self):
        for base in (self.retail, self.applied, _legacy(self.retail)):
            buf = bytearray(base)
            buf[returner._offset(base, returner.GETTER_VA) + 0x30] ^= 0xFF
            self.assertEqual(returner.status(bytes(buf)), "foreign")
            with self.assertRaises(returner.ReturnerFixError):
                returner.apply(bytes(buf))
        getter_only = bytearray(self.retail)
        off = returner._offset(self.retail, returner.GETTER_VA)
        getter_only[off:off + returner.GETTER_SIZE] = returner.getter_bytes()
        self.assertEqual(returner.status(bytes(getter_only)), "foreign")

    def test_released_executables_upgrade_in_place(self):
        seen = 0
        for name, path in RELEASED.items():
            data = _read(path)
            if data is None:
                continue
            seen += 1
            with self.subTest(release=name):
                self.assertEqual(returner.status(data), "legacy")
                upgraded, receipt = returner.apply(data)
                self.assertEqual(returner.status(upgraded), "applied")
                self.assertEqual(len(upgraded), len(data))
                getter = returner._offset(data, returner.GETTER_VA)
                self.assertEqual(upgraded[getter:getter + returner.GETTER_SIZE], returner.getter_bytes())
                text = next(s for s in _sections(data) if s.virtual_address <= returner.GETTER_VA < s.virtual_address + s.raw_size)
                allowed = [(text.header_offset + 36, text.header_offset + 56)]
                for va, size in ((returner.GETTER_VA, returner.GETTER_SIZE), (returner.LINEUP_HOOK_VA, 7),
                                 (returner.SUMMARY_TAIL_VA, len(returner.RETAIL_SUMMARY_TAIL)),
                                 (returner.EXCHANGE_VA, returner.EXCHANGE_SIZE), (returner.ALL_STAR_CALL_VA, 5),
                                 (returner.SITE_VA, returner.SITE_SIZE),     # the loop gains the injury test
                                 # beta 81 (K01): the row labels and the compacted nth-returner lookup share their
                                 # two retail functions with the fielded-returner display check
                                 (returner.ROW_LABEL_VA, returner.ROW_LABEL_SIZE),
                                 (returner.FN_NTH_RETURNER, returner.NTH_SIZE)):
                    off = returner._offset(data, va)
                    allowed.append((off, off + size))
                for start, end in _diff_runs(data, upgraded):
                    self.assertTrue(all(any(lo <= offset < hi for lo, hi in allowed) for offset in range(start, end)), hex(start))
                self.assertEqual(receipt["changed_bytes"], sum(end - start for start, end in _diff_runs(data, upgraded)))
        if not seen:
            self.skipTest("no released executable configured (NFL2K5_V08_XBE, NFL2K5_B780_RC_XBE)")

    def test_detail_only_standard_upgrades_and_foreign_summary_selector_refuses(self):
        prior = returner.PREVIOUS["returner_chart"][1]
        self.assertEqual(hashlib.sha256(prior).hexdigest(), "2f3e134f56768b4e4b89e68436cc09893e85ca7d67112bb51d4d2e475d873a0b")
        old = bytearray(self.applied)
        chart = returner._offset(old, returner.ROW_LABEL_VA)
        summary = returner._offset(old, returner.SUMMARY_TAIL_VA)
        old[chart:chart + len(prior)] = prior
        old[summary:summary + len(returner.RETAIL_SUMMARY_TAIL)] = returner.RETAIL_SUMMARY_TAIL
        self.assertEqual(returner.status(bytes(old)), "legacy")
        upgraded, receipt = returner.apply(bytes(old))
        self.assertEqual(upgraded, self.applied)
        self.assertEqual([e["label"] for e in receipt["edits"]], ["returner_chart", "returner_summary"])
        for base in (old, self.applied):
            foreign = bytearray(base)
            foreign[summary + len(returner.RETAIL_SUMMARY_TAIL) - 1] ^= 1
            self.assertEqual(returner.status(bytes(foreign)), "foreign")
            with self.assertRaises(returner.ReturnerFixError):
                returner.apply(bytes(foreign))
        for offset, size in ((chart, len(prior)), (summary, len(returner.RETAIL_SUMMARY_TAIL))):
            mixed = bytearray(old)
            mixed[offset:offset + size] = upgraded[offset:offset + size]
            self.assertEqual(returner.status(bytes(mixed)), "foreign")


@unittest.skipUnless(HAVE_UC, "Unicorn is absent; native x86 proofs require it")
@unittest.skipUnless(RETAIL.is_file(), "the retail default.xbe is not configured (NFL2K5_RETAIL_XBE)")
class ReturnerGetterNativeTests(unittest.TestCase):
    """The game's own depth-chart code, before (retail) and after (patched)."""

    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        cls.images = {"retail + fix": returner.apply(cls.retail)[0]}
        for name, path in RELEASED.items():
            data = _read(path)
            if data is not None and returner.status(data) == "legacy":
                cls.images[name + " upgraded"] = returner.apply(data)[0]

    def test_valid_slots_return_exactly_what_retail_returns(self):
        slots = (1, 2, 4, 8)
        cases = 0
        old = _Machine(self.retail, PS_TAIL, bytes(6))
        for name, image in self.images.items():
            new = _Machine(image, PS_TAIL, bytes(6))
            for kr1, kr2, pr in itertools.product(slots, slots, slots):
                specials = bytes([0, kr1, kr2, 9, 1, pr])
                old.set_specials(specials)
                new.set_specials(specials)
                for position, rank in itertools.product((KR, PR), range(9)):
                    with self.subTest(image=name, kr1=kr1, kr2=kr2, pr=pr, position=hex(position), rank=rank):
                        self.assertEqual(new.row(position, rank), old.row(position, rank))
                        cases += 1
        self.assertGreaterEqual(cases, 64 * 18)

    def test_summary_name_and_jersey_follow_fielded_rows_while_other_selector_callers_keep_stored_slots(self):
        from mod_editor.core.nfl2k5_depth_chart_rows import SUMMARY_COLUMNS
        original = bytes([0, 2, 3, 9, 1, 8])
        m = _Machine(self.images["retail + fix"], PS_TAIL, original)
        names = {}
        for slot in range(len(ROSTER)):
            player = m.players[1, slot]
            data = PLAYERS + 0x8000 + 0x80 * slot
            for off, ptr, text in ((0x10, data, "Alex"), (0x14, data + 32, f"Runner{slot}")):
                m.uc.mem_write(ptr, (text + "\0").encode("utf-16-le"))
                m.uc.mem_write(player + off, struct.pack("<I", ptr))
            names[player] = (str(40 + slot), f"A. Runner{slot}")
        for out in ((), (2,), (8,), (2, 3)):
            for slot in (2, 3, 8):
                m.uc.mem_write(m.players[1, slot] + 0x27, b"\x40" if slot in out else b"\0")
            fielded = m.fielded_rows()
            for role, (row, rank, saved) in enumerate(((0, 0, 2), (0, 1, 3), (1, 0, 8))):
                for kind, expected_callback in enumerate((ROW_NUMBER, ROW_NAME)):
                    col = 1 + 2 * rank + kind
                    callback = struct.unpack("<I", m.uc.mem_read(SUMMARY_COLUMNS[col] + 8, 4))[0]
                    self.assertEqual(callback, expected_callback)
                    state, ptr = m.call(callback, {UC_X86_REG_ECX: col, UC_X86_REG_EDX: row})
                    self.assertEqual(state, "returned")
                    rendered = bytes(m.uc.mem_read(ptr, 64)).decode("utf-16-le").split("\0", 1)[0]
                    self.assertEqual(rendered, names[fielded[role]][kind], (out, row, col))
                for caller in (0x243B8C, 0x243BB0):
                    esp = STACK - 0x200
                    m.uc.mem_write(esp, struct.pack("<I", caller))
                    m.uc.reg_write(UC_X86_REG_ESP, esp)
                    m.uc.reg_write(UC_X86_REG_ECX, 1 + 2 * rank)
                    m.uc.reg_write(UC_X86_REG_EDX, row)
                    m.uc.emu_start(0x242C00, caller, count=2000000)
                    self.assertEqual(m.uc.reg_read(UC_X86_REG_EIP), caller)
                    self.assertEqual(m.uc.reg_read(UC_X86_REG_ESP), esp + 4)
                    self.assertEqual(m.uc.reg_read(UC_X86_REG_EAX), m.players[1, saved])
            self.assertEqual(m.specials(), list(original))

    def test_shared_summary_selector_preserves_retail_columns_and_default_rank(self):
        specials = bytes([0, 2, 3, 9, 1, 8])
        old = _Machine(self.retail, 0, specials)
        new = _Machine(self.images["retail + fix"], 0, specials)
        for page in range(4):
            for machine in (old, new):
                machine.uc.mem_write(0xC174B8, struct.pack("<I", page))
            for row in range(11):
                for column in (*range(8), 0xFFFFFFFF):
                    regs = {UC_X86_REG_ECX: column, UC_X86_REG_EDX: row}
                    previous = old.call(0x242C00, regs)
                    self.assertEqual(previous[0], "returned", (page, row, column))
                    self.assertEqual(new.call(0x242C00, regs), previous, (page, row, column))

    def test_injured_locked_returner_rows_follow_the_game_lineup_and_recover_with_the_player(self):
        # Three distinct designated players let a PR injury and a KR injury be tested independently.
        original = bytes([0, 2, 3, 9, 1, 8])
        roles = ((KR, 0), (KR, 1), (PR, 0))
        for name, image in self.images.items():
            for role, slot in ((0, 2), (2, 8)):
                with self.subTest(image=name, role=roles[role]):
                    machine = _Machine(image, PS_TAIL, original)
                    stored = [machine.players[1, i] for i in (2, 3, 8)]
                    self.assertEqual(machine.fielded_rows(), stored)
                    injured = machine.players[1, slot]
                    machine.uc.mem_write(injured + 0x23, b"\x80")  # active injury
                    machine.uc.mem_write(injured + 0x27, b"\x40")  # Out for field availability
                    fielded = machine.fielded_rows()
                    self.assertNotIn(injured, fielded)
                    self.assertEqual(fielded[role], stored[1])     # healthy designated KR2 fills in
                    self.assertEqual([machine.row_from(COLUMN_TEXT, p, r) for p, r in roles], fielded)
                    self.assertEqual([machine.row_from(EDIT_CALLERS[-1], p, r) for p, r in roles], stored)
                    self.assertEqual(machine.call(RERANK, {UC_X86_REG_ECX: machine.team})[0], "returned")
                    self.assertEqual(machine.specials(), list(original))
                    machine.uc.mem_write(injured + 0x23, b"\0")
                    machine.uc.mem_write(injured + 0x27, b"\0")
                    self.assertEqual(machine.fielded_rows(), stored)
                    self.assertEqual([machine.row_from(COLUMN_TEXT, p, r) for p, r in roles], stored)

    def test_draw_callbacks_show_the_fielded_returner_and_edits_act_on_the_stored_slot(self):
        # The draw callbacks show who fields the kick (the game's lineup builder 0xE80D0); the input handler
        # (0x2442BE: promote, swap) and the rerank helpers get the stored players, so an edit never stores a fill-in.
        # Cases: KR1 out, and KR1 and KR2 out at once.
        original = bytes([0, 2, 3, 9, 1, 3])
        stored_slots = (2, 3, 3)
        rows = ((KR, 0), (KR, 1), (PR, 0))
        for name, image in self.images.items():
            for out in ((2,), (2, 3)):
                machine = _Machine(image, PS_TAIL, original)
                for slot in out:
                    machine.uc.mem_write(machine.players[1, slot] + 0x27, b"\x40")
                fielded = machine.fielded_rows()
                stored = [machine.players[1, s] for s in stored_slots]
                if out == (2,):
                    self.assertNotEqual(fielded[0], stored[0])    # the healthy KR2 moves up
                for caller in DRAW_CALLERS:
                    with self.subTest(image=name, out=out, caller=hex(caller)):
                        self.assertEqual([machine.row_from(caller, p, r) for p, r in rows], fielded)
                for caller in EDIT_CALLERS:
                    with self.subTest(image=name, out=out, caller=hex(caller)):
                        self.assertEqual([machine.row_from(caller, p, r) for p, r in rows], stored)
                self.assertEqual(machine.specials(), list(original))

    def test_an_empty_returner_byte_reads_no_player(self):
        for name, image in self.images.items():
            for byte, position, rank in ((0x195, KR, 0), (0x196, KR, 1), (0x199, PR, 0)):
                specials = bytearray([0, 2, 3, 9, 1, 3])
                specials[byte - 0x194] = 0xFF
                with self.subTest(image=name, byte=hex(byte)):
                    old = _Machine(self.retail, PS_TAIL, bytes(specials))
                    self.assertEqual(old.row(position, rank), ("returned", PS_TAIL))     # the defect
                    self.assertEqual(_Machine(self.retail, 0, bytes(specials)).row(position, rank), ("returned", 0))
                    self.assertEqual(_Machine(image, PS_TAIL, bytes(specials)).row(position, rank), ("returned", 0))
                    self.assertEqual(_Machine(image, 0, bytes(specials)).row(position, rank), ("returned", 0))

    def test_a_byte_past_the_roster_reads_no_player(self):
        for name, image in self.images.items():
            with self.subTest(image=name):
                m = _Machine(image, PS_TAIL, bytes([0, 2, 40, 9, 1, 40]))
                self.assertEqual(m.row(KR, 1), ("returned", 0))
                self.assertEqual(m.row(PR, 0), ("returned", 0))
                self.assertEqual(m.row(KR, 0), ("returned", m.players[(1, 2)]))

    def test_special_teams_rows_and_the_kr_list_no_longer_fault(self):
        empty_kr2 = bytes([0, 2, 0xFF, 9, 1, 3])
        empty_pr = bytes([0, 2, 3, 9, 1, 0xFF])
        old = _Machine(self.retail, PS_TAIL, empty_kr2)
        self.assertEqual(old.call(KR_PHOTO, {UC_X86_REG_EDX: 1}, (OBJ, 0)), ("fault", PS_TAIL + 6))
        old = _Machine(self.retail, PS_TAIL, empty_pr)
        self.assertEqual(old.call(ROW_NUMBER, {UC_X86_REG_ECX: 1, UC_X86_REG_EDX: 1}), ("fault", PS_TAIL + 0x20))
        self.assertEqual(old.call(ROW_NAME, {UC_X86_REG_ECX: 1, UC_X86_REG_EDX: 1})[0], "fault")
        for name, image in self.images.items():
            with self.subTest(image=name):
                m = _Machine(image, PS_TAIL, empty_kr2)
                self.assertEqual(m.call(KR_PHOTO, {UC_X86_REG_EDX: 1}, (OBJ, 0))[0], "returned")
                self.assertEqual(struct.unpack("<I", m.uc.mem_read(OBJ + 8, 4))[0] & 1, 1)        # "no player" row
                self.assertEqual(m.call(ROW_NAME, {UC_X86_REG_ECX: 3, UC_X86_REG_EDX: 0}), ("returned", NO_PLAYER_TEXT))
                self.assertEqual(m.call(ROW_NUMBER, {UC_X86_REG_ECX: 3, UC_X86_REG_EDX: 0}), ("returned", NO_PLAYER_TEXT))
                m = _Machine(image, PS_TAIL, empty_pr)
                self.assertEqual(m.call(ROW_NAME, {UC_X86_REG_ECX: 1, UC_X86_REG_EDX: 1}), ("returned", NO_PLAYER_TEXT))
                self.assertEqual(m.call(ROW_NUMBER, {UC_X86_REG_ECX: 1, UC_X86_REG_EDX: 1}), ("returned", NO_PLAYER_TEXT))
                # the KR row's starter (rank 0) still shows KR1
                self.assertEqual(m.call(ROW_NUMBER, {UC_X86_REG_ECX: 1, UC_X86_REG_EDX: 0})[0], "returned")
                self.assertNotEqual(m.call(ROW_NUMBER, {UC_X86_REG_ECX: 1, UC_X86_REG_EDX: 0})[1], NO_PLAYER_TEXT)

    def test_the_rerank_keeps_a_real_returner_instead_of_slot_0(self):
        empty = bytes([0, 2, 0xFF, 9, 1, 0xFF])
        old = _Machine(self.retail, PS_TAIL, empty)
        self.assertEqual(old.call(RERANK, {UC_X86_REG_ECX: old.team})[0], "returned")
        self.assertEqual(old.specials()[2], 0)                                   # the defect: the slot-0 quarterback
        native = _Machine(self.retail, 0, empty)                                 # retail rosters (no marker)
        native.call(RERANK, {UC_X86_REG_ECX: native.team})
        for name, image in self.images.items():
            with self.subTest(image=name):
                m = _Machine(image, PS_TAIL, empty)
                self.assertEqual(m.call(RERANK, {UC_X86_REG_ECX: m.team})[0], "returned")
                self.assertEqual(m.specials()[1:3], native.specials()[1:3])      # KR1 kept, KR2 = the next returner
                self.assertEqual(m.specials()[5], native.specials()[5])
                self.assertNotIn(0, (m.specials()[2], m.specials()[5]))
                self.assertEqual(ROSTER[m.specials()[2]], "CB")
                self.assertEqual(m.call(NTH_ROW, {UC_X86_REG_EAX: 1, UC_X86_REG_ECX: KR, UC_X86_REG_ESI: m.team}),
                                 ("returned", m.specials()[2]))


if __name__ == "__main__":
    unittest.main()

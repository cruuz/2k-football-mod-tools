"""Bounded native user play-call pane replay, without an Xbox/GPU or game boot.

Unlike the list-only MenuWalker, this loads PLAY through 0xE0D90 and runs
0x144BA0, its formatter, FONT glyph walkers, camera code, all eleven route
slots and formation icons. FPU state is initialized once and preserved.

Inputs: executable, one whole PLAY resource, entry 3's nine FONT resources.
Fixture boundaries: static diagram model objects, an empty roster binding,
an ordinary viewport, no field background, immediate GPU/mesh submissions,
and the Xbox AV-settings query. Player labels, scene streaming, live heap
residency and the emulator GPU are not covered. A return is not a game witness.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import math
import struct

from tests.nfl2k5_play_menu_walk_native import MenuWalker, BOOK_VA, STATE_VA, MENU_VA, STACK, STOP
from mod_editor.core import nfl2k5_playbook_inspector as ip


class UserPlayMenuMachine(MenuWalker):
    # Assigned by the native user menu (0xAC5C4 / 0xAC8D6 and special-team branches).
    CATEGORY_ORDERS = (0x5102CC, 0x510304, 0x510328, 0x510334)

    def __init__(self, xbe: bytes, resource: bytes, font_entry: bytes):
        from nfl_main_menu_font import parse_font, FONT_NAMES
        from nfl_scene_probe import ResourceRecord
        from nfl_txtr import parse_chunks, decode_chunk

        super().__init__(xbe, resource)
        self.hits = Counter()
        self.vertices = 0
        self.leaves = {}
        for name, value in (("FPCW", 0x37F), ("FPTAG", 0xFFFF), ("FPSW", 0)):
            self.uc.reg_write(getattr(self.r, "UC_X86_REG_" + name), value)
        self.uc.mem_map(0x2600000, 0x10000)
        # Native 0x21970 reads each static diagram mesh's matrix pointer +0x14.
        for i, va in enumerate(range(0xBD92D4, 0xBD92F4, 4)):
            obj = 0x2600000 + i * 0x200
            self.put(va, obj)
            self.put(obj + 0x14, obj + 0x100)
        # Undo MenuWalker's header-only relocation; execute the real full loader.
        self.uc.mem_write(BOOK_VA, resource[ip.RESOURCE_HEADER_SIZE:])
        self.put(0xBE4E20, 0x521078)  # Native opcode descriptor table.
        self.put(0xB72918, STATE_VA + 0x800)  # No roster-name binding records.
        self.call(0xE0D90, ecx=BOOK_VA, budget=20_000_000)
        for va, pop in ((0x243D0, 12), (0x2CB50, 12), (0x2D2A0, 12),
                        (0x2CB90, 8), (0x2CBE0, 0), (0x2CA70, 0), (0x2CA00, 0),
                        (0x9CFC0, 0)):
            self.leaves[va] = pop
            self.uc.hook_add(self.u.UC_HOOK_CODE, self._leaf, begin=va, end=va)
        # ExQueryNonVolatileSetting: return failure so the native caller uses
        # its ordinary AV default. Native AV helper 0x3783FF reads the import below.
        self.leaves[0x20A70] = 20
        self.uc.hook_add(self.u.UC_HOOK_CODE, self._leaf, begin=0x20A70, end=0x20A70)
        self.put(0x4E3D14, STATE_VA + 0x1F00)
        self.put(0xA6AFB4, 0xA6AFC0)
        self.uc.mem_write(0xA6AFC0 + 0x250, struct.pack("<8f", 0, 0, 0, 1, 640, 448, 1, 1))

        self.uc.mem_map(0x4000000, 0x400000)
        cursor = 0x4000000
        fonts = parse_chunks(font_entry, allow_trailing=True)[:9]
        if len(fonts) != 9 or any(c.kind != "FONT" for c in fonts):
            raise ValueError("entry 3 must begin with the nine game fonts")
        self.font_hashes = []
        for c in fonts:
            decoded, _ = decode_chunk(font_entry, c)
            digest = hashlib.sha256(decoded).hexdigest()
            record = ResourceRecord(3, "entry3", len(font_entry), c.index, c.offset,
                                    c.kind, c.stored_size, c.system_bytes, c.video_bytes,
                                    c.compression_magic, c.overlap_scratch_bytes)
            font = parse_font(c.index, FONT_NAMES[c.index], record, decoded, digest)
            if cursor + len(decoded) > 0x4400000:
                raise ValueError("bounded FONT heap exceeded")
            self.uc.mem_write(cursor, decoded)
            obj = cursor + font.object_offset
            self.put(obj + 8, cursor + font.range_offset)
            for row in font.ranges:
                self.put(cursor + row["record_offset"] + 4, cursor + row["glyph_records_offset"])
            self.put(0xA90ECC + 4 * c.index, obj)
            self.font_hashes.append(digest)
            cursor += (len(decoded) + 15) & ~15

        self.put(0xBD9424, 16)
        self.put(0xBD9414, 0x2600F00)
        self.put(0xBD9418, 0x2600F00)
        for va in (STATE_VA + 0x1020, STATE_VA + 0x1030):
            self.uc.mem_write(va, struct.pack("<4f", 0, 0, 10, 1))
        self.uc.mem_write(STATE_VA + 0x1100, b"\xff" * 8)
        self.call(0x49ED0)  # Native printf conversion registration, including F4.

    def put(self, address, value):
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def reg(self, name):
        return self.uc.reg_read(getattr(self.r, "UC_X86_REG_" + name.upper()))

    def _leaf(self, _uc, address, _size, _data):
        self.hits[address] += 1
        # Inspect arguments BEFORE returning from the leaf, while ESP is live.
        if address == 0x2CB50:
            values = struct.unpack("<3f", self.uc.mem_read(self.reg("ESP") + 4, 12))
        elif address == 0x2CA70:
            values = struct.unpack("<4f", self.uc.mem_read(self.reg("ECX"), 16))
        else:
            values = None
        if values is not None:
            if not all(math.isfinite(v) for v in values):
                raise AssertionError(f"nonfinite vertex at {address:#x}: {values}")
            self.vertices += 1
        self._return(0xC0000001 if address == 0x20A70 else 0, pop=self.leaves[address])

    def call(self, address, *, ecx=0, edx=0, eax=0, args=(), budget=100_000):
        self.uc.mem_write(STACK, struct.pack("<" + "I" * (1 + len(args)), STOP, *args))
        for name, value in dict(ESP=STACK, EAX=eax, ECX=ecx, EDX=edx,
                                EBX=0, ESI=0, EDI=0, EBP=0, EFLAGS=0x202).items():
            self.uc.reg_write(getattr(self.r, "UC_X86_REG_" + name), value)
        self.uc.emu_start(address, STOP, count=budget)
        if self.reg("EIP") != STOP:
            raise AssertionError(f"native budget expired at {self.reg('EIP'):#x}")
        if self.reg("ESP") != STACK + 4 + 4 * len(args):
            raise AssertionError(f"native stack imbalance in {address:#x}")
        return self.reg("EAX")

    def pane(self, formation: int, play: int | None = None, *, flip=0):
        """Draw one formation or play pane. Native routines keep FPU state between calls."""
        self.uc.mem_write(STATE_VA + 0x1000, struct.pack("<4f", -100, -100, 0, 1))
        self.uc.mem_write(STATE_VA + 0x1010, struct.pack("<4f", 100, 100, 0, 1))
        fva = self.formation_va(formation)
        category = self.call(0xE1A80, ecx=BOOK_VA, edx=fva)
        if not category:
            raise AssertionError("formation has no native category")
        pva = BOOK_VA + ip.PLAY_BASE + play * ip.PLAY_SIZE if play is not None else 0
        args = (STATE_VA + 0x1000, STATE_VA + 0x1010, STATE_VA + 0x1020,
                BOOK_VA, category, fva, pva, STATE_VA + 0x1200,
                2 if play is not None else 1, 0, flip, 4, 0xFFFFFFFF, 0,
                0x3F800000, STATE_VA + 0x1100, 0x41200000)
        self.call(0x144BA0, eax=STATE_VA + 0x1030, args=args, budget=3_000_000)
        if self.reg("FPTAG") != 0xFFFF:
            raise AssertionError("pane leaked floating-point stack entries")

    def categories(self, order):
        """Native category order, retaining only categories with a formation."""
        pointer = self.call(0xE0A50, ecx=BOOK_VA, edx=order)
        seen, visible = set(), []
        while pointer:
            if pointer in seen or len(seen) >= ip.CATEGORY_CAPACITY:
                raise AssertionError("native category walk cycles")
            seen.add(pointer)
            index, remainder = divmod(pointer - BOOK_VA - ip.CATEGORY_BASE, ip.CATEGORY_SIZE)
            if remainder or not 0 <= index < ip.CATEGORY_CAPACITY:
                raise AssertionError("native category pointer outside table")
            if self.call(0xE10D0, ecx=BOOK_VA, edx=pointer):
                visible.append(pointer)
            pointer = self.call(0xE0AA0, ecx=BOOK_VA, edx=order, args=(pointer,))
        return visible

    def formation_page(self, order, page):
        """Native 0xACBB0 category/formation page builder; menu-container leaves only."""
        self.uc.mem_write(STATE_VA, bytes(0x100))
        self.put(STATE_VA + 0x20, BOOK_VA)
        self.put(STATE_VA + 0x28, order)
        self.uc.mem_write(STATE_VA + 0x30, bytes([page]))
        items = []
        self.stubs = {
            0xF3540: lambda: self._return(STATE_VA),
            0xF3520: lambda: self._return(),
            0xF3560: lambda: self._return(),
            0xF36F0: lambda: (items.append(self.reg("EDX")), self._return()),
            0xF36A0: lambda: self._return(),
            0xABB70: lambda: self._return(pop=4),
        }
        try:
            self.call(0xACBB0, ecx=MENU_VA, budget=400_000)
        finally:
            self.stubs = {}
        return items

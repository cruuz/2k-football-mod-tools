"""Native proofs for the player-name keyboard (b77-k1): the game's own code under Unicorn.

Runs the retail (or patched) ``default.xbe`` as it is: the 56-slot key table, the key dispatcher
(0x248E50), the key handler (0x248DA0), the character filter (0x248D20), the append routine
(0x248D50) and both name handlers (First Name 0x346430, Last Name 0x346540, including the commentary
surname scan and the name-pool writer 0xC0330).  Only three things are modelled:

* the keyboard's frame loop around the keys (0x24A220: input polling and rendering).  The handler's
  call into it is stopped, the keyboard is initialised exactly as 0x24A220 does (0x248BE0), the typist
  presses keys through the real dispatcher, and the handler is resumed with the loop's return value
  (1 = Enter, 2 = Esc or an empty name),
* the sound, scrolling and message-box helpers (stubs; the message box records its text),
* the roster root and a few players (a fixture laid out as the handlers read it).

No xemu, no kernel, no disc writes.  Inputs are read-only byte strings.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unicorn as uni
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI,
                               UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)

from mod_editor.core.nfl2k5_cave_oracle import XbeImage

STACK, STOP, HEAP, HEAP_SIZE = 0x03000000, 0x03100000, 0x04000000, 0x100000

# keyboard state, key table and routines
CHARSET, MAXLEN, BUFFER, CURSOR, SELECTED, PASSWORD = 0xAC593C, 0xAC5938, 0xAC5730, 0xAC572C, 0xAC5720, 0xAC5944
KEY_TABLE, KEY_SLOTS, KEY_SIZE, KEY_COUNT = 0xAC4E58, 0x38, 0x28, 54
DISPATCH, KEYBOARD, KEYBOARD_INIT = 0x248E50, 0x24A220, 0x248BE0
DISPATCH_WORDS, DISPATCH_BYTES, CHAR_HANDLER = 0x248F84, 0x248F9C, 0x248F6A
DEFAULT_KEY = 0x29                                  # Enter: the selection 0x248BE0 starts on
ENTER, ESC, CLEAR = 41, 0, 15
# the name handlers and the roster
FIRST_HANDLER, LAST_HANDLER = 0x346430, 0x346540
PLAYER, DIRTY, ROSTER, MESSAGE_BOX = 0xCB8B14, 0xCB8820, 0xB72918, 0x14E440
KEYBOARD_STUBS = ((0x38650, 0x18), (0x89DA0, 0), (0x14D390, 0), (0x70A50, 4), (0x248B00, 0), (0x248AE0, 0),
                  (0x248CB0, 0), (0x3C3E0, 0), (0x3C3B0, 0))
ROOT_NODE, TEAMS, POOL, PLAYERS, NAMES = HEAP + 0x20000, HEAP + 0x30000, HEAP + 0x50000, HEAP + 0x60000, HEAP + 0x70000
FONT_BASE, TEXT = HEAP + 0x80000, HEAP + 0xE0000
FIRST_KEYBOARD_PUSH, LAST_KEYBOARD_PUSH = 0x3464C1, 0x3465BA


class Machine:
    """Unicorn with the XBE sections mapped at their virtual addresses and yield/resume at chosen entries."""

    def __init__(self, xbe: bytes):
        self.image = XbeImage(xbe)
        self.uc = uni.Uc(uni.UC_ARCH_X86, uni.UC_MODE_32)
        top = (self.image.base + self.image.image_size + 0xFFF) & ~0xFFF
        self.uc.mem_map(self.image.base, top - self.image.base)
        self.uc.mem_write(self.image.base, xbe[:self.image.headers_size])
        for section in self.image.sections:
            self.uc.mem_write(section.start, xbe[section.raw:section.raw + min(section.size, section.raw_size)])
        self.uc.mem_map(STACK - 0x10000, 0x20000)
        self.uc.mem_map(STOP, 0x1000)
        self.uc.mem_map(HEAP, HEAP_SIZE)
        self.stack = STACK
        self.yielded = None
        self._stubs = {}
        self._yield_at = set()

    def close(self):
        self.uc = None

    # -- memory
    def word(self, address: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(address, 4))[0]

    def half(self, address: int) -> int:
        return struct.unpack("<H", self.uc.mem_read(address, 2))[0]

    def put(self, address: int, value: int) -> None:
        self.uc.mem_write(address, struct.pack("<I", value & 0xFFFFFFFF))

    def text(self, address: int, limit: int = 96) -> str:
        out = []
        for i in range(limit):
            unit = self.half(address + 2 * i)
            if unit == 0:
                break
            out.append(chr(unit))
        return "".join(out)

    def write_text(self, address: int, value: str) -> None:
        self.uc.mem_write(address, value.encode("utf-16le") + b"\0\0")

    # -- hooks
    def _attach(self, va: int, callback) -> None:
        self.uc.hook_add(uni.UC_HOOK_CODE, lambda uc, a, s, u: callback(), begin=va, end=va)

    def stub(self, va: int, pop: int = 0, value: int = 0, fn=None) -> None:
        """Return from ``va`` as a stdcall callee would (``ret pop``) with EAX = value or fn(machine)."""
        def run():
            esp = self.uc.reg_read(UC_X86_REG_ESP)
            result = fn(self) if fn is not None else None
            self.uc.reg_write(UC_X86_REG_EIP, self.word(esp))
            self.uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)
            self.uc.reg_write(UC_X86_REG_EAX, value if result is None else result)
        self._attach(va, run)

    def yield_at(self, va: int) -> None:
        def run():
            regs = {r: self.uc.reg_read(r) for r in (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EBX,
                                                     UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP)}
            self.yielded = dict(va=va, regs=regs)
            self.uc.emu_stop()
        self._attach(va, run)

    # -- calls
    def _go(self, begin: int, budget: int):
        self.yielded = None
        try:
            self.uc.emu_start(begin, STOP, count=budget)
        except uni.UcError as exc:
            raise RuntimeError(f"{begin:#x}: fault at {self.uc.reg_read(UC_X86_REG_EIP):#x}: {exc}") from exc
        if self.yielded is not None:
            return "yield", self.yielded
        if self.uc.reg_read(UC_X86_REG_EIP) != STOP:
            raise RuntimeError(f"{begin:#x}: did not return within {budget} instructions")
        return "done", self.uc.reg_read(UC_X86_REG_EAX)

    def start(self, va: int, *, eax=0, ecx=0, edx=0, esi=0x22222222, edi=0x33333333, ebx=0x11111111, args=(),
              budget=3_000_000):
        self.uc.mem_write(self.stack, struct.pack("<" + "I" * (1 + len(args)), STOP, *args))
        for register, value in ((UC_X86_REG_ESP, self.stack), (UC_X86_REG_EAX, eax), (UC_X86_REG_ECX, ecx),
                                (UC_X86_REG_EDX, edx), (UC_X86_REG_EBX, ebx), (UC_X86_REG_ESI, esi),
                                (UC_X86_REG_EDI, edi), (UC_X86_REG_EBP, 0x44444444)):
            self.uc.reg_write(register, value)
        return self._go(va, budget)

    def resume(self, yielded: dict, eax: int, pop: int, budget=3_000_000):
        regs = yielded["regs"]
        esp = regs[UC_X86_REG_ESP]
        ret = self.word(esp)
        for register, value in regs.items():
            self.uc.reg_write(register, value)
        self.uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)
        self.uc.reg_write(UC_X86_REG_EAX, eax)
        return self._go(ret, budget)

    def call(self, va: int, **kwargs) -> int:
        kind, value = self.start(va, **kwargs)
        if kind != "done":
            raise RuntimeError(f"{va:#x} stopped at {value['va']:#x} unexpectedly")
        return value


def keyboard_machine(xbe: bytes) -> Machine:
    machine = Machine(xbe)
    for va, pop in KEYBOARD_STUBS:
        machine.stub(va, pop=pop)
    return machine


# ----------------------------------------------------------------------------------- key table
def key_chars(machine: Machine) -> list[tuple[str, str]]:
    """(unshifted, shifted) text of every key slot, read through the table's own pointers."""
    rows = []
    for key in range(KEY_COUNT):
        slot = KEY_TABLE + key * KEY_SIZE
        low, high = machine.word(slot + 0x1C), machine.word(slot + 0x20)
        rows.append((machine.text(low, 8) if low else "", machine.text(high, 8) if high else ""))
    return rows


def key_handler(machine: Machine, key: int) -> int:
    """The address 0x248E50 dispatches this key slot to (its own byte and jump tables)."""
    if key > 0x2A:
        return CHAR_HANDLER
    return machine.word(DISPATCH_WORDS + 4 * machine.uc.mem_read(DISPATCH_BYTES + key, 1)[0])


def character_keys(machine: Machine) -> list[int]:
    return [key for key in range(KEY_COUNT) if key_handler(machine, key) == CHAR_HANDLER]


def neighbours(machine: Machine, key: int) -> list[int]:
    slot = KEY_TABLE + key * KEY_SIZE
    return [machine.word(slot + 4 * i) for i in range(4)]


def reachable(machine: Machine, start: int = DEFAULT_KEY) -> set[int]:
    """Keys the D-pad can reach (up, down, left, right links; 0x37 means no neighbour)."""
    seen, queue = {start}, [start]
    while queue:
        for nxt in neighbours(machine, queue.pop()):
            if nxt != 0x37 and nxt < KEY_COUNT and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def find_key(machine: Machine, character: str):
    for key in character_keys(machine):
        low, high = key_chars(machine)[key]
        if low == character:
            return key, 0
        if high == character:
            return key, 1
    return None


def setup_keyboard(machine: Machine, charset_va: int, *, maxlen: int = 12, text: str = ""):
    buffer = HEAP + 0x1000
    machine.uc.mem_write(buffer, b"\0" * 128)
    machine.write_text(buffer, text)
    for address, value in ((CHARSET, charset_va), (MAXLEN, maxlen), (BUFFER, buffer), (CURSOR, len(text)),
                           (PASSWORD, 0), (0xAC5734, buffer)):
        machine.put(address, value)
    return buffer


def press(machine: Machine, key: int, shift: int) -> tuple[str, str]:
    """One press of a key slot through the real dispatcher; returns the buffer before and after."""
    buffer = machine.word(BUFFER)
    before = machine.text(buffer)
    machine.put(SELECTED, key)
    machine.put(KEY_TABLE + key * KEY_SIZE + 0x18, 0)        # the key's highlight timer must have run out
    machine.call(DISPATCH, eax=key, args=(shift,))
    return before, machine.text(buffer)


def typed_table(machine: Machine, charset_va: int, maxlen: int = 12) -> dict[tuple[int, int], str | None]:
    """What every character key appends for this allowed-character list, shifted and unshifted."""
    table = {}
    for key in character_keys(machine):
        for shift in (0, 1):
            setup_keyboard(machine, charset_va, maxlen=maxlen)
            before, after = press(machine, key, shift)
            table[(key, shift)] = after[len(before):] if len(after) > len(before) else None
    return table


def typeable(machine: Machine, charset_va: int) -> str:
    return "".join(sorted({c for c in typed_table(machine, charset_va).values() if c}))


def charset_pointers(machine: Machine) -> dict[str, int]:
    """The allowed-character list address each name handler pushes for the keyboard (read from its operands)."""
    return {"first_name": machine.word(FIRST_KEYBOARD_PUSH), "last_name": machine.word(LAST_KEYBOARD_PUSH)}


# ----------------------------------------------------------------------------------- name handlers
class Roster:
    """A roster root, one team and a handful of players, in the layout the name handlers read."""

    def __init__(self, machine: Machine, pool_chars: int = 0x1000):
        self.m, self.next_name, self.next_player = machine, NAMES, PLAYERS
        machine.put(ROSTER, ROOT_NODE)
        machine.put(ROOT_NODE + 0x18, 1)                       # team count
        machine.put(ROOT_NODE + 0x1C, TEAMS)                   # teams (500 bytes each)
        machine.put(ROOT_NODE + 0x68, POOL)                    # name pool cursor
        machine.put(ROOT_NODE + 0x6C, POOL + 2 * pool_chars)   # name pool limit
        machine.put(TEAMS + 0x128, 0)
        machine.uc.mem_write(TEAMS + 0x11C, b"\0")             # players on the team

    def name(self, text: str, capacity: int | None = None, guard: bool = False) -> int:
        capacity = capacity or len(text) + 1
        address = self.next_name
        self.m.uc.mem_write(address, b"\0" * (capacity * 2 + 8))
        self.m.write_text(address, text)
        if guard:
            self.m.uc.mem_write(address + capacity * 2, b"\xAA" * 8)
        self.next_name += (capacity * 2 + 8 + 3) & ~3
        return address

    def player(self, first: str, last: str, audio: int, *, created=False, jersey=0, on_team=True, capacity=None):
        m = self.m
        record = self.next_player
        self.next_player += 0x80
        m.uc.mem_write(record, b"\0" * 0x80)
        m.uc.mem_write(record + 4, struct.pack("<H", audio))
        m.uc.mem_write(record + 8, bytes([1 if created else 0]))
        m.put(record + 0x10, self.name(first, capacity, guard=created))
        m.put(record + 0x14, self.name(last, capacity, guard=created))
        m.put(record + 0x20, (jersey & 0x7F) << 3)
        if on_team:
            count = m.uc.mem_read(TEAMS + 0x11C, 1)[0]
            m.put(TEAMS + 4 * count, record)
            m.uc.mem_write(TEAMS + 0x11C, bytes([count + 1]))
        return record

    def guard_intact(self, address: int, capacity: int) -> bool:
        return bytes(self.m.uc.mem_read(address + capacity * 2, 8)) == b"\xAA" * 8

    def pool_cursor(self) -> int:
        return self.m.word(ROOT_NODE + 0x68)


class Typist:
    """Types scripted names through the real keys; one script entry per keyboard the handler opens.

    An entry is the text to type after Clear, or ``(text, "esc")`` to leave with Esc.  The record of each
    keyboard (title, allowed characters, cap, what was typed and what the buffer held) is kept in ``calls``.
    """

    def __init__(self, machine: Machine, scripts):
        self.m, self.scripts, self.calls, self.messages = machine, list(scripts), [], []
        machine.yield_at(KEYBOARD)
        machine.stub(MESSAGE_BOX, pop=0x18, fn=self._message)

    def _message(self, machine):
        self.messages.append(machine.text(machine.uc.reg_read(UC_X86_REG_EDX), 96))

    def drive(self, handler: int, *, widget: int = 0x1234):
        m = self.m
        m.stack = STACK
        kind, value = m.start(handler, ecx=widget)
        while kind == "yield":
            m.stack = STACK - 0x8000         # native side calls run on their own stack, below the handler's frame
            esp = value["regs"][UC_X86_REG_ESP]
            buf, maxlen, _a3, a4, title, charset, a7, a8 = [m.word(esp + 4 + 4 * i) for i in range(8)]
            script = self.scripts.pop(0)
            text, leave = (script, "enter") if isinstance(script, str) else script
            record = dict(title=m.text(title, 48), charset_va=charset, charset=m.text(charset, 96) if charset else None,
                          maxlen=maxlen, initial=m.text(buf, 48), typed=text, leave=leave)
            m.call(KEYBOARD_INIT, eax=title, ecx=charset, edx=a7, esi=buf, edi=maxlen, args=(a4,))
            m.put(SELECTED, CLEAR)
            m.call(DISPATCH, eax=CLEAR, args=(0,))
            untypable = []
            for character in text:
                key = find_key(m, character)
                if key is None:
                    untypable.append(character)
                    continue
                press(m, *key)
            record["untypable_keys"] = untypable
            record["buffer"] = m.text(buf, 48)
            leave_key = ESC if leave == "esc" else ENTER
            m.put(SELECTED, leave_key)
            result = m.call(DISPATCH, eax=leave_key, args=(0,))
            if leave == "enter" and a8 and not m.text(buf, 48):
                result = 2                     # 0x24A220 reports an empty name as a cancel
            record["result"] = result
            self.calls.append(record)
            m.stack = STACK
            kind, value = m.resume(value, eax=result, pop=0x20)
        return value


# ----------------------------------------------------------------------------------- fonts and nameplates
def read_outer(pack0: Path, index: int) -> bytes:
    with open(pack0, "rb") as handle:
        handle.seek(0x9C + 12 * index)
        _identity, size, sector = struct.unpack("<III", handle.read(12))
        handle.seek(sector * 2048)
        return handle.read(size)


def font_resources(span: bytes) -> dict[str, tuple[object, bytes]]:
    """Every FONT chunk of an outer as {name: (chunk, decoded bytes)} (VC-LZ decoded by the repo's reader)."""
    tools = str(ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import nfl_txtr as tx
    fonts = {}
    for chunk in tx.parse_chunks(span, allow_trailing=True):
        if chunk.kind != "FONT":
            continue
        raw = span[chunk.offset:chunk.offset + 0x20 + chunk.stored_size]
        decoded, _info = tx.decode_chunk(raw, tx.parse_chunks(raw, allow_trailing=True)[0])
        if decoded[0x0C:0x10] != b"FONT":
            raise ValueError("not a FONT object")
        name_at = 0x0F + struct.unpack_from("<i", decoded, 0x10)[0]
        end = name_at
        while decoded[end:end + 2] != b"\0\0":
            end += 2
        fonts[decoded[name_at:end].decode("utf-16le")] = (chunk, decoded)
    return fonts


def font_layout(decoded: bytes) -> dict:
    """Header, ranges and glyph records of a decoded FONT (field-relative pointers: target = field + value - 1)."""
    name_at = 0x0F + struct.unpack_from("<i", decoded, 0x10)[0]
    end = name_at
    while decoded[end:end + 2] != b"\0\0":
        end += 2
    obj = (end + 2 + 15) & ~15
    minimum, maximum, count = struct.unpack_from("<HHI", decoded, obj)
    ranges_at = obj + 8 + struct.unpack_from("<I", decoded, obj + 8)[0] - 1
    space_advance, line_advance = struct.unpack_from("<II", decoded, obj + 0x0C)
    glyphs, ranges = {}, []
    for i in range(count):
        record = ranges_at + 8 * i
        first, last = struct.unpack_from("<HH", decoded, record)
        glyph_at = record + 4 + struct.unpack_from("<I", decoded, record + 4)[0] - 1
        ranges.append((first, last, record, glyph_at))
        for code in range(first, last + 1):
            at = glyph_at + (code - first) * 0x60
            advance, = struct.unpack_from("<I", decoded, at)
            uv = struct.unpack_from("<4f", decoded, at + 0x50)
            glyphs[code] = dict(advance=advance, uv=uv)
    return dict(object=obj, minimum=minimum, maximum=maximum, ranges=ranges, glyphs=glyphs,
                space_advance=space_advance, line_advance=line_advance)


def glyph_ink(decoded: bytes, system: int, video: int, layout: dict, code: int, width: int, height: int):
    """Pixels of the glyph's atlas cell whose 4-bit palette index is non-zero (None when there is no glyph)."""
    glyph = layout["glyphs"].get(code)
    if glyph is None:
        return None
    tools = str(ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import nfl_txtr as tx
    pixels = video - 1024
    plane = tx.unswizzle_2d(decoded[system:system + pixels], width, height, 1)
    u0, v0, u1, v1 = glyph["uv"]
    x0, y0, x1, y1 = round(u0 * width), round(v0 * height), round(u1 * width), round(v1 * height)
    return sum(1 for y in range(y0, y1) for x in range(x0, x1) if plane[y * width + x])


def atlas_size(layout: dict, pixel_count: int):
    """Atlas width x height: the power-of-two shape on which every glyph UV lands on whole texels."""
    exact = []
    for width in (64, 128, 256, 512):
        height = pixel_count // width
        if width * height != pixel_count:
            continue
        if all(abs(value * scale - round(value * scale)) < 1e-6
               for glyph in layout["glyphs"].values() for value, scale in zip(glyph["uv"], (width, height, width, height))):
            exact.append((width, height))
    return exact[0] if len(exact) == 1 else None


def load_font(machine: Machine, decoded: bytes, layout: dict, base: int = FONT_BASE) -> int:
    """Place a decoded FONT in memory and relocate its two pointer fields the way the loader does."""
    machine.uc.mem_write(base, decoded)
    obj = layout["object"]
    ranges_at = obj + 8 + struct.unpack_from("<I", decoded, obj + 8)[0] - 1
    machine.put(base + obj + 8, base + ranges_at)
    for _first, _last, record, glyph_at in layout["ranges"]:
        machine.put(base + record + 4, base + glyph_at)
    return base + obj


def font_advance(machine: Machine, font: int, character: str) -> int:
    """0x493E0: a space (or a character with no glyph) advances by the font's space width, others by their glyph."""
    return machine.call(0x493E0, ecx=font, edx=ord(character))


def nameplate_width(machine: Machine, text: str, metrics: list[tuple[int, int]], spacing: int = 1) -> int:
    """0x1C20F0 on a synthetic NAME table; ``metrics`` = (atlas offset, advance) per glyph index."""
    table = HEAP + 0xC0000
    machine.uc.mem_write(table, b"".join(struct.pack("<HH", offset, advance) for offset, advance in metrics))
    machine.write_text(TEXT, text)
    return machine.call(0x1C20F0, esi=TEXT, ebx=spacing, args=(table,))


def nameplate_index(machine: Machine, text: str, position: int = 0) -> int:
    machine.write_text(TEXT, text)
    value = machine.call(0x1C20B0, eax=TEXT, ecx=position)
    return value - (1 << 32) if value & 0x80000000 else value


# ----------------------------------------------------------------------------------- receipt
def summary(xbe: bytes) -> dict:
    """The keyboard facts of one executable as JSON-ready data (used for the retail/patched receipt)."""
    machine = keyboard_machine(xbe)
    try:
        pointers = charset_pointers(machine)
        first, last = (machine.text(pointers[k], 96) for k in ("first_name", "last_name"))
        out = dict(charset_pointers={k: hex(v) for k, v in pointers.items()}, first_name_charset=first,
                   last_name_charset=last, character_keys=character_keys(machine),
                   reachable_keys=len(reachable(machine)), key_chars=key_chars(machine))
        out["typeable_first_name"] = typeable(machine, pointers["first_name"])
        out["typeable_last_name"] = typeable(machine, pointers["last_name"])
        return out
    finally:
        machine.close()


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Native keyboard summary of one or two default.xbe files")
    parser.add_argument("xbe", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = {str(path): summary(path.read_bytes()) for path in args.xbe}
    text = json.dumps(result, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

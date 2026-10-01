"""SoFi Stadium dome probe (job u6): run the retail routines natively (unicorn) on a stadium row of a main ROST and
report what the row's indoor word (+0x18) and surface word (+0x1C) change. No emulator, rendering or saves.

The routines run unmodified from the retail default.xbe: the bundle namer and the indoor reset (0x62BE0 up to 0x62CF4,
with the unrelated settings call 0xE2DB0 skipped), the rain and snow predicates (0x77BE0, 0x77BB0) that name the team
packages after the reset, the light rig choice (0x641C0, table pointer at 0xB34774) and the player-shadow scene choice
(0x91112 up to the scene lookup at 0x91146). The row's string pointers are made absolute, as the loader relocates them.

  python3 tools/nfl2k5_sofi_dome_probe.py XBE ROST_OUTER5 [--index 24] [--tod 0] [--temp 60] [--precip 0.9]
"""
import json, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
import unicorn as uc
from unicorn import x86_const as x86

POOL, STRIDE = 0xD0, 0x80
ROW, STR, OUT, STACK, STOP = 0x2000000, 0x2001000, 0x2002000, 0x300F000, 0x3010000


def rel(buf, at):
    v = struct.unpack_from('<i', buf, at)[0]
    return None if v == 0 else at + v - 1


def utf16(buf, at):
    out = []
    while True:
        c = struct.unpack_from('<H', buf, at)[0]
        if c == 0:
            return ''.join(out)
        out.append(chr(c)); at += 2


class M:
    def __init__(self, payload):
        self.u = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        self.u.mem_map(0x10000, 0x1800000 - 0x10000)
        self.u.mem_map(0x2000000, 0x10000)
        self.u.mem_map(0x3000000, 0x20000)
        img = XbeImage(payload)
        for s in img.sections:
            self.u.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        self.skip = set()
        self.u.hook_add(uc.UC_HOOK_CODE, self._hook)

    def _hook(self, u, address, size, _):
        if address in self.skip:            # return from a skipped callee (cdecl/thiscall without stack args)
            esp = u.reg_read(x86.UC_X86_REG_ESP)
            ret = struct.unpack('<I', u.mem_read(esp, 4))[0]
            u.reg_write(x86.UC_X86_REG_ESP, esp + 4)
            u.reg_write(x86.UC_X86_REG_EIP, ret)

    def put(self, at, v): self.u.mem_write(at, struct.pack('<I', v & 0xFFFFFFFF))
    def get(self, at): return struct.unpack('<I', self.u.mem_read(at, 4))[0]
    def f32(self, at, v): self.u.mem_write(at, struct.pack('<f', v))
    def rf(self, at): return struct.unpack('<f', self.u.mem_read(at, 4))[0]

    def run(self, start, stop, count=200000, **regs):
        self.put(STACK, STOP)
        self.u.reg_write(x86.UC_X86_REG_ESP, STACK)
        for n in ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP'):
            self.u.reg_write(getattr(x86, 'UC_X86_REG_' + n), regs.get(n.lower(), 0))
        self.u.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.u.emu_start(start, stop, count=count)
        return self.u.reg_read(x86.UC_X86_REG_EIP)

    def wstr(self, at):
        out = []
        while True:
            c = struct.unpack('<H', self.u.mem_read(at, 2))[0]
            if c == 0 or len(out) > 60:
                return ''.join(out)
            out.append(chr(c)); at += 2


def row_bytes(rost, index, *, indoor=None, grass=None):
    """The row with its string pointers made absolute (the game relocates them at load), optionally edited."""
    at = POOL + index * STRIDE
    row = bytearray(rost[at:at + STRIDE])
    strings = {}
    cursor = STR
    for field in (0x00, 0x08, 0x0C, 0x10, 0x14):
        t = rel(rost, at + field)
        text = utf16(rost, t) if t is not None else ''
        strings[field] = text
        struct.pack_into('<I', row, field, cursor)
        cursor += 2 * len(text) + 2
        cursor = (cursor + 3) & ~3
    if indoor is not None:
        struct.pack_into('<I', row, 0x18, indoor)
    if grass is not None:
        struct.pack_into('<I', row, 0x1C, grass)
    return bytes(row), strings


def case(payload, rost, index, *, indoor=None, grass=None, tod=0, temp=60.0, precip=0.9, wind=500.0, haze=0.3):
    m = M(payload)
    row, strings = row_bytes(rost, index, indoor=indoor, grass=grass)
    m.u.mem_write(ROW, row)
    cursor = STR
    for field in (0x00, 0x08, 0x0C, 0x10, 0x14):
        m.u.mem_write(cursor, strings[field].encode('utf-16le') + b'\0\0')
        cursor += 2 * len(strings[field]) + 2
        cursor = (cursor + 3) & ~3
    m.put(0xE5FE64, ROW)
    m.put(0xE60184, tod)
    m.f32(0xE5FFA4, temp); m.f32(0xE5FFAC, precip); m.f32(0xE600C0, wind); m.f32(0xE600C4, haze)
    m.skip = {0xE2DB0}                                   # an unrelated settings call before the suffix logic
    stop = m.run(0x62BE0, 0x62CF4)
    bundle = m.wstr(0xB306D0)
    after = dict(temperature=m.rf(0xE5FFA4), precipitation=m.rf(0xE5FFAC), wind=m.rf(0xE600C0), haze=m.rf(0xE600C4))
    # the team-package weather character is recomputed after the reset from the same two predicates
    m.run(0x77BE0, STOP); rain = m.u.reg_read(x86.UC_X86_REG_EAX)
    m.run(0x77BB0, STOP); snow = m.u.reg_read(x86.UC_X86_REG_EAX)
    package_char = 'r' if (rain or snow) else 'd'
    # light rig choice (FUN_000641c0 stores the table pointer at 0xB34774, then tail-jumps into the installer)
    m.put(0xB34774, 0)
    m.run(0x641C0, 0xF2360)
    rig = m.get(0xB34774)
    # player shadow scene name (0x91112 .. the push before the SCNE lookup at 0x91146)
    m.run(0x91112, 0x91146)
    esp = m.u.reg_read(x86.UC_X86_REG_ESP)
    shadow = m.wstr(m.get(esp))
    return dict(stadium=strings[0x00], code=strings[0x0C], indoor=struct.unpack_from('<I', row, 0x18)[0],
                grass=struct.unpack_from('<I', row, 0x1C)[0], tod=tod, weather_in=dict(temperature=temp, precipitation=precip,
                wind=wind, haze=haze), bundle=bundle, weather_after=after, team_package_weather=package_char,
                light_rig=hex(rig), shadow_scene=shadow, stopped_at=hex(stop))


RIGS = {0x4E73B0: "day", 0x4E74D0: "night_indoor", 0x4E7830: "rain", 0x4E7950: "snow", 0x4E7A70: "afternoon"}


def probe(payload, rost, index, **kw):
    r = case(payload, rost, index, **kw)
    r["light_rig"] = RIGS.get(int(r["light_rig"], 16), r["light_rig"])
    return r


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xbe"); ap.add_argument("rost")
    ap.add_argument("--index", type=int, default=24)
    ap.add_argument("--tod", type=int, default=0)
    ap.add_argument("--temp", type=float, default=60.0)
    ap.add_argument("--precip", type=float, default=0.9)
    a = ap.parse_args(argv)
    r = probe(open(a.xbe, "rb").read(), open(a.rost, "rb").read(), a.index, tod=a.tod, temp=a.temp, precip=a.precip)
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

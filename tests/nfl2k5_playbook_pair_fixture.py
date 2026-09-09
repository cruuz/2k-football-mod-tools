"""Bounded instruction harness for the playbook pair owner, never a game launch."""
from pathlib import Path
import struct

from mod_editor.core import nfl2k5_playbook_pair as pair

try:
    import unicorn as uc
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX
    from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP, UC_X86_REG_EFLAGS
except ImportError:
    uc = None

BODY = 0x13390
CODE, STATE, RO = 0x2000000, 0x2100000, 0x2200000
SOURCE, DONOR, OUTPUT = 0x3000000, 0x3020000, 0x3040000
STACK, STOP = 0x4000000, 0x2010000


def relocate(resource, base):
    """Mirror the pinned retail field-relative relocation, without game logic."""
    b = bytearray(resource[32:])
    if len(b) != BODY:
        raise ValueError("expected one fixed PLAY body")
    nf, np, nc = struct.unpack_from("<3I", b, 0x34)
    fields = [0x30, 0x44, 0x48, 0x60, 0x64, 0x68]
    fields += [0x134+i*180 for i in range(nf)]
    fields += [0x993c+i*16 for i in range(nc)]
    for i in range(np):
        fields += [0x33fc+i*96] + [0x3408+i*96+j*8 for j in range(11)]
    for at in fields:
        value = struct.unpack_from("<i", b, at)[0]
        if value:
            struct.pack_into("<I", b, at, (base+at-1+value)&0xffffffff)
    return bytes(b)


def serialize(body, base):
    b = bytearray(body)
    nf, np, nc = struct.unpack_from("<3I", b, 0x34)
    fields = [0x30, 0x44, 0x48, 0x60, 0x64, 0x68]
    fields += [0x134+i*180 for i in range(nf)]
    fields += [0x993c+i*16 for i in range(nc)]
    for i in range(np):
        fields += [0x33fc+i*96] + [0x3408+i*96+j*8 for j in range(11)]
    for at in fields:
        value = struct.unpack_from("<I", b, at)[0]
        if value:
            struct.pack_into("<I", b, at, (value-base-at+1)&0xffffffff)
    b[:0x30] = bytes.fromhex("000000000000000000000000504c415911000000edffffff000000000000000070006c00620000000000000000000000")
    return b"PLAY"+struct.pack("<II", BODY, BODY)+bytes(20)+bytes(b)


class Machine:
    def __init__(self):
        self.u = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        self.u.mem_map(0x10000, 0x1800000)
        for va, size in ((CODE, 0x20000), (STATE, 0x1000), (RO, 0x1000),
                         (SOURCE, 0x100000), (STACK, 0x100000)):
            self.u.mem_map(va, size)
        self.u.mem_write(CODE, pair.code_for(CODE, STATE, RO))
        self.u.mem_write(RO, pair.read_only_bytes(CODE, RO))
        self.events, self.frees = [], []
        self.heap_next = OUTPUT
        self.queue_result = 1
        self.alloc_fail = False
        self.callbacks = []
        self.stub_addresses = {pair.SYMBOLS[n] for n in
            ("heap_native", "allocate_native", "free_native", "queue_native", "unload_native", "notice_native")}
        for at in self.stub_addresses:
            self.u.mem_write(at, b"\xc3")
        self.u.hook_add(uc.UC_HOOK_CODE, self._stub, begin=0x10000, end=0x1800000)

    def get(self, at):
        return struct.unpack("<I", self.u.mem_read(at, 4))[0]

    def put(self, at, value):
        self.u.mem_write(at, struct.pack("<I", value))

    def text(self, at):
        out = bytearray()
        for i in range(256):
            b = bytes(self.u.mem_read(at+i*2, 2))
            if b == b"\0\0":
                return out.decode("utf-16le")
            out.extend(b)
        raise AssertionError("unbounded UI text")

    def _stub(self, machine, address, _size, _user):
        if address not in self.stub_addresses:
            return
        cx, dx = machine.reg_read(UC_X86_REG_ECX), machine.reg_read(UC_X86_REG_EDX)
        sp = machine.reg_read(UC_X86_REG_ESP)
        result, pop = 0, 0
        symbols = pair.SYMBOLS
        if address == symbols["heap_native"]:
            result = 0xb04e24
        elif address == symbols["allocate_native"]:
            self.events.append(("allocate", cx, dx))
            if not self.alloc_fail:
                result = self.heap_next
                self.heap_next += (dx+0xfff)&~0xfff
        elif address == symbols["free_native"]:
            self.frees.append(cx)
        elif address == symbols["queue_native"]:
            args = [self.get(sp+4+i*4) for i in range(4)]
            self.events.append(("queue", self.text(cx), self.text(dx), *args))
            self.callbacks.append(args[3])
            result, pop = self.queue_result, 16
        elif address == symbols["unload_native"]:
            self.events.append(("unload", self.text(cx)))
        elif address == symbols["notice_native"]:
            self.events.append(("notice", self.text(dx)))
        machine.reg_write(UC_X86_REG_EAX, result)
        machine.reg_write(UC_X86_REG_EIP, self.get(sp))
        machine.reg_write(UC_X86_REG_ESP, sp+4+pop)

    def call(self, label, *args, ecx=0, edx=0, stop=STOP, count=150000000):
        sp = STACK+0xf0000
        self.u.mem_write(sp, struct.pack("<"+"I"*(len(args)+1), stop, *args))
        self.u.reg_write(UC_X86_REG_ESP, sp)
        self.u.reg_write(UC_X86_REG_ECX, ecx)
        self.u.reg_write(UC_X86_REG_EDX, edx)
        self.u.reg_write(UC_X86_REG_EFLAGS, 2)
        address = CODE+pair.assembly.LABELS[label] if isinstance(label, str) else label
        self.u.emu_start(address, stop, count=count)
        if self.u.reg_read(UC_X86_REG_EIP) != stop:
            raise AssertionError("instruction budget exhausted")
        return self.u.reg_read(UC_X86_REG_EAX)

    def choose(self, home=3, away=0, mode=4):
        self.put(0xe5ff80,mode)
        for side in range(2):
            team, entry, code = SOURCE+0x90000+side*0x1000, SOURCE+0x90200+side*0x1000, SOURCE+0x90300+side*0x1000
            self.put(0xe5fe68+side*4, team)
            self.put(0xe5fe78+side*4, entry)
            self.put(team+0x110, entry)
            self.put(entry+4, code)
            self.u.mem_write(code, ("KC\0" if side==0 else "BAL\0").encode("utf-16le"))
            self.put(STATE+12+side*64, (home, away)[side])
            self.put(STATE+16+side*64, team)

    def merge(self, offense, defense):
        a, b = relocate(offense, SOURCE), relocate(defense, DONOR)
        self.u.mem_write(SOURCE, a); self.u.mem_write(DONOR, b)
        self.u.mem_write(OUTPUT-16, b"\xa5"*16)
        self.u.mem_write(OUTPUT+BODY, b"\xa5"*16)
        result = self.call("pair_merge", OUTPUT, SOURCE, DONOR)
        if bytes(self.u.mem_read(SOURCE, BODY)) != a or bytes(self.u.mem_read(DONOR, BODY)) != b:
            raise AssertionError("merge mutated a source")
        for at in (OUTPUT-16, OUTPUT+BODY):
            if bytes(self.u.mem_read(at,16)) != b"\xa5"*16:
                raise AssertionError("merge exceeded its destination")
        return result, bytes(self.u.mem_read(OUTPUT, BODY))


def synthetic(*, offense=1, defense=1, marker=1):
    """At most 79 KiB, with different unit roles, scripts and auxiliary bits."""
    b = bytearray(BODY)
    struct.pack_into("<I", b, 0xc, 0x59414c50)
    struct.pack_into("<4I", b, 0x34, 2, offense+defense, 2, 4)
    def pointer(at, target):
        struct.pack_into("<I", b, at, (target-at+1)&0xffffffff)
    for at, target in ((0x44,0x134),(0x48,0x245c),(0x60,0x33fc),(0x64,0x993c),(0x68,0x9adc)):
        pointer(at, target)
    cursor = 0x10840
    def name(at, text):
        nonlocal cursor
        encoded = (text+"\0").encode("utf-16le")
        pointer(at, cursor); b[cursor:cursor+len(encoded)] = encoded; cursor += len(encoded)
    name(0x30, f"Book {marker}")
    for i in range(2):
        f, a, c = 0x134+i*180, 0x245c+i*80, 0x993c+i*16
        name(f, f"Formation {i}"); struct.pack_into("<I", b, f+4, i*4<<8)
        b[f+0xd:f+0x18] = bytes(range(11))
        struct.pack_into("<36H", b, a, *([0x7ff]*36))
        struct.pack_into("<H", b, a, (offense if i else 0)|0xe00)
        struct.pack_into("<II", b, a+72, i|0xa000, 1<<i)
        name(c, f"Category {i}")
        b[c+4:c+16] = bytes([11 if i else 0, *range(11)])
        for j in range(5):
            b[0x4c+i*10+j*2] = i
        b[0x9adc+i*16:0x9adc+i*16+16] = bytes([1,0,marker,i,0,0,0,0,1,2,marker,i,0,0,0,0])
    for i in range(offense+defense):
        at = 0x33fc+i*96; family = int(i>=offense)
        name(at, f"Play {marker} {i}"); struct.pack_into("<I", b, at+4, family<<6)
        for j in range(11):
            struct.pack_into("<I", b, at+8+j*8, 0x1102)
            pointer(at+12+j*8, 0x9adc+family*16)
    struct.pack_into("<I", b, 0x1083c, (cursor-0x10840)//2)
    return b"PLAY"+struct.pack("<II", BODY, BODY)+bytes(20)+bytes(b)

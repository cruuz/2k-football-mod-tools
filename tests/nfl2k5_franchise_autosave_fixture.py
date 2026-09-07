"""Bounded x86 harness. Explicit storage/rendering service boundaries, no Xbox boot."""
import importlib.util
import os
from pathlib import Path
import struct

from mod_editor.core import nfl2k5_franchise_autosave as a
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None


class Machine:
    STACK, STOP, MANAGER, SCENE = 0x3008000, 0x3100000, 0x2200000, 0x2201000
    DEVICES, DEVICE, BUFFER, NAME, FRAME = 0x2202000, 0x2203000, 0x2300000, 0x2204000, 0x2205000

    def __init__(self, payload):
        import unicorn as u
        from unicorn import x86_const as x
        self.u, self.x = u, x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1510000-0x10000)
        image = XbeImage(payload)
        for s in image.sections:
            if s.raw_size:
                self.uc.mem_write(s.start, image.read(s.start, s.raw_size))
        self.uc.mem_protect(0x11000, 0x410000, u.UC_PROT_READ | u.UC_PROT_EXEC)
        for r in a.space.layout(payload)["regions"]:
            s = image.section(r["va"])
            flags = u.UC_PROT_READ | (u.UC_PROT_WRITE if s.writable else 0) | (u.UC_PROT_EXEC if s.executable else 0)
            self.uc.mem_protect(r["va"], r["size"], flags)
        for va, size in ((0x2200000, 0x20000), (self.BUFFER, 0x100000), (0x3000000, 0x10000), (self.STOP, 4096)):
            self.uc.mem_map(va, size)
        alloc = a.allocations(payload)
        self.state = alloc["data"]["va"]
        self.labels = {name: alloc["code"]["va"]+offset for name, offset in a.assembly.LABELS.items()}
        self.hooks = {}
        self.events = []
        self.put(self.MANAGER+0x100, 0)
        self.put(self.MANAGER, a.DESK_VA)
        self.put(self.MANAGER+0x10C, 0x2206000)
        self.put(0xAA2140, self.SCENE)
        self.put(self.SCENE+4, 0x40400000)
        self.put(0xAA2400, 0x40400000)
        self.put(0xE576A0, 2)
        self.put(0xBDBDB0, 1)
        self.put(0xBDBDBC, self.DEVICES)
        self.put(self.DEVICES, self.DEVICE)
        self.put(self.DEVICES+8, 1)
        self.put(self.DEVICES+0x1C, 1)
        self.put(0xBDC1D0, self.NAME)
        self.put(0xBDC1D4, 9)
        self.put(0xBDC1CC, 0xAFCAC)
        self.uc.mem_write(self.NAME, "Franchise1\0".encode("utf-16le"))
        self.stub(0x142DD0, lambda: self.ret(1))
        self.stub(0x16BB20, lambda: (self.events.append("discover"), self.ret()))
        self.stub(0x16B740, self.select_device)
        self.stub(0x16A640, lambda: (self.events.append("close"), self.ret()))
        self.stub(0x14E520, lambda: (self.events.append(("notice", self.string(self.reg("EDX")))), self.ret()))

    def string(self, va):
        result = bytearray()
        for offset in range(0, 512, 2):
            word = bytes(self.uc.mem_read(va+offset, 2))
            if word == b"\0\0":
                return result.decode("utf-16le")
            result.extend(word)
        raise AssertionError("unterminated string")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        for va in list(self.hooks):
            self.unstub(va)
        self.uc = None

    def get(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def reg(self, name, value=None):
        register = getattr(self.x, "UC_X86_REG_"+name)
        if value is None:
            return self.uc.reg_read(register)
        self.uc.reg_write(register, value & 0xFFFFFFFF)

    def ret(self, value=0, pop=0):
        sp = self.reg("ESP")
        self.reg("EAX", value)
        self.reg("EIP", self.get(sp))
        self.reg("ESP", sp+4+pop)

    def stub(self, va, action):
        self.unstub(va)
        self.hooks[va] = self.uc.hook_add(self.u.UC_HOOK_CODE, lambda *_: action(), begin=va, end=va)

    def unstub(self, va):
        if va in self.hooks:
            self.uc.hook_del(self.hooks.pop(va))

    def select_device(self):
        index = self.get(self.reg("ESP")+4)
        self.events.append(("select", index))
        self.put(0xBDBDB8, index)
        self.ret(pop=4)

    def call(self, entry, *, args=(), stop=None, budget=200000, **registers):
        self.put(self.STACK, self.STOP)
        for n, value in enumerate(args, 1):
            self.put(self.STACK+n*4, value)
        initial = dict(ESP=self.STACK, EAX=0, ECX=0, EDX=0, ESI=0x22222222,
                       EBX=0x11111111, EDI=0x33333333, EBP=0x44444444, EFLAGS=0x202)
        initial.update({name.upper(): value for name, value in registers.items()})
        for name, value in initial.items():
            self.reg(name, value)
        target = self.STOP if stop is None else stop
        self.uc.emu_start(self.labels.get(entry, entry), target, count=budget)
        if self.reg("EIP") != target:
            raise AssertionError(f"instruction budget exhausted at {self.reg('EIP'):#x}")
        if stop is None and self.reg("ESP") != self.STACK+4+4*len(args):
            raise AssertionError(f"unbalanced stack {self.reg('ESP'):#x}")
        return self.reg("EAX")

    def ready(self):
        self.call("toggle")
        self.call("load_slot", ebp=0)
        self.put(self.state+4, 1)

    def tick(self):
        return self.call("desk", ecx=self.MANAGER)

    def native_desk_services(self):
        """Execute 6E4E0 event dispatch and 142DD0 Desk update, substituting
        drawing/input and the generic screen handler after the custom hook.
        """
        self.unstub(0x142DD0)
        for va in (0x14FC30, 0x14FC40, 0x13EC40):
            self.stub(va, lambda: self.ret())
        self.stub(0xF3E90, lambda: self.ret(1))
        self.stub(0x2F030, lambda: self.ret(pop=4))

    def event_tick(self):
        return self.call(0x6E4E0, args=(6,), ecx=self.MANAGER, edx=0)

    def native_save_services(self, *, fail=None):
        """Execute retail 16E3F0, 16BE80 and 16C2F0. Stub memory allocation,
        serializers for unrelated state, device/OS async services and drawing.
        The native routing, confirmation, progress, result checks and cleanup
        are executed; stubbed I/O success is NOT a physical signed-save proof.
        """
        self.fail = fail
        self.io_error = 0
        self.saved = None
        self.dialogs = []
        self.stub(0x16A260, lambda: self.ret(1))
        self.stub(0x16A6A0, lambda: self.ret())
        self.stub(0x16AB70, lambda: self.ret())
        self.stub(0x16A9F0, lambda: self.ret(0xAFCAC))
        self.stub(0x16AA10, lambda: self.ret(0xAFCAC))
        self.stub(0x16AB50, lambda: self.ret(0))
        self.stub(0x38FB0, lambda: self.ret(0))
        self.stub(0x48700, lambda: self.ret(0 if fail == "allocation" else self.BUFFER))
        self.stub(0x48870, lambda: (self.events.append("free"), self.ret()))
        self.stub(0xA5470, lambda: self.ret())
        self.stub(0xC1F90, lambda: self.ret())
        self.stub(0x16A0F0, lambda: self.ret(0x91020))
        self.stub(0xC5310, lambda: self.ret())
        self.stub(0x2D0790, lambda: self.ret())
        self.stub(0x2D0780, lambda: self.ret(0x165B0))
        self.stub(0x4A400, lambda: self.ret(pop=4))
        self.stub(0x3A790, lambda: self.ret(0))
        self.stub(0x3A750, lambda: self.ret(self.io_error))
        self.stub(0x14E440, self.dialog)
        self.stub(0x16B870, lambda: self.ret(pop=4))
        # Observe, then execute the real failure handler, its error mapping,
        # native dialog call and state reset. Only device refresh is bounded.
        self.stub(0x16BD70, lambda: self.events.append("native_failure"))

        def complete_io(kind, pop):
            self.events.append(kind)
            if kind == "write":
                self.saved = bytes(self.uc.mem_read(self.get(self.reg("ESP")+4), 0xAFCAC))
            self.put(0xBDBDA0, 0)
            self.put(0xBDBDB4, 0 if fail == kind else 1)
            if fail == kind:
                self.io_error = 6
            self.ret(1, pop)
        self.stub(0x3B4B0, lambda: complete_io("delete", 8))
        self.stub(0x3AF30, lambda: complete_io("create", 16))
        self.stub(0x3B340, lambda: complete_io("write", 24))
        self.stub(0x3AE10, lambda: complete_io("commit", 8))

    def dialog(self):
        sp = self.reg("ESP")
        callback = self.get(sp+8)
        self.dialogs.append(callback)
        # Success/overwrite prompts are still reached for manual saves. Native
        # progress callbacks receive the OS completion outcome supplied above.
        self.ret(2, 24)

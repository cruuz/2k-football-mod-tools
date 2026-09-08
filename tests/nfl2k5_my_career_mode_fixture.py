"""Bounded generic-mode CPU fixture. No disc/pack or Xbox boot is materialized."""
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_my_career_fixture import Machine as BinderMachine


class Machine(BinderMachine):
    ARENA, OUT = 0x2400000, 0x2600000

    def __init__(self, payload):
        super().__init__(payload)
        self.labels = mode.code_for(self.code["va"], self.state)[1]
        self.hooks = {}
        self.events = []
        self.uc.mem_map(self.ARENA, 0x100000)
        self.uc.mem_map(self.OUT, 0x100000)
        self.uc.mem_map(0x2A00000, 0x200000)
        self.heap_next = 0x2A00000
        self.put(0xB72804, self.ARENA)
        self.put(0xB72808, 0x91000)
        self.put(0xB72918, self.ARENA)

    def replace_stub(self, va, action):
        if va in self.hooks:
            self.uc.hook_del(self.hooks.pop(va))
        if action is not None:
            self.hooks[va] = self.uc.hook_add(self.u.UC_HOOK_CODE, lambda *_: action(), begin=va, end=va)

    def close(self):
        for hook in self.stubs + list(self.hooks.values()):
            self.uc.hook_del(hook)
        self.stubs.clear()
        self.hooks.clear()
        self.uc = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def frontend(self, roster):
        """Native menu stack and retail ROST, with layout/hardware seams.

        This executes C0500 relative fixups. It does not load a Franchise,
        fabricate a player or bypass any franchise initializer.
        """
        if len(roster) != 593760 or roster[0x0C:0x10] != b"ROST":
            raise ValueError("the bounded retail ROST resource is required")
        self.root = self.ARENA
        self.put(0xE576A0, 0)
        self.put(0xB7280C, len(roster) - 64)
        self.uc.mem_write(self.ARENA, roster[64:])
        self.call(0xC0500, ecx=self.ARENA, budget=1000000)
        self.manager = self.BODIES + 0x1000
        self.put(self.manager, 0x515660)
        self.put(self.manager + 0x100, 0)
        self.put(self.manager + 0x10C, self.manager + 0x1000)
        self.put(0xBD8050, 1)
        # Native preview registration uses an initially empty intrusive list.
        self.put(0xA6C708, 0xA6C708)
        self.put(0xA6C70C, 0xA6C708)
        self.inputs, self.dialog_answer = 0, 2
        self.put(0xC88A30, 0xFFFFFFFF)  # unopened native network socket
        for va in (0xF2920, 0xF3CD0, 0xF37E0, 0xF2660, 0x14D310, 0x14D390,
                   0x14FF70, 0x14FC20, 0x6B730, 0x6B740, 0x2C8810, 0x2C8880,
                   0x2A08F0, 0x110E60, 0x27C820, 0x27CDF0, 0x27C830, 0x91940, 0x91900):
            self.replace_stub(va, lambda: self.ret())
        self.replace_stub(0x192020, lambda: self.ret(1))  # controller/device-ready UI service
        self.replace_stub(0x37A31F, lambda: self.ret(1))  # console configuration service
        self.replace_stub(0x48BC0, lambda: self.ret(0))  # deterministic entropy service
        self.replace_stub(0x14E440, lambda: self.ret(self.dialog_answer, pop=24))

        def notice():
            p = self.reg("EDX")
            raw = bytes(self.uc.mem_read(p, 200))
            end = next(i for i in range(0, len(raw), 2) if raw[i:i+2] == b"\0\0")
            text = raw[:end].decode("utf-16le")
            self.events.append(("notice", text))
            self.ret()

        self.replace_stub(0x14E520, notice)
        for va in (0xF3750, 0xF3780, 0xF3720):
            self.replace_stub(va, lambda: self.ret(self.inputs if self.reg("EDX") == 0 else 0, pop=4))
        for va in (0x70A10, 0x70A30, 0x709F0):
            self.replace_stub(va, lambda: self.ret(self.inputs if self.reg("ECX") == 0 else 0))

        def consume():
            self.inputs &= ~self.get(self.reg("ESP") + 4)
            self.ret(pop=4)

        self.replace_stub(0x70A50, consume)
        for va in (0x709B0, 0x128670, 0x131A10):
            self.replace_stub(va, lambda: self.ret(int(self.reg("ECX") == 0)))
        for va in (0x2498A0, 0x128C70, 0x128C60, 0xEC200, 0x771F0):
            self.replace_stub(va, lambda: self.ret())

    def depth(self):
        return self.get(self.manager + 0x100)

    def top(self):
        return self.get(self.manager + 8 * self.depth())

    def event(self, event, *, budget=1000000):
        return self.call(0x6E4E0, ecx=self.manager, eax=self.manager, args=(event,), budget=budget)

    def frame(self, buttons=0, *, budget=1000000):
        self.inputs = buttons
        try:
            return self.event(6, budget=budget)
        finally:
            self.inputs = 0

    def select(self, index, *, budget=1000000):
        self.put(self.manager + 8 * self.depth() + 4, index)
        return self.frame(0x100, budget=budget)

    def ui_heap(self):
        """Bounded replacement for the native heap service, with distinct blocks."""
        def allocate():
            size = self.reg("EDX")
            pointer = self.heap_next
            self.heap_next += (size + 15) & ~15
            if self.heap_next > 0x2C00000:
                raise AssertionError("bounded UI heap exhausted")
            self.ret(pointer)
        self.replace_stub(0x48700, allocate)
        self.replace_stub(0x48870, lambda: self.ret())

    def child_services(self):
        self.game_services()
        self.ui_heap()
        # Device enumeration and texture-atlas loading are hardware/asset seams.
        self.put(self.BODIES, self.BODIES + 0x400)
        self.replace_stub(0x3BAF0, lambda: self.ret(pop=12))
        for va in (0x142D50, 0x6A510):
            self.replace_stub(va, lambda: self.ret())

    def game_services(self, *, load=True):
        """Scene, renderer, audio and engine-step seams for stack-route tests.

        Native input, menu construction, START, Team Select, game dispatch,
        pause/confirmation, POP, and 645D0's season-commit dispatch remain live.
        This is not a simulated or witnessed football match.
        """
        for va in (0x27C040, 0x27C050, 0x27C2C0, 0x27C4D0, 0x6F290, 0x6EAD0,
                   0x142FB0, 0x165C10, 0x142B40, 0x27D3A0,
                   0x77200, 0x2C1780, 0x2C17C0, 0x2C0AE0, 0x2C0A70, 0x2C2220,
                   0x2C2240, 0x2C21F0, 0x31F760, 0xED540,
                   0xF6510, 0xF6290, 0xF6210, 0xF5FE0, 0xF53C0, 0x62BE0,
                   0xF5380, 0xF5D30, 0x125C50, 0x64620, 0x64650,
                   0x834F0, 0x61950, 0xF6030, 0xF72A0, 0xF5C70, 0xF5170,
                   0xF61E0, 0x432D0, 0xF6230, 0xF5C80,
                   0xCF840, 0x773F0, 0x9FC40, 0x9FCD0, 0x8AA30, 0x8AA40,
                   0x14F9E0, 0x128D60, 0x128A70, 0x8BEA0, 0x146790,
                   0x8BE90, 0x8BEF0, 0x131500):
            self.replace_stub(va, lambda: self.ret())
        self.replace_stub(0x8C0C0, lambda: self.ret(pop=4))
        self.replace_stub(0xED5E0, lambda: self.ret(pop=4))
        for va in (0x33BFB0, 0x2C1230, 0x2C0EE0, 0x192020, 0x77390):
            self.replace_stub(va, lambda: self.ret(1))
        self.replace_stub(0xF5430, lambda: self.ret(int(load)))
        self.replace_stub(0x64710, lambda: (self.put(0xA83A18, 3), self.put(0xA83A10, 1), self.ret()))
        self.replace_stub(0x649C0, lambda: (self.put(0xA83A10, 0), self.ret()))
        self.replace_stub(0x64CD0, lambda: self.ret() if self.get(0xA83A18) == 3 else None)

    def native_load(self, save, *, requested=True, read_ok=True, capacity=0x91000):
        """Execute 16E540 dispatch, metadata admission and ALL four deserializers.

        Only storage/authentication completion, heap allocation/free and six
        roster preview refresh services are substituted. No serializer or
        MyCareer decisions are replaced by the fixture.
        """
        self.put(0xB72808, capacity)
        self.put(self.state + 2580, int(requested))
        self.put(0xBDBDBC, self.BODIES)
        self.put(0xBDBDB8, 0)
        self.put(self.BODIES + 8, 1)
        self.put(self.BODIES + 0x1C, 1)
        self.put(0xBDC1D4, 9)
        self.put(0xBDC1CC, len(save))
        for va in (0x77AE0, 0x77B20, 0x77A90, 0x77AB0, 0x77470,
                   0x38FB0, 0x48870):
            self.replace_stub(va, lambda: self.ret())
        self.replace_stub(0x77B00, lambda: self.ret(self.get(self.ARENA + 0x1C)))
        self.replace_stub(0x16A260, lambda: self.ret(1))
        self.replace_stub(0x48700, lambda: self.ret(self.SAVE))
        self.replace_stub(0x16C560, lambda: (self.events.append("native_bad_size"), self.ret(pop=4)))

        def read():
            self.events.append("authenticated_read" if read_ok else "failed_read")
            self.uc.mem_write(self.SAVE, save)
            self.ret(int(read_ok), pop=12)

        self.replace_stub(0x16C880, read)
        self.call(0x16E540, ecx=0, budget=8000000)
        self.root = self.get(0xB72918)

    def loaded_menu(self):
        """Native successful-load UI dispatch, CLEAR and REPLACE (16DD30).

        The storage callback has completed before this frame. Device polling
        is idle; the native completion operation and all stack changes run.
        """
        self.put(0xBDBDB0, 0)
        for va in (0x77AE0, 0x77B20, 0x77A90, 0x77AB0, 0x77470, 0x77B00):
            self.replace_stub(va, None)
        self.ui_heap()
        self.call(0x16DD30, ecx=self.manager)

    def native_save(self, *, accepted=True, allocated=True, budget=50000000):
        """Execute 16E3F0 and all serializers through the signing boundary.

        Device preflight and the native signed transaction are service seams;
        this captures their exact full buffer/length, not a physical signature.
        """
        self.saved = None
        self.put(0xBDBDBC, self.BODIES)
        self.put(0xBDBDB8, 0)
        self.put(self.BODIES + 8, 1)
        self.replace_stub(0x16A260, lambda: self.ret(1))
        self.replace_stub(0x16AB50, lambda: self.ret())  # device block-count query
        self.replace_stub(0x38FB0, lambda: self.ret())
        self.replace_stub(0x48700, lambda: self.ret(self.OUT if allocated else 0))
        self.replace_stub(0x48870, lambda: self.ret())
        self.replace_stub(0x16BE80, lambda: self.ret(int(accepted), pop=24))

        def signed_transaction():
            sp = self.reg("ESP")
            kind, size, pointer = self.get(sp + 4), self.get(sp + 16), self.get(sp + 20)
            self.events.append(("native_signing_boundary", kind, size))
            self.saved = bytes(self.uc.mem_read(pointer, size))
            self.ret(1, pop=20)

        self.replace_stub(0x16C2F0, signed_transaction)
        self.call(0x16E3F0, ecx=0, budget=budget)
        return self.saved

    def native_signature(self, body, *, fail_write=False):
        """Native signing begin/update/end and EXTRA write, no physical device.

        Executes 4B2A0, 4D520, 4C880, XCalculateSignature and its HMAC
        construction. Only SHA-1 kernel primitives, heap, console title/key
        initialization and OS path/create/write/close services are supplied.
        The title key comes from the original certificate via the existing
        audited derivation. The final EXTRA bytes are captured at WriteFile.
        """
        import hashlib
        from mod_editor.core import nfl2k5_save_writer as writer
        from tests.nfl2k5_my_career_fixture import XBE
        self.uc.mem_write(self.OUT, body)
        key = writer.derive_sig_key(XBE.read_bytes())
        self.uc.mem_write(self.OUT + 0xE0000, key)
        self.put(0x4E3C8C, self.OUT + 0xE0000)
        self.put(0x10118, self.OUT + 0xE0500)
        self.put(self.OUT + 0xE0508, 0x53450030)
        self.replace_stub(0x1F52E, lambda: self.ret(self.OUT + 0xE0100, pop=8))
        self.replace_stub(0x1F5CE, lambda: self.ret(pop=8))
        sha, writes = {}, []
        def arg(index):
            return self.get(self.reg("ESP") + 4 * index)
        def begin():
            sha[arg(1)] = hashlib.sha1()
            self.ret(pop=4)
        def update():
            sha[arg(1)].update(bytes(self.uc.mem_read(arg(2), arg(3))))
            self.ret(pop=12)
        def end():
            self.uc.mem_write(arg(2), sha[arg(1)].digest())
            self.ret(pop=8)
        for va, action in ((0x20A6A, begin), (0x20A64, update), (0x20A5E, end)):
            self.replace_stub(va, action)
        obj = self.OUT + 0xE0200
        self.uc.mem_write(obj, bytes(0xC0))
        self.put(obj + 8, 2)
        self.put(obj + 12, self.BODIES)
        if self.call(0x4B2A0, esi=obj) != 1:
            raise AssertionError("native signature initialization failed")
        if self.call(0x4D520, esi=obj, eax=len(body), edx=self.OUT, args=(0, 0)) != 1:
            raise AssertionError("native signature update failed")
        self.replace_stub(0x371E0, lambda: self.ret())
        self.replace_stub(0x3790F9, lambda: self.ret(0, pop=24))
        self.replace_stub(0x1E336, lambda: self.ret(123, pop=28))
        self.replace_stub(0x1A69F, lambda: self.ret(1, pop=4))
        def write():
            if not fail_write:
                writes.append(bytes(self.uc.mem_read(arg(2), arg(3))))
            self.put(arg(4), 0 if fail_write else arg(3))
            self.ret(int(not fail_write), pop=20)
        self.replace_stub(0x1D9BF, write)
        self.put(self.BODIES + 0x1AC, self.OUT + 0xE0300)
        self.uc.mem_write(self.OUT + 0xE0300, b"U:\\\x00")
        ok = self.call(0x4C880, esi=obj)
        self.events.append(("native_extra_write", ok, len(body)))
        return writes[-1] if writes else None

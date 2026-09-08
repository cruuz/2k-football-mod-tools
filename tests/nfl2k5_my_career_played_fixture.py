"""Native played-result fixture with explicit scene and event-input boundaries.

No stats, schedule commit, history writer, ledger or menu return is stubbed.
The football engine's final event input and end signal are supplied; this is
not a complete physical match or evidence that an off-field drive is playable.
"""
import struct

from tests.nfl2k5_my_career_mode_fixture import Machine as FrontendMachine


class Machine(FrontendMachine):
    def create(self, roster, *, club=2, position=0, preseason=True):
        self.frontend(roster)
        for rng in (0xB12680, 0xE5FCA0):
            self.call(0x48BE0, ecx=rng, edx=12345)
        if not preseason:
            # Supply the native Franchise "Preseason off" setting at entry to
            # the initializer. The entire initializer still executes normally.
            self.replace_stub(0x13EE10, lambda: self.put(0xE60120, 0))
        self.call(0x6E390, ecx=self.manager, edx=0x5015CC)
        self.select(1)
        self.select(1)
        player = self.get(0xCB8B14)
        self.uc.mem_write(player + 0x35, bytes((position,)))
        self.call(0x343460)
        for _ in range(4):
            self.frame(0x10)
        self.select(0)
        self.select(club)
        self.select(1, budget=500000000)
        self.replace_stub(0x13EE10, None)
        if self.top() != self.labels["apartment"] or self.call("primary") != player:
            raise AssertionError("native creation did not reach the Apartment")
        return player

    def cold(self, roster, source):
        self.frontend(roster)
        self.native_load(source)
        self.loaded_menu()
        self.replace_stub(0x16C880, None)
        self.child_services()
        self.replace_stub(0x177990, lambda: self.ret(pop=4))  # progress text only
        for rng in (0xB12680, 0xE5FCA0):
            self.call(0x48BE0, ecx=rng, edx=12345)

    def launch(self, *, budget=1000000):
        self.select(0, budget=budget)
        if self.top() != 0x51B908:
            raise AssertionError(f"expected Team Select, found {self.top():#x}")
        self.frame(0x10)
        if self.top() != 0x4E7EC0:
            raise AssertionError("native game descriptor was not entered")
        # These are the native match roster, team and stat constructors omitted
        # by the stack fixture's scene/engine initialization service boundary.
        for va in (0x617E0, 0x87160, 0x1D3060, 0x1F1D10, 0x1F1D70):
            self.call(va, budget=2000000)
        self.call(0xCCE00)
        return self.get(self.state + 2564)

    def appearance(self):
        player = self.get(self.state + 2564)
        side = 0xE5FC20 if player < 0xB321A0 else 0xE5FC60
        body = self.BODIES + 0x8000
        for va, value in ((0xE60268, body), (body + 0x3C, player), (body + 0x38, side)):
            self.put(va, value)
        self.call(0x1561C0, args=(0,))
        if self.call("mode_unit_present") != body:
            raise AssertionError("native assignment did not bind MyPlayer")
        return body

    def passing_event(self, yards=17):
        player = self.get(self.state + 2564)
        base = 0xB30C4C if player < 0xB321A0 else 0xB321A0
        receiver = base
        while receiver == player or self.uc.mem_read(receiver + 0x35, 1)[0] not in (3, 7, 8, 9):
            receiver += 84
            if receiver >= base + 65 * 84:
                raise AssertionError("native match has no receiver")
        event = bytearray(20)
        event[0] = 0x12  # Q1 completed pass in the native event format
        event[4] = yards
        event[12] = self.call(0xBBAA0, ecx=player)
        event[13] = self.call(0xBBAA0, ecx=receiver)
        event[16] = 12
        self.put(0xE57474, int(base == 0xB321A0) << 21)  # native drive side
        self.uc.mem_write(0xE53874, bytes(event))
        self.put(0xE53804, 1)
        self.call(0x1EDC60, ecx=0, budget=2000000)

    def value(self, player, stat, bank):
        self.call(0xCB240, ecx=player, edx=stat, args=(bank,))
        # Copy the native x87 result, without substituting its stat provider.
        self.uc.mem_write(self.STOP + 0x100, b'\xd9\x1d' + struct.pack('<I', self.STOP + 0x180) + b'\xc3')
        self.call(self.STOP + 0x100)
        return struct.unpack('<f', self.uc.mem_read(self.STOP + 0x180, 4))[0]

    def finish(self):
        # The supplied engine completion signal is the boundary under test.
        self.put(0xA83A18, 2)
        self.frame(budget=100000000)
        if self.top() != 0x4F19E8:
            raise AssertionError("native played-result dispatch lost its postgame parent")
        self.frame(budget=500000000)
        if self.top() != self.labels["apartment"]:
            raise AssertionError("postgame did not return to the Apartment")

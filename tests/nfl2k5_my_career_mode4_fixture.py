"""Bounded retail-font and presentation evidence. No display or game boot."""
import struct

from tests.nfl2k5_my_career_played_fixture import Machine as PlayedMachine


class Machine(PlayedMachine):
    def presentation(self, *, away=False):
        """Two bounded actor/model inputs, native identity and controllers.

        The receiver eligibility table and scene geometry are supplied data.
        All human, marker, receiver-index and art-input decisions stay live.
        Model/art submission are explicit leaves, not a rendered game claim.
        """
        from tests.mod_editor.test_nfl2k5_my_career_control import ControlTests
        body, side = ControlTests().load(self, 0, away)
        receiver = body + 0x100
        self.put(receiver + 0x30, 0)
        self.put(0xE60280, side)
        self.put(0xE60284, 0xE5FC20 if away else 0xE5FC60)
        for index, actor in enumerate((body, receiver)):
            at = self.BODIES + 0x10000 + 0x3000 * index
            for offset, pointer in ((4, at), (0x10, at + 0x400),
                                    (0x18, at + 0x600), (0x20, at + 0x800)):
                self.put(actor + offset, pointer)
            record = self.get(actor + 0x3C)
            self.put(record + 0x30, at + 0x1000)
            self.put(at + 0x1004, at + 0x1100)
            self.put(at + 0x100C, at + 0x1200)
            self.uc.mem_write(actor + 0x2C, bytes((3 * index, 0, 3 * index, index)))
        at = self.BODIES + 0x19000
        for address, value in ((side + 12, at), (at + 12, at + 0x100),
                (side + 8, at + 0x200), (at + 0x20C, at + 0x300),
                (at + 0x304, 0x3F800000), (0xE602EC, at + 0x400),
                (0xE5FC00, at + 0x600), (0xB616C0, 11), (0xE602B8, 11),
                (0xE6026C, 1), (0xE60264, 0)):
            self.put(address, value)
        # Role 3 receives icon 2; QB has no receiver icon. These are inputs
        # normally filled by the native play's receiver-order construction.
        self.uc.mem_write(0xBDFCD0, b'\xff' * 22)
        self.uc.mem_write(0xBDFCD0 + 6 + int(away), b'\x02')
        self.models, self.art = [], []

        def submit():
            sp = self.reg('ESP')
            self.models.append(tuple(self.get(sp + 4 * i) for i in range(1, 8)))
            self.ret(pop=28)
        self.replace_stub(0xFA270, submit)
        for va, pop in ((0x1807F0, 12), (0x165760, 0), (0x1840B0, 0), (0x182480, 20)):
            self.replace_stub(va, lambda v=va, n=pop: (self.art.append(v), self.ret(pop=n)))
        # Execute native port-mode assignment, removing the older fixture's
        # device-mapping seam. Analog inputs remain the mapped zero values.
        self.uc.hook_del(self.stubs.pop(0))
        self.call(0x1561C0, args=(0,))
        self.call(0x1565F0, ecx=self.get(body + 12), edx=1)
        return body, receiver, side

    def fonts(self, fonts):
        """Host-relocate pinned FONT resources; native metrics/glyphs stay live."""
        self.font_objects = {}
        for font in fonts:
            at = self.heap_next
            self.heap_next += (len(font.decoded) + 15) & ~15
            if self.heap_next > 0x2C00000:
                raise AssertionError("bounded font heap exhausted")
            self.uc.mem_write(at, font.decoded)
            obj = at + font.object_offset
            self.put(obj + 8, at + font.range_offset)
            for row in font.ranges:
                self.put(at + row['record_offset'] + 4, at + row['glyph_records_offset'])
            self.put(0xA90ECC + 4 * font.slot, obj)
            self.font_objects[obj] = font.name
        self.draws = []
        # Immediate GPU submission leaves only. Native text formatting,
        # context setup, font binding, alignment and glyph walking execute.
        for va, pop in ((0x2D2A0, 12), (0x2CB90, 8), (0x2CBE0, 0),
                        (0x2CA70, 0), (0x2CA00, 0)):
            self.replace_stub(va, lambda n=pop: self.ret(pop=n))

        def capture(_uc, va, _size, _data):
            if va == 0x47420:
                context = self.reg("ECX")
                self.draws.append(dict(text=self.string(self.reg("EDX")),
                    font=self.font_objects[self.get(context)],
                    position=struct.unpack('<3f', self.uc.mem_read(context + 16, 12)),
                    color=self.get(context + 32), vertices=[]))
            elif va == 0x2CA70 and self.draws:
                self.draws[-1]['vertices'].append(struct.unpack('<4f',
                    self.uc.mem_read(self.reg("ECX"), 16)))
        for va in (0x47420, 0x2CA70):
            self.stubs.append(self.uc.hook_add(self.u.UC_HOOK_CODE, capture, begin=va, end=va))

    def string(self, pointer, limit=128):
        out = bytearray()
        for i in range(limit):
            pair = bytes(self.uc.mem_read(pointer + 2 * i, 2))
            if pair == b'\0\0':
                return out.decode('utf-16le')
            out.extend(pair)
        raise AssertionError("unterminated bounded text")

    def draw(self):
        self.draws.clear()
        self.event(7, budget=3000000)
        return self.draws

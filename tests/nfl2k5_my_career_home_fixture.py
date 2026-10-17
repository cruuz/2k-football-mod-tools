"""Career Home (job ui1) draw capture over the bounded native menu fixtures. No display, xemu or pad.

The real navigation LAYT/MRKS traversal, row construction, row tint hook, 6BC30 text, glyph walking and the
immediate vertex path (2CBE0 colour, 2CB90 UV, 2CA70 vertex) execute. Two leaves are bounded here: 2D2A0 only
records the material and points the vertex writer at a host push buffer (as tools/player_star/emulate.py), and
2CA00 reads that buffer back. Texture lookups by name ('TXTR' through 449E0) return a stand-in descriptor and
are recorded by name; every other lookup is the navigation fixture's.
"""
import struct

from tests.nfl2k5_my_career_mode4_fixture import Machine as FontMachine
from tests.nfl2k5_my_career_navigation_fixture import install as navigation

PUSH, CONTEXT, TEXTURES = 0x3200000, 0x3280000, 0x32C0000


class Machine(FontMachine):
    def capture(self, fonts, evidence, *, textures=True):
        """Load fonts and the navigation layout, then capture draws. Call after the career exists."""
        self.events, self.lookups = [], {}
        self.fonts(fonts)
        materials = {obj + 0x40: name for obj, name in self.font_objects.items()}
        original = self.replace_stub

        def wrapped(va, action):
            if va == 0x449E0 and action is not None:
                inner = action

                def lookup():
                    kind = struct.pack('<I', self.reg('EDX')).decode('ascii')
                    if kind == 'TXTR':
                        name = self.string(self.get(self.reg('ESP') + 4))
                        if not textures:
                            self.lookups.setdefault(name, 0)
                            self.ret(0, pop=4)
                            return
                        at = self.lookups.setdefault(name, TEXTURES + 0x100 * len(self.lookups))
                        self.put(at + 0xC, 0x07710B29)  # a 128x128 P8 format word
                        self.ret(at, pop=4)
                        return
                    inner()
                return original(va, lookup)
            return original(va, action)
        self.replace_stub = wrapped
        navigation(self, evidence)
        self.replace_stub = original
        self.uc.mem_map(PUSH, 0x100000)

        def begin():
            sp = self.reg('ESP')
            material = self.get(sp + 8)
            self.events.append(dict(kind='strip', primitive=self.get(sp + 4), material=material,
                                    vertex_mode=self.reg('ECX'), matrix=self.get(sp + 12),
                                    key=self.get(material + 4), texture=self.get(material + 0x30),
                                    font=materials.get(material), verts=[]))
            self.put(CONTEXT + 0x318, 4)
            self.put(0xA6B274, CONTEXT)
            for va, value in ((0xA6B27C, PUSH), (0xA6B280, PUSH), (0xA6B284, 0), (0xA6B288, 0), (0xA6B28C, 1),
                              (0xA6B290, 0), (0xA6B2AC, 0xFFFFFFFF), (0xA6B2A0, 0), (0xA6B2A4, 0)):
                self.put(va, value)
            self.ret(pop=12)

        def end():
            count = self.get(0xA6B284)
            raw = bytes(self.uc.mem_read(PUSH, count * 28))
            self.events[-1]['verts'] = [struct.unpack_from('<3fIIff', raw, i * 28) for i in range(count)]
            self.ret()

        def text(_uc, _va, _size, _data):
            context = self.reg('ECX')
            self.events.append(dict(kind='text', text=self.string(self.reg('EDX')),
                                    font=self.font_objects.get(self.get(context)), tint=self.get(context + 32)))
        self.stubs.append(self.uc.hook_add(self.u.UC_HOOK_CODE, text, begin=0x47420, end=0x47420))
        self.replace_stub(0x2D2A0, begin)
        for va in (0x2CB90, 0x2CBE0, 0x2CA70):
            self.replace_stub(va, None)
        self.replace_stub(0x2CA00, end)

    def screen(self):
        """Native event 7 for the top screen: (owned text, owned quads, glyph strips, native rows)."""
        self.events.clear()
        self.native_rows.clear()
        self.event(7, budget=8000000)
        texts = [e for e in self.events if e['kind'] == 'text' and e['text'].strip()]
        strips = [e for e in self.events if e['kind'] == 'strip']
        quads = [e for e in strips if e['font'] is None]
        glyphs = [e for e in strips if e['font'] is not None]
        rows = [r['text'] for r in self.native_rows if r['color'] >> 24 == 0xFF and r['text']][::-1]
        selected = [r['text'] for r in self.native_rows if r['color'] == 0xFFFFFF00]
        return dict(texts=texts, quads=quads, glyphs=glyphs, rows=rows, selected=selected)

    def season_stats(self, values):
        """Supply this season's counters (CB240 bank 11) as the x87 return; the formatting stays native."""
        stub = self.STOP + 0x200

        def stat():
            self.uc.mem_write(stub, struct.pack('<f', float(values.get(self.reg('EDX'), 0))))
            self.uc.mem_write(stub + 4, b'\xd9\x05' + struct.pack('<I', stub) + b'\xc2\x04\x00')
            self.reg('EIP', stub + 4)
        self.replace_stub(0xCB240, stat)

"""b778-xs1: on-demand module prototype (Career Home loaded by the kernel's section loader when MyCareer opens).

Static (pinned USA XBE): install after Career Home, the preload flag cleared and nothing else of the section changed,
both hook sites, exact replay, refusal without Career Home, and every owner still validating. Native (Unicorn): the
gate loads once for a MyCareer screen, never for another screen, retries three times and cancels the screen change
when the load fails, and runs the replaced prologue exactly.
"""
from pathlib import Path
import importlib.util
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_module_loader as loader
from mod_editor.core import nfl2k5_my_career_home as home
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_my_career_fixture import XBE

HAVE_UC = importlib.util.find_spec("unicorn") is not None


class GateCodeTests(unittest.TestCase):
    SPANS = [(0x14BB000, 0x1000), (0x14BC000, 0x3000), (0x1505000, 0x1000)]

    def test_code_fits_and_sites_are_fixed(self):
        body, labels = loader.code_for(0x150C000, 0x150D000, 0x109C8, self.SPANS)
        self.assertEqual(len(body), loader.CODE_SIZE)
        self.assertEqual(body[labels["table"] - 0x150C000:labels["table"] - 0x150C000 + 24],
                         b"".join(struct.pack("<II", *s) for s in self.SPANS))
        (n1, va1, old1, new1), (n2, va2, old2, new2) = loader.sites(0x150C000)
        self.assertEqual((va1, old1.hex(), len(new1)), (0x6E39A, "578bfa7d51", 5))
        self.assertEqual((va2, old2.hex(), len(new2)), (0x6E2E0, "56578bfa6a05", 6))
        self.assertEqual(va1 + 5 + struct.unpack_from("<i", new1, 1)[0], 0x150C000)
        self.assertEqual(va2 + 5 + struct.unpack_from("<i", new2, 1)[0], labels["gate_replace"])
        self.assertEqual(new2[5], 0x90)

    @unittest.skipUnless(HAVE_UC, "Unicorn absent")
    def test_gate_loads_once_skips_other_screens_and_cancels_on_failure(self):
        import unicorn as uc
        from unicorn import x86_const as x86
        code_va, data_va, header = 0x150C000, 0x150D000, 0x109C8
        body, labels = loader.code_for(code_va, data_va, header, self.SPANS)
        fake, stop, resume = 0x3020000, 0x3010000, loader.REPLACE_RESUME

        def run(edx, status):
            m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
            m.mem_map(0x150C000, 0x2000)
            m.mem_write(code_va, body)
            m.mem_write(data_va, state[0])
            m.mem_map(0x4E3000, 0x1000)
            m.mem_write(loader.XE_LOAD_SECTION, struct.pack("<I", fake))
            m.mem_map(0x3000000, 0x30000)
            m.mem_write(fake, b"\xb8" + struct.pack("<i", status) + b"\xc2\x04\x00")   # mov eax, status ; ret 4
            m.mem_map(0x6E000, 0x1000)
            m.mem_write(resume, b"\xf4")    # hlt marks "the replaced prologue ran and resumed"
            stack = 0x3001000
            m.mem_write(stack, struct.pack("<I", stop))
            m.reg_write(x86.UC_X86_REG_ESP, stack)
            m.reg_write(x86.UC_X86_REG_EDX, edx)
            for reg, value in ((x86.UC_X86_REG_EBX, 0x11), (x86.UC_X86_REG_EBP, 0x22), (x86.UC_X86_REG_ECX, 0x33)):
                m.reg_write(reg, value)
            calls = []
            m.hook_add(uc.UC_HOOK_CODE, lambda mu, a, s, d: calls.append(struct.unpack("<I", mu.mem_read(mu.reg_read(x86.UC_X86_REG_ESP) + 4, 4))[0]),
                       begin=fake, end=fake)
            try:
                m.emu_start(labels["gate_replace"], stop, count=400)
            except uc.UcError:
                pass
            eip = m.reg_read(x86.UC_X86_REG_EIP)
            state[0] = bytes(m.mem_read(data_va, 32))
            regs = [m.reg_read(r) for r in (x86.UC_X86_REG_EBX, x86.UC_X86_REG_EBP, x86.UC_X86_REG_ECX, x86.UC_X86_REG_EDX)]
            return eip, calls, regs

        state = [bytes(32)]
        eip, calls, regs = run(0x0051_5660, 0)            # main menu: not a MyCareer screen
        self.assertEqual((eip, calls, regs), (resume + 1, [], [0x11, 0x22, 0x33, 0x515660]))
        eip, calls, regs = run(0x14BB0C8, 0)              # a MyCareer descriptor: load once
        self.assertEqual((eip, calls), (resume + 1, [header]))
        self.assertEqual(regs, [0x11, 0x22, 0x33, 0x14BB0C8])
        self.assertEqual(state[0][loader.LOADED], 1)
        self.assertEqual(struct.unpack_from("<I", state[0], loader.LOADS)[0], 1)
        eip, calls, _ = run(0x1505100, 0)                 # already loaded: no second load
        self.assertEqual((eip, calls), (resume + 1, []))
        state[0] = bytes(32)
        eip, calls, _ = run(0x14BB0C8, -0x3FFFFFFF)       # every try fails: three tries, screen change cancelled
        self.assertEqual((eip, calls), (stop, [header] * 3))
        self.assertEqual((state[0][loader.LOADED], state[0][loader.FAIL]), (0, 1))
        self.assertEqual(struct.unpack_from("<I", state[0], loader.ATTEMPTS)[0], 3)


@unittest.skipUnless(XBE.is_file(), "pinned USA XBE required")
class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        cls.career = mode.apply(retail_bytes())[0]
        cls.home = home.apply(cls.career)[0]
        cls.loaded, cls.receipt = loader.apply(cls.home)

    def test_install_clears_only_the_preload_flag_and_replays(self):
        before, after = self.home, self.loaded
        self.assertEqual(loader.status(before), "retail")
        self.assertEqual((space.status(after), mode.status(after), home.status(after), loader.status(after)),
                         ("applied",) * 4)
        at = space.scale_music_slots(after)[0]
        self.assertEqual(struct.unpack_from("<I", after, at)[0], home.FLAGS & ~0x02)
        old_at = space.scale_music_slots(before)[0]
        self.assertEqual(before[old_at + 4:old_at + 20], after[at + 4:at + 20])
        self.assertEqual(before[old_at + 36:old_at + 56], after[at + 36:at + 56])   # section digest unchanged
        self.assertEqual(before[home.RAW:home.RAW + home.SIZE], after[home.RAW:home.RAW + home.SIZE])
        image = XbeImage(after)
        for _name, va, _old, new in loader.sites(loader.allocation(after)[0]["va"]):
            self.assertEqual(image.read(va, len(new)), new)
        self.assertEqual(loader.apply(after)[0], after)
        self.assertEqual(home.check_static(after), home.check_static(before))

    def test_refusals(self):
        with self.assertRaises(ValueError):
            loader.apply(self.career)          # no Career Home
        bad = bytearray(self.loaded)
        at = space.scale_music_slots(self.loaded)[0]
        struct.pack_into("<I", bad, at, home.FLAGS)   # preload back on without the gate's consent
        self.assertEqual(loader.status(bytes(bad)), "foreign")
        stray = bytearray(self.home)
        struct.pack_into("<I", stray, space.scale_music_slots(self.home)[0], home.FLAGS & ~0x02)
        self.assertEqual(home.status(bytes(stray)), "foreign")   # on demand without the loader is refused


if __name__ == "__main__":
    unittest.main()

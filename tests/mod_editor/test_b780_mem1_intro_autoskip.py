"""b780-mem1: the pregame intro skips itself when DIR_INTRO could not load (nfl2k5_intro_autoskip), proved on the RC's code.

The intro's per-frame update 0x125BC0 runs under Unicorn on the v0.9 RC's own executable, with game setup run first
on its own code and roster (test_b780_mem1_heapb_headroom.Machine): at the lab's Baltimore room the director's heap B
allocation fails (heap B stays empty, H1R2), at a room of 0x1A0000 it succeeds. The skip handler 0xA2120 is hooked
to record each call (the caller's controller index in esi and the return address); 0x709B0 and 0x70A10 run natively
over the controller records at 0xB37A70 + i * 0x244.

Proved: with the director missing the owner calls the skip handler once, from the same place, for the same controller
and in the same frame as a native A press does on the RC without the owner; with the director loaded, or before the
context completes, or once the intro has ended, or outside the intro phase, nothing differs from the RC (no auto skip,
and a real A press still skips exactly as before).
"""
from pathlib import Path
import hashlib
import importlib.util
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mod_editor.core import nfl2k5_intro_autoskip as autoskip  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core import nfl2k5_practice_squad as ps  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
import test_b780_mem1_heapb_headroom as hb  # noqa: E402

UPDATE, SKIP = 0x125BC0, 0xA2120
CONTROLLERS, STRIDE = 0xB37A70, 0x244          # +0 active (0x709B0), +8 buttons (0x70A10)


@unittest.skipUnless(hb.RETAIL_XBE.is_file(), 'the owner shape checks need the pinned retail XBE')
class ShapeTests(unittest.TestCase):
    def test_the_helper_and_the_site(self):
        code = autoskip.code_for(0x14D9FC0)
        self.assertEqual(len(code), autoskip.CODE_SIZE)
        self.assertEqual(code[56:], b'\xcc' * 8)
        self.assertEqual(code[0], 0xE8)
        self.assertEqual(0x14D9FC0 + 5 + struct.unpack_from('<i', code, 1)[0], autoskip.BUTTONS)
        self.assertEqual(code[0x34:0x38], bytes.fromhex('83c810c3'))     # or eax, 0x10; ret
        site = autoskip.site_bytes(0x14D9FC0)
        self.assertEqual(autoskip.SITE_VA + 5 + struct.unpack_from('<i', site, 1)[0], 0x14D9FC0)

    def test_apply_on_retail_is_idempotent_and_lands_in_executable_memory(self):
        retail = hb.RETAIL_XBE.read_bytes()
        self.assertEqual(hashlib.sha256(retail).hexdigest(), ps.RETAIL_SHA256)
        self.assertEqual(autoskip.status(retail), 'retail')
        out, receipt = autoskip.apply(retail)
        self.assertEqual(autoskip.status(out), 'applied')
        self.assertEqual(autoskip.apply(out)[1]['status'], 'already_applied')
        code_va = int(receipt['code_va'], 16)
        base, count, table = (struct.unpack_from('<I', out, o)[0] for o in (0x104, 0x11C, 0x120))
        flags = [f for f, va, vsize in (struct.unpack_from('<3I', out, table - base + i * 0x38) for i in range(count))
                 if va <= code_va and code_va + autoskip.CODE_SIZE <= va + vsize]
        self.assertEqual(len(flags), 1, hex(code_va))
        self.assertTrue(flags[0] & 4 and flags[0] & 2, hex(flags[0]))                  # executable, loaded at boot
        self.assertEqual(XbeImage(out).read(autoskip.SITE_VA, 5), autoskip.site_bytes(code_va))

    def test_it_composes_through_a_reserved_union_in_either_order(self):
        # the build reserves the late owners' union first (throw_tuning._selected_space_requests), then installs them
        from mod_editor.core import nfl2k5_throw_tuning as tt, nfl2k5_protection_calls as calls
        retail = hb.RETAIL_XBE.read_bytes()
        requests = tt._selected_space_requests(protection_calls=True, intro_autoskip=True)
        self.assertIn(autoskip.REQUESTS[0], requests)
        base, _ = space.apply(retail, requests, scaleout=True)
        placed = {(r['owner'], r['kind']): r['va'] for r in space.layout(base)['allocations']}
        one = autoskip.apply(calls.apply(base)[0])[0]
        two = calls.apply(autoskip.apply(base)[0])[0]
        self.assertEqual(one, two)
        self.assertEqual({(r['owner'], r['kind']): r['va'] for r in space.layout(one)['allocations']}, placed)
        self.assertEqual((autoskip.status(one), calls.status(one)), ('applied', 'applied'))

    def test_a_foreign_site_refuses(self):
        retail = bytearray(hb.RETAIL_XBE.read_bytes())
        off = XbeImage(bytes(retail)).offset(autoskip.SITE_VA, 5)
        retail[off:off + 5] = b'\x90' * 5
        self.assertEqual(autoskip.status(bytes(retail)), 'foreign')
        with self.assertRaises(autoskip.IntroAutoskipError):
            autoskip.apply(bytes(retail))


@unittest.skipUnless(hb._fixtures_ready(), 'the intro proofs need NFL2K5_B780_RC_XBE, NFL2K5_B780_RC_ROST and Unicorn')
class IntroUpdateTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rc = hb.RC_XBE.read_bytes()
        assert hashlib.sha256(cls.rc).hexdigest() == hb.RC_XBE_SHA256
        cls.body = hb.RC_ROST.read_bytes()[0x20:]
        cls.owned, cls.receipt = autoskip.apply(cls.rc)
        assert len(cls.owned) == len(cls.rc) and cls.receipt['file_growth'] == 0

    def frame(self, xbe, *, loaded, buttons=0, active=1, state=1, phase=2, ready=True, controller=0, room=None):
        """Game setup, then one frame of the intro update; returns the skip handler calls [(esi, return address)]."""
        import unicorn as uni
        from unicorn.x86_const import UC_X86_REG_ESI, UC_X86_REG_ESP
        m = hb.Machine(xbe, self.body)
        got = m.setup_game(room or (0x1A0000 if loaded else hb.LAB_ROOM_RC), region=True)
        self.assertEqual(got['director'] != 0, loaded, got)
        calls = []

        def skip(_uc, _a, _s, _u):
            calls.append((m.uc.reg_read(UC_X86_REG_ESI), m.word(m.uc.reg_read(UC_X86_REG_ESP))))
            m._return(0)

        m.uc.hook_add(uni.UC_HOOK_CODE, skip, begin=SKIP, end=SKIP)
        m.ret_65d30 = 8                                        # the update's controller loop runs (the flyover)
        for i in range(8):
            m.put(CONTROLLERS + i * STRIDE, active if i == controller else 0)
            m.put(CONTROLLERS + i * STRIDE + 8, buttons if i == controller else 0)
        m.put(autoskip.INTRO_STATE, state)
        m.put(autoskip.PHASE, phase)
        m.put(autoskip.INTRO_FLAGS, autoskip.READY_BIT if ready else 0)
        heap_b = (m.word(0xBB74B0), m.word(0xBB74B4), m.word(0xBB74B0 + 0x88))
        m.call(UPDATE)
        return calls, heap_b

    def test_the_heap_b_test_reads_empty_exactly_when_the_director_failed(self):
        _, (start, end, free) = self.frame(self.rc, loaded=False)
        self.assertEqual((end - start, free), (hb.LAB_HEAP_B_CAP, hb.LAB_HEAP_B_CAP))   # H1R2's empty 6,400 B heap B
        _, (start, end, free) = self.frame(self.rc, loaded=True)
        self.assertEqual(end - start - free, hb.DIRECTOR + 128)                          # the director's 73,856 B

    def test_with_the_director_missing_the_owner_skips_like_a_native_a_press(self):
        native, _ = self.frame(self.rc, loaded=False, buttons=autoskip.A_BIT)            # a player presses A on the RC
        owned, _ = self.frame(self.owned, loaded=False)                                  # nobody presses anything
        self.assertEqual(len(native), 1)
        self.assertEqual(owned, native)                                                  # same controller, same caller
        self.assertEqual(native[0][1], 0x125C48)                                         # returns into the native loop
        self.assertEqual(self.frame(self.rc, loaded=False)[0], [])                       # the RC alone loops (H1R2)

    def test_with_the_director_loaded_nothing_changes(self):
        for buttons in (0, autoskip.A_BIT, 0x100, 0x110):
            with self.subTest(buttons=buttons):
                self.assertEqual(self.frame(self.owned, loaded=True, buttons=buttons)[0],
                                 self.frame(self.rc, loaded=True, buttons=buttons)[0])
        self.assertEqual(self.frame(self.owned, loaded=True)[0], [])

    def test_no_auto_skip_before_the_context_completes_after_the_intro_or_outside_its_phase(self):
        for label, kw in (('loading', dict(ready=False)), ('ended', dict(state=2)), ('other phase', dict(phase=3)),
                          ('no active controller', dict(active=0))):
            with self.subTest(label):
                self.assertEqual(self.frame(self.owned, loaded=False, **kw)[0], [])
                self.assertEqual(self.frame(self.owned, loaded=False, buttons=autoskip.A_BIT, **kw)[0],
                                 self.frame(self.rc, loaded=False, buttons=autoskip.A_BIT, **kw)[0])

    def test_a_heap_b_with_no_room_at_all_counts_as_missing(self):
        # 64 MB-like room: heap A takes all that is left and heap B is built with no room (the guard's empty heap)
        owned, (start, end, free) = self.frame(self.owned, loaded=False, room=1400064)
        self.assertEqual((end - start, free), (0, 0))
        self.assertEqual(owned, self.frame(self.rc, loaded=False, room=1400064, buttons=autoskip.A_BIT)[0])
        self.assertEqual(len(owned), 1)

    def test_the_skip_comes_from_the_controller_that_is_active(self):
        for controller in (0, 3, 7):
            with self.subTest(controller=controller):
                owned, _ = self.frame(self.owned, loaded=False, controller=controller)
                native, _ = self.frame(self.rc, loaded=False, buttons=autoskip.A_BIT, controller=controller)
                self.assertEqual(owned, native)
                self.assertEqual([esi for esi, _ in owned], [controller])

    def test_the_rc_with_the_owner_keeps_its_layout(self):
        # a late owner appended to the RC's sealed scale-out image: no other allocation moves, no section or page grows
        self.assertEqual(autoskip.status(self.owned), 'applied')
        self.assertEqual(hb.resident_bytes(self.owned), hb.resident_bytes(self.rc))
        before = {(r['owner'], r['kind']): r['va'] for r in space.layout(self.rc)['allocations']}
        after = {(r['owner'], r['kind']): r['va'] for r in space.layout(self.owned)['allocations']}
        self.assertEqual({k: after[k] for k in before}, before)
        self.assertEqual(set(after) - set(before), {(autoskip.OWNER, 'code')})
        changed = sum(a != b for a, b in zip(self.rc, self.owned))
        self.assertLess(changed, 900)


if __name__ == '__main__':
    unittest.main()

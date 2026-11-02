"""PROVED OFFLINE: pc patch bytes, source pins, build gating and native projection."""
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_playcall_layout as pc
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from nfl2k5_playcall_projection import DEFAULT_XBE, DEFAULT_PACK, native_proof, scene_sources, measurements


def replace_at(payload, va, value):
    buf = bytearray(payload)
    off = owner.scene.layout.sbpos.va_to_off(payload,va)
    buf[off:off+len(value)] = value
    for s in _sections(buf):
        buf[s.header_offset+36:s.header_offset+56] = section_digest(buf,s)
    return bytes(buf)


@unittest.skipUnless(DEFAULT_XBE.is_file(), 'local USA retail XBE required')
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = DEFAULT_XBE.read_bytes()
        with mock.patch.dict(os.environ, {'NFL2K5_SCOREBUG_PLAYCALL':'sprite'}):
            cls.patched, cls.receipt = owner.apply(cls.retail)

    def setUp(self):
        p = mock.patch.dict(os.environ, {'NFL2K5_SCOREBUG_PLAYCALL':'sprite'})
        p.start(); self.addCleanup(p.stop)

    def test_exact_sites_and_idempotence(self):
        self.assertEqual(owner.status(self.retail), 'retail')
        self.assertEqual(owner.status(self.patched), 'applied')
        self.assertTrue(pc.valid(self.retail,applied=False))
        self.assertTrue(pc.valid(self.patched,applied=True))
        image = XbeImage(self.patched)
        code,data = owner.sites(self.patched)
        compiled,labels = owner.code_for(code['va'],data['va'])
        self.assertEqual(image.read(code['va'],owner.CODE_SIZE),compiled)
        hook = b'\xe8'+struct.pack('<i',labels[pc.HOOK_NAME]-pc.HOOK[0]-5)
        self.assertEqual(image.read(pc.HOOK[0],5),hook)
        # b780 p2: the page strip fit replaces the one native box call of FUN_000AAFD0's loop.
        strip = b'\xe8'+struct.pack('<i',labels[pc.STRIP_HOOK_NAME]-pc.STRIP_HOOK[0]-5)
        self.assertEqual(image.read(pc.STRIP_HOOK[0],5),strip)
        self.assertEqual(XbeImage(self.retail).read(pc.STRIP_HOOK[0],5),pc.STRIP_HOOK[1])
        self.assertEqual(image.read(labels[pc.STRIP_HOOK_NAME],len(pc.strip_code_for(labels[pc.STRIP_HOOK_NAME]))),
                         pc.strip_code_for(labels[pc.STRIP_HOOK_NAME]))
        for va,old,new,_ in pc.edits():
            self.assertEqual(XbeImage(self.retail).read(va,4),old)
            self.assertEqual(image.read(va,4),new)
        again,receipt = owner.apply(self.patched)
        self.assertEqual(again,self.patched)
        self.assertEqual(receipt['changed_bytes'],0)

    def test_every_source_guard_refuses_mutation(self):
        for va,size,_,label in pc.GUARDS:
            # Mutate the last byte to avoid the normalized hook/data operands.
            at = va+size-1
            old = XbeImage(self.retail).read(at,1)
            changed = replace_at(self.retail,at,bytes([old[0]^1]))
            with self.subTest(label=label):
                self.assertEqual(owner.status(changed),'foreign')
                with self.assertRaises(ValueError): owner.apply(changed)

    def test_each_data_word_and_hook_rejects_mixed_states(self):
        for va,old,new,label in pc.edits():
            with self.subTest(label=label,va=hex(va)):
                self.assertEqual(owner.status(replace_at(self.retail,va,new)),'foreign')
                self.assertEqual(owner.status(replace_at(self.patched,va,old)),'foreign')
        self.assertEqual(owner.status(replace_at(self.patched,*pc.HOOK)),'foreign')
        self.assertEqual(owner.status(replace_at(self.patched,*pc.STRIP_HOOK)),'foreign')
        applied = XbeImage(self.patched).read(pc.STRIP_HOOK[0],5)
        self.assertEqual(owner.status(replace_at(self.retail,pc.STRIP_HOOK[0],applied)),'foreign')

    def test_build_option_off_does_not_call_owner_or_change_bytes(self):
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        with mock.patch.object(owner,'apply',wraps=owner.apply) as apply:
            unchanged,_ = tuning._apply_all(self.retail,None,catch_slider=False,scorebug_runtime=False)
            apply.assert_not_called()
        self.assertEqual(unchanged,self.retail)

    def test_build_option_on_installs_layout(self):
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        built,_ = tuning._apply_all(self.retail,None,catch_slider=False,scorebug_runtime=True)
        self.assertEqual(owner.status(built),'applied')
        self.assertTrue(pc.valid(built,applied=True))

    def test_retail_playcalling_escape_keeps_all_layout_bytes(self):
        with mock.patch.dict(os.environ, {'NFL2K5_SCOREBUG_PLAYCALL':'retail'}):
            result,_ = owner.apply(self.retail)
            self.assertEqual(owner.status(result),'applied')
            self.assertNotIn(pc.HOOK_NAME,owner.hooks())
            image = XbeImage(result)
            self.assertEqual(image.read(pc.HOOK[0],5),pc.HOOK[1])
            self.assertEqual(image.read(pc.STRIP_HOOK[0],5),pc.STRIP_HOOK[1])
            self.assertNotIn(pc.STRIP_HOOK_NAME,owner.hooks())
            for va,old,_,_ in pc.edits(): self.assertEqual(image.read(va,4),old)
            self.assertEqual(owner.status(self.patched),'foreign')
        self.assertEqual(owner.status(result),'foreign')

    def test_code_budget_and_full_manifest_site_reservations(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        code,_ = owner.code_for(0x5100000,0x5200000)
        self.assertEqual((owner.CODE_SIZE,owner.DATA_SIZE,owner.REVISION),(5888,128,15))  # b780 p2: RX 5376 -> 5888 (+512), revision 15
        # b773-hd1: +10 bytes; b778 sb2: engine 3583 -> 3613 B; b780 p2: engine 3613 -> 4082 B (+469: the ball spot and slot-free
        # spaces) and the page strip fit (+98), 5327 -> 5849 of the 5888 allocated.
        self.assertEqual(len(code.rstrip(b'\xcc')),5849)
        self.assertEqual(len(pc.code_for(0x5100000)),129)
        self.assertEqual(len(pc.strip_code_for(0x5100000)),98)
        rec = Recorder(self.retail)
        rec.observe(owner,'apply',self.retail,self.patched,self.receipt)
        for va,size in [(pc.HOOK[0],5),(pc.STRIP_HOOK[0],5)]+[(va,4) for va,*_ in pc.edits()]:
            self.assertTrue(any(int(r['start'],0)==va and r['size']==size and r['owner']==owner.OWNER
                                for r in rec.spans),hex(va))

    @unittest.skipUnless((DEFAULT_PACK/'0').is_file(), 'local retail GAMEDATA required')
    def test_native_initializers_animation_cameras_and_viewports(self):
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(DEFAULT_PACK)
        result = native_proof(self.retail,scene_sources(DEFAULT_PACK))
        self.assertEqual(result['matrix_samples'],450)
        self.assertLess(result['max_matrix_error'],.0001)
        self.assertEqual(sum(len(s['nodes']) for s in result['scene_sources']),14)
        self.assertEqual(result['viewports'][0]['before'],result['viewports'][0]['after'])
        self.assertEqual(result['menu_target'][1],16.)

    def test_measured_clearance_respects_native_menu_clip_boundary(self):
        research = Path('/media/noah/Storage/.b76-research')
        for relative in (
            'main/witness/kr_candE/ari.jpg',
            'main/witness/kr_candE/det.jpg',
            'hx/lab-F-20260929-091218/s37-hou/attempt-01/screens/09-last-play.png',
            'hx/lab-20260929-072352/ari-kickoff/attempt-02/screens/toss-0131.3s.jpg',
        ):
            frame = research / relative
            if not frame.is_file():
                self.skipTest(f'Missing private witness frame: {frame}')
        result = measurements(research)
        for row in result['frames']:
            self.assertEqual((row['bar_top_weak'],row['bar_top_strong']),(569,570))
            self.assertGreaterEqual(row['projected_bar_gap'],4.)
        self.assertGreaterEqual(result['design']['selected_menu_clip_margin'],2.)
        self.assertLessEqual(pc.SHIFT,result['design']['max_shift_for_2px_menu_clip_margin'])
        # This explicitly records the limit: a uniform shift cannot clear the
        # raised timeout tab and retain the kickoff selector inside the viewport.
        self.assertGreater(result['design']['timeout_min_shift_for_1px_gap'],
                           result['design']['max_shift_for_2px_menu_clip_margin'])

    def test_tailcall_preserves_native_abi_flags_and_registers(self):
        from nfl2k5_scorebug_projection import StaticMachine
        m = StaticMachine(self.retail); m.record=False
        try:
            cave = 0x5100000
            m.uc.mem_map(cave,4096); m.uc.mem_write(cave,pc.code_for(cave))
            for glob,_,_ in pc.SCENES: m.put(glob,0)
            regs = dict(eax=0x12345678,ebx=0x10203040,esi=0x87654321,edi=0x98765432,
                        ebp=0x11223344,ecx=0xb719d0,edx=0x4f0e20,eflags=0x246)
            args = (0x4f0e10,0x4f0e00,0x4f0df0)
            snapshots = []
            for target in (0x2ba10,cave):
                m.run(target,args,**regs)
                snapshots.append(([m.uc.reg_read(getattr(m.x,'UC_X86_REG_'+n.upper())) for n in (*regs,'esp')],
                                  bytes(m.uc.mem_read(0xb719d0,0x2b0))))
            self.assertEqual(*snapshots)
        finally: m.close()

    def test_null_and_foreign_count_scenes_are_not_written(self):
        from nfl2k5_scorebug_projection import StaticMachine
        m = StaticMachine(self.retail); m.record=False
        try:
            cave = 0x5100000
            m.uc.mem_map(cave,4096); m.uc.mem_write(cave,pc.code_for(cave))
            for i,(glob,count,_) in enumerate(pc.SCENES):
                if i==0: m.put(glob,0); continue
                desc=m.alloc(128); m.put(glob,desc); m.put(desc+0x24,count+1 if i==1 else count)
                # A changed count must not dereference this unmapped pointer;
                # the other scene has a valid count but a null nodes pointer.
                m.put(desc+0x28,0xdeadbeef if i==1 else 0)
            m.run(cave,(0x4f0e10,0x4f0e00,0x4f0df0),ecx=0xb719d0,edx=0x4f0e20)
        finally: m.close()



def _page_boxes(payload, last_index, *, current=0, node_x=42.0, flag=0):
    """Replay FUN_000AAFD0's page box loop in Unicorn and return the calls the native box draw (6D170) received.

    The node table, the two index helpers (23710, 21970) and the box primitive are replaced by fixtures; the loop, the
    colour decision and (patched payload) the strip fit run from the real bytes. Returns (calls, registers after).
    """
    import unicorn
    from nfl2k5_scorebug_projection import StaticMachine
    m = StaticMachine(payload); m.record = False
    try:
        obj, node, other, ctx = m.alloc(0x100), m.alloc(0x200), m.alloc(0x40), m.alloc(0x40)
        m.uc.mem_write(obj, bytes(0x100))
        m.uc.mem_write(obj + 0x30, bytes([current, last_index, current, last_index]))
        m.put(obj + 0x68, other); m.put(obj + 0x6c, other + 0x20)
        m.float(node + 0x30, node_x); m.float(node + 0x34, -319.0); m.float(node + 0x38, 22.0)
        stubs = {0x23710: bytes.fromhex('31c0c3'), 0x21970: bytes.fromhex('b8') + struct.pack('<I', node) + bytes.fromhex('c3'),
                 0x6d170: bytes.fromhex('c21400')}
        for va, code in stubs.items():
            m.uc.mem_write(va, code); m.uc.ctl_remove_cache(va, va + len(code))
        calls = []

        def on_box(uc, va, _size, _data):
            esp = uc.reg_read(m.x.UC_X86_REG_ESP)
            x, y, z, w, h = struct.unpack('<5f', bytes(uc.mem_read(esp + 4, 20)))
            calls.append((x, y, z, w, h, uc.reg_read(m.x.UC_X86_REG_ECX), uc.reg_read(m.x.UC_X86_REG_EDX)))
        hook = m.uc.hook_add(unicorn.UC_HOOK_CODE, on_box, begin=0x6d170, end=0x6d170)
        m.run(0xaafd0, (obj, flag), eax=ctx, limit=200000, esi=0x11111111, edi=0x22222222, ebx=0x33333333, ebp=0x44444444)
        m.uc.hook_del(hook)
        return calls, {n: m.uc.reg_read(getattr(m.x, 'UC_X86_REG_' + n.upper())) for n in ('esi', 'edi', 'ebx', 'ebp')}
    finally:
        m.close()


@unittest.skipUnless(DEFAULT_XBE.is_file(), 'local USA retail XBE required')
class PageStripTests(unittest.TestCase):
    """b780 p2-playcall: ten page boxes covered the formation name of a 30-link menu; six or more pages now fit left of it."""

    @classmethod
    def setUpClass(cls):
        cls.retail = DEFAULT_XBE.read_bytes()
        with mock.patch.dict(os.environ, {'NFL2K5_SCOREBUG_PLAYCALL': 'sprite'}):
            cls.patched = owner.apply(cls.retail)[0]

    def test_fit_model_matches_the_numbers_in_the_docstring(self):
        self.assertEqual([pc.fit(n) for n in (1, 5)], [(0, 15, 10)] * 2)
        self.assertEqual(pc.fit(6), (45, 15, 10))
        self.assertEqual(pc.fit(10), (45, 11, 7))
        self.assertEqual(pc.fit(12), (45, 9, 6))
        self.assertEqual(pc.fit(36), (45, 4, 6))
        for n in range(6, 30):
            _shift, pitch, width = pc.fit(n)
            self.assertLessEqual(pitch * n, pc.STRIP_TOTAL)
            self.assertTrue(pc.WIDTH_MIN <= width <= pc.WIDTH_MAX)
        self.assertEqual(pc.fit(12), (45, 9, 6))        # the most a formation can have: 36 links, 12 pages

    def test_five_pages_and_fewer_are_exactly_retail(self):
        for pages in range(1, 6):
            for current in (0, pages - 1):
                with self.subTest(pages=pages, current=current):
                    retail, regs_retail = _page_boxes(self.retail, pages - 1, current=current)
                    fitted, regs_fitted = _page_boxes(self.patched, pages - 1, current=current)
                    self.assertEqual(len(retail), pages if pages > 1 else 0)
                    self.assertEqual(fitted, retail)
                    self.assertEqual(regs_fitted, regs_retail)

    def test_longer_menus_move_left_and_tighten_and_change_nothing_else(self):
        # The playcall UI allows 36 links per formation: 12 pages. Up to 19 pages the boxes keep clear of each other.
        for pages in list(range(6, 20)) + [36]:
            with self.subTest(pages=pages):
                retail, regs_retail = _page_boxes(self.retail, pages - 1, current=pages // 2)
                fitted, regs_fitted = _page_boxes(self.patched, pages - 1, current=pages // 2)
                shift, pitch, width = pc.fit(pages)
                self.assertEqual(len(fitted), pages)
                self.assertEqual(regs_fitted, regs_retail, 'esi, edi, ebx and ebp come back as retail leaves them')
                for i, (before, after) in enumerate(zip(retail, fitted)):
                    # Same row, depth, height and colours (the current page stays the white box); x and width are the fit.
                    self.assertEqual(after[1:3] + after[4:], before[1:3] + before[4:])
                    self.assertEqual(before[3], 10.0)
                    self.assertEqual(after[3], float(width))
                    self.assertEqual(before[0], 107.0 + 15 * i)
                    self.assertEqual(after[0], 107.0 - shift + pitch * i)
                self.assertEqual([b[6] for b in fitted].count(0xffffffff), 1)
                if pages <= 19:
                    # The strip ends within STRIP_TOTAL units of its new start, and the boxes never overlap (a pitch of
                    # 6 holds the 6-unit minimum width at 19 pages; the 4-unit pitch floor only matters past 29).
                    self.assertLessEqual(fitted[-1][0] + fitted[-1][3] - fitted[0][0], pc.STRIP_TOTAL)
                    for a, b in zip(fitted, fitted[1:]):
                        self.assertGreaterEqual(b[0] - (a[0] + a[3]), 2.0 if pages <= 14 else 0.0)
        # The 30-link menus of the shipped books (ten pages) end 84 units sooner than retail's 252, left of "SINGLEBACK BUNCH".
        retail, _ = _page_boxes(self.retail, 9)
        fitted, _ = _page_boxes(self.patched, 9)
        self.assertEqual((retail[-1][0] + 10.0, fitted[-1][0] + fitted[-1][3]), (252.0, 168.0))

    def test_the_second_strip_and_node_position_use_the_same_fit(self):
        # The strip is anchored at its text node; a different node x moves every box by the same amount.
        base, _ = _page_boxes(self.patched, 9, node_x=42.0)
        moved, _ = _page_boxes(self.patched, 9, node_x=60.0)
        self.assertEqual([m[0] - b[0] for b, m in zip(base, moved)], [18.0] * 10)

if __name__=='__main__': unittest.main()

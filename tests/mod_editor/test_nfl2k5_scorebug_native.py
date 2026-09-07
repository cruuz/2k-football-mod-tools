"""Bounded native callbacks, allocation failures, decompression and wait witnesses.

OS file I/O and GPU completion are explicit host events. This is not a console
emulator: it cannot establish which loop the community tester encountered.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_nfl2k5_scorebug_runtime import Machine, XBE, PACK, HAVE_UC, r, art
from mod_editor.core import nfl2k5_scorebug_fonts as fonts


class Collection:
    def __init__(self, payload, pack, *, end=None, heap_bytes=8 * 1024 * 1024):
        import unicorn
        self.m = m = Machine(payload)
        m.uc.mem_map(m.HEAP + 0x400000, 12 * 1024 * 1024)
        self.pack, self.pending, self.reads, self.registered = pack, [], [], []
        self.registered_fonts = []
        self.closed = False
        heap = m.alloc(0x100)
        pool = m.alloc(heap_bytes)
        # Native heap initialization and every subsequent allocation are real.
        m.record = False
        m.run(0x48640, (heap_bytes,), ecx=heap, edx=pool, limit=10000000)
        m.record = True
        self.heap, self.free_before = heap, m.get(heap + 0x88)
        m.put(0xb12034, heap)
        handlers = m.alloc(48)
        m.put(handlers, handlers + 16)
        m.put(handlers + 8, int.from_bytes(b'TXTR', 'little'))
        m.put(handlers + 12, 0x44f10)
        m.put(handlers + 24, int.from_bytes(b'AUSB', 'little'))
        m.put(handlers + 28, 0x45940)
        m.put(handlers + 16, handlers + 32)
        m.put(handlers + 40, int.from_bytes(b'FONT', 'little'))
        m.put(handlers + 44, 0x44c10)
        m.put(0xb0957c, handlers)
        m.put(0xb09584, 1)
        m.put(0xb09598, art.HUD_START)
        m.put(0xb0959c, 0)
        m.put(0xb095a0, end if end is not None else art.HUD_START + art.HUD_SIZE + art.RUNTIME_APPEND_SIZE)
        m.put(0xb095a4, 0)
        m.put(0xb095b8, 0)
        # File I/O request/completion; no nested synchronous completion.
        m.uc.mem_write(0x48ff0, bytes.fromhex('b801000000c21400'))
        m.uc.mem_write(0x48fc0, b'\xc3')
        # No unrelated collection is queued after this fixture collection.
        m.uc.mem_write(0x43be0, bytes.fromhex('31c0c3'))
        def event(_uc, va, _size, _data):
            if va == 0x48ff0:
                sp = m.uc.reg_read(m.x.UC_X86_REG_ESP)
                lo, hi, size, callback, param = struct.unpack('<5I', m.uc.mem_read(sp + 4, 20))
                ctx = m.uc.reg_read(m.x.UC_X86_REG_ECX)
                dst = m.uc.reg_read(m.x.UC_X86_REG_EDX)
                if self.pending or hi or size > 8 * 1024 * 1024:
                    raise AssertionError('overlapping or unbounded native I/O')
                if not art.HUD_START <= lo < lo + size <= m.get(0xb095a0):
                    raise AssertionError('native read outside collection extent')
                self.pending.append((lo, size, callback, param, ctx, dst))
                self.reads.append((lo, size, callback))
            elif va == 0x44da0:
                self.registered.append(m.uc.reg_read(m.x.UC_X86_REG_ECX))
            elif va == 0x44b60:
                self.registered_fonts.append(m.uc.reg_read(m.x.UC_X86_REG_ECX))
            elif va == 0x48fc0:
                self.closed = True
        m.uc.hook_add(unicorn.UC_HOOK_CODE, event)

    def run(self):
        m = self.m
        m.run(0x43a20, ecx=m.context)
        events, worst = 0, 0
        while self.pending:
            lo, size, callback, param, ctx, dst = self.pending.pop()
            data = self.pack[lo:lo + size]
            if len(data) != size:
                raise AssertionError('short fixture read')
            m.uc.mem_write(dst, bytes(data))
            m.put(ctx, lo + size)
            m.put(ctx + 4, 0)
            m.put(ctx + 0x18, size)
            m.put(ctx + 0x1c, dst)
            m.put(ctx + 0x20, 0)
            m.run(callback, (param,), edx=ctx, limit=1500000)
            worst = max(worst, len(m.visits))
            events += 1
            if events > 1000:
                raise AssertionError('native callback event bound exceeded')
        if not self.closed or m.get(0xb09584) or m.get(0xb09598) != m.get(0xb095a0):
            raise AssertionError('native collection did not finish exactly at EOF')
        return {'events': events, 'max_callback_instructions': worst,
                'registered_txtr': len(self.registered),
                'registered_font': len(self.registered_fonts),
                'heap_bytes': self.free_before - m.get(self.heap + 0x88)}


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC and importlib.util.find_spec('PIL'),
                     'pinned USA XBE, pack 0, Unicorn and Pillow required')
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = r.apply(XBE.read_bytes())[0]
        cls.file = PACK.open('rb')
        cls.addClassCleanup(cls.file.close)
        cls.retail = art.PackView.from_fd(cls.file.fileno(), 0, PACK.stat().st_size)
        cls.pack, cls.receipt = art.compile_runtime_collection(cls.retail)

    def test_exact_async_chain_old_and_new_end_and_setup_registration_order(self):
        old = Collection(self.payload, self.pack, end=art.HUD_START + art.HUD_SIZE)
        before = old.run()
        new = Collection(self.payload, self.pack)
        after = new.run()
        self.assertEqual(after['registered_txtr'] - before['registered_txtr'], 264)
        self.assertEqual(after['registered_font'] - before['registered_font'], len(fonts.NAMES))
        self.assertEqual(after['events'] - before['events'], 528 + 2 * len(fonts.NAMES))
        self.assertEqual(after['heap_bytes'] - before['heap_bytes'], 264 * 5376 + fonts.HEAP_BYTES)
        m = new.m
        for obj in new.registered:
            name = bytes(m.uc.mem_read(m.get(obj + 0x10), 16)).decode('utf-16le').split('\0')[0]
            if name.startswith('sb'):
                descriptor = m.get(obj + 0x14)
                self.assertEqual(m.get(descriptor + 4), obj + 128)
                self.assertEqual(m.get(descriptor + 8), obj + 128 + 4096)
                self.assertEqual(m.get(descriptor + 4) % 128, 0)
                m.textures[name] = descriptor
        self.assertEqual(len(m.textures), 264)
        m.identity('16', art.TEAM_LOGOS['TB']['asset_code'])
        m.setup()
        self.assertEqual(m.get(m.mats['hscore_buga'] + 0x30), m.textures['sb16h3'])
        self.assertEqual(m.get(m.mats['zscore_buga'] + 0x30), m.textures['sb27a3'])
        descriptors = {m.get(root + 20) for root in new.registered_fonts}
        for pointer in (0xa95a10, 0xa95918, 0xa95940, 0xa95968, 0xa959a0, 0xa958f0, 0xa95a80):
            self.assertIn(m.get(pointer), descriptors, hex(pointer))
            self.assertNotEqual(m.get(pointer), 0)
        # Dropping every appended wrapper via the old EOF returns NULL, not a wait.
        old.m.identity('16', '27'); old.m.setup()
        self.assertEqual(old.m.get(old.m.mats['hscore_buga'] + 0x30), 0)
        self.assertTrue(old.m.get(old.m.mats['hscore_buga'] + 8) & 1)
        print('native collection:', before, after)

    def test_native_uncompressed_allocation_failure_advances_without_spin(self):
        # Begin at the appendix with too little memory for even one texture.
        c = Collection(self.payload, self.pack, heap_bytes=1024)
        m = c.m
        m.put(0xb09598, art.HUD_START + art.HUD_SIZE)
        rec = c.run()
        self.assertEqual(rec['events'], 264 + len(fonts.NAMES))
        self.assertEqual(rec['registered_txtr'], 0)
        self.assertEqual(rec['registered_font'], 0)
        self.assertEqual(rec['heap_bytes'], 0)
        m.identity(); m.setup(); m.update()
        self.assertEqual(m.get(m.mats['hscore_buga'] + 0x30), 0)

    def test_native_decompressor_matches_refitted_scene_and_atlas_in_place(self):
        for name in ('score_bug', 'score_buga'):
            rec = art.RESOURCES[name]
            span = self.pack[rec['pack_offset']:rec['pack_offset'] + rec['span_size']]
            chunk, decoded, _ = r.scene.decode(span)
            m = Machine(self.payload)
            size = chunk.system_bytes + chunk.video_bytes
            dst = m.alloc(size + chunk.overlap_scratch_bytes + 128)
            src = dst + size + chunk.overlap_scratch_bytes - chunk.stored_size
            m.uc.mem_write(src, span[32:])
            m.run(0x4dc00, ecx=src, edx=dst, limit=1000000)
            self.assertEqual(bytes(m.uc.mem_read(dst, size)), decoded)

    def test_native_loader_wait_and_gpu_fence_are_distinct_bounded_witnesses(self):
        m = Machine(self.payload)
        m.uc.mem_write(0x38f50, b'\xc3')  # OS event pump without a completion
        m.put(0xb09584, 1)
        with self.assertRaisesRegex(AssertionError, 'instruction bound'):
            m.run(0x432d0, limit=500)
        self.assertIn(0x38f50, m.visits)
        m.put(0xb09584, 0); m.run(0x432d0, limit=100)
        fence = m.alloc(32); m.put(fence + 8, 1)
        m.uc.mem_write(0x33220, b'\xc3')
        m.uc.mem_write(0x341a0, b'\xc3')  # GPU has not acknowledged completion
        with self.assertRaisesRegex(AssertionError, 'instruction bound'):
            m.run(0x33660, ecx=fence, limit=500)
        self.assertIn(0x341a0, m.visits)
        m.put(fence + 8, 0); m.run(0x33660, ecx=fence, limit=100)


if __name__ == '__main__':
    unittest.main()

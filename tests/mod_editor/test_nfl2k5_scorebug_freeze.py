"""Standalone native game-entry and completion-order investigation.

Set NFL2K5_SCOREBUG_FREEZE_TRACE to write bounded JSON evidence after a passing
run. These fixtures cannot reproduce the tester's kernel/GPU or stopped state.
"""
from __future__ import annotations

import importlib.util
import ast
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.mod_editor.test_nfl2k5_scorebug_runtime import XBE, PACK, r, art
from tests.nfl2k5_scorebug_entry_fixture import (
    BUSY, ENABLED, PINS, EntryCollection, gpu_fence, special_lookup_context, validate,
)
from tools.nfl2k5_scorebug_projection import read_fonts

DEPENDENCIES = all(importlib.util.find_spec(name) is not None for name in ('unicorn', 'capstone', 'PIL'))


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and DEPENDENCIES,
                     'pinned USA default.xbe and pack 0, Unicorn, Capstone and Pillow required')
class FreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        validate(cls.retail)
        cls.payload, cls.installation = r.apply(cls.retail)
        cls.stream = PACK.open('rb')
        cls.addClassCleanup(cls.stream.close)
        cls.source = art.PackView.from_fd(cls.stream.fileno(), 0, PACK.stat().st_size)
        cls.fonts = read_fonts(PACK)
        cls.probes = {probe: art.compile_runtime_collection(cls.source, probe=probe)
                      for probe in ('hooks', 'neutral', 'full')}
        cls.evidence = dict(schema='scorebug-freeze-offline-v1', gameplay_witnessed=False,
                            cause_proved=False, xbe_sha256=art.pack_digest(cls.retail),
                            installation=cls.installation,
                            pins=[dict(va=hex(va), size=size, sha256=sha) for va, size, sha in PINS],
                            results={})

    @classmethod
    def tearDownClass(cls):
        destination = os.environ.get('NFL2K5_SCOREBUG_FREEZE_TRACE')
        expected = {'entry', 'practice_mode_3', 'loader_wait', 'gpu_wait',
                    'special_contexts', 'cache_queue_while_busy', 'historical_binding_code'}
        if destination and cls.evidence['results'].keys() == expected:
            # Optional local research output, never an input to these tests.
            path = Path(destination).resolve()
            content = json.dumps(cls.evidence, indent=2, sort_keys=True) + '\n'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')

    def collection(self, probe='full', *, load=True):
        pack, receipt = self.probes[probe]
        c = EntryCollection(self.payload, pack, receipt)
        self.addCleanup(c.close)
        if load:
            c.loaded = c.run()
        c.prepare_scene(self.fonts)
        return c

    def save(self, name, value):
        self.evidence['results'][name] = value

    def test_parent_initializer_and_complete_first_frame_with_and_without_bindings(self):
        results = []
        for probe in ('hooks', 'neutral', 'full'):
            c = self.collection(probe)
            m = c.m
            for mode in (4, 7):  # ordinary game and franchise regular/preseason
                entry = c.entry(mode)
                self.assertEqual(entry['game_ready'], [1, 1])
                self.assertEqual(entry['enabled'], 1)
                self.assertEqual(c.trace.counts[0xfce56], 1)
                self.assertEqual(c.trace.counts[m.labels['setup']], 1)
                self.assertEqual(c.trace.counts[0xfc1a0], 1)
                self.assertEqual(c.trace.counts[0xfce5b], 1)
                self.assertEqual(c.trace.counts[0x647e5], 1)
                self.assertFalse(c.trace.counts[0x432d0] or c.trace.counts[0x33660])
                materials = [m.get(m.state + r.MATERIALS + side * 4) for side in (0, 1)]
                bound = [m.get(mat + 0x30) for mat in materials]
                self.assertTrue(all(materials))
                self.assertEqual([bool(p) for p in bound], [probe != 'hooks'] * 2)
                for mat in materials:
                    self.assertEqual(bool(m.get(mat + 8) & 1), probe == 'hooks')
                frame = c.frame()
                self.assertEqual(c.trace.counts[0xfcfa2], 1)
                self.assertEqual(c.trace.counts[m.labels['update']], 1)
                self.assertEqual(c.trace.counts[0xfc9c0], 1)
                self.assertEqual(c.trace.counts[0xfcfa7], 1)
                self.assertFalse(c.trace.counts[0x432d0] or c.trace.counts[0x33660])
                results.append(dict(probe=probe, loaded=c.loaded, mode=mode, entry=entry, frame=frame,
                                    bound_descriptors=list(map(hex, bound)), boundaries=c.boundaries))
            if probe == 'full':
                # Same loaded collection and allocator, only the two call sites
                # restored in CPU memory. This is a matched offline control.
                c.hook_control(False)
                control = c.entry()
                self.assertEqual(c.trace.counts[m.labels['setup']], 0)
                self.assertEqual(c.trace.counts[0xfc1a0], 1)
                control_frame = c.frame()
                self.assertEqual(c.trace.counts[m.labels['update']], 0)
                results.append(dict(probe='resources-matched-allocation-control', entry=control, frame=control_frame))
            # Free each Unicorn instance before the next probe's allocations.
            c.close()
        self.save('entry', results)

    def test_native_practice_predicate_skips_scorebug_setup(self):
        c = self.collection('hooks')
        for mode in range(4):
            c.m.put(ENABLED, 0)
            entry = c.entry(mode)
            self.assertEqual(entry['game_ready'], [1, 1])
            self.assertEqual(entry['enabled'], 0)
            self.assertEqual(c.trace.counts[0xfccd0], 0)
            self.assertEqual(c.trace.counts[c.m.labels['setup']], 0)
        self.save('practice_mode_3', entry)

    def test_historical_beta61_binding_code_also_returns_in_current_resource_fixture(self):
        try:
            source = subprocess.run(
                ['git', 'show', 'cf349b7:mod_editor/core/nfl2k5_scorebug_runtime.py'],
                cwd=ROOT, check=True, capture_output=True, timeout=15,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            self.save('historical_binding_code', dict(skipped='local cf349b7 history or Git unavailable'))
            self.skipTest('local cf349b7 owner source or Git unavailable; current owner remains covered')
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         'a1fec85c3394249a82d01e5f62d24e1463cef792254e32575e5215b7fb92f52c')
        # Evaluate only the four pinned byte-emitter functions, never historical
        # writers/imports. Use current allocator sites in a CPU-only comparison.
        tree = ast.parse(source)
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in {'_u', '_save', '_restore', 'code_for'}]
        self.assertEqual(len(functions), 4)
        namespace = vars(r).copy()
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<pinned-beta61-emitter>', 'exec'), namespace)
        c = self.collection()
        m = c.m
        code, labels = namespace['code_for'](m.code['va'], m.state)
        m.uc.mem_write(m.code['va'], code)
        m.uc.ctl_remove_cache(m.code['va'], m.code['va'] + len(code))
        m.labels = labels
        c.trace.landmarks.update(labels[name] for name in r.HOOKS)
        for name, (va, _original) in r.HOOKS.items():
            m.uc.mem_write(va, r.hook_bytes(name, labels))
            m.uc.ctl_remove_cache(va, va + 5)
        entry = c.entry()
        self.assertEqual(entry['enabled'], 1)
        self.assertEqual(c.trace.counts[labels['setup']], 1)
        self.assertEqual(c.trace.counts[0xfc1a0], 1)
        frame = c.frame()
        self.assertEqual(c.trace.counts[labels['update']], 1)
        self.assertEqual(c.trace.counts[0xfc9c0], 1)
        self.assertFalse(c.trace.counts[0x432d0] or c.trace.counts[0x33660])
        self.save('historical_binding_code', dict(entry=entry, frame=frame,
                  code_sha256=hashlib.sha256(code).hexdigest(), source_commit='cf349b7',
                  boundary='historical hook instructions with current resources and fixture state, not a beta61 disc'))

    def test_special_lookup_contexts_pending_and_ready_do_not_wait_in_binding(self):
        c = self.collection('neutral')
        m = c.m
        results = []
        for field in (0x10, 0x14):
            for state in (0, 1, 2, 3):
                special_lookup_context(c, field, state)
                m.put(BUSY, 1)  # an unrelated pending load, deliberately withheld
                entry = c.entry()
                self.assertEqual(entry['enabled'], 1)
                self.assertEqual(m.get(BUSY), 1)
                branch = 0x42c90 if field == 0x10 else 0x42e40
                self.assertGreater(c.trace.counts[branch], 0)
                self.assertEqual(c.trace.counts[m.labels['setup']], 1)
                self.assertFalse(c.trace.counts[0x432d0] or c.trace.counts[0x33660])
                for side in (0, 1):
                    material = m.get(m.state + r.MATERIALS + side * 4)
                    self.assertNotEqual(m.get(material + 0x30), 0)
                results.append(dict(context_field=hex(field), state=state, entry=entry))
        self.save('special_contexts', results)

    def test_private_lookup_does_not_queue_work_in_an_unrelated_cache(self):
        c = self.collection('neutral')
        m = c.m
        cache = special_lookup_context(c, 0x10, 0)
        header, records = m.get(cache), m.get(cache + 0x1ac)
        wanted_hash = m.get(records + 4)
        m.put(header + 0x40, 1)
        m.put(header + 0x48, wanted_hash)
        m.put(cache + 0x1a4, 1)
        m.put(records + 4, 0)
        m.put(records + 0xc, 0xffffffff)
        m.put(BUSY, 1)
        entry = c.entry()
        self.assertEqual(entry['enabled'], 1)
        self.assertEqual(m.get(records), 0)
        self.assertEqual(m.get(records + 4), 0)
        self.assertEqual(m.get(cache + 0x94), 0)
        self.assertEqual(c.trace.counts[0x442f0], 0)
        self.assertEqual(c.trace.counts[0x48ff0], 0)
        self.assertFalse(c.trace.counts[0x432d0] or c.trace.counts[0x33660])
        self.assertEqual(m.get(BUSY), 1)
        self.save('cache_queue_while_busy', dict(entry=entry, queued=0, submitted_io=0))

    def test_loader_wait_native_completion_clears_busy_before_setup_callback(self):
        c = self.collection(load=False)
        m = c.m
        # Start at the appended resources; the old SCNE is already registered.
        # File opening/extent selection and completion delivery are fixture inputs.
        m.put(0xb09598, art.HUD_START + art.HUD_SIZE)
        m.put(m.context + 0x18, 0xfccd0)
        m.put(m.context + 0x20, c.heap)
        m.put(0xb09578, 0)
        m.put(BUSY, 0)
        # The VFS-open boundary accepts the extent already supplied above.
        # Native 43db0 inserts this context and calls the real busy/heap setters.
        m.uc.mem_write(0x48ef0, bytes.fromhex('b801000000c3'))
        c.trace.reset()
        m.run(0x43db0, (0,), esi=m.context)
        armed = c.trace.result()
        arm = next(w for w in armed['writes'] if w['address'] == hex(BUSY))
        self.assertEqual((arm['pc'], arm['value']), ('0x42fc0', '0x1'))
        self.assertEqual(len(c.pending), 1)
        c.completion_pump(deliver=False)
        c.trace.reset()
        with self.assertRaisesRegex(AssertionError, 'instruction bound'):
            m.run(0x432d0, limit=4000)
        withheld = c.trace.result()
        self.assertEqual(m.get(BUSY), 1)
        self.assertEqual(c.delivered, 0)
        self.assertGreater(c.trace.counts[0x432c0], 1)
        self.assertEqual(c.trace.counts[m.labels['setup']], 0)
        # Resume the SAME suspended stack and native event-table guard.
        c.deliver = True
        c.trace.reset()
        m.uc.emu_start(m.uc.reg_read(m.x.UC_X86_REG_EIP), m.STOP, count=2000000)
        self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_EIP), m.STOP, c.trace.result())
        self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_ESP), m.STACK + 0xf004)
        self.assertTrue(c.closed)
        self.assertEqual(m.get(BUSY), 0)
        self.assertEqual(m.get(ENABLED), 1)
        self.assertFalse(c.pending)
        self.assertEqual(c.delivered, 528 + 2 * len(art.scoped_fonts.NAMES))
        self.assertEqual(c.trace.counts[m.labels['setup']], 1)
        completion = c.trace.result()
        clear = next(w for w in completion['writes'] if w['address'] == hex(BUSY) and w['value'] == '0x0')
        hook = next(e for e in completion['events'] if e['pc'] == hex(m.labels['setup']))
        self.assertEqual(clear['pc'], '0x42fc0')
        self.assertLess(clear['step'], hook['step'])
        self.assertEqual(hook['busy'], 0)
        self.save('loader_wait', dict(armed=armed, withheld=withheld, completed=completion, callbacks=c.delivered,
                                      file_open='0x48ef0 accepts the supplied appendix extent; VFS not executed',
                                      callback_choice='fixture context+0x18 = native 0xfccd0'))

    def test_gpu_wait_native_packet_callback_releases_same_suspended_continuation(self):
        import unicorn
        c = self.collection('neutral')
        m = c.m
        c.entry()
        c.frame()
        fence, stream = gpu_fence(m, c.trace)
        armed = c.trace.result()
        arm = next(w for w in armed['writes'] if w['address'] == hex(fence + 8))
        self.assertEqual((arm['pc'], arm['value']), ('0x335a3', '0x1'))
        # OS sleep is the only replacement here. RDTSC and the actual wait run.
        m.uc.mem_write(0x341a0, b'\xc3')
        c.trace.reset()
        with self.assertRaisesRegex(AssertionError, 'instruction bound'):
            m.run(0x33660, ecx=fence, limit=1000)
        withheld = c.trace.result()
        self.assertEqual(m.get(fence + 8), 1)
        self.assertGreater(c.trace.counts[0x3367a], 1)
        callback, argument = struct.unpack('<2I', m.uc.mem_read(stream + 4, 8))
        # GPU dispatch itself is unavailable. Deliver exactly the native packet's
        # callback on the existing stack; it is cdecl, with caller cleanup.
        thunk = m.STOP + 0x200
        code = b'\x9c\x60\x68' + struct.pack('<I', argument)
        code += b'\xb8' + struct.pack('<I', callback) + bytes.fromhex('ffd083c404619dc3')
        m.uc.mem_write(thunk, code)
        delivered = []

        def complete(_uc, _pc, _size, _data):
            if not delivered:
                delivered.append(callback)
                m.uc.reg_write(m.x.UC_X86_REG_EIP, thunk)

        handle = m.uc.hook_add(unicorn.UC_HOOK_CODE, complete, begin=0x341a0, end=0x341a0)
        c.trace.reset()
        try:
            m.uc.emu_start(m.uc.reg_read(m.x.UC_X86_REG_EIP), m.STOP, count=2000)
        finally:
            m.uc.hook_del(handle)
        completed = c.trace.result()
        self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_EIP), m.STOP)
        self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_ESP), m.STACK + 0xf004)
        self.assertEqual(m.get(fence + 8), 0)
        clear = next(w for w in completed['writes'] if w['address'] == hex(fence + 8))
        self.assertEqual((clear['pc'], clear['value']), ('0x33414', '0x0'))
        self.save('gpu_wait', dict(armed=armed, withheld=withheld, completed=completed, polled_address=hex(fence + 8),
                                  packet=[hex(v) for v in (0x81d8c, callback, argument)],
                                  dispatch='host delivery of native packet; no GPU execution'))


if __name__ == '__main__':
    unittest.main()

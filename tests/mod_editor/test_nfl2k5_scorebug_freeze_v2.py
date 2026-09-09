"""Native regression controls for HUD-scoped scorebug binding.

No console/GPU emulation. A valid synthetic cache and a native pending fence
expose the old hook's eviction wait; this is not a capture of the tester's heap.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.mod_editor.test_nfl2k5_scorebug_runtime import XBE, PACK, r, art, space, repin
from tests.fixtures import nfl2k5_scorebug_runtime_v4 as old
from tests.nfl2k5_scorebug_entry_fixture import EntryCollection, ENABLED, gpu_fence, special_lookup_context, validate
from tools.nfl2k5_scorebug_projection import StaticMachine, read_fonts
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

DEPENDENCIES = all(importlib.util.find_spec(n) for n in ('unicorn', 'capstone', 'PIL'))


def control(c, version):
    """Change only the two hooks and their owned CPU instructions."""
    m = c.m
    if version == 'native':
        c.hook_control(False)
        return
    if version == 'old':
        if (m.code['va'], m.state) != (old.CODE_VA, old.DATA_VA):
            raise AssertionError('historical control allocation moved')
        content, labels = old.CODE, old.HOOK_LABELS
    else:
        content, labels = r.code_for(m.code['va'], m.state)
    m.uc.mem_write(m.code['va'], content)
    m.uc.ctl_remove_cache(m.code['va'], m.code['va'] + len(content))
    for name, (va, _original) in r.HOOKS.items():
        m.uc.mem_write(va, r.hook_bytes(name, labels))
        m.uc.ctl_remove_cache(va, va + 5)


def cache_eviction(c, wanted='hscore_buga'):
    """One cold indexed name, one ready LRU texture, no GPU completion.

    The victim's real loader-installed destructor runs. The fixture borrows
    its resource root for the cache record and stops before cache-pool freeing;
    this is not a native cache allocation/lifetime test.
    """
    m = c.m
    cache = special_lookup_context(c, 0x10, 3)
    header, records = m.get(cache), m.get(cache + 0x1ac)
    m.run(0x38600, ecx=m.string(wanted))
    wanted_hash = m.uc.reg_read(m.x.UC_X86_REG_EAX)
    victim = next(root for root in c.registered
                  if StaticMachine.read_string(m, m.get(root + 16)) == 'score_buga')
    if m.get(victim + 28) != 0x44dc0:
        raise AssertionError('native TXTR destructor was not installed')
    m.put(header + 0x40, 1)
    m.put(header + 0x48, wanted_hash)
    m.put(cache + 0x1a4, 1)
    m.put(records + 4, 123)  # A different, already resident resource hash.
    m.put(records + 12, 0xffffffff)  # Evictable outside the current generation.
    m.put(records + 28, victim - 32)
    fence, stream = gpu_fence(m, c.trace)
    m.put(0xa6aa70, fence)
    m.put(0xa6a9a0, 0)  # No new frame awaiting submission by 28DE0.
    for va in (0x33220, 0x341a0):
        m.uc.mem_write(va, b'\xc3')
        c.boundaries.append(dict(pc=hex(va), result='host GPU/OS completion withheld'))
    c.trace.landmarks.update((0x42d50, 0x42c00, 0x44dc0, 0x28f40, 0x28de0))
    return dict(cache=cache, records=records, fence=fence, stream=stream,
                wanted=wanted, wanted_hash=hex(wanted_hash), victim=hex(victim))


def indexed_texture_alias(c):
    """Native ready-index format with a genuine, relocated score_buga TXTR."""
    m = c.m
    root = next(root for root in c.registered
                if StaticMachine.read_string(m, m.get(root + 16)) == 'score_buga')
    descriptor = m.get(root + 20)
    m.run(0x38600, ecx=m.string('score_buga'))
    name_hash = m.uc.reg_read(m.x.UC_X86_REG_EAX)
    context, special, table = m.alloc(128), m.alloc(0x200), m.alloc(128)
    for va, value in ((context, m.context), (context + 8, m.string('OTHER_INDEX')),
                      (context + 0x14, special), (special + 4, 3),
                      (special + 0xb0, table), (table, 1), (table + 8, name_hash)):
        m.put(va, value)
    m.uc.mem_write(table + 16, bytes(m.uc.mem_read(descriptor, 24)))
    m.put(0xb09578, context)
    return table + 16


@unittest.skipUnless(XBE.is_file(), 'pinned USA default.xbe evidence absent')
class InstallationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = r.apply(cls.retail)

    def test_unchanged_budget_and_static_v3_both_orders(self):
        self.assertEqual((r.CODE_SIZE, r.DATA_SIZE), (1408, 128))
        code, data = r.sites(self.patched)
        self.assertEqual(len(r.code_for(code['va'], data['va'])[0].rstrip(b'\xcc')), 1404)
        left = r.apply(r.scene.apply_xbe(self.retail)[0])[0]
        right = r.scene.apply_xbe(self.patched)[0]
        self.assertEqual(left, right)
        self.assertEqual(r.status(left), 'applied')
        self.assertEqual(r.scene.xbe_version(left), 'espn-broadcast-exact-v3')
        self.assertEqual(r.apply(left)[0], left)
        self.assertEqual(r.scene.apply_xbe(left)[0], left)
        self.assertEqual(self.receipt['binding_collection'], 'GAMEDATA')
        self.assertFalse(self.receipt['runtime_witnessed'])

    def test_new_dependencies_and_old_sealed_owner_refuse_before_mutation(self):
        for va, size, _sha in r.LOOKUP_GUARDS:
            for at in (va, va + size - 1):
                with self.subTest(va=hex(at)):
                    bad = bytearray(self.patched)
                    off = XbeImage(self.patched).offset(at)
                    bad[off] ^= 1
                    bad = repin(bad)
                    self.assertEqual(r.status(bad), 'foreign')
                    with mock.patch.object(space, 'install_code', side_effect=AssertionError('write before refusal')):
                        with self.assertRaises(ValueError):
                            r.apply(bad)
        self.assertEqual(hashlib.sha256(old.CODE).hexdigest(), old.CODE_SHA256)
        base = space.apply(r.scene.apply_xbe(self.retail)[0], r.REQUESTS)[0]
        self.assertEqual(tuple(s['va'] for s in r.sites(base)), (old.CODE_VA, old.DATA_VA))
        old_xbe = bytearray(space.install_code(base, r.OWNER, old.CODE)[0])
        for name, (va, _original) in r.HOOKS.items():
            off = XbeImage(base).offset(va)
            old_xbe[off:off + 5] = r.hook_bytes(name, old.HOOK_LABELS)
        for va in (0xa95894, 0xa958bc):
            off = XbeImage(base).offset(va)
            old_xbe[off:off + 4] = bytes(4)
        old_xbe = repin(old_xbe)
        self.assertEqual(space.status(old_xbe), 'applied')
        self.assertEqual(r.status(old_xbe), 'foreign')
        with self.assertRaisesRegex(ValueError, 'rebuild'):
            r.apply(old_xbe)


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and DEPENDENCIES,
                     'pinned USA default.xbe/pack 0, Unicorn, Capstone and Pillow required')
class NativeBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = XBE.read_bytes()
        validate(retail)
        cls.payload, receipt = r.apply(retail)
        cls.stream = PACK.open('rb')
        cls.addClassCleanup(cls.stream.close)
        cls.source = art.PackView.from_fd(cls.stream.fileno(), 0, PACK.stat().st_size)
        cls.fonts = read_fonts(PACK)
        cls.probes = {p: art.compile_runtime_collection(cls.source, probe=p) for p in art.PROBES}
        cls.evidence = dict(schema='scorebug-freeze-native-v2', runtime_witnessed=False,
                            community_cause_proved=False, installation=receipt,
                            old_code_sha256=old.CODE_SHA256, cases={})

    @classmethod
    def tearDownClass(cls):
        destination = os.environ.get('NFL2K5_SCOREBUG_FREEZE_V2_TRACE')
        expected = {'eviction', 'typed_alias', 'six_profiles', 'missing_hud', 'hud_opener'}
        if destination and cls.evidence['cases'].keys() == expected:
            path = Path(destination).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cls.evidence, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    def collection(self, probe='neutral'):
        pack, receipt = self.probes[probe]
        c = EntryCollection(self.payload, pack, receipt)
        self.addCleanup(c.close)
        c.loaded = c.run()
        c.prepare_scene(self.fonts)
        return c

    def test_old_binding_enters_eviction_wait_fixed_and_native_controls_return(self):
        c = self.collection()
        m = c.m
        setup = cache_eviction(c)
        results = []
        for version in ('old', 'fixed', 'native'):
            control(c, version)
            m.put(ENABLED, 0)
            if version == 'old':
                with self.assertRaisesRegex(AssertionError, 'instruction bound'):
                    c.entry()
                self.assertEqual(m.get(ENABLED), 0)
                for pc in (0xfce56, 0x42c00, 0x44dc0, 0x28f40, 0x33660):
                    self.assertGreater(c.trace.counts[pc], 0, hex(pc))
                self.assertGreater(c.trace.counts[0x3367a], 1000)
            else:
                entry = c.entry()
                self.assertEqual(entry['game_ready'], [1, 1])
                self.assertEqual(m.get(ENABLED), 1)
                for pc in (0x42c00, 0x44dc0, 0x33660, 0x442f0):
                    self.assertEqual(c.trace.counts[pc], 0, hex(pc))
            self.assertEqual(m.get(setup['fence'] + 8), 1)
            self.assertEqual(m.get(setup['records']), 3)
            results.append(dict(version=version, trace=c.trace.result()))
        self.evidence['cases']['eviction'] = dict(setup=setup, results=results, boundaries=c.boundaries)

    def test_indexed_texture_cannot_be_bound_as_a_private_score_font(self):
        c = self.collection()
        m = c.m
        alias = indexed_texture_alias(c)
        c.prepare_draw()
        results = []
        for version in ('old', 'fixed'):
            control(c, version)
            c.entry()
            selected = m.get(r.SCORE_FONTS[0])
            if version == 'old':
                self.assertEqual(selected, alias)
            else:
                self.assertIn(selected, {m.get(root + 20) for root in c.registered_fonts})
                self.assertNotEqual(selected, alias)
            for _ in range(40):
                c.frame()
            draw = c.draw()
            scores = [s for s in draw['submissions'] if s['text'] == '0']
            self.assertEqual(len(scores), 2)
            self.assertEqual([s['vertices'] > 0 for s in scores], [version == 'fixed'] * 2)
            results.append(dict(version=version, selected_font=hex(selected), draw=draw))
        self.evidence['cases']['typed_alias'] = dict(alias=hex(alias), results=results)

    def test_all_six_profiles_enter_complete_frames_draw_and_reenter(self):
        results = []
        for probe in art.PROBES:
            with self.subTest(probe=probe):
                c = self.collection(probe)
                m = c.m
                hooks = art.probe_has_hooks(probe)
                if not hooks:
                    control(c, 'native')
                c.prepare_draw()
                entry = c.entry(4)
                self.assertEqual(entry['game_ready'], [1, 1])
                self.assertEqual(c.trace.counts[m.labels['setup']], int(hooks))
                frame = c.frame()
                self.assertEqual(c.trace.counts[m.labels['update']], int(hooks))
                self.assertEqual(c.trace.counts[0xfc9c0], 1)
                for _ in range(39):
                    c.frame()
                draw = c.draw()
                self.assertTrue(any(s['vertices'] for s in draw['submissions']))
                self.assertFalse(c.trace.counts[0x33660] or c.trace.counts[0x432d0])
                if hooks:
                    allowed = {m.get(root + 20) for root in c.registered_fonts} | set(m.fonts)
                    self.assertTrue(all(int(s['font'], 16) in allowed for s in draw['submissions']))
                reentry = c.entry(7)
                self.assertEqual(reentry['game_ready'], [1, 1])
                results.append(dict(probe=probe, loaded=c.loaded, entry=entry, frame=frame,
                                    draw=draw, reentry=reentry, boundaries=c.boundaries))
                c.close()
        self.evidence['cases']['six_profiles'] = results

    def test_absent_named_hud_does_not_borrow_other_collections_resources(self):
        c = self.collection()
        m = c.m
        m.put(m.context + 8, m.string('OTHER_COLLECTION'))
        entry = c.entry()
        self.assertEqual(entry['enabled'], 1)
        for side in (0, 1):
            material = m.get(m.state + r.MATERIALS + 4 * side)
            self.assertEqual(m.get(material + 0x30), 0)
            self.assertTrue(m.get(material + 8) & 1)
            self.assertIn(m.get(r.SCORE_FONTS[side]), m.fonts)
        self.assertEqual(m.get(m.state + r.FONT_SCORE), 0)
        self.evidence['cases']['missing_hud'] = entry

    def test_retail_game_loader_constructs_an_ordinary_named_hud_context(self):
        c = self.collection()
        m = c.m
        m.put(0xb09578, 0)
        m.put(0xb09584, 0)
        m.put(0xb09598, art.HUD_START)
        m.uc.mem_write(0x48ef0, bytes.fromhex('b801000000c3'))
        # Native heap selection and VFS open are supplied input boundaries.
        m.uc.mem_write(0x38fb0, b'\xb8' + struct.pack('<I', c.heap) + b'\xc3')
        c.trace.reset()
        m.uc.reg_write(m.x.UC_X86_REG_ESP, m.STACK + 0xf000)
        m.uc.emu_start(0x6310e, 0x6312c, count=250000)
        self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_EIP), 0x6312c)
        self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_ESP), m.STACK + 0xf000)
        context = m.get(0xb09578)
        self.assertEqual(context, 0xb33d5c)
        self.assertEqual(m.get(context + 8), r.HUD_COLLECTION_NAME)
        self.assertEqual([m.get(context + off) for off in (0xc, 0x10, 0x14)], [0, 0, 0])
        self.assertEqual(len(c.pending), 1)
        from tools import nfl_outer
        index = nfl_outer.HEADER_SIZE + art.HUD_OUTER_INDEX * 12
        identity = struct.unpack('<I', self.source[index:index + 4])[0]
        self.assertEqual(identity, zlib.crc32('GAMEDATA.IFF'.encode('utf-16le')))
        self.evidence['cases']['hud_opener'] = dict(context=hex(context), file_hash=hex(identity),
            trace=c.trace.result(), boundaries=['38FB0 supplies the heap', '48EF0 supplies VFS extent/open success'])


if __name__ == '__main__':
    unittest.main()

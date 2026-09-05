"""Exercise roster copy -> gate -> queue -> decal/model -> actual inline vertices."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tools'))
from mod_editor.core import nfl2k5_player_star as ps
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from tools.player_star.audit import RETAIL

HAVE_UNICORN = importlib.util.find_spec('unicorn') is not None


class ShapeTests(unittest.TestCase):
    def test_runtime_is_original_and_fits_declared_spans(self):
        self.assertEqual(ps.ENTITY_LIMIT, 22)
        self.assertEqual(ps.RETAIL_STAR_LIST_LIMIT, 9)
        spans = sorted((va, va+size) for va, size, _ in ps.CAVES)
        self.assertTrue(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])))
        for va, size, code in ps.CAVES:
            self.assertLessEqual(len(code), size)
            self.assertIn(va, ps.CAVE_PINS)
        target = ps.DRAW_CALL_VA+5+struct.unpack_from('<i', ps.PATCHED_DRAW_CALL, 1)[0]
        self.assertEqual(target, ps.SYMBOLS['star_frame'])


@unittest.skipUnless(RETAIL.is_file(), 'private USA retail XBE absent')
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        cls.patched, cls.receipt = ps.apply(cls.retail)
        buf = bytearray(cls.retail)
        at = ps._offset(buf, ps.GATE_VA)
        buf[at:at+ps.GATE_SIZE] = ps.LEGACY_GATE
        cls.legacy = bytes(buf)
        buf = bytearray(cls.retail)
        at = ps._offset(buf, ps.DRAW_CALL_VA)
        buf[at:at+5] = ps.PATCHED_DRAW_CALL
        fixture = json.loads((ROOT/'tests/fixtures/nfl2k5_player_star_thin_v1.json').read_text())
        for row in fixture['caves']:
            va = int(row['va'], 16)
            code = bytes.fromhex(row['code']).ljust(row['capacity'], b'\x90')
            assert hashlib.sha256(code).hexdigest() == ps.LEGACY_OUTLINE_PINS[va]
            at = ps._offset(buf, va)
            buf[at:at+len(code)] = code
        for s in _sections(buf):
            buf[s.header_offset+36:s.header_offset+56] = section_digest(bytes(buf), s)
        cls.thin = bytes(buf)

    def test_upgrade_status_and_idempotence(self):
        self.assertEqual(ps.status(self.retail), 'retail')
        self.assertEqual(ps.status(self.legacy), 'legacy')
        self.assertTrue(ps.read_settings(self.legacy)['needs_upgrade'])
        self.assertEqual(ps.status(self.patched), 'applied')
        self.assertEqual(ps.read_settings(self.patched)['renderer'], 'white_star_outline')
        upgraded, receipt = ps.apply(self.legacy)
        self.assertEqual(upgraded, self.patched)
        self.assertTrue(receipt['controller_gate_restored'])
        again, receipt = ps.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt['changed_bytes'], 0)
        self.assertTrue(receipt['already_applied'])

    def test_exact_thin_outline_upgrades_and_preserves_the_retail_gate(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt

        self.assertEqual(ps.status(self.thin), 'legacy')
        settings = ps.read_settings(self.thin)
        self.assertTrue(settings['needs_upgrade'])
        self.assertEqual(settings['renderer_revision'], 'thin_v1')
        self.assertEqual(settings['renderer'], 'white_star_outline')
        upgraded, receipt = ps.apply(self.thin)
        self.assertEqual(upgraded, self.patched)
        self.assertEqual(receipt['upgraded_renderer'], 'thin_v1')
        self.assertFalse(receipt['controller_gate_restored'])
        self.assertEqual(ps.read_settings(upgraded)['renderer_revision'], 'bold_contrast_v2')
        dispatched, receipt = tt._apply_all(self.thin, None, catch_slider=False, player_star=True)
        self.assertEqual(dispatched, self.patched)
        self.assertEqual(receipt['player_star_patch']['upgraded_renderer'], 'thin_v1')
        for va, size, _ in ps.CAVES:
            # Combining individually valid spans from two revisions is foreign.
            if ps._read(self.thin, va, size) == ps._read(self.patched, va, size):
                continue
            b = bytearray(self.thin)
            at = ps._offset(b, va)
            b[at:at+size] = ps._read(self.patched, va, size)
            self.assertEqual(ps.status(bytes(b)), 'foreign')
            with self.assertRaises(ps.PlayerStarError):
                ps.apply(bytes(b))

    def test_modified_and_mixed_sites_fail_closed(self):
        for source in (self.retail, self.legacy, self.thin, self.patched):
            for _, va, code in ps.sites():
                b = bytearray(source)
                b[ps._offset(b, va)] ^= 1
                with self.subTest(source=ps.status(source), va=hex(va)):
                    self.assertEqual(ps.status(bytes(b)), 'foreign')
                    with self.assertRaises(ps.PlayerStarError):
                        ps.apply(bytes(b))
            for va, size, _ in ps.CAVES:
                b = bytearray(source)
                b[ps._offset(b, va)+size-1] ^= 1
                self.assertEqual(ps.status(bytes(b)), 'foreign')
        b = bytearray(self.patched)
        off = ps._offset(b, ps.DRAW_CALL_VA)
        b[off:off+5] = ps.RETAIL_DRAW_CALL
        self.assertEqual(ps.status(bytes(b)), 'foreign')
        for va, pin in ps.PINS:
            b = bytearray(self.retail)
            b[ps._offset(b, va)] ^= 1
            self.assertEqual(ps.status(bytes(b)), 'foreign', hex(va))
        for va, size, _ in ps.CONTEXT_HASHES:
            b = bytearray(self.retail)
            b[ps._offset(b, va)+size-1] ^= 1
            self.assertEqual(ps.status(bytes(b)), 'foreign', hex(va))

    def test_only_declared_sites_and_digests_change(self):
        spans = [(ps._offset(self.retail, va), len(code)) for _, va, code in ps.sites()]
        spans += [(s.header_offset+36, 20) for s in _sections(self.retail)]
        changed = [i for i, (a, b) in enumerate(zip(self.retail, self.patched)) if a != b]
        self.assertEqual(len(changed), self.receipt['changed_bytes'])
        self.assertEqual(len(self.retail), len(self.patched))
        self.assertTrue(all(any(a <= i < a+n for a, n in spans) for i in changed))
        for s in _sections(self.patched):
            self.assertEqual(self.patched[s.header_offset+36:s.header_offset+56], section_digest(self.patched, s))
        self.assertEqual(ps._read(self.patched, ps.GATE_VA, ps.GATE_SIZE), ps.RETAIL_GATE)
        self.assertEqual(self.receipt['sections_repinned'], [0])

    def test_current_stack_does_not_own_new_spans_and_order_is_independent(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        from mod_editor.core import nfl2k5_position_pools as pools, nfl2k5_depth_chart_rows as rows
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        flags = dict(catch_slider=True, accel_ramp=True, draft_ai=True, edge_rename=True, returner_fix=True,
                     progression=True, scheme_labels=True, camera=True, kick_rules=True, widescreen=True,
                     overtime=True, team_column=True, seven_on_seven=True, penalties='nfl', uniform_choice='choice',
                     kick_laces=True, franchise_practice=True, prospect_names='modern', dynamic_kickoff=True,
                     practice_squad=True, arc_table=False, kick_power=False)
        stack, _ = tt._apply_all(self.retail, None, **flags)
        stack, _ = pools.apply(stack)
        stack, _ = rows.apply(stack)
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(self.retail))
        for va, size, _ in ps.CAVES:
            self.assertEqual(manifest.overlaps(va, va+size, exclude_owner='nfl2k5_player_star'), [])
            self.assertEqual(ps._read(stack, va, size), ps._read(self.retail, va, size))
        final, _ = ps.apply(stack)
        opposite, _ = tt._apply_all(self.patched, None, **flags)
        opposite, _ = pools.apply(opposite)
        opposite, _ = rows.apply(opposite)
        self.assertEqual(final, opposite)
        self.assertEqual(ps.status(final), 'applied')
        from mod_editor.core import nfl2k5_practice_reserves as reserves
        self.assertEqual(reserves.status(final), 'applied')
        tampered = bytearray(final)
        tampered[ps._offset(final, reserves.STAGE_VA) + 4] ^= 1
        self.assertEqual(ps.status(bytes(tampered)), 'foreign')
        repeat, receipt = tt._apply_all(final, None, player_star=True, catch_slider=False)
        self.assertEqual(final, repeat)
        self.assertTrue(receipt['player_star_patch']['already_applied'])

    def test_cave_references_include_entries_short_branches_and_unaligned_pointers(self):
        from tools.player_star.audit import audit
        result = audit(self.retail)
        self.assertEqual(result['external_references'], [])
        self.assertTrue(all(not row['overlaps'] for row in result['spans']))


@unittest.skipUnless(RETAIL.is_file() and HAVE_UNICORN, 'private XBE or Unicorn absent')
class DrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.player_star.emulate import Machine
        cls.Machine = Machine
        cls.retail = RETAIL.read_bytes()
        cls.fixed, _ = ps.apply(cls.retail)
        b = bytearray(cls.retail)
        off = ps._offset(b, ps.GATE_VA)
        b[off:off+ps.GATE_SIZE] = ps.LEGACY_GATE
        cls.legacy = bytes(b)

    def test_old_patch_accepts_tag_but_skips_cpu_decal_and_controlled_gets_same_ring(self):
        from tools.player_star.emulate import MODEL
        old = self.Machine(self.legacy)
        entities = old.entities([1, 1, 1], controlled=(0,))
        self.assertEqual(old.run(ps.GATE_VA, ecx=entities[1]), 1)
        old.frame()
        self.assertEqual(old.u32(ps.STAR_COUNT_VA)&255, 3)
        self.assertEqual(old.strips, [])
        self.assertEqual([m['model'] for m in old.models], [MODEL])
        new = self.Machine(self.fixed)
        new.entities([1, 1, 1], controlled=(0,))
        new.frame()
        self.assertEqual(new.models, old.models)
        self.assertEqual(new.u32(ps.STAR_COUNT_VA)&255, 1)
        self.assertEqual(len(new.strips), 6)

    def test_all_22_get_white_outlines_across_modes_and_control_assignments(self):
        for mode in range(9):
            for controlled in ((), (0,), (3, 12)):
                with self.subTest(mode=mode, controlled=controlled):
                    vm = self.Machine(self.fixed)
                    vm.entities([1]*22, mode=mode, controlled=controlled)
                    vm.frame()
                    self.assertEqual(len(vm.strips), 44)
                    self.assertEqual(vm.u32(ps.STAR_COUNT_VA)&255, len(controlled))
                    self.assertEqual(len(vm.models), len(controlled))
                    for index, strip in enumerate(vm.strips):
                        self.assertEqual(strip['primitive'], 6)
                        self.assertEqual(strip['transform'], 0)
                        self.assertEqual(strip['vertex_mode'], 0)
                        self.assertEqual(len(strip['vertices']), 22)
                        self.assertTrue(all(v[3] == 0xFFFFFFFF for v in strip['vertices']))
                        mat = strip['material']
                        self.assertEqual(struct.unpack_from('<I', mat, 0x18)[0],
                                         0xFF101010 if index%2 == 0 else 0xFFFFFFFF)
                        self.assertEqual(struct.unpack_from('<I', mat, 0x30)[0], 0)
                        self.assertEqual(struct.unpack_from('<I', mat, 0x60)[0]&0x0F000000, 0)

    def test_geometry_is_closed_five_point_outline_at_interpolated_feet(self):
        vm = self.Machine(self.fixed)
        vm.entities([1])
        vm.frame()
        cx, cz = vm.centers[0]
        self.assertEqual(len(vm.strips), 2)
        for strip, scale, height in zip(vm.strips, (1.125, 1), (5, 5.5)):
            vertices = strip['vertices']
            self.assertEqual(vertices[:2], vertices[-2:])
            outer = vertices[::2][:-1]
            for j, (x, y, z, _) in enumerate(vertices[:-2]):
                i, inner = divmod(j, 2)
                radius = (108 if i%2 == 0 else 51)*scale*(0.58 if inner else 1)
                angle = -math.pi/2+i*math.pi/5
                self.assertAlmostEqual(x, cx+radius*math.cos(angle), places=3)
                self.assertAlmostEqual(z, cz+radius*math.sin(angle), places=3)
                self.assertEqual(y, height)
            # Each pass covers only the annulus, leaving the center hollow.
            def area(a, b, c):
                return abs((b[0]-a[0])*(c[2]-a[2])-(b[2]-a[2])*(c[0]-a[0]))/2
            triangles = sum(area(*vertices[i:i+3]) for i in range(20))
            polygon = sum(outer[i][0]*outer[(i+1)%10][2]-outer[(i+1)%10][0]*outer[i][2]
                          for i in range(10))/2
            self.assertAlmostEqual(triangles, abs(polygon)*(1-0.58**2), delta=0.1)

    def test_untagged_and_control_changes_preserve_retail_rendering_and_shared_material(self):
        from tools.player_star.emulate import MATERIAL
        for controlled in ((), (0,), (1,)):
            retail = self.Machine(self.retail)
            retail.entities([0, 0], controlled=controlled)
            retail.frame()
            new = self.Machine(self.fixed)
            new.entities([0, 0], controlled=controlled)
            new.frame()
            self.assertEqual(new.models, retail.models)
            self.assertEqual(new.strips, [])
            before = bytes(new.uc.mem_read(MATERIAL, 128))
            new.uc.mem_write(0xB30C4C+0x53, b'\x01')
            new.frame()
            self.assertEqual(len(new.strips), 2)
            self.assertEqual(bytes(new.uc.mem_read(MATERIAL, 128)), before)

    def test_hud_and_coach_visibility_follow_the_retail_circles(self):
        for ready, visible, coach, coach_visible in ((0, 1, False, True), (1, 0, False, True),
                                                    (1, 1, True, False), (1, 1, True, True)):
            vm = self.Machine(self.fixed, coach=coach, coach_visible=coach_visible)
            vm.entities([1], controlled=(0,))
            vm.set32(ps.DRAW_READY_VA, ready)
            vm.set32(ps.DRAW_VISIBLE_VA, visible)
            vm.frame()
            expected = int(bool(ready and visible and (not coach or coach_visible)))
            self.assertEqual(len(vm.strips), 2*expected)
            self.assertEqual(len(vm.models), expected)

    def test_no_human_and_inactive_null_or_other_bits(self):
        vm = self.Machine(self.fixed)
        vm.entities([1, 2, 3, 1, 1, 1], inactive=(3,), missing_record=(4,), missing_body=(5,))
        vm.set32(0xE5FC50, 0)
        vm.frame()
        self.assertEqual(len(vm.strips), 4)
        self.assertEqual(vm.u32(ps.STAR_COUNT_VA)&255, 0)

    def test_tag_walk_is_bounded_even_with_a_corrupt_cycle(self):
        vm = self.Machine(self.fixed)
        vm.entities([1], cycle=True)
        vm.frame(build=False)  # the retail builder has no corruption bound
        self.assertEqual(len(vm.strips), 44)

    def test_runtime_copy_and_relocator_preserve_every_tag_byte(self):
        from tools.player_star.emulate import HEAP
        vm = self.Machine(self.fixed)
        # Actual retail record relocator followed by the two-team copy primitive.
        team = HEAP+0x90000
        source = HEAP+0xA0000
        target = HEAP+0xB0000
        for i, tag in enumerate((1, 0x81, 0)):
            record = bytearray((j*3+i)&255 for j in range(0x54))
            for ptr in (0, 0x10, 0x14, 0x2C):
                struct.pack_into('<I', record, ptr, 0)
            record[0x53] = tag
            vm.uc.mem_write(source+i*0x54, bytes(record))
            vm.run(0xE5E70, ecx=source+i*0x54)
            vm.set32(team+i*4, source+i*0x54)
        vm.uc.mem_write(team+0x11C, b'\x03')
        vm.run(0xC3C60, ecx=team, edx=target)
        self.assertEqual(bytes(vm.uc.mem_read(source, 3*0x54)), bytes(vm.uc.mem_read(target, 3*0x54)))
        self.assertEqual([bytes(vm.uc.mem_read(target+i*0x54+0x53, 1))[0] for i in range(3)], [1, 0x81, 0])


if __name__ == '__main__':
    unittest.main()

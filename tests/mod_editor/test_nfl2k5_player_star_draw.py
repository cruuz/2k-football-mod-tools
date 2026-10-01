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
ALL_SPANS = ['star_runtime_372d40', 'star_runtime_3ddd50', 'star_runtime_38b0d0', 'star_runtime_2c9110', 'star_runtime_31e650']


def star_passes(star='under_edge'):
    """(outer tip, outer notch, inner tip, inner notch, diffuse, height) of each drawn pass of the installed table."""
    va, _size, code = next(row for row in ps.CAVES if row[0] <= ps.SYMBOLS['star_passes'] < row[0]+len(row[2]))
    code = ps._star_code(va, code, star)
    start, end = ps.SYMBOLS['star_passes'] - va, ps.SYMBOLS['star_passes_end'] - va
    rows = [struct.unpack_from('<4fIf', code, at) for at in range(start, end, 24)]
    return [row for row in rows if row[4] >> 24]


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
        for name, revision, pins in (
                ('thin', 'thin_v1', ps.LEGACY_OUTLINE_PINS),
                ('bold', 'bold_v2', ps.LEGACY_BOLD_OUTLINE_PINS),
                ('filled', 'filled_v3', ps.LEGACY_FILLED_PINS),
                ('badge', 'gold_badge_v4', ps.LEGACY_BADGE_C_PINS)):
            buf = bytearray(cls.retail)
            at = ps._offset(buf, ps.DRAW_CALL_VA)
            buf[at:at+5] = ps.PATCHED_DRAW_CALL
            fixture = json.loads((ROOT/f'tests/fixtures/nfl2k5_player_star_{revision}.json').read_text())
            for row in fixture['caves']:
                va = int(row['va'], 16)
                code = bytes.fromhex(row['code']).ljust(row['capacity'], b'\x90')
                assert hashlib.sha256(code).hexdigest() == pins[va]
                at = ps._offset(buf, va)
                buf[at:at+len(code)] = code
            for section in _sections(buf):
                buf[section.header_offset+36:section.header_offset+56] = section_digest(bytes(buf), section)
            setattr(cls, name, bytes(buf))

    def test_upgrade_status_and_idempotence(self):
        self.assertEqual(ps.status(self.retail), 'retail')
        self.assertEqual(ps.status(self.legacy), 'legacy')
        self.assertTrue(ps.read_settings(self.legacy)['needs_upgrade'])
        self.assertEqual(ps.status(self.patched), 'applied')
        self.assertEqual(ps.read_settings(self.patched)['renderer'], 'white_outline_star_under_edge')
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
        self.assertEqual(ps.read_settings(upgraded)['renderer_revision'], 'outline_star_v5')
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

    def test_exact_bold_outline_upgrades_only_inset_and_digest_through_dispatcher(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt

        self.assertEqual(ps.status(self.bold), 'legacy')
        self.assertEqual(ps.read_settings(self.bold)['renderer_revision'], 'bold_contrast_v2')
        self.assertEqual(ps.read_settings(self.bold)['renderer'], 'white_star_outline')
        self.assertTrue(ps.read_settings(self.bold)['needs_upgrade'])
        upgraded, receipt = ps.apply(self.bold)
        self.assertEqual(upgraded, self.patched)
        self.assertEqual(receipt['upgraded_renderer'], 'bold_contrast_v2')
        self.assertFalse(receipt['controller_gate_restored'])
        # the outline star (job km2) rewrites all five spans
        self.assertEqual([edit['label'] for edit in receipt['edits']], ALL_SPANS)
        allowed = set()
        for va, size, _ in ps.CAVES:
            allowed.update(range(ps._offset(self.bold, va), ps._offset(self.bold, va)+size))
        for section in _sections(self.bold):
            allowed.update(range(section.header_offset+36, section.header_offset+56))
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(self.bold, upgraded)) if a != b))
        dispatched, receipt = tt._apply_all(self.bold, None, catch_slider=False, player_star=True)
        self.assertEqual(dispatched, self.patched)
        self.assertEqual(receipt['player_star_patch']['upgraded_renderer'], 'bold_contrast_v2')
        repeat, receipt = tt._apply_all(dispatched, None, catch_slider=False, player_star=True)
        self.assertEqual(repeat, dispatched)
        self.assertTrue(receipt['player_star_patch']['already_applied'])

    def test_exact_filled_white_star_upgrades_to_the_outline_star(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt

        self.assertEqual(ps.status(self.filled), 'legacy')
        settings = ps.read_settings(self.filled)
        self.assertEqual(settings['renderer_revision'], 'filled_contrast_v3')
        self.assertEqual(settings['renderer'], 'white_star_filled')
        self.assertTrue(settings['needs_upgrade'])
        upgraded, receipt = ps.apply(self.filled)
        self.assertEqual(upgraded, self.patched)
        self.assertEqual(receipt['upgraded_renderer'], 'filled_contrast_v3')
        self.assertEqual([edit['label'] for edit in receipt['edits']], ALL_SPANS)
        self.assertEqual(ps.read_settings(upgraded)['renderer_revision'], 'outline_star_v5')
        dispatched, receipt = tt._apply_all(self.filled, None, catch_slider=False, player_star=True)
        self.assertEqual(dispatched, self.patched)
        self.assertEqual(receipt['player_star_patch']['upgraded_renderer'], 'filled_contrast_v3')

    def test_badge_c_upgrades_to_the_outline_star_and_the_outline_variant_is_one_flag(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt

        self.assertEqual(ps.status(self.badge), 'legacy')
        settings = ps.read_settings(self.badge)
        self.assertEqual((settings['renderer_revision'], settings['renderer']), ('gold_badge_v4', 'gold_star_white_rim'))
        self.assertTrue(settings['needs_upgrade'])
        upgraded, receipt = ps.apply(self.badge)
        self.assertEqual(upgraded, self.patched)
        self.assertEqual(receipt['upgraded_renderer'], 'gold_badge_v4')
        self.assertEqual([edit['label'] for edit in receipt['edits']], ALL_SPANS)
        dispatched, receipt = tt._apply_all(self.badge, None, catch_slider=False, player_star=True)
        self.assertEqual(dispatched, self.patched)
        # the outline-only variant: the under-edge pass's alpha byte at zero, still 'applied'
        outline, receipt = ps.apply(self.patched, 'outline')
        self.assertEqual((ps.status(outline), ps.installed_star(outline)), ('applied', 'outline'))
        alpha = ps._offset(outline, ps.SYMBOLS['star_passes'] + 19)
        self.assertEqual((self.patched[alpha], outline[alpha]), (0xC8, 0))
        digests = set()
        for section in _sections(outline):
            digests.update(range(section.header_offset+36, section.header_offset+56))
        self.assertTrue(all(i in digests or i == alpha for i, (a, b) in enumerate(zip(self.patched, outline)) if a != b))
        self.assertEqual(ps.apply(outline, 'under_edge')[0], self.patched)
        self.assertEqual(ps.apply(outline, 'outline')[1]['changed_bytes'], 0)
        self.assertEqual(ps.apply(self.badge, 'outline')[0], outline)
        with self.assertRaises(ps.PlayerStarError):
            ps.apply(self.patched, 'gold')

    def test_modified_and_mixed_sites_fail_closed(self):
        for source in (self.retail, self.legacy, self.thin, self.bold, self.filled, self.badge, self.patched):
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

    def test_filled_star_composes_with_every_pairwise_owner_in_both_orders(self):
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import OWNERS, prerequisites
        from tests import nfl2k5_allocator_stack as stack
        from mod_editor.core import nfl2k5_xbe_space as space

        seed, _ = space.apply(prerequisites(self.retail), stack.REQUESTS, scaleout=True)
        for name, owner in OWNERS:
            with self.subTest(owner=name):
                before_star, _ = owner.apply(seed)
                left, _ = ps.apply(before_star)
                before_owner, _ = ps.apply(seed)
                right, _ = owner.apply(before_owner)
                self.assertEqual(left, right)
                self.assertEqual(ps.status(left), 'applied')
                self.assertEqual(owner.status(left), 'applied')
                self.assertEqual(ps.apply(left)[0], left)
                self.assertEqual(owner.apply(left)[0], left)


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

    def test_all_22_get_the_outline_star_pair_across_modes_and_control_assignments(self):
        for mode in range(9):
            for controlled in ((), (0,), (3, 12)):
                with self.subTest(mode=mode, controlled=controlled):
                    vm = self.Machine(self.fixed)
                    entities = vm.entities([1]*22, mode=mode, controlled=controlled)
                    vm.frame()
                    self.assertEqual(len(vm.strips), 44)
                    self.assertEqual(vm.u32(ps.STAR_COUNT_VA)&255, len(controlled))
                    self.assertEqual(len(vm.models), len(controlled))
                    for index, strip in enumerate(vm.strips):
                        self.assertEqual(strip['entity'], entities[index//2])
                        self.assertEqual(strip['world_mode'], 1)
                        self.assertEqual(strip['material_address'] % 16, 0)
                        self.assertEqual(strip['primitive'], 6)
                        self.assertEqual(strip['transform'], 0)
                        self.assertEqual(strip['vertex_mode'], 0)
                        self.assertEqual(len(strip['vertices']), 22)
                        self.assertTrue(all(v[3] == 0xFFFFFFFF for v in strip['vertices']))
                        mat = strip['material']
                        self.assertEqual(struct.unpack_from('<I', mat, 0x18)[0],
                                         0xC80E0E10 if index%2 == 0 else 0xFFFFFFFF)
                        self.assertEqual(struct.unpack_from('<I', mat, 0x30)[0], 0)
                        self.assertEqual(struct.unpack_from('<I', mat, 0x60)[0]&0x0F000000, 0)

    def test_geometry_is_an_even_outline_star_at_interpolated_feet(self):
        vm = self.Machine(self.fixed)
        vm.entities([1])
        vm.frame()
        cx, cz = vm.centers[0]
        passes = star_passes()
        self.assertEqual(len(vm.strips), 2)
        # the dark under-edge first (lower), then the white outline
        self.assertEqual([p[4] for p in passes], [0xC80E0E10, 0xFFFFFFFF])
        self.assertEqual([p[5] for p in passes], [5.0, 5.5])
        for strip, (ot, on, it, inn, _diffuse, height) in zip(vm.strips, passes):
            vertices = strip['vertices']
            self.assertEqual(len(vertices), 22)
            for i in (0, 1):                               # ray 10 repeats ray 0 and closes the strip
                for a, b in zip(vertices[i][:3], vertices[20+i][:3]):
                    self.assertAlmostEqual(a, b, places=3)
            outer, inner = [], []
            for j, (x, y, z, _) in enumerate(vertices):
                k, is_inner = divmod(j, 2)
                r = ((it if k % 2 == 0 else inn) if is_inner else (ot if k % 2 == 0 else on))
                angle = k*math.pi/5
                self.assertAlmostEqual(x, cx + r*math.sin(angle), places=2)
                self.assertAlmostEqual(z, cz - r*math.cos(angle), places=2)
                self.assertEqual(y, height)
                if k < 10:
                    (inner if is_inner else outer).append((x, z))
            def area(points):
                return abs(sum(points[i][0]*points[(i+1) % 10][1] - points[(i+1) % 10][0]*points[i][1] for i in range(10)))/2
            def tri(a, b, c):
                return abs((b[0]-a[0])*(c[2]-a[2])-(b[2]-a[2])*(c[0]-a[0]))/2
            covered = sum(tri(*vertices[i:i+3]) for i in range(20))
            self.assertAlmostEqual(covered, area(outer) - area(inner), delta=0.5)
        # the white outline is the star (tips 86.4, notches 29.376) and its 8 cm inward mitred offset:
        # every inner edge lies 8 cm inside its outer edge
        ot, on, it, inn = passes[1][:4]
        def point(r, k):
            return (r*math.sin(k*math.pi/5), -r*math.cos(k*math.pi/5))
        for k in range(10):
            a, b = point(ot if k % 2 == 0 else on, k), point(on if k % 2 == 0 else ot, k+1)
            p = point(it if k % 2 == 0 else inn, k)
            length = math.hypot(b[0]-a[0], b[1]-a[1])
            distance = abs((b[0]-a[0])*(a[1]-p[1]) - (a[0]-p[0])*(b[1]-a[1]))/length
            self.assertAlmostEqual(distance, 8.0, places=3)
        self.assertAlmostEqual(on/ot, 0.34, places=4)
        self.assertEqual(ot, struct.unpack('<f', struct.pack('<f', 86.4))[0])

    def test_the_outline_variant_draws_only_the_white_pass(self):
        outline, _ = ps.apply(self.fixed, 'outline')
        vm = self.Machine(outline)
        vm.entities([1, 1])
        vm.frame()
        self.assertEqual(len(vm.strips), 2)
        self.assertTrue(all(struct.unpack_from('<I', strip['material'], 0x18)[0] == 0xFFFFFFFF for strip in vm.strips))

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

    def test_replay_camera_branch_skips_both_renderers(self):
        for replay in (False, True):
            vm = self.Machine(self.fixed, replay_camera=replay)
            vm.entities([1, 0, 1], controlled=(0,))
            vm.frame()
            self.assertEqual(len(vm.strips), 0 if replay else 4)
            self.assertEqual(len(vm.models), 0 if replay else 1)
            self.assertEqual(vm.trace.count(ps.SYMBOLS['star_frame']), 0 if replay else 1)
            self.assertEqual(vm.trace.count(0xF9320), 0 if replay else 1)

    def test_material_copy_changes_only_diffuse_texture_and_culling(self):
        from tools.player_star.emulate import MATERIAL
        vm = self.Machine(self.fixed)
        vm.entities([1])
        original = bytes(vm.uc.mem_read(MATERIAL, 128))
        vm.frame()
        for strip, color in zip(vm.strips, (0xC80E0E10, 0xFFFFFFFF)):
            expected = bytearray(original)
            struct.pack_into('<I', expected, 0x18, color)
            struct.pack_into('<I', expected, 0x30, 0)
            struct.pack_into('<I', expected, 0x60, struct.unpack_from('<I', original, 0x60)[0] & 0xF0FFFFFF)
            self.assertEqual(strip['material'], bytes(expected))
        self.assertEqual(bytes(vm.uc.mem_read(MATERIAL, 128)), original)

    def test_no_human_and_inactive_null_or_other_bits(self):
        vm = self.Machine(self.fixed)
        entities = vm.entities([1, 2, 3, 1, 1, 1], inactive=(3,), missing_record=(4,), missing_body=(5,))
        vm.set32(0xE5FC50, 0)
        vm.frame()
        self.assertEqual(len(vm.strips), 4)
        self.assertEqual([strip['entity'] for strip in vm.strips], [entities[0]]*2 + [entities[2]]*2)
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

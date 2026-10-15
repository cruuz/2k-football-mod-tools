"""Super Bowl moments carry their own event walls (N06); modern games get the modern ball and older moments keep the disc ball (N15)."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import numpy as np
from PIL import Image
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core import nfl2k5_super_bowl_walls as walls
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_era_ball as ball
from mod_editor.core import nfl2k5_moment_venues as venues
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

DISC = os.environ.get('ME1_DISC')
SIZE = 16
ROW = dict(row=45, event='LII', season=2017, textures=[])


def fake_scene(textures=2):
    """A decoded scene holding `textures` 16 x 16 P8 textures, each with a gradient and a half-clear cutout."""
    rows, blob = [], bytearray(b'\x00' * 64)
    for k in range(textures):
        pixel = len(blob)
        rows.append(dict(index=k, format_name='P8', conversion_status='base_level_supported', width=SIZE,
                         height=SIZE, mip_levels=1, pixel_offset=pixel, palette_offset=pixel + SIZE * SIZE,
                         mapped_material_names=[f'mat{k}']))
        blob += bytes((i * 7 + k) % 256 for i in range(SIZE * SIZE))
        palette = bytearray()
        for i in range(256):
            palette += bytes((i, 255 - i, (i * 3) % 256, 255 if i % 2 else 0))
        blob += palette
    blob += b'\xee' * 32
    return dict(system_bytes=0, embedded_textures=rows), bytes(blob)


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.art = Path(self.temp.name)
        patch.object(walls, 'ART', self.art).start()
        patch.object(walls, '_MANIFEST', None).start()
        self.addCleanup(patch.stopall)
        self.rec, self.decoded = fake_scene()

    def texture(self, material, alpha, colour=(200, 20, 40, 255), areas=None, name=None):
        rgba = np.zeros((SIZE, SIZE, 4), np.uint8)
        rgba[...] = colour
        rgba[:, :4, 3] = 0
        name = name or f'{material}.png'
        Image.fromarray(rgba).save(self.art / name)
        entry = dict(material=material, file=name, size=[SIZE, SIZE], alpha=alpha,
                     sha256=hashlib.sha256((self.art / name).read_bytes()).hexdigest())
        if areas:
            entry['areas'] = areas
        return entry

    def write_manifest(self, textures, row=45):
        doc = dict(schema=walls.SCHEMA, held_rows=[34], rows=[dict(row=row, event='LII', season=2017,
                                                                   textures=textures)])
        (self.art / 'manifest.json').write_text(json.dumps(doc), newline='\n')
        walls._MANIFEST = None
        return walls.entry(row)

    def row(self, k):
        return mv.p8_rows(self.rec)[k]

    def test_alpha_modes(self):
        current = mv.read_texture(self.decoded, self.rec, self.row(0))
        for alpha, expect in (('opaque', np.full((SIZE, SIZE), 255)),
                              ('source', np.where(current[..., 3] >= 128, 255, 0)),
                              ('art', np.where(np.arange(SIZE)[None, :].repeat(SIZE, 0) < 4, 0, 255))):
            rgba, resized, _ = walls.target(self.decoded, self.rec, self.row(0), self.texture('mat0', alpha), ROW,
                                            walls.Marks())
            self.assertFalse(resized)
            np.testing.assert_array_equal(rgba[..., 3], expect, err_msg=alpha)
            self.assertEqual(tuple(rgba[8, 8, :3]), (200, 20, 40))

    def test_areas_keep_disc_texels_outside(self):
        current = mv.read_texture(self.decoded, self.rec, self.row(0))
        texture = self.texture('mat0', 'opaque', areas=[[0, 8, 16, 16]])
        rgba, _, _ = walls.target(self.decoded, self.rec, self.row(0), texture, ROW, walls.Marks())
        np.testing.assert_array_equal(rgba[:8], current[:8])
        self.assertTrue((rgba[8:, :, :3] == (200, 20, 40)).all())

    def test_only_listed_texture_bytes_change_and_scope_is_checked(self):
        entry = self.write_manifest([self.texture('mat0', 'opaque')])
        edited, receipts, _ = walls.painted(self.decoded, self.rec, entry, walls.Marks())
        r0 = self.row(0)
        start, end = r0['pixel_offset'], r0['palette_offset'] + 1024
        self.assertNotEqual(bytes(edited[start:end]), self.decoded[start:end])
        self.assertEqual(bytes(edited[:start]), self.decoded[:start])
        self.assertEqual(bytes(edited[end:]), self.decoded[end:])
        walls._check_scope(self.decoded, bytes(edited), self.rec, receipts)
        edited[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'outside their textures'):
            walls._check_scope(self.decoded, bytes(edited), self.rec, receipts)

    def test_painted_surface_is_recognised_on_replay(self):
        entry = self.write_manifest([self.texture('mat0', 'opaque', areas=[[0, 8, 16, 16]]),
                                     self.texture('mat1', 'source', colour=(10, 60, 200, 255))])
        self.assertFalse(walls.already_painted(self.decoded, self.rec, entry, walls.Marks()))
        edited, _, _ = walls.painted(self.decoded, self.rec, entry, walls.Marks())
        self.assertTrue(walls.already_painted(bytes(edited), self.rec, entry, walls.Marks()))

    def test_refusals(self):
        entry = self.write_manifest([self.texture('mat0', 'opaque'), self.texture('mat0x', 'opaque')])
        with self.assertRaisesRegex(ValueError, 'lacks mat0x'):
            walls.painted(self.decoded, self.rec, entry, walls.Marks())
        self.rec['embedded_textures'][1]['mapped_material_names'] = ['mat1', 'mat0b']
        entry = self.write_manifest([self.texture('mat1', 'opaque'), self.texture('mat0b', 'opaque', name='b.png')])
        with self.assertRaisesRegex(ValueError, 'shares a texture'):
            walls.painted(self.decoded, self.rec, entry, walls.Marks())
        tampered = self.texture('mat0', 'opaque')
        tampered['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            walls.art(tampered)
        escape = dict(tampered, file='../outside.png')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            walls.art(escape)
        bad = self.texture('mat0', 'opaque', areas=[[0, 0, 17, 4]])
        with self.assertRaisesRegex(ValueError, 'area'):
            self.write_manifest([bad])

    def test_held_row_and_foreign_schema_refused(self):
        doc = dict(schema=walls.SCHEMA, held_rows=[34], rows=[dict(row=34, event='XXXVIII', textures=[])])
        (self.art / 'manifest.json').write_text(json.dumps(doc), newline='\n')
        with self.assertRaisesRegex(ValueError, 'held row'):
            walls.manifest()
        walls._MANIFEST = None
        (self.art / 'manifest.json').write_text(json.dumps(dict(doc, schema='other')), newline='\n')
        with self.assertRaisesRegex(ValueError, 'foreign'):
            walls.manifest()

    def test_rows_without_event_walls_are_untouched(self):
        self.write_manifest([self.texture('mat0', 'opaque')], row=45)
        bundle = b'not a bundle'
        self.assertEqual(walls.apply(bundle, 44), (bundle, None))


class ShippedArt(unittest.TestCase):
    def test_every_super_bowl_moment_but_the_held_one_has_event_walls(self):
        doc = walls.manifest()
        catalog = {m['row']: m for m in json.loads((ROOT / 'data/nfl2k5_espn25_fields.json').read_text())['moments']}
        super_bowls = {row for row, m in catalog.items() if m.get('super_bowl')}
        self.assertEqual(len(super_bowls), 17)
        self.assertEqual(doc['held_rows'], [34])
        self.assertEqual({r['row'] for r in doc['rows']}, super_bowls - {34})
        for r in doc['rows']:
            self.assertEqual(r['event'], catalog[r['row']]['super_bowl'])
            names = {t['material'] for t in r['textures']}
            self.assertTrue({'banner_corp', 'banner_home_team', 'banner_away_team', 'banner_home_player'} <= names)
            self.assertGreater(len(names), 4, f"row {r['row']} has no venue surface")
            for t in r['textures']:
                self.assertEqual(walls.art(t).shape[:2], tuple(t['size'][::-1]))

    def test_art_folder_holds_only_manifest_files(self):
        doc = walls.manifest()
        listed = ({t['file'] for r in doc['rows'] for t in r['textures']} | {'manifest.json'}
                  | {t['layer'] for r in doc['rows'] for t in r['textures'] if t.get('layer')})
        present = {p.relative_to(walls.ART).as_posix() for p in walls.ART.rglob('*') if p.is_file()}
        self.assertEqual(present, listed)

    def test_compiler_wires_the_pass_after_period_protection(self):
        source = (ROOT / 'mod_editor/core/nfl2k5_espn25_fields.py').read_text()
        self.assertLess(source.index('protect_period_field(after)'),
                        source.index("super_bowl_walls.apply(after, row['row'], marks=marks)"))


@unittest.skipUnless(DISC, 'set ME1_DISC to the read-only base disc')
class Disc(unittest.TestCase):
    """Real aliases: a built venue (LII, U.S. Bank) and a retail venue with kept areas (LI, NRG)."""
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_historic_styles as historic
        cls.bundles = {}
        with historic.Source(Path(DISC)) as source:
            situ = source.get(identity=historic.SITU_OUTER_ID)
            for row in (45, 30):
                cls.bundles[row] = source.get(f'a{row - 1:02d}{fields.variant(situ, row - 1)}.iff')

    def test_only_the_stadium_span_changes_and_replay_is_a_no_op(self):
        for row, bundle in self.bundles.items():
            with self.subTest(row=row):
                new, receipt = walls.apply(bundle, row)
                self.assertTrue(receipt['written'])
                self.assertEqual(len(new), len(bundle))
                at, size = receipt['stadium_offset'], receipt['stadium_size']
                self.assertEqual(new[:at], bundle[:at])
                self.assertEqual(new[at + size:], bundle[at + size:])
                again, second = walls.apply(new, row)
                self.assertEqual(again, new)
                self.assertTrue(second['already_applied'])
                _, rec, before = walls._stadium_chunk(bundle)
                _, _, after = walls._stadium_chunk(new)
                listed = {t['texture'] for t in receipt['textures']}
                every = set(mv.p8_rows(rec))
                old, now = walls.texture_bytes(before, rec, every), walls.texture_bytes(after, rec, every)
                self.assertEqual({int(k) for k in old if old[k] != now[k]}, listed)


# --- N15: the era ball ---------------------------------------------------------------------------------------------

HAVE_UNICORN = importlib.util.find_spec('unicorn') is not None
CAVE, HEAP, STACK = 0x300000, 0x200000, 0x400000


def run_selector(mode, ordinal, *, textures=2, signature=None):
    """Executes the selector from its cave entry to the displaced instruction's return; (tex0 palette, regs, stack)."""
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn import x86_const as x
    code, (site, retail, hook) = ball.selector(CAVE)
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    for base in (0x95000, CAVE, HEAP, STACK - 0x1000, ball.ORDINAL & ~0xFFF, ball.MODE & ~0xFFF):
        uc.mem_map(base, 0x2000)
    uc.mem_write(CAVE, code)
    scene, array, data1 = HEAP, HEAP + 0x100, HEAP + 0x1000
    uc.mem_write(scene + 0x14, struct.pack('<II', textures, array))
    uc.mem_write(array + 8, struct.pack('<I', 0xDEADBEEF))
    uc.mem_write(array + 0x24, struct.pack('<II', data1, 0))
    uc.mem_write(array + 0x2C, struct.pack('<I', ball.DUAL_FORMAT if signature is None else signature))
    uc.mem_write(ball.MODE, struct.pack('<I', mode))
    uc.mem_write(ball.ORDINAL, struct.pack('<I', ordinal))
    regs = {x.UC_X86_REG_EAX: 0x11, x.UC_X86_REG_EBX: 0x22, x.UC_X86_REG_ECX: 0x33, x.UC_X86_REG_EDX: 0x44,
            x.UC_X86_REG_ESI: 0x55, x.UC_X86_REG_EDI: scene, x.UC_X86_REG_EBP: 0x77, x.UC_X86_REG_ESP: STACK - 0x100}
    for reg, value in regs.items():
        uc.reg_write(reg, value)
    uc.reg_write(x.UC_X86_REG_EFLAGS, 0x246)
    uc.emu_start(CAVE, site + len(retail), count=200)
    after = {reg: uc.reg_read(reg) for reg in regs}
    pushed = struct.unpack('<I', uc.mem_read(after[x.UC_X86_REG_ESP], 4))[0]
    palette = struct.unpack('<I', uc.mem_read(array + 8, 4))[0]
    regs[x.UC_X86_REG_ESP] -= 4
    return palette, data1, after == regs and uc.reg_read(x.UC_X86_REG_EFLAGS) == 0x246, pushed


class BallData(unittest.TestCase):
    def test_old_rows_are_the_moments_before_2006(self):
        moments = json.loads((ROOT / 'data/nfl2k5_espn25_fields.json').read_text())['moments']
        self.assertEqual(ball.old_ball_rows(), [m['row'] for m in moments if m['season'] < 2006])
        self.assertEqual(ball.row_mask(), 0x383FFFFFF)

    def test_palette_b_sits_in_the_freed_normal_map_mips(self):
        self.assertEqual(ball.OLD_PALETTE, ball.TEX1['pixel'] + 65536 + 16384 + 4096)
        self.assertLessEqual(ball.OLD_PALETTE + ball.PALETTE_BYTES, ball.TEX1['palette'])
        self.assertEqual(ball.DUAL_FORMAT & 0xFFF0FFFF, ball.BALL_FORMAT & 0xFFF0FFFF)
        self.assertEqual((ball.DUAL_FORMAT >> 16) & 15, 3)

    def test_joint_palettes_carry_both_designs_through_one_index_image(self):
        rng = np.random.default_rng(5)
        modern = [rng.integers(0, 255, (n, n, 4), dtype=np.uint8) for n in (8, 4)]
        old = [255 - m for m in modern]
        palette, index = ball.joint_palettes(modern, old, 256)
        again, index2 = ball.joint_palettes(modern, old, 256)
        self.assertTrue((palette == again).all() and all((a == b).all() for a, b in zip(index, index2)))
        for m, o, i in zip(modern, old, index):
            self.assertTrue((palette[i][..., :3] == m[..., :3]).all())
            self.assertTrue((palette[i][..., 3:] == o[..., :3]).all())

    def test_shipped_art_is_authored_and_binary(self):
        rgba = ball.art()
        self.assertEqual(rgba.shape, (256, 256, 4))
        self.assertGreater(int((rgba[..., 3] == 255).sum()), 4000)
        doc = ball.manifest()
        self.assertEqual(doc['modern_from_season'], 2006)
        self.assertEqual(hashlib.sha256((ROOT / 'data/nfl2k5_era_ball' / doc['texture']['file']).read_bytes()).hexdigest(),
                         doc['texture']['sha256'])

    def test_selector_fits_and_hooks_the_ball_lookup(self):
        code, (site, retail, hook) = ball.selector(CAVE)
        self.assertEqual(len(code), ball.SELECTOR_SIZE)
        self.assertEqual((site, retail), (0x950CC, bytes.fromhex('687057e600')))
        self.assertEqual(hook, b'\xe9' + struct.pack('<i', CAVE - site - 5))
        self.assertEqual(struct.unpack('<Q', code[-8:])[0], ball.row_mask())

    def test_moment_venues_installs_the_selector_inside_its_owner(self):
        body, edits = venues.code_for(0x500000)
        self.assertEqual(len(body), venues.CODE_SIZE)
        self.assertIn(ball.HOOK[1], [site for site, _, _ in edits])
        site, _, hook = edits[-1]
        target = site + 5 + struct.unpack('<i', hook[1:])[0]
        self.assertEqual(body[target - 0x500000:][:ball.SELECTOR_SIZE], ball.selector(target)[0])
        old_body, old_edits = venues.code_for(0x500000, ball=False)
        self.assertNotIn(ball.HOOK[1], [s for s, _, _ in old_edits])
        at = target - 0x500000
        self.assertEqual(at + ball.SELECTOR_SIZE, venues.TABLE)
        self.assertEqual(old_body[at:venues.TABLE], b'\xcc' * ball.SELECTOR_SIZE)
        self.assertEqual(body[:at] + body[venues.TABLE:], old_body[:at] + old_body[venues.TABLE:])

    def test_build_runs_the_ball_after_every_global_writer(self):
        source = (ROOT / 'mod_editor/core/mod_build.py').read_text()
        at = source.index('era_ball.apply_to_image(target)')
        for writer in ('apply_fields_to_image', 'helmets.apply_to_image', 'wipes.apply_to_image'):
            self.assertLess(source.index(writer), at, writer)
        self.assertLess(at, source.index('finish_private(target'))


@unittest.skipUnless(HAVE_UNICORN, 'Unicorn required to execute the selector')
class BallSelector(unittest.TestCase):
    def test_old_moments_take_palette_b(self):
        for ordinal in (0, 25, 31, 32, 33):
            palette, data1, kept, pushed = run_selector(8, ordinal)
            self.assertEqual(palette, data1 + 0x15000, ordinal)
            self.assertTrue(kept)
            self.assertEqual(pushed, 0xE65770)

    def test_normal_games_and_later_moments_take_palette_a(self):
        for mode, ordinal in ((8, 26), (8, 30), (8, 34), (8, 50), (8, 51), (8, 0x40), (0, 0), (3, 5), (9, 0)):
            palette, data1, kept, _ = run_selector(mode, ordinal)
            self.assertEqual(palette, data1 - 0x440, (mode, ordinal))
            self.assertTrue(kept)

    def test_unsigned_or_foreign_scenes_are_untouched(self):
        for kwargs in (dict(signature=ball.BALL_FORMAT), dict(textures=1), dict(textures=3)):
            palette, _, kept, pushed = run_selector(8, 0, **kwargs)
            self.assertEqual(palette, 0xDEADBEEF, kwargs)
            self.assertTrue(kept)
            self.assertEqual(pushed, 0xE65770)


@unittest.skipUnless(DISC, 'set ME1_DISC to the read-only base disc')
class BallDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_historic_styles as historic
        from mod_editor.core import nfl2k5_espn25_rosters as rosters
        with historic.Source(Path(DISC)) as source:
            cls.outer = source.get(identity=ball.GLOBAL_ID)
        cls.xbe = rosters.read_xbe(Path(DISC))

    def test_only_the_ball_span_changes_and_replay_is_a_no_op(self):
        new, receipt = ball.apply_global(self.outer)
        self.assertEqual((ball.state(self.outer), ball.state(new)), ('retail', 'applied'))
        self.assertEqual(len(new), len(self.outer))
        at, size = receipt['ball_offset'], receipt['ball_size']
        self.assertEqual(new[:at], self.outer[:at])
        self.assertEqual(new[at + size:], self.outer[at + size:])
        again, second = ball.apply_global(new)
        self.assertEqual(again, new)
        self.assertTrue(second['already_applied'])
        self.assertLess(receipt['disc_ball_mean_abs_error'], 1.5)
        self.assertLess(receipt['modern_mean_abs_error'], 1.5)

    def test_palette_b_reproduces_the_disc_ball(self):
        new, _ = ball.apply_global(self.outer)
        _, rec, decoded = ball.ball_scene(self.outer)
        disc = ball._levels(decoded, int(rec['system_bytes']))[0][..., :3].astype(int)
        a, b, index = ball.palettes(new)
        self.assertLess(float(np.abs(b[index][..., :3].astype(int) - disc).mean()), 1.5)
        self.assertGreater(float(np.abs(a[index][..., :3].astype(int) - disc).mean()), 3.0)

    def test_previous_venue_owner_upgrades_and_restores(self):
        self.assertEqual(venues.status(self.xbe), 'previous')
        upgraded, receipt = venues.apply(self.xbe)
        self.assertEqual((venues.status(upgraded), receipt['status']), ('applied', 'applied'))
        self.assertEqual(venues.apply(upgraded)[1]['status'], 'already_applied')
        image = XbeImage(upgraded)
        self.assertNotEqual(image.read(ball.HOOK[1], 5), ball.HOOK[2])
        self.assertEqual(XbeImage(venues.underlying(upgraded)).read(ball.HOOK[1], 5), ball.HOOK[2])


class RepairContract(unittest.TestCase):
    """Exercise actual writes on tiny synthetic files, never an image copy."""
    def setUp(self):
        import contextlib
        import io
        from b77 import me1_repair as repair
        self.repair = repair
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.original, self.copy = self.folder / 'original.bin', self.folder / 'copy.bin'
        self.before, self.after = b'0123456789abcdef', b'0123XYZ789abcdeQ'
        self.mo2, self.mo2_after = b'0123456789MO2def', b'0123XYZ789MO2deQ'
        self.original.write_bytes(self.before)
        self.copy.write_bytes(self.before)
        (self.folder / '000.span').write_bytes(b'XYZ')
        (self.folder / '001.span').write_bytes(b'Q')
        sha = repair.sha
        self.pins = dict(schema='b773/me1/v1', size=16,
                         inputs={sha(self.before): sha(self.after), sha(self.mo2): sha(self.mo2_after)},
                         spans=[dict(offset=4, length=3, file='000.span', before_sha256=sha(b'456'),
                                     after_sha256=sha(b'XYZ')),
                                dict(offset=15, length=1, file='001.span', before_sha256=sha(b'f'),
                                     after_sha256=sha(b'Q'))])
        repair.write_json(self.folder / 'pins.json', self.pins)
        self.addCleanup(patch.stopall)
        patch.object(repair, 'PINS', self.folder / 'pins.json').start()
        patch.object(repair, 'BASE_SHA', sha(self.before)).start()
        self.receipt = self.folder / 'receipt.json'
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def written(self):
        return json.loads(self.receipt.read_text())['written_bytes']

    def test_fixed_span_write_replay_and_full_scope(self):
        self.repair.apply(self.copy, self.folder, self.receipt)
        self.assertEqual(self.written(), 4)
        self.repair.apply(self.copy, self.folder, self.receipt)
        self.assertEqual(self.written(), 0)
        self.repair.scope(self.original, self.copy, self.receipt)
        self.assertEqual(self.copy.read_bytes(), self.after)
        self.assertEqual(json.loads(self.receipt.read_text()), dict(kind='physical_full_disc_compare',
                                                                    changed_bytes=4, changed_outside_spans=0))

    def test_the_post_mo2_input_reaches_its_own_output(self):
        self.copy.write_bytes(self.mo2)
        self.repair.apply(self.copy, self.folder, self.receipt)
        self.assertEqual(self.copy.read_bytes(), self.mo2_after)
        self.assertEqual(json.loads(self.receipt.read_text())['output_sha256'], self.repair.sha(self.mo2_after))

    def test_unknown_input_refused_before_write(self):
        self.copy.write_bytes(b'unknown candidate')
        with self.assertRaisesRegex(ValueError, 'unknown input disc'):
            self.repair.apply(self.copy, self.folder, self.receipt)
        self.assertEqual(self.copy.read_bytes(), b'unknown candidate')
        self.assertFalse(self.receipt.exists())

    def test_tampered_payload_refused_before_write(self):
        (self.folder / '000.span').write_bytes(b'BAD')
        with self.assertRaisesRegex(ValueError, 'payload hash mismatch'):
            self.repair.apply(self.copy, self.folder, self.receipt)
        self.assertEqual(self.copy.read_bytes(), self.before)

    def test_plan_must_match_the_shipped_pins(self):
        doc = dict(self.pins, size=17)
        self.repair.write_json(self.folder / 'pins.json', doc)
        patch.object(self.repair, 'PINS', self.folder / 'other.json').start()
        self.repair.write_json(self.folder / 'other.json', self.pins)
        with self.assertRaisesRegex(ValueError, 'plan differs'):
            self.repair.apply(self.copy, self.folder, self.receipt)

    def test_scope_rejects_change_outside_spans(self):
        bad = b'0123XYZ78!abcdeQ'
        self.copy.write_bytes(bad)
        self.pins['inputs'][self.repair.sha(self.before)] = self.repair.sha(bad)
        self.repair.write_json(self.folder / 'pins.json', self.pins)
        with self.assertRaisesRegex(ValueError, 'out-of-scope change'):
            self.repair.scope(self.original, self.copy, self.receipt)

    def test_executable_runs_join_close_changes_only(self):
        before = bytes(64)
        after = bytearray(before)
        after[3] = after[10] = after[40] = 1
        self.assertEqual(self.repair.xbe_runs(before, bytes(after)), [(3, 11), (40, 41)])

    def test_shipped_pins_cover_both_inputs_and_every_target(self):
        pins = json.loads((ROOT / 'tools/b77/me1_pins.json').read_text())
        mo2 = json.loads((ROOT / 'tools/b77/mo2_pins.json').read_text())
        self.assertEqual(set(pins['inputs']), {mo2['input_sha256'], mo2['output_sha256']})
        names = [s['name'] for s in pins['spans']]
        self.assertEqual(sum(n.endswith(' stadium') for n in names), 16)
        self.assertEqual(names.count('global.iff ball'), 1)
        self.assertIn('default.xbe +0x850cc', names)
        spans = sorted((s['offset'], s['offset'] + s['length']) for s in pins['spans'])
        self.assertTrue(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])))
        for m in mo2['spans']:
            self.assertFalse(any(lo < m['offset'] + m['length'] and m['offset'] < hi for lo, hi in spans))


if __name__ == '__main__':
    unittest.main()

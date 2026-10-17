"""sb1: Super Bowl flank marks on the Anniversary fields and the franchise Super Bowl hosts.

The static tests need nothing. The executable test reads the retail XBE (SB1_RETAIL_XBE); the field and host tests
read the retail disc (SB1_RETAIL) and a finished SOFTDRINK build (SB1_BUILT). User-art tests use synthetic placeholder
images (plain shapes), never a real logo."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import numpy as np
from PIL import Image, ImageDraw
from mod_editor.core import nfl2k5_super_bowl_fields as sbf
from mod_editor.core import nfl2k5_super_bowl_hosts as hosts
from mod_editor.core import nfl2k5_super_bowl_walls as walls

RETAIL = os.environ.get('SB1_RETAIL')
BUILT = os.environ.get('SB1_BUILT')
RETAIL_XBE = os.environ.get('SB1_RETAIL_XBE')
SB_ROWS = [14, 15, 21, 22, 23, 27, 28, 29, 30, 34, 35, 40, 42, 45, 46, 48, 50]


def placeholder(path, size=(400, 200), colour=(230, 0, 200)):
    im = Image.new('RGBA', size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([10, 10, size[0] - 10, size[1] - 10], fill=colour + (255,))
    d.text((size[0] // 3, size[1] // 2), 'TEST', fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


class Manifest(unittest.TestCase):
    def test_every_super_bowl_moment_has_flank_marks(self):
        doc = sbf.manifest()
        self.assertEqual([r['row'] for r in doc['rows']], SB_ROWS)
        kinds = {r['row']: r['flank']['kind'] for r in doc['rows']}
        self.assertEqual(kinds[15], 'shield')
        self.assertEqual({r for r, k in kinds.items() if k == 'team'}, {21, 22, 23})
        for r in doc['rows']:
            f = r['flank']
            # modern Super Bowls put the event mark on the 25s, the older ones on the 30s and 35s
            self.assertIn(f['from_mid_yd'], (15, 20, 25))
            if r['season'] >= 2003:
                self.assertEqual(f['from_mid_yd'], 25)

    def test_authored_marks_are_pinned_and_load(self):
        for key, item in sbf.manifest()['marks'].items():
            raw = (sbf.ART / item['file']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'], key)
            rgba = sbf.authored(key)
            self.assertEqual(list(rgba.shape[1::-1]), item['size'])
            self.assertTrue((rgba[..., 3] == 0).any() and (rgba[..., 3] == 255).any(), key)
        for event in ('LXII', 'LXIII', 'LXIV', 'LXV'):
            self.assertIn(event, sbf.manifest()['marks'])

    def test_team_flanks_follow_the_shipped_end_zones(self):
        """The club on each 30 is the club painted in that end zone (north is -z): the AFC clubs DEN, TEN and NE."""
        teams = {r['row']: r['flank'].get('teams') for r in sbf.manifest()['rows']}
        self.assertEqual(teams[21], {'N': 'DEN', 'S': 'GB'})
        self.assertEqual(teams[22], {'N': 'TEN', 'S': 'STL'})
        self.assertEqual(teams[23], {'N': 'NE', 'S': 'STL'})

    def test_texture_keeps_a_clear_margin(self):
        mark = sbf.trim(sbf.authored('XLII'))
        tex = sbf.texture(mark)
        self.assertEqual(tex.shape, (128, 128, 4))
        m = sbf.MARGIN
        self.assertFalse(tex[:m, :, 3].any() or tex[-m:, :, 3].any() or tex[:, :m, 3].any() or tex[:, -m:, 3].any())
        along, across = sbf.fitted_box(mark, (9.0, 7.0))
        self.assertTrue(along <= 9.0 + 1e-9 and across <= 7.0 + 1e-9)
        self.assertAlmostEqual(along / across, mark.shape[1] / mark.shape[0], places=6)

    def test_user_art_replaces_the_event_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            placeholder(Path(tmp) / 'super_bowl' / 'XLII.png')
            got = sbf.sources(sbf.entry(27), walls.Marks(None, tmp))['both']
            self.assertEqual(got[1]['source'], 'user_art')
            self.assertEqual(got[0].shape[:2], (200, 400))
            got = sbf.sources(sbf.entry(28), walls.Marks(None, tmp))['both']
            self.assertEqual(got[1]['source'], 'authored')

    def test_hosts_table(self):
        self.assertEqual([(h['index'], h['event'], h['slot'], h['source']) for h in hosts.HOSTS],
                         [(1, 'LXII', 's42', 's01'), (2, 'LXIII', 's43', 's20'), (3, 'LXIV', 's41', 's28')])
        self.assertEqual(len(hosts.VARIANTS), 9)


@unittest.skipUnless(RETAIL_XBE, 'SB1_RETAIL_XBE not set')
class Executable(unittest.TestCase):
    """The hiding rules this step relies on, read from the retail executable."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core.nfl2k5_bump_strength import _sections
        cls.xbe = Path(RETAIL_XBE).read_bytes()
        cls.sections = _sections(cls.xbe)

    def at(self, va, n):
        for s in self.sections:
            if s.virtual_address <= va < s.virtual_address + s.raw_size:
                return self.xbe[s.raw_offset + va - s.virtual_address:][:n]
        raise AssertionError(hex(va))

    def wide(self, va):
        raw = self.at(va, 64)
        return raw[:raw.index(b'\0\0\0') + 1].decode('utf-16le').rstrip('\0')

    def test_title_week_materials_are_looked_up_by_name(self):
        # mov edx,<name> before each lookup; the AFC/NFC flags are then forced hidden outside a title week
        self.assertEqual(self.at(0x9C705, 5), b'\xba' + struct.pack('<I', 0xE6662C))
        self.assertEqual(self.at(0x9C778, 5), b'\xba' + struct.pack('<I', 0xE66644))
        self.assertEqual(self.at(0x9C68B, 5), b'\xba' + struct.pack('<I', 0xE66610))
        self.assertEqual(self.wide(0xE6662C), 'AFC_shield')
        self.assertEqual(self.wide(0xE66644), 'NFC_shield')
        self.assertEqual(self.wide(0xE66610), 'playoff_logo')

    def test_renamed_names_are_never_looked_up(self):
        for name in sbf.RENAMES.values():
            self.assertNotIn(name.encode('utf-16le'), self.xbe)
            self.assertNotIn(name.encode(), self.xbe)

    def test_super_bowl_venue_codes(self):
        codes = [self.wide(0xE79528 + 8 * k) for k in range(6)]
        self.assertEqual(codes, ['s40', 's42', 's43', 's41', 's44', 's45'])
        self.assertEqual([h['slot'] for h in hosts.HOSTS], codes[1:4])


@unittest.skipUnless(RETAIL and BUILT, 'SB1_RETAIL and SB1_BUILT not set')
class Fields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_espn25_fields as fields
        from mod_editor.core import nfl2k5_historic_styles as hs
        cls.fields = fields
        with hs.Source(Path(RETAIL)) as retail, hs.Source(Path(BUILT)) as built:
            cls.situ = built.get(identity=hs.SITU_OUTER_ID)
            cls.template = {v: retail.get(f's25{v}.iff') for v in hosts.VARIANTS}
            cls.period, _ = walls.period_shield(retail.get(walls.PERIOD_SHIELD_RESOURCE))
            cls.wordmarks = {}
            for team in ('NYG', 'NE', 'TEN', 'LAR', 'BUF'):
                cls.wordmarks[team] = fields._wordmark(retail.get(fields.WORDMARKS[team] + 'dd.iff'), team)
        cls.catalog = {r['row']: r for r in fields.catalog()}

    def build(self, row, user_art=None):
        code = self.fields.variant(self.situ, row - 1)
        return self.fields._field(self.template[code], self.catalog[row], self.wordmarks, None,
                                  walls.Marks(self.period, user_art))

    def overlay(self, span):
        from mod_editor.core import nfl2k5_modern_metlife as mm
        tx = mm._tools()[0]
        chunk = tx.parse_chunks(span, allow_trailing=True)[0]
        rec, dec = mm._scene(span, chunk)
        return rec, dec

    def quads(self, rec, dec, material):
        shape = [s for s in rec['shapes'] if s['name'] == sbf.OVERLAY_SHAPE][0]
        st0 = sbf._stream(shape, 0)
        out = []
        for q in sbf._quads(rec, dec, shape, material):
            P = np.array([struct.unpack_from('<3f', dec, st0['offset'] + st0['stride'] * i) for i in q]) / 100.0
            out.append(P)
        return out

    def test_xlii_marks_on_both_25s(self):
        span, detail = self.build(27)
        rec, dec = self.overlay(span)
        names = {m['name'] for m in rec['materials']}
        self.assertIn('era_flankA', names)
        self.assertNotIn('AFC_shield', names)
        self.assertIn('NFC_shield', names)            # stays hidden by the executable
        zs = sorted(round(P[:, 2].mean() / sbf.YARD_M, 2) for P in self.quads(rec, dec, 'era_flankA'))
        self.assertEqual(zs, [-25.0, 25.0])
        for P in self.quads(rec, dec, 'era_flankA'):
            self.assertAlmostEqual(P[:, 0].mean(), 0.0, places=3)
        self.assertFalse(detail['geometry_and_descriptors_preserved'])
        self.assertEqual(len(detail['flank_ranges']), 8 + 1)    # eight vertices and one name
        self.assertEqual(detail['super_bowl_flanks']['slots'][0]['source'], 'authored')

    def test_xxxiv_each_club_on_its_own_side(self):
        span, detail = self.build(22)
        rec, dec = self.overlay(span)
        for material, side in (('era_flankA', 1), ('era_flankN', -1)):
            visible = [P for P in self.quads(rec, dec, material) if np.ptp(P[:, 2]) > 0.1]
            collapsed = [P for P in self.quads(rec, dec, material) if np.ptp(P[:, 2]) <= 1e-6]
            self.assertEqual(len(visible), 1)
            self.assertEqual(len(collapsed), 1)
            self.assertAlmostEqual(visible[0][:, 2].mean() / sbf.YARD_M, side * 20.0, places=2)
        sides = {s['sides']: s['key'] for s in detail['super_bowl_flanks']['slots']}
        self.assertEqual(sides, {'S': 'STL', 'N': 'TEN'})

    def test_xxv_period_shields(self):
        span, detail = self.build(15)
        self.assertEqual(detail['super_bowl_flanks']['slots'][0]['source'], 'disc_period_shield')

    def test_user_art_fills_the_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            placeholder(Path(tmp) / 'super_bowl' / 'XLII.png')
            span, detail = self.build(27, tmp)
        self.assertEqual(detail['super_bowl_flanks']['slots'][0]['source'], 'user_art')

    def test_rows_without_a_super_bowl_are_unchanged(self):
        span, detail = self.build(33)
        self.assertNotIn('super_bowl_flanks', detail)
        self.assertTrue(detail['geometry_and_descriptors_preserved'])
        rec, _ = self.overlay(span)
        self.assertIn('AFC_shield', {m['name'] for m in rec['materials']})


@unittest.skipUnless(BUILT, 'SB1_BUILT not set')
class Hosts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_historic_styles as hs
        from mod_editor.core import nfl2k5_modern_metlife as ml
        with hs.Source(Path(BUILT)) as built:
            cls.s01 = built.get('s01nd.iff')
        with ml._outer_image()(str(BUILT)) as image:
            e = image.entries[ml.ROST_OUTER_INDEX]
            cls.rost = image.read(e.virtual_offset, e.size)

    def test_super_bowl_field_on_the_host_copy(self):
        from mod_editor.core import nfl2k5_espn25_fields as fields
        copy, receipt = hosts.super_bowl_field(self.s01, hosts.HOSTS[0], walls.Marks(None, None))
        _c, rec, dec = fields._field_chunk(copy)
        names = {m['name'] for m in rec['materials']}
        self.assertTrue({'era_midlogo', 'era_flankA'} <= names)
        self.assertFalse({'center_logo', 'AFC_shield'} & names)
        self.assertEqual(receipt['flanks']['slots'][0]['key'], 'LXII')
        self.assertEqual(receipt['flanks']['from_mid_yd'], 25)
        again, _ = hosts.super_bowl_field(self.s01, hosts.HOSTS[0], walls.Marks(None, None))
        self.assertEqual(again, copy)

    def test_rost_rows(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        body = self.rost[rr.RESOURCE_HEADER_SIZE:]
        self.assertTrue(all(hosts.ready(body, h) for h in hosts.HOSTS))
        after, receipt = hosts.rost_hosts(self.rost, hosts.HOSTS)
        self.assertEqual(len(after), len(self.rost))
        records = hosts._records(after[rr.RESOURCE_HEADER_SIZE:])
        self.assertEqual(records['s42'][1]['name'][1], 'Super Bowl LXII')
        self.assertEqual(records['s42'][1]['display_name'][1], 'Mercedes-Benz Stadium')
        self.assertEqual(records['s43'][1]['location'][1], 'Las Vegas, NV')
        self.assertEqual(records['s41'][1]['display_name'][1], 'Nissan Stadium')
        for code in ('s40', 's44', 's45', 's01', 's20', 's28'):
            self.assertEqual(records[code], hosts._records(self.rost[rr.RESOURCE_HEADER_SIZE:])[code])
        again, receipt2 = hosts.rost_hosts(after, hosts.HOSTS)
        self.assertEqual(again, after)
        self.assertEqual({r['state'] for r in receipt2}, {'already_applied'})

    def test_repoint_keeps_every_other_row(self):
        from mod_editor.core import nfl2k5_anniversary_pack as ap
        from mod_editor.core import nfl2k5_espn25_more_moments as mm
        from mod_editor.core import nfl2k5_music_archive as archive
        with archive.Disc(Path(BUILT), descriptors=()) as disc:
            p0, pf = disc.pack_extents['0'], disc.pack_extents['F']
            raw0, raw_f = disc.read(p0.size, p0.byte_offset), disc.read(pf.size, pf.byte_offset)
        rep = {'s42dd.iff': b'sb1' * 1000, 's43nr.iff': bytes(range(256)) * 40}
        out0, out_f, receipt = hosts.repoint_packs(raw0, raw_f, rep)
        before, after = ap.entries(raw0), ap.entries(out0)
        self.assertEqual(len(before), len(after))
        self.assertEqual(sum(a != b for a, b in zip(before, after)), 2)
        self.assertEqual(out_f[:len(raw_f)], raw_f)
        f_start = sum(struct.unpack_from('<16I', out0, 12)[:15]) * 2048
        for name, raw in rep.items():
            row = [r for r in after if r[0] == mm.name_id(name)][0]
            at = row[2] * 2048 - f_start
            self.assertEqual(out_f[at:at + row[1]], raw)
        self.assertEqual(len(out_f) % 2048, 0)


if __name__ == '__main__':
    unittest.main()

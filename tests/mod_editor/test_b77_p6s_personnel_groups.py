"""b77 p6s: personnel-group twins, lottery codes, labels and masks in complete offense packs (PROVED OFFLINE).

The Titans book recodes three spare personnel groups so the CPU's native category target (0x209FE0) finds 11 and 12
personnel on passing downs. These tests compile the shipped TEN pack against the retail TEN book and check the written
records, the refusals that keep retained formations' groups stock, and the analytic CPU selector on the result.
Gameplay is unwitnessed."""
import copy
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_complete_offense as full  # noqa: E402

IMAGE = Path(os.environ.get('NFL2K5_RETAIL_IMAGE', '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))
XBE = Path(os.environ.get('NFL2K5_RETAIL_XBE', '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe'))
os.environ.setdefault("NFL2K5_SCORING_XBE", str(XBE))
PACK = ROOT / 'data/playbooks/softdrink_ten_modern.2k5book'


def retail_ten():
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    with OuterImage(IMAGE) as image:
        return image.read_entry(BOOK_ENTRIES['TEN'])


@unittest.skipUnless(IMAGE.exists(), 'retail image not mounted')
class PersonnelGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_ten()
        cls.pack = packs.load_pack(PACK)
        cls.compiled = full.compile_offense(cls.retail, cls.pack, asset_id='book:TEN')
        cls.body = cls.compiled.replacement[32:]

    def cat(self, body, ci):
        off = insp.CATEGORY_BASE + ci * insp.CATEGORY_SIZE
        return body[off + 4] & 0x3F, bytes(body[off + 5:off + 16])

    def test_twins_codes_and_names_are_written(self):
        old = self.retail[32:]
        book = insp.parse_playbook_resource(self.compiled.replacement)
        names = {c.index: c.name.strip() for c in book.categories}
        kings, ace = self.cat(old, 4)[1], self.cat(old, 2)[1]
        self.assertEqual((names[5], self.cat(self.body, 5)), ('Kings Early', (5, kings)))
        self.assertEqual((names[6], self.cat(self.body, 6)), ('Ace Long', (8, ace)))
        self.assertEqual((names[7], self.cat(self.body, 7)), ('Kings Long', (9, kings)))
        for ci in (0, 1, 2, 3, 4, 8):          # every other group (Hail Mary's 5 Wide, Clock's Jokers) stays stock
            self.assertEqual(self.cat(self.body, ci), self.cat(old, ci))
            self.assertEqual(names[ci], insp.parse_playbook_resource(self.retail).categories[ci].name.strip())

    def test_masks_and_owners_follow_the_pack(self):
        for f in self.pack.formations:
            aux = insp.FORMATION_AUX_BASE + f.replace_index * insp.FORMATION_AUX_SIZE
            own, mask = struct.unpack_from('<II', self.body, aux + 0x48)
            self.assertEqual(own & 0x3F, f.category_index, f.custom_name)
            self.assertEqual(mask, sum(1 << c for c in f.category_mask), f.custom_name)
            for c in f.category_mask:
                self.assertEqual(sorted(lib.category_positions(self.body, c)), sorted(f.position_codes))

    def test_json_round_trip_keeps_the_new_fields(self):
        again = packs.loads_pack(self.pack.dumps())
        self.assertEqual(again.dumps(), self.pack.dumps())
        self.assertTrue(any(f.category_code == 9 and f.category_name == 'Kings Long' for f in again.formations))

    def test_retained_group_and_mixed_personnel_mask_refuse(self):
        doc = self.pack.to_json()
        i = next(n for n, f in enumerate(doc['formations']) if f['custom_name'] == 'Gun Trips')
        bad = copy.deepcopy(doc)
        bad['formations'][i]['category_index'] = 8          # 5 Wide: the retained Hail Mary formation's group
        bad['formations'][i]['category_mask'] = [4, 8]
        with self.assertRaises(packs.PlaybookPackError):
            full.compile_offense(self.retail, packs.pack_from_json(bad), asset_id='book:TEN')
        bad = copy.deepcopy(doc)
        bad['formations'][i]['category_mask'] = [2, 7]     # 12 personnel group in an 11 personnel formation's mask
        with self.assertRaises(packs.PlaybookPackError):
            full.compile_offense(self.retail, packs.pack_from_json(bad), asset_id='book:TEN')
        bad = copy.deepcopy(doc)
        j = next(n for n, f in enumerate(doc['formations']) if f['custom_name'] == 'Gun Empty Trey')
        bad['formations'][j]['category_code'] = 7           # two owners disagree about Kings Long's code
        with self.assertRaises(packs.PlaybookPackError):
            full.compile_offense(self.retail, packs.pack_from_json(bad), asset_id='book:TEN')

    def test_selector_keeps_11_personnel_on_third_and_long(self):
        from pb.v2 import selection_model as sm
        bk = sm.book_from(self.compiled.replacement)
        for sit in (dict(down=3, distance=8, yard=50), dict(down=3, distance=12, yard=30)):
            shares = sm.personnel_shares(bk, sit)
            self.assertGreater(shares.get('11', 0), 80, shares)
            self.assertLess(shares.get('10', 0), 1, shares)
        first = sm.personnel_shares(bk, dict(down=1, distance=10, yard=25))
        self.assertGreater(first.get('11', 0), 45, first)
        self.assertGreater(first.get('12', 0), 20, first)


    def test_selection_model_labels_twins_by_who_lines_up(self):
        from pb.v2 import selection_model as sm
        bk = sm.book_from(self.compiled.replacement)
        labels = {c['name']: c['personnel'] for c in bk.cats.values()}
        self.assertEqual((labels['Kings Long'], labels['Kings Early'], labels['Ace Long']), ('11', '11', '12'))
        self.assertEqual(sm.personnel_label(bytes([0, 5, 37, 6, 7, 39, 8, 9, 41, 73, 10])), '11')
        self.assertIsNone(sm.personnel_label(bytes([12, 13, 45, 77, 14, 15, 47, 16, 17, 18, 50])))

    def test_fit_search_never_worsens_and_keeps_every_owner_group(self):
        from pb.v2 import fit_cpu
        from pb.v2 import selection_model as sm
        bk = sm.book_from(self.compiled.replacement)
        fs = {f.replace_index for f in self.pack.formations}
        design = fit_cpu.Design(bk, fs)
        design.tags = {f.replace_index: fit_cpu.v2.oc.FORMATIONS[f.custom_name].tag for f in self.pack.formations}
        groups = {}
        for ci, c in bk.cats.items():
            if c['id'] <= 10 and c.get('personnel') and ci not in bk.special_cats:
                groups.setdefault(design.exact[ci], []).append(ci)
        state = {}
        for fi in sorted(fs):
            f = bk.forms[fi]
            mask = [c for c in range(26) if f['mask'] >> c & 1 and design.exact.get(c) == design.exact[f['own']]]
            state[fi] = (f['own'], sorted(set(mask) | {f['own']}), tuple((f['flags'] >> s) & 7 for s in (21, 24, 27)))
        owners = {own for own, _m, _r in state.values()}
        cells, gun_bins = fit_cpu.targets('TEN')
        start = fit_cpu.objective(design, state, cells, gun_bins)
        state2, best = fit_cpu.search(design, dict(state), groups, cells, gun_bins, 40, 7, log=lambda *_: None)
        self.assertLessEqual(best[0], start[0] + 1e-9)
        self.assertEqual({own for own, _m, _r in state2.values()}, owners)
        for fi, (own, mask, r) in state2.items():
            self.assertIn(own, mask)
            self.assertEqual(fit_cpu.clamp(design.tags.get(fi, ''), r), tuple(r))

    def test_rating_clamp_keeps_heavy_and_spread_sets_in_order(self):
        from pb.v2 import fit_cpu
        self.assertEqual(fit_cpu.clamp('goal', (3, 1, 0)), (3, 4, 4))
        self.assertEqual(fit_cpu.clamp('short', (0, 1, 2)), (0, 3, 4))
        self.assertEqual(fit_cpu.clamp('empty', (2, 4, 0)), (4, 4, 0))
        self.assertEqual(fit_cpu.clamp('pass', (2, 4, 0)), (2, 4, 0))


@unittest.skipUnless(XBE.exists(), 'retail executable not available')
class NativeRouteCheckTests(unittest.TestCase):
    """tools/b77/p6s_route_check.py: the game's route initializer on the concepts p6s fixed."""

    @classmethod
    def setUpClass(cls):
        from tools.b77 import p6s_route_check as rc
        cls.rc = rc
        cls.m = rc.machine(XBE)

    def flags(self, concept, formation):
        from mod_editor.core import nfl2k5_offense_concepts as oc
        spec = oc.FORMATIONS[formation]
        return {f[0] for f in self.rc.check_rows(self.m, {}, self.rc.design_rows(spec, oc.design(concept, spec.context())))}

    def test_left_receivers_are_traced_on_their_own_side(self):
        from mod_editor.core import nfl2k5_offense_concepts as oc
        nodes = oc.codec.encode_chain(oc.route_chain('Quick Out'))
        left = self.rc.trace(self.m, nodes, -17 * self.rc.YD, 0, oc.WR, 1)
        right = self.rc.trace(self.m, nodes, 17 * self.rc.YD, 0, oc.WR, 1)
        self.assertLess(left[-1][1], -17)
        self.assertGreater(right[-1][1], 17)

    def test_fixed_concepts_run_clean(self):
        for concept, formation in (('Scissors', 'Gun Doubles'), ('Smash', 'Singleback Trey'), ('Y Cross', 'Gun Wing'),
                                   ('Double Slants', 'Gun Trey'), ('Mesh', 'Gun Split Backs'), ('Y Pivot', 'Gun Trips'),
                                   ('Post Wheel', 'Singleback Doubles'), ('Stick Nod', 'Gun Trips'), ('Mesh Wheel', 'Gun Doubles Tight')):
            with self.subTest(concept=concept, formation=formation):
                bad = self.flags(concept, formation) & {'COLLIDE', 'STACK', 'OOB', 'COLLIDE_BACK', 'STACK_BACK'}
                self.assertFalse(bad, bad)


if __name__ == '__main__':
    unittest.main()

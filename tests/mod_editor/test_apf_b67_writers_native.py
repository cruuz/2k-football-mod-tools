"""Native witnesses for authoring bytes; no emulator or retail fixture files."""
from pathlib import Path
import os
import struct
import unittest
import tempfile

from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core import apf2k8_master_writer as master_writer
from mod_editor.core import apf2k8_team_tendency as tendency
from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core import apf2k8_playcall_curves_patch as curves
from mod_editor.core.apf2k8_book_identity import read_disc_roster
from tools.apf_playcall_research_probe import Machine, MASTER, BOOK, MANAGER, TEAM, STACK
from tests.mod_editor.test_apf_b67_model_native import inputs, INDEX
from tests.mod_editor.test_apf_playcall_research_native import category_candidates, heavy_addition


class WriterNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.master, cls.runtime = inputs()
        cls.books = {o: splb.read_book(INDEX, o) for o in (134, 618, 767, 1411)}
        cls.machine = Machine(cls.base, cls.runtime)

    def test_ratings_categories_and_compaction_native(self):
        m = self.machine
        for outer in (134, 767):
            original = self.books[outer]
            removed_id = original.records[0].formation_index
            result = splb.remove_formation(original.body, removed_id)
            m.install(splb.parse_book(result.book, outer))
            m.configure()
            first = m.normalize(repair_tail=False)
            second = m.normalize(repair_tail=False)
            self.assertEqual(first, second)
            # Runtime owns only the MASTER pointer; all serialized bytes must
            # already be in the same normal form, including unused trailers.
            published = bytearray(result.book)
            struct.pack_into('>I', published, 0x7E0C, MASTER)
            self.assertEqual(first, bytes(published))
            self.assertEqual(m.call(0x84A8A258, BOOK, MASTER + 0x244 + 184 * removed_id), 0)
            for row, reachable in splb.row_coverage(result.book, self.master).items():
                self.assertTrue(reachable, (outer, row))
                m.call(0x84860730, MANAGER, row, 0, stop=0x8486088C)
                pointer = m.reg(31)
                self.assertEqual(bool(pointer), bool(reachable))
                if reachable:
                    self.assertIn((pointer - MASTER - 0x44) // 16, reachable)
        added = heavy_addition(self.books[767], self.books[1411]).body
        for ratings in ((7, 7, 7), (0, 0, 0)):
            edited = splb.set_formation_ratings(added, 9, ratings)
            m.install(splb.parse_book(edited, 767))
            m.configure()
            _, candidates = category_candidates(m, 0)
            self.assertAlmostEqual(dict(candidates)[0], .1 if ratings[0] == 7 else 3., delta=1e-6)
        print('PROVED raw 7/7/7 gives heavy category weight 0.1; raw 0/0/0 gives 3.0', flush=True)

    def test_master_roles_native_builder_and_defense_row(self):
        m = Machine(self.base, self.runtime)
        m.configure()
        roles = tuple(b & 31 for b in self.master[0x49 + 8 * 16:0x54 + 8 * 16])
        slot = roles.index(9)
        edited_roles = roles[:slot] + (8,) + roles[slot + 1:]
        edited = master_writer.set_category_roles(self.master, 8, edited_roles)
        m.cpu.mem_write(MASTER + 0x49 + 8 * 16, edited[0x49 + 8 * 16:0x54 + 8 * 16])
        # Execute the whole builder, including its native MASTER role reads
        # and assignment loop. An explicit eligible-player provider replaces
        # the roster/depth selection leaf; equipment refresh is also bounded.
        # Neither boundary supplies the role written to the output objects.
        m.put(0x84F3F808, 0)
        m.put(MANAGER + 4, 0x3B0000)
        m.put(0x84F3F7DC, 0x3D0000)
        for i in range(11):
            player, output, descriptor = 0x3A0000 + i * 0x200, 0x3B0000 + i * 0x200, 0x3C0000 + i * 0x100
            m.put(output + 0x3C, output + 0x200 if i < 10 else 0)
            m.put(output + 0x44, player)
            m.put(player + 0xDC, descriptor)
            m.put(descriptor, descriptor + 0x40)
        requested_roles = []
        def eligible_player(z):
            requested_roles.append((z.reg(6), z.reg(10)))
            z.ret(0x3A0000 + z.reg(6) * 0x200)
        m.boundaries[0x847B29E8] = eligible_player
        m.boundaries[0x847C1728] = lambda z: z.ret(0)
        m.boundaries[0x847C16D0] = lambda z: z.ret(0)
        m.call(0x84860020, MANAGER, MASTER + 0x44 + 8 * 16, 0, 0x3E0000, 0, 1, 0, 0, bound=2000000)
        for boundary in (0x847B29E8, 0x847C1728, 0x847C16D0):
            del m.boundaries[boundary]
        self.assertEqual(requested_roles, list(enumerate(edited_roles)))
        self.assertEqual(tuple(m.cpu.mem_read(0x3B0034 + i * 0x200, 1)[0] for i in range(11)), edited_roles)
        self.assertEqual(tuple(m.cpu.mem_read(0x3B0036 + i * 0x200, 1)[0] for i in range(11)), tuple(range(11)))
        from tools.apf_defense_native_probe import added_book
        book = added_book(self.books[134], self.books[618].records[0], 150, 27)
        moved = master_writer.set_category_row(self.master, 27, 13)
        m.cpu.mem_write(MASTER + 0x48 + 27 * 16, moved[0x48 + 27 * 16:0x49 + 27 * 16])
        m.install(book)
        m.configure(urgency=1)
        _, native = category_candidates(m, 13)
        self.assertEqual(dict(native)[27], 1.)
        print('PROVED full 84860020 builder requests/writes Flush TE with supplied eligible players; 5-2 moved to row 13 has weight 1', flush=True)

    def test_roster_tendency_conversion_and_optional_row_reads(self):
        m = self.machine
        rost = read_disc_roster(INDEX)
        for value in (0, 50, 100):
            edited = tendency.set_team_tendency(rost, 0, value)
            edited = tendency.set_row_weights(edited, 0, tuple(range(1, 12)), tuple(range(11, 0, -1)))
            at = tendency._record(edited, 0)
            m.configure(yards=10, goal_yards=50)
            m.put(TEAM, 0x3A0000)
            m.cpu.mem_write(0x3B0000, edited[at:at + 180])
            m.call(0x8492A440, 0x3A0000, 0x3B0000)
            self.assertEqual(struct.unpack('>2H', m.cpu.mem_read(0x3A0000, 4)), (100 - value, value))
            for off, expected in zip((0x9E, 0xB4), tendency.row_weights(edited, 0)):
                self.assertEqual(struct.unpack('>11H', m.cpu.mem_read(0x3A0000 + off, 22)), expected)
            seen = []
            m.observers[0x84929B28] = lambda z: seen.append(z.fpr(1))
            m.call(0x84929A48, bound=500000)
            del m.observers[0x84929B28]
            self.assertEqual(seen, [value / 100])

    def test_removed_formation_never_reached_64_by_20_both_sides(self):
        from tools.apf_defense_native_probe import DefenseMachine, OFFENSE, TEAM as DEF_TEAM
        offense = self.books[767]
        removed = offense.records[0].formation_index
        edited = splb.parse_book(splb.remove_formation(offense.body, removed).book, 767)
        m = Machine(self.base, self.runtime)
        m.install(edited)
        for situation in range(20):
            for seed in range(64):
                m.configure(down=1 + situation % 3, yards=1 + situation % 10,
                            goal_yards=5 + (situation % 5) * 15,
                            run_share=0, fraction=(seed + .5) / 64)
                m.call(0x8486CE88, MANAGER, 0x380000, stop=0x8486D03C, bound=2000000)
                form = (m.reg(3) - MASTER - 0x244) // 184
                self.assertNotEqual(form, removed)
                self.assertIn(form, [r.formation_index for r in edited.records if r.populated])
        defense = self.books[134]
        removed = defense.records[0].formation_index
        edited = splb.parse_book(splb.remove_formation(defense.body, removed).book, 134)
        d = DefenseMachine(self.base, self.master)
        d.install(edited)
        # P2's original ordinary row-13 fixture did not need a clock or
        # opponent score. Rows 5..10 run 696E8's late-state predicate.
        for at, value in ((0x851A278C, 0x350000), (0x851A27C4, 1),
                          (0x851A27B4, 4), (OFFENSE, 0x360000),
                          (0x360008, 0x370000), (DEF_TEAM + 4, 3)):
            d.put(at, value)
        d.cpu.mem_write(0x350010, struct.pack('>f', 900.))
        for situation in range(20):
            for seed in range(64):
                d.seed(seed + 1)
                cat, form = d.cpu_formation(offense_category=situation % 10, position=(situation % 5) * 1000.)
                self.assertNotEqual(form, removed)
                self.assertIn(form, [r.formation_index for r in edited.records if r.populated])
        print('PROVED removal: 64 seeds x 20 situations on each native offensive and defensive category/formation path', flush=True)

    def test_curve_patch_native_both_images(self):
        updated_path = Path(os.environ.get('APF_RETAIL_TU_PE', str(Path(tempfile.gettempdir()) / 'astra-coverage-17votk5s/verified_tu.pe')))
        if not updated_path.is_file():
            self.skipTest('Owned TU flat image absent; set APF_RETAIL_TU_PE')
        s = model.Situation(3, 8, 50, 1, 900, 0, 3)
        for profile, image in zip(curves.PROFILES, (self.base, updated_path.read_bytes())):
            doc = curves.build_curve_patch(profile, offense_category_curve=(1., .5, .1, .01, 0.), defense_category_curve=(1., .001, 0.))
            curves.verify_curve_image(image, doc)
            self.assertEqual(curves.canonical_curve_payload(doc.as_toml().encode()), (profile, True))
            m = Machine(image, self.runtime)
            for address, word in doc.words:
                m.put(address, word)
            for outer, row, values in ((767, 10, doc.offense_category_curve), (134, 13, doc.defense_category_curve)):
                m.install(self.books[outer])
                m.configure(down=3, yards=8, goal_yards=50)
                _, native = category_candidates(m, row)
                expected = model.category_weights(self.books[outer].body, self.master, row, s, distance_curve=values)
                self.assertEqual([c for c, _ in native], [c for c, _ in expected])
                for (_, a), (_, b) in zip(native, expected):
                    self.assertAlmostEqual(a, b, delta=1e-6)
        print('PROVED patched category curve weights on pinned BASE and TU 1.1', flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)

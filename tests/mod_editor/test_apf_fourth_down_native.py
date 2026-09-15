"""Pinned BASE/TU witnesses; bounded PPC execution, no emulator or retail outputs."""
from dataclasses import asdict
import itertools
import json
import struct
import unittest

from tests.mod_editor.test_apf_playcall_research_native import NativePlaycallTests, XEX
from mod_editor.core import apf2k8_fourth_down as f
from tools import apf_fourth_down_probe as probe
from tools.apf_playcall_research_probe import MANAGER, OUTPUT, TEAM, IMAGE_BASE


class FourthDownNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        NativePlaycallTests.setUpClass()
        cls.fixture = NativePlaycallTests()

    def machine(self, updated, book=767):
        return self.fixture.machine(book, updated=updated)

    def test_pinned_reservations_and_exact_instructions(self):
        source = XEX.read_bytes()
        security = int.from_bytes(source[16:20], 'big')
        pages = int.from_bytes(source[security+0x180:security+0x184], 'big')
        for a, kind in ((f.DATA, 3), (f.CAVE, 1)):
            page = (a - IMAGE_BASE) // 65536
            self.assertLess(page, pages)
            self.assertEqual(struct.unpack_from('>I', source, security+0x184+24*page)[0], 0x10 | kind)
        for updated in (False, True):
            m = self.machine(updated)
            doc = f.PatchDocument(f.PROFILES[int(updated)])
            receipt = f.verify_image(m.image, doc)
            data=b''.join(value.to_bytes(4,'big') for _,value in doc.words[:10])
            for hi,lo,upper,base_load,tu_load,offset in f.SITES:
                load=tu_load if updated else base_load
                displacement=load&0xFFFF
                if displacement&0x8000:displacement-=0x10000
                original=((upper&0xFFFF)<<16)+displacement
                size=8 if load>>26==50 else 4
                self.assertEqual(data[offset:offset+size],m.image[original-IMAGE_BASE:original-IMAGE_BASE+size])
            self.assertEqual(data[4:8],struct.pack('>f',4572.))
            receipt['retail_literal_bytes_equal']=True
            # No aligned absolute pointer to either reservation in the entire
            # reconstructed image. This cannot rule out computed references.
            pointers = [i*4+IMAGE_BASE for i, (word,) in enumerate(struct.iter_unpack('>I', m.image))
                        if f.DATA <= word < f.DATA_LIMIT or f.CAVE <= word < f.CAVE_LIMIT]
            self.assertEqual(pointers, [])
            print('APF5_RESERVATION', json.dumps(receipt, sort_keys=True), flush=True)

    def test_neutral_preview_matches_native(self):
        parameters = (f.Thresholds(), f.Thresholds(short_yards=2, own_half_limit=75, fallback_threshold=1),
                      f.Thresholds(short_yards=3, own_half_limit=65, punt_slope=.3, fg_margin=10, fallback_threshold=.7))
        count = 0
        for updated, thresholds in itertools.product((False, True), parameters):
            m = self.machine(updated)
            probe.apply_document(m, f.PatchDocument(f.PROFILES[int(updated)], thresholds, True))
            peak = 0
            for goal, yards, cache in itertools.product((20,40,45,50,52,65,75,90), (.5,1,1.01,2,3,5), (0,.04,.5,.949,.95,.96,1)):
                probe.state(m, down=4, yards=yards, goal_yards=goal, cache=cache)
                before = m.steps
                row = m.call(m.va(0x8486BD90), MANAGER, bound=100_000)
                peak = max(peak, m.steps-before)
                got = 'Field goal' if row == 19 else 'Punt' if row == 17 else 'Go / scrimmage'
                self.assertEqual(got, f.preview(thresholds, yards=yards, goal_yards=goal, random_value=cache),
                                 (updated, asdict(thresholds), goal, yards, cache, row))
                count += 1
            print('APF5_PREVIEW', json.dumps(dict(profile=f.PROFILES[int(updated)].name,
                  thresholds=asdict(thresholds), cases=336, maximum_instructions=peak)), flush=True)
        self.assertEqual(count, 2016)

    def test_retail_values_preserve_late_game_and_urgency_decisions(self):
        count = 0
        for updated in (False, True):
            original, patched = self.machine(updated), self.machine(updated)
            probe.apply_document(patched, f.PatchDocument(f.PROFILES[int(updated)], enabled=True))
            for period, score, clock, urgency, goal in itertools.product((1,4), (-7,0,3), (60,900), (0,.5,1), (30,45,50,52,70)):
                results = []
                for m in (original, patched):
                    probe.state(m, down=4, yards=1, goal_yards=goal, period=period, score=score, clock=clock, urgency=urgency)
                    results.append(m.call(m.va(0x8486BD90), MANAGER, bound=100_000))
                self.assertEqual(*results, (updated,period,score,clock,urgency,goal))
                count += 1
        print('APF5_RETAIL_EQUIVALENCE', count, flush=True)

    def test_punt_to_complete_scrimmage_call(self):
        for updated in (False, True):
            m = self.machine(updated)
            probe.state(m, down=4, yards=1, goal_yards=52, run_share=0)
            self.assertEqual(m.call(m.va(0x8486BD90), MANAGER), 17)
            p = f.Thresholds(short_yards=2, own_half_limit=75, fallback_threshold=1)
            probe.apply_document(m, f.PatchDocument(f.PROFILES[int(updated)], p, True))
            before = m.steps
            m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2_000_000)
            pointers = [m.get(OUTPUT+i) for i in (0,4,12)]
            self.assertTrue(all(pointers))
            self.assertIn(f.CAVE, m.visited)
            self.assertEqual(bytes(m.cpu.mem_read(f.DATA,40)), b''.join(v.to_bytes(4,'big') for a,v in f.PatchDocument(f.PROFILES[int(updated)],p,True).words[:10]))
            print('APF5_COMPLETE_CALL', json.dumps(dict(profile=f.PROFILES[int(updated)].name,
                  pointers=pointers, instructions=m.steps-before)), flush=True)

    def test_draw_producer_and_presnap_boundary(self):
        for updated in (False, True):
            m = self.machine(updated, 1439)
            probe.state(m, down=4, yards=1, goal_yards=52)
            produced = probe.produce_draw(m)
            self.assertEqual(produced['flag'] & 0x200000, 0x200000)
            self.assertEqual(produced['latch'], 1)
            self.assertTrue(all(produced['selected_kick'][0]))
            # Isolated global-o contains only special plays: substitution
            # reaches the native ordinary selector but has no form/play tuple.
            self.assertEqual(produced['replacement'][1:], [0,0])
            observed = []
            for clock, expected in ((2.01,'hold'), (2.,'hold'), (1.99,'timeout_dispatch')):
                result = probe.presnap(m, clock)
                self.assertEqual(result['outcome'], expected)
                observed.append(result)
            print('APF5_DRAW_CHAIN', json.dumps(dict(profile=f.PROFILES[int(updated)].name,
                  producer=produced, presnap=observed)), flush=True)
            # Explicit hypothetical re-entry with the same state/latch. The
            # stopped timeout dispatcher has not consumed a timeout or reset
            # the match. This only proves the one-attempt latch's next choice.
            repeated=probe.produce_draw(m)
            self.assertEqual(repeated['flag'] & 0x200000,0)
            self.assertEqual(repeated['replacement'],produced['selected_kick'][0])
            print('APF5_LATCH_REENTRY', f.PROFILES[int(updated)].name,
                  repeated['replacement'], 'same-state frontier, not full timeout execution', flush=True)

    def test_edited_draw_distance_and_timeout_thresholds(self):
        for updated in (False, True):
            original, patched = self.machine(updated,1439), self.machine(updated,1439)
            p = f.Thresholds(draw_max_yards=3, draw_max_goal=65, timeout_seconds=4)
            probe.apply_document(patched, f.PatchDocument(f.PROFILES[int(updated)],p,True))
            flags=[]
            for yards,goal in ((2.5,52),(1,60),(2.5,60)):
                actual=[]
                for m in (original,patched):
                    probe.state(m, down=4,yards=yards,goal_yards=goal)
                    actual.append(probe.produce_draw(m)['flag'] & 0x200000)
                self.assertEqual(actual,[0,0x200000])
                flags.append(actual)
            for clock,expected in ((4.,'hold'), (3.99,'timeout_dispatch'), (2.,'timeout_dispatch')):
                self.assertEqual(probe.presnap(patched,clock)['outcome'],expected)
            patched.put(TEAM+0x2C,0)
            self.assertNotEqual(probe.presnap(patched,1.99)['outcome'],'timeout_dispatch')
            print('APF5_EDITED_DRAW', f.PROFILES[int(updated)].name, flags, '4.0 hold; 3.99 timeout; flag-clear no timeout', flush=True)


if __name__ == '__main__':
    # Do not discover the imported fixture's suites a second time.
    unittest.main(defaultTest='FourthDownNativeTests', verbosity=2)

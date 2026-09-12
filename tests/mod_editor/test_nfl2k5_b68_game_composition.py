"""Beta 68 scorebug-on and paired-read native composition, no played witness.

Production BuildPlan/XBE passes and bounded GAMEDATA/PLAY inputs execute.
World/animation/device completion remains the existing declared harness seam.
"""
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.nfl2k5_b661_transition import compose, plan_for, DISC
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, HAVE_UC


@unittest.skipUnless(HAVE_UC and DISC.is_file() and
                    all(importlib.util.find_spec(n) for n in ('capstone', 'PIL')),
                    'private USA disc, Unicorn, Capstone and Pillow required')
class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builds = {}
        cls.receipts = {}
        retail = retail_bytes()
        for name in ('advanced', 'simwin66', 'everything'):
            plan = replace(plan_for(name), scorebug_runtime=True)
            payload, receipt = compose(retail, plan)
            cls.builds[name] = (payload, plan)
            cls.receipts[name] = dict(xbe_sha256=hashlib.sha256(payload).hexdigest(),
                                      build=receipt)

    @classmethod
    def tearDownClass(cls):
        destination = os.environ.get('NFL2K5_B68_COMPOSITION_TRACE')
        if destination:
            Path(destination).write_bytes((json.dumps(dict(runtime_witnessed=False,
                cases=cls.receipts), indent=2) + '\n').encode())

    def test_scorebug_on_native_collection_setup_updates_draw_and_reentry(self):
        from tests.mod_editor.test_nfl2k5_scorebug_runtime import PACK, art, r
        from tests.nfl2k5_scorebug_entry_fixture import EntryCollection
        from tools.nfl2k5_scorebug_projection import read_fonts
        if not PACK.is_file():
            self.skipTest('private USA GAMEDATA/FONT archive absent')
        with PACK.open('rb') as stream:
            source = art.PackView.from_fd(stream.fileno(), 0, PACK.stat().st_size)
            pack, receipt = art.compile_runtime_collection(source)
            fonts = read_fonts(PACK)
            for name, (payload, _plan) in self.builds.items():
                with self.subTest(build=name):
                    c = EntryCollection(payload, pack, receipt)
                    try:
                        loaded = c.run()
                        c.prepare_scene(fonts); c.prepare_draw()
                        c.trace.landmarks.update((0x43F50, 0xFBC70))
                        entry = c.entry(5)
                        self.assertEqual(entry['game_ready'], [1, 1])
                        self.assertGreater(c.trace.counts[c.m.labels['setup']], 0)
                        for _ in range(40):
                            frame = c.frame()
                            self.assertEqual(c.trace.counts[c.m.labels['update']], 1)
                            self.assertFalse(c.trace.counts[0x33660])
                        draw = c.draw()
                        self.assertTrue(any(s['vertices'] for s in draw['submissions']))
                        reentry = c.entry(7)
                        self.assertEqual(reentry['game_ready'], [1, 1])
                        self.assertEqual(r.status(payload), 'applied')
                        self.receipts[name]['scorebug'] = dict(loaded=loaded, entry=entry,
                            frame=frame, draw=draw, reentry=reentry, boundaries=c.boundaries)
                    finally:
                        c.close()

    def test_scorebug_on_presentation_and_native_fresh_career_kickoff(self):
        from tests.mod_editor.test_nfl2k5_presentation_v6 import CameraV6Tests
        from tests.nfl2k5_b661_series import Machine
        for name, (payload, plan) in self.builds.items():
            with self.subTest(build=name):
                case = CameraV6Tests('test_kickoff_setup_and_actual_native_row7_lookup')
                case.patched = payload
                case.test_kickoff_setup_and_actual_native_row7_lookup()
                self.receipts[name]['presentation'] = 'native row 7 -> kickoff camera 8'
                if plan.my_career:
                    with Machine(payload, plan) as m:
                        m.series_scene(kickoff=True); m.presentation_services()
                        m.presented_frame()
                        self.assertEqual(m.counts['updates'], 8)
                        self.assertEqual(m.get(0xE602B8), 13)
                        m.call(0xB6F30, budget=3000000)
                        self.assertEqual(m.get(0xE602B8), 14)
                        self.receipts[name]['kickoff'] = dict(updates=dict(m.counts),
                            ready_state=13, approach_state=14, resources=m.resource_passes,
                            boundary='native fresh career; explicit kick command; inherited scene/device services')

    def test_paired_read_recipes_activate_and_exchange_on_composed_stack(self):
        from tests.mod_editor.test_nfl2k5_read_option_frames import FrameMachine, final_reads
        from mod_editor.core import nfl2k5_read_option_runtime as read
        resource, table, receipt = final_reads()
        for name in ('simwin66', 'everything'):
            payload, _plan = self.builds[name]
            self.assertEqual(read.status(payload), 'applied')
            # The final compiler view must match the BuildPlan-installed table.
            from mod_editor.core.nfl2k5_cave_oracle import XbeImage
            allocation = read.allocations(payload)['read_only']
            self.assertEqual(XbeImage(payload).read(allocation['va'], len(table)), table)
            rows = []
            for rpo in (False, True):
                with self.subTest(build=name, rpo=rpo):
                    m = FrameMachine(payload, resource, rpo=rpo, controller=0)
                    try:
                        row = m.frame(.05)
                        self.assertEqual((row['qb_node'], row['back_node']), (4, 3))
                        event = m.exchange()
                        self.assertEqual(m.get(m.BALL), m.RB)
                        self.assertEqual(m.get(m.state_va + 28), 1)
                        rows.append(dict(play=m.pi, first_frame=row, exchange=event))
                    finally:
                        m.uc = None
            self.receipts[name]['read_option'] = dict(pairing=receipt, rows=rows)


if __name__ == '__main__':
    unittest.main()

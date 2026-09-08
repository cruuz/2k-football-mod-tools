"""Private-evidence native tests, individually bounded to two million instructions.

List callback coverage does not claim UI paging or serialized profile persistence.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tests'):
    sys.path.insert(0, str(path))
from espn25_fixture import RETAIL, draft
from mod_editor.core import nfl2k5_espn25_scenarios as e
try:
    from espn25_native import CPU
    NATIVE_ERROR = None
except ImportError as exc:
    NATIVE_ERROR = str(exc)


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if NATIVE_ERROR:
            raise unittest.SkipTest('Unicorn unavailable: ' + NATIVE_ERROR)
        for path in (RETAIL / 'default.xbe', RETAIL / 'vc_53450030/0'):
            if not path.is_file():
                raise unittest.SkipTest('private retail evidence absent: ' + str(path))
        cls.catalog = e.Catalog.load(RETAIL)

    def test_all_fifty_native_name_year_lookups(self):
        c = CPU(self.catalog)
        for i in range(25):
            record = c.run(0x2CFD40, ecx=i)
            for side, pointer, year in (('away', 20, 28), ('home', 24, 32)):
                index = c.run(0x20BD80, ebx=c.r(record + year), args=[c.r(record + pointer)])
                self.assertEqual(index, self.catalog.binding(i, side)['index'])
        record = c.run(0x2CFD40, ecx=0)
        self.assertEqual(c.run(0x20BD80, ebx=1900, args=[c.r(record + 20)]), 0xFFFFFFFF)

    def test_one_real_moment_imports_106_players_and_numeric_setup(self):
        c = CPU(self.catalog)
        c.select(0)
        self.assertEqual([event['outer'] for event in c.events], [133, 125])
        self.assertEqual(c.read(0xBF185C, 108), c.read(c.SITU + e.RECORDS, 108))
        home, away = c.run(0x77B00), c.run(0x77B40)
        self.assertNotEqual(home, away)
        for team in (home, away):
            self.assertEqual(c.read(team + e.rr.TEAM_PLAYER_COUNT, 1), bytes([53]))
            self.assertEqual(len({c.r(team + i * 4) for i in range(53)}), 53)
        self.assertEqual((c.r(0xE60210), c.r(0xE60214)), (3, 5))
        self.assertEqual((c.r(0xE601D0), c.r(0xE60184), c.f(0xE5FFA4)), (3, 0, -13.0))
        result = c.setup()
        self.assertEqual({k: result[k] for k in ('home_score', 'away_score', 'home_timeouts', 'away_timeouts', 'quarter', 'clock_seconds', 'down')},
                         dict(home_score=14, away_score=17, home_timeouts=3, away_timeouts=3, quarter=4, clock_seconds=290.0, down=1))
        self.assertAlmostEqual(result['ball_cm'], -18 * 91.44, places=3)
        self.assertAlmostEqual(result['first_down_cm'], (-18 + 10) * 91.44, places=3)
        self.assertEqual(result['possession'], 0xE5FC20)

    def test_edited_names_number_position_rating_appearance_reach_imported_player(self):
        plan = self.catalog.prepare({'schema': e.SCHEMA, 'rosters': [{'moment': 0, 'side': 'away', 'shared_resource': True,
            'csv': 'pool,index,first,last,jersey,position,speed,skin,face\nprimary,0,A,B,12,QB,91,2,3\n'}],
            'moments': [{'moment': 0, 'setup': {'possession_side': 0, 'home_score': 7, 'away_score': 10, 'clock_seconds': 75.0}}]})
        outputs, _ = e.resolve_plan(self.catalog, plan)
        catalog = e.Catalog({**self.catalog.resources, **{i: (self.catalog.resources[i][0], raw) for i, raw in outputs.items()}})
        c = CPU(catalog); c.select(0)
        team = c.run(0x77B40)
        player = c.r(team)
        self.assertEqual((c.text(c.r(player + 16)), c.text(c.r(player + 20))), ('A', 'B'))
        record = e.rr.PlayerRecord.decode(c.read(player, 84))
        self.assertEqual((record.values['jersey'], record.values['position'], record.values['speed'], record.skin, record.values['face']), (12, 0, 91, 2, 3))
        result = c.setup()
        self.assertEqual((result['home_score'], result['away_score'], result['clock_seconds'], result['possession']), (7, 10, 75.0, 0xE5FC60))

    def test_thirty_row_walker_accessor_caption_callbacks_and_inverse(self):
        c = CPU(self.catalog)
        table = self.catalog.research_table(draft(self.catalog))
        c.load_situ(table)
        self.assertEqual(c.run(0x2CFD20), 30)
        self.assertEqual(c.r(0x529660), 0x20C340)
        self.assertEqual(c.read(0x20C340, 6), bytes.fromhex('b819000000c3'))
        self.assertEqual(c.run(0x20C340), 25)
        # Research-only complete pinned span, in this CPU's memory. No writer ships.
        c.write(0x20C340, bytes.fromhex('b81e000000c3'))
        c.uc.ctl_remove_cache(0x20C000, 0x20D000)
        self.assertEqual(c.run(0x20C340), 30)
        body = table[32:]
        for i in range(c.run(0x20C340)):
            record = c.run(0x2CFD40, ecx=i)
            self.assertEqual(record, c.SITU + e.RECORDS + i * e.STRIDE)
            for offset in e.POINTERS:
                self.assertEqual(c.r(record + offset), c.SITU + e.rel(body, e.RECORDS + i * e.STRIDE + offset))
            caption = c.text(c.run(0x20C350, ecx=i))
            self.assertIn(c.text(c.r(record)), caption)
            self.assertIn(c.text(c.r(record + 12)), caption)
        # Accessor has no bound check; installation needs the list to enforce it.
        self.assertEqual(c.run(0x2CFD40, ecx=30), c.SITU + e.RECORDS + 30 * e.STRIDE)
        for i in range(30):
            c.run(0x2CFCA0, ecx=c.SITU + e.RECORDS + i * e.STRIDE)
        restored = bytearray(c.read(c.SITU, len(body)))
        restored[20:24] = body[20:24]  # undo framework preamble relocation
        self.assertEqual(bytes(restored), body)

    def test_registration_callbacks_have_no_local_count_limit(self):
        c = CPU(self.catalog)
        events = []
        def register(pop):
            events.append((c.reg('edx'), [c.r(c.reg('esp') + 4 + i * 4) for i in range(pop // 4)]))
            c.ret(1, pop)
        c.stubs[0x436A0] = lambda: register(4)
        c.stubs[0x43720] = lambda: register(8)
        self.assertEqual(c.run(0x166000), 1)
        self.assertEqual(events, [(0x55544953, [0x165FC0]), (0x55544953, [0x165F60, 0x165F90])])

    def test_completion_full_dword_get_set_win_loss_and_32_alias(self):
        c = CPU(self.catalog)
        profile = 0x2340000
        c.stubs[0x77560] = lambda: c.ret(profile)
        c.w(0xE5FF80, 8); c.w(0xE6014C, 0)
        c.w(0xBF1880, 1); c.w(0xBF1858, 29); c.w(0xBF18CC, 1)
        c.run(0x20C670, ecx=21, edx=17)  # human home wins
        self.assertEqual(c.r(0xBF18CC), (1 << 29) | 1)
        self.assertEqual(c.run(0x196DC0, ecx=profile), (1 << 29) | 1)
        self.assertEqual(c.run(0x20C390, ecx=29), 1)
        self.assertEqual(c.run(0x20C390, ecx=28), 0)
        self.assertEqual(c.run(0x20C390, ecx=32), 1)  # unsafe alias to bit zero
        c.w(0xBF1858, 28)
        c.run(0x20C670, ecx=17, edx=21)
        self.assertEqual(c.r(0xBF18CC), (1 << 29) | 1)
        c.w(0xBF1880, 0)
        c.run(0x20C670, ecx=17, edx=21)  # human away wins
        self.assertEqual(c.r(0xBF18CC), (1 << 29) | (1 << 28) | 1)
        c.run(0x196DD0, ecx=profile, edx=0xFFFFFFFF)
        self.assertEqual(c.run(0x196DC0, ecx=profile), 0xFFFFFFFF)

    def test_reward_loop_needs_count_patch_in_concert(self):
        c = CPU(self.catalog)
        rewards = []
        c.stubs[0x110E60] = lambda: (rewards.append((c.reg('ecx'), c.reg('edx'))), c.ret(0))
        c.w(0xBF18CC, (1 << 25) - 1)
        c.run(0x20C2BC)
        self.assertEqual(rewards, [(14, 0)])
        self.assertEqual(c.read(0x20C2CA, 5), bytes.fromhex('83f9197cf1'))
        c.write(0x20C2CA, bytes.fromhex('83f91e7cf1'))
        c.uc.ctl_remove_cache(0x20C000, 0x20D000)
        rewards.clear(); c.run(0x20C2BC)
        self.assertEqual(rewards, [])
        c.w(0xBF18CC, (1 << 30) - 1); c.run(0x20C2BC)
        self.assertEqual(rewards, [(14, 0)])


if __name__ == '__main__':
    unittest.main()

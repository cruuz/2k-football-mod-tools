"""Creation tier codec and native integer OVR; no played career claim."""
from pathlib import Path
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career as career
from mod_editor.core import nfl2k5_my_career_prospects as subject
from mod_editor.core import nfl2k5_my_career_save as save
from mod_editor.core import nfl2k5_roster_records as roster
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, draft_save


class ProspectTests(unittest.TestCase):
    def test_prepared_save_reopens_tier_overall_identity_and_goal(self):
        for pos in (0, 3, 4, 11, 12, 16):
            for tier in range(1, 5):
                with self.subTest(pos=pos, tier=tier):
                    source = draft_save(pos)
                    output, setup, receipt = career.prepare(source, first='Tier', last='Player',
                                                            position=pos, prospect_tier=tier)
                    state = bytes.fromhex(setup['state'])
                    career.validate_state(state, output)
                    doc = roster.RosterDocument(output, base=roster.find_block_base(output))
                    chosen = doc.by_offset[receipt['record_offset']]
                    self.assertEqual(subject.native_overall(chosen.record), subject.TIERS[tier][1])
                    self.assertEqual(chosen.record.get('position'), pos)
                    self.assertEqual(setup['prospect']['career_goal'], subject.TIERS[tier][2])
                    self.assertEqual(struct.unpack_from('<I', state, 212)[0], tier)
                    self.assertFalse(receipt['starter_lock'])
                    self.assertEqual((chosen.record.encode()[41] >> 2) & 7,
                                     subject.starting_rank(tier, pos))
                    # The generated prospect has entered the native draft (phase 2).
                    active = bytearray(state)
                    struct.pack_into('<I', active, 24, 2)
                    active[190] = 255
                    block = save.from_runtime(active)
                    self.assertEqual(block[83], tier)
                    self.assertEqual(save.from_runtime(save.to_runtime(block)), block)
                    self.assertEqual(len(output), len(source))

    def test_original_and_invalid_tiers_and_distinct_prototypes(self):
        source = draft_save()
        options = dict(first='Same', last='Player', token='12345678-1234-5678-1234-567812345678')
        self.assertEqual(career.prepare(source, **options), career.prepare(source, prospect_tier=0, **options))
        for value in (-1, 5, True, 'Unknown'):
            with self.assertRaises(ValueError): subject.tier_id(value)
        self.assertEqual(subject.prototypes(0), (('Scrambling QB', 1),
            ('Gunslinger QB', 3), ('Balanced QB', 2), ('Pocket QB', 0)))
        self.assertEqual(subject.prototypes(16, scheme='one_pool'),
                         (('Power EDGE', 0), ('Speed EDGE', 1), ('Balanced EDGE', 2)))
        for count in (1, 2, 5, 8, 10):
            self.assertEqual(subject.starting_rank(4, 3, count), min(count-1, 7))


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA retail XBE and Unicorn required')
class NativeOverallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes, Machine
        cls.machine = Machine(retail_bytes(), trace_writes=False)

    def check(self, record):
        m = self.machine
        m.uc.mem_write(m.ARENA, record.encode())
        self.assertEqual(subject.native_overall(record),
                         m.call(0x246D90, ecx=m.ARENA, edx=0, budget=100000))

    def test_all_templates_tiers_and_body_sizes_match_native_unboosted_overall(self):
        for template in roster.create_player_templates():
            for height, weight in ((74, 220), (67, 170), (80, 350)):
                record = roster.PlayerRecord.decode(bytes(84))
                roster.apply_template(record, template)
                record.set('position', template.position_code)
                record.set('height', height); record.set('weight', weight)
                for tier in range(5):
                    with self.subTest(template=template.index, height=height, weight=weight, tier=tier):
                        chosen = record.copy()
                        subject.apply_tier(chosen, tier)
                        self.check(chosen)
                        if tier:
                            self.assertEqual(subject.native_overall(chosen), subject.TIERS[tier][1])
                        for field in roster.STYLE_RATINGS:
                            self.assertEqual(chosen.get(field), record.get(field))
                        self.assertEqual(chosen.encode()[:54], record.encode()[:54])
                        self.assertEqual(chosen.encode()[82:], record.encode()[82:])

    def test_deterministic_varied_ratings_match_native(self):
        rng = random.Random(69)
        for _ in range(300):
            record = roster.PlayerRecord.decode(bytes(84))
            record.set('position', rng.randrange(17))
            record.set('height', rng.randrange(67, 81)); record.set('weight', rng.randrange(170, 351))
            for field in roster.RATING_BYTE_ORDER:
                record.set(field, rng.randrange(101))
            self.check(record)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA retail XBE/ROST and Unicorn required')
class NativeCreationTests(unittest.TestCase):
    def test_entry_tiers_native_cap_depth_and_cold_saved_goal(self):
        from mod_editor.core import nfl2k5_my_career_mode as mode
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        from tests.nfl2k5_my_career_mode_fixture import Machine
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster, FrontendTests
        payload = mode.apply(retail_bytes())[0]
        source = retail_roster()
        for position in (0, 4):
            for tier in range(1, 5):
                with self.subTest(position=position, tier=tier), Machine(payload) as m:
                    m.frontend(source)
                    m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
                    m.select(1)
                    for _ in range(tier): m.select(4)
                    self.assertEqual(m.get(m.state + 2744), tier)
                    m.select(1)
                    p = m.get(0xCB8B14)
                    m.uc.mem_write(p + 53, bytes((position,)))
                    m.call(0x343460)
                    FrontendTests.complete_cap(self, m)
                    self.assertEqual(m.call(0x246D90, ecx=p, edx=0), subject.TIERS[tier][1])
                    m.select(0); m.select(2)
                    m.select(1, budget=500000000)
                    self.assertEqual(m.top(), m.labels['apartment'])
                    rank = m.call('mode_prospect_rank')
                    self.assertEqual((m.uc.mem_read(p + 41, 1)[0] >> 2) & 7, rank)
                    # Routine launches retain the starting place. Start MyPlayer
                    # remains an explicit later promotion in Apartment Settings.
                    before = bytes(m.uc.mem_read(p, 84))
                    m.call('start_player')
                    self.assertEqual(m.uc.mem_read(p, 84), before)
                    output = m.native_save(budget=500000000)
                    self.assertEqual(save.prospect(output)['career_goal'], subject.TIERS[tier][2])
                with Machine(payload) as cold:
                    cold.frontend(source); cold.native_load(output)
                    self.assertEqual(cold.get(cold.state + 2744), tier)
                    self.assertEqual(save.read(cold.native_save(budget=500000000))[83], tier)


if __name__ == '__main__':
    unittest.main()

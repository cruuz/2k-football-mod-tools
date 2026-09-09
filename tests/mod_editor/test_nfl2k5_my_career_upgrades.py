"""M3 native purchase transactions and played-XP cold persistence.

EXPERIMENTAL / UNWITNESSED. Engine end/event inputs and device completion
are supplied by the existing played fixture; no award or purchase is stubbed.
"""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_my_career_progression as policy
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_my_career_played_fixture import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


class PolicyTests(unittest.TestCase):
    def test_only_ordinary_attributes_and_explicit_balance_boundaries(self):
        self.assertEqual(len(policy.FIELDS), 25)
        self.assertFalse({0x4B, 0x4D, 0x4F} & {f for f, _, _ in policy.FIELDS})
        self.assertEqual([policy.cost(v) for v in (-1, 0, 69, 70, 79, 80, 89, 90, 94, 95, 98, 99)],
                         [0, 10, 10, 15, 15, 25, 25, 40, 40, 60, 60, 0])
        arm = next(i for i, (_, key, _) in enumerate(policy.FIELDS) if key == 'pass_arm_strength')
        self.assertEqual(policy.CAPS[0][arm], 99)
        self.assertTrue(all(policy.CAPS[p][arm] == 75 for p in range(1, 17)))


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST and Unicorn required')
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16*1024**2:
            raise unittest.SkipTest('retail XBE exceeds 16 MiB')
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('USA retail XBE pin differs')
        cls.payload, cls.roster = mode.apply(retail)[0], retail_roster()

    def test_every_position_cap_and_style_refusal_execute_native_purchase(self):
        for pos in range(17):
            with self.subTest(position=pos), Machine(self.payload) as m:
                p = m.create(self.roster, position=pos, preseason=False)
                for index, (field, _, _) in enumerate(policy.FIELDS):
                    cap = policy.CAPS[pos][index]
                    # Declared quote inputs, independently checked at the cap.
                    m.uc.mem_write(p + field, bytes((cap - 1,)))
                    m.put(m.state + 64, 100)
                    before = bytes(m.uc.mem_read(m.root, 0x91000))
                    price = m.call('m3_upgrade_quote', ecx=m.manager, edx=field)
                    self.assertEqual(price, policy.cost(cap - 1))
                    self.assertEqual(m.call('m3_upgrade_commit', ecx=m.manager, edx=1), 1)
                    after = bytes(m.uc.mem_read(m.root, len(before)))
                    self.assertEqual([i for i, (a, b) in enumerate(zip(before, after)) if a != b],
                                     [p + field - m.root])
                    self.assertEqual(after[p + field - m.root], cap)
                    self.assertEqual(m.get(m.state + 64), 100 - price)
                    self.assertEqual(m.call('m3_upgrade_commit', ecx=m.manager, edx=1), 0)
                    self.assertEqual(m.call('m3_upgrade_quote', ecx=m.manager, edx=field), 0)
                for field in (0, 8, 24, 53, 0x4B, 0x4D, 0x4F, 84, 0xFFFFFFFF):
                    self.assertEqual(m.call('m3_upgrade_quote', ecx=m.manager, edx=field), 0)

    def test_cancel_stale_balance_rating_token_and_manager_consume_quote(self):
        with Machine(self.payload) as m:
            p = m.create(self.roster, preseason=False)
            field = policy.FIELDS[0][0]
            for fault in ('cancel', 'balance', 'rating', 'token', 'manager'):
                with self.subTest(fault=fault):
                    m.uc.mem_write(p + field, b'\x45')
                    m.put(m.state + 64, 25)
                    self.assertEqual(m.call('m3_upgrade_quote', ecx=m.manager, edx=field), 10)
                    if fault == 'balance':
                        m.put(m.state + 64, 24)
                    if fault == 'rating':
                        m.uc.mem_write(p + field, b'\x44')
                    if fault == 'token':
                        m.put(m.state + 40, m.get(m.state + 40) ^ 2)
                    before = bytes(m.uc.mem_read(p, 84)), m.get(m.state + 64)
                    answer = m.call('m3_upgrade_commit', ecx=m.manager + int(fault == 'manager'),
                                    edx=2 if fault == 'cancel' else 1)
                    self.assertEqual(answer, 0)
                    self.assertEqual((bytes(m.uc.mem_read(p, 84)), m.get(m.state + 64)), before)
                    self.assertEqual(m.call('m3_upgrade_commit', ecx=m.manager, edx=1), 0)

    def test_played_award_native_a_confirmation_manual_save_and_cold_reload(self):
        with Machine(self.payload) as m:
            m.create(self.roster, preseason=False)
            m.child_services()
            m.launch()
            m.appearance()
            m.passing_event()
            m.finish()
            self.assertEqual(m.get(m.state + 64), 25)
            p = m.call('primary')
            index, field, price = next((i, f, policy.cost(m.uc.mem_read(p+f, 1)[0]))
                for i, (f, _, _) in enumerate(policy.FIELDS)
                if m.uc.mem_read(p+f, 1)[0] < policy.CAPS[0][i]
                and 0 < policy.cost(m.uc.mem_read(p+f, 1)[0]) <= 25)
            old = bytes(m.uc.mem_read(p, 84))
            token = bytes(m.uc.mem_read(m.state + 40, 16))
            m.select(6)
            self.assertEqual(m.top(), m.labels['m3_upgrade_menu'])
            for _ in range(index):
                m.select(1)
            m.dialog_answer = 1  # native Yes/No returns false for row 1
            m.select(2)
            self.assertEqual(bytes(m.uc.mem_read(p, 84)), old)
            self.assertEqual(m.get(m.state + 64), 25)
            m.dialog_answer = 2  # native wrapper returns true for Yes
            m.select(2)
            changed = bytes(m.uc.mem_read(p, 84))
            self.assertEqual([i for i, (a, b) in enumerate(zip(old, changed)) if a != b], [field])
            self.assertEqual(changed[field], old[field] + 1)
            self.assertEqual(m.get(m.state + 64), 25 - price)
            m.select(3)
            self.assertEqual(m.top(), m.labels['apartment'])
            saved = m.native_save(budget=500000000)
        with Machine(self.payload) as cold:
            cold.cold(self.roster, saved)
            p = cold.call('primary')
            self.assertEqual(bytes(cold.uc.mem_read(cold.state + 40, 16)), token)
            self.assertEqual(cold.uc.mem_read(p+field, 1)[0], old[field] + 1)
            self.assertEqual(cold.get(cold.state + 64), 25 - price)
            cold.call('settle')
            self.assertEqual(cold.get(cold.state + 64), 25 - price)
            self.assertEqual(cold.top(), cold.labels['apartment'])


if __name__ == '__main__':
    unittest.main()

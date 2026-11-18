"""Run the ordinary and optional-carousel owner warning decisions on the real franchise code."""
import struct
import unittest

from mod_editor.core import nfl2k5_coach_carousel as carousel
from mod_editor.core import nfl2k5_coach_career_fix as records
from mod_editor.core import nfl2k5_rdata_sites as sites
from tests.mod_editor.test_nfl2k5_cave_oracle import synthetic
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, Machine, retail_bytes


@unittest.skipUnless(HAVE_UC, "Unicorn is required for the bounded owner decision")
class GeneratedWarningTests(unittest.TestCase):
    def test_saved_setting_controls_both_dismissal_notices(self):
        # Enter the shipped 59-byte block after the prior-warning check. The
        # full-image tests below also cover the native caller, PRNG and carousel.
        m = Machine(synthetic(), trace_writes=False)
        m.uc.mem_write(records.WARNING_ACTION_VA, records.PATCHED_WARNING_ACTION)
        wrapper = m.STOP + 0x100
        m.uc.mem_write(wrapper, b'\x53\x55\x56\x57\xe9' + struct.pack('<i', records.WARNING_ACTION_VA - wrapper - 9))
        notices = []
        draws = []
        def choose_notice():
            draws.append(draw)
            m.ret(draw)
        def post_notice():
            notices.append((m.reg('ECX'), m.reg('EDX')))
            m.ret()
        def keep_job():
            m.reg('ESP', m.reg('ESP') + 16)
            m.ret(1)
        m.leaf(0x48BC0, choose_notice, reason='supply each native dismissal RNG outcome')
        m.leaf(0xC4CA0, lambda: m.ret(15), reason='identify the fixture team')
        m.leaf(0x27E3C0, post_notice, reason='record the notice and recipient')
        m.leaf(0x2BA6B6, keep_job, reason='observe the branch to the undismissed continuation')
        for setting in (0, 1, 2):
            for draw in (0, 1):
                with self.subTest(setting=setting, draw=draw):
                    notices.clear()
                    draws.clear()
                    m.put(0xE60144, setting)
                    self.assertEqual(m.call(wrapper, ebx=1), int(setting == 0))
                    self.assertEqual(notices, [(15, 0x29 + draw)] if setting else [])
                    self.assertEqual(draws, [draw] if setting else [])


class OwnerFiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.previous, _ = sites.apply(cls.retail, records.SITES_V1 + records.SITES_V2, 'released coach records')
        cls.fixed, cls.receipt = records.apply(cls.previous)

    def test_previous_release_upgrades_and_rolls_back_exactly(self):
        self.assertEqual(records.status(self.previous), 'previous')
        self.assertEqual(self.receipt['upgraded_from'], 2)
        self.assertEqual(records.apply(self.retail)[0], self.fixed)
        self.assertEqual(records.restore_previous(self.fixed)[0], self.previous)
        self.assertEqual(records.restore_previous(self.previous)[0], self.previous)
        foreign = bytearray(self.previous)
        foreign[sites.offset_of(self.previous, records.WARNING_ACTION_VA) + 13] ^= 1
        self.assertEqual(records.status(bytes(foreign)), 'foreign')
        for operation in (records.apply, records.restore_previous):
            with self.assertRaises(sites.RdataSiteError):
                operation(bytes(foreign))

    @staticmethod
    def decision(payload, setting, warned, seed):
        m = Machine(payload, trace_writes=False)
        state = m.ARENA + 0x100
        wrapper = m.STOP + 0x100
        m.seed(seed)
        m.put(state, 0x01286009 | (4 if warned else 0))
        m.put(0xE60144, setting)
        # The native warning block normally starts with the function's four saved registers on the stack.
        m.uc.mem_write(wrapper, b'\x53\x55\x56\x57\xe9' + struct.pack('<i', 0x2BA675 - wrapper - 9))
        messages = []
        m.leaf(0xC4CA0, lambda: m.ret(15), reason='team-number lookup for Giants fixture')
        def post_notice():
            messages.append((m.reg('ECX'), m.reg('EDX')))
            m.ret()
        m.leaf(0x27E3C0, post_notice, reason='capture native notice recipient and identifier')
        m.leaf(0x2BA5D0, lambda: m.ret(pop=4), reason='owner goal selection after issuing the nameable notice')
        def continue_owner():
            m.reg('ESP', m.reg('ESP') + 16)
            m.ret(1)
        m.leaf(0x2BA6E6, continue_owner, reason='end observation after the warning counter and notice')
        result = m.call(wrapper, ebx=1, esi=state, edi=m.ARENA + 0x300)
        return result, messages, m.get(state), bytes(m.uc.mem_read(0xB12680, 448))

    def test_off_protects_a_warned_owner_and_both_dismissal_notices_still_work(self):
        notices = set()
        for setting in (0, 1, 2):
            for warned in (False, True):
                for seed in (1, 2, 3, 4):
                    with self.subTest(setting=setting, warned=warned, seed=seed):
                        old = self.decision(self.previous, setting, warned, seed)
                        new = self.decision(self.fixed, setting, warned, seed)
                        if setting == 0 and warned:
                            self.assertEqual(old[0], 0)
                            self.assertEqual(new[:2], (1, [(15, 0x26)]))
                        else:
                            self.assertEqual(old, new)
                        if setting and warned:
                            notices.add(new[1][0][1])
        self.assertEqual(notices, {0x29, 0x2A})

    def test_carousel_keeps_its_team_modes_in_either_install_order(self):
        previous_carousel, _ = carousel.apply(self.previous)
        upgraded_carousel, _ = records.apply(previous_carousel)
        new_carousel, _ = carousel.apply(self.fixed)
        self.assertEqual(upgraded_carousel, new_carousel)
        self.assertEqual(carousel.status(new_carousel), 'applied')
        self.assertEqual(records.restore_previous(new_carousel)[0], previous_carousel)
        for setting in (0, 1, 2):
            for warned in (False, True):
                with self.subTest(setting=setting, warned=warned):
                    expected = self.decision(previous_carousel, setting, warned, 1)
                    outcome = self.decision(new_carousel, setting, warned, 1)
                    self.assertEqual(outcome, expected)
                    self.assertEqual(outcome[0], int(setting != 2 or not warned))


if __name__ == "__main__":
    unittest.main()

"""Native signing failure and migrated reserve ownership, without a game boot.

The frontend supplies the existing named device/menu services. Corruption
cases change declared data inputs; the append, cut, CAP, resolve and reserve
routines execute their installed instructions. Private retail stays in RAM.
"""
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_roster_arena as arena
from mod_editor.core import nfl2k5_roster_arena_growth as growth
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, HAVE_UC, XBE
from tests.nfl2k5_my_career_played_fixture import Machine as PlayedMachine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


class Machine(PlayedMachine):
    def __init__(self, payload, grown=None):
        super().__init__(payload)
        self.grown = grown

    def frontend(self, roster):
        super().frontend(roster)
        if self.grown is not None:
            self.uc.mem_write(self.root, self.grown[64:])
            self.put(0xB72808, arena.ARENA_SIZE)
            self.put(0xB7280C, arena.ARENA_SIZE)
            self.call(0xC0500, ecx=self.root, budget=1000000)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'Unicorn and private USA XBE/ROST required')
class SigningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = retail_bytes()
        cls.roster = retail_roster()
        cls.grown = arena.migrate(cls.roster, created_teams_extra=2)[0]
        cls.native = mode.apply(retail)[0]
        cls.squad = mode.apply(ps.apply(retail)[0])[0]
        allocated = mode.space.apply(retail, mode.REQUESTS + growth.REQUESTS, scaleout=True)[0]
        cls.extended = mode.apply(growth.apply(allocated, created_teams_extra=2)[0])[0]

    def enter(self, m):
        m.frontend(self.roster)
        m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
        m.select(1)

    def stage_player(self, m):
        self.enter(m)
        m.select(1)
        player = m.get(0xCB8B14)
        self.assertNotEqual(player, 0)
        for _ in range(4):
            m.frame(0x10)
        m.select(0)
        m.select(2)
        self.assertEqual(m.get(m.state + 2680), 2)
        return player, m.get(m.root + 0x1C) + 1000

    def test_limit_tracks_native_preseason_regular_and_invalid_metadata(self):
        for payload, grown in ((self.native, None), (self.squad, None), (self.extended, self.grown)):
            with self.subTest(grown=grown is not None, native=payload is self.native), Machine(payload, grown) as m:
                self.enter(m)
                team = m.get(m.root + 0x1C)
                for stage, expected in ((7, 65), (8, 65 if payload is self.native else 53)):
                    m.put(0xE576A0, 2)
                    m.put(0xE576A4, stage)
                    # Static GCC helper takes its one argument in EAX.
                    self.assertEqual(m.call('m3_sign_limit', eax=team), expected)
                m.uc.mem_write(team + 0x19B, b'\x03')
                self.assertEqual(m.call('m3_sign_limit', eax=team), 0)

    def test_append_refusal_retains_free_agent_record_and_staged_ownership(self):
        with Machine(self.squad) as m:
            player, team = self.stage_player(m)
            seen = {}

            def before_contract():
                if m.reg('ECX') != player:
                    return
                # Corruption arrives after the last capacity check. The real
                # PS append must reject this metadata; no return is mocked.
                m.uc.mem_write(team + 0x19B, b'\x03')
                seen['roster'] = bytes(m.uc.mem_read(m.root, 0x91000))
                seen['state'] = bytes(m.uc.mem_read(m.state, 200))

            def append_entry():
                if m.reg('ECX') == team and m.reg('EDX') == player:
                    seen['append'] = True

            m.stub(0x3228A0, before_contract)
            m.stub(0xC3EE0, append_entry)
            m.select(1, budget=500000000)
            self.assertTrue(seen['append'])
            self.assertEqual(bytes(m.uc.mem_read(m.root, 0x91000)), seen['roster'])
            self.assertEqual(bytes(m.uc.mem_read(m.state, 200)), seen['state'])
            self.assertEqual(m.get(m.state), 0)
            self.assertEqual(m.get(m.state + 2676), player)
            self.assertEqual(m.get(m.state + 2680), 2)
            self.assertEqual(m.top(), m.labels['team_menu'])
            self.assertIn(('notice', 'Roster is full.'), m.events)
            fa = m.get(m.root + 0x3C)
            self.assertEqual(sum(m.get(fa + i*4) == player for i in range(m.get(m.root + 0x38))), 1)
            self.assertNotIn(player, [m.get(team + i*4) for i in range(65)])

    def test_version_two_requires_owner_extent_and_valid_crc_before_cap(self):
        for reason in ('native_owner', 'ordinary_squad', 'extent', 'crc', 'version'):
            payload = self.native if reason == 'native_owner' else self.squad if reason == 'ordinary_squad' else self.extended
            with self.subTest(reason=reason), Machine(payload, self.grown) as m:
                self.enter(m)
                if reason == 'extent':
                    m.put(0xB72808, 0x91000)
                elif reason == 'crc':
                    m.put(m.root + arena.BLOCK_OFFSET + 20, 0)
                elif reason == 'version':
                    m.uc.mem_write(m.get(m.root + 0x1C) + 0x19B, b'\x03')
                before = bytes(m.uc.mem_read(m.root, arena.ARENA_SIZE))
                m.select(1)
                self.assertEqual(m.top(), m.labels['entry_menu'])
                self.assertEqual(m.get(m.state + 2676), 0)
                self.assertEqual(m.get(0xCB8B14), 0)
                self.assertEqual(bytes(m.uc.mem_read(m.root, arena.ARENA_SIZE)), before)
                self.assertEqual(m.events, [('notice', 'Roster is full.')])

    def test_cap_rejects_a_free_slot_aliased_in_grown_overflow(self):
        with Machine(self.extended, self.grown) as m:
            self.enter(m)
            player = m.call(0xBFF50)
            team = m.get(m.root + 0x1C)
            # Input corruption: otherwise coherent 53+13 metadata and CRC,
            # with the available CAP slot also owned at overflow slot 65.
            active = m.uc.mem_read(team + 0x11C, 1)[0]
            self.assertEqual(active, 53)
            for i in range(53, 65):
                m.put(team + i*4, m.get(team + (i-53)*4))
            m.uc.mem_write(team + ps.COUNT, b'\x0d')
            block = bytearray(m.uc.mem_read(m.root + arena.BLOCK_OFFSET, 352))
            struct.pack_into('<H', block, 32, (player - m.get(m.root + 4)) // 84)
            struct.pack_into('<I', block, 20, 0)
            struct.pack_into('<I', block, 20, zlib.crc32(block) & 0xFFFFFFFF)
            m.uc.mem_write(m.root + arena.BLOCK_OFFSET, bytes(block))
            self.assertGreater(m.call(0x3EE10C, ecx=team), 0)
            before = bytes(m.uc.mem_read(m.root, arena.ARENA_SIZE))
            m.select(1)
            self.assertEqual(m.top(), m.labels['entry_menu'])
            self.assertEqual(m.get(m.state + 2676), 0)
            self.assertEqual(bytes(m.uc.mem_read(m.root, arena.ARENA_SIZE)), before)

    def test_created_player_resolves_from_overflow_and_native_promotion(self):
        with Machine(self.extended, self.grown) as m:
            player = m.create(self.roster, preseason=False)
            team = m.get(m.state + 2588)
            token = bytes(m.uc.mem_read(m.state + 40, 16))
            # Native demotion order puts MyPlayer last in sixteen reserves.
            for _ in range(15):
                self.assertEqual(m.call(ps.SYMBOLS['ps_demote'], ecx=team, edx=m.get(team), budget=3000000), 1)
            self.assertEqual(m.call(ps.SYMBOLS['ps_demote'], ecx=team, edx=player, budget=3000000), 1)
            for _ in range(16):
                p = m.get(m.get(m.root + 0x3C))
                self.assertEqual(m.call(0xC3EE0, ecx=team, edx=p, budget=3000000), 1)
                m.call(0x2425C0, ecx=m.root + 0x38, edx=p)
            self.assertEqual(m.uc.mem_read(team + 0x11C, 1)[0], 53)
            self.assertEqual(m.uc.mem_read(team + ps.COUNT, 1)[0], 16)
            overflow = m.root + arena.BLOCK_OFFSET + 32 + 2*10
            player_id = (player - m.get(m.root + 4)) // 84
            self.assertEqual(struct.unpack('<H', m.uc.mem_read(overflow + 3*2, 2))[0], player_id)
            self.assertNotIn(player, [m.get(team + 4*i) for i in range(65)])
            m.call('resolve_team', budget=3000000)
            self.assertEqual((m.get(m.state + 24), m.get(m.state + 56), m.get(m.state + 80)), (5, 2, 1))
            self.assertEqual(m.call('primary'), player)
            # Removing one active player opens the regular-season slot.
            self.assertEqual(m.call(0xC3EB0, ecx=team, edx=m.get(team), budget=3000000), 1)
            self.assertEqual(m.call(ps.SYMBOLS['ps_promote'], ecx=team, edx=player, budget=3000000), 1)
            m.call('resolve_team', budget=3000000)
            self.assertEqual((m.get(m.state + 24), m.get(m.state + 56), m.get(m.state + 80)), (3, 2, 0))
            self.assertEqual(bytes(m.uc.mem_read(m.state + 40, 16)), token)
            self.assertLess(m.call('mode_next_fixture'), 374)
            m.child_services()
            bound = m.launch()
            self.assertNotEqual(bound, 0)
            self.assertEqual(m.get(bound + 16), m.get(player + 16))
            self.assertEqual(m.get(bound + 20), m.get(player + 20))

    def test_staged_match_identity_rejects_aliases_and_malformed_arrays(self):
        with Machine(self.extended, self.grown) as m:
            player = m.create(self.roster, preseason=False)
            m.child_services()
            copies, before_binding = [], []
            m.stub(0xC3C60, lambda: copies.append(m.reg('ECX')))
            m.stub('mode_match_copy', lambda: before_binding.append(m.get(m.state + 2564)))
            bound = m.launch()
            self.assertEqual(copies, [])  # grown staging bypasses the old copy hook
            self.assertEqual(before_binding, [0])
            self.assertNotEqual(bound, 0)
            team = 0xB30864 if bound < 0xB321A0 else 0xB30A58
            other = m.get(team)
            if other == bound:
                other = m.get(team + 4)
            original = bytes(m.uc.mem_read(other, 84))
            # Two copied creation identities must detach, even on one side.
            m.uc.mem_write(other, bytes(m.uc.mem_read(bound, 84)))
            m.call('mode_match_copy')
            self.assertEqual(m.get(m.state + 2564), 0)
            m.uc.mem_write(other, original)
            m.call('mode_match_copy')
            self.assertEqual(m.get(m.state + 2564), bound)
            first = m.get(team)
            m.put(team, player)  # source pointer is not a staged match slot
            m.call('mode_match_copy')
            self.assertEqual(m.get(m.state + 2564), 0)
            m.put(team, first)
            m.call('mode_match_copy')
            self.assertEqual(m.get(m.state + 2564), bound)
            count = bytes(m.uc.mem_read(team + 0x11C, 1))
            m.uc.mem_write(team + 0x11C, b'\x42')
            m.call('mode_match_copy')
            self.assertEqual(m.get(m.state + 2564), 0)
            m.uc.mem_write(team + 0x11C, count)


if __name__ == '__main__':
    unittest.main()

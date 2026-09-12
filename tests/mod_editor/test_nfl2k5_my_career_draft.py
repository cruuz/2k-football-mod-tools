"""M3 native CAP placement, real AI picks/contracts and cold save routing.

The pinned f0 input is given year-1, untouched-Combine stage scalars.
Most cases enable Preseason; the undrafted case processes all native cuts.
The separate prior-year probe covers the continuous initial entry route.
No generator, pick, signing, cleanup, save or identity routine is replaced.
"""
from pathlib import Path
import hashlib
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_draft_ai as ai
from mod_editor.core import nfl2k5_senior_bowl as bowl
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_my_career_save as career
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, signed_save
from tests.nfl2k5_my_career_draft_fixture import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, signed f0 and Unicorn required')
class DraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        signed_save()  # precise private-evidence skip comes from the fixture
        cls.payload = mode.apply(ai.apply(retail_bytes())[0])[0]
        cls.roster = retail_roster()

    def members(self, m, p):
        teams = m.get(m.root + 0x1C)
        return [(club, slot) for club in range(32) for slot in range(65)
                if m.get(teams + 500*club + 4*slot) == p]

    def players(self, m):
        pool = m.get(m.root + 4)
        return tuple(bowl.Prospect(i, m.uc.mem_read(pool + 84*i+53, 1)[0],
                                  m.uc.mem_read(pool + 84*i+8, 1)[0])
                     for i in range(m.get(m.root)))

    def test_all_positions_and_combined_lb_keep_template_and_selected_squads(self):
        for pos, combined in [(p, False) for p in range(17)] + [(11, True)]:
            with self.subTest(position=pos, combined=combined), Machine(self.payload) as m:
                p = m.prepare_draft(self.roster, position=pos, one_pool=combined)
                index = m.get(m.state + 28)
                pool = m.get(m.root + 4)
                before = m.placement_before
                cap = bytearray(m.cap_record)
                cap[8] |= 0x10
                self.assertEqual(bytes(m.uc.mem_read(p, 84)), bytes(cap))
                # Exactly the selected same-position record is exchanged. All
                # generated players, including the displaced one, survive.
                for i in range(m.get(m.root)):
                    at = pool + 84*i - m.root
                    expected = bytes(cap) if i == index else (
                        before[p-m.root:p-m.root+84] if i == m.cap_index else before[at:at+84])
                    self.assertEqual(bytes(m.uc.mem_read(pool+84*i, 84)), expected, i)
                rows = self.players(m)
                self.assertEqual(len(bowl.current_class(rows)), 381)
                squads = bowl.select_squads(rows, scheme='one_pool' if combined else 'retail')
                self.assertEqual([len(t) for t in squads], [53, 53])
                self.assertEqual(sum(q.index == index for t in squads for q in t), 1)
                self.assertEqual(self.members(m, p), [])
                self.assertFalse(any(m.get(m.get(m.root+0x3C)+4*i) == p for i in range(m.get(m.root+0x38))))
                original = bytes(m.uc.mem_read(m.root, 0x91000))
                self.assertEqual(m.call('m3_place', ecx=m.manager), 0)
                self.assertEqual(bytes(m.uc.mem_read(m.root, len(original))), original)

    def test_bad_stage_membership_and_duplicate_fa_refuse_before_roster_write(self):
        with Machine(self.payload) as m:
            m.prepare_draft(self.roster)
            for fault in ('week', 'year', 'club', 'duplicate_fa'):
                with self.subTest(fault=fault):
                    m.uc.mem_write(m.root, m.placement_before)
                    p = m.get(m.root+4)+84*m.cap_index
                    for at, value in ((m.state+2676,p),(m.state+2680,2),(mode.EXTRA_VA,2),
                                      (0xE576B4,0),(0xE576B8,1)):
                        m.put(at,value)
                    if fault == 'week': m.put(0xE576B4,1)
                    if fault == 'year': m.put(0xE576B8,2)
                    if fault == 'club': m.put(m.get(m.root+0x1C),p)
                    if fault == 'duplicate_fa':
                        n=m.get(m.root+0x38)
                        m.put(m.get(m.root+0x3C)+4*n,p)
                        m.put(m.root+0x38,n+1)
                    before=bytes(m.uc.mem_read(m.root,0x91000))
                    self.assertEqual(m.call('m3_place',ecx=m.manager),0)
                    self.assertEqual(bytes(m.uc.mem_read(m.root,len(before))),before)

    def test_preparation_signed_reader_and_cold_load_preserve_the_player(self):
        with Machine(self.payload) as m:
            m.prepare_draft(self.roster, position=3)
            index=m.get(m.state+28)
            token=bytes(m.uc.mem_read(m.state+40,16))
            saved=m.native_save(budget=500000000)
        with tempfile.TemporaryDirectory(prefix='mycareer-prep-') as directory:
            path=Path(directory)/'SAVEGAME.DAT'
            path.write_bytes(saved)
            path.with_name('EXTRA').write_bytes(rr.sign_save(saved))
            document,players=bowl.read_franchise(path)
            self.assertEqual(document.mycareer,career.read(saved))
            self.assertEqual(sum(p.index==index for t in bowl.select_squads(players) for p in t),1)
            path.with_name('EXTRA').write_bytes(bytes(20))
            with self.assertRaisesRegex(ValueError,'EXTRA'):
                bowl.read_franchise(path)
        with Machine(self.payload) as cold:
            cold.cold(self.roster,saved)
            self.assertEqual(cold.top(),cold.labels['m3_prep_menu'])
            self.assertEqual(cold.get(cold.state+28),index)
            self.assertEqual(bytes(cold.uc.mem_read(cold.state+40,16)),token)
            self.assertEqual(cold.get(cold.state+24),2)

    def test_ai_drafts_high_rating_and_native_contract_reaches_apartment_then_cold(self):
        with Machine(self.payload) as m:
            self.assertEqual(bytes(m.uc.mem_read(ai.VALUE_VA,80)),ai.const_bytes())
            p=m.prepare_draft(self.roster,ratings=99)
            index=m.get(m.state+28)
            token=bytes(m.uc.mem_read(m.state+40,16))
            picks=[]
            m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_CODE,
                lambda *_: picks.append(m.get(0xE3C0A8)*32+m.get(0xE3C0A4)),
                begin=ai.PICK_FN_VA,end=ai.PICK_FN_VA))
            club=m.draft()
            self.assertGreaterEqual(len(picks),200)
            self.assertEqual(len(m.native_signings),1)
            self.assertEqual(m.native_signings[0]['stage'],5)
            self.assertLess(club,32)
            self.assertEqual(m.get(m.state+24),3)
            self.assertEqual(m.top(),m.labels['apartment'])
            self.assertEqual([c for c,_ in self.members(m,p)],[club])
            self.assertEqual(m.get(m.state+28),index)
            # Native contract years/salary are nonzero; flags leave prospect.
            self.assertNotEqual(m.get(p+0x24),0)
            self.assertEqual(m.uc.mem_read(p+8,1)[0]&0x30,0)
            self.assertEqual(m.get(m.state+64),0)
            saved=m.native_save(budget=500000000)
        with Machine(self.payload) as cold:
            cold.cold(self.roster,saved)
            self.assertEqual(cold.top(),cold.labels['apartment'])
            self.assertEqual(cold.get(cold.state+56),club)
            self.assertEqual(cold.get(cold.state+28),index)
            self.assertEqual(bytes(cold.uc.mem_read(cold.state+40,16)),token)
            self.assertEqual([c for c,_ in self.members(cold,cold.call('primary'))],[club])

    def test_mid_draft_cold_load_relocated_allocation_resumes_native_pick(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        with Machine(self.payload) as m:
            m.prepare_draft(self.roster)
            m.select(0,budget=200000000)
            for _ in range(10):
                m.frame(budget=500000000)
            progress=(m.get(0xE3C0A8),m.get(0xE3C0A4))
            token=bytes(m.uc.mem_read(m.state+40,16))
            index=m.get(m.state+28)
            saved=m.native_save(budget=500000000)
        relocated=mode.apply(mode.space.apply(ai.apply(retail_bytes())[0],REQUESTS,scaleout=True)[0])[0]
        self.assertNotEqual(mode.legacy.allocations(relocated)[0]['va'],mode.legacy.allocations(self.payload)[0]['va'])
        with Machine(relocated) as cold:
            cold.cold(self.roster,saved)
            self.assertEqual(cold.top(),cold.labels['m3_draft_menu'])
            self.assertEqual((cold.get(0xE3C0A8),cold.get(0xE3C0A4)),progress)
            self.assertEqual(cold.get(cold.state+28),index)
            self.assertEqual(bytes(cold.uc.mem_read(cold.state+40,16)),token)
            cold.replace_stub(0x48BC0,None)
            cold.frame(budget=500000000)
            self.assertEqual(cold.get(0xE3C0A8)*32+cold.get(0xE3C0A4),progress[0]*32+progress[1]+1)

    def test_low_ratings_undrafted_then_native_udfa_sign_keeps_identity(self):
        with Machine(self.payload) as m:
            p=m.prepare_draft(self.roster,ratings=0,position=1,preseason=False)
            token=bytes(m.uc.mem_read(m.state+40,16))
            index=m.get(m.state+28)
            self.assertEqual(m.draft(),0xFFFFFFFF)
            self.assertEqual(m.native_signings,[])
            self.assertEqual(m.get(m.state+24),4)
            self.assertEqual(m.top(),m.labels['team_menu'])
            self.assertEqual(self.members(m,p),[])
            self.assertEqual(sum(m.get(m.get(m.root+0x3C)+4*i)==p for i in range(m.get(m.root+0x38))),1)
            unsigned=m.native_save(budget=500000000)
            teams=m.get(m.root+0x1C)
            counts=[m.uc.mem_read(teams+500*c+0x11C,1)[0] for c in range(32)]
            self.assertEqual(counts,[54]*32)
            club=2
            t=teams+500*club
            old_members={m.get(t+4*i) for i in range(54)}
            other_rosters={c:bytes(m.uc.mem_read(teams+500*c,260)) for c in range(32) if c!=club}
            m.select(0)
            m.select(club)
            before=bytes(m.uc.mem_read(m.root,0x91000))
            m.dialog_answer=1
            m.select(1,budget=500000000)
            self.assertEqual(bytes(m.uc.mem_read(m.root,len(before))),before)
            self.assertEqual(m.top(),m.labels['team_menu'])
            self.assertEqual(m.get(m.state+24),4)
            m.dialog_answer=2
            m.select(1,budget=500000000)
            self.assertEqual(m.top(),m.labels['apartment'])
            self.assertEqual(m.get(m.state+56),club)
            self.assertEqual(m.get(m.state+28),index)
            self.assertEqual(bytes(m.uc.mem_read(m.state+40,16)),token)
            self.assertEqual([c for c,_ in self.members(m,p)],[club])
            self.assertEqual(m.get(m.state+64),0)
            # Without Practice Squad, native C3EE0 has 65 slots. Signing
            # at 54 must preserve the existing club instead of cutting it.
            counts[club] += 1
            self.assertEqual([m.uc.mem_read(teams+500*c+0x11C,1)[0] for c in range(32)],counts)
            new_members={m.get(t+4*i) for i in range(55)}
            self.assertEqual(new_members-old_members,{p})
            released=old_members-new_members
            self.assertEqual(released,set())
            fa=[m.get(m.get(m.root+0x3C)+4*i) for i in range(m.get(m.root+0x38))]
            self.assertNotIn(p,fa)
            self.assertEqual(sum(q in released for q in fa),0)
            self.assertEqual({c:bytes(m.uc.mem_read(teams+500*c,260)) for c in other_rosters},other_rosters)
            saved=m.native_save(budget=500000000)
        with Machine(self.payload) as cold:
            cold.cold(self.roster,saved)
            self.assertEqual(cold.top(),cold.labels['apartment'])
            self.assertEqual(cold.get(cold.state+28),index)
            self.assertEqual(bytes(cold.uc.mem_read(cold.state+40,16)),token)
            self.assertEqual(cold.get(cold.state+64),0)
            self.assertEqual([c for c,_ in self.members(cold,cold.call('primary'))],[club])
        # Reload the same native undrafted result with the installed Practice
        # Squad owner. Its 53-player limit and occupied reserve tail must be
        # honored instead of treating that tail as corrupt retail storage.
        from mod_editor.core import nfl2k5_practice_squad as ps
        squad_payload=mode.apply(ps.apply(ai.apply(retail_bytes())[0])[0])[0]
        with Machine(squad_payload) as squad:
            squad.cold(self.roster,unsigned)
            self.assertEqual(squad.top(),squad.labels['team_menu'])
            t=squad.get(squad.root+0x1C)+500*club
            reserved=squad.get(t)
            reserve_index=(reserved-squad.get(squad.root+4))//84
            self.assertEqual(squad.call(ps.SYMBOLS['ps_demote'],ecx=t,edx=reserved),1)
            self.assertEqual(squad.uc.mem_read(t+0x11C,1)[0],53)
            self.assertEqual(squad.uc.mem_read(t+ps.COUNT,1)[0],1)
            squad.select(0)
            squad.select(club)
            before=bytes(squad.uc.mem_read(squad.root,0x91000))
            squad.dialog_answer=1
            squad.select(1,budget=500000000)
            self.assertEqual(bytes(squad.uc.mem_read(squad.root,len(before))),before)
            squad.dialog_answer=2
            squad.select(1,budget=500000000)
            self.assertEqual(squad.top(),squad.labels['apartment'])
            self.assertEqual(squad.uc.mem_read(t+0x11C,1)[0],53)
            self.assertEqual(squad.uc.mem_read(t+ps.COUNT,1)[0],1)
            self.assertEqual(squad.get(t+4*53),reserved)
            self.assertEqual([c for c,_ in self.members(squad,squad.call('primary'))],[club])
            self.assertEqual(squad.get(squad.state+28),index)
            self.assertEqual(bytes(squad.uc.mem_read(squad.state+40,16)),token)
            saved=squad.native_save(budget=500000000)
        with Machine(squad_payload) as cold:
            cold.cold(self.roster,saved)
            self.assertEqual(cold.top(),cold.labels['apartment'])
            t=cold.get(cold.root+0x1C)+500*club
            self.assertEqual(cold.uc.mem_read(t+0x11C,1)[0],53)
            self.assertEqual(cold.uc.mem_read(t+ps.COUNT,1)[0],1)
            self.assertEqual((cold.get(t+4*53)-cold.get(cold.root+4))//84,reserve_index)
            self.assertEqual(cold.get(cold.state+28),index)
            self.assertEqual(bytes(cold.uc.mem_read(cold.state+40,16)),token)


if __name__ == '__main__':
    unittest.main()

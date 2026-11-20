"""The shipped Studio owner retains known bytes through installs, edits, dependency changes and rollback."""
import struct
import unittest

from mod_editor.core import nfl2k5_edge_rename as edge, nfl2k5_k128 as memory
from mod_editor.core import nfl2k5_lineup_roles as lineup, nfl2k5_modern_positions as positions
from mod_editor.core import nfl2k5_position_pools as pools, nfl2k5_senior_bowl as senior
from mod_editor.core import nfl2k5_sim_qb_injuries as qb, nfl2k5_sim_qb_injuries_code as code
from mod_editor.core import nfl2k5_sim_realism as simulator, nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import retail_bytes


class SettingTests(unittest.TestCase):
    def test_rate_round_trip_and_lower_upper_neighbors(self):
        for percent, units in [(0,0),('.001',1),('.309',309),(.310,310),(.311,311),(99.999,99999),(100,100000)]:
            with self.subTest(percent=percent):
                setting = qb._setting('custom', percent)
                self.assertEqual(setting.rate, units)
                self.assertEqual(qb._Setting.from_marker(setting.marker()), setting)
        self.assertNotEqual(qb._setting('realistic', None).marker(), qb._setting('custom', .31).marker())
        self.assertIsNone(qb._setting('retail', None))

    def test_invalid_percent_and_marker(self):
        for bad in (-1, '0.0001', '100.001', 'nan', 'inf', None, True):
            with self.subTest(rate=bad), self.assertRaises(qb.SimQbInjuriesError):
                qb._setting('custom', bad)
        with self.assertRaises(qb.SimQbInjuriesError):
            qb._setting('other', 1)
        for mode,rate,reserved in ((0,310,0),(1,309,0),(2,100001,0),(2,1,1)):
            with self.subTest(mode=mode,rate=rate), self.assertRaises(qb.SimQbInjuriesError):
                qb._Setting.from_marker(qb.MARK.pack(qb.SIGNATURE, mode, rate, reserved))
        self.assertEqual(qb.status(b'foreign'), 'foreign')


class NativeSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clean = retail_bytes()
        labeled = positions.apply(edge.apply(clean)[0])[0]
        paired = pools.apply(labeled, roster_has_olb=True)[0]
        cls.standard = space.apply(paired, (*memory.REQUESTS, *simulator.REQUESTS, *lineup.REQUESTS), scaleout=True)[0]
        cls.standard = simulator.apply(memory.apply(cls.standard, require=True)[0])[0]
        cls.roles = lineup.apply(cls.standard, third_down=False)[0]
        cls.enabled = qb.apply(cls.roles)[0]

    def test_whole_executable_retuning_and_off(self):
        blank = space.extend_scaleout(self.roles, qb.REQUESTS)[0]
        self.assertEqual(qb.physical_view(self.enabled), blank)
        self.assertEqual(qb.apply(self.enabled)[0], self.enabled)
        for custom_rate in (0, .309, .310, .311, 100):
            with self.subTest(percent=custom_rate):
                reviewed, _ = qb.apply(self.enabled, 'custom', custom_rate=custom_rate)
                self.assertEqual(qb.read_settings(reviewed), {'mode':'custom','status':'applied','custom_rate':custom_rate,
                                                              'revision':3,'positions':custom_rate > 0})
                self.assertEqual(qb.physical_view(reviewed), blank)
                self.assertEqual(qb.apply(reviewed)[0], self.enabled)
                self.assertEqual(qb.apply(reviewed, 'retail')[0], blank)
                self.assertEqual(simulator.status(reviewed), simulator.status(blank))
                self.assertEqual(lineup.read_settings(reviewed), lineup.read_settings(blank))
                self.assertEqual(senior.status(reviewed), senior.status(blank))

    def test_enable_lineup_before_or_after_and_keep_existing_allocations(self):
        for mode,rate in (('realistic',.310),('custom',0)):
            with self.subTest(mode=mode):
                clinical, _ = qb.apply(self.standard,mode,custom_rate=rate)
                self.assertEqual(lineup.apply(clinical,third_down=False)[0], qb.apply(self.roles,mode,custom_rate=rate)[0])
        before = {(r['owner'],r['kind'],r['va'],r['raw']) for r in space.layout(self.roles)['allocations'] if r['owner'] != space.DIRECTORY_OWNER}
        after = {(r['owner'],r['kind'],r['va'],r['raw']) for r in space.layout(self.enabled)['allocations'] if r['owner'] != space.DIRECTORY_OWNER}
        self.assertTrue(before < after)
        self.assertEqual(len(after - before),1)
        bank = qb._bank_allocation(self.enabled)
        self.assertEqual(bank['va'] % space.PAGE,0)
        self.assertTrue(XbeImage(self.enabled).section(bank['va'],bank['size']).writable)

    def test_no_forced_install_on_stock_or_incomplete_standard(self):
        original=retail_bytes()
        self.assertEqual(qb.apply(original,'retail')[0],original)
        for image in (original, memory.apply(original,require=True)[0], simulator.apply(original)[0]):
            with self.subTest(bytes=len(image)),self.assertRaises(qb.SimQbInjuriesError):
                qb.apply(image)

    def test_refuse_partial_runtime_shared_edits_and_unknown_sibling_bytes(self):
        bank=qb._bank_allocation(self.enabled)
        image=XbeImage(self.enabled)
        guarded=qb._edits(self.enabled,bank,qb._setting('realistic',None))
        for name,address,old,new in guarded:
            if name=='simulated QB injury bank':
                continue
            with self.subTest(label=name):
                bad=qb._transform(self.enabled,[(name,address,new,old)],restoring=False)
                self.assertEqual(qb.status(bad),'foreign')
                with self.assertRaises(ValueError):
                    qb.apply(bad,'retail')
        base=bank['va']
        sim,_=simulator._allocations(self.enabled)
        for address in (base,base+code.MARK_OFFSET,base+0x800,base+0x3b00+97*4,0x102887,sim['va']+12):
            with self.subTest(address=hex(address)):
                old=image.read(address,1)
                bad=qb._transform(self.enabled,[('damaged',address,old,bytes([old[0]^1]))],restoring=False)
                self.assertEqual(qb.status(bad),'foreign')
                self.assertEqual(simulator.status(bad),'foreign')
                with self.assertRaises(ValueError):
                    qb.apply(bad)
        emptied=qb._transform(self.enabled,[('cleared bank',base,image.read(base,code.CODE_SIZE),b'\xcc'*code.CODE_SIZE)],restoring=False)
        self.assertEqual(qb.status(emptied),'foreign')

    def test_running_back_owner_installed_after_the_option_fails_closed(self):
        """Build installs the running-back owner first. Installed after the option, its weekly jump lands where the
        option expects the game's tail (0x133CC9): the option reads foreign and Retail and re-apply refuse instead of
        guessing (review rev-pos2 L2). Restoring Retail first, then the owner, then the option is the way through."""
        from mod_editor.core import nfl2k5_sim_rb_injuries as running_backs
        clean = retail_bytes()
        paired = pools.apply(positions.apply(edge.apply(clean)[0])[0], roster_has_olb=True)[0]
        base = space.apply(paired, (*memory.REQUESTS, *running_backs.REQUESTS, *simulator.REQUESTS, *lineup.REQUESTS),
                           scaleout=True)[0]
        base = lineup.apply(simulator.apply(memory.apply(base, require=True)[0])[0], third_down=False)[0]
        tail, site = bytes.fromhex('5f5e5bc390'), code.WEEKLY_HALFBACK_SITE
        built = qb.apply(running_backs.apply(base)[0])[0]           # Build's order
        self.assertEqual((qb.status(built), running_backs.status(built)), ('applied', 'applied'))
        self.assertEqual(XbeImage(built).read(site, 5), tail)
        option_first = qb.apply(base)[0]                             # the running-back cave is still empty
        self.assertEqual(XbeImage(option_first).read(site, 5), tail)
        late = running_backs.apply(option_first)[0]
        self.assertNotEqual(XbeImage(late).read(site, 5), tail)      # the owner's jump
        self.assertEqual(running_backs.status(late), 'applied')
        self.assertEqual(qb.status(late), 'foreign')
        for mode, rate in (('retail', .310), ('realistic', .310), ('custom', 0), ('custom', 100)):
            with self.subTest(mode=mode, rate=rate), self.assertRaises(qb.SimQbInjuriesError):
                qb.apply(late, mode, custom_rate=rate)
        through = qb.apply(running_backs.apply(qb.apply(option_first, 'retail')[0])[0])[0]
        self.assertEqual(through, built)

    def test_option_preserves_entire_foreign_span_outside_its_sites(self):
        src=qb.physical_view(self.enabled)
        image=XbeImage(src)
        address=0x10b96a  # Same Senior Bowl guard as the weekly entry, outside the five owned bytes.
        old=image.read(address,1)
        foreign=qb._transform(src,[('unrelated change',address,old,bytes([old[0]^1]))],restoring=False)
        self.assertEqual(senior.status(foreign),'foreign')
        enabled=qb.apply(foreign)[0]
        self.assertEqual(senior.status(enabled),'foreign')
        self.assertEqual(qb.apply(enabled,'retail')[0],foreign)


if __name__ == "__main__":
    unittest.main()

"""Experimental executable build passes under the release's non-POSIX shim.

Uses the existing simwin66/everything BuildPlan fixture and its AST-derived
production dispatcher calls. All available compatible XBE switches are selected,
including J3/J4/J5. Archive payloads, external art/audio and an entire disc build
are outside this bounded check; compact-disc publication is tested separately.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tests.nfl2k5_b661_transition import compose,plan_for,DISC
from tests.mod_editor.test_shipped_tools_posix_only import simulated_non_posix
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from mod_editor.core import nfl2k5_throw_tuning as tt,nfl2k5_weather_haze as haze


@unittest.skipUnless(DISC.is_file(),'private USA disc required for compiled PLAY intent inputs')
class SimulatedWindowsBuildTests(unittest.TestCase):
    def test_everything_experimental_has_identical_posix_and_nonposix_writers(self):
        retail=retail_xbe()
        plan=replace(plan_for('everything'),coin_defer=True,decided_clock=True,
            decided_clock_margin=25,decided_clock_seconds=90,cpu_scrambles='modern',weather_haze=True)
        def build_xbe():
            payload,receipt=compose(retail,plan)
            # The fixture predates this final data-only pass. Execute the real
            # same writer here; the compact image suite runs mod_build.build itself.
            payload,haze_receipt=haze.apply(payload,enabled=plan.weather_haze)
            receipt['passes'].append('weather_haze')
            receipt['weather_haze']=haze_receipt
            return payload,receipt
        posix,receipt=build_xbe()
        with simulated_non_posix(): simulated,windows_receipt=build_xbe()
        self.assertEqual(simulated,posix)
        self.assertEqual(windows_receipt,receipt)
        for owner in (tt.coin_defer_patch,tt.decided_clock_patch,tt.cpu_scrambles_patch,
                      tt.my_career_mode_patch,tt.accelerated_clock_patch,haze):
            self.assertEqual(owner.status(simulated),'applied',owner.OWNER)
        tt.decided_clock_patch.verify(simulated,margin=25,seconds=90)
        for key in ('coin_defer','decided_clock','cpu_scrambles'):
            self.assertIn(key,tt.R62_SPACE_KEYS)
        from mod_editor.core.nfl2k5_bump_strength import _sections,section_digest
        for section in _sections(simulated):
            self.assertEqual(simulated[section.header_offset+36:section.header_offset+56],section_digest(simulated,section))
        receipt.update(xbe_sha256=hashlib.sha256(simulated).hexdigest(),
            allocator_layout=tt.xbe_space_patch.layout(simulated),
            runtime_witnessed=False,full_disc_built=False,
            scope='BuildPlan executable passes and native PLAY intent compilation; archive/resource transport excluded')
        if destination:=os.environ.get('NFL2K5_A2B_SIMWIN_TRACE'):
            Path(destination).write_bytes((json.dumps(receipt,indent=2)+'\n').encode())
        print('Experimental XBE passes: POSIX/non-POSIX identical; J3/J4/J5 verified; no full disc built')


if __name__=='__main__':unittest.main()

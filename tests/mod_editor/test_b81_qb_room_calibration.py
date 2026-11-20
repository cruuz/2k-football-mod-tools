"""b81 qb34, review F5 (rev-qb34): the Studio's settings record carries the calibrated H0 from shadow panel P0.

H0 is D3's base benching chance in millionths. P0 fixed it at 0.0270 (27,000 ppm) and panel P1 ran at that value through
a calibration record; the Studio's own record must carry the same value, or 3b ships uncalibrated.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

P0_H0_PPM = 27000


class StudioRecordCalibrationTests(unittest.TestCase):
    def test_the_template_and_the_studio_record_carry_p0s_h0(self):
        from mod_editor.core import nfl2k5_qb_room as room
        code = room._code()
        self.assertEqual(code.H0_PPM, P0_H0_PPM)
        record = code.parse_settings(code.settings_record(room.REALISTIC_STAGES, shadow=room.SHADOW_DEFAULT))
        self.assertEqual(record["h0_ppm"], P0_H0_PPM)

    def test_an_installed_studio_page_reads_back_p0s_h0(self):
        from mod_editor.core import mod_build, nfl2k5_qb_room as room, nfl2k5_sim_qb_injuries as qb
        disc = Path(os.environ.get("NFL2K5_B81_REVIEWED_TEST_DISC", ""))
        if not disc.is_file():
            self.skipTest("the private reviewed test disc is absent")
        source = mod_build._xbe_bytes(disc)
        self.assertEqual(hashlib.sha256(source).hexdigest()[:8], "98dd7329")
        applied, _ = room.install_stages(qb.apply(source, "realistic")[0], room._code().STAGE_D1)
        self.assertEqual(room.read_settings(applied)["h0_ppm"], P0_H0_PPM)


if __name__ == "__main__":
    unittest.main()

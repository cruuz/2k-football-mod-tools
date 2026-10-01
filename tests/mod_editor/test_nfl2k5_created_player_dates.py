"""CP: execute the native date controls and card, and compose the actual owners.

No disc build or Xbox boot. Existing fixtures supply rendering/device services
and entropy; initializer, field edits, text formatting and save codecs execute.
"""
import calendar as gregorian
import hashlib
import struct
import unittest

from mod_editor.core import nfl2k5_season_length as season
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_calendar_engine as calendar
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_my_career_played_fixture import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
from tests.mod_editor.test_nfl2k5_my_career_vb1 import birth_raw, shown_year
from tests.mod_editor.test_nfl2k5_calendar_engine import repin


def text_at(m, pointer):
    return bytes(m.uc.mem_read(pointer, 128)).decode("utf-16le").split("\0")[0]


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned retail XBE, ROST and Unicorn required")
class CreatedPlayerDatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.roster = retail_roster()
        cls.modern = season.apply(cls.retail, groups=("year", "created_player_dates"))[0]
        # Empty named allocations let the shared CPU fixture run without
        # installing MyCareer. All native CAP instructions remain unhooked.
        cls.native_retail = mode.space.apply(cls.retail, mode.REQUESTS, scaleout=True)[0]
        cls.native_modern = mode.space.apply(cls.modern, mode.REQUESTS, scaleout=True)[0]
        cls.career = mode.apply(cls.modern)[0]

    def player(self, m):
        m.frontend(self.roster)
        p = m.call(0xBFF50)
        m.call(0xC0A80, ecx=p)
        m.put(0xCB8B14, p)
        return p

    def test_option_off_keeps_retail_default_limits_and_rookie_marker(self):
        with Machine(self.native_retail) as m:
            p = self.player(m)
            self.assertEqual(shown_year(m), "1979")
            self.assertEqual(m.uc.mem_read(p + 0x25, 1)[0] & 31, 1)
            self.assertEqual(text_at(m, m.call(0x145DA0, ecx=p)), "R")
            for start, handler, expected in ((84, 0x343D20, 54), (54, 0x343D70, 84)):
                m.put(p + 24, (start << 21) | 0x11000)
                m.call(handler)
                self.assertEqual(birth_raw(m, p), expected)
        for s in season.created_player_date_sites(2026):
            self.assertEqual(XbeImage(self.retail).read(s.va, s.size), s.retail)

    def test_season_alone_initializes_january_2004_and_preserves_rookie(self):
        with Machine(self.native_modern) as m:
            # Stale franchise globals must not change a front-end new player.
            for stale in (0, 1, 127):
                p = self.player(m)
                m.put(0xE576B8, stale)
                m.call(0xC0A80, ecx=p)
                self.assertEqual(shown_year(m), "2004")
                self.assertEqual(text_at(m, m.call(0x145D20, ecx=p)), "1/1/2004")
                self.assertEqual(text_at(m, m.call(0x145DA0, ecx=p)), "R")

    def test_every_year_both_directions_wrap_and_preserve_other_bits(self):
        with Machine(self.native_modern) as m:
            p = self.player(m)
            outside = 0xA015BCA5 & ~season.CAP_YEAR_MASK
            for year in range(1981, 2009):
                raw = year - 1900
                for handler, expected in ((0x343D20, 81 if raw == 108 else raw + 1),
                                          (0x343D70, 108 if raw == 81 else raw - 1)):
                    with self.subTest(year=year, handler=hex(handler)):
                        m.put(p + 24, outside | (raw << 21))
                        self.assertEqual(shown_year(m), str(year))
                        before = bytes(m.uc.mem_read(p, 84))
                        m.call(handler)
                        self.assertEqual(m.get(p + 24), outside | (expected << 21))
                        expected_record = bytearray(before)
                        struct.pack_into("<I", expected_record, 24, outside | (expected << 21))
                        self.assertEqual(m.uc.mem_read(p, 84), expected_record)
                        self.assertEqual(shown_year(m), str(expected + 1900))
            for raw in (4, 5, 26, 81, 99, 100, 104, 108):
                m.put(p + 24, 0x11000 | (raw << 21))
                year = raw + (2000 if raw <= 26 else 1900)
                self.assertEqual(shown_year(m), str(year))
                self.assertEqual(text_at(m, m.call(0x145D20, ecx=p)), f"1/1/{year}")

    def test_full_instruction_pins_and_partial_companion_refuse(self):
        for s in season.created_player_date_sites(2026):
            with self.subTest(site=s.label):
                bad = repin(self.retail, s.va, b"\xcc")
                self.assertEqual(season.group_status(bad, "created_player_dates"), "foreign")
                with self.assertRaises(ValueError):
                    season.apply(bad, groups=("year", "created_player_dates"))
                bad = repin(self.career, s.va, s.retail)
                self.assertEqual(mode.status(bad), "foreign")
                with self.assertRaises(ValueError):
                    mode.apply(bad)
        # The whole initializer guard is still checked after normalizing only
        # the six owned bytes. A foreign neighboring instruction cannot hide.
        self.assertEqual(mode.status(repin(self.career, 0xC0AE2, b"\xcc")), "foreign")
        self.assertEqual(mode.apply(self.career)[0], self.career)

    def test_february_day_limit_and_clamp_including_leap_2000(self):
        with Machine(self.native_modern) as m:
            p = self.player(m)
            for year in range(1981, 2009):
                days = gregorian.monthrange(year, 2)[1]
                for raw in (year - 1900, year % 100):
                    self.assertEqual(m.call(0x343170, eax=raw, esi=2), days, year)
                    m.put(p + 24, (raw << 21) | (28 << 16) | (2 << 12))
                    m.call(0x346A80)  # next day
                    self.assertEqual((m.get(p + 24) >> 16) & 31, 29 if days == 29 else 1)
                    m.put(p + 24, (raw << 21) | (1 << 16) | (2 << 12))
                    m.call(0x346AE0)  # previous day wraps
                    self.assertEqual((m.get(p + 24) >> 16) & 31, days)
                    m.put(p + 24, (raw << 21) | (31 << 16) | (2 << 12))
                    m.call(0x346840)  # final page clamps invalid day
                    self.assertEqual((m.get(p + 24) >> 16) & 31, days)

    def test_calendar_and_mycareer_compose_in_both_orders(self):
        requests = mode.REQUESTS + calendar.REQUESTS
        base = season.apply(self.retail)[0]
        base = mode.space.apply(base, requests, scaleout=True)[0]
        for owners in ((calendar, mode), (mode, calendar)):
            out = base
            for owner in owners:
                out = owner.apply(out)[0]
            self.assertEqual(mode.status(out), "applied")
            self.assertEqual(calendar.status(out), "applied")
            self.assertEqual(season.simple_status(out), "applied")
            with Machine(out) as m:
                p = self.player(m)
                m.put(0xE576B8, 1)
                self.assertEqual(text_at(m, m.call(0x145D20, ecx=p)), "1/1/2004")

    def test_manifest_recorder_assigns_all_date_instructions_to_season(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        out, receipt = season.apply(self.retail, groups=("year", "created_player_dates"))
        recorder.observe(season, "apply", self.retail, out, receipt)
        for s in season.created_player_date_sites(2026):
            self.assertTrue(any(int(r["start"], 0) <= s.va and int(r["end"], 0) >= s.va + s.size
                                and r["owner"] == "nfl2k5_season_length" for r in recorder.spans), s.label)
        edits = mode.sites(0, 0, season_birth_dates=True)
        for s in season.created_player_date_sites(2026):
            self.assertFalse(any(s.va < va + len(before) and va < s.va + s.size
                                 for _, va, before, _ in edits), s.label)

    def test_policy_uses_requested_build_year_and_checks_encoding_limit(self):
        for year in (2004, 2027, 2045):
            out = season.apply(self.retail, groups=("year", "created_player_dates"), year=year)[0]
            out = mode.space.apply(out, mode.REQUESTS, scaleout=True)[0]
            with Machine(out) as m:
                self.player(m)
                self.assertEqual(shown_year(m), str(year - 22))
        with self.assertRaisesRegex(ValueError, "seven bits"):
            season.created_player_date_sites(2046)

    def test_new_career_dob_survives_native_save_and_cold_load(self):
        with Machine(self.career) as m:
            p = m.create(self.roster)
            dob = m.get(p + 24) & 0x0FFFF000
            self.assertEqual(dob, (104 << 21) | 0x11000)
            self.assertEqual(text_at(m, m.call(0x145DA0, ecx=p)), "R")
            saved = m.native_save(budget=500000000)
        with Machine(self.career) as m:
            m.frontend(self.roster)
            m.native_load(saved)
            p = m.call("primary")
            self.assertNotEqual(p, 0)
            self.assertEqual(m.get(p + 24) & 0x0FFFF000, dob)
            self.assertEqual(text_at(m, m.call(0x145D20, ecx=p)), "1/1/2004")
            self.assertEqual(text_at(m, m.call(0x145DA0, ecx=p)), "R")


if __name__ == "__main__":
    unittest.main()

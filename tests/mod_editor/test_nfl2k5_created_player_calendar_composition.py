"""CP2: calendar dependencies must not claim the optional CAP editing policy."""
import hashlib
import unittest

from mod_editor.core import nfl2k5_calendar_engine as calendar
from mod_editor.core import nfl2k5_my_career_mode as career
from mod_editor.core import nfl2k5_season_length as season
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.mod_editor.test_nfl2k5_calendar_engine import XBE, repin


@unittest.skipUnless(XBE.is_file(), "pinned retail XBE required")
class CalendarCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise AssertionError("retail XBE pin differs")

    def compose_both_orders(self, base):
        base = career.space.apply(base, career.REQUESTS + calendar.REQUESTS, scaleout=True)[0]
        results = []
        for owners in ((career, calendar), (calendar, career)):
            out = base
            for owner in owners:
                out = owner.apply(out)[0]
            for owner in owners:
                self.assertEqual(owner.status(out), "applied")
                self.assertEqual(owner.apply(out)[0], out)
            results.append(out)
        self.assertEqual(*results)
        return results[0]

    def test_legacy_mycareer_and_calendar_both_orders_at_both_epochs(self):
        # These are the missing CP cases: no modern CAP policy is installed.
        for year in calendar.SUPPORTED_BASE_YEARS:
            with self.subTest(year=year):
                base = self.retail if year == 2004 else season.apply(
                    self.retail, groups=("year",), year=year)[0]
                out = self.compose_both_orders(base)
                self.assertEqual(season.group_status(out, "year", year=year), "applied")
                image = XbeImage(out)
                for label, va, _, after in career.sites(0, 0):
                    if label in season.CAP_SHARED_YEAR_LABELS:
                        self.assertEqual(image.read(va, len(after)), after, label)
                for site in season.created_player_date_sites(year):
                    if site.label not in season.CAP_SHARED_YEAR_LABELS:
                        self.assertEqual(image.read(site.va, site.size), site.retail, site.label)

    def test_complete_season_policy_and_both_runtime_orders_at_both_epochs(self):
        for year in calendar.SUPPORTED_BASE_YEARS:
            with self.subTest(year=year):
                out = self.compose_both_orders(season.apply(self.retail, year=year)[0])
                for group in season.GROUPS:
                    self.assertEqual(season.group_status(out, group, year=year), "applied", group)
                image = XbeImage(out)
                for site in season.created_player_date_sites(year):
                    self.assertEqual(image.read(site.va, site.size), site.patched, site.label)

    def test_calendar_alone_preserves_retail_creation_and_rejects_foreign_year(self):
        out, receipt = calendar.apply(self.retail)
        self.assertNotIn("created_player_dates", receipt["season_dependencies"]["groups"])
        self.assertEqual(season.group_status(out, "created_player_dates", year=2004), "retail")
        for site in season.created_player_date_sites(2004):
            self.assertEqual(XbeImage(out).read(site.va, site.size), site.retail)
        for site in season.year_sites(2026):
            damaged = repin(self.retail, site.va, b"\xcc")
            with self.subTest(site=site.label):
                self.assertEqual(calendar.status(damaged), "foreign")
                with self.assertRaises(ValueError):
                    calendar.apply(damaged)

    def test_modern_franchise_dispatcher_preserves_complete_creation_policy(self):
        # Same executable owner order/options as the ultimate recipe's franchise
        # path. This is an in-memory XBE transaction, not an image/disc build.
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        from mod_editor.core import nfl2k5_franchise_economy as economy
        from mod_editor.core import nfl2k5_practice_squad as squad
        from mod_editor.core import nfl2k5_franchise_practice as practice
        from mod_editor.core import nfl2k5_practice_reserves as reserves
        from mod_editor.core import nfl2k5_franchise_edit_player as editor
        from mod_editor.core import nfl2k5_franchise_autosave as autosave
        from mod_editor.core import nfl2k5_season_cap as cap
        base = season.apply(self.retail, super_bowl_venue=season.SOFI_SB_VENUE)[0]
        options = dict(catch_slider=False, arc_table=False, calendar_engine=True,
                       my_career=True, season_cap=True, franchise_economy=True,
                       practice_squad=True, franchise_practice=True,
                       franchise_edit_player=True, franchise_autosave=True)
        out = tuning._apply_all(base, None, **options)[0]
        for owner in (calendar, career, economy, squad, practice, reserves, editor, autosave, cap):
            self.assertEqual(owner.status(out), "applied", owner.__name__)
        self.assertEqual(season.simple_status(out), "applied")
        self.assertEqual(tuning._apply_all(out, None, **options)[0], out)
        image = XbeImage(out)
        for site in season.created_player_date_sites(2026):
            self.assertEqual(image.read(site.va, site.size), site.patched, site.label)


if __name__ == "__main__":
    unittest.main()

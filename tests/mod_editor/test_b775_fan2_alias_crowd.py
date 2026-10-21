"""b775-fan2: every Anniversary moment stadium draws the same fans as the venue it was copied from.

Noah 10/16: "the 25th anniversary scenarios would have random parts of the stands with glitched fans". On the v0.6.1
Oct 13 disc the ten built moment aliases were copies of their venues taken before cr1 fixed the fans' proportions;
cr1's native repair covered only the 153 sNN venues, so the moments kept squashed and stretched fans. The field
compiler now proves each alias keeps its venue's crowd, and the build's final gate refuses an alias whose venue's fans
changed after the fields were compiled.
"""
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_anniversary_pack as pack  # noqa: E402
from mod_editor.core import nfl2k5_espn25_fields as fields  # noqa: E402
from mod_editor.core import nfl2k5_historic_styles as styles  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
# A finished Studio build whose aliases were compiled after every venue pass (the i4 test disc), and the Oct 13 disc
# whose built aliases predate cr1's native crowd repair. Both are optional private fixtures, read only.
GOOD = Path(os.environ.get("NFL2K5_FAN2_GOOD_DISC", "/nonexistent/fan2-good"))
STALE = Path(os.environ.get("NFL2K5_FAN2_STALE_DISC", "/nonexistent/fan2-stale"))
BUILT_ROWS = (27, 29, 36, 42, 44, 45, 46, 48, 49, 50, 51)
# The Oct 13 disc's stale rows: every built row except 51 (The UNC Bowl), whose Paycor venue cr1 did not change.
STALE_ROWS = (27, 29, 36, 42, 44, 45, 46, 48, 49, 50)


def receipt_rows(image):
    """Compile-receipt-shaped rows for the 51 aliases on a finished image."""
    from mod_editor.core import nfl2k5_espn25_more_moments as moments
    situ = image.get(identity=moments.SITU_ID)
    rows = []
    for row in fields.catalog():
        code = fields.variant(situ, row["row"] - 1)
        rows.append(dict(row=row["row"], alias=f"a{row['row'] - 1:02d}{code}.iff",
                         source=row["source_prefix"] + code + ".iff", source_kind=row["source_kind"]))
    return rows


class CatalogShape(unittest.TestCase):
    def test_built_rows_are_the_modern_venue_moments(self):
        self.assertEqual(tuple(r["row"] for r in fields.catalog() if r["source_kind"] == "built"), BUILT_ROWS)


class DriftLogic(unittest.TestCase):
    def test_only_built_rows_are_compared_and_differences_are_named(self):
        crowds = {"a26nd.iff": "old", "s00nd.iff": "new", "a35ad.iff": "same", "s18ad.iff": "same",
                  "a00ds.iff": "retail copy", "s10ds.iff": "modern lambeau"}
        assets = [dict(row=27, alias="a26nd.iff", source="s00nd.iff", source_kind="built"),
                  dict(row=36, alias="a35ad.iff", source="s18ad.iff", source_kind="built"),
                  dict(row=1, alias="a00ds.iff", source="s10ds.iff", source_kind="retail")]
        with mock.patch.object(fields, "stadium_crowd_digest", side_effect=lambda raw: crowds[raw]):
            drift = fields.crowd_drift(lambda name: name, assets)
        self.assertEqual([(d["row"], d["alias"], d["source"]) for d in drift], [(27, "a26nd.iff", "s00nd.iff")])

    def test_final_gate_refuses_an_alias_whose_venue_fans_changed(self):
        situ = b"finished 51-row situation"
        raw = {f"a{i:02}dd.iff": b"alias %d" % i for i in range(51)}
        raw.update({"s00dd.iff": b"venue", "a26dd.iff": b"alias 26"})
        assets = [dict(row=i + 1, alias=f"a{i:02}dd.iff", size=len(raw[f"a{i:02}dd.iff"]),
                       after=pack.sha(raw[f"a{i:02}dd.iff"]), source="s00dd.iff",
                       source_kind="built" if i == 26 else "retail") for i in range(51)]
        receipt = dict(fields=dict(assets=assets), situation_after_sha256=pack.sha(situ))
        source = mock.MagicMock()
        source.__enter__.return_value = source
        source.get.side_effect = lambda name=None, identity=None: situ if identity else raw[name]
        crowds = {b"venue": "fixed fans", b"alias 26": "fixed fans"}
        with mock.patch.object(styles, "Source", return_value=source), \
                mock.patch.object(fields, "stadium_crowd_digest", side_effect=lambda b: crowds.get(b, "x")):
            result = pack.verify_fields_on_image("finished.iso", receipt)
            self.assertEqual((result["assets_verified"], result["crowd_rows_verified"]), (51, 1))
            crowds[b"venue"] = "fans repaired after the fields were compiled"
            with self.assertRaisesRegex(ValueError, "crowd differs from its venue: a26dd.iff vs s00dd.iff"):
                pack.verify_fields_on_image("finished.iso", receipt)


@unittest.skipUnless(RETAIL.is_file(), "private retail source required")
class RetailDigest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with styles.Source(RETAIL) as source:
            cls.s00, cls.s01, cls.s25 = (source.get(n) for n in ("s00dd.iff", "s01dd.iff", "s25nd.iff"))

    def test_digest_is_stable_and_tells_venues_apart(self):
        self.assertEqual(fields.stadium_crowd_digest(self.s00), fields.stadium_crowd_digest(bytes(self.s00)))
        self.assertNotEqual(fields.stadium_crowd_digest(self.s00), fields.stadium_crowd_digest(self.s01))

    def test_new_field_paint_keeps_the_crowd(self):
        # The compiler replaces only the field scene; the fans must be untouched.
        chunk, _, _ = fields._field_chunk(self.s25)
        from mod_editor.core import nfl2k5_modern_metlife as metlife
        before = metlife.scene_span(self.s25, chunk)
        span, _ = fields._retail_playoff_field(self.s25)
        after = self.s25[:chunk.offset] + span + self.s25[chunk.offset + len(before):]
        self.assertNotEqual(after, self.s25)
        self.assertEqual(fields.stadium_crowd_digest(after), fields.stadium_crowd_digest(self.s25))

    def test_bundle_without_a_stadium_is_refused(self):
        with self.assertRaises(ValueError):
            fields.stadium_crowd_digest(b"\0" * 64)


@unittest.skipUnless(GOOD.is_file(), "private finished Studio build required (NFL2K5_FAN2_GOOD_DISC)")
class FinishedBuild(unittest.TestCase):
    def test_every_built_alias_draws_its_venue_fans(self):
        with styles.Source(GOOD) as image:
            rows = receipt_rows(image)
            self.assertEqual(fields.crowd_drift(image.get, rows), [])


@unittest.skipUnless(STALE.is_file(), "private Oct 13 v0.6.1 disc required (NFL2K5_FAN2_STALE_DISC)")
class StaleDisc(unittest.TestCase):
    def test_the_oct_13_disc_moments_kept_the_pre_cr1_fans(self):
        with styles.Source(STALE) as image:
            drift = fields.crowd_drift(image.get, receipt_rows(image))
        self.assertEqual(tuple(d["row"] for d in drift), STALE_ROWS)


if __name__ == "__main__":
    unittest.main()

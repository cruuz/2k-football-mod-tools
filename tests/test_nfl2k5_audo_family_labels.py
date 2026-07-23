"""Tests for the NFL 2K5 AUDO audible-equivalence family labeling tool."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl2k5_audo_family_labels as families  # noqa: E402

AUDIT = ROOT / "reports/assets/nfl2k5_audo_import_capacity.json"


@unittest.skipUnless(AUDIT.exists(), "pinned AUDO audit not present")
class FamilyLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = families.load_audit(AUDIT)
        cls.result = families.build_families(cls.audit)

    def test_schema_and_claims(self) -> None:
        self.assertEqual(self.result["schema"], families.SCHEMA)
        claims = self.result["claims"]
        self.assertTrue(claims["equal_pcm_means_equal_sound"])
        self.assertFalse(claims["equal_pcm_means_equal_runtime_trigger"])
        self.assertFalse(claims["runtime_ownership_proved"])

    def test_summary_is_deterministic(self) -> None:
        summary = self.result["summary"]
        self.assertEqual(summary["record_count"], 850)
        self.assertEqual(summary["equal_content_family_count"], 53)
        self.assertEqual(summary["multimember_family_count"], 53)
        self.assertEqual(summary["export_only_record_count"], 697)
        # Most export-only cues sit in multi-member byte-identical families...
        self.assertGreaterEqual(summary["export_only_in_multimember_family"], 690)
        # ...but only a few earn a confident headless label (equal sound is not
        # equal trigger; the large crowd families carry conflicting names).
        self.assertLessEqual(
            summary["export_only_with_confident_audible_label"],
            summary["export_only_in_multimember_family"])
        self.assertGreaterEqual(
            summary["largest_family_member_count"], 32)

    def test_every_family_member_resolves_to_a_record(self) -> None:
        keys = {rec["key"] for rec in self.audit["records"]}
        for family in self.result["families"]:
            self.assertEqual(family["member_count"], len(family["members"]))
            for member in family["members"]:
                self.assertIn(member, keys)

    def test_label_basis_is_one_of_known(self) -> None:
        bases = {f["label_basis"] for f in self.result["families"]}
        self.assertLessEqual(bases, {"consistent-name", "reviewed-sibling", "none"})

    def test_main_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "families.json"
            rc = families.main(["--audit", str(AUDIT), "--output", str(out)])
            self.assertEqual(rc, 0)
            written = json.loads(out.read_text())
            self.assertEqual(written["schema"], families.SCHEMA)
            # refuses to overwrite
            self.assertEqual(
                families.main(["--audit", str(AUDIT), "--output", str(out)]), 1)


if __name__ == "__main__":
    unittest.main()

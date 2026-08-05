"""Tests for the NFL 2K5 AUDO audible-equivalence family labeling tool."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl2k5_audo_family_labels as families  # noqa: E402

AUDIT = ROOT / "reports/assets/nfl2k5_audo_import_capacity.json"
TOOL = ROOT / "tools/nfl2k5_audo_family_labels.py"


@unittest.skipUnless(AUDIT.exists(), "pinned AUDO audit not present")
class FamilyLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = families.load_audit(AUDIT)
        cls.audit_sha256 = hashlib.sha256(AUDIT.read_bytes()).hexdigest()
        cls.result = families.build_families(
            cls.audit, source_audit_sha256=cls.audit_sha256
        )

    def test_schema_and_claims(self) -> None:
        self.assertEqual(self.result["schema"], families.SCHEMA)
        self.assertEqual(self.result["source_audit_sha256"], self.audit_sha256)
        claims = self.result["claims"]
        self.assertTrue(claims["equal_pcm_means_equal_sound"])
        self.assertFalse(claims["equal_pcm_means_equal_runtime_trigger"])
        self.assertTrue(claims["family_label_is_inference_not_runtime_proof"])
        self.assertFalse(claims["reviewed_labels_overwritten"])
        self.assertFalse(claims["runtime_ownership_proved"])

    def test_summary_is_deterministic(self) -> None:
        summary = self.result["summary"]
        self.assertEqual(summary["record_count"], 850)
        self.assertEqual(summary["reviewed_label_count"], 152)
        self.assertEqual(summary["proved_fixed_slot_count"], 1)
        self.assertEqual(summary["provisional_record_count"], 697)
        self.assertEqual(summary["equal_content_family_count"], 53)
        self.assertEqual(summary["equal_span_group_count"], 91)
        # Exactly one provisional cue currently decodes byte-identical to a
        # reviewed cue (the second physical menu-back_01); every other family
        # has no reviewed representative and stays provisional.
        self.assertEqual(summary["promoted_cue_count"], 1)
        self.assertEqual(summary["provisional_remaining_count"], 696)
        self.assertGreaterEqual(summary["largest_family_member_count"], 32)

    def test_every_family_member_resolves_to_a_record(self) -> None:
        keys = {rec["key"] for rec in self.audit["records"]}
        for family in self.result["families"]:
            self.assertEqual(family["member_count"], len(family["members"]))
            for member in family["members"]:
                self.assertIn(member, keys)

    def test_label_basis_is_one_of_known(self) -> None:
        bases = {f["label_basis"] for f in self.result["families"]}
        self.assertLessEqual(bases, {"reviewed-representative", "none"})
        for family in self.result["families"]:
            self.assertEqual(
                family["confident_audible_label"] is not None,
                family["label_basis"] == "reviewed-representative",
            )

    def test_promotions_never_touch_reviewed_labels(self) -> None:
        structural, proved_fixed = families.reviewed_keys(self.audit)
        reviewed = structural | proved_fixed
        records = {rec["key"]: rec for rec in self.audit["records"]}
        keys = set()
        for promotion in self.result["promotions"]:
            key = promotion["key"]
            keys.add(key)
            # Reviewed labels and the Menu Back proof are immutable.
            self.assertNotIn(key, reviewed)
            self.assertEqual(
                records[key]["classification"], families.PROVISIONAL_CLASSIFICATION
            )
            # The representative is reviewed and never the cue itself.
            representative = promotion["representative_key"]
            self.assertIn(representative, reviewed)
            self.assertNotEqual(representative, key)
            self.assertEqual(
                promotion["representative_name"], records[representative]["name"]
            )
            # The label text discloses the family inference.
            self.assertEqual(
                promotion["label"],
                families.FAMILY_LABEL_PREFIX + promotion["representative_name"],
            )
            self.assertEqual(
                promotion["confidence"], families.FAMILY_REVIEWED_CONFIDENCE
            )
            self.assertIn(
                promotion["group_kind"],
                {kind for kind, _groups, _hash in families.GROUP_KINDS},
            )
        self.assertEqual(len(keys), len(self.result["promotions"]))

    def test_promotions_follow_reviewed_representatives_only(self) -> None:
        # The 340-member oclapaa_01 crowd family has no reviewed member, so
        # none of its cues may be promoted headlessly.
        records = {rec["key"]: rec for rec in self.audit["records"]}
        oclapaa_keys = {
            rec["key"] for rec in records.values() if rec.get("name") == "oclapaa_01"
        }
        promoted_keys = {p["key"] for p in self.result["promotions"]}
        self.assertEqual(oclapaa_keys & promoted_keys, set())
        self.assertEqual(promoted_keys, {"outer_0009_chunk_0034"})
        promotion = self.result["promotions"][0]
        self.assertEqual(promotion["group_id"], "content:25fac3cc270e6a4c")
        self.assertEqual(promotion["representative_key"], "outer_0003_chunk_0101")

    def test_main_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "families.json"
            rc = families.main(["--audit", str(AUDIT), "--output", str(out)])
            self.assertEqual(rc, 0)
            written = json.loads(out.read_text())
            self.assertEqual(written["schema"], families.SCHEMA)
            self.assertEqual(written["source_audit_sha256"], self.audit_sha256)
            # refuses to overwrite
            self.assertEqual(
                families.main(["--audit", str(AUDIT), "--output", str(out)]), 1)

    def test_output_is_identical_across_python_hash_seeds(self) -> None:
        outputs = []
        for seed in ("0", "1", "42"):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "families.json"
                completed = subprocess.run(
                    [sys.executable, str(TOOL), "--audit", str(AUDIT),
                     "--output", str(out)],
                    capture_output=True,
                    text=True,
                    env={**os.environ, "PYTHONHASHSEED": seed},
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                outputs.append(out.read_bytes())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])


if __name__ == "__main__":
    unittest.main()

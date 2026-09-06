"""Observe actual owner writes without producing a 6 GB acceptance image."""
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career as c, nfl2k5_crib_reclaim as crib
from mod_editor.core.nfl2k5_cave_manifest import Recorder, source_fingerprints
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
from tests.nfl2k5_my_career_fixture import XBE
from tests import nfl2k5_allocator_stack as stack


class BudgetTests(unittest.TestCase):
    def test_actual_requests_match_budget_and_complete_gate_union(self):
        budget = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        rows = [tuple(row) for row in budget if row[0] == c.OWNER]
        self.assertEqual(rows, list(c.REQUESTS))
        self.assertTrue(set(c.REQUESTS).issubset(set(stack.REQUESTS)))
        c.space.plan(stack.REQUESTS)


@unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe is absent")
class ManifestTests(unittest.TestCase):
    def test_allocation_projection_keeps_retail_and_refuses_unknown_owners(self):
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            self.skipTest("retail XBE differs from USA evidence pin")
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(retail))
        allocated = c.space.apply(retail, stack.REQUESTS, scaleout=True)[0]
        allocated = stack.music.apply(allocated, song_records=stack.SONGS)[0]
        projected = stack.manifest_for_allocated_union(manifest, retail, allocated)
        old_retail = [s for s in manifest.document["spans"] if int(s["start"], 0) < c.space.CODE_VA]
        new_retail = [s for s in projected.document["spans"] if int(s["start"], 0) < c.space.CODE_VA]
        self.assertEqual(old_retail, new_retail)
        bad = dict(manifest.document)
        bad["spans"] = manifest.document["spans"] + [dict(start=hex(c.space.CODE_VA),
            end=hex(c.space.CODE_VA + 1), size=1, owner="foreign_owner", basis="foreign reservation")]
        with self.assertRaisesRegex(AssertionError, "unrecognized"):
            stack.manifest_for_allocated_union(ReservationManifest(bad, XbeImage(retail)), retail, allocated)

    def test_observed_sites_named_rx_rw_and_fingerprints(self):
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            self.skipTest("retail XBE differs from USA evidence pin")
        recorder = Recorder(retail)
        result = recorder.wrapper(c, "apply")(retail)[0]
        result = recorder.wrapper(crib, "apply")(result)[0]
        spans = recorder.finish(result)
        for module in (c, crib):
            self.assertTrue(any(s["owner"] == module.OWNER for s in spans))
        for allocation in c.allocations(result):
            self.assertTrue(any(int(s["start"], 0) == allocation["va"] and s["size"] == allocation["size"]
                                and s["owner"] == c.OWNER for s in spans))
        for _, va, *_ in c.HOOKS:
            self.assertTrue(any(int(s["start"], 0) <= va < int(s["end"], 0) for s in spans), hex(va))
        fingerprints = source_fingerprints()
        for name in ("nfl2k5_my_career.py", "nfl2k5_my_career_code.py", "nfl2k5_crib_reclaim.py"):
            self.assertIn("mod_editor/core/" + name, fingerprints)


if __name__ == "__main__":
    unittest.main()

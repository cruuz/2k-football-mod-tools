"""Bounded writer ownership proof. Never writes a disc or the release manifest.

The optional scratch projection inherits unchanged owners' recorded evidence
and observes this writer plus the complete new allocator union. It is explicitly
not evidence of a new production disc build; Claude must regenerate that file.
"""
from pathlib import Path
import copy
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_defensive_try as patch
from mod_editor.core import nfl2k5_cave_manifest as builder
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, OracleError, ReservationManifest, XbeImage
from tests.mod_editor.test_nfl2k5_defensive_try import XBE
from tests.nfl2k5_allocator_stack import REQUESTS


def bounded_projection(retail, document=None):
    parent = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8")) if document is None else document
    historical = ReservationManifest(parent, XbeImage(retail))
    fingerprints = builder.source_fingerprints()
    allowed = "mod_editor/core/nfl2k5_defensive_try.py"
    if not parent.get("source_sha256") or allowed not in parent["source_sha256"]:
        raise OracleError("projection requires the fingerprinted defensive-try parent manifest")
    for path, digest in parent["source_sha256"].items():
        if path != allowed and fingerprints.get(path) != digest:
            raise OracleError(f"unobserved source changed: {path}; regenerate the production manifest")
    for va, before, _ in {**patch.HOOKS, **patch.BRANCHES}.values():
        if historical.overlaps(va, va + len(bytes.fromhex(before)), exclude_owner=patch.OWNER):
            raise OracleError("new try hook collides with an existing owner")
    recorder = builder.Recorder(retail)
    allocated, receipt = space.apply(retail, REQUESTS, scaleout=True)
    recorder.observe(space, "apply", retail, allocated, receipt)
    final, receipt = patch.apply(allocated)
    recorder.observe(patch, "apply", allocated, final, receipt)
    observed = recorder.finish(final)
    layout = space.layout(final)
    known = {space.OWNER, "nfl2k5_xbe_space_directory"} | {a["owner"] for a in layout["allocations"]}
    inherited = []
    for row in parent["spans"]:
        start, end = int(row["start"], 0), int(row["end"], 0)
        regions = [r for r in layout["regions"] if start < r["va"] + r["size"] and r["va"] < end]
        if regions:
            covered = start
            for region in sorted(regions, key=lambda r: r["va"]):
                if region["va"] <= covered:
                    covered = max(covered, region["va"] + region["size"])
            if row["owner"] not in known or covered < end:
                raise OracleError(f"unrecognized inherited grown reservation: {row}")
            # Replace old named addresses with freshly observed complete union.
        else:
            inherited.append(row)
    unique = {(r["start"], r["end"], r["owner"], r["basis"]): r for r in inherited + observed}
    result = copy.deepcopy(parent)
    result.update(model="BOUNDED XBE PROJECTION: unchanged parent reservations plus observed defensive try and complete allocator union; no new disc build",
                  stack_image_size=XbeImage(final).image_size,
                  spans=sorted(unique.values(), key=lambda r: (int(r["start"], 0), int(r["end"], 0), r["owner"])))
    result["source_sha256"][allowed] = fingerprints[allowed]
    result["bounded_projection"] = dict(parent_document_sha256=hashlib.sha256(json.dumps(parent, sort_keys=True).encode()).hexdigest(),
                                        observed_steps=recorder.steps, observed_source=allowed,
                                        inherited_image_steps=True, real_disc_build=False,
                                        production_regeneration_required=True, runtime_witnessed=False)
    ReservationManifest(result, XbeImage(retail), source_root=ROOT)
    return final, result


@unittest.skipUnless(XBE.is_file(), "private USA retail XBE absent; ownership proof requires pinned executable")
class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.final, cls.document = bounded_projection(cls.retail)

    def test_every_hook_and_all_four_children_are_recorded(self):
        rows = self.document["spans"]
        for label, (va, before, _) in {**patch.HOOKS, **patch.BRANCHES}.items():
            self.assertTrue(any(r["owner"] == patch.OWNER and int(r["start"], 0) <= va
                                and va + len(bytes.fromhex(before)) <= int(r["end"], 0) for r in rows), label)
        for site in (*patch._sites(self.final), *patch._stats_sites(self.final)):
            self.assertTrue(any(r["owner"] == site["owner"] and int(r["start"], 0) == site["va"]
                                and r["size"] == site["size"] for r in rows), site)
        self.assertFalse(self.document["bounded_projection"]["real_disc_build"])

    def test_unrelated_source_drift_cannot_be_recertified(self):
        parent = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        parent["source_sha256"]["mod_editor/core/nfl2k5_team_column.py"] = "0" * 64
        with self.assertRaisesRegex(OracleError, "unobserved source changed"):
            bounded_projection(self.retail, parent)
        broken = copy.deepcopy(self.document)
        broken["source_sha256"]["mod_editor/core/nfl2k5_defensive_try.py"] = "0" * 64
        with self.assertRaisesRegex(OracleError, "stale reservation source"):
            ReservationManifest(broken, XbeImage(self.retail), source_root=ROOT)

    def test_builder_owns_extension_through_the_existing_flag(self):
        import ast
        tree = ast.parse(Path(builder.__file__).read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_manifest")
        for attribute in ("REQUESTS", "apply"):
            self.assertTrue(any(isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                                and n.value.id == "defensive_try" and n.attr == attribute for n in ast.walk(function)))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--write-projection":
        target = Path(sys.argv[2]).resolve()
        if not target.is_relative_to((ROOT / ".scratch").resolve()):
            raise SystemExit("test projection output must be inside this worktree's .scratch")
        _, document = bounded_projection(XBE.read_bytes())
        target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote bounded projection, not a new disc-build manifest: {target}")
    else:
        unittest.main()

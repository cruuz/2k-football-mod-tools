"""Bounded writer ownership proof; no disc or protected-manifest writes.

Unchanged parent source fingerprints retain their historical reservations.
The actual allocator and screen-hook writes are observed on a 12 MiB XBE.
The optional scratch projection is explicitly NOT a new production disc build.
"""
from pathlib import Path
import ast
import copy
import hashlib
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_screen_hooks as patch
from mod_editor.core import nfl2k5_cave_manifest as builder
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, OracleError, ReservationManifest, XbeImage
from tests.mod_editor.test_nfl2k5_screen_hooks import retail_xbe
from tests.nfl2k5_allocator_stack import REQUESTS

OBSERVED_SOURCES = (
    "mod_editor/core/nfl2k5_screen_hooks.py",
    "mod_editor/core/nfl2k5_screen_hooks_code.py",
    "tools/nfl2k5_screen_hooks_assemble.py",
)


def parent_document():
    # Accept independently observed current XBE evidence just like both gates.
    # Source fingerprint validation remains mandatory in bounded_projection.
    path = Path(os.environ.get("NFL2K5_CAVE_MANIFEST", DEFAULT_MANIFEST))
    return json.loads(path.read_text(encoding="utf-8"))


def bounded_projection(retail, document=None):
    parent = parent_document() if document is None else document
    historical = ReservationManifest(parent, XbeImage(retail), source_root=ROOT)
    fingerprints = builder.source_fingerprints()
    # Never refresh historical evidence to bless an unobserved changed writer.
    for path, digest in parent["source_sha256"].items():
        if fingerprints.get(path) != digest:
            raise OracleError(f"unobserved source changed: {path}; regenerate production manifest")
    for va, before in patch.HOOKS.values():
        if historical.overlaps(va, va+len(before), exclude_owner=patch.OWNER):
            raise OracleError("screen hook collides with an existing owner")
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
        regions = [r for r in layout["regions"] if start < r["va"]+r["size"] and r["va"] < end]
        if regions:
            covered = start
            for region in sorted(regions, key=lambda r: r["va"]):
                if region["va"] <= covered:
                    covered = max(covered, region["va"]+region["size"])
            if row["owner"] not in known or covered < end:
                raise OracleError(f"unrecognized inherited grown reservation: {row}")
        else:
            inherited.append(row)
    unique = {(r["start"], r["end"], r["owner"], r["basis"]): r for r in inherited+observed}
    result = copy.deepcopy(parent)
    result.update(model="BOUNDED XBE PROJECTION: unchanged parent reservations plus observed screen hooks and allocator union; no new disc build",
                  stack_image_size=XbeImage(final).image_size,
                  spans=sorted(unique.values(), key=lambda r: (int(r["start"], 0), int(r["end"], 0), r["owner"])))
    result["source_sha256"].update({path: fingerprints[path] for path in OBSERVED_SOURCES})
    result["bounded_projection"] = dict(parent_document_sha256=hashlib.sha256(json.dumps(parent, sort_keys=True).encode()).hexdigest(),
                                        observed_steps=recorder.steps, observed_sources=OBSERVED_SOURCES,
                                        inherited_image_steps=True, real_disc_build=False,
                                        production_regeneration_required=True, runtime_witnessed=False)
    ReservationManifest(result, XbeImage(retail), source_root=ROOT)
    return final, result


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.document = bounded_projection(cls.retail)

    def test_both_hooks_and_complete_child_are_recorded(self):
        rows = self.document["spans"]
        for va, before in patch.HOOKS.values():
            self.assertTrue(any(r["owner"] == patch.OWNER and int(r["start"], 0) <= va
                                and va+len(before) <= int(r["end"], 0) for r in rows))
        code = patch.allocation(self.final)
        self.assertTrue(any(r["owner"] == patch.OWNER and int(r["start"], 0) == code["va"]
                            and r["size"] == code["size"] for r in rows))
        self.assertFalse(self.document["bounded_projection"]["real_disc_build"])
        self.assertEqual([s["owner"] for s in self.document["bounded_projection"]["observed_steps"]], [space.OWNER, patch.OWNER])

    def test_unobserved_source_drift_cannot_be_recertified(self):
        parent = parent_document()
        parent["source_sha256"]["mod_editor/core/nfl2k5_team_column.py"] = "0"*64
        with self.assertRaisesRegex(OracleError, "stale reservation source|unobserved source"):
            bounded_projection(self.retail, parent)
        broken = copy.deepcopy(self.document)
        broken["source_sha256"][OBSERVED_SOURCES[0]] = "0"*64
        with self.assertRaisesRegex(OracleError, "stale reservation source"):
            ReservationManifest(broken, XbeImage(self.retail), source_root=ROOT)

    def test_builder_request_observation_install_replay_and_metadata_membership(self):
        tree = ast.parse(Path(builder.__file__).read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_manifest")
        attrs = [n.attr for n in ast.walk(function) if isinstance(n, ast.Attribute)
                 and isinstance(n.value, ast.Name) and n.value.id == "screen_hooks"]
        self.assertTrue({"REQUESTS", "apply", "OWNER"}.issubset(attrs))
        tuples = [n for n in ast.walk(function) if isinstance(n, ast.Tuple)
                  and any(isinstance(item, ast.Name) and item.id == "screen_hooks" for item in n.elts)]
        self.assertGreaterEqual(len(tuples), 3)  # wrapper registry, synthetic probe, status list


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--write-projection":
        target = Path(sys.argv[2]).resolve()
        if not target.is_relative_to((ROOT / ".scratch").resolve()):
            raise SystemExit("projection output must be inside this worktree's .scratch")
        _, document = bounded_projection(retail_xbe())
        target.write_text(json.dumps(document, indent=2)+"\n", encoding="utf-8")
        print(f"Wrote bounded projection, not a disc-build manifest: {target}")
    else:
        unittest.main()

"""b780-b13 (b779 R2 MINOR 6): the cave reservation manifest covers the champions owner's two live call sites.

The Super Bowl champions owner is installed INSIDE the honors owner (honors.apply calls champions.install) and rewrites two
retail ``call rel32`` sites: the stage advance at 0x2485FA and the season awards at 0x116E55. The first byte of each call
(0xE8) never changes, so a byte diff cannot see the sites, and the recorder only wrapped apply-style functions, so no step had
the owner nfl2k5_champions: the manifest held nothing at 0x2485FA / 0x116E55 and nothing would flag a later owner that reused
those two live sites. The recorder now observes champions.install as its own step; the committed manifest was regenerated from
the real observed preset build (stopped after the honors step).
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_cave_manifest as model  # noqa: E402
from mod_editor.core import nfl2k5_champions as champions  # noqa: E402
from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import (  # noqa: E402
    DEFAULT_MANIFEST, RETAIL_SHA256, CaveOracle, OracleError, ReservationManifest, XbeImage,
)

MANIFEST = Path(os.environ.get("NFL2K5_CAVE_MANIFEST", str(DEFAULT_MANIFEST)))
XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
SITES = [(label, va, length) for label, va, _before, _entry, _opcode, length in champions.SITE_TABLE]
assert SITES == [("stage_advance", 0x2485FA, 5), ("season_awards", 0x116E55, 5)]


def _retail() -> bytes:
    """The pinned retail XBE, or a skip. Raised as SkipTest because setUpClass has no test instance to call skipTest on."""
    if not XBE.is_file():
        raise unittest.SkipTest(f"private USA retail default.xbe absent: {XBE}; set NFL2K5_RETAIL_EXTRACTION")
    data = XBE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == RETAIL_SHA256, "private retail XBE has unexpected identity"
    return data


class ManifestModelWiring(unittest.TestCase):
    """Retail-free: the manifest model wraps the champions install."""

    def test_build_manifest_observes_the_champions_install_as_its_own_step(self):
        source = inspect.getsource(model.build_manifest)
        self.assertIn("from . import nfl2k5_champions as champions", source)
        self.assertIn('patch.object(champions, "install", recorder.wrapper(champions, "install"))', source)
        # inside the same ExitStack as the other wrapped writers, before the observed build runs
        self.assertLess(source.index('patch.object(champions, "install"'), source.index("receipt = build.build(plan"))
        self.assertLess(source.index("recorder.wrapper(module, name)"), source.index('patch.object(champions, "install"'))

    def test_install_is_wrapped_for_the_one_module_not_by_name_for_every_module(self):
        # other modules have their own unrelated install() functions; the generic name list must not gain it
        source = inspect.getsource(model.build_manifest)
        names = source[source.index('for name in ("apply", "apply_xbe"'):].split("):")[0]
        self.assertNotIn("install", names)
        self.assertEqual(source.count('"install"'), 2)       # the patch.object target and the wrapper's function name


class RecorderOnRetail(unittest.TestCase):
    """The recorder on the real retail executable: honors.apply installs the champions owner."""

    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()

    def _record(self, *, wrap_champions: bool):
        recorder = model.Recorder(self.retail)
        with patch.object(honors, "apply", recorder.wrapper(honors, "apply")):
            if wrap_champions:
                with patch.object(champions, "install", recorder.wrapper(champions, "install")):
                    result = honors.apply(self.retail)
            else:
                result = honors.apply(self.retail)
        return recorder, result

    def test_without_the_wrapper_nothing_reserves_the_two_call_opcode_bytes(self):
        # The bug: the E8 opcode byte of each call is retail, so no byte diff and no declared edit ever covered it.
        recorder, _result = self._record(wrap_champions=False)
        for _label, va, _length in SITES:
            self.assertFalse([s for s in recorder.spans if int(s["start"], 0) <= va < int(s["end"], 0)], hex(va))
        self.assertEqual([s["owner"] for s in recorder.steps], ["nfl2k5_honors"])

    def test_with_the_wrapper_the_champions_step_reserves_both_complete_sites(self):
        recorder, (payload, _receipt) = self._record(wrap_champions=True)
        self.assertEqual([(s["owner"], s["function"]) for s in recorder.steps],
                         [("nfl2k5_champions", "install"), ("nfl2k5_honors", "apply")])   # the inner install finishes first
        champion, honor = recorder.steps
        self.assertEqual(champion["after_sha256"], honor["after_sha256"])                   # honors returns champions' output
        self.assertEqual(hashlib.sha256(payload).hexdigest(), honor["after_sha256"])
        ranges = [(int(a, 0), int(b, 0)) for a, b in honor["file_runs"]]
        for a, b in ((int(a, 0), int(b, 0)) for a, b in champion["file_runs"]):
            self.assertTrue(any(lo <= a and b <= hi for lo, hi in ranges))                  # honors' diff contains champions'
        declared = {(int(s["start"], 0), int(s["end"], 0), s["basis"]) for s in recorder.spans
                    if s["owner"] == "nfl2k5_champions" and s["basis"].startswith("declared edit:")}
        self.assertEqual(declared, {(va, va + length, "declared edit: " + label) for label, va, length in SITES})
        # the two rewritten call operands are observed too, and the retail opcode byte of each call lies in the declared span
        image = XbeImage(payload)
        retail_image = XbeImage(self.retail)
        for _label, va, _length in SITES:
            self.assertEqual(image.read(va, 1), retail_image.read(va, 1))                   # the E8 byte itself never changes
            self.assertEqual(image.read(va, 1), b"\xe8")
            self.assertNotEqual(image.read(va + 1, 4), retail_image.read(va + 1, 4))


@unittest.skipUnless(MANIFEST.is_file(), "the committed cave manifest is part of the checkout")
class CommittedManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_both_call_sites_are_declared_spans_of_the_champions_owner(self):
        spans = {(int(s["start"], 0), int(s["end"], 0), s["basis"]) for s in self.document["spans"]
                 if s["owner"] == "nfl2k5_champions"}
        for label, va, length in SITES:
            self.assertIn((va, va + length, "declared edit: " + label), spans)

    def test_the_champions_install_is_a_recorded_step_right_before_the_honors_step(self):
        steps = self.document["steps"]
        owners = [s["owner"] for s in steps]
        index = owners.index("nfl2k5_champions")
        self.assertEqual((steps[index]["function"], owners[index + 1]), ("install", "nfl2k5_honors"))
        self.assertEqual(owners.count("nfl2k5_champions"), 1)
        self.assertEqual(steps[index]["after_sha256"], steps[index + 1]["after_sha256"])
        self.assertGreater(steps[index]["changed_bytes"], 0)

    def test_the_named_code_allocation_is_still_reserved_and_the_honors_sites_are_untouched(self):
        rows = [s for s in self.document["spans"] if s["owner"] == "nfl2k5_champions"]
        self.assertEqual([r["size"] for r in rows if r["basis"] == "named code allocation"], [champions.CODE_SIZE])
        honors_declared = {s["basis"] for s in self.document["spans"] if s["owner"] == "nfl2k5_honors"
                           and s["basis"].startswith("declared edit:")}
        self.assertEqual(honors_declared, {"declared edit: " + site[0] for site in honors.SITE_TABLE})

    def test_spans_stay_sorted_unique_and_free_of_private_paths(self):
        spans = self.document["spans"]
        key = lambda s: (int(s["start"], 0), int(s["end"], 0), s["owner"], s["basis"])
        self.assertEqual(spans, sorted(spans, key=key))
        self.assertEqual(len({key(s) for s in spans}), len(spans))
        self.assertNotIn("/home/", MANIFEST.read_text(encoding="utf-8"))
        self.assertNotIn("/media/", MANIFEST.read_text(encoding="utf-8"))


class OracleSeesTheSites(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import capstone  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest("cave analysis requires capstone; install tools/requirements-nfl2k5-cave-oracle.txt") from exc
        cls.retail = _retail()

    def test_the_oracle_refuses_a_later_owner_that_reuses_either_live_site(self):
        manifest = ReservationManifest.load(MANIFEST, XbeImage(self.retail), source_root=ROOT)
        oracle = CaveOracle(self.retail, manifest=manifest, instruction_budget=1, reference_budget=1)
        for label, va, length in SITES:
            for byte in range(va, va + length):
                row = oracle.assess(byte, 1)
                self.assertEqual(row["verdict"], "reserved", (label, hex(byte)))
            row = oracle.assess(va, length)
            self.assertEqual(row["verdict"], "reserved")
            self.assertFalse(row["allocatable"])
            self.assertTrue(any(e["detail"].startswith("nfl2k5_champions: declared edit: " + label) for e in row["witnesses"]),
                            (label, row["witnesses"]))
            with self.assertRaises(OracleError):
                oracle.require_cave(va, length)
            # the span of the champions owner is what protects the retail E8 opcode byte (the honors operand spans start after it)
            self.assertNotEqual(oracle.assess(va, 1, exclude_owner="nfl2k5_champions")["verdict"], "reserved")


if __name__ == "__main__":
    unittest.main()

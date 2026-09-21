"""Beta 74: the preset build path reads the source once and the output once.

Beta 73's "Hashing the verified disc" stage measured the outcome by hashing
the SOURCE and the output after every build, a second 6 GB read of the source
on top of the copy. The copy now hashes the source as it reads it (build_io
and write_copy), and the outcome compares that digest with one read of the
output. Synthetic disc only; no retail bytes.
"""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(Path(__file__).parent)]
from mod_editor.core import mod_build, build_io, build_feedback
from test_mod_build_performance import synthetic_disc, SyntheticProject


class PresetPassTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="b74-preset-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "retail.iso"
        synthetic_disc(self.source)
        self.original = self.source.read_bytes()

    def digests(self):
        calls = []
        real = build_feedback._digest

        def counting(path):
            calls.append(Path(path).name)
            return real(path)

        return calls, mock.patch.object(build_feedback, "_digest", side_effect=counting)

    def test_plain_copy_hashes_the_source_while_copying_and_the_output_once(self):
        target = self.root / "copy.iso"
        calls, counting = self.digests()
        with counting, mock.patch.object(mod_build, "inspect", return_value={}):
            receipt = mod_build.build(mod_build.BuildPlan(str(self.source), str(target)))
        self.assertEqual(receipt["source_sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(calls, [target.name], "only the output is read for the outcome")
        self.assertEqual(receipt["outcome"]["status"], "unchanged")
        self.assertEqual(receipt["outcome"]["source"]["sha256"], receipt["source_sha256"])
        self.assertEqual(target.read_bytes(), self.original)

    def test_xbe_patch_copy_hashes_the_source_while_copying(self):
        target = self.root / "patched.iso"
        calls, counting = self.digests()
        plan = mod_build.BuildPlan(str(self.source), str(target), throw=True, max_deep_yards=80,
                                   catch_slider=True, accel_ramp=True, draft_ai=True, returner_fix=True)
        with counting:
            receipt = mod_build.build(plan)
        self.assertEqual(receipt["source_sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(calls, [target.name])
        self.assertEqual(receipt["outcome"]["status"], "changed")
        self.assertEqual(receipt["outcome"]["source"]["sha256"], receipt["source_sha256"])
        self.assertEqual(receipt["outcome"]["output"]["sha256"], hashlib.sha256(target.read_bytes()).hexdigest())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_project_build_keeps_the_builder_source_hash(self):
        target = self.root / "project.iso"
        service = SyntheticProject(self.source)
        calls, counting = self.digests()
        with counting, mock.patch.object(mod_build, "inspect", return_value={}):
            receipt = mod_build.build_with_project(mod_build.BuildPlan(str(self.source), str(target)),
                                                   service, None, None)
        self.assertEqual(calls, [target.name])
        self.assertEqual(receipt["outcome"]["source"]["sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(receipt["outcome"]["status"], "changed")

    def test_copy_descriptors_feeds_every_source_byte_to_the_hasher(self):
        payload = bytes(range(256)) * 40000  # 10 MB, past one 8 MB chunk
        source, target = self.root / "in.bin", self.root / "out.bin"
        source.write_bytes(payload)
        hasher = hashlib.sha256()
        with mock.patch.object(build_io.platform_compat, "copy_file_range",
                               side_effect=AssertionError("the hashing copy must not use copy_file_range")):
            copied = build_io.copy_image(source, target, None, hasher)
        self.assertEqual(copied, len(payload))
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(hasher.hexdigest(), hashlib.sha256(payload).hexdigest())

    def test_timing_summary_names_the_slowest_stages(self):
        line = build_feedback.timing_summary({"builder": 41.2, "verify": 12.0, "publish": 0.01,
                                              "materialization": 0.4, "Copying the image": 75.0})
        self.assertTrue(line.startswith("Time: 2 min 8 s ("), line)
        self.assertIn("Copying the image 1 min 15 s, builder 41 s, verify 12 s, materialization 0.4 s", line)
        self.assertNotIn("publish", line)
        self.assertEqual(build_feedback.timing_summary(None), "")
        self.assertEqual(build_feedback.timing_summary({}), "")


if __name__ == "__main__":
    unittest.main()

"""Beta 74: the number of full-disc passes a build makes is pinned.

A beta 73 tester's "gameplay fix" build took thirty minutes on a laptop drive
where beta 66 took under a minute: the builder copied the disc, wrote the
spans, then read both files again to hash and compare them, and its verifier
read both files again, so a 6 GB disc moved seven times before publication.
Beta 74 folds the hashes into the copy: the builder reads the source once and
writes the output once; the verifier reads the output once. This gate counts
the bytes that pass through the positional readers and writers on the real
backend over the synthetic b661 source, so a new option cannot bring a pass
back without failing here. Synthetic inputs only; no retail bytes.
"""

import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).parent)]

#: Small reads a pass legitimately makes beside the disc: the XDVDFS sectors,
#: default.xbe (a few hundred KB on the synthetic disc, 2.6 MB on retail) and
#: the selected spans, read from both files.
SLACK = 4 * 1024 * 1024


def load_backend():
    spec = importlib.util.spec_from_file_location(
        "_b74_speed_gate_visual_mod_project", ROOT / "tools/nfl2k5_visual_mod_project.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Meter:
    """Bytes through every positional reader/writer the backend uses."""

    def __init__(self, tool):
        self.tool = tool
        self.read = self.written = 0
        self.full_reads = 0

    def __enter__(self):
        tool = self.tool
        self.size = None
        real = {("platform_compat", "pread"): tool.platform_compat.pread,
                ("common", "pread"): tool.common.pread,
                ("platform_compat", "pwrite"): tool.platform_compat.pwrite,
                ("common", "pwrite"): tool.common.pwrite}

        def reader(original):
            def pread(descriptor, count, offset):
                data = original(descriptor, count, offset)
                self.read += len(data)
                return data
            return pread

        def writer(original):
            def pwrite(descriptor, data, offset):
                count = original(descriptor, data, offset)
                self.written += count
                return count
            return pwrite

        self.patches = [
            mock.patch.object(tool.platform_compat, "pread", reader(real[("platform_compat", "pread")])),
            mock.patch.object(tool.common, "pread", reader(real[("common", "pread")])),
            mock.patch.object(tool.platform_compat, "pwrite", writer(real[("platform_compat", "pwrite")])),
            mock.patch.object(tool.common, "pwrite", writer(real[("common", "pwrite")])),
        ]
        for patch in self.patches:
            patch.start()
        return self

    def __exit__(self, *exc):
        for patch in self.patches:
            patch.stop()
        return False


class FullDiscPassGate(unittest.TestCase):
    def setUp(self):
        import b661_build_fixture as fixture

        self.temporary = tempfile.TemporaryDirectory(prefix="b74-speed-")
        self.addCleanup(self.temporary.cleanup)
        self.root = root = Path(self.temporary.name).resolve()
        equipment, _ = fixture.create(root)
        self.tool = tool = load_backend()
        fixture.configure(tool, root)
        asset, png = equipment.png(independent=False, rgba=bytes((20, 150, 80, 255)) * 1024)
        self.project = root / "project.json"
        self.project.write_bytes(tool.canonical_json(dict(
            schema=tool.SCHEMA, purpose="74 speed gate",
            edits=[dict(kind=tool.UNIFORM_EQUIPMENT_KIND, asset_id=asset, png=str(png))])))
        self.source = root / "source.iso"
        self.output = root / "out.iso"
        self.manifest = root / "manifest.json"
        self.artifacts = root / "artifacts"
        self.size = self.source.stat().st_size

    def test_build_reads_the_source_once_and_writes_the_output_once(self):
        with Meter(self.tool) as meter, redirect_stdout(io.StringIO()):
            result = self.tool.build(self.project, self.source, self.output, self.manifest,
                                     self.artifacts, self.root / "0", self.root / "inventory.json")
        self.assertEqual(result["output"]["copy_method"], "pread_pwrite")
        self.assertEqual(result["output"]["xiso_sha256"], self.tool.file_digest(self.output))
        self.assertEqual(result["source"]["sha256_before"], self.tool.file_digest(self.source))
        self.assertEqual(result["source"]["sha256_after"], result["source"]["sha256_before"])
        self.assertLessEqual(meter.read, self.size + SLACK, "the build read the disc more than once")
        self.assertLessEqual(meter.written, self.size + SLACK, "the build wrote the disc more than once")
        self.assertGreaterEqual(meter.read, self.size)
        self.assertGreaterEqual(meter.written, self.size)
        self.assertTrue(result["patch"]["all_bytes_outside_selected_spans_identical"])
        self.assertEqual(result["patch"]["span_count"], 1)

    def test_receipt_verify_reads_the_output_once_and_the_source_not_at_all(self):
        with redirect_stdout(io.StringIO()):
            self.tool.build(self.project, self.source, self.output, self.manifest,
                            self.artifacts, self.root / "0", self.root / "inventory.json")
        receipt = self.tool.file_digest(self.manifest)
        with Meter(self.tool) as meter:
            verified = self.tool.verify_written(self.project, self.source, self.output,
                                                self.manifest, self.artifacts, receipt)
        self.assertTrue(verified["written_spans_verified"])
        self.assertLessEqual(meter.read, self.size + SLACK, "the verifier read more than one disc")
        self.assertGreaterEqual(meter.read, self.size, "the verifier must hash the whole output")
        self.assertEqual(meter.written, 0)

    def test_historical_verify_reads_each_disc_once(self):
        with redirect_stdout(io.StringIO()):
            self.tool.build(self.project, self.source, self.output, self.manifest,
                            self.artifacts, self.root / "0", self.root / "inventory.json")
        with Meter(self.tool) as meter, redirect_stdout(io.StringIO()):
            verified = self.tool.verify(self.project, self.source, self.output, self.manifest,
                                        self.artifacts, self.root / "0", self.root / "inventory.json")
        self.assertTrue(verified.get("union_spans_reconstructed_from_pinned_importers", True))
        self.assertLessEqual(meter.read, 2 * self.size + SLACK,
                             "a historical verify reads the source and the output once each")
        self.assertEqual(meter.written, 0)

    def test_folded_copy_matches_the_span_by_span_union(self):
        """The one-pass ledger equals the historical two-file union pass, byte for byte."""
        with redirect_stdout(io.StringIO()):
            result = self.tool.build(self.project, self.source, self.output, self.manifest,
                                     self.artifacts, self.root / "0", self.root / "inventory.json")
        tool = self.tool
        import os
        source_fd = os.open(self.source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        output_fd = os.open(self.output, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            project = tool.read_project(self.project)
            reports = tool.pin_reports({edit["kind"] for edit in project.value["edits"]})
            index_pin = tool.ownership.pin_large_file(self.root / "0", "canonical extracted pack 0",
                                                      tool.INDEX_SIZE, tool.INDEX_SHA256)
            inventory_pin = tool.ownership.pin_large_file(self.root / "inventory.json", "canonical chunk inventory",
                                                          tool.INVENTORY_SIZE, tool.INVENTORY_SHA256)
            entries, _ = tool.common.parse_xdvdfs(source_fd, self.size)
            with redirect_stdout(io.StringIO()):
                prepared = tool.prepare_project(project, index_pin, inventory_pin, reports, self.root,
                                                source_fd, entries, None, None, None, use_compile_cache=False)
            tool.bind_prepared_to_source(prepared, source_fd, entries)
            union = tool.verify_union(source_fd, output_fd, self.size, prepared.edits)
            self.assertEqual(union, result["patch"])
            os.close(index_pin.descriptor)
            os.close(inventory_pin.descriptor)
            tool.ownership.cleanup_owned(prepared.temp_files, [prepared.temp_root])
        finally:
            os.close(source_fd)
            os.close(output_fd)


if __name__ == "__main__":
    unittest.main()

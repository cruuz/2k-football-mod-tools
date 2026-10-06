from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("u1_repair", ROOT / "tools/b765/u1_repair.py")
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)


class UniformRepairSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.replacement = self.base / "fixed.bin"
        self.replacement.write_bytes(b"XY")
        self.patch = {"offset": 2, "length": 2, "before_sha256": u.sha(b"cd"),
                      "after_sha256": u.sha(b"XY"), "replacement": "fixed.bin"}

    def test_composes_with_other_jobs_and_is_idempotent(self):
        # Another job's unrelated edit is accepted and preserved.
        after, receipt = u.apply_spans(b"Zbcdef", [self.patch], self.base)
        self.assertEqual(after, b"ZbXYef")
        self.assertTrue(receipt["outside_scope_identical"])
        again, second = u.apply_spans(after, [self.patch], self.base)
        self.assertEqual(again, after)
        self.assertTrue(second["spans"][0]["already_applied"])

    def test_refuses_foreign_owned_bytes(self):
        with self.assertRaisesRegex(ValueError, "unexpected input"):
            u.apply_spans(b"abQdef", [self.patch], self.base)

    def test_refuses_changed_replacement_hash_or_size(self):
        for replacement in (b"ZZ", b"XYZ"):
            self.replacement.write_bytes(replacement)
            with self.assertRaisesRegex(ValueError, "size/hash changed"):
                u.apply_spans(b"abcdef", [self.patch], self.base)

    def test_refuses_overlap_negative_and_out_of_bounds_spans(self):
        for patches in ([self.patch, self.patch],
                        [dict(self.patch, offset=-1)],
                        [dict(self.patch, offset=5)],
                        [dict(self.patch, length=0)]):
            with self.assertRaises(ValueError):
                u.apply_spans(b"abcdef", patches, self.base)

    def test_validates_whole_batch_before_publishing(self):
        source, output = self.base / "in", self.base / "out"
        source.mkdir()
        (source / "16H0.IFF").write_bytes(b"abcdef")
        (source / "16A0.IFF").write_bytes(b"abZZef")
        manifest = {"resources": {"16H0.IFF": [self.patch], "16A0.IFF": [self.patch]}}
        with self.assertRaises(ValueError):
            u.repair_resources(source, output, manifest, self.base)
        self.assertFalse(output.exists())

    def test_resource_output_readback_and_full_receipt(self):
        source, output = self.base / "in", self.base / "out"
        source.mkdir()
        (source / "16H0.IFF").write_bytes(b"abcdef")
        receipt = u.repair_resources(source, output,
                                     {"resources": {"16H0.IFF": [self.patch]}}, self.base)
        self.assertEqual((output / "16H0.IFF").read_bytes(), b"abXYef")
        self.assertTrue(receipt["resources"]["16H0.IFF"]["readback"])
        self.assertEqual(receipt["resources"]["16H0.IFF"]["before_sha256"], u.sha(b"abcdef"))

    def test_refuses_traversal_and_source_alias(self):
        source = self.base / "in"
        source.mkdir()
        for destination, manifest in ((source, {"resources": {}}),
                                      (self.base / "out", {"resources": {"../16H0.IFF": [self.patch]}})):
            with self.assertRaises(ValueError):
                u.repair_resources(source, destination, manifest, self.base)

    def test_replacement_paths_cannot_escape_manifest_directory(self):
        outside = self.base.parent / (self.base.name + "-outside.bin")
        outside.write_bytes(b"XY")
        self.addCleanup(outside.unlink, missing_ok=True)
        for replacement in (str(outside), "../" + outside.name):
            with self.assertRaisesRegex(ValueError, "escapes"):
                u.apply_spans(b"abcdef", [dict(self.patch,replacement=replacement)],self.base)

    def test_symlinked_replacement_directory_is_refused(self):
        link = self.base / "linked"
        try:
            link.symlink_to(self.base,target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError,"symlink"):
            u.apply_spans(b"abcdef",[dict(self.patch,replacement="linked/fixed.bin")],self.base)

    def test_later_output_symlink_does_not_publish_earlier_file(self):
        output = self.base / "out"
        output.mkdir()
        other = self.base / "other.bin"
        other.write_bytes(b"preserve")
        try:
            (output / "b").symlink_to(other)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError,"symlink"):
            u.publish_batch([(output/"a",b"new"),(output/"b",b"other")])
        self.assertFalse((output/"a").exists())
        self.assertEqual(other.read_bytes(),b"preserve")

    def test_existing_different_output_is_preserved(self):
        output = self.base / "out"
        output.mkdir()
        (output/"b").write_bytes(b"other job")
        with self.assertRaisesRegex(ValueError,"existing output differs"):
            u.publish_batch([(output/"a",b"new"),(output/"b",b"replacement")])
        self.assertFalse((output/"a").exists())
        self.assertEqual((output/"b").read_bytes(),b"other job")

    def test_later_staging_collision_is_refused_before_publishing(self):
        output = self.base / "out"
        output.mkdir()
        (output/"b.u1-tmp").write_bytes(b"other job")
        with self.assertRaisesRegex(ValueError,"staging file"):
            u.publish_batch([(output/"a",b"new"),(output/"b",b"new")])
        self.assertFalse((output/"a").exists())
        self.assertEqual((output/"b.u1-tmp").read_bytes(),b"other job")

    def test_commit_failure_rolls_back_only_own_outputs(self):
        output = self.base / "out"
        output.mkdir()
        old = output/"old"
        old.write_bytes(b"existing identical")
        original_link = u.os.link
        count = 0
        def fail_second(src,dst):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("injected commit failure")
            return original_link(src,dst)
        with mock.patch.object(u.os,"link",side_effect=fail_second):
            with self.assertRaisesRegex(OSError,"commit failure"):
                u.publish_batch([(old,b"existing identical"),(output/"a",b"new"),(output/"b",b"new")])
        self.assertEqual(old.read_bytes(),b"existing identical")
        self.assertFalse((output/"a").exists())
        self.assertFalse((output/"b").exists())
        self.assertFalse(list(output.glob("*.u1-tmp")))

    def test_resource_batch_is_idempotent_and_preserves_unowned_files(self):
        source,output = self.base/"in",self.base/"out"
        source.mkdir();output.mkdir()
        (source/"16H0.IFF").write_bytes(b"abcdef")
        (output/"other-job.txt").write_bytes(b"keep")
        manifest = {"resources":{"16H0.IFF":[self.patch]}}
        first = u.repair_resources(source,output,manifest,self.base)
        second = u.repair_resources(source,output,manifest,self.base)
        self.assertEqual(first,second)
        self.assertEqual((output/"other-job.txt").read_bytes(),b"keep")

    def test_output_parent_symlink_is_refused(self):
        real = self.base/"real"
        real.mkdir()
        link = self.base/"link"
        try:
            link.symlink_to(real,target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError,"symlink"):
            u.publish_batch([(link/"out.bin",b"new")])
        self.assertFalse(list(real.iterdir()))

    def test_output_inside_input_directory_is_refused(self):
        source = self.base / "input"
        source.mkdir()
        with self.assertRaisesRegex(ValueError, "inside the input"):
            u.repair_resources(source, source / "output", {"resources": {}}, self.base)

    def test_receipt_write_preserves_a_differing_existing_file(self):
        path = self.base / "receipt.json"
        path.write_bytes(b"other job")
        with self.assertRaisesRegex(ValueError, "existing output differs"):
            u.atomic_write(path, b"replacement")
        self.assertEqual(path.read_bytes(), b"other job")

    def fake_native(self, *, entry_size=6, slots=(1, 1), pack=b"abcdef", ordinal=1):
        source = self.base / "disc.iso"
        source.write_bytes(b"source stays exact")
        index = u.bump._IndexPack(1, len(slots), slots,
                                 tuple(sum(slots[:i]) * u.bump.SECTOR_SIZE for i in range(len(slots))),
                                 (u.bump._IndexEntry(0, 123, entry_size, ordinal),))
        physical = pack + b"_" * (u.bump.SECTOR_SIZE - len(pack)) + b"trailing padding"
        image = SimpleNamespace(index_size=11,
                                pack_size=lambda _i: len(physical),
                                read_pack=lambda _i, start, length: physical[start:start + length],
                                read_index_range=lambda start, length: b"index bytes"[start:start + length])
        context = mock.MagicMock()
        context.__enter__.return_value = image
        return source, index, context, physical

    def test_native_mapping_preserves_full_pack_and_index(self):
        source, index, context, original = self.fake_native()
        output = self.base / "packs"
        manifest = {"resources": {"16H0.IFF": [self.patch]}}
        with mock.patch.object(u.bump._Image, "open", return_value=context), \
             mock.patch.object(u.bump, "_parsed_index", return_value=index), \
             mock.patch.object(u.bump, "logical_name_for", return_value="16H0.IFF"):
            receipt = u.repair_packs(source, output, manifest, self.base)
            again = u.repair_packs(source, output, manifest, self.base)
        name = u.PACK_NAMES[1]
        self.assertEqual((output / name).read_bytes(), original[:2] + b"XY" + original[4:])
        self.assertEqual((output / "0").read_bytes(), b"index bytes")
        self.assertEqual(source.read_bytes(), b"source stays exact")
        self.assertEqual(receipt, again)
        row = receipt["disc_files"][f"vc_53450030/{name}"]
        self.assertTrue(row["outside_scope_identical"])
        self.assertEqual(row["size"], len(original))

    def test_native_resource_boundary_refused_before_any_output(self):
        source, index, context, _original = self.fake_native()
        output = self.base / "packs"
        manifest = {"resources": {"16H0.IFF": [dict(self.patch, offset=5)]}}
        with mock.patch.object(u.bump._Image, "open", return_value=context), \
             mock.patch.object(u.bump, "_parsed_index", return_value=index), \
             mock.patch.object(u.bump, "logical_name_for", return_value="16H0.IFF"):
            with self.assertRaisesRegex(u.bump.BumpTextureWriterError, "exceeds the entry"):
                u.repair_packs(source, output, manifest, self.base)
        self.assertFalse(output.exists())

    def test_native_cross_pack_span_refused_before_any_output(self):
        source, index, context, _original = self.fake_native(entry_size=4096, slots=(1, 1, 1))
        output = self.base / "packs"
        manifest = {"resources": {"16H0.IFF": [dict(self.patch, offset=2047)]}}
        with mock.patch.object(u.bump._Image, "open", return_value=context), \
             mock.patch.object(u.bump, "_parsed_index", return_value=index), \
             mock.patch.object(u.bump, "logical_name_for", return_value="16H0.IFF"):
            with self.assertRaisesRegex(ValueError, "cross-pack"):
                u.repair_packs(source, output, manifest, self.base)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

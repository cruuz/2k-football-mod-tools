"""Synthetic, portable Format 3 source-copy and literal-exclusion contract."""
import hashlib
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_modpack_files import image, contents, m, f, xc


class SourceCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = random.Random(765).randbytes(3 * f.BLOCK + 512)
        # Move retail at 512-byte alignment, across an index-read boundary,
        # overwrite its original destination, mix new bytes and append retail.
        self.new = (self.old[f.BLOCK - 512:f.BLOCK + 7 * f.GRAIN - 512]
                    + b"brand new!" * 4096 + self.old[512:512 + 5 * f.GRAIN])
        self.base = image(self.root / "base.iso", {"default.xbe": b"XBEH", "a": self.old})
        self.built = image(self.root / "built.iso", {"default.xbe": b"XBEH", "a": self.new})
        self.pack = self.root / "test.2k5patch"
        self.receipt = f.export(self.base, self.built, self.pack, require_retail=False)
        self.row = next(r for r in self.receipt["files"] if r["path"] == "a")

    def test_moved_spans_are_referenced_and_all_layouts_rebuild(self):
        self.assertGreaterEqual(self.row["source_copy_bytes"], 12 * f.GRAIN)
        self.assertEqual(self.row["mode"], "runs")
        with zipfile.ZipFile(self.pack) as z:
            records = list(f.SOURCE_COPY.iter_unpack(z.read(self.row["copies"]["member"])))
        self.assertTrue(any(source % f.GRAIN == 3584 for _, source, *_ in records))
        for name, base, order in (("retail", 0, ["default.xbe", "a"]),
                                  ("raw", 0x18300000, ["default.xbe", "a"]),
                                  ("reordered", 0, ["a", "default.xbe"])):
            with self.subTest(name=name):
                src = image(self.root / f"{name}.iso", {"default.xbe": b"XBEH", "a": self.old}, base=base, order=order)
                out = self.root / f"{name}-out.iso"
                self.assertEqual(m.check(self.pack, src)["state"], "ready")
                m.apply(self.pack, src, out)
                self.assertEqual(contents(out), contents(self.built))

    def test_no_literal_grain_exists_at_any_indexed_source_offset(self):
        retail = {self.old[i:i + f.GRAIN] for i in range(0, len(self.old) - f.GRAIN + 1, 512)}
        with zipfile.ZipFile(self.pack) as z:
            stream = io.BytesIO(z.read(self.row["payload"]["member"]))
        while header := stream.read(f.RUN.size):
            _, size, _, _ = f.RUN.unpack(header)
            data = stream.read(size)
            for at in range(0, len(data) - f.GRAIN + 1, f.GRAIN):
                self.assertNotIn(data[at:at + f.GRAIN], retail)

    def test_tampered_retail_source_refuses_and_copy_hash_checks_span(self):
        with self.base.open("r+b", buffering=0) as source, zipfile.ZipFile(self.pack) as z:
            entry = f._files(f._layout(source))["a"]
            _, source_at, *_ = f.SOURCE_COPY.unpack(z.read(self.row["copies"]["member"])[:f.SOURCE_COPY.size])
            at = entry.byte_offset + source_at
            data = xc.read_at(source, at, 1)
            xc.write_at(source, at, bytes([data[0] ^ 1]))
            # Direct replay also checks the referenced span independently of
            # the full-file preflight, including data outside a shrink result.
            with self.assertRaisesRegex(m.ModpackError, "Source-copy SHA-256"):
                list(f._reconstruct(self.row, source, entry, z))
        self.assertEqual(m.check(self.pack, self.base)["state"], "mismatch")
        out = self.root / "kept.iso"
        out.write_bytes(b"keep")
        with self.assertRaises(m.ModpackError):
            m.apply(self.pack, self.base, out, overwrite=True)
        self.assertEqual(out.read_bytes(), b"keep")
        self.assertFalse(list(self.root.glob("*.part")))

    def rewrite(self, change):
        bad = self.root / "bad.2k5patch"
        with zipfile.ZipFile(self.pack) as src, zipfile.ZipFile(bad, "w") as dst:
            doc = json.loads(src.read("manifest.json"))
            members = {n: src.read(n) for n in src.namelist() if n != "manifest.json"}
            change(doc, members)
            dst.writestr("manifest.json", json.dumps(doc))
            for name, data in members.items():
                dst.writestr(name, data)
        return bad

    def test_pre_release_contract_refuses(self):
        bad = self.rewrite(lambda doc, _: (doc.pop("file_contract"), doc.update(min_reader_version=3)))
        with self.assertRaisesRegex(m.ModpackError, "re-export"):
            m.load(bad)

    def test_copy_bounds_hash_and_cross_stream_overlap_refuse(self):
        for field, value in ((1, len(self.old)), (2, f.BLOCK + 1), (4, bytes(32)), (0, 7 * f.GRAIN)):
            with self.subTest(field=field):
                def change(doc, members):
                    row = next(r for r in doc["files"] if r["path"] == "a")
                    blob = row["copies"]
                    records = list(f.SOURCE_COPY.iter_unpack(members[blob["member"]]))
                    record = list(records[0])
                    record[field] = value
                    data = f.SOURCE_COPY.pack(*record) + b"".join(f.SOURCE_COPY.pack(*r) for r in records[1:])
                    members[blob["member"]] = data
                    blob["sha256"] = hashlib.sha256(data).hexdigest()
                bad = self.rewrite(change)
                self.assertEqual(m.check(bad, self.base)["state"], "mismatch")
                with self.assertRaises(m.ModpackError):
                    m.apply(bad, self.base, self.root / "bad.iso")
                self.assertFalse((self.root / "bad.iso").exists())

    def test_hash_collision_still_checks_every_candidate(self):
        old = b"a" * f.GRAIN + b"b" * f.GRAIN
        entry = type("Entry", (), {"byte_offset": 0, "size": len(old)})()
        after = type("Entry", (), {"byte_offset": 0, "size": f.GRAIN})()
        with mock.patch.object(f.hashlib, "blake2b", return_value=type("Hash", (), {"digest": lambda self: b"collision"})()):
            index = f._retail_index(io.BytesIO(old), entry, m._no_progress)
            edits = list(f._edits(io.BytesIO(old), io.BytesIO(b"b" * f.GRAIN), entry, after, index))
        self.assertEqual(len(edits), 1)
        self.assertTrue(edits[0][0])
        self.assertEqual(f.SOURCE_COPY.unpack(edits[0][1])[1], f.GRAIN)

    def test_arbitrary_source_offset_and_growth_use_original_file(self):
        # The wire supports arbitrary offsets even though export indexes 512.
        offset, size = 17, 2 * f.GRAIN
        wanted = self.old[offset:offset + size]
        record = f.SOURCE_COPY.pack(len(self.old), offset, size,
                                    hashlib.sha256(b"").digest(), hashlib.sha256(wanted).digest())
        row = dict(mode="runs", after=dict(size=len(self.old) + size),
                   payload=dict(member="literal", length=0, sha256=f.EMPTY),
                   copies=dict(member="copies", length=len(record), sha256=hashlib.sha256(record).hexdigest()))
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("literal", b"")
            z.writestr("copies", record)
        entry = type("Entry", (), {"byte_offset": 0, "size": len(self.old)})()
        with zipfile.ZipFile(archive) as z:
            data = b"".join(data for _, data in f._reconstruct(row, io.BytesIO(self.old), entry, z))
        self.assertEqual(data, self.old + wanted)

    def test_budgeted_proof_streams_only_large_fixtures_and_cleans_up(self):
        from tools import prove_softdrink_pack as proof
        work = self.root / "proof"
        argv = ["proof", "--retail", str(self.base), "--finished", str(self.built),
                "--pack", str(self.pack), "--work", str(work), "--stream-fixtures", "--scratch-limit", "500000000"]
        with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout", new=io.StringIO()):
            proof.main()
        receipt = json.loads((work / "proof-E.json").read_text())
        self.assertIn("disk apply", receipt["cases"]["retail"]["proof_mode"])
        for case in ("raw", "repacked"):
            self.assertTrue(receipt["cases"][case]["all_files_byte_equal"])
            self.assertEqual(receipt["cases"][case]["output_allocated_bytes"], 0)
        self.assertFalse(list(work.glob("*.iso")))

    def test_cross_file_move_uses_verified_donor_and_never_stores_its_grains(self):
        donor = random.Random(22).randbytes(256 * 1024)
        old = {"default.xbe": b"XBEH", "a": self.old, "donor": donor}
        wanted = donor[512:512 + 16 * f.GRAIN]
        base = image(self.root / "cross-base.iso", old)
        built = image(self.root / "cross-built.iso", dict(old, a=wanted))
        pack = self.root / "cross.2k5patch"
        f.export(base, built, pack, require_retail=False)
        row = next(r for r in m.inspect(pack)["files"] if r["path"] == "a")
        self.assertEqual(row["literal_bytes"], 0)
        self.assertEqual(row["cross_copies"][0]["source_path"], "donor")
        self.assertEqual(row["source_copy_bytes"], len(wanted))
        for prefix, order in ((0, ["default.xbe", "a", "donor"]),
                              (0x18300000, ["donor", "a", "default.xbe"])):
            source = image(self.root / "cross-source.iso", old, base=prefix, order=order)
            out = self.root / "cross-out.iso"
            m.apply(pack, source, out, overwrite=True)
            self.assertEqual(contents(out), contents(built))
        with base.open("r+b", buffering=0) as source, zipfile.ZipFile(pack) as z:
            entries = f._files(f._layout(source))
            xc.write_at(source, entries["donor"].byte_offset + 512, b"X")
            with self.assertRaisesRegex(m.ModpackError, "Source-copy SHA-256"):
                list(f._reconstruct(row, source, entries["a"], z, entries))
        self.assertEqual(m.check(pack, base)["state"], "mismatch")

    def test_cross_file_source_must_be_in_verified_inventory(self):
        def change(doc, members):
            row = next(r for r in doc["files"] if r["path"] == "a")
            row["cross_copies"] = [dict(row.pop("copies"), source_path="unverified")]
        with self.assertRaisesRegex(m.ModpackError, "verified inventory"):
            m.load(self.rewrite(change))


if __name__ == "__main__":
    unittest.main()

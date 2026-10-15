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

    def test_index_uses_exact_seed_bytes_instead_of_lossy_hash_keys(self):
        old = b"a" * f.GRAIN + b"b" * f.GRAIN
        entry = type("Entry", (), {"byte_offset": 0, "size": len(old)})()
        after = type("Entry", (), {"byte_offset": 0, "size": f.GRAIN})()
        index = f._retail_index(io.BytesIO(old), entry, m._no_progress)
        self.assertEqual(index[b"a" * f.COPY_SEED], 0)
        self.assertEqual(index[b"b" * f.COPY_SEED], f.GRAIN)
        self.assertTrue(all(len(seed) == f.COPY_SEED for seed in index))
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

    def test_export_references_unaligned_prefixes_tails_and_read_boundaries(self):
        from tools import nfl2k5_modpack as cli
        import contextlib
        prefix, middle = b"NEW PREFIX!", b"NEW MIDDLE!"
        first = self.old[17:17 + f.BLOCK + 731]
        second = self.old[2 * f.BLOCK + 113:2 * f.BLOCK + 113 + 777]
        wanted = prefix + first + middle + second
        originals = {"default.xbe": b"XBEH", "a": b"previous destination", "donor": self.old}
        base = image(self.root / "unaligned-base.iso", originals)
        built = image(self.root / "unaligned-built.iso", dict(originals, a=wanted))
        pack = self.root / "unaligned.2k5patch"
        receipt = f.export(base, built, pack, require_retail=False)
        row = next(r for r in receipt["files"] if r["path"] == "a")
        copied = []
        with zipfile.ZipFile(pack) as z:
            for source, blob in f._copy_payloads(row):
                self.assertEqual(source, "donor")
                copied.extend(f.SOURCE_COPY.iter_unpack(z.read(blob["member"])))
        for start, data in [(len(prefix), first), (len(prefix) + len(first) + len(middle), second)]:
            covered = sum(max(0, min(start + len(data), at + n) - max(start, at))
                          for at, source, n, *_ in copied)
            self.assertEqual(covered, len(data))
        self.assertTrue(any(source % 512 and n % 4096 for _, source, n, *_ in copied))
        self.assertEqual(m.load(pack).manifest.raw["min_reader_version"], 4)
        out = self.root / "unaligned-cli.iso"
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["apply", str(pack), "--source", str(base), "--out", str(out)]), 0)
        self.assertEqual(contents(out), contents(built))

    def test_short_isolated_retail_fragment_is_copied_without_sparse_anchor(self):
        # No complete 32-byte anchor at a 512-byte source offset fits this
        # fragment. This reproduced a 505-byte retail literal in the full audit.
        donor = random.Random(829).randbytes(4097)
        wanted = b"authored prefix!" + donor[17:522] + b"authored tail!"
        originals = {"default.xbe": b"XBEH", "a": b"old", "donor": donor}
        base = image(self.root / "short-base.iso", originals)
        built = image(self.root / "short-built.iso", dict(originals, a=wanted))
        pack = self.root / "short.2k5patch"
        result = f.export(base, built, pack, require_retail=False)
        row = next(r for r in result["files"] if r["path"] == "a")
        with zipfile.ZipFile(pack) as z:
            with z.open(row["payload"]["member"]) as stream:
                for at, literal in f._literal_records(stream):
                    self.assertEqual(max(0, min(at + len(literal), 521) - max(at, 16)), 0)
        out = self.root / "short-installed.iso"
        m.apply(pack, base, out)
        self.assertEqual(contents(out), contents(built))

    def test_prefix_copy_rechecks_the_new_short_tail_it_creates(self):
        rng = random.Random(830)
        first, other, a, b = (rng.randbytes(n) for n in (17, 17, 16, 16))
        donor = bytes(64).join((first, other, a, b))
        original = {"default.xbe": b"XBEH", "a": b"old1", "b": b"old2", "donor": donor}
        # Sampling first/other copies 17 bytes and leaves unaligned A+B and A.
        # The prefix pass learns A from the short row, copies A from the long
        # row too, and must then discover the newly exposed 16-byte B tail.
        wanted = dict(original, a=first + a + b, b=other + a)
        base = image(self.root / "tail-base.iso", original)
        built = image(self.root / "tail-built.iso", wanted)
        pack = self.root / "tail.2k5patch"
        result = f.export(base, built, pack, require_retail=False)
        for row in result["files"]:
            if row["path"] in ("a", "b"):
                self.assertEqual(row["literal_bytes"], 0, row["path"])
        out = self.root / "tail-installed.iso"
        m.apply(pack, base, out)
        self.assertEqual(contents(out), contents(built))

    def test_four_to_fifteen_byte_whole_literals_are_source_copies(self):
        donor = random.Random(934).randbytes(4097)
        original = {"default.xbe": b"XBEH", "donor": donor}
        wanted = dict(original)
        for size in range(4, 16):
            original[str(size)] = b"old"
            wanted[str(size)] = donor[37:37 + size]
        base = image(self.root / "tiny-base.iso", original)
        built = image(self.root / "tiny-built.iso", wanted)
        pack = self.root / "tiny.2k5patch"
        result = f.export(base, built, pack, require_retail=False)
        for row in result["files"]:
            if row["path"].isdigit():
                self.assertEqual(row["literal_bytes"], 0, row["path"])
        out = self.root / "tiny-installed.iso"
        m.apply(pack, base, out)
        self.assertEqual(contents(out), contents(built))

    def test_short_seed_acceleration_and_stdlib_agree_at_read_boundaries(self):
        raw = random.Random(543).randbytes(f.BLOCK + 79) + bytes(4096)
        needles = {raw[i:i + 4] for i in range(0, len(raw) - 4, 211)}
        needles.update((raw[f.BLOCK - 3:f.BLOCK + 1], bytes(4)))
        entry = type("Entry", (), {"path": "a", "byte_offset": 0, "size": len(raw)})()
        accelerated = f._find_literal_seeds(io.BytesIO(raw), [entry], set(needles),
                                           m._no_progress, seed_size=4)
        with mock.patch.object(f, "_literal_seed_candidates", return_value=None):
            fallback = f._find_literal_seeds(io.BytesIO(raw), [entry], set(needles),
                                            m._no_progress, seed_size=4)
        expected = {seed: raw.find(seed) for seed in needles}
        self.assertEqual(accelerated, expected)
        self.assertEqual(fallback, expected)
        # A four-byte witness cannot straddle independently pinned files.
        entries = [type("Entry", (), {"path": "one", "byte_offset": 0, "size": 31})(),
                   type("Entry", (), {"path": "two", "byte_offset": 31, "size": 31})()]
        self.assertEqual(f._find_literal_seeds(io.BytesIO(raw), entries, {raw[29:33]},
                                              m._no_progress, seed_size=4), {})

    def test_prefix_failure_closes_spools_and_removes_partial_pack(self):
        rng = random.Random(830)
        first, other, a, b = (rng.randbytes(n) for n in (17, 17, 16, 16))
        original = {"default.xbe": b"XBEH", "a": b"old1", "b": b"old2",
                    "donor": bytes(64).join((first, other, a, b))}
        base = image(self.root / "fault-base.iso", original)
        built = image(self.root / "fault-built.iso", dict(original, a=first + a + b, b=other + a))
        pack = self.root / "fault.2k5patch"
        split = f._split_literal
        def fail(*args, **kwargs):
            if kwargs.get("prefix_only"):
                raise RuntimeError("injected prefix failure")
            yield from split(*args, **kwargs)
        with mock.patch.object(f, "_split_literal", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "injected prefix failure"):
                f.export(base, built, pack, require_retail=False)
        self.assertFalse(pack.exists())
        self.assertFalse(list(self.root.glob(".2k5-*")))

    def test_inverse_search_covers_every_alignment_without_crossing_files(self):
        raw = random.Random(929).randbytes(65536 + 64)
        entry = type("Entry", (), {"path": "a", "byte_offset": 0, "size": len(raw)})()
        offsets = [0, 1, 15, 16, 511, 512, 65520, 65535, len(raw) - 16]
        wanted = {raw[at:at + 16]: at for at in offsets}
        actual = f._find_literal_seeds(io.BytesIO(raw), [entry], set(wanted), m._no_progress)
        self.assertEqual(actual, wanted)
        split = 31
        entries = [type("Entry", (), {"path": "first", "byte_offset": 0, "size": split})(),
                   type("Entry", (), {"path": "second", "byte_offset": split, "size": 31})()]
        crossing = raw[split - 8:split + 8]
        self.assertEqual(f._find_literal_seeds(io.BytesIO(raw), entries, {crossing}, m._no_progress), {})

    def test_accelerated_search_and_stdlib_find_the_same_exact_seeds(self):
        raw = random.Random(543).randbytes(f.BLOCK + 79) + bytes(4096)
        offsets = list(range(0, len(raw) - 16, 211)) + [f.BLOCK - 15, f.BLOCK - 1]
        needles = {raw[at:at + 16] for at in offsets}
        needles.add(bytes(16))
        needles.add(b"absent-pattern!!")
        entry = type("Entry", (), {"path": "a", "byte_offset": 0, "size": len(raw)})()
        accelerated = f._find_literal_seeds(io.BytesIO(raw), [entry], set(needles), m._no_progress)
        with mock.patch.object(f, "_literal_seed_candidates", return_value=None):
            fallback = f._find_literal_seeds(io.BytesIO(raw), [entry], set(needles), m._no_progress)
        expected = {seed: raw.find(seed) for seed in needles if seed in raw}
        self.assertEqual(accelerated, expected)
        self.assertEqual(fallback, expected)
        with mock.patch.dict(sys.modules, {"numpy": None}):
            self.assertIsNone(f._literal_seed_candidates(needles))

    def test_prefilter_false_positives_never_become_copies(self):
        raw = random.Random(544).randbytes(8192)
        other = random.Random(54545)
        needles = {other.randbytes(16) for _ in range(4096)}
        needles.add(raw[17:33])
        entry = type("Entry", (), {"path": "a", "byte_offset": 0, "size": len(raw)})()
        with mock.patch.object(f, "_literal_seed_candidates", return_value=lambda data: range(len(data) - 15)):
            actual = f._find_literal_seeds(io.BytesIO(raw), [entry], needles, m._no_progress)
        self.assertEqual(actual, {raw[17:33]: 17})

    def test_seed_after_output_boundary_recovers_the_previous_tail(self):
        # The first searchable anchor is in the next output window. Its exact
        # backward extension must rescue these 23 bytes before emitting literals.
        old = random.Random(194).randbytes(2000)
        wanted = b"N" * (f.BLOCK - 23) + old[17:1701]
        before = type("Entry", (), {"byte_offset": 0, "size": len(old)})()
        after = type("Entry", (), {"byte_offset": 0, "size": len(wanted)})()
        index = f._retail_index(io.BytesIO(old), before, m._no_progress)
        edits = list(f._edits(io.BytesIO(old), io.BytesIO(wanted), before, after, index))
        copies = [f.SOURCE_COPY.unpack(record) for source, record, _ in edits if source is not None]
        self.assertTrue(any(at == f.BLOCK - 23 and source == 17 and size == 23
                            for at, source, size, *_ in copies))
        self.assertEqual(sum(size for _, _, size, *_ in copies), 1684)

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

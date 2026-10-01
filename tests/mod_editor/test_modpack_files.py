"""Retail-free format-3 contract; runs directly in all six OS/Python CI jobs."""
import hashlib
import contextlib
import io
import json
import os
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from nfl2k5_xiso_fixture import dir_node
from mod_editor.core import modpack as m, modpack_files as f, xdvdfs_compact as xc


def image(path, files, order=None, base=0):
    """Independent padded XDVDFS fixture, including nested and empty entries."""
    at, entries = 40 * 2048, {}
    with path.open("wb") as stream:
        for name in order or files:
            data = files[name]
            entries[name] = (at // 2048, len(data), 0x80, name)
            stream.seek(base + at)
            stream.write(data)
            at += xc.align(len(data)) + 3 * 2048
        nested = dir_node([(0, 0, 0x80, "empty")])
        root = dir_node(sorted([*entries.values(), (34, len(nested), 0x10, "sub")], key=lambda r: r[3].casefold()))
        header = bytearray(2048)
        header[:20] = header[-20:] = xc.xiso.XDVDFS_MAGIC
        struct.pack_into("<II", header, 20, 33, len(root))
        for offset, data in ((32 * 2048, header), (33 * 2048, root), (34 * 2048, nested)):
            stream.seek(base + offset)
            stream.write(data)
        stream.truncate(base + at)
    return path


def contents(path):
    with path.open("rb", buffering=0) as stream:
        return {p: xc.read_at(stream, e.byte_offset, e.size) for p, e in xc.read_layout(stream).entries.items()
                if not e.attributes & 0x10}


class FilePackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        rng = random.Random(76)
        self.original = dict(default_xbe=b"XBEH" + rng.randbytes(5000))
        self.original = {"default.xbe": self.original["default_xbe"], "a": rng.randbytes(2 * f.BLOCK + 77),
                         "grow": b"old", "shrink": b"long file", "same": b"unchanged"}
        a = bytearray(self.original["a"])
        a[10:15] = b"EDIT!"
        a[f.BLOCK - 3:f.BLOCK + 4] = b"ACROSS!"
        self.finished = dict(self.original, a=bytes(a), grow=b"new" * 4000, shrink=b"x")
        self.base = image(self.root / "base.iso", self.original)
        built = image(self.root / "built.iso", self.finished, order=list(reversed(self.finished)))
        self.built = self.root / "compact.iso"
        xc.compact_copy(built, self.built)
        self.pack = self.root / "test.2k5patch"
        self.receipt = f.export(self.base, self.built, self.pack, require_retail=False)

    def test_raw_repacked_and_retail_match_all_files_and_author(self):
        for label, base, order in (("retail", 0, list(self.original)),
                                   ("raw", 0x18300000, list(self.original)),
                                   ("repacked", 0, list(reversed(self.original)))):
            with self.subTest(label=label):
                source = image(self.root / f"{label}.iso", self.original, base=base, order=order)
                before = source.stat()
                self.assertEqual(m.check(self.pack, source)["state"], "ready")
                output = self.root / f"{label}-out.iso"
                result = m.apply(self.pack, source, output)
                self.assertTrue(result["target"]["matches_author_result"])
                self.assertEqual(output.read_bytes(), self.built.read_bytes())
                self.assertEqual(contents(output), dict(self.finished, **{"sub/empty": b""}))
                self.assertEqual(source.stat().st_mtime_ns, before.st_mtime_ns)

    def test_modes_and_measured_saving(self):
        rows = {r["path"]: r for r in m.inspect(self.pack)["files"]}
        self.assertEqual(rows["a"]["mode"], "runs")
        self.assertEqual(rows["same"]["mode"], "copy")
        self.assertEqual(rows["grow"]["mode"], "runs")
        self.assertEqual(rows["shrink"]["mode"], "runs")
        self.assertLess(self.receipt["payload_deflated_bytes"], self.receipt["full_copy_deflated_bytes"])

    def test_cli_apply_and_inspect_without_json(self):
        from tools import nfl2k5_modpack as cli
        output = self.root / "cli.iso"
        text = io.StringIO()
        with contextlib.redirect_stdout(text), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["inspect", str(self.pack)]), 0)
            self.assertEqual(cli.main(["apply", str(self.pack), "--source", str(self.base), "--out", str(output)]), 0)
        self.assertIn("game files verified", text.getvalue())
        self.assertEqual(output.read_bytes(), self.built.read_bytes())

    def test_private_proof_driver_checks_real_layouts_and_keeps_last_output(self):
        from tools import prove_softdrink_pack as proof
        work = self.root / "proof"
        args = ["proof", "--retail", str(self.base), "--finished", str(self.built), "--pack", str(self.pack),
                "--work", str(work), "--keep-output"]
        with mock.patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
            proof.main()
        receipt = json.loads((work / "proof-E.json").read_text())
        self.assertEqual(set(receipt["cases"]), {"retail", "raw", "repacked"})
        self.assertTrue(all(case["independent_byte_comparison"] for case in receipt["cases"].values()))
        self.assertTrue(receipt["retail_unchanged"])
        self.assertEqual(Path(receipt["retained_output"]).read_bytes(), self.built.read_bytes())
        self.assertIn("wrong-xbox-game", receipt["negatives"])
        self.assertFalse(list(work.glob("synthetic-*.iso")))

    def test_growth_and_shrink_choose_small_verified_runs(self):
        for mode, new in (("grow", self.original["a"] + b"tail" * (f.BLOCK // 2)),
                          ("shrink", self.original["a"][:f.BLOCK + 4])):
            with self.subTest(mode=mode):
                built = image(self.root / "resized.iso", dict(self.original, a=new))
                pack = self.root / "resized.2k5patch"
                f.export(self.base, built, pack, require_retail=False, overwrite=True)
                row = next(r for r in m.inspect(pack)["files"] if r["path"] == "a")
                self.assertEqual(row["mode"], "runs")
                out = self.root / "resized-out.iso"
                m.apply(pack, self.base, out, overwrite=True)
                self.assertEqual(contents(out)["a"], new)

    def test_harmless_extra_file_and_playstation_diagnostic(self):
        src = image(self.root / "extra.iso", dict(self.original, notes=b"hello"))
        self.assertEqual(m.check(self.pack, src)["state"], "ready")
        ps2 = self.root / "ps2.iso"
        data = bytearray(65536)
        data[0x8000:0x8006] = b"\1CD001"
        data[0x9000:0x900a] = b"SYSTEM.CNF"
        ps2.write_bytes(data)
        report = m.check(self.pack, ps2)
        self.assertIn("PlayStation", report["explanation"])
        self.assertIn("PS2", report["explanation"])

    def test_negative_sources_leave_destination_unchanged(self):
        for kind in ("modded", "truncated", "wrong"):
            with self.subTest(kind=kind):
                data = dict(self.original)
                if kind == "modded": data["same"] = b"modified!"
                if kind == "wrong": data["default.xbe"] = b"other game"
                src = image(self.root / (kind + ".iso"), data)
                if kind == "truncated":
                    with src.open("r+b") as stream: stream.truncate(85000)
                out = self.root / "existing.iso"
                out.write_bytes(b"keep")
                report = m.check(self.pack, src)
                self.assertEqual(report["state"], "mismatch")
                for word in ("Detected:", "Incompatible:", "Next:"):
                    self.assertIn(word, report["explanation"])
                with self.assertRaises(m.ModpackError): m.apply(self.pack, src, out, overwrite=True)
                self.assertEqual(out.read_bytes(), b"keep")
                self.assertFalse(list(self.root.glob("*.part")))

    def test_alias_and_in_place_refused(self):
        with self.assertRaises(m.ModpackError): m.apply(self.pack, self.base, self.base, overwrite=True)
        with self.assertRaises(m.ModpackError): m.apply_in_place(self.pack, self.base)
        alias = self.root / "hardlink.iso"
        os.link(self.base, alias)
        with self.assertRaises(m.ModpackError): m.apply(self.pack, self.base, alias, overwrite=True)

    def test_no_positional_io_and_unicode_paths(self):
        folder = self.root / ("données " + "a" * 75) / ("sources " + "b" * 75) / ("more " + "c" * 75)
        f._path(folder).mkdir(parents=True)
        old_read, old_write = getattr(os, "pread", None), getattr(os, "pwrite", None)
        try:
            if old_read: del os.pread
            if old_write: del os.pwrite
            with mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
                result = m.apply(self.pack, self.base, folder / "été.xiso.iso")
        finally:
            if old_read: os.pread = old_read
            if old_write: os.pwrite = old_write
        self.assertTrue(result["target"]["matches_author_result"])

    def test_alias_refusals_without_resolve(self):
        alias = self.root / "hardlink.iso"
        os.link(self.base, alias)
        before = self.base.read_bytes(), self.pack.read_bytes()
        with mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
            for target in (self.base, alias, self.pack):
                with self.subTest(target=target), self.assertRaisesRegex(m.ModpackError, "different file"):
                    m.apply(self.pack, self.base, target, overwrite=True)
            with mock.patch.object(os.path, "samefile", side_effect=OSError("stat unavailable")):
                with self.assertRaisesRegex(m.ModpackError, "different file"):
                    m.apply(self.pack, self.base, self.root / "." / "base.iso", overwrite=True)
        self.assertEqual((self.base.read_bytes(), self.pack.read_bytes()), before)
        self.assertFalse(list(self.root.glob("*.part")))

    def test_publication_retries_locks_and_keeps_existing_bytes(self):
        out = self.root / "locked.iso"
        before = self.base.read_bytes()
        publish = m.platform_compat.publish_no_replace
        attempts = []
        def transient(part, target):
            attempts.append(target)
            if len(attempts) < 3:
                raise PermissionError("sharing violation")
            return publish(part, target)
        with mock.patch.object(m.platform_compat, "publish_no_replace", side_effect=transient), \
             mock.patch.object(f.time, "sleep"):
            m.apply(self.pack, self.base, out)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(out.read_bytes(), self.built.read_bytes())
        out.write_bytes(b"preserved")
        with mock.patch.object(m.os, "replace", side_effect=PermissionError("sharing violation")) as replace, \
             mock.patch.object(m.time, "sleep"):
            with self.assertRaisesRegex(PermissionError, "Close programs"):
                m.apply(self.pack, self.base, out, overwrite=True)
        self.assertEqual(replace.call_count, 20)
        self.assertEqual(out.read_bytes(), b"preserved")
        self.assertEqual(self.base.read_bytes(), before)
        self.assertFalse(list(self.root.glob("*.part")))

    def rewrite(self, mutation):
        bad = self.root / "bad.2k5patch"
        with zipfile.ZipFile(self.pack) as src, zipfile.ZipFile(bad, "w", zipfile.ZIP_DEFLATED) as dst:
            doc = json.loads(src.read("manifest.json"))
            mutation(doc)
            for name in src.namelist():
                dst.writestr(name, json.dumps(doc).encode() if name == "manifest.json" else src.read(name))
        return bad

    def test_bad_output_hash_and_corrupt_runs_are_transactional(self):
        bad = self.rewrite(lambda d: d["files"][0]["after"].update(sha256="0" * 64))
        with self.assertRaises(m.ModpackError): m.apply(bad, self.base, self.root / "no.iso")
        self.assertFalse((self.root / "no.iso").exists())
        self.assertFalse(list(self.root.glob("*.part")))
        member = next(r["payload"]["member"] for r in self.receipt["files"] if r["mode"] == "runs")
        corrupt = self.root / "corrupt.2k5patch"
        with zipfile.ZipFile(self.pack) as src, zipfile.ZipFile(corrupt, "w", zipfile.ZIP_DEFLATED) as dst:
            for name in src.namelist():
                data = src.read(name)
                if name == member: data = data[:-1] + bytes([data[-1] ^ 1])
                dst.writestr(name, data)
        self.assertEqual(m.check(corrupt, self.base)["state"], "mismatch")
        with self.assertRaises(m.ModpackError): m.apply(corrupt, self.base, self.root / "corrupt.iso")
        self.assertFalse((self.root / "corrupt.iso").exists())

    def test_overlapping_output_extents_and_traversal_refused(self):
        bad = self.rewrite(lambda d: d["files"][1].update(offset=d["files"][0]["offset"]))
        with self.assertRaises(m.ModpackError): m.load(bad)
        bad = self.rewrite(lambda d: d["files"][0].update(path="../escape"))
        with self.assertRaises(m.ModpackError): m.load(bad)
        bad = self.rewrite(lambda d: d.update(metadata=[None]))
        with self.assertRaises(m.ModpackError): m.load(bad)
        bad = self.rewrite(lambda d: d.update(assets=[None]))
        with self.assertRaises(m.ModpackError): m.load(bad)

    def test_zip_directory_budget_precedes_zip_materialization(self):
        data = bytearray(self.pack.read_bytes())
        footer = data.rfind(b"PK\x05\x06")
        struct.pack_into("<I", data, footer + 12, 17 * 1024 * 1024)
        bad = self.root / "huge-directory.2k5patch"
        bad.write_bytes(data)
        with self.assertRaisesRegex(m.ModpackError, "ZIP directory exceeds"):
            m.load(bad)

    def test_low_space_cancel_and_readback_failure(self):
        output = self.root / "no.iso"
        with mock.patch.object(f.shutil, "disk_usage", return_value=type("Usage", (), {"free": 0})()):
            with self.assertRaises(m.ModpackError): m.apply(self.pack, self.base, output)
        def fail(stage, done, total):
            if stage == "Installing finished files": raise RuntimeError("cancelled")
        with self.assertRaises(RuntimeError): m.apply(self.pack, self.base, output, progress=fail)
        original = f._digest
        def corrupt(stream, offset, size, progress=None):
            if str(stream.name).endswith(".part"): return "0" * 64
            return original(stream, offset, size, progress)
        with mock.patch.object(f, "_digest", side_effect=corrupt):
            with self.assertRaises(m.ModpackError): m.apply(self.pack, self.base, output)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob("*.part")))

    def test_publish_failure_and_source_change_keep_existing_destination(self):
        out = self.root / "existing.iso"
        out.write_bytes(b"preserved")
        with mock.patch.object(m, "_atomic_replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError): m.apply(self.pack, self.base, out, overwrite=True)
        self.assertEqual(out.read_bytes(), b"preserved")
        original = f._stamp
        calls = []
        def changed(stream):
            stamp = original(stream)
            calls.append(stamp)
            return stamp if len(calls) == 1 else (*stamp[:-1], stamp[-1] + 1)
        with mock.patch.object(f, "_stamp", side_effect=changed):
            with self.assertRaises(m.ModpackError): m.apply(self.pack, self.base, out, overwrite=True)
        self.assertEqual(out.read_bytes(), b"preserved")
        self.assertFalse(list(self.root.glob("*.part")))


if __name__ == "__main__":
    unittest.main()

"""Shareable disc patches (.2k5patch): export / inspect / check / apply on synthetic images.

Everything here is synthetic: a 1 MiB pseudo-random "base", a patched copy with
scattered edits, and a minimal real XDVDFS image for region labelling.  No game
data is read, so this runs on a bare CI runner.
"""

from __future__ import annotations

from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from mod_editor.core import modpack  # noqa: E402

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"
HEADER_OFFSET = 0x10000
SMALL_BLOCK = 64 * 1024   # exercise block boundaries on 1 MiB inputs

EDITS = (
    (100, 20),          # plain edit
    (150, 10),          # 30-byte gap from the first: coalesced into one run
    (5000, 3),
    (65534, 4),         # straddles a 64 KiB block boundary
    (524287, 2),        # straddles the 512 KiB step boundary
    (700000, 1000),     # a "texture chunk"
    (1048570, 6),       # runs to the very last byte
)


@contextmanager
def windows_file_locks():
    """Emulate Windows replace/unlink denial for real open descriptors/ZIP streams.

    Linux permits these operations on open files. Track the actual handles so
    the same failure paths are exercised locally, including retained tracebacks.
    """
    descriptors, streams = {}, []
    real_open, real_close, real_fdopen = os.open, os.close, os.fdopen
    real_zip_open, real_replace, real_unlink = zipfile.ZipFile.open, os.replace, os.unlink

    def opened(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        descriptors[fd] = Path(path).resolve()
        return fd

    def closed(fd):
        real_close(fd)
        descriptors.pop(fd, None)

    def fdopened(fd, *args, **kwargs):
        stream = real_fdopen(fd, *args, **kwargs)
        streams.append((descriptors.pop(fd), stream))
        return stream

    def zip_opened(archive, *args, **kwargs):
        stream = real_zip_open(archive, *args, **kwargs)
        if isinstance(archive.filename, (str, os.PathLike)):
            streams.append((Path(archive.filename).resolve(), stream))
        return stream

    def open_paths():
        return list(descriptors.values()) + [path for path, stream in streams if not stream.closed]

    def require_closed(*paths):
        for path in paths:
            if Path(path).resolve() in open_paths():
                error = PermissionError(13, "simulated WinError 5: file is open", str(path))
                error.winerror = 5
                raise error

    def replace(source, target):
        require_closed(source, target)
        return real_replace(source, target)

    def unlink(path, *args, **kwargs):
        require_closed(path)
        return real_unlink(path, *args, **kwargs)

    with patch.object(os, "open", opened), patch.object(os, "close", closed), \
            patch.object(os, "fdopen", fdopened), patch.object(zipfile.ZipFile, "open", zip_opened), \
            patch.object(os, "replace", replace), patch.object(os, "unlink", unlink):
        yield open_paths


def make_pair(directory: Path, size: int = 1 << 20, seed: int = 7) -> tuple[Path, Path, bytes, bytes]:
    rng = random.Random(seed)
    base = bytearray(rng.randbytes(size))
    patched = bytearray(base)
    for offset, length in EDITS:
        for index in range(length):
            patched[offset + index] ^= 0x5A
    base_path, patched_path = directory / "base.xiso.iso", directory / "patched.xiso.iso"
    base_path.write_bytes(base)
    patched_path.write_bytes(patched)
    return base_path, patched_path, bytes(base), bytes(patched)


def build_xdvdfs(files: dict[str, bytes], base_offset: int = 0, tail_pad: int = 0) -> bytes:
    """A real, minimal XDVDFS image (flat root; right-leaning AVL chain)."""

    names = sorted(files)
    root_sector = (HEADER_OFFSET // SECTOR) + 1
    layout: dict[str, tuple[int, int]] = {}
    cursor = root_sector + 1
    for name in names:
        layout[name] = (cursor, len(files[name]))
        cursor += max(1, (len(files[name]) + SECTOR - 1) // SECTOR)
    nodes = bytearray()
    offsets: list[int] = []
    for name in names:
        offsets.append(len(nodes))
        sector, size = layout[name]
        nodes += struct.pack("<HHII", 0, 0, sector, size)
        nodes += bytes([0x20, len(name)])
        nodes += name.encode("ascii")
        while len(nodes) % 4:
            nodes += b"\0"
    for index, offset in enumerate(offsets[:-1]):
        struct.pack_into("<H", nodes, offset + 2, offsets[index + 1] // 4)
    header = bytearray(SECTOR)
    header[0:20] = MAGIC
    struct.pack_into("<II", header, 20, root_sector, len(nodes))
    header[SECTOR - 20:SECTOR] = MAGIC
    partition = bytearray((cursor + 1) * SECTOR)
    partition[HEADER_OFFSET:HEADER_OFFSET + SECTOR] = header
    partition[root_sector * SECTOR:root_sector * SECTOR + len(nodes)] = nodes
    for name in names:
        sector, size = layout[name]
        partition[sector * SECTOR:sector * SECTOR + size] = files[name]
    return bytes(base_offset) + bytes(partition) + bytes(tail_pad)


class DiffPrimitiveTests(unittest.TestCase):
    def test_differences_are_exact_at_every_step_boundary(self) -> None:
        rng = random.Random(1)
        a = rng.randbytes(1 << 20)
        b = bytearray(a)
        wanted = []
        for offset in (0, 15, 16, 511, 512, 16383, 16384, 524287, 524288, (1 << 20) - 1):
            b[offset] ^= 0xFF
            wanted.append((offset, offset + 1))
        self.assertEqual(modpack.differences(a, bytes(b)), wanted)
        self.assertEqual(modpack.differences(a, a), [])

    def test_differences_match_a_naive_scan_on_random_edits(self) -> None:
        rng = random.Random(2)
        a = rng.randbytes(300_000)
        b = bytearray(a)
        for _ in range(200):
            start = rng.randrange(len(a))
            for index in range(start, min(len(a), start + rng.randrange(1, 40))):
                b[index] = (b[index] + 1) & 0xFF
        naive: list[tuple[int, int]] = []
        for index, (left, right) in enumerate(zip(a, b)):
            if left != right:
                if naive and naive[-1][1] == index:
                    naive[-1] = (naive[-1][0], index + 1)
                else:
                    naive.append((index, index + 1))
        self.assertEqual(modpack.coalesce(modpack.differences(a, bytes(b)), 1), naive)

    def test_coalesce_merges_only_gaps_below_the_threshold(self) -> None:
        ranges = [(0, 10), (73, 80), (144, 150), (200, 210)]   # gaps of 63, 64 and 50 unchanged bytes
        self.assertEqual(modpack.coalesce(ranges, 64), [(0, 80), (144, 210)])
        self.assertEqual(modpack.coalesce(ranges, 63), [(0, 10), (73, 80), (144, 210)])
        self.assertEqual(modpack.coalesce(ranges, 50), ranges)


class ModpackRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="modpack-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.base, self.patched, self.base_bytes, self.patched_bytes = make_pair(self.tmp)
        self.pack = self.tmp / "edits.2k5patch"

    def export(self, **meta) -> dict:
        meta.setdefault("name", "Synthetic edits")
        meta.setdefault("author", "tests")
        meta.setdefault("version", "1")
        return modpack.export(self.base, self.patched, self.pack, meta, block=SMALL_BLOCK)

    def test_export_records_every_edit_as_a_verified_run(self) -> None:
        receipt = self.export()
        self.assertEqual(receipt["runs"], len(EDITS) - 1)          # 100..120 + 150..160 coalesce (gap 30 < 64)
        self.assertEqual(receipt["bytes"], 60 + 3 + 4 + 2 + 1000 + 6)
        self.assertEqual([(op["offset"], op["length"]) for op in receipt["ops"]],
                         [(100, 60), (5000, 3), (65534, 4), (524287, 2), (700000, 1000), (1048570, 6)])
        self.assertLess(receipt["pack_bytes"], 4096)
        self.assertFalse(receipt["base"]["is_retail"])
        self.assertEqual(receipt["result"]["sha256"], modpack.hash_file(self.patched))
        self.assertEqual(receipt["base"]["sha256"], modpack.hash_file(self.base))
        with zipfile.ZipFile(self.pack) as archive:
            self.assertEqual(sorted(archive.namelist()), ["manifest.json", "payload.bin"])
            for info in archive.infolist():
                self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["format"], 1)
        self.assertEqual(manifest["kind"], "2k5patch")
        self.assertEqual(manifest["game"], "nfl2k5-xbox")
        for op in manifest["ops"]:
            expected = self.base_bytes[op["offset"]:op["offset"] + op["length"]]
            self.assertEqual(op["expected_sha256"], modpack._sha256(expected))

    def test_inspect_reports_the_manifest_without_touching_images(self) -> None:
        self.export(description="scattered edits")
        info = modpack.inspect(self.pack)
        self.assertEqual(info["name"], "Synthetic edits")
        self.assertEqual(info["author"], "tests")
        self.assertEqual(info["description"], "scattered edits")
        self.assertEqual(info["runs"], 6)
        self.assertEqual(info["bytes"], 1075)
        self.assertEqual(info["assets"], [])
        self.assertEqual(info["operations"], [])
        self.assertEqual(info["regions"], [{"name": "(outside any file)", "runs": 6, "bytes": 1075}])

    def test_check_classifies_ready_applied_and_mismatch(self) -> None:
        self.export()
        self.assertEqual(modpack.check(self.pack, self.base)["state"], "ready")
        self.assertEqual(modpack.check(self.pack, self.patched)["state"], "applied")
        wrong = bytearray(self.base_bytes)
        wrong[700_500] ^= 1
        wrong_path = self.tmp / "wrong.xiso.iso"
        wrong_path.write_bytes(wrong)
        report = modpack.check(self.pack, wrong_path)
        self.assertEqual(report["state"], "mismatch")
        self.assertEqual(report["counts"], {"match": 5, "applied": 0, "mismatch": 1, "out_of_range": 0})
        self.assertEqual([run["index"] for run in report["runs"] if run["state"] == "mismatch"], [4])
        partial = bytearray(self.base_bytes)
        partial[100:160] = self.patched_bytes[100:160]
        partial_path = self.tmp / "partial.xiso.iso"
        partial_path.write_bytes(partial)
        self.assertEqual(modpack.check(self.pack, partial_path)["state"], "partial")
        short = self.tmp / "short.xiso.iso"
        short.write_bytes(self.base_bytes[:700_000])
        report = modpack.check(self.pack, short)
        self.assertEqual(report["state"], "mismatch")
        self.assertEqual(report["counts"]["out_of_range"], 2)
        self.assertFalse(report["size_matches_base"])
        hashed = modpack.check(self.pack, self.base, hash_image=True)
        self.assertTrue(hashed["image_matches_base_sha256"])
        self.assertFalse(hashed["image_is_retail"])

    def test_apply_reproduces_the_patched_image_exactly(self) -> None:
        self.export()
        out = self.tmp / "rebuilt.xiso.iso"
        stages: list[str] = []
        receipt = modpack.apply(self.pack, self.base, out, block=SMALL_BLOCK,
                                progress=lambda stage, done, total: stages.append(stage))
        self.assertEqual(out.read_bytes(), self.patched_bytes)
        self.assertEqual(self.base.read_bytes(), self.base_bytes)          # the source is untouched
        self.assertTrue(receipt["target"]["matches_author_result"])
        self.assertTrue(receipt["source"]["matches_base_sha256"])
        self.assertFalse(receipt["source"]["is_retail"])
        self.assertEqual(receipt["runs"], 6)
        self.assertIn("Copying and patching", stages)
        self.assertFalse(out.with_name(out.name + ".part").exists())
        # a second apply refuses to overwrite unless asked, then overwrites cleanly
        with self.assertRaises(modpack.ModpackError):
            modpack.apply(self.pack, self.base, out, block=SMALL_BLOCK)
        modpack.apply(self.pack, self.base, out, overwrite=True, block=SMALL_BLOCK, hash_streams=False)
        self.assertEqual(out.read_bytes(), self.patched_bytes)

    def test_apply_with_the_default_block_size_too(self) -> None:
        self.export()
        out = self.tmp / "rebuilt-default-block.xiso.iso"
        modpack.apply(self.pack, self.base, out)
        self.assertEqual(out.read_bytes(), self.patched_bytes)

    def test_apply_refuses_a_wrong_base_before_writing_anything(self) -> None:
        self.export()
        wrong = bytearray(self.base_bytes)
        wrong[5001] ^= 0x10
        wrong_path = self.tmp / "wrong.xiso.iso"
        wrong_path.write_bytes(wrong)
        out = self.tmp / "never.xiso.iso"
        with self.assertRaises(modpack.ModpackError) as caught:
            modpack.apply(self.pack, wrong_path, out, block=SMALL_BLOCK)
        self.assertIn("not the base", str(caught.exception))
        self.assertFalse(out.exists())
        self.assertFalse(out.with_name(out.name + ".part").exists())
        self.assertEqual(wrong_path.read_bytes(), bytes(wrong))
        with self.assertRaises(modpack.ModpackError):
            modpack.apply(self.pack, self.patched, out, block=SMALL_BLOCK)   # already applied is not "ready"
        self.assertFalse(out.exists())

    def test_apply_refuses_when_the_target_is_the_source(self) -> None:
        self.export()
        with self.assertRaises(modpack.ModpackError):
            modpack.apply(self.pack, self.base, self.base, overwrite=True, block=SMALL_BLOCK)
        self.assertEqual(self.base.read_bytes(), self.base_bytes)

    def test_apply_in_place_patches_an_existing_copy(self) -> None:
        self.export()
        copy = self.tmp / "copy.xiso.iso"
        shutil.copyfile(self.base, copy)
        receipt = modpack.apply(self.pack, copy, in_place=True)
        self.assertEqual(receipt["mode"], "in_place")
        self.assertEqual(copy.read_bytes(), self.patched_bytes)
        with self.assertRaises(modpack.ModpackError):
            modpack.apply_in_place(self.pack, copy)         # already applied
        self.assertEqual(copy.read_bytes(), self.patched_bytes)
        wrong = bytearray(self.base_bytes)
        wrong[1048571] ^= 0x01
        wrong_path = self.tmp / "wrong.xiso.iso"
        wrong_path.write_bytes(wrong)
        with self.assertRaises(modpack.ModpackError):
            modpack.apply_in_place(self.pack, wrong_path)
        self.assertEqual(wrong_path.read_bytes(), bytes(wrong))

    def test_export_refuses_identical_and_mismatched_inputs(self) -> None:
        same = self.tmp / "same.xiso.iso"
        shutil.copyfile(self.base, same)
        with self.assertRaises(modpack.ModpackError):
            modpack.export(self.base, same, self.pack, {"name": "x"}, block=SMALL_BLOCK)
        bigger = self.tmp / "bigger.xiso.iso"
        bigger.write_bytes(self.patched_bytes + b"\0")
        with self.assertRaises(modpack.ModpackError):
            modpack.export(self.base, bigger, self.pack, {"name": "x"}, block=SMALL_BLOCK)
        with self.assertRaises(modpack.ModpackError):
            modpack.export(self.base, self.patched, self.pack, {"name": ""}, block=SMALL_BLOCK)
        with self.assertRaises(modpack.ModpackError):
            modpack.export(self.base, self.patched, self.tmp / "edits.zip", {"name": "x"}, block=SMALL_BLOCK)
        self.assertFalse(self.pack.exists())

    def test_tampered_packs_are_refused(self) -> None:
        self.export()
        with zipfile.ZipFile(self.pack) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            payload = archive.read("payload.bin")

        def rewrite(path: Path, document: dict, data: bytes) -> None:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(document))
                archive.writestr("payload.bin", data)

        flipped = bytearray(payload)
        flipped[0] ^= 1
        edited = self.tmp / "payload-edited.2k5patch"
        rewrite(edited, manifest, bytes(flipped))
        with self.assertRaises(modpack.ModpackError):
            modpack.apply(edited, self.base, self.tmp / "no.xiso.iso", block=SMALL_BLOCK)
        moved = json.loads(json.dumps(manifest))
        moved["ops"][0]["offset"] = 10 ** 12
        far = self.tmp / "op-outside.2k5patch"
        rewrite(far, moved, payload)
        with self.assertRaises(modpack.ModpackError):
            modpack.load(far)
        overlapping = json.loads(json.dumps(manifest))
        overlapping["ops"][1]["offset"] = overlapping["ops"][0]["offset"]
        rewrite(far, overlapping, payload)
        with self.assertRaises(modpack.ModpackError):
            modpack.load(far)
        other_game = json.loads(json.dumps(manifest))
        other_game["game"] = "apf2k8-x360"
        rewrite(far, other_game, payload)
        with self.assertRaises(modpack.ModpackError):
            modpack.load(far)
        future = json.loads(json.dumps(manifest))
        future["format"] = 2
        rewrite(far, future, payload)
        with self.assertRaises(modpack.ModpackError):
            modpack.load(far)
        (self.tmp / "junk.2k5patch").write_bytes(b"not a zip")
        with self.assertRaises(modpack.ModpackError):
            modpack.load(self.tmp / "junk.2k5patch")
        with zipfile.ZipFile(self.tmp / "project.2k5patch", "w") as archive:
            archive.writestr("project.json", "{}")
        with self.assertRaises(modpack.ModpackError):
            modpack.load(self.tmp / "project.2k5patch")


class AssetAndRecipeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="modpack-assets-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.base, self.patched, _base, self.patched_bytes = make_pair(self.tmp)
        self.pack = self.tmp / "with-sources.2k5patch"
        rng = random.Random(11)
        self.sources = {
            "score_buga_modern.png": b"\x89PNG\r\n\x1a\n" + rng.randbytes(20_000),
            "commentary_0123.wav": b"RIFF" + rng.randbytes(50_000),
            "strings.txt": "Touchdown!\nSafety\n".encode("utf-8"),
            "layout.json": json.dumps({"root": [320, 424]}).encode("utf-8"),
            "notes.bin": rng.randbytes(500),
        }
        for name, data in self.sources.items():
            (self.tmp / name).write_bytes(data)

    def test_assets_round_trip_byte_for_byte_with_kinds_and_roles(self) -> None:
        operations = [
            {"op": "scorebug_layout", "layout_version": 2, "textures_asset": {"score_buga": "assets/texture/score_buga_modern.png"}},
            {"op": "audio_replace", "stream_id": 123, "asset": "assets/audio/commentary_0123.wav"},
            {"op": "text_edit", "bank": "game_strings", "entries": [{"id": 7, "text": "Touchdown!"}], "asset": "assets/text/strings.txt"},
        ]
        receipt = modpack.export(
            self.base, self.patched, self.pack,
            {"name": "With sources", "author": "tests",
             "assets": [self.tmp / "score_buga_modern.png",
                        {"path": self.tmp / "commentary_0123.wav", "role": "commentary.123"},
                        self.tmp / "strings.txt", self.tmp / "layout.json", self.tmp / "notes.bin"],
             "operations": operations},
            block=SMALL_BLOCK,
        )
        expected_members = {
            "assets/texture/score_buga_modern.png", "assets/audio/commentary_0123.wav",
            "assets/text/strings.txt", "assets/layout/layout.json", "assets/other/notes.bin",
        }
        self.assertEqual({asset["path"] for asset in receipt["assets"]}, expected_members)
        self.assertEqual(receipt["assets_bytes"], sum(len(data) for data in self.sources.values()))
        pack = modpack.load(self.pack)
        for asset in pack.manifest.assets:
            original = self.sources[asset.source_name]
            self.assertEqual(pack.read_asset(asset.path), original, asset.path)
            self.assertEqual(asset.size, len(original))
        self.assertEqual(pack.asset("assets/audio/commentary_0123.wav").role, "commentary.123")
        with zipfile.ZipFile(self.pack) as archive:
            for info in archive.infolist():
                self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED, info.filename)
        info = modpack.inspect(self.pack)
        self.assertEqual(len(info["assets"]), 5)
        self.assertEqual(info["operations"], operations)
        self.assertTrue(any(line.startswith("ESPN scorebug layout v2") for line in info["recipe_lines"]))
        self.assertTrue(any("stream 123" in line for line in info["recipe_lines"]))
        extracted = modpack.extract_assets(self.pack, self.tmp / "unpacked")
        self.assertEqual(extracted["assets"], 5)
        for name, data in self.sources.items():
            kind = {"png": "texture", "wav": "audio", "txt": "text", "json": "layout", "bin": "other"}[name.rsplit(".", 1)[1]]
            self.assertEqual((self.tmp / "unpacked" / "assets" / kind / name).read_bytes(), data)
        self.assertEqual(json.loads((self.tmp / "unpacked" / "recipe.json").read_text())["operations"], operations)
        # applying still uses only the byte runs
        out = self.tmp / "rebuilt.xiso.iso"
        modpack.apply(self.pack, self.base, out, block=SMALL_BLOCK)
        self.assertEqual(out.read_bytes(), self.patched_bytes)

    def test_a_studio_project_is_embedded_with_its_manifest(self) -> None:
        project = self.tmp / "my-edits.2k5mod"
        document = {"schema": "2k5_mod_studio_project/v1", "game": "espn_nfl_2k5_xbox",
                    "edits": [{"asset_id": "tex/1", "file": "replacements/tex1.png"}]}
        with zipfile.ZipFile(project, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.json", json.dumps(document))
            archive.writestr("replacements/tex1.png", self.sources["score_buga_modern.png"])
        receipt = modpack.export(self.base, self.patched, self.pack, {"name": "Project inside", "project": project}, block=SMALL_BLOCK)
        self.assertEqual({asset["path"] for asset in receipt["assets"]},
                         {"assets/project/project.json", "assets/project/tex1.png"})
        pack = modpack.load(self.pack)
        self.assertEqual(pack.manifest.recipe["project"], document)
        self.assertEqual(pack.read_asset("assets/project/tex1.png"), self.sources["score_buga_modern.png"])
        self.assertEqual(json.loads(pack.read_asset("assets/project/project.json")), document)
        self.assertTrue(any(line.startswith("Embedded studio project: 1") for line in modpack.inspect(pack)["recipe_lines"]))

    def test_a_recipe_may_not_name_an_asset_the_pack_lacks(self) -> None:
        with self.assertRaises(modpack.ModpackError):
            modpack.export(self.base, self.patched, self.pack,
                           {"name": "dangling", "operations": [{"op": "audio_replace", "asset": "assets/audio/missing.wav"}]},
                           block=SMALL_BLOCK)
        self.assertFalse(self.pack.exists())

    def test_a_missing_or_altered_asset_member_is_refused(self) -> None:
        modpack.export(self.base, self.patched, self.pack, {"name": "x", "assets": [self.tmp / "strings.txt"]}, block=SMALL_BLOCK)
        with zipfile.ZipFile(self.pack) as archive:
            members = {info.filename: archive.read(info.filename) for info in archive.infolist()}
        altered = self.tmp / "altered.2k5patch"
        with zipfile.ZipFile(altered, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in members.items():
                archive.writestr(name, b"Touchdown?\nSafety\n" if name == "assets/text/strings.txt" else data)
        with self.assertRaises(modpack.ModpackError):
            modpack.load(altered).read_asset("assets/text/strings.txt")
        missing = self.tmp / "missing.2k5patch"
        with zipfile.ZipFile(missing, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in members.items():
                if not name.startswith("assets/"):
                    archive.writestr(name, data)
        with self.assertRaises(modpack.ModpackError):
            modpack.load(missing)


class RegionLabellingTests(unittest.TestCase):
    """A real (tiny) XDVDFS image: runs are labelled with the file they fall in and
    offsets are partition-relative, so a raw dump with a video partition in front
    accepts the same pack."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="modpack-xdvdfs-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        rng = random.Random(5)
        self.files = {"default.xbe": b"XBEH" + rng.randbytes(9000), "field.pak": rng.randbytes(5000), "readme.txt": b"hello"}
        self.patched_files = dict(self.files)
        xbe = bytearray(self.files["default.xbe"])
        xbe[1000:1004] = b"\x01\x02\x03\x04"
        pak = bytearray(self.files["field.pak"])
        pak[4000:4100] = bytes(100)
        self.patched_files["default.xbe"] = bytes(xbe)
        self.patched_files["field.pak"] = bytes(pak)

    def test_runs_carry_file_names_and_survive_a_partition_offset(self) -> None:
        base = self.tmp / "base.xiso.iso"
        patched = self.tmp / "patched.xiso.iso"
        base.write_bytes(build_xdvdfs(self.files))
        patched.write_bytes(build_xdvdfs(self.patched_files))
        pack = self.tmp / "regions.2k5patch"
        receipt = modpack.export(base, patched, pack, {"name": "regions"}, block=SMALL_BLOCK)
        self.assertEqual({region["name"] for region in receipt["regions"]}, {"default.xbe", "field.pak"})
        self.assertEqual(receipt["regions"][0], {"name": "field.pak", "runs": 1, "bytes": 100})
        # the same game partition behind a 0x18300000-style prefix: offsets are relocated by the applier
        prefix = 3 * SECTOR
        raw_base = self.tmp / "raw-dump.iso"
        raw_base.write_bytes(build_xdvdfs(self.files, base_offset=prefix, tail_pad=SECTOR))
        report = modpack.check(pack, raw_base)
        self.assertEqual(report["state"], "ready")
        self.assertEqual(report["partition_base"], prefix)
        self.assertFalse(report["size_matches_base"])
        out = self.tmp / "raw-patched.iso"
        modpack.apply(pack, raw_base, out, block=SMALL_BLOCK)
        self.assertEqual(out.read_bytes(), build_xdvdfs(self.patched_files, base_offset=prefix, tail_pad=SECTOR))


class CommandLineTests(unittest.TestCase):
    def test_export_inspect_check_apply_extract_via_the_cli(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="modpack-cli-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        base, patched, _base_bytes, patched_bytes = make_pair(tmp)
        (tmp / "atlas.png").write_bytes(b"\x89PNG" + bytes(range(256)))
        (tmp / "recipe.json").write_text(json.dumps([{"op": "text_edit", "bank": "b", "entries": []}]))
        pack = tmp / "cli.2k5patch"
        tool = _REPO_ROOT / "tools" / "nfl2k5_modpack.py"
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT))

        def run(*argv: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, str(tool), *argv], capture_output=True, text=True, env=env, check=False)

        done = run("export", "--base", str(base), "--patched", str(patched), "--out", str(pack),
                   "--name", "CLI pack", "--author", "tests", "--asset", str(tmp / "atlas.png"), "--recipe", str(tmp / "recipe.json"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("6 run(s)", done.stdout)
        done = run("inspect", str(pack), "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        info = json.loads(done.stdout)
        self.assertEqual(info["name"], "CLI pack")
        self.assertEqual(info["assets"][0]["path"], "assets/texture/atlas.png")
        self.assertEqual(info["operations"][0]["op"], "text_edit")
        self.assertEqual(run("check", str(pack), "--image", str(base)).returncode, 0)
        self.assertEqual(run("check", str(pack), "--image", str(patched)).returncode, 1)
        out = tmp / "cli-out.xiso.iso"
        done = run("apply", str(pack), "--source", str(base), "--out", str(out))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(out.read_bytes(), patched_bytes)
        self.assertIn("byte-identical", done.stdout)
        done = run("apply", str(pack), "--source", str(patched), "--out", str(tmp / "never.iso"))
        self.assertEqual(done.returncode, 2)
        self.assertFalse((tmp / "never.iso").exists())
        done = run("extract", str(pack), "--out", str(tmp / "unpacked"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((tmp / "unpacked" / "assets" / "texture" / "atlas.png").read_bytes(), b"\x89PNG" + bytes(range(256)))


class ModularPackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modpack-ops-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.base, self.patched, self.base_bytes, self.patched_bytes = make_pair(self.tmp)
        self.pack = self.tmp / "modular.2k5patch"

    def mutate_manifest(self, edit):
        with zipfile.ZipFile(self.pack) as archive:
            members = {i.filename: archive.read(i.filename) for i in archive.infolist()}
        document = json.loads(members["manifest.json"])
        edit(document)
        members["manifest.json"] = json.dumps(document).encode()
        with zipfile.ZipFile(self.pack, "w", zipfile.ZIP_DEFLATED) as archive:
            for member, data in members.items():
                archive.writestr(member, data)

    def test_v2_byte_runs_have_identical_effect_to_legacy(self):
        legacy = self.tmp / "legacy.2k5patch"
        modpack.export(self.base, self.patched, legacy, {"name": "old"}, recipe=False)
        modpack.export(self.base, self.patched, self.pack, {"name": "new"}, format_version=2, recipe=False)
        self.assertEqual(modpack.inspect(legacy)["format"], 1)
        info = modpack.inspect(self.pack)
        self.assertEqual(info["format"], 2)
        self.assertEqual(info["min_reader_version"], 2)
        self.assertEqual([op["type"] for op in info["patch_operations"]], [0])
        for pack in (legacy, self.pack):
            self.assertEqual(modpack.check(pack, self.base)["state"], "ready")
            self.assertEqual(modpack.check(pack, self.patched)["state"], "applied")
            out = self.tmp / (pack.stem + ".iso")
            modpack.apply(pack, self.base, out, block=SMALL_BLOCK)
            self.assertEqual(out.read_bytes(), self.patched_bytes)

    def test_windows_lock_reproduction_rejects_open_source_and_target(self):
        replacement = self.tmp / "replacement.iso"
        replacement.write_bytes(self.patched_bytes)
        with windows_file_locks() as open_paths:
            for path in (replacement, self.base):
                fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
                try:
                    with self.assertRaises(PermissionError) as caught:
                        os.replace(replacement, self.base)
                    self.assertEqual(caught.exception.winerror, 5)
                    self.assertEqual(self.base.read_bytes(), self.base_bytes)
                finally:
                    os.close(fd)
            self.assertEqual(open_paths(), [])
            os.replace(replacement, self.base)
        self.assertEqual(self.base.read_bytes(), self.patched_bytes)

    def test_export_and_apply_close_handles_before_replacing_existing_files(self):
        out = self.tmp / "existing.iso"
        out.write_bytes(b"keep until commit")
        with windows_file_locks() as open_paths:
            replace = os.replace

            def commit(source, target):
                self.assertEqual(open_paths(), [], "all transaction handles must close before commit")
                return replace(source, target)

            with patch.object(os, "replace", side_effect=commit):
                for _ in range(2):
                    modpack.export(self.base, self.patched, self.pack, {"name": "portable"},
                                   format_version=2, recipe=False, overwrite=True)
                loaded = modpack.load(self.pack)
                self.assertEqual(modpack.check(loaded, self.base)["state"], "ready")
                self.assertEqual(open_paths(), [])
                modpack.apply(loaded, self.base, out, overwrite=True)
                self.assertEqual(out.read_bytes(), self.patched_bytes)
                modpack.apply_in_place(loaded, self.base)
                self.assertEqual(open_paths(), [])
        self.assertEqual(self.base.read_bytes(), self.patched_bytes)

    def test_in_place_accepts_equivalent_path_spellings(self):
        modpack.export(self.base, self.patched, self.pack, {"name": "portable"},
                       format_version=2, recipe=False)
        child = self.tmp / "child"
        child.mkdir()
        alias = child / ".." / self.base.name
        modpack.apply(self.pack, alias, self.base.resolve(), in_place=True)
        self.assertEqual(self.base.read_bytes(), self.patched_bytes)

    def test_locked_commit_keeps_existing_image_and_verified_part(self):
        modpack.export(self.base, self.patched, self.pack, {"name": "portable"},
                       format_version=2, recipe=False)
        out = self.tmp / "existing.iso"
        for in_place in (False, True):
            with self.subTest(in_place=in_place):
                target = self.base if in_place else out
                if not in_place:
                    out.write_bytes(b"keep until commit")
                before = target.read_bytes()
                with windows_file_locks() as open_paths:
                    fd = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0))
                    try:
                        with self.assertRaises(PermissionError):
                            if in_place:
                                modpack.apply_in_place(self.pack, self.base)
                            else:
                                modpack.apply(self.pack, self.base, out, overwrite=True)
                        self.assertEqual(open_paths(), [target.resolve()])
                    finally:
                        os.close(fd)
                self.assertEqual(target.read_bytes(), before)
                part = target.with_name(target.name + ".part")
                self.assertEqual(part.read_bytes(), self.patched_bytes)
                part.unlink()

    def test_payload_failure_releases_streams_even_with_a_retained_traceback(self):
        modpack.export(self.base, self.patched, self.pack, {"name": "portable"},
                       format_version=2, recipe=False)
        self.mutate_manifest(lambda d: d["ops"][0]["payload"].update(sha256="0" * 64))
        out = self.tmp / "existing.iso"
        out.write_bytes(b"keep until commit")
        failures = []
        with windows_file_locks() as open_paths:
            for action in (lambda: modpack.check(self.pack, self.base),
                           lambda: modpack.apply(self.pack, self.base, out, overwrite=True),
                           lambda: modpack.apply_in_place(self.pack, self.base)):
                try:
                    action()
                except modpack.ModpackError as exc:
                    failures.append(exc)  # GUI/error reporters may retain this frame.
                else:
                    self.fail("tampered payload was accepted")
                self.assertEqual(open_paths(), [])
                self.assertEqual(self.base.read_bytes(), self.base_bytes)
                self.assertEqual(out.read_bytes(), b"keep until commit")
                self.assertEqual(list(self.tmp.glob("*.part")), [])
        self.assertEqual(len(failures), 3)

    def test_source_guard_accepts_different_path_and_descriptor_metadata(self):
        modpack.export(self.base, self.patched, self.pack, {"name": "portable"},
                       format_version=2, recipe=False)
        real_stat = os.stat

        def windows_stat(path, *args, **kwargs):
            info = real_stat(path, *args, **kwargs)
            if Path(path) == self.base:
                # Windows path stat and CRT fstat can expose different file IDs
                # and timestamp precision for the very same unchanged file.
                values = list(info)
                values[1] += 1
                values[9] = int(info.st_ctime)
                return os.stat_result(values)
            return info

        with patch.object(os, "stat", side_effect=windows_stat):
            modpack.apply_in_place(self.pack, self.base)
        self.assertEqual(self.base.read_bytes(), self.patched_bytes)

    def test_changed_source_is_refused_before_commit_even_with_unchanged_size(self):
        modpack.export(self.base, self.patched, self.pack, {"name": "portable"},
                       format_version=2, recipe=False)
        stamp = self.base.stat()
        changed = bytearray(self.base_bytes)
        changed[2000] ^= 0xFF  # outside every patch run

        def change_source(stage, done, total):
            if stage == "Applying operations" and done == total:
                self.base.write_bytes(changed)
                os.utime(self.base, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))

        with windows_file_locks() as open_paths:
            with self.assertRaisesRegex(modpack.ModpackError, "source changed before"):
                modpack.apply_in_place(self.pack, self.base, progress=change_source)
            self.assertEqual(open_paths(), [])
        self.assertEqual(self.base.read_bytes(), changed)
        self.assertEqual(self.base.with_name(self.base.name + ".part").read_bytes(), self.patched_bytes)

    def test_source_replaced_during_final_verification_is_refused(self):
        modpack.export(self.base, self.patched, self.pack, {"name": "portable"},
                       format_version=2, recipe=False)
        replacement = self.tmp / "replacement.iso"
        changed = bytes([self.base_bytes[0] ^ 0xFF]) + self.base_bytes[1:]
        replacement.write_bytes(changed)
        verifying = None
        real_read, real_close = modpack._pread_exact, os.close

        def read(fd, length, at, what):
            nonlocal verifying
            if what == "source image before commit":
                verifying = fd
            return real_read(fd, length, at, what)

        def close(fd):
            nonlocal verifying
            real_close(fd)
            if fd == verifying:
                verifying = None
                # Close first so this real replacement also works on Windows.
                os.replace(replacement, self.base)

        with patch.object(modpack, "_pread_exact", side_effect=read), patch.object(os, "close", side_effect=close):
            with self.assertRaisesRegex(modpack.ModpackError, "source changed before"):
                modpack.apply_in_place(self.pack, self.base)
        self.assertEqual(self.base.read_bytes(), changed)
        self.assertEqual(self.base.with_name(self.base.name + ".part").read_bytes(), self.patched_bytes)

    def test_registering_a_handler_requires_no_format_or_dispatcher_change(self):
        from mod_editor.core import modpack_ops as ops
        class FutureRuns(ops.ByteRuns):
            name = "future_runs"
            min_reader_version = 3
        ops.register(99, FutureRuns)
        self.addCleanup(ops.REGISTRY.pop, 99, None)
        data = b"future"
        self.base.write_bytes(bytes(100))
        self.patched.write_bytes(data + bytes(100 - len(data)))
        member = "operations/future.bin"
        operation = {"type": 99, "name": "future_runs", "version": 1,
            "before_size": 100, "after_size": 100,
            "payload": {"member": member, "length": len(data), "sha256": modpack._sha256(data)},
            "runs": [{"op": "replace", "offset": 0, "length": len(data), "payload_offset": 0,
                "expected_sha256": modpack._sha256(bytes(len(data))), "new_sha256": modpack._sha256(data)}]}
        info = modpack.export(self.base, self.patched, self.pack, {"name": "future"}, recipe=False,
            patch_operations=[operation], operation_payloads={member: data})
        self.assertEqual(info["format"], 2)
        self.assertEqual(info["min_reader_version"], 3)
        out = self.tmp / "future.iso"
        modpack.apply(self.pack, self.base, out)
        self.assertEqual(out.read_bytes(), self.patched.read_bytes())
        ops.REGISTRY.pop(99)
        with self.assertRaisesRegex(modpack.ModpackError, "this mod needs a newer Mod Studio"):
            modpack.load(self.pack)

    def test_unknown_op_and_reader_fail_before_output(self):
        for field in ("type", "version", "reader", "registry"):
            modpack.export(self.base, self.patched, self.pack, {"name": "new"}, format_version=2, recipe=False, overwrite=True)
            def edit(d):
                if field == "reader":
                    d["min_reader_version"] = 999
                elif field == "registry":
                    d["op_registry_version"] = 999
                else:
                    d["ops"][0][field] = 999
            self.mutate_manifest(edit)
            out = self.tmp / "never.iso"
            with self.assertRaisesRegex(modpack.ModpackError, "this mod needs a newer Mod Studio"):
                modpack.apply(self.pack, self.base, out)
            self.assertFalse(out.exists())
            self.assertEqual(self.base.read_bytes(), self.base_bytes)

    def test_payload_and_per_run_hashes_fail_closed(self):
        for key in ("payload", "new_sha256", "expected_sha256"):
            modpack.export(self.base, self.patched, self.pack, {"name": "new"}, format_version=2, recipe=False, overwrite=True)
            def edit(d):
                if key == "payload":
                    d["ops"][0]["payload"]["sha256"] = "0" * 64
                else:
                    d["ops"][0]["runs"][0][key] = "0" * 64
            self.mutate_manifest(edit)
            with self.assertRaises(modpack.ModpackError):
                modpack.apply_in_place(self.pack, self.base)
            self.assertEqual(self.base.read_bytes(), self.base_bytes)
            self.assertFalse(self.base.with_name(self.base.name + ".part").exists())

    def test_named_file_replace_and_grow_round_trip(self):
        from mod_editor.core import nfl2k5_depth_chart_storage as storage
        original = {"default.xbe": b"XBEH" + bytes(100), "field.pak": b"old texture", "next.bin": b"adjacent file"}
        self.base.write_bytes(build_xdvdfs(original, tail_pad=13))
        for grow in (False, True):
            self.patched.write_bytes(self.base.read_bytes())
            replacement = b"new texture" if not grow else b"a much larger texture" * 301
            fd = modpack._open(self.patched, os.O_RDWR)
            try:
                size = os.fstat(fd).st_size
                node, sector, length = storage.image_file_node(lambda n, at: modpack._pread_exact(fd, n, at, "test"), 0, size, "field.pak")
                at = (size + SECTOR - 1) // SECTOR * SECTOR if grow else sector * SECTOR
                modpack._pwrite_all(fd, replacement, at, "test")
                if grow:
                    modpack._pwrite_all(fd, struct.pack("<II", at // SECTOR, len(replacement)), node, "test")
            finally:
                os.close(fd)
            receipt = modpack.export(self.base, self.patched, self.pack, {"name": "file"},
                file_operations=["field.pak"], recipe=False, overwrite=True)
            self.assertEqual([op["type"] for op in receipt["ops"]], [3 if grow else 2])
            self.assertEqual(modpack.check(self.pack, self.base)["state"], "ready")
            self.assertEqual(modpack.check(self.pack, self.patched)["state"], "applied")
            out = self.tmp / "file-out.iso"
            modpack.apply(self.pack, self.base, out, overwrite=True)
            self.assertEqual(out.read_bytes(), self.patched.read_bytes())
            fd = modpack._open(out, os.O_RDONLY)
            try:
                entries, _ = modpack._xdvdfs_module().parse_xdvdfs(fd, out.stat().st_size)
                for name, data in original.items():
                    e = entries[name]
                    self.assertEqual(modpack._pread_exact(fd, e.size, e.byte_offset, name), replacement if name == "field.pak" else data)
            finally:
                os.close(fd)

    def test_ordered_overlapping_operations_and_failure_are_transactional(self):
        from unittest.mock import patch
        from mod_editor.core import modpack_ops as ops
        self.base.write_bytes(bytes(128))
        self.patched.write_bytes(b"C" * 16 + bytes(112))
        operations, payloads = [], {}
        for i, (before, after) in enumerate(((bytes(16), b"B" * 16), (b"B" * 16, b"C" * 16))):
            member = f"operations/{i}.bin"
            payloads[member] = after
            operations.append({"type": 0, "name": "byte_runs", "version": 1,
                "before_size": 128, "after_size": 128,
                "payload": {"member": member, "length": 16, "sha256": modpack._sha256(after)},
                "runs": [{"op": "replace", "offset": 0, "length": 16, "payload_offset": 0,
                    "expected_sha256": modpack._sha256(before), "new_sha256": modpack._sha256(after)}]})
        modpack.export(self.base, self.patched, self.pack, {"name": "composed"}, recipe=False,
                       patch_operations=operations, operation_payloads=payloads)
        self.assertEqual(modpack.check(self.pack, self.base)["state"], "ready")
        self.assertEqual(modpack.check(self.pack, self.patched)["state"], "applied")
        original_write = modpack._pwrite_all
        def fail_second(fd, data, at, what):
            if what == "byte_runs" and data == b"C" * 16:
                raise OSError("injected write failure")
            return original_write(fd, data, at, what)
        with windows_file_locks() as open_paths, patch.object(modpack, "_pwrite_all", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "injected"):
                modpack.apply_in_place(self.pack, self.base)
            self.assertEqual(open_paths(), [])
        self.assertEqual(self.base.read_bytes(), bytes(128))
        self.assertFalse(self.base.with_name(self.base.name + ".part").exists())
        modpack.apply_in_place(self.pack, self.base)
        self.assertEqual(self.base.read_bytes(), self.patched.read_bytes())


class GrowingSpecialPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from unittest.mock import patch
        sys.path.insert(0, str(_REPO_ROOT / "tests"))
        from nfl2k5_depth_chart_rows_test import fixture, prepare
        from mod_editor.core import nfl2k5_depth_chart_storage as storage
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        cls.pin = patch.object(storage, "RETAIL_CONTENT_SHA256", modpack._sha256(bytes(storage.RETAIL_SIZE)))
        cls.pin.start()
        cls.addClassCleanup(cls.pin.stop)
        cls.retail = fixture()
        cls.special = bytes(rows.apply(prepare(cls.retail))[0])

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="modpack-special-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.base, self.patched, self.pack = [self.tmp / name for name in ("base.iso", "patched.iso", "special.2k5patch")]
        self.base.write_bytes(build_xdvdfs({"default.xbe": self.retail, "next.bin": b"neighbour"}, tail_pad=19))
        self.patched.write_bytes(self.base.read_bytes())
        from mod_editor.core import nfl2k5_depth_chart_storage as storage
        fd = modpack._open(self.patched, os.O_RDWR)
        try:
            storage.write_image_xbe(fd, self.special)
            modpack._pwrite_all(fd, b"HELLO", 123, "unrelated byte run")
        finally:
            os.close(fd)

    def test_special_round_trip_and_raw_partition(self):
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        receipt = modpack.export(self.base, self.patched, self.pack, {"name": "SPECIAL"}, recipe=True)
        self.assertEqual([op["type"] for op in receipt["ops"]], [0, 1])
        self.assertTrue(any(op["op"] == "depth_chart_rows" and op["enabled"] for op in receipt["operations"]))
        for prefix in (0, 3 * SECTOR):
            source, out = self.tmp / f"source-{prefix}.iso", self.tmp / f"out-{prefix}.iso"
            source.write_bytes(bytes(prefix) + self.base.read_bytes())
            self.assertEqual(modpack.check(self.pack, source)["state"], "ready")
            result = modpack.apply(self.pack, source, out)
            self.assertEqual(out.read_bytes(), bytes(prefix) + self.patched.read_bytes())
            self.assertEqual(modpack.check(self.pack, out)["state"], "applied")
            self.assertEqual(result["target"]["size"], self.patched.stat().st_size + prefix)
            fd = modpack._open(out, os.O_RDONLY)
            try:
                entries, _ = modpack._xdvdfs_module().parse_xdvdfs(fd, out.stat().st_size)
                e = entries["default.xbe"]
                xbe = modpack._pread_exact(fd, e.size, e.byte_offset, "default.xbe")
                self.assertEqual(xbe, self.special)
                self.assertEqual(rows.status(xbe), "applied")
                e = entries["next.bin"]
                self.assertEqual(modpack._pread_exact(fd, e.size, e.byte_offset, "next.bin"), b"neighbour")
            finally:
                os.close(fd)
        modpack.apply_in_place(self.pack, self.base)
        self.assertEqual(self.base.read_bytes(), self.patched.read_bytes())

    def test_unrecognised_size_change_and_extra_tail_refused(self):
        for tail in (b"extra bytes", b"\0"):
            with self.patched.open("ab") as stream:
                stream.write(tail)
            with self.assertRaisesRegex(modpack.ModpackError, "unrecognised image size change"):
                modpack.export(self.base, self.patched, self.pack, {"name": "bad"}, recipe=False)
            self.assertFalse(self.pack.exists())

    def test_wrong_old_xbe_and_corrupt_append_refused(self):
        modpack.export(self.base, self.patched, self.pack, {"name": "SPECIAL"}, recipe=False)
        for source in (self.base, self.patched):
            fd = modpack._open(source, os.O_RDWR)
            try:
                entries, _ = modpack._xdvdfs_module().parse_xdvdfs(fd, source.stat().st_size)
                e = entries["default.xbe"]
                modpack._pwrite_all(fd, b"BAD!", e.byte_offset + 500, "corrupt XBE")
            finally:
                os.close(fd)
            self.assertEqual(modpack.check(self.pack, source)["state"], "mismatch")
            before = modpack.hash_file(source)
            with self.assertRaises(modpack.ModpackError):
                modpack.apply_in_place(self.pack, source)
            self.assertEqual(modpack.hash_file(source), before)


if __name__ == "__main__":
    unittest.main()

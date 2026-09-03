"""Shareable disc patches (.2k5patch): export / inspect / check / apply on synthetic images.

Everything here is synthetic: a 1 MiB pseudo-random "base", a patched copy with
scattered edits, and a minimal real XDVDFS image for region labelling.  No game
data is read, so this runs on a bare CI runner.
"""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()

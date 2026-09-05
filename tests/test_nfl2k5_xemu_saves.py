"""tools/nfl2k5_xemu_saves.py on synthetic FATX partitions and hand-built qcow2 images.

Nothing here touches a real HDD image or a real save.  The FATX volume and the qcow2 container are
both generated in memory; when ``qemu-img`` happens to be installed the qcow2 reader is also checked
against a qcow2 qemu itself wrote (compressed), and qemu is asked to convert the hand-built one back.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import nfl2k5_xemu_saves as xs  # noqa: E402
from fatx_dirent_rename import FATX_SIGNATURE, FATX_PAGE_SIZE, FILE_ATTRIBUTE_DIRECTORY  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

CLUSTER = 0x1000


# --------------------------------------------------------------------------------------------- builders
class FatxBuilder:
    """A bare FATX16 partition (superblock at 0) holding an arbitrary small tree."""

    def __init__(self, cluster: int = CLUSTER, length: int = 0x300000) -> None:
        self.cluster = cluster
        self.length = length
        self.max_clusters = length // cluster + 1
        assert self.max_clusters < 0xFFF0
        fat_size = (self.max_clusters * 2 + FATX_PAGE_SIZE - 1) & ~(FATX_PAGE_SIZE - 1)
        self.file_area = FATX_PAGE_SIZE + fat_size
        self.buffer = bytearray(length)
        struct.pack_into("<IIII", self.buffer, 0, FATX_SIGNATURE, 0x1234ABCD, cluster // 0x200, 1)
        self.next_cluster = 1
        self.fat = [0] * self.max_clusters

    def _alloc(self, size: int) -> list[int]:
        count = max(1, (size + self.cluster - 1) // self.cluster)
        chain = list(range(self.next_cluster, self.next_cluster + count))
        self.next_cluster += count
        assert self.next_cluster < self.max_clusters, "synthetic volume too small"
        for a, b in zip(chain, chain[1:]):
            self.fat[a] = b
        self.fat[chain[-1]] = 0xFFFF
        return chain

    def _write(self, chain: list[int], data: bytes) -> None:
        for index, cluster in enumerate(chain):
            base = self.file_area + (cluster - 1) * self.cluster
            piece = data[index * self.cluster: (index + 1) * self.cluster]
            self.buffer[base: base + len(piece)] = piece

    @staticmethod
    def dirent(name: str, attributes: int, first: int, size: int) -> bytes:
        return struct.pack("<BB42sIIIII", len(name), attributes, name.encode("ascii").ljust(42, b"\xff"),
                           first, size, 0x3141, 0x5926, 0x5358)

    def add_tree(self, tree: dict, *, with_deleted: bool = False) -> int:
        """Directories are dicts, files are bytes.  Returns the first cluster of this directory."""

        chain = self._alloc(self.cluster)
        entries = bytearray()
        if with_deleted:
            entries += b"\xe5" + self.dirent("GHOST.TMP", 0, 0, 0)[1:]
        for name, item in tree.items():
            if isinstance(item, dict):
                first = self.add_tree(item)
                entries += self.dirent(name, FILE_ATTRIBUTE_DIRECTORY, first, 0)
            else:
                file_chain = self._alloc(len(item))
                self._write(file_chain, item)
                entries += self.dirent(name, 0, file_chain[0], len(item))
        entries += b"\xff" * 0x40                                        # end marker
        self._write(chain, bytes(entries))
        return chain[0]

    def build(self, root: dict) -> bytes:
        first = self.add_tree(root, with_deleted=True)
        assert first == 1
        struct.pack_into(f"<{self.max_clusters}H", self.buffer, FATX_PAGE_SIZE, *self.fat)
        return bytes(self.buffer)


def build_qcow2(raw: bytes, *, cluster_bits: int = 16, compressed: set[int] = frozenset(),
                zero: set[int] = frozenset(), skip: set[int] = frozenset()) -> bytes:
    """A qcow2 v3 image of ``raw``: plain clusters, plus chosen compressed / zero-flag / unallocated ones."""

    cs = 1 << cluster_bits
    guest_clusters = (len(raw) + cs - 1) // cs
    assert guest_clusters <= cs // 8
    layout = {"header": 0, "refcount_table": 1, "refcount_block": 2, "l1": 3, "l2": 4}
    data_first = 5
    image = bytearray(cs * data_first)
    l2 = [0] * (cs // 8)
    host_cluster = data_first
    for index in range(guest_clusters):
        piece = raw[index * cs: (index + 1) * cs].ljust(cs, b"\0")
        if index in skip:
            continue
        if index in zero:
            assert not any(piece), "zero-flag cluster must be all zero"
            l2[index] = xs.Qcow2Image.FLAG_ZERO
            continue
        if index in compressed:
            packed = zlib.compressobj(9, zlib.DEFLATED, -15)
            blob = packed.compress(piece) + packed.flush()
            sectors = (len(blob) + 511) // 512
            offset = host_cluster * cs
            shift = 62 - (cluster_bits - 8)
            l2[index] = xs.Qcow2Image.FLAG_COMPRESSED | ((sectors - 1) << shift) | offset
            image += blob.ljust(cs, b"\0")
        else:
            offset = host_cluster * cs
            l2[index] = (1 << 63) | offset
            image += piece
        host_cluster += 1
    total_clusters = host_cluster
    struct.pack_into(">4sIQIIQIIQQIIQQQQII", image, 0, b"QFI\xfb", 3, 0, 0, cluster_bits, len(raw), 0, 1,
                     layout["l1"] * cs, layout["refcount_table"] * cs, 1, 0, 0, 0, 0, 0, 4, 104)
    struct.pack_into(">Q", image, layout["refcount_table"] * cs, layout["refcount_block"] * cs)
    for cluster in range(total_clusters):
        struct.pack_into(">H", image, layout["refcount_block"] * cs + cluster * 2, 1)
    struct.pack_into(">Q", image, layout["l1"] * cs, (1 << 63) | (layout["l2"] * cs))
    struct.pack_into(f">{len(l2)}Q", image, layout["l2"] * cs, *l2)
    return bytes(image)


def fake_arena_save(size: int = xs.FRANCHISE_SAVE_SIZE, *, fill: int = 0x11) -> bytes:
    """The framing every real save carries (wrapper 0x2E0, preamble 0x300, version 0), body filler."""

    buf = bytearray(bytes([fill]) * size)
    buf[0x2E0:0x300] = b"ROST" + struct.pack("<I", xs.ROST_ARENA_LENGTH) + bytes(0x18)
    buf[0x300:0x320] = bytes(12) + b"ROST" + struct.pack("<Ii", 0, 0x20 - 0x14 + 1) + bytes(8)
    return bytes(buf)


def container(name: str, type_code: str, savegame: bytes, *, good_extra: bool = True) -> dict[str, bytes]:
    extra = rr.sign_save(savegame) if good_extra else bytes(20)
    return {"SaveMeta.xbx": b"\xff\xfe" + f"Name={name}\r\n".encode("utf-16-le"),
            "TYPE": f"{type_code}\0".encode("utf-16-le"), "SAVEGAME.DAT": savegame, "EXTRA": extra}


SAVES = {
    "256B40374FD6": ("Franchise1", "FXG", fake_arena_save(), True),
    "0B8506889D40": ("8007Fran", "FXG", fake_arena_save(fill=0x22), True),
    "83C3760943CB": ("Settings1", "STG", bytes(range(256)) * 2 + bytes(224), True),
    "0CE11954A556": ("06lions", "TMM", b"\x30\0\0\0" + bytes(11364), True),
    "006F00611262": ("Noah", "USR", b"TS" + bytes(20718), False),
    "0D0D0D0D0D0D": ("Odd one", "ZZZ", b"\x01\x02\x03", True),
    "AAAAAAAAAAAA": ("RosterOnly", "RST", fake_arena_save(0x91320 + 224, fill=0x33), True),
}
TITLE_FILES = {"TitleMeta.xbx": b"Title=ESPN NFL 2K5\r\n", "TitleImage.xbx": b"XPR0" + bytes(60),
               "SaveImage.xbx": b"XPR0" + bytes(28)}


def synthetic_volume() -> bytes:
    title = dict(TITLE_FILES)
    for uid, (name, code, payload, good) in SAVES.items():
        title[uid] = container(name, code, payload, good_extra=good)
    tree = {"UDATA": {xs.TITLE_ID: title, "4D530051": {"Other": b"x"}}, "TDATA": {xs.TITLE_ID: {}}, "CACHE": {}}
    return FatxBuilder().build(tree)


# --------------------------------------------------------------------------------------------- tests
class ClassifierTests(unittest.TestCase):
    def test_kinds_are_decided_from_bytes_and_type(self) -> None:
        self.assertEqual(xs.classify("FXG", fake_arena_save())[0], "franchise")
        self.assertEqual(xs.classify("RST", fake_arena_save(0x91320 + 224))[0], "roster")
        self.assertEqual(xs.classify("STG", bytes(736))[0], "settings")
        self.assertEqual(xs.classify("USR", bytes(100))[0], "profile")
        self.assertEqual(xs.classify("TMM", bytes(100))[0], "team")
        self.assertEqual(xs.classify("ZZZ", bytes(100))[0], "other")
        truncated = fake_arena_save()[:0x1000]                          # declared arena does not fit
        self.assertFalse(xs.arena_present(truncated))
        self.assertEqual(xs.classify("FXG", truncated)[0], "other")

    def test_meta_and_type_decoders(self) -> None:
        self.assertEqual(xs.decode_save_meta(b"\xff\xfe" + "Name=8007Fran\r\n".encode("utf-16-le")), "8007Fran")
        self.assertEqual(xs.decode_type("FXG\0".encode("utf-16-le")), "FXG")
        self.assertEqual(xs.safe_name("Odd one/two"), "Odd_one_two")


class SyntheticVolumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = synthetic_volume()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.raw_path = cls.root / "bare.img"
        cls.raw_path.write_bytes(cls.raw)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_lists_every_container_with_verified_signatures(self) -> None:
        listing = xs.scan_image(self.raw_path)
        self.assertIn("bare", listing.volume)
        self.assertEqual(set(listing.title_files), set(TITLE_FILES))
        by_uid = {save.uid: save for save in listing.saves}
        self.assertEqual(set(by_uid), set(SAVES))
        for uid, (name, code, payload, good) in SAVES.items():
            save = by_uid[uid]
            self.assertEqual((save.name, save.type_code, save.savegame, save.extra_verified), (name, code, payload, good))
            self.assertEqual(save.sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(by_uid["256B40374FD6"].kind, "franchise")
        self.assertTrue(by_uid["256B40374FD6"].arena_at_0x300)
        self.assertEqual(by_uid["AAAAAAAAAAAA"].kind, "roster")
        self.assertEqual(by_uid["83C3760943CB"].kind, "settings")
        self.assertEqual(by_uid["0CE11954A556"].kind, "team")
        self.assertEqual(by_uid["006F00611262"].kind, "profile")
        self.assertEqual(by_uid["0D0D0D0D0D0D"].kind, "other")
        self.assertEqual(by_uid["256B40374FD6"].folder, "256B40374FD6-Franchise1")
        self.assertEqual(by_uid["0D0D0D0D0D0D"].folder, "0D0D0D0D0D0D-Odd_one")

    def test_partition_map_image_is_found_at_x(self) -> None:
        offset, _length = xs.PARTITIONS["X"]
        mapped = self.root / "mapped.img"
        mapped.write_bytes(bytes(offset) + self.raw)
        listing = xs.scan_image(mapped)
        self.assertIn("partition X", listing.volume)
        self.assertEqual(len(listing.saves), len(SAVES))
        listing = xs.scan_image(mapped, partition="x")
        self.assertEqual(len(listing.saves), len(SAVES))
        with self.assertRaisesRegex(xs.XemuSaveError, "no FATX superblock"):
            xs.scan_image(mapped, partition="E")
        with self.assertRaisesRegex(xs.XemuSaveError, "no FATX volume"):
            xs.scan_image(_write(self.root / "empty.img", bytes(0x2000)))

    def test_extract_lays_out_fixture_folders_and_catalogue(self) -> None:
        out = self.root / "fixtures"
        receipt = xs.extract(self.raw_path, out)
        fran = out / "256B40374FD6-Franchise1" / "UDATA" / xs.TITLE_ID
        self.assertEqual((fran / "256B40374FD6" / "SAVEGAME.DAT").read_bytes(), SAVES["256B40374FD6"][2])
        self.assertEqual((fran / "256B40374FD6" / "EXTRA").read_bytes(), rr.sign_save(SAVES["256B40374FD6"][2]))
        self.assertEqual((fran / "TitleMeta.xbx").read_bytes(), TITLE_FILES["TitleMeta.xbx"])
        self.assertEqual(len(receipt["written"]), len(SAVES) * (4 + len(TITLE_FILES)))
        catalogue = (out / xs.CATALOGUE_NAME).read_text(encoding="utf-8")
        self.assertIn("**franchise**", catalogue)
        self.assertIn("**profile**", catalogue)
        self.assertIn("MISMATCH", catalogue)                              # the bad EXTRA is reported
        self.assertIn(f"{len(SAVES)} saves", catalogue)
        # the real container loader accepts what we wrote
        document = rr.SaveContainer.load(out / "256B40374FD6-Franchise1")
        self.assertTrue(document.verified)
        # a second run skips identical files; a changed file is refused without --overwrite
        again = xs.extract(self.raw_path, out)
        self.assertEqual(again["written"], [])
        self.assertEqual(len(again["skipped_identical"]), len(receipt["written"]))
        (fran / "TitleMeta.xbx").write_bytes(b"tampered")
        with self.assertRaisesRegex(xs.XemuSaveError, "--overwrite"):
            xs.extract(self.raw_path, out)
        xs.extract(self.raw_path, out, overwrite=True)
        self.assertEqual((fran / "TitleMeta.xbx").read_bytes(), TITLE_FILES["TitleMeta.xbx"])

    def test_source_image_is_never_written(self) -> None:
        before = hashlib.sha256(self.raw_path.read_bytes()).hexdigest()
        xs.scan_image(self.raw_path)
        xs.extract(self.raw_path, self.root / "fixtures2", catalogue=False)
        self.assertEqual(hashlib.sha256(self.raw_path.read_bytes()).hexdigest(), before)

    def test_cli_list_and_catalogue(self) -> None:
        stdout = io.StringIO()
        real = sys.stdout
        sys.stdout = stdout
        try:
            self.assertEqual(xs.main(["list", str(self.raw_path), "--json"]), 0)
        finally:
            sys.stdout = real
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["schema"], xs.SCHEMA)
        self.assertEqual({row["uid"] for row in report["saves"]}, set(SAVES))
        out = self.root / "fixtures3"
        self.assertEqual(xs.main(["extract", str(self.raw_path), str(out), "--no-catalogue"]), 0)
        self.assertFalse((out / xs.CATALOGUE_NAME).exists())
        self.assertEqual(xs.main(["catalogue", str(out)]), 0)
        self.assertTrue((out / xs.CATALOGUE_NAME).exists())
        self.assertEqual(xs.main(["list", str(self.root / "missing.img")]), 1)


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


class Qcow2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = synthetic_volume()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_hand_built_qcow2_reads_back_the_raw_bytes(self) -> None:
        clusters = (len(self.raw) + 0xFFFF) // 0x10000
        self.assertGreaterEqual(clusters, 3)
        zero_cluster = clusters - 1                                     # the tail of the volume is zero
        assert not any(self.raw[zero_cluster * 0x10000:]), "test expects a zero tail"
        image = build_qcow2(self.raw, compressed={1}, zero={zero_cluster}, skip=set())
        path = _write(self.root / "hand.qcow2", image)
        stream, size, fmt = xs.open_image(path)
        try:
            self.assertEqual((fmt, size), ("qcow2", len(self.raw)))
            stream.seek(0)
            self.assertEqual(stream.read(), self.raw)
            stream.seek(0x10000 - 5)
            self.assertEqual(stream.read(10), self.raw[0x10000 - 5: 0x10000 + 5])        # crosses a cluster edge
        finally:
            stream.close()
        # an unallocated cluster reads as zeros
        holey = build_qcow2(self.raw, skip={2})
        stream = xs.Qcow2Image(io.BytesIO(holey))
        stream.seek(2 * 0x10000)
        self.assertEqual(stream.read(0x10000), bytes(0x10000))
        # and the volume scan through qcow2 equals the raw scan
        listing = xs.scan_image(path)
        raw_listing = xs.scan_image(_write(self.root / "bare.img", self.raw))
        self.assertEqual([s.sha256 for s in listing.saves], [s.sha256 for s in raw_listing.saves])
        self.assertIn("qcow2 image", listing.volume)

    def test_unsupported_qcow2_features_are_refused(self) -> None:
        image = bytearray(build_qcow2(self.raw))
        struct.pack_into(">Q", image, 8, 0x1000)                          # backing file offset
        with self.assertRaisesRegex(xs.XemuSaveError, "backing file"):
            xs.Qcow2Image(io.BytesIO(bytes(image)))
        image = bytearray(build_qcow2(self.raw))
        struct.pack_into(">I", image, 32, 1)                              # AES
        with self.assertRaisesRegex(xs.XemuSaveError, "encrypted"):
            xs.Qcow2Image(io.BytesIO(bytes(image)))
        with self.assertRaisesRegex(xs.XemuSaveError, "not a qcow2"):
            xs.Qcow2Image(io.BytesIO(b"nope"))

    @unittest.skipUnless(shutil.which("qemu-img"), "qemu-img is not installed")
    def test_against_qemu_img(self) -> None:
        raw_path = _write(self.root / "q.raw", self.raw)
        made = self.root / "qemu.qcow2"
        subprocess.run(["qemu-img", "convert", "-O", "qcow2", "-c", str(raw_path), str(made)], check=True)
        stream = xs.Qcow2Image(open(made, "rb"))
        try:
            self.assertEqual(stream.read(), self.raw)
        finally:
            stream.close()
        hand = _write(self.root / "hand2.qcow2", build_qcow2(self.raw, compressed={0, 1}))
        back = self.root / "back.raw"
        subprocess.run(["qemu-img", "convert", "-O", "raw", str(hand), str(back)], check=True)
        self.assertEqual(back.read_bytes().rstrip(b"\0"), self.raw.rstrip(b"\0"))


REAL_IMAGE = os.environ.get("NFL2K5_XEMU_IMAGE")


@unittest.skipUnless(REAL_IMAGE and Path(REAL_IMAGE).is_file(), "set NFL2K5_XEMU_IMAGE to a COPY of xbox_hdd.qcow2/raw")
class RealImageTests(unittest.TestCase):
    def test_real_image_lists_verified_saves(self) -> None:
        listing = xs.scan_image(REAL_IMAGE)
        self.assertGreaterEqual(len(listing.saves), 1)
        for save in listing.saves:
            self.assertTrue(save.extra_verified, f"{save.uid} {save.name}: EXTRA does not verify")


if __name__ == "__main__":
    unittest.main()

"""Check my SOFTDRINK disc (b780 n4): tell a damaged or cut-short copy apart from a real game bug.

The game streams commentary and other resources from the disc through the post-play and play-call screens, so a bad
copy freezes exactly where Smuzz's reports did. ``nfl2k5_disc_check`` hashes the image's files through the disc
directory and compares them with the released disc's file list. These tests use small real XDVDFS images (the
xiso layout test's builder) and a released-disc record made from one of them."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools")]

from mod_editor.core import nfl2k5_disc_check as dc  # noqa: E402
from tests.mod_editor.test_xiso_layout_tolerance import build_xdvdfs, write_xdvdfs  # noqa: E402

V08_SHA256 = "b0a72eda50ea9b90c643ed5b36da8450162527a928d949bf0bef60afd5782ad5"


def files(seed: int = 0) -> dict[str, bytes]:
    pattern = bytes((i * 7 + seed) & 0xFF for i in range(4096))
    return {"default.xbe": b"XBEH" + pattern * 3,
            "big.bin": pattern * 600,            # about 2.4 MB: several 512 KiB chunks in these tests
            "small.txt": b"hello"}


class DiscCheckTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.chunk = mock.patch.object(dc, "CHUNK", 512 << 10)
        self.chunk.start()
        self.release = self.root / "release.xiso.iso"
        self.release.write_bytes(build_xdvdfs(files()))
        self.entry = dc.make_entry("Test release", self.release)
        self.releases = [self.entry]

    def tearDown(self):
        self.chunk.stop()
        self.dir.cleanup()

    def write(self, name: str, blob: bytes) -> Path:
        path = self.root / name
        path.write_bytes(blob)
        return path

    def test_the_record_carries_the_whole_image_hash_and_every_file(self):
        self.assertEqual(self.entry["image_sha256"], hashlib.sha256(self.release.read_bytes()).hexdigest())
        self.assertEqual(set(self.entry["files"]), {"default.xbe", "big.bin", "small.txt"})
        self.assertGreater(len(self.entry["files"]["big.bin"]["chunks"]), 3)

    def test_an_identical_copy_matches_even_as_a_raw_dump(self):
        result = dc.check(self.release, releases=self.releases)
        self.assertEqual(result["state"], "matches", result)
        raw = self.root / "raw.iso"
        write_xdvdfs(raw, files(), base_offset=0x18300000)      # redump layout, written sparse
        self.assertEqual(dc.check(raw, releases=self.releases)["state"], "matches")
        self.assertIn("matches Test release", dc.describe(result))

    def test_a_damaged_copy_names_the_file_and_the_place(self):
        blob = bytearray(self.release.read_bytes())
        big = self.entry["files"]["big.bin"]
        image = build_xdvdfs(files())
        start = image.find(files()["big.bin"][:4096 * 2])
        blob[start + (1 << 20) + 5] ^= 0xFF          # one byte inside the third 512 KiB piece of big.bin
        result = dc.check(self.write("bad.iso", bytes(blob)), releases=self.releases)
        self.assertEqual(result["state"], "damaged", result)
        self.assertEqual([d["file"] for d in result["differing"]], ["big.bin"])
        self.assertEqual(result["differing"][0]["mib"], [[1.0, 1.5]])
        text = dc.describe(result)
        self.assertIn("damaged or incomplete copy", text)
        self.assertIn("big.bin differs at 1.0-1.5 MiB", text)
        self.assertNotIn("—", text)
        self.assertEqual(big["size"], len(files()["big.bin"]))

    def test_a_copy_cut_short_says_how_much_can_be_read(self):
        blob = self.release.read_bytes()
        image = build_xdvdfs(files())
        start = image.find(files()["big.bin"][:4096 * 2])
        cut = self.write("cut.iso", blob[:start + 700_000])
        result = dc.check(cut, releases=self.releases)
        self.assertEqual(result["state"], "damaged", result)
        self.assertTrue(any(c["file"] == "big.bin" for c in result["cut_short"]))
        self.assertIn("cut short", dc.describe(result))

    def test_a_different_build_is_not_called_damaged(self):
        other = self.write("custom.iso", build_xdvdfs(files(seed=99)))
        result = dc.check(other, releases=self.releases)
        self.assertEqual(result["state"], "different", result)
        self.assertIn("Customize SOFTDRINK", dc.describe(result))

    def test_not_a_disc_image(self):
        result = dc.check(self.write("junk.iso", b"\0" * 300_000), releases=self.releases)
        self.assertEqual(result["state"], "unreadable")
        self.assertIn("not a readable Xbox disc image", dc.describe(result))

    def test_the_shipped_list_holds_the_v0_8_release(self):
        discs = dc.load_releases()
        v08 = next(d for d in discs if d["name"] == "SOFTDRINK 2K28 v0.8")
        self.assertEqual(v08["image_sha256"], V08_SHA256)
        self.assertEqual(v08["image_size"], 6_335_561_728)
        self.assertEqual(len(v08["files"]), 20)
        for name, record in v08["files"].items():
            self.assertEqual(len(record["chunks"]), max(1, -(-record["size"] // v08["chunk"])), name)

    def test_the_command_line_exit_code(self):
        with mock.patch.object(dc, "load_releases", return_value=self.releases), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            self.assertEqual(dc.main([str(self.release)]), 0)
            other = self.write("custom2.iso", build_xdvdfs(files(seed=3)))
            self.assertEqual(dc.main([str(other)]), 1)


class SameNamesReleaseTests(unittest.TestCase):
    """b780: v0.8 and v0.9 have the same 20 file names. The check used to pick the release by name overlap alone, so
    the tie went to the first record (v0.8) and every v0.9 disc read as "damaged" (default.xbe size, vc_53450030)."""

    V09_ENTRY = REPO / "tests/fixtures/nfl2k5_softdrink_v09_disc_entry.json"   # ship10's record of the v0.9 disc

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.chunk = mock.patch.object(dc, "CHUNK", 512 << 10)
        self.chunk.start()
        self.old_image = self.root / "old.xiso.iso"
        self.new_image = self.root / "new.xiso.iso"
        self.old_image.write_bytes(build_xdvdfs(files()))
        self.new_image.write_bytes(build_xdvdfs(files(seed=5)))          # every name and size the same
        self.old = dc.make_entry("Old release", self.old_image)
        self.new = dc.make_entry("New release", self.new_image)

    def tearDown(self):
        self.chunk.stop()
        self.dir.cleanup()

    def test_each_disc_matches_its_own_release_whatever_the_record_order(self):
        self.assertEqual(set(self.old["files"]), set(self.new["files"]))
        self.assertEqual(self.old["image_size"], self.new["image_size"])
        for releases in ([self.old, self.new], [self.new, self.old]):
            for image, name in ((self.old_image, "Old release"), (self.new_image, "New release")):
                result = dc.check(image, releases=releases)
                self.assertEqual((result["state"], result["release"]), ("matches", name), result)

    def test_a_damaged_new_disc_is_damaged_against_the_new_release(self):
        blob = bytearray(self.new_image.read_bytes())
        at = bytes(blob).index(files(seed=5)["big.bin"][:4096]) + 700_000
        blob[at:at + 64] = bytes(64)
        bad = self.root / "bad.iso"
        bad.write_bytes(bytes(blob))
        for releases in ([self.old, self.new], [self.new, self.old]):
            result = dc.check(bad, releases=releases)
            self.assertEqual((result["state"], result["release"]), ("damaged", "New release"), result)
            self.assertEqual([d["file"] for d in result["differing"]], ["big.bin"])

    def test_the_real_v0_9_record_outranks_v0_8_for_a_v0_9_disc(self):
        """The shipped v0.8 record and ship10's v0.9 record share all 20 names; without reading a disc, a v0.9 image's
        files (sizes and hashes from its record) rank v0.9 first, whole or with one damaged file."""
        v08 = next(d for d in dc.load_releases() if d["name"] == "SOFTDRINK 2K28 v0.8")
        v09 = json.loads(self.V09_ENTRY.read_text(encoding="utf-8"))
        self.assertEqual(set(v08["files"]), set(v09["files"]))
        entries = {k.lower(): mock.Mock(size=v["size"], path=k) for k, v in v09["files"].items()}
        for damaged in (None, "big_file"):
            hashed = {k.lower(): (v["sha256"], list(v["chunks"]), v["size"]) for k, v in v09["files"].items()}
            if damaged:
                name = max(v09["files"], key=lambda k: v09["files"][k]["size"])
                digest, chunks, size = hashed[name.lower()]
                hashed[name.lower()] = ("0" * 64, ["0" * len(chunks[0])] + chunks[1:], size)
            ranked = []
            for order, record in enumerate([v08, v09]):
                result = dc._compare(record, None, v09["image_size"], 0, entries, dict(hashed), None)
                ranked.append((dc._rank(result, record, v09["image_size"], order), result))
            best = max(ranked, key=lambda item: item[0])[1]
            self.assertEqual(best["release"], "SOFTDRINK 2K28 v0.9")
            self.assertEqual(best["state"], "damaged" if damaged else "matches")


if __name__ == "__main__":
    unittest.main()

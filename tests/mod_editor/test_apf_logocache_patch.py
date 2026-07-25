"""Writer-contract tests for the APF ``uniform_logocache`` logo writer.

Proves, entirely offline against the extracted retail ``0A`` and without copying
the 1.1 GB volume (that end-to-end path is the standalone
``tests/apf_logocache_patch_test.py`` with ``--full-copy``):

* the pinned retail directory/payload hashes and F0985030 structure still hold;
* a controlled edit of one catalog index rewrites ONLY that entry's VRAM
  base level(s): every DRAM part and every packed mip tail is byte-preserved,
  and every OTHER catalog entry's stored sub-block is preserved verbatim (just
  relocated) — an independent decompression oracle confirms the intended base is
  present and nothing else decodes differently;
* the directory stays exactly 40,960 B and changes only inside auxiliary records;
* the repacked payload stays inside its fixed ``0x9E0800`` allocation; and
* the writer fails closed on a drifted directory/payload hash, a wrong PNG size,
  and an out-of-range catalog index.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_inner  # noqa: E402
import apf_logocache_patch as cache_patch  # noqa: E402
from apf_logo_patch import decode_4444_base, encode_4444_base  # noqa: E402


INDEX_PATH = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"
DISC_AVAILABLE = INDEX_PATH.exists()
CATALOG = 1  # uniform_logo_01; cache 01_logo_l0 base == the pinned package base


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decompress_part_b(payload: bytes, stream_b: int, len_b: int) -> bytes:
    stored = payload[stream_b : stream_b + len_b]
    magic, uncompressed, compressed, unknown, shift = struct.unpack_from(">5I", stored, 0)
    return apf_inner.decompress_h7a(stored[0x14:], uncompressed, shift)


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class CacheWriterPinTests(unittest.TestCase):
    def test_pinned_layout(self) -> None:
        self.assertEqual(cache_patch.DIR_PACK_OFFSET, 53221376)
        self.assertEqual(cache_patch.DIR_SIZE, 0xA000)
        self.assertEqual(cache_patch.PAYLOAD_PACK_OFFSET, 1039226880)
        self.assertEqual(cache_patch.PAYLOAD_SIZE, 0x9E0800)
        self.assertEqual(cache_patch.FILE_COUNT, 236)

    def test_retail_hashes_and_directory_parse(self) -> None:
        _, _, _, dir_raw, pay_raw = cache_patch._read_pair(INDEX_PATH)
        self.assertEqual(_sha(dir_raw), cache_patch.EXPECTED_DIR_SHA256)
        self.assertEqual(_sha(pay_raw), cache_patch.EXPECTED_PAYLOAD_SHA256)
        directory = cache_patch.parse_cache_directory(dir_raw)
        self.assertEqual(len(directory.entries), 236)
        self.assertEqual(directory.total_stream_length, 0x9E04A6)
        # cache 01_logo_l0 base is byte-identical to the pinned package base.
        target = cache_patch._extract_target(directory, pay_raw, "01_logo_l0", None)
        self.assertEqual(
            _sha(target.base),
            "5683fb638cf72e4532149f757ac49d702a6d158043faa930c58745a1b81f9037",
        )


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class CacheWriterRoundTripTests(unittest.TestCase):
    def _assert_only_intended_changed(
        self, result: cache_patch.CachePatchResult, changed_names: set[str]
    ) -> None:
        _, _, _, dir_raw, pay_raw = cache_patch._read_pair(INDEX_PATH)
        src = cache_patch.parse_cache_directory(dir_raw)
        out = cache_patch.parse_cache_directory(result.directory_bytes)
        self.assertEqual(len(result.directory_bytes), cache_patch.DIR_SIZE)
        self.assertEqual(len(result.payload_bytes), cache_patch.PAYLOAD_SIZE)

        observed_changed = set()
        for src_e, out_e in zip(src.entries, out.entries):
            self.assertEqual(src_e.name, out_e.name)
            # DRAM part A: stored bytes preserved verbatim (relocated).
            src_a = pay_raw[src_e.stream_a : src_e.stream_a + src_e.len_a]
            out_a = result.payload_bytes[out_e.stream_a : out_e.stream_a + out_e.len_a]
            self.assertEqual(src_a, out_a, f"{src_e.name} DRAM changed")
            src_b = pay_raw[src_e.stream_b : src_e.stream_b + src_e.len_b]
            out_b = result.payload_bytes[out_e.stream_b : out_e.stream_b + out_e.len_b]
            if src_e.name in changed_names:
                # decoded base differs; mip tail identical.
                src_vram = _decompress_part_b(pay_raw, src_e.stream_b, src_e.len_b)
                out_vram = _decompress_part_b(result.payload_bytes, out_e.stream_b, out_e.len_b)
                self.assertNotEqual(src_vram[:0x80000], out_vram[:0x80000])
                self.assertEqual(src_vram[0x80000:], out_vram[0x80000:])
                observed_changed.add(src_e.name)
            else:
                # Unedited: stored sub-block byte-identical (relocation only).
                self.assertEqual(src_b, out_b, f"{src_e.name} unedited sub-block changed")
        self.assertEqual(observed_changed, changed_names)

        # Directory changes confined to auxiliary records.
        aux_lo = 0x1688 + 236 * 4
        aux_hi = aux_lo + 236 * 0x10
        for i in range(len(dir_raw)):
            if dir_raw[i] != result.directory_bytes[i]:
                self.assertTrue(aux_lo <= i < aux_hi, f"directory changed at 0x{i:x}")

    def test_single_layer_edit(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "l0.png"
            Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(png)
            result = cache_patch.build_cache_patch(INDEX_PATH, CATALOG, png)
        self.assertEqual(result.manifest["mode"], "patched")
        self.assertEqual(result.manifest["validation"]["changed_cache_entries"], [65])
        self.assertGreaterEqual(result.manifest["payload"]["allocation_slack_after"], 0)
        self.assertEqual(
            result.manifest["layers"]["01_logo_l0"]["decode_back_max_abs_error"], 0
        )
        self._assert_only_intended_changed(result, {"01_logo_l0"})

    def test_both_layers_edit(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            png0 = Path(d) / "l0.png"
            png1 = Path(d) / "l1.png"
            Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(png0)
            Image.new("RGBA", (512, 512), (0, 255, 255, 255)).save(png1)
            result = cache_patch.build_cache_patch(INDEX_PATH, CATALOG, png0, png1)
        self.assertEqual(result.manifest["mode"], "patched")
        self.assertEqual(
            result.manifest["validation"]["changed_cache_entries"], [56, 65]
        )
        self.assertGreaterEqual(result.manifest["payload"]["allocation_slack_after"], 0)
        self._assert_only_intended_changed(result, {"01_logo_l0", "01_logo_l1"})

    def test_no_op_returns_source_pair(self) -> None:
        _, _, _, dir_raw, pay_raw = cache_patch._read_pair(INDEX_PATH)
        directory = cache_patch.parse_cache_directory(dir_raw)
        t0 = cache_patch._extract_target(directory, pay_raw, "01_logo_l0", None)
        t1 = cache_patch._extract_target(directory, pay_raw, "01_logo_l1", None)
        with tempfile.TemporaryDirectory() as d:
            png0 = Path(d) / "r0.png"
            png1 = Path(d) / "r1.png"
            Image.frombytes("RGBA", (512, 512), t0.rgba).save(png0)
            Image.frombytes("RGBA", (512, 512), t1.rgba).save(png1)
            result = cache_patch.build_cache_patch(INDEX_PATH, CATALOG, png0, png1)
        self.assertEqual(result.manifest["mode"], "no_op")
        self.assertEqual(result.directory_bytes, dir_raw)
        self.assertEqual(result.payload_bytes, pay_raw)


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class CacheWriterFailClosedTests(unittest.TestCase):
    def _magenta(self, directory: Path) -> Path:
        png = directory / "m.png"
        Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(png)
        return png

    def test_out_of_range_catalog_index_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(cache_patch.PatchError):
                cache_patch.build_cache_patch(INDEX_PATH, 999, self._magenta(Path(d)))

    def test_wrong_png_dimensions_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "bad.png"
            Image.new("RGBA", (256, 256), (1, 2, 3, 4)).save(png)
            with self.assertRaises(cache_patch.PatchError):
                cache_patch.build_cache_patch(INDEX_PATH, CATALOG, png)

    def test_drifted_directory_hash_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            with patch.object(cache_patch, "EXPECTED_DIR_SHA256", "0" * 64):
                with self.assertRaisesRegex(cache_patch.PatchError, "directory hash"):
                    cache_patch.build_cache_patch(INDEX_PATH, CATALOG, self._magenta(Path(d)))

    def test_drifted_payload_hash_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            with patch.object(cache_patch, "EXPECTED_PAYLOAD_SHA256", "0" * 64):
                with self.assertRaisesRegex(cache_patch.PatchError, "payload hash"):
                    cache_patch.build_cache_patch(INDEX_PATH, CATALOG, self._magenta(Path(d)))

    def test_oversize_repack_fails_closed(self) -> None:
        # A high-entropy (incompressible) base grows its VRAM sub-block far past
        # the retail payload's 858-byte tail slack; the writer must refuse rather
        # than overflow the fixed 0x9E0800 allocation.
        import random

        noise = random.Random(1234).randbytes(512 * 512 * 4)
        with tempfile.TemporaryDirectory() as d:
            png = Path(d) / "noise.png"
            Image.frombytes("RGBA", (512, 512), noise).save(png)
            with self.assertRaisesRegex(cache_patch.PatchError, "exceeds the fixed"):
                cache_patch.build_cache_patch(INDEX_PATH, CATALOG, png)


if __name__ == "__main__":
    unittest.main()

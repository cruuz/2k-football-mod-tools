#!/usr/bin/env python3
"""Bounded integration tests for the Crib bar-monitor SCNE writer."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_crib_bar_monitor_png_xiso as writer  # noqa: E402
from nfl_txtr import HEADER, decode_chunk  # noqa: E402


SOURCE_XISO = ROOT / "ESPN NFL 2K5 (USA).xiso.iso"


def _source_span() -> bytes:
    if not SOURCE_XISO.is_file():
        raise unittest.SkipTest("pinned private NFL 2K5 XISO is unavailable")
    with SOURCE_XISO.open("rb") as stream:
        stream.seek(writer.SPAN_ABSOLUTE)
        value = stream.read(writer.SPAN_SIZE)
    assert len(value) == writer.SPAN_SIZE
    return value


def _safe_four_color_rgba() -> bytes:
    """High-detail 2x2 blocks inside the proved fixed-span/scratch envelope."""

    colors = (
        (8, 12, 28, 255),
        (232, 236, 244, 255),
        (18, 92, 180, 255),
        (128, 128, 140, 255),
    )
    state = 0x2A5F19C3
    blocks: list[int] = []
    for _ in range(64 * 64):
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= state >> 17
        state ^= (state << 5) & 0xFFFFFFFF
        blocks.append(state & 3)
    result = bytearray()
    for y in range(128):
        for x in range(128):
            result.extend(colors[blocks[(y // 2) * 64 + (x // 2)]])
    return bytes(result)


class BarMonitorWriterTests(unittest.TestCase):
    def test_verified_staging_is_hidden_until_no_replace_publish(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfl2k5-bar-monitor-test-") as raw:
            root = Path(raw)
            final = root / "modded.xiso"
            staging = writer.reserve_staging(final, "test")
            try:
                payload = b"verified-staging-payload"
                writer.pwrite_all(staging.descriptor, 0, payload)
                self.assertFalse(final.exists())
                published = writer.publish_owned(staging, final)
                self.assertEqual(published[1], staging.identity)
                self.assertEqual(final.read_bytes(), payload)
                writer.unlink_identity(staging.path, staging.identity)
            finally:
                os.close(staging.descriptor)

    def test_compile_replaces_only_bar_monitor_allocation(self) -> None:
        source_span = _source_span()
        replacement, preview, report = writer.compile_replacement(
            source_span, _safe_four_color_rgba()
        )

        self.assertEqual(len(replacement), len(source_span))
        self.assertEqual(len(replacement), writer.SPAN_SIZE)
        self.assertEqual(
            replacement[-writer.OPAQUE_TAIL_SIZE:],
            source_span[-writer.OPAQUE_TAIL_SIZE:],
        )
        self.assertTrue(report["decoded"]["changes_bounded_to_target_allocation"])
        self.assertTrue(report["decoded"]["system_geometry_identical"])
        self.assertLessEqual(
            report["compression"]["encoded_bytes"], writer.RETAIL_CONSUMED
        )
        self.assertLessEqual(
            report["compression"]["required_aligned_scratch_bytes"],
            writer.MAX_SAFE_SCRATCH,
        )
        self.assertTrue(preview.startswith(b"\x89PNG\r\n\x1a\n"))

        scratch = HEADER.unpack_from(replacement)[5]
        decoded, info = decode_chunk(
            replacement, writer.resource_record(scratch).as_chunk()
        )
        self.assertIsNotNone(info)
        self.assertEqual(
            hashlib.sha256(decoded).hexdigest(), report["decoded"]["sha256"]
        )
        self.assertEqual(
            hashlib.sha256(writer.preview_rgba(preview)).hexdigest(),
            report["mips"]["decoded_level_rgba_sha256"][0],
        )

    def test_very_compressible_image_fails_conservative_scratch_bound(self) -> None:
        source_span = _source_span()
        rgba = bytes((24, 48, 96, 255)) * (128 * 128)
        with self.assertRaisesRegex(writer.BarMonitorError, "compresses outside"):
            writer.compile_replacement(source_span, rgba)


if __name__ == "__main__":
    unittest.main()

"""The APF crest-box patch must stay atomic, guarded and retail-free."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_crest_box_patch as patch  # noqa: E402


def _synthetic_retail_image() -> tuple[bytes, int]:
    base = patch.RETAIL_PACKET_ADDRESSES[0] - 0x1000
    size = patch.RETAIL_PACKET_ADDRESSES[-1] - base + 0x1000
    image = bytearray(size)
    image[:2] = b"MZ"
    packet = patch.PACKET_HEADER + struct.pack(">4f", *patch.RETAIL_TRANSFORM)
    for address in patch.RETAIL_PACKET_ADDRESSES:
        start = address - base - len(patch.PACKET_HEADER)
        image[start : start + len(packet)] = packet
    return bytes(image), base


class CrestBoxPatchTests(unittest.TestCase):
    def test_eagles_coverage_is_centred_and_about_one_point_four_x(self) -> None:
        scale_u, scale_v, offset_u, offset_v = patch.transform_for_coverage(1.4)
        self.assertAlmostEqual(scale_u, 1 / 1.4, places=6)
        self.assertEqual(scale_u, scale_v)
        self.assertEqual(offset_u, offset_v)
        self.assertAlmostEqual(offset_u, (1 - scale_u) / 2, places=6)

    def test_unsafe_coverage_is_refused(self) -> None:
        for value in (1.0, 2.01, -1, True, "1.4"):
            with self.subTest(value=value), self.assertRaises(
                patch.CrestBoxPatchError
            ):
                patch.transform_for_coverage(value)  # type: ignore[arg-type]

    def test_document_is_one_atomic_patch_with_twelve_big_endian_writes(self) -> None:
        document = tomllib.loads(patch.patch_document(1.4))
        self.assertEqual(document["title_id"], patch.TITLE_ID)
        self.assertEqual(document["hash"], patch.TITLE_HASH)
        self.assertEqual(len(document["patch"]), 1)
        row = document["patch"][0]
        self.assertTrue(row["is_enabled"])
        self.assertEqual(len(row["be32"]), 12)
        addresses = [entry["address"] for entry in row["be32"]]
        self.assertEqual(
            addresses,
            [
                base + word * 4
                for base in patch.RETAIL_PACKET_ADDRESSES
                for word in range(4)
            ],
        )

    def test_exact_three_guarded_retail_packets_are_required(self) -> None:
        image, base = _synthetic_retail_image()
        self.assertEqual(
            patch.validate_retail_image(image, base),
            patch.RETAIL_PACKET_ADDRESSES,
        )
        broken = bytearray(image)
        offset = patch.RETAIL_PACKET_ADDRESSES[1] - base
        broken[offset] ^= 1
        with self.assertRaisesRegex(
            patch.CrestBoxPatchError, "retail crest packet identity drift"
        ):
            patch.validate_retail_image(bytes(broken), base)

    def test_encrypted_or_unrelated_input_is_refused(self) -> None:
        with self.assertRaisesRegex(patch.CrestBoxPatchError, "decrypted"):
            patch.crest_packet_addresses(b"XEX2" + bytes(0x2000))

    def test_writer_never_overwrites_an_existing_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / patch.PATCH_BASENAME
            patch.write_new_patch(output, 1.4)
            first = output.read_bytes()
            with self.assertRaisesRegex(
                patch.CrestBoxPatchError, "already exists"
            ):
                patch.write_new_patch(output, 1.4)
            self.assertEqual(output.read_bytes(), first)

    def test_public_basename_is_discoverable_by_xenia(self) -> None:
        self.assertEqual(
            patch.PATCH_BASENAME,
            f"{patch.TITLE_ID} - {patch.TITLE_NAME}.patch.toml",
        )


if __name__ == "__main__":
    unittest.main()

"""Packed-mip addressing for the 512x512 4_4_4_4 team crests.

These are pure addressing tests: no retail bytes, no disc, no Qt.  They pin the
property that the crest mip regenerator depends on and that a shipped defect
violated -- every stored level owns a byte range no other level touches.

The defect: mip offsets were advanced by the product of a level's aligned
dimensions instead of by its 4096-byte-aligned subresource stride, and a
level's extent was taken as that same product instead of the Xenos tiled upper
bound.  At two bytes per texel both are wrong by a fixed amount, which put the
packed tail 0x800 bytes inside the 32x32 level.  Regenerating the chain then
blitted the 16x16 and smaller levels through the 32x32 level -- on screen, a
second small logo in the corner of the crest -- while the real packed tail was
never written at all and kept the retail crest at the smallest draw sizes.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from PIL import Image  # noqa: E402

import apf_inner  # noqa: E402
import apf_logo_patch as logo_patch  # noqa: E402
import apf_xenos_4444_mip_layout as mip4444  # noqa: E402


# The retail uniform_logo_NN logo_l0 / logo_l1 descriptor, transcribed from
# tools/apf_logo_patch.py's pinned constants. No retail bytes, just the shape.
CREST_DESCRIPTOR: dict[str, object] = {
    "format": 15,
    "width": 512,
    "height": 512,
    "pitch_pixels": 512,
    "endianness": 1,
    "tiled": True,
    "stacked": False,
    "dimension": 1,
    "mip_min_level": 0,
    "mip_max_level": 9,
    "vc_base_data_length": 0x80000,
    "vc_mip_data_length": 0x2C000,
    "swizzle_components": [2, 1, 0, 3],
    "packed_mips": True,
}


def _written_bytes(location: mip4444.MipLocation) -> set[int]:
    """Every byte offset write_level would touch for one level."""

    touched: set[int] = set()
    for y in range(location.height):
        for x in range(location.width):
            start = location.data_offset + mip4444._tiled_offset(location, x, y)
            touched.update(range(start, start + mip4444.BYTES_PER_BLOCK))
    return touched


class CrestMipLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.locations = mip4444.derive_layout(CREST_DESCRIPTOR)

    def test_chain_has_every_level(self) -> None:
        self.assertEqual(len(self.locations), 10)
        self.assertEqual(
            [item.width for item in self.locations],
            [512, 256, 128, 64, 32, 16, 8, 4, 2, 1],
        )

    def test_no_level_writes_into_another(self) -> None:
        written = {item.level: _written_bytes(item) for item in self.locations}
        for level, offsets in written.items():
            for other, other_offsets in written.items():
                if other <= level:
                    continue
                shared = offsets & other_offsets
                self.assertEqual(
                    shared,
                    set(),
                    f"level {level} and level {other} share "
                    f"{len(shared)} bytes starting at "
                    f"0x{min(shared):x}" if shared else "",
                )

    def test_every_write_stays_inside_its_own_allocation(self) -> None:
        for location in self.locations:
            start = location.data_offset
            end = location.data_offset + location.allocation_length
            for offset in _written_bytes(location):
                self.assertTrue(
                    start <= offset < end,
                    f"level {location.level} writes 0x{offset:x} outside "
                    f"0x{start:x}..0x{end:x}",
                )

    def test_stored_levels_account_for_the_declared_tail_exactly(self) -> None:
        # The declared 0x2C000 is a run of 4096-aligned subresources, not an
        # addressed span plus unexplained padding. An exact match is the
        # strongest available evidence that the stride model is the right one.
        self.assertEqual(
            mip4444.stored_length(self.locations),
            CREST_DESCRIPTOR["vc_mip_data_length"],
        )

    def test_packed_tail_starts_after_the_32x32_level(self) -> None:
        by_level = {item.level: item for item in self.locations}
        level_32 = by_level[4]
        self.assertFalse(level_32.packed_tail)
        packed = [item for item in self.locations if item.packed_tail]
        self.assertEqual([item.level for item in packed], [5, 6, 7, 8, 9])
        # One shared tile: identical origin for every packed level.
        self.assertEqual({item.data_offset for item in packed}, {0xAB000})
        self.assertGreaterEqual(
            packed[0].data_offset,
            level_32.data_offset + level_32.allocation_length,
        )

    def test_packed_levels_occupy_their_documented_corners(self) -> None:
        # Xenia's graph-paper layout for a square texture: 16x16 at (16, 0),
        # then 8x8, 4x4 walking left, 2x2 at (0, 8) and 1x1 at (0, 4).
        corners = {
            item.level: (item.origin_block_x, item.origin_block_y)
            for item in self.locations
            if item.packed_tail
        }
        self.assertEqual(
            corners,
            {5: (16, 0), 6: (8, 0), 7: (4, 0), 8: (0, 8), 9: (0, 4)},
        )

    def test_tail_padding_is_never_negative(self) -> None:
        padding = mip4444.tail_padding(
            self.locations, int(CREST_DESCRIPTOR["vc_mip_data_length"])
        )
        self.assertGreaterEqual(padding, 0)

    def test_overlapping_layout_is_rejected(self) -> None:
        overlapping = [
            mip4444.MipLocation(
                level=0, width=512, height=512, data_offset=0,
                allocation_length=0x80000, pitch_blocks=512,
                origin_block_x=0, origin_block_y=0, packed_tail=False,
            ),
            mip4444.MipLocation(
                level=1, width=256, height=256, data_offset=0x80000,
                allocation_length=0x20000, pitch_blocks=256,
                origin_block_x=0, origin_block_y=0, packed_tail=False,
            ),
            mip4444.MipLocation(
                level=2, width=128, height=128, data_offset=0x90000,
                allocation_length=0x8000, pitch_blocks=128,
                origin_block_x=0, origin_block_y=0, packed_tail=False,
            ),
        ]
        with self.assertRaises(mip4444.MipLayoutError) as caught:
            mip4444._reject_overlap(overlapping)
        self.assertIn("overlap", str(caught.exception))


class TiledExtentTests(unittest.TestCase):
    """The address-space facts the layout is built on."""

    def test_a_32x32_tile_of_two_byte_texels_reaches_0xc00(self) -> None:
        # Xenia texture_util::GetTiledAddressUpperBound2D special-cases this:
        # bit 11 of the address is the bank while bit 10 goes unused, so the
        # tile is scattered over 0xC00 bytes rather than packed into 0x800.
        self.assertEqual(
            mip4444.tiled_address_upper_bound(32, 32, 32),
            mip4444.TILE_ADDRESS_EXTENT_BYTES,
        )
        reached = set()
        for y in range(32):
            for x in range(32):
                offset = apf_inner._tiled_2d_offset(
                    x, y, 32, mip4444.BYTES_PER_BLOCK_LOG2
                )
                reached.update(range(offset, offset + mip4444.BYTES_PER_BLOCK))
        self.assertEqual(len(reached), 32 * 32 * mip4444.BYTES_PER_BLOCK)
        self.assertEqual(max(reached) + 1, mip4444.TILE_ADDRESS_EXTENT_BYTES)

    def test_large_levels_are_a_contiguous_bijection(self) -> None:
        # Above one tile the scatter closes up and the naive product is right,
        # which is why only the 32x32 level was ever mis-sized.
        for size in (64, 128, 256, 512):
            reached = set()
            for y in range(size):
                for x in range(size):
                    offset = apf_inner._tiled_2d_offset(
                        x, y, size, mip4444.BYTES_PER_BLOCK_LOG2
                    )
                    reached.update(
                        range(offset, offset + mip4444.BYTES_PER_BLOCK)
                    )
            expected = size * size * mip4444.BYTES_PER_BLOCK
            self.assertEqual(len(reached), expected, f"{size}x{size}")
            self.assertEqual(max(reached) + 1, expected, f"{size}x{size}")

    def test_subresource_stride_pads_small_levels_to_a_page(self) -> None:
        self.assertEqual(mip4444.subresource_stride(32, 32), 0x1000)
        self.assertEqual(mip4444.subresource_stride(64, 64), 0x2000)
        self.assertEqual(mip4444.subresource_stride(512, 512), 0x80000)


class RegeneratedTailRoundTripTests(unittest.TestCase):
    """End-to-end: regenerate a tail, then read every level back out.

    This is the test that fails on the defective layout. Pre-fix, level 4 came
    back with 427 of its 2048 bytes overwritten by the smaller levels, and the
    real packed tail was never written at all.
    """

    @staticmethod
    def _quadrants() -> "Image.Image":
        # Four flat quadrants: a stray blit from a neighbouring level shows up
        # as a wrong colour rather than hiding inside a gradient.
        image = Image.new("RGBA", (512, 512))
        pixels = image.load()
        for y in range(512):
            for x in range(512):
                if x < 256 and y < 256:
                    pixels[x, y] = (255, 0, 0, 255)
                elif y < 256:
                    pixels[x, y] = (0, 255, 0, 255)
                elif x < 256:
                    pixels[x, y] = (0, 0, 255, 255)
                else:
                    pixels[x, y] = (255, 255, 255, 255)
        return image

    def test_every_regenerated_level_reads_back_exactly(self) -> None:
        descriptor = dict(logo_patch.STRICT_DESCRIPTOR)
        descriptor.update({"mip_min_level": 0, "mip_max_level": 9})
        image = self._quadrants()

        tail = logo_patch.rebuild_mip_tail(
            descriptor, image.tobytes(), bytes(logo_patch.MIP_LEN)
        )
        self.assertEqual(len(tail), logo_patch.MIP_LEN)

        payload = bytes(bytearray(logo_patch.BASE_LEN) + bytearray(tail))
        for location in mip4444.derive_layout(descriptor)[1:]:
            expected = logo_patch.encode_4444_linear(
                descriptor,
                image.resize((location.width, location.height), Image.BOX).tobytes(),
                location.width * location.height,
            )
            self.assertEqual(
                mip4444.read_level(payload, location),
                expected,
                f"level {location.level} ({location.width}x{location.height}) "
                "did not survive the round trip",
            )

    def test_regeneration_writes_the_packed_tail(self) -> None:
        # The tail holds every draw at 16x16 and smaller. Leaving it untouched
        # is what made modded crests keep the retail logo when zoomed out.
        descriptor = dict(logo_patch.STRICT_DESCRIPTOR)
        descriptor.update({"mip_min_level": 0, "mip_max_level": 9})
        tail = logo_patch.rebuild_mip_tail(
            descriptor, self._quadrants().tobytes(), bytes(logo_patch.MIP_LEN)
        )
        packed = [
            item
            for item in mip4444.derive_layout(descriptor)
            if item.packed_tail
        ]
        start = packed[0].data_offset - logo_patch.BASE_LEN
        end = start + packed[0].allocation_length
        self.assertNotEqual(
            tail[start:end],
            bytes(end - start),
            "the packed tail was left at its incoming value",
        )


class SiblingFormatsUnaffectedTests(unittest.TestCase):
    """Scope check: the block-compressed writers must not need this fix.

    BC1 is 8 bytes per block and BC3/DXN are 16, so a 32x32-block level is
    already 0x2000 or 0x4000 bytes -- page-aligned, and addressed contiguously.
    Both corrections collapse to no-ops there, which is why the shipped
    uniform/wordmark lanes stay byte-identical.
    """

    def test_block_compressed_levels_need_no_padding_or_extra_extent(self) -> None:
        for bytes_per_block in (8, 16):
            log2 = bytes_per_block.bit_length() - 1
            product = 32 * 32 * bytes_per_block
            aligned = (
                (product + mip4444.SUBRESOURCE_ALIGNMENT_BYTES - 1)
                // mip4444.SUBRESOURCE_ALIGNMENT_BYTES
                * mip4444.SUBRESOURCE_ALIGNMENT_BYTES
            )
            self.assertEqual(aligned, product, f"{bytes_per_block} B/block")
            reached = set()
            for y in range(32):
                for x in range(32):
                    offset = apf_inner._tiled_2d_offset(x, y, 32, log2)
                    reached.update(range(offset, offset + bytes_per_block))
            self.assertEqual(max(reached) + 1, product, f"{bytes_per_block} B/block")


if __name__ == "__main__":
    unittest.main()

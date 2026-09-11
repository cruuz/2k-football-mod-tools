"""Three-argument digit encoders edit the base without pretending to rebuild mips."""
from __future__ import annotations

import unittest

from mod_editor.apf_studio.backend import ensure_tools_importable
ensure_tools_importable()
import apf_number_texture_patch as numbers


class NumberEncodeDefaultsTests(unittest.TestCase):
    def test_three_argument_encoders_preserve_the_synthetic_tail(self):
        for codec, fmt, base_length, mip_length, layout, transport, encoder, extract, decode in (
            ("DXT1", 18, 0x20000, 0x10000, numbers.bc1_mips, numbers.dxt1_transport,
             numbers._encode_color, "extract_linear_bc1", "decode_linear_bc1"),
            ("DXN", 49, 0x40000, 0x20000, numbers.dxn_mips, numbers.dxn_transport,
             numbers._encode_normal, "extract_linear_dxn", "decode_linear_dxn"),
        ):
            with self.subTest(codec=codec):
                metadata = dict(format=fmt, endianness=1, tiled=True, stacked=False, dimension=1,
                                mip_min_level=0, mip_max_level=7, packed_mips=True,
                                width=512, height=512, pitch_pixels=512,
                                vc_base_data_length=base_length, vc_mip_data_length=mip_length,
                                mip_address_pages=base_length // 4096, swizzle_components=[0, 1, 2, 3])
                original = bytes(base_length + mip_length)
                base = layout.derive_layout(metadata)[0]
                source = getattr(transport, decode)(getattr(layout, extract)(original, base), base)
                wanted = bytearray(source)
                for y in range(4):
                    for x in range(4):
                        offset = (y * 512 + x) * 4
                        wanted[offset:offset + 4] = bytes((255, 255, 0 if fmt == 49 else 255, 255))
                result = encoder(original, metadata, bytes(wanted))
                self.assertNotEqual(result[:base_length], original[:base_length])
                self.assertEqual(result[base_length:], original[base_length:])
                decoded = getattr(transport, decode)(getattr(layout, extract)(result, base), base)
                self.assertEqual(decoded[:4], wanted[:4])


if __name__ == "__main__":
    unittest.main()

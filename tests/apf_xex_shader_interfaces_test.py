"""The shader-interface extractor must parse a real constant table exactly.

This is the tool that closed task #10 -- the crest rectangle turned out to be
pixel-shader constant ``c29`` (``ReverseLogoScaleAndOffset``, default
``(1, 1, 0, 0)``), which no amount of asset inspection could have found. The
parse has to stay exact, and it has to keep rejecting the garbage a linear scan
over 54 MB inevitably turns up: the header signature is only four bytes, so
false positives are the normal case and the discriminators are what make the
scan usable.

The retail image is the user's own game data and is not in this tree, so these
build synthetic big-endian ``D3DXSHADER_CONSTANTTABLE`` blobs. Where a real
figure is asserted it is a coordinate or a compiled default, never game content.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import apf_xex_shader_interfaces as sif  # noqa: E402


def _table(constants, target=b"ps_3_0", creator=b"2.0.5426.0"):
    """Assemble one big-endian constant table the way the compiler emits it.

    Layout: header, the CONSTANTINFO array, then a blob holding the strings and
    default values that the header and array point into. Offsets are relative to
    the table start, which is what the parser has to honour.
    """

    header_size = sif.CTAB_HEADER_SIZE
    info_at = header_size
    blob_at = info_at + len(constants) * sif.CONSTANT_INFO_SIZE
    blob = bytearray()

    def intern(payload: bytes) -> int:
        offset = blob_at + len(blob)
        blob.extend(payload)
        while len(blob) % 4:
            blob.append(0xAB)          # D3DX's own filler
        return offset

    creator_offset = intern(creator + b"\0")
    target_offset = intern(target + b"\0")
    info = bytearray()
    for name, register_set, index, count, default in constants:
        name_offset = intern(name.encode("ascii") + b"\0")
        default_offset = 0
        if default is not None:
            # Write one float4 per declared register, which is what the parser
            # must read back -- a fixed four would hide an array truncation.
            default_offset = intern(struct.pack(f">{len(default)}f", *default))
        info.extend(struct.pack(">IHHHHII", name_offset, register_set, index,
                                count, 0, 0, default_offset))
    head = struct.pack(">7I", header_size, creator_offset, 0xFFFF0300,
                       len(constants), info_at, 0x1000, target_offset)
    return bytes(head) + bytes(info) + bytes(blob)


def _image(*tables: bytes) -> bytes:
    """An MZ-prefixed buffer holding the tables, four-byte aligned."""

    body = bytearray(b"MZ" + b"\0" * 0xFFE)
    for table in tables:
        while len(body) % 4:
            body.append(0)
        body.extend(table)
    body.extend(b"\0" * 0x100)
    return bytes(body)


#: The real crest shader's interface, as read out of the retail image.
CREST = [
    ("Layer0", 3, 0, 1, None),
    ("Layer1", 3, 1, 1, None),
    # float4 Palette[6]: six entries, so 24 floats.  The real shader holds a
    # debug colour ramp here; the point of the fixture is the array length.
    ("Palette", 2, 12, 6, (
        1.0, 0.0, 0.0, 0.0,  0.0, 1.0, 0.0, 0.0,  0.0, 0.0, 1.0, 0.0,
        0.0, 1.0, 1.0, 0.0,  1.0, 0.0, 1.0, 0.0,  0.0, 1.0, 1.0, 0.0,
    )),
    ("ReverseLogoScaleAndOffset", 2, 29, 1, (1.0, 1.0, 0.0, 0.0)),
    ("Enables", 2, 36, 1, (1.0, 1.0, 1.0, 0.0)),
]


class ExtractorTests(unittest.TestCase):
    def test_it_parses_names_registers_counts_and_defaults(self) -> None:
        interfaces = sif.extract_interfaces(_image(_table(CREST)), 0x82000000)
        self.assertEqual(len(interfaces), 1)
        shader = interfaces[0]
        self.assertEqual(shader.target, "ps_3_0")
        self.assertEqual(shader.creator, "2.0.5426.0")

        logo = shader.constant("ReverseLogoScaleAndOffset")
        self.assertIsNotNone(logo)
        assert logo is not None
        self.assertEqual(logo.register_set, "float4")
        self.assertEqual(logo.register_index, 29)
        self.assertEqual(logo.register_count, 1)
        self.assertEqual(logo.register, "c29")
        self.assertEqual(logo.default, (1.0, 1.0, 0.0, 0.0))

    def test_a_sampler_renders_as_s_and_an_array_as_a_range(self) -> None:
        shader = sif.extract_interfaces(_image(_table(CREST)), 0x82000000)[0]
        layer0 = shader.constant("Layer0")
        palette = shader.constant("Palette")
        assert layer0 is not None and palette is not None
        self.assertEqual(layer0.register, "s0")
        self.assertEqual(layer0.register_set, "sampler")
        # Six float4s is the team-colour palette; the range has to be visible or a
        # reader cannot tell c12 from c12..c17.
        self.assertEqual(palette.register, "c12..c17")
        self.assertEqual(palette.register_count, 6)
        # Every declared register must come back.  Reading a fixed four floats
        # reported only the first entry while looking like a complete answer.
        assert palette.default is not None
        self.assertEqual(len(palette.default), 24)
        self.assertEqual(palette.default[4:8], (0.0, 1.0, 0.0, 0.0))

    def test_several_tables_in_one_image_are_all_found(self) -> None:
        other = [("BaseTexture", 3, 0, 1, None), ("WeaveRepeat", 2, 29, 1,
                                                  (60.0, 60.0, 60.0, 60.0))]
        interfaces = sif.extract_interfaces(
            _image(_table(CREST), _table(other, target=b"vs_3_0")), 0x82000000)
        self.assertEqual(len(interfaces), 2)
        self.assertEqual({item.target for item in interfaces}, {"ps_3_0", "vs_3_0"})
        # c29 is the logo transform in one shader and weave repetition in the
        # other.  Any patch keyed on the register number alone corrupts one of
        # them, so the extractor must keep them distinguishable.
        registers = {
            item.target: item.constants[-1].name for item in interfaces
        }
        self.assertNotEqual(registers["ps_3_0"], registers["vs_3_0"])

    def test_a_bad_target_string_is_rejected(self) -> None:
        """The shader-model string is the discriminator that makes the scan work."""

        self.assertEqual(
            sif.extract_interfaces(_image(_table(CREST, target=b"garbage")),
                                   0x82000000),
            (),
        )

    def test_an_absurd_constant_count_is_rejected(self) -> None:
        blob = bytearray(_table(CREST))
        struct.pack_into(">I", blob, 12, 100_000)
        self.assertEqual(sif.extract_interfaces(_image(bytes(blob)), 0x82000000), ())

    def test_a_non_image_is_refused_loudly(self) -> None:
        """A user pointing this at the encrypted xex must be told, not given ()."""

        with self.assertRaisesRegex(sif.ShaderInterfaceError, "decrypted"):
            sif.extract_interfaces(b"\x00" * 0x2000)

    def test_zero_filled_input_yields_nothing_rather_than_noise(self) -> None:
        self.assertEqual(sif.extract_interfaces(_image(), 0x82000000), ())

    def test_addresses_are_reported_against_the_image_base(self) -> None:
        image = _image(_table(CREST))
        interfaces = sif.extract_interfaces(image, 0x82000000)
        self.assertGreaterEqual(interfaces[0].address, 0x82000000)
        rebased = sif.extract_interfaces(image, 0x40000000)
        self.assertEqual(interfaces[0].address - 0x82000000,
                         rebased[0].address - 0x40000000)


if __name__ == "__main__":
    unittest.main()

"""Relocatable page of the modern jersey numbers owner (beta 81, owner nfl2k5_modern_numbers).

One page: code and tables at 0x000 (0xCC after the last byte up to 0xF00), zeros after it. The page has no state of its
own and writes nothing but the joining player's +0x20 number bits (the entry) before the jersey routine's retail tail.
Entered by a 5-byte jmp (plus a nop) at 0x2BD260, the jersey routine's entry. The template, relocations and labels are
generated from tools/modern_numbers by build.py; the rule's tables come from nfl2k5_modern_numbers.
"""
from __future__ import annotations

import struct

PAGE_SIZE = 0x1000
CODE_LIMIT = 0xF00


def page_bytes(va: int) -> bytes:
    """The whole 0x1000-byte page linked for ``va`` (a page boundary)."""
    if type(va) is not int or not 0x1000 <= va <= 0xFFFFF000 or va % 0x1000:
        raise ValueError("The modern numbers page address must be a page boundary")
    page = bytearray(_TEMPLATE)
    for offset, relative, family, addend in _RELOCATIONS:
        target = {"page": va, "stock": 0}[family] + addend
        struct.pack_into("<I", page, offset, (target - (va + offset) if relative else target) & 0xFFFFFFFF)
    return bytes(page)


# Generated from tools/modern_numbers by build.py.
CODE_BYTES = 0x7a2

_TEMPLATE = b''.join((
    bytes.fromhex('5355565789d389cf8d442410fc505357e8fcffffff83c40c85c078168b572081e207fcffffc1e003'),
    bytes.fromhex('09c2895720e93bd32b0089f989da5f5e5d5bb80100000085c0e962d22b005389c189502031d2b84d'),
    bytes.fromhex('554e4d3344911089c3c1eb1031d869c06bcaeb8589c3c1eb0d31d869c035aeb2c289c3c1eb1031d8'),
    bytes.fromhex('4283fa0575d55bc385d2742639ca74225389c38b4a20c1e90389c883e07f83f863770dc1e805ba01'),
    bytes.fromhex('000000d3e20914835bc3c3565389c389d18b4024d3e883e00174216bca0abe0b00000031c04e7414'),
    bytes.fromhex('89cac1ea058b1493d3eaf7d283e20101d041ebe95b5ec3565389c36bc20a8d500a89c6c1ee058b34'),
    bytes.fromhex('b30fa3c672098d71ff85c9740a89f14039d072e583c8ff5b5ec35557565383ec6c8bbc2484000000'),
    bytes.fromhex('8b0d1829b7008b8424800000000fb668358b8424800000008b4020894424248b8424800000008a40'),
    bytes.fromhex('258844242b31f68974241c8b84248800000081386c5b320075298b501081fac26532000f94c381fa'),
    bytes.fromhex('405c32000f94c009d881fabe2f32000f94c209d00fb6c08944241c85c90f94c085ff0f94c208d075'),
    bytes.fromhex('0583fd10760883c8ffe93004000031db895c2438895c243c895c2440895c24440fb7842d80070000'),
    bytes.fromhex('894424188944245c8b51048b84248000000029d0b95400000031d2f7f18944244889f9b8a04c0c00'),
    bytes.fromhex('ffd08944240c8944244ca1b876e50089442450a1a476e5008944241089442454a11829b700894424'),
    bytes.fromhex('140fb69f1c01000080fb417605bb410000008d049f8944242089fe3974242074178b168b8c248000'),
    bytes.fromhex('00008d442438e845feffff83c604ebe38a87f30100003ca5741ea1a076e50083f8020f85d6000000'),
    bytes.fromhex('837c240c1f0f87cb000000e9b40000000fb697f2010000a10828b7008b74241401f08d341a83fe46'),
    bytes.fromhex('7605be4600000031d289542420837c240c1f77238b9000fcffff81fa324b355275158b9004fcffff'),
    bytes.fromhex('31c981fa535632000f94c1894c24206b54240c0a8d841020fcffff8944242c39f30f837bffffff83'),
    bytes.fromhex('fb4077078d049f8b10eb2e837c24200074378d041b8b4c242c8d84017effffff0fb7108b4424148b'),
    bytes.fromhex('0039c2731c8b4424148b40046bd25401c28b8c24800000008d442438e867fdffff43ebab89f9b850'),
    bytes.fromhex('6e2400ffd089c631db83fb407509837c241c007426eb7039f373f389da89f9b8c06e2400ffd089c2'),
    bytes.fromhex('8b8c24800000008d442438e828fdffff43ebce8a5c242b83e31e837c241007770484db74648b7424'),
    bytes.fromhex('24c1ee0389f183e17f83f9637764bf0a00000089c831d2f7f78b7c24180fa3c7735089c8c1e8058b'),
    bytes.fromhex('4484380fa3f0724289c8e9270200000fb6b5500700008b8424880000008b5814c1eb0583e31f83fb'),
    bytes.fromhex('030f86ca000000bb03000000e9c00000000fb6b550070000bb04000000e9af0000000fb6b5500700'),
    bytes.fromhex('0084db7510bb04000000837c2410070f8694000000ba010000008b8c2480000000b8806d2400ffd0'),
    bytes.fromhex('d95c240c8b44240c89c1c1e9170fb6d180f976763985c07835b9640000000fbae01e722c25ffff7f'),
    bytes.fromhex('000d000080006bc064b99500000029d1bb01000000d3e301d8b99600000029d1d3e889c1eb0231c9'),
    bytes.fromhex('8d546d000fb682e005000031db39c173200fb682e1050000bb0100000039c173100fb682e2050000'),
    bytes.fromhex('39c119dbf7d383c303ba010000008d442438e8a7fbffffb96400000031d2f7f18d04b60fb6840320'),
    bytes.fromhex('06000039c2732c31d28d442438e8e9fbffff89c385c0741bba020000008d442438e870fbffff31d2'),
    bytes.fromhex('f7f389d131d2e9d30000006bf614bf0100000031db89fa8d442438e8b3fbffff89c231c085d27408'),
    bytes.fromhex('0fb7847e6006000001c34783ff0a75dd85db750631f631dbeb58ba030000008d442438e81efbffff'),
    bytes.fromhex('31d2f7f389d5bb0100000089da8d442438e86dfbffff89c785c074220fb7845e6006000039c57318'),
    bytes.fromhex('ba040000008d442438e8e8faffff31d2f7f789d1eb4e31c029c54383fb0a75c3eba289f28d442438'),
    bytes.fromhex('e82efbffff01c34683fe0a75ed85db0f8409fcffffba050000008d442438e8abfaffff31d2f7f389'),
    bytes.fromhex('d631db89da8d442438e8fdfaffff39c6730f89f189da8d442438e820fbffffeb0d29c64383fb0a75'),
    bytes.fromhex('dae9c8fbffff83c46c5b5e5f5dc36690669066906690669060554f5d5b535c54515a544f544e4859'),
    bytes.fromhex('4f4c59524d594b45645c51554b4556504b56504b60514a5d554f5b534d514a4556504a'),
    bytes(13),
    bytes.fromhex('32281e0e0c3714140c020000000000411e100c0605030504000000000000000000000017140f0200'),
    bytes.fromhex('0a0808040236281708031c1c1c1c1c1c1c1c1c1c00000000290046'),
    bytes(17),
    bytes.fromhex('1a00070040004a0019'),
    bytes(17),
    bytes.fromhex('07000c00000000000000000000004400760004000600020000000000000078000000080006000000'),
    bytes.fromhex('01001c0000000000000094'),
    bytes(13),
    bytes.fromhex('2900ba00e4'),
    bytes(15),
    bytes.fromhex('180013000a000000b5001b00100006000e003300710005000300000069000e000700030009004900'),
    bytes.fromhex('510000000000000000004f001200cd0091002300000000000000000000000b000d0002000b000100'),
    bytes.fromhex('000000000000000000000a0013000000050002'),
    bytes(12),
    bytes.fromhex('0a0b0309090901020408080505050607'),
    bytes(31),
    bytes.fromhex('03001f021f021f011f001f001f001f011f011f013f023f02e000e000e000e002ff02'),
    b'\xcc' * 1886,
    bytes(256),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0011, True, 'page', 0x106),
    (0x002e, True, 'stock', 0x2bd33b),
    (0x0042, True, 'stock', 0x2bd262),
    (0x01b4, False, 'page', 0x780),
    (0x03aa, False, 'page', 0x750),
    (0x03d4, False, 'page', 0x750),
    (0x03e5, False, 'page', 0x750),
    (0x0467, False, 'page', 0x5e0),
    (0x0474, False, 'page', 0x5e1),
    (0x0484, False, 'page', 0x5e2),
    (0x04af, False, 'page', 0x620),
    (0x0504, False, 'page', 0x660),
    (0x0548, False, 'page', 0x660),
)

LABELS = {
    'number_entry': 0x0,
    'number_pick': 0x10a,
}

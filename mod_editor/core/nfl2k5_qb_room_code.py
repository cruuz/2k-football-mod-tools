"""Relocatable page of the quarterback room owner (beta 81 piece 3, owner nfl2k5_qb_room).

Three pages: code and read-only tables at 0x0000..0x1FFF (0xCC after the last byte of code), the settings record at
0x2000, link words at 0x2020, counters at 0x2040, the event ring at 0x2400 and its cursor at 0x2E00. The file holds
zeros in the counters, ring and cursor; they change only in RAM. Two whole 5-byte calls of the weekly advance enter
the page (and a third for signings once stage 4a is built). The byte interface is fixed by
.b77-scratch/b81/qb34/INTERFACE.md; the rules are DESIGN.md section 2. The template, relocations, labels and counter
names are generated from tools/qb_room by build.py.
"""
from __future__ import annotations

import struct
from typing import Iterator

PAGE_SIZE = 0x3000
CODE_LIMIT = 0x2000
SETTINGS_OFFSET = 0x2000
SETTINGS = struct.Struct("<8sIIIIII")
MAGIC = b"QBROOMv1"
MODE_REALISTIC = 1
LINK_IR_STORE = 0x2020
COUNTERS_OFFSET = 0x2040
RING_OFFSET = 0x2400
RING_COUNT = 128
# year, week, club, decision (low 4 bits: 1 D1, 2 D2, 3 D3, 4 D4, 5 E1, 6 E2; 0x10 S hot, 0x20 stage 7,
# 0x40 b ends ahead of a), result (0 kept, 1 applied, 2 would fire in shadow, 3 lock only, no draw), a, b,
# d (L - W), g, rating10 of row 0, gap ovr(b) - ovr(a), coach1000 / 10, threshold p100k.
RING_EVENT = struct.Struct("<HBBBBHHbBHbBI")
RING_CURSOR = 0x2E00

STAGE_D1, STAGE_D2D3, STAGE_D4, STAGE_SIGN, STAGE_TRADE = 1, 2, 4, 8, 16
STAGE_MASK = 31
FLAG_SHADOW = 1
H0_PPM = 15000                       # D3 base 0.015 in millionths until shadow panel P0 fixes it (DESIGN 6.3).
D2_SCALE_MILLI = 1000                # D2 table scale in thousandths (1000 = the table as written).
LIMIT_PPM = 1_000_000                # Both are clamped to this in the page (a probability is at most 1).

DECISION_D1, DECISION_D2, DECISION_D3, DECISION_D4 = 1, 2, 3, 4
RESULT_KEPT, RESULT_APPLIED, RESULT_SHADOW, RESULT_LOCK_ONLY = 0, 1, 2, 3

# (site, retail bytes, entry label, stage bit the site needs; 0 = always). Whole 5-byte calls.
HOOKS = (
    (0x247DCA, bytes.fromhex("e851620700"), "opening_entry", 0),
    (0x24807A, bytes.fromhex("e8016b0300"), "room_entry", 0),
    (0x248010, bytes.fromhex("e85bb80d00"), "sign_entry", STAGE_SIGN),
)


def _whole(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"The quarterback room {name} must be a whole number from {low} to {high}")
    return value


def settings_record(stages: int, *, shadow: bool = False, h0_ppm: int = H0_PPM,
                    d2_scale_milli: int = D2_SCALE_MILLI) -> bytes:
    """The 32-byte settings record: magic, mode 1 (realistic), stage bits, flags, H0 and the D2 scale."""
    _whole(stages, 0, STAGE_MASK, "stage set")
    if type(shadow) is not bool:
        raise ValueError("The quarterback room shadow flag must be True or False")
    _whole(h0_ppm, 0, LIMIT_PPM, "H0 (millionths)")
    _whole(d2_scale_milli, 0, LIMIT_PPM, "D2 scale (thousandths)")
    return SETTINGS.pack(MAGIC, MODE_REALISTIC, stages, FLAG_SHADOW if shadow else 0, h0_ppm, d2_scale_milli, 0)


def parse_settings(record: bytes) -> dict:
    """Decode a settings record; refuses anything that settings_record could not have written."""
    if not isinstance(record, (bytes, bytearray)) or len(record) != SETTINGS.size:
        raise ValueError("A quarterback room settings record is 32 bytes")
    magic, mode, stages, flags, h0, scale, reserved = SETTINGS.unpack(record)
    if magic != MAGIC or mode != MODE_REALISTIC or stages & ~STAGE_MASK or flags & ~FLAG_SHADOW or reserved \
            or h0 > LIMIT_PPM or scale > LIMIT_PPM:
        raise ValueError("Unrecognized quarterback room settings record")
    return {"mode": mode, "stages": stages, "shadow": bool(flags & FLAG_SHADOW), "h0_ppm": h0,
            "d2_scale_milli": scale}


def _set32(page, offset, value):
    struct.pack_into("<I", page, offset, value & 0xFFFFFFFF)


def page_bytes(va: int, settings: bytes, *, ir_store_va: int = 0) -> bytes:
    """The whole 0x3000-byte page linked for `va`, with the settings record and link words in place."""
    _whole(va, 0x1000, 0xFFFFFFFF - PAGE_SIZE + 1, "page address")
    if va % 0x1000:
        raise ValueError("The quarterback room page must start on a page boundary")
    parse_settings(settings)
    _whole(ir_store_va, 0, 0xFFFFFFFF, "IR store address")
    page = bytearray(_TEMPLATE)
    for offset, relative, family, addend in _RELOCATIONS:
        target = (va if family == "page" else 0) + addend
        _set32(page, offset, target - (va + offset) if relative else target)
    page[SETTINGS_OFFSET:SETTINGS_OFFSET + SETTINGS.size] = settings
    _set32(page, LINK_IR_STORE, ir_store_va)
    return bytes(page)


def _call(at: int, destination: int) -> bytes:
    return b"\xe8" + struct.pack("<I", (destination - at - 5) & 0xFFFFFFFF)


def sites(va: int, stages: int) -> Iterator[tuple[str, int, bytes, bytes]]:
    """(entry label, site, retail call, installed call) for every site the stage set needs."""
    _whole(stages, 0, STAGE_MASK, "stage set")
    for at, original, label, need in HOOKS:
        if need and not stages & need:
            continue
        if label not in LABELS:
            raise ValueError(f"The quarterback room template has no {label} (stage {need} is not built)")
        yield label, at, original, _call(at, va + LABELS[label])


def counters(page: bytes) -> dict:
    """Counter values from a page image (RAM or file)."""
    return {name: struct.unpack_from("<I", page, offset)[0] for name, offset in COUNTERS.items()}


def events(page: bytes) -> list[tuple]:
    """Ring events in the order written (at most the last RING_COUNT)."""
    total = struct.unpack_from("<I", page, RING_CURSOR)[0]
    first = max(0, total - RING_COUNT)
    return [RING_EVENT.unpack_from(page, RING_OFFSET + RING_EVENT.size * (n % RING_COUNT)) for n in range(first, total)]


# Generated from tools/qb_room by build.py.
CODE_BYTES = 0x10c4

_TEMPLATE = b''.join((
    bytes.fromhex('9c60fce8fcffffff619de91ce02b009c60fce8fcffffff619de97ceb270056538b581085db0f8eab'),
    bytes.fromhex('00000089c6694018e803000099f7fb2db80b0000b90400000099f7f989c13d470900007e07b94709'),
    bytes.fromhex('0000eb0685c0790231c9694614e803000099f7fb2d2c0100008d148081fa470900007e07ba470900'),
    bytes.fromhex('00eb0685d2790231d201d169461c204e000099f7fb3d470900007e07b847090000eb0685c0790231'),
    bytes.fromhex('c001c1694620a861000099f7fbba4709000029c281fa470900007e07ba47090000eb0685d2790231'),
    bytes.fromhex('d28d0411b90600000099f7f9eb0231c05b5ec3555756535389c689142489ca8b7c241c8b2d000000'),
    bytes.fromhex('0089e883e07f8b0db876e5006bc0148d980000000066898800000000a1b476e5008843028b068843'),
    bytes.fromhex('03837e04070f94c0c1e0050b04248843048853058b4424188b4004668943068b4704668943088b46'),
    bytes.fromhex('3088430a8b463488430b8d4638e8ccfeffff6689430c8b47088b7c24182b470888430e8b4624b90a'),
    bytes.fromhex('00000031d2f7f188430f8b4424208943108d4501a300000000a19c00000040a39c0000005e5b5e5f'),
    bytes.fromhex('5dc35389c1b83352425131d233049189c3c1eb1031d869c06bcaeb8589c3c1eb0d31d869c035aeb2'),
    bytes.fromhex('c289c3c1eb1031d84283fa0c75d6b9a086010031d2f7f189d05bc383ec348914248b10895424048b'),
    bytes.fromhex('15b876e500895424088b50188954240c8b501c895424108b5020895424148b503c895424188b5048'),
    bytes.fromhex('8b484c8954241c894c24208b50508b485489542424894c24288b40588944242c89e0e863ffffff83'),
    bytes.fromhex('c434c3837a30007523c742300100000083780c0075168b128a425283c801884252a19400000040a3'),
    bytes.fromhex('94000000c3565389c689d38b42248b512489532489412489da89f0e8bbffffff89ca89f0e8b2ffff'),
    bytes.fromhex('ff837e0c00740da19800000040a398000000eb318b13668b42288b09668b592831d86625001c668b'),
    bytes.fromhex('592831c366895928668b4a2831c866894228a19000000040a3900000005b5ec35557565383ec0889'),
    bytes.fromhex('c589d783c038e843fdffff8b55402b5574b9a00000003d890200007e29b9820000003ded0200007e'),
    bytes.fromhex('1db9640000003d510300007e1131c93db50300000f9ec14983e1df83c12d8b4530be0a00000085c0'),
    bytes.fromhex('781cbe32000000741583f8040f9fc00fb6c089c64e83e6ba81c6aa00000031c0837d34030f9fc089'),
    bytes.fromhex('0424ff0c24832424d883042464bb9600000083fa057e19bb6400000083fa0a7e0f31db83fa0f0f9e'),
    bytes.fromhex('c34b83e3dd83c33289f8bf6400000031d2f7f78944240489d00fafc131d2f7f78b7c24040faff901'),
    bytes.fromhex('f8bf6400000031d2f7f789c189d00fafc631d2f7f70fafce01c831d2f7f789c18b04240fafc231d2'),
    bytes.fromhex('f7f78b34240fafce01c831d2f7f789c189d00fafc331d2f7f70fafcb01c88b5d24bee803000031d2'),
    bytes.fromhex('f7f689c189d00fafc331d2f7f60fafcb01c883c4085b5e5f5dc38b150000000081fa5142524f7517'),
    bytes.fromhex('8b150400000081fa4f4d763175098b15080000004a740ca10800000040a308000000c35557565381'),
    bytes.fromhex('ec1c0200008b150c000000895424748944247c85c07505b80700000085c20f84260c0000a1a476e5'),
    bytes.fromhex('008944247083e80783f8027610a10c00000040a30c000000e9050c0000a11829b70085c00f84f80b'),
    bytes.fromhex('0000a11000000083e001894424788b1514000000a11800000081fa40420f007605ba40420f008994'),
    bytes.fromhex('24940000003d40420f007605b840420f0089842498000000a1987fbd008944241085c0740831db89'),
    bytes.fromhex('1d987fbd0031db895c246c83fb1f0f87070b0000a11000000040a31000000089d9b8504c0c00ffd0'),
    bytes.fromhex('8944240485c07510a11400000040a314000000e9cf0a000081c3d75d39008b049d0000000085c074'),
    bytes.fromhex('19a14001e60085c07510a11800000040a318000000e9a50a00008b4424040fb6801c0100003c4176'),
    bytes.fromhex('0231c08b7c24048d04878944240889fb31c031d2bf01000000395c240874378b3385f6742c8a4e35'),
    bytes.fromhex('84c97525668b4e2866c1e90a83e10783f807742d89fdd3e585d5752509ea406bc93489b40ca40000'),
    bytes.fromhex('0083c304ebc383f801760ebb0100000088c1d3e34b39da7410a11c00000040a31c000000e91e0a00'),
    bytes.fromhex('00898424800000008d54246c31c9894c240831db895a5c8b7a388b6f2031f681e50000c0bf75108b'),
    bytes.fromhex('772431c981e6000000700f94c189ce897264017424088d730183c23439f0740489f3ebc883bc24d0'),
    bytes.fromhex('000000007510a12000000040a320000000e9b9090000837c247c007416394424087410a124000000'),
    bytes.fromhex('40a324000000e99c090000a11829b7008b4004894424086bf6348d44246c01f08944240c8d74246c'),
    bytes.fromhex('8b6e3889e88b7c240829f8b95400000031d2f7f189463c8a452583e01ffec80f94c00fb6c0894660'),
    bytes.fromhex('8a455283e001894668ba0100000089e9b8806d2400ffd0d95c24148b44241489c2c1ea170fb6fa80'),
    bytes.fromhex('fa76763785c07833ba640000000fbae01e722a25ffff7f000d000080006bc064b99500000029f9ba'),
    bytes.fromhex('01000000d3e201c2b99600000029f9d3eaeb0231d2895640bf40ee140031d289e9ffd7894644ba06'),
    bytes.fromhex('00000089e9ffd7894648ba0700000089e9ffd789464cba0800000089e9ffd7894650ba0900000089'),
    bytes.fromhex('e9ffd7894654ba0a00000089e9ffd789465883c6343974240c0f8519ffffff8b4c2404b820770c00'),
    bytes.fromhex('ffd089c6898424840000008b4c2404b850770c00ffd089c7898424880000008b4c2404b880770c00'),
    bytes.fromhex('ffd08984248c0000008d143e01d0898424a000000089f829f08984249c0000008b4424048b804c01'),
    bytes.fromhex('000085c074100fb65056b83d00000080fa3c761eeb10a12800000040a328000000ba5300000089d0'),
    bytes.fromhex('83fa637605b86300000069c0580200002df88e0000b92600000031d2f7f1ba4605000029c2899424'),
    bytes.fromhex('90000000f6442474050f84df0400008d44246c31d28954240831d283786400744a8378680075448b'),
    bytes.fromhex('7c240847897c2404837c24080074248b7424088d4eff8b748c206bee348b784039bc2cac0000007d'),
    bytes.fromhex('0a89748c24894c2408ebd58b7c24088954bc208b7c2404897c24088d4a0183c03439da740489caeb'),
    bytes.fromhex('a231c0894424148b5c2408395c24140f84610400008b4424148b4484208944240c6bc0348b8c04d4'),
    bytes.fromhex('00000085c90f853a0400008b9c04cc00000085db74178b8404b400000085c0750c8b7c24708d57f9'),
    bytes.fromhex('83fa0176386b74240c3483bc34c800000000743085db752c8b9434b000000031c085d27e236bd20f'),
    bytes.fromhex('399434b40000007c1731c0837c2470070f97c0eb0bbb01000000eb0431db31c0837c247c00740985'),
    bytes.fromhex('db7509e9c503000085db7407f644247401740b85c07417f6442474047510a13400000040a3340000'),
    bytes.fromhex('00e99f0300006b74240c348dbc34a4000000897c24048b152c0000004289152c00000085db0f8462'),
    bytes.fromhex('0100006b942480000000348d44246c01c231f639c274228d783883786400741483786000750e85f6'),
    bytes.fromhex('74088b6e083968407e0289fe83c034ebdaa13800000040a33800000085f67510a13c00000040a33c'),
    bytes.fromhex('000000e9180300006b7c240c348b843cac0000008b560889c529d50f889900000083fd050f8fbc00'),
    bytes.fromhex('000069ed78ecffff81c5084c0100c744243c010000008b4c246c894c24408b0db876e500894c2444'),
    bytes.fromhex('8b0db476e500894c24488b4e04894c244c8b8c3ca8000000894c245089542454894424588b8424b4'),
    bytes.fromhex('0000008944245c8b8424bc00000089442460a1a8fce50089442464a1b0fce500894424688d44243c'),
    bytes.fromhex('e83df7ffff89c2a14000000040a34000000089d939ea7332eb05bda0860100a14400000040a34400'),
    bytes.fromhex('00006b44240c348b7e2439bc04c80000000f92c00fb6c089c7e97305000031ed31dba14800000040'),
    bytes.fromhex('a3480000006b44240c348b8404c80000003946240f92c00fb6c089c789d931dbe94405000085c00f'),
    bytes.fromhex('84f80100008b8434ac000000894424188b9424ac00000089c629d68bac24b400000083fd597e3d89'),
    bytes.fromhex('54241c8d8424a4000000e81ff5ffff3d830300008b54241c7e228b8c24840000003b8c2488000000'),
    bytes.fromhex('19c0403b8c248800000019ff83e7f083c714eb0731c0bf040000008b0d7800000041890d78000000'),
    bytes.fromhex('85c0740d8b0d7c00000041890d7c0000008d4e0283f904763fa18000000040a3800000008b542404'),
    bytes.fromhex('8d44246ce8c2f6ffff566a00ff74240c8d8424b000000050b90300000089fa8d44247ce84bf5ffff'),
    bytes.fromhex('83c410e94501000085f6781383f80119f681e650c3000081c630750000eb1183f80119f681e6a861'),
    bytes.fromhex('000081c610270000c744243c040000008b44246c89442440a1b876e50089442444a1b476e5008944'),
    bytes.fromhex('24488b8424a80000008944244c6b44240c348b8404a800000089442450895424548b442418894424'),
    bytes.fromhex('58896c245c8b8424bc00000089442460a1a8fce50089442464a1b0fce500894424688d44243ce85f'),
    bytes.fromhex('f5ffff89c5a18400000040a38400000039f57330a18800000040a3880000008d8c24a40000008b54'),
    bytes.fromhex('24048d44246ce8faf5ffff837c24780119c983c102bb40000000eb2aa18c00000040a38c0000008b'),
    bytes.fromhex('5424048d44246ce8a7f5ffff8d9424a40000008d44246ce897f5ffff31c909df89fa5356ff74240c'),
    bytes.fromhex('8d8424b0000000508d44247ce822f4ffff83c41039f5731de922030000a13000000040a330000000'),
    bytes.fromhex('8b5424048d44246ce856f5ffffff442414e991fbffff8b5c247c85db0f85f5020000837c2470080f'),
    bytes.fromhex('85ea020000f6442474020f84df0200008b8424a00000004883f80f0f87ce02000083bc24b4000000'),
    bytes.fromhex('3b7f298bbc24cc00000085ff0f85b50200008b8c24800000008d8424d8000000ba0100000031dbe9'),
    bytes.fromhex('1301000083bc24040100000074cda16000000040a360000000ba40420f008d44246ce859f5ffff8b'),
    bytes.fromhex('157000000001d0730d8b157400000042891574000000a3700000008b9424940000008d44246ce82d'),
    bytes.fromhex('f5ffffb90a00000031d2f7f189c6ba030000008d44246ce81ff4ffff89c7a16400000040a3640000'),
    bytes.fromhex('0039f77333a16800000040a3680000008d8c24a40000008d9424d80000008d44246ce876f4ffff83'),
    bytes.fromhex('7c24780119db83c302ba43000000eb30a16c00000040a36c0000008d9424a40000008d44246ce820'),
    bytes.fromhex('f4ffff8d9424d80000008d44246ce810f4ffffba0300000051568d8424e0000000508d8424b00000'),
    bytes.fromhex('005089d98d44247ce896f2ffff83c41039f70f8297010000e9cefeffff83782c00750a4283c03439'),
    bytes.fromhex('ca72f2eb168378280074f085db74088b73083970087ee489c3ebe085db0f84640100008b43082b84'),
    bytes.fromhex('24ac00000083f8fb0f8c51010000a15000000040a3500000008b94249c000000b8a00f000085d278'),
    bytes.fromhex('19b8e02e000074124ab80071020083fa0377078b0495b41000008b9424a0000000be3200000083fa'),
    bytes.fromhex('01741131c983fa070f9ec189ce4e83e6ba83c6648b8c2498000000bde803000031d2f7f589442404'),
    bytes.fromhex('89d00fafc131d2f7f58b6c24040fafe901e8bd6400000031d2f7f589c189d00fafc631d2f7f50faf'),
    bytes.fromhex('ce01c88bb42490000000bde803000031d2f7f589c189d00fafc631d2f7f50fafce01c8b90a000000'),
    bytes.fromhex('31d2f7f189c6ba020000008d44246ce86ff2ffff89c2a15400000040a35400000039f2732ea15800'),
    bytes.fromhex('000040a3580000008d8c24a400000089da8d44246ce8cbf2ffff837c24780119ff83c702ba420000'),
    bytes.fromhex('00eb2ba15c00000040a35c0000008d9424a40000008d44246ce875f2ffff89da8d44246ce86af2ff'),
    bytes.fromhex('ffba020000005056538d8424b00000005089f98d44247ce8f7f0ffff83c4108b44246c8d5801e9ec'),
    bytes.fromhex('f4ffff837c2410000f84840000008b442410a3987fbd00eb7985ff742a89f18b5424048d44246ce8'),
    bytes.fromhex('41f2ffffa14c00000040a34c00000089f9837c2478007427b902000000eb208b5424048d44246ce8'),
    bytes.fromhex('eff1ffff89f28d44246ce8e4f1ffff83f90119c983e10385db7505bb410000005055ff74240c5689'),
    bytes.fromhex('da8d44247ce869f0ffff83c41085ff0f8460fcffffe965ffffff81c41c0200005b5e5f5dc3a10000'),
    bytes.fromhex('000040a300000000b801000000e960f3ffffa10400000040a30400000031c0e94ef3ffffb8880000'),
    bytes.fromhex('70110100a0860100d0fb0100'),
    b'\xcc' * 3900,
    bytes(4096),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0004, True, 'page', 0x1089),
    (0x000b, True, 'stock', 0x2be01c),
    (0x0013, True, 'page', 0x109e),
    (0x001a, True, 'stock', 0x27eb7c),
    (0x00ed, False, 'page', 0x2e00),
    (0x0101, False, 'page', 0x2400),
    (0x0108, False, 'page', 0x2400),
    (0x017d, False, 'page', 0x2e00),
    (0x0182, False, 'page', 0x20dc),
    (0x0188, False, 'page', 0x20dc),
    (0x0252, False, 'page', 0x20d4),
    (0x0258, False, 'page', 0x20d4),
    (0x0288, False, 'page', 0x20d8),
    (0x028e, False, 'page', 0x20d8),
    (0x02bb, False, 'page', 0x20d0),
    (0x02c1, False, 'page', 0x20d0),
    (0x0404, False, 'page', 0x2000),
    (0x0412, False, 'page', 0x2004),
    (0x0420, False, 'page', 0x2008),
    (0x0428, False, 'page', 0x2048),
    (0x042e, False, 'page', 0x2048),
    (0x043f, False, 'page', 0x200c),
    (0x046e, False, 'page', 0x204c),
    (0x0474, False, 'page', 0x204c),
    (0x048b, False, 'page', 0x2010),
    (0x0498, False, 'page', 0x2014),
    (0x049d, False, 'page', 0x2018),
    (0x04ed, False, 'page', 0x2050),
    (0x04f3, False, 'page', 0x2050),
    (0x0509, False, 'page', 0x2054),
    (0x050f, False, 'page', 0x2054),
    (0x0533, False, 'page', 0x2058),
    (0x0539, False, 'page', 0x2058),
    (0x05ba, False, 'page', 0x205c),
    (0x05c0, False, 'page', 0x205c),
    (0x061f, False, 'page', 0x2060),
    (0x0625, False, 'page', 0x2060),
    (0x063c, False, 'page', 0x2064),
    (0x0642, False, 'page', 0x2064),
    (0x07bf, False, 'page', 0x2068),
    (0x07c5, False, 'page', 0x2068),
    (0x092f, False, 'page', 0x2074),
    (0x0935, False, 'page', 0x2074),
    (0x0950, False, 'page', 0x206c),
    (0x0957, False, 'page', 0x206c),
    (0x099a, False, 'page', 0x2078),
    (0x09a0, False, 'page', 0x2078),
    (0x09a9, False, 'page', 0x207c),
    (0x09af, False, 'page', 0x207c),
    (0x0a58, False, 'page', 0x2080),
    (0x0a5e, False, 'page', 0x2080),
    (0x0a70, False, 'page', 0x2084),
    (0x0a76, False, 'page', 0x2084),
    (0x0a9b, False, 'page', 0x2088),
    (0x0aa1, False, 'page', 0x2088),
    (0x0b35, False, 'page', 0x20b8),
    (0x0b3c, False, 'page', 0x20b8),
    (0x0b46, False, 'page', 0x20bc),
    (0x0b4d, False, 'page', 0x20bc),
    (0x0b5a, False, 'page', 0x20c0),
    (0x0b60, False, 'page', 0x20c0),
    (0x0c36, False, 'page', 0x20c4),
    (0x0c3c, False, 'page', 0x20c4),
    (0x0c45, False, 'page', 0x20c8),
    (0x0c4b, False, 'page', 0x20c8),
    (0x0c75, False, 'page', 0x20cc),
    (0x0c7b, False, 'page', 0x20cc),
    (0x0cc6, False, 'page', 0x2070),
    (0x0ccc, False, 'page', 0x2070),
    (0x0d57, False, 'page', 0x20a0),
    (0x0d5d, False, 'page', 0x20a0),
    (0x0d71, False, 'page', 0x20b0),
    (0x0d7b, False, 'page', 0x20b4),
    (0x0d82, False, 'page', 0x20b4),
    (0x0d87, False, 'page', 0x20b0),
    (0x0db7, False, 'page', 0x20a4),
    (0x0dbd, False, 'page', 0x20a4),
    (0x0dc6, False, 'page', 0x20a8),
    (0x0dcc, False, 'page', 0x20a8),
    (0x0df9, False, 'page', 0x20ac),
    (0x0dff, False, 'page', 0x20ac),
    (0x0e97, False, 'page', 0x2090),
    (0x0e9d, False, 'page', 0x2090),
    (0x0ec6, False, 'page', 0x10b4),
    (0x0f67, False, 'page', 0x2094),
    (0x0f6d, False, 'page', 0x2094),
    (0x0f76, False, 'page', 0x2098),
    (0x0f7c, False, 'page', 0x2098),
    (0x0fa4, False, 'page', 0x209c),
    (0x0faa, False, 'page', 0x209c),
    (0x101d, False, 'page', 0x208c),
    (0x1023, False, 'page', 0x208c),
    (0x108e, False, 'page', 0x2040),
    (0x1094, False, 'page', 0x2040),
    (0x10a3, False, 'page', 0x2044),
    (0x10a9, False, 'page', 0x2044),
)

LABELS = {
    'opening_entry': 0x0,
    'opening_pass': 0x108d,
    'room_entry': 0xf,
    'room_pass': 0x10a2,
}

# Counter name -> page offset, in the order of struct counters in tools/qb_room/room.c.
COUNTERS = {
    'opening_passes': 0x2040,
    'room_passes': 0x2044,
    'passes_bad_settings': 0x2048,
    'passes_inactive': 0x204c,
    'clubs_visited': 0x2050,
    'skip_no_club': 0x2054,
    'skip_unmanaged': 0x2058,
    'skip_room_shape': 0x205c,
    'skip_row0_unhealthy': 0x2060,
    'skip_opening_injured': 0x2064,
    'coach_missing': 0x2068,
    'newcomers': 0x206c,
    'newcomer_locked': 0x2070,
    'newcomer_stage_off': 0x2074,
    'd1_evaluated': 0x2078,
    'd1_no_veteran': 0x207c,
    'd1_drawn': 0x2080,
    'd1_veteran_first': 0x2084,
    'd1_rookie_first': 0x2088,
    'd1_exchanged': 0x208c,
    'd2_evaluated': 0x2090,
    'd2_drawn': 0x2094,
    'd2_fired': 0x2098,
    'd2_kept': 0x209c,
    'd3_evaluated': 0x20a0,
    'd3_drawn': 0x20a4,
    'd3_fired': 0x20a8,
    'd3_kept': 0x20ac,
    'd3_exposure_lo': 0x20b0,
    'd3_exposure_hi': 0x20b4,
    'd4_evaluated': 0x20b8,
    'd4_hot': 0x20bc,
    'd4_lock_only': 0x20c0,
    'd4_drawn': 0x20c4,
    'd4_fired': 0x20c8,
    'd4_kept': 0x20cc,
    'exchanges_written': 0x20d0,
    'locks_written': 0x20d4,
    'shadow_exchanges': 0x20d8,
    'events_logged': 0x20dc,
    'e1_tried': 0x20e0,
    'e1_done': 0x20e4,
    'e2_tried': 0x20e8,
    'e2_done': 0x20ec,
    'trades_posted': 0x20f0,
    'trades_cancelled': 0x20f4,
}

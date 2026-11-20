"""FROZEN previous revision of nfl2k5_qb_room_code: the floor handover template (b81 qb34, pinned at c16934bee and
f34553b06, file SHA-256 752571283e98...). Never regenerate or edit: nfl2k5_qb_room recognizes pages written with it
as "previous" so the Studio can upgrade or restore them. The original docstring follows.

Relocatable page of the quarterback room owner (beta 81 piece 3, owner nfl2k5_qb_room).

Three pages: code and read-only tables at 0x0000..0x1FFF (0xCC after the last byte of code), the settings record at
0x2000, link words at 0x2020 (+0x2020: the IR owner's store, for stage 4a), counters at 0x2040..0x21FF, a range
reserved for code at 0x2200..0x23FF (zero until used), the event ring at 0x2400, its cursor at 0x2E00, the 4a menu
slot at 0x2E04 and a second code piece at 0x2E10 (CODE_TAIL, up to 0x2FFF). The file holds zeros in the counters,
ring, cursor and slot; they change only in RAM. Code-hash checks cover both code pieces. Two whole 5-byte calls of
the weekly advance enter the page, and with stage bit 8 or 64 a third (0x248010, the weekly signings). The byte
interface is fixed by .b77-scratch/b81/qb34/INTERFACE.md; the rules are DESIGN.md section 2. The template,
relocations, labels and counter names are generated from tools/qb_room by build.py.
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
MENU_SLOT = 0x2E04                   # RAM only (zero in the file): the menu sign_entry keeps for the 4a pass.
PIECE3_BYTES = 0x10BC                # piece 3 (both entries, room.c's code and tables); 4a is linked after it.

STAGE_D1, STAGE_D2D3, STAGE_D4, STAGE_SIGN, STAGE_TRADE, STAGE_E2 = 1, 2, 4, 8, 16, 32
STAGE_FLOOR = 64                     # the floor (DESIGN addendum F3): a club with no healthy quarterback gets one
STAGE_OVER_CAP = 128                 # the floor's last rung: sign past the gates, over the cap (only with 64)
STAGE_MASK = 255                     # 16 (trades, 4b) is not built: the page ignores it; 32 counts only with 8.
FLAG_SHADOW = 1
H0_PPM = 27000                       # D3 base 0.0270 in millionths: shadow panel P0's value, P1 ran at it (review F5).
D2_SCALE_MILLI = 1000                # D2 table scale in thousandths (1000 = the table as written).
LIMIT_PPM = 1_000_000                # Both are clamped to this in the page (a probability is at most 1).

DECISION_D1, DECISION_D2, DECISION_D3, DECISION_D4, DECISION_E1, DECISION_E2, DECISION_FLOOR = 1, 2, 3, 4, 5, 6, 7
RESULT_KEPT, RESULT_APPLIED, RESULT_SHADOW, RESULT_LOCK_ONLY, RESULT_OVER_CAP = 0, 1, 2, 3, 5

# (site, retail bytes, entry label, stage bits any of which needs the site; 0 = always). Whole 5-byte calls.
# 0x247DCA enters pregame_entry: opening_pass, then with bit 64 clear `jmp 0x2BE020` exactly as opening_entry (still in
# the template, piece 3's bytes) did; with bit 64 set it calls 0x2BE020, runs the floor and returns to 0x247DCF.
HOOKS = (
    (0x247DCA, bytes.fromhex("e851620700"), "pregame_entry", 0),
    (0x24807A, bytes.fromhex("e8016b0300"), "room_entry", 0),
    (0x248010, bytes.fromhex("e85bb80d00"), "sign_entry", STAGE_SIGN | STAGE_FLOOR),
)
# The floor's last rung enters the native signing past its gates: `sub esp, 0x114; jmp 0x322BB6` (DESIGN F7.5,
# correction C6). The installer authenticates 0x322BB6 onward and accepts retail or a recognized gate jump at 0x322BB0.
UNGATED_SIGNING = 0x322BB6


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
CODE_BYTES = 0x1f50
CODE_TAIL = (0x2e10, 0xf3)             # (page offset, bytes): the second code piece
CODE_RESERVED = (0x2200, 0x2400)        # reserved for code, zero until used

_TEMPLATE = b''.join((
    bytes.fromhex('9c60fce8fcffffff619de91ce02b009c60fce8fcffffff619de97ceb270056538b581085db0f8ea0'),
    bytes.fromhex('00000089c6694018fa00000099f7fb8d8812fdffff81f9470900007e07b947090000eb0685c97902'),
    bytes.fromhex('31c96946148813000099f7fb2ddc0500003d470900007e07b847090000eb0685c0790231c001c169'),
    bytes.fromhex('461c204e000099f7fb3d470900007e07b847090000eb0685c0790231c001c1694620a861000099f7'),
    bytes.fromhex('fbba4709000029c281fa470900007e07ba47090000eb0685d2790231d28d441103b90600000099f7'),
    bytes.fromhex('f9eb0231c05b5ec3555756535389c689142489ca8b7c241c8b2d0000000089e883e07f8b0db876e5'),
    bytes.fromhex('006bc0148d980000000066898800000000a1b476e5008843028b06884303837e04070f94c0c1e005'),
    bytes.fromhex('0b04248843048853058b4424188b4004668943068b4704668943088b463088430a8b463488430b8d'),
    bytes.fromhex('4638e8d7feffff6689430c8b47088b7c24182b470888430e8b4624b90a00000031d2f7f188430f8b'),
    bytes.fromhex('4424208943108d4501a300000000a19c00000040a39c0000005e5b5e5f5dc35389c1b83352425131'),
    bytes.fromhex('d233049189c3c1eb1031d869c06bcaeb8589c3c1eb0d31d869c035aeb2c289c3c1eb1031d84283fa'),
    bytes.fromhex('0c75d6b9a086010031d2f7f189d05bc383ec348914248b10895424048b15b876e500895424088b50'),
    bytes.fromhex('188954240c8b501c895424108b5020895424148b503c895424188b50488b484c8954241c894c2420'),
    bytes.fromhex('8b50508b485489542424894c24288b40588944242c89e0e863ffffff83c434c3837a30007523c742'),
    bytes.fromhex('300100000083780c0075168b128a425283c801884252a19400000040a394000000c3565389c689d3'),
    bytes.fromhex('8b42248b512489532489412489da89f0e8bbffffff89ca89f0e8b2ffffff837e0c00740da1980000'),
    bytes.fromhex('0040a398000000eb318b13668b42288b09668b592831d86625001c668b592831c366895928668b4a'),
    bytes.fromhex('2831c866894228a19000000040a3900000005b5ec35557565383ec0889c589d783c038e84efdffff'),
    bytes.fromhex('8b55402b5574b9a00000003d890200007e29b9820000003ded0200007e1db9640000003d51030000'),
    bytes.fromhex('7e1131c93db50300000f9ec14983e1df83c12d8b4530be0a00000085c0781cbe32000000741583f8'),
    bytes.fromhex('040f9fc00fb6c089c64e83e6ba81c6aa00000031c0837d34030f9fc0890424ff0c24832424d88304'),
    bytes.fromhex('2464bb9600000083fa057e19bb6400000083fa0a7e0f31db83fa0f0f9ec34b83e3dd83c33289f8bf'),
    bytes.fromhex('6400000031d2f7f78944240489d00fafc131d2f7f78b7c24040faff901f8bf6400000031d2f7f789'),
    bytes.fromhex('c189d00fafc631d2f7f70fafce01c831d2f7f789c18b04240fafc231d2f7f78b34240fafce01c831'),
    bytes.fromhex('d2f7f789c189d00fafc331d2f7f70fafcb01c88b5d24bee803000031d2f7f689c189d00fafc331d2'),
    bytes.fromhex('f7f60fafcb01c883c4085b5e5f5dc38b150000000081fa5142524f75178b150400000081fa4f4d76'),
    bytes.fromhex('3175098b15080000004a740ca10800000040a308000000c35557565381ec1c0200008b150c000000'),
    bytes.fromhex('895424748944247c85c07505b80700000085c20f84260c0000a1a476e5008944247083e80783f802'),
    bytes.fromhex('7610a10c00000040a30c000000e9050c0000a11829b70085c00f84f80b0000a11000000083e00189'),
    bytes.fromhex('4424788b1514000000a11800000081fa40420f007605ba40420f00899424940000003d40420f0076'),
    bytes.fromhex('05b840420f0089842498000000a1987fbd008944241085c0740831db891d987fbd0031db895c246c'),
    bytes.fromhex('83fb1f0f87070b0000a11000000040a31000000089d9b8504c0c00ffd08944240485c07510a11400'),
    bytes.fromhex('000040a314000000e9cf0a000081c3d75d39008b049d0000000085c07419a14001e60085c07510a1'),
    bytes.fromhex('1800000040a318000000e9a50a00008b4424040fb6801c0100003c41760231c08b7c24048d048789'),
    bytes.fromhex('44240889fb31c031d2bf01000000395c240874378b3385f6742c8a4e3584c97525668b4e2866c1e9'),
    bytes.fromhex('0a83e10783f807742d89fdd3e585d5752509ea406bc93489b40ca400000083c304ebc383f801760e'),
    bytes.fromhex('bb0100000088c1d3e34b39da7410a11c00000040a31c000000e91e0a0000898424800000008d5424'),
    bytes.fromhex('6c31c9894c240831db895a5c8b7a388b6f2031f681e50000c0bf75108b772431c981e6000000700f'),
    bytes.fromhex('94c189ce897264017424088d730183c23439f0740489f3ebc883bc24d0000000007510a120000000'),
    bytes.fromhex('40a320000000e9b9090000837c247c007416394424087410a12400000040a324000000e99c090000'),
    bytes.fromhex('a11829b7008b4004894424086bf6348d44246c01f08944240c8d74246c8b6e3889e88b7c240829f8'),
    bytes.fromhex('b95400000031d2f7f189463c8a452583e01ffec80f94c00fb6c08946608a455283e001894668ba01'),
    bytes.fromhex('00000089e9b8806d2400ffd0d95c24148b44241489c2c1ea170fb6fa80fa76763785c07833ba6400'),
    bytes.fromhex('00000fbae01e722a25ffff7f000d000080006bc064b99500000029f9ba01000000d3e201c2b99600'),
    bytes.fromhex('000029f9d3eaeb0231d2895640bf40ee140031d289e9ffd7894644ba0600000089e9ffd7894648ba'),
    bytes.fromhex('0700000089e9ffd789464cba0800000089e9ffd7894650ba0900000089e9ffd7894654ba0a000000'),
    bytes.fromhex('89e9ffd789465883c6343974240c0f8519ffffff8b4c2404b820770c00ffd089c689842484000000'),
    bytes.fromhex('8b4c2404b850770c00ffd089c7898424880000008b4c2404b880770c00ffd08984248c0000008d14'),
    bytes.fromhex('3e01d0898424a000000089f829f08984249c0000008b4424048b804c01000085c074100fb65056b8'),
    bytes.fromhex('3d00000080fa3c761eeb10a12800000040a328000000ba5300000089d083fa637605b86300000069'),
    bytes.fromhex('c0580200002df88e0000b92600000031d2f7f1ba4605000029c289942490000000f6442474050f84'),
    bytes.fromhex('df0400008d44246c31d28954240831d283786400744a8378680075448b7c240847897c2404837c24'),
    bytes.fromhex('080074248b7424088d4eff8b748c206bee348b784039bc2cac0000007d0a89748c24894c2408ebd5'),
    bytes.fromhex('8b7c24088954bc208b7c2404897c24088d4a0183c03439da740489caeba231c0894424148b5c2408'),
    bytes.fromhex('395c24140f84610400008b4424148b4484208944240c6bc0348b8c04d400000085c90f853a040000'),
    bytes.fromhex('8b9c04cc00000085db74178b8404b400000085c0750c8b7c24708d57f983fa0176386b74240c3483'),
    bytes.fromhex('bc34c800000000743085db752c8b9434b000000031c085d27e236bd20f399434b40000007c1731c0'),
    bytes.fromhex('837c2470070f97c0eb0bbb01000000eb0431db31c0837c247c00740985db7509e9c503000085db74'),
    bytes.fromhex('07f644247401740b85c07417f6442474047510a13400000040a334000000e99f0300006b74240c34'),
    bytes.fromhex('8dbc34a4000000897c24048b152c0000004289152c00000085db0f84620100006b94248000000034'),
    bytes.fromhex('8d44246c01c231f639c274228d783883786400741483786000750e85f674088b6e083968407e0289'),
    bytes.fromhex('fe83c034ebdaa13800000040a33800000085f67510a13c00000040a33c000000e9180300006b7c24'),
    bytes.fromhex('0c348b843cac0000008b560889c529d50f889900000083fd050f8fbc00000069ed78ecffff81c508'),
    bytes.fromhex('4c0100c744243c010000008b4c246c894c24408b0db876e500894c24448b0db476e500894c24488b'),
    bytes.fromhex('4e04894c244c8b8c3ca8000000894c245089542454894424588b8424b40000008944245c8b8424bc'),
    bytes.fromhex('00000089442460a1a8fce50089442464a1b0fce500894424688d44243ce83df7ffff89c2a1400000'),
    bytes.fromhex('0040a34000000089d939ea7332eb05bda0860100a14400000040a3440000006b44240c348b7e2439'),
    bytes.fromhex('bc04c80000000f92c00fb6c089c7e97305000031ed31dba14800000040a3480000006b44240c348b'),
    bytes.fromhex('8404c80000003946240f92c00fb6c089c789d931dbe94405000085c00f84f80100008b8434ac0000'),
    bytes.fromhex('00894424188b9424ac00000089c629d68bac24b400000083fd597e3d8954241c8d8424a4000000e8'),
    bytes.fromhex('2af5ffff3d830300008b54241c7e228b8c24840000003b8c248800000019c0403b8c248800000019'),
    bytes.fromhex('ff83e7f083c714eb0731c0bf040000008b0d7800000041890d7800000085c0740d8b0d7c00000041'),
    bytes.fromhex('890d7c0000008d4e0283f904763fa18000000040a3800000008b5424048d44246ce8c2f6ffff566a'),
    bytes.fromhex('00ff74240c8d8424b000000050b90300000089fa8d44247ce84bf5ffff83c410e94501000085f678'),
    bytes.fromhex('1383f80119f681e650c3000081c630750000eb1183f80119f681e6a861000081c610270000c74424'),
    bytes.fromhex('3c040000008b44246c89442440a1b876e50089442444a1b476e500894424488b8424a80000008944'),
    bytes.fromhex('244c6b44240c348b8404a800000089442450895424548b44241889442458896c245c8b8424bc0000'),
    bytes.fromhex('0089442460a1a8fce50089442464a1b0fce500894424688d44243ce85ff5ffff89c5a18400000040'),
    bytes.fromhex('a38400000039f57330a18800000040a3880000008d8c24a40000008b5424048d44246ce8faf5ffff'),
    bytes.fromhex('837c24780119c983c102bb40000000eb2aa18c00000040a38c0000008b5424048d44246ce8a7f5ff'),
    bytes.fromhex('ff8d9424a40000008d44246ce897f5ffff31c909df89fa5356ff74240c8d8424b0000000508d4424'),
    bytes.fromhex('7ce822f4ffff83c41039f5731de922030000a13000000040a3300000008b5424048d44246ce856f5'),
    bytes.fromhex('ffffff442414e991fbffff8b5c247c85db0f85f5020000837c2470080f85ea020000f6442474020f'),
    bytes.fromhex('84df0200008b8424a00000004883f80f0f87ce02000083bc24b40000003b7f298bbc24cc00000085'),
    bytes.fromhex('ff0f85b50200008b8c24800000008d8424d8000000ba0100000031dbe91301000083bc2404010000'),
    bytes.fromhex('0074cda16000000040a360000000ba40420f008d44246ce859f5ffff8b157000000001d0730d8b15'),
    bytes.fromhex('7400000042891574000000a3700000008b9424940000008d44246ce82df5ffffb90a00000031d2f7'),
    bytes.fromhex('f189c6ba030000008d44246ce81ff4ffff89c7a16400000040a36400000039f77333a16800000040'),
    bytes.fromhex('a3680000008d8c24a40000008d9424d80000008d44246ce876f4ffff837c24780119db83c302ba43'),
    bytes.fromhex('000000eb30a16c00000040a36c0000008d9424a40000008d44246ce820f4ffff8d9424d80000008d'),
    bytes.fromhex('44246ce810f4ffffba0300000051568d8424e0000000508d8424b00000005089d98d44247ce896f2'),
    bytes.fromhex('ffff83c41039f70f8297010000e9cefeffff83782c00750a4283c03439ca72f2eb168378280074f0'),
    bytes.fromhex('85db74088b73083970087ee489c3ebe085db0f84640100008b43082b8424ac00000083f8fb0f8c51'),
    bytes.fromhex('010000a15000000040a3500000008b94249c000000b8a00f000085d27819b8e02e000074124ab800'),
    bytes.fromhex('71020083fa0377078b0495ac1000008b9424a0000000be3200000083fa01741131c983fa070f9ec1'),
    bytes.fromhex('89ce4e83e6ba83c6648b8c2498000000bde803000031d2f7f58944240489d00fafc131d2f7f58b6c'),
    bytes.fromhex('24040fafe901e8bd6400000031d2f7f589c189d00fafc631d2f7f50fafce01c88bb42490000000bd'),
    bytes.fromhex('e803000031d2f7f589c189d00fafc631d2f7f50fafce01c8b90a00000031d2f7f189c6ba02000000'),
    bytes.fromhex('8d44246ce86ff2ffff89c2a15400000040a35400000039f2732ea15800000040a3580000008d8c24'),
    bytes.fromhex('a400000089da8d44246ce8cbf2ffff837c24780119ff83c702ba42000000eb2ba15c00000040a35c'),
    bytes.fromhex('0000008d9424a40000008d44246ce875f2ffff89da8d44246ce86af2ffffba020000005056538d84'),
    bytes.fromhex('24b00000005089f98d44247ce8f7f0ffff83c4108b44246c8d5801e9ecf4ffff837c2410000f8484'),
    bytes.fromhex('0000008b442410a3987fbd00eb7985ff742a89f18b5424048d44246ce841f2ffffa14c00000040a3'),
    bytes.fromhex('4c00000089f9837c2478007427b902000000eb208b5424048d44246ce8eff1ffff89f28d44246ce8'),
    bytes.fromhex('e4f1ffff83f90119c983e10385db7505bb410000005055ff74240c5689da8d44247ce869f0ffff83'),
    bytes.fromhex('c41085ff0f8460fcffffe965ffffff81c41c0200005b5e5f5dc3a10000000040a300000000b80100'),
    bytes.fromhex('0000e960f3ffffa10400000040a30400000031c0e94ef3ffff669090b888000070110100a0860100'),
    bytes.fromhex('d0fb0100f740200000c0bf750ef74024000000700f94c00fb6c0c331c0c383ec1c89c1ba01000000'),
    bytes.fromhex('b8806d2400ffd0d95c240c8b44240c85c0790231c083c41cc389c2c1ea1780fa767637530fb6daba'),
    bytes.fromhex('640000000fbae01e722b25ffff7f000d000080006bc064b99500000029d9ba01000000d3e201c2b9'),
    bytes.fromhex('9600000029d9d3eaeb0331c0c389d05bc3538b1d78c2e3008b0c955c77e50085c974110fb7889c01'),
    bytes.fromhex('000031d281f9ffff0000740a31d239d9730429cb89da2b902401000089d05bc35557565383ec2c89'),
    bytes.fromhex('44241489542418894c241c31f631ed31ff31c08944240c894424108b4424140fb6801c01000039c6'),
    bytes.fromhex('733a8b4424148b1cb085db742c807b35007526ff44241089d8e8f6feffff85c07417ff44240c89d8'),
    bytes.fromhex('e801ffffff39c5720485ff750489c589df46ebb78b4424188b54240c89108b44241c89388b442440'),
    bytes.fromhex('89288b44241083c42c5b5e5f5dc3530fb6981c01000031c939d97308391488740741ebf431c0eb05'),
    bytes.fromhex('b8010000005bc35557565383ec1c89442408a11829b7008b68388b403c89442404bb603c0e0029eb'),
    bytes.fromhex('c1e30431f631c9890c248d456439c60f838900000039ee7219f6430b03746f8b4308250000001c3d'),
    bytes.fromhex('0000000c75608b0beb078b4424048b0cb085c9745180793500754b833c2440744e8b3c24c1e7048b'),
    bytes.fromhex('44240801c7890f31c039ee0f93c089470c89c8894c240ce822feffff894704506a006a016a0031d2'),
    bytes.fromhex('8b4c241cb840d42b00ffd0ff4424040fb7c08947085a4683c310e973ffffffc70424410000008b04'),
    bytes.fromhex('2483c41c5b5e5f5dc35557565383ec1c8904248954240c894c241889d0c1e0048b342401f0894424'),
    bytes.fromhex('1489f231f68974240431c98b7c240c397c24040f84c00000008b720c85f60f85a90000008b5a0881'),
    bytes.fromhex('fbfeff00000f879a0000008b3a89f8e870fdffff85c00f8489000000837c24300075118b44241883'),
    bytes.fromhex('e80a39d87e7785c97524eb2a837c243001750cf647240f7564807f253f765e85c974138b410839d8'),
    bytes.fromhex('725339c375088b420439410473478d4301894424108b042431db895c240831ed85f674053b680473'),
    bytes.fromhex('178b5c2410395808730e8b30897424088b6804be0100000083c0108b5c241439d875d58b44240839'),
    bytes.fromhex('c7750289d1ff44240483c210e932ffffff89c883c41c5b5e5f5dc35557565381ec7c040000894424'),
    bytes.fromhex('3889d5894c2414b8504c0c00ffd08944240c85c00f84100400008b442414833c855c77e500007414'),
    bytes.fromhex('833d3c01e60001740bff05c0000000e9ee0300008b44240c80b81c010000410f87dd03000083ec0c'),
    bytes.fromhex('8d442454508d4c24548d5424508b44241ce812fdffff83c41083f8020f87b803000031f6837c2444'),
    bytes.fromhex('00740b8b442448e875fcffff89c6837c2440010f868f000000f6842490040000200f848b030000a1'),
    bytes.fromhex('0000000085c0746d813836324952756569542414a40000008d4410408d58040fb60083f8147605b8'),
    bytes.fromhex('140000008d14c339d30f84530300008b3b85ff750583c308ebed807f350075f58954241089f8e8e3'),
    bytes.fromhex('fbffffe801fcffff29f083f8028b5424107edaf643060175218b4720c1e8163c0276caeb15ff05cc'),
    bytes.fromhex('000000e90a030000c744241005000000eb08c7442410060000008d442470e8ecfcffff89c383f840'),
    bytes.fromhex('760bff05c8000000e9dd02000085ed750b8b4c240cb8003f0c00ffd08b5424148b44240ce8d8fbff'),
    bytes.fromhex('ff89c183ec0c6a0089da8d842480000000e873fdffff83c41089c38b4c240cb820770c00ffd08944'),
    bytes.fromhex('24208b4c240cb850770c00ffd0894424248b4c240cb880770c00ffd08944242831c0837c2410050f'),
    bytes.fromhex('94c089442418ff4c241881642418b03cffff81442418a08601008b4424248b7c242029f88944242c'),
    bytes.fromhex('89f88b7c242401f88b7c242801f88944243085db0f84120100008b4304e8f7faffff29f08944241c'),
    bytes.fromhex('837c2410060f850a010000480f8e10020000ff05a80000008b3d987fbd0085ff740831d28915987f'),
    bytes.fromhex('bd008b4c2444be40ee1400ba06000000894c243cffd689442434ba080000008b4c243cffd689c185'),
    bytes.fromhex('ff7406893d987fbd00c744244c060000008b44241489442450a1b876e500894424548b4424208944'),
    bytes.fromhex('24588b4424248944245c8b442428894424608b038b151829b7002b4204bf5400000031d2f7f78944'),
    bytes.fromhex('24648b44243489442468894c246cff05d0000000b83352425131d23344944c89c1c1e91031c869c0'),
    bytes.fromhex('6bcaeb8589c1c1e90d31c869c035aeb2c289c1c1e91031c84283fa0975d5b9a086010031d2f7f181'),
    bytes.fromhex('fa4fc300007637ff05d400000031ede9f1000000837c2410060f841301000031c08944241cff05a0'),
    bytes.fromhex('00000085db750fff05c400000031c931ede9cb00000085ed7410ff05d8000000bd02000000e9b300'),
    bytes.fromhex('00008b44240c80b81c010000357568ba3400000089c1b8a0f92b00ffd0ff05dc0000008b4c240cb8'),
    bytes.fromhex('003f0c00ffd08d442470e8a8faffff89c683f840772b8b5424148b44240ce8aef9ffff89c183ec0c'),
    bytes.fromhex('6a0089f28d842480000000e849fbffff83c41089c385c0750eff05e000000031c985db7444eb3eff'),
    bytes.fromhex('7424388b430840506a00ff742418b8b02b3200ffd089c585c0741c837c241005750dff05a4000000'),
    bytes.fromhex('bd01000000eb0eff05ac000000ebf1ff05e400000089e98b2bff7424186a00ff7424246a00ff7424'),
    bytes.fromhex('40ff74244055ff7424608b5424308b442434e80c2e000083c42081c47c0400005b5e5f5dc3555756'),
    bytes.fromhex('5383ec208b7c24388b4424340fb6a81c01000031f631d231db83fa07772f39eb732b8b4424348b04'),
    bytes.fromhex('9885c0741d39c77419807835007513668b482866c1e90a83e10739f175048904944243ebcc4683fe'),
    bytes.fromhex('0875c431c939ca74328b1c8c668b432880e4e3be001c000083f90577068d7101c1e60a09f0668943'),
    bytes.fromhex('2889d8e804f8ffff85c07504806352fc41ebca66816728ffe3ff052c01000083c4205b5e5f5dc355'),
    bytes.fromhex('57565381ec5c0400008944242089542428894c2418b8504c0c00ffd08944240c85c00f84d6040000'),
    bytes.fromhex('051c0100008944242c8b44240c80b81c010000410f87bc0400008b442418833c855c77e50000740d'),
    bytes.fromhex('833d3c01e600010f85a104000083ec0c8d442458508d4c24588d5424548b44241ce82af8ffff8944'),
    bytes.fromhex('24248b4424548944244083c41085c00f8571040000837c241402761583bc247004000000750bff05'),
    bytes.fromhex('f0000000e955040000ff05ec0000008d442450e897f8ffff89c38b5424188b44240ce8a2f7ffff89'),
    bytes.fromhex('44243883fb4077118d542450c1e30401d331c9894c2410eb26ff05f8000000eb2f31c0837a0c0075'),
    bytes.fromhex('0f8b02e8ecf6ffff85c00f95c00fb6c00944241083c21039da75de837c2410007527ff05f4000000'),
    bytes.fromhex('31c08944242031f631c08944241431ed31c08944241c8944242431dbe959030000837c2420007429'),
    bytes.fromhex('ff05fc00000031f631c08944241431ed31c08944241c8944242431c0c744242002000000e9610300'),
    bytes.fromhex('0031c9894c241c894c242483bc2470040000000f95c2837c2428000f95c084c20f849b0000008b44'),
    bytes.fromhex('24148b7c241c29f883f8020f868800000031ff31ed31db8b44242c0fb60039c7732b8b44240c8b34'),
    bytes.fromhex('b885f67415807e3500750f89f0e834f6ffff85db740839c5730489e889de4789c589f3ebca56566a'),
    bytes.fromhex('016a0189da8b4c241cb800d92b00ffd05f5d89da8b44240ce831f7ffff85c07415ff050401000031'),
    bytes.fromhex('f631db895c241431ede91cffffffff44241cff0500010000895c2424e94affffff837c2428007421'),
    bytes.fromhex('8b44240c80b81c010000357514ba3400000089c1b8a0f92b00ffd0ff050801000031ff31d2895424'),
    bytes.fromhex('1431ed31db8b4c240cb8003f0c00ffd08d442450e8def6ffff89c683f840760bff05f8000000e9c9'),
    bytes.fromhex('0000008b5424188b44240ce8d9f5ffff89c183ec0c6a0089f28d442460e877f7ffff83c41089c385'),
    bytes.fromhex('c0742585ff740dff051c010000be02000000eb0aff050c0100008b742410b8b02b3200e961010000'),
    bytes.fromhex('837c242800746f83ec0c6a0131c989f28d442460e830f7ffff83c41089c385c0752383ec0c6a0231'),
    bytes.fromhex('c989f28d442460e815f7ffff83c41089c385c07508ff0510010000eb3785ff0f849a0000008b4424'),
    bytes.fromhex('0c80b81c01000034771cf6442428807415ff0520010000be03000000b800000000e9eb000000ff05'),
    bytes.fromhex('2401000031f6e93f0100008b44240c8b0cb831c085c9741131d2894c243cb8609f3b00ffd08b4c24'),
    bytes.fromhex('3c394424347c068b44243489f1478944243489ce8b44242c0fb60039c772c485f60f848a000000ba'),
    bytes.fromhex('0100000089f1b8609f3b00ffd045ff05140100008b4c240cb8003f0c00ffd083fd0277658b542418'),
    bytes.fromhex('8b44240ce8a0f4ffff83e80a3b43087f5031ff31f6c7442434fa000000eba58b5424188b44240ce8'),
    bytes.fromhex('7df4ffff83e80a3b43087f348b44242c0fb61080fa3276284a8b4c240cb8a0f92b00ffd0ff442414'),
    bytes.fromhex('ff05180100008b4c240cb8003f0c00ffd0837c24140176b78b7c2410e92cfeffffffb42474040000'),
    bytes.fromhex('8b7b088d5701526a00ff742418ffd085c074418b138b44240ce8d8f4ffff85c0743283fe037508c7'),
    bytes.fromhex('4424100500000083bc247004000000750a8b44241089442420eb17505052ff742418e8fcffffff83'),
    bytes.fromhex('c410ebe5ff052801000083ec0c8d442458508d4c24588d5424548b44241ce8f5f3ffff83c410837c'),
    bytes.fromhex('2444007506ff053001000031c085db74098b43088b3b897c2430837c24280119d283e22083c20750'),
    bytes.fromhex('ff74242056ff742444ff74242455ff742448ff7424408b4c24408b442438e80c2e000083c42081c4'),
    bytes.fromhex('5c0400005b5e5f5dc35557565383ec1c8b6c243485ed7408ff05e8000000eb06ff05b8000000a100'),
    bytes.fromhex('0000003d5142524f7514a1040000003d4f4d76317508a10800000048741385ed0f85bb000000ff05'),
    bytes.fromhex('08000000e9b00000008b1d0c000000a1a476e50031ff85ed751189dac1ea0331c983f8080f94c189'),
    bytes.fromhex('cf21d789dac1ea068d48f983f9020f96c121d1884c240f0fb6d185ed7510f6c308740b83f8087406'),
    bytes.fromhex('ff05bc00000009fa745f833d1829b7000074568b151000000083e2018954240883f807750231db31'),
    bytes.fromhex('f685ff75195050ff7424385589f189da8b442418e81efaffff83c410eb1d83ec0c5389f18b542418'),
    bytes.fromhex('8b442440e822f5ffff83c410807c240f0075ca4683fe2075c083c41c5b5e5f5dc3890d00000000c7'),
    bytes.fromhex('042400000000e96c3832009c60fc6a00ff3500000000e8fcffffff83c408619de9118024009c60fc'),
    bytes.fromhex('e8fcfffffff6050c000000407507619de91ce02b00619de81ce02b009c60fc6a0155e8fcffffff83'),
    bytes.fromhex('c408619dc381ec14010000e9b22b3200'),
    b'\xcc' * 176,
    bytes(3600),
    bytes.fromhex('5557565383ec28890424894c24048b6c243c8b7c24408b5c244c8b0d000000008b351829b7008b76'),
    bytes.fromhex('04a1b876e5006689442414a0b476e500884424168a042488442417885424188a4424048844241983'),
    bytes.fromhex('c8ff85ed740d89e829f0bd5400000031d2f7f5668944241a83c8ff85ff740d89f829f0be54000000'),
    bytes.fromhex('31d2f7f6668944241c8b4424448844241e8b4424488844241f31c085db780d83c8ff81fbffff0000'),
    bytes.fromhex('7f0289d866894424208b442450884424228b442454884424238b4424588944242489ca83e27f6bd2'),
    bytes.fromhex('1481c20000000031c08b5c8414891c824083f80575f341890d00000000ff059c00000083c4285b5e'),
    bytes.fromhex('5f5dc3'),
    bytes(253),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0004, True, 'page', 0x107e),
    (0x000b, True, 'stock', 0x2be01c),
    (0x0013, True, 'page', 0x1093),
    (0x001a, True, 'stock', 0x27eb7c),
    (0x00e2, False, 'page', 0x2e00),
    (0x00f6, False, 'page', 0x2400),
    (0x00fd, False, 'page', 0x2400),
    (0x0172, False, 'page', 0x2e00),
    (0x0177, False, 'page', 0x20dc),
    (0x017d, False, 'page', 0x20dc),
    (0x0247, False, 'page', 0x20d4),
    (0x024d, False, 'page', 0x20d4),
    (0x027d, False, 'page', 0x20d8),
    (0x0283, False, 'page', 0x20d8),
    (0x02b0, False, 'page', 0x20d0),
    (0x02b6, False, 'page', 0x20d0),
    (0x03f9, False, 'page', 0x2000),
    (0x0407, False, 'page', 0x2004),
    (0x0415, False, 'page', 0x2008),
    (0x041d, False, 'page', 0x2048),
    (0x0423, False, 'page', 0x2048),
    (0x0434, False, 'page', 0x200c),
    (0x0463, False, 'page', 0x204c),
    (0x0469, False, 'page', 0x204c),
    (0x0480, False, 'page', 0x2010),
    (0x048d, False, 'page', 0x2014),
    (0x0492, False, 'page', 0x2018),
    (0x04e2, False, 'page', 0x2050),
    (0x04e8, False, 'page', 0x2050),
    (0x04fe, False, 'page', 0x2054),
    (0x0504, False, 'page', 0x2054),
    (0x0528, False, 'page', 0x2058),
    (0x052e, False, 'page', 0x2058),
    (0x05af, False, 'page', 0x205c),
    (0x05b5, False, 'page', 0x205c),
    (0x0614, False, 'page', 0x2060),
    (0x061a, False, 'page', 0x2060),
    (0x0631, False, 'page', 0x2064),
    (0x0637, False, 'page', 0x2064),
    (0x07b4, False, 'page', 0x2068),
    (0x07ba, False, 'page', 0x2068),
    (0x0924, False, 'page', 0x2074),
    (0x092a, False, 'page', 0x2074),
    (0x0945, False, 'page', 0x206c),
    (0x094c, False, 'page', 0x206c),
    (0x098f, False, 'page', 0x2078),
    (0x0995, False, 'page', 0x2078),
    (0x099e, False, 'page', 0x207c),
    (0x09a4, False, 'page', 0x207c),
    (0x0a4d, False, 'page', 0x2080),
    (0x0a53, False, 'page', 0x2080),
    (0x0a65, False, 'page', 0x2084),
    (0x0a6b, False, 'page', 0x2084),
    (0x0a90, False, 'page', 0x2088),
    (0x0a96, False, 'page', 0x2088),
    (0x0b2a, False, 'page', 0x20b8),
    (0x0b31, False, 'page', 0x20b8),
    (0x0b3b, False, 'page', 0x20bc),
    (0x0b42, False, 'page', 0x20bc),
    (0x0b4f, False, 'page', 0x20c0),
    (0x0b55, False, 'page', 0x20c0),
    (0x0c2b, False, 'page', 0x20c4),
    (0x0c31, False, 'page', 0x20c4),
    (0x0c3a, False, 'page', 0x20c8),
    (0x0c40, False, 'page', 0x20c8),
    (0x0c6a, False, 'page', 0x20cc),
    (0x0c70, False, 'page', 0x20cc),
    (0x0cbb, False, 'page', 0x2070),
    (0x0cc1, False, 'page', 0x2070),
    (0x0d4c, False, 'page', 0x20a0),
    (0x0d52, False, 'page', 0x20a0),
    (0x0d66, False, 'page', 0x20b0),
    (0x0d70, False, 'page', 0x20b4),
    (0x0d77, False, 'page', 0x20b4),
    (0x0d7c, False, 'page', 0x20b0),
    (0x0dac, False, 'page', 0x20a4),
    (0x0db2, False, 'page', 0x20a4),
    (0x0dbb, False, 'page', 0x20a8),
    (0x0dc1, False, 'page', 0x20a8),
    (0x0dee, False, 'page', 0x20ac),
    (0x0df4, False, 'page', 0x20ac),
    (0x0e8c, False, 'page', 0x2090),
    (0x0e92, False, 'page', 0x2090),
    (0x0ebb, False, 'page', 0x10ac),
    (0x0f5c, False, 'page', 0x2094),
    (0x0f62, False, 'page', 0x2094),
    (0x0f6b, False, 'page', 0x2098),
    (0x0f71, False, 'page', 0x2098),
    (0x0f99, False, 'page', 0x209c),
    (0x0f9f, False, 'page', 0x209c),
    (0x1012, False, 'page', 0x208c),
    (0x1018, False, 'page', 0x208c),
    (0x1083, False, 'page', 0x2040),
    (0x1089, False, 'page', 0x2040),
    (0x1098, False, 'page', 0x2044),
    (0x109e, False, 'page', 0x2044),
    (0x1433, False, 'page', 0x2100),
    (0x14a0, False, 'page', 0x2020),
    (0x1517, False, 'page', 0x210c),
    (0x1544, False, 'page', 0x2108),
    (0x161c, False, 'page', 0x20e8),
    (0x16b8, False, 'page', 0x2110),
    (0x1701, False, 'page', 0x2114),
    (0x171f, False, 'page', 0x20e0),
    (0x1729, False, 'page', 0x2104),
    (0x173c, False, 'page', 0x2118),
    (0x1767, False, 'page', 0x211c),
    (0x17b3, False, 'page', 0x2120),
    (0x17e4, False, 'page', 0x20e4),
    (0x17f1, False, 'page', 0x20ec),
    (0x17f9, False, 'page', 0x2124),
    (0x1823, True, 'page', 0x2e0c),
    (0x18cb, False, 'page', 0x216c),
    (0x1978, False, 'page', 0x2130),
    (0x1983, False, 'page', 0x212c),
    (0x19bb, False, 'page', 0x2138),
    (0x19ec, False, 'page', 0x2134),
    (0x1a1a, False, 'page', 0x213c),
    (0x1adb, False, 'page', 0x2144),
    (0x1af4, False, 'page', 0x2140),
    (0x1b25, False, 'page', 0x2148),
    (0x1b52, False, 'page', 0x2138),
    (0x1b89, False, 'page', 0x215c),
    (0x1b96, False, 'page', 0x214c),
    (0x1be7, False, 'page', 0x2150),
    (0x1c0b, False, 'page', 0x2160),
    (0x1c15, False, 'page', 0x1f45),
    (0x1c20, False, 'page', 0x2164),
    (0x1c80, False, 'page', 0x2154),
    (0x1cea, False, 'page', 0x2158),
    (0x1d5b, True, 'page', 0x1831),
    (0x1d66, False, 'page', 0x2168),
    (0x1d8f, False, 'page', 0x2170),
    (0x1dcf, True, 'page', 0x2e0c),
    (0x1df2, False, 'page', 0x2128),
    (0x1dfa, False, 'page', 0x20f8),
    (0x1dff, False, 'page', 0x2000),
    (0x1e0b, False, 'page', 0x2004),
    (0x1e17, False, 'page', 0x2008),
    (0x1e28, False, 'page', 0x2048),
    (0x1e33, False, 'page', 0x200c),
    (0x1e7a, False, 'page', 0x20fc),
    (0x1e8d, False, 'page', 0x2010),
    (0x1eeb, False, 'page', 0x2e04),
    (0x1ef2, False, 'page', 0x1efb),
    (0x1ef7, True, 'stock', 0x32386c),
    (0x1f02, False, 'page', 0x2e04),
    (0x1f07, True, 'page', 0x1ddd),
    (0x1f11, True, 'stock', 0x248011),
    (0x1f19, True, 'page', 0x107e),
    (0x1f1f, False, 'page', 0x200c),
    (0x1f29, True, 'stock', 0x2be01c),
    (0x1f30, True, 'stock', 0x2be01c),
    (0x1f3b, True, 'page', 0x1ddd),
    (0x1f4c, True, 'stock', 0x322bb2),
    (0x2e2c, False, 'page', 0x2e00),
    (0x2edb, False, 'page', 0x2400),
    (0x2ef1, False, 'page', 0x2e00),
    (0x2ef7, False, 'page', 0x20dc),
)

LABELS = {
    'emergency_pass': 0x1de1,
    'floor_seat': 0x1835,
    'opening_entry': 0x0,
    'opening_pass': 0x1082,
    'pregame_entry': 0x1f15,
    'room_entry': 0xf,
    'room_pass': 0x1097,
    'sign_after': 0x1efb,
    'sign_entry': 0x1ee9,
    'sign_ungated': 0x1f45,
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
    'sign_passes': 0x20f8,
    'sign_inactive': 0x20fc,
    'sign_skip_human': 0x2100,
    'sign_no_candidate': 0x2104,
    'sign_pool_overflow': 0x2108,
    'sign_ir_unlinked': 0x210c,
    'e2_drawn': 0x2110,
    'e2_kept': 0x2114,
    'sign_shadow': 0x2118,
    'sign_cuts': 0x211c,
    'sign_room_lost': 0x2120,
    'sign_failed': 0x2124,
    'floor_pregame_passes': 0x2128,
    'floor_runs': 0x212c,
    'floor_post_deferred': 0x2130,
    'floor_no_free_agent': 0x2134,
    'floor_pool_overflow': 0x2138,
    'floor_shadow': 0x213c,
    'floor_swaps': 0x2140,
    'floor_swap_stuck': 0x2144,
    'floor_cuts': 0x2148,
    'floor_candidate': 0x214c,
    'floor_no_target': 0x2150,
    'floor_restructures': 0x2154,
    'floor_releases': 0x2158,
    'floor_gated': 0x215c,
    'floor_over_cap': 0x2160,
    'floor_no_room': 0x2164,
    'floor_sign_failed': 0x2168,
    'floor_seated': 0x216c,
    'floor_failed': 0x2170,
}

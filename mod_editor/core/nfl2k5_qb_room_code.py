"""Relocatable page of the quarterback room owner (beta 81 piece 3, owner nfl2k5_qb_room).

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

STAGE_D1, STAGE_D2D3, STAGE_D4, STAGE_SIGN, STAGE_TRADE, STAGE_E2 = 1, 2, 4, 8, 16, 32
STAGE_D2 = STAGE_D2D3                # D2 alone since the review (DESIGN addendum 2, R5); the old name is kept
STAGE_D3 = 256                       # D3 and the season reset (R1), on their own bit (R5)
STAGE_FLOOR = 64                     # the floor (DESIGN addendum F3): a club with no healthy quarterback gets one
STAGE_OVER_CAP = 128                 # the floor's last rung: sign past the gates, over the cap (only with 64)
STAGE_MASK = 511                     # 16 (trades, 4b) is not built: the page ignores it; 32 counts only with 8.
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
CODE_BYTES = 0x1dd0
PIECE3_BYTES = 0xf3c             # piece 3's main part (the entries, room.c's code and tables)
CODE_TAIL = (0x2e10, 0x17b)             # (page offset, bytes): the second code piece
CODE_MID = (0x2200, 0x1af)              # (page offset, bytes): the third piece
CODE_RESERVED = (0x2200, 0x2400)        # the middle piece's range

_TEMPLATE = b''.join((
    bytes.fromhex('9c60fce8fcffffff619de91ce02b009c60fce8fcffffff619de97ceb27005389d189c28d0c88b833'),
    bytes.fromhex('524251330289c3c1eb1031d869c06bcaeb8589c3c1eb0d31d869c035aeb2c289c3c1eb1031d883c2'),
    bytes.fromhex('0439d175d6b9a086010031d2f7f189d05bc356538b581085db0f8ea000000089c6694018fa000000'),
    bytes.fromhex('99f7fb8d8812fdffff81f9470900007e07b947090000eb0685c9790231c96946148813000099f7fb'),
    bytes.fromhex('2ddc0500003d470900007e07b847090000eb0685c0790231c001c169461c204e000099f7fb3d4709'),
    bytes.fromhex('00007e07b847090000eb0685c0790231c001c1694620a861000099f7fbba4709000029c281fa4709'),
    bytes.fromhex('00007e07ba47090000eb0685d2790231d28d441103b90600000099f7f9eb0231c05b5ec355575653'),
    bytes.fromhex('5389c689142489ca8b7c241c8b2d0000000089e883e07f8b0db876e5006bc0148d98000000006689'),
    bytes.fromhex('8800000000a1b476e5008843028b06884303837e04070f94c0c1e0050b04248843048853058b4424'),
    bytes.fromhex('188b4004668943068b4704668943088b463088430a8b463488430b8d4638e8d7feffff6689430c8b'),
    bytes.fromhex('47088b7c24182b470888430e8b4624b90a00000031d2f7f188430f8b4424208943108d4501a30000'),
    bytes.fromhex('0000a19c00000040a39c0000005e5b5e5f5dc383ec348914248b10895424048b15b876e500895424'),
    bytes.fromhex('088b50188954240c8b501c895424108b5020895424148b503c895424188b50488b484c8954241c89'),
    bytes.fromhex('4c24208b50508b485489542424894c24288b40588944242cba0c00000089e0e8f2fdffff83c434c3'),
    bytes.fromhex('837a30007523c742300100000083780c0075168b128a425283c801884252a19400000040a3940000'),
    bytes.fromhex('00c3565389c689d38b42248b512489532489412489da89f0e8bbffffff89ca89f0e8b2ffffff837e'),
    bytes.fromhex('0c00740da19800000040a398000000eb318b13668b42288b09668b592831d86625001c668b592831'),
    bytes.fromhex('c366895928668b4a2831c866894228a19000000040a3900000005b5ec35557565383ec0889c589d7'),
    bytes.fromhex('83c038e88afdffff8b55402b5574b9a00000003d890200007e29b9820000003ded0200007e1db964'),
    bytes.fromhex('0000003d510300007e1131c93db50300000f9ec14983e1df83c12d8b4530be0a00000085c0781cbe'),
    bytes.fromhex('32000000741583f8040f9fc00fb6c089c64e83e6ba81c6aa00000031c0837d34030f9fc0890424ff'),
    bytes.fromhex('0c24832424d883042464bb9600000083fa057e19bb6400000083fa0a7e0f31db83fa0f0f9ec34b83'),
    bytes.fromhex('e3dd83c33289f8bf6400000031d2f7f78944240489d00fafc131d2f7f78b7c24040faff901f8bf64'),
    bytes.fromhex('00000031d2f7f789c189d00fafc631d2f7f70fafce01c831d2f7f789c18b04240fafc231d2f7f78b'),
    bytes.fromhex('34240fafce01c831d2f7f789c189d00fafc331d2f7f70fafcb01c88b5d24bee803000031d2f7f689'),
    bytes.fromhex('c189d00fafc331d2f7f60fafcb01c883c4085b5e5f5dc38b150000000081fa5142524f75178b1504'),
    bytes.fromhex('00000081fa4f4d763175098b15080000004a740ca10800000040a308000000c35557565381ec0c02'),
    bytes.fromhex('00008b150c000000895424648944246c83f80119c083e006050101000085c20f849c0a0000a1a476'),
    bytes.fromhex('e5008944246083e80783f8027610a10c00000040a30c000000e97b0a0000a11829b70085c00f846e'),
    bytes.fromhex('0a0000a11000000083e001894424688b1514000000a11800000081fa40420f007605ba40420f0089'),
    bytes.fromhex('9424840000003d40420f007605b840420f0089842488000000a1987fbd008944240c85c0740831ff'),
    bytes.fromhex('893d987fbd0031db895c245c83fb1f0f87fc090000a11000000040a31000000089d9b8504c0c00ff'),
    bytes.fromhex('d089c585c07510a11400000040a314000000e9c609000081c3d75d39008b049d0000000085c07419'),
    bytes.fromhex('a14001e60085c07510a11800000040a318000000e99c0900000fb6851c0100003c41760231c08d44'),
    bytes.fromhex('85008944240889eb31c031f689742404bf01000000395c2408743b8b3385f674308a4e3584c97529'),
    bytes.fromhex('668b4e2866c1e90a83e10783f807743389fad3e285542404752909542404406bc93489b40c940000'),
    bytes.fromhex('0083c304ebbf83f8017610bb0100000088c1d3e34b395c24047410a11c00000040a31c000000e912'),
    bytes.fromhex('090000894424708d54245c31c9894c24088b7c2408897a5c8b5a388b732031c981e60000c0bf750f'),
    bytes.fromhex('8b4b2481e1000000700f94c10fb6c9894a648b7c240847897c240483c23439f8740a8b7c2404897c'),
    bytes.fromhex('2408ebbd83bc24c0000000007510a12000000040a320000000e9a70800008b44246c8944241085c0'),
    bytes.fromhex('74486b5c2404348d44245c01c389c231c031c9837a64007507418b42388b402083c23439d375ec49'),
    bytes.fromhex('752085c0791c250000c03f3d000040007510a12400000040a324000000e953080000a11829b7008b'),
    bytes.fromhex('4004894424146b442404348d7c245c01f88944241889fb8b733889f08b7c241429f8b95400000031'),
    bytes.fromhex('d2f7f189433c8a462583e01ffec80f94c00fb6c08943608a465283e001894368ba0100000089f1b8'),
    bytes.fromhex('806d2400ffd0d95c241c8b44241c89c2c1ea170fb6fa80fa76763785c07833ba640000000fbae01e'),
    bytes.fromhex('722a25ffff7f000d000080006bc064b99500000029f9ba01000000d3e201c2b99600000029f9d3ea'),
    bytes.fromhex('eb0231d2895340bf40ee140031d289f1ffd7894344ba0600000089f1ffd7894348ba0700000089f1'),
    bytes.fromhex('ffd789434cba0800000089f1ffd7894350ba0900000089f1ffd7894354ba0a00000089f1ffd78943'),
    bytes.fromhex('5883c334395c24180f8519ffffff89e9b820770c00ffd089c68944247489e9b850770c00ffd089c3'),
    bytes.fromhex('8944247889e9b880770c00ffd08944247c8d141e01d08984249000000029f3899c248c0000008b85'),
    bytes.fromhex('4c01000085c074100fb65056b83d00000080fa3c761eeb10a12800000040a328000000ba53000000'),
    bytes.fromhex('89d083fa637605b86300000069c0580200002df88e0000b92600000031d2f7f1ba4605000029c289'),
    bytes.fromhex('9424800000008b44246489442414837c2410000f848f0000000fbae0080f8385000000837c246008'),
    bytes.fromhex('757e8b1db476e50085db7574a1b876e50085c0746b8d44245c31c931d28d70388b685c85ed750289'),
    bytes.fromhex('f183786400741585d2740f8b7a083978407f0775073b6a24730289f24383c0348b7c240439fb72cd'),
    bytes.fromhex('85c9742c83792c0074268b42082b410883f8057e1b31c98d44245ce80c2e0000a13c01000040a33c'),
    bytes.fromhex('010000e915060000f6442414050f84f80200008d44245c31ed31d28378640074378378680075318d'),
    bytes.fromhex('7d01897c240485ed741e8d4dff8b5c8c406bfb348b704039b43c9c0000007d08895c8c4489cdebde'),
    bytes.fromhex('8954ac408b6c24048d4a0183c03439542408740489caebb331ff897c2410396c24100f8493020000'),
    bytes.fromhex('8b4424108b448440894424046bd03483bc14c4000000000f856d0200008bb414bc00000085f67423'),
    bytes.fromhex('8b8414a000000085c07e0c6bc00f398414a40000007d0c8b44246083e80783f80176386b4c240434'),
    bytes.fromhex('83bc0cb800000000743085f6752c8b940ca000000031c085d27e236bd20f39940ca40000007c1731'),
    bytes.fromhex('c0837c2460070f97c0eb0bbe01000000eb0231f631c0837c246c00740985f67509e9ec01000085f6'),
    bytes.fromhex('7407f644246401740b85c07417f6442464047510a13400000040a334000000e9c60100006b542404'),
    bytes.fromhex('348dbc1494000000897c24148b152c0000004289152c00000085f6741889fa8d44245ce8fc210000'),
    bytes.fromhex('85c00f8492010000e9a804000085c00f847a0100006b542470348d44245c01c231ff39c2740e8378'),
    bytes.fromhex('5c0075038d783883c034ebee6b442404348b9c049c0000002b5f08837f10597e2f89f8e8eaf5ffff'),
    bytes.fromhex('3d830300007e218b5424743b54247819c0403b54247819c9894c240883642408f08344240814eb0a'),
    bytes.fromhex('31c0c7442408040000008b15780000004289157800000085c0740d8b157c0000004289157c000000'),
    bytes.fromhex('8d530283fa047610a18000000040a380000000e9e200000085db781383f80119db81e350c3000081'),
    bytes.fromhex('c330750000eb1183f80119db81e3a861000081c310270000c744242c040000008b44245c89442430'),
    bytes.fromhex('a1b876e500894424346b442404348b840498000000894424388b47048944243cba050000008d4424'),
    bytes.fromhex('2ce8d8f4ffff89442404a18400000040a384000000395c2404732ba18800000040a38800000089f9'),
    bytes.fromhex('8b5424148d44245ce8e5f6ffff837c24680119c983c102be40000000eb0da18c00000040a38c0000'),
    bytes.fromhex('0031c98b54240809f25653ff74241c578d44246ce86bf5ffff83c410395c24047310e926030000a1'),
    bytes.fromhex('3000000040a330000000ff442410e963fdffff8b5c246c85db0f8506030000837c2460080f85fb02'),
    bytes.fromhex('00008b542464f7c2020100000f84eb0200008b8424900000004883f80f0f87da0200000fbae20872'),
    bytes.fromhex('10f6442464020f84c9020000e91301000083bc24a40000003b7ee683bc24f40000000074dca16000'),
    bytes.fromhex('000040a360000000ba40420f008d44245ce87ff6ffff8b157000000001d0730d8b15740000004289'),
    bytes.fromhex('1574000000a3700000008b9424840000008d44245ce853f6ffffb90a00000031d2f7f189c6ba0300'),
    bytes.fromhex('00008d44245ce840f5ffff89c7a16400000040a36400000039f77333a16800000040a3680000008d'),
    bytes.fromhex('8c24940000008d9424c80000008d44245ce89cf5ffff837c24680119db83c302ba43000000eb30a1'),
    bytes.fromhex('6c00000040a36c0000008d9424940000008d44245ce846f5ffff8d9424c80000008d44245ce836f5'),
    bytes.fromhex('ffffba0300000051568d8424d0000000508d8424a00000005089d98d44246ce8f8f3ffff83c41039'),
    bytes.fromhex('f70f82b6010000e9ddfeffff8bbc24bc00000085ff0f85a20100008b4c24708d8424c8000000ba01'),
    bytes.fromhex('00000031db39ca732083782c00741483782800740e85db74088b73083970087e0289c34283c034eb'),
    bytes.fromhex('dc85db0f84640100008b43082b84249c00000083f8fb0f8c51010000a15000000040a3500000008b'),
    bytes.fromhex('94248c000000b8a00f000085d27819b8e02e000074124ab80071020083fa0377078b04952c0f0000'),
    bytes.fromhex('8b942490000000be3200000083fa01741131c983fa070f9ec189ce4e83e6ba83c6648b8c24880000'),
    bytes.fromhex('00bde803000031d2f7f58944240489d00fafc131d2f7f58b6c24040fafe901e8bd6400000031d2f7'),
    bytes.fromhex('f589c189d00fafc631d2f7f50fafce01c88bb42480000000bde803000031d2f7f589c189d00fafc6'),
    bytes.fromhex('31d2f7f50fafce01c8b90a00000031d2f7f189c6ba020000008d44245ce871f3ffff89c2a1540000'),
    bytes.fromhex('0040a35400000039f2732ea15800000040a3580000008d8c249400000089da8d44245ce8d2f3ffff'),
    bytes.fromhex('837c24680119ff83c702ba42000000eb2ba15c00000040a35c0000008d9424940000008d44245ce8'),
    bytes.fromhex('7cf3ffff89da8d44245ce871f3ffffba020000005056538d8424a00000005089f98d44246ce83af2'),
    bytes.fromhex('ffff83c4108b44245c8d5801e9f7f5ffff837c240c0074098b44240ca3987fbd0081c40c0200005b'),
    bytes.fromhex('5e5f5dc3a10000000040a300000000b801000000e9e6f4ffffa10400000040a30400000031c0e9d4'),
    bytes.fromhex('f4ffff90b888000070110100a0860100d0fb0100f740200000c0bf750ef74024000000700f94c00f'),
    bytes.fromhex('b6c0c331c0c383ec1c89c1ba01000000b8806d2400ffd0d95c240c8b44240c85c0790231c083c41c'),
    bytes.fromhex('c389c2c1ea1780fa767637530fb6daba640000000fbae01e722b25ffff7f000d000080006bc064b9'),
    bytes.fromhex('9500000029d9ba01000000d3e201c2b99600000029d9d3eaeb0331c0c389d05bc3538b1d78c2e300'),
    bytes.fromhex('8b0c955c77e50085c974110fb7889c01000031d281f9ffff0000740a31d239d9730429cb89da2b90'),
    bytes.fromhex('2401000089d05bc35557565383ec2c8944241489542418894c241c31f631ed31ff31c08944240c89'),
    bytes.fromhex('4424108b4424140fb6801c01000039c6733a8b4424148b1cb085db742c807b35007526ff44241089'),
    bytes.fromhex('d8e8f6feffff85c07417ff44240c89d8e801ffffff39c5720485ff750489c589df46ebb78b442418'),
    bytes.fromhex('8b54240c89108b44241c89388b44244089288b44241083c42c5b5e5f5dc3530fb6981c01000031c9'),
    bytes.fromhex('39d97308391488740741ebf431c0eb05b8010000005bc35557565383ec1c89442408a11829b7008b'),
    bytes.fromhex('68388b403c89442404bb603c0e0029ebc1e30431f631c9890c248d456439c60f838900000039ee72'),
    bytes.fromhex('19f6430b03746f8b4308250000001c3d0000000c75608b0beb078b4424048b0cb085c97451807935'),
    bytes.fromhex('00754b833c2440744e8b3c24c1e7048b44240801c7890f31c039ee0f93c089470c89c8894c240ce8'),
    bytes.fromhex('22feffff894704506a006a016a0031d28b4c241cb840d42b00ffd0ff4424040fb7c08947085a4683'),
    bytes.fromhex('c310e973ffffffc70424410000008b042483c41c5b5e5f5dc35557565383ec1c8904248954240c89'),
    bytes.fromhex('4c241889d0c1e0048b342401f08944241489f231f68974240431c98b7c240c397c24040f84c00000'),
    bytes.fromhex('008b720c85f60f85a90000008b5a0881fbfeff00000f879a0000008b3a89f8e870fdffff85c00f84'),
    bytes.fromhex('89000000837c24300075118b44241883e80a39d87e7785c97524eb2a837c243001750cf647240f75'),
    bytes.fromhex('64807f253f765e85c974138b410839d8725339c375088b420439410473478d4301894424108b0424'),
    bytes.fromhex('31db895c240831ed85f674053b680473178b5c2410395808730e8b30897424088b6804be01000000'),
    bytes.fromhex('83c0108b5c241439d875d58b44240839c7750289d1ff44240483c210e932ffffff89c883c41c5b5e'),
    bytes.fromhex('5f5dc35557565381ec7c0400008944243889d5894c2414b8504c0c00ffd08944240c85c00f841004'),
    bytes.fromhex('00008b442414833c855c77e500007414833d3c01e60001740bff05c0000000e9ee0300008b44240c'),
    bytes.fromhex('80b81c010000410f87dd03000083ec0c8d442454508d4c24548d5424508b44241ce812fdffff83c4'),
    bytes.fromhex('1083f8020f87b803000031f6837c244400740b8b442448e875fcffff89c6837c2440010f868f0000'),
    bytes.fromhex('00f6842490040000200f848b030000a10000000085c0746d813836324952756569542414a4000000'),
    bytes.fromhex('8d4410408d58040fb60083f8147605b8140000008d14c339d30f84530300008b3b85ff750583c308'),
    bytes.fromhex('ebed807f350075f58954241089f8e8e3fbffffe801fcffff29f083f8028b5424107edaf643060175'),
    bytes.fromhex('218b4720c1e8163c0276caeb15ff05cc000000e90a030000c744241005000000eb08c74424100600'),
    bytes.fromhex('00008d442470e8ecfcffff89c383f840760bff05c8000000e9dd02000085ed750b8b4c240cb8003f'),
    bytes.fromhex('0c00ffd08b5424148b44240ce8d8fbffff89c183ec0c6a0089da8d842480000000e873fdffff83c4'),
    bytes.fromhex('1089c38b4c240cb820770c00ffd0894424208b4c240cb850770c00ffd0894424248b4c240cb88077'),
    bytes.fromhex('0c00ffd08944242831c0837c2410050f94c089442418ff4c241881642418b03cffff81442418a086'),
    bytes.fromhex('01008b4424248b7c242029f88944242c89f88b7c242401f88b7c242801f88944243085db0f841201'),
    bytes.fromhex('00008b4304e8f7faffff29f08944241c837c2410060f850a010000480f8e10020000ff05a8000000'),
    bytes.fromhex('8b3d987fbd0085ff740831d28915987fbd008b4c2444be40ee1400ba06000000894c243cffd68944'),
    bytes.fromhex('2434ba080000008b4c243cffd689c185ff7406893d987fbd00c744244c060000008b442414894424'),
    bytes.fromhex('50a1b876e500894424548b442420894424588b4424248944245c8b442428894424608b038b151829'),
    bytes.fromhex('b7002b4204bf5400000031d2f7f7894424648b44243489442468894c246cff05d0000000b8335242'),
    bytes.fromhex('5131d23344944c89c1c1e91031c869c06bcaeb8589c1c1e90d31c869c035aeb2c289c1c1e91031c8'),
    bytes.fromhex('4283fa0975d5b9a086010031d2f7f181fa4fc300007637ff05d400000031ede9f1000000837c2410'),
    bytes.fromhex('060f841301000031c08944241cff05a000000085db750fff05c400000031c931ede9cb00000085ed'),
    bytes.fromhex('7410ff05d8000000bd02000000e9b30000008b44240c80b81c010000357568ba3400000089c1b8a0'),
    bytes.fromhex('f92b00ffd0ff05dc0000008b4c240cb8003f0c00ffd08d442470e8a8faffff89c683f840772b8b54'),
    bytes.fromhex('24148b44240ce8aef9ffff89c183ec0c6a0089f28d842480000000e849fbffff83c41089c385c075'),
    bytes.fromhex('0eff05e000000031c985db7444eb3eff7424388b430840506a00ff742418b8b02b3200ffd089c585'),
    bytes.fromhex('c0741c837c241005750dff05a4000000bd01000000eb0eff05ac000000ebf1ff05e400000089e98b'),
    bytes.fromhex('2bff7424186a00ff7424246a00ff742440ff74244055ff7424608b5424308b442434e8942e000083'),
    bytes.fromhex('c42081c47c0400005b5e5f5dc35557565383ec208b7c24388b4424340fb6a81c01000031f631d231'),
    bytes.fromhex('db83fa07772f39eb732b8b4424348b049885c0741d39c77419807835007513668b482866c1e90a83'),
    bytes.fromhex('e10739f175048904944243ebcc4683fe0875c431c939ca74328b1c8c668b432880e4e3be001c0000'),
    bytes.fromhex('83f90577068d7101c1e60a09f06689432889d8e804f8ffff85c07504806352fc41ebca66816728ff'),
    bytes.fromhex('e3ff052c01000083c4205b5e5f5dc35557565381ec5c0400008944242089542428894c2418b8504c'),
    bytes.fromhex('0c00ffd08944240c85c00f84d6040000051c0100008944242c8b44240c80b81c010000410f87bc04'),
    bytes.fromhex('00008b442418833c855c77e50000740d833d3c01e600010f85a104000083ec0c8d442458508d4c24'),
    bytes.fromhex('588d5424548b44241ce82af8ffff894424248b4424548944244083c41085c00f8571040000837c24'),
    bytes.fromhex('1402761583bc247004000000750bff05f0000000e955040000ff05ec0000008d442450e897f8ffff'),
    bytes.fromhex('89c38b5424188b44240ce8a2f7ffff8944243883fb4077118d542450c1e30401d331c9894c2410eb'),
    bytes.fromhex('26ff05f8000000eb2f31c0837a0c00750f8b02e8ecf6ffff85c00f95c00fb6c00944241083c21039'),
    bytes.fromhex('da75de837c2410007527ff05f400000031c08944242031f631c08944241431ed31c08944241c8944'),
    bytes.fromhex('242431dbe959030000837c2420007429ff05fc00000031f631c08944241431ed31c08944241c8944'),
    bytes.fromhex('242431c0c744242002000000e96103000031c9894c241c894c242483bc2470040000000f95c2837c'),
    bytes.fromhex('2428000f95c084c20f849b0000008b4424148b7c241c29f883f8020f868800000031ff31ed31db8b'),
    bytes.fromhex('44242c0fb60039c7732b8b44240c8b34b885f67415807e3500750f89f0e834f6ffff85db740839c5'),
    bytes.fromhex('730489e889de4789c589f3ebca56566a016a0189da8b4c241cb800d92b00ffd05f5d89da8b44240c'),
    bytes.fromhex('e831f7ffff85c07415ff050401000031f631db895c241431ede91cffffffff44241cff0500010000'),
    bytes.fromhex('895c2424e94affffff837c24280074218b44240c80b81c010000357514ba3400000089c1b8a0f92b'),
    bytes.fromhex('00ffd0ff050801000031ff31d28954241431ed31db8b4c240cb8003f0c00ffd08d442450e8def6ff'),
    bytes.fromhex('ff89c683f840760bff05f8000000e9c90000008b5424188b44240ce8d9f5ffff89c183ec0c6a0089'),
    bytes.fromhex('f28d442460e877f7ffff83c41089c385c0742585ff740dff051c010000be02000000eb0aff050c01'),
    bytes.fromhex('00008b742410b8b02b3200e961010000837c242800746f83ec0c6a0131c989f28d442460e830f7ff'),
    bytes.fromhex('ff83c41089c385c0752383ec0c6a0231c989f28d442460e815f7ffff83c41089c385c07508ff0510'),
    bytes.fromhex('010000eb3785ff0f849a0000008b44240c80b81c01000034771cf6442428807415ff0520010000be'),
    bytes.fromhex('03000000b800000000e9eb000000ff052401000031f6e93f0100008b44240c8b0cb831c085c97411'),
    bytes.fromhex('31d2894c243cb8609f3b00ffd08b4c243c394424347c068b44243489f1478944243489ce8b44242c'),
    bytes.fromhex('0fb60039c772c485f60f848a000000ba0100000089f1b8609f3b00ffd045ff05140100008b4c240c'),
    bytes.fromhex('b8003f0c00ffd083fd0277658b5424188b44240ce8a0f4ffff83e80a3b43087f5031ff31f6c74424'),
    bytes.fromhex('34fa000000eba58b5424188b44240ce87df4ffff83e80a3b43087f348b44242c0fb61080fa327628'),
    bytes.fromhex('4a8b4c240cb8a0f92b00ffd0ff442414ff05180100008b4c240cb8003f0c00ffd0837c24140176b7'),
    bytes.fromhex('8b7c2410e92cfeffffffb424740400008b7b088d5701526a00ff742418ffd085c074418b138b4424'),
    bytes.fromhex('0ce8d8f4ffff85c0743283fe037508c74424100500000083bc247004000000750a8b442410894424'),
    bytes.fromhex('20eb17505052ff742418e8fcffffff83c410ebe5ff052801000083ec0c8d442458508d4c24588d54'),
    bytes.fromhex('24548b44241ce8f5f3ffff83c410837c2444007506ff053001000031c085db74098b43088b3b897c'),
    bytes.fromhex('2430837c24280119d283e22083c20750ff74242056ff742444ff74242455ff742448ff7424408b4c'),
    bytes.fromhex('24408b442438e8942e000083c42081c45c0400005b5e5f5dc35557565383ec1c8b6c243485ed7408'),
    bytes.fromhex('ff05e8000000eb06ff05b8000000a1000000003d5142524f7514a1040000003d4f4d76317508a108'),
    bytes.fromhex('00000048741385ed0f85bb000000ff0508000000e9b00000008b1d0c000000a1a476e50031ff85ed'),
    bytes.fromhex('751189dac1ea0331c983f8080f94c189cf21d789dac1ea068d48f983f9020f96c121d1884c240f0f'),
    bytes.fromhex('b6d185ed7510f6c308740b83f8087406ff05bc00000009fa745f833d1829b7000074568b15100000'),
    bytes.fromhex('0083e2018954240883f807750231db31f685ff75195050ff7424385589f189da8b442418e81efaff'),
    bytes.fromhex('ff83c410eb1d83ec0c5389f18b5424188b442440e822f5ffff83c410807c240f0075ca4683fe2075'),
    bytes.fromhex('c083c41c5b5e5f5dc3890d00000000c7042400000000e96c3832009c60fc6a00ff3500000000e8fc'),
    bytes.fromhex('ffffff83c408619de9118024009c60fce8fcfffffff6050c000000407507619de91ce02b00619de8'),
    bytes.fromhex('1ce02b009c60fc6a0155e8fcffffff83c408619dc381ec14010000e9b22b3200'),
    b'\xcc' * 560,
    bytes(512),
    bytes.fromhex('5557565383ec2489c389d783c0386b53143401c231f639d0741f83782c00741483782800750e85f6'),
    bytes.fromhex('74088b4e24394824730289c683c034ebdda13800000040a33800000085f67512a13c00000040a33c'),
    bytes.fromhex('00000031c0e94d0100008b4f082b4e08786183f9050f8f9d00000069c178ecffff890c248da8084c'),
    bytes.fromhex('0100c7442410010000008b0389442414a1b876e500894424188b46048944241c8b470489442420ba'),
    bytes.fromhex('050000008d442410e81a00000089c2a14000000040a34000000039ea8b0c247349eb05bda0860100'),
    bytes.fromhex('a14400000040a3440000008b4f24ba010000003b4e240f838900000089f289d8e80c2e0000a13401'),
    bytes.fromhex('000040a334010000ba01000000837b0c0119c983c102eb7031eda14800000040a3480000008b4624'),
    bytes.fromhex('3b4724734e83f9057f49837b04077406837b3400753d89c189fa89d8e80c2e000089fa89d8e82c02'),
    bytes.fromhex('000089f289d8e82c020000a13801000040a3380100008b530cb90100000085d2741631d2b9020000'),
    bytes.fromhex('00eb0d31d28b4b1085c9742c31c9eb0ba14c00000040a34c00000085d27505ba4100000055575689'),
    bytes.fromhex('4c240c89d8e81001000083c40c8b0c2431c085c90f95c083c4245b5e5f5dc3'),
    bytes(2657),
    bytes.fromhex('5557565383ec0889c38914248b4014894424048d533831ff397c240474448b4224391424740f39c8'),
    bytes.fromhex('72328b34243b4624732a40eb0639c1742389c8837b0c0075188b32668b6e286681e5ffe389c6c1e6'),
    bytes.fromhex('0a09f58b3266896e288942244783c234ebb6837b0c00740da19800000040a398000000eb0ba19000'),
    bytes.fromhex('000040a39000000083c4085b5e5f5dc35557565383ec28890424894c24048b6c243c8b7c24408b5c'),
    bytes.fromhex('244c8b0d000000008b351829b7008b7604a1b876e5006689442414a0b476e500884424168a042488'),
    bytes.fromhex('442417885424188a4424048844241983c8ff85ed740d89e829f0bd5400000031d2f7f5668944241a'),
    bytes.fromhex('83c8ff85ff740d89f829f0be5400000031d2f7f6668944241c8b4424448844241e8b442448884424'),
    bytes.fromhex('1f31c085db780d83c8ff81fbffff00007f0289d866894424208b442450884424228b442454884424'),
    bytes.fromhex('238b4424588944242489ca83e27f6bd21481c20000000031c08b5c8414891c824083f80575f34189'),
    bytes.fromhex('0d00000000ff059c00000083c4285b5e5f5dc3'),
    bytes(117),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0004, True, 'page', 0xf00),
    (0x000b, True, 'stock', 0x2be01c),
    (0x0013, True, 'page', 0xf15),
    (0x001a, True, 'stock', 0x27eb7c),
    (0x0126, False, 'page', 0x2e00),
    (0x013a, False, 'page', 0x2400),
    (0x0141, False, 'page', 0x2400),
    (0x01b6, False, 'page', 0x2e00),
    (0x01bb, False, 'page', 0x20dc),
    (0x01c1, False, 'page', 0x20dc),
    (0x024f, False, 'page', 0x20d4),
    (0x0255, False, 'page', 0x20d4),
    (0x0285, False, 'page', 0x20d8),
    (0x028b, False, 'page', 0x20d8),
    (0x02b8, False, 'page', 0x20d0),
    (0x02be, False, 'page', 0x20d0),
    (0x0401, False, 'page', 0x2000),
    (0x040f, False, 'page', 0x2004),
    (0x041d, False, 'page', 0x2008),
    (0x0425, False, 'page', 0x2048),
    (0x042b, False, 'page', 0x2048),
    (0x043c, False, 'page', 0x200c),
    (0x046f, False, 'page', 0x204c),
    (0x0475, False, 'page', 0x204c),
    (0x048c, False, 'page', 0x2010),
    (0x0499, False, 'page', 0x2014),
    (0x049e, False, 'page', 0x2018),
    (0x04ee, False, 'page', 0x2050),
    (0x04f4, False, 'page', 0x2050),
    (0x0508, False, 'page', 0x2054),
    (0x050e, False, 'page', 0x2054),
    (0x0532, False, 'page', 0x2058),
    (0x0538, False, 'page', 0x2058),
    (0x05bc, False, 'page', 0x205c),
    (0x05c2, False, 'page', 0x205c),
    (0x0627, False, 'page', 0x2060),
    (0x062d, False, 'page', 0x2060),
    (0x067b, False, 'page', 0x2064),
    (0x0681, False, 'page', 0x2064),
    (0x07e9, False, 'page', 0x2068),
    (0x07ef, False, 'page', 0x2068),
    (0x08b4, True, 'page', 0x2e0c),
    (0x08b9, False, 'page', 0x217c),
    (0x08bf, False, 'page', 0x217c),
    (0x09ed, False, 'page', 0x2074),
    (0x09f3, False, 'page', 0x2074),
    (0x0a0e, False, 'page', 0x206c),
    (0x0a15, False, 'page', 0x206c),
    (0x0a24, True, 'page', 0x21fc),
    (0x0aac, False, 'page', 0x20b8),
    (0x0ab3, False, 'page', 0x20b8),
    (0x0abd, False, 'page', 0x20bc),
    (0x0ac4, False, 'page', 0x20bc),
    (0x0ad1, False, 'page', 0x20c0),
    (0x0ad7, False, 'page', 0x20c0),
    (0x0b4b, False, 'page', 0x20c4),
    (0x0b51, False, 'page', 0x20c4),
    (0x0b5c, False, 'page', 0x20c8),
    (0x0b62, False, 'page', 0x20c8),
    (0x0b87, False, 'page', 0x20cc),
    (0x0b8d, False, 'page', 0x20cc),
    (0x0bb8, False, 'page', 0x2070),
    (0x0bbe, False, 'page', 0x2070),
    (0x0c2e, False, 'page', 0x20a0),
    (0x0c34, False, 'page', 0x20a0),
    (0x0c48, False, 'page', 0x20b0),
    (0x0c52, False, 'page', 0x20b4),
    (0x0c59, False, 'page', 0x20b4),
    (0x0c5e, False, 'page', 0x20b0),
    (0x0c8e, False, 'page', 0x20a4),
    (0x0c94, False, 'page', 0x20a4),
    (0x0c9d, False, 'page', 0x20a8),
    (0x0ca3, False, 'page', 0x20a8),
    (0x0cd0, False, 'page', 0x20ac),
    (0x0cd6, False, 'page', 0x20ac),
    (0x0d8d, False, 'page', 0x2090),
    (0x0d93, False, 'page', 0x2090),
    (0x0dbc, False, 'page', 0xf2c),
    (0x0e5d, False, 'page', 0x2094),
    (0x0e63, False, 'page', 0x2094),
    (0x0e6c, False, 'page', 0x2098),
    (0x0e72, False, 'page', 0x2098),
    (0x0e9a, False, 'page', 0x209c),
    (0x0ea0, False, 'page', 0x209c),
    (0x0f05, False, 'page', 0x2040),
    (0x0f0b, False, 'page', 0x2040),
    (0x0f1a, False, 'page', 0x2044),
    (0x0f20, False, 'page', 0x2044),
    (0x12b3, False, 'page', 0x2100),
    (0x1320, False, 'page', 0x2020),
    (0x1397, False, 'page', 0x210c),
    (0x13c4, False, 'page', 0x2108),
    (0x149c, False, 'page', 0x20e8),
    (0x1538, False, 'page', 0x2110),
    (0x1581, False, 'page', 0x2114),
    (0x159f, False, 'page', 0x20e0),
    (0x15a9, False, 'page', 0x2104),
    (0x15bc, False, 'page', 0x2118),
    (0x15e7, False, 'page', 0x211c),
    (0x1633, False, 'page', 0x2120),
    (0x1664, False, 'page', 0x20e4),
    (0x1671, False, 'page', 0x20ec),
    (0x1679, False, 'page', 0x2124),
    (0x16a3, True, 'page', 0x2e94),
    (0x174b, False, 'page', 0x216c),
    (0x17f8, False, 'page', 0x2130),
    (0x1803, False, 'page', 0x212c),
    (0x183b, False, 'page', 0x2138),
    (0x186c, False, 'page', 0x2134),
    (0x189a, False, 'page', 0x213c),
    (0x195b, False, 'page', 0x2144),
    (0x1974, False, 'page', 0x2140),
    (0x19a5, False, 'page', 0x2148),
    (0x19d2, False, 'page', 0x2138),
    (0x1a09, False, 'page', 0x215c),
    (0x1a16, False, 'page', 0x214c),
    (0x1a67, False, 'page', 0x2150),
    (0x1a8b, False, 'page', 0x2160),
    (0x1a95, False, 'page', 0x1dc5),
    (0x1aa0, False, 'page', 0x2164),
    (0x1b00, False, 'page', 0x2154),
    (0x1b6a, False, 'page', 0x2158),
    (0x1bdb, True, 'page', 0x16b1),
    (0x1be6, False, 'page', 0x2168),
    (0x1c0f, False, 'page', 0x2170),
    (0x1c4f, True, 'page', 0x2e94),
    (0x1c72, False, 'page', 0x2128),
    (0x1c7a, False, 'page', 0x20f8),
    (0x1c7f, False, 'page', 0x2000),
    (0x1c8b, False, 'page', 0x2004),
    (0x1c97, False, 'page', 0x2008),
    (0x1ca8, False, 'page', 0x2048),
    (0x1cb3, False, 'page', 0x200c),
    (0x1cfa, False, 'page', 0x20fc),
    (0x1d0d, False, 'page', 0x2010),
    (0x1d6b, False, 'page', 0x2e04),
    (0x1d72, False, 'page', 0x1d7b),
    (0x1d77, True, 'stock', 0x32386c),
    (0x1d82, False, 'page', 0x2e04),
    (0x1d87, True, 'page', 0x1c5d),
    (0x1d91, True, 'stock', 0x248011),
    (0x1d99, True, 'page', 0xf00),
    (0x1d9f, False, 'page', 0x200c),
    (0x1da9, True, 'stock', 0x2be01c),
    (0x1db0, True, 'stock', 0x2be01c),
    (0x1dbb, True, 'page', 0x1c5d),
    (0x1dcc, True, 'stock', 0x322bb2),
    (0x223a, False, 'page', 0x2078),
    (0x2240, False, 'page', 0x2078),
    (0x2249, False, 'page', 0x207c),
    (0x224f, False, 'page', 0x207c),
    (0x22a9, True, 'page', 0x1a),
    (0x22b0, False, 'page', 0x2080),
    (0x22b6, False, 'page', 0x2080),
    (0x22c9, False, 'page', 0x2084),
    (0x22cf, False, 'page', 0x2084),
    (0x22e9, True, 'page', 0x2e0c),
    (0x22ee, False, 'page', 0x2174),
    (0x22f4, False, 'page', 0x2174),
    (0x230b, False, 'page', 0x2088),
    (0x2311, False, 'page', 0x2088),
    (0x2335, True, 'page', 0x2e0c),
    (0x233e, True, 'page', 0x22c),
    (0x2347, True, 'page', 0x22c),
    (0x234c, False, 'page', 0x2178),
    (0x2352, False, 'page', 0x2178),
    (0x2379, False, 'page', 0x208c),
    (0x237f, False, 'page', 0x208c),
    (0x2396, True, 'page', 0x110),
    (0x2e79, False, 'page', 0x20d8),
    (0x2e7f, False, 'page', 0x20d8),
    (0x2e86, False, 'page', 0x20d0),
    (0x2e8c, False, 'page', 0x20d0),
    (0x2eb4, False, 'page', 0x2e00),
    (0x2f63, False, 'page', 0x2400),
    (0x2f79, False, 'page', 0x2e00),
    (0x2f7f, False, 'page', 0x20dc),
)

LABELS = {
    'emergency_pass': 0x1c61,
    'floor_seat': 0x16b5,
    'opening_entry': 0x0,
    'opening_pass': 0xf04,
    'pregame_entry': 0x1d95,
    'room_entry': 0xf,
    'room_pass': 0xf19,
    'sign_after': 0x1d7b,
    'sign_entry': 0x1d69,
    'sign_ungated': 0x1dc5,
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
    'd1_held': 0x2174,
    'd1_promoted': 0x2178,
    'season_resets': 0x217c,
}

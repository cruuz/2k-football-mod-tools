"""FROZEN previous revision of nfl2k5_qb_room_code: the floor + D1 + D2 hand-over template (b81 qb34, pinned at
b2672e398, file SHA-256 c7067bacabf4...). Never regenerate or edit: nfl2k5_qb_room recognizes pages written with it
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

STAGE_D1, STAGE_D2D3, STAGE_D4, STAGE_SIGN, STAGE_TRADE, STAGE_E2 = 1, 2, 4, 8, 16, 32
STAGE_D2 = STAGE_D2D3                # D2 alone since the review (DESIGN addendum 2, R5); the old name is kept
STAGE_D3 = 256                       # D3 and the season reset (R1), on their own bit (R5)
STAGE_FLOOR = 64                     # the floor (DESIGN addendum F3): a club with no healthy quarterback gets one
STAGE_OVER_CAP = 128                 # retired (floor review F1): the page ignores it; the Studio set drops it
STAGE_MASK = 511                     # 16 (trades, 4b) is not built: the page ignores it; 32 counts only with 8.
FLAG_SHADOW = 1
H0_PPM = 27000                       # D3 base 0.0270 in millionths: shadow panel P0's value, P1 ran at it (review F5).
D2_SCALE_MILLI = 1000                # D2 table scale in thousandths (1000 = the table as written).
LIMIT_PPM = 1_000_000                # Both are clamped to this in the page (a probability is at most 1).

DECISION_D1, DECISION_D2, DECISION_D3, DECISION_D4, DECISION_E1, DECISION_E2, DECISION_FLOOR = 1, 2, 3, 4, 5, 6, 7
RESULT_KEPT, RESULT_APPLIED, RESULT_SHADOW, RESULT_LOCK_ONLY, RESULT_OVER_CAP = 0, 1, 2, 3, 5
RESULT_NO_FIT = 6                    # the floor's named failure: no free agent fits after every restructure and release
FLOOR_LOST_SINCE = 0x10              # floor ring decision bit: the club had a healthy QB earlier in this advance
SEEN_HEALTHY_SLOT = 0x2E08           # RAM only (zero in the file): clubs seen with a healthy QB this advance (bit = club)

# (site, retail bytes, entry label, stage bits any of which needs the site; 0 = always). Whole 5-byte calls.
# 0x247DCA enters pregame_entry: opening_pass, then with bit 64 clear `jmp 0x2BE020` exactly as opening_entry (still in
# the template, piece 3's bytes) did; with bit 64 set it calls 0x2BE020, runs the floor and returns to 0x247DCF.
# 0x24807A enters end_entry (floor review F2): room_pass as room_entry did, then 0x27EB80, then with bit 64 the floor
# at the end of the weekly advance. 0x248687 (the stage advance's `call 0x27EDF0`, with bit 64) enters stage_entry: the
# floor after both camp cuts to 53 and every stage change (qb34/evidence/floor/F2-hook-points.md).
HOOKS = (
    (0x247DCA, bytes.fromhex("e851620700"), "pregame_entry", 0),
    (0x24807A, bytes.fromhex("e8016b0300"), "end_entry", 0),
    (0x248010, bytes.fromhex("e85bb80d00"), "sign_entry", STAGE_SIGN | STAGE_FLOOR),
    (0x248687, bytes.fromhex("e864670300"), "stage_entry", STAGE_FLOOR),
)
# Retired with the over-cap rung (floor review F1): the page no longer enters the native signing past its gates.
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
CODE_BYTES = 0x1ee7
PIECE3_BYTES = 0xf10             # piece 3's main part (the entries, room.c's code and tables)
CODE_TAIL = (0x2e10, 0x1d7)             # (page offset, bytes): the second code piece
CODE_MID = (0x2200, 0x1af)              # (page offset, bytes): the third piece
CODE_RESERVED = (0x2200, 0x2400)        # the middle piece's range

_TEMPLATE = b''.join((
    bytes.fromhex('9c60fce8fcffffff619de91ce02b009c60fce8fcffffff619de97ceb27005389d189c28d0c88b833'),
    bytes.fromhex('524251330289c3c1eb1031d869c06bcaeb8589c3c1eb0d31d869c035aeb2c289c3c1eb1031d883c2'),
    bytes.fromhex('0439d175d6b9a086010031d2f7f189d05bc38b502081e20000c0bf750f8b4024a9000000700f94c0'),
    bytes.fromhex('0fb6c0c331c0c356538b581085db0f8ea000000089c6694018fa00000099f7fb8d8812fdffff81f9'),
    bytes.fromhex('470900007e07b947090000eb0685c9790231c96946148813000099f7fb2ddc0500003d470900007e'),
    bytes.fromhex('07b847090000eb0685c0790231c001c169461c204e000099f7fb3d470900007e07b847090000eb06'),
    bytes.fromhex('85c0790231c001c1694620a861000099f7fbba4709000029c281fa470900007e07ba47090000eb06'),
    bytes.fromhex('85d2790231d28d441103b90600000099f7f9eb0231c05b5ec3555756535389c689142489ca8b7c24'),
    bytes.fromhex('1c8b2d0000000089e883e07f8b0db876e5006bc0148d980000000066898800000000a1b476e50088'),
    bytes.fromhex('43028b06884303837e04070f94c0c1e0050b04248843048853058b4424188b4004668943068b4704'),
    bytes.fromhex('668943088b463088430a8b463488430b8d4638e8d7feffff6689430c8b47088b7c24182b47088843'),
    bytes.fromhex('0e8b4624b90a00000031d2f7f188430f8b4424208943108d4501a300000000a19c00000040a39c00'),
    bytes.fromhex('00005e5b5e5f5dc383ec348914248b10895424048b15b876e500895424088b50188954240c8b501c'),
    bytes.fromhex('895424108b5020895424148b503c895424188b50488b484c8954241c894c24208b50508b48548954'),
    bytes.fromhex('2424894c24288b40588944242cba0c00000089e0e8d5fdffff83c434c3837a30007523c742300100'),
    bytes.fromhex('000083780c0075168b128a425283c801884252a19400000040a394000000c3565389c689d38b4224'),
    bytes.fromhex('8b512489532489412489da89f0e8bbffffff89ca89f0e8b2ffffff837e0c00740da19800000040a3'),
    bytes.fromhex('98000000eb318b13668b42288b09668b592831d86625001c668b592831c366895928668b4a2831c8'),
    bytes.fromhex('66894228a19000000040a3900000005b5ec35557565383ec0889c589d783c038e88afdffff8b5540'),
    bytes.fromhex('2b5574b9a00000003d890200007e29b9820000003ded0200007e1db9640000003d510300007e1131'),
    bytes.fromhex('c93db50300000f9ec14983e1df83c12d8b4530be0a00000085c0781cbe32000000741583f8040f9f'),
    bytes.fromhex('c00fb6c089c64e83e6ba81c6aa00000031c0837d34030f9fc0890424ff0c24832424d883042464bb'),
    bytes.fromhex('9600000083fa057e19bb6400000083fa0a7e0f31db83fa0f0f9ec34b83e3dd83c33289f8bf640000'),
    bytes.fromhex('0031d2f7f78944240489d00fafc131d2f7f78b7c24040faff901f8bf6400000031d2f7f789c189d0'),
    bytes.fromhex('0fafc631d2f7f70fafce01c831d2f7f789c18b04240fafc231d2f7f78b34240fafce01c831d2f7f7'),
    bytes.fromhex('89c189d00fafc331d2f7f70fafcb01c88b5d24bee803000031d2f7f689c189d00fafc331d2f7f60f'),
    bytes.fromhex('afcb01c883c4085b5e5f5dc38b150000000081fa5142524f75178b150400000081fa4f4d76317509'),
    bytes.fromhex('8b15080000004a740ca10800000040a308000000c35557565381ec0c0200008b150c000000895424'),
    bytes.fromhex('648944246c81e2070100000f845a0a0000a1a476e5008944246083e80783f8027610a10c00000040'),
    bytes.fromhex('a30c000000e9390a0000a11829b70085c00f842c0a0000a11000000083e001894424688b15140000'),
    bytes.fromhex('00a11800000081fa40420f007605ba40420f00899424840000003d40420f007605b840420f008984'),
    bytes.fromhex('2488000000a1987fbd008944240c85c0740831ed892d987fbd0031db895c245c83fb1f0f87ba0900'),
    bytes.fromhex('00a11000000040a31000000089d9b8504c0c00ffd08944240485c07510a11400000040a314000000'),
    bytes.fromhex('e98209000081c3d75d39008b049d0000000085c07419a14001e60085c07510a11800000040a31800'),
    bytes.fromhex('0000e9580900008b44246c8944240885c07426837c246008751fa1b476e50085c07516a1b876e500'),
    bytes.fromhex('85c0740d8b5424048d44245ce8942e00008b4424040fb6801c0100003c41760231c08b7424048d04'),
    bytes.fromhex('868944241089f231db31c0bf010000003954241074378b3285f6742c8a4e3584c97525668b4e2866'),
    bytes.fromhex('c1e90a83e10783fb07742d89fdd3e585c5752509e8436bc93489b40c9400000083c204ebc383fb01'),
    bytes.fromhex('760eba0100000088d9d3e24a39d07410a11c00000040a31c000000e99f080000895c24708d4c245c'),
    bytes.fromhex('31f689715c8b4138e83dfaffff894164897424184683c13439f375e683bc24c0000000007510a120'),
    bytes.fromhex('00000040a320000000e961080000837c24080074466bde348d44245c01c389c231c031c9837a6400'),
    bytes.fromhex('7507418b42388b402083c23439d375ec49752085c0791c250000c03f3d000040007510a124000000'),
    bytes.fromhex('40a324000000e914080000a11829b7008b4004894424106bc6348d7c245c01f88944241489fb8b7b'),
    bytes.fromhex('3889f88b4c241029c8b95400000031d2f7f189433c8a472583e01ffec80f94c00fb6c08943608a47'),
    bytes.fromhex('5283e001894368ba0100000089f9b8806d2400ffd0d95c241c8b44241c89c2c1ea170fb6ea85c078'),
    bytes.fromhex('3883fd767633ba640000000fbae01e722a25ffff7f000d000080006bc064b99500000029e9ba0100'),
    bytes.fromhex('0000d3e201c2b99600000029e9d3eaeb0231d2895340bd40ee140031d289f9ffd5894344ba060000'),
    bytes.fromhex('0089f9ffd5894348ba0700000089f9ffd589434cba0800000089f9ffd5894350ba0900000089f9ff'),
    bytes.fromhex('d5894354ba0a00000089f9ffd589435883c334395c24140f8519ffffff8b4c2404b820770c00ffd0'),
    bytes.fromhex('89c7894424748b4c2404b850770c00ffd089c3894424788b4c2404b880770c00ffd08944247c8d14'),
    bytes.fromhex('1f01d08984249000000029fb899c248c0000008b4424048b804c01000085c074100fb65056b83d00'),
    bytes.fromhex('000080fa3c761eeb10a12800000040a328000000ba5300000089d083fa637605b86300000069c058'),
    bytes.fromhex('0200002df88e0000b92600000031d2f7f1ba4605000029c289942480000000837c2408000f848d00'),
    bytes.fromhex('0000837c2460080f85820000008b1db476e50085db7578a1b876e50085c0746f8d44245c31c931d2'),
    bytes.fromhex('8d78388b685c896c240485ed750289f983786400741985d274138b6a083968407f0b750b8b6c2404'),
    bytes.fromhex('3b6a24730289fa4383c03439f372c985c9742c83792c0074268b42082b410883f8057e1b31c98d44'),
    bytes.fromhex('245ce80c2e0000a13c01000040a33c010000e9d8050000f6442464050f84f80200008d44245c31ed'),
    bytes.fromhex('31d28378640074378378680075318d75018974240485ed741e8d4dff8b5c8c406bfb348b704039b4'),
    bytes.fromhex('3c9c0000007d08895c8c4489cdebde8954ac408b6c24048d4a0183c03439542418740489caebb331'),
    bytes.fromhex('ff897c2410396c24100f84930200008b4424108b448440894424046bd03483bc14c4000000000f85'),
    bytes.fromhex('6d0200008bb414bc00000085f674238b8414a000000085c07e0c6bc00f398414a40000007d0c8b44'),
    bytes.fromhex('246083e80783f80176386b4c24043483bc0cb800000000743085f6752c8b940ca000000031c085d2'),
    bytes.fromhex('7e236bd20f39940ca40000007c1731c0837c2460070f97c0eb0bbe01000000eb0231f631c0837c24'),
    bytes.fromhex('6c00740985f67509e9ec01000085f67407f644246401740b85c07417f6442464047510a134000000'),
    bytes.fromhex('40a334000000e9c60100006b542404348dbc1494000000897c24148b152c0000004289152c000000'),
    bytes.fromhex('85f6741889fa8d44245ce8fc21000085c00f8492010000e96b04000085c00f847a0100006b542470'),
    bytes.fromhex('348d44245c01c231ff39c2740e83785c0075038d783883c034ebee6b442404348b9c049c0000002b'),
    bytes.fromhex('5f08837f10597e2f89f8e8f8f5ffff3d830300007e218b5424743b54247819c0403b54247819c989'),
    bytes.fromhex('4c240883642408f08344240814eb0a31c0c7442408040000008b15780000004289157800000085c0'),
    bytes.fromhex('740d8b157c0000004289157c0000008d530283fa047610a18000000040a380000000e9e200000085'),
    bytes.fromhex('db781383f80119db81e350c3000081c330750000eb1183f80119db81e3a861000081c310270000c7'),
    bytes.fromhex('44242c040000008b44245c89442430a1b876e500894424346b442404348b84049800000089442438'),
    bytes.fromhex('8b47048944243cba050000008d44242ce8c9f4ffff89442404a18400000040a384000000395c2404'),
    bytes.fromhex('732ba18800000040a38800000089f98b5424148d44245ce8f3f6ffff837c24680119c983c102be40'),
    bytes.fromhex('000000eb0da18c00000040a38c00000031c98b54240809f25653ff74241c578d44246ce879f5ffff'),
    bytes.fromhex('83c410395c24047310e9e9020000a13000000040a330000000ff442410e963fdffff8b74246c85f6'),
    bytes.fromhex('0f85c9020000837c2460080f85be0200008b542464f7c2020100000f84ae0200008b842490000000'),
    bytes.fromhex('4883f80f0f879d0200000fbae2087210f6442464020f848c020000e9f300000083bc24a40000003b'),
    bytes.fromhex('7ee683bc24f40000000074dca16000000040a360000000ba40420f008d44245ce88df6ffff8b1570'),
    bytes.fromhex('00000001d0730d8b157400000042891574000000a3700000008b9424840000008d44245ce861f6ff'),
    bytes.fromhex('ffb90a00000031d2f7f189c3ba030000008d44245ce84ef5ffff89c7a16400000040a36400000039'),
    bytes.fromhex('df7333a16800000040a3680000008d8c24940000008d9424c80000008d44245ce8aaf5ffff837c24'),
    bytes.fromhex('680119f683c602ba43000000eb10a16c00000040a36c000000ba0300000051538d8424d000000050'),
    bytes.fromhex('8d8424a00000005089f18d44246ce826f4ffff83c41039df0f8299010000e9fdfeffff8bbc24bc00'),
    bytes.fromhex('000085ff0f85850100008b4c24708d8424c8000000ba0100000031f639ca732083782c0074148378'),
    bytes.fromhex('2800740e85f674088b5e083958087e0289c64283c034ebdc85f60f84470100008b46082b84249c00'),
    bytes.fromhex('000083f8fb0f8c34010000a15000000040a3500000008b94248c000000b8a00f000085d27819b8e0'),
    bytes.fromhex('2e000074124ab80071020083fa0377078b0495000f00008b942490000000bb3200000083fa01740f'),
    bytes.fromhex('31db83fa070f9ec34b83e3ba83c3648b8c2488000000bde803000031d2f7f58944240489d00fafc1'),
    bytes.fromhex('31d2f7f58b6c24040fafe901e8bd6400000031d2f7f589c189d00fafc331d2f7f50fafcb01c88b9c'),
    bytes.fromhex('2480000000bde803000031d2f7f589c189d00fafc331d2f7f50fafcb01c8b90a00000031d2f7f189'),
    bytes.fromhex('c3ba020000008d44245ce8a1f3ffff89c2a15400000040a35400000039da732ea15800000040a358'),
    bytes.fromhex('0000008d8c249400000089f28d44245ce802f4ffff837c24680119ff83c702ba42000000eb10a15c'),
    bytes.fromhex('00000040a35c000000ba020000005053568d8424a00000005089f98d44246ce885f2ffff83c4108b'),
    bytes.fromhex('44245c8d5801e939f6ffff837c240c0074098b44240ca3987fbd0081c40c0200005b5e5f5dc3a100'),
    bytes.fromhex('00000040a300000000b801000000e931f5ffffa10400000040a30400000031c0e91ff5ffff669090'),
    bytes.fromhex('b888000070110100a0860100d0fb0100f740200000c0bf750ef74024000000700f94c00fb6c0c331'),
    bytes.fromhex('c0c383ec1c89c1ba01000000b8806d2400ffd0d95c240c8b44240c85c0790231c083c41cc389c2c1'),
    bytes.fromhex('ea1780fa767637530fb6daba640000000fbae01e722b25ffff7f000d000080006bc064b995000000'),
    bytes.fromhex('29d9ba01000000d3e201c2b99600000029d9d3eaeb0331c0c389d05bc3538b1d78c2e3008b0c955c'),
    bytes.fromhex('77e50085c974110fb7889c01000031d281f9ffff0000740a31d239d9730429cb89da2b9024010000'),
    bytes.fromhex('89d05bc35557565383ec2c8944241489542418894c241c31f631ed31ff31c08944240c894424108b'),
    bytes.fromhex('4424140fb6801c01000039c6733a8b4424148b1cb085db742c807b35007526ff44241089d8e8f6fe'),
    bytes.fromhex('ffff85c07417ff44240c89d8e801ffffff39c5720485ff750489c589df46ebb78b4424188b54240c'),
    bytes.fromhex('89108b44241c89388b44244089288b44241083c42c5b5e5f5dc3530fb6981c01000031c939d97308'),
    bytes.fromhex('391488740741ebf431c0eb05b8010000005bc35557565383ec2c89c689542418a11829b7008b7838'),
    bytes.fromhex('8b403c89442414bb603c0e0029fbc1e30431ed31c9894c240c8d476439c50f839c00000039fd721d'),
    bytes.fromhex('f6430b030f84850000008b4308250000001c3d0000000c75768b0beb078b4424148b0ca885c97467'),
    bytes.fromhex('80793500756189c8894c241ce839feffff89442410837c240c008b4c241c7405394604733a506a00'),
    bytes.fromhex('6a016a0031d2894c242cb840d42b00ffd00fb7c05a8b54241839d073228b4c241c890e8b54241089'),
    bytes.fromhex('560489460831c039fd0f93c089460cc744240c010000004583c310e959ffffff8b44240c83c42c5b'),
    bytes.fromhex('5e5f5dc383fa0a7e475383ec0889c3b8ffff000081fa090001007f0e8d42f6eb09837b0c0074148b'),
    bytes.fromhex('430889c289d8e8f0feffff85c075ea31c0eb108b03e876fdffff85c074e1b80100000083c4085bc3'),
    bytes.fromhex('31c0c353a11829b7008b48388b583c31d239ca74198b049385c0740f807835007509e841fdffff85'),
    bytes.fromhex('c0750742ebe331c0eb05b8010000005bc35557565383ec4c89c68954240c8d7c241eb91100000031'),
    bytes.fromhex('c0f3aa8d7c242fb911000000f3aa0fb6861c010000894424048b44240439c173268b048e0fb65035'),
    bytes.fromhex('83fa10771783fa0a7505ba0b000000fe44141ee8d8fcffff0044142f41ebd231ed31c089042431db'),
    bytes.fromhex('8b44240439c50f839c0000008b3cae0fb6573583fa10772883fa0a7505ba0b00000089f8e89ffcff'),
    bytes.fromhex('ff894424088a82281e0000837c240800740d3a44142f720d8b042489dfeb563a44141eebf1837c24'),
    bytes.fromhex('0c007534506a006a016a0031d289f9b840d42b00ffd089c25831c0837c2408000f94c0c1e0100fb7'),
    bytes.fromhex('d209d085db741e8b0c2439c87217ebb8f647240f74b289f9b880630e00ffd085c075b9eba3458904'),
    bytes.fromhex('2489fbe958ffffff85db742350506a016a0189da89f1b800d92b00ffd05a5989da89f0e84afdffff'),
    bytes.fromhex('31db85c00f94c389d883c44c5b5e5f5dc35557565383ec1089442408a1a476e50089442404a1b076'),
    bytes.fromhex('e5008944240cbb407ce50031c931ed803b0075680fb67b018a43028844240309f80a4303745631d2'),
    bytes.fromhex('837c240408751689c8be1100000031d2f7f68b74240c31d239f00f92c2668bb4095479e50009d589'),
    bytes.fromhex('f80fb6f88b44240839c7750a85d2753989f084c075330fb67c24038b44240839c7750989f00fb6c4'),
    bytes.fromhex('09d0751d4183c30881f976010000758783f50131c0837c2404080f94c021e8eb05b80100000083c4'),
    bytes.fromhex('105b5e5f5dc35557565383ec208b7c24388b4424340fb6a81c01000031f631d231db83fa07772f39'),
    bytes.fromhex('eb732b8b4424348b049885c0741d39c77419807835007513668b482866c1e90a83e10739f1750489'),
    bytes.fromhex('04944243ebcc4683fe0875c431c939ca74328b1c8c668b432880e4e3be001c000083f90577068d71'),
    bytes.fromhex('01c1e60a09f06689432889d8e8affaffff85c07504806352fc41ebca66816728ffe3ff052c010000'),
    bytes.fromhex('83c4205b5e5f5dc35557565381ec9c00000083bc24b4000000017514ff05e80000008b8424b00000'),
    bytes.fromhex('00a300000000eb1883bc24b4000000007508ff05b8000000eb06ff0550010000a1000000003d5142'),
    bytes.fromhex('524f7514a1040000003d4f4d76317508a10800000048741983bc24b4000000000f852c090000ff05'),
    bytes.fromhex('08000000e921090000a10c00000089442414a1a476e50031c9894c242483bc24b40000000075158b'),
    bytes.fromhex('542414c1ea0331c983f8080f94c121d1894c24248d50f983fa020f96c18b542414c1ea0688cb21d3'),
    bytes.fromhex('885c243f0fb6d383bc24b4000000007512f644241408740b83f8087406ff05bc0000000b5424240f'),
    bytes.fromhex('84ad080000833d1829b700000f84a00800008b151000000083e2018954242883bc24b40000000175'),
    bytes.fromhex('0831d289150000000083f807750631c089442414837c2414000f9544243e807c243e0119c0894424'),
    bytes.fromhex('3483642434208344243407c74424205c77e50031c089442410837c242400751c8b4c2410b8504c0c'),
    bytes.fromhex('00ffd08944240c85c00f85eb030000e9120800008b4c2410b8504c0c00ffd08944240c85c00f84bf'),
    bytes.fromhex('0300008b4424208338007414833d3c01e60001740bff05c0000000e9a20300008b44240c80b81c01'),
    bytes.fromhex('0000410f879103000083ec0c8d442464508d4c24648d5424608b44241ce87af9ffff83c41083f802'),
    bytes.fromhex('0f876c03000031f6837c245400740b8b442458e8ddf8ffff89c6837c2450010f8684000000f64424'),
    bytes.fromhex('14200f8442030000a10000000085c07465813836324952755d69542410a40000008d4410408d5804'),
    bytes.fromhex('0fb60083f8147605b8140000008d2cc339eb0f840a0300008b3b85ff750583c308ebed807f350075'),
    bytes.fromhex('f589f8e852f8ffffe870f8ffff29f083f8027ee2f6430601751e8b4720c1e8163c0276d2eb12ff05'),
    bytes.fromhex('cc000000e9c9020000bd05000000eb05bd06000000837c242800750b8b4c240cb8003f0c00ffd08b'),
    bytes.fromhex('5424108b44240ce869f8ffff89c28d44245ce825faffff31db85c074048d5c245c8b4c240cb82077'),
    bytes.fromhex('0c00ffd08944242c8b4c240cb850770c00ffd0894424308b4c240cb880770c00ffd08944243831c0'),
    bytes.fromhex('83fd050f94c089442418ff4c241881642418b03cffff81442418a08601008b4424308b7c242c29f8'),
    bytes.fromhex('8944244089f88b7c243001f88b7c243801f88944244485db0f841b0100008b4304e88ff7ffff29f0'),
    bytes.fromhex('8944241c83fd060f8513010000480f8ef6010000ff05a80000008b3d987fbd0085ff740731c0a398'),
    bytes.fromhex('7fbd008b4c2454be40ee1400ba06000000894c244cffd689442448ba080000008b4c244cffd689c1'),
    bytes.fromhex('85ff7406893d987fbd00c744246c060000008b44241089442470a1b876e500894424748b44242c89'),
    bytes.fromhex('4424788b4424308944247c8b442438898424800000008b038b151829b7002b4204bf5400000031d2'),
    bytes.fromhex('f7f7898424840000008b44244889842488000000898c248c000000ff05d0000000b83352425131d2'),
    bytes.fromhex('3344946c89c1c1e91031c869c06bcaeb8589c1c1e90d31c869c035aeb2c289c1c1e91031c84283fa'),
    bytes.fromhex('0975d5b9a086010031d2f7f181fa4fc300007635ff05d400000031c9e9d000000083fd060f84f000'),
    bytes.fromhex('000031c08944241cff05a000000085db750fff05c400000031c931c0e9aa000000837c2428007410'),
    bytes.fromhex('ff05d8000000b902000000e9910000008b44240c80b81c010000357545ba3400000089c1b8a0f92b'),
    bytes.fromhex('00ffd0ff05dc0000008b4c240cb8003f0c00ffd08b5424108b44240ce84cf6ffff89c28d44245ce8'),
    bytes.fromhex('08f8ffff85c0750aff05e000000031c9eb41ffb424b00000008b430840506a00ff742418b8b02b32'),
    bytes.fromhex('00ffd089c185c0741a83fd05750dff05a4000000b901000000eb0eff05ac000000ebf1ff05e40000'),
    bytes.fromhex('008b03ff7424186a00ff7424246a00ff742454ff74245450ff74247089ea8b442430e8f02e000083'),
    bytes.fromhex('c420807c243f000f8431040000e9fefbffff8b44240c051c010000894424388b44240c80b81c0100'),
    bytes.fromhex('00410f870e0400008b442420833800740d833d3c01e600010f85f8030000bb010000008a4c2410d3'),
    bytes.fromhex('e383ec0c8d442468508d4c24688d5424648b44241ce89af5ffff894424408b4424648944243c83c4'),
    bytes.fromhex('1085c0740b091d00000000e9b6030000837c24140074188b442410e8c1f8ffff85c0750bff055401'),
    bytes.fromhex('0000e99703000031c0231d000000000f95c0c1e00489442444ff05ec00000085db7406ff05480100'),
    bytes.fromhex('008b5424108b44240ce8f7f4ffff89442440e804f7ffff8944241c85c07517ff05f400000031ff31'),
    bytes.fromhex('db31ed31c089442418e98d000000837c2428000f8489000000ff05fc00000031c089442418894424'),
    bytes.fromhex('1c31db31ed31c9bf0200000031f6e9d10200008b44240c8b34b885f60f8484000000807e3500757e'),
    bytes.fromhex('89f0e81bf4ffff39c5726f4789c589f38b4424380fb60039c772d056566a016a0189da8b4c241cb8'),
    bytes.fromhex('00d92b00ffd05f5d89da8b44240ce817f5ffff85c07445ff050401000031ff31db31ed31f6e93802'),
    bytes.fromhex('000031c9894c2418894c241c8b4424308b74241829f083f8017629807c243e00742231ff31ed31db'),
    bytes.fromhex('eb9685db748d89e889deeb87ff442418ff0500010000895c241cebc8837c241400741e8b44240c80'),
    bytes.fromhex('b81c01000035751131d2e82af6ffff85c07406ff050801000031db31ed8b4c240cb8003f0c00ffd0'),
    bytes.fromhex('8b5424108b44240ce8b8f3ffff89c28d44246ce874f5ffff89c685c00f85bb000000837c24140075'),
    bytes.fromhex('0dff052401000031ffe98c01000083fd02776631ffc7442430fa0000008b4424380fb60039c77333'),
    bytes.fromhex('8b44240c8b0cb831c085c9741131d2894c2448b8609f3b00ffd08b4c2448394424307c068b442430'),
    bytes.fromhex('89f1478944243089ceebc285f6741aba0100000089f1b8609f3b00ffd045ff0514010000e954ffff'),
    bytes.fromhex('ffba010000008b44240ce862f5ffff85c0741a8d430185db7406ff0544010000ff051801000089c3'),
    bytes.fromhex('e928ffffffff0540010000bf06000000e9a6feffff89e809d87408ff051c010000eb06ff050c0100'),
    bytes.fromhex('008b7c2474ffb424b00000008d4701506a00ff742418b8b02b3200ffd085c00f84a10000008b7424'),
    bytes.fromhex('6c89f28b44240ce866f3ffff85c00f848a0000008d4709b90a00000031d2f7f16689460a8a462483'),
    bytes.fromhex('e0f083c8018846248a462783e0f083c801884627c64626028b4c240cb8003f0c00ffd08b5424108b'),
    bytes.fromhex('44240ce855f2ffff85c07906ff052001000083bc24b4000000007507bf01000000eb338b44242083'),
    bytes.fromhex('38007409833d4001e600007411525256ff742418e8fcffffff83c410ebd6ff054c010000ebceff05'),
    bytes.fromhex('2801000031ff8d74246c83ec0c8d442468508d4c24688d5424648b44241ce821f2ffff83c410837c'),
    bytes.fromhex('2454007506ff053001000031c985f674038b4e0889e809d883f80119c083c00285f674068b368974'),
    bytes.fromhex('242c8b5424448b74243409f251ff74241c50ff74244c5355ff742444ff74243889f98b442430e8f0'),
    bytes.fromhex('2e000083c420ff4424108344242004837c2410200f85b7f7ffff81c49c0000005b5e5f5dc3669090'),
    bytes.fromhex('0201010505020203000300050203030304890d00000000c7042400000000e96c3832009c60fc6a00'),
    bytes.fromhex('ff3500000000e8fcffffff83c408619de9118024009c60fce8fcfffffff6050c000000407507619d'),
    bytes.fromhex('e91ce02b00619de81ce02b009c60fc6a0155e8fcffffff83c408619dc39c60fce8fcffffff619de8'),
    bytes.fromhex('7ceb27009c60fcf6050c0000004074106a02ff3500000000e8fcffffff83c408619dc3e8eced2700'),
    bytes.fromhex('9c60fcf6050c0000004074106a03ff3500000000e8fcffffff83c408619dc3'),
    b'\xcc' * 281,
    bytes(512),
    bytes.fromhex('5557565383ec2489c389d783c0386b53143401c231f639d0741f83782c00741483782800750e85f6'),
    bytes.fromhex('74088b4e24394824730289c683c034ebdda13800000040a33800000085f67512a13c00000040a33c'),
    bytes.fromhex('00000031c0e94d0100008b4f082b4e08786183f9050f8f9d00000069c178ecffff890c248da8084c'),
    bytes.fromhex('0100c7442410010000008b0389442414a1b876e500894424188b46048944241c8b470489442420ba'),
    bytes.fromhex('050000008d442410e81a00000089c2a14000000040a34000000039ea8b0c247349eb05bda0860100'),
    bytes.fromhex('a14400000040a3440000008b4f24ba010000003b4e240f838900000089f289d8e80c2e0000a13401'),
    bytes.fromhex('000040a334010000ba01000000837b0c0119c983c102eb7031eda14800000040a3480000008b4624'),
    bytes.fromhex('3b4724734e83f9057f49837b04077406837b3400753d89c189fa89d8e80c2e000089fa89d8e84902'),
    bytes.fromhex('000089f289d8e849020000a13801000040a3380100008b530cb90100000085d2741631d2b9020000'),
    bytes.fromhex('00eb0d31d28b4b1085c9742c31c9eb0ba14c00000040a34c00000085d27505ba4100000055575689'),
    bytes.fromhex('4c240c89d8e82d01000083c40c8b0c2431c085c90f95c083c4245b5e5f5dc3'),
    bytes(2657),
    bytes.fromhex('5557565383ec0889c38914248b4014894424048d533831ff397c240474448b4224391424740f39c8'),
    bytes.fromhex('72328b34243b4624732a40eb0639c1742389c8837b0c0075188b32668b6e286681e5ffe389c6c1e6'),
    bytes.fromhex('0a09f58b3266896e288942244783c234ebb6837b0c00740da19800000040a398000000eb0ba19000'),
    bytes.fromhex('000040a39000000083c4085b5e5f5dc357565389c689d10fb6921c01000080fa4177458d3c9139f9'),
    bytes.fromhex('743e8b1985db74338a433584c0752c89d8e85e00000085c074218a4352a801741a837e0c0075098a'),
    bytes.fromhex('435283e0fe884352a15801000040a35801000083c104ebbe5b5e5fc35557565383ec28890424894c'),
    bytes.fromhex('24048b6c243c8b7c24408b5c244c8b0d000000008b351829b7008b7604a1b876e5006689442414a0'),
    bytes.fromhex('b476e500884424168a042488442417885424188a4424048844241983c8ff85ed740d89e829f0bd54'),
    bytes.fromhex('00000031d2f7f5668944241a83c8ff85ff740d89f829f0be5400000031d2f7f6668944241c8b4424'),
    bytes.fromhex('448844241e8b4424488844241f31c085db780d83c8ff81fbffff00007f0289d866894424208b4424'),
    bytes.fromhex('50884424228b442454884424238b4424588944242489ca83e27f6bd21481c20000000031c08b5c84'),
    bytes.fromhex('14891c824083f80575f341890d00000000ff059c00000083c4285b5e5f5dc3'),
    bytes(25),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0004, True, 'page', 0xed2),
    (0x000b, True, 'stock', 0x2be01c),
    (0x0013, True, 'page', 0xee7),
    (0x001a, True, 'stock', 0x27eb7c),
    (0x0143, False, 'page', 0x2e00),
    (0x0157, False, 'page', 0x2400),
    (0x015e, False, 'page', 0x2400),
    (0x01d3, False, 'page', 0x2e00),
    (0x01d8, False, 'page', 0x20dc),
    (0x01de, False, 'page', 0x20dc),
    (0x026c, False, 'page', 0x20d4),
    (0x0272, False, 'page', 0x20d4),
    (0x02a2, False, 'page', 0x20d8),
    (0x02a8, False, 'page', 0x20d8),
    (0x02d5, False, 'page', 0x20d0),
    (0x02db, False, 'page', 0x20d0),
    (0x041e, False, 'page', 0x2000),
    (0x042c, False, 'page', 0x2004),
    (0x043a, False, 'page', 0x2008),
    (0x0442, False, 'page', 0x2048),
    (0x0448, False, 'page', 0x2048),
    (0x0459, False, 'page', 0x200c),
    (0x0483, False, 'page', 0x204c),
    (0x0489, False, 'page', 0x204c),
    (0x04a0, False, 'page', 0x2010),
    (0x04ad, False, 'page', 0x2014),
    (0x04b2, False, 'page', 0x2018),
    (0x0502, False, 'page', 0x2050),
    (0x0508, False, 'page', 0x2050),
    (0x051e, False, 'page', 0x2054),
    (0x0524, False, 'page', 0x2054),
    (0x0548, False, 'page', 0x2058),
    (0x054e, False, 'page', 0x2058),
    (0x0585, True, 'page', 0x2e94),
    (0x0601, False, 'page', 0x205c),
    (0x0607, False, 'page', 0x205c),
    (0x063f, False, 'page', 0x2060),
    (0x0645, False, 'page', 0x2060),
    (0x068c, False, 'page', 0x2064),
    (0x0692, False, 'page', 0x2064),
    (0x0802, False, 'page', 0x2068),
    (0x0808, False, 'page', 0x2068),
    (0x08c3, True, 'page', 0x2e0c),
    (0x08c8, False, 'page', 0x217c),
    (0x08ce, False, 'page', 0x217c),
    (0x09fc, False, 'page', 0x2074),
    (0x0a02, False, 'page', 0x2074),
    (0x0a1d, False, 'page', 0x206c),
    (0x0a24, False, 'page', 0x206c),
    (0x0a33, True, 'page', 0x21fc),
    (0x0abb, False, 'page', 0x20b8),
    (0x0ac2, False, 'page', 0x20b8),
    (0x0acc, False, 'page', 0x20bc),
    (0x0ad3, False, 'page', 0x20bc),
    (0x0ae0, False, 'page', 0x20c0),
    (0x0ae6, False, 'page', 0x20c0),
    (0x0b5a, False, 'page', 0x20c4),
    (0x0b60, False, 'page', 0x20c4),
    (0x0b6b, False, 'page', 0x20c8),
    (0x0b71, False, 'page', 0x20c8),
    (0x0b96, False, 'page', 0x20cc),
    (0x0b9c, False, 'page', 0x20cc),
    (0x0bc7, False, 'page', 0x2070),
    (0x0bcd, False, 'page', 0x2070),
    (0x0c3d, False, 'page', 0x20a0),
    (0x0c43, False, 'page', 0x20a0),
    (0x0c57, False, 'page', 0x20b0),
    (0x0c61, False, 'page', 0x20b4),
    (0x0c68, False, 'page', 0x20b4),
    (0x0c6d, False, 'page', 0x20b0),
    (0x0c9d, False, 'page', 0x20a4),
    (0x0ca3, False, 'page', 0x20a4),
    (0x0cac, False, 'page', 0x20a8),
    (0x0cb2, False, 'page', 0x20a8),
    (0x0cdf, False, 'page', 0x20ac),
    (0x0ce5, False, 'page', 0x20ac),
    (0x0d7c, False, 'page', 0x2090),
    (0x0d82, False, 'page', 0x2090),
    (0x0dab, False, 'page', 0xf00),
    (0x0e4a, False, 'page', 0x2094),
    (0x0e50, False, 'page', 0x2094),
    (0x0e59, False, 'page', 0x2098),
    (0x0e5f, False, 'page', 0x2098),
    (0x0e87, False, 'page', 0x209c),
    (0x0e8d, False, 'page', 0x209c),
    (0x0ed7, False, 'page', 0x2040),
    (0x0edd, False, 'page', 0x2040),
    (0x0eec, False, 'page', 0x2044),
    (0x0ef2, False, 'page', 0x2044),
    (0x1277, False, 'page', 0x1e28),
    (0x1474, False, 'page', 0x216c),
    (0x1496, False, 'page', 0x2128),
    (0x14a2, False, 'page', 0x2e04),
    (0x14b4, False, 'page', 0x20f8),
    (0x14bc, False, 'page', 0x2190),
    (0x14c1, False, 'page', 0x2000),
    (0x14cd, False, 'page', 0x2004),
    (0x14d9, False, 'page', 0x2008),
    (0x14f0, False, 'page', 0x2048),
    (0x14fa, False, 'page', 0x200c),
    (0x155f, False, 'page', 0x20fc),
    (0x157c, False, 'page', 0x2010),
    (0x1595, False, 'page', 0x2e08),
    (0x161f, False, 'page', 0x2100),
    (0x1689, False, 'page', 0x2020),
    (0x16f8, False, 'page', 0x210c),
    (0x17d6, False, 'page', 0x20e8),
    (0x187d, False, 'page', 0x2110),
    (0x18c6, False, 'page', 0x2114),
    (0x18e2, False, 'page', 0x20e0),
    (0x18ec, False, 'page', 0x2104),
    (0x1902, False, 'page', 0x2118),
    (0x192d, False, 'page', 0x211c),
    (0x195a, False, 'page', 0x2120),
    (0x1988, False, 'page', 0x20e4),
    (0x1995, False, 'page', 0x20ec),
    (0x199d, False, 'page', 0x2124),
    (0x19c3, True, 'page', 0x2ef0),
    (0x1a47, False, 'page', 0x2e08),
    (0x1a66, False, 'page', 0x2194),
    (0x1a73, False, 'page', 0x2e08),
    (0x1a83, False, 'page', 0x212c),
    (0x1a8d, False, 'page', 0x2188),
    (0x1ab1, False, 'page', 0x2134),
    (0x1ad3, False, 'page', 0x213c),
    (0x1b49, False, 'page', 0x2144),
    (0x1b92, False, 'page', 0x2140),
    (0x1bbd, False, 'page', 0x2148),
    (0x1bfb, False, 'page', 0x2164),
    (0x1c68, False, 'page', 0x2154),
    (0x1c8c, False, 'page', 0x2184),
    (0x1c92, False, 'page', 0x2158),
    (0x1c9f, False, 'page', 0x2180),
    (0x1cb5, False, 'page', 0x215c),
    (0x1cbd, False, 'page', 0x214c),
    (0x1d46, False, 'page', 0x2160),
    (0x1d75, True, 'page', 0x13da),
    (0x1d80, False, 'page', 0x218c),
    (0x1d88, False, 'page', 0x2168),
    (0x1db7, False, 'page', 0x2170),
    (0x1dff, True, 'page', 0x2ef0),
    (0x1e3b, False, 'page', 0x2e04),
    (0x1e42, False, 'page', 0x1e4b),
    (0x1e47, True, 'stock', 0x32386c),
    (0x1e52, False, 'page', 0x2e04),
    (0x1e57, True, 'page', 0x147c),
    (0x1e61, True, 'stock', 0x248011),
    (0x1e69, True, 'page', 0xed2),
    (0x1e6f, False, 'page', 0x200c),
    (0x1e79, True, 'stock', 0x2be01c),
    (0x1e80, True, 'stock', 0x2be01c),
    (0x1e8b, True, 'page', 0x147c),
    (0x1e99, True, 'page', 0xee7),
    (0x1ea0, True, 'stock', 0x27eb7c),
    (0x1ea9, False, 'page', 0x200c),
    (0x1eb4, False, 'page', 0x2e04),
    (0x1eb9, True, 'page', 0x147c),
    (0x1ec4, True, 'stock', 0x27edec),
    (0x1ecd, False, 'page', 0x200c),
    (0x1ed8, False, 'page', 0x2e04),
    (0x1edd, True, 'page', 0x147c),
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
    (0x233e, True, 'page', 0x249),
    (0x2347, True, 'page', 0x249),
    (0x234c, False, 'page', 0x2178),
    (0x2352, False, 'page', 0x2178),
    (0x2379, False, 'page', 0x208c),
    (0x237f, False, 'page', 0x208c),
    (0x2396, True, 'page', 0x12d),
    (0x2e79, False, 'page', 0x20d8),
    (0x2e7f, False, 'page', 0x20d8),
    (0x2e86, False, 'page', 0x20d0),
    (0x2e8c, False, 'page', 0x20d0),
    (0x2ec2, True, 'page', 0x5e),
    (0x2ee1, False, 'page', 0x2198),
    (0x2ee7, False, 'page', 0x2198),
    (0x2f10, False, 'page', 0x2e00),
    (0x2fbf, False, 'page', 0x2400),
    (0x2fd5, False, 'page', 0x2e00),
    (0x2fdb, False, 'page', 0x20dc),
)

LABELS = {
    'emergency_pass': 0x1480,
    'end_entry': 0x1e95,
    'floor_seat': 0x13de,
    'opening_entry': 0x0,
    'opening_pass': 0xed6,
    'pregame_entry': 0x1e65,
    'room_entry': 0xf,
    'room_pass': 0xeeb,
    'sign_after': 0x1e4b,
    'sign_entry': 0x1e39,
    'stage_entry': 0x1ec3,
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
    'floor_no_fit': 0x2180,
    'floor_extra_releases': 0x2184,
    'floor_lost_since': 0x2188,
    'floor_unseated': 0x218c,
    'floor_end_passes': 0x2190,
    'floor_no_game': 0x2194,
    'season_locks_cleared': 0x2198,
}

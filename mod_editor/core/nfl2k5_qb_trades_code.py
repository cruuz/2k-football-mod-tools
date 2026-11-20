"""Relocatable page of the quarterback trades owner (beta 81 stage 4b, owner nfl2k5_qb_trades; DESIGN_CHANGES C20).

One page: code at 0x000 (0xCC after the last byte of code up to 0xF00), the link word +0xF00 (the IR owner's store, for
E2's "lost starter"), the flag word +0xF04 (bit 0: 4b alone in shadow), zeros after them. The page has no settings, counters or ring of its own: it reads the quarterback
room's settings record (stage bit 16, the shadow flag) and writes rows and counters to the room's ring and counters at
the room page's fixed offsets (relocation family "room"). One whole 5-byte call enters it: 0x247E1E, the stage-8 case's
`call 0x2BC960` (the native trade pass), which only runs while the native trade window 0x247D10 is open. The template,
relocations and labels are generated from tools/qb_trades by build.py; the pick word is in nfl2k5_trade_picks.
"""
from __future__ import annotations

import struct

PAGE_SIZE = 0x1000
CODE_LIMIT = 0xF00
LINK_IR_STORE = 0xF00
FLAGS = 0xF04                        # bit 0: 4b alone in shadow (the room's other stages act); written at install
FLAG_SHADOW = 1
# The room page offsets this page reads or writes (the room's INTERFACE.md; checked against its code module by the tests).
ROOM_OFFSETS = {"settings": 0x2000, "counters": 0x2040, "ring": 0x2400, "ring_cursor": 0x2E00}
RING_COUNT = 128                     # the room's ring, as this page indexes it
HOOK = (0x247E1E, bytes.fromhex("e83d4b0700"), "trade_entry")      # call 0x2BC960 (retail and every b81 build)
NATIVE_PASS = 0x2BC960
DECISION_TRADE = 8                   # ring rows: see tools/qb_trades/trades.c
TRADE_NEED_D3, TRADE_AFTER = 0x10, 0x40
RESULT_NOT_POSTED, RESULT_POSTED, RESULT_WOULD, RESULT_REFUSED, RESULT_CANCELLED = 0, 1, 2, 4, 7
RESULT_EXECUTED, RESULT_GONE = 1, 0  # rows after the native pass (decision bit 0x40)


def _whole(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"The quarterback trades {name} must be a whole number from {low} to {high}")
    return value


def _set32(page, offset, value):
    struct.pack_into("<I", page, offset, value & 0xFFFFFFFF)


def page_bytes(va: int, room_va: int, *, ir_store_va: int = 0, shadow: bool = False) -> bytes:
    """The whole 0x1000-byte page linked for `va`, reaching the room page at `room_va`, with the link word and the flag
    word (shadow: 4b computes and logs but writes nothing to the board, whatever the room's own shadow flag) in place."""
    for value, name in ((va, "page address"), (room_va, "room address")):
        _whole(value, 0x1000, 0xFFFFFFFF - 0x3000 + 1, name)
        if value % 0x1000:
            raise ValueError(f"The quarterback trades {name} must be on a page boundary")
    _whole(ir_store_va, 0, 0xFFFFFFFF, "IR store address")
    if type(shadow) is not bool:
        raise ValueError("The quarterback trades shadow flag must be True or False")
    page = bytearray(_TEMPLATE)
    for offset, relative, family, addend in _RELOCATIONS:
        target = {"page": va, "room": room_va, "stock": 0}[family] + addend
        _set32(page, offset, target - (va + offset) if relative else target)
    _set32(page, LINK_IR_STORE, ir_store_va)
    _set32(page, FLAGS, FLAG_SHADOW if shadow else 0)
    return bytes(page)


def site(va: int) -> tuple[int, bytes, bytes]:
    """(site, retail call, installed call)."""
    at, original, label = HOOK
    return at, original, b"\xe8" + struct.pack("<I", (va + LABELS[label] - at - 5) & 0xFFFFFFFF)


# Generated from tools/qb_trades by build.py.
CODE_BYTES = 0x96e

_TEMPLATE = b''.join((
    bytes.fromhex('fc5251e8fcffffff83c408c3f740200000c0bf750ef74024000000700f94c00fb6c0c331c0c35383'),
    bytes.fromhex('ec1889c1ba01000000b8806d2400ffd0d95c240c8b54240c89d0c1e8173c76763c85d278380fb6d8'),
    bytes.fromhex('b8640000000fbae21e722c81e2ffff7f0081ca000080006bd264b99500000029d9b801000000d3e0'),
    bytes.fromhex('01d0b99600000029d9d3e8eb0231c083c4185bc35653b97cc2e3008339000f95c3ba0800000083fa'),
    bytes.fromhex('30741884db741489d683e6fb83fe18740539040a741483c204ebe383c13c81f900c6e30075cd31c0'),
    bytes.fromhex('eb05b8010000005b5ec385c074138b151829b7002b4204b95400000031d2f7f1c3b8ffff0000c355'),
    bytes.fromhex('57565389c58b350000000089f083e07f6bc0148d98000000008b3db876e5006689b800000000a1b4'),
    bytes.fromhex('76e50088430289e8884303885304884b058b442414e8a0ffffff668943068b442418e893ffffff66'),
    bytes.fromhex('8943088b44241c88430a8b44242088430b8b4424246689430c8b44242888430e8b44242c88430fc7'),
    bytes.fromhex('4310b888000046893500000000ff059c0000005b5e5f5dc35557565381ec4c050000ff055c010000'),
    bytes.fromhex('813d000000005142524f0f859d060000813d040000004f4d76310f858d060000833d08000000010f'),
    bytes.fromhex('8580060000f6050c000000100f8473060000833d1829b700000f8466060000833da476e500080f85'),
    bytes.fromhex('53060000a1b876e50089442428a1b476e500894424048b350000000031d231db895c2414895c2410'),
    bytes.fromhex('8d6eff39f20f838c00000081fa800000000f848000000089e829d083e07f6bc0148d88000000000f'),
    bytes.fromhex('b7800000000039442428755d0fb679028d47018b5c240439d8724e8a4105483c0177468a410488c3'),
    bytes.fromhex('83e30f885c24088a4903bb01000000d3e389d983e00f83e80583f8027706095c2410eb1d397c2404'),
    bytes.fromhex('0f94c031db807c2408030f94c389df21c7f7df21cf097c241442e96cffffff8d9c24c001000031c9'),
    bytes.fromhex('894c24048b4c2404b8504c0c00ffd089c68903c743140100000031d289530489531885c00f84c101'),
    bytes.fromhex('00008b442404833c855c77e500000f85af01000089f0e8a1fdffff89c585c00f859e0100000fb686'),
    bytes.fromhex('1c0100008944240883f8410f878a0100008d04868944241889f231c08944240c3954241874418b3a'),
    bytes.fromhex('85ff7436807f350075304589f8e8dafcffff85c074248954241c89f8e8e5fcffff837b04008b5424'),
    bytes.fromhex('1c74053b43187e06897b04894318ff44240c83c204ebb989f1b820770c00ffd089c789430889f1b8'),
    bytes.fromhex('50770c00ffd089430c8944241889f1b880770c00ffd089c1894310837c240c020f97c089c683fd02'),
    bytes.fromhex('0f97c021c631c0837c2408320f97c021f001c08943148b44240883e83183f8030f87d5000000837c'),
    bytes.fromhex('240c000f84ca0000008b5424188d041701c883f8010f86b80000004739d70f82af0000008b442410'),
    bytes.fromhex('8b7c24040fa3f80f829e0000008b7424148a4c2404d3ee83e601740cc7431414000000e983000000'),
    bytes.fromhex('83fd02777e8b5318a10000000085c074088138363249527408ff0588010000eb62694c2404a40000'),
    bytes.fromhex('008d7c08400fb60f83c70439ce734c83fe1474478b2f85ed75064683c708ebeb807d350075f4894c'),
    bytes.fromhex('240c8954240889e8e8b9fbffff8b54240829d083f8028b4c240c7ed6f6470601750a8b4520c1e816'),
    bytes.fromhex('3c0276c6c7431404000000ff44240483c31c837c2404200f8507feffffa1987fbd008944241c85c0'),
    bytes.fromhex('740731c0a3987fbd008d9c24c001000031c08944241831ed8b43148944242c83e00c8944240483f8'),
    bytes.fromhex('040f8539030000ff05640100008b43188944243083c0028944240c8b0389442434a178c2e3008b74'),
    bytes.fromhex('24342b86240100008944243c8dbc24c001000031c0894424148944240889442424837f14020f85b2'),
    bytes.fromhex('0000008b078944243831c0894424108b4424380fb6801c010000394424100f83910000008b442438'),
    bytes.fromhex('8b7424108b34b085f67406807e3500740e8b44240c894424208b742408eb5989f0e896faffff85c0'),
    bytes.fromhex('74e766f74628001c74dff646251c74d9f646240f74d389f0e891faffff894424208b54240c39d07e'),
    bytes.fromhex('c089f1b880630e00ffd08b54243c29c283fa0a7eac89f0e8d0faffff85c075a18b44242489442414'),
    bytes.fromhex('ff4424108b4424208944240c89742408e95affffffff44242483c71c837c2424200f8532ffffff83'),
    bytes.fromhex('7c240800750bff0568010000e917020000b804000000837c240c517f19b805000000837c240c4b7f'),
    bytes.fromhex('0d31c0837c240c460f9cc083c00689eac1e20689c1c1e1050fb68c0d94c0e30031f68974241039e9'),
    bytes.fromhex('750889d609c6897424104083f8087407837c24100074d48b4b088b530c8b43108b7304837c241000'),
    bytes.fromhex('750bff056c010000e995000000c744244808000000896c244c8b7c2428897c2450894c2454895424'),
    bytes.fromhex('588944245c8b442408e834faffff89442460bf40ee1400ba0600000089f1ffd789442464ba080000'),
    bytes.fromhex('0089f1ffd789442468b83352425131d23344944889c1c1e91031c869c06bcaeb8589c1c1e90d31c8'),
    bytes.fromhex('69c035aeb2c289c1c1e91031c84283fa0975d5b9a086010031d2f7f181fab78800007611ff057001'),
    bytes.fromhex('000031c089442404e9c100000031d28d44246c31ff893c904283fa0f75f1c744246c020000006b54'),
    bytes.fromhex('24141c8b9414c0010000895424748b7c2408897c24788b7c243489bc248c0000008b74241089b424'),
    bytes.fromhex('9c0000008d7c24408d7424446a005657b990ae2b00ffd185c07508ff0574010000eb5bb801000000'),
    bytes.fromhex('6bd03c83ba7cc2e3000074114083f80f75eeff0578010000e96dffffff8b44242c83c8088943146b'),
    bytes.fromhex('4424141c838c04d401000008a1100000000b050000000083e0010f8432010000ff057c010000c744'),
    bytes.fromhex('2404020000008b4b088b430c8b531483e21083ca0856ff7424188b7c24148b74243829f757ff7424'),
    bytes.fromhex('1c8d34010373105629c850ff7304ff7424248b4c242489e8e8daf8ffff83c4204583c31c83fd200f'),
    bytes.fromhex('85a3fcffff837c241c0074178b44241ca3987fbd00eb0cff056001000031c9894c24188b94246405'),
    bytes.fromhex('00008b8c2460050000b860c92b00ffd08d9c24a800000031f6397424180f84f80000008b0b8b7b04'),
    bytes.fromhex('833902752339790c751e55556a016a0131d2b860b62b00ffd0ff05b4000000585ab907000000eb2f'),
    bytes.fromhex('8b4b08b8504c0c00ffd00fb6881c01000031d283fa41744039ca733c393c90740342ebefff058001'),
    bytes.fromhex('0000b9010000008b430852ff730c6a00ff73106a006a006a0057ba48000000e80bf8ffff4683c314'),
    bytes.fromhex('83c420e971ffffffff058401000031c9ebcd8d8a7cc2e3008b7c047089bc0280c2e30083c00483f8'),
    bytes.fromhex('3075ed66c782b0c2e3000000c7827cc2e300020000006b442418148d8404a800000089088b742408'),
    bytes.fromhex('8970048968088b74241489700cff4424188b742410897010ff05b0000000c744240401000000e973'),
    bytes.fromhex('feffff81c44c0500005b5e5f5dc3'),
    b'\xcc' * 1426,
    bytes(256),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0004, True, 'page', 0x17c),
    (0x00f7, False, 'room', 0x2e00),
    (0x0105, False, 'room', 0x2400),
    (0x0112, False, 'room', 0x2400),
    (0x0171, False, 'room', 0x2e00),
    (0x0177, False, 'room', 0x20dc),
    (0x018c, False, 'room', 0x219c),
    (0x0192, False, 'room', 0x2000),
    (0x01a2, False, 'room', 0x2004),
    (0x01b2, False, 'room', 0x2008),
    (0x01bf, False, 'room', 0x200c),
    (0x01f8, False, 'room', 0x2e00),
    (0x022b, False, 'room', 0x2400),
    (0x0232, False, 'room', 0x2400),
    (0x0419, False, 'page', 0xf00),
    (0x042b, False, 'room', 0x21c8),
    (0x04e1, False, 'room', 0x21a4),
    (0x05f8, False, 'room', 0x21a8),
    (0x066c, False, 'room', 0x21ac),
    (0x0706, False, 'room', 0x21b0),
    (0x0775, False, 'room', 0x21b4),
    (0x0794, False, 'room', 0x21b8),
    (0x07b5, False, 'room', 0x2010),
    (0x07bb, False, 'page', 0xf04),
    (0x07ca, False, 'room', 0x21bc),
    (0x0839, False, 'room', 0x21a0),
    (0x088b, False, 'room', 0x20f4),
    (0x08be, False, 'room', 0x21c0),
    (0x08f2, False, 'room', 0x21c4),
    (0x0952, False, 'room', 0x20f0),
)

LABELS = {
    'trade_call': 0x180,
    'trade_entry': 0x0,
}

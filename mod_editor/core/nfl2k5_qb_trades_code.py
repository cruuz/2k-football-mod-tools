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
CODE_BYTES = 0x97d

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
    bytes.fromhex('813d000000005142524f7536813d040000004f4d7631752a833d08000000017521f6050c00000010'),
    bytes.fromhex('7418833d1829b70000740f833da476e500087411ff056001000031f689742418e975060000a1b476'),
    bytes.fromhex('e500894424040fb605c5515100394424047208ff058c010000ebd7a1b876e500894424248b350000'),
    bytes.fromhex('000031d231db895c2414895c24108d6eff81fa800000000f848800000039f20f838000000089e829'),
    bytes.fromhex('d083e07f6bc0148d88000000000fb7800000000039442424755d0fb679028d47018b5c240439d872'),
    bytes.fromhex('4e8a4105483c0177468a410488c383e30f885c24088a4903bb01000000d3e389d983e00f83e80583'),
    bytes.fromhex('f8027706095c2410eb1d397c24040f94c031db807c2408030f94c389df21c7f7df21cf097c241442'),
    bytes.fromhex('e96cffffff8d9c24c001000031c9894c24048b4c2404b8504c0c00ffd089c68903c7431401000000'),
    bytes.fromhex('31d289530489531885c00f84c10100008b442404833c855c77e500000f85af01000089f0e893fdff'),
    bytes.fromhex('ff89c585c00f859e0100000fb6861c0100008944240883f8410f878a0100008d04868944241889f2'),
    bytes.fromhex('31c08944240c3954241874418b3a85ff7436807f350075304589f8e8ccfcffff85c074248954241c'),
    bytes.fromhex('89f8e8d7fcffff837b04008b54241c74053b43187e06897b04894318ff44240c83c204ebb989f1b8'),
    bytes.fromhex('20770c00ffd089c789430889f1b850770c00ffd089430c8944241889f1b880770c00ffd089c18943'),
    bytes.fromhex('1083fd020f97c089c6837c240c020f97c021c631c0837c2408320f97c021f001c08943148b442408'),
    bytes.fromhex('83e83183f8030f87d5000000837c240c000f84ca0000008b5424188d041701c883f8010f86b80000'),
    bytes.fromhex('004739d70f82af0000008b4424108b7c24040fa3f80f829e0000008b7424148a4c2404d3ee83e601'),
    bytes.fromhex('740cc7431414000000e98300000083fd02777e8b5318a10000000085c074088138363249527408ff'),
    bytes.fromhex('0588010000eb62694c2404a40000008d7c08400fb60f83c70439ce734c83fe1474478b2f85ed7506'),
    bytes.fromhex('4683c708ebeb807d350075f4894c240c8954240889e8e8abfbffff8b54240829d083f8028b4c240c'),
    bytes.fromhex('7ed6f6470601750a8b4520c1e8163c0276c6c7431404000000ff44240483c31c837c2404200f8507'),
    bytes.fromhex('feffffa1987fbd008944241c85c0740731c0a3987fbd008d9c24c001000031c08944241831ed8b43'),
    bytes.fromhex('148944242883e00c8944240883f8040f8548030000ff05640100008b43188944242c83c002894424'),
    bytes.fromhex('048b0389442430a178c2e3008b7424302b8624010000894424388dbc24c001000031c08944241489'),
    bytes.fromhex('44240c89442420837f14020f85b50000008b078944243431c0894424108b4424340fb6801c010000'),
    bytes.fromhex('394424100f83940000008b4424348b7424108b34b085f67406807e3500740a8b5424048b74240ceb'),
    bytes.fromhex('6489f0e88cfaffff85c074eb66f74628001c74e3f646251c74ddf646240f74d789f0e887faffff89'),
    bytes.fromhex('c28b44240439c27ec63b57188954243c7dbd89f1b880630e00ffd08b4c243829c183f90a7ea989f0'),
    bytes.fromhex('e8bffaffff85c0759e8b442420894424148b54243cff442410895424048974240ce957ffffffff44'),
    bytes.fromhex('242083c71c837c2420200f852fffffff837c240c00750bff0568010000e923020000b80300000083'),
    bytes.fromhex('7c2404597f25b804000000837c2404517f19b805000000837c24044b7f0d31c0837c2404460f9cc0'),
    bytes.fromhex('83c00689eac1e20689c1c1e1050fb68c0d94c0e30031f68974241039e9750889d609c68974241040'),
    bytes.fromhex('837c241000750583f80875d48b4b088b530c8b43108b7304837c241000750bff056c010000e99500'),
    bytes.fromhex('0000c744244808000000896c244c8b7c2424897c2450894c2454895424588944245c8b44240ce817'),
    bytes.fromhex('faffff89442460bf40ee1400ba0600000089f1ffd789442464ba0800000089f1ffd789442468b833'),
    bytes.fromhex('52425131d23344944889c1c1e91031c869c06bcaeb8589c1c1e90d31c869c035aeb2c289c1c1e910'),
    bytes.fromhex('31c84283fa0975d5b9a086010031d2f7f181fab78800007611ff057001000031c089442408e9c100'),
    bytes.fromhex('000031d28d44246c31ff893c904283fa0f75f1c744246c020000006b5424141c8b9414c001000089'),
    bytes.fromhex('5424748b7c240c897c24788b7c243089bc248c0000008b7c241089bc249c0000008d7c24408d7424'),
    bytes.fromhex('446a005657b990ae2b00ffd185c07508ff0574010000eb5bb8010000006bd03c83ba7cc2e3000074'),
    bytes.fromhex('114083f80f75eeff0578010000e96dffffff8b44242883c8088943146b4424141c838c04d4010000'),
    bytes.fromhex('08a1100000000b050000000083e0010f8424010000ff057c010000c7442408020000008b4b088b43'),
    bytes.fromhex('0c8b531483e21083ca0856ff7424188b7c240c8b74243429f757ff74241c8d34010373105629c850'),
    bytes.fromhex('ff7304ff7424288b4c242889e8e8bdf8ffff83c4204583c31c83fd200f8594fcffff837c241c0074'),
    bytes.fromhex('098b44241ca3987fbd008b9424640500008b8c2460050000b860c92b00ffd08d9c24a800000031f6'),
    bytes.fromhex('397424180f84f80000008b0b8b7b04833902752339790c751e55556a016a0131d2b860b62b00ffd0'),
    bytes.fromhex('ff05b4000000585ab907000000eb2f8b4b08b8504c0c00ffd00fb6881c01000031d283fa41744039'),
    bytes.fromhex('ca733c393c90740342ebefff0580010000b9010000008b430852ff730c6a00ff73106a006a006a00'),
    bytes.fromhex('57ba48000000e8fcf7ffff4683c31483c420e971ffffffff058401000031c9ebcd8d8a7cc2e3008b'),
    bytes.fromhex('7c047089bc0280c2e30083c00483f83075ed66c782b0c2e3000000c7827cc2e300020000006b4424'),
    bytes.fromhex('18148d8404a800000089088b74240c8970048968088b74241489700cff4424188b7c2410897810ff'),
    bytes.fromhex('05b0000000c744240801000000e981feffff81c44c0500005b5e5f5dc3'),
    b'\xcc' * 1411,
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
    (0x019e, False, 'room', 0x2004),
    (0x01aa, False, 'room', 0x2008),
    (0x01b3, False, 'room', 0x200c),
    (0x01ce, False, 'room', 0x21a0),
    (0x01f5, False, 'room', 0x21cc),
    (0x0206, False, 'room', 0x2e00),
    (0x0239, False, 'room', 0x2400),
    (0x0240, False, 'room', 0x2400),
    (0x0427, False, 'page', 0xf00),
    (0x0439, False, 'room', 0x21c8),
    (0x04ef, False, 'room', 0x21a4),
    (0x0609, False, 'room', 0x21a8),
    (0x0689, False, 'room', 0x21ac),
    (0x0723, False, 'room', 0x21b0),
    (0x0792, False, 'room', 0x21b4),
    (0x07b1, False, 'room', 0x21b8),
    (0x07d2, False, 'room', 0x2010),
    (0x07d8, False, 'page', 0xf04),
    (0x07e7, False, 'room', 0x21bc),
    (0x089a, False, 'room', 0x20f4),
    (0x08cd, False, 'room', 0x21c0),
    (0x0901, False, 'room', 0x21c4),
    (0x0961, False, 'room', 0x20f0),
)

LABELS = {
    'trade_call': 0x180,
    'trade_entry': 0x0,
}

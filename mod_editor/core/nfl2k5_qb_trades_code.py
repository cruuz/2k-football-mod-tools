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
CODE_BYTES = 0x987

_TEMPLATE = b''.join((
    bytes.fromhex('fc5251e8fcffffff83c408c3f740200000c0bf750ef74024000000700f94c00fb6c0c331c0c35383'),
    bytes.fromhex('ec1889c1b8806d2400ffd0d95c240c8b54240c89d0c1e8173c76763c85d278380fb6d8b864000000'),
    bytes.fromhex('0fbae21e722c81e2ffff7f0081ca000080006bd264b99500000029d9b801000000d3e001d0b99600'),
    bytes.fromhex('000029d9d3e8eb0231c083c4185bc35653b97cc2e3008339000f95c3ba0800000083fa30741884db'),
    bytes.fromhex('741489d683e6fb83fe18740539040a741483c204ebe383c13c81f900c6e30075cd31c0eb05b80100'),
    bytes.fromhex('00005b5ec385c074138b151829b7002b4204b95400000031d2f7f1c3b8ffff0000c35557565389c5'),
    bytes.fromhex('8b350000000089f083e07f6bc0148d98000000008b3db876e5006689b800000000a1b476e5008843'),
    bytes.fromhex('0289e8884303885304884b058b442414e8a0ffffff668943068b442418e893ffffff668943088b44'),
    bytes.fromhex('241c88430a8b44242088430b8b4424246689430c8b44242888430e8b44242c88430fc74310b88800'),
    bytes.fromhex('0046893500000000ff059c0000005b5e5f5dc35557565381ec4c050000ff0560010000813d000000'),
    bytes.fromhex('005142524f7536813d040000004f4d7631752a833d08000000017521f6050c000000107418833d18'),
    bytes.fromhex('29b70000740f833da476e500087411ff056401000031f689742418e984060000a1b476e500894424'),
    bytes.fromhex('040fb605c5515100394424047208ff0590010000ebd7a1b876e500894424248b350000000031d231'),
    bytes.fromhex('db895c2418895c24148d6eff81fa800000000f848800000039f20f838000000089e829d083e07f6b'),
    bytes.fromhex('c0148d88000000000fb7800000000039442424755d0fb679028d47018b5c240439d8724e8a410548'),
    bytes.fromhex('3c0177468a410488c383e30f885c24088a4903bb01000000d3e389d983e00f83e80583f802770609'),
    bytes.fromhex('5c2414eb1d397c24040f94c031db807c2408030f94c389df21c7f7df21cf097c241842e96cffffff'),
    bytes.fromhex('8d9c24c001000031c9894c24048b4c2404b8504c0c00ffd089c68903c743140100000031d2895304'),
    bytes.fromhex('89531885c00f84cf0100008b442404833c855c77e500000f85bd01000089f0e893fdffff8944240c'),
    bytes.fromhex('85c00f85aa0100000fb6861c0100008944240883f8410f87960100008d04868944241c89f531c089'),
    bytes.fromhex('442410396c241c74428b7d0085ff7436807f35007530ff44240c89f8e8cbfcffff85c07421ba0100'),
    bytes.fromhex('000089f8e8d5fcffff837b040074053943187d06897b04894318ff44241083c504ebb889f1b82077'),
    bytes.fromhex('0c00ffd089c789430889f1b850770c00ffd089430c8944241c89f1b880770c00ffd089c689431083'),
    bytes.fromhex('7c240c020f97c089c5837c2410020f97c121e931c0837c2408320f97c021c801c08943148b442408'),
    bytes.fromhex('83e83183f8030f97c1837c2410000f94c008c80f85d100000089e884c00f85c70000008b54241c8d'),
    bytes.fromhex('041701f083f8010f86b50000004739d70f82ac0000008b4424148b7424040fa3f00f829b0000008b'),
    bytes.fromhex('7424188a4c2404d3ee83e601740cc7431414000000e9800000008b431889442408a10000000085c0'),
    bytes.fromhex('74088138363249527408ff058c010000eb6069542404a40000008d7c10400fb60f83c70439ce734a'),
    bytes.fromhex('83fe1474458b2f85ed75064683c708ebeb807d350075f4894c240c31d289e8e8a2fbffff8b542408'),
    bytes.fromhex('29d083f8028b4c240c7ed8f6470601750a8b4520c1e8163c0276c8c7431404000000ff44240483c3'),
    bytes.fromhex('1c837c2404200f85f9fdffffa1987fbd008944241c85c0740731c0a3987fbd008d9c24c001000031'),
    bytes.fromhex('c08944241831ed8b43148944242883e00c8944240883f8040f8549030000ff05680100008b431889'),
    bytes.fromhex('44242c83c002894424048b0389442430a178c2e3008b7424302b8624010000894424388dbc24c001'),
    bytes.fromhex('000031c0894424148944240c89442420837f14020f85b60000008b078944243431c0894424108b44'),
    bytes.fromhex('24340fb6801c010000394424100f83950000008b4424348b7424108b34b085f67406807e3500740a'),
    bytes.fromhex('8b5424048b74240ceb6589f0e883faffff85c074eb66f74628001c74e3f646251c74ddf646240f74'),
    bytes.fromhex('d7ba0100000089f0e879faffff394424047dc53947188944243c7ebc89f1b880630e00ffd08b4c24'),
    bytes.fromhex('3829c183f90a7ea889f0e8b0faffff85c0759d8b442420894424148b54243cff4424108954240489'),
    bytes.fromhex('74240ce956ffffffff44242083c71c837c2420200f852effffff837c240c00750bff056c010000e9'),
    bytes.fromhex('23020000b803000000837c2404597f25b804000000837c2404517f19b805000000837c24044b7f0d'),
    bytes.fromhex('31c0837c2404460f9cc083c00689eac1e20689c1c1e1050fb68c0d94c0e30031f68974241039e975'),
    bytes.fromhex('0889d609c6897424104083f8087407837c24100074d48b4b088b530c8b43108b7304837c24100075'),
    bytes.fromhex('0bff0570010000e995000000c744244808000000896c244c8b7c2424897c2450894c245489542458'),
    bytes.fromhex('8944245c8b44240ce808faffff89442460bf40ee1400ba0600000089f1ffd789442464ba08000000'),
    bytes.fromhex('89f1ffd789442468b83352425131d23344944889c1c1e91031c869c06bcaeb8589c1c1e90d31c869'),
    bytes.fromhex('c035aeb2c289c1c1e91031c84283fa0975d5b9a086010031d2f7f181fab78800007611ff05740100'),
    bytes.fromhex('0031c089442408e9c100000031d28d44246c31ff893c904283fa0f75f1c744246c020000006b5424'),
    bytes.fromhex('141c8b9414c0010000895424748b7c240c897c24788b5424308994248c0000008b74241089b4249c'),
    bytes.fromhex('0000008d7c24408d7424446a005657b990ae2b00ffd185c07508ff0578010000eb5bb8010000006b'),
    bytes.fromhex('d03c83ba7cc2e3000074114083f80f75eeff057c010000e96dffffff8b44242883c8088943146b44'),
    bytes.fromhex('24141c838c04d401000008a1100000000b050000000083e0010f8424010000ff0580010000c74424'),
    bytes.fromhex('08020000008b4b088b430c8b531483e21083ca0856ff7424188b7c240c8b74243429f757ff74241c'),
    bytes.fromhex('8d34010373105629c850ff7304ff7424288b4c242889e8e8aef8ffff83c4204583c31c83fd200f85'),
    bytes.fromhex('93fcffff837c241c0074098b44241ca3987fbd008b9424640500008b8c2460050000b860c92b00ff'),
    bytes.fromhex('d08d9c24a800000031f6397424180f84f80000008b0b8b7b04833902752339790c751e55556a016a'),
    bytes.fromhex('0131d2b860b62b00ffd0ff05b4000000585ab907000000eb2f8b4b08b8504c0c00ffd00fb6881c01'),
    bytes.fromhex('000031d239ca734183fa41743c393c90740342ebefff0584010000b9010000008b430852ff730c6a'),
    bytes.fromhex('00ff73106a006a006a0057ba48000000e8edf7ffff4683c31483c420e971ffffffff058801000031'),
    bytes.fromhex('c9ebcd8d8a7cc2e3008b7c047089bc0280c2e30083c00483f83075ed66c782b0c2e3000000c7827c'),
    bytes.fromhex('c2e300020000006b442418148d8404a800000089088b74240c8970048968088b74241489700cff44'),
    bytes.fromhex('24188b7c2410897810ff05b0000000c744240801000000e981feffff81c44c0500005b5e5f5dc3'),
    b'\xcc' * 1401,
    bytes(256),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0004, True, 'page', 0x177),
    (0x00f2, False, 'room', 0x2e00),
    (0x0100, False, 'room', 0x2400),
    (0x010d, False, 'room', 0x2400),
    (0x016c, False, 'room', 0x2e00),
    (0x0172, False, 'room', 0x20dc),
    (0x0187, False, 'room', 0x21a0),
    (0x018d, False, 'room', 0x2000),
    (0x0199, False, 'room', 0x2004),
    (0x01a5, False, 'room', 0x2008),
    (0x01ae, False, 'room', 0x200c),
    (0x01c9, False, 'room', 0x21a4),
    (0x01f0, False, 'room', 0x21d0),
    (0x0201, False, 'room', 0x2e00),
    (0x0234, False, 'room', 0x2400),
    (0x023b, False, 'room', 0x2400),
    (0x0432, False, 'page', 0xf00),
    (0x0444, False, 'room', 0x21cc),
    (0x04f8, False, 'room', 0x21a8),
    (0x0613, False, 'room', 0x21ac),
    (0x0693, False, 'room', 0x21b0),
    (0x072d, False, 'room', 0x21b4),
    (0x079c, False, 'room', 0x21b8),
    (0x07bb, False, 'room', 0x21bc),
    (0x07dc, False, 'room', 0x2010),
    (0x07e2, False, 'page', 0xf04),
    (0x07f1, False, 'room', 0x21c0),
    (0x08a4, False, 'room', 0x20f4),
    (0x08d7, False, 'room', 0x21c4),
    (0x090b, False, 'room', 0x21c8),
    (0x096b, False, 'room', 0x20f0),
)

LABELS = {
    'trade_call': 0x17b,
    'trade_entry': 0x0,
}

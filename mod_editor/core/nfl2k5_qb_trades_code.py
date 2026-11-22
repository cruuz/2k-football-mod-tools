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
CODE_BYTES = 0xbb0

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
    bytes.fromhex('0046893500000000ff059c0000005b5e5f5dc35557565381ec6c050000ff0560010000813d000000'),
    bytes.fromhex('005142524f7536813d040000004f4d7631752a833d08000000017521f6050c000000107418833d18'),
    bytes.fromhex('29b70000740f833da476e500087411ff056401000031c08944242ce9aa080000a1b476e500894424'),
    bytes.fromhex('0c0fb605c55151003944240c7208ff0590010000ebd7a1b876e500894424408b350000000031d231'),
    bytes.fromhex('c0894424208944241c8d6eff39f20f838c00000081fa800000000f848000000089e829d083e07f6b'),
    bytes.fromhex('c0148d88000000000fb7800000000039442440755d0fb679028d47018b5c240c39d8724e8a410548'),
    bytes.fromhex('3c0177468a410488c383e30f885c24108a4903bb01000000d3e389d983e00f83e80583f802770609'),
    bytes.fromhex('5c241ceb1d807c2410030f94c031db397c240c0f94c389df21c7f7df21cf097c242042e96cffffff'),
    bytes.fromhex('8d9c24e001000031ed896c240c8b4c240cb8504c0c00ffd089c58903c743140100000031ff897b04'),
    bytes.fromhex('897b1885c00f84cf0100008b44240c833c855c77e500000f85bd01000089e8e893fdffff89442414'),
    bytes.fromhex('85c00f85aa0100000fb6851c0100008944241083f8410f87960100008d4485008944242489ef31f6'),
    bytes.fromhex('89742418397c242474418b3785f67436807e35007530ff44241489f0e8cbfcffff85c07421ba0100'),
    bytes.fromhex('000089f0e8d5fcffff837b040074053943187d06897304894318ff44241883c704ebb989e9b82077'),
    bytes.fromhex('0c00ffd089c689430889e9b850770c00ffd089c789430c89e9b880770c00ffd089c1894310837c24'),
    bytes.fromhex('14020f97c089c5837c2418020f97c221ea31c0837c2410320f97c021d001c08943148b44241083e8'),
    bytes.fromhex('3183f8030f97c2837c2418000f94c008d00f85d300000089e884c00f85c90000008d043e01c883f8'),
    bytes.fromhex('010f86bb0000004639fe0f82b20000008b44241c8b7c240c0fa3f80f82a10000008b431889442410'),
    bytes.fromhex('83f8540f8f910000008b7424208a4c240cd3ee83e6017409c7431414000000eb79a10000000085c0'),
    bytes.fromhex('74088138363249527408ff058c010000eb606954240ca40000008d7c10400fb60f83c70483fe1474'),
    bytes.fromhex('4939ce73458b2f85ed75064683c708ebeb807d350075f4894c241431d289e8e8a2fbffff8b542410'),
    bytes.fromhex('29d083f8028b4c24147ed8f6470601750a8b4520c1e8163c0276c8c7431404000000ff44240c83c3'),
    bytes.fromhex('1c837c240c200f85f9fdffffa1987fbd008944243085c0740831c9890d987fbd008dac24e0010000'),
    bytes.fromhex('31d28954242c895424148b45148944244483e00c8944241083f8040f8567050000ff05680100008b'),
    bytes.fromhex('45188944244883c0028944240c8b45008944244ca178c2e3008b7c244c2b8724010000894424208d'),
    bytes.fromhex('b424e001000031c08944241c8944241889442438837e14020f852c0100008b3e31c0894424348d87'),
    bytes.fromhex('1c010000894424540fb6871c010000394424340f83090100008b4424348b1c8785db7406807b3500'),
    bytes.fromhex('74118b44240c894424288b5c2418e9d200000089d8e87afaffff85c074e466f74328001c74dcf643'),
    bytes.fromhex('251c74d6f643240f74d0ba0100000089d8e870faffff894424283944240c7dba3946187eb589d9b8'),
    bytes.fromhex('80630e00ffd08b54242029c283fa0a7ea189d8e8a7faffff8944242485c075928b46048944245031'),
    bytes.fromhex('c08944243c8b4424540fb6003944242473488b4424248b0c8785c90f95c2394c24500f95c084c274'),
    bytes.fromhex('2b39cb742780793500752189c8e8e2f9ffff85c07416ba0100000089c8e8ecf9ffff3944243c7d04'),
    bytes.fromhex('8944243cff442424ebab837c243c3b0f8e25ffffff8b4424388944241cff4424348b442428894424'),
    bytes.fromhex('0c895c2418e9dcfeffffff44243883c61c837c2438200f85b8feffff837c241800750bff056c0100'),
    bytes.fromhex('00e9ca030000837c24200a7f0731c0e960010000c7442428ffff0000817c2420090001007f0b8b44'),
    bytes.fromhex('242083e80a89442428a11829b7008b58388b403c89442454b8603c0e0029d8c1e004894424588b7c'),
    bytes.fromhex('245831c08944242089442450894424388944243c8944243431f68d4364394424200f83c600000039'),
    bytes.fromhex('5c24207221f6470b030f84aa0000008b4708250000001c3d0000000c0f85970000008b0feb0b8b44'),
    bytes.fromhex('24548b5424208b0c9085c90f848000000080793500757aba01000000894c245cb8806d2400ffd0d9'),
    bytes.fromhex('5c24248b44242485c08b4c245c790631c0894424248b5424243954243c720485f67541506a006a01'),
    bytes.fromhex('6a0031d2894c246cb840d42b00ffd00fb7c05a8b4c242839c8732631d2395c24200f93c289542450'),
    bytes.fromhex('894424388b4424248944243c8b4c245c894c2434be01000000ff44242083c710e92dffffff85f60f'),
    bytes.fromhex('84c8feffff837c245000740d8b44243889442428e9f5feffff8b442434e81af8ffff85c074e6ba01'),
    bytes.fromhex('0000008b442434e822f8ffff3944240c7f13ff059401000031c08944241031dbe902020000b80200'),
    bytes.fromhex('0000837c240c5e7f31b803000000837c240c597f25b804000000837c240c517f19b805000000837c'),
    bytes.fromhex('240c4b7f0d31c0837c240c450f9ec083c00689c689f2c1e2058b7c24140fb6941794c0e30031db39'),
    bytes.fromhex('fa750789fbc1e30609f383fe01740f85db0f94c139c60f93c24e84d175ce8b4d088b550c8b45108b'),
    bytes.fromhex('7d0485db750bff0570010000e9a2000000c7442468080000008b7424148974246c8b742440897424'),
    bytes.fromhex('70894c2474895424788944247c8b442418e8f7f7ffff89842480000000be40ee1400ba0600000089'),
    bytes.fromhex('f9ffd689842484000000ba0800000089f9ffd689842488000000b83352425131d23344946889c1c1'),
    bytes.fromhex('e91031c869c06bcaeb8589c1c1e90d31c869c035aeb2c289c1c1e91031c84283fa0975d5b9a08601'),
    bytes.fromhex('0031d2f7f181fab78800007611ff057401000031c089442410e9c900000031d28d84248c00000031'),
    bytes.fromhex('ff893c904283fa0f75eec784248c000000020000006b54241c1c8b9414e001000089942494000000'),
    bytes.fromhex('8b74241889b424980000008b7c244c89bc24ac000000899c24bc0000008d7424608d7c24646a0057'),
    bytes.fromhex('56b990ae2b00ffd185c07508ff0578010000eb5bb8010000006bd03c83ba7cc2e3000074114083f8'),
    bytes.fromhex('0f75eeff057c010000e965ffffff8b44244483c8088945146b44241c1c838c04f401000008a11000'),
    bytes.fromhex('00000b050000000083e0010f8428010000ff0580010000c7442410020000008b4d088b450c8b5514'),
    bytes.fromhex('83e21083ca0856ff7424208b7424148b7c245029fe56538d1c01035d105329c850ff7504ff742434'),
    bytes.fromhex('8b4c24308b442434e88df6ffff83c420ff44241483c51c837c2414200f8570faffff837c24300074'),
    bytes.fromhex('098b442430a3987fbd008b9424840500008b8c2480050000b860c92b00ffd08d9c24c800000031f6'),
    bytes.fromhex('3974242c0f84fb0000008b0b8b7b04833902752339790c751e55556a016a0131d2b860b62b00ffd0'),
    bytes.fromhex('ff05b4000000585ab907000000eb2f8b4b08b8504c0c00ffd00fb6881c01000031d239ca734183fa'),
    bytes.fromhex('41743c393c90740342ebefff0584010000b9010000008b430852ff730c6a00ff73106a006a006a00'),
    bytes.fromhex('57ba48000000e8c7f5ffff4683c31483c420e971ffffffff058801000031c9ebcd8d8a7cc2e3008b'),
    bytes.fromhex('b4049000000089b40280c2e30083c00483f83075ea66c782b0c2e3000000c7827cc2e30002000000'),
    bytes.fromhex('6b44242c148d8404c800000089088b7424188970048b7c24148978088b74241c89700cff44242c89'),
    bytes.fromhex('5810ff05b0000000c744241001000000e97afeffff81c46c0500005b5e5f5dc3'),
    b'\xcc' * 848,
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
    (0x04fb, False, 'room', 0x21a8),
    (0x068d, False, 'room', 0x21ac),
    (0x080c, False, 'room', 0x21d4),
    (0x08a0, False, 'room', 0x21b0),
    (0x0947, False, 'room', 0x21b4),
    (0x09be, False, 'room', 0x21b8),
    (0x09dd, False, 'room', 0x21bc),
    (0x09fe, False, 'room', 0x2010),
    (0x0a04, False, 'page', 0xf04),
    (0x0a13, False, 'room', 0x21c0),
    (0x0aca, False, 'room', 0x20f4),
    (0x0afd, False, 'room', 0x21c4),
    (0x0b31, False, 'room', 0x21c8),
    (0x0b94, False, 'room', 0x20f0),
)

LABELS = {
    'trade_call': 0x17b,
    'trade_entry': 0x0,
}

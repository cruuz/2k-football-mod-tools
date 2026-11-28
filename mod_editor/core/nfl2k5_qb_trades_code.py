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
CODE_BYTES = 0xc13

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
    bytes.fromhex('0046893500000000ff059c0000005b5e5f5dc35557565381ec8c050000ff0560010000813d000000'),
    bytes.fromhex('005142524f7536813d040000004f4d7631752a833d08000000017521f6050c000000107418833d18'),
    bytes.fromhex('29b70000740f833da476e500087411ff056401000031c08944242ce90d090000a1b476e500894424'),
    bytes.fromhex('0c0fb605c55151003944240c7208ff0590010000ebd7a1b876e500894424408b350000000031d231'),
    bytes.fromhex('c0894424208944241c8d6eff39f20f838c00000081fa800000000f848000000089e829d083e07f6b'),
    bytes.fromhex('c0148d88000000000fb7800000000039442440755d0fb679028d47018b5c240c39d8724e8a410548'),
    bytes.fromhex('3c0177468a410488c383e30f885c24108a4903bb01000000d3e389d983e00f83e80583f802770609'),
    bytes.fromhex('5c241ceb1d807c2410030f94c031db397c240c0f94c389df21c7f7df21cf097c242042e96cffffff'),
    bytes.fromhex('8d9c240002000031ed896c240c8b4c240cb8504c0c00ffd089c58903c743140100000031ff897b04'),
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
    bytes.fromhex('1c837c240c200f85f9fdffffa1987fbd008944243085c0740831c9890d987fbd008dac2400020000'),
    bytes.fromhex('31d28954242c895424148b45148944244483e00c8944241083f8040f85ca050000ff05680100008b'),
    bytes.fromhex('45188944244883c0028944240c8b45008944244ca178c2e3008b7c244c2b8724010000894424208d'),
    bytes.fromhex('bc240002000031c08944241c8944241889442438837f14020f85890100008b078944242431c08944'),
    bytes.fromhex('24348b442424051c010000894424548b4424240fb6801c010000394424340f835b0100008b442424'),
    bytes.fromhex('8b7424348b1cb085db7406807b350074118b44240c894424288b5c2418e92001000089d8e86bfaff'),
    bytes.fromhex('ff85c074e466f74328001c74dcf643251c74d6f643240f74d0ba0100000089d8e861faffff894424'),
    bytes.fromhex('283944240c7dba3947187eb531c08b14038994049400000083c00483f85475ee0fb74b0ab8f05f0e'),
    bytes.fromhex('00ffd089c689d9b800ed1300ffd081a424b8000000ffff0fff29c689f1b800600e00ffd066898424'),
    bytes.fromhex('9e0000008d8c2494000000b880630e00ffd08b54242029c283fa0a0f8e50ffffff89d8e847faffff'),
    bytes.fromhex('89c685c00f853fffffff8b47048944245031c08944243c8b4424540fb60039c673458b4424248b0c'),
    bytes.fromhex('b085c90f95c2394c24500f95c084c2742b39cb742780793500752189c8e882f9ffff85c07416ba01'),
    bytes.fromhex('00000089c8e88cf9ffff3944243c7d048944243c46ebb0837c243c3b0f8ed7feffff8b4424388944'),
    bytes.fromhex('241cff4424348b4424288944240c895c2418e983feffffff44243883c71c837c2438200f855bfeff'),
    bytes.fromhex('ff837c241800750bff056c010000e9d0030000837c24200a7f0731c0e960010000c7442428ffff00'),
    bytes.fromhex('00817c2420090001007f0b8b44242083e80a89442428a11829b7008b58388b403c89442454b8603c'),
    bytes.fromhex('0e0029d8c1e004894424588b7c245831c08944242089442450894424388944243c8944243431f68d'),
    bytes.fromhex('4364394424200f83c6000000395c24207221f6470b030f84aa0000008b4708250000001c3d000000'),
    bytes.fromhex('0c0f85970000008b0feb0b8b4424548b5424208b0c9085c90f848000000080793500757aba010000'),
    bytes.fromhex('00894c245cb8806d2400ffd0d95c24248b44242485c08b4c245c790631c0894424248b5424243954'),
    bytes.fromhex('243c720485f67541506a006a016a0031d2894c246cb840d42b00ffd00fb7c05a8b54242839d07326'),
    bytes.fromhex('31d2395c24200f93c289542450894424388b4424248944243c8b4c245c894c2434be01000000ff44'),
    bytes.fromhex('242083c710e92dffffff85f60f84c8feffff837c245000740d8b44243889442428e9f5feffff8b44'),
    bytes.fromhex('2434e8bdf7ffff85c074e6ba010000008b442434e8c5f7ffff3944240c7f13ff059401000031c089'),
    bytes.fromhex('44241031dbe908020000b802000000837c240c5e7f31b803000000837c240c597f25b80400000083'),
    bytes.fromhex('7c240c517f19b805000000837c240c4b7f0d31c0837c240c450f9ec083c00689c689f2c1e2058b7c'),
    bytes.fromhex('24140fb6941794c0e30031db39fa750789fbc1e30609f383fe01740f85db0f94c139c60f93c24e84'),
    bytes.fromhex('d175ce8b4d088b550c8b45108b7d0485db750bff0570010000e9a8000000c7442470080000008b74'),
    bytes.fromhex('2414897424748b74244089742478894c247c89942480000000898424840000008b442418e894f7ff'),
    bytes.fromhex('ff89842488000000be40ee1400ba0600000089f9ffd68984248c000000ba0800000089f9ffd68984'),
    bytes.fromhex('2490000000b83352425131d23344947089c1c1e91031c869c06bcaeb8589c1c1e90d31c869c035ae'),
    bytes.fromhex('b2c289c1c1e91031c84283fa0975d5b9a086010031d2f7f181fab78800007611ff057401000031c0'),
    bytes.fromhex('89442410e9c900000031d28d84249400000031ff893c904283fa0f75eec784249400000002000000'),
    bytes.fromhex('6b54241c1c8b9414000200008994249c0000008b7c241889bc24a00000008b74244c89b424b40000'),
    bytes.fromhex('00899c24c40000008d7424688d7c246c6a005756b990ae2b00ffd185c07508ff0578010000eb5bb8'),
    bytes.fromhex('010000006bd03c83ba7cc2e3000074114083f80f75eeff057c010000e965ffffff8b44244483c808'),
    bytes.fromhex('8945146b44241c1c838c041402000008a1100000000b050000000083e0010f8428010000ff058001'),
    bytes.fromhex('0000c7442410020000008b4d088b450c8b551483e21083ca0856ff7424208b7424148b7c245029fe'),
    bytes.fromhex('56538d1c01035d105329c850ff7504ff7424348b4c24308b442434e82af6ffff83c420ff44241483'),
    bytes.fromhex('c51c837c2414200f850dfaffff837c24300074098b442430a3987fbd008b9424a40500008b8c24a0'),
    bytes.fromhex('050000b860c92b00ffd08d9c24e800000031f63974242c0f84fb0000008b0b8b7b04833902752339'),
    bytes.fromhex('790c751e55556a016a0131d2b860b62b00ffd0ff05b4000000585ab907000000eb2f8b4b08b8504c'),
    bytes.fromhex('0c00ffd00fb6881c01000031d283fa41744039ca733c393c90740342ebefff0584010000b9010000'),
    bytes.fromhex('008b430852ff730c6a00ff73106a006a006a0057ba48000000e864f5ffff4683c31483c420e971ff'),
    bytes.fromhex('ffffff058801000031c9ebcd8d8a7cc2e3008bb4049800000089b40280c2e30083c00483f83075ea'),
    bytes.fromhex('66c782b0c2e3000000c7827cc2e300020000006b44242c148d8404e800000089088b7c2418897804'),
    bytes.fromhex('8b7424148970088b7c241c89780cff44242c895810ff05b0000000c744241001000000e97afeffff'),
    bytes.fromhex('81c48c0500005b5e5f5dc3'),
    b'\xcc' * 749,
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
    (0x06ea, False, 'room', 0x21ac),
    (0x0869, False, 'room', 0x21d4),
    (0x08fd, False, 'room', 0x21b0),
    (0x09aa, False, 'room', 0x21b4),
    (0x0a21, False, 'room', 0x21b8),
    (0x0a40, False, 'room', 0x21bc),
    (0x0a61, False, 'room', 0x2010),
    (0x0a67, False, 'page', 0xf04),
    (0x0a76, False, 'room', 0x21c0),
    (0x0b2d, False, 'room', 0x20f4),
    (0x0b60, False, 'room', 0x21c4),
    (0x0b94, False, 'room', 0x21c8),
    (0x0bf7, False, 'room', 0x20f0),
)

LABELS = {
    'trade_call': 0x17b,
    'trade_entry': 0x0,
}

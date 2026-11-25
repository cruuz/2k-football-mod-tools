"""Relocatable pages of the CPU trades owner (beta 81, owner nfl2k5_cpu_trades): trades between computer clubs at every
position but QB, K and P, a player for a draft pick (tools/cpu_trades/trades.c says exactly which).

Two pages: code at 0x0000 (0xCC after the last byte of code up to 0x1200), the CPUTRDv1 settings record at +0x1200, the
counters at +0x1240 (u32 each, COUNTER_NAMES), the ring cursor at +0x1340 (events ever written; slot = n % 128) and the
ring at +0x1400 (128 events of RING_EVENT, 24 bytes). Only the settings record is non-zero in the file. One whole 5-byte
call enters the code: 0x2BC96C, the native trade pass 0x2BC960's call of its pending scan 0x2BC900. The template,
relocations and labels are generated from tools/cpu_trades by build.py; the pick word is in nfl2k5_trade_picks.
"""
from __future__ import annotations

import struct

PAGE_SIZE = 0x2000
CODE_LIMIT = 0x1200
SETTINGS_OFFSET = 0x1200
SETTINGS = struct.Struct("<8sIIIIII")            # magic, mode, stages, flags, p8_ppm, p7_ppm, reserved
MAGIC = b"CPUTRDv1"
COUNTERS_OFFSET = 0x1240
COUNTERS_LIMIT = 64
RING_CURSOR = 0x1340
RING_OFFSET = 0x1400
RING_COUNT = 128
# year, stage, week, buyer, seller, position, result, player index, pick word, rating, buyer's eff, q25, flags, draw,
# threshold
RING_EVENT = struct.Struct("<HBBBBBBHHBBBBII")
STAGE_SEASON, STAGE_PRESEASON, STAGE_REBUILD = 1, 2, 4
STAGE_MASK = 7
FLAG_SHADOW = 1
MODE_REALISTIC = 1
HOOK = (0x2BC96C, bytes.fromhex("e88fffffff"), "trade_entry")      # call 0x2BC900 (retail and every b81 build)
PENDING_SCAN = 0x2BC900
DECISION = 9
RESULT_KEPT, RESULT_POSTED, RESULT_WOULD, RESULT_NO_PICK = 0, 1, 2, 3
RESULT_REFUSED, RESULT_NO_SLOT, RESULT_CAPPED, RESULT_CANCELLED = 4, 5, 6, 7
RESULT_EXECUTED, RESULT_GONE = 1, 0                # rows written after the pending scan (flag F_AFTER)
F_REBUILD, F_OWN_PICK, F_AFTER = 1, 2, 0x40
MAX_POSTS = 6
LOAD_LIMIT = 3
POSITION_NAMES = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")


def _whole(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"The CPU trades {name} must be a whole number from {low} to {high}")
    return value


def settings_record(stages: int, *, shadow: bool = False, p8_ppm: int, p7_ppm: int) -> bytes:
    """The 32-byte settings record (mode 1 = realistic)."""
    _whole(stages, 1, STAGE_MASK, "stage set")
    _whole(p8_ppm, 0, 1_000_000, "in-season chance")
    _whole(p7_ppm, 0, 1_000_000, "preseason chance")
    if type(shadow) is not bool:
        raise ValueError("The CPU trades shadow flag must be True or False")
    return SETTINGS.pack(MAGIC, MODE_REALISTIC, stages, FLAG_SHADOW if shadow else 0, p8_ppm, p7_ppm, 0)


def parse_settings(record: bytes) -> dict:
    magic, mode, stages, flags, p8, p7, reserved = SETTINGS.unpack(bytes(record[:SETTINGS.size]))
    if magic != MAGIC or mode != MODE_REALISTIC or not 1 <= stages <= STAGE_MASK or flags not in (0, FLAG_SHADOW) \
            or reserved or p8 > 1_000_000 or p7 > 1_000_000:
        raise ValueError("Unknown CPU trades settings record")
    return {"stages": stages, "shadow": bool(flags & FLAG_SHADOW), "p8_ppm": p8, "p7_ppm": p7}


def counters(page: bytes) -> dict:
    """The counters of a page image (RAM or file) by name."""
    return {name: struct.unpack_from("<I", page, COUNTERS_OFFSET + 4 * k)[0] for k, name in enumerate(COUNTER_NAMES)}


def events(page: bytes, since: int = 0) -> list:
    """Ring rows written from event number `since` to the cursor (at most the last RING_COUNT), as dicts."""
    cursor = struct.unpack_from("<I", page, RING_CURSOR)[0]
    names = ("year", "stage", "week", "buyer", "seller", "position", "result", "player", "word", "rating", "eff",
             "q25", "flags", "draw", "threshold")
    return [dict(zip(names, RING_EVENT.unpack_from(page, RING_OFFSET + RING_EVENT.size * (n % RING_COUNT))), n=n)
            for n in range(max(since, cursor - RING_COUNT), cursor)]


def _set32(page, offset, value):
    struct.pack_into("<I", page, offset, value & 0xFFFFFFFF)


def page_bytes(va: int, settings: bytes) -> bytes:
    """The whole 0x2000-byte image linked for `va` with the 32-byte settings record in place."""
    _whole(va, 0x1000, 0xFFFFFFFF - PAGE_SIZE + 1, "page address")
    if va % 0x1000:
        raise ValueError("The CPU trades page address must be on a page boundary")
    parse_settings(settings)
    page = bytearray(_TEMPLATE)
    for offset, relative, family, addend in _RELOCATIONS:
        target = {"page": va, "stock": 0}[family] + addend
        _set32(page, offset, target - (va + offset) if relative else target)
    page[SETTINGS_OFFSET:SETTINGS_OFFSET + SETTINGS.size] = settings
    return bytes(page)


def site(va: int) -> tuple[int, bytes, bytes]:
    """(site, retail call, installed call)."""
    at, original, label = HOOK
    return at, original, b"\xe8" + struct.pack("<I", (va + LABELS[label] - at - 5) & 0xFFFFFFFF)


# Generated from tools/cpu_trades by build.py.
CODE_BYTES = 0xf49
COUNTER_NAMES = ('calls', 'bad_settings', 'inactive', 'past_deadline', 'ticks', 'needs', 'load_out', 'no_package', 'rebuild_packages', 'no_pick', 'kept', 'capped', 'refused', 'no_slot', 'shadow', 'posted', 'executed', 'cancelled', 'gone', 'events_logged')

_TEMPLATE = b''.join((
    bytes.fromhex('fcff742404e8fcffffff83c404c204008b502081e20000c0bf750f8b4024a9000000700f94c00fb6'),
    bytes.fromhex('c0c331c0c35383ec1889c131d2b8806d2400ffd0d95c240c8b54240c89d0c1e8173c76763c85d278'),
    bytes.fromhex('380fb6d8b8640000000fbae21e722c81e2ffff7f0081ca000080006bd264b99500000029d9b80100'),
    bytes.fromhex('0000d3e001d0b99600000029d9d3e8eb0231c083c4185bc35557565383ec0889c689d3894c24048b'),
    bytes.fromhex('0d0000000089c883e07f8904248b2db876e5006bf8186689af0000000089f28897020000008b35b4'),
    bytes.fromhex('76e50089f2889703000000889f040000008a5c2404889f050000008b54241c8897060000008b5424'),
    bytes.fromhex('20889707000000b8ffff0000837c2424007417a11829b7008b50048b44242429d0bb5400000031d2'),
    bytes.fromhex('f7f36b142418668982080000008b4424286689820a0000008b44242c88820c0000008b4424308882'),
    bytes.fromhex('0d0000008b44243488820e0000008b44243888820f0000008d82100000008b5c243c899a10000000'),
    bytes.fromhex('8b54244089500441890d00000000a14c00000040a34c00000083c4085b5e5f5dc35557565381ec1c'),
    bytes.fromhex('0500008944247c89542414a11829b70089442418a1b876e50089442458a1b476e5008944242c837c'),
    bytes.fromhex('2418000f84bb0b0000a11000000040a3100000008b4424188b401c894424108d9c241001000031ed'),
    bytes.fromhex('89e9b8504c0c00ffd089c68903c6430a00c6430900c6430800c6430700c6430600c6430500c64304'),
    bytes.fromhex('00c6430bff31c0c644030c004083f81175f585f60f846a0100008a861c0100003c410f875c010000'),
    bytes.fromhex('0fb6861c0100008843068d9424cc0000008d8c24ff000000c6420200c6420100c6020083c20339ca'),
    bytes.fromhex('75ee31d28954240c8944241c8b7c241c397c240c0f83bf0000008b44240c8d04868b3885ff0f84a5'),
    bytes.fromhex('0000000fb64f35894c241880f9100f879400000089f8e892fdffff89c10fb6430739c87303884b07'),
    bytes.fromhex('89f8e861fdffff85c074756b7c2418038a943ccc0000008a843ccd000000884424080fb6c239c872'),
    bytes.fromhex('1c0fb654240839ca72290fb6843cce00000039c87342b802000000eb268a44240888843cce000000'),
    bytes.fromhex('88943ccd00000031c0eb108a44240888843cce000000b8010000006b542418038dba100500008d14'),
    bytes.fromhex('3c888c10bcfbffffff44240ce933ffffff31d20fb682380f000084c074138d0c528db9100500008d'),
    bytes.fromhex('0c3c8a8408bbfbffff8844130c4283fa1175d88b04ad5c77e50085c07526b87cc2e3008b1083fa01'),
    bytes.fromhex('760e8b500839d674138b502039d6740c83c03c3d00c6e30075e1eb04c64304014583c32083fd200f'),
    bytes.fromhex('8543feffff8b3d6cf0e30081ff570200000f879500000031f631db8d041fb95802000031d2f7f16b'),
    bytes.fromhex('d20c8baa70f0e3008b8a78f0e30089e883e01f83f807740431f6eb5b8b44241039c1722a29c1894c'),
    bytes.fromhex('240889c8b9f401000031d2f7f185d27515817c24087f3e0000770bba0100000088c1d3e209d685ed'),
    bytes.fromhex('79258d94241001000031c00fa3c6730c8a4a0580f9ff740441884a054083c22083f82075e6eba143'),
    bytes.fromhex('81fb580200000f856fffffff8d8424cc0000008dbc2410010000897c24088b7c240831f68a4f0c89'),
    bytes.fromhex('f285d274198d6aff8a9c148f00000038d9730b889c2c9100000089eaebe3888c14900000004683c7'),
    bytes.fromhex('2083fe2075ce8a94249800000088108a9424a00000008850018a9424a80000008850028a9424ac00'),
    bytes.fromhex('000088500383c004ff4424088db4241001000039f0758f8d842410050000894424088d9c24100100'),
    bytes.fromhex('008b7304f7c6010000000f85fe000000807b05027610a11800000040a318000000e9e8000000837c'),
    bytes.fromhex('24140875268b3b89f9b820770c00ffd088430889f9b850770c00ffd088430989f9b880770c00ffd0'),
    bytes.fromhex('88430a8a530680fa32765b89f083c804884304837c241408740b80fa400f879b000000eb55a10c00'),
    bytes.fromhex('0000a8040f84140800000fb643080fb67b098d0c3889cd0fb64b0a01cd83fd030f8ef807000083c0'),
    bytes.fromhex('0239c70f8eed07000089f083c80c884304e9e0070000837c241408750d0fb64308400fb6530939d0'),
    bytes.fromhex('7c4431c931f680b9380f000000741c0fb6540b0c0fb6848ccc00000038c2730b29d039c67305884b'),
    bytes.fromhex('0b89c64183f91175d5807b0bff740f804b0402a11400000040a31400000083c3208b44240839c30f'),
    bytes.fromhex('85e4feffff837c2414087525a1140000008b54242c83fa087605ba080000000fb692180f0000d1e8'),
    bytes.fromhex('0fafd08954243ceb09a1180000008944243c69542458830000006b44242c0701c28b44241401c289'),
    bytes.fromhex('d0c1e81031d069c06bcaeb8589c2c1ea0d31d069c035aeb2c289c2c1ea1031d08944247431c08944'),
    bytes.fromhex('244489442454894424188b4424748b7c244401f883e01f89442408c1e0058db8100500008d143c8a'),
    bytes.fromhex('8c0414010000884c245283e11280f9020f85b70600000fb6ac041b0100000fb684accc0000008944'),
    bytes.fromhex('24280fb684150cfcffff8944244883c003894424408b7c242839f87304897c24408b1578c2e3008b'),
    bytes.fromhex('442408c1e0058b8404100100008944244c8b802401000029c2895424708d84accc00000089442424'),
    bytes.fromhex('8d45f68944245cc744246c0b00000083f8017604896c246c8dbc241001000031c089442430894424'),
    bytes.fromhex('1089442438894424208944240c8b742430397424080f842b0200008a47048844245383e0143c040f'),
    bytes.fromhex('85190200008b078944241c31db31c931f60fb6470639c373388b44241c8d04988b1085d274280fb6'),
    bytes.fromhex('423539c575104189d0e882f8ffff83f80183deffeb10837c245c01770983e80a83f80283d10043eb'),
    bytes.fromhex('c00fb695380f00004239d60f82bd0100008b74246c0fb696240f00004239d10f82a90100008b7424'),
    bytes.fromhex('1c8d0486894424788b4424108944246431f689742468897424348b7424783974241c0f8452010000'),
    bytes.fromhex('8b44241c8b1885db0f843a0100000fb6433539c50f852e01000089d8e8f7f7ffff85c00f841f0100'),
    bytes.fromhex('008a4325884424608a4324f64424601e0f840a010000a80f0f84020100008a532731d0a80f0f84f5'),
    bytes.fromhex('0000008a4353a8010f85ea00000089d8e8d0f7ffff89c68b44244039c60f82d5000000397424640f'),
    bytes.fromhex('83cb0000000fb6470739c60f83bf0000008a44246083e01f8b4c24240fb6510339d672083c060f86'),
    bytes.fromhex('a40000000fb64c2f0c894c246039ce7213f6442453080f848c0000003c050f868400000089d9b880'),
    bytes.fromhex('630e00ffd08b54247029c283fa0a7e70ba7cc2e300b80c0000008b0a83f830741a85c974168d48e8'),
    bytes.fromhex('83f90b76098d0c108b0939cb744a83c004ebdf83c23c81fa00c6e30075cfb870f0e300ba82000000'),
    bytes.fromhex('8b080fa3ca73078b480439cb742283c00c3d900ce40075e88b44246039c60f93c00fb6c089442468'),
    bytes.fromhex('89742464895c24348344241c04e9a0feffff837c24340074258b442434e8d3f6ffff894424108b44'),
    bytes.fromhex('2468894424388b442430894424208b4424348944240cff44243083c720837c2430200f85b5fdffff'),
    bytes.fromhex('837c240c007510a11c00000040a31c000000e9be030000837c243800740ba12000000040a3200000'),
    bytes.fromhex('008b4424240fb64003bb020000003944241073358b4424240fb64002bb030000003944241073228b'),
    bytes.fromhex('4424240fb64001bb0400000039442410730f8b7424283974241019dbf7d383c3068b44240c8a4025'),
    bytes.fromhex('83e01f3c0983dbff8b44240c8a402483e00ffec875014383fb077605bb0700000089dac1e20581c2'),
    bytes.fromhex('94c0e3008d73fe8b44240801d00fb6003944240875138b442408c1e00609c3c744242401000000eb'),
    bytes.fromhex('3531c08d0c020fb609394c24087507c1e00609c3eb1a4083f82075e74b741183ea2039de75b931db'),
    bytes.fromhex('895c242431dbeb0631c9894c2424c7842490000000090000008b4424088984249400000089ac2498'),
    bytes.fromhex('0000008b4424588984249c0000008b442414898424a00000008b44242c898424a4000000a11829b7'),
    bytes.fromhex('008b50048b44240c29d0b95400000031d2f7f1898424a80000008b442408c1e0050fb69404180100'),
    bytes.fromhex('00899424ac0000000fb6840419010000898424b000000031d2b8545450433384949000000089c1c1'),
    bytes.fromhex('e91031c869c06bcaeb8589c1c1e90d31c869c035aeb2c289c1c1e91031c84283fa0975d2be40420f'),
    bytes.fromhex('0031d2f7f68954243085db7515a12400000040a324000000ba03000000e9bd0100008b74243c3974'),
    bytes.fromhex('24307212a12800000040a32800000031d2e9a1010000837c2454057615a12c00000040a32c000000'),
    bytes.fromhex('ba06000000e98501000031c031d2899484900000004083f80f75f1c7842490000000020000008b44'),
    bytes.fromhex('2420c1e0058b840410010000898424980000008b44240c8984249c0000008b44244c898424b00000'),
    bytes.fromhex('00899c24c0000000c744241c010000006b44241c3c8b807cc2e30085c0740bff44241c837c241c0f'),
    bytes.fromhex('75e68d8424900000008dbc24880000008db4248c0000006a005657b990ae2b00ffd185c07515a130'),
    bytes.fromhex('00000040a330000000ba04000000e9dc000000837c241c0f7515a13400000040a334000000ba0500'),
    bytes.fromhex('0000e9c00000008b442408c1e0058a54245283ca10889404140100008b442420c1e005808c041401'),
    bytes.fromhex('000010ff442454a11000000083e0017412a13800000040a338000000ba02000000eb7c6b74241c3c'),
    bytes.fromhex('8d967cc2e3008dbe80c2e300897c241c8b7c241c8d0c078bbc0494000000893983c00483f83075e8'),
    bytes.fromhex('66c786b0c2e3000000c7867cc2e300020000006b442418188b74247c01f089108b74240c8970048b'),
    bytes.fromhex('7424088970088b74242089700c895810896814ff442418a13c00000040a33c000000ba0100000050'),
    bytes.fromhex('50ff742444ff74243c8b44243401c08b74244809f050ff74243cff742460ff74242c53ff74243052'),
    bytes.fromhex('558b4c24508b5424388b442444e836f3ffff83c430ff442444837c2444200f8506f9ffffeb0e80fa'),
    bytes.fromhex('340f861ef8ffffe96af8ffff8b44241881c41c0500005b5e5f5dc35557565381ecac000000a1a476'),
    bytes.fromhex('e5008944240ca10000000040a300000000a1000000003d435055547514a1040000003d5244763175'),
    bytes.fromhex('08a10800000048740da10400000040a304000000eb62837c240c08752ea10c000000a80174478b15'),
    bytes.fromhex('b476e5000fb605c551510039c2720da10c00000040a30c000000eb34ba08000000eb15837c240c07'),
    bytes.fromhex('751ba10c000000a8027412ba070000008d442410e860f3ffff89c6eb0da10800000040a308000000'),
    bytes.fromhex('31f683ec0cffb424cc000000b800c92b00ffd08d5c241c83c40c31ff39fe0f84b10000008b0b8b01'),
    bytes.fromhex('8b6b0483f802752a8b410c39e8752350506a016a0131d2b860b62b00ffd0a14400000040a3440000'),
    bytes.fromhex('005a59b807000000eb3a8b4b08b8504c0c00ffd089c231c00fb68a1c01000083f841745239c8734e'),
    bytes.fromhex('8d0c828b0939e9740340ebe4a14000000040a340000000b8010000008b4b0c8b530883ec086a006a'),
    bytes.fromhex('006a406a006a006a00ff73105550ff73148b44243ce89ef1ffff4783c31883c430e956ffffffa148'),
    bytes.fromhex('00000040a34800000031c0ebbf81c4ac0000005b5e5f5dc301010101020202040800000002010105'),
    bytes.fromhex('050202030003000502030303040000000000000302010101010102020102020202'),
    b'\xcc' * 695,
    bytes(3584),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0006, True, 'page', 0xd87),
    (0x00a1, False, 'page', 0x1340),
    (0x00b9, False, 'page', 0x1400),
    (0x00c1, False, 'page', 0x1402),
    (0x00cf, False, 'page', 0x1403),
    (0x00d5, False, 'page', 0x1404),
    (0x00df, False, 'page', 0x1405),
    (0x00e9, False, 'page', 0x1406),
    (0x00f3, False, 'page', 0x1407),
    (0x0121, False, 'page', 0x1408),
    (0x012c, False, 'page', 0x140a),
    (0x0136, False, 'page', 0x140c),
    (0x0140, False, 'page', 0x140d),
    (0x014a, False, 'page', 0x140e),
    (0x0154, False, 'page', 0x140f),
    (0x015a, False, 'page', 0x1410),
    (0x0164, False, 'page', 0x1410),
    (0x0172, False, 'page', 0x1340),
    (0x0177, False, 'page', 0x128c),
    (0x017d, False, 'page', 0x128c),
    (0x01c2, False, 'page', 0x1250),
    (0x01c8, False, 'page', 0x1250),
    (0x0336, False, 'page', 0xf38),
    (0x04ef, False, 'page', 0x1258),
    (0x04f5, False, 'page', 0x1258),
    (0x054e, False, 'page', 0x120c),
    (0x05a8, False, 'page', 0xf38),
    (0x05dc, False, 'page', 0x1254),
    (0x05e2, False, 'page', 0x1254),
    (0x05fd, False, 'page', 0x1214),
    (0x0612, False, 'page', 0xf18),
    (0x0622, False, 'page', 0x1218),
    (0x07ac, False, 'page', 0xf38),
    (0x07c0, False, 'page', 0xf24),
    (0x0990, False, 'page', 0x125c),
    (0x0996, False, 'page', 0x125c),
    (0x09a7, False, 'page', 0x1260),
    (0x09ad, False, 'page', 0x1260),
    (0x0b4e, False, 'page', 0x1264),
    (0x0b54, False, 'page', 0x1264),
    (0x0b6d, False, 'page', 0x1268),
    (0x0b73, False, 'page', 0x1268),
    (0x0b86, False, 'page', 0x126c),
    (0x0b8c, False, 'page', 0x126c),
    (0x0c2f, False, 'page', 0x1270),
    (0x0c35, False, 'page', 0x1270),
    (0x0c4b, False, 'page', 0x1274),
    (0x0c51, False, 'page', 0x1274),
    (0x0c88, False, 'page', 0x1210),
    (0x0c92, False, 'page', 0x1278),
    (0x0c98, False, 'page', 0x1278),
    (0x0d10, False, 'page', 0x127c),
    (0x0d16, False, 'page', 0x127c),
    (0x0d9f, False, 'page', 0x1240),
    (0x0da5, False, 'page', 0x1240),
    (0x0daa, False, 'page', 0x1200),
    (0x0db6, False, 'page', 0x1204),
    (0x0dc2, False, 'page', 0x1208),
    (0x0dca, False, 'page', 0x1244),
    (0x0dd0, False, 'page', 0x1244),
    (0x0dde, False, 'page', 0x120c),
    (0x0df8, False, 'page', 0x124c),
    (0x0dfe, False, 'page', 0x124c),
    (0x0e13, False, 'page', 0x120c),
    (0x0e2e, False, 'page', 0x1248),
    (0x0e34, False, 'page', 0x1248),
    (0x0e7f, False, 'page', 0x1284),
    (0x0e85, False, 'page', 0x1284),
    (0x0ebd, False, 'page', 0x1280),
    (0x0ec3, False, 'page', 0x1280),
    (0x0eff, False, 'page', 0x1288),
    (0x0f05, False, 'page', 0x1288),
)

LABELS = {
    'trade_call': 0xd8b,
    'trade_entry': 0x0,
}

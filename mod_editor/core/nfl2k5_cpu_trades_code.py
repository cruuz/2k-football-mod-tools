"""Relocatable pages of the CPU trades owner (beta 81, owner nfl2k5_cpu_trades): trades between computer clubs at every
position but QB, K and P, a player for a draft pick (tools/cpu_trades/trades.c says exactly which).

Two pages: code at 0x0000 (0xCC after the last byte of code up to 0x1B00), the CPUTRDv1 settings record at +0x1B00, the
counters at +0x1B20 (u32 each, COUNTER_NAMES, at most 48), the ring cursor at +0x1BE0 (events ever written; slot = n % 64),
six words at +0x1BE4 (our records during a pending scan) and the ring at +0x1C00 (64 events of RING_EVENT, 16 bytes). Only the
settings record is non-zero in the file. Two whole 5-byte calls enter the code: 0x2BC96C, the native trade pass 0x2BC960's
call of its pending scan 0x2BC900, and 0x2BB296, the trade story writer's value line (HOOKS). The template,
relocations and labels are generated from tools/cpu_trades by build.py; the pick word is in nfl2k5_trade_picks.
"""
from __future__ import annotations

import struct

PAGE_SIZE = 0x2000
CODE_LIMIT = 0x1B00
SETTINGS_OFFSET = 0x1B00
SETTINGS = struct.Struct("<8sIIIIII")            # magic, mode, stages, flags, p8_ppm, p7_ppm, reserved
MAGIC = b"CPUTRDv1"
COUNTERS_OFFSET = 0x1B20
COUNTERS_LIMIT = 48
RING_CURSOR = 0x1BE0
CURRENT = 0x1BE4                                 # six words: the records of ours during a pending scan (RAM only)
RING_OFFSET = 0x1C00
RING_COUNT = 64
# year, stage, week, buyer, seller, pool, result, player index, pick word, rating, buyer's percentile, q25, flags
RING_EVENT = struct.Struct("<HBBBBBBHHBBBB")
STAGE_SEASON, STAGE_PRESEASON, STAGE_REBUILD = 1, 2, 4
STAGE_MASK = 7
FLAG_SHADOW = 1
MODE_REALISTIC = 1
# (site, retail bytes, label): the pending-scan call of the native trade pass, and the story writer's value line (S7)
HOOKS = ((0x2BC96C, bytes.fromhex("e88fffffff"), "trade_entry"),         # call 0x2BC900 (retail and every b81 build)
         (0x2BB296, bytes.fromhex("3de8030000"), "story_entry"))         # cmp eax, 0x3e8 in 0x2BB200
HOOK = HOOKS[0]
PENDING_SCAN = 0x2BC900
DECISION = 9
RESULT_KEPT, RESULT_POSTED, RESULT_WOULD, RESULT_NO_PICK = 0, 1, 2, 3
RESULT_REFUSED, RESULT_NO_SLOT, RESULT_CAPPED, RESULT_CANCELLED, RESULT_NO_RELEASE = 4, 5, 6, 7, 8
RESULT_EXECUTED, RESULT_GONE = 1, 0                # rows written after the pending scan (flag F_AFTER)
F_REBUILD, F_RELEASE, F_DEPTH, F_ROUND2, F_AFTER = 1, 2, 4, 8, 0x40
MAX_POSTS = 6
LOAD_LIMIT = 3
PICKS_PAID_LIMIT = 3
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
    names = ("year", "stage", "week", "buyer", "seller", "position", "result", "player", "word", "rating", "pct",
             "q25", "flags")
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


def sites(va: int) -> list[tuple[int, bytes, bytes]]:
    """[(site, retail bytes, installed call)] for both entries."""
    return [(at, original, b"\xe8" + struct.pack("<I", (va + LABELS[label] - at - 5) & 0xFFFFFFFF))
            for at, original, label in HOOKS]


def site(va: int) -> tuple[int, bytes, bytes]:
    """(site, retail call, installed call) of the trade pass entry."""
    return sites(va)[0]


# Generated from tools/cpu_trades by build.py.
CODE_BYTES = 0x19f9
COUNTER_NAMES = ('calls', 'bad_settings', 'inactive', 'past_deadline', 'opening_preseason', 'rounds', 'buyers', 'out_load', 'out_race', 'out_picks', 'out_quarterbacks', 'no_need', 'no_package', 'rej_health', 'rej_contract', 'rej_protected', 'rej_starter', 'rej_depth', 'rej_floor', 'rej_cap', 'rej_ledger', 'rebuild_packages', 'depth_packages', 'no_release', 'releases', 'no_pick', 'kept', 'capped', 'refused', 'no_slot', 'shadow', 'posted', 'executed', 'cancelled', 'gone', 'events_logged', 'second_rounds', 'rows_repaired', 'stories_forced')

_TEMPLATE = b''.join((
    bytes.fromhex('fcff742404e8fcffffff83c404c2040050515255e8fcffffff83c40485c05a595875063de8030000'),
    bytes.fromhex('c381fce8030000c3f7402400000070750f8b4020c1e8163c020f96c00fb6c0c331c0c35383ec1889'),
    bytes.fromhex('c131d2b8806d2400ffd0d95c240c8b54240c89d3c1eb1785d2783d0fb6db83fb767635b864000000'),
    bytes.fromhex('0fbae21e722c81e2ffff7f0081ca000080006bd264b99500000029d9b801000000d3e001d0b99600'),
    bytes.fromhex('000029d9d3e8eb0231c083c4185bc30fb6503580fa1077080fb682e8190000c3b8ff000000c353b9'),
    bytes.fromhex('7cc2e300ba0c0000008b1983fa30741a85db74168d5ae883fb0b76098d1c0a8b1b39c3741483c204'),
    bytes.fromhex('ebdf83c13c81f900c6e30075cf31c0eb05b8010000005bc3565389c3ba70f0e300be820000008b0a'),
    bytes.fromhex('89f0d3e883e00174078b4a0439d9740d83c20c81fa900ce40075e331c05b5ec35557565383ec1089'),
    bytes.fromhex('c789d189d0e865ffffff8a971c0100003dff0000000f84be00000089c689c8e8ccfeffff85c00f84'),
    bytes.fromhex('af0000000fb6c28944240831c0c74424044100000083f84174188b5c240839d873108d14878b1239'),
    bytes.fromhex('ca75048944240440ebe3668b412866c1e80a83e0078944240c31db31c08904248b44240839c3734f'),
    bytes.fromhex('83fb41744a8d049f8b2839e9743e85ed743a89e8e8defeffff39f0752f89e8e854feffff85c07424'),
    bytes.fromhex('668b452866c1e80a83e0078b54240c39d0720e8b54240439d373093944240c7503ff042443eba90f'),
    bytes.fromhex('b686d41900003904240f92c00fb6c0eb0231c083c4105b5e5f5dc3565389c18a5835668b402825ff'),
    bytes.fromhex('e3000089d6c1e60a09f080fb107730be18ec01000fa3de732625ff1f0000bb0040000085d2741631'),
    bytes.fromhex('db83fa01740fbb0020000083fa02740589d3c1e30d09d8668941285b5ec35557565383ec0889c689'),
    bytes.fromhex('d3894c24048b0d0000000089c883e03f8904248b2db876e50089c7c1e7046689af0000000089f288'),
    bytes.fromhex('97020000008b35b476e50089f2889703000000889f040000008a5c2404889f050000008b54241c88'),
    bytes.fromhex('97060000008b542420889707000000b8ffff0000837c2424007417a11829b7008b50048b44242429'),
    bytes.fromhex('d0bb5400000031d2f7f38b1424c1e204668982080000008b4424286689820a0000008b44242c8882'),
    bytes.fromhex('0c0000008b44243088820d0000008b44243488820e0000008b44243888820f00000041890d000000'),
    bytes.fromhex('00a18c00000040a38c00000083c4085b5e5f5dc35557565381ecec09000089842494000000895424'),
    bytes.fromhex('08898c2480000000a11829b70089442418a1b876e5008944246ca1b476e50089442430837c241800'),
    bytes.fromhex('0f849c110000a11400000040a3140000008b4424188b401c894424188d9c246001000031ed89e9b8'),
    bytes.fromhex('504c0c00ffd0894424048903c6430c00c6430b00c6430a00c6430900c6430800c6430700c6430600'),
    bytes.fromhex('c6430500c64304006bc54431d2c684049201000000c684047001000000424083fa1175e9837c2404'),
    bytes.fromhex('00740e8b4424048a801c0100003c417609c6430401e9330200008b4424040fb6801c010000884306'),
    bytes.fromhex('31d2c644133200c68414b7000000004283fa1175ed31d289542410894424286bc5448944242c8b7c'),
    bytes.fromhex('2428397c24100f83490100008b4424048b7c24108d04b88b3885ff0f842b01000089f8e827fcffff'),
    bytes.fromhex('89c63dff0000000f841701000089f8e8affbffff894424140fb643078b4c241439c873078a442414'),
    bytes.fromhex('88430785f67515f747200000c0bf750cf74724000000707503fe430c89f8e85dfbffff85c00f84d1'),
    bytes.fromhex('0000008b44242c05e009000001e0fe8406b2f7ffff668b472866c1e80a83e007668944241c0fb684'),
    bytes.fromhex('34b70000008844240c894424248d04b500000000894424208dbc04c800000031c08b4c242439c873'),
    bytes.fromhex('0e0fb61407663954241c720340ebea83f80474700fb64c240c80f9037605b9030000008b7c242001'),
    bytes.fromhex('f989cf8b54242029d739f8731f8a940cc700000088940cc80000008a940c0b01000088940c0c0100'),
    bytes.fromhex('0049ebd58d94b4e009000001c28a44241c8882e8f6ffff8a44241488822cf7ffff807c240c03770c'),
    bytes.fromhex('8a44240c40888434b7000000ff442410e9a9feffff8d8c240c01000031d20fb6b2c019000089f031'),
    bytes.fromhex('ff85f6742b388414b700000072228d040e8944240c89cfb8ff0000000fb63739c6730289f0478b74'),
    bytes.fromhex('240c39f775ee89c789f8884413104283c10483fa1175b78b04ad5c77e50085c0752ab87cc2e3008b'),
    bytes.fromhex('1083fa0176128b50083954240474158b502039542404740c83c03c3d00c6e30075ddeb04c6430401'),
    bytes.fromhex('8d85b4c0e3008d8d94c1e3000fb61039ea7403fe430b83c02039c875ef4583c34483fd200f8553fd'),
    bytes.fromhex('ffff8b3d6cf0e30081ff570200000f879500000031f631db8d041fb95802000031d2f7f16bd20c8b'),
    bytes.fromhex('aa70f0e3008b8a78f0e30089e883e01f83f807740431f6eb5b8b44241839c1722a29c1894c240489'),
    bytes.fromhex('c8b9f401000031d2f7f185d27515817c24047f3e0000770bba0100000088c1d3e209d685ed79258d'),
    bytes.fromhex('94246001000031c00fa3c6730c8a4a0580f9ff740441884a054083c24483f82075e6eba14381fb58'),
    bytes.fromhex('0200000f856fffffff8d8424c80000008dac246001000031f689e931d2c64121004283c14483fa20'),
    bytes.fromhex('75f3c6400300c6400200c6400100c6000080bec019000000751f4683c0044583fe1175cd8d842460'),
    bytes.fromhex('0100008dbc24e009000089c3e9c600000089ef31c98a5f10885c240489ca4185d274218d5aff895c'),
    bytes.fromhex('240c8a9c140b010000385c2404730d8b54240c889c140d010000ebdb8a5c2404889c140c01000083'),
    bytes.fromhex('c74483f92075be8a94241401000088108a94241c0100008850018a9424240100008850028a942428'),
    bytes.fromhex('01000088500389f18a9c0c7001000031d2389c140c01000073064283fa2075f1c1e208c1ea058894'),
    bytes.fromhex('0c8101000083c1448d968008000039d175cee93bffffff807b05027627a11c00000040a31c000000'),
    bytes.fromhex('c643040183c34439fb0f84e30000008b7304f7c60100000074d5ebe8837c24080875268b2b89e9b8'),
    bytes.fromhex('20770c00ffd088430889e9b850770c00ffd088430989e9b880770c00ffd088430a807b0632763f89'),
    bytes.fromhex('f083c804884304837c2408087554a10c000000a804742e0fb643080fb64b098d14080fb66b0a01ea'),
    bytes.fromhex('83fa037e1883c00339c1721189f083c80c884304eb07837c240808751d0fb64308400fb6530939d0'),
    bytes.fromhex('7310a12000000040a320000000e952ffffff807b0b027610a12400000040a324000000e93cffffff'),
    bytes.fromhex('807b0c017710a12800000040a328000000e926ffffff804b0402a11800000040a318000000e912ff'),
    bytes.fromhex('ffff837c2408087521a1140000008b54243083fa087605ba080000000fb69a64190000d1e80fafd8'),
    bytes.fromhex('eb068b1d18000000837c2408070f94c10f94c20fb6d26944246c830000006b7424300701f08b7c24'),
    bytes.fromhex('0801f88bb42480000000f7de81e6d103000001c689f0c1e81031f069c06bcaeb8589c6c1ee0d31f0'),
    bytes.fromhex('69c035aeb2c289c6c1ee1031f089842490000000c1eb04899c248c00000031c083ff080f95c08944'),
    bytes.fromhex('243cff4c243c8364243cf48344243c4189c8c1e01f89442464c17c24641f836424641131ff897c24'),
    bytes.fromhex('18897c2448897c24406bc211898424980000008b8424900000008b7c244001f883e01f894424046b'),
    bytes.fromhex('c0448a8404640100008844247283e0123c020f853c09000031c0c68404b7000000004083f81175f2'),
    bytes.fromhex('8b1578c2e3006b44240444894424688b840460010000894424148b802401000029c2899424840000'),
    bytes.fromhex('0031db31c9894c247cc7442410ff00000031f689742420897424288974241c897424788b54246831'),
    bytes.fromhex('f689742444bdff000000be00010000b8010000008a88c0190000837c240807752084c974620fb6bc'),
    bytes.fromhex('14930100000fb688d41900004139cf0f92c10fb6c989cfeb0684c9744231ff80bc04b70000000075'),
    bytes.fromhex('368b4c246480bc01401900000074288a8c148201000080f93f760485ff74180fb6f939f7731180f9'),
    bytes.fromhex('3f0f97c10fb6c9894c244489fe89c5404283f811758681fdff0000000f842f080000c6842cb70000'),
    bytes.fromhex('00010fb684acc8000000837c244400740f31d2895424243c08762983e808eb208b7c246881c7e009'),
    bytes.fromhex('00008d143c0fb6941590f7ffff8d72038974242439c67304894424248d84acc8000000894424748d'),
    bytes.fromhex('bc246001000031c08944240c894424348b742434397424040f84140300008a47048844247383e015'),
    bytes.fromhex('3c040f85020300008b078944243831db31c08944245031f60fb6570639d3732d8b4424388d04988b'),
    bytes.fromhex('0885c9741d89c8e8ebf4ffff39c575124689c8e87bf4ffff3944245073048944245043ebcb0fb685'),
    bytes.fromhex('981900004039c6723b0fb64c2f320fb685d41900004039c1722a8b4424388d049089842488000000'),
    bytes.fromhex('8b4424388944244c8b4424208944245c31c0894424608944242ceb3fa14400000040a344000000e9'),
    bytes.fromhex('660200008b44244c8b1885db75378b442460894424588b74245c8b5c242c8344244c048b44245889'),
    bytes.fromhex('4424608974245c895c242c8b74244c39b4248800000075c4e9ed01000089d8e833f4ffff39c575be'),
    bytes.fromhex('8a4325884424548a4324f743200000c0bf75168b4b2481e100000070750ba80f7407f64424541e75'),
    bytes.fromhex('0da13400000040a334000000eb88837c24080775238b15b876e50085d274198a532731d0a80f7510'),
    bytes.fromhex('a13800000040a338000000e95effffff894c245889d8e860f3ffff89c68a4353a801753c0fb64707'),
    bytes.fromhex('39c6733480bdac190000008b4c245874088b44245039c6731f8b4424740fb6400339c67313f64424'),
    bytes.fromhex('541c751c8b4424740fb6400139f07310a13c00000040a33c000000e9fefeffff898c249c00000089'),
    bytes.fromhex('da8b442438e8e6f3ffff8944245885c08b8c249c000000741ef6442473087407f6442454187510a1'),
    bytes.fromhex('4000000040a340000000e9bffeffff8b44242439c672063974245c7210a14800000040a348000000'),
    bytes.fromhex('e9a1feffff8d04198b0089840c0c01000083c10483f95475ec0fb74b0ab8f05f0e00ffd089442454'),
    bytes.fromhex('89d9b800ed1300ffd081a42430010000ffff0fff8b4c245429c1b800600e00ffd066898424160100'),
    bytes.fromhex('008d8c240c010000b880630e00ffd08b94248400000029c28b0db876e500b80400000083f9037705'),
    bytes.fromhex('a1b876e5006bc02d0578030000c1e80201c039c27d10a14c00000040a34c000000e908feffff89d8'),
    bytes.fromhex('e889f2ffff85c07410a15000000040a350000000e9edfdffff89d8e8b0f2ffff85c00f84eefdffff'),
    bytes.fromhex('ebdf837c242c0074318b44242ce8d9f1ffff894424208b4424448944247c896c24108b4424608944'),
    bytes.fromhex('24288b4424348944241c8b44242c8944240cff44243483c744837c2434200f85ccfcffffff442478'),
    bytes.fromhex('bb01000000837c247803740d837c240c000f84acfbffffeb0b837c240c000f8456060000837c2428'),
    bytes.fromhex('007413a15400000040a354000000c744242801000000837c247c007410a15800000040a358000000'),
    bytes.fromhex('834c2428048b842480000000f7d883e0088b7c242809c7897c24388b4424108d9484c80000000fb6'),
    bytes.fromhex('4a02b803000000394c2420731d0fb64a01b804000000394c2420730e0fb6023944242019c0f7d083'),
    bytes.fromhex('c0068b7c240c8a572583e21f80fa0983d8ff8a572483e20ffeca750140837c24080775014083f807'),
    bytes.fromhex('7605b8070000008b7424048d8e94c0e30089c2c1e20501ca0fb61239f274154889c2c1e20501ca0f'),
    bytes.fromhex('b61231c9894c242439d6750d8b542404c1e20609c289542424c784240c010000090000008b442404'),
    bytes.fromhex('898424100100008b442410898424140100008b44246c898424180100008b4424088984241c010000'),
    bytes.fromhex('8b44243089842420010000a11829b7008b50048b44240c29d0b95400000031d2f7f1898424240100'),
    bytes.fromhex('006b442404440fb6940468010000899424280100000fb68404690100008984242c010000c7442444'),
    bytes.fromhex('5454504331d28b4c2444338c940c01000089c8c1e81031c869c06bcaeb8589c1c1e90d31c869c035'),
    bytes.fromhex('aeb2c289c1c1e91031c8894424444283fa0975ca8b4424108bbc24980000008a8438401900008844'),
    bytes.fromhex('24546b442404440fb684046601000031ff8b74243c39f00f82850100008b4424140fb6801c010000'),
    bytes.fromhex('8944245031ed896c243431f689742428c744244c0000000031ff897c242c31ff8b74245039742428'),
    bytes.fromhex('0f8334010000837c2428410f84290100008b4424148b7424288d04b08b3085f60f848300000089f0'),
    bytes.fromhex('e8a2efffff89c13dff000000747383f802766e31db31ed8b4424148d04a88b0085c0740ae87eefff'),
    bytes.fromhex('ff39c1750143458b44245039c5730583fd4175db394c2410750143837c24340075090fb681841900'),
    bytes.fromhex('00eb17837c24340175090fb68170190000eb070fb6819819000039d8731389f28b442414e8b7efff'),
    bytes.fromhex('ff85c07410eb02ddd8d944244c8b6c242c89feeb7289f0e82aefffff85c075e989f0e861efffff85'),
    bytes.fromhex('c075de8a46270fb7560ab93c000000240f74060fb6c06bc83c39d10f93c30f93c00fb6c089c5ba01'),
    bytes.fromhex('00000089f1b8806d2400ffd085ff7427f644242c01750484db75178b44242c39c57594d944244cd8'),
    bytes.fromhex('d9dfe09e7709ddd8eb87bd01000000ff442428d95c244c896c242c89f7e9befeffff85ff750fff44'),
    bytes.fromhex('2434837c2434030f8595feffff834c243802837c2424007515a16400000040a364000000b8030000'),
    bytes.fromhex('00e95d010000b940420f008b44244431d2f7f10fb64424548bb4248c0000000fafc639c27210a168'),
    bytes.fromhex('00000040a368000000e9d6000000837c2448057615a16c00000040a36c000000b806000000e91101'),
    bytes.fromhex('0000f644243802741985ff7515a15c00000040a35c000000b808000000e9f100000031c031db899c'),
    bytes.fromhex('840c0100004083f80f75f1c784240c010000020000006b44241c448b840460010000898424140100'),
    bytes.fromhex('008b44240c898424180100008b4424148984242c0100008b4424248984243c010000bb010000006b'),
    bytes.fromhex('c33c8b807cc2e30085c0744c4383fb0f75eda17400000040a3740000008b8424000a0000c7000100'),
    bytes.fromhex('0000b805000000eb6a85db0f85e1010000a12c00000040a32c000000ff442440837c2440200f8588'),
    bytes.fromhex('f6ffffe9d20100008b351000000083e6010f848a0000006b442404448a54247283ca108894046401'),
    bytes.fromhex('00006b44241c44808c046401000010ff442448a17800000040a378000000b802000000ff7424388b'),
    bytes.fromhex('7c24140fb694bccc000000526b54240c448dbae80900008d143c8b7c24180fb69417a1f7ffff52ff'),
    bytes.fromhex('74242cff742434ff74242050ff74242c8b4c243c8b5424248b442428e87deeffff83c420e953ffff'),
    bytes.fromhex('ff85ff742050506a016a0189fa8b4c2424b800d92b00ffd0a16000000040a3600000005a598dbc24'),
    bytes.fromhex('ac0000008dac24b00000008d84240c0100006a005557b990ae2b00ffd185c07515a17000000040a3'),
    bytes.fromhex('70000000b804000000e94dffffff6bdb3c8d837cc2e3006b542404448a4c247283c910888c146401'),
    bytes.fromhex('00006b54241c44808c146401000010ff4424488d8b80c2e3008d14318bbc3410010000893a83c604'),
    bytes.fromhex('83fe3075ec66c783b0c2e3000000c7837cc2e300020000006b4c2418188bbc249400000001f98901'),
    bytes.fromhex('8b5c240c8959048b7424048971088b7c241c89790c8b5c24248959108b74240c668b7e2866897c24'),
    bytes.fromhex('1489fa66c1ea0a83e207c1e2088b5c241009da8951148b7424188904b500000000ff442418a17c00'),
    bytes.fromhex('000040a37c000000b801000000e981feffffa13000000040a330000000e91afeffff8b44241881c4'),
    bytes.fromhex('ec0900005b5e5f5dc35557565381ece800000089c38954242c31ff897c2448893d00000000893d04'),
    bytes.fromhex('000000893d08000000893d0c000000893d10000000893d140000008d442448508b5424308d442450'),
    bytes.fromhex('e8c7edffff89442434891c24b800c92b00ffd031ed892d00000000892d04000000892d0800000089'),
    bytes.fromhex('2d0c000000892d10000000892d140000008d5c244c83c40c31c0894424188b742424397424180f84'),
    bytes.fromhex('250200008b0b8b018b6b0483f80275308b410c39e8752952526a016a0131d2b860b62b00ffd0a184'),
    bytes.fromhex('00000040a384000000595ec744240c07000000e9b60100008b730889f1b8504c0c00ffd089c131c0'),
    bytes.fromhex('0fb6911c01000039d0731183f841740c8d14818b1239ea740b40ebe431c08944240ceb08c744240c'),
    bytes.fromhex('010000008b5314837c240c000f8461010000a18000000040a380000000c1ea088954241cbf504c0c'),
    bytes.fromhex('0089f1ffd7894424108b4b0cffd789c789e8e818eaffff8944241489e8e8a9e9ffff894424280fb6'),
    bytes.fromhex('871c0100008944242c31f68b44242c39c6734283fe41743d8d04b78b0885c9743189c8e8dfe9ffff'),
    bytes.fromhex('394424147524668b512866c1ea0a89d083e00783e2073954241c730e6683f80774084a89c8e829eb'),
    bytes.fromhex('ffff46ebb68b4424100fb6801c0100008944241c31ff31f683ff4174428b44241c39c7733a8b4424'),
    bytes.fromhex('108d04b88b0885c9742a39e9742689c8e87ae9ffff3944241475198a4152a801740346eb0f89c8e8'),
    bytes.fromhex('ffe8ffff8b4c242839c873ee47ebb983fe077605be0700000031ff8b44241c39c7734883ff417443'),
    bytes.fromhex('8b4424108d04b88b0885c9743339e9742f89c8e827e9ffff394424147522668b512866c1ea0a89d0'),
    bytes.fromhex('83e00783e20739f2720e6683f80774084289c8e873eaffff47ebb089f289e8e867eaffffa1940000'),
    bytes.fromhex('0083c002a394000000eb0ba18800000040a3880000008b4b0c8b53086a406a006a006a00ff731055'),
    bytes.fromhex('ff7424240fb64314508b442440e87ceaffffff44243883c31883c420e9cdfdffff8b44243c81c4dc'),
    bytes.fromhex('0000005b5e5f5dc35653568b7424108b1da476e500a10000000040a300000000a1000000003d4350'),
    bytes.fromhex('55547514a1040000003d524476317508a10800000048740da10400000040a304000000eb5b83fb08'),
    bytes.fromhex('7527a10c000000a80174428b15b476e5000fb605c551510039c2724ca10c00000040a30c000000eb'),
    bytes.fromhex('2f83fb07751fa10c000000a8027416a1b876e50085c07528a11000000040a310000000eb0ba10800'),
    bytes.fromhex('000040a30800000083ec0c56b800c92b00ffd083c40ceb3431c989da89f0e876fcffff85c07425a1'),
    bytes.fromhex('10000000a801751ca19000000040a390000000b90100000089da89f05b5b5ee94dfcffff585b5ec3'),
    bytes.fromhex('8b54240431c08b0c850000000085c9741c8b0c850000000039d17511a19800000040a398000000b8'),
    bytes.fromhex('01000000c34083f80675d331c0c3669066906690669066900000001010101010000a001005050510'),
    bytes.fromhex('100000000c101010040008000e0c0c0c0a0a0000010101010202020408000000021e1e0606020203'),
    bytes.fromhex('010300050203040404000000031e1e1e1e1e1e1e021e001e1e1e1e1e1e0000000201010505020203'),
    bytes.fromhex('00030005020303030400000001000001010000000000000000000101010000000100000202010101'),
    bytes.fromhex('00010002010202020200000001010103030101010101000401020202020000000001020304050607'),
    bytes.fromhex('08090b0b0c0d0e0f10'),
    b'\xcc' * 263,
    bytes(1280),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0006, True, 'page', 0x1814),
    (0x0015, True, 'page', 0x18fc),
    (0x00bb, False, 'page', 0x19e8),
    (0x020a, False, 'page', 0x19d4),
    (0x0287, False, 'page', 0x1be0),
    (0x02a1, False, 'page', 0x1c00),
    (0x02a9, False, 'page', 0x1c02),
    (0x02b7, False, 'page', 0x1c03),
    (0x02bd, False, 'page', 0x1c04),
    (0x02c7, False, 'page', 0x1c05),
    (0x02d1, False, 'page', 0x1c06),
    (0x02db, False, 'page', 0x1c07),
    (0x030b, False, 'page', 0x1c08),
    (0x0316, False, 'page', 0x1c0a),
    (0x0320, False, 'page', 0x1c0c),
    (0x032a, False, 'page', 0x1c0d),
    (0x0334, False, 'page', 0x1c0e),
    (0x033e, False, 'page', 0x1c0f),
    (0x0345, False, 'page', 0x1be0),
    (0x034a, False, 'page', 0x1bac),
    (0x0350, False, 'page', 0x1bac),
    (0x039f, False, 'page', 0x1b34),
    (0x03a5, False, 'page', 0x1b34),
    (0x05c1, False, 'page', 0x19c0),
    (0x0743, False, 'page', 0x19c0),
    (0x0816, False, 'page', 0x1b3c),
    (0x081c, False, 'page', 0x1b3c),
    (0x087f, False, 'page', 0x1b0c),
    (0x08c3, False, 'page', 0x1b40),
    (0x08c9, False, 'page', 0x1b40),
    (0x08d9, False, 'page', 0x1b44),
    (0x08df, False, 'page', 0x1b44),
    (0x08ef, False, 'page', 0x1b48),
    (0x08f5, False, 'page', 0x1b48),
    (0x0903, False, 'page', 0x1b38),
    (0x0909, False, 'page', 0x1b38),
    (0x091a, False, 'page', 0x1b14),
    (0x092f, False, 'page', 0x1964),
    (0x093c, False, 'page', 0x1b18),
    (0x0a8e, False, 'page', 0x19c0),
    (0x0aa8, False, 'page', 0x19d4),
    (0x0ad0, False, 'page', 0x1940),
    (0x0be0, False, 'page', 0x1998),
    (0x0bf1, False, 'page', 0x19d4),
    (0x0c25, False, 'page', 0x1b64),
    (0x0c2b, False, 'page', 0x1b64),
    (0x0caa, False, 'page', 0x1b54),
    (0x0cb0, False, 'page', 0x1b54),
    (0x0cd1, False, 'page', 0x1b58),
    (0x0cd7, False, 'page', 0x1b58),
    (0x0cfe, False, 'page', 0x19ac),
    (0x0d31, False, 'page', 0x1b5c),
    (0x0d37, False, 'page', 0x1b5c),
    (0x0d70, False, 'page', 0x1b60),
    (0x0d76, False, 'page', 0x1b60),
    (0x0d8e, False, 'page', 0x1b68),
    (0x0d94, False, 'page', 0x1b68),
    (0x0e27, False, 'page', 0x1b6c),
    (0x0e2d, False, 'page', 0x1b6c),
    (0x0e42, False, 'page', 0x1b70),
    (0x0e48, False, 'page', 0x1b70),
    (0x0edc, False, 'page', 0x1b74),
    (0x0ee2, False, 'page', 0x1b74),
    (0x0ef6, False, 'page', 0x1b78),
    (0x0efc, False, 'page', 0x1b78),
    (0x108a, False, 'page', 0x1940),
    (0x1155, False, 'page', 0x1984),
    (0x1165, False, 'page', 0x1970),
    (0x116e, False, 'page', 0x1998),
    (0x123a, False, 'page', 0x1b84),
    (0x1240, False, 'page', 0x1b84),
    (0x126f, False, 'page', 0x1b88),
    (0x1275, False, 'page', 0x1b88),
    (0x1286, False, 'page', 0x1b8c),
    (0x128c, False, 'page', 0x1b8c),
    (0x12a6, False, 'page', 0x1b7c),
    (0x12ac, False, 'page', 0x1b7c),
    (0x1323, False, 'page', 0x1b94),
    (0x1329, False, 'page', 0x1b94),
    (0x134a, False, 'page', 0x1b4c),
    (0x1350, False, 'page', 0x1b4c),
    (0x136a, False, 'page', 0x1b10),
    (0x139c, False, 'page', 0x1b98),
    (0x13a2, False, 'page', 0x1b98),
    (0x1419, False, 'page', 0x1b80),
    (0x141f, False, 'page', 0x1b80),
    (0x144a, False, 'page', 0x1b90),
    (0x1450, False, 'page', 0x1b90),
    (0x150d, False, 'page', 0x1be4),
    (0x1516, False, 'page', 0x1b9c),
    (0x151c, False, 'page', 0x1b9c),
    (0x152b, False, 'page', 0x1b50),
    (0x1531, False, 'page', 0x1b50),
    (0x1561, False, 'page', 0x1be4),
    (0x1567, False, 'page', 0x1be8),
    (0x156d, False, 'page', 0x1bec),
    (0x1573, False, 'page', 0x1bf0),
    (0x1579, False, 'page', 0x1bf4),
    (0x157f, False, 'page', 0x1bf8),
    (0x15a7, False, 'page', 0x1be4),
    (0x15ad, False, 'page', 0x1be8),
    (0x15b3, False, 'page', 0x1bec),
    (0x15b9, False, 'page', 0x1bf0),
    (0x15bf, False, 'page', 0x1bf4),
    (0x15c5, False, 'page', 0x1bf8),
    (0x1607, False, 'page', 0x1ba4),
    (0x160d, False, 'page', 0x1ba4),
    (0x166b, False, 'page', 0x1ba0),
    (0x1671, False, 'page', 0x1ba0),
    (0x17bd, False, 'page', 0x1bb4),
    (0x17c5, False, 'page', 0x1bb4),
    (0x17cc, False, 'page', 0x1ba8),
    (0x17d2, False, 'page', 0x1ba8),
    (0x1826, False, 'page', 0x1b20),
    (0x182c, False, 'page', 0x1b20),
    (0x1831, False, 'page', 0x1b00),
    (0x183d, False, 'page', 0x1b04),
    (0x1849, False, 'page', 0x1b08),
    (0x1851, False, 'page', 0x1b24),
    (0x1857, False, 'page', 0x1b24),
    (0x1863, False, 'page', 0x1b0c),
    (0x187d, False, 'page', 0x1b2c),
    (0x1883, False, 'page', 0x1b2c),
    (0x188f, False, 'page', 0x1b0c),
    (0x18a1, False, 'page', 0x1b30),
    (0x18a7, False, 'page', 0x1b30),
    (0x18ae, False, 'page', 0x1b28),
    (0x18b4, False, 'page', 0x1b28),
    (0x18d8, False, 'page', 0x1b10),
    (0x18e1, False, 'page', 0x1bb0),
    (0x18e7, False, 'page', 0x1bb0),
    (0x1909, False, 'page', 0x1be4),
    (0x1914, False, 'page', 0x1be4),
    (0x191d, False, 'page', 0x1bb8),
    (0x1923, False, 'page', 0x1bb8),
)

LABELS = {
    'story_entry': 0x10,
    'story_is_ours': 0x1900,
    'trade_call': 0x1818,
    'trade_entry': 0x0,
}

"""Relocatable pages of the CPU trades owner (beta 81, owner nfl2k5_cpu_trades): trades between computer clubs at every
position but QB, K and P, a player for a draft pick (tools/cpu_trades/trades.c says exactly which).

Two pages: code at 0x0000 (0xCC after the last byte of code up to 0x1B00), the CPUTRDv1 settings record at +0x1B00, the
counters at +0x1B20 (u32 each, COUNTER_NAMES, at most 48), the ring cursor at +0x1BE0 (events ever written; slot = n % 64),
six words at +0x1BE4 (our records during a pending scan), the clubs in our records or a trade this call at +0x1BFC and the ring at +0x1C00 (64 events of RING_EVENT, 16 bytes). Only the
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
ROUND_MASK = 0x1BFC                              # clubs in a record of ours or a trade this call: out of round 2 (S8)
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
CODE_BYTES = 0x1ad9
COUNTER_NAMES = ('calls', 'bad_settings', 'inactive', 'past_deadline', 'opening_preseason', 'rounds', 'buyers', 'out_load', 'out_race', 'out_picks', 'out_quarterbacks', 'no_need', 'no_package', 'rej_health', 'rej_contract', 'rej_protected', 'rej_starter', 'rej_depth', 'rej_floor', 'rej_cap', 'rej_ledger', 'rebuild_packages', 'depth_packages', 'no_release', 'releases', 'no_pick', 'kept', 'capped', 'refused', 'no_slot', 'shadow', 'posted', 'executed', 'cancelled', 'gone', 'events_logged', 'second_rounds', 'rows_repaired', 'stories_forced')

_TEMPLATE = b''.join((
    bytes.fromhex('fcff742404e8fcffffff83c404c2040050515255e8fcffffff83c40485c05a595875063de8030000'),
    bytes.fromhex('c381fce8030000c3f7402400000070750f8b4020c1e8163c020f96c00fb6c0c331c0c35383ec1889'),
    bytes.fromhex('c131d2b8806d2400ffd0d95c240c8b54240c89d3c1eb1785d2783d0fb6db83fb767635b864000000'),
    bytes.fromhex('0fbae21e722c81e2ffff7f0081ca000080006bd264b99500000029d9b801000000d3e001d0b99600'),
    bytes.fromhex('000029d9d3e8eb0231c083c4185bc30fb6503580fa1077080fb682c81a0000c3b8ff000000c353b9'),
    bytes.fromhex('7cc2e300ba0c0000008b1983fa30741a85db74168d5ae883fb0b76098d1c0a8b1b39c3741483c204'),
    bytes.fromhex('ebdf83c13c81f900c6e30075cf31c0eb05b8010000005bc3565389c3ba70f0e300be820000008b0a'),
    bytes.fromhex('89f0d3e883e00174078b4a0439d9740d83c20c81fa900ce40075e331c05b5ec35557565383ec1089'),
    bytes.fromhex('c789d189d0e865ffffff8a971c0100003dff0000000f84be00000089c689c8e8ccfeffff85c00f84'),
    bytes.fromhex('af0000000fb6c28944240831c0c74424044100000083f84174188b5c240839d873108d14878b1239'),
    bytes.fromhex('ca75048944240440ebe3668b412866c1e80a83e0078944240c31db31c08904248b44240839c3734f'),
    bytes.fromhex('83fb41744a8d049f8b2839e9743e85ed743a89e8e8defeffff39f0752f89e8e854feffff85c07424'),
    bytes.fromhex('668b452866c1e80a83e0078b54240c39d0720e8b54240439d373093944240c7503ff042443eba90f'),
    bytes.fromhex('b686b41a00003904240f92c00fb6c0eb0231c083c4105b5e5f5dc3565389c18a5835668b402825ff'),
    bytes.fromhex('e3000089d6c1e60a09f080fb107730be18ec01000fa3de732625ff1f0000bb0040000085d2741631'),
    bytes.fromhex('db83fa01740fbb0020000083fa02740589d3c1e30d09d8668941285b5ec3555756535389c689d589'),
    bytes.fromhex('0c240fb6b81c01000031db83fb41743b39fb73378d049e8b0885c9742b89c8e80bfeffff39e87520'),
    bytes.fromhex('668b412866c1e80a89c283e207f7d0a807740d39142473084a89c8e85bffffff43ebc0585b5e5f5d'),
    bytes.fromhex('c35557565383ec0889c689d3894c24048b0d0000000089c883e03f8904248b2db876e50089c7c1e7'),
    bytes.fromhex('046689af0000000089f28897020000008b35b476e50089f2889703000000889f040000008a5c2404'),
    bytes.fromhex('889f050000008b54241c8897060000008b542420889707000000b8ffff0000837c2424007417a118'),
    bytes.fromhex('29b7008b50048b44242429d0bb5400000031d2f7f38b1424c1e204668982080000008b4424286689'),
    bytes.fromhex('820a0000008b44242c88820c0000008b44243088820d0000008b44243488820e0000008b44243888'),
    bytes.fromhex('820f00000041890d00000000a18c00000040a38c00000083c4085b5e5f5dc35557565381ecec0900'),
    bytes.fromhex('008984249400000089542408894c2464a11829b7008944241ca1b876e50089442470a1b476e50089'),
    bytes.fromhex('442430837c241c000f84fd110000a11400000040a3140000008b44241c8b401c894424188d9c2460'),
    bytes.fromhex('01000031ed89e9b8504c0c00ffd0894424048903c6430c00c6430b00c6430a00c6430900c6430800'),
    bytes.fromhex('c6430700c6430600c6430500c64304006bc54431d2c684049201000000c684047001000000424083'),
    bytes.fromhex('fa1175e9837c240400740e8b4424048a801c0100003c417609c6430401e9420200008b4424040fb6'),
    bytes.fromhex('801c01000088430631d2c644133200c68414b7000000004283fa1175ed31d289542410894424286b'),
    bytes.fromhex('c5448944242c8b7c2428397c24100f83490100008b4424048b7c24108d04b88b3885ff0f842b0100'),
    bytes.fromhex('0089f8e8cffbffff89c63dff0000000f841701000089f8e857fbffff894424140fb643078b4c2414'),
    bytes.fromhex('39c873078a44241488430785f67515f747200000c0bf750cf74724000000707503fe430c89f8e805'),
    bytes.fromhex('fbffff85c00f84d10000008b44242c05e009000001e0fe8406b2f7ffff668b472866c1e80a83e007'),
    bytes.fromhex('668944241c0fb68434b70000008844240c894424248d04b500000000894424208dbc04c800000031'),
    bytes.fromhex('c08b4c242439c8730e0fb61407663954241c720340ebea83f80474700fb64c240c80f9037605b903'),
    bytes.fromhex('0000008b7c242001f989cf8b54242029d739f8731f8a940cc700000088940cc80000008a940c0b01'),
    bytes.fromhex('000088940c0c01000049ebd58d94b4e009000001c28a44241c8882e8f6ffff8a44241488822cf7ff'),
    bytes.fromhex('ff807c240c03770c8a44240c40888434b7000000ff442410e9a9feffff8d8c240c01000031d20fb6'),
    bytes.fromhex('b2a01a000089f031ff85f6742b388414b700000072228d040e8944240c89cfb8ff0000000fb63739'),
    bytes.fromhex('c6730289f0478b74240c39f775ee89c789f8884413104283c10483fa1175b78b04ad5c77e50085c0'),
    bytes.fromhex('7539b87cc2e3008b1083fa0176128b50083954240474248b502039542404741b83c03c3d00c6e300'),
    bytes.fromhex('75dd837c246400740ea1000000000fa3e87304c64304018d95b4c0e3008d8d94c1e3000fb60239e8'),
    bytes.fromhex('7403fe430b83c22039ca75ef4583c34483fd200f8544fdffff8b3d6cf0e30081ff570200000f8795'),
    bytes.fromhex('00000031f631db8d041fb95802000031d2f7f16bd20c8baa70f0e3008b8a78f0e30089e883e01f83'),
    bytes.fromhex('f807740431f6eb5b8b44241839c1722a29c1894c240489c8b9f401000031d2f7f185d27515817c24'),
    bytes.fromhex('047f3e0000770bba0100000088c1d3e209d685ed79258d94246001000031c00fa3c6730c8a4a0580'),
    bytes.fromhex('f9ff740441884a054083c24483f82075e6eba14381fb580200000f856fffffff8d8424c80000008d'),
    bytes.fromhex('ac246001000031f689e931d2c64121004283c14483fa2075f3c6400300c6400200c6400100c60000'),
    bytes.fromhex('80bea01a000000751f4683c0044583fe1175cd8d8424600100008dbc24e009000089c3e9c6000000'),
    bytes.fromhex('89ef31c98a5f10885c240489ca4185d274218d5aff895c240c8a9c140b010000385c2404730d8b54'),
    bytes.fromhex('240c889c140d010000ebdb8a5c2404889c140c01000083c74483f92075be8a94241401000088108a'),
    bytes.fromhex('94241c0100008850018a9424240100008850028a94242801000088500389f18a9c0c7001000031d2'),
    bytes.fromhex('389c140c01000073064283fa2075f1c1e208c1ea0588940c8101000083c1448d968008000039d175'),
    bytes.fromhex('cee93bffffff807b05027627a11c00000040a31c000000c643040183c34439fb0f84e30000008b73'),
    bytes.fromhex('04f7c60100000074d5ebe8837c24080875268b2b89e9b820770c00ffd088430889e9b850770c00ff'),
    bytes.fromhex('d088430989e9b880770c00ffd088430a807b0632763f89f083c804884304837c2408087554a10c00'),
    bytes.fromhex('0000a804742e0fb643080fb64b098d14080fb66b0a01ea83fa037e1883c00339c1721189f083c80c'),
    bytes.fromhex('884304eb07837c240808751d0fb64308400fb6530939d07310a12000000040a320000000e952ffff'),
    bytes.fromhex('ff807b0b027610a12400000040a324000000e93cffffff807b0c017710a12800000040a328000000'),
    bytes.fromhex('e926ffffff804b0402a11800000040a318000000e912ffffff837c2408087521a1140000008b5424'),
    bytes.fromhex('3083fa087605ba080000000fb69a441a0000d1e80fafd8eb068b1d18000000837c2408070f94c10f'),
    bytes.fromhex('94c20fb6d269442470830000006b7424300701f08b7c240801f88b742464f7de81e6d103000001c6'),
    bytes.fromhex('89f0c1e81031f069c06bcaeb8589c6c1ee0d31f069c035aeb2c289c6c1ee1031f089842490000000'),
    bytes.fromhex('c1eb04899c248c00000031c083ff080f95c08944243cff4c243c8364243cf48344243c4189c8c1e0'),
    bytes.fromhex('1f89442468c17c24681f836424681131ff897c241c897c2448897c24406bc211898424980000008b'),
    bytes.fromhex('8424900000008b7c244001f883e01f894424046bc0448a8404640100008844247683e0123c020f85'),
    bytes.fromhex('4809000031c0c68404b7000000004083f81175f28b1578c2e3006b442404448944246c8b84046001'),
    bytes.fromhex('0000894424148b802401000029c28994248400000031db31c9898c2480000000c7442410ff000000'),
    bytes.fromhex('31f68974242089742428897424188974247c8b54246c31f689742444bdff000000be00010000b801'),
    bytes.fromhex('0000008a88a01a0000837c240807752084c974620fb6bc14930100000fb688b41a00004139cf0f92'),
    bytes.fromhex('c10fb6c989cfeb0684c9744231ff80bc04b70000000075368b4c246880bc01201a00000074288a8c'),
    bytes.fromhex('148201000080f93f760485ff74180fb6f939f7731180f93f0f97c10fb6c9894c244489fe89c54042'),
    bytes.fromhex('83f811758681fdff0000000f8438080000c6842cb7000000010fb684acc8000000837c244400740f'),
    bytes.fromhex('31d2895424243c08762983e808eb208b74246c8dbee00900008d143c0fb6941590f7ffff8d7a0389'),
    bytes.fromhex('7c242439c77304894424248d84acc8000000894424788dbc246001000031c08944240c894424348b'),
    bytes.fromhex('742434397424040f84170300008a47048844247783e0153c040f85050300008b078944243831db31'),
    bytes.fromhex('c08944245031f60fb6570639d3732d8b4424388d04988b0885c9741d89c8e884f4ffff39c5751246'),
    bytes.fromhex('89c8e814f4ffff3944245073048944245043ebcb0fb685781a00004039c6723b0fb64c2f320fb685'),
    bytes.fromhex('b41a00004039c1722a8b4424388d0490898424880000008b4424388944244c8b4424208944245c31'),
    bytes.fromhex('c0894424608944242ceb3fa14400000040a344000000e9690200008b44244c8b1885db75378b4424'),
    bytes.fromhex('60894424588b74245c8b5c242c8344244c048b442458894424608974245c895c242c8b74244c39b4'),
    bytes.fromhex('248800000075c4e9ed01000089d8e8ccf3ffff39c575be8a4325884424548a4324f743200000c0bf'),
    bytes.fromhex('75168b4b2481e100000070750ba80f7407f64424541e750da13400000040a334000000eb88837c24'),
    bytes.fromhex('080775238b15b876e50085d274198a532731d0a80f7510a13800000040a338000000e95effffff89'),
    bytes.fromhex('4c245889d8e8f9f2ffff89c68a4353a801753c0fb6470739c6733480bd8c1a0000008b4c24587408'),
    bytes.fromhex('8b44245039c6731f8b4424780fb6400339c67313f64424541c751c8b4424780fb6400139f07310a1'),
    bytes.fromhex('3c00000040a33c000000e9fefeffff898c249c00000089da8b442438e87ff3ffff8944245885c08b'),
    bytes.fromhex('8c249c000000741ef6442477087407f6442454187510a14000000040a340000000e9bffeffff8b44'),
    bytes.fromhex('242439c672063974245c7210a14800000040a348000000e9a1feffff8d04198b0089840c0c010000'),
    bytes.fromhex('83c10483f95475ec0fb74b0ab8f05f0e00ffd08944245489d9b800ed1300ffd081a42430010000ff'),
    bytes.fromhex('ff0fff8b4c245429c1b800600e00ffd066898424160100008d8c240c010000b880630e00ffd08b94'),
    bytes.fromhex('248400000029c28b0db876e500b80400000083f9037705a1b876e5006bc02d0578030000c1e80201'),
    bytes.fromhex('c039c27d10a14c00000040a34c000000e908feffff89d8e822f2ffff85c07410a15000000040a350'),
    bytes.fromhex('000000e9edfdffff89d8e849f2ffff85c00f84eefdffffebdf837c242c0074348b44242ce872f1ff'),
    bytes.fromhex('ff894424208b44244489842480000000896c24108b442460894424288b442434894424188b44242c'),
    bytes.fromhex('8944240cff44243483c744837c2434200f85c9fcffffff44247cbb01000000837c247c03740d837c'),
    bytes.fromhex('240c000f84a9fbffffeb0b837c240c000f84a5060000837c2428007413a15400000040a354000000'),
    bytes.fromhex('c74424280100000083bc2480000000007410a15800000040a358000000834c2428048b442464f7d8'),
    bytes.fromhex('83e0088b7c242809c7897c24388b4424108d9484c80000000fb64a02b803000000394c2420731d0f'),
    bytes.fromhex('b64a01b804000000394c2420730e0fb6023944242019c0f7d083c0068b74240c8a562583e21f80fa'),
    bytes.fromhex('0983d8ff8a562483e20ffeca750140837c24080775014083f8077605b8070000008b7c24048d8f94'),
    bytes.fromhex('c0e30089c2c1e20501ca0fb61239fa74154889c2c1e20501ca0fb61231c9894c242439d7750d8b54'),
    bytes.fromhex('2404c1e20609c289542424c784240c010000090000008b442404898424100100008b442410898424'),
    bytes.fromhex('140100008b442470898424180100008b4424088984241c0100008b44243089842420010000a11829'),
    bytes.fromhex('b7008b50048b44240c29d0b95400000031d2f7f1898424240100006b442404440fb6940468010000'),
    bytes.fromhex('899424280100000fb68404690100008984242c010000c74424445454504331d28b4c2444338c940c'),
    bytes.fromhex('01000089c8c1e81031c869c06bcaeb8589c1c1e90d31c869c035aeb2c289c1c1e91031c889442444'),
    bytes.fromhex('4283fa0975ca8b4424108bb424980000008a8430201a0000884424546b442404440fb68404660100'),
    bytes.fromhex('0031f68b7c243c39f80f828b0100008b4424140fb6801c0100008944245031ed896c243431f68974'),
    bytes.fromhex('2428c744244c0000000031ff897c242c31f68b7c2450397c24280f833a010000837c2428410f842f'),
    bytes.fromhex('0100008b4424148b7c24288d04b88b3885ff0f84f600000089f8e838efffff89c13dff0000000f84'),
    bytes.fromhex('e200000083f8020f86d900000031db31ed8b4424148d04a88b0085c0740ae80cefffff39c1750143'),
    bytes.fromhex('458b44245039c5730583fd4175db394c2410750143837c24340075090fb681641a0000eb17837c24'),
    bytes.fromhex('340175090fb681501a0000eb070fb681781a000039d8737e89fa8b442414e845efffff85c0756f89'),
    bytes.fromhex('f8e8c8eeffff85c0756489f8e8ffeeffff85c075598a47270fb7570ab93c000000240f74060fb6c0'),
    bytes.fromhex('6bc83c39d10f93c30f93c00fb6c089c5ba0100000089f9b8806d2400ffd085f67435f644242c0175'),
    bytes.fromhex('0484db75258b44242c39c5750fd944244cd8d9dfe09e7717ddd8eb02ddd8d944244c8b6c242c89f7'),
    bytes.fromhex('eb05bd01000000ff442428d95c244c896c242c89fee9b8feffff85f6750fff442434837c2434030f'),
    bytes.fromhex('858ffeffff834c243802837c2424007515a16400000040a364000000b803000000e95d010000b940'),
    bytes.fromhex('420f008b44244431d2f7f10fb64424548bbc248c0000000fafc739c27210a16800000040a3680000'),
    bytes.fromhex('00e9d6000000837c2448057615a16c00000040a36c000000b806000000e911010000f64424380274'),
    bytes.fromhex('1985f67515a15c00000040a35c000000b808000000e9f100000031c031db899c840c0100004083f8'),
    bytes.fromhex('0f75f1c784240c010000020000006b442418448b840460010000898424140100008b44240c898424'),
    bytes.fromhex('180100008b4424148984242c0100008b4424248984243c010000bb010000006bc33c8b807cc2e300'),
    bytes.fromhex('85c0744c4383fb0f75eda17400000040a3740000008b8424000a0000c70001000000b805000000eb'),
    bytes.fromhex('6a85db0f852a020000a12c00000040a32c000000ff442440837c2440200f857cf6ffffe91b020000'),
    bytes.fromhex('8b3d1000000083e7010f848a0000006b442404448a54247683ca10889404640100006b4424184480'),
    bytes.fromhex('8c046401000010ff442448a17800000040a378000000b802000000ff7424388b7424140fb694b4cc'),
    bytes.fromhex('000000526b54240c448dbae80900008d143c8b7424180fb69416a1f7ffff52ff74242cff742434ff'),
    bytes.fromhex('74242050ff74242c8b4c24388b5424248b442428e868eeffff83c420e953ffffff85f6744789f0e8'),
    bytes.fromhex('33ecffff89c5668b462866c1e80a83e0078944242850506a016a0189f28b4c2424b800d92b00ffd0'),
    bytes.fromhex('5a598b4c242889ea8b442414e8c5edffffa16000000040a3600000008db424ac0000008dac24b000'),
    bytes.fromhex('00008d84240c0100006a005556b990ae2b00ffd185c07515a17000000040a370000000b804000000'),
    bytes.fromhex('e926ffffff6bdb3c8d837cc2e3006b542404448a4c247683c910888c14640100006b54241844808c'),
    bytes.fromhex('146401000010ff4424488d8b80c2e3008d14398bb43c10010000893283c70483ff3075ec66c783b0'),
    bytes.fromhex('c2e3000000c7837cc2e300020000006b4c241c188bb4249400000001f189018b7c240c8979048b5c'),
    bytes.fromhex('24048959088b74241889710c8b7c24248979108b5c240c668b7328668974241489f266c1ea0a83e2'),
    bytes.fromhex('07c1e2088b7c241009fa8951148b5c241c89049d000000008b1d00000000ba0100000089d08a4c24'),
    bytes.fromhex('04d3e009d88a4c2418d3e209d0a300000000ff44241ca17c00000040a37c000000b801000000e938'),
    bytes.fromhex('feffffa13000000040a330000000e9d1fdffff8b44241c81c4ec0900005b5e5f5dc35557565381ec'),
    bytes.fromhex('d800000089c68954242031ed896c24388b1d6cf0e3008b3d1829b70031c0a300000000a304000000'),
    bytes.fromhex('a308000000a30c000000a310000000a3140000008d442438508b5424248d442440e861edffff8944'),
    bytes.fromhex('2428893424b800c92b00ffd031c0a300000000a304000000a308000000a30c000000a310000000a3'),
    bytes.fromhex('1400000083c40c31f681fb57020000776785ff7463a16cf0e30039d8745a81fe5802000074526bd3'),
    bytes.fromhex('0c8b8278f0e3008b9270f0e30083e21f83fa07752d8b571c39d072268b571c8b2d0000000029d0b9'),
    bytes.fromhex('f401000031d2f7f1ba0100000088c1d3e289d009e8a3000000004381fb58020000750231db46eb91'),
    bytes.fromhex('8d5c243031ff897c240c8b7c2418397c240c0f84db0100008b0b8b018b6b0483f802752f8b410c39'),
    bytes.fromhex('e8752852526a016a0131d2b860b62b00ffd0a18400000040a384000000595ec7042407000000e96d'),
    bytes.fromhex('0100008b43088944240489c1b8504c0c00ffd089c131c00fb6911c01000039d0731183f841740c8d'),
    bytes.fromhex('14818b1239ea740a40ebe431c0890424eb07c70424010000008b7314833c24000f8417010000a180'),
    bytes.fromhex('00000040a380000000bf504c0c008b4c2404ffd7894424048b4b0cffd789c789e8e8f1e8ffff8944'),
    bytes.fromhex('240889e8e882e8ffff8944241cc1ee0889f18b54240889f8e899eaffff8b4424040fb6801c010000'),
    bytes.fromhex('8944241031f631ff83fe4174428b44241039c6733a8b4424048d04b08b0885c9742a39e9742689c8'),
    bytes.fromhex('e89ae8ffff3944240875198a4152a801740347eb0f89c8e81fe8ffff8b4c241c39c873ee46ebb989'),
    bytes.fromhex('fe83ff077605be0700000031ff83ff41744b8b44241039c773438b4424048d04b88b0885c9743339'),
    bytes.fromhex('e9742f89c8e845e8ffff394424087522668b512866c1ea0a89d083e00783e20739f2720e6683f807'),
    bytes.fromhex('74084289c8e891e9ffff47ebb089f289e8e885e9ffffa19400000083c002a394000000eb0ba18800'),
    bytes.fromhex('000040a3880000008b4b0c8b53086a406a006a006a00ff731055ff7424180fb64314508b442434e8'),
    bytes.fromhex('f5e9ffffff44242c83c31883c420e917feffff8b44242c81c4cc0000005b5e5f5dc35653508b7424'),
    bytes.fromhex('108b1da476e500a10000000040a300000000a1000000003d435055547514a1040000003d52447631'),
    bytes.fromhex('7508a10800000048740da10400000040a304000000eb5b83fb087527a10c000000a80174428b15b4'),
    bytes.fromhex('76e5000fb605c551510039c2724ca10c00000040a30c000000eb2f83fb07751fa10c000000a80274'),
    bytes.fromhex('16a1b876e50085c07528a11000000040a310000000eb0ba10800000040a30800000083ec0c56b800'),
    bytes.fromhex('c92b00ffd083c40ceb3b31c0a30000000031c989da89f0e846fcffff85c07425a110000000a80175'),
    bytes.fromhex('1ca19000000040a390000000b90100000089da89f05b5b5ee91dfcffff585b5ec38b54240431c08b'),
    bytes.fromhex('0c850000000085c9741c8b0c850000000039d17511a19800000040a398000000b801000000c34083'),
    bytes.fromhex('f80675d331c0c3900000001010101010000a001005050510100000000c101010040008000e0c0c0c'),
    bytes.fromhex('0a0a0000010101010202020408000000021e1e0606020203010300050203040404000000031e1e1e'),
    bytes.fromhex('1e1e1e1e021e001e1e1e1e1e1e000000020101050502020300030005020303030400000001000001'),
    bytes.fromhex('01000000000000000000010101000000010000020201010100010002010202020200000001010103'),
    bytes.fromhex('03010101010100040102020202000000000102030405060708090b0b0c0d0e0f10'),
    b'\xcc' * 39,
    bytes(1280),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0006, True, 'page', 0x18f6),
    (0x0015, True, 'page', 0x19e5),
    (0x00bb, False, 'page', 0x1ac8),
    (0x020a, False, 'page', 0x1ab4),
    (0x02e2, False, 'page', 0x1be0),
    (0x02fc, False, 'page', 0x1c00),
    (0x0304, False, 'page', 0x1c02),
    (0x0312, False, 'page', 0x1c03),
    (0x0318, False, 'page', 0x1c04),
    (0x0322, False, 'page', 0x1c05),
    (0x032c, False, 'page', 0x1c06),
    (0x0336, False, 'page', 0x1c07),
    (0x0366, False, 'page', 0x1c08),
    (0x0371, False, 'page', 0x1c0a),
    (0x037b, False, 'page', 0x1c0c),
    (0x0385, False, 'page', 0x1c0d),
    (0x038f, False, 'page', 0x1c0e),
    (0x0399, False, 'page', 0x1c0f),
    (0x03a0, False, 'page', 0x1be0),
    (0x03a5, False, 'page', 0x1bac),
    (0x03ab, False, 'page', 0x1bac),
    (0x03f7, False, 'page', 0x1b34),
    (0x03fd, False, 'page', 0x1b34),
    (0x0619, False, 'page', 0x1aa0),
    (0x069a, False, 'page', 0x1bfc),
    (0x07aa, False, 'page', 0x1aa0),
    (0x087d, False, 'page', 0x1b3c),
    (0x0883, False, 'page', 0x1b3c),
    (0x08e6, False, 'page', 0x1b0c),
    (0x092a, False, 'page', 0x1b40),
    (0x0930, False, 'page', 0x1b40),
    (0x0940, False, 'page', 0x1b44),
    (0x0946, False, 'page', 0x1b44),
    (0x0956, False, 'page', 0x1b48),
    (0x095c, False, 'page', 0x1b48),
    (0x096a, False, 'page', 0x1b38),
    (0x0970, False, 'page', 0x1b38),
    (0x0981, False, 'page', 0x1b14),
    (0x0996, False, 'page', 0x1a44),
    (0x09a3, False, 'page', 0x1b18),
    (0x0af5, False, 'page', 0x1aa0),
    (0x0b0f, False, 'page', 0x1ab4),
    (0x0b37, False, 'page', 0x1a20),
    (0x0c47, False, 'page', 0x1a78),
    (0x0c58, False, 'page', 0x1ab4),
    (0x0c8c, False, 'page', 0x1b64),
    (0x0c92, False, 'page', 0x1b64),
    (0x0d11, False, 'page', 0x1b54),
    (0x0d17, False, 'page', 0x1b54),
    (0x0d38, False, 'page', 0x1b58),
    (0x0d3e, False, 'page', 0x1b58),
    (0x0d65, False, 'page', 0x1a8c),
    (0x0d98, False, 'page', 0x1b5c),
    (0x0d9e, False, 'page', 0x1b5c),
    (0x0dd7, False, 'page', 0x1b60),
    (0x0ddd, False, 'page', 0x1b60),
    (0x0df5, False, 'page', 0x1b68),
    (0x0dfb, False, 'page', 0x1b68),
    (0x0e8e, False, 'page', 0x1b6c),
    (0x0e94, False, 'page', 0x1b6c),
    (0x0ea9, False, 'page', 0x1b70),
    (0x0eaf, False, 'page', 0x1b70),
    (0x0f46, False, 'page', 0x1b74),
    (0x0f4c, False, 'page', 0x1b74),
    (0x0f63, False, 'page', 0x1b78),
    (0x0f69, False, 'page', 0x1b78),
    (0x10f4, False, 'page', 0x1a20),
    (0x11c7, False, 'page', 0x1a64),
    (0x11d7, False, 'page', 0x1a50),
    (0x11e0, False, 'page', 0x1a78),
    (0x12aa, False, 'page', 0x1b84),
    (0x12b0, False, 'page', 0x1b84),
    (0x12df, False, 'page', 0x1b88),
    (0x12e5, False, 'page', 0x1b88),
    (0x12f6, False, 'page', 0x1b8c),
    (0x12fc, False, 'page', 0x1b8c),
    (0x1316, False, 'page', 0x1b7c),
    (0x131c, False, 'page', 0x1b7c),
    (0x1393, False, 'page', 0x1b94),
    (0x1399, False, 'page', 0x1b94),
    (0x13ba, False, 'page', 0x1b4c),
    (0x13c0, False, 'page', 0x1b4c),
    (0x13da, False, 'page', 0x1b10),
    (0x140c, False, 'page', 0x1b98),
    (0x1412, False, 'page', 0x1b98),
    (0x14b2, False, 'page', 0x1b80),
    (0x14b8, False, 'page', 0x1b80),
    (0x14e1, False, 'page', 0x1b90),
    (0x14e7, False, 'page', 0x1b90),
    (0x15a4, False, 'page', 0x1be4),
    (0x15aa, False, 'page', 0x1bfc),
    (0x15c6, False, 'page', 0x1bfc),
    (0x15cf, False, 'page', 0x1b9c),
    (0x15d5, False, 'page', 0x1b9c),
    (0x15e4, False, 'page', 0x1b50),
    (0x15ea, False, 'page', 0x1b50),
    (0x1627, False, 'page', 0x1be4),
    (0x162c, False, 'page', 0x1be8),
    (0x1631, False, 'page', 0x1bec),
    (0x1636, False, 'page', 0x1bf0),
    (0x163b, False, 'page', 0x1bf4),
    (0x1640, False, 'page', 0x1bf8),
    (0x1667, False, 'page', 0x1be4),
    (0x166c, False, 'page', 0x1be8),
    (0x1671, False, 'page', 0x1bec),
    (0x1676, False, 'page', 0x1bf0),
    (0x167b, False, 'page', 0x1bf4),
    (0x1680, False, 'page', 0x1bf8),
    (0x16c9, False, 'page', 0x1bfc),
    (0x16e6, False, 'page', 0x1bfc),
    (0x1733, False, 'page', 0x1ba4),
    (0x1739, False, 'page', 0x1ba4),
    (0x1797, False, 'page', 0x1ba0),
    (0x179d, False, 'page', 0x1ba0),
    (0x189f, False, 'page', 0x1bb4),
    (0x18a7, False, 'page', 0x1bb4),
    (0x18ae, False, 'page', 0x1ba8),
    (0x18b4, False, 'page', 0x1ba8),
    (0x1908, False, 'page', 0x1b20),
    (0x190e, False, 'page', 0x1b20),
    (0x1913, False, 'page', 0x1b00),
    (0x191f, False, 'page', 0x1b04),
    (0x192b, False, 'page', 0x1b08),
    (0x1933, False, 'page', 0x1b24),
    (0x1939, False, 'page', 0x1b24),
    (0x1945, False, 'page', 0x1b0c),
    (0x195f, False, 'page', 0x1b2c),
    (0x1965, False, 'page', 0x1b2c),
    (0x1971, False, 'page', 0x1b0c),
    (0x1983, False, 'page', 0x1b30),
    (0x1989, False, 'page', 0x1b30),
    (0x1990, False, 'page', 0x1b28),
    (0x1996, False, 'page', 0x1b28),
    (0x19ad, False, 'page', 0x1bfc),
    (0x19c1, False, 'page', 0x1b10),
    (0x19ca, False, 'page', 0x1bb0),
    (0x19d0, False, 'page', 0x1bb0),
    (0x19f2, False, 'page', 0x1be4),
    (0x19fd, False, 'page', 0x1be4),
    (0x1a06, False, 'page', 0x1bb8),
    (0x1a0c, False, 'page', 0x1bb8),
)

LABELS = {
    'story_entry': 0x10,
    'story_is_ours': 0x19e9,
    'trade_call': 0x18fa,
    'trade_entry': 0x0,
}

"""Relocatable pages of the CPU trades owner (beta 81, owner nfl2k5_cpu_trades): trades between computer clubs at every
position but QB, K and P, a player for a draft pick (tools/cpu_trades/trades.c says exactly which).

Two pages: code at 0x0000 (0xCC after the last byte of code up to 0x1C00), the CPUTRDv1 settings record at +0x1C00, the
counters at +0x1C20 (u32 each, COUNTER_NAMES, at most 48), the ring cursor at +0x1CE0 (events ever written; slot = n % 48),
six words at +0x1CE4 (our records during a pending scan), the clubs in our records or a trade this call at +0x1CFC and
the ring at +0x1D00 (48 events of RING_EVENT, 16 bytes). Only the settings record is non-zero in the file. Two whole 5-byte calls enter the code: 0x2BC96C, the native trade pass 0x2BC960's
call of its pending scan 0x2BC900, and 0x2BB296, the trade story writer's value line (HOOKS). The template,
relocations and labels are generated from tools/cpu_trades by build.py; the pick word is in nfl2k5_trade_picks.
"""
from __future__ import annotations

import struct

PAGE_SIZE = 0x2000
CODE_LIMIT = 0x1C00
SETTINGS_OFFSET = 0x1C00
SETTINGS = struct.Struct("<8sIIIIII")            # magic, mode, stages, flags, p8_ppm, p7_ppm, reserved
MAGIC = b"CPUTRDv1"
COUNTERS_OFFSET = 0x1C20
COUNTERS_LIMIT = 48
RING_CURSOR = 0x1CE0
CURRENT = 0x1CE4                                 # six words: the records of ours during a pending scan (RAM only)
ROUND_MASK = 0x1CFC                              # clubs in a record of ours or a trade this call: out of round 2 (S8)
RING_OFFSET = 0x1D00
RING_COUNT = 48
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
CODE_BYTES = 0x1bd9
COUNTER_NAMES = ('calls', 'bad_settings', 'inactive', 'past_deadline', 'opening_preseason', 'rounds', 'buyers', 'out_load', 'out_race', 'out_picks', 'out_quarterbacks', 'no_need', 'no_package', 'rej_health', 'rej_contract', 'rej_protected', 'rej_starter', 'rej_depth', 'rej_floor', 'rej_cap', 'rej_ledger', 'rebuild_packages', 'depth_packages', 'no_release', 'releases', 'no_pick', 'kept', 'capped', 'refused', 'no_slot', 'shadow', 'posted', 'executed', 'cancelled', 'gone', 'events_logged', 'second_rounds', 'rows_repaired', 'stories_forced')

_TEMPLATE = b''.join((
    bytes.fromhex('fcff742404e8fcffffff83c404c2040050515255e8fcffffff83c40485c05a595875063de8030000'),
    bytes.fromhex('c381fce8030000c3f7402400000070750f8b4020c1e8163c020f96c00fb6c0c331c0c35383ec1889'),
    bytes.fromhex('c131d2b8806d2400ffd0d95c240c8b54240c89d3c1eb1785d2783d0fb6db83fb767635b864000000'),
    bytes.fromhex('0fbae21e722c81e2ffff7f0081ca000080006bd264b99500000029d9b801000000d3e001d0b99600'),
    bytes.fromhex('000029d9d3e8eb0231c083c4185bc30fb6503580fa1077080fb682c81b0000c3b8ff000000c353b9'),
    bytes.fromhex('7cc2e300ba0c0000008b1983fa30741a85db74168d5ae883fb0b76098d1c0a8b1b39c3741483c204'),
    bytes.fromhex('ebdf83c13c81f900c6e30075cf31c0eb05b8010000005bc3565389c3ba70f0e300be820000008b0a'),
    bytes.fromhex('89f0d3e883e00174078b4a0439d9740d83c20c81fa900ce40075e331c05b5ec35557565383ec1089'),
    bytes.fromhex('c789d189d0e865ffffff8a971c0100003dff0000000f84be00000089c689c8e8ccfeffff85c00f84'),
    bytes.fromhex('af0000000fb6c28944240831c0c74424044100000083f84174188b5c240839d873108d14878b1239'),
    bytes.fromhex('ca75048944240440ebe3668b412866c1e80a83e0078944240c31db31c08904248b44240839c3734f'),
    bytes.fromhex('83fb41744a8d049f8b2839e9743e85ed743a89e8e8defeffff39f0752f89e8e854feffff85c07424'),
    bytes.fromhex('668b452866c1e80a83e0078b54240c39d0720e8b54240439d373093944240c7503ff042443eba90f'),
    bytes.fromhex('b686b41b00003904240f92c00fb6c0eb0231c083c4105b5e5f5dc3565389c18a5835668b402825ff'),
    bytes.fromhex('e3000089d6c1e60a09f080fb107730be18ec01000fa3de732625ff1f0000bb0040000085d2741631'),
    bytes.fromhex('db83fa01740fbb0020000083fa02740589d3c1e30d09d8668941285b5ec35557565383ec2c89c689'),
    bytes.fromhex('54241c894c24140fb6801c0100008944241831db31c08944241031ff31d28954240c83fb4174738b'),
    bytes.fromhex('44241839c3736b8d049e8b2885ed745f89e8e8f0fdffff8b4c241c39c87550668b552866c1ea0a89'),
    bytes.fromhex('d083e00783e2073954241473106683f80774164a89e8e838ffffffeb2a6683f806741c6683f80775'),
    bytes.fromhex('1e89e8e84bfdffff403944241073108944241089efeb08c744240c0100000043eb8885ff0f95c28a'),
    bytes.fromhex('44240c83f00184c2741a837c2414067713ba0600000089f883c42c5b5e5f5de9dffeffff83c42c5b'),
    bytes.fromhex('5e5f5dc3555756535389c689d38b3d00000000bd3000000089f831d2f7f58914248b2db876e50089'),
    bytes.fromhex('d0c1e0048d90000000006689a80000000089f0884202a1b476e500884203885a04884a058b442418'),
    bytes.fromhex('8842068b44241c884207b8ffff0000837c2420007417a11829b7008b50048b44242029d0bb540000'),
    bytes.fromhex('0031d2f7f38b1424c1e204668982080000008b4424246689820a0000008b44242888820c0000008b'),
    bytes.fromhex('44242c88820d0000008b44243088820e0000008b44243488820f0000008d4f01890d00000000a18c'),
    bytes.fromhex('00000040a38c000000585b5e5f5dc35557565381ecec0b00008984249400000089542408894c2464'),
    bytes.fromhex('a11829b7008944241ca1b876e50089442470a1b476e50089442430837c241c000f8484120000a114'),
    bytes.fromhex('00000040a3140000008b44241c8b401c894424188d9c246001000031ed89e9b8504c0c00ffd08944'),
    bytes.fromhex('24048903c6430c00c6430b00c6430a00c6430900c6430800c6430700c6430600c6430500c6430400'),
    bytes.fromhex('89d831d2c6404300c6402100c6401000424083fa1175ed837c240400740e8b4424048a801c010000'),
    bytes.fromhex('3c417609c6430401e94a0200008b4424040fb6801c01000088430631d2c644134300c68414b70000'),
    bytes.fromhex('00004283fa1175ed31d289542410894424286bc5548944242c8b7c2428397c24100f83490100008b'),
    bytes.fromhex('4424048b7c24108d04b88b3885ff0f842b01000089f8e86cfbffff89c63dff0000000f8417010000'),
    bytes.fromhex('89f8e8f4faffff894424140fb643078b4c241439c873078a44241488430785f67515f747200000c0'),
    bytes.fromhex('bf750cf74724000000707503fe430c89f8e8a2faffff85c00f84d10000008b44242c05e00b000001'),
    bytes.fromhex('e0fe8406c3f5ffff668b472866c1e80a83e007668944241c0fb68434b70000008844240c89442424'),
    bytes.fromhex('8d04b500000000894424208dbc04c800000031c08b4c242439c8730e0fb61407663954241c720340'),
    bytes.fromhex('ebea83f80474700fb64c240c80f9037605b9030000008b7c242001f989cf8b54242029d739f8731f'),
    bytes.fromhex('8a940cc700000088940cc80000008a940c0b01000088940c0c01000049ebd58d94b4e00b000001c2'),
    bytes.fromhex('8a44241c8882e8f4ffff8a44241488822cf5ffff807c240c03770c8a44240c40888434b7000000ff'),
    bytes.fromhex('442410e9a9feffff6bfd5431c08a9404b700000084d274180fb6b4840c01000031c9feca740e0fb6'),
    bytes.fromhex('8c840d010000eb0431f631c980b8a01b000001760688ca39f1720289f288943c7001000088ca39f1'),
    bytes.fromhex('730289f288943c81010000404783f81175ab8b04ad5c77e50085c07539b87cc2e3008b1083fa0176'),
    bytes.fromhex('128b50083954240474248b502039542404741b83c03c3d00c6e30075dd837c246400740ea1000000'),
    bytes.fromhex('000fa3e87304c64304018d95b4c0e3008d8d94c1e3000fb60239e87403fe430b83c22039ca75ef45'),
    bytes.fromhex('83c35483fd200f8541fdffff8b3d6cf0e30081ff570200000f879500000031f631db8d041fb95802'),
    bytes.fromhex('000031d2f7f16bd20c8baa70f0e3008b8a78f0e30089e883e01f83f807740431f6eb5b8b44241839'),
    bytes.fromhex('c1722a29c1894c240489c8b9f401000031d2f7f185d27515817c24047f3e0000770bba0100000088'),
    bytes.fromhex('c1d3e209d685ed79258d94246001000031c00fa3c6730c8a4a0580f9ff740441884a054083c25483'),
    bytes.fromhex('f82075e6eba14381fb580200000f856fffffff8d8c24c80000008d8424600100008944240c31ed8b'),
    bytes.fromhex('54240c31c0c64232004083c25483f82075f3c6410300c6410200c6410100c601000fb685a01b0000'),
    bytes.fromhex('84c00f84a4000000c1e005894424148b7c240c31c089442404e9df00000089d8c1e8028a84040c01'),
    bytes.fromhex('0000880189d8d1e88a84040c0100008841018d045bc1e8028a84040c0100008841028d04dbbe0a00'),
    bytes.fromhex('000031d2f7f68a84040c01000088410389ee0fb68434700100008944241031c00fb694040c010000'),
    bytes.fromhex('8b7c241039fa0f83a40000008d50013944240489d075e101d0c1e00731d2f7f38884349201000083'),
    bytes.fromhex('c6548d85800a000039c675b64583c104ff44240c83fd110f851affffff8d8424600100008dbc24e0'),
    bytes.fromhex('0b000089c3e9950000008a87a1f5ffff8b7424048d5e0185f675268884340c01000083c7548b4424'),
    bytes.fromhex('1439c30f8325ffffff895c2404837c24041f77ce8a4710ebcf8d56ff895424108a94340b01000038'),
    bytes.fromhex('d073c88b7424108894340d010000ebb789c239da0f835dffffff0fb6bc140c010000397c24100f85'),
    bytes.fromhex('4bffffff42ebe3807b05027627a11c00000040a31c000000c643040183c35439df0f84e30000008b'),
    bytes.fromhex('7304f7c60100000074d5ebe8837c24080875268b2b89e9b820770c00ffd088430889e9b850770c00'),
    bytes.fromhex('ffd088430989e9b880770c00ffd088430a807b0632763f89f083c804884304837c2408087554a10c'),
    bytes.fromhex('000000a804742e0fb643080fb64b098d14080fb66b0a01ea83fa037e1883c00339c1721189f083c8'),
    bytes.fromhex('0c884304eb07837c240808751d0fb64308400fb6530939d07310a12000000040a320000000e952ff'),
    bytes.fromhex('ffff807b0b027610a12400000040a324000000e93cffffff807b0c017710a12800000040a3280000'),
    bytes.fromhex('00e926ffffff804b0402a11800000040a318000000e912ffffff837c2408087521a1140000008b54'),
    bytes.fromhex('243083fa087605ba080000000fb69a441b0000d1e80fafd8eb068b1d18000000837c2408070f94c1'),
    bytes.fromhex('0f94c20fb6d269442470830000006b7424300701f08b7c240801f88b742464f7de81e6d103000001'),
    bytes.fromhex('c689f0c1e81031f069c06bcaeb8589c6c1ee0d31f069c035aeb2c289c6c1ee1031f0898424900000'),
    bytes.fromhex('00c1eb04899c248c00000031c083ff080f95c08944243cff4c243c8364243cf48344243c4189c8c1'),
    bytes.fromhex('e01f89442468c17c24681f836424681131ff897c241c897c244c897c24446bc21189842498000000'),
    bytes.fromhex('8b8424900000008b7c244401f883e01f894424046bc0548a8404640100008844247683e0123c020f'),
    bytes.fromhex('854609000031c0c68404b7000000004083f81175f28b1578c2e3006b442404548944246c8b840460'),
    bytes.fromhex('010000894424148b802401000029c28994248800000031db31c9898c2480000000c7442410ff0000'),
    bytes.fromhex('0031f68974242089742428897424188974247c8b54246c31f689742448bdff000000be00010000b8'),
    bytes.fromhex('010000008a88a01b0000837c240807752084c974620fb6bc14a40100000fb688b41b00004139cf0f'),
    bytes.fromhex('92c10fb6c989cfeb0684c9744231ff80bc04b70000000075368b4c246880bc01201b00000074288a'),
    bytes.fromhex('8c149301000080f93f760485ff74180fb6f939f7731180f93f0f97c10fb6c9894c244889fe89c540'),
    bytes.fromhex('4283f811758681fdff0000000f8436080000c6842cb7000000010fb684acc8000000837c24480074'),
    bytes.fromhex('0f31d2895424243c08762983e808eb208b7c246c81c7e00b00008d143c0fb6941590f5ffff8d7a03'),
    bytes.fromhex('897c242439c77304894424248d84acc8000000894424788dbc246001000031c08944240c89442434'),
    bytes.fromhex('8b742434397424040f84170300008a47048844247783e0153c040f85050300008b078944243831db'),
    bytes.fromhex('31c08944245031f60fb6570639d3732d8b4424388d04988b0885c9741d89c8e893f3ffff39c57512'),
    bytes.fromhex('4689c8e823f3ffff3944245073048944245043ebcb0fb685781b00004039c6723b0fb64c2f430fb6'),
    bytes.fromhex('85b41b00004039c1722a8b4424388d0490898424840000008b442438894424408b4424208944245c'),
    bytes.fromhex('31c0894424608944242ceb3fa14400000040a344000000e9690200008b4424408b1885db75378b44'),
    bytes.fromhex('2460894424588b74245c8b5c242c83442440048b442458894424608974245c895c242c8b74244039'),
    bytes.fromhex('b4248400000075c4e9ed01000089d8e8dbf2ffff39c575be8a4325884424548a4324f743200000c0'),
    bytes.fromhex('bf75168b4b2481e100000070750ba80f7407f64424541e750da13400000040a334000000eb88837c'),
    bytes.fromhex('24080775238b15b876e50085d274198a532731d0a80f7510a13800000040a338000000e95effffff'),
    bytes.fromhex('894c245889d8e808f2ffff89c68a4353a801753c0fb6470739c6733480bd8c1b0000008b4c245874'),
    bytes.fromhex('088b44245039c6731f8b4424780fb6400339c67313f64424541c751c8b4424780fb6400139f07310'),
    bytes.fromhex('a13c00000040a33c000000e9fefeffff898c249c00000089da8b442438e88ef2ffff8944245885c0'),
    bytes.fromhex('8b8c249c000000741ef6442477087407f6442454187510a14000000040a340000000e9bffeffff8b'),
    bytes.fromhex('44242439c672063974245c7210a14800000040a348000000e9a1feffff8d04198b0089840c0c0100'),
    bytes.fromhex('0083c10483f95475ec0fb74b0ab8f05f0e00ffd08944245489d9b800ed1300ffd081a42430010000'),
    bytes.fromhex('ffff0fff8b4c245429c1b800600e00ffd066898424160100008d8c240c010000b880630e00ffd08b'),
    bytes.fromhex('94248800000029c28b0db876e500b80400000083f9037705a1b876e5006bc02d0578030000c1e802'),
    bytes.fromhex('01c039c27d10a14c00000040a34c000000e908feffff89d8e831f1ffff85c07410a15000000040a3'),
    bytes.fromhex('50000000e9edfdffff89d8e858f1ffff85c00f84eefdffffebdf837c242c0074348b44242ce881f0'),
    bytes.fromhex('ffff894424208b44244889842480000000896c24108b442460894424288b442434894424188b4424'),
    bytes.fromhex('2c8944240cff44243483c754837c2434200f85c9fcffffff44247cbb01000000837c240c00751683'),
    bytes.fromhex('7c247c030f85a9fbffff837c240c000f84a5060000837c2428007413a15400000040a354000000c7'),
    bytes.fromhex('4424280100000083bc2480000000007410a15800000040a358000000834c2428048b442464f7d883'),
    bytes.fromhex('e0088b7c242809c7897c24388b4424108d9484c80000000fb64a02b803000000394c2420731d0fb6'),
    bytes.fromhex('4a01b804000000394c2420730e0fb6023944242019c0f7d083c0068b74240c8a562583e21f80fa09'),
    bytes.fromhex('83d8ff8a562483e20ffeca750140837c24080775014083f8077605b8070000008b7c24048d8f94c0'),
    bytes.fromhex('e30089c2c1e20501ca0fb61239d774154889c2c1e20501ca0fb61231c9894c242439d7750d8b5424'),
    bytes.fromhex('04c1e20609c289542424c784240c010000090000008b442404898424100100008b44241089842414'),
    bytes.fromhex('0100008b442470898424180100008b4424088984241c0100008b44243089842420010000a11829b7'),
    bytes.fromhex('008b50048b44240c29d0b95400000031d2f7f1898424240100006b442404540fb694046801000089'),
    bytes.fromhex('9424280100000fb68404690100008984242c010000c74424405454504331d28b4c2440338c940c01'),
    bytes.fromhex('000089c8c1e81031c869c06bcaeb8589c1c1e90d31c869c035aeb2c289c1c1e91031c88944244042'),
    bytes.fromhex('83fa0975ca8b4424108bb424980000008a8430201b0000884424546b442404540fb6840466010000'),
    bytes.fromhex('31f68b7c243c39f80f828b0100008b4424140fb6801c0100008944245031ed896c243431f6897424'),
    bytes.fromhex('28c74424480000000031ff897c242c31f6837c2428410f843d0100008b7c2450397c24280f832f01'),
    bytes.fromhex('00008b4424148b5c24288d04988b3885ff0f84f600000089f8e849eeffff89c183f8020f86e40000'),
    bytes.fromhex('003dff0000000f84d900000031db31ed8b4424148d04a88b0085c0740ae81deeffff39c175014345'),
    bytes.fromhex('8b44245039c5730583fd4175db394c2410750143837c24340075090fb681641b0000eb17837c2434'),
    bytes.fromhex('0175090fb681501b0000eb070fb681781b000039d8737e89fa8b442414e856eeffff85c0756f89f8'),
    bytes.fromhex('e8d9edffff85c0756489f8e810eeffff85c075598a47270fb7570ab93c000000240f74060fb6c06b'),
    bytes.fromhex('c83c39d10f93c30f93c00fb6c089c5ba0100000089f9b8806d2400ffd085f67435f644242c017504'),
    bytes.fromhex('84db75258b44242c39c5750fd9442448d8d9dfe09e7717ddd8eb02ddd8d94424488b6c242c89f7eb'),
    bytes.fromhex('05bd01000000ff442428d95c2448896c242c89fee9b8feffff85f6750fff442434837c2434030f85'),
    bytes.fromhex('8ffeffff834c243802837c2424007515a16400000040a364000000b803000000e95d010000b94042'),
    bytes.fromhex('0f008b44244031d2f7f10fb64424548b9c248c0000000fafc339c27210a16800000040a368000000'),
    bytes.fromhex('e9d6000000837c244c057615a16c00000040a36c000000b806000000e911010000f6442438027419'),
    bytes.fromhex('85f67515a15c00000040a35c000000b808000000e9f100000031c031db899c840c0100004083f80f'),
    bytes.fromhex('75f1c784240c010000020000006b442418548b840460010000898424140100008b44240c89842418'),
    bytes.fromhex('0100008b4424148984242c0100008b4424248984243c010000bb010000006bc33c8b807cc2e30085'),
    bytes.fromhex('c0744c4383fb0f75eda17400000040a3740000008b8424000c0000c70001000000b805000000eb6a'),
    bytes.fromhex('85db0f852a020000a12c00000040a32c000000ff442444837c2444200f857ef6ffffe91b0200008b'),
    bytes.fromhex('3d1000000083e7010f848a0000006b442404548a54247683ca10889404640100006b44241854808c'),
    bytes.fromhex('046401000010ff44244ca17800000040a378000000b802000000ff7424388b5c24140fb6949ccc00'),
    bytes.fromhex('0000526b54240c548db2e80b00008d14348b5c24180fb69413b2f5ffff52ff74242cff742434ff74'),
    bytes.fromhex('242050ff74242c8b4c24388b5424248b442428e8f4edffff83c420e953ffffff85f6744789f0e844'),
    bytes.fromhex('ebffff89c5668b462866c1e80a83e0078944242850506a016a0189f28b4c2424b800d92b00ffd05a'),
    bytes.fromhex('598b4c242889ea8b442414e8d6ecffffa16000000040a3600000008db424ac0000008dac24b00000'),
    bytes.fromhex('008d84240c0100006a005556b990ae2b00ffd185c07515a17000000040a370000000b804000000e9'),
    bytes.fromhex('26ffffff6bdb3c8d837cc2e3006b542404548a4c247683c910888c14640100006b54241854808c14'),
    bytes.fromhex('6401000010ff44244c8d8b80c2e3008d14398bb43c10010000893283c70483ff3075ec66c783b0c2'),
    bytes.fromhex('e3000000c7837cc2e300020000006b4c241c188b9c249400000001d989018b74240c8971048b7c24'),
    bytes.fromhex('048979088b5c241889590c8b7424248971108b7c240c668b5f2866895c241489da66c1ea0a83e207'),
    bytes.fromhex('c1e2088b74241009f28951148b7c241c8904bd000000008b1d00000000ba0100000089d08a4c2404'),
    bytes.fromhex('d3e009d88a4c2418d3e209d0a300000000ff44241ca17c00000040a37c000000b801000000e938fe'),
    bytes.fromhex('ffffa13000000040a330000000e9d1fdffff8b44241c81c4ec0b00005b5e5f5dc35557565381ecd8'),
    bytes.fromhex('00000089c68954242031ed896c24388b1d6cf0e3008b3d1829b70031c0a300000000a304000000a3'),
    bytes.fromhex('08000000a30c000000a310000000a3140000008d442438508b5424248d442440e8daecffff894424'),
    bytes.fromhex('28893424b800c92b00ffd031c0a300000000a304000000a308000000a30c000000a310000000a314'),
    bytes.fromhex('00000083c40c31f681fb57020000776785ff7463a16cf0e30039d8745a81fe5802000074526bd30c'),
    bytes.fromhex('8b8278f0e3008b9270f0e30083e21f83fa07752d8b571c39d072268b571c8b2d0000000029d0b9f4'),
    bytes.fromhex('01000031d2f7f1ba0100000088c1d3e289d009e8a3000000004381fb58020000750231db46eb918d'),
    bytes.fromhex('5c243031ff897c240c8b7c2418397c240c0f84db0100008b0b8b018b6b0483f802752f8b410c39e8'),
    bytes.fromhex('752852526a016a0131d2b860b62b00ffd0a18400000040a384000000595ec7042407000000e96d01'),
    bytes.fromhex('00008b43088944240489c1b8504c0c00ffd089c131c00fb6911c01000039d0731183f841740c8d14'),
    bytes.fromhex('818b1239ea740a40ebe431c0890424eb07c70424010000008b7314833c24000f8417010000a18000'),
    bytes.fromhex('000040a380000000bf504c0c008b4c2404ffd7894424048b4b0cffd789c789e8e802e8ffff894424'),
    bytes.fromhex('0889e8e893e7ffff8944241cc1ee0889f18b54240889f8e8aae9ffff8b4424040fb6801c01000089'),
    bytes.fromhex('44241031f631ff83fe4174428b44241039c6733a8b4424048d04b08b0885c9742a39e9742689c8e8'),
    bytes.fromhex('abe7ffff3944240875198a4152a801740347eb0f89c8e830e7ffff8b4c241c39c873ee46ebb989fe'),
    bytes.fromhex('83ff077605be0700000031ff83ff41744b8b44241039c773438b4424048d04b88b0885c9743339e9'),
    bytes.fromhex('742f89c8e856e7ffff394424087522668b512866c1ea0a89d083e00783e20739f2720e6683f80774'),
    bytes.fromhex('084289c8e8a2e8ffff47ebb089f289e8e896e8ffffa19400000083c002a394000000eb0ba1880000'),
    bytes.fromhex('0040a3880000008b4b0c8b53086a406a006a006a00ff731055ff7424180fb64314508b442434e881'),
    bytes.fromhex('e9ffffff44242c83c31883c420e917feffff8b44242c81c4cc0000005b5e5f5dc35653508b742410'),
    bytes.fromhex('8b1da476e500a10000000040a300000000a1000000003d435055547514a1040000003d5244763175'),
    bytes.fromhex('08a10800000048740da10400000040a304000000eb5b83fb087527a10c000000a80174428b15b476'),
    bytes.fromhex('e5000fb605c551510039c2724ca10c00000040a30c000000eb2f83fb07751fa10c000000a8027416'),
    bytes.fromhex('a1b876e50085c07528a11000000040a310000000eb0ba10800000040a30800000083ec0c56b800c9'),
    bytes.fromhex('2b00ffd083c40ceb3b31c0a30000000031c989da89f0e846fcffff85c07425a110000000a801751c'),
    bytes.fromhex('a19000000040a390000000b90100000089da89f05b5b5ee91dfcffff585b5ec38b54240431c08b0c'),
    bytes.fromhex('850000000085c9741c8b0c850000000039d17511a19800000040a398000000b801000000c34083f8'),
    bytes.fromhex('0675d331c0c3669066906690669066906690669066906690000000100404040d0004000902020209'),
    bytes.fromhex('090000000c101010020003000e0909090c0c0000010101010202020408000000021e1e0606020203'),
    bytes.fromhex('010300050203040404000000031e1e1e1e1e1e1e021e001e1e1e1e1e1e0000000201010505020203'),
    bytes.fromhex('00030005020303030400000001000001010000000000000000000101010000000100000202010101'),
    bytes.fromhex('00010002010202020200000001010103030101010101000401020202020000000001020304050607'),
    bytes.fromhex('08090b0b0c0d0e0f10'),
    b'\xcc' * 39,
    bytes(1024),
))

# (field offset, PC-relative, address family, offset including ELF addend)
_RELOCATIONS = (
    (0x0006, True, 'page', 0x19e5),
    (0x0015, True, 'page', 0x1ad4),
    (0x00bb, False, 'page', 0x1bc8),
    (0x020a, False, 'page', 0x1bb4),
    (0x0357, False, 'page', 0x1ce0),
    (0x0376, False, 'page', 0x1d00),
    (0x037d, False, 'page', 0x1d00),
    (0x03ce, False, 'page', 0x1d08),
    (0x03d9, False, 'page', 0x1d0a),
    (0x03e3, False, 'page', 0x1d0c),
    (0x03ed, False, 'page', 0x1d0d),
    (0x03f7, False, 'page', 0x1d0e),
    (0x0401, False, 'page', 0x1d0f),
    (0x040a, False, 'page', 0x1ce0),
    (0x040f, False, 'page', 0x1cac),
    (0x0415, False, 'page', 0x1cac),
    (0x045f, False, 'page', 0x1c34),
    (0x0465, False, 'page', 0x1c34),
    (0x069e, False, 'page', 0x1ba0),
    (0x0705, False, 'page', 0x1cfc),
    (0x081c, False, 'page', 0x1ba0),
    (0x096e, False, 'page', 0x1c3c),
    (0x0974, False, 'page', 0x1c3c),
    (0x09d7, False, 'page', 0x1c0c),
    (0x0a1b, False, 'page', 0x1c40),
    (0x0a21, False, 'page', 0x1c40),
    (0x0a31, False, 'page', 0x1c44),
    (0x0a37, False, 'page', 0x1c44),
    (0x0a47, False, 'page', 0x1c48),
    (0x0a4d, False, 'page', 0x1c48),
    (0x0a5b, False, 'page', 0x1c38),
    (0x0a61, False, 'page', 0x1c38),
    (0x0a72, False, 'page', 0x1c14),
    (0x0a87, False, 'page', 0x1b44),
    (0x0a94, False, 'page', 0x1c18),
    (0x0be6, False, 'page', 0x1ba0),
    (0x0c00, False, 'page', 0x1bb4),
    (0x0c28, False, 'page', 0x1b20),
    (0x0d38, False, 'page', 0x1b78),
    (0x0d49, False, 'page', 0x1bb4),
    (0x0d7d, False, 'page', 0x1c64),
    (0x0d83, False, 'page', 0x1c64),
    (0x0e02, False, 'page', 0x1c54),
    (0x0e08, False, 'page', 0x1c54),
    (0x0e29, False, 'page', 0x1c58),
    (0x0e2f, False, 'page', 0x1c58),
    (0x0e56, False, 'page', 0x1b8c),
    (0x0e89, False, 'page', 0x1c5c),
    (0x0e8f, False, 'page', 0x1c5c),
    (0x0ec8, False, 'page', 0x1c60),
    (0x0ece, False, 'page', 0x1c60),
    (0x0ee6, False, 'page', 0x1c68),
    (0x0eec, False, 'page', 0x1c68),
    (0x0f7f, False, 'page', 0x1c6c),
    (0x0f85, False, 'page', 0x1c6c),
    (0x0f9a, False, 'page', 0x1c70),
    (0x0fa0, False, 'page', 0x1c70),
    (0x1035, False, 'page', 0x1c74),
    (0x103b, False, 'page', 0x1c74),
    (0x1052, False, 'page', 0x1c78),
    (0x1058, False, 'page', 0x1c78),
    (0x11e3, False, 'page', 0x1b20),
    (0x12b6, False, 'page', 0x1b64),
    (0x12c6, False, 'page', 0x1b50),
    (0x12cf, False, 'page', 0x1b78),
    (0x1399, False, 'page', 0x1c84),
    (0x139f, False, 'page', 0x1c84),
    (0x13ce, False, 'page', 0x1c88),
    (0x13d4, False, 'page', 0x1c88),
    (0x13e5, False, 'page', 0x1c8c),
    (0x13eb, False, 'page', 0x1c8c),
    (0x1405, False, 'page', 0x1c7c),
    (0x140b, False, 'page', 0x1c7c),
    (0x1482, False, 'page', 0x1c94),
    (0x1488, False, 'page', 0x1c94),
    (0x14a9, False, 'page', 0x1c4c),
    (0x14af, False, 'page', 0x1c4c),
    (0x14c9, False, 'page', 0x1c10),
    (0x14fb, False, 'page', 0x1c98),
    (0x1501, False, 'page', 0x1c98),
    (0x15a1, False, 'page', 0x1c80),
    (0x15a7, False, 'page', 0x1c80),
    (0x15d0, False, 'page', 0x1c90),
    (0x15d6, False, 'page', 0x1c90),
    (0x1693, False, 'page', 0x1ce4),
    (0x1699, False, 'page', 0x1cfc),
    (0x16b5, False, 'page', 0x1cfc),
    (0x16be, False, 'page', 0x1c9c),
    (0x16c4, False, 'page', 0x1c9c),
    (0x16d3, False, 'page', 0x1c50),
    (0x16d9, False, 'page', 0x1c50),
    (0x1716, False, 'page', 0x1ce4),
    (0x171b, False, 'page', 0x1ce8),
    (0x1720, False, 'page', 0x1cec),
    (0x1725, False, 'page', 0x1cf0),
    (0x172a, False, 'page', 0x1cf4),
    (0x172f, False, 'page', 0x1cf8),
    (0x1756, False, 'page', 0x1ce4),
    (0x175b, False, 'page', 0x1ce8),
    (0x1760, False, 'page', 0x1cec),
    (0x1765, False, 'page', 0x1cf0),
    (0x176a, False, 'page', 0x1cf4),
    (0x176f, False, 'page', 0x1cf8),
    (0x17b8, False, 'page', 0x1cfc),
    (0x17d5, False, 'page', 0x1cfc),
    (0x1822, False, 'page', 0x1ca4),
    (0x1828, False, 'page', 0x1ca4),
    (0x1886, False, 'page', 0x1ca0),
    (0x188c, False, 'page', 0x1ca0),
    (0x198e, False, 'page', 0x1cb4),
    (0x1996, False, 'page', 0x1cb4),
    (0x199d, False, 'page', 0x1ca8),
    (0x19a3, False, 'page', 0x1ca8),
    (0x19f7, False, 'page', 0x1c20),
    (0x19fd, False, 'page', 0x1c20),
    (0x1a02, False, 'page', 0x1c00),
    (0x1a0e, False, 'page', 0x1c04),
    (0x1a1a, False, 'page', 0x1c08),
    (0x1a22, False, 'page', 0x1c24),
    (0x1a28, False, 'page', 0x1c24),
    (0x1a34, False, 'page', 0x1c0c),
    (0x1a4e, False, 'page', 0x1c2c),
    (0x1a54, False, 'page', 0x1c2c),
    (0x1a60, False, 'page', 0x1c0c),
    (0x1a72, False, 'page', 0x1c30),
    (0x1a78, False, 'page', 0x1c30),
    (0x1a7f, False, 'page', 0x1c28),
    (0x1a85, False, 'page', 0x1c28),
    (0x1a9c, False, 'page', 0x1cfc),
    (0x1ab0, False, 'page', 0x1c10),
    (0x1ab9, False, 'page', 0x1cb0),
    (0x1abf, False, 'page', 0x1cb0),
    (0x1ae1, False, 'page', 0x1ce4),
    (0x1aec, False, 'page', 0x1ce4),
    (0x1af5, False, 'page', 0x1cb8),
    (0x1afb, False, 'page', 0x1cb8),
)

LABELS = {
    'story_entry': 0x10,
    'story_is_ours': 0x1ad8,
    'trade_call': 0x19e9,
    'trade_entry': 0x0,
}

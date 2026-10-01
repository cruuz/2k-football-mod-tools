"""Finite, ordered position-pool traversal in the retail next-candidate span.

No persistent state, new cave, or change to the first-candidate/eligibility callers.
Reconstruct the ordered stream on each call, marking physical lists and roster
indices before advancing past the current player. The two passes retain the
native allowed-mask preference and tier relaxation. Pool aliases can therefore
neither restart a list nor return a player a second time.
"""
from .nfl2k5_draft_ai import _Asm

VA = 0xE8410
SIZE = 0x380
RETAIL = bytes.fromhex(
    "83ec2c33c03bd0894c2404740e33c98a4a0483e13f894c2414eb04894424143b"
    "d08944240c894424248944241c750833c083c42cc20c005355568b74243c0fb6"
    "44320533c98a4a048bd8c1e80583e31f578bd6895c241083e13f89442430e8bd"
    "9d13008b7c24480fb64f3589442428e85c9a13008be88bcde873201800894424"
    "1833c98bc383e803894c2440740348753f8d74242033d28bc3c744242c010000"
    "00e87af0ffff8b5c2414578bf8e86ef4ffff85c08b5c2410740db80100000089"
    "4424408bc8eb238b4c2440eb038d49008bc3e889f0ffff3be874064183f9137c"
    "ef894c2440b8010000008b54242885542418741b83f913894424340f8ce20000"
    "0089442440c744241c000000008bc8394424440f8e4202000083f9130f8d3902"
    "00008bc3e837f0ffff85c98bf87e1283ff030f841502000083ff040f840c0200"
    "008b5424308d7424208bc7e8d0efffff8b6c24148bd88bcb8bd5e831f0ffff8b"
    "4c24448b148d3c04a900894424188b44242452506a008bc5e8b3f0ffff8bf039"
    "7424180f8ebc0100008bcfe8601f18008b4c242885c10f85a90100008b44241c"
    "85c08b7c24180f85950100003bf70f8d910100008b44243485c00f8567010000"
    "56558bc333c9e835f2ffff394424480f8452010000463bf77cdae9660100008b"
    "4c24408bc3e876efffff8be88b44244085c07e1283fd030f84f100000083fd04"
    "0f84e80000008b5424308d7424208bc5e80befffff8b7424148bd88bcb8bd689"
    "5c2420e868efffff8b5424248bf88b4424448b0c853c04a90051526a008bc689"
    "7c2424e8e8efffff8bf03bfe0f8e940000008bcde8971e18008b4c242885c10f"
    "84810000008b44241c85c08bee752a3bf77d738b54241455528bc333c9e87ef1"
    "ffff8b4c2448453bc874063bef7ce4eb55c744241c010000008b44242c85c074"
    "418b44244085c07e393bef7d398b4424108d74243833d2e864eeffff8b5c2414"
    "558bf88b4424245333c9e831f1ffff50e84bf2ffff85c08b7c24188b5c242074"
    "01453bef7c288b44244485c0746d8b4424408b5c24104083f813894424400f8c"
    "dbfeffffb801000000e9f3fdffff8b442414555033c98bc3e8e3f0ffff5f5e5d"
    "5b83c42cc20c0056558bc333c9c744242401000000e8c6f0ffff394424487501"
    "463bf77c228b5c24108b4c24404183f913894c24400f8cc7fdffff5f5e5d33c0"
    "5b83c42cc20c00565533c98bc3e88ef0ffff5f5e5d5b83c42cc20c0090909090"
)


def replacement() -> bytes:
    """fastcall(roster, descriptor, slot, tier, current) -> next or NULL.

    EBP anchors 112 bytes of local storage. Bits 0..27 identify physical
    lists; a separate 256-bit set identifies the byte-sized roster indices.
    Neither bitmap survives a call. Rebuilding the same ordered stream makes
    `current` a cursor without inferring its originating list from its enum.
    In particular an old-save OLB and a modern LB can share either LB chain.

    Stack: roster +00, formation +04, primary kind +08, rank +0c, mask +10,
    pass +14, fallback row index +18, list bits +1c, found-current +20,
    count +24, rank scratch +28, player bits +30..4f, tier +50,
    current +54. Arguments are +84/+88/+8c after the prologue.
    """
    a = _Asm(VA)
    a.b("53 55 56 57 83ec70 8bec 894d00")  # save nonvolatiles; frame
    a.b("31c0 894514 894518 89451c 894520")
    a.b("8d7d30 b908000000 f3ab")             # clear player bits
    a.b("8b4500 89c7 85d2")                  # EDI = roster
    a.j32("0f84", "exhausted")
    a.b("8b8588000000 894550 8b858c000000 894554")
    a.b("0fb64a04 83e13f 894d04")
    a.b("8b8584000000 0fb6440205 89c3 c1e805 89450c 83e31f 895d08")
    a.b("8b9584000000")
    a.call(0x222230)                         # formation slot mask
    a.b("894510")
    a.label("pool")
    a.b("8b4508 8b4d18")
    a.call(0xE7570)                          # unchanged fallback row
    a.b("837d1800")
    a.j8("74", "kind_ok")
    a.b("83f803")
    a.j32("0f84", "next_pool")
    a.b("83f804")
    a.j32("0f84", "next_pool")              # special lists only primary
    a.label("kind_ok")
    a.b("89c3 89c1")
    a.call(0x26A500)
    a.b("234510 0f95c0 0fb6c0 334514 85c0")  # (allowed != pass)
    a.j32("0f84", "next_pool")
    a.b("89d8 8b550c 8d7528")
    a.call(0xE7530)                          # preserve rank-selected chain
    a.b("0fab451c")                         # claim physical list once
    a.j32("0f82", "next_pool")
    a.b("89c3 89c1 89fa")
    a.call(0xE75A0)
    a.b("894524 8b4550 8b04853c04a900 50 ff7504 6a00 89f8")
    a.call(0xE7640)                          # native formation/tier start
    a.b("89c6")
    a.label("player")
    a.b("3b7524")
    a.j32("0f8d", "next_pool")
    # List entries are byte roster indices; 0xff terminates. Guard the scan
    # even for a damaged list count. Retail rosters have at most 53 entries.
    a.b("81feff000000")
    a.j32("0f83", "next_pool")
    a.b("8b849f9c000000 0fb60c30 81f9ff000000")
    a.j32("0f84", "next_pool")
    a.b("0fab4d30")
    a.j8("72", "next_player")
    a.b("8b07 8b0488 85c0")
    a.j8("74", "next_player")
    a.b("3b4554")
    a.j8("75", "candidate")
    a.b("c7452001000000")
    a.j8("eb", "next_player")
    a.label("candidate")
    a.b("837d2000")
    a.j32("0f85", "done")
    a.label("next_player")
    a.b("46")
    a.j32("e9", "player")
    a.label("next_pool")
    a.b("837d5000")
    a.j8("74", "exhausted")               # tier zero is primary only
    a.b("ff4518 837d1813")
    a.j32("0f8c", "pool")
    a.b("837d5001")
    a.j8("7e", "exhausted")
    a.b("837d1400")
    a.j8("75", "exhausted")
    a.b("c7451401000000 c7451800000000")
    a.j32("e9", "pool")
    a.label("exhausted")
    a.b("31c0")
    a.label("done")
    a.b("83c470 5f 5e 5d 5b c20c00")
    code = a.assemble()
    assert len(code) <= SIZE
    return code.ljust(SIZE, b"\x90")

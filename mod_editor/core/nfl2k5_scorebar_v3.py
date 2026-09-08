"""Pinned static scorebar v3 callbacks. EXPERIMENTAL / UNWITNESSED.

No allocator request, loading hook, resource lookup or cached team binding.
The native visibility function's own removed clock-hide logic makes room for
its shared draw callback. See docs/scorebug_ingame/rim/visibility_and_color.s.
"""
from __future__ import annotations

import struct

MATERIAL_INDICES = {"home": 6, "away": 10}
RIM_INDICES = {"home": 9, "away": 7}
SILVER = 0xffd1d2d3
COLOR_TABLE = (0x4e7fe0, 0x4e88a0, 0x1c)


def contrast_color(argb):
    """Hue-preserving darkening, maximum channel 112 for white/yellow text."""
    if max((argb >> shift) & 255 for shift in (0, 8, 16)) <= 112:
        return 0xff000000 | (argb & 0x00ffffff)
    return 0xff000000 | (((argb & 0x00fefefe) >> 1) - ((argb & 0x00f0f0f0) >> 4))


def rim_color(primary, secondary, *, known=True):
    """Use the opaque retail primary, then a distinct secondary, else silver.

    The pinned retail table has no absent colour words. A missing team/code
    or the native accessor's unknown-code default is not a team palette.
    """
    if not known or primary == 0xff0065e6:
        return SILVER
    panel = contrast_color(primary) if primary is not None else 0xff252625
    candidate = secondary if primary is None or primary == panel else primary
    return SILVER if candidate is None or candidate == panel else candidate


def xbe_specs():
    specs = [(VISIBILITY_VA, RETAIL_VISIBILITY, VISIBILITY_CODE,
              "persistent middle and lazy panel/rim colours in native visibility span")]
    for va, getter, side in ((0xfc010, 0x61c50, "home"), (0xfc030, 0x61c60, "away")):
        def branch(opcode, source, target):
            return bytes((opcode,)) + struct.pack("<i", target-source-5)
        old = (b"\x56\x8b\xf1" + branch(0xe8, va+3, getter) + b"\x8b\x90\x3c\x01\x00\x00\x8b\xce" +
               branch(0xe8, va+16, 0x30ab0) + b"\x8b\xce\x5e" + branch(0xe9, va+24, 0x30f50))
        new = b"\x56\x8b\xf1" + branch(0xe8, va+3, getter)
        new += b"\xba" + struct.pack("<I", MATERIAL_INDICES[side]*128)
        new += branch(0xe8, va+len(new), COLOR_VA)
        new += b"\x8b\xce\x5e"
        new += branch(0xe9, va+len(new), 0x30f20)
        specs.append((va, old, new.ljust(len(old), b"\x90"), "live "+side+" name and panel/rim colours"))
    # Reuse one obsolete corner-mark material for the home panel. Its new
    # name is an existing immutable literal; no new string or texture lookup.
    specs.append((0xa95cb0, struct.pack("<I", 0xe6c780), struct.pack("<I", 0xe6c6e8),
                  "home panel uses the existing score_buga material name"))
    old = bytes.fromhex("51568bf1e8d7fcffff894424048d44240450ba38c4e6008bcee8b2e5f4ff5e59c3")
    new = bytearray(old)
    new[4:9] = b"\xe8" + struct.pack("<i", CLOCK_VA-0xfbe39)
    new[19:23] = struct.pack("<I", 0xe6c43a)
    specs.append((0xfbe30, old, bytes(new), "live play clock or -- without changing its cell"))
    # Both half-frame materials and the neutral marks are now used in both
    # placement modes. Keep the native material walk; clear its hidden bit in
    # both branches instead of hiding the alternate full frame/corner mark.
    for va in (0xfc285, 0xfc305):
        specs.append((va, bytes.fromhex("83c801"), bytes.fromhex("83e0fe"),
                      "both rim sides and neutral marks visible in either mode"))
    return specs

VISIBILITY_VA = 0xfca87
COLOR_VA = 0x000fcbf2
CLOCK_VA = 0x000fcca7
RETAIL_VISIBILITY = bytes.fromhex(
    "8b35b402e6003bf70f842f020000538b1dec02e60039bb60010000751639bb98000000740a8d83900000003bc7750433"
    "d2eb05ba01000000a18002e6003bc78b0db802e6008915505ba9000f84050100008b400c83c0040f84f90000008b4004"
    "3bc70f84ee0000008b4004c1e80883e03f83f80a757883f90e0f85d70000003bd70f85cf000000d905345ca900c705e0"
    "5aa90001000000d81d245ca900dfe0f6c4447b06893de05aa900d905545ba900893d005aa900d81d445ba900dfe0f6c4"
    "447a168b159402e600f6421806c705705aa900010000007406893d705aa9005b893dc05ba9005f5e83c408c2040083f8"
    "0c756383fe03745e8bc183e80c74034875543bd77550d905545ba900b901000000d81d445ba900890d102fba00893de0"
    "5aa900890d005aa900dfe0f6c4447a11a19402e600f6401806890d705aa9007406893d705aa9005b5f890dc05ba9005e"
    "83c408c20400d905545ba9008b15fc02e600d81d445ba900893de05aa900dfe0f6c4447a4c84f67848d905345ca900d8"
    "1d245ca900dfe0f6c4447a3583fe04753083f90e742b393d142fba00be010000008935005aa9007510397c240c741d83"
    "f90c740583f90d75138935c05ba900eb11893d005aa900be01000000893dc05ba90083f90e7521d905545ba900d81d44"
    "5ba900dfe0f6c4447a0e39bb980100008935305ca9007506893d305ca900d905545ba900d81d445ba900dfe0f6c4447a"
    "1684f678128b0d9402e600f64118068935705aa9007406893d705aa900e8d7f1faff85c074068935c05ba9005b5f5e83"
    "c408c20400"
)
VISIBILITY_CODE = bytes.fromhex(
    "8b35b402e60039fe0f84550100005355bdb05ba9008b1dec02e60031d239bb60010000751039bb9800000074"
    "0981fb70ffffff740142a18002e60039f88b0db802e6008955a0747b8b400c83c00474738b400439f8746c8b"
    "4004c1e80883e03f83f80a753183f90e755939fa7555d98584000000c78530ffffff01000000d85d74dfe0f6"
    "c4447b0689bd30ffffff897d10e9bc00000083f80c752883fe0374238d41f483f801771b39fa75176a015989"
    "0d102fba0089bd30ffffff894d10e98f000000d945a48b15fc02e600d85d9489bd30ffffffdfe0f6c4447a3e"
    "84f6783ad98584000000d85d74dfe0f6c4447a2a83fe04752583f90e7420393d142fba006a015e7510397c24"
    "10741283f90c740583f90d7508897510eb066a015e897d1083f90e751bd945a4d85d94dfe0f6c4447a0e39bb"
    "9801000089b580000000750689bd80000000e8bef2faff85c074038975106a0158898550feffff8985c0feff"
    "ff5d5b5f5e83c408c204006089d789c385c074258b903c01000085d2741b89f1e8a43ef3ff83bb0c01000000"
    "741089d9e854c1f6ff89c5eb0d66c7060000b8252625ff50eb4da980808000751089c181c10f0f0f00f7c180"
    "808000741489c125fefefe00d1e881e1f0f0f000c1e90429c80d000000ff5081fde66500ff741439e8750e89"
    "d9e84fc1f6ff89c53b04247402eb05bdd3d2d1ff588b0d2855a90085c9741b83791c0b75158b492085c9740e"
    "89443918d1ef29f989a91806000061c38b0d9402e600e30bf64118067505e956eeffff58c7062d002d0066c7"
    "46040000e982f1ffff"
).ljust(len(RETAIL_VISIBILITY), b"\x90")

GUARDS = [(1034887, 581, 'e563e5240911c235ffb43a773f40a319fe53e9af03aa6b98403f38b2931ef44d', 'scorebar visibility and lazy colour span'), (429424, 67, 'f427d83eb8f774be881e8818e9bf807f3c265c83ccedcfe2005c6e5a3c088ee5', 'native team primary accessor'), (199568, 174, '0e2eee1e67c709089c59e72bd3de909c3c9e22f9de49da13a47d9ed9d64a9de2', 'native asset-code comparison'), (5144544, 2240, '0713d8ca89333142d86dad04904d4804ea76687301a50df7265b5407302036e6', 'retail team colour table'), (400464, 22, 'b70dd350e789fd545dc95d77207f46034dab8c79080209a477ba31f0a18a295d', 'live team contexts')]

GUARDS += [(0x68dc0, 67, "7412c79b246c86230e92cc796226fa92088f9441f6c9771f23656d6a8333a5dc", "native team secondary accessor"),
           (0xfc200, 298, "94527caeaa8869858229bb24ea66f39025d0338110601c47b1d83e490c383da6", "native frame material visibility")]

GUARDS += [(0xfc9c0, 0xc7, "461564bc4edab82c22f91d74fecfb8e00c4d8bea8b01586febfde695721d6296",
            "native visibility prefix and zero-register invariant")]

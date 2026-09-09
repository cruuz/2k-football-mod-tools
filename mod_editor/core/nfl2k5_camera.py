"""EXPERIMENTAL / UNWITNESSED Standard, Far and playable Broadcast, USA XBE.

Far is row 1 of 4F03F8. Standard retains retail Far's settled eye positions
with the raised Far pitch. Both rows retain native type, lag and callbacks,
with bounded live growth and modest optional pass zoom. The settings saved-load calls
and common game-camera initialization select the new Standard (Noah's choice, 2026-09-07);
the fresh-profile default already is Standard, so that retail site stays untouched.
Options remains a session choice. The automatic spectator branch uses that same choice.

Broadcast adapts the retail sideline descriptor to a following gameplay camera.
It is NOT a claim to reproduce the coach-mode television director: retail TV
records include inherited eyes and close-up framing. The seventh menu choice
uses engine row 7, skipping First Person (6), without setting Coach Mode.

160 owned RX bytes and one immutable 80-byte descriptor, no RW or retail cave.
Reserve REQUESTS with
all other selected owners before apply. Rebuild historical descriptor-only
installations from retail; mixed/foreign inputs refuse before mutation.
See ASTRA_CAMERA_V2_REPORT.md for native evidence and visual-proof limits.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from typing import Mapping

from . import nfl2k5_xbe_space as space
from .nfl2k5_draft_ai import _Asm
from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

OWNER = "nfl2k5_camera"
VERSION = 5
CODE_SIZE = 160
READ_ONLY_SIZE = 80
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "read_only", READ_ONLY_SIZE, 16))
IMAGE_BASE = 0x10000
DESCRIPTOR_SIZE = 0x50
FIELD_TARGET = 0x10
FIELD_FOV = 0x20
FIELD_OFFSET = 0x30
PRESET_TABLE_VA = 0x004F03F8       # 8 rows x 29 states x (flags u32, descriptor* u32)
STATES_PER_ROW = 0x1D
PRESET_NAMES = ("Standard", "Far", "Side", "Iso", "Blimp", "Custom", "1st Person", "Broadcast")
STANDARD_ROW = 0
FAR_ROW = 1
BROADCAST_ROW = 7
MENU_ROWS = (0, 1, 2, 3, 4, 5, BROADCAST_ROW)
# Every gameplay/preview state gets an independent eye, including kicks and
# pass states. Presentation/replay states and all seven other rows stay native.
BROADCAST_STATES = (1, *range(8, 20))
BROADCAST_TEMPLATE_VA = 0xA881E0
# v5.2 (Noah 2026-09-08 on disc bq: "still too far away, make it look like tv from a broadcast from the nfl last year"
# and "it isn't centered, offense at the left, defense in the middle, empty on the right"): the retail TV director's
# own wide line-of-scrimmage shot, made to follow the ball. Lens word 80 = the director's wide lens (its live shots
# use 120), about 1.85x closer on screen than v5.1 and 3.3x closer than v5; the look-at sits 2.5 m ahead of the ball
# (v5.1 led it by 12 m, which pushed the offense to one edge) and 4 m toward the near sideline so the near wideout
# clears the scorebug. Native projection: 16:9 shows about 17 yards behind the ball to 22 ahead, 4:3 about 13 to 17;
# the far sideline sits in the top quarter, the near sideline is below the frame; receivers 25 yards deep are outside
# until the camera follows the ball, as on television.
# v5.3 (beta 63.1; maumau78 2026-09-09 on beta 63: "on right side will clip over crowd and stadium structure"): v5.2
# used the template's press-box eye, 52.5 m toward the near sideline and 16.5 m up. A type-2 mount follows the ball
# across the field too, and 16.5 m is exactly the front-row height of the stadiums' second level (loge/club), whose
# front sits about 58 m from the field's centre line (Superdome 58.2, Arizona 59.7; measured on the retail stadium
# scenes), so with the ball past the near hash the eye was already among the second-level seats and crowd, and in
# the end zones inside the loge corner trim (14.3..18.9 m up). The mount now sits 45 m out and 14 m up, the front of
# the loge rather than the press box: the same pitch (17.3 degrees, v5.2 17.4), the lens widened from 80 to 68 so
# the framing at the ball is the same (every sample point within 10 px of v5.2 through the native solver), 15%
# closer in perspective. The eye now stays in front of the second level and below the corner trim for every ball
# from the far sideline to 9 m past the centre line toward the camera (the near hash is 2.8 m, the near numbers begin
# at 11 m), the whole field long, both end zones included; a constant-offset follow still moves it into the stands
# for plays wider than that (the native eye clamp box a setup callback could set is the complete fix; WIRING.md).
BROADCAST_VALUES = ((400.0, 0.0, 250.0), 68.0, (4500.0, 1400.0, 200.0))
OPTION_GLOBAL_VA = 0x00E5FFF0            # DAT_00e5fff0: the Options "Camera" value (= table row)
OPTION_DEFAULT_SITE_VA = 0x000E3C68      # FUN_000e3b90: `xor edi,edi ; mov dword ptr [0xE5FFF0], edi` (fresh-profile default 0)
RETAIL_OPTION_DEFAULT = bytes.fromhex("33ff893df0ffe500")   # xor edi,edi ; mov dword [0xE5FFF0], edi

# Seven scrimmage recipients, keyed by game state. State 1 aliases state 16.
STANDARD_DESCRIPTORS: dict[int, int] = {
    9: 0x00A88870,    # pre-snap scrimmage
    13: 0x00A888C0,   # after the catch
    15: 0x00A88A50,   # pass in the air ("Pass Play Zoom Out" adds its own pull-back)
    16: 0x00A88A00,   # the live play; also state 1 (play call) and the pause-menu camera preview
    17: 0x00A88910,   # live variant (ball carrier)
    18: 0x00A88960,   # live variant
    19: 0x00A889B0,   # live variant (look-at behind the ball)
}
# The seven Far recipients. Six retain r63-camera-far geometry exactly.
FAR_DESCRIPTORS: dict[int, int] = {
    9: 0x00A88B90, 13: 0x00A88BE0, 15: 0x00A88D70, 16: 0x00A88D20, 17: 0x00A88C30, 18: 0x00A88C80, 19: 0x00A88CD0,
}
STATE_LABELS = {9: "pre-snap", 13: "after the catch", 15: "pass in the air", 16: "live play",
                17: "live (carrier)", 18: "live", 19: "live (behind)"}

# Retail bytes of each descriptor (whole 0x50-byte record), the pattern that must match before writing.
RETAIL_DESCRIPTORS: dict[int, bytes] = {
    9: bytes.fromhex("020000000000000080034f00000000000000000000002f43000048430000000000000c42000000000000000000000000000000000000c8430080a2c40000000000000000000000000000000000000000"),
    13: bytes.fromhex("020000000000000080034f00000000000000000000000000000000000000000000000c420000000000000000000000000000000000004843000048c40000000000000000000000000000000000000000"),
    15: bytes.fromhex("020000000000000080034f0000000000000000000000c84200000000000000000000f041000000000000000000000000000000000000fa430000afc400000000d0490a00000000000000000000000000"),
    16: bytes.fromhex("020000000000000080034f0000000000000000000000c842000016c30000000000000c42000000000000000000000000000000000000874300803bc40000000090490a00504a0a000000000000000000"),
    17: bytes.fromhex("020000000000000080034f0000000000000000000000a04200008cc20000000000000c42000000000000000000000000000000000000c843004083c40000000050490a00000000000000000000000000"),
    18: bytes.fromhex("020000000000000080034f00000000000000000000000000000000000000000000000c420000000000000000000000000000000000004843000048c40000000050490a00000000000000000000000000"),
    19: bytes.fromhex("020000000000000080034f0000000000000000000000000000007ac40000000000000c42000000000000000000000000000000000000484400007ac40000000050490a00000000000000000000000000"),
}
# Retail bytes of the Far row's records (reference only: the far_look preset is derived from them).
FAR_RETAIL_DESCRIPTORS: dict[int, bytes] = {
    9: bytes.fromhex("020000000000000080034f00000000000000000000002f4300004843000000000000e041000000000000000000000000000000000000c8430080a2c40000000000000000000000000000000000000000"),
    13: bytes.fromhex("020000000000000080034f0000000000000000000000000000000000000000000000e0410000000000000000000000000000000000004843000048c40000000000000000000000000000000000000000"),
    15: bytes.fromhex("020000000000000080034f0000000000000000000000c84200000000000000000000c041000000000000000000000000000000000000fa43004083c400000000f04b0a00000000000000000000000000"),
    16: bytes.fromhex("020000000000000080034f0000000000000000000000c842000016c3000000000000e041000000000000000000000000000000000000874300803bc400000000c04b0a00304c0a000000000000000000"),
    17: bytes.fromhex("020000000000000080034f0000000000000000000000a04200008cc2000000000000e041000000000000000000000000000000000000c843004083c400000000904b0a00000000000000000000000000"),
    18: bytes.fromhex("020000000000000080034f0000000000000000000000000000000000000000000000e0410000000000000000000000000000000000004843000048c400000000904b0a00000000000000000000000000"),
    19: bytes.fromhex("020000000000000080034f0000000000000000000000a04200008cc2000000000000e041000000000000000000000000000000000000c843004083c400000000904b0a00000000000000000000000000"),
}

# Pinned native sideline recipient and the original row-7 pointers.
BROADCAST_RETAIL_DESCRIPTOR = bytes.fromhex(
    "000000000000000080034f0000000000000000000000000000000000000000000000f0420000000000000000000000000010a4450040ce44000048430000803fc0400a00000000000000000000000000")
BROADCAST_RETAIL_ENTRIES = {
    1: bytes.fromhex("030000000085a800"),
    8: bytes.fromhex("00000000b07fa800"),
    9: bytes.fromhex("00000000a080a800"),
    10: bytes.fromhex("000000005080a800"),
    11: bytes.fromhex("000000000080a800"),
    12: bytes.fromhex("00000000b084a800"),
    13: bytes.fromhex("00000000f080a800"),
    14: bytes.fromhex("000000005080a800"),
    15: bytes.fromhex("000000008082a800"),
    16: bytes.fromhex("000000003082a800"),
    17: bytes.fromhex("000000004081a800"),
    18: bytes.fromhex("000000009081a800"),
    19: bytes.fromhex("01000000e081a800"),
}

Values = tuple[tuple[float, float, float], float, tuple[float, float, float]]

# (look-at xyz, lens word, camera offset xyz), centimetres.  Retail Standard for reference.
RETAIL_VALUES: dict[int, Values] = {
    9: ((0.0, 175.0, 200.0), 35.0, (0.0, 400.0, -1300.0)),
    13: ((0.0, 0.0, 0.0), 35.0, (0.0, 200.0, -800.0)),
    15: ((0.0, 100.0, 0.0), 30.0, (0.0, 500.0, -1400.0)),
    16: ((0.0, 100.0, -150.0), 35.0, (0.0, 270.0, -750.0)),
    17: ((0.0, 80.0, -70.0), 35.0, (0.0, 400.0, -1050.0)),
    18: ((0.0, 0.0, 0.0), 35.0, (0.0, 200.0, -800.0)),
    19: ((0.0, 0.0, -1000.0), 35.0, (0.0, 800.0, -1000.0)),
}
# Retail Far: the same positions with the 28 lens (24 with the ball in the air), state 19 like 17.
FAR_RETAIL_VALUES: dict[int, Values] = {
    9: ((0.0, 175.0, 200.0), 28.0, (0.0, 400.0, -1300.0)),
    13: ((0.0, 0.0, 0.0), 28.0, (0.0, 200.0, -800.0)),
    15: ((0.0, 100.0, 0.0), 24.0, (0.0, 500.0, -1050.0)),
    16: ((0.0, 100.0, -150.0), 28.0, (0.0, 270.0, -750.0)),
    17: ((0.0, 80.0, -70.0), 28.0, (0.0, 400.0, -1050.0)),
    18: ((0.0, 0.0, 0.0), 28.0, (0.0, 200.0, -800.0)),
    19: ((0.0, 80.0, -70.0), 28.0, (0.0, 400.0, -1050.0)),
}

PRESETS: dict[str, dict[int, Values]] = {
    # Keep the existing public preset key while making Far the actual selection.
    "far_look": {
        9: ((0.0, 0.0, -250.0), 28.0, (0.0, 700.0, -1800.0)),
        13: ((0.0, 0.0, -250.0), 28.0, (0.0, 650.0, -1600.0)),
        15: ((0.0, 0.0, -250.0), 28.0, (0.0, 700.0, -1800.0)),
        16: ((0.0, 0.0, -350.0), 28.0, (0.0, 650.0, -1600.0)),
        17: ((0.0, 0.0, -250.0), 28.0, (0.0, 650.0, -1600.0)),
        18: ((0.0, 0.0, -250.0), 28.0, (0.0, 650.0, -1600.0)),
        19: ((0.0, 0.0, -250.0), 28.0, (0.0, 650.0, -1600.0)),
    },
    # The earlier proposal: an elevated, set-back view (about 23 yd back, 9-10 yd up, 20 degrees down)
    # with a lens between Standard 35 and Far 28.  Kept as an option; not the default.
    "broadcast_wide": {
        9: ((0.0, 120.0, 100.0), 32.0, (0.0, 900.0, -2200.0)),
        13: ((0.0, 0.0, 0.0), 32.0, (0.0, 850.0, -2100.0)),
        15: ((0.0, 100.0, 0.0), 30.0, (0.0, 1000.0, -2400.0)),
        16: ((0.0, 100.0, 0.0), 32.0, (0.0, 850.0, -2100.0)),
        17: ((0.0, 80.0, 0.0), 32.0, (0.0, 850.0, -2100.0)),
        18: ((0.0, 0.0, 0.0), 32.0, (0.0, 850.0, -2100.0)),
        19: ((0.0, 0.0, -600.0), 32.0, (0.0, 900.0, -2100.0)),
    },
}
DEFAULT_PRESET = "far_look"
PRESET_TITLES = {"far_look": "Far with room above the scorebar (experimental)",
                 "broadcast_wide": "Broadcast Wide (23 yd back, 9-10 yd up, lens 32)"}


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _middle_values(state: int) -> Values:
    # Native type 2 in 5F760 adds the offset TO the target. Preserve the
    # actual retail Far eye relative to the focus, not a mistaken absolute
    # interpretation of descriptor +30. Match the raised Far's optical pitch.
    old_target, lens, old_offset = FAR_RETAIL_VALUES[state]
    raised_offset = PRESETS[DEFAULT_PRESET][state][2]
    eye_y = old_target[1] + old_offset[1]
    eye_z = old_target[2] + old_offset[2]
    offset_z = _f32(eye_y * raised_offset[2] / raised_offset[1])
    target_z = _f32(eye_z - offset_z)
    return ((0.0, 0.0, target_z), 28.0 if state == 15 else lens,
            (0.0, eye_y, offset_z))


STANDARD_VALUES = {state: _middle_values(state) for state in STANDARD_DESCRIPTORS}
# Authored kick views use the original Far geometry, like unchanged new Far.
# 14 aliases 10. Shared return/presentation descriptors are guarded, not edited.
STANDARD_SPECIAL_DESCRIPTORS = {8: 0xA88780, 10: 0xA88820, 11: 0xA887D0}
FAR_SPECIAL_DESCRIPTORS = {8: 0xA88AA0, 10: 0xA88B40, 11: 0xA88AF0}
STANDARD_SPECIAL_RETAIL = {
    8: ((0., 460., -1012.), 36., (0., 210., -1100.)),
    10: ((0., 185., 0.), 35., (0., 245., -700.)),
    11: ((0., 0., 100.), 36., (0., 500., -1325.)),
}
STANDARD_SPECIAL_VALUES = {
    8: ((0., 555., -1432.), 28., (0., 120., -815.)),
    10: ((0., 185., 0.), 28., (0., 245., -700.)),
    11: ((0., 0., 0.), 28., (0., 500., -1325.)),
}
# These records share state 9's exact type/lag/callback template.

# (offset y, offset z, target z), written by existing pass-zoom setup stores.
# Native absolute eye is (target + offset), hence Standard (650,-1200),
# Far (750,-2150). Both remain close to their respective pre-snap distances.
PASS_ZOOM_VALUES = {
    STANDARD_ROW: (650.0, _f32(-650.0 * 1800 / 700),
                   _f32(-1200.0 - _f32(-650.0 * 1800 / 700))),
    FAR_ROW: (750.0, -1900.0, -250.0),
}


class CameraPatchError(ValueError):
    """The camera patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CameraPatchError(message)


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise CameraPatchError(f"VA 0x{va:x} is in no file-backed section")


def descriptor_bytes(retail: bytes, values: Values) -> bytes:
    """The retail record with only the look-at, lens and offset words replaced."""

    _require(len(retail) == DESCRIPTOR_SIZE, "descriptor template must be 0x50 bytes")
    target, fov, offset = values
    buf = bytearray(retail)
    struct.pack_into("<3f", buf, FIELD_TARGET, *target)
    struct.pack_into("<f", buf, FIELD_FOV, fov)
    struct.pack_into("<3f", buf, FIELD_OFFSET, *offset)
    return bytes(buf)


def decode_descriptor(record: bytes) -> dict[str, object]:
    _require(len(record) == DESCRIPTOR_SIZE, "descriptor must be 0x50 bytes")
    return {
        "type": struct.unpack_from("<I", record, 0)[0],
        "flag": struct.unpack_from("<I", record, 4)[0],
        "lag_block": struct.unpack_from("<I", record, 8)[0],
        "target": struct.unpack_from("<3f", record, FIELD_TARGET),
        "fov": struct.unpack_from("<f", record, FIELD_FOV)[0],
        "offset": struct.unpack_from("<3f", record, FIELD_OFFSET),
        "setup_callback": struct.unpack_from("<I", record, 0x40)[0],
        "frame_callback": struct.unpack_from("<I", record, 0x44)[0],
    }


STANDARD_SPECIAL_BYTES = {
    state: descriptor_bytes(RETAIL_DESCRIPTORS[9], values)
    for state, values in STANDARD_SPECIAL_RETAIL.items()
}


# Complete instructions, not just their changed operands. ESI=1 is pinned
# at E3B92; EDI remains zero for the adjacent pivot/zoom defaults.
HOOKS = {
    "settings_load_select": (0x16D1D4, bytes.fromhex("e8475cf7ff")),
    "franchise_load_select": (0x16E7B1, bytes.fromhex("e86a46f7ff")),
    "settings_reload_select": (0x16E864, bytes.fromhex("e8b745f7ff")),
    "game_entry_select": (0xA55EB, bytes.fromhex("e9a0feffff")),
    "spectator_session_choice": (0xA54C3, bytes.fromhex("7e06")),
    "standard_pass_zoom": (0xA4A2D, bytes.fromhex(
        "c7812404000000007a44c7812804000000401cc5c781080400000000fa43")),
    "far_pass_zoom": (0xA4C0C, bytes.fromhex(
        "c7812404000000007a44c7812804000000401cc5c781080400000000fa43")),
    "standard_live_cap": (0xA4B1A, bytes.fromhex("d905348aa800dcc0")),
    "far_live_cap": (0xA4D1F, bytes.fromhex("d905548da800dcc0")),
    "camera_menu_max": (0x2C66A0, bytes.fromhex("b805000000")),
    "camera_menu_width": (0x2C66D5, bytes.fromhex("6a05")),
    "camera_menu_next": (0x2C6B00, bytes.fromhex("8b0df0ffe500")),
    "camera_menu_previous": (0x2C6B40, bytes.fromhex("8b0df0ffe500")),
}
# Narrow immutable prerequisites. Whole table pins include kick/preview states,
# and reject redirected recipients. MyCareer's separate A5490 hook is outside
# these contexts and remains owned by that module.
CONTEXT_PINS = (
    (0xE3B90, bytes.fromhex("5356be0100000057")),
    (0xE2E20, bytes.fromhex("8bd168e0020000b980ffe500")),
    (0xE2E2C, bytes.fromhex("e8cfe1f4ffc3")),
    (0x16D1D2, bytes.fromhex("8bce")),
    (0x16D1D9, bytes.fromhex("e8225cf7ff8d0c30e89a82f3ffe87582f3ff")),
    (0x16E7AE, bytes.fromhex("8d0c33")),
    (0x16E7B6, bytes.fromhex("e84546f7ff03d88d0c33e8bb6cf3ff")),
    (0x16E862, bytes.fromhex("8bce")),
    (0x16E869, bytes.fromhex("e89245f7ff8d0c30e80a6cf3ffe8e56bf3ff")),
    (0xA54B7, bytes.fromhex("a1f065b60083f806741e85ff")),
    (0xA54C5, bytes.fromhex("8b1df0ffe5003bd87410891df065b600c705f465b600010000005f5e5bc3")),
    (0xA55E1, bytes.fromhex("c705e065b60001000000")),
    (0x4EDA58, struct.pack('<f', 500.0)),  # read-only pooled literal, never changed
)
# Hash-only guards are generated from the pinned USA executable, below.
CONTEXT_HASHES = (
    (0x4F03F8, 1856, "2b63b0b1c1d993ebf4b6eb6a502f8aa21417f14aa167262777ecbbab27badb93"),
    (0xA5B20, 480, "ba3262ce0f88dbf9fbf46cf6e4b783076b9ec7e05fa32dbade9bcf9fccf736d8"),
    (0x31000, 33, "6108e11605dbbba3cec8f5dbccc0c99915850f57b2b6267fa3444adf91191974"),
    (0xE3B98, 208, "3f0b05b388c4afa96464e14cb5022db712d6afc2cf98b4c0e0a5a7d9d2f2c145"),
    (0xA55A0, 65, "bd07d17cb82a9f14cadc87f9241aebcd51f8939b89342d9427d0966aa8fb0b11"),
    (0x60090, 652, "c2499c2d3646047733da8f7c983e9f9c345483cfc0e92bf0b69e3c347308be71"),
    (0x5f760, 2330, "099dea96ff3a33cc7b4960754707f986376531a8e4779fed9673b3f946404172"),
    (0x5e100, 26, "568c0199f70fafe44d180569001277d7b1f4ecf47006c041474b0ead2e64b412"),
    (0x4f0380, 120, "76b386d4da5fb35681822d2efcfdf506e59512d9883a43585be3100b7316906b"),
    (0x4f0d5c, 8, "604cce4ae8609b5bfd0acf6cc634ebb82ea1dcef5dbec9ada2b1449218f4144d"),
    # Full Standard and Far setup/live routines; own hook bytes are restored
    # to their recognized retail values solely for these prerequisite hashes.
    (0xA4950, 0x440, "78d271fb1e53de7bbc5d5d325f055e2fd76d9b05f659a53fac1c6b7d73135d4b"),
    (0xA87F10, 0xEB0, "9951b67f9a439ce9eed42f3092e9bd85c76fc581ea20176da0c12968ceab6f09"),
    # Menu callbacks, inclusive label width, shared row and native mount setup.
    (0x2C6690, 80, "c5fbd82b5a65df7dd87f5337adf23f5d69d7b099598ddeab82f0a33c1df2954f"),
    (0x2C6960, 544, "1c3438d34e119af57deca8b3fb76e4b5e9c7321eea95c9354e53ec08dd467178"),
    (0x52B700, 52, "e172db11c35979f0e26c44a4a7fc10cfb438ef017faaf21d8cacc6ae42c19a3b"),
    (0x4F25BC, 32, "4352c09f0e812a241cb513f955ace19f3c9cc818d87b67e585cf844163e13b5f"),
    (0xE69970, 20, "6f31bbda773d426b77003aade9d234fd079f463be74c8135115020336cd9bd18"),
    (0xA40C0, 11, "82bddf5fa41992cc53e15584bf6795c29f35c07a5fe6f6d8d07b3b4b445d0dc5"),
    (0x2C6800, 352, "8c37b7c611afb941dbd7a472e9d5b338c691d9f0f89939ad4a29e2fe9de58551"),
    (0xA5610, 16, "5654ce65877cab777e19bf6be4c79aca679ecd644f414bf81d8eef3ca6633c06"),
    (0x5036C0, 52, "b5bad68ffc3a50bbd3480c1e8794193a150bc09c67a096b98af1e0f3d7c86873"),
)


def code_for(va: int) -> bytes:
    a = _Asm(va)
    # Tail of the common game initializer. Use the native setter so leaving
    # First Person also restores its temporary audio/pivot settings.
    a.b("b900000000 8bd1 890df0ffe500")  # ecx = STANDARD_ROW
    a.call(0xA5B20)
    a.jmp_abs(0xA5490)
    body = a.assemble()
    _require(len(body) <= 32, "camera entry wrapper exceeds its slot")
    a = _Asm(va + 32)
    # Saved-settings callers, not the generic snapshot/restore helper. Its
    # ECX input, EAX destination result and balanced stack remain native.
    a.call(0xE2E20)
    a.b("c705f0ffe50000000000 c3")  # [OPTION_GLOBAL_VA] = STANDARD_ROW
    load = a.assemble()
    _require(len(load) <= 32, "camera import wrapper exceeds its slot")
    # Keep both v4 wrappers byte-for-byte, including MyCareer's detection
    # marker at A54C3. Only the enum callbacks need new code.
    a = _Asm(va + 64)
    a.b("8b0df0ffe500 83f905")
    a.j8("72", "advance")              # 0..4 -> 1..5
    a.b("b907000000")
    a.j8("74", "selected")             # 5 -> 7 (skip First Person)
    a.b("33c9")                        # 7/invalid -> Standard
    a.j8("eb", "selected")
    a.label("advance"); a.b("41")
    a.label("selected"); a.jmp_abs(0x2C6B0D)
    forward = a.assemble()
    a = _Asm(va + 112)
    a.b("8b0df0ffe500 85c9")
    a.j8("74", "wrap")
    a.b("83f905")
    a.j8("76", "retreat")              # 1..5 -> 0..4
    a.b("b906000000")                  # 7/invalid -> Custom
    a.label("retreat"); a.b("49")
    a.j8("eb", "selected")
    a.label("wrap"); a.b("b907000000")
    a.label("selected"); a.jmp_abs(0x2C6B50)
    backward = a.assemble()
    _require(max(len(forward), len(backward)) <= 48, "camera enum wrapper exceeds its slot")
    return (body.ljust(32, b"\xcc") + load.ljust(32, b"\xcc")
            + forward.ljust(48, b"\xcc") + backward.ljust(48, b"\xcc"))


def allocation(payload: bytes, kind: str = "code") -> dict | None:
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    if not rows:
        return None
    _require(sorted((a["kind"], a["size"], a["align"]) for a in rows)
             == [("code", CODE_SIZE, 16), ("read_only", READ_ONLY_SIZE, 16)],
             "foreign camera allocation")
    return next(a for a in rows if a["kind"] == kind)


def broadcast_descriptor() -> bytes:
    """Native sideline lag/setup, with following type 2, a 2.5 m lead and the v5.3 loge-front mount and lens.

    The untouched retail type-0 record has lens 120 and a fixed world eye.
    Reusing it verbatim would frame only a small part of a live play. No retail
    shared descriptor is mutated, and no inherited previous eye is required.
    """
    record = bytearray(descriptor_bytes(BROADCAST_RETAIL_DESCRIPTOR, BROADCAST_VALUES))
    struct.pack_into("<I", record, 0, 2)
    return bytes(record)


def _read(payload: bytes, va: int, size: int) -> bytes:
    off = _offset(payload, va)
    value = payload[off:off + size]
    _require(len(value) == size, "truncated camera span")
    return value


def _sites(payload: bytes, preset: str) -> list[tuple[str, int, bytes, bytes]]:
    _require(preset in PRESETS, f"unknown camera preset {preset!r}")
    a = allocation(payload)
    va = a["va"] if a else 0  # used only to recognize retail with no allocation
    replacements = {
        "game_entry_select": b"\xe9" + struct.pack("<i", va - 0xA55F0),
        "spectator_session_choice": b"\x90\x90",
        # Keep native 1.02 growth, direction, reset and lag decisions. The
        # old limit was twice the live offset height and could overshoot by
        # one update. These limits include that overshoot in the proof.
        "standard_live_cap": bytes.fromhex("d90558da4e00d9d0"),  # fld 500; fnop
        "far_live_cap": b"\xd9\x05" + struct.pack('<I', FAR_DESCRIPTORS[9] + 0x34) + b"\xd9\xd0",
        "camera_menu_max": bytes.fromhex("b807000000"),
        # Native width() consumes an inclusive last index. The intervening
        # First Person label may contribute width, but is never a menu choice.
        "camera_menu_width": bytes.fromhex("6a07"),
        "camera_menu_next": b"\xe9" + struct.pack("<i", va + 64 - 0x2C6B05) + b"\x90",
        "camera_menu_previous": b"\xe9" + struct.pack("<i", va + 112 - 0x2C6B45) + b"\x90",
    }
    for row, label in ((STANDARD_ROW, 'standard_pass_zoom'), (FAR_ROW, 'far_pass_zoom')):
        values = PASS_ZOOM_VALUES[row]
        if row == FAR_ROW and preset == 'broadcast_wide':
            values = (1000.0, -2500.0, 500.0)  # retained backend-only variant
        replacements[label] = b''.join(b'\xc7\x81' + struct.pack('<If', field, value)
            for field, value in zip((0x424, 0x428, 0x408), values))
    for name in ("settings_load_select", "franchise_load_select", "settings_reload_select"):
        replacements[name] = b"\xe8" + struct.pack("<i", va + 32 - HOOKS[name][0] - 5)
    sites = [(label, _offset(payload, addr), before, replacements[label])
             for label, (addr, before) in HOOKS.items()]
    for descriptors, originals, values in (
            (STANDARD_DESCRIPTORS, RETAIL_DESCRIPTORS, STANDARD_VALUES),
            (STANDARD_SPECIAL_DESCRIPTORS, STANDARD_SPECIAL_BYTES, STANDARD_SPECIAL_VALUES)):
        for state, addr in descriptors.items():
            before = originals[state]
            sites.append((f"standard_state_{state}", _offset(payload, addr), before,
                          descriptor_bytes(before, values[state])))
    for state, addr in FAR_DESCRIPTORS.items():
        before = FAR_RETAIL_DESCRIPTORS[state]
        sites.append((f"far_state_{state}", _offset(payload, addr), before,
                      descriptor_bytes(before, PRESETS[preset][state])))
    ro = allocation(payload, "read_only")
    for state, before in BROADCAST_RETAIL_ENTRIES.items():
        addr = PRESET_TABLE_VA + (BROADCAST_ROW * STATES_PER_ROW + state) * 8
        # Retain native transition flags. Only this row's descriptor pointer
        # changes; other rows still use the original shared television records.
        after = before[:4] + struct.pack("<I", ro["va"] if ro else 0)
        sites.append((f"broadcast_state_{state}", _offset(payload, addr), before, after))
    if a:
        sites.append(("owned_camera_wrappers", a["raw"], b"\xcc" * CODE_SIZE, code_for(va)))
        sites.append(("owned_broadcast_descriptor", ro["raw"], bytes(READ_ONLY_SIZE), broadcast_descriptor()))
    return sites


def status(payload: bytes, preset: str = DEFAULT_PRESET) -> str:
    """Retail, exactly applied, or foreign (including partial/old installs)."""
    try:
        sites = _sites(payload, preset)  # allocator validates section digests
        for va, pin in CONTEXT_PINS:
            _require(_read(payload, va, len(pin)) == pin, f"foreign context at {va:#x}")
        for va, size, digest in CONTEXT_HASHES:
            raw = bytearray(_read(payload, va, size))
            start = _offset(payload, va)
            for _label, off, old, new in sites:
                if start <= off and off + len(old) <= start + size:
                    actual = bytes(raw[off-start:off-start+len(old)])
                    _require(actual in (old, new), 'foreign bytes in camera prerequisite')
                    raw[off-start:off-start+len(old)] = old
            _require(hashlib.sha256(raw).hexdigest() == digest,
                     f"foreign camera prerequisite at {va:#x}")
        states = {"retail" if payload[off:off+len(old)] == old else
                  "applied" if payload[off:off+len(new)] == new else "foreign"
                  for _label, off, old, new in sites if old != new}
        if states == {"retail"}:
            return "retail"
        if states == {"applied"} and allocation(payload) is not None:
            return "applied"
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError, OverflowError, zlib.error):
        pass
    return "foreign"


def detect_preset(payload: bytes) -> str | None:
    """'retail', the name of the installed Far variant, or None (foreign)."""

    if status(payload, DEFAULT_PRESET) == "retail":
        return "retail"
    for name in PRESETS:
        if status(payload, name) == "applied":
            return name
    return None


def read_standard(payload: bytes) -> dict[int, dict[str, object]]:
    """Decode the seven Standard scrimmage descriptors in ``payload``."""

    out = {}
    for state, va in STANDARD_DESCRIPTORS.items():
        off = _offset(payload, va)
        out[state] = {"va": va, "label": STATE_LABELS[state], **decode_descriptor(payload[off: off + DESCRIPTOR_SIZE])}
    return out


def read_far(payload: bytes) -> dict[int, dict[str, object]]:
    """Decode the Far-row descriptors for the same states."""

    out = {}
    for state, va in FAR_DESCRIPTORS.items():
        off = _offset(payload, va)
        out[state] = {"va": va, "label": STATE_LABELS[state], **decode_descriptor(payload[off: off + DESCRIPTOR_SIZE])}
    return out


def read_broadcast(payload: bytes) -> dict[int, dict[str, object]]:
    """Decode the selectable Broadcast row, whether retail or installed."""
    return {state: {"va": va, **decode_descriptor(_read(payload, va, DESCRIPTOR_SIZE))}
            for state, (_flags, va) in enumerate(read_preset_table(payload)[BROADCAST_ROW])
            if state in BROADCAST_STATES}


def read_preset_table(payload: bytes) -> list[list[tuple[int, int]]]:
    """The 8 x 29 (flags, descriptor VA) table at 0x4F03F8."""

    off = _offset(payload, PRESET_TABLE_VA)
    rows = []
    for row in range(len(PRESET_NAMES)):
        entries = []
        for state in range(STATES_PER_ROW):
            at = off + (row * STATES_PER_ROW + state) * 8
            entries.append(struct.unpack_from("<II", payload, at))
        rows.append(entries)
    return rows


def option_default_status(payload: bytes) -> str:
    try:
        got = _read(payload, OPTION_DEFAULT_SITE_VA, len(RETAIL_OPTION_DEFAULT))
        return {RETAIL_OPTION_DEFAULT: "standard",
                bytes.fromhex("33ff8935f0ffe500"): "far"}.get(got, "foreign")
    except (ValueError, struct.error):
        return "foreign"


def reservations(payload: bytes) -> list[dict]:
    rows = []
    for label, off, before, _after in _sites(payload, DEFAULT_PRESET):
        allocations = [allocation(payload, kind) for kind in ("code", "read_only")]
        a = next((a for a in allocations if a and off == a["raw"]), None)
        if a:
            rows.append(dict(owner=OWNER, start=hex(a["va"]), end=hex(a["va"]+a["size"]),
                             size=a["size"], basis="named " + a["kind"] + " allocation", parent_owner=space.OWNER))
        else:
            section = _section_for_offset(_sections(payload), off)
            va = section.virtual_address + off - section.raw_offset
            rows.append(dict(owner=OWNER, start=hex(va), end=hex(va+len(before)),
                             size=len(before), basis="declared edit: " + label))
    return rows


def apply(payload: bytes, preset: str = DEFAULT_PRESET) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload, preset)
    _require(state in ("retail", "applied"), "foreign/mixed camera bytes; rebuild from retail")
    common = dict(owner=OWNER, version=VERSION, preset=preset, experimental=True,
                  runtime_witnessed=False, selected_row=STANDARD_ROW, option_default="standard",
                  owned_code_bytes=CODE_SIZE, owned_read_only_bytes=READ_ONLY_SIZE,
                  persistent_data_bytes=0, menu_rows=MENU_ROWS,
                  broadcast="retail sideline descriptor adapted for following gameplay",
                  coach_mode_changed=False, exact_coach_director_proved=False)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    if space.status(payload) == "retail":
        allocated, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
    else:
        _require(allocation(payload) is not None, "camera missing from sealed owner union; rebuild from base")
        allocated, allocation_receipt = payload, {}
    sites = _sites(allocated, preset)
    a = allocation(allocated)
    installed, _ = space.install_code(allocated, OWNER, code_for(a["va"]))
    installed, _ = space.install_read_only(installed, OWNER, broadcast_descriptor())
    buf = bytearray(installed)
    sections = _sections(installed)
    touched = set()
    edits = []
    for label, off, before, after in sites:
        buf[off:off + len(after)] = after
        section = _section_for_offset(sections, off)
        touched.add(section.index)
        va = section.virtual_address + off - section.raw_offset
        edits.append(dict(label=label, va=hex(va), file_offset=hex(off), size=len(after),
                          before=before.hex(), after=after.hex(),
                          after_sha256=hashlib.sha256(after).hexdigest()))
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d:d + 20] = section_digest(buf, section)
    patched = bytes(buf)
    _require(status(patched, preset) == "applied", "camera post-apply verification failed")
    changed = sum(a != b for a, b in zip(payload, patched)) + len(patched) - len(payload)
    return patched, dict(common, status="applied", edits=edits, changed_bytes=changed,
                         file_growth=len(patched)-len(payload), allocation=allocation_receipt,
                         before_sha256=hashlib.sha256(payload).hexdigest(),
                         after_sha256=hashlib.sha256(patched).hexdigest(),
                         sections_repinned=sorted(touched), reservations=reservations(patched))

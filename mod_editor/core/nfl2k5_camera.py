"""Rewrite NFL 2K5's default ("Standard") gameplay camera in ``default.xbe`` (data patch, xemu-only).

How the retail camera is built (all addresses are retail ``default.xbe`` VAs, image base 0x10000):

* The Options "Camera" choice (``DAT_00e5fff0``: 0 Standard, 1 Far, 2 Side, 3 Iso, 4 Blimp, 5 Custom;
  the menu shows ``names[value]`` with ``names`` = 0x4F25BC (``cb_002c66c0``); 6 = 1st Person and
  7 = "Broadcast" exist in the table but are not menu choices) selects a ROW of the .rdata table at
  0x4F03F8: 8 rows x 29 game states x 8 bytes ``(flags, descriptor*)``.  The row is the option value
  itself: ``FUN_000a5490`` copies ``DAT_00e5fff0`` into the live row ``DAT_00b665f0`` every frame while
  a controller is plugged in (row 7 "Broadcast" only when none is), and the option setter
  ``FUN_002c6960`` -> ``FUN_000a5b20(option)`` stores the same value.  The fresh-profile default is
  0 = Standard (``FUN_000e3b90``); a profile save carries the five camera words (``cb_002c69d0`` ->
  0xC8E1A0, restored by ``cb_002c6a90``), so an existing profile keeps whatever it last chose.
* The game state ``DAT_00b616c0`` is set by ``FUN_00089260``; 9 = pre-snap scrimmage, 16 = the live
  play (also state 1 = play call and the pause-menu preview: ``FUN_000a5610``), 17/18/19 = live
  variants, 15 = pass in the air, 13 = post-catch, 8/10/11 = kick alignments.
* A descriptor is an 0x50-byte record in .data: +0x00 type (2 = follow the focus, z flipped with
  the offense direction), +0x08 lag block (0x4F0380/0x4F03A8), +0x10 look-at offset xyz (cm),
  +0x20 lens word (passed as value/18 to the projection; lower = wider, Far uses 28, 1st person
  18), +0x30 camera offset xyz (cm, y up, z toward the offense's own end zone), +0x40/+0x44 setup
  and per-frame callbacks.  ``FUN_00060090`` copies it into the camera object at +0x3F0;
  ``FUN_0005f760`` adds +0x420 (offset) to the focus for the eye and +0x400 for the look-at.
  World units are centimetres (1 yd = 91.44 cm).
* Each row owns its descriptors: the seven Standard records (0xA88870..0xA88A50) are referenced only
  by row 0 of the table and by Standard's own per-frame callback ``FUN_000a4a50`` (re-copy of
  0xA88A00, pull-back cap 2 x [0xA88A34]); the Far records (0xA88B90..0xA88D70) only by row 1 and
  ``FUN_000a4c30`` (0xA88D20 / [0xA88D54]).  Nothing is shared, so a Standard rewrite cannot leak
  into Far or any other preset.

Retail Far is the Standard geometry with a wider lens (28 instead of 35; 24 instead of 30 with the
ball in the air) and a slightly different state-19 look-at.  Noah's 9/3 playtest preferred that
look and asked for it to be the default, so the default preset here (``far_look``) copies Far's
seven live records into Standard's seven (look-at, lens and offset words only; Standard keeps its
own type, lag pointer and callbacks, which are the same code paths with Standard's own pull-back
and pass-zoom-out logic).  The earlier ``broadcast_wide`` proposal (23 yd back, 9-10 yd up, lens
32) stays available as a named preset.  The option default (0 = Standard) is retail already and is
left alone; the kick alignments (8, 10, 11, 12) and the other rows are never touched.  Retail
bytes are verified before writing and the .data section digest is repinned.  Not verified in game.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

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
OPTION_GLOBAL_VA = 0x00E5FFF0            # DAT_00e5fff0: the Options "Camera" value (= table row)
OPTION_DEFAULT_SITE_VA = 0x000E3C68      # FUN_000e3b90: `xor edi,edi ; mov dword ptr [0xE5FFF0], edi` (fresh-profile default 0)
RETAIL_OPTION_DEFAULT = bytes.fromhex("33ff893df0ffe500")   # xor edi,edi ; mov dword [0xE5FFF0], edi

# Standard-row descriptors this patch rewrites, keyed by game state.
STANDARD_DESCRIPTORS: dict[int, int] = {
    9: 0x00A88870,    # pre-snap scrimmage
    13: 0x00A888C0,   # after the catch
    15: 0x00A88A50,   # pass in the air ("Pass Play Zoom Out" adds its own pull-back)
    16: 0x00A88A00,   # the live play; also state 1 (play call) and the pause-menu camera preview
    17: 0x00A88910,   # live variant (ball carrier)
    18: 0x00A88960,   # live variant
    19: 0x00A889B0,   # live variant (look-at behind the ball)
}
# The Far row's records for the same states (read for reference; never written).
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
    # Standard becomes the retail Far look (Noah 9/3: "make [Far] the new default").
    "far_look": dict(FAR_RETAIL_VALUES),
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
PRESET_TITLES = {"far_look": "Standard = the Far look (retail Far geometry and lens)",
                 "broadcast_wide": "Broadcast Wide (23 yd back, 9-10 yd up, lens 32)"}


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


def _sites(payload: bytes, preset: str) -> list[tuple[int, int, bytes, bytes]]:
    _require(preset in PRESETS, f"unknown camera preset {preset!r}")
    values = PRESETS[preset]
    sites = []
    for state, va in STANDARD_DESCRIPTORS.items():
        retail = RETAIL_DESCRIPTORS[state]
        _require(descriptor_bytes(retail, RETAIL_VALUES[state]) == retail, f"retail transcript of state {state} is inconsistent")
        _require(descriptor_bytes(FAR_RETAIL_DESCRIPTORS[state], FAR_RETAIL_VALUES[state]) == FAR_RETAIL_DESCRIPTORS[state],
                 f"retail Far transcript of state {state} is inconsistent")
        sites.append((state, _offset(payload, va), retail, descriptor_bytes(retail, values[state])))
    return sites


def status(payload: bytes, preset: str = DEFAULT_PRESET) -> str:
    """'retail', 'applied' (this preset), or 'foreign'."""

    try:
        sites = _sites(payload, preset)
    except (CameraPatchError, ValueError, struct.error):
        return "foreign"
    states = set()
    for _state, off, before, after in sites:
        got = payload[off: off + DESCRIPTOR_SIZE]
        states.add("retail" if got == before else "applied" if got == after else "foreign")
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def detect_preset(payload: bytes) -> str | None:
    """'retail', the name of the preset the Standard records currently hold, or None (foreign)."""

    if status(payload, DEFAULT_PRESET) == "retail":
        return "retail"
    for name in PRESETS:
        if status(payload, name) == "applied":
            return name
    return None


def read_standard(payload: bytes) -> dict[int, dict[str, object]]:
    """Decode the Standard-row descriptors this patch touches, as they are in ``payload``."""

    out = {}
    for state, va in STANDARD_DESCRIPTORS.items():
        off = _offset(payload, va)
        out[state] = {"va": va, "label": STATE_LABELS[state], **decode_descriptor(payload[off: off + DESCRIPTOR_SIZE])}
    return out


def read_far(payload: bytes) -> dict[int, dict[str, object]]:
    """Decode the Far-row descriptors for the same states (never written by this module)."""

    out = {}
    for state, va in FAR_DESCRIPTORS.items():
        off = _offset(payload, va)
        out[state] = {"va": va, "label": STATE_LABELS[state], **decode_descriptor(payload[off: off + DESCRIPTOR_SIZE])}
    return out


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
    """'standard' when the fresh-profile Camera default is still retail (0 = Standard), else 'foreign'."""

    try:
        off = _offset(payload, OPTION_DEFAULT_SITE_VA)
    except CameraPatchError:
        return "foreign"
    return "standard" if payload[off: off + len(RETAIL_OPTION_DEFAULT)] == RETAIL_OPTION_DEFAULT else "foreign"


def apply(payload: bytes, preset: str = DEFAULT_PRESET) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload, preset)
    _require(state == "retail", f"Standard camera descriptors are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    for game_state, off, _before, after in _sites(payload, preset):
        buf[off: off + DESCRIPTOR_SIZE] = after
        touched.add(_section_for_offset(sections, off).index)
        target, fov, offset = PRESETS[preset][game_state]
        edits.append({"state": game_state, "label": STATE_LABELS[game_state],
                      "va": f"0x{STANDARD_DESCRIPTORS[game_state]:x}", "file_offset": f"0x{off:x}",
                      "target_cm": list(target), "fov": fov, "offset_cm": list(offset)})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched, preset) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"preset": preset, "edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
                     "option_default": option_default_status(patched)}


__all__ = ["CameraPatchError", "DEFAULT_PRESET", "FAR_DESCRIPTORS", "FAR_RETAIL_DESCRIPTORS", "FAR_RETAIL_VALUES",
           "OPTION_DEFAULT_SITE_VA", "OPTION_GLOBAL_VA", "PRESETS", "PRESET_NAMES", "PRESET_TITLES", "RETAIL_DESCRIPTORS",
           "RETAIL_VALUES", "STANDARD_DESCRIPTORS", "STATE_LABELS", "apply", "decode_descriptor", "descriptor_bytes",
           "detect_preset", "option_default_status", "read_far", "read_preset_table", "read_standard", "status"]

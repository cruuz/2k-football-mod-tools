"""EXPERIMENTAL / UNWITNESSED Far selection and scorebar-safe framing, USA XBE.

Far is row 1 of 4F03F8, not a rename of Standard. Seven Far descriptors
retain their native type, lag and callbacks. The settings default, settings
saved-load calls and common game-camera initialization select Far; Options remains a
session choice. The automatic spectator branch uses that same choice.

64 owned RX bytes, no RW allocation, no retail cave. Reserve REQUESTS with
all other selected owners before apply. Rebuild historical descriptor-only
installations from retail; mixed/foreign inputs refuse before mutation.
See ASTRA_CAMERA_FAR_REPORT.md for native evidence and visual-proof limits.
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
VERSION = 2
CODE_SIZE = 64
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
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

# Standard-row reference guards, keyed by game state. These remain unchanged.
STANDARD_DESCRIPTORS: dict[int, int] = {
    9: 0x00A88870,    # pre-snap scrimmage
    13: 0x00A888C0,   # after the catch
    15: 0x00A88A50,   # pass in the air ("Pass Play Zoom Out" adds its own pull-back)
    16: 0x00A88A00,   # the live play; also state 1 (play call) and the pause-menu camera preview
    17: 0x00A88910,   # live variant (ball carrier)
    18: 0x00A88960,   # live variant
    19: 0x00A889B0,   # live variant (look-at behind the ball)
}
# The seven Far recipients; Standard and all unrelated states remain retail.
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
    # Keep the existing public preset key while making Far the actual selection.
    "far_look": {
        9: ((0.0, 0.0, -250.0), 28.0, (0.0, 700.0, -1800.0)),
        13: ((0.0, 0.0, -250.0), 28.0, (0.0, 650.0, -1600.0)),
        15: ((0.0, 50.0, -150.0), 24.0, (0.0, 800.0, -2000.0)),
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


# Complete instructions, not just their changed operands. ESI=1 is pinned
# at E3B92; EDI remains zero for the adjacent pivot/zoom defaults.
HOOKS = {
    "fresh_settings_far": (OPTION_DEFAULT_SITE_VA, RETAIL_OPTION_DEFAULT),
    "settings_load_far": (0x16D1D4, bytes.fromhex("e8475cf7ff")),
    "franchise_load_far": (0x16E7B1, bytes.fromhex("e86a46f7ff")),
    "settings_reload_far": (0x16E864, bytes.fromhex("e8b745f7ff")),
    "game_entry_far": (0xA55EB, bytes.fromhex("e9a0feffff")),
    "spectator_session_choice": (0xA54C3, bytes.fromhex("7e06")),
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
)
# Hash-only guards are generated from the pinned USA executable, below.
CONTEXT_HASHES = (
    (0x4F03F8, 1856, "2b63b0b1c1d993ebf4b6eb6a502f8aa21417f14aa167262777ecbbab27badb93"),
    (0xA5B20, 480, "ba3262ce0f88dbf9fbf46cf6e4b783076b9ec7e05fa32dbade9bcf9fccf736d8"),
    (0x31000, 33, "6108e11605dbbba3cec8f5dbccc0c99915850f57b2b6267fa3444adf91191974"),
    (0xE3B98, 208, "3f0b05b388c4afa96464e14cb5022db712d6afc2cf98b4c0e0a5a7d9d2f2c145"),
    (0xA55A0, 65, "bd07d17cb82a9f14cadc87f9241aebcd51f8939b89342d9427d0966aa8fb0b11"),
    (0xA4B90, 500, "21a951b17f3257486ad6d426241dfae25dc55effa53b369fa9c6eaf2cc6572ac"),
)


def code_for(va: int) -> bytes:
    a = _Asm(va)
    # Tail of the common game initializer. Use the native setter so leaving
    # First Person also restores its temporary audio/pivot settings.
    a.b("b901000000 8bd1 890df0ffe500")
    a.call(0xA5B20)
    a.jmp_abs(0xA5490)
    body = a.assemble()
    _require(len(body) <= 32, "camera entry wrapper exceeds its slot")
    a = _Asm(va + 32)
    # Saved-settings callers, not the generic snapshot/restore helper. Its
    # ECX input, EAX destination result and balanced stack remain native.
    a.call(0xE2E20)
    a.b("c705f0ffe50001000000 c3")
    load = a.assemble()
    _require(len(load) <= 32, "camera import wrapper exceeds its slot")
    return body.ljust(32, b"\xcc") + load.ljust(32, b"\xcc")


def allocation(payload: bytes) -> dict | None:
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"])
             == ("code", CODE_SIZE, 16), "foreign camera allocation")
    return rows[0]


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
        "fresh_settings_far": bytes.fromhex("33ff8935f0ffe500"),
        "game_entry_far": b"\xe9" + struct.pack("<i", va - 0xA55F0),
        "spectator_session_choice": b"\x90\x90",
    }
    for name in ("settings_load_far", "franchise_load_far", "settings_reload_far"):
        replacements[name] = b"\xe8" + struct.pack("<i", va + 32 - HOOKS[name][0] - 5)
    sites = [(label, _offset(payload, addr), before, replacements[label])
             for label, (addr, before) in HOOKS.items()]
    for state, addr in FAR_DESCRIPTORS.items():
        before = FAR_RETAIL_DESCRIPTORS[state]
        sites.append((f"far_state_{state}", _offset(payload, addr), before,
                      descriptor_bytes(before, PRESETS[preset][state])))
    if a:
        sites.append(("owned_camera_wrappers", a["raw"], b"\xcc" * CODE_SIZE, code_for(va)))
    return sites


def status(payload: bytes, preset: str = DEFAULT_PRESET) -> str:
    """Retail, exactly applied, or foreign (including partial/old installs)."""
    try:
        sites = _sites(payload, preset)  # allocator validates section digests
        for va, pin in CONTEXT_PINS:
            _require(_read(payload, va, len(pin)) == pin, f"foreign context at {va:#x}")
        for va, size, digest in CONTEXT_HASHES:
            _require(hashlib.sha256(_read(payload, va, size)).hexdigest() == digest,
                     f"foreign camera prerequisite at {va:#x}")
        for state, va in STANDARD_DESCRIPTORS.items():
            _require(_read(payload, va, DESCRIPTOR_SIZE) == RETAIL_DESCRIPTORS[state],
                     "historical/foreign Standard rewrite; rebuild from retail")
        states = {"retail" if payload[off:off+len(old)] == old else
                  "applied" if payload[off:off+len(new)] == new else "foreign"
                  for _label, off, old, new in sites}
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
    """Decode the unchanged Standard-row reference descriptors in ``payload``."""

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
        a = allocation(payload)
        if a and off == a["raw"]:
            rows.append(dict(owner=OWNER, start=hex(a["va"]), end=hex(a["va"]+CODE_SIZE),
                             size=CODE_SIZE, basis="named code allocation", parent_owner=space.OWNER))
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
                  runtime_witnessed=False, selected_row=FAR_ROW, option_default="far",
                  owned_code_bytes=CODE_SIZE, persistent_data_bytes=0)
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

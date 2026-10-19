"""Per-kit jersey number size (chest and back numbers), a late executable owner. EXPERIMENTAL / UNWITNESSED.

How the game sizes the numbers (PROVED OFFLINE, ns1): every player body carries three number decals, NUMBER_L,
NUMBER_M and NUMBER_R (and a NECKROLL4_ copy), shared by every team. The player builder 0x8EFA0 binds the digit
textures through the selector 0x8E910 (eax number, ecx row, edx family 0xC = jersey font; arguments model, LOD, -,
texture slot); a single digit goes on M, two digits on L (tens) and R (ones). The binder 0x8E8D0 writes the material's
texture (+0x30) and its UV transform (+0x20 U scale 4.0, +0x24 V scale 2.0; +0x28 / +0x2C are the U / V offsets, 0.0
in the model files, rewritten only by the number kerning owner). The draw path 0x307FC applies uv' = uv * scale +
offset, so the number size is the one fixed 4.0 / 2.0 pair for every team. The texture slot is the uniform package
the game mounted as the container HOME (slot 0) or AWAY (slot 1): 0x8E580 looks digits up in [0x4EEACC + 4 * slot]
(L"HOME", L"AWAY"), and 0x63261 / 0x6327F mount the files whose names 0x6169C / 0x616E2 format into 0xB30710 (HOME)
and 0xB30730 (AWAY) as L"%s%c%d.iff" ("13h0.iff": team code, h/a, variant; the home-white swap is already applied).

This owner adds a hook after the jersey-font selector call (0x8F580, 7 bytes: ``mov eax, esi; call 0x8E840``) to a
cave in its own allocation (a late ``nfl2k5_xbe_space`` owner, after every other). The cave reads the player's texture
slot (esi), compares the mounted package name for that slot with its table (10 bytes, "13h0."), and for a listed kit
rewrites the cells the selector just bound (M for 0-9, L and R otherwise; rows 0 NUMBER_ and 11 NECKROLL4_NUMBER_
only): U scale 4/S, V scale 2/S, U offset A_cell * (1 - 1/S) (+ the kerning offset the kerning binder wrote), V offset
AV * (1 - 1/S), an enlargement by S about the pair centre (L 0.816, M 0.4988, R 0.1808 in the retail U frame) and the
upper part of the number (AV, retail V frame). Any other kit, slot, row, family, helmet or shoulder number keeps the
retail binding; the cave only puts back the file's zero offsets if a scaled bind on a shared material left them (with
the retail binder; the kerning binder rewrites its own U offset on every bind). With an empty table nothing is
installed and the executable keeps its retail bytes.

Limit (PROVED OFFLINE on the hi_body decals): the back number decal is only ~1.10 texture heights tall at the retail
V scale (the front 1.28), and the retail glyphs already fill it, so a clean enlargement tops out near S = 1.08-1.10 on
the back (wide tens digits touch the decal's outer bottom corner first); the 2026 photos' ~1.33x needs larger shared
decals in the body model, which this owner does not touch.
"""
from __future__ import annotations

import hashlib
import math
import re
import struct
from typing import Mapping

OWNER = "nfl2k5_team_number_scale"
LABEL = "EXPERIMENTAL / UNWITNESSED"
BUILD_KEY = "team_number_scale"
BUILD_CAPTION = "Jersey numbers: per-kit size (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. A table of uniform kits (for example 13H0 and 13A0, the Chiefs' home and road) whose "
    "chest and back numbers draw at another size. Every other kit, and every helmet and shoulder number, stays as "
    "the game draws it. Empty = off (the executable keeps its retail bytes).")
CODE_SIZE = 0x270
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
TABLE_OFFSET = 0x140
ENTRY_SIZE = 0x24
MAX_ENTRIES = 8
MIN_SCALE, MAX_SCALE = 0.75, 1.30

HOOK_VA, RESUME_VA = 0x8F580, 0x8F587
HOOK_RETAIL = bytes.fromhex("8bc6" "e8b9f2ffff")      # mov eax, esi; call 0x8E840
ROUTE_VA = 0x8E840
ROW_TABLE_VA = 0x4EF7F8                              # jersey-font rows by the player's jersey style (8 dwords)
MATS_VA = 0xA86D6C                                   # [row * 16 + lod * 3 + cell] material indices (L, M, R)
KIT_NAMES_VA = 0xB30710                              # L"13h0.iff" for slot 0 (HOME), +0x20 slot 1 (AWAY)
BINDER_VA, KERNING_BINDER_BYTE = 0x8E8D0, 0x33       # the kerning owner's binder starts xor edx, edx
SCALED_ROWS = (0, 11)                                # NUMBER_ and NECKROLL4_NUMBER_
#: pair centre / single centre in the retail U frame (4 * u at x = 0, front and back averaged; hi_body o3c114)
ANCHOR_U = (4 * (0.2021 + 0.2059) / 2, 4 * 0.1247, 4 * (0.0469 + 0.0435) / 2)
ANCHOR_V = 0.30                                      # the number grows about its upper part ...
GLYPH_TOP, DECAL_TOP = 1 / 64, -0.0142               # ... and its top never rises above the back decal's top edge
#: (va, size, sha256) of the retail code and data the cave relies on
GUARDS = (
    (0x8F52E, 0x8B, "c4257113e01133d0323c295a7a1c2cbacb27935308a9ac29b6552d6a2818c5ce"),  # builder 0x8F52E..0x8F5B9
    (0x8E910, 0x0D, "efaea8df7fef53437ece3fa5efb9f203b24430b08336624125bbb96fdc530a38"),  # selector entry (both binders)
    (ROW_TABLE_VA, 0x20, "f861ee31e3bb9dcaa754bedf1c80396e15d720a115273aa63466c1935ad4113f"),
    (0x6169C, 0x68, "7ea0a13173080173af3e606f4619ea9878ba033216e94ec3c91ce4ce1be7f525"),  # HOME / AWAY names
    (0x63261, 0x42, "8b17c2083f84cd98d9890d474e8834fc777b28ca2d691139a2653a061ea2e1bc"),  # HOME / AWAY mounts
    (0xE61060, 0x16, "e7de0288dcb1be17f92bec4b9c39c2a607c5ee23d25c3bd618d03ba9a7e5a164"),  # L"%s%c%d.iff"
)


class TeamNumberScaleError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise TeamNumberScaleError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _f32(value):
    return struct.pack("<f", value)


# ------------------------------------------------------------------------------------------------ the table

def normalize(value) -> dict[str, float]:
    """The recipe value: {} or {"13H0": 1.08, ...} (kit = two-digit team code, H or A, one-digit variant)."""
    _require(isinstance(value, Mapping), "team_number_scale must be an object of kit: scale")
    out = {}
    for kit, scale in value.items():
        _require(type(kit) is str and re.fullmatch(r"\d\d[HAha]\d", kit) is not None,
                 f"team_number_scale kit {kit!r} must look like 13H0 (team code, H or A, variant 0-9)")
        _require(type(scale) in (int, float) and math.isfinite(scale) and MIN_SCALE <= scale <= MAX_SCALE,
                 f"team_number_scale {kit}: the scale must be {MIN_SCALE}..{MAX_SCALE}")
        key = kit.upper()
        _require(key not in out, f"team_number_scale lists {key} twice")
        out[key] = round(float(scale), 3)
    _require(len(out) <= MAX_ENTRIES, f"team_number_scale holds at most {MAX_ENTRIES} kits")
    return dict(sorted(out.items()))


def anchor_v(scale: float) -> float:
    """The V anchor: ANCHOR_V, lowered for large scales so the number's top stays inside the back decal."""
    if scale <= 1.0:
        return ANCHOR_V
    return min(ANCHOR_V, GLYPH_TOP + (GLYPH_TOP - DECAL_TOP) / (scale - 1.0))


def transform(scale: float, cell: int, kern: float = 0.0) -> tuple[float, float, float, float]:
    """(U scale, V scale, U offset, V offset) the cave writes for ``cell`` (0 L, 1 M, 2 R), as float32 values."""
    def r(x):
        return struct.unpack("<f", _f32(x))[0]
    c = r(ANCHOR_U[cell] * (1 - 1 / scale))
    return r(4 / scale), r(2 / scale), r(c + kern) if kern else c, r(anchor_v(scale) * (1 - 1 / scale))


def _entry(kit: str, scale: float) -> bytes:
    name = (kit[:2] + kit[2].lower() + kit[3] + ".").encode("utf-16le")
    su, sv, _c, ov = transform(scale, 1)
    cells = [transform(scale, cell)[2] for cell in range(3)]
    return name + b"\0\0" + _f32(su) + _f32(sv) + _f32(ov) + b"".join(_f32(c) for c in cells)


def table_bytes(scales: Mapping[str, float]) -> bytes:
    rows = normalize(scales)
    return struct.pack("<I", len(rows)) + b"".join(_entry(k, s) for k, s in rows.items())


def read_table(blob: bytes) -> dict[str, float]:
    """The kits of an installed cave, scales recovered from the stored V scale (2/S) and re-normalized."""
    count = struct.unpack_from("<I", blob, TABLE_OFFSET)[0]
    _require(0 < count <= MAX_ENTRIES, "foreign number-scale table")
    out = {}
    for i in range(count):
        at = TABLE_OFFSET + 4 + i * ENTRY_SIZE
        name = blob[at:at + 10].decode("utf-16le")
        _require(re.fullmatch(r"\d\d[ha]\d\.", name) is not None, "foreign number-scale kit name")
        sv = struct.unpack_from("<f", blob, at + 0x10)[0]
        _require(math.isfinite(sv) and sv > 0, "foreign number-scale entry")
        out[name[:2] + name[2].upper() + name[3]] = round(2 / sv, 3)
    return normalize(out)


# ------------------------------------------------------------------------------------------------ the cave

def code_for(code_va: int, scales: Mapping[str, float]) -> bytes:
    from .nfl2k5_draft_ai import _Asm
    rows = normalize(scales)
    _require(rows, "an empty table installs nothing")
    table = code_va + TABLE_OFFSET
    a = _Asm(code_va)
    a.b("60")                                            # pushad
    a.b("83fe01")                                        # cmp esi, 1          texture slot (0 HOME, 1 AWAY)
    a.j32("0f87", "done")
    a.b("8b45f0")                                        # mov eax, [ebp-0x10] jersey style
    a.b("83e007")                                        # and eax, 7
    a.b("8b0c85" + struct.pack("<I", ROW_TABLE_VA).hex())  # mov ecx, [eax*4 + rows]
    a.b("85c9")                                          # test ecx, ecx
    a.j8("74", "row_ok")
    a.b("83f90b")                                        # cmp ecx, 11
    a.j32("0f85", "done")
    a.label("row_ok")
    a.b("8b5508")                                        # mov edx, [ebp+8]    LOD
    a.b("83fa03")                                        # cmp edx, 3
    a.j32("0f87", "done")
    a.b("c1e104")                                        # shl ecx, 4
    a.b("8d1452")                                        # lea edx, [edx+edx*2]
    a.b("8d8c11" + struct.pack("<I", MATS_VA).hex())     # lea ecx, [ecx+edx+mats]  cell bytes L, M, R
    a.b("8bd6")                                          # mov edx, esi
    a.b("c1e205")                                        # shl edx, 5
    a.b("81c2" + struct.pack("<I", KIT_NAMES_VA).hex())  # add edx, names       the slot's mounted kit name
    a.b("bb" + struct.pack("<I", table + 4).hex())       # mov ebx, first entry
    a.b("8b05" + struct.pack("<I", table).hex())         # mov eax, [count]
    a.label("next")
    a.b("48")                                            # dec eax
    a.j8("78", "other")                                  # js other
    a.b("8b32")                                          # mov esi, [edx]
    a.b("3b33")                                          # cmp esi, [ebx]
    a.j8("75", "skip")
    a.b("8b7204")                                        # mov esi, [edx+4]
    a.b("3b7304")                                        # cmp esi, [ebx+4]
    a.j8("75", "skip")
    a.b("668b7208")                                      # mov si, [edx+8]
    a.b("663b7308")                                      # cmp si, [ebx+8]
    a.j8("74", "found")
    a.label("skip")
    a.b("83c3" + f"{ENTRY_SIZE:02x}")                    # add ebx, ENTRY_SIZE
    a.j8("eb", "next")
    a.label("other")
    a.b("33db")                                          # xor ebx, ebx        not listed
    a.label("found")
    a.b("8b442410")                                      # mov eax, [esp+0x10] the player record (saved ebx)
    a.b("8b4020")                                        # mov eax, [eax+0x20]
    a.b("c1e803")                                        # shr eax, 3
    a.b("83e07f")                                        # and eax, 0x7F       jersey number, as the builder reads it
    a.b("83f80a")                                        # cmp eax, 10
    a.j8("7c", "single")
    a.b("33d2")                                          # xor edx, edx        L
    a.j32("e8", "cell")
    a.b("ba02000000")                                    # mov edx, 2          R
    a.j32("e8", "cell")
    a.j8("eb", "done")
    a.label("single")
    a.b("ba01000000")                                    # mov edx, 1          M
    a.j32("e8", "cell")
    a.label("done")
    a.b("61")                                            # popad
    a.b("8bc6")                                          # mov eax, esi        (the displaced retail pair)
    a.call(ROUTE_VA)                                     # call 0x8E840
    a.jmp_abs(RESUME_VA)
    a.label("cell")                                      # edx cell, ecx cell bytes, ebx entry or 0, edi model
    a.b("0fb60411")                                      # movzx eax, byte [ecx+edx]
    a.b("3b471c")                                        # cmp eax, [edi+0x1C] material count
    a.j8("73", "ret")                                    # jae ret             (0xFF and out of range: unbound)
    a.b("c1e007")                                        # shl eax, 7
    a.b("034720")                                        # add eax, [edi+0x20] the material
    a.b("85db")                                          # test ebx, ebx
    a.j8("74", "reset")
    a.b("8b730c"); a.b("897020")                         # U scale
    a.b("8b7310"); a.b("897024")                         # V scale
    a.b("8b7314"); a.b("89702c")                         # V offset
    a.b("803d" + struct.pack("<I", BINDER_VA).hex() + f"{KERNING_BINDER_BYTE:02x}")  # cmp byte [binder], 0x33
    a.j8("75", "plain")
    a.b("d94028")                                        # fld dword [eax+0x28]   the kerning offset just bound
    a.b("d8449318")                                      # fadd dword [ebx+edx*4+0x18]
    a.b("d95828")                                        # fstp dword [eax+0x28]
    a.b("c3")
    a.label("plain")
    a.b("8b749318")                                      # mov esi, [ebx+edx*4+0x18]
    a.b("897028")                                        # mov [eax+0x28], esi
    a.b("c3")
    a.label("reset")                                     # another kit: the file's zero offsets, only if moved
    a.b("f7402cffffff7f")                                # test dword [eax+0x2C], 0x7FFFFFFF
    a.j8("74", "u")
    a.b("c7402c00000000")                                # mov dword [eax+0x2C], 0
    a.label("u")
    a.b("803d" + struct.pack("<I", BINDER_VA).hex() + f"{KERNING_BINDER_BYTE:02x}")
    a.j8("74", "ret")                                    # the kerning binder owns the U offset
    a.b("f74028ffffff7f")                                # test dword [eax+0x28], 0x7FFFFFFF
    a.j8("74", "ret")
    a.b("c7402800000000")                                # mov dword [eax+0x28], 0
    a.label("ret")
    a.b("c3")
    code = bytearray(a.assemble())
    _require(len(code) <= TABLE_OFFSET, "the number-scale cave outgrew its code budget")
    code += b"\xcc" * (TABLE_OFFSET - len(code)) + table_bytes(rows)
    _require(len(code) <= CODE_SIZE, "the number-scale table outgrew the owner")
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    after = b"\xe9" + struct.pack("<i", code_va - (HOOK_VA + 5))
    return [("number_scale_hook", HOOK_VA, HOOK_RETAIL, after.ljust(len(HOOK_RETAIL), b"\x90"))]


# ------------------------------------------------------------------------------------------------ owner state

def _space():
    from . import nfl2k5_xbe_space as space
    return space


def allocation(payload: bytes) -> dict | None:
    space = _space()
    if space.status(payload) != "applied":
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and rows[0]["kind"] == "code" and rows[0]["size"] == CODE_SIZE,
             "foreign number-scale allocation")
    return rows[0]


def _guards(payload: bytes, hooked: bool) -> None:
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        if hooked and va <= HOOK_VA and HOOK_VA + len(HOOK_RETAIL) <= va + size:
            blob[HOOK_VA - va:HOOK_VA - va + len(HOOK_RETAIL)] = HOOK_RETAIL
        _require(_sha(bytes(blob)) == digest, f"foreign number-scale prerequisite at {va:#x}")
    binder = image.read(BINDER_VA, 1)[0]
    _require(binder in (0x3D, KERNING_BINDER_BYTE), "foreign number binder")


def _state(payload: bytes) -> tuple[str, dict | None, dict]:
    from . import nfl2k5_rdata_sites as rdata
    from .nfl2k5_cave_oracle import XbeImage
    space = _space()
    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    found = allocation(payload)
    if found is None:
        _require(rdata.status(payload, sites(0x14DA000)) == "retail", "the number hook changed without an allocation")
        _guards(payload, False)
        return "retail", None, {}
    blob = XbeImage(payload).read(found["va"], CODE_SIZE)
    if blob == b"\xcc" * CODE_SIZE:
        _require(rdata.status(payload, sites(found["va"])) == "retail", "the number hook changed with an empty owner")
        _guards(payload, False)
        return "retail", found, {}
    scales = read_table(blob)
    _require(blob == code_for(found["va"], scales), "foreign number-scale code")
    _require(rdata.status(payload, sites(found["va"])) == "applied", "mixed number-scale hook")
    _guards(payload, True)
    return "applied", found, scales


def status(payload: bytes) -> str:
    """retail / applied / foreign for default.xbe."""
    try:
        return _state(payload)[0]
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError, UnicodeError):
        return "foreign"


def read_settings(payload: bytes) -> dict:
    try:
        state, _found, scales = _state(payload)
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError, UnicodeError):
        return {"status": "foreign", "scales": {}}
    return {"status": state, "scales": scales}


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in _space().reservations(payload) if r["owner"] == OWNER]
    found = allocation(payload)
    edits = sites(found["va"] if found else 0x14DA000)
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in edits]


def apply(payload: bytes, scales: Mapping[str, float]) -> tuple[bytes, Mapping[str, object]]:
    """Install the owner (a late allocator owner) and its hook for ``scales``; {} leaves the executable unchanged.
    Idempotent for the same table; a different installed table refuses (rebuild from the original)."""
    from . import nfl2k5_rdata_sites as rdata
    space = _space()
    wanted = normalize(scales)
    state, found, installed = _state(payload)
    common = {"owner": OWNER, "label": LABEL, "experimental": True, "runtime_witnessed": False, "scales": wanted}
    if not wanted:
        _require(state == "retail", "the executable already carries a number-scale table; rebuild from the original")
        return payload, {**common, "status": "retail", "changed_bytes": 0, "edits": []}
    if state == "applied":
        _require(installed == wanted, "the executable carries another number-scale table; rebuild from the original")
        return payload, {**common, "status": "applied", "already_applied": True, "changed_bytes": 0, "edits": []}
    before = payload
    if found is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        found = allocation(payload)
    _require(found is not None, "reserve the number-scale allocation first")
    with_code, code_receipt = space.install_code(payload, OWNER, code_for(found["va"], wanted))
    result, site_receipt = rdata.apply(with_code, sites(found["va"]), OWNER)
    _require(status(result) == "applied" and read_settings(result)["scales"] == wanted,
             "number-scale postcondition failed")
    return result, {**common, **site_receipt, "status": "applied", "already_applied": False,
                    "code_install": code_receipt, "code_va": hex(found["va"]),
                    "code_end": hex(found["va"] + CODE_SIZE), "hook_va": hex(HOOK_VA),
                    "changed_bytes": sum(a != b for a, b in zip(before, result)) + abs(len(result) - len(before)),
                    "before_sha256": _sha(before), "after_sha256": _sha(result)}


__all__ = ["OWNER", "REQUESTS", "BUILD_KEY", "BUILD_CAPTION", "HELP_TEXT", "TeamNumberScaleError", "normalize",
           "transform", "anchor_v", "code_for", "sites", "table_bytes", "read_table", "status", "read_settings",
           "reservations", "apply"]

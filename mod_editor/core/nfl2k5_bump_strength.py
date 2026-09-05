"""Bump-strength (detail-scale) editor for the NFL 2K5 retail XBE.

A10 E3 proved the binding chain: FUN_0008e4b0 switches on the bump material
type code (0xC=jersey, 0xD=pants, 0xE=sleeve, 0xF=sock) and pushes a
per-material detail-scale float into FUN_0008e290, which multiplies it by a
constant, clamps to 0..255, and stores the byte at +9 of the material record.
Retail values: jersey 0.1 (0x3DCCCCCD), pants 0.3 (0x3E99999A), sleeve 0.1
(shared immediate with jersey), sock 0.0 (``push imm8``, not a float).

This module finds those push sites by byte pattern (never by blind hardcoded
offsets alone), reads the current strengths, and rewrites the float
immediates on a COPY of the XBE.  After patching it recomputes the affected
XBE section digest (A2 scheme: SHA1(u32le(raw_size) || raw)); the RSA
signature cannot be recomputed without the private key, so patched XBEs are
xemu-only (xemu enforces no XBE integrity, A2) unless resign tooling exists.
The sock slot is read-only here: its retail encoding is a 2-byte ``push 0``
with no room for a 5-byte float push, and repurposing dead code is out of
scope for a fail-closed writer.

Local-only, uncommitted research tooling: nothing here ships.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import shutil
import stat
import struct
from pathlib import Path

from . import platform_compat

XBE_MAGIC = b"XBEH"
RETAIL_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
IMAGE_BASE = 0x10000
SECTION_COUNT = 22
SECTION_HEADER_SIZE = 56
SECTION_TABLE_FIELDS = "<9I20s"

STRENGTH_SLOTS = ("jersey", "pants", "sleeve", "sock")
RETAIL_STRENGTHS: dict[str, float] = {
    "jersey": 0.1,
    "pants": 0.3,
    "sleeve": 0.1,
    "sock": 0.0,
}
SLOT_TYPE_CODES = {"jersey": 0xC, "pants": 0xD, "sleeve": 0xE, "sock": 0xF}

# lea -0xc(%ebx); cmp $0x3,%eax; ja default; jmp *table(,%eax,4)
SWITCH_PATTERN = bytes.fromhex("8d43f483f8037728ff2485")
# flds 0x4(%esp); push %ecx; fmuls <rdata>  -- the scale->byte callee prologue
CALLEE_PROLOGUE = bytes.fromhex("d944240451d80d")
SOCK_PUSH = bytes.fromhex("6a00")
FLOAT_PUSH = 0x68
MAX_STRENGTH = 1.0

READ_SCHEMA = "nfl2k5_bump_strength_read/v1"
WRITE_SCHEMA = "nfl2k5_bump_strength_write/v1"


class BumpStrengthError(ValueError):
    """Raised when the XBE, pattern, or strength request fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BumpStrengthError(message)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _regular_non_link(path: Path) -> os.stat_result:
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode), f"not a regular file: {path}")
    return info


@dataclass(frozen=True, slots=True)
class StrengthSite:
    slot: str
    type_code: int
    handler_offset: int
    float_offset: int | None
    kind: str  # "float" or "push_imm8"
    shared_with: str | None


@dataclass(frozen=True, slots=True)
class _Section:
    index: int
    header_offset: int
    virtual_address: int
    raw_offset: int
    raw_size: int
    stored_digest: bytes


def _find_unique(payload: bytes, pattern: bytes, label: str) -> int:
    first = payload.find(pattern)
    _require(first >= 0, f"XBE lacks the {label} pattern")
    _require(payload.find(pattern, first + 1) < 0,
             f"XBE has more than one {label} pattern")
    return first


def _sections(payload: bytes) -> list[_Section]:
    _require(payload[:4] == XBE_MAGIC, "file is not an XBE (missing XBEH)")
    image_base = struct.unpack_from("<I", payload, 0x104)[0]
    _require(image_base == IMAGE_BASE,
             f"XBE image base is 0x{image_base:x}, not 0x{IMAGE_BASE:x}")
    count, table_va = struct.unpack_from("<II", payload, 0x11C)
    grown_headers = (count in (SECTION_COUNT + 2, SECTION_COUNT + 3, SECTION_COUNT + 4) and table_va == 0x10370
                     and payload[0xDA0:0xDA8] in (b"XSPACE1\0", b"XSPACE2\0")
                     and struct.unpack_from("<I", payload, 0x108)[0] == 0x1000)
    if grown_headers and count >= SECTION_COUNT + 3:
        from . import nfl2k5_xbe_space as space, nfl2k5_music_storage as music_storage
        base = music_storage.unwrap(payload)[0] if space.has_music(payload) else payload
        if struct.unpack_from("<I", base, 0x11C)[0] == SECTION_COUNT + 3:
            space._library(base, True)
            h = space.META_START + 112
            _require(len(base) == space.EXT_FILE_SIZE and
                     base[h:h+56] == space._descriptor("code2", base[h+36:h+56]),
                     "foreign extended code section geometry")
    _require(count == SECTION_COUNT or grown_headers,
             f"XBE declares {count} sections, not {SECTION_COUNT}")
    table_offset = table_va - image_base
    _require(0 <= table_offset < len(payload), "section table is outside the file")
    sections: list[_Section] = []
    for index in range(count):
        header = table_offset + index * SECTION_HEADER_SIZE
        _require(header + SECTION_HEADER_SIZE <= len(payload),
                 "section table is truncated")
        fields = struct.unpack_from(SECTION_TABLE_FIELDS, payload, header)
        sections.append(
            _Section(
                index=index,
                header_offset=header,
                virtual_address=fields[1],
                raw_offset=fields[3],
                raw_size=fields[4],
                stored_digest=fields[9],
            )
        )
    return sections


def _section_for_offset(sections: list[_Section], offset: int) -> _Section:
    for section in sections:
        if section.raw_offset <= offset < section.raw_offset + section.raw_size:
            return section
    raise BumpStrengthError(
        f"offset 0x{offset:x} is not inside any XBE section"
    )


def section_digest(payload: bytes, section: _Section) -> bytes:
    return hashlib.sha1(  # nosec B324 - XBE section scheme, not security
        struct.pack("<I", section.raw_size)
        + payload[section.raw_offset : section.raw_offset + section.raw_size]
    ).digest()


def _callee_offset(payload: bytes, handler_offset: int, push_size: int) -> int:
    """Resolve the e8 rel32 call following the push to a file offset."""

    call_offset = handler_offset + push_size
    _require(payload[call_offset] == 0xE8,
             f"handler at 0x{handler_offset:x} has no call after its push")
    relative = struct.unpack_from("<i", payload, call_offset + 1)[0]
    target_va = (call_offset + 5) + IMAGE_BASE + relative
    _require(target_va >= IMAGE_BASE, "call target precedes the image base")
    target = target_va - IMAGE_BASE
    _require(0 <= target < len(payload), "call target is outside the file")
    _require(payload[target : target + len(CALLEE_PROLOGUE)] == CALLEE_PROLOGUE,
             f"call target 0x{target:x} is not the scale-to-byte callee")
    return target


def locate_sites(payload: bytes) -> tuple[list[StrengthSite], int]:
    """Find the four bump-strength push sites; return (sites, callee_offset)."""

    switch_offset = _find_unique(payload, SWITCH_PATTERN, "bump-strength switch")
    # SWITCH_PATTERN ends at the `jmp *disp32(,%eax,4)` opcode; the following
    # 4 bytes are the jump-table VA, which we resolve to a file offset.
    table_va = struct.unpack_from("<I", payload,
                                  switch_offset + len(SWITCH_PATTERN))[0]
    _require(table_va >= IMAGE_BASE, "jump table precedes the image base")
    table_offset = table_va - IMAGE_BASE
    _require(table_offset + 16 <= len(payload),
             "bump-strength jump table is outside the file")
    targets = struct.unpack_from("<4I", payload, table_offset)
    sites: list[StrengthSite] = []
    float_sites: dict[int, str] = {}
    callee: int | None = None
    for case_index, target_va in enumerate(targets):
        slot = STRENGTH_SLOTS[case_index]
        _require(target_va >= IMAGE_BASE,
                 f"jump table entry {case_index} precedes the image base")
        handler = target_va - IMAGE_BASE
        _require(0 <= handler < len(payload) - 7,
                 f"jump table entry {case_index} is outside the file")
        if payload[handler] == FLOAT_PUSH:
            float_offset = handler + 1
            value = struct.unpack_from("<f", payload, float_offset)[0]
            _require(0.0 <= value <= MAX_STRENGTH,
                     f"{slot} push immediate {value} is not a plausible "
                     "detail scale")
            this_callee = _callee_offset(payload, handler, push_size=5)
            callee = this_callee if callee is None else callee
            _require(this_callee == callee,
                     "bump-strength handlers call different callees")
            shared_with = None
            for previous_offset, previous_slot in float_sites.items():
                if previous_offset == float_offset:
                    shared_with = previous_slot
            float_sites[float_offset] = slot
            sites.append(
                StrengthSite(
                    slot=slot,
                    type_code=SLOT_TYPE_CODES[slot],
                    handler_offset=handler,
                    float_offset=float_offset,
                    kind="float",
                    shared_with=shared_with,
                )
            )
        elif payload[handler : handler + 2] == SOCK_PUSH:
            _require(slot == "sock",
                     f"push-imm8 handler found for {slot!r}, not sock")
            this_callee = _callee_offset(payload, handler, push_size=2)
            callee = this_callee if callee is None else callee
            _require(this_callee == callee,
                     "bump-strength handlers call different callees")
            sites.append(
                StrengthSite(
                    slot=slot,
                    type_code=SLOT_TYPE_CODES[slot],
                    handler_offset=handler,
                    float_offset=None,
                    kind="push_imm8",
                    shared_with=None,
                )
            )
        else:
            raise BumpStrengthError(
                f"jump table entry {case_index} at 0x{handler:x} is neither a "
                "float push nor the sock push-immediate"
            )
    _require(callee is not None, "no bump-strength handlers were resolved")
    return sites, callee


def _read_float(payload: bytes, site: StrengthSite) -> float:
    if site.kind == "push_imm8":
        return 0.0
    assert site.float_offset is not None
    return struct.unpack_from("<f", payload, site.float_offset)[0]


def read_strengths(xbe_path: Path | str) -> dict[str, object]:
    """Read the current per-material bump detail scales from an XBE."""

    path = Path(xbe_path).expanduser().resolve(strict=True)
    _regular_non_link(path)
    payload = path.read_bytes()
    sites, callee = locate_sites(payload)
    strengths = {site.slot: _read_float(payload, site) for site in sites}
    return {
        "schema": READ_SCHEMA,
        "xbe": str(path),
        "xbe_sha256": _digest(payload),
        "matches_retail_sha256": _digest(payload) == RETAIL_XBE_SHA256,
        "callee_offset": f"0x{callee:x}",
        "sites": [
            {
                "slot": site.slot,
                "type_code": f"0x{site.type_code:X}",
                "kind": site.kind,
                "handler_offset": f"0x{site.handler_offset:x}",
                "float_offset": (
                    f"0x{site.float_offset:x}"
                    if site.float_offset is not None
                    else None
                ),
                "shared_with": site.shared_with,
                "value": strengths[site.slot],
            }
            for site in sites
        ],
        "strengths": strengths,
        "retail_strengths": dict(RETAIL_STRENGTHS),
        "sock_editable": False,
    }


def _validate_strength(slot: str, value: float) -> None:
    _require(value == value and value not in (float("inf"), float("-inf")),
             f"{slot} strength must be a finite float")
    _require(0.0 <= value <= MAX_STRENGTH,
             f"{slot} strength {value} is outside 0.0..{MAX_STRENGTH}")


def write_strengths(
    source_xbe: Path | str,
    target_xbe: Path | str,
    *,
    jersey: float | None = None,
    pants: float | None = None,
    sleeve: float | None = None,
    sock: float | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    """Rewrite bump detail scales on a COPY of the XBE.

    By default the target must not exist; with ``overwrite=True`` an existing
    target is replaced (a target that IS the source is always refused).  The
    affected section digest is recomputed; the RSA signature stays stale
    (xemu-only output, see module docstring).
    """

    requests = {"jersey": jersey, "pants": pants, "sleeve": sleeve,
                "sock": sock}
    _require(
        sock is None,
        "sock strength is read-only: retail encodes it as a 2-byte push 0 "
        "with no room for a float immediate",
    )
    wanted = {
        slot: float(value) for slot, value in requests.items()
        if value is not None
    }
    _require(bool(wanted), "no strength changes were requested")
    for slot, value in wanted.items():
        _validate_strength(slot, value)

    source = Path(source_xbe).expanduser().resolve(strict=True)
    target = Path(target_xbe).expanduser()
    source_info = _regular_non_link(source)
    if target.exists():
        _require(overwrite,
                 f"target already exists; pass overwrite=True to replace it: "
                 f"{target}")
        target_info = target.lstat()
        _require(
            (source_info.st_dev, source_info.st_ino)
            != (target_info.st_dev, target_info.st_ino),
            "source and target are the same file; the target must be a copy",
        )
        _require(stat.S_ISREG(target_info.st_mode),
                 f"target is not a regular file: {target}")
        target.unlink()
    _require(str(source) != str(target.resolve()),
             "source and target are the same path; the target must be a copy")
    original = source.read_bytes()
    source_sha = _digest(original)
    sites, callee = locate_sites(original)
    sections = _sections(original)

    shared_groups: dict[int, list[str]] = {}
    for site in sites:
        if site.slot in wanted and site.float_offset is not None:
            shared_groups.setdefault(site.float_offset, []).append(site.slot)
    for slots in shared_groups.values():
        bits = {
            struct.unpack("<I", struct.pack("<f", wanted[slot]))[0]
            for slot in slots
        }
        _require(
            len(bits) == 1,
            f"slots {', '.join(slots)} share one float immediate in the XBE "
            "and must be given the same strength",
        )

    plan: list[tuple[StrengthSite, float, float]] = []
    for site in sites:
        if site.slot not in wanted:
            continue
        new_value = wanted[site.slot]
        _require(site.kind == "float" and site.float_offset is not None,
                 f"{site.slot} strength is not float-encoded")
        old_value = struct.unpack_from("<f", original, site.float_offset)[0]
        old_bits = struct.unpack_from("<I", original, site.float_offset)[0]
        new_bits = struct.unpack("<I", struct.pack("<f", new_value))[0]
        _require(old_bits != new_bits,
                 f"{site.slot} strength already equals the requested value")
        plan.append((site, old_value, new_value))
    _require(bool(plan), "requested changes matched the existing values")

    touched_sections = sorted(
        {
            _section_for_offset(sections, site.float_offset).index
            for site, _old, _new in plan
        }
    )
    digest_updates: list[dict[str, object]] = []
    for index in touched_sections:
        section = sections[index]
        before = section_digest(original, section)
        _require(
            before == section.stored_digest,
            f"section {index} digest is already stale; refusing to patch a "
            "previously modified XBE",
        )

    payload = bytearray(original)
    changes: list[dict[str, object]] = []
    float_writes: list[tuple[int, bytes]] = []
    for site, old_value, new_value in plan:
        assert site.float_offset is not None
        struct.pack_into("<f", payload, site.float_offset, new_value)
        new_bits = struct.unpack_from("<I", payload, site.float_offset)[0]
        float_writes.append(
            (site.float_offset, struct.pack("<I", new_bits))
        )
        changes.append(
            {
                "slot": site.slot,
                "shared_with": site.shared_with,
                "float_offset": f"0x{site.float_offset:x}",
                "old": old_value,
                "new": new_value,
                "old_bits":
                    f"0x{struct.unpack_from('<I', original, site.float_offset)[0]:08x}",
                "new_bits": f"0x{new_bits:08x}",
                "_float_offset": site.float_offset,
            }
        )
    digest_writes: list[tuple[int, bytes]] = []
    for index in touched_sections:
        section = sections[index]
        after = section_digest(bytes(payload), section)
        digest_writes.append((section.header_offset + 36, after))
        digest_updates.append(
            {
                "section": index,
                "raw_offset": f"0x{section.raw_offset:x}",
                "raw_size": section.raw_size,
                "digest_before": section.stored_digest.hex(),
                "digest_after": after.hex(),
                "_section_index": index,
            }
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    descriptor = os.open(
        target, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        for offset, word in float_writes:
            written = platform_compat.pwrite(descriptor, word, offset)
            _require(written == len(word), "short write on a strength float")
        for offset, digest_bytes in digest_writes:
            written = platform_compat.pwrite(descriptor, digest_bytes, offset)
            _require(written == len(digest_bytes),
                     "short write on a section digest")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    for update in digest_updates:
        del update["_section_index"]
    for change in changes:
        del change["_float_offset"]

    result = Path(target).read_bytes()
    verify_sites, _verify_callee = locate_sites(result)
    verified = {site.slot: _read_float(result, site) for site in verify_sites}
    for slot, value in wanted.items():
        _require(
            struct.unpack("<I", struct.pack("<f", verified[slot]))[0]
            == struct.unpack("<I", struct.pack("<f", value))[0],
            f"post-write readback disagrees for {slot}",
        )
    result_sections = _sections(result)
    for index in touched_sections:
        section = result_sections[index]
        _require(section_digest(result, section) == section.stored_digest,
                 f"section {index} digest does not match after patching")
    _require(len(result) == len(original), "patched XBE changed size")
    expected_changed = {
        offset + byte
        for offset, _word in float_writes
        for byte in range(4)
    }
    expected_changed.update(
        offset + byte for offset, _digest_bytes in digest_writes
        for byte in range(20)
    )
    actual_changed = {
        offset
        for offset, (old_byte, new_byte) in enumerate(zip(original, result))
        if old_byte != new_byte
    }
    _require(
        actual_changed <= expected_changed,
        "patched XBE differs from the source outside the requested floats "
        "and their section digests",
    )
    _require(bool(actual_changed), "patch produced no byte changes")
    return {
        "schema": WRITE_SCHEMA,
        "source": {
            "xbe": str(source),
            "sha256": source_sha,
            "matches_retail_sha256": source_sha == RETAIL_XBE_SHA256,
        },
        "target": {
            "xbe": str(target),
            "sha256": _digest(result),
        },
        "callee_offset": f"0x{callee:x}",
        "changes": changes,
        "section_digests": digest_updates,
        "verified_strengths": verified,
        "signature_status": (
            "RSA signature left stale; patched XBE is xemu-only (xemu "
            "enforces no XBE integrity, A2). Real hardware needs a resign "
            "this tool cannot produce."
        ),
    }


__all__ = [
    "BumpStrengthError",
    "READ_SCHEMA",
    "RETAIL_STRENGTHS",
    "RETAIL_XBE_SHA256",
    "STRENGTH_SLOTS",
    "StrengthSite",
    "WRITE_SCHEMA",
    "locate_sites",
    "read_strengths",
    "section_digest",
    "write_strengths",
]

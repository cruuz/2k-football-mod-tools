#!/usr/bin/env python3
"""Derive the NFL 2K5 and APF 2K8 camera-options surface from the binaries.

This is the machine-readable companion to ``docs/product/CAMERA_MAP.md``. It
reads the two executables and re-derives, rather than restating: the menu row
tables, every row's label, kind, live global and five callbacks, the min/max/step
constants each callback actually loads, the preset name tables, and the preset
parameter data. Nothing is hardcoded that the file itself can answer.

It is read-only. It never opens a save, never writes a game file, and it emits
no vertex or pixel payload -- only addresses, sizes, hashes and the small
scalar constants the menu itself displays.

Two boundaries are recorded rather than implied, because both have been got
wrong before:

* **2K5 has six camera presets, not eight.** ``.rdata`` there is a run of
  adjacent enum label tables, each ending in a ``Custom`` entry that points at
  the same string. The table after the camera one begins ``1st Person``,
  ``Broadcast`` -- so reading past six silently walks into the replay-camera
  enum. This tool bounds the read by the MAX callback's own immediate and
  records that immediate as the evidence.
* **The bound constants are pooled compiler literals.** 0.0 at 0x004E4180 has
  thousands of consumers. Nothing here may be used to edit a constant in place;
  the per-row operand addresses are emitted instead.

Nothing in the output is a runtime claim. No game was launched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "vc_camera_options_audit/v1"

DEFAULT_XBE = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
DEFAULT_APF_PE = Path("/tmp/apf.pe")
DEFAULT_OUTPUT = ROOT / "reports/gameplay_tuning/camera_options_audit.json"

NFL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
NFL_XBE_SIZE = 11_948_032
APF_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
APF_PE_SIZE = 54_001_664

#: Per-section VA - raw deltas for the 2K5 XBE. The ``.text`` +0x10000 shortcut
#: is wrong for every UI string in this game, so each section is mapped on its
#: own; these are re-derived from the section table and asserted below.
NFL_SECTIONS = {
    ".text": (0x00011000, 0x00001000),
    ".rdata": (0x004E3AE0, 0x004D9000),
    ".data": (0x00A69980, 0x00A5F000),
    ".string_": (0x00E60320, 0x00AEF000),
}

NFL_CAMERA_ROW_TABLE = 0x0052B700
NFL_ROW_STRIDE = 0x34
NFL_PRESET_LABELS = 0x004F25BC
NFL_PRESET_RECORDS = 0x004F047C
NFL_PRESET_RECORD_STRIDE = 0xE8

APF_BASE = 0x82000000
APF_CAMERA_ROW_TABLE = 0x84E40940
APF_ROW_STRIDE = 0x60
APF_PRESET_NAMES = 0x820D9FA0
APF_PRESET_BLOCKS = 0x84E11E00
APF_PRESET_BLOCK_STRIDE = 0x440
APF_PRESET_SLOT_STRIDE = 0x40
APF_PRESET_SLOTS = 17


class AuditError(ValueError):
    """The pinned input drifted, or a derived structure did not hold."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_pinned(path: Path, size: int, digest: str, label: str) -> bytes:
    require(path.is_file() and not path.is_symlink(),
            f"{label} must be a regular non-symlink file: {path}")
    payload = path.read_bytes()
    require(len(payload) == size, f"{label} size drift: {len(payload)} != {size}")
    require(sha256_bytes(payload) == digest, f"{label} SHA-256 drift")
    return payload


# --------------------------------------------------------------------------
# NFL 2K5
# --------------------------------------------------------------------------

def nfl_sections(image: bytes) -> dict[str, tuple[int, int, int]]:
    """Re-derive the section table instead of trusting the constants above.

    Returns ``name -> (virtual_address, raw_offset, raw_size)``. Each section is
    mapped on its own: the ``.text`` +0x10000 delta does not apply to ``.rdata``,
    ``.data`` or ``.string_``, and using it for a UI string silently reads the
    wrong bytes.
    """

    base = struct.unpack_from("<I", image, 0x104)[0]
    count = struct.unpack_from("<I", image, 0x11C)[0]
    headers = struct.unpack_from("<I", image, 0x120)[0] - base
    found: dict[str, tuple[int, int, int]] = {}
    for index in range(count):
        offset = headers + index * 0x38
        _flags, va, _vsize, raw, raw_size, name_ptr = struct.unpack_from(
            "<IIIIII", image, offset
        )
        name = image[name_ptr - base : name_ptr - base + 16].split(b"\0")[0]
        found[name.decode("latin1")] = (va, raw, raw_size)
    for name, expected in NFL_SECTIONS.items():
        actual = found.get(name)
        require(actual is not None and actual[:2] == expected,
                f"2K5 section {name} moved: {actual} != {expected}")
    return found


def nfl_reader(image: bytes, sections: dict[str, tuple[int, int, int]]):
    """Read by VA through the section that actually CONTAINS it.

    Selecting the first section whose arithmetic happens to land inside the file
    picks the wrong bytes -- several sections overlap once their deltas are
    applied. Containment is the only correct test.
    """

    def read(va: int, size: int) -> bytes:
        for name, (section_va, raw, raw_size) in sections.items():
            if section_va <= va < section_va + raw_size:
                offset = va - section_va + raw
                require(offset + size <= len(image),
                        f"2K5 read at {va:#010x} runs past {name}")
                return image[offset : offset + size]
        raise AuditError(f"2K5 VA {va:#010x} is outside every mapped section")
    return read


def nfl_string(image: bytes, sections: dict[str, tuple[int, int, int]], va: int,
               limit: int = 64) -> str:
    """UTF-16LE, NUL terminated. ASCII needles find nothing in this title."""

    section_va, raw, _raw_size = sections[".string_"]
    offset = va - section_va + raw
    out: list[str] = []
    for index in range(limit):
        pair = image[offset + index * 2 : offset + index * 2 + 2]
        if len(pair) < 2:
            break
        code = pair[0] | (pair[1] << 8)
        if code == 0:
            break
        out.append(chr(code))
    return "".join(out)


def nfl_float_operand(body: bytes) -> int | None:
    """The absolute address an ``fld dword ptr [imm32]`` callback loads.

    ``d9 05 <imm32>`` is the whole body of every min/max callback in this menu,
    which is exactly why they are getters and not clamps.
    """

    if len(body) >= 6 and body[0] == 0xD9 and body[1] == 0x05:
        return struct.unpack_from("<I", body, 2)[0]
    return None


def nfl_int_operand(body: bytes) -> int | None:
    """The immediate an int getter returns.

    Two forms appear: ``b8 <imm32>`` (``mov eax, imm32``) for a non-zero bound
    and ``33 c0`` (``xor eax, eax``) for zero, which the compiler prefers. A
    decoder that only knows the first reports every minimum as unknown.
    """

    if len(body) >= 5 and body[0] == 0xB8:
        return struct.unpack_from("<I", body, 1)[0]
    if len(body) >= 3 and body[0] == 0x33 and body[1] == 0xC0:
        return 0
    return None


def audit_nfl(image: bytes) -> dict[str, Any]:
    sections = nfl_sections(image)
    read = nfl_reader(image, sections)

    rows: list[dict[str, Any]] = []
    for index in range(16):
        base = NFL_CAMERA_ROW_TABLE + NFL_ROW_STRIDE * index
        words = struct.unpack("<13I", read(base, 52))
        kind, label_ptr = words[0], words[1]
        if kind == 3 and label_ptr == 0:
            break  # the table's own terminator
        require(label_ptr != 0, f"2K5 camera row {index} has no label")
        callbacks = {
            "maximum": words[3], "minimum": words[4], "current": words[5],
            "increment": words[6], "decrement": words[7],
        }
        row: dict[str, Any] = {
            "index": index,
            "row_virtual_address": f"0x{base:08X}",
            "kind": kind,
            "label": nfl_string(image, sections, label_ptr),
            "label_virtual_address": f"0x{label_ptr:08X}",
            "callbacks": {k: f"0x{v:08X}" for k, v in callbacks.items()},
        }
        if kind in (5, 7):
            row["label_lookup"] = f"0x{words[8]:08X}"
            row["label_width_helper"] = f"0x{words[9]:08X}"
        maximum_body = read(callbacks["maximum"], 8)
        minimum_body = read(callbacks["minimum"], 8)
        float_max = nfl_float_operand(maximum_body)
        if float_max is not None:
            float_min = nfl_float_operand(minimum_body)
            row["stored_type"] = "float32"
            row["maximum"] = struct.unpack("<f", read(float_max, 4))[0]
            row["minimum"] = struct.unpack("<f", read(float_min, 4))[0]
            row["maximum_constant_virtual_address"] = f"0x{float_max:08X}"
            row["minimum_constant_virtual_address"] = f"0x{float_min:08X}"
            # The operand, not the constant: the constants are pooled literals
            # with thousands of unrelated consumers.
            row["maximum_operand_file_offset"] = (
                f"0x{callbacks['maximum'] - sections['.text'][0] + sections['.text'][1] + 2:06X}"
            )
            row["minimum_operand_file_offset"] = (
                f"0x{callbacks['minimum'] - sections['.text'][0] + sections['.text'][1] + 2:06X}"
            )
        else:
            row["stored_type"] = "int32"
            row["maximum"] = nfl_int_operand(maximum_body)
            row["minimum"] = nfl_int_operand(minimum_body)
        rows.append(row)

    require(len(rows) == 7, f"2K5 camera table row count drift: {len(rows)}")

    enum_rows = [row for row in rows if row["kind"] == 7]
    require(len(enum_rows) == 1, "2K5 camera table must hold exactly one enum row")
    preset_maximum = enum_rows[0]["maximum"]
    require(isinstance(preset_maximum, int) and 0 < preset_maximum < 32,
            "2K5 camera preset maximum is not a small non-negative immediate")
    preset_count = preset_maximum + 1

    presets: list[dict[str, Any]] = []
    for index in range(preset_count):
        name_ptr = struct.unpack("<I", read(NFL_PRESET_LABELS + index * 4, 4))[0]
        record = NFL_PRESET_RECORDS + index * NFL_PRESET_RECORD_STRIDE
        block_ptr = struct.unpack("<I", read(record, 4))[0]
        entry: dict[str, Any] = {
            "index": index,
            "name": nfl_string(image, sections, name_ptr),
            "record_virtual_address": f"0x{record:08X}",
            "descriptor_virtual_address": f"0x{block_ptr:08X}" if block_ptr else None,
        }
        if block_ptr:
            block = read(block_ptr, 0x50)
            entry["descriptor_kind"] = struct.unpack_from("<I", block, 0)[0]
            entry["position"] = list(struct.unpack_from("<3f", block, 0x10))
            entry["field_0x20"] = struct.unpack_from("<f", block, 0x20)[0]
            entry["update_function"] = f"0x{struct.unpack_from('<I', block, 0x40)[0]:08X}"
        presets.append(entry)

    return {
        "game": "ESPN NFL 2K5",
        "platform": "original Xbox",
        "row_table_virtual_address": f"0x{NFL_CAMERA_ROW_TABLE:08X}",
        "row_stride": NFL_ROW_STRIDE,
        "callback_slot_order": ["maximum", "minimum", "current", "increment", "decrement"],
        "rows": rows,
        "preset_label_table_virtual_address": f"0x{NFL_PRESET_LABELS:08X}",
        "preset_count": preset_count,
        "preset_count_evidence": (
            "the enum row's MAX callback returns this immediate; .rdata here is a "
            "run of adjacent enum label tables, so reading past it walks into the "
            "next enum (which begins '1st Person', 'Broadcast')"
        ),
        "presets": presets,
        "custom_preset_index": next(
            (p["index"] for p in presets if p["name"] == "Custom"), None
        ),
        "float_settings_apply_only_in_custom": True,
        "writer_available": False,
        "writer_boundary": (
            "camera values live in the save, not the executable; the save is "
            "covered by a 20-byte XCalculateSignature EXTRA that is compared "
            "exactly on load, and every menu constant is inside a digested XBE "
            "section"
        ),
    }


# --------------------------------------------------------------------------
# APF 2K8
# --------------------------------------------------------------------------

def apf_reader(image: bytes):
    def read(va: int, size: int) -> bytes:
        offset = va - APF_BASE
        require(0 <= offset <= len(image) - size, f"APF VA {va:#010x} out of range")
        return image[offset : offset + size]
    return read


def apf_string(image: bytes, va: int, limit: int = 64) -> str:
    """UTF-16BE. This title stores text big-endian; ASCII needles find nothing."""

    offset = va - APF_BASE
    out: list[str] = []
    for index in range(limit):
        pair = image[offset + index * 2 : offset + index * 2 + 2]
        if len(pair) < 2:
            break
        code = (pair[0] << 8) | pair[1]
        if code == 0:
            break
        out.append(chr(code))
    return "".join(out)


def apf_constant(image: bytes, read, va: int) -> tuple[str, Any] | None:
    """Decode one PowerPC min/max getter.

    Two forms, both three instructions and neither of them a clamp:
    ``li r3, imm; blr`` returns an integer bound, and
    ``lis r11, hi; lfs f1, lo(r11); blr`` returns the float at ``(hi<<16)+lo``.
    """

    words = struct.unpack(">3I", read(va, 12))
    if (words[0] >> 16) == 0x3860 and words[1] == 0x4E800020:
        value = words[0] & 0xFFFF
        return "int32", value - 0x10000 if value & 0x8000 else value
    if (words[0] >> 16) == 0x3D60 and (words[1] >> 16) == 0xC02B:
        high = words[0] & 0xFFFF
        low = words[1] & 0xFFFF
        address = (high << 16) + (low - 0x10000 if low & 0x8000 else low)
        return "float32", struct.unpack(">f", read(address, 4))[0]
    return None


def audit_apf(image: bytes) -> dict[str, Any]:
    read = apf_reader(image)

    rows: list[dict[str, Any]] = []
    for index in range(16):
        base = APF_CAMERA_ROW_TABLE + APF_ROW_STRIDE * index
        words = struct.unpack(">8I", read(base, 32))
        kind, label_ptr = words[0], words[1]
        if kind > 32 or not (0x84500000 <= label_ptr < 0x8462C7DA):
            break  # past the end of the table
        row: dict[str, Any] = {
            "index": index,
            "row_virtual_address": f"0x{base:08X}",
            "kind": kind,
            "label": apf_string(image, label_ptr),
            "label_virtual_address": f"0x{label_ptr:08X}",
            "callbacks": {
                "maximum": f"0x{words[3]:08X}", "minimum": f"0x{words[4]:08X}",
                "current": f"0x{words[5]:08X}", "increment": f"0x{words[6]:08X}",
                "decrement": f"0x{words[7]:08X}",
            },
        }
        high = apf_constant(image, read, words[3])
        low = apf_constant(image, read, words[4])
        if high is not None and low is not None and high[0] == low[0]:
            row["stored_type"] = high[0]
            row["maximum"] = high[1]
            row["minimum"] = low[1]
        rows.append(row)
    require(len(rows) == 9, f"APF camera table row count drift: {len(rows)}")

    # The name pointers run on past the camera enum into the NEXT enum label
    # table, exactly as they do in 2K5's .rdata. Reading to the end of the
    # pointer run yields 16 names ending 'TV Broadcast', 'In Stands',
    # 'On Field', 'Custom', 'On', 'Off' -- the replay-camera enum plus a
    # boolean, not camera presets. Bound the list from the DATA instead: a
    # camera preset is an index whose parameter block is fully populated and
    # carries a non-zero slot-0 eye position. That admits 0..5 and rejects
    # 'Broadcast' at 6, whose block is present but entirely zero.
    raw_names: list[str] = []
    for index in range(16):
        pointer = struct.unpack(">I", read(APF_PRESET_NAMES + index * 4, 4))[0]
        if not (0x84500000 <= pointer < 0x8462C7DA):
            break
        raw_names.append(apf_string(image, pointer))

    def _authored(index: int) -> bool:
        body = read(APF_PRESET_BLOCKS + index * APF_PRESET_BLOCK_STRIDE,
                    APF_PRESET_BLOCK_STRIDE)
        populated = sum(
            1 for slot in range(APF_PRESET_SLOTS)
            if any(body[slot * APF_PRESET_SLOT_STRIDE : (slot + 1) * APF_PRESET_SLOT_STRIDE])
        )
        return populated == APF_PRESET_SLOTS and any(struct.unpack_from(">3f", body, 0x10))

    names: list[str] = []
    for index, name in enumerate(raw_names):
        if not _authored(index):
            break
        names.append(name)
    require(len(names) >= 5, f"APF camera preset run collapsed to {len(names)}")
    beyond = raw_names[len(names) : len(names) + 4]

    presets: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        block = APF_PRESET_BLOCKS + index * APF_PRESET_BLOCK_STRIDE
        body = read(block, APF_PRESET_BLOCK_STRIDE)
        populated = sum(
            1 for slot in range(APF_PRESET_SLOTS)
            if any(body[slot * APF_PRESET_SLOT_STRIDE : (slot + 1) * APF_PRESET_SLOT_STRIDE])
        )
        presets.append({
            "index": index,
            "name": name,
            "block_virtual_address": f"0x{block:08X}",
            "slot0_kind": struct.unpack_from(">I", body, 0)[0],
            "slot0_eye": list(struct.unpack_from(">3f", body, 0x10)),
            "populated_slots": populated,
            "slot_count": APF_PRESET_SLOTS,
            "authored": populated == APF_PRESET_SLOTS
            and any(struct.unpack_from(">3f", body, 0x10)),
        })

    return {
        "game": "All-Pro Football 2K8",
        "platform": "Xbox 360",
        "row_table_virtual_address": f"0x{APF_CAMERA_ROW_TABLE:08X}",
        "row_stride": APF_ROW_STRIDE,
        "rows": rows,
        "preset_name_table_virtual_address": f"0x{APF_PRESET_NAMES:08X}",
        "preset_name_count": len(names),
        "preset_count_evidence": (
            "bounded by authored parameter data, not by the pointer run: the "
            "name pointers continue into the next enum label table. The first "
            "names beyond the camera enum are "
            + ", ".join(repr(name) for name in beyond)
            + " -- the replay-camera enum, which also appears verbatim in 2K5's "
            ".rdata. Reading past this bound is the same off-by-table error on "
            "both products."
        ),
        "preset_block_table_virtual_address": f"0x{APF_PRESET_BLOCKS:08X}",
        "presets": presets,
        "menu_reachable_preset_count": 5,
        "menu_bound_sites": {
            "increment_compare": "0x84A15D00",
            "decrement_wrap": "0x84A15D5C",
            "maximum_callback": "0x84A15540",
        },
        "menu_bound_note": (
            "the increment and decrement bounds are hard-coded immediates and do "
            "not read maximum(), which is why an authored preset above the bound "
            "is unreachable"
        ),
        "writer_available": False,
        "writer_boundary": (
            "no serializer for the camera block exists anywhere in the image; the "
            "21-slider blob stops one dword short of the first camera global, so "
            "there is no camera file to edit and the only route is a XEX patch"
        ),
    }


def build_report(xbe_path: Path, pe_path: Path) -> dict[str, Any]:
    xbe = read_pinned(xbe_path, NFL_XBE_SIZE, NFL_XBE_SHA256, "NFL 2K5 XBE")
    pe = read_pinned(pe_path, APF_PE_SIZE, APF_PE_SHA256, "APF decompressed PE")
    return {
        "schema": SCHEMA,
        "scope": {
            "read_only": True,
            "originals_modified": False,
            "emulator_or_game_launched": False,
            "runtime_behaviour_claimed": False,
            "asset_side_camera_representation_found": False,
        },
        "inputs": {
            "nfl_xbe": {"size": len(xbe), "sha256": sha256_bytes(xbe)},
            "apf_decompressed_pe": {"size": len(pe), "sha256": sha256_bytes(pe)},
        },
        "nfl2k5": audit_nfl(xbe),
        "apf2k8": audit_apf(pe),
        "shared_boundary": (
            "Neither product exposes a camera writer. Every camera constant is "
            "inside a signed executable, and the gameplay camera has no "
            "asset-side representation in either archive."
        ),
    }


def canonical_json(report: dict[str, Any]) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, default=DEFAULT_XBE)
    parser.add_argument("--apf-pe", type=Path, default=DEFAULT_APF_PE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        report = build_report(args.xbe, args.apf_pe)
    except (AuditError, OSError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    payload = canonical_json(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(
        "CAMERA_OPTIONS_AUDIT_OK "
        f"nfl_rows={len(report['nfl2k5']['rows'])} "
        f"nfl_presets={report['nfl2k5']['preset_count']} "
        f"apf_rows={len(report['apf2k8']['rows'])} "
        f"apf_preset_names={report['apf2k8']['preset_name_count']} "
        f"writers=0 runtime=false sha256={sha256_bytes(payload)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

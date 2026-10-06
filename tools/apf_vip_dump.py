#!/usr/bin/env python3
"""Read APF 2K8 Xbox 360 VIP saves without modifying a save.

The raw .USR layout is established by the retail BASE executable's native
copy routines. Most individual statistics remain unnamed. Their numeric views
are explicitly interpretations, and a complete hex image preserves every byte.
Xenia .header sidecars are metadata, not STFS signatures. Signed STFS input is
hash-checked by the existing extractor; RSA authentication is never claimed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
from typing import Any

# Embeddable CPython does not prepend the script directory to sys.path.
_TOOLS = str(Path(__file__).resolve().parent)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import apf_stfs_roster_extract as stfs


SCHEMA = "apf2k8_vip_dump/v1"
USR_SIZE = 0x4FE8
PRIMARY_SIZE = 0x1410
SUPPLEMENTARY_SIZE = 0x3BD8
XENIA_HEADER_SIZE = 0x148
APF_TITLE_ID = 0x54540807

# Direct native UI label/formatter loads; computed formatter results are excluded.
# Tuple: offset, display label, native type, table entry, label VA, formatter VA, load PC.
PRIMARY_STAT_FIELDS = (
    (0x1068, 'Points', 'u32be', 0x821042c0, 0x84624100, 0x84765a00, 0x84765a1c),
    (0x1078, 'Points Allowed', 'u32be', 0x821042e0, 0x84624160, 0x84765c08, 0x84765c24),
    (0x1088, 'First Downs', 'u32be', 0x82104300, 0x84624200, 0x84765e10, 0x84765e2c),
    (0x108c, 'Carries', 'u32be', 0x82104308, 0x84624218, 0x84765e98, 0x84765eb4),
    (0x1094, 'Pass Attempts', 'u32be', 0x82104318, 0x84624248, 0x84765fa0, 0x84765fbc),
    (0x1098, 'Completions', 'u32be', 0x82104320, 0x84624264, 0x84766028, 0x84766044),
    (0x109c, 'Completion %', 'float32be', 0x82104328, 0x8462427c, 0x847660b0, 0x847660c4),
    (0x10a0, 'Touchdowns Rushing', 'u32be', 0x82104330, 0x84624298, 0x84766140, 0x8476615c),
    (0x10a4, 'Touchdowns Passing', 'u32be', 0x82104338, 0x846242c0, 0x847661c8, 0x847661e4),
    (0x10a8, 'Kick Return Touchdowns', 'u32be', 0x82104340, 0x846242e8, 0x84766250, 0x8476626c),
    (0x10ac, 'Punt Return Touchdowns', 'u32be', 0x82104348, 0x84624318, 0x847662d8, 0x847662f4),
    (0x10b0, 'Interception Touchdowns', 'u32be', 0x82104350, 0x84624348, 0x84766360, 0x8476637c),
    (0x10b4, 'Fumble Touchdowns', 'u32be', 0x82104358, 0x84624378, 0x847663e8, 0x84766404),
    (0x10b8, 'Tackles', 'u32be', 0x82104360, 0x8462439c, 0x84766470, 0x8476648c),
    (0x10bc, 'Interceptions', 'u32be', 0x82104368, 0x846243ac, 0x847664f8, 0x84766514),
    (0x10c0, 'Sacks', 'u32be', 0x82104370, 0x846243c8, 0x84766580, 0x8476659c),
    (0x10c4, 'Defensive Touchdowns', 'u32be', 0x82104378, 0x846243d4, 0x84766608, 0x84766624),
    (0x10c8, '3rd Down Conversion Attempts', 'u32be', 0x82104380, 0x84624400, 0x84766690, 0x847666ac),
    (0x10cc, '3rd Down Conversions', 'u32be', 0x82104388, 0x8462443c, 0x84766718, 0x84766734),
    (0x10d0, '3rd Down Conversion %', 'float32be', 0x82104390, 0x84624468, 0x847667a0, 0x847667b4),
    (0x10d4, '4th Down Conversion Attempts', 'u32be', 0x82104398, 0x84624494, 0x84766830, 0x8476684c),
    (0x10d8, '4th Down Conversions', 'u32be', 0x821043a0, 0x846244d0, 0x847668b8, 0x847668d4),
    (0x10dc, '4th Down Conversion %', 'float32be', 0x821043a8, 0x846244fc, 0x84766940, 0x84766954),
    (0x10e0, 'Redzone Possessions', 'u32be', 0x821043b0, 0x84624528, 0x847669d0, 0x847669ec),
    (0x10e4, 'Redzone Field Goals', 'u32be', 0x821043b8, 0x84624550, 0x84766a58, 0x84766a74),
    (0x10e8, 'Redzone Touchdowns', 'u32be', 0x821043c0, 0x84624578, 0x84766ae0, 0x84766afc),
    (0x10ec, 'Redzone Scoring %', 'float32be', 0x821043c8, 0x846245a0, 0x84766b68, 0x84766b7c),
    (0x10f0, 'Redzone Stands', 'u32be', 0x821043d0, 0x846245c4, 0x84766bf8, 0x84766c14),
    (0x10f4, 'Redzone Field Goals Allowed', 'u32be', 0x821043d8, 0x846245e4, 0x84766c80, 0x84766c9c),
    (0x10f8, 'Redzone Touchdowns Allowed', 'u32be', 0x821043e0, 0x8462461c, 0x84766d08, 0x84766d24),
    (0x10fc, 'Redzone Scoring % Allowed', 'float32be', 0x821043e8, 0x84624654, 0x84766d90, 0x84766da4),
    (0x1100, 'Extra Point Attempts', 'u32be', 0x821043f0, 0x84624688, 0x84766e20, 0x84766e3c),
    (0x1104, 'Extra Point Conversions', 'u32be', 0x821043f8, 0x846246b4, 0x84766ea8, 0x84766ec4),
    (0x1108, '2pt Conversion Attempts', 'u32be', 0x82104400, 0x846246e4, 0x84766f30, 0x84766f4c),
    (0x110c, '2pt Conversions', 'u32be', 0x82104408, 0x84624714, 0x84766fb8, 0x84766fd4),
    (0x1110, '2pt Conversion %', 'float32be', 0x82104410, 0x84624734, 0x84767040, 0x84767054),
    (0x1114, 'Running Plays', 'u32be', 0x82104418, 0x84624758, 0x847670d0, 0x847670ec),
    (0x1118, 'Pass Plays', 'u32be', 0x82104420, 0x84624774, 0x84767158, 0x84767174),
    (0x111c, 'Carries Outside Left', 'u32be', 0x82104428, 0x8462478c, 0x847671e0, 0x847671fc),
    (0x1120, 'Carries Inside Left', 'u32be', 0x82104430, 0x846247b8, 0x84767268, 0x84767284),
    (0x1124, 'Carries Inside Right', 'u32be', 0x82104438, 0x846247e0, 0x847672f0, 0x8476730c),
    (0x1128, 'Carries Outside Right', 'u32be', 0x82104440, 0x8462480c, 0x84767378, 0x84767394),
    (0x113c, 'Pass Attempts Left', 'u32be', 0x82104468, 0x84624914, 0x84767600, 0x8476761c),
    (0x1140, 'Pass Attempts Middle', 'u32be', 0x82104470, 0x8462493c, 0x84767688, 0x847676a4),
    (0x1144, 'Pass Attempts Right', 'u32be', 0x82104478, 0x84624968, 0x84767710, 0x8476772c),
    (0x1148, 'Pass Attempts Left Short', 'u32be', 0x82104480, 0x84624990, 0x84767798, 0x847677b4),
    (0x114c, 'Pass Attempts Middle Short', 'u32be', 0x82104488, 0x846249c4, 0x84767820, 0x8476783c),
    (0x1150, 'Pass Attempts Right Short', 'u32be', 0x82104490, 0x846249fc, 0x847678a8, 0x847678c4),
    (0x1154, 'Pass Attempts Left Medium', 'u32be', 0x82104498, 0x84624a30, 0x84767930, 0x8476794c),
    (0x1158, 'Pass Attempts Middle Medium', 'u32be', 0x821044a0, 0x84624a64, 0x847679b8, 0x847679d4),
    (0x115c, 'Pass Attempts Right Medium', 'u32be', 0x821044a8, 0x84624a9c, 0x84767a40, 0x84767a5c),
    (0x1160, 'Pass Attempts Left Deep', 'u32be', 0x821044b0, 0x84624ad4, 0x84767ac8, 0x84767ae4),
    (0x1164, 'Pass Attempts Middle Deep', 'u32be', 0x821044b8, 0x84624b04, 0x84767b50, 0x84767b6c),
    (0x1168, 'Pass Attempts Right Deep', 'u32be', 0x821044c0, 0x84624b38, 0x84767bd8, 0x84767bf4),
    (0x116c, 'Completions Left', 'u32be', 0x821044c8, 0x84624b6c, 0x84767c60, 0x84767c7c),
    (0x1170, 'Completions Middle', 'u32be', 0x821044d0, 0x84624b90, 0x84767ce8, 0x84767d04),
    (0x1174, 'Completions Right', 'u32be', 0x821044d8, 0x84624bb8, 0x84767d70, 0x84767d8c),
    (0x1178, 'Completions Left Short', 'u32be', 0x821044e0, 0x84624bdc, 0x84767df8, 0x84767e14),
    (0x117c, 'Completions Middle Short', 'u32be', 0x821044e8, 0x84624c0c, 0x84767e80, 0x84767e9c),
    (0x1180, 'Completions Right Short', 'u32be', 0x821044f0, 0x84624c40, 0x84767f08, 0x84767f24),
    (0x1184, 'Completions Left Medium', 'u32be', 0x821044f8, 0x84624c70, 0x84767f90, 0x84767fac),
    (0x1188, 'Completions Middle Medium', 'u32be', 0x82104500, 0x84624ca0, 0x84768018, 0x84768034),
    (0x118c, 'Completions Right Medium', 'u32be', 0x82104508, 0x84624cd4, 0x847680a0, 0x847680bc),
    (0x1190, 'Completions Left Deep', 'u32be', 0x82104510, 0x84624d08, 0x84768128, 0x84768144),
    (0x1194, 'Completions Middle Deep', 'u32be', 0x82104518, 0x84624d34, 0x847681b0, 0x847681cc),
    (0x1198, 'Completions Right Deep', 'u32be', 0x82104520, 0x84624d64, 0x84768238, 0x84768254),
    (0x119c, 'Punt Returns', 'u32be', 0x82104528, 0x84624d94, 0x847682c0, 0x847682dc),
    (0x11a4, 'Kick Returns', 'u32be', 0x82104538, 0x84624dd4, 0x847683c8, 0x847683e4),
    (0x11ac, 'Penalties', 'u32be', 0x82104548, 0x84624e14, 0x847684d0, 0x847684ec),
    (0x11b0, 'Yards Penalized', 'u32be', 0x82104550, 0x84624e28, 0x84768558, 0x84768574),
    (0x11b4, 'Turnovers', 'u32be', 0x82104558, 0x84624e48, 0x847685e0, 0x847685fc),
    (0x11b8, 'Points Off Turnovers', 'u32be', 0x82104560, 0x84624e5c, 0x84768668, 0x84768684),
    (0x11bc, 'Punts', 'u32be', 0x82104568, 0x84624e88, 0x847686f0, 0x8476870c),
    (0x11c0, 'Punts Inside 20 Yard Line', 'u32be', 0x82104570, 0x84624e94, 0x84768778, 0x84768794),
    (0x11d4, 'Most Consecutive Games Rushing TD', 'u32be', 0x82104598, 0x84624f50, 0x84768a00, 0x84768a1c),
    (0x11d8, 'Most Consecutive Games Passing TD', 'u32be', 0x821045a0, 0x84624f98, 0x84768a88, 0x84768aa4),
)



class VipError(ValueError):
    """The input is unsupported, ambiguous, or malformed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VipError(message)


def _text(raw: bytes, encoding: str) -> dict[str, Any]:
    """Decode the bounded first terminated string; retain stale/padding bytes."""
    unit = 2 if encoding == "utf-16-be" else 1
    end = next((i for i in range(0, len(raw), unit)
                if raw[i:i + unit] == b"\0" * unit), len(raw))
    try:
        text = raw[:end].decode(encoding)
        error = None
    except UnicodeDecodeError as exc:
        text = None
        error = str(exc)
    return {
        "encoding": encoding,
        "text": text,
        "terminated": end < len(raw),
        "used_bytes": end,
        "raw_hex": raw.hex(),
        "decode_error": error,
    }


def _word(data: bytes, offset: int) -> dict[str, Any]:
    raw = data[offset:offset + 4]
    number = struct.unpack(">f", raw)[0]
    # Strict JSON has no NaN/Infinity; exact bits are always in raw_hex.
    float_view: float | str
    if math.isfinite(number):
        float_view = number
    else:
        float_view = "NaN" if math.isnan(number) else (
            "-Infinity" if number < 0 else "Infinity")
    return {
        "offset": offset,
        "offset_hex": f"0x{offset:04X}",
        "raw_hex": raw.hex(),
        "u32be": int.from_bytes(raw, "big"),
        "i32be": int.from_bytes(raw, "big", signed=True),
        "float32be_interpretation": float_view,
    }


def _float32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def _ui_ratio_math(numerator: float, denominator: float) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "UNSUPPORTED_INPUT",
                              "proportion_float32": None,
                              "displayed_integer_percent": None}

    def integer(value: float) -> int | None:
        if not math.isfinite(value):
            return None
        truncated = math.trunc(value)
        return truncated if -(1 << 31) <= truncated < (1 << 31) else None

    denominator_int = integer(denominator)
    if denominator_int is None:
        result["reason"] = "denominator conversion is non-finite or outside int32"
        return result
    result["denominator_integer"] = denominator_int
    if denominator_int <= 0:
        proportion = 0.0
    else:
        numerator_int = integer(numerator)
        if numerator_int is None:
            result["reason"] = "numerator conversion is non-finite or outside int32"
            return result
        result["numerator_integer"] = numerator_int
        proportion = _float32(_float32(float(numerator_int))
                              / _float32(float(denominator_int)))
    percent = integer(_float32(proportion * 100.0))
    result["proportion_float32"] = proportion
    if percent is None:
        result["reason"] = "percentage conversion is outside int32"
        return result
    result["displayed_integer_percent"] = percent
    result["status"] = "PROVED_NATIVE_ARITHMETIC_WITHIN_STATED_CONVERSION_BOUNDS"
    return result


def _motion_ui(data: bytes) -> dict[str, Any]:
    """Reproduce the bounded category-0 Motion viewer's integer/float math."""
    numerator = struct.unpack_from(">f", data, 0x3A28)[0]
    denominator = struct.unpack_from(">f", data, 0x39AC)[0]
    result: dict[str, Any] = {
        "status": "PROVED_NATIVE_UI_DISPLAY; EVENT_UNITS_AND_CPU_EFFECT_UNKNOWN",
        "numerator": {
            "name": "Motion UI ratio numerator",
            **_word(data, 0x3A28),
            "native_type": "float32be",
            "status": "PROVED_NATIVE_UI_RATIO_INPUT; EVENT_UNIT_UNKNOWN",
            "evidence": "context getter 0x84AE7258; initializer load 0x84A6C5F4 "
                        "from context+0x13F0; save context offset 0x2638",
        },
        "denominator": {
            "name": "Motion UI ratio denominator",
            **_word(data, 0x39AC),
            "native_type": "float32be",
            "status": "PROVED_NATIVE_UI_RATIO_INPUT; EVENT_UNIT_UNKNOWN",
            "evidence": "initializer load 0x84A6C5D8 from context+0x1374; "
                        "save context offset 0x2638",
        },
        "derived": {
            "status": "UNSUPPORTED_INPUT",
            "proportion_float32": None,
            "displayed_integer_percent": None,
            "rule": "Truncate denominator to signed int32; if <=0 use 0. "
                    "Otherwise truncate numerator to signed int32, round both "
                    "to float32, divide to float32, multiply by 100 to float32, "
                    "and truncate to signed int32 for the Motion %d%% viewer.",
            "evidence": "0x84A6C5D8..0x84A6C638; category-0 "
                        "0x84A6EA14..0x84A6EA60; label 0x84613FA0; "
                        "format 0x84614104; percent multiplier 0x820009B8",
            "limits": "Non-finite and signed-int32-overflow conversions are "
                      "unproved; default nearest float32 rounding is modeled.",
        },
        "warning": "This is the native VIP statistics viewer, not a CPU motion "
                   "probability. The source fields' event units/update rules are unknown.",
    }

    result["derived"].update(_ui_ratio_math(numerator, denominator))
    return result


def _other_ui_displays(data: bytes) -> list[dict[str, Any]]:
    # Component roles are established only in these UI formulas; their wider
    # event units, update rules and CPU consumers remain unknown.
    definitions = (
        ("Audible", ((0x276C, 0x84A6C6E0), (0x2748, 0x84A6C6DC)),
         ((0x2764, 0x84A6C6B8), (0x2740, 0x84A6C6BC)),
         0x84613FE8, "0x84A6C6B8..0x84A6C72C", "0x84A6EB80..0x84A6EBB8"),
        ("Formation Shifts", ((0x2770, 0x84A6C74C),), ((0x2764, 0x84A6C730),),
         0x84614080, "0x84A6C730..0x84A6C794", "0x84A6ED20..0x84A6ED40"),
        ("O-Line Adjustments", ((0x2778, 0x84A6C7B8), (0x2774, 0x84A6C7B4),
                                (0x277C, 0x84A6C7C4)), ((0x2764, 0x84A6C798),),
         0x846140A4, "0x84A6C798..0x84A6C808", "0x84A6ED84..0x84A6EDA4"),
    )
    results = []
    for name, numerator_fields, denominator_fields, label, initializer, formatter in definitions:
        def components(fields: tuple[tuple[int, int], ...], role: str) -> list[dict[str, Any]]:
            return [{"name": f"{name} UI ratio {role} component {index}",
                     **_word(data, offset), "native_type": "float32be",
                     "status": "PROVED_NATIVE_UI_RATIO_INPUT; EVENT_UNIT_UNKNOWN",
                     "evidence": {"load_instruction": f"0x{load:08X}",
                                  "context_delta": f"0x{offset - 0x2638:X}"}}
                    for index, (offset, load) in enumerate(fields)]

        def sum_components(fields: tuple[tuple[int, int], ...]) -> float:
            value = struct.unpack_from(">f", data, fields[0][0])[0]
            for offset, _ in fields[1:]:
                other = struct.unpack_from(">f", data, offset)[0]
                try:
                    value = _float32(value + other)
                except OverflowError:
                    value = math.copysign(math.inf, value + other)
            return value

        results.append({
            "name": name,
            "status": "PROVED_NATIVE_UI_DISPLAY; EVENT_UNITS_AND_CPU_EFFECT_UNKNOWN",
            "numerator_components": components(numerator_fields, "numerator"),
            "denominator_components": components(denominator_fields, "denominator"),
            "derived": {
                **_ui_ratio_math(sum_components(numerator_fields), sum_components(denominator_fields)),
                "rule": "Add components in listed order, rounding each addition to float32; "
                        "then apply the same truncate-int32 / denominator>0 / float32 ratio "
                        "and integer percent rule as the Motion UI viewer.",
                "limits": "Non-finite and signed-int32-overflow conversions are unproved; "
                          "default nearest float32 rounding is modeled.",
                "evidence": {"initializer": initializer, "formatter": formatter,
                             "label_pointer": f"0x{label:08X}"},
            },
            "warning": "UI display only. Event units, update/merge rules and CPU effects are unknown.",
        })
    return results


def parse_usr(data: bytes) -> dict[str, Any]:
    """Dump one exact native primary + supplementary VIP payload."""
    require(isinstance(data, bytes), "VIP input must be immutable bytes")
    require(len(data) == USR_SIZE,
            f"APF .USR payload must be {USR_SIZE} bytes (0x{USR_SIZE:X})")
    return {
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "profile_id": {
            **_word(data, 0),
            "status": "PROVED_NATIVE",
            "meaning": "profile identifier generated from a nonzero random value",
            "evidence": "retail BASE 0x8476CCF0..0x8476CCFC; clone 0x8476CDC4",
        },
        "name": {
            "offset": 4,
            "status": "PROVED_NATIVE",
            "capacity_utf16_units": 16,
            "evidence": "retail BASE name getter 0x84765730; create "
                        "0x8476CCE0..0x8476CCEC copies at most 16 UTF-16 units to primary+4",
            **_text(data[4:0x24], "utf-16-be"),
        },
        "typed_fields": [
            {
                "name": "field_0024",
                **_word(data, 0x24),
                "native_type": "float32be",
                "status": "PROVED_NATIVE_TYPE; UNKNOWN_MEANING",
                "evidence": "retail BASE getter/setter 0x84765760/0x84765768",
            },
            {
                "name": "field_0028",
                **_word(data, 0x28),
                "native_type": "u32be",
                "status": "PROVED_NATIVE_TYPE; UNKNOWN_MEANING",
                "evidence": "retail BASE getter/setter 0x84765770/0x84765778",
            },
        ],
        "display_statistics": {
            "status": "PROVED_NATIVE_UI_LABEL_AND_DIRECT_LOAD; CPU_EFFECT_UNPROVED",
            "warning": "Names identify VIP statistics shown by the native UI. "
                       "They do not prove CPU behavior. Values are stored values; "
                       "formatter unit conversion is not reproduced.",
            "fields": [
                {
                    "name": name,
                    **_word(data, offset),
                    "native_type": native_type,
                    "value": (_word(data, offset)["u32be"] if native_type == "u32be"
                              else _word(data, offset)["float32be_interpretation"]),
                    "status": "PROVED_NATIVE_UI_LABEL_AND_DIRECT_LOAD",
                    "evidence": {"table_entry": f"0x{table:08X}",
                                 "label_pointer": f"0x{label:08X}",
                                 "formatter": f"0x{formatter:08X}",
                                 "load_instruction": f"0x{load:08X}"},
                }
                for offset, name, native_type, table, label, formatter, load
                in PRIMARY_STAT_FIELDS
            ],
        },
        "motion_ui_display": _motion_ui(data),
        "other_ui_displays": _other_ui_displays(data),
        "regions": [
            {
                "name": "primary_profile",
                "offset": 0,
                "length": PRIMARY_SIZE,
                "status": "PROVED_NATIVE_ALLOCATION",
                "evidence": "retail BASE 0x847655B0 copies 0x1410 bytes",
                "field_meanings": "UNKNOWN except profile_id, name and display_statistics above",
            },
            {
                "name": "supplementary_profile",
                "offset": PRIMARY_SIZE,
                "length": SUPPLEMENTARY_SIZE,
                "status": "PROVED_NATIVE_ALLOCATION",
                "evidence": "retail BASE 0x84AE4DD0 size; 0x84AE4DD8 copy",
                "field_meanings": "UNKNOWN except mapped UI ratio input roles above",
            },
        ],
        "word_views": {
            "status": "UNKNOWN_FIELD_TYPES_AND_MEANINGS",
            "warning": "Multiple numeric interpretations are views of the same bytes; "
                       "none establishes a tendency, counter, or percentage.",
            "words": [_word(data, offset) for offset in range(0, len(data), 4)],
        },
        "opaque_record_view": {
            "status": "HYPOTHESIS_STRUCTURAL_VIEW_ONLY",
            "offset": 0x3F00,
            "stride": 0x20,
            "count": 128,
            "evidence": "repeated float-like pair/u16/small-byte pattern in supplied save; "
                        "runtime field types and row identities unproved",
            "records": [
                {
                    "index": index,
                    "offset": offset,
                    "raw_hex": data[offset:offset + 0x20].hex(),
                    "word0": _word(data, offset),
                    "word1": _word(data, offset + 4),
                    "u16be_at_plus8_interpretation": int.from_bytes(
                        data[offset + 8:offset + 10], "big"),
                }
                for index, offset in enumerate(range(0x3F00, 0x4F00, 0x20))
            ],
        },
        "lossless": {
            "encoding": "hex",
            "offset": 0,
            "length": len(data),
            "data": data.hex(),
        },
        "integrity": {
            "profile_id_is_checksum": False,
            "native_bank_transport_integrity": "NO_SIGNATURE_OPERATION_IN_AUDITED_COPY_FAMILY",
            "native_transport_evidence": "retail BASE load 0x847641C0; save 0x847655B0; "
                                         "supplementary copies 0x84AE4DD8/0x84AE4DF0",
            "filesystem_or_lifecycle_integrity": "UNKNOWN_OUTSIDE_ENUMERATED_NATIVE_TRANSPORT",
            "writer_available": False,
        },
    }


def parse_xenia_header(data: bytes) -> dict[str, Any]:
    """Interpret the bounded XCONTENT_AGGREGATE_DATA metadata sidecar."""
    require(isinstance(data, bytes), "Xenia header must be immutable bytes")
    require(len(data) == XENIA_HEADER_SIZE,
            "only the 328-byte Xenia aggregate metadata header is supported")
    return {
        "kind": "XCONTENT_AGGREGATE_DATA",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "layout_status": "PROVED_XENIA_SOURCE; NOT_USER_BUILD_IDENTITY",
        "evidence": "xenia-project/xenia 95a5c3ee250f80c3b9d139658649d9ffb6db3eec "
                    "src/xenia/kernel/xam/content_manager.h",
        "device_id": _word(data, 0),
        "content_type": _word(data, 4),
        "display_name": {"offset": 8, **_text(data[8:0x108], "utf-16-be")},
        "file_name": {"offset": 0x108, **_text(data[0x108:0x132], "ascii")},
        "padding_132_hex": data[0x132:0x134].hex(),
        "opaque_134": {
            "offset": 0x134,
            "raw_hex": data[0x134:0x13C].hex(),
            "u64be_interpretation": int.from_bytes(data[0x134:0x13C], "big"),
            "status": "UNKNOWN; upstream also leaves meaning unnamed",
        },
        "alignment_padding_13c_hex": data[0x13C:0x140].hex(),
        "title_id": _word(data, 0x140),
        "tail_padding_144_hex": data[0x144:0x148].hex(),
        "lossless_hex": data.hex(),
        "cryptographic_signature": "ABSENT_FROM_THIS_METADATA_LAYOUT",
    }


def _read(path: Path, maximum: int) -> bytes:
    require(not path.is_symlink(), f"refusing a symlink input: {path}")
    require(path.is_file(), f"input is not a regular file: {path}")
    require(path.stat().st_size <= maximum, f"input exceeds {maximum}-byte bound")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        data = stream.read(maximum + 1)
    require(len(data) <= maximum, "input grew beyond the read bound")
    return data


def _find_payload(source: Path) -> tuple[Path, Path | None]:
    require(not source.is_symlink(), f"refusing a symlink input: {source}")
    if source.is_file():
        return source, None
    require(source.is_dir(), f"input does not exist: {source}")
    candidates = [p for p in source.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".usr"]
    require(len(candidates) == 1,
            f"choose an individual .USR file: found {len(candidates)} in directory")
    payload = candidates[0]
    # Match the header by exact payload name; refuse competing metadata.
    headers = [p for p in source.rglob("*")
               if p.is_file() and p.name.lower() == (payload.name + ".header").lower()]
    require(len(headers) <= 1, "multiple metadata headers match this .USR")
    return payload, headers[0] if headers else None


def dump_path(source: Path, *, header: Path | None = None,
              member: str | None = None) -> dict[str, Any]:
    """Read a loose payload/tree or one hash-verified signed STFS member."""
    payload_path, discovered_header = _find_payload(source)
    raw = _read(payload_path, stfs.MAX_CONTAINER_BYTES)
    container: dict[str, Any] = {"kind": "raw_usr", "rsa_signature_verified": False}
    if raw[:4] in stfs.STFS_MAGICS:
        try:
            require(int.from_bytes(raw[0x360:0x364], "big") == APF_TITLE_ID,
                    "STFS package belongs to another title")
            require(int.from_bytes(raw[0x344:0x348], "big") == 1,
                    "STFS package is not saved-game content")
            reader = stfs._StfsReader(raw)
            entries = [entry for entry in reader.directory_entries()
                       if not entry.is_directory and entry.path.lower().endswith(".usr")]
            if member is not None:
                entries = [entry for entry in entries if entry.path == member]
            require(len(entries) == 1,
                    "STFS input needs exactly one .USR member; choose --member if ambiguous")
            entry = entries[0]
            require(entry.file_size == USR_SIZE, "STFS .USR member has unsupported size")
            payload = reader.extract(entry)
            container.update({
                "kind": reader.package_kind,
                "member": entry.path,
                "metadata_hash_verified": True,
                "active_hash_tree_verified": True,
                "data_blocks_verified": entry.block_count,
                "rsa_signature_note": "Signature storage exists but is not authenticated.",
            })
        except stfs.StfsRosterError as exc:
            raise VipError(str(exc)) from exc
    else:
        require(member is None, "--member applies only to STFS input")
        payload = raw
    selected_header = header if header is not None else discovered_header
    metadata = (parse_xenia_header(_read(selected_header, XENIA_HEADER_SIZE))
                if selected_header is not None else None)
    if metadata is not None:
        require(metadata["content_type"]["u32be"] == 1,
                "Xenia metadata is not saved-game content")
        require(metadata["title_id"]["u32be"] == APF_TITLE_ID,
                "Xenia metadata belongs to another title")
        require(metadata["file_name"]["text"] == payload_path.name,
                "Xenia metadata filename does not match the selected payload")
    result = {
        "schema": SCHEMA,
        "source": {"path": str(payload_path), "size": len(raw),
                   "sha256": hashlib.sha256(raw).hexdigest()},
        "container": container,
        "xenia_header": metadata,
        "vip": parse_usr(payload),
        "limitations": [
            "Field offsets and numeric views do not establish gameplay meanings.",
            "The Motion UI proportion is mapped; event units, formation/play "
            "usage identities and CPU behavior remain unproved.",
            "This reader supplies no save writer or console re-signing.",
            "Offline parsing is not a game-load or gameplay witness.",
        ],
    }
    if selected_header is not None:
        result["xenia_header"]["source_path"] = str(selected_header)
    return result


def write_json(document: dict[str, Any], destination: Path) -> None:
    """Create a new private JSON artifact; never overwrite any existing file."""
    encoded = (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2)
               + "\n").encode("utf-8")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="raw .USR, Xenia exported tree, or STFS save")
    parser.add_argument("--header", type=Path, help="optional Xenia 328-byte metadata sidecar")
    parser.add_argument("--member", help="exact .USR path inside an STFS save")
    parser.add_argument("--output", type=Path, help="new JSON file; existing paths are refused")
    args = parser.parse_args(argv)
    try:
        document = dump_path(args.source, header=args.header, member=args.member)
        if args.output is None:
            json.dump(document, sys.stdout, ensure_ascii=False, allow_nan=False, indent=2)
            sys.stdout.write("\n")
        else:
            write_json(document, args.output)
    except (VipError, OSError) as exc:
        parser.exit(2, f"apf_vip_dump: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

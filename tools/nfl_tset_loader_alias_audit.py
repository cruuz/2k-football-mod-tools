#!/usr/bin/env python3
"""Audit NFL 2K5 TSET decompression with the title's in-place memory layout.

This is a local, read-only compatibility test.  It reconstructs the allocation,
tail read, and forward VC-LZ decode performed by default.xbe at 0x451D0,
0x45280, and 0x45100.  It does not launch the game or alter any disc image.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Any

from nfl_txtr import decompress_vc_lz


ROOT = Path(__file__).resolve().parents[1]
HEADER = struct.Struct("<4s7I")
FEEDBEEF = 0xFEEDBEEF
SCHEMA = "nfl2k5_tset_loader_alias_audit/v1"

EXPECTED_RETAIL_ISO_SHA256 = (
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
EXPECTED_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)

HOME_XISO = Path(
    "/media/noah/Storage/.codex-tmp/nfl2k5-lions-png-import-xiso-20260711/"
    "ESPN-NFL-2K5-Lions-CODEX-MOD-jersey-layout-identical.xiso.iso"
)
AWAY_XISO = Path(
    "/media/noah/Storage/.codex-tmp/"
    "nfl2k5-actual-jersey-binding-away-probe-20260711/"
    "ESPN-NFL-2K5-Detroit-AWAY-CODEX-MOD-binding-probe.xiso.iso"
)
AWAY_MANIFEST = Path(
    "/media/noah/Storage/.codex-tmp/"
    "nfl2k5-actual-jersey-binding-away-probe-20260711/workflow_manifest.json"
)


class AuditError(RuntimeError):
    """Raised when a pinned alias-audit invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def pin_file(path: Path, expected_sha256: str | None = None) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    require(resolved.is_file(), f"not a regular file: {resolved}")
    digest = sha256_file(resolved)
    if expected_sha256 is not None:
        require(digest == expected_sha256, f"hash changed: {path}")
    return {
        "path": str(path),
        "size": resolved.stat().st_size,
        "sha256": digest,
        "opened_read_only": True,
    }


def read_span(path: Path, offset: int, size: int) -> bytes:
    resolved = path.resolve(strict=True)
    require(resolved.is_file(), f"not a regular file: {resolved}")
    require(offset >= 0 and size >= HEADER.size, "invalid span request")
    require(offset + size <= resolved.stat().st_size,
            f"span exceeds {path}: {offset}+{size}")
    with resolved.open("rb") as stream:
        stream.seek(offset)
        value = stream.read(size)
    require(len(value) == size, f"short read from {path}")
    return value


def align16(value: int) -> int:
    return (value + 15) & ~15


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    role: str
    path: Path
    offset: int
    span_size: int
    expected_span_sha256: str
    expected_decoded_sha256: str
    expected_consumed_bytes: int
    expected_scratch: int
    expected_exact_minimum: int
    expected_alias_safe: bool
    expected_first_collision: tuple[int, int, int, int, int] | None


def parse_wrapper(span: bytes) -> dict[str, Any]:
    require(len(span) >= HEADER.size, "span lacks a resource wrapper")
    kind, stored, system, video, compression, scratch, reserved0, reserved1 = \
        HEADER.unpack_from(span)
    require(kind == b"TSET", f"unexpected kind {kind!r}")
    require(compression == FEEDBEEF, "TSET is not VC-LZ compressed")
    require(reserved0 == reserved1 == 0, "TSET reserved words are nonzero")
    require(HEADER.size + stored == len(span), "TSET span length disagrees with +0x04")
    require(system + video > 0, "TSET decoded length is zero")
    return {
        "kind": kind.decode("ascii"),
        "stored_bytes": stored,
        "system_bytes": system,
        "video_bytes": video,
        "decoded_bytes": system + video,
        "compression_magic": "0xfeedbeef",
        "overlap_scratch_bytes": scratch,
        "reserved_words": [reserved0, reserved1],
    }


def token_requirements(body: bytes, decoded_bytes: int, stored_bytes: int) -> dict[str, Any]:
    require(len(body) == stored_bytes, "body length changed")
    require(len(body) >= 10, "compressed body is too short")
    require(struct.unpack_from("<I", body, 0)[0] == decoded_bytes,
            "stream output size disagrees with wrapper")
    offset_bits = body[8]
    require(1 <= offset_bits <= 15, "invalid VC-LZ offset width")
    distance_mask = (1 << offset_bits) - 1
    length_mask = (1 << (16 - offset_bits)) - 1
    source = 10
    flags = body[9]
    flag_mask = 1
    destination = 0
    token_index = 0
    maximum = -1
    maximum_at: dict[str, int] | None = None

    while destination < decoded_bytes:
        token_index += 1
        token_start = destination
        if flags & flag_mask:
            require(source + 2 <= len(body), "truncated reference token")
            code = struct.unpack_from("<H", body, source)[0]
            source += 2
            distance = code & distance_mask
            length = ((code >> offset_bits) & length_mask) + 3
            require(0 < distance <= token_start, "invalid reference token")
        else:
            require(source < len(body), "truncated literal token")
            source += 1
            length = 1
        destination += length
        require(destination <= decoded_bytes, "token overruns declared output")

        # During this token's high-to-low write, the next unread compressed
        # byte is at `source`.  Requiring the output endpoint not to cross it
        # yields A >= S - D + dst - src.  No source remains after the final
        # token, so the final boundary is intentionally excluded.
        if destination < decoded_bytes:
            required = stored_bytes - decoded_bytes + destination - source
            if required > maximum:
                maximum = required
                maximum_at = {
                    "token_index": token_index,
                    "output_endpoint": destination,
                    "next_unread_source_offset": source,
                }

        flag_mask = (flag_mask << 1) & 0xFF
        if flag_mask == 0:
            # The x86 decoder fetches the next flag byte before its loop-end
            # comparison.  That extra byte matters only when reporting the
            # loader cursor; it cannot cause a final-token write collision.
            require(source < len(body), "missing VC-LZ flag byte")
            flags = body[source]
            source += 1
            flag_mask = 1

    require(maximum_at is not None and maximum >= 0,
            "failed to derive an alias requirement")
    return {
        "exact_minimum_scratch_bytes": maximum,
        "maximum_at": maximum_at,
        "token_count": token_index,
        "loader_cursor_consumed_bytes": source,
    }


def alias_decode(
    body: bytes,
    decoded_bytes: int,
    stored_bytes: int,
    scratch_bytes: int,
    reference_consumed_bytes: int,
) -> dict[str, Any]:
    allocation_bytes = decoded_bytes + scratch_bytes
    source_start = allocation_bytes - stored_bytes
    require(source_start >= 0, "tail read would begin before the allocation")
    memory = bytearray(allocation_bytes)
    memory[source_start:source_start + stored_bytes] = body

    offset_bits = memory[source_start + 8]
    distance_mask = (1 << offset_bits) - 1
    length_mask = (1 << (16 - offset_bits)) - 1
    source = source_start + 10
    flags = memory[source_start + 9]
    flag_mask = 1
    destination = 0
    token_index = 0
    first_collision: dict[str, int | str] | None = None
    first_invalid_match: dict[str, int] | None = None
    used_source_end = source_start + reference_consumed_bytes

    while destination < decoded_bytes:
        token_index += 1
        token_start = destination
        token_kind = "match" if flags & flag_mask else "literal"
        if token_kind == "match":
            require(source + 2 <= len(memory), "aliased token read exceeds allocation")
            code = memory[source] | memory[source + 1] << 8
            source += 2
            distance = code & distance_mask
            length = ((code >> offset_bits) & length_mask) + 3
            if (distance == 0 or distance > token_start) and first_invalid_match is None:
                first_invalid_match = {
                    "token_index": token_index,
                    "output_cursor": token_start,
                    "distance": distance,
                    "length": length,
                    "source_cursor_relative": source - source_start,
                }
            for index in range(length - 1, -1, -1):
                write_address = token_start + index
                if (first_collision is None and
                        source <= write_address < used_source_end):
                    first_collision = {
                        "token_index": token_index,
                        "token_kind": token_kind,
                        "output_cursor_before": token_start,
                        "next_unread_source_absolute": source,
                        "next_unread_source_relative": source - source_start,
                        "first_overwrite_absolute": write_address,
                        "first_overwrite_source_relative": write_address - source_start,
                    }
                read_address = token_start - distance + index
                require(0 <= read_address < len(memory),
                        "corrupted match reads outside the modeled allocation")
                require(write_address < len(memory),
                        "corrupted match writes outside the modeled allocation")
                memory[write_address] = memory[read_address]
            destination += length
        else:
            require(source < len(memory), "aliased literal read exceeds allocation")
            if (first_collision is None and
                    source <= token_start < used_source_end):
                first_collision = {
                    "token_index": token_index,
                    "token_kind": token_kind,
                    "output_cursor_before": token_start,
                    "next_unread_source_absolute": source,
                    "next_unread_source_relative": source - source_start,
                    "first_overwrite_absolute": token_start,
                    "first_overwrite_source_relative": token_start - source_start,
                }
            require(token_start < len(memory), "literal writes outside allocation")
            memory[token_start] = memory[source]
            source += 1
            destination += 1

        flag_mask = (flag_mask << 1) & 0xFF
        if flag_mask == 0:
            require(source < len(memory), "aliased flag read exceeds allocation")
            flags = memory[source]
            source += 1
            flag_mask = 1

    output = bytes(memory[:decoded_bytes])
    return {
        "allocation_bytes": allocation_bytes,
        "source_start": source_start,
        "source_allocation_end": source_start + stored_bytes,
        "reference_source_consumed_end": source_start + reference_consumed_bytes,
        "decoded_output_end": decoded_bytes,
        "loader_cursor_consumed_bytes": source - source_start,
        "final_output_cursor": destination,
        "output_sha256": sha256_bytes(output),
        "first_unread_source_collision": first_collision,
        "first_invalid_match": first_invalid_match,
    }


def audit_case(spec: CaseSpec) -> dict[str, Any]:
    span = read_span(spec.path, spec.offset, spec.span_size)
    span_sha = sha256_bytes(span)
    require(span_sha == spec.expected_span_sha256,
            f"{spec.case_id}: span hash changed")
    wrapper = parse_wrapper(span)
    require(wrapper["overlap_scratch_bytes"] == spec.expected_scratch,
            f"{spec.case_id}: wrapper scratch changed")
    body = span[HEADER.size:]
    decoded, decode_info = decompress_vc_lz(body, wrapper["decoded_bytes"])
    decoded_sha = sha256_bytes(decoded)
    require(decoded_sha == spec.expected_decoded_sha256,
            f"{spec.case_id}: separate decode hash changed")
    require(decode_info.consumed_bytes == spec.expected_consumed_bytes,
            f"{spec.case_id}: compressed consumption changed")

    requirements = token_requirements(
        body, wrapper["decoded_bytes"], wrapper["stored_bytes"]
    )
    require(requirements["exact_minimum_scratch_bytes"] ==
            spec.expected_exact_minimum,
            f"{spec.case_id}: exact scratch minimum changed")
    unused = wrapper["stored_bytes"] - decode_info.consumed_bytes
    aligned_sufficient = align16(max(
        unused, requirements["exact_minimum_scratch_bytes"]
    ))
    repair_scratch = max(wrapper["overlap_scratch_bytes"], aligned_sufficient)

    alias = alias_decode(
        body, wrapper["decoded_bytes"], wrapper["stored_bytes"],
        wrapper["overlap_scratch_bytes"], decode_info.consumed_bytes,
    )
    alias_matches = alias["output_sha256"] == decoded_sha
    require(alias_matches == spec.expected_alias_safe,
            f"{spec.case_id}: alias safety changed")
    actual_collision = alias["first_unread_source_collision"]
    if spec.expected_first_collision is None:
        require(actual_collision is None, f"{spec.case_id}: unexpected collision")
    else:
        require(actual_collision is not None, f"{spec.case_id}: collision disappeared")
        assert actual_collision is not None
        observed = (
            int(actual_collision["output_cursor_before"]),
            int(actual_collision["next_unread_source_absolute"]),
            int(actual_collision["next_unread_source_relative"]),
            int(actual_collision["first_overwrite_absolute"]),
            int(actual_collision["first_overwrite_source_relative"]),
        )
        require(observed == spec.expected_first_collision,
                f"{spec.case_id}: collision coordinates changed: {observed}")

    corrected = alias_decode(
        body, wrapper["decoded_bytes"], wrapper["stored_bytes"],
        repair_scratch, decode_info.consumed_bytes,
    )
    require(corrected["output_sha256"] == decoded_sha,
            f"{spec.case_id}: sufficient-scratch probe did not round-trip")
    require(corrected["first_unread_source_collision"] is None and
            corrected["first_invalid_match"] is None,
            f"{spec.case_id}: sufficient-scratch probe still collides")

    return {
        "case_id": spec.case_id,
        "role": spec.role,
        "span": {
            "path": str(spec.path),
            "offset": spec.offset,
            "size": spec.span_size,
            "sha256": span_sha,
            "opened_read_only": True,
        },
        "wrapper": wrapper,
        "reference_decode": {
            "decoded_sha256": decoded_sha,
            "declared_output_bytes": decode_info.declared_output_size,
            "stream_tag": decode_info.stream_tag,
            "offset_bits": decode_info.offset_bits,
            "length_bits": decode_info.length_bits,
            "consumed_bytes": decode_info.consumed_bytes,
            "unused_trailing_bytes": unused,
            "literal_count": decode_info.literal_count,
            "match_count": decode_info.match_count,
        },
        "alias_requirement": {
            "equation": "A >= S - D + dst_endpoint - next_unread_src",
            **requirements,
            "current_scratch_bytes": wrapper["overlap_scratch_bytes"],
            "current_margin_bytes": (
                wrapper["overlap_scratch_bytes"] -
                requirements["exact_minimum_scratch_bytes"]
            ),
            "conservative_unused_bytes": unused,
            "aligned_sufficient_scratch_bytes": aligned_sufficient,
            "repair_scratch_bytes": repair_scratch,
        },
        "current_loader_alias": {
            **alias,
            "matches_reference_decode": alias_matches,
            "safe": alias_matches and actual_collision is None,
        },
        "sufficient_scratch_probe": {
            "scratch_bytes": repair_scratch,
            **corrected,
            "matches_reference_decode": True,
            "safe": True,
            "wrapper_or_input_file_modified": False,
        },
    }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    pins = {
        "retail_xiso": pin_file(args.retail_xiso, EXPECTED_RETAIL_ISO_SHA256),
        "retail_xbe": pin_file(args.xbe, EXPECTED_XBE_SHA256),
        "loader_trace": pin_file(
            args.loader_trace,
            "b74575dfb1ceb80c1926468fc64c876a59b0d9507584266a5009ae5adc27321f",
        ),
        "loader_pseudo_c": pin_file(
            args.loader_pseudo,
            "b5b5fa3f5b2a9bba9c292fb6d835a1f9b66fa41918e1f209c4839be57f9ef49f",
        ),
        "home_png_span": pin_file(
            args.home_span,
            "76630c16fe8e1b60fabbdd2ec6c8c100ae8020061c27765678ef81ea885d8ae8",
        ),
        "home_manifest": pin_file(
            args.home_manifest,
            "c4ddd7d3bd206d29d5a743dc78ea2ca69352807fcd643eacd3dcf4307e7b0f41",
        ),
        "donor_manifest": pin_file(
            args.donor_manifest,
            "810c5e34f153e3711b5046ab7c51fbf0d113606da64ae8259b8b231958dabd19",
        ),
        "away_manifest": pin_file(
            args.away_manifest,
            "420977b306b14ec1eb1457dab71c0a9c7bc95414b84aeb86c1ce9df4141b3836",
        ),
        "compatibility_tsv": pin_file(
            args.compatibility,
            "5f074fe299a2d23c10cca2b61a2ff9695684eeba0c134b32f9e82863051bbbb0",
        ),
    }

    home_manifest = load_json(args.home_manifest)
    away_manifest = load_json(args.away_manifest)
    require(home_manifest["patch"]["absolute_span_offset"] == 5_011_470_448,
            "HOME manifest span offset changed")
    require(home_manifest["patch"]["span_size"] == 74_720,
            "HOME manifest span size changed")
    require(away_manifest["target"]["absolute_span_offset"] == 4_718_884_976,
            "AWAY manifest span offset changed")
    require(away_manifest["target"]["span_size"] == 79_120,
            "AWAY manifest span size changed")
    require(away_manifest["target"]["stored_size"] == 79_088,
            "AWAY manifest stored size changed")

    home_xiso_span = read_span(args.home_xiso, 5_011_470_448, 74_720)
    require(home_xiso_span == args.home_span.read_bytes(),
            "HOME standalone and XISO spans differ")
    require(sha256_bytes(home_xiso_span) ==
            home_manifest["patch"]["replacement_span_sha256"],
            "HOME XISO span disagrees with its manifest")
    away_xiso_span = read_span(args.away_xiso, 4_718_884_976, 79_120)
    require(sha256_bytes(away_xiso_span) ==
            away_manifest["patch"]["replacement_span_sha256"],
            "AWAY XISO span disagrees with its manifest")

    cases = [
        CaseSpec(
            "retail_09H0", "retail Detroit current HOME target",
            args.retail_xiso, 5_011_470_448, 74_720,
            "9faf4c167d7837f2f0fb663c742733f384901de76f91a26bad3856b8358a7862",
            "92a7e5ed6b8d0b468c4782509cf6335f88dfa06e189d7b624f80600ce727aa1e",
            74_674, 32, 16, True, None,
        ),
        CaseSpec(
            "retail_01A0_donor", "retail Falcons current AWAY donor",
            args.retail_xiso, 4_623_452_272, 74_720,
            "0d6bcfe1f48ff0158a6c29be98cce56800a90bbd4754282e8fc876dea517dbd9",
            "de80718cf743f0a866b2d0381b5658a72bedd68644dc6a5bbf009cd2c523d95a",
            74_679, 16, 3, True, None,
        ),
        CaseSpec(
            "png_09H0_home", "existing Detroit HOME PNG replacement",
            args.home_span, 0, 74_720,
            "76630c16fe8e1b60fabbdd2ec6c8c100ae8020061c27765678ef81ea885d8ae8",
            "f5ed9101fa5c8bb742168b18fac698f57185c6b6a0190545ecafc1bb1b99c30e",
            22_285, 32, 52_392, False,
            (116_664, 116_669, 14_301, 116_681, 14_313),
        ),
        CaseSpec(
            "png_09A0_away", "existing Detroit AWAY PNG replacement",
            args.away_xiso, 4_718_884_976, 79_120,
            "390c36805ed9ad7c9fbd0d330873bf93cf728cc270a73375fa3460d3967d2f5b",
            "f5ed9101fa5c8bb742168b18fac698f57185c6b6a0190545ecafc1bb1b99c30e",
            22_285, 16, 56_792, False,
            (111_632, 111_639, 13_687, 111_649, 13_697),
        ),
    ]
    results = [audit_case(spec) for spec in cases]

    return {
        "schema": SCHEMA,
        "title": "ESPN NFL 2K5 TSET loader-alias audit",
        "scope": {
            "mode": "local_offline_static_and_emulated_loader_layout",
            "game_or_emulator_started": False,
            "game_binary_modified": False,
            "disc_images_modified": False,
            "case_count": len(results),
        },
        "source_pins": pins,
        "container_span_cross_checks": {
            "home_modified_xiso": {
                "path": str(args.home_xiso),
                "size": args.home_xiso.stat().st_size,
                "expected_container_sha256":
                    "b9f47fcec3e284a12ea30f390035dd29f97fa62507330ba3ff30391cf4e10ae6",
                "full_container_hash_recomputed_here": False,
                "relevant_span_sha256": sha256_bytes(home_xiso_span),
                "matches_standalone_span": True,
            },
            "away_modified_xiso": {
                "path": str(args.away_xiso),
                "size": args.away_xiso.stat().st_size,
                "expected_container_sha256":
                    "ac2a6556b9a6c77724a770c6665d5ea2d4b639e015fea468631a2faa8653b855",
                "full_container_hash_recomputed_here": False,
                "relevant_span_sha256": sha256_bytes(away_xiso_span),
                "matches_manifest": True,
            },
        },
        "recovered_loader_semantics": {
            "0x000451D0": (
                "read wrapper fields; allocate D+A bytes; choose TSET/HSET heap"
            ),
            "0x00045280": (
                "read S bytes to base+D+A-S and schedule 0x45100 completion"
            ),
            "0x00045100": (
                "forward-decompress from tail into base, shrink to D, relocate "
                "the TSET root and register embedded TXTR records"
            ),
            "symbols": {
                "D": "wrapper[+0x08] system bytes + wrapper[+0x0c] video bytes",
                "S": "wrapper[+0x04] stored bytes",
                "A": "wrapper[+0x14] overlap scratch bytes",
                "source_start": "base + D + A - S",
            },
            "collision_free_equation":
                "A >= max_nonfinal_tokens(S - D + dst_endpoint - next_unread_src)",
        },
        "cases": results,
        "conclusions": [
            {
                "claim": "Retail 09H0 and the exact retail 01A0 donor decode correctly in the title's aliased layout.",
                "confidence": "proved_by_loader_emulation",
            },
            {
                "claim": "Both existing PNG replacement streams overwrite unread compressed bytes because their much shorter streams retained the retail +0x14 scratch values.",
                "confidence": "proved_by_first_collision_and_hash_mismatch",
            },
            {
                "claim": "The alias failure explains the two PNG visual negatives but not the retail-donor negative.",
                "confidence": "bounded_conclusion",
            },
            {
                "claim": "Changing only +0x14 to 52416 (HOME) or 56816 (AWAY) makes the existing streams decode identically without changing +0x04, padding placement, or span size.",
                "confidence": "proved_offline_not_runtime",
            },
        ],
        "best_next_local_test": (
            "Make copy-only corrected spans with +0x14 set to the audited aligned "
            "values, then require this alias audit before packaging; runtime visibility "
            "remains a separate later checkpoint."
        ),
        "portme": [
            "PORTME: retain a loader-faithful alias check in every compressed TSET writer.",
            "PORTME: continue the separate registry/context investigation for the alias-safe retail donor negative.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-xiso", type=Path,
                        default=ROOT / "ESPN NFL 2K5 (USA).xiso.iso")
    parser.add_argument("--xbe", type=Path,
                        default=ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe")
    parser.add_argument("--home-span", type=Path, default=ROOT /
                        "reports/assets/nfl2k5_lions_09H0_diagnostic_png_import.tset.bin")
    parser.add_argument("--home-xiso", type=Path, default=HOME_XISO)
    parser.add_argument("--away-xiso", type=Path, default=AWAY_XISO)
    parser.add_argument("--home-manifest", type=Path, default=ROOT /
                        "reports/assets/nfl2k5_lions_09H0_diagnostic_png_import_xiso_direct.json")
    parser.add_argument("--donor-manifest", type=Path, default=ROOT /
                        "reports/assets/nfl2k5_jersey_tset_donor_xiso_direct.json")
    parser.add_argument("--away-manifest", type=Path, default=AWAY_MANIFEST)
    parser.add_argument("--compatibility", type=Path, default=ROOT /
                        "reports/assets/nfl2k5_jersey_tset_compatibility.tsv")
    parser.add_argument("--loader-trace", type=Path, default=ROOT /
                        "reports/assets/nfl_jersey_loader_cache_ghidra/"
                        "nfl_jersey_loader_cache_trace.txt")
    parser.add_argument("--loader-pseudo", type=Path, default=ROOT /
                        "reports/assets/nfl_jersey_loader_cache_ghidra/"
                        "nfl_jersey_loader_cache_pseudo_c.c")
    parser.add_argument("--output", type=Path, default=ROOT /
                        "reports/assets/nfl2k5_tset_loader_alias_audit.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    by_id = {case["case_id"]: case for case in report["cases"]}
    print(
        "NFL_TSET_LOADER_ALIAS_AUDIT_OK "
        f"cases={len(by_id)} retail_safe=2 png_unsafe=2 "
        f"home_min={by_id['png_09H0_home']['alias_requirement']['exact_minimum_scratch_bytes']} "
        f"home_fix={by_id['png_09H0_home']['alias_requirement']['repair_scratch_bytes']} "
        f"away_min={by_id['png_09A0_away']['alias_requirement']['exact_minimum_scratch_bytes']} "
        f"away_fix={by_id['png_09A0_away']['alias_requirement']['repair_scratch_bytes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

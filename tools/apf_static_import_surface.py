#!/usr/bin/env python3
"""Measure the exact XEX import surface referenced by APF's generated C++."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re


SCHEMA = "apf2k8_static_import_surface/v1"
EXPECTED_TREE_SHA256 = "6ac280d3fa0c6f016011ff176089ddbee4df4077c366a69623d9556db0e54599"
EXTERN_RE = re.compile(r"PPC_EXTERN_FUNC\((__imp__[A-Za-z0-9_]+)\);")
MAPPING_RE = re.compile(r"\{ (0x[0-9A-F]+), (__imp__[A-Za-z0-9_]+) \},")
CALL_RE = re.compile(r"\b(__imp__[A-Za-z0-9_]+)\s*\(ctx, base\)")


class SurfaceError(ValueError):
    """Raised when a pinned import or generated-code invariant changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SurfaceError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"path": str(path), "size": len(data), "sha256": digest(data)}


def lane(name: str) -> str:
    """Return a transparent name-prefix planning lane, not an ABI claim."""
    if name.startswith(("XamInput", "XInput")):
        return "input"
    if name.startswith(("XAudio", "XMA", "XamVoice")):
        return "audio_voice"
    if name.startswith(("NetDll_", "XNet")):
        return "network"
    if name.startswith(("Vd", "Mm")):
        return "graphics_memory"
    if name.startswith(("Xex", "XeCrypt", "XeKeys")):
        return "loader_crypto"
    if name.startswith(("Nt", "Ke", "Kf", "Ki", "Ex", "Ob", "Rtl", "Io",
                        "Fsc", "Stfs", "Hal")) or name in {
        "sprintf", "_vsnprintf", "DbgPrint", "__C_specific_handler"
    }:
        return "kernel_crt_io_sync"
    return "xam_system_profile_ui_or_other"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xex-report", type=Path, required=True)
    parser.add_argument("--static-probe", type=Path, required=True)
    parser.add_argument("--shared-header", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--generated-dir", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    args = parser.parse_args()

    xex_report = json.loads(args.xex_report.read_text(encoding="utf-8"))
    imports = xex_report["imports"]
    items = imports["items"]
    require(imports["logical_count"] == 347 and imports["thunk_count"] == 334,
            "APF XEX import cardinality changed")

    probe = json.loads(args.static_probe.read_text(encoding="utf-8"))
    generated = probe["generated_output"]
    require(generated["tree_sha256"] == EXPECTED_TREE_SHA256,
            "generated tree identity changed")

    callable_items = [item for item in items if item["thunk_address"] is not None]
    data_items = [item for item in items if item["thunk_address"] is None]
    require(len(callable_items) == 334 and len(data_items) == 13,
            "callable/data import split changed")

    shared_text = args.shared_header.read_text(encoding="utf-8")
    declared = set(EXTERN_RE.findall(shared_text))
    expected_symbols = {"__imp__" + item["name"] for item in callable_items}
    require(declared == expected_symbols, "generated import declarations differ")

    mapping_text = args.mapping.read_text(encoding="utf-8")
    mapped = {symbol: address for address, symbol in MAPPING_RE.findall(mapping_text)}
    require(set(mapped) == expected_symbols, "generated import mappings differ")
    for item in callable_items:
        require(mapped["__imp__" + item["name"]] == item["thunk_address"],
                f"thunk mapping differs for {item['name']}")

    translation_units = sorted(
        args.generated_dir.glob("ppc_recomp.*.cpp"),
        key=lambda path: int(path.name.split(".")[1]),
    )
    require(len(translation_units) == 236,
            "generated translated-code unit count changed")
    calls: Counter[str] = Counter()
    per_tu_state = hashlib.sha256()
    for source in translation_units:
        data = source.read_bytes()
        per_tu_state.update(source.name.encode("utf-8") + b"\0")
        per_tu_state.update(len(data).to_bytes(8, "big"))
        per_tu_state.update(hashlib.sha256(data).digest())
        calls.update(CALL_RE.findall(data.decode("utf-8")))
    require(set(calls).issubset(expected_symbols), "unknown generated import call")
    require(len(calls) == 333 and sum(calls.values()) == 1708,
            "generated import call surface changed")
    uncalled = sorted(expected_symbols - set(calls))
    require(uncalled == ["__imp____C_specific_handler"],
            "uncalled callable import set changed")

    rows: list[dict[str, object]] = []
    for item in items:
        symbol = "__imp__" + item["name"] if item["thunk_address"] else ""
        rows.append({
            "kind": "callable_thunk" if symbol else "data_slot",
            "library": item["library"],
            "library_version": item["library_version"],
            "ordinal": item["ordinal"],
            "name": item["name"],
            "reference_address": item["reference_address"],
            "thunk_address": item["thunk_address"] or "",
            "planning_lane": lane(item["name"]),
            "static_call_sites": calls.get(symbol, 0),
        })

    callable_rows = [row for row in rows if row["kind"] == "callable_thunk"]
    call_sites_by_library = Counter()
    symbols_by_library = Counter()
    call_sites_by_lane = Counter()
    symbols_by_lane = Counter()
    for row in callable_rows:
        sites = int(row["static_call_sites"])
        symbols_by_library[str(row["library"])] += 1
        call_sites_by_library[str(row["library"])] += sites
        symbols_by_lane[str(row["planning_lane"])] += 1
        call_sites_by_lane[str(row["planning_lane"])] += sites

    top = sorted(
        ({"name": row["name"], "library": row["library"],
          "call_sites": row["static_call_sites"]} for row in callable_rows),
        key=lambda row: (-int(row["call_sites"]), str(row["name"])),
    )[:25]
    report = {
        "schema": SCHEMA,
        "result": {
            "logical_import_count": len(rows),
            "callable_thunk_count": len(callable_rows),
            "data_slot_count": len(data_items),
            "callable_thunks_with_static_calls": len(calls),
            "callable_thunks_without_static_calls": len(uncalled),
            "generated_static_call_site_count": sum(calls.values()),
            "all_callable_imports_implemented": False,
            "native_title_runtime_exists": False,
        },
        "call_sites_by_library": dict(sorted(call_sites_by_library.items())),
        "symbols_by_library": dict(sorted(symbols_by_library.items())),
        "call_sites_by_planning_lane": dict(sorted(call_sites_by_lane.items())),
        "symbols_by_planning_lane": dict(sorted(symbols_by_lane.items())),
        "top_callable_imports": top,
        "uncalled_callable_symbols": uncalled,
        "data_imports": [row for row in rows if row["kind"] == "data_slot"],
        "interpretation": {
            "worked": (
                "The generated APF corpus exposes an exact 334-function guest ABI "
                "surface plus 13 imported data slots; 333 functions occur at 1,708 "
                "static call sites."
            ),
            "failed": (
                "No guest-ABI implementation is supplied by the translator, and "
                "the existing host adapters are deliberately not ABI-compatible."
            ),
            "boundary": (
                "Planning lanes are transparent name-prefix groupings only; static "
                "call counts do not establish boot reachability or safe no-op behavior."
            ),
        },
        "sources": {
            "xex_report": pin(args.xex_report),
            "static_probe": pin(args.static_probe),
            "shared_header": pin(args.shared_header),
            "mapping": pin(args.mapping),
            "generator": pin(Path(__file__)),
            "translation_unit_count": len(translation_units),
            "translation_unit_aggregate_sha256": per_tu_state.hexdigest(),
            "generated_tree_sha256": generated["tree_sha256"],
        },
        "portme": [
            "// PORTME: implement the 334 callable XAM/xboxkrnl guest-ABI thunks; a trap stub is not a title runtime.",
            "// PORTME: seed the 13 imported data slots with guest-valid objects/values before title entry.",
            "// PORTME: recover boot-reachable call order and exact argument/result/error semantics before classifying any import as optional.",
        ],
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with args.tsv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)
    print(
        "APF_STATIC_IMPORT_SURFACE_COMPLETE "
        f"logical={len(rows)} callable={len(callable_rows)} data={len(data_items)} "
        f"called={len(calls)} sites={sum(calls.values())} runtime=no"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, SurfaceError) as exc:
        raise SystemExit(f"error: {exc}") from exc

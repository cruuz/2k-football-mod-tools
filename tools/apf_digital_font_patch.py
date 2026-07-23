#!/usr/bin/env python3
"""Copy-only APF 2K8 global ``digital_font`` PNG writer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import apf_digital_font_transport as transport
import apf_inner
import apf_outer
import apf_texture_patch as archive_patch
import apf_xenos_dxt5a as dxt5a


SCHEMA = "apf_digital_font_patch/v1"


def build_patch(index_path: Path, png_path: Path) -> archive_patch.PatchResult:
    result = transport.build_patch(index_path, png_path)
    result.manifest["transport_schema"] = result.manifest["schema"]
    result.manifest["schema"] = SCHEMA
    result.manifest["family_target"] = {
        "outer_index": 1310,
        "outer_name": "global.iff",
        "inner_index": 246,
        "inner_name": "digital_font",
        "fixed_allocation": len(result.entry_bytes),
        "shared_global_ui_texture": True,
        "field_scorebug_only_proved": False,
        "runtime_visibility_proved": False,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="user-owned retail APF 0A")
    parser.add_argument("--png", required=True, type=Path, help="128x128 RGBA PNG; RGB must be white")
    parser.add_argument("--output-entry", type=Path, help="new rebuilt global.iff allocation")
    parser.add_argument("--output-volume", type=Path, help="new copied 0A volume")
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    reservation: archive_patch.OutputReservation | None = None
    manifest_path = args.manifest.expanduser()
    try:
        index_path = args.index.expanduser()
        png_path = args.png.expanduser()
        output_entry = args.output_entry.expanduser() if args.output_entry else None
        output_volume = args.output_volume.expanduser() if args.output_volume else None
        archive_patch._preflight_output_paths(  # type: ignore[attr-defined]
            [index_path, png_path],
            [
                ("manifest", manifest_path),
                ("output entry", output_entry),
                ("output volume", output_volume),
            ],
        )
        reservation = archive_patch._reserve_new(manifest_path)  # type: ignore[attr-defined]
        result = build_patch(index_path, png_path)
        document = result.manifest
        if output_entry is not None:
            archive_patch._write_new(output_entry, result.entry_bytes)  # type: ignore[attr-defined]
            document["output_entry"] = {
                "path": str(output_entry),
                "size": len(result.entry_bytes),
                "sha256": transport.sha256(result.entry_bytes),
            }
        if output_volume is not None:
            archive = apf_outer.parse_archive(index_path)
            document["copied_volume"] = archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                index_path, output_volume, archive.entries[1310], result.entry_bytes
            )
        archive_patch._commit_reserved(  # type: ignore[attr-defined]
            manifest_path,
            reservation,
            (json.dumps(document, indent=2) + "\n").encode("utf-8"),
        )
        archive_patch._close_reserved(reservation)  # type: ignore[attr-defined]
        reservation = None
        print(
            "APF_DIGITAL_FONT_PATCH_PASS outer=1310 inner=246 "
            f"mode={document['mode']} entry_sha256={transport.sha256(result.entry_bytes)} "
            "runtime=false"
        )
    except (
        transport.FontTransportError,
        dxt5a.DXT5AError,
        archive_patch.PatchError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        OSError,
    ) as exc:
        if reservation is not None:
            archive_patch._abort_reserved(manifest_path, reservation)  # type: ignore[attr-defined]
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Independently verify a copied XISO made by the bounded bar-monitor writer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any

import nfl_crib_bar_monitor_png_xiso as writer
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_crib_bar_monitor_png_verify/v1"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


class VerificationError(ValueError):
    """The copied XISO, PNG provenance, preview, or manifest failed closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def open_regular(path: Path, label: str) -> tuple[Path, int, tuple[int, int]]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise VerificationError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    identity = common.fd_identity(descriptor)
    try:
        require(common.path_identity(resolved) == identity,
                f"{label} pathname identity changed")
    except Exception:
        os.close(descriptor)
        raise
    return resolved, descriptor, identity


def read_small(path: Path, label: str, limit: int) -> tuple[Path, bytes]:
    resolved, descriptor, identity = open_regular(path, label)
    try:
        size = os.fstat(descriptor).st_size
        require(0 < size <= limit, f"{label} size is outside the safe bound")
        payload = common.read_exact(descriptor, 0, size)
        require(common.path_identity(resolved) == identity,
                f"{label} pathname changed while reading")
        return resolved, payload
    finally:
        os.close(descriptor)


def verify(source_path: Path, output_path: Path, png_path: Path,
           preview_path: Path, manifest_path: Path) -> dict[str, Any]:
    source, source_fd, source_identity = open_regular(source_path, "source XISO")
    output, output_fd, output_identity = open_regular(output_path, "output XISO")
    try:
        require(source_identity != output_identity,
                "output XISO aliases the source inode")
        source_entries, source_directory, _pack = writer.validate_xiso_source(source_fd)
        require(os.fstat(output_fd).st_size == common.EXPECTED_XISO_SIZE,
                "output XISO size changed")
        output_entries, output_directory = common.parse_xdvdfs(
            output_fd, common.EXPECTED_XISO_SIZE
        )
        require(output_entries == source_entries and
                output_directory == source_directory,
                "output XISO filesystem tree/layout differs from source")

        png, png_payload, rgba = writer.read_png(png_path)
        source_span = common.read_exact(source_fd, writer.SPAN_ABSOLUTE, writer.SPAN_SIZE)
        expected_span, expected_preview, compile_report = writer.compile_replacement(
            source_span, rgba
        )
        actual_span = common.read_exact(output_fd, writer.SPAN_ABSOLUTE, writer.SPAN_SIZE)
        require(actual_span == expected_span,
                "output XISO bar_monitor span differs from fresh PNG reconstruction")
        source_sha, output_sha, changed, changed_runs = writer.compare_images(
            source_fd, output_fd, common.EXPECTED_XISO_SIZE,
            writer.SPAN_ABSOLUTE, expected_span,
        )
        require(source_sha == common.EXPECTED_XISO_SHA256,
                "source XISO changed during independent verification")
        xbe = output_entries["default.xbe"]
        require(common.sha256_fd(output_fd, xbe.byte_offset, xbe.size) ==
                common.EXPECTED_XBE_SHA256,
                "output XISO default.xbe differs from retail")

        preview, preview_payload = read_small(
            preview_path, "replacement preview", writer.MAX_PNG_BYTES
        )
        require(preview_payload == expected_preview,
                "preview PNG differs from fresh replacement decode")
        manifest, manifest_payload = read_small(
            manifest_path, "writer manifest", MAX_MANIFEST_BYTES
        )
        value = json.loads(manifest_payload)
        require(value.get("schema") == writer.SCHEMA,
                "writer manifest schema changed")
        require(
            value.get("target", {}).get("selector") == writer.SELECTOR
            and value.get("target", {}).get("asset_id") == writer.ASSET_ID,
            "writer manifest target changed",
        )
        require(
            value.get("input_png", {}).get("sha256") == sha256(png_payload)
            and value.get("input_png", {}).get("rgba_sha256") == sha256(rgba),
            "writer manifest PNG provenance changed",
        )
        require(
            value.get("compile", {}).get("replacement_span", {}).get("sha256")
            == sha256(expected_span)
            and value.get("compile", {}).get("decoded", {}).get("sha256")
            == compile_report["decoded"]["sha256"],
            "writer manifest compiled-span provenance changed",
        )
        require(
            value.get("output", {}).get("sha256") == output_sha
            and value.get("output", {}).get("changed_byte_count") == changed
            and value.get("output", {}).get("changed_run_count") == changed_runs,
            "writer manifest copied-XISO ledger changed",
        )
        require(
            value.get("preview", {}).get("sha256") == sha256(preview_payload)
            and value.get("safety", {}).get("manifest_contains_retail_bytes") is False
            and value.get("safety", {}).get("public_tool_contains_retail_bytes") is False,
            "writer manifest preview/public-data safety claim changed",
        )
        require(common.path_identity(source) == source_identity and
                common.path_identity(output) == output_identity,
                "source/output pathname changed during independent verification")

        return {
            "schema": SCHEMA,
            "selector": writer.SELECTOR,
            "source": {
                "path": str(source),
                "sha256": source_sha,
                "opened_read_only": True,
                "modified": False,
            },
            "output": {
                "path": str(output),
                "sha256": output_sha,
                "size": common.EXPECTED_XISO_SIZE,
                "changed_byte_count": changed,
                "changed_run_count": changed_runs,
                "all_differences_inside_selected_fixed_span": True,
                "xdvdfs_tree_and_layout_identical": True,
                "default_xbe_identical": True,
            },
            "png": {"path": str(png), "sha256": sha256(png_payload)},
            "preview": {"path": str(preview), "sha256": sha256(preview_payload)},
            "manifest": {"path": str(manifest), "sha256": sha256(manifest_payload)},
            "fresh_reconstruction_equal": True,
            "opaque_tail_preserved": True,
            "runtime_visibility_proved": False,
        }
    finally:
        os.close(output_fd)
        os.close(source_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--preview", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = verify(
            args.source_xiso, args.output_xiso, args.png,
            args.preview, args.manifest,
        )
    except (OSError, ValueError, KeyError, TypeError, struct.error,
            json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SCHEMA", "VerificationError", "verify"]

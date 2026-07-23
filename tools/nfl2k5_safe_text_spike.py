#!/usr/bin/env python3
"""Audit or transport one bounded NFL 2K5 STRG/SITU text replacement.

``audit`` emits only counts and capability claims.  ``smoke-copy`` creates an
exact-layout XISO copy, applies one user-authored fixed-allocation string,
and compares every image byte.  The source is opened read-only and a failed
run publishes neither an output nor a receipt.

This tool contains no decoded retail strings.  It requires a user's own
recognized USA Xbox XISO and the private cache derived from that XISO.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.nfl2k5_safe_text_banks import SafeTextCatalog  # noqa: E402
import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402


SMOKE_SCHEMA = "2k5_mod_studio_safe_text_transport_smoke/v1"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_atomic_json(path: Path, value: object) -> None:
    parent = path.expanduser().parent.resolve(strict=True)
    target = parent / path.name
    if target.exists():
        raise ValidationError(f"Output already exists: {target}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.tmp-", dir=parent
    )
    temporary = Path(temporary_name)
    success = False
    try:
        payload = _json_bytes(value)
        written = 0
        while written < len(payload):
            amount = os.write(descriptor, payload[written:])
            if amount <= 0:
                raise ValidationError("Short audit write")
            written += amount
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target)
        success = True
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not success and temporary.exists():
            temporary.unlink()


def audit(pack0: Path, inventory: Path, output: Path | None) -> dict[str, object]:
    result = SafeTextCatalog.from_paths(pack0, inventory).audit_document()
    if output is not None:
        _write_atomic_json(output, result)
    return result


def _temporary_owned_file(final: Path) -> xiso.OwnedFile:
    parent = final.expanduser().parent.resolve(strict=True)
    if final.exists():
        raise ValidationError(f"Output already exists: {final}")
    descriptor, name = tempfile.mkstemp(prefix=f".{final.name}.building-", dir=parent)
    return xiso.OwnedFile(Path(name), descriptor, xiso.fd_identity(descriptor))


def smoke_copy(
    *,
    source_xiso: Path,
    pack0: Path,
    inventory: Path,
    selector: str,
    text: str,
    output_xiso: Path,
    receipt: Path,
) -> dict[str, object]:
    catalog = SafeTextCatalog.from_paths(pack0, inventory)
    replacement = catalog.resolve_edit(selector, text)
    source = source_xiso.expanduser().resolve(strict=True)
    output = output_xiso.expanduser().parent.resolve(strict=True) / output_xiso.name
    receipt_path = receipt.expanduser().parent.resolve(strict=True) / receipt.name
    if output == source or receipt_path in {source, output}:
        raise ValidationError("Source, output, and receipt paths must be distinct")
    if output.exists() or receipt_path.exists():
        raise ValidationError("Smoke output and receipt must not already exist")
    supplied_info = source_xiso.expanduser().lstat()
    if stat.S_ISLNK(supplied_info.st_mode):
        raise ValidationError("Source XISO must not be a symbolic link")

    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    temporary: xiso.OwnedFile | None = None
    output_published = False
    success = False
    try:
        source_info = os.fstat(source_fd)
        xiso.require(stat.S_ISREG(source_info.st_mode), "source is not a regular file")
        xiso.require(
            source_info.st_size == xiso.EXPECTED_XISO_SIZE,
            "retail XISO size mismatch",
        )
        source_identity = xiso.fd_identity(source_fd)
        xiso.require(xiso.path_identity(source) == source_identity, "source pathname changed")
        source_sha_before = xiso.sha256_fd(source_fd)
        xiso.require(
            source_sha_before == xiso.EXPECTED_XISO_SHA256,
            "retail XISO SHA-256 mismatch",
        )
        entries, directory = xiso.parse_xdvdfs(source_fd, source_info.st_size)
        xiso_entry = entries.get(f"vc_53450030/{replacement.pack_name}".casefold())
        xiso.require(xiso_entry is not None, "target archive pack is missing from XISO")
        pack = catalog.pack0.parent / replacement.pack_name
        xiso.require(
            xiso_entry.size == pack.stat().st_size,
            "private cache and XISO pack sizes disagree",
        )
        cache_pack_sha = _sha256_path(pack)
        source_pack_sha = xiso.sha256_fd(
            source_fd, xiso_entry.byte_offset, xiso_entry.size
        )
        xiso.require(cache_pack_sha == source_pack_sha, "private cache is not from this XISO")

        absolute = xiso_entry.byte_offset + replacement.pack_offset
        before = xiso.read_exact(source_fd, absolute, replacement.size)
        xiso.require(
            hashlib.sha256(before).hexdigest() == replacement.preimage_sha256,
            "XISO text allocation does not match the proved preimage",
        )
        changed_relative = {
            index
            for index, (old, new) in enumerate(zip(before, replacement.replacement))
            if old != new
        }
        xiso.require(changed_relative, "replacement would not change any XISO bytes")
        allowed = {absolute + index for index in changed_relative}

        temporary = _temporary_owned_file(output)
        xiso.require(
            xiso.fd_identity(temporary.descriptor) != source_identity,
            "temporary output aliases the source inode",
        )
        copy_method = xiso.copy_fd_exact(
            source_fd, temporary.descriptor, source_info.st_size
        )
        xiso.require(xiso.owned_path_matches(temporary), "temporary output changed")
        written = os.pwrite(temporary.descriptor, replacement.replacement, absolute)
        xiso.require(written == replacement.size, "short fixed-text patch write")
        xiso.require(
            xiso.read_exact(temporary.descriptor, absolute, replacement.size)
            == replacement.replacement,
            "fixed-text patch readback mismatch",
        )
        os.fsync(temporary.descriptor)

        source_sha_after, output_sha, differences = xiso.compare_and_hash(
            source_fd, temporary.descriptor, source_info.st_size, allowed
        )
        xiso.require(source_sha_after == source_sha_before, "source XISO changed")
        output_entries, output_directory = xiso.parse_xdvdfs(
            temporary.descriptor, source_info.st_size
        )
        xiso.require(output_directory == directory, "XDVDFS directory metadata changed")
        xiso.require(output_entries == entries, "XDVDFS directory tree changed")

        result: dict[str, object] = {
            "schema": SMOKE_SCHEMA,
            "source": {
                "sha256_before": source_sha_before,
                "sha256_after": source_sha_after,
                "size": source_info.st_size,
                "opened_read_only": True,
                "modified": False,
            },
            "output": {
                "path": str(output),
                "sha256": output_sha,
                "size": source_info.st_size,
                "copy_method": copy_method,
            },
            "edit": {
                "selector": replacement.selector,
                "asset_id": replacement.asset_id,
                "replacement_text_sha256": hashlib.sha256(
                    text.encode("utf-8")
                ).hexdigest(),
                "allocation_bytes": replacement.size,
                "changed_byte_count": len(differences),
            },
            "verification": {
                "cache_pack_matches_xiso": True,
                "preimage_matches_private_catalog": True,
                "replacement_readback_matches": True,
                "all_other_xiso_bytes_identical": True,
                "xdvdfs_tree_identical": True,
                "source_unchanged": True,
                "retail_text_in_receipt": False,
                "raw_offsets_in_receipt": False,
            },
        }

        # Publish only after the complete comparison succeeds.  A later receipt
        # failure removes the published output again in the finally block.
        os.close(temporary.descriptor)
        temporary = xiso.OwnedFile(temporary.path, -1, temporary.identity)
        os.replace(temporary.path, output)
        output_published = True
        _write_atomic_json(receipt_path, result)
        success = True
        return result
    finally:
        os.close(source_fd)
        if temporary is not None and temporary.descriptor >= 0:
            os.close(temporary.descriptor)
        if not success:
            if temporary is not None and temporary.path.exists():
                temporary.path.unlink()
            if output_published and output.exists():
                output.unlink()
            if receipt_path.exists():
                receipt_path.unlink()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--pack0", required=True, type=Path)
    audit_parser.add_argument("--inventory", required=True, type=Path)
    audit_parser.add_argument("--output", type=Path)
    smoke_parser = subparsers.add_parser("smoke-copy")
    smoke_parser.add_argument("--source-xiso", required=True, type=Path)
    smoke_parser.add_argument("--pack0", required=True, type=Path)
    smoke_parser.add_argument("--inventory", required=True, type=Path)
    smoke_parser.add_argument("--selector", required=True)
    smoke_parser.add_argument("--text", required=True)
    smoke_parser.add_argument("--output-xiso", required=True, type=Path)
    smoke_parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            result = audit(args.pack0, args.inventory, args.output)
            summary: Any = result["proved_fixed_allocation_banks"]
        else:
            result = smoke_copy(
                source_xiso=args.source_xiso,
                pack0=args.pack0,
                inventory=args.inventory,
                selector=args.selector,
                text=args.text,
                output_xiso=args.output_xiso,
                receipt=args.receipt,
            )
            summary = {
                "output": result["output"]["path"],
                "changed_byte_count": result["edit"]["changed_byte_count"],
                "all_other_xiso_bytes_identical": True,
            }
    except (OSError, ValueError, ValidationError, xiso.PatchError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


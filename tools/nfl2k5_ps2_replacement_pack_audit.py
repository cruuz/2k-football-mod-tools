#!/usr/bin/env python3
"""Audit a PCSX2 NFL 2K5 replacement tree before any Xbox mapping claim.

PCSX2 replacement identity is a GS texture/CLUT hash, while the Xbox editor
addresses an authenticated archive package, TXTR/TSET resource, format and
fixed span. Image dimensions or a friendly folder name cannot bridge those
two identities. This scanner therefore inventories the supplied tree,
deduplicates exact files, recognizes canonical PCSX2 hash names, and reports
whether a source-owned mapping manifest exists. It never edits the pack.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
from typing import Any


SCHEMA = "nfl2k5_ps2_replacement_pack_audit/v1"
SERIAL = "SLUS-20919"
MAX_FILES = 100_000
MAX_DIRECTORIES = 100_000
MAX_FILE_BYTES = 64 * 1024 * 1024
PCSX2_HASH_NAME = re.compile(
    r"^[0-9a-f]{16}-[0-9a-f]{16}-[0-9a-f]{8}\.png$", re.ASCII
)
MAPPING_MANIFEST = "nfl2k5-xbox-map.v1.json"
MAPPING_SCHEMA = "nfl2k5_ps2_to_xbox_texture_map/v1"


class PackAuditError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackAuditError(message)


def _png_header(path: Path) -> tuple[int, int, int, int]:
    with path.open("rb") as stream:
        head = stream.read(33)
    require(
        len(head) == 33
        and head[:8] == b"\x89PNG\r\n\x1a\n"
        and head[12:16] == b"IHDR",
        f"PNG header is malformed: {path}",
    )
    width, height, bit_depth, color_type = struct.unpack_from(">IIBB", head, 16)
    require(0 < width <= 16_384 and 0 < height <= 16_384,
            f"PNG dimensions are outside the safe bound: {path}")
    return width, height, bit_depth, color_type


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _walk(root: Path) -> tuple[list[Path], int]:
    files: list[Path] = []
    directory_count = 0
    pending = [root]
    while pending:
        current = pending.pop()
        directory_count += 1
        require(directory_count <= MAX_DIRECTORIES,
                "replacement tree exceeds the directory safety bound")
        try:
            children = sorted(os.scandir(current), key=lambda row: row.name.casefold())
        except OSError as exc:
            raise PackAuditError(f"cannot read replacement directory {current}: {exc}") from exc
        for child in children:
            try:
                info = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise PackAuditError(f"cannot inspect replacement entry {child.path}: {exc}") from exc
            require(not stat.S_ISLNK(info.st_mode),
                    f"replacement tree must not contain links: {child.path}")
            if stat.S_ISDIR(info.st_mode):
                pending.append(Path(child.path))
            elif stat.S_ISREG(info.st_mode):
                require(0 < info.st_size <= MAX_FILE_BYTES,
                        f"replacement file size is outside the safe bound: {child.path}")
                files.append(Path(child.path))
                require(len(files) <= MAX_FILES,
                        "replacement tree exceeds the file safety bound")
            else:
                raise PackAuditError(
                    f"replacement tree contains a non-file entry: {child.path}"
                )
    return sorted(files, key=lambda path: path.relative_to(root).as_posix().casefold()), directory_count


def _mapping_manifest(root: Path) -> tuple[bool, int, str]:
    path = root / MAPPING_MANIFEST
    if not path.exists():
        return False, 0, ""
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            "Xbox mapping manifest must be a regular non-link file")
    require(info.st_size <= 8 * 1024 * 1024,
            "Xbox mapping manifest exceeds the 8 MiB bound")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackAuditError(f"cannot read Xbox mapping manifest: {exc}") from exc
    entries = document.get("entries") if isinstance(document, dict) else None
    require(
        isinstance(document, dict)
        and document.get("schema") == MAPPING_SCHEMA
        and isinstance(entries, list),
        f"Xbox mapping manifest schema must be {MAPPING_SCHEMA}",
    )
    for number, row in enumerate(entries):
        require(
            isinstance(row, dict)
            and set(row) == {"pcsx2_png", "xbox_asset_id"}
            and isinstance(row["pcsx2_png"], str)
            and isinstance(row["xbox_asset_id"], str)
            and row["pcsx2_png"]
            and row["xbox_asset_id"].startswith(("p8:", "tset:", "nfl2k5.")),
            f"Xbox mapping manifest entry {number} is invalid",
        )
    return True, len(entries), _sha256(path)


def audit(root: Path) -> dict[str, Any]:
    requested = root.expanduser().resolve(strict=True)
    info = requested.lstat()
    require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            "replacement-pack root must be a regular non-link directory")
    files, directory_count = _walk(requested)
    png_rows: list[dict[str, Any]] = []
    suffixes: Counter[str] = Counter()
    hashes: dict[str, list[str]] = defaultdict(list)
    for path in files:
        relative = path.relative_to(requested).as_posix()
        suffixes[path.suffix.lower() or "<none>"] += 1
        if path.suffix.lower() != ".png":
            continue
        width, height, bit_depth, color_type = _png_header(path)
        digest = _sha256(path)
        hashes[digest].append(relative)
        png_rows.append({
            "bit_depth": bit_depth,
            "color_type": color_type,
            "height": height,
            "path": relative,
            "pcsx2_hash_filename": PCSX2_HASH_NAME.fullmatch(path.name.lower()) is not None,
            "sha256": digest,
            "width": width,
        })
    manifest_present, mapping_entries, mapping_sha256 = _mapping_manifest(requested)
    canonical = sum(row["pcsx2_hash_filename"] is True for row in png_rows)
    blockers: list[str] = []
    if not png_rows:
        blockers.append("no PNG replacement files were supplied")
    if canonical == 0:
        blockers.append("no canonical PCSX2 GS texture/CLUT hash filenames were supplied")
    if not manifest_present:
        blockers.append(
            "no source-owned PCSX2-to-Xbox asset mapping manifest was supplied"
        )
    if manifest_present and mapping_entries == 0:
        blockers.append("the source-owned mapping manifest has no entries")
    return {
        "schema": SCHEMA,
        "root_name": requested.name,
        "serial_directory_present": any(
            SERIAL.casefold() in part.casefold()
            for row in png_rows for part in Path(row["path"]).parts
        ),
        "summary": {
            "canonical_pcsx2_hash_png_count": canonical,
            "directory_count": directory_count,
            "file_count": len(files),
            "mapping_entry_count": mapping_entries,
            "png_count": len(png_rows),
            "unique_png_payload_count": len(hashes),
        },
        "suffix_counts": dict(sorted(suffixes.items())),
        "mapping_manifest": {
            "file": MAPPING_MANIFEST,
            "present": manifest_present,
            "sha256": mapping_sha256,
        },
        "xbox_mapping_ready": not blockers,
        "blocking_reasons": blockers,
        "duplicate_payload_groups": [
            {"sha256": digest, "paths": paths}
            for digest, paths in sorted(hashes.items()) if len(paths) > 1
        ],
        "pngs": png_rows,
        "contract": {
            "identity_boundary": (
                "PCSX2 GS texture/CLUT hashes do not identify an Xbox archive "
                "package, resource selector, format, or fixed byte span"
            ),
            "mutation": "read-only audit; no file in the supplied tree is changed",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    try:
        report = audit(args.root)
    except (OSError, PackAuditError) as exc:
        print(f"nfl2k5_ps2_replacement_pack_audit: {exc}", file=os.sys.stderr)
        return 2
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json is not None:
        args.json.write_text(payload, encoding="utf-8", newline="\n")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

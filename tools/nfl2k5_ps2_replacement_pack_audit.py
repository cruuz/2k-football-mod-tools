#!/usr/bin/env python3
"""Audit a PCSX2 NFL 2K5 replacement tree before any Xbox mapping claim.

PCSX2 replacement identity is a GS texture/CLUT hash, while the Xbox editor
addresses an authenticated archive package, TXTR/TSET resource, format and
fixed span. Image dimensions or a friendly folder name cannot bridge those
two identities. This scanner therefore inventories the supplied tree,
deduplicates exact files, recognizes canonical PCSX2 hash names, and reports
whether a source-owned mapping manifest exists. It never edits the pack.

**Retail-free.** The audit reads a PNG's 33-byte IHDR for geometry and hashes
files whole, but it never decodes, copies, re-encodes or emits a single game
pixel. The report carries names, sizes, dimensions and digests only. That is
the property that lets this run against a pack nobody may redistribute.

What a real 23,010-PNG pack forced this scanner to learn:

*Names.* PCSX2 emits six replacement shapes, each optionally mip-suffixed,
and its 64-bit fields print through ``%llx``, which is **not** zero padded.
Demanding a fixed 16 hex digits threw away 2,337 files whose hash merely
began with a zero nibble. See ``PCSX2_HASH_NAME``.

*Empty files.* 1,067 zero-byte ``.txt`` files in that pack are deliberate
donor-slot provenance markers -- the *filename* is the payload (``NFL 2k5
Original Player <team>- <name>``, ``UNK_<id>``). An empty file is content
here, not corruption, so ``_walk`` inventories it instead of aborting.

*Symlinks.* The root the caller names may be a symlink; symlinks *inside*
the tree may not. See ``_resolve_root`` for the policy and its reasoning.

*Encoding.* Pack-manager JSON is written by PowerShell's ``ConvertTo-Json``
and carries a UTF-8 BOM, which ``json.loads`` rejects as invalid whitespace.
Every JSON read here goes through ``_read_json_document``, which decodes with
``utf-8-sig``. Report *output* stays BOM-free.

Deliberately **not** relaxed:

* No pixel decode, copy or emission, ever -- widening the audit is not a
  reason to start reading image bodies.
* Symlinks below the root stay fatal. Resolving the root is a convenience
  for the caller's own path; following links found *during* the walk would
  let a pack escape the tree the caller consented to.
* File-size, file-count and directory-count bounds still apply. Empty is
  allowed; unbounded is not.
* A malformed PNG header is still fatal. Zero bytes is a marker, but a file
  that claims to be a PNG and is not is a broken pack.
* Names match case-sensitively. ``%llx`` emits lower case, so an upper-case
  name is not something PCSX2 wrote, even though ``sscanf`` would parse it.
* The identity boundary itself. A canonical name plus a duplicate-payload
  group is still not an Xbox asset id; only the source-owned manifest is.
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
import sys
from typing import Any


SCHEMA = "nfl2k5_ps2_replacement_pack_audit/v2"
SERIAL = "SLUS-20919"
MAX_FILES = 100_000
MAX_DIRECTORIES = 100_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024

# PCSX2 emits six replacement-name shapes, each optionally carrying a mip
# suffix. From GSTextureReplacements.cpp (the format strings at :35-40, the
# mip-suffixed dump names at :323-344):
#
#     plain            %llx-%08x
#     CLUT             %llx-%llx-%08x
#     region           %llx-r%ux%u-%08x
#     region + CLUT    %llx-%llx-r%ux%u-%08x
#     old region       %llx-r%llx-%08x
#     old region+CLUT  %llx-%llx-r%llx-%08x
#
# The 64-bit fields print with %llx, which is NOT zero padded, so a hash
# whose top nibble is zero prints fewer than 16 digits. Requiring a fixed
# width of 16 rejected 27.36% of a real 23,010-PNG pack; accepting 1..16
# rejects 17.20% and recovers 2,337 files, none of them false positives.
#
# The trailing %08x is the packed texture-property word and is always eight
# digits. The %u fields are u32 in principle, but they are GS region extents
# and mip levels -- five digits is far past anything the hardware can carry,
# and holding that bound keeps absurd names out.
_PCSX2_HASH64 = r"[0-9a-f]{1,16}"
_PCSX2_PROPS32 = r"[0-9a-f]{8}"
_PCSX2_DECIMAL = r"[0-9]{1,5}"
PCSX2_HASH_NAME = re.compile(
    rf"^{_PCSX2_HASH64}"
    rf"(?:-{_PCSX2_HASH64})?"
    rf"(?:-r(?:{_PCSX2_DECIMAL}x{_PCSX2_DECIMAL}|{_PCSX2_HASH64}))?"
    rf"-{_PCSX2_PROPS32}"
    rf"(?:-mip{_PCSX2_DECIMAL})?"
    # The hash digits stay case-sensitive -- %llx emits lower case, so an
    # upper-case hash is not something PCSX2 wrote. The *extension* is a
    # different matter: PCSX2 selects its loader with Strncasecmp, so it
    # loads ``.PNG`` happily, and 51 of one real 5,312-file pack are exactly
    # that -- lower-case canonical hashes with an upper-case extension.
    # Case-folding the whole name would have re-admitted upper-case hashes;
    # folding only the suffix keeps both properties.
    rf"\.(?i:png)$",
    re.ASCII,
)
MAPPING_MANIFEST = "nfl2k5-xbox-map.v1.json"
MAPPING_SCHEMA = "nfl2k5_ps2_to_xbox_texture_map/v1"
# Pack-manager sidecar. Not authored by us and not authoritative for
# anything; inventoried so the report says which mod set was staged.
MODS_MANIFEST = ".mods/mods.json"
# PowerShell's ConvertTo-Json writes a UTF-8 BOM. json.loads() sees U+FEFF as
# a stray character and fails, so every JSON read decodes with utf-8-sig.
JSON_READ_ENCODING = "utf-8-sig"


class PackAuditError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackAuditError(message)


def _png_header(path: Path) -> tuple[int, int, int, int]:
    """Read geometry from the IHDR alone. No pixel data is ever decoded."""
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


def _read_json_document(path: Path, label: str) -> Any:
    """Read one JSON sidecar, tolerating a UTF-8 BOM but nothing else.

    Pack-manager sidecars come out of PowerShell's ``ConvertTo-Json``, which
    prefixes U+FEFF. ``json.loads`` treats that as an invalid character, so a
    plain ``utf-8`` read fails on a perfectly good file. Decoding as
    ``utf-8-sig`` strips a leading BOM and is a no-op otherwise.

    Still refused: a link, a non-regular file, anything over
    ``MAX_JSON_BYTES``, and any text that is not valid UTF-8 or not valid
    JSON. Tolerating a BOM is an encoding fix, not a parsing amnesty.
    """
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a regular non-link file")
    require(info.st_size <= MAX_JSON_BYTES,
            f"{label} exceeds the {MAX_JSON_BYTES // (1024 * 1024)} MiB bound")
    try:
        return json.loads(path.read_text(encoding=JSON_READ_ENCODING))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackAuditError(f"cannot read {label}: {exc}") from exc


def _resolve_root(root: Path) -> tuple[Path, Path]:
    """Resolve the caller's root once, and say so in the report.

    A replacement directory is very often a symlink: PenguinScreen2 points
    ``.../PenguinScreen2/textures/SLUS-20919/replacements`` at the PCSX2
    pack rather than duplicating 23,010 files. Refusing that path would
    refuse the normal installation.

    So the root -- and only the root -- may be a link. It is resolved once,
    and both the path the caller gave and the path actually walked go into
    the report, because "which bytes did you audit" must not be ambiguous
    when the two differ.

    Symlinks encountered *below* the root stay fatal (see ``_walk``). The
    caller consented to one tree; a link discovered mid-walk can point
    anywhere, could re-enter the tree and loop, and would let the same file
    be inventoried under two identities. Resolving one path the caller typed
    is a convenience; following arbitrary links found inside the data is a
    different and much larger promise.
    """
    given = Path(os.path.abspath(str(Path(root).expanduser())))
    try:
        resolved = given.resolve(strict=True)
    except OSError as exc:
        raise PackAuditError(f"cannot resolve replacement-pack root {given}: {exc}") from exc
    try:
        info = os.stat(resolved)
    except OSError as exc:
        raise PackAuditError(f"cannot inspect replacement-pack root {resolved}: {exc}") from exc
    require(stat.S_ISDIR(info.st_mode),
            f"replacement-pack root must be a directory: {resolved}")
    return given, resolved


def _walk(root: Path) -> tuple[list[tuple[Path, int]], int]:
    """Inventory every regular file under ``root`` as ``(path, size)``.

    Zero-byte files are kept. A real pack uses 1,067 empty ``.txt`` files as
    donor-slot provenance markers whose filenames carry the information, so
    treating "empty" as corruption aborted the audit on the first one. The
    upper bound stays: empty is allowed, oversized is not.

    Symlinks below the root remain fatal -- see ``_resolve_root``.
    """
    files: list[tuple[Path, int]] = []
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
                require(info.st_size <= MAX_FILE_BYTES,
                        f"replacement file size is outside the safe bound: {child.path}")
                files.append((Path(child.path), info.st_size))
                require(len(files) <= MAX_FILES,
                        "replacement tree exceeds the file safety bound")
            else:
                raise PackAuditError(
                    f"replacement tree contains a non-file entry: {child.path}"
                )
    files.sort(key=lambda row: row[0].relative_to(root).as_posix().casefold())
    return files, directory_count


def _mapping_manifest(root: Path) -> tuple[bool, int, str]:
    path = root / MAPPING_MANIFEST
    if not path.exists():
        return False, 0, ""
    document = _read_json_document(path, "Xbox mapping manifest")
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


def _mods_manifest(root: Path) -> dict[str, Any]:
    """Inventory the pack-manager sidecar, if the tree carries one.

    This is somebody else's file and it is not authoritative for the Xbox
    identity question -- it only records which mod options a pack manager
    staged. It is read so the report can name them, and because it is the
    file that proved JSON here arrives BOM-first.
    """
    path = root / MODS_MANIFEST
    row: dict[str, Any] = {
        "file": MODS_MANIFEST,
        "present": False,
        "byte_order_mark": False,
        "category_count": 0,
        "option_count": 0,
        "sha256": "",
    }
    if not path.exists():
        return row
    # An unrecognised shape is NOT fatal. This sidecar belongs to whatever
    # pack manager the user happens to run, its schema is nobody's contract,
    # and the audit draws no conclusion from it. Aborting a 23,010-file audit
    # because a third party reorganised their own JSON would be refusing the
    # pack over a file we already declared non-authoritative. So: report that
    # it is present and unrecognised, and carry on.
    #
    # Still fatal, via _read_json_document: a link, a non-regular file, an
    # oversized one, or bytes that are not valid UTF-8/JSON at all. Those say
    # the tree is broken or hostile, not merely unfamiliar.
    row["present"] = True
    with path.open("rb") as stream:
        row["byte_order_mark"] = stream.read(3) == b"\xef\xbb\xbf"
    row["sha256"] = _sha256(path)
    document = _read_json_document(path, "pack-manager mods manifest")
    categories = document.get("categories") if isinstance(document, dict) else None
    if not isinstance(categories, list):
        row["recognised"] = False
        row["note"] = "no categories list; shape not recognised, ignored"
        return row
    option_count = 0
    for category in categories:
        if not isinstance(category, dict):
            row["recognised"] = False
            row["note"] = "a category entry is not an object; shape not recognised, ignored"
            return row
        options = category.get("options")
        if options is not None:
            if not isinstance(options, list):
                row["recognised"] = False
                row["note"] = "a category has a non-list options field; shape not recognised, ignored"
                return row
            option_count += len(options)
    row["recognised"] = True
    row["category_count"] = len(categories)
    row["option_count"] = option_count
    return row


def audit(root: Path) -> dict[str, Any]:
    given, resolved = _resolve_root(root)
    files, directory_count = _walk(resolved)
    png_rows: list[dict[str, Any]] = []
    empty_markers: list[str] = []
    suffixes: Counter[str] = Counter()
    hashes: dict[str, list[str]] = defaultdict(list)
    for path, size in files:
        relative = path.relative_to(resolved).as_posix()
        suffixes[path.suffix.lower() or "<none>"] += 1
        if size == 0:
            # A deliberate provenance marker: the filename is the content.
            empty_markers.append(relative)
            continue
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
            "pcsx2_hash_filename": PCSX2_HASH_NAME.fullmatch(path.name) is not None,
            "sha256": digest,
            "width": width,
        })
    manifest_present, mapping_entries, mapping_sha256 = _mapping_manifest(resolved)
    mods_manifest = _mods_manifest(resolved)
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
        "root_name": resolved.name,
        "root": {
            "given": given.as_posix(),
            "resolved": resolved.as_posix(),
            "given_is_symlink": given.is_symlink(),
            "resolved_differs": given != resolved,
        },
        "serial_directory_present": any(
            SERIAL.casefold() in part.casefold()
            for row in png_rows for part in Path(row["path"]).parts
        ),
        "summary": {
            "canonical_pcsx2_hash_png_count": canonical,
            "directory_count": directory_count,
            "empty_marker_count": len(empty_markers),
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
        "mods_manifest": mods_manifest,
        "xbox_mapping_ready": not blockers,
        "blocking_reasons": blockers,
        "duplicate_payload_groups": [
            {"sha256": digest, "paths": paths}
            for digest, paths in sorted(hashes.items()) if len(paths) > 1
        ],
        "empty_markers": empty_markers,
        "pngs": png_rows,
        "contract": {
            "identity_boundary": (
                "PCSX2 GS texture/CLUT hashes do not identify an Xbox archive "
                "package, resource selector, format, or fixed byte span"
            ),
            "empty_files": (
                "zero-byte files are inventoried as provenance markers, not "
                "treated as corruption; their filenames are the content"
            ),
            "symlinks": (
                "the supplied root may be a symlink and is resolved once; "
                "symlinks inside the tree are refused"
            ),
            "mutation": "read-only audit; no file in the supplied tree is changed",
            "retail_free": (
                "no game pixel is decoded, copied or emitted; the report "
                "carries names, sizes, dimensions and digests only"
            ),
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
        print(f"nfl2k5_ps2_replacement_pack_audit: {exc}", file=sys.stderr)
        return 2
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json is not None:
        # Not Path.write_text(newline=...): that keyword is 3.10+, and this
        # tool targets 3.9. The report is written UTF-8 without a BOM --
        # we tolerate one on the way in, we never emit one.
        with args.json.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

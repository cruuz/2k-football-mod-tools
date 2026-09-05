#!/usr/bin/env python3
"""Independently verify an exported PCSX2 replacement pack for NFL 2K5 PS2.

This is the evidence behind ``mod_editor/core/ps2_export_service.py``. Given an
exported pack, the mapping manifest, and optionally the project the pack was
exported from, it re-derives from the bytes alone that

  1. the folder holds exactly what the receipt claims -- every file is listed,
     every listed file exists, there are no extras, no links, and no directory
     other than ``textures/SLUS-20919/replacements/``;
  2. every filename is a canonical PCSX2 GS hash name **and** appears in the
     manifest under the ``xbox_asset_id`` the receipt claims for it, so a file
     cannot be attributed to an asset the map does not join it to;
  3. every PNG carries a valid IHDR and hashes to the digest the receipt
     recorded, so nothing was swapped or truncated after the export;
  4. the receipt's provenance block is the manifest's, key for key -- a pack
     whose filenames came from one disc and emulator convention cannot claim
     another's;
  5. **no receipt entry names a target the project does not mark edited.** This
     is the hard rule of the whole lane: an unedited texture in a pack is
     retail pixels leaving the disc. It needs the project as a third input;
     without one the verdict is downgraded to ``INCOMPLETE`` and says so,
     rather than passing silently.

**Nothing here is imported from the exporter.** A verifier that reuses the
writer's code cannot see a bug in the writer, because both sides would compute
the same wrong name, the same wrong digest, or the same wrong geometry and
agree with each other. So the PCSX2 filename grammar, the receipt and manifest
schemas, the replacement directory layout, the provenance key set, the PNG
header layout and the project archive's asset-key derivation are all restated
below rather than imported. If the exporter's copy and this one ever disagree,
that disagreement is the finding.

The receipt is an input to be checked, never evidence. Its claims are compared
against what the folder, the manifest and the project independently say; where
they differ, verification fails rather than adopting the receipt's version.

Every violation raises ``PackVerifyError`` naming the offending path, and the
CLI exits nonzero. Passing a pack that leaks an unedited texture would be the
worst possible outcome here, so every check is biased toward refusing.

Usage::

    nfl2k5_ps2_replacement_pack_verify.py --pack <folder> \\
        [--manifest <nfl2k5-xbox-map.v1.json>] [--project <file.2k5mod>]
    nfl2k5_ps2_replacement_pack_verify.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import zipfile


SCHEMA = "nfl2k5_ps2_replacement_pack_verify/v1"

# --------------------------------------------------------------------------
# Restated contract. Deliberately duplicated from the exporter's knowledge of
# its own output so the two can disagree; see the module docstring.
# --------------------------------------------------------------------------

SERIAL = "SLUS-20919"
REPLACEMENTS_PARTS = ("textures", SERIAL, "replacements")
REPLACEMENTS_POSIX = "/".join(REPLACEMENTS_PARTS)

RECEIPT_NAME = "nfl2k5-ps2-export-receipt.v1.json"
RECEIPT_SCHEMA = "nfl2k5_ps2_export_receipt/v1"
MAPPING_MANIFEST = "nfl2k5-xbox-map.v1.json"
MAPPING_SCHEMA = "nfl2k5_ps2_to_xbox_texture_map/v1"
PROVENANCE_KEYS = ("disc", "emulator", "method", "generated", "counts")

#: The files a pack may carry at its root. Anything else there is an extra.
ROOT_FILES = (RECEIPT_NAME, MAPPING_MANIFEST)

#: Every receipt file row must carry exactly these keys.
RECEIPT_FILE_KEYS = frozenset({
    "path", "pcsx2_png", "resampled_from", "sha256", "source_target",
    "xbox_asset_id",
})

# PCSX2 prints its 64-bit hash fields with %llx, which is NOT zero padded, so a
# hash whose leading nibble is zero prints fewer than 16 digits. The trailing
# %08x property word is always eight. Names stay case-sensitive because %llx
# emits lower case; only the extension is case-folded, because PCSX2 selects
# its loader with Strncasecmp and loads ``.PNG`` happily.
_HASH64 = r"[0-9a-f]{1,16}"
_PROPS32 = r"[0-9a-f]{8}"
_DECIMAL = r"[0-9]{1,5}"
PCSX2_HASH_NAME = re.compile(
    r"^" + _HASH64
    + r"(?:-" + _HASH64 + r")?"
    + r"(?:-r(?:" + _DECIMAL + r"x" + _DECIMAL + r"|" + _HASH64 + r"))?"
    + r"-" + _PROPS32
    + r"(?:-mip" + _DECIMAL + r")?"
    + r"\.(?i:png)$",
    re.ASCII,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JSON_READ_ENCODING = "utf-8-sig"

MAX_FILES = 100_000
MAX_DIRECTORIES = 1_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_PROJECT_BYTES = 2 * 1024 * 1024 * 1024

RESULT_PASS = "PASS"
RESULT_INCOMPLETE = "INCOMPLETE"


class PackVerifyError(AssertionError):
    """A verification contract was violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PackVerifyError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path, label: str):
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             f"{label} must be a regular non-link file: {path}")
    _require(info.st_size <= MAX_JSON_BYTES,
             f"{label} exceeds its safe size bound: {path}")
    try:
        # utf-8-sig: a JSON file that has been through a Windows pack manager
        # carries a BOM, which json.loads rejects as a stray character.
        return json.loads(path.read_text(encoding=JSON_READ_ENCODING))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise PackVerifyError(f"{label} is not readable JSON: {path}: {exc}") from exc


# --------------------------------------------------------------------------
# Independent PNG header decode. 33 bytes is the whole IHDR; no pixel in the
# pack is ever decoded, which is what lets this run against art nobody may
# redistribute.
# --------------------------------------------------------------------------

def png_geometry(payload: bytes, path: str):
    _require(
        len(payload) >= 33
        and payload[:8] == PNG_SIGNATURE
        and payload[12:16] == b"IHDR",
        f"PNG header is malformed: {path}",
    )
    width, height = struct.unpack_from(">II", payload, 16)
    _require(0 < width <= 16_384 and 0 < height <= 16_384,
             f"PNG dimensions are outside the safe bound: {path}")
    return int(width), int(height)


# --------------------------------------------------------------------------
# Independent walk of the pack.
# --------------------------------------------------------------------------

def _walk(root: Path):
    """Every regular file under ``root`` as a POSIX relative path -> size.

    Symlinks are fatal anywhere below the root. The caller consented to one
    tree; a link found mid-walk can point anywhere, and would let a file be
    counted under two identities.
    """

    files = {}
    directories = set()
    pending = [root]
    while pending:
        current = pending.pop()
        # relative_to() of the root itself is Path("."); the root is "".
        relative = current.relative_to(root).as_posix()
        directories.add("" if relative == "." else relative)
        _require(len(directories) <= MAX_DIRECTORIES,
                 f"the pack exceeds the directory safety bound: {root}")
        try:
            children = sorted(os.scandir(current), key=lambda row: row.name)
        except OSError as exc:
            raise PackVerifyError(f"cannot read pack directory {current}: {exc}") from exc
        for child in children:
            try:
                info = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise PackVerifyError(
                    f"cannot inspect pack entry {child.path}: {exc}"
                ) from exc
            _require(not stat.S_ISLNK(info.st_mode),
                     f"the pack must not contain links: {child.path}")
            if stat.S_ISDIR(info.st_mode):
                pending.append(Path(child.path))
            elif stat.S_ISREG(info.st_mode):
                _require(info.st_size <= MAX_FILE_BYTES,
                         f"pack file size is outside the safe bound: {child.path}")
                files[Path(child.path).relative_to(root).as_posix()] = info.st_size
                _require(len(files) <= MAX_FILES,
                         f"the pack exceeds the file safety bound: {root}")
            else:
                raise PackVerifyError(
                    f"the pack contains a non-file entry: {child.path}"
                )
    return files, directories


def _open_pack(pack: Path) -> Path:
    given = Path(os.path.abspath(os.fspath(Path(pack).expanduser())))
    _require(not given.is_symlink(),
             f"Refusing to verify through a symlink: {given}. Pass the real folder.")
    try:
        info = os.stat(given)
    except OSError as exc:
        raise PackVerifyError(f"cannot inspect the pack root {given}: {exc}") from exc
    _require(stat.S_ISDIR(info.st_mode), f"the pack root must be a directory: {given}")
    return given


# --------------------------------------------------------------------------
# Independent reads of the three inputs.
# --------------------------------------------------------------------------

def read_manifest(path: Path):
    """The mapping manifest, indexed ``xbox_asset_id -> {pcsx2_png}``."""

    document = _read_json(path, "The mapping manifest")
    _require(isinstance(document, dict) and document.get("schema") == MAPPING_SCHEMA,
             f"the mapping manifest schema must be {MAPPING_SCHEMA}: {path}")
    entries = document.get("entries")
    _require(isinstance(entries, list),
             f"the mapping manifest has no entry list: {path}")
    by_asset = {}
    for number, row in enumerate(entries):
        _require(
            isinstance(row, dict)
            and set(row) == {"pcsx2_png", "xbox_asset_id"}
            and isinstance(row["pcsx2_png"], str)
            and isinstance(row["xbox_asset_id"], str)
            and bool(row["pcsx2_png"])
            and row["xbox_asset_id"].startswith(("p8:", "tset:", "nfl2k5.")),
            f"mapping manifest entry {number} is invalid: {path}",
        )
        by_asset.setdefault(row["xbox_asset_id"], set()).add(row["pcsx2_png"])
    provenance = {key: document[key] for key in PROVENANCE_KEYS if key in document}
    return by_asset, provenance, document


def read_receipt(path: Path):
    document = _read_json(path, "The export receipt")
    _require(isinstance(document, dict) and document.get("schema") == RECEIPT_SCHEMA,
             f"the export receipt schema must be {RECEIPT_SCHEMA}: {path}")
    rows = document.get("files")
    _require(isinstance(rows, list), f"the export receipt has no file list: {path}")
    for number, row in enumerate(rows):
        _require(isinstance(row, dict) and set(row) == RECEIPT_FILE_KEYS,
                 f"receipt file row {number} has the wrong shape: {path}")
        for key in ("path", "pcsx2_png", "sha256", "source_target", "xbox_asset_id"):
            _require(isinstance(row[key], str) and bool(row[key]),
                     f"receipt file row {number} has an empty {key}: {path}")
        _require(
            row["resampled_from"] is None
            or (isinstance(row["resampled_from"], list)
                and len(row["resampled_from"]) == 2
                and all(isinstance(value, int) for value in row["resampled_from"])),
            f"receipt file row {number} has an invalid resampled_from: {path}",
        )
    skipped = document.get("skipped", [])
    _require(isinstance(skipped, list),
             f"the export receipt skipped list is not a list: {path}")
    provenance = document.get("provenance")
    _require(isinstance(provenance, dict),
             f"the export receipt carries no provenance block: {path}")
    return document, rows, provenance


def read_project_edited_ids(path: Path):
    """The asset ids a ``.2k5mod`` project marks edited.

    Read straight out of the archive with ``zipfile``: the project's own
    manifest lists one row per user-authored replacement. Nothing in the studio
    is imported to do it, so a bug in the studio's reader cannot make an
    unedited target look edited here.
    """

    archive_path = Path(path)
    info = archive_path.lstat()
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             f"the project must be a regular non-link file: {archive_path}")
    _require(info.st_size <= MAX_PROJECT_BYTES,
             f"the project exceeds its safe size bound: {archive_path}")
    edited = set()
    try:
        with zipfile.ZipFile(archive_path) as archive:
            try:
                payload = archive.read("manifest.json")
            except KeyError as exc:
                raise PackVerifyError(
                    f"the project has no manifest: {archive_path}"
                ) from exc
            document = json.loads(payload.decode("utf-8"))
            _require(isinstance(document, dict),
                     f"the project manifest is not an object: {archive_path}")
            edits = document.get("edits")
            _require(isinstance(edits, list),
                     f"the project manifest has no edit list: {archive_path}")
            for number, row in enumerate(edits, 1):
                _require(isinstance(row, dict) and isinstance(row.get("asset_id"), str)
                         and bool(row["asset_id"]),
                         f"project edit {number} has no asset id: {archive_path}")
                edited.add(row["asset_id"])
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        if isinstance(exc, PackVerifyError):
            raise
        raise PackVerifyError(
            f"the project cannot be read: {archive_path}: {exc}"
        ) from exc
    return edited


# --------------------------------------------------------------------------
# The verification itself.
# --------------------------------------------------------------------------

def verify(pack, manifest=None, project=None):
    """Verify one exported pack. Returns the report; raises on any violation."""

    root = _open_pack(Path(pack))

    receipt_path = root / RECEIPT_NAME
    _require(receipt_path.is_file() and not receipt_path.is_symlink(),
             f"the pack carries no export receipt: {receipt_path}")
    receipt, rows, receipt_provenance = read_receipt(receipt_path)

    if manifest is not None:
        manifest_path = Path(manifest)
    else:
        manifest_path = root / MAPPING_MANIFEST
        _require(
            manifest_path.is_file(),
            "no mapping manifest was supplied and the pack carries none: "
            f"{manifest_path}",
        )
    by_asset, manifest_provenance, _document = read_manifest(manifest_path)

    # ---- 1. the folder holds exactly what the receipt claims ----------------
    files, directories = _walk(root)
    allowed_directories = {""}
    for depth in range(1, len(REPLACEMENTS_PARTS) + 1):
        allowed_directories.add("/".join(REPLACEMENTS_PARTS[:depth]))
    for name in sorted(directories):
        _require(
            name in allowed_directories,
            f"the pack carries a directory outside {REPLACEMENTS_POSIX}/: "
            f"{root / name}",
        )

    claimed = {}
    for number, row in enumerate(rows):
        relative = row["path"]
        pure = PurePosixPath(relative)
        _require(
            not pure.is_absolute()
            and relative == pure.as_posix()
            and all(part not in {"", ".", ".."} for part in pure.parts),
            f"receipt row {number} names an unsafe path: {relative}",
        )
        _require(
            relative == REPLACEMENTS_POSIX + "/" + row["pcsx2_png"],
            f"receipt row {number} path does not sit in {REPLACEMENTS_POSIX}/ "
            f"under its own PCSX2 name: {relative}",
        )
        _require(relative not in claimed,
                 f"receipt row {number} repeats a path already claimed: {relative}")
        claimed[relative] = row
        _require(relative in files,
                 f"the receipt names a file the pack does not carry: {root / relative}")

    for relative in sorted(files):
        if relative in ROOT_FILES:
            continue
        _require(
            relative in claimed,
            f"the pack carries a file the receipt does not name: {root / relative}",
        )

    # ---- 2/3/4/5, per file -------------------------------------------------
    checked = 0
    resampled = 0
    for relative in sorted(claimed):
        row = claimed[relative]
        path = root / relative
        name = row["pcsx2_png"]

        # 2. canonical PCSX2 shape, and the manifest joins it to this asset.
        _require(PCSX2_HASH_NAME.fullmatch(name) is not None,
                 f"filename is not a canonical PCSX2 GS hash name: {path}")
        mapped = by_asset.get(row["xbox_asset_id"])
        _require(
            mapped is not None,
            f"the manifest carries no row for the Xbox asset this file claims "
            f"({row['xbox_asset_id']}): {path}",
        )
        _require(
            name in mapped,
            f"the manifest does not map {row['xbox_asset_id']} to this filename: "
            f"{path}",
        )

        # 3. a valid PNG whose bytes are the ones the receipt recorded.
        payload = path.read_bytes()
        png_geometry(payload, str(path))
        _require(
            _sha256_bytes(payload) == row["sha256"],
            f"file content does not match the digest the receipt recorded: {path}",
        )
        if row["resampled_from"] is not None:
            resampled += 1
        checked += 1

    # 4. provenance is the manifest's, key for key -- and, where the pack
    # carries its own copy of the manifest, that copy is the very file whose
    # digest the receipt recorded. A pack whose bundled map had been swapped
    # after export would otherwise still satisfy every other check.
    bundled = root / MAPPING_MANIFEST
    recorded = receipt.get("mapping_manifest")
    if bundled.is_file() and isinstance(recorded, dict):
        expected = recorded.get("sha256")
        if isinstance(expected, str) and expected:
            _require(
                _sha256_bytes(bundled.read_bytes()) == expected,
                "the manifest bundled with the pack is not the one the receipt "
                f"recorded a digest for: {bundled}",
            )
    _require(
        receipt_provenance == manifest_provenance,
        "the receipt's provenance is not the manifest's; this pack's filenames "
        "cannot be traced to the disc and emulator convention it claims.\n"
        f"  receipt:  {json.dumps(receipt_provenance, sort_keys=True)}\n"
        f"  manifest: {json.dumps(manifest_provenance, sort_keys=True)}",
    )

    # 5. no receipt entry names an unedited target.
    result = RESULT_PASS
    downgrade = ""
    edited_checked = 0
    if project is not None:
        edited = read_project_edited_ids(Path(project))
        for relative in sorted(claimed):
            row = claimed[relative]
            _require(
                row["source_target"] in edited,
                "the pack contains a texture for a target the project does not "
                f"mark edited ({row['source_target']}), which would be retail "
                f"pixels leaving the disc: {root / relative}",
            )
        edited_checked = len(claimed)
    else:
        result = RESULT_INCOMPLETE
        downgrade = (
            "no project was supplied, so the check that no exported file names "
            "an unedited target could not run. Re-run with --project <file."
            "2k5mod> for a full PASS."
        )

    report = {
        "schema": SCHEMA,
        "pack": root.as_posix(),
        "manifest": Path(manifest_path).as_posix(),
        "project": Path(project).as_posix() if project is not None else None,
        "files_checked": checked,
        "files_resampled": resampled,
        "edited_targets_checked": edited_checked,
        "skipped_recorded": len(receipt.get("skipped", [])),
        "mapping_entries": sum(len(value) for value in by_asset.values()),
        "checks": {
            "folder_matches_receipt": True,
            "names_canonical_and_mapped": True,
            "png_headers_and_digests": True,
            "provenance_matches_manifest": True,
            "bundled_manifest_matches_receipt": True,
            "no_unedited_target": project is not None,
        },
        "result": result,
    }
    if downgrade:
        report["downgraded"] = True
        report["downgrade_reason"] = downgrade
    return report


# --------------------------------------------------------------------------
# Self-test. Builds its own fixtures with the standard library only, so it
# needs no game data, no exporter and no Pillow.
# --------------------------------------------------------------------------

def _chunk(tag: bytes, payload: bytes) -> bytes:
    import zlib

    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def synthetic_png(width: int, height: int, value: int = 0x40) -> bytes:
    """A real, minimal, valid RGBA PNG. No game pixel is involved."""

    import zlib

    raw = b"".join(
        b"\x00" + bytes([value, value, value, 0xFF]) * width for _ in range(height)
    )
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def _write_json(path: Path, document) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def build_synthetic_pack(root: Path):
    """A correct pack, its manifest and its project. Returns their paths."""

    provenance = {
        "counts": {"entries": 2},
        "disc": {"serial": SERIAL, "boot_sha256": "0" * 64, "content_sha256": "1" * 64},
        "emulator": {
            "name": "PenguinScreen2",
            "commit": "0123456789abcdef",
            "hash_convention": "classic-tcc-bit14",
        },
        "generated": "2026-01-01T00:00:00Z",
        "method": "hop1/v5",
    }
    names = ("aaa1-bbb2-00006269.png", "aaa3-bbb4-00006269.png")
    asset = "p8:12:jersey00"
    manifest = dict(provenance)
    manifest["schema"] = MAPPING_SCHEMA
    manifest["entries"] = [
        {"pcsx2_png": names[0], "xbox_asset_id": asset},
        {"pcsx2_png": names[1], "xbox_asset_id": asset},
    ]
    manifest_path = root / "map" / MAPPING_MANIFEST
    _write_json(manifest_path, manifest)

    project_path = root / "fixture.2k5mod"
    with zipfile.ZipFile(project_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps({
            "schema": "2k5_mod_studio_project/v1",
            "game": "espn_nfl_2k5_xbox",
            "payload_policy": "user-replacements-only",
            "edits": [{
                "asset_id": asset,
                "file": "replacements/" + hashlib.sha256(
                    asset.encode("utf-8")).hexdigest() + ".png",
                "png_sha256": "0" * 64,
                "rgba_sha256": "0" * 64,
            }],
        }, indent=2, sort_keys=True))

    pack = root / "pack"
    replacements = pack.joinpath(*REPLACEMENTS_PARTS)
    replacements.mkdir(parents=True)
    payload = synthetic_png(512, 256)
    rows = []
    for name in names:
        (replacements / name).write_bytes(payload)
        rows.append({
            "path": REPLACEMENTS_POSIX + "/" + name,
            "pcsx2_png": name,
            "resampled_from": None,
            "sha256": _sha256_bytes(payload),
            "source_target": asset,
            "xbox_asset_id": asset,
        })
    _write_json(pack / MAPPING_MANIFEST, manifest)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "serial": SERIAL,
        "exported": "2026-01-01T00:00:00Z",
        "replacements_directory": REPLACEMENTS_POSIX,
        "mapping_manifest": {
            "file": MAPPING_MANIFEST,
            "sha256": _sha256_bytes((pack / MAPPING_MANIFEST).read_bytes()),
        },
        "counts": {"files": 2, "resampled": 0, "skipped": 0, "targets": 1},
        "files": rows,
        "skipped": [],
        "provenance": provenance,
    }
    _write_json(pack / RECEIPT_NAME, receipt)
    return pack, manifest_path, project_path


def selftest(tmp=None) -> int:
    """Prove the checks accept a correct pack and reject the ways it can rot.

    The control case matters as much as the rejections: a verifier that simply
    always raised would satisfy every ``rejected`` case below and be worthless.
    """

    import shutil
    import tempfile

    room = Path(tmp) if tmp is not None else Path(tempfile.mkdtemp(prefix="ps2pack-"))
    try:
        base = room / "good"
        base.mkdir(parents=True)
        pack, manifest, project = build_synthetic_pack(base)

        report = verify(pack, manifest, project)
        assert report["result"] == RESULT_PASS, report
        assert report["files_checked"] == 2, report
        assert report["edited_targets_checked"] == 2, report

        without = verify(pack, manifest)
        assert without["result"] == RESULT_INCOMPLETE, without
        assert without["downgraded"] is True, without
        assert without["checks"]["no_unedited_target"] is False, without

        def rejected(name, mutate, why):
            room_case = room / name
            room_case.mkdir(parents=True)
            shutil.copytree(base, room_case / "case")
            case_pack = room_case / "case" / "pack"
            case_manifest = room_case / "case" / "map" / MAPPING_MANIFEST
            case_project = room_case / "case" / "fixture.2k5mod"
            mutate(case_pack, case_manifest, case_project)
            try:
                verify(case_pack, case_manifest, case_project)
            except PackVerifyError:
                return
            raise AssertionError(f"{why} must fail verification")

        def flip_a_byte(case_pack, _manifest, _project):
            victim = case_pack.joinpath(*REPLACEMENTS_PARTS, "aaa1-bbb2-00006269.png")
            blob = bytearray(victim.read_bytes())
            blob[-8] ^= 0xFF
            victim.write_bytes(bytes(blob))

        def add_an_extra(case_pack, _manifest, _project):
            case_pack.joinpath(
                *REPLACEMENTS_PARTS, "cccc-dddd-00006269.png"
            ).write_bytes(synthetic_png(8, 8))

        def forge_an_unedited_target(case_pack, _manifest, _project):
            path = case_pack / RECEIPT_NAME
            document = json.loads(path.read_text(encoding="utf-8"))
            document["files"][0]["source_target"] = "p8:99:never_edited"
            document["files"][0]["xbox_asset_id"] = "p8:99:never_edited"
            _write_json(path, document)

        def forge_the_mapping(case_pack, _manifest, _project):
            path = case_pack / RECEIPT_NAME
            document = json.loads(path.read_text(encoding="utf-8"))
            document["files"][0]["pcsx2_png"] = "9999-8888-00006269.png"
            document["files"][0]["path"] = (
                REPLACEMENTS_POSIX + "/9999-8888-00006269.png"
            )
            _write_json(path, document)

        def drop_a_file(case_pack, _manifest, _project):
            case_pack.joinpath(
                *REPLACEMENTS_PARTS, "aaa3-bbb4-00006269.png"
            ).unlink()

        def rewrite_the_provenance(case_pack, _manifest, _project):
            path = case_pack / RECEIPT_NAME
            document = json.loads(path.read_text(encoding="utf-8"))
            document["provenance"]["emulator"]["commit"] = "ffffffffffffffff"
            _write_json(path, document)

        def add_a_stray_directory(case_pack, _manifest, _project):
            stray = case_pack / "textures" / SERIAL / "dumps"
            stray.mkdir(parents=True)
            stray.joinpath("aaa1-bbb2-00006269.png").write_bytes(synthetic_png(4, 4))

        def uncanonical_name(case_pack, case_manifest, _project):
            old = "aaa1-bbb2-00006269.png"
            new = "NotAHash.png"
            case_pack.joinpath(*REPLACEMENTS_PARTS, old).rename(
                case_pack.joinpath(*REPLACEMENTS_PARTS, new))
            for path in (case_pack / RECEIPT_NAME,):
                document = json.loads(path.read_text(encoding="utf-8"))
                document["files"][0]["pcsx2_png"] = new
                document["files"][0]["path"] = REPLACEMENTS_POSIX + "/" + new
                _write_json(path, document)
            for path in (case_manifest, case_pack / MAPPING_MANIFEST):
                document = json.loads(path.read_text(encoding="utf-8"))
                document["entries"][0]["pcsx2_png"] = new
                _write_json(path, document)

        # The second gate M1 requires: the audit tool must independently call
        # this same pack ready. Imported here, not at module scope, and behind
        # the sys.path guard the shipped-tool self-sufficiency rule requires --
        # the installed Windows runtime does not put tools/ on sys.path.
        if str(Path(__file__).resolve().parent) not in sys.path:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
        import nfl2k5_ps2_replacement_pack_audit as pack_audit

        audited = pack_audit.audit(pack)
        assert audited["xbox_mapping_ready"] is True, audited["blocking_reasons"]
        assert audited["serial_directory_present"] is True, audited
        assert audited["summary"]["canonical_pcsx2_hash_png_count"] == 2, audited

        rejected("mutated", flip_a_byte, "one changed output byte")
        rejected("extra", add_an_extra, "a file the receipt does not name")
        rejected("unedited", forge_an_unedited_target,
                 "a receipt entry naming an unedited target")
        rejected("unmapped", forge_the_mapping,
                 "a filename the manifest does not map to the claimed asset")
        rejected("missing", drop_a_file, "a receipt entry with no file")
        rejected("provenance", rewrite_the_provenance,
                 "provenance that is not the manifest's")
        rejected("stray_dir", add_a_stray_directory,
                 "a directory outside the replacements folder")
        def swap_the_bundled_manifest(case_pack, _manifest, _project):
            document = json.loads(
                (case_pack / MAPPING_MANIFEST).read_text(encoding="utf-8"))
            document["entries"].append(
                {"pcsx2_png": "dead-beef-00006269.png",
                 "xbox_asset_id": "p8:1:smuggled"})
            _write_json(case_pack / MAPPING_MANIFEST, document)

        rejected("uncanonical", uncanonical_name,
                 "a filename that is not a canonical PCSX2 hash name")
        rejected("swapped_map", swap_the_bundled_manifest,
                 "a bundled manifest swapped after export")
    finally:
        if tmp is None:
            shutil.rmtree(room, ignore_errors=True)

    print(
        "NFL2K5_PS2_REPLACEMENT_PACK_VERIFY_SELFTEST_PASS decoder=independent "
        "accepts=receipt-exact rejects=mutated-byte,extra-file,unedited-target,"
        "unmapped-name,missing-file,forged-provenance,stray-directory,"
        "uncanonical-name,swapped-bundled-map downgrades=no-project "
        "audit=xbox_mapping_ready"
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--pack", type=Path, help="the exported replacement pack folder")
    parser.add_argument(
        "--manifest", type=Path,
        help="the mapping manifest; defaults to the copy inside the pack",
    )
    parser.add_argument(
        "--project", type=Path,
        help="the .2k5mod the pack was exported from; without it the verdict is "
             "downgraded, because the unedited-target check cannot run",
    )
    parser.add_argument(
        "--require-project", action="store_true",
        help="treat a missing --project as a failure instead of a downgrade",
    )
    parser.add_argument(
        "--selftest", action="store_true",
        help="prove the checks against synthetic fixtures; no game data needed",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.pack:
        parser.error("--pack is required unless --selftest is given")
    if args.require_project and not args.project:
        parser.error("--require-project was given but --project was not")

    report = verify(args.pack, args.manifest, args.project)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["result"] != RESULT_PASS:
        print(
            "nfl2k5_ps2_replacement_pack_verify: verdict downgraded to "
            + report["result"] + " -- " + report.get("downgrade_reason", ""),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

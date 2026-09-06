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
  5. the receipt says which emulator the pack was exported for, and its
     instructions are that emulator's -- a pack telling a stock PCSX2 user to
     turn on a setting their build does not have, or telling a PenguinScreen2
     user nothing about Classic Texture Names, is wrong in the way that costs
     an evening;
  6. **no receipt entry names a target the pack's own author did not edit.**
     This is the hard rule of the whole lane: an unedited texture in a pack is
     retail pixels leaving the disc. It needs a third input, and *which* third
     input depends on where the pixels came from -- the receipt says so in
     ``origin``. An ``xbox-project`` pack is checked against the ``.2k5mod`` it
     was exported from; a ``disc-native-art`` pack, whose art was decoded from
     the user's own PS2 disc and edited there, is checked against the edits
     document written beside it. Without the one its origin calls for, the
     verdict is downgraded to ``INCOMPLETE`` and says so, rather than passing
     silently. Neither input is ever the receipt itself.

Emulator target
---------------

The filenames are the same for every emulator; what differs is which of them a
build looks *up*. PCSX2 v1.7.4034 began hashing only the clamped draw region
instead of the whole texture, so a pack named the original way -- as this one
is -- is not looked for on a texture the game draws clamped; PenguinScreen2's
Classic Texture Names restores the original hashing. (v1.7.5606 later dropped
the TCC flag from dumped names but ignores that bit when reading, so it never
broke loading.) The receipt therefore carries ``emulator_target`` and the
instructions that go with it, and this tool restates the settings each target
needs rather than importing them: a receipt with no target, an unknown one, or
instructions belonging to a different one is a failure.

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
    nfl2k5_ps2_replacement_pack_verify.py --pack <folder> \\
        --edits <uniform-art edits document>       # a disc-native pack
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

#: The emulator a pack says it is for, and what each one has to turn on.
#: Restated, not imported -- see the module docstring.
TARGET_PENGUINSCREEN2_CLASSIC = "penguinscreen2_classic"
TARGET_PCSX2_MODERN = "pcsx2_modern"
TARGET_PCSX2_LEGACY = "pcsx2_legacy"
EMULATOR_TARGETS = (
    TARGET_PENGUINSCREEN2_CLASSIC, TARGET_PCSX2_MODERN, TARGET_PCSX2_LEGACY,
)
#: Settings the instructions for a target must name...
TARGET_REQUIRED_SETTINGS = {
    TARGET_PENGUINSCREEN2_CLASSIC: ("ClassicTextureNames=true",
                                    "LoadTextureReplacements=true"),
    TARGET_PCSX2_MODERN: ("LoadTextureReplacements=true",),
    TARGET_PCSX2_LEGACY: ("LoadTextureReplacements=true",),
}
#: ...and settings they must not: a stock PCSX2 has no Classic Texture Names,
#: and a user told to turn it on will look for it until they give up.
TARGET_FORBIDDEN_SETTINGS = {
    TARGET_PENGUINSCREEN2_CLASSIC: (),
    TARGET_PCSX2_MODERN: ("ClassicTextureNames",),
    TARGET_PCSX2_LEGACY: ("ClassicTextureNames",),
}
#: What the steps for a target have to still say, so instructions cannot be
#: swapped between targets while keeping the settings list plausible.
TARGET_REQUIRED_INSTRUCTION_FACTS = {
    TARGET_PENGUINSCREEN2_CLASSIC: ("Classic Texture Names",),
    TARGET_PCSX2_MODERN: ("1.7.4034", "clamped"),
    TARGET_PCSX2_LEGACY: ("1.7.4034",),
}

#: Where a pack's pixels were authored, and therefore which third input can
#: prove that no file in it is an unedited texture. Restated, not imported.
ORIGIN_XBOX_PROJECT = "xbox-project"
ORIGIN_DISC_NATIVE_ART = "disc-native-art"
EXPORT_ORIGINS = (ORIGIN_XBOX_PROJECT, ORIGIN_DISC_NATIVE_ART)
#: A receipt written before origins existed is an Xbox-project export; that is
#: the only pack the exporter could produce then, so the default adds no pack.
DEFAULT_ORIGIN = ORIGIN_XBOX_PROJECT
#: What each origin's third input is called on the command line.
ORIGIN_INPUT_FLAG = {
    ORIGIN_XBOX_PROJECT: "--project <file.2k5mod>",
    ORIGIN_DISC_NATIVE_ART: "--edits <uniform-art edits document>",
}

#: The edits document a disc-native pack is checked against: the lane's own
#: record of which disc textures the user replaced, and with what.
EDITS_SCHEMA = "nfl2k5_ps2_uniform_art_edits/v1"

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

#: A lowercase hex SHA-256, the only digest shape any of these documents use.
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

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
    origin = document.get("origin", DEFAULT_ORIGIN)
    _require(
        origin in EXPORT_ORIGINS,
        "the export receipt claims an origin this tool does not know "
        "(origin must be one of " + ", ".join(EXPORT_ORIGINS) + f"): {path}",
    )
    target = document.get("emulator_target")
    _require(
        target in EMULATOR_TARGETS,
        "the export receipt does not say which emulator it was exported for "
        "(emulator_target must be one of " + ", ".join(EMULATOR_TARGETS)
        + f"): {path}",
    )
    instructions = document.get("instructions")
    _require(isinstance(instructions, dict),
             f"the export receipt carries no instructions block: {path}")
    settings = instructions.get("settings")
    lines = instructions.get("lines")
    for name, value in (("settings", settings), ("lines", lines)):
        _require(
            isinstance(value, list) and value
            and all(isinstance(row, str) and row.strip() for row in value),
            f"the receipt's instructions have no {name}: {path}",
        )
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


def read_edits_edited_ids(path: Path):
    """The asset ids a disc-native uniform-art edits document marks edited.

    The disc-native counterpart of :func:`read_project_edited_ids`: a plain JSON
    file the lane writes beside the pack, one row per texture the user replaced,
    each naming the disc target, the Xbox asset id the pack is attributed to and
    the digest of the PNG they supplied. Read here with ``json`` alone, so a bug
    in the lane cannot make an untouched texture look edited.
    """

    edits_path = Path(path)
    document = _read_json(edits_path, "The uniform-art edits document")
    _require(isinstance(document, dict) and document.get("schema") == EDITS_SCHEMA,
             f"the edits document schema must be {EDITS_SCHEMA}: {edits_path}")
    _require(document.get("origin") == ORIGIN_DISC_NATIVE_ART,
             "an edits document proves a disc-native pack; this one claims "
             f"origin {document.get('origin')!r}: {edits_path}")
    rows = document.get("edits")
    _require(isinstance(rows, list) and rows,
             f"the edits document lists no edits: {edits_path}")
    edited = set()
    for number, row in enumerate(rows, 1):
        _require(isinstance(row, dict), f"edit {number} is not an object: {edits_path}")
        for key in ("target", "xbox_asset_id", "png_sha256"):
            _require(isinstance(row.get(key), str) and bool(row[key]),
                     f"edit {number} has an empty {key}: {edits_path}")
        _require(_SHA256_RE.fullmatch(row["png_sha256"]) is not None,
                 f"edit {number} has no lowercase hex PNG digest: {edits_path}")
        edited.add(row["xbox_asset_id"])
    return edited


# --------------------------------------------------------------------------
# The verification itself.
# --------------------------------------------------------------------------

def verify(pack, manifest=None, project=None, edits=None):
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

    # 5. the instructions are the ones this emulator needs, and not another's.
    target = receipt["emulator_target"]
    settings = list(receipt["instructions"]["settings"])
    steps = "\n".join(receipt["instructions"]["lines"])
    for needed in TARGET_REQUIRED_SETTINGS[target]:
        _require(
            needed in settings,
            f"a pack for {target} must tell the user to turn on {needed}, and "
            f"its receipt does not: {receipt_path}",
        )
    for refused in TARGET_FORBIDDEN_SETTINGS[target]:
        _require(
            not any(refused in row for row in settings),
            f"a pack for {target} must not tell the user to turn on {refused}; "
            f"that build has no such setting: {receipt_path}",
        )
    for fact in TARGET_REQUIRED_INSTRUCTION_FACTS[target]:
        _require(
            fact in steps,
            f"the instructions in this receipt are not {target}'s: they never "
            f"mention {fact}: {receipt_path}",
        )

    # 6. no receipt entry names a target its author did not edit. Which third
    # input can say so is the receipt's origin, not the caller's choice: an
    # Xbox-project pack is held to its project and a disc-native pack to its
    # edits document, and neither substitutes for the other.
    origin = receipt.get("origin", DEFAULT_ORIGIN)
    result = RESULT_PASS
    downgrade = ""
    edited_checked = 0
    edited = None
    source_label = ""
    if origin == ORIGIN_XBOX_PROJECT and project is not None:
        edited = read_project_edited_ids(Path(project))
        source_label = "the project"
    elif origin == ORIGIN_DISC_NATIVE_ART and edits is not None:
        edited = read_edits_edited_ids(Path(edits))
        source_label = "the edits document"
    if edited is not None:
        for relative in sorted(claimed):
            row = claimed[relative]
            _require(
                row["source_target"] in edited,
                f"the pack contains a texture for a target {source_label} does "
                f"not mark edited ({row['source_target']}), which would be "
                f"retail pixels leaving the disc: {root / relative}",
            )
        edited_checked = len(claimed)
    else:
        result = RESULT_INCOMPLETE
        downgrade = (
            f"this pack's receipt says its art was authored from {origin}, and "
            f"no {ORIGIN_INPUT_FLAG[origin].split()[0]} was supplied, so the "
            "check that no exported file names an unedited target could not "
            f"run. Re-run with {ORIGIN_INPUT_FLAG[origin]} for a full PASS."
        )

    report = {
        "schema": SCHEMA,
        "pack": root.as_posix(),
        "manifest": Path(manifest_path).as_posix(),
        "project": Path(project).as_posix() if project is not None else None,
        "edits": Path(edits).as_posix() if edits is not None else None,
        "origin": origin,
        "emulator_target": target,
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
            "instructions_match_the_emulator_target": True,
            "no_unedited_target": edited is not None,
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
        "emulator_target": TARGET_PENGUINSCREEN2_CLASSIC,
        "instructions": {
            "settings": list(
                TARGET_REQUIRED_SETTINGS[TARGET_PENGUINSCREEN2_CLASSIC]),
            "lines": [
                "1. Copy the textures folder into PenguinScreen2.",
                "2. Turn on Classic Texture Names and texture replacement.",
            ],
        },
        "counts": {"files": 2, "resampled": 0, "skipped": 0, "targets": 1},
        "files": rows,
        "skipped": [],
        "provenance": provenance,
    }
    _write_json(pack / RECEIPT_NAME, receipt)
    return pack, manifest_path, project_path


def make_disc_native(pack: Path, edits_path: Path,
                     targets=("00H0:1:0:jersey00",)) -> None:
    """Turn a correct Xbox-origin pack into a correct disc-native one.

    Same folder, same names, same digests: only where the pixels were authored
    changes, and with it which third input is allowed to prove they were.
    """

    receipt_path = pack / RECEIPT_NAME
    document = json.loads(receipt_path.read_text(encoding="utf-8"))
    document["origin"] = ORIGIN_DISC_NATIVE_ART
    rows = []
    for number, row in enumerate(document["files"]):
        row["source_target"] = row["xbox_asset_id"]
        rows.append({
            "target": targets[number % len(targets)],
            "xbox_asset_id": row["xbox_asset_id"],
            "selector": "00H0",
            "texture": "jersey00",
            "png_sha256": row["sha256"],
            "size": [512, 256],
        })
    _write_json(receipt_path, document)
    _write_json(edits_path, {
        "schema": EDITS_SCHEMA,
        "serial": SERIAL,
        "origin": ORIGIN_DISC_NATIVE_ART,
        "source": "the operator's own disc image",
        "pack": pack.as_posix(),
        "emulator_target": document["emulator_target"],
        "edits": rows,
    })


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
        assert report["emulator_target"] == TARGET_PENGUINSCREEN2_CLASSIC, report

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

        def drop_the_emulator_target(case_pack, _manifest, _project):
            path = case_pack / RECEIPT_NAME
            document = json.loads(path.read_text(encoding="utf-8"))
            del document["emulator_target"]
            _write_json(path, document)

        def claim_an_unknown_emulator(case_pack, _manifest, _project):
            path = case_pack / RECEIPT_NAME
            document = json.loads(path.read_text(encoding="utf-8"))
            document["emulator_target"] = "dolphin"
            _write_json(path, document)

        def instructions_for_another_emulator(case_pack, _manifest, _project):
            """Say PCSX2 while carrying PenguinScreen2's settings."""

            path = case_pack / RECEIPT_NAME
            document = json.loads(path.read_text(encoding="utf-8"))
            document["emulator_target"] = TARGET_PCSX2_MODERN
            _write_json(path, document)

        def instructions_that_say_nothing(case_pack, _manifest, _project):
            path = case_pack / RECEIPT_NAME
            document = json.loads(path.read_text(encoding="utf-8"))
            document["instructions"]["lines"] = ["1. Copy the folder."]
            _write_json(path, document)

        # ---- the disc-native origin: same pack, a different third input ----
        native_room = room / "native"
        native_room.mkdir(parents=True)
        shutil.copytree(base, native_room / "case")
        native_pack = native_room / "case" / "pack"
        native_manifest = native_room / "case" / "map" / MAPPING_MANIFEST
        native_edits = native_room / "case" / "uniform-art-edits.json"
        make_disc_native(native_pack, native_edits)

        native = verify(native_pack, native_manifest, edits=native_edits)
        assert native["result"] == RESULT_PASS, native
        assert native["origin"] == ORIGIN_DISC_NATIVE_ART, native
        assert native["edited_targets_checked"] == 2, native

        bare = verify(native_pack, native_manifest)
        assert bare["result"] == RESULT_INCOMPLETE, bare
        assert "--edits" in bare["downgrade_reason"], bare

        # The project is not a substitute: a disc-native pack is not proved by
        # an Xbox project, and an Xbox pack is not proved by an edits document.
        crossed = verify(native_pack, native_manifest, project=project)
        assert crossed["result"] == RESULT_INCOMPLETE, crossed
        crossed_back = verify(pack, manifest, edits=native_edits)
        assert crossed_back["result"] == RESULT_INCOMPLETE, crossed_back
        assert "--project" in crossed_back["downgrade_reason"], crossed_back

        def native_rejected(name, mutate, why):
            case_room = room / ("native_" + name)
            case_room.mkdir(parents=True)
            shutil.copytree(native_room / "case", case_room / "case")
            case_pack = case_room / "case" / "pack"
            case_manifest = case_room / "case" / "map" / MAPPING_MANIFEST
            case_edits = case_room / "case" / "uniform-art-edits.json"
            mutate(case_pack, case_manifest, case_edits)
            try:
                verify(case_pack, case_manifest, edits=case_edits)
            except PackVerifyError:
                return
            raise AssertionError(f"{why} must fail verification")

        def forge_an_unedited_native_target(case_pack, _manifest, _edits):
            path = case_pack / RECEIPT_NAME
            document = json.loads(path.read_text(encoding="utf-8"))
            document["files"][0]["source_target"] = "p8:99:never_edited"
            _write_json(path, document)

        def empty_the_edits(_pack, _manifest, case_edits):
            document = json.loads(case_edits.read_text(encoding="utf-8"))
            document["edits"] = []
            _write_json(case_edits, document)

        def relabel_the_edits_origin(_pack, _manifest, case_edits):
            document = json.loads(case_edits.read_text(encoding="utf-8"))
            document["origin"] = ORIGIN_XBOX_PROJECT
            _write_json(case_edits, document)

        def claim_an_unknown_origin(case_pack, _manifest, _edits):
            path = case_pack / RECEIPT_NAME
            document = json.loads(path.read_text(encoding="utf-8"))
            document["origin"] = "somewhere-else"
            _write_json(path, document)

        native_rejected("unedited", forge_an_unedited_native_target,
                        "a receipt entry naming a target the edits document omits")
        native_rejected("empty_edits", empty_the_edits,
                        "an edits document that lists no edits")
        native_rejected("relabelled", relabel_the_edits_origin,
                        "an edits document that is not a disc-native one")
        native_rejected("unknown_origin", claim_an_unknown_origin,
                        "a receipt claiming an origin this tool does not know")
        native_rejected("mutated", flip_a_byte,
                        "one changed output byte in a disc-native pack")

        rejected("uncanonical", uncanonical_name,
                 "a filename that is not a canonical PCSX2 hash name")
        rejected("swapped_map", swap_the_bundled_manifest,
                 "a bundled manifest swapped after export")
        rejected("no_target", drop_the_emulator_target,
                 "a receipt that does not say which emulator it is for")
        rejected("unknown_target", claim_an_unknown_emulator,
                 "a receipt naming an emulator this tool does not know")
        rejected("crossed_target", instructions_for_another_emulator,
                 "instructions belonging to a different emulator")
        rejected("empty_instructions", instructions_that_say_nothing,
                 "instructions that never mention what the target needs")
    finally:
        if tmp is None:
            shutil.rmtree(room, ignore_errors=True)

    print(
        "NFL2K5_PS2_REPLACEMENT_PACK_VERIFY_SELFTEST_PASS decoder=independent "
        "accepts=receipt-exact "
        "targets=penguinscreen2_classic,pcsx2_modern,pcsx2_legacy "
        "rejects=mutated-byte,extra-file,unedited-target,"
        "unmapped-name,missing-file,forged-provenance,stray-directory,"
        "uncanonical-name,swapped-bundled-map,no-emulator-target,"
        "unknown-emulator-target,crossed-instructions,empty-instructions,"
        "unknown-origin,unedited-disc-native-target,empty-edits,"
        "relabelled-edits "
        "origins=xbox-project,disc-native-art "
        "downgrades=no-project,no-edits,crossed-origin-input "
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
        "--edits", type=Path,
        help="the uniform-art edits document a disc-native pack was written "
             "beside; the disc-native counterpart of --project",
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

    report = verify(args.pack, args.manifest, args.project, args.edits)
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

#!/usr/bin/env python3
"""Refuse undeclared, retail-derived, binary, or local-workspace release files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Iterable
import xml.etree.ElementTree as ET


MAX_RELEASE_FILE_BYTES = 8 * 1024 * 1024

# Product target catalogs are decoded metadata: selectors, dimensions, hashes,
# offsets, ownership labels, and constraints. They contain no compressed game
# spans, decoded pixels, audio, or other retail payload. ``reports/`` remains a
# forbidden root except for these exact size/hash/schema-pinned files.  The
# compact Crib catalog and sanitized product-inspection snapshots live with
# product data instead of ``reports/``, but are held to the same immutable
# contract so a release cannot silently acquire retail payloads.
REVIEWED_METADATA: dict[str, tuple[int, str, str]] = {
    "reports/assets/menu_state_trace.json": (
        39_938,
        "ecd93117a3a808a16697c23ae10e3225953bcb4dabda30afabdc5c02911974f1",
        "vc_menu_state_trace/v1",
    ),
    "reports/assets/nfl_main_menu_live_state.json": (
        18_483,
        "a5d4b64962fefb2e5dbee4768d120172c0642405df2a0137759e2bce3737b89a",
        "nfl2k5_main_menu_live_state/v1",
    ),
    "reports/assets/nfl2k5_p8_texture_inventory.json": (
        8_338_553,
        "01b030e9f7b58786a76ba23a66d59a485024e7001656b03d595991aec0c8cf3f",
        "nfl2k5_p8_texture_inventory/v1",
    ),
    "reports/assets/nfl2k5_jersey_tset_compatibility.json": (
        2_155_779,
        "046d03546242c11478d39b48d7f6f80b5f2009c85641b5c81abdaa6f8171cacd",
        "nfl2k5_jersey_tset_compatibility/v1",
    ),
    "reports/assets/nfl2k5_sleeve_tset_compatibility.json": (
        2_244_430,
        "72a25d908135322a6c15c1f19f2f575224ab224c8b8c4c6969f5b4ba2359ae2b",
        "nfl2k5_sleeve_tset_compatibility/v1",
    ),
    "reports/assets/nfl2k5_pants_tset_compatibility.json": (
        2_329_500,
        "cab15d4f03c69f5143edd40f567ec038d2425bba80bf9dd1a85b642e144ac1ac",
        "nfl2k5_pants_tset_compatibility/v1",
    ),
    "reports/assets/nfl2k5_live_helmet_txtr_compatibility.json": (
        2_572_552,
        "1b7bdbb67a28b9d70531c3af80ff67574a7d60ef421bcf42ba9422f0f278e6ff",
        "nfl2k5_live_helmet_txtr_compatibility/v1",
    ),
    "reports/assets/nfl2k5_live_numbers_nameplate_compatibility.json": (
        63_407_409,
        "d122c1e7de4fbad42c725969dce3473fc16a100e75d68ae5fb5d64077f536cd4",
        "nfl2k5_live_numbers_nameplate_compatibility/v1",
    ),
    "reports/assets/nfl2k5_team_select_card_inventory.json": (
        4_855_883,
        "3a1d3543afbf851331389228bc910ba453d749c04f7cf12f6471ba0cde64bf13",
        "nfl2k5_team_select_card_inventory/v1",
    ),
    "reports/assets/nfl2k5_player_portrait_compatibility.json": (
        9_446_076,
        "c0f792df4aa03a9a0c4e670c7b214da53a97f19526c84fd52765137120713481",
        "nfl2k5_player_portrait_compatibility/v1",
    ),
    "reports/assets/nfl2k5_live_face_texture_compatibility.json": (
        5_188_081,
        "812db90df6b50b4491d8701a0ceb13b54a26ea7afadc2fbd86c4715b15aa9e09",
        "nfl2k5_live_face_texture_compatibility/v1",
    ),
    "reports/assets/nfl2k5_create_team_field_art_inventory.json": (
        1_870_444,
        "6014d0ca882c76f0bba68a14338e357d7f33a745e9818856c57da7979ed1a4f5",
        "nfl2k5_create_team_field_art_inventory/v1",
    ),
    "reports/assets/scorebug_presentation_audit.json": (
        46_512,
        "57bcbb1c0ff8e6c2376565365aba523e4c2fe8cdb66d3a7058daa84993c2ccd1",
        "vc_scorebug_presentation_audit/v1",
    ),
    "reports/assets/nfl2k5_audo_import_capacity.json": (
        3_759_183,
        "1d9ebb31a8822d113ae0fc8ec028e4ff652ccb7cbcf9d6d1d870aa58ef65f556",
        "nfl2k5_audo_import_capacity/v1",
    ),
    "reports/assets/nfl2k5_audo_family_labels.json": (
        72_257,
        "ea66da8ea539114563de5694599a6046bde78661556846a34f8addeb31d544dd",
        "nfl2k5_audo_family_labels/v2",
    ),
    "reports/assets/uniform_texture_sharing.v2.json": (
        415_528,
        "9e137a17d0a5faaf6c12f35b7503193f583f4a97e7370deced28fefadf7c26cf",
        "uniform_texture_sharing_audit/v2",
    ),
    "mod_editor/data/nfl2k5_crib_catalog.v1.json": (
        735_928,
        "c78801144df2f070e003ba458c5affa15a52cc00221cc1a3d9983f1fbf172cd8",
        "2k5_mod_studio_crib_catalog/v1",
    ),
    "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json": (
        5_851_450,
        "fa2c9ca9bcc267b6981735347bf6daf6243d6ab8b83fba268804c280cfd94173",
        "nfl2k5_uniform_equipment_export_catalog/v1",
    ),
    "reports/specs/nfl2k5_crib_static_position_targets.v1.json": (
        14_024,
        "90f955166c8582f7041bd0d936bacbef1f44b3869487f71535acec1caeb44b4f",
        "nfl2k5_crib_static_position_targets/v1",
    ),
    "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json": (
        858_600,
        "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa",
        "nfl2k5_stadium_static_target_catalog/v1",
    ),
    "mod_editor/data/nfl2k5_gameplay_inspection.v1.json": (
        22_874,
        "864c785d3b0a689dace1ec9c37be0bc276519a334775c9df8953d6d62722dbe3",
        "nfl2k5_mod_studio_gameplay_inspection/v1",
    ),
    "mod_editor/data/nfl2k5_main_menu_inspection.v1.json": (
        3_563,
        "fae27305eada0ac1200896f0b907307e20942d2cf4506b2ff172c22ceb767629",
        "mod_editor_named_main_menu_inspector/v1",
    ),
}

# This 55 MiB inventory is reproducibly generated in the user's private cache
# from their selected XISO. It is deliberately not a release metadata input.
PRIVATE_INVENTORY_PATH = "reports/assets/nfl2k5_resource_chunks_v2.json"
PRIVATE_INVENTORY_SHA256 = (
    "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"
)
PRIVATE_AUDIO_ORIGIN_SCHEMAS = frozenset({
    "2k5_mod_studio_audio_source_pcm_fingerprints/v1",
    "2k5_mod_studio_audio_pcm_containment/v1",
    "2k5_mod_studio_audio_pcm_containment/v2",
})
PRIVATE_AUDIO_ORIGIN_NAME_MARKERS = (
    "audio-origin",
    "audio-pcm-containment",
    "audio-source-pcm-fingerprints",
)

# These roots contain local research, extracted retail data, runtime captures,
# or generated outputs. A release-stage tree must never contain them, even if a
# future allowlist accidentally names a file below one.
FORBIDDEN_COMPONENTS = frozenset(
    {
        ".cache",
        ".codex-tmp",
        ".geometry-proof",
        ".git",
        "__pycache__",
        "assets",
        "build",
        "cache",
        "derived",
        "dist",
        "evidence",
        "exports",
        "extracted",
        "fixtures",
        "ghidra_projects",
        "originals",
        "projects",
        "reports",
        "runtime",
    }
)
FORBIDDEN_PREFIXES = ("build-", "vc_53450030")
FORBIDDEN_SUFFIXES = frozenset(
    {
        ".0a",
        ".7z",
        ".arc",
        ".bin",
        ".chd",
        ".cso",
        ".dat",
        ".deb",
        ".dll",
        ".dol",
        ".elf",
        ".exe",
        ".gz",
        ".glb",
        ".gltf",
        ".iff",
        ".img",
        ".iso",
        ".jpg",
        ".jpeg",
        ".ogg",
        ".pak",
        ".png",
        ".qcow2",
        ".rar",
        ".raw",
        ".rom",
        ".rvz",
        ".sav",
        ".so",
        ".tar",
        ".vhd",
        ".vhdx",
        ".wad",
        ".wav",
        ".xbe",
        ".xex",
        ".xex2",
        ".xiso",
        ".xma",
        ".zip",
    }
)
ALLOWED_SUFFIXES = frozenset(
    {
        ".bat",
        ".cfg",
        ".command",
        ".css",
        ".desktop",
        ".html",
        ".ini",
        ".json",
        ".md",
        ".py",
        ".sh",
        ".svg",
        ".toml",
        ".txt",
    }
)
# Double-click launchers that must carry the owner-executable bit or they will
# silently fail to start (a macOS .command, a Unix .sh). A Windows .bat is not
# executed through a Unix mode bit, so it is deliberately excluded here.
EXECUTABLE_LAUNCHER_SUFFIXES = frozenset({".command", ".sh"})
ALLOWED_SUFFIXLESS_NAMES = frozenset({"copying", "license", "notice"})

# Renaming a known retail file to a text-looking extension must not bypass the
# path and suffix checks. Hashes are metadata only; none of the payloads ship.
KNOWN_RETAIL_SHA256 = frozenset(
    {
        # NFL 2K5 USA retail XISO.
        "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
        # NFL 2K5 USA default.xbe.
        "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
        # NFL 2K5 extracted vc_53450030/0 retail archive.
        "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
    }
)
RETAIL_MAGIC = (
    b"MICROSOFT*XBOX*MEDIA",
    b"XBEH",
    b"XEX2",
)

# The one binary asset in this release: the application icon Windows puts on the
# Start Menu shortcut. Icons are the classic hiding place for a payload someone
# renamed, so this file is not merely allowlisted -- it is pinned to an exact
# size and SHA-256 and required to still be a Windows icon image, the same
# treatment the APF release gives its reviewed extractor binaries.
#
# The bytes are original work generated from geometry by tools/make_app_icons.py
# (also in this release), which is deterministic: anyone can re-run it and get
# this exact file back. Update the pin only from that script's --print-pins
# output, never by hand.
ICO_MAGIC = b"\x00\x00\x01\x00"
REVIEWED_ICON = "packaging/icons/2k5-mod-studio.ico"
REVIEWED_ICON_SIZE = 24_127
REVIEWED_ICON_SHA256 = (
    "76fdffd1de77aa7ed53ba87076e995b7443f3cc379981c1241f7c9c108f5a18f"
)

# Reject only the two known workstation prefixes.  Build the strings from
# fragments so this allowlisted checker does not contain the private paths it
# is designed to detect in staged text.
FORBIDDEN_PRIVATE_TEXT_FRAGMENTS = (
    "/" + "home" + "/" + "noah",
    "/" + "media" + "/" + "noah",
)


class ReleaseCheckError(ValueError):
    """One or more release-stage invariants failed."""


def _safe_relative(value: str, label: str) -> PurePosixPath:
    if "\\" in value:
        raise ReleaseCheckError(f"{label} uses a backslash: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseCheckError(f"{label} is not a safe relative path: {value!r}")
    return path


def read_allowlist(path: Path) -> tuple[frozenset[str], tuple[str, ...]]:
    try:
        payload = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReleaseCheckError(f"cannot read release allowlist: {exc}") from exc
    exact: set[str] = set()
    prefixes: list[str] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(payload.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        is_prefix = line.endswith("/")
        normalized = line[:-1] if is_prefix else line
        relative = _safe_relative(normalized, f"allowlist line {line_number}").as_posix()
        key = relative + ("/" if is_prefix else "")
        if key in seen:
            raise ReleaseCheckError(f"duplicate release allowlist entry: {key}")
        seen.add(key)
        if is_prefix:
            prefixes.append(relative + "/")
        else:
            exact.add(relative)
    if not exact and not prefixes:
        raise ReleaseCheckError("release allowlist is empty")
    return frozenset(exact), tuple(sorted(prefixes))


def _is_allowed(relative: str, exact: frozenset[str], prefixes: tuple[str, ...]) -> bool:
    return relative in exact or any(relative.startswith(prefix) for prefix in prefixes)


def _is_declared_directory(relative: str, exact: frozenset[str], prefixes: tuple[str, ...]) -> bool:
    prefix = relative.rstrip("/") + "/"
    return any(item.startswith(prefix) for item in exact) or any(
        item == prefix or item.startswith(prefix) or prefix.startswith(item)
        for item in prefixes
    )


def _is_reviewed_metadata_or_parent(relative: PurePosixPath) -> bool:
    value = relative.as_posix().rstrip("/")
    prefix = value + "/"
    return value in REVIEWED_METADATA or any(
        item.startswith(prefix) for item in REVIEWED_METADATA
    )


def _forbidden_path(relative: PurePosixPath) -> str | None:
    if _is_reviewed_metadata_or_parent(relative):
        return None
    for component in relative.parts:
        folded = component.casefold()
        if folded in FORBIDDEN_COMPONENTS:
            return component
        if any(folded.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            return component
    return None


def _iter_tree(root: Path) -> Iterable[tuple[Path, os.stat_result]]:
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise ReleaseCheckError(f"cannot scan release directory {directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ReleaseCheckError(f"cannot inspect release entry {path}: {exc}") from exc
            yield path, info
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)


def _validate_reviewed_icon(path: Path, relative: str, info: os.stat_result) -> str:
    """Confirm the staged icon is byte-for-byte the reviewed one."""
    if info.st_size != REVIEWED_ICON_SIZE:
        raise ReleaseCheckError(f"reviewed application icon size changed: {relative}")
    payload = path.read_bytes()
    if len(payload) != REVIEWED_ICON_SIZE:
        raise ReleaseCheckError(f"release file changed while being read: {relative}")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != REVIEWED_ICON_SHA256:
        raise ReleaseCheckError(f"reviewed application icon hash changed: {relative}")
    if not payload.startswith(ICO_MAGIC):
        raise ReleaseCheckError(
            f"reviewed application icon is no longer a Windows icon: {relative}"
        )
    return digest


def _hash_and_validate_text(
    path: Path, relative: str, size: int, maximum_size: int,
) -> tuple[str, str]:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    completed = 0
    with path.open("rb") as source:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            completed += len(block)
            if completed > maximum_size:
                raise ReleaseCheckError(
                    f"release file exceeds its reviewed size ceiling: {relative}"
                )
            digest.update(block)
            chunks.append(block)
    if completed != size:
        raise ReleaseCheckError(f"release file changed while being read: {relative}")
    payload = b"".join(chunks)
    if b"\0" in payload:
        raise ReleaseCheckError(f"binary NUL byte in release text file: {relative}")
    # Format-aware source code legitimately names these signatures. Refuse a
    # disguised container whose payload starts with one; ordinary UTF-8 code
    # that documents or checks the signature remains distributable tooling.
    if any(payload.startswith(magic) for magic in RETAIL_MAGIC):
        raise ReleaseCheckError(f"retail/container magic in release file: {relative}")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseCheckError(f"release file is not UTF-8 text: {relative}") from exc
    folded_text = text.casefold()
    if any(fragment.casefold() in folded_text
           for fragment in FORBIDDEN_PRIVATE_TEXT_FRAGMENTS):
        raise ReleaseCheckError(f"private host path in release text file: {relative}")
    # Long whitespace-free strings are typical of embedded base64/binary blobs,
    # never a required product-code resource in this allowlist.
    token_length = 0
    for character in text:
        if character.isspace():
            token_length = 0
        else:
            token_length += 1
            if token_length > 4096:
                raise ReleaseCheckError(
                    f"possible embedded binary blob in release file: {relative}"
                )
    return digest.hexdigest(), text


def _metadata_contains_payload(value: object) -> bool:
    """Reject byte arrays/data URIs even inside an otherwise valid JSON file."""

    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                folded = str(key).casefold()
                if folded in {
                    "base64", "data_uri", "payload", "payload_base64",
                    "raw_bytes", "retail_bytes", "rgba_bytes",
                } and isinstance(item, (str, list)):
                    return True
                pending.append(item)
        elif isinstance(current, list):
            if len(current) > 256 and all(
                type(item) is int and 0 <= item <= 255 for item in current
            ):
                return True
            pending.extend(current)
        elif isinstance(current, str):
            folded = current.casefold()
            if folded.startswith("data:") or folded.startswith("base64:"):
                return True
    return False


def _validate_reviewed_metadata(
    relative: str, size: int, digest: str, text: str,
) -> None:
    expected_size, expected_digest, expected_schema = REVIEWED_METADATA[relative]
    if size != expected_size or digest != expected_digest:
        raise ReleaseCheckError(
            f"reviewed metadata size/hash changed: {relative}"
        )
    try:
        document = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise ReleaseCheckError(f"reviewed metadata is invalid JSON: {relative}") from exc
    if not isinstance(document, dict) or document.get("schema") != expected_schema:
        raise ReleaseCheckError(f"reviewed metadata schema changed: {relative}")
    if _metadata_contains_payload(document):
        raise ReleaseCheckError(f"retail payload data found in metadata: {relative}")


def audit_release(root: Path, allowlist: Path) -> dict[str, object]:
    try:
        root_info = root.lstat()
    except FileNotFoundError as exc:
        raise ReleaseCheckError(f"release root does not exist: {root}") from exc
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise ReleaseCheckError("release root must be a non-symlink directory")
    release_root = root.resolve(strict=True)
    exact, prefixes = read_allowlist(allowlist)

    seen_files: set[str] = set()
    seen_directories: set[str] = set()
    folded_paths: set[str] = set()
    total_bytes = 0
    reviewed_metadata_count = 0
    reviewed_icon_count = 0
    for path, info in _iter_tree(release_root):
        relative_path = PurePosixPath(path.relative_to(release_root).as_posix())
        relative = relative_path.as_posix()
        folded = relative.casefold()
        if folded in folded_paths:
            raise ReleaseCheckError(f"case-colliding release path: {relative}")
        folded_paths.add(folded)
        forbidden = _forbidden_path(relative_path)
        if forbidden is not None:
            raise ReleaseCheckError(
                f"forbidden extracted/build/local-data path component {forbidden!r}: {relative}"
            )
        if stat.S_ISLNK(info.st_mode):
            raise ReleaseCheckError(f"release symlinks are forbidden: {relative}")
        if stat.S_ISDIR(info.st_mode):
            if not _is_declared_directory(relative, exact, prefixes):
                raise ReleaseCheckError(f"undeclared release directory: {relative}")
            seen_directories.add(relative + "/")
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ReleaseCheckError(f"special release filesystem entry is forbidden: {relative}")
        if info.st_nlink != 1:
            raise ReleaseCheckError(f"hardlinked release file is forbidden: {relative}")
        if info.st_mode & stat.S_IWOTH:
            raise ReleaseCheckError(f"world-writable release file is forbidden: {relative}")
        if not _is_allowed(relative, exact, prefixes):
            raise ReleaseCheckError(f"file is absent from the release allowlist: {relative}")
        if relative == REVIEWED_ICON:
            # The only non-text file here, and the exemption is anchored to this
            # one path: ".ico" stays an unapproved suffix everywhere else, so
            # nothing can ship simply by taking the extension.  Whether the icon
            # is *present* is not decided here -- the allowlist declares it, and
            # the completeness check below refuses a release that omits it.
            _validate_reviewed_icon(path, relative, info)
            reviewed_icon_count += 1
            seen_files.add(relative)
            total_bytes += info.st_size
            continue
        suffix = path.suffix.casefold()
        if suffix in FORBIDDEN_SUFFIXES:
            raise ReleaseCheckError(f"retail/container/media suffix is forbidden: {relative}")
        if suffix not in ALLOWED_SUFFIXES and path.name.casefold() not in ALLOWED_SUFFIXLESS_NAMES:
            raise ReleaseCheckError(f"unapproved release file type: {relative}")
        if suffix in EXECUTABLE_LAUNCHER_SUFFIXES and not info.st_mode & stat.S_IXUSR:
            raise ReleaseCheckError(f"launcher script is not executable: {relative}")
        metadata_contract = REVIEWED_METADATA.get(relative)
        maximum_size = (
            metadata_contract[0] if metadata_contract is not None
            else MAX_RELEASE_FILE_BYTES
        )
        if info.st_size > maximum_size:
            raise ReleaseCheckError(
                f"release file exceeds its reviewed size ceiling: {relative}"
            )
        digest, text = _hash_and_validate_text(
            path, relative, info.st_size, maximum_size
        )
        if any(
            marker in relative.casefold()
            for marker in PRIVATE_AUDIO_ORIGIN_NAME_MARKERS
        ):
            raise ReleaseCheckError(
                f"private audio-origin inventory path is forbidden: {relative}"
            )
        if suffix == ".json":
            try:
                json_document = json.loads(text)
            except (ValueError, TypeError):
                json_document = None
            if isinstance(json_document, dict) and json_document.get("schema") \
                    in PRIVATE_AUDIO_ORIGIN_SCHEMAS:
                raise ReleaseCheckError(
                    f"private audio-origin inventory schema is forbidden: {relative}"
                )
        if digest in KNOWN_RETAIL_SHA256:
            raise ReleaseCheckError(f"known retail payload hash in release: {relative}")
        if digest == PRIVATE_INVENTORY_SHA256 or relative == PRIVATE_INVENTORY_PATH:
            raise ReleaseCheckError(
                f"private user-XISO inventory is forbidden in release: {relative}"
            )
        if metadata_contract is not None:
            _validate_reviewed_metadata(relative, info.st_size, digest, text)
            reviewed_metadata_count += 1
        if suffix == ".svg":
            try:
                ET.parse(path)
            except (ET.ParseError, OSError) as exc:
                raise ReleaseCheckError(f"invalid SVG XML in release: {relative}") from exc
        seen_files.add(relative)
        total_bytes += info.st_size

    missing_files = sorted(exact - seen_files)
    missing_prefixes = sorted(prefix for prefix in prefixes if prefix not in seen_directories)
    if missing_files or missing_prefixes:
        raise ReleaseCheckError(
            f"release is incomplete; missing files={missing_files}, missing directories={missing_prefixes}"
        )
    return {
        "schema": "2k5_mod_studio_release_audit/v1",
        "file_count": len(seen_files),
        "directory_count": len(seen_directories),
        "total_bytes": total_bytes,
        "reviewed_metadata_file_count": reviewed_metadata_count,
        "reviewed_icon_count": reviewed_icon_count,
        "private_generated_inventories_included": False,
        "retail_payloads_included": False,
        "symlinks_included": False,
        "undeclared_files_included": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_root", type=Path, help="already-staged release directory")
    parser.add_argument(
        "--allowlist",
        type=Path,
        help="allowlist file (default: <release-root>/packaging/release-allowlist.txt)",
    )
    args = parser.parse_args(argv)
    allowlist = args.allowlist or args.release_root / "packaging/release-allowlist.txt"
    try:
        report = audit_release(args.release_root, allowlist)
    except ReleaseCheckError as exc:
        print(f"2K5_MOD_STUDIO_RELEASE_REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        "2K5_MOD_STUDIO_RELEASE_PASS "
        f"files={report['file_count']} directories={report['directory_count']} "
        f"bytes={report['total_bytes']} "
        f"metadata={report['reviewed_metadata_file_count']} "
        "private_inventory=false retail=false symlinks=false undeclared=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

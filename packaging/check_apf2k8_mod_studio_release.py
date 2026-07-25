#!/usr/bin/env python3
"""Fail closed unless an APF 2K8 Mod Studio release is declared and retail-free."""

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


MAX_TEXT_FILE_BYTES = 8 * 1024 * 1024

# The product recognizes these payloads by hash, but none of their bytes may be
# distributed.  The set covers the USA ISO and every file in the validated
# extracted boot tree.
KNOWN_RETAIL_SHA256 = frozenset(
    {
        "c45aab61de93773dfe25adbae5749ad5adb3f3369a6c0106b2159ad603b6fe53",
        "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
        "775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53",
        "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
        "04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084",
        "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f",
        "39a492de1d957e767657dfe7fb5ff3b315a22c10aa8e9d4009c524362d851fc8",
    }
)

# A locally reviewed, GPL-licensed extractor is the sole binary in the public
# closure.  Its exact license is mandatory beside it.  Neither file contains
# game data.
REVIEWED_BINARY = "tools/vendor/extract-xiso/build/extract-xiso"
REVIEWED_BINARY_SIZE = 56_584
REVIEWED_BINARY_SHA256 = (
    "96e6286d371e47e24474a3b7c89ef5c204ddca9c93c95d5ebcb7bcf1d6eb530f"
)
REVIEWED_LICENSE = "tools/vendor/extract-xiso/LICENSE.TXT"
REVIEWED_LICENSE_SIZE = 3_115
REVIEWED_LICENSE_SHA256 = (
    "719d9e9a12c470a20d9f1988a03108fd99bb0b07a5340c6bbf3caf524b7adf01"
)
# The Windows extractor, built from the same vendored extract-xiso 2.7.1 source
# as the ELF above so a Windows user can hand the app a .iso directly.  It is
# reviewed exactly like its sibling -- pinned to an exact size and hash, and
# required to still be a PE image -- which is what earns it an exception from
# the forbidden-suffix rule.  ".exe" stays forbidden for every other path: this
# is one named file, not a relaxed category.
REVIEWED_WINDOWS_BINARY = "tools/vendor/extract-xiso/build/extract-xiso.exe"
REVIEWED_WINDOWS_BINARY_SIZE = 293_273
REVIEWED_WINDOWS_BINARY_SHA256 = (
    "e9567fe31b168b226531ed532714b3e1cc9070cdfac0c102fb881e2825aee68d"
)
REVIEWED_PATHS = frozenset(
    {REVIEWED_BINARY, REVIEWED_WINDOWS_BINARY, REVIEWED_LICENSE}
)

INSTALL_SURFACE = frozenset(
    {
        "APF-2K8-Mod-Studio.sh",
        "APF2K8-README.md",
        "install.sh",
        "uninstall.sh",
        "packaging/apf2k8_mod_studio_installer.py",
        "tools/launch_apf2k8_mod_studio.sh",
        "packaging/apf2k8-mod-studio.desktop",
        "packaging/apf2k8-mod-studio.svg",
    }
)
INSTALL_EXECUTABLES = frozenset(
    {
        "APF-2K8-Mod-Studio.sh",
        "install.sh",
        "uninstall.sh",
        "packaging/apf2k8_mod_studio_installer.py",
        "tools/launch_apf2k8_mod_studio.sh",
    }
)

# Product-release identity and the Alpha34 cue-annotation boundary. These
# are source/docs markers only: no game bytes, replacement payload hashes, or
# private paths are embedded in the release checker.
REQUIRED_PRODUCT_CONTRACT_MARKERS: dict[str, tuple[str, ...]] = {
    "mod_editor/apf_studio/__init__.py": (
        '__version__ = "0.1.0-alpha.34"',
    ),
    "mod_editor/apf_studio/audio_annotations.py": (
        'AUDIO_ANNOTATIONS_SCHEMA = "apf2k8_audio_annotations/v1"',
        "MAX_AUDIO_ANNOTATIONS = 47_775",
        "Annotations are user-authored project metadata",
    ),
    "mod_editor/apf_studio/project.py": (
        "AUDIO_ANNOTATIONS_MEMBER",
        "audio-annotations.json",
        "_reject_duplicate_json_pairs",
    ),
    "mod_editor/apf_studio/gui.py": (
        "AUDIO_ANNOTATION_UI_CONTRACT",
        "project_metadata_only_stable_logical_cue_id",
        "Labeled only",
        "Your cue label & notes",
        "AUDIO_DIRECT_DROP_CONTRACT",
        "selected_exact_slot_xma1_or_pcm16_wav",
        "Drop .xma or exact PCM16 .wav here",
        "directAudioReplacementWorkerFinished",
        "submission through worker drain",
        "AUDIO_REPLACEMENT_IMPORT_CONFIRMATION_CONTRACT",
        "fully_validated_read_only_preview_then_explicit_apply",
        "Would change",
        "Already current",
        "Modified audio after Apply",
        "run_when_idle=self._run_when_idle",
        "self._idle_callbacks.append(callback)",
    ),
    "mod_editor/apf_studio/session.py": (
        "set_audio_annotation",
        "clear_audio_annotation",
        "project_metadata_count",
        "_audio_replacement_confirmation_token",
        "member_sha256",
        "validated_result_sha256",
        "project_audio_revision",
        "hmac.compare_digest",
    ),
    "mod_editor/apf_studio/facade.py": (
        "labeled_only",
        "set_audio_annotation",
        "clear_audio_annotation",
        "preview_audio_replacement_pack",
        "confirmation_token",
    ),
    "APF2K8-README.md": (
        "0.1.0-alpha.34",
        "Your cue label & notes",
        "Labeled only",
        "47,775 playable cues",
        "Drop .xma or exact PCM16 .wav here",
        "Review replacement",
        "nothing is staged",
    ),
    "docs/mod_editor/apf2k8_mod_studio_getting_started.md": (
        "0.1.0-alpha.34",
        "Your cue label & notes",
        "Labeled only",
        "audio-annotations.json",
        "Drop .xma or exact PCM16 .wav here",
        "Would change",
        "Modified audio after Apply",
    ),
    "docs/mod_editor/apf2k8_mod_studio_changelog.md": (
        "0.1.0-alpha.34",
        "project_metadata_only_stable_logical_cue_id",
        "audio-annotations.json",
        "selected_exact_slot_xma1_or_pcm16_wav",
        "fully_validated_read_only_preview_then_explicit_apply",
    ),
    "docs/mod_editor/APF2K8_STATUS.md": (
        "0.1.0-alpha.34 candidate boundary",
        "project_metadata_only_stable_logical_cue_id",
        "47,775 playable cues",
        "selected_exact_slot_xma1_or_pcm16_wav",
        "fully_validated_read_only_preview_then_explicit_apply",
    ),
}

# These compact catalogs contain reviewed coordinates or sanitized named
# findings only. They have no decoded pixels, compressed spans, preimages, or
# rollback bytes. Exact pinning prevents a later data file from silently
# broadening the public metadata boundary.
REVIEWED_METADATA: dict[str, tuple[int, str, str]] = {
    "mod_editor/data/apf2k8_product_findings.v1.json": (
        4_763,
        "aa25d22534bce1b84bcf97b7f534c41ac37da71b22aca10110b2f867b482cd7d",
        "apf2k8_mod_studio_product_findings/v1",
    ),
    "mod_editor/data/apf2k8_player_ratings.v1.json": (
        9_591,
        "b727bcb6bf99b26df077c780c9c77320d28506817a42cfa7749cf140942b1797",
        "apf2k8_player_ratings/v1",
    ),
    "mod_editor/data/apf2k8_player_positions.v1.json": (
        2_330,
        "9af0925439c2c61428700da0b50e7f36bae9f16626c7ac0afd25c09385135eb9",
        "apf2k8_player_positions/v1",
    ),
    "mod_editor/data/apf2k8_uniform_targets.v1.json": (
        45_434,
        "2c5457150195a9c634e0dda93f05d28814c275fef6d4d2f1485428e98b800ed9",
        "apf2k8_uniform_targets/v1",
    ),
}

ALLOWED_TEXT_SUFFIXES = frozenset(
    {
        ".bat", ".command", ".css", ".desktop", ".html", ".ini", ".json",
        ".md", ".py", ".sh", ".svg", ".toml", ".txt",
    }
)
ALLOWED_SUFFIXLESS_TEXT = frozenset({"copying", "license", "notice"})
# Double-click launchers that must carry the owner-executable bit or they will
# silently fail to start (a macOS .command, a Unix .sh). A Windows .bat is not
# executed through a Unix mode bit, so it is deliberately excluded here.
EXECUTABLE_LAUNCHER_SUFFIXES = frozenset({".command", ".sh"})
FORBIDDEN_MEDIA_SUFFIXES = frozenset(
    {
        ".0a",
        ".0b",
        ".1a",
        ".1b",
        ".7z",
        ".aac",
        ".arc",
        ".avi",
        ".bin",
        ".bmp",
        ".chd",
        ".cso",
        ".dat",
        ".dds",
        ".dll",
        ".elf",
        ".exe",
        ".flac",
        ".gif",
        ".glb",
        ".gltf",
        ".gz",
        ".h7a",
        ".iff",
        ".img",
        ".iso",
        ".jpeg",
        ".jpg",
        ".m4a",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".ogg",
        ".pak",
        ".png",
        ".rar",
        ".raw",
        ".riff",
        ".rom",
        ".rvz",
        ".sav",
        ".so",
        ".tar",
        ".tga",
        ".vhd",
        ".vhdx",
        ".wav",
        ".webm",
        ".xex",
        ".xiso",
        ".xma",
        ".zip",
    }
)

# These are local/private product outputs or common homes for retail-derived
# payloads.  An allowlist typo cannot make one of these roots distributable.
FORBIDDEN_COMPONENTS = frozenset(
    {
        ".cache",
        ".codex-tmp",
        ".git",
        "__pycache__",
        "$systemupdate",
        "assets",
        "audio",
        "backups",
        "cache",
        "captures",
        "derived",
        "dist",
        "evidence",
        "export",
        "exports",
        "extracted",
        "fixtures",
        "game",
        "games",
        "gltf",
        "manifests",
        "originals",
        "preimages",
        "private",
        "reports",
        "rollback",
        "runtime",
        "screenshots",
        "storage",
        "videos",
        "wineprefix",
        "xenia",
    }
)
FORBIDDEN_GAME_NAMES = frozenset(
    {
        "0a",
        "0b",
        "1a",
        "1b",
        "default.xex",
        "su20076000_00000000",
    }
)
RETAIL_MAGIC = (
    b"MICROSOFT*XBOX*MEDIA",
    b"XEX2",
    b"XBEH",
    b"RIFF",  # Audio/video belongs only in the user's private export folder.
)


class ReleaseCheckError(ValueError):
    """A release-stage invariant failed."""


def _safe_relative(value: str, label: str) -> PurePosixPath:
    if "\\" in value:
        raise ReleaseCheckError(f"{label} uses a backslash: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or value.endswith("/")
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ReleaseCheckError(f"{label} is not an exact safe relative file: {value!r}")
    return path


def read_allowlist(path: Path) -> frozenset[str]:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ReleaseCheckError(f"release allowlist is missing: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ReleaseCheckError("release allowlist must be a regular non-symlink file")
    if info.st_size > 256 * 1024:
        raise ReleaseCheckError("release allowlist is unexpectedly large")
    try:
        payload = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReleaseCheckError(f"cannot read release allowlist: {exc}") from exc
    declared: set[str] = set()
    for line_number, raw in enumerate(payload.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        relative = _safe_relative(line, f"allowlist line {line_number}")
        value = relative.as_posix()
        if value in declared:
            raise ReleaseCheckError(f"duplicate release allowlist entry: {value}")
        declared.add(value)
    if not declared:
        raise ReleaseCheckError("release allowlist is empty")
    return frozenset(declared)


def _is_reviewed_path_or_parent(relative: PurePosixPath) -> bool:
    value = relative.as_posix().rstrip("/")
    prefix = value + "/"
    return value in REVIEWED_PATHS or any(item.startswith(prefix) for item in REVIEWED_PATHS)


def _forbidden_path(relative: PurePosixPath) -> str | None:
    reviewed_parent = _is_reviewed_path_or_parent(relative)
    for component in relative.parts:
        folded = component.casefold()
        if folded == "build" and reviewed_parent:
            continue
        if folded in FORBIDDEN_COMPONENTS or folded in FORBIDDEN_GAME_NAMES:
            return component
        if folded.startswith("build-") or folded.startswith("apf-all-family-selector-runtime"):
            return component
        suffix = PurePosixPath(component).suffix.casefold()
        if suffix != ".py" and any(
            marker in folded
            for marker in ("manifest", "preimage", "rollback", "screenshot", "runtime-capture")
        ):
            return component
    return None


def _iter_tree(root: Path) -> Iterable[tuple[Path, os.stat_result]]:
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise ReleaseCheckError(f"cannot scan {directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ReleaseCheckError(f"cannot inspect {path}: {exc}") from exc
            yield path, info
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)


def _hash_regular(path: Path, expected_size: int, maximum: int) -> tuple[str, bytes]:
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    completed = 0
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            completed += len(block)
            if completed > maximum:
                raise ReleaseCheckError(f"release file exceeds its size ceiling: {path.name}")
            digest.update(block)
            chunks.append(block)
    if completed != expected_size:
        raise ReleaseCheckError(f"release file changed while being read: {path.name}")
    return digest.hexdigest(), b"".join(chunks)


def _validate_reviewed_windows_binary(path: Path, info: os.stat_result) -> str:
    if info.st_size != REVIEWED_WINDOWS_BINARY_SIZE:
        raise ReleaseCheckError("reviewed extract-xiso Windows binary size changed")
    digest, payload = _hash_regular(path, info.st_size, REVIEWED_WINDOWS_BINARY_SIZE)
    if digest != REVIEWED_WINDOWS_BINARY_SHA256:
        raise ReleaseCheckError("reviewed extract-xiso Windows binary hash changed")
    if not payload.startswith(b"MZ"):
        raise ReleaseCheckError(
            "reviewed extract-xiso Windows binary is no longer a PE image"
        )
    return digest


def _validate_reviewed_binary(path: Path, info: os.stat_result) -> str:
    if info.st_size != REVIEWED_BINARY_SIZE:
        raise ReleaseCheckError("reviewed extract-xiso binary size changed")
    digest, payload = _hash_regular(path, info.st_size, REVIEWED_BINARY_SIZE)
    if digest != REVIEWED_BINARY_SHA256:
        raise ReleaseCheckError("reviewed extract-xiso binary hash changed")
    if not payload.startswith(b"\x7fELF"):
        raise ReleaseCheckError("reviewed extract-xiso binary is no longer ELF")
    if not info.st_mode & stat.S_IXUSR:
        raise ReleaseCheckError("reviewed extract-xiso binary is not executable")
    return digest


def _validate_text(path: Path, relative: str, info: os.stat_result) -> tuple[str, str]:
    if info.st_size > MAX_TEXT_FILE_BYTES:
        raise ReleaseCheckError(f"release text file exceeds 8 MiB: {relative}")
    digest, payload = _hash_regular(path, info.st_size, MAX_TEXT_FILE_BYTES)
    if any(payload.startswith(magic) for magic in RETAIL_MAGIC):
        raise ReleaseCheckError(f"game/media container magic in release file: {relative}")
    if b"\0" in payload:
        raise ReleaseCheckError(f"binary NUL byte in release text file: {relative}")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseCheckError(f"release file is not UTF-8 text: {relative}") from exc
    token_length = 0
    for character in text:
        if character.isspace():
            token_length = 0
        else:
            token_length += 1
            if token_length > 4096:
                raise ReleaseCheckError(f"possible embedded binary blob: {relative}")
    return digest, text


def _contains_embedded_payload(value: object) -> bool:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                folded = str(key).casefold()
                if folded in {
                    "base64",
                    "body_hex",
                    "compressed_bytes",
                    "data_uri",
                    "payload",
                    "payload_base64",
                    "raw_bytes",
                    "retail_bytes",
                    "rgba",
                    "rgba_bytes",
                    "texture_data",
                } and isinstance(item, (str, list)):
                    return True
                pending.append(item)
        elif isinstance(current, list):
            if len(current) > 256 and all(type(item) is int and 0 <= item <= 255 for item in current):
                return True
            pending.extend(current)
        elif isinstance(current, str):
            lowered = current.casefold()
            if lowered.startswith(("data:", "base64:")):
                return True
    return False


def _validate_structured_text(path: Path, relative: str, text: str) -> None:
    suffix = path.suffix.casefold()
    if suffix == ".json":
        try:
            document = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise ReleaseCheckError(f"invalid JSON in release: {relative}") from exc
        if _contains_embedded_payload(document):
            raise ReleaseCheckError(f"embedded game/media payload in JSON: {relative}")
        metadata_contract = REVIEWED_METADATA.get(relative)
        if metadata_contract is not None:
            _size, _digest, schema = metadata_contract
            if not isinstance(document, dict) or document.get("schema") != schema:
                raise ReleaseCheckError(f"reviewed metadata schema changed: {relative}")
    elif suffix == ".svg":
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ReleaseCheckError(f"invalid SVG XML in release: {relative}") from exc
        if not root.tag.endswith("svg"):
            raise ReleaseCheckError(f"SVG root element changed: {relative}")


def _validate_install_surface(relative: str, text: str, info: os.stat_result) -> None:
    if relative not in INSTALL_SURFACE:
        return
    if relative in INSTALL_EXECUTABLES and not info.st_mode & stat.S_IXUSR:
        raise ReleaseCheckError(f"install/launch surface is not executable: {relative}")
    required_markers: dict[str, tuple[str, ...]] = {
        "APF-2K8-Mod-Studio.sh": (
            "tools/launch_apf2k8_mod_studio.sh",
            'exec "$launcher" "$@"',
        ),
        "install.sh": (
            "apf2k8_mod_studio_installer.py",
            'install --source-root "$release_root"',
        ),
        "uninstall.sh": (
            "apf2k8_mod_studio_installer.py",
            'uninstall "$@"',
        ),
        "packaging/apf2k8_mod_studio_installer.py": (
            'INSTALL_SCHEMA = "apf2k8_mod_studio_install/v1"',
            "contains_retail_game_data",
            "preserves_user_data_on_uninstall",
            "Do not use sudo or run this installer as root",
            "_validate_app_marker",
            "_preflight_external",
        ),
        "tools/launch_apf2k8_mod_studio.sh": (
            "PYTHONNOUSERSITE=1",
            "python3 -m mod_editor.apf_studio",
            "XDG_STATE_HOME",
            "last-launch.log",
        ),
        "packaging/apf2k8-mod-studio.desktop": (
            "Exec=apf2k8-mod-studio",
            "TryExec=apf2k8-mod-studio",
            "Icon=apf2k8-mod-studio",
        ),
    }
    for marker in required_markers.get(relative, ()):
        if marker not in text:
            raise ReleaseCheckError(
                f"install/launch surface omitted required contract marker {marker!r}: {relative}"
            )
    if relative.endswith(".sh") and any(
        token in text for token in ("rm -rf", "rm -fr", "DISPLAY=:0", "xdotool")
    ):
        raise ReleaseCheckError(f"install/launch shell contains a destructive or active-desktop token: {relative}")
    if relative == "packaging/apf2k8_mod_studio_installer.py" and any(
        token in text for token in ("shell=True", "os.system(", "shutil.rmtree", "DISPLAY=:0")
    ):
        raise ReleaseCheckError("per-user installer contains an unsafe execution/deletion primitive")


def _validate_product_contract(relative: str, text: str) -> None:
    for marker in REQUIRED_PRODUCT_CONTRACT_MARKERS.get(relative, ()):
        if marker not in text:
            raise ReleaseCheckError(
                f"Alpha34 product contract omitted {marker!r}: {relative}"
            )


def audit_release(root: Path, allowlist_path: Path) -> dict[str, object]:
    try:
        root_info = root.lstat()
    except FileNotFoundError as exc:
        raise ReleaseCheckError(f"release root does not exist: {root}") from exc
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise ReleaseCheckError("release root must be a non-symlink directory")
    release_root = root.resolve(strict=True)
    declared = read_allowlist(allowlist_path)
    if INSTALL_SURFACE - declared:
        raise ReleaseCheckError(
            f"per-user install/portable surface is incomplete: {sorted(INSTALL_SURFACE - declared)}"
        )
    for item in declared:
        forbidden = _forbidden_path(PurePosixPath(item))
        if forbidden is not None:
            raise ReleaseCheckError(
                f"allowlist declares forbidden private/game component {forbidden!r}: {item}"
            )
    if REVIEWED_PATHS - declared:
        raise ReleaseCheckError("reviewed extract-xiso binary and license must both be declared")

    seen_files: set[str] = set()
    seen_folded: set[str] = set()
    total_bytes = 0
    reviewed_metadata_count = 0
    for path, info in _iter_tree(release_root):
        relative_path = PurePosixPath(path.relative_to(release_root).as_posix())
        relative = relative_path.as_posix()
        folded = relative.casefold()
        if folded in seen_folded:
            raise ReleaseCheckError(f"case-colliding release path: {relative}")
        seen_folded.add(folded)
        forbidden = _forbidden_path(relative_path)
        if forbidden is not None:
            raise ReleaseCheckError(
                f"forbidden private/game path component {forbidden!r}: {relative}"
            )
        if stat.S_ISLNK(info.st_mode):
            raise ReleaseCheckError(f"release symlinks are forbidden: {relative}")
        if stat.S_ISDIR(info.st_mode):
            prefix = relative.rstrip("/") + "/"
            if not any(item.startswith(prefix) for item in declared):
                raise ReleaseCheckError(f"undeclared release directory: {relative}")
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ReleaseCheckError(f"special filesystem entry is forbidden: {relative}")
        if info.st_nlink != 1:
            raise ReleaseCheckError(f"hardlinked release file is forbidden: {relative}")
        if info.st_mode & stat.S_IWOTH:
            raise ReleaseCheckError(f"world-writable release file is forbidden: {relative}")
        if relative not in declared:
            raise ReleaseCheckError(f"file is absent from the APF release allowlist: {relative}")
        if relative == REVIEWED_BINARY:
            digest = _validate_reviewed_binary(path, info)
        elif relative == REVIEWED_WINDOWS_BINARY:
            digest = _validate_reviewed_windows_binary(path, info)
        else:
            suffix = path.suffix.casefold()
            if suffix in FORBIDDEN_MEDIA_SUFFIXES:
                raise ReleaseCheckError(f"game/container/media suffix is forbidden: {relative}")
            if suffix not in ALLOWED_TEXT_SUFFIXES and path.name.casefold() not in ALLOWED_SUFFIXLESS_TEXT:
                raise ReleaseCheckError(f"unapproved release file type: {relative}")
            if suffix in EXECUTABLE_LAUNCHER_SUFFIXES and not info.st_mode & stat.S_IXUSR:
                raise ReleaseCheckError(f"launcher script is not executable: {relative}")
            digest, text = _validate_text(path, relative, info)
            _validate_structured_text(path, relative, text)
            _validate_install_surface(relative, text, info)
            _validate_product_contract(relative, text)
            metadata_contract = REVIEWED_METADATA.get(relative)
            if metadata_contract is not None:
                expected_size, expected_digest, _schema = metadata_contract
                if info.st_size != expected_size or digest != expected_digest:
                    raise ReleaseCheckError(f"reviewed metadata size/hash changed: {relative}")
                reviewed_metadata_count += 1
            if relative == REVIEWED_LICENSE and (
                info.st_size != REVIEWED_LICENSE_SIZE or digest != REVIEWED_LICENSE_SHA256
            ):
                raise ReleaseCheckError("reviewed extract-xiso license changed")
        if digest in KNOWN_RETAIL_SHA256:
            raise ReleaseCheckError(f"known APF retail payload hash in release: {relative}")
        seen_files.add(relative)
        total_bytes += info.st_size

    missing = sorted(declared - seen_files)
    if missing:
        raise ReleaseCheckError(f"release is incomplete; missing files={missing}")
    return {
        "schema": "apf2k8_mod_studio_release_audit/v1",
        "file_count": len(seen_files),
        "total_bytes": total_bytes,
        "retail_hash_count_rejected": len(KNOWN_RETAIL_SHA256),
        "reviewed_binary_count": 1,
        "reviewed_metadata_count": reviewed_metadata_count,
        "install_surface_count": len(INSTALL_SURFACE),
        "retail_payloads_included": False,
        "private_outputs_included": False,
        "symlinks_included": False,
        "undeclared_files_included": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_root", type=Path, help="already-staged APF release directory")
    parser.add_argument(
        "--allowlist",
        type=Path,
        help=(
            "exact allowlist (default: "
            "<release-root>/packaging/apf2k8-release-allowlist.txt)"
        ),
    )
    args = parser.parse_args(argv)
    allowlist = args.allowlist or args.release_root / "packaging/apf2k8-release-allowlist.txt"
    try:
        report = audit_release(args.release_root, allowlist)
    except ReleaseCheckError as exc:
        print(f"APF2K8_MOD_STUDIO_RELEASE_REFUSED: {exc}", file=sys.stderr)
        return 1
    print(
        "APF2K8_MOD_STUDIO_RELEASE_PASS "
        f"files={report['file_count']} bytes={report['total_bytes']} "
        f"metadata={report['reviewed_metadata_count']} "
        f"install_surface={report['install_surface_count']} "
        "retail_hashes=7 extractor=reviewed private=false retail=false "
        "symlinks=false undeclared=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

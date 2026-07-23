#!/usr/bin/env python3
"""Create a copy-only NFL 2K5 tree with two proved uniform color words patched.

This is intentionally a narrow writer.  It patches only the two 32-bit packed
color fields in the raw ``Unif`` resource of the retail Detroit Lions current
home and away packages.  It is not a texture, model, or general IFF writer.

All non-target files are hard-linked into a newly-created output tree.  Packs
``A`` and ``B`` are byte-copied into new, exclusively-created inodes before any
write.  Source files are opened read-only, and every output write stays bound
to the file descriptor/inode that this process created.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
from typing import Iterable

from nfl_outer import Archive, Entry, Pack, parse_archive, read_entry_range


SCHEMA = "nfl2k5_uniform_color_patch/v1"
TESTED_INDEX_REL = Path("vc_53450030/0")
TARGET_PACK_RELS = (Path("vc_53450030/A"), Path("vc_53450030/B"))
EXPECTED_FILE_COUNT = 19
EXPECTED_ISO_SHA256 = (
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
EXPECTED_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
EXPECTED_INDEX_SHA256 = (
    "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
)
MAGENTA_ARGB = 0xFFFF00FF
MAGENTA_PAIR = struct.pack("<II", MAGENTA_ARGB, MAGENTA_ARGB)
UNIF_WRAPPER_SIZE = 0x20
UNIF_BODY_SIZE = 0x50
UNIF_PAYLOAD_OFFSET = 0x30
COLOR_PAIR_ENTRY_OFFSET = UNIF_WRAPPER_SIZE + UNIF_PAYLOAD_OFFSET


class PatchError(ValueError):
    """Raised when an input or output cannot be proved safe."""


@dataclass(frozen=True)
class Target:
    outer_index: int
    logical_name: str
    name_id: int
    expected_outer_size: int
    expected_outer_sha256: str
    expected_unif_body_sha256: str
    expected_colors: tuple[int, int]
    expected_pack: str


TARGETS = (
    Target(
        3685,
        "09H0.IFF",
        0x9A4832D6,
        1_533_088,
        "471080a38b3ac0bce62fe3e47502e47ac2045ec0cc18bdd876cfd74c0e8145ce",
        "54a25776a10aac769cb3e299ff950b4dcb6f79e030be8fc0e68a8bfb19a56b53",
        (0xFF000000, 0xFF385AAF),
        "A",
    ),
    Target(
        4002,
        "09A0.IFF",
        0x07E10847,
        1_544_224,
        "df067569943e0d1a24e6bf3be4dbb9a8a34b9ff305a44dbf0a0b61bf3e7f8d1c",
        "0d327a8ef4771d4a4034384167d6ba61a18efdfe8c4233d4e5b171492c09f9e2",
        (0xFF000000, 0xFF385AAF),
        "B",
    ),
)

EXPECTED_PACK_SHA256 = {
    "A": "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b",
    "B": "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614",
}


@dataclass(frozen=True)
class OwnedFile:
    path: Path
    descriptor: int
    identity: tuple[int, int]


@dataclass(frozen=True)
class PatchSlice:
    pack_name: str
    pack_offset: int
    data: bytes
    virtual_offset: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PatchError(message)


def sha256_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while True:
        chunk = os.pread(descriptor, 8 * 1024 * 1024, offset)
        if not chunk:
            break
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        return sha256_fd(descriptor)
    finally:
        os.close(descriptor)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fd_identity(descriptor: int) -> tuple[int, int]:
    info = os.fstat(descriptor)
    return info.st_dev, info.st_ino


def path_identity(path: Path) -> tuple[int, int] | None:
    try:
        info = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return None
    return info.st_dev, info.st_ino


def reserve_file(path: Path, mode: int = 0o644) -> OwnedFile:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
    except FileExistsError as exc:
        raise PatchError(f"output already exists: {path}") from exc
    return OwnedFile(path, descriptor, fd_identity(descriptor))


def owned_path_matches(owned: OwnedFile) -> bool:
    return path_identity(owned.path) == owned.identity


def unlink_if_owned(owned: OwnedFile) -> None:
    if owned_path_matches(owned):
        owned.path.unlink()


def write_owned_json(owned: OwnedFile, value: dict[str, object]) -> None:
    require(owned_path_matches(owned), f"output path inode changed: {owned.path}")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    os.ftruncate(owned.descriptor, 0)
    offset = 0
    while offset < len(payload):
        written = os.pwrite(owned.descriptor, payload[offset:], offset)
        require(written > 0, "short manifest write")
        offset += written
    os.fsync(owned.descriptor)
    require(os.pread(owned.descriptor, len(payload), 0) == payload, "manifest readback failed")
    require(owned_path_matches(owned), f"manifest path inode changed: {owned.path}")


def _canonical_nonexistent(path: Path) -> Path:
    return path.parent.resolve(strict=True) / path.name


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def preflight_paths(source_root: Path, output_root: Path, manifest: Path) -> tuple[Path, Path, Path]:
    source = source_root.resolve(strict=True)
    require(source.is_dir(), f"source game root is not a directory: {source}")
    output = _canonical_nonexistent(output_root)
    manifest_canonical = _canonical_nonexistent(manifest)
    require(not output.exists(), f"output tree already exists: {output}")
    require(not manifest_canonical.exists(), f"manifest already exists: {manifest_canonical}")
    require(output != source, "output tree aliases source tree")
    require(not _is_within(output, source), "output tree may not be inside source tree")
    require(not _is_within(source, output), "source tree may not be inside output tree")
    require(not _is_within(manifest_canonical, output), "manifest may not be inside output tree")
    require(manifest_canonical != source, "manifest aliases source tree")
    return source, output, manifest_canonical


def validate_source_tree(source_root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(source_root.rglob("*")):
        require(not path.is_symlink(), f"PORTME: source tree contains symlink: {path}")
        if path.is_file():
            paths.append(path.relative_to(source_root))
        else:
            require(path.is_dir(), f"PORTME: unsupported source node: {path}")
    require(len(paths) == EXPECTED_FILE_COUNT, f"expected {EXPECTED_FILE_COUNT} retail files, found {len(paths)}")
    require(Path("default.xbe") in paths, "retail default.xbe is missing")
    require(TESTED_INDEX_REL in paths, "retail archive index is missing")
    for target in TARGET_PACK_RELS:
        require(target in paths, f"retail target pack is missing: {target}")
    require(sha256_file(source_root / "default.xbe") == EXPECTED_XBE_SHA256, "default.xbe SHA-256 mismatch")
    require(sha256_file(source_root / TESTED_INDEX_REL) == EXPECTED_INDEX_SHA256, "archive index SHA-256 mismatch")
    return paths


def validate_target(archive: Archive, target: Target) -> tuple[Entry, bytes]:
    require(target.outer_index < len(archive.entries), f"outer {target.outer_index} is absent")
    entry = archive.entries[target.outer_index]
    require(entry.name_id == target.name_id, f"{target.logical_name}: outer ID mismatch")
    require(entry.size == target.expected_outer_size, f"{target.logical_name}: outer size mismatch")
    require(len(entry.segments) == 1, f"{target.logical_name}: PORTME target unexpectedly spans packs")
    require(entry.segments[0].pack_name == target.expected_pack, f"{target.logical_name}: target pack mismatch")
    head = read_entry_range(archive, entry, 0, UNIF_WRAPPER_SIZE + UNIF_BODY_SIZE)
    wrapper = head[:UNIF_WRAPPER_SIZE]
    body = head[UNIF_WRAPPER_SIZE:]
    require(wrapper[:4] == b"Unif", f"{target.logical_name}: missing Unif wrapper")
    require(struct.unpack_from("<I", wrapper, 4)[0] == UNIF_BODY_SIZE, f"{target.logical_name}: Unif size mismatch")
    require(wrapper[8:] == bytes(0x18), f"{target.logical_name}: unsupported Unif wrapper flags")
    require(sha256_bytes(body) == target.expected_unif_body_sha256, f"{target.logical_name}: Unif body SHA-256 mismatch")
    require(body[0x0C:0x10] == b"Unif", f"{target.logical_name}: inner Unif marker mismatch")
    require(struct.unpack_from("<II", body, 0x10) == (17, 29), f"{target.logical_name}: relative fields mismatch")
    require(body[0x18:0x20] == bytes(8), f"{target.logical_name}: callback slots are not zero")
    require(body[0x20:0x30].decode("utf-16le").rstrip("\0") == "uniform", f"{target.logical_name}: object name mismatch")
    colors = struct.unpack_from("<II", body, UNIF_PAYLOAD_OFFSET)
    require(colors == target.expected_colors, f"{target.logical_name}: retail colors mismatch")
    # Hash the complete outer without relying on the inventory report.
    digest = hashlib.sha256()
    cursor = 0
    while cursor < entry.size:
        size = min(8 * 1024 * 1024, entry.size - cursor)
        digest.update(read_entry_range(archive, entry, cursor, size))
        cursor += size
    require(digest.hexdigest() == target.expected_outer_sha256, f"{target.logical_name}: outer SHA-256 mismatch")
    return entry, body


def map_virtual_write(archive: Archive, virtual_offset: int, data: bytes) -> tuple[PatchSlice, ...]:
    """Map one virtual archive write into bounded physical pack slices.

    The routine deliberately supports a write crossing any number of pack
    boundaries even though the two currently proved fields live wholly in A/B.
    """
    require(data, "zero-length virtual write")
    virtual_end = virtual_offset + len(data)
    require(0 <= virtual_offset < archive.virtual_size, "virtual write starts outside archive")
    require(virtual_end <= archive.virtual_size, "virtual write ends outside archive")
    slices: list[PatchSlice] = []
    consumed = 0
    for pack in archive.packs:
        start = max(virtual_offset, pack.virtual_start)
        end = min(virtual_end, pack.virtual_end)
        if start < end:
            size = end - start
            slices.append(PatchSlice(pack.name, start - pack.virtual_start, data[consumed:consumed + size], start))
            consumed += size
        if end == virtual_end:
            break
    require(consumed == len(data), "could not map complete virtual write")
    return tuple(slices)


def _copy_fd(source_fd: int, destination_fd: int, size: int) -> None:
    offset = 0
    while offset < size:
        chunk = os.pread(source_fd, min(8 * 1024 * 1024, size - offset), offset)
        require(chunk, "short source read while copying target pack")
        written_total = 0
        while written_total < len(chunk):
            written = os.pwrite(destination_fd, chunk[written_total:], offset + written_total)
            require(written > 0, "short destination write while copying target pack")
            written_total += written
        offset += len(chunk)
    os.fsync(destination_fd)


def clone_tree(source_root: Path, output_root: Path, relative_files: Iterable[Path]) -> tuple[dict[str, int], dict[str, OwnedFile], dict[str, int]]:
    try:
        output_root.mkdir(mode=0o755)
    except FileExistsError as exc:
        raise PatchError(f"output tree appeared after preflight: {output_root}") from exc
    root_info = output_root.stat(follow_symlinks=False)
    root_identity = {"device": root_info.st_dev, "inode": root_info.st_ino}
    owned_packs: dict[str, OwnedFile] = {}
    hardlinked = 0
    copied = 0
    for relative in relative_files:
        source = source_root / relative
        destination = output_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if relative in TARGET_PACK_RELS:
            source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                source_info = os.fstat(source_fd)
                require(stat.S_ISREG(source_info.st_mode), f"target pack is not regular: {source}")
                owned = reserve_file(destination, stat.S_IMODE(source_info.st_mode))
                try:
                    _copy_fd(source_fd, owned.descriptor, source_info.st_size)
                    require(fd_identity(source_fd) != owned.identity, f"target pack remained hard-linked: {relative}")
                    require(sha256_fd(source_fd) == EXPECTED_PACK_SHA256[relative.name], f"source pack {relative.name} SHA-256 mismatch")
                    require(sha256_fd(owned.descriptor) == EXPECTED_PACK_SHA256[relative.name], f"copied pack {relative.name} SHA-256 mismatch")
                except Exception:
                    os.close(owned.descriptor)
                    unlink_if_owned(owned)
                    raise
                owned_packs[relative.name] = owned
                copied += 1
            finally:
                os.close(source_fd)
        else:
            try:
                os.link(source, destination, follow_symlinks=False)
            except FileExistsError as exc:
                raise PatchError(f"output file appeared during clone: {destination}") from exc
            hardlinked += 1
    return {"hardlinked_files": hardlinked, "copied_files": copied}, owned_packs, root_identity


def pwrite_owned(owned: OwnedFile, offset: int, data: bytes) -> None:
    require(owned_path_matches(owned), f"owned output path inode changed: {owned.path}")
    info = os.fstat(owned.descriptor)
    require(0 <= offset <= info.st_size - len(data), "patch write is out of bounds")
    before_size = info.st_size
    written = os.pwrite(owned.descriptor, data, offset)
    require(written == len(data), "short patch write")
    os.fsync(owned.descriptor)
    require(os.fstat(owned.descriptor).st_size == before_size, "patch changed pack size")
    require(os.pread(owned.descriptor, len(data), offset) == data, "patch readback mismatch")
    require(owned_path_matches(owned), f"owned output path inode changed: {owned.path}")


def changed_offsets(source: Path, output: OwnedFile, allowed: set[int]) -> list[int]:
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        source_info = os.fstat(source_fd)
        output_info = os.fstat(output.descriptor)
        require(source_info.st_size == output_info.st_size, "patched pack size differs from retail")
        result: list[int] = []
        offset = 0
        while offset < source_info.st_size:
            size = min(8 * 1024 * 1024, source_info.st_size - offset)
            left = os.pread(source_fd, size, offset)
            right = os.pread(output.descriptor, size, offset)
            require(len(left) == size and len(right) == size, "short diff read")
            for index, (a, b) in enumerate(zip(left, right)):
                if a != b:
                    absolute = offset + index
                    require(absolute in allowed, f"unintended byte change in {output.path.name} at 0x{absolute:x}")
                    result.append(absolute)
            offset += size
        require(result, f"no bytes changed in target pack {output.path.name}")
        return result
    finally:
        os.close(source_fd)


def verify_hardlinks(source_root: Path, output_root: Path, relative_files: Iterable[Path]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for relative in relative_files:
        source_info = (source_root / relative).stat(follow_symlinks=False)
        output_info = (output_root / relative).stat(follow_symlinks=False)
        if relative in TARGET_PACK_RELS:
            require((source_info.st_dev, source_info.st_ino) != (output_info.st_dev, output_info.st_ino), f"writable pack aliases source: {relative}")
        else:
            require((source_info.st_dev, source_info.st_ino) == (output_info.st_dev, output_info.st_ino), f"unrelated file was not hard-linked unchanged: {relative}")
            result.append({"path": str(relative), "size": source_info.st_size, "same_inode": True})
    return result


def build_patch(source_root: Path, output_root: Path, manifest_owned: OwnedFile) -> dict[str, object]:
    relative_files = validate_source_tree(source_root)
    archive = parse_archive(source_root / TESTED_INDEX_REL)
    validated: list[tuple[Target, Entry, bytes]] = []
    for target in TARGETS:
        entry, body = validate_target(archive, target)
        validated.append((target, entry, body))

    clone_stats, owned_packs, root_identity = clone_tree(source_root, output_root, relative_files)
    require(set(owned_packs) == {"A", "B"}, "did not reserve both target packs")
    try:
        allowed_by_pack: dict[str, set[int]] = {"A": set(), "B": set()}
        patch_records: list[dict[str, object]] = []
        for target, entry, body in validated:
            virtual = entry.virtual_offset + COLOR_PAIR_ENTRY_OFFSET
            slices = map_virtual_write(archive, virtual, MAGENTA_PAIR)
            require(len(slices) == 1 and slices[0].pack_name == target.expected_pack, f"{target.logical_name}: unexpected physical mapping")
            for item in slices:
                owned = owned_packs.get(item.pack_name)
                require(owned is not None, f"PORTME: virtual write maps to uncopied pack {item.pack_name}")
                pwrite_owned(owned, item.pack_offset, item.data)
                allowed_by_pack[item.pack_name].update(range(item.pack_offset, item.pack_offset + len(item.data)))
            patch_records.append(
                {
                    "outer_index": target.outer_index,
                    "logical_name": target.logical_name,
                    "name_id": f"0x{target.name_id:08x}",
                    "entry_size": entry.size,
                    "entry_virtual_offset": entry.virtual_offset,
                    "entry_relative_field_offsets": [COLOR_PAIR_ENTRY_OFFSET, COLOR_PAIR_ENTRY_OFFSET + 4],
                    "unif_body_relative_field_offsets": [UNIF_PAYLOAD_OFFSET, UNIF_PAYLOAD_OFFSET + 4],
                    "before": [f"0x{value:08x}" for value in target.expected_colors],
                    "after": [f"0x{MAGENTA_ARGB:08x}", f"0x{MAGENTA_ARGB:08x}"],
                    "physical_slices": [
                        {
                            "pack": item.pack_name,
                            "pack_offset": item.pack_offset,
                            "size": len(item.data),
                            "before_hex": body[UNIF_PAYLOAD_OFFSET:UNIF_PAYLOAD_OFFSET + len(item.data)].hex(),
                            "after_hex": item.data.hex(),
                        }
                        for item in slices
                    ],
                }
            )

        output_archive = parse_archive(output_root / TESTED_INDEX_REL)
        for target in TARGETS:
            entry = output_archive.entries[target.outer_index]
            patched = read_entry_range(output_archive, entry, COLOR_PAIR_ENTRY_OFFSET, len(MAGENTA_PAIR))
            require(patched == MAGENTA_PAIR, f"{target.logical_name}: parser readback is not magenta")

        pack_records: list[dict[str, object]] = []
        for pack_name in ("A", "B"):
            owned = owned_packs[pack_name]
            differences = changed_offsets(source_root / "vc_53450030" / pack_name, owned, allowed_by_pack[pack_name])
            require(owned_path_matches(owned), f"target pack output path inode changed: {owned.path}")
            pack_records.append(
                {
                    "pack": pack_name,
                    "source_sha256": EXPECTED_PACK_SHA256[pack_name],
                    "patched_sha256": sha256_fd(owned.descriptor),
                    "size": os.fstat(owned.descriptor).st_size,
                    "source_output_independent_inodes": True,
                    "allowed_byte_offsets": sorted(allowed_by_pack[pack_name]),
                    "actual_changed_byte_offsets": differences,
                    "no_changes_outside_allowed_offsets": True,
                }
            )

        unrelated = verify_hardlinks(source_root, output_root, relative_files)
        output_root_info = output_root.stat(follow_symlinks=False)
        require(
            {"device": output_root_info.st_dev, "inode": output_root_info.st_ino} == root_identity,
            "output root inode changed during patch",
        )
        manifest: dict[str, object] = {
            "schema": SCHEMA,
            "scope": {
                "title": "ESPN NFL 2K5 (USA)",
                "modification": "Detroit Lions current HOME/AWAY raw Unif color words",
                "new_color_argb": f"0x{MAGENTA_ARGB:08x}",
                "copy_only": True,
                "texture_writer": False,
                "model_writer": False,
            },
            "source": {
                "game_root": str(source_root),
                "expected_original_iso_sha256": EXPECTED_ISO_SHA256,
                "default_xbe_sha256": EXPECTED_XBE_SHA256,
                "archive_index_sha256": EXPECTED_INDEX_SHA256,
                "archive_virtual_size": archive.virtual_size,
                "archive_pack_count": len(archive.packs),
                "archive_entry_count": len(archive.entries),
            },
            "output": {
                "game_root": str(output_root),
                "root_identity": root_identity,
                **clone_stats,
                "target_pack_count": 2,
                "unrelated_file_count": len(unrelated),
            },
            "targets": patch_records,
            "packs": pack_records,
            "unrelated_files": unrelated,
            "validation": {
                "parser_backed_source_validation": True,
                "retail_outer_hashes_match": True,
                "retail_unif_hashes_match": True,
                "source_files_opened_read_only": True,
                "target_outputs_created_exclusively": True,
                "target_output_writes_bound_to_owned_fds": True,
                "target_output_path_inodes_stable": True,
                "target_packs_independent_before_patch": True,
                "patched_tree_reparsed": True,
                "both_color_fields_read_back_magenta": True,
                "only_allowed_pack_byte_offsets_changed": True,
                "all_unrelated_files_hardlinked_unchanged": True,
            },
            "portme": [
                "PORTME: this proof edits two raw packed-color words; it does not identify the exact material/channel each word controls at runtime.",
                "PORTME: this is not a PNG texture importer and does not rewrite TSET/TXTR resources.",
                "PORTME: this is not a general IFF/archive serializer; size-changing edits remain unsupported.",
                "PORTME: opaque magenta is encoded as little-endian ARGB 0xffff00ff based on the proved packed-color consumers; emulator capture is still required to label its visible effect.",
            ],
            "phase_summary": {
                "worked": [
                    "Both retail Lions current-uniform packages were found and validated by ID, size, wrapper/body layout, and SHA-256.",
                    "Only the four proved color fields were overwritten in independent copies of packs A and B.",
                    "Every unrelated extracted-game file is an unchanged hardlink; writable packs are separate inodes.",
                ],
                "failed": [
                    "No PNG, texture, model, or size-changing resource replacement is attempted by this bounded writer."
                ],
                "blocking": [
                    "A runtime emulator capture is needed to prove which visible uniform regions the two packed colors affect."
                ],
            },
        }
        write_owned_json(manifest_owned, manifest)
        return manifest
    finally:
        for owned in owned_packs.values():
            os.close(owned.descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-game-root", type=Path, required=True)
    parser.add_argument("--output-game-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)

    manifest_owned: OwnedFile | None = None
    try:
        source, output, manifest_path = preflight_paths(
            args.source_game_root, args.output_game_root, args.manifest
        )
        manifest_owned = reserve_file(manifest_path)
        result = build_patch(source, output, manifest_owned)
        print(
            "NFL_UNIFORM_COLOR_PATCH_PASS "
            f"targets={len(result['targets'])} copied_packs=2 "
            f"unrelated_files={len(result['unrelated_files'])} "
            f"color=0x{MAGENTA_ARGB:08x}"
        )
        return 0
    except (OSError, PatchError, ValueError) as exc:
        if manifest_owned is not None:
            try:
                unlink_if_owned(manifest_owned)
            except OSError:
                pass
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if manifest_owned is not None:
            os.close(manifest_owned.descriptor)


if __name__ == "__main__":
    raise SystemExit(main())

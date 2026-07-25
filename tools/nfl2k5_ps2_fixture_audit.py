#!/usr/bin/env python3
"""Read-only availability audit for the ESPN NFL 2K5 PS2 evidence lane.

The Xbox and PlayStation 2 releases are different executables and asset
pipelines.  This tool therefore proves only what is locally available for the
PS2 NTSC-U build.  It never copies an Xbox address into a PS2 claim, extracts
disc/save payloads, patches an image, or writes to a PCSX2 profile.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Iterable


def change_time_identity(info: os.stat_result) -> tuple[int, ...]:
    """``(info.st_ctime_ns,)`` on POSIX; ``()`` on Windows.

    Inlined rather than imported from
    :mod:`mod_editor.core.platform_compat` because this module is executed as a
    self-contained, tools-only closure and may not import the editor package;
    the contract is byte-for-byte that helper's.

    On Windows a path stat and an fd stat of the *same, untouched* file do not
    agree on ``st_ctime``, so putting it in an identity tuple refuses a file
    nothing touched.  ``st_dev``/``st_ino`` stay the identity and
    ``st_size``/``st_mtime_ns`` stay the change detectors, so a swapped or
    rewritten file is still caught.  What is genuinely lost on Windows is the
    metadata-only-change signal -- a permission or attribute edit that leaves
    the bytes, the size and the modification time untouched -- and Windows
    offers no equivalent field that is stable across the two calls, so this
    check is weaker there than on POSIX.  Stated, not hidden.
    """

    if sys.platform.startswith("win"):
        return ()
    return (info.st_ctime_ns,)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "nfl2k5_ps2_fixture_audit/v1"
SERIAL = "SLUS-20919"
BOOT_ELF_NAME = "SLUS_209.19"
SAVE_PREFIX = b"BASLUS-20919"
EXPECTED_ISO_SIZE = 4_665_081_856
EXPECTED_ISO_MD5 = "46ef5e7a2e155994e7c3e5627293e068"
EXPECTED_DISC_VERSION = "1.01"

PCSX2_RESOURCE_ROOT = Path(
    "/var/lib/flatpak/app/net.pcsx2.PCSX2/current/active/files/bin/resources"
)
DEFAULT_GAME_INDEX = PCSX2_RESOURCE_ROOT / "GameIndex.yaml"
DEFAULT_REDUMP_DB = PCSX2_RESOURCE_ROOT / "RedumpDatabase.yaml"
EXPECTED_GAME_INDEX_SIZE = 2_662_382
EXPECTED_GAME_INDEX_SHA256 = (
    "bc7d17e87b623f5c36775465be7e94b12c8fac1fc3c90c185d970c3c9e50e77b"
)
EXPECTED_REDUMP_SIZE = 1_898_666
EXPECTED_REDUMP_SHA256 = (
    "aa8ebbc304e332fd9f7f6f71e2904849e23e8100a579537c93f156967a4a2e6d"
)

PCSX2_PROFILE = Path("/home/noah/.var/app/net.pcsx2.PCSX2/config/PCSX2")
DEFAULT_MEMORY_CARDS = (
    PCSX2_PROFILE / "memcards/Mcd001.ps2",
    PCSX2_PROFILE / "memcards/Mcd002.ps2",
)
DEFAULT_TEXTURE_ROOT = PCSX2_PROFILE / "textures"
DEFAULT_SUSPECT_DISCS = (
    ROOT / "ESPN NFL 2K5 (USA).xiso.iso",
    Path(
        "/home/noah/Downloads/ESPN NFL 2K5 (USA)/"
        "ESPN NFL 2K5 (USA).xiso.iso"
    ),
)
DEFAULT_SCAN_ROOTS = (
    ROOT,
    Path("/home/noah/Downloads"),
    Path("/media/noah/12TB HDD/Backups/Emulation/Roms/PCSX2 Games"),
    Path(
        "/media/noah/12TB HDD/Backups/Full Desktop Backup/"
        "Emulation/Roms/PCSX2 Games"
    ),
    Path(
        "/media/noah/12TB HDD/Backups/Old 2012 Flash Drive Backup/"
        "Emulation/ISOs/PS2"
    ),
    Path("/media/noah/12TB HDD/Backups/Rom Archive/PlayStation 2"),
)
DEFAULT_JSON = (
    ROOT / "reports/gameplay_tuning/nfl2k5_ps2_fixture_availability.json"
)

MEMORY_CARD_MAGIC = b"Sony PS2 Memory Card Format 1.2.0.0\x00"
XDVDFS_MAGIC = b"MICROSOFT*XBOX*MEDIA"


class FixtureAuditError(ValueError):
    """A pinned source or recovered invariant differs."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureAuditError(message)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def hash_regular_file(
    path: Path,
    *,
    algorithms: tuple[str, ...] = ("sha256",),
    expected_size: int | None = None,
) -> tuple[int, dict[str, str]]:
    """Hash a stable non-symlink file through an O_RDONLY descriptor."""

    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
            f"not a non-symlink regular file: {path}")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode), f"not regular after open: {path}")
        require((opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
                f"identity changed before open: {path}")
        if expected_size is not None:
            require(opened.st_size == expected_size, f"size differs: {path}")
        digests = {name: hashlib.new(name) for name in algorithms}
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(16 * 1024 * 1024, remaining))
            require(bool(chunk), f"short read: {path}")
            for digest in digests.values():
                digest.update(chunk)
            remaining -= len(chunk)
        require(not os.read(descriptor, 1), f"file grew while hashing: {path}")
        after = os.fstat(descriptor)
        require(
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
             *change_time_identity(after))
            == (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns,
                *change_time_identity(opened)),
            f"file changed while hashing: {path}",
        )
        return opened.st_size, {
            name: digest.hexdigest() for name, digest in digests.items()
        }
    finally:
        os.close(descriptor)


def read_pinned_text(
    path: Path, expected_size: int, expected_sha256: str, label: str
) -> tuple[str, dict[str, Any]]:
    size, hashes = hash_regular_file(path, expected_size=expected_size)
    require(hashes["sha256"] == expected_sha256, f"{label} SHA-256 differs")
    # The identity was pinned above.  A second bounded read is acceptable for
    # these small, immutable packaged resources.
    payload = path.read_bytes()
    require(len(payload) == size, f"{label} changed after hashing")
    return payload.decode("utf-8"), {
        "path": str(path),
        "sha256": hashes["sha256"],
        "size": size,
    }


def parse_game_index(text: str) -> dict[str, Any]:
    match = re.search(
        rf"(?m)^{re.escape(SERIAL)}:\n"
        r"  name: \"(?P<name>[^\"]+)\"\n"
        r"  region: \"(?P<region>[^\"]+)\"\n"
        r"  compat: (?P<compat>[0-9]+)(?:\n|$)",
        text,
    )
    require(match is not None, f"{SERIAL} missing from PCSX2 GameIndex")
    return {
        "compat": int(match.group("compat")),
        "name": match.group("name"),
        "region": match.group("region"),
        "serial": SERIAL,
    }


def parse_redump_database(text: str) -> dict[str, Any]:
    pattern = re.compile(
        r"(?m)^- hashes:\n"
        r"  - md5: (?P<md5>[0-9a-f]{32})\n"
        r"    size: (?P<size>[0-9]+)\n"
        r"  name: (?P<name>ESPN NFL 2K5 \(USA\))\n"
        rf"  serial: {re.escape(SERIAL)}\n"
        r"  version: '(?P<version>[^']+)'(?:\n|$)"
    )
    match = pattern.search(text)
    require(match is not None, "NTSC-U ESPN NFL 2K5 missing from Redump database")
    result = {
        "md5": match.group("md5"),
        "name": match.group("name"),
        "serial": SERIAL,
        "size": int(match.group("size")),
        "version": match.group("version"),
    }
    require(result["md5"] == EXPECTED_ISO_MD5, "Redump MD5 invariant differs")
    require(result["size"] == EXPECTED_ISO_SIZE, "Redump size invariant differs")
    require(result["version"] == EXPECTED_DISC_VERSION,
            "Redump version invariant differs")
    return result


def read_at(path: Path, offset: int, size: int) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.lseek(descriptor, offset, os.SEEK_SET)
        return os.read(descriptor, size)
    finally:
        os.close(descriptor)


def classify_disc_header(path: Path) -> str:
    size = path.stat().st_size
    if size >= 0x10000 + len(XDVDFS_MAGIC):
        if read_at(path, 0x10000, len(XDVDFS_MAGIC)) == XDVDFS_MAGIC:
            return "xdvdfs_xbox"
    if size >= 0x8001 + 5 and read_at(path, 0x8001, 5) == b"CD001":
        return "iso9660"
    return "unknown"


def inspect_suspect_disc(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
            f"disc suspect is not a non-symlink regular file: {path}")
    classification = classify_disc_header(path)
    after = path.lstat()
    require(
        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
         *change_time_identity(after))
        == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
            *change_time_identity(before)),
        f"disc suspect changed during header inspection: {path}",
    )
    return {
        "accepted_as_target_ps2_disc": False,
        "classification": classification,
        "exists": True,
        "path": str(path),
        "reason": (
            "Xbox XDVDFS image, not a PS2 disc"
            if classification == "xdvdfs_xbox"
            else "does not satisfy the pinned PS2 disc identity"
        ),
        "size": before.st_size,
    }


def walk_regular_files(roots: Iterable[Path]) -> Iterable[Path]:
    """Yield regular files without following symlinked directories."""

    seen: set[tuple[int, int]] = set()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            candidates = (root,)
        else:
            def onerror(error: OSError) -> None:
                raise FixtureAuditError(f"scan failed: {error}")
            candidates = (
                Path(directory) / filename
                for directory, _directories, filenames in os.walk(
                    root, followlinks=False, onerror=onerror
                )
                for filename in filenames
            )
        for path in candidates:
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                continue
            identity = (info.st_dev, info.st_ino)
            if identity in seen:
                continue
            seen.add(identity)
            yield path


def scan_for_fixtures(roots: tuple[Path, ...]) -> dict[str, Any]:
    exact_size: list[dict[str, Any]] = []
    elf_candidates: list[dict[str, Any]] = []
    loose_save_candidates: list[dict[str, Any]] = []
    elf_names = {BOOT_ELF_NAME.lower(), f"{SERIAL.lower()}.elf"}
    for path in walk_regular_files(roots):
        info = path.lstat()
        lowered = path.name.lower()
        if info.st_size == EXPECTED_ISO_SIZE:
            size, hashes = hash_regular_file(
                path,
                algorithms=("md5", "sha256"),
                expected_size=EXPECTED_ISO_SIZE,
            )
            exact_size.append({
                "accepted": hashes["md5"] == EXPECTED_ISO_MD5,
                "md5": hashes["md5"],
                "path": str(path),
                "sha256": hashes["sha256"],
                "size": size,
            })
        if lowered in elf_names or (
            "slus" in lowered and "20919" in lowered.replace("-", "").replace("_", "")
        ):
            size, hashes = hash_regular_file(path)
            elf_candidates.append({
                "path": str(path), "sha256": hashes["sha256"], "size": size
            })
        if lowered.startswith("baslus-20919"):
            size, hashes = hash_regular_file(path)
            loose_save_candidates.append({
                "path": str(path), "sha256": hashes["sha256"], "size": size
            })
    return {
        "exact_size_disc_candidates": sorted(exact_size, key=lambda row: row["path"]),
        "extracted_elf_candidates": sorted(elf_candidates, key=lambda row: row["path"]),
        "loose_save_candidates": sorted(
            loose_save_candidates, key=lambda row: row["path"]
        ),
        "roots": [str(path) for path in roots],
    }


def memory_card_names(payload: bytes) -> list[str]:
    """Inventory BASLUS strings without exporting any save payload bytes."""

    names: set[str] = set()
    for match in re.finditer(rb"BASLUS-[\x20-\x7e]{1,25}", payload):
        raw = match.group(0)
        # Directory names end at a NUL/non-printable byte.  The bounded regex
        # may include printable slack, so trim at a known 32-byte PS2 name cap.
        names.add(raw[:32].decode("ascii"))
    return sorted(names)


def inspect_memory_card(path: Path) -> dict[str, Any]:
    size, hashes = hash_regular_file(path)
    payload = path.read_bytes()
    require(len(payload) == size, f"memory card changed after hashing: {path}")
    require(payload.startswith(MEMORY_CARD_MAGIC), f"memory-card magic differs: {path}")
    names = memory_card_names(payload)
    marker_offsets: list[int] = []
    cursor = 0
    while True:
        offset = payload.find(SAVE_PREFIX, cursor)
        if offset < 0:
            break
        marker_offsets.append(offset)
        cursor = offset + 1
    return {
        "format_magic": MEMORY_CARD_MAGIC[:-1].decode("ascii"),
        "nfl2k5_marker_occurrence_count": len(marker_offsets),
        "path": str(path),
        "save_directory_markers": names,
        "sha256": hashes["sha256"],
        "size": size,
    }


def inspect_texture_root(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "regular_file_count": 0}
    require(path.is_dir() and not path.is_symlink(),
            "PCSX2 texture root must be a non-symlink directory")
    files = sorted(
        str(candidate.relative_to(path))
        for candidate in path.rglob("*")
        if candidate.is_file() and not candidate.is_symlink()
    )
    target_files = [name for name in files if SERIAL.lower() in name.lower()]
    return {
        "exists": True,
        "path": str(path),
        "regular_file_count": len(files),
        "target_serial_file_count": len(target_files),
        "target_serial_files": target_files,
    }


def limitation_rows() -> list[dict[str, Any]]:
    common = {
        "address_reuse_from_xbox_allowed": False,
        "ps2_owner_status": "unmapped_no_verified_ps2_elf_or_save_fixture",
        "safe_ps2_patch_ready": False,
    }
    return [
        {
            **common,
            "id": "draft_trade_logic",
            "xbox_comparator_only": (
                "Xbox evidence separates a 17-position fantasy-draft priority "
                "surface from still-unmapped trade valuation. This is only a "
                "PS2 search hypothesis, not shared code ownership."
            ),
            "required_ps2_evidence": (
                "Hash-pinned MIPS ELF plus controlled fantasy-draft and trade "
                "save/runtime deltas."
            ),
        },
        {
            **common,
            "id": "salary_cap_contracts",
            "xbox_comparator_only": (
                "Xbox has a mapped cap-enforcement gate, while contract "
                "encoding and negotiation remain unresolved. No PS2 semantic "
                "or address follows from that result."
            ),
            "required_ps2_evidence": (
                "Hash-pinned MIPS ELF plus one-field-at-a-time salary, years, "
                "bonus, penalty, and cap-state save pairs."
            ),
        },
        {
            **common,
            "id": "super_bowl_future_stadium",
            "xbox_comparator_only": (
                "Xbox selects five explicit future venues and then a fallback. "
                "The PS2 branch/table shape is unknown until independently "
                "recovered from its MIPS ELF."
            ),
            "required_ps2_evidence": (
                "Hash-pinned MIPS ELF plus copied franchise saves or traces for "
                "Super Bowl indices 0 through at least 6."
            ),
        },
        {
            **common,
            "id": "shared_team_textures",
            "xbox_comparator_only": (
                "Xbox native asset spans and PCSX2 replacement hashes are "
                "different mechanisms. PS2 sharing must be established from "
                "its disc selectors and GS texture dumps."
            ),
            "required_ps2_evidence": (
                "Verified PS2 disc/ELF, per-team uniform selector joins, and "
                "controlled PCSX2 GS dumps for identical uniform slots."
            ),
        },
    ]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    game_text, game_source = read_pinned_text(
        args.game_index,
        EXPECTED_GAME_INDEX_SIZE,
        EXPECTED_GAME_INDEX_SHA256,
        "PCSX2 GameIndex",
    )
    redump_text, redump_source = read_pinned_text(
        args.redump_database,
        EXPECTED_REDUMP_SIZE,
        EXPECTED_REDUMP_SHA256,
        "PCSX2 Redump database",
    )
    game = parse_game_index(game_text)
    redump = parse_redump_database(redump_text)
    scan = scan_for_fixtures(tuple(args.scan_root))
    exact_verified = [
        row for row in scan["exact_size_disc_candidates"] if row["accepted"]
    ]
    cards = [inspect_memory_card(path) for path in args.memory_card if path.exists()]
    texture = inspect_texture_root(args.texture_root)
    rejected = [inspect_suspect_disc(path) for path in args.suspect_disc]
    rejected = [row for row in rejected if row["exists"]]
    save_marker_count = sum(
        row["nfl2k5_marker_occurrence_count"] for row in cards
    )
    limitations = limitation_rows()
    return {
        "limitations": limitations,
        "local_evidence": {
            "memory_cards": cards,
            "pcsx2_texture_root": texture,
            "rejected_named_disc_suspects": rejected,
            "scan": scan,
        },
        "scope": {
            "disc_or_save_payload_bytes_emitted": False,
            "elf_decompilation_performed": False,
            "read_only_source_access": True,
            "retail_or_emulator_source_modified": False,
            "xbox_addresses_reused": False,
        },
        "schema": SCHEMA,
        "source_authorities": {
            "pcsx2_game_index": {**game_source, "entry": game},
            "pcsx2_redump_database": {**redump_source, "entry": redump},
        },
        "summary": {
            "all_four_ps2_owners_mapped": False,
            "expected_iso_present": bool(exact_verified),
            "extracted_boot_elf_present": bool(scan["extracted_elf_candidates"]),
            "memory_card_count": len(cards),
            "pcsx2_texture_dump_present": texture.get("target_serial_file_count", 0) > 0,
            "safe_ps2_patch_ready": False,
            "save_directory_marker_present": save_marker_count > 0,
            "serial": SERIAL,
        },
        "target": {
            "boot_elf_expected_name": BOOT_ELF_NAME,
            "disc_version": EXPECTED_DISC_VERSION,
            "expected_iso_md5": EXPECTED_ISO_MD5,
            "expected_iso_size": EXPECTED_ISO_SIZE,
            "platform": "PlayStation 2",
            "region": "NTSC-U",
            "serial": SERIAL,
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--game-index", type=Path, default=DEFAULT_GAME_INDEX)
    result.add_argument("--redump-database", type=Path, default=DEFAULT_REDUMP_DB)
    result.add_argument(
        "--memory-card", action="append", type=Path, default=None,
        help="raw PCSX2 memory card to inspect; repeatable",
    )
    result.add_argument(
        "--texture-root", type=Path, default=DEFAULT_TEXTURE_ROOT,
        help="PCSX2 texture root to inventory without changing settings",
    )
    result.add_argument(
        "--suspect-disc", action="append", type=Path, default=None,
        help="named disc suspect to classify by header; repeatable",
    )
    result.add_argument(
        "--scan-root", action="append", type=Path, default=None,
        help="root searched for exact-size discs, boot ELF, and loose save; repeatable",
    )
    result.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.memory_card is None:
        args.memory_card = list(DEFAULT_MEMORY_CARDS)
    if args.suspect_disc is None:
        args.suspect_disc = list(DEFAULT_SUSPECT_DISCS)
    if args.scan_root is None:
        args.scan_root = list(DEFAULT_SCAN_ROOTS)
    report = build_report(args)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_bytes(canonical_json(report))
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

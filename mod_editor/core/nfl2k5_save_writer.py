"""Save/slider/franchise writer trio for NFL 2K5 (local-only, uncommitted).

Productizes three proven research lanes into one fail-closed editor module:

* A1 -- the settings slider block.  Settings1/SAVEGAME.DAT (STG, 736 bytes)
  and the first 0x2E0 bytes of Franchise1/SAVEGAME.DAT are verbatim images of
  RAM 0xE5FF80..0xE60260.  21 gameplay sliders live there: Human/CPU
  Blocking..Catching (editable + mirror copies), Injury, Fumble,
  Interception.  "consistent" edits update both the editable and mirror
  copies, matching the game's sync state machine.
* A4 -- save signing.  Every container's EXTRA file equals
  HMAC-SHA1(SigKey16, SAVEGAME.DAT) with SigKey16 derived from the retail XBE
  certificate key and the published Xbox master key (title-static, public by
  construction; mode-0 XCalculateSignature skips the per-console HDKey path).
  Saves are resignable offline and are NOT console-bound.
* A7 -- franchise fields.  Franchise1/SAVEGAME.DAT is 720,044 bytes; the
  state block at 0x91320 carries the mode bytes, a season ordinal (u16,
  +0x91324) and a year field (u16, +0x91326).  Runtime triple A_PROVEN:
  year 7->8 was accepted in-game after resign and displayed franchise year
  advanced by one (displayed year = 2004 + field, B_INFERENCE); a stale
  EXTRA was rejected, proving the HMAC is enforced at load.

All operations are copy-only: loose-file edits refuse to overwrite and ask
for fresh target paths; HDD write-back refuses same-file source/target and
only pwrites the container's own extents.  Saves whose stored EXTRA does not
verify are refused (we will not edit what we cannot re-sign honestly).

FATX support is ported from the A4 research tool (attachments/A4).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
import stat
import struct
from pathlib import Path

from . import platform_compat

XBE_MAGIC = b"XBEH"
MASTER_XBOX_KEY = bytes.fromhex("5C0733AE0401F7E8BA7993FDCD2F1FE0")

SETTINGS_SAVE_SIZE = 736
SETTINGS_BLOCK_SIZE = 0x2E0
FRANCHISE_SAVE_SIZE = 720044
FRANCHISE_STATE_OFFSET = 0x91320
FRANCHISE_SEASON_ORDINAL_OFFSET = 0x91324
FRANCHISE_YEAR_OFFSET = 0x91326
FRANCHISE_DISPLAY_YEAR_BASE = 2004  # B_INFERENCE (A7 entry 12)

SLIDER_ORDER = (
    "Blocking", "Passing", "Running", "Coverage", "Pursuit",
    "Tackling", "Kicking", "Fatigue", "Catching",
)
EDITABLE_HUMAN_BASE = 0x154
EDITABLE_CPU_BASE = 0x178
MIRROR_CPU_BASE = 0x298
MIRROR_HUMAN_BASE = 0x2BC
SPECIAL_SLIDERS = {"Injury": 0x284, "Fumble": 0x288, "Interception": 0x28C}
SLIDER_LABELS = tuple(
    [f"Human {name}" for name in SLIDER_ORDER]
    + [f"CPU {name}" for name in SLIDER_ORDER]
    + list(SPECIAL_SLIDERS)
)
SLIDER_MODES = ("editable", "mirror", "consistent")

READ_SCHEMA = "nfl2k5_save_read/v1"
EDIT_SCHEMA = "nfl2k5_save_edit/v1"
WRITEBACK_SCHEMA = "nfl2k5_save_writeback/v1"

FATX_SIGNATURE = 0x58544146
FATX_PAGE_SIZE = 0x1000
FATX_SECTOR_SIZE = 0x200
FILE_ATTRIBUTE_DIRECTORY = 0x10
DIRENT_DELETED = 0xE5
DIRENT_END = {0x00, 0xFF}
DIRENT_SIZE = 0x40
FATX_PARTITIONS = {
    "X": (0x00080000, 0x2EE00000),
    "Y": (0x2EE80000, 0x2EE00000),
    "Z": (0x5DC80000, 0x2EE00000),
    "C": (0x8CA80000, 0x1F400000),
    "E": (0xABE80000, 0x1312D6000),
}
SAVEGAME_NAME = "SAVEGAME.DAT"
EXTRA_NAME = "EXTRA"


class SaveWriterError(ValueError):
    """Raised when a save, signature, or write fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SaveWriterError(message)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _regular_non_link(path: Path) -> os.stat_result:
    resolved = path.expanduser().resolve(strict=True)
    info = resolved.lstat()
    _require(stat.S_ISREG(info.st_mode), f"not a regular file: {resolved}")
    return info


def _refuse_same_file(source: Path, target: Path) -> None:
    _require(
        str(source.resolve()) != str(target.resolve()),
        "source and target are the same path; the target must be a copy",
    )
    source_info = source.lstat()
    target_info = target.lstat()
    _require(
        (source_info.st_dev, source_info.st_ino)
        != (target_info.st_dev, target_info.st_ino),
        "source and target are the same file; the target must be a copy",
    )


# ---------------------------------------------------------------------------
# A4: signing
# ---------------------------------------------------------------------------

def xbe_cert_sig_key(xbe_payload: bytes) -> bytes:
    _require(xbe_payload[:4] == XBE_MAGIC, "file is not an XBE (missing XBEH)")
    base = struct.unpack_from("<I", xbe_payload, 260)[0]
    cert = struct.unpack_from("<I", xbe_payload, 280)[0]
    _require(cert >= base, "XBE certificate precedes the image base")
    location = cert - base
    _require(location + 208 <= len(xbe_payload),
             "XBE certificate region is truncated")
    return xbe_payload[location + 192 : location + 208]


def derive_sig_key(xbe_payload: bytes) -> bytes:
    """SigKey16 = HMAC-SHA1(MASTER_XBOX_KEY, cert sig key)[:16] (A_PROVEN)."""

    return hmac.new(MASTER_XBOX_KEY, xbe_cert_sig_key(xbe_payload),
                    hashlib.sha1).digest()[:16]


def sign_save(sig_key: bytes, savegame: bytes) -> bytes:
    return hmac.new(sig_key, savegame, hashlib.sha1).digest()


def verify_extra(sig_key: bytes, savegame: bytes, extra: bytes) -> bool:
    return len(extra) == 20 and sign_save(sig_key, savegame) == extra


# ---------------------------------------------------------------------------
# A1: sliders
# ---------------------------------------------------------------------------

def slider_offsets(label: str) -> dict[str, int]:
    """Region -> settings-block offset for one of the 21 sliders."""

    if label in SPECIAL_SLIDERS:
        return {"editable": SPECIAL_SLIDERS[label]}
    if label.startswith("Human "):
        index = SLIDER_ORDER.index(label.split(" ", 1)[1])
        return {
            "editable": EDITABLE_HUMAN_BASE + 4 * index,
            "mirror": MIRROR_HUMAN_BASE + 4 * index,
        }
    if label.startswith("CPU "):
        index = SLIDER_ORDER.index(label.split(" ", 1)[1])
        return {
            "editable": EDITABLE_CPU_BASE + 4 * index,
            "mirror": MIRROR_CPU_BASE + 4 * index,
        }
    raise SaveWriterError(
        f"unknown slider {label!r}; expected one of {len(SLIDER_LABELS)}"
    )


def _read_slider_values(payload: bytes) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = {}
    for label in SLIDER_LABELS:
        regions = {}
        for region, offset in slider_offsets(label).items():
            regions[region] = struct.unpack_from("<f", payload, offset)[0]
        values[label] = regions
    return values


def apply_slider_edits(
    payload: bytearray,
    edits: dict[str, float],
    *,
    mode: str,
) -> list[dict[str, object]]:
    _require(mode in SLIDER_MODES, f"unknown slider mode {mode!r}")
    _require(len(payload) >= SETTINGS_BLOCK_SIZE,
             "save is smaller than the 0x2E0 settings block")
    changes: list[dict[str, object]] = []
    for label, value in edits.items():
        _require(label in SLIDER_LABELS, f"unknown slider {label!r}")
        value = float(value)
        _require(value == value and float("-inf") < value < float("inf"),
                 f"{label} must be a finite float")
        _require(0.0 <= value <= 1.0,
                 f"{label}={value} is outside the 0.0..1.0 slider range")
        for region, offset in slider_offsets(label).items():
            if mode == "editable" and region != "editable":
                continue
            if mode == "mirror" and region != "mirror":
                continue
            old = struct.unpack_from("<f", payload, offset)[0]
            struct.pack_into("<f", payload, offset, value)
            changes.append(
                {
                    "slider": label,
                    "region": region,
                    "offset": f"0x{offset:x}",
                    "old": old,
                    "new": value,
                }
            )
    return changes


# ---------------------------------------------------------------------------
# A7: franchise fields
# ---------------------------------------------------------------------------

def save_kind(payload: bytes) -> str:
    if len(payload) == SETTINGS_SAVE_SIZE:
        return "settings"
    if len(payload) == FRANCHISE_SAVE_SIZE:
        return "franchise"
    return "unknown"


def read_franchise_fields(payload: bytes) -> dict[str, object]:
    _require(len(payload) == FRANCHISE_SAVE_SIZE,
             "save is not a 720,044-byte Franchise1 SAVEGAME.DAT")
    state = payload[FRANCHISE_STATE_OFFSET : FRANCHISE_STATE_OFFSET + 4]
    season_ordinal = struct.unpack_from(
        "<H", payload, FRANCHISE_SEASON_ORDINAL_OFFSET
    )[0]
    year_field = struct.unpack_from("<H", payload, FRANCHISE_YEAR_OFFSET)[0]
    return {
        "state_bytes": state.hex(),
        "season_ordinal": season_ordinal,
        "year_field": year_field,
        "display_year": FRANCHISE_DISPLAY_YEAR_BASE + year_field,
        "display_year_grade": "B_INFERENCE (A7 entry 12)",
    }


def apply_franchise_year(payload: bytearray, display_year: int) -> dict[str, object]:
    _require(len(payload) == FRANCHISE_SAVE_SIZE,
             "save is not a 720,044-byte Franchise1 SAVEGAME.DAT")
    _require(isinstance(display_year, int), "franchise year must be an int")
    field = display_year - FRANCHISE_DISPLAY_YEAR_BASE
    _require(0 <= field <= 60,
             f"franchise display year {display_year} implies field {field}; "
             "expected 0..60 (30-season wall at 0x1E is separate)")
    old_field = struct.unpack_from("<H", payload, FRANCHISE_YEAR_OFFSET)[0]
    _require(old_field != field,
             f"franchise year already equals {display_year}")
    struct.pack_into("<H", payload, FRANCHISE_YEAR_OFFSET, field)
    return {
        "offset": f"0x{FRANCHISE_YEAR_OFFSET:x}",
        "old_year_field": old_field,
        "new_year_field": field,
        "old_display_year": FRANCHISE_DISPLAY_YEAR_BASE + old_field,
        "new_display_year": display_year,
    }


# ---------------------------------------------------------------------------
# Loose-file read/edit (A1 + A4 + A7)
# ---------------------------------------------------------------------------

def read_save(savegame_path: Path | str) -> dict[str, object]:
    path = Path(savegame_path).expanduser().resolve(strict=True)
    _regular_non_link(path)
    payload = path.read_bytes()
    kind = save_kind(payload)
    result: dict[str, object] = {
        "schema": READ_SCHEMA,
        "path": str(path),
        "sha256": _digest(payload),
        "size": len(payload),
        "kind": kind,
        "sliders": _read_slider_values(payload)
        if len(payload) >= SETTINGS_BLOCK_SIZE
        else {},
    }
    if kind == "franchise":
        result["franchise"] = read_franchise_fields(payload)
    return result


def edit_save_file(
    source_dat: Path | str,
    target_dat: Path | str,
    target_extra: Path | str,
    *,
    xbe_path: Path | str,
    sliders: dict[str, float] | None = None,
    slider_mode: str = "consistent",
    franchise_year: int | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    """Edit a loose SAVEGAME.DAT copy and emit a fresh 20-byte EXTRA.

    Targets must not exist unless ``overwrite=True``; a target that IS the
    source is always refused.
    """

    source = Path(source_dat).expanduser().resolve(strict=True)
    target = Path(target_dat).expanduser()
    extra_target = Path(target_extra).expanduser()
    source_info = _regular_non_link(source)
    for candidate in (target, extra_target):
        if not candidate.exists():
            continue
        _require(overwrite,
                 f"target already exists; pass overwrite=True to replace it: "
                 f"{candidate}")
        candidate_info = candidate.lstat()
        _require(
            (source_info.st_dev, source_info.st_ino)
            != (candidate_info.st_dev, candidate_info.st_ino),
            "source and target are the same file; the target must be a copy",
        )
        _require(stat.S_ISREG(candidate_info.st_mode),
                 f"target is not a regular file: {candidate}")
        candidate.unlink()
    payload = bytearray(source.read_bytes())
    kind = save_kind(bytes(payload))
    _require(kind in ("settings", "franchise"),
             f"save size {len(payload)} is neither Settings1 (736) nor "
             "Franchise1 (720,044)")

    slider_changes = apply_slider_edits(
        payload, dict(sliders or {}), mode=slider_mode
    )
    year_change = None
    if franchise_year is not None:
        year_change = apply_franchise_year(payload, franchise_year)
    _require(bool(slider_changes) or year_change is not None,
             "no edits were requested")

    xbe_payload = Path(xbe_path).expanduser().resolve(strict=True).read_bytes()
    sig_key = derive_sig_key(xbe_payload)
    extra = sign_save(sig_key, bytes(payload))

    target.parent.mkdir(parents=True, exist_ok=True)
    extra_target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bytes(payload))
    extra_target.write_bytes(extra)
    return {
        "schema": EDIT_SCHEMA,
        "source": {"path": str(source), "sha256": _digest(source.read_bytes()),
                   "kind": kind},
        "target": {"path": str(target), "sha256": _digest(bytes(payload)),
                   "kind": kind},
        "extra": {"path": str(extra_target), "sha256": _digest(extra),
                  "mac": extra.hex()},
        "slider_mode": slider_mode,
        "slider_changes": slider_changes,
        "franchise_year_change": year_change,
        "signature": "HMAC-SHA1(SigKey16, SAVEGAME.DAT), title-static (A4)",
    }


# ---------------------------------------------------------------------------
# FATX container write-back (ported from the A4 research tool)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _Dirent:
    name: str
    attributes: int
    first_cluster: int
    file_size: int
    dirent_offset: int

    @property
    def is_directory(self) -> bool:
        return bool(self.attributes & FILE_ATTRIBUTE_DIRECTORY)


class _FatXVolume:
    """Minimal FATX reader over one descriptor (A4 scheme)."""

    def __init__(self, descriptor: int, offset: int, length: int) -> None:
        self.descriptor = descriptor
        self.offset = offset
        self.length = length
        header = self._pread(offset, 16)
        signature, self.serial, sectors_per_cluster, self.root_cluster = (
            struct.unpack("<LLLL", header)
        )
        _require(signature == FATX_SIGNATURE,
                 f"bad FATX signature at 0x{offset:x}: 0x{signature:08x}")
        self.bytes_per_cluster = sectors_per_cluster * FATX_SECTOR_SIZE
        self.max_clusters = (length // self.bytes_per_cluster) + 1
        self.fat16 = self.max_clusters < 0xFFF0
        entry_size = 2 if self.fat16 else 4
        fat_size = self.max_clusters * entry_size
        fat_size = (fat_size + FATX_PAGE_SIZE - 1) & ~(FATX_PAGE_SIZE - 1)
        self.fat_offset = FATX_PAGE_SIZE
        self.file_area_offset = self.fat_offset + fat_size
        fat_bytes = self._pread(offset + self.fat_offset,
                                self.max_clusters * entry_size)
        code = "H" if self.fat16 else "L"
        self.fat = struct.unpack(f"<{self.max_clusters}{code}", fat_bytes)

    def _pread(self, offset: int, size: int) -> bytes:
        data = platform_compat.pread(self.descriptor, size, offset)
        _require(len(data) == size,
                 f"short read at 0x{offset:x} ({len(data)}/{size})")
        return data

    def cluster_offset(self, cluster: int) -> int:
        return (self.offset + self.file_area_offset
                + self.bytes_per_cluster * (cluster - 1))

    def cluster_chain(self, first: int) -> list[int]:
        chain: list[int] = []
        current = first
        seen: set[int] = set()
        reserved = 0xFFF0 if self.fat16 else 0xFFFFFFF0
        while True:
            _require(current not in seen, "FATX cluster loop")
            _require(1 <= current < self.max_clusters,
                     f"FATX cluster out of range {current}")
            seen.add(current)
            chain.append(current)
            nxt = self.fat[current]
            if nxt >= reserved:
                return chain
            _require(nxt != 0, "unexpected free cluster in chain")
            current = nxt

    def read_directory(self, first_cluster: int) -> list[_Dirent]:
        entries: list[_Dirent] = []
        for cluster in self.cluster_chain(first_cluster):
            base = self.cluster_offset(cluster)
            data = self._pread(base, self.bytes_per_cluster)
            for relative in range(0, self.bytes_per_cluster, DIRENT_SIZE):
                raw = data[relative : relative + DIRENT_SIZE]
                name_length, attributes, name_raw, first, size, *_ = (
                    struct.unpack("<BB42sLLLLL", raw)
                )
                if name_length in DIRENT_END:
                    return entries
                if name_length == DIRENT_DELETED:
                    continue
                _require(1 <= name_length <= 42, "bad FATX name length")
                name = name_raw[:name_length].decode("ascii", "replace")
                entries.append(
                    _Dirent(name, attributes, first, size, base + relative)
                )
        return entries

    def resolve(self, components: tuple[str, ...]) -> _Dirent | None:
        entries = self.read_directory(self.root_cluster)
        current: _Dirent | None = None
        for component in components:
            nxt = None
            for entry in entries:
                if entry.name.casefold() == component.casefold():
                    nxt = entry
                    break
            if nxt is None:
                return None
            current = nxt
            if nxt.is_directory:
                entries = self.read_directory(nxt.first_cluster)
        return current

    def file_extents(self, entry: _Dirent) -> list[tuple[int, int]]:
        chain = self.cluster_chain(entry.first_cluster)
        remaining = entry.file_size
        extents: list[tuple[int, int]] = []
        for cluster in chain:
            if remaining <= 0:
                break
            count = min(self.bytes_per_cluster, remaining)
            extents.append((self.cluster_offset(cluster), count))
            remaining -= count
        return extents

    def read_file(self, entry: _Dirent) -> bytes:
        parts = []
        remaining = entry.file_size
        for offset, count in self.file_extents(entry):
            parts.append(self._pread(offset, min(count, remaining)))
            remaining -= count
        return b"".join(parts)[: entry.file_size]


def _open_volume(image_path: Path, partition: str, *, writable: bool):
    _require(partition in FATX_PARTITIONS,
             f"unknown FATX partition {partition!r}")
    offset, length = FATX_PARTITIONS[partition]
    info = _regular_non_link(image_path)
    _require(info.st_size > offset,
             f"image is too small to contain partition {partition}")
    length = min(length, info.st_size - offset)
    flags = os.O_RDWR if writable else os.O_RDONLY
    descriptor = os.open(
        image_path, flags | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        volume = _FatXVolume(descriptor, offset, length)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, volume


def write_back_to_hdd(
    source_hdd: Path | str,
    target_hdd: Path | str,
    *,
    container: tuple[str, ...],
    xbe_path: Path | str,
    sliders: dict[str, float] | None = None,
    slider_mode: str = "consistent",
    franchise_year: int | None = None,
    partition: str = "E",
) -> dict[str, object]:
    """Edit a save inside a COPIED raw Xbox HDD image, extents-only."""

    source = Path(source_hdd).expanduser().resolve(strict=True)
    target = Path(target_hdd).expanduser().resolve(strict=True)
    _regular_non_link(source)
    _regular_non_link(target)
    _refuse_same_file(source, target)
    xbe_payload = Path(xbe_path).expanduser().resolve(strict=True).read_bytes()
    sig_key = derive_sig_key(xbe_payload)

    source_descriptor, source_volume = _open_volume(
        source, partition, writable=False
    )
    try:
        components = tuple(container) + (SAVEGAME_NAME,)
        save_entry = source_volume.resolve(components)
        _require(save_entry is not None,
                 f"no {SAVEGAME_NAME} in container {'/'.join(container)}")
        assert save_entry is not None
        extra_entry = source_volume.resolve(tuple(container) + (EXTRA_NAME,))
        _require(extra_entry is not None,
                 f"no {EXTRA_NAME} in container {'/'.join(container)}")
        assert extra_entry is not None
        savegame = source_volume.read_file(save_entry)
        stored_extra = source_volume.read_file(extra_entry)
        _require(
            verify_extra(sig_key, savegame, stored_extra),
            "stored EXTRA does not verify against this save; refusing to "
            "edit a save we cannot honestly re-sign",
        )
        payload = bytearray(savegame)
        kind = save_kind(bytes(payload))
        slider_changes = apply_slider_edits(
            payload, dict(sliders or {}), mode=slider_mode
        )
        year_change = None
        if franchise_year is not None:
            year_change = apply_franchise_year(payload, franchise_year)
        _require(bool(slider_changes) or year_change is not None,
                 "no edits were requested")
        _require(len(payload) == save_entry.file_size,
                 "edit changed the save size; containers are fixed-size")
        new_extra = sign_save(sig_key, bytes(payload))
        save_extents = source_volume.file_extents(save_entry)
        extra_extents = source_volume.file_extents(extra_entry)
    finally:
        os.close(source_descriptor)

    target_descriptor, target_volume = _open_volume(
        target, partition, writable=True
    )
    try:
        target_save = target_volume.resolve(tuple(container) + (SAVEGAME_NAME,))
        target_extra = target_volume.resolve(tuple(container) + (EXTRA_NAME,))
        _require(target_save is not None and target_extra is not None,
                 "target image lacks the container files")
        assert target_save is not None and target_extra is not None
        _require(target_save.file_size == save_entry.file_size
                 and target_extra.file_size == extra_entry.file_size,
                 "target container geometry differs from the source")
        position = 0
        for offset, count in save_extents:
            written = platform_compat.pwrite(
                target_descriptor,
                bytes(payload[position : position + count]),
                offset,
            )
            _require(written == count, "short write on the save extents")
            position += count
        for offset, count in extra_extents:
            written = platform_compat.pwrite(target_descriptor,
                                             new_extra[:count], offset)
            _require(written == count, "short write on the EXTRA extent")
        os.fsync(target_descriptor)
        readback = target_volume.read_file(target_save)
        readback_extra = target_volume.read_file(target_extra)
        _require(readback == bytes(payload),
                 "post-write SAVEGAME.DAT readback mismatch")
        _require(readback_extra == new_extra,
                 "post-write EXTRA readback mismatch")
    finally:
        os.close(target_descriptor)

    return {
        "schema": WRITEBACK_SCHEMA,
        "source": {"path": str(source), "partition": partition},
        "target": {"path": str(target), "partition": partition},
        "container": list(container),
        "save_kind": kind,
        "save_sha256_before": _digest(savegame),
        "save_sha256_after": _digest(bytes(payload)),
        "extra_mac": new_extra.hex(),
        "slider_mode": slider_mode,
        "slider_changes": slider_changes,
        "franchise_year_change": year_change,
        "post_write_readback_matches": True,
    }


def _argument_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Read and edit NFL 2K5 saves (A1 sliders, A4 resign, A7 "
            "franchise year) on copies only. Loose-file mode emits a mutated "
            "SAVEGAME.DAT plus a fresh EXTRA; writeback mode patches the "
            "container extents inside a copied raw Xbox HDD image."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    read_parser = commands.add_parser("read", help="report save contents")
    read_parser.add_argument("savegame", type=Path)

    edit_parser = commands.add_parser(
        "edit", help="edit a loose SAVEGAME.DAT copy and sign it"
    )
    edit_parser.add_argument("savegame", type=Path)
    edit_parser.add_argument("--out-dat", type=Path, required=True)
    edit_parser.add_argument("--out-extra", type=Path, required=True)
    edit_parser.add_argument("--xbe", type=Path, required=True)
    edit_parser.add_argument(
        "--slider", action="append", default=[], nargs=2,
        metavar=("LABEL", "VALUE"),
        help=f"one of: {', '.join(SLIDER_LABELS)}",
    )
    edit_parser.add_argument("--mode", choices=SLIDER_MODES,
                             default="consistent")
    edit_parser.add_argument("--franchise-year", type=int, default=None)
    edit_parser.add_argument("--overwrite", action="store_true",
                             help="replace existing output files")

    writeback_parser = commands.add_parser(
        "writeback", help="edit a save inside a copied raw HDD image"
    )
    writeback_parser.add_argument("source_hdd", type=Path)
    writeback_parser.add_argument("target_hdd", type=Path)
    writeback_parser.add_argument("--xbe", type=Path, required=True)
    writeback_parser.add_argument("--container", required=True,
                                  help="slash-separated, e.g. 53450030/Franchise1")
    writeback_parser.add_argument("--partition", default="E",
                                  choices=sorted(FATX_PARTITIONS))
    writeback_parser.add_argument(
        "--slider", action="append", default=[], nargs=2,
        metavar=("LABEL", "VALUE"),
    )
    writeback_parser.add_argument("--mode", choices=SLIDER_MODES,
                                  default="consistent")
    writeback_parser.add_argument("--franchise-year", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    import json

    args = _argument_parser().parse_args(argv)
    if args.command == "read":
        print(json.dumps(read_save(args.savegame), indent=2, sort_keys=True))
        return 0
    sliders = {label: float(value) for label, value in args.slider}
    if args.command == "edit":
        result = edit_save_file(
            args.savegame, args.out_dat, args.out_extra,
            xbe_path=args.xbe, sliders=sliders, slider_mode=args.mode,
            franchise_year=args.franchise_year,
            overwrite=args.overwrite,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.command == "writeback":
        result = write_back_to_hdd(
            args.source_hdd, args.target_hdd,
            container=tuple(args.container.split("/")),
            xbe_path=args.xbe, sliders=sliders, slider_mode=args.mode,
            franchise_year=args.franchise_year, partition=args.partition,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    raise SaveWriterError(f"unknown command {args.command!r}")


__all__ = [
    "EDIT_SCHEMA",
    "FRANCHISE_DISPLAY_YEAR_BASE",
    "FRANCHISE_SAVE_SIZE",
    "READ_SCHEMA",
    "SETTINGS_SAVE_SIZE",
    "SLIDER_LABELS",
    "SLIDER_MODES",
    "SaveWriterError",
    "WRITEBACK_SCHEMA",
    "apply_franchise_year",
    "apply_slider_edits",
    "derive_sig_key",
    "edit_save_file",
    "read_franchise_fields",
    "read_save",
    "save_kind",
    "sign_save",
    "slider_offsets",
    "verify_extra",
    "main",
    "write_back_to_hdd",
    "xbe_cert_sig_key",
]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SaveWriterError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc

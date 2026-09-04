#!/usr/bin/env python3
"""List and extract ESPN NFL 2K5 saves from an xemu Xbox HDD image (read-only).

The image is opened read-only and never written.  Both the raw 8 GiB HDD image and xemu's
``xbox_hdd.qcow2`` are understood: qcow2 (version 2/3, zlib-compressed clusters, no backing
file) is decoded by ``Qcow2Image`` here, so ``qemu-img`` is not needed.  The Xbox partition map
is fixed (``fatx_dirent_rename.PARTITIONS``); saves live on E: under
``UDATA/53450030/<uid>/{SaveMeta.xbx, TYPE, SAVEGAME.DAT, EXTRA}`` with the title-level
``TitleMeta.xbx / TitleImage.xbx / SaveImage.xbx`` beside the uid folders.  A bare FATX
partition image (``FATX`` at offset 0) is accepted too, which is what the tests build.

Commands::

    nfl2k5_xemu_saves.py list <image> [--json]
    nfl2k5_xemu_saves.py extract <image> <out_dir> [--overwrite] [--no-catalogue]
    nfl2k5_xemu_saves.py catalogue <dir>

``extract`` writes ``<out_dir>/<uid>-<SaveMeta name>/UDATA/53450030/<uid>/...`` (the shape the
studio's private fixtures already use), verifies every ``EXTRA`` against ``SAVEGAME.DAT`` with
the title HMAC and then writes ``<out_dir>/CATALOGUE.md`` covering every save folder in
``out_dir`` (including ones that were already there).  Existing files are never overwritten
unless ``--overwrite`` is given; identical files are skipped silently.

Kinds are decided from bytes, not names: ``franchise`` = TYPE ``FXG`` plus the runtime ROST
arena wrapper at 0x2E0 (720,044 bytes); ``roster`` = a ROST arena without the franchise TYPE;
``settings`` = TYPE ``STG`` / 736 bytes (the slider block); ``profile`` = TYPE ``USR`` (the VIP
profile Finn's "Crib Cheater" edits); ``team`` = TYPE ``TMM`` (an exported team: team record,
coach and its players); anything else is ``other`` with the TYPE code shown.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import struct
import sys
import zlib
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, BinaryIO, Iterable

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fatx_dirent_rename import PARTITIONS, Dirent, FatXVolume, FATX_SIGNATURE  # noqa: E402

TITLE_ID = "53450030"
SAVE_ROOTS = ("UDATA", "TDATA")
CONTAINER_MEMBERS = ("SaveMeta.xbx", "TYPE", "SAVEGAME.DAT", "EXTRA")
TITLE_FILES = ("TitleMeta.xbx", "TitleImage.xbx", "SaveImage.xbx")
MAX_MEMBER_SIZE = 16 * 1024 * 1024
QCOW2_MAGIC = b"QFI\xfb"
ROST_WRAPPER_OFFSET = 0x2E0
ROST_PREAMBLE_OFFSET = 0x300
ROST_ARENA_LENGTH = 0x91020
FRANCHISE_SAVE_SIZE = 720_044
SETTINGS_SAVE_SIZE = 736
CATALOGUE_NAME = "CATALOGUE.md"
SCHEMA = "nfl2k5_xemu_saves/v1"


class XemuSaveError(ValueError):
    """The image, volume or save container cannot be read as expected."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise XemuSaveError(message)


# --------------------------------------------------------------------------------------------- qcow2
class Qcow2Image:
    """Read-only, file-like view of a qcow2 image's guest bytes.

    Supports qcow2 version 2 and 3 with zlib-compressed clusters (xemu's default), no backing
    file, no encryption, no external data file and no extended L2 entries.  Internal snapshots
    are ignored: the active L1 table is what the guest sees.  Only ``seek``/``read``/``tell`` are
    offered because that is all ``FatXVolume`` needs.
    """

    L2_OFFSET_MASK = 0x00FFFFFFFFFFFE00
    FLAG_COMPRESSED = 1 << 62
    FLAG_ZERO = 1

    def __init__(self, stream: BinaryIO) -> None:
        self.stream = stream
        stream.seek(0)
        header = stream.read(104)
        _require(len(header) >= 72 and header[:4] == QCOW2_MAGIC, "not a qcow2 image")
        (self.version, backing_offset, backing_size, self.cluster_bits, self.size, crypt_method,
         l1_size, l1_offset, _refcount_offset, _refcount_clusters, self.snapshots,
         _snapshots_offset) = struct.unpack(">IQIIQIIQQIIQ", header[4:72])
        _require(self.version in (2, 3), f"qcow2 version {self.version} is not supported")
        _require(backing_offset == 0 and backing_size == 0, "qcow2 images with a backing file are not supported")
        _require(crypt_method == 0, "encrypted qcow2 images are not supported")
        _require(9 <= self.cluster_bits <= 21, f"implausible qcow2 cluster_bits {self.cluster_bits}")
        if self.version >= 3:
            incompatible, _compatible, _autoclear, _refcount_order, header_length = struct.unpack(">QQQII", header[72:104])
            _require(incompatible & ~0x1 == 0 or incompatible == 0,
                     f"qcow2 incompatible features 0x{incompatible:x} are not supported")
            compression_type = 0
            if header_length > 104:
                stream.seek(104)
                compression_type = stream.read(1)[0]
            _require(compression_type == 0, f"qcow2 compression type {compression_type} is not zlib")
        self.cluster_size = 1 << self.cluster_bits
        self.l2_entries = self.cluster_size // 8
        stream.seek(l1_offset)
        raw = stream.read(l1_size * 8)
        _require(len(raw) == l1_size * 8, "truncated qcow2 L1 table")
        self.l1 = struct.unpack(f">{l1_size}Q", raw) if l1_size else ()
        self._l2_cache: dict[int, tuple[int, ...]] = {}
        self._cluster_cache: dict[int, bytes] = {}
        self.position = 0

    # ----------------------------------------------------------------- file-like surface
    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.position = offset
        elif whence == 1:
            self.position += offset
        elif whence == 2:
            self.position = self.size + offset
        else:
            raise ValueError("bad whence")
        _require(self.position >= 0, "negative seek")
        return self.position

    def tell(self) -> int:
        return self.position

    def read(self, count: int = -1) -> bytes:
        if count < 0:
            count = self.size - self.position
        count = max(0, min(count, self.size - self.position))
        out = bytearray()
        while count:
            index, inner = divmod(self.position, self.cluster_size)
            chunk = self._cluster(index)[inner: inner + count]
            out += chunk
            self.position += len(chunk)
            count -= len(chunk)
        return bytes(out)

    def close(self) -> None:
        self.stream.close()

    def __enter__(self) -> "Qcow2Image":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ----------------------------------------------------------------- mapping
    def _l2_table(self, l1_index: int) -> tuple[int, ...] | None:
        if l1_index in self._l2_cache:
            return self._l2_cache[l1_index]
        if l1_index >= len(self.l1):
            return None
        entry = self.l1[l1_index] & self.L2_OFFSET_MASK
        if entry == 0:
            table = None
        else:
            self.stream.seek(entry)
            raw = self.stream.read(self.cluster_size)
            _require(len(raw) == self.cluster_size, "truncated qcow2 L2 table")
            table = struct.unpack(f">{self.l2_entries}Q", raw)
        if len(self._l2_cache) > 64:
            self._l2_cache.clear()
        self._l2_cache[l1_index] = table
        return table

    def _cluster(self, index: int) -> bytes:
        cached = self._cluster_cache.get(index)
        if cached is not None:
            return cached
        l1_index, l2_index = divmod(index, self.l2_entries)
        table = self._l2_table(l1_index)
        data = bytes(self.cluster_size)
        if table is not None:
            entry = table[l2_index]
            if entry & self.FLAG_COMPRESSED:
                shift = 62 - (self.cluster_bits - 8)
                host = entry & ((1 << shift) - 1)
                sectors = ((entry >> shift) & ((1 << (self.cluster_bits - 8)) - 1)) + 1
                self.stream.seek(host)
                packed = self.stream.read(sectors * 512)
                try:
                    data = zlib.decompressobj(-15).decompress(packed, self.cluster_size)
                except zlib.error as exc:
                    raise XemuSaveError(f"qcow2 cluster {index}: corrupt compressed data ({exc})") from exc
                _require(len(data) == self.cluster_size, f"qcow2 cluster {index}: short compressed cluster")
            elif entry & self.FLAG_ZERO:
                pass
            else:
                host = entry & self.L2_OFFSET_MASK
                if host:
                    self.stream.seek(host)
                    data = self.stream.read(self.cluster_size)
                    _require(len(data) == self.cluster_size, f"qcow2 cluster {index}: truncated host cluster")
        if len(self._cluster_cache) > 256:
            self._cluster_cache.clear()
        self._cluster_cache[index] = data
        return data


def open_image(path: Path | str) -> tuple[BinaryIO | Qcow2Image, int, str]:
    """Open a raw or qcow2 HDD image read-only: (file-like, guest size, format)."""

    source = Path(path).expanduser()
    _require(source.is_file(), f"{source} is not a file")
    stream = open(source, "rb")
    head = stream.read(4)
    if head == QCOW2_MAGIC:
        image = Qcow2Image(stream)
        return image, image.size, "qcow2"
    stream.seek(0, 2)
    return stream, stream.tell(), "raw"


# --------------------------------------------------------------------------------------------- FATX
def _has_fatx(image: BinaryIO | Qcow2Image, offset: int, size: int) -> bool:
    if offset + 16 > size:
        return False
    image.seek(offset)
    head = image.read(16)
    return len(head) == 16 and struct.unpack_from("<I", head)[0] == FATX_SIGNATURE


def find_volume(image: BinaryIO | Qcow2Image, size: int, partition: str = "auto") -> tuple[str, int, int]:
    """Locate the FATX volume holding the saves: ``(label, offset, length)``.

    ``auto`` takes a bare partition image (FATX at 0) as a whole, otherwise the first of E, C,
    X, Y, Z from the fixed Xbox map that carries a FATX superblock.  A named partition letter
    is taken verbatim.
    """

    if partition != "auto":
        letter = partition.upper()
        _require(letter in PARTITIONS, f"unknown partition {partition!r}; expected one of {sorted(PARTITIONS)}")
        offset, length = PARTITIONS[letter]
        _require(_has_fatx(image, offset, size), f"no FATX superblock at partition {letter} (0x{offset:x})")
        return letter, offset, min(length, size - offset)
    if _has_fatx(image, 0, size):
        return "bare", 0, size
    for letter in ("E", "C", "X", "Y", "Z"):
        offset, length = PARTITIONS[letter]
        if _has_fatx(image, offset, size):
            return letter, offset, min(length, size - offset)
    raise XemuSaveError("no FATX volume found (neither a bare partition nor the fixed Xbox partition map)")


def read_member(volume: FatXVolume, entry: Dirent, *, maximum: int = MAX_MEMBER_SIZE) -> bytes:
    _require(not entry.is_directory, f"{entry.name} is a directory")
    _require(0 <= entry.file_size <= maximum, f"{entry.name} is {entry.file_size} bytes, over the {maximum} cap")
    if entry.file_size == 0:
        return b""
    chain = volume.cluster_chain(entry.first_cluster)
    needed = (entry.file_size + volume.bytes_per_cluster - 1) // volume.bytes_per_cluster
    _require(len(chain) >= needed, f"{entry.name}: FAT chain is shorter than the file")
    out = bytearray()
    remaining = entry.file_size
    for cluster in chain[:needed]:
        volume.image.seek(volume.cluster_offset(cluster))
        chunk = volume.image.read(min(volume.bytes_per_cluster, remaining))
        _require(len(chunk) == min(volume.bytes_per_cluster, remaining), f"{entry.name}: short cluster read")
        out += chunk
        remaining -= len(chunk)
    return bytes(out)


def _child(entries: Iterable[Dirent], name: str) -> Dirent | None:
    for entry in entries:
        if entry.name.casefold() == name.casefold():
            return entry
    return None


# --------------------------------------------------------------------------------------------- saves
@dataclass
class TitleSave:
    root: str                      # UDATA or TDATA
    uid: str                       # the 12-hex container folder
    name: str                      # SaveMeta.xbx "Name=" text
    type_code: str                 # TYPE (three letters)
    members: dict[str, bytes]      # every file in the container
    extra_verified: bool | None    # None when the title key is unavailable
    kind: str = "other"
    reason: str = ""
    arena_at_0x300: bool = False

    @property
    def savegame(self) -> bytes:
        return self.members["SAVEGAME.DAT"]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.savegame).hexdigest()

    @property
    def folder(self) -> str:
        return f"{self.uid}-{safe_name(self.name)}"

    def row(self) -> dict[str, Any]:
        return {"root": self.root, "uid": self.uid, "name": self.name, "type": self.type_code,
                "size": len(self.savegame), "sha256": self.sha256, "extra_verified": self.extra_verified,
                "kind": self.kind, "reason": self.reason, "arena_at_0x300": self.arena_at_0x300,
                "members": {name: len(data) for name, data in self.members.items()}}


@dataclass
class TitleListing:
    volume: str
    title_files: dict[str, bytes] = dc_field(default_factory=dict)
    saves: list[TitleSave] = dc_field(default_factory=list)


def safe_name(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text.strip())
    return cleaned or "unnamed"


def decode_save_meta(payload: bytes) -> str:
    """``SaveMeta.xbx`` is UTF-16LE with a BOM: ``Name=<text>\\r\\n``."""

    text = payload[2:].decode("utf-16-le", errors="replace") if payload.startswith(b"\xff\xfe") else \
        payload.decode("utf-16-le", errors="replace")
    for line in text.replace("\r", "\n").split("\n"):
        if line.startswith("Name="):
            return line[5:]
    return text.strip()


def decode_type(payload: bytes) -> str:
    try:
        return payload.decode("utf-16-le", errors="replace").rstrip("\0")
    except Exception:                                                   # pragma: no cover - defensive
        return payload.hex()


def _title_key():
    try:
        from mod_editor.core import nfl2k5_roster_records as rr
    except Exception:                                                   # pragma: no cover - key module missing
        return None
    return rr


def verify_extra(savegame: bytes, extra: bytes) -> bool | None:
    module = _title_key()
    if module is None:
        return None
    return module.verify_extra(savegame, extra)


def arena_present(payload: bytes) -> bool:
    """The runtime ROST arena every roster-bearing save carries: wrapper at 0x2E0, preamble at 0x300."""

    if len(payload) < ROST_PREAMBLE_OFFSET + 0x20:
        return False
    if payload[ROST_WRAPPER_OFFSET: ROST_WRAPPER_OFFSET + 4] != b"ROST":
        return False
    declared = struct.unpack_from("<I", payload, ROST_WRAPPER_OFFSET + 4)[0]
    if payload[ROST_PREAMBLE_OFFSET + 0x0C: ROST_PREAMBLE_OFFSET + 0x10] != b"ROST":
        return False
    version = struct.unpack_from("<I", payload, ROST_PREAMBLE_OFFSET + 0x10)[0]
    return version == 0 and ROST_PREAMBLE_OFFSET + declared <= len(payload)


def classify(type_code: str, payload: bytes) -> tuple[str, str, bool]:
    """``(kind, how decided, arena present)`` from the TYPE code and the bytes."""

    arena = arena_present(payload)
    size = len(payload)
    if arena and type_code == "FXG":
        return ("franchise", f"TYPE FXG + ROST arena wrapper at 0x2E0 ({size:,} B"
                             f"{'' if size == FRANCHISE_SAVE_SIZE else ', unusual size'})", True)
    if arena:
        return "roster", f"ROST arena wrapper at 0x2E0 without the franchise TYPE (TYPE {type_code}, {size:,} B)", True
    if type_code == "STG" or size == SETTINGS_SAVE_SIZE:
        return "settings", f"TYPE {type_code}, {size} B slider/settings block (RAM 0xE5FF80..)", False
    if type_code == "USR":
        return "profile", f"TYPE USR ({size:,} B): the VIP profile with the ticker text (Finn's 'Crib Cheater' target)", False
    if type_code == "TMM":
        return "team", f"TYPE TMM ({size:,} B): exported team (team record, coach, players and their names)", False
    return "other", f"TYPE {type_code}, {size:,} B, no ROST arena", False


def list_title(volume: FatXVolume, *, label: str = "?", title_id: str = TITLE_ID,
               roots: tuple[str, ...] = SAVE_ROOTS) -> TitleListing:
    listing = TitleListing(volume=label)
    root_entries = volume.read_directory(volume.root_cluster)
    for root in roots:
        top = _child(root_entries, root)
        if top is None or not top.is_directory:
            continue
        title = _child(volume.read_directory(top.first_cluster), title_id)
        if title is None or not title.is_directory:
            continue
        for entry in volume.read_directory(title.first_cluster):
            if not entry.is_directory:
                if root == "UDATA":
                    listing.title_files[entry.name] = read_member(volume, entry)
                continue
            members = {child.name: read_member(volume, child)
                       for child in volume.read_directory(entry.first_cluster) if not child.is_directory}
            if "SAVEGAME.DAT" not in members:
                continue
            name = decode_save_meta(members.get("SaveMeta.xbx", b""))
            type_code = decode_type(members.get("TYPE", b""))
            extra = members.get("EXTRA")
            verified = verify_extra(members["SAVEGAME.DAT"], extra) if extra is not None else False
            kind, reason, arena = classify(type_code, members["SAVEGAME.DAT"])
            listing.saves.append(TitleSave(root, entry.name, name, type_code, members, verified, kind, reason, arena))
    listing.saves.sort(key=lambda save: (save.root, save.kind, save.name.casefold(), save.uid))
    return listing


def scan_image(path: Path | str, *, partition: str = "auto") -> TitleListing:
    image, size, fmt = open_image(path)
    try:
        label, offset, length = find_volume(image, size, partition)
        volume = FatXVolume(image, offset, length)
        return list_title(volume, label=f"{fmt} image, partition {label} @0x{offset:x}")
    finally:
        image.close()


# --------------------------------------------------------------------------------------------- extract
def extract(path: Path | str, out_dir: Path | str, *, partition: str = "auto", overwrite: bool = False,
            catalogue: bool = True) -> dict[str, Any]:
    """Write every title save into ``out_dir/<uid>-<name>/UDATA/53450030/...`` and catalogue the folder."""

    listing = scan_image(path, partition=partition)
    target_root = Path(out_dir).expanduser()
    target_root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    skipped: list[str] = []
    for save in listing.saves:
        base = target_root / save.folder / save.root / TITLE_ID
        for name, data in listing.title_files.items():
            _place(base / name, data, overwrite, written, skipped)
        for name, data in save.members.items():
            _place(base / save.uid / name, data, overwrite, written, skipped)
    receipt = {"schema": SCHEMA, "image": str(Path(path).expanduser()), "volume": listing.volume,
               "out_dir": str(target_root), "saves": [save.row() for save in listing.saves],
               "written": written, "skipped_identical": skipped}
    if catalogue:
        receipt["catalogue"] = str(write_catalogue(target_root))
    return receipt


def _place(target: Path, data: bytes, overwrite: bool, written: list[str], skipped: list[str]) -> None:
    if target.exists():
        if target.read_bytes() == data:
            skipped.append(str(target))
            return
        _require(overwrite, f"{target} exists with different content; pass --overwrite to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    written.append(str(target))


# --------------------------------------------------------------------------------------------- catalogue
def catalogue_rows(folder: Path | str) -> list[dict[str, Any]]:
    """One row per ``<folder>/*/UDATA|TDATA/53450030/<uid>/SAVEGAME.DAT`` in a fixtures folder."""

    root = Path(folder).expanduser()
    rows: list[dict[str, Any]] = []
    for savegame in sorted(root.glob(f"*/*/{TITLE_ID}/*/SAVEGAME.DAT")):
        container = savegame.parent
        payload = savegame.read_bytes()
        extra = container / "EXTRA"
        meta = container / "SaveMeta.xbx"
        type_file = container / "TYPE"
        type_code = decode_type(type_file.read_bytes()) if type_file.is_file() else "?"
        name = decode_save_meta(meta.read_bytes()) if meta.is_file() else "?"
        kind, reason, arena = classify(type_code, payload)
        verified = verify_extra(payload, extra.read_bytes()) if extra.is_file() else False
        row = {"folder": savegame.relative_to(root).parts[0], "root": savegame.relative_to(root).parts[1],
               "uid": container.name, "name": name, "type": type_code, "size": len(payload),
               "sha256": hashlib.sha256(payload).hexdigest(), "extra_verified": verified, "kind": kind,
               "reason": reason, "arena_at_0x300": arena, "summary": franchise_summary(payload) if kind == "franchise" else ""}
        rows.append(row)
    return rows


def franchise_summary(payload: bytes) -> str:
    """A one-line franchise summary when the franchise decoder is importable (year, stage, user team, cap)."""

    try:
        from mod_editor.core import nfl2k5_franchise_save as fs
    except Exception:
        return ""
    try:
        return fs.FranchiseSave(payload).one_line()
    except Exception as exc:                                             # pragma: no cover - decoder refused
        return f"(decoder: {exc})"


def render_catalogue(rows: list[dict[str, Any]], folder: Path) -> str:
    lines = [
        "# NFL 2K5 save fixtures — catalogue",
        "",
        f"Generated by `tools/nfl2k5_xemu_saves.py catalogue` on {dt.date.today().isoformat()} from `{folder}`.",
        "Private fixtures: never commit these bytes.  Kinds are decided from the bytes and the TYPE code",
        "(see the tool's docstring); `arena@0x300` = the runtime ROST arena the ★ Rosters tab opens.",
        "",
        "| folder | uid | SaveMeta name | TYPE | size | sha256 (16) | EXTRA | kind | how decided | arena@0x300 | summary |",
        "|---|---|---|---|---:|---|---|---|---|---|---|",
    ]
    for row in rows:
        extra = {True: "verified", False: "MISMATCH", None: "unchecked"}[row["extra_verified"]]
        lines.append(f"| `{row['folder']}` | `{row['uid']}` | {row['name']} | {row['type']} | {row['size']:,} | "
                     f"`{row['sha256'][:16]}` | {extra} | **{row['kind']}** | {row['reason']} | "
                     f"{'yes' if row['arena_at_0x300'] else 'no'} | {row['summary']} |")
    lines.append("")
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    lines.append(f"{len(rows)} saves: " + ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items())) + ".")
    lines.append("")
    return "\n".join(lines)


def write_catalogue(folder: Path | str) -> Path:
    root = Path(folder).expanduser()
    rows = catalogue_rows(root)
    target = root / CATALOGUE_NAME
    target.write_text(render_catalogue(rows, root), encoding="utf-8")
    return target


# --------------------------------------------------------------------------------------------- CLI
def _format_listing(listing: TitleListing) -> str:
    lines = [f"volume: {listing.volume}", f"title files: {', '.join(f'{k} ({len(v)} B)' for k, v in listing.title_files.items()) or 'none'}"]
    for save in listing.saves:
        extra = {True: "verified", False: "MISMATCH", None: "unchecked"}[save.extra_verified]
        lines.append(f"{save.root}/{save.uid}  {save.name!r:<18} {save.type_code}  {len(save.savegame):>9,} B  "
                     f"sha256 {save.sha256[:16]}  EXTRA {extra}  {save.kind} ({save.reason})")
    lines.append(f"{len(listing.saves)} saves")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    lister = sub.add_parser("list", help="list the title's saves on the image")
    lister.add_argument("image", type=Path)
    lister.add_argument("--partition", default="auto", help="auto (default), or one of E C X Y Z")
    lister.add_argument("--json", action="store_true")
    extractor = sub.add_parser("extract", help="copy every save out into a fixtures folder and catalogue it")
    extractor.add_argument("image", type=Path)
    extractor.add_argument("out_dir", type=Path)
    extractor.add_argument("--partition", default="auto")
    extractor.add_argument("--overwrite", action="store_true")
    extractor.add_argument("--no-catalogue", action="store_true")
    extractor.add_argument("--json", action="store_true")
    cataloguer = sub.add_parser("catalogue", help="(re)write CATALOGUE.md for a fixtures folder")
    cataloguer.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            listing = scan_image(args.image, partition=args.partition)
            if args.json:
                print(json.dumps({"schema": SCHEMA, "volume": listing.volume,
                                  "title_files": {k: len(v) for k, v in listing.title_files.items()},
                                  "saves": [save.row() for save in listing.saves]}, indent=2))
            else:
                print(_format_listing(listing))
        elif args.command == "extract":
            receipt = extract(args.image, args.out_dir, partition=args.partition, overwrite=args.overwrite,
                              catalogue=not args.no_catalogue)
            if args.json:
                print(json.dumps(receipt, indent=2))
            else:
                print(f"{len(receipt['written'])} files written, {len(receipt['skipped_identical'])} identical files "
                      f"skipped, {len(receipt['saves'])} saves -> {receipt['out_dir']}")
                if receipt.get("catalogue"):
                    print(f"catalogue: {receipt['catalogue']}")
        else:
            target = write_catalogue(args.folder)
            print(f"wrote {target}")
    except (XemuSaveError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

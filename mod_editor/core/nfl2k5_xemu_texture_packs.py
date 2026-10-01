"""Texture packs for the xemu 2K5 Edition: keys, a disc's texture catalog, dump naming, pack build and install.

The 2K5 Edition xemu (``~/xemu-2k5-edition``, research tracks R2/R3/z2 made into one build) replaces a texture at
draw time with a high-resolution image from a pack, without the game ever holding the large image. It finds the
image by the texture's **x2 key**, a pure function of the guest bytes:

    x2_<W>x<H>_<TEX>[_<PAL>|_$]_<FMT>

``TEX`` is the canonical XXH3-64 of the level-0 texels exactly as the game uploads them (swizzled texels, DXT
blocks, or linear rows without pitch padding), ``PAL`` the XXH3-64 of the 1024 palette bytes of a P8 texture (``$``
in a file name matches every palette of that index chain), ``FMT`` the NV2A colour format (two hex digits). No VRAM
address is involved, so a key survives load order and relocation. It does change whenever the texel or palette
bytes change: a pack is keyed to the disc it was built for, so **packs are keyed from the disc Noah plays** (the
native modded build), never assumed from retail.

The game uploads its disc textures byte for byte, which is why the Studio can compute keys offline (research R2:
372 of 557 runtime keys of one match reproduced from disc bytes; the rest are runtime-composed textures, front-end
screens and resource kinds not decoded yet). ``catalog_disc`` goes further than R2's three ledgers: it scans the
decoded system section of every compressed chunk (TXTR, TSET, SCNE and every other kind) for the 32-byte texture
descriptor all of them share ({unknown, pixel offset, palette offset, NV2A format word, explicit size, flags, ...})
and keys each descriptor's level 0 in the chunk's video section.

Workflow (``tools/nfl2k5_texture_pack.py``):

1. ``catalog DISC`` - every keyable texture on that disc, named where the Studio can name it (TXTR names; TSET and
   SCNE names joined from the retail ledgers by position), and ``--retail`` marks which ones the mod changed.
2. ``name-dump DUMP`` - for textures the catalog cannot see (runtime-composed ones), the Edition's dump mode
   (``xemu-2k5 --dump DIR``) writes every texture a session drew; this names each dumped key from a catalog.
3. ``workspace`` - one folder per chosen texture with the guest image and a 4x template to redraw.
4. ``build`` - a manifest of redrawn images (by key, by catalog name or by catalog position, or a ``.2ktexmaster``
   bundle whose 4x preview is the pack image) resolved against the disc's catalog, validated and written as a pack
   folder with ``pack.json``; ``validate`` checks a pack; ``install`` copies it into the Edition's packs folder and
   touches ``RELOAD`` so a running Edition picks it up without a restart.

Nothing here reads or writes retail bytes into a pack: a pack holds only the images the modder supplies.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field, fields
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import time
from typing import Callable, Iterable, Iterator, Mapping, Sequence
import zlib

from PIL import Image

from . import platform_compat
from .xxh3 import xxh3_64_hex
from tools import nfl_txtr as txtr
from tools import nfl_uniform_color_xiso_direct_patch as xiso

SCHEMA_PACK = "2k5-texture-pack/1"
SCHEMA_CATALOG = "2k5-texture-catalog/1"
KEY_VERSION = "x2"
TITLE_ID = "53450030"
PACK_FOLDER = "vc_53450030"
PALETTE_BYTES = 1024
KEY_RE = re.compile(r"^x2_(\d+)x(\d+)_([0-9a-f]{16})(?:_([0-9a-f]{16}|\$))?_([0-9a-f]{2})$")
DEFAULT_PACKS_ROOT = Path.home() / "xemu-2k5-edition" / "packs"

# NV097 texture colour formats: code -> (name, bytes per texel or DXT block bytes, linear, dxt)
FORMATS: dict[int, tuple[str, int, bool, bool]] = {
    0x00: ("SZ_Y8", 1, False, False), 0x01: ("SZ_AY8", 1, False, False),
    0x02: ("SZ_A1R5G5B5", 2, False, False), 0x03: ("SZ_X1R5G5B5", 2, False, False),
    0x04: ("SZ_A4R4G4B4", 2, False, False), 0x05: ("SZ_R5G6B5", 2, False, False),
    0x06: ("SZ_A8R8G8B8", 4, False, False), 0x07: ("SZ_X8R8G8B8", 4, False, False),
    0x0B: ("SZ_I8_A8R8G8B8", 1, False, False),
    0x0C: ("L_DXT1_A1R5G5B5", 8, False, True), 0x0E: ("L_DXT23_A8R8G8B8", 16, False, True),
    0x0F: ("L_DXT45_A8R8G8B8", 16, False, True),
    0x10: ("LU_IMAGE_A1R5G5B5", 2, True, False), 0x11: ("LU_IMAGE_R5G6B5", 2, True, False),
    0x12: ("LU_IMAGE_A8R8G8B8", 4, True, False), 0x13: ("LU_IMAGE_Y8", 1, True, False),
    0x17: ("LU_IMAGE_G8B8", 2, True, False), 0x19: ("SZ_A8", 1, False, False),
    0x1A: ("SZ_A8Y8", 2, False, False), 0x1B: ("LU_IMAGE_AY8", 1, True, False),
    0x1C: ("LU_IMAGE_X1R5G5B5", 2, True, False), 0x1D: ("LU_IMAGE_A4R4G4B4", 2, True, False),
    0x1E: ("LU_IMAGE_X8R8G8B8", 4, True, False), 0x1F: ("LU_IMAGE_A8", 1, True, False),
    0x20: ("LU_IMAGE_A8Y8", 2, True, False), 0x27: ("SZ_R6G5B5", 2, False, False),
    0x28: ("SZ_G8B8", 2, False, False), 0x29: ("SZ_R8B8", 2, False, False),
    0x35: ("LU_IMAGE_Y16", 2, True, False), 0x3A: ("SZ_A8B8G8R8", 4, False, False),
    0x3B: ("SZ_B8G8R8A8", 4, False, False), 0x3C: ("SZ_R8G8B8A8", 4, False, False),
    0x3F: ("LU_IMAGE_A8B8G8R8", 4, True, False), 0x40: ("LU_IMAGE_B8G8R8A8", 4, True, False),
    0x41: ("LU_IMAGE_R8G8B8A8", 4, True, False),
}
P8 = 0x0B
NO_ALPHA = {0x00, 0x03, 0x05, 0x07, 0x11, 0x13, 0x1C, 0x1E, 0x35}


class TexturePackError(ValueError):
    """A key, catalog, image or pack that cannot be used, with the reason."""


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise TexturePackError(message)


# ---- keys ---------------------------------------------------------------------------------------------------

def format_name(fmt: int) -> str:
    return FORMATS.get(fmt, (f"0x{fmt:02x}", 0, False, False))[0]


def level0_size(fmt: int, width: int, height: int) -> int:
    """Bytes of level 0 as the key hashes them (linear rows without pitch padding)."""
    _require(fmt in FORMATS, f"NV2A format 0x{fmt:02x} is not keyable")
    _require(width > 0 and height > 0, "texture size must be positive")
    _name, unit, _linear, dxt = FORMATS[fmt]
    if dxt:
        return ((width + 3) // 4) * ((height + 3) // 4) * unit
    return width * height * unit


def texture_key(fmt: int, width: int, height: int, level0: bytes, palette: bytes | None = None) -> str:
    """The x2 key the Edition computes for this texture's guest bytes."""
    _require(len(level0) == level0_size(fmt, width, height),
             f"level 0 is {len(level0)} bytes; a {width}x{height} {format_name(fmt)} needs "
             f"{level0_size(fmt, width, height)}")
    base = f"x2_{width}x{height}_{xxh3_64_hex(level0)}"
    if fmt == P8:
        _require(palette is not None and len(palette) == PALETTE_BYTES,
                 "a P8 key needs the 1024 palette bytes the NV2A reads")
        return f"{base}_{xxh3_64_hex(palette)}_{fmt:02x}"
    return f"{base}_{fmt:02x}"


@dataclass(frozen=True)
class KeyParts:
    width: int
    height: int
    texels: str
    palette: str | None  # 16 hex digits, "$" or None
    fmt: int

    @property
    def wild(self) -> str | None:
        if self.palette is None:
            return None
        return f"x2_{self.width}x{self.height}_{self.texels}_$_{self.fmt:02x}"


def parse_key(key: str) -> KeyParts:
    match = KEY_RE.match(key)
    _require(match is not None, f"{key!r} is not an x2 texture key")
    width, height, texels, palette, fmt = match.groups()
    return KeyParts(int(width), int(height), texels, palette, int(fmt, 16))


def wild_key(key: str) -> str:
    """The "any palette" form of a P8 key."""
    wild = parse_key(key).wild
    _require(wild is not None, f"{key} has no palette, so it has no any-palette form")
    return wild


# ---- archive entry names ------------------------------------------------------------------------------------------

def entry_name_id(filename: str) -> int:
    """The outer-archive entry id: CRC32 of the upper-cased UTF-16LE file name (tools/nfl2k5_soundbank_swap)."""
    return zlib.crc32(filename.upper().encode("utf-16le")) & 0xFFFFFFFF


def known_entry_names() -> dict[int, str]:
    """Entry ids of the file names the catalog can name: stadium bundles sNN + day/afternoon/night +
    dry/rain/snow (s16dd.iff = Gillette Stadium, day, dry; the venue table is in nfl2k5_stadium_texture_writer)."""
    names = {}
    for venue in range(60):
        for time_of_day in "dan":
            for weather in "drs":
                name = f"s{venue:02d}{time_of_day}{weather}.iff"
                names[entry_name_id(name)] = name
    return names


# ---- a disc's archive, read in place --------------------------------------------------------------------------

@dataclass(frozen=True)
class DiscEntry:
    index: int
    name_id: int
    size: int
    offset: int                                   # virtual offset in the archive
    extents: tuple[tuple[int, int, int], ...]     # (image byte offset, entry relative start, length)


class DiscArchive:
    """The game's outer archive (vc_53450030/0..Z) inside an XISO, read without extracting anything."""

    def __init__(self, image: Path):
        self.image = Path(image)
        self.fd = os.open(self.image, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            size = os.fstat(self.fd).st_size
            entries, _ = xiso.parse_xdvdfs(self.fd, size)
            self.files = entries
            pack0 = self._file("0")
            fixed = self._pread(pack0.byte_offset, 12 + 36 * 4)
            count, reserved, populated = struct.unpack_from("<III", fixed)
            _require(1 <= count <= 1_000_000 and reserved == 0 and 1 <= populated <= 36,
                     "the disc's archive header is not the game's")
            blocks = struct.unpack_from("<36I", fixed, 12)
            names = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            self.packs: list[tuple[int, int, int]] = []  # (virtual start, image offset, size)
            virtual = 0
            for ordinal in range(populated):
                entry = self._file(names[ordinal])
                pack_size = blocks[ordinal] * 0x800
                _require(entry.size >= pack_size, f"pack {names[ordinal]} is shorter than its header says")
                self.packs.append((virtual, entry.byte_offset, pack_size))
                virtual += pack_size
            table = self._read_virtual(12 + 36 * 4, count * 12)
            result = []
            for i in range(count):
                name_id, entry_size, offset_blocks = struct.unpack_from("<III", table, i * 12)
                offset = offset_blocks * 0x800
                result.append(DiscEntry(i, name_id, entry_size, offset, self._extents(offset, entry_size)))
            self.entries = tuple(result)
        except BaseException:
            os.close(self.fd)
            raise

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> "DiscArchive":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _file(self, name: str):
        entry = self.files.get(f"{PACK_FOLDER}/{name}".casefold()) or self.files.get(f"{PACK_FOLDER}/{name.lower()}")
        _require(entry is not None, f"the disc has no {PACK_FOLDER}/{name}")
        return entry

    def _pread(self, offset: int, size: int) -> bytes:
        data = platform_compat.pread(self.fd, size, offset)
        _require(len(data) == size, f"short read at 0x{offset:x}")
        return data

    def _extents(self, virtual: int, size: int) -> tuple[tuple[int, int, int], ...]:
        out = []
        relative = 0
        for start, image_offset, pack_size in self.packs:
            end = start + pack_size
            lo, hi = max(virtual, start), min(virtual + size, end)
            if lo < hi:
                out.append((image_offset + lo - start, relative, hi - lo))
                relative += hi - lo
        _require(relative == size, f"archive range 0x{virtual:x}+0x{size:x} is outside the packs")
        return tuple(out)

    def _read_virtual(self, virtual: int, size: int) -> bytes:
        return b"".join(self._pread(off, length) for off, _rel, length in self._extents(virtual, size))

    def read_entry(self, entry: DiscEntry) -> bytes:
        return b"".join(self._pread(off, length) for off, _rel, length in entry.extents)


# ---- resource chunks, walked the way tools/nfl_resource_scan.py walks them ------------------------------------

_MAX_ZERO_PADDING = 0x100000


def _bounded_header(data: bytes, offset: int) -> bool:
    if len(data) - offset < 0x20:
        return False
    kind = data[offset:offset + 4]
    stored = struct.unpack_from("<I", data, offset + 4)[0]
    return all(0x20 <= b <= 0x7E for b in kind) and stored != 0 and offset + 0x20 + stored <= len(data)


def iter_chunks(data: bytes) -> Iterator[txtr.Chunk]:
    """Every resource chunk of an archive entry, numbered like the Studio's chunk inventory: fixed-slot
    aggregates (the FaceTextures faces, Team Select cards, SCNE/SHAP tables) pad chunks with zeroes, and a
    walk that stopped at the first gap would miss everything after it."""
    offset, index = 0, 0
    while len(data) - offset >= 0x20:
        if not _bounded_header(data, offset):
            end = min(len(data), offset + _MAX_ZERO_PADDING)
            gap = len(data[offset:end]) - len(data[offset:end].lstrip(b"\0"))
            candidate = offset + gap
            if gap == 0 or candidate >= end or candidate % 0x10 or not _bounded_header(data, candidate):
                return
            offset = candidate
            continue
        fields = struct.unpack_from("<4s7I", data, offset)
        chunk = txtr.Chunk(index=index, offset=offset, kind=fields[0].decode("ascii"), stored_size=fields[1],
                           system_bytes=fields[2], video_bytes=fields[3], compression_magic=fields[4],
                           overlap_scratch_bytes=fields[5], reserved0=fields[6], reserved1=fields[7])
        yield chunk
        offset = chunk.end_offset
        index += 1


# ---- the texture descriptor every texture-bearing chunk uses ---------------------------------------------------

@dataclass(frozen=True)
class Descriptor:
    offset: int          # of the descriptor (its first word) in the decoded chunk
    pixel_offset: int    # level 0, relative to the video section
    palette_offset: int
    fmt: int
    width: int
    height: int
    levels: int
    word_format: int
    word_size: int
    flags: int


def _descriptor_fields(word_format: int, word_size: int) -> tuple[int, int, int, int, int] | None:
    dims = (word_format >> 4) & 0xF
    fmt = (word_format >> 8) & 0xFF
    levels = (word_format >> 16) & 0xF
    if dims != 2 or word_format & 0x4 or (word_format >> 28) & 0xF or fmt not in FORMATS or not 1 <= levels <= 13:
        return None
    if word_size == 0:
        log_u, log_v = (word_format >> 20) & 0xF, (word_format >> 24) & 0xF
        if log_u > 12 or log_v > 12:
            return None
        width, height = 1 << log_u, 1 << log_v
    else:
        width, height = word_size & 0xFFFF, (word_size >> 16) & 0xFFFF
        if not (1 <= width <= 4096 and 1 <= height <= 4096):
            return None
    return fmt, width, height, levels, dims


def scan_descriptors(system: bytes, video_bytes: int) -> list[Descriptor]:
    """Every 32-byte texture descriptor in a decoded chunk's system section whose level 0 (and palette) fits the
    chunk's video section. Word 5 (flags) has bit 31 set on every descriptor the Studio's ledgers know."""
    count = len(system) // 4
    if count < 8 or video_bytes <= 0:
        return []
    from .runtime_dependencies import require_numpy
    np = require_numpy("The texture-pack disc catalog")
    words = np.frombuffer(system, dtype="<u4", count=count)
    fmt_words = words[3:count - 4]
    flag_words = words[5:count - 2]
    candidates = np.nonzero(((fmt_words >> 4) & 0xF == 2) & ((flag_words & 0x80000000) != 0)
                            & ((fmt_words & 0x4) == 0) & ((fmt_words >> 28) == 0))[0]
    out: list[Descriptor] = []
    for i in candidates.tolist():
        unknown0, pixel, palette, word_format, word_size, flags = (int(v) for v in words[i:i + 6])
        parsed = _descriptor_fields(word_format, word_size)
        if parsed is None:
            continue
        fmt, width, height, levels, _dims = parsed
        size = level0_size(fmt, width, height)
        if pixel + size > video_bytes:
            continue
        if fmt == P8 and palette + PALETTE_BYTES > video_bytes:
            continue
        out.append(Descriptor(i * 4, pixel, palette, fmt, width, height, levels, word_format, word_size, flags))
    return out


# ---- catalog ------------------------------------------------------------------------------------------------

@dataclass
class CatalogRow:
    key: str
    wild: str
    kind: str
    outer: int
    chunk: int
    descriptor: int
    fmt: int
    width: int
    height: int
    levels: int
    name: str = ""
    changed: str = ""   # vs retail: "same", "changed", "new" ("" when not compared)
    file: str = ""      # the archive entry's file name when known (s16dd.iff), else its id in hex

    @property
    def position(self) -> tuple[int, int, int]:
        return self.outer, self.chunk, self.descriptor


_KNOWN_NAMES: dict[int, str] | None = None


def _catalog_entry(job: tuple[str, int]) -> tuple[list[dict], str | None]:
    global _KNOWN_NAMES
    if _KNOWN_NAMES is None:
        _KNOWN_NAMES = known_entry_names()
    image, index = job
    rows: list[dict] = []
    try:
        with DiscArchive(Path(image)) as archive:
            entry = archive.entries[index]
            data = archive.read_entry(entry)
        file_name = _KNOWN_NAMES.get(entry.name_id, f"0x{entry.name_id:08x}")
        chunks = list(iter_chunks(data))
    except (TexturePackError, txtr.TxtrError, OSError, ValueError) as exc:
        return rows, f"entry {index}: {exc}"
    for chunk in chunks:
        if chunk.video_bytes <= 0 or chunk.system_bytes < 0x20:
            continue
        try:
            output, _info = txtr.decode_chunk(data, chunk)
        except (txtr.TxtrError, ValueError):
            continue
        if len(output) < chunk.system_bytes + chunk.video_bytes:
            continue  # an uncompressed kind whose header words mean something else
        system = output[:chunk.system_bytes]
        video = output[chunk.system_bytes:chunk.system_bytes + chunk.video_bytes]
        name_by_offset: dict[int, str] = {}
        if chunk.kind == "TXTR":
            try:
                info = txtr.parse_texture(output, chunk)
                name_by_offset[info.descriptor_offset] = info.name
            except txtr.TxtrError:
                pass
        for d in scan_descriptors(system, len(video)):
            level0 = video[d.pixel_offset:d.pixel_offset + level0_size(d.fmt, d.width, d.height)]
            palette = video[d.palette_offset:d.palette_offset + PALETTE_BYTES] if d.fmt == P8 else None
            key = texture_key(d.fmt, d.width, d.height, level0, palette)
            rows.append({
                "key": key, "wild": parse_key(key).wild or "", "kind": chunk.kind, "outer": index,
                "chunk": chunk.index, "descriptor": d.offset, "fmt": d.fmt, "width": d.width,
                "height": d.height, "levels": d.levels, "name": name_by_offset.get(d.offset, ""),
                "file": file_name,
            })
    return rows, None


def catalog_disc(image: Path, *, jobs: int = 8, entries: Iterable[int] | None = None,
                 progress: Callable[[int, int], None] | None = None) -> tuple[list[CatalogRow], list[str]]:
    """Every keyable texture descriptor on the disc (all chunk kinds), in archive order."""
    image = Path(image).resolve()
    with DiscArchive(image) as archive:
        indices = list(entries) if entries is not None else [e.index for e in archive.entries]
    rows: list[CatalogRow] = []
    errors: list[str] = []
    jobs_list = [(str(image), i) for i in indices]
    done = 0
    if jobs <= 1:
        results = map(_catalog_entry, jobs_list)
        executor = None
    else:
        executor = ProcessPoolExecutor(max_workers=jobs)
        results = executor.map(_catalog_entry, jobs_list, chunksize=8)
    try:
        for found, error in results:
            rows.extend(CatalogRow(**r) for r in found)
            if error:
                errors.append(error)
            done += 1
            if progress:
                progress(done, len(jobs_list))
    finally:
        if executor is not None:
            executor.shutdown()
    return rows, errors


CATALOG_FIELDS = [f.name for f in fields(CatalogRow)]


def write_catalog(rows: Sequence[CatalogRow], path: Path, *, source: Mapping[str, object] | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        stream.write(f"# {SCHEMA_CATALOG} {json.dumps(dict(source or {}), sort_keys=True)}\n")
        writer = csv.DictWriter(stream, CATALOG_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            record = asdict(row)
            record["fmt"] = f"{row.fmt:02x}"
            writer.writerow(record)


def read_catalog(path: Path) -> list[CatalogRow]:
    with Path(path).open(encoding="utf-8") as stream:
        first = stream.readline()
        _require(first.startswith(f"# {SCHEMA_CATALOG}"), f"{path} is not a {SCHEMA_CATALOG} file")
        reader = csv.DictReader(stream, delimiter="\t")
        rows = []
        for r in reader:
            rows.append(CatalogRow(
                key=r["key"], wild=r["wild"], kind=r["kind"], outer=int(r["outer"]), chunk=int(r["chunk"]),
                descriptor=int(r["descriptor"]), fmt=int(r["fmt"], 16), width=int(r["width"]),
                height=int(r["height"]), levels=int(r["levels"]), name=r.get("name", ""),
                changed=r.get("changed", ""), file=r.get("file", "")))
    return rows


def compare_with_retail(rows: Sequence[CatalogRow], retail: Sequence[CatalogRow]) -> dict[str, int]:
    """Mark each row "same", "changed" (the mod rewrote that texture) or "new" (no retail texture there)."""
    by_position = {r.position: r.key for r in retail}
    counts = {"same": 0, "changed": 0, "new": 0}
    for row in rows:
        old = by_position.get(row.position)
        row.changed = "new" if old is None else ("same" if old == row.key else "changed")
        counts[row.changed] += 1
    return counts


def name_from_ledgers(rows: Sequence[CatalogRow], repo_root: Path) -> int:
    """Fill names for TSET and SCNE textures from the Studio's retail ledgers, joined by position. Returns how
    many rows got a name. (Positions are stable on built discs: builds rewrite entries in place.)"""
    assets = Path(repo_root) / "reports" / "assets"
    names: dict[tuple[int, int, int], str] = {}
    files: dict[int, str] = {}
    tset = assets / "nfl2k5_uniform_tset_textures.tsv"
    if tset.is_file():
        with tset.open(encoding="utf-8") as stream:
            for r in csv.DictReader(stream, delimiter="\t"):
                files[int(r["outer_index"])] = r["logical_name"]
                team = r.get("roster_current_abbreviations") or r.get("asset_code", "")
                names[(int(r["outer_index"]), int(r["tset_chunk_index"]), int(r["descriptor_offset"]))] = (
                    f"uniform {r['logical_name']} {team} {r['side_context']}/{r['name']}")
    scne = assets / "nfl2k5_scne_embedded_textures.tsv"
    if scne.is_file():
        with scne.open(encoding="utf-8") as stream:
            for r in csv.DictReader(stream, delimiter="\t"):
                materials = r.get("mapped_material_names", "")
                names[(int(r["outer_index"]), int(r["chunk_index"]), int(r["descriptor_offset"]))] = (
                    f"scene {r['scene_name']}#{r['index']}" + (f" ({materials})" if materials else ""))
    count = 0
    for row in rows:
        if row.file.startswith("0x") and row.outer in files:
            row.file = files[row.outer]
        if not row.name and row.position in names:
            row.name = names[row.position]
            count += 1
    return count


def guest_image(image: Path, row: CatalogRow, archive: DiscArchive | None = None) -> Image.Image:
    """The texture a catalog row keys, decoded from the disc to RGBA (P8, DXT1, A8R8G8B8 and A1R5G5B5; the
    Studio's verified decoder). This is the native art a 4x redraw starts from; no emulator run is needed."""
    own = archive is None
    archive = archive or DiscArchive(Path(image))
    try:
        entry = archive.entries[row.outer]
        data = archive.read_entry(entry)
    finally:
        if own:
            archive.close()
    chunks = list(iter_chunks(data))
    _require(row.chunk < len(chunks), f"{row.key}: entry {row.outer} has no chunk {row.chunk}")
    chunk = chunks[row.chunk]
    output, _ = txtr.decode_chunk(data, chunk)
    unknown0, pixel, palette, word_format, word_size, flags = struct.unpack_from("<6I", output, row.descriptor)
    info = txtr.TextureInfo(
        name=row.name, name_offset=0, descriptor_offset=row.descriptor, pixel_offset=pixel,
        palette_offset=palette, packed_format=word_format, packed_size=word_size, descriptor_flags=flags,
        dimensions=2, format_code=row.fmt, format_name=format_name(row.fmt), mip_levels=row.levels,
        width=row.width, height=row.height, depth=1)
    try:
        rgba = txtr.texture_to_rgba(output, chunk, info)
    except txtr.TxtrError as exc:
        raise TexturePackError(f"{row.key}: {exc}") from exc
    return Image.frombytes("RGBA", (row.width, row.height), rgba)


# ---- dump naming ----------------------------------------------------------------------------------------------

@dataclass
class DumpRow:
    key: str
    size: str
    fmt: str
    source: str          # "guest" (dumped), "pack" (already replaced)
    png: str
    match: str           # "exact", "any-palette", "none"
    names: str
    dynamic: bool


def name_dump(dump_dir: Path, rows: Sequence[CatalogRow]) -> list[DumpRow]:
    """Name every texture an Edition dump recorded, from a disc catalog. Textures with no catalog match are the
    runtime-composed or not-yet-decoded ones; textures at a VRAM offset the game rewrote often are dynamic."""
    dump_dir = Path(dump_dir)
    index = dump_dir / "index.tsv"
    _require(index.is_file(), f"{index} is missing (run the Edition with --dump)")
    exact: dict[str, list[CatalogRow]] = {}
    wild: dict[str, list[CatalogRow]] = {}
    for row in rows:
        exact.setdefault(row.key, []).append(row)
        if row.wild:
            wild.setdefault(row.wild, []).append(row)
    dynamic_offsets = set()
    rewrites = dump_dir / "rewrites.tsv"
    if rewrites.is_file():
        with rewrites.open(encoding="utf-8") as stream:
            for r in csv.DictReader(stream, delimiter="\t"):
                if int(r["rewrites"]) >= 8:
                    dynamic_offsets.add(r["vram_offset"])
    out = []
    with index.open(encoding="utf-8") as stream:
        for r in csv.DictReader(stream, delimiter="\t"):
            key = r["key"]
            hits = exact.get(key, [])
            match = "exact" if hits else "none"
            if not hits:
                try:
                    w = parse_key(key).wild
                except TexturePackError:
                    w = None
                hits = wild.get(w, []) if w else []
                match = "any-palette" if hits else "none"
            label = "; ".join(sorted({(h.name or f"{h.kind} {h.outer}:{h.chunk}@{h.descriptor}") for h in hits}))[:400]
            png = dump_dir / f"{key}.png"
            out.append(DumpRow(key, r["size"], r["fmt_name"], r.get("source", "guest"),
                               str(png) if png.is_file() else "", match, label,
                               r["vram_offset"] in dynamic_offsets))
    return out


# ---- redraw workspace -----------------------------------------------------------------------------------------

def make_workspace(targets: Sequence[tuple[str, str, Path | None]], out_dir: Path, *, scale: int = 4) -> Path:
    """One folder per texture: the guest image, a ``scale``x template to paint over (Lanczos, a starting point
    only), and ``workspace.json`` for ``build``. targets: (key, label, guest png or None)."""
    _require(scale in (2, 3, 4, 6, 8), "scale must be 2, 3, 4, 6 or 8")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "2k5-texture-workspace/1", "scale": scale, "entries": []}
    for key, label, guest in targets:
        parts = parse_key(key)
        folder = out_dir / re.sub(r"[^A-Za-z0-9._-]+", "_", (label or key))[:80]
        folder.mkdir(exist_ok=True)
        entry = {"key": key, "label": label, "guest": None, "template": None,
                 "paint": f"{folder.name}/{key}.png"}
        if guest and Path(guest).is_file():
            shutil.copyfile(guest, folder / "guest.png")
            with Image.open(folder / "guest.png") as im:
                big = im.convert("RGBA").resize((parts.width * scale, parts.height * scale), Image.LANCZOS)
            big.save(folder / f"template_{scale}x.png")
            entry["guest"] = f"{folder.name}/guest.png"
            entry["template"] = f"{folder.name}/template_{scale}x.png"
        manifest["entries"].append(entry)
    (out_dir / "workspace.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return out_dir / "workspace.json"


# ---- pack build, validate, install ------------------------------------------------------------------------------

@dataclass
class PackEntry:
    key: str
    file: str
    asset: str = ""
    guest: str = ""
    scale: float = 0.0
    notes: list[str] = field(default_factory=list)


def _image_from_source(source: Path) -> tuple[Image.Image, str]:
    """An RGBA image from a PNG/JPEG/... file, or the high-resolution preview of a .2ktexmaster bundle."""
    source = Path(source)
    if source.suffix.lower() == ".2ktexmaster":
        from . import texture_master
        bundle = texture_master.load_texture_master_bundle(source)
        image = Image.open(io.BytesIO(bundle.high_resolution_png)).convert("RGBA")
        return image, f"texture master {bundle.asset_id} ({bundle.high_resolution_scale}x preview)"
    with Image.open(source) as im:
        return im.convert("RGBA"), source.name


def _resolve_targets(spec: Mapping[str, object], catalog: Sequence[CatalogRow]) -> list[tuple[str, str]]:
    """A manifest entry's target -> [(key, asset label)]. Targets: {"key"}; {"name", "file"} (the catalog rows with
    that exact name in that archive file, e.g. "splayer" in "18H0.IFF"); {"name"} alone only when the name is in
    one archive entry (texture names such as splayer, logo or helmet00 repeat in all 634 uniform files, so a bare
    name would put one image on every team) or with "all": true; {"outer", "chunk"[, "descriptor"]}.
    "any_palette": true keys the "$" form."""
    wild = bool(spec.get("any_palette"))
    if "key" in spec:
        key = str(spec["key"])
        parse_key(key)
        return [(wild_key(key) if wild else key, str(spec.get("label", "")))]
    if "name" in spec:
        name = str(spec["name"])
        rows = [r for r in catalog if r.name == name]
        if "file" in spec:
            wanted = str(spec["file"]).casefold()
            rows = [r for r in rows if r.file.casefold() == wanted]
            _require(rows, f"no catalog texture is named {name!r} in {spec['file']!r}")
        else:
            _require(rows, f"no catalog texture is named {name!r}")
            entries = sorted({(r.outer, r.file) for r in rows})
            _require(len(entries) == 1 or bool(spec.get("all")),
                     f"{name!r} is in {len(entries)} archive entries (for example "
                     f"{', '.join(f or str(o) for o, f in entries[:4])}); add \"file\" to pick one, or "
                     "\"all\": true to replace it everywhere")
    else:
        _require("outer" in spec and "chunk" in spec, f"target needs key, name or outer+chunk: {dict(spec)}")
        rows = [r for r in catalog if r.outer == int(spec["outer"]) and r.chunk == int(spec["chunk"])
                and ("descriptor" not in spec or r.descriptor == int(spec["descriptor"]))]
        _require(rows, f"no catalog texture at outer {spec['outer']} chunk {spec['chunk']}")
    out = {}
    for r in rows:
        key = r.wild if (wild and r.wild) else r.key
        out[key] = r.name or f"{r.kind} {r.outer}:{r.chunk}@{r.descriptor}"
    return sorted(out.items())


def check_image_for_key(key: str, width: int, height: int) -> list[str]:
    """Problems (errors start with "ERROR") and advice for using a width x height image for this key."""
    parts = parse_key(key)
    notes = []
    sx, sy = width / parts.width, height / parts.height
    name, _unit, linear, _dxt = FORMATS.get(parts.fmt, ("?", 0, False, False))
    if linear and abs(sx - sy) > 0.01:
        notes.append(f"ERROR linear texture {name}: the image must scale both axes the same ({sx:.3f} vs {sy:.3f})")
    elif abs(sx - sy) > 0.01:
        notes.append(f"aspect ratio differs from the guest's ({width}x{height} for {parts.width}x{parts.height}); "
                     "it will be stretched to the same UV square")
    if sx < 1 or sy < 1:
        notes.append(f"smaller than the guest texture ({width}x{height} < {parts.width}x{parts.height})")
    if (width & (width - 1)) or (height & (height - 1)):
        notes.append("not a power of two (works; mip chains are cleaner with powers of two)")
    if max(width, height) > 8192:
        notes.append("ERROR larger than 8192 texels on a side (not every GPU samples it)")
    if parts.fmt in NO_ALPHA:
        notes.append("the guest format has no alpha: the image's alpha is ignored")
    return notes


def build_pack(manifest_path: Path, catalog: Sequence[CatalogRow], out_dir: Path, *,
               disc_label: str = "", overwrite: bool = False) -> dict:
    """Build a pack folder from a manifest:

        {"name": "...", "priority": 0, "description": "...",
         "entries": [{"image": "art/splayer_4x.png", "target": {"name": "splayer", "file": "18H0.IFF"}},
                     {"image": "x.2ktexmaster", "target": {"outer": 3741, "chunk": 11}},
                     {"image": "logo.png", "target": {"key": "x2_..."}, "group": "fields"}]}

    Image paths are relative to the manifest. Every target resolves against the catalog of the disc the pack is
    for (catalog_disc on that disc), so the keys are the keys of the textures the player's disc really uploads."""
    manifest_path = Path(manifest_path)
    spec = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(isinstance(spec.get("entries"), list) and spec["entries"], "the manifest has no entries")
    out_dir = Path(out_dir)
    if out_dir.exists():
        _require(overwrite, f"{out_dir} exists (pass overwrite)")
        shutil.rmtree(out_dir)
    (out_dir / "textures").mkdir(parents=True)
    entries: list[PackEntry] = []
    errors: list[str] = []
    for item in spec["entries"]:
        image_path = (manifest_path.parent / str(item["image"])).resolve()
        targets = _resolve_targets(item.get("target", {}), catalog)
        image, source_label = _image_from_source(image_path)
        group = re.sub(r"[^A-Za-z0-9._-]+", "_", str(item.get("group", "textures")))
        for key, label in targets:
            notes = check_image_for_key(key, image.width, image.height)
            errors += [f"{key}: {n}" for n in notes if n.startswith("ERROR")]
            rel = Path("textures") / group / f"{key}.png"
            (out_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            image.save(out_dir / rel, optimize=False, compress_level=6)
            parts = parse_key(key)
            entries.append(PackEntry(key, rel.as_posix(), label or source_label,
                                     f"{parts.width}x{parts.height} {format_name(parts.fmt)}",
                                     round(image.width / parts.width, 3), notes))
    _require(not errors, "the pack has images the Edition cannot use:\n  " + "\n  ".join(errors))
    pack = {
        "schema": SCHEMA_PACK,
        "name": str(spec.get("name") or out_dir.name),
        "description": str(spec.get("description", "")),
        "priority": int(spec.get("priority", 0)),
        "enabled": True,
        "game": {"title_id": TITLE_ID, "title": "ESPN NFL 2K5"},
        "key": KEY_VERSION,
        "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "disc": disc_label,
        "textures": {e.key: {k: v for k, v in asdict(e).items() if k != "key"} for e in entries},
    }
    (out_dir / "pack.json").write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8", newline="\n")
    return pack


def validate_pack(pack_dir: Path, catalog: Sequence[CatalogRow] | None = None) -> dict:
    """Check a pack folder the way the Edition reads it, plus the catalog of the disc it is meant for."""
    pack_dir = Path(pack_dir)
    report: dict[str, object] = {"pack": str(pack_dir), "images": 0, "errors": [], "warnings": [],
                                 "not_on_disc": []}
    errors: list[str] = report["errors"]  # type: ignore[assignment]
    warnings: list[str] = report["warnings"]  # type: ignore[assignment]
    meta = pack_dir / "pack.json"
    if meta.is_file():
        try:
            doc = json.loads(meta.read_text(encoding="utf-8"))
            if doc.get("schema") != SCHEMA_PACK:
                warnings.append(f"pack.json schema is {doc.get('schema')!r}, not {SCHEMA_PACK}")
            if doc.get("enabled") is False:
                warnings.append("pack.json says enabled: false (the Edition skips this pack)")
        except json.JSONDecodeError as exc:
            errors.append(f"pack.json is not valid JSON: {exc}")
    else:
        warnings.append("no pack.json (the Edition still loads the images; tools need it for names)")
    keys = {r.key for r in catalog} | {r.wild for r in catalog if r.wild} if catalog else None
    seen: dict[str, Path] = {}
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".png", ".dds"):
            continue
        stem = path.stem.lower()
        if not stem.startswith("x2_"):
            continue
        report["images"] += 1  # type: ignore[operator]
        try:
            parse_key(stem)
        except TexturePackError as exc:
            errors.append(f"{path.relative_to(pack_dir)}: {exc}")
            continue
        if stem in seen:
            warnings.append(f"{stem} twice: {seen[stem].relative_to(pack_dir)} and {path.relative_to(pack_dir)}"
                            " (the Edition keeps the first in folder order)")
        seen[stem] = path
        if path.suffix.lower() == ".png":
            try:
                with Image.open(path) as im:
                    width, height = im.size
            except OSError as exc:
                errors.append(f"{path.relative_to(pack_dir)}: unreadable PNG ({exc})")
                continue
            for note in check_image_for_key(stem, width, height):
                (errors if note.startswith("ERROR") else warnings).append(f"{stem}: {note}")
        if keys is not None and stem not in keys:
            report["not_on_disc"].append(stem)  # type: ignore[union-attr]
    return report


def install_pack(pack_dir: Path, packs_root: Path = DEFAULT_PACKS_ROOT, *, name: str | None = None,
                 overwrite: bool = False) -> Path:
    """Copy a pack into the Edition's packs folder and touch RELOAD (a running Edition re-reads the packs)."""
    pack_dir = Path(pack_dir)
    _require((pack_dir / "pack.json").is_file(), f"{pack_dir} has no pack.json")
    packs_root = Path(packs_root)
    packs_root.mkdir(parents=True, exist_ok=True)
    target = packs_root / (name or pack_dir.name)
    if target.exists():
        _require(overwrite, f"{target} exists (pass overwrite)")
        shutil.rmtree(target)
    shutil.copytree(pack_dir, target)
    reload_marker = packs_root / "RELOAD"
    reload_marker.write_text(time.strftime("%Y-%m-%dT%H:%M:%S") + "\n", encoding="utf-8", newline="\n")
    return target


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = [
    "CatalogRow", "DiscArchive", "DumpRow", "KeyParts", "TexturePackError", "build_pack", "catalog_disc",
    "guest_image",
    "check_image_for_key", "compare_with_retail", "install_pack", "level0_size", "make_workspace", "name_dump",
    "name_from_ledgers", "parse_key", "read_catalog", "scan_descriptors", "texture_key", "validate_pack",
    "wild_key", "write_catalog",
]

"""Shareable disc patches for NFL 2K5: the ``.2k5patch`` file.

Why this exists.  Every edit the studio makes is a byte-level change to a COPY
of the user's own disc image, and a finished copy is 6.3 GB of somebody else's
game -- sharing it is piracy.  What a second person actually needs is only the
bytes that differ from the base they already own, plus a way to prove that
their copy really is that base before one byte is written.  A ``.2k5patch``
carries exactly that, and alongside it the creator's own sources so the work
can be inspected, remixed and rebuilt:

* **byte runs** -- the finished bytes of every changed span, each pinned to the
  SHA-256 of the bytes it replaces.  Applying uses these and nothing else, and
  it refuses on the first run whose bytes are not the expected ones, before
  anything has been written;
* **assets/** -- the source files behind those bytes (PNG textures, WAV audio,
  text and layout JSON, or a whole studio ``.2k5mod`` project), stored
  byte-for-byte so a reader gets back exactly what the creator put in;
* **recipe** -- every studio operation with its parameters (throw ceiling /
  arc / realistic flag, code-cave flags, scorebug layout version and texture
  asset names, audio and text replacements) so the studio can rebuild the
  patch from sources on another base and a person can see what is in it.

This is NOT the studio's ``.2k5mod`` project archive
(:mod:`mod_editor.studio.project_archive`): a project stores only the user's
replacement files and never game bytes, while a patch stores the finished
bytes of the changed spans -- which is what makes it applicable without the
studio's source packs.  The two formats therefore keep different extensions; a
project can be embedded in a patch as one of its assets.

Layout of a pack (all members deflated)::

    manifest.json        {"format": 1, "kind": "2k5patch", ..., "ops": [...],
                          "assets": [...], "recipe": {...}}
    payload.bin          the new bytes of every run, concatenated in op order
    assets/<kind>/<name> the creator's source files, listed in the manifest

Offsets in ``ops`` are relative to the XDVDFS game partition, which is the file
offset in an extracted ``.xiso`` (partition base 0) and ``base + offset`` in a
raw dump that still carries the video partition in front.  The applier locates
the partition in the user's own image, so the same pack fits both dump shapes.

Nothing here loads a disc image into memory: images are diffed, copied and
verified in fixed-size blocks through positional reads and writes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
from typing import Any
import zipfile

from mod_editor.core import platform_compat

FORMAT = 1
KIND = "2k5patch"
EXTENSION = ".2k5patch"
GAME = "nfl2k5-xbox"
MANIFEST_MEMBER = "manifest.json"
PAYLOAD_MEMBER = "payload.bin"
ASSET_ROOT = "assets"
PROJECT_EXTENSION = ".2k5mod"

RETAIL_XISO_SIZE = 6_300_499_968
RETAIL_XISO_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"

BLOCK = 16 * 1024 * 1024          # diff / copy block
COALESCE_GAP = 64                 # unchanged bytes between two runs that still make one run
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_PAYLOAD_BYTES = 256 * 1024 * 1024   # a "patch" that replaces more than this is a disc, not a patch
MAX_ASSET_BYTES = 256 * 1024 * 1024     # one asset
MAX_ASSETS_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_ASSETS = 4096
MAX_PACK_BYTES = MAX_PAYLOAD_BYTES + MAX_ASSETS_TOTAL_BYTES + MAX_MANIFEST_BYTES
MAX_RUNS = 200_000
MAX_OPERATIONS = 4096
MAX_TEXT = {"name": 120, "author": 120, "version": 40, "description": 4000, "base_label": 200}
ASSET_KINDS = ("texture", "audio", "text", "layout", "project", "other")
_KIND_BY_SUFFIX = {
    ".png": "texture", ".bmp": "texture", ".tga": "texture", ".dds": "texture", ".jpg": "texture", ".jpeg": "texture",
    ".wav": "audio", ".flac": "audio", ".ogg": "audio", ".mp3": "audio",
    ".txt": "text", ".csv": "text", ".md": "text",
    ".json": "layout", ".yaml": "layout", ".yml": "layout", ".toml": "layout",
    PROJECT_EXTENSION: "project",
}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ +()\-]{0,199}$")

EXPORT_SCHEMA = "nfl2k5_modpack_export/v1"
CHECK_SCHEMA = "nfl2k5_modpack_check/v1"
APPLY_SCHEMA = "nfl2k5_modpack_apply/v1"
EXTRACT_SCHEMA = "nfl2k5_modpack_extract/v1"

ProgressSink = Callable[[str, int, int], None]
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ModpackError(ValueError):
    """A pack, an image or a request that must not be acted on."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModpackError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _no_progress(stage: str, done: int, total: int) -> None:
    return None


# --------------------------------------------------------------------------
# Files


def _regular_path(path: Path | str, what: str) -> Path:
    path = Path(path).expanduser()
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise ModpackError(f"{what} does not exist: {path}") from exc
    _require(not stat.S_ISLNK(info.st_mode), f"{what} must not be a symbolic link: {path}")
    _require(stat.S_ISREG(info.st_mode), f"{what} must be a regular file: {path}")
    return path


def _open(path: Path, flags: int, mode: int = 0o644) -> int:
    return os.open(
        path,
        flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0),
        mode,
    )


def _identity(descriptor: int) -> tuple[int, int]:
    info = os.fstat(descriptor)
    return info.st_dev, info.st_ino


def _pread_exact(descriptor: int, length: int, offset: int, what: str) -> bytes:
    chunks: list[bytes] = []
    position = offset
    remaining = length
    while remaining > 0:
        chunk = platform_compat.pread(descriptor, remaining, position)
        _require(bool(chunk), f"short read at 0x{position:x} while reading {what}")
        chunks.append(chunk)
        position += len(chunk)
        remaining -= len(chunk)
    return chunks[0] if len(chunks) == 1 else b"".join(chunks)


def _pwrite_all(descriptor: int, data: bytes, offset: int, what: str) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = platform_compat.pwrite(descriptor, view[written:], offset + written)
        _require(count > 0, f"short write at 0x{offset + written:x} while writing {what}")
        written += count


def _read_small_file(path: Path, what: str, limit: int) -> bytes:
    resolved = _regular_path(path, what)
    size = os.lstat(resolved).st_size
    _require(size <= limit, f"{what} is {size} bytes; the limit is {limit}")
    fd = _open(resolved, os.O_RDONLY)
    try:
        return _pread_exact(fd, size, 0, what) if size else b""
    finally:
        os.close(fd)


def _xdvdfs_module():
    """The proven XDVDFS reader lives in tools/; import it lazily."""

    try:
        import nfl_uniform_color_xiso_direct_patch as xc  # type: ignore
        return xc
    except ImportError:
        tools = Path(__file__).resolve().parents[2] / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        import nfl_uniform_color_xiso_direct_patch as xc  # type: ignore
        return xc


def partition_base(descriptor: int, size: int) -> int | None:
    """Byte offset of the XDVDFS game partition, or None when the file has none."""

    try:
        xc = _xdvdfs_module()
        return int(xc.locate_xdvdfs_base(descriptor, size))
    except Exception:  # noqa: BLE001 -- any parse failure means "not a disc image"
        return None


@dataclass(frozen=True)
class Region:
    name: str
    offset: int      # absolute file offset in the image it was read from
    size: int


def image_regions(descriptor: int, size: int) -> tuple[Region, ...]:
    """Every file extent in the image, sorted by offset ([] for a non-disc file)."""

    try:
        xc = _xdvdfs_module()
        entries, _directory = xc.parse_xdvdfs(descriptor, size)
    except Exception:  # noqa: BLE001
        return ()
    regions = [
        Region(entry.path, int(entry.byte_offset), int(entry.size))
        for entry in entries.values()
        if not (entry.attributes & 0x10) and entry.size > 0
    ]
    regions.sort(key=lambda region: region.offset)
    return tuple(regions)


def _region_of(regions: Sequence[Region], offset: int) -> str | None:
    lo, hi = 0, len(regions)
    while lo < hi:
        mid = (lo + hi) // 2
        if regions[mid].offset <= offset:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        return None
    region = regions[lo - 1]
    return region.name if offset < region.offset + region.size else None


# --------------------------------------------------------------------------
# Diffing

_STEPS = (1 << 19, 1 << 14, 1 << 9, 16)   # 512 KiB, 16 KiB, 512 B, 16 B, then bytes


def differences(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """Exact differing ``[start, end)`` ranges between two equal-length buffers.

    Slice comparisons are C memcmp, so the buffer is narrowed in four steps and
    only the last 16-byte pieces are walked byte by byte.  A 16 MiB block with
    a handful of edits costs a few milliseconds, not the seconds of a pure
    Python byte loop.
    """

    _require(len(a) == len(b), "difference inputs have unequal sizes")
    result: list[tuple[int, int]] = []

    def bytes_walk(lo: int, hi: int) -> None:
        start = -1
        for index in range(lo, hi):
            if a[index] != b[index]:
                if start < 0:
                    start = index
            elif start >= 0:
                result.append((start, index))
                start = -1
        if start >= 0:
            result.append((start, hi))

    def scan(lo: int, hi: int, level: int) -> None:
        if level >= len(_STEPS):
            bytes_walk(lo, hi)
            return
        step = _STEPS[level]
        for start in range(lo, hi, step):
            end = min(start + step, hi)
            if a[start:end] != b[start:end]:
                scan(start, end, level + 1)

    if a != b:
        scan(0, len(a), 0)
    return result


def coalesce(ranges: Sequence[tuple[int, int]], gap: int = COALESCE_GAP) -> list[tuple[int, int]]:
    """Merge sorted ranges separated by fewer than ``gap`` unchanged bytes."""

    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if merged and start - merged[-1][1] < gap:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def diff_descriptors(
    base: int,
    patched: int,
    size: int,
    *,
    block: int = BLOCK,
    gap: int = COALESCE_GAP,
    hash_streams: bool = True,
    progress: ProgressSink | None = None,
) -> tuple[list[tuple[int, int]], str | None, str | None]:
    """Streaming diff: coalesced differing ranges plus both whole-file digests."""

    report = progress or _no_progress
    base_hash = hashlib.sha256() if hash_streams else None
    patched_hash = hashlib.sha256() if hash_streams else None
    runs: list[tuple[int, int]] = []
    position = 0
    while position < size:
        request = min(block, size - position)
        left = _pread_exact(base, request, position, "the base image")
        right = _pread_exact(patched, request, position, "the patched image")
        if base_hash is not None and patched_hash is not None:
            base_hash.update(left)
            patched_hash.update(right)
        if left != right:
            local = [(position + s, position + e) for s, e in differences(left, right)]
            runs = coalesce(runs + local, gap) if runs else coalesce(local, gap)
        position += request
        report("Comparing images", position, size)
    return (
        runs,
        base_hash.hexdigest() if base_hash else None,
        patched_hash.hexdigest() if patched_hash else None,
    )


# --------------------------------------------------------------------------
# Manifest


@dataclass(frozen=True)
class Run:
    offset: int            # relative to the game partition
    length: int
    expected_sha256: str   # of the bytes being replaced
    new_sha256: str        # of the replacement bytes
    payload_offset: int
    region: str | None = None

    def as_json(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "op": "replace",
            "offset": self.offset,
            "length": self.length,
            "expected_sha256": self.expected_sha256,
            "new_sha256": self.new_sha256,
            "payload_offset": self.payload_offset,
        }
        if self.region is not None:
            item["region"] = self.region
        return item


@dataclass(frozen=True)
class Asset:
    path: str              # zip member, always "assets/<kind>/<name>"
    kind: str
    size: int
    sha256: str
    role: str | None = None        # what the studio used it for, e.g. "scorebug.score_buga"
    source_name: str | None = None  # the creator's original file name

    def as_json(self) -> dict[str, Any]:
        item: dict[str, Any] = {"path": self.path, "kind": self.kind, "size": self.size, "sha256": self.sha256}
        if self.role:
            item["role"] = self.role
        if self.source_name:
            item["source_name"] = self.source_name
        return item


@dataclass(frozen=True)
class Manifest:
    name: str
    author: str
    version: str
    description: str
    created: str
    tool: dict[str, Any]
    base: dict[str, Any]
    result: dict[str, Any]
    payload: dict[str, Any]
    runs: tuple[Run, ...]
    assets: tuple[Asset, ...] = ()
    recipe: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_bytes(self) -> int:
        return sum(run.length for run in self.runs)

    @property
    def base_is_retail(self) -> bool:
        return bool(self.base.get("is_retail"))

    @property
    def operations(self) -> list[dict[str, Any]]:
        items = self.recipe.get("operations")
        return [dict(item) for item in items] if isinstance(items, list) else []

    def region_summary(self) -> list[dict[str, Any]]:
        counts: dict[str, list[int]] = {}
        for run in self.runs:
            entry = counts.setdefault(run.region or "(outside any file)", [0, 0])
            entry[0] += 1
            entry[1] += run.length
        return [{"name": name, "runs": runs, "bytes": total}
                for name, (runs, total) in sorted(counts.items(), key=lambda item: -item[1][1])]


def _text(value: Any, key: str, *, required: bool = False) -> str:
    if value is None:
        value = ""
    _require(isinstance(value, str), f"manifest {key} must be text")
    value = value.strip()
    _require(len(value) <= MAX_TEXT.get(key, 4000), f"manifest {key} is longer than {MAX_TEXT.get(key, 4000)} characters")
    _require("\0" not in value, f"manifest {key} contains a NUL byte")
    if required:
        _require(bool(value), f"manifest {key} is required")
    return value


def _hex64(value: Any, key: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    _require(isinstance(value, str) and bool(_HEX64.match(value)), f"manifest {key} is not a SHA-256 hex digest")
    return value


def _int(value: Any, key: str, *, minimum: int = 0) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"manifest {key} must be an integer")
    _require(value >= minimum, f"manifest {key} must be at least {minimum}")
    return value


def _asset_path(value: Any, key: str) -> str:
    _require(isinstance(value, str), f"{key} must be text")
    parts = value.split("/")
    _require(len(parts) == 3 and parts[0] == ASSET_ROOT and parts[1] in ASSET_KINDS,
             f"{key} must look like {ASSET_ROOT}/<kind>/<name>: {value!r}")
    _require(bool(_SAFE_NAME.match(parts[2])) and parts[2] not in (".", ".."),
             f"{key} has an unsafe file name: {parts[2]!r}")
    return value


def parse_manifest(document: Mapping[str, Any]) -> Manifest:
    """Validate a manifest completely; anything questionable is a refusal."""

    _require(isinstance(document, Mapping), "manifest is not a JSON object")
    _require(document.get("format") == FORMAT, f"unsupported patch format {document.get('format')!r} (this build reads format {FORMAT})")
    _require(document.get("kind") == KIND, "this file is not a 2K5 disc patch")
    _require(document.get("game") == GAME, f"patch is for {document.get('game')!r}, not {GAME}")

    base = document.get("base")
    _require(isinstance(base, Mapping), "manifest base is missing")
    base_size = _int(base.get("size"), "base.size", minimum=1)
    base_sha = _hex64(base.get("sha256"), "base.sha256", optional=True)
    base_partition = _int(base.get("partition_base", 0), "base.partition_base")
    base_doc = {
        "size": base_size,
        "sha256": base_sha,
        "partition_base": base_partition,
        "is_retail": bool(base.get("is_retail")) and base_size == RETAIL_XISO_SIZE and base_sha == RETAIL_XISO_SHA256,
        "label": _text(base.get("label"), "base_label"),
    }

    result = document.get("result") or {}
    _require(isinstance(result, Mapping), "manifest result must be an object")
    result_doc = {
        "size": _int(result.get("size", base_size), "result.size", minimum=1),
        "sha256": _hex64(result.get("sha256"), "result.sha256", optional=True),
    }
    _require(result_doc["size"] == base_size, "format 1 patches keep the image size; result.size differs from base.size")

    payload = document.get("payload")
    _require(isinstance(payload, Mapping), "manifest payload is missing")
    payload_doc = {
        "member": payload.get("member", PAYLOAD_MEMBER),
        "length": _int(payload.get("length"), "payload.length"),
        "sha256": _hex64(payload.get("sha256"), "payload.sha256"),
    }
    _require(payload_doc["member"] == PAYLOAD_MEMBER, "manifest names an unknown payload member")
    _require(payload_doc["length"] <= MAX_PAYLOAD_BYTES, "payload is larger than a patch may be")

    ops = document.get("ops")
    _require(isinstance(ops, list) and ops, "manifest has no ops")
    _require(len(ops) <= MAX_RUNS, f"manifest has more than {MAX_RUNS} ops")
    runs: list[Run] = []
    cursor = -1
    payload_cursor = 0
    for index, item in enumerate(ops):
        _require(isinstance(item, Mapping), f"op {index} is not an object")
        _require(item.get("op") == "replace", f"op {index} is not a replace op")
        offset = _int(item.get("offset"), f"op {index} offset")
        length = _int(item.get("length"), f"op {index} length", minimum=1)
        _require(base_partition + offset + length <= base_size, f"op {index} extends past the base image")
        _require(offset > cursor, f"op {index} overlaps or precedes the op before it")
        payload_offset = _int(item.get("payload_offset"), f"op {index} payload_offset")
        _require(payload_offset == payload_cursor, f"op {index} payload_offset does not follow the op before it")
        _require(payload_offset + length <= payload_doc["length"], f"op {index} extends past the payload")
        region = item.get("region")
        if region is not None:
            _require(isinstance(region, str) and len(region) <= 260, f"op {index} region is not a short name")
        runs.append(Run(
            offset=offset,
            length=length,
            expected_sha256=_hex64(item.get("expected_sha256"), f"op {index} expected_sha256") or "",
            new_sha256=_hex64(item.get("new_sha256"), f"op {index} new_sha256") or "",
            payload_offset=payload_offset,
            region=region,
        ))
        cursor = offset + length - 1
        payload_cursor += length
    _require(payload_cursor == payload_doc["length"], "payload length does not equal the sum of the ops")

    assets_doc = document.get("assets") or []
    _require(isinstance(assets_doc, list), "manifest assets must be a list")
    _require(len(assets_doc) <= MAX_ASSETS, f"manifest lists more than {MAX_ASSETS} assets")
    assets: list[Asset] = []
    seen: set[str] = set()
    assets_total = 0
    for index, item in enumerate(assets_doc):
        _require(isinstance(item, Mapping), f"asset {index} is not an object")
        path = _asset_path(item.get("path"), f"asset {index} path")
        _require(path not in seen, f"asset {index} repeats {path}")
        seen.add(path)
        kind = path.split("/")[1]
        _require(item.get("kind", kind) == kind, f"asset {index} kind does not match its folder")
        size = _int(item.get("size"), f"asset {index} size")
        _require(size <= MAX_ASSET_BYTES, f"asset {index} is larger than {MAX_ASSET_BYTES} bytes")
        assets_total += size
        role = item.get("role")
        source_name = item.get("source_name")
        if role is not None:
            _require(isinstance(role, str) and len(role) <= 120, f"asset {index} role is not a short name")
        if source_name is not None:
            _require(isinstance(source_name, str) and len(source_name) <= 260, f"asset {index} source_name is not a short name")
        assets.append(Asset(path=path, kind=kind, size=size, sha256=_hex64(item.get("sha256"), f"asset {index} sha256") or "",
                            role=role or None, source_name=source_name or None))
    _require(assets_total <= MAX_ASSETS_TOTAL_BYTES, "assets exceed the pack's 1 GiB asset limit")

    tool = document.get("tool") or {}
    _require(isinstance(tool, Mapping), "manifest tool must be an object")
    recipe = document.get("recipe") or {}
    _require(isinstance(recipe, Mapping), "manifest recipe must be an object")
    operations = recipe.get("operations", [])
    _require(isinstance(operations, list) and len(operations) <= MAX_OPERATIONS, "recipe operations must be a short list")
    for index, operation in enumerate(operations):
        _require(isinstance(operation, Mapping) and isinstance(operation.get("op"), str) and 0 < len(operation["op"]) <= 64,
                 f"recipe operation {index} needs a short 'op' name")
        for key, value in operation.items():
            if key in ("asset", "assets") or key.endswith("_asset"):
                for candidate in (value.values() if isinstance(value, Mapping) else value if isinstance(value, list) else [value]):
                    _require(candidate is None or (isinstance(candidate, str) and candidate in seen),
                             f"recipe operation {index} names an asset the pack does not carry: {candidate!r}")

    return Manifest(
        name=_text(document.get("name"), "name", required=True),
        author=_text(document.get("author"), "author"),
        version=_text(document.get("version"), "version"),
        description=_text(document.get("description"), "description"),
        created=_text(document.get("created"), "created"),
        tool={"name": _text(tool.get("name"), "name"), "version": _text(tool.get("version"), "version")},
        base=base_doc,
        result=result_doc,
        payload=payload_doc,
        runs=tuple(runs),
        assets=tuple(assets),
        recipe=dict(recipe),
        raw=dict(document),
    )


# --------------------------------------------------------------------------
# Reading a pack


@dataclass
class Pack:
    path: Path
    manifest: Manifest
    size: int
    _payload: bytes | None = None

    def _member(self, name: str, expected_size: int, what: str) -> bytes:
        with zipfile.ZipFile(self.path) as archive:
            try:
                info = archive.getinfo(name)
            except KeyError as exc:
                raise ModpackError(f"{what} is listed in the manifest but missing from the pack: {name}") from exc
            _require(info.file_size == expected_size, f"{what} member size differs from the manifest: {name}")
            with archive.open(info) as stream:
                data = stream.read(expected_size + 1)
        _require(len(data) == expected_size, f"{what} member is not the declared length: {name}")
        return data

    def payload(self) -> bytes:
        """The verified replacement bytes (read once, then cached)."""

        if self._payload is None:
            data = self._member(PAYLOAD_MEMBER, self.manifest.payload["length"], "payload")
            _require(_sha256(data) == self.manifest.payload["sha256"], "payload digest does not match the manifest; the file is damaged or edited")
            self._payload = data
        return self._payload

    def new_bytes(self, run: Run) -> bytes:
        data = self.payload()
        return data[run.payload_offset: run.payload_offset + run.length]

    def asset(self, path: str) -> Asset:
        for asset in self.manifest.assets:
            if asset.path == path:
                return asset
        raise ModpackError(f"the pack has no asset {path}")

    def read_asset(self, path: str) -> bytes:
        """One asset's bytes, verified against the manifest digest."""

        asset = self.asset(path)
        data = self._member(asset.path, asset.size, "asset")
        _require(_sha256(data) == asset.sha256, f"asset digest does not match the manifest: {asset.path}")
        return data


def load(pack_path: Path | str) -> Pack:
    """Open and validate a ``.2k5patch`` (manifest fully, payload and assets lazily)."""

    path = _regular_path(pack_path, "patch file")
    size = os.lstat(path).st_size
    _require(0 < size <= MAX_PACK_BYTES, f"patch file is {size} bytes; not a 2K5 disc patch")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            _require(MANIFEST_MEMBER in names and PAYLOAD_MEMBER in names, "not a 2K5 disc patch (manifest.json / payload.bin missing)")
            _require(not any(info.flag_bits & 1 for info in infos), "the pack contains an encrypted member")
            info = archive.getinfo(MANIFEST_MEMBER)
            _require(info.file_size <= MAX_MANIFEST_BYTES, "manifest is too large")
            _require(archive.getinfo(PAYLOAD_MEMBER).file_size <= MAX_PAYLOAD_BYTES, "payload is larger than a patch may be")
            with archive.open(info) as stream:
                text = stream.read(info.file_size + 1)
    except zipfile.BadZipFile as exc:
        raise ModpackError(f"not a 2K5 disc patch (not a zip archive): {path.name}") from exc
    _require(len(text) == info.file_size, "manifest member is not the declared length")
    try:
        document = json.loads(text.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModpackError(f"manifest is not valid JSON: {exc}") from exc
    manifest = parse_manifest(document)
    for asset in manifest.assets:
        _require(asset.path in names, f"asset listed in the manifest is missing from the pack: {asset.path}")
    return Pack(path=path, manifest=manifest, size=size)


def inspect(pack: Pack | Path | str) -> dict[str, Any]:
    """Everything a person needs to decide whether to apply a pack."""

    loaded = pack if isinstance(pack, Pack) else load(pack)
    manifest = loaded.manifest
    return {
        "path": str(loaded.path),
        "pack_bytes": loaded.size,
        "format": FORMAT,
        "name": manifest.name,
        "author": manifest.author,
        "version": manifest.version,
        "description": manifest.description,
        "created": manifest.created,
        "tool": dict(manifest.tool),
        "base": dict(manifest.base),
        "result": dict(manifest.result),
        "runs": len(manifest.runs),
        "bytes": manifest.total_bytes,
        "first_offset": min(run.offset for run in manifest.runs),
        "last_offset": max(run.offset + run.length for run in manifest.runs),
        "regions": manifest.region_summary(),
        "assets": [asset.as_json() for asset in manifest.assets],
        "assets_bytes": sum(asset.size for asset in manifest.assets),
        "recipe": dict(manifest.recipe),
        "operations": manifest.operations,
        "recipe_lines": describe_recipe(manifest.recipe),
    }


def extract_assets(pack: Pack | Path | str, directory: Path | str, *, overwrite: bool = False) -> dict[str, Any]:
    """Write every asset (verified) plus ``recipe.json`` and ``manifest.json`` under ``directory``."""

    loaded = pack if isinstance(pack, Pack) else load(pack)
    root = Path(directory).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def put(relative: str, data: bytes) -> None:
        destination = root / PurePosixPath(relative)
        _require(root in destination.parents or destination == root, f"refusing to write outside {root}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            _require(overwrite, f"already exists: {destination}")
            _require(stat.S_ISREG(os.lstat(destination).st_mode), f"not a regular file: {destination}")
            destination.unlink()
        fd = _open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
        except BaseException:
            raise
        written.append(str(destination))

    for asset in loaded.manifest.assets:
        put(asset.path, loaded.read_asset(asset.path))
    put("recipe.json", json.dumps(loaded.manifest.recipe, indent=1).encode("utf-8"))
    put(MANIFEST_MEMBER, json.dumps(loaded.manifest.raw, indent=1).encode("utf-8"))
    return {"schema": EXTRACT_SCHEMA, "pack": str(loaded.path), "directory": str(root), "files": written,
            "assets": len(loaded.manifest.assets)}


# --------------------------------------------------------------------------
# Recipe recognition (display and rebuild metadata; applying always uses the byte runs)


def _throw_module():
    from mod_editor.core import nfl2k5_throw_tuning as tt
    return tt


def _scorebug_assets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "nfl2k5_scorebug_espn"


SCOREBUG_TEXTURE_ROLES = (
    ("score_buga", "score_buga_modern.png"),
    ("shield_espn", "shield_espn_modern.png"),
    ("digital_font", "digital_font_modern.png"),
    ("NAVTEXTURE", "NAVTEXTURE_modern.png"),
)


class _SeasonStatus:
    """Adapter: the season-length module reports per-group states; the recogniser wants one word."""

    @staticmethod
    def status(payload: bytes) -> str:
        from mod_editor.core import nfl2k5_season_length
        return nfl2k5_season_length.simple_status(payload)


def recognise_recipe(base_fd: int, patched_fd: int, size: int, base_path: Path, patched_path: Path) -> dict[str, Any]:
    """Best-effort labels for studio-made edits found between base and patched.

    Returns ``{"detected": {...}, "operations": [...], "auto_assets": [...]}``
    where ``operations`` carry the parameters the studio would need to redo
    each edit and ``auto_assets`` name the studio-shipped source files behind
    them (bundled by :func:`export` when present on this machine).
    """

    detected: dict[str, Any] = {}
    operations: list[dict[str, Any]] = []
    auto_assets: list[dict[str, Any]] = []
    try:
        tt = _throw_module()
        offset, length = tt.image_xbe_extent(base_fd, size)
    except Exception:  # noqa: BLE001 -- no recognisable default.xbe: nothing to label
        return {"detected": detected, "operations": operations, "auto_assets": auto_assets}
    try:
        base_xbe = _pread_exact(base_fd, length, offset, "base default.xbe")
        patched_xbe = _pread_exact(patched_fd, length, offset, "patched default.xbe")
    except ModpackError:
        return {"detected": detected, "operations": operations, "auto_assets": auto_assets}
    base_digest, patched_digest = _sha256(base_xbe), _sha256(patched_xbe)
    detected["default_xbe"] = {
        "changed": base_xbe != patched_xbe,
        "base_sha256": base_digest,
        "patched_sha256": patched_digest,
        "base_is_retail": base_digest == tt.RETAIL_XBE_SHA256,
    }
    if base_xbe != patched_xbe:
        from mod_editor.core import (nfl2k5_accel_ramp, nfl2k5_camera, nfl2k5_catch_slider, nfl2k5_draft_ai,
                                     nfl2k5_edge_rename, nfl2k5_kick_rules, nfl2k5_modern_positions,
                                     nfl2k5_position_pools, nfl2k5_progression, nfl2k5_returner_fix,
                                     nfl2k5_season_length, nfl2k5_widescreen, nfl2k5_overtime, nfl2k5_seven_on_seven)
        for label, module in (("catch_slider", nfl2k5_catch_slider),
                              ("accel_ramp", nfl2k5_accel_ramp),
                              ("draft_ai", nfl2k5_draft_ai),
                              ("returner_fix", nfl2k5_returner_fix),
                              ("progression", nfl2k5_progression),
                              ("edge_rename", nfl2k5_edge_rename),
                              ("scheme_labels", nfl2k5_modern_positions),
                              ("camera", nfl2k5_camera),
                              ("kick_rules", nfl2k5_kick_rules),
                              ("position_pools", nfl2k5_position_pools),
                              ("season_2026", _SeasonStatus),
                              ("widescreen", nfl2k5_widescreen),
                              ("overtime", nfl2k5_overtime),
                              ("seven_on_seven", nfl2k5_seven_on_seven)):
            try:
                before, after = module.status(base_xbe), module.status(patched_xbe)
            except Exception:  # noqa: BLE001
                continue
            if before != after:
                detected[label] = {"base": before, "patched": after}
                if label == "kick_rules" and after == "power_only":
                    operations.append({"op": "kick_power", "enabled": True, "status": after})
                else:
                    operations.append({"op": label, "enabled": after == "applied", "status": after})
        try:
            before = tt.infer_settings(tt.read_curves(base_xbe), tt.arc_table_status(base_xbe))
            after = tt.infer_settings(tt.read_curves(patched_xbe), tt.arc_table_status(patched_xbe))
            if before != after:
                settings = {"max_deep_yards": after.max_deep_yards, "arc": after.arc, "realistic_flight": after.realistic_flight,
                            "arc_by_distance": getattr(after, "arc_by_distance", False)}
                detected["throw_tuning"] = {
                    "base": {"max_deep_yards": before.max_deep_yards, "arc": before.arc, "realistic_flight": before.realistic_flight,
                             "arc_by_distance": getattr(before, "arc_by_distance", False)},
                    "patched": settings,
                }
                operations.append({"op": "throw_tuning", **settings})
        except Exception:  # noqa: BLE001
            pass
    try:
        tools = Path(__file__).resolve().parents[2] / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        import importlib
        layout = importlib.import_module("nfl2k5_scorebug_layout")
        before, after = layout.status(Path(base_path)), layout.status(Path(patched_path))
        if before != after:
            version = int(layout.LAYOUT_VERSION)
            detected["scorebug_layout"] = {"base": before, "patched": after, "layout_version": version}
            if after == "applied":
                textures: dict[str, str | None] = {}
                folder = _scorebug_assets_dir()
                for role, file_name in SCOREBUG_TEXTURE_ROLES:
                    candidate = folder / file_name
                    if candidate.is_file():
                        member = f"{ASSET_ROOT}/texture/{file_name}"
                        textures[role] = member
                        auto_assets.append({"path": candidate, "member": member, "role": f"scorebug.{role}"})
                operations.append({"op": "scorebug_layout", "layout_version": version, "freeze_elements": True,
                                   "textures_asset": textures})
    except (Exception, SystemExit):  # noqa: BLE001 -- the layout tool exits when its assets are absent
        pass
    try:
        from mod_editor.core import nfl2k5_team_history as _team_history
        before, after = _team_history.status(Path(base_path)), _team_history.status(Path(patched_path))
        if before != after:
            detected["team_history"] = {"base": before, "patched": after}
            if after in ("applied", "applied-custom"):
                op: dict[str, Any] = {"op": "team_history", "enabled": True, "status": after,
                                      "source": "retail" if after == "applied" else "custom"}
                if after == "applied" and _team_history.SHIPPED_CSV.is_file():
                    member = f"{ASSET_ROOT}/text/{_team_history.SHIPPED_CSV.name}"
                    auto_assets.append({"path": _team_history.SHIPPED_CSV, "member": member, "role": "team_history.csv"})
                    op["csv_asset"] = member
                operations.append(op)
    except Exception:  # noqa: BLE001
        pass
    try:
        from mod_editor.core import nfl2k5_prospect_names as _prospect_names
        before, after = _prospect_names.image_status(Path(base_path)), _prospect_names.image_status(Path(patched_path))
        if before != after:
            detected["prospect_names"] = {"base": before, "patched": after}
            if after in ("applied", "applied-custom"):
                op = {"op": "prospect_names", "enabled": True, "status": after,
                      "source": "modern" if after == "applied" else "custom"}
                if after == "applied" and _prospect_names.SHIPPED_CSV.is_file():
                    member = f"{ASSET_ROOT}/text/{_prospect_names.SHIPPED_CSV.name}"
                    auto_assets.append({"path": _prospect_names.SHIPPED_CSV, "member": member, "role": "prospect_names.csv"})
                    op["csv_asset"] = member
                operations.append(op)
    except Exception:  # noqa: BLE001
        pass
    return {"detected": detected, "operations": operations, "auto_assets": auto_assets}


def describe_operation(operation: Mapping[str, Any]) -> str:
    op = str(operation.get("op", "?"))
    if op == "throw_tuning":
        return (f"Throw Distance & Arc: max deep {operation.get('max_deep_yards')} yd, arc {operation.get('arc')}"
                + (", realistic flight" if operation.get("realistic_flight") else "")
                + (", arc by distance (retail to 40 yd, 45-60 high, 63+ flat)" if operation.get("arc_by_distance") else ""))
    if op == "team_history":
        source = "built-in nflverse data" if operation.get("source") == "retail" else "a custom CSV"
        return f"Real team history on the Player Card for the roster's past seasons ({source}; franchises created from the copy)"
    if op == "prospect_names":
        source = "built-in nflverse 2015-2025 list" if operation.get("source") == "modern" else "a custom CSV"
        return f"Modern draft-prospect names in the generated-player pool ({source}; recorded surnames keep their call-outs, new ones are announced by number; franchises created from the copy)"
    if op in ("catch_slider", "accel_ramp", "draft_ai", "returner_fix", "progression", "edge_rename", "scheme_labels", "camera", "kick_rules", "kick_power", "position_pools", "season_2026", "widescreen", "overtime", "seven_on_seven"):
        label = {"catch_slider": "Catch slider cave", "accel_ramp": "Acceleration ramp cave", "draft_ai": "Franchise draft AI",
                 "returner_fix": "KR/PR returner fix", "progression": "NFL-shaped progression", "edge_rename": "DE -> EDGE rename",
                 "scheme_labels": "Scheme depth-chart labels (SAM/MIKE/WILL, EDGE, NT)", "camera": "Standard camera = the Far look",
                 "kick_rules": "Modern kicking (35/35/15, ~70-yd legs)",
                 "kick_power": "Kicking power only (~70-yd legs for elite kickers, retail kick spots)",
                 "position_pools": "One EDGE / LB / interior pool across 4-3 and 3-4 (XBE + playbooks + rosters)",
                 "season_2026": "2026 franchise (real schedule, 17 games / 18 weeks, 3-game preseason, 14-team playoffs, 2026 dates, rookie birth years)",
                 "widescreen": "Widescreen hor+ 16:9 (needs xemu aspect 16x9)",
                 "overtime": "Modern overtime (both possess, 10-min regular season, playoffs to a winner)",
                 "seven_on_seven": "7-on-7 practice mode (Practice Type 7-On-7 + the 7-on-7 sets in the practice playbook)"}[op]
        return f"{label}: {'on' if operation.get('enabled') else operation.get('status', 'off')}"
    if op == "scorebug_layout":
        textures = operation.get("textures_asset") or {}
        names = ", ".join(f"{role} <- {PurePosixPath(str(path)).name}" for role, path in textures.items() if path) or "no bundled textures"
        return f"ESPN scorebug layout v{operation.get('layout_version')}: {names}"
    if op in ("audio_replace", "commentary_replace"):
        return f"Audio replacement: stream {operation.get('stream_id', operation.get('cue', '?'))} <- {operation.get('asset')}"
    if op in ("text_edit", "text_replace"):
        return f"Text edit: bank {operation.get('bank', '?')}, {len(operation.get('entries') or [])} entries"
    parameters = ", ".join(f"{key}={value}" for key, value in operation.items() if key != "op")
    return f"{op}: {parameters}" if parameters else op


def describe_recipe(recipe: Mapping[str, Any]) -> list[str]:
    """Human lines for a recipe section (tolerates anything a future pack adds)."""

    lines: list[str] = []
    operations = recipe.get("operations")
    if isinstance(operations, list):
        for operation in operations:
            if isinstance(operation, Mapping):
                lines.append(describe_operation(operation))
    detected = recipe.get("detected")
    if isinstance(detected, Mapping):
        xbe = detected.get("default_xbe")
        if isinstance(xbe, Mapping):
            if xbe.get("changed"):
                lines.append("default.xbe is edited"
                             + (" (built on the retail executable)" if xbe.get("base_is_retail") else " (built on an already-modified executable)"))
            else:
                lines.append("default.xbe is untouched")
    project = recipe.get("project")
    if isinstance(project, Mapping):
        edits = project.get("edits")
        lines.append(f"Embedded studio project: {len(edits) if isinstance(edits, list) else 0} replacement edit(s)"
                     + (f", {len(project.get('audio_edits'))} audio" if isinstance(project.get("audio_edits"), list) else ""))
    return lines


# --------------------------------------------------------------------------
# Assets


@dataclass
class _Staged:
    member: str
    data: bytes
    kind: str
    role: str | None
    source_name: str | None


def _kind_for(path: Path, explicit: str | None) -> str:
    if explicit:
        _require(explicit in ASSET_KINDS, f"unknown asset kind {explicit!r}; one of {', '.join(ASSET_KINDS)}")
        return explicit
    return _KIND_BY_SUFFIX.get(path.suffix.casefold(), "other")


def _safe_member_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ +()\-]", "_", name).strip()
    cleaned = cleaned.lstrip(".") or "asset"
    return cleaned[:200]


def _stage_assets(specs: Iterable[Any], auto: Iterable[Mapping[str, Any]]) -> list[_Staged]:
    """Read every asset now (so the pack never references a file that moved)."""

    staged: list[_Staged] = []
    taken: set[str] = set()

    def unique(member: str) -> str:
        candidate = member
        stem, suffix = PurePosixPath(member).stem, PurePosixPath(member).suffix
        counter = 2
        while candidate in taken:
            candidate = f"{PurePosixPath(member).parent}/{stem} ({counter}){suffix}"
            counter += 1
        taken.add(candidate)
        return candidate

    for spec in auto:
        path = Path(spec["path"])
        data = _read_small_file(path, f"asset {path.name}", MAX_ASSET_BYTES)
        member = unique(str(spec["member"]))
        staged.append(_Staged(member, data, member.split("/")[1], spec.get("role"), path.name))
    for spec in specs:
        if isinstance(spec, (str, Path)):
            spec = {"path": spec}
        _require(isinstance(spec, Mapping) and spec.get("path"), "each asset needs a path")
        path = Path(spec["path"]).expanduser()
        kind = _kind_for(path, spec.get("kind"))
        data = _read_small_file(path, f"asset {path.name}", MAX_ASSET_BYTES)
        member = unique(f"{ASSET_ROOT}/{kind}/{_safe_member_name(spec.get('name') or path.name)}")
        role = spec.get("role")
        staged.append(_Staged(member, data, kind, str(role) if role else None, path.name))
    _require(len(staged) <= MAX_ASSETS, f"more than {MAX_ASSETS} assets")
    _require(sum(len(item.data) for item in staged) <= MAX_ASSETS_TOTAL_BYTES, "assets exceed the pack's 1 GiB asset limit")
    return staged


def _stage_project(project_path: Path | str | None) -> tuple[list[_Staged], dict[str, Any] | None]:
    """Embed a studio ``.2k5mod`` project: its members under assets/project/, its manifest in the recipe."""

    if project_path is None:
        return [], None
    path = _regular_path(project_path, "studio project")
    _require(path.suffix.casefold() == PROJECT_EXTENSION, f"the studio project must be a {PROJECT_EXTENSION} file")
    staged: list[_Staged] = []
    document: dict[str, Any] | None = None
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            _require(0 < len(infos) <= MAX_ASSETS, "the studio project has no members or too many")
            total = sum(info.file_size for info in infos)
            _require(total <= MAX_ASSETS_TOTAL_BYTES, "the studio project expands past the 1 GiB asset limit")
            for info in infos:
                _require(not info.is_dir() and not (info.flag_bits & 1), "the studio project contains a folder or encrypted member")
                _require(info.file_size <= MAX_ASSET_BYTES, f"project member is too large: {info.filename}")
                with archive.open(info) as stream:
                    data = stream.read(info.file_size + 1)
                _require(len(data) == info.file_size, f"project member is not its declared size: {info.filename}")
                name = _safe_member_name(PurePosixPath(info.filename).name)
                member = f"{ASSET_ROOT}/project/{name}"
                if info.filename == "project.json":
                    try:
                        parsed = json.loads(data.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise ModpackError(f"the studio project's project.json is not valid JSON: {exc}") from exc
                    _require(isinstance(parsed, dict), "the studio project's project.json is not an object")
                    document = parsed
                staged.append(_Staged(member, data, "project", f"project.{PurePosixPath(info.filename).name}", info.filename))
    except zipfile.BadZipFile as exc:
        raise ModpackError(f"the studio project is not a zip archive: {path.name}") from exc
    _require(document is not None, "the studio project has no project.json")
    seen: set[str] = set()
    for item in staged:
        _require(item.member not in seen, f"the studio project has two members named {PurePosixPath(item.member).name}")
        seen.add(item.member)
    return staged, document


# --------------------------------------------------------------------------
# Export


def _tool_version() -> str:
    try:
        import mod_editor
        return str(getattr(mod_editor, "__version__", "unknown"))
    except Exception:  # noqa: BLE001
        return "unknown"


def export(
    base_iso: Path | str,
    patched_iso: Path | str,
    out_path: Path | str,
    meta: Mapping[str, Any],
    *,
    overwrite: bool = False,
    recipe: bool = True,
    progress: ProgressSink | None = None,
    block: int = BLOCK,
    gap: int = COALESCE_GAP,
) -> dict[str, Any]:
    """Diff ``patched_iso`` against ``base_iso`` and write a ``.2k5patch``.

    ``meta`` carries ``name`` (required), ``author``, ``version``,
    ``description``, ``base_label``; optionally ``assets`` (paths or
    ``{"path", "kind", "role", "name"}`` specs bundled under ``assets/``),
    ``operations`` (recipe operation objects, each with an ``op`` name and its
    parameters) and ``project`` (a studio ``.2k5mod`` whose members are
    embedded under ``assets/project/`` and whose manifest becomes
    ``recipe.project``).  Studio edits the exporter recognises are added to
    the recipe automatically, with their shipped source textures.

    Both images are opened read-only and never modified.
    """

    started = time.monotonic()
    report = progress or _no_progress
    name = _text(meta.get("name"), "name", required=True)
    author = _text(meta.get("author"), "author")
    version = _text(meta.get("version"), "version")
    description = _text(meta.get("description"), "description")
    base_label = _text(meta.get("base_label"), "base_label")
    user_operations = list(meta.get("operations") or [])
    _require(all(isinstance(item, Mapping) and isinstance(item.get("op"), str) for item in user_operations),
             "every recipe operation needs an 'op' name")

    base_path = _regular_path(base_iso, "base image")
    patched_path = _regular_path(patched_iso, "patched image")
    out = Path(out_path).expanduser()
    _require(out.suffix.casefold() == EXTENSION, f"the patch file must end in {EXTENSION}")
    if out.exists():
        _require(overwrite, f"output already exists: {out}")
        _require(stat.S_ISREG(os.lstat(out).st_mode), f"output is not a regular file: {out}")
    part = out.with_name(out.name + ".part")
    _require(not part.exists(), f"a previous interrupted export left {part.name}; delete it first")

    base_fd = _open(base_path, os.O_RDONLY)
    try:
        patched_fd = _open(patched_path, os.O_RDONLY)
        try:
            _require(_identity(base_fd) != _identity(patched_fd), "base and patched are the same file")
            size = os.fstat(base_fd).st_size
            patched_size = os.fstat(patched_fd).st_size
            _require(size == patched_size,
                     f"the patched image is {patched_size} bytes and the base {size}; a format {FORMAT} patch "
                     "only carries same-size images (the studio's writers never change the size)")
            _require(size > 0, "the base image is empty")
            pbase = partition_base(base_fd, size)
            regions = image_regions(base_fd, size) if pbase is not None else ()
            ranges, base_sha, patched_sha = diff_descriptors(
                base_fd, patched_fd, size, block=block, gap=gap, progress=report)
            _require(bool(ranges), "the patched image is identical to the base; there is nothing to share")
            total = sum(end - start for start, end in ranges)
            _require(total <= MAX_PAYLOAD_BYTES,
                     f"{total} bytes differ; that is not a small patch (limit {MAX_PAYLOAD_BYTES}). "
                     "Is the patched image really built from this base?")
            partition = pbase or 0
            _require(ranges[0][0] >= partition, "differences in front of the game partition cannot be shared")

            report("Collecting changed bytes", 0, total)
            runs: list[Run] = []
            payload = bytearray()
            for start, end in ranges:
                before = _pread_exact(base_fd, end - start, start, "base run")
                after = _pread_exact(patched_fd, end - start, start, "patched run")
                runs.append(Run(
                    offset=start - partition,
                    length=end - start,
                    expected_sha256=_sha256(before),
                    new_sha256=_sha256(after),
                    payload_offset=len(payload),
                    region=_region_of(regions, start),
                ))
                payload += after
                report("Collecting changed bytes", len(payload), total)
            payload_bytes = bytes(payload)

            recognised: dict[str, Any] = {"detected": {}, "operations": [], "auto_assets": []}
            if recipe:
                report("Recognising studio edits", 0, 0)
                recognised = recognise_recipe(base_fd, patched_fd, size, base_path, patched_path)
        finally:
            os.close(patched_fd)
    finally:
        os.close(base_fd)

    report("Bundling assets", 0, 0)
    staged = _stage_assets(meta.get("assets") or (), recognised["auto_assets"])
    project_members, project_document = _stage_project(meta.get("project"))
    staged.extend(project_members)
    assets = [Asset(path=item.member, kind=item.kind, size=len(item.data), sha256=_sha256(item.data),
                    role=item.role, source_name=item.source_name) for item in staged]
    recipe_doc: dict[str, Any] = {
        "operations": [dict(item) for item in recognised["operations"]] + [dict(item) for item in user_operations],
        "detected": recognised["detected"],
    }
    if project_document is not None:
        recipe_doc["project"] = project_document

    is_retail = size == RETAIL_XISO_SIZE and base_sha == RETAIL_XISO_SHA256
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "kind": KIND,
        "game": GAME,
        "name": name,
        "author": author,
        "version": version,
        "description": description,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": {"name": "2K5 Mod Studio", "version": _tool_version()},
        "base": {
            "size": size,
            "sha256": base_sha,
            "partition_base": partition,
            "is_retail": is_retail,
            "label": base_label or ("ESPN NFL 2K5 (USA) retail disc image" if is_retail else "custom base (not the retail disc image)"),
        },
        "result": {"size": size, "sha256": patched_sha},
        "payload": {"member": PAYLOAD_MEMBER, "length": len(payload_bytes), "sha256": _sha256(payload_bytes)},
        "ops": [run.as_json() for run in runs],
        "assets": [asset.as_json() for asset in assets],
        "recipe": recipe_doc,
    }
    parse_manifest(manifest)   # the exporter must never write what the loader would refuse
    text = json.dumps(manifest, indent=1, sort_keys=False).encode("utf-8")
    _require(len(text) <= MAX_MANIFEST_BYTES, "the manifest grew past its size limit")

    report("Writing the patch file", 0, 0)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = _open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        with os.fdopen(fd, "wb") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                archive.writestr(MANIFEST_MEMBER, text)
                archive.writestr(PAYLOAD_MEMBER, payload_bytes)
                for item in staged:
                    archive.writestr(item.member, item.data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(part, out)
    except BaseException:
        try:
            os.unlink(part)
        except OSError:
            pass
        raise
    pack_size = os.lstat(out).st_size
    loaded = load(out)   # read back through the strict loader
    for asset in loaded.manifest.assets:
        loaded.read_asset(asset.path)
    return {
        "schema": EXPORT_SCHEMA,
        "pack": str(out),
        "pack_bytes": pack_size,
        "name": name,
        "author": author,
        "version": version,
        "base": dict(manifest["base"]),
        "result": dict(manifest["result"]),
        "runs": len(runs),
        "bytes": len(payload_bytes),
        "regions": loaded.manifest.region_summary(),
        "ops": [run.as_json() for run in runs],
        "assets": [asset.as_json() for asset in assets],
        "assets_bytes": sum(asset.size for asset in assets),
        "recipe": recipe_doc,
        "operations": recipe_doc["operations"],
        "recipe_lines": describe_recipe(recipe_doc),
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


# --------------------------------------------------------------------------
# Check


def _classify(actual: bytes, run: Run) -> str:
    digest = _sha256(actual)
    if digest == run.expected_sha256:
        return "match"
    if digest == run.new_sha256:
        return "applied"
    return "mismatch"


def _check_descriptor(pack: Pack, descriptor: int, size: int, *, hash_image: bool, progress: ProgressSink) -> dict[str, Any]:
    manifest = pack.manifest
    pbase = partition_base(descriptor, size)
    partition = pbase if pbase is not None else 0
    results: list[dict[str, Any]] = []
    counts = {"match": 0, "applied": 0, "mismatch": 0, "out_of_range": 0}
    for index, run in enumerate(manifest.runs):
        start = partition + run.offset
        if start + run.length > size:
            state = "out_of_range"
        else:
            state = _classify(_pread_exact(descriptor, run.length, start, f"run {index}"), run)
        counts[state] += 1
        results.append({"index": index, "file_offset": start, "length": run.length, "region": run.region, "state": state})
        progress("Checking runs", index + 1, len(manifest.runs))
    if counts["mismatch"] or counts["out_of_range"]:
        overall = "mismatch"
    elif counts["applied"] == len(manifest.runs):
        overall = "applied"
    elif counts["match"] == len(manifest.runs):
        overall = "ready"
    else:
        overall = "partial"
    image_sha: str | None = None
    if hash_image:
        digest = hashlib.sha256()
        position = 0
        while position < size:
            chunk = _pread_exact(descriptor, min(BLOCK, size - position), position, "the image")
            digest.update(chunk)
            position += len(chunk)
            progress("Hashing the image", position, size)
        image_sha = digest.hexdigest()
    return {
        "schema": CHECK_SCHEMA,
        "pack": str(pack.path),
        "state": overall,
        "counts": counts,
        "runs": results,
        "image_size": size,
        "size_matches_base": size == manifest.base["size"],
        "partition_base": pbase,
        "image_sha256": image_sha,
        "image_matches_base_sha256": None if image_sha is None or manifest.base["sha256"] is None else image_sha == manifest.base["sha256"],
        "image_is_retail": None if image_sha is None else (size == RETAIL_XISO_SIZE and image_sha == RETAIL_XISO_SHA256),
        "explanation": explain_state(overall, counts, size == manifest.base["size"]),
    }


def explain_state(state: str, counts: Mapping[str, int], size_matches: bool) -> str:
    if state == "ready":
        text = "Every run's expected bytes are present: the patch can be applied to this image."
    elif state == "applied":
        text = "This image already carries the patch (every run holds the new bytes)."
    elif state == "partial":
        text = (f"{counts['applied']} run(s) already carry the new bytes and {counts['match']} do not: "
                "a partially applied or re-edited copy. Start from a clean copy instead.")
    else:
        text = (f"{counts['mismatch'] + counts['out_of_range']} run(s) hold bytes that are neither the expected base "
                "nor the patched bytes: this image is not the base the patch was made from. Nothing will be written.")
    if not size_matches:
        text += (" (The file size differs from the author's base; runs are located through the game partition, "
                 "so a raw dump with the video partition still attached is fine when every run matches.)")
    return text


def check(pack: Pack | Path | str, image: Path | str, *, hash_image: bool = False, progress: ProgressSink | None = None) -> dict[str, Any]:
    """Dry run: which runs match, which are already applied, which mismatch."""

    loaded = pack if isinstance(pack, Pack) else load(pack)
    path = _regular_path(image, "disc image")
    fd = _open(path, os.O_RDONLY)
    try:
        return _check_descriptor(loaded, fd, os.fstat(fd).st_size, hash_image=hash_image, progress=progress or _no_progress)
    finally:
        os.close(fd)


# --------------------------------------------------------------------------
# Apply


def _verify_written(pack: Pack, descriptor: int, partition: int) -> None:
    for index, run in enumerate(pack.manifest.runs):
        actual = _pread_exact(descriptor, run.length, partition + run.offset, f"written run {index}")
        _require(_sha256(actual) == run.new_sha256, f"run {index} read back differently from what was written")


def apply(
    pack: Pack | Path | str,
    source_iso: Path | str,
    target_iso: Path | str | None = None,
    *,
    overwrite: bool = False,
    in_place: bool = False,
    hash_streams: bool = True,
    progress: ProgressSink | None = None,
    block: int = BLOCK,
) -> dict[str, Any]:
    """Apply a pack to the user's own disc image.

    Default: copy ``source_iso`` to ``target_iso`` with every run spliced in
    while copying, verifying each run's expected bytes as its span streams past,
    then read every run back.  ``in_place=True`` patches ``source_iso`` itself
    (``target_iso`` must then be None or the same path) after checking every
    run first.  The source is opened read-only in copy mode and is never
    modified by it.
    """

    if in_place:
        _require(target_iso is None or Path(target_iso).expanduser() == Path(source_iso).expanduser(),
                 "in-place apply patches the source itself; give one path")
        return apply_in_place(pack, source_iso, progress=progress)
    _require(target_iso is not None, "a target path is required unless in_place=True")

    started = time.monotonic()
    report = progress or _no_progress
    loaded = pack if isinstance(pack, Pack) else load(pack)
    manifest = loaded.manifest
    payload = loaded.payload()
    source = _regular_path(source_iso, "source image")
    target = Path(target_iso).expanduser()
    if target.exists():
        _require(overwrite, f"target already exists: {target}")
        _require(stat.S_ISREG(os.lstat(target).st_mode), f"target is not a regular file: {target}")
    part = target.with_name(target.name + ".part")
    _require(not part.exists(), f"a previous interrupted apply left {part.name}; delete it first")

    src = _open(source, os.O_RDONLY)
    try:
        size = os.fstat(src).st_size
        if target.exists():
            probe = _open(target, os.O_RDONLY)
            try:
                _require(_identity(probe) != _identity(src), "the target must not be the source image")
            finally:
                os.close(probe)
        precheck = _check_descriptor(loaded, src, size, hash_image=False, progress=report)
        _require(precheck["state"] == "ready", precheck["explanation"])
        partition = precheck["partition_base"] or 0
        runs = manifest.runs
        starts = [partition + run.offset for run in runs]
        ends = [start + run.length for start, run in zip(starts, runs)]

        target.parent.mkdir(parents=True, exist_ok=True)
        dst = _open(part, os.O_RDWR | os.O_CREAT | os.O_EXCL)
        try:
            source_hash = hashlib.sha256() if hash_streams else None
            result_hash = hashlib.sha256() if hash_streams else None
            pending: dict[int, Any] = {}
            next_run = 0
            position = 0
            while position < size:
                request = min(block, size - position)
                chunk = _pread_exact(src, request, position, "the source image")
                end = position + request
                if source_hash is not None:
                    source_hash.update(chunk)
                if next_run < len(runs) and starts[next_run] < end:
                    buffer = bytearray(chunk)
                    index = next_run
                    while index < len(runs) and starts[index] < end:
                        lo, hi = max(starts[index], position), min(ends[index], end)
                        hasher = pending.setdefault(index, hashlib.sha256())
                        hasher.update(chunk[lo - position: hi - position])
                        run = runs[index]
                        head = run.payload_offset + (lo - starts[index])
                        buffer[lo - position: hi - position] = payload[head: head + (hi - lo)]
                        if ends[index] <= end:
                            _require(hasher.hexdigest() == run.expected_sha256,
                                     f"run {index} changed under the copy at 0x{starts[index]:x}; the source is not stable")
                            del pending[index]
                        index += 1
                    while next_run < len(runs) and ends[next_run] <= end:
                        next_run += 1
                    out = bytes(buffer)
                else:
                    out = chunk
                if result_hash is not None:
                    result_hash.update(out)
                _pwrite_all(dst, out, position, "the patched copy")
                position = end
                report("Copying and patching", position, size)
            _require(next_run == len(runs) and not pending, "not every run was reached during the copy")
            os.fsync(dst)
            _require(os.fstat(dst).st_size == size, "the copy has the wrong size")
            report("Verifying the written runs", 0, 0)
            _verify_written(loaded, dst, partition)
        except BaseException:
            os.close(dst)
            try:
                os.unlink(part)
            except OSError:
                pass
            raise
        os.close(dst)
    finally:
        os.close(src)
    os.replace(part, target)

    source_sha = source_hash.hexdigest() if source_hash else None
    result_sha = result_hash.hexdigest() if result_hash else None
    return {
        "schema": APPLY_SCHEMA,
        "mode": "copy",
        "pack": str(loaded.path),
        "name": manifest.name,
        "source": {
            "path": str(source),
            "size": size,
            "sha256": source_sha,
            "matches_base_sha256": None if source_sha is None or manifest.base["sha256"] is None else source_sha == manifest.base["sha256"],
            "is_retail": None if source_sha is None else (size == RETAIL_XISO_SIZE and source_sha == RETAIL_XISO_SHA256),
        },
        "target": {
            "path": str(target),
            "size": size,
            "sha256": result_sha,
            "matches_author_result": None if result_sha is None or manifest.result["sha256"] is None else result_sha == manifest.result["sha256"],
        },
        "partition_base": partition,
        "runs": len(runs),
        "bytes": manifest.total_bytes,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def apply_in_place(pack: Pack | Path | str, image: Path | str, *, progress: ProgressSink | None = None) -> dict[str, Any]:
    """Patch an existing copy in place: check every run, write, read back."""

    started = time.monotonic()
    report = progress or _no_progress
    loaded = pack if isinstance(pack, Pack) else load(pack)
    manifest = loaded.manifest
    payload = loaded.payload()
    path = _regular_path(image, "disc image")
    fd = _open(path, os.O_RDWR)
    try:
        size = os.fstat(fd).st_size
        precheck = _check_descriptor(loaded, fd, size, hash_image=False, progress=report)
        _require(precheck["state"] == "ready", precheck["explanation"])
        partition = precheck["partition_base"] or 0
        for index, run in enumerate(manifest.runs):
            start = partition + run.offset
            current = _pread_exact(fd, run.length, start, f"run {index}")
            _require(_sha256(current) == run.expected_sha256, f"run {index} changed between the check and the write")
            _pwrite_all(fd, payload[run.payload_offset: run.payload_offset + run.length], start, f"run {index}")
            report("Writing runs", index + 1, len(manifest.runs))
        os.fsync(fd)
        report("Verifying the written runs", 0, 0)
        _verify_written(loaded, fd, partition)
    finally:
        os.close(fd)
    return {
        "schema": APPLY_SCHEMA,
        "mode": "in_place",
        "pack": str(loaded.path),
        "name": manifest.name,
        "target": {"path": str(path), "size": size},
        "partition_base": partition,
        "runs": len(manifest.runs),
        "bytes": manifest.total_bytes,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def hash_file(path: Path | str, *, progress: ProgressSink | None = None) -> str:
    """Whole-file SHA-256 in blocks (never loads the file)."""

    report = progress or _no_progress
    resolved = _regular_path(path, "file")
    fd = _open(resolved, os.O_RDONLY)
    try:
        size = os.fstat(fd).st_size
        digest = hashlib.sha256()
        position = 0
        while position < size:
            chunk = _pread_exact(fd, min(BLOCK, size - position), position, "the file")
            digest.update(chunk)
            position += len(chunk)
            report("Hashing", position, size)
    finally:
        os.close(fd)
    return digest.hexdigest()


__all__ = [
    "APPLY_SCHEMA",
    "ASSET_KINDS",
    "ASSET_ROOT",
    "Asset",
    "BLOCK",
    "CHECK_SCHEMA",
    "COALESCE_GAP",
    "EXPORT_SCHEMA",
    "EXTENSION",
    "EXTRACT_SCHEMA",
    "FORMAT",
    "GAME",
    "KIND",
    "MAX_ASSET_BYTES",
    "MAX_PAYLOAD_BYTES",
    "Manifest",
    "ModpackError",
    "PROJECT_EXTENSION",
    "Pack",
    "RETAIL_XISO_SHA256",
    "RETAIL_XISO_SIZE",
    "Region",
    "Run",
    "apply",
    "apply_in_place",
    "check",
    "coalesce",
    "describe_operation",
    "describe_recipe",
    "diff_descriptors",
    "differences",
    "explain_state",
    "export",
    "extract_assets",
    "hash_file",
    "image_regions",
    "inspect",
    "load",
    "parse_manifest",
    "partition_base",
    "recognise_recipe",
]

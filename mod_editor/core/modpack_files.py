"""Format 3: content-pinned files to a bounded, compact XDVDFS transaction.

No compiler, extracted disc tree, native delta helper, or container-offset base
identity is involved. See docs/MODPACK_FORMAT.md for the wire contract.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager, ExitStack
import hashlib
import heapq
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import tempfile
import time
import zipfile
import zlib

from . import modpack as m
from . import xdvdfs_compact as xc

BLOCK = 1024 * 1024
GRAIN = 4096
SOURCE_ALIGNMENT = 512
RUN = struct.Struct("<QI32s32s")
SOURCE_COPY = struct.Struct("<QQI32s32s")
FILE_CONTRACT = "source-copy-v1"
READER_VERSION = 4
EMPTY = hashlib.sha256(b"").hexdigest()
require = m._require


def _path(path):
    return m.platform_compat.io_path(path)


def _output_path(path):
    try:
        m.platform_compat.validate_output_path(path)
    except ValueError as exc:
        raise m.ModpackError(str(exc)) from exc
    return _path(path)


def _source_path(path):
    try:
        return m._regular_path(_path(path), "game image")
    except (m.ModpackError, OSError) as exc:
        raise failure("unreadable game image", str(exc), "Choose an accessible, regular ESPN NFL 2K5 USA Xbox image file.") from exc


def _open_source(path):
    try:
        return _source_path(path).open("rb", buffering=0)
    except OSError as exc:
        raise failure("unreadable game image", str(exc), "Check the image's permissions and choose a complete, readable Xbox dump.") from exc


def failure(detected, incompatible, next_step):
    return m.ModpackError(f"Detected: {detected}\nIncompatible: {incompatible}\nNext: {next_step}")


def _stamp(stream):
    """File details of an open source: device, file ID, size, mtime and st_ctime.

    Metadata, never a verdict (Beta 77 E1). Nothing may be refused, and no finished
    image may be thrown away, because these moved. A OneDrive, antivirus or
    search-indexer pass can rewrite the times and attributes of a file it is working
    on with no byte changed, and on Windows CPython 3.12 st_ctime is the file's
    CREATION time, which sync software can reset under an open handle. Beta 72.1
    ruled the same for projects and builds
    (tests/mod_editor/test_b721_change_time_identity.py). The bytes decide instead:
    every source byte that reaches the output is covered by the pack's SHA-256
    values (before-hash per file and per replaced run, after-hash per output file,
    read-back of the written image), so content that really changed still refuses,
    even with every one of these fields restored. ``apply`` only reports which of
    them moved."""
    s = os.fstat(stream.fileno())
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def _moved(first, now):
    """Names of the file details that differ between two ``_stamp`` readings."""
    names = ("device", "file ID", "size", "modified time", "creation time" if os.name == "nt" else "change time")
    return [name for name, a, b in zip(names, first, now) if a != b]


def _layout(stream):
    try:
        return xc.read_layout(stream)
    except (ValueError, OSError) as exc:
        found = xc.xiso.identify_non_xdvdfs_image(stream.fileno(), os.fstat(stream.fileno()).st_size)
        raise failure(found or "incomplete or invalid Xbox image", str(exc),
                      "Choose a complete, clean ESPN NFL 2K5 USA Xbox dump. PS2 copies cannot be used.") from exc


def _files(layout):
    return {k: e for k, e in layout.entries.items() if not e.attributes & 0x10}


def _chunks(stream, offset, size):
    for at in range(0, size, BLOCK):
        yield xc.read_at(stream, offset + at, min(BLOCK, size - at))


def _digest(stream, offset, size, progress=None):
    h = hashlib.sha256()
    done = 0
    for data in _chunks(stream, offset, size):
        h.update(data)
        done += len(data)
        if progress:
            progress(done)
    return h.hexdigest()


def _retail_index(base, entry, progress, *, index=None, tag=0):
    """4 KiB windows at 512-byte offsets, including windows across read blocks.

    Hashes are lookup keys only. Every candidate is compared byte for byte.
    Keep all offsets so even a hash collision cannot hide a retail match.
    """
    index = {} if index is None else index
    for at in range(0, max(0, entry.size - GRAIN + 1), BLOCK):
        data = xc.read_at(base, entry.byte_offset + at, min(BLOCK + GRAIN - SOURCE_ALIGNMENT, entry.size - at))
        for lo in range(0, min(BLOCK, len(data) - GRAIN + 1), SOURCE_ALIGNMENT):
            key = hashlib.blake2b(data[lo:lo + GRAIN], digest_size=12).digest()
            offsets = index.get(key)
            if offsets is None:
                index[key] = tag + at + lo
            elif isinstance(offsets, int):
                index[key] = [offsets, tag + at + lo]
            else:
                offsets.append(tag + at + lo)
        progress("Indexing retail spans", min(at + BLOCK, entry.size), entry.size)
    return index


def _edits(base, built, before, after, index, sources=None):
    """Yield literal or source-copy records, coalesced to 1 MiB.

    Unchanged grains stay implicit. Never trade retail references for a more
    compressible full replacement. Literal grains always start on a file grain.
    """
    for at in range(0, after.size, BLOCK):
        count = min(BLOCK, after.size - at)
        old_count = max(0, min(count, before.size - at))
        a = xc.read_at(base, before.byte_offset + at, old_count) if old_count else b""
        b = xc.read_at(built, after.byte_offset + at, count)
        spans = []
        for lo in range(0, count, GRAIN):
            hi = min(lo + GRAIN, count)
            data = b[lo:hi]
            if a[lo:hi] == data:
                continue
            source_at, source_entry = None, None
            if len(data) == GRAIN:
                candidates = index.get(hashlib.blake2b(data, digest_size=12).digest(), ())
                if isinstance(candidates, int):
                    candidates = (candidates,)
                for candidate in candidates:
                    entry = sources[candidate >> 32] if sources is not None else before
                    offset = candidate & 0xFFFFFFFF if sources is not None else candidate
                    if xc.read_at(base, entry.byte_offset + offset, GRAIN) == data:
                        source_at, source_entry = offset, entry
                        break
            if spans and spans[-1][1] == lo and (
                    source_at is None and spans[-1][2] is None or
                    source_at is not None and spans[-1][2] is not None and
                    source_entry is spans[-1][3] and
                    source_at == spans[-1][2] + lo - spans[-1][0]):
                spans[-1] = (spans[-1][0], hi, spans[-1][2], source_entry)
            else:
                spans.append((lo, hi, source_at, source_entry))
        for lo, hi, source_at, source_entry in spans:
            old, new = a[lo:hi], b[lo:hi]
            hashes = hashlib.sha256(old).digest(), hashlib.sha256(new).digest()
            if source_at is None:
                yield None, RUN.pack(at + lo, hi - lo, *hashes) + new, hi - lo
            else:
                yield source_entry, SOURCE_COPY.pack(at + lo, source_at, hi - lo, *hashes), hi - lo


class _Measure:
    def __init__(self):
        self.zip = zlib.compressobj(6, zlib.DEFLATED, -15)
        self.size = self.compressed = 0
        self.hash = hashlib.sha256()

    def add(self, data):
        self.size += len(data)
        self.hash.update(data)
        self.compressed += len(self.zip.compress(data))

    def finish(self):
        self.compressed += len(self.zip.flush())
        return dict(length=self.size, sha256=self.hash.hexdigest(), compressed_bytes=self.compressed)


def _member(archive, name, chunks):
    h, size = hashlib.sha256(), 0
    with archive.open(name, "w", force_zip64=True) as output:
        for data in chunks:
            output.write(data)
            h.update(data)
            size += len(data)
    return dict(member=name, length=size, sha256=h.hexdigest(),
                compressed_bytes=archive.getinfo(name).compress_size)


def _changed_members(archive, number, base, built, before, after, scratch, index, sources):
    counts = dict(literal_bytes=0, source_copy_bytes=0, source_copy_records=0)
    with ExitStack() as stack:
        copies = {}
        def literals():
            for source_entry, record, size in _edits(base, built, before, after, index, sources):
                if source_entry is not None:
                    path = source_entry.path.casefold()
                    if path not in copies:
                        copies[path] = stack.enter_context(tempfile.SpooledTemporaryFile(max_size=BLOCK, dir=scratch))
                    copies[path].write(record)
                    counts["source_copy_bytes"] += size
                    counts["source_copy_records"] += 1
                else:
                    counts["literal_bytes"] += size
                    yield record
        result = dict(payload=_member(archive, f"operations/{number:04d}.bin", literals()))
        for group, (path, stream) in enumerate(sorted(copies.items())):
            stream.seek(0)
            blob = _member(archive, f"operations/{number:04d}-copies-{group:04d}.bin", iter(lambda: stream.read(BLOCK), b""))
            if path == before.path.casefold():
                result["copies"] = blob
            else:
                result.setdefault("cross_copies", []).append(dict(blob, source_path=path))
    return dict(result, **counts)


def _alias(a, b):
    return m.platform_compat.paths_alias(a, b)


def _retry_locked(operation, *args):
    for attempt in range(20):
        try:
            return operation(*args)
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


@contextmanager
def _transaction(target, inputs=(), overwrite=False):
    target = _output_path(target)
    for source in inputs:
        require(not _alias(target, Path(source)), "Output must be a different file from every input.")
    require(not target.exists() or overwrite, f"Output already exists: {target}")
    require(not target.is_symlink(), "Output cannot be a symbolic link")
    fd, name = tempfile.mkstemp(prefix=".2k5-", suffix=".part", dir=target.parent)
    os.close(fd)
    part = Path(name)
    try:
        yield part
        for source in inputs:
            require(not _alias(target, source), "Output must be a different file from every input.")
        require(not target.is_symlink(), "Output cannot be a symbolic link")
        require(overwrite or not target.exists(), f"Output appeared during installation: {target}")
        try:
            if overwrite:
                m._atomic_replace(part, target)
            else:
                _retry_locked(m.platform_compat.publish_no_replace, part, target)
        except PermissionError as exc:
            raise PermissionError(f"Cannot publish {target}. Close programs using the output and try again. {exc}") from exc
    finally:
        _retry_locked(lambda: part.unlink(missing_ok=True))


def export(base_iso, built_iso, output, *, name="SOFTDRINK 2K28", recipe=None,
           source_assets=None, overwrite=False, progress=None, require_retail=True):
    """Export from finished files. Only synthetic tests opt out of retail XBE identity."""
    started = time.monotonic()
    progress = progress or m._no_progress
    output = _output_path(output)
    base_path, built_path = _path(base_iso), _path(built_iso)
    with base_path.open("rb", buffering=0) as base, built_path.open("rb", buffering=0) as built:
        bl, tl = _layout(base), _layout(built)
        bf, tf = _files(bl), _files(tl)
        require(bf.keys() == tf.keys(), "Finished disc must retain the retail file paths; file additions/deletions are unsupported.")
        require("default.xbe" in bf, "Retail input has no default.xbe")
        if require_retail:
            from .nfl2k5_disc_identity import RETAIL_XBE_SHA256, RETAIL_XBE_SIZE
            e = bf["default.xbe"]
            require(e.size == RETAIL_XBE_SIZE and _digest(base, e.byte_offset, e.size) == RETAIL_XBE_SHA256,
                    "Export requires the clean ESPN NFL 2K5 USA retail executable.")
        plan = xc.plan(tl)
        metadata = [dict(offset=32 * xc.SECTOR, data=base64.b64encode(plan["header"]).decode())]
        metadata += [dict(offset=plan["destinations"][p], data=base64.b64encode(d).decode())
                     for p, d in plan["directories"].items()]
        rows = []
        with _transaction(output, (base_path, built_path, *(source_assets or {}).values()), overwrite) as part:
            # A shared index also removes retail data relocated between archives.
            # The high 32 bits identify a verified inventory entry; the low bits
            # are a source-file offset. XDVDFS file lengths are uint32.
            sources = sorted(bf.values(), key=lambda e: e.path.casefold())
            retail_index = {}
            for source_number, entry in enumerate(sources):
                progress("Indexing retail file: " + entry.path, source_number, len(sources))
                _retail_index(base, entry, progress, index=retail_index, tag=source_number << 32)
            with zipfile.ZipFile(part, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
                z.writestr("payload.bin", b"")
                total = sum(e.size for e in tf.values())
                done = 0
                for index, planned in enumerate(plan["files"]):
                    path = planned["path"]
                    a, b = bf[path], tf[path]
                    progress("Comparing finished files: " + path, done, total)
                    full, bh = _Measure(), hashlib.sha256()
                    # Retain the measured full-file baseline, never store it.
                    for at in range(0, max(a.size, b.size), BLOCK):
                        old = xc.read_at(base, a.byte_offset + at, min(BLOCK, a.size - at)) if at < a.size else b""
                        new = xc.read_at(built, b.byte_offset + at, min(BLOCK, b.size - at)) if at < b.size else b""
                        bh.update(old)
                        full.add(new)
                        progress("Comparing finished files", done + min(at + BLOCK, b.size), total)
                    f = full.finish()
                    before = dict(size=a.size, sha256=bh.hexdigest())
                    after = dict(size=b.size, sha256=f["sha256"])
                    mode = "copy" if before == after else "runs"
                    row = dict(path=path, before=before, after=after, offset=planned["offset"], mode=mode,
                               full_copy_bytes=b.size, full_deflated_bytes=f["compressed_bytes"])
                    if mode != "copy":
                        row.update(_changed_members(z, index, base, built, a, b, output.parent, retail_index, sources))
                    rows.append(row)
                    done += b.size
                assets = []
                for member, source in (source_assets or {}).items():
                    _asset_name(member)
                    p = _path(source)
                    with p.open("rb") as stream:
                        info = _member(z, member, iter(lambda: stream.read(BLOCK), b""))
                    assets.append(info)
                progress("Hashing finished image", 0, tl.size)
                author_sha = _digest(built, 0, tl.size, lambda n: progress("Hashing finished image", n, tl.size))
                doc = dict(format=3, min_reader_version=READER_VERSION, file_contract=FILE_CONTRACT, kind=m.KIND, game=m.GAME,
                           name=name, author="SOFTDRINKTV", version="2K28", description="Finished disc files; layout-independent install",
                           base=dict(size=bl.size, sha256=None, partition_base=bl.base, label="Clean ESPN NFL 2K5 USA files",
                                     is_retail=False, is_retail_equivalent=require_retail),
                           result=dict(size=plan["output_bytes"], sha256=author_sha, author_size=tl.size),
                           files=rows, metadata=metadata, assets=assets, recipe=recipe or {},
                           tool=dict(name="2K5 Mod Studio", version=m._tool_version()))
                encoded = json.dumps(doc, separators=(",", ":")).encode()
                require(len(encoded) <= m.MAX_MANIFEST_BYTES, "File manifest exceeds 16 MiB")
                z.writestr("manifest.json", encoded)
            # The replay re-reads both inputs and compares every replayed byte with them and with the
            # hashes pinned above, so inputs that really changed refuse here, whatever their metadata did.
            verified = load(part, doc)
            replay = verify_against(verified, base_path, built_path, progress=progress)
    result = inspect(m.load(output))
    result.update(pack=str(output), elapsed_seconds=round(time.monotonic() - started, 3), replay=replay)
    return result


def _asset_name(name):
    require(isinstance(name, str) and name.startswith("assets/") and "\\" not in name,
            "Unsafe source member")
    parts = name.split("/")
    require(all(m.platform_compat.portable_component(p) for p in parts),
            "Unsafe or nonportable source member")


def _contained_path(root, member):
    """Check spelling and existing descendants without canonicalizing the root.

    A lexical check alone would allow a planted symlink or Windows junction to
    redirect extraction. Refuse those descendants, including dangling links;
    the user-selected root itself may live through a filesystem alias.
    """
    target = _path(root / member)
    require(m.platform_compat.path_is_within(target, root), "Source extraction would escape its folder")
    child = root
    for component in member.split("/"):
        child = _path(child / component)
        try:
            info = child.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_reparse_tag", 0),
                "Source path contains a symbolic link or reparse point")
    return target


def _state(value):
    require(isinstance(value, dict), "Missing file identity")
    size = m._int(value.get("size"), "file.size")
    require(size <= 0xFFFFFFFF, "File exceeds XDVDFS length limit")
    m._hex64(value.get("sha256"), "file.sha256")


def _copy_payloads(row):
    if "copies" in row:
        yield row.get("path"), row["copies"]
    for blob in row.get("cross_copies", []):
        yield blob["source_path"], blob


def _payloads(row):
    if "payload" in row:
        yield row["payload"]
    for _, blob in _copy_payloads(row):
        yield blob


def load(path, doc):
    doc = dict(doc)
    for key, value in (("assets", []), ("recipe", {}), ("tool", {})):
        doc.setdefault(key, value)
    require(all(isinstance(doc.get(key), dict) for key in ("base", "result", "recipe", "tool")),
            "Invalid file-pack metadata objects")
    for key in ("author", "version", "description"):
        doc[key] = m._text(doc.get(key), key)
    m._int(doc["base"].get("size"), "base.size", minimum=1)
    doc["base"].setdefault("sha256", None)
    doc["base"].setdefault("is_retail", False)
    doc["base"].setdefault("label", "Content-pinned game files")
    require(doc.get("file_contract") == FILE_CONTRACT,
            "Unsupported pre-release Format 3 contract; re-export with source-copy-v1")
    require(doc.get("min_reader_version") == READER_VERSION and doc.get("kind") == m.KIND and doc.get("game") == m.GAME,
            "This mod needs a newer Mod Studio or targets another game")
    rows = doc.get("files")
    require(isinstance(rows, list) and 0 < len(rows) <= 4096, "Invalid file inventory")
    names, spans, members, source_paths = set(), [], {}, set()
    for row in rows:
        require(isinstance(row, dict), "Invalid file record")
        p = row.get("path")
        require(isinstance(p, str) and len(p) <= 4096 and p == p.casefold() and "\\" not in p and "\0" not in p
                and all(x not in ("", ".", "..") for x in p.split("/")), "Invalid disc path")
        require(p not in names, "Duplicate disc path")
        names.add(p)
        _state(row.get("before")); _state(row.get("after"))
        mode = row.get("mode")
        require(mode in ("copy", "runs"), "Unknown file operation; replacements must be re-exported as source-aware runs")
        require(mode != "copy" or row["before"] == row["after"], "Copy changes file identity")
        require(mode != "copy" or not any(k in row for k in ("payload", "copies", "cross_copies")), "Copy has unexpected payloads")
        cross = row.get("cross_copies", [])
        require(isinstance(cross, list) and len(cross) <= 4096, "Invalid cross-file copy inventory")
        seen_sources = {p}
        for blob in cross:
            require(isinstance(blob, dict) and isinstance(blob.get("source_path"), str), "Invalid cross-file source")
            source_path = blob["source_path"]
            require(source_path not in seen_sources, "Repeated cross-file source")
            seen_sources.add(source_path)
            source_paths.add(source_path)
        off = m._int(row.get("offset"), "file.offset")
        size = row["after"]["size"]
        require(off % xc.SECTOR == 0 and (off >= 33 * xc.SECTOR or not size), "Invalid output extent")
        if size:
            spans.append((off, off + xc.align(size)))
        blobs = [(False, row.get("payload"))] if mode != "copy" else []
        blobs.extend((True, blob) for _, blob in _copy_payloads(row))
        for is_copy, blob in blobs:
            require(isinstance(blob, dict), "Missing file payload")
            member = blob.get("member")
            require(isinstance(member, str) and member.startswith("operations/") and len(member.split("/")) == 2
                    and bool(m._SAFE_NAME.fullmatch(member.split("/")[1])), "Unsafe file payload")
            length = m._int(blob.get("length"), "payload.length")
            m._hex64(blob.get("sha256"), "payload.sha256")
            if is_copy:
                require(0 < length <= size * SOURCE_COPY.size and length % SOURCE_COPY.size == 0, "Invalid source-copy payload length")
            else:
                require(length <= size * (RUN.size + 1), "Invalid payload length")
            require(member not in members, "Repeated payload member")
            members[member] = length
    require(source_paths <= names, "Cross-file copy source is absent from the verified inventory")
    require("default.xbe" in names, "File inventory has no default.xbe")
    metadata = doc.get("metadata")
    require(isinstance(metadata, list) and 0 < len(metadata) <= 4096, "Invalid output metadata")
    metadata_bytes = 0
    for item in metadata:
        require(isinstance(item, dict), "Invalid metadata record")
        off = m._int(item.get("offset"), "metadata.offset")
        try:
            data = base64.b64decode(item["data"], validate=True)
        except (KeyError, ValueError, TypeError) as exc:
            raise m.ModpackError("Invalid metadata encoding") from exc
        metadata_bytes += len(data)
        require(data and off >= 32 * xc.SECTOR and off % xc.SECTOR == 0, "Invalid metadata extent")
        spans.append((off, off + xc.align(len(data))))
    require(metadata_bytes <= xc.MAX_METADATA, "Metadata exceeds budget")
    spans.sort()
    require(spans[0][0] == 32 * xc.SECTOR and all(a[1] == b[0] for a, b in zip(spans, spans[1:])),
            "Output extents overlap or are not compact")
    result = doc.get("result", {})
    require(result.get("size") == xc.align(spans[-1][1], 32 * xc.SECTOR), "Invalid compact image size")
    m._hex64(result.get("sha256"), "result.sha256")
    assets = doc.get("assets", [])
    require(isinstance(assets, list) and len(assets) <= 20000, "Too many source assets")
    require(all(isinstance(asset, dict) for asset in assets), "Invalid source asset record")
    require(sum(m._int(a.get("length"), "asset.length") for a in assets) <= 8 * 1024**3, "Source assets exceed 8 GiB")
    folded_members = {n.casefold() for n in members}
    for asset in assets:
        _asset_name(asset.get("member"))
        m._hex64(asset.get("sha256"), "asset.sha256")
        require(asset["member"].casefold() not in folded_members, "Duplicate source asset")
        folded_members.add(asset["member"].casefold())
        members[asset["member"]] = asset["length"]
    with zipfile.ZipFile(path) as z:
        require(set(z.namelist()) == set(members) | {"manifest.json", "payload.bin"}, "Unlisted or missing pack members")
        require(z.getinfo("payload.bin").file_size == 0, "Format 3 payload.bin must be empty")
        for member, size in members.items():
            require(z.getinfo(member).file_size == size, f"Member length differs: {member}")
    manifest = m.Manifest(name=m._text(doc.get("name"), "name", required=True), author=str(doc.get("author", "")),
                          version=str(doc.get("version", "")), description=str(doc.get("description", "")), created="",
                          tool=doc.get("tool", {}), base=doc.get("base", {}), result=result,
                          payload={}, runs=(), recipe=doc.get("recipe", {}), raw=doc)
    return m.Pack(Path(path), manifest, Path(path).stat().st_size)


def inspect(pack):
    d = pack.manifest.raw
    rows, assets = d["files"], d["assets"]
    changed = [r for r in rows if r["mode"] != "copy"]
    return dict(path=str(pack.path), pack_bytes=pack.size, format=3, name=pack.manifest.name,
                min_reader_version=d["min_reader_version"], file_contract=d["file_contract"],
                author=pack.manifest.author, version=pack.manifest.version, description=pack.manifest.description,
                created="", tool=d["tool"], base=d["base"], result=d["result"], files=rows,
                runs=len(changed), bytes=sum(b["length"] for r in rows for b in _payloads(r)),
                regions=[], patch_operations=[], recipe=d["recipe"],
                recipe_lines=["SOFTDRINK finished files. Extract sources to customize in the full Studio builder."] if d["recipe"] else [],
                assets=[dict(path=a["member"], size=a["length"], sha256=a["sha256"]) for a in assets],
                assets_bytes=sum(a["length"] for a in assets), sources_deflated_bytes=sum(a["compressed_bytes"] for a in assets),
                payload_deflated_bytes=sum(b.get("compressed_bytes", 0) for r in rows for b in _payloads(r)),
                literal_bytes=sum(r.get("literal_bytes", 0) for r in rows),
                source_copy_bytes=sum(r.get("source_copy_bytes", 0) for r in rows),
                source_copy_records=sum(r.get("source_copy_records", 0) for r in rows),
                full_copy_baseline_bytes=sum(r["after"]["size"] for r in changed),
                full_copy_deflated_bytes=sum(r.get("full_deflated_bytes", 0) for r in changed))


def _validate_source(pack, stream, progress):
    layout = _layout(stream)
    files = _files(layout)
    rows = pack.manifest.raw["files"]
    required = {r["path"] for r in rows}
    if not required <= files.keys():
        raise failure("Xbox XDVDFS disc", f"Required files are missing: {sorted(required - files.keys())}",
                      "Choose your clean ESPN NFL 2K5 USA Xbox image.")
    total, done = sum(r["before"]["size"] for r in rows), 0
    # Executable first gives a useful early refusal for another game/mod.
    for row in sorted(rows, key=lambda r: r["path"] != "default.xbe"):
        e, expected = files[row["path"]], row["before"]
        actual = _digest(stream, e.byte_offset, e.size,
                         lambda n: progress("Checking clean game files", done + n, total)) if e.size == expected["size"] else "size differs"
        if e.size != expected["size"] or actual != expected["sha256"]:
            raise failure("Xbox disc with changed or incompatible game files",
                          f"{row['path']}: expected {expected['size']} bytes / SHA-256 {expected['sha256']}; found {e.size} bytes / {actual}.",
                          "Select an unmodified ESPN NFL 2K5 USA Xbox dump. An already modded disc cannot be upgraded with this pack.")
        done += e.size
    return layout


def check(pack, image, *, progress=None, **_kwargs):
    progress = progress or m._no_progress
    try:
        with _open_source(image) as source, zipfile.ZipFile(pack.path) as archive:
            layout = _validate_source(pack, source, progress)
            for row in pack.manifest.raw["files"]:
                if row["mode"] == "copy":
                    continue
                digest = hashlib.sha256()
                for at, data in _reconstruct(row, source, layout.entries[row["path"]], archive, layout.entries):
                    digest.update(data)
                    progress("Checking pack payloads", at + len(data), row["after"]["size"])
                require(digest.hexdigest() == row["after"]["sha256"], "Reconstructed file SHA-256 differs")
        state, explanation, base = "ready", "Every required game file matches. ISO order, padding and video prefix are accepted.", layout.base
    except (m.ModpackError, zipfile.BadZipFile, OSError) as exc:
        state, explanation, base = "mismatch", str(exc), None
    return dict(state=state, explanation=explanation, partition_base=base,
                counts=dict(match=len(pack.manifest.raw["files"]) if state == "ready" else 0,
                            applied=0, mismatch=int(state != "ready"), out_of_range=0),
                runs=[], image_sha256=None, image_is_retail=False, image_matches_base_sha256=False)


class _Payload:
    def __init__(self, stream, blob):
        self.stream, self.blob = stream, blob
        self.hash, self.count = hashlib.sha256(), 0

    def read(self, count):
        data = self.stream.read(count)
        require(len(data) == count, "Truncated file payload")
        self.hash.update(data)
        self.count += len(data)
        return data

    def finish(self):
        require(not self.stream.read(1) and self.count == self.blob["length"] and self.hash.hexdigest() == self.blob["sha256"],
                "Payload SHA-256 or length differs")


def _reconstruct(row, source, entry, archive, source_entries=None):
    """Yield bounded (file offset, bytes) chunks for either proof or writing."""
    size = row["after"]["size"]
    def copy(lo, hi):
        if lo == hi:
            return
        require(lo <= hi <= entry.size, "Uncovered growth bytes in file runs")
        for at in range(lo, hi, BLOCK):
            yield at, xc.read_at(source, entry.byte_offset + at, min(BLOCK, hi - at))
    if row["mode"] == "copy":
        yield from copy(0, size)
        return
    with ExitStack() as stack:
        def records(blob, copy_entry=None):
            raw = stack.enter_context(archive.open(blob["member"]))
            payload = _Payload(raw, blob)
            header = SOURCE_COPY if copy_entry is not None else RUN
            while payload.count < blob["length"]:
                values = header.unpack(payload.read(header.size))
                if copy_entry is not None:
                    at, source_at, length, before, after = values
                    require(source_at + length <= copy_entry.size, "Source-copy span exceeds retail file")
                    source_at += copy_entry.byte_offset
                else:
                    at, length, before, after = values
                    source_at = None
                require(0 < length <= BLOCK and at + length <= size, "File runs exceed bounds")
                data = payload.read(length) if source_at is None else None
                yield at, length, before, after, source_at, data
            payload.finish()
        cursor = 0
        streams = [records(row["payload"])]
        for path, blob in _copy_payloads(row):
            copy_entry = entry if path == row.get("path") else (source_entries or {}).get(path)
            require(copy_entry is not None, "Missing verified cross-file copy source")
            streams.append(records(blob, copy_entry))
        for at, length, before, after, source_at, data in heapq.merge(*streams, key=lambda r: r[0]):
            require(cursor <= at, "File runs overlap or are out of order")
            yield from copy(cursor, at)
            old_size = max(0, min(length, entry.size - at))
            old = xc.read_at(source, entry.byte_offset + at, old_size) if old_size else b""
            require(hashlib.sha256(old).digest() == before, "File run expected-before SHA-256 differs")
            if source_at is not None:
                data = xc.read_at(source, source_at, length)
            require(hashlib.sha256(data).digest() == after,
                    "Source-copy SHA-256 differs" if source_at is not None else "File run expected-after SHA-256 differs")
            yield at, data
            cursor = at + length
        yield from copy(cursor, size)


def verify_against(pack, source_iso, finished_iso, *, progress=None):
    """Read-only exact-byte replay, also possible before space for an output exists."""
    progress = progress or m._no_progress
    started = time.monotonic()
    with _open_source(source_iso) as source, _open_source(finished_iso) as finished, zipfile.ZipFile(pack.path) as archive:
        before = _validate_source(pack, source, progress)
        after = _layout(finished)
        rows = pack.manifest.raw["files"]
        require(_files(after).keys() == {r["path"] for r in rows}, "Finished file inventory differs")
        total, done = sum(r["after"]["size"] for r in rows), 0
        for row in rows:
            actual = after.entries[row["path"]]
            require(actual.size == row["after"]["size"], "Finished file length differs")
            h, size = hashlib.sha256(), 0
            for at, data in _reconstruct(row, source, before.entries[row["path"]], archive, before.entries):
                require(data == xc.read_at(finished, actual.byte_offset + at, len(data)),
                        f"Pack replay differs from finished file {row['path']} at 0x{at:x}")
                h.update(data)
                size += len(data)
                progress("Proving exported files", done + size, total)
            require(size == actual.size and h.hexdigest() == row["after"]["sha256"], "Replayed file hash or length differs")
            done += size
    return dict(all_files_byte_equal=True, files=len(rows), compared_bytes=total,
                elapsed_seconds=round(time.monotonic() - started, 3))


def apply(pack, source_iso, target_iso, *, overwrite=False, progress=None, **_kwargs):
    started = time.monotonic()
    progress = progress or m._no_progress
    target = _output_path(target_iso)
    source_path = _source_path(source_iso)
    rows, doc = pack.manifest.raw["files"], pack.manifest.raw
    total = sum(r["after"]["size"] for r in rows)
    with _transaction(target, (source_path, pack.path), overwrite) as part:
        with _open_source(source_path) as source, zipfile.ZipFile(pack.path) as archive:
            stamp = _stamp(source)
            layout = _validate_source(pack, source, progress)
            required_space = doc["result"]["size"]
            require(shutil.disk_usage(target.parent).free >= required_space,
                    f"Not enough disk space. Need {required_space:,} free bytes for the new image.")
            done = 0
            with part.open("w+b", buffering=0) as output:
                output.truncate(required_space)
                for item in doc["metadata"]:
                    xc.write_at(output, item["offset"], base64.b64decode(item["data"]))
                for row in rows:
                    e, offset, size = layout.entries[row["path"]], row["offset"], row["after"]["size"]
                    h = hashlib.sha256()
                    for at, data in _reconstruct(row, source, e, archive, layout.entries):
                        h.update(data)
                        # This is a new zero-filled file. Leave all-zero blocks sparse
                        # where the host supports holes; no platform-specific API.
                        if data.strip(b"\0"):
                            xc.write_at(output, offset + at, data)
                        progress("Installing finished files", done + at + len(data), total)
                    require(h.hexdigest() == row["after"]["sha256"], f"Reconstructed file SHA-256 differs: {row['path']}")
                    done += size
                output.flush()
                os.fsync(output.fileno())
                actual = _layout(output)
                require(_files(actual).keys() == {r["path"] for r in rows}, "Written directory inventory differs")
                done = 0
                for row in rows:
                    e = actual.entries[row["path"]]
                    require(e.byte_offset == row["offset"] and e.size == row["after"]["size"], "Written directory extent differs")
                    digest = _digest(output, e.byte_offset, e.size,
                                     lambda n: progress("Verifying installed files", done + n, total))
                    require(digest == row["after"]["sha256"], f"Read-back SHA-256 differs: {row['path']}")
                    done += e.size
                sha = _digest(output, 0, required_space, lambda n: progress("Verifying image", n, required_space))
            # Every output byte was just proved against the pack's SHA-256 values, so the install is
            # complete whatever the source's file details did meanwhile. A synced folder (OneDrive)
            # moves them under an open file: refusing here threw away a verified 6 GB image
            # ("Source changed during installation", Beta 77 E1). Report it; never refuse on it.
            source_metadata_changed = _moved(stamp, _stamp(source))
        # All descriptors, including ZIP handles, are closed before Windows rename.
    return dict(name=pack.manifest.name, mode="file-copy", runs=sum(r["mode"] != "copy" for r in rows), bytes=total,
                target=dict(path=str(target), size=required_space, sha256=sha,
                            matches_author_result=sha == doc["result"]["sha256"], all_game_files_verified=True),
                elapsed_seconds=round(time.monotonic() - started, 3), disk_required_bytes=required_space,
                files_verified=len(rows), format=3, source_metadata_changed=source_metadata_changed)


def extract_assets(pack, directory, *, overwrite=False):
    root = _path(m.platform_compat.absolute_path(_output_path(directory)))
    names = set()
    for asset in pack.manifest.raw["assets"]:
        _asset_name(asset["member"])
        key = asset["member"].casefold()
        require(key not in names, "Duplicate source asset")
        names.add(key)
    root.mkdir(parents=True, exist_ok=True)
    written = []
    with zipfile.ZipFile(pack.path) as archive:
        for asset in pack.manifest.raw["assets"]:
            target = _contained_path(root, asset["member"])
            target.parent.mkdir(parents=True, exist_ok=True)
            with _transaction(target, (pack.path,), overwrite) as part:
                with archive.open(asset["member"]) as src, part.open("wb") as dst:
                    reader = _Payload(src, asset)
                    for at in range(0, asset["length"], BLOCK):
                        dst.write(reader.read(min(BLOCK, asset["length"] - at)))
                    reader.finish()
            written.append(str(target))
    for name, data in (("recipe.json", pack.manifest.recipe), ("manifest.json", pack.manifest.raw)):
        with _transaction(_contained_path(root, name), (pack.path,), overwrite) as part:
            part.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")
    return dict(directory=str(root), files=written, assets=len(written))

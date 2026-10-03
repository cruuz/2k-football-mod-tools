"""DESIGN: bounded XDVDFS repacking; only finish_private mutates its input.

File contents, names, attributes and directory search trees are retained. The
output is an extracted game partition with 2048-byte extents and a 32-sector
end alignment. No extracted files or OS-specific I/O. A second image is written
beside the build copy only when the in-place move plan is too fragmented.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import stat
import struct
import tempfile
import time

from tools import nfl_uniform_color_xiso_direct_patch as xiso

SECTOR = 2048
BLOCK = 1024 * 1024
MAX_METADATA = 32 * BLOCK
STUDIO_RECEIPTS = (".colour-lighting.json", ".venues-2026.json", ".surfaces.json")
# PROVED OFFLINE: physical order of the pinned USA retail rip. These are names,
# never physical read addresses. Restores slots even when the input was rebuilt.
NFL_ORDER = ("update.xbe", "default.xbe", "dashupdate.xbe") + tuple(
    "vc_53450030/" + name for name in "9531024768dbacef")


# beta 76.3: bounds for the in-place move plan, checked by a dry run with no I/O before anything is written. The
# SOFTDRINK 2K28 build needs about 360 steps in well under a second. A dump that stores the same files in another
# order can need a full in-place permutation whose fragments are rescanned every step: minutes to hours even without
# I/O, seen by users as a frozen "Compacting disc image".
IN_PLACE_MAX_STEPS = 20_000
IN_PLACE_MAX_SECONDS = 2.0
REWRITE_SPARE_BYTES = 64 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


class _OverBudget(Exception):
    """The in-place move plan exceeds its dry-run bounds."""


def align(size, unit=SECTOR):
    return (size + unit - 1) // unit * unit


def read_at(stream, offset, size):
    stream.seek(offset)
    data = stream.read(size)
    require(len(data) == size, "short XDVDFS read")
    return data


def write_at(stream, offset, data):
    stream.seek(offset)
    view = memoryview(data)
    while view:
        count = stream.write(view)
        require(count is not None and count > 0, "short XDVDFS write")
        view = view[count:]


@dataclass
class Layout:
    size: int
    base: int
    header: bytearray
    directories: dict
    entries: dict
    nodes: dict


def _layout_at(stream, size, base):
    header = bytearray(read_at(stream, base + 32 * SECTOR, SECTOR))
    require(header[:20] == header[-20:] == xiso.XDVDFS_MAGIC, "invalid XDVDFS descriptor")
    root_sector, root_size = struct.unpack_from("<II", header, 20)
    pending = [("", root_sector, root_size, 0)]
    directories, entries, nodes, seen, total = {}, {}, {}, set(), 0
    while pending:
        parent, sector, length, depth = pending.pop()
        require(depth <= xiso.MAX_DIRECTORY_DEPTH, "directory nesting too deep")
        require((sector, length) not in seen, "cyclic directory extent")
        seen.add((sector, length))
        total += length
        require(14 <= length <= MAX_METADATA and total <= MAX_METADATA, "directory metadata budget exceeded")
        at = base + sector * SECTOR
        require(sector > 0 and at + length <= size, "directory outside image")
        data = bytearray(read_at(stream, at, length))
        directories[parent.casefold()] = (at, data)
        todo, visited, records = [0], set(), []
        while todo:
            off = todo.pop()
            require(off not in visited and 0 <= off <= length - 14, "invalid directory tree")
            visited.add(off)
            left, right, start, count, attrs, nlen = struct.unpack_from("<HHIIBB", data, off)
            require(nlen and off + 14 + nlen <= length, "invalid directory name")
            require(off // SECTOR == (off + 13 + nlen) // SECTOR, "directory record crosses a sector")
            records.append((off, align(off + 14 + nlen, 4)))
            name = bytes(data[off + 14:off + 14 + nlen]).decode("latin-1")
            require(not any(c in name for c in ("/", "\\", "\0")) and name not in (".", ".."), "invalid disc name")
            path = f"{parent}/{name}" if parent else name
            key = path.casefold()
            require(key not in entries, "duplicate directory name")
            require(len(entries) < xiso.MAX_DIRECTORY_NODES, "directory node limit exceeded")
            require(base + start * SECTOR + count <= size, "file outside image")
            entries[key] = xiso.XdvdfsEntry(path, start, count, attrs, base)
            nodes[key] = (parent.casefold(), off + 4)
            if attrs & 0x10 and count:
                pending.append((path, start, count, depth + 1))
            todo.extend(child * 4 for child in (left, right) if child)
        records.sort()
        require(all(a[1] <= b[0] for a, b in zip(records, records[1:])), "overlapping directory records")
    spans = [(base + 32 * SECTOR, base + 33 * SECTOR)]
    spans += [(at, at + align(len(data))) for at, data in directories.values()]
    spans += [(e.byte_offset, e.byte_offset + align(e.size)) for e in entries.values()
              if e.size and not e.attributes & 0x10]
    spans.sort()
    require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "overlapping XDVDFS extents")
    # Independent Studio reader checks the same tree after the bounded walk.
    parsed, _ = xiso.parse_xdvdfs(stream.fileno(), size, base)
    require(parsed == entries, "Studio directory walk disagrees")
    return Layout(size, base, header, directories, entries, nodes)


def read_layout(stream):
    size = os.fstat(stream.fileno()).st_size
    fallback = None
    for base in xiso.iter_xdvdfs_bases(stream.fileno(), size):
        layout = _layout_at(stream, size, base)
        if "default.xbe" in layout.entries:
            return layout
        if fallback is None:
            fallback = layout
    require(fallback is not None, "no XDVDFS game partition found")
    return fallback


def file_order(layout, reference=None):
    files = {k: e for k, e in layout.entries.items() if not e.attributes & 0x10}
    if reference is not None:
        with Path(reference).open("rb") as stream:
            original = read_layout(stream)
        order = [k for k, e in sorted(original.entries.items(), key=lambda row: row[1].byte_offset)
                 if k in files and not e.attributes & 0x10]
        mode = "reference"
    elif set(NFL_ORDER) <= files.keys():
        order, mode = list(NFL_ORDER), "nfl2k5-retail"
    else:
        order, mode = [], "source-physical"
    order += [k for k, e in sorted(files.items(), key=lambda row: (row[1].byte_offset, row[0])) if k not in order]
    return order, mode


def plan(layout, reference=None):
    order, mode = file_order(layout, reference)
    at, destinations = 33 * SECTOR, {}
    for name, (_, data) in layout.directories.items():
        destinations[name] = at
        at += align(len(data))
    rows = []
    for name in order:
        entry = layout.entries[name]
        destinations[name] = at if entry.size else 0
        rows.append(dict(path=name, source_offset=entry.byte_offset, offset=destinations[name], size=entry.size))
        at += align(entry.size)
    header = bytearray(layout.header)
    struct.pack_into("<I", header, 20, destinations[""] // SECTOR)
    directories = {name: bytearray(data) for name, (_, data) in layout.directories.items()}
    for name, entry in layout.entries.items():
        parent, node = layout.nodes[name]
        struct.pack_into("<I", directories[parent], node, destinations.get(name, 0) // SECTOR)
    return dict(order=mode, files=rows, destinations=destinations, header=header,
                directories=directories, output_bytes=align(at, 32 * SECTOR))


def _hash_files(stream, rows, field, progress):
    hashes = {}
    for row in rows:
        digest = hashlib.sha256()
        for at in range(0, row["size"], BLOCK):
            digest.update(read_at(stream, row[field] + at, min(BLOCK, row["size"] - at)))
            progress("Verifying disc files", at + min(BLOCK, row["size"] - at), row["size"])
        hashes[row["path"]] = digest.hexdigest()
    return hashes


def _copy(stream, output, source, dest, size, progress, *, backward=False):
    remaining = size
    while remaining:
        count = min(BLOCK, remaining)
        delta = remaining - count if backward else size - remaining
        data = read_at(stream, source + delta, count)
        write_at(output, dest + delta, data)
        remaining -= count
        progress("Compacting disc image", size - remaining, size)


@dataclass
class Move:
    source: int
    dest: int
    size: int
    saved: bytes | None = None

    def part(self, start, end):
        return Move(self.source + start, self.dest + start, end - start,
                    None if self.saved is None else self.saved[start:end])


def _move_private(stream, rows, progress, *, budget=None):
    """DESIGN: drain safe destination intervals, breaking cycles with <=1 MiB.

    A destination is safe only if it overlaps no OTHER pending source. A
    self-overlap uses memmove direction. When a cycle has no gap, save one
    bounded source prefix in memory and drain the hole it leaves. Source and
    destination extents are disjoint within each set, so a saved prefix always
    leaves a gap until it has been restored. No disk scratch is needed.
    With budget=(steps, seconds) the same plan runs with no I/O at all and
    raises _OverBudget once it passes either bound.
    """
    dry = budget is not None
    deadline = time.monotonic() + budget[1] if dry else None
    steps = 0
    pending = [Move(r["source_offset"], r["offset"], align(r["size"])) for r in rows
               if r["size"] and r["source_offset"] != r["offset"]]
    peak_saved = 0
    while pending:
        if dry:
            steps += 1
            if steps > budget[0] or time.monotonic() > deadline:
                raise _OverBudget(steps)
        choice = None
        sources = sorted((m.source, m.source + m.size, i) for i, m in enumerate(pending) if m.saved is None)
        for index, move in enumerate(pending):
            cursor, end = move.dest, move.dest + move.size
            # Only a WHOLE move can ignore its own source. A partial memmove
            # could overwrite bytes belonging to the remainder of that move.
            if not any(other != index and lo < end and hi > cursor for lo, hi, other in sources):
                choice = (index, 0, move.size)
                break
            for lo, hi, other in sources:
                if hi <= cursor:
                    continue
                if lo >= end:
                    break
                if lo > cursor:
                    choice = (index, cursor - move.dest, min(lo, end) - move.dest)
                    break
                cursor = max(cursor, hi)
                if cursor >= end:
                    break
            if choice is None and cursor < end:
                choice = (index, cursor - move.dest, move.size)
            if choice is not None:
                break
        if choice is None:
            require(not any(m.saved is not None for m in pending), "compaction dependency stalled")
            move = pending.pop(0)
            count = min(BLOCK, move.size)
            saved = bytes(count) if dry else read_at(stream, move.source, count)
            peak_saved = max(peak_saved, count)
            pending.append(Move(move.source, move.dest, count, saved))
            if count < move.size:
                pending.append(move.part(count, move.size))
            continue
        index, start, end = choice
        move = pending.pop(index)
        if dry:
            pass
        elif move.saved is not None:
            write_at(stream, move.dest + start, move.saved[start:end])
        else:
            _copy(stream, stream, move.source + start, move.dest + start, end - start, progress,
                  backward=move.dest > move.source)
        if start:
            pending.append(move.part(0, start))
        if end < move.size:
            pending.append(move.part(end, move.size))
    return peak_saved


def _in_place_fits(rows):
    """True when the in-place move plan finishes within its bounds (dry run, no I/O)."""
    try:
        _move_private(None, rows, None, budget=(IN_PLACE_MAX_STEPS, IN_PLACE_MAX_SECONDS))
    except _OverBudget:
        return False
    except ValueError:
        return False  # a stalled plan: the sibling rewrite handles any plan
    return True


def _replace_image(staged, target):
    """Replace the build image; Windows may briefly hold a just-closed file open (indexer, antivirus)."""
    for attempt in range(40):
        try:
            os.replace(staged, target)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 39:
                raise
            time.sleep(0.25)


def _rewrite_beside(target, layout, planned, hashes, progress):
    """beta 76.3: write the SAME planned layout into a new sibling file, then replace the build image.

    Used only when the in-place plan is too fragmented. The output bytes equal the
    in-place result; it needs the finished image's size in free space beside it.
    """
    need = planned["output_bytes"] + REWRITE_SPARE_BYTES
    free = shutil.disk_usage(target.parent).free
    require(free >= need,
            "This copy of the game stores its files in a different order from the retail disc, so finishing the "
            f"disc needs {need / 1e9:.1f} GB free on the drive that holds {target.name} ({free / 1e9:.1f} GB free "
            "now). Free some space there and make the disc again.")
    from .platform_compat import temporary_sibling
    staged = temporary_sibling(target, suffix=".compact")
    try:
        with target.open("rb", buffering=0) as source, staged.open("x+b", buffering=0) as out:
            for row in planned["files"]:
                for at in range(0, row["size"], BLOCK):
                    count = min(BLOCK, row["size"] - at)
                    write_at(out, row["offset"] + at, read_at(source, row["source_offset"] + at, count))
                    progress("Compacting disc image", at + count, row["size"])
            _metadata(out, planned)
            receipt = _verify(out, layout, planned, hashes, progress)
        _replace_image(staged, target)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return dict(receipt, scratch_disk_bytes=planned["output_bytes"], peak_cycle_buffer_bytes=0)


def _metadata(output, planned):
    write_at(output, 0, bytes(32 * SECTOR))
    write_at(output, 32 * SECTOR, planned["header"])
    for name, data in planned["directories"].items():
        write_at(output, planned["destinations"][name], data + bytes(align(len(data)) - len(data)))
    end = 33 * SECTOR + sum(align(len(d)) for d in planned["directories"].values())
    for row in planned["files"]:
        if row["size"]:
            end = row["offset"] + align(row["size"])
            write_at(output, row["offset"] + row["size"], bytes(align(row["size"]) - row["size"]))
    write_at(output, end, bytes(planned["output_bytes"] - end))
    output.truncate(planned["output_bytes"])
    output.flush()
    os.fsync(output.fileno())


def _verify(output, layout, planned, hashes, progress):
    fresh = read_layout(output)
    before = {k: (e.path, e.size, e.attributes) for k, e in layout.entries.items()}
    after = {k: (e.path, e.size, e.attributes) for k, e in fresh.entries.items()}
    require(before == after, "compacted directory inventory differs")
    require(fresh.base == 0 and fresh.size == planned["output_bytes"], "compacted geometry differs")
    for name, entry in fresh.entries.items():
        require(entry.byte_offset == planned["destinations"].get(name, 0), "compacted extent differs")
    actual = _hash_files(output, planned["files"], "offset", progress)
    require(actual == hashes, "compacted file SHA-256 differs")
    return dict(classification="PROVED OFFLINE", input_bytes=layout.size, output_bytes=fresh.size,
                bytes_saved=layout.size - fresh.size, order=planned["order"],
                files=[dict(row, sha256=hashes[row["path"]]) for row in planned["files"]],
                directory_count=len(fresh.directories), all_file_hashes_identical=True,
                studio_directory_check=True, runtime_witnessed=False)


def finish_private(target, *, original=None, progress=None):
    """DESIGN: caller owns a disposable build image; failure must discard it.

    Never call this on a published image. Builds already isolate their output
    and publish only after all gates succeed. Public callers use compact_copy.
    """
    target = Path(target)
    info = target.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "compaction needs a private regular image")
    progress = progress or (lambda *_: None)
    with target.open("r+b", buffering=0) as stream:
        layout = read_layout(stream)
        # The known retail name order survives rebuilding an already grown 2K5
        # source. Other games retain the caller's original source order.
        nfl = set(NFL_ORDER) <= layout.entries.keys()
        candidates = [plan(layout, None if nfl else original)]
        if nfl and original is not None:
            # beta 76.3: a dump that stores its files in another order (other xiso tools) would need a full
            # in-place permutation into retail order; its own order needs only the growth moves.
            own = plan(layout, original)
            if [r["offset"] for r in own["files"]] != [r["offset"] for r in candidates[0]["files"]]:
                candidates.append(own)
        planned = next((c for c in candidates if _in_place_fits(c["files"])), None)
        if planned is not None:
            hashes = _hash_files(stream, planned["files"], "source_offset", progress)
            # A final partial source sector has no file bytes in its missing suffix.
            stream.truncate(max(align(layout.size), planned["output_bytes"]))
            peak = _move_private(stream, planned["files"], progress)
            _metadata(stream, planned)
            receipt = _verify(stream, layout, planned, hashes, progress)
            return dict(receipt, scratch_disk_bytes=0, peak_cycle_buffer_bytes=peak)
        planned = candidates[0]
        hashes = _hash_files(stream, planned["files"], "source_offset", progress)
    return _rewrite_beside(target, layout, planned, hashes, progress)


def compact_copy(source, output, *, reference=None, progress=None):
    """DESIGN: read-only source, new destination, one streamed output, no overwrite."""
    source, output = Path(source), Path(output)
    require(not output.exists() and not output.is_symlink(), "output already exists")
    require(source.resolve() != output.resolve(), "output must differ from source")
    progress = progress or (lambda *_: None)
    from .platform_compat import publish_no_replace
    # These receipts pin resource bytes, not physical disc addresses. Carry
    # them with the image just as mod_build does, so Studio status stays useful.
    sidecars = []
    for suffix in STUDIO_RECEIPTS:
        src, dst = Path(str(source) + suffix), Path(str(output) + suffix)
        require(not dst.exists() and not dst.is_symlink(), "output receipt already exists")
        if src.is_file():
            require(src.stat().st_size <= 8 * BLOCK, "Studio receipt exceeds size budget")
            sidecars.append((src, dst))
    with source.open("rb", buffering=0) as reader:
        before = os.fstat(reader.fileno())
        require(stat.S_ISREG(before.st_mode), "source must be a regular image")
        layout = read_layout(reader)
        planned = plan(layout, reference)
        with tempfile.TemporaryDirectory(prefix=".xdvdfs-", dir=output.parent) as temp:
            staged = Path(temp) / "compact.iso"
            hashes = {}
            with staged.open("x+b", buffering=0) as writer:
                for row in planned["files"]:
                    digest = hashlib.sha256()
                    for at in range(0, row["size"], BLOCK):
                        count = min(BLOCK, row["size"] - at)
                        data = read_at(reader, row["source_offset"] + at, count)
                        digest.update(data)
                        write_at(writer, row["offset"] + at, data)
                        progress("Compacting disc image", at + count, row["size"])
                    hashes[row["path"]] = digest.hexdigest()
                _metadata(writer, planned)
                receipt = _verify(writer, layout, planned, hashes, progress)
            after = os.fstat(reader.fileno())
            require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), "source changed during compaction")
            published = []
            try:
                for index, (src, dst) in enumerate(sidecars):
                    staged_receipt = Path(temp) / f"receipt-{index}.json"
                    with src.open("rb", buffering=0) as inp, staged_receipt.open("xb", buffering=0) as out:
                        info = os.fstat(inp.fileno())
                        require(info.st_size <= 8 * BLOCK, "Studio receipt exceeds size budget")
                        _copy(inp, out, 0, 0, info.st_size, progress)
                        current = os.fstat(inp.fileno())
                        require((info.st_size, info.st_mtime_ns) == (current.st_size, current.st_mtime_ns),
                                "Studio receipt changed during copy")
                        os.fsync(out.fileno())
                    publish_no_replace(staged_receipt, dst)
                    published.append((dst, dst.stat()))
                publish_no_replace(staged, output)
            except BaseException:
                for dst, info in published:
                    if dst.exists() and dst.stat() == info:
                        dst.unlink()
                raise
    receipt["studio_receipts_copied"] = [dst.name for _, dst in sidecars]
    return receipt

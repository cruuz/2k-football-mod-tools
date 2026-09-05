"""Fresh read-only storage for SPECIAL's 46 records, outside the retail image.

There is no certified 3312-byte retail .rdata cave. Extend the final .XTLID
section, retaining its entire original payload, and preload its new read-only
tail. This is a loader allocation, not permission to reuse an unknown cave.
The disc writer must support the resulting XBE growth; see WIRING_SPECIAL.md.
"""
from __future__ import annotations

import hashlib
import os
import struct

from .nfl2k5_bump_strength import _sections

TABLE_VA = 0xEE3000
TABLE_SIZE = 46 * 0x48
SECTION_VA = 0xED0380
RETAIL_SIZE = 0x1440
RETAIL_RAW = 0xB63000
RETAIL_FILE_SIZE = 0xB65000
RETAIL_IMAGE_SIZE = 0xEC17C0
SIZE = TABLE_VA + TABLE_SIZE - SECTION_VA
TABLE_RAW = RETAIL_RAW + TABLE_VA - SECTION_VA
FILE_SIZE = (RETAIL_RAW + SIZE + 0xFFF) & ~0xFFF
RETAIL_FLAGS, FLAGS = 0x38, 0x3A  # preserve head/tail RO flags; add preload, never write/execute
RETAIL_CONTENT_SHA256 = "24df4adb3674c6858efa68d143fb1763b6bbd3820103b71ecde589ae438b6b71"


def _section(payload: bytes):
    matches = [s for s in _sections(payload) if s.virtual_address == SECTION_VA]
    if len(matches) != 1:
        raise ValueError("missing final .XTLID storage owner")
    return matches[0]


def state(payload: bytes) -> str:
    try:
        if struct.unpack_from("<I", payload, 0x11C)[0] in (24, 25, 26):
            from . import nfl2k5_xbe_space as space
            return space.special_state(payload)
        s = _section(payload)
        h = s.header_offset
        flags, va, size, raw, raw_size = struct.unpack_from("<5I", payload, h)
        if (va, raw) != (SECTION_VA, RETAIL_RAW):
            return "foreign"
        if hashlib.sha256(payload[raw:raw + RETAIL_SIZE]).hexdigest() != RETAIL_CONTENT_SHA256:
            return "foreign"
        image_size = struct.unpack_from("<I", payload, 0x10C)[0]
        if (flags, size, raw_size, image_size, len(payload)) == (
                RETAIL_FLAGS, RETAIL_SIZE, RETAIL_SIZE, RETAIL_IMAGE_SIZE, RETAIL_FILE_SIZE):
            return "retail" if not any(payload[raw + RETAIL_SIZE:]) else "foreign"
        if (flags, size, raw_size, image_size, len(payload)) == (
                FLAGS, SIZE, SIZE, TABLE_VA + TABLE_SIZE - 0x10000, FILE_SIZE):
            if any(payload[raw + RETAIL_SIZE:TABLE_RAW]) or any(payload[TABLE_RAW + TABLE_SIZE:]):
                return "foreign"
            return "applied"
    except (ValueError, struct.error):
        pass
    return "foreign"


def extend(payload: bytes) -> tuple[bytearray, list[dict]]:
    if state(payload) != "retail":
        raise ValueError("unknown read-only storage header/payload/padding")
    s = _section(payload)
    for other in _sections(payload):
        if other.index != s.index and other.virtual_address < TABLE_VA + TABLE_SIZE and TABLE_VA < other.virtual_address + other.raw_size:
            raise ValueError("fresh table overlaps another section")
    buf = bytearray(payload)
    grown = len(buf) > FILE_SIZE
    if not grown:
        buf.extend(bytes(FILE_SIZE - len(buf)))
    edits = []
    for label, off, value in (("storage_preload", s.header_offset, FLAGS),
                               ("storage_virtual_size", s.header_offset + 8, SIZE),
                               ("storage_raw_size", s.header_offset + 16, SIZE),
                               ("image_size", 0x10C, TABLE_VA + TABLE_SIZE - 0x10000)):
        if grown and label == "image_size":
            continue
        struct.pack_into("<I", buf, off, value)
        edits.append({"label": label, "file_offset": hex(off), "va": hex(0x10000 + off), "size": 4})
    return buf, edits


def image_file_node(read, partition: int, image_size: int, path: str) -> tuple[int, int, int]:
    """Resolve a named file to (sector/length field offset, sector, length).

    ``read(length, offset)`` also accepts the modpack's projected image reader,
    so checking composed operations uses the very same directory traversal as
    the actual SPECIAL writer. Paths are disc paths, never host paths.
    """
    parts = path.split("/")
    if not parts or any(p in ("", ".", "..") or "\\" in p or "\0" in p for p in parts):
        raise ValueError("invalid disc file path")
    header = read(2048, partition + 0x10000)
    if header[:20] != b"MICROSOFT*XBOX*MEDIA" or header[-20:] != header[:20]:
        raise ValueError("invalid XDVDFS volume header")
    sector, length = struct.unpack_from("<II", header, 20)
    for index, component in enumerate(parts):
        start = partition + sector * 2048
        if length < 14 or start + length > image_size:
            raise ValueError("invalid directory extent")
        pending, seen, found = [0], set(), None
        while pending:
            off = pending.pop()
            if off in seen or off + 14 > length or len(seen) >= 4096:
                raise ValueError("invalid directory tree")
            seen.add(off)
            node = read(14, start + off)
            left, right, file_sector, file_length = struct.unpack_from("<HHII", node)
            if not node[13] or off + 14 + node[13] > length:
                raise ValueError("invalid directory name")
            name = read(node[13], start + off + 14).decode("latin-1")
            if name.casefold() == component.casefold():
                if found is not None:
                    raise ValueError("ambiguous disc file node")
                found = (start + off + 4, file_sector, file_length, node[12])
            pending.extend(child * 4 for child in (left, right) if child)
        if found is None:
            raise ValueError(f"missing disc file: {path}")
        node, sector, length, attributes = found
        if partition + sector * 2048 + length > image_size:
            raise ValueError("disc file extent exceeds image")
        if bool(attributes & 0x10) != (index < len(parts) - 1):
            raise ValueError("disc path has the wrong file/directory type")
    return node, sector, length


def write_image_xbe(descriptor: int, payload: bytes) -> dict:
    """Write an already patched XBE to a disposable XISO, with rollback.

    Growth appends the complete file and switches only its root-directory
    sector/length. No following file is overwritten. Replays use the existing
    allocation. This helper is ready for the protected builder/throw writer.
    """
    from . import platform_compat as io
    from . import nfl2k5_throw_tuning as tt
    if not recognized_grown_xbe(payload):
        raise ValueError("expected a complete recognised grown XBE")
    xc = tt._xdvdfs_module()
    image_size = os.fstat(descriptor).st_size
    entries, directory = xc.parse_xdvdfs(descriptor, image_size)
    entry = entries.get("default.xbe")
    from . import nfl2k5_xbe_space as space
    from . import nfl2k5_music_storage as music_storage
    if entry is None or entry.size not in (RETAIL_FILE_SIZE, FILE_SIZE, space.FILE_SIZE, music_storage.FILE_SIZE, space.EXT_FILE_SIZE):
        raise ValueError("unknown default.xbe extent")
    original = io.pread(descriptor, entry.size, entry.byte_offset)
    if (len(original) != entry.size or
            not (entry.size == RETAIL_FILE_SIZE and state(original) == "retail"
                 or recognized_grown_xbe(original))):
        raise ValueError("unknown default.xbe storage before write")
    node, sector, length = image_file_node(
        lambda count, offset: io.pread(descriptor, count, offset),
        entry.base_offset, image_size, "default.xbe")
    if (sector, length) != (entry.sector, entry.size):
        raise ValueError("ambiguous default.xbe root node")
    old_node = io.pread(descriptor, 8, node)
    growth = entry.size != len(payload)
    offset = ((image_size + 2047) // 2048) * 2048 if growth else entry.byte_offset
    sector = (offset - entry.base_offset) // 2048
    new_node = struct.pack("<II", sector, len(payload))

    def write(data, at):
        if io.pwrite(descriptor, data, at) != len(data):
            raise ValueError("short grown XBE write")

    try:
        if growth and offset > image_size:
            write(bytes(offset - image_size), image_size)
        write(payload, offset)
        if io.pread(descriptor, len(payload), offset) != payload:
            raise ValueError("SPECIAL XBE payload read-back differs")
        if growth:
            write(new_node, node)
        os.fsync(descriptor)
        if xc.xbe_extent(descriptor, os.fstat(descriptor).st_size) != (offset, len(payload)):
            raise ValueError("SPECIAL XBE directory read-back differs")
    except Exception as exc:
        try:
            if growth:
                write(old_node, node)
                os.ftruncate(descriptor, image_size)
            else:
                write(original, offset)
            os.fsync(descriptor)
            if io.pread(descriptor, 8, node) != old_node or io.pread(descriptor, entry.size, entry.byte_offset) != original:
                raise ValueError("rollback read-back differs")
        except Exception as rollback:
            raise ValueError(f"{exc}; rollback failed: {rollback}; discard this output copy") from exc
        raise
    return {"offset": offset, "size": len(payload), "directory_offset": node,
            "image_growth": os.fstat(descriptor).st_size - image_size, "relocated": growth}


def recognized_grown_xbe(payload: bytes) -> bool:
    """One recognition policy shared by the writer and protected extent handoff."""
    from . import nfl2k5_depth_chart_rows as rows
    from . import nfl2k5_xbe_space as space
    from . import nfl2k5_music_storage as music_storage
    if len(payload) in (space.FILE_SIZE, music_storage.FILE_SIZE, space.EXT_FILE_SIZE) and space.status(payload) == "applied":
        return space.special_state(payload) == "retail" or rows.status(payload) == "applied"
    return len(payload) == FILE_SIZE and rows.status(payload) == "applied"


def allocation_evidence(retail: bytes, manifest) -> dict:
    """No overwritten mapping/owner or encoded retail reference to the new page.

    The existing oracle cannot allocate unmapped memory and its unknown verdict
    is unchanged. Use its validated mapping and manifest for this distinct
    loader-extension proof. Register-synthesized addresses and external effects
    are outside this static proof, as they are for an ordinary new link section.
    """
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(retail)
    if manifest.document.get("retail_sha256") != image.sha256:
        raise ValueError("allocation evidence uses a different image's manifest")
    start, end = TABLE_VA, TABLE_VA + 0x1000
    if image.base + image.image_size > start or image.section(start):
        raise ValueError("new storage overlaps a retail image allocation")
    # After Claude regenerates, this audits the current owner's established
    # allocation; it must still reject every other owner, including overlaps.
    if manifest.overlaps(start, end, exclude_owner="nfl2k5_depth_chart_rows"):
        raise ValueError("new storage overlaps a manifest owner")
    hits = []
    spans = [(image.base, retail[:image.headers_size], False)]
    spans += [(s.start, retail[s.raw:s.raw + s.raw_size], s.executable) for s in image.sections]
    for base, data, executable in spans:
        for off in range(len(data)):
            if off + 4 <= len(data) and start <= struct.unpack_from("<I", data, off)[0] < end:
                hits.append((base + off, "absolute"))
            if not executable:
                continue
            op, prefix, width = data[off], 0, 0
            if op in (0xE8, 0xE9):
                prefix, width = 1, 4
            elif op == 0x0F and off + 1 < len(data) and 0x80 <= data[off + 1] <= 0x8F:
                prefix, width = 2, 4
            elif op == 0xEB or 0x70 <= op <= 0x7F or 0xE0 <= op <= 0xE3:
                prefix, width = 1, 1
            if width and off + prefix + width <= len(data):
                delta = int.from_bytes(data[off + prefix:off + prefix + width], "little", signed=True)
                target = (base + off + prefix + width + delta) & 0xFFFFFFFF
                if start <= target < end:
                    hits.append((base + off, "relative"))
    if hits:
        raise ValueError(f"retail reference encodings into fresh storage: {hits[:8]}")
    return {"allocation": "new_read_only_section_tail", "start": hex(start), "end": hex(end),
            "retail_image_end": hex(image.base + image.image_size), "encoded_references": [],
            "manifest_overlaps": [], "cave_verdict": "unmapped; no existing cave allocated",
            "proof_boundary": "encoded references and loader mappings; no gameplay witness"}

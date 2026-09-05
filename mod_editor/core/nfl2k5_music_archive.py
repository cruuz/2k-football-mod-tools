"""Bounded archive/resource and named-disc-file primitives for music builds.

EXPERIMENTAL / UNWITNESSED. No cached physical ranges and no in-place public
writer. The caller must own a disposable image until all verification passes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import struct
import zlib

from tools import nfl2k5_commentary_swap as audio
from tools.nfl_outer import HEADER_SIZE, ENTRY_SIZE, align_up
from . import platform_compat as io
from .nfl2k5_depth_chart_storage import image_file_node

PACK_NAMES = "0123456789ABCDEF"
BLOCK = 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(read, size):
    result = hashlib.sha256()
    for at in range(0, size, BLOCK):
        data = read(min(BLOCK, size - at), at)
        require(len(data) == min(BLOCK, size - at), "short hash read")
        result.update(data)
    return result.hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        result = hashlib.sha256()
        while data := stream.read(BLOCK):
            result.update(data)
        return result.hexdigest()


def chunks(payload):
    """Walk complete 0x20-byte resource wrappers, retaining zero slot gaps.

    The selected retail containers are sequential resources, with self-relative
    body references. No enclosing offset table is present. Preserve every other
    resource (including its wrapper), order, and gap byte for byte.
    """
    at, index = 0, 0
    while at < len(payload):
        if payload[at:at + 16] == bytes(16):
            at += 16
            continue
        require(at % 16 == 0 and at + 32 <= len(payload), "unaligned/truncated resource wrapper")
        magic, size = struct.unpack_from("<4sI", payload, at)
        require(all(32 <= x < 127 for x in magic) and size > 0 and size % 16 == 0
                and at + 32 + size <= len(payload), "invalid resource wrapper/size")
        yield index, at, payload[at:at + 32 + size]
        index += 1
        at += 32 + size
    require(at == len(payload), "unparsed resource suffix")


@dataclass(frozen=True)
class Descriptor:
    outer: int
    chunk: int
    offset: int
    raw: bytes
    name: str
    external: int
    channels: int
    boundaries: tuple[int, ...]


class Disc(audio.DiscBanks):
    """Fresh image reader; all constructor failures close the reader handle.

    Stable outer/chunk ownership is pinned; offsets and sizes are resolved by
    walking wrappers so changed counts can be reopened safely.
    """
    def __init__(self, path, *, descriptors=audio.PINNED_DESCRIPTORS):
        self.path = Path(path).resolve()
        self.descriptors = descriptors
        self.descriptor = os.open(self.path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            self.image_size = os.fstat(self.descriptor).st_size
            self.entries, _ = audio.xiso.parse_xdvdfs(self.descriptor, self.image_size)
            self.pack_extents = self._pack_extents()
            require(tuple(self.pack_extents) == tuple(PACK_NAMES), "writer requires exactly packs 0..F")
            pack0 = self.pack_extents['0']
            self.header = self.read(HEADER_SIZE, pack0.byte_offset)
            count = struct.unpack_from('<I', self.header)[0]
            require(HEADER_SIZE + count*ENTRY_SIZE <= pack0.size, 'outer index exceeds pack 0')
            self.archive_entries = self._parse_archive()
            require(self.archive_entries[-1].virtual_end == self.packs[-1].virtual_end,
                    "last outer must reach archive end")
            require(len({e.name_id for e in self.archive_entries}) == len(self.archive_entries), "duplicate outer ID")
            require(not any(struct.unpack_from('<20I', self.header, 12 + 16 * 4)), "nonzero unused packs")
            self.partition = pack0.base_offset
            # Reject overlapping named extents, including directories. The
            # parser returns directory records as well as ordinary files.
            spans = sorted((e.byte_offset, e.byte_offset + e.size, name)
                           for name, e in self.entries.items() if e.size)
            root_sector, root_size = struct.unpack('<II', self.read(8,self.partition+0x10014))
            root_at = self.partition + root_sector*2048
            spans.append((root_at,root_at+root_size,'root directory'))
            spans.sort()
            end = self.partition + 0x10800
            for lo, hi, name in spans:
                require(lo >= end, f"overlapping disc file or metadata: {name}")
                end = hi
            self.nodes = {}
            for name, extent in self.pack_extents.items():
                node = image_file_node(self.read, self.partition, self.image_size, f"vc_53450030/{name}")
                require(node[1:] == (extent.sector, extent.size), "ambiguous pack directory node")
                self.nodes[name] = node
            self.containers = {}
            self.descriptor_records = self._descriptors()
            self.banks = {}
            for d in self.descriptor_records:
                if d.name in self.banks:
                    old = self.banks[d.name]
                    require((old.channels, old.boundaries, old.external) ==
                            (d.channels, d.boundaries, d.external), "AUSB aliases disagree")
                self.banks[d.name] = d
        except BaseException:
            self.close()
            raise

    def read(self, count, offset):
        data = io.pread(self.descriptor, count, offset)
        require(len(data) == count, "short disc read")
        return data

    def _descriptors(self):
        result = []
        for outer in sorted({pin[0] for pin in self.descriptors}):
            entry = self.archive_entries[outer]
            require(entry.size <= 32 * BLOCK, "descriptor container exceeds 32 MiB budget")
            payload = self.read_entry_range(entry, 0, entry.size)
            self.containers[outer] = payload
            walked = list(chunks(payload))
            wanted = {p[1]: p[4] for p in self.descriptors if p[0] == outer}
            require({i for i, _, raw in walked if raw[:4] == b'AUSB'} == set(wanted),
                    "foreign AUSB resource ownership")
            for index, at, raw in walked:
                if index not in wanted:
                    continue
                require(raw[:4] == raw[0x2C:0x30] == b'AUSB' and not any(raw[8:32]), "foreign AUSB wrapper")
                require(len(raw) >= 0xBC, "short AUSB descriptor")
                name_at = 0x2F + struct.unpack_from('<i', raw, 0x30)[0]
                require(0x34 <= name_at < 0x60, "foreign AUSB name pointer")
                name = audio._utf16z(raw, name_at, 0x60)
                external_name = audio._utf16z(raw, 0x60, 0xA0)
                require(name == wanted[index] and external_name.casefold() == name + '.bin', "foreign bank name")
                count, _, channels, rate, unit = struct.unpack_from('<5I', raw, 0xA0)
                require(0 < count <= 100000 and channels in (1, 2) and rate == 22050 and unit == 0x12000,
                        "unsupported AUSB words")
                require(0xB8 + 4 * (count + 1) <= len(raw), "truncated AUSB boundaries")
                boundaries = struct.unpack_from(f'<{count + 1}I', raw, 0xB8)
                crc = zlib.crc32(external_name.upper().encode('utf-16le')) & 0xFFFFFFFF
                matches = [e for e in self.archive_entries if e.name_id == crc]
                require(len(matches) == 1, "bank external file is not unique")
                entry = matches[0]
                require(boundaries[0] == 0 and boundaries[-1] == entry.size and
                        all(a < b and (b-a) % (36*channels) == 0 for a, b in zip(boundaries, boundaries[1:])),
                        "invalid/non-block AUSB boundaries")
                result.append(Descriptor(outer, index, at, raw, name, entry.table_index, channels, boundaries))
        require(len(result) == len(self.descriptors), "missing descriptor")
        return tuple(result)

    def outer_hash(self, index):
        entry = self.archive_entries[index]
        return digest(lambda n, at: self.read_entry_range(entry, at, n), entry.size)


def boundary_writer(descriptor, boundaries):
    require(len(boundaries) >= 2 and boundaries[0] == 0 and boundaries[-1] <= 0xFFFFFFFF
            and all(a < b and (b-a) % (36*descriptor.channels) == 0 for a, b in zip(boundaries, boundaries[1:])),
            "invalid replacement boundaries")
    old_count = len(descriptor.boundaries) - 1
    count = len(boundaries) - 1
    raw = descriptor.raw
    if count == old_count:
        result = bytearray(raw)  # exact same-count fast path, including padding
    else:
        tail = raw[0xB8 + 4*(old_count + 1):]
        require(not any(tail), "unknown live descriptor suffix; cannot resize")
        result = bytearray(align_up(0xB8 + 4*(count + 1), 16))
        result[:0xB8] = raw[:0xB8]
        struct.pack_into('<I', result, 4, len(result) - 32)
        struct.pack_into('<I', result, 0xA0, count)
    struct.pack_into(f'<{count + 1}I', result, 0xB8, *boundaries)
    return bytes(result)


def rewrite_containers(disc, replacements):
    result = {}
    for outer, payload in disc.containers.items():
        cursor, pieces = 0, []
        for index, at, raw in chunks(payload):
            pieces.append(payload[cursor:at])
            pieces.append(replacements.get((outer, index), raw))
            cursor = at + len(raw)
        pieces.append(payload[cursor:])
        rewritten = b''.join(pieces)
        if rewritten != payload:
            result[outer] = rewritten
    return result


def layout(disc, sizes):
    at = align_up(HEADER_SIZE + ENTRY_SIZE * len(disc.archive_entries))
    entries, moved = [], []
    for old in disc.archive_entries:
        size = sizes.get(old.table_index, old.size)
        require(0 < size <= 0xFFFFFFFF and at // 2048 <= 0xFFFFFFFF, "outer u32 limit")
        item = dict(index=old.table_index, name_id=old.name_id, offset=at, size=size)
        entries.append(item)
        if at != old.virtual_offset:
            moved.append(dict(index=old.table_index, before=old.virtual_offset, after=at))
        end = at + size
        at = align_up(end)
    require(end == at, "final outer must end on a pack boundary")
    final_size = end - disc.packs[-1].virtual_start
    require(0 < final_size < 2**31, "pack F must be positive and below 2 GiB")
    packs, image_size = [], disc.image_size
    for pack in disc.packs:
        size = final_size if pack.name == 'F' else pack.size
        node, sector, _ = disc.nodes[pack.name]
        if size > pack.size:
            offset = align_up(image_size)
            sector = (offset - disc.partition) // 2048
            image_size = offset + size
        else:
            offset = disc.pack_extents[pack.name].byte_offset
        require(sector <= 0xFFFFFFFF and size <= 0xFFFFFFFF, "XDVDFS u32 limit")
        packs.append(dict(name=pack.name, virtual_start=pack.virtual_start, size=size,
                          delta=size-pack.size, offset=offset, sector=sector, node=node))
    return dict(entries=entries, moved_outers=moved, packs=packs, virtual_size=end, image_size=image_size)


def write_all(fd, payload, offset):
    view = memoryview(payload)
    while view:
        n = io.pwrite(fd, view, offset)
        require(n > 0, "short image write")
        view = view[n:]
        offset += n


def write_virtual(fd, packs, offset, payload):
    end = offset + len(payload)
    written = 0
    for p in packs:
        lo, hi = max(offset, p['virtual_start']), min(end, p['virtual_start'] + p['size'])
        if lo < hi:
            write_all(fd, payload[lo-offset:hi-offset], p['offset'] + lo-p['virtual_start'])
            written += hi-lo
    require(written == len(payload), "virtual write escapes packs")


def write_named(fd, read, partition, path, replacement, size):
    """Grow by append/repoint; shrink in the existing extent, retaining slack."""
    before = os.fstat(fd).st_size
    node, sector, old_size = image_file_node(read, partition, before, path)
    require(0 < size <= 0xFFFFFFFF, "invalid named file size")
    offset = align_up(before) if size > old_size else partition + sector * 2048
    sector = (offset - partition) // 2048
    require(sector <= 0xFFFFFFFF, "named file sector overflow")
    for at in range(0, size, BLOCK):
        data = replacement(min(BLOCK, size-at), at)
        require(len(data) == min(BLOCK, size-at), "short named replacement")
        write_all(fd, data, offset+at)
    write_all(fd, struct.pack('<II', sector, size), node)
    require(image_file_node(read, partition, os.fstat(fd).st_size, path) == (node, sector, size),
            "named file directory read-back failed")
    return dict(path=path, directory_offset=node, offset=offset, size=size,
                before_size=old_size, image_growth=os.fstat(fd).st_size-before)

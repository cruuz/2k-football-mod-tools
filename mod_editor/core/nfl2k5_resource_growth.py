"""Stream an existing pack-0 resource collection into a grown archive pack.

Generalizes the scorebug appended-TXTR layout using the music archive's bounded
I/O primitives. All existing outer identities/order survive; virtual offsets
after the insertion and pack-0's block count move together. The caller owns
the XDVDFS transaction. No whole archive pack is materialized in memory.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct

from . import nfl2k5_music_archive as archive
from . import platform_compat as io
from tools.nfl_outer import HEADER_SIZE, align_up

require = archive.require


@dataclass(frozen=True)
class CollectionPlan:
    table: bytes
    start: int
    old_end: int
    replacement: bytes
    size_before: int
    size_after: int
    source_sha256: str
    outer: int
    fixed_spans: tuple = ()
    padding_byte: int = 0


def plan_pack0(read, size, outer, name_id, replacement, *, fixed_spans=(), padding_bytes=(0,)):
    """read(count, pack_offset); bounded replacement of one existing collection."""
    require(0 < len(replacement) <= 32*archive.BLOCK and len(replacement) % 16 == 0,
            "collection replacement must fit the 32 MiB budget and 16-byte alignment")
    require(size > HEADER_SIZE and size % 2048 == 0, "pack 0 size/alignment")
    header = read(HEADER_SIZE, 0)
    require(len(header) == HEADER_SIZE, "short archive header")
    count, reserved, packs = struct.unpack_from("<3I", header)
    require(reserved == 0 and 1 <= count <= 100000 and 1 <= packs <= 36
            and type(outer) is int and 0 <= outer < count, "foreign outer table header")
    blocks = struct.unpack_from("<36I", header, 12)
    require(blocks[0]*2048 == size and all(blocks[:packs]) and not any(blocks[packs:]),
            "archive pack counts differ from their allocation")
    table_size = HEADER_SIZE+count*12
    require(table_size <= size, "archive table exceeds pack 0")
    table = bytearray(read(table_size, 0))
    require(len(table) == table_size, "short archive table")
    entries = [struct.unpack_from("<3I", table, HEADER_SIZE+i*12) for i in range(count)]
    require(len({e[0] for e in entries}) == count, "duplicate outer identities")
    end = align_up(table_size)
    for identity, length, sector in entries:
        start = sector*2048
        require(length > 0 and start >= end and start+length <= sum(blocks)*2048,
                "overlapping or out-of-range archive entry")
        end = align_up(start+length)
    identity, length, sector = entries[outer]
    start = sector*2048
    require(identity == name_id and start+length <= size, "collection identity or pack containment changed")
    old_end = align_up(start+length)
    gap_size = old_end-start-length
    gap = read(gap_size, start+length)
    require(len(gap) == gap_size and any(gap == bytes([value])*gap_size for value in padding_bytes),
            "unrecognized collection alignment padding")
    padding_byte = gap[0] if gap else 0
    growth = align_up(start+len(replacement))-old_end
    new_size = size+growth
    require(0 < new_size <= 0xffffffff and new_size % 2048 == 0, "grown pack size overflow")
    struct.pack_into("<I", table, 12, new_size//2048)
    struct.pack_into("<I", table, HEADER_SIZE+outer*12+4, len(replacement))
    for index in range(outer+1, count):
        new_sector = entries[index][2]+growth//2048
        require(0 <= new_sector <= 0xffffffff, "grown virtual sector overflow")
        struct.pack_into("<I", table, HEADER_SIZE+index*12+8, new_sector)
    spans = tuple(sorted((at, bytes(before), bytes(after)) for at,before,after in fixed_spans))
    require(sum(len(before) for _,before,_ in spans) <= 32*archive.BLOCK, "fixed edits exceed 32 MiB")
    previous = table_size
    for at,before,after in spans:
        require(at >= previous and len(before) == len(after) > 0 and at+len(before) <= size
                and (at+len(before) <= start or at >= old_end), "overlapping/out-of-range fixed pack edit")
        require(read(len(before), at) == before, "fixed pack edit differs from its source pin")
        previous = at+len(before)
    return CollectionPlan(bytes(table), start, old_end, bytes(replacement), size, new_size,
                          archive.digest(read, size), outer, spans, padding_byte)


def write_pack0(fd, read, plan, offset):
    """Write/verify only a new extent. Revalidate source before any write."""
    require(offset >= 0 and offset % 2048 == 0, "destination pack must be sector aligned")
    require(archive.digest(read, plan.size_before) == plan.source_sha256,
            "source pack changed after collection preflight")
    digest = hashlib.sha256()
    cursor = 0

    def write(data):
        nonlocal cursor
        require(io.pwrite(fd, data, offset+cursor) == len(data), "short collection pack write")
        digest.update(data)
        cursor += len(data)

    def copy(start, end):
        for at in range(start, end, archive.BLOCK):
            count = min(archive.BLOCK, end-at)
            data = read(count, at)
            require(len(data) == count, "short source pack read")
            for edit_at, before, after in plan.fixed_spans:
                lo, hi = max(at, edit_at), min(at+count, edit_at+len(after))
                if lo < hi:
                    buf = bytearray(data)
                    buf[lo-at:hi-at] = after[lo-edit_at:hi-edit_at]
                    data = bytes(buf)
            write(data)

    write(plan.table)
    copy(len(plan.table), plan.start)
    for at in range(0, len(plan.replacement), archive.BLOCK):
        write(plan.replacement[at:at+archive.BLOCK])
    write(bytes([plan.padding_byte])*(align_up(cursor)-cursor))
    copy(plan.old_end, plan.size_before)
    require(cursor == plan.size_after, "grown collection pack length mismatch")
    expected = digest.hexdigest()
    require(archive.digest(lambda n, at: io.pread(fd, n, offset+at), cursor) == expected,
            "grown collection pack readback mismatch")
    return dict(outer=plan.outer, pack_size_before=plan.size_before, pack_size_after=plan.size_after,
                pack_growth=plan.size_after-plan.size_before, before_sha256=plan.source_sha256,
                after_sha256=expected, streamed_block_bytes=archive.BLOCK)

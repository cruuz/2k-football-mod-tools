"""EA ``QL01`` preload caches: what they copy, and which container's bytes it is.

A ``QL01`` file is not a container.  It is a **flat run of byte copies** of
things that already exist elsewhere on the disc, laid out so the game can
stream a screen's worth of data in one read.  Two kinds of copy are carried
[M]:

* a **container header** -- the first ``data_offset`` bytes of a ``TERF``
  file, which is its header plus the ``DIR1`` and ``COMP`` directories;
* a **member**, byte for byte as that member is stored in its container.

**This is load-bearing for any writer.**  A member edit that changes a
member's stored size or codec moves the container's directory, and a cache
still carrying the old directory hands the game the wrong offsets.  A member
that is itself copied has to be rewritten in the cache too, or the game
preloads the stale bytes and the edit is silently ignored.

The format [M]::

    QL01 chunk   8-byte tag+size, then a u32 payload offset at +0x08
    FILS chunk   tag, size, u32 count, then count x 48-byte NUL-padded names
    DTLS chunk   tag, size, u32 count, then count x 12-byte entries
    DATA chunk   tag, size 0; the payload runs from the QL01 offset to EOF

A ``DTLS`` entry is ``u8 kind, u8, u8 file index, u8, u32 member, u32
offset``: *kind* 0 is a header copy and 1 a member copy, *file index* points
into ``FILS``, and *offset* is relative to the payload.

Two discs are measured against this reader [M]: Madden NFL 09 (``SLUS-21770``)
ships ``GAME.QKL`` and ``FE.QKL`` carrying 6,270 copies across 39 containers,
and NCAA Football 09 (``SLUS-21752``) ships **three** caches -- ``FE.QKL``,
``GAME.QKL`` and ``PL.QKL`` -- carrying 564 copies across 47 containers.  The
same reader opens both; the cache count is a fact about the disc, not about
the format.

**Why attribution is a separate step.**  A ``DTLS`` row at a container
boundary can name a member the container it names does not have, and the bytes
at its offset are then the *next* thing the cache carries.  Measured twice on
Madden 09's retail disc and twelve times on Madden 06 [M].  So a row whose
declared member does not exist is re-attributed to another row at the same
offset in the same cache whose own attribution resolves and whose source bytes
are what is actually there; the row's own words are kept beside it.  Anything
else keeps its words and is refused by :meth:`PreloadCopy.length_in`, which
names the offset rather than guessing a length.

**Retail-free.**  This module carries the format's own constants and nothing
read off a disc.  A caller hands it bytes; it hands back offsets, lengths and
names.

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
import struct
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from mod_editor.games.contract import Refusal

from . import ea_terf

#: The magic a cache starts with.
QL01_MAGIC = b"QL01"
#: The chunk naming every file the cache copies from.
QL01_FILS = b"FILS"
#: The chunk listing the copies themselves.
QL01_DTLS = b"DTLS"
#: The tag the payload chunk carries.  Its declared size is 0 on every
#: measured cache: the payload runs from the ``QL01`` offset to EOF [M].
QL01_DATA_TAG = b"DATA"
#: Where the u32 payload offset sits inside the ``QL01`` chunk.
QL01_PAYLOAD_OFFSET = 8
#: One ``FILS`` name is a NUL-padded fixed-width slot.
QL01_NAME_STRIDE = 48
#: One ``DTLS`` row.
QL01_ENTRY_STRIDE = 12
#: Every chunk begins with a 4-byte tag and a u32 size.
QL01_CHUNK_HEADER = 8
#: Both count words sit one chunk header into their chunk.
QL01_COUNT_OFFSET = 8

#: ``DTLS`` kind 0: the copy is a container's header and directories.
PRELOAD_KIND_HEADER = 0
#: ``DTLS`` kind 1: the copy is one member's stored bytes.
PRELOAD_KIND_MEMBER = 1

#: Sanity bounds.  A file declaring more than these is being read at the wrong
#: offset, and saying so is better than allocating for it.
QL01_MAX_FILES = 4096
QL01_MAX_ENTRIES = 1 << 20

#: How many chunks the chain is walked for before the file is called malformed.
QL01_MAX_CHUNKS = 64


class Ql01Error(Refusal):
    """This cache could not be read; the sentence says what was found."""


@dataclass(frozen=True)
class PreloadCopy:
    """One byte-for-byte copy a preload cache carries, and where it lives.

    :attr:`container`, :attr:`kind` and :attr:`member` are what this copy
    **is**, which is not always what its ``DTLS`` row *said*: see
    :func:`attribute`.  The row's own words survive in
    :attr:`declared_container` / :attr:`declared_kind` /
    :attr:`declared_member`, so nothing is lost and the coherence rule covers
    the bytes rather than the claim.
    """

    cache: str
    container: str
    kind: int
    #: The member copied, or ``None`` for a header copy.
    member: Optional[int]
    #: Absolute byte offset inside the cache file.
    offset: int
    #: What the ``DTLS`` row named, when that is not what this copy is.
    declared_container: str = ""
    declared_kind: Optional[int] = None
    declared_member: Optional[int] = None

    @property
    def is_header(self) -> bool:
        return self.kind == PRELOAD_KIND_HEADER

    @property
    def reattributed(self) -> bool:
        """Whether this copy's ``DTLS`` row named something it is not."""

        return bool(self.declared_container)

    def length_in(self, parsed: ea_terf.TerfContainer) -> int:
        """How many bytes this copy is, given the container it copies."""

        if self.is_header:
            return parsed.data_offset
        if self.member is None or not 0 <= self.member < parsed.member_count:
            raise Ql01Error(
                f"{self.cache} carries a copy of {self.container} member "
                f"{self.member} at byte {self.offset}, and that container has "
                f"{parsed.member_count} member(s) (0..{parsed.member_count - 1}); "
                f"no other copy in the cache at that offset matches the bytes "
                f"there, so how long this copy is cannot be said."
            )
        return parsed.members[self.member].stored_size

    def as_dict(self) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "cache": self.cache,
            "container": self.container,
            "kind": "header" if self.is_header else "member",
            "member": self.member,
            "offset": self.offset,
        }
        if self.reattributed:
            row["declared_container"] = self.declared_container
            row["declared_kind"] = ("header" if self.declared_kind == PRELOAD_KIND_HEADER
                                    else "member")
            row["declared_member"] = self.declared_member
        return row


@dataclass(frozen=True)
class ContainerPreload:
    """Every copy of one container the caches carry."""

    container: str
    header: Tuple[PreloadCopy, ...] = ()
    members: Mapping[int, Tuple[PreloadCopy, ...]] = dataclass_field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.header and not self.members

    def for_member(self, index: int) -> Tuple[PreloadCopy, ...]:
        return tuple(self.members.get(index, ()))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "container": self.container,
            "header": [copy.as_dict() for copy in self.header],
            "members": {str(index): [copy.as_dict() for copy in items]
                        for index, items in sorted(self.members.items())},
        }


@dataclass(frozen=True)
class ContainerShape:
    """What a ``TERF`` file's own header says, read from its first bytes.

    Enough to say how many members it has, how long its directory is, and
    where any one member's stored bytes sit -- without holding a 180 MB
    container in memory to answer a question about 512 bytes of a cache.
    """

    head: bytes
    member_count: int
    data_offset: int
    directory_offset: int

    def member(self, index: int) -> Optional[Tuple[int, int]]:
        """``(offset in DATA, stored size)`` for member *index*, if it is there."""

        if not 0 <= index < self.member_count:
            return None
        at = self.directory_offset + 8 + 8 * index
        if at + 8 > len(self.head):
            return None
        offset, stored = struct.unpack_from("<II", self.head, at)
        return int(offset), int(stored)


def container_shape(head: bytes) -> Optional[ContainerShape]:
    """Read a ``TERF`` file's shape from its first bytes, or ``None``.

    ``None`` is a state, not a failure: a ``/DATA`` file a cache names may not
    be a ``TERF`` container at all, and a caller that has to tell "not a
    container" from "unreadable" gets the first here and an exception nowhere.
    """

    if not head or not head.startswith(ea_terf.TERF_MAGIC):
        return None
    try:
        _alignment, member_count = struct.unpack_from("<HH", head, 12)
    except struct.error:
        return None
    position = 0
    directory_offset = data_offset = -1
    for _ in range(QL01_MAX_CHUNKS):
        if position + QL01_CHUNK_HEADER > len(head):
            break
        tag = bytes(head[position:position + 4])
        size, = struct.unpack_from("<I", head, position + 4)
        if size < QL01_CHUNK_HEADER:
            break
        if tag == ea_terf.DIR1_MAGIC:
            directory_offset = position
        if tag == ea_terf.DATA_MAGIC:
            data_offset = position
            break
        position += size
    if directory_offset < 0 or data_offset < 0:
        return None
    return ContainerShape(head=head, member_count=int(member_count),
                          data_offset=data_offset, directory_offset=directory_offset)


class CopySource(Protocol):
    """What :func:`attribute` and :func:`collect` need of a disc.

    Three questions, all read-only, all answerable from a few kilobytes: which
    ``/DATA`` files are present, what shape one of them is, and what bytes sit
    at a given run inside one.  A game module's ``containers`` module answers
    them off the user's own image; a test answers them from a dict.
    """

    def names(self) -> Sequence[str]:
        """Every ``/DATA`` file name present, upper-cased."""

    def shape(self, name: str) -> Optional[ContainerShape]:
        """*name*'s container shape, or ``None`` if it is not a container."""

    def bytes_at(self, name: str, start: int, length: int) -> Optional[bytes]:
        """*length* bytes of *name* starting at *start*, or ``None``."""

    def cache_bytes(self, name: str) -> Optional[bytes]:
        """A whole cache file, or ``None`` when it is not on this image."""


def parse_cache(data: bytes, cache: str) -> Tuple[PreloadCopy, ...]:
    """Every copy a ``QL01`` cache declares.  Refuses; never guesses."""

    if len(data) < QL01_CHUNK_HEADER + 4 or data[:4] != QL01_MAGIC:
        raise Ql01Error(
            f"{cache} starts with {bytes(data[:4])!r}, not {QL01_MAGIC!r}, so it is not "
            f"a preload cache. Nothing here reads it."
        )
    chunks: Dict[bytes, Tuple[int, int]] = {}
    cursor = 0
    for _ in range(QL01_MAX_CHUNKS):
        if cursor + QL01_CHUNK_HEADER > len(data):
            break
        tag = bytes(data[cursor:cursor + 4])
        size, = struct.unpack_from("<I", data, cursor + 4)
        chunks[tag] = (cursor, int(size))
        if size <= 0 or cursor + size > len(data):
            break
        cursor += size
    for wanted in (QL01_FILS, QL01_DTLS):
        if wanted not in chunks:
            raise Ql01Error(
                f"{cache} carries no {wanted.decode('ascii')} chunk, so it does not say "
                f"what it copies. Nothing here reads it."
            )
    payload, = struct.unpack_from("<I", data, QL01_PAYLOAD_OFFSET)
    if not 0 < payload <= len(data):
        raise Ql01Error(
            f"{cache} puts its payload at byte {payload} and the file is {len(data)} "
            f"bytes; it is being read at the wrong offset."
        )

    files_offset, _size = chunks[QL01_FILS]
    file_count, = struct.unpack_from("<I", data, files_offset + QL01_COUNT_OFFSET)
    if not 0 <= file_count <= QL01_MAX_FILES:
        raise Ql01Error(
            f"{cache} declares {file_count} file name(s); this reader stops at "
            f"{QL01_MAX_FILES}, so the cache is being read at the wrong offset."
        )
    names: List[str] = []
    base = files_offset + QL01_COUNT_OFFSET + 4
    for index in range(file_count):
        start = base + QL01_NAME_STRIDE * index
        if start + QL01_NAME_STRIDE > len(data):
            raise Ql01Error(f"{cache}'s file-name table runs past the end of the file.")
        names.append(bytes(data[start:start + QL01_NAME_STRIDE]).split(b"\x00")[0]
                     .decode("latin-1").upper())

    entries_offset, _size = chunks[QL01_DTLS]
    entry_count, = struct.unpack_from("<I", data, entries_offset + QL01_COUNT_OFFSET)
    if not 0 <= entry_count <= QL01_MAX_ENTRIES:
        raise Ql01Error(
            f"{cache} declares {entry_count} copies; this reader stops at "
            f"{QL01_MAX_ENTRIES}, so the cache is being read at the wrong offset."
        )
    out: List[PreloadCopy] = []
    base = entries_offset + QL01_COUNT_OFFSET + 4
    for index in range(entry_count):
        start = base + QL01_ENTRY_STRIDE * index
        if start + QL01_ENTRY_STRIDE > len(data):
            raise Ql01Error(f"{cache}'s copy table runs past the end of the file.")
        kind = data[start]
        file_index = data[start + 2]
        member, offset = struct.unpack_from("<II", data, start + 4)
        if file_index >= len(names):
            raise Ql01Error(
                f"{cache} copy {index} names file {file_index} and the cache lists "
                f"{len(names)}."
            )
        if kind not in (PRELOAD_KIND_HEADER, PRELOAD_KIND_MEMBER):
            continue
        out.append(PreloadCopy(
            cache=cache, container=names[file_index], kind=int(kind),
            member=None if kind == PRELOAD_KIND_HEADER else int(member),
            offset=payload + int(offset)))
    return tuple(out)


def cache_names(data: bytes, cache: str) -> Tuple[str, ...]:
    """Every container *cache* names, in the order its rows first mention them.

    The conservative floor a writer asks about before it touches a container:
    a container a cache names is one whose directory the cache may be carrying.
    """

    seen: List[str] = []
    for copy in parse_cache(data, cache):
        if copy.container and copy.container not in seen:
            seen.append(copy.container)
    return tuple(seen)


def attribute(copies: Sequence[PreloadCopy], blob: bytes,
              source: CopySource) -> Tuple[PreloadCopy, ...]:
    """File every copy under the container whose bytes it actually equals.

    A row whose declared member does not exist is re-attributed to another row
    **at the same offset in the same cache** whose own attribution resolves and
    whose source bytes are what is there.  Anything else keeps its own words.
    """

    present = {name.upper() for name in source.names()}
    shapes: Dict[str, Optional[ContainerShape]] = {}

    def shape_of(name: str) -> Optional[ContainerShape]:
        key = name.upper()
        if key not in shapes:
            shapes[key] = source.shape(key) if key in present else None
        return shapes[key]

    def resolves(copy: PreloadCopy) -> bool:
        shape = shape_of(copy.container)
        if shape is None:
            return True  # not on this image: nothing to check it against
        if copy.is_header:
            return True
        # ``copy.member or -1`` would call member 0 unresolved, which every
        # cache carries dozens of.
        return copy.member is not None and 0 <= copy.member < shape.member_count

    unresolved = [copy for copy in copies if not resolves(copy)]
    if not unresolved:
        return tuple(copies)

    def source_bytes(copy: PreloadCopy) -> Optional[bytes]:
        shape = shape_of(copy.container)
        if shape is None:
            return None
        if copy.is_header:
            return (shape.head[:shape.data_offset]
                    if shape.data_offset <= len(shape.head) else None)
        if copy.member is None:
            return None
        row = shape.member(copy.member)
        if row is None:
            return None
        offset, stored = row
        if stored <= 0:
            return None
        return source.bytes_at(copy.container, shape.data_offset + offset, stored)

    by_offset: Dict[int, List[PreloadCopy]] = {}
    for copy in copies:
        by_offset.setdefault(copy.offset, []).append(copy)
    out: List[PreloadCopy] = []
    for copy in copies:
        if resolves(copy):
            out.append(copy)
            continue
        matches: List[PreloadCopy] = []
        for other in by_offset.get(copy.offset, ()):
            if other is copy or not resolves(other):
                continue
            found = source_bytes(other)
            if found and blob[copy.offset:copy.offset + len(found)] == found:
                if not any(item.container == other.container and item.kind == other.kind
                           and item.member == other.member for item in matches):
                    matches.append(other)
        if len(matches) == 1:
            settled = matches[0]
            out.append(PreloadCopy(
                cache=copy.cache, container=settled.container, kind=settled.kind,
                member=settled.member, offset=copy.offset,
                declared_container=copy.container, declared_kind=copy.kind,
                declared_member=copy.member))
        else:
            out.append(copy)
    return tuple(out)


def collect(caches: Sequence[str], source: CopySource) -> Dict[str, ContainerPreload]:
    """``container name -> ContainerPreload`` for every cache on this image.

    The one function every lane that writes a container calls, so the coherence
    rule lives in one place: a member edit that changes a container's directory
    has to change the copies of that directory too, and a member that is itself
    copied has to be rewritten in the cache as well or refused.
    """

    found: Dict[str, Dict[str, Any]] = {}
    for cache in caches:
        blob = source.cache_bytes(cache)
        if blob is None:
            continue
        for copy in attribute(parse_cache(blob, cache), blob, source):
            row = found.setdefault(copy.container, {"header": [], "members": {}})
            if copy.is_header:
                row["header"].append(copy)
            else:
                row["members"].setdefault(copy.member, []).append(copy)
    return {
        name: ContainerPreload(
            container=name, header=tuple(row["header"]),
            members={index: tuple(items) for index, items in sorted(row["members"].items())})
        for name, row in sorted(found.items())
    }


def build_cache(payload: Sequence[Tuple[str, int, Optional[int], bytes]],
                *, payload_alignment: int = 16) -> bytes:
    """A ``QL01`` cache built from the format's own rules, for a synthetic disc.

    *payload* is ``(container name, kind, member or None, bytes)`` in the order
    the copies are laid out.  Nothing here is sampled: a caller hands in bytes
    it computed, and the result is a cache that :func:`parse_cache` reads back.
    """

    names: List[str] = []
    for container, _kind, _member, _blob in payload:
        key = container.upper()
        if key not in names:
            names.append(key)
    body = bytearray()
    rows: List[Tuple[int, int, int, int]] = []
    for container, kind, member, blob in payload:
        while len(body) % payload_alignment:
            body.append(0)
        rows.append((int(kind), names.index(container.upper()),
                     0 if member is None else int(member), len(body)))
        body += blob
    files_size = QL01_COUNT_OFFSET + 4 + QL01_NAME_STRIDE * len(names)
    details_size = QL01_COUNT_OFFSET + 4 + QL01_ENTRY_STRIDE * len(rows)
    head_size = QL01_CHUNK_HEADER + 4
    payload_offset = head_size + files_size + details_size + QL01_CHUNK_HEADER

    out = bytearray()
    out += QL01_MAGIC + struct.pack("<II", head_size, payload_offset)
    out += QL01_FILS + struct.pack("<I", files_size) + struct.pack("<I", len(names))
    for name in names:
        out += name.encode("latin-1")[:QL01_NAME_STRIDE].ljust(QL01_NAME_STRIDE, b"\x00")
    out += QL01_DTLS + struct.pack("<I", details_size) + struct.pack("<I", len(rows))
    for kind, file_index, member, offset in rows:
        out += bytes((kind, 0, file_index, 0)) + struct.pack("<II", member, offset)
    out += QL01_DATA_TAG + struct.pack("<I", 0)
    assert len(out) == payload_offset, (len(out), payload_offset)
    out += body
    return bytes(out)



__all__ = [
    "ContainerPreload",
    "ContainerShape",
    "CopySource",
    "PRELOAD_KIND_HEADER",
    "PRELOAD_KIND_MEMBER",
    "PreloadCopy",
    "QL01_CHUNK_HEADER",
    "QL01_COUNT_OFFSET",
    "QL01_DATA_TAG",
    "QL01_DTLS",
    "QL01_ENTRY_STRIDE",
    "QL01_FILS",
    "QL01_MAGIC",
    "QL01_MAX_CHUNKS",
    "QL01_MAX_ENTRIES",
    "QL01_MAX_FILES",
    "QL01_NAME_STRIDE",
    "QL01_PAYLOAD_OFFSET",
    "Ql01Error",
    "attribute",
    "build_cache",
    "cache_names",
    "collect",
    "container_shape",
    "parse_cache",
]

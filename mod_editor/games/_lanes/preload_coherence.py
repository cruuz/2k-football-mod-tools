"""Keeping a disc's ``QL01`` preload caches in step with a container it rewrote.

The caches are **part of the writer, not a footnote**.  A ``QL01`` file carries
byte copies of container directories and of individual members
(:mod:`mod_editor.games._formats.ea_ql01`), and the game preloads from the copy
rather than from the container.  Two consequences, and every writer on this
stack has to answer both:

* a member rewrite is free only while the container's first ``data_offset``
  bytes stay put -- and they move the moment a member changes stored size or
  codec, because both live in the ``DIR1``/``COMP`` directory the cache copies.
  Every copy of that directory has to be rewritten, or the game reads the new
  container against the old offsets;
* a member that is itself copied has to be rewritten in the cache too, and the
  copy is a **fixed slot**: if its stored size changed there is nowhere to put
  the new bytes, and that is refused by name rather than written past the end
  of somebody else's copy.

Measured on the two discs this serves [M]: Madden 09's ``UNIFORMS.DAT``
directory is copied three times and none of its members at all, so a member
rewrite there is free while the directory holds; NCAA 09's ``LEAGUE.DAT`` has
two directory copies **and two member copies**, and ``PLYRFACE.DAT`` has two
directory copies and seventy-two member copies, so on that disc the member path
is the ordinary case rather than the exception.

Both halves are here: :func:`patch_caches` rewrites what a build disturbed, and
:func:`check_caches` re-derives from the destination image alone that every copy
still equals what it copies -- so a receipt that forgot a copy fails rather than
being believed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_terf
from mod_editor.games.contract import Refusal

#: What :func:`patch_caches` returns beside the rewritten cache bytes: one row
#: per copy it touched, carrying the copy's own words plus why it moved.
CopyNote = Dict[str, Any]


def patch_caches(discs: Any, image: Any, present: Mapping[str, Any],
                 preload: Mapping[str, Any], caches: Dict[str, bytearray],
                 notes: List[CopyNote], container_name: str,
                 before: bytes, after: bytes, touched: Sequence[int],
                 *, allow_shorter: bool = False) -> None:
    """Rewrite every cached copy of *container_name* that the edit disturbed.

    *caches* accumulates ``cache name -> mutable bytes`` across however many
    containers one build rebuilds, so two containers copied into the same cache
    produce one rewritten cache and not two.  *notes* accumulates the receipt's
    account of what moved and why.

    ``allow_shorter`` admits a cached member whose replacement packs **smaller**
    than what it replaces.  The default is off, and off is the conservative
    reading: a cached copy is a fixed slot and a caller that has not thought
    about it should be refused.  It is on for a lane whose replacement is read
    through the directory copy it also rewrites -- the game takes the member's
    length from the directory, so bytes past the shorter copy are never read
    [A], and the copy is padding or the next copy's bytes, which this never
    touches.  A **larger** copy is refused either way, because those bytes
    would land in something else.

    Raises the game's own ``DiscError`` -- taken from *discs* so the sentence
    reads as that game's -- naming the first thing that does not fit.  Nothing
    is written when it does.
    """

    def require(condition: object, message: str) -> None:
        if not condition:
            raise discs.DiscError(message)

    row = preload.get(container_name.upper()) or preload.get(container_name)
    if row is None or row.empty:
        return
    parsed_before = ea_terf.parse_terf(before, allow_size_mismatch=True)
    parsed_after = ea_terf.parse_terf(after, allow_size_mismatch=True)

    def cache_bytes(name: str) -> bytearray:
        if name not in caches:
            require(name in present,
                    f"{name} carries a copy of {container_name} and is not on this "
                    f"image; the two disagree and nothing was written.")
            caches[name] = bytearray(discs.read_file(image, present[name], limit=None))
        return caches[name]

    directory_moved = (before[:parsed_before.data_offset]
                       != after[:parsed_after.data_offset])
    if directory_moved:
        require(parsed_after.data_offset == parsed_before.data_offset,
                f"the rebuilt {container_name}'s directory is "
                f"{parsed_after.data_offset} bytes and the one the preload caches copy "
                f"is {parsed_before.data_offset}; a cached copy is a fixed slot and "
                f"cannot grow. Nothing was written.")
        for copy in row.header:
            blob = cache_bytes(copy.cache)
            length = copy.length_in(parsed_after)
            end = copy.offset + length
            require(end <= len(blob),
                    f"{copy.cache}'s copy of {container_name}'s directory runs past the "
                    f"end of the cache; nothing was written.")
            blob[copy.offset:end] = after[:length]
            notes.append({**copy.as_dict(), "length": length,
                          "why": "the container's directory moved"})
    for member in touched:
        copies = row.for_member(int(member))
        if not copies:
            continue
        was = parsed_before.members[int(member)].stored_size
        now = parsed_after.members[int(member)].stored_size
        fits = now <= was if allow_shorter else was == now
        require(fits,
                f"{container_name} member {member} is copied into "
                f"{', '.join(sorted({copy.cache for copy in copies}))} and the rewrite "
                f"changed its stored size from {was} to {now}. A cached copy is a fixed "
                f"slot, so this member cannot be rewritten at a "
                + ("larger" if allow_shorter else "different")
                + " size; nothing was written.")
        stored = parsed_after.stored(int(member))
        for copy in copies:
            blob = cache_bytes(copy.cache)
            end = copy.offset + now
            require(end <= len(blob),
                    f"{copy.cache}'s copy of {container_name} member {member} runs past "
                    f"the end of the cache; nothing was written.")
            blob[copy.offset:end] = stored
            notes.append({**copy.as_dict(), "length": now,
                          "why": "the member itself was rewritten"})


def check_caches(discs: Any, image: Any, files: Mapping[str, Any], blob: bytes,
                 container_name: str) -> Tuple[Optional[str], int]:
    """Every cached copy of *container_name* still equals the container.

    Derived from the **destination image alone** -- the caches are re-parsed
    there and compared against the container as it now stands -- so a receipt
    that forgot a copy fails here rather than being believed.

    Returns ``(refusal sentence or None, copies checked)``.  A sentence rather
    than an exception because a lane's ``verify`` turns it into a
    :class:`~mod_editor.games.contract.Verdict` and the wording is the verdict.
    """

    try:
        preload = discs.preload_copies(image)
    except Refusal as exc:
        return str(exc), 0
    row = preload.get(container_name.upper()) or preload.get(container_name)
    if row is None or row.empty:
        return None, 0
    parsed = ea_terf.parse_terf(blob, allow_size_mismatch=True)
    cache_bytes: Dict[str, bytes] = {}
    checked = 0
    for copy in list(row.header) + [item for items in row.members.values()
                                    for item in items]:
        if copy.cache not in cache_bytes:
            if copy.cache not in files:
                return (f"{copy.cache} carries a copy of {container_name} and is not on "
                        f"the new image."), checked
            cache_bytes[copy.cache] = discs.read_file(image, files[copy.cache], limit=None)
        data = cache_bytes[copy.cache]
        length = copy.length_in(parsed)
        wanted = blob[:length] if copy.is_header else parsed.stored(int(copy.member))
        if data[copy.offset:copy.offset + length] != wanted:
            where = "directory" if copy.is_header else f"member {copy.member}"
            return (f"{copy.cache}'s copy of {container_name}'s {where} at byte "
                    f"0x{copy.offset:x} is not what the container now holds. The game "
                    f"preloads from that copy, so the edit would be read against a stale "
                    f"directory."), checked
        checked += 1
    return None, checked


def cached_member_indices(preload: Mapping[str, Any], container_name: str) -> Tuple[int, ...]:
    """Which members of *container_name* a cache carries a copy of, sorted.

    A catalogue quotes this so a user can see, before choosing, which targets
    are the ones whose stored size may not change.
    """

    row = preload.get(container_name.upper()) or preload.get(container_name)
    if row is None:
        return ()
    return tuple(sorted(int(index) for index in row.members))


__all__ = ["CopyNote", "cached_member_indices", "check_caches", "patch_caches"]

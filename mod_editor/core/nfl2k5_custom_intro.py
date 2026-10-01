"""Custom intro video: the boot intro movie replaced by your own. EXPERIMENTAL / UNWITNESSED.

The fourth boot movie, outer 4296 ``intro.mov`` (50,241,536 bytes, pinned), is
replaced through the existing streaming archive writer: the archive table and
every later outer move, and pack F grows or shrinks in place when it is the last
extent on the disc, as on the retail image: the bytes after it (14,336 zero bytes
on retail) move with its end, so the disc shrinks or grows by exactly the change
and a restore gives back the identical image.  (Otherwise the writer's generic
answer applies: shrink in place, relocate to grow.)  Every other outer and named
file is hash-verified on read-back before publication.
The executable and the other three boot movies stay retail.

With the Crib movie cut (b76-f2): after the cut pack F holds 34,611,200 bytes on
retail, less than a short intro frees, so the shrink spills into the packs
before F (``nfl2k5_music_archive.pack_sizes``: F keeps one sector, E gives up
the rest).  When those packs are the disc's last extents (the cut compacts the
disc, so they are on a retail source) they are resized where they are, one
after the other, and a restore grows them back to the retail source's sizes:
the restored disc is the Crib-cut disc byte for byte.

The replacement must pass every retail Sofdec rule for a 640x480 boot movie
(``nfl2k5_sofdec.problems``); with it the game's header stage makes the retail
intro's reads and its 10,171,344-byte allocation.  Make one from any clip with
``tools/nfl2k5_intro_encode.py``.  Revert: ``restore`` writes the pinned retail
intro back from a retail source, or build again from the retail source without
the option.  The game playing the movie is UNWITNESSED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import zlib

from . import nfl2k5_intro_videos as boot
from . import nfl2k5_music_archive as archive
from . import nfl2k5_music_banks as banks
from . import nfl2k5_sofdec as sofdec

OWNER = "nfl2k5_custom_intro"
SCHEMA = "nfl2k5_custom_intro/v1"
OUTER, NAME = 4296, "intro.mov"


def retail_pin():
    """(size, sha256) of the retail intro, from the boot movie pins."""
    return next((size, digest) for index, _, size, digest in boot.MOVIES if index == OUTER)


RETAIL_SIZE, RETAIL_SHA256 = retail_pin()
MAX_MOVIE_BYTES = 256 * 1024 * 1024
BUILD_CAPTION = "Custom intro video"
HELP_TEXT = (
    "Replace the game's intro movie with your own. Make the movie from any clip with "
    "tools/nfl2k5_intro_encode.py; the other startup movies and the executable stay retail. "
    "Works with the Crib movie cut; cannot be combined with Trim intro videos. EXPERIMENTAL / UNWITNESSED."
)
require = archive.require


def read_movie(path):
    """A movie file checked against every retail rule for a 640x480 boot movie."""
    path = Path(path)
    require(path.is_file(), f"custom intro movie not found: {path}")
    size = path.stat().st_size
    require(0 < size <= MAX_MOVIE_BYTES, f"custom intro movie must be 1 byte to {MAX_MOVIE_BYTES // 2**20} MiB")
    data = path.read_bytes()
    found = sofdec.problems(data)
    require(not found, "custom intro movie breaks a retail Sofdec rule (make it with "
            "tools/nfl2k5_intro_encode.py): " + "; ".join(found[:3]))
    return data


def _inspect(disc):
    """(state, current outer size, current outer sha256); state is retail or custom."""
    require(len(disc.archive_entries) > OUTER, "intro movie inventory is incomplete")
    entry = disc.archive_entries[OUTER]
    require(entry.name_id == zlib.crc32(NAME.upper().encode("utf-16le")), "foreign intro movie resource ID")
    require(boot.status(banks._xbe(disc)) == "retail",
            "the boot movie loop is not retail (Trim intro videos?); build from a source without it")
    for index, name, size, digest in boot.MOVIES:
        if index != OUTER:
            other = disc.archive_entries[index]
            require(other.size == size and disc.outer_hash(index) == digest,
                    f"boot movie {name} is not retail; build from the original source")
    digest = disc.outer_hash(OUTER)
    if (entry.size, digest) == retail_pin():
        return "retail", entry.size, digest
    head = disc.read_entry_range(entry, 0, min(entry.size, 64 * sofdec.SECTOR))
    require(entry.size % sofdec.SECTOR == 0 and head[2 * sofdec.SECTOR + 32:2 * sofdec.SECTOR + 44] == b"SofdecStream",
            "foreign intro movie payload")
    return "custom", entry.size, digest


def _table_padding(disc):
    """(virtual offset, bytes) after the outer table.  Retail fills it with 0x9F; the
    shared writer re-pads a rewritten table with zeros, so the source's bytes go back."""
    end = archive.HEADER_SIZE + archive.ENTRY_SIZE * len(disc.archive_entries)
    size = archive.align_up(end) - end
    return end, disc.read(size, disc.pack_extents["0"].byte_offset + end) if size else b""


def _resized_run(disc, geometry):
    """The packs from the first one whose size changes through F (just F without a
    spill), when they are the disc's last extents, back to back in pack order; else
    None.  On retail F is the last extent, and after the Crib cut's compaction E
    and F are the last two."""
    packs = geometry["packs"]
    first = next((i for i, p in enumerate(packs) if p["size"] != disc.packs[i].size), len(packs) - 1)
    run = [disc.pack_extents[p["name"]] for p in packs[first:]]
    if any(a.byte_offset + a.size != b.byte_offset for a, b in zip(run, run[1:])):
        return None
    start = run[0].byte_offset
    if any(e.byte_offset + e.size > start for e in disc.entries.values() if not any(e is r for r in run)):
        return None
    return packs[first:]


def _geometry(disc, size, reference=None):
    try:
        geometry = archive.layout(disc, {OUTER: size}, spill=True, reference=reference)
    except ValueError as exc:
        raise ValueError(f"the archive cannot take this intro ({exc}); build from the original disc") from exc
    run = _resized_run(disc, geometry)
    if run is not None:
        # The resized packs are the disc's last extents: resize them where they
        # are, one after the other, and carry the bytes after F along, instead
        # of relocating a pack to grow.
        at = disc.pack_extents[run[0]["name"]].byte_offset
        for pack in run:
            pack["offset"], pack["sector"] = at, (at - disc.partition) // 2048
            at += pack["size"]
        extent = disc.pack_extents["F"]
        end = extent.byte_offset + extent.size
        geometry["tail"] = dict(source_offset=end, size=disc.image_size - end, offset=at)
        geometry["image_size"] = at + (disc.image_size - end)
    return geometry


def preflight(source, movie_path):
    """Build's early refusal: the movie file and the source's intro state, without hashing the disc."""
    movie = read_movie(movie_path)
    with archive.Disc(Path(source).resolve(), descriptors=()) as disc:
        state, old_size, _ = _inspect(disc)
        geometry = _geometry(disc, len(movie))
    return dict(source_state=state, before_size=old_size, after_size=len(movie),
                output_bytes=geometry["image_size"], movie_sha256=hashlib.sha256(movie).hexdigest())


def _facts(movie):
    """Receipt facts for a movie; the pinned retail intro (a restore) is known by its hash."""
    digest = hashlib.sha256(movie).hexdigest()
    if (len(movie), digest) == retail_pin():
        return dict(bytes=len(movie), sha256=digest, retail=True)
    return sofdec.summary(movie)


def plan(source, movie, *, reference=None):
    """Read-only: what replacing the intro with ``movie`` (bytes) does to ``source``.

    ``reference``: pack sizes a spilled pack grows back to (a restore passes the
    retail source's)."""
    source = Path(source).resolve()
    before = archive.identity(source)
    facts = _facts(movie)
    with archive.Disc(source, descriptors=()) as disc:
        state, old_size, old_digest = _inspect(disc)
        geometry = _geometry(disc, len(movie), reference)
        receipt = dict(schema=SCHEMA, owner=OWNER, experimental=True, runtime_witnessed=False,
                       source_sha256=archive.file_hash(source), source_bytes=disc.image_size,
                       outer=OUTER, name=NAME, source_state=state,
                       before=dict(size=old_size, sha256=old_digest),
                       after=dict(size=len(movie), sha256=facts["sha256"]),
                       movie=facts, archive_delta_bytes=len(movie) - old_size,
                       output_bytes=geometry["image_size"], pack_f_relocated=
                       geometry["packs"][-1]["offset"] != disc.pack_extents["F"].byte_offset,
                       layout=geometry, retail=dict(zip(("size", "sha256"), retail_pin())),
                       scratch_bytes=geometry["image_size"] + 16 * archive.BLOCK,
                       xbe_changed=False, other_boot_movies="retail",
                       already_applied=old_digest == facts["sha256"] and old_size == len(movie))
        resized = {p["name"]: dict(before=disc.packs[i].size, after=p["size"])
                   for i, p in enumerate(geometry["packs"]) if p["delta"]}
        if set(resized) - {"F"}:        # b76-f2: the shrink spilled past pack F (or a restore grew it back)
            receipt["packs_resized"] = resized
        if reference is not None:
            receipt["reference_pack_sizes"] = list(reference)
    require(archive.identity(source) == before, "intro source changed during planning")
    return receipt


def verify(source, output, planned, movie, *, progress=None):
    """Fresh read-back: the new intro, every other outer, every other named file, the size."""
    progress = progress or (lambda *_: None)
    with archive.Disc(source, descriptors=()) as original, archive.Disc(output, descriptors=()) as result:
        state, size, digest = _inspect(result)
        require((size, digest) == (len(movie), hashlib.sha256(movie).hexdigest()), "intro movie read-back differs")
        require(banks._xbe(result) == banks._xbe(original), "executable changed")
        require(len(original.archive_entries) == len(result.archive_entries), "outer count changed")
        retained = []
        for old, new in zip(original.archive_entries, result.archive_entries):
            i = old.table_index
            require(old.name_id == new.name_id, "retained outer ID changed")
            if i != OUTER:
                require(old.size == new.size, "retained outer size changed")
                digest_ = original.outer_hash(i)
                require(digest_ == result.outer_hash(i), f"retained outer {i} changed")
                retained.append((i, digest_))
            progress("verify", i + 1, len(original.archive_entries))
        require(set(original.entries) == set(result.entries), "named file inventory changed")
        for name, old in original.entries.items():
            if old.attributes & 0x10 or name.startswith("vc_53450030/"):
                continue
            new = result.entries[name]
            require(old.size == new.size and
                    archive.digest(lambda n, at: original.read(n, old.byte_offset + at), old.size) ==
                    archive.digest(lambda n, at: result.read(n, new.byte_offset + at), new.size),
                    f"unrelated named file changed: {name}")
        require(result.image_size == planned["output_bytes"], "output length differs from plan")
        for pack in planned["layout"]["packs"]:
            extent = result.pack_extents[pack["name"]]
            require((extent.byte_offset, extent.size) == (pack["offset"], pack["size"]),
                    f"pack {pack['name']} geometry differs from plan")
        require(_table_padding(result) == _table_padding(original), "bytes after the outer table differ")
        tail = planned["layout"].get("tail")
        if tail and tail["size"]:
            require(original.read(tail["size"], tail["source_offset"]) == result.read(tail["size"], tail["offset"]),
                    "bytes after the movie archive differ")
        stage = "retail intro (hash pin)"
        if state == "custom":
            reads, width, height = sofdec.header_stage(
                result.read_entry_range(result.archive_entries[OUTER], 0, 5 * sofdec.SECTOR))
            stage = dict(reads=[list(r) for r in reads], width=width, height=height)
        return dict(state=state, intro_size=size, intro_sha256=digest, outer_count=len(retained),
                    all_retained_outer_hashes_verified=True,
                    retained_inventory_sha256=hashlib.sha256(json.dumps(retained).encode()).hexdigest(),
                    header_stage=stage,
                    output_sha256=archive.file_hash(output), output_bytes=result.image_size)


def rebuild(source, output, movie, *, expected_plan=None, overwrite=False, progress=None, reference=None):
    """Write ``movie`` (bytes, already checked) as the intro into a verified separate copy."""
    progress = progress or (lambda *_: None)
    source, output = Path(source).resolve(), Path(output).absolute()
    planned = plan(source, movie, reference=reference)
    require(expected_plan is None or planned == expected_plan, "stale custom intro plan")
    if planned["source_bytes"] > 1024 ** 3:
        needed = planned["scratch_bytes"] + 1024 ** 3
        free = shutil.disk_usage(output.parent).free
        require(free >= needed, f"Not enough free space for the custom intro: needs {needed / 1024**3:.1f} GiB, "
                                f"{free / 1024**3:.1f} GiB free")

    def build(_directory, staged):
        if planned["already_applied"]:
            return {}
        with archive.Disc(source, descriptors=()) as disc:
            _inspect(disc)
            geometry = _geometry(disc, len(movie), reference)
            require(geometry == planned["layout"], "source geometry changed")
            fd = os.open(staged, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                banks._write_archive(fd, disc, geometry, {OUTER: movie}, {}, progress)
                at, fill = _table_padding(disc)
                if fill:
                    archive.write_virtual(fd, geometry["packs"], at, fill)
                tail = geometry.get("tail")
                if tail and tail["size"]:
                    archive.write_all(fd, disc.read(tail["size"], tail["source_offset"]), tail["offset"])
                os.ftruncate(fd, geometry["image_size"])
                os.fsync(fd)
            finally:
                os.close(fd)
        return dict(outer=OUTER, written_bytes=len(movie))

    built, checked = archive.transactional_copy(
        source, output, source_sha256=planned["source_sha256"], scratch_bytes=planned["scratch_bytes"],
        build=build, verify=lambda staged, _: verify(source, staged, planned, movie, progress=progress),
        overwrite=overwrite, progress=progress)
    return dict(schema=SCHEMA, owner=OWNER, experimental=True, runtime_witnessed=False, plan=planned,
                output=str(output), written=built, verification=checked)


def _retail(retail_source):
    """(pinned retail intro bytes, pack sizes) of a retail source image."""
    with archive.Disc(Path(retail_source).resolve(), descriptors=()) as disc:
        entry = disc.archive_entries[OUTER]
        require((entry.size, disc.outer_hash(OUTER)) == retail_pin(),
                "the retail source's intro movie is not the pinned retail one")
        return disc.read_entry_range(entry, 0, entry.size), tuple(p.size for p in disc.packs)


def retail_intro(retail_source):
    """The pinned retail intro bytes from a retail source image (for an exact revert)."""
    return _retail(retail_source)[0]


def restore(source, output, retail_source, *, overwrite=False, progress=None):
    """Exact revert: the retail intro written back (read from ``retail_source``, hash-pinned),
    and any pack a spill shrank grown back to the retail source's size (b76-f2), so a
    restore after the Crib movie cut gives back the Crib-cut disc byte for byte."""
    movie, reference = _retail(retail_source)
    return rebuild(source, output, movie, reference=reference, overwrite=overwrite, progress=progress)


def image_status(source):
    """retail, custom or foreign (the inspector row)."""
    try:
        with archive.Disc(source, descriptors=()) as disc:
            return _inspect(disc)[0]
    except (ValueError, OSError, IndexError, struct.error):
        return "foreign"


def finish_output(target, movie_path, progress=None):
    """Called only on Build's disposable output, before its atomic publication."""
    movie = read_movie(movie_path)
    target = Path(target).resolve()
    with tempfile.TemporaryDirectory(prefix=".custom-intro-", dir=target.parent) as temp:
        staged = Path(temp).resolve() / "intro.iso"
        receipt = rebuild(target, staged, movie, progress=progress)
        os.replace(staged, target)
    receipt["output"] = str(target)
    receipt["movie_file"] = str(Path(movie_path).resolve())
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info")
    for name in ("status", "check"):
        sub.add_parser(name).add_argument("path", type=Path)
    planning = sub.add_parser("plan")
    planning.add_argument("source", type=Path)
    planning.add_argument("movie", type=Path)
    building = sub.add_parser("rebuild")
    building.add_argument("source", type=Path)
    building.add_argument("output", type=Path)
    building.add_argument("movie", type=Path)
    reverting = sub.add_parser("restore")
    reverting.add_argument("source", type=Path)
    reverting.add_argument("output", type=Path)
    reverting.add_argument("retail_source", type=Path)
    args = parser.parse_args(argv)
    if args.command == "info":
        result = dict(help=HELP_TEXT, experimental=True, runtime_witnessed=False, outer=OUTER,
                      retail_size=RETAIL_SIZE, retail_sha256=RETAIL_SHA256)
    elif args.command == "status":
        result = dict(state=image_status(args.path))
    elif args.command == "check":
        data = args.path.read_bytes()
        result = dict(problems=sofdec.problems(data), **(sofdec.summary(data) if not sofdec.problems(data) else {}))
    elif args.command == "plan":
        result = plan(args.source, read_movie(args.movie))
    elif args.command == "rebuild":
        result = rebuild(args.source, args.output, read_movie(args.movie))
    else:
        result = restore(args.source, args.output, args.retail_source)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

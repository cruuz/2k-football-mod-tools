"""Boot movies only. EXPERIMENTAL / UNWITNESSED.

Bypass the pinned four-movie boot loop before shrinking its resources.
Use the existing streaming archive writer, named-file nodes and transactional
publication. Resource IDs and every retained outer payload survive unchanged.
The Crib reels, tutorials, promotional reel and game presentation remain intact.
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

from . import nfl2k5_music_archive as archive
from . import nfl2k5_music_banks as banks
from . import nfl2k5_rdata_sites as rdata
from . import platform_compat as io
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_depth_chart_storage import image_file_node

OWNER = "nfl2k5_intro_videos"
REQUESTS = ()
SCHEMA = "nfl2k5_intro_videos/v1"
TOMBSTONE = b"BOOT_MOVIES_DISABLED_V1\0".ljust(2048, b"\0")
BUILD_CAPTION = "Trim intro videos"
HELP_TEXT = (
    "Skip the four startup movies and save about 60 MiB on the output disc. "
    "Keeps the legal/Sega screens, Crib reels, tutorials and game presentation. "
    "Does not increase the GAMEDATA memory budget. EXPERIMENTAL / UNWITNESSED."
)
# Skip directly to the existing post-movie clock reset. No new runtime memory,
# no shared movie-player patch, and no fake stream ever reaches the decoder.
SITES = (("skip_boot_movie_loop", 0x74BBB, bytes.fromhex("be30974e00"),
          bytes.fromhex("e923000000")),)
GUARDS = (
    (0x74bb1, 0x3d, '6164102e9bff6a3f7299db5973776b7cb83ef469d8d820214066dfdd78fcc9e7'),
    (0x4e9720, 0x30, 'c9697cb9f0df49bc45c6453e7a8218df0a43d17b272984016474bdd4e9a60893'),
    (0x178150, 0x573, 'f42d8148095a66612407439109556088b84099a2ce26fd8b961a6d4e82d85e09'),
)
MOVIES = (
    (4293, 'espn_videogames.mov', 3973120, '50fa376d1a604193dd1919811d5f250a803996fe1cf2a153c4757ec5b9819611'),
    (4294, 'vc.mov', 5425152, 'ff285e3b8e643a71a332e09f667a363fa42dbd409803bb17b7d7920802cb649c'),
    (4295, 'espn_game_sound.mov', 3256320, '4153fde58457c8dd63f69e817010800fa5934e1ac4c33a1519472e9d47fafc73'),
    (4296, 'intro.mov', 50241536, 'c5c52a954ac0b40738e37decb9c2ebccfb976d601b5db29a2f0659852744d62a'),
)
require = archive.require


def status(payload):
    try:
        state = rdata.status(payload, SITES)
        require(state in ("retail", "applied"), "foreign boot movie loop")
        for section in _sections(payload):
            require(section.stored_digest == section_digest(payload, section), "stale XBE section digest")
        image = XbeImage(payload)
        for va, size, digest in GUARDS:
            raw = bytearray(image.read(va, size))
            for _, hook, before, _ in SITES:
                if va <= hook and hook + len(before) <= va + size:
                    raw[hook-va:hook-va+len(before)] = before
            require(hashlib.sha256(raw).hexdigest() == digest, "foreign boot movie dependency")
        return state
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return "foreign"


def apply(payload):
    require(status(payload) != "foreign", "foreign/mixed Intro movie bytes; refusing")
    result, receipt = rdata.apply(payload, SITES, "Intro movie cut")
    return result, {**receipt, "owner": OWNER, "experimental": True, "runtime_witnessed": False,
                    "movies_disabled": 4, "crib_and_tutorials_preserved": True, "gamedata_append_credit": 0,
                    "code_allocation": 0, "disc_bytes_reclaimed": 0,
                    "note": "Use rebuild for disc shrink; the skip alone frees no disc bytes or GAMEDATA budget."}


def _inspect(disc):
    payload = banks._xbe(disc)
    xbe_state = status(payload)
    require(xbe_state != "foreign", "foreign Intro movie consumer")
    states, rows = set(), []
    for index, name, size, digest in MOVIES:
        require(index < len(disc.archive_entries), "Intro movie inventory is incomplete")
        entry = disc.archive_entries[index]
        require(entry.name_id == zlib.crc32(name.upper().encode("utf-16le")), "foreign Intro movie resource ID")
        actual = disc.outer_hash(index)
        if entry.size == size and actual == digest:
            state = "retail"
        elif entry.size == len(TOMBSTONE) and actual == hashlib.sha256(TOMBSTONE).hexdigest():
            state = "applied"
        else:
            raise ValueError(f"foreign Intro movie payload: {name}")
        states.add(state)
        rows.append(dict(index=index, name=name, before_size=entry.size,
                         after_size=len(TOMBSTONE), before_sha256=actual))
    require(len(states) == 1, "mixed Intro movie resource states")
    state = states.pop()
    require(state != "applied" or xbe_state == "applied", "movies removed while their consumer is enabled")
    return payload, state, rows


def _geometry(disc):
    saving = sum(disc.archive_entries[i].size - len(TOMBSTONE) for i, *_ in MOVIES)
    require(disc.packs[-1].size > saving,
            "Intro trim exceeds the remaining final-pack capacity; choose the original retail source")
    geometry = archive.layout(disc, {i: len(TOMBSTONE) for i, *_ in MOVIES})
    # Directories remain fixed. Compact ordinary files after the last directory
    # while preserving the video partition/header and any earlier fixed files.
    root_sector, root_size = struct.unpack("<II", disc.read(8, disc.partition + 0x10014))
    floor = archive.align_up(max([disc.partition + 0x10800,
                                 disc.partition + root_sector * 2048 + root_size] +
                                [e.byte_offset + e.size for e in disc.entries.values() if e.attributes & 0x10]))
    packs = {p["name"]: p for p in geometry["packs"]}
    at, files = floor, []
    for name, entry in sorted(disc.entries.items(), key=lambda item: item[1].byte_offset):
        if entry.attributes & 0x10:
            continue
        # XDVDFS normalizes file names to lower case; the archive uses A..F.
        pack_name = name.split("/")[-1].upper() if name.startswith("vc_53450030/") else None
        size = packs[pack_name]["size"] if pack_name in packs else entry.size
        node, _, _ = image_file_node(disc.read, disc.partition, disc.image_size, name)
        offset = entry.byte_offset if entry.byte_offset < floor else at
        require(offset % 2048 == 0 and offset >= disc.partition, "invalid compacted file extent")
        sector = (offset - disc.partition) // 2048
        if offset >= floor:
            at = archive.align_up(offset + size)
        item = dict(name=name, node=node, offset=offset, sector=sector, size=size,
                    old_offset=entry.byte_offset, old_size=entry.size)
        files.append(item)
        if pack_name in packs:
            packs[pack_name].update(offset=offset, sector=sector)
    geometry.update(files=files, image_size=at, metadata_end=floor)
    require(at <= disc.image_size, "Intro compaction would grow this source; rebuild from a compact base")
    return geometry


def plan(source):
    source = Path(source).resolve()
    before = archive.identity(source)
    with archive.Disc(source, descriptors=()) as disc:
        payload, state, rows = _inspect(disc)
        geometry = None if state == "applied" else _geometry(disc)
        receipt = dict(schema=SCHEMA, experimental=True, runtime_witnessed=False,
                       source_sha256=archive.file_hash(source), source_bytes=disc.image_size,
                       already_applied=state == "applied", movies=rows, layout=geometry,
                       gross_movie_bytes=sum(row[2] for row in MOVIES),
                       retained_movie_markers=4 * len(TOMBSTONE),
                       archive_bytes_reclaimed=0 if geometry is None else sum(r["before_size"] - r["after_size"] for r in rows),
                       disc_bytes_reclaimed=0 if geometry is None else disc.image_size - geometry["image_size"],
                       placement_gap_bytes_reclaimed=0 if geometry is None else (
                           disc.image_size - geometry["image_size"] - sum(r["before_size"] - r["after_size"] for r in rows)),
                       scratch_bytes=disc.image_size + 16 * archive.BLOCK,
                       crib_and_tutorials_preserved=True, gamedata_append_credit=0,
                       xbe_before_sha256=hashlib.sha256(payload).hexdigest())
    require(archive.identity(source) == before, "Intro source changed during planning")
    return receipt


def verify(source, output, planned, *, progress=None):
    progress = progress or (lambda *_: None)
    with archive.Disc(source, descriptors=()) as original, archive.Disc(output, descriptors=()) as result:
        old_xbe, _, _ = _inspect(original)
        new_xbe, state, _ = _inspect(result)
        require(state == "applied" and new_xbe == apply(old_xbe)[0], "Intro consumer readback differs")
        require(len(original.archive_entries) == len(result.archive_entries), "outer count changed")
        changed = {i for i, *_ in MOVIES}
        retained = []
        for old, new in zip(original.archive_entries, result.archive_entries):
            i = old.table_index
            require(old.name_id == new.name_id, "retained outer ID changed")
            if i not in changed:
                require(old.size == new.size, "retained outer size changed")
                digest = original.outer_hash(i)
                require(digest == result.outer_hash(i), f"retained outer {i} changed")
                retained.append((i, digest))
            progress("verify", i + 1, len(original.archive_entries))
        require(set(original.entries) == set(result.entries), "named file inventory changed")
        for name, old in original.entries.items():
            if old.attributes & 0x10 or name.startswith("vc_53450030/") or name == "default.xbe":
                continue
            new = result.entries[name]
            require(old.size == new.size and
                    archive.digest(lambda n, at: original.read(n, old.byte_offset + at), old.size) ==
                    archive.digest(lambda n, at: result.read(n, new.byte_offset + at), new.size),
                    f"unrelated named file changed: {name}")
        expected_size = planned["source_bytes"] - planned["disc_bytes_reclaimed"]
        require(result.image_size == expected_size, "Intro output length differs from plan")
        # Keep a compact hash of retained entries and explicit presentation/movie receipts.
        return dict(outer_count=len(retained), all_retained_outer_hashes_verified=True,
                    retained_inventory_sha256=hashlib.sha256(json.dumps(retained).encode()).hexdigest(),
                    protected_outer_sha256={str(i): result.outer_hash(i) for i in (21, 346, 4248, *range(4297, 4323))},
                    output_sha256=archive.file_hash(output), output_bytes=result.image_size)


def rebuild(source, output, *, expected_plan=None, overwrite=False, progress=None):
    progress = progress or (lambda *_: None)
    source, output = Path(source).resolve(), Path(output).absolute()
    planned = plan(source)
    require(expected_plan is None or planned == expected_plan, "stale Intro reclaim plan")
    # The staged shrink needs its scratch bytes plus a small margin on the output
    # drive; the transaction also checks its exact budget. (The 100 GiB workstation
    # floor from the development brief is not a product rule.)
    if planned["source_bytes"] > 1024**3:
        needed = planned["scratch_bytes"] + 1024**3
        free = shutil.disk_usage(output.parent).free
        require(free >= needed,
                f"Not enough free space for the Intro rebuild: needs {needed / 1024**3:.1f} GiB, "
                f"{free / 1024**3:.1f} GiB free")

    def build(_directory, staged):
        if planned["already_applied"]:
            return {}
        with archive.Disc(source, descriptors=()) as disc:
            original_xbe, _, _ = _inspect(disc)
            replacement, hook_receipt = apply(original_xbe)
            geometry = _geometry(disc)
            require(geometry == planned["layout"], "source geometry changed")
            fd = os.open(staged, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                # Populate relocated files from the independent source reader.
                # The common archive writer then shrinks resources in these packs.
                for item in geometry["files"]:
                    if item["offset"] != item["old_offset"]:
                        for at in range(0, item["size"], archive.BLOCK):
                            data = disc.read(min(archive.BLOCK, item["size"] - at), item["old_offset"] + at)
                            archive.write_all(fd, data, item["offset"] + at)
                    archive.write_all(fd, struct.pack("<II", item["sector"], item["size"]), item["node"])
                banks._write_archive(fd, disc, geometry, {i: TOMBSTONE for i, *_ in MOVIES}, {}, progress)
                archive.write_named(fd, lambda n, at: io.pread(fd, n, at), disc.partition, "default.xbe",
                                    lambda n, at: replacement[at:at+n], len(replacement))
                os.ftruncate(fd, geometry["image_size"])
                os.fsync(fd)
            finally:
                os.close(fd)
        return hook_receipt

    built, checked = archive.transactional_copy(
        source, output, source_sha256=planned["source_sha256"], scratch_bytes=planned["scratch_bytes"],
        build=build, verify=lambda staged, _: verify(source, staged, planned, progress=progress),
        overwrite=overwrite, progress=progress)
    return dict(schema=SCHEMA, experimental=True, runtime_witnessed=False, plan=planned,
                output=str(output), xbe=built, verification=checked)


def image_status(source):
    try:
        with archive.Disc(source, descriptors=()) as disc:
            _, state, _ = _inspect(disc)
            return state
    except (ValueError, OSError):
        return "foreign"


def finish_output(target, progress=None):
    """Called only on Build's disposable output, before its atomic publication."""
    target = Path(target).resolve()
    with tempfile.TemporaryDirectory(prefix=".intro-trim-", dir=target.parent) as temp:
        staged = Path(temp).resolve() / "trimmed.iso"
        receipt = rebuild(target, staged, progress=progress)
        os.replace(staged, target)
    receipt["output"] = str(target)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info")
    planning = sub.add_parser("plan")
    planning.add_argument("source", type=Path)
    building = sub.add_parser("rebuild")
    building.add_argument("source", type=Path)
    building.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    result = ({"help": HELP_TEXT, "experimental": True, "runtime_witnessed": False} if args.command == "info"
              else plan(args.source) if args.command == "plan" else rebuild(args.source, args.output))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

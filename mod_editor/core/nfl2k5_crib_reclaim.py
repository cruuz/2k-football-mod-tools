"""Crib movies only, retaining the Trophy Room. EXPERIMENTAL / UNWITNESSED.

Disable the one pinned 23-movie dispatch path before shrinking its resources.
Use the existing streaming archive writer, named-file nodes and transactional
publication. Resource IDs and every retained outer payload survive unchanged.
The shared room, optional games/furniture, trophy caches and VIP remain intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import zlib

from . import nfl2k5_music_archive as archive
from . import nfl2k5_music_banks as banks
from . import nfl2k5_rdata_sites as rdata
from . import platform_compat as io
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_depth_chart_storage import image_file_node

OWNER = "nfl2k5_crib_reclaim"
REQUESTS = ()
SCHEMA = "nfl2k5_crib_reclaim/v1"
TOMBSTONE = b"CRIB_MOVIES_DISABLED_V1\0".ljust(2048, b"\0")
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: The Crib includes 23 movies. "
    "Patch: Disables those movies and rebuilds the archive to save space. "
    "The Trophy Room, awards, saved profiles, room, games and furniture stay."
)
# The native MOV opener is fastcall with two stack arguments (ret 8). Its
# zero return already selects state 6, the screen-pop path, without a MOV
# context destructor. Keep the existing reward/credit and TrophyViewer code.
SITES = (("disable_movie_open", 0x272A94, bytes.fromhex("e857911500"),
          bytes.fromhex("83c40833c0")),)
GUARDS = (
    (2566752, 299, '8cbd9452d51b640b52197ab007cb3fec05a54db9d2b3bab5ef922104f9328d39'),
    (2413632, 29, '0f697fa74abaa4e1d38046f2439f77d41f1138ff99ae5e9b18fa09c8f88dd3fc'),
    (2568304, 32, 'd604f0755e7de9d1c4a06cd2a9dca6da77fbc325f6281253b96abddbda91849c'),
    (2580512, 32, 'b7f0be33223c1cdfa8388e0991c71fe58bd0c2764112a4c9c65528cb168ceb7b'),
    (5330216, 52, 'df49dfaca4c581d0a6a0c89f13fa44ea094ab9bced847db52e2b1bcbc445ca89'),
)
MOVIES = (
    (4298, 'crib_100percent.mov', 8337408, '701ca741f5d00df40b164fc3315eaa5a6b85ac3cce4d46989e819883f3c938fa'),
    (4299, 'crib_berman.mov', 23930880, 'ef222f93a722ba01b89bc2fd603fd703768a23cd21753eb343d8a596c7e2dd0f'),
    (4300, 'crib_celectra.mov', 25511936, '53ff81aded5bcb9e5327d7295a21e8467f4966efec95d5e249de020cceb3ff99'),
    (4301, 'crib_darquette.mov', 16470016, '08a33ffabc85df304067ba13fdb1d0362d4caa03bfd9c4e448b51974ef8e1acf'),
    (4302, 'crib_fflex.mov', 21512192, '41f8e9c2cfb7ce350be501939bd95db0c8e9e04fc70370c25f7f96f5908ff7c9'),
    (4303, 'crib_jkennedy.mov', 22644736, '2958b4c9eb849c2d2e4023a7708e37e4fe61476266a5c4c907004f147477f643'),
    (4304, 'crib_nfl2k.mov', 34668544, '29043050a593abf4e887a89cf1cbc175e8e6aca52b5acf490c1f10e9fc8438f9'),
    (4305, 'crib_nfl2k1.mov', 26591232, '6ca559c74eaabfc1d9f55e773d816c83950b942254e6c19f1a090f16f76ca40d'),
    (4306, 'crib_nfl2k2.mov', 28805120, '916994c7ae0d5b11cf8928f68f80d85b457cc32810247376798f3209cf20e80b'),
    (4307, 'crib_nfl2k3.mov', 47966208, '809f2b321fbeaf40b458a75fe166a054c9d645e01cbada30e7e86d77286b2e0f'),
    (4308, 'crib_nfl2k4.mov', 18558976, 'a3c49fb16ef6ee83684deedab51c7e5c5cbd5981b8426f0926924d98a7d84686'),
    (4309, 'crib_sc1.mov', 13410304, 'e56396d5ae1e781b1045ccd2c6e6d0d00265c8017e43ac7fe09770b06c47d708'),
    (4310, 'crib_sc10.mov', 14424064, '5d2e186b4650844a02a4e3ea4786094506932fff77f3ceb1a6b0ebe11fce3784'),
    (4311, 'crib_sc2.mov', 12095488, '38ca53c17e962f69728eb36758ae475a8e90a2b42a916f3d368a8da2225b4bcd'),
    (4312, 'crib_sc3.mov', 6963200, 'c3c8859ec3ee615048d4a3fea178b7fa441ab09820b9fea6792a6d22a6428598'),
    (4313, 'crib_sc4.mov', 12697600, '9853f0f55f8a609124186674daba31d8ee417c470d9f99516777e795a92ba781'),
    (4314, 'crib_sc5.mov', 6318080, '585acc6542b3e3e8d345d898739aa28440455d23e159d53045758e48f9ac7d3a'),
    (4315, 'crib_sc6.mov', 9363456, '227b3e41c1284e66675d3a3edba7b7512d714401c742549cec622c37f8b9e93b'),
    (4316, 'crib_sc7.mov', 7239680, 'c971777d09f36455fa8bc89c7f632652ec49db6a3bea689a37889f2b2aa8e209'),
    (4317, 'crib_sc8.mov', 13692928, '430b63f3272caca85d124720d1181b2ff90264e68d1da0b5ec9ac21e8b6db9d5'),
    (4318, 'crib_sc9.mov', 13568000, '1fa5f646ca231f9d09422367415b13c502cd602eb05031cf435a1f681783b1fc'),
    (4319, 'crib_steveo.mov', 25849856, '05691391d2399e709a8e452f5e8039520f00b6b5c9449dcf53c540015e7eaf7d'),
    (4320, 'crib_towens.mov', 6549504, 'c0a3505c0ed4e68d02c804665b752cc2d85ff61c527cc727ecb052ef8193ccb6'),
)
require = archive.require


def status(payload):
    try:
        state = rdata.status(payload, SITES)
        require(state in ("retail", "applied"), "foreign Crib movie dispatch")
        for section in _sections(payload):
            require(section.stored_digest == section_digest(payload, section), "stale XBE section digest")
        image = XbeImage(payload)
        for va, size, digest in GUARDS:
            raw = bytearray(image.read(va, size))
            for _, hook, before, _ in SITES:
                if va <= hook and hook + len(before) <= va + size:
                    raw[hook-va:hook-va+len(before)] = before
            require(hashlib.sha256(raw).hexdigest() == digest, "foreign Crib dependency")
        return state
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return "foreign"


def apply(payload):
    require(status(payload) != "foreign", "foreign/mixed Crib movie bytes; refusing")
    result, receipt = rdata.apply(payload, SITES, "Crib movie cut")
    return result, {**receipt, "owner": OWNER, "experimental": True, "runtime_witnessed": False,
                    "movies_disabled": 23, "trophy_room_preserved": True, "profile_edits": 0,
                    "code_allocation": 0, "disc_bytes_reclaimed": 0,
                    "note": "Use rebuild for archive and disc shrink; an XBE hook alone frees no disc bytes."}


def _inspect(disc):
    payload = banks._xbe(disc)
    xbe_state = status(payload)
    require(xbe_state != "foreign", "foreign Crib movie consumer")
    states, rows = set(), []
    for index, name, size, digest in MOVIES:
        require(index < len(disc.archive_entries), "Crib movie inventory is incomplete")
        entry = disc.archive_entries[index]
        require(entry.name_id == zlib.crc32(name.upper().encode("utf-16le")), "foreign Crib movie resource ID")
        actual = disc.outer_hash(index)
        if entry.size == size and actual == digest:
            state = "retail"
        elif entry.size == len(TOMBSTONE) and actual == hashlib.sha256(TOMBSTONE).hexdigest():
            state = "applied"
        else:
            raise ValueError(f"foreign Crib movie payload: {name}")
        states.add(state)
        rows.append(dict(index=index, name=name, before_size=entry.size,
                         after_size=len(TOMBSTONE), before_sha256=actual))
    require(len(states) == 1, "mixed Crib movie resource states")
    state = states.pop()
    require(state != "applied" or xbe_state == "applied", "movies removed while their consumer is enabled")
    return payload, state, rows


def _geometry(disc):
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
    require(at <= disc.image_size, "Crib compaction would grow this source; rebuild from a compact base")
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
                       retained_movie_markers=23 * len(TOMBSTONE),
                       archive_bytes_reclaimed=0 if geometry is None else sum(r["before_size"] - r["after_size"] for r in rows),
                       disc_bytes_reclaimed=0 if geometry is None else disc.image_size - geometry["image_size"],
                       scratch_bytes=disc.image_size + 16 * archive.BLOCK,
                       trophy_room_preserved=True, profile_edits=0,
                       xbe_before_sha256=hashlib.sha256(payload).hexdigest())
    require(archive.identity(source) == before, "Crib source changed during planning")
    return receipt


def verify(source, output, planned, *, progress=None):
    progress = progress or (lambda *_: None)
    with archive.Disc(source, descriptors=()) as original, archive.Disc(output, descriptors=()) as result:
        old_xbe, _, _ = _inspect(original)
        new_xbe, state, _ = _inspect(result)
        require(state == "applied" and new_xbe == apply(old_xbe)[0], "Crib consumer readback differs")
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
        require(result.image_size == expected_size, "Crib output length differs from plan")
        # Keep a compact hash of all individual retained receipts, plus explicit trophy entries.
        return dict(outer_count=len(retained), all_retained_outer_hashes_verified=True,
                    retained_inventory_sha256=hashlib.sha256(json.dumps(retained).encode()).hexdigest(),
                    trophy_outer_sha256={str(i): result.outer_hash(i) for i in (4248, 4272, 4291)},
                    output_sha256=archive.file_hash(output), output_bytes=result.image_size)


def rebuild(source, output, *, expected_plan=None, overwrite=False, progress=None):
    progress = progress or (lambda *_: None)
    source, output = Path(source).resolve(), Path(output).absolute()
    planned = plan(source)
    require(expected_plan is None or planned == expected_plan, "stale Crib reclaim plan")
    # The staged shrink needs its scratch bytes plus a small margin on the output
    # drive; the transaction also checks its exact budget. (The 100 GiB workstation
    # floor from the development brief is not a product rule.)
    if planned["source_bytes"] > 1024**3:
        needed = planned["scratch_bytes"] + 1024**3
        free = shutil.disk_usage(output.parent).free
        require(free >= needed,
                f"Not enough free space for the Crib rebuild: needs {needed / 1024**3:.1f} GiB, "
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

#!/usr/bin/env python3
"""Read-only native probes for the unresolved d2b pre-snap wait.

Execute actual Xbox instructions in bounded Unicorn RAM. Supplied endurance,
injury and actor objects are synthetic; this does not run frame/animation/I/O.
No leaf routines are substituted. No disc or executable bytes are written.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_roster_records as rr
from tests.nfl2k5_supersim_draft_fixture import Machine
from tools.nfl2k5_playbook_position_recode import BOOK_ENTRIES, OuterImage
from tools.nfl_motion_inventory import parse_common

V04_XBE = "5a9dc534b50c7f13b5124bfff9e39c99f96f62be4cc1de33309895c330c75f29"
V04_ROSTER = "a10aadd7f7968ef5334eb029109b199db954c7cfdd305229d24ea36beb711bb0"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def lineup(args, payload, books):
    doc = rr.load_image(args.disc, scheme="one_pool")
    body = doc.to_body()
    if digest(body) != V04_ROSTER:
        raise ValueError("v0.4 roster evidence pin differs")
    m = Machine(payload, trace_writes=False)
    base = m.ARENA + 0x300
    m.uc.mem_write(base, body)
    m.fixup_roster(base + 0x40)
    m.put(m.root + 0x18, 32)
    for address, value in ((0xE60140, 1), (0xAC26B8, 0), (0xE5FF80, 4), (0xE602B4, 4)):
        m.put(address, value)
    for address in (0xE60194, 0xE601A4, 0xE60198, 0xE601A8):
        m.put(address, 75)
    records = list(doc.players)
    for n, player in enumerate(records):
        pointer, runtime = base + player.offset, m.ARENA + 0xA0000 + n * 48
        m.put(pointer + 0x30, runtime)
        m.put(runtime, runtime + 32)
        m.put(runtime + 4, runtime + 32)
        m.put(runtime + 0xC, 0x2140000)
    side, assigned = 0xE5FC20, m.ARENA + 0x190000
    kinds, bookva = assigned + 0x200, m.ARENA + 0x1C0000
    actors = [assigned + 0x1000 + i * 0x80 for i in range(11)]
    m.put(0x2140008, 1)
    m.put(0xE5FE64, assigned + 0x500)
    m.put(side + 4, actors[0])
    m.put(0xE5FE80, bookva)
    for i, actor in enumerate(actors):
        m.put(actor + 0x34, actors[i + 1] if i < 10 else 0)
        m.put(actor + 0x38, side)
        m.put(actor + 0x24, actor + 0x70)
        m.put(actor + 0x3C, base + records[i].offset)
    aliases = {"ARZ": "ARI", "SD": "LAC", "OAK": "LV", "STL": "LAR"}
    by_name = {t.abbreviation: t for t in doc.teams[:32]}
    rows = []
    for path, raw, book in books:
        livebody = bytearray(raw[32:])
        for field in (0x30, 0x44, 0x48, 0x60, 0x64, 0x68):
            relative = struct.unpack_from("<i", livebody, field)[0]
            struct.pack_into("<I", livebody, field, bookva + field - 1 + relative)
        m.uc.mem_write(bookva, bytes(livebody))
        team = by_name.get(aliases.get(book.book_name, book.book_name), doc.teams[1])
        for category in book.categories:
            catbuf = bookva + insp.CATEGORY_BASE + category.index * insp.CATEGORY_SIZE
            category_data = raw[32 + insp.CATEGORY_BASE + category.index * insp.CATEGORY_SIZE:]
            for profile in args.profiles:
                # Rebuild the real list rather than fabricating invalid list sentinels.
                for player in records:
                    m.put(base + player.offset + 0x24, struct.unpack_from("<I", body, player.offset + 0x24)[0])
                for address in (0xE6019C, 0xE601AC):
                    m.put(address, 1 if "unavailable" in profile else 7)
                if "unavailable" in profile:
                    backs = [p for p in doc.team_players(team.index) if p.record.position_code == 7]
                    if profile == "lead_unavailable":
                        backs = [min(backs, key=lambda p: p.record.values["depth_rank"])]
                    for player in backs:
                        address = base + player.offset + 0x24
                        m.put(address, (m.get(address) & ~0x70000000) | 0x60000000)
                m.call(0xE80D0, ecx=m.team_base + team.index * 500, edx=0xB336F4,
                       args=(0, 1), budget=10000000)
                m.put(0xB336F8, 0)
                for n, _ in enumerate(records):
                    m.f32(m.ARENA + 0xA0000 + n * 48 + 36, .1 if profile == "fatigued" else .8)
                m.uc.mem_write(assigned, bytes(44))
                m.call(0x18A5D0, ecx=side, edx=catbuf,
                       args=(0, assigned, kinds, 1, 1, 0), budget=10000000)
                picks = [m.get(assigned + i * 4) for i in range(11)]
                assert all(picks) and len(set(picks)) == 11, (path, category.index, profile, picks)
                for i, actor in enumerate(actors):
                    assert m.get(actor + 0x3C) == picks[i]
                    assert m.uc.mem_read(actor + 0x2C, 1)[0] == category_data[5 + i] & 31
                    assert m.uc.mem_read(actor + 0x2E, 1)[0] == i
                    assert m.get(m.get(picks[i] + 0x30) + 0x10) == actor
                rows.append(dict(file=path.name, book=book.book_name, category=category.index,
                                 profile=profile, players=[doc.by_offset[p - base].index for p in picks]))
        print(path.name, "lineup complete", flush=True)
    return dict(cases=len(rows), rows=rows, roster_sha256=digest(body), native_leaves_substituted=[])


def mirror(args, payload, books):
    m = Machine(payload, trace_writes=False)
    m.put(0xE5FF80, 4)
    m.put(0xE602B4, 4)
    buf, rows, calls, forms = m.ARENA + 0x160000, [], 0, 0
    with OuterImage(args.retail) as archive:
        for path, raw, book in books:
            retail = archive.read_entry(BOOK_ENTRIES[book.book_name])
            for form in book.formations:
                forms += 1
                record = lib.formation_record(raw[32:], form.index)
                m.uc.mem_write(buf, record.to_bytes())
                for mirrored, column in itertools.product((False, True), range(3)):
                    positions = []
                    for slot in range(11):
                        m.call(0x190520, eax=buf + 0x1000, ecx=slot, edx=buf,
                               esi=column, args=(int(mirrored),), budget=5000)
                        positions.append(tuple(struct.unpack("<4f", m.uc.mem_read(buf + 0x1000, 16))))
                        calls += 1
                    duplicates = [(i, j) for i in range(11) for j in range(i) if positions[i] == positions[j]]
                    if duplicates:
                        old = lib.formation_record(retail[32:], form.index)
                        rows.append(dict(file=path.name, book=book.book_name, formation=form.index,
                                         name=form.name, mirrored=mirrored, column=column,
                                         duplicates=duplicates, positions=positions,
                                         geometry_identical_to_retail=old.to_bytes()[4:] == record.to_bytes()[4:]))
    return dict(formations=forms, calls=calls, duplicates=rows,
                limitation="Coincident targets do not prove an animation/collision stall.")


def assets(args):
    def walk(archive):
        rows, tails, kinds, chunks = {}, [], Counter(), 0
        for entry in archive.entries:
            at, ordinal = 0, 0
            while at + 32 <= entry.size:
                header = archive.read(entry.virtual_offset + at, 32)
                if header == bytes(32):
                    at += 32
                    continue
                if header[:16] == bytes(16):
                    at += 16
                    continue
                tag, size = header[:4], struct.unpack_from("<I", header, 4)[0]
                if not all(chr(c).isascii() and chr(c).isalnum() for c in tag) or not size or at + 32 + size > entry.size:
                    tails.append(dict(entry=entry.index, parsed_end=at, trailing_bytes=entry.size - at, head=header.hex()))
                    break
                kinds[tag.decode()] += 1
                chunks += 1
                if tag in (b"SMCD", b"MMCD", b"SKEL"):
                    data = archive.read(entry.virtual_offset + at, 32 + size)
                    rows[(entry.index, ordinal)] = dict(entry=entry.index, chunk=ordinal, offset=at,
                        kind=tag.decode(), name=parse_common(data[32:], tag.decode())[0] if tag != b"SKEL" else "",
                        size=len(data), sha256=digest(data))
                at += 32 + size
                ordinal += 1
        return rows, tails, dict(kinds), chunks
    with OuterImage(args.retail) as retail, OuterImage(args.disc) as disc:
        before, btails, bkinds, bchunks = walk(retail)
        after, atails, akinds, achunks = walk(disc)
    changes = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if not old or not new or any(old[field] != new[field] for field in ("kind", "name", "size", "sha256")):
            changes.append(dict(key=key, retail=old, candidate=new))
    return dict(motion_and_skeleton_chunks=len(after), retail_chunks=len(before), changes=changes,
                retail_kind_counts=bkinds, candidate_kind_counts=akinds, retail_parsed_chunks=bchunks,
                candidate_parsed_chunks=achunks, retail_unparsed_tails=btails,
                candidate_unparsed_tails=atails, rows=list(after.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("lineup", "mirror", "assets"))
    parser.add_argument("--disc", type=Path, required=True)
    parser.add_argument("--retail", type=Path)
    parser.add_argument("--xbe", type=Path)
    parser.add_argument("--expected-xbe-sha256", default=V04_XBE)
    parser.add_argument("--books", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profiles", nargs="+", choices=("healthy", "fatigued", "lead_unavailable", "all_hb_unavailable"),
                        default=("healthy", "fatigued"))
    args = parser.parse_args()
    if args.mode in ("mirror", "assets") and not args.retail:
        parser.error("mirror and assets probes require --retail")
    started = time.monotonic()
    if args.mode != "assets":
        if not args.xbe or not args.books:
            parser.error("native probes require --xbe and --books")
        payload = args.xbe.read_bytes()
        if digest(payload) != args.expected_xbe_sha256:
            raise ValueError("executable evidence pin differs")
        books = [(path, path.read_bytes()) for path in sorted(args.books.glob("book-*.bin"))]
        if len(books) != 69:
            raise ValueError("expected the complete 69-book shipped corpus")
        books = [(path, data, insp.parse_playbook_resource(data)) for path, data in books]
        result = lineup(args, payload, books) if args.mode == "lineup" else mirror(args, payload, books)
        result["xbe_sha256"] = digest(payload)
        result["book_sha256"] = {path.name: digest(raw) for path, raw, _ in books}
    else:
        result = assets(args)
    result.update(mode=args.mode, scope=__doc__, wall_seconds=time.monotonic() - started)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key in ("mode", "cases", "calls", "formations", "motion_and_skeleton_chunks", "retail_chunks", "wall_seconds")}))


if __name__ == "__main__":
    main()

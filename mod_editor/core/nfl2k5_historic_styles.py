"""Historic teams keep their retail art: a spare style per franchise (USA Xbox). EXPERIMENTAL / UNWITNESSED.

The 2026 program (u1's kits and Team Select cards, u3's logos and mini helmets) rewrites style 0 of every franchise.
A team's style is its uniform set index: the kit files ``<code><h|a><S>.iff`` and the style-keyed art in the three
streamed aggregates (logos.cdf: logo_, helm_a, helm_h, unif_a, unif_h; mini.cdf: logo_s, mini_h, mini_a;
flipchip.cdf: <code>_flipchip_00_h<S>) are all keyed by (asset code, S). Historic teams draw their team record's
style byte (+0x192) in the Crib and Quick Game; moments draw the SITU record's kit index (+0x58 away, +0x5C home) in
the list, the details screen and the game. Every one of them on style 0 would show 2026 art.

This option gives each affected franchise a spare style S* that holds the RETAIL style-0 art on every surface and
points the historic and moment teams at it:
- S* is the franchise's first free uniform index (its retail table lists styles 1..n-1 as non-zero year pairs at
  team +0x15A + 4 (S-1); E2A90 treats an index as valid only if its pair is non-zero, and E2F20 steps an invalid
  index down toward 0). The Eagles use all 15 indexes, so their S* overwrites era style 9 (2000, all midnight green),
  which duplicates style 11 (2003) most closely, is no team's default and no moment's kit, and is not Kelly green.
- New kit files ``<code>h<S*>.iff`` and ``<code>a<S*>.iff``: the retail style-0 kit bytes, as new outer entries at
  the end of pack F (one directory slot each).
- New aggregate members for S*: copies of the retail style-0 slots, renamed. Each aggregate's CACR record (logos.iff,
  mini.iff, flipchip.iff, all in pack 0) lists the member count, the slot size and the sorted CRC-32 of the members'
  UTF-16LE names; the game binary-searches the hash (42D50) and streams slot index x size (43980), so a new member
  is inserted at its sorted place in both the record and the aggregate. Screens load only the record plus a fixed
  slot cache, so the growth costs 4 heap bytes per member.
- Historic files of an affected franchise (the retail ones and the 25 more moments' own files) gain the S* pair
  (2004, 2004, read "2004 Uniform"); those whose style byte is 0 now read S*. SITU rows with kit 0 for an affected
  franchise read S*. The main roster is not changed, so the current teams' uniform choices stay as they are.
Nothing here changes the executable. The steps that write the 2026 style-0 art must run before this one; its
copies always come from the retail source disc.
"""
from __future__ import annotations

import hashlib
import os
import re
import struct
import zlib
from pathlib import Path

OWNER = "nfl2k5_historic_styles"
LABEL = "Historic teams keep their retail uniforms and logos"
MAX_STYLE = 14                   # uniform indexes 1..14 have year pairs; the style byte +0x192 follows the table
TABLE = 0x15A                    # team record: 14 (first, last) u16 pairs for styles 1..14
STYLE = 0x192                    # team record: the team's default style
SPARE_YEARS = (2004, 2004)       # E3530 labels a pair with first == last as "%d Uniform": "2004 Uniform"
EAGLES, EAGLES_SPARE = "21", 9   # all 15 Eagles styles are used; 9 duplicates 11 most closely (m1 census)
SITU_OUTER_ID = 0x3F407CF4
ROSTER_OUTER_ID = 0x4A37581D     # the main ROST (outer 5)

# name id (CRC-32 of the upper-case UTF-16LE file name) of each record and aggregate, and the members per style
AGGREGATES = (
    dict(name="logos", record=0x89ACDBBE, cdf=0x823E3053,
         members=("logo_{c}_{s}", "helm_a{c}_{s}", "helm_h{c}_{s}", "unif_a{c}_{s}", "unif_h{c}_{s}")),
    dict(name="mini", record=0x436A7B61, cdf=0x48F8908C, members=("logo_s{c}_{s}", "mini_h{c}_{s}", "mini_a{c}_{s}")),
    dict(name="flipchip", record=0xFE99F1DC, cdf=0xF50B1A31, members=("{c}_flipchip_00_h{s}",)),
)
RECORD_COUNT = 0x60              # record file offsets: count, slot size, then the sorted hashes
RECORD_HASHES = 0x68


class HistoricStylesError(ValueError):
    """A foreign disc, an unexpected layout or a failed read-back."""


def require(condition, message):
    if not condition:
        raise HistoricStylesError(message)


def name_id(name):
    return zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF


def member_hash(name):
    """The CACR hash of an aggregate member: CRC-32 of its UTF-16LE name as written (PROVED OFFLINE, 2,855 slots)."""
    return zlib.crc32(name.encode("utf-16le")) & 0xFFFFFFFF


def sha(data):
    return hashlib.sha256(data).hexdigest()


def u16(data, at):
    return struct.unpack_from("<H", data, at)[0]


def rel(data, at):
    return at + struct.unpack_from("<i", data, at)[0] - 1


def utf16(data, at, end=None):
    end = len(data) if end is None else end
    stop = at
    while stop + 1 < end and data[stop:stop + 2] != b"\0\0":
        stop += 2
    return bytes(data[at:stop]).decode("utf-16le")


# ------------------------------------------------------------------------------------------------ the census

def team_records(rost):
    """[(team record body offset, asset code)] of a ROST resource (the main roster or a one-team historic file)."""
    body = rost[32:]
    count = struct.unpack_from("<I", body, 0x40 + 0x18)[0]
    table = rel(body, 0x40 + 0x1C)
    out = []
    for i in range(min(count, 64)):
        at = table + i * 0x1F4
        out.append((at, utf16(body, rel(body, at + 0x10C))))
    return out


def franchise_styles(main_rost):
    """{asset code: number of styles} for the 32 NFL teams of the main roster: 1 + the non-zero pairs."""
    body = main_rost[32:]
    out = {}
    for at, code in team_records(main_rost)[:32]:
        pairs = [struct.unpack_from("<HH", body, at + TABLE + 4 * k) for k in range(MAX_STYLE)]
        used = [k + 1 for k, (a, b) in enumerate(pairs) if a or b]
        require(used == list(range(1, len(used) + 1)), f"franchise {code}: uniform table has a gap")
        out[code] = len(used) + 1
    return out


def spare_style(code, styles, taken=None):
    """The franchise's spare style: its first index past its uniform table with no art of its own (``taken``: the
    indexes that already have a kit file or an aggregate member; the Jets carry art for an unlisted style 7). The
    Eagles have no free index: their spare is the redundant era 9."""
    if code == EAGLES:
        require(styles[code] == MAX_STYLE + 1, "the Eagles' uniform table changed")
        return EAGLES_SPARE
    for index in range(styles[code], MAX_STYLE + 1):
        if not taken or index not in taken.get(code, ()):
            return index
    raise HistoricStylesError(f"franchise {code} has no free uniform index")


def taken_styles(source, styles):
    """{asset code: indexes past the uniform table that already have a kit file or an aggregate member}."""
    hashes = {}
    for aggregate in AGGREGATES:
        _count, _slot, found = parse_record(source.get(identity=aggregate["record"]))
        hashes[aggregate["name"]] = set(found)
    out = {}
    for code, count in styles.items():
        for index in range(count, MAX_STYLE + 1):
            kit = any(source.has(f"{code}{side}{index}.iff") for side in "ha")
            art = any(member_hash(p.format(c=code, s=index)) in hashes[a["name"]]
                      for a in AGGREGATES for p in a["members"])
            if kit or art:
                out.setdefault(code, set()).add(index)
    return out


def historic_style(raw):
    """(asset code, style byte) of a one-team historic ROST file."""
    (at, code), = team_records(raw)[:1]
    return code, raw[32 + at + STYLE]


def census(historic_files, situ_rows):
    """{asset code: [reasons]} for every franchise with a historic file or a moment side on style 0.

    historic_files: {file name: raw}; situ_rows: [(row, side, asset code, kit index)].
    """
    out = {}
    for name, raw in sorted(historic_files.items()):
        code, style = historic_style(raw)
        if style == 0:
            out.setdefault(code, []).append(f"{name} style 0")
    for row, side, code, kit in situ_rows:
        if kit == 0:
            out.setdefault(code, []).append(f"row {row + 1} {side} kit 0")
    return out


# ------------------------------------------------------------------------------------------------ the aggregates

def parse_record(record):
    require(record[:4] == b"CACR" and struct.unpack_from("<I", record, 4)[0] == len(record) - 32,
            "foreign CACR record")
    count, slot = struct.unpack_from("<II", record, RECORD_COUNT)
    require(0 < count <= 8192 and 0 < slot <= 1 << 20 and RECORD_HASHES + 4 * count <= len(record),
            "foreign CACR counts")
    hashes = list(struct.unpack_from(f"<{count}I", record, RECORD_HASHES))
    require(hashes == sorted(hashes) and len(set(hashes)) == count, "CACR hashes are not sorted and unique")
    return count, slot, hashes


def build_record(record, hashes):
    """The record with a new sorted hash list; the body stays 16-byte aligned, as retail pads it."""
    body_end = RECORD_HASHES + 4 * len(hashes)
    size = 32 + ((body_end - 32 + 15) // 16) * 16
    out = bytearray(record[:RECORD_COUNT].ljust(size, b"\0"))
    struct.pack_into("<I", out, 4, size - 32)
    struct.pack_into("<II", out, RECORD_COUNT, len(hashes), struct.unpack_from("<I", record, RECORD_COUNT + 4)[0])
    struct.pack_into(f"<{len(hashes)}I", out, RECORD_HASHES, *hashes)
    return bytes(out)


def slot_name(slot):
    """The member name inside a slot: the TXTR object's UTF-16LE name (body +0x10 relative field)."""
    body = slot[32:32 + 0x80]
    require(slot[:4] == b"TXTR" and body[0x0C:0x10] == b"TXTR", "foreign aggregate slot")
    name_at = struct.unpack_from("<I", body, 0x10)[0] + 0x0F
    desc_at = struct.unpack_from("<I", body, 0x14)[0] + 0x13
    require(0x18 <= name_at < desc_at <= 0x80 - 0x1C, "foreign slot header")
    return utf16(body, name_at, desc_at)


def rename_slot(slot, name):
    """A copy of the slot under another member name; the texture descriptor moves on to stay 4-byte aligned when
    the name grows (retail slots keep it aligned, with zeros up to the 128-byte system buffer's end)."""
    body = bytearray(slot[32:32 + 0x80])
    require(slot[:4] == b"TXTR" and struct.unpack_from("<I", slot, 8)[0] == 0x80, "foreign aggregate slot")
    name_at = struct.unpack_from("<I", body, 0x10)[0] + 0x0F
    desc_at = struct.unpack_from("<I", body, 0x14)[0] + 0x13
    descriptor = bytes(body[desc_at:])
    require(not any(descriptor[0x1C:]), "slot descriptor tail is not zero")
    text = name.encode("utf-16le") + b"\0\0"
    new_desc = max(desc_at, (name_at + len(text) + 3) // 4 * 4)
    require(new_desc + 0x1C <= 0x80, "the new name does not fit the slot's system buffer")
    body[name_at:] = bytes(0x80 - name_at)
    body[name_at:name_at + len(text)] = text
    body[new_desc:new_desc + 0x1C] = descriptor[:0x1C]
    struct.pack_into("<I", body, 0x14, new_desc - 0x13)
    out = bytes(slot[:32]) + bytes(body) + bytes(slot[32 + 0x80:])
    require(slot_name(out) == name, "renamed slot read-back differs")
    return out


def grow_aggregate(record, cdf, additions):
    """(new record, new aggregate): additions {name: slot bytes} inserted at their sorted hash positions."""
    count, slot, hashes = parse_record(record)
    require(len(cdf) == count * slot, "aggregate size differs from its record")
    new = {member_hash(n): s for n, s in additions.items()}
    require(not set(new) & set(hashes) and len(new) == len(additions), "an added member already exists")
    for s in new.values():
        require(len(s) == slot, "added slot has the wrong size")
    merged = sorted(set(hashes) | set(new))
    position = {h: i for i, h in enumerate(hashes)}
    pieces = [new[h] if h in new else cdf[position[h] * slot:(position[h] + 1) * slot] for h in merged]
    return build_record(record, merged), b"".join(pieces)


def overwrite_members(record, cdf, replacements):
    """(record, aggregate) with existing members' slots replaced in place (the Eagles' spare)."""
    count, slot, hashes = parse_record(record)
    out = bytearray(cdf)
    for name, data in replacements.items():
        h = member_hash(name)
        require(h in hashes and len(data) == slot, f"member {name} is not in the aggregate")
        i = hashes.index(h)
        out[i * slot:(i + 1) * slot] = data
    return record, bytes(out)


def member_slot(record, cdf, name):
    count, slot, hashes = parse_record(record)
    h = member_hash(name)
    require(h in hashes, f"member {name} is missing")
    i = hashes.index(h)
    data = cdf[i * slot:(i + 1) * slot]
    require(slot_name(data) == name, f"member {name}: slot name differs from its hash")
    return data


# ------------------------------------------------------------------------------------------------ team files

def with_spare(raw, spare):
    """A historic ROST file whose spare style is valid (a free pair gets SPARE_YEARS; the Eagles' era pair 9 stays)
    and whose style byte, if 0, is the spare."""
    out = bytearray(raw)
    (at, _code), = team_records(raw)[:1]
    t = 32 + at
    pair = t + TABLE + 4 * (spare - 1)
    if struct.unpack_from("<HH", out, pair) == (0, 0):
        struct.pack_into("<HH", out, pair, *SPARE_YEARS)
    if out[t + STYLE] == 0:
        out[t + STYLE] = spare
    return bytes(out)


def undo_spare(raw, code, spare):
    """The inverse of with_spare for a file whose retail style byte was 0 or whose pair was free (status checks)."""
    out = bytearray(raw)
    (at, _code), = team_records(raw)[:1]
    t = 32 + at
    if out[t + STYLE] == spare:
        out[t + STYLE] = 0
    if code != EAGLES:
        struct.pack_into("<HH", out, t + TABLE + 4 * (spare - 1), 0, 0)
    return bytes(out)


# ------------------------------------------------------------------------------------------------ the archive

def rewrite_plan(disc, edits, appended):
    """Lay out edited outers (any size, each inside one pack) and appended files (after the last outer).

    The archive is one contiguous virtual stream split into packs of arbitrary sizes; an outer may cross a pack
    boundary. An edited outer that grows or shrinks moves every later outer by the same aligned amount and changes
    only its own pack's size, so each pack that holds an edit (and pack 0 for the directory, pack F for the appended
    files) is rewritten as a whole new extent; every other pack keeps its bytes and only its virtual start moves.
    """
    from tools.nfl_outer import HEADER_SIZE, align_up
    entries = disc.archive_entries
    packs = disc.packs
    count = len(entries) + len(appended)
    first = max(entries[0].virtual_offset, align_up(HEADER_SIZE + count * 12))
    directory_growth = first - entries[0].virtual_offset
    ids = {e.name_id for e in entries}
    for name, data in appended:
        require(name_id(name) not in ids and len(data) > 0, f"{name} already exists or is empty")
        ids.add(name_id(name))

    def pack_of(offset):
        return next(p for p in packs if p.virtual_start <= offset < p.virtual_start + p.size)

    growth = {p.name: 0 for p in packs}
    growth[packs[0].name] = directory_growth
    for index, data in edits.items():
        e = entries[index]
        p = pack_of(e.virtual_offset)
        require(e.virtual_offset + align_up(e.size) <= p.virtual_start + p.size and len(data) > 0,
                f"outer {index} crosses its pack or is emptied")
        growth[p.name] += align_up(len(data)) - align_up(e.size)
    rows, at = [], first
    for i, e in enumerate(entries):
        size = len(edits[i]) if i in edits else e.size
        rows.append((e.name_id, size, at))
        at = align_up(at + size)
    last_end = rows[-1][2] + rows[-1][1]
    placed = []
    for name, data in appended:
        placed.append((name, at, len(data)))
        rows.append((name_id(name), len(data), at))
        last_end = at + len(data)
        at = align_up(at + len(data))
    require(last_end % 2048 == 0, "the last outer must end on a sector (pad it or add a filler)")
    sizes = [p.size + growth[p.name] for p in packs]
    appended_total = last_end - (sum(p.size for p in packs) + sum(growth.values()))
    sizes[-1] += appended_total
    require(sum(sizes) == last_end and all(size > 0 and size % 2048 == 0 for size in sizes), "pack sizes")
    changed = {"0", packs[-1].name} | {name for name, g in growth.items() if g}
    changed |= {pack_of(entries[i].virtual_offset).name for i in edits}
    return dict(rows=rows, sizes=sizes, growth=growth, placed=placed, changed=sorted(changed),
                edits=sorted(edits), count_before=len(entries), count_after=count,
                directory_growth=directory_growth, first_payload=first)


def _new_table(disc, plan):
    from tools.nfl_outer import HEADER_SIZE
    table = bytearray(disc.header[:HEADER_SIZE])
    struct.pack_into("<I", table, 0, plan["count_after"])
    for ordinal, size in enumerate(plan["sizes"]):
        struct.pack_into("<I", table, 12 + 4 * ordinal, size // 2048)
    for name, size, offset in plan["rows"]:
        table.extend(struct.pack("<III", name, size, offset // 2048))
    return bytes(table)


def pack_stream(disc, pack, plan, edits, appended):
    """Yield the new bytes of one pack, in order, as (bytes) blocks."""
    from tools.nfl_outer import align_up
    block = 1 << 20
    start, size = pack.virtual_start, pack.size
    extent = disc.pack_extents[pack.name]
    cuts = []
    if pack.ordinal == 0:
        first = disc.archive_entries[0].virtual_offset
        table = _new_table(disc, plan)
        cuts.append((0, first, table + bytes(plan["first_payload"] - len(table))))
    for index in plan["edits"]:
        e = disc.archive_entries[index]
        if start <= e.virtual_offset < start + size:
            data = edits[index]
            old_end = e.virtual_offset + align_up(e.size)
            gap = disc.read(old_end - e.virtual_offset - e.size, extent.byte_offset + e.virtual_offset - start + e.size)
            require(len(set(gap)) <= 1, f"outer {index}: foreign alignment padding")
            pad = (gap[:1] or b"\0") * (align_up(len(data)) - len(data))
            cuts.append((e.virtual_offset - start, old_end - start, data + pad))
    cuts.sort()
    cursor = 0
    for lo, hi, data in cuts:
        require(lo >= cursor, "overlapping pack edits")
        for at in range(cursor, lo, block):
            yield disc.read(min(block, lo - at), extent.byte_offset + at)
        for at in range(0, len(data), block):
            yield data[at:at + block]
        cursor = hi
    for at in range(cursor, size, block):
        yield disc.read(min(block, size - at), extent.byte_offset + at)
    if pack is disc.packs[-1]:
        for (name, data), (_n, offset, length) in zip(appended, plan["placed"]):
            yield data
            yield bytes(align_up(length) - length)


def rewrite_archive(path, edits, appended, *, verify=None):
    """Apply rewrite_plan on a private disc copy: each changed pack becomes a new extent at the image end and its
    XDVDFS node is switched; a failed read-back restores the nodes and the image length."""
    from . import nfl2k5_music_archive as archive
    from . import platform_compat as io
    from tools.nfl_outer import align_up
    path = Path(path).resolve()
    with archive.Disc(path, descriptors=()) as disc:
        plan = rewrite_plan(disc, edits, appended)
        old_size = disc.image_size
        base = disc.pack_extents["0"].base_offset
        nodes = {p.name: disc.nodes[p.name] for p in disc.packs if p.name in plan["changed"]}
        old_nodes = {name: struct.pack("<II", sector, size) for name, (_node, sector, size) in nodes.items()}
        identity = archive.identity(path)
        with path.open("r+b") as writer:
            fd = writer.fileno()
            try:
                cursor = align_up(old_size)
                placed = {}
                for pack, new_size in zip(disc.packs, plan["sizes"]):
                    if pack.name not in plan["changed"]:
                        continue
                    require(archive.identity(path) == identity or placed, "image changed after the preflight")
                    start = cursor
                    digest = hashlib.sha256()
                    for data in pack_stream(disc, pack, plan, edits, appended):
                        require(io.pwrite(fd, data, cursor) == len(data), "short pack write")
                        digest.update(data)
                        cursor += len(data)
                    require(cursor - start == new_size, f"pack {pack.name}: {cursor - start} bytes, planned {new_size}")
                    placed[pack.name] = (start, new_size, digest.hexdigest())
                    cursor = align_up(cursor)
                for name, (start, new_size, _digest) in placed.items():
                    io.pwrite(fd, struct.pack("<II", (start - base) // 2048, new_size), nodes[name][0])
                os.fsync(fd)
                if verify is not None:
                    require(verify(path), "the rewritten archive failed its read-back")
            except Exception as exc:
                try:
                    for name, raw in old_nodes.items():
                        io.pwrite(fd, raw, nodes[name][0])
                    os.ftruncate(fd, old_size)
                    os.fsync(fd)
                except Exception as rollback:  # noqa: BLE001
                    raise HistoricStylesError(f"{exc}; rollback failed: {rollback}; discard the copy") from exc
                raise
            growth = os.fstat(fd).st_size - old_size
    return dict(packs={name: dict(offset=start, size=size, sha256=d) for name, (start, size, d) in placed.items()},
                directory_count=[plan["count_before"], plan["count_after"]],
                directory_growth=plan["directory_growth"],
                appended=[dict(file=n, virtual_offset=o, size=l) for n, o, l in plan["placed"]],
                edited_outers=plan["edits"], image_growth=growth)


# ------------------------------------------------------------------------------------------------ the plan

FILLER = "m1_spare_styles_end.bin"     # 2,048 zero bytes after the kit copies: the archive must end on a sector


class Source:
    """Name-keyed reads from a disc image or an extracted game folder (the retail copies' source)."""

    def __init__(self, path):
        from tools.nfl2k5_playbook_position_recode import OuterImage
        self.archive = OuterImage(Path(path))
        self.by_id = {e.name_id: e for e in self.archive.entries}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.archive.__exit__(*exc)

    def has(self, name):
        return name_id(name) in self.by_id

    def get(self, name=None, *, identity=None):
        e = self.by_id.get(name_id(name) if identity is None else identity)
        require(e is not None, f"{name or hex(identity)} is missing from the source")
        return self.archive.read(e.virtual_offset, e.size)


class Target:
    """The same reads from an open archive.Disc (the build copy), plus outer indexes for the rewrite."""

    def __init__(self, disc):
        self.disc = disc
        self.index = {e.name_id: e.table_index for e in disc.archive_entries}

    def has(self, name):
        return name_id(name) in self.index

    def outer(self, name=None, *, identity=None):
        i = self.index.get(name_id(name) if identity is None else identity)
        require(i is not None, f"{name or hex(identity)} is missing from the disc")
        return i

    def get(self, name=None, *, identity=None):
        e = self.disc.archive_entries[self.outer(name, identity=identity)]
        return self.disc.read_entry_range(e, 0, e.size)


def situ_sides(situ):
    """[(row, side, selector, season, kit, kit field offset in the file)] for every SITU row."""
    first_len = 32 + struct.unpack_from("<I", situ, 4)[0]
    body = situ[32:first_len]
    count = struct.unpack_from("<I", body, 64)[0]
    out = []
    for row in range(count):
        at = 0x44 + row * 0x6C
        for side, name_at, year_at, kit_at in (("away", 20, 0x1C, 0x58), ("home", 24, 0x20, 0x5C)):
            selector = utf16(body, rel(body, at + name_at))
            season, kit = struct.unpack_from("<I", body, at + year_at)[0], struct.unpack_from("<I", body, at + kit_at)[0]
            out.append((row, side, selector, season, kit, 32 + at + kit_at))
    return out


def plan_spares(target, source):
    """Everything the option writes, from the build copy (target) and the retail source (copies, styles)."""
    from . import nfl2k5_espn25_more_moments as moments
    main = source.get(identity=ROSTER_OUTER_ID)
    styles = franchise_styles(main)
    descriptors = moments._retail_descriptors(main)
    by_season = {(d["selector"], d["year"]): d for d in descriptors}
    codes_of = {}
    for d in descriptors:
        codes_of.setdefault(d["selector"], d["code"])
    situ = target.get(identity=SITU_OUTER_ID)
    historic, sides = {}, []
    for d in descriptors:
        historic[d["filename"]] = target.get(d["filename"])
    for row, side, selector, season, kit, field in situ_sides(situ):
        if row < 25:
            d = by_season.get((selector, season))
            require(d is not None, f"row {row + 1}: no retail team {selector} {season}")
            code, filename = d["code"], d["filename"]
        else:
            code = codes_of.get(selector)
            filename = f"h-{code}-{season}-{selector}-9.iff" if code else None
            if not filename or not target.has(filename):
                hits = [f"h-{c}-{season}-{selector}-9.iff" for c in styles
                        if target.has(f"h-{c}-{season}-{selector}-9.iff")]
                require(len(hits) == 1, f"row {row + 1}: no file for {selector} {season}")
                filename, code = hits[0], hits[0][2:4]
            historic.setdefault(filename, target.get(filename))
        sides.append((row, side, code, kit, field, filename))
    affected = census(historic, [(r, s, c, k) for r, s, c, k, _f, _n in sides])
    taken = taken_styles(source, styles)
    spares = {code: spare_style(code, styles, taken) for code in affected}
    return dict(styles=styles, taken=taken, affected=affected, spares=spares, sides=sides, historic=historic,
                situ=situ)


def compile_spares(target, source, plan):
    """(edits {outer index: bytes}, appended [(name, bytes)]) for the plan."""
    spares = plan["spares"]
    edits = {}
    for name, raw in plan["historic"].items():
        code, _style = historic_style(raw)
        if code in spares:
            new = with_spare(raw, spares[code])
            if new != raw:
                edits[target.outer(name)] = new
    situ = bytearray(plan["situ"])
    for row, side, code, kit, field, _filename in plan["sides"]:
        if kit == 0 and code in spares:
            struct.pack_into("<I", situ, field, spares[code])
    if bytes(situ) != plan["situ"]:
        edits[target.outer(identity=SITU_OUTER_ID)] = bytes(situ)
    for aggregate in AGGREGATES:
        record = target.get(identity=aggregate["record"])
        cdf = target.get(identity=aggregate["cdf"])
        src_record = source.get(identity=aggregate["record"])
        src_cdf = source.get(identity=aggregate["cdf"])
        added, replaced = {}, {}
        for code, spare in sorted(spares.items()):
            for pattern in aggregate["members"]:
                old = pattern.format(c=code, s=0)
                new = pattern.format(c=code, s=spare)
                slot = rename_slot(member_slot(src_record, src_cdf, old), new)
                (replaced if code == EAGLES else added)[new] = slot
        new_record, new_cdf = record, cdf
        if replaced:
            new_record, new_cdf = overwrite_members(new_record, new_cdf, replaced)
        if added:
            new_record, new_cdf = grow_aggregate(new_record, new_cdf, added)
        if new_record != record:
            edits[target.outer(identity=aggregate["record"])] = new_record
        if new_cdf != cdf:
            edits[target.outer(identity=aggregate["cdf"])] = new_cdf
    appended = []
    for code, spare in sorted(spares.items()):
        for side in "ha":
            kit = source.get(f"{code}{side}0.iff")
            if code == EAGLES:
                edits[target.outer(f"{code}{side}{spare}.iff")] = kit
            else:
                appended.append((f"{code}{side}{spare}.iff", kit))
    if appended and len(appended[-1][1]) % 2048:
        appended.append((FILLER, bytes(2048)))
    return edits, appended


# ------------------------------------------------------------------------------------------------ the disc

def _expected(target, source, plan):
    """Every byte the applied state must hold: {member name: slot}, {kit name: bytes}."""
    members, kits = {}, {}
    for aggregate in AGGREGATES:
        src_record = source.get(identity=aggregate["record"])
        src_cdf = source.get(identity=aggregate["cdf"])
        for code, spare in plan["spares"].items():
            for pattern in aggregate["members"]:
                slot = member_slot(src_record, src_cdf, pattern.format(c=code, s=0))
                members[(aggregate["name"], pattern.format(c=code, s=spare))] = rename_slot(
                    slot, pattern.format(c=code, s=spare))
    for code, spare in plan["spares"].items():
        for side in "ha":
            kits[f"{code}{side}{spare}.iff"] = source.get(f"{code}{side}0.iff")
    return members, kits


def image_status(path, source):
    """'applied' (every spare in place with retail bytes and no historic or moment team left on style 0), 'retail'
    (style-0 users and none of the spares), else 'foreign'. source: the retail disc image or extracted folder.

    A team on its franchise's spare counts as a style-0 user for the census (the spare of a non-Eagles franchise is a
    new index; the Eagles' 9 is no retail team's or moment's), so the same franchises are checked either way."""
    from . import nfl2k5_music_archive as archive
    try:
        with archive.Disc(Path(path), descriptors=()) as disc, Source(source) as src:
            target = Target(disc)
            plan = plan_spares(target, src)
            styles, taken = plan["styles"], plan["taken"]
            spare_of = {code: spare_style(code, styles, taken) for code in styles}
            users = set()
            for raw in plan["historic"].values():
                code, style = historic_style(raw)
                if code in styles and style in (0, spare_of[code]):
                    users.add(code)
            for _row, _side, code, kit, _field, _filename in plan["sides"]:
                if code in styles and kit in (0, spare_of[code]):
                    users.add(code)
            if not users:
                return "retail"
            spares = {code: spare_of[code] for code in users}
            members, kits = _expected(target, src, dict(plan, spares=spares))
            records = {a["name"]: (target.get(identity=a["record"]), target.get(identity=a["cdf"])) for a in AGGREGATES}
            found = []                 # (the Eagles' own era slot, True/False when present, None when absent)
            for (aggregate, member), slot in members.items():
                record, cdf = records[aggregate]
                _count, _slot, hashes = parse_record(record)
                result = (member_slot(record, cdf, member) == slot) if member_hash(member) in hashes else None
                found.append((member.startswith(("logo_21_", "helm_a21_", "helm_h21_", "unif_a21_", "unif_h21_",
                                                 "logo_s21_", "mini_h21_", "mini_a21_", "21_flipchip")), result))
            for kit, data in kits.items():
                found.append((kit.startswith("21"), (target.get(kit) == data) if target.has(kit) else None))
            if not plan["affected"] and all(result is True for _e, result in found):
                for raw in plan["historic"].values():
                    code, _style = historic_style(raw)
                    if code in spares and with_spare(raw, spares[code]) != raw:
                        return "foreign"
                return "applied"
            # retail: style-0 users remain and no new spare exists (the Eagles' era 9 is retail art of its own;
            # some of its members, the wing logo for one, are the same picture as style 0)
            if plan["affected"] and all(eagles or result is None for eagles, result in found):
                return "retail"
            return "foreign"
    except (ValueError, KeyError, IndexError, struct.error, OSError):
        return "foreign"


def apply_to_image(path, source):
    """Install every spare on a private build copy (after the 2026 style-0 writers); replay is a no-op."""
    from . import nfl2k5_music_archive as archive
    path = Path(path).resolve()
    state = image_status(path, source)
    if state == "applied":
        return dict(status="already_applied", image_growth=0)
    require(state == "retail", f"historic styles: the disc is {state}")
    with archive.Disc(path, descriptors=()) as disc, Source(source) as src:
        target = Target(disc)
        plan = plan_spares(target, src)
        edits, appended = compile_spares(target, src, plan)
    receipt = rewrite_archive(path, edits, appended, verify=lambda p: image_status(p, source) == "applied")
    return dict(status="applied", experimental=True, runtime_witnessed=False,
                spares={code: spare for code, spare in sorted(plan["spares"].items())},
                reasons={code: reasons for code, reasons in sorted(plan["affected"].items())},
                kit_copies=[name for name, _data in appended if name != FILLER], **receipt)

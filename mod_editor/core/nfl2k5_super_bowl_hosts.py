"""Franchise Super Bowl hosts (sb1): the announced future Super Bowls played in their real stadiums with Super Bowl
field art.

How the game picks the venue (PROVED OFFLINE, u6 section 10 and this job): in week 20 FUN_001332b0 takes the
franchise season index and maps it through a jump table (0x133354) to one of six asset codes in ``.data`` (0xE79528
on): index 0 ``s40``, 1 ``s42``, 2 ``s43``, 3 ``s41``, 4 ``s44``, 5 and later ``s45``, then finds the first stadium row
of the main ROST with that code and builds the bundle name ``%s%c%c.iff`` (0x62C82) from it. The team packages take
their Super Bowl variant only for these six codes, so the codes and the executable stay as they are.

The 2026 franchise's first season (index 0) plays Super Bowl LXI at SoFi Stadium in row ``s40`` (nfl2k5_sofi_model).
This step dresses the next three neutral rows as the announced hosts (NFL announcements: LXII 2024-10-15, LXIII
2026-03-30, LXIV 2026-05-19; Wikipedia, checked 2026-10-17):

========  ==========  ============  ===================  ========================================================
index     Super Bowl  date          neutral row (retail)  host (the mod's own built model of the building)
========  ==========  ============  ===================  ========================================================
1         LXII        2028-02-13    s42 "Super Bowl 2006"  Mercedes-Benz Stadium, Atlanta (s01, Mercedes-Benz model)
2         LXIII       2029-02-11    s43 "Super Bowl 2007"  Allegiant Stadium, Las Vegas (s20, Allegiant model)
3         LXIV        2030-02-10    s41 "Super Bowl 2008"  Nissan Stadium, Nashville (s28; the new enclosed stadium
                                                           opens in 2027, so the current building stands in)
========  ==========  ============  ===================  ========================================================

Index 4 (LXV, no host announced) keeps ``s44`` and later seasons ``s45`` with the yearless Super Bowl type.

For each host whose source row already names the real building (its model or 2026 venue rename is installed):

* the neutral row's nine bundles become copies of the host's finished bundles, appended to the archive's last pack
  with the directory rows of the neutral names pointing at them (the retail bundles stay on the disc, unreferenced);
* each copy's field is a Super Bowl field: the current NFL shield at midfield at its real size (the midfield
  material renamed so the native team-texture swap cannot replace it), the event mark on both 25-yard lines
  (nfl2k5_super_bowl_fields: authored generic current-system marks, since none of these logos is revealed, or the
  user's ``super_bowl/<NUMERALS>.png``), the host club's own end zones painted plain turf (the native swap still
  loads the home team's end zones over them, as in every retail Super Bowl, whose neutral fields carry no end-zone
  texture at all) and the sideline playoff strips cleared;
* the neutral ROST row takes the event as its name, the host's display name and location, and the host row's
  capacity, roof and surface words and climate. The asset code and the secondary label stay.

The stadium dressing (walls, boards, banners) is the host building's own as built. EXPERIMENTAL and UNWITNESSED in game.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_super_bowl_hosts"
LABEL = "EXPERIMENTAL / UNWITNESSED"
HOSTS = (
    dict(index=1, event="LXII", slot="s42", source="s01", display="Mercedes-Benz Stadium", date="2028-02-13",
         announced="2024-10-15"),
    dict(index=2, event="LXIII", slot="s43", source="s20", display="Allegiant Stadium", date="2029-02-11",
         announced="2026-03-30"),
    dict(index=3, event="LXIV", slot="s41", source="s28", display="Nissan Stadium", date="2030-02-10",
         announced="2026-05-19"),
)
VARIANTS = tuple(t + w for t in "dan" for w in "drs")
#: the event marks on the 25s at the size of the current system's marks (LVIII and LX measured 14 to 15.6 yards
#: along and about 10 to 11 across)
FLANK = dict(kind="event", from_mid_yd=25, box_yd=[14.0, 10.5])
#: the midfield shield of a modern Super Bowl, about 12 yards across (LVIII and LX field diagrams)
SHIELD_ACROSS_M = 10.6
MIDFIELD = {"center_logo": "era_midlogo"}
WORD_FIELDS = (0x04, 0x18, 0x1C)
CLIMATE = (0x28, 0x7C)
SB_STRING = "Super Bowl {event}"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(bytes(raw)).hexdigest()


def spec(host):
    return dict(row=None, event=host["event"], season=2026 + host["index"], flank=dict(FLANK))


# --- the field ------------------------------------------------------------------------------------------------------

def super_bowl_field(bundle, host, marks):
    """(bundle, receipt): the copy's field made a Super Bowl field (see the module notes)."""
    from . import nfl2k5_espn25_fields as fields
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_modern_venues_2026 as mv
    from . import nfl2k5_super_bowl_fields as sbf
    from . import nfl2k5_super_bowl_walls as walls
    import numpy as np
    chunk, rec, decoded = fields._field_chunk(bundle)
    names = {m["name"] for m in rec["materials"]}
    require("center_logo" in names and "era_midlogo" not in names, f"{host['slot']}: the host field's midfield differs")
    rows, materials = mv.p8_rows(rec), mv.rows_by_material(rec)
    out = bytearray(decoded)
    textures, ranges = [], []
    # midfield: the current shield, at its real size, protected from the native team-texture swap
    shield = sbf.trim(walls.modern_shield())
    r = rows[materials["center_logo"]]
    tex = walls.resample(walls.defringe(shield), int(r["width"]) - 8, int(r["height"]) - 8)
    full = np.zeros((int(r["height"]), int(r["width"]), 4), np.uint8)
    full[4:-4, 4:-4] = tex
    mm.write_p8(out, rec["system_bytes"], r, full, 256)
    textures.append(materials["center_logo"])
    h, w = shield.shape[:2]
    scale = int(r["width"]) / (int(r["width"]) - 8)
    across = SHIELD_ACROSS_M * scale
    along = SHIELD_ACROSS_M * w / h * scale
    ranges += sbf.place_single(out, rec, decoded, "center_logo", along, across, centre=(0.0, 0.0))
    ranges += sbf.rename(out, rec, ["center_logo"], MIDFIELD)
    # the host club's painted end zones become plain turf (the field's own grass colour); the sideline playoff strips
    # are cleared
    turf = (58, 104, 46)
    if "color_premipped" in materials:
        g = mv.read_texture(decoded, rec, rows[materials["color_premipped"]])
        turf = tuple(int(c) for c in np.median(g[..., :3].reshape(-1, 3), axis=0))
    for end in "NS":
        for part in "LMR":
            m = f"endzone_{end}_{part}"
            if m in materials and materials[m] not in textures:
                t = rows[materials[m]]
                plain = np.zeros((int(t["height"]), int(t["width"]), 4), np.uint8)
                plain[..., :3] = turf
                plain[..., 3] = 255
                mm.write_p8(out, rec["system_bytes"], t, plain, 256)
                textures.append(materials[m])
    if "playoff_logo" in materials:
        t = rows[materials["playoff_logo"]]
        mm.write_p8(out, rec["system_bytes"], t, np.zeros((int(t["height"]), int(t["width"]), 4), np.uint8), 256)
        textures.append(materials["playoff_logo"])
    flank_textures, flank_ranges, flanks = sbf.apply_field(out, rec, decoded, None, marks, spec=spec(host))
    textures += [t for t in flank_textures if t not in textures]
    ranges += flank_ranges
    span, detail = fields._seal_field(bundle, chunk, rec, decoded, out, textures, ranges)
    before = mm.scene_span(bundle, chunk)
    after = bundle[:chunk.offset] + span + bundle[chunk.offset + len(before):]
    _c, rec2, back = fields._field_chunk(after)
    require(back == bytes(out), f"{host['slot']}: Super Bowl field read-back differs")
    require("era_midlogo" in {m["name"] for m in rec2["materials"]}, f"{host['slot']}: midfield not protected")
    return after, dict(detail, flanks=flanks, field_before=sha(before), field_after=sha(span))


# --- the ROST rows --------------------------------------------------------------------------------------------------

def _records(body):
    from . import nfl2k5_modern_metlife as mm
    return {fields["asset_code"][1]: (offset, fields) for offset, fields in mm._stadium_records(bytes(body))}


def wanted_strings(host, source_fields):
    return dict(name=SB_STRING.format(event=host["event"]), display_name=host["display"],
                location=source_fields["location"][1], asset_code=host["slot"], secondary_label="")


def ready(body, host):
    """True when the host's source row names the real building (its model or 2026 rename is installed)."""
    records = _records(body)
    if host["source"] not in records:
        return False
    _o, f = records[host["source"]]
    return f["display_name"][1] == host["display"] and f["name"][1] == host["display"]


def rost_hosts(resource, hosts):
    """(ROST resource, receipt) with each host's neutral row renamed and given the host row's words and climate.
    Strings are repacked in the row's own contiguous block (Modern MetLife's method); nothing else changes."""
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_roster_records as rr
    header = rr.RESOURCE_HEADER_SIZE
    require(resource[:4] == b"ROST", "outer 5 is not a ROST resource")
    body = bytearray(resource[header:])
    receipt = []
    for host in hosts:
        records = _records(body)
        offset, fields = records[host["slot"]]
        src_offset, src_fields = records[host["source"]]
        wanted = wanted_strings(host, src_fields)
        texts = {k: v[1] for k, v in fields.items()}
        a, b = CLIMATE
        words = [struct.unpack_from("<I", body, src_offset + f)[0] for f in WORD_FIELDS]
        if (texts == wanted and [struct.unpack_from("<I", body, offset + f)[0] for f in WORD_FIELDS] == words
                and body[offset + a:offset + b] == body[src_offset + a:src_offset + b]):
            receipt.append(dict(slot=host["slot"], state="already_applied"))
            continue
        require(texts["asset_code"] == host["slot"] and texts["secondary_label"] == "",
                f"{host['slot']}: the neutral row is foreign")
        records_all = mm._stadium_records(bytes(body))
        text_spans = [(t, t + 2 * len(txt) + 2) for _o, fs in records_all for t, txt in fs.values()]
        block = mm._string_block(fields)
        require(block is not None, f"{host['slot']}: stadium strings are not one contiguous block")
        start, end = block
        pointer_fields = {offset + field for field, _name in mm.ROST_STRING_FIELDS}
        stray = mm._pointers_into(bytes(body), start, end, pointer_fields, text_spans)
        require(not stray, f"{host['slot']}: other pointers reach the stadium strings")
        payload, at = bytearray(), {}
        for key in ("name", "display_name", "location", "asset_code", "secondary_label"):
            at[key] = start + len(payload)
            payload += wanted[key].encode("utf-16le") + b"\0\0"
        require(len(payload) <= end - start, f"{host['slot']}: the host strings do not fit the row's block")
        body[start:end] = bytes(payload) + bytes(end - start - len(payload))
        for field, name in mm.ROST_STRING_FIELDS:
            struct.pack_into("<i", body, offset + field, at[name] - (offset + field) + 1)
        before = [struct.unpack_from("<I", body, offset + f)[0] for f in WORD_FIELDS]
        for field, value in zip(WORD_FIELDS, words):
            struct.pack_into("<I", body, offset + field, value)
        body[offset + a:offset + b] = body[src_offset + a:src_offset + b]
        check = {k: v[1] for k, v in _records(body)[host["slot"]][1].items()}
        require(check == wanted, f"{host['slot']}: the renamed row reads back differently")
        receipt.append(dict(slot=host["slot"], state="applied", event=host["event"], strings=wanted,
                            words_before=before, words_after=words, block=[start, end], bytes_used=len(payload)))
    return bytes(resource[:header]) + bytes(body), receipt


# --- the archive ----------------------------------------------------------------------------------------------------

def repoint_packs(pack0, pack_f, replacements):
    """(pack 0, pack F, receipt): each named resource's bytes appended to pack F and its directory row pointed at
    them. Every other row, every existing payload and the old bytes of the replaced resources are kept."""
    from . import nfl2k5_anniversary_pack as ap
    from . import nfl2k5_espn25_more_moments as mm
    from . import nfl2k5_music_archive as archive
    rows = ap.entries(pack0)
    sizes = list(struct.unpack_from("<16I", pack0, 12))
    require(sizes[0] * 2048 == len(pack0) and sizes[15] * 2048 == len(pack_f), "pack size mismatch")
    ids = {r[0]: i for i, r in enumerate(rows)}
    require(len(ids) == len(rows), "the archive directory repeats an identity")
    f_start = sum(sizes[:15]) * 2048
    new0, new_f = bytearray(pack0), bytearray(pack_f)
    moved = []
    for name, raw in replacements.items():
        identity = mm.name_id(name)
        require(identity in ids, f"{name} is not in the archive directory")
        i = ids[identity]
        _, size, sector = rows[i]
        at = archive.align_up(len(new_f))
        new_f.extend(bytes(at - len(new_f)))
        new_f.extend(raw)
        new_f.extend(bytes(archive.align_up(len(new_f)) - len(new_f)))
        struct.pack_into("<III", new0, ap.HEADER + 12 * i, identity, len(raw), (f_start + at) // 2048)
        moved.append(dict(name=name, before=dict(size=size, sector=sector), after_size=len(raw),
                          pack_f_offset=at, sha256=sha(raw)))
    struct.pack_into("<I", new0, 12 + 15 * 4, len(new_f) // 2048)
    require(new_f[:len(pack_f)] == pack_f, "existing pack F changed")
    return bytes(new0), bytes(new_f), dict(moved=moved, pack_f_growth=len(new_f) - len(pack_f))


def apply_to_image(path, *, user_art=None, progress=None):
    """Dress the announced hosts' neutral rows on a finished Studio build (after every field and colour pass)."""
    import os
    from pathlib import Path
    from . import nfl2k5_modern_metlife as ml
    from . import nfl2k5_music_archive as archive
    from . import nfl2k5_historic_styles as styles
    from . import nfl2k5_super_bowl_walls as walls
    from . import nfl2k5_super_bowl_fields as sbf
    from . import nfl2k5_roster_records as rr
    from . import platform_compat as io
    say = progress or (lambda *a: None)
    with ml._outer_image()(str(path)) as image:
        e = image.entries[ml.ROST_OUTER_INDEX]
        rost = image.read(e.virtual_offset, e.size)
    body = rost[rr.RESOURCE_HEADER_SIZE:]
    hosts = [h for h in HOSTS if ready(body, h)]
    skipped = [dict(slot=h["slot"], event=h["event"], reason=f"{h['source']} does not name {h['display']}")
               for h in HOSTS if h not in hosts]
    if not hosts:
        return dict(state="skipped", skipped=skipped)
    marks = walls.Marks(None, user_art)
    replacements, fields_receipt = {}, []
    with styles.Source(path) as built:
        for host in hosts:
            for k, variant in enumerate(VARIANTS):
                name = f"{host['slot']}{variant}.iff"
                say(f"Super Bowl {host['event']} at {host['display']}: {name}", k + 1, len(VARIANTS))
                source = built.get(f"{host['source']}{variant}.iff")
                current = built.get(name)
                if current[:64] and _is_copy(current, host):
                    continue
                copy, receipt = super_bowl_field(source, host, marks)
                replacements[name] = copy
                fields_receipt.append(dict(name=name, source=f"{host['source']}{variant}.iff", size=len(copy),
                                           sha256=sha(copy), flanks=receipt["flanks"]))
    after_rost, rost_receipt = rost_hosts(rost, hosts)
    with ml._outer_image()(str(path), writable=True) as image:
        e = image.entries[ml.ROST_OUTER_INDEX]
        require(image.read(e.virtual_offset, e.size) == rost, "the ROST changed while preparing")
        require(len(after_rost) == len(rost), "the host rows changed the ROST size")
        image.write(e.virtual_offset, after_rost)
    pack_receipt = None
    if replacements:
        with archive.Disc(Path(path), descriptors=()) as disc:
            p0, pf = disc.pack_extents["0"], disc.pack_extents["F"]
            raw0, raw_f = disc.read(p0.size, p0.byte_offset), disc.read(pf.size, pf.byte_offset)
            out0, out_f, pack_receipt = repoint_packs(raw0, raw_f, replacements)
            old_size = disc.image_size
            at0 = archive.align_up(old_size)
            at_f = archive.align_up(at0 + len(out0))
            nodes = [(disc.nodes["0"][0], struct.pack("<II", p0.sector, p0.size)),
                     (disc.nodes["F"][0], struct.pack("<II", pf.sector, pf.size))]
            with Path(path).open("r+b") as f:
                fd = f.fileno()
                try:
                    for at, raw in ((at0, out0), (at_f, out_f)):
                        archive.write_all(fd, raw, at)
                        require(io.pread(fd, len(raw), at) == raw, "Super Bowl host pack read-back")
                    archive.write_all(fd, struct.pack("<II", (at0 - disc.partition) // 2048, len(out0)), nodes[0][0])
                    archive.write_all(fd, struct.pack("<II", (at_f - disc.partition) // 2048, len(out_f)), nodes[1][0])
                    os.fsync(fd)
                except BaseException:
                    for at, raw in nodes:
                        archive.write_all(fd, raw, at)
                    os.ftruncate(fd, old_size)
                    os.fsync(fd)
                    raise
        pack_receipt["image_growth"] = at_f + len(out_f) - old_size
    with styles.Source(path) as built:
        for item in fields_receipt:
            require(sha(built.get(item["name"])) == item["sha256"], f"{item['name']}: host copy read-back differs")
    log = [f"Super Bowl {h['event']}: {h['display']} ({h['slot']})" for h in hosts]
    log += [f"Super Bowl {s['event']}: kept the neutral {s['slot']} ({s['reason']})" for s in skipped]
    log += sbf.user_art_lines([f["flanks"] for f in fields_receipt[:1]] if fields_receipt else [])
    return dict(state="applied", label=LABEL, hosts=[h["slot"] for h in hosts], skipped=skipped,
                bundles=fields_receipt, rost=rost_receipt, packs=pack_receipt, log=log)


def _is_copy(bundle, host):
    """True when the neutral bundle is already this host's Super Bowl copy (a replay)."""
    from . import nfl2k5_espn25_fields as fields
    try:
        _c, rec, _d = fields._field_chunk(bundle)
    except ValueError:
        return False
    return "era_midlogo" in {m["name"] for m in rec["materials"]}


def status(path):
    """applied / retail / mixed for the hosts' neutral rows of an image."""
    from . import nfl2k5_modern_metlife as ml
    from . import nfl2k5_roster_records as rr
    with ml._outer_image()(str(path)) as image:
        e = image.entries[ml.ROST_OUTER_INDEX]
        body = image.read(e.virtual_offset, e.size)[rr.RESOURCE_HEADER_SIZE:]
    records = _records(body)
    states = {records[h["slot"]][1]["name"][1] == SB_STRING.format(event=h["event"]) for h in HOSTS}
    return "applied" if states == {True} else "retail" if states == {False} else "mixed"

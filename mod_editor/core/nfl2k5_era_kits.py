"""The five Anniversary era kits as a Studio stage (b77 a5k trades, Noah approved 10/8).

The v0.6 disc built five kits by recombining existing native kit parts into five retail slots and relabelling them:
NE 11 (2017), PHI 14 (2017), NO 6 (2006-2016), BAL 1 (2008-2025) and PIT 4 (2025, the Unc Bowl black away kit).
Until now only the native repair (``tools/b77/a5k_kits.py`` + ``a5k_repair.py``) composed the kit bytes; the Studio
build wrote the labels (roster edits) and the moment selections but left the ten kit packages retail. The Unc Bowl
finish then refused the retail 22A4 after a three-hour build (job i4, 10/16).

This module is a byte-exact port of the a5k compiler (``compile_kit``) and runs it on the build copy, before the
Unc Bowl finish:

* every texture chunk keeps its native format and all mips; donors are copied, never quantised;
* chunks 1..43 (and 49..52 behind them) are repacked inside the kit's own fixed allocation, the last chunk of each
  run absorbing the spare stored space;
* the three far-player atlases whose exact donor union exceeds one palette use the game's truecolor format;
* the Unif colour word comes from the donor (NE: the helmet donor).

All inputs are read before the first write. A kit is composed only when the main roster labels its slot with the
era years (so a plain retail build keeps its throwbacks) and the slot still holds the retail package; a slot the
user's recipe filled keeps its art. With the SOFTDRINK donors the result must equal the pinned v0.6 bytes
(``data/nfl2k5_era_kits_pins.json``); other donors (a user's own recipe) compose the same way without that pin.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_bump_texture_writer as bump
from nfl_txtr import (HEADER, Chunk, TxtrError, decode_chunk, parse_chunks, parse_texture,
                      rebuild_compressed_chunk_fixed_span, swizzle_2d, unswizzle_2d)

ROOT = Path(__file__).resolve().parents[2]
RECIPES = ROOT / "data/nfl2k5_moment_era_kits.json"
PINS = ROOT / "data/nfl2k5_era_kits_pins.json"
RECIPE_SCHEMA = "b77/a5k/native-parts/v1"
PIN_SCHEMA = "nfl2k5_era_kits/v1"
ROSTER_NAME_ID = 0x4A37581D       # the main roster (outer entry 5)
TEAM_TABLE = 0x15A                # team record: 14 (first, last) u16 year pairs for styles 1..14
UNIF_COLOURS = 0x50               # the kit package's Unif record: facemask/faceshield word, then the turtleneck word
RETAIL_PREFIX = "retail_"         # a part read from the retail source disc instead of the build copy
# The small player atlas ("splayer", 256x128) boxes the era atlases take from a donor (tools/nfl2k5_team_2026_art).
SPLAYER = {"pants": (0, 0, 128, 90), "sock_low": (127, 100, 160, 128), "sock": (160, 100, 190, 128)}
WET_NUM, WET_DEN = 93, 100        # w1's mud rule: mud = clean * 0.93
COMPACT_CACHE: dict = {}


def require(ok, message):
    if not ok:
        raise ValueError("Anniversary era kits: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def recipes():
    document = json.loads(RECIPES.read_text(encoding="utf-8"))
    require(document.get("schema") == RECIPE_SCHEMA and len(document["items"]) == 5, "expected exactly five era kits")
    require([(r["id"], r["code"], r["style"]) for r in document["items"]] ==
            [("G1", "16", 11), ("G1b", "21", 14), ("G2", "17", 6), ("G3", "02", 1), ("G4", "22", 4)],
            "recipes differ from the five approved target slots")
    return document["items"]


def pins():
    document = json.loads(PINS.read_text(encoding="utf-8"))
    require(document.get("schema") == PIN_SCHEMA, "unexpected pin schema")
    require(document["recipes_sha256"] == sha(RECIPES.read_bytes()), "era kit recipes changed after the pins")
    return document


def targets(recipe):
    """{side: target selector} of one recipe ("22A4", ...)."""
    return {side: recipe["code"] + side + str(recipe["style"]) for side in "HA"}


def inputs_of(recipe, side):
    """(donor selector, {part key: selector}) read for one side; ``retail_`` parts come from the retail disc."""
    return recipe["kits"][side], dict(recipe.get("parts", {}))


# -- the a5k compiler (tools/b77/a5k_kits.py, byte for byte) --------------------------------------------------------

def _tset_texture(decoded, reference):
    """(name, palette offset) of one TSET texture (u1_audit.tset_texture)."""
    base = 0x18 + reference * 0x24
    name_at = base + 4 + struct.unpack_from("<i", decoded, base + 4)[0] - 1
    desc_at = base + 8 + struct.unpack_from("<i", decoded, base + 8)[0] - 1
    end = name_at
    while decoded[end:end + 2] != b"\0\0":
        end += 2
    _self, _pixel, palette, _fmt, _size, _flags = struct.unpack_from("<6I", decoded, desc_at)
    return decoded[name_at:end].decode("utf-16le"), palette


def _tset_palettes(decoded):
    return dict(_tset_texture(decoded, i) for i in range(struct.unpack_from("<I", decoded, 4)[0]))


def _dark(value):
    return (value * 3 + 2) // 5


def _wet(value):
    return (value * WET_NUM + WET_DEN // 2) // WET_DEN


def _rewrite_mud(span):
    """w1_repair.rewrite_chunk: mud entries equal to darken_60 of the clean palette become wet_93; wet_93 stays."""
    kind, stored, system, video, magic, scratch, r0, r1 = HEADER.unpack_from(span)
    require(kind == b"TSET" and len(span) == HEADER.size + stored, "not a whole TSET span")
    chunk = Chunk(0, 0, "TSET", stored, system, video, magic, scratch, r0, r1)
    decoded, info = decode_chunk(span, chunk)
    require(info is not None, "TSET span is not compressed")
    palettes = _tset_palettes(decoded)
    new, changed = bytearray(decoded), 0
    for name, clean_at in palettes.items():
        if name.endswith("_mud") or name + "_mud" not in palettes:
            continue
        base_c, base_m = 256 + clean_at, 256 + palettes[name + "_mud"]
        for k in range(256):
            c = decoded[base_c + 4 * k:base_c + 4 * k + 4]
            have = decoded[base_m + 4 * k:base_m + 4 * k + 4]
            d60 = bytes((_dark(c[0]), _dark(c[1]), _dark(c[2]), c[3]))
            w93 = bytes((_wet(c[0]), _wet(c[1]), _wet(c[2]), c[3]))
            require(have in (d60, w93), f"{name}_mud entry {k} is neither darken_60 nor wet_93 of the clean palette")
            if have != w93:
                new[base_m + 4 * k:base_m + 4 * k + 4] = w93
                changed += 1
    if changed == 0:
        return span
    rebuilt, _info = rebuild_compressed_chunk_fixed_span(span, bytes(new))
    require(len(rebuilt) == len(span), "rebuilt span size changed")
    require(decode_chunk(rebuilt, chunk)[0] == bytes(new), "rebuilt span does not decode to the wet palette")
    return rebuilt


def _lossless_rebuild(span, decoded):
    try:
        return rebuild_compressed_chunk_fixed_span(span, decoded)
    except TxtrError as exc:
        if "bound" not in str(exc):
            raise
        from nfl_vc_lz_fill import rebuild_fixed_span_filled
        return rebuild_fixed_span_filled(span, decoded, encoder="optimal")


def _wet_template(span):
    """Normalize retail mud palettes to w1's accepted input (darken_60 of the clean palette), then apply w1."""
    chunk = parse_chunks(span)[0]
    decoded, _ = decode_chunk(span, chunk)
    new = bytearray(decoded)
    palettes = _tset_palettes(decoded)
    for name, clean_at in palettes.items():
        if name.endswith("_mud") or name + "_mud" not in palettes:
            continue
        c, at = 256 + clean_at, 256 + palettes[name + "_mud"]
        for k in range(256):
            pixel = decoded[c + 4 * k:c + 4 * k + 4]
            new[at + 4 * k:at + 4 * k + 4] = bytes([_dark(v) for v in pixel[:3]]) + pixel[3:]
    normalized = _lossless_rebuild(span, bytes(new))[0] if bytes(new) != decoded else span
    try:
        return _rewrite_mud(normalized)
    except TxtrError as exc:
        if "bound" not in str(exc):
            raise
        # A temporary larger compressed allocation for w1, then its exact decoded output fitted back losslessly.
        fields = list(HEADER.unpack_from(normalized))
        fields[1] += 8192
        fields[5] += 8192
        wet = _rewrite_mud(HEADER.pack(*fields) + normalized[HEADER.size:] + bytes(8192))
        decoded_wet, _ = decode_chunk(wet, parse_chunks(wet)[0])
        return _lossless_rebuild(span, decoded_wet)[0]


def _native_atlas(base, chunk, overlays, format_name):
    """Exact donor rectangles at every mip, with no colour quantization."""
    t = parse_texture(base, chunk)
    donors = [base] + [d for d, _boxes in overlays]
    require(t.format_code == 11 and all(parse_texture(d, chunk) == t for d in donors), "atlas layouts differ")
    palettes = [d[chunk.system_bytes + t.palette_offset:chunk.system_bytes + t.palette_offset + 1024] for d in donors]
    video, cursor = [], t.pixel_offset
    for level in range(t.mip_levels):
        width, height = max(1, t.width >> level), max(1, t.height >> level)
        planes = [unswizzle_2d(d[chunk.system_bytes + cursor:chunk.system_bytes + cursor + width * height],
                               width, height, 1) for d in donors]
        pixels = bytearray(width * height * 4)
        for y in range(height):
            for x in range(width):
                donor = 0
                for index, (_d, boxes) in enumerate(overlays, 1):
                    if any(x0 >> level <= x < (x1 + (1 << level) - 1) >> level and
                           y0 >> level <= y < (y1 + (1 << level) - 1) >> level
                           for x0, y0, x1, y1 in (SPLAYER[b] for b in boxes)):
                        donor = index
                index = planes[donor][y * width + x]
                at = (y * width + x) * 4
                pixels[at:at + 4] = palettes[donor][index * 4:index * 4 + 4]
        video.append((width, height, bytes(pixels)))
        cursor += width * height
    system = bytearray(base[:chunk.system_bytes])
    require(format_name == "A8R8G8B8", "unsupported atlas format")
    struct.pack_into("<I", system, t.descriptor_offset + 8, 0)
    struct.pack_into("<I", system, t.descriptor_offset + 12, (t.packed_format & ~0xff00) | (6 << 8))
    return bytes(system) + b"".join(swizzle_2d(p, w, h, 4) for w, h, p in video)


def _atlas_overlays(recipe):
    atlas = recipe["atlas"]
    return atlas.get("overlays", [dict(donor=atlas.get("donor"), boxes=atlas.get("boxes"))])


def _encoded_span(template, decoded, video_bytes):
    from nfl_txtr import compress_vc_lz, minimum_vc_lz_overlap_scratch
    c = parse_chunks(template)[0]
    _old, info = decode_chunk(template, c)
    stream, _ = compress_vc_lz(decoded, stream_tag=info.stream_tag, offset_bits=info.offset_bits,
                               verify_roundtrip=True)
    fields = list(HEADER.unpack_from(template))
    fields[1] = (len(stream) + 15) & ~15
    fields[3] = video_bytes
    padding = fields[1] - len(stream)
    fields[5] = max(fields[5], (max(padding, minimum_vc_lz_overlap_scratch(stream, fields[1], len(decoded))) + 15) & ~15)
    span = HEADER.pack(*fields) + stream + bytes(padding)
    require(decode_chunk(span, parse_chunks(span)[0])[0] == decoded, "native atlas round-trip differs")
    return span


def _compact_span(span, *, optimal=False):
    """Same native decoded allocation, smaller stored allocation, guarded overlap."""
    from nfl_txtr import minimum_vc_lz_overlap_scratch
    from nfl_vc_lz_fill import compress_optimal
    key = (sha(span), optimal)
    if key in COMPACT_CACHE:
        return COMPACT_CACHE[key]
    chunk = parse_chunks(span)[0]
    decoded, info = decode_chunk(span, chunk)
    stream = (compress_optimal(decoded, stream_tag=info.stream_tag, offset_bits=info.offset_bits)
              if optimal else span[HEADER.size:HEADER.size + info.consumed_bytes])
    fields = list(HEADER.unpack_from(span))
    fields[1] = (len(stream) + 15) & ~15
    padding = fields[1] - len(stream)
    fields[5] = max(fields[5], (max(padding, minimum_vc_lz_overlap_scratch(stream, fields[1], len(decoded))) + 15) & ~15)
    rebuilt = HEADER.pack(*fields) + stream + bytes(padding)
    require(decode_chunk(rebuilt, parse_chunks(rebuilt)[0])[0] == decoded, "compact span changed decoded bytes")
    COMPACT_CACHE[key] = rebuilt
    return rebuilt


def _absorb(last, budget, total):
    """The last piece of a run takes the unused stored space; its decoded bytes and mips stay exact."""
    from nfl_txtr import minimum_vc_lz_overlap_scratch
    c = parse_chunks(last)[0]
    decoded, info = decode_chunk(last, c)
    stream = last[HEADER.size:HEADER.size + info.consumed_bytes]
    fields = list(HEADER.unpack_from(last))
    fields[1] += budget - total
    fields[5] = max(fields[5], (max(fields[1] - len(stream),
                                    minimum_vc_lz_overlap_scratch(stream, fields[1], len(decoded))) + 15) & ~15)
    return HEADER.pack(*fields) + stream + bytes(fields[1] - len(stream))


def _repack_prefix(target, donor, parts, recipe):
    """Chunks 1..43 from the donor (or a named part), stored inside the target's own 1..43 allocation."""
    tc = parse_chunks(target)
    sources = {"base": donor, **parts}
    pieces = []
    for index in range(1, 44):
        raw = sources[recipe.get("chunks", {}).get(str(index), "base")]
        c = parse_chunks(raw)[index]
        span = raw[c.offset:c.end_offset]
        if index in (1, 2, 3):
            span = _wet_template(span)
        pieces.append(_compact_span(span, optimal=recipe["id"] in ("G1", "G3") and index in (1, 2, 3, 11, 12, 43)))
    budget = tc[44].offset - tc[1].offset
    total = sum(map(len, pieces))
    require(total <= budget, f"exact native prefix needs {total}, available {budget}")
    pieces[-1] = _absorb(pieces[-1], budget, total)
    result = bytearray(target)
    result[tc[1].offset:tc[44].offset] = b"".join(pieces)
    return bytes(result)


def _repack_suffix(target, donor, parts, recipe):
    chunks = parse_chunks(target)
    pieces = []
    for index in range(49, 53):
        c = parse_chunks(donor)[index]
        span = donor[c.offset:c.end_offset]
        if index == 51 and recipe.get("atlas"):
            decoded, _ = decode_chunk(donor, c)
            overlays = []
            for row in _atlas_overlays(recipe):
                other = parts[row["donor"]]
                overlays.append((decode_chunk(other, parse_chunks(other)[51])[0], row["boxes"]))
            mixed = _native_atlas(decoded, c, overlays, recipe["atlas"]["format"])
            span = _encoded_span(span, mixed, len(mixed) - c.system_bytes)
        pieces.append(_compact_span(span))
    budget = len(target) - chunks[49].offset
    used = sum(map(len, pieces))
    prefix = target[:chunks[49].offset]
    if used > budget:
        # First reclaim prefix padding, then losslessly recompress existing relief maps; pixels and mips stay exact.
        c = chunks[43]
        before = [target[:c.offset], _compact_span(target[c.offset:c.end_offset])]
        tail = {i: target[chunks[i].offset:chunks[i].end_offset] for i in range(44, 49)}

        def available():
            return len(target) - sum(map(len, before)) - sum(map(len, tail.values()))
        for index in (45, 47, 46, 48):
            if available() >= used:
                break
            tail[index] = _compact_span(tail[index], optimal=True)
        require(available() >= used, f"native suffix needs {used}, available {available()} after lossless recompression")
        prefix = b"".join(before + [tail[i] for i in range(44, 49)])
        budget = len(target) - len(prefix)
    pieces[-1] = _absorb(pieces[-1], budget, used)
    result = prefix + b"".join(pieces)
    require(len(result) == len(target), "repacked complete kit size differs")
    return result


def compile_kit(target, donor, parts, recipe):
    """The composed kit package: same size, every donor texture with all its mips (a5k ``compile_kit``)."""
    original = target
    if recipe.get("repack_prefix"):
        target = _repack_prefix(target, donor, parts, recipe)
    if recipe.get("repack_suffix"):
        target = _repack_suffix(target, donor, parts, recipe)
    result = bytearray(target)
    unif_source = parts[recipe["unif_donor"]] if recipe.get("unif_donor") else donor
    result[UNIF_COLOURS:UNIF_COLOURS + 8] = unif_source[UNIF_COLOURS:UNIF_COLOURS + 8]
    require(len(result) == len(original), "kit allocation changed")
    return bytes(result)


# -- the Studio stage -----------------------------------------------------------------------------------------------

def roster_labels(roster):
    """{(asset code, style): (first, last)} of the five era slots in the main roster."""
    from . import nfl2k5_historic_styles as hs
    require(roster[:4] == b"ROST", "unexpected main roster wrapper")
    body = roster[32:]
    records = {}
    for at, code in hs.team_records(roster)[:32]:
        records.setdefault(code, []).append(at)
    out = {}
    for recipe in recipes():
        found = records.get(recipe["code"], [])
        require(len(found) == 1, f"the main roster has {len(found)} team records with asset code {recipe['code']}")
        out[(recipe["code"], recipe["style"])] = struct.unpack_from(
            "<HH", body, found[0] + TEAM_TABLE + 4 * (recipe["style"] - 1))
    return out


def _kit_task(task):
    """Worker: one composed kit. A pure function of the target, donor, parts and recipe bytes."""
    raw, donor, parts, recipe = task
    return compile_kit(raw, donor, parts, recipe)


def _compile_kits(pending):
    """[compile_kit(...)] for each pending kit, in order, in worker processes with a verified cache.

    NFL2K5_SERIAL_ERA_KITS=1 or NFL2K5_BUILD_WORKERS=1 compile them here one at a time;
    NFL2K5_DISABLE_COMPILE_CACHE=1 turns the cache off. The caller still checks every result against its output pin.
    """
    from . import nfl2k5_late_steps as late
    cache = late.StepCache.open("era-kits", **late.step_code("era-kits"))
    fixed, keys, misses = {}, {}, []
    for position, item in enumerate(pending):
        raw, donor, parts, recipe = item["task"]
        if cache is not None:
            keys[position] = cache.key(recipe, sha(raw), sha(donor), {k: sha(v) for k, v in sorted(parts.items())})
            hit = cache.get(keys[position])
            if isinstance(hit, dict) and isinstance(hit.get("after"), bytes) and len(hit["after"]) == len(raw) \
                    and hit.get("after_sha256") == sha(hit["after"]) and hit.get("before_sha256") == sha(raw):
                fixed[position] = hit["after"]
                continue
        misses.append(position)
    computed = late.ordered_map(_kit_task, [pending[i]["task"] for i in misses],
                                late.worker_count(len(misses), "NFL2K5_SERIAL_ERA_KITS", per_worker_mb=700))
    for position in misses:
        fixed[position] = next(computed)
        if cache is not None:
            raw = pending[position]["task"][0]
            cache.put(keys[position], dict(after=fixed[position], after_sha256=sha(fixed[position]), before_sha256=sha(raw)))
    return [fixed[position] for position in range(len(pending))]


def _finish_kits(rows, pending):
    """Compile the pending kits and fill their rows (the row slot of each is None until now)."""
    compiled = _compile_kits(pending)
    for item, fixed in zip(pending, compiled):
        raw, selector, row = item["task"][0], item["selector"], item["row"]
        if item["pinned"]:
            require(sha(fixed) == item["pin"]["after_sha256"], selector + ": composed kit differs from its output pin")
        rows[item["slot"]] = (selector, fixed, dict(row, state="composed", pinned_inputs=item["pinned"],
                                                    before_sha256=item["digest"], after_sha256=sha(fixed),
                                                    changed_bytes=sum(a != b for a, b in zip(raw, fixed)),
                                                    inputs={k: sha(v) for k, v in item["sources"].items()}))


def plan(kits, labels, retail_parts=None, document=None):
    """Decide and compile every era kit from already-read packages; nothing is written here.

    ``kits`` maps "SELECTOR.IFF" to the build copy's package bytes (targets, donors and parts); ``retail_parts``
    maps "SELECTOR.IFF" to retail packages for ``retail_`` parts (needed only when a kit is composed).
    Returns [(selector, new bytes or None, receipt row)].

    Every composed kit is independent of the others (the inputs are all read first), so the decisions are made
    here in order and the kits compile together (_compile_kits); the rows come out in the original order.
    """
    document = document or pins()
    rows, pending = [], []
    try:
        for recipe in recipes():
            wanted = tuple(recipe["label"])
            for side, selector in targets(recipe).items():
                pin = document["kits"][selector]
                name = selector + ".IFF"
                raw = kits.get(name)
                row = dict(selector=selector, id=recipe["id"], label=list(wanted))
                if raw is None:
                    rows.append((selector, None, dict(row, state="absent")))
                    continue
                digest = sha(raw)
                if labels.get((recipe["code"], recipe["style"])) != wanted:
                    # A build without the SOFTDRINK slot labels keeps the retail kit the slot still advertises.
                    rows.append((selector, None, dict(row, state="retail_label", sha256=digest)))
                    continue
                if digest == pin["after_sha256"]:
                    rows.append((selector, None, dict(row, state="applied", sha256=digest)))
                    continue
                if digest != pin["before_sha256"]:
                    # The user's recipe already put its own art in the era slot: keep it.
                    rows.append((selector, None, dict(row, state="other_uniform", sha256=digest)))
                    continue
                donor_name, part_names = inputs_of(recipe, side)
                missing = [n for n in [donor_name] + list(part_names.values())
                           if not n.startswith(RETAIL_PREFIX) and n + ".IFF" not in kits]
                if missing:
                    # e.g. no historic spare styles on this build: the donor packages do not exist
                    rows.append((selector, None, dict(row, state="donor_absent", missing=missing, sha256=digest)))
                    continue
                donor = kits[donor_name + ".IFF"]
                parts = {}
                for key, part in part_names.items():
                    if part.startswith(RETAIL_PREFIX):
                        require(retail_parts is not None, "the retail source is needed for " + part)
                        parts[key] = retail_parts[part[len(RETAIL_PREFIX):] + ".IFF"]
                    else:
                        parts[key] = kits[part + ".IFF"]
                sources = {donor_name: donor, **{part_names[k]: v for k, v in parts.items()}}
                pinned = all(sha(data) == pin["inputs"][label] for label, data in sources.items())
                pending.append(dict(slot=len(rows), selector=selector, row=row, pin=pin, pinned=pinned, digest=digest,
                                    sources=sources, task=(raw, donor, parts, recipe)))
                rows.append(None)
    except BaseException:
        # A kit that was due to compile before the failing one would have failed first.
        _finish_kits(rows, pending)
        raise
    _finish_kits(rows, pending)
    return rows


def needed_packages():
    """Every kit package the stage reads from the build copy, and the retail-only parts."""
    copy, retail = set(), set()
    for recipe in recipes():
        for side, selector in targets(recipe).items():
            donor, parts = inputs_of(recipe, side)
            copy |= {selector + ".IFF", donor + ".IFF"}
            for part in parts.values():
                (retail if part.startswith(RETAIL_PREFIX) else copy).add(part.removeprefix(RETAIL_PREFIX) + ".IFF")
    return sorted(copy), sorted(retail)


def _read_packages(image, names):
    index = bump._parsed_index(image)
    by_name = {}
    for entry in index.entries:
        by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
    out = {}
    for name in names:
        entries = by_name.get(name, [])
        require(len(entries) <= 1, name + " kit package duplicated")
        if entries:
            out[name] = image.read_segments(index.sub_extents(entries[0], 0, entries[0].size))
    return index, by_name, out


def apply_to_image(path, retail_source):
    """Compose the era kits on a private build copy; ``retail_source`` is a path or a callable returning one.

    Read every input (and compile every kit) before the first write; replay on the output is a no-op.
    """
    try:
        with bump._Image.open(Path(path), writable=False) as source:
            index = bump._parsed_index(source)
            names = {bump.logical_name_for(e.name_id) for e in index.entries}
    except (ValueError, OSError):
        return dict(state="other_image", written=0, kits=[])
    copy_names, retail_names = needed_packages()
    if not all(f"{r['code']}{s}{r['style']}.IFF" in names for r in recipes() for s in "HA"):
        return dict(state="other_uniform", written=0, kits=[])
    with bump._Image.open(Path(path), writable=True) as image:
        index, by_name, kits = _read_packages(image, copy_names)
        roster_entry = index.entries[5]
        require(roster_entry.name_id == ROSTER_NAME_ID, "unexpected main roster identity")
        labels = roster_labels(image.read_segments(index.sub_extents(roster_entry, 0, roster_entry.size)))
        retail_parts = None
        if any(labels.get((r["code"], r["style"])) == tuple(r["label"]) for r in recipes()):
            retail = Path(retail_source() if callable(retail_source) else retail_source)
            with bump._Image.open(retail, writable=False) as original:
                retail_parts = _read_packages(original, retail_names)[2]
            require(set(retail_parts) == set(retail_names), "retail era kit parts absent from the source disc")
        rows = plan(kits, labels, retail_parts)
        written = 0
        for selector, data, _row in rows:
            if data is None:
                continue
            entry = by_name[selector + ".IFF"][0]
            segments = index.sub_extents(entry, 0, len(data))
            image.write_segments(segments, data)
            require(image.read_segments(segments) == data, selector + " read-back differs")
            written += 1
    receipts = [row for _selector, _data, row in rows]
    states = {row["state"] for row in receipts}
    return dict(state="applied" if states & {"composed", "applied"} else "other_uniform", written=written,
                runtime_witnessed=False, kits=receipts)

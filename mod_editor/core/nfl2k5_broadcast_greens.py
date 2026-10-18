"""Final grass-only palette correction, after venue and Anniversary writers.

The transform is applied once to the completed field set. It preserves P8
indices, every mip, alpha, paint textures, geometry, light rigs and shadows.
Only named, exclusively owned grass materials are eligible. A receipt makes
image replay idempotent; the pure bundle operation intentionally has no marker.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_modern_metlife as ml
from . import nfl2k5_modern_surfaces as ms

REVISION = "gr1-v2"
SCHEMA = "nfl2k5_broadcast_greens/v1"
# Median of the three neutral MetLife photo medians / median of three
# playtest MetLife still medians. The fireworks photograph is excluded.
SYNTHETIC_GAIN = (58 / 87, 102 / 111, 56 / 62)
# Noah also requested darker natural grass. Preserve its measured warmer hue
# with the common green-channel reduction. This is an extrapolation, not a
# claim that grass broadcasts were too bright in the playtest.
GRASS_GAIN = (102 / 111,) * 3
FIELD_MATERIALS = frozenset(("color_premipped", "grass_outside_premipped"))
STADIUM_MATERIALS = {
    "pf_ground": "grass", "pf_field_strip": "grass",
    "pf_turf_strip": "synthetic", "env_grass": "grass",
}


def require(ok, message):
    if not ok:
        raise ValueError("Broadcast greens: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def green(rgb, alpha=255):
    """Eligibility inside a grass-owned texture: keep white paint and snow."""
    r, g, b = rgb
    return alpha > 0 and g > r * 1.08 and g > b * 1.10 and g - min(r, b) > 18


def rgb_transform(rgb, family):
    require(family in ("grass", "synthetic"), "unknown surface family")
    gains = GRASS_GAIN if family == "grass" else SYNTHETIC_GAIN
    return tuple(int(round(c * k)) for c, k in zip(rgb, gains))


def palette_transform(palette, family):
    require(len(palette) == 1024, "P8 palette size differs")
    out = bytearray(palette)
    selected = []
    for i in range(256):
        b, g, r, a = palette[i * 4:i * 4 + 4]
        if not green((r, g, b), a):
            continue
        nr, ng, nb = rgb_transform((r, g, b), family)
        out[i * 4:i * 4 + 3] = bytes((nb, ng, nr))
        selected.append(i)
    return bytes(out), selected


def paint_scene(decoded, rec, family):
    """Return exact decoded edits and scope, refusing shared paint palettes."""
    out = bytearray(decoded)
    allowed = ({name: family for name in FIELD_MATERIALS} if rec["name"] == "field"
               else STADIUM_MATERIALS if rec["name"] == "stadium" else {})
    ranges, palettes, words = [], [], []
    textures = {int(r["index"]): r for r in rec["embedded_textures"]}
    owners = {}
    for material in rec["materials"]:
        index = material.get("texture_index")
        if index is not None:
            owners.setdefault(int(index), []).append(material["name"])
    done = set()
    for material in rec["materials"]:
        name = material["name"]
        if name not in allowed:
            continue
        index = material.get("texture_index")
        if index is None:
            at = material["record_offset"] + 0x18
            word = struct.unpack_from("<I", decoded, at)[0]
            rgb = ((word >> 16) & 255, (word >> 8) & 255, word & 255)
            if green(rgb, word >> 24):
                r, g, b = rgb_transform(rgb, allowed[name])
                new = (word & 0xFF000000) | r << 16 | g << 8 | b
                struct.pack_into("<I", out, at, new)
                ranges.append((at, at + 3))
                words.append(dict(material=name, offset=at, before=word, after=new))
            continue
        index = int(index)
        require(index in textures, "missing grass texture")
        require(set(owners[index]) <= set(allowed), "grass texture shared with paint: " + str(owners[index]))
        row = textures[index]
        require(row["format_name"] == "P8", "unsupported grass texture format")
        at = rec["system_bytes"] + row["palette_offset"]
        if at in done:
            continue
        done.add(at)
        # Different texture descriptors can alias the same palette. Audit all
        # descriptors, including those not reached through the selected material.
        for other in textures.values():
            if other["palette_offset"] == row["palette_offset"]:
                require(set(owners.get(int(other["index"]), ())) <= set(allowed),
                        "grass palette shared with paint")
        before = bytes(decoded[at:at + 1024])
        after, selected = palette_transform(before, allowed[name])
        out[at:at + 1024] = after
        for i in selected:
            ranges.append((at + i * 4, at + i * 4 + 3))
        palettes.append(dict(materials=owners[index], family=allowed[name], offset=at,
                             entries=selected, before=sha(before), after=sha(after)))
    restored = bytearray(out)
    for lo, hi in ranges:
        restored[lo:hi] = decoded[lo:hi]
    require(restored == decoded, "decoded bytes outside grass RGB changed")
    return bytes(out), dict(palettes=palettes, materials=words, decoded_ranges=ranges,
                           non_grass_bytes_changed=0, indices_mips_alpha_identical=True)


def safe_fills(encoded, decoded, stored, scratch_allocation):
    """Fixed-size fills with the final flag fetch inside the allocation.

    A match can be split into two matches with the same distance and decoded
    bytes. This changes token/flag alignment without an expensive new parse.
    The split consumes only spare compressed storage, never loader scratch.
    """
    tx = ml._tools()[0]
    import nfl_vc_lz_fill as fill
    size, tag, bits, tokens = fill.parse_tokens(encoded)
    candidates = [encoded]
    # At most four additional two-byte match commands. Put the extra input
    # early, keeping the in-place decoder ahead of its output.
    split = list(tokens)
    for _ in range(4):
        index = next((i for i, t in enumerate(split) if t[0] == "M" and t[2] >= 6), None)
        if index is None:
            break
        _kind, distance, length = split[index]
        split[index:index + 1] = [("M", distance, 3), ("M", distance, length - 3)]
        stream = fill.serialize(size, tag, bits, split)
        if len(stream) > stored:
            break
        candidates.append(stream)
    for stream in candidates:
        for slack in dict.fromkeys((0, min(16, scratch_allocation))):
            filled = fill.fill_stream(stream, decoded, stored, slack=slack)[0]
            padding = stored - len(filled)
            scratch = tx.minimum_vc_lz_overlap_scratch(filled, stored, len(decoded))
            if (scratch <= scratch_allocation and padding <= scratch_allocation
                    and (padding > 0 or len(fill.parse_tokens(filled)[3]) % 8 != 0)):
                yield filled + bytes(padding), dict(padding=padding, scratch=scratch,
                                                   scratch_allocation=scratch_allocation,
                                                   split_matches=stream is not encoded)


def fit_span(span, decoded):
    """Lossless fixed allocation, preserving wrapper and decoder scratch."""
    tx = ml._tools()[0]
    import nfl_vc_lz_fill as fill
    c = tx.parse_chunks(span, allow_trailing=True)[0]
    if not c.compressed:
        require(len(decoded) == c.stored_size, "raw scene size differs")
        return span[:32] + decoded, dict(encoder="raw")
    declared, tag = struct.unpack_from("<II", span, 32)
    require(declared == len(decoded), "decoded allocation differs")
    widths = tuple(dict.fromkeys((span[40], 10, 9, 8, 11)))
    attempts = []
    for optimal in (False, True):
        for bits in widths:
            try:
                encoded = (fill.compress_optimal(decoded, stream_tag=tag, offset_bits=bits) if optimal else
                           tx.compress_vc_lz(decoded, stream_tag=tag, offset_bits=bits,
                                             max_encoded_size=c.stored_size, verify_roundtrip=False)[0])
                if len(encoded) > c.stored_size:
                    continue
                for body, fit in safe_fills(encoded, decoded, c.stored_size, c.overlap_scratch_bytes):
                    after = span[:32] + body
                    require(len(after) == len(span), "fixed scene size differs")
                    require(tx.decode_chunk(after, tx.parse_chunks(after, allow_trailing=True)[0])[0] == decoded,
                            "lossless scene readback differs")
                    return after, dict(encoder="optimal" if optimal else "greedy", offset_bits=bits, **fit)
            except ValueError as exc:
                attempts.append(str(exc)[:160])
    raise ValueError("Broadcast greens cannot fit losslessly: " + str(attempts))


def bundle_transform(data, name, family):
    """No palette quantization, texture replacement, geometry or lighting edits."""
    tx, inv, ResourceRecord, _header, _writer = ml._tools()
    out = bytearray(data)
    edits = []
    # Parse each scene once. Detail normals, Fldd and st1's shadow retain
    # their original encoded bytes. Visible green divot texels follow grass.
    for c in tx.parse_chunks(data, allow_trailing=True):
        if c.kind == "TXTR" and family == "grass":
            decoded = tx.decode_chunk(data, c)[0]
            info = tx.parse_texture(decoded, c)
            if info.name == "divots":
                require(info.format_name == "P8", "unsupported divot texture")
                at = c.system_bytes + info.palette_offset
                palette, selected = palette_transform(decoded[at:at + 1024], family)
                edited = bytearray(decoded)
                edited[at:at + 1024] = palette
                if edited != decoded:
                    span, fitted = fit_span(data[c.offset:c.end_offset], bytes(edited))
                    out[c.offset:c.end_offset] = span
                    edits.append(dict(scene="divots", offset=c.offset, size=len(span), fit=fitted,
                                      palettes=[dict(materials=["divots"], family=family, offset=at, entries=selected)],
                                      materials=[], decoded_ranges=[(at + i * 4, at + i * 4 + 3) for i in selected],
                                      non_grass_bytes_changed=0, indices_mips_alpha_identical=True))
            continue
        if c.kind != "SCNE":
            continue
        decoded = tx.decode_chunk(data, c)[0]
        _at, scene = inv.pointer_name(decoded, 0x10, c.system_bytes, "greens scene")
        if scene not in ("field", "stadium"):
            continue
        record = ResourceRecord(outer_index=0, outer_id="", outer_size=len(data), chunk_index=c.index,
                                chunk_offset=c.offset, kind=c.kind, stored_size=c.stored_size,
                                word_08=c.system_bytes, word_0c=c.video_bytes, word_10=c.compression_magic,
                                word_14=c.overlap_scratch_bytes)
        rec = inv.parse_scene(c.index, record, decoded, {})[0]
        edited, receipt = paint_scene(decoded, rec, family)
        if edited == decoded:
            continue
        span, fitted = fit_span(data[c.offset:c.end_offset], edited)
        out[c.offset:c.end_offset] = span
        edits.append(dict(scene=rec["name"], offset=c.offset, size=len(span), fit=fitted, **receipt))
    return bytes(out), dict(name=name, family=family, before=sha(data), after=sha(out), edits=edits,
                           non_grass_bytes_changed=0, lighting_shadows_detail_identical=True)


def entries(archive):
    """All native stadium variants and all installed Anniversary aliases."""
    names = [f"{kind}{i:02}{t}{w}.iff" for kind in "sa" for i in range(100) for t in "dan" for w in "drs"]
    ids = {ml.name_id(n): n for n in names}
    out = {}
    for entry in archive.entries:
        name = ids.get(entry.name_id)
        if name is not None:
            require(name not in out, "duplicate field resource: " + name)
            out[name] = entry
    require(set(ms.HOME_BUNDLES) <= set(out), "missing home fields")
    return out


def families(archive):
    """Modern home surfaces from venue table, other fields from ROST turf word."""
    e = archive.entries[ms.ROST_OUTER_INDEX]
    body = archive.read(e.virtual_offset, e.size)[32:]
    result = {}
    for at, fields in ml._stadium_records(body):
        prefix = fields["asset_code"][1]
        word = struct.unpack_from("<I", body, at + 0x1C)[0]
        require(word in (0, 1), "unknown ROST surface word")
        family = "grass" if word else "synthetic"
        require(prefix not in result or result[prefix] == family, "conflicting ROST surface words")
        result[prefix] = family
    result.update({p: v["surface"] for p, v in ms.venues().items()})
    from . import nfl2k5_espn25_fields as fields
    for row in fields.catalog():
        # Period aliases copy their source field, regardless of the moment's
        # displayed venue. Built sources carry modern surfaces.
        prefix = row["source_prefix"]
        result[f"a{row['row'] - 1:02}"] = result[prefix]
    return result


def receipt_path(path):
    return Path(str(path) + ".greens.json")


def save(path, doc):
    Path(path).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")


def _bundle_job(job):
    name, family, before = job
    after, receipt = bundle_transform(before, name, family)
    return name, after, receipt


LEGACY_WORKERS = 4


def _greens_task(job):
    """Worker: one field bundle. Returns (name, after, receipt); a pure function of the job."""
    return _bundle_job(job)


def _remembered_bundle(cache, key, job):
    """A cached (name, after, receipt) for exactly this bundle, or None; checked against its own digests."""
    from . import nfl2k5_late_steps as late
    record = cache.get(key) if cache is not None else None
    name, family, before = job
    if not (isinstance(record, dict) and isinstance(record.get("after"), bytes) and isinstance(record.get("rec"), dict)
            and record["rec"].get("before") == late.sha(before) and record["rec"].get("after") == late.sha(record["after"])
            and record["rec"].get("name") == name and len(record["after"]) == len(before)):
        return None
    return name, record["after"], record["rec"]


def apply_to_image(target, *, progress=None, anniversary_receipt=None, workers=None):
    """Last resource pass on a disposable Studio build, before compaction.

    ``workers`` defaults to the late-step pool size (cores - 1, or NFL2K5_BUILD_WORKERS). The bundles are
    independent and consumed in name order, so the written bytes do not depend on the count.
    NFL2K5_SERIAL_BROADCAST_GREENS=1 (or NFL2K5_SERIAL_LATE_STEPS=1) restores the old four workers.
    """
    from . import nfl2k5_late_steps as late
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_modern_venues_2026 as venues
    require(workers is None or (type(workers) is int and workers >= 1), "workers must be a positive number")
    say = progress or (lambda *args: None)
    path = receipt_path(target)
    old = json.loads(path.read_text()) if path.exists() else None
    with ms._outer_image()(str(target)) as archive:
        names = entries(archive)
        kinds = families(archive)
        if old is not None:
            require(old.get("schema") == SCHEMA and old.get("revision") == REVISION, "foreign greens receipt")
            require(set(old["bundles"]) == set(names), "greens resource set differs")
            require(all(sha(archive.read(e.virtual_offset, e.size)) == old["bundles"][n]["after"]
                        for n, e in names.items()), "field changed after greens pass")
            return dict(state="applied", bundles=len(names), bytes_written=0, already_applied=True)
        jobs = []
        for name, e in sorted(names.items()):
            require(name[:3] in kinds, "unknown surface family for " + name)
            before = archive.read(e.virtual_offset, e.size)
            jobs.append((name, kinds[name[:3]], before))
    work = {}
    if workers is None:
        workers = late.worker_count(len(jobs), "NFL2K5_SERIAL_BROADCAST_GREENS", per_worker_mb=600,
                                    legacy=LEGACY_WORKERS)
    cache = late.StepCache.open("broadcast-greens", **late.step_code("broadcast-greens"))
    keys, answers, misses = {}, {}, []
    for position, job in enumerate(jobs):
        if cache is not None:
            keys[position] = cache.key(job[0], job[1], late.sha(job[2]))
            hit = _remembered_bundle(cache, keys[position], job)
            if hit is not None:
                answers[position] = hit
                continue
        misses.append(position)
    computed = late.ordered_map(_greens_task, [jobs[i] for i in misses], workers)
    for i, job in enumerate(jobs):
        if i in answers:
            name, after, rec = answers[i]
        else:
            name, after, rec = next(computed)
            if cache is not None:
                cache.put(keys[i], dict(after=after, rec=rec))
        work[name] = (names[name], after, rec)
        say("Broadcast greens: " + name, i + 1, len(names))
    cr, vr, sr = colour.read_image_receipt(target), venues.read_receipt(target), ms.read_receipt(target)
    written = 0
    with ms._outer_image()(str(target), writable=True) as archive:
        for name, (e, after, rec) in work.items():
            require(sha(archive.read(e.virtual_offset, e.size)) == rec["before"], "field changed while preparing")
            for edit in rec["edits"]:
                lo, size = edit["offset"], edit["size"]
                written += archive.write(e.virtual_offset + lo, after[lo:lo + size])
            require(archive.read(e.virtual_offset, e.size) == after, "image readback differs")
            if cr is not None:
                ms._update_colour_receipt(cr, name, after)
            for doc in (vr, sr):
                if doc is not None and name in doc.get("bundles", {}):
                    doc["bundles"][name]["applied_sha256"] = sha(after)
            if anniversary_receipt is not None:
                for row in anniversary_receipt["fields"]["assets"]:
                    if row["alias"] == name:
                        row["before_greens"] = row["after"]
                        row["after"] = sha(after)
    if cr is not None:
        colour._save_image_receipt(target, cr)
    if vr is not None:
        venues._save_receipt(target, vr)
    if sr is not None:
        ms.save_receipt(target, sr)
    save(path, dict(schema=SCHEMA, revision=REVISION, bundles={n: rec for n, (_e, _a, rec) in work.items()},
                    bytes_written=written, gains=dict(synthetic=SYNTHETIC_GAIN, grass=GRASS_GAIN)))
    return dict(state="applied", bundles=len(work), bytes_written=written, non_grass_bytes_changed=0)

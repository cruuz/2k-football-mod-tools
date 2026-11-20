"""The 2026 jersey relief: this season's construction in the bump maps of every SOFTDRINK 2026 kit (beta 81).

Job b81-uniforms (Noah 11/18 on the first modern relief: "The jersey looks overly sculpted tbh, should be less obvious
and more accurate to the real thing"; 11/19, of the three strengths drawn from this season's close-ups: "B. Keep new.")
replaces the ``bump_jersey``, ``bump_sleeve`` and ``bump_pants`` maps of the 178 SOFTDRINK 2026 kit packages
(A8R8G8B8 tangent-space normal maps, R = +u, G = up, B = out) with level B of ``tools/b81_uniforms/bump_true.py``:

* jersey: the 2004 sculpt's folds softened (gain 0.8) with every 2004 construction detail lifted out, hairline seams,
  a flat collar band, two small vents, sparse pin holes below the V, and the collar shield barely raised under the
  kit's own painted shield (and any maker's mark the kit paints on the torso shoulder caps);
* sleeve: the master sleeve's folds, one hem hairline, the painted swoosh barely raised;
* pants: the kit's own pants sculpt with the 2004 shield and Reebok embosses lifted out, the painted swoosh and shield
  barely raised.

What ships (``data/nfl2k5_relief_2026_b81u.json`` and its art folder ``data/nfl2k5_relief_2026_b81u/``): one master
map for the jersey and one for the sleeve, and small per-kit patches (PNG boxes; alpha 255 takes the patch texel,
alpha 0 keeps the base), each distinct patch once. Pants carry no master: a kit's pants map is composed on its own
pants map as the disc holds it. A map is composed with numpy only, its mip chain is the Studio bump writer's box
filter, it is swizzled and packed into the kit's own fixed compressed span (the retail packer first, the tighter
optimal parse only when a span needs it), each DISTINCT map compressed once and its stream reused for every slot that
takes it. The wrapper, its loader scratch word and the span size never change; each written span is read back.

Every slot is pinned: ``before_sha256`` is the stored span as a v0.10 build holds it after the earlier steps,
``after_sha256`` the span this step writes. A Studio build (not strict) leaves a slot alone when it holds anything else
(a user's own bump art); a second run writes nothing. Strict refuses any slot that is neither.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

from . import nfl2k5_bump_texture_writer as bump
from . import build_steps
from nfl_tset_png_import import decode_rgba_png
from nfl_txtr import (HEADER, COMPRESSED_SENTINEL, TxtrError, check_vc_lz_native, compress_vc_lz, decode_chunk,
                      minimum_vc_lz_overlap_scratch, parse_chunks, parse_texture, swizzle_2d, texture_to_rgba)
from nfl_vc_lz_fill import compress_optimal, fill_stream

SCHEMA = "nfl2k5_relief_2026/v1"
ROOT = Path(__file__).resolve().parents[2]
DATA_B81U = ROOT / "data/nfl2k5_relief_2026_b81u.json"
SLOTS = ("bump_jersey", "bump_sleeve", "bump_pants")
BASES = ("master", "before")


def require(ok, message):
    if not ok:
        raise ValueError("2026 jersey relief: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def spec(path=None):
    document = json.loads(Path(path or DATA_B81U).read_text(encoding="utf-8"))
    require(document.get("schema") == SCHEMA, "unexpected data schema")
    seen = set()
    for row in document["slots"]:
        key = (row["selector"], row["slot"])
        require(key not in seen, "duplicate slot entry " + repr(key))
        seen.add(key)
        require(row["slot"] in SLOTS and row["base"] in BASES, "unknown slot or base")
        require(row["base"] != "master" or row["slot"] in document["masters"], "slot without its master")
        require(row["patch"] is None or document["patches"][row["patch"]]["slot"] == row["slot"], "patch of another slot")
    return document


def relief_b81u():
    """The b81-uniforms relief document (level B on the 178 SOFTDRINK 2026 kit packages)."""
    return spec(DATA_B81U)


def art_folder(document):
    name = document.get("art")
    require(isinstance(name, str) and name == Path(name).name and name.startswith("nfl2k5_relief_2026"),
            "unexpected art folder")
    return ROOT / "data" / name


def selectors(document=None):
    return sorted({r["selector"] for r in (document or relief_b81u())["slots"]})


# -- composing a map ------------------------------------------------------------------------------------------------

def read_art(folder, entry):
    """One authored PNG of the document as an (h, w, 4) uint8 array, checked against its pin and size."""
    payload = (Path(folder) / entry["png"]).read_bytes()
    require(sha(payload) == entry["sha256"], entry["png"] + " differs from its pin")
    width, height, rgba = decode_rgba_png(payload, (entry["width"], entry["height"]))
    return np.frombuffer(rgba, np.uint8).reshape(height, width, 4)


def compose(base, patch=None, at=(0, 0)):
    """``base`` with ``patch`` laid over it at ``at`` (x, y): texels of alpha 255 replace, alpha 0 keep. Alpha is
    255 everywhere in the result (these maps do not use it)."""
    out = np.array(base, np.uint8, copy=True)
    if patch is not None:
        x, y = at
        h, w = patch.shape[:2]
        require(0 <= x and 0 <= y and x + w <= out.shape[1] and y + h <= out.shape[0], "patch outside its map")
        take = patch[..., 3] == 255
        require(bool(np.all(take | (patch[..., 3] == 0))), "patch alpha is neither 0 nor 255")
        region = out[y:y + h, x:x + w]
        region[take] = patch[take]
    out[..., 3] = 255
    return out


def mip_levels(rgba, levels):
    """The bump writer's box-filter chain (``generate_mips``: each texel the rounded mean of its four parents,
    ``(a + b + c + d + 2) // 4`` per channel), in numpy."""
    out = [np.ascontiguousarray(rgba, np.uint8)]
    for _ in range(1, levels):
        a = out[-1].astype(np.uint16)
        require(a.shape[0] % 2 == 0 and a.shape[1] % 2 == 0, "map cannot be halved exactly")
        s = a[0::2, 0::2] + a[0::2, 1::2] + a[1::2, 0::2] + a[1::2, 1::2]
        out.append(((s + 2) // 4).astype(np.uint8))
    return out


def body(system, rgba, levels):
    """The decoded TXTR body: the slot's own system buffer, then the swizzled B,G,R,A mip chain."""
    chain = []
    for level in mip_levels(rgba, levels):
        bgra = level[..., [2, 1, 0, 3]]
        chain.append(swizzle_2d(np.ascontiguousarray(bgra).tobytes(), level.shape[1], level.shape[0], 4))
    return bytes(system) + b"".join(chain)


# -- packing into a fixed span ----------------------------------------------------------------------------------------

def fit(template_span, decoded, compressed):
    """``nfl_vc_lz_fill.rebuild_fixed_span_filled`` for a stream compressed once for several slots, with the bump
    writer's fill slack: fill it to this slot's stored body inside the retail loader scratch allowance, keep the
    wrapper exactly, check it natively and by an independent decode."""
    raw_kind, stored_size, system_bytes, video_bytes, magic, scratch, _r0, _r1 = HEADER.unpack_from(template_span)
    require(magic == COMPRESSED_SENTINEL and len(decoded) == system_bytes + video_bytes, "not this slot's body")
    require(len(compressed) <= stored_size, "stream longer than the stored body")
    chunk = parse_chunks(template_span, allow_trailing=True)[0]
    # the bump writer's tail slack: all 16 bytes of the common retail allowance as slack can need 17 when the last
    # token crosses a flag group
    filled, _ = fill_stream(compressed, decoded, stored_size, slack=min(scratch, 8))
    padding = stored_size - len(filled)
    exact = minimum_vc_lz_overlap_scratch(filled, stored_size, len(decoded))
    require(padding <= scratch and exact <= scratch, "cannot keep the retail scratch word (stream %d, filled %d, stored "
            "%d, padding %d, needs %d, retail %d)" % (len(compressed), len(filled), stored_size, padding, exact, scratch))
    rebuilt = template_span[:HEADER.size] + filled + bytes(padding)
    try:
        check_vc_lz_native(rebuilt[HEADER.size:], stored_size, scratch, decoded)
    except TxtrError:
        require(scratch != 0, "native check failed with no scratch")
        filled, _ = fill_stream(compressed, decoded, stored_size - 1, slack=0)
        padding = stored_size - len(filled)
        exact = minimum_vc_lz_overlap_scratch(filled, stored_size, len(decoded))
        require(padding <= scratch and exact <= scratch, "native-safe fill cannot keep the retail scratch word")
        rebuilt = template_span[:HEADER.size] + filled + bytes(padding)
        check_vc_lz_native(rebuilt[HEADER.size:], stored_size, scratch, decoded)
    back, info = decode_chunk(rebuilt, chunk)
    require(back == decoded and len(rebuilt) == len(template_span) and info.consumed_bytes == len(filled),
            "filled span failed its independent decode")
    return rebuilt


def _stream_facts(span):
    chunk = parse_chunks(span, allow_trailing=True)[0]
    require(chunk.kind == "TXTR" and chunk.compressed and chunk.end_offset == len(span), "not one compressed TXTR span")
    stream = span[chunk.body_offset:chunk.end_offset]
    system = bump._decompress_prefix(stream, chunk.output_size, chunk.system_bytes)
    texture = parse_texture(system, chunk)
    return chunk, system, texture, int.from_bytes(stream[4:8], "little"), stream[8]


def _job(job):
    """One distinct map: compose it, build its body, compress it once, fit it into every slot that takes it.
    job = (composed sha256, base ("master": RGBA bytes and shape, or "before": None), patch (RGBA bytes, shape, x, y)
    or None, [(key, before span), ...]) -> [(key, after span, detail), ...]"""
    composed_sha, master, patch, slots = job
    facts = [_stream_facts(span) for _key, span in slots]
    chunk, system, texture = facts[0][:3]
    for other in facts[1:]:
        require(other[1] == system, "slots of one map differ in their system buffer")
    if master is None:
        decoded, _ = decode_chunk(slots[0][1], chunk)
        base = np.frombuffer(texture_to_rgba(decoded, chunk, texture), np.uint8).reshape(texture.height, texture.width, 4)
    else:
        data, shape = master
        base = np.frombuffer(data, np.uint8).reshape(shape)
    require(base.shape == (texture.height, texture.width, 4), "map size differs from the slot")
    over = None if patch is None else (np.frombuffer(patch[0], np.uint8).reshape(patch[1]), (patch[2], patch[3]))
    rgba = compose(base, *(over or (None,)))
    require(sha(rgba.tobytes()) == composed_sha, "composed map differs from its pin")
    decoded = body(system, rgba, texture.mip_levels)
    require(len(decoded) == chunk.output_size, "mip chain does not fill the slot's allocation")
    streams = {}
    out = []
    for (key, span), (slot_chunk, _s, _t, tag, offset_bits) in zip(slots, facts):
        stored = slot_chunk.stored_size
        greedy = streams.get(("greedy", tag, offset_bits))
        if greedy is None:
            greedy = streams[("greedy", tag, offset_bits)] = compress_vc_lz(
                decoded, stream_tag=tag, offset_bits=offset_bits, verify_roundtrip=True)[0]
        encoder, stream = "greedy", greedy
        if len(greedy) > stored:
            encoder, stream = "optimal", streams.get(("optimal", tag, offset_bits))
            if stream is None:
                stream = streams[("optimal", tag, offset_bits)] = compress_optimal(decoded, stream_tag=tag,
                                                                                   offset_bits=offset_bits)
            require(len(stream) <= stored, "map needs %d bytes, more than its %d-byte span" % (len(stream), stored))
        out.append((key, fit(span, decoded, stream), dict(encoder=encoder, packed_bytes=len(stream), stored_size=stored)))
    return out


def workers(count=None):
    return count or min(8, max(1, (os.cpu_count() or 2) - 1))


def compile_slots(rows, spans, document=None, *, count=None, progress=None):
    """{(selector, slot): before span} for the given document rows -> {(selector, slot): (after span, detail)}.
    Rows that take the same composed map share one compressed stream."""
    document = document or relief_b81u()
    folder = art_folder(document)
    masters = {name: read_art(folder, entry) for name, entry in document["masters"].items()}
    patches = {}
    groups = {}
    for row in rows:
        key = (row["selector"], row["slot"])
        base = "master" if row["base"] == "master" else "before:" + sha(spans[key])
        group = groups.setdefault((row["slot"], base, row["patch"], row["composed_sha256"]), [])
        group.append((key, spans[key]))
    jobs = []
    for (slot, base, patch_id, composed), slots in groups.items():
        master = None
        if base == "master":
            m = masters[slot]
            master = (m.tobytes(), m.shape)
        patch = None
        if patch_id is not None:
            entry = document["patches"][patch_id]
            p = patches.get(patch_id)
            if p is None:
                p = patches[patch_id] = read_art(folder, entry)
            patch = (p.tobytes(), p.shape, entry["x"], entry["y"])
        jobs.append((composed, master, patch, slots))
    jobs.sort(key=lambda job: -sum(len(span) for _k, span in job[3]))
    say = progress or (lambda message, done, total: None)
    results = {}
    n = workers(count)
    say("The 2026 jersey relief: packing %d distinct maps into %d slots" % (len(jobs), len(rows)), 0, len(jobs))
    if n > 1 and len(jobs) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=n) as pool:
            for index, out in enumerate(pool.map(_job, jobs, chunksize=1)):
                for key, span, detail in out:
                    results[key] = (span, detail)
                say("The 2026 jersey relief: %d of %d maps packed" % (index + 1, len(jobs)), index + 1, len(jobs))
    else:
        for index, job in enumerate(jobs):
            for key, span, detail in _job(job):
                results[key] = (span, detail)
            say("The 2026 jersey relief: %d of %d maps packed" % (index + 1, len(jobs)), index + 1, len(jobs))
    return results


# -- the image ------------------------------------------------------------------------------------------------------

def _chunk_for(raw, index):
    for chunk in parse_chunks(raw, allow_trailing=True):
        if chunk.index == index:
            return chunk
    raise ValueError("2026 jersey relief: chunk %d absent" % index)


def state_of(row, raw):
    """("before" | "after" | "other", chunk, span) of one pinned slot in its package bytes."""
    chunk = _chunk_for(raw, row["chunk"])
    span = raw[chunk.offset:chunk.end_offset]
    layout_ok = (len(raw), chunk.offset, len(span)) == (row["resource_size"], row["offset"], row["length"])
    digest = sha(span) if layout_ok else None
    state = "before" if digest == row["before_sha256"] else "after" if digest == row["after_sha256"] else "other"
    return state, chunk, span


def apply_to_image(path, *, strict=False, document=None, count=None, progress=None):
    """Studio build step: the pinned bump spans only. Not strict, a slot holding anything but its pinned input (or its
    finished output) is left alone; strict refuses it. Every write is read back."""
    document = document or relief_b81u()
    try:
        with bump._Image.open(Path(path), writable=False) as source:
            index = bump._parsed_index(source)
            names = {bump.logical_name_for(e.name_id) for e in index.entries}
    except (ValueError, OSError):
        if strict:
            raise
        return dict(state="other_image", written_spans=0, written_bytes=0, skipped_slots=[], kits=[])
    wanted = selectors(document)
    if not strict and not all(s + ".IFF" in names for s in wanted):
        return dict(state="other_uniform", written_spans=0, written_bytes=0, skipped_slots=[], kits=[])
    by_selector = {}
    for row in document["slots"]:
        by_selector.setdefault(row["selector"], []).append(row)
    written, written_bytes, skipped, todo, spans, places, kits = 0, 0, [], [], {}, {}, {}
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        entries = {}
        for entry in index.entries:
            entries.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        # Preflight every slot before the first write, so a refusal leaves the image untouched.
        for selector in wanted:
            found = entries.get(selector + ".IFF", [])
            require(len(found) == 1, selector + " kit package absent or duplicated")
            entry = found[0]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            with build_steps.resource(selector + ".IFF"):
                for row in by_selector[selector]:
                    state, chunk, span = state_of(row, raw)
                    kits.setdefault(selector, dict(selector=selector, written=[], kept=[], skipped=[]))
                    if state == "after":
                        kits[selector]["kept"].append(row["slot"])
                        continue
                    if state == "other":
                        require(not strict, "%s %s: unknown input hash" % (selector, row["slot"]))
                        skipped.append("%s:%s" % (selector, row["slot"]))
                        kits[selector]["skipped"].append(row["slot"])
                        continue
                    key = (selector, row["slot"])
                    todo.append(row)
                    spans[key] = span
                    places[key] = (entry, chunk.offset)
        if todo:
            results = compile_slots(todo, spans, document, count=count, progress=progress)
            for row in todo:
                key = (row["selector"], row["slot"])
                new, _detail = results[key]
                require(len(new) == len(spans[key]) and new[:HEADER.size] == spans[key][:HEADER.size],
                        "%s %s: wrapper or span size changed" % key)
                require(sha(new) == row["after_sha256"], "%s %s: Studio compile differs from its output pin" % key)
            for row in todo:
                key = (row["selector"], row["slot"])
                new = results[key][0]
                entry, offset = places[key]
                segments = index.sub_extents(entry, offset, len(new))
                image.write_segments(segments, new)
                require(image.read_segments(segments) == new, "written span read-back differs")
                written += 1
                written_bytes += len(new)
                kits[row["selector"]]["written"].append(row["slot"])
    nothing_known = skipped and not written and not any(k["kept"] for k in kits.values())
    return dict(state="other_uniform" if nothing_known else "applied", written_spans=written, written_bytes=written_bytes, skipped_slots=skipped,
                kits=list(kits.values()))


def apply_relief_b81u(path, *, strict=False, progress=None):
    """Studio uniform finish pass for the b81-uniforms relief, after the uniform pass numbers: pinned spans only."""
    return apply_to_image(path, strict=strict, document=relief_b81u(), progress=progress)

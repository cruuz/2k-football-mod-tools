"""Repair the known SOFTDRINK Giants home shoulder-number mismatch.

The jersey's existing plain-white P8 mip chain is the donor. Only the ten
``an48`` through ``an57`` texture videos change; their native descriptors,
wrappers, allocations and names stay intact. ``hn`` names are helmet digits.
No artwork or retail pixels are distributed with this repair.

The Studio runs this after its uniform layers. Exact input/output pins limit
it to the known 18H0 recipe; retail and other user-authored kits are untouched.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from . import nfl2k5_bump_texture_writer as bump
from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba
from nfl_vc_lz_fill import rebuild_fixed_span_filled

RESOURCE = "18H0.IFF"
PINS = Path(__file__).resolve().parents[2] / "data/nfl2k5_nyg_numbers_pins.json"


def require(ok, message):
    if not ok:
        raise ValueError("Giants shoulder numbers: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pins():
    document = json.loads(PINS.read_text(encoding="utf-8"))
    require(document.get("schema") == "nfl2k5_nyg_numbers/v1" and
            document.get("resource") == RESOURCE and
            [p["digit"] for p in document["digits"]] == list(range(10)), "unexpected pins")
    return document


def digit_chunks(raw):
    """Resolve texture identity, never assume helmet/arm chunk ordering."""
    wanted = {prefix + str(48 + i) for prefix in ("", "an", "hn") for i in range(10)}
    result = {}
    for chunk in parse_chunks(raw):
        if chunk.kind != "TXTR":
            continue
        # Native kit TXTR system names are small, but decode through the codec
        # so compressed streams and descriptor pointers receive its checks.
        decoded, _ = decode_chunk(raw, chunk)
        texture = parse_texture(decoded, chunk)
        if texture.name in wanted:
            require(texture.name not in result, "duplicate digit texture " + texture.name)
            result[texture.name] = chunk
    require(set(result) == wanted, "missing jersey, helmet or shoulder digit textures")
    return result


def copy_digit_video(jersey_span, arm_span, digit):
    """Copy the donor's palette and all four native mips without resampling."""
    require(type(digit) is int and 0 <= digit < 10, "invalid digit")
    sources = []
    for span, name in ((jersey_span, str(48 + digit)), (arm_span, "an" + str(48 + digit))):
        chunks = parse_chunks(span)
        require(len(chunks) == 1 and chunks[0].end_offset == len(span), "expected one complete digit span")
        chunk = chunks[0]
        decoded, _ = decode_chunk(span, chunk)
        texture = parse_texture(decoded, chunk)
        require(chunk.kind == "TXTR" and chunk.compressed and texture.name == name,
                "wrong native digit family/name")
        require((texture.width, texture.height, texture.mip_levels, texture.format_name,
                 texture.pixel_offset, texture.palette_offset, chunk.system_bytes, chunk.video_bytes) ==
                (64, 64, 4, "P8", 0, 5440, 128, 6464), "unsupported digit storage")
        sources.append((chunk, decoded, texture))
    jc, jd, jt = sources[0]
    ac, ad, _at = sources[1]
    rgba = texture_to_rgba(jd, jc, jt)
    require(any(rgba[3::4]) and all(rgba[i:i + 3] == b"\xff\xff\xff"
            for i in range(0, len(rgba), 4) if rgba[i + 3]), "donor is not plain white")
    edited = ad[:ac.system_bytes] + jd[jc.system_bytes:]
    if edited == ad:
        return arm_span, dict(changed=False, wrapper_identical=True, system_identical=True,
                              donor_video_sha256=sha(jd[jc.system_bytes:]))
    # The ordinary greedy encoder alone overflows digit 4's allocation.
    # The existing optimal fallback fits it without changing pixels or scratch.
    rebuilt, fit = rebuild_fixed_span_filled(arm_span, edited, encoder="auto")
    require(len(rebuilt) == len(arm_span) and rebuilt[:32] == arm_span[:32], "wrapper/allocation changed")
    check, _ = decode_chunk(rebuilt, parse_chunks(rebuilt)[0])
    require(check == edited, "donor mip-chain round trip differs")
    return rebuilt, dict(changed=True, wrapper_identical=True, system_identical=True,
                         donor_video_sha256=sha(jd[jc.system_bytes:]), fit=asdict(fit))


def compile_resource(raw, *, strict=True):
    """Preflight all donors and destinations before compiling any replacement."""
    spec = pins()
    chunks = digit_chunks(raw)
    donors, before, after = [], [], []
    for p in spec["digits"]:
        j, a = chunks[str(48 + p["digit"])], chunks["an" + str(48 + p["digit"])]
        layout = (len(raw), j.offset, j.end_offset - j.offset, a.offset, a.end_offset - a.offset)
        expected = (spec["size"], p["donor_offset"], p["donor_length"], p["offset"], p["length"])
        donors.append(layout == expected and sha(raw[j.offset:j.end_offset]) == p["donor_sha256"])
        digest = sha(raw[a.offset:a.end_offset])
        before.append(digest == p["before_sha256"])
        after.append(digest == p["after_sha256"])
    supported = all(donors) and (all(before) or all(after))
    if not supported:
        # A known kit with only some of the ten digits changed is corruption or
        # an incomplete repair, not a separate user recipe.
        require(not strict and not any(before) and not any(after), "unknown or partially repaired input hashes")
        return [], dict(state="other_uniform", changed_bytes=0, parts=[])
    if all(after):
        return [], dict(state="applied", changed_bytes=0, parts=[])
    replacements, rows = [], []
    for p in spec["digits"]:
        j, a = chunks[str(48 + p["digit"])], chunks["an" + str(48 + p["digit"])]
        old = raw[a.offset:a.end_offset]
        new, detail = copy_digit_video(raw[j.offset:j.end_offset], old, p["digit"])
        require(sha(new) == p["after_sha256"], "Studio compile differs from output pin")
        replacements.append((a.offset, new))
        rows.append(dict(digit=p["digit"], native_name="an" + str(48 + p["digit"]),
                         chunk_index=a.index, offset=a.offset, length=len(new),
                         before_sha256=sha(old), after_sha256=sha(new),
                         changed_bytes=sum(x != y for x, y in zip(old, new)), **detail))
    return replacements, dict(state="applied", changed_bytes=sum(r["changed_bytes"] for r in rows), parts=rows)


def apply_to_image(path, *, strict=False):
    """Studio uniform finish pass; only fixed shoulder TXTR spans are written."""
    # Automatic recipe maintenance is irrelevant to images without a readable
    # NFL outer archive. Strict native repair must reject these inputs. Keep
    # this check read-only and do not swallow failures on identified kit data.
    try:
        with bump._Image.open(Path(path), writable=False) as source:
            index = bump._parsed_index(source)
    except (ValueError, OSError):
        if strict:
            raise
        return dict(state="other_image", resource=RESOURCE, written_spans=0,
                    written_bytes=0, changed_bytes=0, parts=[])
    entries = [e for e in index.entries if bump.logical_name_for(e.name_id) == RESOURCE]
    if not entries and not strict:
        return dict(state="other_uniform", resource=RESOURCE, written_spans=0,
                    written_bytes=0, changed_bytes=0, parts=[])
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        entries = [e for e in index.entries if bump.logical_name_for(e.name_id) == RESOURCE]
        require(len(entries) == 1, "home uniform resource absent or duplicated")
        entry = entries[0]
        raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
        replacements, receipt = compile_resource(raw, strict=strict)
        for offset, data in replacements:
            segments = index.sub_extents(entry, offset, len(data))
            image.write_segments(segments, data)
            require(image.read_segments(segments) == data, "written span read-back differs")
    return dict(resource=RESOURCE, written_spans=len(replacements),
                written_bytes=sum(len(data) for _, data in replacements), **receipt)

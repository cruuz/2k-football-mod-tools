#!/usr/bin/env python3
"""Beta 77 ALG: scoped native repair of the Allegiant Stadium stretch and grass in the nine s20 bundles of a v0.5 resource set.

Input is a directory of the nine extracted s20{d,a,n}{d,r,s}.iff bundles as SOFTDRINK 2K28 v0.5 ships them. The repair
owns three spans per bundle: the Allegiant stretch (the cityscape chunk's start to the intro cameras chunk's end, the same
offset and length as retail), the field scene's span and the divots span (pass 4: the turf colour). It refuses a span whose
SHA-256 is not the pinned v0.5 one (or the pinned output, which reports already_applied).

* The new stretch is the Studio's own compile of the model at this tree's pins (``data/nfl2k5_allegiant_model/pins.json``)
  from the supported retail bundle, with v0.5's three painted fan banners (banner_home_player, banner_home_team,
  banner_away_team) carried across byte for byte: each one's P8 mip chain and palette are copied from the v0.5 stadium
  scene into the same texture of the new scene, then the scene is refitted into the model's fixed span.
* The new field span is the v0.5 field repainted by Modern surfaces' own painter for the Allegiant row's design target
  (``design`` in data/nfl2k5_modern_surfaces/venues.json) under the rig, tint and settings v0.5 was built with (the
  manifest carries Modern colour's settings; the repair first proves they reproduce the v0.5 field from its measured
  broadcast target byte for byte): the colour map and the outside grass are repainted, the turf-coloured end-zone palette
  entries follow, and the scene is refitted into its fixed span. The divots palette's greens follow the new grass at the
  same luminance.

Every byte outside the three spans (the detail normal, the other TXTR chunks, Fldd) stays as the input has it. It never
opens or modifies an ISO.

    python3 tools/b77/alg_repair.py --input V05_DIR --output OUT_DIR --retail RETAIL_EXTRACTED
    python3 tools/b77/alg_repair.py --input V05_DIR --output OUT_DIR --retail RETAIL_EXTRACTED --record   (author time)
    python3 tools/b77/alg_repair.py --input V05_DIR --output OUT_DIR --record-grass --colour-lighting RECEIPT.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from mod_editor.core import nfl2k5_allegiant_model as lv  # noqa: E402
from mod_editor.core import nfl2k5_model_fan_art as fan  # noqa: E402
from mod_editor.core import nfl2k5_modern_color as colour  # noqa: E402
from mod_editor.core import nfl2k5_modern_metlife as ml  # noqa: E402
from mod_editor.core import nfl2k5_modern_surfaces as ms  # noqa: E402
from mod_editor.core import nfl2k5_modern_venues_2026 as mv  # noqa: E402

MANIFEST = Path(__file__).with_name("alg_repair_manifest.json")
SCHEMA = "b77_alg_repair/v2"
RECEIPT_SCHEMA = "b77_alg_native_scope/v1"
#: the SOFTDRINK 2K28 v0.5 disc the input bundles come from (read only)
V05_DISC_SHA256 = "5317a7b16558621e4030f3883789060f37a42af542df431a5d338b2ca1f3c76f"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        chunks = []
        while True:
            block = os.read(fd, 1 << 20)
            if not block:
                return b"".join(chunks)
            chunks.append(block)
    finally:
        os.close(fd)


def write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)


def outside_digest(data, start, end):
    return sha(bytes(data[:start]) + bytes(data[end:]))


def _pin(name):
    return next(p for p in lv.model_pins()["bundles"] if p["name"] == name)


def fan_payloads(bundle):
    """{fan key: (P8 bytes from the base level's pixels to the palette's end, RGBA)} of a bundle's stadium scene."""
    chunk = ml.bundle_scenes(bundle)["stadium"]
    rec, decoded = ml._scene(bundle, chunk)
    rows = mv.p8_rows(rec)
    out = {}
    for key in sorted(fan.FAN_KEYS):
        index = mv.find_stadium_texture(rec, key)
        if index is None:
            raise ValueError(f"the stadium scene has no {key} texture")
        row = rows[index]
        start = chunk.system_bytes + int(row["pixel_offset"])
        end = chunk.system_bytes + int(row["palette_offset"]) + 1024
        rgba, _ = ml.read_p8(decoded, chunk.system_bytes, row)
        out[key] = dict(bytes=bytes(decoded[start:end]), rgba=rgba, size=[int(row["width"]), int(row["height"])],
                        mip_levels=int(row["mip_levels"]), index=index)
    return out


def carry_fan_art(model, banners):
    """The model bundle with each fan banner's P8 allocation replaced by ``banners``' bytes; (bundle, textures)."""
    chunk = ml.bundle_scenes(model)["stadium"]
    rec, decoded = ml._scene(model, chunk)
    rows = mv.p8_rows(rec)
    edited = bytearray(decoded)
    ranges, textures = [], []
    for key in sorted(fan.FAN_KEYS):
        index = mv.find_stadium_texture(rec, key)
        row = rows[index]
        start = chunk.system_bytes + int(row["pixel_offset"])
        end = chunk.system_bytes + int(row["palette_offset"]) + 1024
        src = banners[key]
        if src["size"] != [int(row["width"]), int(row["height"])] or src["mip_levels"] != int(row["mip_levels"]) \
                or len(src["bytes"]) != end - start:
            raise ValueError(f"{key}: the v0.5 banner differs from the model's allocation")
        before, _ = ml.read_p8(decoded, chunk.system_bytes, row)
        edited[start:end] = src["bytes"]
        after, _ = ml.read_p8(edited, chunk.system_bytes, row)
        if not np.array_equal(after, src["rgba"]):
            raise ValueError(f"{key}: the carried banner reads back differently")
        ranges.append((start, end))
        textures.append(dict(key=key, texture=index, size=src["size"], mip_levels=src["mip_levels"], range=[start, end],
                             model_rgba_sha256=sha(before.tobytes()), carried_rgba_sha256=sha(after.tobytes()),
                             payload_sha256=sha(src["bytes"])))
    last, kept = 0, hashlib.sha256()
    for start, end in sorted(ranges):
        kept.update(decoded[last:start]); last = end
    kept.update(decoded[last:])
    span = ml.scene_span(model, chunk)
    fitted, fit = ml.fit_span(span, bytes(edited))
    if len(fitted) != len(span) or fitted[:32] != span[:32]:
        raise ValueError("the stadium scene's wrapper or fixed span changed")
    out = model[:chunk.offset] + fitted + model[chunk.offset + len(span):]
    back_chunk = ml.bundle_scenes(out)["stadium"]
    _rec, back = ml._scene(out, back_chunk)
    if back != bytes(edited):
        raise ValueError("the refitted stadium scene reads back differently")
    last, again = 0, hashlib.sha256()
    for start, end in sorted(ranges):
        again.update(back[last:start]); last = end
    again.update(back[last:])
    if again.hexdigest() != kept.hexdigest():
        raise ValueError("decoded bytes outside the three banner allocations changed")
    return out, dict(textures=textures, decoded_outside_banners_sha256=kept.hexdigest(),
                     decoded_model_sha256=sha(decoded), decoded_after_sha256=sha(back), compression=fit)


def compile_model(retail, name):
    """The Studio's compile of one bundle, checked against this tree's model pin."""
    _n, model, info = lv._compile((name, retail[name], retail[lv.dry_of(name)]))
    pin = _pin(name)
    start, end = pin["offset"], pin["offset"] + pin["length"]
    if sha(model[start:end]) != pin["model_sha256"]:
        raise ValueError(f"{name}: the compiled stretch is not this tree's model pin")
    return model, info


def _repair_stretch(data, name, doc, model=None):
    """(repaired bytes, receipt); refuses an unexpected stretch or a stretch that would not reproduce its pin."""
    if name not in doc["bundles"]:
        raise ValueError(f"unowned resource: {name}")
    want = doc["bundles"][name]
    if len(data) != want["size"]:
        raise ValueError(f"{name}: {len(data)} bytes, not {want['size']}")
    start, end = want["offset"], want["offset"] + want["length"]
    if lv.stretch(data) != (start, end):
        raise ValueError(f"{name}: the stretch moved")
    have = sha(data[start:end])
    base = dict(name=name, offset=start, length=want["length"], before_sha256=sha(data),
                outside_stretch_sha256=outside_digest(data, start, end))
    if have == want.get("after_stretch_sha256"):
        return data, dict(base, state="already_applied", after_sha256=sha(data), stretch_sha256=have)
    if have != want["before_stretch_sha256"]:
        raise ValueError(f"{name}: unexpected stretch SHA-256 {have}")
    if model is None:
        raise ValueError("compile the model from the supported retail bundles first")
    banners = fan_payloads(data)
    painted, detail = carry_fan_art(model, banners)
    new = painted[start:end]
    expected = want.get("after_stretch_sha256")
    if expected and sha(new) != expected:
        raise ValueError(f"{name}: the new stretch does not reproduce its pin")
    out = data[:start] + new + data[end:]
    if len(out) != len(data) or outside_digest(out, start, end) != base["outside_stretch_sha256"]:
        raise ValueError(f"{name}: bytes outside the stretch changed")
    if lv.stretch(out) != (start, end) or sha(out[start:end]) != sha(new):
        raise ValueError(f"{name}: read-back of the written stretch failed")
    return out, dict(base, state="repaired", after_sha256=sha(out), before_stretch_sha256=have,
                     after_stretch_sha256=sha(new), model_stretch_sha256=_pin(name)["model_sha256"],
                     scope="the Allegiant stretch (cityscape, stadium and intro cameras chunks); the field scene, TXTR "
                           "and Fldd chunks unchanged", **detail)


# --- pass 4: the turf colour -------------------------------------------------------------------------------------------
PREFIX = "s20"
LOOK = "grass_bermuda"
#: every s20 bundle is drawn under the dome rig: the Allegiant model turns the ROST row indoor (+0x18 = 1)
LIGHT = "dome"


def old_target():
    """The broadcast target v0.5's field was solved against: the row's measured broadcast, not its pass 4 design."""
    seen = ms.venues()[PREFIX]["broadcast"]
    base = ms.target_rgb(LOOK, seen["light"])
    return tuple(t * (m / max(1e-6, b)) for t, m, b in zip(ms.target_rgb(LOOK, LIGHT), seen["rgb"], base))


def new_target():
    """The pass 4 design target (the venue table's ``design``)."""
    return ms.venue_target(PREFIX, LOOK, LIGHT)


def _end_zone_follow(painted, rec, system, old_samples, old_mean, new_mean):
    """The turf-coloured entries of the end-zone palettes take the new turf colour, as the first pass of the painter does
    (here from the surfaced field's own turf, not the retail one); returns (bytes, entries changed)."""
    out, rows = bytearray(painted), ms._texture_rows(rec)
    envelope, done, changed = ms.turf_envelope(old_samples), set(), 0
    for name in ms.END_ZONE_MATERIALS:
        row = rows.get(name)
        if row is None:
            continue
        at = system + int(row["palette_offset"])
        if at in done:
            continue
        done.add(at)
        pal, n = ms.recolour_end_zone_palette(bytes(out[at:at + 1024]), envelope, old_mean, new_mean)
        out[at:at + 1024] = pal
        changed += n
    return bytes(out), changed


def retarget_field_span(span, *, rig, settings, tint, target):
    """(new field span of the same size, receipt): the surfaced field repainted for ``target`` and refitted."""
    tx, HEADER = ms._tools()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    rec, decoded = ml._scene(span, chunk)
    ms.require(rec["name"] == ms.FIELD_SCENE and ms.surfaced(decoded, rec), "the span is not a surfaced field scene")
    old_samples, old_mean = ms._current_turf(decoded, rec, chunk.system_bytes)
    attempts = []
    for optimal in (False, True):
        for detail, cap in ms.FIT_LADDER:
            painted, receipt = ms.paint_field(decoded, rec, chunk.system_bytes, look=LOOK, cls=LIGHT, rig=rig,
                                              colour_settings=settings, tint=tint, cap=cap, detail=detail, target=target)
            new_mean = tuple(min(255.0, v) for v in receipt["map_mean"])
            painted, entries = _end_zone_follow(painted, rec, chunk.system_bytes, old_samples, old_mean, new_mean)
            if painted == decoded:
                return bytes(span), dict(receipt, refit=False, palette_cap=cap, end_zone_entries=entries)
            try:
                rebuilt, fit = ms._fit(span, painted, optimal=optimal)
            except (tx.TxtrError, ValueError) as exc:
                attempts.append(f"detail {detail}, {cap} colours{' (optimal)' if optimal else ''}: {str(exc)[:120]}")
                continue
            back, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
            if back != painted or len(rebuilt) != len(span) or rebuilt[:HEADER.size] != span[:HEADER.size]:
                raise ValueError("field refit read-back differs")
            return rebuilt, dict(receipt, refit=True, palette_cap=cap, end_zone_entries=entries, old_map_mean=[round(v, 2) for v in old_mean],
                                 **fit)
    raise ValueError("the field does not fit its span: " + " | ".join(attempts))


def retint_divots_span(span, new_grass):
    """The divots palette's grass-coloured entries (hue 60 to 160, saturation over 0.15, as the painter picks them) take
    the new grass colour at the luminance they had; every other entry is untouched."""
    tx, HEADER = ms._tools()
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    output, info0 = tx.decode_chunk(span, chunk)
    info = tx.parse_texture(output, chunk)
    edited = bytearray(output)
    at = chunk.system_bytes + info.palette_offset
    gl = max(1e-6, 0.299 * new_grass[0] + 0.587 * new_grass[1] + 0.114 * new_grass[2])
    changed = 0
    for i in range(256):
        b, g, r, a = output[at + i * 4:at + i * 4 + 4]
        h, sat, _v = ms.colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if not (60 <= h * 360 <= 160 and sat > 0.15):
            continue
        k = min(1.6 * 0.92, (0.299 * r + 0.587 * g + 0.114 * b) / gl)
        new = bytes(int(min(255, max(0, round(c * k)))) for c in (new_grass[2], new_grass[1], new_grass[0]))
        if new != bytes((b, g, r)):
            edited[at + i * 4:at + i * 4 + 3] = new
            changed += 1
    if bytes(edited) == output:
        return bytes(span), dict(entries=0)
    rebuilt, _fit = colour.fit_fixed_span(span, bytes(edited))
    check, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
    if check != bytes(edited) or len(rebuilt) != len(span):
        raise ValueError("divots refit read-back differs")
    return rebuilt, dict(entries=changed)


def grass_settings(doc):
    """Modern colour's settings the v0.5 field was graded with (carried in the manifest)."""
    settings = doc["colour_settings"]
    if colour.settings_id(settings) != doc["colour_settings_sha256"]:
        raise ValueError("the manifest's colour settings do not match their pinned digest")
    return settings


def _grass_sites(data, name):
    sites = ms.bundle_sites(data)
    return sites["field"], sites["divots"], ms.field_tint(data)


def repair_grass(data, name, doc):
    """(bytes, receipt) for one bundle's field and divots spans; refuses unexpected spans, and refuses a field that the
    recorded settings, rig and measured target do not reproduce byte for byte."""
    want = doc["bundles"][name]["grass"]
    (f_at, f_len), (d_at, d_len), tint = _grass_sites(data, name)
    if (f_at, f_len, d_at, d_len) != (want["field_offset"], want["field_length"], want["divots_offset"], want["divots_length"]):
        raise ValueError(f"{name}: the field or divots span moved")
    field, divots = bytes(data[f_at:f_at + f_len]), bytes(data[d_at:d_at + d_len])
    have = (sha(field), sha(divots))
    base = dict(field_offset=f_at, field_length=f_len, divots_offset=d_at, divots_length=d_len)
    if have == (want.get("field_after_sha256"), want.get("divots_after_sha256")):
        return data, dict(base, state="already_applied", field_sha256=have[0], divots_sha256=have[1])
    if have != (want["field_before_sha256"], want["divots_before_sha256"]):
        raise ValueError(f"{name}: unexpected field or divots span SHA-256 {have}")
    settings = grass_settings(doc)
    rig = ms.rig_name(LIGHT, name[3])
    again, _ = ms.field_span(field, look=LOOK, cls=LIGHT, rig=rig, colour_settings=settings, tint=tint, target=old_target())
    if again != field:
        raise ValueError(f"{name}: the recorded settings and measured target do not reproduce the v0.5 field")
    new_field, frec = retarget_field_span(field, rig=rig, settings=settings, tint=tint, target=new_target())
    old_mean = frec["old_map_mean"]
    new_grass = [v * (t / 255.0) for v, t in zip(frec["map_mean"], tint)]
    new_divots, drec = retint_divots_span(divots, new_grass)
    out = bytearray(data)
    out[f_at:f_at + f_len] = new_field
    out[d_at:d_at + d_len] = new_divots
    if len(out) != len(data) or bytes(out[f_at + f_len:d_at]) != bytes(data[f_at + f_len:d_at]):
        raise ValueError(f"{name}: bytes outside the field and divots spans changed")
    if sha(bytes(out[f_at:f_at + f_len])) != want.get("field_after_sha256", sha(new_field)) \
            or sha(bytes(out[d_at:d_at + d_len])) != want.get("divots_after_sha256", sha(new_divots)):
        raise ValueError(f"{name}: the new field or divots span does not reproduce its pin")
    return bytes(out), dict(base, state="repaired", field_before_sha256=have[0], divots_before_sha256=have[1],
                            field_after_sha256=sha(new_field), divots_after_sha256=sha(new_divots),
                            target_before=[round(v, 2) for v in old_target()], target_after=[round(v, 2) for v in new_target()],
                            map_mean_before=[round(v, 2) for v in old_mean], map_mean_after=frec["map_mean"],
                            outside_mean_after=frec["outside_mean"], end_zone_entries=frec["end_zone_entries"],
                            divots_entries=drec["entries"], palette_cap=frec["palette_cap"], pattern_detail=frec["pattern_detail"])


def repair_bundle(data, name, doc, model=None):
    """(repaired bytes, receipt): the stretch, then the field and divots spans (each skipped when already applied)."""
    if name not in doc["bundles"]:
        raise ValueError(f"unowned resource: {name}")
    stretch_out, stretch = _repair_stretch(data, name, doc, model)
    grass_out, grass = repair_grass(stretch_out, name, doc)
    state = "already_applied" if stretch["state"] == grass["state"] == "already_applied" else "repaired"
    receipt = dict(stretch, state=state, grass=grass, before_sha256=sha(data), after_sha256=sha(grass_out))
    if grass["state"] == "repaired" or stretch["state"] == "repaired":
        receipt["scope"] = ("the Allegiant stretch (cityscape, stadium and intro cameras chunks), the field scene span and the "
                            "divots span; the detail normal, the other TXTR chunks and Fldd unchanged")
    return grass_out, receipt


def record_grass(input_dir, colour_lighting):
    """Author time: pin the colour settings and each bundle's v0.5 field and divots spans, then the repaired ones."""
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    receipt = json.loads(Path(colour_lighting).read_text(encoding="utf-8"))
    settings = receipt["settings"]
    if colour.settings_id(settings) != receipt["settings_sha256"]:
        raise SystemExit("the colour-lighting receipt's settings do not match its digest")
    doc["schema"] = SCHEMA
    doc["colour_settings"], doc["colour_settings_sha256"] = settings, receipt["settings_sha256"]
    for name in lv.VARIANTS:
        data = read(Path(input_dir) / name)
        (f_at, f_len), (d_at, d_len), _tint = _grass_sites(data, name)
        doc["bundles"][name]["grass"] = dict(
            field_offset=f_at, field_length=f_len, divots_offset=d_at, divots_length=d_len,
            field_before_sha256=sha(data[f_at:f_at + f_len]), divots_before_sha256=sha(data[d_at:d_at + d_len]))
        _out, receipt_g = repair_grass(data, name, doc)
        doc["bundles"][name]["grass"].update(field_after_sha256=receipt_g["field_after_sha256"],
                                             divots_after_sha256=receipt_g["divots_after_sha256"])
        print(name, receipt_g["state"], receipt_g["field_after_sha256"][:16], "map", receipt_g["map_mean_after"],
              "end zone entries", receipt_g["end_zone_entries"], "divots entries", receipt_g["divots_entries"], flush=True)
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", required=True, type=Path, help="the nine v0.5 s20 bundles")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--retail", type=Path, help="supported unmodified retail image or extracted archive (not needed by --record-grass)")
    parser.add_argument("--record", action="store_true", help="author time: pin the v0.5 input and the output stretches")
    parser.add_argument("--record-grass", action="store_true", help="author time: pin the colour settings and the field and divots spans (no outputs)")
    parser.add_argument("--colour-lighting", type=Path, help="with --record-grass: the v0.5 build's colour-lighting receipt")
    args = parser.parse_args(argv)
    if args.input.resolve() == args.output.resolve():
        raise SystemExit("use a separate output directory")
    if args.record_grass:
        if not args.colour_lighting:
            raise SystemExit("--record-grass needs --colour-lighting")
        return record_grass(args.input, args.colour_lighting)
    if args.record:
        doc = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {}
        grass = {n: b["grass"] for n, b in doc.get("bundles", {}).items() if "grass" in b}
        doc.update(schema=SCHEMA, source=f"SOFTDRINK 2K28 v0.5 (2026-10-06) disc sha256 {V05_DISC_SHA256}", bundles={})
        for name in lv.VARIANTS:
            data = read(args.input / name)
            start, end = lv.stretch(data)
            pin = _pin(name)
            if (start, end - start) != (pin["offset"], pin["length"]) or len(data) != pin["size"]:
                raise SystemExit(f"{name}: the input's stretch is not the model's")
            doc["bundles"][name] = dict(size=len(data), offset=start, length=end - start,
                                        before_stretch_sha256=sha(data[start:end]))
            if name in grass:
                doc["bundles"][name]["grass"] = grass[name]
    else:
        doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
        if doc.get("schema") != SCHEMA:
            raise SystemExit("unexpected repair manifest schema")
    if args.retail is None:
        raise SystemExit("--retail is required")
    retail = None
    args.output.mkdir(parents=True, exist_ok=True)
    receipts = []
    for name in sorted(doc["bundles"]):
        data = read(args.input / name)
        want = doc["bundles"][name]
        start, end = want["offset"], want["offset"] + want["length"]
        model = None
        if sha(data[start:end]) != want.get("after_stretch_sha256"):
            if retail is None:
                retail = lv.read_retail(args.retail)
            model, _info = compile_model(retail, name)
        out, receipt = repair_bundle(data, name, doc, model)
        if args.record:
            want["after_stretch_sha256"] = receipt["after_stretch_sha256"]
        target = args.output / name
        if target.exists() and read(target) != out:
            raise SystemExit(f"refusing to replace an unrelated output {target}")
        write(target, out)
        receipts.append(receipt)
        print(name, receipt["state"], receipt.get("after_stretch_sha256", receipt.get("stretch_sha256")), flush=True)
    if args.record:
        with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    with open(args.output / "scope_receipt.json", "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(dict(schema=RECEIPT_SCHEMA, model_pins_sha256=sha(lv.PINS_PATH.read_bytes()),
                                bundles=receipts), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

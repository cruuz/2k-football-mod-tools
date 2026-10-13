#!/usr/bin/env python3
"""st1: field shadows cast by the stadium each afternoon bundle really carries, and MetLife's afternoon field brightness,
written natively into a built SOFTDRINK disc (fixed-span writes inside the owned bundles; nothing else moves).

The Studio fix:

* ``mod_editor/core/nfl2k5_stadium_shadow.py`` casts a bundle's stadium scene onto the field under the venue's retail
  sun (``data/nfl2k5_stadium_shadow/venues.json``) and writes the retail-format ``shadow`` TXTR inside its span; the
  MetLife model's compile (``nfl2k5_metlife_model.model_bundle``) calls it, and its pins carry the shadow site;
* ``data/nfl2k5_modern_surfaces/venues.json`` gives MetLife's rows the afternoon response measured in game, so Modern
  playing surfaces paints the s18ad and s19ad fields to their target.

This tool carries exactly that into a disc built before the fix. For every owned bundle it computes the new bytes with
the Studio's own functions (the shadow from the stadium scene on the disc, the field with Modern surfaces' painter under
Modern colour's settings from tools/b77/alg_repair_manifest.json), requires them to equal the pins, and writes only the
owned spans (the shadow TXTR span, the field SCNE span).

    record  --disc BASE.iso --out tools/b77/st1_pins.json          author time: pin inputs, outputs and spans
    apply   --disc COPY.iso --pins PINS --receipt JSON              write in place (refuses unpinned bundle bytes)
    scope   --before BASE.iso --after COPY.iso --disc-receipt JSON --receipt JSON
    studio  --disc COPY.iso --retail RETAIL.iso --pins PINS --receipt JSON   the Studio's own compile from retail agrees

Every step refuses on a pin mismatch, verifies the whole batch in memory before writing, reads back, and a second
``apply`` writes 0 bytes.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PINS_SCHEMA = "b77_st1_pins/v1"
ALG_MANIFEST = Path(__file__).with_name("alg_repair_manifest.json")
#: the bundles this repair owns and why: MetLife's afternoon dry bundles (shadow + field)
BUNDLES = {"s18ad.iff": ("shadow", "field"), "s19ad.iff": ("shadow", "field")}
INDOOR = {"s18": False, "s19": False}


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def require(ok, message):
    if not ok:
        raise SystemExit(f"st1_repair: REFUSED: {message}")


def read_file(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        parts = []
        while True:
            block = os.read(fd, 1 << 20)
            if not block:
                return b"".join(parts)
            parts.append(block)
    finally:
        os.close(fd)


def write_json(path, doc):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(doc, indent=1) + "\n")


def colour_settings():
    """Modern colour's settings the disc was graded with (candidate J's, carried and pinned by the alg manifest)."""
    from mod_editor.core import nfl2k5_modern_color as colour
    doc = json.loads(read_file(ALG_MANIFEST).decode("utf-8"))
    settings = doc["colour_settings"]
    require(colour.settings_id(settings) == doc["colour_settings_sha256"], "the manifest's colour settings changed")
    return settings


def spans_of(bundle, kinds):
    """{kind: (offset, length)} of the owned spans of one bundle."""
    from mod_editor.core import nfl2k5_modern_surfaces as ms
    from mod_editor.core import nfl2k5_stadium_shadow as shadow
    out = {}
    if "shadow" in kinds:
        found = shadow.shadow_chunk(bundle)
        require(found is not None, "no shadow texture")
        out["shadow"] = (found[0].offset, 32 + found[0].stored_size)
    if "field" in kinds:
        out["field"] = ms.bundle_sites(bundle)["field"]
    return out


def repair_bundle(name, data, settings):
    """(new bytes, receipt): the shadow cast from the bundle's own stadium scene, then Modern surfaces' painter."""
    from mod_editor.core import nfl2k5_modern_surfaces as ms
    from mod_editor.core import nfl2k5_stadium_shadow as shadow
    kinds = BUNDLES[name]
    prefix = name[:3]
    spans = spans_of(data, kinds)
    out = bytes(data)
    receipt = dict(name=name)
    if "shadow" in kinds:
        out, receipt["shadow"] = shadow.bundle_shadow(out, prefix)
    if "field" in kinds:
        out, surf = ms.surface_bundle(out, name, indoor=INDOOR[prefix], colour_settings=settings)
        receipt["surfaces_edits"] = [dict(kind=e["kind"], offset=e["offset"], size=e["size"]) for e in surf["edits"]]
        receipt["field"] = {k: surf["field"].get(k) for k in ("target", "response", "map_mean", "outside_mean", "palette_cap",
                                                             "pattern_detail", "refit")}
        require({e["kind"] for e in surf["edits"]} <= {"field"}, f"{name}: Modern surfaces changed more than the field")
    require(len(out) == len(data), f"{name}: size changed")
    # every changed byte lies inside an owned span
    owned = sorted(spans.values())
    i = 0
    view_a, view_b = memoryview(data), memoryview(out)
    for at, length in owned:
        require(view_a[i:at] == view_b[i:at], f"{name}: bytes outside the owned spans changed")
        i = at + length
    require(view_a[i:] == view_b[i:], f"{name}: bytes after the owned spans changed")
    receipt["spans"] = {k: dict(offset=at, length=length, before_sha256=sha(data[at:at + length]),
                                after_sha256=sha(out[at:at + length])) for k, (at, length) in spans.items()}
    receipt.update(before_sha256=sha(data), after_sha256=sha(out))
    return out, receipt


def _entries(archive):
    from mod_editor.core import nfl2k5_modern_metlife as ml
    byid = {e.name_id: e for e in archive.entries}
    out = {}
    for name in BUNDLES:
        e = byid.get(ml.name_id(name))
        require(e is not None, f"{name}: not in the archive")
        out[name] = e
    return out


def cmd_record(a):
    from mod_editor.core import nfl2k5_modern_metlife as ml
    settings = colour_settings()
    rows = []
    with ml._outer_image()(str(a.disc)) as archive:
        for name, e in _entries(archive).items():
            data = archive.read(e.virtual_offset, e.size)
            out, rec = repair_bundle(name, data, settings)
            again, _ = repair_bundle(name, out, settings)
            require(again == out, f"{name}: the repair is not idempotent")
            rows.append(dict(name=name, outer_index=e.index, name_id=e.name_id, size=e.size, input_sha256=sha(data),
                             output_sha256=sha(out), spans=rec["spans"], shadow_sun=rec.get("shadow", {}).get("sun"),
                             field=rec.get("field")))
            print(name, "pinned", sha(data)[:12], "->", sha(out)[:12], flush=True)
    write_json(a.out, dict(schema=PINS_SCHEMA, input_disc=dict(name=Path(a.disc).name, sha256=a.disc_sha256),
                           colour_settings_sha256=json.loads(read_file(ALG_MANIFEST))["colour_settings_sha256"],
                           bundles=rows))
    return 0


def load_pins(path):
    doc = json.loads(read_file(path).decode("utf-8"))
    require(doc.get("schema") == PINS_SCHEMA, "unexpected pins schema")
    return {r["name"]: r for r in doc["bundles"]}, doc


def cmd_apply(a):
    from mod_editor.core import nfl2k5_modern_metlife as ml
    rows, doc = load_pins(a.pins)
    settings = colour_settings()
    plan = []
    with ml._outer_image()(str(a.disc)) as archive:
        for name, e in _entries(archive).items():
            r = rows[name]
            require(e.index == r["outer_index"] and e.size == r["size"], f"{name}: archive entry differs")
            data = archive.read(e.virtual_offset, e.size)
            have = sha(data)
            require(have in (r["input_sha256"], r["output_sha256"]), f"{name}: the bundle is neither the pinned input "
                    "nor the pinned output")
            out, rec = repair_bundle(name, data, settings)
            require(sha(out) == r["output_sha256"], f"{name}: the Studio functions no longer give the pinned output")
            plan.append((name, e, data, out, rec))
    # the whole batch is verified in memory; only now write the owned spans
    receipts, written = [], 0
    with ml._outer_image()(str(a.disc), writable=True) as archive:
        for name, e, data, out, rec in plan:
            ranges, wrote = [], 0
            for kind, span in sorted(rec["spans"].items()):
                at, length = span["offset"], span["length"]
                new = out[at:at + length]
                if data[at:at + length] != new:
                    archive.write(e.virtual_offset + at, new)
                    wrote += length
                require(archive.read(e.virtual_offset + at, length) == new, f"{name} {kind}: read-back differs")
                ranges += [(pack.image_offset + o, pack.image_offset + o + n)
                           for pack, o, n in archive._segments(e.virtual_offset + at, length)]
            back = archive.read(e.virtual_offset, e.size)
            require(back == out, f"{name}: bundle read-back differs")
            written += wrote
            receipts.append(dict(name=name, outer_index=e.index, virtual_offset=e.virtual_offset, size=e.size,
                                 before_sha256=sha(data), after_sha256=sha(out), already_applied=data == out,
                                 bytes_written=wrote, owned_image_ranges=ranges, spans=rec["spans"],
                                 shadow=rec.get("shadow"), field=rec.get("field")))
    write_json(a.receipt, dict(schema="b77_st1_disc_write/v1", disc=str(a.disc), pins_sha256=sha(read_file(a.pins)),
                               bundles=receipts, bytes_written=written))
    print("DISC", len(receipts), "bundles,", sum(not r["already_applied"] for r in receipts), "written,", written, "bytes")
    return 0


def cmd_scope(a):
    """Byte comparison of two disc images: every differing byte must fall inside an owned span."""
    import numpy as np
    disc_rec = json.loads(read_file(a.disc_receipt).decode("utf-8"))
    owned = sorted((s, e, b["name"]) for b in disc_rec["bundles"] for s, e in b["owned_image_ranges"])
    require(os.path.getsize(a.before) == os.path.getsize(a.after), "disc sizes differ")
    diffs, block = [], 1 << 24
    with open(a.before, "rb") as fb, open(a.after, "rb") as fa:
        pos = 0
        while True:
            x, y = fb.read(block), fa.read(block)
            if not x:
                break
            if x != y:
                d = np.flatnonzero(np.frombuffer(x, np.uint8) != np.frombuffer(y, np.uint8))
                start = prev = int(d[0])
                for k in d[1:].tolist():
                    if k != prev + 1:
                        diffs.append((pos + start, pos + prev + 1))
                        start = k
                    prev = k
                diffs.append((pos + start, pos + prev + 1))
            pos += len(x)
    starts = [s for s, _e, _n in owned]
    outside, per_bundle = [], {}
    for s, e in diffs:
        i = bisect.bisect_right(starts, s) - 1
        if i < 0 or not (owned[i][0] <= s and e <= owned[i][1]):
            outside.append((s, e))
        else:
            per_bundle[owned[i][2]] = per_bundle.get(owned[i][2], 0) + (e - s)
    doc = dict(schema="b77_st1_disc_scope/v1", before=str(a.before), after=str(a.after), before_sha256=a.before_sha256,
               after_sha256=a.after_sha256, image_size=os.path.getsize(a.after), differing_runs=len(diffs),
               differing_bytes=sum(e - s for s, e in diffs), owned_ranges=len(owned),
               owned_bytes=sum(e - s for s, e, _n in owned), bytes_outside_owned=sum(e - s for s, e in outside),
               outside_runs=outside[:50], changed_bytes_per_bundle=per_bundle)
    write_json(a.receipt, doc)
    print("DIFF runs", len(diffs), "bytes", doc["differing_bytes"], "outside owned", doc["bytes_outside_owned"])
    require(not outside, "bytes changed outside the owned spans")
    return 0


def cmd_studio(a):
    """The Studio's own compile from the retail disc gives the shadow span on the disc, and Modern surfaces' painter
    leaves the disc's field as it is (it is the painter's own output for these settings)."""
    from mod_editor.core import nfl2k5_metlife_model as mm
    from mod_editor.core import nfl2k5_modern_metlife as ml
    from mod_editor.core import nfl2k5_modern_surfaces as ms
    rows, _doc = load_pins(a.pins)
    settings = colour_settings()
    retail = mm._read_retail(a.retail)
    pins = {p["name"]: p for p in mm.model_pins()["bundles"]}
    checks = []
    with ml._outer_image()(str(a.disc)) as archive:
        for name, e in _entries(archive).items():
            data = archive.read(e.virtual_offset, e.size)
            require(sha(data) == rows[name]["output_sha256"], f"{name}: the disc does not carry the repair")
            skin = mm.skin_bundle(retail[name], name, retail[ml.dry_name(name)])
            model, info = mm.model_bundle(skin, name)
            span = rows[name]["spans"]["shadow"]
            studio_shadow = model[span["offset"]:span["offset"] + span["length"]]
            disc_shadow = data[span["offset"]:span["offset"] + span["length"]]
            off, stretch = mm._stretch(model)
            painted, _rec = ms.surface_bundle(data, name, indoor=INDOOR[name[:3]], colour_settings=settings)
            row = dict(name=name, shadow_equal=studio_shadow == disc_shadow, shadow_sha256=sha(disc_shadow),
                       shadow_pin_equal=sha(studio_shadow) == pins[name]["shadow"]["model_sha256"],
                       stadium_stretch_equal=data[off:off + len(stretch)] == stretch,
                       surfaces_painter_leaves_it=painted == data)
            require(all(v for k, v in row.items() if k.endswith(("_equal", "_leaves_it"))), f"{name}: {row}")
            checks.append(row)
            print(name, row, flush=True)
    write_json(a.receipt, dict(schema="b77_st1_studio_equality/v1", disc=str(a.disc), retail=str(a.retail),
                               bundles=checks))
    print("VERIFIED", len(checks))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("record"); s.add_argument("--disc", required=True); s.add_argument("--out", required=True)
    s.add_argument("--disc-sha256", required=True)
    s = sub.add_parser("apply"); s.add_argument("--disc", required=True); s.add_argument("--pins", required=True)
    s.add_argument("--receipt", required=True)
    s = sub.add_parser("scope"); s.add_argument("--before", required=True); s.add_argument("--after", required=True)
    s.add_argument("--disc-receipt", required=True); s.add_argument("--receipt", required=True)
    s.add_argument("--before-sha256", default=""); s.add_argument("--after-sha256", default="")
    s = sub.add_parser("studio"); s.add_argument("--disc", required=True); s.add_argument("--retail", required=True)
    s.add_argument("--pins", required=True); s.add_argument("--receipt", required=True)
    a = p.parse_args(argv)
    return dict(record=cmd_record, apply=cmd_apply, scope=cmd_scope, studio=cmd_studio)[a.cmd](a) or 0


if __name__ == "__main__":
    raise SystemExit(main())

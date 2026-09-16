"""Modern Arrowhead (experimental): the Kansas City home stadium packages toward the 2026 look.

Nine archive bundles (``s13{d,a,n}{d,r,s}.iff``: day, afternoon, night; dry, rain, snow) carry the
Arrowhead field scene and stadium scene. This option replaces fourteen embedded P8 textures in each
bundle with authored art from ``data/nfl2k5_modern_arrowhead``: the CHIEFS end zones and centre mark
on the field scene; red seats, red wall pads with the gold rail, the fascia boards, the wall ads, the
fan banners and the tarps on the stadium scene. Each SCNE is refit inside its fixed VC-LZ span with
the retail wrapper untouched (the same fixed-allocation compiler the Stadium Studio route uses), and
every bundle carries retail and modern pins so the build refuses foreign bundles. Crowd people, the
grass colour map, the field bump map, lights, walls and props are untouched. EXPERIMENTAL and
UNWITNESSED in game: the writes are proved by byte receipts and decoder read-back only.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import zlib
from pathlib import Path

OWNER = "nfl2k5_modern_arrowhead"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_CAPTION = "Modern Arrowhead (experimental)"
HELP_TEXT = (
    "The Kansas City home packages (day, afternoon, night; dry, rain, snow) take a 2026 look: red seats, "
    "red wall pads with the gold rail, current fascia boards and wall ads, CHIEFS end zones with the mark at "
    "both ends, the current mark at midfield, and Chiefs fan banners. Fourteen textures per package are "
    "refit inside their fixed spans; crowd figures, grass, lights and geometry stay retail. Off in every "
    "preset; needs a disc image. Appearance in game is unwitnessed."
)
ROOT = Path(__file__).resolve().parents[2]
ART_DIR = ROOT / "data" / "nfl2k5_modern_arrowhead"
PINS_PATH = ROOT / "data" / "nfl2k5_modern_arrowhead_pins.json"
PINS_SCHEMA = "nfl2k5_modern_arrowhead_pins/v1"
VENUE_PREFIX = "s13"  # Arrowhead Stadium in the retail STRG venue table
VARIANTS = tuple(f"{VENUE_PREFIX}{tod}{weather}.iff" for tod in "dan" for weather in "drs")
# (scene name, material name) -> authored PNG; several materials share one texture (end zones N/S, seats 01/02).
TARGETS = {
    ("field", "endzone_N_L"): "endzone_L.png", ("field", "endzone_N_M"): "endzone_M.png",
    ("field", "endzone_N_R"): "endzone_R.png", ("field", "center_logo"): "center_logo.png",
    ("stadium", "seat03"): "seat03.png", ("stadium", "seat01"): "seat_rows.png",
    ("stadium", "yardside"): "yardside.png", ("stadium", "yardfront"): "yardfront.png",
    ("stadium", "ad01"): "ad01.png", ("stadium", "banner_corp"): "banner_corp.png",
    ("stadium", "banner_home_team"): "banner_home_team.png",
    ("stadium", "banner_home_player"): "banner_home_player.png",
    ("stadium", "banner_away_team"): "banner_away_team.png", ("stadium", "tarpGreen"): "tarp_red.png",
}
SCENES = ("field", "stadium")


class ModernArrowheadError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ModernArrowheadError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def name_id(filename):
    """The engine's archive name id: CRC-32 of the upper-case UTF-16LE filename."""
    return zlib.crc32(filename.upper().encode("utf-16le")) & 0xFFFFFFFF


def _tools():
    tools = ROOT / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import nfl_txtr as tx  # noqa: E402
    import nfl_scne_inventory as inv  # noqa: E402
    from nfl_scene_probe import ResourceRecord, HEADER  # noqa: E402
    from . import nfl2k5_stadium_texture_writer as stw
    return tx, inv, ResourceRecord, HEADER, stw


def _outer_image():
    from . import nfl2k5_roster_records as rr
    return rr._outer_image()


# --- art -----------------------------------------------------------------------

_ART = {}


def art_rgba(filename, width, height):
    """Exact-size RGBA8 bytes of one authored PNG (cached)."""
    key = (filename, width, height)
    if key not in _ART:
        from PIL import Image
        path = ART_DIR / filename
        require(path.is_file(), f"Modern Arrowhead art is missing: {filename}")
        with Image.open(path) as image:
            require(image.size == (width, height),
                    f"{filename} is {image.size[0]}x{image.size[1]}, the texture needs {width}x{height}")
            _ART[key] = image.convert("RGBA").tobytes()
    return _ART[key]


def art_pins():
    return {p.name: sha(p.read_bytes()) for p in sorted(ART_DIR.glob("*.png"))}


# --- scenes ------------------------------------------------------------------------

def _scene(data, chunk):
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    record = ResourceRecord(outer_index=0, outer_id="", outer_size=len(data), chunk_index=chunk.index,
                            chunk_offset=chunk.offset, kind=chunk.kind, stored_size=chunk.stored_size,
                            word_08=chunk.system_bytes, word_0c=chunk.video_bytes, word_10=chunk.compression_magic,
                            word_14=chunk.overlap_scratch_bytes)
    decoded, _ = tx.decode_chunk(data, chunk)
    rec, _names, _maps, _sample = inv.parse_scene(chunk.index, record, decoded, {})
    return rec, decoded


def scene_targets(rec):
    """{texture index: (PNG name, row)} for the materials this option replaces in one scene."""
    scene = rec.get("name")
    materials = {m["name"]: m for m in rec.get("materials", ())}
    rows = {int(r["index"]): r for r in rec.get("embedded_textures", ())}
    out = {}
    for (scene_name, material), png in TARGETS.items():
        if scene_name != scene or material not in materials:
            continue
        index = int(materials[material]["texture_index"])
        row = rows.get(index)
        require(row is not None and row.get("format_name") == "P8"
                and row.get("conversion_status") == "base_level_supported", f"{material}: not an editable P8 texture")
        out.setdefault(index, (png, row))
    return out


def paint_scene(data, chunk):
    """Author the decoded textures; the caller owns compression and wrappers."""
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    rec, decoded = _scene(data, chunk)
    span = bytes(data[chunk.offset:chunk.offset + HEADER.size + chunk.stored_size])
    targets = scene_targets(rec)
    require(targets, f"{rec.get('name')}: no target textures in this scene")
    edited = bytearray(decoded)
    system = int(rec["system_bytes"])
    receipt = []
    for index, (png, row) in sorted(targets.items()):
        width, height, levels = int(row["width"]), int(row["height"]), int(row["mip_levels"])
        dims = stw._mip_dimensions(width, height, levels)
        rgba = art_rgba(png, width, height)
        mips = stw._generate_dynamic_mips(rgba, dims)
        palette, linear, quant = stw.quantize_levels(mips)
        swizzled = b"".join(stw.swizzle_2d(indices, level.width, level.height, 1) for level, indices in zip(mips, linear))
        palette_payload = stw.palette_bytes(palette)
        pixel_start = system + int(row["pixel_offset"])
        palette_start = system + int(row["palette_offset"])
        require(len(swizzled) == sum(w * h for w, h in dims) and len(palette_payload) == stw.PALETTE_BYTES
                and palette_start == pixel_start + len(swizzled) and palette_start + stw.PALETTE_BYTES <= len(edited),
                f"{png}: allocation mismatch")
        edited[pixel_start:pixel_start + len(swizzled)] = swizzled
        edited[palette_start:palette_start + stw.PALETTE_BYTES] = palette_payload
        receipt.append(dict(texture=index, png=png, material=row.get("mapped_material_names"),
                            palette_entries=len(palette), size=[width, height], mips=levels))
    return bytes(edited), receipt


def modern_scene_span(data, chunk):
    """Refit authored art in its existing scene allocation."""
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    rec, decoded = _scene(data, chunk)
    span = bytes(data[chunk.offset:chunk.offset + HEADER.size + chunk.stored_size])
    _, info = stw.decompress_vc_lz(span[HEADER.size:], len(decoded))
    consumed = info.consumed_bytes
    opaque_tail = span[HEADER.size + consumed:]
    edited, receipt = paint_scene(data, chunk)
    fixed = stw._rebuild_vc_lz_fixed_span(bytes(edited), span[:HEADER.size], opaque_tail,
                                          consumed_cap=consumed, scratch_cap=stw.SCNE_OBSERVED_SCRATCH_MAX,
                                          template_stream_prefix=span[HEADER.size:HEADER.size + 9])
    require(len(fixed.span) == len(span) and fixed.span[:HEADER.size - 12] == span[:HEADER.size - 12],
            "refit span changed its wrapper")
    return fixed.span, dict(scene=rec.get("name"), textures=receipt, encoded_bytes=fixed.encoded_bytes,
                            consumed_cap=consumed, scratch_after=fixed.scratch_after)


def bundle_plan(data):
    """[(scene name, chunk)] for the field and stadium scenes of one bundle."""
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    out = []
    for chunk in tx.parse_chunks(data, allow_trailing=True):
        if chunk.kind != "SCNE":
            continue
        rec, _decoded = _scene(data, chunk)
        if rec.get("name") in SCENES:
            out.append((rec["name"], chunk))
    require(len(out) == 2, "bundle lacks its field or stadium scene")
    return out


def modern_bundle(data):
    """(modern bundle bytes, edits) for one retail Arrowhead bundle."""
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    out = bytearray(data)
    edits = []
    for name, chunk in bundle_plan(data):
        size = HEADER.size + chunk.stored_size
        before = bytes(data[chunk.offset:chunk.offset + size])
        after, receipt = modern_scene_span(data, chunk)
        out[chunk.offset:chunk.offset + size] = after
        edits.append(dict(kind=name, offset=chunk.offset, size=size, before_sha256=sha(before), after_sha256=sha(after), **receipt))
    return bytes(out), edits


# --- pins and images ---------------------------------------------------------------

_PINS = None


def _pins(*, optional=False):
    global _PINS
    if _PINS is None:
        if not PINS_PATH.is_file():
            if optional:
                return None
            raise ModernArrowheadError("Modern Arrowhead pins are missing from this build")
        _PINS = json.loads(PINS_PATH.read_text(encoding="utf-8"))
        require(_PINS.get("schema") == PINS_SCHEMA, "unsupported Modern Arrowhead pins schema")
        require(_PINS.get("art") == art_pins(), "the authored art differs from the pinned art")
    return _PINS


def arrowhead_entries(archive):
    """{filename: entry} for the nine Arrowhead bundles present in an archive."""
    ids = {name_id(name): name for name in VARIANTS}
    found = {}
    for entry in archive.entries:
        if entry.name_id in ids:
            found[ids[entry.name_id]] = entry
    return found


def _bundle_state(archive, pin):
    # An image without the pinned entry (another game, a synthetic test disc, a rebuilt archive) is foreign to
    # this option; inspect must report that rather than fail.
    if pin["outer"] >= len(archive.entries):
        return "foreign"
    entry = archive.entries[pin["outer"]]
    if entry.name_id != pin["name_id"] or entry.size != pin["size"]:
        return "foreign"
    states = set()
    for site in pin["sites"]:
        have = sha(archive.read(entry.virtual_offset + site["offset"], site["size"]))
        if have == site["retail"]:
            states.add("retail")
        elif have == site["applied"]:
            states.add("applied")
        else:
            return "foreign"
    return "mixed" if len(states) > 1 else states.pop()


def image_status(source):
    """retail / applied / mixed / foreign across the nine pinned bundles."""
    pins = _pins()
    from . import nfl2k5_modern_color as colour
    receipt = colour.read_image_receipt(source)
    combined = receipt.get("modern_arrowhead") if receipt else None
    if combined is not None:
        require(combined.get("art") == art_pins(), "Combined Arrowhead art pins differ")
        require(set(combined.get("bundles", {})) == {p["name"] for p in pins["bundles"]},
                "Combined Arrowhead receipt must cover all nine bundles")
        with _outer_image()(source) as archive:
            for pin in pins["bundles"]:
                row = combined["bundles"][pin["name"]]
                require(row.get("retail_sha256") == pin["retail_sha256"], "Combined Arrowhead source differs")
                sites = row.get("sites", [])
                require(len(sites) == len(pin["sites"]), "Combined Arrowhead site count differs")
                entry = archive.entries[pin["outer"]]
                require(entry.name_id == pin["name_id"] and entry.size == pin["size"], "Combined Arrowhead entry differs")
                data = archive.read(entry.virtual_offset, entry.size)
                if sha(data) != row.get("applied_sha256"):
                    return "foreign"
                for site, original in zip(sites, pin["sites"]):
                    require(all(site.get(k) == original[k] for k in ("kind", "offset", "size", "retail")),
                            "Combined Arrowhead receipt escaped its pinned span")
                    if sha(data[site["offset"]:site["offset"] + site["size"]]) != site.get("applied"):
                        return "foreign"
        return "applied"
    with _outer_image()(source) as archive:
        states = {_bundle_state(archive, pin) for pin in pins["bundles"]}
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign" if "foreign" in states else "mixed"


status = image_status


def verify(source, *, enabled=True):
    state = image_status(source)
    require(state == ("applied" if enabled else "retail"), "Arrowhead bundles do not match the requested option")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False, bundles=len(_pins()["bundles"]))


def apply_to_image(target, *, progress=None, retail_source=None):
    """Build-only: target must be the caller's disposable output image (or loose folder)."""
    from . import nfl2k5_modern_color as colour
    if colour.read_image_receipt(target) is not None:
        return apply_combined_to_image(target, retail_source=retail_source, progress=progress)
    pins = _pins()
    say = progress or (lambda message, done, total: None)
    receipt = dict(label=LABEL, runtime_witnessed=False, bundles=[], edits=[])
    with _outer_image()(target, writable=True) as archive:
        todo = []
        for pin in pins["bundles"]:
            state = _bundle_state(archive, pin)
            require(state in ("retail", "applied"), f"{pin['name']}: {state} bundle; rebuild from a supported base")
            if state == "applied":
                receipt["bundles"].append(dict(name=pin["name"], state="already_applied"))
            else:
                todo.append(pin)
        for index, pin in enumerate(todo):
            say(f"Modern Arrowhead: {pin['name']} ({index + 1} of {len(todo)})", index, len(todo))
            entry = archive.entries[pin["outer"]]
            data = archive.read(entry.virtual_offset, entry.size)
            require(sha(data) == pin["retail_sha256"], f"{pin['name']}: bundle bytes differ from the retail pin")
            after, edits = modern_bundle(data)
            require(sha(after) == pin["applied_sha256"], f"{pin['name']}: the refit bundle differs from the applied pin")
            archive.write(entry.virtual_offset, after)
            require(archive.read(entry.virtual_offset, entry.size) == after, f"{pin['name']}: write-back mismatch")
            receipt["bundles"].append(dict(name=pin["name"], state="applied", changed_bytes=sum(a != b for a, b in zip(data, after))))
            receipt["edits"].append(dict(name=pin["name"], edits=edits))
        say("Modern Arrowhead: done", len(todo), len(todo))
    receipt.update(verify(target, enabled=True))
    return receipt


def combined_bundle(retail, graded, *, outer_index, settings=None):
    """Compose art before colour grading and compress the shared field once."""
    from . import nfl2k5_modern_color as colour
    tx, inv, ResourceRecord, HEADER, stw = _tools()
    require(len(retail) == len(graded), "Combined bundle changed allocation")
    out = bytearray(graded)
    edits = []
    for name, chunk in bundle_plan(retail):
        size = HEADER.size + chunk.stored_size
        before = retail[chunk.offset:chunk.offset + size]
        if name == "field":
            after, detail = colour.modern_field_scene(before, outer_index=outer_index,
                                                      settings=settings, modern_arrowhead=True)
        else:
            after, detail = modern_scene_span(retail, chunk)
        require(len(after) == size, "Combined scene escaped its allocation")
        out[chunk.offset:chunk.offset + size] = after
        edits.append(dict(kind=name, offset=chunk.offset, size=size,
                          retail=sha(before), applied=sha(after), detail=detail))
    return bytes(out), edits


def apply_combined_to_image(target, *, retail_source, progress=None):
    """Add Arrowhead to a verified colour build using its original retail source."""
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    previous = colour.read_image_receipt(target)
    require(previous is not None, "Combined Arrowhead requires a colour receipt")
    require(colour.image_status(target, receipt=previous) == previous["state"],
            "Colour bytes differ from their receipt; rebuild from the original retail disc")
    if previous.get("modern_arrowhead") is not None:
        return dict(verify(target), already_applied=9, rewritten=0)
    require(retail_source is not None, "Combined Arrowhead needs the original retail source")
    say = progress or (lambda message, done, total: None)
    result = deepcopy(previous)
    combined = dict(art=art_pins(), bundles={})
    todo = []
    with _outer_image()(retail_source) as source, _outer_image()(target) as output:
        for index, pin in enumerate(_pins()["bundles"]):
            say(f"Modern Arrowhead and colour: {pin['name']}", index, 9)
            entry = source.entries[pin["outer"]]
            require(entry.name_id == pin["name_id"] and entry.size == pin["size"], "Arrowhead source entry differs")
            retail = source.read(entry.virtual_offset, entry.size)
            require(sha(retail) == pin["retail_sha256"], "Combined Arrowhead needs the original retail source")
            target_entry = output.entries[pin["outer"]]
            graded = output.read(target_entry.virtual_offset, target_entry.size)
            row = result["bundle_pins"][pin["name"]]
            require(sha(graded) == row["applied_sha256"], "Colour bundle changed after preflight")
            after, edits = combined_bundle(retail, graded, outer_index=pin["outer"], settings=previous["settings"])
            updated = dict(row, applied_sha256=sha(after), sites=[dict(site,
                applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in row["sites"]])
            result["bundle_pins"][pin["name"]] = updated
            combined["bundles"][pin["name"]] = dict(retail_sha256=pin["retail_sha256"],
                applied_sha256=sha(after), sites=[{k:e[k] for k in ("kind", "offset", "size", "retail", "applied")} for e in edits])
            # Each art span and every colour span must retain its pinned scope.
            require([(e["kind"], e["offset"], e["size"], e["retail"]) for e in edits] ==
                    [(s["kind"], s["offset"], s["size"], s["retail"]) for s in pin["sites"]], "Combined Arrowhead scope changed")
            todo.append((target_entry.virtual_offset, sha(graded), after))
    # Complete every bounded refit before the first output write.
    with _outer_image()(target, writable=True) as output:
        for at, before_hash, after in todo:
            require(sha(output.read(at, len(after))) == before_hash, "Combined bundle changed before write")
            require(output.write(at, after) == len(after), "Short combined Arrowhead write")
            require(output.read(at, len(after)) == after, "Combined Arrowhead read-back differs")
    result["modern_arrowhead"] = combined
    require(colour.image_status(target, receipt=result) == result["state"], "Combined colour read-back failed")
    colour._save_image_receipt(target, result)
    return dict(verify(target), rewritten=len(todo), already_applied=0)


def record_pins(source, out_path=PINS_PATH, *, progress=None):
    """Author-time: compute retail and applied pins for the nine bundles from a retail source."""
    say = progress or (lambda message, done, total: None)
    bundles = []
    with _outer_image()(source) as archive:
        entries = arrowhead_entries(archive)
        require(set(entries) == set(VARIANTS), f"Arrowhead bundles missing: {sorted(set(VARIANTS) - set(entries))}")
        for index, name in enumerate(VARIANTS):
            entry = entries[name]
            say(f"pinning {name}", index, len(VARIANTS))
            data = archive.read(entry.virtual_offset, entry.size)
            after, edits = modern_bundle(data)
            bundles.append(dict(name=name, outer=entry.table_index if hasattr(entry, "table_index") else entry.index,
                                name_id=entry.name_id, size=entry.size, retail_sha256=sha(data), applied_sha256=sha(after),
                                sites=[dict(kind=e["kind"], offset=e["offset"], size=e["size"], retail=e["before_sha256"], applied=e["after_sha256"],
                                            encoded_bytes=e["encoded_bytes"], consumed_cap=e["consumed_cap"], scratch_after=e["scratch_after"],
                                            textures=[t["png"] for t in e["textures"]]) for e in edits]))
    document = dict(schema=PINS_SCHEMA, venue="Arrowhead Stadium", art=art_pins(), bundles=bundles)
    Path(out_path).write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")
    return document


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_modern_arrowhead")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status"); s.add_argument("source")
    r = sub.add_parser("record-pins"); r.add_argument("source"); r.add_argument("--out", default=str(PINS_PATH))
    args = parser.parse_args(argv)
    if args.command == "status":
        print(image_status(args.source)); return 0
    document = record_pins(args.source, args.out, progress=lambda m, d, t: print(f"  {m}", flush=True))
    print(json.dumps({b["name"]: [(s["kind"], s["encoded_bytes"], s["consumed_cap"], s["scratch_after"]) for s in b["sites"]] for b in document["bundles"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

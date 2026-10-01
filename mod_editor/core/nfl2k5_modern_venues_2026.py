"""2026 field and wall art in every team's home stadium (experimental).

Every NFL team has its own home venue record in the retail main ROST (+0x114 of the team record), and each venue
has nine archive bundles, ``<prefix>{d,a,n}{d,r,s}.iff`` (day, afternoon, night; dry, rain, snow). A bundle holds
a field scene (end zones, midfield mark, turf) and a stadium scene (the bowl, its walls, boards, ribbons, signs and
fan banners). Noah, 2026-09-23: "the field art should be updated for every team. The stadium wall art should be
updated for every team. We can keep the same stadiums for now". So this option keeps every stadium and writes each
team's 2026 art into its home venue:

* the end zones are composited over each variant's own retail turf (north and, where a venue has separate south
  textures, south); the midfield mark replaces the retail mark with its own alpha;
* the team wall art in the stadium scene (walls, pads, boards, ribbons, signs, tarps, fan banners) replaces the
  retail texture inside the regions the art names (the rest of an atlas stays retail);
* every item is authored against the dry-day bundle; each other bundle gets the retail dry-day to variant look
  (a per-channel affine fit of the retail pair, plus snow drift on walls), and a variant that holds the texture at
  another size is filled from the 4x master.

The art comes from a folder of per-team art in the ``metlife_team_art/v1`` contract (job u1's ``art.py venue``,
extended for walls by job u4): ``<art root>/<ABBR>/venue/manifest.json`` with the team's ``spec.json`` beside
``venue/``. Nothing retail or from the web ships: the repository carries the venue table (hashes, texture maps,
the team-art targets), the code and the tests. The Giants and Jets venues (s18, s19) belong to Modern MetLife and
are skipped. Kansas City (s13) is written here only when the art folder carries a Kansas City venue, and then Modern
Arrowhead must be off (one writer per bundle); its reviewed art fills what the Kansas City folder leaves out,
except the sideline yard markers, which stay retail.

Venue names: where the 2004 building is still the team's home, its stadium record in the main ROST takes the 2026
name (name and display name; ``data/nfl2k5_modern_venues_2026/names.json``, twelve venues); teams that moved keep
the retail name, because the model is the old building.

Every changed scene is refit inside its fixed VC-LZ span with the retail wrapper (loader scratch word included)
unchanged, stepping the authored textures down a palette ladder only when a span misses. With Modern colour on,
the field art is composed before the colour grade and compressed once, as Modern Arrowhead and MetLife do.
EXPERIMENTAL and UNWITNESSED in game unless a report says otherwise.

The shared supplement also writes yearless plain-type event field logos in s31,
s39 and s41-s45. SoFi owns s40 and keeps its existing LXI field art.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import struct
from pathlib import Path

OWNER = "nfl2k5_modern_venues_2026"
LABEL = "EXPERIMENTAL / UNWITNESSED"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_CAPTION = "2026 field and wall art in every home stadium (experimental)"
HELP_TEXT = (
    "Writes each team's 2026 end zones, midfield mark and stadium wall art (walls, pads, boards, ribbons, signs, "
    "fan banners) into its home stadium, day, afternoon and night, dry, rain and snow. The stadiums stay as they "
    "are; where the building is the same, it takes its 2026 name (Acrisure Stadium, Empower Field, Lumen Field ...). "
    "Choose the folder of team art made with the 2026 team tools (one <team>/venue folder per team). Giants and "
    "Jets are Modern MetLife's; Kansas City needs Modern Arrowhead off. Every scene is refit inside its fixed span. "
    "Special event fields use yearless Super Bowl and Pro Bowl type; SoFi keeps its LXI art. "
    "Off in every preset; needs a disc image. Appearance in game is unwitnessed."
)
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_modern_venues_2026"
TABLE_PATH = DATA_DIR / "venues.json"
NAMES_PATH = DATA_DIR / "names.json"
NAMES_SCHEMA = "nfl2k5_modern_venues_2026_names/v1"
ROST_OUTER_INDEX = 5
TABLE_SCHEMA = "nfl2k5_modern_venues_2026_table/v1"
ART_SCHEMA = "metlife_team_art/v1"
RECEIPT_SCHEMA = "nfl2k5_modern_venues_2026_receipt/v1"
METLIFE_VENUES = ("s18", "s19")
ARROWHEAD_VENUE = "s13"
SOFI_VENUES = ("s23", "s24")   # b76-u6: SoFi Stadium owns the Rams and Chargers packages when its option is on
HIGHMARK_VENUES = ("s03",)     # b76-st: Highmark Stadium owns the Bills' packages when its option is on
ATT_VENUES = ("s07",)          # b76-st2: AT&T Stadium owns the Cowboys' packages when its option is on
LEVIS_VENUES = ("s25",)        # b76-st2: Levi's Stadium owns the 49ers' packages when its option is on
ALLEGIANT_VENUES = ("s20",)    # b76-st2: Allegiant Stadium owns the Raiders' packages when its option is on
MERCEDES_BENZ_VENUES = ("s01",)  # b76-st2: Mercedes-Benz Stadium owns the Falcons' packages when its option is on
USBANK_VENUES = ("s15",)       # b76-st3: U.S. Bank Stadium owns the Vikings' packages when its option is on
LUCAS_OIL_VENUES = ("s11",)    # b76-st3: Lucas Oil Stadium owns the Colts' packages when its option is on
STATE_FARM_VENUES = ("s00",)   # b76-st3: State Farm Stadium owns the Cardinals' packages when its option is on
HARD_ROCK_VENUES = ("s14",)   # b76-st4: Hard Rock Stadium owns the Dolphins' packages when its option is on
GILLETTE_VENUES = ("s16",)   # b76-st4: Gillette Stadium owns the Patriots' packages when its option is on
LAMBEAU_VENUES = ("s10",)   # b76-st4: Lambeau Field owns the Packers' packages when its option is on
EVERBANK_VENUES = ("s12",)   # b76-st4: EverBank Stadium owns the Jaguars' packages when its option is on
TIMES, WEATHERS = "dan", "drs"
CODES = tuple(t + w for t in TIMES for w in WEATHERS)
SCENES = ("field", "stadium")
END_ZONE_PARTS = ("L", "M", "R")
FIELD_KEYS = tuple(f"endzone_{end}_{part}" for end in "NS" for part in END_ZONE_PARTS) + ("center_logo",)
# Classes of the team-art targets (see the table): walls and pads take the retail snow drift in snow bundles.
DRIFT_CLASSES = ("wall", "colour")
# A variant texture counts as the same texture as the dry-day one when their small luma images correlate at
# least this well (flat textures: when their mean brightness is this close); see match_texture.
MATCH_CORRELATION = 0.5
FLAT_STD = 4.0
FLAT_MEAN_DELTA = 48.0
MAX_ART_BYTES = 16 * 1024 * 1024


class ModernVenuesError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ModernVenuesError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _mm():
    from . import nfl2k5_modern_metlife as mm
    return mm


def _tools():
    return _mm()._tools()


def _outer_image():
    return _mm()._outer_image()


def name_id(filename):
    return _mm().name_id(filename)


def bundle_names(prefix):
    return tuple(f"{prefix}{code}.iff" for code in CODES)


def code_of(filename):
    return filename[3:5]


def export_key(names):
    """The key job u1's venue exporter puts after ``<W>x<H>_`` in a texture's file name."""
    return "_".join(names or ["nomat"])[:60].replace("/", "_")


def _norm(names):
    return frozenset(n[6:] if n.startswith("LIGHT_") else n for n in (names or ()))


# --- the venue table --------------------------------------------------------------------------------------

_TABLE = None


def table():
    """The checked-in venue table: per home venue its nine bundles (retail pins), field layout and targets."""
    global _TABLE
    if _TABLE is None:
        require(TABLE_PATH.is_file(), "the 2026 venue table is missing from this build")
        doc = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
        require(doc.get("schema") == TABLE_SCHEMA, "unsupported 2026 venue table schema")
        _TABLE = doc
    return _TABLE


def venues():
    from . import nfl2k5_stadium_shared_art as shared
    return {**table()["venues"], **shared.special_venues()}


def arrowhead_art_path(name):
    from . import nfl2k5_modern_arrowhead as arrowhead
    return arrowhead.ART_DIR / name


# --- venue names (main ROST, outer 5) --------------------------------------------------------------------------

_NAMES = None


def names():
    """The checked-in venue names table: for every venue its retail strings, whether the 2004 building is still the
    team's home, its 2026 name and sources; a rename only where the building is the same."""
    global _NAMES
    if _NAMES is None:
        require(NAMES_PATH.is_file(), "the 2026 venue names are missing from this build")
        doc = json.loads(NAMES_PATH.read_text(encoding="utf-8"))
        require(doc.get("schema") == NAMES_SCHEMA, "unsupported 2026 venue names schema")
        _NAMES = doc
    return _NAMES


def renames():
    return {code: row for code, row in names()["venues"].items() if row.get("rename")}


def _renamed_texts(row):
    return dict(row["retail"], name=row["rename"]["name"], display_name=row["rename"]["display_name"])


def rost_rename(resource):
    """(ROST resource, receipt): the same-building venues take their 2026 name and display name.

    Modern MetLife's method for each record: its five strings form one contiguous block of the string pool, which
    is repacked in place (name, the display name when it differs, location, asset code, secondary label),
    zero-filled to the retail block end, and the record's five relative pointers are rewritten. The asset code, the
    engine's file-name key, stays. A record whose strings are neither retail nor renamed refuses, and so does any
    other pointer into its block.
    """
    mm = _mm()
    from . import nfl2k5_roster_records as rr
    header = rr.RESOURCE_HEADER_SIZE
    require(resource[:4] == b"ROST", "outer 5 is not a ROST resource")
    body = bytearray(resource[header:])
    records = mm._stadium_records(bytes(body))
    by_code = {fields["asset_code"][1]: (offset, fields) for offset, fields in records}
    text_spans = [(t, t + 2 * len(txt) + 2) for _o, fs in records for t, txt in fs.values()]
    receipt = dict(records=[])
    for code, row in sorted(renames().items()):
        require(code in by_code, f"the ROST has no {code} stadium record")
        offset, fields = by_code[code]
        texts = {name: text for name, (_t, text) in fields.items()}
        wanted = _renamed_texts(row)
        if texts == wanted:
            receipt["records"].append(dict(venue=code, state="already_applied"))
            continue
        require(texts == row["retail"], f"{code}: stadium strings are not retail ({texts})")
        block = mm._string_block(fields)
        require(block is not None, f"{code}: stadium strings are not one contiguous block")
        start, end = block
        pointer_fields = {offset + field for field, _name in mm.ROST_STRING_FIELDS}
        stray = mm._pointers_into(bytes(body), start, end, pointer_fields, text_spans)
        require(not stray, f"{code}: other pointers reach the stadium strings at {stray[:4]}")
        layout = [("name", wanted["name"])]
        if wanted["display_name"] != wanted["name"]:
            layout.append(("display_name", wanted["display_name"]))
        layout += [("location", texts["location"]), ("asset_code", texts["asset_code"]),
                   ("secondary_label", texts["secondary_label"])]
        payload, at = bytearray(), {}
        for key, text in layout:
            at[key] = start + len(payload)
            payload += text.encode("utf-16le") + b"\0\0"
        used = len(payload)
        require(used <= end - start, f"{code}: the 2026 name does not fit the retail string block")
        body[start:end] = bytes(payload) + bytes(end - start - used)
        at.setdefault("display_name", at["name"])
        for field, name in mm.ROST_STRING_FIELDS:
            struct.pack_into("<i", body, offset + field, at[name] - (offset + field) + 1)
        check = {name: text for name, (_t, text) in dict(mm._stadium_records(bytes(body)))[offset].items()}
        require(check == wanted, f"{code}: renamed record read-back differs")
        receipt["records"].append(dict(venue=code, state="applied", name=wanted["name"],
                                       display_name=wanted["display_name"], block=[start, end], bytes_used=used))
    return bytes(resource[:header]) + bytes(body), receipt


def rost_state(resource):
    """retail / applied / foreign for the renamed stadium records of one ROST resource."""
    mm = _mm()
    try:
        from . import nfl2k5_roster_records as rr
        records = {f["asset_code"][1]: f for _o, f in mm._stadium_records(resource[rr.RESOURCE_HEADER_SIZE:])}
    except Exception:  # noqa: BLE001 - a ROST this module cannot read is foreign to it
        return "foreign"
    states = set()
    for code, row in renames().items():
        fields = records.get(code)
        if fields is None:
            return "foreign"
        texts = {name: text for name, (_t, text) in fields.items()}
        if texts == row["retail"]:
            states.add("retail")
        elif texts == _renamed_texts(row):
            states.add("applied")
        else:
            return "foreign"
    return states.pop() if len(states) == 1 else "foreign"


def _read_rost(archive):
    entry = archive.entries[ROST_OUTER_INDEX]
    return entry, archive.read(entry.virtual_offset, entry.size)


def apply_rost(archive):
    """Rename the same-building venues in the image's main ROST; returns the receipt."""
    entry, data = _read_rost(archive)
    state = rost_state(data)
    require(state in ("retail", "applied"), f"the venue names in the ROST are {state}; rebuild from a supported base")
    if state == "applied":
        return dict(state="already_applied")
    after, receipt = rost_rename(data)
    require(len(after) == len(data), "the venue rename changed the ROST size")
    archive.write(entry.virtual_offset, after)
    require(archive.read(entry.virtual_offset, entry.size) == after, "the venue rename read-back differs")
    return dict(receipt, state="applied", changed_bytes=sum(a != b for a, b in zip(data, after)))


# --- images ------------------------------------------------------------------------------------------------

def _rgba(data):
    import numpy as np
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        return np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()


def resample(rgba, width, height):
    """RGBA uint8 array resized to (height, width, 4), premultiplied so clear edges do not darken."""
    import numpy as np
    from PIL import Image
    if rgba.shape[:2] == (height, width):
        return rgba
    a = rgba.astype(np.float64) / 255.0
    pre = np.concatenate([a[..., :3] * a[..., 3:4], a[..., 3:4]], axis=-1)
    down = width <= rgba.shape[1] and height <= rgba.shape[0]
    method = Image.Resampling.BOX if down else Image.Resampling.BICUBIC
    channels = [np.asarray(Image.fromarray(np.float32(pre[..., c])).resize((width, height), method), dtype=np.float64)
                for c in range(4)]
    out = np.stack(channels, axis=-1).clip(0.0, 1.0)
    alpha = out[..., 3:4]
    rgb = np.where(alpha > 1e-6, out[..., :3] / np.maximum(alpha, 1e-6), 0.0)
    return np.uint8(np.clip(np.rint(np.concatenate([rgb, alpha], axis=-1) * 255.0), 0, 255))


def letterbox(rgba, width, height):
    """The art scaled to fit (width, height) with its own aspect, centred, fully clear around it."""
    import numpy as np
    h0, w0 = rgba.shape[:2]
    scale = min(width / w0, height / h0)
    w1, h1 = max(1, int(round(w0 * scale))), max(1, int(round(h0 * scale)))
    out = np.zeros((height, width, 4), dtype=np.uint8)
    x0, y0 = (width - w1) // 2, (height - h1) // 2
    out[y0:y0 + h1, x0:x0 + w1] = resample(rgba, w1, h1)
    return out


def _small_luma(rgba, size=16):
    import numpy as np
    small = resample(rgba, size, size).astype(np.float64)
    return small[..., 0] * 0.299 + small[..., 1] * 0.587 + small[..., 2] * 0.114


def similarity(a, b):
    """How alike two textures look (same picture, other weather or size): luma correlation, or for flat
    textures, closeness of mean brightness. 1.0 is identical."""
    import numpy as np
    x, y = _small_luma(a), _small_luma(b)
    if x.std() < FLAT_STD or y.std() < FLAT_STD:
        return float(max(0.0, 1.0 - abs(x.mean() - y.mean()) / FLAT_MEAN_DELTA))
    return float(np.corrcoef(x.ravel(), y.ravel())[0, 1])


# --- scenes ------------------------------------------------------------------------------------------------

def p8_rows(rec):
    """{texture index: row} of the editable P8 textures of one parsed scene."""
    return {int(r["index"]): r for r in rec.get("embedded_textures", ())
            if r.get("format_name") == "P8" and r.get("conversion_status") == "base_level_supported"}


def read_texture(decoded, rec, row):
    return _mm().read_p8(decoded, int(rec["system_bytes"]), row)[0]


def bundle_scenes(data):
    """{scene name: chunk} for the field and stadium scenes of one bundle."""
    out = _mm().bundle_scenes(data)
    return {name: chunk for name, chunk in out.items() if name in SCENES}


def decode_scenes(data):
    """{scene name: (rec, decoded)} for the field and stadium scenes of one bundle."""
    mm = _mm()
    return {name: mm._scene(data, chunk) for name, chunk in bundle_scenes(data).items()}


def rows_by_material(rec):
    out = {}
    for index, row in p8_rows(rec).items():
        for name in row.get("mapped_material_names") or ():
            out.setdefault(name, index)
    return out


def find_stadium_texture(rec, key):
    """The dry-day stadium texture a manifest key names: the exporter's key, or one of its material names."""
    rows = p8_rows(rec)
    exact = [i for i, r in rows.items() if export_key(r.get("mapped_material_names")) == key]
    if len(exact) == 1:
        return exact[0]
    named = [i for i, r in rows.items() if key in (r.get("mapped_material_names") or ())]
    require(len(named) <= 1, f"stadium key {key} names {len(named)} textures; use the exporter's key")
    return named[0] if named else None


def _shape_ok(ref_row, row):
    """A texture of another size is still the same surface when it keeps the aspect or is larger both ways (the
    Miami snow walls hold 256x128 art at 256x256); a smaller texture of another shape is other art."""
    w0, h0, w1, h1 = int(ref_row["width"]), int(ref_row["height"]), int(row["width"]), int(row["height"])
    return w1 * h0 == h1 * w0 or (w1 >= w0 and h1 >= h0)


def match_texture(ref_rec, ref_decoded, ref_index, rec, decoded):
    """(index, score) of the texture in another bundle's scene that is the reference texture ``ref_index``.

    Tier 1, the same material names (night LIGHT_ names count as the day names), is trusted when the shape
    fits: weather changes a surface a lot (snow on the pads) but not its name. Tier 2 (a shared name) and tier 3
    (the same texture index, as for Chicago's afternoon ``bearwall02``) must also look like the reference
    (``similarity`` at least MATCH_CORRELATION). Returns (None, best score) when nothing qualifies, as with
    Foxborough's night ``wall04``, which is smaller other art.
    """
    ref_row = p8_rows(ref_rec)[ref_index]
    base = read_texture(ref_decoded, ref_rec, ref_row)
    want = _norm(ref_row.get("mapped_material_names"))
    rows = p8_rows(rec)
    tiers = (("names", [i for i, r in rows.items() if _norm(r.get("mapped_material_names")) == want]),
             ("shared", [i for i, r in rows.items() if _norm(r.get("mapped_material_names")) & want]),
             ("index", [ref_index] if ref_index in rows else []))
    best = -1.0
    for tier, candidates in tiers:
        scored = []
        for index in candidates:
            row = rows[index]
            if not _shape_ok(ref_row, row):
                continue
            score = similarity(base, read_texture(decoded, rec, row))
            best = max(best, score)
            if tier == "names" or score >= MATCH_CORRELATION:
                scored.append((index == ref_index, score, index))
        if scored:
            scored.sort(reverse=True)
            return scored[0][2], scored[0][1]
    return None, best


def resolve_variants(dd_index, decoded):
    """{code: (index, score) or (None, score)} of one dry-day stadium texture in all nine bundles.

    ``decoded`` is {code: (stadium rec, decoded)}. Each time of day's dry bundle is matched to the dry-day
    one, then its rain and snow bundles to that dry bundle (same time of day, so a renamed texture still
    looks alike), falling back to the dry-day bundle.
    """
    out = {"dd": (dd_index, 1.0)}
    dd_rec, dd_dec = decoded["dd"]
    for tod in TIMES:
        dry = tod + "d"
        if dry != "dd":
            rec, dec = decoded[dry]
            out[dry] = match_texture(dd_rec, dd_dec, dd_index, rec, dec)
        ref_index = out[dry][0]
        for weather in "rs":
            code = tod + weather
            rec, dec = decoded[code]
            if ref_index is not None:
                ref_rec, ref_dec = decoded[dry]
                found = match_texture(ref_rec, ref_dec, ref_index, rec, dec)
                if found[0] is not None:
                    out[code] = found
                    continue
            out[code] = match_texture(dd_rec, dd_dec, dd_index, rec, dec)
    return out


# --- the art contract (metlife_team_art/v1 plus the walls extension) ---------------------------------------

def _manifest_paths(root):
    """[(team folder or None, manifest path)] under an art root: <root>/<team>/venue/manifest.json, or venue
    folders directly (<root>/<x>/manifest.json), or the root itself when it is one venue folder."""
    root = Path(root)
    require(root.is_dir(), f"the venue art folder was not found: {root}")
    if (root / "manifest.json").is_file():
        return [(root.parent if root.name == "venue" else None, root / "manifest.json")]
    out = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if (child / "venue" / "manifest.json").is_file():
            out.append((child, child / "venue" / "manifest.json"))
        elif (child / "manifest.json").is_file():
            out.append((None, child / "manifest.json"))
    return out


def _spec_slots(team_dir):
    """{banner key: [slot rects]} from the team's spec (venue.banners[key].banners[*].slot), retail pixels."""
    if team_dir is None:
        return {}
    path = Path(team_dir) / "spec.json"
    if not path.is_file():
        return {}
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    banners = ((spec.get("venue") or {}).get("banners") or {}) if isinstance(spec, dict) else {}
    out = {}
    for key, sheet in banners.items():
        slots = [list(map(int, b["slot"])) for b in (sheet or {}).get("banners", ()) if isinstance(b, dict) and "slot" in b]
        if slots:
            out[key] = slots
    return out


def _rects_ok(rects, width, height):
    return all(len(r) == 4 and 0 <= r[0] < r[2] <= width and 0 <= r[1] < r[3] <= height for r in rects)


def load_art(root):
    """Read and check every venue manifest under ``root``.

    Returns {"venues": {prefix: venue art}, "skipped": [...], "root": str}. A venue art is {"prefix", "team",
    "manifest", "digest", "items": [item]}; an item is {"scene", "key", "layer", "size", "rgba", "master",
    "rects", "sha256"}. Every file must match its manifest SHA-256 and size. The Giants and Jets venues are
    skipped (Modern MetLife owns them).
    """
    known = venues()
    out, skipped = {}, []
    for team_dir, path in _manifest_paths(root):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ModernVenuesError(f"{path}: not a readable manifest ({exc})") from exc
        if not isinstance(doc, dict) or doc.get("schema") != ART_SCHEMA:
            continue  # another kind of manifest (the kit art has its own schema)
        prefix = doc.get("venue_prefix")
        if prefix in METLIFE_VENUES:
            skipped.append(dict(manifest=str(path), venue=prefix, reason="Modern MetLife owns the Giants and Jets venues"))
            continue
        require(prefix in known, f"{path}: {prefix} is not a home venue in the 2026 venue table")
        require(prefix not in out, f"two art folders name venue {prefix}: {out.get(prefix, {}).get('manifest')} and {path}")
        slots = _spec_slots(team_dir)
        base = path.parent
        items, seen = [], set()
        for raw in doc.get("items") or ():
            scene, key, layer = raw.get("scene"), raw.get("material"), raw.get("layer")
            require(scene in SCENES, f"{path}: item {key}: scene must be field or stadium")
            require(layer in ("overlay", "full"), f"{path}: item {key}: layer must be overlay or full")
            require(isinstance(key, str) and key and (scene, key) not in seen, f"{path}: item {key} is missing or repeated")
            seen.add((scene, key))
            if scene == "field":
                require(key in FIELD_KEYS, f"{path}: field item {key} is not an end zone panel or the midfield mark")
            file = (base / raw["file"]).resolve()
            require(file.is_file() and file.stat().st_size <= MAX_ART_BYTES, f"{path}: item {key}: {raw['file']} is missing")
            data = file.read_bytes()
            require(sha(data) == raw.get("sha256"), f"{path}: item {key}: {raw['file']} differs from its manifest SHA-256")
            rgba = _rgba(data)
            width, height = (int(v) for v in raw.get("size") or (0, 0))
            require(rgba.shape[:2] == (height, width), f"{path}: item {key}: the PNG is {rgba.shape[1]}x{rgba.shape[0]}, "
                    f"the manifest says {width}x{height}")
            master = None
            if raw.get("master"):
                candidate = (base / raw["master"]).resolve()
                if candidate.is_file():
                    if raw.get("master_sha256"):
                        require(sha(candidate.read_bytes()) == raw["master_sha256"],
                                f"{path}: item {key}: {raw['master']} differs from its manifest SHA-256")
                    master = str(candidate)
            rects = raw.get("rects")
            if rects is None and scene == "stadium" and layer == "full":
                rects = slots.get(key)
            if rects is not None:
                rects = [list(map(int, r)) for r in rects]
                require(rects and _rects_ok(rects, width, height), f"{path}: item {key}: rects must lie inside {width}x{height}")
            items.append(dict(scene=scene, key=key, layer=layer, size=[width, height], rgba=rgba, master=master,
                              rects=rects, sha256=raw["sha256"], source="team"))
        require(items, f"{path}: the manifest has no items")
        digest = sha(json.dumps([[i["scene"], i["key"], i["layer"], i["sha256"], i["rects"]] for i in items],
                                sort_keys=True).encode("utf-8"))
        out[prefix] = dict(prefix=prefix, team=doc.get("team"), manifest=str(path), digest=digest, items=items)
    return dict(venues=out, skipped=skipped, root=str(Path(root)), league=load_league_marks(root))


def _extra_items(prefix, supplied):
    """Reviewed art the table adds to a venue when its team art leaves those keys out (Kansas City: Modern
    Arrowhead's art, except the sideline yard markers). An extra that names ``rects`` (a full layer) redraws only
    those rectangles and goes under the team's own art for the same texture (team items compose after table items),
    so it applies whether or not the team supplies the key: Washington's defunct 2004 sponsor cells (st2,
    2026-09-28). One marked ``over`` goes over the team's art instead (its source is table_over, composed after the
    team's items), for a team item that itself carries what the policy takes off: Pittsburgh's drawn sponsor marks
    (main, 2026-09-28)."""
    out = []
    for extra in venues()[prefix].get("extras", ()):
        rects = extra.get("rects")
        over = bool(extra.get("over"))
        require(rects or not over, f"{prefix}: reviewed art {extra['art']}: an extra over the team's art names rects")
        if (extra["scene"], extra["key"]) in supplied and not rects:
            continue
        path = arrowhead_art_path(extra["art"]) if extra.get("from") == "modern_arrowhead" else DATA_DIR / extra["art"]
        require(path.is_file(), f"{prefix}: reviewed art {extra['art']} is missing from this build")
        data = path.read_bytes()
        require(sha(data) == extra["sha256"], f"{prefix}: reviewed art {extra['art']} differs from the table")
        rgba = _rgba(data)
        width, height = rgba.shape[1], rgba.shape[0]
        if rects:
            rects = [list(map(int, r)) for r in rects]
            require(extra["layer"] == "full" and _rects_ok(rects, width, height),
                    f"{prefix}: reviewed art {extra['art']}: rects need a full layer and must lie inside {width}x{height}")
        out.append(dict(scene=extra["scene"], key=extra["key"], layer=extra["layer"], size=[width, height],
                        rgba=rgba, master=None, rects=rects or None, sha256=extra["sha256"],
                        source="table_over" if over else extra.get("from", "table")))
    return out


LEAGUE_SCHEMA = "nfl2k5_league_marks/v1"
LEAGUE_MARKS = ("nfl_shield", "afc", "nfc")
# table_over (st6: an extra over the team's art, s22) and shared_art (fb2: residual sponsors and event field type)
# both compose after the team's items; they never meet (shared art excludes every board-kit venue, s22 among them).
SOURCE_ORDER = {"league": 0, "league_art": 0.5, "modern_arrowhead": 1, "table": 1, "team": 2, "table_over": 3, "shared_art": 3}
# Reviewed league-wide art in data/nfl2k5_modern_venues_2026 (tools/nfl2k5_modern_venues_2026_art.py): the field-level
# sponsor sheet's eight defunct 2004 cloths become 2026 league type (ESPN, NFL+, PLAY 60, NFL FLAG, SUPER BOWL LXI,
# NFLPA, NFL NETWORK); Riddell, Gatorade and NFL.com stay. Written in every venue the build writes, under team art.
LEAGUE_ART = ({"key": "banner_corp", "art": "league/banner_corp.png",
               "rects": [[5, 2, 123, 61], [5, 66, 123, 125], [131, 67, 190, 126], [195, 67, 254, 126],
                         [131, 131, 190, 190], [195, 131, 254, 190], [5, 194, 123, 253], [195, 195, 254, 254]]},)


def load_league_marks(root):
    """{mark: RGBA master} from ``<art root>/_league/manifest.json`` ({"schema", "marks": {mark: {"file",
    "sha256"}}}), or {} when the folder carries none. The marks are the current NFL shield (2008) and the AFC
    and NFC marks (2010), as official vectors rendered by the user's own tools; nothing of them ships."""
    import numpy as np
    from PIL import Image
    path = Path(root) / "_league" / "manifest.json"
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(doc, dict) and doc.get("schema") == LEAGUE_SCHEMA, f"{path}: unsupported league marks manifest")
    out = {}
    for mark, row in (doc.get("marks") or {}).items():
        require(mark in LEAGUE_MARKS, f"{path}: unknown league mark {mark}")
        file = (path.parent / row["file"]).resolve()
        require(file.is_file() and file.stat().st_size <= 4 * MAX_ART_BYTES, f"{path}: {row['file']} is missing")
        data = file.read_bytes()
        require(sha(data) == row.get("sha256"), f"{path}: {row['file']} differs from its manifest SHA-256")
        with Image.open(io.BytesIO(data)) as image:
            out[mark] = dict(rgba=np.asarray(image.convert("RGBA"), dtype=np.uint8).copy(), sha256=row["sha256"])
    return out


def knockout_white(rgba):
    """A coloured mark as white with its white details knocked out (the badge colour shows through them):
    the AFC and NFC marks on the red and navy championship badges."""
    import numpy as np
    a = rgba.astype(np.float64) / 255.0
    whiteness = np.clip((a[..., :3].min(axis=-1) - 0.55) / 0.35, 0.0, 1.0)
    out = np.empty_like(a)
    out[..., :3] = 1.0
    out[..., 3] = a[..., 3] * (1.0 - whiteness)
    return np.uint8(np.clip(np.rint(out * 255.0), 0, 255))


def fill_rect(rgba, rect):
    """The texture with the pixels inside ``rect`` refilled from the pixels around it (growing masked box
    means), so a new mark placed there leaves no sliver of the old one."""
    import numpy as np
    x0, y0, x1, y1 = rect
    rgb = rgba.astype(np.float64)
    inside = np.zeros(rgba.shape[:2], dtype=bool)
    inside[y0:y1, x0:x1] = True
    weight = (~inside).astype(np.float64)
    out = rgb.copy()
    holes = inside.copy()
    radius = 2
    while holes.any() and radius <= 2 * max(rgba.shape[:2]):
        num = _box_mean(rgb * weight[..., None], radius)
        den = _box_mean(weight, radius)
        ready = holes & (den > 1e-6)
        out[ready] = num[ready] / den[ready][:, None]
        holes &= ~ready
        radius *= 2
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def _alpha_crop(rgba):
    import numpy as np
    ys, xs = np.nonzero(rgba[..., 3] > 8)
    if not len(xs):
        return rgba
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def league_art(base, entry, marks):
    """Full-texture art for one league entry: the old mark's rect refilled (reaching a pixel or two past it, so no
    sliver of the old outline survives), the new mark cropped to its own shape and letterboxed into the rect."""
    mm = _mm()
    h, w = base.shape[:2]
    x0, y0, x1, y1 = entry["rect"]
    grow = min(3, max(1, round(0.04 * max(x1 - x0, y1 - y0))))
    fx0, fy0, fx1, fy1 = max(0, x0 - grow), max(0, y0 - grow), min(w, x1 + grow), min(h, y1 + grow)
    mark = _alpha_crop(marks[entry["mark"]]["rgba"])
    if entry.get("style") == "knockout_white":
        mark = knockout_white(mark)
    filled = fill_rect(base, [fx0, fy0, fx1, fy1])
    placed = letterbox(mark, x1 - x0, y1 - y0)
    out = filled.copy()
    out[y0:y1, x0:x1] = mm.composite_over(filled[y0:y1, x0:x1], placed)
    # outside the refilled box the texture stays exactly retail
    out[:fy0], out[fy1:], out[:, :fx0], out[:, fx1:] = base[:fy0], base[fy1:], base[:, :fx0], base[:, fx1:]
    return out


# --- the plan: which texture of which bundle takes which art -------------------------------------------------

def _target_row(prefix, key):
    """The venue table's target row for a stadium key, or None. A neutral model slot has no row: SoFi's s40, which
    the model fan step paints through paint_scene (nfl2k5_model_fan_art.neutral_plan)."""
    return next((t for t in venues().get(prefix, {}).get("targets", ()) if t["key"] == key), None)


def plan_venue(prefix, art, bundles, league=None):
    """Resolve one venue's art against its retail bundles ({name: bytes}; the dry-day one at least).

    Returns {"prefix", "items": [item + "dd": {scene, index} (+ "variants" for stadium items)], "notes",
    "uncovered", "base": {(scene, index): retail dry-day RGBA}}. Field keys name materials (found by name in
    every bundle); a stadium key names one dry-day texture (the exporter's key), mapped to the other bundles
    by the venue table or, for a texture the table does not list, by resolve_variants. Every item's size must
    equal its dry-day texture's size.
    """
    row = venues()[prefix]
    decoded = {"dd": decode_scenes(bundles[f"{prefix}dd.iff"])}
    notes = []
    from . import nfl2k5_stadium_shared_art as shared
    team_items = (list(art["items"]) if art else []) + list(shared.items(prefix))
    supplied = {(i["scene"], i["key"]) for i in team_items}
    items = team_items + (_extra_items(prefix, supplied) if art else [])
    planned = []
    field_rec, field_decoded = decoded["dd"]["field"]
    stadium_rec, stadium_decoded = decoded["dd"]["stadium"]
    materials = rows_by_material(field_rec)
    field_rows, stadium_rows = p8_rows(field_rec), p8_rows(stadium_rec)
    for item in items:
        if item["scene"] == "field":
            key = item["key"]
            if key not in materials:
                require(item.get("kind") != "field-logo", f"{prefix}: missing event field logo {key}")
                notes.append(f"{key}: this venue has no {key} texture (uncovered)")
                continue
            index = materials[key]
            if key.startswith("endzone_S_") and materials.get(key.replace("_S_", "_N_")) == index:
                notes.append(f"{key}: both end zones share one texture in this venue; the north art is used at both ends")
                continue
            target = field_rows[index]
            extra = {}
            if item.get("kind") == "field-logo":
                known = row["field_logos"][key]
                require(known["texture"] == index, f"{prefix}: event field logo {key} moved")
                extra = dict(variants=known["variants"])
            size = [int(target["width"]), int(target["height"])]
            if key == "center_logo" and item["size"] != size:
                # Cincinnati's midfield texture is 512x256; a square mark is centred in it at full height with
                # its own aspect, clear at the sides (a team can supply the texture's own size instead).
                item = dict(item, rgba=letterbox(item["rgba"], *size), size=size, master=None)
                notes.append(f"center_logo: the {size[0]}x{size[1]} midfield texture takes the mark letterboxed")
        else:
            index = find_stadium_texture(stadium_rec, item["key"])
            require(index is not None, f"{prefix}: stadium key {item['key']} names no texture in the dry-day stadium scene")
            target = stadium_rows[index]
            known = _target_row(prefix, item["key"])
            if known is not None and known["texture"] == index:
                variants = {code: (tuple(v) if v else None) for code, v in known["variants"].items()}
            else:
                for name, data in bundles.items():
                    code = code_of(name)
                    if code not in decoded:
                        decoded[code] = decode_scenes(data)
                require(len(decoded) == len(CODES), f"{prefix}: resolving {item['key']} needs all nine bundles")
                found = resolve_variants(index, {code: decoded[code]["stadium"] for code in CODES})
                variants = {}
                for code, (vindex, _score) in found.items():
                    if vindex is None:
                        variants[code] = None
                    else:
                        vrow = p8_rows(decoded[code]["stadium"][0])[vindex]
                        variants[code] = (vindex, int(vrow["width"]), int(vrow["height"]))
            extra = dict(variants=variants)
        require([int(target["width"]), int(target["height"])] == item["size"],
                f"{prefix}: {item['key']} is {item['size'][0]}x{item['size'][1]}, the texture is "
                f"{target['width']}x{target['height']}")
        planned.append(dict(item, dd=dict(scene=item["scene"], index=index), **extra))
    # South end zones in split venues take the north art unless the team supplies them.
    keys = {p["key"] for p in planned if p["scene"] == "field"}
    for part in END_ZONE_PARTS:
        north, south = f"endzone_N_{part}", f"endzone_S_{part}"
        if north in keys and south not in keys and south in materials and materials[south] != materials[north]:
            source = next(p for p in planned if p["key"] == north)
            planned.append(dict(source, key=south, dd=dict(scene="field", index=materials[south]), mirrored_from=north))
    if league:
        for entry in row.get("league", ()):
            if entry["mark"] not in league:
                continue
            rec, dec = decoded["dd"][entry["scene"]]
            rows = p8_rows(rec)
            index = entry["texture"]
            require(index in rows and export_key(rows[index].get("mapped_material_names")) == entry["key"],
                    f"{prefix}: league mark target {entry['key']} is not where the venue table says")
            base_tex = read_texture(dec, rec, rows[index])
            art_tex = league_art(base_tex, entry, league)
            key = entry["material"] if entry["scene"] == "field" else entry["key"]
            item = dict(scene=entry["scene"], key=key, layer="full", size=list(entry["size"]), rgba=art_tex,
                        master=None, rects=[list(entry["rect"])], sha256=league[entry["mark"]]["sha256"],
                        source="league", mark=entry["mark"], dd=dict(scene=entry["scene"], index=index))
            if entry["scene"] == "stadium":
                item["variants"] = {code: (tuple(v) if v else None) for code, v in entry["variants"].items()}
            planned.append(item)
    for entry in row.get("league_art", ()):
        path = DATA_DIR / entry["art"]
        require(path.is_file(), f"reviewed league art {entry['art']} is missing from this build")
        data = path.read_bytes()
        require(sha(data) == entry["sha256"], f"reviewed league art {entry['art']} differs from the venue table")
        rgba = _rgba(data)
        require([rgba.shape[1], rgba.shape[0]] == list(entry["size"]), f"{entry['art']} is not {entry['size']}")
        planned.append(dict(scene="stadium", key=entry["key"], layer="full", size=list(entry["size"]), rgba=rgba,
                            master=None, rects=[list(r) for r in entry["rects"]], sha256=entry["sha256"],
                            source="league_art", dd=dict(scene="stadium", index=entry["texture"]),
                            variants={code: (tuple(v) if v else None) for code, v in entry["variants"].items()}))
    covered = {p["dd"]["index"] for p in planned if p["scene"] == "stadium" and p.get("source") not in ("league", "league_art")}
    uncovered = [t["key"] for t in row.get("targets", ()) if t["class"] in ("wall", "board", "sign", "fan")
                 and t["texture"] not in covered]
    base = {}
    for p in planned:
        rec, dec = decoded["dd"][p["dd"]["scene"]]
        base[(p["dd"]["scene"], p["dd"]["index"])] = read_texture(dec, rec, p8_rows(rec)[p["dd"]["index"]])
    return dict(prefix=prefix, items=planned, notes=notes, uncovered=uncovered, base=base)


def variant_index(plan_item, code, rec):
    """The texture index of one planned item in the bundle with ``code`` (None: not in that bundle)."""
    if plan_item["dd"]["scene"] == "field":
        index = rows_by_material(rec).get(plan_item["key"])
        if plan_item.get("kind") == "field-logo":
            expected, width, height = plan_item["variants"][code]
            row = p8_rows(rec).get(index)
            require(index == expected and row is not None
                    and (int(row["width"]), int(row["height"])) == (width, height),
                    f"{code}: event logo {plan_item['key']} differs from its native P8 target")
        return index
    mapped = plan_item["variants"].get(code)
    if mapped is None:
        return None
    index, width, height = mapped
    row = p8_rows(rec).get(index)
    require(row is not None and (int(row["width"]), int(row["height"])) == (width, height),
            f"{code}: {plan_item['key']} is not where the venue map says")
    return index


def _art_at(item, width, height):
    """The item's art at a texture size: the native PNG, or its 4x master (else the native) resampled."""
    if (width, height) == tuple(item["size"]):
        return item["rgba"]
    if item.get("master"):
        from PIL import Image
        import numpy as np
        with Image.open(item["master"]) as image:
            master = np.asarray(image.convert("RGBA"), dtype=np.uint8)
        return resample(master, width, height)
    return resample(item["rgba"], width, height)


def _box_mean(values, radius):
    """Mean over a (2r+1)^2 window with edge clamping (numpy only)."""
    import numpy as np
    if radius <= 0:
        return values
    k = 2 * radius + 1
    padded = np.pad(values, [(radius, radius), (radius, radius)] + [(0, 0)] * (values.ndim - 2), mode="edge")
    cs = padded.cumsum(axis=0).cumsum(axis=1)
    cs = np.pad(cs, [(1, 0), (1, 0)] + [(0, 0)] * (values.ndim - 2))
    h, w = values.shape[:2]
    return (cs[k:k + h, k:k + w] - cs[0:h, k:k + w] - cs[k:k + h, 0:w] + cs[0:h, 0:w]) / (k * k)


def clean_turf(rgba):
    """The retail end zone with its 2004 marks filled in from the surrounding turf (or paint).

    End-zone art is painted over this base at the art's own alpha (u1's art.py paints at 0.92), so whatever
    shows through should be turf grain, not the old letters. Pixels far from the texture's dominant colour
    (the marks, dilated by a pixel) are refilled with a masked box mean of the kept pixels, growing the window
    until every hole is filled. A texture with no dominant background (under a third of it, as Cincinnati's
    all-over tiger stripes) becomes its median colour, so the paint shows an even tint and no pattern.
    """
    import numpy as np
    rgb = rgba[..., :3].astype(np.float64)
    median = np.median(rgb.reshape(-1, 3), axis=0)
    far = np.abs(rgb - median).sum(axis=-1) > 60.0
    far = _box_mean(far.astype(np.float64), 1) > 0.0
    keep = ~far
    if keep.mean() < 0.33:
        flat = rgba.copy()
        flat[..., :3] = np.clip(np.rint(median), 0, 255).astype(np.uint8)
        return flat
    out = rgb.copy()
    weight = keep.astype(np.float64)
    radius = 2
    holes = far.copy()
    while holes.any() and radius <= max(rgba.shape[:2]):
        num = _box_mean(rgb * weight[..., None], radius)
        den = _box_mean(weight, radius)
        ready = holes & (den > 1e-6)
        out[ready] = num[ready] / den[ready][:, None]
        holes &= ~ready
        radius *= 2
    result = rgba.copy()
    result[..., :3] = np.clip(np.rint(out), 0, 255).astype(np.uint8)
    return result


def compose(item, base, current, art, weather, cls=None, canvas=None):
    """One texture of one bundle: the authored dry-day art carried to this bundle's look.

    ``base`` is the retail dry-day texture (resized to this bundle's size), ``current`` the retail texture of
    this bundle. Overlays (end zones): the paint takes the dry-day to bundle fit, then goes over this bundle's
    own turf with the 2004 marks filled in (clean_turf); the
    midfield mark and full items replace their regions (all of the texture unless ``rects`` names some) and
    take the fit region by region; walls and pads take the retail snow drift in snow bundles.
    """
    mm = _mm()
    height, width = current.shape[:2]
    if item["layer"] == "overlay" and item["key"] != "center_logo":
        # The paint takes the retail dry-day to bundle fit and goes over this bundle's own retail turf with the
        # 2004 marks filled in (clean_turf): rain and snow turf stay exactly retail (and compress like it), and
        # no old letters show through paint painted at less than full alpha.
        paint, _fits = mm.weather_transfer(base, current, art, snow=False)
        return mm.composite_over(clean_turf(current) if item["scene"] == "field" else current, paint)
    sx, sy = width / item["size"][0], height / item["size"][1]
    rects = item.get("rects") or [[0, 0, item["size"][0], item["size"][1]]]
    result = (current if canvas is None else canvas).copy()
    snow = weather == "s" and cls in DRIFT_CLASSES
    for x0, y0, x1, y1 in rects:
        x0, x1 = int(round(x0 * sx)), int(round(x1 * sx))
        y0, y1 = int(round(y0 * sy)), int(round(y1 * sy))
        piece, _fits = mm.weather_transfer(base, current, art, region=(y0, y1, x0, x1), snow=snow)
        result[y0:y1, x0:x1] = piece[y0:y1, x0:x1]
    return result


def paint_scene(decoded, rec, prefix, code, plan, base, *, cap=256):
    """Author one decoded scene of the bundle ``<prefix><code>`` in place. Returns (bytes, receipt).

    Items that land on the same texture are applied in order: league marks, then reviewed fallback art, then
    the team's art; an item that covers the whole texture replaces what came before it.
    """
    mm = _mm()
    scene = rec.get("name")
    edited = bytearray(decoded)
    system = int(rec["system_bytes"])
    rows = p8_rows(rec)
    receipt = dict(scene=scene, textures=[], skipped=[], palette_cap=cap)
    groups = {}
    for item in plan["items"]:
        if item["dd"]["scene"] != scene:
            continue
        index = variant_index(item, code, rec)
        if index is None:
            receipt["skipped"].append(dict(key=item["key"], reason="not in this bundle"))
            continue
        groups.setdefault(index, []).append(item)
    for index in sorted(groups):
        row = rows[index]
        width, height = int(row["width"]), int(row["height"])
        current, _raw = mm.read_p8(edited, system, row)
        canvas = current
        applied = []
        keys = {i["key"] for i in groups[index]}
        for item in sorted(groups[index], key=lambda i: SOURCE_ORDER.get(i.get("source", "team"), 2)):
            if item["key"].startswith("endzone_S_") and item["key"].replace("_S_", "_N_") in keys:
                continue  # where a bundle shares one end-zone texture for both ends, it takes the north art
            dry = base[(item["dd"]["scene"], item["dd"]["index"])]
            dry = resample(dry, width, height) if dry.shape[:2] != (height, width) else dry
            target = _target_row(prefix, item["key"]) if scene == "stadium" else None
            layered = compose(item, dry, current, _art_at(item, width, height), code[1],
                              cls=(target or {}).get("class"), canvas=canvas)
            canvas = layered
            applied.append(dict(key=item["key"], source=item.get("source", "team"), layer=item["layer"],
                                mark=item.get("mark")))
        colours = mm.write_p8(edited, system, row, canvas, cap)
        receipt["textures"].append(dict(key=applied[-1]["key"], texture=index, size=[width, height], items=applied,
                                        palette_entries=colours))
    return bytes(edited), receipt


def modern_scene_span(data, chunk, prefix, code, plan, base):
    """(refit span, receipt) of one retail scene; a scene the plan does not change keeps its bytes."""
    mm = _mm()
    tx = _tools()[0]
    rec, decoded = mm._scene(data, chunk)
    span = mm.scene_span(data, chunk)
    attempts = []
    for cap in mm.PALETTE_CAPS:
        edited, receipt = paint_scene(decoded, rec, prefix, code, plan, base, cap=cap)
        if edited == decoded:
            return span, dict(receipt, refit=False)
        try:
            rebuilt, info = mm.fit_span(span, edited)
        except tx.TxtrError as exc:
            attempts.append(f"{cap} colours: {exc}")
            continue
        check, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
        require(check == edited, f"{prefix}{code} {rec.get('name')}: refit read-back differs")
        require(rebuilt[:32] == span[:32], f"{prefix}{code} {rec.get('name')}: the refit changed the retail wrapper")
        return rebuilt, dict(receipt, refit=True, fit_attempts=attempts, **info)
    raise ModernVenuesError(f"{prefix}{code} {rec.get('name')} does not fit its span: " + " | ".join(attempts))


def modern_bundle(data, name, plan, base):
    """(modern bundle bytes, edits) for one retail venue bundle."""
    mm = _mm()
    prefix, code = name[:3], code_of(name)
    out = bytearray(data)
    edits = []
    scenes_used = {i["dd"]["scene"] for i in plan["items"]}
    for scene, chunk in sorted(bundle_scenes(data).items(), key=lambda kv: kv[1].offset):
        if scene not in scenes_used:
            continue
        before = mm.scene_span(data, chunk)
        after, receipt = modern_scene_span(data, chunk, prefix, code, plan, base)
        require(len(after) == len(before), f"{name} {scene}: refit escaped its allocation")
        if after == before:
            continue
        out[chunk.offset:chunk.offset + len(before)] = after
        edits.append(dict(kind=scene, offset=chunk.offset, size=len(before), retail=sha(before), applied=sha(after),
                          detail={k: v for k, v in receipt.items() if k != "weather_fit"}))
    return bytes(out), edits


def combined_bundle(retail, graded, name, plan, base, *, outer_index, settings=None):
    """Compose the venue art before the colour grade (field) and compress the shared field once."""
    from . import nfl2k5_modern_color as colour
    mm = _mm()
    tx = _tools()[0]
    require(len(retail) == len(graded), "combined bundle changed allocation")
    prefix, code = name[:3], code_of(name)
    out = bytearray(graded)
    edits = []
    scenes_used = {i["dd"]["scene"] for i in plan["items"]}
    for scene, chunk in sorted(bundle_scenes(retail).items(), key=lambda kv: kv[1].offset):
        if scene not in scenes_used:
            continue
        before = mm.scene_span(retail, chunk)
        if scene == "field":
            attempts = []
            for cap in mm.PALETTE_CAPS:
                def painter(span, field_chunk, cap=cap):
                    rec, decoded = mm._scene(span, field_chunk)
                    return paint_scene(decoded, rec, prefix, code, plan, base, cap=cap)
                try:
                    after, detail = colour.modern_field_scene(before, outer_index=outer_index, settings=settings,
                                                              painter=painter)
                    detail = dict(detail, palette_cap=cap, fit_attempts=attempts)
                    break
                except (tx.TxtrError, ValueError) as exc:
                    attempts.append(f"{cap} colours: {exc}")
            else:
                raise ModernVenuesError(f"{name} field does not fit its span with the colour grade: " + " | ".join(attempts))
        else:
            require(graded[chunk.offset:chunk.offset + len(before)] == before,
                    f"{name} {scene}: the colour grade touched a scene it does not own")
            after, detail = modern_scene_span(retail, chunk, prefix, code, plan, base)
        require(len(after) == len(before), f"{name} {scene}: combined scene escaped its allocation")
        out[chunk.offset:chunk.offset + len(before)] = after
        edits.append(dict(kind=scene, offset=chunk.offset, size=len(before), retail=sha(before), applied=sha(after),
                          detail={k: v for k, v in detail.items() if k != "weather_fit"}))
    return bytes(out), edits


# --- archive access, receipts and state ------------------------------------------------------------------

def receipt_path(source):
    return Path(str(source) + ".venues-2026.json")


def read_receipt(source):
    path = receipt_path(source)
    if not path.is_file():
        return None
    require(path.stat().st_size <= 8 * 1024 * 1024, "the 2026 venue receipt is too large")
    doc = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(doc, dict) and doc.get("schema") == RECEIPT_SCHEMA, "unsupported 2026 venue receipt")
    return doc


def _save_receipt(target, receipt):
    import tempfile
    path = receipt_path(target)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write((json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode("utf-8"))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _entry(archive, pin):
    if pin["outer"] >= len(archive.entries):
        return None
    entry = archive.entries[pin["outer"]]
    if entry.name_id != pin["name_id"] or entry.size != pin["size"]:
        return None
    return entry


def _colour_receipt(source):
    from . import nfl2k5_modern_color as colour
    try:
        return colour.read_image_receipt(source)
    except (OSError, ValueError):
        return None


def _arrowhead_applied(archive, name, colour_receipt):
    """True when Modern Arrowhead (standalone or combined with colour) owns this s13 bundle's bytes."""
    from . import nfl2k5_modern_arrowhead as arrowhead
    try:
        pins = {p["name"]: p for p in arrowhead._pins()["bundles"]}
    except (OSError, ValueError):
        return False
    pin = pins.get(name)
    if pin is None:
        return False
    combined = (colour_receipt or {}).get("modern_arrowhead")
    if combined is not None:
        entry = _entry(archive, pin)
        row = (combined.get("bundles") or {}).get(name) or {}
        return entry is not None and sha(archive.read(entry.virtual_offset, entry.size)) == row.get("applied_sha256")
    return arrowhead._bundle_state(archive, pin) == "applied"


def _sofi_applied(archive, pin, fan_receipt=None):
    """True when SoFi Stadium (b76-u6) wrote this Rams or Chargers bundle: its stadium stretch is the pinned model."""
    try:
        from . import nfl2k5_sofi_model as sofi
        return sofi.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the SoFi option or its pins the bundle is not SoFi's
        return False


def _highmark_applied(archive, pin, fan_receipt=None):
    """True when Highmark Stadium (b76-st) wrote this Bills bundle: its stadium stretch is the pinned model."""
    try:
        from . import nfl2k5_highmark_model as highmark
        return highmark.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the Highmark option or its pins the bundle is not Highmark's
        return False


def _att_applied(archive, pin, fan_receipt=None):
    """True when AT&T Stadium (b76-st2) wrote this Cowboys bundle: its stadium stretch is the pinned model."""
    try:
        from . import nfl2k5_att_model as att
        return att.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the AT&T Stadium option or its pins the bundle is not AT&T Stadium's
        return False


def _levis_applied(archive, pin, fan_receipt=None):
    """True when Levi's Stadium (b76-st2) wrote this 49ers bundle: its stadium stretch is the pinned model."""
    try:
        from . import nfl2k5_levis_model as levis
        return levis.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the Levi's Stadium option or its pins the bundle is not Levi's Stadium's
        return False


def _allegiant_applied(archive, pin, fan_receipt=None):
    """True when Allegiant Stadium (b76-st2) wrote this Raiders bundle: its stadium stretch is the pinned model."""
    try:
        from . import nfl2k5_allegiant_model as allegiant
        return allegiant.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the Allegiant Stadium option or its pins the bundle is not Allegiant Stadium's
        return False


def _mercedes_benz_applied(archive, pin, fan_receipt=None):
    """True when Mercedes-Benz Stadium (b76-st2) wrote this Falcons bundle: its stadium stretch is the pinned model."""
    try:
        from . import nfl2k5_mercedes_benz_model as mercedes_benz
        return mercedes_benz.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the Mercedes-Benz Stadium option or its pins the bundle is not Mercedes-Benz Stadium's
        return False


def _usbank_applied(archive, pin, fan_receipt=None):
    """True when U.S. Bank Stadium (b76-st3) wrote this Vikings bundle: its stadium stretch is the pinned model."""
    try:
        from . import nfl2k5_usbank_model as usbank
        return usbank.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the U.S. Bank Stadium option or its pins the bundle is not its
        return False


def _lucas_oil_applied(archive, pin, fan_receipt=None):
    """True when Lucas Oil Stadium (b76-st3) wrote this Colts bundle: its stadium stretch is the pinned model."""
    try:
        from . import nfl2k5_lucas_oil_model as lucas
        return lucas.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the Lucas Oil Stadium option or its pins the bundle is not its
        return False


def _state_farm_applied(archive, pin, fan_receipt=None):
    """True when State Farm Stadium (b76-st3) wrote this Cardinals bundle: its stretch is the pinned model."""
    try:
        from . import nfl2k5_state_farm_model as state_farm
        return state_farm.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the State Farm Stadium option or its pins the bundle is not its
        return False


def _hard_rock_applied(archive, pin, fan_receipt=None):
    """True when Hard Rock Stadium (b76-st4) wrote this Dolphins bundle: its stretch is the pinned model."""
    try:
        from . import nfl2k5_hard_rock_model as hard_rock
        return hard_rock.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the Hard Rock Stadium option or its pins the bundle is not its
        return False


def _gillette_applied(archive, pin):
    """True when Gillette Stadium (b76-st4) wrote this Patriots bundle: its stretch is the pinned model."""
    try:
        from . import nfl2k5_gillette_model as gillette
        return gillette.bundle_state(archive, pin["name"]) == "applied"
    except Exception:  # noqa: BLE001 - without the Gillette Stadium option or its pins the bundle is not its
        return False


def _lambeau_applied(archive, pin, fan_receipt=None):
    """True when Lambeau Field (b76-st4) wrote this Packers bundle: its stretch is the pinned model."""
    try:
        from . import nfl2k5_lambeau_model as lambeau
        return lambeau.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the Lambeau Field option or its pins the bundle is not its
        return False


def _everbank_applied(archive, pin, fan_receipt=None):
    """True when EverBank Stadium (b76-st4) wrote this Jaguars bundle: its stretch is the pinned model."""
    try:
        from . import nfl2k5_everbank_model as everbank
        return everbank.bundle_state(archive, pin["name"], fan_receipt=fan_receipt) == "applied"
    except Exception:  # noqa: BLE001 - without the EverBank Stadium option or its pins the bundle is not its
        return False


def _board_kit_venues():
    """The venues the modern stadium boards (b76-st3, the tier 2 board kit) can renovate: they keep this option's wall
    art and change geometry only."""
    try:
        from . import nfl2k5_board_kit as board_kit
        return set(board_kit.pinned_venues())
    except Exception:  # noqa: BLE001 - without the board kit no venue is its
        return set()


def _board_kit_applied(archive, pin):
    """True when the modern stadium boards renovated this bundle's stadium scene (on retail or on this option's art)."""
    try:
        from . import nfl2k5_board_kit as board_kit
        return board_kit.bundle_state(archive, pin["name"]) == "applied"
    except Exception:  # noqa: BLE001 - without the board kit or its pins the bundle is not the kit's
        return False


def bundle_state(archive, pin, receipt, colour_receipt):
    """retail / venues / arrowhead / foreign for one venue bundle.

    Retail means the field and stadium scenes are retail, or the field is exactly what the colour receipt
    recorded (the colour grade is not venue art).
    """
    entry = _entry(archive, pin)
    if entry is None:
        return "foreign"
    rows = (receipt or {}).get("bundles") or {}
    if pin["name"] in rows:
        data = archive.read(entry.virtual_offset, entry.size)
        return "venues" if sha(data) == rows[pin["name"]].get("applied_sha256") else "foreign"
    # Model writers retain their checked fan composition pins in the venue sidecar.
    # Delegate to the owner so parent model, span and final hash are all verified.
    fan = ((receipt or {}).get("model_fan_art") or {}).get(pin["name"])
    colour_row = ((colour_receipt or {}).get("bundle_pins") or {}).get(pin["name"]) or {}
    colour_sites = {s.get("kind"): s for s in colour_row.get("sites", ()) if isinstance(s, dict)}
    for site in pin["sites"]:
        have = sha(archive.read(entry.virtual_offset + site["offset"], site["size"]))
        if have == site["retail"]:
            continue
        if site["kind"] == "field" and colour_sites.get("field", {}).get("applied") == have:
            continue
        if pin["name"].startswith(ARROWHEAD_VENUE) and _arrowhead_applied(archive, pin["name"], colour_receipt):
            return "arrowhead"
        if pin["name"][:3] in SOFI_VENUES and _sofi_applied(archive, pin, fan):
            return "sofi"
        if pin["name"][:3] in HIGHMARK_VENUES and _highmark_applied(archive, pin, fan):
            return "highmark"
        if pin["name"][:3] in ATT_VENUES and _att_applied(archive, pin, fan):
            return "att"
        if pin["name"][:3] in LEVIS_VENUES and _levis_applied(archive, pin, fan):
            return "levis"
        if pin["name"][:3] in ALLEGIANT_VENUES and _allegiant_applied(archive, pin, fan):
            return "allegiant"
        if pin["name"][:3] in MERCEDES_BENZ_VENUES and _mercedes_benz_applied(archive, pin, fan):
            return "mercedes_benz"
        if pin["name"][:3] in USBANK_VENUES and _usbank_applied(archive, pin, fan):
            return "usbank"
        if pin["name"][:3] in LUCAS_OIL_VENUES and _lucas_oil_applied(archive, pin, fan):
            return "lucas_oil"
        if pin["name"][:3] in STATE_FARM_VENUES and _state_farm_applied(archive, pin, fan):
            return "state_farm"
        if pin["name"][:3] in HARD_ROCK_VENUES and _hard_rock_applied(archive, pin, fan):
            return "hard_rock"
        if pin["name"][:3] in GILLETTE_VENUES and _gillette_applied(archive, pin):
            return "gillette"
        if pin["name"][:3] in LAMBEAU_VENUES and _lambeau_applied(archive, pin, fan):
            return "lambeau"
        if pin["name"][:3] in EVERBANK_VENUES and _everbank_applied(archive, pin, fan):
            return "everbank"
        if pin["name"][:3] in _board_kit_venues() and _board_kit_applied(archive, pin):
            return "board_kit"
        return "foreign"
    return "retail"


def image_report(source):
    """State and individual bundle results, grouped by venue, plus the ROST names.

    Later model owners validate their pinned spans, including recorded fan art.
    Full-bundle venue receipts remain authoritative for the bundles they own.
    """
    receipt = read_receipt(source)
    colour_receipt = _colour_receipt(source)
    states = set()
    results = {}
    with _outer_image()(source) as archive:
        for prefix, row in venues().items():
            bundles = {pin["name"]: bundle_state(archive, pin, receipt, colour_receipt) for pin in row["bundles"]}
            results[prefix] = dict(team=row["team"], bundles=bundles)
            states.update(bundles.values())
        names_state = rost_state(_read_rost(archive)[1])
    if "foreign" in states or names_state == "foreign":
        state = "foreign"
    else:
        state = "applied" if ("venues" in states or names_state == "applied") else "retail"
    return dict(state=state, venues=results, names_state=names_state)


def readback_details(report):
    """Name every unrecognized bundle without truncating the failing venues."""
    problems = []
    for prefix, row in sorted(report["venues"].items()):
        bad = [f"{name}={state}" for name, state in sorted(row["bundles"].items()) if state == "foreign"]
        if bad:
            problems.append(f"{prefix} ({row['team']}): " + ", ".join(bad))
    problems.append(f"ROST venue names={report['names_state']}")
    return "; ".join(problems)


def image_status(source):
    """retail / applied / foreign across the venue table, later owners and names."""
    return image_report(source)["state"]


status = image_status


def verify(source, *, enabled=True):
    report = image_report(source)
    state = report["state"]
    require(state == ("applied" if enabled else "retail"),
            f"the venue bundles do not match the requested option ({state}): {readback_details(report)}")
    return dict(state=state, enabled=enabled, label=LABEL, runtime_witnessed=False)


def coverage(art):
    """Per venue: the table's team-art targets the art covers and leaves uncovered (field and stadium)."""
    out = {}
    for prefix, row in venues().items():
        venue = art["venues"].get(prefix)
        keys = {i["key"] for i in venue["items"]} if venue else set()
        wanted = [t for t in row.get("targets", ()) if t["class"] in ("wall", "board", "sign", "fan")]

        def hit(target):
            # an item may name the texture by the exporter's key or by one of its material names
            return target["key"] in keys or bool(keys & set(target.get("names", ())))
        known = {t["key"] for t in row.get("targets", ())} | {n for t in row.get("targets", ()) for n in t.get("names", ())}
        out[prefix] = dict(team=row["team"], art=venue is not None,
                           field=sorted(k for k in keys if k in FIELD_KEYS),
                           covered=sorted(t["key"] for t in wanted if hit(t)),
                           uncovered=sorted(t["key"] for t in wanted if not hit(t)),
                           extra=sorted(k for k in keys if k not in known and k not in FIELD_KEYS))
    return out


def venues_to_write(art, *, modern_arrowhead=False, sofi=False, highmark=False, att=False, levis=False,
                    allegiant=False, mercedes_benz=False, usbank=False, lucas_oil=False, state_farm=False,
                    hard_rock=False, gillette=False, lambeau=False, everbank=False):
    """[(prefix, team art or None)]: every venue with team art, plus every other venue when the art root carries
    league marks (their 2004 shields and conference marks); Kansas City stays Modern Arrowhead's when that
    option is on and the art has no Kansas City venue; the Rams and Chargers venues (s23, s24) are SoFi Stadium's
    when that option is on (it paints their fields itself), the Bills' (s03) Highmark Stadium's when its option is on
    (it paints the Bills' field art from this same folder), and the Cowboys' (s07) AT&T Stadium's, the 49ers' (s25)
    Levi's Stadium's, the Raiders' (s20) Allegiant Stadium's, the Falcons' (s01) Mercedes-Benz Stadium's, the
    Vikings' (s15) U.S. Bank Stadium's, the Colts' (s11) Lucas Oil Stadium's, the Cardinals' (s00) State Farm
    Stadium's, the Dolphins' (s14) Hard Rock Stadium's, the Patriots' (s16) Gillette Stadium's, the Packers' (s10)
    Lambeau Field's and the Jaguars' (s12) EverBank Stadium's when their options are on (the same way)."""
    out = []
    for prefix in sorted(venues()):
        if sofi and prefix in SOFI_VENUES:
            continue
        if highmark and prefix in HIGHMARK_VENUES:
            continue
        if att and prefix in ATT_VENUES:
            continue
        if levis and prefix in LEVIS_VENUES:
            continue
        if allegiant and prefix in ALLEGIANT_VENUES:
            continue
        if mercedes_benz and prefix in MERCEDES_BENZ_VENUES:
            continue
        if usbank and prefix in USBANK_VENUES:
            continue
        if lucas_oil and prefix in LUCAS_OIL_VENUES:
            continue
        if state_farm and prefix in STATE_FARM_VENUES:
            continue
        if hard_rock and prefix in HARD_ROCK_VENUES:
            continue
        if gillette and prefix in GILLETTE_VENUES:
            continue
        if lambeau and prefix in LAMBEAU_VENUES:
            continue
        if everbank and prefix in EVERBANK_VENUES:
            continue
        team = art["venues"].get(prefix)
        if team is None and not art.get("league") and not venues()[prefix].get("field_logos"):
            continue
        if prefix == ARROWHEAD_VENUE and modern_arrowhead:
            require(team is None, "Modern Arrowhead and the 2026 venue art would both write the Kansas City "
                    "packages. Turn Modern Arrowhead off (the venue art carries Kansas City) or remove the KC venue folder.")
            continue
        out.append((prefix, team))
    return out


def check_request(source, art_root, *, modern_arrowhead=False, sofi=False, highmark=False, att=False, levis=False,
                  allegiant=False, mercedes_benz=False, usbank=False, lucas_oil=False, state_farm=False,
                  hard_rock=False, gillette=False, lambeau=False, everbank=False):
    """The build's quick check, before any copy: the art folder reads (every file matches its manifest), the
    Kansas City rule holds, the source carries no venue art yet and every venue this build writes is retail in
    its field and stadium scenes (colour-graded fields count as retail). Keys are resolved at write time;
    ``preflight`` (the ``check --source`` command) resolves them all without writing."""
    art = load_art(art_root)
    require(art["venues"] or art["league"], f"no venue art (metlife_team_art/v1 manifests) or league marks under {art_root}")
    todo = venues_to_write(art, modern_arrowhead=modern_arrowhead, sofi=sofi, highmark=highmark, att=att,
                           levis=levis, allegiant=allegiant, mercedes_benz=mercedes_benz,
                           usbank=usbank, lucas_oil=lucas_oil, state_farm=state_farm,
                           hard_rock=hard_rock, gillette=gillette, lambeau=lambeau,
                           everbank=everbank)
    require(read_receipt(source) is None, "this source already carries the 2026 venue art; build from the original retail disc")
    colour_receipt = _colour_receipt(source)
    with _outer_image()(source) as archive:
        for prefix, _team in todo:
            for pin in venues()[prefix]["bundles"]:
                state = bundle_state(archive, pin, None, colour_receipt)
                require(state == "retail", f"{pin['name']} is {state}; build from a supported retail source")
        names_state = rost_state(_read_rost(archive)[1])
        require(names_state == "retail", f"the venue names in the main ROST are {names_state}; build from a supported retail source")
    return dict(venues=[prefix for prefix, _team in todo], team_art=sorted(art["venues"]), league=sorted(art["league"]),
                skipped=art["skipped"])


def preflight(source, art_root, *, modern_arrowhead=False, sofi=False, highmark=False, att=False, levis=False,
              allegiant=False, mercedes_benz=False, usbank=False, lucas_oil=False, state_farm=False,
              hard_rock=False, gillette=False, lambeau=False, everbank=False, progress=None):
    """Check the art folder against the source's retail venue bundles without writing anything.

    Returns {"venues": {prefix: {"items", "notes", "uncovered"}}, "skipped": [...]}.
    """
    say = progress or (lambda message, done, total: None)
    art = load_art(art_root)
    require(art["venues"] or art["league"], f"no venue art (metlife_team_art/v1 manifests) or league marks under {art_root}")
    todo = venues_to_write(art, modern_arrowhead=modern_arrowhead, sofi=sofi, highmark=highmark, att=att,
                           levis=levis, allegiant=allegiant, mercedes_benz=mercedes_benz,
                           usbank=usbank, lucas_oil=lucas_oil, state_farm=state_farm,
                           hard_rock=hard_rock, gillette=gillette, lambeau=lambeau,
                           everbank=everbank)
    receipt = read_receipt(source)
    require(receipt is None, "this source already carries the 2026 venue art; build from the original retail disc")
    colour_receipt = _colour_receipt(source)
    out = {}
    with _outer_image()(source) as archive:
        for index, (prefix, venue) in enumerate(todo):
            say(f"2026 venue art: checking {prefix} ({venues()[prefix]['team']})", index, len(todo))
            row = venues()[prefix]
            for pin in row["bundles"]:
                state = bundle_state(archive, pin, None, colour_receipt)
                require(state == "retail", f"{pin['name']}: {state} bundle; build from a supported retail source")
            bundles = {}
            for pin in row["bundles"]:
                entry = _entry(archive, pin)
                bundles[pin["name"]] = archive.read(entry.virtual_offset, entry.size)
            plan = plan_venue(prefix, venue, bundles, art["league"])
            out[prefix] = dict(team=venues()[prefix]["team"], team_art=venue is not None, items=len(plan["items"]),
                               league=sum(1 for i in plan["items"] if i.get("source") == "league"),
                               notes=plan["notes"], uncovered=plan["uncovered"])
    return dict(venues=out, skipped=art["skipped"], league_marks=sorted(art["league"]))


# --- apply -------------------------------------------------------------------------------------------------

def _workers(requested=None):
    if requested is not None:
        return max(1, int(requested))
    return max(1, min(16, (os.cpu_count() or 2) // 2))


def _compile_job(job):
    """Worker: one bundle. job = (name, data, graded or None, plan, base, outer, settings)."""
    name, data, graded, plan, base, outer, settings = job
    if graded is None:
        after, edits = modern_bundle(data, name, plan, base)
    else:
        after, edits = combined_bundle(data, graded, name, plan, base, outer_index=outer, settings=settings)
    return name, after, edits


def _stream(jobs, workers):
    """Yield (name, after, edits) for every job, compiled in worker processes with a bounded queue."""
    count = _workers(workers)
    if count == 1:
        for job in jobs:
            yield _compile_job(job)
        return
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    with ProcessPoolExecutor(max_workers=count) as pool:
        pending = set()
        iterator = iter(jobs)
        exhausted = False
        while True:
            while not exhausted and len(pending) < 2 * count:
                try:
                    pending.add(pool.submit(_compile_job, next(iterator)))
                except StopIteration:
                    exhausted = True
            if not pending:
                return
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                yield future.result()


def apply_to_image(target, art_root, *, progress=None, retail_source=None, modern_arrowhead=False, workers=None,
                   sofi=False, highmark=False, att=False, levis=False, allegiant=False, mercedes_benz=False,
                   usbank=False, lucas_oil=False, state_farm=False, hard_rock=False, gillette=False, lambeau=False, everbank=False):
    """Build-only: write the venue art into ``target`` (the caller's disposable output image or loose folder).

    Without Modern colour the bundles are read from ``target`` itself (their field and stadium scenes must be
    retail; other chunks keep whatever earlier steps wrote); with it (a colour receipt beside the target) the
    retail bundles come from ``retail_source`` and the field art is composed before the grade. The receipt
    beside the target records every written bundle; the colour receipt, when present, is updated so Modern
    colour still recognizes its own bytes.
    """
    from copy import deepcopy
    from . import nfl2k5_modern_color as colour
    say = progress or (lambda message, done, total: None)
    art = load_art(art_root)
    require(art["venues"] or art["league"], f"no venue art (metlife_team_art/v1 manifests) or league marks under {art_root}")
    todo = venues_to_write(art, modern_arrowhead=modern_arrowhead, sofi=sofi, highmark=highmark, att=att,
                           levis=levis, allegiant=allegiant, mercedes_benz=mercedes_benz,
                           usbank=usbank, lucas_oil=lucas_oil, state_farm=state_farm,
                           hard_rock=hard_rock, gillette=gillette, lambeau=lambeau,
                           everbank=everbank)
    require(read_receipt(target) is None, "the output already carries the 2026 venue art")
    colour_receipt = _colour_receipt(target)
    combined = colour_receipt is not None
    if combined:
        require(retail_source is not None, "the 2026 venue art on a colour build needs the original retail source")
        require(colour.image_status(target, receipt=colour_receipt) == colour_receipt["state"],
                "colour bytes differ from their receipt; rebuild from the original retail disc")
    receipt = dict(schema=RECEIPT_SCHEMA, label=LABEL, runtime_witnessed=False, table_sha256=sha(TABLE_PATH.read_bytes()),
                   combined_colour=combined, art_root=art["root"], skipped=art["skipped"], venues={}, bundles={})
    from . import nfl2k5_stadium_shared_art as shared
    receipt["shared_art_table_sha256"] = sha(shared.TABLE_PATH.read_bytes())
    receipt["event_fields_sha256"] = sha(shared.EVENT_PATH.read_bytes())
    new_colour = deepcopy(colour_receipt) if combined else None
    order = [prefix for prefix, _team in todo]
    with _outer_image()(target) as output:
        for prefix in order:
            for pin in venues()[prefix]["bundles"]:
                state = bundle_state(output, pin, None, colour_receipt)
                require(state == "retail", f"{pin['name']}: {state} bundle; rebuild from a supported retail source")
    source_image = retail_source if combined else target
    befores, plans = {}, {}

    def jobs():
        for vindex, prefix in enumerate(order):
            venue = art["venues"].get(prefix)
            row = venues()[prefix]
            say(f"2026 venue art: {prefix} ({row['team']})", vindex, len(order))
            pins = {p["name"]: p for p in row["bundles"]}
            bundles, graded = {}, {}
            with _outer_image()(source_image) as source:
                for name, pin in pins.items():
                    entry = _entry(source, pin)
                    require(entry is not None, f"{name}: the source entry differs from the venue table")
                    data = source.read(entry.virtual_offset, entry.size)
                    if combined:
                        require(sha(data) == pin["retail_sha256"], f"{name}: the retail bundle differs from the venue table")
                    bundles[name] = data
            if combined:
                with _outer_image()(target) as output:
                    for name, pin in pins.items():
                        entry = _entry(output, pin)
                        data = output.read(entry.virtual_offset, entry.size)
                        require(sha(data) == colour_receipt["bundle_pins"][name]["applied_sha256"],
                                f"{name}: the colour bundle changed after its receipt")
                        graded[name] = data
            plan = plan_venue(prefix, venue, bundles, art["league"])
            base = plan.pop("base")
            plans[prefix] = plan
            for name in bundle_names(prefix):
                befores[name] = sha(graded.get(name, bundles[name]))
                yield (name, bundles[name], graded.get(name), plan, base, pins[name]["outer"],
                       (colour_receipt or {}).get("settings"))

    written = 0
    finished = 0
    for name, after, edits in _stream(jobs(), workers):
        finished += 1
        say(f"2026 venue art: {name} ({finished} of {9 * len(order)})", finished, 9 * len(order))
        pin = next(p for p in venues()[name[:3]]["bundles"] if p["name"] == name)
        if sha(after) == befores[name]:
            continue
        with _outer_image()(target, writable=True) as output:
            entry = _entry(output, pin)
            require(sha(output.read(entry.virtual_offset, entry.size)) == befores[name], f"{name}: changed before write")
            require(output.write(entry.virtual_offset, after) == len(after), f"{name}: short write")
            require(output.read(entry.virtual_offset, entry.size) == after, f"{name}: write-back differs")
        written += 1
        receipt["bundles"][name] = dict(outer=pin["outer"], size=pin["size"], retail_sha256=pin["retail_sha256"],
                                        applied_sha256=sha(after),
                                        sites=[{k: e[k] for k in ("kind", "offset", "size", "retail", "applied")}
                                               for e in edits])
        if combined:
            crow = new_colour["bundle_pins"][name]
            new_colour["bundle_pins"][name] = dict(crow, applied_sha256=sha(after), sites=[dict(
                site, applied=sha(after[site["offset"]:site["offset"] + site["size"]])) for site in crow["sites"]])
    with _outer_image()(target, writable=True) as output:
        receipt["venue_names"] = apply_rost(output)
    for prefix in order:
        venue, plan = art["venues"].get(prefix), plans[prefix]
        receipt["venues"][prefix] = dict(team=venues()[prefix]["team"], manifest=venue["manifest"] if venue else None,
                                         digest=venue["digest"] if venue else None, items=len(plan["items"]),
                                         league=sum(1 for i in plan["items"] if i.get("source") == "league"),
                                         notes=plan["notes"], uncovered=plan["uncovered"],
                                         bundles=[n for n in bundle_names(prefix) if n in receipt["bundles"]])
    receipt["league_marks"] = {m: v["sha256"] for m, v in art["league"].items()}
    if combined:
        new_colour["modern_venues_2026"] = dict(table_sha256=receipt["table_sha256"],
                                                venues={p: v["digest"] for p, v in receipt["venues"].items()},
                                                bundles=sorted(receipt["bundles"]))
        require(colour.image_status(target, receipt=new_colour) == new_colour["state"], "combined colour read-back failed")
        colour._save_image_receipt(target, new_colour)
    _save_receipt(target, receipt)
    say("2026 venue art: done", 1, 1)
    result = verify(target, enabled=True)
    return dict(result, venues=len(receipt["venues"]), bundles_written=written, combined_colour=combined,
                skipped=art["skipped"], coverage={p: v["uncovered"] for p, v in receipt["venues"].items()},
                venue_names=receipt["venue_names"])


# --- author time: the venue table --------------------------------------------------------------------------

def _table_venue(job):
    """Worker for record_table: one venue's table row."""
    source, prefix, team, targets, league, league_art = job
    mm = _mm()
    ids = {name_id(name): name for name in bundle_names(prefix)}
    bundles, decoded = [], {}
    with _outer_image()(source) as archive:
        entries = {ids[e.name_id]: e for e in archive.entries if e.name_id in ids}
        require(set(entries) == set(ids.values()), f"{prefix}: bundles missing from the source")
        for name in bundle_names(prefix):
            entry = entries[name]
            data = archive.read(entry.virtual_offset, entry.size)
            scenes = bundle_scenes(data)
            sites = []
            for scene in SCENES:
                span = mm.scene_span(data, scenes[scene])
                sites.append(dict(kind=scene, offset=scenes[scene].offset, size=len(span), retail=sha(span)))
            bundles.append(dict(name=name, outer=entry.index, name_id=entry.name_id, size=entry.size,
                                retail_sha256=sha(data), sites=sites))
            decoded[code_of(name)] = decode_scenes(data)
    dd_field, _ = decoded["dd"]["field"]
    materials = rows_by_material(dd_field)
    split = any(materials.get(f"endzone_S_{p}") != materials.get(f"endzone_N_{p}") for p in END_ZONE_PARTS)
    dd_rec, dd_dec = decoded["dd"]["stadium"]
    rows = []
    for t in targets:
        index = t["index"]
        dd_row = p8_rows(dd_rec)[index]
        require(export_key(dd_row.get("mapped_material_names")) == t["key"], f"{prefix}: target {t['key']} moved")
        variants, scores = {}, {}
        found_all = resolve_variants(index, {code: decoded[code]["stadium"] for code in CODES})
        for code in CODES:
            found, score = found_all[code]
            rec = decoded[code]["stadium"][0]
            if found is None:
                variants[code] = None
            else:
                r = p8_rows(rec)[found]
                variants[code] = [found, int(r["width"]), int(r["height"])]
            scores[code] = round(score, 3)
        rows.append(dict(key=t["key"], texture=index, size=[int(dd_row["width"]), int(dd_row["height"])],
                         names=list(dd_row.get("mapped_material_names") or ()), variants=variants,
                         match=scores, cutout=bool(t.get("cutout")), note=t["note"], **{"class": t["cls"]}))
    marks = []
    for entry in league:
        scene = entry["scene"]
        rec, dec = decoded["dd"][scene]
        row = p8_rows(rec)[entry["texture"]]
        require(export_key(row.get("mapped_material_names")) == entry["key"], f"{prefix}: league target {entry['key']} moved")
        out = dict(scene=scene, key=entry["key"], texture=entry["texture"], size=[int(row["width"]), int(row["height"])],
                   rect=list(entry["rect"]), mark=entry["mark"], style=entry.get("style", "colour"),
                   found=entry.get("found", ""))
        if scene == "field":
            material = (row.get("mapped_material_names") or [None])[0]
            out["material"] = material
            out["variants"] = {code: (lambda r, i: [i, int(r["width"]), int(r["height"])] if r is not None else None)(
                p8_rows(decoded[code]["field"][0]).get(rows_by_material(decoded[code]["field"][0]).get(material)),
                rows_by_material(decoded[code]["field"][0]).get(material)) for code in CODES}
        else:
            found_all = resolve_variants(entry["texture"], {code: decoded[code]["stadium"] for code in CODES})
            out["variants"] = {}
            for code in CODES:
                vindex, _score = found_all[code]
                vrow = p8_rows(decoded[code]["stadium"][0]).get(vindex) if vindex is not None else None
                out["variants"][code] = [vindex, int(vrow["width"]), int(vrow["height"])] if vrow is not None else None
        marks.append(out)
    art_rows = []
    for entry in league_art:
        index = find_stadium_texture(dd_rec, entry["key"])
        require(index is not None, f"{prefix}: no {entry['key']} texture for the league art")
        row = p8_rows(dd_rec)[index]
        found_all = resolve_variants(index, {code: decoded[code]["stadium"] for code in CODES})
        variants = {}
        for code in CODES:
            vindex, _score = found_all[code]
            vrow = p8_rows(decoded[code]["stadium"][0]).get(vindex) if vindex is not None else None
            variants[code] = [vindex, int(vrow["width"]), int(vrow["height"])] if vrow is not None else None
        art_rows.append(dict(key=entry["key"], texture=index, size=[int(row["width"]), int(row["height"])],
                             art=entry["art"], sha256=entry["sha256"], rects=entry["rects"], variants=variants))
    return prefix, dict(team=team["team"], stadium=team["stadium"],
                        field=dict(endzones="split" if split else "shared", center_logo="center_logo" in materials),
                        bundles=bundles, targets=rows, league=marks, league_art=art_rows, extras=[])


def record_table(source, targets_path, out_path=TABLE_PATH, *, progress=None, workers=None, league_path=None):
    """Author-time: the venue table from a retail source and the census targets (class, key, texture per venue).

    For every home venue except the Giants and Jets: the nine bundles with their retail SHA-256 and the field and
    stadium scene spans; the field layout (shared or split end zones, a midfield texture or not); every target's
    texture in each bundle (match_texture) with its size and match score.
    """
    say = progress or (lambda message, done, total: None)
    from . import nfl2k5_roster_records as rr
    targets = json.loads(Path(targets_path).read_text(encoding="utf-8"))
    league = json.loads(Path(league_path).read_text(encoding="utf-8")) if league_path else {}
    mm = _mm()
    doc = dict(schema=TABLE_SCHEMA, label=LABEL, skipped={v: "Modern MetLife" for v in METLIFE_VENUES},
               note="Home venues from the retail ROST (+0x114 of each team record); retail pins and texture maps from "
                    "the user's retail disc; targets from job u4's census (class: wall, board, sign, fan, colour, "
                    "league). No retail bytes.", venues={})
    with _outer_image()(source) as archive:
        rost_entry = archive.entries[mm.ROST_OUTER_INDEX]
        body = archive.read(rost_entry.virtual_offset, rost_entry.size)[rr.RESOURCE_HEADER_SIZE:]
    roster = rr.RosterDocument(body, base=0)
    records = dict(mm._stadium_records(body))
    teams = {}
    for team in roster.teams[:32]:
        fields = records[roster.stadiums[team.stadium_index].offset]
        teams[fields["asset_code"][1]] = dict(team=team.abbreviation, stadium=fields["name"][1].strip())
    order = sorted(p for p in teams if p not in METLIFE_VENUES)
    league_art = [dict(entry, sha256=sha((DATA_DIR / entry["art"]).read_bytes())) for entry in LEAGUE_ART]
    jobs = [(str(source), prefix, teams[prefix], targets.get(prefix, {}).get("targets", ()), league.get(prefix, ()),
             league_art) for prefix in order]
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=_workers(workers)) as pool:
        for done, (prefix, row) in enumerate(pool.map(_table_venue, jobs)):
            say(f"venue table: {prefix}", done + 1, len(jobs))
            doc["venues"][prefix] = row
    if ARROWHEAD_VENUE in doc["venues"]:
        doc["venues"][ARROWHEAD_VENUE]["extras"] = _arrowhead_extras()
    for prefix, extras in TABLE_EXTRAS.items():
        if prefix in doc["venues"]:
            kept = doc["venues"][prefix]["extras"] if prefix == ARROWHEAD_VENUE else []   # Modern Arrowhead's come first
            doc["venues"][prefix]["extras"] = kept + _table_extras(extras)
    Path(out_path).write_text(table_text(doc), encoding="utf-8", newline="\n")
    return doc


def table_text(doc):
    """The table as indented JSON: the release checker refuses any whitespace-free run over 4,096 characters
    (a guard against embedded blobs), so the table is never written compactly."""
    return json.dumps(doc, indent=1, sort_keys=True) + "\n"


# Modern Arrowhead's reviewed art that fills what a Kansas City venue folder leaves out. Its yard marker art
# (yardside.png, yardfront.png) is left out on purpose: those two textures are the orange sideline yard-number
# boxes, not wall pads, and keep their retail numbers here.
ARROWHEAD_EXTRAS = (("field", "endzone_N_L", "full", "endzone_L.png"), ("field", "endzone_N_M", "full", "endzone_M.png"),
                    ("field", "endzone_N_R", "full", "endzone_R.png"), ("field", "center_logo", "full", "center_logo.png"),
                    ("stadium", "seat03", "full", "seat03.png"), ("stadium", "seat02_seat01", "full", "seat_rows.png"),
                    ("stadium", "ad01", "full", "ad01.png"), ("stadium", "banner_corp", "full", "banner_corp.png"),
                    ("stadium", "banner_home_team", "full", "banner_home_team.png"),
                    ("stadium", "banner_home_player", "full", "banner_home_player.png"),
                    ("stadium", "banner_away_team", "full", "banner_away_team.png"),
                    ("stadium", "tarpGreen", "full", "tarp_red.png"))


# Reviewed name fixes the table carries for venues whose team art leaves a texture's old name (st2, 2026-09-28):
# (scene, key, layer, art under data/nfl2k5_modern_venues_2026[, rects]); an overlay paints only its opaque pixels, a
# full layer with rects redraws only those rectangles, under the team's own art for the same texture.
# s27 lambert12: the cloth on Buccaneer Cove's ship reads TAMPA BAY STADIUM (the building the stadium replaced in
# 1998); tools/nfl2k5_modern_venues_2026_art.py --tb-ship-banner draws RAYMOND JAMES STADIUM in plain type over it.
# (The same texture is also material lambert98, so both owners take it.)
# s27 lambert63: its two rows read TAMPA B / AY STADIUM end to end along both sideline fascias (the SN audit);
# --tb-fascia-name draws RAYMOND JAMES STADIUM along that run in the sign's own colours (the rows only; the 2004
# league marks below them are not drawn by the scene).
# s13 ad01 (main's policy check): the Kansas City folder's own ad01 item (u4's two slots) keeps Modern Arrowhead's
# fallback from applying, so the retail sponsors stay around the slots: ESPN THE MAGAZINE and ESPN VIDEOGAMES -> ESPN,
# MOTOROLA -> NFL NETWORK, and the parts of PLAYERS INC and VISUAL CONCEPTS that u4's ARROWHEAD STADIUM slot leaves
# in view -> NFLPA and NFL+ (--kc-cells).
# s22 ad_bb01 and ad_bb02 (main, 2026-09-28): d2's 9/23 scoreboard art, never brought under u4's policy, draws the
# Acrisure A mark and three Nike swooshes; over the team's art, ACRISURE STADIUM becomes plain type and each swoosh a
# PLAY 60 type panel (tools/nfl2k5_modern_venues_2026_art.py --pit-cells; the ad_bb01 column is drawn turned a
# quarter clockwise, as the scene lays it along the scoreboard's lower-left panel).
# s29 banner01 and exit01: the defunct 2004 sponsors u4's Washington art keeps (main, 2026-09-28, under u4's league
# sponsor policy, U4_MODERN_VENUES section 10d): MOTOROLA -> NFL NETWORK, Reebok -> PLAY 60, ESPN VIDEOGAMES -> ESPN
# (tools/nfl2k5_modern_venues_2026_art.py --was-sponsor-cells). Current brands (ESPN, SportsCenter, Riddell, Wilson,
# Gatorade, ESPN Radio) stay retail; u4's own banner01 slots (the COMMANDERS type) are left to the team's art.
# s26 (the SN audit and the same policy): the tower's name band in lambert73 reads SEAHAWKS STADIUM -> LUMEN FIELD;
# the tower's panels carry MOTOROLA and ESPN VIDEOGAMES (lambert70) -> NFL NETWORK and ESPN, its message board a
# Visual Concepts welcome (lambert69) -> NFL+, and lambert74 Reebok and ESPN THE MAGAZINE -> PLAY 60 and ESPN
# (tools/nfl2k5_modern_venues_2026_art.py --sea-cells).
SEA_LAMBERT73_RECTS = ((0, 92, 128, 128),)
SEA_LAMBERT70_RECTS = ((0, 2, 128, 24), (0, 104, 128, 126))
SEA_LAMBERT69_RECTS = ((0, 0, 64, 39),)
SEA_LAMBERT74_RECTS = ((0, 0, 64, 32), (0, 32, 64, 64))
WAS_BANNER01_RECTS =((1, 49, 125, 74), (128, 49, 255, 74), (129, 96, 206, 124), (129, 126, 192, 141),
                      (192, 126, 255, 141), (1, 160, 99, 179), (100, 160, 198, 179), (1, 180, 130, 203),
                      (129, 233, 188, 256))
WAS_EXIT01_RECTS = ((0, 0, 64, 13),)
TB_LAMBERT63_RECTS = ((0, 2, 128, 19), (0, 23, 128, 40))
PIT_AD_BB01_RECTS = ((0, 0, 191, 76), (192, 0, 240, 96), (192, 96, 240, 192))
PIT_AD_BB02_RECTS = ((130, 86, 254, 162),)
KC_AD01_RECTS = ((128, 2, 206, 57), (0, 148, 104, 171), (0, 173, 103, 208), (158, 172, 206, 192), (105, 209, 128, 233))
TABLE_EXTRAS = {"s27": (("stadium", "lambert12", "overlay", "extras/s27_lambert12.png"),
                        ("stadium", "lambert63", "full", "extras/s27_lambert63.png", TB_LAMBERT63_RECTS)),
                "s26": (("stadium", "lambert73", "full", "extras/s26_lambert73.png", SEA_LAMBERT73_RECTS),
                        ("stadium", "lambert70", "full", "extras/s26_lambert70.png", SEA_LAMBERT70_RECTS),
                        ("stadium", "lambert69", "full", "extras/s26_lambert69.png", SEA_LAMBERT69_RECTS),
                        ("stadium", "lambert74", "full", "extras/s26_lambert74.png", SEA_LAMBERT74_RECTS)),
                "s13": (("stadium", "ad01", "full", "extras/s13_ad01.png", KC_AD01_RECTS),),
                "s22": (("stadium", "ad_bb01", "full", "extras/s22_ad_bb01.png", PIT_AD_BB01_RECTS, "over"),
                        ("stadium", "ad_bb02", "full", "extras/s22_ad_bb02.png", PIT_AD_BB02_RECTS, "over")),
                "s29": (("stadium", "banner01", "full", "extras/s29_banner01.png", WAS_BANNER01_RECTS),
                        ("stadium", "exit01", "full", "extras/s29_exit01.png", WAS_EXIT01_RECTS))}


def _table_extras(extras):
    out = []
    for scene, key, layer, png, *rest in extras:
        path = DATA_DIR / png
        require(path.is_file(), f"reviewed art {png} is missing")
        row = {"scene": scene, "key": key, "layer": layer, "art": png, "from": "table", "sha256": sha(path.read_bytes())}
        if rest:
            row["rects"] = [list(r) for r in rest[0]]
        if rest[1:] == ["over"]:
            row["over"] = True
        out.append(row)
    return out


def _arrowhead_extras():
    out = []
    for scene, key, layer, png in ARROWHEAD_EXTRAS:
        path = arrowhead_art_path(png)
        require(path.is_file(), f"Modern Arrowhead art {png} is missing")
        out.append({"scene": scene, "key": key, "layer": layer, "art": png, "from": "modern_arrowhead",
                    "sha256": sha(path.read_bytes())})
    return out


# st3's board-kit venues (st3, job st7, 2026-09-28; the SN stale-name audit and main's calls), on st2's rect extras
# as they are (tools/nfl2k5_modern_venues_2026_st3_art.py draws the PNGs):
# s30 lambert39: the header "at Cleveland Browns Stadium" that the south upper fascia still draws (group268, V 0 to
# 0.0917) becomes HUNTINGTON BANK FIELD in plain type; its MOTOROLA panel (on the 2004 boards) becomes NFL NETWORK.
# s17 swall3: the field-wall posters' 2004 players photo and STALLWORTH/BENTLEY strip become SAINTS and WHO DAT in plain
# type (U4_MODERN_VENUES 10c listed the photo; main chose plain type); the helmet and the fleur-de-lis stay retail.
# s17 corp_temp_adbanner01 and 02 (candidate E's Superdome lab, 2026-09-29): the sponsor atlases of the fascia ribbons
# and the panels round the Welcome board, under the same policy: MOTOROLA -> NFL NETWORK, Reebok -> PLAY 60, ESPN THE
# MAGAZINE -> ESPN, PLAYERS INC -> NFLPA (ESPN, ESPN Radio, Gatorade, Riddell, Wilson and the NFC shield stay).
# s37 texscore01 and texscore02: the defunct 2004 cells under u4's sponsor policy (10d): MOTOROLA -> NFL NETWORK,
# Reebok -> PLAY 60, ESPN VIDEOGAMES and ESPN THE MAGAZINE -> ESPN, the Visual Concepts credit -> NFL+; u4's own
# Texans slots compose over them. Denver's adBoard02 and every banner_corp are already u4's (its 10a rows and the
# league sponsor sheet).
CLE_LAMBERT39_RECTS = ((0, 1, 128, 11), (1, 19, 127, 39))
NO_SWALL3_RECTS = ((0, 0, 128, 64), (0, 65, 128, 77))
NO_ADBANNER01_RECTS = ((0, 0, 64, 32), (0, 32, 64, 64))
NO_ADBANNER02_RECTS = ((0, 0, 128, 31), (35, 32, 67, 64), (67, 32, 128, 64), (65, 64, 128, 96), (0, 96, 35, 128))
HOU_TEXSCORE01_RECTS = ((183, 52, 256, 90), (183, 90, 256, 131), (0, 155, 124, 194))
HOU_TEXSCORE02_RECTS = ((168, 26, 254, 48), (163, 114, 254, 140), (163, 142, 254, 168), (4, 152, 162, 172))
TABLE_EXTRAS.update({
    "s30": (("stadium", "lambert39", "full", "extras/s30_lambert39.png", CLE_LAMBERT39_RECTS),),
    "s17": (("stadium", "swall3", "full", "extras/s17_swall3.png", NO_SWALL3_RECTS),
            ("stadium", "corp_temp_adbanner01", "full", "extras/s17_corp_temp_adbanner01.png", NO_ADBANNER01_RECTS),
            ("stadium", "corp_temp_adbanner02", "full", "extras/s17_corp_temp_adbanner02.png", NO_ADBANNER02_RECTS)),
    "s37": (("stadium", "texscore01", "full", "extras/s37_texscore01.png", HOU_TEXSCORE01_RECTS),
            ("stadium", "texscore02", "full", "extras/s37_texscore02.png", HOU_TEXSCORE02_RECTS)),
})


# The league-wide sweep for defunct 2004 brand logos (st3, 2026-09-29; main's call after candidate E's Superdome lab):
# the logo-only cells the OCR lists missed (the Motorola batwing, the Reebok vector, the Players Inc and ESPN THE
# MAGAZINE marks, the ESPN VIDEOGAMES logo, the Visual Concepts logo, and the league cloths' TEAM NFL, PLAY FOOTBALL and
# COACHES ASSOCIATION), under the same policy, in u4's type panels (tools/nfl2k5_modern_venues_2026_st3_art.py,
# SWEEP_CELLS). The owners of these venues' other work: s02, s09 and s30 st3; s04, s27 and s29 st2's board kit
# venues; s28 u4's art alone (Soldier Field's two fence cells are fb2's shared-art residual items, c3407046). Cleveland's LIGHT_jumbotronA1 (an ESPN VIDEOGAMES cell on the old boards) is
# left out: it is the board kit's freed slot, which the venue art never paints (the kit's repaint, the ribbons' art,
# takes it when the kit is on).
SWEEP_RECTS = {
    ("s02", "ad03"): ((4, 59, 125, 75),),
    ("s04", "panthers_score01"): ((0, 17, 68, 31), (1, 70, 97, 87), (99, 50, 127, 78)),
    ("s04", "panthers_score02"): ((110, 15, 128, 54), (99, 96, 107, 126)),
    ("s09", "sign02_sign04"): ((2, 88, 110, 169),),
    ("s27", "lambert63"): ((6, 64, 56, 95), (82, 63, 114, 94), (6, 95, 56, 128)),
    ("s27", "lambert64"): ((0, 32, 64, 64),),
    ("s27", "lambert65"): ((0, 0, 64, 32), (0, 32, 64, 64)),
    ("s28", "ad_bb02"): ((129, 0, 254, 25), (194, 97, 230, 179)),
    ("s29", "ad_bb01_LIGHT_ad_bb01"): ((2, 132, 127, 193), (4, 193, 126, 256)),
    ("s29", "ad_bb02"): ((4, 5, 124, 63),),
    ("s29", "banner_home_team"): ((1, 1, 65, 40), (1, 40, 65, 62), (66, 1, 127, 61)),
    ("s30", "LIGHT_jumbotronB1"): ((0, 0, 92, 67), (0, 70, 93, 128)),
    ("s30", "jumbotronE1"): ((0, 17, 64, 45),),
    ("s30", "lambert40"): ((1, 1, 31, 14), (2, 15, 30, 30), (35, 33, 63, 63)),
}


def _sweep_art(prefix, key):
    """The sweep's PNG for one texture (s27 lambert63's logos beside st2's name rows take their own file)."""
    return f"extras/{prefix}_{key}_logos.png" if (prefix, key) == ("s27", "lambert63") else f"extras/{prefix}_{key}.png"


for (_prefix, _key), _rects in SWEEP_RECTS.items():
    TABLE_EXTRAS[_prefix] = TABLE_EXTRAS.get(_prefix, ()) + (("stadium", _key, "full", _sweep_art(_prefix, _key), _rects),)
del _prefix, _key, _rects


# Paycor Stadium's one residual cell, moved here from fb2's shared-art catalog (c3407046, design row s06 signsA1) when
# tier 3 put s06 on the board kit: the shared-art catalog leaves board-kit venues to this table (its EXCLUDED list,
# st3's job st9). The cell is the tip of the Reebok vector above u4's [86, 88, 169, 128] rectangle, and the whole panel
# is refilled with PLAY 60 in fb2's type. The PNG is fb2's, byte for byte (tools/nfl2k5_residual_sponsor_art.py on
# job/b76-ev drew it). It goes over the team's art, as the shared-art item did, so u4's panel does not cut it off.
CIN_SIGNSA1_RECTS = ((86, 83, 169, 126),)
TABLE_EXTRAS["s06"] = TABLE_EXTRAS.get("s06", ()) + (
    ("stadium", "signsA1", "full", "extras/s06_signsA1.png", CIN_SIGNSA1_RECTS, "over"),)


# --- command line --------------------------------------------------------------------------------------------

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_modern_venues_2026")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status"); s.add_argument("source")
    c = sub.add_parser("check", help="check an art folder (manifests, hashes, sizes) and print its coverage")
    c.add_argument("art_root"); c.add_argument("--source", help="also resolve every item against this retail disc")
    r = sub.add_parser("record-table"); r.add_argument("source"); r.add_argument("targets")
    r.add_argument("--league", help="league mark targets (u4 census: the 2004 shields and conference marks)")
    r.add_argument("--out", default=str(TABLE_PATH))
    args = parser.parse_args(argv)
    if args.command == "status":
        print(image_status(args.source))
        return 0
    if args.command == "check":
        art = load_art(args.art_root)
        report = dict(venues=sorted(art["venues"]), skipped=art["skipped"], coverage=coverage(art))
        if args.source:
            report["preflight"] = preflight(args.source, args.art_root)
        print(json.dumps(report, indent=1))
        return 0
    doc = record_table(args.source, args.targets, args.out, progress=lambda m, d, t: print(f"  {m}", flush=True),
                       league_path=args.league)
    print(json.dumps({p: dict(team=v["team"], targets=len(v["targets"]), field=v["field"],
                              unmatched={t["key"]: [c for c, x in t["variants"].items() if x is None]
                                         for t in v["targets"] if None in t["variants"].values()})
                      for p, v in doc["venues"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

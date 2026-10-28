"""Game-accurate uniforms for the 25th Anniversary moments as NEW kit slots (ek1, Noah 10/17). EXPERIMENTAL / UNWITNESSED.

Noah asked that every team in the 25th Anniversary mode wear the uniform it wore in that game. Job ek1 compared all
102 moment sides with per-game references (``data/nfl2k5_moment_kits.json`` lists the evidence): 88 sides already
select a matching kit. For the rest this stage, run on the Studio build copy after every other uniform writer:

* adds each missing look as a NEW style index of its franchise (``free_index_rule``: no kit package and no aggregate
  member at that index on the copy). Nothing existing is replaced and no modern kit changes;
* composes the two kit packages ``<code>h<S>.iff`` / ``<code>a<S>.iff`` from kits already on the copy: a whole kit, a
  colour-swapped H/A set (a package does not know its letter: chunk 0 is the same for H and A), or chunks of several
  kits, with the far-player atlas mixed by the era-kit helper and small vector art (``nfl2k5_kit_fixes_2026``'s
  compiler) where a donor carries a mark the game did not have;
* adds the nine aggregate card members of the new index (logos: logo, helm_a, helm_h, unif_a, unif_h; mini: logo_s,
  mini_h, mini_a; flipchip) as renamed copies of the donors' members;
* gives the new index a year pair in the moment's own team file only (E2A90: an index exists for a team record when
  its pair is non-zero), so modern Team Select, which reads the main roster, never offers it, while the historic team
  can select it;
* points the moment sides at their kits (SITU +0x58 away, +0x5C home), including sides that switch to an existing
  kit that matches the game better.

The packages are appended as new outer entries at the end of the archive (``nfl2k5_historic_styles.rewrite_archive``).
All inputs are read before any write; replay on the output is a no-op; any other state of a target index refuses.
With the SOFTDRINK donors (``data/nfl2k5_moment_kits_pins.json``) every composed package must equal its pin.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_moment_kits.json"
PINS = ROOT / "data/nfl2k5_moment_kits_pins.json"
SCHEMA = "nfl2k5_moment_kits/v1"
PIN_SCHEMA = "nfl2k5_moment_kits_pins/v1"
OWNER = "nfl2k5_moment_kits"
FILLER = "ek1_moment_kits_end.bin"     # zero bytes after the new packages: the archive must end on a sector
MOMENT_ROWS = 51
MAX_STYLE = 14
UNIF_COLOURS = 0x50                    # chunk 0 (Unif): facemask/faceshield word, then the turtleneck word
# The largest decoded allocations an existing kit already has (a5k: 21A14/17A6/02A1 at 2,840,256 video bytes).
MAX_VIDEO_BYTES = 2_840_256
MAX_SYSTEM_BYTES = 10_752
CARD_KEYS = ("unif_h", "helm_h", "mini_h", "unif_a", "helm_a", "mini_a", "logo")


def require(ok, message):
    if not ok:
        raise ValueError("Anniversary moment kits: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_document(doc):
    """Validate a moment/classic-kit document in the shared shape and return it."""
    require(isinstance(doc, dict) and doc.get("schema") == SCHEMA, "unexpected data schema")
    doc.setdefault("selections", [])
    doc.setdefault("classic_defaults", [])
    ids = [k["id"] for k in doc["kits"]]
    require(len(set(ids)) == len(ids), "duplicate kit ids")
    seen = set()
    for kit in doc["kits"]:
        require(type(kit["style"]) is int and 1 <= kit["style"] <= MAX_STYLE, kit["id"] + ": style out of range")
        require((kit["code"], kit["style"]) not in seen, kit["id"] + ": two kits on one index")
        seen.add((kit["code"], kit["style"]))
        a, b = kit["label"]
        require(1900 <= a <= b <= 2100, kit["id"] + ": label years")
        require(set(kit["sides"]) == {"H", "A"}, kit["id"] + ": needs H and A")
        require(set(kit["cards"]) <= set(CARD_KEYS) | {"H", "A"} and {"H", "A", "logo"} <= set(kit["cards"]),
                kit["id"] + ": cards")
        if kit.get("card_art"):
            from . import nfl2k5_classic_art as art
            art.card_art(kit)
    by_id = {k["id"]: k for k in doc["kits"]}
    rows = set()
    for s in doc["selections"]:
        require(1 <= s["row"] <= MOMENT_ROWS and s["side"] in ("away", "home"), "selection row/side")
        require((s["row"], s["side"]) not in rows, f"row {s['row']} {s['side']} selected twice")
        rows.add((s["row"], s["side"]))
        require(("kit" in s) != ("reuse" in s), "a selection names a new kit or an existing one")
        if "kit" in s:
            kit = by_id[s["kit"]]
            require(kit["style"] == s["style"] and s["file"][2:4] == kit["code"], f"row {s['row']}: kit/file mismatch")
        else:
            require(s["reuse"][:2] == s["file"][2:4] and int(s["reuse"][3:]) == s["style"], f"row {s['row']}: reuse")
    files = [c["file"] for c in doc.get("classic_defaults", [])]
    require(len(set(files)) == len(files), "a team file has two classic defaults")
    for c in doc.get("classic_defaults", []):
        require(type(c["style"]) is int and 1 <= c["style"] <= MAX_STYLE, c["file"] + ": classic default style")
    return doc


def document(path=None):
    return validate_document(json.loads(Path(path or DATA).read_text(encoding="utf-8")))


def pins():
    doc = json.loads(PINS.read_text(encoding="utf-8"))
    require(doc.get("schema") == PIN_SCHEMA, "unexpected pin schema")
    require(doc["data_sha256"] == sha(DATA.read_bytes()), "moment kit data changed after the pins")
    return doc


def reserved_styles():
    """{(asset code, style)} of the new kits (historic_styles never picks one of these as a spare)."""
    return {(k["code"], k["style"]) for k in document()["kits"]}


def _expand(spec):
    """{"13-22": "18A0", "1": ...} -> {13: "18A0", ...}"""
    out = {}
    for key, value in spec.items():
        a, _, b = key.partition("-")
        for index in range(int(a), int(b or a) + 1):
            require(index not in out and 0 < index < 53, "chunk " + key)
            out[index] = value
    return out


def package_name(code, letter, style):
    return f"{code}{letter.lower()}{style}.iff"


def selector_name(selector):
    return f"{selector[:2]}{selector[2].lower()}{int(selector[3:])}.iff"


def donors(doc=None):
    """Every existing kit package the stage reads (selectors)."""
    doc = doc or document()
    out = set()
    for kit in doc["kits"]:
        for side in kit["sides"].values():
            out.add(side["base"])
            out |= set(_expand(side.get("chunks", {})).values())
            out |= {o["donor"] for o in side.get("atlas", {}).get("overlays", [])}
    return sorted(out)


def compose_side(side, packages, retail=None, report=None, label=""):
    """The new kit package of one side, from ``packages`` {selector: bytes}.

    b779-ce1 (Coach Edwards' project): a donor kit the user's own artwork made bigger than any retail kit, or whose
    clean and _mud textures no longer share their indices (an own-texture sock), used to stop the whole build hours in.
    When ``retail`` ({selector: retail package bytes}) is given, such a donor chunk is taken from the retail kit
    instead, in this new Anniversary kit only (the user's own kit keeps its texture), and the swap is appended to
    ``report`` by name. Only the chunks that cause the refusal are swapped; if that still does not compose, the
    original refusal stands (the caller can then leave the whole kit out)."""
    try:
        return _compose_side(side, packages, {})
    except ValueError as first:
        if retail is None:
            raise
        for swaps in _swap_plans(side, packages, retail):
            try:
                out = _compose_side(side, packages, swaps, retail)
            except ValueError:
                continue
            if report is not None:
                report.append(dict(side=label, reason=str(first), chunks=sorted(swaps),
                                   from_kits=sorted({swaps[i] for i in swaps})))
            return out
        raise first


def _swap_plans(side, packages, retail):
    """The chunk swaps to try, smallest first: {chunk index: donor selector whose RETAIL chunk replaces it}."""
    from nfl_txtr import parse_chunks
    from . import nfl2k5_kit_fixes_2026 as fixes
    sources = _expand(side.get("chunks", {}))
    art = {row["chunk"] for row in side.get("art", [])}
    size_changed, unshared, differs = {}, {}, {}
    for index in range(1, 53):
        selector = sources.get(index, side["base"])
        if selector not in packages or selector not in retail:
            continue
        have, was = parse_chunks(packages[selector]), parse_chunks(retail[selector])
        if len(have) != 53 or len(was) != 53:
            continue
        a, b = have[index], was[index]
        span, original = packages[selector][a.offset:a.end_offset], retail[selector][b.offset:b.end_offset]
        if (a.video_bytes, a.system_bytes) != (b.video_bytes, b.system_bytes):
            size_changed[index] = selector
        elif span != original and index in art:
            differs[index] = selector
            if a.kind == "TSET":
                try:
                    fixes.native_textures(span, "tset")
                except ValueError:
                    unshared[index] = selector
    first = {**size_changed, **unshared}
    plans = []
    if first:
        plans.append(first)
    if differs and {**first, **differs} != first:
        plans.append({**first, **differs})
    return plans


def _compose_side(side, packages, swaps, retail=None):
    from nfl_txtr import decode_chunk, parse_chunks
    from . import nfl2k5_era_kits as era
    from . import nfl2k5_kit_fixes_2026 as fixes
    base = packages[side["base"]]
    chunks = parse_chunks(base)
    require(len(chunks) == 53 and chunks[0].kind == "Unif", side["base"] + ": not a kit package")
    sources = _expand(side.get("chunks", {}))
    spans = []
    for c in chunks:
        selector = sources.get(c.index, side["base"])
        donor = (retail if c.index in swaps else packages)[selector]
        dc = parse_chunks(donor)
        require(len(dc) == 53 and dc[c.index].kind == c.kind, f"chunk {c.index} kind differs in the donor")
        spans.append(donor[dc[c.index].offset:dc[c.index].end_offset])
    for row in side.get("art", []):
        i = row["chunk"]
        if row["kind"] == "palette_map":
            spans[i] = palette_map(spans[i], row)
        elif row["kind"] == "palette":
            spans[i], _receipt = fixes.compile_palette(spans[i], row)
        else:
            # a row may ask for a fresh encoding (b775-ct1: whole new numerals do not fit the donor's stored span)
            spans[i], _receipt = fixes.compile_texture(spans[i], row, fixed=not row.get("reencode", False))
    atlas = side.get("atlas")
    if atlas:
        span = spans[51]
        c = parse_chunks(span)[0]
        decoded, _ = decode_chunk(span, c)
        overlays = []
        for row in atlas["overlays"]:
            other = packages[row["donor"]]
            overlays.append((decode_chunk(other, parse_chunks(other)[51])[0], row["boxes"]))
        mixed = era._native_atlas(decoded, c, overlays, atlas["format"])
        if atlas.get("ops"):
            from . import nfl2k5_classic_kit_art as classic_art      # b778-ss2: finish the far-player atlas
            mixed = classic_art.atlas_edit(mixed, c, atlas["ops"])
        spans[51] = era._encoded_span(span, mixed, len(mixed) - c.system_bytes)
    out = bytearray(b"".join(spans))
    if side.get("unif"):
        out[UNIF_COLOURS:UNIF_COLOURS + 8] = packages[side["unif"]][UNIF_COLOURS:UNIF_COLOURS + 8]
    if side.get("unif_colours"):
        from . import nfl2k5_classic_kit_art as classic_art          # b778-ss2: authored facemask/turtleneck
        out[UNIF_COLOURS:UNIF_COLOURS + 8] = classic_art.unif_words(side["unif_colours"])
    out = bytes(out)
    parsed = parse_chunks(out)
    require(len(parsed) == 53, "composed package chunk count")
    video = sum(c.video_bytes for c in parsed)
    system = sum(c.system_bytes for c in parsed)
    require(video <= MAX_VIDEO_BYTES and system <= MAX_SYSTEM_BYTES,
            f"composed kit allocation {system}/{video} exceeds the largest existing kit")
    return out


def _hex(text):
    return tuple(int(text[k:k + 2], 16) for k in (1, 3, 5))


def map_entries(palette, mapping, tolerance):
    """Swap team colours in a palette, keeping shading and white blends: an entry that is w*white + s*from (least
    squares, within ``tolerance`` per channel) becomes w*white + s*to. Entries on no colour's plane (black, grey,
    blends of two team colours) stay. Exact rational arithmetic, so every platform writes the same bytes."""
    from fractions import Fraction
    import math
    out = palette.copy()
    white = (255, 255, 255)
    dot = lambda u, v: sum(x * y for x, y in zip(u, v))
    for i in range(256):
        if palette[i, 3] == 0:
            continue
        rgb = tuple(int(v) for v in palette[i, :3])
        best = None
        for m in mapping:
            a = _hex(m["from"])
            g11, g12, g22 = dot(white, white), dot(white, a), dot(a, a)
            r1, r2 = dot(white, rgb), dot(a, rgb)
            det = g11 * g22 - g12 * g12
            if det == 0:
                continue
            w, k = Fraction(r1 * g22 - r2 * g12, det), Fraction(g11 * r2 - g12 * r1, det)
            if w < Fraction(-1, 50) or k <= Fraction(1, 20):
                continue
            residual = max(abs(w * 255 + k * a[c] - rgb[c]) for c in range(3))
            if residual <= tolerance and (best is None or residual < best[0]):
                best = (residual, max(w, Fraction(0)), k, _hex(m["to"]))
        if best is not None:
            _r, w, k, b = best
            out[i, :3] = [min(255, max(0, math.floor(w * 255 + k * b[c] + Fraction(1, 2)))) for c in range(3)]
    return out


def palette_map(span, row):
    """One chunk with its palettes colour-swapped (TSET: the clean palette and its _mud twin; TXTR: its palette);
    indices, sizes, mips and the stored allocation stay the same."""
    from . import nfl2k5_kit_fixes_2026 as fixes
    tex = row.get("texture_kind", "tset")
    if tex == "tset":
        chunk, decoded, textures = fixes.native_textures(span, "tset")
    else:
        chunk, decoded, texture = fixes._txtr(span)
        textures = [dict(palette=texture.palette_offset)]
    new = decoded
    for t in textures:
        palette = fixes.read_palette(new, chunk, t)
        mapped = map_entries(palette, row["map"], int(row.get("tolerance", 12)))
        new = fixes.write_texture(new, chunk, dict(t, pixel=0, width=0, height=0, mips=0), [], mapped)
    require(new != decoded, "the palette map changed nothing")
    from . import nfl2k5_era_kits as era
    # a new package has no fixed allocation to keep: re-encode the chunk (same decoded bytes and video allocation)
    return era._encoded_span(span, new, chunk.video_bytes)


def compose(doc, packages, retail=None, report=None, skipped=None):
    """{new package name: bytes} for every kit.

    ``retail`` / ``report``: see ``compose_side``. ``skipped`` (a dict, b779-ce1): a kit that cannot be composed even
    with retail chunks is left out and recorded as {kit id: reason} instead of stopping the build; the donors are
    never touched. Without it the refusal propagates (the shipped SOFTDRINK documents compose exactly)."""
    out = {}
    for kit in doc["kits"]:
        try:
            made = {package_name(kit["code"], letter, kit["style"]):
                    compose_side(side, packages, retail, report, _side_label(kit, letter))
                    for letter, side in kit["sides"].items()}
        except ValueError as exc:
            if skipped is None:
                raise
            skipped[kit["id"]] = str(exc)
            continue
        out.update(made)
    return out


def _side_label(kit, letter):
    return f"{kit['id']} ({kit.get('team', kit['code'])}, {'away' if letter == 'A' else 'home'})"


def without_kits(doc, skipped):
    """The document without the kits in ``skipped`` ({kit id: reason}) and without the selections that point at them
    (those moment sides keep the kit they had)."""
    if not skipped:
        return doc
    out = dict(doc)
    out["kits"] = [k for k in doc["kits"] if k["id"] not in skipped]
    out["selections"] = [s for s in doc["selections"] if s.get("kit") not in skipped]
    return out


def card_sources(kit):
    """{new member name: (aggregate, source member name)} of one kit."""
    code, style, cards = kit["code"], kit["style"], kit["cards"]

    def src(key, default_letter):
        selector = cards.get(key, cards[default_letter])
        return selector[2].lower(), int(selector[3:]), selector[:2]

    out = {}
    for letter in "ha":
        for kind, aggregate in (("unif", "logos"), ("helm", "logos"), ("mini", "mini")):
            l, s, c = src(f"{kind}_{letter}", letter.upper())
            require(c == code, kit["id"] + ": card from another franchise")
            if kind != "unif":
                # sm1 (Noah, b775 video: helmets on three Anniversary menu rows face away from each other): the helmet
                # cards are drawn facing one way per slot letter (retail mini_h / helm_h face left, mini_a / helm_a face
                # right; the menu draws the away team with mini_a on the left and the home team with mini_h on the
                # right). A kit whose jersey look comes from the donor's other letter (a swapped H/A kit, or one built
                # from one letter alone) keeps the donor STYLE's helmet but must take it from this slot's own letter, or
                # the helmet turns the wrong way. The jersey cards (unif) do not face a side and keep the selector.
                l = letter
            out[f"{kind}_{letter}{code}_{style}"] = (aggregate, f"{kind}_{l}{code}_{s}")
    _l, s, _c = src("logo", "H")
    out[f"logo_{code}_{style}"] = ("logos", f"logo_{code}_{s}")
    out[f"logo_s{code}_{style}"] = ("mini", f"logo_s{code}_{s}")
    out[f"{code}_flipchip_00_h{style}"] = ("flipchip", f"{code}_flipchip_00_h{s}")
    return out


def _team_file_pairs(raw):
    from . import nfl2k5_historic_styles as hs
    (at, code), = hs.team_records(raw)[:1]
    t = 32 + at
    return code, t, [struct.unpack_from("<HH", raw, t + hs.TABLE + 4 * k) for k in range(MAX_STYLE)]


def main_label(main_roster, code, style):
    from . import nfl2k5_historic_styles as hs
    body = main_roster[32:]
    for at, c in hs.team_records(main_roster)[:32]:
        if c == code:
            return struct.unpack_from("<HH", body, at + hs.TABLE + 4 * (style - 1))
    raise ValueError("no NFL team uses asset code " + code)


def file_edit(raw, labels, default=None):
    """The team file with each {style: (first, last)} pair set where it is still (0, 0) (other pairs stay) and, when
    given, its default style byte (+0x192: the classic team's main uniform in Quick Game) set to ``default``."""
    from . import nfl2k5_historic_styles as hs
    _code, t, pairs = _team_file_pairs(raw)
    out = bytearray(raw)
    for style, pair in sorted(labels.items()):
        if pairs[style - 1] == (0, 0):
            struct.pack_into("<HH", out, t + hs.TABLE + 4 * (style - 1), *pair)
    if default is not None:
        require(struct.unpack_from("<HH", out, t + hs.TABLE + 4 * (default - 1)) != (0, 0),
                f"classic default {default} has no year pair in its team file")
        out[t + hs.STYLE] = default
    return bytes(out)


def wanted_labels(doc, main_roster, files):
    """{team file: {style: pair}} every selection needs (new kits: their label; an existing kit the file does not
    list yet: the main roster's label)."""
    by_id = {k["id"]: k for k in doc["kits"]}
    out = {}
    for s in doc["selections"]:
        if "kit" in s:
            pair = tuple(by_id[s["kit"]]["label"])
        else:
            if _team_file_pairs(files[s["file"]])[2][s["style"] - 1] != (0, 0):
                continue
            pair = main_label(main_roster, s["file"][2:4], s["style"])
            require(pair != (0, 0), f"row {s['row']}: reused style {s['style']} is listed nowhere")
        out.setdefault(s["file"], {})[s["style"]] = pair
    return out


def added_pairs():
    """{team file: {style: pair}} of the new-kit labels (the only bytes the stage adds to a team file)."""
    doc = document()
    by_id = {k["id"]: k for k in doc["kits"]}
    out = {}
    for s in doc["selections"]:
        if "kit" in s:
            out.setdefault(s["file"], {})[s["style"]] = tuple(by_id[s["kit"]]["label"])
    return out


def without_added_pairs(payload, filename):
    """A team file with ek1's new-kit pairs back to (0, 0) (only pairs equal to the data's label)."""
    from . import nfl2k5_historic_styles as hs
    labels = added_pairs().get(filename)
    if not labels:
        return payload
    try:
        _code, t, pairs = _team_file_pairs(payload)
    except (ValueError, IndexError, struct.error):
        return payload
    out = bytearray(payload)
    for style, pair in labels.items():
        if pairs[style - 1] == pair:
            struct.pack_into("<HH", out, t + hs.TABLE + 4 * (style - 1), 0, 0)
    return bytes(out)


# ------------------------------------------------------------------------------------------------ the disc

def _situ_fields(situ):
    from . import nfl2k5_historic_styles as hs
    return {(row + 1, side): (kit, field) for row, side, _sel, _season, kit, field in hs.situ_sides(situ)}


class RetailPackages(dict):
    """{selector: retail kit package bytes} read lazily from the retail disc (only a fallback ever asks)."""

    def __init__(self, retail):
        super().__init__()
        self._retail = retail
        self._names = None

    def _open(self):
        from . import nfl2k5_historic_styles as hs
        from . import nfl2k5_music_archive as archive
        path = self._retail() if callable(self._retail) else self._retail
        return archive.Disc(Path(path), descriptors=()), hs

    def __missing__(self, selector):
        disc, hs = self._open()
        with disc:
            target = hs.Target(disc)
            require(target.has(selector_name(selector)), selector + ": retail kit absent from the retail disc")
            value = self[selector] = target.get(selector_name(selector))
        return value

    def __contains__(self, selector):
        try:
            self[selector]
        except (ValueError, OSError):
            return False
        return True


def read_inputs(target, doc, retail=None, allow_skip=True):
    """Everything the stage reads from the build copy (hs.Target). ``retail`` (a path or a callable returning one)
    lets a kit that cannot be composed from the copy's own donors use the retail kits' chunks instead;
    ``allow_skip``: a kit that cannot be composed even then is left out (False: the refusal stands)."""
    from . import nfl2k5_historic_styles as hs
    inputs = dict(packages={}, files={}, members={}, retail=RetailPackages(retail) if retail is not None else None,
                  report=[], skipped={}, allow_skip=allow_skip)
    for selector in donors(doc):
        require(target.has(selector_name(selector)), selector + ": donor kit absent from the copy")
        inputs["packages"][selector] = target.get(selector_name(selector))
    for name in [s["file"] for s in doc["selections"]] + [c["file"] for c in doc.get("classic_defaults", [])]:
        require(target.has(name), name + ": team file absent from the copy")
        inputs["files"][name] = target.get(name)
    inputs["situ"] = target.get(identity=hs.SITU_OUTER_ID)
    inputs["main"] = target.get(identity=hs.ROSTER_OUTER_ID)
    for a in hs.AGGREGATES:
        inputs["members"][a["name"]] = (target.get(identity=a["record"]), target.get(identity=a["cdf"]))
    inputs["new_present"] = {package_name(k["code"], l, k["style"]): target.has(package_name(k["code"], l, k["style"]))
                             for k in doc["kits"] for l in "HA"}
    if inputs["retail"] is not None and _donors_pinned(inputs["packages"]):
        # the SOFTDRINK donors compose exactly to the shipped pins; a refusal there is a bug to see, not to work around
        inputs["retail"] = None
    return inputs


def _donors_pinned(packages):
    try:
        pin = pins()
    except (OSError, ValueError, KeyError):
        return False
    return bool(packages) and all(sha(data) == pin["donors"].get(selector) for selector, data in packages.items())


def expected(doc, inputs):
    """(packages, members {aggregate: {name: slot}}, files {name: bytes}, situ bytes) of the applied state."""
    from . import nfl2k5_historic_styles as hs
    packages = compose(doc, inputs["packages"], inputs.get("retail"), inputs.setdefault("report", []),
                       inputs.setdefault("skipped", {}) if inputs.get("retail") is not None
                       and inputs.get("allow_skip", True) else None)
    doc = without_kits(doc, inputs.get("skipped"))
    members = {a["name"]: {} for a in hs.AGGREGATES}
    for kit in doc["kits"]:
        authored = {}
        if kit.get("card_art"):
            from . import nfl2k5_classic_art as art
            authored = art.card_art(kit)
        for new, (aggregate, old) in card_sources(kit).items():
            record, cdf = inputs["members"][aggregate]
            donor = hs.member_slot(record, cdf, old)
            if new in authored:
                key, filename = authored[new]
                members[aggregate][new], _receipt = art.authored_slot(donor, key, filename, new)
            else:
                members[aggregate][new] = hs.rename_slot(donor, new)
    labels = wanted_labels(doc, inputs["main"], inputs["files"])
    defaults = {c["file"]: c["style"] for c in doc.get("classic_defaults", [])}
    files = {name: file_edit(raw, labels.get(name, {}), defaults.get(name)) for name, raw in inputs["files"].items()}
    situ = bytearray(inputs["situ"])
    fields = _situ_fields(inputs["situ"])
    if doc.get("selections"):
        require(len({r for r, _s in fields}) == MOMENT_ROWS, "the copy does not hold the 51 Anniversary moments")
    for s in doc["selections"]:
        struct.pack_into("<I", situ, fields[(s["row"], s["side"])][1], s["style"])
    return packages, members, files, bytes(situ)


def _installed_document(doc, inputs):
    """The document minus the kits an earlier install of this stage left out (b779-ce1).

    A kit is read as left out only when none of its packages or card members is on the copy, its moment sides still
    have the kit they had, at least one other kit IS installed, and composing it from the copy's donors (with the
    retail chunks) really does fail. Anything else is a partial or foreign install and keeps the whole document."""
    from . import nfl2k5_historic_styles as hs
    retail = inputs.get("retail")
    if retail is None or len(doc["kits"]) < 2 or not inputs.get("allow_skip", True):
        return doc
    fields = _situ_fields(inputs["situ"])
    hashes = {name: set(hs.parse_record(record)[2]) for name, (record, _cdf) in inputs["members"].items()}
    absent, here = [], []
    for kit in doc["kits"]:
        names = [package_name(kit["code"], l, kit["style"]) for l in "HA"]
        members = [hs.member_hash(new) in hashes[agg] for new, (agg, _old) in card_sources(kit).items()]
        sides = [s for s in doc["selections"] if s.get("kit") == kit["id"]]
        if not any(inputs["new_present"][n] for n in names) and not any(members) and all(
                fields[(s["row"], s["side"])][0] == s["before"] for s in sides):
            absent.append(kit)
        else:
            here.append(kit)
    if not absent or not here:
        return doc
    skipped = {}
    try:
        compose(dict(doc, kits=absent), inputs["packages"], retail, [], skipped)
    except ValueError:
        return doc
    if {k["id"] for k in absent} != set(skipped):
        return doc
    inputs["skipped"] = skipped
    return without_kits(doc, skipped)


def state_of(doc, inputs, target, *, pinned_packages=None):
    """'retail' (nothing installed, every selection as before), 'applied', else 'foreign'.

    ``pinned_packages`` ({name: sha256}, the shipped document's pins): a new package also reads as installed when it
    is byte for byte its pinned composition. b778 bd3: the team-coloured sleeves (sl1) run after this stage and
    rewrite the long-sleeve palettes of the DONOR kits, so composing again from the copy's donors no longer gives
    the bytes this stage wrote, while the installed kits are exactly the pinned ones."""
    from . import nfl2k5_historic_styles as hs
    doc = _installed_document(doc, inputs)
    fields = _situ_fields(inputs["situ"])
    kits_now = {(s["row"], s["side"]): fields[(s["row"], s["side"])][0] for s in doc["selections"]}
    present = {n: v for n, v in inputs["new_present"].items()
               if n in {package_name(k["code"], l, k["style"]) for k in doc["kits"] for l in "HA"}}
    hashes = {name: set(hs.parse_record(record)[2]) for name, (record, _cdf) in inputs["members"].items()}
    new_members = {(agg, new) for k in doc["kits"] for new, (agg, _old) in card_sources(k).items()}
    member_present = {m: hs.member_hash(m[1]) in hashes[m[0]] for m in new_members}
    if (not any(present.values()) and not any(member_present.values())
            and all(kits_now[(s["row"], s["side"])] == s["before"] for s in doc["selections"])):
        return "retail"
    if not (all(present.values()) and all(member_present.values())
            and all(kits_now[(s["row"], s["side"])] == s["style"] for s in doc["selections"])):
        return "foreign"
    packages, members, files, situ = expected(doc, inputs)
    if situ != inputs["situ"] or any(files[n] != inputs["files"][n] for n in files):
        return "foreign"
    for name, data in packages.items():
        have = target.get(name)
        if have != data and not (pinned_packages and name in pinned_packages and sha(have) == pinned_packages[name]):
            return "foreign"
    for aggregate, wanted in members.items():
        record, cdf = inputs["members"][aggregate]
        for name, slot in wanted.items():
            if hs.member_slot(record, cdf, name) != slot:
                return "foreign"
    return "applied"


def image_status(path, doc=None, retail=None, allow_skip=True):
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_music_archive as archive
    pinned = None
    if doc is None:
        doc = document()
        try:
            pinned = pins()["packages"]
        except (OSError, ValueError, KeyError):
            pinned = None
    try:
        with archive.Disc(Path(path), descriptors=()) as disc:
            target = hs.Target(disc)
            if doc.get("selections") and len(_situ_fields(target.get(identity=hs.SITU_OUTER_ID))) != 2 * MOMENT_ROWS:
                return "not_applicable"
            return state_of(doc, read_inputs(target, doc, retail, allow_skip), target, pinned_packages=pinned)
    except (ValueError, KeyError, IndexError, struct.error, OSError):
        return "foreign"


def compile_edits(target, doc, inputs):
    """(edits {outer index: bytes}, appended [(name, bytes)], receipt rows) for a 'retail' copy."""
    from . import nfl2k5_historic_styles as hs
    for name, there in inputs["new_present"].items():
        require(not there, name + " already exists: the index is not free")
    packages, members, files, situ = expected(doc, inputs)
    skipped = dict(inputs.get("skipped") or {})
    doc = without_kits(doc, skipped)
    if not packages:
        return {}, [], dict(kits=[], pinned_donors=None, members=0, team_files=[], selections=0,
                            skipped_kits=skipped, substitutions=list(inputs.get("report") or []))
    edits = {}
    for aggregate in hs.AGGREGATES:
        record, cdf = inputs["members"][aggregate["name"]]
        new_record, new_cdf = hs.grow_aggregate(record, cdf, members[aggregate["name"]])
        edits[target.outer(identity=aggregate["record"])] = new_record
        edits[target.outer(identity=aggregate["cdf"])] = new_cdf
    for name, data in files.items():
        if data != inputs["files"][name]:
            edits[target.outer(name)] = data
    if situ != inputs["situ"]:
        edits[target.outer(identity=hs.SITU_OUTER_ID)] = situ
    appended = sorted(packages.items())
    if len(appended[-1][1]) % 2048:
        # b778 bf1: the Anniversary moments and the classic teams' authored
        # kits are two installs of this same module, in that order. The first
        # one's zero filler is already in the archive when the second appends,
        # so the second needs a distinct filler name (the filler is packaging
        # only, never a named package the document pins).
        filler = FILLER
        if target.has(filler):
            stem, _, suffix = filler.rpartition(".")
            number = 2
            while target.has(f"{stem}_{number}.{suffix}"):
                number += 1
            filler = f"{stem}_{number}.{suffix}"
        appended.append((filler, bytes(2048)))
    pinned = None
    try:
        pin = pins()
    except (OSError, ValueError, KeyError):
        pin = None
    if pin is not None:
        pinned = all(sha(inputs["packages"][s]) == pin["donors"].get(s) for s in inputs["packages"])
        if pinned:
            for name, data in packages.items():
                require(sha(data) == pin["packages"][name], name + ": composed kit differs from its pin")
    rows = [dict(file=n, size=len(d), sha256=sha(d)) for n, d in sorted(packages.items())]
    return edits, appended, dict(kits=rows, pinned_donors=pinned,
                                 members=sum(len(v) for v in members.values()),
                                 team_files=sorted(n for n in files if files[n] != inputs["files"][n]),
                                 selections=len(doc["selections"]),
                                 skipped_kits=skipped, substitutions=list(inputs.get("report") or []))


CHUNK_NAMES = {4: "socks", 5: "elbow pads", 6: "gloves", 7: "long sleeves", 8: "shoes (styles 1, 2, 3)",
               9: "shoes (styles 4, 5, 6)", 10: "wristbands"}


def _chunk_words(indexes):
    words = [CHUNK_NAMES.get(i, f"piece {i}") for i in indexes]
    return ", ".join(words[:-1]) + " and " + words[-1] if len(words) > 1 else words[0]


def user_notes(receipt, feature="Anniversary moment kits"):
    """Plain sentences for the build log and summary: every swap and every kit left out, by name (b779-ce1)."""
    notes = []
    for row in receipt.get("substitutions", ()):
        kits_from = " and ".join(row["from_kits"])
        why = row["reason"].split(": ", 1)[-1]
        notes.append(f"{feature}: the new kit {row['side']} uses the retail {_chunk_words(row['chunks'])} of {kits_from} "
                     f"(chunk{'s' if len(row['chunks']) > 1 else ''} {', '.join(str(c) for c in row['chunks'])}), because "
                     f"your edited version cannot be used in a new kit ({why}). Your own kits keep your artwork.")
    for kit_id, reason in sorted(receipt.get("skipped_kits", {}).items()):
        notes.append(f"{feature}: the new kit {kit_id} was left out and the moment sides that use it keep the kit they "
                     f"had ({reason.split(': ', 1)[-1]}).")
    return notes


def apply_to_image(path, doc=None, retail=None, allow_skip=True, feature="Anniversary moment kits"):
    """Install every new kit and moment selection on a private build copy; replay is a no-op.

    ``retail`` (a path or a callable returning one): when a donor kit of the user's cannot be composed into a new
    kit, that chunk (or, last, the whole kit) is taken from the retail disc and named in ``user_notes`` rather than
    stopping the build. ``allow_skip=False`` (the classic teams' own kit, which their files need): no kit is left out."""
    from . import nfl2k5_historic_styles as hs
    from . import nfl2k5_music_archive as archive
    doc = doc or document()
    path = Path(path).resolve()
    state = image_status(path, doc, retail, allow_skip)
    if state in ("applied", "not_applicable"):
        return dict(state=state, written=0)
    require(state == "retail", "the copy is " + state)
    with archive.Disc(path, descriptors=()) as disc:
        target = hs.Target(disc)
        inputs = read_inputs(target, doc, retail, allow_skip)
        edits, appended, receipt = compile_edits(target, doc, inputs)
    notes = user_notes(receipt, feature)
    if not appended:
        # every kit was left out: nothing to write, the copy stays as it is
        return dict(state="skipped_all", experimental=True, runtime_witnessed=False, owner=OWNER, written=0,
                    user_notes=notes, **receipt)
    rewrite = hs.rewrite_archive(path, edits, appended, verify=lambda p: image_status(p, doc, retail, allow_skip) == "applied")
    return dict(state="applied", experimental=True, runtime_witnessed=False, owner=OWNER, user_notes=notes,
                **receipt, **rewrite)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("image-status", help="state of a built disc image")
    p.add_argument("image", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(dict(status=image_status(args.image), owner=OWNER, experimental=True, runtime_witnessed=False)))


if __name__ == "__main__":
    main()

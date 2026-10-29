"""Super Bowl event walls on the dedicated Anniversary stadium aliases (N06, refreshed by sb2).

The alias compiler copies each venue's non-field scenes from its source, so a Super Bowl moment showed the host team's
slogans, banners and boards (Vikings SKOL walls in Super Bowl LII, Colts walls in XLVI). For the Super Bowl rows this
pass repaints only the listed temporary surfaces of the stadium scene with event art. Permanent venue signs, geometry,
material bindings and every other texture keep their bytes. The stadium scene is refit into its existing compressed
span, so the bundle keeps its size and every other chunk, and a native repair can write the same span in place.
Regular venue resources are never touched.

Each surface is two shipped PNGs drawn by ``tools/nfl2k5_super_bowl_walls_art.py``: the base (background, type and
plates) and an optional layer holding the authored marks that sit in the surface's slots. A slot is a box with a kind:

``shield``  the NFL shield of the game's season. From the 2008 season on it is the mod's own official shield
            (``data/nfl2k5_espn25_fields/row45/center_logo.png``, pinned). Before that it is the period shield, taken
            at build time from the user's retail disc (field ``center_logo`` of ``s43dd.iff``), so no retail pixel
            ships.
``event``   the game's event mark: the bundled real logo (``super_bowl/<NUMERALS>.png`` below) or a file from the
            user's own folder.
``brand``   the broadcaster: the bundled real mark (``brands/<name>.png`` below) or a file from the user's folder.
``team``    a club: the mod's own team logo (baked into the layer at author time), the bundled real logo for the four
            team-seasons the mod lacks, or a file from the user's folder.

The bundled folder (``data/nfl2k5_super_bowl_logos``) is Noah's real-logo set, approved 2026-10-28 for this free fan
mod and carried by the Studio and the SOFTDRINK pack. A build whose ``super_bowl_user_art`` is empty uses it; a
non-empty user folder is used instead, and a slot it does not name keeps the authored mark. A missing or unreadable
bundled file also falls back to the authored mark. A placed file is trimmed to its visible pixels, fitted by aspect
inside the slot's safe margin, held to the slot's palette budget and composited with its alpha.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "data/nfl2k5_super_bowl_walls"
#: the bundled real Super Bowl, network and team-season logos (sb3); the default logo folder of every build
BUNDLED_LOGOS = ROOT / "data/nfl2k5_super_bowl_logos"
LOGO_SCHEMA = "nfl2k5_super_bowl_logos/v1"
SCHEMA = "nfl2k5_super_bowl_walls/v2"
ALPHA_MODES = ("opaque", "source", "art")
SLOT_KINDS = ("shield", "event", "brand", "team")
BRANDS = ("abc", "cbs", "espn", "fox", "nbc")
#: user_art sub-folder per overridable slot kind
USER_FOLDERS = {"event": "super_bowl", "brand": "brands", "team": "teams"}
#: the mod's own 2008 official shield (Anniversary field art, shipped)
MODERN_SHIELD = ROOT / "data/nfl2k5_espn25_fields/row45/center_logo.png"
MODERN_SHIELD_SHA256 = "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6"
#: the shield changed for the 2008 season; Super Bowls of earlier seasons carry the period shield
MODERN_SHIELD_FROM_SEASON = 2008
#: the period shield: the retail field texture (decoded RGBA) the build reads from the user's disc
PERIOD_SHIELD_RESOURCE = "s43dd.iff"
PERIOD_SHIELD_MATERIAL = "center_logo"
PERIOD_SHIELD_RGBA_SHA256 = "c69a5a4bbc1b8f50501f794e81b12acacca156976b05d9fd6abcaf109b8a02ff"
USER_ART_MAX_BYTES = 8 * 1024 * 1024
USER_ART_MAX_SIDE = 4096
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


_MANIFEST = None


def manifest():
    global _MANIFEST
    if _MANIFEST is None:
        raw = (ART / "manifest.json").read_bytes()
        require(len(raw) < 512 * 1024, "Super Bowl wall manifest is too large")
        doc = json.loads(raw)
        require(doc.get("schema") == SCHEMA, "foreign Super Bowl wall manifest")
        rows = [r["row"] for r in doc["rows"]]
        require(len(rows) == len(set(rows)) and all(1 <= r <= 51 for r in rows), "Super Bowl wall rows")
        require(not set(rows) & set(doc.get("held_rows", ())), "a held row carries wall art")
        for r in doc["rows"]:
            names = [t["material"] for t in r["textures"]]
            require(len(names) == len(set(names)) and names, f"row {r['row']}: wall materials")
            teams = set(r.get("teams", {}).values())
            for t in r["textures"]:
                require(t["alpha"] in ALPHA_MODES and len(t["size"]) == 2, f"row {r['row']}: {t['material']} entry")
                w, h = t["size"]
                for box in t.get("areas", ()):
                    require(len(box) == 4 and 0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h,
                            f"row {r['row']}: {t['material']} area {box}")
                boxes = []
                for s in t.get("slots", ()):
                    box = s["box"]
                    require(s["kind"] in SLOT_KINDS and len(box) == 4 and 0 <= box[0] < box[2] <= w
                            and 0 <= box[1] < box[3] <= h, f"row {r['row']}: {t['material']} slot {s}")
                    require(s["kind"] != "event" or s["key"] == r["event"], f"row {r['row']}: event slot key")
                    require(s["kind"] != "brand" or s["key"] in BRANDS, f"row {r['row']}: brand slot key")
                    require(s["kind"] != "team" or s["key"] in teams, f"row {r['row']}: team slot key")
                    require(all(box[2] <= b[0] or b[2] <= box[0] or box[3] <= b[1] or b[3] <= box[1]
                                for b in boxes), f"row {r['row']}: {t['material']} slots overlap")
                    boxes.append(box)
                require(bool(t.get("slots")) == bool(t.get("layer")) or all(
                    s["kind"] == "shield" for s in t.get("slots", ())), f"row {r['row']}: {t['material']} layer")
        _MANIFEST = doc
    return _MANIFEST


_LOGO_MANIFEST = None


def logo_manifest():
    """The bundled real logos' manifest: ``{relative PNG path: sha256, size, width, height}``."""
    global _LOGO_MANIFEST
    if _LOGO_MANIFEST is None:
        raw = (BUNDLED_LOGOS / "manifest.json").read_bytes()
        require(len(raw) < 256 * 1024, "Super Bowl logo manifest is too large")
        doc = json.loads(raw)
        require(doc.get("schema") == LOGO_SCHEMA, "foreign Super Bowl logo manifest")
        files = doc.get("files")
        require(isinstance(files, dict) and files, "Super Bowl logo manifest is empty")
        for name, item in files.items():
            require(isinstance(name, str) and name.endswith(".png") and name == Path(name).as_posix()
                    and ".." not in name.split("/") and not name.startswith("/"), f"{name}: bundled logo path")
            require(isinstance(item, dict) and isinstance(item.get("sha256"), str) and len(item["sha256"]) == 64
                    and isinstance(item.get("size"), int) and item["size"] > 0
                    and isinstance(item.get("width"), int) and item["width"] > 0
                    and isinstance(item.get("height"), int) and item["height"] > 0,
                    f"{name}: bundled logo entry")
        _LOGO_MANIFEST = doc
    return _LOGO_MANIFEST


def effective_user_art(folder=""):
    """The logo folder a build uses: the bundled real logos when ``folder`` is empty, else the user's folder."""
    text = str(folder).strip() if folder else ""
    return text or str(BUNDLED_LOGOS)


def is_bundled(folder):
    """True when ``folder`` is the bundled real logo folder."""
    if not folder:
        return False
    from . import platform_compat as io
    return io.path_key(io.absolute_path(folder)) == io.path_key(BUNDLED_LOGOS)


def entry(row):
    """The manifest row for an Anniversary physical row, or None for a row without event walls."""
    found = [r for r in manifest()["rows"] if r["row"] == row]
    return found[0] if found else None


def _png(name, digest, size=None):
    from PIL import Image
    import numpy as np
    path = (ART / name).resolve()
    require(path.is_relative_to(ART.resolve()), "wall art path escapes its folder")
    raw = path.read_bytes()
    require(len(raw) < 1024 * 1024 and sha(raw) == digest, f"{name}: wall art hash differs")
    with Image.open(path) as im:
        require(size is None or list(im.size) == size, f"{name}: wall art dimensions differ")
        return np.asarray(im.convert("RGBA")).copy()


def art(texture):
    """The surface's base RGBA (background, type and plates)."""
    return _png(texture["file"], texture["sha256"], texture["size"])


def layer(texture):
    """The surface's authored slot marks (RGBA, clear outside the slots), or a clear layer."""
    import numpy as np
    if not texture.get("layer"):
        return np.zeros((texture["size"][1], texture["size"][0], 4), np.uint8)
    return _png(texture["layer"], texture["layer_sha256"], texture["size"])


# --- marks ---------------------------------------------------------------------------------------------------------

_MODERN = None


def modern_shield():
    """The mod's own official 2008 shield (RGBA), pinned."""
    global _MODERN
    if _MODERN is None:
        from PIL import Image
        import numpy as np
        raw = MODERN_SHIELD.read_bytes()
        require(sha(raw) == MODERN_SHIELD_SHA256, "the shipped NFL shield differs from its pin")
        with Image.open(MODERN_SHIELD) as im:
            _MODERN = np.asarray(im.convert("RGBA")).copy()
    return _MODERN


def _box_sum(a, r):
    """Integer sum of each (2r + 1)-square window (zero outside), exact on every platform."""
    import numpy as np
    h, w = a.shape[:2]
    c = np.zeros((h + 2 * r + 1, w + 2 * r + 1) + a.shape[2:], np.int64)
    c[1:, 1:] = np.pad(a.astype(np.int64), ((r, r), (r, r)) + ((0, 0),) * (a.ndim - 2)).cumsum(0).cumsum(1)
    k = 2 * r + 1
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def defringe(rgba):
    """Pull edge colours from the opaque interior so a cut-out mark keeps no background fringe (alpha unchanged).
    Integer arithmetic only, so every platform gets the same texels."""
    import numpy as np
    a = rgba[..., 3]
    solid = (a >= 250).astype(np.int64)
    out = rgba.copy()
    todo = (a < 250) & (a > 0)
    if solid.any():
        colour = rgba[..., :3].astype(np.int64) * solid[..., None]
        for radius in (1, 2, 4, 8, 16):
            if not todo.any():
                break
            n = _box_sum(solid, radius)
            pick = todo & (n > 0)
            sums = _box_sum(colour, radius)
            mean = (sums * 2 + np.maximum(n, 1)[..., None]) // (2 * np.maximum(n, 1)[..., None])
            out[..., :3] = np.where(pick[..., None], mean, out[..., :3]).astype(np.uint8)
            todo &= ~pick
    out[a == 0, :3] = 0
    return out


def period_shield(bundle):
    """(RGBA, receipt) of the period NFL shield from the user's retail ``s43dd.iff``: its field's ``center_logo``
    texture with its own cut-out alpha, edge colours pulled from the interior. Read at build time; never shipped."""
    from . import nfl2k5_espn25_fields as fields
    from . import nfl2k5_modern_venues_2026 as mv
    _chunk, rec, decoded = fields._field_chunk(bundle)
    rows, materials = mv.p8_rows(rec), mv.rows_by_material(rec)
    require(PERIOD_SHIELD_MATERIAL in materials, "the retail field lacks its centre logo")
    rgba = mv.read_texture(decoded, rec, rows[materials[PERIOD_SHIELD_MATERIAL]]).copy()
    digest = sha(rgba.tobytes())
    require(rgba.shape[:2] == (256, 256) and (rgba[..., 3] == 0).any() and (rgba[..., 3] == 255).any(),
            "the retail centre logo is not a cut-out shield")
    return defringe(rgba), dict(source=PERIOD_SHIELD_RESOURCE, material=PERIOD_SHIELD_MATERIAL, rgba_sha256=digest,
                                pinned_retail=digest == PERIOD_SHIELD_RGBA_SHA256)


def period_shield_needed(rows=None):
    """True when a listed Super Bowl row (or any, by default) predates the 2008 shield."""
    return any(r["season"] < MODERN_SHIELD_FROM_SEASON for r in manifest()["rows"]
               if rows is None or r["row"] in rows)


def user_art_file(folder, kind, key):
    """(path, None) of the user's PNG for a slot, (None, None) when absent, or (None, reason) when refused."""
    from . import platform_compat as io
    if not folder or kind not in USER_FOLDERS:
        return None, None
    base = io.io_path(io.absolute_path(folder)) / USER_FOLDERS[kind]
    try:
        if not base.is_dir():
            return None, None
        wanted = f"{key}.png".lower()
        found = sorted(p for p in base.iterdir() if p.name.lower() == wanted)
    except OSError as exc:
        return None, f"{USER_FOLDERS[kind]}: {exc}"
    if not found:
        return None, None
    path = found[0]
    rel = f"{USER_FOLDERS[kind]}/{path.name}"
    try:
        if path.is_symlink() or io.is_reparse_point(path) or not path.is_file():
            return None, f"{rel}: not a regular file"
        size = path.stat().st_size
        if size > USER_ART_MAX_BYTES:
            return None, f"{rel}: larger than {USER_ART_MAX_BYTES // (1024 * 1024)} MB"
        with path.open("rb") as stream:
            if stream.read(8) != PNG_SIGNATURE:
                return None, f"{rel}: not a PNG file"
    except OSError as exc:
        return None, f"{rel}: {exc}"
    return path, None


def load_user_png(path):
    """RGBA array of a user PNG, refusing oversized or unreadable images (the caller falls back)."""
    from PIL import Image
    import numpy as np
    with Image.open(path) as im:
        require(im.format == "PNG", "not a PNG image")
        require(max(im.size) <= USER_ART_MAX_SIDE and min(im.size) >= 8, f"image size {im.size[0]} x {im.size[1]}")
        im.load()
        rgba = np.asarray(im.convert("RGBA")).copy()
    require((rgba[..., 3] > 0).any(), "the image is fully transparent")
    return rgba


class Marks:
    """The build-time marks: the era shields and the bundled or user logo folder (see :func:`effective_user_art`)."""

    def __init__(self, period_shield=None, user_art=None):
        self.period = period_shield
        self.user_art = str(user_art) if user_art else ""
        self.bundled = is_bundled(self.user_art)
        self._cache = {}
        self._fitted = {}

    def fitted(self, mark, origin, key, width, height, slot):
        """fit_mark of a mark for a slot box, cached per source and box."""
        opts = (slot.get("margin", 0.06), slot.get("budget", 48), tuple(slot.get("keyline") or ()),
                bool(slot.get("shadow", False)))
        cache_key = (origin, key, width, height, opts)
        if cache_key not in self._fitted:
            self._fitted[cache_key] = fit_mark(mark, width, height, margin=opts[0], budget=opts[1],
                                               keyline=slot.get("keyline"), shadow=opts[3])
        return self._fitted[cache_key]

    def shield(self, season):
        if season >= MODERN_SHIELD_FROM_SEASON:
            return modern_shield(), "mod_shield_2008"
        require(self.period is not None, "Super Bowls before the 2008 season need the period shield from the retail "
                                         "disc (s43dd.iff)")
        return self.period, "disc_period_shield"

    def user(self, kind, key, season=None):
        """(RGBA or None, origin, note) for an overridable slot. A team takes ``teams/<CODE>_<SEASON>.png`` for
        one season before ``teams/<CODE>.png`` for every season."""
        if (kind, key, season) in self._cache:
            return self._cache[(kind, key, season)]
        from PIL import UnidentifiedImageError
        path, reason = None, None
        for name in ([f"{key}_{season}"] if kind == "team" and season is not None else []) + [key]:
            path, why = user_art_file(self.user_art, kind, name)
            reason = reason or why
            if path is not None:
                break
        result = (None, "authored", reason)
        if path is not None:
            try:
                rel = f"{USER_FOLDERS[kind]}/{path.name}"
                if self.bundled:
                    item = logo_manifest()["files"].get(rel)
                    require(item is not None and sha(path.read_bytes()) == item["sha256"],
                            f"{rel}: bundled logo differs from its manifest")
                    origin = "bundled_logo"
                else:
                    origin = "user_art"
                result = (load_user_png(path), origin, rel)
            except (OSError, ValueError, UnidentifiedImageError) as exc:
                result = (None, "authored", f"{USER_FOLDERS[kind]}/{path.name}: {exc}")
        self._cache[(kind, key, season)] = result
        return result


# --- compositing -------------------------------------------------------------------------------------------------

def _halve(p):
    """2 x 2 box reduction of a premultiplied int64 (h, w, 4) array; an odd edge is repeated."""
    import numpy as np
    if p.shape[0] % 2:
        p = np.concatenate([p, p[-1:]], 0)
    if p.shape[1] % 2:
        p = np.concatenate([p, p[:, -1:]], 1)
    return (p[0::2, 0::2] + p[1::2, 0::2] + p[0::2, 1::2] + p[1::2, 1::2] + 2) // 4


def _area_weights(n_in, n_out):
    """(n_out, n_in) integer overlaps of output and input texel intervals; each row sums to n_in."""
    import numpy as np
    i = np.arange(n_out)[:, None]
    j = np.arange(n_in)[None, :]
    lo = np.maximum(j * n_out, i * n_in)
    hi = np.minimum((j + 1) * n_out, (i + 1) * n_in)
    return np.maximum(hi - lo, 0).astype(np.int64)


def resample(rgba, width, height):
    """Area resampling of an RGBA uint8 array to (height, width) with premultiplied alpha, in exact integer
    arithmetic (no BLAS, no Pillow), so the Studio writes the same texels on every platform."""
    import numpy as np
    a = rgba[..., 3:4].astype(np.int64)
    p = np.concatenate([rgba[..., :3].astype(np.int64) * a, a * 255], -1)
    while p.shape[0] >= 4 * height and p.shape[1] >= 4 * width:
        p = _halve(p)
    wy, wx = _area_weights(p.shape[0], height), _area_weights(p.shape[1], width)
    rows = np.einsum("ij,jkc->ikc", wy, p)
    full = np.einsum("ij,kjc->kic", wx, rows)
    total = p.shape[0] * p.shape[1]
    q = (full + total // 2) // total
    alpha = (q[..., 3] + 127) // 255
    rgb = np.where(alpha[..., None] > 0, (q[..., :3] + np.maximum(alpha, 1)[..., None] // 2)
                   // np.maximum(alpha, 1)[..., None], 0)
    return np.dstack([np.clip(rgb, 0, 255), np.clip(alpha, 0, 255)]).astype(np.uint8)


def quantise(rgba, budget):
    """At most ``budget`` RGBA colours by the texture writer's own median cut (pure Python, deterministic)."""
    import numpy as np
    from . import nfl2k5_modern_metlife as mm
    stw = mm._tools()[4]
    h, w = rgba.shape[:2]
    palette, linear, _ = stw.quantize_levels([stw.MipLevel(0, w, h, np.ascontiguousarray(rgba).tobytes())], budget)
    table = np.asarray(palette, np.uint8).reshape(-1, 4)
    return table[np.frombuffer(linear[0], np.uint8)].reshape(h, w, 4)


def _grow(alpha):
    """3 x 3 maximum of a uint8 mask (zero outside)."""
    import numpy as np
    padded = np.pad(alpha, 1)
    h, w = alpha.shape
    return np.max([padded[y:y + h, x:x + w] for y in range(3) for x in range(3)], 0)


def fit_mark(mark, width, height, *, margin=0.06, budget=48, keyline=None, shadow=False):
    """RGBA (height, width) holding a mark trimmed to its visible pixels, fitted by aspect inside the safe margin,
    centred, held to ``budget`` colours, with an optional 1-texel keyline and a soft one-texel shadow. Exact integer
    arithmetic throughout."""
    import numpy as np
    mark = np.ascontiguousarray(mark, dtype=np.uint8)
    ys, xs = np.nonzero(mark[..., 3] > 8)
    require(len(ys) > 0, "the mark is empty")
    src = mark[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    pad = max(0, int(round(min(width, height) * margin)))
    edge = (1 if keyline else 0) + (1 if shadow else 0)
    inner_w, inner_h = max(1, width - 2 * pad - 2 * edge), max(1, height - 2 * pad - 2 * edge)
    sh, sw = src.shape[:2]
    if sw * inner_h >= sh * inner_w:
        fw, fh = inner_w, max(1, (sh * inner_w * 2 + sw) // (2 * sw))
    else:
        fw, fh = max(1, (sw * inner_h * 2 + sh) // (2 * sh)), inner_h
    fitted = resample(src, fw, fh)
    if budget and budget < 256:
        fitted = quantise(fitted, budget)
    out = np.zeros((height, width, 4), np.uint8)
    x, y = (width - fw) // 2, (height - fh) // 2
    if shadow:
        shade = np.zeros((height, width), np.int64)
        shade[y + 1:y + 1 + fh, x + 1:x + 1 + fw] = fitted[..., 3].astype(np.int64) * 9 // 16
        out = over(out, np.dstack([np.zeros((height, width, 3), np.uint8), shade.astype(np.uint8)]))
    if keyline:
        a = np.zeros((height, width), np.uint8)
        a[y:y + fh, x:x + fw] = fitted[..., 3]
        ring = np.minimum(_grow(a).astype(np.int64) * 4, 255).astype(np.uint8)
        ring = np.where(_grow(a) > 64, 255, ring).astype(np.uint8)
        colour = np.broadcast_to(np.asarray(keyline[:3], np.uint8), (height, width, 3))
        out = over(out, np.dstack([colour, ring]))
    placed = np.zeros((height, width, 4), np.uint8)
    placed[y:y + fh, x:x + fw] = fitted
    return over(out, placed)


def shade_like(mark, base):
    """The mark's RGB modulated by the base's local brightness relative to its mean (cloth folds carry through);
    integer arithmetic."""
    import numpy as np
    lum = base[..., 0].astype(np.int64) * 299 + base[..., 1].astype(np.int64) * 587 + base[..., 2].astype(np.int64) * 114
    mean = max(1000, int(lum.sum()) // max(1, lum.size))
    ratio = np.clip((lum * 1000 + mean // 2) // mean, 820, 1120)
    out = mark.copy()
    out[..., :3] = np.clip((mark[..., :3].astype(np.int64) * ratio[..., None] + 500) // 1000, 0, 255).astype(np.uint8)
    return out


def over(dst, src):
    """Straight-alpha source-over of two RGBA uint8 arrays of the same shape, in integer arithmetic."""
    import numpy as np
    sa = src[..., 3:4].astype(np.int64)
    da = dst[..., 3:4].astype(np.int64)
    oa = sa * 255 + da * (255 - sa)
    rgb = (src[..., :3].astype(np.int64) * sa * 255 + dst[..., :3].astype(np.int64) * da * (255 - sa)
           + oa // 2) // np.maximum(oa, 1)
    alpha = (oa + 127) // 255
    return np.dstack([np.where(oa > 0, rgb, 0), alpha]).clip(0, 255).astype(np.uint8)


def compose(texture, row_entry, marks):
    """(RGBA of the texture's art, slot receipts): the base with every slot filled from its source."""
    base = art(texture)
    marks_layer = layer(texture)
    receipts = []
    for slot in texture.get("slots", ()):
        x0, y0, x1, y1 = slot["box"]
        w, h = x1 - x0, y1 - y0
        region = base[y0:y1, x0:x1]
        kind, key = slot["kind"], slot.get("key")
        if kind == "shield":
            mark, origin = marks.shield(row_entry["season"])
            note = None
        else:
            mark, origin, note = marks.user(kind, key, row_entry.get("season"))
        if mark is None:
            placed = marks_layer[y0:y1, x0:x1]
            origin = slot.get("authored", "authored")
        else:
            placed = marks.fitted(mark, origin, note if origin in ("user_art", "bundled_logo") else None, w, h, slot)
            if slot.get("shade"):
                placed = shade_like(placed, region)
        base[y0:y1, x0:x1] = over(region, placed)
        receipt = dict(material=texture["material"], kind=kind, key=key, box=list(slot["box"]), source=origin)
        if kind != "shield":
            receipt["file"] = user_file_name(row_entry, kind, key)
        if note:
            receipt["note"] = note
        receipts.append(receipt)
    return base, receipts


def area_mask(texture, width, height):
    """Boolean (height, width) mask of the painted texels: the listed areas, or the whole texture."""
    import numpy as np
    mask = np.zeros((height, width), bool)
    boxes = texture.get("areas") or [[0, 0] + list(texture["size"])]
    sx, sy = width / texture["size"][0], height / texture["size"][1]
    for x0, y0, x1, y1 in boxes:
        mask[int(y0 * sy):int(y1 * sy), int(x0 * sx):int(x1 * sx)] = True
    return mask


def target(decoded, rec, r, texture, row_entry, marks):
    """(RGBA the surface should carry, resized, slot receipts) from its art, its slots, its alpha mode and the disc
    texels it keeps."""
    from . import nfl2k5_modern_venues_2026 as mv
    from PIL import Image
    import numpy as np
    width, height = int(r["width"]), int(r["height"])
    rgba, slots = compose(texture, row_entry, marks)
    resized = rgba.shape[:2] != (height, width)
    if resized:
        rgba = np.asarray(Image.fromarray(rgba).resize((width, height), Image.Resampling.LANCZOS)).copy()
    current = mv.read_texture(decoded, rec, r)
    if texture["alpha"] == "source":
        rgba[..., 3] = np.where(current[..., 3] >= 128, 255, 0).astype(np.uint8)
    elif texture["alpha"] == "art":
        rgba[..., 3] = np.where(rgba[..., 3] >= 128, 255, 0).astype(np.uint8)
    else:
        rgba[..., 3] = 255
    if texture.get("areas"):
        keep = ~area_mask(texture, width, height)
        rgba[keep] = current[keep]
    return rgba, resized, slots


def already_painted(decoded, rec, row_entry, marks):
    """True when every listed surface already shows its art (within quantisation error) with the expected cutout.
    Surfaces that keep disc texels outside their areas cannot be re-quantised to identical bytes, so a replay is
    recognised here instead of by byte equality."""
    from . import nfl2k5_modern_venues_2026 as mv
    import numpy as np
    rows = mv.p8_rows(rec)
    materials = mv.rows_by_material(rec)
    for texture in row_entry["textures"]:
        if texture["material"] not in materials:
            return False
        r = rows[materials[texture["material"]]]
        want, _, _ = target(decoded, rec, r, texture, row_entry, marks)
        have = mv.read_texture(decoded, rec, r)
        mask = area_mask(texture, int(r["width"]), int(r["height"])) & (want[..., 3] >= 128)
        if not np.array_equal(have[..., 3] >= 128, want[..., 3] >= 128):
            return False
        if mask.any() and float(np.abs(have[mask][:, :3].astype(int) - want[mask][:, :3].astype(int)).mean()) > 6.0:
            return False
    return True


def painted(decoded, rec, row_entry, marks, cap=256):
    """(edited decoded scene, texture receipts, slot receipts) with every listed surface painted.

    ``alpha: source`` keeps the disc texture's own cutout (the crowd banners' cloth outlines), ``art`` uses the
    authored cutout and ``opaque`` fills the texture. Cutouts are snapped to fully opaque or clear. A surface with
    ``areas`` keeps the disc's texels outside them.
    """
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_modern_venues_2026 as mv
    rows = mv.p8_rows(rec)
    materials = mv.rows_by_material(rec)
    system = int(rec["system_bytes"])
    edited = bytearray(decoded)
    receipts, slots = [], []
    done = set()
    for texture in row_entry["textures"]:
        require(texture["material"] in materials, f"stadium scene lacks {texture['material']}")
        index = materials[texture["material"]]
        require(index not in done, f"{texture['material']} shares a texture with another listed surface")
        done.add(index)
        r = rows[index]
        width, height = int(r["width"]), int(r["height"])
        rgba, resized, placed = target(decoded, rec, r, texture, row_entry, marks)
        slots += placed
        colours = mm.write_p8(edited, system, r, rgba, cap)
        receipts.append(dict(material=texture["material"], texture=index, size=[width, height],
                             alpha=texture["alpha"], palette_entries=colours, resized=resized,
                             pixel_offset=int(r["pixel_offset"]), palette_offset=int(r["palette_offset"])))
    return edited, receipts, slots


def slot_sources(row_entry, marks):
    """Slot receipts (what fills each slot) without touching a scene."""
    out = []
    for texture in row_entry["textures"]:
        out += compose(texture, row_entry, marks)[1]
    return out


def texture_bytes(decoded, rec, indices):
    """{texture index: sha256 of its pixel chain and palette} for the comparison receipts."""
    from . import nfl2k5_modern_venues_2026 as mv
    rows = mv.p8_rows(rec)
    system = int(rec["system_bytes"])
    out = {}
    for index in indices:
        r = rows[index]
        start, end = system + int(r["pixel_offset"]), system + int(r["palette_offset"]) + 1024
        out[str(index)] = sha(bytes(decoded[start:end]))
    return out


def _stadium_chunk(bundle):
    from . import nfl2k5_modern_metlife as mm
    tx = mm._tools()[0]
    found = []
    for chunk in tx.parse_chunks(bundle, allow_trailing=True):
        if chunk.kind == "SCNE":
            rec, decoded = mm._scene(bundle, chunk)
            if rec.get("name") == "stadium":
                found.append((chunk, rec, decoded))
    require(len(found) == 1, "venue resource lacks a single stadium scene")
    return found[0]


def apply(bundle, row, *, period_shield=None, user_art=None, marks=None):
    """(bundle, receipt) with the row's event walls; rows without event walls return (bundle, None) unchanged.

    ``period_shield`` is the RGBA from :func:`period_shield` (needed for Super Bowls before the 2008 season);
    ``user_art`` is the logo folder (:func:`effective_user_art` picks the bundled one for an empty plan field).
    ``marks`` may carry both instead.
    """
    from . import nfl2k5_modern_metlife as mm
    row_entry = entry(row)
    if row_entry is None:
        return bundle, None
    marks = marks or Marks(period_shield, user_art)
    tx = mm._tools()[0]
    chunk, rec, decoded = _stadium_chunk(bundle)
    span = mm.scene_span(bundle, chunk)
    head = dict(row=row, event=row_entry["event"], stadium_offset=chunk.offset, stadium_size=len(span))
    if already_painted(decoded, rec, row_entry, marks):
        return bundle, dict(head, already_applied=True, written=False, slots=slot_sources(row_entry, marks))
    attempts = []
    for cap in mm.PALETTE_CAPS:
        edited, textures, slots = painted(decoded, rec, row_entry, marks, cap)
        if bytes(edited) == decoded:
            return bundle, dict(head, already_applied=True, written=False, textures=textures, slots=slots)
        try:
            rebuilt, info = mm.fit_span(span, bytes(edited))
        except (tx.TxtrError, mm.ModernMetLifeError) as exc:
            attempts.append(f"{cap} colours: {exc}")
            continue
        back, _ = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt, allow_trailing=True)[0])
        require(back == bytes(edited) and len(rebuilt) == len(span), f"row {row}: stadium refit read-back differs")
        result = bundle[:chunk.offset] + rebuilt + bundle[chunk.offset + len(span):]
        _check_scope(decoded, bytes(edited), rec, textures)
        return result, dict(head, already_applied=False, written=True, palette_cap=cap, fit_attempts=attempts,
                            stadium_before=sha(span), stadium_after=sha(rebuilt), decoded_before=sha(decoded),
                            decoded_after=sha(bytes(edited)), textures=textures, slots=slots, fit=info,
                            geometry_and_other_textures_identical=True)
    raise ValueError(f"row {row}: event walls do not fit the stadium span: " + " | ".join(attempts))


def _check_scope(decoded, edited, rec, textures):
    """Every changed decoded byte lies in a listed texture's pixel chain or palette."""
    system = int(rec["system_bytes"])
    allowed = [(system + t["pixel_offset"], system + t["palette_offset"] + 1024) for t in textures]
    protected = bytearray(edited)
    for start, end in allowed:
        protected[start:end] = decoded[start:end]
    require(bytes(protected) == decoded, "event walls changed bytes outside their textures")


# --- the user folder ---------------------------------------------------------------------------------------------

FRIENDLY = {
    "wall": "field wall", "ribbon": "LED ribbon boards", "wing": "video board wings", "panel": "corner boards",
    "signs4": "bowl signs", "prow": "square display", "vbanners": "hanging banners", "screen": "ring screen",
    "mesh": "mesh banner", "bands2": "field wall pads", "bands3": "ring walls", "band": "field wall",
    "hang": "hanging banner", "pad": "wall pads", "flag": "hanging flag", "mark": "wall mark",
    "corp": "crowd banners", "fans_home": "fan banners", "fans_away": "fan banners", "players": "player banners",
    "tile_logo": "wall tile", "hang_wide": "wide banner", "marquee": "concourse marquee",
}


def user_file_name(row_entry, kind, key):
    """The user folder file a slot reads first: ``super_bowl/<NUMERALS>.png``, ``brands/<name>.png``,
    ``teams/<CODE>.png``, or ``teams/<CODE>_<SEASON>.png`` for a season whose logo the mod does not carry."""
    if kind == "team" and row_entry.get("team_logos", {}).get(key) == "authored":
        return f"{USER_FOLDERS[kind]}/{key}_{row_entry['season']}.png"
    return f"{USER_FOLDERS[kind]}/{key}.png"


#: a comfortable source size per kind (any shape works: the mark is trimmed and fitted by aspect)
RECOMMENDED = {"event": (512, 512), "brand": (512, 256), "team": (256, 256)}


def slot_catalog():
    """[{file, kind, key, recommended (w, h), largest_slot (w, h), uses [(event, surfaces)]}] for every overridable
    slot, in folder order and by Super Bowl."""
    found = {}
    for r in manifest()["rows"]:
        for t in r["textures"]:
            for s in t.get("slots", ()):
                if s["kind"] == "shield":
                    continue
                name = user_file_name(r, s["kind"], s["key"])
                item = found.setdefault(name, dict(kind=s["kind"], key=Path(name).stem, largest=[0, 0], uses={}))
                w, h = s["box"][2] - s["box"][0], s["box"][3] - s["box"][1]
                if w * h > item["largest"][0] * item["largest"][1]:
                    item["largest"] = [w, h]
                surface = s.get("surface", "")
                item["uses"].setdefault(f"Super Bowl {r['event']}", set()).add(
                    FRIENDLY.get(surface, surface.replace("_", " ")))
    out = []
    folders = list(USER_FOLDERS.values())
    for name in sorted(found, key=lambda n: (folders.index(n.split("/")[0]), _order(n))):
        item = found[name]
        out.append(dict(file=name, kind=item["kind"], key=item["key"], recommended=list(RECOMMENDED[item["kind"]]),
                        largest_slot=item["largest"],
                        uses=[(event, sorted(s)) for event, s in sorted(item["uses"].items(),
                                                                         key=lambda e: _order(e[0].split()[-1]))]))
    return out


_ROMAN = dict(I=1, V=5, X=10, L=50, C=100)


def _roman(text):
    total = 0
    for a, b in zip(text, text[1:] + " "):
        v = _ROMAN.get(a, 0)
        total += -v if _ROMAN.get(b, 0) > v else v
    return total


def _order(name):
    stem = Path(name).stem
    return (_roman(stem) or 999, stem) if set(stem) <= set(_ROMAN) else (999, stem)


def user_art_readme():
    """The README.md text of the user folder, listing every file name the walls can take."""
    rows = manifest()["rows"]
    lines = [
        "# Your Super Bowl logos (optional)",
        "",
        "2K5 Mod Studio ships real Super Bowl event logos, network marks and the four team-season logos, and places",
        "them on every Super Bowl moment's walls, ribbon boards and banners by default. Put your own PNG files here",
        "and the next build places them in the matching slots instead of the bundled logos and the mod's own",
        "designed marks. Nothing in this folder is required: a missing file keeps the mod's own mark.",
        "",
        "How files are placed:",
        "",
        "- Use the exact file names below (upper or lower case both work).",
        "- A transparent PNG is preferred. The build trims empty borders, fits the image inside each slot by its",
        "  aspect ratio with a safe margin, keeps the transparency and holds it to a small colour budget so it fits",
        "  the game's 256-colour textures. An image without transparency is placed as a rectangle.",
        "- The recommended size is a comfortable source size; the largest slot in the game is much smaller, so a",
        "  sharp, simple mark reads best. Up to 4096 pixels on a side and 8 MB per file.",
        "- The build log lists which slots were filled from this folder and which kept the mod's own marks.",
        "- An event logo also fills that game's field marks on the 25s, 30s or 35s, and a team file the club marks on",
        "  the 30s of Super Bowls XXXII, XXXIV and XXXVI. Franchise Super Bowls take LXII.png, LXIII.png, LXIV.png.",
        "- The NFL shield is not taken from this folder: seasons from 2008 use the mod's official shield, and earlier",
        "  seasons use the period shield read from your own retail disc.",
        "",
        "Leave **Your Super Bowl logos** empty in Build to use the bundled real logos, or set",
        "`BuildPlan.super_bowl_user_art` to this folder to use your files instead. A folder with none of these names",
        "keeps the mod's own designed marks.",
        "",
    ]
    titles = {"event": "Event logos (`super_bowl/`)", "brand": "Network marks (`brands/`)",
              "team": "Team logos (`teams/`, optional)"}
    notes = {
        "event": ("One per Super Bowl moment, named by its Roman numerals. The Studio bundles the real logo of "
                  "each game; a file here replaces it."),
        "brand": ("The networks that carried these games, plus ESPN (the game's own presentation banner). The "
                  "Studio bundles the real network marks; a file here replaces one."),
        "team": ("The Studio bundles the real logo of the four team-seasons below, so nothing is needed here. The "
                 "mod's own 2026 team logos fill the other clubs. CODE.png replaces that club's logo in every Super "
                 "Bowl it plays; CODE_SEASON.png (the year the season began) only in that season."),
    }
    catalog = slot_catalog()
    for kind in ("event", "brand", "team"):
        w, h = RECOMMENDED[kind]
        lines += [f"## {titles[kind]}", "", notes[kind], f"Recommended: a transparent PNG about {w} x {h} pixels "
                  "or larger (any shape works). The largest slot column is the biggest box the file fills in the "
                  "game's textures, in texels.", "",
                  "| File | Largest slot | Appears on |", "| --- | --- | --- |"]
        for item in catalog:
            if item["kind"] != kind:
                continue
            uses = "; ".join(f"{event}: {', '.join(s)}" for event, s in item["uses"])
            sw, sh = item["largest_slot"]
            lines.append(f"| `{item['file']}` | {sw} x {sh} | {uses} |")
        lines.append("")
    teams_without = sorted({(r["event"], f"{code}_{r['season']}") for r in rows
                            for code, how in r.get("team_logos", {}).items() if how == "authored"},
                           key=lambda e: _order(e[0]))
    if teams_without:
        lines += ["Team-seasons with their own bundled real logo: " +
                  ", ".join(f"Super Bowl {e} `teams/{c}.png`" for e, c in teams_without) + ".", ""]
    return "\n".join(lines)


def create_user_art_layout(folder):
    """Create the folder with its three empty sub-folders and README.md; existing files are never replaced except
    the README, which is regenerated. Returns the folder."""
    from . import platform_compat as io
    root = io.io_path(io.absolute_path(folder))
    root.mkdir(parents=True, exist_ok=True)
    for sub in USER_FOLDERS.values():
        (root / sub).mkdir(exist_ok=True)
    readme = root / "README.md"
    require(not readme.is_symlink(), "README.md is a link")
    with readme.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(user_art_readme())
    return root


def user_art_summary(receipts):
    """Build-log lines from the walls receipts: the slots filled from the user folder, those filled from the bundled
    real logos, and those that kept the authored marks."""
    filled, bundled, kept, refused = {}, {}, {}, []
    for walls in receipts:
        for s in walls.get("slots", ()):
            if s["kind"] == "shield":
                continue
            name = s.get("file") or f"{USER_FOLDERS[s['kind']]}/{s['key']}.png"
            if s["source"] == "user_art":
                filled.setdefault(s.get("note", name), set()).add(walls["event"])
            elif s["source"] == "bundled_logo":
                bundled.setdefault(s.get("note", name), set()).add(walls["event"])
            else:
                kept.setdefault(name, set()).add(walls["event"])
                if s.get("note"):
                    refused.append(s["note"])
    lines = []
    if filled:
        lines.append("Super Bowl walls: filled from your folder: " + "; ".join(
            f"{name} ({', '.join(sorted(events, key=_order))})" for name, events in sorted(filled.items())))
    else:
        lines.append("Super Bowl walls: no files from your folder were placed")
    if bundled:
        lines.append("Super Bowl walls: filled from the bundled real logos: " + "; ".join(
            f"{name} ({', '.join(sorted(events, key=_order))})" for name, events in sorted(bundled.items())))
    if kept:
        lines.append("Super Bowl walls: authored marks kept for: " + ", ".join(sorted(kept, key=lambda n: (
            list(USER_FOLDERS.values()).index(n.split("/")[0]), _order(n)))))
    for note in sorted(set(refused)):
        lines.append("Super Bowl walls: ignored " + note)
    return lines


def user_art_status(folder):
    """One line for the Build panel: how many of the folder's expected files were found."""
    from . import platform_compat as io
    root = io.io_path(io.absolute_path(folder))
    if not root.is_dir():
        return f"Folder not found: {folder}. Create folder... makes it with a README of every file name."
    counts, totals, refused = {}, {}, []
    for item in slot_catalog():
        kind = item["kind"]
        totals[kind] = totals.get(kind, 0) + 1
        path, reason = user_art_file(folder, kind, item["key"])
        if path is not None:
            counts[kind] = counts.get(kind, 0) + 1
        elif reason:
            refused.append(reason)
    text = (f"Found {counts.get('event', 0)} of {totals.get('event', 0)} event logos, {counts.get('brand', 0)} of "
            f"{totals.get('brand', 0)} network marks and {counts.get('team', 0)} of {totals.get('team', 0)} team "
            "files; the rest keep the authored marks.")
    if refused:
        text += " Ignored: " + "; ".join(sorted(set(refused))) + "."
    return text

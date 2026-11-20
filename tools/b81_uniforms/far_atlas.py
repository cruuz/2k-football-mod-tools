#!/usr/bin/env python3
"""b81-uniforms R54: the far-player atlas follows the 2026 uniform pass.

Every kit package holds a 256x128 ``splayer`` atlas (chunk 51): a reduced, pre-shaded picture of the pants, torso,
helmet side and sleeve that the game draws for bench and far-away players. The 2026 uniform pass
(``data/nfl2k5_kit_fixes_2026_b81u.json``) corrects the full-size pants, jersey and sleeve textures and leaves the atlas
alone, so far players kept the old stripes, hems and marks. This tool writes ``data/nfl2k5_sideline_2026_b81u.json``:
one row per kit in the Studio's own kit-fix format (runs of the atlas texels that change), pinned to the atlas a build
holds when the step runs (``before_sha256``) and to what the Studio's compile makes of it (``after_sha256``). Each row
also pins, as ``donors``, the finished field textures it mirrors, so a kit whose pants, jersey or sleeve are a user's own
art keeps its atlas.

The picture, per changed part (pants island 0,0-128,90; torso 128,0-256,100; sleeve 195,101-256,127):
  * the part's field texture reduced onto the island by the island's own mapping: the retail atlases show the left leg of
    the pants texture (measured by registration, uniforms/work/R2/helper_s1/ATLAS_SURVEY.md, checked again in R2F),
    the islands the sideline step composed show its crop (``SIDELINE_COMPOSE``);
  * the island's baked shading S = gain x folds: the folds are the sideline step's own measure of the island
    (``_sideline_folds``), the gain the median ratio of atlas to reduced old texture where the atlas is a shade of it
    (a dark kit, where it cannot be measured, takes the part's measured default);
  * inside the changed area (native texels that moved by 4 or more, reduced to a coverage per atlas texel):
    S x reduce(new) + (1 - coverage) x (atlas - S x reduce(old)): the shaded new art where the texel is wholly
    changed, the atlas's own detail kept in proportion to the unchanged share;
  * beside it, up to 8 texels away and reached only through each other, texels that still show an old changed colour and
    that the new art does not explain within two texels of shift (the retail picture drew a stripe wider or a hem
    straighter than the texture) take the shaded new art;
  * everything else, and every texel moved by less than 4 levels, keeps its bytes. In the belt rows of a retail pants
    island (0-5) the renderer's waistband (texels the old texture does not explain) is never touched.
A retail sleeve island is a rendered sleeve, not an affine map of the texture; it is changed only where the reduced old
texture registers on it (normalised correlation of the shaded reduction >= 0.7), otherwise it is left and reported.

  python3 tools/b81_uniforms/far_atlas.py build --released V09.iso --built BUILT.iso --out data/nfl2k5_sideline_2026_b81u.json
                                                [--receipt R.json] [--decoded DIR] [--only SEL ...]

``--released`` is the released v0.9 disc (the uniform pass rows are pinned to its textures), ``--built`` a Studio build of
this branch's base (its atlases are what the step finds). Authoring tool: nothing here ships but the document.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT, ROOT / "tools"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

SCHEMA = "nfl2k5_kit_fixes_2026/v1"
SOURCE = ("b81-uniforms R54 (beta 81): the far-player atlas (chunk 51 splayer) of every kit the 2026 uniform pass changed, "
          "reduced from the corrected pants, jersey and sleeve textures and lit by the atlas's own baked shading")
METHOD = ("changed area: shading x reduced new texture + (1 - coverage) x the atlas's own residual; old-art remnants "
          "beside it take the shaded new art; everything else keeps its bytes; runs of the changed texels, pinned to the "
          "atlas a build holds and to the finished field textures (donors)")
LUMA = np.array([0.299, 0.587, 0.114], np.float64)
PARTS = {"torso": (1, "jersey00"), "pants": (2, "pants00"), "sleeve": (3, "sleeve00")}
ISLAND = {"pants": (0, 0, 128, 90), "torso": (128, 0, 256, 100), "sleeve": (195, 101, 256, 127)}
MAPS = {
    "pants": {"retail": (23.126, -0.769, 297.216, 229.974), "compose": (255.0, 0.0, 512.0, 227.0)},
    "torso": {"retail": (1.070, 0.0, 392.508, 256.41), "compose": (0.0, 0.0, 391.0, 253.0)},
    "sleeve": {"retail": (0.0, 0.0, 121.0, 65.0), "compose": (0.0, 0.0, 121.0, 65.0)},
}
BELT_ROWS = 6        # a retail pants island's rows 0-5 hold the renderer's belt (SIDELINE_RULE_REGIONS starts at 6)
MATCH = 48.0         # an atlas texel within this of shading x reduced old texture shows the texture
CHANGE = 4           # a native texel whose RGB moved by at least this much is part of the change
RELIABLE = 40.0      # the gain is measured where the reduced old texture's luma is at least this
DEFAULT_GAIN = {"pants": 0.99, "torso": 0.77, "sleeve": 0.84}   # median atlas/reduced luma, light retail islands (R2F)
REMNANT = 40.0       # an atlas texel within this of a shaded old changed colour ...
FAR = 64.0           # ... that the shaded new art does not come within this of (two texels of shift) is a remnant
GROW = 8             # remnants are looked for at most this many texels from the changed area
KEEP = 4             # an atlas texel the result moves by less than this in every channel keeps its colour
SLEEVE_NCC = 0.7     # a retail sleeve island is changed only where the old texture registers on it this well
COMPOSE_RETAIL_SLEEVES = False   # --compose-retail-sleeves: an unregistered retail sleeve is composed again instead
MATCH_AREA = 0.5     # measures: an atlas texel at least this much covered by the change is "inside the changed area"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def modules():
    import b81_uniform_pass as up
    from mod_editor.core import nfl2k5_kit_fixes_2026 as kf
    return kf, up


# -- geometry ---------------------------------------------------------------------------------------------------------

def weights(n_out: int, n_in: int, a: float, b: float) -> np.ndarray:
    """(n_out, n_in) area weights: output cell i covers source [a + i*s, a + (i+1)*s), s = (b - a) / n_out; source cells
    outside the texture are clamped to its edge texel."""
    s = (b - a) / n_out
    w = np.zeros((n_out, n_in))
    for i in range(n_out):
        lo, hi = a + i * s, a + (i + 1) * s
        for j in range(int(np.floor(lo)), int(np.ceil(hi))):
            ov = min(hi, j + 1) - max(lo, j)
            if ov > 0:
                w[i, min(max(j, 0), n_in - 1)] += ov
        w[i] /= w[i].sum()
    return w


def reduce(img: np.ndarray, box, size) -> np.ndarray:
    """Area-reduce ``img`` (h, w[, c]) over the fractional ``box`` (x0, y0, x1, y1) to ``size`` (w, h)."""
    x0, y0, x1, y1 = box
    wy, wx = weights(size[1], img.shape[0], y0, y1), weights(size[0], img.shape[1], x0, x1)
    a = img.astype(np.float64)
    if a.ndim == 2:
        return wy @ a @ wx.T
    return np.stack([wy @ a[..., c] @ wx.T for c in range(a.shape[2])], axis=2)


def _chroma(c):
    return c / np.maximum(c.sum(axis=-1, keepdims=True), 1.0)


def _ncc(a, b):
    a, b = a - a.mean(), b - b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 1e-9 else 0.0


def shading(atlas, island, ro, part):
    """(S, gain): the island's baked shading as gain x folds (the sideline step's fold measure, median 1)."""
    kf, _ = modules()
    x0, y0, x1, y1 = ISLAND[part]
    fold = kf._sideline_folds(atlas, (x0, y0, x1, y1)).astype(np.float64)
    lo, la = ro @ LUMA, island @ LUMA
    ok = (lo >= RELIABLE) & (np.abs(_chroma(island) - _chroma(ro)).max(axis=2) < 0.05)
    gain = float(np.clip(np.median(la[ok] / (lo[ok] * fold[ok])), 0.3, 1.5)) if ok.sum() >= 30 else DEFAULT_GAIN[part]
    return gain * fold, gain


def part_change(atlas: np.ndarray, old: np.ndarray, new: np.ndarray, part: str, mapping: str):
    """(wanted island RGB float or None, info) for one part of one kit (``atlas`` the whole 128x256 RGBA atlas,
    ``old``/``new`` the part's native RGBA textures). None: the part is left as it is (``info['left']`` says why)."""
    x0, y0, x1, y1 = ISLAND[part]
    size = (x1 - x0, y1 - y0)
    box = MAPS[part][mapping]
    a = atlas[y0:y1, x0:x1, :3].astype(np.float64)
    o, n = old[..., :3].astype(np.float64), new[..., :3].astype(np.float64)
    mask = np.abs(n - o).max(axis=2) >= CHANGE
    cov = reduce(mask.astype(np.float64), box, size)
    ro, rn = reduce(o, box, size), reduce(n, box, size)
    shade, gain = shading(atlas, a, ro, part)
    residual = a - shade[..., None] * ro
    lit = shade
    if gain > 1.0:
        # an atlas palette lighter than its texture (gain above 1) is a colour difference, not shading: only colours the
        # old kit wore keep it; a colour the old kit never had (the Rams' new gold) is not brightened past the texture
        colours, counts = np.unique(o.reshape(-1, 3).astype(np.int64), axis=0, return_counts=True)
        seen = colours[np.argsort(-counts, kind="stable")[:12]].astype(np.float64)
        known = np.min([np.abs(rn - c).max(axis=2) for c in seen], axis=0) <= 24
        lit = np.where(known, shade, shade / gain)
    ideal = lit[..., None] * rn
    belt = np.zeros(cov.shape, bool)
    if part == "pants" and mapping == "retail":
        # the renderer's belt: in rows 0-5 a texel the old texture does not explain (a dark waistband over white
        # fabric) is kept; a stripe the atlas draws through the belt rows follows the texture
        belt[:BELT_ROWS] = np.abs(residual[:BELT_ROWS]).max(axis=2) > MATCH
        cov[belt] = 0.0
    info = dict(mapping=mapping, gain=round(gain, 4), native_changed=int(mask.sum()),
                area=int((cov >= MATCH_AREA).sum()), cov=cov, ideal=ideal, shade=shade, ro=ro, rn=rn)
    if part == "sleeve" and mapping == "retail":
        info["registration"] = round(_ncc(a @ LUMA, (shade[..., None] * ro) @ LUMA), 3)
        if info["registration"] < SLEEVE_NCC:
            if COMPOSE_RETAIL_SLEEVES:
                # the island shows another design's sleeve: it is laid again from the corrected sleeve texture by the
                # sideline step's own compose (its crop, lit by the island's folds), as vk2 did for other kits
                kf, _ = modules()
                composed = kf._sideline_compose(atlas, "sleeve", new, {})[y0:y1, x0:x1, :3].astype(np.float64)
                moved = np.abs(composed - a).max(axis=2) >= KEEP
                info.update(remnant=0, moved=int(moved.sum()), composed=True,
                            ideal=composed)            # the measures read the composed island as its target
                info["cov"] = np.ones(cov.shape)
                return np.where(moved[..., None], composed, a), info
            info["left"] = ("retail sleeve picture does not register on the sleeve texture (NCC %.2f < %.2f)"
                            % (info["registration"], SLEEVE_NCC))
            return None, info
    want = np.where((cov > 0)[..., None], ideal + (1.0 - cov)[..., None] * residual, a)
    remnant = np.zeros(cov.shape, bool)
    olds = o[mask]
    if len(olds):
        colours, counts = np.unique(olds.astype(np.int64), axis=0, return_counts=True)
        near_old = np.full(cov.shape, np.inf)
        for c in colours[np.argsort(-counts, kind="stable")[:8]].astype(np.float64):
            near_old = np.minimum(near_old, np.abs(a - shade[..., None] * c).max(axis=2))
        explained = np.full(cov.shape, np.inf)
        pad = np.pad(ideal, ((2, 2), (2, 2), (0, 0)), mode="edge")
        for dy in range(5):
            for dx in range(5):
                explained = np.minimum(explained,
                                       np.abs(a - pad[dy:dy + cov.shape[0], dx:dx + cov.shape[1]]).max(axis=2))
        candidate = (near_old <= REMNANT) & (explained >= FAR)
        candidate[belt] = False
        seed = cov > 0
        remnant = seed & candidate
        frontier = seed
        for _ in range(GROW):
            grown = frontier.copy()
            grown[1:, :] |= frontier[:-1, :]
            grown[:-1, :] |= frontier[1:, :]
            grown[:, 1:] |= frontier[:, :-1]
            grown[:, :-1] |= frontier[:, 1:]
            add = grown & candidate & ~remnant & ~seed
            if not add.any():
                break
            remnant |= add
            frontier = add
        want = np.where(remnant[..., None], ideal, want)
    want = np.clip(np.round(want), 0, 255)
    moved = np.abs(want - a).max(axis=2) >= KEEP
    info.update(remnant=int(remnant.sum()), moved=int(moved.sum()))
    return np.where(moved[..., None], want, a), info


def measure(island, ideal, cov):
    """Mean |island - shaded new| (0-255 per channel) inside the changed area (coverage >= 0.5)."""
    area = cov >= MATCH_AREA
    return round(float(np.abs(island - ideal)[area].mean()), 2) if area.any() else None


# -- palette --------------------------------------------------------------------------------------------------------

MAX_NEW = 40         # at most this many new palette colours per atlas (the compile names each one)


def fit_palette(span: bytes, atlas: np.ndarray, want: np.ndarray, limit: int = MAX_NEW):
    """(want quantised, stats): every changed texel takes either a colour the atlas palette keeps for the texels outside
    the change (exactly) or one of at most len(free) new colours, the free entries being those no texel outside the
    change uses at any mip (``free_slots``). The new colours are a k-means fit to what the protected colours miss, so
    the compile never folds or moves an entry a protected texel uses."""
    kf, _ = modules()
    chunk, decoded, textures = kf.native_textures(span, "txtr")
    planes = kf.read_planes(decoded, chunk, textures[0])
    palette = kf.read_palette(decoded, chunk, textures[0]).astype(np.int64)
    scope = (want[..., :3] != atlas[..., :3]).any(axis=2)
    kf.require(bool((atlas[..., 3][scope] == 255).all()), "a changed atlas texel is not opaque")
    free = kf.free_slots(planes, kf.scope_chain(scope, planes))
    fixed = np.array([i for i in range(256) if i not in set(free) and palette[i, 3] == 255], np.int64)
    protected = palette[fixed, :3].astype(np.float64)
    target = want[scope][:, :3].astype(np.float64)
    k = min(len(free), limit)

    def assign(centres):
        pool = np.concatenate([protected, centres]) if len(centres) else protected
        d = ((target[:, None, :] - pool[None, :, :]) ** 2).sum(axis=2)
        return pool, d.argmin(axis=1), np.sqrt(d.min(axis=1))

    centres = np.zeros((0, 3))
    pool, pick, err = assign(centres)
    while len(centres) < k and err.max() > 3.0:          # farthest-point seeds where the protected colours miss most
        centres = np.concatenate([centres, target[int(err.argmax())][None]])
        pool, pick, err = assign(centres)
    for _ in range(10):                                   # Lloyd steps on the new colours only
        moved = False
        for j in range(len(centres)):
            members = pick == len(protected) + j
            if members.any():
                mean = np.round(target[members].mean(axis=0))
                if (mean != centres[j]).any():
                    centres[j], moved = mean, True
        pool, pick, err = assign(centres)
        if not moved:
            break
    out = want.copy()
    out[scope, :3] = np.clip(np.round(pool[pick]), 0, 255).astype(np.uint8)
    used_new = int(len(np.unique(pick[pick >= len(protected)])))
    return out, dict(free_entries=len(free), new_colours=used_new, scope_texels=int(scope.sum()),
                     quantise_mean=round(float(np.abs(out[scope, :3].astype(np.float64) - target).mean()), 2),
                     quantise_worst=int(np.abs(out[scope, :3].astype(np.int64) - target.astype(np.int64)).max()))


# -- the kits ---------------------------------------------------------------------------------------------------------

def composed_parts() -> dict:
    kf, _ = modules()
    return {row["selector"]: set((row.get("compose") or {})) for row in kf.sideline()["kits"]}


def field_kit(raw: bytes, selector: str) -> bytes:
    """The kit package after the 2026 uniform pass (its rows are pinned to the released textures)."""
    kf, _ = modules()
    document = kf.uniforms_b81()
    if not any(r["selector"] == selector for r in document["textures"]):
        return raw
    replacements, receipt = kf.compile_resource(selector, raw, strict=False, document=document)
    out = bytearray(raw)
    for offset, data in replacements:
        out[offset:offset + len(data)] = data
    return bytes(out)


def span_of(raw: bytes, index: int) -> bytes:
    kf, _ = modules()
    chunk = kf._chunk_for(raw, index)
    return raw[chunk.offset:chunk.end_offset]


def plan_kit(selector: str, released: bytes, built: bytes, composed: set):
    """(wanted atlas RGBA or None, build package bytes, per-part receipt)."""
    kf, up = modules()
    field = field_kit(released, selector)
    require = kf.require
    require(len(built) == len(field), selector + ": the built package's size differs from the released one")
    c51 = kf._chunk_for(field, 51)
    b51 = kf._chunk_for(built, 51)
    require((c51.offset, c51.end_offset) == (b51.offset, b51.end_offset), selector + ": atlas allocation moved")
    package = field[:c51.offset] + built[c51.offset:c51.end_offset] + field[c51.end_offset:]
    atlas, _native = up.level0(span_of(package, 51), "txtr")
    want = atlas.copy()
    parts = {}
    for part, (index, name) in PARTS.items():
        old_span, new_span = span_of(released, index), span_of(field, index)
        if old_span == new_span:
            continue
        old, _ = up.level0(old_span, "tset")
        new, _ = up.level0(new_span, "tset")
        mapping = "compose" if part in composed else "retail"
        wanted, info = part_change(atlas, old, new, part, mapping)
        x0, y0, x1, y1 = ISLAND[part]
        island = atlas[y0:y1, x0:x1, :3].astype(np.float64)
        record = {k: v for k, v in info.items() if k not in ("cov", "ideal", "shade", "ro", "rn")}
        record["before"] = measure(island, info["ideal"], info["cov"])
        if wanted is not None and info["moved"]:
            want[y0:y1, x0:x1, :3] = wanted.astype(np.uint8)
            record["field_sha256"] = sha(new_span)
            record["chunk"] = index
        parts[part] = (record, info)
    moved = (want[..., :3] != atlas[..., :3]).any(axis=2)
    return (want if moved.any() else None), package, parts


FIT_LADDER = (MAX_NEW, 16, 8, 4, 0)   # a tight allocation (the fill cannot keep the scratch word): fewer new colours


def kit_job(job):
    """One kit, in a worker: (selector, receipt entry, row or None, after RGBA or None, before RGBA or None)."""
    selector, released, built, composed = job
    kf, up = modules()
    try:
        want, package, parts = plan_kit(selector, released, built, composed)
        atlas, _ = up.level0(span_of(package, 51), "txtr")
        entry = dict(parts={p: r for p, (r, _i) in parts.items()}, atlas_before_sha256=sha(span_of(package, 51)),
                     atlas_released_sha256=sha(span_of(released, 51)))
        if want is None:
            entry["state"] = "unchanged"
            return selector, entry, None, None, None
        mirrored = sorted(r["chunk"] for r, _i in parts.values() if "chunk" in r)
        names = [p for p, (r, _i) in parts.items() if "chunk" in r]
        note = "far-player atlas: " + ", ".join(names) + " of the 2026 uniform pass"
        error = None
        for limit in FIT_LADDER:
            quantised, fit = fit_palette(span_of(package, 51), atlas, want, limit)
            try:
                row, after, stats = up.build_row(selector, "splayer", package, quantised,
                                                 dict(note=note, snap=0, family=0, declare=MAX_NEW + 8))
                break
            except ValueError as exc:
                if "scratch word" not in str(exc) and "fit" not in str(exc).lower() and "palette" not in str(exc):
                    raise
                error = exc
        else:
            raise error
        entry["palette"] = fit
        if row is None:
            entry["state"] = "unchanged after snapping"
            return selector, entry, None, None, None
        row["parts"] = names
        row["donors"] = {str(i): sha(span_of(package, i)) for i in mirrored}
        # end to end, as a build runs it: the guard reads the finished field textures, the compile gives the pin
        replacements, _applied = kf.compile_resource(selector, package, strict=True,
                                                     document=dict(schema=SCHEMA, textures=[row]))
        kf.require(len(replacements) == 1 and sha(replacements[0][1]) == row["after_sha256"],
                   selector + ": the Studio compile differs from the pin")
        for part, (record, info) in parts.items():
            x0, y0, x1, y1 = ISLAND[part]
            record["after"] = measure(after[y0:y1, x0:x1, :3].astype(np.float64), info["ideal"], info["cov"])
        entry.update(state="row", stats=stats, parts={p: r for p, (r, _i) in parts.items()})
        return selector, entry, row, after, atlas
    except Exception as exc:  # noqa: BLE001 - named in the receipt and the document; the other kits are still written
        return selector, dict(state="failed", error=str(exc)[:300]), None, None, None


def cmd_build(args) -> int:
    from concurrent.futures import ProcessPoolExecutor
    from PIL import Image
    kf, up = modules()
    rows_b81u = kf.uniforms_b81()["textures"]
    selectors = sorted({r["selector"] for r in rows_b81u if r["chunk"] in (1, 2, 3)})
    if args.only:
        selectors = [s for s in selectors if s in set(args.only)]
    released = up.read_kits(Path(args.released), selectors)
    built = up.read_kits(Path(args.built), selectors)
    composed = composed_parts()
    rows, receipt, failed = [], {}, 0
    decoded = Path(args.decoded) if args.decoded else None
    if decoded:
        decoded.mkdir(parents=True, exist_ok=True)
    jobs = [(s, released[s], built[s], composed.get(s, set())) for s in selectors]
    with ProcessPoolExecutor(max_workers=max(1, int(args.workers))) as pool:
        for selector, entry, row, after, before in pool.map(kit_job, jobs):
            receipt[selector] = entry
            if entry["state"] == "failed":
                failed += 1
                print("FAILED", selector, entry["error"][:200], flush=True)
                continue
            if row is None:
                continue
            rows.append(row)
            if decoded:
                Image.fromarray(after, "RGBA").save(decoded / f"{selector}_splayer.png")
                Image.fromarray(before, "RGBA").save(decoded / f"{selector}_splayer_before.png")
            stats = entry["stats"]
            print(selector, row["parts"], stats["texels"], "texels, new colours", entry["palette"]["new_colours"],
                  "of", entry["palette"]["free_entries"], "free, quantise mean", entry["palette"]["quantise_mean"],
                  flush=True)
    rows.sort(key=lambda r: r["selector"])
    # every kit the uniform pass changed is a row, unchanged in the atlas, or left with its reason
    unchanged = sorted(s for s, e in receipt.items() if e.get("state", "").startswith("unchanged"))
    left = {s: "not written: " + e["error"][:160] for s, e in sorted(receipt.items()) if e.get("state") == "failed"}
    left_parts = {f"{s}:{p}": r["left"] for s, e in sorted(receipt.items()) for p, r in sorted(e.get("parts", {}).items())
                  if r.get("left")}
    composed_sleeves = sorted(s for s, e in receipt.items() if e.get("parts", {}).get("sleeve", {}).get("composed"))
    document = dict(schema=SCHEMA, source=SOURCE, method=METHOD, textures=rows, unchanged=unchanged, left=left,
                    left_parts=left_parts, composed_sleeves=composed_sleeves)
    Path(args.out).write_text(json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8",
                              newline="\n")
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                      newline="\n")
    print(json.dumps(dict(rows=len(rows), texels=sum(r["texels"] for r in rows), failed=failed,
                          unchanged=len(unchanged), left_parts=len(left_parts))))
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build")
    build.add_argument("--released", required=True)
    build.add_argument("--built", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--receipt")
    build.add_argument("--decoded")
    build.add_argument("--only", nargs="+")
    build.add_argument("--workers", type=int, default=3)
    build.add_argument("--compose-retail-sleeves", action="store_true")
    args = parser.parse_args(argv)
    global COMPOSE_RETAIL_SLEEVES
    COMPOSE_RETAIL_SLEEVES = bool(args.compose_retail_sleeves)
    return cmd_build(args)


if __name__ == "__main__":
    sys.exit(main())

"""Carry the selected u4 fan art onto retained model textures.

No artwork lives here. The build's existing venue-art folder supplies the same
manifest, retail PNGs, masters, rectangles and weather composition as u4. Models
without those materials keep their geometry and bytes. Base model pins remain
valid; a composed span is recognized through its checked build receipt. SoFi's
neutral s40, which has no club art, takes its reviewed residual cloth item from
the shared-art catalog instead (neutral_plan).
"""
from __future__ import annotations

from copy import deepcopy

FAN_KEYS = frozenset(("banner_home_player", "banner_home_team", "banner_away_team"))


def receipt_rows(source, model_receipt):
    """Use the venue receipt retained by Studio's export/compaction paths too."""
    from . import nfl2k5_modern_venues_2026 as mv
    venue = mv.read_receipt(source) or {}
    rows = {name: dict(fan_art=pin) for name, pin in venue.get("model_fan_art", {}).items()}
    rows.update((model_receipt or {}).get("bundles", {}))
    return rows


def preserve_receipts(target, model_receipt):
    """Carry model fan pins inside the already-supported venue-art sidecar.

    Standalone model callers still have their model receipt. A composed Studio
    build also has u4's receipt, which the exporter and compactor already copy.
    Its original bundle pins and ownership are left untouched.
    """
    from . import nfl2k5_modern_venues_2026 as mv
    venue = mv.read_receipt(target)
    if venue is None:
        return
    authored = {name: row["fan_art"] for name, row in model_receipt["bundles"].items() if row.get("fan_art")}
    if authored:
        venue.setdefault("model_fan_art", {}).update(authored)
        mv._save_receipt(target, venue)


def applied(have, pin, receipt):
    """Accept a composed span only if its receipt descends from a pinned model."""
    if not receipt:
        return False
    parents = {pin[k] for k in ("model_sha256", "model_portrait_sha256", "classic_sha256") if k in pin}
    return (receipt.get("schema") == "nfl2k5_model_fan_art/v1"
            and receipt.get("before_sha256") in parents
            and receipt.get("offset") == pin["offset"]
            and receipt.get("length") == pin["length"]
            and have == receipt.get("after_sha256"))


def paint_bundle(bundle, filename, plan):
    """Only P8 fan pixels/palettes change in the decoded stadium scene.

    The existing u4 painter supplies all sizing, mip, palette and weather rules.
    Texture indices are resolved on the finished model because it compacts them.
    Compression is refit inside the model's existing span without a palette step
    down. Every byte outside that compressed scene stays identical.
    """
    from . import nfl2k5_modern_venues_2026 as mv
    mm = mv._mm()
    chunk = mv.bundle_scenes(bundle)["stadium"]
    rec, decoded = mm._scene(bundle, chunk)
    remapped = []
    for item in plan["items"]:
        if item["scene"] != "stadium" or item["key"] not in FAN_KEYS:
            continue
        index = mv.find_stadium_texture(rec, item["key"])
        if index is None:
            continue  # removed by the model owner's geometry filter
        row = mv.p8_rows(rec)[index]
        mapped = deepcopy(item)
        mapped["variants"] = {filename[3:5]: [index, row["width"], row["height"]]}
        remapped.append(mapped)
    if not remapped:
        return bundle, None
    painted, detail = mv.paint_scene(decoded, rec, filename[:3], filename[3:5],
                                     dict(items=remapped), plan["base"], cap=256)
    span = mm.scene_span(bundle, chunk)
    after, fit = mm.fit_span(span, painted)
    mv.require(len(after) == len(span), f"{filename}: fan art escaped model span")
    mv.require(after[:32] == span[:32], f"{filename}: fan art changed model wrapper")
    tx = mv._tools()[0]
    back, _ = tx.decode_chunk(after, tx.parse_chunks(after, allow_trailing=True)[0])
    mv.require(back == painted, f"{filename}: fan art read-back differs")
    out = bytearray(bundle)
    out[chunk.offset:chunk.offset + len(span)] = after
    return bytes(out), dict(textures=detail["textures"], palette_cap=256,
                            decoded_before_sha256=mv.sha(decoded), decoded_after_sha256=mv.sha(painted),
                            fit=fit)


def neutral_plan(prefix, retail):
    """The plan for a neutral slot that a model writer builds (shared.MODEL_NEUTRAL: SoFi's s40), or None.

    Such a slot has no u4 team art and no venue-table row. Its retained fan
    cloth takes the reviewed residual items of the shared-art catalog instead,
    planned the way plan_venue plans a venue's items. Each item's texture is
    found in the retail dry-day stadium scene, which also supplies the weather
    base. paint_bundle then maps each item onto the finished model's own texture
    index, as it does for club art.
    """
    from . import nfl2k5_modern_venues_2026 as mv
    from . import nfl2k5_stadium_shared_art as shared
    if prefix not in shared.MODEL_NEUTRAL:
        return None
    items = list(shared.items(prefix))
    if not items:
        return None
    mv.require(all(i["scene"] == "stadium" and i["key"] in FAN_KEYS for i in items),
               f"{prefix}: a neutral model slot takes fan cloth items only")
    rec, decoded = mv.decode_scenes(retail[f"{prefix}dd.iff"])["stadium"]
    rows = mv.p8_rows(rec)
    planned, base = [], {}
    for item in items:
        index = mv.find_stadium_texture(rec, item["key"])
        mv.require(index is not None, f"{prefix}: {item['key']} names no retail dry-day texture")
        row = rows[index]
        mv.require([int(row["width"]), int(row["height"])] == item["size"],
                   f"{prefix}: {item['key']} is not {item['size'][0]}x{item['size'][1]} in the retail dry-day scene")
        planned.append(dict(item, dd=dict(scene="stadium", index=index), variants={}))
        base[("stadium", index)] = mv.read_texture(decoded, rec, row)
    manifest = shared.ART_ROOT / prefix / "manifest.json"
    return dict(prefix=prefix, items=planned, base=base,
                manifest=manifest.relative_to(shared.ROOT).as_posix(), digest=mv.sha(manifest.read_bytes()))


def paint_results(results, retail, art_root, pins):
    """Shared final texture step in each model writer, before archive writes.

    No art root means the original pinned model. Home venues take the art
    root's club fan art. SoFi's neutral s40 never takes club art. Under the
    same art-root switch it takes only its residual cloth item from the
    shared-art catalog (neutral_plan).
    """
    from . import nfl2k5_modern_venues_2026 as mv
    from . import nfl2k5_stadium_shared_art as shared
    if not art_root:
        return results
    art = mv.load_art(art_root)
    plans = {}
    by_name = {p["name"]: p for p in pins["bundles"]}
    out = []
    for name, bundle, info in results:
        prefix = name[:3]
        venue = art["venues"].get(prefix)
        if venue is None and prefix not in shared.MODEL_NEUTRAL:
            out.append((name, bundle, info))
            continue
        if prefix not in plans:
            if venue is None:
                plans[prefix] = neutral_plan(prefix, retail)
            else:
                # Keep only u4 fan items. Sponsor supplements never enter a model.
                fans = dict(venue, items=[i for i in venue["items"]
                                         if i["scene"] == "stadium" and i["key"] in FAN_KEYS])
                if not fans["items"]:
                    plans[prefix] = None
                else:
                    planned = mv.plan_venue(prefix, fans, {n: b for n, b in retail.items() if n[:3] == prefix})
                    planned["items"] = [i for i in planned["items"] if i["key"] in FAN_KEYS]
                    plans[prefix] = planned
        if plans[prefix] is None:
            out.append((name, bundle, info))
            continue
        after, detail = paint_bundle(bundle, name, plans[prefix])
        if detail is not None:
            pin = by_name[name]
            start, end = pin["offset"], pin["offset"] + pin["length"]
            source = venue or plans[prefix]
            receipt = dict(schema="nfl2k5_model_fan_art/v1", offset=start, length=pin["length"],
                           before_sha256=mv.sha(bundle[start:end]), after_sha256=mv.sha(after[start:end]),
                           manifest=source["manifest"], art_digest=source["digest"], **detail)
            mv.require(applied(receipt["after_sha256"], pin, receipt),
                       f"{name}: fan art requires a pinned base model")
            info = dict(info, fan_art=receipt)
        out.append((name, after, info))
    return out

"""Explicit, lossless separation of a venue's shared north/south field paint.

The explicitly selected Cleveland/Detroit/Houston routes copy three P8 textures at their
original resolution, palette and mip count. Existing south materials point to
the copies; geometry, draw words and every existing texture stay identical.
Call before painting so the normal colour/weather writers see independent ends.
"""
from __future__ import annotations

import copy

from . import nfl2k5_scne_builder as sb

VENUES = {"s09", "s30", "s37"}
LOAN_VENUES = {"s09", "s30"}
PARTS = "LMR"


def pairs(scene):
    result = []
    for part in PARTS:
        north = [m for m in scene.materials if m.name == "endzone_N_" + part]
        south = [m for m in scene.materials if m.name == "endzone_S_" + part]
        sb.require(len(north) == len(south) == 1, "end-zone material pair is missing or repeated")
        sb.require(north[0].texture is not None and south[0].texture is not None,
                   "end-zone material lacks its P8 texture")
        result.append((north[0], south[0]))
    return result


def assert_original_scene(before, after, painted_textures=()):
    """Remove only the copies/links and canonically restore every original record."""
    sb.require(len(after.textures) == len(before.textures) + 3,
               "end-zone separation must append exactly three textures")
    restored = copy.deepcopy(after)
    for index in painted_textures:
        sb.require(0 <= index < len(after.textures), "painted texture index is outside the scene")
        if index < len(before.textures):
            restored.textures[index].pixels = before.textures[index].pixels
            restored.textures[index].palette = before.textures[index].palette
    for (old_n, old_s), (new_n, new_s) in zip(pairs(before), pairs(restored)):
        sb.require(old_n.texture == old_s.texture and new_n.texture == old_n.texture,
                   "end-zone separation changed the north texture link")
        sb.require(new_s.texture >= len(before.textures), "south texture was not appended")
        new_s.texture = old_s.texture
    del restored.textures[len(before.textures):]
    sb.require(sb.serialize(restored) == sb.serialize(before),
               "end-zone separation changed an existing scene record")


def split_span(span, name, *, painter=None):
    """Return a fixed-size field SCNE with independent, initially identical ends.

    This function supplies allocation and routing. It never invents or applies
    team art. An already independent set of ends is an exact no-op; partial
    sharing refuses. The caller must explicitly select the source manifest flag.
    """
    from . import nfl2k5_modern_metlife as ml
    from . import nfl2k5_usbank_model as um

    sb.require(name[:3] in VENUES, "end-zone split has not been reviewed for " + name[:3])
    tx = ml._tools()[0]
    chunks = tx.parse_chunks(span, allow_trailing=True)
    sb.require(len(chunks) == 1 and chunks[0].kind == "SCNE", "split expects one field SCNE span")
    chunk = chunks[0]
    decoded, _ = tx.decode_chunk(span, chunk)
    before = sb.parse(decoded, chunk.system_bytes, secondary=True)
    shared = [n.texture == s.texture for n, s in pairs(before)]
    if not any(shared):
        return bytes(span), dict(added=False, reason="existing independent end-zone textures")
    sb.require(all(shared), "partially shared end-zone textures are not supported")
    added = copy.deepcopy(before)
    links = []
    for north, south in pairs(added):
        texture = added.textures[north.texture]
        sb.require((texture.width, texture.height) == (256, 128),
                   "end-zone split requires the reviewed native 256x128 allocation")
        index = len(added.textures)
        added.textures.append(copy.deepcopy(texture))
        links.append(dict(material=south.name, original_texture=south.texture,
                          appended_texture=index, size=[texture.width, texture.height],
                          mips=texture.mips))
        south.texture = index
    assert_original_scene(before, added)
    authored, system, video = sb.serialize(added)
    painted_indices = ()
    paint_receipt = None
    if painter is not None:
        authored, paint_receipt = painter(authored, system, video)
        sb.require(len(authored) == system + video, "end-zone painter changed scene allocation")
        painted_indices = tuple(row["texture"] for row in paint_receipt["textures"])
        added = sb.parse(authored, system, secondary=True)
        assert_original_scene(before, added, painted_indices)
    attempts = []
    # Painting leaves the appended palettes at the decoded tail. Keep enough
    # unused video after them for the subsequent colour/surface refits too.
    # No texture points into this padding and no pixel/mip/palette is reduced.
    for padding in ((4096, 8192) if painter is not None else (128, 256, 512, 1024)):
        try:
            after, fit = um.fit_keep_scratch(authored + bytes(padding), system, video + padding, span)
            break
        except sb.ScneBuildError as exc:
            attempts.append(dict(unused_video_padding=padding, error=str(exc)))
    else:
        raise sb.ScneBuildError("full-resolution end-zone paint cannot keep its scratch: " + str(attempts))
    back, _ = tx.decode_chunk(after, tx.parse_chunks(after, allow_trailing=True)[0])
    assert_original_scene(before, sb.parse(back, system, secondary=True), painted_indices)
    sb.require(len(after) == len(span) and after[:8] == span[:8]
               and after[16:32] == span[16:32], "end-zone split changed allocation or scratch")
    return after, dict(added=True, links=links, existing_scene_preserved=True,
                       paint=paint_receipt,
                       extra_video_padding=padding, system=system, video=video + padding,
                       fit_attempts=attempts, **fit)


def owned_scope(data, name):
    """The reviewed field allocation, including its lossless donor when used."""
    from . import nfl2k5_modern_metlife as ml
    if name[:3] in LOAN_VENUES:
        from . import nfl2k5_midfield_art as mf
        _field, _layer, normal, _decoded = mf.pit_sites(data)
        return 0, normal.end_offset, "field_detail_prefix"
    sb.require(name[:3] in VENUES, "end-zone scope has not been reviewed")
    field = ml.bundle_scenes(data)["field"]
    return field.offset, field.end_offset - field.offset, "field"


def split_bundle(data, name, *, painter=None):
    """Separate selected ends using a measured, lossless field-normal loan.

    Only DET/CLE borrow allocation. Their original normal pixels, palette and
    mips remain exact; the intervening compressed detail-layer span is copied
    byte for byte. The original Fldd offset and every later byte stay fixed.
    Already independent ends are an exact no-op, before any donor compression.
    """
    from . import nfl2k5_modern_metlife as ml
    sb.require(name[:3] in VENUES, "end-zone split has not been reviewed")
    tx = ml._tools()[0]
    field = ml.bundle_scenes(data)["field"]
    decoded, _ = tx.decode_chunk(data, field)
    scene = sb.parse(decoded, field.system_bytes, secondary=True)
    if all(n.texture != s.texture for n, s in pairs(scene)):
        return bytes(data), dict(added=False, reason="existing independent end-zone textures")
    if name[:3] not in LOAN_VENUES:
        span = ml.scene_span(data, field)
        after, receipt = split_span(span, name, painter=painter)
        end = field.end_offset
        out = data[:field.offset] + after + data[end:]
        sb.require(out[:field.offset] == data[:field.offset] and out[end:] == data[end:],
                   "end-zone split escaped its field allocation")
        return out, dict(receipt, scope_offset=field.offset, scope_size=len(span),
                         scope_kind="field", outside_scope_identical=True)
    from . import nfl2k5_midfield_art as mf
    field, layer, normal, old_normal = mf.pit_sites(data)
    span = ml.scene_span(data, field)
    new_normal, loan = mf.compress_detail_normal(ml.scene_span(data, normal))
    header = list(tx.HEADER.unpack_from(span))
    header[1] += loan["loan"]
    enlarged = tx.HEADER.pack(*header) + span[tx.HEADER.size:] + bytes(loan["loan"])
    after, receipt = split_span(enlarged, name, painter=painter)
    old_layer = ml.scene_span(data, layer)
    end = normal.end_offset
    out = after + old_layer + new_normal + data[end:]
    sb.require(len(out) == len(data) and out[end:] == data[end:],
               "end-zone allocation loan escaped its field prefix")
    _field, new_layer, new_normal_chunk, decoded_normal = mf.pit_sites(out)
    sb.require(ml.scene_span(out, new_layer) == old_layer and decoded_normal == old_normal
               and new_normal_chunk.end_offset == end,
               "end-zone loan changed detail-layer or normal data")
    return out, dict(receipt, allocation_loan=loan, scope_offset=0, scope_size=end,
                     scope_kind="field_detail_prefix", old_field_size=len(span),
                     field_size=len(after), detail_layer_span_identical=True,
                     detail_normal_decoded_identical=True, outside_scope_identical=True)

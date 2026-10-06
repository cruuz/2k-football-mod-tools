"""Opt-in missing midfield overlays, using the existing native field SCNE writer.

Only DEN, MIA and PIT have reviewed placements here. Existing midfield draws
are exact no-ops. The source venue manifest must request ``add_missing_midfield``;
the presence of a logo alone never enables this writer.
"""
from __future__ import annotations

import struct

from . import nfl2k5_scne_builder as sb

# DEN: ink approximately ten yards across in the 2026 official home-game
# gallery. Its art has a 90% coverage box; placement is an inference.
# MIA: copy the unmodified afternoon/night quad, keeping those variants intact.
HALF_EXTENTS = {
    "s08": (5.08, 5.08),
    "s14": (4.232652893066406, 4.575841064453125),
    "s22": (5.08, 5.08),
}
MATERIAL = "center_logo"
LOAN_PREFIX = "s22"


class TeamField(dict):
    """Texture arrays with a manifest-controlled midfield opt-in."""
    add_missing_midfield = False


def assert_existing_scene(before, after):
    """Prove that removing the appended overlay recreates every old record.

    Serialized pointer locations change with SCNE growth. Compare independently
    reparsed records through the canonical serializer instead of absolute offsets.
    All original texture pixels, palettes, vertex streams and draw words remain.
    """
    import copy

    restored = copy.deepcopy(after)
    original = before.shape("D_graphic_overlays")
    overlay = restored.shape("D_graphic_overlays")
    sb.require(len(restored.textures) == len(before.textures) + 1
               and len(restored.materials) == len(before.materials) + 1,
               "midfield must append exactly one texture and material")
    sb.require(restored.materials[-1].name == MATERIAL
               and len(overlay.submeshes) == len(original.submeshes) + 1
               and overlay.vertex_count == original.vertex_count + 4
               and overlay.submeshes[-1].material == len(restored.materials) - 1,
               "midfield must append one draw and four private vertices")
    restored.textures.pop()
    restored.materials.pop()
    overlay.submeshes.pop()
    struct.pack_into("<H", overlay.record, 0x4C, original.vertex_count)
    struct.pack_into("<H", overlay.record, 0x54, len(original.submeshes))
    overlay.streams = [None if value is None else value[:len(old)]
                       for value, old in zip(overlay.streams, original.streams)]
    sb.require(sb.serialize(restored) == sb.serialize(before),
               "midfield append changed an existing scene record")


def append_span(span, name, logo):
    """Add one full 256x256 P8 overlay inside the fixed stored field span.

    The native loader scratch word stays unchanged. An extra 128 bytes of unused
    video padding keep palette-tail literals away from the in-place decoder's
    unread input. This changes no texture allocation or scene record.
    """
    from . import nfl2k5_modern_metlife as ml
    from . import nfl2k5_usbank_model as um

    sb.require(name[:3] in HALF_EXTENTS, "midfield placement has not been reviewed for " + name[:3])
    tx = ml._tools()[0]
    chunks = tx.parse_chunks(span, allow_trailing=True)
    sb.require(len(chunks) == 1 and chunks[0].kind == "SCNE", "midfield expects one field SCNE span")
    chunk = chunks[0]
    decoded, _ = tx.decode_chunk(span, chunk)
    before = sb.parse(decoded, chunk.system_bytes, secondary=True)
    if any(m.name == MATERIAL for m in before.materials):
        sb.require(any(before.materials[sub.material].name == MATERIAL
                       for shape in before.shapes for sub in shape.submeshes),
                   "field midfield material has no draw")
        return bytes(span), dict(added=False, reason="existing midfield draw")
    authored, system, video = um.add_midfield(decoded, chunk.system_bytes, logo, cap=256, half=False)
    added = sb.parse(authored, system, secondary=True)
    overlay = added.shape("D_graphic_overlays")
    positions = bytearray(overlay.streams[0])
    hx, hz = HALF_EXTENTS[name[:3]]
    for i in range(before.shape("D_graphic_overlays").vertex_count, overlay.vertex_count):
        at = overlay.stride(0) * i
        x, y, z = struct.unpack_from("<3f", positions, at)
        struct.pack_into("<3f", positions, at, x * hx / um.MIDFIELD_HALF, y, z * hz / um.MIDFIELD_HALF)
    overlay.streams[0] = bytes(positions)
    original = before.shape("D_graphic_overlays")
    cx, cy, cz = struct.unpack_from("<3f", original.record, 0)
    radius = struct.unpack_from("<f", original.record, 0x48)[0]
    for i in range(original.vertex_count, overlay.vertex_count):
        x, y, z = struct.unpack_from("<3f", positions, overlay.stride(0) * i)
        sb.require((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2 <= radius ** 2,
                   "new midfield vertices escape the existing overlay bounds")
    overlay.record[:12] = original.record[:12]
    overlay.record[0x48:0x4C] = original.record[0x48:0x4C]
    authored, system, video = sb.serialize(added)
    assert_existing_scene(before, added)
    after, fit = um.fit_keep_scratch(authored + bytes(128), system, video + 128, span)
    reparsed, _ = tx.decode_chunk(after, tx.parse_chunks(after, allow_trailing=True)[0])
    assert_existing_scene(before, sb.parse(reparsed, system, secondary=True))
    sb.require(len(after) == len(span) and after[:8] == span[:8]
               and after[16:32] == span[16:32], "midfield changed the fixed wrapper or loader scratch")
    return after, dict(added=True, native_size=[256, 256], palette_cap=256,
                      half_detail=False, half_extents_m=[hx, hz],
                      extra_video_padding=128, existing_scene_preserved=True,
                      system=system, video=video + 128, **fit)


def pit_sites(data):
    """The contiguous field/detail-layer/detail-normal prefix; Fldd stays put."""
    from . import nfl2k5_modern_metlife as ml
    tx = ml._tools()[0]
    chunks = tx.parse_chunks(data, allow_trailing=True)
    sb.require(len(chunks) >= 4 and [c.kind for c in chunks[:4]] == ["SCNE", "SCNE", "TXTR", "Fldd"],
               "PIT field prefix differs from the reviewed chunk route")
    field, layer, normal = chunks[:3]
    sb.require(ml._scene(data, field)[0].get("name") == "field"
               and ml._scene(data, layer)[0].get("name") == "detail_layer",
               "PIT field/detail-layer names differ")
    decoded, _ = tx.decode_chunk(data, normal)
    texture = tx.parse_texture(decoded, normal)
    sb.require(texture.name == "detail_normal" and texture.format_name == "P8"
               and (texture.width, texture.height, texture.mip_levels) == (512, 256, 6)
               and normal.system_bytes == 128 and normal.video_bytes == 175744,
               "PIT detail-normal descriptor differs")
    return field, layer, normal, decoded


def compress_detail_normal(span, *, loan_bytes=None):
    """Losslessly compress PIT's raw P8 normal with its original zero scratch.

    Retail FUN_0004dc00 reads the offset width from stream byte 8, constructs
    (1 << width)-1 and (1 << (16-width))-1 masks and has no width-14 special
    case. The actual retail code has been run in-place with this width-15
    stream: exact 175872 output bytes, no reads/writes beyond that allocation.
    The same compressed detail_normal resource/descriptor route ships in s11
    and s15. Width 14 saves too little for the full-resolution PIT snow logo.
    """
    from . import nfl2k5_modern_metlife as ml
    tx = ml._tools()[0]
    import nfl_vc_lz_fill as fill
    header = list(tx.HEADER.unpack_from(span))
    chunk = tx.parse_chunks(span)[0]
    sb.require(not chunk.compressed and chunk.overlap_scratch_bytes == 0,
               "PIT allocation loan needs the reviewed raw, zero-scratch normal")
    decoded, _ = tx.decode_chunk(span, chunk)
    encoded = fill.compress_optimal(decoded, stream_tag=4614, offset_bits=15)
    first = (len(encoded) + 15) & ~15
    for stored in range(first, min(chunk.stored_size, first + 256), 16):
        filled, expanded = fill.fill_stream(encoded, decoded, stored, slack=0)
        alias = tx.minimum_vc_lz_overlap_scratch(filled, stored, len(decoded))
        if len(filled) == stored and alias == 0 and len(fill.parse_tokens(filled)[3]) % 8 != 0:
            break
    else:
        raise sb.ScneBuildError("PIT normal cannot keep zero scratch and the native final-flag read inside its allocation")
    sb.require(stored < chunk.stored_size, "PIT normal provides no allocation loan")
    if loan_bytes is not None:
        sb.require(type(loan_bytes) is int and loan_bytes > 0 and loan_bytes % 16 == 0,
                   "normal allocation loan must be a positive aligned byte count")
        requested = chunk.stored_size-loan_bytes
        sb.require(requested >= stored, "normal cannot provide the requested allocation loan")
        filled, expanded = fill.fill_stream(encoded, decoded, requested, slack=0)
        alias = tx.minimum_vc_lz_overlap_scratch(filled, requested, len(decoded))
        sb.require(len(filled) == requested and alias == 0 and len(fill.parse_tokens(filled)[3]) % 8 != 0,
                   "normal allocation loan cannot keep its native final read inside zero scratch")
        stored = requested
    header[1], header[4] = stored, tx.COMPRESSED_SENTINEL
    rebuilt = tx.HEADER.pack(*header) + filled
    back, info = tx.decode_chunk(rebuilt, tx.parse_chunks(rebuilt)[0])
    sb.require(back == decoded and info.consumed_bytes == stored,
               "PIT normal lossless read-back differs")
    return rebuilt, dict(old_stored=chunk.stored_size, stored=stored,
                         loan=chunk.stored_size - stored, offset_bits=15,
                         encoded=len(encoded), expanded=expanded, scratch=0,
                         alias_scratch=alias, decoded_identical=True)


def append_pit_bundle(data, name, logo):
    """Borrow only the field-owned normal's allocation, preserving total size.

    The intervening detail-layer span relocates unchanged. Fldd and every
    subsequent byte, including the city/stadium spans and offsets, stay exact.
    """
    from . import nfl2k5_modern_metlife as ml
    sb.require(name[:3] == LOAN_PREFIX, "allocation loan is reviewed only for PIT")
    tx = ml._tools()[0]
    field, layer, normal, old_normal = pit_sites(data)
    field_span = ml.scene_span(data, field)
    decoded, _ = tx.decode_chunk(data, field)
    scene = sb.parse(decoded, field.system_bytes, secondary=True)
    if any(m.name == MATERIAL for m in scene.materials):
        sb.require(any(scene.materials[s.material].name == MATERIAL
                       for shape in scene.shapes for s in shape.submeshes), "existing PIT midfield has no draw")
        return bytes(data), dict(added=False, reason="existing midfield draw")
    new_normal, detail = compress_detail_normal(ml.scene_span(data, normal))
    header = list(tx.HEADER.unpack_from(field_span))
    header[1] += detail["loan"]
    enlarged = tx.HEADER.pack(*header) + field_span[tx.HEADER.size:] + bytes(detail["loan"])
    new_field, receipt = append_span(enlarged, name, logo)
    old_layer = ml.scene_span(data, layer)
    end = normal.end_offset
    out = new_field + old_layer + new_normal + data[end:]
    sb.require(len(out) == len(data) and out[end:] == data[end:], "PIT loan escaped its field prefix")
    nf, nl, nn, decoded_normal = pit_sites(out)
    sb.require(ml.scene_span(out, nl) == old_layer and decoded_normal == old_normal
               and nn.end_offset == end, "PIT loan changed detail-layer or normal data")
    return out, dict(receipt, allocation_loan=detail, scope_offset=0, scope_size=end,
                     old_field_size=len(field_span), field_size=len(new_field),
                     detail_layer_span_identical=True, detail_normal_decoded_identical=True,
                     outside_prefix_identical=True)


def refit_washington_field(data, name, painter, *, normal_span=None, loan_bytes=1680):
    """Fit reviewed WAS paint using only lossless field-normal allocation.

    Studio supplies the ordinary surface writer's complete raw normal. Native
    repair can omit it to preserve its current normal instead. The stored
    detail layer is copied exactly; Fldd and every later byte stay at their
    original offsets. No texture or scene record is reduced or added here.
    """
    from . import nfl2k5_modern_metlife as ml
    sb.require(name[:3] == "s29", "existing field allocation loan is reviewed only for WAS")
    tx = ml._tools()[0]
    field, layer, normal, _old_normal = pit_sites(data)
    span = ml.scene_span(data, field)
    donor = ml.scene_span(data, normal) if normal_span is None else bytes(normal_span)
    donor_chunk = tx.parse_chunks(donor)[0]
    sb.require(len(donor) == normal.end_offset-normal.offset
               and donor_chunk.system_bytes == normal.system_bytes
               and donor_chunk.video_bytes == normal.video_bytes,
               "WAS normal replacement changed its original allocation")
    expected_normal, _ = tx.decode_chunk(donor, donor_chunk)
    new_normal, loan = compress_detail_normal(donor, loan_bytes=loan_bytes)
    header = list(tx.HEADER.unpack_from(span))
    header[1] += loan["loan"]
    enlarged = tx.HEADER.pack(*header) + span[tx.HEADER.size:] + bytes(loan["loan"])
    new_field, paint = painter(enlarged)
    sb.require(len(new_field) == len(enlarged) and new_field[:32] == enlarged[:32],
               "WAS painter changed its enlarged wrapper/allocation")
    old_layer = ml.scene_span(data, layer)
    end = normal.end_offset
    out = new_field + old_layer + new_normal + data[end:]
    sb.require(len(out) == len(data) and out[end:] == data[end:], "WAS loan escaped its field prefix")
    _field, new_layer, new_normal_chunk, decoded_normal = pit_sites(out)
    sb.require(ml.scene_span(out, new_layer) == old_layer and decoded_normal == expected_normal
               and new_normal_chunk.end_offset == end, "WAS loan changed its layer/normal/suffix")
    return out, dict(paint=paint, allocation_loan=loan, scope_offset=0, scope_size=end,
                     scope_kind="field_detail_prefix", old_field_size=len(span), field_size=len(new_field),
                     detail_layer_span_identical=True, detail_normal_decoded_identical=True,
                     outside_prefix_identical=True)


def apply_late_to_image(target, art_root, *, progress=None):
    """Studio's explicit PIT manifest option, after the final surface writer."""
    from . import nfl2k5_modern_metlife as ml
    from . import nfl2k5_modern_venues_2026 as mv
    from . import nfl2k5_modern_surfaces as surfaces
    from . import nfl2k5_modern_color as colour
    art = mv.load_art(art_root)
    venue = art["venues"].get(LOAN_PREFIX)
    if not venue or not venue.get("add_missing_midfield"):
        return None
    item = next(i for i in venue["items"] if i["scene"] == "field" and i["key"] == MATERIAL)
    logo = mv._art_at(item, 256, 256)
    receipts, changed = [], {}
    say = progress or (lambda message, done, total: None)
    with mv._outer_image()(str(target), writable=True) as archive:
        for index, pin in enumerate(mv.venues()[LOAN_PREFIX]["bundles"]):
            entry = mv._entry(archive, pin)
            before = archive.read(entry.virtual_offset, entry.size)
            after, receipt = append_pit_bundle(before, pin["name"], logo)
            if after != before:
                owned = after[:receipt["scope_size"]]
                sb.require(archive.write(entry.virtual_offset, owned) == len(owned), "short PIT midfield write")
                sb.require(archive.read(entry.virtual_offset, entry.size) == after, "PIT midfield image read-back differs")
            changed[pin["name"]] = after
            receipts.append(dict(name=pin["name"], before_sha256=ml.sha(before), after_sha256=ml.sha(after), **receipt))
            say("PIT full-resolution midfield", index + 1, 9)
    # Historical receipt windows retain their reviewed retail offsets/sizes;
    # their applied digests and complete-bundle digests follow the new bytes.
    colour_receipt = colour.read_image_receipt(target)
    if colour_receipt is not None:
        for name, after in changed.items():
            surfaces._update_colour_receipt(colour_receipt, name, after)
        colour._save_image_receipt(target, colour_receipt)
    venues_receipt = mv.read_receipt(target)
    if venues_receipt is not None:
        for name, after in changed.items():
            if name in venues_receipt.get("bundles", {}):
                venues_receipt["bundles"][name]["applied_sha256"] = ml.sha(after)
        mv._save_json(mv.receipt_path(target), venues_receipt)
    surface_receipt = surfaces.read_receipt(target)
    if surface_receipt is not None:
        for row in receipts:
            if row["name"] in surface_receipt.get("bundles", {}):
                surface_receipt["bundles"][row["name"]].update(applied_sha256=row["after_sha256"], midfield=row)
        surfaces.save_receipt(target, surface_receipt)
    return dict(state="applied", bundles=receipts)

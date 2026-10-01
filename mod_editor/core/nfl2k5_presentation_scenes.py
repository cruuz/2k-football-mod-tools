"""Embedded presentation scene textures: the raw MRKS transport adapter and the fixed-span SCNE refit.

The ESPN presentation scenes keep their textures inside the scene resource: a descriptor table in the
system buffer and the pixel indices and palette of each descriptor in the video buffer. Two resource
shapes carry them (the presentation research, r2 sections 1 and 2):

- raw MRKS: the six streamed wipes of ``wipe.cdf`` (outer 3114, pack 4) are uncompressed (compression
  word 0, scratch word 0, stored body = system + video bytes). An MRKS wraps its scene one level down:
  MRKS +0x14 points at a wrapper descriptor at +0x20 whose first relative pointer owns the ordinary scene
  descriptor. :func:`scene_view` gives the strict SCNE parser a temporary view of that descriptor; the
  original bytes are never changed by it.
- VC-LZ SCNE: the pause scoreboard (outer 347 chunk 5), the helmet bumper (outer 18 chunk 11) and the
  other menu and studio scenes are compressed. Their stored body is the compressed stream, a zero gap
  and an opaque tail; the 32-byte wrapper carries the in-place decode scratch word.

The raw adapter (:func:`compile_raw`) replaces the pixel and palette bytes of chosen descriptors at the
same allocation and nothing else: the wrapper, the system buffer, every other video byte and the span
size stay byte-identical, and there is no compression step to fit. The SCNE path
(:func:`compile_compressed`) uses the stadium writer's allocation contract and compiler, then refits the
stream to the retail consumed length so the wrapper (scratch word included) and the opaque tail are
kept, and checks the retail scratch still covers the in-place decode (the r2 coach-desk recipe).

Every descriptor must pass the stadium writer's ``_target_contract``: P8, one complete halving mip chain
that ends exactly at its palette, no overlap with another descriptor, and a decoded base level that
matches the parser. PNGs are compiled with the same quantiser, swizzle and mip generation as the Stadium
Studio. Offsets are relative to the decoded resource, never independent offsets in compressed bytes.
EXPERIMENTAL; appearance in game is UNWITNESSED.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
_TOOLS = ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from . import nfl2k5_stadium_texture_writer as stadium  # noqa: E402
from nfl_scene_probe import ResourceRecord, decode_resource  # noqa: E402
from nfl_scne_inventory import parse_scene  # noqa: E402
from nfl_tset_png_import import palette_bytes, quantize_levels, rgba_from_indices  # noqa: E402
from nfl_txtr import COMPRESSED_SENTINEL, HEADER, minimum_vc_lz_overlap_scratch, swizzle_2d  # noqa: E402
from nfl_vc_lz_fill import compress_optimal, fill_stream  # noqa: E402

MRKS = "MRKS"
SCNE = "SCNE"
PALETTE_BYTES = 1024
MRKS_WRAPPER_POINTER = 13          # MRKS +0x14 -> the wrapper descriptor at +0x20


class PresentationSceneError(ValueError):
    """A presentation scene resource, descriptor or compiled texture failed closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PresentationSceneError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def scene_view(decoded: bytes, kind: str) -> bytes:
    """The bytes the strict SCNE parser reads: an MRKS is re-pointed at its owned scene descriptor.

    MRKS +0x14 resolves its wrapper descriptor at +0x20; that descriptor's first relative pointer owns the
    ordinary scene descriptor. Only this temporary view changes (+0x0C and +0x14); offsets, materials,
    geometry and allocations are the original decoded bytes.
    """

    if kind == SCNE:
        return decoded
    require(kind == MRKS, f"{kind} is not a presentation scene resource")
    require(len(decoded) >= 0x24 and decoded[12:16] == b"MRKS"
            and struct.unpack_from("<i", decoded, 20)[0] == MRKS_WRAPPER_POINTER,
            "MRKS wrapper descriptor drift")
    descriptor = 32 + struct.unpack_from("<i", decoded, 32)[0] - 1
    require(0x24 <= descriptor < len(decoded), "MRKS scene descriptor pointer is out of range")
    view = bytearray(decoded)
    view[12:16] = b"SCNE"
    struct.pack_into("<i", view, 20, descriptor - 20 + 1)
    return bytes(view)


@dataclass(frozen=True)
class SceneResource:
    """One complete scene resource span, decoded and parsed (read only)."""

    record: ResourceRecord
    span: bytes
    decoded: bytes
    raw: bool
    consumed: int
    opaque_tail: bytes
    scene: dict

    @property
    def kind(self) -> str:
        return self.record.kind

    @property
    def system_bytes(self) -> int:
        return self.record.word_08

    @property
    def video_bytes(self) -> int:
        return self.record.word_0c

    @property
    def scratch(self) -> int:
        return self.record.word_14

    @property
    def textures(self) -> tuple[dict, ...]:
        return tuple(self.scene["embedded_textures"])


def open_resource(span: bytes, *, outer_index: int, outer_id: str = "", outer_size: int = 0,
                  chunk_index: int = 0, chunk_offset: int = 0) -> SceneResource:
    """Validate and parse one scene resource span (wrapper + stored body), raw MRKS or VC-LZ SCNE."""

    span = bytes(span)
    require(len(span) >= HEADER.size, "scene resource span is truncated")
    kind_raw, stored, system, video, magic, scratch, reserved0, reserved1 = HEADER.unpack_from(span)
    kind = kind_raw.decode("ascii", "replace")
    require(kind in (MRKS, SCNE), f"{kind!r} is not an MRKS or SCNE resource")
    require(len(span) == HEADER.size + stored and reserved0 == reserved1 == 0,
            f"{kind}: the span does not match its wrapper")
    record = ResourceRecord(outer_index, outer_id, outer_size or len(span), chunk_index, chunk_offset, kind,
                            stored, system, video, magic, scratch)
    if magic == 0:
        require(stored == system + video and scratch == 0,
                f"{kind}: a raw resource must store exactly its system and video bytes with no scratch")
        decoded, consumed, tail = span[HEADER.size:], stored, b""
    else:
        require(magic == COMPRESSED_SENTINEL and kind == SCNE, f"{kind}: unsupported compression word 0x{magic:08x}")
        decoded, detail = decode_resource(span, record)
        consumed = int(detail["lz"]["consumed_bytes"])
        tail = span[HEADER.size + consumed:]
    require(len(decoded) == system + video, f"{kind}: decoded size differs from the wrapper")
    scene = parse_scene(0, record, scene_view(decoded, kind), {})[0]
    return SceneResource(record, span, decoded, magic == 0, consumed, tail, scene)


def texture_contract(resource: SceneResource, texture_index: int, *, pack_name: str = "",
                     pack_offset: int = 0) -> "stadium.DynamicStadiumP8Contract":
    """The stadium writer's fixed-allocation contract for one embedded descriptor of this resource."""

    record = resource.record
    base = dict(
        outer_index=record.outer_index, outer_id=record.outer_id, chunk_index=record.chunk_index, scene_index=0,
        pack_name=pack_name, pack_sector=0, pack_size=0, pack_sha256="", pack_offset=pack_offset,
        chunk_offset=record.chunk_offset, stored_size=record.stored_size, system_bytes=record.word_08,
        video_bytes=record.word_0c, decoded_sha256=digest(resource.decoded),
        source_span_sha256=digest(resource.span), retail_consumed=resource.consumed,
        retail_scratch=record.word_14, opaque_tail_size=len(resource.opaque_tail),
        opaque_tail_sha256=digest(resource.opaque_tail))
    selector = f"presentation:o{record.outer_index}:c{record.chunk_index}:t{texture_index}"
    try:
        return stadium._DynamicStadiumResolver._target_contract(
            selector, texture_index, resource.textures, resource.decoded, base)
    except stadium.StadiumTextureWriterError as exc:
        raise PresentationSceneError(f"{selector}: {exc}") from exc


def allocation(contract: "stadium.DynamicStadiumP8Contract") -> tuple[int, int, int, int]:
    """(pixel start, pixel end, palette start, palette end) in the decoded resource."""

    pixel = contract.system_bytes + contract.pixel_offset
    palette = contract.system_bytes + contract.palette_offset
    return pixel, pixel + contract.index_chain_bytes, palette, palette + PALETTE_BYTES


def decoded_mips(decoded: bytes, contract: "stadium.DynamicStadiumP8Contract") -> tuple[bytes, ...]:
    """RGBA of every mip level of one descriptor, straight from decoded resource bytes."""

    return stadium._decode_dynamic_p8_mips(decoded, contract)


def compile_texture(contract: "stadium.DynamicStadiumP8Contract", png: Path | str
                    ) -> tuple[bytes, bytes, tuple[bytes, ...], dict[str, Any]]:
    """PNG -> (swizzled index chain, 1,024-byte palette, expected RGBA per mip, receipt), Stadium rules."""

    try:
        payload, rgba = stadium._read_dynamic_png(Path(png), contract)
        levels = stadium._generate_dynamic_mips(rgba, contract.mip_dimensions)
        palette, linear, quantization = quantize_levels(levels)
    except (stadium.StadiumTextureWriterError, OSError, ValueError) as exc:
        raise PresentationSceneError(f"{contract.texture_id}: {exc}") from exc
    indices = b"".join(swizzle_2d(ix, level.width, level.height, 1) for level, ix in zip(levels, linear))
    colours = palette_bytes(palette)
    require(len(indices) == contract.index_chain_bytes and len(colours) == PALETTE_BYTES,
            f"{contract.texture_id}: the compiled allocation changed size")
    expected = tuple(rgba_from_indices(ix, palette) for ix in linear)
    return indices, colours, expected, dict(
        png_sha256=digest(payload), png_rgba_sha256=digest(rgba), palette_entries=len(palette),
        quantization=dict(quantization), mip_rgba_sha256=[digest(level) for level in expected],
        base_rgba_exact=expected[0] == rgba)


def _apply(resource: SceneResource, edits: Sequence[tuple[int, Path | str]], *, pack_name: str, pack_offset: int
           ) -> tuple[bytes, list[dict[str, Any]], list[tuple[int, int]]]:
    require(bool(edits), "no presentation texture edits were requested")
    indices_seen = [int(index) for index, _png in edits]
    require(len(indices_seen) == len(set(indices_seen)), "a presentation texture target repeats")
    edited = bytearray(resource.decoded)
    rows: list[dict[str, Any]] = []
    ranges: list[tuple[int, int]] = []
    for index, png in edits:
        contract = texture_contract(resource, int(index), pack_name=pack_name, pack_offset=pack_offset)
        pixel0, pixel1, palette0, palette1 = allocation(contract)
        before = bytes(edited[pixel0:pixel1]) + bytes(edited[palette0:palette1])
        indices, colours, expected, receipt = compile_texture(contract, png)
        edited[pixel0:pixel1] = indices
        edited[palette0:palette1] = colours
        back = decoded_mips(bytes(edited), contract)
        require(back == expected, f"{contract.texture_id}: decoded read-back differs from the compiled texture")
        ranges += [(pixel0, pixel1), (palette0, palette1)]
        after = indices + colours
        rows.append(dict(
            texture_index=int(index), selector=contract.texture_id, materials=list(contract.mapped_material_names),
            width=contract.width, height=contract.height, mip_levels=len(contract.mip_dimensions),
            descriptor_offset=contract.descriptor_offset, decoded_pixel_offset=pixel0, decoded_palette_offset=palette0,
            index_bytes=pixel1 - pixel0, allocation_bytes=(pixel1 - pixel0) + PALETTE_BYTES,
            retail_rgba_sha256=contract.rgba_sha256, retail_allocation_sha256=digest(before),
            applied_allocation_sha256=digest(after), changed_bytes=sum(a != b for a, b in zip(before, after)),
            **receipt))
    ordered = sorted(ranges)
    require(all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:])), "presentation texture allocations overlap")
    return bytes(edited), rows, ordered


def _outside(before: bytes, after: bytes, ranges: Sequence[tuple[int, int]]) -> bool:
    """True when every byte outside ``ranges`` is identical (the ranges are sorted and disjoint)."""

    cursor = 0
    for start, end in ranges:
        if before[cursor:start] != after[cursor:start]:
            return False
        cursor = end
    return before[cursor:] == after[cursor:]


def compile_raw(resource: SceneResource, edits: Sequence[tuple[int, Path | str]], *, pack_name: str = "",
                pack_offset: int = 0) -> tuple[bytes, dict[str, Any]]:
    """The raw MRKS transport adapter: new texture bytes at the same allocations, everything else kept."""

    require(resource.raw, f"{resource.kind} chunk {resource.record.chunk_index} is compressed; use compile_compressed")
    edited, rows, ranges = _apply(resource, edits, pack_name=pack_name, pack_offset=pack_offset)
    span = resource.span[:HEADER.size] + edited
    require(len(span) == len(resource.span) and span[:HEADER.size] == resource.span[:HEADER.size],
            "the raw MRKS wrapper or span size changed")
    require(edited[:resource.system_bytes] == resource.decoded[:resource.system_bytes],
            "the raw MRKS system buffer changed")
    require(_outside(resource.decoded, edited, ranges), "a raw MRKS edit escaped its texture allocations")
    again = open_resource(span, outer_index=resource.record.outer_index, outer_id=resource.record.outer_id,
                          outer_size=resource.record.outer_size, chunk_index=resource.record.chunk_index,
                          chunk_offset=resource.record.chunk_offset)
    require(again.scene["name"] == resource.scene["name"]
            and descriptor_summary(again) == descriptor_summary(resource),
            "the raw MRKS scene no longer parses to the same descriptors")
    return span, dict(
        scene=resource.scene["name"], kind=resource.kind, raw=True, span_size=len(span),
        stored_size=resource.record.stored_size, system_bytes=resource.system_bytes,
        video_bytes=resource.video_bytes, scratch_before=resource.scratch, scratch_after=resource.scratch,
        source_span_sha256=digest(resource.span), rebuilt_span_sha256=digest(span),
        decoded_after_sha256=digest(edited), wrapper_identical=True, system_bytes_identical=True,
        other_decoded_bytes_identical=True, textures=rows, archive_growth=0, rw_pool_growth=0,
        runtime_witnessed=False)


def compile_compressed(resource: SceneResource, edits: Sequence[tuple[int, Path | str]], *, pack_name: str = "",
                       pack_offset: int = 0) -> tuple[bytes, dict[str, Any]]:
    """A VC-LZ SCNE: stadium compile, then refit to the retail consumed length (wrapper, scratch, tail kept)."""

    require(not resource.raw and resource.kind == SCNE, "compile_compressed needs a compressed SCNE resource")
    edited, rows, ranges = _apply(resource, edits, pack_name=pack_name, pack_offset=pack_offset)
    stored, cap = resource.record.stored_size, resource.consumed
    _size, tag = struct.unpack_from("<II", resource.span, HEADER.size)
    bits = resource.span[HEADER.size + 8]
    attempts: list[dict[str, Any]] = []
    chosen = None
    for encoder in ("greedy", "optimal"):
        try:
            if encoder == "greedy":
                # the encoder _compile_resolved_scene runs for a changed scene, on the same decoded bytes
                stream = stadium._rebuild_vc_lz_fixed_span(
                    edited, resource.span[:HEADER.size], resource.opaque_tail, consumed_cap=cap,
                    scratch_cap=stadium.SCNE_OBSERVED_SCRATCH_MAX,
                    template_stream_prefix=resource.span[HEADER.size:HEADER.size + 9]).encoded
            else:
                # the optimal parse of the same token format packs tighter, which leaves the fill more matches
                # to spend as literals at the front of the stream, where the in-place decode needs its margin
                stream = compress_optimal(edited, stream_tag=tag, offset_bits=bits)
        except (stadium.StadiumTextureWriterError, ValueError) as exc:
            attempts.append(dict(encoder=encoder, error=str(exc)[:160]))
            continue
        if len(stream) > cap:
            attempts.append(dict(encoder=encoder, compressed=len(stream), error="longer than the retail stream"))
            continue
        encoded, expanded = fill_stream(stream, edited, cap, slack=0)
        minimum = minimum_vc_lz_overlap_scratch(encoded, stored, len(edited))
        attempts.append(dict(encoder=encoder, compressed=len(stream), filled=len(encoded), minimum_scratch=minimum))
        if len(encoded) <= cap and max(minimum, stored - len(encoded)) <= resource.scratch:
            chosen = (encoder, encoded, expanded, minimum)
            break
    require(chosen is not None, f"{resource.scene['name']}: the edit cannot keep the retail scratch word "
            f"(retail {resource.scratch}; tried {attempts})")
    encoder, encoded, expanded, minimum = chosen
    span = resource.span[:HEADER.size] + encoded + bytes(cap - len(encoded)) + resource.opaque_tail
    require(len(span) == len(resource.span) and span[:HEADER.size] == resource.span[:HEADER.size],
            "the SCNE wrapper, scratch word or span size changed")
    back, detail = decode_resource(span, resource.record)
    require(back == edited and int(detail["lz"]["consumed_bytes"]) == len(encoded),
            "the refit SCNE stream failed its independent decode")
    require(_outside(resource.decoded, back, ranges), "an SCNE edit escaped its texture allocations")
    again = open_resource(span, outer_index=resource.record.outer_index, outer_id=resource.record.outer_id,
                          outer_size=resource.record.outer_size, chunk_index=resource.record.chunk_index,
                          chunk_offset=resource.record.chunk_offset)
    require(again.scene["name"] == resource.scene["name"]
            and descriptor_summary(again) == descriptor_summary(resource) and again.consumed == len(encoded),
            "the refit SCNE no longer parses to the same descriptors")
    if resource.opaque_tail:
        require(span[-len(resource.opaque_tail):] == resource.opaque_tail, "the SCNE opaque tail changed")
    return span, dict(
        scene=resource.scene["name"], kind=resource.kind, raw=False, span_size=len(span), stored_size=stored,
        system_bytes=resource.system_bytes, video_bytes=resource.video_bytes, retail_consumed=cap,
        encoded_bytes=len(encoded), zero_gap_bytes=cap - len(encoded), matches_expanded=expanded, encoder=encoder,
        encoder_attempts=attempts,
        opaque_tail_size=len(resource.opaque_tail), opaque_tail_sha256=digest(resource.opaque_tail),
        scratch_before=resource.scratch, scratch_after=resource.scratch, minimum_scratch=minimum,
        source_span_sha256=digest(resource.span), rebuilt_span_sha256=digest(span),
        decoded_after_sha256=digest(back), wrapper_identical=True, other_decoded_bytes_identical=True,
        textures=rows, archive_growth=0, rw_pool_growth=0, runtime_witnessed=False)


def compile_resource(resource: SceneResource, edits: Sequence[tuple[int, Path | str]], *, pack_name: str = "",
                     pack_offset: int = 0) -> tuple[bytes, dict[str, Any]]:
    """Raw MRKS through the transport adapter, VC-LZ SCNE through the fixed-span refit."""

    compiler = compile_raw if resource.raw else compile_compressed
    return compiler(resource, edits, pack_name=pack_name, pack_offset=pack_offset)


def texture_rgba(resource: SceneResource, texture_index: int) -> tuple[int, int, bytes]:
    """(width, height, base-level RGBA) of one embedded descriptor (author-time and test helper)."""

    contract = texture_contract(resource, texture_index)
    return contract.width, contract.height, decoded_mips(resource.decoded, contract)[0]


def descriptor_summary(resource: SceneResource) -> list[Mapping[str, Any]]:
    """The descriptor rows of a resource in the catalog shape: offsets relative to the decoded resource."""

    out = []
    for texture in resource.textures:
        chain = sum(max(1, texture["width"] >> level) * max(1, texture["height"] >> level)
                    for level in range(texture["mip_levels"]))
        out.append(dict(index=texture["index"], materials=list(texture["mapped_material_names"]),
                        width=texture["width"], height=texture["height"], mip_levels=texture["mip_levels"],
                        format_name=texture["format_name"], descriptor_offset=texture["descriptor_offset"],
                        decoded_pixel_offset=resource.system_bytes + texture["pixel_offset"],
                        decoded_palette_offset=resource.system_bytes + texture["palette_offset"],
                        index_chain_bytes=chain,
                        contiguous=texture["palette_offset"] == texture["pixel_offset"] + chain))
    return out

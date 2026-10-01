"""Explicit standalone presentation inventory for GAMEDATA, with a graded, typed mark build.

The All Textures lane pins 11,395 standalone targets in a private report and never covered the 44
standalone TXTR chunks of ``gamedata.iff`` (outer 346, pack 0): the ESPN marks, the NFL chiclet, the
telestration rings, the replay and pass icons and the scorebug plate art. This module pins those 44
rows in ``data/nfl2k5_presentation_standalone.json`` (re-derivable byte for byte from a retail XISO
through its XDVDFS and archive directory, no retail payload kept), and offers an explicit extended
view: 11,439 targets catalogued, 11,437 format-supported (``espn1`` and ``nflShield1`` are DXT1 and
refused).

Only graded art is offered. ``espnLogo1``, ``shield_espn``, ``nfl_chiclet`` (grade A) and
``z_ESPN_bug`` (grade B) are the four marks authored from 2026 ESPN broadcast stills; every other row
is refused with its reason, the six C targets with the reasons the presentation research recorded.

A mark is compiled as a complete resource: the All Textures lane's ``build_replacement`` quantises,
swizzles and writes the palette into the retail decoded layout, then ``rebuild_fixed_span_filled``
refits the VC-LZ body inside the retail span so the 32-byte wrapper, scratch word +0x14 included,
stays byte-identical (the lane's zero-padded intermediate span is never the output). The 128-byte
system/descriptor region is kept, the decoded RGBA must equal the authored PNG, and nothing grows.
Retail spans are pinned by SHA-256 only. EXPERIMENTAL; appearance in game is UNWITNESSED.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_TOOLS = ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import nfl_all_texture_xiso_workflow as writer  # noqa: E402
from nfl_outer import HEADER_SIZE, ENTRY_SIZE, PACK_NAMES, parse_archive  # noqa: E402
from nfl_tset_png_import import decode_rgba_png  # noqa: E402
from nfl_txtr import HEADER, decode_chunk, parse_chunks, parse_texture, texture_to_rgba  # noqa: E402
import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402
from nfl_vc_lz_fill import rebuild_fixed_span_filled  # noqa: E402

SCHEMA = "nfl2k5_presentation_standalone/v1"
STANDALONE_PATH = ROOT / "data" / "nfl2k5_presentation_standalone.json"
STANDALONE_SHA256 = "69e6589ffbdda17fc3a5f3b9201ffc206bd0c347e54596b38a88cfeb1d454f36"
OUTER_INDEX = 346
OUTER_NAME = "gamedata.iff"
OUTER_NAME_ID = 0x00B6926C
PACK_PATH = "vc_53450030/0"
SHIPPED_TARGETS = 11_395
EXTENSION_TARGETS = 44
EXTENSION_FORMAT_SUPPORTED = 42

# Grades follow the espn_marks rules: A = authored from 2026 broadcast stills with the consumer
# geometry honoured, B = from 2026 stills with an inferred consumer, C = no 2026 source.
AUTHORED_GRADES = {
    "nfl_chiclet": "A",   # flat stinger shield, five-frame registered median (beta 76)
    "shield_espn": "A",   # red stinger wordmark in the retail two-row wrap (beta 76)
    "espnLogo1": "A",     # the 2026 scorebug wordmark, 1,523-frame median (beta 72)
    "z_ESPN_bug": "B",    # same wordmark; its consumer is untraced, the split is inferred (beta 72)
}
OFFERED_GRADES = ("A", "B")
REFUSED = {
    "telecircle1": "C: no 2026 telestration ring to copy; the 2026 telestrator draws yellow freehand strokes, "
                   "and a re-vectored retail ring is not a broadcast still",
    "telecircle2": "C: no 2026 telestration ring to copy; the 2026 telestrator draws yellow freehand strokes, "
                   "and a re-vectored retail ring is not a broadcast still",
    "passicons": "C: Xbox controller glyphs, not a broadcast mark; a 2026 broadcast has no controller art",
    "replayicons": "C: replay transport glyphs (pause, play, rewind, HIDE SAVE EXIT), not a broadcast mark",
    "endQTR_textures": "C: a UI primitive atlas whose consumer is untraced, and no end-of-quarter card appears "
                       "in the 2026 frames",
    "score_buga": "C: the retail scorebug plate atlas; its consumer UV rects are untraced here and the sprite "
                  "scorebug supersedes the retail bar",
}
DXT1_REASON = "DXT1: no fixed-span DXT encoder exists, so this texture has no write route"
UNGRADED_REASON = ("no graded broadcast-still art exists for this texture; only the four A/B graded ESPN "
                   "presentation marks are offered")


class PresentationMarkError(ValueError):
    """A presentation target, its pins or an authored mark failed closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PresentationMarkError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(document: object) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def asset_id(texture: str) -> str:
    return f"p8:{OUTER_INDEX}:{texture}"


# --- the retail disc, read only --------------------------------------------------------------------

class DiscArchive:
    """Read-only XDVDFS and outer-archive adapter over a retail XISO; never extracts a payload."""

    def __init__(self, image: Path | str):
        self.fd = os.open(image, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            self.image_size = os.fstat(self.fd).st_size
            self.files, _ = xiso.parse_xdvdfs(self.fd, self.image_size)
            offset, _ = xiso.pack_extent(self.fd, self.image_size, "0", entries=self.files)
            header = xiso.read_exact(self.fd, offset, HEADER_SIZE)
            count, reserved, pack_count = struct.unpack_from("<III", header)
            require(count == 4323 and not reserved and pack_count == 16, "retail archive directory drift")
            blocks = struct.unpack_from("<36I", header, 12)
            require(not any(blocks[pack_count:]), "unused pack slots changed")
            self.extents: dict[str, tuple[int, int]] = {}
            self.packs: list[tuple[str, int, int]] = []
            virtual = 0
            for index, block_count in enumerate(blocks[:pack_count]):
                name = PACK_NAMES[index]
                absolute, size = xiso.pack_extent(self.fd, self.image_size, name, entries=self.files)
                require(size == block_count * 2048, f"pack {name} size drift")
                self.extents[name] = (absolute, size)
                self.packs.append((name, virtual, size))
                virtual += size
            table = xiso.read_exact(self.fd, offset + HEADER_SIZE, count * ENTRY_SIZE)
            self.entries = tuple(struct.iter_unpack("<III", table))
            self.directory_sha256 = digest(header + table)
            self._hashes: dict[str, dict] = {}
        except BaseException:
            os.close(self.fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        os.close(self.fd)

    def location(self, outer: int, offset: int, size: int) -> tuple[str, int]:
        _name_id, outer_size, blocks = self.entries[outer]
        require(0 <= offset and size >= 1 and offset + size <= outer_size, "resource exceeds its outer allocation")
        absolute = blocks * 2048 + offset
        for name, start, length in self.packs:
            if start <= absolute and absolute + size <= start + length:
                return name, absolute - start
        raise PresentationMarkError("presentation resource crosses a pack boundary")

    def read(self, outer: int, offset: int, size: int) -> bytes:
        name, relative = self.location(outer, offset, size)
        return xiso.read_exact(self.fd, self.extents[name][0] + relative, size)

    def pack_identity(self, name: str) -> dict:
        if name not in self._hashes:
            absolute, size = self.extents[name]
            self._hashes[name] = dict(path=f"vc_53450030/{name}", retail_sector=absolute // 2048, size=size,
                                      sha256=xiso.sha256_fd(self.fd, absolute, size))
        return self._hashes[name]


def derive_standalone(disc: DiscArchive) -> dict:
    """The pinned inventory document, straight from the disc (every TXTR of outer 346)."""

    name_id, outer_size, _blocks = disc.entries[OUTER_INDEX]
    require(name_id == OUTER_NAME_ID, "outer 346 is not gamedata.iff")
    body = disc.read(OUTER_INDEX, 0, outer_size)
    rows = []
    for chunk in parse_chunks(body, allow_trailing=True):
        if chunk.kind != "TXTR":
            continue
        span = body[chunk.offset:chunk.end_offset]
        decoded, _ = decode_chunk(body, chunk)
        texture = parse_texture(decoded, chunk)
        pack, pack_offset = disc.location(OUTER_INDEX, chunk.offset, len(span))
        chain = sum(max(1, texture.width >> i) * max(1, texture.height >> i) for i in range(texture.mip_levels))
        grade = AUTHORED_GRADES.get(texture.name) or ("C" if texture.name in REFUSED else None)
        rows.append(dict(
            outer_index=OUTER_INDEX, outer_id=f"0x{name_id:08x}", outer_size=outer_size,
            chunk_index=chunk.index, chunk_offset=chunk.offset, pack_name=pack, pack_offset=pack_offset,
            span_size=len(span), span_sha256=digest(span), kind=chunk.kind, stored_size=chunk.stored_size,
            system_bytes=chunk.system_bytes, video_bytes=chunk.video_bytes,
            scratch_bytes=chunk.overlap_scratch_bytes, compressed=chunk.compressed,
            texture=texture.name, width=texture.width, height=texture.height, format_name=texture.format_name,
            mip_levels=texture.mip_levels, pixel_offset=texture.pixel_offset,
            palette_offset=texture.palette_offset, packed_format=texture.packed_format,
            packed_size=texture.packed_size, descriptor_offset=texture.descriptor_offset,
            descriptor_flags=texture.descriptor_flags, decoded_sha256=digest(decoded),
            asset_id=asset_id(texture.name), authored_grade=grade,
            replacement_supported=(texture.format_name == "P8" and texture.pixel_offset == 0
                                   and texture.palette_offset == chain and texture.packed_size == 0
                                   and chain + 1024 <= chunk.video_bytes)))
    packs = {name: disc.pack_identity(name) for name in sorted({row["pack_name"] for row in rows})}
    grades = Counter(row["authored_grade"] for row in rows if row["authored_grade"])
    return dict(schema=SCHEMA, archive_directory_sha256=disc.directory_sha256, packs=packs, targets=rows,
                summary=dict(target_count=len(rows),
                             editable_target_count=sum(row["replacement_supported"] for row in rows),
                             offered_target_count=sum(row["replacement_supported"]
                                                      and row["authored_grade"] in OFFERED_GRADES for row in rows),
                             format_counts=dict(sorted(Counter(row["format_name"] for row in rows).items())),
                             grade_counts=dict(sorted(grades.items()))))


# --- the pinned view -----------------------------------------------------------------------------------

_DOCUMENT: dict | None = None


def load_standalone(path: Path | str = STANDALONE_PATH) -> dict:
    """The pinned 44-row extension, fail-closed on any byte of drift."""

    global _DOCUMENT
    path = Path(path)
    if path == STANDALONE_PATH and _DOCUMENT is not None:
        return _DOCUMENT
    payload = path.read_bytes()
    require(digest(payload) == STANDALONE_SHA256, "presentation standalone content drift")
    document = json.loads(payload)
    require(document.get("schema") == SCHEMA, "presentation standalone schema drift")
    summary = document.get("summary") or {}
    require(summary.get("target_count") == EXTENSION_TARGETS == len(document.get("targets") or ())
            and summary.get("editable_target_count") == EXTENSION_FORMAT_SUPPORTED,
            "presentation standalone counts drift")
    if path == STANDALONE_PATH:
        _DOCUMENT = document
    return document


def rows_by_texture(document: dict | None = None) -> dict[str, dict]:
    document = document or load_standalone()
    return {row["texture"]: row for row in document["targets"]}


def refusal_reason(row: dict) -> str | None:
    """None when the row is offered for a write, else the reason it is refused."""

    if row["format_name"] == "DXT1":
        return DXT1_REASON
    if row["texture"] in REFUSED:
        return REFUSED[row["texture"]]
    if not row["replacement_supported"]:
        return "this texture's descriptor layout has no proved fixed-span write route"
    if row.get("authored_grade") not in OFFERED_GRADES or row["texture"] not in AUTHORED_GRADES:
        return UNGRADED_REASON
    return None


def offered_marks(document: dict | None = None) -> tuple[str, ...]:
    """The graded marks a build may write, in chunk order."""

    return tuple(row["texture"] for row in (document or load_standalone())["targets"] if refusal_reason(row) is None)


def is_presentation_asset(selector: object) -> bool:
    """True for a GAMEDATA row (``p8:346:<texture>``); the prefix test keeps other lanes off this file."""

    if not isinstance(selector, str) or not selector.startswith(f"p8:{OUTER_INDEX}:"):
        return False
    return selector in {row["asset_id"] for row in load_standalone()["targets"]}


def mark_record(row: dict, document: dict | None = None) -> dict[str, Any]:
    """One extension row in the All Textures proof-record shape, plus its grade and refusal."""

    pack = (document or load_standalone())["packs"][row["pack_name"]]
    reason = refusal_reason(row)
    return {
        "asset_id": row["asset_id"], "chunk_index": row["chunk_index"], "format": row["format_name"],
        "height": row["height"], "mip_levels": row["mip_levels"], "outer_index": row["outer_index"],
        "pack_offset": row["pack_offset"], "selector": row["asset_id"], "span_sha256": row["span_sha256"],
        "span_size": row["span_size"], "texture": row["texture"], "width": row["width"],
        "logical_span_sha256": row["span_sha256"], "logical_span_size": row["span_size"],
        "physical_span_count": 1, "physical_span_index": 0, "replacement_offset": 0,
        "xiso_absolute_span_offset": pack["retail_sector"] * 2048 + row["pack_offset"],
        "xiso_pack_path": pack["path"], "xiso_pack_sector": pack["retail_sector"],
        "xiso_pack_sha256": pack["sha256"], "xiso_pack_size": pack["size"],
        "group": "Presentation Marks (GAMEDATA)", "authored_grade": row.get("authored_grade"),
        "format_supported": bool(row["replacement_supported"]),
        "replacement_supported": reason is None, "refusal_reason": reason or "",
    }


def extension_records(document: dict | None = None) -> dict[str, dict[str, Any]]:
    document = document or load_standalone()
    return {row["asset_id"]: mark_record(row, document) for row in document["targets"]}


def extended_standalone_inventory(inventory_path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """The shipped 11,395 All Textures records plus the 44 GAMEDATA rows (11,439), keyed by asset id.

    The shipped rows keep the lane's own ``target_record`` shape; the extension rows carry the same keys
    plus ``authored_grade``, ``format_supported`` and a grade-gated ``replacement_supported``.
    """

    from . import nfl2k5_p8_texture_writer as p8
    shipped = p8.load_inventory(Path(inventory_path) if inventory_path is not None else p8.DEFAULT_REPORT)
    view = {key: p8.target_record(value) for key, value in shipped.items()}
    for key, record in extension_records().items():
        require(key not in view, "presentation inventory overlaps the shipped inventory")
        view[key] = record
    require(len(view) == SHIPPED_TARGETS + EXTENSION_TARGETS, "extended inventory count drift")
    return view


def require_offered(texture: str, document: dict | None = None) -> dict:
    """The pinned row of an offered mark; refused names raise their reason."""

    rows = rows_by_texture(document)
    row = rows.get(texture)
    require(row is not None, f"{texture!r} is not a GAMEDATA presentation target")
    reason = refusal_reason(row)
    require(reason is None, f"{texture} is refused: {reason}")
    return row


# --- one complete resource -----------------------------------------------------------------------------

def resolve_span(span: bytes, row: dict) -> "writer.ResolvedTarget":
    """The lane's resolved target for one complete retail span (wrapper + stored body), fail-closed."""

    span = bytes(span)
    require(len(span) == row["span_size"] and digest(span) == row["span_sha256"],
            f"{row['texture']}: the span is not the pinned retail resource")
    chunks = parse_chunks(span, allow_trailing=True)
    require(len(chunks) == 1 and chunks[0].kind == "TXTR", f"{row['texture']}: not one TXTR resource")
    chunk = replace(chunks[0], index=row["chunk_index"], offset=0)
    decoded, _ = decode_chunk(span, chunk)
    info = parse_texture(decoded, chunk)
    chain = sum(max(1, info.width >> i) * max(1, info.height >> i) for i in range(info.mip_levels))
    require(info.name == row["texture"] and info.format_name == "P8" and info.pixel_offset == 0
            and info.packed_size == 0 and info.palette_offset == chain
            and info.palette_offset + writer.PALETTE_BYTES <= chunk.video_bytes
            and (info.width, info.height, info.mip_levels) == (row["width"], row["height"], row["mip_levels"]),
            f"{row['texture']}: retail texture layout changed")
    piece = writer.PhysicalSpan(pack_name=row["pack_name"], pack_relative_offset=row["pack_offset"],
                                replacement_offset=0, size=len(span), span_sha256=digest(span))
    return writer.ResolvedTarget(
        pack_name=row["pack_name"], outer_index=row["outer_index"], chunk_index=row["chunk_index"],
        texture=info.name, width=info.width, height=info.height, mip_levels=info.mip_levels,
        format_name=info.format_name, packed_size=info.packed_size, pixel_chain_bytes=chain,
        pixel_offset=info.pixel_offset, palette_offset=info.palette_offset, system_bytes=chunk.system_bytes,
        video_bytes=chunk.video_bytes, pack_relative_offset=row["pack_offset"], span_size=len(span),
        span_sha256=digest(span), decoded=decoded, template_span=span, chunk=chunk, physical_spans=(piece,))


def compile_mark(target: "writer.ResolvedTarget", png: Path | str, row: dict) -> tuple[bytes, dict[str, Any]]:
    """Authored PNG -> complete replacement span with the retail wrapper and scratch word kept."""

    png = Path(png)
    require(png.is_file() and not png.is_symlink(), f"{row['texture']}: the authored mark must be a regular PNG")
    require(target.span_sha256 == row["span_sha256"] and target.chunk_index == row["chunk_index"],
            f"{row['texture']}: the resolved span is not the pinned retail target")
    try:
        candidate, lane = writer.build_replacement(target, png)
    except (writer.TextureWorkflowError, ValueError) as exc:
        raise PresentationMarkError(f"{row['texture']}: {exc}") from exc
    chunk = replace(target.chunk, offset=0)
    decoded, _ = decode_chunk(candidate, chunk)
    try:
        rebuilt, fill = rebuild_fixed_span_filled(target.template_span, decoded, encoder="auto")
    except ValueError as exc:
        raise PresentationMarkError(f"{row['texture']}: {exc}") from exc
    back, _ = decode_chunk(rebuilt, chunk)
    rgba = texture_to_rgba(back, chunk, parse_texture(back, chunk))
    _w, _h, authored = decode_rgba_png(png.read_bytes(), (row["width"], row["height"]))
    require(rgba == authored, f"{row['texture']}: read-back RGBA differs from the authored PNG")
    require(back == decoded and back[:target.system_bytes] == target.decoded[:target.system_bytes],
            f"{row['texture']}: descriptor or decoded round trip drift")
    require(len(rebuilt) == len(target.template_span) and rebuilt[:HEADER.size] == target.template_span[:HEADER.size]
            and fill.wrapper_identical and fill.exact_minimum_scratch <= fill.scratch_bytes,
            f"{row['texture']}: wrapper, scratch word or fixed span drift")
    return rebuilt, dict(
        texture=row["texture"], grade=row.get("authored_grade"), chunk_index=row["chunk_index"],
        chunk_offset=row["chunk_offset"], pack_offset=row["pack_offset"], span_size=len(rebuilt),
        source_span_sha256=target.span_sha256, rebuilt_span_sha256=digest(rebuilt), rgba_sha256=digest(rgba),
        png_sha256=lane.get("png_sha256"), palette_entries=lane.get("palette_entries"), fill=asdict(fill),
        authored_rgba_identical=True, wrapper_identical=True, system_bytes_identical=True,
        archive_growth=0, gamedata_growth=0, rw_pool_growth=0, runtime_witnessed=False)


def build_unified_presentation_mark_imports(
    index: Path | str, selector: str, png: Path | str,
) -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]]:
    """The typed-build adapter: the same staged-edit shape as ``build_unified_p8_texture_imports``."""

    document = load_standalone()
    rows = {row["asset_id"]: row for row in document["targets"]}
    row = rows.get(str(selector))
    require(row is not None, f"{selector} is not a GAMEDATA presentation target")
    reason = refusal_reason(row)
    require(reason is None, f"{row['texture']} is refused: {reason}")
    archive = parse_archive(Path(index))
    try:
        resolved = writer.resolve_target(archive, OUTER_INDEX, row["texture"])
    except writer.TextureWorkflowError as exc:
        raise PresentationMarkError(str(exc)) from exc
    require(resolved.span_sha256 == row["span_sha256"] and resolved.chunk_index == row["chunk_index"]
            and len(resolved.physical_spans) == 1
            and resolved.physical_spans[0].pack_name == row["pack_name"]
            and resolved.physical_spans[0].pack_relative_offset == row["pack_offset"],
            f"retail span for {selector} differs from the pinned GAMEDATA inventory")
    rebuilt, receipt = compile_mark(resolved, png, row)
    require(rebuilt != resolved.template_span, f"replacement equals retail for {selector}")
    proof = mark_record(row, document)
    proof["logical_replacement_sha256"] = digest(rebuilt)
    record = {
        "schema": "nfl2k5_presentation_mark_import/v1", "asset_id": row["asset_id"],
        "label": f"{row['texture']} (GAMEDATA presentation mark, grade {row['authored_grade']})",
        "group": proof["group"], "logical_replacement_sha256": digest(rebuilt),
        "replacement_sha256": digest(rebuilt), "target": proof,
        **{key: value for key, value in receipt.items() if key != "rebuilt_span_sha256"},
    }
    return [(rebuilt, [], record, str(proof["selector"]), proof)]


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_presentation_standalone",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("derive", help="re-derive the pinned inventory from a retail XISO")
    d.add_argument("disc", type=Path)
    d.add_argument("--output", type=Path, required=True)
    sub.add_parser("offered", help="list the offered marks and the refused rows with their reasons")
    args = parser.parse_args(argv)
    if args.command == "derive":
        with DiscArchive(args.disc) as disc:
            document = derive_standalone(disc)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(canonical(document))
        print(json.dumps(dict(summary=document["summary"], sha256=digest(canonical(document)))))
        return 0
    for row in load_standalone()["targets"]:
        reason = refusal_reason(row)
        print(f"{row['asset_id']:28s} {row['format_name']:5s} {row.get('authored_grade') or '-':2s} "
              f"{'OFFERED' if reason is None else 'refused: ' + reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

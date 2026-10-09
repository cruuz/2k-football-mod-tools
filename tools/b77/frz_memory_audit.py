#!/usr/bin/env python3
"""Read-only shipped-kit memory census using the mapped NFL 2K5 decoder.

Package totals are resource requirements, not a captured live heap. Native
decoder checks execute bounded CPU routines with an allocation fixture.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from nfl2k5_playbook_position_recode import OuterImage
from nfl_uniform_inventory import logical_name_candidates, parse_tset
from nfl_scene_probe import ResourceRecord
from nfl_txtr import decode_chunk, minimum_vc_lz_overlap_scratch, parse_chunks, parse_texture
from mod_editor.core import nfl2k5_roster_records as rr
from tools.b77.frz_transition import V05, V06, TextureMachine


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, document):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, separators=(",", ":"))
        stream.write("\n")


def union_size(ranges):
    """Count distinct bytes, including aliased clean/mud mip chains only once."""
    end = total = 0
    for start, stop in sorted(ranges):
        if start < 0 or stop < start:
            raise ValueError("invalid video range")
        total += max(0, stop - max(start, end))
        end = max(end, stop)
    return total


def texture_ranges(texture, video_bytes):
    """Validate all declared mip levels and the full 256-entry palette."""
    levels = []
    offset = texture["pixel_offset"]
    width, height = texture["width"], texture["height"]
    count, fmt = texture["mip_levels"], texture["format_code"]
    if not 1 <= count <= 1 + max(width, height).bit_length() - 1:
        raise ValueError("invalid mip count")
    for level in range(count):
        w, h = max(1, width >> level), max(1, height >> level)
        if fmt in (0x0B, 0x7F, 0, 1):
            size = w * h
        elif fmt in (6, 7):
            size = w * h * 4
        elif fmt in (2, 3, 4, 5):
            size = w * h * 2
        elif fmt in (0x0C, 0x0E, 0x0F):
            size = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fmt == 0x0C else 16)
        else:
            raise ValueError(f"unsupported texture format {fmt:#x}")
        levels.append(dict(level=level, width=w, height=h, offset=offset, bytes=size))
        offset += size
    if offset > video_bytes:
        raise ValueError("mip chain exceeds wrapper video allocation")
    palette = texture["palette_offset"]
    palette_range = None
    if fmt in (0x0B, 0x7F):
        if palette < 0 or palette + 1024 > video_bytes:
            raise ValueError("palette exceeds wrapper video allocation")
        palette_range = (palette, palette + 1024)
    return levels, (texture["pixel_offset"], offset), palette_range


def describe_chunk(raw, chunk, entry, logical, machine):
    decoded, transport = decode_chunk(raw, chunk)
    span = raw[chunk.offset:chunk.end_offset]
    row = dict(kind=chunk.kind, stored=chunk.stored_size, system=chunk.system_bytes,
               video=chunk.video_bytes, scratch=chunk.overlap_scratch_bytes,
               compressed=chunk.compressed, span_sha256=sha(span), decoded_sha256=sha(decoded),
               reserved=[chunk.reserved0, chunk.reserved1], errors=[], textures=[])
    if chunk.compressed:
        minimum = minimum_vc_lz_overlap_scratch(span[32:32+transport.consumed_bytes],
                                                chunk.stored_size, chunk.output_size)
        row.update(consumed=transport.consumed_bytes, offset_bits=transport.offset_bits,
                   exact_minimum_scratch=minimum, scratch_margin=chunk.overlap_scratch_bytes-minimum,
                   output=chunk.output_size, load_request=chunk.output_size+chunk.overlap_scratch_bytes)
        if minimum > chunk.overlap_scratch_bytes:
            row["errors"].append("scratch below exact in-place minimum")
        if chunk.output_size + chunk.overlap_scratch_bytes < chunk.stored_size:
            row["errors"].append("tail read begins before allocation")
        if machine and not row["errors"]:
            machine.check(span, chunk, decoded)
            row["native_decoder_guarded"] = True
    else:
        # Raw Unif and NAME use +4 stored bytes, their +8/+c are zero.
        row.update(output=len(decoded), load_request=len(decoded), exact_minimum_scratch=0,
                   scratch_margin=0)
    if chunk.kind == "TSET":
        record = ResourceRecord(entry.index, hex(entry.name_id), entry.size, chunk.index,
                                chunk.offset, chunk.kind, chunk.stored_size, chunk.system_bytes,
                                chunk.video_bytes, chunk.compression_magic, chunk.overlap_scratch_bytes)
        _, textures, _ = parse_tset(decoded, record, logical, None)
        row["textures"] = textures
    elif chunk.kind == "TXTR":
        row["textures"] = [asdict(parse_texture(decoded, chunk))]
    chains, palettes = [], []
    for texture in row["textures"]:
        levels, chain, palette = texture_ranges(texture, chunk.video_bytes)
        texture["levels"] = levels
        texture["chain_bytes"] = chain[1]-chain[0]
        chains.append(chain)
        if palette:
            palettes.append(palette)
        if texture["format_code"] in (0x0B, 0x7F):
            palette_data = decoded[chunk.system_bytes+palette[0]:chunk.system_bytes+palette[1]]
            texture["distinct_palette_colors"] = len(set(struct.iter_unpack("<I", palette_data)))
            texture["used_base_palette_indices"] = len(set(decoded[chunk.system_bytes+chain[0]:
                chunk.system_bytes+chain[0]+texture["width"]*texture["height"]]))
    row.update(chain_count=len(set(chains)), chain_bytes=union_size(chains),
               palette_count=len(set(palettes)), palette_bytes=union_size(palettes),
               video_padding=chunk.video_bytes-union_size(chains+palettes))
    if union_size(chains+palettes) != union_size(chains)+union_size(palettes):
        row["errors"].append("pixel chain overlaps palette")
    return row


def package_totals(chunks, live_only=False):
    rows = [r for r in chunks if not live_only or r["index"] <= 48]
    output = sum(r["output"] for r in rows)
    return dict(system=sum(r["system"] if r["kind"] in ("TSET", "TXTR") else r["output"] for r in rows),
                video=sum(r["video"] for r in rows), decoded=output,
                scratch=sum(r["scratch"] if r["compressed"] else 0 for r in rows),
                all_requests=sum(r["load_request"] for r in rows),
                decoded_plus_largest_scratch=output+max((r["scratch"] for r in rows), default=0),
                chain_bytes=sum(r["chain_bytes"] for r in rows),
                palette_count=sum(r["palette_count"] for r in rows),
                palette_bytes=sum(r["palette_bytes"] for r in rows),
                texture_count=sum(len(r["textures"]) for r in rows))


def census(out, native):
    out.mkdir(parents=True, exist_ok=True)
    cache = {}
    start = time.monotonic()
    names = logical_name_candidates()
    summary = dict(schema="frz2-kit-memory-v1", packages={}, unique_decoded=0,
                   native=native, faults=[], elapsed_seconds=0)
    for label, path in (("v05", V05), ("v06", V06)):
        # The extracted executables are pinned by the caller's bounded read receipt.
        machine = TextureMachine((out/(label+".xbe")).read_bytes()) if native else None
        native_seen = set()
        rows = []
        with OuterImage(path) as image:
            roster = rr.load_body(image.read_entry(5)[32:], scheme="one_pool")
            teams = {t.asset_id: t.abbreviation for t in roster.teams}
            for entry in image.entries:
                logical = names.get(entry.name_id)
                if logical is None:
                    continue
                raw = image.read_entry(entry.index)
                package = dict(package=logical.name, team=teams.get(int(logical.asset_code),logical.asset_code),
                               outer=entry.index, file_size=len(raw), sha256=sha(raw), chunks=[])
                try:
                    chunks = parse_chunks(raw, allow_trailing=True)
                    if len(chunks) != 53:
                        raise ValueError(f"expected 53 kit chunks, found {len(chunks)}")
                    package["tail_bytes"] = len(raw)-chunks[-1].end_offset
                    package["nonzero_tail_bytes"] = sum(v != 0 for v in raw[chunks[-1].end_offset:])
                    for c in chunks:
                        span = raw[c.offset:c.end_offset]
                        key = (c.index, sha(span))
                        if key not in cache:
                            cache[key] = describe_chunk(raw, c, entry, logical, machine)
                            if c.compressed and machine:
                                native_seen.add(key)
                        elif native and c.compressed and key not in native_seen:
                            decoded, _ = decode_chunk(raw, c)
                            machine.check(span, c, decoded)
                            native_seen.add(key)
                        record = dict(cache[key], index=c.index, offset=c.offset,
                                      image_offset=image.image_offset(entry.virtual_offset+c.offset))
                        package["chunks"].append(record)
                        for error in record["errors"]:
                            summary["faults"].append(dict(version=label, package=logical.name,
                                chunk=c.index, error=error))
                    package["total"] = package_totals(package["chunks"])
                    package["live_through_bump_sock"] = package_totals(package["chunks"], True)
                except Exception as exc:
                    summary["faults"].append(dict(version=label, package=logical.name, error=str(exc)))
                    package["error"] = str(exc)
                rows.append(package)
                if len(rows) % 20 == 0:
                    print(label, len(rows), "kits", len(cache), "unique inputs", round(time.monotonic()-start,1), "s", flush=True)
        summary["packages"][label] = rows
        summary[label+"_native_unique"] = len(native_seen)
        save(out/(label+"-census.json"), rows)
        print(label, len(rows), "complete", len(native_seen), "native", flush=True)
    summary["unique_decoded"] = len(cache)
    summary["elapsed_seconds"] = time.monotonic()-start
    save(out/"census.json", summary)
    print("faults", len(summary["faults"]), "elapsed", round(summary["elapsed_seconds"],1), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--native", action="store_true")
    args = parser.parse_args()
    census(args.out, args.native)

#!/usr/bin/env python3
"""Read-only retail proof; all art/windows live in a disposable directory.

The only persistent output is a JSON receipt with hashes and measured errors.
No game image or archive pack is copied or loaded whole.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.nfl2k5_digit_texture import make_digit_mips
from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
from nfl_outer import parse_archive, read_entry_bytes, read_entry_range
from nfl_txtr import decode_chunk, encode_rgba_png, parse_chunks
from nfl2k5_visual_mod_project import write_all


def design(width, height):
    """Original block stripe/sole design, aligned to sixteen-pixel footprints."""
    return b"".join(bytes(
        (240, 0, 200, 0) if x < 16 or y < 16 else
        (245, 245, 240, 255) if width * 3 // 8 <= x < width // 2 or y >= height - 32 else
        (10, 180, 160, 255) if x < width // 2 else (25, 35, 65, 255)
    ) for y in range(height) for x in range(width))


def prove(index, *, set_selector="28H0", texture_name="shoes01", scale=4):
    by_id, groups = writer.load_targets()
    target = next(row for row in by_id.values()
                  if row.set_selector == set_selector and row.name == texture_name)
    archive = parse_archive(index)
    entry = archive.entries[target.outer_index]
    assert entry.size <= writer.MAX_PACKAGE_BYTES
    package = read_entry_bytes(archive, entry)
    chunk = next(c for c in parse_chunks(package, allow_trailing=True) if c.index == target.chunk_index)
    assert chunk.output_size <= writer.MAX_DECODED_BYTES
    before_span = package[chunk.offset:chunk.end_offset]
    before, _ = decode_chunk(package, chunk)
    rows = groups[(target.outer_index, target.chunk_index)]
    textures, _ = writer._validate_layout(before, chunk, rows)
    rgba = design(target.width, target.height)
    png = with_import_mode(encode_rgba_png(target.width, target.height, rgba),
                           target.asset_id, rgba, independent=True, scale=scale)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory(prefix="equipment-retail-proof-") as directory:
        root = Path(directory).resolve()
        path = root / "new-cleat.png"
        path.write_bytes(png)
        built = writer.build_unified_uniform_equipment_imports(index, [(target.asset_id, path)])
        after_span, _previews, receipt, _selector, record = built
        report = receipt["edits"][0]
        assert report["import_mode"] == "independent-mip-chain"
        chunk_after = replace(parse_chunks(after_span)[0], index=target.chunk_index)
        after, _ = decode_chunk(after_span, chunk_after)
        actual = writer.decode_equipment_levels(after, chunk_after, replace(
            textures[target.reference_index], pixel_offset=report["pixel_offset"],
            width=report["encoded_dimensions"][0], height=report["encoded_dimensions"][1],
            mip_levels=report["mip_levels"],
        ))
        expected = make_digit_mips(rgba, target.width, target.height, target.mip_levels)
        expected[0] = replace(expected[0], rgba=rgba)
        expected = expected[scale.bit_length() - 1:]
        assert actual == [level.rgba for level in expected], "This proof requires exact colours and coverage"
        changed_base = sum(a != b for a, b in zip(
            writer.decode_equipment_levels(before, chunk, textures[target.reference_index])[scale.bit_length() - 1], actual[0]))
        assert changed_base
        sibling_hashes = []
        for row in rows:
            if row.reference_index == target.reference_index:
                continue
            original = writer.decode_equipment_levels(before, chunk, textures[row.reference_index])
            rebuilt = writer.decode_equipment_levels(after, chunk_after, textures[row.reference_index])
            assert original == rebuilt
            sibling_hashes.append({"asset_id": row.asset_id, "all_level_rgba_sha256": list(map(sha, rebuilt))})
        # Use the production exact-offset writer on a small actual source
        # window, close it, reopen it, and independently decode every saved mip.
        window = root / "bounded-source-window.bin"
        prefix = package[chunk.offset - 32:chunk.offset]
        suffix = package[chunk.end_offset:chunk.end_offset + 32]
        assert len(prefix) == len(suffix) == 32
        window.write_bytes(prefix + before_span + suffix)
        result, application = writer.apply_equipment_span(before_span, after_span, receipt)
        descriptor = os.open(window, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            write_all(descriptor, len(prefix), result)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        reopened = window.read_bytes()
        assert reopened[:32] == prefix and reopened[-32:] == suffix
        stored = reopened[32:-32]
        decoded, _ = decode_chunk(stored, parse_chunks(stored)[0])
        assert decoded == after
        replay, replay_receipt = writer.apply_equipment_span(stored, after_span, receipt)
        assert replay == stored and not replay_receipt["changed"]
        # No persistent receipt may point at temporary or private art files.
        for row in receipt["input_pngs"]:
            row.pop("path", None)
        outcome = {
            "schema": "nfl2k5_equipment_chain_retail_proof/v1",
            "experimental_unwitnessed": True,
            "complete_import_receipt": receipt,
            "retail_span_sha256": sha(before_span), "replacement_span_sha256": sha(after_span),
            "authored_png_sha256": sha(png), "changed_base_channel_count": changed_base,
            "every_encoded_level_matches_direct_coverage_exactly": True,
            "all_sibling_levels": sibling_hashes, "application": application, "replay": replay_receipt,
            "window_bytes": len(reopened), "guard_bytes_each_side": 32,
            "closed_reopened_and_independently_decoded": True,
        }
    assert sha(read_entry_range(archive, entry, chunk.offset, len(before_span))) == sha(before_span)
    outcome["source_span_unchanged"] = True
    outcome["all_disposable_art_and_window_files_deleted"] = not root.exists()
    return outcome


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--set", default="28H0", dest="set_selector")
    parser.add_argument("--texture", default="shoes01")
    parser.add_argument("--scale", type=int, choices=(1, 2, 4), default=4)
    args = parser.parse_args()
    receipt = prove(args.index, set_selector=args.set_selector, texture_name=args.texture, scale=args.scale)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"target": receipt["complete_import_receipt"]["edits"][0]["asset_id"],
                      "allocation": receipt["complete_import_receipt"]["allocation"],
                      "fit": receipt["complete_import_receipt"]["bounded_palette_fit"],
                      "all_levels_exact": receipt["every_encoded_level_matches_direct_coverage_exactly"]}, indent=2))

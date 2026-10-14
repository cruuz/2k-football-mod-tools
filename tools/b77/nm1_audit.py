#!/usr/bin/env python3
"""Read-only indicator-code and existing scorebug-glyph audit. Never repairs a disc."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import string
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import xdvdfs_compact as xd
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_scorebug_sprite import load_layout

RANGES = (
    ("indicator_predicate", 0x75D40, 0x50),
    ("indicator_collection", 0x75D90, 0x6ED),
    ("option_default_store", 0x77C84, 10),
    ("name_number_draw", 0xF9D00, 0xCF),
    ("indicator_font_setup", 0xF9F40, 0x152),
    ("indicator_submission", 0xFA0B0, 0x1B2),
    ("indicator_projection", 0xFA270, 0x186),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_xbe(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as stream:
        entry = xd.read_layout(stream).entries["default.xbe"]
        stream.seek(entry.byte_offset)
        raw = stream.read(entry.size)
    if len(raw) != entry.size:
        raise ValueError("truncated default.xbe")
    return raw


def utf16_string(image, va):
    units = []
    for i in range(128):
        unit = image.read(va + 2 * i, 2)
        if unit == b"\0\0":
            return b"".join(units).decode("utf-16le")
        units.append(unit)
    raise ValueError("unterminated option label")


def can_spell(word, tokens):
    """Whole registered tiles only. A tile such as GOAL is not four glyphs."""
    reached = {0}
    for i in range(len(word)):
        if i in reached:
            reached.update(i + len(t) for t in tokens if t and word.startswith(t, i))
    return len(word) in reached


def font_report(spec, image):
    # The scoreboard's text faces only. T in timeout_tab means an entire
    # TIMEOUT panel, and must never be reported as a standalone letter T.
    sets = {k: spec["glyph_sets"][k] for k in ("score", "clock", "small", "label", "quarter", "record")}
    tokens = {t for gs in sets.values() for t in gs["glyphs"] if t not in ("ESPN", "~")}
    letters = set("".join(tokens).upper()) & set(string.ascii_uppercase)
    return dict(
        source_sheet_size=list(image.size), compiled_atlas_size=spec["atlas"],
        source_sha256=sha(image.tobytes()),
        standalone_uppercase="".join(c for c in string.ascii_uppercase if c in tokens),
        absent_even_if_text_tiles_split="".join(c for c in string.ascii_uppercase if c not in letters),
        tile_segmentation_proven=False,
        samples={w: can_spell(w, tokens) for w in ("WILLIAMS", "ELLIOTT", "SLYE", "WARD", "JONES", "DIKE", "LAWRENCE", "TESLAA", "Inches")},
        cells={k: {t: dict(cell=g["cell"], box=spec["cells"][g["cell"]]["box"])
                   for t, g in gs["glyphs"].items()} for k, gs in sets.items()},
        provenance=spec.get("provenance", {}),
    )


def audit(discs, folder=None):
    raw = {name: read_xbe(path) for name, path in discs.items()}
    images = {name: XbeImage(data) for name, data in raw.items()}
    rows = []
    for name, va, size in RANGES:
        blocks = {k: im.read(va, size) for k, im in images.items()}
        rows.append(dict(name=name, va=hex(va), size=size,
                         sha256={k: sha(b) for k, b in blocks.items()},
                         changed_vs_retail={k: sum(a != b for a, b in zip(blocks["retail"], block))
                                            for k, block in blocks.items()}))
    options = {}
    for k, im in images.items():
        store = im.read(0x77C84, 10)
        if store[:6] != bytes.fromhex("c70590ffe500"):
            raise ValueError(f"{k}: unrecognized option initializer")
        labels = [utf16_string(im, p) for p in struct.unpack("<3I", im.read(0x4ED950, 12))]
        value = struct.unpack_from("<I", store, 6)[0]
        options[k] = dict(labels=labels, builtin_default=value,
                          builtin_default_label=labels[value] if value < len(labels) else "unknown",
                          saved_setting_observed=False)
    spec, image = load_layout(folder)
    return dict(schema="b773/nm1-audit/v1", xbe_sha256={k: sha(b) for k, b in raw.items()},
                ranges=rows, options=options, font=font_report(spec, image),
                disc_bytes_written=0, live_capture=False, root_cause_established=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("retail", "public", "base"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = audit({k: getattr(args, k) for k in ("retail", "public", "base")}, args.folder)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    for row in receipt["ranges"]:
        d = row["changed_vs_retail"]
        print(f'{row["name"]} {row["va"]} size={row["size"]}: public_diff={d["public"]} base_diff={d["base"]}')
    for name, row in receipt["options"].items():
        print(f'{name}: choices={row["labels"]!r}; built-in default={row["builtin_default_label"]}')
    font = receipt["font"]
    print("standalone uppercase text glyphs:", repr(font["standalone_uppercase"]))
    print("letters absent even if text tiles split:", font["absent_even_if_text_tiles_split"])
    print("whole-tile samples:", json.dumps(font["samples"]))
    print("disc_bytes_written=0 live_capture=false root_cause_established=false")


if __name__ == "__main__":
    main()

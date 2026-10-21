#!/usr/bin/env python3
"""v0.6.1 Team Needs and Unc Bowl repair, with only owned byte ranges pinned.

  v1g_repair.py --input DISC.xiso.iso --output OUT/vc_53450030 --receipt OUT/receipt.json
  v1g_repair.py --input OUT/vc_53450030 --xbe default.before.xbe \
      --output REPLAY/vc_53450030 --receipt REPLAY/receipt.json

Writes copies of vc_53450030/0, A and B. No XBE or roster changes. Never
opens the input writable. Foreign owned spans and partial repairs refuse.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77"), str(ROOT / "tools/b765")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump
from mod_editor.core import nfl2k5_position_pools as pools
from mod_editor.core import nfl2k5_unc_bowl_uniforms as uniforms
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from nfl_txtr import parse_chunks
from nfl_outer import PACK_NAMES
import u3s_repair as scoped

sha, require = uniforms.sha, uniforms.require


def read_binary(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        return stream.read()


def xbe_check(raw):
    require(pools.status(raw) == "applied", "Team Needs requires the applied modern position pools")
    xbe = XbeImage(raw)
    import struct
    maxima = struct.unpack("<17I", xbe.read(pools.ROSTER_MAXIMA_VA, 68))
    targets = struct.unpack("<17I", xbe.read(pools.ROSTER_TARGETS_VA, 68))
    require([(maxima[i], targets[i]) for i in (10, 11, 15, 16)] == [(0, 0), (7, 5), (6, 4), (6, 4)],
            "unexpected modern Team Needs targets")
    return dict(sha256=sha(raw), changed=False, edge_target=5, lb_target=6, dt_target=5)


def compile_patches(image):
    index = bump._parsed_index(image)
    by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
    read = lambda entry: image.read_segments(index.sub_extents(entry, 0, entry.size))
    require(index.entries[9].name_id == 3649596148, "Team Needs resource identity differs")
    require(index.entries[22].name_id == 0x3F407CF4 and uniforms.unc_bowl_uses_slots(read(index.entries[22])),
            "the Unc Bowl does not select 22A4 and 06H5")
    kit_inputs = {name: read(by_name[name]) for name in uniforms.OWNED}
    specs = {name: uniforms.validate_owned(name, raw) for name, raw in kit_inputs.items()}
    ui = read(index.entries[9])
    chunk = parse_chunks(ui)[7]
    scene, ui_receipt = pools.apply_team_needs_scene(ui[chunk.offset:chunk.end_offset])
    fixed = {"06H5.IFF": uniforms.finish_cincinnati(kit_inputs["06H5.IFF"]),
             "22A4.IFF": uniforms.finish_pittsburgh(kit_inputs["22A4.IFF"], read(by_name["22H0.IFF"]))}
    groups = {}

    def add(entry, resource, patch, data):
        pieces = index.sub_extents(entry, patch["offset"], patch["length"])
        require(len(pieces) == 1, "owned span crosses a pack")
        ordinal, at, length = pieces[0]
        require(length == len(data) == patch["length"], "owned span size differs")
        groups.setdefault(ordinal, []).append(dict(patch, offset=at, resource=resource,
            resource_offset=patch["offset"], data=data))

    for name, data in fixed.items():
        for patch in specs[name]["spans"]:
            at, n = patch["offset"], patch["length"]
            require(sha(data[at:at + n]) == patch["after_sha256"], "compiled uniform differs from output pin")
            add(by_name[name], name, patch, data[at:at + n])
        require((uniforms.finish_cincinnati(data) if name == "06H5.IFF" else
                 uniforms.finish_pittsburgh(data, read(by_name["22H0.IFF"]))) == data,
                "uniform compiler is not idempotent")
    for edit in ui_receipt["edits"]:
        at, n = edit["offset"], edit["length"]
        add(index.entries[9], "outer:9/team_needs", dict(edit, offset=chunk.offset + at), scene[at:at + n])
    require(set(groups) == {0, 10, 11}, "unexpected output disc files")
    return groups


def repair(source, output, xbe_path=None):
    io = scoped._b765()
    io.refuse_links(source)
    io.refuse_links(output)
    require(source.resolve() != output.resolve() and not
            (source.is_dir() and output.resolve().is_relative_to(source.resolve())), "unsafe output path")
    pending, receipts = [], {}
    with bump._Image.open(source, writable=False) as image:
        if image.kind == "xiso":
            entry = image._xiso_entries["default.xbe"]
            xbe = os.pread(image._descriptor, entry.size, entry.byte_offset)
        else:
            require(xbe_path is not None, "an extracted input requires --xbe")
            io.refuse_links(xbe_path)
            xbe = read_binary(xbe_path)
        executable = xbe_check(xbe)
        groups = compile_patches(image)
        for ordinal, patches in sorted(groups.items()):
            original = image.read_pack(ordinal, 0, image.pack_size(ordinal))
            data, receipt = scoped.apply_patches(original, patches)
            require(scoped.apply_patches(data, patches)[0] == data, "native repair replay differs")
            name = PACK_NAMES[ordinal]
            pending.append((output / name, data))
            receipts["vc_53450030/" + name] = dict(receipt, readback=True)
    io.publish_batch(pending)
    return dict(schema="b771/v1g/repair/v1", disc_files=receipts, executable=executable,
        idempotent=True, outside_scope_identical=True, runtime_witnessed=False,
        pins_sha256=sha(uniforms.PINS.read_bytes()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("input", "output", "receipt"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--xbe", type=Path)
    args = parser.parse_args(argv)
    io = scoped._b765()
    io.refuse_links(args.receipt)
    require(args.receipt.resolve() != args.input.resolve() and not
            (args.input.is_dir() and args.receipt.resolve().is_relative_to(args.input.resolve())) and
            args.receipt.resolve() not in {args.output.resolve() / n for n in PACK_NAMES}, "unsafe receipt path")
    receipt = repair(args.input, args.output, args.xbe)
    io.atomic_write(args.receipt, (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps(dict(receipt=str(args.receipt), files=list(receipt["disc_files"]), scope_verified=True)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

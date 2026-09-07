#!/usr/bin/env python3
"""Reproduce bounded static consumer metadata. Never writes game bytes.

EXPERIMENTAL / UNWITNESSED. Audits every field SCNE in outer 3136..3612,
the scorebug's nine frame materials, and the live helmet's A shell/accessories
at both LODs. --families adds the ESPN strip, numbers and clean/mud jersey
draws at the three player scene splits. This is not an exhaustive runtime
call-graph proof.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/"tools")]
from mod_editor.core import nfl2k5_hires_pack as pack
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import nfl2k5_models as models
from tools import nfl_scne_gltf as topology
from tools import nfl_txtr as txtr


def audit_scene(raw, key, wanted):
    source = models.ModelSpanSource({key:raw})
    _, decoded, scene = source.parse(key)
    selected = {x["index"] for x in scene["materials"] if
                (wanted(x["name"]) if callable(wanted) else x["name"] in wanted)}
    rows = []
    for shape in scene["shapes"]:
        subs = [x for x in scene["submeshes"] if x["shape_index"]==shape["index"] and x["material_index"] in selected]
        if not subs:
            continue
        lanes = models._shape_lanes(scene,shape,decoded)
        archive.require(lanes.texcoord is not None, "Selected draw lacks NORMSHORT2 UVs")
        values = models.read_lane_2h(decoded,shape,lanes.texcoord,lanes.vertex_count)
        for sub in subs:
            ids = sorted({i for _,batch in topology.decode_batches(decoded,sub["command_offset"],sub["primary_command_word_count"]) for i in batch})
            uv = [models.uv_to_gltf(*values[i],lanes.uv_scale,lanes.uv_offset) for i in ids]
            archive.require(uv and all(math.isfinite(v) for pair in uv for v in pair), "Nonfinite or absent UVs")
            rows.append(dict(material=sub["material_name"],shape=shape["index"],shape_record=shape["record_offset"],
                vertex_count=len(ids),first_vertex=min(ids),last_vertex=max(ids),uv_scale=list(lanes.uv_scale),
                uv_offset=list(lanes.uv_offset),uv_bounds=[[min(p[i] for p in uv),max(p[i] for p in uv)] for i in range(2)],
                lane=list(lanes.texcoord),uv_bytes_sha256=pack.sha(b"".join(struct.pack("<2h",*values[i]) for i in ids))))
    return dict(key=key,scene=scene["name"],span_sha256=pack.sha(raw),decoded_sha256=pack.sha(decoded),draws=rows)


def audit(image, *, families=False):
    result = dict(schema="nfl2k5_hires_consumers/v2" if families else "nfl2k5_hires_consumers/v1",experimental=True,runtime_witnessed=False,
        equation="uv = NORMSHORT2(register 6) * shape[+0x30].xy + shape[+0x30].zw; no texture-size term",
        inherited_shader_evidence="mod_editor/core/nfl2k5_models.py module documentation; RC78 UV correction",
        exhaustive_runtime_consumers_proved=False,scenes=[],field_scenes_scanned=477)
    with archive.Disc(image,descriptors=()) as disc:
        result["consumer_xbe"] = pack._consumer_check(disc,tuple(texture.key for texture in pack.ASSETS))
        entry = disc.entries["default.xbe"]
        xbe = disc.read(entry.size,entry.byte_offset)
        sections = pack.nfl2k5_bump_strength._sections(xbe)
        def readva(va,size):
            section = next(s for s in sections if s.virtual_address<=va and va+size<=s.virtual_address+s.raw_size)
            at = section.raw_offset+va-section.virtual_address
            return xbe[at:at+size]
        def string(va):
            data = readva(va,128)
            end = next(i for i in range(0,len(data),2) if data[i:i+2]==bytes(2))
            return data[:end].decode("utf-16le")
        pairs = [list(string(v) for v in struct.unpack("<II",readva(0xA95C60+i*8,8))) for i in range(11)]
        result["scorebug_binding_pairs"] = pairs
        wanted = {material for material,name in pairs if families or name=="score_buga"}
        uniform = (lambda n: n in {"HI_HELMET_A", "HELMET_A_accessories"} or 'NUMBER' in n or 'UNIF_jersey' in n)
        scenes = ((346,78,wanted),(3,113,uniform),(3,114,uniform),(3,115,uniform)) if families else (
            (346,78,wanted),(3,113,{"HI_HELMET_A","HELMET_A_accessories"}),
            (3,115,{"HI_HELMET_A","HELMET_A_accessories"}))
        for outer,chunk,names in scenes:
            entry = disc.archive_entries[outer]
            archive.require(entry.size<=32*archive.BLOCK,"Scene container exceeds bound")
            container = disc.read_entry_range(entry,0,entry.size)
            _,_,raw = list(archive.chunks(container))[chunk]
            result["scenes"].append(audit_scene(raw,f"o{outer}c{chunk}",names))
        fields, absent = [], []
        for outer in range(3136,3613):
            entry = disc.archive_entries[outer]
            header = disc.read_entry_range(entry,0,32)
            stored = int.from_bytes(header[4:8],"little")
            archive.require(header[:4]==b"SCNE" and stored<16*archive.BLOCK
                            and 32+stored<=entry.size, "Foreign field scene")
            raw = disc.read_entry_range(entry,0,32+stored)
            chunk = txtr.parse_chunks(raw)[0]
            archive.require(chunk.output_size<=32*archive.BLOCK,"Field decode exceeds bound")
            decoded,_ = txtr.decode_chunk(raw,chunk)
            if "center_logo".encode("utf-16le") not in decoded:
                absent.append(outer)
                continue
            row = audit_scene(raw,f"o{outer}c0",{"center_logo"})
            if row["draws"]:
                fields.append(row)
            else:
                absent.append(outer)
        result["field_scenes_with_logo"] = len(fields)
        result["field_scenes_without_logo"] = absent
        result["scenes"].extend(fields)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image",type=Path)
    parser.add_argument("--families", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit(args.image, families=args.families),indent=2))


if __name__ == "__main__":
    main()

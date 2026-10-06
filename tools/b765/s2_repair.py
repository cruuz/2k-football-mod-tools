"""Scoped native repair of ATL field paint in a v0.4 resource file set.

Input is a directory of extracted s01{d,a,n}{d,r,s}.iff bundles, plus the
reviewed DEN/MIA/PIT bundles when --include-midfield is selected, and independent
end-zone bundles when --include-endzones is selected. The repair
pins the field span, rather than the entire bundle, so s1 can independently
repair its stadium span. It never opens or modifies an ISO. No yard numbers
or stadium geometry are written. The four Atlanta midfield
positions use the source manifest's reviewed scale; its texture stays identical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
from mod_editor.core import nfl2k5_modern_metlife as ml
from mod_editor.core import nfl2k5_mercedes_benz_model as mb
from mod_editor.core import nfl2k5_modern_color as colour
from mod_editor.core import nfl2k5_modern_surfaces as surfaces

MANIFEST = Path(__file__).with_name("s2_repair_manifest.json")
MATERIALS = tuple(f"endzone_N_{p}" for p in "LMR")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def outside_digest(data,ranges):
    digest=hashlib.sha256();last=0
    for start,end in sorted(ranges):
        if not 0<=last<=start<=end<=len(data):
            raise ValueError("Repair ranges overlap or escape the resource")
        digest.update(data[last:start]);last=end
    digest.update(data[last:]);return digest.hexdigest()


def compile_payloads(retail,name,team):
    """Run the Studio's field/colour/surface steps and retain only owned P8 bytes.

    This makes the native repair and a normal pack build agree even at graded
    antialiased pixels. A second quantization of post-grade RGBA would change
    those edges and lose the weather appearance.
    """
    pin=mb._venue_pins()[name]
    settings=colour.normalize_settings({})
    chunk=ml.bundle_scenes(retail)["field"]
    span,fit=mb.field_span(retail,name,team=team,colour_settings=settings,outer_index=pin["outer"])
    if fit["half_detail"] or fit["palette_cap"]!=256:
        raise ValueError(f"{name}: refusing reduced-detail Studio field art")
    compiled=retail[:chunk.offset]+span+retail[chunk.offset+len(span):]
    compiled,surface_receipt=surfaces.surface_bundle(compiled,name,indoor=True,colour_settings=settings)
    final_chunk=ml.bundle_scenes(compiled)["field"];rec,decoded=ml._scene(compiled,final_chunk)
    rows=ml.texture_rows(rec);payloads={}
    for key in MATERIALS:
        row=rows[key];start=final_chunk.system_bytes+int(row["pixel_offset"])
        end=final_chunk.system_bytes+int(row["palette_offset"])+1024
        rgba,_=ml.read_p8(decoded,final_chunk.system_bytes,row)
        payloads[key]=dict(bytes=decoded[start:end],rgba=rgba,
                           size=[row["width"],row["height"]],mip_levels=row["mip_levels"])
    return payloads,dict(field_fit=fit,surface=surface_receipt,
                        selected_payload_sha256={k:sha(v["bytes"]) for k,v in payloads.items()})


def repair_bundle(data,name,team,manifest=None,*,payloads=None):
    """Return repaired bytes and a proof; refuse unexpected field or art hashes."""
    doc=manifest or json.loads(MANIFEST.read_text())
    if name not in doc["bundles"]:
        raise ValueError(f"Unowned field resource: {name}")
    pin=doc["bundles"][name]
    for key in MATERIALS:
        if sha(np.ascontiguousarray(team[key]).tobytes()) != doc["art_rgba_sha256"][key]:
            raise ValueError(f"{key}: unexpected source art pixels")
    if getattr(team,"midfield_scale",1.0) != doc.get("midfield_scale",1.0):
        raise ValueError("Unexpected midfield placement")
    chunk=ml.bundle_scenes(data)["field"]
    span=ml.scene_span(data,chunk)
    if chunk.offset != pin["field_offset"] or len(span) != pin["field_size"]:
        raise ValueError(f"{name}: field allocation moved")
    digest=sha(span)
    if digest == pin.get("after_field_sha256"):
        return data,dict(name=name,state="already_applied",before_sha256=sha(data),after_sha256=sha(data),
                         field_sha256=digest)
    if digest != pin["field_sha256"]:
        raise ValueError(f"{name}: unexpected field SHA-256 {digest}")
    rec,decoded=ml._scene(data,chunk);rows=ml.texture_rows(rec)
    if sha(decoded) != pin["decoded_sha256"] or chunk.system_bytes != pin["system_bytes"]:
        raise ValueError(f"{name}: unexpected decoded field")
    if payloads is None:
        raise ValueError("Compile hash-pinned Studio field payloads from the supported retail resource first")
    edited=bytearray(decoded);allowed=[];textures=[]
    for key in MATERIALS:
        row=rows[key];before,_=ml.read_p8(decoded,chunk.system_bytes,row)
        start=chunk.system_bytes+int(row["pixel_offset"])
        end=chunk.system_bytes+int(row["palette_offset"])+1024
        source=payloads[key]
        if source["size"]!=[row["width"],row["height"]] or len(source["bytes"])!=end-start:
            raise ValueError(f"{key}: Studio payload differs from its native allocation")
        expected_payload=pin.get("payload_sha256",{}).get(key)
        if expected_payload and sha(source["bytes"])!=expected_payload:
            raise ValueError(f"{name}: non-reproducible Studio payload {key}")
        edited[start:end]=source["bytes"]
        allowed.append((start,end))
        after,_=ml.read_p8(edited,chunk.system_bytes,row)
        if not np.array_equal(after,source["rgba"]):
            raise ValueError("Studio/native texture readback differs")
        textures.append(dict(material=key,texture=row["index"],native_size=[row["width"],row["height"]],
                             mip_levels=row["mip_levels"],palette_entries=256,range=[start,end],
                             studio_payload_sha256=sha(source["bytes"]),studio_native_exact=True,
                             before_rgba_sha256=sha(before.tobytes()),
                             after_rgba_sha256=sha(after.tobytes()),
                             studio_pixel_max_error=0))
    placement=mb.scale_midfield(edited,rec,doc.get("midfield_scale",1.0))
    allowed.extend(placement)
    untouched=outside_digest(decoded,allowed)
    if untouched != outside_digest(edited,allowed):
        raise ValueError("Bytes outside the three P8 allocations and midfield positions changed")
    # s01ad's completely filled stream makes the native decoder's final
    # DWORD fetch read one byte beyond the original allocation. Keep trailing
    # slack within the unchanged 16-byte scratch; decoded art is identical.
    fitted,fit=(colour.fit_fixed_span(span,bytes(edited)) if name=="s01ad.iff"
                else ml.fit_span(span,bytes(edited)))
    if fitted[:32] != span[:32] or len(fitted)!=len(span):
        raise ValueError("The field wrapper or fixed allocation changed")
    out=data[:chunk.offset]+fitted+data[chunk.offset+len(span):]
    # Independent decode through the ordinary resource reader.
    back_chunk=ml.bundle_scenes(out)["field"];_,back=ml._scene(out,back_chunk)
    if back != edited or outside_digest(back,allowed)!=untouched:
        raise ValueError("Native readback or decoded scope proof failed")
    expected=pin.get("after_field_sha256")
    if expected and sha(fitted)!=expected:
        raise ValueError(f"{name}: non-reproducible output field SHA-256")
    outer_range=[(chunk.offset,chunk.offset+len(span))]
    if outside_digest(data,outer_range)!=outside_digest(out,outer_range):
        raise ValueError("Stadium, cameras or other outside-field bytes changed")
    return out,dict(name=name,state="repaired",before_sha256=sha(data),after_sha256=sha(out),
                    before_field_sha256=digest,after_field_sha256=sha(fitted),
                    field_offset=chunk.offset,field_size=len(span),decoded_ranges=allowed,
                    outside_field_sha256=outside_digest(data,outer_range),
                    outside_decoded_scope_sha256=untouched,decoded_before_sha256=sha(decoded),
                    decoded_after_sha256=sha(back),wrapper_unchanged=True,
                    scope="three end-zone P8 mip chains and palettes; eight midfield x/z floats",
                    midfield_position_ranges=placement,midfield_scale=doc.get("midfield_scale",1.0),
                    textures=textures,compression=fit)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--art-root",required=True,type=Path)
    parser.add_argument("--retail",required=True,type=Path,help="supported unmodified retail image or extracted archive")
    parser.add_argument("--include-midfield",action="store_true",help="also repair the 21 manifest-selected DEN/MIA/PIT fields using frozen pins")
    parser.add_argument("--include-endzones",action="store_true",help="also repair the manifest-selected independent end zones using frozen pins")
    parser.add_argument("--include-existing-fields",action="store_true",help="also repair the reviewed TB/WAS paint and TB midfield placement")
    args=parser.parse_args()
    if args.input.resolve()==args.output.resolve():
        raise ValueError("Use a separate output resource directory")
    doc=json.loads(MANIFEST.read_text());team=mb.team_field_art(args.art_root)
    retail=mb.read_retail(args.retail)
    args.output.mkdir(parents=True,exist_ok=True);receipts=[]
    for name in sorted(doc["bundles"]):
        before=(args.input/name).read_bytes()
        chunk=ml.bundle_scenes(before)["field"]
        already=sha(ml.scene_span(before,chunk))==doc["bundles"][name].get("after_field_sha256")
        payloads,build=({}, {}) if already else compile_payloads(retail[name],name,team)
        after,receipt=repair_bundle(before,name,team,doc,payloads=payloads)
        if build:receipt["studio_build"]=build
        target=args.output/name
        if target.exists() and target.read_bytes()!=after:
            raise ValueError(f"Refusing to replace an unrelated output {target}")
        target.write_bytes(after);receipts.append(receipt)
        print(name,receipt["state"],receipt.get("after_field_sha256",receipt.get("field_sha256")),flush=True)
    if args.include_midfield:
        from tools.b765 import s2_midfield as midfield
        pins=json.loads(midfield.PINS.read_text());arrays=midfield.logos(args.art_root)
        if pins.get("schema")!=midfield.SCHEMA:
            raise ValueError("Unexpected missing-midfield pin schema")
        for name in sorted(pins["bundles"]):
            after,receipt=midfield.repair_bundle((args.input/name).read_bytes(),name,arrays[name[:3]],pins)
            target=args.output/name
            if target.exists() and target.read_bytes()!=after:
                raise ValueError(f"Refusing to replace an unrelated output {target}")
            target.write_bytes(after);receipts.append(receipt)
            print(name,"already_applied" if receipt.get("already_applied") else "repaired",flush=True)
    if args.include_endzones:
        from tools.b765 import s2_endzones as endzones
        receipt=endzones.repair_all(args.input,args.output,args.art_root,args.retail)
        receipts.extend(receipt["bundles"])
    if args.include_existing_fields:
        from tools.b765 import s2_existing_fields as existing_fields
        receipt=existing_fields.repair(args.input,args.output,args.art_root,args.retail)
        receipts.extend(receipt["bundles"])
    schema="s2_combined_native_scope/v1" if args.include_midfield or args.include_endzones or args.include_existing_fields else "s2_native_scope/v1"
    (args.output/"scope_receipt.json").write_text(json.dumps(dict(schema=schema,bundles=receipts),indent=2)+"\n", newline="\n")


if __name__=="__main__":
    main()

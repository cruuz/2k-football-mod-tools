"""Transfer reviewed Studio paint into existing native field allocations.

No scene records or texture allocations are added. Pinned selected P8 mip
chains/palettes and TB's eight private position floats are the only decoded
field changes. WAS borrows 1680 stored
bytes from its losslessly compressed full detail normal; the stored layer,
decoded normal and everything after that prefix stay exact. This command
reads extracted resources and never opens an ISO for writing.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_modern_metlife as ml
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_modern_color as colour
from mod_editor.core import nfl2k5_modern_surfaces as surfaces
from mod_editor.core import nfl2k5_midfield_art as midfield

PINS=Path(__file__).with_name("s2_existing_field_pins.json")
SCHEMA="b765_s2_existing_field_paint/v1"
REVIEWED_PREFIXES={"s27","s29"}


def sha(data):return hashlib.sha256(data).hexdigest()


def outside_sha(data,ranges):
    h=hashlib.sha256();last=0
    for start,end in sorted(ranges):
        if not 0<=last<=start<=end<=len(data):raise ValueError("Owned paint ranges overlap or escape field")
        h.update(data[last:start]);last=end
    h.update(data[last:]);return h.hexdigest()


def selected_payloads(data,keys):
    chunk=ml.bundle_scenes(data)["field"];rec,decoded=ml._scene(data,chunk)
    rows=ml.texture_rows(rec);result={}
    for key in keys:
        row=rows[key];start=chunk.system_bytes+int(row["pixel_offset"])
        end=chunk.system_bytes+int(row["palette_offset"])+1024
        result[key]=dict(data=decoded[start:end],size=[row["width"],row["height"]],
                         mips=row["mip_levels"],sha256=sha(decoded[start:end]))
    return result


def owned_scope(data,name):
    if name[:3]=="s29":
        _field,_layer,normal,_decoded=midfield.pit_sites(data)
        return 0,normal.end_offset,"field_detail_prefix"
    if name[:3]!="s27":raise ValueError("Unowned existing field: "+name)
    field=ml.bundle_scenes(data)["field"]
    return field.offset,field.end_offset-field.offset,"field"


def _compile(job):
    name,data,plan,base,outer,keys=job;settings=colour.normalize_settings({})
    out,venue=mv.combined_bundle(data,data,name,plan,base,outer_index=outer,settings=settings)
    options=dict(field_normal_loan=True) if name[:3]=="s29" and plan.get("endzone_turf_from_field") else {}
    out,surface=surfaces.surface_bundle(out,name,indoor=False,colour_settings=settings,**options)
    fields=[r["detail"] for r in venue if r["kind"]=="field"]
    if len(fields)!=1 or fields[0].get("palette_cap")!=256:
        raise ValueError(name+": refusing reduced-palette field paint")
    if surface["field"].get("palette_cap",256)!=256 or surface["field"].get("pattern_detail",2)!=2:
        raise ValueError(name+": refusing reduced-detail surface fallback")
    geometry={}
    if plan.get("midfield_scale_xz"):
        original_chunk=ml.bundle_scenes(data)["field"];rec,decoded=ml._scene(data,original_chunk)
        expected=bytearray(decoded)
        ranges=mv.scale_existing_midfield(expected,rec,name[:3],plan["midfield_scale_xz"])
        _rec,actual=ml._scene(out,ml.bundle_scenes(out)["field"])
        if any(actual[a:b]!=expected[a:b] for a,b in ranges):
            raise ValueError(name+": source midfield positions differ from reviewed placement")
        geometry=dict(ranges=ranges,sha256=sha(b"".join(actual[a:b] for a,b in ranges)))
    return name,selected_payloads(out,keys),dict(venue=venue,surface=surface,geometry=geometry)


def source_pixels(art_root,selected):
    art=mv.load_art(art_root);result={}
    for prefix,keys in selected.items():
        if prefix not in REVIEWED_PREFIXES:raise ValueError("Unreviewed existing field: "+prefix)
        items={i["key"]:i for i in art["venues"][prefix]["items"] if i["scene"]=="field"}
        result[prefix]={k:sha(mv._art_at(items[k],*items[k]["size"]).tobytes()) for k in keys}
    return result


def source_turf_donors(art_root,selected):
    """Pin the explicit background route as well as unchanged overlay pixels."""
    art=mv.load_art(art_root)
    return {prefix:True for prefix in selected
            if art["venues"][prefix].get("endzone_turf_from_field")}


def compile_payloads(retail_source,art_root,selected):
    art=mv.load_art(art_root);jobs=[]
    with mv._outer_image()(retail_source) as archive:
        for prefix,keys in selected.items():
            if prefix not in REVIEWED_PREFIXES:raise ValueError("Unreviewed existing field: "+prefix)
            bundles={}
            for pin in mv.venues()[prefix]["bundles"]:
                e=mv._entry(archive,pin);data=archive.read(e.virtual_offset,e.size)
                if sha(data)!=pin["retail_sha256"]:raise ValueError("Unexpected retail source: "+pin["name"])
                bundles[pin["name"]]=data
            plan=mv.plan_venue(prefix,art["venues"][prefix],bundles,art["league"])
            base=plan.pop("base");plan["items"]=[i for i in plan["items"] if i["scene"]=="field"]
            for pin in mv.venues()[prefix]["bundles"]:
                jobs.append((pin["name"],bundles[pin["name"]],plan,base,pin["outer"],keys))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(_compile,jobs))
    return {n:p for n,p,_r in rows},{n:r for n,_p,r in rows}


def repair_bundle(data,name,compiled,doc,*,derive=False):
    if name not in doc["bundles"] or name[:3] not in REVIEWED_PREFIXES:
        raise ValueError("Unowned existing field: "+name)
    pin=doc["bundles"][name];keys=doc["selected"][name[:3]]
    chunk=ml.bundle_scenes(data)["field"];span=ml.scene_span(data,chunk)
    scope_at,scope_size,scope_kind=owned_scope(data,name)
    digest=sha(data[scope_at:scope_at+scope_size])
    if not derive and digest==pin["after_sha256"]:
        return bytes(data),dict(name=name,already_applied=True,before_sha256=sha(data),after_sha256=sha(data))
    if digest!=pin["before_sha256"]:raise ValueError("Unexpected owned field SHA-256: "+name)
    if set(compiled)!=set(keys):raise ValueError("Unexpected selected field payload set")
    if any(sha(p["data"])!=p["sha256"] for p in compiled.values()):
        raise ValueError("Compiled payload bytes differ from their hashes")
    if not derive and {k:p["sha256"] for k,p in compiled.items()}!=pin["payload_sha256"]:
        raise ValueError("Unexpected Studio field payloads: "+name)
    rec,decoded=ml._scene(data,chunk);rows=ml.texture_rows(rec);edited=bytearray(decoded)
    ranges=[];written={};textures=[]
    for key in keys:
        row=rows[key];p=compiled[key];start=chunk.system_bytes+int(row["pixel_offset"])
        end=chunk.system_bytes+int(row["palette_offset"])+1024
        if p["size"]!=[row["width"],row["height"]] or p["mips"]!=row["mip_levels"] or len(p["data"])!=end-start:
            raise ValueError("Studio/native texture allocation differs: "+key)
        if start in written:
            if written[start]!=p["data"]:raise ValueError("Aliased field materials have different paint")
        else:
            edited[start:end]=p["data"];written[start]=p["data"];ranges.append((start,end))
        textures.append(dict(material=key,size=p["size"],mips=p["mips"],payload_sha256=p["sha256"],range=[start,end]))
    geometry=doc.get("midfield_scale_xz",{}).get(name[:3])
    placement=[]
    if geometry is not None:
        placement=mv.scale_existing_midfield(edited,rec,name[:3],geometry)
        ranges.extend(placement)
    untouched=outside_sha(decoded,ranges)
    if outside_sha(edited,ranges)!=untouched:raise ValueError("Unselected decoded field bytes changed")
    # The game's decoder fetches a final DWORD even when only one byte is
    # consumed. Washington's afternoon stream can therefore read one byte
    # beyond its allocation with a completely filled body. The existing
    # fixed-span fitter reserves trailing slack within the unchanged16-byte
    # scratch, keeping that real native read inside the original allocation.
    loan=None
    if name[:3]=="s29":
        out,loan=midfield.refit_washington_field(data,name,
            lambda enlarged:colour.fit_fixed_span(enlarged,bytes(edited)))
        fit=loan["paint"]
        after=ml.scene_span(out,ml.bundle_scenes(out)["field"])
        if after[:4]!=span[:4] or after[8:32]!=span[8:32] or len(after)!=len(span)+1680:
            raise ValueError("Native field loan changed more than its stored allocation")
    else:
        after,fit=ml.fit_span(span,bytes(edited))
        if after[:32]!=span[:32] or len(after)!=len(span):raise ValueError("Native field wrapper/allocation changed")
        out=data[:chunk.offset]+after+data[chunk.end_offset:]
    end=scope_at+scope_size
    if out[:scope_at]!=data[:scope_at] or out[end:]!=data[end:]:raise ValueError("Outside-owned-field bytes changed")
    _,back=ml._scene(out,ml.bundle_scenes(out)["field"])
    if back!=edited:raise ValueError("Native field readback differs")
    applied=sha(out[scope_at:end])
    if not derive and applied!=pin["after_sha256"]:raise ValueError("Native output differs from deterministic pin")
    return out,dict(name=name,before_sha256=sha(data),after_sha256=sha(out),field_before_sha256=sha(span),
                    field_after_sha256=sha(after),scope_before_sha256=digest,scope_after_sha256=applied,
                    scope_kind=scope_kind,scope_offset=scope_at,scope_size=scope_size,
                    outside_scope_identical=True,outside_scope_sha256=sha(data[:scope_at]+data[end:]),
                    outside_decoded_scope_sha256=untouched,studio_native_payload_exact=True,
                    wrapper_identical=loan is None,wrapper_scratch_and_decoded_sizes_identical=True,
                    allocation_loan=loan,textures=textures,fit=fit,
                    midfield_scale_xz=geometry,midfield_position_ranges=placement,
                    midfield_position_sha256=sha(b"".join(edited[a:b] for a,b in placement)) if placement else None)


def repair(input_dir,output_dir,art_root,retail_source,*,pins=PINS):
    src,dst=Path(input_dir).resolve(),Path(output_dir).resolve()
    if src==dst or src in dst.parents:raise ValueError("Repair output must be separate from input")
    doc=json.loads(Path(pins).read_text());selected=doc["selected"]
    expected={n for prefix in selected for n in mv.bundle_names(prefix)}
    if doc.get("schema")!=SCHEMA or set(doc["bundles"])!=expected:
        raise ValueError("Unexpected existing-field pin schema/resource set")
    if source_pixels(art_root,selected)!=doc["source_rgba_sha256"]:
        raise ValueError("Unexpected reviewed source pixels")
    art=mv.load_art(art_root)
    placements={prefix:art["venues"][prefix]["midfield_scale_xz"] for prefix in selected
                if art["venues"][prefix].get("midfield_scale_xz")}
    if placements!=doc.get("midfield_scale_xz",{}):
        raise ValueError("Unexpected reviewed midfield placement")
    if source_turf_donors(art_root,selected)!=doc.get("endzone_turf_from_field",{}):
        raise ValueError("Unexpected reviewed end-zone turf donor route")
    compiled,build=compile_payloads(retail_source,art_root,selected);rows=[];dst.mkdir(parents=True,exist_ok=True)
    for name in sorted(doc["bundles"]):
        out,row=repair_bundle((src/name).read_bytes(),name,compiled[name],doc);path=dst/name
        geometry=build[name]["geometry"]
        if not row.get("already_applied") and geometry and geometry["sha256"]!=row["midfield_position_sha256"]:
            raise ValueError("Studio/native midfield positions differ: "+name)
        if path.exists() and path.read_bytes()!=out:raise ValueError("Refusing differing output: "+str(path))
        if not path.exists():path.write_bytes(out)
        rows.append(row)
    result=dict(schema=SCHEMA,bundles=rows,build=build)
    (dst/"existing_field_scope_receipt.json").write_text(json.dumps(result,indent=2)+"\n", newline="\n")
    return result


def prove_native_decoder(input_dir,xbe,*,pins=PINS):
    """Execute the recognized retail decompressor against every frozen field."""
    from tools.b765.s2_native_decoder import prove_chunk
    doc=json.loads(Path(pins).read_text());rows=[]
    for name,pin in sorted(doc["bundles"].items()):
        data=(Path(input_dir)/name).read_bytes();chunk=ml.bundle_scenes(data)["field"]
        at,size,_kind=owned_scope(data,name)
        if sha(data[at:at+size])!=pin["after_sha256"]:
            raise ValueError("Native decoder proof needs frozen existing field: "+name)
        rows.append(dict(name=name,kind="field",**prove_chunk(data,chunk,xbe)))
        if name[:3]=="s29":
            _field,_layer,normal,_decoded=midfield.pit_sites(data)
            rows.append(dict(name=name,kind="detail_normal",**prove_chunk(data,normal,xbe)))
    return dict(native_entry="0x4dc00",offline_cpu_execution=True,chunks=rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True,type=Path);p.add_argument("--output",required=True,type=Path)
    p.add_argument("--art-root",type=Path);p.add_argument("--retail",type=Path)
    p.add_argument("--prove-decoder",action="store_true");p.add_argument("--xbe",type=Path)
    a=p.parse_args()
    if a.prove_decoder:
        if not a.xbe:p.error("--prove-decoder requires --xbe")
        result=prove_native_decoder(a.input,a.xbe)
        a.output.write_text(json.dumps(result,indent=2)+"\n", newline="\n");return
    if not a.art_root or not a.retail:p.error("repair requires --art-root and --retail")
    result=repair(a.input,a.output,a.art_root,a.retail)
    print(json.dumps(dict(repaired=len(result["bundles"]),receipt=str(a.output/"existing_field_scope_receipt.json"))))


if __name__=="__main__":main()

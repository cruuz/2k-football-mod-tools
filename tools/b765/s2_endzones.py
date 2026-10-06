"""Reproduce the reviewed shared-end field repair without opening a disc for writing.

Studio compiles the six P8 payloads at native dimensions with its colour/surface
steps. Native repair copies only these payloads and three texture links/copies.
Whole-bundle hashes are evidence, not pins, so independent stadium repairs stack.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_metlife as ml
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_modern_color as colour
from mod_editor.core import nfl2k5_modern_surfaces as surfaces
from mod_editor.core import nfl2k5_scne_builder as sb
from mod_editor.core import nfl2k5_split_endzone_art as ez

PINS = Path(__file__).with_name("s2_endzone_pins.json")
DET_PINS = Path(__file__).with_name("s2_det_endzone_pins.json")
CLE_PINS = Path(__file__).with_name("s2_cle_endzone_pins.json")
PINSETS = {"s37": PINS, "s09": DET_PINS, "s30": CLE_PINS}
TEAM_PREFIXES = {"HOU": "s37", "DET": "s09", "CLE": "s30"}
SCHEMA = "b765_s2_independent_endzones/v1"
KEYS = tuple("endzone_"+end+"_"+part for end in "NS" for part in "LMR")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def field_scene(data):
    chunk = ml.bundle_scenes(data)["field"]
    decoded, _ = ml._tools()[0].decode_chunk(data, chunk)
    return chunk, sb.parse(decoded, chunk.system_bytes, secondary=True)


def payloads(data):
    _, scene = field_scene(data)
    result = {}
    for key in KEYS:
        t = scene.textures[scene.materials[scene.material_index(key)].texture]
        result[key] = dict(pixels=t.pixels, palette=t.palette,
                           size=[t.width,t.height],mips=t.mips,
                           sha256=sha(t.pixels+t.palette))
    return result


def _compile(job):
    name, retail, plan, base, outer = job
    settings = colour.normalize_settings({})
    built, detail = mv.combined_bundle(retail,retail,name,plan,base,outer_index=outer,settings=settings)
    options = dict(preserve_full_normal=True,full_detail=True) if plan.get("field_prefix_loan") else {}
    built, surface = surfaces.surface_bundle(built,name,indoor=name[:3] in {"s09","s37"},
                                             colour_settings=settings,**options)
    field=[r["detail"] for r in detail if r["kind"]=="field"]
    if len(field)!=1 or field[0].get("palette_cap")!=256:
        raise ValueError(name+": refusing reduced-palette independent end zones")
    if plan.get("field_prefix_loan") and surface["normal"]!="full":
        raise ValueError(name+": refusing tiled or flattened normal fallback")
    return name, payloads(built), dict(venue=detail,surfaces=surface)


def source_pixels(art_root,prefix="s37"):
    art = mv.load_art(art_root)
    venue = art["venues"][prefix]
    if not venue.get("split_shared_endzones"):
        raise ValueError(prefix+" source must explicitly select independent end zones")
    return {i["key"]:sha(mv._art_at(i,256,128).tobytes())
            for i in venue["items"] if i["scene"]=="field" and i["key"] in KEYS}


def compile_payloads(retail_source,art_root,prefix="s37"):
    art=mv.load_art(art_root);venue=art["venues"][prefix]
    if not venue.get("split_shared_endzones"):
        raise ValueError(prefix+" source must explicitly select independent end zones")
    bundles={}
    with mv._outer_image()(retail_source) as archive:
        for pin in mv.venues()[prefix]["bundles"]:
            entry=mv._entry(archive,pin)
            data=archive.read(entry.virtual_offset,entry.size)
            if sha(data)!=pin["retail_sha256"]:
                raise ValueError("Unexpected retail source: "+pin["name"])
            bundles[pin["name"]]=data
    plan=mv.plan_venue(prefix,venue,bundles,art["league"])
    base=plan.pop("base");plan["items"]=[i for i in plan["items"] if i["scene"]=="field"]
    jobs=[(p["name"],bundles[p["name"]],plan,base,p["outer"]) for p in mv.venues()[prefix]["bundles"]]
    with ProcessPoolExecutor(max_workers=2) as pool:
        rows=list(pool.map(_compile,jobs))
    return {name:p for name,p,_ in rows},{name:r for name,_,r in rows}


def repair_bundle(data,name,compiled,doc,*,derive=False):
    if name[:3] not in PINSETS or name not in doc["bundles"]:
        raise ValueError("Unowned independent-end resource: "+name)
    pin=doc["bundles"][name]
    chunk,original=field_scene(data)
    span=ml.scene_span(data,chunk)
    at,size,kind=ez.owned_scope(data,name);end=at+size
    if pin.get("scope_kind", "field") != kind:
        raise ValueError("Unexpected owned field scope: "+name)
    digest=sha(data[at:end])
    if not derive and digest==pin["after_sha256"]:
        return bytes(data),dict(name=name,already_applied=True,before_sha256=sha(data),after_sha256=sha(data))
    if digest!=pin["before_sha256"]:
        raise ValueError("Unexpected owned field SHA-256: "+name)
    if set(compiled)!=set(KEYS):
        raise ValueError("Expected all six compiled end-zone payloads")
    if any(sha(p["pixels"]+p["palette"])!=p["sha256"] for p in compiled.values()):
        raise ValueError("Compiled payload bytes differ from their hashes")
    if not derive and {k:p["sha256"] for k,p in compiled.items()}!=pin["payload_sha256"]:
        raise ValueError("Unexpected Studio end-zone payloads: "+name)
    def painter(decoded,system,video):
        scene=sb.parse(decoded,system,secondary=True);rows=[]
        for key in KEYS:
            index=scene.materials[scene.material_index(key)].texture
            t=scene.textures[index];p=compiled[key]
            if (p["size"]!=[t.width,t.height] or p["mips"]!=t.mips
                    or len(p["pixels"])!=len(t.pixels) or len(p["palette"])!=1024):
                raise ValueError("Studio/native texture allocation differs: "+key)
            t.pixels,t.palette=p["pixels"],p["palette"]
            rows.append(dict(key=key,texture=index,studio_payload_sha256=p["sha256"],size=p["size"],mips=p["mips"]))
        out,ns,nv=sb.serialize(scene)
        if (ns,nv)!=(system,video):
            raise ValueError("Native paint changed scene allocation")
        return out,dict(textures=rows,palette_cap=256)
    out,detail=ez.split_bundle(data,name,painter=painter)
    after=out[at:end]
    if not derive and sha(after)!=pin["after_sha256"]:
        raise ValueError("Native output differs from deterministic pin: "+name)
    if out[:at]!=data[:at] or out[end:]!=data[end:]:
        raise ValueError("Bytes outside owned field differ")
    got=payloads(out)
    if {k:p["sha256"] for k,p in got.items()}!={k:p["sha256"] for k,p in compiled.items()}:
        raise ValueError("Native readback differs from Studio paint")
    return out,dict(name=name,before_sha256=sha(data),after_sha256=sha(out),
                    field_before_sha256=sha(span),field_after_sha256=sha(ml.scene_span(out,ml.bundle_scenes(out)["field"])),
                    owned_before_sha256=digest,owned_after_sha256=sha(after),
                    scope_kind=kind,scope_offset=at,scope_size=size,outside_scope_identical=True,
                    outside_field_identical=kind=="field",
                    outside_scope_sha256=sha(data[:at]+data[end:]),
                    studio_native_payload_exact=True,detail=detail)


def repair(input_dir,output_dir,art_root,retail_source,*,pins=PINS):
    src,dst=Path(input_dir).resolve(),Path(output_dir).resolve()
    if src==dst or src in dst.parents:
        raise ValueError("Repair output must be separate from input")
    doc=json.loads(Path(pins).read_text())
    prefixes={n[:3] for n in doc["bundles"]}
    if len(prefixes)!=1 or not prefixes <= set(PINSETS):
        raise ValueError("Unexpected independent-end ownership")
    prefix=next(iter(prefixes))
    if doc.get("schema")!=SCHEMA or set(doc["bundles"])!=set(mv.bundle_names(prefix)):
        raise ValueError("Unexpected independent-end pin schema/resource set")
    if source_pixels(art_root,prefix)!=doc["source_rgba_sha256"]:
        raise ValueError("Unexpected reviewed source pixels: "+prefix)
    compiled,build=compile_payloads(retail_source,art_root,prefix)
    rows=[];dst.mkdir(parents=True,exist_ok=True)
    for name in sorted(doc["bundles"]):
        out,row=repair_bundle((src/name).read_bytes(),name,compiled[name],doc)
        path=dst/name
        if path.exists() and path.read_bytes()!=out:
            raise ValueError("Refusing to overwrite a differing output: "+str(path))
        if not path.exists():path.write_bytes(out)
        rows.append(row)
    receipt=dict(schema=SCHEMA,bundles=rows,build=build)
    (dst/"endzone_scope_receipt.json").write_text(json.dumps(receipt,indent=2)+"\n", newline="\n")
    return receipt


def repair_all(input_dir,output_dir,art_root,retail_source,*,prefixes=tuple(PINSETS)):
    rows=[];build={}
    for prefix in prefixes:
        if prefix not in PINSETS:raise ValueError("Unowned independent-end venue: "+prefix)
        receipt=repair(input_dir,output_dir,art_root,retail_source,pins=PINSETS[prefix])
        rows.extend(receipt["bundles"]);build.update(receipt["build"])
        (Path(output_dir)/(prefix+"_endzone_scope_receipt.json")).write_text(json.dumps(receipt,indent=2)+"\n", newline="\n")
    result=dict(schema=SCHEMA,bundles=rows,build=build)
    (Path(output_dir)/"endzone_scope_receipt.json").write_text(json.dumps(result,indent=2)+"\n", newline="\n")
    return result


def prove_native_decoder(input_dir,xbe,*,pins=PINS):
    """Run retail decoder code offline against frozen repaired field spans."""
    from tools.b765.s2_native_decoder import prove_chunk
    doc=json.loads(Path(pins).read_text());rows=[]
    for name,pin in sorted(doc["bundles"].items()):
        data=(Path(input_dir)/name).read_bytes()
        chunk=ml.bundle_scenes(data)["field"]
        at,size,kind=ez.owned_scope(data,name)
        if sha(data[at:at+size])!=pin["after_sha256"]:
            raise ValueError("Native decoder proof needs a frozen repaired field: "+name)
        rows.append(dict(name=name,kind="field",**prove_chunk(data,chunk,xbe)))
        if kind=="field_detail_prefix":
            from mod_editor.core import nfl2k5_midfield_art as mf
            _f,_l,normal,_decoded=mf.pit_sites(data)
            rows.append(dict(name=name,kind="detail_normal",**prove_chunk(data,normal,xbe)))
    return dict(native_entry="0x4dc00",offline_cpu_execution=True,chunks=rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=("repair","pin","prove-decoder"))
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--art-root",type=Path)
    p.add_argument("--retail",type=Path)
    p.add_argument("--xbe",type=Path)
    p.add_argument("--team",choices=("all","HOU","DET","CLE"),default="all")
    a=p.parse_args()
    prefixes=tuple(PINSETS) if a.team=="all" else (TEAM_PREFIXES[a.team],)
    if a.command=="prove-decoder":
        if not a.xbe:p.error("prove-decoder requires --xbe")
        results=[prove_native_decoder(a.input,a.xbe,pins=PINSETS[v]) for v in prefixes]
        result=dict(native_entry="0x4dc00",offline_cpu_execution=True,chunks=[r for d in results for r in d["chunks"]])
        a.output.write_text(json.dumps(result,indent=2)+"\n", newline="\n")
        return
    if not a.art_root or not a.retail:p.error("repair/pin require --art-root and --retail")
    if a.command=="repair":
        result=repair_all(a.input,a.output,a.art_root,a.retail,prefixes=prefixes)
        print(json.dumps(dict(repaired=len(result["bundles"]),receipt=str(a.output/"endzone_scope_receipt.json"))))
    else:
        if len(prefixes)!=1:p.error("pin requires one --team")
        prefix=prefixes[0]
        compiled,_=compile_payloads(a.retail,a.art_root,prefix)
        doc=dict(schema=SCHEMA,source_rgba_sha256=source_pixels(a.art_root,prefix),bundles={})
        for name in mv.bundle_names(prefix):
            data=(a.input/name).read_bytes()
            at,size,kind=ez.owned_scope(data,name)
            doc["bundles"][name]=dict(scope_kind=kind,before_sha256=sha(data[at:at+size]))
            out,row=repair_bundle(data,name,compiled[name],doc,derive=True)
            doc["bundles"][name].update(after_sha256=row["owned_after_sha256"],
                                        payload_sha256={k:p["sha256"] for k,p in compiled[name].items()},receipt=row)
        if a.output.exists():raise ValueError("Pin output already exists")
        a.output.write_text(json.dumps(doc,indent=2)+"\n", newline="\n")


if __name__=="__main__":main()

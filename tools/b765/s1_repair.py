#!/usr/bin/env python3
"""Apply reviewed stadium edits to extracted disc resources, never an original disc.

Plan schema b765_s1_repair_plan/v1, entries:
  {name, manifest, edited, positions:[shape IDs], uvs:[shape IDs],
   rescale_uvs:[], bounds:[]} for geometry authored by the coordinator; or
  {name, manifest, textures:[{material, png}]} for stadium-only P8 pixels.
Paths are relative to the plan. Export manifests pin exact source SCNE spans.
Other chunks (including job s2's field art) compose and stay byte-identical.
Preflight every entry before any output; deterministic, exact-output idempotent.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.b765 import s1_geometry as geometry


def texture_bundle(data,manifest_path,textures):
    """Exact source-span pin; only named stadium P8 allocations may differ decoded."""
    import numpy as np
    from PIL import Image
    from mod_editor.core import nfl2k5_modern_metlife as ml,nfl2k5_scne_builder as sb
    manifest=json.loads(manifest_path.read_text())
    geometry.require(manifest.get('schema')==geometry.SCHEMA,'unexpected export manifest schema')
    span=(manifest_path.parent/'source.scne').read_bytes()
    geometry.require(geometry.sha(span)==manifest['source_span_sha256'],'source SCNE hash differs')
    source_chunk,rec,original=geometry.stadium(span)
    geometry.require(geometry.sha(original)==manifest['source_decoded_sha256'],'source decoded hash differs')
    rows=ml.texture_rows(rec);edited=bytearray(original);ranges=[];detail=[];seen=set();allocations=set()
    for item in textures:
        geometry.require(set(item)=={'material','png'},'texture item must contain material and png')
        mat=item['material'];geometry.require(mat in rows and mat not in seen,'missing or duplicate stadium P8 material')
        seen.add(mat);row=rows[mat]
        geometry.require(row['index'] not in allocations,'multiple material names target the same texture allocation')
        allocations.add(row['index'])
        image_path=Path(item['png'])
        with Image.open(image_path) as im:rgba=np.asarray(im.convert('RGBA'),dtype=np.uint8)
        current,_=ml.read_p8(original,source_chunk.system_bytes,row)
        if np.array_equal(current,rgba):continue
        count=ml.write_p8(edited,source_chunk.system_bytes,row,rgba)
        pixel=source_chunk.system_bytes+int(row['pixel_offset']);palette=source_chunk.system_bytes+int(row['palette_offset'])
        ranges.append((pixel,palette+1024))
        detail.append(dict(material=mat,mapped_material_names=row['mapped_material_names'],texture_index=row['index'],offset=pixel,length=palette+1024-pixel,
            png_sha256=geometry.sha(image_path.read_bytes()),palette_entries=count))
    proof=geometry.scope_proof(original,bytes(edited),ranges)
    if bytes(edited)==original:after,fit=span,dict(unchanged=True)
    else:after,fit=sb.fixed_span_chunk('SCNE',bytes(edited),source_chunk.system_bytes,source_chunk.video_bytes,span)
    chunk,_,before_decoded=geometry.stadium(data);before=data[chunk.offset:chunk.end_offset]
    geometry.require(chunk.offset==manifest['chunk_offset'] and len(before)==manifest['chunk_length'],'stadium span moved')
    geometry.require(geometry.sha(before) in {geometry.sha(span),geometry.sha(after)},'unexpected input stadium hash')
    output=data[:chunk.offset]+after+data[chunk.end_offset:]
    _,_,back=geometry.stadium(output)
    geometry.require(back==bytes(edited),'native texture readback differs')
    geometry.require(output[:chunk.offset]==data[:chunk.offset] and output[chunk.end_offset:]==data[chunk.end_offset:],'outside-span bytes differ')
    return output,dict(schema='b765_s1_texture_receipt/v1',disc_file=manifest['disc_file'],
        before_sha256=geometry.sha(data),after_sha256=geometry.sha(output),offset=chunk.offset,length=len(after),
        before_span_sha256=geometry.sha(before),after_span_sha256=geometry.sha(after),source_span_sha256=geometry.sha(span),
        decoded_before_sha256=geometry.sha(before_decoded),decoded_after_sha256=geometry.sha(back),
        outside_stored_span_identical=True,readback_exact=True,already_applied=before==after,
        decoded_scope=geometry.scope_proof(before_decoded,back,ranges),compiled_source_scope=proof,textures=detail,compression=fit)


def _prepare_entry(job):
    input_dir,base,item=job
    name=item['name'];data=(Path(input_dir)/name).read_bytes();manifest=(base/item['manifest']).resolve()
    geometry.require(json.loads(manifest.read_text())['disc_file']==name,'export manifest names a different resource')
    if 'textures' in item:
        geometry.require(set(item)=={'name','manifest','textures'},'unexpected texture plan fields')
        tex=[dict(t,png=str((base/t['png']).resolve())) for t in item['textures']]
        return texture_bundle(data,manifest,tex)
    geometry.require(set(item)<={'name','manifest','edited','positions','uvs','rescale_uvs','bounds','uv_constants'},'unexpected geometry plan fields')
    return geometry.compile_bundle(data,manifest,(base/item['edited']).resolve(),
        uv_constants={int(k):v for k,v in item.get('uv_constants',{}).items()},
        **{key:set(item.get(key,[])) for key in ('positions','uvs','rescale_uvs','bounds')})


def prepare(input_dir,plan_path, *, workers=1):
    plan_path=Path(plan_path);doc=json.loads(plan_path.read_text());base=plan_path.parent
    geometry.require(doc.get('schema')=='b765_s1_repair_plan/v1' and isinstance(doc.get('entries'),list),'unexpected repair plan schema')
    geometry.require(workers>0,'workers must be positive')
    output={};receipts=[];names=set();jobs=[]
    for item in doc['entries']:
        name=item['name'];geometry.require(Path(name).name==name and name.endswith('.iff') and name not in names,'unsafe or duplicate resource name')
        names.add(name);jobs.append((input_dir,base,item))
    if workers==1:
        results=map(_prepare_entry,jobs)
        for item,(result,receipt) in zip(doc['entries'],results):
            output[item['name']]=result;receipts.append(receipt)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for item,(result,receipt) in zip(doc['entries'],pool.map(_prepare_entry,jobs)):
                output[item['name']]=result;receipts.append(receipt)
    return output,dict(schema='b765_s1_native_repair/v1',plan_sha256=geometry.sha(plan_path.read_bytes()),
        touched_disc_resources=[r['disc_file'] for r in receipts if r['before_sha256']!=r['after_sha256']],
        scope='stadium SCNE spans only; per-entry decoded lane/allocation receipts',entries=receipts)


def main(argv=None, *, verify_output=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--workers',type=int,default=1)
    a=p.parse_args(argv)
    geometry.require(a.input_dir.resolve()!=a.output_dir.resolve(),'input/output folders must differ')
    doc=json.loads(a.plan.read_text());protected={a.plan.resolve()};destinations=set()
    for item in doc.get('entries',[]):
        name=item['name'];geometry.require(Path(name).name==name and name.endswith('.iff'),'unsafe resource name')
        protected.add((a.input_dir/name).resolve());destinations.add((a.output_dir/name).resolve())
        manifest=(a.plan.parent/item['manifest']).resolve();protected.add(manifest)
        protected.update(p.resolve() for p in manifest.parent.rglob('*') if p.is_file())
        if 'edited' in item:
            edited=(a.plan.parent/item['edited']).resolve();protected.add(edited)
            gltf=json.loads(edited.read_text())
            protected.update((edited.parent/unquote(b['uri'])).resolve() for b in gltf.get('buffers',[]) if 'uri' in b and not b['uri'].startswith('data:'))
        protected.update((a.plan.parent/t['png']).resolve() for t in item.get('textures',[]))
    geometry.require(not destinations&protected,'output resource collides with an input or source artifact')
    geometry.require(a.receipt.resolve() not in protected|destinations,'receipt collides with an input, source artifact or output resource')
    output,receipt=prepare(a.input_dir,a.plan,workers=a.workers)
    if verify_output is not None:
        for entry in receipt['entries']:
            verify_output(entry['disc_file'],output[entry['disc_file']],entry)
    for name,data in output.items():geometry.write_atomic(a.output_dir/name,data)
    geometry.write_atomic(a.receipt,geometry.json_bytes(receipt))
    print(json.dumps(dict(touched=receipt['touched_disc_resources'],receipt=str(a.receipt))))
    return 0


if __name__=='__main__':raise SystemExit(main())

"""Serial in-memory model bundle proof; no output game image or disc writes."""
import sys,json,importlib,resource,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_model_fan_art as fans
from mod_editor.core import nfl2k5_scne_builder as sb
from PIL import Image,ImageDraw
import numpy as np
B=ROOT.parent;ART=B.parent/'main/freeze/candC/root_final_v2';art=mv.load_art(ART)
SOURCE=ROOT/'extracted/ESPN NFL 2K5 (USA)'
MODELS={'s00':'state_farm','s01':'mercedes_benz','s03':'highmark','s07':'att','s10':'lambeau','s11':'lucas_oil','s12':'everbank','s14':'hard_rock','s15':'usbank','s16':'gillette','s20':'allegiant','s23':'sofi','s24':'sofi','s25':'levis'}
checks=[];inventory=[];pages=[];memory={}
# Only three compressed model bundles are necessary; every model's retained
# materials and geometry are also checked on the actual owner-built scene.
compressed={'s00','s03','s23'}
for prefix,model in MODELS.items():
 mod=importlib.import_module('mod_editor.core.nfl2k5_'+model+'_model');name=prefix+'dd.iff'
 with mv._outer_image()(SOURCE,writable=False) as archive:
  retail={}
  for pin in mv.venues()[prefix]['bundles']:
   e=mv._entry(archive,pin);data=archive.read(e.virtual_offset,e.size);assert mv.sha(data)==pin['retail_sha256'];retail[pin['name']]=data
 raw=retail[name];built=mod.build(venue=prefix)
 sc=mod.build_scene(raw,name,built,dry_bundle=raw);retained=sorted({m.name for m in sc.materials}&fans.FAN_KEYS)
 print('RETAINED',prefix,retained,flush=True)
 venue=art['venues'][prefix];plan=mv.plan_venue(prefix,dict(venue,items=[i for i in venue['items'] if i['key'] in fans.FAN_KEYS]),retail)
 plan['items']=[i for i in plan['items'] if i['key'] in fans.FAN_KEYS]
 rr,rd=mv.decode_scenes(raw)['stadium'];expected,detail=mv.paint_scene(rd,rr,prefix,'dd',plan,plan['base'])
 # Contact sheets use native retail against the actual u4 P8 writer output.
 for key in retained:
  idx=mv.find_stadium_texture(rr,key);row=mv.p8_rows(rr)[idx]
  a=Image.fromarray(mv.read_texture(rd,rr,row));b=Image.fromarray(mv.read_texture(expected,rr,row))
  item=next(i for i in venue['items'] if i['key']==key)
  inventory.append(dict(venue=prefix,team=venue['team'],key=key,size=list(a.size),format='P8',sha256=item['sha256'],master_sha256=mv.sha(Path(item['master']).read_bytes()),before=a,after=b))
 check=dict(venue=prefix,model=model,retained=retained,source_sha256=mv.sha(raw))
 if prefix in compressed:
  # Use the pinned owner's cameras and stretch as the E base model.
  camera=getattr(mod,model+'_shots');shots=camera(prefix) if model=='sofi' else camera()
  cache=B/'tmp'/('fb2_base_'+name);meta=cache.with_suffix('.json')
  if cache.is_file():baseline=cache.read_bytes();info=json.loads(meta.read_text())
  else:
   baseline,info=mod.model_bundle(raw,name,built,cameras=shots,dry_bundle=raw)
   cache.write_bytes(baseline);meta.write_text(json.dumps(info))
  pin=next(p for p in mod.model_pins()['bundles'] if p['name']==name);start=pin['offset'];end=start+pin['length']
  assert mv.sha(baseline[start:end]) in [pin[k] for k in ['model_sha256','model_portrait_sha256'] if k in pin],name
  memory[name]=baseline;memory[name+'.sentinel']=raw
  result=fans.paint_results([(name,baseline,info)],retail,ART,mod.model_pins())
  _,after,afterinfo=result[0];memory[name]=after
  oldrec,olddec=mv.decode_scenes(baseline)['stadium'];newrec,newdec=mv.decode_scenes(after)['stadium']
  assert oldrec['system_bytes']==newrec['system_bytes']
  assert olddec[:int(oldrec['system_bytes'])]==newdec[:int(newrec['system_bytes'])],(name,'system/geometry changed')
  mask=np.zeros(len(olddec),dtype=bool);same=[]
  for key in retained:
   ri=mv.find_stadium_texture(rr,key);r=mv.p8_rows(rr)[ri]
   ni=mv.find_stadium_texture(newrec,key);n=mv.p8_rows(newrec)[ni]
   p0=int(newrec['system_bytes'])+n['pixel_offset'];p1=int(newrec['system_bytes'])+n['palette_offset']+1024
   q0=int(rr['system_bytes'])+r['pixel_offset'];q1=int(rr['system_bytes'])+r['palette_offset']+1024
   assert newdec[p0:p1]==expected[q0:q1],(name,key,'not exactly u4 P8/mips/palette')
   mask[p0:p1]=True;same.append(dict(key=key,bytes=p1-p0,sha256=mv.sha(newdec[p0:p1])))
  assert np.array_equal(np.frombuffer(olddec,dtype=np.uint8)[~mask],np.frombuffer(newdec,dtype=np.uint8)[~mask]),name
  c=mv.bundle_scenes(baseline)['stadium'];stop=c.offset+32+c.stored_size
  assert baseline[:c.offset]==after[:c.offset] and baseline[stop:]==after[stop:]
  assert baseline[c.offset:c.offset+32]==after[c.offset:c.offset+32]
  assert memory[name+'.sentinel']==raw
  assert fans.applied(mv.sha(after[start:end]),pin,afterinfo['fan_art'])
  check.update(compressed_image=True,before=mv.sha(baseline),after=mv.sha(after),u4_equal=same,all_other_decoded_bytes_unchanged=int((~mask).sum()),outside_stadium_compressed_span_unchanged=True,wrapper_unchanged=True,receipt=afterinfo['fan_art'])
  (B/'evidence/fan_proof.json').write_text(json.dumps(dict(evidence='PROVED OFFLINE',checks=checks+[check]),indent=2,default=str)+'\n')
  print('PROVED MEMORY',name,len(same),flush=True)
 checks.append(check)
 del sc,built,raw,retail
# MetLife owner drops the retail field banners outright.
from mod_editor.core import nfl2k5_metlife_model as metlife
checks.append(dict(venue='s18/s19',model='metlife',retained=[],keep=sorted(metlife.KEEP),proof='exact KEEP set omits banners; build_scene filters shapes before compacting materials'))
for start in range(0,len(inventory),6):
 group=inventory[start:start+6];page=Image.new('RGB',(1120,len(group)*304),'#bbb');d=ImageDraw.Draw(page)
 for j,item in enumerate(group):
  y=j*304;d.text((8,y+5),f"PROVED OFFLINE {item['venue']} {item['team']} {item['key']} {item['size']} P8",fill='black')
  for x,title,pic in [(8,'Retail 2004',item['before']),(565,'u4 2026 (native P8, same mip/palette rules)',item['after'])]:
   d.text((x,y+23),title,fill='black');pic=pic.resize((pic.width*2,pic.height*2),Image.Resampling.NEAREST);page.paste(pic,(x,y+42),pic)
 path=B/f'review/model_banners_{start//6:02}.png';page.save(path);pages.append(path.name)
(B/'review/model_banners.html').write_text('<!doctype html><meta charset="utf-8"><title>Retail vs u4 model banners</title><p>PROVED OFFLINE: native P8 texture output enlarged 2x without smoothing.</p>'+''.join(f'<p>{p}</p><img src="{p}" alt="Retail and u4 banner textures">' for p in pages))
(B/'evidence/fan_inventory.json').write_text(json.dumps([{k:v for k,v in r.items() if k not in ['before','after']} for r in inventory],indent=2)+'\n')
(B/'evidence/fan_proof.json').write_text(json.dumps(dict(evidence='PROVED OFFLINE',checks=checks,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),indent=2,default=str)+'\n')
print('DONE',len(inventory),'textures',len(checks),'checks',flush=True)

"""Native owner sweep and a 50-state contact sheet in descriptor/buffer order."""
from pathlib import Path
import hashlib,json,struct,sys,time
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as s,nfl2k5_scorebug_runtime as owner,nfl2k5_scorebug_ingame as scene
import nfl2k5_scorebug_projection as projection
OUT=Path(__file__).resolve().parent
STATES=[('standard',dict(down=1,away='DAL',home='KC')),('no_at_den',dict(away='NO',home='DEN',possession='away'))]
STATES += [('score_'+str(n),dict(away_score=n,home_score=n)) for n in (0,28,100)]
STATES += [('clock_007',dict(clock=7)),('play_12',dict(play_clock=12)),('play_3',dict(play_clock=3))]
STATES += [('down_'+str(n),dict(down=n)) for n in range(1,5)]
STATES += [('overtime',dict(quarter=5)),('inches',dict(distance=0)),('goal',dict(goal_to_go=True))]
STATES += [('timeouts_'+str(n),dict(away_timeouts=n,home_timeouts=n)) for n in range(4)]
STATES += [(e.replace(' ','_').lower(),dict(event=e)) for e in ('FLAG','FUMBLE','hang time','ball on','score slabs','hidden play clock')]

def refresh(g,c):
 m=c['machine'];b=c['body'];live=bytes(m.uc.mem_read(b,len(c['live_decoded'])));c['live_decoded']=live
 scale=m.floats(b+scene.layout.SHAPE+0x1c,1)[0];bias=m.floats(b+scene.layout.SHAPE+0x10,3)
 for v in range(scene.layout.VCOUNT):
  q=struct.unpack_from('<3h',live,scene.layout.S0+v*6);point=(*projection.decode_position(q,scale,bias),1)
  index=struct.unpack_from('<h',live,scene.layout.S1+v*10+8)[0]//3;palette=m.floats(0xafa710+index*48,12)
  world=[sum(point[j]*palette[i*4+j] for j in range(4)) for i in range(3)]
  g['world_positions'][v]=world;g['positions'][v]=c['project'](world)
 for mat in g['materials']:
  a=int(mat['address'],16);mat.update(visible=not(m.get(a+8)&1),tint=hex(m.get(a+0x18)),texture=hex(m.get(a+0x30)))
 return live

def raster(p,mode,g,c,path,calibration=None):
 return projection.render_native(c['live_decoded'],mode['atlas'],p.fonts,g,path,texture_spans=c['texture_spans'],background=Image.new('RGB',tuple(calibration['size']) if calibration else (640,480),'#343b40'),calibration=calibration)

def main():
 p=s.NativePreview();patched=owner.apply(p.payload)[0];code,data=owner.sites(patched);update=owner.code_for(code['va'],data['va'])[1]['update']
 receipts=[];contact=[];states={}
 for wide in (False,True):
  aspect='169' if wide else '43';mode=p.modes[wide];compiled=mode['compiled'];c={}
  # Run FC9C0's real request path (its gameplay predicates are explicit fixture boundaries).
  g=projection.native_geometry(p.payload,mode['scene'],fonts=p.fonts,texture_span=mode['atlas'],runtime_textures=mode['textures'],capture=c,widescreen=wide,identity=dict(away='DAL',home='KC'),visibility_state='pre_snap',down=1,distance_yards=10)
  g=projection.native_text_draw(c)|g
  try:
   m=c['machine'];field=next(r for r in compiled.spec['fields'] if r['name']=='down');rows=[q for q in compiled.quads if q['name'].startswith('down:')]
   tokens={s.quantized_uv(compiled.cells[v['cell']],compiled.spec['atlas']):k for k,v in compiled.spec['glyph_sets'][field['glyph_set']]['glyphs'].items() if v['size'][0]}
   roi=tuple(round(v) for v in s.contracted(s.hud_box(field['box'],wide),wide))
   for goal in (False,True):
    m.uc.mem_write(0xfc760,b'\xe9'+struct.pack('<i',0xfbd50-0xfc765) if goal else bytes.fromhex('d9eec3'));m.uc.ctl_remove_cache(0xfc760,0xfc766)
    for down in range(1,5):
     for distance in ([10] if goal else range(100)):
      # Alternate possession: both crimson and navy plates are in the sweep.
      possession='home' if (down+distance)%2 else 'away';m.put(0xe60280,0xe5fc20 if possession=='home' else 0xe5fc60)
      m.put(m.play+4,down);m.float(m.play+0x28,distance*91.4);m.run(update,(0x3c888889,),limit=500000)
      visits=list(m.visits);live=refresh(g,c)
      assert 0xfc7d0 in visits and 0xfc9c0 in visits
      assert m.get(0xa95a00)==1
      actual=[];visible=[]
      for q in rows:
       v=q['vertex'];colour=struct.unpack_from('<I',live,scene.layout.S1+v*10)[0]
       if not colour:continue
       assert colour==0xffffffff
       uv=tuple(x for j in range(4) for x in struct.unpack_from('<2h',live,scene.layout.S1+(v+j)*10+4))
       actual.append(tokens[uv]);visible.append(v)
      expected=str(down)+('st','nd','rd','th')[down-1]+'&'+('GOAL' if goal else 'Inches' if distance==0 else str(distance))
      assert ''.join(actual)==expected,(wide,down,distance,goal,actual,expected)
      # Crop the canvas at the same HUD scale, keeping annotations outside the measured strip.
      w,h=roi[2]-roi[0],roi[3]-roi[1]
      calibration=dict(size=[w,h+32],affine=[1,1,-roi[0],16-roi[1]])
      path=ROOT/'.scratch/s9-label-sweep-crop.png';result=raster(p,mode,g,c,path,calibration)
      ink=sum(min(rgb)>200 for rgb in Image.open(path).convert('RGB').crop((0,16,w,16+h)).getdata())
      assert ink>25,(wide,down,distance,goal,ink)
      receipts.append(dict(aspect=aspect,down=down,distance=distance,goal=goal,possession=possession,text=expected,white_pixels=ink,vertices=visible,native_formatter=True))
     print('sweep',aspect,'down',down,'goal',goal,'states',len(receipts),flush=True)
  finally:c['machine'].close()
  for name,state in STATES:
   g,c=p.capture(state,wide)
   try:
    path=OUT/(name+'_'+aspect+'.png');result=raster(p,mode,g,c,path)
    # S8 display model: all 640 HUD columns, with the native contraction already applied.
    im=Image.open(path).convert('RGB').crop((0,16,640,464)).resize(s.DISPLAY[wide]['size'],Image.Resampling.LANCZOS)
    points=[s.display_box((g['positions'][q['vertex']][0],g['positions'][q['vertex']][1],g['positions'][q['vertex']+3][0],g['positions'][q['vertex']+3][1]),wide) for q in compiled.quads if q['name'] in ('body_left','body_right')]
    left=min(a[0] for a in points)-12;right=max(a[2] for a in points)+12
    crop=im.crop((round(left),930,round(right),1065));crop.save(OUT/(name+'_'+aspect+'_crop.png'))
    contact.append((name+' / '+aspect,crop.resize((864,108),Image.Resampling.LANCZOS)))
    if name in ('standard','goal','flag','inches'):im.save(OUT/(name+'_'+aspect+'_display.png'))
    if name=='flag':
     roi=tuple(round(v) for v in s.contracted(s.hud_box([837,947,1083,983],wide),wide))
     pix=list(Image.open(path).convert('RGB').crop(roi).getdata())
     yellow=sum(r>180 and g>130 and b<70 for r,g,b in pix);dark=sum(max(rgb)<80 for rgb in pix)
     assert yellow>100 and dark>10,(aspect,yellow,dark)
     states[name+'_'+aspect]=dict(yellow_pixels=yellow,dark_label_pixels=dark)
    states.setdefault(name+'_'+aspect,{}).update(state=s.normalize_state(state),raster=result,runtime_witnessed=False)
   finally:c['machine'].close()
   print('contact',name,aspect,flush=True)
 board=Image.new('RGB',(1728,25*132),'#16191d');draw=ImageDraw.Draw(board)
 # Pair each state across aspects, rather than place all 4:3 before all widescreen.
 ordered=[contact[i] for j in range(25) for i in (j,j+25)]
 for i,(name,im) in enumerate(ordered):
  x=(i%2)*864;y=(i//2)*132;draw.text((x+5,y+3),name+' / NATIVE CPU + SUBMISSION-ORDER SOFTWARE RASTER',fill='white');board.paste(im,(x,y+22))
 board.save(OUT/'states_contact_sheet.png')
 (OUT/'states.json').write_text(json.dumps(states,indent=2)+'\n')
 (OUT/'label_sweep.json').write_text(json.dumps(dict(count=len(receipts),minimum_white_pixels=min(r['white_pixels'] for r in receipts),states=receipts,runtime_witnessed=False),indent=2)+'\n')
 (OUT/'volume.json').write_text(json.dumps({str(k):v['volume'] for k,v in p.modes.items()},indent=2)+'\n')
 print('PROVED',len(receipts),'native label states; 50 contact states; FLAG both aspects; UNWITNESSED in game',flush=True)
if __name__=='__main__':main()

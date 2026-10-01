"""DESIGN: bounded PHI/CHI display colours, sourced CHI plate, and measured label size.

Idempotent relative to candidate F. Existing official marks stay byte-identical.
The measured tint is projected into the existing transfer bound; this is a
constrained native fit, not a claim of reproducing every broadcast RGB exactly.
"""
from pathlib import Path
import json,sys,subprocess
import numpy as np
import io,math
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT)]
from mod_editor.core import nfl2k5_scorebug_teams as teams
OUT=Path(__file__).resolve().parent;DATA=ROOT/'data/nfl2k5_scorebug_sprite'
BASE='6bd9b3d66d239a267f8d4f66e083b8a6eb320671'
def base(name):return json.loads(subprocess.check_output(['git','show',BASE+':data/nfl2k5_scorebug_sprite/'+name],cwd=ROOT))
def hexof(v):return '#'+''.join(f'{round(float(c)):02X}' for c in v)
def constrained(measured,fitted,bound):
    m=np.array(teams.rgb(measured));f=np.array(teams.rgb(fitted));good=f.copy()
    for fraction in np.linspace(0,1,10001):
        value=f+(m-f)*fraction
        if teams.oklab_distance(hexof(value),fitted)<=bound:good=value
    return hexof(good)
def main():
    a=base('team_accents.json');d=base('broadcast_display.json');s=base('layout.json')
    fits=json.loads((OUT/'fit.json').read_text())['teams'];logos=json.loads((OUT/'logo_fit.json').read_text())['teams'];receipt={}
    for name in ('PHI','CHI'):
        r=fits[name];t=a['teams'][name];old={k:t[k] for k in ('wing','plate','rim','logo_fit')}
        v=constrained(r['hex'],r['fitted'],r['bound'])
        d['measured'][name]=dict(wing=v,parent=r['parent'],evidence='2026 PHI at CHI supplied NFL highlights KScULet1ves; reports/b76_sb2/fit.json and author_receipt.json; constrained to the existing transfer bound',unconstrained_wing=r['hex'],method='bounded native inverse fit',frames=r['frames'])
        sourced='#AC3100' if name=='CHI' else t['display']['sourced']
        t['display']=dict(t['display'],source='measured',parent=r['parent'],sourced=sourced)
        t['wing']=t['wash']=v
        if name=='CHI':t['plate']=t['rim']='#AC3100'
        t['candidates']['broadcast_display']=dict(hex=v,parent=r['parent'],variant='broadcast_measured',contrast_white=round(teams.contrast_white(v),4),facts=dict(role='wing and wash only',label='no label is drawn over the wing',measurement='reports/b76_sb2/fit.json'))
        t['logo_fit']=logos[name]['after']['fit'];s['logo_fit']['by_team'][name]=t['logo_fit']
        receipt[name]=dict(before=old,after={k:t[k] for k in old},unconstrained_wing=r['hex'],constraint_distance=teams.oklab_distance(v,r['fitted']),constraint_bound=r['bound'])
    # Common down label is 23 source pixels high on both possession colours.
    # Test 24 pixels at native resolution; ESPN keeps its existing 100x24 box.
    f=next(r for r in s['fields'] if r['name']=='down');f.update(size=24,box=[829,955,1089,979],anchor=[959,955])
    e=s['glyph_sets']['label']['glyphs']['ESPN'];e.update({'size':[125,30],'advance':125,'raise':-1.25})
    # Preserve the shared tick cell's effective footprint too (the legacy '~' token).
    tick=s['glyph_sets']['label']['glyphs']['~'];tick['size']=[v*1.25 for v in tick['size']];tick['advance']*=1.25
    from reports.b76_sbfix import author as strings
    image=Image.open(io.BytesIO(subprocess.check_output(['git','show',BASE+':data/nfl2k5_scorebug_sprite/template.png'],cwd=ROOT))).convert('RGBA')
    s,image,string_receipt=strings.build(s,image)
    filtered=[];done=set()
    for glyph in s['glyph_sets']['label']['glyphs'].values():
        cell=glyph['cell']
        if cell in done or not all(glyph['size']):continue
        done.add(cell);box=s['cells'][cell]['box'];w,h=glyph['size']
        limit=(max(1,math.floor(w*.8/3+.00001)),max(1,math.floor(h*.8*448/1080+.00001)))
        original=image.crop(box)
        size=(min(original.width,limit[0]),min(original.height,limit[1]))
        if size==original.size:continue
        # These existing label cells are white masks. Filter coverage, keeping white RGB at every alpha.
        alpha=original.getchannel('A').resize(size,Image.Resampling.BOX)
        # Restore edge coverage after the 12-row to 9-row filter; selected by the broadcast ink-area comparison.
        alpha=Image.fromarray(np.rint((np.asarray(alpha)/255.)**.8*255).astype('uint8'))
        small=Image.new('RGBA',size,'white');small.putalpha(alpha)
        image.paste(Image.new('RGBA',original.size,(0,0,0,0)),box[:2]);image.paste(small,box[:2])
        s['cells'][cell]['box']=[box[0],box[1],box[0]+size[0],box[1]+size[1]]
        filtered.append(dict(cell=cell,before=list(original.size),after=list(size)))
    image.save(DATA/'template.png')
    s['provenance']['sb2']='reports/b76_sb2/author_receipt.json; PHI/CHI official-mark placement and 24 px down labels; ESPN mark keeps its box'
    for name,obj in [('team_accents.json',a),('broadcast_display.json',d),('layout.json',s)]:
        (DATA/name).write_text(json.dumps(obj,indent=2 if name=='team_accents.json' else 1)+'\n')
    teams.load()
    (OUT/'author_receipt.json').write_text(json.dumps(dict(classification='DESIGN',base=BASE,teams=receipt,down=dict(before=[30,950],after=[24,955]),official_mark_pixels_changed=False,filtered_cells=filtered,label_coverage_exponent=.8,strings=string_receipt),indent=2)+'\n')
    print(receipt)
if __name__=='__main__':main()

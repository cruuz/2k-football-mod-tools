"""Read-only check of the supplied disc-o patch against this compiler."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys
import zipfile
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_scorebug_resources as art
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
from PIL import Image
import nfl2k5_scorebug_projection as projection

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patch',type=Path,required=True)
    args=parser.parse_args()
    patch=args.patch
    p = sprite.NativePreview()
    with zipfile.ZipFile(patch) as z:
        payload = z.read('operations/file-0001.bin')
        with z.open('operations/file-0000.bin') as f:
            f.seek(art.HUD_START + art.HUD_SIZE)
            data = f.read(p.modes[True]['volume']['appended_bytes'])
    chunks = [data[c.offset:c.end_offset] for c in scene.tx.parse_chunks(data)]
    report = {'patch':patch.name, 'components': [], 'states':[]}
    expected = p.modes[True]['volume']['components']
    report['components'] = [dict(name=e['name'], equal=hashlib.sha256(c).hexdigest()==e['sha256'], sha256=hashlib.sha256(c).hexdigest()) for c,e in zip(chunks,expected)]
    (ROOT/'reports/b72_s3/disc_probe.json').write_text(json.dumps(report,indent=2)+'\n')
    print('All appended components match:', all(r['equal'] for r in report['components']), flush=True)
    validator=projection.validate_native_code
    def installed_validator(data):
        assert runtime.status(data)=='applied'
        check=bytearray(data)
        for va,original in projection.STATIC_CALLS:
            at=scene.layout.sbpos.va_to_off(data,va)
            check[at:at+len(original)]=original
        return validator(bytes(check))
    projection.validate_native_code=installed_validator
    p.payload = payload
    p.modes[True].update(scene=scene.decode(chunks[-1])[1], atlas=chunks[-2], textures=chunks[:-1])
    for possession in ('home','away'):
        state=dict(away='DET',home='LV',possession=possession,clock=300,quarter=1,down=2)
        g,c=p.capture(state,True)
        try:
            out=ROOT/'reports/b72_s3'/('disc_'+possession+'.png')
            raster=projection.render_native(c['live_decoded'],chunks[-2],p.fonts,g,out,texture_spans=c['texture_spans'],background=Image.new('RGB',(640,480),'#303030'))
            Image.open(out).crop((0,16,640,464)).resize((1920,1080)).save(out.with_name(out.stem+'_display.png'))
            report['states'].append(dict(state=state,materials=g['materials'],raster=raster))
        finally:c['machine'].close()
    (ROOT/'reports/b72_s3/disc_probe.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'components':report['components']}),flush=True)

if __name__=='__main__':main()

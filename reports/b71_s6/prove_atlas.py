"""Decode the appended P8 resource exactly as the shared native raster does."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from PIL import Image
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_scorebug_ingame as scene
p=sprite.NativePreview()
chunk,body,_=scene.decode(p.atlas)
tex=scene.tx.parse_texture(body,chunk)
Image.frombytes('RGBA',(tex.width,tex.height),scene.tx.texture_to_rgba(body,chunk,tex)).save(ROOT/'reports/b71_s6/atlas.png')
print(json.dumps(dict(width=tex.width,height=tex.height,bytes=len(p.atlas),source='actual appended P8 decoded by shared raster')))

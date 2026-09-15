from pathlib import Path
import hashlib,json,struct
from mod_editor.core.apf2k8_xex import decode_xex,reconstruct_tu
from mod_editor.core import apf2k8_situation_mask as m
source=Path('/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/default.xex').read_bytes()
base=decode_xex(source)[0];tu=reconstruct_tu(base,source,Path('/home/noah/Downloads/uranus/TU_1A58207_0000008000000.0000000000082').read_bytes())[0]
policies={'O-ManBlock':[[] for _ in range(12)]};policies['O-ManBlock'][8]=[14]
rows=[]
for image in (base,tu):
 patch=m.compile_patch(image,policies);data=bytearray(image)
 for address,value in patch.words:struct.pack_into('>I',data,address-m.IMAGE_BASE,value)
 rows.append({'profile':patch.profile.name,'flat_sha256':hashlib.sha256(data).hexdigest(),'code':patch.receipt['code']})
print(json.dumps(rows,indent=2))
Path('reports/b71_apf4/final_byte_pins.json').write_bytes((json.dumps(rows,indent=2)+'\n').encode())

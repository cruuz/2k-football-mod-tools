"""Metadata-only jersey digit UV census from the user's retail player meshes."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from tools.b70_t2_stadium_probe import CACHE, RETAIL
from mod_editor.core import nfl2k5_models as m
from nfl_scne_gltf import decode_batches


def main():
    source = m.ModelSource(RETAIL/'vc_53450030/0', CACHE/'indexes/nfl2k5_resource_chunks_v2.json')
    result = []
    for key in ('o3c114', 'o3c113'):
        resource, decoded, scene = source.parse(key)
        shapes = {s['index']:s for s in scene['shapes']}
        rows = []
        for submesh in scene['submeshes']:
            if not any(name in submesh['material_name'] for name in ('NUMBER_shoulder', 'NUMBER_sleeve')):
                continue
            shape = shapes[submesh['shape_index']]
            lanes = m._shape_lanes(scene,shape,decoded)
            pairs = m.read_lane_2h(decoded,shape,lanes.texcoord,lanes.vertex_count)
            ids = sorted({i for _, batch in decode_batches(decoded,submesh['command_offset'],submesh['primary_command_word_count']) for i in batch})
            uvs = [m.uv_to_gltf(*pairs[i],lanes.uv_scale,lanes.uv_offset) for i in ids]
            rows.append(dict(material=submesh['material_name'],material_index=submesh['material_index'],
                submesh_index=submesh['submesh_index'],vertex_count=len(ids),
                uv_min=[min(v[a] for v in uvs) for a in (0,1)],uv_max=[max(v[a] for v in uvs) for a in (0,1)],
                uv_stream=lanes.texcoord[0],uv_byte_offset=lanes.texcoord[1],uv_stride=lanes.texcoord[2],
                uv_scale=lanes.uv_scale,uv_offset=lanes.uv_offset,shape_record=lanes.record_offset))
        result.append(dict(key=key,scene=scene['name'],decoded_sha256=hashlib.sha256(decoded).hexdigest(),
                           shape_count=len(shapes),digit_surfaces=rows,in_game_outcome='UNWITNESSED'))
    (ROOT/'reports/b70_t2/arm-uv.json').write_text(json.dumps(result,indent=2)+'\n')
    print([(r['key'],len(r['digit_surfaces'])) for r in result])


if __name__ == '__main__':
    main()

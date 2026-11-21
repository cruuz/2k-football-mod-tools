"""Build the shipped Modern-helmets head scene (o3c115) from the retail disc and dump the helmet C parts."""
import sys, json, struct
from pathlib import Path
import numpy as np
WT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(WT)); sys.path.insert(0, str(WT/'tools'))
from mod_editor.core import nfl2k5_modern_helmets as mh, nfl2k5_models as models
from nfl_outer import parse_archive, read_entry_range
INDEX = Path(__import__('os').environ.get('NFL2K5_RETAIL_INDEX', '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))
arch = parse_archive(INDEX)
entry = arch.entries[3]
payload = read_entry_range(arch, entry, 0, entry.size)
chunks = mh._chunks(payload)
out = {}
for mode in ('retail', 'modern'):
    key = mh.HI
    _o, index = models.parse_model_key(key)
    span = mh._chunk_span(payload, chunks[index])
    if mode == 'modern':
        span, rec = mh.compile_scene(key, span, mh.load_geometry(), mh.load_pins())
        print(rec['state'])
    src = models.ModelSpanSource({key: span})
    dest = Path(f'head_{mode}/hi_head_o3c115.gltf'); dest.parent.mkdir(exist_ok=True)
    res = models.export_model(src, key, dest, include_textures=True)
    print(mode, res)

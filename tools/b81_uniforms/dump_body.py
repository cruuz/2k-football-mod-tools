"""Export the retail hi_body (o3c114) and copy-free reference to the modern head export of b81-art."""
import sys
from pathlib import Path
WT = Path('/home/noah/2k-worktrees/b81-uniforms'); sys.path.insert(0, str(WT)); sys.path.insert(0, str(WT/'tools'))
from mod_editor.core import nfl2k5_modern_helmets as mh, nfl2k5_models as models
from nfl_outer import parse_archive, read_entry_range
INDEX = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0')
arch = parse_archive(INDEX)
entry = arch.entries[3]
payload = read_entry_range(arch, entry, 0, entry.size)
chunks = mh._chunks(payload)
for key in ('o3c114',):
    _o, index = models.parse_model_key(key)
    span = mh._chunk_span(payload, chunks[index])
    src = models.ModelSpanSource({key: span})
    dest = Path(sys.argv[1]) / f'hi_body_{key}.gltf'
    print(models.export_model(src, key, dest, include_textures=True))

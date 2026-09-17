"""Exercise spawned fit workers on real read-only spans, without a disc copy."""
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
from tools import nfl2k5_visual_mod_project as backend


def run():
    index = ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
    targets, _ = writer.load_targets()
    selected = [t for t in targets.values() if t.set_selector in ('22H2','30H0')
                and t.name in ('socks00','socks00_mud')]
    assert len(selected) == 4
    with tempfile.TemporaryDirectory(prefix='b71-t5-parallel-') as temporary:
        root = Path(temporary)
        edits, groups = [], {}
        for n, target in enumerate(selected):
            rgba = bytes((18+n*3, 90+n*5, 160+n*7, 255)) * (target.width*target.height)
            path = root/f'{n}.png'
            path.write_bytes(with_import_mode(writer.encode_rgba_png(target.width,target.height,rgba),
                                             target.asset_id,rgba,independent=True,scale=4))
            edit=dict(kind='uniform_equipment_texture',asset_id=target.asset_id,png=str(path))
            edits.append(edit)
            groups.setdefault((target.outer_index,target.chunk_index),[]).append(edit)
        project_path=root/'project.json'
        project_path.write_bytes(backend.canonical_json(dict(schema=backend.SCHEMA,purpose='T5 parallel fit proof',edits=edits)))
        project=backend.read_project(project_path)
        pins=backend.pin_project_inputs(project)
        cache=writer.EquipmentCompileCache()
        started=time.monotonic()
        backend._parallel_equipment_fits(groups,project,pins,index,cache,2)
        seconds=time.monotonic()-started
        assert len(cache.compiled) == 2
        from unittest.mock import patch
        with patch.object(writer,'_compile_group',side_effect=AssertionError('worker result recompressed')):
            for rows in groups.values():
                writer.build_unified_uniform_equipment_imports(index,
                    [(r['asset_id'],Path(r['png'])) for r in rows],compile_cache=cache,preflight_only=True)
        print(json.dumps(dict(seconds=seconds,workers=2,groups=2,replacements=4,
            cache_hits=cache.hits,output_disc_written=False,in_game='UNWITNESSED')),flush=True)


if __name__ == '__main__':
    run()

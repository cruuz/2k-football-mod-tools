#!/usr/bin/env python3
"""Verify a complete ur1 corpus against read-only disc inputs and native pins."""
import argparse
from collections import Counter
import json
from pathlib import Path

from PIL import Image
from ur1_compare import OuterImage, logical_name_candidates, load_provenance, sha, write_json
from nfl_uniform_inventory import FIRST_OUTER, LAST_OUTER, UNIF_COUNT, TSET_REFS_PER_PACKAGE, TXTR_PER_PACKAGE


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--public', type=Path, required=True)
    p.add_argument('--current', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    out = a.out.resolve()
    report = json.loads((out/'compare.json').read_text())
    renders = json.loads((out/'render_receipt.json').read_text())
    candidates = logical_name_candidates()
    provenance = load_provenance()
    counts = Counter()
    owners = Counter()
    render_hashes = {}
    rows = {r['selector']:r for r in report['kits']}
    with OuterImage(a.public) as before, OuterImage(a.current) as after:
        maps = [{candidates[e.name_id].name.removesuffix('.IFF'):e
                 for e in img.entries if e.name_id in candidates} for img in (before,after)]
        assert maps[0].keys() == maps[1].keys() == rows.keys() == renders.keys(), 'inventory incomplete'
        for entries in maps:
            # Modified images can append kits after the original 634 packages.
            assert len(entries) >= UNIF_COUNT
            assert set(range(FIRST_OUTER,LAST_OUTER+1)) <= {e.index for e in entries.values()}
        for sel,row in rows.items():
            raw_sides = []
            docs = []
            for tag,img,entries in zip(('public','current'),(before,after),maps):
                entry = entries[sel]
                raw = img.read(entry.virtual_offset,entry.size)
                doc = json.loads((out/'extracts'/tag/sel/'manifest.json').read_text())
                assert sha(raw) == doc['resource_sha256'], (tag,sel,'resource hash')
                assert len(doc['chunks']) == 53, (tag,sel,'chunk count')
                assert len(doc['assets']) == TSET_REFS_PER_PACKAGE+TXTR_PER_PACKAGE
                for c in doc['chunks']:
                    assert sha(raw[c['offset']:c['offset']+c['length']]) == c['span_sha256'], (tag,sel,c['chunk'])
                for asset in doc['assets']:
                    if 'png' in asset:
                        with Image.open(asset['png']) as im:
                            assert im.size == (asset['width'],asset['height'])
                            assert sha(im.convert('RGBA').tobytes()) == asset['rgba_sha256']
                        counts['native_pngs_verified'] += 1
                raw_sides.append(raw)
                docs.append(doc)
                counts['resources_readback_verified'] += 1
                counts['chunks_readback_verified'] += len(doc['chunks'])
            assert len(docs[0]['assets']) == len(docs[1]['assets'])
            actual = [x['chunk'] for x,y in zip(docs[0]['chunks'],docs[1]['chunks'])
                      if x['decoded_sha256'] != y['decoded_sha256']]
            assert actual == [c['chunk'] for c in row['changes']], (sel,'diff inventory')
            for change in row['changes']:
                pp = provenance.get((sel,change['chunk']),[])
                matches = []
                for pin in pp:
                    b = raw_sides[1][pin['offset']:pin['offset']+pin['length']]
                    if sha(b) == pin['after_sha256']:
                        matches.append(pin['job'])
                assert matches, (sel,change['chunk'],'unattributed or output pin mismatch')
                owners[matches[-1]] += 1
                change['provenance'] = [{k:r.get(k) for k in
                    ('job','file','note','defects','before_sha256','after_sha256','pin_scope')} for r in pp]
                change['output_pin_match'] = True
                change['verified_output_owner'] = matches[-1]
                counts['changed_chunks_pinned'] += 1
            assert renders[sel]['renderer_version'] == 2
            for sheet in (row['sheet'],renders[sel]['sheet']):
                with Image.open(sheet) as im:
                    im.verify()
                counts['sheets_verified'] += 1
            for side in renders[sel]['paths']:
                assert len(side) == 7
                for path in side.values():
                    assert Path(path).is_file(), path
                    if path not in render_hashes:
                        with Image.open(path) as im:
                            im.verify()
                        render_hashes[path] = sha(Path(path).read_bytes())
            counts['kits_verified'] += 1
    result = dict(counts, changed_chunk_owners=dict(owners), unknown_changed_chunks=0,
                  unique_model_images_verified=len(render_hashes),
                  inventory_exact=True, input_mode='read-only')
    write_json(out/'render_hashes.json',render_hashes)
    write_json(out/'compare.json',report)
    write_json(out/'audit.json',result)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()

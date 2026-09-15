"""Revalidate unchanged reservations for current colour/scorebug writes, scratch only.

Historical disc fields remain historical. Resource/build helper fingerprints are
snapshots only; this projection does not claim a new disc or release manifest.
"""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_cave_manifest as cm
from mod_editor.core import nfl2k5_modern_color as colour, nfl2k5_scorebug_runtime as runtime, nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import ReservationManifest, XbeImage, RETAIL_SHA256
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

SOURCE=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe')
ALLOWED={
 'mod_editor/core/mod_build.py':'Build dispatcher snapshot; project/publication suites, not a disc build',
 'mod_editor/core/nfl2k5_modern_color.py':'Observed XBE writer; exhaustive 477 bundle proof separately',
 'mod_editor/core/nfl2k5_scorebug_exact.py':'Inherited A5 scorebug helper used by observed runtime; no independent resource-build claim',
 'mod_editor/core/nfl2k5_scorebug_resources.py':'Inherited A5 resource helper used by observed runtime; no resource-build claim',
 'mod_editor/core/nfl2k5_scorebug_runtime.py':'Observed XBE writer; same declared requests and covered writes',
}


def main():
    retail=SOURCE.read_bytes()
    assert colour.sha(retail)==RETAIL_SHA256
    parent=(ROOT/'data/nfl2k5_cave_reservations.json').read_bytes()
    doc=json.loads(parent)
    pins=cm.source_fingerprints()
    changed={p for p,v in doc['source_sha256'].items() if pins.get(p)!=v}
    assert changed==set(ALLOWED), sorted(changed)
    manifest=ReservationManifest(doc,XbeImage(retail))
    owned=doc['allocator_layout']['allocations']
    requested=[(a['owner'],a['kind'],a['size'],a['align']) for a in owned
               if a['owner'] not in (space.OWNER,space.DIRECTORY_OWNER,'nfl2k5_music_metadata')]
    actual_runtime={r for r in requested if r[0]==runtime.OWNER}
    assert actual_runtime==set(runtime.REQUESTS), 'runtime request changed'
    allocated=space.apply(retail,requested)[0]
    actual=space.layout(allocated)['allocations']
    for owner in (runtime.OWNER,):
        assert [a for a in owned if a['owner']==owner]==[a for a in actual if a['owner']==owner]
    recorder=cm.Recorder(retail)
    current=allocated
    for module,writer,status in ((runtime.scene,runtime.scene.apply_xbe,runtime.scene.xbe_status),
                                 (runtime,runtime.apply,runtime.status),(colour,colour.apply,colour.status)):
        after,receipt=writer(current)
        assert status(after)=='applied'
        assert writer(after)[0]==after
        recorder.observe(module,'apply: bounded unchanged-reservation revalidation',current,after,receipt)
        current=after
    # Every new observed span is already reserved to its owner. Header digest
    # writes may coincide with other owners, as in the historical manifest.
    assert space.status(current)=='applied'  # Verifies allocator directory and code hashes.
    directory_hash=0x10000+space.DIRECTORY+len(space.SCALE_TAG)+8
    digest_ranges=[(directory_hash,directory_hash+32)]
    for section in _sections(current):
        assert section.stored_digest==section_digest(current,section)
        digest_ranges.append((0x10000+section.header_offset+36,0x10000+section.header_offset+56))
    for row in recorder.spans:
        lo,hi=int(row['start'],0),int(row['end'],0)
        if any(a<=lo<hi<=b for a,b in digest_ranges):
            continue  # Verified section SHA-1 / allocator directory SHA-256 metadata.
        ranges=sorted((int(s['start'],0),int(s['end'],0)) for s in doc['spans'] if s['owner']==row['owner'])
        cursor=lo
        for a,b in ranges:
            if a<=cursor<b:cursor=b
        assert cursor>=hi,(row,'write exceeds historical ownership')
    summary=dict(release_manifest=False,disc_built=False,parent_disc_fields_are_historical=True,
                 parent_manifest_sha256=colour.sha(parent),changed_sources=sorted(changed),
                 snapshot_scope=ALLOWED,observed_steps=recorder.steps,observed_span_count=len(recorder.spans),
                 reservations_unchanged=True,section_digests_verified=True,production_regeneration_required=True)
    doc['source_sha256'].update({p:pins[p] for p in changed})
    doc['b71_c4_projection']=summary
    doc['model']='BOUNDED C4 PROJECTION: historical reservations plus current colour/scorebug coverage revalidation; no new disc build'
    # Keep the existing layout, reservations, observed historical steps and
    # historical disc digests intact; attach current observations separately.
    ReservationManifest(doc,XbeImage(retail),source_root=ROOT)
    output=ROOT/'.scratch/b71_c4_manifest.json'
    output.write_text(json.dumps(doc,indent=2)+'\n')
    summary['projection_sha256']=colour.sha(output.read_bytes())
    (ROOT/'reports/b71_c4/manifest-projection.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    main()

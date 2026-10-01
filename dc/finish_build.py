"""PROVED OFFLINE: verify the complete task disc, retain proof, delete the disc."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dc.import_depth import OUT,sha,rr
from dc.native_probe import run as native
from dc.lineup_probe import run as lineups
from mod_editor.core import mod_build,nfl2k5_depth_locks as locks,nfl2k5_returner_fix as fix,nfl2k5_depth_roles as roles

def main():
    disc=OUT/'candidate_C_dc.xiso.iso'
    assert disc.is_file() and not disc.is_symlink() and disc.resolve().parent==OUT.resolve()
    build_path=disc.with_suffix('.build.json');summary_path=disc.with_suffix('.summary.json')
    build=json.loads(build_path.read_text());summary=json.loads(summary_path.read_text())
    assert Path(build['result']['target']).resolve()==disc.resolve()
    assert not summary['not_applied']
    xbe=mod_build._xbe_bytes(disc)
    assert locks.status(xbe)==fix.status(xbe)=='applied'
    assert build['result']['plan']['depth_locks'] and build['result']['plan']['returner_fix']
    with rr._outer_image()(disc) as archive:
        entry=rr._entry(archive)
        body=archive.read(entry.virtual_offset,entry.size)[rr.RESOURCE_HEADER_SIZE:]
    reapplied,receipt=rr.apply_body(body,ROOT/'dc/special_depth_fragment.json')
    assert not receipt['log'] and reapplied==body
    (OUT/'final_default.xbe').write_bytes(xbe)
    (OUT/'final_roster.rost').write_bytes(body)
    native(xbe,body,ROOT/'dc/proof/final_native.json')
    formation_receipt=lineups(xbe,body,roles._resources(disc),ROOT/'dc/proof/final_lineups.json')
    with disc.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    assert build['result']['outcome']['output']=={'sha256':digest,'size':disc.stat().st_size}
    result={'evidence':'PROVED OFFLINE','disc_sha256':digest,'disc_bytes':disc.stat().st_size,
            'xbe_sha256':sha(xbe),'roster_sha256':sha(body),'build_seconds':build['seconds'],
            'build_receipt_sha256':sha(build_path.read_bytes()),'summary_receipt_sha256':sha(summary_path.read_bytes()),
            'depth_locks':locks.status(xbe),'returner_fix':fix.status(xbe),'fragment_replay':receipt,
            'final_native_teams':32,'final_native_full_formations':formation_receipt['formation_count'],
            'summary':summary,'runtime_witnessed':False,'disc_deleted':False}
    path=ROOT/'dc/proof/full_build.json';path.write_text(json.dumps(result,indent=2)+'\n')
    disc.unlink()
    result['disc_deleted']=not disc.exists();result['storage_free_after_delete']=shutil.disk_usage(OUT).free
    path.write_text(json.dumps(result,indent=2)+'\n')
    print('PROVED OFFLINE: FULL C build verified and task disc deleted',flush=True)
if __name__=='__main__':main()

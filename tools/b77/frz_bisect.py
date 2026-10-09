#!/usr/bin/env python3
"""Prepare FRZ bisect recipes, optionally repair a NEW copy of the v0.5 disc.

Preparation writes one 12 MB diagnostic executable and a manifest. It never
builds a disc. --output-image explicitly requests a disc copy for later testing.
All source images are opened read only. Fixed-size XDVDFS and outer layouts must
match exactly, so no repack, emulator, Wine or runtime dependency is required.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
import nfl_uniform_color_xiso_direct_patch as xiso
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_cpu_money_downs as cpu
from mod_editor.core import nfl2k5_punter_holder as holder
from mod_editor.core import nfl2k5_moment_gun_weight as gun
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

V05_HASH = '2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab'
V06_HASH = 'b4fec92f4c03d129687405c406d9882387b731615d71eb4cca3a447304e74f30'
VARIANTS = {
    'A': 'v0.5 plus v0.6 main roster/depth and 32 team books. Code and art from v0.5.',
    'B': 'v0.5 plus complete v0.6 executable. All data and art from v0.5.',
    'C': 'v0.5 plus v0.6 executable with a4/a4pd, p9, g2 and h1 restored to v0.5. Data and art from v0.5.',
    'D': 'v0.5 plus all v0.6 pack files. Executable from v0.5.',
    'E': 'Complete v0.6 bytes over v0.5, except players SPCI cue table restored to v0.5. Tests the c2 cue retirement.',
    'F': 'Complete v0.6 bytes over v0.5, except all team kit packages and GLOBAL.IFF restored to v0.5. Tests player art, kitx, eqx, sh1 and wet kit palettes.',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def revert_primary(before, final):
    """Diagnostic rollback only. Existing allocator placement is retained."""
    if sha(before) != V05_HASH or sha(final) != V06_HASH:
        raise ValueError('expected the exact shipped v0.5 and final v0.6 executables')
    old_image, new_image = XbeImage(before), XbeImage(final)
    old_layout = {a['owner']:a for a in space.layout(before)['allocations'] if a['kind']=='code'}
    new_layout = {a['owner']:a for a in space.layout(final)['allocations'] if a['kind']=='code'}
    _, _, requests = space._validate(final)
    buf = bytearray(final)
    ranges = []
    def restore(va,size,label):
        off = new_image.offset(va,size)
        buf[off:off+size] = old_image.read(va,size)
        ranges.append(dict(label=label,va=hex(va),size=size,file_offset=off))
    for owner in (abilities.OWNER,cpu.OWNER,'nfl2k5_stock_books'):
        old,new = old_layout[owner],new_layout[owner]
        if (old['va'],old['size']) != (new['va'],new['size']):
            raise ValueError(f'allocator moved {owner}')
        restore(new['va'],new['size'],owner)
    for name,(va,raw) in abilities.HOOKS.items():
        restore(va,len(raw),'g2/'+name)
    for name,(va,raw) in cpu.HOOKS2.items():
        restore(va,len(raw),'p9/'+name)
    restore(gun.SITE_VA,len(gun.RETAIL_SITE),'a4/shotgun_weight')
    for name,va,raw,after in holder.sites():
        restore(va,len(raw),'h1/'+name)
    space._seal_scaleout(buf,requests)
    for section in _sections(buf):
        buf[section.header_offset+36:section.header_offset+56] = section_digest(buf,section)
    result = bytes(buf)
    if space.status(result) != 'applied':
        raise ValueError('diagnostic allocator seals failed')
    for module in (abilities,cpu,holder):
        if module.status(result) != module.status(before):
            raise ValueError(f'diagnostic rollback failed recognition for {module.OWNER}')
    restored = bytearray(result)
    scope = [(r['file_offset'],r['size']) for r in ranges]
    scope += [(section.header_offset+36,20) for section in _sections(result)]
    scope += [(space.DIRECTORY,space.LIB_COPY-space.DIRECTORY),(space.SCALE_DIRECTORY,space.PAGE)]
    for offset,size in scope:
        restored[offset:offset+size] = final[offset:offset+size]
    if bytes(restored) != final:
        raise ValueError('rollback changed undeclared bytes')
    return result,dict(sha256=sha(result),ranges=ranges,outside_scope_identical=True,
        owners={m.OWNER:m.status(result) for m in (abilities,cpu,holder)},
        allocator=space.status(result),runtime_witness=False)


def read_xbe(source,path):
    files,_ = xiso.parse_xdvdfs(source._fd,path.stat().st_size)
    file = files['default.xbe']
    return os.pread(source._fd,file.size,file.byte_offset),files


def check_room(parent,required):
    free = shutil.disk_usage(parent).free
    floor = 50*1024**3 if parent.stat().st_dev == Path('/').stat().st_dev else 0
    if free-required < floor:
        raise ValueError('insufficient output space; would cross the 50 GiB root floor')


def stream_write(source_fd,target_fd,source_offset,target_offset,size):
    h = hashlib.sha256()
    for offset in range(0,size,4*1024**2):
        wanted = min(4*1024**2,size-offset)
        raw = os.pread(source_fd,wanted,source_offset+offset)
        if len(raw) != wanted:
            raise ValueError('short source read')
        if os.pwrite(target_fd,raw,target_offset+offset) != len(raw):
            raise ValueError('short output write')
        h.update(raw)
    return h.hexdigest()


def prepare(v05,v06,out):
    out.mkdir(parents=True,exist_ok=True)
    check_room(out,13*1024**2)
    with OuterImage(v05) as old,OuterImage(v06) as new:
        before,old_files = read_xbe(old,v05)
        final,new_files = read_xbe(new,v06)
        if old.entries != new.entries:
            raise ValueError('outer archive layouts differ')
        if set(old_files) != set(new_files) or any(
            (v.size,v.byte_offset)!=(new_files[k].size,new_files[k].byte_offset)
            for k,v in old_files.items()):
            raise ValueError('XDVDFS layouts differ')
        rollback,receipt = revert_primary(before,final)
        path = out/'C.default.xbe'
        if path.exists() and path.read_bytes() != rollback:
            raise ValueError('refusing different existing output')
        path.write_bytes(rollback)
        from mod_editor.core import nfl2k5_commentary_final as c2
        from mod_editor.core.nfl2k5_bump_texture_writer import logical_name_for
        old_entry,new_entry = old.read_entry(3),new.read_entry(3)
        at,new_at = c2.find_table(old_entry),c2.find_table(new_entry)
        before_table = old_entry[at:at+c2.SPCI_SIZE]
        final_table = new_entry[new_at:new_at+c2.SPCI_SIZE]
        if at != new_at or c2.patch_table(before_table)[0] != final_table:
            raise ValueError('SPCI rollback is not the expected one-byte c2 edit')
        cue_offset = old.image_offset(old.entries[3].virtual_offset+at+c2.EXPECTED_ID_OFFSET)
        kit_resources = [dict(name=logical_name_for(e.name_id),entry=e.index,size=e.size)
                         for e in old.entries if logical_name_for(e.name_id) is not None]
        plan = dict(schema='b77/frz-bisect/v1',v05=str(v05),v06=str(v06),variants=VARIANTS,
            xbe_before_sha256=sha(before),xbe_final_sha256=sha(final),rollback=receipt,
            layouts_identical=True,output_image_created=False,
            E=dict(image_offset=cue_offset,before_final='ef',after_rollback='8c',changed_bytes=1),
            F=dict(resources=kit_resources,count=len(kit_resources),
                   restoration='whole kit packages and GLOBAL.IFF from v0.5'))
        (out/'bisect.json').write_text(json.dumps(plan,indent=1)+'\n')
        return plan


def repair_disc(v05,v06,prepared,variant,output):
    if output.exists():
        raise ValueError('refusing existing output image')
    check_room(output.parent,v05.stat().st_size)
    plan = prepare(v05,v06,prepared)
    shutil.copyfile(v05,output)
    rows = []
    with OuterImage(v05) as old,OuterImage(v06) as new:
        _,files = read_xbe(old,v05)
        _,new_files = read_xbe(new,v06)
        fd = os.open(output,os.O_RDWR)
        try:
            if variant == 'A':
                indices = [5]+[BOOK_ENTRIES[key] for key in books_keys()]
                for index in indices:
                    entry = old.entries[index]
                    source_offset = new.image_offset(entry.virtual_offset)
                    target_offset = old.image_offset(entry.virtual_offset)
                    digest = stream_write(new._fd,fd,source_offset,target_offset,entry.size)
                    rows.append(dict(entry=index,size=entry.size,sha256=digest))
            elif variant in ('B','C'):
                file = files['default.xbe']
                raw = (prepared/'C.default.xbe').read_bytes() if variant=='C' else read_xbe(new,v06)[0]
                if len(raw) != file.size:
                    raise ValueError('XBE size differs')
                os.pwrite(fd,raw,file.byte_offset)
                rows.append(dict(file='default.xbe',sha256=sha(raw),size=len(raw)))
            elif variant == 'D':
                for name,file in files.items():
                    if not name.startswith('vc_53450030/'):
                        continue
                    digest = stream_write(new._fd,fd,new_files[name].byte_offset,file.byte_offset,file.size)
                    rows.append(dict(file=name,sha256=digest,size=file.size))
            else:
                # E/F retain the final code/data interaction. Start with the
                # requested v0.5 copy, overlay every same-layout v0.6 file,
                # then drop the single candidate layer. No repack/build.
                for name,file in files.items():
                    digest = stream_write(new._fd,fd,new_files[name].byte_offset,file.byte_offset,file.size)
                    rows.append(dict(file=name,sha256=digest,size=file.size))
                if variant == 'E':
                    from mod_editor.core import nfl2k5_commentary_final as c2
                    old_entry,new_entry = old.read_entry(3),new.read_entry(3)
                    at,new_at = c2.find_table(old_entry),c2.find_table(new_entry)
                    before = old_entry[at:at+c2.SPCI_SIZE]
                    final = new_entry[new_at:new_at+c2.SPCI_SIZE]
                    if c2.table_status(before) != 'retail' or c2.table_status(final) != 'applied' or at != new_at:
                        raise ValueError('unexpected commentary cue tables')
                    if c2.patch_table(before)[0] != final:
                        raise ValueError('commentary rollback is not the one-byte c2 edit')
                    offset = old.image_offset(old.entries[3].virtual_offset+at+c2.EXPECTED_ID_OFFSET)
                    restored = before[c2.EXPECTED_ID_OFFSET:c2.EXPECTED_ID_OFFSET+1]
                    os.pwrite(fd,restored,offset)
                    rows.append(dict(restored='c2 cue-table byte',image_offset=offset,size=1,sha256=sha(restored)))
                else:
                    from mod_editor.core.nfl2k5_bump_texture_writer import logical_name_for
                    for entry in old.entries:
                        name = logical_name_for(entry.name_id)
                        if name is None:
                            continue
                        raw = old.read_entry(entry.index)
                        segments,cursor = [],0
                        for pack,local,length in old._segments(entry.virtual_offset,entry.size):
                            offset = pack.image_offset+local
                            if os.pwrite(fd,raw[cursor:cursor+length],offset) != length:
                                raise ValueError('short kit-resource write')
                            if os.pread(fd,length,offset) != raw[cursor:cursor+length]:
                                raise ValueError('kit-resource read-back differs')
                            segments.append(dict(image_offset=offset,size=length))
                            cursor += length
                        rows.append(dict(restored=name,entry=entry.index,segments=segments,size=len(raw),sha256=sha(raw)))
            os.fsync(fd)
        finally:
            os.close(fd)
    (output.with_suffix(output.suffix+'.receipt.json')).write_text(json.dumps(
        dict(variant=variant,description=VARIANTS[variant],output=str(output),edits=rows,
             base=str(v05),layouts_identical=True,runtime_witness=False),indent=1)+'\n')


def books_keys():
    from mod_editor.core.nfl2k5_playbook_pack import TEAM_BOOKS
    return [key for key in BOOK_ENTRIES if key in TEAM_BOOKS]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--v05',type=Path,required=True)
    ap.add_argument('--v06',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,required=True)
    ap.add_argument('--variant',choices=tuple(VARIANTS))
    ap.add_argument('--output-image',type=Path)
    args = ap.parse_args()
    if bool(args.variant) != bool(args.output_image):
        ap.error('--variant and --output-image must be supplied together')
    if args.output_image:
        repair_disc(args.v05,args.v06,args.out_dir,args.variant,args.output_image)
    else:
        print(json.dumps(prepare(args.v05,args.v06,args.out_dir),indent=1))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Read-only FRZ post-play probes on the shipped discs. No disc build.

Native decoder and commentary routines are real. RAM, allocation and file I/O
are fixtures. This cannot prove Xbox heap residency or audio scheduling.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_commentary_final as c2
from mod_editor.core.nfl2k5_bump_texture_writer import logical_name_for
from nfl_uniform_color_xiso_direct_patch import parse_xdvdfs
from nfl_txtr import HEADER, parse_chunks, decode_chunk, minimum_vc_lz_overlap_scratch

V05 = Path('/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso')
V06 = Path('/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6 (2026-10-08 final).xiso.iso')
TEAMS = ('IND', 'TEN', 'CLE', 'JAX')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, doc):
    path.write_text(json.dumps(doc, indent=1)+'\n')


def extract(scratch):
    """Fresh reads, bounded resources only, and match previous extraction."""
    import shutil
    if shutil.disk_usage('/').free < 50*1024**3 + 64*1024**2:
        raise ValueError('root floor would be crossed')
    for label, source in (('v05',V05), ('v06',V06)):
        out = scratch/label
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        with OuterImage(source) as image:
            files, _ = parse_xdvdfs(image._fd, source.stat().st_size)
            xbe = files['default.xbe']
            resources = [('default.xbe', os.pread(image._fd,xbe.size,xbe.byte_offset))]
            resources += [(f'entry{i}.bin', image.read_entry(i)) for i in (3,5)]
            resources += [(key+'.play',image.read_entry(index)) for key,index in BOOK_ENTRIES.items()]
            roster = rr.load_body(resources[2][1][32:], scheme='one_pool')
            codes = {f'{t.asset_id:02d}' for t in roster.teams[:32] if t.abbreviation in TEAMS}
            for entry in image.entries:
                name = logical_name_for(entry.name_id)
                if name and name[:2] in codes and name.endswith('.IFF') and len(name) == 8:
                    resources.append((name,image.read_entry(entry.index)))
            for name,raw in resources:
                target = out/name
                existed = target.exists()
                if existed and target.read_bytes() != raw:
                    raise ValueError(f'previous extracted input differs: {target}')
                if not existed:
                    target.write_bytes(raw)
                rows.append(dict(file=name,size=len(raw),sha256=sha(raw),previous_equal=existed))
        save(out/'transition-extract.json',dict(source=str(source),resources=rows))
        print(label, len(rows), 'resources', sum(r['size'] for r in rows), 'bytes',flush=True)


def commentary(directory, output):
    from tests.mod_editor.c2_native_probe import Probe, MODES, classify
    payload = (directory/'default.xbe').read_bytes()
    entry = (directory/'entry3.bin').read_bytes()
    at = c2.find_table(entry)
    table = entry[at:at+c2.SPCI_SIZE]
    probe = Probe(payload,table)
    roster = rr.load_body((directory/'entry5.bin').read_bytes()[32:],scheme='one_pool')
    before_entry = (directory.parent/'v05'/'entry3.bin').read_bytes()
    before_at = c2.find_table(before_entry)
    before_table = before_entry[before_at:before_at+c2.SPCI_SIZE]
    before_probe = Probe((directory.parent/'v05'/'default.xbe').read_bytes(),before_table)
    before_roster = rr.load_body((directory.parent/'v05'/'entry5.bin').read_bytes()[32:],scheme='one_pool')
    result = dict(xbe_sha256=sha(payload),spci_sha256=sha(table),table_status=c2.table_status(table),
                  sorted_ids=list(c2.ids(table)) == sorted(set(c2.ids(table))),
                  budget=500000,leaves=probe.machine.leaves,teams=[],faults=[],missing=[],fallbacks=[],
                  resolver_deltas=[],main_roster_id_deltas=[],team_assets={})
    for team in roster.teams[:32]:
        result['team_assets'][team.abbreviation] = team.asset_id
        labels = Counter()
        row = dict(team=team.abbreviation,players=0,cases=0,labels={},faults=[])
        for player in roster.team_players(team.index):
            record = player.record.encode()
            pbp,jersey = struct.unpack_from('<H',record,4)[0],player.record.values['jersey']
            row['players'] += 1
            for a0,a1 in MODES:
                row['cases'] += 1
                try:
                    kind,cue = probe.resolve(record,a0,a1)
                    # Resolver returns a zero-based class; its DB370 calls
                    # use esi + 1 (native instructions at 0x67300..0x6730B).
                    recorded = probe.recorded(cue,kind+1)
                    # Compare exactly the same final record and mode on v0.5.
                    old_kind,old_cue = before_probe.resolve(record,a0,a1)
                    old_recorded = before_probe.recorded(old_cue,old_kind+1)
                    if (kind,cue,recorded) != (old_kind,old_cue,old_recorded):
                        result['resolver_deltas'].append(dict(team=team.abbreviation,player=player.display,
                            mode=[a0,a1],before=[old_kind,old_cue,old_recorded],after=[kind,cue,recorded]))
                    labels[classify(cue,pbp,jersey)] += 1
                    if not recorded and cue != 9999:
                        result['missing'].append(dict(team=team.abbreviation,player=player.display,
                            pbp=pbp,jersey=jersey,mode=[a0,a1],kind=kind,cue=cue))
                except Exception as exc:
                    row['faults'].append(dict(player=player.display,pbp=pbp,mode=[a0,a1],error=str(exc),
                        pc=hex(probe.machine.reg('EIP'))))
        row['labels'] = dict(labels)
        result['teams'].append(row)
        save(output,result)
        print(team.abbreviation,row['cases'],len(row['faults']),flush=True)
        for slot,(old,new) in enumerate(zip(before_roster.team_players(team.index),roster.team_players(team.index))):
            a,b = old.record.values['pbp_id'],new.record.values['pbp_id']
            if a != b:
                result['main_roster_id_deltas'].append(dict(team=team.abbreviation,slot=slot,before=a,after=b))
    # Old franchise saves may still have the retired cue or an invalid id.
    record = roster.team_players(0)[0].record
    for jersey in range(100):
        edited = rr.PlayerRecord.decode(record.encode())
        edited.set('jersey',jersey)
        for cue in (9100,9199,65535,9999):
            raw = bytearray(edited.encode())
            struct.pack_into('<H',raw,4,cue)
            for mode in MODES:
                kind,resolved = probe.resolve(bytes(raw),*mode)
                result['fallbacks'].append(dict(input=cue,jersey=jersey,mode=mode,kind=kind,resolved=resolved,
                                               recorded=probe.recorded(resolved,kind+1)))
    save(output,result)


def text(directory, output):
    """Run final native printf on names from the disc and grade boundaries."""
    from tests.nfl2k5_supersim_draft_fixture import Machine
    from mod_editor.core import nfl2k5_letter_grades as lg
    payload = (directory/'default.xbe').read_bytes()
    m = Machine(payload,trace_writes=False)
    old = Machine((directory.parent/'v05'/'default.xbe').read_bytes(),trace_writes=False)
    doc = rr.load_body((directory/'entry5.bin').read_bytes()[32:],scheme='one_pool')
    fmt,dest,args,name = (m.ARENA+i for i in (0x1000,0x2000,0x3000,0x4000))
    result = dict(xbe_sha256=sha(payload),letter_grades=lg.status(payload),budget=200000,
                  cases=0,faults=[],normal_format_deltas=[])
    for player in doc.players:
        if not player.first and not player.last:
            continue
        value = player.display
        for machine in (m,old):
            machine.uc.mem_write(fmt,'%s caught it for %d yards'.encode('utf-16le')+bytes(2))
            machine.uc.mem_write(name,value.encode('utf-16le')+bytes(2))
            machine.uc.mem_write(args,struct.pack('<Ii',name,23))
            machine.uc.mem_write(dest,b'\xee'*512)
            try:
                machine.call(0x4A400,ecx=dest,edx=fmt,args=(args,),budget=200000)
                result['cases'] += 1
            except Exception as exc:
                result['faults'].append(dict(player=value,error=str(exc),pc=hex(machine.reg('EIP'))))
        if bytes(m.uc.mem_read(dest,512)) != bytes(old.uc.mem_read(dest,512)):
            result['normal_format_deltas'].append(value)
    m.uc.mem_write(fmt,'%R'.encode('utf-16le')+bytes(2))
    for rating in (*range(-5,126),-2147483648,2147483647):
        m.uc.mem_write(args,struct.pack('<i',rating))
        m.uc.mem_write(dest,b'\xee'*512)
        try:
            m.call(0x4A400,ecx=dest,edx=fmt,args=(args,),budget=200000)
            result['cases'] += 1
            if bytes(m.uc.mem_read(dest+8,504)) != b'\xee'*504:
                raise ValueError('grade text exceeded four UTF-16 units')
        except Exception as exc:
            result['faults'].append(dict(rating=rating,error=str(exc),pc=hex(m.reg('EIP'))))
    save(output,result)


class TextureMachine:
    """Native wrapper allocator and in-place VC-LZ decoder, guarded buffers."""
    def __init__(self,payload):
        import unicorn as u
        from unicorn import x86_const as x
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        self.x = x
        self.u = u.Uc(u.UC_ARCH_X86,u.UC_MODE_32)
        self.u.mem_map(0x10000,0x1600000)
        for section in XbeImage(payload).sections:
            if section.raw_size:
                self.u.mem_write(section.start,payload[section.raw:section.raw+section.raw_size])
        self.u.mem_map(0x2000000,0x800000)
        self.u.mem_map(0x3000000,0x10000)
        self.sizes = []
        def leaf(uc,address,size,data):
            if address == 0x48700:
                self.sizes.append(uc.reg_read(x.UC_X86_REG_EDX))
            esp = uc.reg_read(x.UC_X86_REG_ESP)
            uc.reg_write(x.UC_X86_REG_EAX,0x2100000)
            uc.reg_write(x.UC_X86_REG_EIP,struct.unpack('<I',uc.mem_read(esp,4))[0])
            uc.reg_write(x.UC_X86_REG_ESP,esp+4)
        for address in (0x437D0,0x48700):
            self.u.hook_add(u.UC_HOOK_CODE,leaf,begin=address,end=address)

    def call(self,pc,**regs):
        x = self.x
        self.u.mem_write(0x3008000,struct.pack('<I',0x3009000))
        defaults = dict(esp=0x3008000,eax=0,ecx=0,edx=0,ebx=0,esi=0,edi=0,ebp=0,eflags=0x202)
        defaults.update(regs)
        for name,value in defaults.items():
            self.u.reg_write(getattr(x,'UC_X86_REG_'+name.upper()),value)
        self.u.emu_start(pc,0x3009000,count=20000000,timeout=10000000)
        eip = self.u.reg_read(x.UC_X86_REG_EIP)
        if eip != 0x3009000:
            raise ValueError(f'native budget expired at {eip:#x}')

    def check(self,span,chunk,decoded):
        capacity = len(decoded)+chunk.overlap_scratch_bytes
        if capacity > 6*1024**2 or capacity < chunk.stored_size:
            raise ValueError('invalid bounded decode capacity')
        dest = 0x2100000
        end = dest+capacity
        source = end-chunk.stored_size
        self.u.mem_write(dest-32,b'P'*32)
        self.u.mem_write(dest,bytes([0xa5])*capacity)
        self.u.mem_write(end,b'S'*32)
        self.u.mem_write(source,span[32:32+chunk.stored_size])
        self.call(0x4DC00,ecx=source,edx=dest)
        if bytes(self.u.mem_read(dest,len(decoded))) != decoded:
            raise ValueError('native in-place output differs')
        if bytes(self.u.mem_read(dest-32,32)) != b'P'*32 or bytes(self.u.mem_read(end,32)) != b'S'*32:
            raise ValueError('native decoder changed guard bytes')
        if chunk.kind == 'TSET':
            self.u.mem_write(0x2001000,span[:32])
            self.call(0x451D0,eax=0x2001000)
            if self.sizes[-1] != capacity:
                raise ValueError(f'allocator requested {self.sizes[-1]}, needed {capacity}')


def textures(directory, baseline, output):
    payload = (directory/'default.xbe').read_bytes()
    machine = TextureMachine(payload)
    result = dict(xbe_sha256=sha(payload),decoder='0x4DC00',allocator='0x451D0',
        substituted_leaves=['0x437D0 resource setup','0x48700 allocation'],
        budget=20000000,packages=[],faults=[],native_unique=0)
    cache = set()
    for path in sorted(directory.glob('*.IFF')):
        raw = path.read_bytes()
        old = (baseline/path.name).read_bytes()
        before_chunks = parse_chunks(old,allow_trailing=True)
        chunks = parse_chunks(raw,allow_trailing=True)
        row = dict(package=path.name,before_sha256=sha(old),after_sha256=sha(raw),
                   before_allocation=0,after_allocation=0,chunks=[])
        primary = path.stem[-1] == '0'
        for chunk,before in zip(chunks,before_chunks):
            row['before_allocation'] += before.output_size+before.overlap_scratch_bytes
            row['after_allocation'] += chunk.output_size+chunk.overlap_scratch_bytes
            if not chunk.compressed:
                continue
            span = raw[chunk.offset:chunk.end_offset]
            item = dict(index=chunk.index,kind=chunk.kind,stored=chunk.stored_size,
                        decoded=chunk.output_size,scratch=chunk.overlap_scratch_bytes,native=False)
            try:
                decoded,info = decode_chunk(span,parse_chunks(span)[0])
                stream = span[32:32+info.consumed_bytes]
                minimum = minimum_vc_lz_overlap_scratch(stream,chunk.stored_size,chunk.output_size)
                item.update(minimum_scratch=minimum,margin=chunk.overlap_scratch_bytes-minimum)
                if chunk.overlap_scratch_bytes < minimum:
                    raise ValueError('insufficient overlap scratch')
                key = sha(span)
                if primary and key not in cache:
                    local = parse_chunks(span)[0]
                    machine.check(span,local,decoded)
                    cache.add(key)
                    result['native_unique'] += 1
                item['native'] = primary
            except Exception as exc:
                result['faults'].append(dict(package=path.name,index=chunk.index,error=str(exc),
                    pc=hex(machine.u.reg_read(machine.x.UC_X86_REG_EIP))))
            row['chunks'].append(item)
        result['packages'].append(row)
        save(output,result)
        print(path.name,row['before_allocation'],row['after_allocation'],len(result['faults']),flush=True)
    save(output,result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('extract','commentary','textures','text'))
    p.add_argument('--scratch',type=Path,default=Path('/home/noah/2k-worktrees/.b77-scratch/frz'))
    a = p.parse_args()
    if a.mode == 'extract':
        extract(a.scratch)
    elif a.mode == 'commentary':
        commentary(a.scratch/'v06',a.scratch/'commentary.json')
    elif a.mode == 'text':
        text(a.scratch/'v06',a.scratch/'text.json')
    else:
        textures(a.scratch/'v06',a.scratch/'v05',a.scratch/'textures.json')


if __name__ == '__main__':
    main()

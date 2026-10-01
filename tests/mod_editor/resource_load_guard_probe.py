"""Bounded native G pregame path, resource completion and absent-director execution.

Only archive read/close and the inherited game-setup UI/context boundaries are modeled.
No xemu, kernel execution, disc writes or rendering. Inputs remain read-only.
"""
from pathlib import Path
import argparse
import gc
import hashlib
import json
import os
import resource
import struct
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.mod_editor.test_nfl2k5_ingame_block_budget import InGameBlockBudgetTests as Harness
from tests.mod_editor.test_nfl2k5_ingame_block_budget import MAIN_HEAP, HEAP_A, HEAP_B, BLOCK_SIZE, BLOCK_LEFT, BLOCK_CURSOR
from mod_editor.core import nfl2k5_practice_reserves as pr
from mod_editor.core import nfl2k5_k128 as k128
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_resource_load_guard as guard
from mod_editor.core.nfl2k5_roster_records import _outer_image
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EDX

G_SHA256 = '7ddb384bf4dee80f09cb3fabc422747ea1a009a1a904415aee94efeef098a91e'
ENTRY_SHA256 = '7d3de460e8d98d9cce9fc38a80badd2cf9314dd57a11137d7dc9681c9888c60d'
OFFSET = 0x3178820


class Probe(Harness):
    def setup_pregame(self, xbe, body, home_index, room, *, roster_heap=False):
        self.body = body
        self.boot(xbe)
        self.put(0xB72808, 0x91000)
        self.put(0xB7280C, 0x91000)
        home, away = self.teams + 500 * home_index, self.teams + 500 * 29
        for a,v in ((0xE576A0,0),(0xE5FF80,4),(0xB9C290,0),(0xB9E230,1),(0xE5FFE4,0),
                    (0xE5FE64,self.word(home+0x114)),(0xB018B8,0)):
            self.put(a,v)
        self.call(pr.STAGE_VA, ecx=away, edx=home)
        self.main_heap(room + 0x91080)
        roster_control = MAIN_HEAP
        if roster_heap:
            allocation = next(a for a in space.plan(tuple(space._validate(xbe)[2]) + k128.REQUESTS,
                              scaleout=True)['allocations'] if a['owner'] == k128.OWNER)
            code_va = allocation['va']
            flags = k128.options_word(roster_heap=True)
            self.uc.mem_write(code_va, k128.code_for(code_va, flags))
            for _, va, before, after in k128.sites(code_va, flags):
                assert bytes(self.uc.mem_read(va, len(before))) == before
                self.uc.mem_write(va, after)
            self.uc.mem_map(0x06000000, 0x200000)
            self.put(k128.DEVKIT_BASE_VA, 0x06000000)
            self.put(k128.DEVKIT_END_VA, 0x06200000)
            roster_control = self.call(code_va + k128.HEAP_OFFSET)
        assert self.call(0x48700, ecx=roster_control, edx=0x91000)
        actual_room = self.call(0x48960, ecx=MAIN_HEAP)
        snapshot = self.call(0xC0B50,ecx=0xB30864,edx=0xB30A58,args=(self.word(0xE5FE64),))
        assert self.call(0x84EB0,ecx=0x180000,edx=0x20000) == 1
        row = dict(home_index=home_index,fixture_baseline_room=room,roster_heap=roster_heap,
                   largest_at_setup=actual_room,snapshot=snapshot,
                   block=self.word(BLOCK_SIZE),left=self.word(BLOCK_LEFT))
        boundary = self.word(BLOCK_CURSOR) + self.word(BLOCK_LEFT)
        before = bytes(self.uc.mem_read(boundary, 128))
        self.call(0x125700)
        row.update(heap_a_capacity=self.word(HEAP_A+4)-self.word(HEAP_A),
                   heap_b_capacity=self.word(HEAP_B+4)-self.word(HEAP_B),
                   heap_b_free=self.word(HEAP_B+0x88),
                   block_boundary_preserved=before == bytes(self.uc.mem_read(boundary,128)))
        return row

    def stream_intro(self, entry, *, loader_va=None):
        """Enter native header dispatch as an already-completed 32-byte wrapper read.

        The host boundary at 0x48FF0 emulates a successful archive read's cursor,
        byte count, destination and status, then delivers the native callback.
        The dispatcher, skip, payload fixup, registration, EOF and completion run
        unmodified. The failed path never reaches this boundary.
        """
        context, request, header = 0xBB75B8, 0xB09598, 0xB09550
        self.call(0xDC6B0)  # native director/active-script initialization
        for a,v in ((0xB0957C,0),(0xB09578,context),(0xB09584,1),(0xB09590,0),
                    (0xB09614,0),(0xB11224,0),(context+0x18,0x1256D0),
                    (context+0x20,HEAP_B),(request,OFFSET),(request+4,0),
                    (request+8,OFFSET+len(entry)-32),(request+12,0),
                    (request+0x18,32),(request+0x1c,header),(request+0x20,0),
                    (0xB12034,HEAP_B)):
            self.put(a,v)
        self.uc.mem_write(header,entry[:32])
        if loader_va is None:
            self.call(0x166760)  # real DRCT registration routine
        else:
            self.call(0x436A0,ecx=0xBDB730,edx=int.from_bytes(entry[:4],'little'),args=(loader_va,))
        reads, pending, trace = [], [], []
        def read(_uc,_pc,_size,_data):
            sp = self.uc.reg_read(UC_X86_REG_ESP)
            dest = self.uc.reg_read(UC_X86_REG_EDX)
            req = self.uc.reg_read(UC_X86_REG_ECX)
            args = list(struct.unpack('<5I',self.uc.mem_read(sp+4,20)))
            row = dict(destination=dest,request=req,args=args)
            reads.append(row)
            if dest:
                assert args[:3] == [OFFSET,0,len(entry)-32], row
                self.uc.mem_write(dest,entry[32:])
                self.put(req,OFFSET+len(entry)-32)
                self.put(req+0x18,len(entry)-32)
                self.put(req+0x1c,dest)
                self.put(req+0x20,0)
                pending.append((args[3],req,args[4]))
            self._return(1,20)
        hooks = [self.uc.hook_add(UC_HOOK_CODE,read,begin=0x48FF0,end=0x48FF0),
                 self.uc.hook_add(UC_HOOK_CODE,lambda *_:self._return(1),begin=0x48FC0,end=0x48FC0)]
        for a in (0x43948,0x43A20,0x43880,0x1256D0,0x166700,0xDC700,0xDC840):
            hooks.append(self.uc.hook_add(UC_HOOK_CODE,lambda _u,pc,_s,_d:trace.append(pc),begin=a,end=a))
        self.call(0x438D0,edx=request,args=(context,))
        for callback,req,user in pending:
            self.call(callback,edx=req,args=(user,))
        for h in hooks:
            self.uc.hook_del(h)
        result = dict(reads=reads,trace=[hex(a) for a in trace],
                      ready=bool(self.word(0xBB75F0)&4),loading=self.word(0xB09584),
                      cursor=self.word(request),registered=self.word(0xB73BD0),
                      registry_sha256=hashlib.sha256(bytes(self.uc.mem_read(0xB73BD0,0x60))).hexdigest(),
                      heap_b_after=self.word(HEAP_B+0x88))
        if not reads:
            assert result['ready'] and result['loading']==0 and result['registered']==0, result
            assert result['cursor']==OFFSET+len(entry)-32
            assert 0x43948 in trace and 0x1256D0 in trace and 0x166700 not in trace
            event = self.BASE+0x180100
            self.uc.mem_write(event,struct.pack('<5I',0x71,0,0,0,0))
            # Native missing selection, all channels idle, scheduler returns every tick.
            result['selection_returns']=[self.call(0xDC930,ecx=event,edx=1) for _ in range(3)]
            assert result['selection_returns']==[0,0,0]
            for _ in range(3):
                self.call(0xDC6F0,args=(0,))
            result['active_channels']=[self.call(0x5A920,ecx=i) for i in range(1,15)]
            assert result['active_channels']==[0]*14
            assert all(self.word(0xB2C16C+i*0x3c)==0 for i in range(32))
            result['scheduler_ticks_returned']=3
            # Run the game's pregame ready gate, not just the selector in isolation.
            self.put(0xB72BDC,1)
            self.put(0xE6002C,0)  # no controller input in this bounded tick
            attempts=[]
            h=self.uc.hook_add(UC_HOOK_CODE,lambda *_:attempts.append(self.uc.reg_read(UC_X86_REG_ECX)),
                               begin=0x67DF0,end=0x67DF0)
            for _ in range(3):
                self.call(0x125BC0)
            self.uc.hook_del(h)
            assert attempts==[0x71],attempts
            assert self.word(0xB72BDC)==0
            result['pregame_event_attempts']=attempts
            result['pregame_pending_after']=self.word(0xB72BDC)
            block=self.call(0x48700,ecx=MAIN_HEAP,edx=256)
            assert block
            self.call(0x48870,ecx=block)
            result['main_heap_allocate_free_after_skip']=True
        elif reads[0]['destination']:
            assert result['ready'] and result['loading']==0 and result['registered']
            assert all(a in trace for a in (0x166700,0xDC700,0xDC840,0x1256D0))
            result['relocated_payload_sha256']=hashlib.sha256(bytes(self.uc.mem_read(reads[0]['destination'],len(entry)-32))).hexdigest()
        return result


def run(xbe,body,entry):
    patched,receipt=guard.apply(xbe)
    assert guard.apply(patched)[0]==patched
    rows=[]
    # BAL, DET, CLE. BAL gives exactly 0 / 18176 / 83712 / 214784.
    for team in (24,18,5):
        for room,kroute in ((0x160000,False),(0x170000,False),(0x180000,False),(0x160000,True)):
            pair=[]
            for fixed,data in ((False,xbe),(True,patched)):
                p=Probe()
                row=p.setup_pregame(data,body,team,room,roster_heap=kroute)
                row['fixed']=fixed
                row.update(p.stream_intro(entry))
                if fixed:
                    assert row['block_boundary_preserved']
                    assert all(r['destination'] for r in row['reads'])
                    assert row['ready'] and row['loading']==0
                    assert bool(row['reads']) == (row['heap_b_capacity']>=73856)
                else:
                    assert len(row['reads'])==1
                p.uc=None
                gc.collect()
                pair.append(row)
                rows.append(row)
            if pair[0]['reads'][0]['destination']:
                # Full payload fixup, pointer registration, request and heap accounting match.
                assert {k:v for k,v in pair[0].items() if k!='fixed'} == {k:v for k,v in pair[1].items() if k!='fixed'}, pair
    return rows,receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xbe',type=Path)
    parser.add_argument('disc',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS,(5*1024**3,5*1024**3))
    xbe=args.xbe.read_bytes()
    assert hashlib.sha256(xbe).hexdigest()==G_SHA256
    with _outer_image()(args.disc) as archive:
        body=archive.read_entry(5)[32:]
        entry=archive.read_entry(1194)
    assert hashlib.sha256(entry).hexdigest()==ENTRY_SHA256
    rows,receipt=run(xbe,body,entry)
    report=dict(evidence='PROVED OFFLINE',xbe_sha256=G_SHA256,entry_sha256=ENTRY_SHA256,
                affinity=sorted(os.sched_getaffinity(0)),max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                limitation='Controlled main-heap fixtures, modeled archive I/O and inherited setup UI/context boundaries. No renderer, coin toss or kernel execution. K128 upper region is a bounded 2 MiB fixture; startup has separate tests.',
                patch=receipt,rows=rows)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    for row in rows:
        print(row['home_index'],row['fixed'],row['roster_heap'],row['heap_b_capacity'],
              [r['destination'] for r in row['reads']],row['ready'],row['loading'],flush=True)


if __name__=='__main__':
    main()

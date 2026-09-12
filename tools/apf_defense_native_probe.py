#!/usr/bin/env python3
"""Bounded pinned BASE defensive category/formation/normalizer witnesses.

No retail bytes are emitted. PPC64 integer and ABI instructions absent from
Unicorn PPC32 are adapted instruction by instruction, not selector results.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.apf_personnel_native_probe import PersonnelMachine, BOOK, MASTER, STACK, STOP
from tools.apf_book_resolution_probe import PE_SHA256, BASE
from mod_editor.core import apf2k8_splb_writer as splb

STATE, DETAIL, OFFENSE, GAME, TEAM, DIRECTION = (0x300000, 0x301000, 0x302000, 0x303000, 0x304000, 0x305000)
RNG = 0x8505CD00


class DefenseMachine(PersonnelMachine):
    def __init__(self, image, master):
        self.wide = {}
        self.adapted = set()
        self.weights = []
        import unicorn as u
        from unicorn import ppc_const as r
        payload = image if isinstance(image, bytes) else Path(image).read_bytes()
        if hashlib.sha256(payload).hexdigest() != PE_SHA256:
            raise ValueError("Expected the pinned flat BASE PE")
        self.u, self.r = u, r
        self.cpu = u.Uc(u.UC_ARCH_PPC, u.UC_MODE_32 | u.UC_MODE_BIG_ENDIAN)
        self.cpu.mem_map(BASE, (len(payload)+4095) & ~4095)
        self.cpu.mem_write(BASE, payload)
        self.cpu.mem_map(BOOK, 0x400000)
        self.cpu.mem_write(MASTER, master)
        self.put(0x84f3f808, BOOK)
        self.cpu.hook_add(u.UC_HOOK_CODE, self._abi)
        self.cpu.reg_write(self.r.UC_PPC_REG_MSR, 0x2000)
        for at, value in ((STATE+0x20, BOOK), (STATE+0xc, DETAIL), (OFFENSE+0xc, DETAIL),
                          (OFFENSE+8, TEAM), (TEAM+0xc, DIRECTION), (0x851A2780, OFFENSE),
                          (0x851A2784, STATE), (0x851A27EC, GAME)):
            self.put(at, value)
        self.cpu.mem_write(DETAIL+0xe4, struct.pack('>f', 1.0))
        self.cpu.mem_write(DIRECTION+4, struct.pack('>f', 1.0))
        self.seed(1)

    def put(self, at, value):
        self.cpu.mem_write(at, struct.pack('>I', value & 0xffffffff))

    def seed(self, seed):
        # Explicit synthetic 55-word state, not a claim about retail seeding.
        self.cpu.mem_write(RNG, struct.pack('>II', 54, 30))
        value = seed
        for i in range(55):
            value = (value * 6364136223846793005 + 1442695040888963407) & ((1 << 64)-1)
            self.cpu.mem_write(RNG+8+i*8, struct.pack('>Q', value))
        self.wide.clear()

    def _abi(self, x, pc, size, data):
        r = self.r
        get = lambda n: x.reg_read(r.UC_PPC_REG_0+n)
        setreg = lambda n,v: x.reg_write(r.UC_PPC_REG_0+n, v & 0xffffffff)
        def wide(n):
            value = self.wide.get(n, get(n))
            return value if value & 0xffffffff == get(n) else get(n)
        sp = get(1)
        if pc == 0x84863388:
            n = get(4)
            self.weights.append({'power': get(5), 'weights': list(struct.unpack('>'+str(n)+'f', x.mem_read(get(3),4*n)))})
        # Extend the existing exact GPR ABI adapters down through r14.
        if 0x84bd6db0 <= pc <= 0x84bd6dbc:
            first = 14+(pc-0x84bd6db0)//4
            for reg in range(first,32):
                x.mem_write(sp-0x10-(31-reg)*8,struct.pack('>Q',get(reg)))
            x.mem_write(sp-8,struct.pack('>I',get(12)))
            x.reg_write(r.UC_PPC_REG_PC,x.reg_read(r.UC_PPC_REG_LR));return
        # Floating register ABI thunks address their save area with r12.
        if 0x84bd7380 <= pc <= 0x84bd73ac or 0x84bd73cc <= pc <= 0x84bd73f8:
            word = int.from_bytes(x.mem_read(pc,4),'big')
            op,fr,ra = word>>26,(word>>21)&31,(word>>16)&31
            if op in (50,54):  # native lfd/stfd are supported
                return
        word = int.from_bytes(x.mem_read(pc,4),'big')
        op,rt,ra,rb,xo = word>>26,(word>>21)&31,(word>>16)&31,(word>>11)&31,(word>>1)&1023
        handled = True
        if op == 31 and xo == 986:  # extsw
            value = get(rt); self.wide[ra] = value if value < 0x80000000 else value - (1<<32)
            setreg(ra,value)
        elif op == 62 and word & 3 == 0:  # std
            d = word & 0xfffc; d = d if d < 0x8000 else d - 0x10000
            x.mem_write((get(ra)+d)&0xffffffff, struct.pack('>Q',wide(rt) & ((1<<64)-1)))
        elif op == 58 and word & 3 == 0:  # ld
            d = word & 0xfffc; d = d if d < 0x8000 else d - 0x10000
            value = int.from_bytes(x.mem_read((get(ra)+d)&0xffffffff,8),'big')
            self.wide[rt]=value;setreg(rt,value)
        elif op == 31 and xo == 21:  # ldx
            value=int.from_bytes(x.mem_read(((get(ra) if ra else 0)+get(rb))&0xffffffff,8),'big')
            self.wide[rt]=value;setreg(rt,value)
        elif op == 31 and xo == 149:  # stdx
            x.mem_write(((get(ra) if ra else 0)+get(rb))&0xffffffff,struct.pack('>Q',wide(rt) & ((1<<64)-1)))
        elif pc in (0x84b3e87c,0x84b3e8e4):  # 64-bit sum in RNG
            value=(wide(ra)+wide(rb)) & ((1<<64)-1)
            self.wide[rt]=value;setreg(rt,value)
        elif op == 63 and xo == 846:  # fcfid
            bits=x.reg_read(r.UC_PPC_REG_FPR0+rb)
            value=bits if bits < 1<<63 else bits-(1<<64)
            x.reg_write(r.UC_PPC_REG_FPR0+rt,struct.unpack('>Q',struct.pack('>d',float(value)))[0])
        elif word == 0x786b07e0:  # clrldi r11,r3,63 (RNG tie test)
            setreg(11,get(3)&1)
        elif word == 0x2b2b0000:  # cmpldi cr6,r11,0, here r11 is 0 or 1
            cr=x.reg_read(r.UC_PPC_REG_CR)
            x.reg_write(r.UC_PPC_REG_CR,(cr & ~0xf0) | (0x20 if get(11)==0 else 0x40))
        else:
            handled=False
        if handled:
            self.adapted.add(pc)
            x.reg_write(r.UC_PPC_REG_PC,pc+4)
        else:
            super()._abi(x,pc,size,data)

    def call(self,address,*args,stop=STOP):
        x,r=self.cpu,self.r
        x.reg_write(r.UC_PPC_REG_1,STACK)
        x.reg_write(r.UC_PPC_REG_LR,STOP)
        for i,arg in enumerate(args,3):x.reg_write(r.UC_PPC_REG_0+i,arg)
        try:
            x.emu_start(address,stop,count=4000000)
        except Exception as exc:
            raise RuntimeError(f'PPC stopped at {x.reg_read(r.UC_PPC_REG_PC):08X}: {exc}') from exc
        if x.reg_read(r.UC_PPC_REG_PC)!=stop:raise AssertionError(f'4000000 instruction bound exceeded at {x.reg_read(r.UC_PPC_REG_PC):08X}')
        return x.reg_read(r.UC_PPC_REG_3)

    def matchup(self,row,position=0.0):
        self.cpu.mem_write(GAME+0x18,struct.pack('>f',position))
        return self.call(0x84869B60,row)

    def category(self,row):
        result=self.call(0x8486AEB0,STATE,row,0)
        return (result-MASTER-0x44)//16 if result else None

    def formation(self,category):
        result=self.call(0x848693F8,STATE,14,MASTER+0x44+category*16,0,0)
        return (result-MASTER-0x244)//184 if result else None

    def cpu_formation(self, offense_category=3, position=0.0):
        self.put(DETAIL+0x2c, 8)  # existing offensive call available
        self.put(DETAIL+4, MASTER+0x44+offense_category*16)
        self.put(DETAIL+8, MASTER+0x244)  # ordinary offense form, not cached Hail Mary
        self.cpu.mem_write(GAME+0x18, struct.pack('>f', position))
        self.call(0x8486D0F8, STATE, 0x306000, 0, stop=0x8486D38C)
        category = self.cpu.reg_read(self.r.UC_PPC_REG_28)
        formation = self.cpu.reg_read(self.r.UC_PPC_REG_30)
        return ((category-MASTER-0x44)//16, (formation-MASTER-0x244)//184)

    def initialize_plays(self, master, play_ids):
        # Rebase the serialized name and assignment-chain pointers only.
        for i in range(586):
            at = 0x80c4+i*100
            for field in (at, *(at+0x10+j*8 for j in range(11))):
                old = int.from_bytes(master[field:field+4], 'big')
                self.put(MASTER+field, MASTER+field+old-1)
        self.call(0x84A877C8, 0x820FBFC8)
        for play in sorted(set(play_ids)):
            self.call(0x84A88E90, MASTER+0x80c4+play*100)

    def play_candidates(self, category, formation):
        cat, form = MASTER+0x44+category*16, MASTER+0x244+formation*184
        first = self.call(0x84A8D440, BOOK, cat)
        output = []
        while first:
            play = (first-MASTER-0x80c4)//100
            flags = int.from_bytes(self.cpu.mem_read(first+8,4),'big')
            if (flags & 0x80000 and self.call(0x84A8C0B8,BOOK,first,form)
                    and self.call(0x848646B0,BOOK,first,form)):
                second = self.call(0x84A8C4E0,BOOK,first)
                partners = []
                while second:
                    if (int.from_bytes(self.cpu.mem_read(second+8,4),'big') & 0x80000
                            and self.call(0x84A8C0B8,BOOK,second,form)):
                        partners.append((second-MASTER-0x80c4)//100)
                    second = self.call(0x84A8A488,BOOK,first,second)
                output.append({'first_play':play,'compatible_second_plays':partners})
            first = self.call(0x84A8D4D0,BOOK,cat,first)
        return output

    def normalize(self,body):
        self.cpu.mem_write(BOOK,body)
        self.put(BOOK+0x7e0c,MASTER)
        self.cpu.reg_write(self.r.UC_PPC_REG_25,BOOK)
        # Execute all entry cleanup, record compaction and category/formation/play caches.
        # Stop before the optional five-item tail repair and comparison/report suffix.
        self.call(0x84A8C7C0,stop=0x84A8CCF4)
        return bytes(self.cpu.mem_read(BOOK,splb.RESOURCE_SIZE))


def added_book(book, donor, formation, category):
    record = next(r.record_index for r in book.records if not r.populated)
    changes = [splb.TrailerReplace(book.outer_index,record,formation,category)]
    changes += [splb.MembershipChange(book.outer_index,record,e.play_index,True) for e in donor.entries]
    compiled = splb.compile_book(book,changes)
    splb.verify_book(book.body,compiled.replacement,changes)
    return splb.parse_book(compiled.replacement,book.outer_index)


def compact_remove(book, formation):
    """Research edit: remove every matching record and rebuild record caches.

    Does not change the five-item special tail or a saved/global source book.
    This is deliberately not a Studio removal writer.
    """
    body = bytearray(book.body)
    records = [r for r in book.records if r.populated and r.formation_index != formation]
    empty = struct.pack('>H', splb.FILLER)*84 + bytes.fromhex('0000920000000000')
    for i in range(splb.RECORD_COUNT):
        at = splb.RECORD_BASE+i*splb.RECORD_STRIDE
        if i < len(records):
            old = splb.RECORD_BASE+records[i].record_index*splb.RECORD_STRIDE
            body[at:at+splb.RECORD_STRIDE] = book.body[old:old+splb.RECORD_STRIDE]
        else:
            body[at:at+splb.RECORD_STRIDE] = empty
    for at, count in ((0x7d98, 6), (0x7db0, 21), (0x7e04, 2)):
        body[at:at+4*count] = bytes(4*count)
    def bit(at, index):
        offset = at+4*(index//32)
        value = struct.unpack_from('>I',body,offset)[0] | (1 << (index%32))
        struct.pack_into('>I',body,offset,value)
    for record in records:
        bit(0x7d98,record.formation_index)
        bit(0x7e04,record.category_index)
        word_b = int.from_bytes(record.trailer[4:], 'big')
        for category in range(32):
            if word_b & (1 << category): bit(0x7e04,category)
        for entry in record.entries: bit(0x7db0,entry.play_index)
    return splb.parse_book(bytes(body),book.outer_index)


def native_witness(image, index, seeds=128):
    from collections import Counter
    from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
    master = read_master_play_body(index)
    machine = DefenseMachine(image,master)
    book = splb.read_book(index,134)
    donor = splb.read_book(index,618).records[0]
    experiments = []
    for form,cat in ((147,23),(150,27)):
        added = added_book(book,donor,form,cat)
        machine.install(added)
        counts = Counter()
        for seed in range(1,seeds+1):
            machine.seed(seed)
            counts[machine.cpu_formation()] += 1
        machine.seed(1); machine.weights.clear()
        row = machine.matchup(3)
        category = machine.category(row)
        lottery = machine.weights[0]
        assert row == 13
        expected = [0.0,1.0,0.009999990463256836,0.0,1.0 if form==147 else 0.0]
        assert lottery == {'power':3,'weights':expected}, lottery
        assert set(counts) <= ({(11,141),(23,147)} if form==147 else {(11,141)})
        experiments.append({'added_formation':form,'added_category':cat,
                            'compiled_body_sha256':hashlib.sha256(added.body).hexdigest(),
                            'offense_row':3,'requested_defense_row':row,'category_lottery':lottery,
                            'seeds':seeds,'results':[{'category':c,'formation':f,'count':n}
                                                   for (c,f),n in sorted(counts.items())]})
    # Force a representable high draw with an explicit RNG state. The first
    # weighted candidate consumes one tie draw; the following pair supplies U.
    machine.seed(1)
    machine.cpu.mem_write(RNG+8+53*8,struct.pack('>Q',0x7fffff))
    machine.cpu.mem_write(RNG+8+29*8,struct.pack('>Q',0))
    near = machine.cpu_formation(position=4500.0)
    assert near == (27,150), near
    removals = []
    for outer in (134,1037):
        original = splb.read_book(index,outer)
        retired = original.records[0].formation_index
        hole = bytearray(original.body)
        hole[splb.RECORD_BASE:splb.RECORD_BASE+168] = struct.pack('>H',splb.FILLER)*84
        machine.install(splb.parse_book(bytes(hole),outer))
        later = original.records[1].formation_index
        hidden = machine.call(0x84a8a258,BOOK,MASTER+0x244+later*184)
        assert hidden == 0
        after_hole = splb.parse_book(machine.normalize(bytes(hole)),outer)
        compact = compact_remove(original,retired)
        normalized = splb.parse_book(machine.normalize(compact.body),outer)
        assert retired not in [r.formation_index for r in normalized.records if r.populated]
        assert compact.body[0x7d98:0x7e0c] == normalized.body[0x7d98:0x7e0c]
        assert [r.trailer for r in compact.records if r.populated] == [r.trailer for r in normalized.records if r.populated]
        assert machine.call(0x84a8a258,BOOK,MASTER+0x244+retired*184) == 0
        normalized_twice = machine.normalize(normalized.body)
        assert normalized.body == normalized_twice
        if outer == 134:
            for seed in range(1,17):
                machine.seed(seed)
                assert machine.cpu_formation()[1] != retired
        removals.append({'book':original.name,'retired_formation':retired,
                         'hole_hides_later_before_normalization':hidden==0,
                         'hole_mask':hex(struct.unpack_from('>I',after_hole.body,0x7e04)[0]),
                         'compact_mask':hex(struct.unpack_from('>I',normalized.body,0x7e04)[0]),
                         'remaining_formations':[r.formation_index for r in normalized.records if r.populated],
                         'compact_surviving_trailers_unchanged':True,'normalized_twice_identical':True})
    machine.install(book)
    machine.initialize_plays(master,[e.play_index for r in book.records for e in r.entries])
    candidates = machine.play_candidates(11,141)
    assert len(candidates)==12 and sum(len(p['compatible_second_plays']) for p in candidates)==192
    return {'grade':'PROVED bounded native BASE; gameplay UNWITNESSED',
            'image_sha256':PE_SHA256,'master_sha256':hashlib.sha256(master).hexdigest(),
            'bounds':'4000000 instructions per call; driver stops before play scoring at 8486D38C',
            'synthetic_state':'55-word LCG fixture; retail RNG initialization not modeled; donor entries from X-34Base for both added records',
            'experiments':experiments,'near_goal_high_draw':{'category':near[0],'formation':near[1]},
            'removal':removals,'native_defensive_component_candidates':candidates,
            'play_scoring':'A860 lineup evaluator and C448/C6C8 final play lotteries not executed',
            'adapted_instruction_addresses':[f'{pc:08X}' for pc in sorted(machine.adapted)]}


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    report=native_witness(args.image,args.index)
    args.report.write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps({k:report[k] for k in ('grade','experiments','near_goal_high_draw','removal')},indent=2))

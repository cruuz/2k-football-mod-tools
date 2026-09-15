"""Full-width ABI oracle for emitted PPC bytes, independent of native PPC32 adapters."""
import random,struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_apf_playcall_patch import SyntheticMachine,MASK64
from mod_editor.core import apf2k8_situation_mask as m

class MaskMachine(SyntheticMachine):
    def __init__(self,profile,category,excluded,phase=4):
        super().__init__()
        self.profile,self.category=profile,category
        self.f={0:0xFFF0010203040506,13:0x4001234501020304}
        self.fpscr=0x9F83A12B
        self.original_f=self.f.copy();self.original_fpscr=self.fpscr
        self.original_control=(self.lr,self.ctr)
        self.manager=0x60000;team=0x61000;state=0x62000
        self.add(self.manager,bytes(0x3000))
        self.put(self.manager+0xC,team,4)
        game=m.GAME[profile.name];self.add(game,bytes(0x80))
        self.put(game+0x6C,state,4);self.put(game+0x34,phase,4)
        self.put(state+4,3,4)
        self.put(state+0x18,int.from_bytes(struct.pack('>f',0),'big'),4)
        self.put(state+0x28,int.from_bytes(struct.pack('>f',731.52),'big'),4)
        self.add(m.RECEIPT_START,bytes(m.RECEIPT_LIMIT-m.RECEIPT_START))
        policies={'O-ManBlock':[[] for _ in range(12)]};policies['O-ManBlock'][8]=excluded
        self.add(m.DATA_START,m.encode_data(policies))
        for i,value in enumerate('O-ManBlock'.encode('utf-16-be')):self.put(self.book+0x30+i,value,1)
        for i,(form,cat) in enumerate(((2,6),(14,6),(24,6),(30,3))):self.record(i,[0],cat,form)
        self.put(self.master+0x44+6*16+4,10,1)
        if category:
            self.r[28],self.r[27],self.r[26],self.r[21],self.r[24]=self.book,self.manager,10,0,2
            ids=(3,6);base,stride=0x44,16;po,wo=0x110,0x70
        else:
            self.r[29],self.r[28],self.r[25],self.r[27]=self.book,self.master+0x44+6*16,0,3
            ids=(2,14,24);base,stride=0x244,184;po,wo=0xF0,0x50
        for i,identifier in enumerate(ids):
            self.put(self.r[1]+po+4*i,self.master+base+identifier*stride,4)
            self.put(self.r[1]+wo+4*i,int.from_bytes(struct.pack('>f',i+.5),'big'),4)
        self.original_buffer=bytes(self.get(self.r[1]+wo+i,1) for i in range(160))
    def get(self,address,size):return super().get(address&0xFFFFFFFF,size)
    def put(self,address,value,size):return super().put(address&0xFFFFFFFF,value,size)
    def run(self):
        code,hooks=m.assemble(self.profile)
        words={m.CODE_START+i:int.from_bytes(code[i:i+4], 'big') for i in range(0,len(code),4)}
        hook,entry=hooks[0 if self.category else 1]
        self.hook=hook
        self.before = self.r.copy(); original_cr = self.cr
        outside = {a:v for a,v in self.mem.items() if not 0x10000 <= a < 0x11000}
        pc = entry
        for step in range(2_000_000):
            if pc == self.hook+4:
                break
            w = words[pc]; op=w>>26; rt=w>>21&31; ra=w>>16&31; rb=w>>11&31
            imm=self.signed(w,16); nextpc=pc+4
            if op in (14,15):
                self.r[rt] = ((self.r[ra] if ra else 0) + (imm << (16 if op==15 else 0))) & MASK64
            elif op in (32,34,40):
                self.r[rt] = self.get((self.r[ra]+imm)&MASK64,{32:4,34:1,40:2}[op])
            elif op in (48,50,52,54):
                address=(self.r[ra]+imm)&0xFFFFFFFF
                if op==48:self.f[rt]=struct.unpack('>d',struct.pack('>d',struct.unpack('>f',self.get(address,4).to_bytes(4,'big'))[0]))[0]
                elif op==50:self.f[rt]=self.get(address,8)
                elif op==52:
                    value=self.f[rt]
                    if isinstance(value,int):value=struct.unpack('>d',value.to_bytes(8,'big'))[0]
                    self.put(address,int.from_bytes(struct.pack('>f',value),'big'),4)
                else:
                    value=self.f[rt]
                    if isinstance(value,float):value=int.from_bytes(struct.pack('>d',value),'big')
                    self.put(address,value,8)
            elif op in (59,63):
                if w==0xFDA0048E:self.f[13]=self.fpscr
                elif w==0xFDFE6D8E:self.fpscr=self.f[13]
                elif w==0xEC006828:
                    self.f[0]=struct.unpack('>f',struct.pack('>f',self.f[0]-self.f[13]))[0]
                    self.fpscr ^= 0x82000000  # make restoration observable
                elif w==0xFC000210:self.f[0]=abs(self.f[0])
                else:raise AssertionError(f'Unsupported floating instruction {w:08x}')
            elif op == 36:
                self.put((self.r[ra]+imm)&MASK64,self.r[rt],4)
            elif op in (58,62):
                address=(self.r[ra]+self.signed(w & 0xFFFC,16)) & MASK64
                if op==58:self.r[rt]=self.get(address,8)
                else:
                    self.put(address,self.r[rt],8)
                    if w&1:self.r[ra]=address
            elif op==7:
                self.r[rt]=(self.r[ra]*imm)&MASK64
            elif op==10:
                left,right=self.r[ra]&0xFFFFFFFF,w&0xFFFF
                shift=28-4*(rt>>2)
                self.cr=(self.cr & ~(15<<shift)) | ((8 if left<right else 4 if left>right else 2)<<shift)
            elif op==21:
                sh,mb,me=rb,w>>6&31,w>>1&31
                mask=sum(1<<(31-i) for i in range(32) if (mb<=i<=me if mb<=me else i>=mb or i<=me))
                value=self.r[rt]&0xFFFFFFFF
                self.r[ra]=((value<<sh)|(value>>(32-sh))) & mask
            elif op==28:
                self.r[ra]=self.r[rt] & (w&0xFFFF)
                value=self.r[ra]
                self.cr=(self.cr&0x0FFFFFFF) | ((2 if value==0 else 8 if value>>63 else 4)<<28)
            elif op==18:
                nextpc=pc+self.signed(w&0x3FFFFFC,26)
            elif op==16:
                bo,bi=rt,ra
                bit=(self.cr>>(31-bi))&1
                if (bo==12 and bit) or (bo==4 and not bit):nextpc=pc+self.signed(w&0xFFFC,16)
                if bo not in (4,12):raise AssertionError('Unexpected BO')
            elif op==31:
                xo=w>>1&1023
                if xo==19:self.r[rt]=self.cr
                elif xo==144:self.cr=self.r[rt]&0xFFFFFFFF
                elif xo==32:
                    left,right=self.r[ra]&0xFFFFFFFF,self.r[rb]&0xFFFFFFFF
                    shift=28-4*(rt>>2)
                    self.cr=(self.cr&~(15<<shift)) | ((8 if left<right else 4 if left>right else 2)<<shift)
                elif xo==444:self.r[ra]=self.r[rt]|self.r[rb]
                elif xo==28:self.r[ra]=self.r[rt]&self.r[rb]
                elif xo==24:
                    shift=self.r[rb]&63;self.r[ra]=(self.r[rt]<<shift)&0xFFFFFFFF if shift<32 else 0
                elif xo==23:self.r[rt]=self.get(self.r[ra]+self.r[rb],4)
                elif xo==151:self.put(self.r[ra]+self.r[rb],self.r[rt],4)
                elif xo==40:self.r[rt]=(self.r[rb]-self.r[ra])&MASK64
                elif xo==266:self.r[rt]=(self.r[ra]+self.r[rb])&MASK64
                elif xo==459:self.r[rt]=(self.r[ra]&0xFFFFFFFF)//(self.r[rb]&0xFFFFFFFF)
                else:raise AssertionError(f'Unsupported XO {xo}')
            else:raise AssertionError(f'Unsupported opcode {op}')
            pc=nextpc
        else:raise AssertionError('Cave exceeded bounded instruction budget')
        assert self.cr==original_cr
        assert self.f==self.original_f
        assert self.fpscr==self.original_fpscr
        assert (self.lr,self.ctr)==self.original_control
        count_reg=24 if self.category else 27
        for r in range(32):
            if r not in (5,count_reg):assert self.r[r]==self.before[r],(r,hex(self.r[r]),hex(self.before[r]))
        assert self.r[5]==(3 if self.category else 1)
        writable=((0x10000,0x11000),(m.RECEIPT_START,m.RECEIPT_LIMIT))
        assert all(self.mem[a]==v for a,v in outside.items() if not any(lo<=a<hi for lo,hi in writable))
        pointer=self.before[1]+(0x110 if self.category else 0xF0)
        base,stride=(0x44,16) if self.category else (0x244,184)
        return [(self.get(pointer+4*i,4)-self.master-base)//stride for i in range(self.r[count_reg])]


class AbiTests(unittest.TestCase):
    def test_full_registers_cr_fprs_fpscr_stack_and_guarded_writes(self):
        for profile in m.PROFILES:
            for category in (False,True):
                for excluded in ([],[14],[2,14,24],[2,14,24,30]):
                    machine=MaskMachine(profile,category,excluded)
                    actual=machine.run()
                    if category:expected=[3] if {2,14,24}<=set(excluded) and 30 not in excluded else [3,6]
                    else:expected=[i for i in (2,14,24) if i not in excluded] or [2,14,24]
                    self.assertEqual(actual,expected)
                    receipt=m.RECEIPT_START+(0 if category else 24)
                    if excluded:
                        self.assertEqual(machine.get(receipt,4),8)
                    if len(excluded)==4:self.assertEqual(machine.get(receipt+16,4),1)
    def test_special_phases_are_byte_identical(self):
        for profile in m.PROFILES:
            for category in (False,True):
                for phase in (0,1,2,3,5):
                    machine=MaskMachine(profile,category,[2,14,24,30],phase)
                    self.assertEqual(machine.run(),[3,6] if category else [2,14,24])
                    self.assertEqual(bytes(machine.get(m.RECEIPT_START+i,1) for i in range(48)),bytes(48))

if __name__=='__main__':unittest.main()

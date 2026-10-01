"""Native PLAY scoring release gate. See pb/SCORING_CONTRACT.md.

PROVED OFFLINE: execute supplied USA executable instructions, including operand
callbacks, with game-plan scoring enabled. No scorer or decoder is substituted.
DESIGN: this certifies bounded PLAY consumers, not a running game or roster AI.
The caller supplies its executable, or NFL2K5_SCORING_XBE for stand-alone tools.
Missing Unicorn, executable, unsupported code, faults and budget expiry refuse.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import struct
import threading

from . import nfl2k5_playbook_inspector as ip
from .nfl2k5_cave_oracle import XbeImage

SCHEMA = 'nfl2k5-native-play-scoring/v1'
BOOK = 0xB75A40
SOURCE, STACK, STOP = 0x3000000, 0x303F000, 0x303FF00
TEAM, META, DIRECTION, STATE, ACTOR = (0x3020000+i*0x1000 for i in range(5))
CONTEXTS = (0, 1, 2, 3)


class ScoringError(ValueError):
    pass


@lru_cache(maxsize=4)
def _read_executable(path, size, mtime_ns):
    from .mod_build import _xbe_bytes
    return _xbe_bytes(Path(path))


def executable_bytes(source=None):
    if isinstance(source, bytes):
        return source
    source = source or os.environ.get('NFL2K5_SCORING_XBE')
    if source is None:
        raise ScoringError('Native PLAY scoring requires the source executable; supply xbe=bytes or NFL2K5_SCORING_XBE')
    source = Path(source)
    if source.is_dir():
        if source.name.casefold() == 'vc_53450030':
            source = source.parent
        source = source / 'default.xbe'
    stat = source.stat()
    return _read_executable(str(source.resolve()), stat.st_size, stat.st_mtime_ns)


class NativeScorer:
    def __init__(self, payload):
        try:
            import unicorn as uc
            from unicorn import x86_const as r
        except ImportError as exc:
            raise ScoringError('Unicorn is required for native PLAY scoring; install unicorn') from exc
        self.ucmod, self.r = uc, r
        self.m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        self.xbe_hash = hashlib.sha256(payload).hexdigest()
        image = XbeImage(payload)
        pins = json.loads(Path(__file__).with_name('nfl2k5_play_scoring_pins.json').read_text())
        for row in pins['ranges']:
            if hashlib.sha256(image.read(row['va'], row['size'])).hexdigest() != row['sha256']:
                raise ScoringError(f"Unsupported native scoring code/table at {row['va']:#x}")
        # Native data and BSS; no low/null page, Xbox kernel or physical-RAM alias.
        self.m.mem_map(0x10000, 0xF00000)
        self.m.mem_map(SOURCE, 0x40000)
        # Production owners add real XBE sections above retail's image. Map
        # only their declared pages, keeping kernel/physical aliases unmapped
        # and refusing any overlap with the isolated fixture address range.
        extra_pages = set()
        for section in image.sections:
            end = max(section.end, section.start+section.raw_size)
            if section.start < 0x10000 or end > SOURCE:
                raise ScoringError('Executable section lies outside the native scoring image area')
            extra_pages.update(range(max(0xF10000, section.start & ~0xfff), (end+0xfff)&~0xfff, 0x1000))
        for page in sorted(extra_pages):
            self.m.mem_map(page, 0x1000)
        for section in image.sections:
            if section.raw_size:
                self.m.mem_write(section.start, image.read(section.start, section.raw_size))
        self.m.reg_write(r.UC_X86_REG_CR0, self.m.reg_read(r.UC_X86_REG_CR0) & ~4)
        self.m.reg_write(r.UC_X86_REG_CR4, self.m.reg_read(r.UC_X86_REG_CR4) | 0x200)
        self.put(0xBE4E20, 0x521078)
        self.put(0xE60280, TEAM)
        self.put(0xE60284, TEAM)
        self.put(0xE602EC, STATE)
        self.put(TEAM+8, META)
        self.put(TEAM+12, META+0x100)
        self.put(TEAM+4, ACTOR)
        for slot in range(11):
            actor = ACTOR+slot*0x100
            self.m.mem_write(actor+0x2e, bytes([slot]))
            self.put(actor+0x34, actor+0x100 if slot < 10 else 0)
            self.put(actor+0x3c, META+0x800)
        self.put(META+12, DIRECTION)
        self.fput(DIRECTION+4, 1)
        self.fput(STATE+0x28, 10*91.44)
        self.put(0xC5D4AC, 9)  # active plan, including the special receiver-role branch
        for a in range(0xC5D4C0, 0xC5D508, 4):
            self.fput(a, 1)
        self.problem = None
        self.counts = Counter()
        self.m.hook_add(uc.UC_HOOK_MEM_INVALID, self.invalid)
        # Check effective table indices BEFORE reads, including mapped neighbours.
        self.guards = {
            0x281312: ('EAX', 11, 'carrier slot'),
            0x281343: ('EAX', 9, 'take-handoff scoring hole'),
            0x281607: ('EAX', 5, 'run tendency'),
            0x2816D9: ('EAX', 12, 'route type'),
            0x281712: ('EDX', 5, 'pass lateral zone'),
            0x281721: ('EAX', 4, 'pass depth zone'),
            0x281750: ('EAX', 4, 'receiver role'),
            0x2B6F50: ('ECX', 9, 'take-handoff position'),
            0x2B6F40: ('ECX', 18, 'lateral position'),
        }
        for pc in self.guards:
            self.m.hook_add(uc.UC_HOOK_CODE, self.guard, begin=pc, end=pc)
        # Environmental player-rating and matchup inputs. No PLAY reader,
        # score function, trajectory, compatibility or decoder is stubbed.
        self.environment = {0x246A80: (1.0, 4), 0xCB2D0: (0.0, 4)}
        self.environment_calls = Counter()
        for pc, (value, pop) in self.environment.items():
            # Different callbacks may share a trampoline: rewrite on entry.
            def supplied(m, address, size, _, self=self):
                value, pop = self.environment[address]
                self.environment_calls[hex(address)] += 1
                self.fput(STOP+0x60, value)
                m.mem_write(STOP+0x10, b'\xd9\x05'+struct.pack('<I',STOP+0x60)+b'\xc2'+struct.pack('<H',pop))
                m.reg_write(self.r.UC_X86_REG_EIP, STOP+0x10)
            self.m.hook_add(uc.UC_HOOK_CODE, supplied, begin=pc, end=pc)
        def roster(m, address, size, _):
            self.environment_calls[hex(address)] += 1
            sp = m.reg_read(r.UC_X86_REG_ESP)
            output = self.get(sp+12)
            for slot in range(11):
                self.put(output+slot*4, META+0x800)
            m.reg_write(r.UC_X86_REG_EAX, 1)
            m.reg_write(r.UC_X86_REG_EIP, self.get(sp))
            m.reg_write(r.UC_X86_REG_ESP, sp+20)
        self.m.hook_add(uc.UC_HOOK_CODE, roster, begin=0xE89F0, end=0xE89F0)

    def put(self, address, value):
        self.m.mem_write(address, struct.pack('<I', value & 0xffffffff))

    def get(self, address):
        return struct.unpack('<I', self.m.mem_read(address, 4))[0]

    def fput(self, address, value):
        self.m.mem_write(address, struct.pack('<f', value))

    def invalid(self, m, access, address, size, value, _):
        self.problem = dict(kind='unmapped-access', pc=hex(m.reg_read(self.r.UC_X86_REG_EIP)),
                            address=hex(address), size=size, access=access)
        return False

    def guard(self, m, pc, size, _):
        reg, limit, label = self.guards[pc]
        value = m.reg_read(getattr(self.r, 'UC_X86_REG_'+reg))
        if value >= limit:
            self.problem = dict(kind='out-of-domain-read', pc=hex(pc), operand=label,
                                value=value, valid=f'0..{limit-1}')
            m.emu_stop()

    def call(self, pc, *, args=(), **regs):
        r, m = self.r, self.m
        self.problem = None
        values = dict(ESP=STACK, EBP=0, EAX=0, EBX=0, ECX=0, EDX=0, ESI=0, EDI=0,
                      EFLAGS=0x202, FPCW=0x37F, FPTAG=0xFFFF, FPSW=0)
        values.update({k.upper(): v for k,v in regs.items()})
        for name, value in values.items():
            m.reg_write(getattr(r, 'UC_X86_REG_'+name), value)
        m.mem_write(STACK, struct.pack('<'+'I'*(1+len(args)), STOP, *args))
        self.counts[hex(pc)] += 1
        try:
            m.emu_start(pc, STOP, count=100000)
        except self.ucmod.UcError as exc:
            if self.problem is None:
                self.problem = dict(kind='native-fault', pc=hex(m.reg_read(r.UC_X86_REG_EIP)), error=str(exc))
        if self.problem:
            raise ScoringError(json.dumps(self.problem))
        if m.reg_read(r.UC_X86_REG_EIP) != STOP:
            raise ScoringError(f'Native instruction budget expired at {m.reg_read(r.UC_X86_REG_EIP):#x}')
        if m.reg_read(r.UC_X86_REG_ESP) != STACK+4+4*len(args):
            raise ScoringError(f'Native stack imbalance at {pc:#x}')
        return m.reg_read(r.UC_X86_REG_EAX)

    def sweep(self, resource):
        book = ip.parse_playbook_resource(resource)
        faults = []
        self.counts.clear()
        self.environment_calls.clear()
        self.m.mem_write(SOURCE, resource[32:])
        self.call(0x161E30, ecx=SOURCE, edx=0)
        self.put(TEAM+0x20, BOOK)
        for play in book.plays:
            pv = BOOK+ip.PLAY_BASE+play.index*96
            for pc in (0x1A9840, 0x1A9A80):
                value = self.call(pc, ecx=pv)
                if pc == 0x1A9840 and value:
                    faults.append(dict(play=play.index, name=play.name, routine=hex(pc), error=f'validator {value:#x}'))
            flags = self.get(pv+4)
            # Decode every handoff node, including non-primary carriers and
            # fakes, through the actual opcode callback for all flag values.
            for assignment in play.assignments:
                chain = self.get(pv+12+assignment.slot_index*8)
                for ni in range(assignment.declared_length):
                    node = chain+ni*8
                    op = self.m.mem_read(node, 1)[0]
                    if op not in (0x16, 0x17):
                        continue
                    for context in CONTEXTS:
                        self.call(0x2B6F70, ecx=node, edx=context, args=(SOURCE+0x18000,))
                        hole = struct.unpack('<f',self.m.mem_read(SOURCE+0x1801c,4))[0]
                        if not 0 <= hole <= 8:
                            faults.append(dict(play=play.index,name=play.name,slot=assignment.slot_index,node=ni,
                                               routine='0x2b6f70',context=context,hole=hole,error='handoff hole outside 0..8'))
            # Every play gets the defensive game-plan filter, both on/off and
            # all two-bit tendency combinations. It only consumes PLAY flags.
            for plan in range(8):
                self.put(0xC5D508, plan)
                self.call(0x281580, ecx=pv)
            kind = (flags >> 6) & 7
            # Run the shared offensive/defensive scorer for every play and
            # compatible formation. Kind >1 returns 1 before using arguments.
            compatible = []
            for formation in book.formations:
                fv = BOOK+ip.FORMATION_BASE+formation.index*ip.FORMATION_SIZE
                if self.call(0xE1440, ecx=BOOK, edx=pv, args=(fv,)):
                    compatible.append((formation.index, fv))
            for fi, fv in compatible or [(None, 0)]:
                if not fv and kind <= 1:
                    continue
                category = self.call(0xE1A80, ecx=BOOK, edx=fv) if fv else 0
                for profile in (0.0, 0.5):
                    for base in (0xBF1090, 0xBF1168, 0xBF12D0, 0xBF13A8):
                        self.m.mem_write(base, struct.pack('<54f', *([profile]*54)))
                    for context in CONTEXTS:
                        try:
                            self.call(0x208820, ecx=TEAM, edx=pv, args=(pv, fv, category, context))
                        except ScoringError as exc:
                            faults.append(dict(play=play.index,name=play.name,routine='0x208820',formation=fi,
                                               context=context,profile=profile,detail=self.problem,error=str(exc)))
            if kind:
                continue
            for plan in (0, 1, 9):
                self.put(0xC5D4AC, plan)
                for context in CONTEXTS:
                    # Run classifier also safely handles non-run offensive plays.
                    try:
                        self.call(0x2815F0, ecx=pv, edx=context)
                    except ScoringError as exc:
                        faults.append(dict(play=play.index, name=play.name, routine='0x2815f0', context=context,
                                           plan=plan,detail=self.problem, error=str(exc)))
            if not flags & 0x2000:
                continue
            # Every compatible formation, all mirror contexts and every native
            # receiver-role index. Field/down/score do not index these tables.
            for fi, fv in compatible:
                for context in CONTEXTS:
                    for role in (0, 8, 9, 10, 11):
                        self.m.mem_write(ACTOR+0x2c, bytes([role]))
                        for plan in (0, 1, 9):
                            self.put(0xC5D4AC, plan)
                            try:
                                self.call(0x281620, ecx=fv, edx=pv, args=(context, ACTOR))
                            except ScoringError as exc:
                                faults.append(dict(play=play.index, name=play.name, routine='0x281620',
                                                   formation=fi, context=context, role=role, plan=plan,
                                                   detail=self.problem, error=str(exc)))
        return dict(schema=SCHEMA, status='PROVED OFFLINE', resource_sha256=hashlib.sha256(resource).hexdigest(),
                    xbe_sha256=self.xbe_hash, plays=len(book.plays), contexts=list(CONTEXTS),
                    coverage=dict(run_plan_states=[0,1,9],pass_plan_states=[0,1,9],
                                  defense_plan_states=list(range(8)),receiver_roles=[0,8,9,10,11],
                                  shared_profiles=[0.0,0.5],formations='every compatible formation'),
                    calls=dict(self.counts), environment_calls=dict(self.environment_calls),
                    faults=faults, fault_count=len(faults), runtime_witness=False)


_local = threading.local()


@lru_cache(maxsize=128)
def _sweep_cached(resource, payload):
    digest = hashlib.sha256(payload).hexdigest()
    if getattr(_local, 'digest', None) != digest:
        _local.machine = NativeScorer(payload)
        _local.digest = digest
    return _local.machine.sweep(resource)


def sweep(resource, xbe=None):
    # Cache only complete executions, keyed by the exact PLAY and XBE bytes.
    # Return a fresh receipt so a caller cannot forge a later cached result.
    import copy
    return copy.deepcopy(_sweep_cached(resource, executable_bytes(xbe)))


def require_safe(resource, xbe=None):
    result = sweep(resource, xbe)
    if result['faults']:
        first = result['faults'][0]
        raise ScoringError(f"Native PLAY scoring rejected {result['fault_count']} cases: {first}")
    return result

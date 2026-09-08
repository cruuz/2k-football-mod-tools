"""Bounded scorebug entry research, never imported by the product.

The ordinary collection runs real reader/allocation/registration instructions.
OS completion, unrelated game subsystems, animation and world predicates are
explicit fixture boundaries. There is no kernel, GPU or played-game state here.
"""
from __future__ import annotations

from collections import Counter, deque
import hashlib
import struct

from tests.mod_editor.test_nfl2k5_scorebug_native import Collection
from tests.mod_editor.test_nfl2k5_scorebug_runtime import r, art
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tools.nfl2k5_scorebug_projection import StaticMachine, validate_native_code

BUSY, ENABLED, MODE = 0xb09584, 0xa95520, 0xe5ff80
PINS = (
    (0x64710, 0x2a3, "d86fda82f1c62088897a1cd41fb9cb9ef1672fade68611752fcc8f6304d4bdbe"),
    (0x62550, 0x1a, "16fd0f8a3a48888c85c139c826acd0498ebfaea395cdbf3a334a4da72ddc0ed4"),
    (0x432c0, 0x2f, "92ea290bc2112ee28246b4a9ad98ecc168a6c02a276c7b99c9cf70488f4eb14c"),
    (0x38cd0, 0x44, "588f1fa15476ba12749bdae3f12b4e2c0aac8a8942c5cee11d03e49a36fb1af0"),
    (0x38f50, 0x27, "d4451a9771925a57b0488cb9ac1bdff6ce9601f92c41b6bddd118846424e98d7"),
    (0x42fc0, 0x7, "0a241bbe0d59b5ffaa07c2d243438e9d5d8e7319ee22a3a88da735e725548af6"),
    (0x43880, 0x44, "a13e07259c5d864589639945432dd6f83d16cbd858a42e2e6e2e8de57632ec08"),
    (0x33410, 0xc, "6630143f0247ff687b29c47e8e90fe22a9e90489cee05ec98a04ea5b16478b3e"),
    (0x334e0, 0xe3, "3bac60c9614b374be737f2a414f2aec3df24c6b004dda28a7ba3e60cb879339c"),
    (0x33660, 0x23, "307d1b019d26cf3b1e66d8eee0ee9c68cb42c7c38dc57274f65ee08e54de2c0d"),
    (0x42c90, 0x83, "73cc2f063c131d58a1b1f9e0611bfd16238211640a60aff09320a17f7debe883"),
    (0x42d50, 0xa7, "5b6c027e4b039e94a612b81f3e816ce86ce8f8531715692af2eb6f7da39f3af9"),
    (0x42e40, 0x53, "5fddcdb2d38790e1e72156763d507f2728e6d6c074c8b67b07639b87b3b47248"),
    (0x442f0, 0xdc, "8484807689d031ec6e95e700b8dbe4a2b32c3004892e584d42cc9225a528ac3b"),
    (0x333c0, 0x43, "ea9839c2fe8c2c0dda6e19392e7941e061014f009209204790d31e45e1da2118"),
    (0x42c00, 0x59, "cffe48dbea515414bd1477b10d6fec07a23af3df7dda1c1e6bf477076bb13922"),
    (0x42e00, 0x37, "04395920fdf18be84bdd36c1bc58dd1a437c62762cccbcc0366b7d0909492edc"),
    (0x38570, 0xdd, "8f7ed40cef2d6a3aa5eededa3b75e86ec9ac195f1ff426441ee37b767bb3e4f7"),
    (0x43db0, 0x52, "ff3dc1dcdc4aa3695e767a387b4c5bb46c034504d827261f2a54f5d5a788d3f8"),
    (0x437e0, 0x7, "d6d7ddc26cd3ea8c7d0f051c6e5dc0b823663238f51083a7b199843eee8c7974"),
)


def validate(payload):
    validate_native_code(payload)
    if not r._abi_valid(payload):
        raise ValueError("foreign runtime ABI")
    image = XbeImage(payload)
    for va, size, sha in PINS:
        if hashlib.sha256(image.read(va, size)).hexdigest() != sha:
            raise ValueError(f"foreign entry/wait instructions at {va:#x}")


class Trace:
    """Counts plus at most 256 landmarks, 128 writes and the last 48 PCs."""
    def __init__(self, m):
        import unicorn
        self.m = m
        self.landmarks = {0x64710, 0x647e0, 0x647e5, 0x6499b, 0x649a5,
                          0xfccd0, 0xfce56, 0xfc1a0, 0xfce5b, 0xfce5c,
                          0xfce66, 0xfce70, 0xfcfa2, 0xfc9c0, 0xfcfa7,
                          0xfd427, 0x449e0, 0x443d0, 0x432d0, 0x43880, 0x43db0, 0x43de6,
                          0x42fc0, 0x438a1, 0x334e0, 0x335a3, 0x33660,
                          0x33410, 0x33414, *[m.labels[k] for k in r.HOOKS]}
        self.material_slots = {m.state + r.MATERIALS + side * 4 for side in (0, 1)}
        self.watched = {BUSY, ENABLED, 0xa83a1c, 0xa83a10, *self.material_slots}
        self.reset()
        self.handles = [
            m.uc.hook_add(unicorn.UC_HOOK_CODE, self.code),
            m.uc.hook_add(unicorn.UC_HOOK_MEM_WRITE, self.write),
            m.uc.hook_add(unicorn.UC_HOOK_MEM_READ, self.read),
        ]

    def reset(self):
        self.counts, self.polls = Counter(), Counter()
        self.events, self.writes, self.tail = [], [], deque(maxlen=48)
        self.steps = 0

    def code(self, _uc, pc, _size, _data):
        self.steps += 1
        self.counts[pc] += 1
        self.tail.append(pc)
        if pc in self.landmarks and len(self.events) < 256:
            self.events.append(dict(step=self.steps, pc=hex(pc), busy=self.m.get(BUSY),
                                    enabled=self.m.get(ENABLED)))

    def write(self, _uc, _access, address, size, value, _data):
        if address in self.material_slots and size == 4 and value:
            self.watched.add(value + 0x30)
        if address in self.watched and len(self.writes) < 128:
            self.writes.append(dict(step=self.steps, pc=hex(self.m.uc.reg_read(self.m.x.UC_X86_REG_EIP)),
                                    address=hex(address), size=size, value=hex(value)))

    def read(self, _uc, _access, address, size, _value, _data):
        if address in self.watched and size == 4:
            pc = self.m.uc.reg_read(self.m.x.UC_X86_REG_EIP)
            self.polls[(pc, address, self.m.get(address))] += 1

    def result(self):
        return dict(instructions=self.steps, final_pc=hex(self.m.uc.reg_read(self.m.x.UC_X86_REG_EIP)),
                    events=self.events, writes=self.writes, tail=[hex(pc) for pc in self.tail],
                    polls=[dict(pc=hex(pc), address=hex(address), value=hex(value), reads=n)
                           for (pc, address, value), n in sorted(self.polls.items())],
                    frequent_pcs=[dict(pc=hex(pc), visits=n) for pc, n in self.counts.most_common(12)])

    def close(self):
        for handle in self.handles:
            self.m.uc.hook_del(handle)
        self.handles.clear()


class EntryCollection(Collection):
    def __init__(self, payload, pack, receipt):
        super().__init__(payload, pack, end=art.HUD_START + receipt['outer_size_after'])
        self.payload, self.receipt = payload, receipt
        self.boundaries, self.handles = [], []
        self.trace = None

    def close(self):
        if self.trace is not None:
            self.trace.close()
        for handle in self.handles:
            self.m.uc.hook_del(handle)
        self.handles.clear()
        # Machine/Collection use callbacks that capture the machine. Close the
        # native engine promptly across repeated probes, even after assertion.
        self.m.uc = None

    def prepare_scene(self, retail_fonts):
        m = self.m
        image = XbeImage(self.payload)
        m.uc.mem_write(0xfc9c0, image.read(0xfc9c0, 780))
        # Actual native visibility/slide remains installed. Only world queries
        # and the animation controller outside this resource fixture are replaced.
        for va in (0xabe90, 0x72190, 0xa7940):
            m.uc.mem_write(va, bytes.fromhex('31c0c3'))
            self.boundaries.append(dict(pc=hex(va), result='world predicate = 0'))
        for va in (0xfbcc0, 0xa6300):
            m.uc.mem_write(va, bytes.fromhex('d9eec3'))
            self.boundaries.append(dict(pc=hex(va), result='world field float = 0'))
        m.uc.mem_write(0xfc700, b'\xc3')
        m.uc.mem_write(0x2f010, bytes.fromhex('c20400'))
        self.boundaries.extend([dict(pc='0xfc700', result='external field event omitted'),
                                dict(pc='0x2f010', result='startup animation selection omitted')])
        # Existing parser supplies relocated retail fonts. Appended private FONTs
        # have already been loaded and relocated by the actual native callbacks.
        StaticMachine.load_fonts(m, retail_fonts)
        record = art.RESOURCES['score_bug']
        span = self.pack[record['pack_offset']:record['pack_offset'] + record['span_size']]
        _chunk, decoded, _ = r.scene.decode(span)
        body = m.alloc(len(decoded))
        m.uc.mem_write(body, decoded)
        m.run(0x2f140, ecx=body + 256, limit=500000)
        m.run(0x43e30, (0,), ecx=body, edx=0, limit=500000)
        m.put(0xa6a9d0, 720)
        m.put(0xa6a9d4, 480)
        m.identity('16', '27')
        owner, node = m.alloc(32), m.alloc(32)
        m.put(0xe5fc20 + 12, owner)
        m.put(owner + 8, node)
        m.put(node + 4, 0xc00)
        m.put(0xe602b8, 12)
        m.put(ENABLED, 0)
        m.record = False
        self.trace = Trace(m)

    def hook_control(self, enabled):
        image = XbeImage(self.payload)
        for va, original in r.HOOKS.values():
            self.m.uc.mem_write(va, image.read(va, 5) if enabled else original)
            self.m.uc.ctl_remove_cache(va, va + 5)

    def entry(self, mode=4):
        """Execute every instruction of 64710, including its real scorebug call.

        Other subsystem calls at this parent are individually recorded host
        boundaries. This cannot establish their loader/GPU/world side effects.
        """
        import unicorn
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        m = self.m
        m.put(MODE, mode)
        m.put(0xa83a1c, 0)
        m.put(0xa83a10, 0)
        native = {0x61c50, 0x61c60, 0x62550, 0x66930, 0xfccd0}
        cleanup = {0x61c70: 8, 0x61c80: 8, 0x84eb0: 4, 0xfb0a0: 4}
        image = XbeImage(self.payload)
        skipped = {i.address: (int(i.op_str, 16), i.size)
                   for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(image.read(0x64710, 0x2a3), 0x64710)
                   if i.mnemonic == 'call' and int(i.op_str, 16) not in native}
        observed = []

        def boundary(_uc, pc, _size, _data):
            if pc not in skipped:
                return
            target, size = skipped[pc]
            consumed = cleanup.get(target, 0)
            observed.append(dict(pc=hex(pc), target=hex(target), stack_bytes=consumed, eax=0))
            m.uc.reg_write(m.x.UC_X86_REG_EAX, 0)
            m.uc.reg_write(m.x.UC_X86_REG_ESP, m.uc.reg_read(m.x.UC_X86_REG_ESP) + consumed)
            m.uc.reg_write(m.x.UC_X86_REG_EIP, pc + size)

        handle = m.uc.hook_add(unicorn.UC_HOOK_CODE, boundary, begin=0x64710, end=0x649b2)
        self.trace.reset()
        try:
            m.run(0x64710, limit=250000)
            return dict(trace=self.trace.result(), mode=mode, omitted_parent_calls=observed,
                        game_ready=[m.get(0xa83a1c), m.get(0xa83a10)], enabled=m.get(ENABLED))
        finally:
            m.uc.hook_del(handle)

    def frame(self):
        self.trace.reset()
        self.m.run(0xfce70, (0x3c888889,), limit=250000)
        return self.trace.result()

    def prepare_draw(self):
        """Supply field/camera inputs and stop only at scene/GPU submission.

        FONT selection, strings, ranges, glyph walks and vertices remain native.
        This extends the entry fixture beyond its former first-update return.
        """
        from mod_editor.core import nfl2k5_widescreen as wide
        m = self.m
        direction = m.alloc(32)
        m.float(direction + 4, 1)
        for score in (m.home, m.away):
            m.put(score + 12, direction)
        for team, context in ((0xe5fc20, r.HOME_CONTEXT), (0xe5fc60, r.AWAY_CONTEXT)):
            m.put(team + 0x1c, context)
        m.put(0xe60284, 0xe5fc60)
        StaticMachine.identity(m, home='NE', away='TB')
        m.float(m.play + 0x28, 914)
        m.float(m.play + 0x38, -1371.6)
        clock = m.alloc(64)
        m.put(0xe6028c, clock)
        m.float(clock + 16, 60)
        m.put(0xe602c4, 1)
        m.put(0xa6afb4, wide.ACTIVE_CAMERA_VA)
        for va, code, reason in (
                (wide.RENDER_LIST_VA, '31c0c3', 'scene submission boundary'),
                (0x8ab40, '31c0c3', 'world suppression predicate = 0'),
                (0x21860, '31c0c3', 'scorebug mesh submission boundary'),
                (0xfc760, 'd9eec3', 'field boundary = 0'),
                (0x2d2a0, 'c20c00', 'GPU text primitive begin'),
                (0x2cb90, 'c20800', 'GPU text texture coordinates'),
                (0x2cbe0, 'c3', 'GPU text color'),
                (0x2ca70, 'c3', 'GPU text vertex'),
                (0x2ca00, 'c3', 'GPU text primitive end')):
            m.uc.mem_write(va, bytes.fromhex(code))
            self.boundaries.append(dict(pc=hex(va), result=reason))

    def draw(self):
        import unicorn
        m, submissions = self.m, []

        def submit(_uc, pc, _size, _data):
            if pc == 0x47420:
                obj = m.uc.reg_read(m.x.UC_X86_REG_ECX)
                text = m.uc.reg_read(m.x.UC_X86_REG_EDX)
                submissions.append(dict(font=hex(m.get(obj)),
                                         text=StaticMachine.read_string(m, text), vertices=0))
            elif pc == 0x2ca70 and submissions:
                submissions[-1]['vertices'] += 1

        handle = m.uc.hook_add(unicorn.UC_HOOK_CODE, submit)
        m.put(0xa95524, 1)
        self.trace.reset()
        try:
            m.run(0xfc360, limit=250000)
            return dict(trace=self.trace.result(), submissions=submissions)
        finally:
            m.uc.hook_del(handle)

    def completion_pump(self, *, deliver=True):
        """Route host disk completions through the real 38f50/38cd0 pump.

        A guest thunk saves registers, calls the actual request callback and
        returns to the native callback table. Never recursively enter Unicorn,
        and never clear the loader flag on the host.
        """
        import unicorn
        m = self.m
        thunk, slots = m.STOP + 0x100, m.alloc(16)
        code = (b'\x9c\x60\x8b\x15' + struct.pack('<I', slots) +
                b'\xff\x35' + struct.pack('<I', slots + 4) +
                b'\xff\x15' + struct.pack('<I', slots + 8) + b'\x61\x9d\xc3')
        m.uc.mem_write(thunk, code)
        m.put(0xb04d1c, 1)
        m.put(0xb04d20, 0)
        m.put(0xb04d24, thunk)
        self.delivered = 0
        self.deliver = deliver

        def event(_uc, _pc, _size, _data):
            if not self.deliver or not self.pending:
                m.uc.reg_write(m.x.UC_X86_REG_EIP, thunk + len(code) - 1)
                return
            lo, size, callback, param, context, dst = self.pending.pop()
            body = self.pack[lo:lo + size]
            if len(body) != size:
                raise AssertionError('short fixture disk completion')
            m.uc.mem_write(dst, bytes(body))
            for offset, value in ((0, lo + size), (4, 0), (0x18, size), (0x1c, dst), (0x20, 0)):
                m.put(context + offset, value)
            m.put(slots, context)
            m.put(slots + 4, param)
            m.put(slots + 8, callback)
            self.delivered += 1
            if self.delivered > 1000:
                raise AssertionError('disk completion count exceeded')

        self.handles.append(m.uc.hook_add(unicorn.UC_HOOK_CODE, event, begin=thunk, end=thunk))


def gpu_fence(m, trace):
    """Build a bounded command-buffer input, then let native 334e0 arm it."""
    fence, commands, stream = m.alloc(32), m.alloc(0x340), m.alloc(256)
    start_out, end_out = m.alloc(8), m.alloc(8)
    m.put(fence, commands)
    m.put(commands + 0xc, stream)
    m.put(commands + 0x10, stream + 128)
    m.put(commands + 0x14, stream)
    m.put(commands + 0x18, stream + 256)
    trace.watched.update((fence + 8, stream, stream + 4, stream + 8))
    trace.reset()
    m.run(0x334e0, (end_out,), ecx=fence, edx=start_out, limit=1000)
    packet = struct.unpack('<3I', m.uc.mem_read(stream, 12))
    if packet != (0x81d8c, 0x33410, fence) or m.get(fence + 8) != 1:
        raise AssertionError('native fence packet/arming differs')
    return fence, stream


def special_lookup_context(c, field, state):
    """Prepend a synthetic native cache/index context to the real HUD list.

    Hashes are calculated by 38600. Ready entries reuse native loader-returned
    texture descriptors; pending entries must fall through to the resident HUD.
    These are valid branch inputs, not a capture of the tester's context list.
    """
    m = c.m
    descriptors = {}
    for root in c.registered:
        name = StaticMachine.read_string(m, m.get(root + 0x10))
        if name.startswith('sb--h'):
            descriptors[name] = m.get(root + 0x14)
    entries = []
    for count in range(4):
        m.run(0x38600, ecx=m.string(f'sb16h{count}'))
        entries.append((m.uc.reg_read(m.x.UC_X86_REG_EAX), descriptors[f'sb--h{count}']))
    context, special = m.alloc(128), m.alloc(0x200)
    m.put(context, m.context)
    m.put(context + 8, m.string('OTHER_COLLECTION'))
    m.put(context + field, special)
    m.put(0xb09578, context)
    if field == 0x10:
        header, records = m.alloc(128), m.alloc(4 * 32)
        m.put(special, header)
        m.put(special + 0x1a4, 4)
        m.put(special + 0x1ac, records)
        for i, (name_hash, descriptor) in enumerate(entries):
            at = records + i * 32
            body = m.alloc(64)
            m.put(at, state)
            m.put(at + 4, name_hash)
            m.put(at + 28, body)
            m.put(body + 32 + 0xc, int.from_bytes(b'TXTR', 'little'))
            m.put(body + 32 + 0x14, descriptor)
    elif field == 0x14:
        table = m.alloc(8 + 4 * 8 + 4 * 64)
        m.put(special + 4, state)
        m.put(special + 0xb0, table)
        m.put(table, 4)
        for i, (name_hash, descriptor) in enumerate(entries):
            m.put(table + 8 + i * 8, name_hash)
            m.put(table + 12 + i * 8, i * 64)
            m.uc.mem_write(table + 40 + i * 64, bytes(m.uc.mem_read(descriptor, 64)))
    else:
        raise ValueError('unknown native lookup context field')
    return special

"""Bounded native NV2A command capture, with explicit inherited-state gaps.

The fixture executes the retail material binder, texture state encoder, vertex
program upload and pixel-combiner upload. It is not a live PGRAPH capture.
"""
from pathlib import Path
import hashlib
import struct

ROOT = Path(__file__).resolve().parents[2]
GPU_CODE_PINS = (
    (0x23870, 0x243d0, '2dc78017dd47358122b47241dc0f636e6c6e66ee2cf091404f2bf927d9ff72b8'),
    (0x31430, 0x32540, '550a34c204f976bf29d7404bc001deb35040c85c86923ec5b19217491b0ced49'),
)


def methods(words):
    """Decode increasing/non-increasing NV2A method packets, rejecting jumps."""
    result = []
    i = 0
    while i < len(words):
        header = words[i]
        i += 1
        if header == 0:
            continue
        if header & 0xa0030003:
            raise ValueError('Unsupported FIFO control word: ' + hex(header))
        count = (header >> 18) & 0x7ff
        if not count or i + count > len(words):
            raise ValueError('Truncated NV2A packet')
        for j in range(count):
            result.append(dict(method=(header & 0x1ffc) + (0 if header & 0x40000000 else 4*j),
                               value=words[i+j], subchannel=(header >> 13) & 7))
        i += count
    return result


def capture_state(capture):
    import unicorn
    from mod_editor.core import nfl2k5_scorebug_ingame as scene
    from tools.scorebug_sprite.native import CODE_PINS
    m, body = capture['machine'], capture['body']
    for start, end, expected in CODE_PINS + GPU_CODE_PINS:
        if hashlib.sha256(bytes(m.uc.mem_read(start, end-start))).hexdigest() != expected:
            raise ValueError('Foreign native submission code at ' + hex(start))
    bucket, head, sink = m.alloc(0x400), m.alloc(128), m.alloc(0x20000)
    m.put(head, bucket)
    m.put(0xa6aa6c, head)
    mats = m.get(body + 0x120)
    m.put(bucket+4, m.get(mats+4))
    m.put(bucket+12, sink)
    # Force state caches dirty. These are CPU caches, not GPU register defaults.
    m.uc.mem_write(bucket+0x20, b'\x86' * 0x2c0)
    m.uc.mem_write(bucket+0x20, bytes(v ^ 255 for v in m.uc.mem_read(mats+0x60, 32)))
    # The caller's diffuse multiplier is not supplied by the CPU geometry harness.
    m.uc.mem_write(bucket+0x2e0, struct.pack('<4f', 1, 1, 1, 1))
    # Use owned resident vertex slots. Native upload still executes; allocator
    # addresses/list bookkeeping have no effect on the uploaded instructions.
    for anchor in (0xa6c708, 0xa6c6e8):
        m.put(anchor, anchor)
        m.put(anchor+4, anchor)
    slot = 0
    for index in range(15):
        program = m.get(0xa6c784+4*index)
        if program:
            m.run(0x31570, ecx=program)
            m.put(program+0x18, m.alloc(32))
            m.uc.mem_write(program+0x10, struct.pack('<HH', slot, 0))
            slot += struct.unpack('<H', m.uc.mem_read(program+0x14, 2))[0]
    replacements = {0x22950: bytes.fromhex('8b44240cc20c00'),
                    0x28110: bytes.fromhex('a16caaa600c3')}
    saved = {va: bytes(m.uc.mem_read(va, len(code))) for va, code in replacements.items()}
    rows = []
    def trace(_u, va, _size, _data):
        if va == 0x24160:
            sp = m.uc.reg_read(m.x.UC_X86_REG_ESP)
            mat = m.get(sp+8)
            rows.append(dict(material=(mat-mats)//128, name=m.read_string(m.get(mat)),
                             word_start=(m.get(bucket+12)-sink)//4,
                             material_words=list(struct.unpack('<32I', m.uc.mem_read(mat, 128)))))
    hook = m.uc.hook_add(unicorn.UC_HOOK_CODE, trace, begin=0x24160, end=0x24160)
    try:
        for va, code in replacements.items():
            m.uc.mem_write(va, code)
            m.uc.ctl_remove_cache(va, va+len(code))
        m.run(0x243d0, (mats, 0, 0), ecx=body+scene.layout.SHAPE,
              edx=capture['matrices'], limit=200000)
        size = m.get(bucket+12)-sink
        if not 0 <= size <= 0x20000:
            raise ValueError('Native GPU command sink exceeded')
        words = list(struct.unpack('<'+'I'*(size//4), m.uc.mem_read(sink, size)))
        state = {}
        constants = {}
        constant_at = 0
        program = []
        # Keep ordered packets as well as the last write to each register.
        for i, row in enumerate(rows):
            end = rows[i+1]['word_start'] if i+1 < len(rows) else len(words)
            begin = row['word_start'] if i else 0
            row['methods'] = methods(words[begin:end])
            for method in row['methods']:
                state[f"0x{method['method']:04x}"] = method['value']
                offset, value = method['method'], method['value']
                if offset == 0x1ea4:
                    constant_at = value*4
                if 0xb80 <= offset < 0xc00:
                    constants[str(constant_at)] = value
                    constant_at += 1
                if 0xb00 <= offset < 0xb80:
                    program.append(value)
            row['state'] = dict(state)
            row['vertex_constants'] = dict(constants)
            row['vertex_program'] = list(program)
        return dict(rows=rows, push_words=words, runtime_witnessed=False,
                    code_pins=[dict(start=hex(a),end=hex(b),sha256=h) for a,b,h in CODE_PINS + GPU_CODE_PINS],
                    inherited_complete=False,
                    fixture_assumptions=['Caller diffuse multiplier at bucket+0x2e0 = (1,1,1,1)',
                        'Owned resident vertex slots; native upload executes',
                        '22950 matrix upload replaced by already captured native geometry',
                        'No preceding game-frame FIFO/PGRAPH state supplied'],
                    boundaries=['caller diffuse multiplier', 'preceding game-frame GPU state',
                                'vertex-program evaluation and raster coverage'])
    finally:
        m.uc.hook_del(hook)
        for va, code in saved.items():
            m.uc.mem_write(va, code)
            m.uc.ctl_remove_cache(va, va+len(code))

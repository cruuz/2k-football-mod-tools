#!/usr/bin/env python3
"""Project broadcast scenes and reconstruct historical inputs with native FONT submissions.

This research tool is not imported by the application. Runtime code is applied
only to an in-memory CPU fixture. Geometry, text bindings and glyph submissions run on the CPU;
the final software raster is explicitly a model of unexecuted GPU state.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_ingame as r
from mod_editor.core import nfl2k5_scorebug_resources as art, nfl2k5_widescreen as wide
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from nfl_normshort3_positions import decode_position

AUDIT_CODE_PINS = (
    (0xfc010, 0xfc192, 'cf9082b794a40e3f908bbffe6c7cb7b87c5d8c549311e43b1366e1a45d8e28be', 'identity score quarter and clock callbacks'),
    (0xfc360, 0xfc6aa, '9170acbe42aa1311f72b7af90c56c4f3f7de0832421eec262e9ddd2d88ea3dcb', 'text draw table walks'),
    (0xfc7d0, 0xfc98e, '61eb66a3851ced7740b600c9b2ec8dc32c1fcfdb6c980ae7995b78407b23390a', 'down formatter'),
    (0xfccd0, 0xfce56, '3078ab47ceea380c8f254120c545d52f8db32b32d872a79f9966f47aabc022cf', 'scene and text setup'),
    (0xfc200, 0xfc32a, '94527caeaa8869858229bb24ea66f39025d0338110601c47b1d83e490c383da6', 'frame material visibility'),
    (0x46920, 0x469b0, 'eb1885e56619b0b7e653fa72af949e5ada2e8452bf19b1867dcc8591b267e7d7', 'text object defaults'),
)
STATIC_CALLS = ((0xfce56, bytes.fromhex('e845f3ffff')), (0xfcfa2, bytes.fromhex('e819faffff')))


def validate_native_code(payload):
    from nfl_main_menu_font import EXPECTED_RANGES
    font_names = {'font_slot_getter', 'font_range_glyph_lookup', 'quad_and_glyph_submit',
                  'font_assignment', 'utf16_glyph_walk', 'line_segment_draw', 'font_character_advance'}
    pins = list(AUDIT_CODE_PINS)
    pins.extend((start, end, sha, name) for name, start, end, sha in EXPECTED_RANGES if name in font_names)
    for start, end, sha, label in pins:
        off = r.layout.sbpos.va_to_off(payload, start)
        if r.digest(r.guard_bytes(payload, start, end-start)) != sha:
            raise ValueError('foreign native audit code: ' + label)
    for va, original in STATIC_CALLS:
        off = r.layout.sbpos.va_to_off(payload, va)
        if payload[off:off+len(original)] != original:
            raise ValueError('static audit refuses scorebug runtime or foreign hooks')
    return [dict(start=hex(start), end=hex(end), sha256=sha, label=label) for start, end, sha, label in pins]


class StaticMachine:
    """Bounded native CPU fixture for static or diagnostic runtime inputs.

    Scene relocation, name lookup, text bindings and score transforms run from
    the supplied executable. Heap, game state, font IDs and GPU boundaries are
    explicit fixture inputs. Nothing here is written back to an executable.
    """
    HEAP, STACK, STOP = 0x4000000, 0x5000000, 0x5010000

    def __init__(self, payload):
        import unicorn as uc
        from unicorn import x86_const as x
        self.x, self.uc = x, uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        pages = {}
        for s in image.sections:
            if not s.flags & 2:
                continue
            for page in range(s.start & -4096, (s.end + 4095) & -4096, 4096):
                flags = (uc.UC_PROT_READ | (uc.UC_PROT_EXEC if s.executable else 0)
                         | (uc.UC_PROT_WRITE if s.writable else 0))
                pages[page] = pages.get(page, 0) | flags
        self.uc.mem_map(image.base, 4096)
        self.uc.mem_write(image.base, payload[:image.headers_size])
        # Preserve the exact page permission union and every unmapped gap, but
        # avoid thousands of separate Unicorn regions for adjacent pages.
        # The latter made every repeated native FONT trial spend seconds in
        # mem_map before executing a single game instruction.
        regions = []
        for page, flags in sorted(pages.items()):
            if regions and regions[-1][1] == page and regions[-1][2] == flags:
                regions[-1][1] += 4096
            else:
                regions.append([page,page+4096,flags])
        for start, end, _flags in regions:
            self.uc.mem_map(start, end-start)
        for s in image.sections:
            if s.flags & 2:
                self.uc.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        for start, end, flags in regions:
            self.uc.mem_protect(start, end-start, flags)
        self.uc.mem_map(self.HEAP, 0x400000)
        self.uc.mem_map(self.STACK, 0x10000)
        self.uc.mem_map(self.STOP, 4096, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        self.cursor = self.HEAP
        self.visits, self.writes = [], []
        self._hooks = [self.uc.hook_add(uc.UC_HOOK_CODE, lambda _u, va, _s, _d: self.visits.append(va)),
                       self.uc.hook_add(uc.UC_HOOK_MEM_WRITE,
                                        lambda _u, _a, va, size, value, _d: self.writes.append((va, size, value)))]
        self.put(0xb09578, self.alloc(128))  # Native resource lookup context.
        self.put(0xb09590, 0)
        self.put(0xa6afb4, wide.ACTIVE_CAMERA_VA)
        self.home, self.away = self.alloc(64), self.alloc(64)
        self.put(0xe5fc28, self.home)
        self.put(0xe5fc68, self.away)
        self.clock, self.game_clock = self.alloc(64), self.alloc(64)
        self.put(0xe60294, self.clock)
        self.put(0xe6028c, self.game_clock)
        self.float(self.clock + 16, 12)
        self.float(self.game_clock + 16, 790)
        self.put(0xe602c4, 1)
        self.put(0xe60280, 0xe5fc20)
        self.put(0xe602b4, 4)
        self.play = self.alloc(512)
        self.put(0xe602ec, self.play)
        self.put(self.play + 4, 1)
        # E5FC28 is both the home-score owner and E5FC20+8's direction owner.
        # Keep one fixture object so home-score updates reach the native reader.
        direction_owner, direction = self.home, self.alloc(32)
        self.put(0xe5fc20 + 8, direction_owner)
        self.put(direction_owner + 12, direction)
        # Possession-colour cases exercise the away context too. Both use the
        # explicitly sampled field direction; FC200's display mode is separate.
        self.put(self.away + 12, direction)
        self.float(direction + 4, 1)
        self.float(self.play + 0x28, 914)  # Native ceiling formats this fixture as 10 yards.
        self.identity()

    def alloc(self, size):
        at = (self.cursor + 127) & -128
        self.cursor = at + size
        if self.cursor > self.HEAP + 0x400000:
            raise ValueError('bounded fixture heap exhausted')
        return at

    def close(self):
        # Break callback cycles promptly when a bounded fixture is finished.
        for hook in self._hooks:
            self.uc.hook_del(hook)
        self._hooks.clear()

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack('<I', value & 0xffffffff))

    def get(self, va):
        return struct.unpack('<I', self.uc.mem_read(va, 4))[0]

    def floats(self, va, count):
        return list(struct.unpack('<' + 'f' * count, self.uc.mem_read(va, count * 4)))

    def float(self, va, value):
        self.uc.mem_write(va, struct.pack('<f', value))

    def string(self, value):
        data = (value + '\0').encode('utf-16le')
        at = self.alloc(len(data))
        self.uc.mem_write(at, data)
        return at

    def read_string(self, at):
        data = bytearray()
        for i in range(256):
            unit = bytes(self.uc.mem_read(at + i * 2, 2))
            if unit == b'\0\0':
                return data.decode('utf-16le')
            data.extend(unit)
        raise ValueError('unterminated native fixture string')

    def identity(self, *, home='GB', away='OAK', home_code='11', away_code='20'):
        for context, name, code in ((0xb30864, home, home_code), (0xb30a58, away, away_code)):
            self.put(context + 0x10c, self.string(code))
            self.put(context + 0x13c, self.string(name))

    def run(self, va, args=(), limit=200000, **regs):
        sp = self.STACK + 0xf000
        self.uc.mem_write(sp, struct.pack('<' + 'I' * (len(args) + 1), self.STOP, *args))
        self.uc.reg_write(self.x.UC_X86_REG_ESP, sp)
        for name, value in regs.items():
            self.uc.reg_write(getattr(self.x, 'UC_X86_REG_' + name.upper()), value)
        self.visits.clear()
        self.writes.clear()
        self.uc.emu_start(va, self.STOP, count=limit)
        if self.uc.reg_read(self.x.UC_X86_REG_EIP) != self.STOP:
            raise AssertionError('native projection instruction bound exceeded')
        if self.uc.reg_read(self.x.UC_X86_REG_ESP) != sp + 4 + len(args) * 4:
            raise AssertionError('native projection stack imbalance')

    def load_texture(self, span):
        chunk, decoded, _ = r.decode(span)
        tex = r.tx.parse_texture(decoded, chunk)
        at = self.alloc(len(decoded))
        self.uc.mem_write(at, decoded)
        self.put(0xb120d8, at + chunk.system_bytes)
        self.run(0x43e30, (0x44dc0,), ecx=at, edx=0x44da0, limit=1000)
        return at + tex.descriptor_offset


    def load_fonts(self, fonts):
        # Host relocation is explicit. The parser proves every field-local
        # pointer; font selection, metrics and glyph walking run natively.
        self.fonts = {}
        for font in fonts:
            at = self.alloc(len(font.decoded))
            self.uc.mem_write(at, font.decoded)
            obj = at + font.object_offset
            self.put(obj + 8, at + font.range_offset)
            for row in font.ranges:
                self.put(at + row['record_offset'] + 4, at + row['glyph_records_offset'])
            self.put(0xa90ecc + 4 * font.slot, obj)
            self.fonts[obj] = font


    def load_private_font(self, span, font):
        """Real FONT registration/relocation, without writing a global slot."""
        original_slots = bytes(self.uc.mem_read(0xa90ecc, 9 * 4))
        chunk, decoded, _ = r.decode(span)
        at = self.alloc(len(decoded))
        self.uc.mem_write(at, decoded)
        self.put(0xb12074, at + chunk.system_bytes)
        self.run(0x43e30, (0x44b80,), ecx=at, edx=0x44b60, limit=30000)
        obj = self.get(at + 20)
        if obj != at + font.object_offset:
            raise ValueError('native private FONT descriptor differs from its serialized pointer')
        changed_slots = bytes(self.uc.mem_read(0xa90ecc, 9 * 4)) != original_slots
        if changed_slots:
            raise ValueError('private FONT registration changed the global FONT table')
        self.fonts[obj] = font
        return dict(name=font.name, object=hex(obj), span_sha256=r.digest(span),
                    range_pointer=hex(self.get(obj+8)), system_bytes=chunk.system_bytes,
                    video_bytes=chunk.video_bytes, global_slot_changed=changed_slots)


def private_font(span, source):
    """Parse installed metrics independently of the author's scale parameters."""
    from dataclasses import replace
    from nfl_main_menu_font import field_pointer, Glyph
    chunk, decoded, _ = r.decode(span)
    _, obj = field_pointer(decoded, 20, chunk.system_bytes)
    _, name_at = field_pointer(decoded, 16, chunk.system_bytes)
    text = decoded[name_at:obj].decode('utf-16le').split('\0')[0]
    minimum, maximum, count = struct.unpack_from('<HHI', decoded, obj)
    _, range_at = field_pointer(decoded, obj+8, chunk.system_bytes)
    glyphs, ranges = [], []
    for i in range(count):
        at = range_at + i*8
        first, last = struct.unpack_from('<HH', decoded, at)
        _, glyph_at = field_pointer(decoded, at+4, chunk.system_bytes)
        if not minimum <= first <= last <= maximum or glyph_at+(last-first+1)*96 > chunk.system_bytes:
            raise ValueError('private FONT glyph range exceeds its system buffer')
        ranges.append(dict(index=i, first_codepoint=first, last_codepoint=last,
                           record_offset=at, glyph_records_offset=glyph_at, glyph_count=last-first+1))
        for cp in range(first, last+1):
            off = glyph_at + (cp-first)*96
            glyphs.append(Glyph(cp, off, struct.unpack_from('<I',decoded,off)[0],
                                struct.unpack_from('<16f',decoded,off+16),
                                struct.unpack_from('<4f',decoded,off+80)))
    video = decoded[chunk.system_bytes:]
    pixels = source.width * source.height
    return replace(source, name=text, decoded=decoded, decoded_sha256=r.digest(decoded),
                   object_offset=obj, range_offset=range_at, minimum=minimum, maximum=maximum,
                   range_count=count, space_advance=struct.unpack_from('<I',decoded,obj+12)[0],
                   line_advance=struct.unpack_from('<I',decoded,obj+16)[0],
                   graphics_descriptor_offset=obj+64, glyphs=tuple(glyphs), ranges=tuple(ranges),
                   swizzled_indices=video[:pixels],
                   linear_indices=r.tx.unswizzle_2d(video[:pixels],source.width,source.height,1),
                   palette=video[pixels:pixels+64],palette_tail=video[pixels+64:])


def read_fonts(pack):
    """Read only the bounded FONT outer, using the existing pinned parser."""
    from nfl_outer import parse_archive, read_entry_bytes
    from nfl_scene_probe import record_from_header
    from nfl_main_menu_font import EXPECTED_FONTS, FONT_NAMES, parse_font
    archive = parse_archive(pack)
    resource = read_entry_bytes(archive, archive.entries[3], max_size=3_000_000)
    chunks = r.tx.parse_chunks(resource)
    fonts = []
    for slot, name in enumerate(FONT_NAMES[:9]):
        decoded, _ = r.tx.decode_chunk(resource, chunks[slot])
        sha = r.digest(decoded)
        if sha != EXPECTED_FONTS[name][4]:
            raise ValueError('foreign ' + name)
        record = record_from_header(archive, 3, slot, chunks[slot].offset, 'retail', None)
        fonts.append(parse_font(slot, name, record, decoded, sha))
    return fonts


def static_receipts(payload, spans, *, scorebug_folder=None):
    """Exact current-template replay and native overlapping decompression receipts."""
    patched, xbe_receipt = r.apply_xbe(payload, scorebug_folder=scorebug_folder)
    if r.apply_xbe(patched, scorebug_folder=scorebug_folder)[0] != patched:
        raise ValueError('static XBE replay changed bytes')
    m = StaticMachine(patched)
    resources = []
    try:
        for name in ('score_bug', 'score_buga'):
            before = spans[name]
            after, receipt = r.apply(before, name, scorebug_folder=scorebug_folder)
            if r.apply(after, name, scorebug_folder=scorebug_folder)[0] != after:
                raise ValueError('static resource replay changed bytes')
            chunk, decoded, _ = r.decode(after)
            size = chunk.system_bytes + chunk.video_bytes
            dst = m.alloc(size + chunk.overlap_scratch_bytes + 128)
            src = dst + size + chunk.overlap_scratch_bytes - chunk.stored_size
            m.uc.mem_write(src, after[32:])
            m.run(0x4dc00, ecx=src, edx=dst, limit=1000000)
            actual = bytes(m.uc.mem_read(dst, size))
            if actual != decoded or before[:32] != after[:32]:
                raise ValueError('native decompression or retail wrapper changed')
            resources.append({**receipt, 'decoded_sha256': r.digest(decoded),
                              'native_decoded_sha256': r.digest(actual), 'replay_identical': True,
                              'wrapper_plus_14_before': struct.unpack_from('<I', before, 20)[0],
                              'wrapper_plus_14_after': struct.unpack_from('<I', after, 20)[0]})
    finally:
        m.close()
    return dict(version=r.scene_version(scorebug_folder=scorebug_folder), static=True,
                v10=scorebug_folder is not None, native_refit_verified=True, pixel_match_claimed=False,
                xbe=xbe_receipt, xbe_replay_identical=True,
                runtime_hooks=[dict(va=hex(va), bytes=original.hex()) for va, original in STATIC_CALLS],
                resources=resources, temporary_disc_created=False)


from functools import lru_cache


@lru_cache(maxsize=4)
def _runtime_payload(payload, code_identity):
    # Cache the immutable writer result during coordinate trials. The key
    # includes the emitted hook bytes so authored variants cannot alias.
    from mod_editor.core import nfl2k5_scorebug_runtime as runtime
    return runtime.apply(payload)[0]


def native_geometry(payload, decoded, *, root=r.ROOT, widescreen=False, mode=0, slide=1.0,
                    score_transforms=True, score_phase=0.0, texture_span=None, fonts=None,
                    capture=None, baseline_v8=False, visible_elements=(0, 1),
                    score_values=(0, 0), previous_scores=(0, 0), baseline_v9=False,
                    runtime_textures=None, identity=None, timeouts=(3, 3), scorebug_folder=None, runtime_fonts=(),
                    possession='home', game_seconds=790, play_seconds=12, quarter=1,
                    ball_yards=50, visibility_state=None):
    """Run the actual scene relocator, setup, frame driver and camera activation.

    Startup animation selection, optional font IDs, per-frame game predicates
    and the GPU render-list boundary are replaced. Settled score transforms run
    by default. score_transforms=False reproduces the old harness omission.
    """
    if r.digest(decoded) == art.TEMPLATE_SCENE_SHA256 and scorebug_folder is None:
        from mod_editor.core.nfl2k5_scorebug_template import DEFAULT_FOLDER
        scorebug_folder = DEFAULT_FOLDER
    if scorebug_folder is not None and (baseline_v8 or baseline_v9 or runtime_textures is not None):
        raise ValueError('v10 folder scene cannot use historical or exact runtime bindings')
    validate_native_code(payload)
    if widescreen:
        payload = wide.apply(payload)[0]
    payload = r.apply_xbe(payload, scorebug_folder=scorebug_folder)[0]
    if baseline_v8 or baseline_v9:
        # Reconstruct the historical data fields in this CPU fixture only.
        # First undo the v9-only fields, then install the retained v8 specs.
        buf = bytearray(payload)
        for va, old, _new, _label in r.xbe_specs():
            off = r.layout.sbpos.va_to_off(payload, va)
            buf[off:off + len(old)] = old
        for va, _old, new, _label in r.xbe_specs(baseline_v8=baseline_v8, baseline_v9=baseline_v9):
            off = r.layout.sbpos.va_to_off(payload, va)
            buf[off:off + len(new)] = new
        for section in r.bs._sections(buf):
            off = section.header_offset + 36
            buf[off:off + 20] = r.bs.section_digest(buf, section)
        payload = bytes(buf)
    if runtime_textures is not None:
        if baseline_v8 or baseline_v9:
            raise ValueError('historical scene cannot use the current runtime')
        from mod_editor.core import nfl2k5_scorebug_runtime as runtime
        payload = _runtime_payload(payload, runtime.code_for(0, 0)[0])
    m = StaticMachine(payload)
    if possession not in ('home','away'):
        m.close()
        raise ValueError('unknown possession fixture side')
    m.put(0xe60280,0xe5fc20 if possession == 'home' else 0xe5fc60)
    if identity is not None:
        m.identity(**identity)
    m.put(m.home, score_values[0])
    m.put(m.away, score_values[1])
    m.float(m.game_clock + 16, game_seconds); m.float(m.clock + 16, play_seconds)
    m.put(0xe602c4, quarter)
    m.put(0xe5fc20 + 0x1c, 0xb30864); m.put(0xe5fc60 + 0x1c, 0xb30a58)
    m.put(0xe60284, 0xe5fc60 if possession == 'home' else 0xe5fc20)
    # FBA40 uses the native field coordinate, positive from midfield toward
    # the possessing team's goal (one yard = 91.44 native distance units).
    m.float(m.play + 0x38, (ball_yards - 50) * 91.44)
    m.put(m.home + 4, timeouts[0]); m.put(m.away + 4, timeouts[1])
    loaded_textures = {}
    if texture_span is not None:
        loaded_textures[hex(m.load_texture(texture_span))] = texture_span
    for span in runtime_textures or ():
        loaded_textures[hex(m.load_texture(span))] = span
    m.uc.mem_write(r.layout.sbpos.X_SLOT, struct.pack('<2f', *root))
    body = m.alloc(len(decoded)); m.uc.mem_write(body, decoded)
    # No startup animation controller or font renderer in this geometry fixture.
    m.uc.mem_write(0x2f010, bytes.fromhex('c20400'))
    m.run(0x2f140, ecx=body + 256, limit=500000)
    m.run(0x43e30, (0,), ecx=body, edx=0, limit=500000)
    if fonts is None:
        m.uc.mem_write(0xef850, bytes.fromhex('b801000000c3'))
    else:
        m.load_fonts(fonts)
    private_receipts = []
    if runtime_fonts:
        if runtime_textures is None or fonts is None or scorebug_folder is not None:
            raise ValueError('private fonts require the exact runtime and retail font sources')
        from mod_editor.core import nfl2k5_scorebug_fonts as scoped
        for span, (slot, _sx, _sy) in zip(runtime_fonts, scoped.SCALES):
            private_receipts.append(m.load_private_font(span, private_font(span, fonts[slot])))
    m.put(0xa6a9d0, 720); m.put(0xa6a9d4, 480)
    m.run(0xfccd0, limit=500000)
    instance = m.get(0xa9552c)
    if instance != body + 352:
        raise ValueError('native scene instance identity changed')
    # The frame driver still executes all native transforms and root operands.
    # Explicit geometry sample; the binding/draw audit below runs separately.
    if visibility_state is None:
        m.uc.mem_write(0xfc9c0, bytes.fromhex('c20400'))
    else:
        configure_visibility(m, visibility_state)
    m.put(0xa95870, mode)
    m.run(0xfc200)
    for i in range(2):
        record = 0xa9594c + i * 0x38
        m.put(record + 0x30, int(score_transforms))
        m.float(record + 0x2c, score_phase)
        cached = (str(previous_scores[i]) + '\0').encode('utf-16le')
        if len(cached) > 12:
            raise ValueError('score fixture exceeds native cache capacity')
        m.uc.mem_write(record + 0x20, cached)
    for i in range(6):
        record = r.layout.ELEMENT_RECORDS + i * 0x70
        # +58 is binding availability, not requested visibility. Retail
        # FC360 and the material updater both use the current slide at +3C.
        # The old fixture disabled text but left every background fully open.
        m.put(record + 0x38, int(i in visible_elements))
        m.float(record + 0x3c, (30 * slide if i == 0 else m.floats(record + 0x30, 1)[0])
                if i in visible_elements else m.floats(record + 0x2c, 1)[0])
    m.run(0xfce70, (0,), limit=500000)
    visibility_trace = []
    if visibility_state is not None:
        for step in range(40):
            m.run(0xfce70, (struct.unpack('<I', struct.pack('<f', 1/60))[0],), limit=500000)
            visibility_trace.append(dict(frame=step, requests=[m.get(r.layout.ELEMENT_RECORDS+i*0x70+0x38) for i in range(6)],
                slides=[m.floats(r.layout.ELEMENT_RECORDS+i*0x70+0x3c, 1)[0] for i in range(6)]))
    frame_instructions = len(m.visits)
    matrices = m.get(instance + 0x14)
    m.run(0x22c00, (body + r.layout.SHAPE, matrices), limit=10000)
    m.uc.mem_write(wide.RENDER_LIST_VA, bytes.fromhex('31c0c3'))
    m.run(0x2ac80, ecx=0xa95530, limit=10000)
    def floats(va, count):
        return struct.unpack('<' + 'f' * count, m.uc.mem_read(va, count * 4))
    camera = floats(wide.ACTIVE_CAMERA_VA + 0xf0, 16)
    def project(p):
        p = (*p, 1)
        result = [sum(p[j] * camera[j * 4 + i] for j in range(4)) for i in range(4)]
        # Explicit active-area crop, not an assumption of a 640-pixel framebuffer.
        return [result[0] / result[3] - r.HUD_INSET[0], result[1] / result[3]]
    scale = floats(body + r.layout.SHAPE + 0x1c, 1)[0]
    bias = floats(body + r.layout.SHAPE + 0x10, 3)
    positions, world_positions = [], []
    for v in range(r.layout.VCOUNT):
        q = struct.unpack_from('<3h', decoded, r.layout.S0 + v * 6)
        point = (*decode_position(q, scale, bias), 1)
        index = struct.unpack_from('<h', decoded, r.layout.S1 + v * 10 + 8)[0] // 3
        palette = floats(0xafa710 + index * 48, 12)
        world = [sum(point[j] * palette[i * 4 + j] for j in range(4)) for i in range(3)]
        world_positions.append(world)
        positions.append(project(world))
    anchors = {}
    for name in (r.V8_ANCHORS if baseline_v8 else r.V9['ANCHORS'] if baseline_v9 else r.V10['ANCHORS'] if scorebug_folder is not None else r.ANCHORS):
        out = m.alloc(16)
        m.run(0xfb640, ecx=out, edx=0x4f6950, eax=matrices + r.layout.T[name] * 64)
        anchors[name] = project(floats(out, 3))
    def bounds(indices):
        points = [positions[i] for i in indices]
        return [min(p[0] for p in points), min(p[1] for p in points),
                max(p[0] for p in points), max(p[1] for p in points)]
    materials = []
    scene = m.get(0xa95528)
    for i in range(m.get(scene + 0x1c)):
        at = m.get(scene + 0x20) + i * 128
        materials.append(dict(name=m.read_string(m.get(at)), flags=hex(m.get(at + 8)),
                              visible=not bool(m.get(at + 8) & 1), texture=hex(m.get(at + 0x30))))
    visible = {row['name'] for row in materials if row['visible']}
    objects = {}
    for k, indices in r.layout.strips(decoded):
        lo, hi, name = r.layout.SUBMESHES[k]
        if name not in visible:
            continue
        live = set()
        for j in range(len(indices) - 2):
            triangle = indices[j:j + 3]
            a, b, c = [positions[v] for v in triangle]
            if abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) > 1e-6:
                live.update(triangle)
        objects[name] = bounds(sorted(live) if live else range(lo, hi + 1))
    frame_name = next(name for name in ('yscore_buga', 'yscore_buga1') if name in visible)
    root_matrix = list(floats(matrices, 16))
    viewport = list(floats(wide.ACTIVE_CAMERA_VA + 0x250, 8))
    if capture is not None:
        capture.update(machine=m, matrices=matrices, body=body, project=project,
                       texture_spans=loaded_textures, private_fonts=private_receipts)
    else:
        m.close()
    return dict(schema='nfl2k5_scorebug_native_projection/v2', experimental=True, runtime_witnessed=False,
                coordinate_system='720x480 framebuffer, crop x=40..680 to a 640x480 comparison',
                root=list(root), native_root_matrix=root_matrix,
                native_camera=list(camera), hud_viewport=viewport,
                positions=positions, world_positions=world_positions, anchors=anchors,
                materials=materials, objects=objects, score_transforms=score_transforms,
                scorebug_runtime_installed=runtime_textures is not None, private_fonts=private_receipts,
                possession=possession,
                static_version='espn-reference-v8' if baseline_v8 else 'espn-reference-v9' if baseline_v9 else r.scene_version(scorebug_folder=scorebug_folder),
                score_phase=score_phase, score_values=list(score_values), previous_scores=list(previous_scores),
                visible_elements=list(visible_elements),
                native_visibility=visibility_state, visibility_trace=visibility_trace,
                frame=objects[frame_name], frame_material=frame_name,
                clock=bounds(range(48, 64)), down=bounds(range(64, 80)),
                frame_instructions=frame_instructions, widescreen=widescreen, mode=mode,
                text_scale_x=27 / 32 if widescreen else 1,
                scene_sha256=r.digest(decoded),
                limitations=['CPU fixture, not console execution', 'GPU state and rasterization not executed',
                             'per-frame gameplay predicates replaced', 'explicit score phase sample'])


def configure_visibility(m, state):
    """World inputs around the real FC9C0; never replace its visibility logic.

    Requests, slide integration and material gates all run natively. Only
    unrelated game/world queries and the direction-placement decision are
    supplied. The latter is tested independently in both placement modes.
    """
    allowed = {'pre_snap', 'after_play', 'live', 'kickoff', 'flag', 'fumble'}
    if state not in allowed:
        raise ValueError('unknown native visibility state')
    for va in (0xabe90, 0x72190, 0xa7940, 0xff340):
        m.uc.mem_write(va, bytes.fromhex('31c0c3'))
    m.uc.mem_write(0xa6300, bytes.fromhex('d9eec3'))
    m.uc.mem_write(0xfc700, b'\xc3')
    m.put(0xe602b8, 14 if state in ('live', 'kickoff', 'fumble') else 12)
    m.put(0xba2f14, int(state == 'after_play'))
    m.put(m.clock + 0x18, 6 if state in ('after_play','live','fumble') else 0)
    m.put(m.play + 0x160, int(state == 'flag'))
    m.put(m.play + 0x198, int(state == 'fumble'))
    context, record = m.alloc(32), m.alloc(32)
    m.put(context + 8, record); m.put(record + 4, (10 if state == 'kickoff' else 0) << 8)
    for owner in (0xe5fc20, 0xe5fc60): m.put(owner + 0xc, context)


def native_text_draw(capture, *, shadow_offset=None):
    """Capture FC360's actual strings and native FONT glyph submissions.

    FC360, its table walks, formatters, colour/position/alignment setters and
    score-object matrix setup execute natively. World predicates, scene
    submission and immediate GPU submission are fixture replacements.
    """
    import unicorn
    m, body = capture['machine'], capture['body']
    for va in (0x8ab40, 0x21860):
        m.uc.mem_write(va, bytes.fromhex('31c0c3'))
    m.uc.mem_write(0xfc760, bytes.fromhex('d9eec3'))  # Fixture field boundary = 0.
    if not getattr(m, 'fonts', None):
        raise ValueError('native text audit requires the pinned retail FONT resources')
    for va, code in ((0x2d2a0, 'c20c00'), (0x2cb90, 'c20800'),
                     (0x2cbe0, 'c3'), (0x2ca70, 'c3'), (0x2ca00, 'c3')):
        m.uc.mem_write(va, bytes.fromhex(code))
    m.put(0xa95524, 1)
    bindings = []
    for index in range(5):
        va = 0xa95884 + index * 0x28
        node = m.get(va + 0x18)
        bindings.append(dict(record=hex(va), name=m.read_string(m.get(va - 4)),
                             callback=hex(m.get(va)), enabled=bool(m.get(va + 0x20)),
                             node_index=(node - body - r.layout.TBASE) // 112 if node else None))
    draws = []
    callback = [None]
    primitive = dict(matrix=None, color=0xffffffff, uv=None)
    callbacks = {m.get(0xa95884 + i * 40) for i in range(5)}
    callbacks.update(m.get(0xa959c8 + i * 112 + 4) for i in range(6))
    callbacks.update((0xfc050, 0xfc070))
    def trace(_u, va, _size, _data):
        if va in callbacks:
            callback[0] = hex(va)
        if va == 0x47420:
            text = m.read_string(m.uc.reg_read(m.x.UC_X86_REG_EDX))
            obj = m.uc.reg_read(m.x.UC_X86_REG_ECX)
            # Cached score frames do not call their formatter. Attribute their
            # glyphs to the actual score record, not the previous clock callback.
            record = m.uc.reg_read(m.x.UC_X86_REG_ESI) - 0x14
            if obj != 0xa957f0 and record in (0xa9594c, 0xa95984):
                callback[0] = hex(m.get(record))
            if shadow_offset is not None:
                m.uc.mem_write(obj + 0x30, struct.pack('<3f', *shadow_offset))
            position = m.floats(obj + 16, 3)
            matrix = m.get(obj + 0x60)
            draws.append(dict(callback=callback[0], text=text, position=position,
                              matrix=m.floats(matrix, 16) if matrix else None,
                              screen=capture['project'](position),
                              shadow_offset=m.floats(obj + 0x30, 3), color=hex(m.get(obj + 0x20)),
                              align=m.get(obj + 0x64), vertical_align=m.get(obj + 0x68),
                              font=m.fonts[m.get(obj)].name, vertices=[]))
        elif va == 0x2d2a0:
            sp = m.uc.reg_read(m.x.UC_X86_REG_ESP)
            matrix = m.get(sp + 12)
            primitive['matrix'] = m.floats(matrix, 16) if matrix else None
        elif va == 0x2cbe0:
            primitive['color'] = m.uc.reg_read(m.x.UC_X86_REG_ECX)
        elif va == 0x2cb90:
            sp = m.uc.reg_read(m.x.UC_X86_REG_ESP)
            primitive['uv'] = m.floats(sp + 4, 2)
        elif va == 0x2ca70:
            p = m.floats(m.uc.reg_read(m.x.UC_X86_REG_ECX), 4)
            matrix = primitive['matrix']
            if matrix:
                p[3] = 1
                p = [sum(p[j] * matrix[j * 4 + i] for j in range(4)) for i in range(4)]
            draws[-1]['vertices'].append(dict(world=p[:3], screen=capture['project'](p[:3]),
                                              uv=list(primitive['uv']), color=hex(primitive['color'])))
    hook = m.uc.hook_add(unicorn.UC_HOOK_CODE, trace)
    try:
        m.run(0xfc360, limit=200000)
        instructions = len(m.visits)
    finally:
        m.uc.hook_del(hook)
    return dict(bindings=bindings, draws=draws, draw_instructions=instructions)


def native_team_binding_audit(capture):
    """All 32 team inputs leave FC1A0's fixed material texture table unchanged."""
    import unicorn
    m = capture['machine']
    scene = m.get(0xa95528)
    rows = [m.get(scene + 0x20) + i * 128 for i in range(m.get(scene + 0x1c))]
    names = [m.read_string(m.get(at)) for at in rows]
    context_reads = []
    hook = m.uc.hook_add(unicorn.UC_HOOK_MEM_READ,
                        lambda _u, _a, va, size, _v, _d: context_reads.append((va, size)),
                        begin=0xb30864, end=0xb30a58 + 0x194)
    cases = []
    try:
        for team, record in art.TEAM_LOGOS.items():
            context_reads.clear()
            m.identity(home=team, away=team, home_code=record['asset_code'], away_code=record['asset_code'])
            m.run(0xfc1a0, limit=20000)
            cases.append(dict(team=team, asset_code=record['asset_code'],
                              context_reads=list(context_reads),
                              textures={name: hex(m.get(at + 0x30)) for name, at in zip(names, rows)},
                              instructions=len(m.visits)))
    finally:
        m.uc.hook_del(hook)
        m.identity()
    return cases


def reference_rails(widescreen=False, *, scorebug_folder=None):
    rails = [84, 381, 560, 429] if scorebug_folder is not None else list(r.exact.RAILS)
    if widescreen:
        for i in (0, 2):
            rails[i] = 320 + (rails[i] - 320) * 27 / 32
    return rails


def containment_failures(geometry, rails=None, tolerance=2):
    """Acceptance predicate covering every nondegenerate visible object/glyph."""
    if rails is None:
        rails = reference_rails(geometry['widescreen'], scorebug_folder=(
            True if geometry.get('static_version') in
            (r.TEMPLATE_VERSION, 'espn-reference-v8', 'espn-reference-v9') else None))
    def outside(box):
        return any((box[0] < rails[0] - tolerance, box[1] < rails[1] - tolerance,
                    box[2] > rails[2] + tolerance, box[3] > rails[3] + tolerance))
    failures = {}
    for name, box in geometry['objects'].items():
        if box[2] - box[0] > .01 and box[3] - box[1] > .01 and outside(box):
            failures[name] = box
    for draw in geometry.get('draws', []):
        if draw['vertices'] and any(int(v['color'], 16) >> 24 for v in draw['vertices']):
            points = [v['screen'] for v in draw['vertices']]
            box = [min(p[0] for p in points), min(p[1] for p in points),
                   max(p[0] for p in points), max(p[1] for p in points)]
            if outside(box):
                failures[draw['callback'] + ':' + draw['text']] = box
    return failures


def render_native(decoded, texture_span, fonts, geometry, path, *, cull_positive=False,
                  texture_spans=None, background=None, calibration=None):
    """Software diagnostic of captured inputs; GPU blend/cull policy is explicit.

    Native FONT quads, UVs and colours replace all fabricated preview strings.
    Scene UVs use SHAP's real scale/bias and each vertex's D3DCOLOR. The simple
    depth/alpha sampler is a model, not an NV2A rasterizer. Optional culling is
    a hypothesis image, never silently treated as a proved hardware state.
    """
    import math
    from PIL import Image, ImageDraw
    from nfl_main_menu_font import rgba_from_font
    size = tuple(calibration['size']) if calibration is not None else (640, 480)
    if len(size) != 2 or any(type(v) is not int or not 1 <= v <= 2048 for v in size):
        raise ValueError('native raster size exceeds the bounded diagnostic canvas')
    sx, sy, offset_x, offset_y = calibration['affine'] if calibration is not None else (1, 1, 0, 0)
    if not all(math.isfinite(v) for v in (sx, sy, offset_x, offset_y)) or not (0 < sx <= 4 and 0 < sy <= 4):
        raise ValueError('invalid native raster calibration')
    im = (background.convert('RGBA').copy() if background is not None else
          Image.new('RGBA', size, (44, 83, 39, 255)))
    if im.size != size:
        raise ValueError('native raster background size differs from the diagnostic canvas')
    width, height = size
    draw = ImageDraw.Draw(im)
    if background is None:
        for x in range(0, 640, 80):
            draw.line((x, 0, x + 95, 480), fill=(224, 235, 215, 255), width=2)
    depth = [float('inf')] * (width * height)
    pixels = im.load()
    chunk, body, _ = r.decode(texture_span)
    tex = r.tx.parse_texture(body, chunk)
    atlas = Image.frombytes('RGBA', (tex.width, tex.height), r.tx.texture_to_rgba(body, chunk, tex))
    material_atlases = {}
    texture_receipts = {}
    for descriptor, span in (texture_spans or {}).items():
        chunk, body, _ = r.decode(span)
        tex = r.tx.parse_texture(body, chunk)
        material_atlases[descriptor] = Image.frombytes('RGBA', (tex.width, tex.height),
                                                      r.tx.texture_to_rgba(body, chunk, tex))
        texture_receipts[descriptor] = dict(name=tex.name, span_sha256=r.digest(span),
                                            dimensions=[tex.width, tex.height])
    font_atlases = {font.name: Image.frombytes('RGBA', (font.width, font.height), rgba_from_font(font))
                    for font in fonts}
    def color(word):
        return ((word >> 16) & 255, (word >> 8) & 255, word & 255, word >> 24)
    def triangle(texture, points, uvs, colors, zs, *, cull=False):
        points = [(x * sx + offset_x, y * sy + offset_y) for x, y in points]
        (ax, ay), (bx, by), (cx, cy) = points
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(area) < 1e-6 or (cull and area > 0):
            return
        x0, x1 = max(0, math.floor(min(ax, bx, cx))), min(width-1, math.ceil(max(ax, bx, cx)))
        y0, y1 = max(0, math.ceil(16*sy+offset_y), math.floor(min(ay, by, cy))), min(height-1, math.floor(464*sy+offset_y)-1, math.ceil(max(ay, by, cy)))
        texels = texture.load()
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                # Pixel centres; small edge differences from NV2A remain unproved.
                px, py = x + .5, y + .5
                w1 = ((px - ax) * (cy - ay) - (cx - ax) * (py - ay)) / area
                w2 = ((bx - ax) * (py - ay) - (px - ax) * (by - ay)) / area
                weights = (1 - w1 - w2, w1, w2)
                if min(weights) < -1e-6:
                    continue
                z = sum(w * v for w, v in zip(weights, zs))
                at = y * width + x
                if z > depth[at] + .001:
                    continue
                uv = [sum(weights[i] * uvs[i][k] for i in range(3)) for k in range(2)]
                tx, ty = uv[0] * texture.width - .5, uv[1] * texture.height - .5
                ix, iy = math.floor(tx), math.floor(ty)
                fx, fy = tx - ix, ty - iy
                sample = [0.] * 4
                for dx, dy, w in ((0, 0, (1-fx)*(1-fy)), (1, 0, fx*(1-fy)),
                                  (0, 1, (1-fx)*fy), (1, 1, fx*fy)):
                    rgba = texels[min(texture.width-1, max(0, ix+dx)),
                                  min(texture.height-1, max(0, iy+dy))]
                    for k in range(4):
                        sample[k] += rgba[k] * w
                rgba = [sample[k] * sum(weights[i] * colors[i][k] for i in range(3)) / 255
                        for k in range(4)]
                if rgba[3] < 1:
                    continue
                a = rgba[3] / 255
                background = pixels[x, y]
                pixels[x, y] = tuple(round(rgba[k] * a + background[k] * (1-a)) for k in range(3)) + (255,)
                depth[at] = z
    uv_transform = struct.unpack_from('<4f', decoded, r.layout.SHAPE + 0x30)
    uv, colors = [], []
    for i in range(r.layout.VCOUNT):
        offset = r.layout.S1 + i * 10
        colors.append(color(struct.unpack_from('<I', decoded, offset)[0]))
        q = struct.unpack_from('<2h', decoded, offset + 4)
        uv.append([v / (32768 if v < 0 else 32767) * uv_transform[k] + uv_transform[k+2]
                   for k, v in enumerate(q)])
    visible = {m['name'] for m in geometry['materials'] if m['visible']}
    bound = {m['name']: m['texture'] for m in geometry['materials']}
    if geometry.get('scorebug_runtime_installed'):
        missing = {bound[name] for name in visible if bound[name] not in material_atlases}
        if missing:
            raise ValueError('runtime raster is missing native texture descriptors: ' + ', '.join(sorted(missing)))
    winding = {}
    for k, indices in r.layout.strips(decoded):
        name = r.layout.SUBMESHES[k][2]
        if name not in visible:
            continue
        winding[name] = dict(positive=0, negative=0)
        for i in range(len(indices) - 2):
            vs = indices[i:i+3]
            if i % 2:
                vs = vs[::-1]
            pts = [geometry['positions'][v] for v in vs]
            a, b, c = pts
            area = (b[0]-a[0])*(c[1]-a[1]) - (c[0]-a[0])*(b[1]-a[1])
            if abs(area) > 1e-6:
                winding[name]['positive' if area > 0 else 'negative'] += 1
            triangle(material_atlases.get(bound[name], atlas), pts, [uv[v] for v in vs], [colors[v] for v in vs],
                     [geometry['world_positions'][v][2] for v in vs], cull=cull_positive)
    for row in geometry['draws']:
        vertices = row['vertices']
        for first in range(0, len(vertices), 4):
            quad = vertices[first:first+4]
            for ix in ((0, 1, 2), (2, 1, 3)):
                vs = [quad[i] for i in ix]
                triangle(font_atlases[row['font']], [v['screen'] for v in vs], [v['uv'] for v in vs],
                         [color(int(v['color'], 16)) for v in vs], [v['world'][2] for v in vs])
    if calibration is not None:
        gain, bias = calibration.get('gain', 1), calibration.get('bias', 0)
        if not all(math.isfinite(v) for v in (gain, bias)) or not (0 < gain <= 2 and -255 <= bias <= 255):
            raise ValueError('invalid diagnostic tone calibration')
        lut = [min(255, max(0, round(v*gain+bias))) for v in range(256)]
        im = im.convert('RGB').point(lut*3).convert('RGBA')
        draw = ImageDraw.Draw(im)
    label = geometry['static_version'].upper() + ' / NATIVE INPUTS / SOFTWARE RASTER'
    if cull_positive:
        label += ' / CULL HYPOTHESIS'
    draw.text((8, 4), label, fill='white')
    draw.text((8, height-12), 'EXPERIMENTAL / CPU FIXTURE / NOT A GAME CAPTURE', fill='white')
    im.convert('RGB').save(path)
    return dict(uv_transform=list(uv_transform), winding=winding,
                rendered_materials={name: dict(descriptor=bound[name],
                    **texture_receipts.get(bound[name], dict(name='score_buga',
                       span_sha256=r.digest(texture_span), dimensions=[64, 64]))) for name in sorted(visible)},
                raster_policy=dict(depth='less-equal model', blend='vertex * texture, source alpha model',
                                   cull_positive=cull_positive, gpu_state_proved=False,
                                   calibration=calibration))


def v7_baseline(spans):
    """Reconstruct and pin the shipped v7 inputs, for comparison only."""
    from PIL import ImageDraw
    mesh = r.mesh(r.pinned(spans['score_bug'], art.RESOURCES['score_bug']), baseline_v7=True)
    decoded = bytearray(r.serialize(mesh))
    for v, pos in enumerate(mesh.pos):
        q = [round((c - o) / 420 * 32767) for c, o in zip(pos, (-20, 100, -29.5))]
        struct.pack_into('<3h', decoded, r.layout.S0 + v * 6, *q)
    scene, _ = r.layout.refit(spans['score_bug'], bytes(decoded))
    atlas = r.atlas_v8(spans); draw = ImageDraw.Draw(atlas)
    draw.rectangle((0, 0, 63, 15), fill=(0, 0, 0, 0))
    draw.rounded_rectangle((0, 0, 63, 15), 2, fill=(19,20,25,255), outline=(122,124,132,255))
    draw.line((3,1,60,1), fill=(190,190,196,255))
    for x in range(64):
        value = round(75 * (1-x/63) + 17*x/63)
        draw.line((x,16,x,31), fill=(value,value,value+5,255))
    for x in (48,53,58):
        draw.line((x,30,x+2,30), fill=(230,230,232,255))
    texture, _ = r.encode_atlas(spans['score_buga'], atlas)
    if r.digest(scene) != '475efc3d7aa03535f8f807dbdca0baaa32928faf2ade9116551c7bb57039c732':
        raise ValueError('v7 scene baseline drifted')
    if r.digest(texture) != '72aee2c09b471c6f07e3658c00ef6f204021f3f6065cd96344c7c72d30df9947':
        raise ValueError('v7 atlas baseline drifted')
    return bytes(decoded), texture


def v8_baseline(spans):
    """Rebuild the witnessed v8 resource identities, never accepted by v9 apply."""
    decoded = r.serialize(r.mesh_v8(r.pinned(spans['score_bug'], art.RESOURCES['score_bug'])))
    scene, _ = r.layout.refit(spans['score_bug'], decoded)
    atlas, _ = r.encode_atlas(spans['score_buga'], r.atlas_v8(spans))
    if r.digest(scene) != 'cdcf2aa898dd85332e3b872ca73eeae525ca85e9e543f4d07250bf820df16427':
        raise ValueError('v8 scene baseline drifted')
    if r.digest(atlas) != '8771f332aa07a63db1c21d9803455cc4ed5dd7f04fb88d36d571b03f1c7b7cd0':
        raise ValueError('v8 atlas baseline drifted')
    return decoded, atlas


def main(argv=None):
    """An explicit --folder retains the v10 proof CLI; default compares exact."""
    args = list(sys.argv[1:] if argv is None else argv)
    if any(arg == '--folder' or arg.startswith('--folder=') for arg in args):
        from nfl2k5_scorebug_template_proof import main as prove_template
        return prove_template(args)
    from nfl2k5_scorebug_exact import main as exact_main
    return exact_main(args)


if __name__ == '__main__':
    raise SystemExit(main())

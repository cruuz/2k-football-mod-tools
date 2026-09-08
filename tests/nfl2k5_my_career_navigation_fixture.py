"""Pinned navigation resources and native row dispatch, without a scene/GPU.

Resource lookup and scene geometry are declared boundaries. Native LAYT
relocation, binding, traversal, MRKS callback lookup and row formatting run.
The capture is a text submission boundary, not a rendered screenshot.
"""
import hashlib
import struct
import unittest

from tests.nfl2k5_my_career_fixture import XBE

PINS = (
    (3, 443504, 288, 'LAYT', 'navigation', 'fb85421f3dbc83eef05341c2b1b2f3348c8c710189d437c0edecec78b459fc75'),
    (3, 440480, 384, 'LAYT', 'title_bar_wide', 'b04d79c42021983eacfd00d6a43e977f2f005ba1c58da88168de41f77b349623'),
    (8, 1334720, 560, 'LAYT', 'nav_menu_a', '1329b50f078f421b588cfc3908b1175c1135095302f470a7c9e2e5ba8b61f098'),
    (8, 1315056, 17024, 'MRKS', 'nav_menu_list_a', 'ea2a2255bad55cec4f044c48ad6bb7c5e447e1ea83cce3f32a56533c20e135af'),
)


def resources():
    from mod_editor.core import nfl2k5_roster_records as roster
    try:
        with roster._outer_image()(XBE.parent) as archive:
            out = []
            for entry, offset, size, kind, name, digest in PINS:
                # Exact spans, never whole packs. These four resources are raw.
                span = archive.read(archive.entries[entry].virtual_offset + offset, 32 + size)
                if span[:4] != kind.encode() or hashlib.sha256(span[32:]).hexdigest() != digest:
                    raise ValueError(f'{name} evidence pin differs')
                out.append((kind, name, span[32:]))
            return out
    except (OSError, ValueError) as exc:
        raise unittest.SkipTest(f'pinned USA LAYT/MRKS evidence unavailable: {exc}') from exc


def install(m, evidence):
    objects = {}
    m.native_rows = []
    def alloc(data):
        at = m.heap_next
        m.heap_next += (len(data) + 15) & ~15
        if m.heap_next > 0x2C00000:
            raise AssertionError('bounded navigation heap exhausted')
        m.uc.mem_write(at, data)
        return at
    def relative(data, field):
        raw = struct.unpack_from('<I', data, field)[0]
        return (field + raw - 1) & 0xFFFFFFFF if raw else 0
    for kind, name, data in evidence:
        at = alloc(data)
        obj = at + relative(data, 20)
        objects[kind, name] = obj
        if kind == 'LAYT':
            m.put(at + 20, obj)
            m.call(0x1690B0, ecx=at)
        else:
            # MRKS text table only. Scene geometry is deliberately absent.
            offset = obj - at
            for field in (0, 8, 16, 24, 32):
                m.put(obj + field, at + relative(data, offset + field))
    def lookup():
        kind = struct.pack('<I', m.reg('EDX')).decode('ascii')
        name = m.string(m.get(m.reg('ESP') + 4))
        m.ret(objects.get((kind, name), 0), pop=4)
    m.replace_stub(0x449E0, lookup)
    for va in (0xF3CD0, 0xF37E0, 0x2C8810, 0x2C8880, 0x14FF70):
        m.replace_stub(va, None)
    # Preserve native LAYT traversal. The scene leaf forwards its MRKS table
    # to the real 143450 dispatch, omitting geometry, transforms and GPU work.
    # Arguments: descriptor, time, coordinates, scene mode, manager.
    bridge = alloc(bytes.fromhex('ff74241453ff742410ff742410') +
                   b'\xe8' + bytes(4) + bytes.fromhex('c21400'))
    m.put(bridge + 14, (0x143450 - (bridge + 18)) & 0xFFFFFFFF)
    def scene():
        if m.get(m.reg('EBX') + 0x50):
            m.reg('EIP', bridge)
        else:
            m.ret(pop=20)
    m.replace_stub(0x143720, scene)
    # Scene time, projection matrices and final text draw are explicit leaves.
    m.replace_stub(0x143CE0, lambda: m.ret(pop=4))
    m.replace_stub(0x2AD80, lambda: m.ret())
    m.replace_stub(0x2AC80, lambda: m.ret())
    m.replace_stub(0x150E30, lambda: m.ret())
    m.replace_stub(0x1513D0, lambda: m.ret())
    def capture():
        marker = m.reg('ECX')
        m.native_rows.append(dict(text=m.string(m.reg('EDX')),
            color=m.get(0xAA2870 + 32), marker=marker,
            font=m.get(marker + 0x70), flags=m.get(marker + 0x74)))
        m.ret()
    m.replace_stub(0x151440, capture)
    # Rebuild the current owned screen using the real constructor and loader.
    m.event(3)

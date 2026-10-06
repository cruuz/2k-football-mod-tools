#!/usr/bin/env python3
"""Read-only native initialization of exact authored PLAY checkdown assignments.

The entire native route initializer 229ae0 executes its real decoders, endpoint,
timing and lookahead callees. Supplied actors use explicit .8 ratings and exact
formation column0 positions. This proves authored route predictions, not live
player movement, animation completion or a game witnessed by Noah.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.nfl2k5_back_throws_replay import NativeMachine, x86
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_playbook_inspector as inspector
from mod_editor.core import nfl2k5_play_library as lib


def _book(machine, payload):
    cache = getattr(machine, '_route_book_cache', {})
    digest = hashlib.sha256(payload).digest()
    if digest not in cache:
        if len(cache) >= 80:
            cache.clear()
        cache[digest] = inspector_book = inspector.parse_playbook_resource(payload)
        machine._route_book_cache = cache
        return inspector_book
    return cache[digest]


def native_assignment(machine, payload, formation_index, play_index, slot,
                      *, direction=1, active_index=1, current_position=None):
    m = machine
    book = _book(m, payload)
    fr = lib.formation_record(payload[32:], formation_index)
    codes = lib.category_positions(payload[32:], lib.formation_category(payload[32:], formation_index))
    assignment = book.plays[play_index].assignments[slot]
    nodes = [codec.Node.from_bytes(bytes.fromhex(n.raw_hex))
             for n in book.assignment_chain(assignment).nodes]
    if nodes[active_index].op != 18:
        raise ValueError('Probe entry must be an actual active route segment')
    # Real runtime opcode metadata, initialized by the native setter.
    m.call(0x1a8bc0, ecx=0x521078)
    state, descriptor, chain = m.P+0x600, m.P+0x1900, m.P+0x1910
    m.uc.mem_write(state, bytes(0x600))
    m.uc.mem_write(m.TEAM+0x300, bytes(0x100))
    m.put(descriptor, assignment.descriptor_word); m.put(descriptor+4, chain)
    m.uc.mem_write(chain, b''.join(n.to_bytes() for n in nodes))
    m.put(state+0x41c, descriptor); m.uc.mem_write(state+0x450, bytes([active_index]))
    # The native task-stack empty sentinel, not a replacement task callee.
    m.put(state+0x300, state+0x240); m.put(state+0x310, state-0xb0)
    m.put(m.P+0x24, m.P+0x1a00); m.put(m.TEAM+0xc, m.TEAM+0x300)
    form = payload[32+inspector.FORMATION_BASE+formation_index*inspector.FORMATION_SIZE:
                   32+inspector.FORMATION_BASE+(formation_index+1)*inspector.FORMATION_SIZE]
    m.uc.mem_write(m.P+0x1b00, form); m.put(m.TEAM+0x34c, m.P+0x1b00)
    m.f(m.P+0x390, .8)
    for k, value in enumerate(nodes[active_index].operands):
        m.f(state+0x430+k*4, float(value))
    m.put(state+0x420, 0x20000 if nodes[active_index].flags & 2 else 0)
    m.put(0xe602b8, 14); m.put(0xe602b4, 4)
    m.uc.mem_write(m.P+0x2e, bytes([slot])); m.uc.mem_write(0xbdfcd0+slot*2, b'\x00')
    role = {10:1, 11:2, 8:4}[codes[slot]&31]
    m.uc.mem_write(m.P+0x2c, bytes([role])); m.uc.mem_write(m.P+0x1035, bytes([role]))
    x, z = current_position if current_position is not None else (fr.slots[slot].x[0], fr.slots[slot].z[0])
    m.f(m.TEAM+0x204, direction)
    m.vec(m.P+0x530, (float(x)*direction, 0., float(z)*direction, 1.))
    m.vec(m.P+0x540, (0., 0., 0., 0.))
    m.vec(m.CTX+0x10, (0., 0., 0., 1.))
    # Zero is an inactive prediction-time sentinel in native 2266a0; the
    # elapsed clock is positive when an assignment executes in a game.
    m.uc.mem_write(0xc16590, bytes(0x98))
    m.put(0xe5fc00, 0); m.f(m.CLOCK+0x10, 1.)
    m.call(0x229ae0, ecx=m.P, count=100000)
    table = bytes(m.uc.mem_read(0xc16590, 0x98)); records = []
    for offset in range(12, 12+8*16, 16):
        time, xx, zz, flags = struct.unpack_from('<3fI', table, offset)
        records.append(dict(time=time, x=xx*direction, z=zz*direction,
                            kind=flags&31, flags=flags))
    return dict(records=records, route_initializer_instructions=sum(m.counts.values()),
                endpoint_calls=m.counts[0x225730], decoder_calls=m.counts[0x2b6f70],
                nodes=[n.to_bytes().hex() for n in nodes], direction=direction)


def native_qb_drop(machine, payload, formation_index, play_index, *, direction=1):
    """Actual 2f3d10 prefix through endpoint-store; no later animation requests."""
    m = machine
    book = _book(m, payload)
    fr = lib.formation_record(payload[32:], formation_index)
    nodes = [codec.Node.from_bytes(bytes.fromhex(n.raw_hex))
             for n in book.assignment_chain(book.plays[play_index].assignments[0]).nodes]
    index = next(i for i, n in enumerate(nodes) if n.op == 4)
    state, descriptor, chain = m.Q+0x600, m.Q+0x1900, m.Q+0x1910
    m.uc.mem_write(state, bytes(0x600))
    m.put(descriptor, book.plays[play_index].assignments[0].descriptor_word)
    m.put(descriptor+4, chain); m.uc.mem_write(chain, b''.join(n.to_bytes() for n in nodes))
    m.put(state+0x41c, descriptor); m.uc.mem_write(state+0x450, bytes([index]))
    m.put(state+0x300, state+0x240); m.put(state+0x310, state-0xb0)
    m.put(m.Q+0x24, m.Q+0x1a00)
    for k, value in enumerate(nodes[index].operands):
        m.f(state+0x430+k*4, float(value))
    m.f(m.TEAM+0x204, direction)
    m.vec(m.Q+0x530, (fr.slots[0].x[0]*direction, 0., fr.slots[0].z[0]*direction, 1.))
    m.vec(m.CTX+0x10, (0., 0., 0., 1.))
    m.uc.reg_write(x86.UC_X86_REG_ESP, m.SP)
    m.uc.reg_write(x86.UC_X86_REG_ECX, m.Q)
    m.run(0x2f3d10, 0x2f3e31, count=100000)
    task = m.get(state+0x310)
    return dict(z=m.rf(task+0x28)*direction, x=m.rf(task+0x20)*direction,
                task_callback=hex(m.get(task)), native_instructions=sum(m.counts.values()),
                nodes=[n.to_bytes().hex() for n in nodes], direction=direction)

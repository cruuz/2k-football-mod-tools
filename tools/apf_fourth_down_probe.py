"""Bounded fourth-down research helpers. All inputs/images remain in memory."""
from __future__ import annotations
import struct
from mod_editor.core import apf2k8_fourth_down as fd
from tools.apf_playcall_research_probe import GAME, HISTORY, TEAM, MANAGER, IMAGE_BASE, STOP

PLAYER, OBJECT, CONTEXT, CONTROL, ELAPSED, PLAYCLOCK = (0x390000, 0x391000, 0x392000, 0x393000, 0x394000, 0x395000)
DRAW_LATCH = 0x84DBAFB0


def apply_document(machine, document):
    fd.verify_image(machine.image, document)
    image = bytearray(machine.image)
    for address, value in document.words:
        struct.pack_into('>I', image, address - IMAGE_BASE, value)
        machine.put(address, value)
    machine.image = bytes(image)
    # An already-called retail function can have translated blocks cached.
    # Invalidate them after changing instructions, as a fresh Xenia load does.
    machine.cpu.ctl_flush_tb()


def call_target(machine, base_site):
    site = machine.va(base_site)
    word = struct.unpack_from('>I', machine.image, site - IMAGE_BASE)[0]
    if word >> 26 != 18 or word & 3 != 1:
        raise AssertionError('Expected a relative bl instruction')
    offset = word & 0x3FFFFFC
    if offset & 0x2000000:
        offset -= 0x4000000
    return site + offset


def state(machine, *, cache=.5, need=0, phase=12, **kwargs):
    machine.configure(**kwargs)
    delta = 0x30 if machine.updated else 0
    machine.put(GAME + delta + 0x38, phase)
    machine.put(0x330014, 1)  # native timeout availability gate
    machine.putf(HISTORY + delta + 0x400, cache)
    machine.putf(HISTORY + delta + 0x3FC, need)
    machine.put(DRAW_LATCH, 0)


def produce_draw(machine):
    """Execute selector -> draw predicate -> flag store -> substitution routine.

    Only animation setup and timer initialization are boundary adapters.
    The fixture must contain special-team categories (the retail global book).
    """
    delta = 0x30 if machine.updated else 0
    machine.put(0x84F3F8F8, 5)
    machine.put(PLAYER + 0x28, OBJECT)
    machine.put(OBJECT + 0x6D0, CONTEXT)
    machine.put(PLAYER + 0x40, MANAGER)
    machine.put(0x85158350 + delta, 0)
    machine.put(TEAM + 0x2C, 0)
    boundaries = [call_target(machine, pc) for pc in (0x84817008, 0x84817020, 0x8481702C)]
    for a in boundaries:
        machine.boundaries[a] = lambda m: m.ret(0)
    started = machine.steps
    kick = []
    def selected(m):
        target = 0x85158360 + delta
        kick.append([m.get(target + i) for i in (0, 4, 12)])
    machine.observers[machine.va(0x848170A4)] = selected
    machine.call(machine.va(0x84816FF0), PLAYER, bound=2_000_000)
    return {'instructions': machine.steps - started, 'flag': machine.get(TEAM + 0x2C),
            'latch': machine.get(DRAW_LATCH), 'selected_kick': kick,
            'replacement': [machine.get(0x85158360 + delta + i) for i in (0, 4, 12)],
            'boundary_addresses': boundaries, 'adapted_pcs': sorted(machine.adapted)}


def presnap(machine, playclock, *, defense_gate=False):
    """Execute from the snap-controller entry through timeout dispatch/hold.

    The draw flag is read from TEAM without replacing it. Player/animation
    readiness and the defense snap predicate have explicit synthetic returns.
    Stop at timeout dispatch before presentation or match-state side effects.
    """
    delta = 0x30 if machine.updated else 0
    machine.put(PLAYER + 0x40, MANAGER)
    machine.put(PLAYER + 0x28, OBJECT)
    machine.put(OBJECT + 0x6D0, CONTEXT)
    machine.put(PLAYER + 0x10, CONTROL)
    machine.put(CONTROL, -1)
    machine.put(TEAM + 0x10, 0)
    machine.put(MANAGER + 4, 0)
    machine.put(GAME + delta + 0x10, ELAPSED)
    machine.putf(ELAPSED + 0x10, 1)
    machine.put(GAME + delta + 0x14, PLAYCLOCK)
    machine.putf(PLAYCLOCK + 0x10, playclock)
    machine.put(CONTEXT + 0xF8, 4)
    machine.putf(CONTEXT + 0x60, 1)
    boundaries = []
    for site, value in ((0x84836734, 0), (0x84836784, 0), (0x848367A4, 1),
                        (0x848368AC, 0), (0x848369A0, 0), (0x84836B94, int(defense_gate)), (0x84836BA4, 0)):
        a = call_target(machine, site)
        boundaries.append((a, value))
        machine.boundaries[a] = lambda m, v=value: m.ret(v)
    outcomes = []
    for address, outcome in ((call_target(machine, 0x84836C9C), 'timeout_dispatch'),
                             (machine.va(0x84836CC4), 'hold'),
                             (machine.va(0x84836CB4), 'snap_gate')):
        def stop(m, result=outcome):
            outcomes.append(result)
            m.cpu.reg_write(m.r.UC_PPC_REG_PC, STOP)
        machine.boundaries[address] = stop
    start = machine.steps
    machine.call(machine.va(0x84836698), PLAYER, bound=100_000)
    if len(outcomes) != 1:
        raise AssertionError('Snap controller did not reach a reviewed frontier')
    return {'outcome': outcomes[0], 'instructions': machine.steps - start,
            'playclock': playclock, 'draw_flag': bool(machine.get(TEAM + 0x2C) & 0x200000),
            'boundaries': boundaries, 'timeout_dispatch': call_target(machine, 0x84836C9C),
            'adapted_pcs': sorted(machine.adapted)}

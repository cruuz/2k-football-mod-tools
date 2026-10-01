"""DESIGN: dynamic defensive-team fatigue write, shared by gdb and offline proof."""
import struct


def force_defense(read, write, stack):
    def u32(a):
        return struct.unpack('<I', read(a, 4))[0]
    desc, context = u32(stack + 0x10), u32(stack + 0x14)
    codes = read(desc + 5, 11)
    kinds = [x & 31 for x in codes]
    if not all(12 <= k <= 18 for k in kinds) or not any(k in (14, 15) for k in kinds):
        return None
    # Match the native branch at 0x18A613. The away context is not derived
    # from a guessed team-object stride.
    if not context:
        raise ValueError('missing team context')
    getter = 0x61C70 if context == 0xE5FC20 else 0x61C80
    op = read(getter, 6)
    if op[0] != 0xB8 or op[5] != 0xC3:
        raise ValueError('foreign roster getter')
    roster = struct.unpack('<I', op[1:5])[0]
    team = u32(roster)
    count = read(team + 0x11C, 1)[0]
    if not 11 <= count <= 64:
        raise ValueError(f'implausible roster count {count}')
    changes = []
    for i in range(count):
        p = u32(team + 4 * i)
        enum = read(p + 0x35, 1)[0]
        if enum not in (10, 11):
            continue
        side = read(p + 0x34, 1)[0]
        settings = 0xE60194 if side == 1 else 0xE601A4
        out, into = u32(settings), u32(settings + 4)
        if not 0 < out <= 20 or not 0 < into <= 20:
            raise ValueError('fatigue disabled or foreign thresholds')
        wrapper = u32(p + 0x30)
        energy = u32(wrapper + 4) + 4
        old = struct.unpack('<f', read(energy, 4))[0]
        if not 0 <= old <= 1.01:
            raise ValueError('foreign fatigue pointer/value')
        changes.append(dict(player=hex(p), enum=enum, energy_address=hex(energy),
                            before=old, after=0.0, out_threshold=out / 20,
                            in_threshold=into / 20, active=u32(wrapper + 0x10)))
    if not changes:
        raise ValueError('no defensive linebackers')
    # Validate the complete target set before the first write.
    for c in changes:
        write(int(c['energy_address'], 16), struct.pack('<f', c['after']))
    return dict(descriptor=hex(desc), context=hex(context), roster=hex(roster),
                slot_kinds=kinds, linebackers=changes)

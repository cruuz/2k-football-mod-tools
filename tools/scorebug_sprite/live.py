"""Read xemu NV097 text traces without supplying unobserved GPU defaults.

The stock logger suppresses ARRAY_ELEMENT16 values. A BEGIN/END pair with no
geometry events is therefore not evidence of an empty draw. Each independently
enabled trace window must be parsed separately: state cannot cross a gap.
"""
from collections import Counter
from dataclasses import dataclass, field
import re


METHOD = re.compile(
    r'nv2a_pgraph_method (\d+): (0x[0-9a-fA-F]+) -> '
    r'(0x[0-9a-fA-F]+) (\S+) (0x[0-9a-fA-F]+)$')
ABBREV = re.compile(
    r'nv2a_pgraph_method_abbrev (\d+): (0x[0-9a-fA-F]+) -> '
    r'(0x[0-9a-fA-F]+) (\S+) \* (\d+)$')
UNHANDLED = re.compile(
    r'nv2a_pgraph_method_unhandled (\d+): (0x[0-9a-fA-F]+) -> '
    r'(0x[0-9a-fA-F]+) (0x[0-9a-fA-F]+)$')


@dataclass
class Context:
    state: dict = field(default_factory=dict)
    writes: dict = field(default_factory=dict)
    constants: dict = field(default_factory=dict)
    constant_writes: dict = field(default_factory=dict)
    program: dict = field(default_factory=dict)
    program_writes: dict = field(default_factory=dict)
    constant_load: int | None = None
    program_load: int | None = None
    active: dict | None = None

    def snapshot(self):
        start = self.state.get('0x1ea0')
        program = []
        complete = False
        if start is not None:
            for slot in range(start, 136):
                words = [self.program.get(str(slot*4+i)) for i in range(4)]
                if None in words:
                    break
                program.extend(words)
                if words[3] & 1:
                    complete = True
                    break
        return dict(state=dict(self.state), state_writes=dict(self.writes),
                    vertex_constants=dict(self.constants),
                    constant_writes=dict(self.constant_writes),
                    program_memory=dict(self.program),
                    program_writes=dict(self.program_writes),
                    vertex_program=program, vertex_program_complete=complete)


def parse(lines, *, first_line=1):
    """Return observed draw states and provenance for one uninterrupted window.

    Upload port component selection and auto-increment follow pgraph.c, not
    packet-order assumptions. Missing load pointers leave uploads unknown.
    Unhandled notifications never establish register state.
    """
    contexts = {}
    draws, events, warnings = [], [], []
    counts, names = Counter(), {}
    for number, raw in enumerate(lines, first_line):
        line = raw.strip()
        if not line:
            continue
        match = METHOD.fullmatch(line)
        if match is None:
            if UNHANDLED.fullmatch(line):
                counts['unhandled_notifications'] += 1
                continue
            abbrev = ABBREV.fullmatch(line)
            if abbrev:
                counts['abbreviations'] += 1
                sub, cls, offset, name, count = abbrev.groups()
                context = contexts.get((int(sub), int(cls, 16)))
                if context and context.active is not None:
                    context.active['geometry_events'].append(dict(
                        line=number, method=offset, abbreviated_count=int(count),
                        indices_unknown=True))
                continue
            raise ValueError(f'Unrecognized trace line {number}: {line[:120]}')
        sub, cls, offset, name, value = match.groups()
        sub, cls, offset, value = int(sub), int(cls, 16), int(offset, 16), int(value, 16)
        counts['handled'] += 1
        if cls != 0x97:
            counts['other_classes'] += 1
            continue
        context = contexts.setdefault((sub, cls), Context())
        key = f'0x{offset:04x}'
        names[key] = name
        if name.startswith('?'):
            counts['unnamed_attempts'] += 1
            continue
        if offset in (0x1800, 0x1808, 0x1810, 0x1818):
            if context.active is not None:
                context.active['geometry_events'].append(dict(line=number, method=key, value=value))
            else:
                warnings.append(dict(line=number, reason='geometry outside observed BEGIN'))
            continue
        if offset == 0x17fc:
            if value:
                if context.active is not None:
                    warnings.append(dict(line=number, reason='BEGIN without observed END'))
                row = dict(id=len(draws), begin_line=number, end_line=None,
                           subchannel=sub, primitive=value, geometry_events=[],
                           changes_inside=[], **context.snapshot())
                draws.append(row)
                context.active = row
            elif context.active is None:
                counts['orphan_ends'] += 1
            else:
                context.active['end_line'] = number
                context.active = None
            continue
        if context.active is not None:
            context.active['changes_inside'].append(dict(line=number, method=key, value=value))
        if offset == 0x1e9c:
            context.program_load = value
        elif offset == 0x1ea4:
            context.constant_load = value
        elif 0xb00 <= offset < 0xc00:
            constant = offset >= 0xb80
            component = ((offset - (0xb80 if constant else 0xb00)) // 4) % 4
            pointer = context.constant_load if constant else context.program_load
            if pointer is not None:
                memory = context.constants if constant else context.program
                writes = context.constant_writes if constant else context.program_writes
                index = str(pointer*4+component)
                memory[index], writes[index] = value, number
                if component == 3:
                    if constant:
                        context.constant_load += 1
                    else:
                        context.program_load += 1
            else:
                counts['uploads_without_load_pointer'] += 1
            continue
        context.state[key], context.writes[key] = value, number
        if offset in (0x12c, 0x130, 0x200, 0x204, 0x208, 0x210, 0x214, 0x1d94):
            events.append(dict(line=number, method=key, name=name, value=value))
    counts['draws'] = len(draws)
    counts['closed_draws'] = sum(d['end_line'] is not None for d in draws)
    counts['draws_without_geometry_values'] = sum(not d['geometry_events'] for d in draws)
    return dict(counts=dict(counts), draws=draws, boundary_events=events,
                warnings=warnings, method_names=names,
                limitations=['Missing registers and upload words are unknown',
                    'Stock xemu suppresses ARRAY_ELEMENT16 values',
                    'No DMA object, host texture cache, shader uniform or framebuffer snapshots'])


def read_ram(ram, offset, size):
    """Refuse truncated regions instead of padding missing physical memory."""
    if offset < 0 or size < 0 or offset+size > len(ram):
        raise ValueError(f'RAM range {offset:#x}+{size:#x} exceeds dump {len(ram):#x}')
    return ram[offset:offset+size]

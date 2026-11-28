"""Install the trade, release and signed-load ownership safeguards for standard franchises, including modern IR recovery."""
from __future__ import annotations

import struct

from . import nfl2k5_franchise_ownership_code as runtime
from . import nfl2k5_franchise_ownership_code_b81_prev as runtime_previous
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = 'nfl2k5_franchise_ownership'
CODE_SIZE = space.FRANCHISE_OWNERSHIP_SIZE
REQUESTS = ((OWNER, 'code', CODE_SIZE, 16),)
# The trade validator call is downstream of both roster-capacity owner variants, before either
# club gives up a pick or player. A release and a proration are also public native routines.
RELEASE_SITE = 0x2BD900
HOOKS = (
    (0x2BC688, bytes.fromhex('e8f3fcffff'), 'ownership_trade_stub', 0xE8),
    (RELEASE_SITE, bytes.fromhex('56578bf28bf9'), 'ownership_release_stub', 0xE9),
    (0x2BCF60, bytes.fromhex('0fb74e0ae88790e2ff'), 'ownership_contract_stub', 0xE9),
)


def _allocation(payload: bytes):
    layout = space.layout(payload)
    matches = [row for row in layout['allocations'] if row['owner'] == OWNER]
    if not matches:
        return None
    if len(matches) != 1 or (matches[0]['kind'], matches[0]['size'], matches[0]['align']) != ('code', CODE_SIZE, 16):
        raise ValueError('Unexpected franchise ownership allocation')
    return matches[0]


def load_entry(payload: bytes) -> int:
    row = _allocation(payload)
    if row is None:
        raise ValueError('The franchise load repair has no reserved code')
    return row['va'] + runtime.LABELS['ownership_repair_loaded']


def code_for(va: int, store_va: int, module=runtime) -> bytes:
    if not 0 <= store_va <= 0xFFFFFFFF or len(module.CODE) > CODE_SIZE:
        raise ValueError('Invalid franchise ownership code or IR store')
    data = bytearray(module.CODE)
    for offset, kind, symbol, value in module.RELOCATIONS:
        if symbol != 'code' or kind not in (1, 2):
            raise ValueError('Unsupported franchise ownership relocation')
        addend = struct.unpack_from('<i', data, offset)[0]
        relocated = va + value + addend - (va + offset if kind == 2 else 0)
        struct.pack_into('<I', data, offset, relocated & 0xFFFFFFFF)
    struct.pack_into('<I', data, module.LABELS['ownership_store'], store_va)
    return bytes(data).ljust(CODE_SIZE, b'\xCC')


# The previous revision (b81 before the trades lane's refusal fix): its hook-site labels equal this revision's, so the
# sites read the same and an upgrade rewrites the page only.
PREVIOUS = (runtime_previous,)


def revision(payload: bytes, store_va: int = 0) -> str | None:
    """'current' or 'previous' for an installed page (guard or applied), None when retail or foreign."""
    try:
        row = _allocation(payload)
        if row is None:
            return None
        raw = XbeImage(payload).read(row['va'], CODE_SIZE)
        for name, module in (('current', runtime),) + tuple(('previous', m) for m in PREVIOUS):
            if any(raw == code_for(row['va'], address, module) for address in {0, store_va}):
                return name
    except (TypeError, ValueError, KeyError, IndexError, struct.error, OverflowError):
        return None
    return None


def sites(va: int):
    for at, before, symbol, opcode in HOOKS:
        displacement = va + runtime.LABELS[symbol] - (at + 5)
        yield at, before, (bytes([opcode]) + struct.pack('<i', displacement)).ljust(len(before), b'\x90')


def status(payload: bytes, store_va: int = 0) -> str:
    try:
        image = XbeImage(payload)
        row = _allocation(payload)
        if row is None:
            return 'retail' if all(image.read(at, len(old)) == old for at, old, _, _ in HOOKS) else 'foreign'
        va = row['va']
        raw = image.read(va, CODE_SIZE)
        if raw == b'\xCC' * CODE_SIZE:
            return 'retail' if all(image.read(at, len(old)) == old for at, old, _, _ in HOOKS) else 'foreign'
        for mode, address in (('guard', 0), ('applied', store_va)):
            if (mode == 'applied' and not address) or raw not in [code_for(va, address, m) for m in (runtime,) + PREVIOUS]:
                continue
            for at, original, patched in sites(va):
                expected = original if mode == 'guard' and at == RELEASE_SITE else patched
                if image.read(at, len(expected)) != expected:
                    return 'foreign'
            return mode
        return 'foreign'
    except (TypeError, ValueError, KeyError, IndexError, struct.error, OverflowError):
        return 'foreign'


def apply(payload: bytes, store_va: int) -> tuple[bytes, dict]:
    """Install only on known original bytes or return the verified previous installation unchanged."""
    current = status(payload, store_va)
    if current == 'foreign':
        raise ValueError('The franchise ownership routines contain unrecognized changes')
    target = 'applied' if store_va else 'guard'
    if current == target and revision(payload, store_va) == 'current':
        return payload, {'owner': OWNER, 'status': 'already_applied', 'changed_bytes': 0}
    row = _allocation(payload)
    if row is None:
        raise ValueError('The standard franchise installer must reserve its ownership code first')
    va = row['va']
    if current == target:
        # the previous revision installed with this mode: rewrite the page in place (the hook sites read the same)
        installed = XbeImage(payload).read(va, CODE_SIZE)
        old = next(m for m in PREVIOUS if installed == code_for(va, store_va if store_va else 0, m))
        filled, _ = space.install_code(payload, OWNER, code_for(va, store_va), previous=code_for(va, store_va, old))
        if status(filled, store_va) != target or revision(filled, store_va) != 'current':
            raise ValueError('Franchise ownership upgrade failed verification')
        return filled, {'owner': OWNER, 'status': 'applied', 'mode': target, 'code_va': hex(va), 'upgraded_from': 'previous',
                        'edits': [], 'changed_bytes': space.count_differing_bytes(payload, filled)}
    previous = code_for(va, 0) if current == 'guard' and revision(payload, 0) == 'current' else (
        code_for(va, 0, PREVIOUS[0]) if current == 'guard' else None)
    filled, _ = space.install_code(payload, OWNER, code_for(va, store_va), previous=previous)
    image = XbeImage(filled)
    output = bytearray(filled)
    edits = []
    for at, old, patched in sites(va):
        if not store_va and at == RELEASE_SITE:
            continue
        if current == 'guard' and at != RELEASE_SITE:
            continue
        offset = image.offset(at, len(old))
        if output[offset:offset+len(old)] != old:
            raise ValueError(f'Unexpected franchise ownership hook at {at:#x}')
        output[offset:offset+len(old)] = patched
        edits.append({'va': hex(at), 'before': old.hex(), 'after': patched.hex()})
    for section in _sections(output):
        output[section.header_offset+36:section.header_offset+56] = section_digest(output, section)
    result = bytes(output)
    if status(result, store_va) != target:
        raise ValueError('Franchise ownership installation failed verification')
    receipt = {'owner': OWNER, 'status': 'applied', 'mode': target, 'code_va': hex(va),
               'edits': edits, 'changed_bytes': space.count_differing_bytes(payload, result)}
    if store_va:
        receipt['load_entry'] = hex(load_entry(result))
    return result, receipt

"""Install the trade, release and signed-load ownership safeguards used by modern franchise IR."""
from __future__ import annotations

import struct

from . import nfl2k5_franchise_ownership_code as runtime
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = 'nfl2k5_franchise_ownership'
CODE_SIZE = 3328
REQUESTS = ((OWNER, 'code', CODE_SIZE, 16),)
# The trade validator call is downstream of both roster-capacity owner variants, before either
# club gives up a pick or player. A release and a proration are also public native routines.
HOOKS = (
    (0x2BC688, bytes.fromhex('e8f3fcffff'), 'ownership_trade_stub', 0xE8),
    (0x2BD900, bytes.fromhex('56578bf28bf9'), 'ownership_release_stub', 0xE9),
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


def code_for(va: int, store_va: int) -> bytes:
    if not 0 < store_va <= 0xFFFFFFFF or len(runtime.CODE) > CODE_SIZE:
        raise ValueError('Invalid franchise ownership code or IR store')
    data = bytearray(runtime.CODE)
    for offset, kind, symbol, value in runtime.RELOCATIONS:
        if symbol != 'code' or kind not in (1, 2):
            raise ValueError('Unsupported franchise ownership relocation')
        addend = struct.unpack_from('<i', data, offset)[0]
        relocated = va + value + addend - (va + offset if kind == 2 else 0)
        struct.pack_into('<I', data, offset, relocated & 0xFFFFFFFF)
    struct.pack_into('<I', data, runtime.LABELS['ownership_store'], store_va)
    return bytes(data).ljust(CODE_SIZE, b'\xCC')


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
        if raw != code_for(va, store_va) or any(image.read(at, len(patched)) != patched for at, _, patched in sites(va)):
            return 'foreign'
        return 'applied'
    except (TypeError, ValueError, KeyError, IndexError, struct.error, OverflowError):
        return 'foreign'


def apply(payload: bytes, store_va: int) -> tuple[bytes, dict]:
    """Install only on known original bytes or return the verified previous installation unchanged."""
    current = status(payload, store_va)
    if current == 'foreign':
        raise ValueError('The franchise ownership routines contain unrecognized changes')
    if current == 'applied':
        return payload, {'owner': OWNER, 'status': 'already_applied', 'changed_bytes': 0}
    row = _allocation(payload)
    if row is None:
        raise ValueError('The modern IR installer must reserve the franchise ownership code first')
    va = row['va']
    filled, _ = space.install_code(payload, OWNER, code_for(va, store_va))
    image = XbeImage(filled)
    output = bytearray(filled)
    edits = []
    for at, old, patched in sites(va):
        offset = image.offset(at, len(old))
        if output[offset:offset+len(old)] != old:
            raise ValueError(f'Unexpected franchise ownership hook at {at:#x}')
        output[offset:offset+len(old)] = patched
        edits.append({'va': hex(at), 'before': old.hex(), 'after': patched.hex()})
    for section in _sections(output):
        output[section.header_offset+36:section.header_offset+56] = section_digest(output, section)
    result = bytes(output)
    if status(result, store_va) != 'applied':
        raise ValueError('Franchise ownership installation failed verification')
    return result, {'owner': OWNER, 'status': 'applied', 'code_va': hex(va), 'load_entry': hex(load_entry(result)),
                    'edits': edits, 'changed_bytes': space.count_differing_bytes(payload, result)}

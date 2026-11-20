"""Reversible 128 MiB simulated quarterback injuries and the matched scheduled passing model."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import struct

from . import nfl2k5_k128 as memory
from . import nfl2k5_lineup_roles as lineup
from . import nfl2k5_sim_realism as simulator
from . import nfl2k5_sim_scoring as scoring
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = space.QB_INJURY_OWNER
REQUESTS = (space.QB_INJURY_REQUEST,)
REALISTIC_RATE = 310
MARK = struct.Struct('<8sIII')
SIGNATURE = b'QBMEDv1\0'
ERRORS = (ValueError, TypeError, IndexError, KeyError, OverflowError, struct.error)


class SimQbInjuriesError(ValueError):
    """The requested option or the executable's installed state could not be verified."""


def _require(condition, message):
    if not condition:
        raise SimQbInjuriesError(message)


@dataclass(frozen=True)
class _Setting:
    mode: str
    rate: int

    def marker(self):
        mode = 1 if self.mode == 'realistic' else 2
        return MARK.pack(SIGNATURE, mode, self.rate, 0)

    @classmethod
    def from_marker(cls, raw):
        signature, mode, rate, reserved = MARK.unpack(raw)
        _require(signature == SIGNATURE and reserved == 0 and mode in (1, 2), 'Unknown simulated QB injury settings marker')
        _require(rate <= 100000 and (mode != 1 or rate == REALISTIC_RATE), 'Unknown simulated QB injury rate')
        return cls('realistic' if mode == 1 else 'custom', rate)


def _setting(mode, percent):
    _require(mode in ('retail', 'realistic', 'custom'), 'Choose Retail, Realistic or Custom for simulated QB injuries')
    if mode == 'retail':
        return None
    if mode == 'realistic':
        return _Setting(mode, REALISTIC_RATE)
    try:
        value = Decimal(str(percent))
    except (InvalidOperation, ValueError) as exc:
        raise SimQbInjuriesError('Custom QB injury chance must be a percentage') from exc
    _require(value.is_finite() and 0 <= value <= 100, 'Custom QB injury chance must be between 0 and 100 percent')
    units = value * 1000
    _require(units == units.to_integral_value(), 'Custom QB injury chance supports 0.001 percent increments')
    return _Setting(mode, int(units))


def _bank_allocation(payload):
    rows = [r for r in space.layout(payload)['allocations'] if r['owner'] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and tuple(rows[0][k] for k in ('owner','kind','size','align')) == REQUESTS[0],
             'Unknown simulated QB injury allocation')
    row = rows[0]
    section = XbeImage(payload).section(row['va'], row['size'])
    _require(section.writable and section.executable, 'Simulated QB injuries need a writable executable pool')
    return row


def _lineup_va(payload):
    """Use the original lineup entry points to distinguish active, reserved and absent roles."""
    rows = [r for r in space.layout(payload)['allocations'] if r['owner'] == lineup.OWNER]
    if not rows:
        return None
    row = lineup.allocation(payload)
    image = XbeImage(payload)
    states = set()
    for _, at, before, after in lineup.sites(row['va'], lineup._gate_target(payload)):
        value = image.read(at, len(before))
        states.add('applied' if value == after else 'retail' if value == before else 'foreign')
    if states == {'applied'}:
        return row['va']
    _require(states == {'retail'} and image.read(row['va'], row['size']) == b'\xcc' * row['size'],
             'Foreign or mixed simulated QB lineup dependency')
    return None


def _edits(payload, bank, setting, *, with_scoring=True):
    """The option's whole edit list; the in-place simulated kicking sites ride with it (beta 81 scoring slice)."""
    from . import nfl2k5_sim_qb_injuries_code as code
    image = XbeImage(payload)
    sim, data = simulator._allocations(payload)
    _require(sim['size'] == simulator.CODE_SIZE, 'Update simulated season realism before enabling QB injuries')
    base = bank['va']
    addresses = (base, sim['va'], data['va'], _lineup_va(payload))
    body = code.bank_bytes(image.read, *addresses, rate=setting.rate, marker=setting.marker())
    _require(len(body) == bank['size'], 'Incorrect simulated QB injury runtime size')
    kicking = scoring.edits() if with_scoring else ()
    return (*code.edits(*addresses, rate=setting.rate), *kicking,
            ('simulated QB injury bank', base, b'\xcc' * bank['size'], body))


def _transform(payload, edits, *, restoring):
    """Authenticate all inputs, then update the allocator seals and the changed XBE sections."""
    image = XbeImage(payload)
    data = bytearray(payload)
    changed_sections = set()
    for name, address, original, enabled in edits:
        before, after = (enabled, original) if restoring else (original, enabled)
        _require(len(before) == len(after) and image.read(address, len(before)) == before,
                 f'Foreign or mixed simulated QB injury bytes at {address:#x} ({name})')
        at = image.offset(address, len(before))
        data[at:at + len(after)] = after
        changed_sections.add(image.section(address).start)
    space._seal_scaleout(data, space._read_scale_directory(payload))
    for section in _sections(data):
        if section.virtual_address in changed_sections:
            at = section.header_offset + 36
            data[at:at + 20] = section_digest(data, section)
    space._validate(data)
    return bytes(data)


def _validate_simulation(payload):
    _require(memory.read_settings(payload).get('require_128'), 'Simulated QB injuries require a 128 MiB standard executable')
    _require(simulator._recognize_physical(payload) == 'applied', 'Enable the current simulated season realism before QB injuries')
    roles = lineup._read_physical_settings(payload)
    _require(roles['status'] in ('applied','retail'), 'Simulated QB injuries found an unknown lineup patch')


@lru_cache(maxsize=1)
def _state(payload: bytes):
    """Return the physical simulator only after the entire installed option matches its authored bytes."""
    if not space.is_scaleout(payload) or not any(r[0] == OWNER for r in space._scale_directory_requests(payload)):
        _require(scoring.status(payload) == 'retail', 'Simulated kicking bytes without the simulator option')
        return None, payload
    from . import nfl2k5_sim_qb_injuries_code as code
    allocation = _bank_allocation(payload)
    image = XbeImage(payload)
    if image.read(allocation['va'], allocation['size']) == b'\xcc' * allocation['size']:
        for address, width in code.FIXED_SPANS:
            entry = image.read(address, width)
            if entry[:1] in (b'\xe8', b'\xe9'):
                target = address + 5 + struct.unpack_from('<i', entry, 1)[0]
                _require(not allocation['va'] <= target < allocation['va'] + allocation['size'],
                         f'Simulated QB injury entry at {address:#x} points into an empty allocation')
        _require(scoring.status(payload) == 'retail', 'Simulated kicking bytes beside an empty simulator option')
        return None, payload
    marker = image.read(allocation['va'] + code.MARK_OFFSET, MARK.size)
    setting = _Setting.from_marker(marker)
    # An option installed before the scoring slice has retail kicking sites; apply() upgrades it in place.
    kicking = scoring.status(payload)
    _require(kicking in ('applied', 'retail'), 'Foreign or mixed simulated kicking bytes')
    restored = _transform(payload, _edits(payload, allocation, setting, with_scoring=kicking == 'applied'),
                          restoring=True)
    _validate_simulation(restored)
    return setting, restored


def physical_view(payload):
    """Recognize shared simulator and lineup sites while retaining every unrelated validation."""
    return _state(bytes(payload))[1]


def read_settings(payload):
    try:
        XbeImage(payload)
        setting, _ = _state(bytes(payload))
        if setting is None:
            return {'status':'retail', 'mode':'retail', 'custom_rate':REALISTIC_RATE / 1000}
        return {'status':'applied', 'mode':setting.mode, 'custom_rate':setting.rate / 1000}
    except ERRORS as exc:
        return {'status':'foreign', 'reason':str(exc)}


def status(payload):
    return read_settings(payload)['status']


def apply(payload, level='realistic', *, custom_rate=0.310):
    """Install, retune or restore on an existing standard executable without moving installed owners."""
    wanted = _setting(level, custom_rate)
    source = bytes(payload)
    XbeImage(source)
    original, physical = _state(source)
    receipt = {'owner':OWNER, 'mode':level, 'custom_rate':wanted.rate / 1000 if wanted else None}
    if original == wanted and (wanted is None or scoring.status(source) == 'applied'):
        return source, {**receipt, 'status':'already_applied' if wanted else 'retail', 'changed_bytes':0}
    if wanted is None:
        result = physical
    else:
        _validate_simulation(physical)
        bank = _bank_allocation(physical)
        if bank is None:
            physical, receipt['allocation'] = space.extend_scaleout(physical, REQUESTS)
            bank = _bank_allocation(physical)
        result = _transform(physical, _edits(physical, bank, wanted), restoring=False)
    confirmed, restored = _state(result)
    _require(confirmed == wanted and restored == physical, 'Simulated QB injury settings failed readback')
    _require(scoring.status(result) == ('applied' if wanted else 'retail'), 'Simulated kicking failed readback')
    return result, {**receipt, 'status':'applied' if wanted else 'retail', 'changed_bytes':space.count_differing_bytes(source,result),
                    'file_growth':len(result) - len(source)}

"""Reversible 128 MiB simulated quarterback injuries and the matched scheduled passing model.

Install the running-back owner before this option: installed after it, that owner's weekly jump lands where this
option expects the game's own tail and the option reads foreign (Retail and re-apply refuse); a route that turns the
running-back owner on later must restore Retail first, install it, then apply the option again.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import struct

from . import nfl2k5_k128 as memory
from . import nfl2k5_lineup_roles as lineup
from . import nfl2k5_sim_rb_injuries as running_backs
from . import nfl2k5_sim_realism as simulator
from . import nfl2k5_sim_scoring as scoring
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = space.QB_INJURY_OWNER
REQUESTS = (space.QB_INJURY_REQUEST,)
REALISTIC_RATE = 310
MARK = struct.Struct('<8sIII')
# Slices 1 (QBMEDv1), 2 (QBMEDv2) and 3 (QBMEDv3) are read and reversed through their frozen code modules; every apply
# writes the current revision. Slice 2 added the line, edge and ball-carrier checks and parks the weekly running-back
# roll; slice 3 added receivers, tight ends, fullbacks, defensive tackles, linebackers and defensive backs; revision 4
# (QBMEDv4) adds the long-franchise stability factor (pos3/DESIGN.md addendum).
SIGNATURES = {1: b'QBMEDv1\0', 2: b'QBMEDv2\0', 3: b'QBMEDv3\0', 4: b'QBMEDv4\0'}
REVISION = 4
SIGNATURE = SIGNATURES[REVISION]
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
    revision: int = REVISION

    def marker(self):
        mode = 1 if self.mode == 'realistic' else 2
        return MARK.pack(SIGNATURES[self.revision], mode, self.rate, 0)

    @classmethod
    def from_marker(cls, raw):
        signature, mode, rate, reserved = MARK.unpack(raw)
        revision = next((number for number, known in SIGNATURES.items() if known == signature), None)
        _require(revision is not None and reserved == 0 and mode in (1, 2), 'Unknown simulated QB injury settings marker')
        _require(rate <= 100000 and (mode != 1 or rate == REALISTIC_RATE), 'Unknown simulated QB injury rate')
        return cls('realistic' if mode == 1 else 'custom', rate, revision)


def _runtime(revision):
    """The code module that authored this revision's bank and edits (slices 1, 2 and 3 are frozen copies)."""
    if revision == 1:
        from . import nfl2k5_sim_qb_injuries_code_b81_slice1 as code
    elif revision == 2:
        from . import nfl2k5_sim_qb_injuries_code_b81_slice2 as code
    elif revision == 3:
        from . import nfl2k5_sim_qb_injuries_code_b81_slice3 as code
    else:
        from . import nfl2k5_sim_qb_injuries_code as code
    _require(code.MARK_SIGNATURE == SIGNATURES[revision] if revision > 1 else not hasattr(code, 'MARK_SIGNATURE'),
             'Simulated QB injury code module does not match its settings revision')
    return code


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


def _running_back_va(payload):
    """The running-back owner's weekly entry when its cave is installed, decided by bytes alone.

    Never asks running_backs.status here: that reads through physical_view, which calls back into this module.
    """
    rows = [r for r in space.layout(payload)['allocations'] if r['owner'] == running_backs.OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and tuple(rows[0][k] for k in ('owner','kind','size','align')) == running_backs.REQUESTS[0],
             'Unknown simulated running-back injury allocation')
    row = rows[0]
    if XbeImage(payload).read(row['va'], row['size']) == b'\xcc' * row['size']:
        return None
    return row['va']


def _edits(payload, bank, setting, *, kicking=None):
    """The option's whole edit list.

    The in-place simulated scoring sites (beta 81 scoring slice) ride with it: ``kicking`` None writes the current
    defaults, a dict writes those parameters (``nfl2k5_sim_scoring.parameters``), False leaves the sites out (an
    install from before the scoring slice).
    """
    code = _runtime(setting.revision)
    image = XbeImage(payload)
    sim, data = simulator._allocations(payload)
    _require(sim['size'] == simulator.CODE_SIZE, 'Update simulated season realism before enabling QB injuries')
    base = bank['va']
    addresses = (base, sim['va'], data['va'], _lineup_va(payload))
    body = code.bank_bytes(image.read, *addresses, rate=setting.rate, marker=setting.marker())
    _require(len(body) == bank['size'], 'Incorrect simulated QB injury runtime size')
    # Slice 2: with a rate above zero the weekly running-back jump is the expected byte run and the game's own tail
    # is installed (code.edits adds it only then). The usual authentication refuses anything else at that site.
    extra = {} if setting.revision == 1 else {'rb_va': _running_back_va(payload)}
    scoring_sites = () if kicking is False else scoring.edits(**(kicking or {}))
    return (*code.edits(*addresses, rate=setting.rate, **extra), *scoring_sites,
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
    # Only on the restored executable, where the weekly running-back site holds that owner's own bytes again.
    _require(running_backs.status(payload) in ('retail', 'applied', 'previous'),
             'Simulated QB injuries found an unknown running-back injury patch')


@lru_cache(maxsize=1)
def _state(payload: bytes):
    """Return the physical simulator only after the entire installed option matches its authored bytes."""
    if not space.is_scaleout(payload) or not any(r[0] == OWNER for r in space._scale_directory_requests(payload)):
        _require(scoring.installed(payload)[0] == 'retail', 'Simulated kicking bytes without the simulator option')
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
        _require(scoring.installed(payload)[0] == 'retail', 'Simulated kicking bytes beside an empty simulator option')
        return None, payload
    marker = image.read(allocation['va'] + code.MARK_OFFSET, MARK.size)
    setting = _Setting.from_marker(marker)
    # An option installed before the scoring slice has retail scoring sites; apply() upgrades it in place.
    kicking, installed = scoring.installed(payload)
    _require(kicking in ('applied', 'retail'), 'Foreign or mixed simulated kicking bytes')
    restored = _transform(payload, _edits(payload, allocation, setting,
                                          kicking=installed if kicking == 'applied' else False), restoring=True)
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
        return {'status':'applied', 'mode':setting.mode, 'custom_rate':setting.rate / 1000, 'revision':setting.revision,
                'positions':setting.revision >= 2 and setting.rate > 0}
    except ERRORS as exc:
        return {'status':'foreign', 'reason':str(exc)}


def status(payload):
    return read_settings(payload)['status']


def apply(payload, level='realistic', *, custom_rate=0.310, breakaway_stop=None):
    """Install, retune or restore on an existing standard executable without moving installed owners.

    A slice 1, 2 or 3 install is reversed exactly and the current revision written fresh, even at the same mode and
    rate.
    """
    wanted = _setting(level, custom_rate)
    kick = scoring.parameters(breakaway_stop_beyond=breakaway_stop)   # validated; None = the shipped default
    source = bytes(payload)
    XbeImage(source)
    original, physical = _state(source)
    receipt = {'owner':OWNER, 'mode':level, 'custom_rate':wanted.rate / 1000 if wanted else None}
    if original == wanted and (wanted is None or scoring.installed(source) == ('applied', kick)):
        return source, {**receipt, 'status':'already_applied' if wanted else 'retail', 'changed_bytes':0}
    if wanted is None:
        result = physical
    else:
        _validate_simulation(physical)
        bank = _bank_allocation(physical)
        if bank is None:
            physical, receipt['allocation'] = space.extend_scaleout(physical, REQUESTS)
            bank = _bank_allocation(physical)
        result = _transform(physical, _edits(physical, bank, wanted, kicking=kick), restoring=False)
        receipt['breakaway_stop'] = kick['breakaway_stop_beyond']
        receipt['revision'] = wanted.revision
        if original is not None and original.revision != wanted.revision:
            receipt['upgraded_from'] = f'slice{original.revision}'
    confirmed, restored = _state(result)
    _require(confirmed == wanted and restored == physical, 'Simulated QB injury settings failed readback')
    _require(scoring.installed(result) == (('applied', kick) if wanted else ('retail', None)),
             'Simulated kicking failed readback')
    return result, {**receipt, 'status':'applied' if wanted else 'retail', 'changed_bytes':space.count_differing_bytes(source,result),
                    'file_growth':len(result) - len(source)}

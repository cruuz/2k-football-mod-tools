"""PROVED OFFLINE: native MyNFL start/rollover, with explicit evidence boundaries.

A real contract fragment is required for financial-gate proof. --control-minimums
instead makes a synthetic test fixture using cited CBA minimums. That mode is
never a real-player contract fragment or proof of the 2026 league's finances.
No xemu, rendering, save I/O, or raw memory dump is used.
"""
from __future__ import annotations
import argparse
from collections import Counter
import struct
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.nfl2k5_supersim_draft_fixture import Machine, retail_bytes, retail_roster
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_franchise_economy as economy
from tools.franchise_economy.contracts import FIELDS, fit_schedule

RELEASE_BLOCKER = ('DESIGN: five-field cap fits do not preserve original cash/APY, exact future '
                   'cap schedules or legacy team dead money; native gates alone are not release approval')


def assess(result):
    """PROVED OFFLINE: gate counts are separate from a current-NFL release claim."""
    checks = {}
    for key in ('finances_start', 'finances_rollover', 'finances_after_free_agency'):
        rows = result.get(key, [])
        checks[key] = {'cap_pass': sum(r['cap_pass'] for r in rows),
                       'native_gate_pass': sum(bool(r['native_gate']) for r in rows), 'teams': len(rows)}
    result['checks'] = checks
    result['native_financial_gates_proved'] = (
        result['scope'] == 'modern-contract-fragment' and result['status'] == 'completed'
        and all(r['cap_pass'] == r['native_gate_pass'] == r['teams'] == 32 for r in checks.values()))
    result['release_proof'] = False
    result['release_blocker'] = RELEASE_BLOCKER


def start(body, payload):
    m = Machine(payload, trace_writes=False)
    m.uc.mem_write(m.ARENA + 0x300, body)
    m.fixup_roster(m.ARENA + 0x340)
    m.seed(12345)
    for a, v in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, 5), (0xE60010, 5)):
        m.put(a, v)
    m.call(0x13EE10, budget=150_000_000)
    return m


def finances(m):
    rows = []
    for team in range(32):
        p = m.team_base + team * 500
        # Recompute through the native salary walker before every observation.
        m.call(0xC3F00, ecx=p)
        salary = m.get(p + 0x124)
        cap = m.call(0x13ECA0, ecx=p, edx=1, args=(0,))
        dead = struct.unpack('<H', m.uc.mem_read(p + 0x19c, 2))[0]
        name_ptr = m.get(p + 0x104)
        name = bytes(m.uc.mem_read(name_ptr, 64)).decode('utf-16-le', 'replace').split('\0')[0]
        rows.append({'team': team, 'name': 'Commanders' if name == 'Redskins' else name,
                     'payroll_real_dollars': salary * 4000,
                     'cap_space_real_dollars': (cap - salary) * 4000,
                     'dead_money_ledger_real_dollars': dead * 4000,
                     'effective_dead_money_real_dollars': (m.get(0xE3C278) - cap) * 4000,
                     'players': m.uc.mem_read(p + 0x11C, 1)[0],
                     'salary_game_thousands': salary, 'cap_game_thousands': cap,
                     'cap_pass': salary <= cap, 'native_gate': m.call(0x2BF950, ecx=p)})
    return rows


def control(body):
    doc = rr.RosterDocument(body)
    data = json.loads((ROOT / 'data/nfl2k5_franchise_economy.json').read_text())
    edits, cache = [], {}
    for p in doc.players:
        if not any(t < 32 for t in p.teams):
            continue
        minimum = data['minimums']['dollars'][min(rr.accrued_seasons(p.record.values['years_pro']), 7)]
        term = 1 + p.index % 2
        key = (minimum, term)
        if key not in cache:
            cache[key] = fit_schedule([minimum + year * 45000 for year in range(term)])
        fit = cache[key]
        edits.append({'pool': p.pool, 'index': p.index, 'first': p.first,
                      'last': p.last, 'fields': fit['fields']})
    return rr.apply_body(body, {'schema': rr.EDITS_SCHEMA, 'edits': edits})


def run(body, *, label, out, patch=True):
    before = time.monotonic()
    payload = retail_bytes()
    if patch:
        payload, _ = economy.apply(payload)
    m = start(body, payload)
    result = {'evidence': 'PROVED OFFLINE', 'scope': label, 'release_proof': False,
              'roster_sha256': hashlib.sha256(body).hexdigest(), 'xbe_sha256': hashlib.sha256(payload).hexdigest(),
              'seed': 12345, 'finances_start': finances(m), 'transitions': [], 'status': 'running'}
    notices, visits = [], Counter()
    def notice():
        p = m.reg('EDX')
        notices.append(bytes(m.uc.mem_read(p, 512)).decode('utf-16-le', 'replace').split('\0')[0])
        m.ret()
    m.leaf(0x177990, lambda: m.ret(pop=4), reason='progress renderer only')
    m.leaf(0x14E520, notice, reason='informational dialog acknowledgement only')
    def decision(*_):
        raise AssertionError(f'unhandled decision dialog, caller {m.get(m.reg("ESP")):#x}')
    m.uc.hook_add(m.u.UC_HOOK_CODE, decision, begin=0x14E440, end=0x14E440)
    addresses = (0xC7A20, 0x1356D0, 0x247B40, 0x3228A0, 0x322980, 0x323B30, 0x323D80, 0x324060, 0x322BB0, 0x322EB0, 0x2BFBE0, 0x2BD900)
    for address in addresses:
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_, a=address: visits.update([a]), begin=address, end=address)
    def state():
        return {k: m.get(a) for k, a in (('stage', 0xE576A4), ('week', 0xE576B4),
                                        ('end_week', 0xE576B0), ('year', 0xE576B8))}
    def save():
        result.update(native_calls={hex(k): v for k, v in visits.items()}, notices=notices,
                      leaves=m.leaves, seconds=round(time.monotonic() - before, 3), state=state())
        out.write_text(json.dumps(result, indent=2) + '\n')
    menu = m.ARENA + 0x1A0000
    result['transitions'].append(state())
    save()
    try:
        for _ in range(40):
            current = state()
            if current['year'] >= 1 and current['stage'] == 4:
                break
            if current['stage'] == 9 and current['week'] >= current['end_week']:
                # Native zero-owner path ends MyNFL. Register through its real setter.
                m.call(0xC4D30, ecx=m.team_base, edx=1)
                result['temporary_native_owner'] = 0
            address = 0x247D40 if current['stage'] in (7, 8, 9) and current['week'] < current['end_week'] else 0x2480B0
            m.call(address, ecx=menu, budget=3_000_000_000)
            after = state()
            if after == current:
                raise AssertionError('native advance did not change league state')
            result['transitions'].append(after)
            if after['year'] > current['year']:
                result['finances_rollover'] = finances(m)
            save()
            print(json.dumps({'evidence': 'PROVED OFFLINE', **after, 'fixtures': visits[0xC7A20],
                              'seconds': result['seconds']}), flush=True)
        result['finances_after_free_agency'] = finances(m)
        if state()['year'] != 1 or state()['stage'] != 4 or visits[0x247B40] != 1:
            raise AssertionError('did not reach one complete rollover and the next Combine')
        result['status'] = 'completed'
    except Exception as exc:
        result['status'] = 'stopped'
        result['failure'] = f'{type(exc).__name__}: {exc}'
        result['eip'] = hex(m.reg('EIP'))
        # A budget stop is not called a hang without stronger evidence.
    assess(result)
    save()
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', type=Path, required=True)
    ap.add_argument('--ratings', type=Path)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--fragment', type=Path)
    group.add_argument('--control-minimums', action='store_true')
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    body = retail_roster()
    for path in (args.base, args.ratings):
        if path:
            body, receipt = rr.apply_body(body, path)
            if receipt['log']:
                raise ValueError(f'input {path} logged discrepancies')
    if args.fragment:
        fragment = rr.read_edits(args.fragment)
        meta = fragment.get('fc_economy', {})
        required = sum(any(t < 32 for t in p.teams) for p in rr.RosterDocument(body).players)
        if meta.get('scale') != 4 or meta.get('resolved', meta.get('matched')) != required or meta.get('required') != required:
            raise ValueError('complete matching 1:4 fragment required')
        if any(set(row.get('fields', {})) != FIELDS or set(row) - {'pool', 'index', 'first', 'last', 'fields'} for row in fragment['edits']):
            raise ValueError('fragment contains something other than contract fields')
        body, receipt = rr.apply_body(body, fragment)
        label = 'modern-contract-fragment'
    else:
        body, receipt = control(body)
        label = 'synthetic CBA-minimum control, not player contracts'
    if receipt['log']:
        raise ValueError('contract replay logged discrepancies')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    result = run(body, label=label, out=args.out)
    print(json.dumps({'status': result['status'], 'scope': label, 'seconds': result['seconds']}))
    return 0 if (result['native_financial_gates_proved'] or args.control_minimums and result['status'] == 'completed') else 2


if __name__ == '__main__':
    raise SystemExit(main())

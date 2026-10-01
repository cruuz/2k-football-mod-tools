"""PROVED OFFLINE: bounded native decisions on explicitly synthetic trade cases."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, retail_roster
from tools.franchise_economy.probe import start
from mod_editor.core import nfl2k5_franchise_economy as economy


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    m = start(retail_roster(), economy.apply(retail_bytes())[0])
    m.put(0xE576A4, 5)
    for team in range(32):
        m.put(m.team_base + team * 500 + 0x124, 30000)
    m.leaf(0x14E540, lambda: m.ret(1), reason='user confirms the proposed trade; native CPU decision remains')
    m.leaf(0x14E520, lambda: m.ret(), reason='informational rejection display only')
    trade, sums = m.ARENA + 0x1A0000, m.ARENA + 0x1A0400
    def reset():
        m.uc.mem_write(trade, bytes(0x100))
        m.put(trade + 8, m.team_base)
        m.put(trade + 0x20, m.team_base + 500)
    def decision(name, assumptions):
        legal = m.call(0x2BAE90, eax=trade, args=(sums, sums + 4, 0))
        offered, requested = m.get(sums), m.get(sums + 4)
        score = min(1, max(0, .8 + 2.5 * (offered - requested) / (offered + requested))) if offered + requested else 0
        accepted = m.call(0x2BC380, ebx=trade, args=(1,), budget=5_000_000)
        return {'evidence': 'PROVED OFFLINE', 'case': name, 'fixture': 'DESIGN: ' + assumptions,
                'legal': bool(legal), 'offered': offered, 'requested': requested,
                'unpenalized_score': round(score, 6), 'accepted': bool(accepted)}
    rows = []
    for a, b in ((1, 7), (7, 1), (1, 1), (1, 2)):
        reset()
        m.uc.mem_write(trade + 0x18, struct.pack('<H', a))
        m.uc.mem_write(trade + 0x30, struct.pack('<H', b))
        rows.append(decision(f'round {a} slot 1 for round {b} slot 1', 'picks only, known current draft order'))
    # INFERRED: map observed overall slots into the native 32-pick rounds.
    # This preserves chart rank but does not add compensatory pick ownership.
    def ordinal(n):
        return ((n - 1) // 32 + 1) | (((n - 1) % 32) << 6)
    for full in (True, False):
        reset()
        picks = [ordinal(34), ordinal(99), 3 | 0x1000] if full else [ordinal(34)]
        for i, pick in enumerate(picks):
            m.uc.mem_write(trade + 0x18 + i * 2, struct.pack('<H', pick))
        m.uc.mem_write(trade + 0x30, struct.pack('<H', ordinal(25)))
        row = decision('Giants-Texans observed pick package' if full else 'Giants-Texans package with sweeteners removed',
                       '2025 overall ranks mapped to native slots; future third valued at the modeled median')
        row['source'] = 'https://www.giants.com/news/jaxson-dart-trade-details-nfl-draft-room-joe-schoen-brian-daboll-abdul-carter-ole-miss'
        row['real_world_status'] = 'observed accepted package' if full else 'hypothetical reduced offer; no real-world rejection claimed'
        rows.append(row)
    pa, pb = m.get(m.team_base), m.get(m.team_base + 500)
    originals = [bytes(m.uc.mem_read(p, 84)) for p in (pa, pb)]
    def player(p, original, *, position, experience, total, rating=85):
        record = bytearray(original)
        record[8] = 4
        record[0x24:0x28] = bytes((4, experience, 2, 4))
        record[0x35] = position
        record[0x38:] = bytes([rating] * (84 - 0x38))
        struct.pack_into('<H', record, 10, total)
        m.uc.mem_write(p, bytes(record))
    young = dict(position=0, experience=3, total=500)
    old = dict(position=0, experience=20, total=7500)
    rb = dict(position=7, experience=3, total=500)
    pricey = dict(position=0, experience=3, total=7500)
    for label, a, b in (('young cheap QB for aging costly QB', young, old),
                        ('aging costly QB for young cheap QB', old, young),
                        ('cheap QB for same-rated expensive QB', young, pricey),
                        ('expensive QB for same-rated cheap QB', pricey, young),
                        ('QB for same-rated RB', young, rb), ('RB for same-rated QB', rb, young)):
        reset()
        player(pa, originals[0], **a)
        player(pb, originals[1], **b)
        m.put(trade + 12, pa)
        m.put(trade + 0x24, pb)
        rows.append(decision(label, f'all native rating bytes 85; offered={a}; requested={b}; balanced four-year terms'))
    output = {'evidence': 'PROVED OFFLINE', 'scope': 'synthetic native trade decisions, not reconstructed NFL transactions',
              'threshold': 0.82, 'cases': rows, 'leaves': m.leaves,
              'limitations': 'DESIGN: pick and positional-market sources inform the model; these cases do not establish actual NFL acceptance or rejection of hypothetical trades.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()

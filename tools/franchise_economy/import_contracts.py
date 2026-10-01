"""DESIGN: pinned nflverse/OTC import with separately identified fallback rules.

Use the current historical_contracts.parquet, or a lossless JSON conversion
(table.to_pylist()) of it. APY and all season money fields are millions, as
specified by the nflreadr dictionary. No network access is performed.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr
from tools.franchise_economy.contracts import fit_schedule, fit_minimum, FIELDS

SOURCE = 'https://github.com/nflverse/nflverse-data/releases/tag/contracts'
DICTIONARY = 'https://nflreadr.nflverse.com/articles/dictionary_contracts.html'
SNAPSHOT_SHA256 = '0c13b84878e2a2d4aa1845bb5bf94ff2092f8bf646a5e2a570af94e8cb626418'
JSON_SHA256 = 'eee20a3664e4c11d17cc4f7e51aa718ddc64b1e5692a1460475d78c51973d038'
ASSET_TIME = '2026-09-24T12:40:52Z'
REVIEW = ROOT / 'fc/data/identity_review.json'


def normalize(name):
    s = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode().lower()
    words = re.sub('[^a-z0-9 ]', '', s).split()
    if words and words[-1] in ('jr', 'sr', 'ii', 'iii', 'iv', 'v'):
        words.pop()
    return ''.join(words)


def millions(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0:
            raise ValueError('invalid money')
        return int((n * 1_000_000).to_integral_value())
    except InvalidOperation as exc:
        raise ValueError('missing or invalid money') from exc


def identifier(value):
    if value is None or str(value).lower() in ('', 'nan', 'none'):
        return ''
    return str(value).removesuffix('.0')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_pinned_parquet(path, pin, *, active_only=False):
    """Bounded current-snapshot reader; dates and SHA-256 must travel together."""
    if path.suffix != '.parquet' or not pin.get('updated_at') or not pin.get('url'):
        raise ValueError('a dated Parquet source receipt is required')
    if digest(path) != pin.get('sha256'):
        raise ValueError('contract input differs from its pinned snapshot')
    import pyarrow.parquet as pq
    rows = []
    for batch in pq.ParquetFile(path).iter_batches(batch_size=256, use_threads=False):
        rows.extend(r for r in batch.to_pylist() if not active_only or
                    (r['is_active'] and (r['year_signed'] or 9999) <= 2026))
    return rows


def read_rows(path):
    expected = SNAPSHOT_SHA256 if path.suffix == '.parquet' else JSON_SHA256
    if path.suffix not in ('.json', '.parquet'):
        raise ValueError('use current parquet or pinned lossless JSON, never the stale CSV')
    if digest(path) != expected:
        raise ValueError('contract input differs from the reviewed September 24 snapshot')
    if path.suffix == '.parquet':
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise ValueError('reading parquet needs pyarrow; use the pinned JSON conversion') from exc
        return pq.read_table(path).to_pylist()
    data = json.loads(path.read_text())
    meta = data['meta']
    if (meta['parquet_sha256'] != SNAPSHOT_SHA256 or meta['asset_updated_at'] != ASSET_TIME
            or meta['rows'] != len(data['rows']) or meta['rows'] != 52944):
        raise ValueError('lossless conversion provenance differs from reviewed receipt')
    parquet = path.with_suffix('.parquet')
    if not parquet.exists() or digest(parquet) != SNAPSHOT_SHA256:
        raise ValueError('the pinned source parquet must accompany the lossless conversion')
    return data['rows']


def nested(value):
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict):
        keys = list(value)
        value = [dict(zip(keys, row)) for row in zip(*(value[k] for k in keys))]
    if not isinstance(value, list) or any(not isinstance(r, dict) for r in value):
        raise ValueError('missing nested season_history; APY is not an annual cap schedule')
    return value


def cap_schedule(row, year=2026):
    """DESIGN: only continuous playable years; no inferred extension/void cash."""
    schedule = {}
    excluded = []
    for season in nested(row.get('season_history')):
        label = str(season.get('year', ''))
        if not re.fullmatch(r'\d{4}(?:\.0)?', label):
            excluded.append(season)
            continue
        season_year = int(float(label))
        if season_year < year:
            continue
        cap = millions(season.get('cap_number'))
        base = millions(season.get('base_salary'))
        # A pure accounting/void year is not another playable contract season.
        if base == 0 or cap == 0 or season.get('cash_paid') == 0:
            excluded.append(season)
            continue
        if season_year in schedule:
            raise ValueError('multiple team charges in one year require a reviewed allocation')
        schedule[season_year] = cap
    years = sorted(schedule)
    if not years or years != list(range(year, year + len(years))):
        raise ValueError('no continuous cap schedule beginning in 2026')
    if len(years) > 15:
        raise ValueError('more than fifteen future years exceeds the contract term nibble')
    return [schedule[y] for y in years], excluded


def player_index(rows):
    out = {}
    for row in rows:
        names = {row.get('display_name', ''), row.get('player', '')}
        for key in ('first_name', 'common_first_name', 'football_name'):
            if row.get(key) and row.get('last_name'):
                names.add(row[key] + ' ' + row['last_name'])
        for name in names:
            if name:
                out.setdefault(normalize(name), []).append(row)
    return out


def fallback_schedule(player, row, data):
    """DESIGN: imported active-roster role controls modeled missing schedules.

    Drafted 2026 rookies use linear interpolation of the cited OTC four-year
    cap schedules by actual draft slot. Other missing histories, undrafted
    rookies, practice players and unsigned veterans use one credited-season
    minimum deal. Native years_pro proxies credited seasons. No APY is used
    as an annual cap hit. These are never counted as observed schedules.
    """
    if row and row.get('draft_year') == 2026 and row.get('draft_overall'):
        pick = int(row['draft_overall'])
        knots = [r for r in data['rookie_anchors']['rows'] if len(r.get('cap_hits', [])) == 4]
        knots.sort(key=lambda r: r['pick'])
        source_pick = pick
        pick = max(knots[0]['pick'], min(pick, knots[-1]['pick']))
        lower = max((r for r in knots if r['pick'] <= pick), key=lambda r: r['pick'])
        upper = min((r for r in knots if r['pick'] >= pick), key=lambda r: r['pick'])
        ratio = (pick - lower['pick']) / (upper['pick'] - lower['pick']) if upper != lower else 0
        cap = [round(a['cap_number'] + ratio * (b['cap_number'] - a['cap_number']))
               for a, b in zip(lower['cap_hits'], upper['cap_hits'])]
        return cap, {'evidence': 'DESIGN', 'rule': 'OTC draft-slot cap schedule interpolation',
                     'draft_slot': source_pick, 'scale_slot': pick, 'knots': [lower['pick'], upper['pick']],
                     'source': data['rookie_anchors']['source'] if 'source' in data['rookie_anchors'] else 'https://overthecap.com/draft'}
    pro = min(player.record.values['years_pro'], 7)
    return [data['minimums']['dollars'][pro]], {
        'evidence': 'DESIGN', 'rule': 'one-year active-roster CBA minimum',
        'experience_proxy': pro, 'source': 'https://nflpaweb.blob.core.windows.net/website/PDFs/CBA/March-15-2020-NFL-NFLPA-Collective-Bargaining-Agreement-Final-Executed-Copy.pdf'}


def audit(body, identities, contracts=None):
    doc = rr.RosterDocument(body)
    players = [p for p in doc.players if any(t < 32 for t in p.teams)]
    name_index, contract_names = player_index(identities), player_index(contracts or [])
    reviews = {(r['pool'], r['index']): r for r in json.loads(REVIEW.read_text())['entries']}
    data = json.loads((ROOT / 'data/nfl2k5_franchise_economy.json').read_text())
    by_gsis, by_otc = {}, {}
    for row in contracts or []:
        for key, index in (('gsis_id', by_gsis), ('otc_id', by_otc)):
            ident = identifier(row.get(key))
            if ident:
                index.setdefault(ident, []).append(row)
    ledger, unmatched, edits, exceptions = [], [], [], []
    id_matches = 0
    for player in players:
        team = next(t for t in player.teams if t < 32)
        identity_rows = name_index.get(normalize(player.display), [])
        unique_ids = {identifier(r.get('gsis_id')): r for r in identity_rows if identifier(r.get('gsis_id'))}
        identity = next(iter(unique_ids.values())) if len(unique_ids) == 1 else None
        review = reviews.get((player.pool, player.index))
        if review:
            if review['roster_name'] != player.display or review['roster_team'] != doc.teams[team].nickname:
                raise ValueError('identity review belongs to a different frozen roster')
            identity = review
        if identity:
            id_matches += 1
        candidates, method = [], 'normalized-name'
        if identity:
            candidates = by_gsis.get(identifier(identity.get('gsis_id')), [])
            method = 'gsis_id'
            if not candidates:
                candidates = by_otc.get(identifier(identity.get('otc_id')), [])
                method = 'otc_id'
        if not candidates:
            candidates = contract_names.get(normalize(player.display), [])
            method = 'normalized-name'
        entry = {'pool': player.pool, 'index': player.index, 'name': player.display,
                 'team': team, 'team_name': doc.teams[team].nickname,
                 'gsis_id': identity.get('gsis_id') if identity else None,
                 'otc_id': identifier(identity.get('otc_id')) if identity else None,
                 'reviewed_identity': bool(review)}
        if contracts is None:
            unmatched.append({**entry, 'reason': 'nflverse contract snapshot unavailable'})
            continue
        candidates = [r for r in candidates if r.get('is_active') in (True, 1, 'TRUE', 'true')
                      and int(r.get('year_signed') or 9999) <= 2026]
        if len(candidates) > 1 and review and 'active_value_millions' in review:
            exceptions.append({**entry, 'evidence': 'PROVED OFFLINE', 'reason': review['reason'],
                               'active_candidates': [{k:r[k] for k in ('player','team','otc_id','value','years')} for r in candidates]})
            candidates = [r for r in candidates if r['value'] == review['active_value_millions']]
        if len(candidates) > 1:
            unmatched.append({**entry, 'reason': f'{len(candidates)} active candidate contracts'})
            continue
        row = candidates[0] if candidates else None
        modeled = None
        try:
            if row is None:
                raise ValueError('no active contract in pinned release')
            cap, excluded = cap_schedule(row)
        except (ValueError, TypeError) as exc:
            # Only absent annual histories qualify. Discontinuous or duplicate
            # positive schedules remain fatal and require an explicit review.
            reason = str(exc)
            if reason not in ('no active contract in pinned release', 'no continuous cap schedule beginning in 2026'):
                unmatched.append({**entry, 'reason': reason})
                continue
            future = [s for s in nested(row['season_history']) if str(s.get('year','')).isdigit()
                      and int(s['year']) >= 2026 and s.get('cap_number')] if row else []
            if future:
                unmatched.append({**entry, 'reason': 'noncontinuous future schedule requires review'})
                continue
            cap, modeled = fallback_schedule(player, row, data)
            excluded = []
            exceptions.append({**entry, 'reason': reason, **modeled})
        fit = (fit_minimum(cap[0]) if modeled and modeled["rule"] == "one-year active-roster CBA minimum"
               else fit_schedule(cap, opening_priority=True))
        headline = {k: millions(row[k]) if row.get(k) is not None else None
                    for k in ('apy','value','guaranteed')} if row else None
        history = nested(row['season_history']) if row else []
        future = [s for s in history if str(s.get('year','')).isdigit() and int(s['year']) >= 2026]
        ledger.append({**entry, 'match_method': method if row else None,
                       'schedule_kind': 'modeled' if modeled else 'observed', 'fallback': modeled,
                       'headline_dollars': headline, 'source_years': row.get('years') if row else None,
                       'year_signed': row.get('year_signed') if row else None,
                       'source': row.get('player_page') if row else None,
                       'source_team': row.get('team') if row else None,
                       'gsis_id': row.get('gsis_id') if row else entry['gsis_id'],
                       'otc_id': row.get('otc_id') if row else entry['otc_id'],
                       'contract_history': row.get('contract_history') if row else [],
                       'season_history_2026_and_later': future,
                       'excluded_years': [r for r in excluded if r.get('year') != 'Total'], 'fit': fit})
        edits.append({'pool': player.pool, 'index': player.index, 'first': player.first,
                      'last': player.last, 'fields': fit['fields']})
    observed = sum(r['schedule_kind'] == 'observed' for r in ledger)
    matches = sum(r['match_method'] is not None for r in ledger)
    report = {'evidence': 'PROVED OFFLINE', 'source': SOURCE, 'dictionary': DICTIONARY,
              'base_body_sha256': hashlib.sha256(body).hexdigest(), 'rostered_players': len(players),
              'identity_matches': id_matches, 'contract_matches': matches, 'observed_schedules': observed,
              'modeled_schedules': len(ledger) - observed, 'resolved': len(ledger),
              'contract_match_rate': matches / len(players) if players else 0,
              'status': 'complete' if not unmatched and players else 'blocked',
              'unmatched': unmatched, 'exceptions': exceptions, 'ledger': ledger}
    report['by_team'] = []
    for team in range(32):
        rows = [r for r in ledger if r['team'] == team]
        total = sum(team in p.teams for p in players)
        n = sum(r['match_method'] is not None for r in rows)
        obs = sum(r['schedule_kind'] == 'observed' for r in rows)
        report['by_team'].append({'team': team, 'name': doc.teams[team].nickname, 'players': total,
                                  'active_contract_matches': n, 'match_rate': n / total,
                                  'observed_schedules': obs, 'modeled_schedules': len(rows) - obs,
                                  'source_opening_payroll': sum(r['fit']['source_cap_dollars'][0] for r in rows),
                                  'represented_opening_payroll': sum(r['fit']['represented_cap_dollars'][0] for r in rows)})
    fragment = {'schema': rr.EDITS_SCHEMA, 'name': 'DESIGN: 2026 contracts, internal 1:4 scale',
                'author': 'fc', 'source_body_sha256': report['base_body_sha256'],
                'players': len(doc.players), 'edits': edits,
                'fc_economy': {'scale': 4, 'year': 2026, 'evidence': 'DESIGN',
                               'matched': matches, 'resolved': len(ledger), 'required': len(players),
                               'observed_schedules': observed, 'modeled_schedules': len(ledger) - observed}}
    replayed, receipt = rr.apply_body(body, fragment)
    if receipt['log'] or any(set(e['fields']) != FIELDS for e in edits):
        raise ValueError('contract-only replay invariant failed')
    report['replay'] = receipt
    report['result_body_sha256'] = hashlib.sha256(replayed).hexdigest()
    return report, fragment


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', type=Path, required=True, help='modern base roster-edits JSON')
    ap.add_argument('--players', type=Path, required=True, help='nflverse players.csv.gz')
    ap.add_argument('--contracts', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    from tests.nfl2k5_supersim_draft_fixture import retail_roster
    body, base_receipt = rr.apply_body(retail_roster(), args.base)
    if base_receipt['log']:
        raise ValueError('base roster replay logged discrepancies')
    with gzip.open(args.players, 'rt') as f:
        identities = list(csv.DictReader(f))
    rows = read_rows(args.contracts) if args.contracts else None
    report, fragment = audit(body, identities, rows)
    report['source_receipt'] = {'evidence': 'PROVED OFFLINE', 'json_sha256': JSON_SHA256,
                              'parquet_sha256': SNAPSHOT_SHA256, 'asset_updated_at': ASSET_TIME,
                              'json_verified': bool(args.contracts and args.contracts.suffix == '.json'),
                              'parquet_verified': bool(args.contracts)}
    report['inputs'] = {str(p): digest(p)
                        for p in (args.base, args.players, args.contracts, REVIEW, ROOT / 'data/nfl2k5_franchise_economy.json') if p}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'contract_audit.json').write_text(json.dumps(report, indent=2) + '\n')
    target = args.out / 'fc_contract_fragment.json'
    if report['status'] != 'complete':
        # Refuse to leave a stale complete fragment alongside a newer failed audit.
        if target.exists():
            target.unlink()
        print(f"PROVED OFFLINE: {report['identity_matches']}/{report['rostered_players']} identities; "
              f"{report['contract_matches']} contracts. Fragment withheld: {len(report['unmatched'])} unresolved.")
        return 2
    target.write_text(json.dumps(fragment, indent=2) + '\n')
    print(f"PROVED OFFLINE: {len(fragment['edits'])} resolved records; "
          f"{report['observed_schedules']} observed and {report['modeled_schedules']} modeled schedules; "
          "zero replay log lines")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Source-labelled compact historic season rosters, isolated from moment resources.

The audit is intentionally separate from the ESPN moment data. A season roster
cannot overwrite a shared moment file while claiming both owners still apply.
The Build option refuses incomplete source data before copying a disc.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import hashlib

from . import nfl2k5_roster_records as rr

OWNER = 'nfl2k5_historic_rosters'
SCHEMA = OWNER + '/v1'
DATA_DIR = Path(__file__).resolve().parents[2] / 'data/nfl2k5_historic_rosters'
CAPTION = 'Historic season rosters (2026)'
HELP_TEXT = (
    'Season-specific compact rosters for all 75 historic teams. Source citations and '
    'inferred or designed values are listed in the historic roster report. '
    'Requires historic local Team Select. Off in every preset.'
)
DEFAULT_ENABLED = False
REQUESTS = ()


class HistoricRostersError(ValueError):
    """Source or routing proof is incomplete."""


def era_ratings(teams, season, position, starter=False):
    """DESIGN prior for a player without a matched retail rating vector.

    Use the target's five-year era and exact retail position. Each donor is a
    uniquely numbered compatible source candidate. Require eight observations;
    widen symmetrically in five-year steps, never selecting by franchise wins.
    Component-wise median is the reserve prior; upper quartile is the explicitly
    sourced starter prior. It estimates a role relative to the era, not measured
    athletic speed, ability, fame, or an invented 40 time. Keep raw style channels
    from a real median donor, because those bytes are enums, not talent scores.
    """
    donors = []
    radius = 0
    era = season // 5 * 5
    for radius in range(0, 60, 5):
        donors = [s for t in teams if era-radius <= t['year'] <= era+4+radius
                  for s in t['slots'] if s['position'] == position and
                  s['match'] == 'unique_number_position']
        if len(donors) >= 8:
            break
    if not donors:
        raise HistoricRostersError(f'No sourced retail rating donors for {position}')
    quantile = .75 if starter else .5
    # Nearest order statistic gives deterministic integral game bytes.
    at = round((len(donors)-1)*quantile)
    values = {k: sorted(s['ratings'][k] for s in donors)[at] for k in rr.RATING_BYTE_ORDER}
    styles = {'kicking_style', 'power_run_style', 'scramble'}
    donor = min(donors, key=lambda s: (sum(abs(s['ratings'][k]-values[k])
                                         for k in rr.RATING_BYTE_ORDER if k not in styles), s['slot']))
    for key in styles & values.keys():
        values[key] = donor['ratings'][key]
    return values, dict(label='DESIGN', method='same-position era quantile v1', era=[era-radius, era+4+radius],
                        donors=len(donors), quantile=quantile, starter=starter,
                        limitation='Role prior only; individual performance and speed are not established.')


def dataset():
    path = DATA_DIR / 'manifest.json'
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise HistoricRostersError('Historic season roster data is not installed; '
                                  'install the complete source-labelled manifest.') from exc
    if len(raw) > 32 * 1024 * 1024:
        raise HistoricRostersError('Historic season roster manifest exceeds 32 MiB')
    data = json.loads(raw)
    if data.get('schema') != SCHEMA or len(data.get('teams', [])) != 75:
        raise HistoricRostersError('Historic season roster manifest needs all 75 teams')
    if len({t['filename'] for t in data['teams']}) != 75:
        raise HistoricRostersError('Duplicate historic season resource')
    return data


def source_gaps(data=None):
    data = dataset() if data is None else data
    # Recompute; a hand-edited ready flag must never bypass the guard.
    return [dict(team=t['name'], slot=p['slot'], player=p.get('player'), issues=p['blockers'])
            for t in data['teams'] for p in t['players'] if p['blockers']]


def require_build_ready():
    data = dataset()
    gaps = source_gaps(data)
    if gaps:
        teams = len({g['team'] for g in gaps})
        raise HistoricRostersError(
            f'Historic season rosters: {len(gaps)} unresolved slots across {teams} teams; '
            'see ht/HT_REPORT.md and the per-player manifest. No disc was changed.')
    for t in data['teams']:
        rows = t['players']
        require(30 <= len(rows) <= 65, 'historic roster count outside compact team capacity')
        require([p['slot'] for p in rows] == list(range(len(rows))), 'noncontiguous roster slots')
        require(len({p['player'] for p in rows}) == len(rows), 'duplicate roster identity')
        require(t['alias'] == 'HTS-' + t['filename'], 'foreign season alias')
        for p in rows:
            for part in ('first','last'):
                rr.validate_name(p[part])
            require(p['position'] in rr.POSITIONS and 0 <= p['jersey'] <= 99, 'invalid position/number')
            require(60 <= p['height'] <= 90 and 150 <= p['weight'] <= 405, 'invalid size')
            require(1 <= p['depth'] <= 8, 'invalid position depth')
            require(set(p['ratings']) == set(rr.RATING_BYTE_ORDER), 'incomplete rating vector')
            require(all(type(v) is int and 0 <= v <= 100 for v in p['ratings'].values()), 'invalid ratings')
            for field in ('player','membership','jersey','height','weight','position','ratings','depth','equipment','display_name'):
                basis = p['fields'].get(field, {})
                require(basis.get('label') in ('PROVED OFFLINE','INFERRED','DESIGN'), f'uncited {field}')
                require(bool(basis.get('sources') or basis.get('url') or basis.get('method')), f'no basis for {field}')
    return data


def require(ok, message):
    if not ok:
        raise HistoricRostersError(message)


def compile_team(raw, team):
    """Append a new player pool and names; rebuild every roster and special-teams link.

    Team identity, category, franchise label, style and coach retain the input's
    encodings. The old pool is unreachable. No invented player fills a short team.
    """
    from . import nfl2k5_espn25_more_moments as more
    from . import nfl2k5_modern_helmets as helmets
    # hm runs later in the full recipe. Its exact classic mask mapping must be
    # reflected here so readback and equipment agree before and after that pass.
    equipment=helmets.historic_edits()
    if team['outer'] in equipment:
        raw=helmets.compile_historic(raw,team['outer'],equipment)
    doc = rr.RosterDocument(raw[32:])
    require(len(doc.teams)==1 and len(doc.players)==53, 'foreign historic template')
    body = bytearray(raw[32:]); rows = team['players']; t = doc.teams[0].offset
    body.extend(bytes(-len(body)%4)); pool = len(body)
    body.extend(bytes(len(rows)*rr.PLAYER_SIZE))
    counts = {p:sum(r['position']==p for r in rows) for p in rr.POSITIONS}
    names = {}
    for i,row in enumerate(rows):
        at=pool+i*rr.PLAYER_SIZE
        candidates=[p for p in doc.players if p.record.position_name==row['position']]
        donor=doc.players[row['retail_slot']] if row['retail_slot'] is not None else (candidates or doc.players)[0]
        record=donor.record.copy();v=record.values
        v.update(row['ratings']);v.update(position=rr.POSITIONS.index(row['position']),jersey=row['jersey'],
            height=row['height'],weight_raw=row['weight']-150,helmet=0,
            face_mask=donor.record.values['face_mask'] if donor.record.values['face_mask']<12 else 0,
            history_pointer=0,college_pointer=0,injured_reserve=0,unknown_52=0,
            pbp_id=9000+row['jersey'])
        # Unmatched appearance/biography is a game template, not a sourced identity claim.
        depth=row['depth']; pos=row['position']
        v['depth_rank'],v['depth_side']=more._paired_chain(depth,counts[pos]) if pos in more.PAIRED else (depth-1,0)
        for part,field in (('first','first_name_pointer'),('last','last_name_pointer')):
            if row[part] not in names:
                names[row[part]]=more._append_text(body,row[part])
            offset=at+rr.FIELD_BY_NAME[field].offset
            v[field]=(names[row[part]]-offset+1)&0xffffffff
        body[at:at+rr.PLAYER_SIZE]=record.encode()
    count_field,table_field=rr.POOL_FIELDS['primary']
    struct.pack_into('<I',body,doc.obj_base+count_field,len(rows))
    more._set_rel(body,doc.obj_base+table_field,pool)
    slots=[pool+i*rr.PLAYER_SIZE for i in range(len(rows))]
    for i in range(rr.TEAM_SLOTS):
        field=t+4*i
        struct.pack_into('<i',body,field,slots[i]-field+1 if i<len(rows) else 0)
    body[t+rr.TEAM_PLAYER_COUNT]=len(rows)
    flat=[dict(r,**r['ratings']) for r in rows]
    # The kicker byte permits a documented two-way K/P whose primary code is P.
    special_rows=[dict(r,position='K' if 'K' in r.get('special_roles',[]) else r['position']) for r in flat]
    template_roles={at:more._slot_role(doc,raw[32+t+at]) for at in more.SPECIAL_TEAMS}
    special=more.special_teams(slots,dict(zip(slots,special_rows)),template_roles)
    for at,index in special.items():
        body[t+at]=index
    body.extend(bytes(-len(body)%16))
    header=bytearray(raw[:32]);struct.pack_into('<II',header,4,len(body),len(body))
    result=bytes(header+body)
    after=rr.RosterDocument(result[32:])
    require(len(after.players)==len(rows) and after.teams[0].slots==slots,'compact roster readback')
    require(all((p.first,p.last)==(r['first'],r['last']) for p,r in zip(after.players,rows)),'name readback')
    if not any(p.record.position_name=='OLB' for p in doc.players):
        # E2's stock bank uses the same historic 4-3 recode under One-pool.
        # Rebuild merged linebacker ranks through the established roster owner.
        result=more._one_pool(result)
    return result


def image_status(source):
    from . import nfl2k5_historic_styles as styles
    try:
        data=require_build_ready()
        with rr._outer_image()(source) as archive:
            ids={e.name_id:e.index for e in archive.entries}
            present=[styles.name_id(t['alias']) in ids for t in data['teams']]
            if not any(present):
                return 'retail'
            if not all(present):
                return 'foreign'
            for team in data['teams']:
                raw=archive.read_entry(team['outer'])
                if archive.read_entry(ids[styles.name_id(team['alias'])]) != compile_team(raw,team):
                    return 'foreign'
        from . import nfl2k5_historic_teams_quick_game as h1
        return 'applied' if h1.season_routing_status(read_xbe(source)) else 'foreign'
    except (ValueError,OSError,KeyError,IndexError,struct.error):
        return 'foreign'


def read_xbe(path):
    from . import nfl2k5_espn25_rosters as e
    return e.read_xbe(path)


def apply_to_image(path):
    from . import nfl2k5_historic_styles as styles
    from . import nfl2k5_historic_teams_quick_game as h1
    from . import nfl2k5_espn25_rosters as e
    data=require_build_ready()
    if image_status(path)=='applied':
        return dict(status='already_applied',aliases=75)
    require(image_status(path)=='retail','foreign or partial historic roster bank')
    payload=read_xbe(path);patched=h1.enable_season_routing(payload)
    with rr._outer_image()(path) as archive:
        appended=[(t['alias'],compile_team(archive.read_entry(t['outer']),t)) for t in data['teams']]
    appended.append(('HTS-filler.iff',bytes(2048)))
    receipt=styles.rewrite_archive(path,{},appended)
    # Archive installation precedes enabling the filename route.
    write_xbe(path,patched)
    require(image_status(path)=='applied','historic roster transaction readback failed')
    return dict(status='applied',aliases=75,entry_cost=76,**receipt)


def write_xbe(path,payload):
    from . import nfl2k5_espn25_rosters as e
    with open(path,'r+b') as stream:
        offset,before=e._image_xbe(stream)
        e.install_image_xbe(stream,offset,before,payload)


def main():
    """Read-only source summary; the disc writer is invoked through Build."""
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    try:
        gaps = source_gaps()
        print(json.dumps(dict(label='DESIGN', writer_implemented=True,
                              unresolved_slots=len(gaps),
                              unresolved_teams=len({g['team'] for g in gaps}),
                              default_enabled=False), indent=2))
    except HistoricRostersError as exc:
        print(json.dumps(dict(label='DESIGN', writer_implemented=True, error=str(exc)), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

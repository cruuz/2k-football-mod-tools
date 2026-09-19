"""Read-only MyCareer Draft Advisory and 53-man cut-risk estimates.

Targets/maxima are the executable tables read by 0x2BD410/0x2BD400, at
0x521C68/0x521C20. The active roster mode selects the existing retail or
one-pool table interpretation, also used by that patch's writer. An optional
XBE read verifies these tables; this module never patches an executable.

Clubs rank by descending target shortfall, then maximum headroom, then club
index. Counts use active primary players, excluding MyPlayer. Cut risk assumes
MyPlayer joins each club: ties in unboosted overall favor incumbents. High means
rank exceeds the position maximum, or both rank exceeds target and projected
roster exceeds 53. Moderate means either target rank or 53 is exceeded; otherwise
low. These are capacity estimates, not probabilities, scouting or draft control.
Recompute on every request; a changed prospect class or roster mode is refused.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_roster_records as roster
from . import nfl2k5_position_pools as pools
from . import nfl2k5_my_career_prospects as prospects


def roster_tables(scheme='retail', *, xbe=None):
    scheme = roster.normalise_scheme(scheme)
    target = pools.new_targets() if scheme == 'one_pool' else pools.RETAIL_TARGETS
    maximum = pools.new_maxima() if scheme == 'one_pool' else pools.RETAIL_MAXIMA
    if xbe is not None:
        from .nfl2k5_cave_oracle import XbeImage
        image = XbeImage(xbe)
        actual = (struct.unpack('<17I', image.read(pools.ROSTER_TARGETS_VA, 68)),
                  struct.unpack('<17I', image.read(pools.ROSTER_MAXIMA_VA, 68)))
        if actual != (target, maximum):
            raise ValueError('Executable roster tables differ from the selected roster mode. Match the mode before reviewing.')
    return target, maximum


def class_fingerprint(document, scheme='retail'):
    roster.normalise_scheme(scheme)
    rows = []
    for player in document.players:
        if player.pool == 'primary' and player.record.get('player_type') & 0x30:
            # Include flags, names, college, body, ratings and membership. Pointers
            # need not enter the digest; their resolved strings identify the class.
            raw = player.record.encode()
            rows.append([player.index, player.display, player.college, sorted(player.teams),
                         player.offset in document.free_agents, raw[8:16].hex(),
                         raw[24:44].hex(), raw[52:].hex()])
    if not rows:
        raise ValueError('No prospect class remains. Choose the prepared draft save.')
    return hashlib.sha256(json.dumps([scheme, rows], separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()


def estimate(payload, *, player_index, expected_class, scheme='retail', xbe=None):
    """Fresh estimates from a prepared save; no mutation of payload or documents."""
    from . import nfl2k5_my_career as career, nfl2k5_franchise_save as fs
    career.save_key(payload)
    if payload[fs.SEASON_BLOCK + fs.S_MODE] != 2 or payload[fs.SEASON_BLOCK + fs.S_STAGE] != 5:
        raise ValueError('Draft Advisory needs the prepared NFL Draft stage save.')
    document = roster.RosterDocument(payload, base=roster.find_block_base(payload), scheme=scheme)
    if scheme == 'one_pool' and any(p.pool == 'primary' and p.record.get('position') == 10 for p in document.players):
        raise ValueError('This save still has retired OLB players. Reclassify its roster before reviewing the one-pool estimate.')
    fingerprint = class_fingerprint(document, scheme)
    if fingerprint != expected_class:
        raise ValueError('The prospect class or roster mode changed. Prepare MyPlayer again before reviewing Draft Advisory.')
    players = [p for p in document.players if p.pool == 'primary' and p.index == player_index]
    if len(players) != 1 or not players[0].record.get('player_type') & 0x10:
        raise ValueError('MyPlayer is no longer an eligible prospect. Choose the prepared save.')
    player = players[0]
    position = player.record.get('position')
    roster.check_position_code(position, scheme)
    targets, maxima = roster_tables(scheme, xbe=xbe)
    target, maximum = targets[position], maxima[position]
    overall = prospects.native_overall(player.record)
    rows = []
    for team in document.teams:
        if team.index >= 32:
            continue
        if not team.clean_parse or len(set(team.slots)) != len(team.slots):
            raise ValueError('A club roster is malformed. Repair it before reviewing Draft Advisory.')
        active = [document.by_offset[offset] for offset in team.slots if offset != player.offset]
        if any(p.pool != 'primary' or len([club for club in p.teams if club < 32]) != 1 for p in active):
            raise ValueError('A club has invalid or shared player membership. Repair it before reviewing Draft Advisory.')
        peers = [p for p in active if p.record.get('position') == position]
        rank = 1 + sum(prospects.native_overall(p.record) >= overall for p in peers)
        projected = len(active) + 1
        risk = ('High' if rank > maximum or (rank > target and projected > 53) else
                'Moderate' if rank > target or projected > 53 else 'Low')
        rows.append({'club_index': team.index, 'club': team.display,
                     'position_count': len(peers), 'target': target, 'maximum': maximum,
                     'shortfall': max(0, target - len(peers)), 'headroom': maximum - len(peers),
                     'projected_roster': projected, 'projected_position_rank': rank, 'cut_risk': risk})
    rows.sort(key=lambda row: (-row['shortfall'], -row['headroom'], row['club_index']))
    return {'label': 'Draft Advisory and 53-man cut risk: estimates from this save',
            'note': 'Capacity estimates only. These do not change the draft or cut MyPlayer.',
            'class_fingerprint': fingerprint, 'scheme': scheme, 'clubs': rows}


def review_prepared(setup_path, *, scheme='retail'):
    """Reopen all inputs on every review; a stale class never reuses a cached list."""
    from . import nfl2k5_my_career as career
    setup_path = Path(setup_path)
    state = career.read_setup(setup_path)
    with setup_path.with_name('receipt.json').open('r', encoding='utf-8') as stream:
        receipt = json.load(stream)
    if receipt.get('position_scheme') != scheme:
        raise ValueError('The roster mode changed. Prepare MyPlayer with the selected mode before reviewing.')
    source = roster.SaveContainer.load(setup_path.with_name('MyCareer.zip'))
    return estimate(source.savegame, player_index=struct.unpack_from('<I', state, 28)[0],
                    expected_class=receipt.get('class_fingerprint'), scheme=scheme)

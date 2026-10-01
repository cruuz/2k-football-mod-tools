"""Per-player, per-season real measures from public nflverse data (CC-BY 4.0; FTN charting CC-BY-SA 4.0).

Every number here is a count or a sum over rows of the named file; nothing is estimated. Output:
<work>/features_<season>.json = {gsis_id: {group: {measure: value}}}. Regular season only.

Files (nflverse-data releases): play_by_play_<y>.csv.gz, pbp_participation_<y>.csv, ftn_charting_<y>.csv,
snap_counts_<y>.csv.gz, roster_weekly_<y>.csv.gz, injuries_<y>.csv.gz, stats_player_reg_<y>.csv.gz,
advstats_season_{def,pass,rec,rush}.csv.gz, ngs_{passing,receiving,rushing}.csv.gz, players.csv.gz, combine.csv.gz.
"""
import collections, json, math
from common import nfl, read_csv, work

FILES = ("play_by_play_{y}.csv.gz", "pbp_participation_{y}.csv", "ftn_charting_{y}.csv", "snap_counts_{y}.csv.gz",
         "roster_weekly_{y}.csv.gz", "injuries_{y}.csv.gz", "stats_player_reg_{y}.csv.gz",
         "advstats_season_def.csv.gz", "advstats_season_pass.csv.gz", "advstats_season_rec.csv.gz",
         "advstats_season_rush.csv.gz", "ngs_passing.csv.gz", "ngs_receiving.csv.gz", "ngs_rushing.csv.gz",
         "players.csv.gz", "combine.csv.gz")

def f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None

def b(x):
    return str(x).strip().upper() in ('1', '1.0', 'TRUE')

def id_maps():
    pfr2gsis, gsis = {}, {}
    for r in read_csv(nfl('players.csv.gz')):
        g = r['gsis_id']
        if not g:
            continue
        gsis[g] = r
        if r.get('pfr_id'):
            pfr2gsis[r['pfr_id']] = g
    return pfr2gsis, gsis

def season_features(season, pfr2gsis):
    F = collections.defaultdict(lambda: collections.defaultdict(lambda: collections.defaultdict(float)))
    def add(pid, grp, key, v=1.0):
        if pid:
            F[pid][grp][key] += v
    # ---------------------------------------------------------------- pbp (REG)
    pbp = {}
    for r in read_csv(nfl(f'play_by_play_{season}.csv.gz')):
        if r['season_type'] != 'REG':
            continue
        key = (r['game_id'], r['play_id'])
        pt = r['play_type']
        dropback = b(r['qb_dropback'])
        passer, rec, rush = r['passer_player_id'], r['receiver_player_id'], r['rusher_player_id']
        sack = b(r['sack']); att = b(r['pass_attempt']) and not sack
        scramble = b(r['qb_scramble'])
        epa = f(r['epa'])
        pbp[key] = dict(dropback=dropback, run=(pt == 'run' and not scramble), sack=sack, att=att, posteam=r['posteam'],
                        defteam=r['defteam'], passer=passer, rec=rec, epa=epa, complete=b(r['complete_pass']),
                        ybc=None, interception=b(r['interception']), yards=f(r['yards_gained']) or 0.0,
                        success=b(r['success']) if r.get('success') not in (None, '', 'NA') else None,
                        down=r['down'], ydstogo=f(r['ydstogo']))
        if dropback and passer:
            add(passer, 'qb', 'dropbacks'); add(passer, 'qb', 'epa_sum', epa or 0.0)
            if sack:
                add(passer, 'qb', 'sacks')
            if att:
                add(passer, 'qb', 'att')
                c = f(r['cpoe'])
                if c is not None:
                    add(passer, 'qb', 'cpoe_sum', c); add(passer, 'qb', 'cpoe_n')
                ay = f(r['air_yards'])
                if ay is not None:
                    add(passer, 'qb', 'air_n'); add(passer, 'qb', 'air_sum', ay)
                    if ay >= 20:
                        add(passer, 'qb', 'deep_att')
                        add(passer, 'qb', 'deep_epa', epa or 0.0)      # v2.2: what his deep balls are worth
                        if b(r['complete_pass']):
                            add(passer, 'qb', 'deep_cmp')
                if b(r['interception']):
                    add(passer, 'qb', 'int')
        if scramble and rush:
            add(rush, 'qb', 'scrambles'); add(rush, 'qb', 'scramble_yds', f(r['yards_gained']) or 0.0)
        if att and rec:
            add(rec, 'rec', 'targets')
            if b(r['complete_pass']):
                add(rec, 'rec', 'receptions'); add(rec, 'rec', 'yac', f(r['yards_after_catch']) or 0.0)
            add(rec, 'rec', 'epa_sum', epa or 0.0)
        if pt == 'run' and rush and not scramble:
            add(rush, 'rush', 'carries'); add(rush, 'rush', 'yards', f(r['yards_gained']) or 0.0)
            add(rush, 'rush', 'epa_sum', epa or 0.0)
            if pbp[key]['success']:
                add(rush, 'rush', 'success')
        for col in ('fumbled_1_player_id', 'fumbled_2_player_id'):
            if r.get(col):
                add(r[col], 'ball', 'fumbles')
        # touches (for fumble rates)
        if rush and pt == 'run':
            add(rush, 'ball', 'touches')
        if rec and b(r['complete_pass']):
            add(rec, 'ball', 'touches')
        if dropback and passer:
            add(passer, 'ball', 'qb_plays')
        # defense
        sk = r.get('sack_player_id')
        if sk:
            add(sk, 'def', 'sacks', 1.0)
        for col in ('half_sack_1_player_id', 'half_sack_2_player_id'):
            if r.get(col):
                add(r[col], 'def', 'sacks', 0.5)
        for col in ('qb_hit_1_player_id', 'qb_hit_2_player_id'):
            if r.get(col):
                add(r[col], 'def', 'qb_hits')
        for col in ('tackle_for_loss_1_player_id', 'tackle_for_loss_2_player_id'):
            if r.get(col):
                add(r[col], 'def', 'tfl')
        tacklers = [r.get(c) for c in ('solo_tackle_1_player_id', 'solo_tackle_2_player_id',
                                         'tackle_with_assist_1_player_id', 'tackle_with_assist_2_player_id',
                                         'assist_tackle_1_player_id', 'assist_tackle_2_player_id',
                                         'assist_tackle_3_player_id', 'assist_tackle_4_player_id') if r.get(c)]
        for t in set(tacklers):
            add(t, 'def', 'tackles_any')
            if pt == 'run' and not scramble:
                add(t, 'def', 'run_tackles')
                if pbp[key]['success'] is False:
                    add(t, 'def', 'run_stops')
            if att and b(r['complete_pass']):
                add(t, 'def', 'rec_tackles')
        for col in ('pass_defense_1_player_id', 'pass_defense_2_player_id'):
            if r.get(col):
                add(r[col], 'def', 'pd')
        if r.get('interception_player_id'):
            add(r['interception_player_id'], 'def', 'int')
        for col in ('forced_fumble_player_1_player_id', 'forced_fumble_player_2_player_id'):
            if r.get(col):
                add(r[col], 'def', 'ff')
        # penalties (accepted or not, the flag is the player's act)
        pp = r.get('penalty_player_id')
        if pp and b(r['penalty']):
            ptype = (r.get('penalty_type') or '').strip()
            add(pp, 'pen', 'all')
            add(pp, 'pen', ptype.replace(' ', '_').lower() or 'unknown')
        # kicking
        kk = r.get('kicker_player_id')
        if b(r['field_goal_attempt']) and kk:
            d = f(r['kick_distance']) or 0.0
            made = r['field_goal_result'] == 'made'
            F[kk]['k'].setdefault('fg_list', [])
            F[kk]['k']['fg_list'].append([d, 1 if made else 0])
        if b(r['extra_point_attempt']) and kk:
            add(kk, 'k', 'xp_att'); add(kk, 'k', 'xp_made', 1.0 if r['extra_point_result'] == 'good' else 0.0)
        if pt == 'kickoff' and kk:
            d = f(r['kick_distance'])
            if d is not None:
                add(kk, 'k', 'ko_n'); add(kk, 'k', 'ko_dist', d)
            if b(r['touchback']):
                add(kk, 'k', 'ko_tb')
        pu = r.get('punter_player_id')
        if pt == 'punt' and pu and not b(r['punt_blocked']):
            d = f(r['kick_distance']) or 0.0
            ret = f(r['return_yards']) or 0.0
            tb = b(r['touchback'])
            add(pu, 'p', 'n'); add(pu, 'p', 'gross', d); add(pu, 'p', 'net', d - ret - (20.0 if tb else 0.0))
            add(pu, 'p', 'in20', 1.0 if b(r['punt_inside_twenty']) else 0.0); add(pu, 'p', 'tb', 1.0 if tb else 0.0)
            add(pu, 'p', 'fair', 1.0 if b(r['punt_fair_catch']) else 0.0)
            yl = f(r.get('yardline_100'))
            if yl is not None:
                add(pu, 'p', 'yl_sum', yl)
    # ---------------------------------------------------------------- participation (on-field counts, pressure)
    team_pp = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in read_csv(nfl(f'pbp_participation_{season}.csv')):
        key = (r['nflverse_game_id'], r['play_id'])
        p = pbp.get(key)
        if p is None:
            continue
        off = [x for x in (r['offense_players'] or '').split(';') if x]
        dfn = [x for x in (r['defense_players'] or '').split(';') if x]
        pressure = b(r['was_pressure']) if r.get('was_pressure') not in (None, '', 'NA') else None
        ttt = f(r.get('time_to_throw'))
        if p['dropback']:
            for x in off:
                add(x, 'on', 'off_pass')
                if pressure is not None:
                    add(x, 'on', 'off_pass_pr_n'); add(x, 'on', 'off_pass_pressured', 1.0 if pressure else 0.0)
                if p['sack']:
                    add(x, 'on', 'off_pass_sacked')
            for x in dfn:
                add(x, 'on', 'def_pass')
                if pressure is not None:
                    add(x, 'on', 'def_pass_pr_n'); add(x, 'on', 'def_pass_pressure', 1.0 if pressure else 0.0)
            if pressure is not None and p['passer']:
                side = 'pr' if pressure else 'clean'
                add(p['passer'], 'qbp', side + '_db'); add(p['passer'], 'qbp', side + '_epa', p['epa'] or 0.0)
                if p['att']:
                    add(p['passer'], 'qbp', side + '_att')
                    add(p['passer'], 'qbp', side + '_cmp', 1.0 if p['complete'] else 0.0)
            if ttt is not None:
                for x in off:
                    add(x, 'on', 'off_pass_ttt', ttt); add(x, 'on', 'off_pass_ttt_n')
            if pressure is not None:
                team_pp[p['posteam']]['n'] += 1; team_pp[p['posteam']]['pr'] += 1.0 if pressure else 0.0
                if ttt is not None:
                    team_pp[p['posteam']]['ttt'] += ttt; team_pp[p['posteam']]['ttt_n'] += 1
        elif p['run']:
            for x in off:
                add(x, 'on', 'off_run'); add(x, 'on', 'off_run_epa', p['epa'] or 0.0)
                add(x, 'on', 'off_run_yds', p['yards'])
                if p['success'] is not None:
                    add(x, 'on', 'off_run_success', 1.0 if p['success'] else 0.0)
            for x in dfn:
                add(x, 'on', 'def_run'); add(x, 'on', 'def_run_epa', p['epa'] or 0.0)
                if p['success'] is not None:
                    add(x, 'on', 'def_run_success', 1.0 if p['success'] else 0.0)
        # the targeted receiver's route (participation 'route' names the target's route)
    # ---------------------------------------------------------------- FTN charting
    for r in read_csv(nfl(f'ftn_charting_{season}.csv')):
        key = (r['nflverse_game_id'], r['nflverse_play_id'])
        p = pbp.get(key)
        if p is None:
            continue
        if p['att']:
            q, rc = p['passer'], p['rec']
            add(q, 'ftn_qb', 'att')
            if b(r['is_throw_away']):
                add(q, 'ftn_qb', 'throwaway')
            else:
                add(q, 'ftn_qb', 'aimed')
                if b(r['is_catchable_ball']):
                    add(q, 'ftn_qb', 'catchable')
            if b(r['is_interception_worthy']):
                add(q, 'ftn_qb', 'int_worthy')
            if b(r['is_qb_out_of_pocket']):
                add(q, 'ftn_qb', 'out_of_pocket')
            if rc and not b(r['is_throw_away']):
                add(rc, 'ftn_rec', 'targets')
                if b(r['is_catchable_ball']):
                    add(rc, 'ftn_rec', 'catchable')
                    if p['complete']:
                        add(rc, 'ftn_rec', 'catchable_caught')
                if b(r['is_drop']):
                    add(rc, 'ftn_rec', 'drops')
                if b(r['is_contested_ball']):
                    add(rc, 'ftn_rec', 'contested')
                    if p['complete']:
                        add(rc, 'ftn_rec', 'contested_caught')
                if b(r['is_created_reception']):
                    add(rc, 'ftn_rec', 'created')
        if p['sack'] and p['passer']:
            add(p['passer'], 'ftn_qb', 'sacks')
            if b(r['is_qb_fault_sack']):
                add(p['passer'], 'ftn_qb', 'fault_sacks')
    # ---------------------------------------------------------------- snaps
    for r in read_csv(nfl(f'snap_counts_{season}.csv.gz')):
        if r['game_type'] != 'REG':
            continue
        g = pfr2gsis.get(r['pfr_player_id'])
        if not g:
            continue
        o, d, s = f(r['offense_pct']) or 0.0, f(r['defense_pct']) or 0.0, f(r['st_pct']) or 0.0
        add(g, 'snap', 'games')
        add(g, 'snap', 'off', f(r['offense_snaps']) or 0.0); add(g, 'snap', 'def', f(r['defense_snaps']) or 0.0)
        add(g, 'snap', 'st', f(r['st_snaps']) or 0.0)
        add(g, 'snap', 'share_sum', max(o, d))
        if max(o, d) >= 0.5:
            add(g, 'snap', 'games_half')
    # ---------------------------------------------------------------- weekly roster status + injury report
    for r in read_csv(nfl(f'roster_weekly_{season}.csv.gz')):
        if r.get('game_type', 'REG') != 'REG':
            continue
        g = r['gsis_id']
        st = r['status']
        if st in ('ACT', 'INA', 'RES'):
            add(g, 'avail', 'weeks')
            if st == 'RES':
                add(g, 'avail', 'reserve')
    for r in read_csv(nfl(f'injuries_{season}.csv.gz')):
        if r.get('game_type', 'REG') != 'REG':
            continue
        if (r.get('report_status') or '') == 'Out':
            add(r['gsis_id'], 'avail', 'out')
    # ---------------------------------------------------------------- stats (nflverse player stats)
    for r in read_csv(nfl(f'stats_player_reg_{season}.csv.gz')):
        g = r['player_id']
        for k in ('games', 'completions', 'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions',
                  'sacks_suffered', 'passing_epa', 'carries', 'rushing_yards', 'rushing_tds', 'rushing_epa',
                  'receptions', 'targets', 'receiving_yards', 'receiving_tds', 'receiving_epa',
                  'receiving_yards_after_catch', 'def_tackles_solo', 'def_tackle_assists', 'def_tackles_with_assist',
                  'def_tackles_for_loss', 'def_sacks', 'def_qb_hits', 'def_interceptions', 'def_pass_defended',
                  'def_fumbles_forced', 'fumbles_total', 'fumbles_lost_total', 'fg_made', 'fg_att', 'fg_long',
                  'pt_att', 'pt_yards', 'pt_net_yards', 'pt_inside_20', 'pt_touchback', 'penalties'):
            v = f(r.get(k))
            if v is not None:
                F[g]['stats'][k] = v
    return F, team_pp

def pfr_season(kind, season, pfr2gsis):
    out = {}
    for r in read_csv(nfl(f'advstats_season_{kind}.csv.gz')):
        if str(r.get('season')) != str(season):
            continue
        g = pfr2gsis.get(r.get('pfr_id') or r.get('pfr_player_id') or '')
        if not g:
            continue
        row = {k: f(v) if f(v) is not None else v for k, v in r.items()}
        tm = str(r.get('tm') or '')
        # a traded player has one row per club plus a combined "2TM"/"3TM" row: keep the combined one
        if g in out and not tm.endswith('TM') and str(out[g].get('tm', '')).endswith('TM'):
            continue
        if g in out and not tm.endswith('TM'):
            # two club rows and no combined row yet: sum the counts
            prev = out[g]
            for k, v in row.items():
                if isinstance(v, float) and isinstance(prev.get(k), float) and k not in ('season', 'age'):
                    prev[k] = prev[k] + v
            prev['tm'] = 'SUM'
            continue
        out[g] = row
    return out

def ngs_season(kind, season):
    out = {}
    for r in read_csv(nfl(f'ngs_{kind}.csv.gz')):
        if r['season'] == str(season) and r['season_type'] == 'REG' and r['week'] == '0':
            out[r['player_gsis_id']] = {k: f(v) if f(v) is not None else v for k, v in r.items()}
    return out

def main():
    pfr2gsis, gsis = id_maps()
    for season in (2024, 2025):
        F, team_pp = season_features(season, pfr2gsis)
        for kind in ('def', 'pass', 'rec', 'rush'):
            for g, row in pfr_season(kind, season, pfr2gsis).items():
                F[g]['pfr_' + kind] = row
        for kind in ('passing', 'receiving', 'rushing'):
            for g, row in ngs_season(kind, season).items():
                F[g]['ngs_' + kind] = row
        out = {g: {grp: dict(v) for grp, v in groups.items()} for g, groups in F.items()}
        json.dump({'season': season, 'players': out, 'team_pressure': {t: dict(v) for t, v in team_pp.items()}},
                  open(work(f'features_{season}.json'), 'w'))
        print(season, len(out), 'players')

if __name__ == '__main__':
    main()

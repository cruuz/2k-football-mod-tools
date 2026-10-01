"""r1 ratings model v2: real 2024-2025 measures -> NFL 2K5's own rating scale. DESIGN / PROVED OFFLINE.

For every NFL-club record of the 2026 league roster:
  1. Tier: starter or backup at his 2K5 position (2026 depth rank against the base lineup: QB 1, HB 1, FB 1, WR 3,
     TE 1, T 2, G 2, C 1, DT 2, EDGE 2, LB 2, CB 3, FS 1, SS 1, K 1, P 1).
  2. Each rating the engine uses for his position gets a real measure (components below), from the 2025 season
     (weight 1.0) and 2024 (weight 0.5), each component shrunk toward the tier's mean by its sample size.
  3. The measure's percentile inside his 2026 tier is read off the SAME tier of the retail 2004 rosters (the
     distribution 2K tuned its engine on), per rating.
  4. Physicals come from how 2K itself built them: retail speed/agility/jumping/strength are linear in the combine
     drills (fits in physfit.json, r2 up to 0.99), with 2K's own age slope past 29 (age_fit.json).
  5. Ratings the engine does not use for that position take the retail tier median (no tier-profile copying).
  v2.1 (after the native franchise-sim validation):
  6. Each component's shrinkage constant k comes from its own 2024 -> 2025 stability (stability.py), and a noisy
     component no longer gets its weight back through re-standardising: z-scores divide by the spread of the raw
     values among regulars, so a component that does not repeat year to year counts for little.
  7. QB accuracy blends CPOE with EPA per dropback (stabilised, 2024 carried in): the franchise sim leans on the
     passing composite (0.4 accuracy + 0.4 arm) for team strength, so the QB order has to be the real one.
  8. Era offsets (ERA): 2K tuned the engine on 2004 football; 2025 completes 64% (2004: 61%). Small shifts by
     position group, the same for every player of the group, so no order changes.
Inputs (all under <work>, made by build.py): features_<season>.json, ratings_v2_reference.json (reference.py),
honors.json (honors.py), predraft/*.json (predraft.py); cited 40s in nfl2k5.forty_sources.v1 files.
"""
import collections, glob, json, math, statistics
from mod_editor.core.nfl2k5_ratings_model import name_key, load_forty_sources
from common import CFG, nfl, read_csv, work

W = {2025: 1.0, 2024: 0.5}
MODEL_VERSION = 'r1-ratings-v2.4'
STARTERS = {'QB': 1, 'K': 1, 'P': 1, 'WR': 3, 'CB': 3, 'FS': 1, 'SS': 1, 'HB': 1, 'FB': 1, 'TE': 1, 'LB': 2, 'C': 1,
            'G': 2, 'T': 2, 'DT': 2, 'EDGE': 2}
GROUP = {'QB': 'QB', 'HB': 'RB', 'FB': 'RB', 'WR': 'WR', 'TE': 'TE', 'T': 'OL', 'G': 'OL', 'C': 'OL', 'DT': 'DL',
         'EDGE': 'DL', 'LB': 'LB', 'CB': 'DB', 'FS': 'DB', 'SS': 'DB', 'K': 'KP', 'P': 'KP'}
RATINGS = ('speed', 'agility', 'pass_arm_strength', 'stamina', 'kick_power', 'durability', 'strength', 'jumping',
           'coverage', 'run_route', 'tackle', 'break_tackle', 'pass_accuracy', 'pass_read_coverage', 'catch',
           'run_blocking', 'pass_blocking', 'hold_onto_ball', 'pass_rush', 'run_coverage', 'kick_accuracy',
           'kicking_style', 'leadership', 'power_run_style', 'composure', 'scramble', 'consistency',
           'aggressiveness')
PHYSICAL = ('speed', 'agility', 'jumping', 'strength')


def f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------------------------- inputs
class Data:
    def __init__(self, forty_sources=()):
        self.F = {y: json.load(open(work(f'features_{y}.json')))['players'] for y in W}
        ref = json.load(open(work('ratings_v2_reference.json')))
        self.ref = ref['tiers']
        self.phys = ref['physfit']['fits']
        self.age = ref['age']
        self.imp = ref['impute']
        self.combine = self._combine()
        self.forty_cited = self._forty_cited(forty_sources)
        self.wiki = self._wiki()
        self.honors = json.load(open(work('honors.json')))['by_gsis'] if work('honors.json').exists() else {}

    def _combine(self):
        players = {r['gsis_id']: r for r in read_csv(nfl('players.csv.gz')) if r['gsis_id']}
        pfr = {r['pfr_id']: g for g, r in players.items() if r.get('pfr_id')}
        byname = collections.defaultdict(list)
        for g, r in players.items():
            byname[(name_key(r['display_name']), str(r.get('draft_year') or ''))].append(g)
        out = {}
        for r in read_csv(nfl('combine.csv.gz')):
            g = pfr.get(r['pfr_id'] or '')
            if not g:
                hits = byname.get((name_key(r['player_name']), str(r.get('draft_year') or r.get('season') or '')), [])
                g = hits[0] if len(hits) == 1 else None
            if g:
                out[g] = {k: f(r.get(k)) for k in ('forty', 'bench', 'vertical', 'broad_jump', 'cone', 'shuttle', 'wt')}
                out[g]['source'] = f"nflverse combine.csv {r.get('season')} ({r.get('player_name')})"
        return out

    def _forty_cited(self, paths):
        out = {}
        for p in paths:
            for g, e in load_forty_sources(p).items():
                out.setdefault(g, dict(e, file=p))
        return out

    def _wiki(self):
        """Pre-draft measurables from each player's Wikipedia article ({{NFL predraft}}; the note names the event,
        NFL Combine or Pro Day, with the article's own citations). R/data/wiki_predraft*.json (wiki_predraft.py)."""
        out = {}
        # matches whose article birth year disagrees with the roster's (a father, a namesake) are rejected
        # (build.py predraft writes the list after its check; Jev reviewed the doubtful matches)
        rej_path = work('predraft', 'rejected.json')
        rejected = set(json.load(open(rej_path))) if rej_path.exists() else set()
        for p in sorted(glob.glob(str(work('predraft', 'x').parent / '*.json'))):
            if p.endswith('rejected.json'):
                continue
            for g, rec in json.load(open(p)).items():
                if g in rejected:
                    continue
                if rec.get('status') == 'ok' and rec.get('drills'):
                    note = '; '.join(v for v in (rec.get('notes') or {}).values() if v)[:160]
                    out[g] = dict(rec['drills'], source=f"Wikipedia {rec.get('url') or rec.get('evidence', '')}",
                                  note=note)
        return out

    # pooled counts over the two seasons
    def P(self, g, grp, key):
        return sum(w * f((self.F[y].get(g, {}).get(grp) or {}).get(key) or 0) for y, w in W.items())

    def seasons(self, g, grp):
        return [(y, w, self.F[y].get(g, {}).get(grp)) for y, w in W.items() if self.F[y].get(g, {}).get(grp)]

    def ngs(self, g, kind, field, vol):
        num = den = 0.0
        for y, w, row in self.seasons(g, 'ngs_' + kind):
            v, n = f(row.get(field)), f(row.get(vol)) or 0.0
            if v is not None and n > 0:
                num += w * n * v; den += w * n
        return (num / den, den) if den else (None, 0.0)

    def ngs_max(self, g, kind, field):
        vals = [f(row.get(field)) for y, w, row in self.seasons(g, 'ngs_' + kind) if f(row.get(field)) is not None]
        return max(vals) if vals else None


def rate(num, den):
    return (num / den) if den else None


def passer_rating(cmp_, att, yds, td, int_):
    if not att:
        return None
    a = max(0, min(2.375, (cmp_ / att - 0.3) * 5)); b = max(0, min(2.375, (yds / att - 3) * 0.25))
    c = max(0, min(2.375, td / att * 20)); d = max(0, min(2.375, 2.375 - int_ / att * 25))
    return (a + b + c + d) / 6 * 100


# ----------------------------------------------------------------------------------------------- measures
def components(D, g, pos):
    """{rating: [(component, value (higher=better), volume, k, weight)]} for the ratings measured at pos."""
    P = D.P
    out = collections.defaultdict(list)
    def add(rating, name, value, vol, k, weight=1.0):
        if value is not None and vol and vol > 0:
            out[rating].append((name, value, vol, k, weight))
    att = P(g, 'qb', 'att'); db = P(g, 'qb', 'dropbacks')
    touches_ball = P(g, 'ball', 'touches') + P(g, 'ball', 'qb_plays')
    fum = P(g, 'ball', 'fumbles')
    def pfr(kind, key):
        return sum(w * (f(row.get(key)) or 0.0) for y, w, row in D.seasons(g, 'pfr_' + kind))
    if pos == 'QB':
        add('pass_accuracy', 'cpoe', rate(P(g, 'qb', 'cpoe_sum'), P(g, 'qb', 'cpoe_n')), P(g, 'qb', 'cpoe_n'), 150, 0.35)
        add('pass_accuracy', 'epa_per_dropback', rate(P(g, 'qb', 'epa_sum'), db), db, 150, 0.35)
        add('pass_accuracy', 'ftn_catchable_rate', rate(P(g, 'ftn_qb', 'catchable'), P(g, 'ftn_qb', 'aimed')),
            P(g, 'ftn_qb', 'aimed'), 150, 0.15)
        pa = pfr('pass', 'pass_attempts')
        add('pass_accuracy', 'pfr_bad_throw_rate_inv', -rate(pfr('pass', 'bad_throws'), pa) if pa else None, pa, 150, 0.15)
        mx = D.ngs_max(g, 'passing', 'max_air_distance')
        add('pass_arm_strength', 'ngs_max_air_distance', mx, att, 100, 0.4)
        ad, n_ad = D.ngs(g, 'passing', 'avg_air_distance', 'attempts')
        add('pass_arm_strength', 'ngs_avg_air_distance', ad, n_ad, 150, 0.1)
        add('pass_arm_strength', 'deep_attempt_rate', rate(P(g, 'qb', 'deep_att'), P(g, 'qb', 'air_n')),
            P(g, 'qb', 'air_n'), 150, 0.2)
        # v2.2: what the arm is worth, EPA per throw of 20+ air yards (the franchise sim's passing composite is 40% arm)
        add('pass_arm_strength', 'deep_epa_per_deep_attempt', rate(P(g, 'qb', 'deep_epa'), P(g, 'qb', 'deep_att')),
            P(g, 'qb', 'deep_att'), 60, 0.3)
        add('pass_read_coverage', 'ftn_int_worthy_rate_inv', -rate(P(g, 'ftn_qb', 'int_worthy'), P(g, 'ftn_qb', 'att'))
            if P(g, 'ftn_qb', 'att') else None, P(g, 'ftn_qb', 'att'), 150, 0.45)
        add('pass_read_coverage', 'ftn_fault_sack_rate_inv', -rate(P(g, 'ftn_qb', 'fault_sacks'), db) if db else None,
            db, 150, 0.2)
        add('pass_read_coverage', 'epa_per_dropback', rate(P(g, 'qb', 'epa_sum'), db), db, 150, 0.35)
        add('composure', 'epa_per_pressured_dropback', rate(P(g, 'qbp', 'pr_epa'), P(g, 'qbp', 'pr_db')),
            P(g, 'qbp', 'pr_db'), 60, 0.7)
        add('composure', 'pressured_cmp_rate', rate(P(g, 'qbp', 'pr_cmp'), P(g, 'qbp', 'pr_att')),
            P(g, 'qbp', 'pr_att'), 50, 0.3)
        add('hold_onto_ball', 'fumbles_per_play_inv', -rate(fum, touches_ball) if touches_ball else None,
            touches_ball, 300)
    if pos in ('HB', 'FB'):
        ra, rc = pfr('rush', 'att'), pfr('rec', 'rec')
        add('break_tackle', 'pfr_broken_tackles_per_touch', rate(pfr('rush', 'brk_tkl') + pfr('rec', 'brk_tkl'), ra + rc),
            ra + rc, 80, 0.4)
        add('break_tackle', 'pfr_yards_after_contact_per_att', rate(pfr('rush', 'yac'), ra), ra, 80, 0.3)
        ry, n_ry = D.ngs(g, 'rushing', 'rush_yards_over_expected_per_att', 'rush_attempts')
        add('break_tackle', 'ngs_ryoe_per_att', ry, n_ry, 80, 0.3)
        add('hold_onto_ball', 'fumbles_per_touch_inv', -rate(fum, touches_ball) if touches_ball else None, touches_ball, 200)
        add('catch', 'ftn_catchable_caught_rate', rate(P(g, 'ftn_rec', 'catchable_caught'), P(g, 'ftn_rec', 'catchable')),
            P(g, 'ftn_rec', 'catchable'), 25, 0.7)
        tg = pfr('rec', 'tgt')
        add('catch', 'pfr_drop_rate_inv', -rate(pfr('rec', 'drop'), tg) if tg else None, tg, 40, 0.3)
        add('run_route', 'targets_per_pass_snap', rate(P(g, 'rec', 'targets'), P(g, 'on', 'off_pass')),
            P(g, 'on', 'off_pass'), 100)
        if pos == 'FB':
            add('run_blocking', 'team_run_success_on_field', rate(P(g, 'on', 'off_run_success'), P(g, 'on', 'off_run')),
                P(g, 'on', 'off_run'), 150)
    if pos in ('WR', 'TE'):
        add('catch', 'ftn_catchable_caught_rate', rate(P(g, 'ftn_rec', 'catchable_caught'), P(g, 'ftn_rec', 'catchable')),
            P(g, 'ftn_rec', 'catchable'), 40, 0.6)
        add('catch', 'ftn_contested_caught_rate', rate(P(g, 'ftn_rec', 'contested_caught'), P(g, 'ftn_rec', 'contested')),
            P(g, 'ftn_rec', 'contested'), 15, 0.25)
        tg = pfr('rec', 'tgt')
        add('catch', 'pfr_drop_rate_inv', -rate(pfr('rec', 'drop'), tg) if tg else None, tg, 60, 0.15)
        # v2.2: route running leans on earning targets (r 0.69 season to season); separation over expected 0.25
        add('run_route', 'targets_per_pass_snap', rate(P(g, 'rec', 'targets'), P(g, 'on', 'off_pass')),
            P(g, 'on', 'off_pass'), 150, 0.75)
        sep = D.sep_oe.get(g) if hasattr(D, 'sep_oe') else None
        if sep:
            add('run_route', 'ngs_separation_over_expected', sep[0], sep[1], 40, 0.25)
        rc = pfr('rec', 'rec')
        add('break_tackle', 'pfr_broken_tackles_per_rec', rate(pfr('rec', 'brk_tkl'), rc), rc, 40, 0.5)
        ya, n_ya = D.ngs(g, 'receiving', 'avg_yac_above_expectation', 'receptions')
        add('break_tackle', 'ngs_yac_above_expectation', ya, n_ya, 40, 0.5)
        add('hold_onto_ball', 'fumbles_per_touch_inv', -rate(fum, touches_ball) if touches_ball else None, touches_ball, 100)
        if pos == 'TE':
            run_share = rate(P(g, 'on', 'off_run'), P(g, 'on', 'off_run') + P(g, 'on', 'off_pass'))
            vol = P(g, 'on', 'off_run') + P(g, 'on', 'off_pass')
            add('run_blocking', 'team_run_success_on_field', rate(P(g, 'on', 'off_run_success'), P(g, 'on', 'off_run')),
                P(g, 'on', 'off_run'), 200, 0.5)
            add('run_blocking', 'run_snap_share', run_share, vol, 200, 0.5)
            # no public per-TE pass-protection data: the in-line (run-snap-heavy) role stands in (INFERRED proxy)
            add('pass_blocking', 'run_snap_share', run_share, vol, 200, 1.0)
    if pos in ('T', 'G', 'C'):
        n_pp = P(g, 'on', 'off_pass_pr_n')
        pr = rate(P(g, 'on', 'off_pass_pressured'), n_pp)
        ttt = rate(P(g, 'on', 'off_pass_ttt'), P(g, 'on', 'off_pass_ttt_n'))
        if pr is not None and ttt is not None:
            exp_pr = D.pressure_fit[0] + D.pressure_fit[1] * ttt
            add('pass_blocking', 'team_pressure_over_expected_inv', exp_pr - pr, n_pp, 250, 0.30)
        sk = rate(P(g, 'on', 'off_pass_sacked'), P(g, 'on', 'off_pass'))
        add('pass_blocking', 'team_sack_rate_on_field_inv', -sk if sk is not None else None, P(g, 'on', 'off_pass'), 250, 0.10)
        snaps = P(g, 'snap', 'off')
        hold = P(g, 'pen', 'offensive_holding'); fs = P(g, 'pen', 'false_start')
        add('pass_blocking', 'holding_false_start_per_snap_inv', -(hold + fs) / snaps if snaps else None, snaps, 400, 0.30)
        # how much of his club's football he played over the two seasons (teams keep their best linemen on the field)
        role = P(g, 'snap', 'share_sum') / (17.0 * sum(W.values()))
        add('pass_blocking', 'season_snap_share', role, P(g, 'snap', 'games') or 1.0, 8, 0.30)
        add('run_blocking', 'team_run_success_on_field', rate(P(g, 'on', 'off_run_success'), P(g, 'on', 'off_run')),
            P(g, 'on', 'off_run'), 200, 0.30)
        add('run_blocking', 'team_run_epa_on_field', rate(P(g, 'on', 'off_run_epa'), P(g, 'on', 'off_run')),
            P(g, 'on', 'off_run'), 200, 0.15)
        add('run_blocking', 'holding_per_snap_inv', -hold / snaps if snaps else None, snaps, 400, 0.25)
        add('run_blocking', 'season_snap_share', role, P(g, 'snap', 'games') or 1.0, 8, 0.30)
    if pos in ('DT', 'EDGE', 'LB', 'CB', 'FS', 'SS'):
        dp, dr = P(g, 'on', 'def_pass'), P(g, 'on', 'def_run')
        prss = pfr('def', 'prss')
        k_pr = 200 if pos in ('DT', 'EDGE') else 300
        add('pass_rush', 'pfr_pressures_per_pass_snap', rate(prss, dp), dp, k_pr, 0.75)
        add('pass_rush', 'sacks_per_pass_snap', rate(P(g, 'def', 'sacks'), dp), dp, k_pr * 1.5, 0.25)
        add('run_coverage', 'run_stops_per_run_snap', rate(P(g, 'def', 'run_stops'), dr), dr, 150, 0.7)
        add('run_coverage', 'tfl_per_run_snap', rate(P(g, 'def', 'tfl'), dr), dr, 250, 0.3)
        comb, miss = pfr('def', 'comb'), pfr('def', 'm_tkl')
        add('tackle', 'pfr_missed_tackle_rate_inv', -rate(miss, comb + miss) if comb + miss else None, comb + miss,
            30 if pos != 'LB' else 40, 0.8)
        add('tackle', 'tackles_per_snap', rate(P(g, 'def', 'tackles_any'), P(g, 'snap', 'def')), P(g, 'snap', 'def'), 400, 0.2)
        if pos in ('LB', 'CB', 'FS', 'SS'):
            tgt, cmp_, yds, td, int_ = (pfr('def', k) for k in ('tgt', 'cmp', 'yds', 'td', 'int'))
            add('coverage', 'pfr_yards_allowed_per_pass_snap_inv', -yds / dp if dp else None, dp, 300, 0.55)
            pr = passer_rating(cmp_, tgt, yds, td, int_)
            add('coverage', 'pfr_passer_rating_allowed_inv', -pr if pr is not None else None, tgt, 40, 0.3)
            add('coverage', 'pfr_targets_per_pass_snap_inv', -tgt / dp if dp else None, dp, 300, 0.15)
            ints, pds = P(g, 'def', 'int'), P(g, 'def', 'pd')
            add('catch', 'int_share_of_balls_defended', rate(ints, ints + pds), ints + pds, 20, 0.7)
            add('catch', 'int_per_target', rate(pfr('def', 'int'), tgt), tgt, 60, 0.3)
    if pos == 'K':
        fg = []
        for y, w in W.items():
            for d, made in (D.F[y].get(g, {}).get('k', {}) or {}).get('fg_list', []) or []:
                fg.append((w, d, made))
        if fg:
            n = sum(w for w, _, _ in fg)
            oe = sum(w * (made - D.fg_prob(d)) for w, d, made in fg) / n
            add('kick_accuracy', 'fg_made_over_expected', oe, n, 20, 0.8)
            made_d = [d for w, d, m in fg if m]
            add('kick_power', 'long_fg_made', max(made_d) if made_d else None, n, 10, 0.4)
            add('kick_power', 'fg_att_50_plus_rate', rate(sum(w for w, d, m in fg if d >= 50), n), n, 20, 0.3)
        add('kick_accuracy', 'xp_rate', rate(P(g, 'k', 'xp_made'), P(g, 'k', 'xp_att')), P(g, 'k', 'xp_att'), 40, 0.2)
        add('kick_power', 'kickoff_avg_distance', rate(P(g, 'k', 'ko_dist'), P(g, 'k', 'ko_n')), P(g, 'k', 'ko_n'), 30, 0.3)
    if pos == 'P':
        n = P(g, 'p', 'n')
        add('kick_power', 'gross_avg', rate(P(g, 'p', 'gross'), n), n, 30)
        add('kick_accuracy', 'inside_20_rate', rate(P(g, 'p', 'in20'), n), n, 30, 0.5)
        add('kick_accuracy', 'touchback_rate_inv', -rate(P(g, 'p', 'tb'), n) if n else None, n, 30, 0.2)
        add('kick_accuracy', 'net_minus_gross', rate(P(g, 'p', 'net') - P(g, 'p', 'gross'), n), n, 30, 0.3)
    # every position
    games = P(g, 'snap', 'games')
    add('stamina', 'snap_share_when_playing', rate(P(g, 'snap', 'share_sum'), games), games, 4)
    wk = P(g, 'avail', 'weeks')
    add('durability', 'weeks_available_share', 1 - rate(P(g, 'avail', 'reserve') + P(g, 'avail', 'out'), wk) if wk else None,
        wk, 8)
    return out


# which ratings each position's engine role uses (measured or physical); everything else = retail tier median
MEASURED = {
    'QB': ('pass_accuracy', 'pass_arm_strength', 'pass_read_coverage', 'composure', 'hold_onto_ball'),
    'HB': ('break_tackle', 'hold_onto_ball', 'catch', 'run_route'),
    'FB': ('break_tackle', 'hold_onto_ball', 'catch', 'run_route', 'run_blocking'),
    'WR': ('catch', 'run_route', 'break_tackle', 'hold_onto_ball'),
    'TE': ('catch', 'run_route', 'break_tackle', 'hold_onto_ball', 'run_blocking', 'pass_blocking'),
    'T': ('pass_blocking', 'run_blocking'), 'G': ('pass_blocking', 'run_blocking'), 'C': ('pass_blocking', 'run_blocking'),
    'DT': ('pass_rush', 'run_coverage', 'tackle'), 'EDGE': ('pass_rush', 'run_coverage', 'tackle'),
    'LB': ('tackle', 'run_coverage', 'coverage', 'pass_rush', 'catch'),
    'CB': ('coverage', 'catch', 'tackle', 'run_coverage', 'pass_rush'),
    'FS': ('coverage', 'catch', 'tackle', 'run_coverage', 'pass_rush'),
    'SS': ('coverage', 'catch', 'tackle', 'run_coverage', 'pass_rush'),
    'K': ('kick_power', 'kick_accuracy'), 'P': ('kick_power', 'kick_accuracy'),
}
ALL_MEASURED = ('stamina', 'durability')
MENTAL = ('leadership', 'composure', 'consistency', 'aggressiveness')


_STABILITY = None


def stable_k(group, component, k_now):
    """k for a component from its 2024 -> 2025 stability (work/stability.json, stability.py): k = n (1 - r) / r,
    bounded to [0.5, 12] x the v2.0 constant; a component that does not repeat (r <= 0.02) takes 12 x; one measured
    over both seasons at once (r = 1, NGS separation over expected) or with too few players keeps its constant."""
    global _STABILITY
    if _STABILITY is None:
        path = work('stability.json')
        _STABILITY = {}
        if path.exists():
            for row in json.load(open(path)):
                _STABILITY.setdefault((row['group'], row['component']), row)
    row = _STABILITY.get((group, component))
    if not row or row.get('note') or row.get('r_2024_2025') is None:
        return k_now
    r = row['r_2024_2025']
    if r >= 0.999:
        return k_now
    if r <= 0.02 or not row.get('k_data'):
        return 12.0 * k_now
    return min(12.0 * k_now, max(0.5 * k_now, row['k_data']))


# 2K tuned the engine on 2004 football. The franchise sim (native, 3 seasons) completes 60.7% with v2.0 and 60.4%
# with the retail rosters; 2025 completed 64.3%. Trials (4 weeks each, R/sim/trials): defenders' coverage -6 = +2.9
# pp, receivers' catch +6 = +2.0 pp, QB accuracy +6 = +1.6 pp; OL run block +6 moved nothing. v2.2 moves the weight
# to QB accuracy (the lever with no YPA cost) and keeps catch at +1. Run game (v2.3, 8-week trials on v2.2): the sim
# ran 3.86 YPC (2025: 4.36); defenders' tackle -6 = 3.97, HB break tackle +8 = 3.97, DL/LB run coverage -8 = 3.92,
# all three together 4.36. Per position group (DESIGN), applied after the percentile is read off the retail tier.
ERA = {'QB': {'pass_accuracy': 5}, 'WR': {'catch': 1}, 'TE': {'catch': 1}, 'HB': {'catch': 1, 'break_tackle': 6},
       'FB': {'catch': 1},
       'CB': {'coverage': -3, 'tackle': -5}, 'FS': {'coverage': -3, 'tackle': -5}, 'SS': {'coverage': -3, 'tackle': -5},
       'LB': {'coverage': -3, 'tackle': -5, 'run_coverage': -6},
       'DT': {'tackle': -5, 'run_coverage': -6}, 'EDGE': {'tackle': -5, 'run_coverage': -6}}


# The engine's catch curve (0x50AC84, PROVED OFFLINE): catch rating -> probability on a clean ball.
CATCH_CURVE = ((0, 0.10), (30, 0.40), (50, 0.80), (65, 1.00), (80, 1.10), (99, 1.50))
CATCH_FLOOR_MIN_BALLS = 20


def catch_for_probability(p):
    """The lowest catch rating whose clean-ball probability on the engine's curve reaches p."""
    for (c0, p0), (c1, p1) in zip(CATCH_CURVE, CATCH_CURVE[1:]):
        if p <= p1:
            return c0 + (c1 - c0) * max(0.0, p - p0) / (p1 - p0)
    return CATCH_CURVE[-1][0]


def quantile(sorted_vals, q):
    if not sorted_vals:
        return None
    q = min(1.0, max(0.0, q))
    at = q * (len(sorted_vals) - 1)
    lo = int(math.floor(at)); hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (at - lo)


def clamp(v, lo=0, hi=99):
    return int(max(lo, min(hi, round(v))))


class Model:
    def __init__(self, D, players):
        """players: list of dicts with gsis, pos, tier, team, weight, height, birth_date, years, draft_number,
        record index. Computes every rating for every player."""
        self.D, self.players = D, players
        self._prepare()

    # league fits used by some measures (all from the same public data)
    def _prepare(self):
        D = self.D
        # pressure rate vs time to throw, across team-seasons (participation) -> expected pressure for a lineman
        xs, ys = [], []
        for y in W:
            tp = json.load(open(work(f'features_{y}.json')))['team_pressure']
            for t, v in tp.items():
                if v.get('ttt_n') and v.get('n'):
                    xs.append(v['ttt'] / v['ttt_n']); ys.append(v['pr'] / v['n'])
        mx, my = statistics.mean(xs), statistics.mean(ys)
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        D.pressure_fit = (my - b * mx, b, len(xs))
        # field goal make probability by distance (logistic, both seasons, all kickers)
        pts = []
        for y in W:
            for g, p in D.F[y].items():
                for d, made in (p.get('k') or {}).get('fg_list', []) or []:
                    pts.append((d, made))
        a, c = 6.0, -0.1
        for _ in range(300):      # Newton-free gradient steps on the log-likelihood, deterministic
            ga = gc = 0.0
            for d, m in pts:
                p = 1 / (1 + math.exp(-(a + c * d)))
                ga += (m - p); gc += (m - p) * d
            a += 0.5 * ga / len(pts); c += 0.5 * gc / len(pts) / 1600
        D.fg_fit = (a, c, len(pts))
        D.fg_prob = lambda d: 1 / (1 + math.exp(-(D.fg_fit[0] + D.fg_fit[1] * d)))
        # NGS separation over expected (receivers): avg_separation ~ avg_cushion + avg_intended_air_yards
        rows = []
        for y, w in W.items():
            for g, p in D.F[y].items():
                r = p.get('ngs_receiving')
                if r and f(r.get('avg_separation')) is not None and f(r.get('avg_cushion')) is not None:
                    rows.append((g, w, f(r['avg_separation']), f(r['avg_cushion']), f(r['avg_intended_air_yards']) or 0.0,
                                 f(r.get('targets')) or 0.0))
        from reference import ols
        beta, sd, r2 = ols([[1.0, c_, a_] for _, _, _, c_, a_, _ in rows], [s for _, _, s, _, _, _ in rows])
        D.sep_fit = (beta, r2, len(rows))
        acc = collections.defaultdict(lambda: [0.0, 0.0])
        for g, w, s, c_, a_, n in rows:
            res = s - (beta[0] + beta[1] * c_ + beta[2] * a_)
            acc[g][0] += w * n * res; acc[g][1] += w * n
        D.sep_oe = {g: (v[0] / v[1], v[1]) for g, v in acc.items() if v[1]}

    # ------------------------------------------------------------------------------------------ physicals
    def physical(self, p):
        D = self.D
        grp = GROUP[p['pos']]
        cmb = dict(D.combine.get(p['gsis'], {}))
        basis = {}
        wt = p['weight']
        drills = {k: cmb.get(k) for k in ('forty', 'bench', 'vertical', 'broad_jump', 'cone', 'shuttle')}
        src = {k: ('combine' if v is not None else None) for k, v in drills.items()}
        if drills['forty'] is None and p['gsis'] in D.forty_cited:
            c = D.forty_cited[p['gsis']]
            drills['forty'] = c['forty']; src['forty'] = f"cited {c['kind']}: {c['source_url']}"
        wk = D.wiki.get(p['gsis'], {})
        for k in drills:
            if drills[k] is None and wk.get(k) is not None:
                drills[k] = wk[k]; src[k] = f"{wk['source']} ({wk.get('note') or 'event not named'})"
        # impute missing drills from the combine population (per group regressions on forty and weight)
        for k in ('forty', 'shuttle', 'vertical', 'bench', 'broad_jump'):
            if drills[k] is None:
                fit = D.imp.get(grp, {}).get(k)
                if fit:
                    feats = fit['features']
                    vals = [wt if x == 'wt' else drills.get(x) for x in feats]
                    if all(v is not None for v in vals):
                        drills[k] = fit['beta'][0] + sum(b * v for b, v in zip(fit['beta'][1:], vals))
                        src[k] = 'imputed from ' + '+'.join(feats) + ' (combine population)'
        age = p.get('age') or 26
        out = {}
        if grp == 'KP':
            return out, {}          # kickers and punters keep the retail tier medians (no drill fits for K/P)
        for rating, feats_pref in (('speed', [['forty']]), ('agility', [['shuttle', 'forty'], ['forty']]),
                                   ('jumping', [['vertical'], ['broad']]), ('strength', [['bench', 'wt'], ['bench'], ['wt']])):
            fits = D.phys.get(rating, {}).get(grp) or D.phys.get(rating, {}).get('LB')
            val = None
            for feats in feats_pref:
                fit = next((x for x in (fits or []) if x['features'] == feats), None)
                if fit is None:
                    continue
                vals = [wt if x == 'wt' else (drills.get('broad_jump') if x == 'broad' else drills.get(x)) for x in feats]
                if any(v is None for v in vals):
                    continue
                val = fit['beta'][0] + sum(b * v for b, v in zip(fit['beta'][1:], vals))
                basis[rating] = {'fit': '+'.join(feats), 'group': grp, 'r2': fit['r2'],
                                 'drills': {x: (round(v, 2), src.get('broad_jump' if x == 'broad' else x, 'record weight'))
                                            for x, v in zip(feats, vals)}}
                break
            if val is None:
                continue
            slope = D.age[rating]['slope_per_year_past_29']
            if age > 29:
                val += slope * (age - 29)
                basis[rating]['age_adjust'] = round(slope * (age - 29), 2)
            out[rating] = clamp(val, 1, 99)
        return out, basis


def build_players(D, rows, doc, by):
    """The 1,696 records as model players."""
    from common import ONE_POOL, team_of
    players = []
    for r in rows:
        pl = by[(r['pool'], int(r['index']))]
        v = pl.record.values
        pos = ONE_POOL[v['position']]
        bd = r.get('source_birth_date') or ''
        try:
            y, m, d = (int(x) for x in bd[:10].split('-'))
            age = 2026 - y - (1 if (m, d) > (9, 1) else 0)
        except ValueError:
            age = None
        players.append(dict(gsis=r['gsis_id'], name=r['source_name'], pos=pos, index=int(r['index']), pool=r['pool'],
                            team=team_of(r, doc, pl), depth=v['depth_rank'],
                            tier='starter' if v['depth_rank'] < STARTERS.get(pos, 1) else 'backup',
                            weight=pl.record.get('weight'), height=v['height'], age=age,
                            years=int(f(r.get('source_years_exp')) or 0), current=pl.record.ratings()))
    return players


# ----------------------------------------------------------------------------------------------- assembly
HONOR_FLOOR = {('AP1', 2025): 0.97, ('AP2', 2025): 0.94, ('PB', 2025): 0.90,
               ('AP1', 2024): 0.93, ('AP2', 2024): 0.90, ('PB', 2024): 0.85}
# an honour lifts the skill ratings only at a matching position (a punt returner's All-Pro says nothing about his
# catching; the Pro Bowl's "outside linebacker" is usually an edge rusher)
HONOR_POS = {'QB': ('QB',), 'HB': ('HB',), 'FB': ('FB',), 'WR': ('WR',), 'TE': ('TE',), 'T': ('T', 'G'), 'G': ('G', 'T', 'C'),
             'C': ('C', 'G'), 'EDGE': ('EDGE', 'DT'), 'DT': ('DT', 'EDGE'), 'LB': ('LB', 'EDGE'), 'CB': ('CB',),
             'S': ('FS', 'SS'), 'K': ('K',), 'P': ('P',)}
Q_CLIP = (0.03, 0.985)   # keep retail's outlier tails (1s and 99s it gave special cases) out of reach of noise
ROOKIE_PRIOR = ((10, 0.75), (32, 0.65), (64, 0.55), (100, 0.45), (150, 0.38), (262, 0.30))


def pct_ranks(vals):
    """Mid-rank percentiles (ties share the mean rank) for a list of numbers."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        q = ((i + j) / 2 + 0.5) / len(vals)
        for k in range(i, j + 1):
            out[order[k]] = q
        i = j + 1
    return out


def rate_all(D, players, draft):
    """Fill p['ratings'] and p['basis'] for every player. draft: {gsis: pick number or None}."""
    M = Model(D, players)
    D._players = players
    by_pos = collections.defaultdict(list)
    for p in players:
        p['comp'] = components(D, p['gsis'], p['pos'])
        by_pos[p['pos']].append(p)
    for pos, lst in by_pos.items():
        pool = pos
        rated = set(MEASURED.get(pos, ())) | set(ALL_MEASURED)
        # --- measured ratings: shrink, standardise over the position, combine, percentile inside the tier
        for rating in rated:
            names = sorted({c[0] for p in lst for c in p['comp'].get(rating, [])})
            if not names:
                continue
            spec = {}
            for c in names:
                entries = [(p, x) for p in lst for x in p['comp'].get(rating, []) if x[0] == c]
                k_now = entries[0][1][3]
                tier_mu = {}
                for tier in ('starter', 'backup'):
                    te = [(x[1], x[2]) for p, x in entries if p['tier'] == tier]
                    if not te:
                        te = [(x[1], x[2]) for p, x in entries]
                    # v2.1: the prior is the tier's typical regular (plain mean over players with a real sample), not
                    # the volume-weighted mean, which the best (most-played) players pull up: a starter with 60
                    # attempts no longer lands in the tier's top fifth by default
                    reg = [v for v, n in te if n >= k_now]
                    tier_mu[tier] = statistics.mean(reg) if len(reg) >= 5 else sum(v * n for v, n in te) / sum(n for v, n in te)
                k = stable_k(GROUP[pos], c, k_now)
                w = entries[0][1][4]
                regular = [x[1] for p, x in entries if x[2] >= k_now] or [x[1] for p, x in entries]
                spec[c] = dict(tier_mu=tier_mu, k=k, k_v20=k_now, w=w,
                               raw_sd=statistics.pstdev(regular) if len(regular) > 1 else 0.0)
            shrunk = {}
            for p in lst:
                have = {x[0]: x for x in p['comp'].get(rating, [])}
                shrunk[id(p)] = {}
                for c, s in spec.items():
                    mu = s['tier_mu'][p['tier']]
                    n = have[c][2] if c in have else 0.0
                    if p['tier'] == 'starter' and n < s['k_v20']:
                        # v2.1: a starter without a regular's sample (a new starter, a former backup) is not assumed
                        # to be a typical established starter: his prior slides toward the backups' typical regular
                        # until his volume reaches a regular's (Malik Willis, 62 attempts, was rated like a top-12 QB)
                        mu = mu * (n / s['k_v20']) + s['tier_mu']['backup'] * (1 - n / s['k_v20'])
                    if c in have:
                        v = have[c][1]
                        shrunk[id(p)][c] = ((v * n + mu * s['k']) / (n + s['k']), n)
                    else:
                        shrunk[id(p)][c] = (mu, 0.0)
            zs = {}
            for c, s in spec.items():
                vals = [shrunk[id(p)][c][0] for p in lst]
                # centre on the shrunk values, scale by the raw spread among regulars: the shrinkage now also says
                # how much a component can move a player (v2.0 divided by the shrunk spread and undid it)
                mu, sd = statistics.mean(vals), s['raw_sd'] or statistics.pstdev(vals) or 1.0
                zs[c] = (mu, sd)
            for p in lst:
                tot = sum(s['w'] for s in spec.values())
                score = sum(spec[c]['w'] * (shrunk[id(p)][c][0] - zs[c][0]) / zs[c][1] for c in spec) / tot
                vol = sum(shrunk[id(p)][c][1] for c in spec)
                p.setdefault('score', {})[rating] = score
                p.setdefault('vol', {})[rating] = vol
                p.setdefault('comp_used', {})[rating] = {c: [round(shrunk[id(p)][c][0], 4), round(shrunk[id(p)][c][1], 1)]
                                                         for c in spec}
            for tier in ('starter', 'backup'):
                grp = [p for p in lst if p['tier'] == tier]
                if not grp:
                    continue
                qs = pct_ranks([p['score'][rating] for p in grp])
                for p, q in zip(grp, qs):
                    p.setdefault('q', {})[rating] = q
        # --- rookies without NFL data: a draft-position prior; honours floors
        for p in lst:
            for rating in list((p.get('q') or {}).keys()):
                note = None
                if p['years'] == 0 and p['vol'].get(rating, 0) == 0 and rating in MEASURED.get(pos, ()):
                    pick = draft.get(p['gsis'])
                    prior = next((q for lim, q in ROOKIE_PRIOR if pick and pick <= lim), 0.2)
                    p['q'][rating] = prior
                    note = f'rookie prior (pick {pick})'
                if rating in MEASURED.get(pos, ()):
                    floor = 0.0
                    for h in D.honors.get(p['gsis'], []):
                        if pos in HONOR_POS.get(h.get('position'), ()):
                            floor = max(floor, HONOR_FLOOR.get((h['level'], h['season']), 0.0))
                    if floor > p['q'][rating]:
                        p['q'][rating] = floor
                        note = (note + '; ' if note else '') + f'honours floor {floor}'
                if note:
                    p.setdefault('notes', {})[rating] = note
        # --- experience and quality percentiles (mental ratings follow 2K's own design: composure r=0.74 with
        #     years pro, leadership r=0.45 years / 0.67 OVR, consistency r=0.51 / 0.61 in the retail rosters)
        for tier in ('starter', 'backup'):
            grp = [p for p in lst if p['tier'] == tier]
            if not grp:
                continue
            ex = pct_ranks([p['years'] for p in grp])
            for p, q in zip(grp, ex):
                p['q_exp'] = q
                skill = [p['q'][r] for r in MEASURED.get(pos, ()) if r in p.get('q', {})]
                p['q_quality'] = statistics.mean(skill) if skill else 0.5
            # aggression: defensive playmaking per snap; HB: yards after contact; others: tier median
            if pos in ('DT', 'EDGE', 'LB', 'CB', 'FS', 'SS', 'HB'):
                vals = []
                for p in grp:
                    g = p['gsis']
                    if pos == 'HB':
                        att = sum(w * (f(r.get('att')) or 0) for y, w, r in D.seasons(g, 'pfr_rush'))
                        yac = sum(w * (f(r.get('yac')) or 0) for y, w, r in D.seasons(g, 'pfr_rush'))
                        vals.append((yac + 3.0 * 30) / (att + 30))
                    else:
                        snaps = D.P(g, 'snap', 'def')
                        plays = (D.P(g, 'def', 'sacks') + D.P(g, 'def', 'tfl') + D.P(g, 'def', 'ff') + D.P(g, 'def', 'int')
                                 + D.P(g, 'def', 'pd') + 0.5 * sum(w * (f(r.get('prss')) or 0) for y, w, r in D.seasons(g, 'pfr_def')))
                        vals.append((plays + 0.02 * 300) / (snaps + 300))
                for p, q in zip(grp, pct_ranks(vals)):
                    p['q_aggr'] = q
        for p in lst:
            ref = D.ref[pool][p['tier']]['ratings'] if D.ref[pool][p['tier']]['n'] else D.ref[pool]['all']['ratings']
            med = {r: quantile(ref[r], 0.5) for r in RATINGS}
            out, basis = {}, {}
            for r in RATINGS:
                if r in (p.get('q') or {}):
                    q = min(Q_CLIP[1], max(Q_CLIP[0], p['q'][r]))
                    if r == 'composure' and pos == 'QB':
                        q = 0.6 * q + 0.4 * p['q_exp']
                    era = ERA.get(pos, {}).get(r, 0)
                    out[r] = clamp(quantile(ref[r], q) + era)
                    basis[r] = {'q': round(q, 3), 'components': p['comp_used'].get(r), 'note': (p.get('notes') or {}).get(r)}
                    if era:
                        basis[r]['era_offset'] = era
                else:
                    out[r] = clamp(med[r]); basis[r] = {'q': 0.5, 'rule': 'retail tier median (not used by this position)'}
            # mental
            for r, q, rule in (('composure', p['q_exp'], 'experience percentile in tier (2K design, r=0.74)'),
                               ('leadership', 0.5 * p['q_exp'] + 0.5 * p['q_quality'], '0.5 experience + 0.5 measured quality'),
                               ('consistency', 0.5 * p['q_exp'] + 0.5 * p['q_quality'], '0.5 experience + 0.5 measured quality')):
                if r == 'composure' and pos == 'QB':
                    continue
                out[r] = clamp(quantile(ref[r], q)); basis[r] = {'q': round(q, 3), 'rule': rule}
            if 'q_aggr' in p:
                out['aggressiveness'] = clamp(quantile(ref['aggressiveness'], p['q_aggr']))
                basis['aggressiveness'] = {'q': round(p['q_aggr'], 3),
                                           'rule': 'defensive playmaking per snap' if pos != 'HB' else 'yards after contact per attempt'}
            # v2.4: a receiver's catch never sits below what the engine's own curve needs for his real hands. The retail
            # backup TE / HB tiers were blocking TEs and plodders (backup TE catch median 55, 10th percentile 35), so a
            # rank inside them put 88-93% pass catchers (Ertz, Kamara, Theo Johnson) in the drop zone (31-47).
            if pos in ('WR', 'TE', 'HB', 'FB'):
                cc = ((p.get('comp_used') or {}).get('catch') or {}).get('ftn_catchable_caught_rate')
                if cc and cc[1] >= CATCH_FLOOR_MIN_BALLS:
                    floor = clamp(math.ceil(catch_for_probability(cc[0])))
                    if out['catch'] < floor:
                        basis['catch']['floor'] = f'engine catch curve at his catchable-ball rate {cc[0]:.3f}: {floor}'
                        out['catch'] = floor
            # physicals: 2K's own drill fits
            phys, pb = M.physical(p)
            if pos == 'QB' and 'imputed' in str(((pb.get('speed') or {}).get('drills') or {}).get('forty', ['', ''])[1]):
                # no timed 40 anywhere (combine, pro day, cited): his real rushing says how fast he plays. The speed is
                # the retail QB tier's speed at his rushing-yards-per-game percentile (the same percentile as scramble).
                scramble(D, p, players)
                qm = D._qb_mob.get(p['gsis'], 0.3)
                phys['speed'] = clamp(quantile(ref['speed'], min(Q_CLIP[1], max(Q_CLIP[0], qm))))
                pb['speed'] = {'rule': 'no timed 40: retail QB tier speed at the rushing-yards-per-game percentile',
                               'q': round(qm, 3)}
            for r in PHYSICAL:
                if r in phys:
                    out[r] = phys[r]; basis[r] = pb[r]
                else:
                    basis[r] = {'rule': 'retail tier median (no drill data)'}
            # styles
            out['kicking_style'] = 99 if pos == 'K' else 1 if pos == 'P' else 49
            basis['kicking_style'] = {'rule': 'retail convention (K 99, P 1, others 49)'}
            out['power_run_style'], basis['power_run_style'] = power_style(D, p)
            out['scramble'], basis['scramble'] = scramble(D, p, players)
            if pos == 'QB':
                s, a = out['scramble'], out['agility']
                if basis['scramble']['mobile'] and s + a <= 150:
                    s = min(98, 151 - a + ((151 - a) % 2))
                elif not basis['scramble']['mobile'] and s + a > 150:
                    s = max(10, 150 - a - ((150 - a) % 2))
                out['scramble'] = s
                basis['scramble']['family'] = 'mobile (even, scramble + agility > 150)' if s + a > 150 else \
                    'pocket (even, scramble + agility <= 150)'
            p['ratings'], p['basis'] = out, basis
    return players


POWER_SHARE = {'HB': (0.22, 0.23), 'WR': (0.17, 0.09)}   # retail (Finesse, Power) shares: HB 27/122, 28/122; WR 33/200, 17/200


def power_style(D, p):
    """Power Run Style (+0x4D): Finesse 1 / Balanced 50 / Power 99, read by the contact routines as a 0..1 blend
    weight (PROVED OFFLINE: 0x344E10 thresholds 33/66; FUN_001d9c50, FUN_001dfe30, FUN_00284080 ... read it).
    DB 1, QB/K/P 50, linemen/LB/FB/TE 99 as in retail. HB and WR (DESIGN): a style score from real contact data,
    HB = 0.5 weight + 0.5 yards after contact per carry, WR = 0.5 weight + 0.3 broken tackles per catch - 0.2 aDOT
    (deep threats lean Finesse), z-scored at the position; the top share is Power and the bottom share Finesse in
    retail's own proportions (HB 23% / 22%, WR 9% / 17%)."""
    pos = p['pos']
    if pos in ('CB', 'FS', 'SS'):
        return 1, {'rule': 'retail: every DB is Finesse (1)'}
    if pos in ('QB', 'K', 'P'):
        return 50, {'rule': 'retail: QB/K/P Balanced (50)'}
    if pos not in ('HB', 'WR'):
        return 99, {'rule': 'retail: linemen, linebackers, FB and TE are Power (99)'}
    if not hasattr(D, '_style'):
        D._style = {}
    if pos not in D._style:
        rows = [x for x in D._players if x['pos'] == pos]
        feats = []
        for x in rows:
            g = x['gsis']
            def pf(kind, key):
                return sum(w * (f(r.get(key)) or 0) for y, w, r in D.seasons(g, 'pfr_' + kind))
            if pos == 'HB':
                att = pf('rush', 'att')
                feats.append((x['weight'], (pf('rush', 'yac') + 2.9 * 40) / (att + 40)))
            else:
                rec = pf('rec', 'rec'); tgt = pf('rec', 'tgt')
                adot = (pf('rec', 'adot') * 0 + (sum(w * (f(r.get('adot')) or 0) * (f(r.get('tgt')) or 0)
                                                    for y, w, r in D.seasons(g, 'pfr_rec')) + 10.0 * 20) / (tgt + 20))
                feats.append((x['weight'], (pf('rec', 'brk_tkl') + 0.06 * 30) / (rec + 30), adot))
        cols = list(zip(*feats))
        zs = []
        for c in cols:
            mu, sd = statistics.mean(c), statistics.pstdev(c) or 1.0
            zs.append([(v - mu) / sd for v in c])
        w = (0.5, 0.5) if pos == 'HB' else (0.5, 0.3, -0.2)
        score = [sum(wi * z[i] for wi, z in zip(w, zs)) for i in range(len(rows))]
        qs = pct_ranks(score)
        fin, pw = POWER_SHARE[pos]
        D._style[pos] = {x['gsis']: (q, s) for x, q, s in zip(rows, qs, score)}
        D._style[pos + '_cut'] = (fin, 1 - pw)
    q, s = D._style[pos][p['gsis']]
    lo, hi = D._style[pos + '_cut']
    v = 99 if q > hi else 1 if q <= lo else 50
    return v, {'rule': 'style score percentile at the position, retail shares (HB 22% Finesse / 23% Power, WR 17% / 9%)',
               'q': round(q, 3), 'score': round(s, 3)}


def scramble(D, p, players):
    """QB Scramble byte, the game's own mobile-QB archetype (PROVED OFFLINE from the retail code and rosters):
    the low bit picks the animation family at 0x2D92B1 and, when even, scramble + agility > 150 picks the mobile
    family (0xAD2088) over the pocket family (0xAD2048). Retail's scramblers (McNabb 96, McNair 90, Culpepper 90,
    Garcia 86, Stewart 86, ...) are all even with scramble + agility > 150; its pocket passers are even and at or
    below 150; the odd family is Vick (97), Gannon (81), Rivers (53) and every non-QB (5). The magnitude is also read
    by the CPU QB's run/scramble decisions (0x1973F0, 0x19BAE0, FUN_0019B8A0).
    Rule (DESIGN): mobility = 0.4 scrambles per dropback + 0.3 designed runs per game + 0.3 rushing yards per game
    (2024-25, shrunk), percentile inside the QB's tier; the value is the retail QB tier's scramble at that
    percentile, made even; the top 30% of QBs (retail had 10 of 32 starters in the mobile family) are forced into
    the mobile family (scramble + agility > 150), everyone else into the pocket family (<= 150)."""
    if p['pos'] != 'QB':
        return 5, {'rule': 'retail: 5 for every non-QB (the odd family)'}
    if not hasattr(D, '_qb_mob'):
        comps = {}
        for x in players:
            if x['pos'] != 'QB':
                continue
            g = x['gsis']
            db = D.P(g, 'qb', 'dropbacks'); scr = D.P(g, 'qb', 'scrambles')
            games = sum(w * (f((D.F[y].get(g, {}).get('stats') or {}).get('games')) or 0) for y, w in W.items())
            carries = sum(w * (f((D.F[y].get(g, {}).get('stats') or {}).get('carries')) or 0) for y, w in W.items())
            yds = sum(w * (f((D.F[y].get(g, {}).get('stats') or {}).get('rushing_yards')) or 0) for y, w in W.items())
            comps[g] = ((scr + 0.06 * 60) / (db + 60), (max(0.0, carries - scr) + 1.5 * 4) / (games + 4),
                        (yds + 8.0 * 4) / (games + 4))
        ks = list(comps)
        zs = []
        for i in range(3):
            vals = [comps[k][i] for k in ks]
            mu, sd = statistics.mean(vals), statistics.pstdev(vals) or 1.0
            zs.append([(v - mu) / sd for v in vals])
        score = dict(zip(ks, [0.4 * a + 0.3 * b + 0.3 * c for a, b, c in zip(*zs)]))
        D._qb_mob, D._qb_mob_all = {}, dict(zip(ks, pct_ranks([score[k] for k in ks])))
        for tier in ('starter', 'backup'):       # percentile inside the tier, like every other rating
            grp = [x['gsis'] for x in players if x['pos'] == 'QB' and x['tier'] == tier]
            D._qb_mob.update(dict(zip(grp, pct_ranks([score[g] for g in grp]))))
        D._qb_mob_raw = comps
    q = D._qb_mob.get(p['gsis'], 0.3)
    ref = D.ref['QB'][p['tier']]['ratings']['scramble'] if D.ref['QB'][p['tier']]['n'] else D.ref['QB']['all']['ratings']['scramble']
    value = int(2 * round(quantile(ref, min(Q_CLIP[1], max(Q_CLIP[0], q))) / 2))
    raw = D._qb_mob_raw.get(p['gsis'])
    return max(10, min(98, value)), {'rule': 'mobility percentile -> retail QB tier scramble, even; family set in rate_all',
                                     'q': round(q, 3), 'mobile': q >= 0.69,
                                     'scrambles_per_dropback': round(raw[0], 3) if raw else None,
                                     'designed_runs_per_game': round(raw[1], 2) if raw else None,
                                     'rush_yds_per_game': round(raw[2], 1) if raw else None}

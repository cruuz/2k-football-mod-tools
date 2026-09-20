"""Bounded safe per-team placement search using unchanged s10 residual ROIs."""
import json
import fit as F
import player_scale as P
from mod_editor.core import nfl2k5_scorebug_resources as art
from mod_editor.core import nfl2k5_scorebug_teams as teams


def main():
    spec = json.loads((F.DATA/'layout.json').read_text())
    spec['logo_fit']['by_team']['HOU']['shift_x'] = 0.
    preview = P.sprite.NativePreview()
    palette = teams.load()
    indices = {name: i+1 for i, name in enumerate(sorted(art.TEAM_LOGOS))}
    rows = []

    def install(team, fit):
        span = art.mnf_panel_span(preview.atlas, team, 'home',
            logo_fit={'by_team': {team: fit}},
            plate_tints={n: t['plate'] for n, t in palette.items()},
            wing_tints={n: t['wing'] for n, t in palette.items()})
        for mode in preview.modes.values():
            mode['textures'][indices[team]] = span

    for team, fit in spec['logo_fit']['by_team'].items():
        install(team, fit)
    for matchup, (path, state) in P.CASES.items():
        reference = P.reference(path)
        for team in (state['away'], state['home']):
            old = spec['logo_fit']['by_team'][team]
            candidates = []
            # Native texture pixels, both aspects. Preserve the team's s10
            # horizontal proportion; only size and placement may change.
            for zoom in (.976, .94, .90, .86):
                for dx in (-4, -2, 0, 2, 4):
                    candidate = dict(old, zoom=zoom, shift_x=dx/64, shift_y=0.)
                    if not F.retained(team, candidate, inset=1)['passed']:
                        continue
                    install(team, candidate)
                    measurements = []
                    for wide in (False, True):
                        image, _ = P.draw(preview, state, wide)
                        measurements.extend(P.metrics(image, reference))
                    totals = {name: sum(r['visible_area_px'] for r in measurements if r['feature']==name)/2
                              for name in ('logo', 'wing_colour', 'score')}
                    row = dict(team=team, fit=candidate, metrics=totals,
                               objective=totals['logo']+totals['wing_colour'])
                    rows.append(row); candidates.append(row)
                    print(json.dumps(row), flush=True)
            best = min(candidates, key=lambda r: r['objective'])
            spec['logo_fit']['by_team'][team] = best['fit']
            install(team, best['fit'])
            print('SELECT', team, best, flush=True)
    F.write('search_trials.json', rows)
    F.write('selected_fits.json', {n: spec['logo_fit']['by_team'][n] for n in ('DEN', 'KC', 'LV', 'HOU')})
    (F.DATA/'layout.json').write_text(json.dumps(spec, indent=1)+'\n', encoding='utf-8', newline='\n')
    accents = json.loads((F.DATA/'team_accents.json').read_text())
    for team, row in accents['teams'].items():
        if team in spec['logo_fit']['by_team']:
            row['logo_fit'] = spec['logo_fit']['by_team'][team]
    (F.DATA/'team_accents.json').write_text(json.dumps(accents, indent=2)+'\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()

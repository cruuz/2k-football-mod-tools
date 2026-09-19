"""ESPN hierarchy and readability rubric over code-measured facts only."""
LEVELS=[
    'Critical failure: label absent/dim, overlap, or false calibration claim.',
    'Major issue: one or more fields unreadable or team identity incorrect.',
    'Readable fields, but hierarchy, spacing or team identity remains uncertain.',
    'Readable fields with clear hierarchy and identity; calibration unresolved.',
    'Every field readable, no overlaps, team identity clear, calibrated comparison passes.',
]


def request(descriptor,*,calibration_verified=False,identity_verified=False,overlap_verified=False):
    fields=descriptor['fields']
    # Clock and quarter have intentional dark ink on a light capsule.
    readable={k:(v['core_luma']>=200 if k not in ('clock','quarter') else v['ink_pixels']>0)
              for k,v in fields.items() if k in ('away_score','home_score','clock','quarter','play_clock','down')}
    heights={k:(v['ink_box'][3]-v['ink_box'][1] if v['ink_box'] else 0) for k,v in fields.items() if k in readable}
    hierarchy=heights['away_score']>heights['clock'] and heights['home_score']>heights['clock']
    return dict(tool='jev_score',instructions='Judge ESPN scorebug design from these measured facts only. Scores should lead, then clock, then label. Unknown calibration prevents the top level. Missing bright label ink is critical. Do not calculate or infer unprovided facts.',
                state=dict(readable=readable,score_hierarchy=hierarchy,overlap='verified_clear' if overlap_verified else 'unverified',
                    identity='verified_team_specific' if identity_verified else 'unverified',calibration='passed' if calibration_verified else 'unresolved'),levels=LEVELS)

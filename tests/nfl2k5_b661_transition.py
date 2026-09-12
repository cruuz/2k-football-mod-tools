"""Read-only beta 66.1 transition research: real BuildPlan -> native XBE.

No disc is copied. Resource loading remains a declared harness boundary.
The two executable-pass argument expressions come from mod_build._build so
this fixture cannot silently substitute the allocator gate's option defaults.
"""
from dataclasses import replace
import ast
import inspect
from pathlib import Path

from mod_editor.core import mod_build as mb
from mod_editor.core import nfl2k5_throw_tuning as tt

ROOT = Path(__file__).resolve().parents[1]
DISC = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
SIMWIN66 = dict(
    accelerated_clock=True, accelerated_clock_minimum_seconds=20,
    player_star=True, position_pools=True, edge_rename=True, my_career=True,
    xbe_space=True, cpu_money_downs='modern', coverage_trail=True,
    franchise_edit_player=True, weekly_prep=True, weekly_prep_cpu=True,
    weekly_prep_remember=True, playbook_pair=True, read_option_runtime=True,
    qb_spy=True, deep_zone_facing=True, deep_zone_bail=True,
    seven_on_seven=True, abilities=True, camera=True, helmet_finish='matte',
    playbook_packs=tuple(str(ROOT / 'data/playbooks' / name) for name in
                        ('softdrink_option.2k5book', 'softdrink_modern_defense.2k5book')),
)
# Mutually exclusive choices use the runtime variant (Guardian B, dynamic
# scorebug). External user artwork/audio/roster imports require user assets.
EXTRA = dict(momentum=3, momentum_contact=True, momentum_collisions=True,
    momentum_collision_level=3, guardian_cap=False, guardian_overlay=True,
    scorebug_runtime=True, music_shuffle=True, screen_hooks=True,
    crib_reclaim=True,
    reserves_16=True, created_teams_extra=2, defensive_try=True,
    zone_drop_cap=True, all_stadiums=True, music_policy='jukebox_menus',
    music_unlock=True, music_userlist=True, practice_squad_screen=True,
    coverage_slider=True, scramble_tuning=True, chop_block_toggle=True,
    team_names_2026=True)


def plan_for(name):
    plan = mb.BuildPlan(source=str(DISC), target='unused-b661-harness.iso')
    if name == 'retail':
        return plan
    plan = mb.apply_preset(plan, 'softdrink_advanced' if name == 'advanced'
                           else 'softdrink_experimental')
    if name in ('simwin66', 'everything', 'everything_no_career'):
        plan = replace(plan, **SIMWIN66)
    if name.startswith('everything'):
        plan = replace(plan, **EXTRA)
    if name == 'everything_no_career':
        plan = replace(plan, my_career=False)
    return plan


def _expression(node, env):
    return eval(compile(ast.Expression(node), '<mod_build executable arguments>', 'eval'), env)


def compose(retail, plan):
    """Execute the disc builder's XBE passes in memory, retaining its order.

    PLAY intents are compiled against the original source by the Build tab's
    real preview compiler. Later archive recoding/relocation is outside this
    fixture; frame probes must declare their own loaded PLAY/ROST inputs.
    """
    if not plan.wants_xbe_patch():
        return retail, {'plan': plan.to_recipe(), 'passes': []}
    r62 = mb._validated_r62_plan_options(plan)
    if plan.momentum or plan.momentum_collisions:
        plan = replace(plan, accel_ramp=False)
    tree = ast.parse(inspect.getsource(mb._build))
    env = dict(plan=plan, tt=tt, source=DISC, progress=lambda *_: None,
               uniform_choice_mode=mb.uniform_choice_mode)
    kwargs_node = next(n.value for n in ast.walk(tree) if isinstance(n, ast.AnnAssign)
                       and isinstance(n.target, ast.Name) and n.target.id == 'kwargs')
    first = _expression(kwargs_node, env)
    accepted = inspect.signature(tt._apply_all).parameters
    first = {k: v for k, v in first.items() if k in accepted}
    settings = tt.TuningSettings(plan.max_deep_yards, plan.arc,
                                plan.realistic_flight, plan.arc_by_distance)
    payload, _ = tt._apply_all(retail, tt.curves_for(settings) if plan.throw else None,
                              arc_table=plan.arc_by_distance, **first)
    passes = ['initial_xbe']
    from mod_editor.core import nfl2k5_position_pools as pools
    from mod_editor.core import nfl2k5_depth_chart_rows as rows
    from mod_editor.core import nfl2k5_season_length as season
    from mod_editor.core import nfl2k5_playoff_picture as picture
    from mod_editor.core import nfl2k5_scorebug_ingame as scorebug
    if plan.scorebug and not plan.scorebug_runtime:
        payload = scorebug.apply_xbe(payload)[0]
        passes.append('static_scorebug')
    if plan.position_pools:
        payload = pools.apply(payload, roster_has_olb=True)[0]
        passes.append('pools_retained')
    if plan.depth_chart_rows:
        payload = rows.apply(payload)[0]
        passes.append('depth_chart_rows')
    if plan.season_2026:
        payload = season.apply(payload)[0]
        payload = picture.apply(payload)[0]
        passes.append('season_2026')
    if plan.position_pools:
        payload = pools.apply(payload, roster_has_olb=False)[0]
        passes.append('pools_final')
    pairs = mb._preview_play_intents(DISC, list(plan.playbook_packs)) if (
        plan.read_option_runtime or plan.qb_spy) else []
    read_table, read_receipt = tt.read_option_patch.compile_intent_table(pairs) if plan.read_option_runtime else (None, None)
    spy_table, spy_receipt = tt.qb_spy_patch.compile_intent_table(pairs) if plan.qb_spy else (None, None)
    playlist_selection = tt.music_playlist_patch.Selection() if plan.music_shuffle else None
    env.update(r62=r62, read_table=read_table, spy_table=spy_table,
               playlist_selection=playlist_selection)
    runtime_call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and n.func.attr == '_apply_all'
        and any(k.arg == 'qb_spy_intent_table' for k in n.keywords))
    runtime = {}
    for keyword in runtime_call.keywords:
        value = _expression(keyword.value, env)
        if keyword.arg is None:
            runtime.update(value)
        else:
            runtime[keyword.arg] = value
    payload, _ = tt._apply_all(payload, **runtime)
    passes.append('runtime_union')
    from mod_editor.core import nfl2k5_helmet_finish as finish
    if plan.helmet_finish == 'matte':
        payload = finish.apply(payload, finish='matte')[0]
        passes.append('helmet_finish')
    return payload, dict(plan=plan.to_recipe(), passes=passes,
                        read_intents=read_receipt, spy_intents=spy_receipt)

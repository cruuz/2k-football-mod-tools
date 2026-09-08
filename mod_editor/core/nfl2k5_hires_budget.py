"""A necessary texture-memory bound, explicitly NOT a whole-game fit proof.

The corpus proves a variable residual heap, not its live free space. A folder
over the physical-arena ceiling is refused; a smaller folder remains UNPROVED.
Never display the arithmetic residual as measured or guaranteed headroom.
"""
from __future__ import annotations

from itertools import combinations

from . import nfl2k5_hires_catalog as catalog

MIB = 1024**2
GUEST_BYTES = 64*MIB
GPU_MASK = 0x03FFFFFF
PHYSICAL_RESERVE = 2*MIB  # retail DAT_00A6D324, subtracted in 0x326E0
ARENA_CEILING = GUEST_BYTES-PHYSICAL_RESERVE
HEADER_BYTES = ALIGNMENT = 128  # 0x483D0: align(request+0x80, 0x80)
# o3c164..185 jerseyname00..21, 256x32 P8 output surfaces. Their source
# glyph atlas is the separate 1024x32 per-kit TXTR, which stays native.
PLAYER_NAMES = 22 * ((128+11776+16+128+127) & ~127)


def allocation(request):
    if type(request) is not int or request < 0:
        raise ValueError('Allocation bytes must be a nonnegative integer')
    return (request+HEADER_BYTES+ALIGNMENT-1) & -ALIGNMENT


def _family(asset):
    return asset.family or {'helmet': 'helmets', 'field_logo': 'field_logos', 'scorebug': 'scorebug'}[asset.key]


def _kit(asset):
    return asset.kit or ('00h0' if asset.key == 'helmet' else '')


def model(assets, scale=2, *, rows=()):
    """Two worst kit packages, two field scenes, two external logos, scorebug.

    Counts are a stated matchup/transition scenario, not an observed residency
    limit. 22 players bind shared kit handles and have native generated name
    surfaces; per-player models are unknown, not multiplied by the kit size.
    Before encoding, zero scratch is a lower bound. After encoding the actual
    checked scratch is included. This permits sound rejection, never sound fit.
    """
    if type(scale) is not int or scale not in (1, 2):
        raise ValueError('Only native or 2x output is supported')
    assets = tuple(assets)
    checked = {r['key']: r['after'] for r in rows}
    kits = getattr(catalog, 'KIT_COSTS', {})
    fields = getattr(catalog, 'FIELD_COSTS', {})
    # Unif and NAME have zero size words and use other registered loaders;
    # they are excluded, rather than assigned an invented 128-byte block.
    kit_native = {k: sum(allocation(s+v+scratch) for s, v, scratch in costs if s or v)
                  for k, costs in kits.items()}
    kit_after = dict(kit_native)
    field_native = {k: allocation(sum(cost)) for k, cost in fields.items()}
    field_after = dict(field_native)
    external_native, external_after, score_native, score_after = [], [], [], []
    family_rows = {}
    for a in assets:
        family = _family(a)
        selected = a.video_size(scale)
        video = ((a.original_video+127) & ~127)+selected if a.kind == 'SCNE' else selected
        scratch = checked.get(a.key, {}).get('scratch_bytes', 0)
        new = allocation(a.system_size+video+scratch)
        native_video = a.original_video if a.kind == 'SCNE' else a.video_size(1)
        native = allocation(a.system_size+native_video)
        bucket = family_rows.setdefault(family, dict(assets=0, native_texture_video_bytes=0,
                                                    output_texture_video_bytes=0, disc_resource_allocation_bytes=0))
        bucket['assets'] += 1
        bucket['native_texture_video_bytes'] += a.video_size(1)
        bucket['output_texture_video_bytes'] += selected
        bucket['disc_resource_allocation_bytes'] += new
        kit = _kit(a)
        if kit in kits:
            original = allocation(sum(kits[kit][a.chunk]))
            kit_after[kit] += new-original
        elif family in ('helmets', 'numbers', 'jerseys'):
            # Used only by small synthetic fixtures; never invent retail kits.
            kit_native[kit or a.key] = kit_native.get(kit or a.key, 0)+native
            kit_after[kit or a.key] = kit_after.get(kit or a.key, 0)+new
        elif family == 'stock_fields':
            field_native[a.outer] = field_native.get(a.outer, native)
            field_after[a.outer] = new
        elif family == 'field_logos':
            external_native.append(native)
            external_after.append(new)
        elif family == 'scorebug':
            score_native.append(native)
            score_after.append(new)
    def largest(values, count=2):
        return sum(sorted(values, reverse=True)[:count])
    components = [
        dict(component='two shared uniform texture sets', native_bytes=largest(kit_native.values()), output_bytes=largest(kit_after.values())),
        dict(component='two primary field scenes', native_bytes=largest(field_native.values()), output_bytes=largest(field_after.values())),
        dict(component='two selected external midfield logos', native_bytes=largest(external_native), output_bytes=largest(external_after)),
        dict(component='selected scorebug textures', native_bytes=sum(score_native), output_bytes=sum(score_after)),
        dict(component='22 player name output surfaces', native_bytes=PLAYER_NAMES, output_bytes=PLAYER_NAMES),
    ]
    native = sum(c['native_bytes'] for c in components)
    total = sum(c['output_bytes'] for c in components)
    over = max(0, total-ARENA_CEILING)
    return dict(budget_schema='nfl2k5_hires_budget/v2', budget_status='over-budget' if over else 'unproved',
                guest_bytes=GUEST_BYTES, arena_upper_bound_bytes=ARENA_CEILING, gpu_address_mask=GPU_MASK,
                allocator_header_bytes=HEADER_BYTES, allocator_alignment_bytes=ALIGNMENT,
                modeled_native_bytes=native, modeled_output_bytes=total, modeled_delta_bytes=total-native,
                modeled_residual_to_ceiling_bytes=ARENA_CEILING-total, over_budget_bytes=over,
                headroom_bytes=None, whole_game_fit_proved=False, largest_proved_growth_subset=[],
                live_heap_base=None, live_heap_size=None, live_heap_free_bytes=None,
                on_field_players=22, shared_team_packages=2, components=components, families=family_rows,
                scratch_policy='actual checked output scratch' if checked else 'zero output scratch lower bound',
                unknowns=['kernel contiguous allocation result', 'startup arena reservations',
                          'resource-context heap selection', 'nontexture residents including Unif and NAME objects',
                          'sideline and replay lifetimes', 'fragmentation and largest free block',
                          'simultaneous old/new loads outside the two-scene scenario'],
                message=(f'Hi-res textures need at least {total:,} bytes in this scenario; '
                         f'the arena ceiling is {ARENA_CEILING:,} bytes; over by {over:,} bytes.' if over else
                         f'Modeled texture allocations: {total:,} bytes. Whole-game memory fit is unproved.'))


def enforce(receipt):
    if receipt['over_budget_bytes']:
        raise ValueError(receipt['message'])


def family_subsets(assets, scale=2):
    """Largest whole-family selection inside the necessary bound, not a fit claim."""
    assets = tuple(assets)
    names = sorted({_family(a) for a in assets})
    candidates = []
    for count in range(len(names)+1):
        for families in combinations(names, count):
            selected = tuple(a for a in assets if _family(a) in families)
            report = model(selected, scale)
            if not report['over_budget_bytes']:
                candidates.append((len(selected), families, report['modeled_output_bytes']))
    best = max(candidates, default=(0, (), 0))
    return dict(families=list(best[1]), assets=best[0], modeled_output_bytes=best[2],
                whole_game_fit_proved=False, largest_proved_growth_subset=[])

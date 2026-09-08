"""Bounded PLAY census and experimental coverage recipes using native exchanges.

No executable patch or new receiver recognition algorithm is installed. The
retail boundary test is geometry, not a route-name or modern #2-release key.
See docs/mod_editor/match_coverage/README.md for the exact evidence boundary.
"""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
from typing import Sequence

from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib
from . import nfl2k5_playbook_inspector as inspector
from .errors import ValidationError

EVIDENCE = "EXPERIMENTAL / UNWITNESSED"
CENSUS_SCHEMA = "nfl2k5_match_coverage_census/v1"
MATCH_PRESETS = (
    "Cover 3 Rip exchange EXPERIMENTAL", "Cover 3 Liz exchange EXPERIMENTAL",
    "Quarters exchange EXPERIMENTAL", "Two Read exchange EXPERIMENTAL",
    "Cover 1 Robber EXPERIMENTAL",
)
PACK_NAMES = (
    "SD C3 Rip Match EXP", "SD C3 Liz Match EXP", "SD Quarters Match EXP",
    "SD Two Read EXP", "SD One Robber EXP",
)
MODERN_NAMES = (
    "SD Zero Man", "SD One High Man", "SD Two Man", "SD Two Hard", "SD Two Soft",
    "SD Three Deep", "SD Four Deep Spot", "SD Six Split Field",
    "SD Fire Replace Three", "SD Replace Three",
)
RECIPE_LIMITS = (
    "Fixed right-side inside-break exchange with three deep destinations. "
    "No automatic strength call, #2 vertical key or complete Rip rules.",
    "Fixed left-side inside-break exchange with three deep destinations. "
    "No automatic strength call, #2 vertical key or complete Liz rules.",
    "Outside corners hand vertical targets to the safeties, then take outer quarters. "
    "Safeties do not independently read #2; complete quarters-match is unproved.",
    "Corners hand inside-breaking targets to the safeties, then take the flats. "
    "This does not implement the Palms corner's #2-out key.",
    "Five native man assignments, a middle robber landmark and one deep safety. "
    "The robber uses ordinary native receiver pickup; no new route recognition.",
)
# Complete retail defense grammar found in all 37 books. Anything else remains
# visible as an unresolved candidate, never silently counted as ordinary zone.
RETAIL_SHAPES = {
    (0x01, 0x01), (0x1B, 0x0B), (0x1B, 0x0D), (0x1B, 0x0E),
    (0x1B, 0x0D, 0x0E), (0x1B, 0x0E, 0x0D), (0x1B, 0x18, 0x0B),
}


def boundary_words(mode: int) -> str:
    """Plain description of 0x0019FA10, table 0x0050A4C8 (identity 0..15)."""
    if type(mode) is not int or not 0 <= mode <= 15:
        raise ValidationError("A native coverage boundary must be 0 through 15.")
    clauses = []
    if mode & 3 in (1, 2):
        side = "left" if mode & 3 == 1 else "right"
        clauses.append(f"the receiver moves {side} past the defender and the "
                       "midpoint between that defender and the game's reference player")
    if mode & 12 == 4:
        clauses.append("the receiver goes beyond the defender and reaches 15 yards downfield")
    elif mode & 12 == 8:
        clauses.append("the receiver comes behind the defender and below 15 yards downfield")
    return " or ".join(clauses) or "no lateral or depth boundary is enabled"


def analyze_chains(chains: Sequence) -> dict:
    """Classify complete declared chains, not play names or a lone flag bit.

    Transition operand 6 arms both consumers (+0xa8). Man operand 5 signals
    the friendly slot. A lone man node with operand 7 set is not an exchange.
    Unknown predicates and incomplete pairs are returned for explicit review.
    """
    if len(chains) != 11:
        raise ValidationError("A coverage census needs all eleven assignments.")
    flows, issues, predicates = {}, [], []
    for slot, chain in enumerate(chains):
        ops = tuple(n[0] for n in chain)
        if ops not in RETAIL_SHAPES:
            issues.append(dict(slot=slot, reason="Unclassified defensive chain", opcodes=list(ops)))
        predicates.extend(dict(slot=slot, node=i, kind=int(n[1][0]))
                          for i, n in enumerate(chain) if n[0] == 0x1A)
        if ops not in ((0x1B, 0x0D, 0x0E), (0x1B, 0x0E, 0x0D)):
            if any(n[0] in (0x0D, 0x0E) and n[1][6] for n in chain):
                issues.append(dict(slot=slot, reason="Transition without a recognized continuation"))
            continue
        man = next(n[1] for n in chain if n[0] == 0x0E)
        zone = next(n[1] for n in chain if n[0] == 0x0D)
        if not man[6] or not zone[6] or not 0 <= man[5] < 11:
            issues.append(dict(slot=slot, reason="Exchange has an unarmed action or invalid partner"))
            continue
        flows[slot] = dict(slot=slot, partner=int(man[5]),
            direction="man_to_zone" if ops[1] == 0x0E else "zone_to_man",
            boundary=int(man[4]), receiver_selector=int(man[3]),
            cushion_yards=round(man[1] / lib.YD, 4),
            zone_x_yards=round(zone[0] / lib.YD, 4),
            zone_depth_yards=round(zone[1] / lib.YD, 4),
            man_transition=int(man[6]), zone_transition=int(zone[6]))
    pairs = []
    for slot, rule in flows.items():
        partner = flows.get(rule['partner'])
        if (not partner or partner['partner'] != slot or
                partner['direction'] == rule['direction'] or
                partner['receiver_selector'] != rule['receiver_selector']):
            issues.append(dict(slot=slot, kind="unpaired", reason="Missing, nonreciprocal or different-target exchange partner"))
            continue
        if rule['direction'] == 'man_to_zone':
            if not rule['boundary']:
                issues.append(dict(slot=slot, reason="Man continuation has no geometric boundary"))
            else:
                pairs.append(dict(man_slot=slot, zone_slot=rule['partner'],
                                  boundary=rule['boundary'], trigger=boundary_words(rule['boundary'])))
    return dict(rules=list(flows.values()), pairs=pairs, unresolved=issues, predicates=predicates)


def _formation_row(book, body, formation, analysis):
    codes = lib.category_positions(body, lib.formation_category(body, formation.index))
    labels = [codec.position_label(c) for c in codes]
    pairs = []
    by_slot = {r['slot']: r for r in analysis['rules']}
    for pair in analysis['pairs']:
        m, z = pair['man_slot'], pair['zone_slot']
        mr, zr = by_slot[m], by_slot[z]
        pairs.append(dict(pair, man_position=labels[m], zone_position=labels[z],
            description=(f"{labels[m]} (slot {m}) starts in man. When {pair['trigger']}, "
                f"it signals {labels[z]} (slot {z}) and takes a zone at "
                f"X {mr['zone_x_yards']:+g}, depth {mr['zone_depth_yards']:g} yards. "
                f"{labels[z]} starts with a zone landmark at X {zr['zone_x_yards']:+g}, depth "
                f"{zr['zone_depth_yards']:g} yards, then changes from zone to man. "
                "The receiver position is predicted 0.2 seconds ahead; live pickup remains native.")))
    paired = {s for p in analysis['pairs'] for s in (p['man_slot'], p['zone_slot'])}
    warnings = []
    for rule in analysis['rules']:
        s, partner = rule['slot'], rule['partner']
        if s in paired:
            continue
        if rule['direction'] == 'man_to_zone':
            words = (f"{labels[s]} (slot {s}) has a man-to-zone rule when "
                f"{boundary_words(rule['boundary'])}. It signals {labels[partner]} (slot {partner}), "
                f"then takes a zone at X {rule['zone_x_yards']:+g}, depth {rule['zone_depth_yards']:g} yards.")
        else:
            words = (f"{labels[s]} (slot {s}) has a zone-to-man continuation, waiting for its own slot signal; "
                f"its later man node names {labels[partner]} (slot {partner}) as partner.")
        warnings.append(words + ' The stored partner slots are not reciprocal. Live effect is unproved.')
    return dict(index=formation.index, name=formation.name, labels=labels, pairs=pairs, warnings=warnings)


def census_book(resource: bytes, team: str) -> dict:
    """One 78,768-byte resource at a time; include every play and menu alias."""
    if len(resource) != inspector.BODY_SIZE + 32:
        raise ValidationError("Census input must be one fixed-size PLAY resource.")
    book = inspector.parse_playbook_resource(resource, asset_id='book:' + team)
    body = resource[32:]
    matches, unresolved, shapes = [], [], Counter()
    defense_count = predicates = ordinary_flagged_man = 0
    for play in book.plays:
        flags, raw_chains = lib.play_chains(body, play.index)
        error = codec.validate_play(flags, raw_chains)
        if error:
            raise ValidationError(f"{team} play {play.index}: {error}")
        codec.validate_sync(raw_chains)
        chains = lib.exact_play_chains(body, play.index)
        if play.family_id != 1:
            continue
        defense_count += 1
        for chain in chains:
            shapes['/'.join(f'{n[0]:02x}' for n in chain)] += 1
            ordinary_flagged_man += int(len(chain) == 2 and chain[-1][0] == 0x0E
                                       and bool(chain[-1][1][7]) and not chain[-1][1][6])
        analysis = analyze_chains(chains)
        predicates += len(analysis['predicates'])
        if analysis['unresolved']:
            unresolved.append(dict(play=play.index, name=play.name, **analysis))
        if not analysis['rules']:
            continue
        forms = [_formation_row(book, body, f, analysis) for f in book.formations
                 if any(l.play_index == play.index for l in f.play_links)]
        if not forms:
            unresolved.append(dict(play=play.index, name=play.name, reason="Exchange has no formation menu link"))
        matches.append(dict(book=team, play=play.index, name=play.name,
                            rules=analysis['rules'], formations=forms))
    # The independent codec must reproduce unused pool nodes too.
    for index in range(book.node_count):
        node = body[inspector.NODE_BASE + 8 * index:inspector.NODE_BASE + 8 * (index + 1)]
        if codec.Node.from_bytes(node).to_bytes() != node:
            raise ValidationError(f"{team} pool node {index} cannot round-trip exactly.")
    return dict(book=team, source_sha256=hashlib.sha256(resource).hexdigest(),
        body_sha256=hashlib.sha256(body).hexdigest(), plays=len(book.plays),
        defensive_plays=defense_count, nodes=book.node_count,
        formations=len(book.formations), matches=matches, unresolved=unresolved,
        predicate_nodes=predicates, ordinary_flagged_man_assignments=ordinary_flagged_man,
        shapes=dict(sorted(shapes.items())))


def census(image: Path) -> dict:
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    with OuterImage(image) as archive:
        books = [census_book(archive.read_entry(entry), team) for team, entry in BOOK_ENTRIES.items()]
    totals = {key: sum(b[key] for b in books) for key in
              ('plays', 'defensive_plays', 'nodes', 'predicate_nodes', 'ordinary_flagged_man_assignments')}
    totals.update(books=len(books), matched_plays=sum(len(b['matches']) for b in books),
                  matched_menu_entries=sum(len(p['formations']) for b in books for p in b['matches']),
                  unresolved=sum(len(b['unresolved']) for b in books),
                  unclassified_plays=sum(any(i.get('kind') != 'unpaired' for i in p.get('unresolved', [p]))
                      for b in books for p in b['unresolved']),
                  reciprocal_plays=sum(bool(p['formations'] and p['formations'][0]['pairs'])
                      for b in books for p in b['matches']))
    return dict(schema=CENSUS_SCHEMA, evidence=EVIDENCE, gameplay_witnessed=False,
                criterion="Explicit geometric man-to-zone and zone-to-man continuations, including unpaired retail rules",
                vocabulary=["man-to-zone match", "zone-to-man match"], totals=totals, books=books)


def rule_catalog(book, body) -> list[dict]:
    """Named bundles resolve by decoded rules, including renamed retail calls."""
    rows = []
    for play in book.plays:
        if play.family_id != 1:
            continue
        analysis = analyze_chains(lib.exact_play_chains(body, play.index))
        if not analysis['pairs'] or analysis['unresolved']:
            continue
        depth = any(p['boundary'] & 12 == 4 for p in analysis['pairs'])
        label = 'Match: vertical handoff' if depth else 'Match: inside-break exchange'
        for form in book.formations:
            if any(l.play_index == play.index for l in form.play_links):
                detail = _formation_row(book, body, form, analysis)
                rows.append(dict(preset='match_vertical' if depth else 'match_inside', label=label,
                    play=play.index, play_name=play.name, formation=form.index,
                    formation_name=form.name, scope='active',
                    note=EVIDENCE + '. ' + ' '.join(p['description'] for p in detail['pairs'])))
    return rows


def _exchange(design, man_slot, zone_slot, *, boundary, man_zone, zone_start):
    """Author a reciprocal pair with the proved native continuation grammar.

    Side selectors 10/6 and boundary masks follow the audited right/left
    outside-receiver donors. They are not numbered modern receiver keys.
    Neutral starts retain this formation's own geometry and personnel.
    """
    side = 1 if man_slot == 9 else -1
    selector = 10 if side == 1 else 6
    zone_mode = 9 if side == 1 else 10
    def zone(point, mode, transition):
        return (0x0D, [point[0] * lib.YD, point[1] * lib.YD, selector, 0, mode, 1, transition])
    start = (0x1B, [0, 0, 0, 0, 17, 0])
    design.chains[man_slot] = [start,
        (0x0E, [0, 3 * lib.YD, 2 if side == 1 else 1, selector, boundary, zone_slot, 2, 0]),
        zone(man_zone, zone_mode if man_zone[1] >= 15 else (5 if side == 1 else 6), 1)]
    design.chains[zone_slot] = [start, zone(zone_start, zone_mode if zone_start[1] >= 15 else 4, 2),
        (0x0E, [0, 3 * lib.YD, 0, selector, 10 if side == 1 else 9, man_slot, 1, 1])]


def make_match_design(book, body, formation_index, preset):
    if preset not in MATCH_PRESETS:
        raise ValidationError("Unknown experimental match recipe.")
    base = ('Cover 2 Man' if preset == MATCH_PRESETS[4] else
            'Cover 4 Quarters (spot)' if preset == MATCH_PRESETS[2] else
            'Cover 2 Soft' if preset == MATCH_PRESETS[3] else 'Cover 3')
    design = lib.make_defense_design(book, body, formation_index, base)
    if preset in MATCH_PRESETS[:2]:
        right = preset == MATCH_PRESETS[0]
        _exchange(design, 9 if right else 10, 4 if right else 6,
                  boundary=13 if right else 14,
                  man_zone=(16 if right else -16, 18), zone_start=(8 if right else -8, 8))
        # Fix the underneath rotation explicitly; it never auto-flips to strength.
        design.chains[8][1][1][:2] = [(-10 if right else 10) * lib.YD, 8 * lib.YD]
    elif preset == MATCH_PRESETS[2]:
        for m, z, side in ((9, 7, 1), (10, 8, -1)):
            _exchange(design, m, z, boundary=7, man_zone=(18 * side, 18), zone_start=(6 * side, 18))
    elif preset == MATCH_PRESETS[3]:
        for m, z, side in ((9, 7, 1), (10, 8, -1)):
            _exchange(design, m, z, boundary=13 if side == 1 else 14,
                      man_zone=(16 * side, 5), zone_start=(12 * side, 18))
    else:
        for slot, depth in ((7, 20), (8, 8)):
            design.chains[slot][1][1][:2] = [0, depth * lib.YD]
            design.chains[slot][1][1][4:] = [8 if slot == 7 else 4, 0, 0]
    design.preset = preset
    for chain in design.chains:
        codec.validate_defense_operands(chain)
    error = lib.validate_chains(design.play_flags,
                                lib.play_chains(body, design.donor_play_index)[1], design.chains)
    analysis = analyze_chains(design.chains)
    if error or analysis['unresolved']:
        raise ValidationError(f"Experimental coverage failed validation: {error or analysis['unresolved']}")
    return design


def match_coverage_pack(book, body, team=None):
    from . import nfl2k5_playbook_pack as pk
    team = team or book.book_name
    if team not in pk.DEFENSE_BOOKS:
        raise ValidationError("Match coverage supports the 37 retail books only.")
    if any(p.name in PACK_NAMES for p in book.plays):
        raise ValidationError("This book already contains part or all of match coverage; use its source.")
    fi = next((f.index for f in book.formations if f.name == 'Nickel'), None)
    if fi is None:
        fi = next((f.index for f in book.formations if f.name == '4-3'), None)
    if fi is None:
        raise ValidationError("No native Nickel or 4-3 formation is available.")
    lib.defense_personnel(book, body, fi)
    append = team in ('Editor', 'PRACTICE')
    # Keep all stock exchanges and all ten modern-defense destinations. These
    # two built-in packs can therefore coexist without losing either menu set.
    reserved = {p.index for p in book.plays if p.name in MODERN_NAMES}
    if not reserved and not append:
        reserved = {p.replace_index for p in pk.modern_defense_pack(book, body, team).plays}
    candidates = []
    forms = [fi] + [f.index for f in book.formations if f.index != fi and f.name in ('4-3', '3-4', 'Dime')]
    for candidate_form in forms:
        ftype = lib.formation_record(body, candidate_form).type_code
        candidates = sorted({p.index for p in book.plays_for_formation(candidate_form)
            if p.family_id == 1 and (p.flags_or_id & 63) == ftype and p.index not in reserved
            and lib.defense_component(lib.decoded_chains(body, p.index)) == 'coverage'
            and not analyze_chains(lib.exact_play_chains(body, p.index))['rules']}, reverse=True)
        if append or len(candidates) >= len(MATCH_PRESETS):
            fi = candidate_form
            break
    if not append and len(candidates) < len(MATCH_PRESETS):
        raise ValidationError("Fewer than five unused coverage destinations remain in this book.")
    plays = []
    for i, (preset, name) in enumerate(zip(MATCH_PRESETS, PACK_NAMES)):
        design = make_match_design(book, body, fi, preset)
        donor = book.plays[design.donor_play_index]
        target = None if append else candidates[i]
        plays.append(pk.PackPlay(id=f'sd-match-{i:02d}', custom_name=name, play_type='defense',
            assignments=pk._freeze_chains(design.chains),
            donor=pk.PackDonor(donor.index, donor.name, donor.flags_or_id, lib.defense_signature(body, donor.index)),
            play_flags=donor.flags_or_id, replace_index=target,
            replace_name=book.plays[target].name if target is not None else '', concept=preset,
            link_formation=fi if append else None, link_group=3 if append else None,
            defense_formation=book.formations[fi].name, front_index=design.front_index,
            component=lib.defense_component(design.chains), preset_recipe=True))
    return pk.PlaybookPack(
        pk.PackBook(team, 'SOFTDRINK match coverage experiments', 'SOFTDRINK', '1.0.0', 'CC0-1.0', (),
            EVIDENCE + '. Native geometric exchanges, not full modern matching rules. ' + ' '.join(RECIPE_LIMITS)),
        pk.PackBase(pk.book_fingerprint(body), len(book.formations), len(book.plays), book.node_count),
        (), tuple(plays), pk.DEFENSE_SCHEMA)


def main(argv=None):
    # The tool owns filesystem exports and the optional offscreen Qt renderer.
    from tools.nfl2k5_match_coverage import main as command
    return command(argv)


if __name__ == '__main__':
    raise SystemExit(main())

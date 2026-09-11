"""Composed-preset resource inputs for the bounded native series fixture.

Only the primary ROST and ATL PLAY are loaded, in memory. Production data
compilers keep their native relative pointers; no individual player readiness,
schedule outcome or snap is supplied. This is not a whole archive build.
"""
import json
import hashlib
import unittest

from tests.nfl2k5_b661_transition import ROOT
from tests.nfl2k5_supersim_series import Machine as SeriesMachine
from tests.nfl2k5_my_career_fixture import XBE


def resources(plan):
    if not (XBE.parent / 'vc_53450030/0').is_file():
        raise unittest.SkipTest('private USA primary ROST / ATL PLAY archive is absent')
    from tools import nfl2k5_roster_reclassify as roster
    from tools import nfl2k5_playbook_position_recode as recode
    from tools import nfl2k5_franchise_schedule as schedule
    from tools import nfl2k5_kickoff_alignment as alignment
    from mod_editor.core import nfl2k5_roster_arena as arena
    from mod_editor.core import nfl2k5_kickoff_returns as returns
    from mod_editor.core import nfl2k5_depth_roles as roles
    from mod_editor.core import nfl2k5_screen_timing as timing
    with roster.OuterImage(XBE.parent) as archive:
        re, pe = archive.entries[5], archive.entries[308]
        if re.size > 1024**2 or pe.size != 78768:
            raise AssertionError('bounded primary ROST / ATL PLAY sizes differ')
        raw = archive.read_entry(5)
        play = archive.read_entry(308)
        schemes = roster.book_schemes(archive)
    if (hashlib.sha256(raw[32:]).hexdigest() !=
            'b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae' or
            hashlib.sha256(play).hexdigest() !=
            '7963263b71c0a7a2de4798afa8053b59647f6773c2cf76b6f902288217bd62d5'):
        raise unittest.SkipTest('private primary ROST / ATL PLAY evidence pins differ')
    passes = []
    if plan.position_pools:
        parsed = roster.parse_resource(5, 0, raw)
        moves, _ = roster.plan_resource(parsed, schemes)
        body = bytearray(parsed.body)
        roster.apply_moves(body, moves)
        raw = raw[:32] + bytes(body)
        book = recode.parse_book('ATL', pe, play)
        table, _ = recode.recoded_table(book)
        at = book.table_offset - book.virtual_offset
        play = play[:at] + table + play[at + len(table):]
        passes.append('position pools ROST / PLAY')
    if plan.kickoff_alignment:
        book = recode.parse_book('ATL', pe, play)
        for name, ref in alignment._formation_refs(book, play).items():
            points = (alignment.kickoff_xz_2026() if name == alignment.KICKOFF_NAME
                      else alignment.KICK_RETURN_XZ_2026)
            at = ref.virtual_offset - book.virtual_offset
            new = alignment.with_xz(ref.slots, points)
            play = play[:at] + new + play[at + len(new):]
        passes.append('kickoff alignment')
    if plan.dynamic_kickoff:
        play = returns.apply(play)[0]
        passes.append('kickoff return assignments')
    if plan.depth_roles:
        play = roles.normalise(play).replacement
        passes.append('depth roles')
    if plan.screen_timing:
        play = timing.apply(play, plan.screen_timing)[0]
        passes.append('screen timing ' + plan.screen_timing)
    if plan.season_2026:
        doc = json.loads((ROOT / 'data/nfl_2026_schedule.json').read_text())
        raw = schedule.apply_pack(raw, schedule.encode_schedule(doc)[0], rost=0,
                                  preseason=schedule.encode_preseason(doc)[0])[0]
        passes.append('2026 regular and preseason templates')
    if plan.reserves_16 or plan.created_teams_extra:
        raw = arena.migrate(raw, reserves_16=plan.reserves_16,
                            created_teams_extra=plan.created_teams_extra)[0]
        passes.append('roster arena migration')
    return raw[32:], play, passes


class Machine(SeriesMachine):
    def __init__(self, payload, plan, *, existing_career=False):
        super().__init__(payload)
        self.roster_input, self.play_input, self.resource_passes = resources(plan)
        self.existing_career = existing_career
        self.signing_input = None

    def create(self, roster, **kwargs):
        player = super().create(roster, **kwargs)
        team = self.get(self.root + 0x1C) + 500 * kwargs.get('club', 2)
        limit = self.call(0x3EE10C, ecx=team)
        self.signing_input = dict(club=self.get(self.state + 56),
            career_state=self.get(self.state + 24),
            team_count=self.uc.mem_read(team + 0x11C, 1)[0], limit=limit)
        if self.existing_career:
            # Explicit scenario input: a signed player already belongs to
            # the club. First retain the fresh-sign result as separate
            # evidence, then construct membership with native cut/append.
            # This does not repair the product's creation route or supply
            # any lineup, animation, camera, readiness or snap flags.
            if self.signing_input != dict(club=0xFFFFFFFF, career_state=4,
                                          team_count=53, limit=53):
                raise AssertionError('fresh-sign boundary changed; review the existing-career input')
            if self.call(0xC3EE0, ecx=team, edx=player) != 0:
                raise AssertionError('full-team append unexpectedly succeeded')
            self.call(0x2BF9A0, ecx=team, edx=limit - 1, budget=10000000)
            if self.call(0xC3EE0, ecx=team, edx=player) != 1:
                raise AssertionError('native membership input failed')
            self.call('resolve_team')
            if self.get(self.state + 56) != kwargs.get('club', 2):
                raise AssertionError('native membership did not resolve the career club')
        return player

    def frontend(self, roster):
        # Keep the existing named hardware/menu services, then supply the
        # paired resource before any career creation or match initialization.
        super().frontend(roster)
        body = self.roster_input[64:]
        self.uc.mem_write(self.ARENA, body)
        self.put(0xB72808, len(body))
        self.put(0xB7280C, len(body))
        self.call(0xC0500, ecx=self.ARENA, budget=1000000)

    def cpu_scene(self, resource, **kwargs):
        return super().cpu_scene(self.play_input, **kwargs)

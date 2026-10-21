"""Native Team Select harness for the classic teams (job ct1): the historic Quick Game harness plus the Anniversary
moment files and the classic files served by name, on an executable with the moments, Quick Game and classic owners.

Native: everything TeamSelectCPU runs (handlers, the option's code in its classic variant, the classic helpers,
release C2300, import C1030 / the practice squad importer). Substituted: the same archive, pad, sound, redraw and
random boundaries as nfl2k5_historic_quick_game_native. EXPERIMENTAL / UNWITNESSED: offline evidence only.
"""
from __future__ import annotations

from nfl2k5_historic_quick_game_native import TeamSelectCPU, disc_evidence  # noqa: F401


class ClassicCPU(TeamSelectCPU):
    def __init__(self, payload, resources, context, identities, *, extra_files):
        self.extra_files = dict(extra_files)
        self.extra_loads = []
        super().__init__(payload, resources, context, identities)

    def archive_stubs(self):
        super().archive_stubs()
        base = self.stubs[0x43F50]

        def load():
            name = self.text(self.reg("edx"))
            if name in self.extra_files:
                self.queued.append(name)
                self.extra_loads.append(name)
                self.write(0x2200000, self.extra_files[name][32:])
                self.ret(1, 16)
            else:
                base()
        self.stubs[0x43F50] = load

    def stadium_id(self, team):
        p = self.r(team + 0x114)
        return self.read(p + 0x7C, 1)[0] if p else None

    def style(self, team):
        return self.read(team + 0x192, 1)[0]


def build(retail_dir, *, season_route=False, payload=None):
    """(cpu, data, moment files, classic files, receipts) on the private retail extraction. payload: a built
    executable to use instead (for example a test disc's), already carrying Quick Game, the moments and maybe the
    season route; else one is composed from retail."""
    from pathlib import Path
    from mod_editor.core import nfl2k5_classic_teams as ct, nfl2k5_espn25_more_moments as mm
    from mod_editor.core import nfl2k5_espn25_rosters as e, nfl2k5_historic_teams_quick_game as h1
    from mod_editor.core import nfl2k5_roster_records as rr
    from mod_editor.core import nfl2k5_throw_tuning as tt
    retail_dir = Path(retail_dir)
    if payload is None:
        payload, _ = tt._apply_all(e.read_xbe(retail_dir), None, False, scheme_labels=True, practice_squad=True,
                                   franchise_practice=True, depth_locks=True, xbe_space=True, zone_drop_cap=True,
                                   espn25_more_moments=True, historic_teams_quick_game=True)
        # A shipped build carries directory code (the H-back, draft-pick and team-ratings spills), which makes the
        # read-only run executable; reserve one such slot here (0xCC padding, no code) so the composition matches.
        from mod_editor.core import nfl2k5_xbe_space as space
        payload, _ = space.extend_scaleout(payload, (space.DIRECTORY_CODE_REQUEST,))
        if season_route:
            payload = h1.enable_season_routing(payload)
    season_route = h1.season_routing_status(payload)
    data, moments = ct.Data.load(), mm.Data.load()
    with rr._outer_image()(retail_dir) as archive:
        by_id = {x.name_id: x for x in archive.entries}
        read = lambda name: archive.read(by_id[mm.name_id(name)].virtual_offset, by_id[mm.name_id(name)].size)  # noqa: E731
        main = archive.read(archive.entries[5].virtual_offset, archive.entries[5].size)
        moment_templates = {k: read(t["template"]) for k, t in moments.teams.items()}
        templates = {k: read(data.teams[k]["template"]) for k in data.order()}
        kits = {e2.name_id for e2 in archive.entries}
    moment_files = mm.compile_files(main, moment_templates, moments)
    has_kit = lambda code, style: all(mm.name_id(f"{code}{s}{style}.iff") in kits for s in "ha")  # noqa: E731
    prefix = "HTS-" if season_route else ""
    files, receipts = ct.compile_files(main, templates, data, spares={}, has_kit=has_kit, prefix=prefix)
    payload, receipt = ct.apply_xbe(payload, ct.rows_for(main, data))
    resources, context, ids = disc_evidence(retail_dir)
    extra = dict(moment_files)
    extra.update(files)
    if season_route:     # the retail 75 under their season-route names (the ht bank serves its own rosters there)
        for d in context["descriptors"]:
            extra["HTS-" + d["filename"]] = resources[d["outer"]]
    make = lambda: ClassicCPU(payload, resources, context, ids, extra_files=extra)  # noqa: E731
    return make, data, moment_files, files, receipt, receipts

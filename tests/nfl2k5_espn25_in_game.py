"""Bounded historic import, re-entry, match roster, depth and kit trace.

Native C1030/C0500, C2300, 617E0/61730/C3C60, E80D0/E7C50/E7810,
E8790, 10C040/10BD80 and 615A0 execute. Archive I/O, controller and presentation are the inherited
explicit boundaries. This does not execute graphics, audio or a complete game.
"""
from pathlib import Path
import os
import zlib

from nfl2k5_espn25_rosters_native import CPU, XBE_SHA256
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_roster_records as rr

BN_XBE_SHA256 = "f174abdc082c013ea90fa29f743c13c2810c65f6eb66d35794e28a26ad97cd52"
BN_CONTEXT = {5: "996e61235f3d2e38d8b36d3aba68f9b2b20cec58ecba9b459813ec9ad0410cb2",
              22: "8a7a3742a944afbdf96da685f96a1ea5a5f3554fc2887e2ede3bd5c898ec35cc"}
BN_IMAGE = Path(os.environ.get("NFL2K5_ESPN25_BN_IMAGE",
    "/home/noah/2K5 Mod Studio Builds/NFL 2K5 MOD TEST 2026-09-08bn (beta-62 RC86 Experimental minus merged positions + ESPN Anniversary exact rosters).xiso.iso"))


def evidence(source):
    manifest, _ = e.dataset()
    wanted = (5, 22, *(t["outer"] for t in manifest["resources"]))
    with rr._outer_image()(source) as archive:
        resources = {}
        for i in wanted:
            e.require(archive.entries[i].size <= e.MAX_RESOURCE, "native evidence resource exceeds bound")
            resources[i] = archive.read_entry(i)
        context = e.describe_context(resources[5], resources[22], archive.entries)
        identities = {entry.name_id for entry in archive.entries}
    return resources, context, identities


class LiveCPU(CPU):
    def __init__(self, payload, resources, context, identities):
        self.imports, self.releases = [], []
        self.identities = identities
        super().__init__(None, resources, context["descriptors"], payload=payload,
                         xbe_sha256=e.sha(payload), instruction_budget=40_000_000)

    def _hook(self, uc, at, size, data):
        if at == 0xC1030:
            dst = self.reg("edx")
            self.imports.append({"destination": dst, "active_before": self.read(dst + 0x11C, 1)[0],
                                 "pointers_before": sum(bool(self.r(dst + i * 4)) for i in range(65))})
        elif at == 0x2D1896:
            self.imports[-1]["result"] = self.reg("eax")
        elif at == 0xC240F:
            # ESI has just been restored; capture the team saved at entry below.
            dst = self.releases[-1]["team"]
            self.releases[-1].update(active_after=self.read(dst + 0x11C, 1)[0],
                pointers_after=sum(bool(self.r(dst + i * 4)) for i in range(65)))
        elif at == 0xC2300:
            dst = self.reg("ecx")
            self.releases.append({"team": dst, "active_before": self.read(dst + 0x11C, 1)[0]})
        super()._hook(uc, at, size, data)

    def person(self, pointer):
        record = rr.PlayerRecord.decode(self.read(pointer, 84))
        return {"pointer": pointer, "first": self.text(self.r(pointer + 16)),
                "last": self.text(self.r(pointer + 20)), "jersey": record.values["jersey"],
                "position": record.position_name, "rank": record.values["depth_rank"],
                "side": record.values["depth_side"]}

    def selected(self):
        result = {}
        for side, getter in (("home", 0x77B00), ("away", 0x77B40)):
            team = self.run(getter)
            result[side] = {"team": team, "name": self.text(self.r(team + 0x104)),
                            "city": self.text(self.r(team + 0x138)),
                            "code": self.text(self.r(team + 0x10C)),
                            "active": self.read(team + 0x11C, 1)[0]}
        return result

    def match(self):
        self.run(0x617E0)  # Real game-day staging; native source/player copies.
        self.run(0x615A0)  # Real era validation and complete kit filename formatter.
        result = self.selected()
        stages = (
                ("home", 0x61C50, 0x61C70, 0xE6019C, 0xB30710),
                ("away", 0x61C60, 0x61C80, 0xE601AC, 0xB30730))
        for side, team_getter, depth_getter, settings, kit_name in stages:
            team, depth = self.run(team_getter), self.run(depth_getter)
            self.run(0xE80D0, ecx=team, edx=depth, args=(self.r(settings), 0))
        scenario = self.scenario_setup()
        for side, team_getter, depth_getter, settings, kit_name in stages:
            team, depth = self.run(team_getter), self.run(depth_getter)
            qb = self.field_player(side, "QB", 0)
            kit = self.text(kit_name)
            identity = zlib.crc32(kit.upper().encode("utf-16le")) & 0xFFFFFFFF
            result[side].update(match_team=team, quarterback=qb, kit=kit,
                                kit_archive_id=identity, kit_exists=identity in self.identities, depth=depth)
        # Execute the real export used by the game load path, with the selected
        # stadium and both native match copies. Its backing buffer is bounded.
        root = self.run(0xC0B90, ecx=self.run(0x61C50), edx=self.run(0x61C60),
                        args=(self.run(0x77460), 0x2400000))
        return {"sides": result, "scenario": scenario, "export_root": root,
                "export_players": self.r(root) if root else None}

    def scenario_setup(self):
        """Real scenario scalars and depth rebuild, after match initialization."""
        for at, target in ((0xE5FC28, 0x2320000), (0xE5FC68, 0x2321000),
                           (0xE6028C, 0x2322000), (0xE602EC, 0x2323000)):
            self.w(at, target)
        saved = dict(self.stubs)
        try:
            # Spatial callbacks and world/clock transitions only. The player
            # iteration, E6680 reset and both E7C50 depth rebuilds execute.
            for at in (0xE9460, 0x10BD60, 0xAF510):
                self.stubs[at] = lambda: self.ret(0)
            self.stubs[0x9CBD0] = lambda: self.ret(0, 8)
            self.run(0x10C040)
        finally:
            self.stubs = saved
        return {"home_score": self.r(0x2320000), "away_score": self.r(0x2321000),
                "clock_seconds": self.f(0x2322010), "quarter": self.r(0xE602C4)}

    def role_player(self, side, position, ordinal):
        depth = self.run(0x61C70 if side == "home" else 0x61C80)
        pool = self.run(0x221EE0, ecx=rr.POSITIONS.index(position))
        kind = self.run(0xE7530, eax=pool, edx=ordinal, esi=0x23A0000)
        index = self.r(0x23A0000)
        # E7810 trusts its caller; real callers first check this native length.
        # Lists abut in memory and do not each carry a trailing FF sentinel.
        if index >= self.run(0xE75A0, ecx=kind, edx=depth):
            return None
        pointer = self.run(0xE7810, eax=kind, ecx=0, args=(depth, index))
        return self.person(pointer) if pointer else None

    def field_player(self, side, position, ordinal, assigned=()):
        """Real formation player picker, with the stated assigned-player set."""
        depth = self.run(0x61C70 if side == "home" else 0x61C80)
        pool = self.run(0x221EE0, ecx=rr.POSITIONS.index(position))
        assert len(assigned) <= 11
        for i, pointer in enumerate(assigned):
            self.w(0x23A0100 + i * 4, pointer)
        pointer = self.run(0xE8790, ecx=depth, edx=0,
                           args=(0, 0, 0x23A0100, len(assigned), 0, pool, ordinal))
        return self.person(pointer) if pointer else None

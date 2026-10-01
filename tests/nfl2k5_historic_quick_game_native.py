"""Bounded native Team Select harness for historic teams in Quick Game.

Native: the Team Select next and previous handlers (2C2240, 2C2310) with the option's six call sites, the
Random Team spin steps (2C1AC0, 2C1B10), the option's code, the retail steps, iterator (778C0, 77950), filter
(E2E50) and setters (2C1780, 2C17C0), the release C2300, the import C1030 (or the practice squad's ps_import
it jumps to), and the spare player pool. Moments use the inherited ESPN 25th Anniversary harness (20CB30,
2D17B0, 20C3C0, 617E0, C0B90 native).

Substituted boundaries, explicit: archive queue, wait, lookup and pop (the named historic file's bytes are
handed back from the disc evidence), the pad-to-side query 771F0, the menu sound 89DA0, the menu redraw
31F010 and the random source 48B50. No graphics, audio, disc timing or complete game.
"""
from __future__ import annotations

import struct

from unicorn import UC_HOOK_CODE

from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_roster_records as rr
from nfl2k5_espn25_in_game import LiveCPU

FLOW, HOME, AWAY = 0xACF614, 0xACF63C, 0xACF640
QUICK_GAME_MASK = 0x5F
HISTORIC_CONTEXT = 0xE9F9A8


def disc_evidence(source):
    """Main ROST, SITU and every historic ROST the main roster names, plus the directory identities."""
    from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
    require_nfl_retail_packs(source)
    with rr._outer_image()(source) as archive:
        main, situ = archive.read_entry(5), archive.read_entry(22)
        context = e.describe_context(main, situ, archive.entries)
        resources = {5: main, 22: situ}
        for descriptor in context["descriptors"]:
            resources[descriptor["outer"]] = archive.read_entry(descriptor["outer"])
        identities = {entry.name_id for entry in archive.entries}
    return resources, context, identities


class TeamSelectCPU(LiveCPU):
    """LiveCPU with Team Select boundaries and hooks only at the named addresses (fast native runs)."""

    BOUNDARIES = frozenset({
        0xC1030, 0x2D1896, 0xC2300, 0xC240F,                    # LiveCPU's import/release observers
        0x43F50, 0x432D0, 0x449E0, 0x432F0,                     # archive boundary
        0x771F0, 0x89DA0, 0x31F010, 0x48B50,                    # pad side, menu sound, redraw, random
        0xF3210, 0x6E390, 0xE3150, 0xF3580, 0x773F0,            # moment selection UI (select())
        0xE9460, 0x10BD60, 0xAF510, 0x9CBD0,                    # match staging spatial/clock seams
    })

    def __init__(self, payload, resources, context, identities):
        self.queued, self.sounds, self.redraws = [], 0, 0
        self.side, self.draw = 1, 0
        super().__init__(payload, resources, context, identities)
        self.uc.hook_del(self._code_hook)
        for at in sorted(self.BOUNDARIES):
            self.uc.hook_add(UC_HOOK_CODE, self._hook, begin=at, end=at)
        head = self.read(0xC1030, 5)
        self.import_body = (0xC1035 + struct.unpack("<i", head[1:])[0]) if head[0] == 0xE9 else 0xC1030
        self.import_runs = 0

        def count(uc, at, size, data):
            self.import_runs += 1
        self.uc.hook_add(UC_HOOK_CODE, count, begin=self.import_body, end=self.import_body)
        self.archive_stubs()

    def run(self, at, **registers):
        missing = set(self.stubs) - self.BOUNDARIES
        assert not missing, f"unobserved substitution addresses: {sorted(missing)}"
        return super().run(at, **registers)

    def archive_stubs(self):
        super().archive_stubs()
        load = self.stubs[0x43F50]

        def queue():
            self.queued.append(self.text(self.reg("edx")))
            load()

        def lookup():
            # The historic context hands back the file just queued. Other contexts (the stadium shot the home
            # setter asks for) find nothing: this harness loads no other resources.
            self.ret(0x2200040 if self.reg("ecx") == HISTORIC_CONTEXT else 0, 4)

        def sound():
            self.sounds += 1
            self.ret(0, 0x18)               # 89DA0 takes six stack arguments (ret 18h)

        def redraw():
            self.redraws += 1
            self.ret(0)
        self.stubs.update({0x43F50: queue, 0x449E0: lookup, 0x771F0: lambda: self.ret(self.side),
                           0x89DA0: sound, 0x31F010: redraw, 0x48B50: lambda: self.ret(self.draw)})

    def select(self, index=0):
        super().select(index)
        self.archive_stubs()

    # -- roster views
    def root(self):
        return self.r(0xB72918)

    def team(self, i):
        return self.r(self.root() + 0x1C) + 500 * i

    def index(self, team):
        count, base = self.r(self.root() + 0x18), self.r(self.root() + 0x1C)
        if not team or not base <= team < base + 500 * count or (team - base) % 500:
            return None
        return (team - base) // 500

    def view(self, team):
        if not team:
            return None
        text = lambda field: self.text(self.r(team + field)) if self.r(team + field) else None  # noqa: E731
        return {"index": self.index(team), "name": text(0x104), "abbr": text(0x108),
                "category": self.r(team + 0x128), "players": self.read(team + 0x11C, 1)[0],
                "identity": struct.unpack("<H", self.read(team + 0x118, 2))[0],
                "pointers": sum(bool(self.r(team + 4 * i)) for i in range(65))}

    def pool(self):
        """Spare player records (flag bit 0). BFF50 hands out one with bit 2 clear; an import marks it."""
        count, base = self.r(self.root()), self.r(self.root() + 4)
        flags = self.read(base, 84 * count)[8::84]
        spare = [f for f in flags if f & 1]
        return {"records": len(spare), "used": sum(1 for f in spare if f & 4)}

    def spare_slots(self):
        return [self.team(i) for i in range(self.r(self.root() + 0x18))
                if self.r(self.team(i) + 0x128) in (2, 4)]

    def last_resident(self):
        """The team before the first team in the Quick Game list: the last resident team."""
        return self.run(0x77950, ecx=self.team(0), edx=QUICK_GAME_MASK)

    # -- Team Select
    def team_select(self, home, away, flow=1):
        self.w(FLOW, flow)
        self.w(0xE5FF80, 4)                 # Quick Game's game mode (set at 2C20F3)
        self.run(0x2C1780, ecx=home)
        self.run(0x2C17C0, ecx=away)

    def press(self, side, direction):
        """One pad press: the real next (2C2240) or previous (2C2310) handler for that side's pad."""
        self.side = 1 if side == "home" else 2
        before = len(self.queued)
        self.run(0x2C2240 if direction > 0 else 0x2C2310, args=(0x2310000, 0))
        return {"home": self.view(self.r(HOME)), "away": self.view(self.r(AWAY)),
                "loaded": self.queued[before:], "pool": self.pool()}

    def random_step(self, side, draw):
        """One Random Team spin step: the real 2C1AC0 (home) or 2C1B10 (away) with a given random draw."""
        self.draw = draw
        before = len(self.queued)
        self.run(0x2C1AC0 if side == "home" else 0x2C1B10, args=(1,))
        return {"home": self.view(self.r(HOME)), "away": self.view(self.r(AWAY)), "loaded": self.queued[before:]}

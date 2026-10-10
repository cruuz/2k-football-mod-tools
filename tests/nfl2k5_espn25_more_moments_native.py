"""Native harness for 25 more Anniversary moments: the grown SITU and the new team files under the game's code.

The retail relocation (165EE0) and context setup (2CFD00) take the grown SITU chunk; 20C340/20C350/20C390 answer
for every row; 20CB30 selects a new moment through the option's search (20BD80) and loader call (2D17B0 with the
roster's historic list pointed at the moment table); C1030 (or the practice squad's importer) imports the new
files; 617E0/615A0/10C040 build the match. Archive reads of the new files are served by file name, as the retail
ones are. EXPERIMENTAL / UNWITNESSED: offline evidence, not a played game.
"""
from unicorn import UC_HOOK_CODE
from unicorn import x86_const as regs

from nfl2k5_espn25_in_game import LiveCPU, evidence  # noqa: F401  (evidence re-exported for the tests)

# The list's row-draw callbacks (registered in the list descriptor, .rdata 5293CC / 52947C / 52952C / 5295DC).
# kind -> (entry, the `call 2CFD40` sites that read a SITU record, where the cell has resolved what it will draw).
# A helmet cell stops at the helmet draw 20BDF0 with EDI = the team and EBX = the kit index.
ROW_CELLS = {
    "title": (0x20C800, (0x20C813,), 0x20C818),
    "home_helmet": (0x20C710, (0x20C71E, 0x20C740), 0x20BDF0),
    "away_helmet": (0x20C790, (0x20C79B,), 0x20BDF0),
}


class MomentsCPU(LiveCPU):
    """LiveCPU with a grown SITU chunk and extra historic files served by name."""

    def __init__(self, payload, resources, context, identities, *, situ_chunk, extra_files):
        self.situ_chunk = situ_chunk
        self.extra_files = dict(extra_files)
        self.extra_loads = []
        super().__init__(payload, resources, context, set(identities))

    def load_situ(self, wrapped):
        return super().load_situ(self.situ_chunk)

    def archive_stubs(self):
        super().archive_stubs()
        base_load = self.stubs[0x43F50]

        def load():
            filename = self.text(self.reg("edx"))
            if filename in self.extra_files:
                assert len(self.events) < 100, "archive event budget"
                self.events.append({"filename": filename, "outer": None})
                self.extra_loads.append(filename)
                self.write(0x2200000, self.extra_files[filename][32:])
                self.ret(1, 16)
            else:
                base_load()
        self.stubs[0x43F50] = load

    def draw_row(self, kind, row):
        """Run one row-draw callback of the Anniversary list for list row `row` up to the point where it has resolved
        its SITU record(s), and return what it resolved: the row each record read asked for (ECX at the call), the
        records, the first record's title and date texts and, for a helmet cell, the team and kit it would draw.
        Drawing itself is not executed."""
        entry, calls, stop = ROW_CELLS[kind]
        asked, records, seen, scratch = {}, {}, {"pending": None}, 0x2500000
        self.write(scratch, bytes(0x400))

        def hook(uc, at, size, data):
            if at in calls:
                seen["pending"] = at                     # the call site; the option's helper may remap ECX next
            elif at == 0x2CFD40 and seen["pending"] is not None:
                asked[seen["pending"]] = uc.reg_read(regs.UC_X86_REG_ECX)     # the row the record getter receives
                seen["pending"] = None
            elif at - 5 in calls:
                records[at - 5] = uc.reg_read(regs.UC_X86_REG_EAX)
            if at == stop and len(records) == len(calls):
                seen["edi"], seen["ebx"] = uc.reg_read(regs.UC_X86_REG_EDI), uc.reg_read(regs.UC_X86_REG_EBX)
                seen["stopped"] = True
                uc.emu_stop()
        handles = [self.uc.hook_add(UC_HOOK_CODE, hook, begin=0x20C700, end=0x20C900),
                   self.uc.hook_add(UC_HOOK_CODE, hook, begin=0x2CFD40, end=0x2CFD40),
                   self.uc.hook_add(UC_HOOK_CODE, hook, begin=0x20BDF0, end=0x20BDF0)]
        try:
            self.w(self.STACK, self.STOP)
            for name in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
                self.uc.reg_write(getattr(regs, "UC_X86_REG_" + name.upper()), 0)
            self.uc.reg_write(regs.UC_X86_REG_ECX, scratch)           # the cell's owner object
            self.uc.reg_write(regs.UC_X86_REG_EDX, scratch + 0x100)   # the list context (floats read as zero)
            for i, value in enumerate((0, 0, 0, 0, 0, row, 0)):       # six arguments: the row is the sixth
                self.w(self.STACK + 4 + i * 4, value)
            self.uc.reg_write(regs.UC_X86_REG_ESP, self.STACK)
            self.uc.emu_start(entry, self.STOP, count=self.instruction_budget)
        finally:
            for handle in handles:
                self.uc.hook_del(handle)
        assert seen.get("stopped"), f"row-draw callback {kind} did not reach {stop:#x}"
        order = sorted(calls)
        first = records[order[0]]
        result = dict(kind=kind, row=row, asked=[asked[c] for c in order], records=[records[c] for c in order],
                      title=self.text(self.r(first)), date=self.text(self.r(first + 0xC)))
        if kind != "title":
            team = seen["edi"]
            result.update(kit=seen["ebx"], team=self.text(self.r(team + 0x104)) if team else None,
                          code=self.text(self.r(team + 0x10C)) if team else None)
        return result

    def caption(self, row):
        return self.text(self.run(0x20C350, ecx=row)).replace("\n", " | ")

    def completed(self, row):
        return self.run(0x20C390, ecx=row)

    def win(self, row):
        """The won-moment path of 20C670 for this row: mode 8, not a replay, human side ahead."""
        self.w(0xBF1858, row)
        self.w(0xE5FF80, 8)
        self.w(0xE6014C, 0)
        self.w(0xBF1880, 0)                    # the copied record's human side: away
        self.stubs[0x77560] = lambda: self.ret(0)   # no active profile: the save call is skipped
        try:
            self.run(0x20C670, ecx=3, edx=7)   # ECX = home 3, EDX = away 7: the away side (the human) won
        finally:
            self.stubs.pop(0x77560, None)


class FastMomentsCPU(MomentsCPU):
    """MomentsCPU with code hooks only at the named boundaries, as the Team Select harness does: a click that imports
    two 53-player rosters runs in well under a second instead of several. Every substituted address must be named in
    BOUNDARIES (or added with watch()); an unwatched stub would never fire, so run() refuses it."""

    BOUNDARIES = frozenset({
        0xC1030, 0x2D1896, 0xC2300, 0xC240F,                    # LiveCPU's import/release observers
        0x43F50, 0x432D0, 0x449E0, 0x432F0,                     # archive boundary
        0xF3210, 0x6E390, 0xE3150, 0xF3580, 0x773F0,            # moment selection UI (select())
        0xE9460, 0x10BD60, 0xAF510, 0x9CBD0,                    # match staging spatial/clock seams
        0x77560, 0x1707C0, 0xF31B0,                             # the won-moment save, the list highlight restore
    })

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.uc.hook_del(self._code_hook)
        self._watched = set()
        self.watch(*self.BOUNDARIES)

    def watch(self, *addresses):
        for at in addresses:
            if at not in self._watched:
                self._watched.add(at)
                self.uc.hook_add(UC_HOOK_CODE, self._hook, begin=at, end=at)

    def run(self, at, **registers):
        watched = getattr(self, "_watched", None)
        if watched is not None:
            missing = set(self.stubs) - watched
            assert not missing, f"unwatched native substitution addresses: {sorted(hex(a) for a in missing)}"
        return super().run(at, **registers)

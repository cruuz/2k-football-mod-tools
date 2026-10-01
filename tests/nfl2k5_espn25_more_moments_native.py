"""Native harness for 25 more Anniversary moments: the grown SITU and the new team files under the game's code.

The retail relocation (165EE0) and context setup (2CFD00) take the grown SITU chunk; 20C340/20C350/20C390 answer
for every row; 20CB30 selects a new moment through the option's search (20BD80) and loader call (2D17B0 with the
roster's historic list pointed at the moment table); C1030 (or the practice squad's importer) imports the new
files; 617E0/615A0/10C040 build the match. Archive reads of the new files are served by file name, as the retail
ones are. EXPERIMENTAL / UNWITNESSED: offline evidence, not a played game.
"""
from nfl2k5_espn25_in_game import LiveCPU, evidence  # noqa: F401  (evidence re-exported for the tests)


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

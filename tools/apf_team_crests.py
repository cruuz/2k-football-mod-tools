#!/usr/bin/env python3
"""Which crest package belongs to which APF 2K8 team.

The crest writers take an outer archive entry index, which is the right thing
for a writer and the wrong thing to put in front of a modder.  Nobody knows
that the Americans wear ``uniform_logo_30.iff`` at outer entry 1133; they know
they want to edit the Philadelphia team.  This is the table that turns one into
the other, so the editor can offer twenty-four team names instead of a number.

Every row is derived from the disc, not from a list somebody typed:
``tools/apf_uniform_inventory.py`` resolves each team's selector slot 5 to a
``uniform_logo_NN.iff`` name, matches that name's CRC32 against the outer
archive, and reports the table index.  ``asset_index`` is the ``NN`` in the
package name and is also the catalog index the same crest occupies inside the
prebuilt ``uniform_logocache`` aggregate, which is why one number drives both
writers.

The eight online and eight user slots are deliberately absent: they all point
at ``uniform_logo_80`` (the Federals' crest) rather than owning one, so
offering them would imply an edit that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamCrest:
    """One built-in team and the crest package it wears."""

    team: str
    abbreviation: str
    asset_index: int      # the NN in uniform_logo_NN.iff, and the cache catalog index
    outer_entry_index: int

    @property
    def package_name(self) -> str:
        return f"uniform_logo_{self.asset_index:02d}.iff"

    @property
    def label(self) -> str:
        return f"{self.team} ({self.abbreviation}) - {self.package_name}"


TEAM_CRESTS: tuple[TeamCrest, ...] = (
    TeamCrest("Americans", "PHI", 30, 1133),
    TeamCrest("Assassins", "NJ", 1, 36),
    TeamCrest("Beasts", "CHI", 7, 830),
    TeamCrest("Cobras", "CAR", 68, 1328),
    TeamCrest("Cougars", "DEN", 21, 453),
    TeamCrest("Cyclones", "MIA", 77, 887),
    TeamCrest("Federals", "WAS", 80, 1281),
    TeamCrest("Firebirds", "DET", 32, 1185),
    TeamCrest("Gunslingers", "DAL", 56, 1371),
    TeamCrest("Indians", "MIL", 75, 1442),
    TeamCrest("Iron Men", "PIT", 87, 612),
    TeamCrest("Knights", "NY", 47, 112),
    TeamCrest("Legends", "LA", 88, 1390),
    TeamCrest("Minutemen", "BOS", 52, 106),
    TeamCrest("Red Dogs", "OH", 86, 529),
    TeamCrest("Rhinos", "STL", 66, 594),
    TeamCrest("Rollers", "LV", 85, 192),
    TeamCrest("Rustlers", "TEX", 82, 1041),
    TeamCrest("Sailors", "SEA", 83, 867),
    TeamCrest("Scorpions", "ARI", 67, 577),
    TeamCrest("Sharks", "SF", 69, 1346),
    TeamCrest("Top Guns", "TB", 31, 780),
    TeamCrest("Wasps", "ATL", 84, 209),
    TeamCrest("Werewolves", "MIN", 90, 173),
)

# The crest the writers have always defaulted to, kept so existing callers that
# pass nothing keep hitting exactly the target they used to.
DEFAULT_TEAM = "Assassins"


#: How many crest packages the game actually carries.  The twenty-four above are
#: the ones a built-in team wears; they are not the whole set.  APF ships
#: ``uniform_logo_00.iff`` through ``uniform_logo_117.iff``, and the
#: runtime-resident ``uniform_logocache`` catalogues every one --
#: ``tools/apf_logocache_patch.py`` has carried ``CATALOG_COUNT = 118`` all along.
#: The other ninety-four are the game's selectable logo library, the options its
#: own uniform editor cycles through.
#:
#: This is a different question from the sixteen absent team selectors noted in
#: the module docstring.  Those are *selectors* that alias to another team's
#: crest and own no art; these are real packages with their own.
CATALOG_SLOT_COUNT = 118


@dataclass(frozen=True)
class CrestSlot:
    """One crest package, whether or not a built-in team wears it."""

    asset_index: int
    outer_entry_index: int
    team: TeamCrest | None = None

    @property
    def package_name(self) -> str:
        return f"uniform_logo_{self.asset_index:02d}.iff"

    @property
    def is_team_crest(self) -> bool:
        return self.team is not None

    @property
    def label(self) -> str:
        if self.team is not None:
            return self.team.label
        return f"Logo slot {self.asset_index:02d} - {self.package_name}"


def crest_slots(index_path) -> tuple[CrestSlot, ...]:
    """Resolve every crest package in the user's own archive.

    Derived from the disc rather than typed out, for the same reason the team
    table is: a hand-written list of a hundred-odd entry indices is a list
    somebody can get wrong, and the archive already answers the question.  Names
    are stored only as a CRC32 of the uppercase filename, and the packages are
    scattered -- slot 0 sits at outer entry 363 while slot 30 is at 1133 -- so
    each is recovered by matching its checksum.

    Slots a built-in team wears carry that team; the rest are labelled by index.
    An unnamed slot is writable by the same writer, but it has no pinned retail
    hash, so it leans on the allocation-fit and decode-back checks rather than an
    exact source match.
    """

    import zlib

    import apf_outer

    archive = apf_outer.parse_archive(index_path)
    by_name_id: dict[int, int] = {}
    for entry in archive.entries:
        by_name_id.setdefault(entry.name_id & 0xFFFFFFFF, entry.table_index)

    teams_by_index = {row.asset_index: row for row in TEAM_CRESTS}
    slots: list[CrestSlot] = []
    for asset_index in range(CATALOG_SLOT_COUNT):
        name = f"uniform_logo_{asset_index:02d}.iff"
        checksum = zlib.crc32(name.upper().encode("ascii")) & 0xFFFFFFFF
        entry_index = by_name_id.get(checksum)
        if entry_index is None:
            continue
        slots.append(
            CrestSlot(asset_index, entry_index, teams_by_index.get(asset_index))
        )
    return tuple(slots)


def by_team(name: str) -> TeamCrest:
    for row in TEAM_CRESTS:
        if row.team.casefold() == name.casefold():
            return row
    raise KeyError(f"no APF built-in team named {name!r}")


def by_outer_entry(index: int) -> TeamCrest:
    for row in TEAM_CRESTS:
        if row.outer_entry_index == index:
            return row
    raise KeyError(f"no APF team crest at outer entry {index}")


def default_crest() -> TeamCrest:
    return by_team(DEFAULT_TEAM)


if __name__ == "__main__":
    for row in TEAM_CRESTS:
        print(f"{row.team:<12} {row.abbreviation:<5} {row.package_name:<22} "
              f"outer {row.outer_entry_index:>5}  catalog {row.asset_index:>3}")

"""Bounded census of consumers of the main roster's shared college indices.

Single-team disc ROSTs use main-table indices, not local relative pointers.
The shipped Anniversary datasets also reserve the names they will compile.
Main-roster players are checked separately by the main roster writer.
"""
from __future__ import annotations
from collections import defaultdict
from . import nfl2k5_roster_records as rr


def external_references(archive, colleges):
    from . import nfl2k5_espn25_rosters as esp
    from . import nfl2k5_espn25_more_moments as more
    references = defaultdict(list)
    def add(index, owner):
        rr._require(0 <= index < len(colleges), f'{owner}: college index outside main table')
        references[index].append(owner)
    for entry in archive.entries:
        if entry.index == rr.ROST_OUTER_INDEX or entry.size < 32:
            continue
        header = archive.read(entry.virtual_offset, 32)
        if header[:4] != b'ROST':
            continue
        rr._require(entry.size <= 1024 * 1024 and int.from_bytes(header[16:20], 'little') == 0,
                    'shared college census cannot inspect this ROST')
        document = rr.RosterDocument(archive.read(entry.virtual_offset + 32, entry.size - 32))
        if document.colleges:  # Independent local table, like a complete save.
            continue
        for player in document.players:
            add(player.record.values['college_pointer'], f'outer:{entry.index}/{player.pool}:{player.index}')
    _, sheets = esp.dataset()
    datasets = (('espn25_rosters', sheets), ('espn25_more_moments', more.Data.load().rosters))
    for owner, sheets in datasets:
        for key, rows in sheets.items():
            for n, row in enumerate(rows):
                name = row.get('college', '')
                if name:
                    rr._require(colleges.count(name) == 1,
                                f'{owner}: college must resolve exactly once in the main table: {name!r}')
                    add(colleges.index(name), f'{owner}:{key}/{n}')
    return dict(references)


def verify_table_edit(archive, before, after):
    """Refuse semantic changes under existing external indices before any write."""
    old, new = rr.RosterDocument(before), rr.RosterDocument(after)
    if old.colleges == new.colleges:
        return
    rr._require(len(old.colleges) == len(new.colleges), 'college table count changed')
    for index, consumers in external_references(archive, old.colleges).items():
        rr._require(old.colleges[index] == new.colleges[index],
                    f'college slot {index} ({old.colleges[index]!r}) is referenced by {consumers[0]}')

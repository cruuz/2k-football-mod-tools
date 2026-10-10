"""Native play-by-play probe for job c2: the game's own resolver and cue lookup, run under Unicorn on real disc data.

The instructions that run are the shipped ones: ``FUN_00067150`` (corrects the player's id for the situation and falls back to
the live uniform number) and ``FUN_000DB370`` (is a cue recorded for this class?), with the real ``players`` SPCI table and the
real ``default.xbe``. RAM is synthetic, no native leaf is substituted and nothing is played. It answers one question for any
roster record: which cue would the announcer be asked to play, in each of the four (announcer, real-player) modes.

Used by ``tools/b77/c2_repair.py --native-proof`` and by ``test_nfl2k5_commentary_final.py`` (private data: skipped without it).
"""
from __future__ import annotations

import collections
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
for _entry in (str(ROOT), str(ROOT / "tools")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from mod_editor.core import nfl2k5_commentary_final as final  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from nfl_outer import ALIGNMENT, HEADER_SIZE, PACK_SLOT_COUNT  # noqa: E402

MODES = ((0, 0), (0, 1), (1, 0), (1, 1))      # (announcer flag a0, "real player" flag a1) as the sequencer passes them
RESOLVER_VA = 0x67150
LOOKUP_VA = 0xDB370
BANK_HANDLE = 0xB34814                        # the players bank object the resolver asks
DOUBLE_ZERO = 9100
NO_CALL = 9999                                # the resolver's last resort: nothing recorded fits


class Probe:
    """One executable plus one players cue table in synthetic RAM."""

    def __init__(self, xbe: bytes, spci: bytes) -> None:
        from tests.nfl2k5_supersim_draft_fixture import Machine
        self.machine = Machine(xbe, trace_writes=False)
        base = self.machine.ARENA + 0x140000
        table = bytearray(spci)
        for field in (0x54, 0x58, 0x5C, 0x60, 0x68, 0x6C, 0x1BBC, 0x1BC0):
            relative = struct.unpack_from("<I", table, field)[0]
            if relative:
                struct.pack_into("<I", table, field, base + field + relative - 1)
        self.machine.uc.mem_write(base, bytes(table))
        self.machine.put(BANK_HANDLE, base)
        self.machine.put(BANK_HANDLE + 8, base + 0x50)
        self.player = self.machine.ARENA + 0x100000
        self.slot = self.machine.ARENA + 0x100200

    def resolve(self, record: bytes, announcer: int, real: int, *, line_cue: int | None = None) -> tuple[int, int]:
        """(class index, resolved cue) for one 0x54-byte player record. ``line_cue`` is the sequencer's edx (default: the id)."""
        assert len(record) == rr.PLAYER_SIZE
        self.machine.uc.mem_write(self.player, record)
        pbp = struct.unpack_from("<H", record, 4)[0]
        self.machine.put(self.slot, pbp)
        edx = pbp if line_cue is None else line_cue
        kind = self.machine.call(RESOLVER_VA, edx=edx, args=(announcer, real, self.slot, self.player))
        return kind, self.machine.get(self.slot)

    def recorded(self, cue: int, kind: int) -> bool:
        return bool(self.machine.call(LOOKUP_VA, ecx=BANK_HANDLE, edx=cue, args=(0, kind, 0)))


def classify(cue: int, pbp: int, jersey: int) -> str:
    """What the announcer would be asked to say for a resolved cue."""
    if cue == DOUBLE_ZERO:
        return "double_zero" if jersey != 100 else "double_zero_100"
    if cue == NO_CALL:
        return "no_call"
    if rr.PBP_NUMBER_BASE <= cue < rr.PBP_NUMBER_BASE + 100:
        n = cue - rr.PBP_NUMBER_BASE
        if n != jersey:
            return "number_wrong"
        return "zero_clip" if n == 0 else "number"
    return "name" if cue == pbp else "other"


def spci_variant(table: bytes, variant: str) -> bytes:
    """The real table as it is, or forced to the retail (9100 present) or applied (9100 retired) form."""
    if variant == "as_is":
        return table
    array = list(final.ids(table))
    out = bytearray(table)
    at = final.ID_TABLE_OFFSET + 2 * final.EXPECTED_ID_INDEX
    wanted = final.OLD_CUE if variant == "retail" else final.NEW_CUE
    assert array[final.EXPECTED_ID_INDEX] in (final.OLD_CUE, final.NEW_CUE)
    struct.pack_into("<H", out, at, wanted)
    return bytes(out)


def read_pack_resources(paths: dict[int, Path]) -> tuple[list[dict], bytes]:
    """Every ROST resource inside the given loose packs (pack ordinals as in the outer directory), and the players SPCI table."""
    fds = {ordinal: os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)) for ordinal, path in paths.items()}
    try:
        head = os.pread(fds[0], HEADER_SIZE, 0)
        count, _reserved, populated = struct.unpack_from("<3I", head)
        directory = os.pread(fds[0], 12 * count, HEADER_SIZE)
        blocks = struct.unpack_from(f"<{PACK_SLOT_COUNT}I", head, 12)
        spans, virtual = [], 0
        for ordinal in range(populated):
            spans.append((virtual, blocks[ordinal] * ALIGNMENT))
            virtual += blocks[ordinal] * ALIGNMENT
        out, table = [], b""
        for index in range(count):
            name_id, size, offset_blocks = struct.unpack_from("<III", directory, 12 * index)
            virtual_offset = offset_blocks * ALIGNMENT
            for ordinal, (start, span) in enumerate(spans):
                if ordinal in fds and start <= virtual_offset and virtual_offset + size <= start + span:
                    break
            else:
                continue
            local = virtual_offset - start
            if index == final.SPCI_OUTER_INDEX:
                entry = os.pread(fds[ordinal], size, local)
                at = final.find_table(entry)
                table = entry[at: at + final.SPCI_SIZE]
            if size > rr.RESOURCE_HEADER_SIZE and os.pread(fds[ordinal], 4, local) == b"ROST" and size <= 0x92060:
                out.append({"index": index, "name_id": name_id, "pack": ordinal, "size": size,
                            "raw": os.pread(fds[ordinal], size, local)})
        return out, table
    finally:
        for fd in fds.values():
            os.close(fd)


def audit_resources(resources: list[dict], probe: Probe) -> dict:
    """Run the resolver over every named player record of the given ROST resources."""
    counts: collections.Counter = collections.Counter()
    by_pack: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    offenders: list[dict] = []
    players = 0
    for resource in resources:
        raw = resource["raw"]
        document = rr.load_body(raw[rr.RESOURCE_HEADER_SIZE:])
        for player in document.players:
            if not (player.first or player.last) or "*" in player.first + player.last:
                continue
            players += 1
            record = raw[rr.RESOURCE_HEADER_SIZE + player.offset: rr.RESOURCE_HEADER_SIZE + player.offset + rr.PLAYER_SIZE]
            pbp, jersey = player.record.values["pbp_id"], player.record.values["jersey"]
            labels = {classify(probe.resolve(record, a0, a1)[1], pbp, jersey) for a0, a1 in MODES}
            for label in labels:
                counts[label] += 1
                by_pack[str(resource["pack"])][label] += 1
                if label in ("double_zero", "number_wrong", "no_call", "other") and len(offenders) < 40:
                    offenders.append({"outer_entry": resource["index"], "player": player.display, "jersey": jersey,
                                      "pbp_id": pbp, "label": label})
    return {"players": players, "labels": dict(counts), "by_pack": {k: dict(v) for k, v in sorted(by_pack.items())},
            "double_zero_players": counts["double_zero"], "wrong_number_players": counts["number_wrong"],
            "no_call_players": counts["no_call"], "zero_clip_players": counts["zero_clip"], "offenders": offenders}


def audit_packs(paths: dict[int, Path], xbe_path: Path, *, spci: str = "retail") -> dict:
    """The audit over loose packs with the game's executable. ``spci``: retail (9100 present: tests the DATA), applied (cue retired)."""
    resources, table = read_pack_resources(paths)
    probe = Probe(Path(xbe_path).read_bytes(), spci_variant(table, spci))
    result = audit_resources(resources, probe)
    result.update({"spci": spci, "resources": len(resources), "native_leaf_substitutions": list(probe.machine.leaves)})
    return result

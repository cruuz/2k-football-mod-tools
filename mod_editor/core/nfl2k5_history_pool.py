"""Franchise career history pool: whole career totals and no full-pool stall (job b780 hist1). A 2004 bug fix.

What the 2004 game does (static RE of the USA ``default.xbe``, then the real code under Unicorn)
------------------------------------------------------------------------------------------------
Every season stat a franchise keeps is one 32-bit word in the roster's history pool (``root+0x44``, used count
``root+0x40``; capacity ``FUN_0014E7E0``: 50,000 words in a 35+ team league, 20,000 otherwise; the pool sits inside the
ROST arena, +0x62CC8 in the 0xCA000 arena). The writer ``FUN_0014F220`` inserts each new word at the head of the
player's stream (``0x14E8B0``: a byte-wise memmove of the whole pool tail, then every player's pointer). When the pool
is full it runs, on every single write, the compaction ``0x14E9D0`` and then the fold ``0x14EFE0`` at the oldest
season level present. The fold moves each old word one slot up into the next season (sum, or max for ten fields,
rule table 0xAA26C0), compacting the whole pool once per merged word, and stores the sum in one signed 16-bit cell
with no overflow check.

So a long career wraps: the v0.9 franchise's own fold took Aaron Rodgers' career passing yards from 66,267 to 1,065
in season one (HUNT4). A long retail franchise wraps the same way (Favre, Testaverde, Landeta, Feagles in the 2004
roster). And once the pool is full every write pays the collection: a franchise week spends most of its time in the
byte-wise memmove (MC1: 66 % of a MyCareer week at 0x31060).

What this owner changes (in place, inside the engine's own bytes: no cave, no new section, no RW data)
------------------------------------------------------------------------------------------------------
* The fold never wraps. A merge whose 16-bit sum would leave -32,768..32,767 is not made: that old word stays where it
  is. The rest of the career still folds around it, so the career total stays exact and the long careers keep their
  overflow as one more folded row.
* No collection on every write. When the pool is full, ``gc_chunk`` (the full-pool path of 0x14F220) frees the deleted
  words, then folds whole season levels, oldest first, until 6,000 words (about half a season) are free. It never
  folds at depth < 3, so the current and the last season always keep their own rows.
* The compaction is one pass over the pool (pointer fixups from a 256-word block table on the stack) instead of one
  memmove of the pool tail per deleted run; the fold deletes in place and compacts once per level, not once per word.
* The writer's insert moves the pool tail with ``rep movsd`` instead of the byte loop (same result, about 4x fewer
  iterations).

The pool stays 50,000 words: no save, arena or memory change, so v0.8 and v0.9 franchise saves load as they are (their
full pools collect and fold the new way; a career total the old fold already wrapped stays as it was saved).

What the player sees: the old seasons fold into the career row the way the 2004 game does, and a few long careers
(the QBs and punters past 32,767 yards) show one extra "--" row. Career totals on the Player Card and in the history
screens are whole.

Sites (``nfl2k5_history_pool_code.SITES``, linked at their own addresses from ``tools/nfl2k5_history_pool/runtime.S``):
A 0x14E8B0 insert, B 0x14E930 gc_chunk (the old remove: only the old compaction called it), C 0x14E9D0 compaction and
helpers, D 0x14EFE0 fold, E 0x14F16F (``ret`` after the rule-table load at 0x14F168, which keeps its retail bytes or
the honors owner's call), F 0x14F249 (the full-pool path of 0x14F220). The only callers of 0x14E8B0, 0x14E930,
0x14E9D0 and 0x14EFE0 in the whole executable are inside the engine (checked by a call scan).

Coexistence: ``nfl2k5_defensive_try`` pins the whole engine (0x14E7E0, 3,216 bytes) and ``nfl2k5_honors`` pins the
fold's first 0x188 bytes and the writer; both restore these sites' retail bytes before hashing, only while this owner
reads exactly applied (``applied_sites``, ``compatible_edits``). The honors fold rule (0x14F168) is still the rule the
fold uses for every field below 87; fields 87 and up (TEAM, the honors and the pressure counters) sum.

Evidence: tests/mod_editor/test_b780_hist1_history_pool.py (the fold, the collection and the old saves under Unicorn
on the retail engine and on real franchise pools). Not witnessed in game.
"""
from __future__ import annotations

import hashlib

from . import nfl2k5_history_pool_code as runtime
from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_history_pool"
EVIDENCE = "UNWITNESSED"
BUILD_CAPTION = "Career history: whole totals, no full-pool slowdown"
HELP_TEXT = ("Fixes a 2004 franchise bug. When the career history fills up, the game folds old seasons into one row "
             "and long careers wrap (a QB's 66,267 career yards became 1,065), and every stat write then runs a slow "
             "cleanup. This keeps career totals whole and cleans up 6,000 entries at a time. Old seasons still fold "
             "into the career row as in the 2004 game; a few long careers show one extra \"--\" row.")
SITES = tuple(runtime.SITES)
CHUNK_WORDS = 6000
MIN_DEPTH = 3
CAPACITY_WORDS = 50000


def _digest(sites) -> str:
    h = hashlib.sha256()
    for label, va, before, after in sites:
        h.update(label.encode("ascii") + va.to_bytes(4, "little") + before + after)
    return h.hexdigest()


PATCHED_SHA256 = "af2e761f12729b101c019df26b5298a8d8067af80dce325ba2b6dc7133acb1d2"   # the six sites (label, VA, retail, patched); tests check it


def status(payload: bytes) -> str:
    """``retail`` | ``applied`` | ``foreign`` for a default.xbe image. There is no earlier release of this owner."""

    return rdata.status(payload, SITES)


def apply(payload: bytes):
    """(patched payload, receipt). Refuses an executable whose sites are neither retail nor exactly this owner's."""

    result, receipt = rdata.apply(payload, SITES, "history pool")
    return result, {"owner": OWNER, "status": status(result), **dict(receipt)}


def applied_sites(image) -> list[tuple[str, int, bytes, bytes]]:
    """``SITES`` when every site of an :class:`XbeImage` reads exactly this owner's bytes, else []. The honors owner
    masks these (restores their retail bytes) before it hashes the fold and the writer it pins."""

    try:
        if all(image.read(va, len(after)) == after for _label, va, _before, after in SITES):
            return list(SITES)
    except (ValueError, IndexError, KeyError):
        pass
    return []


def compatible_edits(payload: bytes) -> list[tuple[int, bytes]]:
    """[(VA, retail bytes)] of every site while this owner is exactly applied, else []. ``nfl2k5_defensive_try``
    restores them before it hashes its pinned history-engine context: this owner keeps the engine's interface (the
    writer, the getters and setters defensive_try calls are untouched; field 59 folds by the retail rule)."""

    if status(payload) != "applied":
        return []
    return [(va, before) for _label, va, before, _after in SITES]


def verify(payload: bytes) -> dict:
    return {"owner": OWNER, "status": status(payload), "experimental": False, "runtime_witnessed": False,
            "sites": [{"label": label, "va": f"0x{va:x}", "bytes": len(after)} for label, va, _b, after in SITES],
            "chunk_words": CHUNK_WORDS, "min_fold_depth": MIN_DEPTH, "capacity_words": CAPACITY_WORDS,
            "patched_sha256": PATCHED_SHA256}


__all__ = ["OWNER", "BUILD_CAPTION", "HELP_TEXT", "SITES", "CHUNK_WORDS", "MIN_DEPTH", "status", "apply",
           "applied_sites", "compatible_edits", "verify"]

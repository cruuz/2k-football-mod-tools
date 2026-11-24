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
reads exactly applied or previous (``applied_sites``, ``compatible_edits``). The honors fold rule (0x14F168) is still
the rule the fold uses for every field below 87; fields 87 and up (TEAM, the honors and the pressure counters) sum.

The last resort before a dropped write (b81 history-pool, Noah 11/23: "fix the history storage for franchise now")
----------------------------------------------------------------------------------------------------------------
v0.9's collection could fold only seasons 3+ years old. Once every word of a full pool was in the current season, the
last one or the folded career row, a new stat word was dropped: seed 68003's 2029 kept Trey Smack's 52-yard make and
lost its attempt (1 made of 0 attempted); the pool was full at 4 of 40 simulated closing saves. Now, when depth 3+
leaves the pool full, ``gc_chunk`` folds the last season into the career row for the men on the game's free-agent list
(root+0x38/0x3C) and nobody else (``fa_fold`` marks them in a 4,096-bit bitmap on the stack, then ``fold`` with depth
-2 asks ``fold_base`` one bit per man), and only then drops the write (``history_drop``, 0x14F256). Club men (active list, injured reserve, practice squad) keep their last season; a free
agent's last season joins his career row (his totals stay whole). While depth 3+ leaves the write room nothing runs
that writes memory, so every franchise that never reaches this point is byte-identical to v0.9's.

Revisions: ``SITES`` is this release; ``PREVIOUS_SITES`` is the beta-80 / v0.9 revision (shipped on the v0.9 disc and
written by every earlier Studio), which reads ``previous`` and is upgraded in place by ``apply`` (``UPGRADE_SITES``).

Evidence: tests/mod_editor/test_b780_hist1_history_pool.py (the fold, the collection and the old saves under Unicorn
on the retail engine and on real franchise pools; the last resort on a synthetic full pool and on a stored full
franchise image). Not witnessed in game.
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
             "into the career row as in the 2004 game; a few long careers show one extra \"--\" row. If the history "
             "is still full, a free agent's last season joins his career row before a new stat would be lost.")
SITES = tuple(runtime.SITES)
CHUNK_WORDS = 6000
MIN_DEPTH = 3
FREE_AGENT_DEPTH = 2           # b81: the last resort folds depth 2, free agents only
CAPACITY_WORDS = 50000
DROP_VA = 0x0014F256           # history_drop: a write the full pool still cannot take returns here unwritten


def _digest(sites) -> str:
    h = hashlib.sha256()
    for label, va, before, after in sites:
        h.update(label.encode("ascii") + va.to_bytes(4, "little") + before + after)
    return h.hexdigest()


PATCHED_SHA256 = "2b34685900f874735e6009599d434f38913f16eb13b8e89b202f998e245661bb"   # the six sites (label, VA, retail, patched); tests check it

# b81 history-pool: the beta-80 / v0.9 revision (b780 hist1 as shipped): (label, VA, patched bytes). Each lies at the
# start of the same site of this release, which is at least as long, so its retail bytes are the first bytes of ours.
PREVIOUS_PATCHED = (
    ('site_a', 0x0014E8B0, bytes.fromhex(
        "56578b0d1829b7008b414089fe2b7144c1fe0289c129f17e0b8d748ffc8d3c8ffdf3a5fc5f8b351829b7008b0e8b5604"
        "85c97e0f397a2c760483422c0483c25449ebedff4640b8010000005ec3"
    )),
    ('site_b', 0x0014E930, bytes.fromhex(
        "60ff35987fbd00c705987fbd00000000006a01e888000000e87302000089c3e88cfeffff8b0d1829b7002d7017000039"
        "41407e0e83fb037c0953e8710600004bebdd8f05987fbd00e863feffff8b0d1829b70031d23941400f9cc28954241c61"
        "c3"
    )),
    ('site_c', 0x0014E9D0, bytes.fromhex(
        "5553565781ec08020000a11829b7008b48408b704485c90f8ef500000081f9000001000f87e9000000898c2400020000"
        "31d231db84db750989dfc1ef086689147cf7049e000000107401424339cb72e485d20f84ba00000089d5a11829b7008b"
        "088b580485c97e608b432c29f07253c1e8023b842400020000734789c28b3c96f7c700000010741785ff780a423b9424"
        "0002000072e7c7432c00000000eb2389c2c1ea080fb73c54c1e20839c2730df704960000001074014742ebefc1e70229"
        "7b2c83c35449eb9c8b8c240002000031d289f731db8b0496a900000010750e890783c70431db85c0781443eb1185c079"
        "0d85db7409814ffc0000008031db4239ca72d2a11829b700296840b801000000eb0231c081c4080200005f5e5b5dc204"
        "00528b1081ca00000010891085d279218b512c39d0761383e804f7000000001075f1810800000080eb07c7412c000000"
        "005ac3e8b8fcffff8b0d1829b7003941407c17506a00e895feffff598b151829b700394a407c0931c0c3b801000000c3"
        "b802000000c3"
    )),
    ('site_d', 0x0014EFE0, bytes.fromhex(
        "5553565783ec14a11829b7008b4840894c2404c7042400000000a11829b7008b0c243b080f8d3a0100006bc954034804"
        "894c24088b5124c1ea0883e21f8954240c8b442408beff00000089f2e86ff8ffff85c00f840301000089c38b0b89cfc1"
        "ef1783e71f8b54240c29fa3b5424280f8cd4000000c1e91083e17f89ce47578b4c240c89f2e8b6fdffff89c531c985c0"
        "74030fbf080fbf1383fe5773155152e8e40000005a5985c0750839d17d1789d1eb1301d18d81008000003dffff00000f"
        "8784000000894c241085ed754685c97468e86dfaffff85c0746f83f8020f845effffff8b4c240889d8e823faffff89fa"
        "c1e20709f2c1e2100fb744241009c281ca000000408b4c2408e832010000e92effffff85c9750d8b4c240889e8e8eff9"
        "ffffeb158b4500250000ffff0fb7c909c80d000000408945008b4c240889d8e8cdf9ffffe9f8feffff89d8beff000000"
        "89f2e849f7ffffe9f5feffffff0424e9b6feffff6a00e885f8ffffa11829b7008b484031c0394c24040f97c083c4145f"
        "5e5b5dc20400"
    )),
    ('site_e', 0x0014F16F, bytes.fromhex(
        "c3"
    )),
    ('site_f', 0x0014F249, bytes.fromhex(
        "e8e2f6ffff85c00f85650000005f5e5d59c3"
    )),
)
PREVIOUS_SITES = tuple((label, va, before[:len(old)], old)
                       for (label, va, before, _after), (label_old, va_old, old) in zip(SITES, PREVIOUS_PATCHED)
                       if (label, va) == (label_old, va_old) and len(old) <= len(before))
PREVIOUS_SHA256 = "12f8f431af15622399a453dc937f869a5fc5c8956f9769d6190c9634c2ce3373"   # beta-80's PATCHED_SHA256
# What a previous install holds over each of this release's spans (its bytes, then retail to our length), and the
# in-place upgrade: only the spans whose bytes change.
_PREVIOUS_SPANS = tuple((label, va, before, old + before[len(old):])
                        for (label, va, before, _after), (_l, _v, _b, old) in zip(SITES, PREVIOUS_SITES))
UPGRADE_SITES = tuple((label, va, was, after) for (label, va, _before, was), (_l, _v, _b, after)
                      in zip(_PREVIOUS_SPANS, SITES) if was != after)
if len(PREVIOUS_SITES) != len(SITES) or _digest(PREVIOUS_SITES) != PREVIOUS_SHA256:
    raise ImportError("nfl2k5_history_pool: the beta-80 revision does not match its pin")


def status(payload: bytes) -> str:
    """``retail`` | ``applied`` | ``previous`` (the beta-80 / v0.9 revision) | ``foreign`` for a default.xbe image."""

    state = rdata.status(payload, SITES)
    if state == "foreign" and rdata.status(payload, _PREVIOUS_SPANS) == "applied":
        return "previous"
    return state


def apply(payload: bytes):
    """(patched payload, receipt). Retail and previous become applied (previous in place: only the changed spans);
    refuses an executable whose sites are neither retail, previous nor exactly this owner's."""

    state = status(payload)
    if state == "previous":
        result, receipt = rdata.apply(payload, UPGRADE_SITES, "history pool (beta-80 revision)")
        receipt = {**dict(receipt), "upgraded_from": "previous"}
    else:
        result, receipt = rdata.apply(payload, SITES, "history pool")
    if status(result) != "applied":
        raise rdata.RdataSiteError("history pool: post-apply verification failed")
    return result, {"owner": OWNER, "status": status(result), **dict(receipt)}


def _installed_sites(read) -> list[tuple[str, int, bytes, bytes]]:
    for sites in (SITES, PREVIOUS_SITES):
        try:
            if all(read(va, len(after)) == after for _label, va, _before, after in sites):
                return list(sites)
        except (ValueError, IndexError, KeyError):
            return []
    return []


def applied_sites(image) -> list[tuple[str, int, bytes, bytes]]:
    """``SITES`` when every site of an :class:`XbeImage` reads exactly this owner's bytes, ``PREVIOUS_SITES`` when every
    site reads the beta-80 revision, else []. The honors owner masks these (restores their retail bytes) before it
    hashes the fold and the writer it pins."""

    return _installed_sites(image.read)


def compatible_edits(payload: bytes) -> list[tuple[int, bytes]]:
    """[(VA, retail bytes)] of every site while this owner is exactly applied (or exactly the beta-80 revision), else [].
    ``nfl2k5_defensive_try`` restores them before it hashes its pinned history-engine context: this owner keeps the
    engine's interface (the writer, the getters and setters defensive_try calls are untouched; field 59 folds by the
    retail rule)."""

    state = status(payload)
    sites = SITES if state == "applied" else PREVIOUS_SITES if state == "previous" else ()
    return [(va, before) for _label, va, before, _after in sites]


def verify(payload: bytes) -> dict:
    return {"owner": OWNER, "status": status(payload), "experimental": False, "runtime_witnessed": False,
            "sites": [{"label": label, "va": f"0x{va:x}", "bytes": len(after)} for label, va, _b, after in SITES],
            "chunk_words": CHUNK_WORDS, "min_fold_depth": MIN_DEPTH, "free_agent_fold_depth": FREE_AGENT_DEPTH,
            "capacity_words": CAPACITY_WORDS, "drop_va": f"0x{DROP_VA:x}", "patched_sha256": PATCHED_SHA256,
            "previous_sha256": PREVIOUS_SHA256}


__all__ = ["OWNER", "BUILD_CAPTION", "HELP_TEXT", "SITES", "PREVIOUS_SITES", "UPGRADE_SITES", "CHUNK_WORDS",
           "MIN_DEPTH", "FREE_AGENT_DEPTH", "DROP_VA", "status", "apply", "applied_sites", "compatible_edits", "verify"]

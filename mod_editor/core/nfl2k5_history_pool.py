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
the honors owner's call), F 0x14F249 (the full-pool path of 0x14F220), G 0x14F239 (the writer's capacity call), H
0x14EDA8 (the end of 0x14ED90) and I 0x14F170 (the retail fold's dead tail, cut off by site D). The only callers of
0x14E8B0, 0x14E930, 0x14E9D0 and 0x14EFE0 in the whole executable are inside the engine (checked by a call scan).

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
-2 asks ``fold_base`` one bit per man and goes straight past every other man; with the pool full it only merges, the
way a word the 16-bit cell cannot hold stays where it is), and only then drops the write (``history_drop``, 0x14F256). Club men (active list, injured reserve, practice squad) keep their last season; a free
agent's last season joins his career row (his totals stay whole). While depth 3+ leaves the write room nothing runs
that writes memory, so every franchise that never reaches this point is byte-identical to v0.9's.

The playoff reserve (coordinator's ruling on the history-pool report, 11/24): in a ten-season panel the pool first ran
out in the 2028 playoffs and then in every playoffs, where postseason stat words (wiped at the offseason rollover)
took the last words and the season's Super Bowl champion, Super Bowl MVP and Pro Bowl honors (about 134 regular-class
words, written in the same window) were lost every season, in v0.9 and with the free-agent resort alike. Now a new
playoff word (postseason class while the franchise stage is 9) may not take one of the last ``PLAYOFF_RESERVE`` (512)
words: the writer's capacity test (site G, 0x14F239) calls ``reserve_cap`` (site A's tail), so such a word reaches
``gc_chunk`` 512 words before the pool is full; ``gc_chunk`` runs the same depth 3+ collection as for any full-pool
write and keeps the word only if 512 words stay free. Preseason games write the postseason class too (stage 7); they see
the whole capacity, as in v0.9, since filling the pool with them is what triggers v0.9's yearly collection. No
postseason-class word runs the free-agent resort, and the free-agent resort runs only in stages 8 and 9 (never in the
preseason, after the rollover, where the star career reads the season just played). Regular-class writes see the whole
capacity as before.

The playoff fold (coordinator's second ruling, 11/24): the reserve alone kept 3.6 % of the playoff stat words the
stats screens' postseason views show until the rollover (v0.9 about 28 %). A playoff word that still has no room
outside the reserve after the depth 3+ collection now runs ``fold`` with ``PLAYOFF_FOLD``: every man's career row (two
seasons back) merges into his last season, the merge v0.9's first collection of the next preseason makes, only
earlier; 11,547 words on the stored full 68001/2032 pool, a playoffs needs about 4,300. It leaves the fields the
Studio's season close reads per season (``CLOSE_FIELDS``: games, club and the ten leader fields of
``nfl2k5_history``'s ``read_career``), so club leaders, the Hall of Fame seasons count and main club come out exactly as
with v0.9's bytes. At the rollover's postseason wipe (0x247B40 calls 0x14ED90 for every record with class 1, the first
record first, after advancing years pro and after the close) site H's ``rollover_tail`` finishes the merge for every
man folded early (``fold`` with ``COMPLETE_FOLD``), as v0.9's next preseason collection would; when nobody was folded
early it does nothing.

Revisions: ``SITES`` is this release. ``REVISIONS`` holds the earlier ones, each pinned: the beta-80 / v0.9 revision
(``PREVIOUS_SITES``: shipped on the v0.9 disc and written by every earlier Studio), the first b81 revision 570cd7c16
(``REVISION_570CD7C16_SITES``: the free-agent resort without the reserve) and the second, 26d92bde0
(``REVISION_26D92BDE0_SITES``: the reserve without the playoff fold). Each reads ``previous`` and ``apply`` upgrades it
in place (``UPGRADE_SITES``, ``UPGRADE_570CD7C16_SITES``, ``UPGRADE_26D92BDE0_SITES``) to exactly a fresh install.

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
             "is still full, a free agent's last season joins his career row before a new stat would be lost; in the "
             "playoffs every player's older seasons join his last season early (as the next preseason would) so "
             "playoff stats are kept, with room left for the season's honors.")
SITES = tuple(runtime.SITES)
CHUNK_WORDS = 6000
MIN_DEPTH = 3
FREE_AGENT_DEPTH = 2           # b81: the last resort folds depth 2, free agents only
PLAYOFF_RESERVE = 512          # b81: words a new playoff (postseason-class) word may not take (runtime.S RESERVE)
PLAYOFF_FOLD_DEPTH = 2         # b81: the playoff fold merges every man's career row into his last season ...
PLAYOFF_ROOM = 4096            # round 4: ... free agents first, then the rest, until this much is free besides the reserve
HONOR_FIELDS = tuple(range(96, 106))   # round 4: no early fold (a negative depth) merges the honors
CLOSE_FIELDS = (0, 2, 3, 8, 9, 12, 13, 14, 18, 19, 20, 87)   # ... but these (nfl2k5_history read_career, per season)
CAPACITY_WORDS = 50000
DROP_VA = 0x0014F256           # history_drop: a write the full pool still cannot take returns here unwritten


def _digest(sites) -> str:
    h = hashlib.sha256()
    for label, va, before, after in sites:
        h.update(label.encode("ascii") + va.to_bytes(4, "little") + before + after)
    return h.hexdigest()


PATCHED_SHA256 = "9e8e9f792d6734174f875473f2eea789fb312462d28318f18dee7c37ac78ec5d"   # the ten sites (label, VA, retail, patched); tests check it

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
# b81 history-pool: the first b81 revision (570cd7c16: the free-agent last resort without the playoff reserve). It was
# never merged, but the coordinator's ruling asks that it upgrade in place like the shipped one.
REVISION_570CD7C16_PATCHED = (
    ('site_a', 0x0014E8B0, bytes.fromhex(
        "56578b0d1829b7008b414089fe2b7144c1fe0289c129f17e0b8d748ffc8d3c8ffdf3a5fc5f8b351829b7008b0e8b5604"
        "85c97e0f397a2c760483422c0483c25449ebedff4640b8010000005ec3"
    )),
    ('site_b', 0x0014E930, bytes.fromhex(
        "60ff35987fbd00c705987fbd00000000006a01e888000000e87302000089c3e88cfeffff8b0d1829b7002d7017000039"
        "41407e0e83fb037c0953e8710600004bebdde869feffff8b0d1829b7003941407c05e8d40800008f05987fbd00e84efe"
        "ffff8b0d1829b70031d23941400f9cc28954241c61c3"
    )),
    ('site_c', 0x0014E9D0, bytes.fromhex(
        "5553565781ec08020000a11829b7008b48408b704485c90f8ef500000081f9000001000f87e9000000898c2400020000"
        "31d231db84db750989dfc1ef086689147cf7049e000000107401424339cb72e485d20f84ba00000089d5a11829b7008b"
        "088b580485c97e608b432c29f07253c1e8023b842400020000734789c28b3c96f7c700000010741785ff780a423b9424"
        "0002000072e7c7432c00000000eb2389c2c1ea080fb73c54c1e20839c2730df704960000001074014742ebefc1e70229"
        "7b2c83c35449eb9c8b8c240002000031d289f731db8b0496a900000010750e890783c70431db85c0781443eb1185c079"
        "0d85db7409814ffc0000008031db4239ca72d2a11829b700296840b801000000eb0231c081c4080200005f5e5b5dc204"
        "00528b1081ca00000010891085d279218b512c39d0761383e804f7000000001075f1810800000080eb07c7412c000000"
        "005ac3e8b8fcffff8b0d1829b7003941407c1e837c242c007c14506a00e88efeffff598b151829b700394a407c0931c0"
        "c3b801000000c3b802000000c38b5124c1ea0883e21f8b44242c85c079208d14428b4424043d0010000073070fa34424"
        "30720bc7442410c0ffffff31c0c389542410b801000000c3"
    )),
    ('site_d', 0x0014EFE0, bytes.fromhex(
        "5553565783ec14a11829b7008b4840894c2404c7042400000000a11829b7008b0c243b080f8d3a0100006bc954034804"
        "894c2408e844fbffff85c00f841b0100008b442408beff00000089f2e86ff8ffff85c00f840301000089c38b0b89cfc1"
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
        "e8e2f6ffff85c00f85650000005f5e5d59c381ec0002000089e731c0b980000000f3ab8b351829b7008b4e388b5e3c8b"
        "7604bd5400000049781c8b048b29f072f631d2f7f585d275ee3d0010000073e70fab0424ebe16afee83afdffff81c400"
        "020000c3"
    )),
)

# b81 history-pool: the second b81 revision (26d92bde0: the playoff reserve without the playoff fold). Never merged;
# the coordinator's ruling (11/24, second round) asks that it upgrade in place like the others.
REVISION_26D92BDE0_PATCHED = (
    ('site_a', 0x0014E8B0, bytes.fromhex(
        "56578b0d1829b7008b414089fe2b7144c1fe0289c129f17e0b8d748ffc8d3c8ffdf3a5fc5f8b351829b7008b0e8b5604"
        "85c97e0f397a2c760483422c0483c25449ebedff4640b8010000005ec3e8defeffff833d987fbd0000740e833da476e5"
        "000975052d00020000c3"
    )),
    ('site_b', 0x0014E930, bytes.fromhex(
        "60ff35987fbd00c705987fbd00000000006a01e888000000e87302000089c3e88cfeffff8b0d1829b7002d7017000039"
        "41407e0e83fb037c0953e8710600004bebdd833c24007515e863feffff8b0d1829b7003941407c05e8ce0800008f0598"
        "7fbd00e865ffffff8b0d1829b70031d23941400f9cc28954241c61c3"
    )),
    ('site_c', 0x0014E9D0, bytes.fromhex(
        "5553565781ec08020000a11829b7008b48408b704485c90f8ef500000081f9000001000f87e9000000898c2400020000"
        "31d231db84db750989dfc1ef086689147cf7049e000000107401424339cb72e485d20f84ba00000089d5a11829b7008b"
        "088b580485c97e608b432c29f07253c1e8023b842400020000734789c28b3c96f7c700000010741785ff780a423b9424"
        "0002000072e7c7432c00000000eb2389c2c1ea080fb73c54c1e20839c2730df704960000001074014742ebefc1e70229"
        "7b2c83c35449eb9c8b8c240002000031d289f731db8b0496a900000010750e890783c70431db85c0781443eb1185c079"
        "0d85db7409814ffc0000008031db4239ca72d2a11829b700296840b801000000eb0231c081c4080200005f5e5b5dc204"
        "00528b1081ca00000010891085d279218b512c39d0761383e804f7000000001075f1810800000080eb07c7412c000000"
        "005ac3e8b8fcffff8b0d1829b7003941407c1e837c242c007c14506a00e88efeffff598b151829b700394a407c0931c0"
        "c3b801000000c3b802000000c38b5124c1ea0883e21f8b44242c85c079208d14428b4424043d0010000073070fa34424"
        "30720bc7442410c0ffffff31c0c389542410b801000000c3"
    )),
    ('site_d', 0x0014EFE0, bytes.fromhex(
        "5553565783ec14a11829b7008b4840894c2404c7042400000000a11829b7008b0c243b080f8d3a0100006bc954034804"
        "894c2408e844fbffff85c00f841b0100008b442408beff00000089f2e86ff8ffff85c00f840301000089c38b0b89cfc1"
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
        "e8e2f6ffff85c00f85650000005f5e5d59c381ec0002000089e731c0b980000000f3ab8b351829b7008b4e388b5e3c8b"
        "7604bd5400000049781c8b048b29f072f631d2f7f585d275ee3d0010000073e70fab0424ebe16afee83afdffff81c400"
        "020000c3"
    )),
    ('site_g', 0x0014F239, bytes.fromhex(
        "e8bff6ffff"
    )),
)

# b81 history-pool: the third b81 revision (f27dd95a6: the playoff fold of every man, the rollover's completion). Never
# merged; reviewed in round 3 and pinned like 26d92bde0, so its executables upgrade in place too.
REVISION_F27DD95A6_PATCHED = (
    ('site_a', 0x0014E8B0, bytes.fromhex(
        "56578b0d1829b7008b414089fe2b7144c1fe0289c129f17e0b8d748ffc8d3c8ffdf3a5fc5f8b351829b7008b0e8b5604"
        "85c97e0f397a2c760483422c0483c25449ebedff4640b8010000005ec3e8defeffff833d987fbd0000740e833da476e5"
        "000975052d00020000c3"
    )),
    ('site_b', 0x0014E930, bytes.fromhex(
        "60ff35987fbd00c705987fbd00000000006a01e888000000e87302000089c3e88cfeffff8b0d1829b7002d7017000039"
        "41407e0e83fb037c0953e8710600004bebdde869feffff8b0d1829b7008b15a476e50083ea08833c240074162d000200"
        "003941407c1b4a75186afde840060000eb0f3941407c0a83fa017705e8aa0800008f05987fbd00e841ffffff8b0d1829"
        "b70031d23941400f9cc28954241c61c3"
    )),
    ('site_c', 0x0014E9D0, bytes.fromhex(
        "5553565781ec08020000a11829b7008b48408b704485c90f8ef500000081f9000001000f87e9000000898c2400020000"
        "31d231db84db750989dfc1ef086689147cf7049e000000107401424339cb72e485d20f84ba00000089d5a11829b7008b"
        "088b580485c97e608b432c29f07253c1e8023b842400020000734789c28b3c96f7c700000010741785ff780a423b9424"
        "0002000072e7c7432c00000000eb2389c2c1ea080fb73c54c1e20839c2730df704960000001074014742ebefc1e70229"
        "7b2c83c35449eb9c8b8c240002000031d289f731db8b0496a900000010750e890783c70431db85c0781443eb1185c079"
        "0d85db7409814ffc0000008031db4239ca72d2a11829b700296840b801000000eb0231c081c4080200005f5e5b5dc204"
        "00528b1081ca00000010891085d279218b512c39d0761383e804f7000000001075f1810800000080eb07c7412c000000"
        "005ac3e8b8fcffff8b0d1829b7003941407c25837c242cfc7407837c242c007c14506a00e887feffff598b151829b700"
        "394a407c0931c0c3b801000000c3b802000000c38b5124c1ea0883e21f8b44242c85c0792c83c00275168b4424043d00"
        "10000073280fa344243073214a4aeb134074f9e80006000085c0741183ea03eb0229c289542410b801000000c3c74424"
        "10c0ffffff31c0c3"
    )),
    ('site_d', 0x0014EFE0, bytes.fromhex(
        "5553565783ec14a11829b7008b4840894c2404c7042400000000a11829b7008b0c243b080f8d3a0100006bc954034804"
        "894c2408e84bfbffff85c00f841b0100008b442408beff00000089f2e86ff8ffff85c00f840301000089c38b0b89cfc1"
        "ef1783e71fc1e91083e17f89cee81e01000085c00f88cf0000000f1f0047578b4c240c89f2e8b6fdffff89c531c985c0"
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
        "e8e2f6ffff85c00f85650000005f5e5d59c381ec0002000089e731c0b980000000f3ab8b351829b7008b4e388b5e3c8b"
        "7604bd5400000049781c8b048b29f072f631d2f7f585d275ee3d0010000073e70fab0424ebe16afee83afdffff81c400"
        "020000c3"
    )),
    ('site_g', 0x0014F239, bytes.fromhex(
        "e8bff6ffff"
    )),
    ('site_h', 0x0014EDA8, bytes.fromhex(
        "e824040000"
    )),
    ('site_i', 0x0014F170, bytes.fromhex(
        "8b44241029f8781f837c242cfd751883fe57741083fe1f770eb80d731c000fa3f019c0c383c8ffc356538b5924c1eb08"
        "83e31f83eb02c1e31781cb000000408b712c31c085f674168b0683c60450250000807f39d858740685c079ec31c05b5e"
        "c3817c2408827c2400753c833da476e500097533a11829b7003b70047529608b2889f14d7820e89dffffff83c15485c0"
        "74f18325987fbd00006afce8d0fdffffff05987fbd0061b801000000c3"
    )),
)


def _revision(name: str, patched, pin: str):
    """(name, the revision's own sites (label, VA, retail, patched), what it holds over each of this release's spans
    (its bytes, then retail to our length; retail where it has no such site), the in-place upgrade (changed spans))."""
    old = {label: (va, after) for label, va, after in patched}
    own = tuple((label, va, before[:len(old[label][1])], old[label][1]) for label, va, before, _after in SITES
                if label in old and old[label][0] == va and len(old[label][1]) <= len(before))
    if len(own) != len(old) or _digest(own) != pin:
        raise ImportError(f"nfl2k5_history_pool: the {name} revision does not match its pin")
    spans = tuple((label, va, before, (old[label][1] + before[len(old[label][1]):]) if label in old else before)
                  for label, va, before, _after in SITES)
    upgrade = tuple((label, va, was, after) for (label, va, _before, was), (_l, _v, _b, after) in zip(spans, SITES)
                    if was != after)
    return name, own, spans, upgrade


PREVIOUS_SHA256 = "12f8f431af15622399a453dc937f869a5fc5c8956f9769d6190c9634c2ce3373"   # beta-80's PATCHED_SHA256
REVISION_570CD7C16_SHA256 = "7b61e3e99770293913efdb989b8d097a8bf2b2ef4a03b1a54e7d972f0144ddae"   # 570cd7c16's
REVISION_26D92BDE0_SHA256 = "92f96e1b979b075ccb73f67f7951f08ee523987baaea500439404d9a016d4d38"   # 26d92bde0's
REVISION_F27DD95A6_SHA256 = "dea980b4159eefd0b5f7b7728dba0c2b7386b5c5838027d4f60f49d516597845"   # f27dd95a6's
REVISIONS = (_revision("beta-80", PREVIOUS_PATCHED, PREVIOUS_SHA256),
             _revision("b81 570cd7c16", REVISION_570CD7C16_PATCHED, REVISION_570CD7C16_SHA256),
             _revision("b81 26d92bde0", REVISION_26D92BDE0_PATCHED, REVISION_26D92BDE0_SHA256),
             _revision("b81 f27dd95a6", REVISION_F27DD95A6_PATCHED, REVISION_F27DD95A6_SHA256))
PREVIOUS_SITES, UPGRADE_SITES = REVISIONS[0][1], REVISIONS[0][3]        # the shipped (beta-80 / v0.9) revision
REVISION_570CD7C16_SITES, UPGRADE_570CD7C16_SITES = REVISIONS[1][1], REVISIONS[1][3]
REVISION_26D92BDE0_SITES, UPGRADE_26D92BDE0_SITES = REVISIONS[2][1], REVISIONS[2][3]
REVISION_F27DD95A6_SITES, UPGRADE_F27DD95A6_SITES = REVISIONS[3][1], REVISIONS[3][3]


def _reads(payload: bytes, spans) -> bool:
    try:
        return all(payload[rdata.offset_of(payload, va):rdata.offset_of(payload, va) + len(want)] == want
                   for _label, va, _before, want in spans)
    except (rdata.RdataSiteError, ValueError, IndexError):
        return False


def installed_revision(payload: bytes) -> str | None:
    """The earlier revision every span of this release reads exactly (``REVISIONS`` names), else None."""

    for name, _own, spans, _upgrade in REVISIONS:
        if _reads(payload, spans):
            return name
    return None


def status(payload: bytes) -> str:
    """``retail`` | ``applied`` | ``previous`` (the beta-80 / v0.9 revision, or the b81 revisions 570cd7c16, 26d92bde0) |
    ``foreign`` for a default.xbe image."""

    state = rdata.status(payload, SITES)
    if state == "foreign" and installed_revision(payload) is not None:
        return "previous"
    return state


def apply(payload: bytes):
    """(patched payload, receipt). Retail and previous become applied (previous in place: only the changed spans);
    refuses an executable whose sites are neither retail, previous nor exactly this owner's."""

    state = status(payload)
    if state == "previous":
        name = installed_revision(payload)
        upgrade = next(row[3] for row in REVISIONS if row[0] == name)
        result, receipt = rdata.apply(payload, upgrade, f"history pool ({name} revision)")
        receipt = {**dict(receipt), "upgraded_from": "previous", "previous_revision": name}
    else:
        result, receipt = rdata.apply(payload, SITES, "history pool")
    if status(result) != "applied":
        raise rdata.RdataSiteError("history pool: post-apply verification failed")
    return result, {"owner": OWNER, "status": status(result), **dict(receipt)}


def _installed_sites(read) -> list[tuple[str, int, bytes, bytes]]:
    for sites in (SITES,) + tuple(row[1] for row in REVISIONS):
        try:
            if all(read(va, len(after)) == after for _label, va, _before, after in sites):
                return list(sites)
        except (ValueError, IndexError, KeyError):
            return []
    return []


def applied_sites(image) -> list[tuple[str, int, bytes, bytes]]:
    """``SITES`` when every site of an :class:`XbeImage` reads exactly this owner's bytes, an earlier revision's own
    sites (``PREVIOUS_SITES``, ``REVISION_570CD7C16_SITES``, ``REVISION_26D92BDE0_SITES``) when every one reads that
    revision, else []. The honors
    owner masks these (restores their retail bytes) before it hashes the fold and the writer it pins."""

    return _installed_sites(image.read)


def compatible_edits(payload: bytes) -> list[tuple[int, bytes]]:
    """[(VA, retail bytes)] of every site while this owner is exactly applied (or exactly an earlier revision), else [].
    ``nfl2k5_defensive_try`` restores them before it hashes its pinned history-engine context: this owner keeps the
    engine's interface (the writer, the getters and setters defensive_try calls are untouched; field 59 folds by the
    retail rule)."""

    state = status(payload)
    if state == "applied":
        sites = SITES
    elif state == "previous":
        name = installed_revision(payload)
        sites = next(row[1] for row in REVISIONS if row[0] == name)
    else:
        sites = ()
    return [(va, before) for _label, va, before, _after in sites]


def verify(payload: bytes) -> dict:
    return {"owner": OWNER, "status": status(payload), "experimental": False, "runtime_witnessed": False,
            "sites": [{"label": label, "va": f"0x{va:x}", "bytes": len(after)} for label, va, _b, after in SITES],
            "chunk_words": CHUNK_WORDS, "min_fold_depth": MIN_DEPTH, "free_agent_fold_depth": FREE_AGENT_DEPTH,
            "capacity_words": CAPACITY_WORDS, "playoff_reserve_words": PLAYOFF_RESERVE,
            "playoff_fold_depth": PLAYOFF_FOLD_DEPTH, "close_fields": list(CLOSE_FIELDS), "drop_va": f"0x{DROP_VA:x}",
            "patched_sha256": PATCHED_SHA256, "previous_sha256": PREVIOUS_SHA256,
            "revision_570cd7c16_sha256": REVISION_570CD7C16_SHA256, "revision_26d92bde0_sha256": REVISION_26D92BDE0_SHA256,
            "revision_f27dd95a6_sha256": REVISION_F27DD95A6_SHA256, "playoff_room_words": PLAYOFF_ROOM,
            "honor_fields_left_by_early_folds": list(HONOR_FIELDS)}


__all__ = ["OWNER", "BUILD_CAPTION", "HELP_TEXT", "SITES", "PREVIOUS_SITES", "UPGRADE_SITES", "REVISIONS",
           "REVISION_570CD7C16_SITES", "UPGRADE_570CD7C16_SITES", "REVISION_26D92BDE0_SITES", "UPGRADE_26D92BDE0_SITES",
           "REVISION_F27DD95A6_SITES", "UPGRADE_F27DD95A6_SITES", "PLAYOFF_ROOM", "HONOR_FIELDS",
           "CHUNK_WORDS", "MIN_DEPTH", "FREE_AGENT_DEPTH", "PLAYOFF_RESERVE", "PLAYOFF_FOLD_DEPTH", "CLOSE_FIELDS", "DROP_VA", "status", "apply", "applied_sites", "compatible_edits", "installed_revision",
           "verify"]

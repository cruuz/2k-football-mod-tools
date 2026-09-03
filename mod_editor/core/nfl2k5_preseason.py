"""Template-driven three-game preseason for ESPN NFL 2K5 (executable patch, xemu-only).

Retail (proved in the retail ``default.xbe``, see ``FRANCHISE_2026_09-03_NIGHT.md``):

* the preseason is **generated at random** by ``FUN_002bec20`` (0x2BEC20..0x2BF18A + its weekday
  jump table, 0x2BF18C..0x2BF1A8; the next function starts at 0x2BF1B0): 32 teams shuffled, five
  weeks of 13/13/13/13/12 pairings (6 idle teams in weeks 0-3, 8 in week 4 -- four games per
  team), written into grid rows 0..4 with flags (1,1) and zeroed quarter scores, then dated from
  the Thursday 119 days before Thanksgiving of ``2000 + 4 + season`` (retail ``add al,4`` at
  0x2BEF6B; the ``year`` group used to move it) with 2-3 Thursday, 3-4 Saturday, 2-3 Monday
  games and the rest on Sunday, all at 1:00;
* callers: the franchise start ``FUN_0013ee10`` (0x13EEE8, when "Preseason Games" is on) and the
  Signing -> Preseason transition ``FUN_002480b0`` case 6 (0x2484E7), both through the thunk at
  0x2BF8A0; the regular season is regenerated into rows 0..17 at the Preseason -> Season
  transition (``FUN_002bf8b0`` -> ``FUN_002bf270``), so the preseason rows never shift the
  regular-season rows, the Wild Card row or the 14-team bracket;
* the Preseason stage simulates ``.rdata`` stage-table byte 0x5151B4 weeks (row 7, +4: retail 5)
  and byte +5 (0x5151B5, retail 5) bounds the weekly-preparation gate ``FUN_00247d10``.

The patch (``preseason`` group of ``nfl2k5_season_length``):

* ``FUN_002bec20`` is rewritten **in place** (0x590 bytes available, ~0x1E0 used, int3 padded; no
  call, jump or pointer lands inside the retail body other than at its entry) to copy a template
  instead: it keeps the retail prologue (grid reset ``FUN_000c4ec0``, week/slot := 0,
  ``FUN_001161a0``, the 32-entry team lookup refresh ``FUN_002bea40``), locates the block through
  the roster pool (``[0xB72918]`` -> pair +0x28/+0x2C = the regular-season template, block =
  ``records + count * 8``), checks the ``'PR'`` tag and count (1..68), and writes every record to
  row = its type byte (0..3; the date-based week detector would merge preseason weeks 1 and 2
  because Saturday -> Thursday is not a week break to it), slot = running count per row, with
  flags (1,1) and zeroed scores through the retail helpers.  Season 0 keeps the template dates
  verbatim; later seasons re-date every record to ``HOF Thursday + (record - first record)``
  where HOF Thursday = Thanksgiving of ``template year + season`` minus 119 days (retail's own
  preseason anchor; the regular season anchors 84 days before Thanksgiving, so the preseason
  keeps its two-week gap before kickoff).  No template block (tag missing) -> an empty preseason
  (four idle weeks), never a crash;
* stage bytes 0x5151B4 / 0x5151B5: 5 -> 4 (Hall of Fame week + three league-wide weeks).

The template itself is data: ``tools/nfl2k5_franchise_schedule.py encode_preseason`` writes
``[u32 'PR'<<16 | count][records]`` after the regular-season template in the ROST tail of pack 0
(``data/nfl_2026_schedule.json["preseason"]``: the real 2026 slate from ESPN -- HOF Game Thu Aug 6
Panthers at Cardinals, then 16 games each on Aug 13-15, Aug 20-23, Aug 27-29; 3 per team, the
HOF pair 4).  Everything is pattern-checked against the retail bytes and the touched section
digests are recomputed.  Emulated under unicorn in ``tests/nfl2k5_preseason_test.py``; not yet
witnessed in xemu.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .nfl2k5_draft_ai import _Asm

GENERATOR_VA = 0x002BEC20            # FUN_002bec20 (retail preseason generator), rewritten in place
GENERATOR_SIZE = 0x590               # up to FUN_002bf1b0
GENERATOR_THUNK_VA = 0x002BF8A0      # jmp FUN_002bec20 (callers 0x13EEE8 and 0x2484E7 go through it)
STAGE_PRESEASON_WEEKS_VA = 0x005151B4  # stage table row 7 (Preseason) byte +4: weeks to simulate
STAGE_PRESEASON_PREP_VA = 0x005151B5   # byte +5: weekly-preparation week bound (FUN_00247d10)
RETAIL_PRESEASON_WEEKS = 5
PATCHED_PRESEASON_WEEKS = 4
RETAIL_PRESEASON_GAMES = 4
PATCHED_PRESEASON_GAMES = 3

# retail helpers the rewritten generator calls (all proved by the retail generators' own calls)
FN_RESET_GRID = 0x000C4EC0           # every slot type 7, flags 0, then FUN_000c4bc0(0)
FN_SET_WEEK = 0x000C4E60             # DAT_00e576b4 = ecx
FN_SET_SLOT = 0x000C4E80             # DAT_00e576bc = ecx
FN_MARQUEE_RESET = 0x001161A0        # clears the per-team game-of-the-week blocks (both generators)
FN_TEAM_LOOKUP = 0x002BEA40          # edi = team ordinal -> eax = index (refreshes DAT_00c8c768[32])
FN_SEASON_INDEX = 0x000C4EB0         # eax = DAT_00e576b8
FN_DAY_NUMBER = 0x001C19F0           # ecx = record -> eax = day number of [rec+3..5] (month, day, yy)
FN_WEEKDAY = 0x001C18B0              # ecx = [month, day, yy] -> eax = Mon 0 .. Sun 6
FN_ADD_DAYS = 0x001C1B30             # ecx = [month, day, yy], edx = days (in place)
FN_SUB_DAYS = 0x001C1BB0             # ecx = [month, day, yy], edx = days (in place)
FN_MEMCPY = 0x00031000               # ecx = dst, edx = src, [esp+4] = n; ret 4
FN_FLAG_A = 0x000C4F50               # ecx = row, edx = slot, [esp+4] = value; ret 4
FN_FLAG_B = 0x000C4F70
FN_WRITE_RECORD = 0x000C6900         # ecx = row, edx = slot, [esp+4] = record ptr; ret 4
FN_SCORE_HOME = 0x000C5050           # ecx = row, edx = slot, [esp+4] = quarter, [esp+8] = value; ret 8
FN_SCORE_AWAY = 0x000C5090
POOL_POINTER_GLOBAL = 0x00B72918     # -> resolved ROST pool; +0x28 count, +0x2C records pointer
TEAM_ORDER_TABLE = 0x00ACF038        # 32 team ordinals in division order
TEAM_LOOKUP_TABLE = 0x00C8C768       # DAT_00c8c768[32]
PRESEASON_TAG = 0x5052               # 'PR': high half of the block header
PRESEASON_MAX_GAMES = 68             # four rows x 17 slots
PRESEASON_MAX_ROW = 3
GRID_SLOTS = 17
PRESEASON_ANCHOR_DAYS_BEFORE_THANKSGIVING = 119   # retail 0x77 (kickoff Thursday - 35 days)
RECORD_KIND_OFFSET = 0               # template record: type byte = preseason week 0..3


class PreseasonError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PreseasonError(message)


@dataclass(frozen=True)
class Site:
    label: str
    va: int
    retail: bytes
    patched: bytes
    note: str

    @property
    def size(self) -> int:
        return len(self.retail)


RETAIL_GENERATOR = bytes.fromhex(
    "558bec83e4f881ec3801000053555657e88b62e0ff33c9e82462e0ff33c9e83d62e0ffe85875e5ff33c08d9b00000000898484c80000004083f8207cf3be0100"
    "00008dbc24c8000000bb1f0000008bffb9a0fce500e8d69ed8ff33d2b9200000002bcef7f183c70403d68b8c94c80000008d8494c80000008b57fc8910894ffc"
    "464b75cc33f6eb088da42400000000908bbe38f0ac00e885fdffff898668c7c80083c60481fe800000007ce433db33f6895c24188974242c33c983fb040f95c1"
    "33d283c10c83fb040f95c2894c242003c933c04a83e20285c97e2503d68d49008bf281e61f00008079054e83cee0468bb4b4c80000008974844840423bc17ce0"
    "49c744241400000000894c243ceb048b4c243c85c9c744241c000000007e3fbe010000008d7c24488be98d9b00000000b9a0fce500e8f69dd8ff8b4c242003c9"
    "33d22bcef7f18b0f83c70403d68b4494488d549448890a8947fc464d75d28b44242c33ed85c00f8ebe0000008d6424008b44241c85c00f85ae0000008b442420"
    "33db85c00f8e910000008d9b000000008b44241c85c00f857f00000033f68bff8b44241c85c075668b7cdc488bd68bcde82b60e0ff8bc8e8c45ee0ff3bc77416"
    "8bd68bcde81760e0ff8bc8e8b05ee0ff3b44dc4c75328bd68bcde82160e0ff8bc8e89a5ee0ff3bc774168bd68bcde80d60e0ff8bc8e8865ee0ff3b44dc4c7508"
    "c744241c010000004683fe0d7c928b442420433bd80f8c75ffffff8b442418453be88bd80f8c46ffffff8b4c24148b44241c4185c0894c2414740b8bc183f814"
    "0f8cc9feffff8b44242033f685c00f8ece00000033d28d4c2440e8012ef0ff6a018bd68bcbe8c660e0ff6a018bd68bcbe8db60e0ff8a54f4488a44f44c8d4c24"
    "4088542441518bd68bcb88442446e84d7ae0ff6a006a008bd68bcbe89061e0ff6a006a018bd68bcbe88361e0ff6a006a028bd68bcbe87661e0ff6a006a038bd6"
    "8bcbe86961e0ff6a006a048bd68bcbe85c61e0ff6a006a008bd68bcbe88f61e0ff6a006a018bd68bcbe88261e0ff6a006a028bd68bcbe87561e0ff6a006a038b"
    "d68bcbe86861e0ff6a006a048bd68bcbe85b61e0ff8b442420463bf00f8c32ffffff8b74242c83c6064383fe1e895c24188974242c0f8c7dfdffffc64424100b"
    "c644241101e8465fe0ff04048d4c241088442412e83729f0ff83f806773fff24858cf12b00ba1b000000eb28ba1a000000eb21ba19000000eb1aba18000000eb"
    "13ba17000000eb0cba16000000eb05ba150000008d4c2410e8732bf0ffba770000008d4c2410e8e52bf0ffc744241800000000c744241c02000000eb038d4900"
    "8b4c2418e8375fe0ff8bd8b9a0fce500895c2420e8579bd8ff8bf083e601b9a0fce50083c602e8459bd8ff8bf883e701b9a0fce50083c703e8339bd8ff8be883"
    "e50183c5022bdd2bdf6a038d5424148d4c24382bdee8c61fd7ff8b54241c83c2fe8d4c2434e8e62af0ff6a038d5424148d4c243ce8a71fd7ff8b54241c4a8d4c"
    "2438e8c92af0ff6a038d5424148d4c242ce88a1fd7ff8b54241c8d4c2428e8ad2af0ff6a038d5424148d4c2434e86e1fd7ff8b54241c428d4c2430e8902af0ff"
    "85f6c74424140000000074228d6424008b4c24188d542434528b542418e85efaffff8b4c2414414e894c241475e285ff741e8b5424148b4c24188d44243850e8"
    "3cfaffff8b4c2414414f894c241475e285db741e8b5424148d4c2428518b4c241ce81afaffff8b4c2414414b894c241475e285ed741e8b4c24188d542430528b"
    "542418e8f8f9ffff8b4c2414414d894c241475e28b7c242033f685ffc644242401c6442425007e1deb068d9b000000008b4c24188d442424508bd6e8e0f9ffff"
    "463bf77ceb8b44241c8b74241883c0074683f825897424188944241c0f8c5efeffff5f5e5d5b8be55dc38bff9aef2b00a1ef2b00a8ef2b00afef2b0085ef2b00"
    "8cef2b0093ef2b009090909090909090"
)


def generator_code() -> tuple[bytes, dict[str, int]]:
    """The rewritten FUN_002bec20 (see the module docstring); returns (code, labels)."""

    a = _Asm(GENERATOR_VA)
    # frame: [ebp-0x08] rec, [ebp-0x10] prev (unused), [ebp-0x18] anchor {month, day, yy, pad},
    #        [ebp-0x1c] day number of template record 0, [ebp-0x20] season, [ebp-0x24] count,
    #        [ebp-0x28] row, [ebp-0x2c] slot, [ebp-0x30] i, [ebp-0x34] template records
    a.label("entry")
    a.b("55"); a.b("8bec"); a.b("83ec40"); a.b("53"); a.b("56"); a.b("57")
    a.call(FN_RESET_GRID)
    a.b("33c9"); a.call(FN_SET_WEEK)
    a.b("33c9"); a.call(FN_SET_SLOT)
    a.call(FN_MARQUEE_RESET)
    a.b("33f6")
    a.label("team_table")
    a.b("8bbe" + struct.pack("<I", TEAM_ORDER_TABLE).hex())          # mov edi,[esi+table]
    a.call(FN_TEAM_LOOKUP)
    a.b("8986" + struct.pack("<I", TEAM_LOOKUP_TABLE).hex())         # mov [esi+lookup],eax
    a.b("83c604"); a.b("81fe80000000"); a.j8("7c", "team_table")
    # ---- locate the template block through the pool pair
    a.b("8b0d" + struct.pack("<I", POOL_POINTER_GLOBAL).hex())       # mov ecx,[pool]
    a.b("8b4128")                                                     # mov eax,[ecx+0x28]  (count)
    a.b("8b712c")                                                     # mov esi,[ecx+0x2c]  (records)
    a.b("8d34c6")                                                     # lea esi,[esi+eax*8]
    a.b("8b06"); a.b("8bd0"); a.b("c1ea10")                           # eax = header; edx = header >> 16
    a.b("81fa" + struct.pack("<I", PRESEASON_TAG).hex()); a.j32("0f85", "done")   # tag 'PR'?
    a.b("0fb7c0"); a.b("85c0"); a.j32("0f84", "done")                 # count == 0 -> nothing to do
    a.b("83f8" + f"{PRESEASON_MAX_GAMES:02x}"); a.j32("0f87", "done")  # count > 68 -> refuse
    a.b("8945dc")                                                     # [count] = eax
    a.b("83c604"); a.b("8975cc")                                      # [template] = esi + 4
    a.call(FN_SEASON_INDEX); a.b("8945e0"); a.b("85c0"); a.j8("74", "init")
    # ---- season > 0: anchor = Thanksgiving(template year + season) - 119 days
    a.b("c645e80b"); a.b("c645e901")                                  # anchor = Nov 1
    a.b("8a4605"); a.b("0245e0"); a.b("8845ea")                       # yy = template[0].yy + season
    a.b("8d4de8"); a.call(FN_WEEKDAY)                                 # eax = weekday of Nov 1 (Mon 0)
    a.b("ba03000000"); a.b("2bd0"); a.b("83c207")                     # edx = 10 - wd
    a.b("83fa07"); a.j8("72", "nowrap"); a.b("83ea07")                # (3 - wd + 7) mod 7
    a.label("nowrap")
    a.b("83c215")                                                     # + 21 = fourth Thursday
    a.b("8d4de8"); a.call(FN_ADD_DAYS)
    a.b("ba" + struct.pack("<I", PRESEASON_ANCHOR_DAYS_BEFORE_THANKSGIVING).hex())
    a.b("8d4de8"); a.call(FN_SUB_DAYS)                                # anchor = HOF Thursday
    a.b("8b4dcc"); a.call(FN_DAY_NUMBER); a.b("8945e4")               # [day0] = daynum(template[0])
    a.label("init")
    a.b("33c0"); a.b("8945d8"); a.b("8945d4"); a.b("8945d0")          # row = slot = i = 0
    a.label("loop")
    a.b("8b45d0"); a.b("3b45dc"); a.j32("0f8d", "done")               # i >= count -> done
    a.b("8b55cc"); a.b("8d14c2"); a.b("8d4df8"); a.b("6a08"); a.call(FN_MEMCPY)   # rec = template[i]
    a.b("0fb645f8"); a.b("83f8" + f"{PRESEASON_MAX_ROW:02x}"); a.j32("0f87", "next")  # week > 3 -> skip
    a.b("3b45d8"); a.j8("74", "sameweek")
    a.b("8945d8"); a.b("c745d400000000")                              # new row: slot = 0
    a.label("sameweek")
    a.b("837dd4" + f"{GRID_SLOTS:02x}"); a.j32("0f83", "next")        # slot >= 17 -> skip
    a.b("c645f800")                                                   # rec.type = 0 (upcoming)
    a.b("8b45e0"); a.b("85c0"); a.j8("74", "write")                   # season 0: dates verbatim
    a.b("8d4df8"); a.call(FN_DAY_NUMBER); a.b("2b45e4")               # eax = daynum(rec) - day0
    a.b("668b4de8"); a.b("66894dfb"); a.b("8a4dea"); a.b("884dfd")    # rec.date = anchor
    a.b("8bd0"); a.b("8d4dfb"); a.call(FN_ADD_DAYS)                   # rec.date += delta
    a.label("write")
    a.b("8b5dd8"); a.b("8b7dd4")                                      # ebx = row, edi = slot
    a.b("6a01"); a.b("8bd7"); a.b("8bcb"); a.call(FN_FLAG_A)
    a.b("6a01"); a.b("8bd7"); a.b("8bcb"); a.call(FN_FLAG_B)
    a.b("8d45f8"); a.b("50"); a.b("8bd7"); a.b("8bcb"); a.call(FN_WRITE_RECORD)
    a.b("33f6")
    a.label("scores")
    a.b("6a00"); a.b("56"); a.b("8bd7"); a.b("8bcb"); a.call(FN_SCORE_HOME)
    a.b("6a00"); a.b("56"); a.b("8bd7"); a.b("8bcb"); a.call(FN_SCORE_AWAY)
    a.b("46"); a.b("83fe05"); a.j8("7c", "scores")
    a.b("ff45d4")                                                     # slot++
    a.label("next")
    a.b("ff45d0"); a.j32("e9", "loop")                                # i++
    a.label("done")
    a.b("5f"); a.b("5e"); a.b("5b"); a.b("8be5"); a.b("5d"); a.b("c3")
    a.label("end")
    code = a.assemble()
    _require(len(code) <= GENERATOR_SIZE, "rewritten preseason generator does not fit")
    return code, {k: GENERATOR_VA + v for k, v in a.labels.items()}


def generator_bytes() -> bytes:
    code, _labels = generator_code()
    return code + b"\xcc" * (GENERATOR_SIZE - len(code))


def cave_labels() -> dict[str, int]:
    return generator_code()[1]


def sites() -> tuple[Site, ...]:
    return (
        Site("preseason_generator", GENERATOR_VA, RETAIL_GENERATOR, generator_bytes(),
             "FUN_002bec20 rewritten in place: copy the 'PR' template block after the regular-season "
             "records into rows 0..3 (row = record type byte), season 0 verbatim, later seasons re-dated "
             "from Thanksgiving - 119 days"),
        Site("stage_preseason_weeks", STAGE_PRESEASON_WEEKS_VA, bytes([RETAIL_PRESEASON_WEEKS]),
             bytes([PATCHED_PRESEASON_WEEKS]), "stage table row 7 byte +4: preseason weeks 5 -> 4"),
        Site("stage_preseason_prep", STAGE_PRESEASON_PREP_VA, bytes([RETAIL_PRESEASON_WEEKS]),
             bytes([PATCHED_PRESEASON_WEEKS]), "stage table row 7 byte +5: weekly-preparation bound 5 -> 4"),
    )


def site_table() -> list[dict[str, object]]:
    return [{"label": s.label, "va": f"0x{s.va:08x}", "size": s.size,
             "retail": s.retail.hex() if s.size <= 16 else f"<{s.size} bytes>",
             "patched": s.patched.hex() if s.size <= 16 else f"<{s.size} bytes>", "note": s.note} for s in sites()]


def code_report() -> dict[str, object]:
    code, labels = generator_code()
    return {"generator_va": f"0x{GENERATOR_VA:08x}", "region_size": GENERATOR_SIZE, "code_size": len(code),
            "labels": {k: f"0x{v:08x}" for k, v in labels.items()},
            "helpers": {"reset_grid": f"0x{FN_RESET_GRID:x}", "set_week": f"0x{FN_SET_WEEK:x}",
                        "set_slot": f"0x{FN_SET_SLOT:x}", "marquee_reset": f"0x{FN_MARQUEE_RESET:x}",
                        "team_lookup": f"0x{FN_TEAM_LOOKUP:x}", "season_index": f"0x{FN_SEASON_INDEX:x}",
                        "day_number": f"0x{FN_DAY_NUMBER:x}", "weekday": f"0x{FN_WEEKDAY:x}",
                        "add_days": f"0x{FN_ADD_DAYS:x}", "sub_days": f"0x{FN_SUB_DAYS:x}",
                        "memcpy": f"0x{FN_MEMCPY:x}", "flag_a": f"0x{FN_FLAG_A:x}", "flag_b": f"0x{FN_FLAG_B:x}",
                        "write_record": f"0x{FN_WRITE_RECORD:x}", "score_home": f"0x{FN_SCORE_HOME:x}",
                        "score_away": f"0x{FN_SCORE_AWAY:x}"},
            "template": "pool[0xB72918] -> [+0x2C] + 8 * [+0x28]; header 'PR'<<16 | count; records "
                        "[week][home][away][month][day][yy][hour12][minute]",
            "preseason_weeks": PATCHED_PRESEASON_WEEKS, "games_per_team": PATCHED_PRESEASON_GAMES}


__all__ = ["GENERATOR_SIZE", "GENERATOR_VA", "PATCHED_PRESEASON_GAMES", "PATCHED_PRESEASON_WEEKS",
           "PRESEASON_MAX_GAMES", "PRESEASON_TAG", "RETAIL_GENERATOR", "RETAIL_PRESEASON_GAMES",
           "RETAIL_PRESEASON_WEEKS", "STAGE_PRESEASON_PREP_VA", "STAGE_PRESEASON_WEEKS_VA", "PreseasonError",
           "Site", "cave_labels", "code_report", "generator_bytes", "generator_code", "site_table", "sites"]

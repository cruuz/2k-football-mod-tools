"""Franchise Player Progress screen and weekly snapshot capture (native owner, EXPERIMENTAL).

Retail's Front Office **Player Progress** screen (descriptor 0x551800) already knows how to show a
player's attributes as ``Previously`` / ``Currently`` / ``+/- Change``. This owner keeps that screen
and makes it useful all season:

* **Visibility** (0x2C26A0): retail shows the Front Office row only in stages 1..4 (the offseason).
  The cave shows it in stages 1..4 and 7..9 (preseason, regular season, playoffs).
* **Season baseline** (0x247B20 call sites 0x13EF03 and 0x248641): when the game enters the regular
  season (stage 8), capture the user team's 65-player roster as the week-0 snapshot.
* **Week advance** (0xC4E60, the game's week setter): after every week of the regular season and
  playoffs, capture the new live ratings when the setter moves the week forward by one. The record keeps the season baseline and the previous
  week's ratings; ``+/- Change`` can then show either the season change or the last week's change.
* **Screen values** (0x365B20): return the stored baseline for ``Previously``, the live rating for
  ``Currently``, and either ``live - baseline`` (season) or ``live - previous`` (last week) for the
  change row. The player is mapped to the user team's roster slot by pointer, and the stored identity
  (pbp id, position, jersey) must match.
* **Change header** (0x365E34): ``+/- Change`` becomes ``Last Week`` while the toggle is on.
* **Toggle** (unused screen event): any input event the screen currently ignores flips the toggle.

The record is the ``PPG2`` v1 layout in ``nfl2k5_player_progression``: 5,232 bytes in a fixed,
all-zero tail of the roster arena (file 0x8FCF4), so the save stays 720,044 bytes and an old save
loads unchanged. The game's own save copies it (an emulator autosave decodes exactly: baseline
overall 77, previous 79, last overall +2, accuracy 76 -> 81 -> last +5 on the first QB).

**SAVE HOST STATUS (b778-pg2, emulator): the tail is NOT safe at runtime.** With the record written,
the running Front Office stopped responding to the Player Progress row (the same row opens in a
control run with only the visibility patch and no record). The game uses that tail while the Front
Office/Player Progress screens are alive. The build option is therefore OFF in every preset. The
record still needs a versioned franchise footer (the MyCareer ``MCPL0001`` footer is the precedent)
or an owned arena reserve with native save/load hooks; the capture/value code above is ready for
that host. One small pending change for that host: weekly captures and the value getter must take
the team from the record header once a baseline exists. ``0xC4D70`` is the controller-assigned team
and changed during a simulated week (it returned team 7 instead of the user's team 30); the probe
patched it only to keep the test deterministic.

The owner is a late executable owner. It requests **code 1,392 bytes** (assembled cave + row map +
``Last Week`` string, 16-aligned) and **writable data 16 bytes** (the toggle). It needs the growable
pool from job xs1; on the pre-xs1 base the allocation refuses and the coordinator merges this owner
after ``nfl2k5_weekly_progression`` and before ``nfl2k5_module_loader``. Nothing is written to the
disc and no save growth is requested.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_player_progression as record
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_player_progress_screen"
BUILD_CAPTION = "Franchise: Player Progress screen with weekly changes"
HELP_TEXT = (
    "EXPERIMENTAL. The Front Office Player Progress screen is available every week of the regular "
    "season and playoffs. Previously is the season-opening rating, Currently is the live rating and "
    "+/- Change is movement since the season began; an unused pad button switches the change row to "
    "Last Week. Old saves load normally."
)

IMAGE_BASE = 0x10000
MAGIC_DWORD = struct.unpack("<I", record.MAGIC)[0]
RUNTIME_RECORD_DELTA = record.RECORD_RUNTIME_DELTA
MAP = record.ROW_MAP
LAST_WEEK_TEXT = "Last Week".encode("utf-16-le") + b"\0\0"

# --- retail routines and globals the cave reads or calls -----------------------------------------
STAGE_VA = 0x00E576A4
WEEK_VA = 0x00E576B4
YEAR_VA = 0x00E576B8
ROSTER_VA = 0x00B72918
FN_TEAM = 0x000C4D70
FN_LIST = 0x000F31B0
FN_LIST_INDEX = 0x00170510
FN_OVERALL = 0x000E6660
FN_STAGE_ENTER = 0x00247B20
FN_STAGE = 0x000C4BB0
RETAIL_HEADER_TEXT = 0x00EB92D8

# --- hook sites ---------------------------------------------------------------------------------
SITE_VISIBILITY = (0x002C26A0, bytes.fromhex("568bf2c746"))
SITE_STAGE_NEW_SEASON = (0x0013EF03, bytes.fromhex("e8188c1000"))
SITE_STAGE_NEXT = (0x00248641, bytes.fromhex("e8daf4ffff"))
SITE_WEEK = (0x000C4E60, bytes.fromhex("890db476e500c3"))
SITE_VALUE = (0x00365B20, bytes.fromhex("538b5c240c"))
SITE_HEADER = (0x00365E34, bytes.fromhex("bad892eb00"))
SITE_EVENT_POINTER = (0x000F4268, struct.pack("<I", 0x000F4221))

GUARDS = (
    ("coached_team", 0x000C4D70, 0x2B, "889b779e28323f3894bf937be5dc6c0f2e7e3d486233f41feee28acd7048fd39"),
    ("overall", 0x000E6660, 0x20, "71dc9b688f7bff8fbb96cac537f87baa864f212b5a9aa376d556ca27de6fb5e3"),
    ("player_list", 0x000F31B0, 0x43, "2a56fd6cd3ee619b21dd97469e8ad38607521aec146a14c0fcaa74b2df969e0a"),
    ("player_list_index", 0x00170510, 0x06, "ef53e39626a1f56685aeea674ccacc10683aa6711268a3ab503b84e311f623aa"),
    ("stage_enter", 0x00247B20, 0x1A, "9c5d1882c1b1254cd4350626a07d48ee6b313812568e9c6479eb4dcf294bced6"),
    ("visibility", 0x002C26A0, 0x30, "d2fdc73119dcd27672d4c6931e48e8db73a44f016b5bb582f98617f159700bd6"),
    ("value_getter", 0x00365B20, 0x14B, "de28b89c34bd93cf45db19b5c0c85e67bb8fb2b209c84d43c0d191781bbb412d"),
    ("header_context", 0x00365E20, 0x40, "6dc7bfaa61f1a2be4c695787a43399bd999f0177c29a22ced3522b6e19c00c2e"),
    ("screen_descriptor", 0x00551800, 0x30, "f0523debaafd92b19ddc1483b39be14ac2219e7b9e8ff514daed9daee45ee166"),
    ("new_season", 0x0013EEF0, 0x20, "bce2d9b67db13d51774a43fe7763853d75bb0b4c2c50d42ec32661f226e078e9"),
    ("next_season", 0x00248628, 0x28, "0f8174c1515f9c934e742a3cc8e14cf872ff9f6a74d399681900641f7fc3d403"),
    ("week_advance", 0x000C5D14, 0x20, "eb8c8b928d15c51927b2be3d9d9be47d125ca6330ddf56f7814e814547e6ce79"),
    ("screen_event", 0x000F4268, 0x10, "13e838dff3bb9b334bfccb42574a81b2fb743ca8130dd23f54099eb3d411f08a"),
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, AttributeError)

JZ = "0f84"
JE = "0f84"
JNZ = "0f85"
JNE = "0f85"
JAE = "0f83"
JB = "0f82"
JBE = "0f86"
JL = "0f8c"
JLE = "0f8e"
JGE = "0f8d"

class PlayerProgressScreenError(ValueError):
    """Unsupported executable, foreign installation, or no room for the owner."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlayerProgressScreenError(message)


def _imm(value: int) -> str:
    return struct.pack("<I", value).hex()


def _rel32(target: int, site: int, size: int = 5) -> bytes:
    return struct.pack("<i", target - (site + size))


def _assemble(code_va: int, data_va: int, map_va: int, text_va: int,
              capture_baseline_va: int, capture_week_va: int) -> tuple[bytes, dict[str, int]]:
    """The cave.  All intra-cave call targets are absolute and supplied by the caller."""
    a = _Asm(code_va)

    # ---- visibility: stage 1..4 and 7..9 visible, everything else hidden -----------------------
    a.label("visibility")
    a.b("a1" + _imm(STAGE_VA))                  # mov eax,[stage]
    a.b("c7420801000000")                       # mov dword [edx+8],1
    a.b("83f804"); a.j8("74", "vis4")           # cmp eax,4 ; je vis4
    a.b("83f801"); a.j8("72", "vis_hide")       # cmp eax,1 ; jb vis_hide
    a.b("83f803"); a.j8("76", "vis_show")       # cmp eax,3 ; jbe vis_show
    a.b("83f807"); a.j8("72", "vis_hide")       # cmp eax,7 ; jb vis_hide
    a.b("83f809"); a.j8("77", "vis_hide")       # cmp eax,9 ; ja vis_hide
    a.label("vis_show")
    a.b("c7420800000000")                       # mov dword [edx+8],0
    a.label("vis_hide")
    a.b("c3")
    a.label("vis4")
    a.b("ba02000000")                           # mov edx,2
    a.jmp_abs(0x0014FCD0)                        # retail stage-4 tail

    # ---- toggle (one unused screen event) ------------------------------------------------------
    a.label("toggle")
    a.b("8035" + _imm(data_va) + "01")          # xor byte [toggle],1
    a.b("b801000000")                           # mov eax,1
    a.b("c3")

    # ---- change header: "+/- Change" or "Last Week" -------------------------------------------
    a.label("header")
    a.b("ba" + _imm(RETAIL_HEADER_TEXT))        # mov edx,retail
    a.b("f605" + _imm(data_va) + "01")          # test byte [toggle],1
    a.j8("74", "hdr_done")
    a.b("ba" + _imm(text_va))                   # mov edx,Last Week
    a.label("hdr_done")
    a.b("c3")

    # ---- stage-8 call wrapper: enter the stage, then capture the season baseline --------------
    a.label("stage_wrapper")
    a.b("60")                                   # pushad
    a.b("8be9")                                 # mov ebp,ecx (stage)
    a.call(FN_STAGE_ENTER)                      # call 0x247b20
    a.b("83fd08"); a.j8("75", "stage_done")     # cmp ebp,8 ; jne done
    a.call(capture_baseline_va)
    a.label("stage_done")
    a.b("61")                                   # popad
    a.b("c3")

    # ---- weekly advance: the game sets a new week; capture once after the games ----------------
    a.label("week_setter")
    a.b("60")                                   # pushad
    a.b("89cb")                                 # mov ebx,ecx (new week)
    a.b("8b35" + _imm(WEEK_VA))                 # mov esi,[week] (old week)
    a.b("890d" + _imm(WEEK_VA))                 # mov [week],ecx (the displaced setter)
    a.call(FN_STAGE)                            # call 0xc4bb0 (stage)
    a.b("83f808"); a.j8("74", "week_do")        # cmp eax,8 ; je
    a.b("83f809"); a.j8("75", "week_done")      # cmp eax,9 ; jne done
    a.label("week_do")
    a.b("8d5601")                               # lea edx,[esi+1]
    a.b("39d3"); a.j8("75", "week_done")        # cmp ebx,edx ; jne done
    a.call(capture_week_va)
    a.label("week_done")
    a.b("61")                                   # popad
    a.b("c3")

    # ---- value getter -------------------------------------------------------------------------
    a.label("value")
    a.b("53565755")                             # push ebx,esi,edi,ebp
    a.b("83ec20")                               # sub esp,0x20
    a.b("894c2404")                             # mov [esp+4],ecx (manager)
    a.b("8b442434")                             # mov eax,[esp+0x34] mode
    a.b("8944240c")                             # mov [esp+0x0c],eax
    a.b("8b442438")                             # mov eax,[esp+0x38] row
    a.b("89442408")                             # mov [esp+0x08],eax
    a.b("8b4c2404"); a.call(FN_LIST)
    a.b("85c0"); a.j32(JZ, "value_retail")
    a.b("89442404")                             # mov [esp+4],eax (list record)
    a.b("8bc8"); a.call(FN_LIST_INDEX)
    a.b("8b4c2404")                             # mov ecx,[esp+4]
    a.b("3b81a4000000")                         # cmp eax,[ecx+0xa4]
    a.j32(JAE, "value_retail")
    a.b("8b5140")                               # mov edx,[ecx+0x40]
    a.b("8b0482")                               # mov eax,[edx+eax*4]
    a.b("85c0"); a.j32(JZ, "value_retail")
    a.b("890424")                               # mov [esp],eax (player)
    a.call(FN_TEAM)
    a.b("85c0"); a.j32(JZ, "value_retail")
    a.b("89c2")                                 # mov edx,eax (team)
    a.b("8b3424")                               # mov esi,[esp] (player)
    a.b("0fb68a1c010000")                       # movzx ecx,byte [edx+0x11c]
    a.b("31db")                                 # xor ebx,ebx
    a.label("value_scan")
    a.b("39cb"); a.j32(JAE, "value_retail")     # cmp ebx,ecx
    a.b("39349a"); a.j32(JE, "value_found")     # cmp [edx+ebx*4],esi
    a.b("43"); a.j32("e9", "value_scan")        # inc ebx ; jmp
    a.label("value_found")
    a.b("895c2410")                             # mov [esp+0x10],ebx (slot)
    a.b("8b2d" + _imm(ROSTER_VA))               # mov ebp,[roster]
    a.b("81c5" + _imm(RUNTIME_RECORD_DELTA))    # add ebp,record delta
    a.b("817d00" + _imm(MAGIC_DWORD)); a.j32(JNZ, "value_retail")
    a.b("807d0401"); a.j32(JNE, "value_retail") # version
    a.b("89d8"); a.b("6bc050")                  # mov eax,ebx ; imul eax,eax,80
    a.b("8d7c0520")                             # lea edi,[ebp+eax+0x20]
    a.b("897c2414")                             # mov [esp+0x14],edi
    a.b("0fb74604")                             # movzx eax,word [esi+4]
    a.b("0fb65635")                             # movzx edx,byte [esi+0x35]
    a.b("c1e210"); a.b("09d0")                  # shl edx,16 ; or eax,edx
    a.b("8b5620"); a.b("c1ea03"); a.b("83e27f"); a.b("c1e218"); a.b("09d0")
    a.b("3907"); a.j32(JNE, "value_retail")     # identity
    a.b("f6470602"); a.j32(JZ, "value_retail")  # baseline valid
    a.b("8b4c2404")                             # mov ecx,[esp+4]
    a.b("8b4964")                               # mov ecx,[ecx+0x64] (group base)
    a.b("8b442408")                             # mov eax,[esp+8] (row)
    a.b("85c0"); a.j32(JZ, "value_overall")
    a.b("6bc91a"); a.b("01c1")                  # imul ecx,ecx,26 ; add ecx,eax
    a.b("0fb60c0d" + _imm(map_va))              # movzx ecx,byte [map+ecx]
    a.b("0fbe040e")                             # movsx eax,byte [esi+ecx] current
    a.b("83e936")                               # sub ecx,0x36
    a.b("0fb6540f08")                           # movzx edx,byte [edi+ecx+8] baseline
    a.b("0fb6740f24")                           # movzx esi,byte [edi+ecx+0x24] previous
    a.b("89cb"); a.b("d1eb")                    # mov ebx,ecx ; shr ebx,1
    a.b("0fb65c1f40")                           # movzx ebx,byte [edi+ebx+0x40]
    a.b("f6c101"); a.j8("74", "value_low")
    a.b("c1fb04"); a.j32("e9", "value_sign")
    a.label("value_low")
    a.b("83e30f")
    a.label("value_sign")
    a.b("c1e31c"); a.b("c1fb1c")                # signature-extend the nibble
    a.b("89c1")                                 # mov ecx,eax current
    a.j32("e9", "value_have")
    a.label("value_overall")
    a.b("8bce"); a.call(FN_OVERALL)             # mov ecx,esi ; call overall
    a.b("89c1")                                 # mov ecx,eax current
    a.b("0fb65704")                             # movzx edx,byte [edi+4]
    a.b("0fb64705")                             # movzx eax,byte [edi+5]
    a.b("8bf0")                                 # mov esi,eax previous
    a.b("0fbe5f4e")                             # movsx ebx,byte [edi+0x4e]
    a.j32("e9", "value_have")
    a.label("value_have")
    a.b("8b44240c")                             # mov eax,[esp+0xc] mode
    a.b("85c0"); a.j32(JZ, "value_previous")
    a.b("83f801"); a.j32(JE, "value_current")
    a.b("803d" + _imm(data_va) + "00"); a.j32(JZ, "value_season")
    a.b("f6470608"); a.j32(JZ, "value_season")
    a.b("89d8"); a.j32("e9", "value_store")     # mov eax,ebx last week
    a.label("value_season")
    a.b("89c8"); a.b("29d0")                    # mov eax,ecx ; sub eax,edx
    a.j32("e9", "value_store")
    a.label("value_previous")
    a.b("89d0"); a.j32("e9", "value_store")     # mov eax,edx
    a.label("value_current")
    a.b("89c8")                                 # mov eax,ecx
    a.label("value_store")
    a.b("8944241c")                             # mov [esp+0x1c],eax
    a.b("83c420"); a.b("5d5f5e5b"); a.b("c20c00")
    a.label("value_retail")
    a.b("83c420"); a.b("5d5f5e5b")              # restore the caller frame
    a.b("53"); a.b("8b5c240c")                  # replay the retail prologue
    a.jmp_abs(0x00365B25)

    # ---- snapshot capture ---------------------------------------------------------------------
    a.label("capture_baseline")
    a.b("b800000000"); a.j32("e9", "capture_common")
    a.label("capture_week")
    a.b("b801000000")
    a.label("capture_common")
    a.b("60")                                   # pushad
    a.b("83ec40")                               # sub esp,0x40
    a.b("89442410")                             # [esp+0x10] = mode
    a.call(FN_TEAM)
    a.b("85c0"); a.j32(JZ, "cap_done")
    a.b("890424")                               # [esp] = team
    a.b("8b2d" + _imm(ROSTER_VA)); a.b("81c5" + _imm(RUNTIME_RECORD_DELTA))
    a.b("896c2404")                             # [esp+4] = record
    a.b("8b442410"); a.b("85c0"); a.j32(JZ, "cap_baseline")
    a.b("817d00" + _imm(MAGIC_DWORD)); a.j32(JNZ, "cap_baseline")
    a.b("807d0401"); a.j32(JNE, "cap_baseline")
    a.b("0fb74506")                             # movzx eax,word [record+6]
    a.b("0fb715" + _imm(YEAR_VA))               # movzx edx,word [year]
    a.b("39d0"); a.j32(JNE, "cap_baseline")
    a.b("f6450501"); a.j32(JZ, "cap_baseline")
    a.j32("e9", "cap_loop")
    a.label("cap_baseline")
    a.b("c744241000000000")                     # mode = baseline
    a.b("c74500" + _imm(MAGIC_DWORD))           # magic
    a.b("c6450401")                             # version
    a.b("c6450503")                             # header flags baseline+previous
    a.b("66a1" + _imm(YEAR_VA)); a.b("66894506")# year
    a.b("c6450800"); a.b("c6450900")            # team 0, week 0
    a.label("cap_loop")
    a.b("8b0424")                               # mov eax,[esp] team
    a.b("0fb6881c010000")                       # movzx ecx,byte [eax+0x11c]
    a.b("83f941"); a.j32(JBE, "cap_count_ok")
    a.b("b941000000")                           # 65 slots
    a.label("cap_count_ok")
    a.b("894c2414")                             # [esp+0x14] = count
    a.b("31db")                                 # xor ebx,ebx
    a.label("cap_slot")
    a.b("3b5c2414"); a.j32(JAE, "cap_slots_done")
    a.b("8b0424"); a.b("8b3498")                # mov eax,[esp] ; mov esi,[eax+ebx*4]
    a.b("85f6"); a.j32(JZ, "cap_next")
    a.b("8974240c")                             # [esp+0x0c] = player
    a.b("89d8"); a.b("6bc050")                  # mov eax,ebx ; imul eax,eax,80
    a.b("8d7c0520")                             # lea edi,[ebp+eax+0x20]
    a.b("897c2418")                             # [esp+0x18] = slot record
    a.b("31c9")
    a.label("cap_read")
    a.b("8a540e36")                             # mov dl,[esi+ecx+0x36]
    a.b("88540c20")                             # mov [esp+ecx+0x20],dl
    a.b("41"); a.b("83f91c"); a.j32(JB, "cap_read")
    a.b("8bce"); a.call(FN_OVERALL)
    a.b("8944241c")                             # [esp+0x1c] = current overall
    a.b("0fb74604"); a.b("0fb65635"); a.b("c1e210"); a.b("09d0")
    a.b("8b5620"); a.b("c1ea03"); a.b("83e27f"); a.b("c1e218"); a.b("09d0")
    a.b("8b7c2418")                             # mov edi,[esp+0x18]
    a.b("3907"); a.j32(JE, "cap_same")
    a.b("8907")                                 # new player: identity
    a.b("8b44241c"); a.b("884704"); a.b("884705")
    a.b("c6470607")                             # flags identity+baseline+previous
    a.j32("e9", "cap_copy_both")
    a.label("cap_same")
    a.b("8b442410"); a.b("85c0"); a.j32(JZ, "cap_reset")
    a.b("f6470602"); a.j32(JZ, "cap_reset")
    a.b("31c9")
    a.label("cap_pack")
    a.b("89ca"); a.b("01d2")                    # edx = 2 * ecx
    a.b("0fbe441420")                           # movsx eax,byte [esp+edx+0x20]
    a.b("0fbe741724")                           # movsx esi,byte [edi+edx+0x24]
    a.b("29f0")                                 # sub eax,esi
    a.b("83f807"); a.j32(JLE, "cap_c1")
    a.b("b807000000")
    a.label("cap_c1")
    a.b("83f8f8"); a.j32(JGE, "cap_c2")
    a.b("b8f8ffffff")
    a.label("cap_c2")
    a.b("83e00f"); a.b("8844243c")              # low nibble
    a.b("0fbe441421")                           # movsx eax,byte [esp+edx+0x21]
    a.b("0fbe741725")                           # movsx esi,byte [edi+edx+0x25]
    a.b("29f0")
    a.b("83f807"); a.j32(JLE, "cap_c3")
    a.b("b807000000")
    a.label("cap_c3")
    a.b("83f8f8"); a.j32(JGE, "cap_c4")
    a.b("b8f8ffffff")
    a.label("cap_c4")
    a.b("83e00f"); a.b("c1e004"); a.b("0a44243c")# high nibble
    a.b("88440f40")                             # mov [edi+ecx+0x40],al
    a.b("41"); a.b("83f90e"); a.j32(JB, "cap_pack")
    a.b("31c9")
    a.label("cap_copy_prev")
    a.b("8a540c20"); a.b("88540f24")
    a.b("41"); a.b("83f91c"); a.j32(JB, "cap_copy_prev")
    a.b("8b44241c"); a.b("0fbe5705"); a.b("29d0")
    a.b("83f87f"); a.j32(JLE, "cap_o1")
    a.b("b87f000000")
    a.label("cap_o1")
    a.b("83f880"); a.j32(JGE, "cap_o2")
    a.b("b880ffffff")
    a.label("cap_o2")
    a.b("88474e")                               # last-week overall change
    a.b("8b44241c"); a.b("884705")              # previous overall = current
    a.b("804f0608")                             # last-week valid
    a.j32("e9", "cap_next")
    a.label("cap_reset")
    a.b("8b44241c"); a.b("884704")
    a.b("c6470607")
    a.label("cap_copy_both")
    a.b("31c9")
    a.label("cap_copy_both_loop")
    a.b("8a540c20"); a.b("88540f08"); a.b("88540f24")
    a.b("41"); a.b("83f91c"); a.j32(JB, "cap_copy_both_loop")
    a.b("31c0"); a.b("894740"); a.b("894744"); a.b("894748"); a.b("89474c"); a.b("88474e")
    a.label("cap_next")
    a.b("43"); a.j32("e9", "cap_slot")
    a.label("cap_slots_done")
    a.b("8b442410"); a.b("85c0"); a.j32(JZ, "cap_hdr_baseline")
    a.b("804d0504")                             # header last-week flag
    a.b("a1" + _imm(WEEK_VA)); a.b("48"); a.b("884509")   # week = current - 1
    a.j32("e9", "cap_team_index")
    a.label("cap_hdr_baseline")
    a.b("c6450503"); a.b("c6450900")
    a.label("cap_team_index")
    a.b("8b0424")
    a.b("8b0d" + _imm(ROSTER_VA)); a.b("8b491c")
    a.b("29c8"); a.b("31d2"); a.b("b9f4010000"); a.b("f7f1")
    a.b("884508")                               # team index
    a.label("cap_done")
    a.b("83c440"); a.b("61"); a.b("c3")
    return a.assemble(), dict(a.labels)


_TEMPLATE, _LABELS = _assemble(0, 0, 0, 0, 0, 0)
_MAP_OFFSET = len(_TEMPLATE)
_TEXT_OFFSET = _MAP_OFFSET + len(MAP)
CODE_SIZE = (_TEXT_OFFSET + len(LAST_WEEK_TEXT) + 15) & ~15
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", 16, 16))


def labels() -> dict[str, int]:
    return dict(_LABELS)


def code_for(code_va: int, data_va: int) -> bytes:
    """The full allocation: cave, row map, "Last Week" string, int3 padding."""
    first, labels_now = _assemble(code_va, data_va, 0, 0,
                                  code_va + _LABELS["capture_baseline"],
                                  code_va + _LABELS["capture_week"])
    map_off = len(first)
    text_off = map_off + len(MAP)
    code, again = _assemble(code_va, data_va, code_va + map_off, code_va + text_off,
                            code_va + labels_now["capture_baseline"],
                            code_va + labels_now["capture_week"])
    _require(len(code) == len(first) and again == labels_now, "cave assembly drifted")
    blob = code + MAP + LAST_WEEK_TEXT
    _require(len(blob) <= CODE_SIZE, "cave does not fit its allocation")
    return blob.ljust(CODE_SIZE, b"\xcc")


def _sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    """Every executable edit: label, VA, retail bytes, patched bytes."""
    lab = _LABELS
    vis = code_va + lab["visibility"]
    stage = code_va + lab["stage_wrapper"]
    week = code_va + lab["week_setter"]
    value = code_va + lab["value"]
    header = code_va + lab["header"]
    toggle = code_va + lab["toggle"]
    return [
        ("visibility", SITE_VISIBILITY[0], SITE_VISIBILITY[1],
         b"\xe9" + _rel32(vis, SITE_VISIBILITY[0])),
        ("stage_new_season", SITE_STAGE_NEW_SEASON[0], SITE_STAGE_NEW_SEASON[1],
         b"\xe8" + _rel32(stage, SITE_STAGE_NEW_SEASON[0])),
        ("stage_next_season", SITE_STAGE_NEXT[0], SITE_STAGE_NEXT[1],
         b"\xe8" + _rel32(stage, SITE_STAGE_NEXT[0])),
        ("week_advance", SITE_WEEK[0], SITE_WEEK[1],
         b"\xe9" + _rel32(week, SITE_WEEK[0]) + b"\x90" * (len(SITE_WEEK[1]) - 5)),
        ("value_getter", SITE_VALUE[0], SITE_VALUE[1],
         b"\xe9" + _rel32(value, SITE_VALUE[0])),
        ("change_header", SITE_HEADER[0], SITE_HEADER[1],
         b"\xe8" + _rel32(header, SITE_HEADER[0])),
        ("event_pointer", SITE_EVENT_POINTER[0], SITE_EVENT_POINTER[1],
         struct.pack("<I", toggle)),
    ]


def allocation(payload: bytes) -> tuple[dict, dict] | None:
    if space.status(payload) == "foreign":
        return None
    rows = space.layout(payload)["allocations"]
    code = [r for r in rows if r["owner"] == OWNER and r["kind"] == "code"]
    data = [r for r in rows if r["owner"] == OWNER and r["kind"] == "data"]
    if not code and not data:
        return None
    _require(len(code) == 1 and len(data) == 1
             and (code[0]["size"], code[0]["align"]) == (CODE_SIZE, 16)
             and (data[0]["size"], data[0]["align"]) == (16, 16),
             "foreign Player Progress allocation")
    return code[0], data[0]


def _guards_ok(image: XbeImage, checked_sites) -> bool:
    for _name, va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _label, at, before, _after in checked_sites:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        if hashlib.sha256(content).hexdigest() != digest:
            return False
    return True


def _recognize(payload: bytes) -> str:
    _require(space.status(payload) != "foreign", "foreign XBE geometry")
    found = allocation(payload)
    image = XbeImage(payload)
    sites = _sites(found[0]["va"] if found else 0x0014DA000)
    if not found:
        states = set()
        for _label, va, before, _after in sites:
            raw = image.read(va, len(before))
            states.add("retail" if raw == before else "foreign")
        _require(states == {"retail"}, "mixed Player Progress sites without an allocation")
        _require(_guards_ok(image, sites), "foreign Player Progress prerequisite")
        return "retail"
    states = set()
    for _label, va, before, after in sites:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if raw == after else "foreign")
    _require(states in ({"retail"}, {"applied"}), "mixed Player Progress sites")
    code_va, data_va = found[0]["va"], found[1]["va"]
    raw = image.read(code_va, CODE_SIZE)
    states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(code_va, data_va) else "foreign")
    _require(states in ({"retail"}, {"applied"}), "foreign Player Progress code")
    _require(_guards_ok(image, sites), "foreign Player Progress prerequisite")
    return next(iter(states))


def status(payload: bytes) -> str:
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install, or replay an identical installation. Needs the growable pool (xs1)."""
    state = _recognize(payload)
    common = {"owner": OWNER, "experimental": True, "code_bytes": CODE_SIZE, "data_bytes": 16,
              "record_file_offset": hex(record.RECORD_FILE_OFFSET),
              "record_runtime_delta": hex(RUNTIME_RECORD_DELTA),
              "record_size": record.RECORD_SIZE, "save_growth": 0}
    if state == "applied":
        return payload, {**common, "status": "already_applied", "changed_bytes": 0, "edits": []}
    before = payload
    if allocation(payload) is None:
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            _require(space.is_scaleout(payload), "Player Progress needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    else:
        allocation_receipt = {}
    code, data = allocation(payload)
    payload, _ = space.install_code(payload, OWNER, code_for(code["va"], data["va"]))
    buf = bytearray(payload)
    image = XbeImage(payload)
    edits = _sites(code["va"])
    for label, va, old, new in edits:
        off = image.offset(va, len(old))
        _require(bytes(buf[off:off + len(old)]) == old, f"Player Progress site {label} is not retail")
        buf[off:off + len(new)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    _require(_recognize(result) == "applied" and space.status(result) == "applied",
             "Player Progress postcondition failed")
    return result, {**common, "status": "applied", "code_va": hex(code["va"]), "data_va": hex(data["va"]),
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest(),
                    "changed_bytes": space.count_differing_bytes(before, result),
                    "file_growth": len(result) - len(before), "allocation": allocation_receipt,
                    "edits": [{"label": label, "va": hex(va), "size": len(old)} for label, va, old, _new in edits],
                    "reservations": [r for r in space.reservations(result) if r["owner"] == OWNER],
                    "hooks": {"visibility": hex(SITE_VISIBILITY[0]), "stage8": [hex(SITE_STAGE_NEW_SEASON[0]),
                              hex(SITE_STAGE_NEXT[0])], "week": hex(SITE_WEEK[0]), "value": hex(SITE_VALUE[0]),
                              "header": hex(SITE_HEADER[0]), "event": hex(SITE_EVENT_POINTER[0])},
                    "integration_order": "after nfl2k5_weekly_progression, before nfl2k5_module_loader"}


__all__ = ["OWNER", "BUILD_CAPTION", "HELP_TEXT", "CODE_SIZE", "REQUESTS", "GUARDS", "SITE_VISIBILITY",
           "SITE_STAGE_NEW_SEASON", "SITE_STAGE_NEXT", "SITE_WEEK", "SITE_VALUE", "SITE_HEADER",
           "SITE_EVENT_POINTER", "PlayerProgressScreenError", "allocation", "apply", "code_for", "labels",
           "status"]

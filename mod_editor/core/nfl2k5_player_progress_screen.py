"""Franchise Player Progress screen and weekly snapshot capture (native owner, EXPERIMENTAL).

Retail's Front Office **Player Progress** screen (descriptor 0x551800) already knows how to show a
player's attributes as ``Previously`` / ``Currently`` / ``+/- Change``. This owner keeps that screen
and makes it useful all season:

* **Visibility** (0x2C26A0): retail shows the Front Office row only in stages 1..4 (the offseason).
  The cave shows it in stages 1..4 and 7..9 (preseason, regular season, playoffs). The
  visibility-only variant installs this patch alone and never grows a save.
* **Season baseline** (0x247B20 call sites 0x13EF03 and 0x248641): when the game enters the regular
  season (stage 8), capture the user team's 65-player roster as the week-0 snapshot.
* **Week advance** (0xC4E60, the game's week setter): after every week of the regular season and
  playoffs, append the new live ratings to the slot's 17-week ring.
* **Screen values** (0x365B20): the season view returns the stored baseline for ``Previously``, the
  live rating for ``Currently`` and their difference for ``Change``. A toggle cycles the historical
  weekly views: ``Previously`` is the previous stored week, ``Currently`` the selected stored week
  and ``Change`` that week's delta. The header shows ``Last Week`` or ``2..8 Weeks``.
* **Toggle** (screen event): any input event the screen currently ignores cycles the view.

The record is the ``PPG3`` v1 history ring and the footer is ``PPGF0001`` in
``nfl2k5_player_progression``. The footer follows the complete native save (and the MyCareer footer
when present); the native save transaction writes and signs it. Old saves have no footer, read as
"no record", and are never changed. The screen never reads the roster-arena tail that froze the
Front Office in b778-pg2.

The owner is a late executable owner. It requests **code 4,096 bytes** and **writable data 34,336
bytes** (16 toggle bytes + the 34,320-byte footer). It needs the growable pool from job xs1. It
composes with the generic MyCareer owner by chaining its displaced size/save/load hooks; MyCareer's
runtime also admits the footer sizes (``tools/mycareer_mode/runtime.c``).
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
VISIBLE_CAPTION = "Franchise: Player Progress row every week"
VISIBLE_HELP_TEXT = (
    "The Front Office Player Progress row is available in the preseason, regular season and playoffs; "
    "retail shows it only in the offseason. This safe half changes no save byte and adds no snapshot."
)
HELP_TEXT = (
    "EXPERIMENTAL. The Front Office Player Progress screen is available every week of the regular "
    "season and playoffs. Previously is the season-opening rating, Currently is the live rating and "
    "+/- Change is movement since the season began; an unused pad button cycles the change row through "
    "Last Week and the previous stored weeks. Old saves load normally."
)

IMAGE_BASE = 0x10000
RECORD_MAGIC = struct.unpack("<I", record.RECORD_MAGIC)[0]          # "PPG3"
FOOTER_MAGIC0 = struct.unpack("<I", record.FOOTER_MAGIC[:4])[0]     # "PPGF"
FOOTER_MAGIC1 = struct.unpack("<I", record.FOOTER_MAGIC[4:])[0]     # "0001"
FOOTER_SIZE = record.FOOTER_SIZE
RECORD_SIZE = record.RECORD_SIZE
RECORD_OFFSET = 16 + record.FOOTER_HEADER_SIZE                       # 48 from the data base
RECORD_VA_DELTA = RECORD_OFFSET
MAP = record.ROW_MAP
HISTORY_WEEKS = record.HISTORY_WEEKS
SLOT_SIZE = record.SLOT_SIZE
SNAPSHOT_SIZE = record.SNAPSHOT_SIZE
RECORD_HEADER_SIZE = record.RECORD_HEADER_SIZE
MAX_VIEW_WEEKS = 8

_TEXT_STRIDE = 24
_TEXTS = ("Last Week", "2 Weeks", "3 Weeks", "4 Weeks", "5 Weeks", "6 Weeks", "7 Weeks", "8 Weeks")
LAST_WEEK_TEXT = b"".join(text.encode("utf-16-le") + b"\0\0" for text in _TEXTS).ljust(
    _TEXT_STRIDE * MAX_VIEW_WEEKS, b"\0")

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
FN_LEAGUE = 0x000C4B80
RETAIL_HEADER_TEXT = 0x00EB92D8

# --- hook sites ---------------------------------------------------------------------------------
SITE_VISIBILITY = (0x002C26A0, bytes.fromhex("568bf2c746"))
SITE_STAGE_NEW_SEASON = (0x0013EF03, bytes.fromhex("e8188c1000"))
SITE_STAGE_NEXT = (0x00248641, bytes.fromhex("e8daf4ffff"))
SITE_WEEK = (0x000C4E60, bytes.fromhex("890db476e500c3"))
SITE_VALUE = (0x00365B20, bytes.fromhex("538b5c240c"))
SITE_HEADER = (0x00365E34, bytes.fromhex("bad892eb00"))
SITE_EVENT_POINTER = (0x000F4268, struct.pack("<I", 0x000F4221))
SITE_TOTAL_SIZE = (0x0016AA26, bytes.fromhex("e8555d1600"))       # call 0x2d0780 (front-office size)
SITE_SAVE_FRONT_OFFICE = (0x0016E50D, bytes.fromhex("e87e221600"))  # call 0x2d0790 (write front office)
SITE_LOAD_END = (0x0016E815, bytes.fromhex("e8661f1600"))          # call 0x2d0780 (after the load)
SITE_ADMISSION = (0x0016ABB5, bytes.fromhex("e856feffffeb13"))     # call 0x16aa10; jmp 0x16abcf

FOOTER_ENTRY_BYTES = (
    (0x0016AA10, bytes.fromhex("56e83affffff")),      # push esi; call 0x16a950
    (0x0016E3F0, bytes.fromhex("81ec24080000")),      # sub esp,0x824
    (0x0016E540, bytes.fromhex("83ec14a1b8bdbd00")),  # sub esp,0x14; mov eax,[0xbdbdb8]
    (0x0016AB70, bytes.fromhex("568d3440c1e603")),    # push esi; lea esi,[eax+eax*2]; shl
)
FOOTER_GUARDS = (
    ("total_size", 0x16AA10, 0x24, "b0e6f1e31f6e6c2e0e5c8a9a4c3a4c0b9c3b6d1f8f6f1a6a7d0b0f2e6b0b7c6d"),
    ("save_front_office", 0x16E3F0, 0x150, "fbafb374865bf17a8d3716f468de28eb31c3119bbccd4282e7a8454dd630fd79"),
    ("load_end", 0x16E540, 0x66, "3fae05e6ebeeeab6f3444b89051944a7cdadeeb3e25e42800f482a936fe747f3"),
    ("admission", 0x16AB70, 0x71, "88b837948a533c94bb6af14d995a8a803d1f7bec9f257f081933ff5f87f7a9af"),
)

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

CODE_SIZE = 4096
DATA_SIZE = 16 + FOOTER_SIZE
TRAILER_SIZE = 24
TRAILER_MAGIC = 0x47505056          # "VPPG"
VARIANT_VISIBLE, VARIANT_FULL = 1, 2
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", (DATA_SIZE + 15) & ~15, 16))


class PlayerProgressScreenError(ValueError):
    """Unsupported executable, foreign installation, or no room for the owner."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlayerProgressScreenError(message)


def _imm(value: int) -> str:
    return struct.pack("<I", value).hex()


def _rel32(target: int, site: int, size: int = 5) -> bytes:
    return struct.pack("<i", target - (site + size))


def _call_target(image: XbeImage, site: int, before: bytes) -> int:
    raw = image.read(site, len(before))
    if raw == before[:5]:
        if raw[0] != 0xE8:
            _require(raw[0] == 0xE9, f"site 0x{site:x} is not a call")
        return site + 5 + struct.unpack("<i", raw[1:5])[0]
    _require(raw[0] == 0xE8 and len(before) >= 5, f"site 0x{site:x} is not a call")
    return site + 5 + struct.unpack("<i", raw[1:5])[0]


def _assemble(code_va: int, data_va: int, map_va: int, text_va: int,
              capture_baseline_va: int, capture_week_va: int,
              size_target: int, save_target: int, load_target: int,
              visible_only: bool = False) -> tuple[bytes, dict[str, int]]:
    """The cave.  All intra-cave call targets are absolute and supplied by the caller."""
    a = _Asm(code_va)
    record_va = data_va + RECORD_VA_DELTA
    footer_va = data_va + 16

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
    a.jmp_abs(0x0014FCD0)                       # retail stage-4 tail
    if visible_only:
        return a.assemble(), dict(a.labels)

    # ---- toggle: cycle season (0) and the stored weeks 1..8 -----------------------------------
    a.label("toggle")
    a.b("5f")                                   # pop edi (the retail event's stack contract)
    a.b("a0" + _imm(data_va))                   # mov al,[toggle]
    a.b("04" + "01")                            # add al,1
    a.b("3c" + f"{MAX_VIEW_WEEKS + 1:02x}")     # cmp al,9
    a.j8("72", "tog_store")                     # jb tog_store
    a.b("30c0")                                 # xor al,al
    a.label("tog_store")
    a.b("a2" + _imm(data_va))                   # mov [toggle],al
    a.b("b801000000")                           # mov eax,1
    a.b("5e")                                   # pop esi
    a.b("c3")

    # ---- change header ------------------------------------------------------------------------
    a.label("header")
    a.b("ba" + _imm(RETAIL_HEADER_TEXT))        # mov edx,retail
    a.b("a0" + _imm(data_va))                   # mov al,[toggle]
    a.b("84c0")                                 # test al,al
    a.j8("74", "hdr_done")
    a.b("0fb6c0")                               # movzx eax,al
    a.b("48")                                   # dec eax
    a.b("6bc0" + f"{_TEXT_STRIDE:02x}")         # imul eax,eax,24
    a.b("8d90" + _imm(text_va))                 # lea edx,[eax+text]
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

    # ---- weekly advance -----------------------------------------------------------------------
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
    a.b("83ec24")                               # sub esp,0x24
    a.b("894c2404")                             # mov [esp+4],ecx (manager)
    a.b("8b442438")                             # mov eax,[esp+0x38] mode
    a.b("8944240c")                             # mov [esp+0x0c],eax
    a.b("8b44243c")                             # mov eax,[esp+0x3c] row
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
    # record present?
    a.b("c744242000000000")                     # [esp+0x20]=0 (record valid)
    a.b("bd" + _imm(record_va))                 # mov ebp,record
    a.b("813d" + _imm(record_va) + _imm(RECORD_MAGIC)); a.j32(JNE, "value_team")
    a.b("807d0401"); a.j32(JNE, "value_team")
    a.b("f6450501"); a.j32(JZ, "value_team")    # header baseline flag
    a.b("c744242001000000")                     # [esp+0x20]=1
    # team pointer: header team index when the record exists
    a.b("a1" + _imm(ROSTER_VA)); a.b("8b401c")  # mov eax,[roster]; mov eax,[eax+0x1c]
    a.b("0fb64d08")                             # movzx ecx,byte [ebp+8]
    a.b("69c9f4010000")                         # imul ecx,ecx,0x1f4
    a.b("01c8")                                 # add eax,ecx
    a.j32("e9", "value_have_team")
    a.label("value_team")
    a.call(FN_TEAM)
    a.label("value_have_team")
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
    a.b("837c242000"); a.j32(JE, "value_retail")   # no valid record
    a.b("89d8"); a.b("69c0" + _imm(SLOT_SIZE))   # mov eax,ebx ; imul eax,eax,527
    a.b("8d7c0520")                             # lea edi,[ebp+eax+0x20] (slot record)
    a.b("89fb")                                 # mov ebx,edi (slot record)
    # identity: pbp_id | position<<16 | jersey<<24
    a.b("0fb74604")                             # movzx eax,word [esi+4]
    a.b("0fb65635")                             # movzx edx,byte [esi+0x35]
    a.b("c1e210"); a.b("09d0")                  # shl edx,16 ; or eax,edx
    a.b("8b5620"); a.b("c1ea03"); a.b("83e27f"); a.b("c1e218"); a.b("09d0")
    a.b("3907"); a.j32(JNE, "value_retail")
    a.b("f6470402"); a.j32(JZ, "value_retail")  # slot baseline flag
    # selected view: 0 = season, 1..count = stored week
    a.b("0fb605" + _imm(data_va))               # movzx eax,byte [toggle]
    a.b("0fb64d0a")                             # movzx ecx,byte [ebp+10] count
    a.b("39c8"); a.j32(JBE, "view_ok")          # cmp eax,ecx ; jbe
    a.b("89c8")                                 # mov eax,ecx
    a.label("view_ok")
    a.b("89442410")                             # mov [esp+0x10],eax (view)
    # field index or overall sentinel in [esp+0x14]
    a.b("8b442408")                             # mov eax,[esp+8] row
    a.b("85c0"); a.j32(JZ, "field_overall")
    a.b("8b4c2404"); a.b("8b4964")              # mov ecx,[list+0x64] group base
    a.b("6bc91a"); a.b("01c1")                  # imul ecx,ecx,26 ; add ecx,eax
    a.b("0fb60c0d" + _imm(map_va))              # movzx ecx,byte [map+ecx]
    a.b("83e936")                               # sub ecx,0x36
    a.b("894c2414")                             # [esp+0x14]=field
    a.j32("e9", "view_values")
    a.label("field_overall")
    a.b("c7442414ffffffff")                     # field = -1
    a.label("view_values")
    a.b("837c241000"); a.j32(JNE, "view_history")
    # ---- season view: previous=baseline, current=live ----
    a.b("837c240800"); a.j32(JNE, "season_rating")
    a.b("8bce"); a.call(FN_OVERALL)             # mov ecx,esi ; call overall
    a.b("89442418")                             # current
    a.b("0fb64705"); a.b("8944241c")            # previous overall
    a.j32("e9", "view_choose")
    a.label("season_rating")
    a.b("8b4c2414")                             # field
    a.b("0fb6440e36"); a.b("89442418")          # current = player[0x36+field]
    a.b("0fb6440f06"); a.b("8944241c")          # previous = slot baseline
    a.j32("e9", "view_choose")
    # ---- history view: previous/current = stored weeks ----
    a.label("view_history")
    a.b("0fb64d0b")                             # movzx ecx,byte [ebp+11] head
    a.b("2b4c2410")                             # sub ecx,[esp+0x10] (T)
    a.b("79" + "03")                            # jns +3 (skip the add)
    a.b("83c1" + f"{HISTORY_WEEKS:02x}")        # add ecx,HISTORY_WEEKS
    a.b("894c2420")                             # [esp+0x20]=index
    a.b("6bc91d")                               # imul ecx,ecx,29
    a.b("89df")                                 # mov edi,ebx (slot record)
    a.b("8d7c0f22")                             # lea edi,[edi+ecx+0x22]
    a.b("837c2414ff"); a.j32(JNE, "hist_rating_cur")
    a.b("0fb6471c"); a.b("89442418")            # current overall
    a.j32("e9", "hist_prev")
    a.label("hist_rating_cur")
    a.b("8b4c2414"); a.b("0fb60c0f"); a.b("894c2418")
    a.label("hist_prev")
    a.b("8b442410")                             # T
    a.b("0fb64d0a")                             # count
    a.b("39c8"); a.j32(JAE, "hist_baseline")    # T >= count -> baseline
    a.b("8b4c2420"); a.b("49"); a.j8("79", "hist_prev_ok")
    a.b("83c1" + f"{HISTORY_WEEKS:02x}")
    a.label("hist_prev_ok")
    a.b("6bc91d")
    a.b("89df")                                 # mov edi,ebx (slot record)
    a.b("8d7c0f22")
    a.b("837c2414ff"); a.j32(JNE, "hist_rating_prev")
    a.b("0fb6471c"); a.b("8944241c")
    a.j32("e9", "view_choose")
    a.label("hist_rating_prev")
    a.b("8b4c2414"); a.b("0fb60c0f"); a.b("894c241c")
    a.j32("e9", "view_choose")
    a.label("hist_baseline")
    a.b("89df")                                 # mov edi,ebx (slot record)
    a.b("837c2414ff"); a.j32(JNE, "hist_rating_base")
    a.b("0fb64705"); a.b("8944241c")            # baseline overall
    a.j32("e9", "view_choose")
    a.label("hist_rating_base")
    a.b("8b4c2414"); a.b("0fb64c0f06"); a.b("894c241c")
    a.label("view_choose")
    a.b("8b44240c")                             # mode
    a.b("85c0"); a.j32(JZ, "mode_previous")
    a.b("83f801"); a.j32(JE, "mode_current")
    a.b("8b442418"); a.b("2b44241c")            # change = current - previous
    a.j32("e9", "mode_store")
    a.label("mode_previous")
    a.b("8b44241c")
    a.j32("e9", "mode_store")
    a.label("mode_current")
    a.b("8b442418")
    a.label("mode_store")
    a.b("83c424"); a.b("5d5f5e5b"); a.b("c20c00")
    a.label("value_retail")
    a.b("83c424"); a.b("5d5f5e5b")              # restore the caller frame
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
    a.b("bd" + _imm(record_va))                 # mov ebp,record
    a.call(FN_LEAGUE)                           # franchise only (league type 2)
    a.b("83f802"); a.j32(JNE, "cap_done")
    a.b("a1" + _imm(ROSTER_VA)); a.b("85c0"); a.j32(JZ, "cap_done")
    a.b("8b401c"); a.b("85c0"); a.j32(JZ, "cap_done")
    a.b("8b442410"); a.b("85c0"); a.j32(JZ, "cap_baseline_team")
    # weekly: only an existing same-year baseline continues
    a.b("813d" + _imm(record_va) + _imm(RECORD_MAGIC)); a.j32(JNE, "cap_baseline_team")
    a.b("807d0401"); a.j32(JNE, "cap_baseline_team")
    a.b("0fb74506")                             # movzx eax,word [record+6]
    a.b("0fb715" + _imm(YEAR_VA))               # movzx edx,word [year]
    a.b("39d0"); a.j32(JNE, "cap_baseline_team")
    a.b("f6450501"); a.j32(JZ, "cap_baseline_team")
    # team from the header index (the controller team can change during simulation)
    a.b("a1" + _imm(ROSTER_VA)); a.b("8b401c")
    a.b("0fb64d08"); a.b("69c9f4010000"); a.b("01c8")
    a.b("890424")                               # [esp]=team
    a.j32("e9", "cap_have_team")
    a.label("cap_baseline_team")
    a.call(FN_TEAM)
    a.b("85c0"); a.j32(JZ, "cap_done")
    a.b("890424")
    # new baseline: footer header and record header
    a.b("c705" + _imm(footer_va) + _imm(FOOTER_MAGIC0))
    a.b("c705" + _imm(footer_va + 4) + _imm(FOOTER_MAGIC1))
    a.b("66c705" + _imm(footer_va + 8) + "0100")
    a.b("66c705" + _imm(footer_va + 10) + "2000")
    a.b("c705" + _imm(footer_va + 12) + _imm(RECORD_SIZE))
    a.b("c74500" + _imm(RECORD_MAGIC))
    a.b("c6450401")                             # version
    a.b("c6450501")                             # flags baseline
    a.b("66a1" + _imm(YEAR_VA)); a.b("66894506")# year
    a.b("c6450900"); a.b("c6450a00"); a.b("c6450b00")
    a.label("cap_have_team")
    a.b("8b0424")                               # team
    a.b("0fb6881c010000")                       # count
    a.b("83f941"); a.j32(JBE, "cap_count_ok")
    a.b("b941000000")
    a.label("cap_count_ok")
    a.b("894c2414")                             # [esp+0x14]=count
    a.b("31db")                                 # xor ebx,ebx
    a.label("cap_slot")
    a.b("3b5c2414"); a.j32(JAE, "cap_slots_done")
    a.b("8b0424"); a.b("8b3498")                # mov eax,[esp] ; mov esi,[eax+ebx*4]
    a.b("85f6"); a.j32(JZ, "cap_next")
    a.b("8974240c")                             # [esp+0x0c]=player
    a.b("89d8"); a.b("69c0" + _imm(SLOT_SIZE))  # mov eax,ebx ; imul eax,SLOT_SIZE
    a.b("8d7c0520")                             # lea edi,[ebp+eax+0x20]
    a.b("897c2418")                             # [esp+0x18]=slot
    a.b("8bce"); a.call(FN_OVERALL)
    a.b("8944241c")                             # [esp+0x1c]=overall
    a.b("8b74240c")
    a.b("0fb74604"); a.b("0fb65635"); a.b("c1e210"); a.b("09d0")
    a.b("8b5620"); a.b("c1ea03"); a.b("83e27f"); a.b("c1e218"); a.b("09d0")
    a.b("8b7c2418")
    a.b("3907"); a.j32(JE, "cap_same")
    # new/renumbered player: reset this slot to the live values
    a.b("8907")
    a.b("8b44241c"); a.b("884705")
    a.b("c6470403")                             # identity + baseline
    a.b("31c9")
    a.label("cap_reset_copy")
    a.b("8a540e36"); a.b("88540f06")
    a.b("41"); a.b("83f91c"); a.j32(JB, "cap_reset_copy")
    a.b("31c9")                                 # ecx = snapshot index
    a.label("cap_reset_snap")
    a.b("89c8"); a.b("6bc01d")                  # eax = ecx*29
    a.b("8d540722")                             # edx = edi+eax+0x22
    a.b("31f6")                                 # esi = rating index
    a.label("cap_reset_rat")
    a.b("8a443706"); a.b("880432")              # al=[edi+esi+6]; [edx+esi]=al
    a.b("46"); a.b("83fe1c"); a.j32(JB, "cap_reset_rat")
    a.b("8a4705"); a.b("88421c")                # snapshot overall = baseline overall
    a.b("41"); a.b("83f911"); a.j32(JB, "cap_reset_snap")
    a.j32("e9", "cap_next")
    a.label("cap_same")
    a.b("8b442410"); a.b("85c0"); a.j32(JZ, "cap_week_snapshot")
    # weekly capture writes the ring at head
    a.b("0fb6450b")                             # head
    a.b("6bc01d")                               # *29
    a.b("8d540722")                             # lea edx,[edi+eax+0x22]
    a.b("31c9")
    a.label("cap_week_copy")
    a.b("8a440e36"); a.b("88440a00")            # al=player rating; [edx+ecx]=al
    a.b("41"); a.b("83f91c"); a.j32(JB, "cap_week_copy")
    a.b("8b44241c"); a.b("88421c")              # snapshot overall
    a.j32("e9", "cap_next")
    a.label("cap_week_snapshot")
    a.j32("e9", "cap_next")
    a.label("cap_next")
    a.b("43"); a.j32("e9", "cap_slot")
    a.label("cap_slots_done")
    a.b("8b442410"); a.b("85c0"); a.j32(JZ, "cap_baseline_header")
    # advance the ring and header
    a.b("0fb6450b"); a.b("40"); a.b("83f811"); a.j8("72", "cap_head_ok")
    a.b("31c0")
    a.label("cap_head_ok")
    a.b("88450b")
    a.b("0fb6450a"); a.b("40"); a.b("83f811"); a.j8("76", "cap_count_ok2")
    a.b("b811000000")
    a.label("cap_count_ok2")
    a.b("88450a")
    a.b("804d0502")                             # history flag
    a.b("a1" + _imm(WEEK_VA)); a.b("48"); a.b("884509")
    a.j32("e9", "cap_team_index")
    a.label("cap_baseline_header")
    a.b("c6450501"); a.b("c6450900")
    a.label("cap_team_index")
    a.b("8b0424")                               # team pointer
    a.b("8b0d" + _imm(ROSTER_VA)); a.b("8b491c")
    a.b("29c8"); a.b("31d2"); a.b("b9f4010000"); a.b("f7f1")
    a.b("884508")                               # team index
    a.label("cap_done")
    a.b("83c440"); a.b("61"); a.b("c3")

    # ---- footer hooks -------------------------------------------------------------------------
    a.label("size_hook")
    a.call(size_target)
    a.b("05" + _imm(FOOTER_SIZE))               # add eax,FOOTER_SIZE
    a.b("c3")

    a.label("save_hook")
    a.b("51")                                   # push ecx
    a.call(save_target)
    a.b("83c404")                               # add esp,4
    a.b("9c")                                   # pushfd
    a.b("60")                                   # pushad
    a.b("8b5c2410")                             # mov ebx,[esp+0x10] (saved EBX)
    a.b("81fb" + _imm(FOOTER_SIZE)); a.j32(JB, "save_done")
    a.b("8b742404")                             # mov esi,[esp+4] (saved ESI)
    a.b("89f7")                                 # mov edi,esi
    a.b("01df")                                 # add edi,ebx
    a.b("81ef" + _imm(FOOTER_SIZE))
    a.b("be" + _imm(footer_va))                 # mov esi,footer
    a.b("b9" + _imm(FOOTER_SIZE))
    a.b("fc")                                   # cld
    a.b("f3a4")                                 # rep movsb
    a.label("save_done")
    a.b("61"); a.b("9d"); a.b("c3")             # popad ; popfd ; ret

    a.label("load_hook")
    a.call(load_target)
    a.b("9c"); a.b("60")
    a.b("8b85ccc1bd00")                         # mov eax,[ebp+0xbdc1cc] (file size)
    a.b("3d" + _imm(FOOTER_SIZE)); a.j32(JB, "load_clear")
    a.b("89f7")                                 # mov edi,esi (file buffer)
    a.b("01c7")                                 # add edi,eax
    a.b("81ef" + _imm(FOOTER_SIZE))
    a.b("813f" + _imm(FOOTER_MAGIC0)); a.j32(JNE, "load_clear")
    a.b("817f04" + _imm(FOOTER_MAGIC1)); a.j32(JNE, "load_clear")
    a.b("66817f080100"); a.j32(JNE, "load_clear")
    a.b("66817f0a2000"); a.j32(JNE, "load_clear")
    a.b("817f0c" + _imm(RECORD_SIZE)); a.j32(JNE, "load_clear")
    a.b("89fe")                                 # mov esi,edi
    a.b("bf" + _imm(footer_va))                 # mov edi,footer
    a.b("b9" + _imm(FOOTER_SIZE))
    a.b("fc"); a.b("f3a4")
    a.j32("e9", "load_done")
    a.label("load_clear")
    a.b("bf" + _imm(footer_va))
    a.b("31c0")
    a.b("b9" + _imm(FOOTER_SIZE // 4))
    a.b("fc"); a.b("f3ab")                      # rep stosd
    a.label("load_done")
    a.b("61"); a.b("9d"); a.b("c3")

    a.label("admission")
    a.b("8b8eccc1bd00")                         # mov ecx,[esi+0xbdc1cc] (file size)
    a.b("8b15" + _imm(0x00B72808))              # mov edx,[0xb72808] (arena size)
    a.b("b8" + _imm(record.RETAIL_SAVE_SIZE))
    a.b("81fa" + _imm(0x000B0000)); a.j8("72", "adm_92")
    a.b("b8" + _imm(record.CAPACITY_SAVE_SIZE)); a.j8("eb", "adm_base")
    a.label("adm_92")
    a.b("81fa" + _imm(0x00092000)); a.j8("72", "adm_base")
    a.b("b8" + _imm(record.RESERVE_SAVE_SIZE))
    a.label("adm_base")
    a.b("39c1"); a.j8("74", "adm_ok")
    a.b("8d90" + _imm(record.MYCAREER_FOOTER_SIZE)); a.b("39d1"); a.j8("74", "adm_ok")
    a.b("8d90" + _imm(FOOTER_SIZE)); a.b("39d1"); a.j8("74", "adm_ok")
    a.b("8d90" + _imm(record.MYCAREER_FOOTER_SIZE + FOOTER_SIZE)); a.b("39d1"); a.j8("74", "adm_ok")
    a.b("81f9" + _imm(record.RETAIL_SAVE_SIZE)); a.j8("74", "adm_ok")
    a.b("81f9" + _imm(record.RETAIL_SAVE_SIZE + record.MYCAREER_FOOTER_SIZE)); a.j8("74", "adm_ok")
    a.b("81f9" + _imm(record.RETAIL_SAVE_SIZE + FOOTER_SIZE)); a.j8("74", "adm_ok")
    a.b("81f9" + _imm(record.RETAIL_SAVE_SIZE + record.MYCAREER_FOOTER_SIZE + FOOTER_SIZE)); a.j8("74", "adm_ok")
    a.b("b801000000"); a.b("5e"); a.b("c3")     # mov eax,1 ; pop esi ; ret (damaged)
    a.label("adm_ok")
    a.b("31c0"); a.b("5e"); a.b("c3")
    return a.assemble(), dict(a.labels)


def _trailer(variant: int, size_target: int, save_target: int, load_target: int,
             native_admission: bool = True) -> bytes:
    return struct.pack("<IIIIII", TRAILER_MAGIC, variant, size_target, save_target, load_target,
                       int(native_admission))


def _finish(blob: bytes, variant: int, size_target: int, save_target: int, load_target: int,
            native_admission: bool = True) -> bytes:
    _require(len(blob) <= CODE_SIZE - TRAILER_SIZE, "cave does not fit its allocation")
    tail = _trailer(variant, size_target, save_target, load_target, native_admission)
    return blob.ljust(CODE_SIZE - TRAILER_SIZE, b"\xcc") + tail


_TEMPLATE, _LABELS = _assemble(0, 0, 0, 0, 0, 0, 0, 0, 0)
_MAP_OFFSET = len(_TEMPLATE)
_TEXT_OFFSET = _MAP_OFFSET + len(MAP)
_VISIBLE_TEMPLATE, _VISIBLE_LABELS = _assemble(0, 0, 0, 0, 0, 0, 0, 0, 0, visible_only=True)
_TRAILERS = ()


def labels() -> dict[str, int]:
    return dict(_LABELS)


def _code(visible_only: bool, code_va: int, data_va: int,
          size_target: int, save_target: int, load_target: int,
          use_native_admission: bool = True) -> bytes:
    if visible_only:
        first, labels_now = _assemble(code_va, data_va, 0, 0, 0, 0, 0, 0, 0, visible_only=True)
        _require(len(first) == len(_VISIBLE_TEMPLATE) and labels_now == _VISIBLE_LABELS,
                 "visibility cave assembly drifted")
        return _finish(first, VARIANT_VISIBLE, 0, 0, 0)
    first, labels_now = _assemble(code_va, data_va, 0, 0, 0, 0, 0, 0, 0)
    map_off = len(first)
    text_off = map_off + len(MAP)
    code, again = _assemble(code_va, data_va, code_va + map_off, code_va + text_off,
                            code_va + labels_now["capture_baseline"],
                            code_va + labels_now["capture_week"],
                            size_target, save_target, load_target)
    _require(len(code) == len(first) and again == labels_now, "cave assembly drifted")
    blob = code + MAP + LAST_WEEK_TEXT
    return _finish(blob, VARIANT_FULL, size_target, save_target, load_target, use_native_admission)


def code_for(code_va: int, data_va: int, targets: tuple[int, int, int] | None = None,
             use_native_admission: bool = True) -> bytes:
    """The full allocation: cave, row map, week labels, int3 padding and the hook trailer."""
    size_target, save_target, load_target = targets or (0x002D0780, 0x002D0790, 0x002D0780)
    return _code(False, code_va, data_va, size_target, save_target, load_target, use_native_admission)


def visible_code_for(code_va: int) -> bytes:
    return _code(True, code_va, 0, 0, 0, 0)


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


def _footer_sites(code_va: int, include_admission: bool = True) -> list[tuple[str, int, bytes, bytes]]:
    lab = _LABELS
    sites = [
        ("total_size", SITE_TOTAL_SIZE[0], SITE_TOTAL_SIZE[1],
         b"\xe8" + _rel32(code_va + lab["size_hook"], SITE_TOTAL_SIZE[0])),
        ("save_front_office", SITE_SAVE_FRONT_OFFICE[0], SITE_SAVE_FRONT_OFFICE[1],
         b"\xe8" + _rel32(code_va + lab["save_hook"], SITE_SAVE_FRONT_OFFICE[0])),
        ("load_end", SITE_LOAD_END[0], SITE_LOAD_END[1],
         b"\xe8" + _rel32(code_va + lab["load_hook"], SITE_LOAD_END[0])),
    ]
    if include_admission:
        sites.append(("admission", SITE_ADMISSION[0], SITE_ADMISSION[1],
                      b"\xe9" + _rel32(code_va + lab["admission"], SITE_ADMISSION[0])
                      + b"\x90" * (len(SITE_ADMISSION[1]) - 5)))
    return sites


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
             and (data[0]["size"], data[0]["align"]) == (REQUESTS[1][2], 16),
             "foreign Player Progress allocation")
    return code[0], data[0]


def _trailer_at(image: XbeImage, code_va: int) -> tuple[int, int, int, int, bool] | None:
    raw = image.read(code_va + CODE_SIZE - TRAILER_SIZE, TRAILER_SIZE)
    magic, variant, size_target, save_target, load_target, native_admission = struct.unpack("<IIIIII", raw)
    if magic != TRAILER_MAGIC or variant not in (VARIANT_VISIBLE, VARIANT_FULL) or native_admission > 1:
        return None
    return variant, size_target, save_target, load_target, bool(native_admission)


def _save_prerequisites_ok(image: XbeImage) -> bool:
    return all(image.read(va, len(expected)) == expected for va, expected in FOOTER_ENTRY_BYTES)


def _guards_ok(image: XbeImage, checked_sites) -> bool:
    for _name, va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _label, at, before, _after in checked_sites:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        if hashlib.sha256(content).hexdigest() != digest:
            return False
    return True


def _site_states(image: XbeImage, sites) -> set[str]:
    states = set()
    for _label, va, before, after in sites:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if raw == after else "foreign")
    return states


def _footer_prerequisite_ok(image: XbeImage, site) -> bool:
    """Retail, or the generic MyCareer owner's displaced call/jump at that same site."""
    _label, va, before, after = site
    raw = image.read(va, len(before))
    if raw == before or raw == after:
        return True
    if va == SITE_ADMISSION[0]:
        return raw[0] in (0xE8, 0xE9)
    return raw[0] == 0xE8


def _displaced_targets(image: XbeImage) -> tuple[int, int, int]:
    return (_call_target(image, SITE_TOTAL_SIZE[0], SITE_TOTAL_SIZE[1]),
            _call_target(image, SITE_SAVE_FRONT_OFFICE[0], SITE_SAVE_FRONT_OFFICE[1]),
            _call_target(image, SITE_LOAD_END[0], SITE_LOAD_END[1]))


def _recognize(payload: bytes) -> str:
    _require(space.status(payload) != "foreign", "foreign XBE geometry")
    found = allocation(payload)
    image = XbeImage(payload)
    if not found:
        sites = _sites(0x0014DA000)
        _require(_site_states(image, sites) == {"retail"}, "mixed Player Progress sites without an allocation")
        _require(_guards_ok(image, sites), "foreign Player Progress prerequisite")
        _require(_save_prerequisites_ok(image), "foreign franchise save routine")
        return "retail"
    code_va, data_va = found[0]["va"], found[1]["va"]
    trailer = _trailer_at(image, code_va)
    if trailer is None:
        _require(_site_states(image, _sites(code_va)) == {"retail"},
                 "mixed Player Progress sites without a trailer")
        _require(all(_footer_prerequisite_ok(image, site) for site in _footer_sites(code_va)),
                 "foreign franchise save hooks without a trailer")
        _require(image.read(code_va, CODE_SIZE) == b"\xcc" * CODE_SIZE,
                 "foreign Player Progress code without a trailer")
        _require(_guards_ok(image, _sites(code_va)), "foreign Player Progress prerequisite")
        _require(_save_prerequisites_ok(image), "foreign franchise save routine")
        return "retail"
    variant, size_target, save_target, load_target, native_admission = trailer
    full_sites = _sites(code_va) + _footer_sites(code_va, include_admission=not native_admission)
    visible = _sites(code_va)[:1]
    if variant == VARIANT_VISIBLE:
        states = _site_states(image, visible)
        _require(states in ({"retail"}, {"applied"}), "mixed visibility sites")
        rest = _site_states(image, _sites(code_va)[1:])
        _require(rest == {"retail"}, "visibility-only build has extra Player Progress edits")
        _require(all(_footer_prerequisite_ok(image, site) for site in _footer_sites(code_va,
                                                                                   include_admission=False)),
                 "visibility-only build has foreign franchise save hooks")
        raw = image.read(code_va, CODE_SIZE)
        expected = visible_code_for(code_va)
        _require(raw == expected, "foreign visibility-only code")
        _require(_guards_ok(image, visible), "foreign Player Progress prerequisite")
        return "visible" if states == {"applied"} else "retail"
    states = _site_states(image, full_sites)
    _require(states in ({"retail"}, {"applied"}), "mixed Player Progress sites")
    if native_admission:
        _require(image.read(SITE_ADMISSION[0], 1) == b"\xe9",
                 "the native admission hook this build chains to is gone")
    raw = image.read(code_va, CODE_SIZE)
    expected = code_for(code_va, data_va, (size_target, save_target, load_target),
                        use_native_admission=native_admission)
    _require(raw == expected, "foreign Player Progress code")
    _require(_guards_ok(image, full_sites), "foreign Player Progress prerequisite")
    return "applied" if states == {"applied"} else "retail"


def status(payload: bytes) -> str:
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def variant(payload: bytes) -> str | None:
    try:
        found = allocation(payload)
        if not found:
            return None
        trailer = _trailer_at(XbeImage(payload), found[0]["va"])
        if trailer is None:
            return None
        if trailer[0] == VARIANT_VISIBLE:
            return "visible" if _recognize(payload) == "visible" else None
        return "full" if _recognize(payload) == "applied" else None
    except _ERRORS:
        return None


def apply(payload: bytes, *, visible_only: bool = False) -> tuple[bytes, Mapping[str, object]]:
    """Install (or replay) the owner.  Needs the growable pool (xs1)."""
    state = _recognize(payload)
    common = {"owner": OWNER, "experimental": True, "code_bytes": CODE_SIZE,
              "data_bytes": REQUESTS[1][2], "record_size": RECORD_SIZE,
              "footer_size": FOOTER_SIZE, "save_growth": 0 if visible_only else FOOTER_SIZE}
    if state == "visible" and visible_only:
        return payload, {**common, "status": "already_applied", "changed_bytes": 0, "edits": []}
    if state == "applied" and not visible_only:
        return payload, {**common, "status": "already_applied", "changed_bytes": 0, "edits": []}
    _require(state in ("retail", "visible"), "foreign Player Progress installation")
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
    image = XbeImage(payload)
    targets = (0x002D0780, 0x002D0790, 0x002D0780)
    use_native_admission = False
    if not visible_only:
        targets = _displaced_targets(image)
    blob = _code(visible_only, code["va"], data["va"], *targets,
                 use_native_admission=use_native_admission)
    payload, _ = space.install_code(payload, OWNER, blob)
    buf = bytearray(payload)
    image = XbeImage(payload)
    edits = (_sites(code["va"])[:1] if visible_only else
             _sites(code["va"]) + _footer_sites(code["va"], include_admission=not use_native_admission))
    for label, va, old, new in edits:
        off = image.offset(va, len(old))
        raw = bytes(buf[off:off + len(old)])
        if label == "visibility" and raw != old:
            _require(raw == new, "visibility site is neither retail nor this owner")
            continue
        if label in ("total_size", "save_front_office", "load_end", "admission") and raw != old:
            _require(_footer_prerequisite_ok(image, next(site for site in _footer_sites(code["va"])
                                                        if site[0] == label)),
                     f"Player Progress site {label} is neither retail nor a MyCareer hook")
        else:
            _require(raw == old, f"Player Progress site {label} is not retail")
        buf[off:off + len(new)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    final_state = "visible" if visible_only else "applied"
    _require(_recognize(result) == final_state and space.status(result) == "applied",
             "Player Progress postcondition failed")
    return result, {**common, "status": "applied", "variant": final_state,
                    "native_admission": use_native_admission,
                    "code_va": hex(code["va"]), "data_va": hex(data["va"]),
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest(),
                    "changed_bytes": space.count_differing_bytes(before, result),
                    "file_growth": len(result) - len(before), "allocation": allocation_receipt,
                    "edits": [{"label": label, "va": hex(va), "size": len(old)} for label, va, old, _new in edits],
                    "reservations": [r for r in space.reservations(result) if r["owner"] == OWNER],
                    "hooks": {"visibility": hex(SITE_VISIBILITY[0]),
                              "stage8": [hex(SITE_STAGE_NEW_SEASON[0]), hex(SITE_STAGE_NEXT[0])],
                              "week": hex(SITE_WEEK[0]), "value": hex(SITE_VALUE[0]),
                              "header": hex(SITE_HEADER[0]), "event": hex(SITE_EVENT_POINTER[0]),
                              "total_size": hex(SITE_TOTAL_SIZE[0]),
                              "save_front_office": hex(SITE_SAVE_FRONT_OFFICE[0]),
                              "load_end": hex(SITE_LOAD_END[0]), "admission": hex(SITE_ADMISSION[0])},
                    "integration_order": "after nfl2k5_weekly_progression, before nfl2k5_module_loader"}


__all__ = ["OWNER", "BUILD_CAPTION", "HELP_TEXT", "VISIBLE_CAPTION", "VISIBLE_HELP_TEXT", "CODE_SIZE", "DATA_SIZE", "REQUESTS", "GUARDS",
           "SITE_VISIBILITY", "SITE_STAGE_NEW_SEASON", "SITE_STAGE_NEXT", "SITE_WEEK", "SITE_VALUE",
           "SITE_HEADER", "SITE_EVENT_POINTER", "SITE_TOTAL_SIZE", "SITE_SAVE_FRONT_OFFICE",
           "SITE_LOAD_END", "SITE_ADMISSION", "PlayerProgressScreenError", "allocation", "apply",
           "code_for", "labels", "status", "variant", "visible_code_for"]

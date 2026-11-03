"""The Player Progress screen's code and sites as beta-79 (e8c1de3a8, SOFTDRINK 2K28 v0.8) shipped them.

b780 n6: frozen, generator only (no status or apply). beta-80 changed this owner (b9: the weekly views moved from
the shared event slot 0xF4268 to the screen's own descriptor 0x551808; j23: the hosted variant and the footer
family), so a v0.8 executable carries this older code. ``nfl2k5_player_progress_screen`` reads that exact install as
"previous" (and lets MyCareer see its own footer hooks through it), and refuses to update it in place. This is
e8c1de3a8's module from ``from __future__`` up to (not including) ``allocation``.
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
    "+/- Change is movement since the season began. Old saves load normally."
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
SITE_GAME_END = (0x001353FC, bytes.fromhex("e8cff9ffff"))         # call 0x134dd0 (second club's stat merge)
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
    ("value_helper", 0x00365B00, 0x20, "dad1bbfe0d3f155a9df8c341622a44c234916fab956417d50aedf95d0c765f90"),
    ("value_table", 0x00AEFBFC, 0x1A0, "bde9a060b25ade38914a074c95b2081548f543a11374a1ed3823955c02e0cda5"),
    ("header_context", 0x00365E20, 0x40, "6dc7bfaa61f1a2be4c695787a43399bd999f0177c29a22ced3522b6e19c00c2e"),
    ("screen_descriptor", 0x00551800, 0x30, "f0523debaafd92b19ddc1483b39be14ac2219e7b9e8ff514daed9daee45ee166"),
    ("new_season", 0x0013EEF0, 0x20, "bce2d9b67db13d51774a43fe7763853d75bb0b4c2c50d42ec32661f226e078e9"),
    ("next_season", 0x00248628, 0x28, "0f8174c1515f9c934e742a3cc8e14cf872ff9f6a74d399681900641f7fc3d403"),
    ("week_advance", 0x000C5D14, 0x20, "eb8c8b928d15c51927b2be3d9d9be47d125ca6330ddf56f7814e814547e6ce79"),
    ("game_end", 0x001353D0, 0x40, "43aeb9adc0db3244104a928fe684f2915a6c8f34478a62f78828976d92c5f9e6"),
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

    # ---- stable row label (b779-pp5) ----------------------------------------------------------
    # The old toggle sat on the screen's ignored-event class, which is a per-frame event (event 9):
    # it incremented on every frame and the label cycled at frame rate. No distinct Black/UP/DOWN
    # event reaches this class, so a reliable button gate is not available here. The released fix
    # keeps the season row ("+/- Change") and leaves the stored weekly ring for a future, properly
    # screen-scoped switcher. Both hooks stay installed so the install layout is unchanged; the
    # handler is the retail no-op and the header returns the retail string.
    a.label("toggle")
    a.b("5f")                                   # pop edi (the retail event's stack contract)
    a.b("b801000000")                           # mov eax,1
    a.b("5e")                                   # pop esi
    a.b("c3")

    a.label("header")
    a.b("ba" + _imm(RETAIL_HEADER_TEXT))        # mov edx,retail "+/- Change"
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
    a.b("85db"); a.j8("74", "week_done")        # a real week (not the stage-enter reset to 0)
    a.b("83fb11"); a.j8("77", "week_done")      # and not past 17
    a.b("8d5601")                               # lea edx,[esi+1]
    a.b("39d3"); a.j8("75", "week_done")        # cmp ebx,edx ; jne done
    a.call(code_va + _HELPERS.get("capture_ensure", 0))
    a.label("week_done")
    a.b("61")                                   # popad
    a.b("c3")

    # ---- value getter -------------------------------------------------------------------------
    # The game's own 0x365B00 value helper computes every visible attribute (some are sums or
    # tables, not one byte), so the screen asks it for both sides of the comparison.  The stored
    # side is staged into the live player's 28 ratings, read, and restored.
    a.label("value")
    a.b("53565755")                             # push ebx,esi,edi,ebp
    a.b("83ec48")                               # sub esp,0x48
    a.b("8b44245c")                             # mov eax,[esp+0x5c] mode
    a.b("8944242c")                             # [esp+0x2c]=mode
    a.b("8b442460")                             # mov eax,[esp+0x60] row
    a.b("89442428")                             # [esp+0x28]=row
    a.b("894c241c")                             # [esp+0x1c]=ecx (manager)
    a.b("894c2418")                             # [esp+0x18]=ecx, kept for the retail fallback (b778 pp1)
    a.b("8b4c241c"); a.call(FN_LIST)
    a.b("85c0"); a.j32(JZ, "value_retail")
    a.b("8944241c")                             # [esp+0x1c]=list record
    a.b("8bc8"); a.call(FN_LIST_INDEX)
    a.b("8b4c241c")                             # mov ecx,[esp+0x1c]
    a.b("3b81a4000000")                         # cmp eax,[ecx+0xa4]
    a.j32(JAE, "value_retail")
    a.b("8b5140")                               # mov edx,[ecx+0x40]
    a.b("8b0482")                               # mov eax,[edx+eax*4]
    a.b("85c0"); a.j32(JZ, "value_retail")
    a.b("89442420")                             # [esp+0x20]=player
    # record present?  The roster order is not stable across a week, so the slot is found by
    # identity (pbp_id | position << 16 | jersey << 24), never by the current list index.
    a.b("bd" + _imm(record_va))                 # mov ebp,record
    a.b("813d" + _imm(record_va) + _imm(RECORD_MAGIC)); a.j32(JNE, "value_retail")
    a.b("807d0401"); a.j32(JNE, "value_retail")
    a.b("f6450501"); a.j32(JZ, "value_retail")  # header baseline flag
    a.b("8b742420")                             # mov esi,[esp+0x20] (player)
    a.call(code_va + _HELPERS.get("identity", 0))
    a.call(code_va + _HELPERS.get("slot_for_identity", 0))
    a.b("85ff"); a.j32(JZ, "value_retail")
    a.b("897c2440")                             # [esp+0x40]=slot
    # selected column group
    a.b("8b44241c"); a.b("8b4064")              # mov eax,[list+0x64]
    a.b("89442424")                             # [esp+0x24]=group
    # selected view: 0 = season, 1..count = stored week
    a.b("0fb605" + _imm(data_va))               # movzx eax,byte [toggle]
    a.b("0fb64d0a")                             # movzx ecx,byte [record+10] count
    a.b("39c8"); a.j32(JBE, "view_ok")          # cmp eax,ecx ; jbe
    a.b("89c8")                                 # mov eax,ecx
    a.label("view_ok")
    a.b("89442430")                             # [esp+0x30]=view
    # current/previous staging pointers
    a.b("837c243000"); a.j32(JNE, "view_history")
    a.b("c744243c00000000")                     # season current = live
    a.b("8b442440"); a.b("83c006")              # season previous = slot baseline
    a.b("89442444")
    a.j32("e9", "sources_done")
    a.label("view_history")
    a.b("0fb64d0b")                             # movzx ecx,byte [record+11] head
    a.b("2b4c2430")                             # sub ecx,[esp+0x30] (view)
    a.b("7903")                                 # jns +3
    a.b("83c111")                               # add ecx,HISTORY_WEEKS
    a.b("894c2434")                             # [esp+0x34]=index
    a.b("89c8")                                 # mov eax,ecx
    a.b("6bc01d")                               # imul eax,eax,29
    a.b("03442440")                             # add eax,[esp+0x40] (slot)
    a.b("83c022")                               # add eax,0x22
    a.b("8944243c")                             # [esp+0x3c]=current source
    a.b("8b442430")                             # view
    a.b("0fb64d0a")                             # count
    a.b("39c8"); a.j32(JAE, "hist_base")        # view >= count -> baseline
    a.b("8b4c2434")                             # ecx=index
    a.b("49")                                   # dec ecx
    a.b("7903")
    a.b("83c111")
    a.b("89c8"); a.b("6bc01d"); a.b("03442440"); a.b("83c022")
    a.b("89442444")                             # previous source
    a.j32("e9", "sources_done")
    a.label("hist_base")
    a.b("8b442440"); a.b("83c006")              # previous = slot baseline
    a.b("89442444")
    a.label("sources_done")
    a.b("837c242800"); a.j32(JNE, "value_rating")
    # ---- overall row (stored overall for previous/history, live overall for the season current)
    a.b("837c243000"); a.j32(JNE, "hist_overall")
    a.b("8b4c2420"); a.call(FN_OVERALL)         # mov ecx,player ; call overall
    a.b("89442434")                             # current
    a.b("8b442440"); a.b("0fb64805")            # movzx ecx,byte [slot+5]
    a.b("894c2438")                             # previous
    a.j32("e9", "view_choose")
    a.label("hist_overall")
    a.b("8b44243c"); a.b("0fb6481c")            # current = snapshot overall
    a.b("894c2434")
    a.b("8b442430")                             # view
    a.b("0fb64d0a")                             # count
    a.b("39c8"); a.j8("72", "hist_overall_snap")  # view < count -> previous snapshot
    a.b("8b442440"); a.b("0fb64805")            # view == count -> baseline overall
    a.b("894c2438")
    a.j32("e9", "view_choose")
    a.label("hist_overall_snap")
    a.b("8b442444"); a.b("0fb6481c")            # previous = previous snapshot overall
    a.b("894c2438")
    a.j32("e9", "view_choose")
    # ---- rating row: the game's own helper, with the stored ratings staged in
    a.label("value_rating")
    a.b("8b4c2420")                             # ecx=player
    a.b("8b442424")                             # eax=group
    a.b("8b542428")                             # edx=row
    a.b("8b7c243c")                             # edi=current source
    a.call(code_va + _HELPERS.get("calc_value", 0))
    a.b("89442434")                             # current
    a.b("8b4c2420"); a.b("8b442424"); a.b("8b542428")
    a.b("8b7c2444")                             # edi=previous source
    a.call(code_va + _HELPERS.get("calc_value", 0))
    a.b("89442438")                             # previous
    a.label("view_choose")
    a.b("8b44242c")                             # mode
    a.b("85c0"); a.j32(JZ, "mode_previous")
    a.b("83f801"); a.j32(JE, "mode_current")
    a.b("8b442434"); a.b("2b442438")            # change = current - previous
    a.j32("e9", "mode_store")
    a.label("mode_previous")
    a.b("8b442438")
    a.j32("e9", "mode_store")
    a.label("mode_current")
    a.b("8b442434")
    a.label("mode_store")
    a.b("83c448"); a.b("5d5f5e5b"); a.b("c20c00")
    a.label("value_retail")
    # b778 pp1: the retail getter takes the screen manager in ECX (its first call, 0xF31B0, reads the list
    # through it). [esp+0x1c] holds the list record by now and ECX whatever the last call left, so on a
    # franchise with no record yet the fallback bugchecked at 0xF31B6 (Front Office > Player Progress froze).
    a.b("8b4c2418")                             # mov ecx,[esp+0x18] (the manager)
    a.b("83c448"); a.b("5d5f5e5b")              # restore the caller frame
    a.b("53"); a.b("8b5c240c")                  # replay the retail prologue
    a.jmp_abs(0x00365B25)

    # ---- identity helpers ---------------------------------------------------------------------
    a.label("identity")                         # esi = player -> eax = pbp | position << 16 | jersey << 24
    a.b("0fb74604")                             # movzx eax,word [esi+4]
    a.b("0fb65635")                             # movzx edx,byte [esi+0x35]
    a.b("c1e210"); a.b("09d0")                  # shl edx,16 ; or eax,edx
    a.b("8b5620"); a.b("c1ea03"); a.b("83e27f"); a.b("c1e218"); a.b("09d0")
    a.b("c3")

    a.label("slot_for_identity")                # eax = identity, ebp = record -> edi = slot or 0
    a.b("31c9")                                 # xor ecx,ecx
    a.label("sfi_loop")
    a.b("89ca"); a.b("69d2" + _imm(SLOT_SIZE))  # mov edx,ecx ; imul edx,edx,527
    a.b("8d7c1520")                             # lea edi,[ebp+edx+0x20]
    a.b("3907")                                 # cmp dword [edi],eax
    a.j8("75", "sfi_next")
    a.b("f6470401")                             # test byte [edi+4],1
    a.j8("74", "sfi_next")
    a.b("c3")
    a.label("sfi_next")
    a.b("41"); a.b("83f941"); a.j8("72", "sfi_loop")
    a.b("31ff")                                 # xor edi,edi
    a.b("c3")

    a.label("free_slot")                        # ebp = record -> edi = empty slot or 0
    a.b("31c9")
    a.label("fs_loop")
    a.b("89ca"); a.b("69d2" + _imm(SLOT_SIZE))
    a.b("8d7c1520")
    a.b("833f00")                               # cmp dword [edi],0
    a.j8("74", "fs_done")
    a.b("41"); a.b("83f941"); a.j8("72", "fs_loop")
    a.b("31ff")
    a.label("fs_done")
    a.b("c3")

    a.label("calc_value")                       # ecx=player, eax=group, edx=row, edi=source (0=live)
    a.b("53565755")                             # push ebx,esi,edi,ebp
    a.b("83ec20")                               # sub esp,0x20
    a.b("89ce")                                 # mov esi,ecx (player)
    a.b("89c3")                                 # mov ebx,eax (group)
    a.b("89d5")                                 # mov ebp,edx (row)
    a.b("31c9")
    a.label("cv_save")
    a.b("8a440e36"); a.b("88040c")              # save the live rating
    a.b("41"); a.b("83f91c"); a.j8("72", "cv_save")
    a.b("85ff"); a.j8("74", "cv_call")          # source 0 = live
    a.b("31c9")
    a.label("cv_copy")
    a.b("8a040f"); a.b("88440e36")              # stage the stored rating
    a.b("41"); a.b("83f91c"); a.j8("72", "cv_copy")
    a.label("cv_call")
    a.b("8bce"); a.b("8bc3")                    # ecx=player ; eax=group (ebx)
    a.b("8bd5")                                 # edx=row
    a.call(0x00365B00)                          # the retail per-attribute value helper
    a.b("89c3")                                 # ebx=result
    a.b("31c9")
    a.label("cv_restore")
    a.b("8a040c"); a.b("88440e36")              # restore the live rating
    a.b("41"); a.b("83f91c"); a.j8("72", "cv_restore")
    a.b("8bc3")                                 # mov eax,ebx
    a.b("83c420"); a.b("5d5f5e5b"); a.b("c3")

    # ---- snapshot capture ---------------------------------------------------------------------
    # mode 0: season/load baseline (clear and fill).  mode 1: a completed week's post-game ring
    # entry.  mode 3: ensure a same-year baseline exists without disturbing it.
    a.label("capture_baseline")
    a.b("b800000000"); a.j32("e9", "capture_common")
    a.label("capture_week")
    a.b("b801000000"); a.j32("e9", "capture_common")
    a.label("capture_ensure")
    a.b("b803000000")
    a.label("capture_common")
    a.b("60")                                   # pushad
    a.b("83ec40")                               # sub esp,0x40
    a.b("89442410")                             # [esp+0x10] = mode
    a.b("bd" + _imm(record_va))                 # mov ebp,record
    a.call(FN_LEAGUE)                           # franchise only (league type 2)
    a.b("83f802"); a.j32(JNE, "cap_done")
    a.b("a1" + _imm(ROSTER_VA)); a.b("85c0"); a.j32(JZ, "cap_done")
    a.b("8b401c"); a.b("85c0"); a.j32(JZ, "cap_done")
    # mode 3: a valid same-year baseline already exists -> done
    a.b("837c241003"); a.j32(JNE, "cap_mode1")
    a.b("813d" + _imm(record_va) + _imm(RECORD_MAGIC)); a.j32(JNE, "cap_mode1")
    a.b("807d0401"); a.j32(JNE, "cap_mode1")
    a.b("f6450501"); a.j32(JZ, "cap_mode1")
    a.b("0fb74506"); a.b("0fb715" + _imm(YEAR_VA)); a.b("39d0"); a.j32(JNE, "cap_mode1")
    a.j32("e9", "cap_done")
    a.label("cap_mode1")
    a.b("837c241001"); a.j32(JNE, "cap_baseline_team")   # modes 0/3 -> baseline
    # weekly: only an existing same-year baseline continues; never invent one here
    a.b("813d" + _imm(record_va) + _imm(RECORD_MAGIC)); a.j32(JNE, "cap_done")
    a.b("807d0401"); a.j32(JNE, "cap_done")
    a.b("0fb74506"); a.b("0fb715" + _imm(YEAR_VA)); a.b("39d0"); a.j32(JNE, "cap_done")
    a.b("f6450501"); a.j32(JZ, "cap_done")
    # team from the header index (the controller team can change during simulation)
    a.b("a1" + _imm(ROSTER_VA)); a.b("8b401c")
    a.b("0fb64d08"); a.b("69c9f4010000"); a.b("01c8")
    a.b("890424")                               # [esp]=team
    a.j32("e9", "cap_have_team")
    a.label("cap_baseline_team")
    a.call(FN_TEAM)
    a.b("85c0"); a.j32(JZ, "cap_done")
    a.b("890424")
    # roster readiness: a count and a first player
    a.b("0fb6881c010000")                       # movzx ecx,byte [eax+0x11c]
    a.b("85c9"); a.j32(JZ, "cap_done")
    a.b("833800")                               # cmp dword [eax],0
    a.j32(JZ, "cap_done")
    # clear the record body, then the footer and record headers
    a.b("89ef")                                 # mov edi,ebp
    a.b("31c0")                                 # xor eax,eax
    a.b("b9" + _imm(8568))                      # 34,272 bytes
    a.b("fc"); a.b("f3ab")                      # cld ; rep stosd
    a.b("b90f000000")                           # 15 bytes (record size is 34,287, not a dword multiple)
    a.b("f3aa")                                 # rep stosb
    a.b("bd" + _imm(record_va))                 # mov ebp,record
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
    a.b("8bce"); a.call(FN_OVERALL)
    a.b("8944241c")                             # [esp+0x1c]=overall
    a.b("8b74240c")                             # esi=player
    a.call(code_va + _HELPERS.get("identity", 0))
    a.b("89442420")                             # [esp+0x20]=identity
    a.b("bd" + _imm(record_va))
    a.call(code_va + _HELPERS.get("slot_for_identity", 0))
    a.b("85ff"); a.j32(JNZ, "cap_found")
    a.b("bd" + _imm(record_va))
    a.call(code_va + _HELPERS.get("free_slot", 0))
    a.b("85ff"); a.j32(JNZ, "cap_new_slot")
    # no free slot: reuse the slot at the current roster index
    a.b("89d8"); a.b("69c0" + _imm(SLOT_SIZE)); a.b("8d7c0520")
    a.label("cap_new_slot")
    # a new player (or a baseline capture): reset this slot to the live values
    a.b("8b74240c")                             # esi=player
    a.b("8b442420"); a.b("8907")                # identity
    a.b("8b44241c"); a.b("884705")              # overall
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
    a.label("cap_found")
    a.b("837c241001"); a.j32(JNE, "cap_new_slot")   # baseline/ensure resets even a known slot
    # weekly capture writes the post-game values to the ring at head
    a.b("bd" + _imm(record_va))
    a.b("0fb6450b")                             # head
    a.b("6bc01d")                               # *29
    a.b("8d540722")                             # lea edx,[edi+eax+0x22]
    a.b("31c9")
    a.label("cap_week_copy")
    a.b("8a440e36"); a.b("88440a00")            # al=player rating; [edx+ecx]=al
    a.b("41"); a.b("83f91c"); a.j32(JB, "cap_week_copy")
    a.b("8b44241c"); a.b("88421c")              # snapshot overall
    a.j32("e9", "cap_next")
    a.label("cap_next")
    a.b("43"); a.j32("e9", "cap_slot")
    a.label("cap_slots_done")
    a.b("837c241001"); a.j32(JNE, "cap_baseline_header")
    # advance the ring and header, labelled with the week just completed (post-game)
    a.b("bd" + _imm(record_va))
    a.b("0fb6450b"); a.b("40"); a.b("83f811"); a.j8("72", "cap_head_ok")
    a.b("31c0")
    a.label("cap_head_ok")
    a.b("88450b")
    a.b("0fb6450a"); a.b("40"); a.b("83f811"); a.j8("76", "cap_count_ok2")
    a.b("b811000000")
    a.label("cap_count_ok2")
    a.b("88450a")
    a.b("804d0502")                             # history flag
    a.b("a1" + _imm(WEEK_VA)); a.b("884509")    # last completed week = the simulated week
    a.j32("e9", "cap_team_index")
    a.label("cap_baseline_header")
    a.b("bd" + _imm(record_va))
    a.b("c6450501"); a.b("c6450900")
    a.b("c605" + _imm(data_va) + "00")          # a new baseline starts on the season view
    a.label("cap_team_index")
    a.b("8b0424")                               # team pointer
    a.b("8b0d" + _imm(ROSTER_VA)); a.b("8b491c")
    a.b("29c8"); a.b("31d2"); a.b("b9f4010000"); a.b("f7f1")
    a.b("884508")                               # team index
    a.label("cap_done")
    a.b("83c440"); a.b("61"); a.b("c3")

    # ---- game end: run the second club's stat merge, then snapshot the user's completed week ----
    a.label("game_end")
    a.b("9c")                                   # pushfd
    a.b("60")                                   # pushad
    a.b("ff74242c")                             # push arg1 (edx) for the displaced merge
    a.b("ff74242c")                             # push arg2 (1)
    a.call(0x00134DD0)                          # retail per-player stat merge (ret 8)
    a.b("8b5c2444")                             # mov ebx,[esp+0x44] (game struct)
    a.b("85db"); a.j32(JZ, "ge_retail")
    a.b("0fb64b01")                             # movzx ecx,byte [ebx+1] (club 1)
    a.b("0fb65302")                             # movzx edx,byte [ebx+2] (club 2)
    a.b("89ce")                                 # mov esi,ecx
    a.b("89d5")                                 # mov ebp,edx
    a.b("a1" + _imm(ROSTER_VA)); a.b("85c0"); a.j32(JZ, "ge_retail")
    a.b("8b781c"); a.b("85ff"); a.j32(JZ, "ge_retail")
    a.call(FN_TEAM)
    a.b("85c0"); a.j32(JZ, "ge_retail")
    a.b("29f8")                                 # sub eax,edi (team - array)
    a.b("31d2")                                 # xor edx,edx
    a.b("b9f4010000")                           # mov ecx,0x1f4
    a.b("f7f1")                                 # div ecx -> eax = team index
    a.b("39f0"); a.j8("74", "ge_stage")         # user is club 1
    a.b("39e8"); a.j8("75", "ge_retail")        # not club 2
    a.label("ge_stage")
    a.call(FN_STAGE)
    a.b("83f808"); a.j8("74", "ge_capture")
    a.b("83f809"); a.j8("75", "ge_retail")
    a.label("ge_capture")
    a.call(capture_week_va)
    a.label("ge_retail")
    a.b("61"); a.b("9d")                        # popad ; popfd
    a.b("c20800")                               # ret 8 (the original merge call's args)

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
    a.call(capture_baseline_va)                 # an old save starts a fresh history here
    a.label("load_done")
    a.b("61"); a.b("9d"); a.b("c3")

    a.label("admission")
    # b779 ag1: admitted franchise sizes, each also with the MyCareer footer, the Player Progress footer or both:
    # retail (720,044), this build's own native size (720,044 + [0xB72808] - 0x91000: 724,140 on the 0x92000 arena,
    # the capacity size on the capacity arena), and on a capacity build larger than beta-78's, beta-78's 847,020
    # save (nfl2k5_roster_arena.LEGACY_CAPACITY_SAVE_SIZE), which loads and migrates.
    a.b("8b8eccc1bd00")                         # mov ecx,[esi+0xbdc1cc] (file size)
    a.b("b8" + _imm(record.RETAIL_SAVE_SIZE)); a.j32("e8", "adm_family"); a.j8("74", "adm_ok")
    a.b("a1" + _imm(0x00B72808))                # mov eax,[0xb72808] (arena size)
    a.b("05" + _imm(record.RETAIL_SAVE_SIZE - 0x91000)); a.j32("e8", "adm_family"); a.j8("74", "adm_ok")
    a.b("3d" + _imm(record.LEGACY_CAPACITY_SAVE_SIZE)); a.j8("76", "adm_bad")
    a.b("b8" + _imm(record.LEGACY_CAPACITY_SAVE_SIZE)); a.j32("e8", "adm_family"); a.j8("74", "adm_ok")
    a.label("adm_bad")
    a.b("b801000000"); a.b("5e"); a.b("c3")     # mov eax,1 ; pop esi ; ret (damaged)
    a.label("adm_ok")
    a.b("31c0"); a.b("5e"); a.b("c3")
    a.label("adm_family")                       # ZF: ecx is eax plus 0, the career, the progress or both footers
    a.b("39c1"); a.j8("74", "adm_family_done")
    a.b("8d90" + _imm(record.MYCAREER_FOOTER_SIZE)); a.b("39d1"); a.j8("74", "adm_family_done")
    a.b("8d90" + _imm(FOOTER_SIZE)); a.b("39d1"); a.j8("74", "adm_family_done")
    a.b("8d90" + _imm(record.MYCAREER_FOOTER_SIZE + FOOTER_SIZE)); a.b("39d1")
    a.label("adm_family_done")
    a.b("c3")
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


_HELPERS: dict[str, int] = {}
_TEMPLATE, _LABELS = _assemble(0, 0, 0, 0, 0, 0, 0, 0, 0)
_HELPERS.update({name: _LABELS[name] for name in ("identity", "slot_for_identity", "free_slot", "calc_value", "capture_ensure")})
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
        ("game_end", SITE_GAME_END[0], SITE_GAME_END[1],
         b"\xe8" + _rel32(code_va + lab["game_end"], SITE_GAME_END[0])),
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

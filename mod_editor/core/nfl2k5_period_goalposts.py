"""Period goalposts: Anniversary moments played before the 2014 season keep the 30 ft uprights (b77 v1b).

``nfl2k5_modern_goalposts`` (v1) raised the two shared goalpost scenes to the modern 35 ft above the crossbar. The NFL made
that rule in March 2014, effective for the 2014 season; Noah (10/8) wants the 38 Anniversary moments of earlier seasons to
keep the old 30 ft. The venue has ONE goalpost model for every game and there is no room for a second pair of scenes (the
gamedata.iff entry has 1,888 spare bytes, a second pair needs 4,800 and the retail executable has no cave the cave oracle
calls free), so the height is chosen when a stadium loads:

* a hook on the call at VA 0x99B16 (in the stadium loader, just before it sets up both goals) runs the original call, decides
  ``period`` (game mode 8 and a physical Anniversary row 0..50 whose season is before 2014, the same test the Anniversary
  venue bundles use) and rewrites the Y word of the 56 + 32 upright-top vertices of ``goalpost`` and ``goalpost_shadow``
  in memory (the 3D data is NORMSHORT3 with one scale: tops 30 ft are word 25435, tops 35 ft are word 32702; the draw lists
  only index the vertices, so the GPU reads the new words when it draws). It runs on every stadium load, so a normal
  game after a moment gets the 35 ft posts again;
* the two thin upright lines (``0x985B0``) and the ball/upright collision (``0x1C68C0``) read their top height through
  small stubs that run the same period test (no stored state), instead of their constants.

The code needs 176 bytes of new executable space and 32 of read-only tables, so it is an allocator owner
(``nfl2k5_period_goalposts``), placed after every other owner like K128. It fits the allocator's worst case (every owner
installed at once leaves 192 code bytes and no data page, so the owner asks for neither more code nor any writable data).
The data file is ``data/nfl2k5_moment_goalposts.json``.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from . import nfl2k5_xbe_space as space
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_period_goalposts"
BUILD_CAPTION = UI_LABEL = "Period goalposts (30 ft uprights for Anniversary moments before 2014)"
CODE_SIZE, RO_SIZE = 176, 32
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "read_only", RO_SIZE, 4))
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_moment_goalposts.json"
SCHEMA = "nfl2k5_moment_goalposts/v1"
RULE_SEASON = 2014                 # uprights 35 ft above the crossbar from this NFL season on
PERIOD_FT, MODERN_FT = 30, 35      # above the 10 ft crossbar
ROWS = 51

# game facts (retail default.xbe, all unchanged by this owner)
LOAD_CALL_VA, LOAD_CALLEE_VA = 0x00099B16, 0x00097B50       # `call 0x97B50` in the stadium loader, then goal setup
FIND_VA = 0x000449E0                                         # (ecx=0, edx='SCNE', [name]) -> scene or 0, callee pops
MODE_VA, ROW_VA = 0x00E5FF80, 0x00BF1858                     # game mode (8 = Anniversary), physical moment row
NAME_POST_VA, NAME_SHADOW_VA = 0x00E661CC, 0x00E662A8        # L"goalpost", L"goalpost_shadow"
LINE_LEFT_VA, LINE_RIGHT_VA = 0x000986AA, 0x000986FB         # push <top of the upright line>
COLLISION_VA = 0x001C6A2C                                    # fadd dword ptr [top]
TOP_MODERN, TOP_PERIOD = 1371.6, 1219.2                      # cm above the field
# NORMSHORT3 Y words of the upright tops in the two modern scenes (scale 687.1716, offset 685.8 -> 1371.608 / 1219.209 cm)
WORD_MODERN, WORD_PERIOD = 32702, 25435
SCENES = (("goalpost", NAME_POST_VA, 243), ("goalpost_shadow", NAME_SHADOW_VA, 174))

# the v1 (modern goalposts) bytes at the three executable sites, which this owner supersedes
V1_LINE = b"\x68" + struct.pack("<f", TOP_MODERN)
V1_COLLISION = b"\xd8\x05" + struct.pack("<I", 0x004F689C)
RETAIL_LINE = b"\x68" + struct.pack("<f", TOP_PERIOD)
RETAIL_COLLISION = b"\xd8\x05" + struct.pack("<I", 0x0050A510)
RETAIL_LOAD = b"\xe8" + struct.pack("<i", LOAD_CALLEE_VA - (LOAD_CALL_VA + 5))


class PeriodGoalpostsError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise PeriodGoalpostsError(message)


# --- the data file ---------------------------------------------------------------------------------------------

def build_rows() -> list[dict[str, Any]]:
    """The 51 moments with their season and upright height, from the Anniversary catalogs (season = the NFL season
    in which the game was played, e.g. the January 1999 playoff game is season 1998)."""

    era = {r["row"]: r for r in json.loads((ROOT / "data/nfl2k5_era_rules.json").read_text())["mappings"]}
    fields = {r["row"]: r for r in json.loads((ROOT / "data/nfl2k5_espn25_fields.json").read_text())["moments"]}
    require(sorted(era) == sorted(fields) == list(range(1, ROWS + 1)), "the Anniversary catalogs do not list 51 rows")
    rows = []
    for k in range(1, ROWS + 1):
        require(era[k]["season"] == fields[k]["season"], f"row {k}: the two catalogs disagree on the season")
        season = fields[k]["season"]
        feet = PERIOD_FT if season < RULE_SEASON else MODERN_FT
        rows.append(dict(row=k, date=fields[k]["date"], title=fields[k]["title"], season=season,
                         uprights_above_crossbar_ft=feet, upright_top_above_field_ft=feet + 10))
    return rows


def document() -> dict[str, Any]:
    return dict(
        schema=SCHEMA, classification="SOURCED",
        rule=dict(
            period_ft_above_crossbar=PERIOD_FT, modern_ft_above_crossbar=MODERN_FT, crossbar_ft_above_field=10,
            modern_from_season=RULE_SEASON,
            basis=("The NFL owners voted in March 2014 to extend the uprights from 30 to 35 feet above the crossbar, "
                   "effective for the 2014 season. Noah (2026-10-08) chose to keep 30 ft for every earlier moment; "
                   "how tall the uprights were in the decades before is not researched and is not modelled."),
            sources=["https://www.footballzebras.com/2014/03/goalposts-will-grow-5-feet-taller/",
                     "https://www.neworleanssaints.com/news/john-deshazier-nfl-votes-to-extend-length-of-uprights-12812659",
                     "https://www.si.com/nfl/2014/04/04/nfl-taller-field-goal-posts-makers"]),
        moments=build_rows())


def moments() -> list[dict[str, Any]]:
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    require(doc.get("schema") == SCHEMA, "foreign moment goalpost table")
    rows = doc["moments"]
    require([r["row"] for r in rows] == list(range(1, ROWS + 1)), "moment goalpost table must list rows 1..51")
    require(all(r["uprights_above_crossbar_ft"] == (PERIOD_FT if r["season"] < RULE_SEASON else MODERN_FT) for r in rows),
            "the upright heights do not follow the season rule")
    return rows


def period_flags() -> bytes:
    """One byte per physical moment row: 1 = the 30 ft uprights."""

    return bytes(1 if r["uprights_above_crossbar_ft"] == PERIOD_FT else 0 for r in moments())


# --- the code --------------------------------------------------------------------------------------------------

def _h(value: int) -> str:
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


def tables() -> bytes:
    """The owner's read-only bytes (32): the 51-bit period mask, the two top heights, the two scene descriptors."""

    mask = sum(1 << i for i, f in enumerate(period_flags()) if f)
    return (struct.pack("<Q", mask) + struct.pack("<2f", TOP_MODERN, TOP_PERIOD)
            + struct.pack("<IH", NAME_POST_VA, SCENES[0][2]) + struct.pack("<IH", NAME_SHADOW_VA, SCENES[1][2])
            ).ljust(RO_SIZE, b"\0")


TABLE_MASK, TABLE_TOPS, TABLE_POST, TABLE_SHADOW = 0, 8, 16, 22      # offsets in tables()


def code_for(code_va: int, ro_va: int) -> bytes:
    """The owner's 176 code bytes: the stadium-load stub (period test, scene patcher), the period test, and the three
    site stubs. The only game state it reads is the game mode, the moment row and the scenes; it keeps no state of its own."""

    a = _Asm(code_va)
    a.label("stub")
    a.call(LOAD_CALLEE_VA)                                   # the displaced call
    a.b("60")                                                # pushad
    a.j32("e8", "calc")                                      # eax = 1 for a period moment
    a.b("89c3" "be" + _h(ro_va + TABLE_POST))                # mov ebx,eax ; mov esi,desc_post
    a.label("next")                                          # esi = descriptor {name va, vertex count}, ebx = period
    a.b("ff36" "ba" + _h(0x454E4353) + "31c9")               # push [esi] ; mov edx,'SCNE' ; xor ecx,ecx
    a.call(FIND_VA)                                          # eax = scene or 0
    a.b("85c0")
    a.j8("74", "skip")
    a.b("8b4830" "0fb77e04" "6639794c")                      # mov ecx,[eax+0x30] ; movzx edi,[esi+4] ; cmp [ecx+0x4c],di
    a.j8("75", "skip")
    a.b("8b89d4000000")                                      # mov ecx,[ecx+0xd4]   (the position stream)
    a.b("b8" + _h(WORD_PERIOD) + "ba" + _h(WORD_MODERN) + "85db")   # eax=q30, edx=q35, test ebx,ebx
    a.j8("74", "go")
    a.b("92")                                                # xchg eax,edx         (period: from q35 to q30)
    a.label("go")
    a.b("83c102")                                            # add ecx,2            (the first vertex's Y word)
    a.label("loop")
    a.b("663901")                                            # cmp [ecx],ax
    a.j8("75", "same")
    a.b("668911")                                            # mov [ecx],dx
    a.label("same")
    a.b("83c106" "4f")                                       # add ecx,6 ; dec edi
    a.j8("75", "loop")
    a.label("skip")
    a.b("83c606" "81fe" + _h(ro_va + TABLE_SHADOW + 6))      # add esi,6 ; cmp esi,end
    a.j8("72", "next")
    a.b("61c3")                                              # popad ; ret
    a.label("calc")                                          # eax = 1 when mode 8 and the moment row is before 2014
    a.b("31c0" "833d" + _h(MODE_VA) + "08")                  # xor eax,eax ; cmp [mode],8
    a.j8("75", "ret")
    a.b("a1" + _h(ROW_VA) + "83f833")                        # mov eax,[row] ; cmp eax,51
    a.j8("73", "zero")
    a.b("0f a3 05".replace(" ", "") + _h(ro_va + TABLE_MASK) + "19c0" "f7d8")   # bt [mask],eax ; sbb eax,eax ; neg eax
    a.label("ret")
    a.b("c3")
    a.label("zero")
    a.b("31c0c3")
    a.label("line")                                          # call-site stub of `push <top>`: leaves the top, returns
    a.b("50")                                                # push eax
    a.j32("e8", "calc")
    a.b("8b0485" + _h(ro_va + TABLE_TOPS))                   # mov eax,[eax*4+tops]
    a.b("87442404" "870424" "c3")                            # xchg eax,[esp+4] ; xchg eax,[esp] ; ret   (eax restored)
    a.label("coll")                                          # replaces `fadd dword ptr [top]`
    a.b("9c50")                                              # pushfd ; push eax
    a.j32("e8", "calc")
    a.b("d80485" + _h(ro_va + TABLE_TOPS) + "589dc3")        # fadd dword [eax*4+tops] ; pop eax ; popfd ; ret
    # `next` is a short loop back-branch; the assembler needs a near form for the far label, so it is spelled out
    body = bytearray(a.assemble())
    labels = dict(a.labels)
    require(len(body) <= CODE_SIZE, f"period goalposts code budget: {len(body)} > {CODE_SIZE}")
    body += b"\xcc" * (CODE_SIZE - len(body))
    code_for.labels = labels
    return bytes(body)


def labels(code_va: int, ro_va: int) -> dict[str, int]:
    code_for(code_va, ro_va)
    return {k: code_va + v for k, v in code_for.labels.items()}


def sites(code_va: int, ro_va: int) -> list[tuple[str, int, tuple[bytes, ...], bytes]]:
    """(label, VA, accepted input bytes, output bytes) of the four executable sites; the inputs are the retail or v1 bytes."""

    lab = labels(code_va, ro_va)
    call = lambda va, target: b"\xe8" + struct.pack("<i", target - (va + 5))
    return [
        ("stadium_load_hook", LOAD_CALL_VA, (RETAIL_LOAD,), call(LOAD_CALL_VA, lab["stub"])),
        ("upright_line_left_top", LINE_LEFT_VA, (RETAIL_LINE, V1_LINE), call(LINE_LEFT_VA, lab["line"])),
        ("upright_line_right_top", LINE_RIGHT_VA, (RETAIL_LINE, V1_LINE), call(LINE_RIGHT_VA, lab["line"])),
        ("upright_collision_top", COLLISION_VA, (RETAIL_COLLISION, V1_COLLISION),
         call(COLLISION_VA, lab["coll"]) + b"\x90"),
    ]


# --- the executable --------------------------------------------------------------------------------------------

def _offset(payload: bytes, va: int, size: int) -> int:
    from .nfl2k5_cave_oracle import XbeImage
    return XbeImage(payload).offset(va, size)


def allocations(payload: bytes) -> dict[str, dict[str, Any]] | None:
    """{'code': allocation, 'read_only': allocation} when the executable's directory carries this owner, else None."""

    found = {r["kind"]: r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER}
    if not found:
        return None
    require(set(found) == {"code", "read_only"} and found["code"]["size"] == CODE_SIZE and found["read_only"]["size"] == RO_SIZE,
            "the period goalposts allocation is not the supported size")
    return found


def _planned(payload: bytes):
    """The allocation the owner has, or would get if its two requests were appended to an installed directory."""

    have = allocations(payload)
    if have:
        return have["code"], have["read_only"], False
    requests = list(space._read_scale_directory(payload))
    allocs = space._scale_allocations(requests + list(REQUESTS))
    mine = {a["kind"]: a for a in allocs if a["owner"] == OWNER}
    return mine["code"], mine["read_only"], True


def status(payload: bytes) -> str:
    """retail | modern (v1 bytes) | applied | foreign, over the four executable sites and the owner's code."""

    try:
        have = allocations(payload)
        code = have["code"] if have else None
        ro = have["read_only"] if have else None
        installed = bool(have) and payload[code["raw"]:code["raw"] + CODE_SIZE] == code_for(code["va"], ro["va"]) \
            and payload[ro["raw"]:ro["raw"] + RO_SIZE] == tables()
        if have and installed:
            for _label, va, _accepted, after in sites(code["va"], ro["va"]):
                at = _offset(payload, va, len(after))
                if payload[at:at + len(after)] != after:
                    return "foreign"
            return "applied"
        if have and payload[code["raw"]:code["raw"] + CODE_SIZE] != b"\xcc" * CODE_SIZE:
            return "foreign"                                # the allocation holds something else
        states = set()
        for _label, va, accepted, _after in sites(0x14F0000, 0x14F8000):
            at = _offset(payload, va, len(accepted[0]))
            site = payload[at:at + len(accepted[0])]
            states.add("retail" if site in (RETAIL_LOAD, RETAIL_LINE, RETAIL_COLLISION)
                       else "modern" if site in (V1_LINE, V1_COLLISION) else "foreign")
        return "foreign" if "foreign" in states else "retail" if states == {"retail"} else "modern"
    except (PeriodGoalpostsError, ValueError, KeyError, struct.error):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict[str, Any]]:
    """Install the owner in an executable that already carries the sealed scale-out allocator (the Studio's build step
    after ``xbe_space``, or a v0.5 disc's executable: the directory is extended with this one late owner, which moves no
    other owner). Idempotent; refuses foreign bytes."""

    from .nfl2k5_bump_strength import _sections, section_digest
    require(space.is_scaleout(payload) and space.status(payload) == "applied", "needs the sealed scale-out allocator")
    code, ro, extended = _planned(payload)
    if not extended and status(payload) == "applied":
        return payload, dict(status="already_applied", changed_bytes=0, edits=[])
    buf = bytearray(payload)
    requests = list(space._read_scale_directory(payload))
    if extended:
        requests = requests + list(REQUESTS)
    require(bytes(buf[code["raw"]:code["raw"] + CODE_SIZE]) == b"\xcc" * CODE_SIZE
            or bytes(buf[code["raw"]:code["raw"] + CODE_SIZE]) == code_for(code["va"], ro["va"]),
            "the owner's code allocation holds foreign bytes")
    require(bytes(buf[ro["raw"]:ro["raw"] + RO_SIZE]) in (bytes(RO_SIZE), tables()), "the owner's read-only allocation holds foreign bytes")
    buf[code["raw"]:code["raw"] + CODE_SIZE] = code_for(code["va"], ro["va"])
    buf[ro["raw"]:ro["raw"] + RO_SIZE] = tables()
    edits, touched, sections = [], set(), _sections(payload)
    for label, va, accepted, after in sites(code["va"], ro["va"]):
        at = _offset(payload, va, len(after))
        before = bytes(payload[at:at + len(accepted[0])])
        require(before in accepted or before == after, f"{label}: foreign bytes at {hex(va)}")
        buf[at:at + len(after)] = after
        touched.add(next(s.index for s in sections if s.raw_offset <= at < s.raw_offset + s.raw_size))
        edits.append(dict(label=label, va=hex(va), file_offset=hex(at), before=before.hex(), after=after.hex()))
    edits.append(dict(label="owner_code", va=hex(code["va"]), file_offset=hex(code["raw"]), size=CODE_SIZE))
    space._seal_scaleout(buf, requests)
    for section in sections:
        if section.index in touched:
            buf[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(buf), section)
    result = bytes(buf)
    require(space.status(result) == "applied" and status(result) == "applied", "period goalposts postcondition failed")
    return result, dict(status="applied", edits=edits, directory_extended=extended,
                        changed_bytes=sum(x != y for x, y in zip(payload, result)),
                        code_va=hex(code["va"]), read_only_va=hex(ro["va"]))


class XbePatch:
    OWNER = OWNER
    REQUESTS = REQUESTS
    apply = staticmethod(apply)
    status = staticmethod(status)

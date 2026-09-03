"""Make CPU franchise drafts and free agency pick like the NFL (executable patch, xemu-only, local research).

Two retail routines are replaced.

1. The draft pick.  When a CPU team is on the clock, ``FUN_00325b90`` ("Round %u: %s chose %s") asks
   ``FUN_0031e0f0`` (0x31E0F0; fastcall ecx=team, edx=1 for CPU) for the player.  Retail orders the 17
   positions by need (``FUN_0031dea0``: roster count against the target plus a per-round table, weighted
   by how weak the position is), then in round 1 takes the best raw overall among the three neediest
   positions and in later rounds the best raw overall at need rank 0/1/2/3/4 with 40/30/15/10/5 % odds.
   Raw overall is compared across positions, and the rookie generator rolls every position between its
   own low/high templates, so the positions whose rookies roll the highest overalls (HB, DE, T, QB) flood
   round 1, and the 11th-best HB goes as soon as HB is a top-three need.  The routine is rewritten in
   place (head at 0x31E0F0, tail in the dead bytes below):

       need[17]  = FUN_0031dea0(team, round, pick)             (retail need order kept)
       mean[pos] = class average overall at pos (prospects = pool players with flag 0x10)
       score(p)  = ((overall(p) - mean[pos]) + (17 - needrank(pos)) * NEED_STEP) * VALUE[pos]
                   + (rand & 255)/256 * PICK_JITTER             (CPU only; human auto-pick is deterministic)
       pick      = the available prospect with the highest score

   Subtracting each position's own class average cancels the generator's per-position scale, VALUE is a
   real-NFL first-round positional value (QB, T, DE, WR, CB high; RB, S, LB lower; K/P 0.3), need tilts
   the order the way front offices do, and the jitter keeps two teams from reading the board identically.

2. Free-agent wishes (the earlier "draft AI" cave, which in fact targets free agency).  The offseason
   day tick ``FUN_00324600`` runs the 100-slot bidding pool at 0xE3C600 during the retirement,
   re-signing and free-agency days: ``FUN_003242c0`` (0x3242C0..0x324562) lets each CPU team hold up to
   four "wishes" for the best unsigned player at a position, filled in retail by two passes in
   position-enum order (QB, K, P, WR, CB, ...).  The passes are replaced by a scored selection hosted in
   the XBE boot-logo bitmap (0x10B40..0x10C87; constants 0x10AF0..0x10B3F):

       score[p] = (best_overall[p]*100 - team_average[p]) * VALUE[p] + deficit[p] * DEFICIT_BONUS
                + (rand & 255) * JITTER/256 ; take the best four above 0 through the game's FUN_00324180.

   The projected-"round" routine ``FUN_00322690`` is the free-agent contract tier by years pro and is
   left retail (an earlier revision hooked it; that cave ranked players against the whole player pool).

3. The Rookie Report / prospect ranking key (Noah, 9/3 night: "It often has fullbacks as the top
   prospect ... fullbacks, kickers, and punters should never, ever, ever be a top 25 prospect").
   The ESPN.com Rookie Report page (``FUN_0035fce0`` -> ``FUN_0035fca0`` -> ``FUN_0035f140``) sorts
   every prospect by ``FUN_0031d8f0`` = the scouted overall at his own position: a per-position table
   at ``.data 0xAE2A20`` (17 pointers to ``{base, scale, count, entries}``, a copy of the displayed-
   overall tables at 0xAC4948 used only by this key and by Mel's projected-pick text ``FUN_0031d900``)
   gives ``key = clamp(0.3 + 0.7 * (weighted attribute average - base) / scale, 0, 1)``.  Every
   position's best rookie therefore approaches 1.0 and a good FB or K class tops the list.  Data fix,
   consistent with the draft pick's ``VALUE`` (FB 0.60, K/P 0.30): the ``scale`` of the FB, K and P
   tables is divided by that value, which shrinks their keys toward 0.3 by exactly that factor
   (``0.3 + 0.7 * value * ...``); every other position keeps its retail table.  Emulated on two real
   380-player classes from the game's own generator: retail put a K at #5 and a FB at #24 (seed
   12345) and a FB at #5, K #11, P #12 and #25 (seed 777); patched, the best FB ranks 199-221 and the
   best K/P 315-329 while the 25th key stays 0.72-0.73.

Pattern-checked, ``.text`` and ``.data`` digests recomputed.  Unverified at runtime.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

IMAGE_BASE = 0x10000
BODY_VA = 0x00324414          # first byte of the replaced passes
BODY_END_VA = 0x00324545      # `mov esi,[esp+0x18]`: the outer team loop continues here
BODY_SIZE = BODY_END_VA - BODY_VA   # 305
VALUE_VA = 0x00010AF0         # 17 floats
DEFICIT_VA = 0x00010B34
JITTER_VA = 0x00010B38
THRESH_VA = 0x00010B3C
CAVE_VA = 0x00010B40          # the scored selection itself (~330 bytes, ends before 0x10CC2)
LOGO_END_VA = 0x00010CC2
CONST_100 = 0x004E5CAC        # the game's own 100.0 used by the retail comparison
FN_COUNT_AT_POS = 0x000C3CB0  # fastcall(ecx=team, edx=pos) -> count
FN_TARGET = 0x002BD410        # fastcall(ecx=pos) -> minimum roster count
FN_MAX = 0x002BD400           # fastcall(ecx=pos) -> maximum roster count
FN_RATING = 0x00246D80        # fastcall(ecx=player, edx=1) -> st0 overall 0..1
FN_WISH = 0x00324180          # eax=player, [esp]=team (callee cleans) -> 1 if a wish was created
FN_RAND = 0x00048BC0          # () -> eax

POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
# Positional value, NFL 2015-2024 first-round shares folded into a multiplier around 1.0.  It scales
# a prospect's edge over his own position's class average, so a running back has to be clearly
# elite to out-rank a tackle or an edge with the same edge over their peers.
VALUE = {"QB": 1.15, "K": 0.30, "P": 0.30, "WR": 1.08, "CB": 1.08, "FS": 0.95, "SS": 0.95, "RB": 0.92,
         "FB": 0.60, "TE": 0.95, "OLB": 1.00, "ILB": 0.93, "C": 0.88, "G": 0.92, "T": 1.12, "DT": 1.00, "DE": 1.12}
DEFICIT_BONUS = 12.0
JITTER_POINTS = 20.0
THRESHOLD = 0.0

# --- the real CPU draft pick: retail FUN_0031e0f0 (0x31E0F0, 275 bytes; fastcall ecx=team on the
# clock, edx=1 for a CPU team; eax=player) is called by the on-the-clock routine FUN_00325b90 ("Round %u:
# %s chose %s").  Retail: FUN_0031dea0 orders the 17 positions by need, then round 1 takes the best
# overall among the three neediest positions and later rounds the best overall at need-rank
# 0/1/2/3/4 with 40/30/15/10/5 % odds.  No positional value, raw overall across positions (so the
# positions whose rookies roll the highest overalls flood round 1, and "the 11th-best HB" is simply
# the best HB left when HB is a top-three need).  Replaced in place by a value pick.
PICK_FN_VA = 0x0031E0F0
PICK_FN_SIZE = 275
FN_NEED = 0x0031DEA0          # fastcall(ecx=team, edx=round, [esp]=pick, [esp+4]=int need[17]) ; ret 8
DRAFT_ROUND_VA = 0x00E3C0A8   # current round, 0-based
DRAFT_PICK_VA = 0x00E3C0A4    # current pick within the round
POOL_PTR = 0x00B72918         # -> {int count; player *base; ...}: the whole player pool, stride 0x54
POOL_STRIDE = 0x54
FLAG_PROSPECT = 0x10          # player+8: unsigned draft prospect
FLAG_DRAFTED = 0x20           # player+8: already taken in this draft
NEED_STEP = 0.010             # per need rank, on the 0..1 overall scale: the neediest position is worth +0.17 before VALUE
PICK_JITTER = 0.06            # random 0..0.06 added to every CPU evaluation (about 6 rating points)
PICK_CONST_OFF = 264            # the two floats sit in the last 8 bytes of the 275-byte function (aligned)
PICK_TAIL_VA = BODY_VA + 5      # the scan half of the pick routine, after the jump into the wish cave
RETAIL_PICK_FN = bytes.fromhex(
    "83ec4c535556578bfa8b15a4c0e3008d44241850528b15a8c0e300894c241ce88cfdffff33f633db85ff743ce89faad2ff33d2b9"
    "65000000f7f183fa057d07bb04000000eb2283fa0f7d07bb03000000eb1683fa1e7d07bb02000000eb0a83fa3c7d05bb01000000"
    "8b6c241c8d64240083fb100f8f88000000a1a8c0e30085c075608b54241852e8d4faffff558bf0e8ccfaffff8bf88bcfe8e384dc"
    "ffd95c24108bcee8d884dcffd85c2410dfe0f6c4057a028bf78b44242050e8a1faffff8bf88bcfe8b884dcffd95c24108bcee8ad"
    "84dcffd85c2410dfe0f6c4057a118bf7eb0d8b4c9c1851e874faffff8bf04385f60f8479ffffff5f8bc65e5d5b83c44cc385f675"
    "f28b5424148b025f5e5d5b83c44cc3"
)

# --- Rookie Report ranking key: the per-position scouting tables at .data 0xAE2A20 (17 pointers to
# {float base, float scale, u32 count, entries*}); the FB / K / P ``scale`` words are divided by the
# draft VALUE so their keys shrink by that factor.  Struct addresses read from the retail pointer table.
ROOKIE_KEY_TABLES_VA = 0x00AE2A20
ROOKIE_KEY_SCALE_OFF = 4
ROOKIE_KEY_SCALE = {"FB": VALUE["FB"], "K": VALUE["K"], "P": VALUE["P"]}
ROOKIE_KEY_SITES = (
    # (position, struct VA, retail scale bits)
    ("K", 0x00AE1D80, 0x3F333333),      # 0.70
    ("P", 0x00AE1D90, 0x3F2B851F),      # 0.67
    ("FB", 0x00AE1DD0, 0x3F333333),     # 0.70
)

RETAIL_BODY = bytes.fromhex(
    "33ff83fb047d3beb038d490083ff117d2d8bd78bcee882f8d9ff8bcf8be8e8d98ff9ff2bc585c07e0f8b44bc2056e839fdffff85c0"
    "7401434783fb047cce895c241033ff83fb040f8de400000083ff110f8ddb0000008b44bc2033ed3bc50f84c30000008bd78bcee82f"
    "f8d9ff8bcf8bd8e8768ff9ff2bc385c00f8ea30000008a861c01000084c0896c2414762f8b0cae0fb641353bc77518ba01000000e8"
    "c928f2ffd80dac5c4e00d8442414d95c24140fb68e1c010000453be97cd18bd78bcee8d6f7d9ff85c074218bd78bcee8c9f7d9ff89"
    "44241cdb44241cd95c241cd944241cd87c2414d95c24148b5cbc20ba010000008bcbe87128f2ffd80dac5c4e00d85c2414dfe0f6c4"
    "417517568bc3e858fcffff85c0740b8b5c241043895c2410eb048b5c24104783fb040f8c1cffffff"
)
# retail boot-logo bytes from file 0xAF0 (VA 0x10AF0) to the end of the bitmap (0xCC2): 466 bytes
RETAIL_LOGO_AF0 = bytes.fromhex(
    "e3ff43d3f79323f9a30323f7b33332f0130353f7e343f7e305a3f7a303e3f7d305d3f7c303d3f75303f913071333030313f9d3f7a3f7d3f913f943d3f9030303f993f9e3"
    "2323f9730503f963f9d34313030773f92305a3f903f92303f9030f53f973fde3b3f913f923f9730fd3f7e3030393f9030533f913e3ffd30303e3f7d307a3f913f90343f7d32200a"
    "3f923fd43e3f7d343f943f9030d03f95305f9e30743f90303b3ffe303f9a307d3f953f7e30393f7932200fb03fbe303f973a3f7d343f90305030723f90305f9a307d3f39323090"
    "333d3fb23f9430513f973b3f79303e3f7330f03f9d303fb4323f933e3f79343f90513f963f907f9b3054322f0430573f923f97305a3f913f94303f9030f33f97303f9e30353f91"
    "3f94313f97343e3f773b3f7b30793f96323e3f7d3f9a30303a3f903d3f7e32373f96303f90313f9b3a30d73f92303f94303b3f923f90303d322f0b303f973071326f0e303d32af"
    "073032326f0a30343f90343fb930dd3f90303f7e305f9a353f90503e3fdb30303f9330923ff73030303e322f0630763fde34305a3f7b305d3f9330d4b0547130303491373a7930"
    "70343a3c3a37313051349030b0353d3f3e3731309034373a3d3f3e373130b03235347030749130749030d"
)


class DraftAiError(ValueError):
    """The draft-AI patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DraftAiError(message)


def const_bytes() -> bytes:
    return struct.pack("<17f", *(VALUE[p] for p in POSITIONS)) + struct.pack("<3f", DEFICIT_BONUS, JITTER_POINTS / 256.0, THRESHOLD)


# ---------------------------------------------------------------- mini assembler
class _Asm:
    def __init__(self, base: int) -> None:
        self.base = base
        self.items: list = []      # bytes | ("j8", opcode, label) | ("j32", opcode, label) | ("call", va)
        self.labels: dict[str, int] = {}

    def b(self, hexs: str) -> None:
        self.items.append(bytes.fromhex(hexs))

    def label(self, name: str) -> None:
        self.items.append(("label", name))

    def j8(self, opcode: str, label: str) -> None:
        self.items.append(("j8", bytes.fromhex(opcode), label))

    def j32(self, opcode: str, label: str) -> None:
        self.items.append(("j32", bytes.fromhex(opcode), label))

    def call(self, va: int) -> None:
        self.items.append(("call", va))

    def jmp_abs(self, va: int) -> None:
        self.items.append(("jmpabs", va))

    def _size(self, item) -> int:
        if isinstance(item, bytes):
            return len(item)
        kind = item[0]
        if kind == "label":
            return 0
        if kind == "j8":
            return 2
        if kind == "j32":
            return len(item[1]) + 4
        return 5  # call / jmpabs

    def assemble(self) -> bytes:
        pos = 0
        for item in self.items:
            if isinstance(item, tuple) and item[0] == "label":
                self.labels[item[1]] = pos
            pos += self._size(item)
        out = bytearray()
        for item in self.items:
            here = len(out)
            if isinstance(item, bytes):
                out += item
            elif item[0] == "label":
                continue
            elif item[0] == "j8":
                rel = self.labels[item[2]] - (here + 2)
                _require(-128 <= rel <= 127, f"rel8 out of range for {item[2]}")
                out += item[1] + struct.pack("<b", rel)
            elif item[0] == "j32":
                rel = self.labels[item[2]] - (here + len(item[1]) + 4)
                out += item[1] + struct.pack("<i", rel)
            elif item[0] == "call":
                out += b"\xe8" + struct.pack("<i", item[1] - (self.base + here + 5))
            elif item[0] == "jmpabs":
                out += b"\xe9" + struct.pack("<i", item[1] - (self.base + here + 5))
        return bytes(out)


def body_patch() -> bytes:
    """What replaces 0x324414..0x324544: a jump into the wish cave, then the tail of the draft-pick
    routine in the now-dead bytes of the old passes (never reached by the jump), int3 padded.  The
    projected "round" routine FUN_00322690 is left retail: it is the free-agent contract tier by
    experience, not a draft projection."""

    jump = b"\xe9" + struct.pack("<i", CAVE_VA - (BODY_VA + 5))
    _head, tail = pick_fn_bytes()
    return jump + tail + b"\xcc" * (BODY_SIZE - len(jump) - len(tail))


def pick_fn_bytes() -> tuple[bytes, bytes]:
    """Replacement for FUN_0031e0f0: ecx = team, edx = CPU flag -> eax = player.  Returns the head
    (275 bytes, assembled in place of the retail routine, its two tunable floats in the last 8 bytes)
    and the tail (hosted in the dead bytes of the old free-agency passes at PICK_TAIL_VA).

        need[17] = FUN_0031dea0(team, round, pick)            (retail need order, rank 0 = neediest)
        mean[pos] = average overall of the undrafted-or-drafted prospects at pos (the class)
        score(p)  = ((overall(p) - mean[pos]) + (17 - needrank(pos)) * NEED_STEP) * VALUE[pos]
                  + (rand() & 255) / 256 * PICK_JITTER          (CPU only)
        pick      = the available prospect (flag 0x10 set, 0x20 clear) with the highest score,
                    else the retail fallback (first roster player).
    Frame: sum[17] at [esp], count[17] at [esp+0x44], need[17] at [esp+0x88], scratch [esp+0xcc],
    best score [esp+0xd0], best player [esp+0xd4].
    """

    a = _Asm(PICK_FN_VA)
    imm = lambda va: struct.pack("<I", va).hex()  # noqa: E731
    a.b("53565755")                                    # push ebx; push esi; push edi; push ebp
    a.b("81ecd8000000")                                # sub esp,0xd8
    a.b("8be9")                                        # mov ebp,ecx        ; team
    a.b("8bfa")                                        # mov edi,edx        ; CPU flag
    a.b("31c031c9")                                    # xor eax,eax ; xor ecx,ecx
    a.label("zero")
    a.b("89048c")                                      # mov [esp+ecx*4],eax
    a.b("41")                                          # inc ecx
    a.b("83f936")                                      # cmp ecx,0x36       ; 54 dwords: sums, counts, need, best
    a.j8("7c", "zero")                                 # jl zero
    a.b("8d842488000000")                              # lea eax,[esp+0x88]
    a.b("50")                                          # push eax           ; &need
    a.b("ff35" + imm(DRAFT_PICK_VA))                   # push [pick]
    a.b("8b15" + imm(DRAFT_ROUND_VA))                  # mov edx,[round]
    a.b("8bcd")                                        # mov ecx,ebp        ; team
    a.call(FN_NEED)                                    # need order (callee pops 8)
    a.b("8b35" + imm(POOL_PTR))                        # mov esi,[POOL_PTR]
    a.b("8b1e")                                        # mov ebx,[esi]      ; count
    a.b("8b7604")                                      # mov esi,[esi+4]    ; base
    a.label("sum_loop")
    a.b("85db")                                        # test ebx,ebx
    a.j8("7e", "sum_done")                             # jle sum_done
    a.b("f6460810")                                    # test byte [esi+8],0x10   ; prospect?
    a.j8("74", "sum_next")                             # jz sum_next
    a.b("8bceba01000000")                              # mov ecx,esi ; mov edx,1
    a.call(FN_RATING)                                  # st0 = overall
    a.b("0fb64635")                                    # movzx eax, byte [esi+0x35]
    a.b("d80484")                                      # fadd dword [esp+eax*4]
    a.b("d91c84")                                      # fstp dword [esp+eax*4]
    a.b("ff448444")                                    # inc dword [esp+eax*4+0x44]
    a.label("sum_next")
    a.b("83c654")                                      # add esi,0x54
    a.b("4b")                                          # dec ebx
    a.j8("eb", "sum_loop")                             # jmp sum_loop
    a.label("sum_done")
    a.jmp_abs(PICK_TAIL_VA)                            # continue in the dead bytes of the old passes
    head = a.assemble()
    _require(len(head) <= PICK_CONST_OFF, f"draft pick head is {len(head)} bytes, over {PICK_CONST_OFF}")
    consts = struct.pack("<2f", NEED_STEP, PICK_JITTER / 256.0)
    head = head + b"\xcc" * (PICK_CONST_OFF - len(head)) + consts
    head = head + b"\xcc" * (PICK_FN_SIZE - len(head))

    a = _Asm(PICK_TAIL_VA)
    a.b("c78424d0000000000000cf")                      # mov dword [esp+0xd0],-2147483648.0 ; best score
    a.b("8b35" + imm(POOL_PTR))                        # mov esi,[POOL_PTR]
    a.b("8b1e")                                        # mov ebx,[esi]
    a.b("8b7604")                                      # mov esi,[esi+4]
    a.j8("eb", "scan_loop")                            # jmp scan_loop
    a.label("scan_next")
    a.b("83c654")                                      # add esi,0x54
    a.b("4b")                                          # dec ebx
    a.label("scan_loop")
    a.b("85db")                                        # test ebx,ebx
    a.j32("0f8e", "scan_done")                         # jle scan_done
    a.b("8a4608")                                      # mov al,[esi+8]
    a.b("a810")                                        # test al,0x10       ; prospect
    a.j8("74", "scan_next")                            # jz scan_next
    a.b("a820")                                        # test al,0x20       ; already drafted
    a.j8("75", "scan_next")                            # jnz scan_next
    a.b("8bceba01000000")                              # mov ecx,esi ; mov edx,1
    a.call(FN_RATING)                                  # st0 = overall
    a.b("0fb64635")                                    # movzx eax, byte [esi+0x35]
    a.b("8b4c8444")                                    # mov ecx,[esp+eax*4+0x44]   ; count at pos (>= 1: he is in it)
    a.b("898c24cc000000")                              # mov [esp+0xcc],ecx
    a.b("db8424cc000000")                              # fild dword [esp+0xcc]
    a.b("d83c84")                                      # fdivr dword [esp+eax*4]    ; st0 = mean, st1 = overall
    a.b("dee9")                                        # fsubp st1,st0              ; overall - mean
    a.b("31c9")                                        # xor ecx,ecx
    a.label("rank_loop")
    a.b("39848c88000000")                              # cmp [esp+ecx*4+0x88],eax
    a.j8("74", "rank_found")                           # je rank_found
    a.b("41")                                          # inc ecx
    a.b("83f911")                                      # cmp ecx,0x11
    a.j8("7c", "rank_loop")                            # jl rank_loop
    a.label("rank_found")
    a.b("ba11000000")                                  # mov edx,0x11
    a.b("2bd1")                                        # sub edx,ecx                ; 17 - rank
    a.b("899424cc000000")                              # mov [esp+0xcc],edx
    a.b("db8424cc000000")                              # fild dword [esp+0xcc]
    a.b("d80d" + imm(PICK_FN_VA + PICK_CONST_OFF))     # fmul [NEED_STEP]
    a.b("dec1")                                        # faddp st1,st0              ; edge + need bonus
    a.b("d80c85" + imm(VALUE_VA))                      # fmul dword [eax*4 + VALUE] ; x positional value
    a.b("85ff")                                        # test edi,edi
    a.j8("74", "no_jitter")                            # jz no_jitter               ; human auto-pick: deterministic
    a.call(FN_RAND)                                    # eax = rand
    a.b("25ff000000")                                  # and eax,0xff
    a.b("898424cc000000")                              # mov [esp+0xcc],eax
    a.b("db8424cc000000")                              # fild dword [esp+0xcc]
    a.b("d80d" + imm(PICK_FN_VA + PICK_CONST_OFF + 4)) # fmul [PICK_JITTER/256]
    a.b("dec1")                                        # faddp st1,st0
    a.label("no_jitter")
    a.b("d89424d0000000")                              # fcom dword [esp+0xd0]
    a.b("dfe0")                                        # fnstsw ax
    a.b("f6c441")                                      # test ah,0x41               ; score <= best
    a.j8("75", "scan_drop")                            # jne scan_drop
    a.b("d99c24d0000000")                              # fstp dword [esp+0xd0]
    a.b("89b424d4000000")                              # mov [esp+0xd4],esi
    a.j32("e9", "scan_next")                           # jmp scan_next
    a.label("scan_drop")
    a.b("ddd8")                                        # fstp st0
    a.j32("e9", "scan_next")                           # jmp scan_next
    a.label("scan_done")
    a.b("8b8424d4000000")                              # mov eax,[esp+0xd4]
    a.b("85c0")                                        # test eax,eax
    a.j8("75", "fin")                                  # jnz fin
    a.b("8b4500")                                      # mov eax,[ebp]              ; retail fallback
    a.label("fin")
    a.b("81c4d8000000")                                # add esp,0xd8
    a.b("5d5f5e5b")                                    # pop ebp; pop edi; pop esi; pop ebx
    a.b("c3")                                          # ret
    tail = a.assemble()
    _require(5 + len(tail) <= BODY_SIZE, f"draft pick tail is {len(tail)} bytes, over {BODY_SIZE - 5}")
    return head, tail


def cave_bytes() -> bytes:
    """The scored selection, assembled for CAVE_VA in the boot-logo bitmap."""

    a = _Asm(CAVE_VA)
    imm = lambda va: struct.pack("<I", va).hex()  # noqa: E731
    NEG = "000000cf"                                   # float -2147483648.0 as the "consumed / impossible" score
    a.b("83ec50")                                      # sub esp,0x50           ; score[17] at [esp], sum [esp+0x44], k [esp+0x48]
    a.b("31ff")                                        # xor edi,edi            ; pos
    a.label("score_loop")
    a.b("83ff11")                                      # cmp edi,0x11
    a.j32("0f8d", "select")                            # jge select
    a.b("c704bc" + NEG)                                # mov dword [esp+edi*4], NEG
    a.b("8b44bc70")                                    # mov eax,[esp+edi*4+0x70]   ; best prospect at pos
    a.b("85c0")                                        # test eax,eax
    a.j32("0f84", "next_pos")                          # jz next_pos
    a.b("8bce8bd7")                                    # mov ecx,esi ; mov edx,edi
    a.call(FN_COUNT_AT_POS)                            # eax = count at pos
    a.b("8be8")                                        # mov ebp,eax
    a.b("8bcf")                                        # mov ecx,edi
    a.call(FN_MAX)                                     # eax = max at pos
    a.b("2bc5")                                        # sub eax,ebp
    a.j32("0f8e", "next_pos")                          # jle next_pos           ; no roster room
    a.b("c744244400000000")                            # mov dword [esp+0x44],0 ; sum
    a.b("c744244800000000")                            # mov dword [esp+0x48],0 ; k
    a.b("85ed")                                        # test ebp,ebp
    a.j8("74", "avg_done")                             # jz avg_done            ; nobody at pos -> average 0
    a.label("sum_loop")
    a.b("8b4c2448")                                    # mov ecx,[esp+0x48]
    a.b("0fb6861c010000")                              # movzx eax, byte [esi+0x11c] ; roster count
    a.b("3bc8")                                        # cmp ecx,eax
    a.j8("7d", "sum_done")                             # jge sum_done
    a.b("8b0c8e")                                      # mov ecx,[esi+ecx*4]    ; player k
    a.b("0fb64135")                                    # movzx eax, byte [ecx+0x35]
    a.b("3bc7")                                        # cmp eax,edi
    a.j8("75", "sum_next")                             # jne sum_next
    a.b("ba01000000")                                  # mov edx,1
    a.call(FN_RATING)                                  # st0 = overall
    a.b("d80d" + imm(CONST_100))                       # fmul [100.0]
    a.b("d8442444")                                    # fadd dword [esp+0x44]
    a.b("d95c2444")                                    # fstp dword [esp+0x44]
    a.label("sum_next")
    a.b("ff442448")                                    # inc dword [esp+0x48]
    a.j8("eb", "sum_loop")                             # jmp sum_loop
    a.label("sum_done")
    a.b("896c2448")                                    # mov [esp+0x48],ebp     ; count
    a.b("db442448")                                    # fild dword [esp+0x48]
    a.b("d87c2444")                                    # fdivr dword [esp+0x44] ; sum / count
    a.b("d95c2444")                                    # fstp dword [esp+0x44]  ; average
    a.label("avg_done")
    a.b("8b4cbc70")                                    # mov ecx,[esp+edi*4+0x70] ; best prospect
    a.b("ba01000000")                                  # mov edx,1
    a.call(FN_RATING)                                  # st0 = prospect overall
    a.b("d80d" + imm(CONST_100))                       # fmul [100.0]
    a.b("d8642444")                                    # fsub dword [esp+0x44]  ; - average
    a.b("d80cbd" + imm(VALUE_VA))                      # fmul dword [edi*4 + VALUE]
    a.b("8bcf")                                        # mov ecx,edi
    a.call(FN_TARGET)                                  # eax = target
    a.b("2bc5")                                        # sub eax,ebp            ; deficit
    a.j8("7e", "no_deficit")                           # jle no_deficit
    a.b("89442448")                                    # mov [esp+0x48],eax
    a.b("db442448")                                    # fild dword [esp+0x48]
    a.b("d80d" + imm(DEFICIT_VA))                      # fmul [DEFICIT_BONUS]
    a.b("dec1")                                        # faddp st1,st0
    a.label("no_deficit")
    a.call(FN_RAND)                                    # eax = rand
    a.b("25ff000000")                                  # and eax,0xff
    a.b("89442448")                                    # mov [esp+0x48],eax
    a.b("db442448")                                    # fild dword [esp+0x48]
    a.b("d80d" + imm(JITTER_VA))                       # fmul [JITTER/256]
    a.b("dec1")                                        # faddp st1,st0
    a.b("d91cbc")                                      # fstp dword [esp+edi*4] ; score[pos]
    a.label("next_pos")
    a.b("47")                                          # inc edi
    a.j32("e9", "score_loop")                          # jmp score_loop
    a.label("select")
    a.b("83fb04")                                      # cmp ebx,4
    a.j8("7d", "done")                                 # jge done
    a.b("31ff")                                        # xor edi,edi
    a.b("bdffffffff")                                  # mov ebp,-1
    a.b("d905" + imm(THRESH_VA))                       # fld [THRESHOLD]        ; st0 = best score
    a.label("argmax_loop")
    a.b("83ff11")                                      # cmp edi,0x11
    a.j8("7d", "argmax_done")                          # jge argmax_done
    a.b("d904bc")                                      # fld dword [esp+edi*4]  ; st0 = score, st1 = best
    a.b("dbf1")                                        # fcomi st0,st1
    a.j8("76", "keep_old")                             # jbe keep_old           ; score <= best
    a.b("ddd9")                                        # fstp st1               ; best = score
    a.b("8bef")                                        # mov ebp,edi
    a.j8("eb", "argmax_next")                          # jmp argmax_next
    a.label("keep_old")
    a.b("ddd8")                                        # fstp st0
    a.label("argmax_next")
    a.b("47")                                          # inc edi
    a.j8("eb", "argmax_loop")                          # jmp argmax_loop
    a.label("argmax_done")
    a.b("ddd8")                                        # fstp st0               ; drop best
    a.b("83fdff")                                      # cmp ebp,-1
    a.j8("74", "done")                                 # je done                ; nothing above threshold
    a.b("c704ac" + NEG)                                # mov dword [esp+ebp*4], NEG ; consume position
    a.b("8b44ac70")                                    # mov eax,[esp+ebp*4+0x70]   ; its best prospect
    a.b("56")                                          # push esi               ; team
    a.call(FN_WISH)                                    # eax = wish created?
    a.b("85c0")                                        # test eax,eax
    a.j8("74", "select")                               # jz select
    a.b("43")                                          # inc ebx
    a.j8("eb", "select")                               # jmp select
    a.label("done")
    a.b("895c2460")                                    # mov [esp+0x60],ebx     ; the frame's copy of the wish count
    a.b("83c450")                                      # add esp,0x50
    a.jmp_abs(BODY_END_VA)                             # jmp 0x324545
    code = a.assemble()
    _require(CAVE_VA + len(code) <= LOGO_END_VA, f"cave is {len(code)} bytes, overruns the boot-logo bitmap")
    return code


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise DraftAiError(f"VA 0x{va:x} is in no section")


def _sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    consts = const_bytes()
    _require(len(consts) == 80, "constant block must be 80 bytes")
    _require(len(RETAIL_LOGO_AF0) == LOGO_END_VA - VALUE_VA, "retail logo transcript must cover 0x10AF0..0x10CC2")
    _require(len(RETAIL_PICK_FN) == PICK_FN_SIZE, "retail transcript must cover the whole pick routine")
    cave = cave_bytes()
    cave_off = CAVE_VA - VALUE_VA
    sites = [
        ("constants", _offset(payload, VALUE_VA), RETAIL_LOGO_AF0[:80], consts),
        ("cave", _offset(payload, CAVE_VA), RETAIL_LOGO_AF0[cave_off: cave_off + len(cave)], cave),
        ("body_jump_and_pick_tail", _offset(payload, BODY_VA), RETAIL_BODY, body_patch()),
        ("draft_pick_head", _offset(payload, PICK_FN_VA), RETAIL_PICK_FN, pick_fn_bytes()[0]),
    ]
    for pos, struct_va, retail_bits in ROOKIE_KEY_SITES:
        before = struct.pack("<I", retail_bits)
        after = struct.pack("<f", struct.unpack("<f", before)[0] / ROOKIE_KEY_SCALE[pos])
        sites.append((f"rookie_key_scale_{pos.lower()}", _offset(payload, struct_va + ROOKIE_KEY_SCALE_OFF), before, after))
    return sites


def rookie_key_tables(payload: bytes) -> dict[str, dict[str, object]]:
    """The 17 scouting-key tables as the game reads them: {position: {base, scale, entries}}."""

    ptrs = struct.unpack_from("<17I", payload, _offset(payload, ROOKIE_KEY_TABLES_VA))
    out = {}
    for pos, ptr in zip(POSITIONS, ptrs):
        base, scale, count, entries = struct.unpack_from("<ffII", payload, _offset(payload, ptr))
        rows = [struct.unpack_from("<4B", payload, _offset(payload, entries) + 4 * k) for k in range(count)]
        out[pos] = {"va": f"0x{ptr:x}", "base": round(base, 4), "scale": round(scale, 4),
                    "entries": [{"weight": w, "lo": lo, "hi": hi, "category": cat} for w, lo, hi, cat in rows]}
    return out


def status(payload: bytes) -> str:
    try:
        sites = _sites(payload)
    except (DraftAiError, ValueError, struct.error):
        return "foreign"
    states = set()
    for _label, off, before, after in sites:
        got = payload[off: off + len(before)]
        states.add("retail" if got == before else "applied" if got == after else "foreign")
    if states == {"retail"}:
        return "retail"
    if states == {"applied"}:
        return "applied"
    return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload)
    _require(state == "retail", f"draft-AI sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    header = _header_size(payload)
    touched = set()
    edits = []
    for label, off, before, after in _sites(payload):
        buf[off: off + len(after)] = after
        if off >= header:
            touched.add(_section_for_offset(sections, off).index)
        edits.append({"label": label, "file_offset": f"0x{off:x}", "bytes": len(after)})
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    patched = bytes(buf)
    _require(status(patched) == "applied", "post-apply verification failed")
    changed = sum(1 for a, b in zip(payload, patched) if a != b)
    return patched, {"edits": edits, "changed_bytes": changed, "sections_repinned": sorted(touched),
                     "code_bytes": len(cave_bytes()) + PICK_CONST_OFF - pick_fn_bytes()[0][:PICK_CONST_OFF].count(b"\xcc") + len(pick_fn_bytes()[1]),
                     "values": dict(zip(POSITIONS, (VALUE[p] for p in POSITIONS))),
                     "need_step": NEED_STEP, "pick_jitter": PICK_JITTER,
                     "rookie_key_scale": dict(ROOKIE_KEY_SCALE)}


__all__ = ["DraftAiError", "BODY_VA", "CAVE_VA", "PICK_FN_VA", "PICK_FN_SIZE", "RETAIL_PICK_FN", "VALUE_VA", "VALUE",
           "ROOKIE_KEY_SITES", "ROOKIE_KEY_SCALE", "ROOKIE_KEY_TABLES_VA",
           "apply", "body_patch", "cave_bytes", "const_bytes", "pick_fn_bytes", "rookie_key_tables", "status"]

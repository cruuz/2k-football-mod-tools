"""Stop franchise teams from putting a quarterback at kick or punt returner (executable patch, xemu-only).

Root cause (retail ``default.xbe``).  The franchise auto depth chart, ``FUN_002bdcf0`` (0x2BDCF0),
runs every week and after every offseason stage for each CPU team (and for human teams with the
"CPU manages my depth chart" option, ``DAT_00e60140``).  After sorting each position by overall it
picks the returners in a loop over the roster (0x2BDE70..0x2BDFD0):

* kick returner: best "returner" score (rating category 10 = 0.4 speed + 0.2 agility + 0.1 stamina
  + 0.2 break tackle + 0.1 secure ball, ``FUN_00246a80``) among non-starting WR/CB/RB/FB;
* punt returner: the best score among non-starting CB/FS/SS — but the loop never records **which
  player** had the best punt-return score.  It only keeps the score (a 0..1 float) and at the end
  stores ``(int)score`` as the roster index (0x2BDFBE: ``cvttss2si`` of the score, ``mov
  [team+0x199], al``).  So the punt returner is always roster slot 0 (or 1), whoever that is.  In
  franchise the first roster slot is routinely a quarterback (retail rosters list by position
  name, and offseason signings/retirements shuffle the slots), hence a QB fielding punts.
* the second kick returner has the same bug in a milder form (its score is never updated, only
  its index), and the loop stops one player short of the roster end.

The patch rewrites those 352 bytes in place (same frame, same registers, same helpers):

* two passes over the roster: pass 0 excludes starters (retail rule, so stars do not return
  kicks); pass 1 only runs for a slot still empty and lets anyone at an eligible position fill it;
* eligibility by position mask (tunable bytes at the end of the patched region): KR = WR, CB, FS,
  SS, RB, FB; PR = WR, CB, FS, SS, RB; K/P/QB/OL/DL/LB never;
* best and second-best kick returner **and** the best punt returner are tracked by index; the
  whole roster is scanned; the game's own category-10 score is the ranking key;
* b780 st1 (MC1 U9b): an injured player (+0x20 bit 31, the flag the weekly injury tick 0x133BD0 counts
  down) is skipped in both passes, so the next healthy eligible player returns; only when no healthy
  player can return kicks at all, passes 2 and 3 repeat passes 0 and 1 with the injured allowed, so such
  a club keeps the pick it had before (no slot is ever left empty).  The beta-79 .. beta-80 loop is
  recognised as ``previous`` and upgrades in place.

Pattern-checked against the retail bytes, ``.text`` digest recomputed.  Unverified at runtime.

b780 st1 (second site, the returner getter).  Every depth-chart view of the kick and punt returners and
the re-rank ``FUN_00243790`` read the team's returner bytes through ``FUN_00242a60`` (0x242A60, called
only by the row getter ``FUN_00242ae0`` for position codes 0xFE KR and 0xFD PR):
``mov eax,[team + slot*4]`` with no check.  An empty byte (0xFF, written natively by the roster-removal
handler 0xC3A90 when the KR1/KR2/PR player is cut or traded, and shipped in the pack rosters for three
clubs' KR2) reads the dword in front of the team record: the previous club's +0x1F0.  Retail rosters
keep that dword 0, so the getter said "no player" and the re-rank fell back to the next returner.  The
practice-squad metadata (+0x1F2 count, +0x1F3 marker 0xA5, every club since the practice squad) makes
it 0xA5NN0000, a pointer to nowhere: the Special Teams KR list's photo row (0x242D10 -> 0xE7170) and
the KR/PR rows dereference it (a page fault, the game freezes) and the re-rank stores roster slot 0.
The getter is rewritten in place (96 of its 128 bytes): the same results for every valid byte, and a
byte that is not a roster slot of the team (0x80..0xFF or at least the player count) reads as no
player, as retail rosters always did.

b780 st1, three more sites (all in place, retail-pinned):

* the line-up builder ``FUN_000e7c50`` (game setup 0x6476A -> 0xE80D0, and the depth chart) checks
  KR1/KR2/PR only for -1; a byte at or past the player count read a vacated (NULL) slot and faulted in
  the availability test 0xE7900 (the game froze setting up the game).  Its KR1 load at 0xE7CC5 calls a
  32-byte slot check placed after the getter: such a byte becomes -1, which the builder already skips;
* the weekly exchange store ``FUN_000c3d70`` (the weekly sort swaps two players with two stores) cleared
  every specialist byte pointing at either slot, so the long snapper, the holder and the kicker bytes
  were lost whenever their slot moved (all 32 clubs by the second season).  It is rewritten in its 128
  bytes so each byte follows its player (see ``_exchange_code``); a real replacement still clears;
* the weekly loop head 0x2BDD1B (HUNT6's finding): the postseason puts the AFC and NFC Pro Bowl teams in
  league slots 32/33 and the weekly auto-depth sorted them, moving their members on their own clubs.  The
  call now goes to an all-star skip in the exchange site's spare bytes, so Basic and Advanced (no depth
  locks) skip them as depth locks revision 5 does.  The returner fix owns this call: depth locks accepts
  it as its own skip site and leaves it, and on an image where depth locks came first the returner fix
  reads depth locks' call as ``previous`` (status ``legacy``) and points it at its own skip, so either
  order ends in the same bytes.
"""

from __future__ import annotations

import struct
from typing import Mapping

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_draft_ai import _Asm

IMAGE_BASE = 0x10000
SITE_VA = 0x002BDE70            # first byte of the retail returner loop (inside FUN_002bdcf0)
SITE_END_VA = 0x002BDFD0        # `mov esi,[esp+0x2c]`: the outer team loop continues here
SITE_SIZE = SITE_END_VA - SITE_VA   # 352
FN_CATEGORY = 0x00246A80        # thiscall(ecx=player, edx=1, [esp]=category) -> st0, callee pops the arg
FN_FINISH_DEPTH = 0x00243790    # fastcall(ecx=team): re-rank every position after the returners are set
CATEGORY_RETURNER = 10

POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
KR_ELIGIBLE = ("WR", "CB", "FS", "SS", "RB", "FB")
PR_ELIGIBLE = ("WR", "CB", "FS", "SS", "RB")

RETAIL_SITE = bytes.fromhex(
    "0fb6871c01000033c933db4885c0894c2420894c2428894c2424894c241c894c24180f8e0d010000eb0633c98d6424008b34"
    "9f668b4628f6c41cbd01000000750233ed0fb656358bca83e9037403497509f6c4e00f84ca00000033c93be90f84c0000000"
    "8d42fd83f805774fff248508e02b006a0aba010000008bcee88f8bf8ffd95c2410c744241400000000eb346a0aba01000000"
    "8bcee8738bf8ffd95c2410eb04894c24106a0aba010000008bcee85b8bf8ffd95c2414eb08894c2410894c2414d9442410d8"
    "5c2420dfe0f6c441751e8b4c24208b44241c8b542410894c24288954242089442418895c241ceb1dd9442410d85c2428dfe0"
    "f6c441750e8b4c241051e847eaffff895c2418d9442414d85c2424dfe0f6c44175088b542414895424240fb6871c01000043"
    "483bd80f8cf5feffff8b4424248a4c241c8a54241850888f95010000889796010000e8fde9ffff8bcf888799010000e8c057"
    "f8ff"
)


# b780 st1: the returner getter FUN_00242a60 (eax = 0xFE KR / 0xFD PR, ecx = list row, edx = team) and the two
# padding nops after it, up to the row getter FUN_00242ae0.  Retail bytes = v0.8 = v0.9 RC bytes.
GETTER_VA = 0x00242A60
GETTER_SIZE = 0x80
ROW_LABEL_VA = 0x242980
ROW_LABEL_SIZE = 0x50
RETAIL_ROW_LABEL = bytes.fromhex("a18074c1008b4c240403c283e8006a00742d48741d48740dba0889e800e85e7ae0ffc20c00baf488e800e8517ae0ffc20c00bae088e800e8447ae0ffc20c00bacc88e800e8377ae0ffc20c0090909090")
SUMMARY_TAIL_VA = 0x242C2D      # in 0x242C00, after it loads the descriptor's position and side
SUMMARY_FILTER_VA = 0x242C50
SUMMARY_NAME_RETURN = 0x243AC5
SUMMARY_JERSEY_RETURN = 0x243B06
RETAIL_SUMMARY_TAIL = bytes.fromhex(
    "743983f904751556528b159c74c100b90100000051e899feffff5ec383f906751556528b159c74c100b90200000051e87ffeffff5ec3"
    "83f901751256528b159c74c10033c951e868feffff5ec333c083f9030f95c056528b159c74c100408bc851e84dfeffff5ec3"
)
NTH_SIZE = 0x90
RETAIL_NTH = bytes.fromhex(
    "518b5424080fb6831c010000558b6c24105733ff2bd63bc789542410897c24087e5f8b04bb33c985f6ba010000007e113b448d00750233d2413bce7cf385d274348b54241c33c985"
    "d27e2a0fb65035908b6c24183b548d00750e8b6c2410396c2408741fff4424088b6c241c413bcd7cdf8b6c24140fb6831c010000473bf87ca133c05f5d59c2100090909090909090"
)
FN_NTH_RETURNER = 0x002429D0    # stdcall(row, exclusions, position table, count; ebx = team, esi = exclusions) -> eax
NTH_POSITIONS = 0x00514D38      # its retail table of the six kick-return positions
TEAM_COUNT = 0x11C
TEAM_KR1, TEAM_PR = 0x195, 0x199
RETAIL_GETTER = bytes.fromhex(
    "83ec08535633f63dfe0000008bda75343bce0fbe83950100000fbe93960100008b04838b1493894424088954240c744883f9"
    "0175085e8bc25b83c408c3be02000000eb223dfd000000751b3bce0fbe83990100008b0483894424088974240c7417be0100"
    "00006a0668384d51008d5424105251e8f8feffff5e5b83c408c39090"
)

# b780 st1 (Q91): the line-up builder's KR1 load (0xE7CC5, inside FUN_000e7c50) calls the slot check that sits
# after the getter in the same site.
LINEUP_HELPER_VA = GETTER_VA + 96
LINEUP_HOOK_VA = 0x000E7CC5
RETAIL_LINEUP_HOOK = bytes.fromhex("0fbe8895010000")        # movsx ecx, byte [eax+0x195]
# b780 st1 (Q34, Q32): the weekly exchange store FUN_000c3d70 and its padding up to FUN_000c3df0; its spare
# bytes carry the all-star skip that the weekly loop head calls (0x2BDD1B).
EXCHANGE_VA = 0x000C3D70
EXCHANGE_SIZE = 0x80
ALL_STAR_SKIP_VA = EXCHANGE_VA + 0x68
RETAIL_EXCHANGE = bytes.fromhex(
    "8b442404891481560fbeb19401000080caff3bc675068891940100000fbeb1950100003bc675068891950100000fbeb196"
    "0100003bc675068891960100000fbeb1970100003bc675068891970100000fbeb1980100003bc675068891980100000fbe"
    "b1990100003bc65e7506889199010000c204009090909090909090909090"
)
ALL_STAR_CALL_VA = 0x002BDD1B                                # the weekly loop head's user-club test
RETAIL_ALL_STAR_CALL = bytes.fromhex("e8100fe8ff")           # call 0x13EC30
DEPTH_LOCKS_ALL_STAR_CALL = bytes.fromhex("e8de4ff8ff")      # call 0x242CFE: depth locks revision 5's own skip
FN_USER_CLUB = 0x0013EC30
WEEKLY_LOOP_TAIL_VA = 0x002BDFD0


class ReturnerFixError(ValueError):
    """The returner patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReturnerFixError(message)


def mask_bytes() -> bytes:
    kr = bytes(1 if p in KR_ELIGIBLE else 0 for p in POSITIONS)
    pr = bytes(1 if p in PR_ELIGIBLE else 0 for p in POSITIONS)
    return kr + pr


def _code(masks_va: int, v2: bool = False) -> bytes:
    """The replacement loop.  edi = team; [esp+0x10..0x28] are the routine's own scratch dwords:
    0x10 best KR score, 0x14 its index, 0x18 second KR score, 0x1c its index, 0x20 best PR score,
    0x24 its index, 0x28 pass number.  [esp+0x2c] (the team counter) is left alone.  A score of
    0.0 means "nobody yet"; indices default to 0 (the retail default) but are only used with a score."""

    a = _Asm(SITE_VA)
    imm = lambda va: struct.pack("<I", va).hex()  # noqa: E731
    kr_mask = masks_va
    pr_mask = masks_va + len(POSITIONS)
    a.b("31c0")                                # xor eax,eax
    a.b("b907000000" if v2 else "6a0759")     # mov ecx,7 (push 7 ; pop ecx)
    a.label("init")
    a.b("89448c0c")                            # mov [esp+ecx*4+0x0c],eax   ; 0x10..0x28 := 0
    a.b("49")                                  # dec ecx
    a.j8("75", "init")                         # jnz init
    a.label("pass_loop")
    a.b("31db")                                # xor ebx,ebx          ; roster index
    a.j8("eb", "cand_loop")                    # jmp cand_loop
    a.label("next")
    a.b("43")                                  # inc ebx
    a.label("cand_loop")
    a.b("0fb6871c010000")                      # movzx eax, byte [edi+0x11c]   ; roster count
    a.b("3bd8")                                # cmp ebx,eax
    a.j32("0f8d", "cand_done")                 # jge cand_done
    a.b("8b349f")                              # mov esi,[edi+ebx*4]  ; player
    a.b("0fb65635")                            # movzx edx, byte [esi+0x35]    ; position
    a.b("83fa11")                              # cmp edx,17
    a.j8("73", "next")                         # jae next
    a.b("0fb68a" + imm(kr_mask))               # movzx ecx, byte [edx+KR_MASK]
    a.b("0fb6aa" + imm(pr_mask))               # movzx ebp, byte [edx+PR_MASK]
    a.b("8d2c69")                              # lea ebp,[ecx+ebp*2]  ; bit0 = KR eligible, bit1 = PR eligible
    a.b("85ed")                                # test ebp,ebp
    a.j8("74", "next")                         # jz next
    if v2:
        a.b("837c242800")                      # cmp dword [esp+0x28],0
        a.j8("75", "scored")                   # jne scored          ; pass 1: starters allowed
    else:
        # b780 st1 (MC1 U9b): an injured player (+0x20 bit 31, the weekly injury tick's flag) is not a returner in
        # passes 0 and 1; passes 2 and 3 repeat today's passes 0 and 1 with him allowed, and run only when no
        # healthy player can return kicks at all, so such a club keeps today's pick
        a.b("f6462380")                        # test byte [esi+0x23],0x80
        a.j8("74", "healthy")
        a.b("f644242802")                      # test byte [esp+0x28],2
        a.j8("74", "next")
        a.label("healthy")
        a.b("f644242801")                      # test byte [esp+0x28],1   ; passes 1 and 3: starters allowed
        a.j8("75", "scored")
    a.b("f646291c")                            # test byte [esi+0x29],0x1c     ; depth rank 0 = starter
    a.j8("74", "next")                         # jz next
    a.b("83fa03")                              # cmp edx,3           ; WR
    a.j8("74", "wr_cb")                        # je wr_cb
    a.b("83fa04")                              # cmp edx,4           ; CB
    a.j8("75", "scored")                       # jne scored
    a.label("wr_cb")
    a.b("f64629e0")                            # test byte [esi+0x29],0xe0     ; side bits 0 = the other starter
    a.j8("74", "next")                         # jz next
    a.label("scored")
    a.b("6a0a")                                # push 10             ; returner category
    a.b("ba01000000" if v2 else "33d242")     # mov edx,1 (xor edx,edx ; inc edx)
    a.b("8bce")                                # mov ecx,esi
    a.call(FN_CATEGORY)                        # st0 = score (ebx/esi/edi/ebp preserved)
    if v2:
        a.b("f7c501000000")                    # test ebp,1
        a.j8("74", "pr_part")                  # jz pr_part
    else:
        a.b("0fbae500")                        # bt ebp,0
        a.j8("73", "pr_part")                  # jnc pr_part
    a.b("d8542410")                            # fcom dword [esp+0x10]
    a.b("dfe0")                                # fnstsw ax
    a.b("f6c441")                              # test ah,0x41        ; score <= best
    a.j8("75", "kr_second")                    # jne kr_second
    a.b("8b442410")                            # mov eax,[esp+0x10]
    a.b("89442418")                            # mov [esp+0x18],eax  ; second = old best
    a.b("8b442414")                            # mov eax,[esp+0x14]
    a.b("8944241c")                            # mov [esp+0x1c],eax
    a.b("d9542410")                            # fst dword [esp+0x10]
    a.b("895c2414")                            # mov [esp+0x14],ebx
    a.j8("eb", "pr_part")                      # jmp pr_part
    a.label("kr_second")
    a.b("d8542418")                            # fcom dword [esp+0x18]
    a.b("dfe0")                                # fnstsw ax
    a.b("f6c441")                              # test ah,0x41
    a.j8("75", "pr_part")                      # jne pr_part
    a.b("d9542418")                            # fst dword [esp+0x18]
    a.b("895c241c")                            # mov [esp+0x1c],ebx
    a.label("pr_part")
    if v2:
        a.b("f7c502000000")                    # test ebp,2
        a.j8("74", "drop")                     # jz drop
    else:
        a.b("0fbae501")                        # bt ebp,1
        a.j8("73", "drop")                     # jnc drop
    a.b("d8542420")                            # fcom dword [esp+0x20]
    a.b("dfe0")                                # fnstsw ax
    a.b("f6c441")                              # test ah,0x41
    a.j8("75", "drop")                         # jne drop
    a.b("d9542420")                            # fst dword [esp+0x20]
    a.b("895c2424")                            # mov [esp+0x24],ebx
    a.label("drop")
    a.b("ddd8")                                # fstp st0
    a.j32("e9", "next")                        # jmp next
    a.label("cand_done")
    if v2:
        a.b("837c242800")                      # cmp dword [esp+0x28],0
        a.j8("75", "finalize")                 # jne finalize
        a.b("ff442428")                        # inc dword [esp+0x28]
        a.b("837c241000")                      # cmp dword [esp+0x10],0
        a.j32("0f84", "pass_loop")             # je pass_loop        ; no kick returner: allow starters
        a.b("837c242000")                      # cmp dword [esp+0x20],0
        a.j32("0f84", "pass_loop")             # je pass_loop        ; no punt returner
    else:
        a.b("8a442428")                        # mov al,[esp+0x28]   ; the pass just done
        a.b("ff442428")                        # inc dword [esp+0x28]
        a.b("a801")                            # test al,1
        a.j8("75", "odd_done")
        a.b("837c241000")                      # cmp dword [esp+0x10],0   ; pass 0 or 2 left a slot empty:
        a.j8("74", "again")                    # je again                 ; the same players with starters
        a.b("837c242000")                      # cmp dword [esp+0x20],0
        a.j8("75", "finalize")
        a.label("again")
        a.j32("e9", "pass_loop")               # jmp pass_loop
        a.label("odd_done")
        a.b("3c01")                            # cmp al,1            ; after pass 3: done
        a.j8("75", "finalize")
        a.b("837c241000")                      # cmp dword [esp+0x10],0   ; no healthy kick returner at all (the
        a.j8("74", "again")                    # je again                 ; punt returners are a subset): today's
                                               #                          ; passes with the injured allowed
    a.label("finalize")
    a.b("8b442414")                            # mov eax,[esp+0x14]  ; KR1 (0 = retail default when nobody)
    a.b("8b4c241c")                            # mov ecx,[esp+0x1c]  ; KR2
    a.b("837c241800")                          # cmp dword [esp+0x18],0
    a.j8("75", "have_kr2")                     # jne have_kr2
    a.b("8bc8")                                # mov ecx,eax         ; no runner-up: same man
    a.label("have_kr2")
    a.b("8b542424")                            # mov edx,[esp+0x24]  ; PR
    a.b("837c242000")                          # cmp dword [esp+0x20],0
    a.j8("75", "have_pr")                      # jne have_pr
    a.b("8bd0")                                # mov edx,eax         ; no punt returner: the kick returner
    a.label("have_pr")
    a.b("888795010000")                        # mov [edi+0x195],al
    a.b("888f96010000")                        # mov [edi+0x196],cl
    a.b("889799010000")                        # mov [edi+0x199],dl
    a.b("8bcf")                                # mov ecx,edi
    a.call(FN_FINISH_DEPTH)                    # re-rank the depth chart (retail call)
    a.jmp_abs(SITE_END_VA)                     # jmp 0x2bdfd0
    return a.assemble()


def site_bytes(v2: bool = False) -> bytes:
    """Code, then the two 17-byte eligibility masks, int3-padded to the retail loop's size.  ``v2`` is the loop of
    beta-79 .. beta-80 before the injury test (recognised so those images upgrade in place)."""

    probe = _code(SITE_VA, v2)                 # size pass: the mask address depends on the code size
    masks_va = SITE_VA + len(probe)
    code = _code(masks_va, v2)
    _require(len(code) == len(probe), "assembler size drift")
    body = code + mask_bytes()
    _require(len(body) <= SITE_SIZE, f"returner patch is {len(body)} bytes, over {SITE_SIZE}")
    return body + b"\xcc" * (SITE_SIZE - len(body))


def _row_label_code() -> bytes:
    """The four adjacent Special Teams labels in the retail order, including its default for every other row."""
    a = _Asm(ROW_LABEL_VA)
    a.b("a18074c100 01d0 83f803")
    a.j8("72", "label")
    a.b("6a03 58")
    a.label("label")
    a.b("6bc014 8d90cc88e800 8b4c2404 6a00")
    a.call(0x4A400)
    a.b("c20c00")
    return a.assemble()


def summary_tail_bytes() -> bytes:
    """Preserve the shared selector's column mapping and identify its two read-only formatters."""
    a = _Asm(SUMMARY_TAIL_VA)
    a.b("49 83f906")                        # decrement the column; 1..6 each form a jersey/name pair
    a.j8("72", "pair")
    a.b("6a04 59")                          # other columns take the retail default, rank 2
    a.label("pair")
    a.b("d1e9 56 52 51 8b159c74c100")       # rank /= 2; push side, position, rank; EDX = team
    a.call(0x242AE0)
    a.label("row_return")
    a.b("5e c3")                           # restore the selector's saved ESI
    selector = a.assemble()
    _require(len(selector) <= SUMMARY_FILTER_VA - SUMMARY_TAIL_VA, "returner summary selector exceeds its room")

    check = _Asm(SUMMARY_FILTER_VA)
    check.b("8b54244c")                    # caller of 0x242AE0, including this filter's return address
    check.b("81fa" + struct.pack("<I", SUMMARY_TAIL_VA + a.labels["row_return"]).hex())
    check.j8("74", "summary")
    check.b("81ea002d2400 81fa000b0000 c3") # carry for an existing detail callback in 0x242D00..0x2437FF
    check.label("summary")
    check.b("8b542460")                    # above three row arguments and saved ESI: caller of 0x242C00
    for caller in (SUMMARY_NAME_RETURN, SUMMARY_JERSEY_RETURN):
        check.b("81fa" + struct.pack("<I", caller).hex())
        check.j8("74", "draw")
    check.b("f8 c3")                       # clear carry: edit, duplicate check or another consumer
    check.label("draw")
    check.b("f9 c3")
    body = selector.ljust(SUMMARY_FILTER_VA - SUMMARY_TAIL_VA, b"\xcc") + check.assemble()
    _require(len(body) <= len(RETAIL_SUMMARY_TAIL), "returner summary filter exceeds its room")
    return body.ljust(len(RETAIL_SUMMARY_TAIL), b"\xcc")


def _display_check() -> bytes:
    """Only detail draws and the two summary formatters may replace an unavailable named returner."""
    start = ROW_LABEL_VA + len(_row_label_code())
    a = _Asm(start)
    a.call(SUMMARY_FILTER_VA)
    a.j8("73", "done")
    a.b("85c0")
    a.j8("74", "done")
    a.b("8b542404 85d2")                   # first named slot on the getter's stack
    a.j8("74", "selected")
    a.b("f6422770")
    a.j8("75", "fielded")
    a.label("selected")
    a.b("f6402770")
    a.j8("74", "done")
    a.label("fielded")
    a.b("ebfe")                            # short jump to the lineup lookup, patched below
    a.label("done")
    a.b("c3")
    code = bytearray(a.assemble())
    at = a.labels["fielded"]
    rel = FN_NTH_RETURNER + len(_nth_code()) - (start + at + 2)
    _require(-128 <= rel < 128, "the returner lineup lookup is out of short-jump range")
    code[at + 1] = rel & 0xFF
    return bytes(code)


def row_label_bytes() -> bytes:
    body = _row_label_code() + _display_check()
    _require(len(body) <= ROW_LABEL_SIZE, "returner display exceeds the Special Teams label routine")
    return body.ljust(ROW_LABEL_SIZE, b"\xcc")


def _nth_code() -> bytes:
    """The retail list lookup, compacted inside its original 144-byte function to share the space with the row display."""
    a = _Asm(FN_NTH_RETURNER)
    a.b("55 57 51")             # save EBP, EDI and ECX as the native function does
    a.b("8b542410 2bd6")
    a.j8("78", "empty")
    a.b("31ed")   # requested row minus number of named entries; EBP = club slot
    a.label("player")
    a.b("89e8 3a831c010000")
    a.j8("73", "empty")         # slot >= club count
    a.b("8b04ab 89f1 8b7c2414") # EAX=player; ECX=excluded count; EDI=excluded list
    a.b("85c9")
    a.j8("7e", "positions")
    a.b("f2af")                 # search excluded player pointers
    a.j8("74", "next")
    a.label("positions")
    a.b("8b4c241c 8b7c2418")    # number of position codes, their address
    a.b("50 0fb64035")          # preserve the player, compare his position against the list
    a.label("position")
    a.b("85c9")
    a.j8("7e", "miss")
    a.b("f2af")
    a.j8("75", "miss")
    a.b("4a")                   # count each match (including a repeated position, as in retail)
    a.j8("79", "position")
    a.b("58")
    a.j8("eb", "done")
    a.label("miss")
    a.b("58")
    a.label("next")
    a.b("45")
    a.j8("eb", "player")
    a.label("empty")
    a.b("31c0")
    a.label("done")
    a.b("59 5f 5d c21000")
    return a.assemble()


def _available_returner() -> bytes:
    """Resolve an unavailable named depth row through the same lineup builder that actually fields the returner."""
    a = _Asm(FN_NTH_RETURNER + len(_nth_code()))
    a.b("89cf")                               # EDI = named row (preserved by the builder)
    a.b("81ec34030000 89e2 89d9 6a00 6a00")     # allocate a native lineup context and use normal availability
    a.call(0xE80D0)
    # The native builder packs its positional lists consecutively, with one directory pointer per kind.
    # 28 minus the number of named rows selects kind 26 for KR (two rows) or 27 for PR (one row).
    a.b("6a1c 59 29f1 89ce 89e2")               # ECX = ESI = list kind, EDX = built lineup context
    a.call(0xE75A0)                             # native number of candidates in this list
    a.b("39c7")                                 # cmp edi,eax
    a.j8("73", "empty")                         # a missing KR2 must never read the first PR
    a.b("89e2 57 52 89f0 31c9")                 # row, context; EAX = kind, ECX = normal roster lookup
    a.call(0xE7810)                             # same native lookup used by match personnel selection
    a.j8("eb", "done")
    a.label("empty")
    a.b("31c0")
    a.label("done")
    a.b("81c434030000 c3")
    return a.assemble()


def lookup_bytes() -> bytes:
    body = _nth_code() + _available_returner()
    _require(len(body) <= NTH_SIZE, f"returner lookup requires {len(body)} bytes")
    return body.ljust(NTH_SIZE, b"\xcc")


def _getter_code(v1: bool = False, *, previous: bool = False) -> bytes:
    """FUN_00242a60 with a slot check.  in: eax = 0xFE (KR) / 0xFD (PR), ecx = list row, edx = team.
    out: eax = player or 0.  The named slots (KR1, KR2 or PR) go into a zeroed two-dword exclusion list,
    each only when its byte is a roster slot of the team (unsigned byte below the player count); a row
    below the named count returns that entry, any other row is the retail FUN_002429d0 call with the same
    arguments (row, list, the six kick-return positions, 6; ebx = team, esi = named count).  ebx, esi, edi
    are kept; the only caller, FUN_00242ae0, keeps the rest.  ``v1`` is the first b780 st1 form (98 bytes,
    the list pushed as two immediates), recognised so an image built with it upgrades in place."""

    a = _Asm(GETTER_VA)
    a.b("53")                                  # push ebx
    a.b("56")                                  # push esi
    a.b("57")                                  # push edi
    if v1:
        a.b("6a00")                            # push 0            ; list[1]
        a.b("6a00")                            # push 0            ; list[0]  (list at [esp])
        a.b("8bda")                            # mov ebx,edx       ; team
        a.b("33f6")                            # xor esi,esi       ; named slots
    else:
        a.b("33f6")                            # xor esi,esi       ; named slots
        a.b("56")                              # push esi          ; list[1] = 0
        a.b("56")                              # push esi          ; list[0] = 0  (list at [esp])
        a.b("8bda")                            # mov ebx,edx       ; team
    a.b("8dbb" + struct.pack("<I", TEAM_PR).hex())   # lea edi,[ebx+0x199]  ; PR byte
    a.b("3dfd000000" if v1 or previous else "3cfd")                          # cmp eax,0xfd
    a.j8("74", "one_more")                     # je  -> 1 named slot
    a.b("3dfe000000" if v1 or previous else "3cfe")                          # cmp eax,0xfe
    a.j8("75", "nth")                          # jne -> no named slot (retail: never called so)
    a.b("8dbb" + struct.pack("<I", TEAM_KR1).hex())  # lea edi,[ebx+0x195]  ; KR1 byte, KR2 follows
    a.b("46")                                  # inc esi
    a.label("one_more")
    a.b("46")                                  # inc esi           ; 1 PR, 2 KR
    a.b("33d2")                                # xor edx,edx
    a.label("fill")
    a.b("0fbe0417")                            # movsx eax, byte [edi+edx]
    a.b("3a83" + struct.pack("<I", TEAM_COUNT).hex())  # cmp al, byte [ebx+0x11c]
    a.j8("73", "skip")                         # jae skip          ; 0xFF (empty) or past the roster
    a.b("8b0483")                              # mov eax,[ebx+eax*4]
    a.b("890494")                              # mov [esp+edx*4],eax
    a.label("skip")
    a.b("42")                                  # inc edx
    a.b("3bd6")                                # cmp edx,esi
    a.j8("72", "fill")                         # jb fill
    a.b("3bce")                                # cmp ecx,esi
    a.j8("73", "nth")                          # jae nth
    a.b("8b048c")                              # mov eax,[esp+ecx*4]
    if not (v1 or previous):
        a.call(ROW_LABEL_VA + len(_row_label_code()))
    a.j8("eb", "done")                         # jmp done
    a.label("nth")
    a.b("6a06")                                # push 6
    a.b("68" + struct.pack("<I", NTH_POSITIONS).hex())  # push 0x514d38
    a.b("8d542408")                            # lea edx,[esp+8]   ; the list
    a.b("52")                                  # push edx
    a.b("51")                                  # push ecx          ; row
    a.call(FN_NTH_RETURNER)                    # ret 0x10
    a.label("done")
    a.b("83c408")                              # add esp,8
    a.b("5f")                                  # pop edi
    a.b("5e")                                  # pop esi
    a.b("5b")                                  # pop ebx
    a.b("c3")                                  # ret
    return a.assemble()


def _lineup_helper_code() -> bytes:
    """b780 st1 (Q91): called from 0xE7CC5 in the line-up builder FUN_000e7c50 in place of its
    ``movsx ecx, byte [eax+0x195]``.  in: eax = team, ecx = player count (0xE7CA6), edx = PR, ebx = KR2
    (sign-extended bytes), flags = ``cmp edi,7`` for the builder's jge at 0xE7CDC.  out: edx, ebx and
    ecx = KR1 are -1 when the byte is not a roster slot of the team (at or past the count), so the
    builder's own ``cmp reg,-1 / jle`` tests skip them instead of reading a vacated (NULL) slot; eax =
    the count (the builder overwrites eax before reading it).  Flags are kept."""

    a = _Asm(LINEUP_HELPER_VA)
    a.b("9c")                                  # pushfd
    a.b("3bd1")                                # cmp edx,ecx       ; PR
    a.j8("72", "pr_ok")
    a.b("83caff")                              # or edx,-1
    a.label("pr_ok")
    a.b("3bd9")                                # cmp ebx,ecx       ; KR2
    a.j8("72", "kr2_ok")
    a.b("83cbff")                              # or ebx,-1
    a.label("kr2_ok")
    a.b("91")                                  # xchg ecx,eax      ; ecx = team, eax = count
    a.b("0fbe89" + struct.pack("<I", TEAM_KR1).hex())  # movsx ecx, byte [ecx+0x195]  ; KR1
    a.b("3bc8")                                # cmp ecx,eax
    a.j8("72", "kr1_ok")
    a.b("83c9ff")                              # or ecx,-1
    a.label("kr1_ok")
    a.b("9d")                                  # popfd
    a.b("c3")                                  # ret
    return a.assemble()


def getter_bytes(*, previous: bool = False) -> bytes:
    """The getter site: the guarded getter (96 bytes) and the line-up builder's slot check (32 bytes)."""
    code = _getter_code(previous=previous)
    _require(GETTER_VA + len(code) <= LINEUP_HELPER_VA, "returner getter exceeds its assigned room")
    body = code.ljust(LINEUP_HELPER_VA - GETTER_VA, b"\xcc") + _lineup_helper_code()
    _require(len(body) <= GETTER_SIZE, f"returner getter site is {len(body)} bytes, over {GETTER_SIZE}")
    return body + b"\xcc" * (GETTER_SIZE - len(body))


def getter_bytes_v1() -> bytes:
    code = _getter_code(v1=True)
    return code + b"\xcc" * (GETTER_SIZE - len(code))


def lineup_hook_bytes() -> bytes:
    a = _Asm(LINEUP_HOOK_VA)
    a.call(LINEUP_HELPER_VA)                   # call the slot check (5 bytes)
    a.b("9090")                                # the displaced 7-byte movsx ends here
    return a.assemble()


def _exchange_code() -> bytes:
    """b780 st1 (Q34): FUN_000c3d70, the slot store of the weekly exchange sort (and of 0xC3DF0).
    thiscall-like: ecx = team, edx = player, [esp+4] = slot s; ret 4.  Retail stores the player and
    clears (-1) every specialist byte (+0x194 holder, +0x195/6 KR1/KR2, +0x197 K, +0x198 LS, +0x199 PR)
    that pointed at s, so the weekly sort, which swaps two players with two stores (store j = P_i, then
    store i = P_j), loses the long snapper, the holder and the kicker whenever their slot moves.
    Now the store keeps each byte on its player:
      * P is still in another slot r of the team (the first store of a swap): bytes == r -> s (P's roles
        follow him) and bytes == s -> r (the displaced player's roles follow him to r, where the second
        store puts him);
      * P is in no other slot but the displaced player still is (the second store of a swap): the bytes
        already follow both players; nothing changes;
      * neither is anywhere else (a real replacement): bytes == s -> -1, as retail;
      * P is already at s: nothing changes.
    ebx, esi, edi and ecx are kept; eax and edx are clobbered as retail."""

    a = _Asm(EXCHANGE_VA)
    a.b("53")                                  # push ebx
    a.b("56")                                  # push esi
    a.b("57")                                  # push edi
    a.b("8b442410")                            # mov eax,[esp+0x10]  ; s
    a.b("8b3c81")                              # mov edi,[ecx+eax*4] ; O, the player at s
    a.b("0fb6b1" + struct.pack("<I", TEAM_COUNT).hex())  # movzx esi, byte [ecx+0x11c]
    a.b("83cbff")                              # or ebx,-1           ; r: P's other slot
    a.b("6aff")                                # push -1             ; k: O's other slot
    a.label("scan")
    a.b("4e")                                  # dec esi
    a.j8("78", "scanned")                      # js scanned
    a.b("3bf0")                                # cmp esi,eax
    a.j8("74", "scan")                         # je scan            ; not s itself
    a.b("3914b1")                              # cmp [ecx+esi*4],edx
    a.j8("75", "not_p")
    a.b("8bde")                                # mov ebx,esi         ; r
    a.label("not_p")
    a.b("393cb1")                              # cmp [ecx+esi*4],edi
    a.j8("75", "scan")
    a.b("893424")                              # mov [esp],esi       ; k
    a.j8("eb", "scan")
    a.label("scanned")
    a.b("5e")                                  # pop esi             ; k
    a.b("891481")                              # mov [ecx+eax*4],edx ; the store
    a.b("3bd7")                                # cmp edx,edi
    a.j8("74", "out")                          # same player: nothing changes
    a.b("85db")                                # test ebx,ebx
    a.j8("79", "swap")                         # r >= 0: first store of a swap
    a.b("85f6")                                # test esi,esi
    a.j8("79", "out")                          # O still placed: second store of a swap
    a.b("b77f")                                # mov bh,0x7f         ; bl = 0xff: bytes == s -> -1, no second rule
    a.j8("eb", "remap")
    a.label("swap")
    a.b("8afb")                                # mov bh,bl           ; bytes == r -> s; bl = r: bytes == s -> r
    a.label("remap")
    a.b("8db1" + struct.pack("<I", 0x194).hex())  # lea esi,[ecx+0x194]
    a.b("ba06000000")                          # mov edx,6
    a.label("byte")
    a.b("3806")                                # cmp [esi],al        ; == s
    a.j8("75", "not_s")
    a.b("881e")                                # mov [esi],bl
    a.j8("eb", "next_byte")
    a.label("not_s")
    a.b("383e")                                # cmp [esi],bh        ; == r
    a.j8("75", "next_byte")
    a.b("8806")                                # mov [esi],al
    a.label("next_byte")
    a.b("46")                                  # inc esi
    a.b("4a")                                  # dec edx
    a.j8("75", "byte")
    a.label("out")
    a.b("5f")                                  # pop edi
    a.b("5e")                                  # pop esi
    a.b("5b")                                  # pop ebx
    a.b("c20400")                              # ret 4
    return a.assemble()


def _all_star_code(va: int) -> bytes:
    """b780 st1 (Q32, HUNT6's finding): the weekly auto-depth's loop head (0x2BDD1B) calls this in place of the
    user-club test 0x13EC30, ecx = the team.  An all-star team (+0x128 kind 1: the AFC/NFC Pro Bowl teams the
    postseason puts in league slots 32/33, NFL, the all-time squads) drops the return address and goes to the
    loop tail 0x2BDFD0 (next team: no sort, no returner pass), so a Pro Bowler keeps his own club's depth rows;
    every other team takes the user-club test as before.  Depth locks revision 5 carries the same check in its
    own block for builds without the returner fix."""

    a = _Asm(va)
    a.b("83b9" + struct.pack("<I", 0x128).hex() + "01")  # cmp dword [ecx+0x128],1
    a.j8("74", "all_star")
    a.jmp_abs(FN_USER_CLUB)                    # the user-club test, unchanged (returns to 0x2BDD20)
    a.label("all_star")
    a.b("58")                                  # pop eax             ; drop the loop head's return address
    a.jmp_abs(WEEKLY_LOOP_TAIL_VA)             # mov esi,[esp+0x2c]; inc esi; ... next team
    return a.assemble()


def exchange_bytes() -> bytes:
    store = _exchange_code()
    _require(EXCHANGE_VA + len(store) <= ALL_STAR_SKIP_VA, f"exchange store is {len(store)} bytes")
    body = store + b"\xcc" * (ALL_STAR_SKIP_VA - EXCHANGE_VA - len(store)) + _all_star_code(ALL_STAR_SKIP_VA)
    _require(len(body) <= EXCHANGE_SIZE, f"exchange site is {len(body)} bytes, over {EXCHANGE_SIZE}")
    return body + b"\xcc" * (EXCHANGE_SIZE - len(body))


def all_star_call_bytes() -> bytes:
    a = _Asm(ALL_STAR_CALL_VA)
    a.call(ALL_STAR_SKIP_VA)
    return a.assemble()


def _header_size(payload: bytes) -> int:
    return struct.unpack_from("<I", payload, 0x108)[0]


def _offset(payload: bytes, va: int) -> int:
    if IMAGE_BASE <= va < IMAGE_BASE + _header_size(payload):
        return va - IMAGE_BASE
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise ReturnerFixError(f"VA 0x{va:x} is in no section")


def _sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    _require(len(RETAIL_SITE) == SITE_SIZE, "retail transcript must cover the whole returner loop")
    _require(len(RETAIL_GETTER) == GETTER_SIZE, "retail transcript must cover the whole returner getter")
    _require(len(RETAIL_EXCHANGE) == EXCHANGE_SIZE, "retail transcript must cover the whole exchange store")
    return [("returner_loop", _offset(payload, SITE_VA), RETAIL_SITE, site_bytes()),
            ("returner_chart", _offset(payload, ROW_LABEL_VA), RETAIL_ROW_LABEL, row_label_bytes()),
            ("returner_summary", _offset(payload, SUMMARY_TAIL_VA), RETAIL_SUMMARY_TAIL, summary_tail_bytes()),
            ("returner_lookup", _offset(payload, FN_NTH_RETURNER), RETAIL_NTH, lookup_bytes()),
            ("returner_getter", _offset(payload, GETTER_VA), RETAIL_GETTER, getter_bytes()),
            ("lineup_slot_check", _offset(payload, LINEUP_HOOK_VA), RETAIL_LINEUP_HOOK, lineup_hook_bytes()),
            ("exchange_store", _offset(payload, EXCHANGE_VA), RETAIL_EXCHANGE, exchange_bytes()),
            ("all_star_skip", _offset(payload, ALL_STAR_CALL_VA), RETAIL_ALL_STAR_CALL, all_star_call_bytes())]


# Complete prior chart and list routines from the standard beta 81 build (6bb6862e0) and the
# following draw/edit separation (b02446e8c). Each old routine must match before it can upgrade.
_PREVIOUS_CHART = (_row_label_code() + bytes.fromhex(
    "817c2448102d2400721d85c074198b54240485d27406f64227707506f64027707405e952000000c3"
)).ljust(ROW_LABEL_SIZE, b"\xcc")
_PREVIOUS_DETAIL_CHART = _row_label_code() + bytes.fromhex(
    "0fb75424496681ea2d2483fa0b731a85c074168b54240485d27406f64227707506f64027707402eb50c3"
)
_PREVIOUS_LOOKUP = (_nth_code() + bytes.fromhex(
    "8d792029f729f781ec3403000089e289d96a006a00e89756eaff0fb6143c81c43403000031c03a931c01000073038b0493c3"
)).ljust(NTH_SIZE, b"\xcc")

# Earlier installs that upgrade in place: the first b780 st1 getter; depth locks revision 5's own all-star call
# (an image where depth locks came first): the returner fix owns the loop head's call and points it at its own
# skip, so either order of the two owners ends in the same bytes.
PREVIOUS = {"returner_chart": (_PREVIOUS_CHART, _PREVIOUS_DETAIL_CHART), "returner_lookup": (_PREVIOUS_LOOKUP,),
            "returner_getter": (getter_bytes_v1(), getter_bytes(previous=True)), "all_star_skip": (DEPTH_LOCKS_ALL_STAR_CALL,),
            "returner_loop": (site_bytes(v2=True),)}


def _site_states(payload: bytes) -> dict[str, str]:
    states = {}
    for label, off, before, after in _sites(payload):
        got = payload[off: off + len(before)]
        states[label] = ("retail" if got == before else "applied" if got == after else
                         "previous" if got in PREVIOUS.get(label, ()) else "foreign")
    return states


def status(payload: bytes) -> str:
    """retail | applied | legacy (an earlier install: the loop of beta-79 and older builds, upgraded in place) |
    foreign.  The all-star call may be depth locks revision 5's own (depth locks came first); apply points it at
    the returner fix's skip."""
    try:
        states = _site_states(payload)
    except (ReturnerFixError, ValueError, struct.error):
        return "foreign"
    # The current chart calls a helper in the summary selector. They ship as a pair.
    if (states["returner_chart"] == "applied") != (states["returner_summary"] == "applied"):
        return "foreign"
    others = {k: v for k, v in states.items() if k != "all_star_skip"}
    call = states["all_star_skip"]           # "previous" = depth locks revision 5's own call, taken over on apply
    if set(others.values()) == {"retail"} and call in ("retail", "previous"):
        return "retail"
    if set(others.values()) == {"applied"} and call == "applied":
        return "applied"
    if others["returner_loop"] in ("applied", "previous") and "foreign" not in others.values() and call != "foreign":
        return "legacy"                      # beta-79 and older (loop only), the first st1 getter, depth locks' call
    return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload)
    _require(state in ("retail", "legacy"), f"returner sites are {state}, not retail")
    states = _site_states(payload)
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    for label, off, before, after in _sites(payload):
        if states[label] == "applied":
            continue                            # an earlier install keeps what is already right
        buf[off: off + len(after)] = after
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
                     "code_bytes": len(site_bytes()) - site_bytes().count(b"\xcc"),
                     "getter_code_bytes": len(_getter_code()), "lineup_check_bytes": len(_lineup_helper_code()),
                     "exchange_code_bytes": len(_exchange_code()),
                     **({"upgraded_from": "legacy"} if state == "legacy" else {}),
                     "kr_eligible": list(KR_ELIGIBLE), "pr_eligible": list(PR_ELIGIBLE)}


__all__ = ["ReturnerFixError", "SITE_VA", "SITE_SIZE", "RETAIL_SITE", "GETTER_VA", "GETTER_SIZE", "RETAIL_GETTER",
           "LINEUP_HOOK_VA", "EXCHANGE_VA", "EXCHANGE_SIZE", "ALL_STAR_CALL_VA", "ALL_STAR_SKIP_VA",
           "KR_ELIGIBLE", "PR_ELIGIBLE", "all_star_call_bytes", "apply", "exchange_bytes", "getter_bytes",
           "lineup_hook_bytes", "mask_bytes", "site_bytes", "status"]

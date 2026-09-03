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
  whole roster is scanned; the game's own category-10 score is the ranking key.

Pattern-checked against the retail bytes, ``.text`` digest recomputed.  Unverified at runtime.
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


class ReturnerFixError(ValueError):
    """The returner patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReturnerFixError(message)


def mask_bytes() -> bytes:
    kr = bytes(1 if p in KR_ELIGIBLE else 0 for p in POSITIONS)
    pr = bytes(1 if p in PR_ELIGIBLE else 0 for p in POSITIONS)
    return kr + pr


def _code(masks_va: int) -> bytes:
    """The replacement loop.  edi = team; [esp+0x10..0x28] are the routine's own scratch dwords:
    0x10 best KR score, 0x14 its index, 0x18 second KR score, 0x1c its index, 0x20 best PR score,
    0x24 its index, 0x28 pass number.  [esp+0x2c] (the team counter) is left alone.  A score of
    0.0 means "nobody yet"; indices default to 0 (the retail default) but are only used with a score."""

    a = _Asm(SITE_VA)
    imm = lambda va: struct.pack("<I", va).hex()  # noqa: E731
    kr_mask = masks_va
    pr_mask = masks_va + len(POSITIONS)
    a.b("31c0")                                # xor eax,eax
    a.b("b907000000")                          # mov ecx,7
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
    a.b("837c242800")                          # cmp dword [esp+0x28],0
    a.j8("75", "scored")                       # jne scored          ; pass 1: starters allowed
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
    a.b("ba01000000")                          # mov edx,1
    a.b("8bce")                                # mov ecx,esi
    a.call(FN_CATEGORY)                        # st0 = score (ebx/esi/edi/ebp preserved)
    a.b("f7c501000000")                        # test ebp,1
    a.j8("74", "pr_part")                      # jz pr_part
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
    a.b("f7c502000000")                        # test ebp,2
    a.j8("74", "drop")                         # jz drop
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
    a.b("837c242800")                          # cmp dword [esp+0x28],0
    a.j8("75", "finalize")                     # jne finalize
    a.b("ff442428")                            # inc dword [esp+0x28]
    a.b("837c241000")                          # cmp dword [esp+0x10],0
    a.j32("0f84", "pass_loop")                 # je pass_loop        ; no kick returner: allow starters
    a.b("837c242000")                          # cmp dword [esp+0x20],0
    a.j32("0f84", "pass_loop")                 # je pass_loop        ; no punt returner
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


def site_bytes() -> bytes:
    """Code, then the two 17-byte eligibility masks, int3-padded to the retail loop's size."""

    probe = _code(SITE_VA)                     # size pass: the mask address depends on the code size
    masks_va = SITE_VA + len(probe)
    code = _code(masks_va)
    _require(len(code) == len(probe), "assembler size drift")
    body = code + mask_bytes()
    _require(len(body) <= SITE_SIZE, f"returner patch is {len(body)} bytes, over {SITE_SIZE}")
    return body + b"\xcc" * (SITE_SIZE - len(body))


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
    return [("returner_loop", _offset(payload, SITE_VA), RETAIL_SITE, site_bytes())]


def status(payload: bytes) -> str:
    try:
        sites = _sites(payload)
    except (ReturnerFixError, ValueError, struct.error):
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
    _require(state == "retail", f"returner sites are {state}, not retail")
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    edits = []
    for label, off, before, after in _sites(payload):
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
                     "kr_eligible": list(KR_ELIGIBLE), "pr_eligible": list(PR_ELIGIBLE)}


__all__ = ["ReturnerFixError", "SITE_VA", "SITE_SIZE", "RETAIL_SITE", "KR_ELIGIBLE", "PR_ELIGIBLE",
           "apply", "mask_bytes", "site_bytes", "status"]

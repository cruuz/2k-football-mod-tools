"""Kickoff return blocking: one blocker per coverage player, and no blocker left waiting (USA Xbox).

EXPERIMENTAL / UNWITNESSED. Noah's recording of 2026-09-23 [v2 5:33-5:38]: "Nobody moves until the ball is caught...
They could block better."

The dynamic kickoff (nfl2k5_dynamic_kickoff) chooses a released return blocker's target in its ``block_target`` rule,
the hook on the native target selector FUN_002FAFF0 (ECX blocker, EDX origin, seven stack operands, ST0 threshold).
Its loop keeps the best lane score (4 dx^2 + dz^2) among coverage players (slots 1..10) who are in front of the
blocker and approaching him. Measured in the native return replay (tests/mod_editor/test_nfl2k5_kickoff_v5.py,
``return_replay``; saved in docs/nfl2k5_kickoff_v5_receipts.json):
* blockers choose on their own, so two of them can take the same man (frame 1: slots 14 and 18 both take coverage
  2, slots 19 and 20 both take coverage 1);
* once no coverage player is both in front and approaching, the rule returns no target and ``block_tick`` parks the
  blocker at zero throttle. Four of nine setup blockers wait from frame 17 to the end of the return (701-731 waiting
  ticks per return) and never touch anyone.

This rule keeps the same entry checks, stack contract and result writes, and changes the choice only:
1. a coverage player already targeted by another receiving player's native drive-block task (task callback
   0x23CE70, target at task+0x40) is skipped: one blocker per man;
2. if nobody qualifies, a second pass drops the approaching test (in front only), and a third drops the in-front
   test, so a free blocker always takes the nearest unclaimed man in his lane before he would wait.
Outside a released normal kickoff return blocker (the dynamic kickoff's own ``block_scope``) it replays the retail
selector exactly as the dynamic kickoff does.

The code lives in the 25th Anniversary gate's allocation (nfl2k5_anniversary_kickoff), which already owns a
trampoline in front of the selector hook: outside game mode 8 that trampoline enters this rule instead of the cave's
``block_target``; in mode 8 the retail selector runs as before. The word just before the entry keeps the cave label
the trampoline replaced, so the kickoff's recognizers still read the site as their own hook.

It is a Build option (``kickoff_return_blocking``, off in every preset): gameplay feel is Noah's call, so the rule
goes to him as a test item and a build without the option carries none of this code.
"""
from __future__ import annotations

import struct

UI_LABEL = "Return blockers claim distinct men after the catch (test)"
HELP_TEXT = ("EXPERIMENTAL / UNWITNESSED. A feel test for Noah, off in every preset. Retail: without this option "
             "the new (2026) kickoff lets every return blocker pick his own man once the ball touches, so two can take "
             "the same coverage player and a blocker with nobody in front of him stands still for the rest of the "
             "return. Patch: after the ball first touches, each return blocker takes a coverage player no teammate is "
             "already blocking, and a free blocker takes the nearest unclaimed man instead of standing still. Nothing "
             "changes before the catch: the setup blockers still hold until the ball touches. The 25th Anniversary "
             "moments keep the retail kickoff. Needs the dynamic kickoff on a disc image.")

SELECTOR_VA = 0x2FAFF0                    # FUN_002FAFF0, the native drive-block target selector
SELECTOR_PROLOGUE = bytes.fromhex("558bec83e4f0")
BLOCK_TASK_CALLBACK = 0x23CE70            # [task+0] of a native drive-block task (the block tick)
STRONG_SCORE = 0x4E696C                   # the float the dynamic kickoff returns in ST0 ("strong primary score")
SCOPE_DELTA = -54                         # block_scope - block_target in the dynamic kickoff's instruction stream
FLAGS_OPERAND_DELTA = 78 + 2              # the FLAGS imm32 of `test byte [FLAGS], 0x10` in block_target's loop
MAX_PASS = 2                              # 0 strict (front + approaching), 1 front only, 2 anywhere
ENTRY = "e1_block_target"
CAVE_WORD = "e1_cave_block_target"


def _imm(value):
    return struct.pack("<I", value & 0xFFFFFFFF).hex()


def emit(a, *, cave_target, flags, max_pass=MAX_PASS):
    """Append the rule to the gate's assembler ``a``: a 4-byte word (the cave label it replaces), then ENTRY.

    ``cave_target`` is the dynamic kickoff's block_target label (legacy cave or relocated copy); its block_scope is
    SCOPE_DELTA bytes before it. ``flags`` is the kickoff state byte the cave tests for the kicking direction."""
    if max_pass not in (0, 1, 2):
        raise ValueError("max_pass is 0, 1 or 2")
    a.label(CAVE_WORD)
    a.items.append(struct.pack("<I", cave_target))
    a.label(ENTRY)
    a.b("60")                                                    # pushad (the cave's save(False))
    a.call(cave_target + SCOPE_DELTA)                            # the dynamic kickoff's block_scope
    a.b("85c0"); a.j32("0f84", "e1_go")
    a.b("837c242802"); a.j32("0f85", "e1_go")                    # native drive mode only
    a.b("8b41388b00")                                            # kicking team, from the verified receiving player
    a.b("8b7118" + "ff7004" + "680000807f" + "31db" + "6a00")    # self transform; [esp+8] list, [esp+4] +inf, [esp] pass
    a.label("e1_pass")
    a.b("8b7c2408" + "6a165d")                                   # first coverage candidate; at most 22
    a.label("e1_loop")
    a.b("85ff"); a.j32("0f84", "e1_end")
    a.b("837f4800"); a.j32("0f85", "e1_next")
    a.b("8a472efec83c09"); a.j32("0f87", "e1_next")               # coverage slots 1..10
    a.j32("e8", "e1_claimed"); a.b("85c0"); a.j32("0f85", "e1_next")
    a.b("8b5718d94238d86638")                                    # candidate z - self z
    a.b("f605" + _imm(flags) + "10" + "7502" + "d9e0")           # in the receiving direction
    a.b("d9e4dfe0ddd89e"); a.j32("0f83", "e1_front")
    a.b("833c2402"); a.j32("0f82", "e1_next")                    # behind: third pass only
    a.label("e1_front")
    a.b("0f2842300f5c46300f28c80f594a400f12d10f57dbf30f58ca0f2fcb")
    a.j32("0f8a", "e1_next"); a.j32("0f86", "e1_score")          # approaching (dot <= 0)
    a.b("833c2401"); a.j32("0f82", "e1_next")                    # not approaching: second pass on
    a.label("e1_score")
    a.b("f30f58c00f59c00f12c8f30f58c10f2f442404")               # 4 dx^2 + dz^2 against the best
    a.j32("0f83", "e1_next"); a.j32("0f8a", "e1_next")
    a.b("f30f1144240489fb")
    a.label("e1_next")
    a.b("8b7f344d"); a.j32("0f85", "e1_loop")
    a.label("e1_end")
    a.b("85db"); a.j32("0f85", "e1_done")
    a.b("ff0424" + "833c24" + f"{max_pass + 1:02x}"); a.j32("0f82", "e1_pass")
    a.label("e1_done")
    a.b("83c40c")
    a.b("8b41208b8010030000895840")                              # the task keeps the choice (refresh reads it)
    a.b("8d742430fcad8918adc7000000803f31d2ad8910ad8910")          # out: target, 1.0, 0, 0
    a.b("61" + "d905" + _imm(STRONG_SCORE) + "c21c00")
    a.label("e1_go")                                             # outside the rule: the retail selector
    a.b("61" + SELECTOR_PROLOGUE.hex())
    a.jmp_abs(SELECTOR_VA + len(SELECTOR_PROLOGUE))
    # EAX = 1 when another receiving player's drive-block task targets EDI (ECX = this blocker).
    a.label("e1_claimed")
    a.b("5253" + "8b513885d2"); a.j8("74", "e1_c_none")
    a.b("8b5204" + "6a165b")
    a.label("e1_c_loop")
    a.b("85d2"); a.j8("74", "e1_c_none")
    a.b("39ca"); a.j8("74", "e1_c_next")
    a.b("8b422085c0"); a.j8("74", "e1_c_next")
    a.b("8b801003000085c0"); a.j8("74", "e1_c_next")
    a.b("8138" + _imm(BLOCK_TASK_CALLBACK)); a.j8("75", "e1_c_next")
    a.b("397840"); a.j8("74", "e1_c_yes")
    a.label("e1_c_next")
    a.b("8b52344b"); a.j8("75", "e1_c_loop")
    a.label("e1_c_none")
    a.b("31c05b5ac3")
    a.label("e1_c_yes")
    a.b("31c0405b5ac3")


def cave_parameters(image, cave_target):
    """(scope VA, FLAGS VA) of an installed dynamic kickoff whose block_target label is ``cave_target``."""
    flags = struct.unpack("<I", image.read(cave_target + FLAGS_OPERAND_DELTA, 4))[0]
    return cave_target + SCOPE_DELTA, flags

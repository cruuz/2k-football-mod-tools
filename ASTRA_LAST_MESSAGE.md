b75-a2: ability-based charged-ability cap implemented; off by default and EXPERIMENTAL.
Delivery: one commit in .scratch/b75-a2.bundle from beta-74 base 56b537342; no push.
Core module: mod_editor/core/apf2k8_charge_abilities.py; supports pinned BASE and TU 1.1.
Charge routine: BASE 848C51C0; TU 848C5FF8, both .text.
Gold comparison: BASE 848C5294; TU 848C60CC; packed tier word mask 00000600 equals 00000200.
Hook/resume: BASE 848C5288/848C52AC; TU 848C60C0/848C60E4.
QB no-arm gate preserved at BASE 848C5214 and TU 848C604C.
Authored leaf: 76 bytes at 84D0D100; reserved zero range ends 84D0D180 in the XEX code page.
Charged masks: roster +24=0F800000, +28=000001FC, +2C=0E000000; 15 charged abilities.
Retail Gold+ability / Silver+ability / Gold-without-ability decision table: 2 / 1 / 2.
Patched decision table: 2 / 2 / 1; all four tiers and every packed bit tested.
QB qualification: retail passing fixture caps armed Gold at 1; patched arms reach 2, no-arm gate stays 0.
CPU bypass: controller -1 skips unless the selected-automation helper is true; caller remains retail.
Proof: both complete pinned images execute bounded charge state transitions; full-width authored-leaf ABI oracle.
Exact synthetic-XEX and real-image apply/revert pass; partial, foreign and occupied-cave inputs are refused.
Build flag, Tools checkbox, patch install/remove, receipts, capability, allowlist and alpha.98 beta-75 changelog added.
Final isolated result: 34 files, 380 passed, 1 skipped, 834 subtests passed.
APF product contract and registry pass; repin applies zero changes; H7A remains 0755; 2K5 code unchanged.
Integration follow-up: untouched 2K5 count assertions expect 176 shared rows; new registry has 177.
Report and Urianus player/ability/halo/move retest: docs/research/apf_b75_charge_abilities.md; gameplay UNWITNESSED.

b75-a1 is a research handoff. The reported cause is still unproved, and no
gameplay patch is proposed for release.

The [research report](docs/research/apf_b75_dl_instructions.md) records the
retail 4-3 Base decode, BASE/TU addresses, native proofs, writer audit and
the remaining capture steps. A controlled production export changed
O-ManBlock while leaving MASTER and all six compared defensive book types
byte-identical. This was not the beta 73/74 folder used in the clips; that
folder was not found locally and the path clarification remains unanswered.

The native CPU lane resolver preserves Base at the supplied design position.
A constructed displacement produces Gap Left/Right lane vectors while Base's
assignment and modes remain intact. The clip's displacement trigger and live
call tuple were not captured, so this is a mechanism to test, not the proven
root cause. The main automatic front-shift callers bypass a human team in
the tested state.

Validation: 61 passed, 2 subtests passed across the new DL tests, existing
route/alignment writer tests and production-finalizer tests. Four recorded
native runs cover BASE and TU, with the tested shipped options off/on.
No retail binaries or media are committed; tools/apf_h7a_optimal remains 0755.
Job a2's completed bundle was available, but its commit had not landed in
this checkout's origin/main. This independent research can be applied after a2.

Shared Git metadata rejected the commit as read-only. The authorized fallback
is `.scratch/b75-a1.git`, with import bundle `.scratch/b75-a1.bundle`.
The final response and `.scratch/b75-a1-commit.json` identify its commit.

20-line summary:
01. Job b75-a1 investigated CPU defensive linemen appearing to ignore Base.
02. The reported root cause remains unproved.
03. No production gameplay behavior was changed.
04. The visible retail counterpart is 4-3 Base, MASTER play 277.
05. Base owns front slots 0 through 3 through descriptor bit 0x800.
06. Its rush lanes are 13, 3, 9, 5 and its modes are 1, 1, 0, 1.
07. Gap Left and Gap Right have distinct lane and mode values.
08. There is no proved single Base/Gap technique enum in PLAY or DRCT.
09. The native assignment selector preserves Base with 2 Hard or 2 Man.
10. Each native configuration checks 1,064 front ownership choices.
11. BASE and TU readers preserve the called operands and their mirrors.
12. The CPU lane resolver adjusts lanes relative to player displacement.
13. Constructed displaced Base inputs reproduce the Gap lane vectors.
14. That fixture does not establish the trigger in the tester's clips.
15. A separate automatic shift table was located and sampled natively.
16. Its three tested main entry points bypass human-controlled teams.
17. The tested runtime options preserve these native DL results.
18. Controlled O-ManBlock export preserves MASTER and six defensive books.
19. Validation finished with 61 passed and 2 profile subtests passed.
20. Closure needs the tester folder and one failing call's runtime state.
ASTRA_DONE

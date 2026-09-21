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
ASTRA_DONE

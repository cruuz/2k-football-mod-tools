# b75-a2 validation evidence

Final isolated result: 34 files, 380 passed, 1 skipped, 834 subtests passed.

`decision-proof.json` records the three requested cases, per-update charge
states, peak instruction counts, adapter words and final patch receipts for
both owned profiles. It contains no extracted image or roster payload.
`native-initial.log` records the complete native ability/QB/CPU witness run;
the isolated native log records the subsequent final-code pass (5 passed).
The synthetic/transport/build suite adds 5 passes and the Qt option adds 1.

`isolated/results.json` records one pytest process per selected APF test file.
`test_files.txt` is the selection: every `test_apf_*` file mentioning the APF
build service, a build call or fourth-down, plus the new tests and launcher
coverage. The installer contract runs separately in `installer-final.log` (16 passed).
Use `QT_QPA_PLATFORM=offscreen python3 -m pytest -q -p no:cacheprovider FILE`
for each listed file.

The first combined invocation hit a Qt segmentation fault in the existing
field-material panel after several test classes had shared one QApplication.
`regression.log` preserves that failure. The affected file passes in its own
process. The final capability/parity logs validate the canonical registry
and the new option alongside the existing fourth-down option.

`registry-final.log` validates the registry and all local evidence paths.
`product-contract.log` runs `_check_static_product_contract` from the APF
release checker against its 110 product modules, with 74 APF capabilities.
This is the static contract check, not a full staged Windows release audit.
`repin.log` records zero necessary pin updates. The H7A encoder remains 0755.
All 17 address/context rows in the research report were compared against
the BASE and TU decoded images and match, including the TU call deltas.

The research report has the address pins, unchanged QB gate, CPU bypass,
passing-mode QB qualification and exact Urianus retest steps:
`docs/research/apf_b75_charge_abilities.md`.

Delivery uses `.scratch/b75-a2.bundle` with one commit based on
`56b537342331a2c9ee2f2208c2efbe31ae32208c`, because writes to the shared Git
metadata were refused. No push or retail file modification is performed.
The shared registry now has 177 entries; the untouched 2K5 count assertions
still expect 176 and need coordination before a combined release.

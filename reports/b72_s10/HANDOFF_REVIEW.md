# Handoff fact-check dispositions

The installed Jev fact-check recipe evaluated all 20 summary lines using the captured job evidence. The final run returned four NEEDS_READ flags, no witness-claim flags and no uncovered claims. Its flagged exit is retained. The raw call and exact request are in `handoff_call.json` and `handoff_request.json`; `handoff_evidence.txt` freezes the evidence so replay does not silently use later report updates. The earlier run preceded the final auxiliary results and remains under `handoff_initial_*`, including its charge.

| Flagged claim | Review |
|---|---|
| Six sheets cover three matchups in both aspects | Supported by the six files under `sheets/` and the explicit source labels visible in them. FIDELITY.md says all six include the four real disc r before captures. Missing WAS-LAC broadcast and 4:3 game witnesses are disclosed, not invented. |
| Auxiliary gates have two timeouts and two inherited manifest errors | Supported directly by aux_checks.json: both all-owner suites return 124 at 420.03 seconds; the oracle log records 29 tests and two errors naming the stale exact.py fingerprint. Both exact.py and the protected manifest match the base bytes. VALIDATION.md explicitly records these failures and the separate packaging pass. |
| Exact disc q/r options and required manifest regeneration | Supported by TEST_DISC.md, the complete option dictionary, the two source receipt hashes and their equal plans, and owner_scan.json's inherited source-fingerprint warning. WIRING.md gives the integration command. |
| No emulator/release step, no new game outcome or 1:1 claim | Supported by the job's offline harness/closure commands and the explicit FIDELITY.md limitations. Temporary closure staging is an inventory/runtime check, not a publish or release action. The final text explicitly declines a witnessed-game or 1:1 claim. |

All four flags were read against the actual artifacts. No claim was promoted because a model approved it, and no unfavourable model answer was discarded. Final usage, including both fact-check calls, is aggregated in `JEV_USAGE.json`.

# b72-s10 Jev review

Jev receives text descriptors and measured feature tables, never pixels. Every inference request and raw response is retained in `jev_calls.json`, `gate_initial_call.json`, `gate_final_call.json`, and the handoff call receipt when present. `JEV_USAGE.json` aggregates current usage: $0.01117210, 28 calls, against the $1.00 cap. Requests are bounded before dispatch using a conservative byte-count reserve. The initial configuration-only status probe does not perform inference.

Both phrasings of each ranking ask for the largest measured visible-area gap. The initial raw-RGB order was wing, housing/rim, down capsule, logo, pill, score. Feature occupancy subsequently replaced raw RGB because palette shade differences inflated area without measuring proportion. Jev saw the revised table; measurements retained authority throughout. The final ranking is logo, wing colour, housing/rim, down capsule, pill, score. Both final next-gap calls select logo, with confidence 0.86 and 0.93, matching the measured 1,931.75-pixel residual.

Both recognition phrasings use the same 0-to-4 concrete rubric. Raw-RGB baseline scores were 1.14 and 1.13. The revised occupancy baseline scores were 1.73 and 1.62. An intermediate candidate scored 1.23 and 1.47; these unfavourable answers remain logged. The final corrected SD candidate scores 1.79 and 1.86, with confidence 0.44 and 0.50. These cautious results do not certify that the bar reads as ESPN or establish a quantitative gain across differently worded contexts. They cannot overrule area measurements or a future player verdict. All six measured feature residuals remain nonzero.

The installed diff-gate recipe was run via request capture, actual MCP batch execution and exact-input replay. Its final source review covers base `97d2bf9b2` through implementation commit `73273e596a`. Later changes are report evidence only. Eleven windows, zero provider errors and zero deterministic findings; two model flags remain documented in `own_diff_gate.md`:

| Flag | Probability | Disposition |
|---|---:|---|
| PINNED_VALUE, logo-fit test | 0.91 | Reviewed. The old expected ratio used the 200x107 mapping. The test now derives the actual 230x110 quad aspect and expects the deliberately cropped KC/DEN silhouettes. The 0.12 tolerance and wide-silhouette floor remain. This is a layout contract, not proof of broadcast fidelity. |
| PINNED_VALUE, layout cell coordinates | 0.63 | Reviewed. Coordinates belong to deterministic atlas repacking. Bounds, native sampling, SD footprint, append budgets and regeneration pass; no native table/resource format changes. |

The recipe separately dismisses four hash warnings because every digest matches the HEAD bytes: provider pin, release catalogue hash, PNG identity and replication pins. No inventory-count assertion was changed. The gate returned its flagged status; this report does not present it as an unconditional model pass. The independent release closures, measured art checks and source audit support the reviewed dispositions.

The handoff fact-check uses the installed recipe over the final summary and these job reports. Its receipt and any reviewed flags are recorded separately in `handoff_factcheck.md`. No model output is represented as an in-game witness.

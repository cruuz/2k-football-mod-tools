# Beta 71 S4 handoff

Painted v4 is implemented on the private branch `astra/b71-s4-painted-bar`.

- Appended payload: **410,624 bytes**, 2,944 below v3. Owner: **1,380 / 1,408 code bytes**, 128 RW bytes. Scene: unchanged 4,800-byte span.
- All measured regions, native text boxes and raster ink boxes are within **1 HUD pixel** in 4:3 and widescreen. DEN at KC, NO at DEN, individual retail events and multi-digit scores are rendered.
- **Exact ESPN pixel matching remains unachieved.** Mean region RGB MAE is **36.479 / 35.514**; both `exact_match` results are false. The comparison images are the review artifacts.
- All 28 standalone programs and strict validation passed: 282 unittest cases, including 15 documented skips. Both detached XBE gates passed (119 memory-write and 131 cave-reference cases), as did the 29-case oracle and the full 506-case owner-pair suite.
- Compiler pins, provider seals, cave projection, registry evidence and the anonymous RC96 bullet are updated.

See [ASTRA_REPORT.md](ASTRA_REPORT.md), [4:3 comparison](reports/b71_s4/compare_43.png), [wide comparison](reports/b71_s4/compare_wide.png), and [state contact sheet](reports/b71_s4/states_contact_sheet.png).

Bundle: `.scratch/astra-b71-s4.bundle`; prerequisite: `464423f0889581182f4a6de53971ecab23be19d5` (completed S3 HEAD). `.scratch/b71-s4-delivery.json` records the final commit, bundle size and SHA-256 after verification.

`reports/b71_s4/build_testdisc71.py` is prepared with the requested `NFL 2K5 MOD TEST 2026-09-15j (painted bar + colour + widescreen)` name and the same options. It was not run, including plan-only mode. No disc, patch archive, push or emulator launch. Played-game behavior and GPU appearance remain UNWITNESSED.

ASTRA_DONE

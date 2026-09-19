b72-t1 implements byte-identical equipment fitting and incremental project checks on base `088e3f41`. Phase A is commit `bd66e362`; Phase B is the tip of the `b72-t1` branch in `b72-t1.bundle`. The shared worktree's Git metadata is read-only here, so the two commits were created in separate temporary metadata. The bundle is the landing artifact; no release was published.

The primary path uses Python and the already shipped NumPy 1.26.4. Measurements below use this same AMD Ryzen 9 3950X host, 32 logical CPUs, Linux and Python 3.12.3. OFF disables the reviewed helper. ON allows the verified Linux helper after chmod 0755. No Windows hardware timing is claimed. These are single-run timings, with raw records retained. Open invokes no encoder, so its one measurement per version is repeated in both helper columns. Build baselines were replayed from a complete rc97 tree, so spawned workers and file-loaded adapters also use rc97. The final Build runs disable persistent stage caches in both the parent and spawned workers; in-memory caches start empty for each worker setting.

| Operation, seconds | Before OFF | After OFF | Before ON | After ON |
| --- | ---: | ---: | ---: | ---: |
| 64x64 photographic shoe import | 11.697 | 0.767 | 13.123 | 0.644 |
| Retail photographic sock + mud | 23.832 | 1.042 | 24.293 | 0.947 |
| Retail number sheet sock + mud, needs refit | 10.018 | 1.135 | 8.396 | 0.953 |
| Retail 256x256 photographic shoe, needs refit | 235.893 | 4.428 | 226.454 | 3.624 |
| 32-group fit pass, 1 worker | 34.131 | 2.450 | 36.204 | 1.861 |
| 32-group fit pass, 8 workers | 8.366 | 2.601 | 8.372 | 2.239 |
| Serial reuse pass after 1-worker fit | 10.141 | 0.067 | 11.885 | 0.067 |
| Refit one item in a 24-item project | 30.070 | 1.783 | 29.647 | 1.608 |
| Open 600 replacements, no encoding | 0.743 | 0.773 | 0.743 | 0.773 |

The one-worker fit pass is 13.93 times faster than its matching baseline. Both worker settings assert **zero serial group compilations** using Build's own adapter and retain that counter in the JSON. The 32-group fixture has 64 replacements and 15 distinct spans. This measures equipment preparation, not a complete ISO copy or an in-game result. At this small size the old serial pass also compiled zero groups; its catalog and PNG work still cost seconds. A separate forced-eviction test verifies that the new serial pass reuses a spilled result, and the 2,681-entry test proves there is no 128-group or 32-artwork cap.

The oversized retail shoe has a proved lower bound of 55,802 bytes against a 55,280-byte span. It reaches a clear needs-refit result and names a separately encoded 64x64, two-colour suggestion at 55,270 bytes. It never quantizes a full-size rung in this case. The existing quality choice remains explicit. Normal/mud and unresolved siblings retain their separate fit status.

The photographic 256x256 synthetic sock fits in 10.227 seconds with the helper OFF and 8.913 seconds ON, compared with the dossier's 184.05/180.34 seconds. Repeat imports remain under 0.02 seconds in these fixtures. These larger photographic fits remain the slowest tested imports because they still create and verify real mip chains, compressed streams and detailed quality receipts. Eight-worker startup and result transfer remain visible: the final eight-worker result is above the dossier's 1.5-second stretch target. The required one-worker improvement and per-item targets pass.

The version-map probe gives:

| Version | Helper OFF | Helper ON |
| --- | ---: | ---: |
| beta-68 / rc93 | 7.945 | 8.104 |
| beta-69 / rc94 | 7.550 | 2.035 |
| beta-70 / rc95 | 16.296 | 15.771 |
| beta-71 / rc96 | 16.540 | 16.001 |
| beta-71.1 / rc97 | 23.879 | 23.335 |
| beta-72 / rc98 candidate | 1.214 | 1.128 |

The rc98 candidate is fastest in both modes and below rc94's original dossier measurement of 12.3 seconds. As in the supplied probe, historical runs use their own writer/LZ owners with current shared support modules. Consequently rc94 also benefits from the new palette support in this comparison. rc93 executes the full build entry and is not directly comparable to preflight; the probe's old receipt-index error was corrected and that row rerun.

Implementation and byte preservation:

- NumPy uses signed 64-bit visible-colour distances, exact weighted median-cut box decisions, frequency/RGBA medoid tie order, and first-index nearest-colour ties. The old quantizer remains a test-only oracle. Six fixtures run every palette limit; the existing CASES and complete-span goldens remain unchanged.
- One candidate generator builds each group ladder. The selected optimal attempt reuses its candidates. Filtered size suggestions compute their own quantization, because filtering quantized pixels would change the algorithm. Identical pixels share quantization and mip generation even when their PNG intents name different normal/mud or package targets. Quality receipts are calculated for the selected fit, and public quantizer calls still return the identical receipt.
- Capacity is an optimistic token-cost proof over unchanged source regions. It permits overlapping matches, arbitrary edited bytes and hash collisions, which can only lower the bound. A too-large result therefore safely skips all full-size rungs.
- The greedy codec changes stay in nfl_txtr.py: NumPy forms exact three-byte keys, and C substring searches replace long Python candidate walks. The optimal parser uses the same longest-match search with the original comparison charges. The span filler calculates the exact flag/payload size delta and serializes once. Oracle tests and unchanged compressed-span goldens verify the bytes.
- Staging retains a SHA-256 with the file identity. Unchanged files are not reread by receipt saving. Art, source span, target layout, intent and scale bind each group check. One edited group rechecks its members; the 24-item refit fixture changes full-project preflights from two to one, followed by a three-row check of the affected group.
- EquipmentCompileCache grows with project size to a 512 MiB bound and uses byte-counted LRU stores. Quantized output and parse caches are separately bounded. Build-owned temporary storage retains evicted preflight results until serial consumption. Single-worker Build avoids process startup; process workers retain caches across jobs.

Validation: the combined focused run passed 79 tests and 66 subtests, including T1/T4/T5, unchanged retail round-trip checks, byte oracles, capacity, incremental rechecks, cache sizing, serial reuse, refit count and target-specific PNG mip reuse. The POSIX-only scan, self-sufficiency scan and simulated non-POSIX build passed 17 tests. The canonical repinner was run after pinned-owner changes. No XBE writer changed.

The full isolated pytest sweep covers 708 files: 708 green, 0 failures. It reports 6,988 passed tests, 61,547 passed subtests, 126 built-in skips and 127 successful standalone unittest checks. The 13 excluded gates are exactly the list in sweep711.py. Five existing unittest entry-point wrappers were run directly because pytest collects no tests from them. An intermediate provider-pin syntax error interrupted 222 files during collection; all affected files were rerun after the correction, and only the final result is counted here. See [consolidated results](reports/b72_t1/sweep_final.json) and [all initial and final per-file logs](reports/b72_t1/sweep_logs.tar.gz).

Coach Edwards should see project open remain immediate, a fitting shoe or retail sock complete in about a second per measured unit, and an impossible retail shoe promptly offer a checked smaller size. The measured 32-group equipment fit plus serial reuse takes 2.518 seconds with one worker. Real imports can fan out to multiple reviewed packages; those share matching artwork and spans, while distinct spans still require a check. A complete Build ALL also includes other assets and disc copying. No in-game result is claimed.

Exact laptop commands and the UI verification sequence are in [VERIFY_WINDOWS.md](reports/b72_t1/VERIFY_WINDOWS.md). Authoritative timing evidence: import_before.json/import_release.json, retail_before.json/retail_release.json, build_cold_rc97_off.json/build_cold_rc97_on.json, build_cold_release_off.json/build_cold_release_on.json, refit_rc97.json/refit_release.json, open_rc97.json/open_release.json and version_final.json, all under reports/b72_t1/.

01. Job b72-t1 starts from origin/main 088e3f41.
02. Phase A is commit bd66e362 and preserves the quantizer output bytes.
03. Phase B is the second commit on the bundled b72-t1 branch.
04. The runtime uses shipped NumPy and needs no native helper on Windows.
05. Six old-quantizer oracle fixtures pass every palette limit.
06. Existing byte goldens and retail round-trip tests remain unchanged.
07. Each fit ladder generates its candidate pixels once.
08. Identical normal and mud artwork shares quantization and mip work.
09. Capacity checks prove impossible full-size fits before quantization.
10. Helper OFF shoe import improves from 11.697 to 0.767 seconds.
11. Helper OFF retail sock plus mud improves from 23.832 to 1.042 seconds.
12. The oversized retail shoe reaches checked needs-refit in 4.428 seconds.
13. Cold single-worker 32-group fitting improves from 34.131 to 2.450 seconds.
14. Serial reuse takes 0.067 seconds and recompiles zero completed groups.
15. The 24-item refit improves from 30.070 to 1.783 seconds.
16. Opening 600 replacements stays below one second at 0.773 seconds.
17. Incremental hashes, group checks and byte-bounded caches replace project churn.
18. All 708 included test files pass; only the 13 specified gates are excluded.
19. Windows verification commands and full timing evidence accompany the report.
20. No Windows hardware timing, published installer or in-game result is claimed.
ASTRA_DONE

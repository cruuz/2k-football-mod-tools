PROVED OFFLINE: ED1, 2026-09-29. Work started at `6bd9b3d66d239a267f8d4f66e083b8a6eb320671` on `job/b76-ed1`. The N1 and N2 failures were reproduced with synthetic inputs. No disc build or xemu was run.

PROVED OFFLINE: Read `/home/noah/AGENTS.md`, the project index, N1 and N2 in `/home/noah/Desktop/2K5-8 Editors/DISCORD_TRIAGE_2026-09-29.md`, and the supplied errors log. The log names `05162_import.json`, 41,613,140 bytes, against a 33,554,432-byte limit. Those inputs were not modified and no reporter was contacted.

PROVED OFFLINE: N1 root cause on the starting stack:

| Status | Location at 6bd9b3d66 | Finding |
| --- | --- | --- |
| PROVED OFFLINE | `mod_editor/studio/project_archive.py:60,811` | The base reader rejects project.json above 16 MiB. |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_model_project_session.py:47` | The Models precheck rejects the same file, even if it has no model edits. This supplies Coach Edwards's exact error text. |
| PROVED OFFLINE | `mod_editor/studio/project_archive.py:697-711` | Saving serializes fit receipts and checks combined payload size, without the reader's manifest check. |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_project_fit.py:82-92,110-129` | Changed fit digests accumulate. Art receipts also repeat their complete inputs/targets body once per input, causing quadratic growth within a group. |
| PROVED OFFLINE | `mod_editor/studio/project_archive.py:92-133` | The receipt sanitizer limits key and row counts, with no byte budget. |

PROVED OFFLINE: The exact starting writer saved 600 equipment PNGs across 200 synthetic uniform sets, 200 uniform colour records, and 100 generations of fit measurements. Its manifest was 17,345,658 bytes. Both starting readers then refused it. The reproduction loads the original Python modules directly from the starting commit. See [reproduce_baseline.py](reproduce_baseline.py) and [baseline-reproduction.log](baseline-reproduction.log).

PROVED OFFLINE: N2 root cause on the starting stack:

| Status | Location at 6bd9b3d66 | Finding |
| --- | --- | --- |
| PROVED OFFLINE | `mod_editor/core/equipment_palette.py:137-147` | `quality()` emits every distinct source/destination RGBA colour pair as a JSON object, including pixel counts. A detailed texture can approach one object per pixel. |
| PROVED OFFLINE | `mod_editor/core/nfl2k5_uniform_equipment_writer.py:1629,1977` | Each selected texture's complete colour list is included in the physical group's import report. |
| PROVED OFFLINE | `tools/nfl2k5_visual_mod_project.py:1606-1608,4404-4415` | Normalization deep-copies that report and the builder serializes it verbatim. These writer lines moved from the beta 75 triage. |
| PROVED OFFLINE | `mod_editor/core/equipment_reporting.py:15,38-52` | Studio refuses the resulting receipt above 32 MiB. |

PROVED OFFLINE: Three synthetic 256x256 palette-projected equipment textures generated 65,528 colour-change entries each and a 53,820,262-byte receipt with the starting writer. The real normalization and parent receipt reader reproduced the size refusal. No project-wide edit list, embedded PNG data, or repeated fit history was necessary to produce it. The synthetic fixed replacement span, all three preview hashes, and aggregate quality measurements equal the baseline. Span SHA-256: `f61254ba9afe1b9eeba2b292d6c0dfd8c653bf02fda8caf64cb0a4fc561a881e`.

INFERRED: Accumulated fit receipts are a plausible explanation for Coach Edwards's oversized project, and colour-change detail is a demonstrated explanation for oversized equipment import receipts. His project and retained receipt were not supplied, so their exact contents and his particular recovery remain unverified. The 05162 ordinal alone does not identify which provider produced that receipt.

DESIGN: The fix keeps a 16 MiB limit for newly saved manifests and enforces it before publication through `project_archive.manifest_payload()` at line 163. Both the base writer and Models archive copier use it. Optional fits are removed if necessary before refusing oversized authored metadata, and a failed save preserves the previous file. The existing archive, replacement, checksum, member and expanded-size gates remain active.

DESIGN: `project_archive.read_project_manifest()` at line 146 is shared by both readers. For a legacy manifest over 16 MiB, `project_manifest.recover_manifest()` at line 156 streams and validates JSON while discarding only the top-level advisory fit cache. It handles large strings without loading the whole history. Authored metadata remains bounded at 16 MiB; malformed JSON, duplicate keys, excessive nesting, invalid assets, or an archive beyond its existing total bound are not treated as successful recovery. This is recovery for cache-inflated projects, not a claim to repair corrupt files or unlimited authored metadata.

DESIGN: Opening never rewrites the supplied archive. The note explains that old measurements were cleared, the artwork was retained, and Save Project keeps the smaller file. Session, Models and facade propagate that note; `StudioOperationResult.project_migrated` enables Save in the GUI. Build rechecks the cleared measurements.

DESIGN: `nfl2k5_project_fit._prune()` at line 82 removes obsolete source/input/group identities during fit, restore and save. Art receipts store one shared body and restore labels for all inputs. `project_archive._fit_receipts()` at line 96 adds a 4 MiB total budget and 128 KiB per-group budget. Oversized advisory diagnostics become pending measurements rather than blocking artwork recovery.

DESIGN: `equipment_palette.quality()` at line 154 retains exact full-image quality metrics, exact merge/pixel totals, and at most 64 deterministic colour examples per texture. Omitted examples are explicitly counted. `compact_quality()` at line 143 also handles old cached measurements when the writer assembles its report at line 1978. Small reports keep their existing shape. Palette selection and encoded game bytes are unchanged by this reporting change.

PROVED OFFLINE: The pinned equipment catalog contains 28,530 textures in 4,438 physical groups, with at most 14 textures per group and at most 65,536 pixels per texture. The new example cap therefore permits at most 896 colour-change examples per group receipt. The focused synthetic receipt shrank to 65,314 bytes. Receipt size varies slightly with temporary path length.

DESIGN: The 32 MiB parent receipt bound stays in place. The verbose field now scales with a fixed example count and the catalog's group size, rather than every distinct pixel pair. Other fit, mip, input, target, preview, replacement and hash evidence remains in the receipt. Raising the bound would also increase the reports Studio retains in memory and would leave the growth cause intact.

PROVED OFFLINE: All 12 tests in [test_b76_ed1_large_projects.py](../../tests/mod_editor/test_b76_ed1_large_projects.py) passed. The 17,345,658-byte legacy manifest opened through the facade and saved at 218,634 bytes. All 600 PNG payloads, all 200 colour records and the original archive hash were preserved. Tests also cover repeated fits, compact shared art records, byte budgets, atomic save refusal, malformed recovery JSON, receipt tampering, Models metadata preservation, and the GUI Save state. The Models test substitutes the source-span restore boundary; it tests archive transport, not model geometry or runtime behavior.

PROVED OFFLINE: [focused-tests.log](focused-tests.log) records 12 tests in 13.601 seconds and peak RSS 208,880 KiB. [baseline-reproduction.log](baseline-reproduction.log) records the original failures and identical replacement evidence, with peak RSS 616,044 KiB. Test commands used `taskset -c 24-31`, `ulimit -v 1450000`, `OPENBLAS_NUM_THREADS=1`, and `OMP_NUM_THREADS=1`. Only this job's focused tests and reproductions ran. Candidate F had not exposed a completion/failure marker at the last check, so broader suites were not run.

DESIGN: [COACH_EDWARDS_NOTE.md](COACH_EDWARDS_NOTE.md) contains wording Noah can relay. No message was sent.

DESIGN: Handoff uses `.scratch/ed1-private.git`, with the shared object store referenced read-only. The private commit includes explicit pathspecs and the requested coauthor trailer. The incremental bundle is `reports/b76_ed1/b76-ed1.bundle`, based on 6bd9b3d66. The accompanying `bundle-verification.log` and `HANDOFF.json` record verification and the resulting commit. No shared refs, push or tags are part of this handoff.

PROVED OFFLINE: 1. The starting writer saved a project both readers refused.
PROVED OFFLINE: 2. The synthetic legacy manifest measured 17,345,658 bytes.
PROVED OFFLINE: 3. Recovery saved that manifest at 218,634 bytes.
PROVED OFFLINE: 4. All 600 PNGs and 200 uniform colours survived.
PROVED OFFLINE: 5. Recovery left the original archive unchanged.
DESIGN: 6. Save and open share the manifest budget and recovery reader.
DESIGN: 7. Stale fit groups are pruned and shared art bodies are compacted.
DESIGN: 8. Advisory fits have explicit per-group and total byte budgets.
PROVED OFFLINE: 9. Three detailed textures reproduced a 53.8 MB receipt.
PROVED OFFLINE: 10. The focused fixed receipt measured 65,314 bytes.
PROVED OFFLINE: 11. Replacement bytes, previews and quality metrics matched the baseline.
DESIGN: 12. Recovery explains the change and enables Save Project.
PROVED OFFLINE: 13. All 12 focused regressions passed within the memory limit.
INFERRED: 14. Coach Edwards's exact files still need direct confirmation.
PROVED OFFLINE: 15. No disc build, xemu, reporter contact, push or tag occurred.
ASTRA_DONE

# b72-s6: live capture audited, cause and fix remain unresolved

Base: `ebed4b998b7f052bb05906c562f9650eb0e03776` (`refs/astra/b72-s5/b72-s5`). Delivery branch and bundle: `b72-s6`.

**The supplied sample contains no appended scorebug atlas draw. The dark-label reproduction gate fails, so no cause-specific runtime fix is claimed or applied.** The 60,972 method events form 788 closed draws, with no surface/clear/flip markers and zero uses of the sprite atlas. Stock xemu also suppresses every 16-bit index value; enabling its abbreviation event would supply counts only. The contents do not support the description of several whole frames.

An additional earlier window in the original session `trace.log`, at 13:55:28, contains six atlas draws and two logo draws. Their order and texture addresses correspond to the later RAM scene descriptors. Because the actual indices were omitted and RAM was saved later, material names are explicitly inferred. The inferred label and score draws have identical observed state, identical s5 vertex programs, c6=0.5, zero final combiner constants and bright label vertex colours. Missing state remains unknown, with last-write provenance recorded for every observed register and constant.

The actual saved disc-p `.2k5patch` atlas matches RAM exactly: 131,072 swizzled index bytes at `0x01e55480` and 1,024 palette bytes at `0x01e75480`, with zero changed bytes. The later RAM scene index batches also match disc p. The RAM file is missing 7,901,184 top bytes, but those resource and scene regions are fully present. This establishes intact guest resources at dump time, not the contents of xemu's host texture cache at the earlier draw.

The raw-memory decoder and captured fragment model predict label cores 255 and score cores 253. The two supplied screenshots' measured label interior peaks at 32.79, with score maxima 253. These are texel-centre probes and explicit screenshot-region measurements, not an exact raster reproduction. No fitted darkening was introduced. The installed xemu is commit `fc24584`, while the supplied local source is `f9b1403`; the installed logger and upload semantics were verified, but a full shader/cache source equivalence claim is not made.

[GPU findings](reports/b72_s6/GPU_FINDINGS.md), [complete method/provenance comparison](reports/b72_s6/gpu_methods.md), [resource comparison](reports/b72_s6/ram_build_comparison.json), [model probes](reports/b72_s6/model_probe.json), [bounded next-capture specification](reports/b72_s6/NEXT_CAPTURE.md).

The next decisive evidence is a same-frame label/score pair with actual indices, full draw-time PGRAPH state, host texture bytes, GLSL/uniforms and colour/depth attachments before and after each draw and at frame end. The capture specification corrects the index logger and requires a one-shot collector, unconditional trace cleanup, an independent timeout and verified disabled events. A fixed-duration method-only sample is not enough.

The product changes are diagnostic: a bounded trace parser with explicit unknowns, exact-RAM P8 decoding and acceptance of the observed one-mip filter setting. The runtime, scene, neutral template and s5 team colours are unchanged. RX remains 4,086/4,096 bytes with 10 spare bytes, RW 128 bytes, appended data 324,832/400,000 bytes. All-team fixed readability cannot be certified until reproduction succeeds.

[Validation](reports/b72_s6/VALIDATION.md): all 35 required standalone files pass below 100 seconds, covering 307 collected cases, 299 executed and eight existing skips. This includes native order, visibility, all-team tint checks, provider integrity and portability scans. Both application release/runtime closures pass. The runtime rebuild and read-only cave space proof pass. The separate source-freshness check fails first at `nfl2k5_scorebug_exact.py`; its stale-source set is unchanged from the base; the manifest was not regenerated. The full unchanged auxiliary allocator/oracle suites were not rerun.

The live Jev diff-gate recipe returned zero deterministic findings and flagged two diagnostic model changes for review. [Manual dispositions](reports/b72_s6/JEV_REVIEW.md) explain the retained validation and tested filter extension. New tooling is allowlisted and pinned; provider closure remains 301. This job uses the [jev-2k-testing skill](/home/noah/.codex/skills/jev-2k-testing/SKILL.md).

Git commits and branch `b72-s6` are in the owned `.scratch/b72-s6.git` store because shared worktree metadata is outside writable roots. The transferable bundle is `.scratch/b72-s6.bundle`, with the same payload also at `.scratch/astra-b72-s6.bundle`. No emulator, disc, installer or release was launched or built. The integrator still owns any eventual test disc; nothing ships before player approval. This is a diagnostic handoff, not a beta 73 label fix.

## 20-line summary
01. Job b72-s6 starts at ebed4b99 and is delivered on branch/bundle b72-s6.
02. The supplied 13:55:49 sample contains zero appended sprite-atlas draws.
03. It has 60972 method events and 788 closed draws, with no frame-boundary markers.
04. Every observed draw state and write provenance is retained in the compressed state dump.
05. Stock xemu suppresses all ARRAY_ELEMENT16 values; abbreviation adds counts only.
06. An earlier 13:55:28 window in the same session contains six atlas draws.
07. Later RAM descriptors corroborate inferred label and score draw identities.
08. Those identities are not proved indices or a synchronized draw-time RAM snapshot.
09. Inferred label and score draws have identical observed GPU state and vertex programs.
10. Actual disc-p atlas indices and palette match RAM byte-for-byte, with zero differences.
11. RAM truncation misses 7901184 top bytes but includes the relevant atlas and scene.
12. Exact-byte fragment probes predict label cores 255 and score cores 253.
13. Screenshot label interiors peak at 32.79; exact raster reproduction remains unavailable.
14. The dark-label cause is unresolved and no guessed runtime fix is applied.
15. The next capture requires same-frame indices, full state, host textures and attachment history.
16. The capture recipe limits tracing, always disables events and checks complete RAM length.
17. Runtime and team colours are unchanged; RX is 4086/4096 and appendix 324832/400000 bytes.
18. All 35 required test files pass under 100 seconds; both product closures pass.
19. Jev flagged two reviewed model extensions; stale cave-source evidence remains unregenerated.
20. No emulator, test disc or release was produced; no new in-game result is claimed.
ASTRA_DONE

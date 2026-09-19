# b72-s5: active team colours, GPU cause unresolved

Base: `ec5d68d4` (`refs/astra/b72-s3/b72-s3`). Delivery branch/bundle: `b72-s5`.

**Step A fails its reproduction gate. Step B is implemented. This is not a validated beta 72.1 dark-label fix.** The native trace now executes the retail material and shader binders, but its label and score fragment state is identical and predicts bright white labels. The model maxima are 255 against supplied screenshot maxima 67, 90 and 74. The exact darkening state is still unknown, so no guessed GPU reset or material-path change is applied.

The decisive missing evidence is a live FIFO/PGRAPH capture covering the preceding game draw and paired label/score draws, their VRAM texture/palette bytes, vertex program/constants, generated xemu shader and uniforms, and render-target pixels before/after each draw. In particular, the bounded fixture lacks actual inherited depth-test enable, shade mode, logic-op state, DMA context/surface/clipping/AA state and real fetch/cache contents. A live CPU shadow-cache snapshot is also needed because forcing this fixture cache dirty can conceal disagreement with actual GPU registers. The captured final C0 alpha is zero; a nonzero inherited constant remains a hypothesis, not an established cause.

[GPU findings and the exact next capture](reports/b72_s5/GPU_FINDINGS.md), [side-by-side NV097 method table](reports/b72_s5/gpu_methods.md), [three-screenshot calibration receipt](reports/b72_s5/calibration.json), [xemu source identity](reports/b72_s5/xemu_source.json).

`render.py` defaults to the bounded xemu fragment model, with P8 swizzle/palette decode, captured vertex colour multiplication, combiner math, alpha test and blending. The old path is available with `--naive`. The images, CLI and sidecars explicitly mark calibration failed. Surface-scale coverage, the omitted preceding frame state and retained native event-font raster prevent a claim of game-equivalent preview output. S3's CPU plate-before-label result is retained; required order and 71.1 visibility regressions remain in the validation set.

Team accents are active through a revision-2 native table covering 52 asset-code/kind slots. Neutral shape masks remove old template hues. Rims, wings, plates, capsules and pointers use the relevant team's validated palette variants. Clock and quarter ink are white for contrast. Raiders wings/rims are a darker supplied silver variant; plate/capsules are official black. The wing alpha gradient is reduced to 75 percent. No glyph shape or visibility decision was changed.

[4:3 all-team model sheet](reports/b72_s5/all_teams_43.png), [16:9 all-team model sheet](reports/b72_s5/all_teams_169.png), [team-colour implementation and review list](reports/b72_s5/TEAM_COLOURS.md), [review swatches](reports/b72_s5/accents/contact_sheet.png).

Jev ran live typed choices over all 42 prior review slots. Two phrasings agreed at confidence >=0.8 for 22; 20 retain code-valid prior choices for Noah's review. Seven custom or undocumented slots retain explicitly flagged neutral palettes, for 27 review entries total. Full requests, responses and confidence gates are retained under `reports/b72_s5/accents/`. The decision model received text/metadata, not images. Palette membership and contrast are checked independently in Python and against native vertex output for every slot, both possessions and both aspects. The weakest selected plate has white contrast 4.682:1. Model core diagnostics are >=253 at 4:3 and >=254 at 16:9; these uncalibrated predictions do not pass Step A.

Appended data is 324,832 / 400,000 bytes. The native owner uses 4,086 / 4,096 RX bytes and the existing 128-byte RW allocation. RX headroom is only 10 bytes; future edits must recheck it. Revision-1 scene compatibility remains available for baseline comparisons. New modules are declared in the release allowlist and replication/provider pin closures. The PNG catalog's single changed template entry and its digest pin are refreshed; no cave manifest was regenerated.

[Validation details and final timings](reports/b72_s5/VALIDATION.md): all 34 required standalone files pass, with every default path below 100 seconds (298 collected cases, 290 executed, eight existing skips documented). The slowest is the resource suite at 78.49 seconds. Both application release/runtime closures, provider integrity and portability scans pass. The cave-oracle audit reports two stale-manifest errors, both first identifying `nfl2k5_scorebug_ingame.py`; its manifest checks were retained and no regeneration was performed. [Performance changes and differential evidence](reports/b72_s5/PERFORMANCE.md) document how the default scorebug tests avoid repeated work while preserving output and assertions. The auxiliary allocator audit passed all seven tests in 431.67 seconds on its longer retry; its first 420-second timeout is retained. No test disc, installer or release was built, and no new in-game result is claimed. The integrator still owns the unavailable `jev_diff_gate.py` run and any manifest regeneration/integration work. Noah's approval remains required before anything ships.

The shared Git metadata is outside this sandbox's writable roots. The commit and `b72-s5` branch are therefore created in the owned `.codex-tmp/b72-s5.git` store, with a transferable `.codex-tmp/b72-s5.bundle` based on `ec5d68d4`. The original worktree Git metadata is untouched.

## 20-line summary
01. Job b72-s5 is based on ec5d68d4 and delivered as branch/bundle b72-s5.
02. Step A fails calibration; this is not a proved beta 72.1 dark-label fix.
03. Native capture now executes the retail material, vertex-program and combiner binders.
04. Label and score fragment state match in the bounded fixture at both aspects.
05. Captured P8 fetch, vertex colour, combiner, alpha test and blend predict white label cores.
06. Model maxima 255 miss screenshot maxima 67, 90 and 74 by more than 15.
07. The exact darkening state remains unknown; no guessed GPU reset was applied.
08. A live paired draw capture must include preceding GPU state, CPU caches and VRAM contents.
09. render.py defaults to the bounded xemu model; --naive preserves the earlier comparison.
10. Images and receipts visibly flag failed calibration and absence of a game capture.
11. Neutral template masks and team accents are active for all 52 roster tint slots.
12. Raiders use silver-derived grey and black; their fills contain no pink.
13. Jev processed all 42 prior review slots and resolved 22 at the confidence gate.
14. Twenty unresolved choices and seven undocumented neutral palettes remain flagged for Noah.
15. Both-aspect contact sheets and all-slot native tint/palette checks are included.
16. Model cores are at least 253; these predictions do not establish in-game readability.
17. Appended data is 324832/400000 bytes and RX is 4086/4096 bytes, with 128 RW bytes.
18. All 34 required files pass below 100 seconds; both product closures pass; see VALIDATION.md.
19. Cave-oracle stale-manifest errors remain; the integrator owns regeneration and Jev diff gate.
20. No manifest, release, installer or test disc was generated; no new in-game result is claimed.
ASTRA_DONE

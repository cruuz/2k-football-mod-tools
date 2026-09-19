# b72-s1: SD scorebug and calendar-aware ESPN watermark

Base: `088e3f41`. Branch: `b72-s1`. Source commit: `b83df72b`.

The supplied report said, "the scorebug still doesn't appear to have readable 1st and 10" and requested "espn nfl, only mnf when it's literally monday night football." The shipped SD cut now has larger type, individually area-filtered atlas cells, the measured ESPN art changes, and one watermark quad that selects NFL or MNF at runtime. In-game appearance and behaviour remain **UNWITNESSED**.

## Result and evidence

- [Residual table](reports/b72_s1/residuals.md), [machine-readable measurements](reports/b72_s1/residuals.json), [before/after sheet](reports/b72_s1/before_after.png), and [label A/B](reports/b72_s1/label_size_proof.png).
- The final table contains **95 PASS, nine justified SD text exceptions, and zero FAIL**.
- At 16:9, the actual quantized label has **12 ink scanlines**, an **effective 2.654 HUD pixel stem**, and an **8.003 HUD pixel digit width**. At 4:3 the corresponding values are 12, 3.536 and 10.664. The effective stem is integrated decoded P8 alpha across the middle third of the zero's left stem, scaled by the native quad width. The scanline count uses reconstructed alpha greater than 0.5 at actual raster pixel centres.
- All eight digit columns are sampled. [Sampling receipt](reports/b72_s1/sampling.json) checks every used atlas cell against both aspects, including maximum field compression. The matcher separately traces the actual quantized UV endpoints and bilinear taps. No atlas cell is minified; no mip chain is needed. Separate team-logo textures retain their existing sampling model and are not included in this atlas claim.
- The down cap is 30 source pixels. The proposed 28 would give only 11.61 HUD pixels before rasterization, below the 12-scanline requirement. Quarter and play-clock caps are 26 source pixels. Text has no drop shadow.
- The match uses the real SCNE descriptor and push-buffer order, native transforms and 27/32 widescreen contraction, the full 640 by 448 active viewport, then display expansion. It measures the supplied temporal median and canonical frame 012001; all 16 representative frames are also measured and hashed. The moving broadcast colour range supplements the stricter median gate. Source RGB remains in the JSON beside SD-projected targets.
- The deliberate SD text differences are explicit `IMPOSSIBLE` rows. Exact broadcast cap and digit widths conflict with the readability floor. Requiring at least 2.5-pixel stems at 16:9 also requires at least 3.333 pixels at 4:3, over one pixel above the broadcast median of 2.222. These exceptions concern exact broadcast proportions, not failed minimum readability gates.
- The artwork includes team-coloured top wash and bottom rim, brighter smooth wing ramps, enlarged/repositioned logos, a glossy possession plate, lighter housing, white scores, capsule separator, and dark pointer. Clean temporal samples exclude the moving white possession arrow. Selected rare pointer, gloss and rim colours survive P8 quantization.

## Runtime and Studio

Auto mode uses ESPN NFL for Play Now and for every franchise slot except Monday night. It requires franchise mode 2, weekday Monday, and night enum 2. Invalid week, slot, month or day bounds fall back to NFL. The date is read from the current eight-byte live schedule record.

The callable current-record weekday site is **0xD22AC**, taking the record in ECX. Retail adds three before entering the historical date routine; the calendar owner detours this site. The sprite calls the site, never the raw 0x1C18B0 routine. Tests execute both the retail route and the extended-calendar route, including a year-2100 Monday.

The [two brand cells](reports/b72_s1/watermark_cells.png) share one quad. The spare static-table word locates the policy and both UV sets inside the existing scene allocation. Auto starts with NFL even before the first update; always-MNF starts with MNF; off starts transparent. Every update selects the UVs and colour. The NFL face reuses the measured ESPN/N/F art, with L reconstructed from F's stem and flipped top arm. There was no separate local NFL still, so that reconstruction is documented rather than presented as a directly measured NFL asset.

Studio and Build expose **ESPN watermark: NFL (MNF on Monday night) / Always MNF / Off**. The setting persists in projects and presets, and Preview shows both cells plus four broadcast-slot fixtures. The default policy is auto. The experimental sprite feature itself remains off in every preset.

## Native execution boundary

[Visibility sweep](reports/b72_s1/label_sweep.json): 808 cases across both aspects, four downs, distances 0 through 99, goal-to-go, and alternating possession. Each executes the native formatter and request path, verifies emitted glyphs, and draws measured white pixels.

[Retained sequence](reports/b72_s1/native_sequence.json): 28 stages across both aspects, 65 native updates per stage, covering kickoff, ball-on, retained requests, FLAG, FUMBLE and recovery to all four downs. No request, slide, binding, material or colour is reset between stages. Removing only the down glyph colours yields zero changed pixels while an event occludes the label, and nonzero label pixels in each recovered non-event stage.

[Watermark execution](reports/b72_s1/watermark_native.json): 78 scenario/policy/aspect/calendar combinations. Play Now selects NFL, Monday night selects MNF, Sunday night selects NFL, and Monday afternoon selects NFL. All three policies execute. The extended calendar enters its installed site detour without visiting the raw historical helper. Additional grid-boundary probes reject invalid indices.

The fixtures use synthetic gameplay objects and bounded predicate returns. They execute game CPU routines and the installed owner, then use a software raster. They do not boot a console, execute NV2A rendering, prove a played intro, or establish a player witness. [Input hashes](reports/b72_s1/proof_inputs.json) identify the final atlas and runtime used for these proofs.

## Size and integration

[Budget receipt](reports/b72_s1/budget.json): 47 quads, 34 TXTR plus one SCNE resource, **323,808 appended bytes**, **zero-byte delta** from beta 71.1, and 76,192 bytes below the 400,000-byte ceiling. The owner reserves 4,096 RX bytes, uses 3,798, and retains 128 RW bytes. The brand table fits existing scene padding. No FONT is appended.

The brief-authorized Build and GUI changes are implemented. [WIRING.md](WIRING.md) supplies the precise protected-registry edit, PNG-catalog pin update and cave-manifest regeneration follow-up for integration. No registry rows or version bumps were added. Source fingerprints were refreshed with `packaging/repin.py --apply`. The protected manifest remains for the integrator to regenerate under the supplied context rules. A separate fresh pure-XBE manifest observes the full scaleout safety-gate composition for the oracle run. Its resource-build check explicitly skips; no historical disc observation is presented as a fresh build.

The reviewed PNG catalog now identifies the final atlas. The protected release checker retains its old catalog digest, so the plain template-release test cannot pass until the one-line integration update is applied. The full five-test file was validated with only that exact pending constant substituted in memory, including its tamper-refusal tests. The checker file was verified unchanged. This scoped validation is identified separately in the test index; it is not a claim that the unmodified release checker accepts the new atlas.

Shared Git metadata is read-only in this sandbox. The delivery branch therefore lives in `.scratch/b72-s1.git`, using the original object database read-only. The final verified delivery bundle is `.scratch/astra-b72-s1.bundle`, based on 088e3f41. Nothing was pushed. No retail executable, pack or disc bytes were copied into the delivery. Only the supplied small measurement archive, reference crops, generated raster images and receipts are included. No emulator, display GUI or audio ran. Optional Jev judging was not used: zero calls and zero cost.

## Reproduction and validation

Run each test file standalone with `PYTHONPATH=.` and `QT_QPA_PLATFORM=offscreen`. Commands and captured outputs are indexed in [validation](reports/b72_s1/validation.md); the two runners retain per-file exit codes and durations. The five pinned suites are unmodified. The runner uses the explicit pending-pin probe for the template-release file until integration.

```sh
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 reports/b72_s1/run_suites.py
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 reports/b72_s1/final_checks.py
PYTHONPATH=. python3 reports/b72_s1/prove_all.py
python3 tools/scorebug_sprite/build_runtime.py --check
python3 tools/scorebug_sprite/match_espn.py --frames /path/to/read-only/frames --output reports/b72_s1
```

The native proof runner defaults to the local read-only reference path given in the job. The matcher accepts an explicit path for another machine. Preview and native tests require the user's pinned retail source. Historical iteration logs are retained for traceability; the final `residuals.*`, `proof_inputs.json`, `match_final.log` and frozen-atlas test logs are the acceptance evidence.

## Three player witness screens

1. **4:3 Play Now:** first-and-ten after kickoff and again after a FLAG clears. Confirm readable label pixels, clocks, logos, and ESPN NFL.
2. **16:9 Play Now:** first-and-ten with the small quarter and play clock, then a possession change. Confirm label readability, stable proportions and ESPN NFL.
3. **16:9 franchise Monday night:** confirm ESPN MNF. As controls within this check, a Sunday game and Monday afternoon must show ESPN NFL.

Every one of those in-game checks remains UNWITNESSED.

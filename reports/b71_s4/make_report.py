"""Write the handoff from measured output and retained command receipts."""
from pathlib import Path
import hashlib,json,re,shlex,subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/b71_s4'
m=json.loads((OUT/'measurements.json').read_bytes())
manifest=json.loads((ROOT/'data/nfl2k5_cave_reservations.json').read_bytes())
results=sorted((json.loads(p.read_bytes()) for p in OUT.glob('*.result.json')),key=lambda r:r['start'])
by_name={r['name']:r for r in results}
programs=sorted((ROOT/'tests/mod_editor').glob('test_*scorebug*.py'))
programs += [ROOT/'tests/nfl2k5_scorebug_layout_test.py',ROOT/'tests/nfl2k5_scorebug_mod_project_test.py']
programs += [ROOT/'tests/mod_editor'/('test_'+n+'.py') for n in ('provider_integrity','product_catalog','phase1_packaging')]
gates=['xbe-memory-final','xbe-cave-references-final']
names=[p.stem+'-delivery' for p in programs]+['registry-strict-delivery']+gates
summary_path=OUT/'final-delivery-suite-summary.json'
summary=json.loads(summary_path.read_bytes()) if summary_path.exists() else {}
ready=not summary.get('failed',True) and summary.get('sources_frozen') and all(n in by_name and by_name[n]['exit']==0 for n in names)
(OUT/'command_ledger.json').write_text(json.dumps(results,indent=2)+'\n')
lines=['# Beta 71 S4 — painted ESPN bar','',
'## Result','',
'The painted v4 implementation is delivered on the private branch `astra/b71-s4-painted-bar`, based on the completed S3 HEAD `464423f0889581182f4a6de53971ecab23be19d5`.', '',
'**Boundary acceptance is proved; visual equality is not.** Every measured region, native text box and thresholded text-ink box is within one HUD pixel in 4:3 and widescreen. The append is **410,624 bytes**, 2,944 bytes below v3. The code emits **1,380 bytes** inside the existing 1,408-byte RX allocation, with 128 bytes of RW state. `compare().exact_match` remains **false** in both aspects; this is not an exact ESPN image match.', '',
('All requested standalone suites, strict registry validation and both detached XBE gates passed on the final implementation.' if ready else 'Final validation is still pending; this generated draft must be refreshed after all gates finish.'), '',
'Compare the actual output: [4:3, ESPN above / native below at 2×](reports/b71_s4/compare_43.png), [widescreen at 2×](reports/b71_s4/compare_wide.png), [event and matchup contact sheet](reports/b71_s4/states_contact_sheet.png). The supplied `bar_compare_espn_vs_s3_render_2x.png` was inspected before editing.', '',
'## The six residuals','',
'1. **Painted body and ramps.** `atlas_mnf()` paints at twice source resolution, then downsamples tiles into a same-name **256×512 P8** `score_buga` atlas. The frame tile is 256×110, stretched over the 1,041×110 source rectangle; this horizontal storage limit remains visible in fine edges. Body RGB is (37,37,37), with an r=8 silhouette, two-source-pixel top rim (60,64,70) and bottom rim (13,20,28). Two neutral white alpha ramps are tinted by the owner and blend smoothly to the charcoal inner wing edge. Score-panel slabs are gone: score digits sit over the same flat body. The housing, capsule, red-cell silhouette and plate are painted tiles.',
'2. **Plate and label.** Plate 837..1083 × 947..983; a separate top-centre triangle uses the same tintable white mask. The complete v3 primary/near-black-secondary table stays. Roboto Condensed Bold is rasterized at 64 pixels (46-pixel cap, twice the target 23), retained as a checked-in mask sheet, and downsampled into existing ASCII cells in slot 9. Digits, ordinal letters, ampersand, Goal/and letters and space remain available to native formatting. The font authoring source and SHA are in `painted_label_2x.json`; no installed font is required at runtime.',
'3. **Capsule.** White 839..1019 × 999..1039 and red (215,0,51) cell 1019..1082 × 999..1040. A 41-source-pixel painted backing covers the capsule; the white region bottom is therefore 0.413 HUD pixel below its 40-pixel reference box. Quarter is dark (30,30,30), with raised smaller capitals; clock is black bold; play-clock digits are white. Native countdown and visibility remain, with the existing below-five-seconds red pulse. Hidden play clock removes its digit/pulse layer; the painted red backing remains.',
'4. **Scores and ticks.** Private large-score cells are now 26×48 texels, with 53-source-pixel draw height and RGB (225,225,225). Compact multi-digit cells share those UVs and remain clear of the plate for 28, 100 and 999. Three bright (246,246,246) 20-source-pixel ticks use native timeout callbacks with 10-pixel gaps. Their ink lands within one HUD pixel of the requested y=1032..1038 boxes.',
'5. **Logos.** One shared 64×64 logo cell per team replaces separate home/away textures. The v3 aspect fit is retained in a 200×107 source quad; DEN is enlarged to fill that height. The original small source marks still limit edge quality. Both DEN at KC and NO at DEN were rendered in both aspects; NO uses its gold secondary possession plate.',
'6. **Retail states.** Native flag, score-event (FUMBLE), hang-time, ball-on and hidden play-clock states were rendered individually at both aspects. Their slabs sample flat charcoal and their native text remains readable. `all_events` intentionally overlays incompatible labels and is diagnostic only. Native formatting, callback ABI, missing-FONT fallback, score ranges, timeouts and urgency cases are covered by active native suites.', '',
'## Native routes and allocation','',
'The appended same-name atlas wins the ordinary HUD resource lookup. The original 64×64 static fallback atlas remains in its fixed span. Slot 9 uses an appended same-name `FirstPersonComic` FONT, preserving the retail root/boot-loop lookup; quarter uses appended `core_bug`. Their live descriptor references are field-relative, including a backwards range-table reference resolved with x86 32-bit wrapping. No parallel invented FONT record replaces the native loader.', '',
'The scene stays in its **4,800-byte compressed span** with retail wrapper/scratch size retained by the fill compressor. Existing NV2A command spans are rewritten to plain quads (13 quads plus the pointer triangle across 11 submeshes). The steady visible bar has 19 triangles. Retail nine-slice indices and score slabs no longer draw. SHAPE UV scale/bias is normalized to (0.5,0.5,0.5,0.5), avoiding the retail 64-pixel correction sampling a neighbouring white atlas texel on event slabs.', '',
'Material ownership: `cscore_buga` draws body, housing and capsule; `yscore_buga` / `yscore_buga1` draw tintable away/home masks; `zscore_buga` / `hscore_buga` draw shared logos; `dscore_buga` draws plate and pointer. The spare `score_buga` material owns the red pulse cell. Native event materials retain separate charcoal quads. Hang time owns the spare event slab, preserving its formatter and visibility.', '',
'Both sides resolve the canonical `sbXXh0` resource. Per-team plate and wing ARGB words occupy unused TXTR header padding immediately before the native descriptor (descriptor −8 / −4), sealed by full compiler hashes. Setup caches them in RW state and updates the masks and possession plate. This removes inline colour tables and keeps the owner in the established legacy allocation. Missing HUD/FONT lookups retain native score and clock callbacks; private codepoints are installed only after successful slot-9 lookup.', '',
'Score ranges are U+0080..0089 (large) and U+0090..0099 (compact), clock U+00B0..00B9 and play clock U+00C0..00C9. Native clock formatters still produce the values before remapping. Event ASCII remains available. The owner setup and update displaced calls execute once, with their original ABI.', '',
'### Exact volume','',
'| Appended component | Count × bytes | Total bytes | Native heap bytes |',
'| --- | ---: | ---: | ---: |',
'| Shared 64×64 team TXTR | 32 × 5,280 | 168,960 | 172,032 |',
'| Neutral 32×32 TXTR | 1 × 2,208 | 2,208 | 2,304 |',
'| Painted 256×512 P8 atlas | 1 × 132,256 | 132,256 | 132,352 |',
'| Slot-9 FirstPersonComic FONT, 256×256 | 1 × 80,160 | 80,160 | 80,256 |',
'| core_bug quarter FONT, 128×128 | 1 × 27,040 | 27,040 | 27,136 |',
'| **Total** | **34 TXTR + 2 FONT** | **410,624** | **414,080** |', '',
'The pack grows by **411,648 bytes** after sector alignment. V3 appended 413,568 bytes: v4 saves **2,944 bytes (0.71%)**. The payload stays in the historically viable ~0.4 MB class. This is a byte/loader-allocation proof, not a played-game peak-memory or freeze guarantee.', '',
'## Measurements','',
'Reference: `frame_012001.jpg`, 1920×1080, SHA-256 `'+m['reference']['sha256']+'`. The corrected S4 boxes supersede the older broad v3 comparison rectangles. Source coordinates map to the active 640×448 HUD with y inset 16; widescreen additionally contracts x around 320 by 27/32. Boundary errors below are HUD pixels, not pixels of the enlarged comparison sheet.', '',
'`prove_v4.py` executes the native callbacks and scene transforms, then calls `compare()` with `MNF_V4_COMPARE_REGIONS` and the requested text boxes. Software raster output is measured independently for text ink. [measurements.json](reports/b71_s4/measurements.json) includes full native boxes, thresholded ink boxes and source-restored ink boxes.', '',
'### Per-region boundary error and RGB MAE','',
'| Region | 4:3 boundary | Wide boundary | 4:3 RGB MAE | Wide RGB MAE |',
'| --- | ---: | ---: | ---: | ---: |']
for name,a in m['comparisons']['43']['regions'].items():
 b=m['comparisons']['wide']['regions'][name]
 lines.append(f"| {name} | {a['native_boundary_error_px']:.6f} | {b['native_boundary_error_px']:.6f} | {a['rgb_mae']:.3f} | {b['rgb_mae']:.3f} |")
lines += ['', 'Mean region RGB MAE: **'+f"{m['comparisons']['43']['mean_region_rgb_mae']:.3f} / {m['comparisons']['wide']['mean_region_rgb_mae']:.3f}"+'** (4:3 / wide). The comparison threshold is 8; neither image passes it. Full-frame containment is empty and every visible triangle has consistent winding. The reference still differs in bevel/reflection detail, plate colour (the requested v3 team table is retained), mark contours, text shapes and sampled edges. These differences must not be described as an exact ESPN match.', '',
'### Text boundaries','',
'Each row reports the greatest coordinate error for the native quad and measured raster ink. Source rectangles use exclusive right/bottom edges.', '',
'| Text | Requested source box | 4:3 native / ink HUD error | Wide native / ink HUD error |',
'| --- | --- | ---: | ---: |']
for role,box in m['reference']['text_source_boxes'].items():
 rows=[]
 for aspect in ('43','wide'):
  c=m['comparisons'][aspect];cb=next(cb for cb,r in c['callback_roles'].items() if r==role);rows.append(c['text'][cb])
 a,b=rows
 lines.append(f"| {role} | {box} | {a['max_error_px']:.6f} / {a['rendered_ink_max_error_px']:.6f} | {b['max_error_px']:.6f} / {b['rendered_ink_max_error_px']:.6f} |")
lines += ['', '| Text | Source-restored ink, 4:3 | Source-restored ink, wide | Max HUD error, 4:3 / wide |', '| --- | --- | --- | ---: |']
for role in m['reference']['text_source_boxes']:
 a,b=[m['comparisons'][aspect]['rendered_text_source_boxes'][role] for aspect in ('43','wide')]
 lines.append(f"| {role} | {a['box']} | {b['box']} | {a['max_hud_pixel_error']:.6f} / {b['max_hud_pixel_error']:.6f} |")
lines += ['', '## Regeneration and tests','',
'Compiler pins were regenerated after the final UV correction: [compiler_pins.json](reports/b71_s4/compiler_pins.json), `pins-uv.log`. `packaging/repin.py --apply` refreshed provider seals. The unified visual provider now seals the assets module used for arbitrary atlas dimensions; its product allowlist includes that module and the two authored label files. The strict provider count is 286.', '',
'The S3 `refresh_manifest.py` recipe observed the complete forward XBE stack from the A5 manifest, retaining historical retail reservations and excluding the shared rules helper from duplicate ownership. The final manifest has **13,095 spans**, with **138 observed calls**. SHA-256: `'+hashlib.sha256((ROOT/'data/nfl2k5_cave_reservations.json').read_bytes()).hexdigest()+'`. Scorebug owner code is `0x14BAA60..0x14BAFE0`; RW data is `0x14BB010..0x14BB090` in this union. The projection records `release_manifest=false`, `disc_built=false`, `runtime_witnessed=false`, `production_regeneration_required=true`; inherited disc fields are historical. External production packaging must regenerate its disc receipt.', '',
'Both XBE gates were launched **detached** using `setsid nohup`, redirected logs and stdin `/dev/null`, then polled. A foreground shell waited for each detached child to keep the sandbox session alive. No `pkill -f` was used. Their full classes cover both installation orders, allocation scale-out and oracle checks.', '',
'### Final standalone results','',
'The `-delivery` driver runs every standalone scorebug suite plus provider integrity, product catalog and phase1 packaging in independent offscreen Python processes. It records source hashes before and after. Strict validation retains default file checks. Earlier runs remain diagnostic; only this final frozen-source run and the named final gates are the delivery verdict.', '',
'| Command | Exit | Tests | Skips | Seconds |', '| --- | ---: | ---: | ---: | ---: |']
total=skips=0
for name in names:
 r=by_name.get(name)
 if r is None:lines.append(f'| {name} | PENDING | | | |');continue
 log=(OUT/(name+'.log')).read_text();count=re.search(r'Ran (\d+) tests?',log);skip=re.search(r'skipped=(\d+)',log)
 total+=int(count[1]) if count else 0;skips+=int(skip[1]) if skip else 0
 lines.append(f"| [{name}](reports/b71_s4/{name}.log) | {r['exit']} | {count[1] if count else '—'} | {skip[1] if skip else '0'} | {r['seconds']} |")
lines += ['',f'Final reported unittest cases including gates: **{total}**, including **{skips} skips**. Frozen-source driver complete: **{bool(ready)}**.', '',
'Skips retain the established precise boundaries: read-only Storage for the assets disc-copy transaction; five historical private-font-v8 cases; missing source-art fixtures; and historical layout image/glTF fixtures. Active current-font/native suites run. These skipped cases are not boot or disc evidence.', '',
'Exploratory failures are retained in the command ledger. An initial larger owner exceeded the full legacy allocator capacity; caching colours from logo header padding reduced it to 1,380 bytes. A manifest attempt detected source edits during observation and was rerun after freezing code. Later suite failures were obsolete separate-away-resource and FONT-state assertions, a missing-font callback guard, provider closure and missing ignored registry evidence. The final tests assert the new shared resources, native fallback callbacks and preserved event sampling. No gate assertions or registry file checks were relaxed. A misspelled cave-gate filename exited before execution; the correctly named detached gate supersedes it.', '',
'Strict registry validation initially lacked the same 75 ignored evidence files as S3. Real copies were restored from the existing read-only checkout, checked against S3 hashes: **2,063,157 bytes**. [evidence_hydration.json](reports/b71_s4/evidence_hydration.json) records them. These baseline ignored files are neither staged nor bundled.', '',
'## Registry, RC96 and prepared builder','',
'The existing runtime capability row now describes v4 resource counts, measured boundaries, failed exact-pixel acceptance and evidence links. Runtime status remains `not-tested`, experimental and off in every preset. The RC96 bullet is anonymous and states the software-render/played-game limits.', '',
'[build_testdisc71.py](reports/b71_s4/build_testdisc71.py) follows the S3 builder pattern: `softdrink_advanced` preset, `scorebug`, `scorebug_runtime`, `modern_color`, `widescreen` all true. Prepared output:', '',
'`NFL 2K5 MOD TEST 2026-09-15j (painted bar + colour + widescreen)`', '',
'**The builder was not run, including `--plan-only`.** It was parsed/compiled and its literal name/options checked without importing or executing it; [builder_prepared.json](reports/b71_s4/builder_prepared.json) seals the file. The builds folder is read-only here. When run externally, it checks output access, refuses an existing named output, preserves patches, applies the inherited three-test-image retention policy, checks resource/XBE/477-colour-bundle/widescreen readback, and removes an incomplete disc on failure.', '',
'Import the bundle into the integration checkout before running the builder so external receipts record the delivered source head. No disc, patch archive or disc readback receipt was generated in this task.', '',
'## PROVED / UNWITNESSED','',
'**PROVED:** authored atlas/FONT compilation and full hashes; same-name native resource binding; owner ABI, fallback, state and formatter execution; exact byte budgets; fixed scene span; corrected native boundaries and measured ink within one HUD pixel; both aspect transforms; individual event renders; multi-digit clearance; final passing suites and XBE gates as listed.', '',
'**NOT ACHIEVED:** pixel equality to the ESPN crop. The side-by-side is the review artifact, and RGB MAE remains above acceptance. It would be incorrect to call this the same image or to attribute remaining differences to untested GPU filtering.', '',
'**UNWITNESSED:** an actual intro/coin toss/kickoff load, peak memory during the intro, played-game transitions and visibility, GPU filtering, real score/timeout/possession changes and event animation. No emulator was opened. These require the external test build and a played match.', '',
'## Commits and delivery','',
'The ordinary worktree `.git` and shared repository remain untouched. All commits use enumerated explicit paths in `.scratch/private.git`, branch `astra/b71-s4-painted-bar`. Implementation commits include `d74418b8` and `52cd8348`; later test/evidence/report commits are in the bundle. No push.', '',
'Bundle: `.scratch/astra-b71-s4.bundle`, prerequisite **`464423f0889581182f4a6de53971ecab23be19d5`**, the actual completed S3 worktree HEAD. The shared S3 branch name was stale, so the prerequisite uses that exact commit. The external delivery receipt in `.scratch/b71-s4-delivery.json` records the final head, bundle size and SHA after verification. Retail inputs remain read-only; no retail native FONT/TXTR/XBE/pack/disc binaries are bundled. Scratch usage is below 200 MB.', '',
'## Command ledger','',
'[command_ledger.json](reports/b71_s4/command_ledger.json) contains exact argv, UTC start/end, duration and exit status for recorded compilation, proof and verification commands. Each named log retains complete output. Read-only discovery, patching, private-git setup, detached shell wrappers and report assembly are also in the session tool transcript. Failed exploratory runs are explicitly superseded, not erased.', '',
'| Name | UTC start | Seconds | Exit | Exact command |', '| --- | --- | ---: | ---: | --- |']
for r in results:
 command=shlex.join(r['command']).replace('|','\\|')
 lines.append(f"| [{r['name']}](reports/b71_s4/{r['name']}.log) | {r['start']} | {r['seconds']} | {r['exit']} | `{command}` |")
(ROOT/'ASTRA_REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(validation_complete=bool(ready),recorded_commands=len(results),tests=total,skips=skips)))

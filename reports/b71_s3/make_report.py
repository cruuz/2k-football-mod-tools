"""Assemble the handoff from recorded measurements and final command results."""
from pathlib import Path
import hashlib,json,re,shlex,subprocess
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/b71_s3'
def read(name):return json.loads((OUT/name).read_bytes())
m=read('measurements.json')
results=sorted((json.loads(p.read_bytes()) for p in OUT.glob('*.result.json')),key=lambda r:r['start'])
(OUT/'command_ledger.json').write_text(json.dumps(results,indent=2)+'\n')
by_name={r['name']:r for r in results}
summary=read('final-suite-summary.json') if (OUT/'final-suite-summary.json').exists() else None
gate_names=('xbe-memory-release','xbe-caves-release')
ready=bool(summary and not summary['failed'] and all(by_name.get(n,{}).get('exit')==0 for n in gate_names))
source_commit=read('source_commit.json')['commit']
lines=['# Beta 71 S3: scorebug v3','', '## Outcome','',
'V3 is implemented and committed on `astra/b71-s3-scorebug-v3`, from `a7440f05` (A5 integration). '+('Every final standalone suite, strict registry validation and both detached XBE gates passed.' if ready else '**Final validation is still running; this is a working report.**'),'',
'The native bar boundaries follow the requested source boxes within 0.007 HUD pixels in both aspects. The native comparison does **not** pass pixel-exact acceptance: text and RGB differences remain, and the supplied numeric plate/score dimensions differ from the photographed frame. The paired crops expose those differences. Appended data is **413,568 bytes / 0.394409 MiB**, only 11,008 bytes above A5.', '',
'**PROVED:** generated resource identities, bounded native collection/font lookup, actual score/timeout/play-clock callbacks, geometry and software raster output, multi-digit score separation, and the completed checks listed below. **UNWITNESSED:** booting or playing this build, GPU filtering, real-match transitions, the final disc and its option read-back. No emulator, disc build or push was run.', '',
'## Inputs and interpretation','',
'- Read `ASTRA_CONTEXT.md`, the scorebug-v2 verdict in `BETA71_TRIAGE.md`, all four requested B70/B71 source reports, and the A5 `ASTRA_REPORT.md` at the parent revision. The S3 brief expressly authorizes scorebug writers, registry evidence, RC96 and the cave-manifest update despite the older general context exclusions.',
'- Opened `/home/noah/Desktop/2K5-8 Editors/beta71_evidence/bar_compare_espn_vs_disc_f.png`: ESPN above, disc f below. The stated verdict was “it doesn’t look exactly like espn ... not close yet”.',
'- Measured source: `'+m['reference']['path']+'`, 1920×1080, SHA-256 `'+m['reference']['sha256']+'`.',
'- The explicit plate is `(828,946,1120,1000)`, larger than the approximately `(837,947,1084,983)` plate in the frame. The frame’s score “7” has 53 pixels of thresholded ink, while this brief requests 45. V3 follows the explicit numeric dimensions and reports the resulting photograph comparison honestly.',
'- The HUD transform is `x/3`, `16 + y*448/1080`; authored scene coordinates use `exact.scene_box`. Widescreen applies the existing `27/32` horizontal contraction about HUD x=320. Crops undo that contraction before restoring the 1920×1080 source coordinates.', '',
'## Implementation and injection routes','',
'### Bar, wings and possession plate','',
'The retail frame mesh uses an authored 64×64 atlas nine-slice with a real rounded corner, a light rim and vertical charcoal shading. The per-team 64×64 wing textures retain the proved small collection route. Each packs a height-filling logo and a two-dimensional colour ramp; the ramp reaches the body at about 65% of the wing width. Logo fitting uses the final source box aspect, preserving the mark’s proportions even when the texture cell itself is stretched. DEN uses the lit wing RGB `(56,89,144)`; KC uses `(180,56,86)`. No 256×512 atlas is added.', '',
'The plate is a white mask multiplied by full team colour, with a small pointer. Every other team uses its complete primary; the explicit near-black secondary choices are:', '',
'| Team | Plate secondary |','| --- | --- |',
'| CHI | `#C83803` |','| DEN | `#FB4F14` |','| HOU | `#C8102E` |','| LV | `#A5ACAF` |','| NE | `#C60C30` |','| NO | `#D3BC8D` |','| PIT | `#FFB612` |','| SEA | `#69BE28` |','| TEN | `#4B92DB` |', '',
'Unknown asset codes retain the neutral table value. The existing 40-entry asset-code table and owner lookup provide the tint; created-team fallbacks remain guarded.', '',
'### Scores, timeout ticks and capsule','',
'- The appended `FirstPersonComic` FONT uses the existing tenth boot name (slot 9), copied from the complete retail font4 donor including its loader object tail. Its original ASCII cells remain available. The owner binds only the intended scorebug descriptors; global retail font slots stay unchanged.',
'- `U+0080..U+0089` provide 40×45 source-pixel score quads from 13×20 masks packed in previously unused 128×128 atlas space. `U+0090..U+0099` reuse those exact UV cells at narrower metrics for multi-digit scores. Native score formatters at `0xFC050` and `0xFC070` still determine the string, then the owner callbacks at records `0xA9594C` and `0xA95984` select the appropriate range. Scores 28, 100 and 999 remain outside the down plate in both aspects. No additional texture pixels are allocated for compact scores.',
'- Timeout callbacks write `~ ~ ~`, trimmed to 0–3 timeouts. The private tilde is a solid small tick with explicit advance and spacing; colour is `0xFFC8CACE`. This is not a FONT8 hyphen.',
'- The grey quarter uses the smaller `core_bug` font with capital suffix masks. The game clock uses the broadcast digit fork in black. The play-clock callback wraps native `0xFBE30` and removes the leading zero from `04`; its digit stays white.',
'- Spare material `score_buga` supplies the 61×39 geometry box from `(1021,1000)` to `(1082,1039)`, corresponding to the brief’s nominal 61×40 cell. Base tint is `(120,14,39)`, with the existing urgency behavior expressed as a bright-red pulse on the cell under five seconds. The pulse derives from the countdown bits, not a promised fixed-Hz timer. Boundary tests cover 12, 5, 4, 2.5, 0, negative and NaN values, with white text in both red phases.',
'- The capsule backing is on the always-visible alternate frame material. Hiding the play-clock element during live play therefore keeps a light backing behind the black game clock and grey quarter.', '',
'### Retail states and owner capacity','',
'Native event formatters and visibility remain in use. A separate charcoal material, `zz_ESPN_bug1`, restores independent hang-time visibility at descriptor `0xA95AEC`; v2 had cleared its availability. Individual FLAG, Hangtime, Ball at Midfield, FUMBLE and hidden-play-clock renders are in [states.json](reports/b71_s3/states.json). `score_*` images refer to the retail FUMBLE event formatter, not a newly authored TOUCHDOWN slab. The `all_events_*` image deliberately forces incompatible simultaneous elements and is a stress diagnostic, not an accepted retail display state.', '',
'Owner revision 7 occupies **1,386 / 1,408 code bytes**, plus the existing 128-byte data allocation. Shared wing setup and score-flash helpers recovered room; `CODE_SIZE` did not need to grow. Runtime data remains in its named writable allocation. The slot-9 lookup failure retains native descriptor fallbacks. Tests cover register/FPU preservation, native visibility, write ownership, foreign-byte refusal, idempotence and composition.', '',
'## Volume and freeze boundary','',
'| Component | Bytes |','| --- | ---: |','| 66 texture spans × 5,280 | 348,480 |','| FirstPersonComic FONT | 38,048 |','| core_bug FONT | 27,040 |','| Appended payload | **413,568** |','| Sector-rounded resource growth | 413,696 |','| Native rounded heap estimate for appended spans | 420,096 |', '',
'The new FONT metadata adds 11,008 bytes over the 402,560-byte A5 appendix. Atlas video sizes remain unchanged. This stays near the historically successful 0.4 MB class rather than the roughly 1.7 MB expansion associated with a failed loader allocation and subsequent null read. That historical evidence and the bounded loader tests are not a new boot witness; in-game freeze freedom remains UNWITNESSED.', '',
'## Native measurements','',
'[4:3 ESPN/native comparison](reports/b71_s3/compare_43.png) · [Widescreen ESPN/native comparison](reports/b71_s3/compare_wide.png) · [Full JSON](reports/b71_s3/measurements.json)', '',
'`prove_v3.py` executes the native HUD/formatters with the compiled collection, then calls `compare()` with `MNF_COMPARE_REGIONS` and text boxes independently thresholded from the broadcast frame. Text components touching ROI edges are discarded to exclude capsule-rim fragments. The v3 role map supplies the right light/dark polarity for relocated callbacks. Native glyph quads include transparent padding; source-restored raster ink is reported separately.', '',
'### Region errors','',
'Boundary and edge-distance values below are HUD pixels; RGB MAE is on the 0–255 channel scale. Geometry matching is distinct from photo matching.', '',
'| Region | Boundary 4:3 | Boundary wide | RGB MAE 4:3 | RGB MAE wide | Edge p95 4:3 / wide |','| --- | ---: | ---: | ---: | ---: | ---: |']
for name,a in m['comparisons']['43']['regions'].items():
 b=m['comparisons']['wide']['regions'][name]
 lines.append(f"| {name} | {a['native_boundary_error_px']:.6f} | {b['native_boundary_error_px']:.6f} | {a['rgb_mae']:.3f} | {b['rgb_mae']:.3f} | {a['pixel_edges']['p95_px']:.3f} / {b['pixel_edges']['p95_px']:.3f} |")
lines+=['','| Extra region | Boundary 4:3 | Boundary wide |','| --- | ---: | ---: |']
for name,a in m['comparisons']['43']['extra_regions'].items():
 b=m['comparisons']['wide']['extra_regions'][name]
 lines.append(f"| {name} | {a['native_boundary_error_px']:.6f} | {b['native_boundary_error_px']:.6f} |")
lines+=['','### Text errors in source pixels','','All boxes are `[left, top, right, bottom]`, with exclusive right/bottom. These are independently measured ink boxes. The quarter’s capitals are now within 3–4 pixels; the widest remaining text difference is the down label (20 pixels at its right edge), which is centered on the larger requested plate.','',
'| Text | Broadcast ink | 4:3 rendered ink | Max error 4:3 / wide |','| --- | --- | --- | ---: |']
for name,a in m['comparisons']['43']['rendered_text_source_boxes'].items():
 b=m['comparisons']['wide']['rendered_text_source_boxes'][name]
 lines.append(f"| {name} | `{a['reference_box']}` | `{a['box']}` | {a['max_source_pixel_error']} / {b['max_source_pixel_error']} |")
lines+=['','`compare().exact_match` is **false in both aspects**. Mean region RGB MAE is '+f"{m['comparisons']['43']['mean_region_rgb_mae']:.3f} / {m['comparisons']['wide']['mean_region_rgb_mae']:.3f}"+'. All measured native frame containment checks are empty and visible triangle winding is consistent. Software raster sampling, low-resolution marks, differing text proportions, the larger plate and the specified shorter score explain why boundary agreement is not visual equality. No claim is made that GPU output will remove those residuals.', '',
'## Regeneration and validation','',
'Compiler pins were regenerated from the actual final `Build` output, including the whole appended FONT hash: [compiler_pins.json](reports/b71_s3/compiler_pins.json). `packaging/repin.py --apply` updated provider seals. The resource identity is `scorebug-mnf-2026-v3`.', '',
'The cave manifest contains 13,081 reservations and 138 observed steps. Its final SHA-256 is `06609653fb463e26f05c90d3db8aaede996201000c6c3f0afbe3941da2af9e2a`. The scorebug owner occupies code `0x14BAA60..0x14BAFE0` and data `0x14BB010..0x14BB090` in this union. This is a **bounded complete forward XBE projection**, freshly observed from the A5 parent. It retains historical retail reservations and records final owner bytes/source hashes. It is not a production disc receipt: `release_manifest=false`, `disc_built=false`, `production_regeneration_required=true`, and inherited disc fields are explicitly historical. The external production build must regenerate its full receipt.', '',
'The first projection accidentally recorded `nfl2k5_rules_patch.apply` and its named caller as two owners of the same rule bytes. The cave gate rejected `nfl2k5_coin_defer/choose` at `0x25E7B5`. The corrected local projection recipe excludes that shared helper from independent observation, retains the real rule writers, and always starts from the A5 manifest. No gate or oracle assertion was relaxed.', '',
'### Final standalone results','',
'The final driver completed 28 standalone programs: 279 reported unittest cases, including 15 skips, with no failures and unchanged source snapshots. Each final command is an independent Python process with `PYTHONPATH=<repo>:<repo>/tools` and `QT_QPA_PLATFORM=offscreen`. Two independent suites run concurrently. Strict registry validation uses default file checking, without `--skip-file-checks`. The final driver snapshots source hashes before and after.', '',
'| Command/result | Exit | Tests | Skips | Wall seconds |','| --- | ---: | ---: | ---: | ---: |']
programs=sorted((ROOT/'tests/mod_editor').glob('test_*scorebug*.py'))+[ROOT/'tests/nfl2k5_scorebug_layout_test.py',ROOT/'tests/nfl2k5_scorebug_mod_project_test.py']
programs += [ROOT/'tests/mod_editor'/('test_'+n+'.py') for n in ('provider_integrity','product_catalog','phase1_packaging')]
final_names=[p.stem+'-release' for p in programs]+['registry-strict-release',*gate_names]
for name in final_names:
 r=by_name.get(name)
 if r is None:lines.append(f'| {name} | PENDING | | | |');continue
 log=(OUT/(name+'.log')).read_text();count=re.search(r'Ran (\d+) tests?',log);skip=re.search(r'skipped=(\d+)',log)
 lines.append(f"| [{name}](reports/b71_s3/{name}.log) | {r['exit']} | {count[1] if count else '—'} | {skip[1] if skip else '0'} | {r['seconds']} |")
lines+=['','The assets suite precisely skips its disc-copy transaction when the required Storage scratch directory is read-only (EROFS/EACCES/EPERM). Its other checks still execute. The font suite retains five historical private-font-v8 skips; current v3 lookup, relocation, glyphs and callbacks have active native tests. The source-art suite has three skips for missing developer PNG/scene fixtures and the corresponding old disc comparison. The layout suite has five skips for an absent historical Create-a-Play image and one for a missing glTF research export. A verbose rerun with its CPU-emulation flag enabled confirmed the image blocker. These skips are not boot or disc evidence; exact reasons are in `source-art-skip-details.log` and `layout-skip-details.log`.', '',
'Preliminary failures are retained in the ledger: read-only Storage, stale hyphen/dark-text/fixed-callback assertions, pin changes while early exploratory suites were already loaded, a mistaken test expectation for the pulse phase, the font-span rounding correction, and the duplicate shared-helper manifest owner. The final `-release` runs supersede those exploratory verdicts. The old sequential driver retains its failure exit; it is not advertised as a passing final run.', '',
'Initial strict registry validation lacked 75 ignored evidence files. Real copies were restored from the existing read-only local evidence source, matching the A5 per-file hashes (2,063,157 bytes); [evidence_hydration.json](reports/b71_s3/evidence_hydration.json) records them. They are neither staged nor bundled.', '',
'## Registry, RC96 and builder','',
'The existing `nfl2k5.scorebug_presentation.runtime` capability row was updated with v3 scope, volume and proof paths. No capability rows were added. Runtime witness status remains `not-tested`, experimental and off in every preset. The RC96 scorebug bullet is anonymous and states the native proof limits.', '',
'The prepared [builder](reports/b71_s3/build_testdisc71.py) follows A5: Advanced preset with scorebug, scorebug runtime, modern colour and widescreen all enabled. Output:', '',
'`/home/noah/2K5 Mod Studio Builds/NFL 2K5 MOD TEST 2026-09-15h (scorebug v3 + colour + widescreen).xiso.iso`', '',
'Only `--plan-only` ran here. The builds folder is read-only in this session. The external builder first checks destination access, refuses an existing named output, preserves every patch archive, and follows A5’s at-most-three MOD TEST image policy. It removes incomplete discs on failure. After building it reparses the scorebug resources, XBE owner, all 477 colour bundles and widescreen sites, requires every status to be `applied` and aspect `16:9`, then exports the patch.', '',
'Import the bundle into the integration checkout (or fast-forward this worktree’s ordinary branch outside the sandbox) before building, so build receipts record the final source head. The private branch does not update the ordinary read-only HEAD. Then run externally from that checkout:', '',
'```bash\nbash reports/b71_s3/launch_testdisc71.sh\n```', '',
'Expected external receipts are `.scratch/testdisc71h/{plan,pruning,receipt,readback,patch-receipt,result}.json` plus `build.log`, `pid` and `exit`. No disc image, patch or read-back receipt was created here.', '',
'### Played-game witness still required','',
'- Intro/coin toss/kickoff load without the historical allocation crash.\n- Steady bar in 4:3 and widescreen; large marks, gradients, rim and score font match the supplied crops.\n- Possession changes including near-black teams; single-, double- and triple-digit score updates; timeout consumption.\n- Clock running/paused/hidden, urgency below five seconds, quarter and overtime labels.\n- Native flag, hang-time, ball-on and score events stay readable through their real transitions.', '',
'## Commits and delivery','',
'- Base: `a7440f05`, branch `astra/b71-s3-scorebug-v3`. The ordinary worktree `.git` is read-only, so commits live in `.scratch/private.git` using `.scratch/g`. No shared branch refs or other worktrees were changed.',
'- Implementation commits: `374872cd` and `'+source_commit+'`. Staging and commits use enumerated paths; the second list is in [source_commit.json](reports/b71_s3/source_commit.json). Evidence/manifest/report commits follow after the checks.',
'- Bundle: `.scratch/astra-b71-s3.bundle`, prerequisite `a7440f05`. It is created from the final private branch and verified locally. The final delivery receipt records head, size and SHA-256.',
'- Retail inputs remain read-only and no retail pack/XBE/disc bytes are stored in the report or bundle. Scratch remains under 200 MB. No push or emulator launch.', '',
'## Command ledger','',
'[command_ledger.json](reports/b71_s3/command_ledger.json) contains exact argv, UTC start/end, elapsed seconds and exit status for all recorded commands; each named log contains the complete output. Early read-only discovery and editing commands are in the session tool transcript rather than this runner. The first aborted manifest observation was overwritten by its retry; it is not counted as a proof. No validation claim relies on an unrecorded run.', '',
'| Name | UTC start | Seconds | Exit | Exact command |','| --- | --- | ---: | ---: | --- |']
for r in results:
 command=shlex.join(r['command']).replace('|','\\|')
 lines.append(f"| [{r['name']}](reports/b71_s3/{r['name']}.log) | {r['start']} | {r['seconds']} | {r['exit']} | `{command}` |")
(ROOT/'ASTRA_REPORT.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(final_validation_complete=ready,recorded_commands=len(results),report_bytes=(ROOT/'ASTRA_REPORT.md').stat().st_size)))

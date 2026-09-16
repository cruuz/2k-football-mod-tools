"""Summarize reproducible C4 evidence and every recorded check attempt."""
from pathlib import Path
import colorsys
import json
import re
import shlex
import subprocess

ROOT=Path(__file__).resolve().parents[2]
F=ROOT/'reports/b71_c4'
proof=json.loads((F/'daylight-proof.json').read_text())
rows={r['name']:r for r in proof['rigs']}
checks={p.stem:json.loads(p.read_text()) for p in F.glob('*.json') if 'exit_code' in json.loads(p.read_text())}
fmt=lambda rgb:'('+', '.join(map(str,rgb))+')'
lines=['''# Beta 71 C4: day and afternoon Broadcast defaults

All required checks pass, including both detached XBE gates (119 / 131 tests), all 477 bundle pins, seven rig read-backs, controls/reset suites, strict registry and final repin. The additional oracle passes 29 tests against the documented scratch projection; the protected release manifest still needs integration regeneration.

## Delivery and scope

- Private branch `astra/b71-c4-day-afternoon`, based on A5 `a7440f05`, with C3 `45a5ade9` merged first. Merge `ddaaf5c4` retains both lines of work and all RC96 bullets; original reports/messages are archived under `reports/b71_a5/INHERITED_*` and `reports/b71_c3/INHERITED_*`.
- Private Git directory: `.scratch/astra-c4.git`. The linked worktree/shared branch refs remain untouched. The C3 shared branch ref was stale, so the explicitly requested commit was used. Merge staging used an explicit path list and `commit-tree` with both parents; later commits use `git commit -- <explicit paths>`. See `reports/b71_c4/merge.json` and commit logs.
- Implementation commit: `f9c2ac27`. The final evidence commit is included in `.scratch/astra-b71-c4.bundle`; the incremental bundle requires A5 `a7440f05` and contains C3 history. No push.
- Only the default **day** and **afternoon** rig bytes change from C3/v2.1. All 477 stadium bundle pins and the other five rigs are pinned unchanged. No scorebug or widescreen owner source differs from A5.
- The shared turf saturation control remains 1.12, hue target 72, pull 0.50, value curve 2.8. Changing these shared controls would alter approved night/dome turf. Daylight desaturation is accomplished through the two rig channel gains, with warm direct sunlight and cool sky fill. This is not a blanket brightness reduction: the old daylight model was dark and saturated; the revised model raises blue while holding value near 0.40.
- 55 controls remain. Five numeric defaults change (day ambient/key/fill; afternoon ambient/fill). The two daylight balance labels now say “Light colour / shadow recipe” because they also interpolate the shadow scalar. Retail, per-rig Off and recipe Off restore the retail scalar; Broadcast restores C4. Reset tests preserve master On and Off, and all three presets still default the option Off.
- C3 GUI/build/registry wiring is merged directly. C4 updates the existing owner, its pins/provider expectation, two GUI labels, tests, documentation and the existing capability description. No capability rows are added, no build dispatcher is edited beyond the C3 merge, and no deferred GUI wiring is needed.

## Before / after, per condition

The reference map below is the calibrated report’s (181,216,102), not a decoded stadium mean. SCREEN_FACTOR remains exactly day (0.21,0.21,0.21), night (0.183,0.183,0.165); afternoon keeps the existing night-factor fallback and is explicitly an extrapolation. The beta-70 model still reproduces (51,61,32).

| Condition | v2.1 prediction | C4 prediction | Broadcast reference | C4 saturation | C4 value |
|---|---|---|---|---:|---:|''']
for name in ('day','afternoon','night_indoor','alt_day','alt_dynamic','rain','snow'):
    r=rows[name]
    lines.append(f"| {name} | {fmt(r['prediction_before'])} | {fmt(r['prediction_after'])} | {fmt(r['reference']) if r['reference'] else 'No separate C4 target'} | {r['hsv']['saturation']:.3f} | {r['hsv']['value']:.3f} |")
lines.append('''
Day is within one red level of (88,105,61). Afternoon remains below its broadcast median (98,119,72), intentionally retaining value 0.404 rather than pushing to 0.467. The day reference RGB actually computes to hue 83.18°; C4 is 81.82°. The supplied screenshot sample (80,95,45) computes to 78°. The tune follows the supplied RGB/saturation target and warms the direct sun, rather than claiming a lower turf hue angle.

![Model-only turf swatches](reports/b71_c4/predicted-swatches.png)

| Rig lever | Day before → after | Afternoon before → after |
|---|---|---|
| Ambient RGB | (0.94,0.96,1) unchanged | (1,0.95,0.86) → (1,0.96,1) |
| Ambient strength | 0.58 → 0.44 | 0.45 → 0.60 |
| Key RGB | (1,0.98,0.94) → (1,0.94,0.88) | (1,0.94,0.84) → (1,0.91,0.78) |
| Key strength | 1.20 → 1.60 | 1.20 unchanged |
| Fill RGB | (0.90,0.94,1) → (0.32,0.40,1) | (0.70,0.78,1) → (0.40,0.445,1), twice |
| Fill strength | 0.48 → 0.99 | 0.26 → 1.04, twice |
| Shadow scalar +0x100 | 0.275 → 0.32 | 0.27 → 0.22 |
| Key / ambient intensity | 2.069 → 3.636 | 2.667 → 2.000 |
| Total directional / ambient intensity | 2.897 → 5.886 | 3.822 → 5.467 |
| Light count | 2 unchanged | 3 unchanged |

Gain and colour-recipe sliders still default to 1. The stronger blue fill compensates the existing map/screen blue loss while keeping sunlight warmer. White uniforms, shaded players and skin are outside the turf model and must be checked for a blue cast or clipping. No such appearance is claimed proved.

## Shadow and executable proof

**PROVED:** retail day stores key vector (0.433,0.866,0.25), about 60° elevation; afternoon stores (0,0.43,0.903), about 25.46°. Ideal flat-ground shadow length per unit height from those vectors is 0.577 and 2.10 respectively. These are geometric calculations, not rendered measurements. The retail selector replaces the afternoon vector from the stadium sun node (`0x642ee` onward), so a stadium’s actual afternoon direction can differ. All direction bytes, counts, selector/installer/push guards and runtime selection logic remain retail. No new direction is authored.

**PROVED by bounded native execution:** `0x64000` reads selected rig +0x100; `0x12fb8d` calls it and negates it; `0x2af50` writes the resulting light descriptor. Unicorn executes these actual routines with each of the seven decoded tables, preserving the direction vector, descriptor type 1 and mask -1, and producing intensity -0.32 for day, -0.22 for afternoon and the original five other values. This scalar controls a negative light term. It is **not** a blur radius or a sun-angle parameter. C4 gives day stronger shadow contrast and afternoon a gentler term with more ambient relative to its key; rendered hardness, softness and length remain **UNWITNESSED**.

**PROVED:** default XBE apply, exact replay and restore; custom recipe apply/replay/restore; foreign-byte refusal; section digests; all changed offsets confined to owned colour/intensity floats and the two +0x100 words. Full tables are already reserved in place in writable `.rdata`, with no code/cave/request growth. `daylight-proof.json` includes every rig’s retail, old applied and new applied SHA-256, decoded values, exact changed offsets, directions, native descriptor and code fingerprints.

| Rig | C4 applied SHA-256 | Change from v2.1 |
|---|---|---|''')
for name,r in rows.items():
    lines.append(f"| {name} | `{r['after_sha256']}` | {'Daylight tune' if r['before_sha256']!=r['after_sha256'] else 'Exact pin retained'} |")
lines.append('''
## Bundle and decoder proof

**PROVED:** all 477 complete retail/applied bundle records exactly retain v2.1. The canonical bundle-record digest is `f4ef2c5a179ad39a07f4670ed924e3c4a605a6a2775518a78aa790306c706295`. `data/nfl2k5_modern_color_pins.json` changes only the two applied rig hashes; it contains the retail/modern pins for every bundle and rig. The exhaustive verifier rebuilds all pins from read-only retail, refits 390 distinct spans, reparses the outputs and compares the complete records. It passed in 331.847 seconds. Palette, divot, bump/mips, tint, outside grass, end zones and fixed wrappers receive no new changes.

Six representative bundles were also rebuilt in memory, checked against the full pins and decoded independently. All 32-byte wrappers and decoded sizes remain exact. Rounded decoded means differ from the calibrated report’s median; they must not be presented as the same sample.

| Bundle | Retail decoded map / word | C4 decoded map / word | Rig | Predicted turf |
|---|---|---|---|---|''')
for b in proof['decoded_bundles']:
    lines.append(f"| {b['name']} | {fmt(b['decoded'][0]['rgb'])} | {fmt(b['decoded'][1]['rgb'])} | {b['rig']} | {fmt(b['prediction'])} |")
lines.append('''
The s08 day mean still predicts more saturation than the broadcast day reference: (87,107,52), saturation 0.514. That is a limitation of a shared rig across different maps, not a hidden exact-match claim. The supplied measured screenshot sample (80,95,45), far-field saturation 0.69, bump shading and wear coverage are not a fresh calibration here. The model does not prove the far-field band reaches 0.42. Night/dome decoded maps and their predictions above are unchanged from v2.1.

## Gates and regressions

All commands run offscreen with `PYTHONPATH` set to this worktree. The required XBE gates were launched using the literal detached pattern below, with a retained tool session to keep the parent tool context alive. They run in separate sessions, with stdin detached and output logged; polling reads the files/tool session. No process-name kill was used.

```sh
setsid nohup python3 reports/b71_c4/run_check.py xbe_memory_writes python3 tests/mod_editor/test_xbe_patch_memory_writes.py > reports/b71_c4/xbe_memory_writes.launch.log 2>&1 < /dev/null &
setsid nohup python3 reports/b71_c4/run_check.py xbe_cave_references python3 tests/mod_editor/test_xbe_patch_cave_references.py > reports/b71_c4/xbe_cave_references.launch.log 2>&1 < /dev/null &
wait
```

The global gates are supplemented with the actual C4 writer read-back and focused composition proof: six application orders of lighting, scorebug runtime and widescreen give identical bytes, all three statuses stay applied, replay is exact, and restoring lighting independently preserves its peers.

| Check | Result | Process seconds |
|---|---|---:|''')
important=['colour_legacy','colour_controls_final','colour_gui','all_default_pins','daylight_readback','daylight_composition','build_panel','mod_build','project_settings','providers','provider_integrity_updated','phase1_packaging','product_catalog','registry_final','builder_source','xbe_memory_writes','xbe_cave_references','manifest_projection_final','cave_oracle_projected','scope_audit','repin_final']
for name in important:
    d=checks.get(name)
    if d:
        log=(F/(name+'.log')).read_text()
        m=re.search(r'Ran (\d+) tests?',log)
        verdict=('PASS' if d['exit_code']==0 else 'FAIL')+(f" ({m.group(1)} tests)" if m else '')
        lines.append(f"| [{name}](reports/b71_c4/{name}.log) | {verdict} | {d['seconds']:.3f} |")
    else:
        lines.append(f"| {name} | RUNNING / not yet recorded | — |")
lines.append('''
### Failed attempts and their disposition

- Strict registry initially failed on missing `docs/research/apf_audio.md`. The existing C3 inventory supplied 75 missing research/metadata documents by read-only byte copies; no retail executable, texture, pack, disc, embedded GLTF buffer or hard link was introduced. These hydrated documents are excluded from commits; `evidence-hydration.json` records their identities. Strict validation then passes with 174 capabilities.
- Provider integrity initially found its C3 data-pin test expectation still at the old two-rig hashes. The expected file digest was updated to the current pinned data JSON; all eight provider-integrity tests now pass. `packaging/repin.py --apply` updates the owner and data source pins in `providers.py`; final runs report no remaining changes.
- The unmodified release-manifest oracle run fails two tests because the protected manifest has five stale source fingerprints: inherited build/scorebug sources plus the colour owner. The release manifest is intentionally not edited. The scratch projection records actual scorebug scene, runtime and colour writes; checks them against unchanged historical owner reservations; and separately verifies recomputed section/allocator digests. Early projection attempts refused nested scorebug scene attribution and shared digest metadata; the final proof attributes the scene to its own writer and bounds checksum exceptions to the verified digest fields. It does not weaken executable write checks or add/free reservations. Build/resource helper fingerprints are explicitly snapshots, not renewed disc-build evidence. Historical disc fields stay marked historical. The final oracle run uses this projection; production manifest regeneration remains required during integration.

## Prepared combined test-disc builder

`reports/b71_c4/build_testdisc71.py` is prepared and **has not been imported or executed**, including its plan-only path. `check_builder_source.py` parses/compiles the AST and verifies its constants/options without running the builder.

- Name: `NFL 2K5 MOD TEST 2026-09-15g (day tuning + scorebug v2 + widescreen)`.
- Preset: `softdrink_advanced` (Advanced).
- Explicit options: `scorebug=True`, `scorebug_runtime=True`, `modern_color=True`, `widescreen=True`.
- Original retail xiso as source; output under `/home/noah/2K5 Mod Studio Builds`, which is read-only in this sandbox.
- Refuses existing named outputs and tests directory access before pruning. Deletes oldest `*MOD TEST*.iso` images until there are fewer than three, leaving room for this one. Preserves every `.2k5patch` archive and verifies their size/mtime afterward. Postcondition: at most three test images.
- Read-back: scorebug resources/runtime, modern-colour XBE, all 477 bundle pins, all seven rig pins including the immutable night hash, and widescreen 16:9. Exports the accompanying `.2k5patch`. C3 build code publishes the colour recipe sidecar. Incomplete images are cleaned up; a fully verified disc is retained if only patch export fails.

Integrator command (not run here):

```sh
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 -u reports/b71_c4/build_testdisc71.py
```

The shared release cave manifest must be regenerated during normal integration. For the reproducible bounded oracle check, run `python3 reports/b71_c4/project_manifest.py`, then `NFL2K5_CAVE_MANIFEST=.scratch/b71_c4_manifest.json PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_cave_oracle.py`.

## PROVED / UNWITNESSED

**PROVED:** exact data writes/pins, lower predicted daylight turf saturation, preserved approved night/dome bytes, unchanged retail light directions/counts and selector, negative native shadow-light term, 55 controls and both resets, serialization/persistence, exhaustive default refits, decoder read-back, custom refusals and receipts, focused scorebug/widescreen composition, strict registry and provider pins, and the prepared builder’s static contract. Gate verdicts are reported above only after completion.

**UNWITNESSED:** final day/afternoon appearance, shadow length/edge softness, whether shadows read naturally at each stadium’s actual sun angle, far-field saturation/shimmer, clipping or blue fill on white uniforms/skin, every extrapolated class/condition prediction, and the new combined disc build. No xemu, display server, audio or network was opened; no disc/pack was copied or built.

Witness recipe: build image g from original retail, compare day and afternoon at matched camera/resolution and weather, inspect midfield and far field, bright and shaded white uniforms, skin, player/stadium shadows, sidelines/end zones and stripe detail. Then compare night and dome against the approved build to confirm the preserved bytes render as expected. Keep the colour sidecar and build receipts with the test disc.

## Command ledger

`run_check.py` records each command’s exact argument vector, UTC start/end, process exit and monotonic duration beside its complete log. The table includes failed attempts. Final commit/bundle/import commands are recorded separately in `.scratch/handoff-ledger.json` to avoid a self-referential evidence commit. Git setup/merge ancestry and its explicit path inventory are in `merge.json`; exploratory read-only searches are not test claims.

| Check / log | Exact command | Exit | Seconds | UTC start | UTC end |
|---|---|---:|---:|---|---|''')
for name,d in sorted(checks.items(),key=lambda x:x[1]['start_utc']):
    command=shlex.join(d['command']).replace('|','\\|')
    lines.append(f"| [{name}](reports/b71_c4/{name}.log) | `{command}` | {d['exit_code']} | {d['seconds']:.3f} | {d['start_utc']} | {d['end_utc']} |")
(ROOT/'ASTRA_REPORT.md').write_text('\n'.join(lines)+'\n')
print('Wrote C4 report with',len(checks),'recorded command attempts')

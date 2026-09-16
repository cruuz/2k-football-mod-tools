"""Write the S6 handoff from measured proofs and the latest completed checks."""
from pathlib import Path
import datetime,json,re,shlex
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/b71_s6'
rows=sorted((json.loads(p.read_text()) for p in OUT.glob('*.result.json')),key=lambda r:r['start_utc'])
latest={}
for r in rows:latest[tuple(r['argv'][1:])]=r
required=sorted(str(p.relative_to(ROOT)) for p in (ROOT/'tests/mod_editor').glob('test_*.py') if 'scorebug' in p.name or 'scorebar' in p.name)
required+=['tests/nfl2k5_scorebug_layout_test.py','tests/nfl2k5_scorebug_mod_project_test.py']
required+=['tests/mod_editor/test_'+n+'.py' for n in ('provider_integrity','product_catalog','phase1_packaging','mod_build','build_panel_qt','nfl2k5_allocator_scaleout','nfl2k5_xbe_space','xbe_patch_memory_writes','xbe_patch_cave_references','nfl2k5_cave_oracle','nfl2k5_owner_pairwise_composition')]
checks={}
for path in required:
 candidates=[r for r in latest.values() if path in r['argv']]
 if not candidates:continue
 r=max(candidates,key=lambda r:r['start_utc']);log=(OUT/(r['name']+'.log')).read_text()
 ran=re.findall(r'Ran (\d+) tests?',log);skip=re.findall(r'\bskipped=(\d+)',log)
 checks[path]={**r,'tests':int(ran[-1]) if ran else 0,'skips':int(skip[-1]) if skip else 0}
summary=dict(required_suites=len(required),missing_required=[p for p in required if p not in checks],failed_latest=[p for p,r in checks.items() if r['exit_code']],tests=sum(r['tests'] for r in checks.values()),skips=sum(r['skips'] for r in checks.values()),checks=checks)
(OUT/'suite-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
if summary['missing_required'] or summary['failed_latest']:
 print(json.dumps({k:v for k,v in summary.items() if k!='checks'},indent=2));raise SystemExit(1)
proof=json.loads((OUT/'finish-proof.json').read_text());measure=json.loads((OUT/'measurements.json').read_text());owner=json.loads((OUT/'owner-bounds.json').read_text());identity=json.loads((OUT/'projection-identity.json').read_text())
for name in ('previews-sealed','finish-sealed','finish-native-profile','owner-bounds-sealed','compiler-pins-feather','manifest-sealed','projection-identity','builder-final','registry-final'):
 assert json.loads((OUT/(name+'.result.json')).read_text())['exit_code']==0,name
static=max(r['max_hud_error'] for a in measure.values() for r in a['static'].values())
dynamic=max(r['max_hud_error'] for a in measure.values() for r in a['glyphs'].values())
ink=max(r['ink_hud_error'] for a in measure.values() for r in a['glyphs'].values())
text=f'''# Beta 71 S6: sprite scorebug pass 2

S6 corrects the residual logo fringe, possession plate, round ends, rim and wing
finish in the PNG/JSON sprite design and shared texture compiler. The append
remains **323,808 bytes**, exactly S5's total: 34 TXTRs and one enlarged SCNE,
with **zero FONT resources**. The separate light notch brings the quad count to
46 and fits inside existing scene padding. The native owner instructions,
allocator layout and complete stack XBE are byte-identical to S5.

The private branch is `astra/b71-s6-sprite-pass2`, based on S5
`0520e2e1df15818fe86494a13b7c55966d2a039c`. Private Git metadata is in
`.scratch/b71-s6-git`; the shared worktree Git metadata was read only. Delivery
is `.scratch/astra-b71-s6.bundle`. Explicit-path commits and independent bundle
fetch verification are recorded in `.scratch/b71-s6-delivery.json`.

**PROVED:** decoded textures, native loading/owner execution, field coverage,
software raster measurements, freeze-class resource volume and integration
checks. **UNWITNESSED:** console GPU sampling, played intro, live gameplay and
full display appearance. No disc build, xemu session or push was performed.

## Design and cause

1. **Logo edges.** `nfl2k5_scorebug_exact.mnf_panel` previously composited onto
   transparent black, leaving all 1,907 DEN and 1,431 KC zero-alpha panel texels
   with black RGB. The source PNGs themselves have 2,724 and 2,206 black
   transparent pixels. The old RGBA median cut also changed 377 DEN and 393 KC
   opaque texels into partial coverage. It did not make zero-alpha texels
   nonzero; the before diagnostic records zero such changes. Pillow's RGBA
   resize already premultiplies, so black contamination was not proved to arise
   solely in that resize. It survived canvas placement and palette conversion
   into the straight-RGBA bilinear sampling path; faint resampling tails made
   its dashed outline visible.

   `nfl2k5_scorebug_assets.alpha_bleed` extends visible RGB six texels into
   transparent space before resizing and again after placement; `resample_logo`
   explicitly filters RGBa, removes faint ringing and bounds fractional coverage
   to the one-texel silhouette boundary. The atlas packer bleeds each cell too.
   `quantize_alpha_aware` separates transparent, opaque, white-mask and coloured
   feather entries, measures feather colour in premultiplied RGBA, and never
   dithers. It keeps low-alpha white ramps continuous. Both logos now have zero
   changed alpha endpoints and zero feather texels outside that boundary band.
   All palette slots were already resident, so using up to 256 instead of 128
   colours adds no bytes. Historical non-MNF texture authors retain their
   original quantizer. Shared MNF pins were regenerated from the current builder.

2. **Plate and pointer.** `template.png` has a neutral luminance gradient with
   soft inner edge shading and a darker lower lip. The source plate is
   [837,947,1083,983]. JSON's optional `plate_tints` supplies KC's broadcast
   crimson tint; other teams retain their existing primary/secondary choices.
   The [951,942,965,947] pointer is a separate light, untinted, downward notch.
   The measured top and bottom strips below exclude white label ink.

3. **Capsule and play-clock cell.** The left capsule and right red cell are
   filtered to their HUD footprint in the PNG, preserving curved edge coverage
   during bilinear sampling. Their boxes stay [839,999,1019,1039] and
   [1019,999,1082,1040]. Both decoded end masks are vertically symmetric, have
   transparent corners, full centre coverage and a feather. The red fill is
   (215,0,51). The digit's [1042,1009,1057,1028] ink target and anchor 1049.5
   stay fixed. Comparing the isolated native digit to the full bar loses **zero
   coverage** at both aspects: no other material clips it. Its native centre
   error is below 0.003 HUD px. No owner draw-order patch was needed.

4. **Body and wings.** The body keeps the r=8 silhouette, gains a stronger
   two-source-pixel top rim over the soft highlight, reaches charcoal near
   (37,37,37) in the middle and retains its dark two-pixel bottom rim. Wing
   masks fade by (1-x)^1.5; their top alpha admits the rim and their bottom alpha
   admits the dark border. Both decoded P8 column profiles are monotonic from
   the outer team colour to body colour, with no inner seam. Additional columns from the actual native raster, with
   logos/text hidden only for that diagnostic, have zero channel reversals at
   both aspects. Black-background
   crops isolate the new rounded corners from the screenshot's existing rails.

5. **Widescreen and states.** The native 27/32 x contraction is retained and
   undone for display-restored comparisons. Logo, round-end and corner quads
   have the same restored dimensions at both aspects within
   {proof['display_proportions']['max_source_pixel_difference']:.6f} source pixels.
   Every S5 state was rerendered: DEN/KC, NO/DEN, scores 0/7/28/100, 0:07,
   play clocks 3/4/12, all downs, OT, Inches, Goal, timeouts 0..3, FLAG, FUMBLE,
   hang time, ball on, score slabs and hidden play clock. The ordinary bar uses
   no FONT draws. Event callbacks and their inherited formatting remain; FUMBLE
   hides the play-clock digit and the score slabs leave sprite scores attached
   to the root. These are native state fixtures, not played-game captures.

## Measured comparison

| Region | ESPN RGB | S5 RGB | S6 RGB |
| --- | --- | --- | --- |
'''
for name in ('plate_top','plate_bottom','body_top_rim','body_highlight','body_middle','body_bottom_rim','red_cell'):
 r=proof['plate_and_rims']['43'][name]
 text+='| '+name+' | '+' | '.join(str(r[k]) for k in ('reference','s5','s6'))+' |\n'
text+='''
The exact sample rectangles and the separate 16:9 measurements are in
`finish-proof.json`. Frame/JPEG rim samples include the photograph's rail
placement and tinted reflection; they are not substituted for the requested
neutral design colours. The sprite render remains softer than the broadcast
photograph at the native 640x480 HUD sampling limit. The legacy RGB comparator
continues to report a mismatch; no pixel-identical claim is made.

| Logo | Mean dark RGB sampling error, S5 | S6 | S5 95th percentile | S6 |
| --- | ---: | ---: | ---: | ---: |
'''
for team in ('DEN','KC'):
 r=proof['logos'][team];text+=f"| {team} | {r['before']['mean_dark_rgb_error']:.3f} | {r['after']['mean_dark_rgb_error']:.3f} | {r['before']['p95_dark_rgb_error']:.3f} | {r['after']['p95_dark_rgb_error']:.3f} |\n"
text+=f'''
This samples decoded P8 with straight versus premultiplied bilinear filtering
at identical fractional positions; it isolates dark sampling error, not a
photographic similarity score. The extra hidden-RGB ablation preserves every
alpha byte while replacing zero-alpha RGB, separately demonstrating that cause.
The source marks remain 64x64; this pass does not invent higher-resolution detail.

Standard static boundaries: **{static:.6f} HUD px** maximum error. Dynamic
boundaries: **{dynamic:.6f} HUD px**. Visible glyph ink: **{ink:.6f} HUD px**.
All visible fields across 50 captures remain within their boxes with maximum
containment error **{owner['field_containment']['max_hud_error']:.6f} HUD px**.
Setup/update recorded {owner['setup']['writes']} / {owner['update']['writes']}
writes and zero writes outside the allowlist. Native tests preserve GPRs, flags,
x87, MXCSR and XMM state, call displaced routines once, reparse all resources,
retain retail HUD bytes and refuse foreign code/data/resources. The custom
PNG/JSON design proof still changes position, size and colour with identical
owner instructions.

## Review artifacts

- [ESPN / S5 / S6 at 4:3, 2x](reports/b71_s6/espn_s5_s6_43_2x.png)
- [ESPN / S5 / S6 at 16:9, 2x](reports/b71_s6/espn_s5_s6_169_2x.png)
- [All 50 state/aspect crops](reports/b71_s6/states_contact_sheet.png)
- [DEN edges at 4x](reports/b71_s6/DEN_edge_compare_43_4x.png) and [16:9](reports/b71_s6/DEN_edge_compare_169_4x.png)
- [KC edges at 4x](reports/b71_s6/KC_edge_compare_43_4x.png) and [16:9](reports/b71_s6/KC_edge_compare_169_4x.png)
- [Decoded wing column profiles](reports/b71_s6/wing_column_profiles.png)
- [Clean background, 4:3](reports/b71_s6/clean_background_43_2x.png) and [16:9](reports/b71_s6/clean_background_169_2x.png)
- [Day background, 4:3](reports/b71_s6/day_43.png) and [16:9](reports/b71_s6/day_169.png)
- [Decoded P8 atlas](reports/b71_s6/atlas.png), [finish measurements](reports/b71_s6/finish-proof.json), [native geometry/ink](reports/b71_s6/measurements.json)

The ESPN/S5 comparison and both disc-i shine screenshots requested in the brief
were opened and reviewed. Screenshots used as preview backgrounds are preserved;
any uncovered pixels of an earlier bar remain visible. The separate black
background proof avoids that confound when reviewing the new rims and corners.

## Resource and integration proof

| Component | Count | Bytes each | Total |
| --- | ---: | ---: | ---: |
| Team logo TXTR | 32 | 5,280 | 168,960 |
| Neutral logo TXTR | 1 | 2,208 | 2,208 |
| P8 atlas TXTR, 256x512 | 1 | 132,256 | 132,256 |
| Scene with layout | 1 | 20,384 | 20,384 |
| FONT | 0 | 0 | 0 |
| **Append** | **35** | | **323,808** |

Native heap-rounded sum: 327,168 bytes. Sector pack growth: 323,584 bytes.
The hard sprite limit is 400,000 bytes; the oversized profile refusal is tested.
This is a freeze-class volume proof, not a witnessed intro peak-memory trace.

Provider pins and legacy compiler pins are regenerated. Provider integrity,
product catalog, phase1 packaging and strict registry validation run without
skipping file checks. The 75 inherited private evidence inputs were verified as
independent copies against their inventory (2,063,157 bytes); they are not in
commits or the bundle. The existing runtime registry row includes S6 evidence;
no capability rows were added. The RC96 bullet and design documentation describe
the finish and retain experimental, off-by-default and UNWITNESSED status.

The cave projection observes the complete current writer stack. It seals
{identity['source_seals']} current source files, preserves every S5 allocation,
and produces the same stack XBE SHA-256:
`{identity['stack_xbe_sha256']}`.
Both XBE gates, cave oracle and owner-pair matrix were run detached against the
final seals even though owner instructions did not change. Duplicate historical projection payloads were compacted below the 8 MiB
reader bound; the complete top-level write ledger, reservations, source seals
and XBE identity were proved unchanged. The projection is
explicitly not a release-disc receipt; inherited disc fields remain historical
and production regeneration is required when a disc is built.

`reports/b71_s6/build_testdisc71.py` is prepared with disc m's
`softdrink_advanced` plan and the five enabled options: scorebug,
scorebug_runtime, modern_color, modern_arrowhead and widescreen. Its name is
**NFL 2K5 MOD TEST 2026-09-16n (sprite scorebug pass 2 + everything)**.
`verify_builder.py` imports and checks the immutable plan without calling the
builder. The builds directory is untouched. No disc or patch export was run.

## Completed checks

All **{summary['required_suites']} required suites** have passing latest results:
**{summary['tests']} tests, {summary['skips']} explicit skips**. Missing: none.
The skips retain their exact reasons in the suite logs; they cover historical
retired mechanisms, unavailable private developer inputs and read-only storage
for a full-disc transaction. Native sprite loading, owner, raster and geometry
checks are not skipped. Gameplay, intro and GPU appearance still require a
played witness at both aspects, including possessions, timeouts and all events.

| Check | Tests | Skips | Seconds | Exit |
| --- | ---: | ---: | ---: | ---: |
'''
for path,r in sorted(checks.items()):text+=f"| [{Path(path).stem}](reports/b71_s6/{r['name']}.log) | {r['tests']} | {r['skips']} | {r['seconds']} | {r['exit_code']} |\n"
text+='''
## Exact detached command ledger

`run_logged.py` starts each command in a new process session, captures its log
and waits in a supervisor. The tool yields while it runs, so progress remains
visible. An initial orphan-only launch did not survive the sandbox's process
namespace lifetime; it produced no proof and was replaced with this supervised
detached pattern. No process-name kill was used. Times below are UTC. Source
reads and short authoring edits were not benchmark runs; final Git commands and
bundle verification are in the private delivery receipt.

Failed and superseded attempts remain visible: an initial import-path fix, one
one-level RGB rounding expectation, the initial sampling-error threshold,
stale shared-MNF pins, and projections that correctly refused source edits
during observation. The final checks use regenerated pins and current source
seals. Native/XBE tests and strict registry file checks remain enabled.

| Log | Started UTC | Seconds | Exit | Exact argv |
| --- | --- | ---: | ---: | --- |
'''
for r in rows:
 command=shlex.join(r['argv']).replace('|','&#124;').replace('\n','\\n')
 text+=f"| [{r['name']}](reports/b71_s6/{r['name']}.log) | {r['start_utc']} | {r['seconds']} | {r['exit_code']} | `{command}` |\n"
text+='\nASTRA_DONE\n'
(ROOT/'ASTRA_REPORT.md').write_text(text)
print(json.dumps({k:v for k,v in summary.items() if k!='checks'},indent=2))

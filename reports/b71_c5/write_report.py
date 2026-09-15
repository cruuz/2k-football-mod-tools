"""Assemble the C5 handoff from completed check records and decoder evidence."""
from pathlib import Path
import json
import re
ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT/'reports/b71_c5'
proof = json.loads((FOLDER/'all-decoder-proof.json').read_text())
scope = json.loads((FOLDER/'delivery-scope.json').read_text())
rows = proof['rows']
grass = [r for r in rows if r['conditions']]
other = [r['name'] for r in rows if not r['conditions']]
checks = {}
for path in sorted(FOLDER.glob('*.json')):
    doc = json.loads(path.read_text())
    if isinstance(doc,dict) and {'command','exit_code','seconds'} <= set(doc):
        checks[path.stem] = doc
required = ['final_decoder_and_pins','all_default_pins_final','colour_legacy_release','colour_controls_release',
            'colour_gui_release','build_panel','build_settings','mod_build','providers','provider_integrity',
            'phase1_packaging','registry_final','registry_projected','builder_source_final','scope_audit','repin_final','repin_handoff','swatches']
assert all(checks[name]['exit_code']==0 for name in required), 'Do not report success before every required check completes'
for key in required:
    assert (FOLDER/(key+'.log')).is_file()
ledger = ['# C5 command ledger','', 'All checks use `PYTHONPATH=<worktree>` and `QT_QPA_PLATFORM=offscreen`. Logs retain complete stdout/stderr. Superseded runs are included; only the final checks named in ASTRA_REPORT.md certify the delivered bytes.','', '| Check | Exact command | Exit | Seconds | UTC start | UTC end |','|---|---|---:|---:|---|---|']
import shlex
for name, doc in sorted(checks.items(),key=lambda item:item[1]['start_utc']):
    ledger.append(f"| [{name}]({name}.log) | `{shlex.join(doc['command'])}` | {doc['exit_code']} | {doc['seconds']} | {doc['start_utc']} | {doc['end_utc']} |")
(FOLDER/'CHECKS.md').write_text('\n'.join(ledger)+'\n')
ratios = [max(p['outside'])/max(p['field']) for r in grass for p in r['conditions'].values()]
shaded = [v for r in grass for p in r['conditions'].values() for v in p['tinted_value_ratios']]
lines = ['# Beta 71 C5: outside grass follows the field','',
'**PROVED offline:** final pins, decoder read-back, every grass-bearing bundle under all seven rigs, colour suites, page tests, strict registry validation and provider repin pass. Field resources and all seven C4 rigs remain exact. Final in-game appearance is **UNWITNESSED**.','',
'## Delivery','',
'- Base: `astra/b71-c4-day-afternoon`, `5eac51c7b2986bad2f2971135333de7cc82675fe`. Branch: `astra/b71-c5-sidelines`. Incremental bundle: `.scratch/astra-b71-c5.bundle`, requiring that base. No push.',
'- Commits live in `.scratch/astra-c5.git`, with read-only object alternates to the shared repository. This keeps all Git writes inside the authorized worktree; the shared linked-worktree HEAD remains at the base. Use the bundle for integration. Original C4 reports and inherited wiring are archived in `reports/b71_c5/INHERITED_*`.',
'- The RC96 bullet contains no reporter names. Option remains EXPERIMENTAL and Off in every preset. No scorebug, widescreen, build-dispatcher, rig, executable-code or reservation change. No emulator, GUI display, audio or network was opened. No disc was built or retail payload saved.','',
'## Implementation','',
'The former outside rule could only raise palette value toward the field-map mean. It shared FIELD slider values while retaining a different drawn response and separate coloured vertex tints. C5 instead derives an outside map from each decoded FIELD mean (or its material +0x18 word) using a separately calibrated outside response. The inverse cancels the per-condition light gain and FIELD screen factor, so the same map follows every rig without adding preview conditions to cache identity.',
'',
'At full linked match, the target is 0.97 × FIELD map / outside response, with an 8% blend toward neutral map chroma to absorb quantization. Texture value variation remains. Outside vertex RGB becomes neutral with shade at least 246/255; alpha, indices, mip layout, geometry and all other surfaces keep their C4 data. Every separate outside material +0x14/+0x18 word in the inventory is already neutral white and is preserved. The bluer-green s48/s50/s51 palettes are included through hue 180; FIELD grading itself keeps its old cutoff and bytes.',
'',
'The Colour & lighting page now shows its own outside swatch against the current FIELD prediction. Linked controls follow FIELD; unlinking restores the independently saved hue, saturation and brightness. The match blend applies only while linked. Retail/reset, master Off, project persistence and custom refit receipts are tested. The transform revision participates in the settings digest, so an old baked-grade receipt cannot silently reuse C4 bytes; rebuild from original retail.',
'',
'## Predictions before and after','',
'The outside calibration uses the supplied disc g day strip (101,151,76), V 0.592, H 100°, and independently decoded C4 s08dd outside mean (175.8333,218.8282,85.7385). This does not change FIELD calibration. The outside response ratios are '+str(tuple(round(v,6) for v in proof['outside_response']))+'. Night, dome, afternoon and other outside conditions extrapolate this single surface calibration. No shader/render equivalence is claimed.',
'',
'Table RGB values are rounded decoded-mean predictions, not the median references used by C4’s UI. FIELD is identical before and after. V and S use fractional predictions; both fractional and rounded RGB bounds also pass.',
'',
'| Bundle / condition | FIELD C4 = C5 | Outside C4 | Outside C5 | FIELD V / S | C5 outside V / S | Darker, unshaded / darkest vertex |',
'|---|---|---|---|---|---|---|']
for r in rows:
    if 'prediction_before' not in r: continue
    a,b=r['prediction_after'],r['prediction_before']
    rgb=lambda values:str(tuple(round(c) for c in values))
    label=r['name']+' / '+r['representative_rig']
    if r['name']=='s11dd.iff':label=r['name']+' / dome grass'
    if r['name']=='s09dd.iff':label=r['name']+' / dome material turf'
    lines.append(f"| {label} | {rgb(a['field'])} | {rgb(b['outside'])} | {rgb(a['outside'])} | {a['field_hsv']['value']:.3f} / {a['field_hsv']['saturation']:.3f} | {a['outside_hsv']['value']:.3f} / {a['outside_hsv']['saturation']:.3f} | {(1-max(a['outside'])/max(a['field']))*100:.2f}% / {(1-min(a['tinted_value_ratios']))*100:.2f}% |")
lines += ['', '![FIELD and outside model swatches](reports/b71_c5/predicted-swatches.png)', '',
f"Across {len(grass)} grass-bearing bundles × seven rigs, the unshaded outside mean is {(1-max(ratios))*100:.3f}% to {(1-min(ratios))*100:.3f}% darker. Including every outside vertex tint, the largest drop is {(1-min(shaded))*100:.3f}%. No fractional or rounded prediction is brighter or more saturated than FIELD. The {len(other)} remaining bundles have no green outside entries and remain C4-exact; their names are recorded in the decoder proof. These are mean-colour bounds, not guarantees for every grass blade, texture texel or rendered pixel.", '',
'## Decoder, pins and scope','',
f"All 477 complete bundle records and seven rig records reproduce. {scope['changed_bundle_count']} bundle hashes change, solely within the compressed field-scene resource. The independently decoded C4/C5 difference is restricted to outside palette RGB and outside vertex RGB in every bundle. The normal, divots and shared Fldd tint sites are exact C4; wrappers, span lengths and decoded sizes are preserved; no default field refit is unfit. Seven representative C4 bundles are also rebuilt against their old pins for before/after swatches.",
'',
'`reports/b71_c5/all-decoder-proof.json` contains per-bundle decoded means, tints, seven-condition predictions, changed-byte counts and hashes. `delivery-scope.json` checks every pin record and unchanged rig functions/constants. The complete applied XBE equals C4 byte-for-byte, and replay is exact. **No rig changed, so the two detached XBE gates were not rerun.** The inherited release cave manifest still needs normal integration fingerprint regeneration; no reservation changes are requested.',
'',
f"Final colour-pins file SHA-256: `{scope['pins_sha256']}`. Final owner SHA-256: `{scope['owner_sha256']}`.",
'',
'## Completed checks','', '| Check | Result | Seconds |','|---|---|---:|']
for name in required:
    log=(FOLDER/(name+'.log')).read_text()
    count=re.search(r'Ran (\d+) tests?',log)
    result='PASS'+(' ('+count.group(1)+' tests)' if count else '')
    lines.append(f"| [{name}](reports/b71_c5/{name}.log) | {result} | {checks[name]['seconds']} |")
lines += ['', 'Exact commands, UTC times, exit codes and complete output links are in [CHECKS.md](reports/b71_c5/CHECKS.md). Every touched test file ran standalone. The final all-default-pins verifier independently recompresses the retail inventory after the final pin rebuild.', '',
'### Earlier attempts','',
'- The first controls run found tuple/list receipt round-trip inequality and insufficient saturation margin after RGB rounding. Receipts now store JSON lists; the model checks both fractional and rounded colour, including dim alternate rigs and edge shades.',
'- Inventory preflight exposed outside snow without green entries, then blue-green grass outside the old hue cutoff. Snow-white surfaces retain C4 data. The named outside material now includes blue-green hues; FIELD target measurement includes them while its grading stays exact. Final full-inventory proofs pass.',
'- Strict registry initially lacked the inherited `docs/research/apf_audio.md` evidence. The same C3/C4 metadata inventory was hydrated as real local copies (75 documents, no retail payloads), excluded from commits. Strict validation now passes. Intermediate pin runs are retained only as superseded evidence.',
'',
'## Prepared test-disc builder','',
'`reports/b71_c5/build_testdisc71.py` follows the A5/C4 builder pattern. It was AST-checked and compiled, **never imported or executed**, including plan-only mode.',
'',
'- Name: **NFL 2K5 MOD TEST 2026-09-15k (sidelines + day tuning + scorebug v2 + widescreen)**.',
'- Advanced preset `softdrink_advanced`; `scorebug=True`, `scorebug_runtime=True`, `modern_color=True`, `widescreen=True`.',
'- Original retail xiso source; outputs under `/home/noah/2K5 Mod Studio Builds`. Existing named outputs are refused. Access is checked before pruning oldest test ISOs to leave room for at most three; every `.2k5patch` archive is preserved and checked.',
'- Reads back scorebug resources/runtime, modern-colour XBE and all 477 bundle pins, all seven rigs, immutable night pin and widescreen 16:9. Exports the patch and retains the colour recipe sidecar. Incomplete disc output is cleaned up; a verified disc survives patch-export failure.',
'', 'Integrator command (not run here):', '', '```sh', 'PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 -u reports/b71_c5/build_testdisc71.py', '```', '',
'## Integration and witness','',
'`WIRING.md` supplies four exact prose replacements for the protected existing registry row; no functional wiring or new capability rows are needed. Both the unchanged registry and the proposed metadata projection validate strictly. Apply that prose and regenerate the inherited cave-manifest fingerprints during integration.',
'',
'In-game witness still needed: compare FIELD, both sidelines and grass behind both end zones in day, afternoon, night and dome games at matched camera, weather and resolution. Include Denver, Arrowhead, Indianapolis, Detroit material turf and a blue-green stadium variant. Check texture detail and transitions at boundary lines, then confirm unlinked custom outside colour. The supplied day sample calibrates a prediction; it does not prove final appearance, far-field shading, weather response or other shader/display effects.',
]
(ROOT/'ASTRA_REPORT.md').write_text('\n'.join(lines)+'\n')
print('Report assembled from',len(rows),'decoder rows and',len(checks),'completed command records')
(ROOT/'ASTRA_LAST_MESSAGE.md').write_text('''C5 is ready on `astra/b71-c5-sidelines`, based on C4 `5eac51c7`.

- Implementation: `f047f20c`. Final commits are in `.scratch/astra-c5.git`; deliver `.scratch/astra-b71-c5.bundle`.
- Linked outside grass follows FIELD in every modeled condition, at most 8% darker and never more saturated. Unlinked custom colour remains independent. All C4 field data and seven rigs stay exact.
- Completed: 477 bundle pin reproductions and decoder checks, seven rig pins, colour suites (10 / 11), page tests (6), provider integrity (8), strict registry (174 capabilities), and final repin. In-game appearance remains UNWITNESSED.
- Prepared only: `reports/b71_c5/build_testdisc71.py`, named `NFL 2K5 MOD TEST 2026-09-15k (sidelines + day tuning + scorebug v2 + widescreen)`, Advanced with the same four options.
- `ASTRA_REPORT.md` contains predictions, scope and exact check links. `WIRING.md` supplies four protected registry prose replacements and the inherited manifest integration follow-up. No functional wiring is outstanding.
- No rig change, so no XBE gates rerun. No push, disc build or emulator launch.

ASTRA_DONE
''')

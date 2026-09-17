"""Assemble the evidence and exact persisted command ledger; never build a disc."""
from pathlib import Path
import json,shlex,re,subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
rows=sorted((json.loads(p.read_text()) for p in OUT.glob('*.result.json')),key=lambda r:r['start_utc'])
audit=json.loads((OUT/'scene_byte_audit.json').read_text())
sequence=json.loads((OUT/'native_sequence.json').read_text())
last={}
for r in rows:
 if len(r['argv'])>1 and r['argv'][0]=='python3' and r['argv'][1].startswith('tests/'):
  last[r['argv'][1]]=r
checks=[]
for path,r in sorted(last.items()):
 log=(OUT/(r['name']+'.log')).read_text();m=re.search(r'Ran (\d+) tests?',log);skip=re.search(r'OK \(skipped=(\d+)\)',log)
 checks.append(dict(path=path,**r,tests=int(m[1]) if m else None,skips=int(skip[1]) if skip else 0))
(OUT/'validation.json').write_text(json.dumps(dict(checks=checks,failed=[r['name'] for r in checks if r['exit_code']],total_tests=sum(r['tests'] or 0 for r in checks),total_skips=sum(r['skips'] for r in checks)),indent=2)+'\n')
(OUT/'commands.json').write_text(json.dumps(rows,indent=2)+'\n')
body='''# Beta 71.1 S10: native visibility correction; played root cause unresolved

**PROVED:** the sprite owner incorrectly treated pending event requests as draw visibility. The corrected owner uses native binding/slide visibility, including event fade-out. **The proposed lost draw-path clear is disproved in the bounded native sequence. This is a validated visibility correction, not proof that the persistent in-game blank label has been fixed.** The actual values in the witnessed blank frame remain unavailable. A history counterexample below prevents an unconditional claim that every pre-snap state must display down text in the current compact event layout.

Branch `astra/b71-s10-down-label-cause`, based on `a3f18036230e386c63b26ee7ec95606753d7eea8`. Commits use explicit file paths in `.scratch/astra-b71-s10.git`; the worktree's original Git administration and HEAD remain untouched. Bundle: `.scratch/astra-b71-s10.bundle`, with that S9 head as prerequisite. No push, emulator, GUI, network, disc build, retail mutation, full pack/disc copy or global process-name kill was performed. Heavy commands use `run_logged.py`: the child starts in a new session and its supervisor remains alive until the time/exit receipt is written. Scratch remained below 200 MB. No subagents were used.

Read: `ASTRA_CONTEXT.md`, `BETA71_TRIAGE.md`, S9's root report (retained in `reports/b71_s10/INHERITED_S9_REPORT.md`), the S5 report at `reports/b71_s6/INHERITED_ASTRA_REPORT.md`, `FABLE_B71_S8_REPORT_2026-09-16.md`, the C owner, Python dispatch/static writer, compiler, renderer and retained disassemblies. The specific S10 brief authorizes scorebug edits despite the older context's general exclusion. The supplied image names were absent from this worktree; their copies in `/home/noah/Desktop/2K5-8 Editors/beta71_evidence/` were inspected read-only. The local `disc_n_1.png` copy shows a kickoff formation; the other supplied capture clearly shows a blank plate at the line. This does not dismiss the pre-snap witness.

## A: every identified request writer, and why hiding a material does not lose a clear

USA XBE virtual addresses. The six element records have canonical origins `0xA959C8 + i*0x70`; their names/material names sit at origin minus 8/minus 4. Indices: 0 down, 1 play clock, 2 hang time, 3 FLAG, 4 ball-on, 5 FUMBLE. Score slabs have separate score-animation records at `0xA9594C` and `0xA95984`; they are not additional owners of these four event request words.

Full executable-section Capstone census plus unaligned raw-reference census: `writers.log`, `writer_references.json`, `scan_writers.py`. All direct request constants resolve into FC9C0. The only additional writers in the HUD's record aliases are the startup loop and timer loop below. This is an audit of the pinned executable and known record aliases, not a proof against arbitrary memory corruption.

| Word | Retail direct writer PCs | Condition / value |
|---|---|---|
| `A95AE0` hang time | `FCB14` | Sets 1 for play kind 10, subphase 14, no flag condition. |
| | `FCB2B` | Clears if the fumble slide is above its closed position in that path. |
| | `FCBA4`, `FCBEF` | Clear on the special kind-12 branch and general branch respectively. |
| `A95B50` FLAG | `FCACC` | Writes the computed boolean every nonzero game phase: play object `+160`, or valid nonempty `+90` record indicated by `+98`. Both absent writes zero. |
| `A95BC0` ball-on | `FCB67` | Clears on the kind-10/subphase-14 path. |
| | `FCBD0` | Sets 1 for kind 12, phase != 3, subphase 12/13, no flag. |
| | `FCC40` | Sets 1 when general down conditions permit and `BA2F14` is set, or recent histories differ during subphase 12/13. |
| | `FCC53` | Clears when those conditions do not request ball-on. |
| | `FCCBD` | Sets 1 when the final `ABE90` query is true. |
| `A95C30` FUMBLE | `FCC77` | Tentatively sets 1 in subphase 14 with the FLAG slide closed. |
| | `FCC7F` | Clears when that predicate fails or play object `+198` is zero. Early kind-10/kind-12 branches do not visit this writer. |
| `A95A00` down | `FCB37`, `FCC48` | Clear on the kind-10 live branch or failed general down predicate. |
| | `FCBAA`, `FCC28` | Set 1 on the eligible kind-12 or general scrimmage branch. |

General retail down predicate at `FCBDD..FCC48`: FLAG and FUMBLE slides are closed, `E602FC & 0x8000` is clear, game phase `E602B4 == 4`, subphase `E602B8 != 14`. The eligible kind-12 branch is an explicit exception. Phase zero returns before rewriting these words. Floating comparisons are executed natively in the sequence.

The shipped scorebar-v3 tail is also audited, not confused with retail. It binds `EBP=A95BB0` and keeps event semantics at relocated PCs:

| Word | Shipped PCs (value) |
|---|---|
| hang time | `FCAFB` (1); `FCB0F`, `FCB3C`, `FCB56` (0) |
| FLAG | `FCACA` (computed 0/1) |
| ball-on | `FCB15`, `FCBA4` (0); `FCB42`, `FCB9C`, `FCBD6` (1) |
| FUMBLE | `FCBBF` (1); `FCBC7` (0) |
| down | `FCBDC` (1 at the common nonzero-phase finalizer) |

See `disasm-shipped-visibility.log`. That existing static tail forces the middle's down/play-clock requests on; S10 does not change it.

Three common request-writing instructions apply to **all six** elements:

- `FCD5D`: startup initializes `[EDI+3C]` to zero (`EDI=A959C4+i*70`). This runs during scene binding. `FCD69/FCD77` set/clear binding availability from node/material lookup success.
- `FCEF6`: the update loop sets `[ECX-18]` to 1 while a timed request is active (`ECX=A95A18+i*70`) and the binding is available.
- `FCF19`: clears that request when elapsed time reaches the deadline; `FCF1C` clears the timer flag. `FC730` only schedules it, writing timer flag/elapsed/deadline at `FC739/FC743/FC74D`. No formatter or draw call is required.

The slide integration and material hidden-bit write at `FCF1F..FCF8C` consume the request. They run before the hooked FC9C0 call at `FCFA2`. Material hidden bits do **not** gate this update. Binding availability does gate the timer/integrator; all six bindings are available in the shipped-scene native sequence. Re-materialing hang time onto the spare slab preserves this path. `FC360` submits the scene and walks text elements but writes none of these request words. The formatters do not clear them either.

`timers_literals.json` executes native FC730/FCE70 for each of the six records and observes every timed request clear at `FCF19` **without any draw call**. `baseline_sequence.json` runs the pre-fix shipped scene/owner through kickoff, ball-on, pre-snap and flag: after the gameplay latch is cleared and native predicates stop requesting the event, the request words clear and down glyphs return. Therefore A's specific “hiding stopped a retail draw clear, causing a permanent stale request” mechanism is not reproduced and is inconsistent with the traced code.

`disc_n_native_bindings.json` independently repeats a bounded 225-frame sequence with **disc n's actual XBE, appended scene and textures**, read directly from its ISO without exporting those retail inputs. Its installed owner is byte-identical to the pinned S9 owner at its actual allocation; both hook targets are verified. Static HUD/widescreen replay is asserted byte-identical. The audit normalizes only those verified hooks in a validation copy; executed owner/hook bytes stay intact. All six bindings remain 1 throughout kickoff, ball-on, recovery, FLAG and recovery. Both pre-snap recoveries yield `[1,1,0,0,0,0]` and five white down glyphs. The first attempt was refused by the baseline harness's deliberate installed-hook guard; the corrected probe explicitly verifies the installed owner before using it. This proves that even disc n's actual hidden/re-materialed scene does not lose a draw-path clear under these inputs. It remains a HUD fixture with supplied world predicates, not captured gameplay.

## B: A95A00 is a request, not visibility

`A95A00` is down record `A959C8 + 38`, the requested target for the animation update. It is neither a material-hidden bit nor binding availability. Its writers are listed above. The binding is `A95A20` (`+58`); the current slide is float `A95A04` (`+3C`); closed is float `A959F4` (`+2C`); open is `A959F8` (`+30`). The callback is `A959CC` and material pointer is `A95A0C`.

The retail text draw gate at `FC3C0..FC3D5` checks binding availability and compares **current slide to closed position**, not the request. Its callback call is at `FC416`. The corrected regression observes entry to that actual native branch independently of the owner's code. The shipped static tail's `FCBDC` forces A95A00 to 1 in a nonzero phase, so a static override making it false cannot explain a normal phase-4 blank frame. No sprite setup/static override writes it to zero. Native startup, timer expiration, or phase-zero retention are distinct, documented cases. Hiding a material does not change A95A00.

## C: a missed history input, and the causal limit

`FC330` sets `BA2F14`; `FC340` clears it; setup `FC1B1` also clears it. Caller `A09F7` tail-calls FC330 when `[ESI+38] != [E60288]`; `9F4BA` tail-calls FC340 after its gameplay transition work. These calls are independent of the HUD draw path. The main sequence calls the real latch entry points, with the higher-level world scheduling explicitly outside the fixture.

There is a second ball-on source. `FCA4A..FCA7F` compares the two latest valid history records at `+20`. `A7940` reads the latest index from `B6FF64`; `A7970` checks the five-slot ring's sequence identity at `B6E7F0 + (index%5)*4B0` and returns its data at `+10`. Earlier previews replaced the history count with zero.

`history_probe.json` restores and executes the **real A7940/A7970 readers** with sampled ring entries. With different team values, a cleared BA2F14, phase 4/subphase 12, the shipped native path repeatedly yields `[1,1,0,0,1,0]`. FC360 enters both down and ball-on elements and formats `Ball at Midfield`. With equal history values, the requests become `[1,1,0,0,0,0]` and five down glyphs return. This is an omitted fixture input, not a lost clear. The snapshot field's actual values during the witnessed blank frame have not been supplied.

The native formatter produces `Pregame`/`Overtime` in phase 0, `Safety Kick` in 1, `Kickoff` in 2, `Point After` in 3, and `1st & 10` in phase 4. Non-down literals have no label tokens and deliberately emit no down glyphs. No alternate phase-4 literal was discovered; the numeric/Inches/GOAL sweep below exercises the real formatter. These observations do not prove that the witnessed game's phase was correct.

A separate pre-existing formatter limitation appeared in the initial sequence's default 13:10 clock: source 5 calls FC100, which returns an empty string for times >=600 seconds (`FC10B..FC138`); retail uses FC150 for that range. The final sequence uses a five-minute period matching the supplied capture. This observation is not a down-label cause and S10 does not alter the clock formatter.

**Root-cause status: UNPROVED for the persistent played symptom.** The old owner's request-based early return is a proved defect, but both a held latch and differing history entries also legitimately keep an event drawable. The corrected compact layout still prioritizes that visible event. It would be false to claim this change guarantees down text in every imaginable pre-snap state, or that it reproduces the witness of a blank plate with no event text. Resolving that remaining distinction needs the blank frame's phase/subphase, history indices/values, six requests/slides/bindings, native event draws, and live down quad colours/UVs. No speculative request clear or guessed phase timeout was added.

## Implemented correction

- `tools/scorebug_sprite/runtime.c`: `element_visible()` implements FC360's binding/current-slide gate. Its negated `<=` also retains the native unordered floating comparison behavior. Down uses its own computed visibility; event suppression uses the same computed gate for indices 2–5. The owner no longer reads the four event request words to decide down visibility and never clears gameplay requests.
- The compact layout keeps the S5 event replacement policy: drawable events occupy the down plate. Pending-but-closed or unavailable events no longer suppress it; closing events keep it hidden until their current slide is closed. This is deliberately distinguished from raw retail's ability to draw down and ball-on at separate positions.
- `mod_editor/core/nfl2k5_scorebug_sprite.py`: down's table visibility address changes from request `A95A00` to binding `A95A20`. The C slide check completes the native gate. Runtime revision becomes 10; generated engine and provider hashes are regenerated.
- S9 submission order, equal sprite depth, atlas/UVs, preview renderer, custom-layout ordering and layout JSON remain intact. The only scene byte change is its binding-address byte at `0x4244`.

The first candidate relied solely on event plates covering the down glyphs. A differential raster found 66 changed pixels underneath ball-on at 4:3 because the plate has translucent pixels. That candidate was corrected to use computed event visibility before the final owner commit. The first direct C-engine regression also exposed a test caller ABI mistake (cdecl arguments were not popped); its native caller was corrected. The failed logs remain in the ledger, along with the initially mistyped prepared-builder function-name check. The initial suite supervisor retains its nonzero aggregate result from the old C-caller test; the corrected final per-suite receipts are authoritative. Failed intermediate runs are not counted as passing validation.

## Final native sequence and images

`native_sequence.json`: one retained machine per aspect, 14 stages × 65 frames × two aspects = **1,820 native update frames**, with per-frame requests, slides, bindings, colours and request-writing PCs. No request/slide/binding/material/colour word is reset between stages. Native FC330/FC340 latch calls and sampled gameplay fields/predicate returns drive the transitions. This is a bounded HUD sequence, not a full kickoff/physics/AI simulation.

Sequence: kickoff/hang-time, ball-on, deliberately held-latch pre-snap counterexample, latch-clear recovery with downs 1–4, FLAG, recovery with downs 1–4, FUMBLE, recovery. On both aspects, settled event stages have zero label glyphs/pixels; recovery stages have five white glyphs. FC360's actual element branch and native event formatter output are captured. A differential raster removes only down colours and compares otherwise identical frames, establishing visible down contribution versus hidden event states. The history counterexample is retained separately, not silently converted into a passing pre-snap state.

| Stage | Requests [down,clock,hang,flag,ball,fumble] | Final down glyphs | Down pixels, 4:3 / 16:9 |
|---|---|---:|---:|
'''
for i in range(len(sequence['stages'])//2):
 a=sequence['stages'][i];b=sequence['stages'][i+len(sequence['stages'])//2];assert a['name']==b['name']
 row=a['frames'][-1]
 body+=f"| {a['name']} | `{row['requests']}` | {row['visible_glyphs']} | {a['down_changed_pixels']} / {b['down_changed_pixels']} |\n"
body+='''
- [50-state contact sheet](reports/b71_s10/states_contact_sheet.png), regenerated with the final owner.
- [Post-kickoff 1st down, 4:3](reports/b71_s10/after_kickoff_down_1_43_display.png) / [16:9](reports/b71_s10/after_kickoff_down_1_169_display.png).
- [Post-FLAG 4th down, 4:3](reports/b71_s10/after_flag_down_4_43_display.png) / [16:9](reports/b71_s10/after_flag_down_4_169_display.png).
- [FLAG, 4:3](reports/b71_s10/flag_43_display.png) / [16:9](reports/b71_s10/flag_169_display.png).

The separate final sweep covers four downs × numeric distances 0–99 plus four GOAL states, at both aspects (808 states), using the native formatter and owner. `label_sweep.json`, `states.json` and `volume.json` retain receipts. CPU execution plus a software raster is **PROVED** within the stated fixture. Actual GPU behavior and the played fix are **UNWITNESSED**.

## Integration and prepared disc

**Both owner and scene bytes changed.** Owner RX allocation stays 4,096 bytes; RW stays 128 bytes. No new hook, allocation, literal, static XBE write site or reservation is introduced. The generated C engine and wrapper emission change; the scene's one-byte table change occurs at both aspects. All 34 texture chunks, raw material records, command descriptors/buffers, geometry, glyph metrics and S9 order remain identical to a3f18036. Appended resources remain 323,808 bytes, zero appended FONT, one 20,352-byte decoded scene and 47 quads. Exact hashes/ranges are in `scene_byte_audit.json`.

'''
body+=f"Owner `code_for(0,0)` before SHA-256: `{audit['owner']['before']}`; after: `{audit['owner']['after']}`. Changed owner bytes at this relocation: {audit['owner']['changed_bytes']}.\n\n"
body+='''`build_runtime.py --check` passes; toolchain versions are in `toolchain-gcc.log` and `toolchain-ld.log`. Compiler pins were regenerated; retained legacy compiler pins do not change. Provider hashes were updated with `packaging/repin.py --apply` before each code commit.

**Hotfix integration must regenerate the cave manifest and rerun the manifest/XBE memory-write/cave-reference/pairwise gates on the integrated tree.** S10 intentionally leaves the protected manifest unchanged. Its source-fingerprint audit reports changed runtime, sprite compiler and generated engine. This job does not claim those combined-tree gates passed. No capability row, protected GUI, build dispatcher or packaging-check edit was needed.

`reports/b71_s10/build_testdisc71.py` is prepared, AST/syntax checked, and **was not imported or run**. Its plan function is AST-identical to S9's, retaining Advanced plus scorebug/runtime, modern colour, modern Arrowhead and widescreen. Name: **NFL 2K5 MOD TEST 2026-09-16q (down label cause fix)**. The requested name does not change the evidence status: this is still a candidate with an unresolved played cause. Evidence paths use b71_s10. No disc/patch archive/build-folder operation occurred.

## Validation and command ledger

The table lists the latest result per standalone suite, including all scorebug/scorebar suites, the root layout/project suites, provider integrity, product catalog, phase1 packaging, build/Qt and allocator/space checks. Earlier runs importing the intermediate owner were rerun against final sources. Precise skips are retained in individual logs.

'''
body+=f"Latest suite results: {len(checks)} suites, {sum(r['tests'] or 0 for r in checks)} tests, {sum(r['skips'] for r in checks)} explicit skips; failed latest suites: {[r['name'] for r in checks if r['exit_code']]}.\n\n"
body+='| Suite log | Tests | Skips | Seconds | Exit |\n|---|---:|---:|---:|---:|\n'
for r in checks:body+=f"| [{r['name']}](reports/b71_s10/{r['name']}.log) | {r['tests']} | {r['skips']} | {r['seconds']} | {r['exit_code']} |\n"
body+='''
Exact persisted experiment/check/commit commands follow, with UTC start, elapsed seconds, exit code and full logs. `commands.json` additionally records UTC end times and argv arrays. Exploratory navigation/read commands at session start were not separately timed; no fabricated timings are supplied. The initial un-supervised detached launch did not survive its sandbox session; the writer census was rerun under the retained supervisor and has a complete receipt.

| UTC start | Seconds | Exit | Command | Log |
|---|---:|---:|---|---|
'''
for r in rows:
 command=shlex.join(r['argv']).replace('|','\\|')
 body+=f"| {r['start_utc']} | {r['seconds']} | {r['exit_code']} | `{command}` | [{r['name']}](reports/b71_s10/{r['name']}.log) |\n"
body+='''
Final evidence/report commits and bundle creation/verification are recorded in `.scratch/delivery_commands.json` and `.scratch/delivery.json`, so the report does not contain its own commit or bundle hash. The delivery performs an independent fetch into another private Git directory and checks that its head equals the delivered branch.

## Remaining witness / unresolved requirement

Do not mark the sustained played-game missing-label cause solved from this bundle. The native sequence proves request clearing and the corrected computed-visibility contract, but it does not prove the unknown live inputs of the reported frame. In particular, a valid visible ball-on event can coexist with retail down visibility during pre-snap; the compact replacement layout intentionally prioritizes that event. Thus the brief's unconditional “label visible on every pre-snap down” is **not proved** for all native inputs. The history probe is the concrete counterexample. A captured blank-frame state or a separately specified change to that event replacement policy is required to close the causal gap. No emulator was opened to manufacture a witness.
'''
(ROOT/'ASTRA_REPORT.md').write_text(body)
print('Report and ledgers written. Root cause remains explicitly unproved.')

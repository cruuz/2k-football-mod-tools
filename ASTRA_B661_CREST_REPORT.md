# Beta 66.1 H5: crest imports and fixed compressed-art budgets

Branch: `astra/b661-crest`, based on `9e4bc5d4`. Implementation commit:
`f24b8273` (`Beta 66.1: fit crest masks to fixed budgets and preview PS3 imports`).

Aszemple, #2k8-bugs, 2026-09-11: “I have imported PS3 Logos I've done, some work
but other some to prevent from getting applied ... not sure why as they are all
the same size.” He named “Giants, Colts, Dolphins, Browns, Bears” and supplied
the slot-92 / outer-621 refusal, “exceeds its fixed outer allocation by 23562 bytes”.
I read `ASTRA_CONTEXT.md`, triage row 25 and `CREST_MEASUREMENT.md` before editing.

## What changed

The crest writer keeps the outer allocation and location fixed. It first tries
its existing greedy H7A encoder, then the field-art writer's reviewed optimal
encoder. If the import permits simplification, it tries 8, 4 and 2 shades for
each RGB region independently, with greedy then optimal at each level, stopping
at the first fit. Only changed layers are simplified. Alpha bytes are retained;
mips regenerate from that step's simplified layer. The six region masks never
merge or mirror. Streams must decode exactly and every match must satisfy
`length <= distance`; the selected IFF passes the existing independent reparse
and payload-ownership gate before output is returned.

`compress_h7a_best` delegates binary acceptance and invocation to the existing
reviewed field-art implementation, including platform, regular-file, symlink,
link-count, size, permission, hash and timeout checks. It also explicitly checks
non-overlap before accepting the result. The binary was not edited or chmodded:
mode **0755**, one link, 14,472 bytes, SHA-256
`9061866e31f1a2930eceaa4fb8652ef1b7aa9b04cbce0174cc0eae125f8e49ab`.
Its diagnostic reported `available: true` on this Linux x86_64 run.

PS3 mapping computes budgets and compressed sizes in the existing task worker,
with per-pair and per-shade progress. The in-memory caches key measurements by
pixel hash and exact preserved layout, and compressed streams by decoded VRAM
hash and shift. All 118 retail destinations reduce to two measured layouts:
52 use shift 8 and 66 use shift 9; their writable spans have zero preserved
seed bytes. Grouping is proved by masking only the bytes the writer overwrites,
including exact mip addresses, rather than assuming another package's padding.
The row reports unchanged fit, shade reduction, or the byte shortfall. Combo
choices show slot numbers and budgets. Tooltips and plan receipts list packages
with room. “Choose packages with room” changes checked rows only when clicked;
the roster crest index must still match the selected slot. Staging rechecks the
live destinations, pixel hashes and fit before making any session changes.
Endzone-only review skips crest measurement.

PS3 mapping and Team Art crest replacement enable shade reduction by default.
Both expose an explained checkbox; `allow_simplification` is stored with each
crest's project metadata, survives Save/Open, and can be set false to refuse
reduction. Old project records without the key use the default true. Direct
writer APIs, including `build_patch_rgba_batch`, retain a strict default and
accept `allow_simplification=True`. Full-shell migration keeps that strict default.

Receipts retain source hashes, actual output hashes, layer and mip evidence,
footer checks, and fixed-allocation details. The new `fit` records every attempted
size, the selected encoder and shades, and a complete status sentence. Build
progress, the completed-build message, and its saved receipt carry that sentence.
The single-crest build now retains package and cache component receipts too.
The linked logo cache receives the same simplified masks without overwriting
the project's original PNGs. A synthetic reversed inner-file order caught and
fixed an existing single-layer receipt bug: sibling preservation now resolves
`logo_l1` by name, not a fixed file index.

No protected implementation file needed wiring. All product changes are in the
owned APF studio and `tools/apf_logo_patch.py`; the existing `WIRING.md` is unchanged.
The existing capability and release paths remain sufficient. Repin was run last
before the implementation commit and reported `applied 0 pin update(s)`.

## Reporter evidence and exact outcomes

Read-only bundle:
`/home/noah/Desktop/2K5-8 Editors/discord-dump-2026-09-11b/attachments/2k8_aszemple_NFL_Logos_Textures.zip`.
The bundle and retail volumes were opened for reading. No reporter pixels,
retail pixels, PNGs, rebuilt packages or compressed streams were committed.
Tests synthesize their own art and IFF headers. Scratch receipts contain
metadata, hashes and numbers only; no full disc or copied volume was built.

The preflight measured the five named teams against all 118 crest destinations,
then ran `build_patch_rgba(..., allow_simplification=True)` for each against slot
92 / outer 621 and slot 23 / outer 301. Every successful package was rebuilt and
independently reparsed in memory. Predicted shades and bytes exactly matched the
writer result; the refused rows matched the writer's final required-byte counts.
The measured run took **1006.157 seconds**, including source/bundle decoding,
both H7A layouts, fit attempts and ten package builds/refusals.

Slot 92's compressed-art budget is **48,609 bytes**; slot 23's is **165,345 bytes**.
These are stream budgets, excluding the IFF header, preserved DRAM, footer and
20-byte H7A header. Equal DDS lengths therefore do not decide fit. Different
H7A shifts also explain why a team's unchanged stream can have a different size
in slot 23 than in slot 92.

| Team | Slot 92 result | Compressed bytes | Encoder | Slot 23, unchanged, greedy |
| --- | --- | ---: | --- | ---: |
| New York Giants | Fits at 8 shades | 37,246 | greedy H7A | 77,681 |
| Indianapolis Colts | Refused at 2 shades; 1,814 over | 50,423 | safe optimal H7A | 67,850 |
| Miami Dolphins | Refused at 2 shades; 17,396 over | 66,005 | safe optimal H7A | 102,051 |
| Cleveland Browns | Fits at 2 shades | 48,003 | safe optimal H7A | 85,642 |
| Chicago Bears | Fits at 4 shades | 46,499 | greedy H7A | 58,318 |

Exact successful slot-92 status strings:

```text
Logo slot 92: 16 shades reduced to 8 per region to fit 48,609 bytes; 37,246 used
Logo slot 92: 16 shades reduced to 2 per region to fit 48,609 bytes; 48,003 used
Logo slot 92: 16 shades reduced to 4 per region to fit 48,609 bytes; 46,499 used
```

Exact slot-92 refusals:

```text
This crest package holds 48,609 bytes of compressed art; this logo needs 50,423 at 2 shades. Choose a package with room (for example Logo slot 23, 85, 28) or flatten the art.
This crest package holds 48,609 bytes of compressed art; this logo needs 66,005 at 2 shades. Choose a package with room (for example Logo slot 23, 85, 28) or flatten the art.
```

The numeric example in the task was illustrative. The measured Browns result
needs optimal H7A at two shades: greedy uses 48,974 bytes; optimal uses 48,003.
On a platform without the reviewed helper, those measured greedy bytes remain
365 over slot 92's budget. Windows/macOS use the supported greedy fallback;
a native Windows or macOS build was not run. Giants and Bears use greedy at
their successful shade level and do not need the helper for that fit.

The unchanged Giants needs 75,249 bytes in slot 92, versus 37,246 at eight shades.
Bears needs 52,620 unchanged, versus 46,499 at four. The writer stops at those
first fits rather than reducing them further. The original staged art remains
available if Aszemple chooses another package or refuses simplification.

Commands used for reporter checks:

```bash
PYTHONPATH=.:tools python3 /tmp/h5_reporter.py > /tmp/h5-reporter.log 2>&1
PYTHONPATH=.:tools python3 /tmp/h5_reporter_final.py > /tmp/h5-reporter-final.log 2>&1
```

The first script calls `read_bundle`, `destination_slots`, `measure_bundle_logos`,
`logo_fit_row` and `build_patch_rgba`. The second starts a fresh process and calls
the committed writer directly with the same five decoded pairs and two entries.
It completed in **599.837 seconds**. A comparison of the two metadata receipts
reported `REPORTER_PLAN_WRITER_MATCH: 10/10 cases; 8 exact output SHA-256 matches;
2 exact refusals`. The committed writer SHA-256 for the fresh run is
`d50f2146ddb5edfb0c1fed65e21b2b953af7eb0c5e0160bdd4600091cd9ca222`.
Local metadata receipts are `/tmp/h5-reporter-results.json` and
`/tmp/h5-reporter-final-results.json`. They are not release inputs.

Reproduce the direct writer calls without those local scripts:

```python
from pathlib import Path
from mod_editor.apf_studio.ps3_texture_bundle import read_bundle
from mod_editor.apf_studio.backend import ensure_tools_importable
ensure_tools_importable()
import apf_logo_patch as writer

bundle = read_bundle(Path("/home/noah/Desktop/2K5-8 Editors/discord-dump-2026-09-11b/attachments/2k8_aszemple_NFL_Logos_Textures.zip"))
index = Path("extracted/All-Pro Football 2K8 (USA)/0A")
teams = {"New York Giants", "Indianapolis Colts", "Miami Dolphins", "Cleveland Browns", "Chicago Bears"}
for pair in bundle.pairs:
    if pair.kind != "logo" or pair.team not in teams:
        continue
    for slot, outer in ((92, 621), (23, 301)):
        try:
            result = writer.build_patch_rgba(index, *(layer.image.tobytes() for layer in pair.layers),
                                            entry_index=outer, allow_simplification=True)
            print(pair.team, result.manifest["fit"]["status"])
        except writer.PatchError as exc:
            print(pair.team, slot, str(exc))
```

## Verification commands and output

All commands ran from this worktree. Qt ran offscreen. The synthetic fit suite
uses full 512x512 generated art, actual encoders, authored IFFs, byte-sized
budgets selecting each ladder rung, explicit overlap rejection, retained alpha,
independent decode, reparse corruption refusal, source hashes, the batch path,
and cache reuse. The budget/import suite covers per-row predictions, missing
measurements, opt-out, explicit destination changes, worker execution, refusal
before staging, saved project policy, coupled cache inputs and final build text.

| Command | Output |
| --- | --- |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_logo_patch.py` | `Ran 18 tests in 122.467s`; `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_logocache_patch.py` | `Ran 14 tests in 123.344s`; `OK` |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_team_art.py` | `Ran 10 tests in 85.129s`; `OK` |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_team_art_qt.py` | `Ran 6 tests in 0.177s`; `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_ps3_texture_bundle.py` | `Ran 28 tests in 70.560s`; `OK` |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_ps3_texture_bundle_qt.py` | `Ran 4 tests in 0.473s`; `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_crest_fit.py` | `Ran 10 tests in 247.069s`; `OK` |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_crest_budget_import.py` | `Ran 12 tests in 0.438s`; `OK` |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_helmet_crest_design_product.py` | `Ran 13 tests in 1.162s`; `OK` |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_team_logo_gui.py` | `Ran 23 tests in 2.291s`; `OK` |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_package_map_writer.py` | `Ran 40 tests in 2.031s`; `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_all_crest_slots.py` | `Ran 15 tests in 0.788s`; `OK` |
| `PYTHONPATH=. python3 tests/mod_editor/test_apf_helmet_logo_regions.py` | `Ran 12 tests in 4.795s`; `OK` |
| `PYTHONPATH=. python3 tests/apf_h7a_no_overlap_test.py` | `Ran 4 tests in 18.952s`; `OK` |
| `PYTHONPATH=. python3 tests/apf_h7a_optimal_is_bounded_test.py` | `Ran 4 tests in 31.992s`; `OK` |
| `PYTHONPATH=. python3 tests/apf_logo_patch_test.py --report /tmp/h5-logo-roundtrip.json` | `APF_LOGO_ROUNDTRIP_PASS entry=36 file=1 copied_volume=false report=/tmp/h5-logo-roundtrip.json` |
| `PYTHONPATH=. python3 tests/apf_logocache_patch_test.py --report /tmp/h5-logocache-roundtrip.json` | `APF_LOGOCACHE_ROUNDTRIP_PASS catalog=1 copied_volume=false report=/tmp/h5-logocache-roundtrip.json` |
| `python3 packaging/repin.py --apply` (last before implementation commit) | `applied 0 pin update(s)` |
| `git diff --check` | No output; exit 0 |
| `stat -c '%a %h %s' tools/apf_h7a_optimal` | `755 1 14472` |

The optimal fallback negative test intentionally mocks the binary predicate;
its logged “reviewed SHA-256 mismatch” warning is from that mock, not the actual
bundled binary. Offscreen Qt emitted ordinary `propagateSizeHints` warnings.
Neither warning was a test failure. The full-copy options were not run.

## PROVED and UNWITNESSED

**PROVED offline:** the pinned logo/cache contracts remain green; each accepted
candidate round-trips, has no overlapping H7A matches, stays inside the original
allocation and reparses to the intended blocks. Generated-art tests retain the
six channels and alpha, regenerate mips, preserve untouched layers, keep source
hashes and exercise the batch route. The saved policy, worker boundary, table
rows, explicit remapping, build text and coupled cache inputs pass offscreen
or headless product tests. The reporter measurements and in-memory writer
results above are observed, not estimates from DDS size.

**UNWITNESSED:** Aszemple's simplified crest on an actual helmet, at close and
normal gameplay distances, after a complete built game is launched. No emulator,
gameplay, GUI display, audio, network, full disc build, native Windows/macOS
execution, or hardware test ran. This work does not prove which runtime surface
samples the package versus the linked cache. The quality change is intentional
and disclosed; acceptability of the simplified edge detail is Aszemple's witness.

## What Aszemple must witness

1. In PS3 mapping, choose the intended crest slot and leave shade reduction on.
   Giants in slot 92 should predict eight shades and Bears four. On the tested
   Linux helper path, Browns predicts two. Build the complete game and retain
   the receipt showing the exact reduction and bytes above.
2. Point the roster's crest selector at that same slot. For Colts or Dolphins,
   explicitly choose a roomy slot such as 23 and update the roster selection to
   match; the importer does not silently redirect an existing index of 92.
3. Launch that built game and check the crest **on the helmet**, including a
   close view and normal gameplay distance where smaller mips are used. Check
   the six palette regions, edge detail and absence of the previous team's
   detail artwork. Report the platform, chosen slot, receipt status and a
   helmet capture. A mapping row or successful build alone is not this witness.

The final follow-up also corrects the Team Art action's lookup of saved crest
metadata (`package_modifications(package, session.modifications)`). An additional
offscreen test opens that action and verifies both restored and forwarded
opt-out state. All 12 budget/import tests and all 6 Team Art dialog/browser tests
pass after that correction. The PS3 guide's obsolete GUI-handoff note is removed.

No H5 wiring handoff is outstanding. The remaining acceptance step is this
in-game witness, not another allocation expansion or package move.

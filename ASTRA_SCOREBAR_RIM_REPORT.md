# r64 scorebar rim, 2026-09-08

**EXPERIMENTAL / UNWITNESSED.** The default static v3 bar now selects each
outline from the same live retail team as its panel. A primary that differs
from the panel fill is retained; otherwise the retail secondary is used.
An indistinguishable secondary, absent team/code or unknown palette uses
silver (`FFD1D2D3`). The down pill, clock cells, neutral centre and decorative
timeout marks do not inherit team tint.

Base: `45c0544a`, branch `astra/r64-scorebar-rim`. Noah's September 7 disc-bh
witness establishes that the preceding v3 bar was good apart from its
silver-left/red-right rim. It does not witness this revision. This work used
bounded retail XBE/archive reads and native CPU fixtures only. No game,
console emulator, GUI display, audio, network, full disc/pack copy or push.
Qt checks ran offscreen. No protected file was edited.

## PROVED: source and scene decision

The installed rim comes from `nfl2k5_scorebug_exact.atlas()`: its generated
24-by-24 tile explicitly paints silver on the left and red on the right.
It does **not** come from the shipped v10 template's PNG layers. The white
mask now occupies atlas x=24..47, y=0..23. It can therefore take material tint
without multiplying a team's colour by the old Raiders/Texans painting.
The original tile remains available to the existing diagnostic scene.

The former alternate full frames become the independent left/away and
right/home outlines. Their existing material indices are 7 and 9. Panel
indices remain away=10 and home=6. Both modes use both halves; only two
existing three-byte visibility instructions change, `FC285` and `FC305`,
from `OR EAX,1` to `AND EAX,FFFFFFFE`. No material lookup or entry work is added.
The CPU projection audit measures the union of the two halves as the frame.

The clock material's previously collapsed final quad supplies a neutral
backing. Its clock quad and text retain their positions. The unused second
corner-mark material supplies both decorative timeout strips, now sampling
an independent white mask. Their overall spans remain; fitting their three
marks to the small atlas introduces about 0.10 to 0.12 RGB MAE inside the
panel regions compared with v3. They remain decorative, not live counters.
The index strips, vertex/material/command counts, strings and 16,512-byte
decoded scene size are unchanged. Every submitted visible triangle has the
expected winding, including the newly used neutral geometry.

The explicit-folder v10 contract is byte-identical: all PNGs, layout.json,
palette catalog, XBE output, scene and atlas are unchanged. Only the template
README explains the distinction. No PNG-layer split or Studio panel change
was necessary. Both document-model and offscreen-page tests open/save/reopen
the template byte for byte; the existing template and release-catalog suites
validate the output and reviewed assets.

## PROVED: callbacks, colours and ownership

The same `FC010`/`FC030` abbreviation callbacks get the live team contexts,
copy/uppercase the live name and select the two material words for that side.
The primary accessor is `68D70`; its secondary counterpart is `68DC0`.
Both use the same pinned 80-row table and case-insensitive asset-code lookup.
Asset codes are strings, not table row indices; native reads establish the
Texans colours below. The full table remains SHA-256
`0713d8ca89333142d86dad04904d4804ea76687301a50df7265b5407302036e6`.

| Team | Retail primary | Retail secondary | Panel | Rim |
| --- | --- | --- | --- | --- |
| BAL | 0xff31145c | 0xff101010 | 0xff31145c | 0xff101010 |
| JAX | 0xff0c586d | 0xff03031b | 0xff0c586d | 0xff03031b |
| MIN | 0xff422259 | 0xffffffff | 0xff422259 | 0xffffffff |
| NYJ | 0xff253f36 | 0xffffffff | 0xff253f36 | 0xffffffff |
| LV | 0xff101010 | 0xffd1d2d3 | 0xff101010 | 0xffd1d2d3 |
| HOU | 0xff061638 | 0xffab253c | 0xff061638 | 0xffab253c |
| ATL | 0xff101010 | 0xffb51441 | 0xff101010 | 0xffb51441 |
| GB | 0xff006419 | 0xffe0b02a | 0xff006419 | 0xffe0b02a |

The table contains both opaque colour words in all 80 rows. There is no
supported row with a missing primary but a present secondary. The host
selection rule also handles that case by using the supplied secondary.
In the pinned native path, an absent palette has neither word, so it uses
silver. The native accessor's unknown-code blue is excluded from rim
selection, and the proof confirms that sentinel is absent from real primary
rows. Distinct dark retail secondaries, such as BAL black and JAX navy, are
retained deliberately; their physical visibility still needs Noah's check.

The existing `FCA87..FCCCC` ownership remains exactly **581 bytes**:
363 for visibility, 181 for the colour helper at `FCBF2`, and 37 for the
play-clock helper at `FCCA7`. Reusing a saved EBP as the native descriptor
base and compacting equivalent conditionals makes room. The original
visibility prefix, including zero EDI, is now explicitly hash-guarded.
The secondary accessor and complete frame-material updater are also guarded.
The checked-in assembly reproduces all 581 bytes exactly.

Native fixtures prove register restoration, live team changes without scene
reload, two bounded material writes per callback, unchanged other-side and
centre materials, and fresh table resolution after the scene table changes.
Null/wrong scene tables suppress stores. Visibility writes are traced to the
same seven existing native state words or the caller stack. No writable
runtime data enters .text; there is no new owner, cave, allocation or cached
team/material pointer. The existing all-owner stack already composes this
static writer in both directions, so no allocator/manifest owner list changes
are needed. The new native secondary call and complete visibility instructions
are included explicitly in the cave gate's existing static-owner assertions.

The actual renderer reads the callback-written material `+18` and emits its
28-byte shader-constant command. The fixture verifies ARGB channels divided
by 510 and no duplicate command when unchanged. This proves the CPU command
boundary, not GPU execution. As in v3, mesh submission precedes abbreviation
callbacks: a new scene starts with neutral panels and silver outlines, and
the next draw uses the live colours. A reused scene may show the old pair for
one draw; no loading hook was introduced to remove that delay.

## Forecasts and comparator scores

[comparison.png](docs/scorebug_ingame/rim/comparison.png) shows pinned v3
and the rim forecast for BAL at JAX, MIN at NYJ, LV at HOU, live MIN at NYJ,
ATL at GB, a Raiders mirror match and missing codes. Individual frames and
full native geometry are in
[forecasts.json](docs/scorebug_ingame/rim/forecasts.json).
[colours and command evidence](docs/scorebug_ingame/rim/colors.json) records
both native colour-word read addresses and material submissions.

The old compiler and callbacks are independent, hash-pinned fixtures copied
from this base. They reconstruct the preceding v3 XBE
`5ec31f2351d6e0257b978ca577585161cf44b2f76cd85fce183e75a8a13f46fd`
and scene span
`7b072c04b9d35f59a5645ce196cd209238ff5426d657e5bae43de6e26a5f7a35`.
This is a real previous build, not a negative control made by hiding new nodes.
Old-v3 and mixed-version application refuse before mutation; current replay
is byte-identical. The explicit-folder v10 pins still pass independently.

The existing five-region v3 comparator uses the same historical LV/HOU
broadcast photograph and unchanged thresholds. These are mean regional RGB
MAE values on a 0..255 scale; lower means closer to that particular photograph.
Team-aware outlines intentionally differ from its baked silver/red rim.
The static bar's live abbreviations and fonts also differ from the photograph;
**no exact photographic-match claim is made**. Text submissions, including
all positions, colours, fonts and glyph vertices, are identical to v3 in all
seven cases. The centre-pill and clock-strip v3-to-rim RGB MAE is exactly zero.

| Forecast | V3 broadcast MAE | Rim broadcast MAE | Identical text draws |
| --- | ---: | ---: | --- |
| bal_at_jax | 66.861623 | 72.670682 | True |
| min_at_nyj | 62.546720 | 68.444438 | True |
| lv_at_hou | 67.577831 | 70.156974 | True |
| live_min_at_nyj | 62.415971 | 68.313688 | True |
| atl_at_gb | 69.745166 | 73.078033 | True |
| lv_mirror_secondary_silver | 68.568942 | 72.409092 | True |
| missing_codes_silver | 67.323399 | 71.166603 | True |

Reproduction:

```sh
python3 -m tools.nfl2k5_scorebar_rim_witness \
  --extraction '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)'
```

## Fixed-span receipts and validation

[receipts.json](docs/scorebug_ingame/rim/receipts.json) contains the complete
retail/replacement instruction bytes and a read-only real-disc preflight.
It plans exactly three writes: XBE at 2,396,160 (11,948,032 bytes), SCNE at
1,741,675,264 (4,832 bytes), and atlas at 1,741,540,432 (2,432 bytes).
**Zero real-disc writes were performed.** Temporary test fixtures were cleaned
by their context managers; no acceptance disc or archive copy was left behind.

| Generated output | SHA-256 |
| --- | --- |
| Static XBE | `13502211c0798bb0373ef500865af3b3238d68ec77276b058773e392d37a7e85` |
| Static SCNE span | `0588f2f49a0f3cf40ae179dd34d1a57b25748dbc993df34b020153fcd124d8cf` |
| Static atlas span | `01a30410e9147f5669614fbe6fa59e0066e5defa39c7d7fae325098f51dd39f6` |
| Decoded static SCNE | `2d48ab3d3876a9e533a213c4cd22d181dc64a74f9292e5ed1a3fdd53e913de93` |
| Diagnostic HUD containing the shared atlas | `39d5d95e08e993802fc2e8bb723e69c832c28a356b81b50282cf58cf2ef04b7b` |

Complete 32-byte retail wrappers and their 16-byte overlap-scratch declaration
are preserved. Host/native decompression and fixed-span replay pass. The
resources module received only the necessary generated-output pin updates.
The diagnostic scene, FONT resources and appendix remain unchanged; updating
its shared-atlas digest does not fix or enable the historical runtime owner.

**410 passed, 11 skipped, zero failures/errors across 25 standalone suites.** Both full XBE gates pass: 91 memory-write tests and 103 cave-reference tests, including both owner orders and scale-out.

The separate oracle suite ran 28 tests: 27 passed and one expected error, exactly the stale `nfl2k5_espn25_scenarios.py` reservation source specified in the brief. Its protected manifest was not regenerated. Claude must refresh it after the complete stack lands; the passing composition gates do not assert manifest source freshness.

Each table row ran as `python3 <path> -v`, under `/usr/bin/time -v`. Qt suites used `QT_QPA_PLATFORM=offscreen`; the legacy layout run used `NFL2K5_SCOREBUG_EMULATION_TEST=1`. [validation.json](docs/scorebug_ingame/rim/validation.json) records final results, log hashes, exact source/artifact hashes and the protected-path audit.

| Standalone path | Passed | Skipped | Expected errors |
| --- | ---: | ---: | ---: |
| `tests/nfl2k5_scorebug_layout_test.py` | 14 | 1 | 0 |
| `tests/nfl2k5_scorebug_mod_project_test.py` | 3 | 7 | 0 |
| `tests/mod_editor/test_apf_scorebug_workspace_qt.py` | 11 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | 27 | 0 | 1 |
| `tests/mod_editor/test_nfl2k5_scorebar_rim.py` | 8 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebar_v3.py` | 9 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_author.py` | 12 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_exact.py` | 8 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_fonts.py` | 9 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_freeze.py` | 7 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_ingame.py` | 11 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py` | 9 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_native.py` | 4 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_projection.py` | 14 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_resources.py` | 6 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_runtime.py` | 12 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_source_art.py` | 10 | 3 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_template.py` | 19 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_template_release.py` | 5 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py` | 5 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py` | 11 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py` | 14 | 0 | 0 |
| `tests/mod_editor/test_nfl2k5_scorebug_versions.py` | 4 | 0 | 0 |
| `tests/mod_editor/test_scorebug_studio_panel_qt.py` | 11 | 0 | 0 |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 103 | 0 | 0 |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 91 | 0 | 0 |

The eleven precise skips name absent legacy source-art exports (3), a historical intermediate glTF (1), and the typed-project JSON fixture (7). No current rim, native, template, Qt or XBE gate check was skipped. Largest test RSS was 926,572 KiB, below 2 GiB. `git diff --check` and Python compilation pass. Scratch contains only small logs/scripts/metadata, below 200 MB, and the filesystem remained above 100 GB free.


The APF scorebug page test had a pre-existing missing repository bootstrap
under plain `python3 file.py`. Its three-line test-only path setup now follows
the standalone contract; no APF product or GUI code changed. Earlier development
checks caught an incorrect rim material offset, decorative marks inheriting
tint, winding on the repurposed mark, and tests still expecting a collapsed
mark or a single frame. The final tests check the actual new ownership and
native geometry without weakening foreign-byte, winding or containment checks.

## HYPOTHESIS, Noah's witness list and delivery

The GPU, video filtering, display overscan, sustained gameplay and full game
entry were not executed. The live MIN/NYJ forecast uses the preceding witness's
state and fixture clock `4:15` with unavailable play clock `--`; it is not a
new live capture. Dark secondaries and the one-draw update delay remain physical
witness questions. Decorative marks are still not live timeout counters.

1. Build the Experimental static bar from clean retail, blank artwork folder,
   diagnostic effects off. Play **ATL at GB**: away red and home gold outlines
   must match their respective dark primary panels. Swap possession and teams,
   finish the game, return to the menu and re-enter without a hang.
2. Play **LV at HOU**: left silver and right Texans red must follow the correct
   sides. Reverse home/away and confirm that the outlines swap. Also inspect
   BAL/JAX's dark secondaries against the actual field and display.
3. Play an **LV at LV mirror match** (or two teams using the Raiders retail
   palette). Both primary fills are black, so the secondary fallback must
   produce silver on both sides. The separate missing-code CPU forecast proves
   the final silver fallback, but does not witness an unmapped created team.
4. In those games check presnap, snap/live play, whistle, flag, fumble and
   kickoff; the centre and clocks must stay, and decorative marks must stay
   neutral. Check 4:3/widescreen, both placements, clock/quarter transitions,
   score rotation and menu-to-next-match colour refresh.
5. Open, save and reopen a copied explicit v10 folder in Scorebar Studio;
   build it separately and confirm the retained v10 artwork. Keep the build
   receipt with Noah's captures so the actual installed revision is known.

Protected integration is the final r64-scorebar-rim section of `WIRING.md`.
It specifies the existing dispatcher/status/BuildPlan/preset/patch-help,
caption, allowlist, runtime-closure and capability behavior, plus Claude's
required protected-manifest regeneration. No span growth or new option is
waiting for integration; only shared help text and generated manifest refresh.

The initial three-file `git add -- <paths>` succeeded, but final staging of
all reviewed paths failed with `index.lock: Read-only file system` in the
shared worktree metadata. Delivery therefore uses the authorized fallback:
an isolated commit with this base as its parent, created using explicit
`git add -- <paths>` and `git commit -- <paths>`, and
`.scratch/r64-scorebar-rim.bundle`. The shared branch is not advanced; the
initial three files remain staged there. The bundle is verified and imported
into a disposable local repository, with its changed paths and every reviewed
blob checked. `ASTRA_BRIEF.md` and `.scratch/` are excluded from the commit.
Nothing is pushed. Commit identity, bundle hash and verification details are
recorded in `.scratch/scorebar-rim/DELIVERY.json`.

# Beta 66 D1: 2K5 Python tool fixes

Branch: `astra/b66-2k5-tool`. Implementation commit: `7f8f1572`. The six D1 fixes are implemented in core/facade
code. Protected panels are **integration handoffs**, not edits to the production
panels: apply the complete D1 blocks in `WIRING.md` / the matching
`reports/beta66_d1/panels.patch`. Offscreen tests execute those exact changes
in memory. No emulator, audio, network, full disc build or external message was
used. Retail inputs were read in place; temporary exported images were deleted.

## Smuzz: refusal at the option choice

Report: “Couldn't make the disc” after the build; “crashed twice”.
`mod_build.validate_plan` now names both full on-screen labels and runs before
any project preparation in public `build`, with another check at `_build` entry.
`plan_controls.refresh_playbook_controls` provides the synchronous shared gate
for Build and the editable Gameplay patches panel. Source-installed options
also count, restored conflicting selections block writing, and a selected
option can still be unticked on an eligible retail source. Helper subtitles give
the reason. The read-only Gameplay panel has no toggles; the existing
`GameplayBuildLink` synchronizes the editable panels.

PROVED: validator permutations, early refusal before preparation, all three
Basic/Modern/Experimental presets keeping the conflicting options off, linked
offscreen toggles in both directions, restored invalid state, source eligibility
and installed-option conflicts. This is the existing EXPERIMENTAL option gate,
not a compatibility patch. D2 owns the paired-root compatibility research.
imdakine1's “softdrink modern and create a modded iso wouldn't create” did not
include an error, so its original cause remains unconfirmed.

## maumau78: shoe copies and compressed budgets

Report: “If I simply try to export this shoe and import into another slot...
the texture looks washed up”. The two shoe slots use different index images.
A palette-only copy projects the new artwork onto the old index map; averaging
those colours and mip shades can wash it out. Supported shoe/glove imports now
default to independent artwork. Explicit recolour projects remain supported;
their projection uses dominant authored base colours instead of an average.
Export strips private import-choice metadata while retaining exact straight
RGBA values, including RGB under alpha zero.

The independent quantizer retains every base colour at a fitting <=256-colour
tier; extra mip shades cannot evict them. Reduced tiers keep authored colours
and dominant/far-separated colours at very small budgets. Every changed colour
has a complete from/to RGBA and pixel-count entry, with the reason (fixed
compressed budget, P8 palette limit, or shared-index recolour). CIE76 uses sRGB
to D65 Lab; alpha is covered separately by maximum RGBA channel error.
`nfl_vc_lz_fill` preserves the retail wrapper scratch word at +0x14.
The frozen visual-provider closure includes the palette, collection and college
warning dependencies so the isolated build process can import them.

PROVED synthetic: export -> stage another shoe -> unified package build is
lossless in a roomy slot; all 256 base colours survive extra mip colours;
alpha/hidden RGB survive; a tight palette retains dominant colours and its
message enumerates every merge. Existing equipment consumer and native texture
suites also run.

PROVED retail, read-only: Titans `28H0`, source
`tset:3850:8:0:shoes01`, Style 4 destination
`tset:3850:9:0:shoes02`, original 256x256 PNG with 211 colours. The facade export
is byte-exact against the decoded RGBA source. The original-size independent
chain cannot fit the destination's **58,016-byte compressed TSET**, even at two
colours, and is refused during import. At explicit scale 4, the real facade ->
`stage_equipment_import` -> `build_unified_uniform_equipment_imports` path fits
64x64 at two colours, stages the existing 402 consumer-package links, and keeps
wrapper +0x14 unchanged. No full disc was created.

| Comparison | Maximum channel error | Mean CIE76 | Maximum CIE76 |
|---|---:|---:|---:|
| Old palette-only projection, before final compression | 254 | 13.3390450164 | 99.6549260879 |
| New 64x64 decoded output vs 64x64 import pixels | 136 | 9.29713853285 | 51.9309672087 |
| New output enlarged with nearest-neighbour to original exported PNG | 254 | 9.42985286519 | 99.6549260879 |

The resized result differs in 2,630 of 4,096 pixels and reports 1,329 unique
from/to colour pairs; these are genuine budget/resize losses, not a lossless
claim. The old projection and new scaled result are different operating modes;
the table does not claim equal compression settings or game-rendered quality.
The exact retail diagnostic output is in `reports/beta66_d1/shoe_metrics.txt`.
Reproduce without writing a disc:

```bash
PYTHONPATH=. python3 reports/beta66_d1/reproduce_shoe.py --scale 4
```

The checked-in diagnostic was rerun after cleanup; its output matched
`reports/beta66_d1/shoe_metrics.txt` byte for byte (`cmp` exit 0).

UNWITNESSED: the copied shoe's appearance in the game. Full-size import on this
particular retail target needs more budget or a different authored image; the
tool does not silently resize it or claim that two colours are lossless.

## Coach Edwards: digit preflight

Report: “Arm / Shoulder Digit: this family has no fixed-span prediction yet”.
`CONTRACTS` now covers jersey, helmet and arm/shoulder digits. Each row obtains
the allocation and full layout from its digit target module, including actual
dimensions, palette gap, storage order, stream parameters, and, when reading
the source, the frozen system/gap bytes. The prediction uses the writer's digit
mips and quantizer and the same ladder down to its 16-colour floor. Existing
five-field prediction inputs still work; digit rows carry the exact contract
in an optional sixth field. Missing private target reports are explicitly
unpredicted rather than assigned a guessed allocation.

PROVED: each family on a synthetic 896-byte 32x32 digit slot, full/reduced/refused
wording and the 16-colour floor; existing preflight and digit suites. The
session supplies the source archive to preflight. No panel change is needed
for the existing Check my images dialog to consume the extra verdicts.

## iwb3 / Ju3tin: open the disc again later

Report: standalone xemu says “please insert disc”; “does it need to be .iso not
.xiso?”. The launch argv is unchanged for native xemu. Flatpak keeps its per-run
grant and also checks/sets a persistent user read-only override for the build
folder, with a status line on a new grant. After a successful process launch,
the facade atomically writes `[sys.files] dvd_path` in xemu's settings, checking
that every other parsed setting survives. Unsupported hand-authored layouts or
concurrent changes are reported without overwriting them.

Settings lookup follows SDL's `xemu/xemu` preference subdirectory under Linux
XDG data home, macOS Application Support, Windows Roaming AppData, or Flatpak's
application data directory. An existing `xemu.toml` beside the Windows executable
wins for portable mode; explicit `-config_path` also wins. Launch settings and
Flatpak failures remain visible in the final message.

The actual-path footer, Build help handoff, FAQ and changelog include:
“Your disc: ~/2K5 Mod Studio Builds/NFL 2K5 Modded.xiso.iso. To play again later:
open xemu, then Machine > Load Disc”. `.xiso.iso` is a valid name.

PROVED: temporary settings roundtrips/preservation/refusals, platform paths,
portable and explicit config, mocked override-once, unchanged native argv,
successful-launch persistence and failed-launch behaviour. UNWITNESSED: actual
standalone relaunch on each platform. No real emulator or persistent Flatpak
override was executed by this job.

## BigTimeEmpire: load, warn, then repair

Report: “certain roster and save files can't be edited if a player doesn't have
a college or there are errors with their college”. The refusal was the ROST
codec following an off-arena college reference before the checker could open.
It now records null, off-table and outside-arena signed references without
dereferencing them. College tables, names and unrelated references retain their
validation. Existing scan/repair can correct the unresolved college words;
typed generic pointer edits remain forbidden.

`SaveRost` and `RosterDocument` expose the exact common warning:
“N players have a missing/invalid college; use Check my rosters to repair”.
The panel handoff keeps that warning in Rosters/Franchise status and offers
Check my rosters after opening the document. A document-identity check prevents
a queued prompt from opening against a different roster. An unrepaired save
can be preserved in a signed copy; the warning persists until repaired.

PROVED: synthetic null/off-table/outside references, load/repair, undo/redo,
signed-copy reload, franchise schedule edits, and the exact offscreen offer
handoff. A structurally invalid college table is still refused. In-game loading
of a user-provided repaired save remains UNWITNESSED.

## Mud: a separate library collection

Report: “can I put them into their own playlist?” and “the game still freezes
after going to Incite #2”. Added rows now belong to `My songs` (or the supplied
library recipe name). The 59 retail song identities and 18 retail collection
headers retain their groups. `MSONGS2` owns a new native collection table in the
existing sealed read-only music allocation. Its new rows reuse a real retail
artwork resource identifier; they do not invent a missing asset name.

The new collection owner pins 51 complete instructions for table references
and native collection-count boundaries. No runtime data is placed in `.text`
and no cave is added. The verifier reparses collection records, checks the
sealed payload, verifies every instruction and supports idempotence. Policy
purchase changes re-seal copied headers; both owner orders produce identical
bytes. Playlist full-function guards normalize only verified metadata-owned
accessors. Older `MSONGS1` libraries remain readable/idempotent; rebuilding from
the original disc migrates their previous grouping.

PROVED: unchanged first 59 identities, new named groups, foreign-data refusal,
idempotence, native count/title/artwork-pointer and per-group-count getters,
200-node native list build/rebuild/lookup/scroll/metadata/profile serialization,
and policy/playlist composition. The public Add songs lane retains its current
134-addition maximum; the existing lower-level 400-row codec can use two new
groups of at most 256 additions each.

D2 coordination is the explicit local handoff
`reports/beta66_d1/D2_COLLECTION_LAYOUT.md`, including the instruction range,
table format and owner composition. UNWITNESSED: entering the collection,
artwork rendering, actual music playback, the reported freeze, and Xbox
soundtrack coexistence. Additional on-disc groups shift the Xbox soundtrack
boundary; previously saved Xbox soundtrack selections need a game witness and
may need reselection. This job does not claim the freeze fixed.

## Integration and verification

Apply the D1 panel patch and add the four new product modules to the protected
release allowlist using `WIRING.md`. Existing capabilities own these fixes;
there is no new capability or preset flag. Regenerate the cave manifest for the
changed music owner at integration. The protected runtime checker's hash-only
changes are generated by the explicitly requested `packaging/repin.py --apply`.

No retail payload is checked in. Scratch uses `TemporaryDirectory`; no large
write was made. The root volume was already approximately 98 GB free at the
disk-space check, below the context's requested 100 GB floor, so this job did
not build or copy a disc there. Linux/offscreen/native harness results do not
claim macOS/Windows execution or in-game witnesses.

Standalone test commands and their final outputs follow. Some old tests were
updated because refusing a repairable college reference is no longer correct.
Unrelated facade tests inject a dummy catalog. Provider tests copy their reviewed
source/data dependencies to temporary workspaces so a local extraction symlink
cannot affect these synthetic tests. The digit budget suite gives
a precise skip when its private target catalog is absent. Skips remain visible.

The first oracle run against the unchanged protected release manifest reported
two stale-source errors (`mod_build.py` is the first changed fingerprint).
The final oracle command uses the separately observed scratch projection from:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 reports/beta66_d1/refresh_test_manifest.py
```

That script records the full forward native safety-gate build, retains
historical retail reservations, and records current music owner writes. The
collection helper is attributed to its metadata owner. Resource/disc fields
inherited from the release manifest are explicitly historical; this does not
replace the required production manifest regeneration or assert a disc build.
The disposable scratch JSON is removed after verification; the command above
regenerates it. The small observation summary is retained with this report.

50 standalone suites completed: 1181 tests, 11 explicit skips. All final results are OK.

Each row uses `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/<suite>.py`
from this worktree. The batch runner supplied the same PYTHONPATH as an absolute path.
The oracle additionally sets `NFL2K5_CAVE_MANIFEST=.scratch/beta66_d1_manifest.json`.
Exact per-suite commands and unittest output are recorded in `reports/beta66_d1/tests.json`.

| Suite | Final unittest output |
|---|---|
| `test_2k5_build_parse_caches` | Ran 14 tests in 0.087s; OK (skipped=3) |
| `test_beta66_d1_images` | Ran 6 tests in 0.375s; OK |
| `test_beta66_d1_panels` | Ran 4 tests in 0.666s; OK |
| `test_build_panel_qt` | Ran 12 tests in 1.879s; OK |
| `test_emulator_launch_polish` | Ran 11 tests in 0.304s; OK |
| `test_facade_external_build` | Ran 2 tests in 0.054s; OK |
| `test_hotfix63_digit_budget` | Ran 5 tests in 0.025s; OK (skipped=3) |
| `test_mod_build` | Ran 11 tests in 1.544s; OK |
| `test_mod_build_beta62_integration` | Ran 8 tests in 214.577s; OK |
| `test_mod_build_beta62_integration3` | Ran 11 tests in 144.608s; OK |
| `test_music_playlist_project` | Ran 4 tests in 0.737s; OK |
| `test_music_service` | Ran 10 tests in 3.057s; OK |
| `test_music_simple` | Ran 12 tests in 21.656s; OK |
| `test_nfl2k5_cave_oracle` | Ran 29 tests in 683.923s; OK |
| `test_nfl2k5_college_check` | Ran 17 tests in 10.623s; OK |
| `test_nfl2k5_college_check_page_qt` | Ran 11 tests in 2.582s; OK |
| `test_nfl2k5_college_check_qt` | Ran 3 tests in 0.560s; OK |
| `test_nfl2k5_digit_sheet` | Ran 3 tests in 0.429s; OK |
| `test_nfl2k5_digit_sheet_quality` | Ran 13 tests in 7.570s; OK (skipped=1) |
| `test_nfl2k5_equipment_consumers` | Ran 17 tests in 37.560s; OK |
| `test_nfl2k5_equipment_import` | Ran 11 tests in 1.462s; OK |
| `test_nfl2k5_equipment_import_wiring` | Ran 6 tests in 1.068s; OK |
| `test_nfl2k5_equipment_texture_chain` | Ran 16 tests in 5.842s; OK |
| `test_nfl2k5_equipment_texture_native` | Ran 5 tests in 0.304s; OK |
| `test_nfl2k5_franchise_save` | Ran 13 tests in 1.630s; OK |
| `test_nfl2k5_franchise_schedule_college` | Ran 8 tests in 1.950s; OK |
| `test_nfl2k5_import_preflight` | Ran 17 tests in 18.992s; OK |
| `test_nfl2k5_music_acceptance` | Ran 1 test in 0.000s; OK (skipped=1) |
| `test_nfl2k5_music_banks` | Ran 15 tests in 12.580s; OK |
| `test_nfl2k5_music_build` | Ran 8 tests in 3.679s; OK |
| `test_nfl2k5_music_metadata` | Ran 7 tests in 31.483s; OK |
| `test_nfl2k5_music_playlist` | Ran 15 tests in 19.626s; OK |
| `test_nfl2k5_music_playlist_contexts` | Ran 7 tests in 15.912s; OK |
| `test_nfl2k5_music_playlist_library` | Ran 7 tests in 23.741s; OK |
| `test_nfl2k5_music_playlist_manifest` | Ran 2 tests in 4.861s; OK |
| `test_nfl2k5_music_policy` | Ran 8 tests in 15.846s; OK |
| `test_nfl2k5_owner_pairwise_composition` | Ran 335 tests in 2794.394s; OK |
| `test_nfl2k5_roster_records` | Ran 108 tests in 13.531s; OK (skipped=1) |
| `test_nfl2k5_save_rost` | Ran 9 tests in 2.750s; OK |
| `test_provider_integrity` | Ran 7 tests in 29.243s; OK |
| `test_providers` | Ran 33 tests in 9.198s; OK |
| `test_roster_editor_panel_franchise` | Ran 2 tests in 0.446s; OK |
| `test_roster_editor_panel_qt` | Ran 50 tests in 4.291s; OK (skipped=1) |
| `test_save_roster_import` | Ran 12 tests in 0.002s; OK |
| `test_studio_facade` | Ran 11 tests in 0.020s; OK |
| `test_studio_session` | Ran 18 tests in 0.849s; OK |
| `test_uniform_bundle_cross_project` | Ran 0 tests in 0.000s; OK (skipped=1) |
| `test_xbe_patch_cave_references` | Ran 127 tests in 2206.371s; OK |
| `test_xbe_patch_memory_writes` | Ran 115 tests in 1800.345s; OK |
| `test_xemu_settings` | Ran 5 tests in 0.011s; OK |

Additional checks:

```text
python3 packaging/repin.py --apply
applied 0 pin update(s)
git apply --check reports/beta66_d1/panels.patch
(exit 0)
git diff --check
(exit 0)
```

The observed scratch manifest has 12,720 spans and 125 recorded operations.
Its summary and SHA-256 are in `reports/beta66_d1/manifest_observation.json`.
The implementation commit is followed by this report/evidence commit; neither is pushed.

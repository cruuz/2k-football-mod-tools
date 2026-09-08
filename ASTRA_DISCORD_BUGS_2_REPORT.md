# Community reports, batch 2: editor fixes and gameplay verdicts

2026-09-07. **EXPERIMENTAL / UNWITNESSED** for game appearance and runtime
behavior. This job ran no emulator, display, audio, network request, or real-disc
build. No executable owner bytes, allocator budgets or protected files changed.
The editor backends are implemented; the protected GUI and copy-wrapper edits
are a concrete, tested proposal in `tests/fixtures/discord_bugs_2_wiring.patch`
and the final section of `WIRING.md`. They still require integration.

**PROVED** below means inspected source, pinned native bytes, an existing
owner's specifically identified offline receipt, or this job's bounded test.
It does not mean someone played this change. **HYPOTHESIS** marks causal
explanations of the community symptoms. The original attached images, clip,
error screenshots and comparison videos were not available in this checkout;
the ledger text is the report, not substitute visual evidence.

`docs/mod_editor/discord_bugs_2_evidence.json` records the 73 preceding report
versions and headings, ten native function body ranges and direct-call lists,
16 byte probes and receipt arithmetic. The supplied retail USA XBE was read
and verified: 11,948,032 bytes, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
The Ghidra corpus was read only. Function bodies use its exact `body_ranges`,
not an approximate interval that could accidentally include another function.
The 6,300,499,968-byte canonical XISO and its hash in older receipts were not
rehashed or copied here. No private game payload is added to the repository.

## B15: 0-9 sheets

**Report.** Coach Edwards confirmed beta 61 fixed the Windows path-length
failure, then asked for a reliable sheet format and showed incorrectly imported
numbers. This job preserves that existing path fix.

**PROVED cause.** `nfl2k5_digit_sheet.split_digit_sheet` chose the longer axis
and rounded ten cut positions. A 5-column, 2-row sheet was interpreted as a
horizontal strip, and widths not divisible by ten were silently split into
unequal cells. The UI documented only horizontal/vertical without an explicit
layout choice. **HYPOTHESIS:** the unavailable pictures used a grid, unwanted
cell spacing, or a different order. Their exact defect cannot be inferred.

**Fix.** The splitter now accepts explicit horizontal, vertical, 5x2 and 2x5
layouts, always in digit order 0 through 9, left to right then top to bottom.
Cells must divide the actual sheet dimensions exactly. Ambiguous automatic
layouts refuse and request a layout instead of guessing. Alpha is preserved;
each cell is resized to its selected jersey/helmet/arm target. Header dimensions
are capped at 16 million pixels before decoding to bound memory. The new
`docs/mod_editor/number_sheets.md` explains equal transparent cells, spacing,
examples, order, scaling, file limits and the absence of a sheet generator.
The protected Studio proposal adds the four-choice dialog, help text and the
orientation argument to the real import callback.

**Tests/witness.** The pre-fix regression failed on both explicit grids and
accepted an ambiguous sheet incorrectly. The fixed tests verify all four
orders, per-cell color/alpha, refusal reasons and unchanged source. The
proposed UI callback is executed offscreen through its splitter call. Existing
digit-sheet tests also pass. Noah's remaining witness: import a labeled 0-9
grid into one known kit, export the ten results, then photograph front/back,
helmet and arm numbers in play. A grid with gutters must first become equal
cells; the importer does not detect glyph boundaries.

**FAQ.** Select the sheet's row/column layout and use ten equal cells; see the
new number-sheet page. A 5x2 sheet is now supported explicitly.

## B18: APF multi-edit and Build Game Folder

**Report.** MarqueePCGaming wants several movie-team logos and custom endzones
in one Xenia game folder; only one edit survived and Build Game Folder errored.

**PROVED causes on this stack.** Every crest used one session asset ID; staging
another team overwrote the first, the build explicitly refused more than one,
and the GUI refreshed its picker back to the last staged team. Field Art used
panel/facade dictionaries outside the shared project. Its copied-0A export
rebuilt one selected texture from the original. Replacing one such output with
another necessarily lost the first edit. These are reproducible defects.
The missing error screenshot prevents identifying his exact Build Game Folder
exception. A bad source, unsupported texture, compressed allocation overflow
or destination failure remains a separate possibility, not a proved diagnosis.

**Fix.** Session state now retains crests per team, replacing only the chosen
team and keeping Undo. The most recently edited crest retains the legacy ID;
earlier teams use slot-qualified IDs, preserving old single-crest projects.
Project save/load validates and round-trips both IDs. Build compiles each
team package and updates the shared crest cache once with every team's layers.
Detail layers are checked for missing/changed bytes before and after compilation.
Multiple Retail side-decal profiles compose. A full-shell design changes a
shared helmet model, so full-shell plus another team refuses before altering
session state; this is an explicit remaining limit.

Field Art is now a real project modification with selector, dimensions and
PNG hash validation using the existing frozen writer contracts. Build groups
all selected inner textures of an outer package into one existing
`build_field_art_patch_many` operation, then includes that result alongside
crests and other edits in the same transactional game-folder copy. Existing
source pins, fixed-span budgets, sibling preservation and conflict refusals
remain active. There is no new texture codec. Format-59 DXT5A is still refused;
supported format-18 endzone layers retain their compressed budgets. Packed
mip tails remain unchanged, as documented by the existing Field Art writer.

The protected APF GUI proposal stages through the shared facade, emits project
dirty/refresh signals, reads project state after Undo/load, reverts the chosen
team, preserves the chosen picker slot, and saves that team's authoring master.
It directs a workspace with multiple edits to Build Game Folder instead of
silently exporting only one texture. The standalone export remains available
for one edit.

**Tests/witness.** Pre-fix tests proved two crests became one and Field Art had
no session operation. Fixed tests cover replacement/Undo, real project ZIP
round-trip with two crests and Field Art, grouped texture compilation, one
shared cache build, and atomic full-shell conflict refusal. A bounded synthetic
game folder is built with a crest and two Field Art layers: all three edits
are receipted and output bytes match, while source and unrelated spans remain
identical. Archive/native compiler dependencies are mocked for that small
composition fixture; this is not a real APF folder acceptance build. Existing
crest, raw-overlay, field-writer and project suites pass. The existing field
writer suite also exercised real APF endzone copied-volume/no-op verification
against the supplied 0A: temporary 1.1 GB volumes were streamed, independently
compared and deleted. That is separate from a multi-edit game-folder build.
Offscreen proposed GUI tests reproduce/fix the picker jump and shared staging.

The APF allowlist now includes both help pages; its runtime tool imports
explicitly include Field Art and crest-cache compilers. All 104 product/tool
imports and the literal import-closure check pass. A complete clean release
stage cannot be assembled: the checkout lacks the vendored extractor's
`BUILDING-THE-BUNDLED-BINARIES.md`, `LICENSE.TXT`, `build/extract-xiso` and
`build/extract-xiso.exe`. The checker also correctly refuses the development
tree's private `reports` directory as a release root. No gate was relaxed and
no substitute binaries were manufactured.

Noah's remaining witness after GUI integration: stage three distinct Retail
team crests plus two supported endzone layers, save/reopen the project, build
one new folder from a complete original, and inspect every team and endzone in
Xenia. Record a complete error/receipt if the original folder-build error
persists. The desktop changes and rendered art remain unwitnessed.

**FAQ.** Keep all supported edits in one saved project and use Build Game
Folder. Separate single-texture 0A exports are complete alternative copies,
not files that can be stacked by overwriting each other.

## B21: emulator swapping and alleged image damage

**Report.** Atomic Game Room Productions reports crashes and a “bricked” XISO
when swapping emulators without ejecting.

**PROVED distinction.** A separate read-only process can retain the image
while its bytes remain identical. POSIX permits replacement of that pathname
while the first process still reads the old inode. Windows sharing rules may
reject replacement. The existing protected `mod_build.build` and throw-tuning
copy wrapper performed unconditional final `os.replace`, and could overwrite
a destination created after preflight. The cached Studio build service already
used atomic no-replace publication. **HYPOTHESIS:** retained handles or stale
emulator state explain the report. We have no before/after image hashes from
either emulator and cannot rule out another writer. No actual emulator damage
or recovery was reproduced, and an emulator swap alone is not proof of damage.

**Fix.** New `core/image_use.py` probes an existing image without writing it.
Windows requests an exclusive read handle and closes it; Linux checks visible
same-user `/proc` descriptors and mappings by device/inode; macOS checks lsof.
Observed use refuses with: “Eject the disc and close both emulators, then retry.
Mod Studio did not change the image.” Unknown/inaccessible checks refuse with
their reason. Studio Launch now performs the probe before invoking the process
launcher. The cached build service adds that explanation for occupied outputs.
The protected two copy wrappers use preflight and final rechecks, identity/
size/mtime comparison, and atomic no-replace when a destination did not exist.
All owned handles close before publication; failed candidates are removed.
The helper's standalone copy streams in 1 MiB chunks, fsyncs and never replaces
the source, its hardlink, or a selected output symlink.

**Limits.** POSIX inspection is a snapshot, not a mandatory lock against a
noncooperating process that opens between the last probe and replacement.
Linux only covers visible processes owned by the current user; other-user
processes are not universally observable. Windows releases its probe before
the rename and still relies on kernel sharing checks at rename time. Native
Windows/macOS behavior needs those platforms' witness; Linux was exercised.
No process is killed and no disc is ejected automatically.

**Tests/witness.** A real child Python reader holds a tiny image. The actual
Studio launch method refuses, never calls its launcher, and copy/build
preflight refuse; the original bytes remain identical. Closing the reader
allows replacement. Tests also cover source alias, symlink, changed target,
no-overwrite and a racer creating a fresh destination. Protected-wrapper
tests prove the backend does not start when occupied and final publication
refuses a newly observed handle. This proves editor refusal, not emulator
behavior. Noah's witness uses streaming SHA-256 and size before launch, while
held, after closing both emulators, and after any failure; record both image
paths, timestamps, exact emulators and whether either was configured to write.
If hashes match, diagnose handles/cache/guest failure; if different, preserve
both copies and identify changed extents before blaming an owner.

**FAQ.** Eject and close both emulators before switching or replacing an
output. A crash is not evidence of changed image bytes; hashes establish that.

## B13: screen-edge artifact

**Report.** Smuzz's clip showed an edge artifact; Noah associated it with the
widescreen patch. The clip is unavailable here.

**PROVED audit.** `ASTRA_WIDESCREEN_POLISH_REPORT.md` already fixed the active
projection for both interlaced fields and planes, local shadow camera load
`0x1C32FB`, sky lens `0x9E1BC`, sky tint coverage, projected billboard/foot/head
markers (`0x7EC59`, `0xFA2A1`, `0xFA31E`), auxiliary projections and label cull
`0xF9950`, plus scissor minimum pixels. Its 16:9 treatment uses 32/27 hor+
relative to the game's 720x480 projection, inverse 27/32 and K=56.25; assuming
a generic 4/3 multiplier would duplicate a correction. World culling already
uses the active wide camera.

Kickoff A-D traces the on-field assignment renderer through
`0x64E80 -> 0x11A8F0 -> 0x75D90 -> 0x1807F0`; `BDFBE4=0` makes `0x180120`
return. Assignment lines flow through `0x181CC0 -> 0x180410 -> 0x164AC0 ->
0x164880` as world vertices, not through the screen helper `0x2AB40`.
Long stale assignment endpoints can therefore misplace world play art without
a screen-space scaling error. Play-call diagrams are another surface.

**HYPOTHESIS/verdict.** A remaining far-sky wrap/seam, fog or LOD transition
near `0x9DE10/0x9CEF0`, a render-to-texture camera at `0x29880`, or an unaudited
non-unit effect quad at `0xD9FA0` could draw an edge. A fixed scorebug/HUD edge
belongs to its screen layout; a world-following line belongs to assignment
geometry. The Hi-res pilot changes resources with normalized UVs, not camera
or mesh positions, so it can expose sampling/art seams but is not evidence of
a projection change. There is no justified new blanket widescreen patch.

**Proposal/witness.** From the same original and same scene compare retail
4:3, widescreen v3 alone, then that build with only the selected Hi-res family.
Record output hashes, EEPROM aspect flags, actual video mode, render scale,
camera and the entire frame including edges. Toggle play art and determine
whether the defect follows screen coordinates, field position, player/mesh,
sky rotation or camera distance. Retest the current v3 before changing any
owner. A reproducible remaining surface needs its own pinned callsite witness.

**FAQ.** Capture the full frame with play art off/on and identify what the
artifact moves with; the old clip does not establish a remaining v3 defect.

## B19: blocking and hurry-up

**Report.** Blocking allegedly breaks with mods and hurry-up does not block;
no selected-option list or clip accompanies the ledger entry.

**PROVED owner audit; causal ranking remains HYPOTHESIS.**

| Owner | Actual scope and relevance |
| --- | --- |
| Abilities runtime | Carrier-only charge policy clears noncarrier meter fields `+44/+48/+90` and steering `+18`. Hook `0x2D4740` denies nine unclassified direct consumers (`18D2C6`, `18DF7C`, `1E773E`, `1E7BA2`, `2319CB`, `291D60`, `308512`, `30EDA7`, `31793D`). Native powered blocks/tackles/catches can use charge. The seven ability flags do not grant blocker permissions. Strongest direct general-blocking suspect; the nine calls have not all been proved to be blocking. No no-huddle gate was demonstrated. |
| Momentum | Dispatcher `0x1CD5D7` changes ordinary live locomotion for CPU and human entities, not just the carrier. Turning table `0x50A588`, helper `0x237CCC/0x237CDA` and floor `0x237D11/0x237D20` can delay approach/engagement. It does not write protection assignments or explicitly select hurry-up. Momentum-contact's carrier break-tackle reads are a separate, narrower owner. |
| Screen data / screen hooks | Timing D changes 64 of 129 named screens matching a known PLAY grammar. Runtime block completion hook `0x23ECD2` and QB timer `0x19C7E9` use phase 14, snap clock `[E6029C]+10`, and specific QB/receiver plus lineman finite-hold/release/block grammar. Block hold is 0.8 seconds; default QB delay is 0.6. Loaded buffers are `B75A40/B88DD0`. A stale assignment/clock after hurry-up is plausible but was not exercised by the owner fixture. These are not universal pass-protection changes. |
| Kickoff nearest-blocker v2/v3 | Normal kickoff context, live phase 14 after first contact, receiving team noncarrier and mode 2. Selects an approaching coverage player; guards exclude ordinary scrimmage. Low hurry-up suspect unless a capture proves stale kickoff context. |
| Coverage slider | `0x1F4250` changes a defender's ball-reaction consumer from `(C+.25)*.15` to `C*.225`, neutral at slider 50. No block-assignment writer or no-huddle branch is shown. Low direct suspect. |

Other selected settings can matter: holding/clipping penalties, progression's
block/tackle/secure-ball/break-tackle ratings, direct pass/run blocking roster
edits and custom PLAY assignments. They must be retained in the receipt rather
than silently attributing everything to Momentum. Return-block targeting is
not proof of successful engagement or a won block.

Native UTF-16 “no huddle” at `0xE6CBD0` is referenced at `0xFF550` in
`0xFF360`, a HUD path. “No Huddle Manager” descriptors reference menu data.
Those names do not identify the simulation's tempo reset path. **Verdict:**
general noncarrier charge loss is a concrete policy concern; a specific
hurry-up defect remains unproved.

**Bounded proposal/witness.** Compare the same roster, offense/defense, play,
sliders and input sequence in a normal huddle and repeated hurry-up snaps.
Discs: clean control; matching allocator-only control where required;
abilities only; Momentum only; screen timing D only; that timing plus screen
hooks; kickoff only. Start each from the same original, not a previously
patched output. Capture assignment index/type/target, snap clock and phase,
ball carrier/team, charge and kickoff context before the second snap. First
classify the denied abilities consumers; only then consider preserving native
noncarrier charge for proved blocking consumers. For screen hooks, reproduce
a stale clock/grammar and add a guarded reset test before changing the owner.
No guessed bytes or new owner budget are proposed here.

**FAQ.** Record the full option list and compare the same play with a huddle
and hurry-up. Abilities, Momentum and screen timing are separate experiments.

## B20: slower patched disc

**Report.** Atomic reports a material xemu slowdown as features accumulate.
The videos and frame counters are unavailable; hardware specifications alone
cannot establish a causal patch or a performance threshold.

**PROVED receipt arithmetic.** Values below retain the scope/version of their
source report; disc growth, compressed assets and decoded residency differ.

| Item and source | Measured/modelled delta |
| --- | --- |
| Grown XBE, allocator scale-out | Retail 11,948,032 to v3 12,300,288: **+352,256 B**. Historical beta-61 12,099,584 was +151,552 B. Appending a relocated XBE to a disc can append the complete executable, not just this difference. |
| Three-asset Hi-res pilot | Video 181,888 to 718,336: **+536,448 B**. Stored resources 61,392 to 373,152: +311,760 B. Pack sector growth +311,296 B. Physical XISO 6,300,499,968 to 6,752,544,768: **+452,044,800 B**, primarily relocated pack extent, not extra resident texture data. |
| Expanded Hi-res families | 2,524 resources: 64 helmets, 1,920 numbers, 64 paired jerseys, 126 external textures, 348 embedded textures and two scorebugs. Reported scene model (two shared kits, two field scenes, two external sets, 22 names) 7,166,976 to 11,313,152: **+4,146,176 B**. Stored spans 80,424,912 to 85,094,032: +4,669,120 B. The full-catalog 419,720,832 video bytes are spread across mutually exclusive scenes, not a simultaneous allocation. |
| 200-track music payload model | 200 three-minute stereo records: **893,030,400 B**; with mono twins **1,339,545,600 B**, an additional 446,515,200 B. These are encoded archive payloads. |
| 200-track menu / jukebox archives | Projected physical XISOs 7,627,702,272 / 7,776,137,216: **+1,327,202,304 / +1,475,637,248 B** relative to canonical retail. Logical archive 6,227,718,144 to 7,103,186,944 / 7,239,526,400: +875,468,800 / +1,011,808,256 B. Descriptor expansion 192 to 960 B and 201 boundaries; a separate 64 KiB music metadata section is not 200 decoded songs. Tiny synthetic tone receipts are not a realistic library-size estimate. |
| Runtime scorebug, runtime/fix reports | 264 P8 textures: pixels 1,081,344, palettes 270,336, system bodies 33,792; **1,385,472 B** before heap overhead. Native headers/alignment add 33,792: **1,419,264 B** extra heap occupancy (1.3535 MiB). All variants load, although current teams select only eight descriptors. HUD outer 2,977,184 to 4,371,104: +1,393,920 B; sector growth +1,394,688 B. The older acceptance XISO grew +207,134,720 B due to relocated pack/XBE. |

Sources: `ASTRA_ALLOCATOR_SCALEOUT_REPORT.md`, `ASTRA_HIRES_PACK_REPORT.md`,
`ASTRA_HIRES_MORE_REPORT.md`, `ASTRA_MUSIC_BANKS_REPORT.md`,
`ASTRA_MUSIC_PLAYLIST_REPORT.md`, `ASTRA_MUSIC_ALL_MODES_REPORT.md`,
`ASTRA_SCOREBUG_RUNTIME_REPORT.md`, `ASTRA_SCOREBUG_FIX_REPORT.md`, and the
later scorebug exact/exact2 integration reports. The current runtime owner
retains its 1,408 B RX / 128 B RW requests and six diagnostic probes. Later
panel geometry is not the old receipt's visual identity.

**HYPOTHESIS/verdict.** Hi-res can increase upload/decode work, GPU texture
bandwidth and emulator host texture residency. Embedded replacements retain
old scene material, so stored-size reduction is not a memory certificate.
Runtime scorebug has a real resident-allocation cost; its hook does no
per-frame file I/O or allocation. Added owner code costs frame time only when
executed; reserved RX capacity or physical XISO padding is not a cycle count.
Music is streamed: 200 records are not decoded every frame. Playlist refill
is N-1 shuffle selections; current selected lists cap at 100, with up to 400
browsable per bank. Its 2 KiB RX / 512 B RW / 1 KiB RO budgets and 1,689 B
all-modes code are small; loading-time I/O, transitions or mode-4 overlapping
audio streams are distinct possible costs. The guest residual heap is dynamic;
nominal host RAM or enabling 128 MiB does not certify game/GPU headroom. The
Hi-res audit deliberately leaves the 64 MiB GPU-address constraint intact.

**Witness.** Establish clean/Basic/Advanced/Experimental at identical emulator
build, guest memory, CPU/GPU settings, resolution, roster, stadium, weather,
camera and replay segment. Show the emulator frame counter, warm caches
consistently, then record comparable frame-time distributions (median, 95th
percentile and lows), emulator rate, load duration, disk reads and host/guest
memory separately. One-owner variants: v3 allocator scaffold; each Hi-res
family alone; bank expansion without shuffle; shuffle with a small library;
200 real-length tracks; runtime scorebug's existing `transport`, `hooks`,
`resources`, `neutral`, `pair` and `full` probes. Do not combine Hi-res scorebug
with runtime scorebug's conflicting resource pins. Only paired measurements
justify a performance note in a preset. No FPS number or tested-safe maximum
feature count is established here.

**FAQ.** Compare one feature at a time with the frame counter visible. A
larger XISO does not mean that entire file is loaded into RAM.

## B5: dynamic card, traditional kickoff

**Report.** BigTimeEmpire saw a dynamic-looking playsheet but a traditional
kickoff after choosing the play. Beta 62 alignment has Noah's historical
played witness; this reporter has not supplied a current-stack retest.

**PROVED selection path.** `tools/nfl2k5_kickoff_alignment.py` finds existing
formations by exact name and type: `Kickoff`/8 and `Kick Return`/9. It changes
their X/Z coordinates; it does not create a new named dynamic formation. The
book compiler's formation references retain the existing index and packed
type (`flags >> 8 & 0x3f`); plays link to that index. Card layout is a preview,
not activation of executable logic. The current writer covers 36 eligible
book pairs. A book with neither is skipped (retail PRACTICE); a book with only
one of the pair refuses, and fewer than 32 paired books refuses. Thus a missing
named “dynamic formation” is not itself a missing feature, nor does the normal
writer silently succeed on a half-present pair.

`softdrink_basic` and `softdrink_advanced` set both `dynamic_kickoff` and
`kickoff_alignment` false. `softdrink_experimental` sets both true. Normalization
of dynamic enables kick rules and alignment and disables old kick power;
relocated kickoff implies dynamic. Build order is executable, alignment, then
return-assignment writer. These protections already exist on this stack.

**HYPOTHESIS/verdict.** An older build with card/alignment only, a preset with
dynamic off, a foreign/custom book or a different selected formation can
explain the symptom. A correctly normalized current Experimental build does
not need another dynamic formation inserted. No duplicate kickoff owner or
new compiler patch is justified.

**Witness.** Retest from retail with current dynamic on. Record receipt XBE
status/settings, per-book alignment and return receipts, selected team/book,
formation index/type, normal versus onside/safety choice and possession
direction. Show the card, pre-kick placement, kick and first touch in one
capture. Confirm both directions and a second book; a card screenshot alone
cannot close the report.

**FAQ.** Basic/Advanced leave dynamic kickoff off. Check executable and book
receipts together; the playsheet is not proof that the rule is active.

## B6: muffs, alignment and blockers running past threats

**Report.** andrethealchemist described muffed kick/punt returns and awkward
alignment; other users report return blockers missing the first threat.
Noah's September 4 spacing/hold notes and later v2 jitter witness are historical
played observations, not a v3 acceptance result.

**PROVED existing fixes.** `ASTRA_KICKOFF_FIXES_REPORT.md` A uses actual ball
coordinates for landing-zone eligibility; the receiving-side example
4,480.56 cm is short of the 4,572 cm goal line while player-root/descriptor
logic could disagree. B preserves neutral idle instead of skipping animation.
C replaces the old 21-30-yard rush-then-block chains in slots 2-6 and erroneous
deep-returner chains in 7-10 across all 36 normal-return books, preserving the
two deep returners and onside/safety behavior. The combined A-D PLAY receipt
uses 78 private nodes per book, 2,808 total, fixed `0x133B0` spans and 19,217
changed bytes. D corrects assignment/play-art geometry, not the world camera.

`ASTRA_KICKOFF_V2_REPORT.md` proves the retail nearest-target path `0x2FAFF0`
could choose 1,000 cm over 500 cm with score zero; lead refresh `0x23A630`
discarded weak confidence. The replacement searches approaching, in-front
coverage players 1-10 (not the kicker), finite X/Z distance and at most 22
entities, sets confidence 1, and replaces an old task beyond 137.16 cm
hysteresis. It is scoped to normal kickoff after contact and receiving
noncarriers, not punt coverage or ordinary scrimmage. Several blockers may
choose the same defender; nearest selection does not guarantee a block win.
The deep alternate uses drive-block type 0 instead of lead type 4.

`ASTRA_KICKOFF_V3_REPORT.md` follows Noah's v2 observation that art improved
but jitter remained. Static/native fixtures identify fresh late collision
writes near `0x1D898D/0x1D8997`, residual motion at `0x28D06D/0x28D081`, and turn spring
`0xE0110` through `0x28E360`. V3 guards `0x1D8940` and clears residual motion,
animation clock and spring state during the hold. Its synthetic fixture holds
19 players (ten coverage, nine setup), leaves kicker/two deep returners free,
checks 60 final frames in both directions and releases on contact. The fixture's
250 cm collision radius is synthetic. **V3 remains UNWITNESSED.**

**Unresolved.** None of A-D/v2/v3 is a global catch/muff/fumble-rate fix or a
punt-return assignment rewrite. The separate `nfl2k5_returner_fix` corrects
franchise auto-depth-chart index selection at `0x2BDE70..0x2BDFD0`, preventing
QB/invalid returners; it does not alter catching probability. Ratings, fatigue,
weather, user input and the chosen catch-slider setting remain controls, not
established causes of the reported muffs.

**Witness/proposal.** Run current v3 normal kickoffs in both directions,
record pre-kick spacing, every held player's root position/animation, first
touch and each blocker's chosen threat after release. Separately compare
stock and patched punt returns with the same returner, ratings, weather and
input. Count opportunities and muffs for kicks and punts separately. Preserve
onside/safety controls. Do not declare the muff issue solved by improved
alignment, or reimplement the already-landed nearest-target fix.

**FAQ.** Current v3 targets hold jitter and kickoff return assignments. Muffed
punts and catch rates still require a separate controlled comparison.

## B8: Berman/audio loop versus SEGA boot hang

**Report.** Two users reach Berman, hear looping crowd audio during game load,
then return. Noah's everything-on disc hangs at SEGA while Experimental boots.
The brief suggests a common cause; **HYPOTHESIS:** they could share resource
pressure or a loader fault. The different phases do not prove one failure.

**PROVED native startup request order.** The new pinned read-only trace shows:

1. `0x74BF0` calls heap startup `0x38FC0` at `0x74C17`, then `0x748A0`
   at `0x74C21`. This is after the executable loader's section work.
2. `0x748AB` calls roster arena initialization `0xC1F00`. Retail stores capacity
   at `0xC1F2D`, pushes allocation size at `0xC1F3C`, and calls allocator
   `0x48700` at `0xC1F43`. Arena growth therefore affects boot allocation before
   a franchise is selected.
3. `0x74969` requests the legal-page sequence through `0xF5D60`. Table
   `0x4E9720` names legalpage (5 seconds) then segalogo (2 seconds), followed
   by the other presentation logos.
4. Subsequent startup requests include FaceTextures/igfaces.iff (`0x749D1`),
   FaceShapes/shapes.iff (`0x749EF`), GLOBAL/global.iff (`0x74A0D`),
   DIRECTOR/dir_ingame.iff (`0x74A2B`) and ROSTER/roster.iff (`0x74A49`).
5. `0x74B72` calls `0xF6230`, which requests FRONTEND/frontend.iff at
   `0xF6252`, then `0xF60D0`; that requests logos.iff and flipchip.iff and
   calls coach ambience `0x165C20`. It is not the draft-load function.

This is native call/request order, **not** proved ordering of asynchronous
read completion, first rendered frames, patched callbacks or actual failing
sectors. A SEGA image can remain on screen while later requests are pending.
No single textual logo position is sufficient to identify the stopped PC.

**Owner effects and bisect priority (HYPOTHESIS rankings).**

| Content opt-in | Proved boot/load effect | SEGA rank / later game-load relevance |
| --- | --- | --- |
| Roster arena growth | Capacity `0x91000 -> 0x92000` (+4,096 B), wrapped ROST `0x90F80 -> 0x92060` (+4,320 B), roster v17->18/save v0->1. Hooks allocator/callback/admission path (`C1F00`, `C1E30`, `C1EA0`), 8 KiB RX budget. | **1**, with matching allocator scaffold control. Before legal-page request; also relevant when loading/migrating roster/save state. |
| Crib reclaim | 23 MOV outers 4298-4320 become 2,048-byte tombstones: archive reclaim 417,122,304 B; physical plan reclaims 417,136,640 B. MOV opener call `0x272A94` becomes two-argument cleanup, zero result and state-6 exit. TrophyRoom 4248/4272/4291 remain. | **2** for archive compaction/index mistakes affecting early reads. The Crib MOV callback itself is later and does not remove the live Berman frontend. Distinguish compacted data from the XBE suppression. |
| Guardian overlay | Global `helmet01` chunk 224 in common outer 3 grows 2,387,424 -> 2,475,968 B (+88,544; +88,064 sector growth). Equipment hooks `8F02E`, `8FB45`, `C16CD`; 496 B actual RX, no RW. Native lookup `449E0/443D0`. | **3** early global resource/index effect; higher at player-scene load/bind. Missing texture has a hide/fallback path, so absence alone does not prove a hang. ROST cap flags alone have a different, later scope. |
| Music banks/shuffle | Archive growth changes descriptors/locations; initialization/state hooks include `6E4E0` and mode dispatch `F6510`. Loading `64590` selects mode 2; native timed loading `F5410/F5430` remains. Halftime `D90F0`, wrap-up `28F7F0` and draft `325E22` are later paths. | **4** for early boot, higher for menu/load audio-state or stream transitions. First-read index damage and runtime shuffle are different trials. Audio looping can be the last queued buffer while another thread waits. |
| Practice Squad screen | Existing menu clone, 676-byte table selected through pointer `0x5221A0`; 4 KiB RX/256 B RW budget, 12 state bytes used. Replaces the Coach Desk Crib row, not the title main menu. Its shared frontend hook composes with playlist. | **5** for SEGA. No new early boot callback is shown; allocator prerequisite still needs control. Becomes a direct suspect when entering its menu or exercising shared menu-hook composition. |

Sources: `ASTRA_ROSTER_ARENA_GROWTH_REPORT.md`, Crib section of
`ASTRA_MY_CAREER_REPORT.md`, `ASTRA_GUARDIAN_OVERLAY_REPORT.md`,
`ASTRA_MUSIC_PLAYLIST_REPORT.md`, `ASTRA_MUSIC_ALL_MODES_REPORT.md`, and the
Practice Squad screen owner/source and preceding report inventory.

For the Berman-to-match failure, independently prioritize selected Hi-res,
runtime scorebug and global player resources, then roster load/migration and
music state; Crib relocation remains relevant if mappings are wrong. The
runtime scorebug is off in every preset and remains diagnostic. Its later
`ASTRA_SCOREBUG_FIX_REPORT.md` proves two native waits consistent with
audio-alive freezes: collection-busy loop `0x432D0 -> 0x432C0/0x38F50`, and
GPU-completion loop `0x33660` polling object `+8`, yielding at `0x341A0`, with
callback `0x33410`. Fixtures can withhold completion to keep either waiting;
neither was located in this reporter's stopped game. The direct TXTR OOM path
returns, so “extra texture memory means an infinite allocation loop” is not
proved. The measured extra 1.3535 MiB can still aggravate a nearly full heap.

**Minimal witness/proposal.** Preserve the booting Experimental recipe/hash
as a control, then build one optional owner at a time from the same original,
with its required allocator and paired archive changes. Match allocator layout
in a scaffold-only control. Do not accidentally include all optional content
through a saved recipe. For a failing compound owner, use its existing bounded
diagnostic probes (scorebug already has six); a Crib XBE-only versus paired
compaction experiment must be explicitly receipted, not an unsupported mixed
release image. Do not hand-patch away foreign/mixed validation to create a disc.

Expected distinguishing evidence: an XBE section/load rejection before guest
entry implicates loader layout, not a later menu; zero/failed roster allocation
or stalled callback points to arena/headroom; a failed named archive read,
wrong sector/length or decompression pin points to transport/resources; a
stable PC at the collection loop with pending I/O differs from a GPU wait;
an exception/fallback to frontend differs from a stable wait; a Practice Squad
failure only after its selection points to its callback; missing Guardian art
with a continuing game matches its fallback, not a boot crash. These are
expected observations to discriminate hypotheses, not logs observed here.

Capture cold boot continuously through game entry, exact recipe/hash and last
successful named read, stopped guest PC/call stack, outstanding I/O, heap
allocation result and GPU completion state where available. Record whether
the game returns to Berman or stays frozen with audio. Keep only one disposable
disc at a time and preserve the >=100 GB free-space floor. No new owner change
is justified until the first failing single-owner comparison is identified.

**FAQ.** Looping crowd audio does not identify the music owner. Separate a
SEGA wait from a game-load return and compare one content opt-in per disc.

## Validation, integration and delivery

New standalone suites run as `python3 tests/mod_editor/<name>.py`; Qt is
offscreen. Existing suites were run with `PYTHONPATH=.` where their legacy
standalone imports require it. No pytest or private disc mutation is required.

| Suite | Result |
| --- | --- |
| `test_discord_bugs_2.py` | 11 passed |
| `test_discord_bugs_2_wiring.py` | 6 passed; exact proposed sources executed in memory |
| `test_discord_bugs_2_research.py` | 4 passed; native pins/Capstone calls, preset and report-version checks |
| `test_nfl2k5_digit_sheet.py` | 3 passed |
| `test_apf_helmet_crest_design_product.py` | 13 passed |
| `test_apf_build_raw_span_overlays.py` | 7 passed |
| `test_apf_field_art_patch.py` | 26 run, 24 passed, 2 slow practice-overlay recompressions skipped (`APF_FIELD_ART_SLOW` unset) |
| `test_apf_field_art.py` | 6 passed |
| `test_apf_team_crest_selection.py` | 9 passed |
| `test_apf_project_streaming.py` | 6 passed |
| `test_studio_facade.py` | 11 passed |
| `test_nfl2k5_build_service.py` | 27 passed |
| `test_apf_project_document_workflow.py` | 13 passed |

Total: **142 run, 140 passed, two skipped**. Initial editor regression: six
tests, two failures/five errors including subtests. The protected-source
comparison with `ASTRA_TEST_UNWIRED=1` produces four failures/two errors; one
error comes from reaching a deliberately absent backend output instead of
refusing preflight. These red runs are expected reproduction, not final gate
failures. The fixed source-proposal patch passes `git apply --check` without
being applied. APF import checks pass; full release-stage validation remains
blocked by the four absent extractor files described above. The 2K5 release
closure requires the protected allowlist/import/source-pin handoff.

No XBE owner changed, so there is no new request, cave reservation or owner to
add to the two executable union gates; this job does not claim to have rerun
the entire unrelated owner matrix. All fixtures are bounded; no full disc or
pack is loaded into RAM. The final six existing editor suites measured peak
RSS at most 133,228 KiB. Logs and receipt scripts remain in `.scratch`, not
the commit; final disk, syntax and delivery checks are recorded there.

FAQ delivery is `docs/mod_editor/discord_bugs_2_faq.md`. Known gaps are the
protected integration, missing packaged extractor inputs, unavailable original
screenshots/clips, native Windows/macOS refusal witnesses, real APF multi-edit
acceptance and every listed played gameplay comparison. Decisions are made
and documented; no user questions or network access were needed.

Delivery uses the authorized bundle fallback: Git accepted the initial
explicit-path staging but refused the final update with a read-only
`index.lock` error. The final commit is created using isolated metadata under
`.scratch`, on `astra/r63-discord-bugs-2`, with parent
`24899d1feab227c6bc57260769724899be62d2a2`. The bundle is
`.scratch/r63-discord-bugs-2.bundle`. The working files retain the final
contents; the shared index may still reflect the initial staging snapshot.
Neither `ASTRA_BRIEF.md` nor `.scratch` is committed. Nothing is pushed.

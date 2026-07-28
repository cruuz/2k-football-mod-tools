# APF 2K8 Mod Studio — Status

The source code and UI identify as the retail-free **`0.1.0-alpha.46`**.
`0.1.0-alpha.34` remains preserved unchanged; its mode-`0444`,
815,213-byte archive has SHA-256
`beb8b1409b83e052e6c432a9ddc4a79f9f990820c79e0b67dea894dc869393f4`,
authenticated by the adjacent mode-`0444` `.sha256` sidecar.
`0.1.0-alpha.33` remains preserved unchanged; its mode-`0444`,
808,649-byte archive has SHA-256
`e071a6b42bbc5270c1cee2517c27c3115de03966977b1b178b92649e18982270`.
Alpha.32 also remains preserved unchanged.

The Alpha.34 seal completed headlessly. The exact 105-file/15-directory
allowlist stage (3,519,281 file bytes) passes the retail-free release gate
before and after the 67-module runtime closure
(`private=false retail=false symlinks=false undeclared=false`,
`extractor=reviewed`, `capabilities=31`), and the 120-member deterministic
rebuild is byte-identical. The authoritative cross-title product suite passes
**1156/1156**. The recognized source revision remains the seven read-only
hashes in the app's source ledger (original ISO plus `0A`, `0B`, `1A`, `1B`,
`default.xex`, and `$SystemUpdate/su20076000_00000000`); no source file is
changed. A separate independent hostile review and the real-source Xenia
visual/audio runtime proofs remain recommended before wide publication and
were not performed as part of this headless seal; identifying unknown cues or
proving authored audio audibly still requires later listening/controller input.

Alpha.34 adds `project_metadata_only_stable_logical_cue_id` across all **47,775
playable cues**: 2,261 standalone AUDO sounds and 45,514 individual AUSB
substreams. A selected sound can own one bounded custom title and/or multiline
note. The metadata is immediately searchable, **Labeled only** isolates named
discoveries, and collection-export metadata preserves the custom title, note,
game/catalog name, stable cue ID, and payload path.

Annotations persist in checksum/size/count-bound `audio-annotations.json` and
may form a valid annotation-only `.apf2k8mod` project. They participate in
recovery, Undo, Clear, Revert All, and project load, but remain outside modified
asset counts and the build document. Consequently an annotation alone never
receives a Modified badge, enables Build, enters APF, or authorizes replacement.
The annotation route contains no retail audio, decoded PCM, source path,
preimage, rollback byte, or replacement packet.

Alpha.33 adds `selected_exact_slot_xma1_or_pcm16_wav`: one selected-sound drop
target accepts a local regular `.xma` or exact PCM16 `.wav` for any of the
47,775 individually editable AUDO/AUSB rows. Both formats enter their existing
button-owned validator/writer path; links, directories, remote/multiple files,
unsupported rows, and busy PCM/direct/pack states are refused without mutation.
All Audio mutation/template controls fence from submission through exact worker
unregistration, and a rejected runner admission is explained.

Alpha.32 changes Audio replacement-pack admission to
`fully_validated_read_only_preview_then_explicit_apply`. Review validates every
supplied file first and reports supplied, would-change, already-current,
missing, current-modified-audio, and resulting-modified-audio counts without
staging an edit. Cancel and unchanged-only input are no-ops. Explicit Apply
reopens and revalidates the pack, then verifies an opaque token bound to exact
authored members, validated results, source, session, and current project-audio
revision. The confirmation continuation runs only after its preview worker and
lifecycle signal have drained.

Alpha.31 added one-action **Add all matching** Audio
shortlist curation across the exact applied query or Soundtrack album, with
stable deduplication, an atomic 256-sound ceiling, and a cached 47,814-row
filter result. Source switching and application close now cancel and drain
owned preview/waveform workers before the loaded private session is released;
rapid source selections coalesce to the latest request.

Alpha.30 makes preview and waveform decode genuinely
interruptible across original AUDO, original AUSB, and both staged exact-slot
replacement families. **Cancel preview**, **Cancel waveform**, selection
changes, and source transitions stop the request-owned FFmpeg/ffprobe process
group, discard partial private output, and silently drain stale results. A
rejected worker admission also returns immediately to **Play**.

Alpha.30's **792,312-byte** archive and mode-`0444` adjacent `.sha256` sidecar
remain preserved; its SHA-256 is
`6f0ca573707ba28d4fba296642e80a7337295d899605f9f3a93c90663819a999`.

Alpha.29 gave the 47,814-row Audio browser an applied
query/page token, exact-order one-level shortlist Clear/Undo, and request-owned
preview success/failure handling. Page-wide actions cannot consume a stale
table during the 180 ms search delay; selected-row actions keep their exact row
identity. A late preview result cannot start or report against a newer
selection, while a current failure restores retryable Play. The existing
transactional source-switch path was experimentally confirmed to preserve the
complete old Audio workspace after a failed or cancelled candidate load, so it
was not rewritten.

Alpha.29's **785,069-byte** archive and mode-`0444` adjacent `.sha256` sidecar
remain preserved; its SHA-256 is
`76c7e88786ffccb3a65a26acaa0698c3840b2be6fa46a6c663cfd22a9b76ea80`.

Alpha.28 adds metadata-only v2 folder/ZIP templates and
project-atomic exact PCM16 WAV batch import for all 47,775 individually
editable AUDO/AUSB sounds through a separately installed user-configured XMA1
encoder. One template may list the complete surface; one transaction accepts
at most 256 supplied WAVs. Legacy pre-encoded-XMA1 v1 packs remain the default,
byte-compatible, auto-detected route. It carries forward selected-sound PCM,
exact Position (17), native 0–99 ratings, pre-build free-space refusal, Ctrl+1
sidebar focus, a shared Ctrl+F search shortcut, larger-font-safe shell, and
descriptive accessibility text. Isolated visual QA, a real-encoder
compatibility run, authored-audio audibility proof, and the first
changed-position Xenia spot check remain pending.
Alpha.28's **781,027-byte** archive and mode-`0444` adjacent `.sha256` sidecar
remain preserved; its SHA-256 is
`33fe5e1e1c0c11001b159f8ee909f43a4640b6952e33a941753bd00230bd55df`.
Alpha.27's **772,445-byte** archive and its mode-`0444` adjacent `.sha256`
sidecar remain preserved; its SHA-256 is
`89e40ccf6e20e221137c634d170f7c7293a805efec7f820c5dd29c53e2b60c84`.
Packaged guides remain self-hash-free.
It retains alpha.13's capability-to-action parity, alpha.12's
93-scene Stadium Studio, alpha.11's complete 408-record Uniforms surface,
Gameplay and field-scorebug semantic workspaces, private whole-game Text Sheet,
Audio shortlist/reorder, 15-track stereo/mono Soundtrack album, recovery/
document workflow, bounded visual writers, and exact-byte access to all 19
named physical XMA1 banks.

Alpha.28 adds a v2 `apf2k8_mod_studio_audio_replacement_pack/v2` contract
beside the unchanged v1 pre-encoded route. The Audio workspace exposes
**Pre-encoded XMA1** and **Exact PCM16 WAV** before folder/ZIP template export;
import auto-detects either contract. V2 uses exact listed `pcm16/*.wav` paths,
accepts no more than 256 supplied WAVs per transaction, copies each WAV into a
private pinned input, and uses the existing configured encoder. The complete
set is admitted only after every output clears exact allocation, packet,
complete-decode, duration, target, baseline, alias, and cross-family source-
packet checks. Failure or cancellation stages no edit and adds no Undo action.

Alpha.27 added **Export PCM authoring template…**, **Configure XMA1 encoder…**,
**Replace from PCM WAV…**, and **Cancel PCM encoding** for a selected standalone
AUDO or semantic AUSB row. The generated template is deterministic exact-length
PCM16 silence and contains no source audio. The bridge passes only the selected
canonical WAV and a private output path through a literal no-shell argv to the
modder's separately installed native tool or Windows `.exe` via separately
installed Wine. Configuration lives in per-user application settings, not the
project. Encoder output remains untrusted until the existing RIFF, exact
allocation, packet, complete-decode, duration, alias, target, and cross-family
exact-source-packet checks all pass. Cancellation is checked before final
validation and immediately before staging; process-group cleanup covers every
success/failure/timeout/cancel path. Mod Studio cannot classify the copyright
or license of independently re-encoded PCM selected by the user.

Alpha.26 extended the retail-free batch audio authoring workflow to normal
folders and deterministic ZIP hand-offs for up to all **47,775** individually
editable sounds. The Audio tab creates a metadata-only template from current
filters, the 15-track Soundtrack album view, or the exact reviewed shortlist,
then imports supplied pre-encoded one-stream RIFF XMA1 files as one Undo action.
Each target and disclosed alias carries an optimistic replacement-only
baseline, so a stale template cannot overwrite a newer audio edit while
unrelated project work is left alone. Validation reports progress after each
complete file, and Cancel stops between files with no project mutation or Undo
entry. ZIP import privately materializes only bounded members and rejects path
traversal, symlinks/special entries, encryption, duplicate/case-colliding
names, wrappers, undeclared members, oversized expansion, and identity races.
Existing Alpha.25 folders remain accepted. The exact allowlisted Alpha.27 stage
and clean extraction pass the retail-free and isolated runtime gates. No
interactive desktop or emulator was launched.

Alpha.22 upgrades the 2,261
standalone `AUDO` rows from export-only to an experimental, target-exact XMA1
editor: Replace, individual Revert, Undo, project save/load, staged preview,
and typed Build are wired for pre-encoded one-stream RIFF XMA1. The writer is
**offline-writer-proved**. Its completed Xenia spot check is **runtime partial**:
the candidate booted, logged no XMA error, and survived five intended triggers,
but matched waveform and spectral tests did not prove audible cue consumption.
Alpha.28 accepts one selected exact-shape PCM16 WAV or a v2 pack containing up
to 256 supplied exact-shape WAVs through a separately installed encoder;
FLAC/MP3, mixed-format packs, and a bundled encoder remain unsupported.

Alpha.23 extends that strict exact-slot workflow to **all 45,514
semantic AUSB substreams** backed by **45,513 canonical physical ranges** in 19
external banks. Replace, individual Revert, Undo, project save/load,
replacement preview, and typed multi-pack Build are wired for pre-encoded
one-stream RIFF XMA1. One `cwdloop` physical range has two disclosed semantic
owners: identical alias edits deduplicate and divergent edits are rejected.
One soundtrack allocation—Track 3—crosses the end of `0A` and start of `0B`;
the pack-aware builder splits and source-guards both spans without changing or
repacking the bank descriptor. Projects contain only the user's canonical
packets and retail-free semantic metadata. Alpha.23 constructs one complete
fingerprint inventory of every `0x800`-byte source packet across both the 2,261
standalone AUDO slots and all 45,513 canonical AUSB ranges. Session admission,
project load, modified preview, and Build each reject a replacement containing
even one complete packet from either family, so a retail packet cannot be moved
between AUDO and AUSB or hidden inside an otherwise changed payload. The 40,316
unique whole-AUSB-payload hashes remain a useful inventory fact, not the
authorization boundary.

The private Alpha.23 runtime candidate booted, selected **Track 12 — Bury Me
Standing Remix**, and visibly remained in playback for 25 seconds without a
crash. The objective capture experiment is now complete and
**negative/inconclusive for modified-stream causality**: the final sustained
segment matched neither the mutated candidate nor stock Track 12; the best
17-second absolute normalized cross-correlation was about `0.031`, and
candidate-versus-stock distinguishing frames favored neither meaningfully. A
self-control confirmed that the classifier could distinguish the known inputs.
This therefore proves boot/selection/stability only. It proves neither authored
audio consumption nor stock fallback, so the runtime status remains partial.
The source soundtrack decoder sweep also remains an
important authoring caveat: FFmpeg 6.1.1 decoded 18 of 30 original stereo/mono
sides and rejected 12 otherwise packet-valid retail inputs. Replacement input
must still pass the stricter complete decoder check.

A real-source final Build gate scanned both source audio domains and rejected
an 8-bit-mutated Track 12 near-retail candidate at replacement packet 0. That
candidate had passed the older whole-payload-only check. The bounded gate run
completed in 14.13 seconds with 208,896 KiB peak RSS; no private path, hash, or
audio byte is recorded in this public status. This is retail-byte-protection
evidence, not modified-audio runtime-causality evidence.

Alpha.23 also adds an honest 32-team, 53-row roster planner. For each of the 32
populated source team records, rows 1–42 are the memberships APF currently sees
at runtime; rows 43–53 are eleven **project-only** reserve choices. Reserve
plans store only authored player indices and are not applied by Build. True
53-active-player teams still require a version-pinned emulator-target XEX
consumer/accessor patch plus owned side-table storage; the planner never claims
that stock APF sees those eleven reserves.

Post-seal static follow-up closed one unsafe longshot without changing the
sealed package: stock code reads and writes `team +0x120..+0x126`, so the
earlier idea of starting packed reserves at `+0x120` is falsified. The compact
17-byte representation still fits by size, but it needs a separately owned
ROST region or emulator-allocated side table. The bounded slot-43 experiment
therefore writes no team-tail byte and conditionally exposes one pinned test
player through one exact runtime consumer only.

That emulator experiment is now implemented and independently GO-reviewed.
The final traversal-scoped hook is pinned at Xenia source commit
`d145430737f787f522e08e7d86d3e94bdde6d6a1`; its native Linux binary has
SHA-256 `e8d7fda95239d12c11a1d2b336bbed33b39d1da738a65dc2e757c16b8d215641`.
The retail-free headless runner forces null GPU/audio/input, disables title
updates, PatchDB, and plugins, uses new storage/content/cache/home/XDG roots,
and hashes the complete source tree before and after. Its focused synthetic
suite passes. A valid passive observe control then booted the pinned Xenia for
the full 180-second bound, preserved the complete source tree and `default.xex`,
and completed `path_not_reached` with
`complete_target_receipts_not_seen`. Ordinary no-input boot therefore does not
exercise the exact defensive roster-builder path. Modified behavior remains
locked until a fresh observe run deliberately navigates into that path and
records `observe_path_proved`. The research runner and pinned Xenia binary are
not part of Mod Studio's public release.

A bounded headless static inventory has now mapped the next true-53 boundary.
The pinned XEX contains 30 direct calls to the primary position-count helper
and 63 direct calls to the matching ordinal getter, spanning 19 owner
functions. At least 25 roster-class routines also access count/membership
state directly; append routines `0x84AB9B70` and `0x84AB9D50` explicitly cap
the count at 42. Most importantly, `0x84AB93D0` allocates and sorts a fixed
17-by-42 pointer workspace: its stock 3,088-byte frame is too small for
17-by-53, so literal constant edits would overwrite stack state. This
falsifies a one-byte or one-helper complete patch, but it does not falsify an
emulator-owned side table plus coordinated consumer replacements. The
observe-only follow-up is a metadata-only memory-access census across roster,
depth, gameplay, substitution, injury, stats, postgame, and reload paths. The
passive slot-43 control above did not reach that path; the census still needs a
deliberately navigated isolated run. See the
[true-53 consumer inventory](../product/APF_TRUE_53_RUNTIME_CONSUMER_INVENTORY.md).

Alpha.20 upgrades the complete/selected Audio batch archive to
the self-describing
`apf2k8_mod_studio_audio_batch_export/v2` contract. Every requested semantic
row is represented in deterministic UTF-8 `catalog.csv`, successful playable
rows are ordered in `playlist.m3u8`, and the manifest records sanitized source,
bank, role, format, sample-rate, channel, duration, soundtrack-pairing, packet,
payload-size, and payload-SHA-256 metadata without placing an export into the
project. Zero successful sounds deliberately means no playlist member. The
same atomic no-overwrite, cancellation, source-fencing, and private-retail-data
boundaries remain in force.

Alpha.21 product-wired nonempty player
first/last-name Replace/Revert through the same bounded token-preserving ROST
compiler, adds complete local alias-owner disclosure, and broadens project-load
and Build admission through one centralized fail-closed scope. Its complete
product regression passes `648/648` in `90.763s`. The real-source public
Replace/Undo/Revert/project-reopen/Build/reparse smoke and isolated-display
visual QA both pass. Alpha.20 is preserved as an older sealed checkpoint at
SHA-256
`f3f02cbefbbcd5f0890efb889948e2a34487a9f07f0a2900744d44b19da56ef8`.
Alpha.21 is preserved as another older sealed checkpoint at SHA-256
`35b7d23298ce69639ad7e2a09b24be4838de6066d22963abaf0f387dd3d4e232`.

Alpha.19 turns that 19-bank access into one
explicit product action: **Export all original banks (19)…** writes every
physical XMA1 packet bank and a source-bound integrity manifest into one
private deterministic ZIP. The archive uses stable stored member paths,
records the exact size and SHA-256 of every bank, preserves every descriptor
owner and derived role, and marks every entry as an original rather than a
replacement. Publication is atomic and no-overwrite: a fatal safety or archive-
integrity failure cannot publish a partial destination, and an existing
destination is never replaced. An ordinary per-bank export failure is recorded
and later banks continue. Cancellation is checked between complete banks,
never midway through a bank copy, and the manifest accounts for every requested
bank as successful, failed, or cancelled. This export contains retail audio
and must remain private; it never enters a shareable `.apf2k8mod` project.

The current release has replaced the failed generic ROST recompressor with
a token-preserving compiler and exposes narrow, reversible player/team-name
editing plus all 28 independent player base ratings. Ratings
can be changed individually or through a guarded 2,254-player private CSV.
Rating edits use semantic player/attribute IDs and strict user-authored `0..99`
integers; an existing native `100` is displayed exactly and remains revertible.
This is native per-attribute editing of 28 independently stored rating bytes,
not a rescaled presentation layer. Overall is derived, while Gold/Silver/Bronze
tier, abilities, and roster structure are separate systems. Player-name,
team-name, rating, and exact Position (17) deltas compose into one rebuilt outer
entry. Position Apply and Revert author the native `+0x34` byte and required
`+0x35` mirror atomically; abbreviations, jersey numbers, membership, depth
charts, abilities, and Gold/Silver/Bronze tier remain product-locked and
separately scoped.

The runtime receipts are positive but carefully bounded. `Americans` →
`CODEXTEAM` booted through first-run team construction and rendered in Logo
Selection, Team Summary, and Team Select. Dan Marino Speed `40` → `99` changed
exactly one decoded byte, preserved 284,014 of 284,015 H7A tokens, booted, and
loaded/rendered his player card without the old `0x84AB1D40` startup crash.
APF has no numeric ratings screen, so the latter proves transport and player-
record consumption, not a measured on-field Speed effect.

The matching player-name experiment is now positive. Dan Marino's six-character
last-name allocation was changed `Marino` → `CODEX`; exactly six decoded bytes
changed inside its 14-byte allocation, 284,010 of 284,015 H7A tokens were
preserved, all 40 team names, all 120 team identity fields, and all 63,112 base
ratings stayed unchanged. Xenia visibly rendered both **Dan CODEX #13 QB** in
Gold-player selection and **QB #13 DAN CODEX - GOLD STAR** on the Star Card,
then exited normally without `0x84AB1D40` or an access violation. This proves a
bounded exact-allocation player first/last-name route; it does not automatically
prove either abbreviation family, jersey numbers, or roster-capacity changes.

Alpha.21 turns that bounded result into a reversible product route for 3,191
nonempty player-name allocations serving 4,482 writable first/last references.
Together with 40 team display-name allocations, the package exposes 3,231
product-editable name allocations. There are 429 shared editable player-name
allocations; the largest has 23 owners, and 61 span both first- and last-name
fields. The details panel lists every semantic owner and warns that one edit
changes them together. The zero-capacity empty allocation, abbreviations,
mixed/unknown scopes, jersey numbers, and roster structure remain locked.

**Export ratings sheet…** and **Import ratings sheet…** form one private,
spreadsheet-friendly bulk editor containing all 2,254 player rows and all 28
exact base-rating columns. The v2 sheet is source-bound, exports active project
values, publishes atomically with owner-only permissions, and never enters a
shareable project. Preview validates all 63,112 cells, distinguishes hard
source conflicts from explicitly confirmable project conflicts, and rechecks
the file plus active-edit fingerprint before one atomic Apply/Undo action.

The full-source v2 smoke covered 2,254 rows, 28 rating columns, indices
0..2253, exact observed range 0..99, Dan Marino Speed 40→99, confirmed conflict
replacement, Undo, project-ZIP inspection, and identical `0A` SHA-256 before
and after. This retail roster contains zero source-100 cells; native-100
preservation/revert remains an engine-compatible contract covered by the
focused synthetic fixture. All private CSVs were deleted after the smoke.

Alpha.14 gives Audio
an explicit, cancellable waveform loader that reuses the verified private WAV
route without decoding on selection; long PCM16 files are sampled within a
fixed memory bound and physical bank/index rows remain ineligible. The complete
Audio batch route accounts for all 47,814 semantic rows in one atomic XMA/WAV
ZIP: 2,261 standalone cues and 45,514 addressed substreams use the verified
single-sound exporter, while all 20 AUSB index rows and 19 physical-bank rows
are preserved in that cue-catalog manifest as unsupported. Alpha.19 adds a
separate whole-bank route for those 19 physical rows; it does not pretend that
a raw multi-cue bank is a directly playable or replaceable individual sound.

Alpha.20 makes the cue-catalog route self-describing rather than
requiring Mod Studio to interpret its manifest later. Both complete and
selected archives carry `catalog.csv`, successful rows carry exact exported
file size and SHA-256, and `playlist.m3u8` contains successes only. The root
manifest and completion receipt state payload bytes, catalog-record count, and
playlist-record count and hash the companion catalog/playlist members.

The dedicated Field Art workspace inventories 258 honest records in seven
groups and 125 packages without claiming texture ownership: 235 endzone
records, four field scenes, four radiance records, six divot/weather records,
three overlays, four practice scenes, and two penalty curves. Its semantic
search/filter and normal preview/export routes are wired; Replace/Revert remain
locked.

Rosters & Players exposes a bounded map of 3,273 fixed UTF-16BE allocations,
3,272 of which are nonempty. Those allocations serve 4,628 mapped player/team
identity references. The sealed Alpha.20 GUI enables exact team display names;
the current Alpha.28 source carries forward Alpha.21's 3,191 nonempty pure
player-name allocations and discloses every alias owner locally. Projects store
only authored replacement text and the established offset-free target contract,
not retail names, source strings, alias-owner lists, records, preimages, or game
bytes. Both abbreviation families remain runtime-unproved and inspection-only.
The old generic-rebuild negative remains diagnostic history, while the current
[team-name result](../product/APF_ROSTER_IDENTITY_TOKEN_PRESERVING_RUNTIME.md)
and [rating result](../product/APF_PLAYER_RATINGS_TOKEN_PRESERVING_RUNTIME.md)
document the token-preserving positive route. Jersey numbers remain read-only
because no consumer-backed field is identified.

Alpha.13's central change is capability-to-action parity: the shared registry
contains 31 APF capabilities and 62 capabilities globally, including a
dedicated editable `draft_logo` record, while every non-Coming-Soon APF card
binds to a real desktop handler and explicit actions. Six research-semantic
cards without such a handler are honestly downgraded to Coming Soon instead of
advertising an action the desktop cannot perform.

The previous Alpha.22 capability registry splits into 9 Editable, 5 Preview,
3 Export-only, and 14 Coming Soon across the 31 APF capability records. The
current Alpha.28 source resolves to 10 Editable, 6 Preview,
1 Export-only, and 14 Coming Soon; the AUSB capability is Editable only because
its concrete Replace/Revert/project/Build route is now wired.
**Rosters & Players** is Editable through its exact team-display-name and
per-attribute base-rating handlers and its bounded player-name handler.
Abbreviations, zero-capacity or mixed-owner
names, jersey numbers, and roster structure remain visibly locked. **Menus & Text** remains correctly Editable
through its real bounded in-place writer for
2,410 of 2,413 TXT/STRG allocations; it does not depend on a fictional file-
extension input. The hidden `jersey_06_runtime` record remains a proof alias
and does not create a duplicate desktop editor.

Stadium Studio inventories all 93 exact `stadium` SCNE records, derives a
source-hash-fenced private glTF on demand, and provides orbit, pan, zoom, reset,
surface picking, private scene-ZIP export, and same-outer package inspection.
The first untouched-source scene loaded 116 meshes, 112,158 vertices, and
68,669 source triangles. Material/TXTR ownership is still unresolved, so a
clicked surface never auto-selects a texture and Replace/Revert remain disabled.

The completed material experiments now explain that lock more
precisely. Its 116 mesh nodes produce 328 draw records that resolve to material
slots 0–112, all 113 serialized material records, and 13 shader families. None
of 737 unique named texture identities is statically referenced by the
scene-system material data, including the three same-package candidates. The
bounded runtime follow-up configured Xenia to stop at the renderer handoff, but
Wine intercepted the host instruction breakpoint before a game frame or guest
register capture. The private runtime configuration was restored byte-for-byte.
This completes that route without testing ownership; the best future route is
a small logging instrumentation build or native-Windows guest debugger, not a
repeat of the Wine breakpoint attempt.

Alpha.11 separates the 96 proved jersey/pants/helmet/shoulder material writers
from 312 additional uniform/equipment records without hiding or duplicating
anything. Sliders & Gameplay now contains 21 mapped stock slider definitions
and 17 retained draft-lineage weights; no current profile value or unproved
patch is presented as editable. Scorebug & Presentation now separates its
eight-row semantic map, bounded `digital_font` editor, and 25 raw assets.

Audio exposes 47,814 semantic rows: 2,261 standalone sounds, 20 AUSB
descriptors, all 45,514 addressable substreams, and 19 named physical packet
banks owned by 20 descriptor links. A physical bank can be exported exactly as
`.bin`, but it cannot Play, enter a shortlist, or Replace because it is a
multi-cue container. It can now also participate in the private all-19-bank
bundle without changing that limitation. Playable-row wording promises
WAV/Play only when that individual decode verifies.

The previous Alpha.22 package introduced editing for the 2,261 standalone rows through a
strict exact-slot route. Each supplied RIFF must contain one XMA1 stream whose
channels, sample rate, encoded allocation, packet headers, and decoded sample
count match the selected target. The project retains only canonical
user-supplied packets and bounded target-shape metadata. Its release-era gate
rejected exact whole-cue matches within the source AUDO family. Alpha.23
supersedes that family-local check with the cross-domain complete-packet
authorization described below.

Alpha.23 applies the same deliberately narrow authoring model to
all 45,514 AUSB substream rows. Those semantic rows resolve to 45,513 canonical
physical ranges: exactly one `cwdloop` range has two owners. The product
discloses both affected IDs before Replace; byte-identical edits through both
aliases collapse to one physical write, while different payloads targeting the
same bytes fail before publication. Of the physical ranges, 45,512 occupy one
pack span and the Track 3 stereo soundtrack range occupies two spans across
`0A`/`0B`. Build validates the live semantic target, the complete cross-domain
`0x800`-packet authorization inventory, and every individual source span, then
writes only the disposable staging copy. Session admission, project load, and
modified preview apply the same packet gate. The 19 complete physical bank rows remain raw private exports;
users edit their individually addressed substream rows rather than replacing a
whole opaque bank.

Alpha.13 also makes that boundary visually unambiguous:
physical-bank selection hides single-sound Play, says **Choose a sound to
shortlist**, and gives long technical identity text more width and height.
Global disabled styling covers primary, secondary, utility, Build, and Launch
controls, and Stadium shows **Replace (locked)** instead of a disabled control
that can retain active orange styling.

Alpha.5 added transactional Audio export for any
1–256 currently filtered playable rows as one original-XMA or verified-WAV ZIP,
including mixed AUDO/AUSB selections and a useful metadata manifest. This makes
bounded slices of the very large commentary banks practical while replacement
correctly remains disabled.

Alpha.6 adds a coordinate-stable Audio source/bank selector with playable
counts. It
intersects with search, kind, and role for paging, decoded export, and bounded
sound ZIP export, making every soundtrack or commentary bank directly
discoverable without knowing its hidden name first.

Alpha.7 adds a session-only Audio shortlist. A modder can collect up to 256
playable sounds across unrelated searches, pages, roles, and banks, see exact
selection badges/counts, and export the ordered selection through the existing
transactional original-XMA or verified-WAV bundle route. The shortlist holds no
audio bytes, never enters a project, and clears when the loaded model changes.

Alpha.8 gives `.apf2k8mod` projects normal document behavior: first Save names
the project, later `Ctrl+S` fast-saves the exact remembered file, Save As can
copy a clean named project, and the title distinguishes untitled, dirty named,
and clean named states. Dirty state no longer aliases replacement count, so a
final Revert All remains an unsaved zero-edit document until explicitly saved
or discarded. Expected-target fingerprints protect foreign files and project
opening validates into a candidate session before committing. Source/project
switches and close use Save/Discard/Cancel. Recent-project menus and automatic
crash recovery remain explicitly deferred to alpha.9.

Alpha.9 closes that deferred document-safety gap. It remembers the selected ISO
or extracted folder and protected projects, autosaves authored changes through
the same replacement-only project writer, and binds recovery to the selected
path plus recognized `0A` hash. Recover/Later/Discard, manual recovery, stale
disabled recents, coalescing, source fencing, and source-selective cleanup are
all product-wired. A postponed recovery for another source is preserved instead
of being overwritten. Playable Audio collection ZIPs also carry an ordered
`playlist.m3u8` beside their manifest.

Alpha.10 makes two already-owned data surfaces practical for real modding work.
The Universal Text inspector can export all 2,413 TXT/STRG allocations to one
private, source-bound UTF-8 CSV and atomically import valid replacements/reverts
as one Undo action. The sheet contains original game strings and therefore must
stay private; shareable projects still contain authored replacements only. In
Audio, **Review selected** exposes the exact shortlist insertion order with
local paging, play/export/remove, and Move up/down controls that determine ZIP
and playlist order, then restores the prior browser state. **Soundtrack album
(15)** exposes the paired `jukeboxmusic` stereo masters by default and the
`jukebox22` mono companions through a selector. Track numbers come from owned
bank indices; artist/title remain explicitly Unknown.

The packaged application has a complete per-user delivery path:
`install.sh`, `uninstall.sh`, a location-independent portable launcher, an
absolute app-menu command, atomic staged updates, and authenticated cleanup
that preserves every user-data directory. The release/runtime gates exercise
that lifecycle headlessly in an isolated home before a package can ship.

Last updated: 2026-07-28

## 0.1.0-alpha.46 candidate boundary — no APF change

- Source/UI identity is `0.1.0-alpha.46`. Version parity only.

## 0.1.0-alpha.45 candidate boundary — no APF change

- Source/UI identity is `0.1.0-alpha.45`. Version parity only; the 2K5 side
  gained the All Textures workspace and a corrected linear-texture decode.

## 0.1.0-alpha.44 candidate boundary — no APF change

- Source/UI identity is `0.1.0-alpha.44`. Version parity only; the 2K5 side
  fixed a tab regression and made capability cards honest about where editing
  actually happens.

## 0.1.0-alpha.43 candidate boundary — no APF change

- Source/UI identity is `0.1.0-alpha.43`. No APF capability or behaviour changed;
  the bump keeps the two products' shipped versions in step after a 2K5-only fix.

## 0.1.0-alpha.42 candidate boundary — shared PNG importer accepts real PNGs

- Source/UI identity is `0.1.0-alpha.42`. No APF capability changed.
- The shared PNG importer accepted only colour type 6 at bit depth 8,
  non-interlaced. Every colour type and bit depth the specification defines is
  now decoded and widened to RGBA internally.

## 0.1.0-alpha.41 candidate boundary — shared registry grew a textures surface

- Source/UI identity is `0.1.0-alpha.41`. No APF capability changed.
- The shared capability registry gained `nfl2k5.textures.all_p8` and a
  `textures` surface scoped to NFL 2K5, so the APF runtime gate's shared row
  count moved from 66 to 67. APF's own 34 capabilities are untouched.

## 0.1.0-alpha.40 candidate boundary — the game partition is found, not guessed

- Source/UI identity is `0.1.0-alpha.40`. No capability changed.
- A legally dumped disc could be refused with "does not appear to be a valid
  xbox iso image". The bundled `extract-xiso` probes exactly four partition
  offsets (`0`, `0x0FD90000`, `0x02080000`, `0x18300000`) and rejects anything
  else -- the same defect the 2K5 lane was fixed for, hidden in a vendored
  binary. The disc is now read with the project's own XDVDFS reader first,
  which searches sector-aligned positions for the magic and confirms a
  candidate at both ends of the header sector; `extract-xiso` stays a fallback.
- A disc for another console is now named rather than called invalid. The
  prompting report was the PlayStation 3 release of the same game, named
  `.iso`. ISO 9660 volumes, PS3 discs, STFS packages and ZIP/RAR/7z archives
  are identified by structure and reported by name.
- Only the six files the editor reads are extracted: the supported USA dump
  resolves in ~26s and 3.9 GB rather than unpacking the whole 7.8 GB disc.
- The identity ledger is unchanged and all six files come out byte-identical
  to it.

## 0.1.0-alpha.39 candidate boundary — a disc image is identified by its contents

- Source/UI identity is `0.1.0-alpha.39`. No capability changed.
- Selecting an APF disc image no longer requires the whole container to hash
  to the project's own rip. Xbox 360 dumps vary as much as original-Xbox ones,
  and the real identity check already ran straight afterwards against the
  per-file ledger (0A/0B/1A/1B and default.xex by exact size and hash). The
  container gate refused legal dumps before that stronger check could run --
  the same defect the 2K5 side was fixed for. The container hash is still
  recorded and still keys the extraction cache; it is simply no longer a gate.

## 0.1.0-alpha.38 candidate boundary — text output is LF everywhere

- Source/UI identity is `0.1.0-alpha.38`. No capability changed.
- Every shipped module now pins the line ending when it writes text. Text mode
  on Windows rewrites `\n` as `\r\n`, so any generated file later hashed or
  size-checked could never match. 38 call sites across 29 files.

## 0.1.0-alpha.37 candidate boundary — sibling imports on installed Windows

- Source/UI identity is `0.1.0-alpha.37`. No capability changed.
- Fixed: shipped `tools/*.py` import each other, and the embeddable CPython the
  installer ships defines `sys.path` from its `._pth` without adding a script's
  own directory. `apf_texture_patch` and `apf_roster` among others therefore
  raised ModuleNotFoundError on installed Windows copies only -- never from the
  tarball, never in CI. Each shipped tool now restores its own directory, and
  the `._pth` lists `app\tools` as a second guard.

## 0.1.0-alpha.36 candidate boundary — failed-build cleanup on Windows

- Source/UI identity is `0.1.0-alpha.36`. No capability was added, removed or
  re-graded; the registry stays at 65 capabilities.
- Fixed: every `_abort_reserved` unlinked the failed output while its descriptor
  was still open. Correct on POSIX, impossible on Windows, and the resulting
  PermissionError was swallowed, so a failed build left a stray partial output
  and the next build refused to overwrite it. The unlink is now retried after
  the close, so POSIX keeps its window-free ordering and Windows still cleans up.
- Surfaced by an outside contributor's stricter test on the Windows runners;
  every test of ours that reaches this path is gated on retail data.

## 0.1.0-alpha.35 candidate boundary — Windows texture writers

- Source/UI identity is `0.1.0-alpha.35`. No capability was added, removed, or
  re-graded: the registry stays at 65 capabilities and every ladder position is
  unchanged. This boundary exists because four shipped writers could not run at
  all on Windows.
- Fixed: `tools/apf_field_art_patch.py`, `tools/apf_logo_patch.py`,
  `tools/apf_logocache_patch.py` and `tools/apf_texture_patch.py` passed
  `os.O_CLOEXEC` to `os.open` as a bare attribute. CPython on Windows does not
  define that name, so each raised `AttributeError: module 'os' has no attribute
  'O_CLOEXEC'` before doing any work. `tools/apf_uniform_mip_patch.py` inherited
  the fault through `archive_patch._reserve_new`. Field art, team logos, the
  logo cache, the generic texture writer and uniform mips were therefore all
  unusable on Windows; a user reported it against the endzone flow.
- The flag is now `getattr(os, "O_CLOEXEC", 0)`, matching the 284 sites that
  already used that form. **No guarantee is weakened by the fallback to `0`:**
  PEP 446 makes every descriptor CPython creates non-inheritable on all
  platforms, so close-on-exec is enforced by the interpreter rather than by this
  flag. The descriptor-ownership, inode-identity and fail-closed refusal
  contracts are byte-for-byte the ones alpha.34 proved.
- Guarded against recurrence by
  `tests/mod_editor/test_shipped_tools_posix_only.py`, which needs **no retail
  data** — the reason the previous suite reported Windows/macOS/Linux parity and
  still shipped this. It scans every file in both release allowlists for bare
  POSIX-only `os.open` flags, and it deletes those names from `os` to drive each
  shipped writer's real reservation path, asserting the fail-closed refusal still
  refuses for the right reason. Both discover their targets from the allowlists,
  so a writer added later is covered without editing the test.

## 0.1.0-alpha.34 candidate boundary — release prep in progress

- Source/UI identity is `0.1.0-alpha.34`. The Audio workspace exposes **Your
  cue label & notes**, **Save label**, **Clear**, annotation-aware search, and
  **Labeled only** for exactly 47,775 playable cues under
  `project_metadata_only_stable_logical_cue_id`.
- One annotation owns only a stable standalone-AUDO or individual-AUSB cue ID,
  custom title, and note. The bounded `apf2k8_audio_annotations/v1` document
  rejects container IDs, duplicate cue IDs, excess rows/text, control/format
  characters, and ambiguous duplicate JSON keys at the project boundary.
- `.apf2k8mod` binds `audio-annotations.json` by exact filename, SHA-256, size,
  and count. Annotation-only projects are valid and recoverable. Labels and
  notes participate in project mutation history but remain separate from
  replacement modifications and the composed build document.
- Matching/shortlist Audio export metadata carries custom title, note, and the
  preserved game/catalog name. Playlist display prefers the custom title; the
  logical cue ID, export identity, and payload path remain stable.
- Release work is intentionally unfinished: the allowlist and 67-module import
  closure are prepared, but exact feature-source pins, synthetic clean-stage
  runtime proof, final tests, staging, deterministic packaging, and independent
  audit wait for core/GUI freeze. Alpha.33 remains the sealed release.

## Five-line Alpha.34 status

- **Shipped:** source-level release preparation for the retail-free per-cue label/note workflow; no Alpha.34 package has been claimed or published.
- **Experiment result:** the pre-change Alpha.33 clean extraction still passes its 104-file retail-free and 66-module runtime gates; Alpha.34 final tests are pending feature freeze.
- **Blocked on the user:** nothing blocks headless implementation or packaging; assigning accurate cue titles still requires later human listening.
- **Next step:** freeze core/GUI, add exact source pins and a synthetic annotation runtime exercise, run the complete suites, then stage and independently audit Alpha.34.
- **Deliberately not done:** no Alpha.34 hash, archive size, package metrics, sealed status, audio-runtime claim, active desktop use, or mouse control is asserted before those gates pass.

## 0.1.0-alpha.33 candidate boundary — sealed receipt

- Source/UI identity is `0.1.0-alpha.33`. The selected-sound Audio panel adds
  **Drop .xma or exact PCM16 .wav here** under the contract
  `selected_exact_slot_xma1_or_pcm16_wav`.
- One captured editable row owns the drop. `.xma` dispatches to the established
  standalone AUDO or AUSB-substream exact-slot writer; `.wav` dispatches to the
  established user-configured encoder bridge. Both keep the existing Undo,
  project, source-packet, decode, shape, alias, and Build boundaries.
- Admission accepts exactly one local regular non-symlink `.xma` or `.wav`.
  Raw banks/index rows, directories, links, remote URLs, multiple files, other
  extensions, active PCM/direct-XMA1 encoding/replacement, and active pack
  review/Apply are refused before mutation. All Audio mutation/template controls
  stay fenced from submission through worker-idle. No encoder or retail audio is added.
- The focused lifecycle/drop selection passes 17/17, independent review's
  relevant GUI/backend selection passes 68/68, the complete APF suite passes
  504/504, and the combined cross-title suite passes 1113/1113. Independent
  review is GO with no P0/P1 finding.
- The exact stage and clean extraction each contain 104 files, 15 directories,
  zero links/bytecode, and 3,458,863 file bytes. Both pass the retail-free
  release gate, 66-module runtime gate, desktop validation, four shell syntax
  checks, and post-runtime release recheck. The 119-member deterministic rebuild
  is byte-identical. The mode-`0444`, 808,649-byte archive is
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.33-linux-x86_64.tar.gz`; its
  authoritative adjacent sidecar records SHA-256
  `e071a6b42bbc5270c1cee2517c27c3115de03966977b1b178b92649e18982270`.
  Alpha.32 and Alpha.31 re-verify unchanged; temporary verification output was
  moved recoverably to Trash.

## Five-line Alpha.33 sealed status

- **Shipped:** Alpha.33 is sealed with selected-sound `.xma`/exact-PCM16 `.wav` drag and drop through the existing safe writers; Alpha.32 remains preserved unchanged.
- **Experiment result:** 17/17 focused lifecycle/drop, 68/68 independent relevant, 504/504 APF, and 1113/1113 combined checks pass; stage/extraction gates and deterministic rebuild are green.
- **Blocked on the user:** real-tool compatibility and audibility need a legally obtained XMA1 encoder plus independently authored PCM. Configure it in **Audio → Configure XMA1 encoder…**, create a PCM16 pack or selected template, import it, then return the exact tool/version/argv and accepted project or error. True-53 observation still needs deliberate isolated controller navigation into a roster/depth/gameplay path.
- **Next step:** return to 2K5 for project-backed Audio cue labels/notes, then bring the same discovery workflow to APF where its project schema allows.
- **Deliberately not done:** Alpha.33 does not bundle/certify an encoder, accept FLAC/MP3, weaken validation, prove authored audio is consumed, claim positions or rows 43–53 are runtime-active, or use the active desktop/pointer for visual QA. Re-encoded audio rights remain the mod author's responsibility.

## 0.1.0-alpha.32 candidate boundary — sealed receipt

- Source/UI identity is `0.1.0-alpha.32`. The reviewed candidate was sealed as
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.32-linux-x86_64.tar.gz` with
  mode `0444`, size 804,083 bytes, and authoritative SHA-256
  `d80e690d3eec13b962ecaa96d6b2f725f0e2beaa71d8ce137a860e4d67735de1`.
  Its adjacent 119-byte mode-`0444` sidecar passes `sha256sum -c`. Alpha.31's
  sealed artifacts remain unchanged.
- `AUDIO_REPLACEMENT_IMPORT_CONFIRMATION_CONTRACT` is
  `fully_validated_read_only_preview_then_explicit_apply`. The preview receipt
  is sanitized count metadata plus an opaque token; it contains no audio bytes,
  extracted member path, source fingerprint inventory, or member/result hash.
- The private confirmation token binds exact supplied member hashes and fully
  validated result hashes to the manifest/baseline, loaded source, private
  session nonce, and current project-audio revision. Apply reopens the named
  folder/ZIP, revalidates it under the existing session lock, compares the
  token, and commits only an identical reviewed outcome.
- Cancel, validation cancellation, and unchanged-only review add no project
  edit and no Undo action. Preview-only unreferenced packet cache is discarded.
  A successful nonempty Apply still commits one atomic Undo snapshot and only
  then invalidates the prior build receipt.
- GUI confirmation is queued after the completed preview worker so its finish
  and audio-import lifecycle signals drain before a dialog or second worker.
  The focused four-suite Audio result is 98/98, the complete APF result is
  496/496, and the combined cross-title result is 1105/1105.
- The exact stage contains 104 files, 15 directories, 0 symlinks, and 3,440,321
  file bytes. Stage and clean extraction each pass the retail-free release gate,
  66-module runtime gate, desktop validation, shell syntax, and post-runtime
  release recheck. Its 119-member deterministic rebuild is byte-identical.
  Independent review is GO with no P0/P1 finding. Temporary verification output
  was moved recoverably to Trash.

## 0.1.0-alpha.31 packaged boundary

- Alpha.31 is the current packaged retail-free source/UI identity. Alpha.30's
  release tree, archive, and authoritative sidecar were not modified.
- **Add all matching (N)** reads only the exact applied query/model token or
  Soundtrack album rows, excludes already selected IDs, preserves stable
  catalog order, and either adds the complete set or adds nothing at the
  256-sound ceiling. It starts no worker, writes no edit, and stores no audio.
- One applied-query/album cache prevents selection-only button refreshes from
  rescanning all 47,814 decoded rows. Every model/game transition clears it.
- Close and source switching cancel the exact Audio preview/waveform token,
  leave its worker registered until it drains, then close or replace the loaded
  private session. Multiple queued sources collapse to the latest. A protected
  build/export still uses the established wait-before-close dialog.
- Source tests pass 32/32 focused Audio GUI and 487/487 complete APF.
  Independent review is GO with no P0/P1 blocker. The 104-file stage contains
  15 directories, 3,403,930 file bytes, 22 executables, and 71 Python files.
- Stage and clean extraction pass the retail-free release gate with
  `private=false`, `retail=false`, `symlinks=false`, and `undeclared=false`,
  plus the 66-module runtime gate. The 119-member archive rebuild is
  byte-identical. Its size is 795,740 bytes and its authoritative SHA-256 is
  `d0e5bd23a56881574a56760709ca87dd76e47bdbe5a431b1f67be57e56c19e5a`.
  The archive and adjacent sidecar are mode `0444`; Alpha.30 re-verifies
  unchanged.
- Packaging and QA used no active desktop, pointer, emulator, private game
  source, retail audio, or encoder. Temporary clean-extraction/rebuild outputs
  were moved recoverably to Trash after verification.

## 0.1.0-alpha.30 packaged boundary

- Alpha.30 is the current packaged retail-free source/UI identity. The visible
  desktop version is derived from `mod_editor.apf_studio.__version__`.
  Alpha.29's release tree, archive, and authoritative sidecar were not modified.
- The preview and waveform controls own one exact `(model epoch, row ID,
  generation)` request plus a thread-safe cancellation event. While work is
  active the same control becomes **Cancel preview** or **Cancel waveform**;
  after cancellation it reports **Cancelling…** until the worker exits. No
  second preview can enter that lane, and rejected admission restores **Play**.
- The optional callback crosses facade, session, private asset I/O, AUDO/AUSB
  export, and both exact-slot decoders. Cancellable FFmpeg/ffprobe processes
  are new session leaders; TERM, bounded drain, KILL escalation, and process-
  group existence checks cover Cancel, timeout, and callback failure. The old
  no-callback command-line route remains unchanged.
- Source previews stage privately before publication. Modified previews use a
  hidden same-directory WAV and no-replace link. Cancellation before receipt
  publication removes that request's output and receipt, while an already
  validated cache entry remains receipted and intact.
- Source tests pass 29/29 Audio GUI, 9/9 waveform, 7/7 decoder-cancellation,
  and 480/480 complete APF. The packaged runtime gate emits explicit preview
  and waveform process-cancellation receipts in addition to the Alpha.29
  query, shortlist, and preview-ownership receipts.
- Packaging and QA used no active desktop, pointer, emulator, private game
  source, retail audio, or encoder. The release contains only exact allowlisted
  program/docs assets and the existing separately licensed XISO extractor.

## 0.1.0-alpha.29 packaged boundary

- Alpha.29 is the current packaged retail-free source/UI identity. The visible
  desktop version is derived from `mod_editor.apf_studio.__version__`.
  Alpha.28's release tree, archive, and authoritative sidecar were not modified.
- The Audio browser applies a token over model epoch, search, kind, role,
  source/bank, and page offset only after publishing the matching table.
  Add-this-page, pagination, matching/template export, and filtered decoded-row
  export are both visibly disabled and guarded while a new query is pending.
  Fast type/erase restores the exact already-published page without a query.
- Shortlist Clear stores only the ordered decoded row metadata already held by
  the session; it never stores audio bytes, enters a project, emits an edit, or
  starts a worker. Undo restores once and does not reopen Review. Any real
  shortlist mutation or decoded-model change destroys the snapshot.
- Preview preparation catches its own decoder result and delivers an owned
  success/error tuple. Only the matching `(model epoch, row ID, generation)`
  may start a player or show an error. Current failure resets Play; selection
  or model change invalidates the request and makes late completion silent.
- The declared closure contains exactly 104 regular files, 15 directories
  including the root, 22 executables, 71 Python files, and 119 sorted safe tar
  members. The allowlisted release gate reports `private=false`, `retail=false`,
  `symlinks=false`, and `undeclared=false`; the isolated runtime gate emits all
  three Alpha.29 Audio lifecycle receipts.
- Source tests pass 26/26 focused and 466/466 complete. Independent review is
  GO with no P0/P1/P2 issue in the changed lifecycle. Packaging used no active
  desktop, pointer, emulator, private game source, or retail audio.

## 0.1.0-alpha.28 packaged boundary

- Alpha.28 is the current packaged retail-free source/UI identity. The visible
  desktop version is derived from `mod_editor.apf_studio.__version__`; no second
  GUI version string needs manual synchronization. Alpha.27's archive and
  checksum sidecar were not modified.
- Audio batch template export now offers unchanged v1 **Pre-encoded XMA1** or
  v2 **Exact PCM16 WAV** for folders and ZIPs. V2 manifests use schema
  `apf2k8_mod_studio_audio_replacement_pack/v2`, list generated `pcm16/*.wav`
  paths and exact target shapes, and contain no original audio, source-owned
  names, encoder binary, preimages, rollback bytes, or replacement payloads.
- A v2 template may list all 47,775 editable sounds; import accepts at most 256
  supplied WAVs. Each must be exact signed little-endian PCM16 with the listed
  channels, sample rate, and frame count. Import auto-detects v1/v2. V1 output
  keeps its Alpha.26/27 schema, README, default selection, and deterministic
  bytes, and a v1 import never requires an encoder. Folder v2 import refuses
  entry 257 before opening or hashing any WAV byte; ZIP v2 applies the ceiling
  before extracting payload members.
- V2 inputs are identity-pinned, privately copied, encoded individually, and
  passed through the existing exact-slot validators. The active edit map swaps
  only after the full supplied set, optimistic target baseline, and AUSB alias
  groups pass; success is one Undo action. Failure/cancel removes only new
  unreferenced work and changes no edit, Undo state, or last valid build.
- The shared shell owns one window-wide **Ctrl+F** shortcut and targets only an
  enabled search field visible in the active workspace. Headless Qt coverage
  checks dispatch and the no-search status message; this is not visual or
  screen-reader certification.
- The focused product gate passes 115/115 and the complete APF suite passes
  457/457. The exact allowlisted stage and independent clean extraction pass
  the retail-free release and source-free runtime gates. Deterministic archive
  reproduction is byte-identical. No GUI, active desktop, emulator, real XMA1
  encoder, or private game source was used while sealing this package.

## 0.1.0-alpha.27 packaged boundary

- Alpha.27 is the previous packaged retail-free source/UI identity. The visible
  desktop version is derived from `mod_editor.apf_studio.__version__`; no second
  GUI version string needs manual synchronization.
- Every individually editable Audio row keeps **Replace with XMA1…** and adds an
  exact PCM16 silence template plus selected-WAV authoring through a trusted,
  separately installed external encoder. Native and Wine modes use a bounded
  literal argv without a shell. Encoder paths, Wine path, argv, and timeout are
  local settings and never enter `.apf2k8mod`.
- The final encoded result receives no trust. Existing AUDO/AUSB exact-slot,
  complete-decode, alias, source/target, and cross-family exact-source-packet
  gates run before one ordinary Undo-able edit is staged. Cancellation before
  validation or commit changes no edit/Undo/build state; newly created,
  unreferenced cache data is removed. Owned process groups are terminated and
  drained on success, nonzero exit, timeout, cancel, and exceptions.
- The declared closure contains exactly `104` regular files, `15` directories
  including the root, `3,297,442` total file bytes, `22` executables, `71`
  Python files, and `119` sorted safe tar members. The exact stage
  and independent clean extraction pass the retail-free release gate and the
  `66`-module / `31`-capability source-free runtime gate; deterministic
  re-archive comparison is byte-identical. The authoritative archive identity
  is only in the adjacent `.sha256` sidecar.
- Final root runs pass 442/442 complete APF tests, 65/65 focused release/GUI
  tests, and 44/44 slot-43/census tests. Independent adversarial review is GO.
  Synthetic encoders prove only process/validator plumbing: no real XMA1 tool,
  interactive desktop, or emulator was launched for this package.

## 0.1.0-alpha.26 packaged boundary

- Alpha.26 is the previous sealed retail-free source/UI identity. The visible desktop
  version is derived from `mod_editor.apf_studio.__version__`; no second GUI
  version string needs manual synchronization.
- Audio batch authoring now exposes **Editable folder** and **ZIP hand-off**.
  Both select the same filters/album/review set and feed the same exact-slot
  AUDO/AUSB writers, optimistic baselines, cancellation, and one-action Undo.
- ZIP templates are metadata-only and deterministic. Edited ZIPs must keep
  `replacement-pack.json`, `README.md`, and `xma1/` at the archive root. Import
  accepts normal stored/deflated, unencrypted ZIPs and privately cleans its
  bounded extraction after success or failure.
- Alpha.25 template folders remain accepted, including their original generated
  README. Alpha.25 remains the prior sealed retail-free package; the Alpha.26
  promotion did not alter, rebuild, or supersede its authenticated archive.
- The shared shell adds window-wide **Ctrl+1** sidebar focus, strong keyboard
  focus outlines on category and asset lists, flexible header/footer heights
  for larger system fonts, and descriptive accessibility text for navigation,
  operation status/progress, Build, and Launch. Headless Qt coverage checks
  these contracts without claiming completed visual or screen-reader QA.
- The workflow still accepts only target-exact, pre-encoded one-stream RIFF
  XMA1. It adds no WAV/FLAC encoder and makes no new in-game consumption claim.
  No interactive desktop or emulator was launched while assembling or checking
  the Alpha.26 package.

## 0.1.0-alpha.25 packaged boundary

- Alpha.25 is the previous sealed retail-free Linux checkpoint. Its adjacent checksum
  sidecar is authoritative; packaged documentation deliberately contains no
  circular self-hash or local-machine path.
- The declared public closure contains exactly `101` regular files and no
  source game, retail payload, private replacement/template, Xenia binary,
  symlink, hardlink, special file, or undeclared path.
- The stage and independent clean extraction pass the retail-free release gate
  and the `65`-module / `31`-capability source-free runtime gate. Their file
  bytes and normalized modes match; a deterministic re-archive is byte-identical.
- The pack-specific suite passes **32/32** and the final root-selected audio,
  build, and project closure passes **128/128**. Independent adversarial review
  is GO after two reproduced blockers were fixed before sealing.
- Alpha.25 remains an exact-slot, pre-encoded one-stream RIFF XMA1 workflow.
  It has no distributable WAV/FLAC/MP3-to-XMA1 encoder and makes no new runtime-
  consumption claim. No package step launched a GUI or emulator.

## 0.1.0-alpha.24 packaged boundary

- Alpha.24 is an older sealed retail-free Linux checkpoint. Its adjacent checksum
  sidecar is authoritative; packaged documentation deliberately contains no
  circular self-hash or local-machine path.
- The declared public closure contains exactly `100` regular files, including
  the self-contained true-53 consumer inventory. It contains no source-game
  file, retail payload, private experiment output, Xenia binary, symlink,
  hardlink, special file, or undeclared path.
- The stage and an independent clean extraction pass the retail-free release
  gate and the `64`-module / `31`-capability source-free runtime gate. Their
  file hashes and normalized modes match, and the deterministic extraction
  re-archive is byte-identical.
- The focused source gate passes **163/163** tests, including Position (17),
  composite ROST editing, project/recovery paths, capability/action parity,
  installer/runtime closure, and APF/2K5 build-space refusal.
- Position (17) is offline-writer-proved and packaged, but its first changed-
  position Xenia consumption check and isolated visual QA remain pending. No
  Alpha.24 package step launched a GUI or emulator or addressed the user's
  active desktop or pointer.

## Post-Alpha.24 membership-census checkpoint

- The observation-only hook and its direct Linux hostile-thunk sentinel are
  committed at `d09cae8d8374324048ef603d48a9c1696b39d552`.
- The exact reviewed `xenia_canary` SHA-256 is
  `712df8acf4886bbc917713a7b5e120140d57b3a59a0c98e4f5ff6b5f8a47187d`.
  The runner now rejects every other live binary/commit pair.
- The stable retail-free local checkpoint is
  `artifacts/apf_membership_census_xenia_d09cae8d/`; its exact binary, source
  patches, license, and checksum manifest verify cleanly.
- Sentinel 1/1 (22 assertions), backend 18/18 (88 assertions), full CPU
  247/247 (845 assertions), and runner/safety 43/43 all pass.
- This unlocks the controlled boot experiment only. No Xenia/game process was
  launched, the static-ledger pin remains locked, and no claim about true
  53-active rosters has changed.

## 0.1.0-alpha.23 sealed release receipt

- Package status: historical sealed retail-free Linux checkpoint; Alpha.26 is
  the current packaged checkpoint, Alpha.25 is the
  previous sealed package, and Alpha.24/Alpha.22 are older. Alpha.23 release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.23-linux-x86_64/`.
  The adjacent archive is `682,202` bytes with SHA-256
  `ca1f5ed0f3dab91f373a520e664cbdb59d1f30afc2844e83c3ed76204a039c67`;
  its `119`-byte mode-`0444` sidecar verifies.
- Seal inventory: the stage and independent clean extraction each contain
  exactly `96` allowlisted regular files, `15` directories including the root,
  `2,920,207` file bytes, `22` executables, and `67` Python files. The tar has
  `111` sorted safe members. There are no symlinks, hardlinks, special files,
  undeclared files, private runtime artifacts, source-game files, or retail
  payloads. Two direct archives and one re-archive of the clean extraction are
  byte-identical.
- Independent gates: stage and extraction each passed the retail-free release
  gate before and after runtime, the `62`-module / `31`-capability source-free
  runtime gate, the private-source gate at `10,464` universal rows / `96`
  editable uniforms / `408` complete equipment rows, desktop validation, all
  four Bash syntax checks, the exact Alpha.23 version check, and AST parsing of
  all `67` packaged Python files.
- Product checks: the full product suite passes **722/722 in 93.739s**. The
  dedicated cross-domain audio-safety suite passes `4/4`, the focused combined
  audio/build suite passes `25/25`, and the complete headless APF source suite
  passes `348/348`.
- Visual closure: Spark previously approved the fresh Alpha.23 Audio/Soundtrack
  screen on isolated `DISPLAY=:99` with no clipping, overlap, or spacing defect.
  The sealed `gui.py` and launch wrapper are byte-identical to that approved
  source at SHA-256 `0ccc9c88a7cec85292456ff8cac0572a65b3e9858dcaea370dc87dc2af3c3f34`
  and `e924207810c3ec3cf670ac475cd0c3f478e86698f49d2111e673f44ac40766a0`.
  No second GUI launch was needed, and the user's live display and pointer were
  never addressed.
- Audio safety: session admission, project load, modified preview, and Build
  inventory every whole payload and complete `0x800`-byte packet across the
  2,261 AUDO slots and 45,513 canonical AUSB ranges. An exact source payload or
  any source packet is rejected across either family; no source fingerprints,
  packets, preimages, or private paths enter a project/public receipt.
- Runtime boundary: the private Track 12 candidate proved boot, selection, and
  stability. Its final sustained capture matched neither mutated candidate nor
  decoded stock Track 12, so authored-audio consumption and stock fallback both
  remain unproved.
- Roster boundary: the 32×53 surface is a planner. Stock APF consumes 42
  memberships per populated team; rows 43–53 are project-only reserves and
  Build does not apply them. True 53-player runtime teams require a version-
  pinned emulator-target XEX accessor/consumer patch plus owned side-table
  storage, and offline selector ownership for teams 25–32 remains unproved.

## 0.1.0-alpha.22 release receipt

- Package status: previous sealed retail-free Linux checkpoint. Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.22-linux-x86_64/`.
  The adjacent archive is `633,190` bytes with SHA-256
  `f2adf77b9abdeddd1b2c2bf93fd2523a93eb721a192543c7660ba3e49b4578fb`;
  its `119`-byte mode-`0444` sidecar verifies.
- Seal inventory: the stage and independent clean extraction match exactly at
  `92` allowlisted regular files, `15` directories including the root,
  `2,706,017` file bytes, and `22` executables. Their canonical
  path/type/mode/size/content inventory SHA-256 is
  `75e647061b379f1970448d85847ed12b8bbbdeb2064b8ff04112dc60036f1629`.
  The tar contains `107` safe members. There are no links, special files,
  undeclared files, private runtime artifacts, source-game files, or retail
  payloads.
- Independent gates: two deterministic archives were byte-identical. Stage and
  extraction each passed the retail-free gate before and after runtime, the
  `59`-module / `31`-capability source-free runtime gate, the private-source
  gate at `10,464` universal rows / `96` editable uniforms / `408` complete
  uniform-equipment rows, desktop validation, all four Bash syntax checks, and
  the exact `0.1.0-alpha.22` headless version check. All `64` packaged Python
  files parse.
- Product checks: the Alpha.22 APF-focused suite passed `300/300`; the strict
  exact-slot validator passes `23/23`; focused Audio GUI coverage passes
  `20/20`. The sealed and source GUI are byte-identical at SHA-256
  `e12724fb3bf8e27540b8320dffa89f2ba4094761e2ee5707a9899c874bf23973`.
  Spark Hands inspected the recognized-source Audio window only on isolated
  `DISPLAY=:99`: **Alpha 22 • retail-free**, all `47,814` rows, enabled
  **Replace with XMA1…**, correctly disabled Revert for an original sound, and
  the advanced WAV/FLAC warning were visible without clipping.
- Runtime scope: the one-span candidate and byte-identical stock control both
  booted and completed five intended Schedule-enter cycles. No XMA fault or
  stability failure occurred. Waveform and 160-set spectral controls remained
  non-significant, so audible consumption is explicitly inconclusive and the
  capability remains offline-writer-proved/runtime-partial.
- Prior checkpoints were rehashed after sealing and remain unchanged: Alpha.17
  `21ecdd192b474c10d130280ae32793fe1633440a79f6a634316cf05417887a32`,
  Alpha.18 `34cf9e157ebc07bde1b003db8505925cdd647939c220360fa779a8f1f3373dfc`,
  Alpha.19 `58502c450033b28190c0f3eaff8f0b6705a9a2d17165a2809031145415442aa1`,
  Alpha.20 `f3f02cbefbbcd5f0890efb889948e2a34487a9f07f0a2900744d44b19da56ef8`,
  and Alpha.21
  `35b7d23298ce69639ad7e2a09b24be4838de6066d22963abaf0f387dd3d4e232`.

## 0.1.0-alpha.21 release receipt

- Package status: historical sealed retail-free Linux checkpoint. The release tree
  is `build/releases/apf2k8-mod-studio-0.1.0-alpha.21-linux-x86_64/`; its
  adjacent archive SHA-256 is
  `35b7d23298ce69639ad7e2a09b24be4838de6066d22963abaf0f387dd3d4e232`.
  The archive is `607,218` bytes; its authoritative `119`-byte mode-`0444`
  `.sha256` sidecar verifies it; and the tar contains `105` safe members.
- Seal inventory: the stage and independent clean extraction each contain
  exactly `90` allowlisted regular files, `15` directories including the root,
  `2,594,779` file bytes, and `22` executables. Both contain zero symlinks,
  hardlinks, special files, undeclared files, private-source material, or retail
  game data. Their canonical JSON path/type/mode/size/content inventory SHA-256
  is `96f74cb24a044368a244e04b843f0bc6c6bb686ef2f8b5c1c0523a0670db7da5`.
- Independent gates: a second deterministic tar was byte-identical. Both stage
  and extraction passed the retail-free release gate before and after runtime,
  the source-free runtime gate at `58` modules / `31` capabilities, the private
  source gate at `10,464` universal rows / `96` specialist uniforms / `408`
  complete uniform-equipment rows, desktop validation, and all four Bash
  syntax checks. All `63` packaged Python files parse. Source, stage, and
  extraction GUI SHA-256 are identically
  `5b7d8a42abbbd1dc6ecec0bf0838221be4b6867cf55dda906109149ec12ab093`.
- Audit history: an independent audit rejected and deleted the first
  regenerable Alpha.21 candidate because its bundled docs still described
  Alpha.20 as current and Alpha.21 as pre-seal. Only the corrected rebuild with
  current-Alpha.21 package wording was sealed. Package docs are intentionally
  frozen and self-hash-free; the adjacent sidecar and this post-seal source
  receipt are the authority for exact archive/tree facts.
- Prior checkpoints rehashed unchanged: Alpha.17
  `21ecdd192b474c10d130280ae32793fe1633440a79f6a634316cf05417887a32`,
  Alpha.18 `34cf9e157ebc07bde1b003db8505925cdd647939c220360fa779a8f1f3373dfc`,
  Alpha.19 `58502c450033b28190c0f3eaff8f0b6705a9a2d17165a2809031145415442aa1`,
  and Alpha.20
  `f3f02cbefbbcd5f0890efb889948e2a34487a9f07f0a2900744d44b19da56ef8`.
- Product scope: 3,191 nonempty pure player-name allocations serving 4,482
  writable first/last references plus 40 team display-name allocations, for
  3,231 product-editable name allocations total. The zero-capacity allocation,
  abbreviations, mixed team/player ownership, unknown ownership, and future
  unclassified fields fail closed.
- Alias contract: 429 editable player-name allocations are shared, the largest
  has 23 owners, and 61 include both first- and last-name owners. The local
  inspector supplies each owner's entity kind, index, field, and readable label;
  Replace/Revert warns that every disclosed owner changes together.
- Project/build contract: player and team names retain one replacement-only JSON
  payload and the existing offset-free allocation metadata. Save/load, Undo,
  individual/project-wide Revert, standalone name Build, and the disjoint
  name-plus-rating composite route are admitted by the same centralized scope.
  Projects do not persist original names, alias-owner lists, source records,
  preimages, physical offsets, or retail game bytes.
- Runtime basis: player 788's exact `apf:roster-name:1977` allocation changed
  `Marino` → `CODEX`; Xenia rendered **Dan CODEX #13 QB** and **QB #13 DAN
  CODEX - GOLD STAR** without the old `0x84AB1D40` crash. This result does not
  extend to either abbreviation family or any roster-capacity field.
- Regression evidence: the complete product suite passes `648/648`
  in `90.763s`.
- Public product smoke: loaded the recognized source; replaced Dan's last name
  with `CODEX`; ran Undo; replaced again; ran individual Revert; replaced again;
  saved a project; reopened that project into a fresh session; built a separate
  3.7 GB game directory; and reparsed the output successfully. The project is
  989 bytes, contains replacement JSON only, and has SHA-256
  `45902ead474bfd868c88469220076e3cd23a47e7a58c3fa568129e1bb743694e`.
  The private `product-smoke.receipt.json` has SHA-256
  `6e0c84222ba28ce89f96f79e6cccb482ef1d9aa771d7e59a06ad3fe865d88f70`
  and records runtime equivalence to the prior candidate and video hashes.
- Output proof: built `0A` SHA-256 is
  `0212b638c1cdfa348110e57dbef4af5e0048101ff340202f52fec2021cd54044`,
  exactly matching the runtime-proved candidate. Only outer 1126 changed, the
  edited ROST reparsed, and the recognized source identity/hash remained
  unchanged throughout.
- Visual proof: Spark inspected a fresh isolated-display window after the UX
  fix. **Identity & Names** was visible by default beside **Base Ratings (28)**;
  **Replace Player Name**, **Revert Player Name**, and **View 23 affected fields…**
  were simultaneously visible with the exact `4/4` limit and no clipping or
  scroll trap. A separate retail-free product-code dialog check showed high
  contrast and all 23 owner rows at once. The user's live desktop and pointer
  were untouched.
- Distribution boundary: the public package and shareable project contain no
  retail game bytes. Built game directories and private source-derived exports
  still contain the user's data and must not be redistributed.

## 0.1.0-alpha.20 release receipt

- Source version: `0.1.0-alpha.20`.
- Product delta: complete and selected Audio batch archives now use manifest
  schema `apf2k8_mod_studio_audio_batch_export/v2`. Deterministic UTF-8
  `catalog.csv` accounts for every requested row; `playlist.m3u8` lists only
  successful playable exports and is omitted when none succeed. Sanitized
  metadata covers role/source/bank identity, format/rate/channels/duration,
  logical-track and paired-soundtrack identity, and packet sizes. Each success
  records exact payload `file_size` and `file_sha256`; root metadata records
  `payload_bytes`, companion hashes, catalog/playlist identities, and their
  record counts. Atomic no-overwrite publication, cancellation accounting,
  source fencing, and project isolation remain unchanged.
- Real untouched-source cancellation smoke: requested `47,814`, succeeded `1`,
  failed `0`, unsupported `0`, cancelled `47,813`; `catalog.csv` contains
  `47,814` records, `playlist.m3u8` contains `1` entry, and successful payload
  totals `55,356` bytes. The ZIP has `4` members and is `78,490,844` bytes.
  Archive SHA-256 is
  `a85425e6a39cd1b603bf7496aa3dab011194eceac83bc8146c70b29629ed5c90`;
  manifest SHA-256 is
  `e32681e4819b29976f3cbe09b5db3762c54d95eb7cb6d4e834ecdf19070e7d05`;
  the one exported payload SHA-256 is
  `67fc872990065b1c2e8d4c6c8ff12dfa8dbc36fc0d4ea501e955f7d064ff0622`.
  Project modification count stayed `0` before and after, all six source
  identity/hash observations remained unchanged, and the private 78 MB QA ZIP
  was deleted with its temporary directory.
- Regression evidence: the focused Audio suite passes `53/53`; the complete
  Mod Studio product suite passes `641/641`.
- Spark Hands inspected a fresh Alpha.20 Audio window only on isolated
  `DISPLAY=:99`. It visibly loaded all `47,814` rows (`2,261` standalone
  sounds, `20` AUSB indexes, `45,514` substreams, and `19` physical banks),
  showed the complete-catalog, all-original-banks, and cancellation controls,
  and kept the `catalog.csv`, `playlist.m3u8`, checksum, private-export, and
  non-cue explanation readable with no clipping, overlap, or spacing defect.
  The user's live desktop and pointer were untouched.
- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.20-linux-x86_64/`.
  Archive and authoritative adjacent sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.20-linux-x86_64.tar.gz`
  and `.tar.gz.sha256`.
- Seal receipt: archive size `596,710` bytes; deterministic SHA-256
  `f3f02cbefbbcd5f0890efb889948e2a34487a9f07f0a2900744d44b19da56ef8`;
  `105` safe tar members. The staged tree and independent clean extraction
  each contain `90` exact allowlisted regular files, `15` directories
  including the root, `2,557,988` file bytes, `22` executables, and no
  symlinks, hardlinks, special files, undeclared files, private source paths,
  or retail payloads. Their canonical path/type/mode/size/content inventory
  SHA-256 is
  `8add9197f0199ae11f4d6015a061c10602b8706bc0e2295cf8f9e5727a1fa2d0`.
  A second deterministic archive was byte-identical.
- Both the stage and independent extraction passed the retail-free release
  gate, 58-module/31-capability source-free runtime gate, private-source gate
  at `10,464` universal rows, `96` specialist uniform rows, and `408` complete
  uniform/equipment rows, desktop validation, and all four launcher/install
  Bash syntax checks. The visually inspected source GUI and sealed GUI are
  byte-identical at SHA-256
  `bb3f8f47ab005cba20d0df98722fb01697c5b0b9d90105927568c6d8b30934d4`.
  Alpha.17, Alpha.18, and Alpha.19 remained unchanged at
  `21ecdd192b474c10d130280ae32793fe1633440a79f6a634316cf05417887a32`,
  `34cf9e157ebc07bde1b003db8505925cdd647939c220360fa779a8f1f3373dfc`,
  and `58502c450033b28190c0f3eaff8f0b6705a9a2d17165a2809031145415442aa1`.
  This exact source-document receipt was filled only after the release tree,
  archive, and sidecar were sealed; those package artifacts were not rewritten.
- Player-name runtime proof: player `788`, last-name allocation
  `apf:roster-name:1977`, sole owner `player788:last_name`, changed `Marino` to
  `CODEX` within its six-character limit. Exactly six decoded bytes changed
  inside the 14-byte allocation; 284,010/284,015 H7A tokens were preserved and
  five repaired. All 40 team names, all 120 team identity fields, all 63,112
  base ratings, and Dan Marino Speed `40` were unchanged. Candidate `0A`
  SHA-256 is
  `0212b638c1cdfa348110e57dbef4af5e0048101ff340202f52fec2021cd54044`;
  the candidate receipt SHA-256 is
  `b7c23be3bfe2ab6aad590f28b18c49c7b64940b35d09424c3fdfc1419da79919`.
  Both candidate hashes remained unchanged after the run.
- Xenia visibly rendered **Dan CODEX #13 QB** in Gold-player selection and
  **QB #13 DAN CODEX - GOLD STAR** on the Star Card, with stable player model,
  portrait, biography, and abilities. The emulator exited normally; its log
  contains neither `0x84AB1D40` nor an access violation. Private video evidence:
  `apf-player-name-dan-codex-token-preserving-runtime-20260719.mp4`, SHA-256
  `89f406ce59f6b1f2f5b83d2a3cfa3ea24d9b4e8c5d3db9a13ccab6f6f198acdd`;
  `apf-player-name-dan-codex-star-card-runtime-20260719.mp4`, SHA-256
  `ef3ad1d5f7ee53016128be9a6275098eaa6afe32cde3dab6436f5d605cfe6a11`.
- Product boundary: the experiment promotes bounded player first/last names to
  runtime-proved, not yet Editable. A release handler still must enforce each
  exact allocation limit, surface aliases, preserve automatic originals, and
  support per-field/project-wide Revert. It does not promote team abbreviations,
  jersey numbers, roster membership, depth charts, active-roster capacity, or
  shareable inclusion of any retail source bytes.

## 0.1.0-alpha.19 release receipt

- Product action: **Export all original banks (19)…** writes the complete
  physical-bank set plus `manifest.json` into one private deterministic
  `ZIP_STORED` archive. Stable paths use
  `banks/oNNNNN-<safe-source-name>.bin`; the manifest schema is
  `apf2k8_mod_studio_external_audio_bank_bundle/v1`.
- Safety: source SHA-256, per-file SHA-256/size/name identity, all descriptor
  owners, derived roles, and `replacement=false` are recorded. Publication is
  atomic hard-link no-overwrite. Duplicate identities and bad source hashes
  fail before export; fatal integrity and progress-callback failures remove
  staging and publish nothing. Ordinary per-bank failures are recorded and do
  not prevent later banks from being attempted. Cancellation is honored only
  between complete bank copies and is accounted for in the manifest.
- Full untouched-source smoke: requested `19`, succeeded `19`, failed `0`,
  cancelled `0`; payload `1,144,270,848` bytes; final archive
  `1,144,299,829` bytes; `20` ZIP members; `20` descriptor owners; both
  soundtrack banks present. Archive SHA-256 is
  `ddc57c7762afb14b5df9ceb9bf68ebaae780b3dea73ee088c931dcf38994d103`;
  manifest SHA-256 is
  `f582212a8638d5f0157de7d9cfb736bd55645aec743d0954f6091ad71ba49e11`.
- Independent verification reread every archived member and matched its
  manifest size and SHA-256. Project modification count remained `0` before
  and after; the recognized `0A` SHA-256 remained
  `dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e`;
  source stat identity was unchanged. The private QA archive was deleted.
- Cancellation evidence is deliberately split: a synthetic backend run
  completed one bank and marked three banks cancelled, while the GUI control
  test proves running/disabled/cancel/recovery state. A real visual cancel was
  not captured because the operating-system cache let the 1.1 GB export finish
  before the isolated desktop operator could press Cancel.
- Spark Hands inspected fresh Alpha.19 Audio windows only on isolated
  `DISPLAY=:99`. The page showed 2,261 standalone cues, 20 AUSB descriptors,
  45,514 substreams, 19 physical banks, all 47,814 rows, and the separate
  complete-catalog, all-original-banks, and Cancel controls without clipping
  or overlap. A real 19/19 completion dialog initially exposed washed-out text;
  the global `QMessageBox` styling was corrected and a fresh rerun showed the
  exact 19/19, 0 failure, 0 cancelled, 1.1 GB receipt in white-on-dark text
  with an orange, legible OK button. The user's live desktop and pointer were
  untouched.
- Boundary: these `.bin` members are raw multi-cue retail banks. They remain
  ineligible for direct Play, waveform, shortlist, or Replace, and neither the
  archive nor its manifest may enter a shareable mod project. The feature does
  not supply an XMA1 encoder or claim commentary/music replacement.
- Product regression: the complete Mod Studio suite passes `639/639`; the
  focused Audio suite passes `51/51`. The release tree and an independent
  extraction each pass the retail-free release gate, the 58-module/31-
  capability source-free runtime gate, desktop/Bash checks, and the untouched-
  private-source gate at 10,464 universal rows, 96 specialist uniform rows,
  and 408 complete uniform/equipment rows.
- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.19-linux-x86_64/`.
  Archive and authoritative adjacent sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.19-linux-x86_64.tar.gz`
  and `.tar.gz.sha256`.
- Archive size: `589,210` bytes; deterministic SHA-256:
  `58502c450033b28190c0f3eaff8f0b6705a9a2d17165a2809031145415442aa1`;
  `105` tar members. Both trees contain `90` allowlisted files, `15`
  directories including the root, `2,532,861` file bytes, `22` executables,
  and no symlinks or special files. The byte/path/mode inventory SHA-256 is
  `855c814cb1a5ea730a50708d6f2b567c1549d3029e59d40225ea3cbcb256463c`.
  A second deterministic archive was byte-identical. Alpha.17 and Alpha.18
  reverified unchanged at `21ecdd192b474c10d130280ae32793fe1633440a79f6a634316cf05417887a32`
  and `34cf9e157ebc07bde1b003db8505925cdd647939c220360fa779a8f1f3373dfc`.
- The visually inspected source GUI and sealed GUI are byte-identical at
  SHA-256 `9e00d4fca0aa19eac62705ff254417989e54d5098bd7de1374eea39714274413`.

## 0.1.0-alpha.18 release receipt

- Source version: `0.1.0-alpha.18`.
- Product delta: private source-bound v2 ratings CSV import/export, immutable
  preview receipts, hard source-conflict fencing, confirmable project conflicts,
  atomic batch Apply, and one-step Undo/no-op behavior.
- Real-source smoke: 2,254 players, 28 attributes, 63,112 cells, observed 0..99,
  Dan Marino Speed `40` → `99`, confirmed active-edit conflict, Undo, no CSV or
  source values in the shareable project, and unchanged source SHA-256
  `dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e`.
- Product regression: `628/628` Mod Studio tests pass; the focused installer,
  capability-parity, ratings-import, and roster-GUI group passes `38/38`.
  A repository-wide legacy research check separately found six pre-existing
  evidence-pin drifts in the old SCNE/uniform-format receipt tests; those files
  are outside this 90-file release closure and were deliberately not rewritten.
- Retail-free release gate: `90` exact allowlisted regular files,
  `2,490,269` file bytes, `15` directories, `22` executables, no symlinks,
  no undeclared paths, and no private or retail payload. Source-free runtime
  passes with `58` modules and `31` capabilities. Private-source runtime passes
  at `10,464` universal rows, `96` specialist uniform rows, and `408` uniform
  inventory rows while preserving the exact source SHA-256 above.
- Spark Hands checked the final ratings-import modal on isolated
  `DISPLAY=:99`: New replacements `1`, Reverts `0`, Already matches `63,111`,
  Source conflicts `0`, Project conflicts `0`, Errors `0`. Labels, warning,
  one-Undo note, Cancel, and Apply are high-contrast with no clipping or
  overlap. The source and sealed GUI module are byte-identical at SHA-256
  `e7f10a11dcb6567e2d92256cd9323d428d27a0ede3700c07db2aa8d30b0c072b`;
  the user's live desktop and pointer were untouched.
- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.18-linux-x86_64/`.
  Archive and authoritative adjacent sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.18-linux-x86_64.tar.gz`
  and `.tar.gz.sha256`.
- Archive size: `580,877` bytes; deterministic SHA-256:
  `34cf9e157ebc07bde1b003db8505925cdd647939c220360fa779a8f1f3373dfc`;
  `105` tar members. Independent extraction passed the release/runtime gates
  and byte/mode/size comparison. Normalized path/type/mode/size inventory
  SHA-256: `3e851f71725aae62aa2c4dcfae1a10bd86752c8fd71bf16409593b596cfced30`.
  Alpha 17's published `21ecdd…` archive also reverified unchanged.

## 0.1.0-alpha.17 release receipt

- Source version: `0.1.0-alpha.17`; product behavior is the 617/617-tested
  Alpha 16 ratings build with release-facing version/document consistency
  corrections only.
- The staged release contains `89` exact allowlisted files and passes the
  retail-free release gate, 57-module source-free runtime gate, untouched-
  private-source indexing gate, and 27/27 focused installer/ratings-GUI/
  capability-parity regression.
- Spark Hands visually verified the fresh `Alpha 17 • retail-free` window on
  isolated `DISPLAY=:99`: exact-value editor, Apply/Revert controls,
  Value/Byte/State table, spacing, and footer all render without clipping or
  overlap. The user's live desktop and pointer were untouched.
- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.17-linux-x86_64/`
- Archive and checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.17-linux-x86_64.tar.gz`
  and the adjacent `.sha256` file.
- Archive size: `567,440` bytes; SHA-256:
  `21ecdd192b474c10d130280ae32793fe1633440a79f6a634316cf05417887a32`.
- Release tree and independent extraction: `89` allowlisted files, `15`
  directories including the root, `2,431,729` file bytes, `22` executable
  files, and `104` tar members.
- The independent extraction is byte-, path-, mode-, and size-identical. A
  second deterministic archive is byte-identical. The normalized path/type/
  mode/size inventory SHA-256 is
  `c7e1e438a14410fdf00643aed6bb9da4cf3a177cae334e76ac730013585722e5`.

## 0.1.0-alpha.16 release receipt

- Source version: `0.1.0-alpha.16`.
- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.16-linux-x86_64/`
- Archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.16-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.16-linux-x86_64.tar.gz.sha256`
- Archive size: `566,696` bytes.
- SHA-256:
  `dd84f8e6f2366d85bb9e3c4ad34652635878eaa8a0ad80d01dbc0a3d74ed5bcd`.
- Full source regression: `617/617` tests passed.
- Release tree and independent extraction: `89` allowlisted files, `15`
  directories including the root, `2,428,480` file bytes, and `22` executable
  files. The tar contains `104` members.
- Runtime closure: `57` modules and `31` APF capabilities; the untouched
  private source produced `10,464` universal assets, `96` specialist uniform
  assets, and `408` complete uniform/equipment records.
- Retail-free release gate: three exact reviewed metadata files, eight install
  surface files, seven retail hashes fenced, reviewed extractor pinned, and no
  private/retail payloads, undeclared files, links, or special files.
- Independent extraction is byte-, path-, mode-, and size-identical. A second
  deterministic archive is byte-identical to the published archive. The
  normalized path/type/mode/size inventory SHA-256 is
  `3ef081a50324068c360e658927ea7c3855b3ebb942485cdd9acf043bb549cf46`.
- Visual QA ran only through Spark Hands on isolated `DISPLAY=:99`. The fresh
  `Alpha 16 • retail-free` Rosters & Players window showed the exact-value
  spinbox, Apply/Revert controls above the Value/Byte/State table, readable
  spacing, and a fully visible footer with no clipping or overlap. The user's
  live desktop and pointer were untouched.

## 0.1.0-alpha.14 release receipt

- Source version: `0.1.0-alpha.14`.
- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.14-linux-x86_64/`
- Archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.14-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.14-linux-x86_64.tar.gz.sha256`
- Archive size: `541,112` bytes.
- SHA-256:
  `b38350de9dbc121c963861db44e2bac2d9caa8595cdd35e39766f2b205203279`.
- Full source regression: `588/588` tests passed.
- Release tree: `84` files, `15` directories including the root,
  `2,290,070` file bytes, and `22` executable files.
- Runtime closure: `55` modules and `31` APF capabilities; the untouched
  private source produced `10,464` universal assets, `96` specialist uniform
  assets, and `408` complete uniform/equipment records.
- Retail-free release gate: three exact reviewed metadata files, eight install
  surface files, seven retail hashes fenced, reviewed extractor pinned, and no
  private/retail payloads, undeclared files, symlinks, or special files.
- Independent extraction is path-, mode-, and size-identical to the sealed
  tree. The deterministic rebuild is byte-identical to the published archive;
  inventory SHA-256 is
  `10225801c90f369a8ebe56d60c6f05bd76f7091a45a8552b2b87474978276b8e`.
- Visual QA ran only on isolated `DISPLAY=:99`: the full **Roster + Base
  Ratings** workspace, 28/28 exact ratings, runtime-lock badges, independent
  table/detail scrolling, spacing, and control reachability passed without
  clipping or overlap. The user's live desktop was untouched.

## 0.1.0-alpha.13 release receipt

- Source version: `0.1.0-alpha.13`.
- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.13-linux-x86_64/`
- Archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.13-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.13-linux-x86_64.tar.gz.sha256`
- Size: `477,068` bytes
- SHA-256:
  `645c021d9d3d0570ed6a307c15a8a06387fb4be3cf20abaf23a70f3bc0b14e9f`
- Capability/action parity is implemented. Editable cards require concrete
  Replace/Revert methods, Export-only cards require a concrete export handler,
  and exact asset routes use the same binding as their capability card.
- `apf2k8.logos_cards.draft_logo` is now a dedicated editable capability.
  Registry totals are 31 APF records and 61 records globally; the existing 30
  NFL 2K5 records are unchanged. APF card status totals are 7 Editable, 7
  Preview, 3 Export-only, and 14 Coming Soon. The hidden
  `jersey_06_runtime` capability remains a proof alias rather than another
  product editor.
- `apf2k8.menus.layouts` binds to the real Universal Text action surface and
  stays Editable for 2,410 of 2,413 bounded allocations. Its card no longer
  depends on an irrelevant file-extension field; the two fallbacks and one
  zero-capacity STRG allocation stay read-only.
- Cross-title model conversion, the broad uniform-logo catalog, mode/state
  routing, generic SCNE-to-glTF conversion, `hi_head` face research, and
  retained Season/franchise research render as Coming Soon because they lack a
  dedicated APF product handler. The specialized Stadium viewer remains
  Export-only through its real glTF handler.
- Disabled primary/secondary/utility/Build/Launch controls have explicit
  styling; Stadium replacement is labeled **Replace (locked)**. Physical bank
  Audio rows hide single-sound Play, use a sound-specific shortlist prompt,
  and retain more detail-pane space.
- The retail-free stadium findings projection records the completed negative
  static-ownership experiment and the runtime renderer-handoff experiment that
  should follow it.
- Feature gate: the complete source suite passes `528/528` tests.
- Release gate: `73` allowlisted files and `2,023,280` file bytes pass with two
  metadata files, eight install-surface files, all seven retail hashes fenced,
  and the exact reviewed extractor. Private data, retail data, symlinks, and
  undeclared files are all absent.
- Runtime and private-source gates pass at `50` modules / `31` APF
  capabilities, `10,464` universal catalog items, `96` specialist uniforms,
  and `408` total uniform/equipment records. Registry validation passes at
  `61` capabilities globally / `31` APF, with cards split 7 Editable, 7
  Preview, 3 Export-only, and 14 Coming Soon.
- The published tree and independent extraction are path-, mode-, and
  size-identical: `73` files, `14` directories including the root, `2,023,280`
  file bytes, `22` executables, zero symlinks or special files, and `87` tar
  entries. Their shared path/mode/size inventory SHA-256 is
  `6b5c7868c4f39febd889e225ab9f7d6d5e075064bbeccd17bbb0fc9f4ad98cd2`.
- Spark Hands inspected fresh Stadium window `0x03800035` and Audio window
  `0x04000035` on isolated `DISPLAY=:99`. Both showed the exact `Alpha 13`
  badge. Stadium displayed the 116-mesh / 328-draw / 113-material /
  13-shader-family / 737-texture-identity finding and a gray **Replace
  (locked)** control. Audio displayed all `47,814` semantic rows and the XMA
  replacement boundary. Neither window had clipping, overlap, or footer
  obstruction; the user's active desktop and pointer were untouched.
- The independent extraction is retained at
  `/tmp/apf-alpha13-extract.gZubBi`. The release tree, archive, checksum
  sidecar, and extracted package are immutable. This exact source-document
  receipt was filled after sealing without rewriting any package artifact.

## 0.1.0-alpha.12 release receipt

- Source version: `0.1.0-alpha.12`.
- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.12-linux-x86_64/`
- Archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.12-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.12-linux-x86_64.tar.gz.sha256`
- Size: `462,020` bytes
- SHA-256:
  `2cc7a3178f0afff81ebd402d308b75fbaa272075003ee2630f42c2794c678ccf`
- Feature gates before packaging: `20/20` focused Stadium/Audio-UX tests,
  `15/15` Stadium packaging closure, and `512/512` complete cross-title Mod
  Studio tests.
- Private-source proof: 93 exact stadium SCNE records; the first scene loads
  116 meshes, 112,158 vertices, 68,669 source triangles, and nine same-outer
  package records.
- Visual gate: Spark Hands inspected a fresh source-ready `1480×920` window on
  isolated `DISPLAY=:99`. It showed `Alpha 12 • retail-free`, all `93` stadium
  scenes, the first private 3D scene at 116 meshes / 112,158 vertices / 68,669
  source triangles / 11,549 preview triangles, its nine-record outer package,
  and a 2048×1024 `stadium_radiance` PNG preview. Scene controls, source-safety
  wording, unresolved-ownership boundary, footer, Build, and Xenia controls
  were readable without overlap. The gate also caught that Qt selector
  specificity made a disabled primary Replace button look orange; alpha.12
  remains immutable and the global disabled-state fix is queued into the next
  build rather than silently rewriting this archive.
- The published tree and independent clean extraction are byte-, size-, and
  mode-identical: `71` allowlisted files, `14` directories including the root,
  `1,976,945` file bytes, `22` executables, zero symlinks, hardlinks, or special
  files, and `85` archive members. Their shared file path/mode/size inventory
  SHA-256 is
  `120ccb4207026a4bfeedb6fe0af976c7bd4ba51a03102b5016faa579d3a02b6c`.
- Both trees pass the retail-free release gate, source-free runtime (`49`
  modules / `30` capabilities), supported private-source runtime (`10,464`
  universal assets / `96` specialist uniforms / `408` total uniforms),
  source-free registry validation (`60` capabilities / two games / `20`
  surfaces), desktop validation, all-four-script Bash syntax, and the isolated
  per-user install/update/uninstall contract. No derived `.gltf`, `.glb`,
  `.bin`, or `.zip` is allowed into the release.
- Alpha.11, alpha.10, and alpha.9 remain unchanged at
  `66b7ecbf1d951d2353832ace3750fbcc067959d11e973f985e35cb39eaa7e7fe`,
  `c72d53f052fb843d01e259e50fa7628b5b56f21212588c6545757554e4c0fd28`,
  and `046f7463a8eb7a13b78e4a7b53eff2e310a2594e5d4b4526378b8dfc1204b83d`.

## 0.1.0-alpha.11 release receipt

- Source version: `0.1.0-alpha.11`.
- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.11-linux-x86_64/`
- Archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.11-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.11-linux-x86_64.tar.gz.sha256`
- Size: `428,574` bytes
- SHA-256:
  `66b7ecbf1d951d2353832ace3750fbcc067959d11e973f985e35cb39eaa7e7fe`
- Feature gates before packaging: `14/14` focused Uniform/Product-Findings,
  `52/52` focused Audio ownership/export, and `507/507` complete cross-title
  Mod Studio tests.
- Private-source proof: 10,464 universal items, 408 uniform/equipment records
  (96 editable + 312 additional), 2,302 Audio-category assets, 47,814 semantic
  Audio rows, 19 named physical banks, and 20 descriptor owners.
- Visual gate: passed after sealing through Spark Hands on isolated
  `DISPLAY=:99`. A fresh source-ready `1480×920` window showed
  `Alpha 11 • retail-free`; Uniforms rendered the exact 96/312 split and all
  408 records; Gameplay rendered all 38 honest read-only semantic rows;
  Scorebug rendered the eight-row Presentation Map, editable 128×128
  `digital_font` contract, and 25 raw assets; Audio completed at 47,814 rows
  and filtered `lines.bin` to the single 776.4 MB raw-bank row. No emulator,
  active desktop, user pointer, export, or edit was used. The footer remained
  unobstructed. Spark noted minor leading-glyph/tab-label OCR or padding
  clipping and dense ellipsized table/detail text; these are queued as source
  UX polish rather than hidden from the receipt.
- The published tree and independent clean extraction are byte-, size-, and
  mode-identical: exactly `68` allowlisted files, `13` directories including
  the root, `1,840,704` file bytes, `22` executables, and zero symlinks,
  hardlinks, or special files. Their shared mode/size inventory SHA-256 is
  `833421de12a6a461d65fbee109dad504604395849ab3ec43a32659118b30f859`.
- The archive has `81` members. Both trees passed the retail-free release gate,
  source-free runtime (`46` modules and `30` capabilities), supported
  private-source runtime (`10,464` universal assets, `96` specialist uniform
  writers, and `408` total uniform records), source-free registry validation
  (`60` capabilities, two games, `20` surfaces), desktop validation, all four
  Bash syntax checks, isolated per-user install/update/uninstall, and repeated
  post-runtime release gates.
- The real-source Audio proof resolved `2,302` category assets, `47,814`
  semantic rows, `19` physical banks, and `20` descriptor owners. A typed
  exact-byte `loadm.bin` export independently matched its `6,144`-byte source;
  that private temporary output was removed and never entered the package.
- The sealed alpha.10 and alpha.9 archives remain byte-for-byte unchanged at
  `c72d53f052fb843d01e259e50fa7628b5b56f21212588c6545757554e4c0fd28`
  and `046f7463a8eb7a13b78e4a7b53eff2e310a2594e5d4b4526378b8dfc1204b83d`.

## 0.1.0-alpha.10 release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.10-linux-x86_64/`
- Archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.10-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.10-linux-x86_64.tar.gz.sha256`
- Size: `412,489` bytes
- SHA-256:
  `c72d53f052fb843d01e259e50fa7628b5b56f21212588c6545757554e4c0fd28`
- Test gates: `20/20` focused Audio/Text-Sheet, `20/20` focused recovery,
  `115/115` APF-pattern, and `489/489` complete cross-title Mod Studio tests.
- Visual gate: passed after the headless seal through Spark Hands on isolated
  `DISPLAY=:99`. Fresh source-ready windows showed `Alpha 10 • retail-free`,
  both Text Sheet buttons and allocation-limit UI, all shortlist Review/reorder
  controls, the 15-row `Stereo masters • jukeboxmusic (15)` album, and the
  switch to `Mono companions • jukebox22 (15)`. Spark found no clipping,
  overlap, spacing collapse, or footer obstruction. The active desktop and
  user pointer were never used; no emulator was launched.
- The published tree and independent clean extraction are byte-, size-, and
  mode-identical: exactly `66` allowlisted files, `13` directories including
  the root, `1,775,875` file bytes, `22` executables, and zero symlinks,
  hardlinks, or special files. Their shared mode/size inventory SHA-256 is
  `d0a0cd009f94db5237fc22e1f03c1befeee7612da74c0c01f14b113e1c131ae8`.
- The archive has `79` members. Both trees passed the retail-free release gate,
  source-free runtime (`45` modules and `30` capabilities), supported
  private-source runtime (`10,464` universal assets and `96` uniforms with
  `private_source_verified=true`), source-free registry validation, desktop
  validation, all-four-script Bash syntax, isolated per-user install/update/
  uninstall, and repeated post-runtime release gates.
- The sealed alpha.9 archive remains byte-for-byte unchanged at
  `046f7463a8eb7a13b78e4a7b53eff2e310a2594e5d4b4526378b8dfc1204b83d`;
  its retained tree/extraction inventory remains
  `ffa61522d1a6e13cc30805ea37069d2a4fff7420a68cd7e867334fc8dc8c6d9c`.

## 0.1.0-alpha.9 release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.9-linux-x86_64/`
- Archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.9-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.9-linux-x86_64.tar.gz.sha256`
- Size: `401,795` bytes
- SHA-256:
  `046f7463a8eb7a13b78e4a7b53eff2e310a2594e5d4b4526378b8dfc1204b83d`
- Feature gates before packaging: `20/20` focused recovery tests and `107/107`
  APF-pattern tests; the complete current cross-title suite passes `468/468`.
- Visual gate: current-code alpha.9 window `0x09a0002b` passed at `1480×920`
  on isolated `DISPLAY=:99`, including both recent-file flyouts and the manual
  Recover action.
- Stage and independent clean extraction are byte-, size-, and mode-identical:
  exactly `65` allowlisted files, `13` directories including the root,
  `1,726,822` file bytes, `22` executables, and zero symlinks, hardlinks, or
  special files. Their shared mode/size inventory SHA-256 is
  `ffa61522d1a6e13cc30805ea37069d2a4fff7420a68cd7e867334fc8dc8c6d9c`.
- The archive has `78` members. Both trees passed the release gate, source-free
  runtime (`44` modules and `30` capabilities), private-source runtime
  (`10,464` universal assets and `96` uniforms with
  `private_source_verified=true`), registry, desktop-file, all-four-script
  Bash, and repeated post-runtime release gates.
- The sealed alpha.8 archive was reverified unchanged at
  `7fe2198bebdf0f0f0c2114358b1174bfbc34507bf93678f559347c99c6f9003a`.

## 0.1.0-alpha.8 release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.8-linux-x86_64/`
- Archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.8-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.8-linux-x86_64.tar.gz.sha256`
- Size: `392,574` bytes
- SHA-256:
  `7fe2198bebdf0f0f0c2114358b1174bfbc34507bf93678f559347c99c6f9003a`
- Unit gates: `9/9` document-workflow tests, `36/36` focused
  document/core/safety tests, and `443/443` complete cross-title tests.
- Visual gate: source-ready alpha.8 window `0x0860002b` at `1480×920` on
  isolated `DISPLAY=:99`; `Alpha 8 • retail-free`, all `14` sidebar categories,
  source-ready header controls, and File-menu Open Project (`Ctrl+Shift+O`),
  Save (`Ctrl+S`), Save As (`Ctrl+Shift+S`), and Quit (`Ctrl+Q`) were readable
  and unclipped. Save and Save As were correctly disabled for the clean
  no-active-project state, with no overlap or cramped spacing.
- Stage and independent clean extraction: exactly `65` allowlisted files, `13`
  directories including the root, `1,675,159` file bytes, `22` executables,
  and zero symlinks or hardlinked files. Both passed release, source-free and
  private-source runtime, registry, desktop, all-four-script Bash, and repeated
  post-runtime release gates.
- The archive has `78` members. Runtime closure is `44` modules and `30`
  capabilities; the supported untouched private source produced `10,464`
  universal assets and `96` uniforms with `private_source_verified=true`.
- Alpha.7 was reverified unchanged at
  `e031891a7b610d6462ba05c6053f21a4641e77beb318ac78cb7f77de812b52d7`.
- Recent-project menus and crash-recovery autosave remain deliberately deferred
  to alpha.9. Audio replacement remains unavailable until the XMA1 encoder,
  cue/loop ownership, and reversible bank writer exist together.

## 0.1.0-alpha.7 release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.7-linux-x86_64/`
- Archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.7-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.7-linux-x86_64.tar.gz.sha256`
- Size: `391,496` bytes
- SHA-256: `e031891a7b610d6462ba05c6053f21a4641e77beb318ac78cb7f77de812b52d7`
- Unit gate: the complete current cross-title product suite passes `428/428`.
- Visual gate: Audio loaded all `47,795` decoded rows at 1480×920 on isolated
  `DISPLAY=:99`; the shortlist heading, Add/Remove, Add this page, Clear,
  `Selected N / 256`, export, matching-export, and replacement-boundary
  controls were all readable and unclipped.
- Stage and clean extraction: `65` files, `13` directories including the root,
  `1,649,360` file bytes, and `22` executables. Both passed the release gate,
  source-free runtime, private-source runtime, source-free registry validation,
  desktop validation, all four Bash syntax checks, and the repeated
  post-runtime release gate.
- Runtime closure: `44` modules and `30` capabilities; the untouched private
  source produced `10,464` universal assets and `96` uniforms with
  `private_source_verified=true`.
- Archive/extraction: `78` tar members with byte-, size-, and mode-identical
  extraction. No symlinks, hardlinked files, generated caches, retail bytes,
  private payloads, unsafe paths, duplicates, or case collisions were present.
- The alpha.6 archive was reverified unchanged at
  `9710308dc637c7129c35d7e944726f4b3ef3f4274a0cb510c11510ab7230dcae`.

## 0.1.0-alpha.6 release receipt

- Archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.6-linux-x86_64.tar.gz`
- Size: `388,619` bytes
- SHA-256: `9710308dc637c7129c35d7e944726f4b3ef3f4274a0cb510c11510ab7230dcae`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.6-linux-x86_64.tar.gz.sha256`
- Unit gate: the complete current cross-title product suite passes `419/419`.
- Visual gate: the current-code two-row Audio filter layout passed on isolated
  `DISPLAY=:99`, including the new source selector and existing action pane.
- Stage gates: `65` files and `13` directories (including the release root),
  totaling `1,633,476` file bytes, passed exact-allowlist, source-free runtime,
  per-user install/update/uninstall, private-source runtime, desktop-entry,
  launcher-syntax, and post-runtime zero-retail checks on the original stage
  and a clean extraction.
- Runtime closure: `44` modules and `30` capabilities; the untouched private
  source produced `10,464` universal assets and `96` uniforms.
- The adjacent `.sha256` sidecar is the authoritative archive checksum.

## 0.1.0-alpha.5 release receipt

- Archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.5-linux-x86_64.tar.gz`
- Size: `386,254` bytes
- SHA-256: `05c4e7132167f0167ce71bc7b244fa6c3ca9faa2b75dab7433617f97556515a8`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.5-linux-x86_64.tar.gz.sha256`
- Unit gate: all `72` matching APF product tests passed.
- Visual gate: current-code Audio passed on isolated `DISPLAY=:99`; its
  full-height tabs and stacked batch/replacement controls are unclipped.
- Stage gates: `65` files and `13` directories (including the release root)
  totaling `1,624,668` file bytes passed release, source-free runtime/install lifecycle, untouched-private-
  source runtime, registry, desktop-entry, launcher-syntax, and post-runtime
  retail-free checks.
- Runtime closure: `44` modules and `30` capabilities; the untouched private
  source produced `10,464` universal assets and `96` uniforms.
- Archive and clean-extraction gates: `65` regular files, `13` directories,
  `78` total members, checksum and metadata parity, and no links, special files,
  duplicate paths, case collisions, private evidence, or retail payloads.

## 0.1.0-alpha.4 release receipt

- Archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.4-linux-x86_64.tar.gz`
- Size: `381,325` bytes
- SHA-256: `88fabc7bd1c167a60d6f943f9404366578070e168d3fe5d9d6989519ca3f9b93`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.4-linux-x86_64.tar.gz.sha256`
- Unit gate: all `69` matching APF product tests passed.
- Stage gates: `65` files, `13` directories, and `1,610,375` file bytes passed both release checkers, source-free runtime/install lifecycle, untouched-private-source runtime, and the post-runtime retail-free audit.
- Runtime closure: `44` modules and `30` capabilities; the untouched private source produced `10,464` universal assets and `96` uniforms.
- Archive and clean-extraction gates: `65` regular files and `13` directories; checksum and hash/metadata parity passed; no links, special files, duplicates, case collisions, reports, private evidence, or retail bytes were present.

## Clickable now

The APF Qt shell presents all fourteen product categories from first launch:

1. Getting Started
2. Uniforms & Equipment
3. Rosters & Players
4. Team Identity
5. Logos & Team Art
6. Scorebug & Presentation
7. Field Art
8. Stadium Studio
9. Menus & Text
10. Audio
11. Sliders & Gameplay
12. Playbooks & Plays
13. Season & Franchise Lab
14. All Game Assets

After loading a recognized private source, these operations are wired:

- Browse, search, filter, page through, and inspect all 10,464 universal items.
- Export decodable textures to PNG and exact multipart resources to private raw
  bundles.
- Browse all 2,254 players, 40 teams, 31 stadium identities, and 1,344 roster
  memberships. Preview 3,273 mapped player/team name allocations serving 4,628
  references, including alias-owner counts. Bounded pure player first/last names,
  team display names, and all 28 player base ratings have dedicated editors;
  jersey numbers and other packed roster fields remain read-only.
- Open Alpha.23's **53-player roster planner** for each of the 32
  populated team records. It shows the exact 42 source-active memberships and
  lets the modder assign eleven retail-free project reserves. The `.apf2k8roster`
  plan never stores the 42 source rows and Build does not apply reserves; slots
  43–53 remain planning data until an emulator-target consumer patch exists.
- Search 1,572 TXT-localization references and all 2,413 underlying string-pool
  allocations from the two TXT-localization and two STRG banks. Replace/Revert
  is enabled for 2,410 allocations under the displayed UTF-16 limit; shared
  allocations show how many consumers will change before Apply.
- Export the rows matching any specialized inspector's current search/kind
  filter as structured JSON or spreadsheet-friendly CSV. These are local,
  retail-derived exports and never enter a shareable project or release.
- Inspect one playbook containing 163 formations, 586 plays, 28 categories,
  4,948 route nodes, and 6,446 slot references.
- Inspect five director resources containing 137 fixed records, 1,623
  instructions, and 120 primary strings.
- Inspect all 1,120 uniform selector records across 80 static HOME/AWAY banks.
- Browse all 258 Field Art records through seven named semantic families and
  125 source packages, with normal preview/export and an explicit locked
  replacement boundary.
- Browse/export all 2,261 `AUDO` resources and all 45,514 addressable substreams
  in 20 `AUSB` banks. Each row carries stable coordinates, broad evidence-labeled
  role, normal audio metadata, and a suggested safe filename. XMA is the original
  export; WAV playback/export publishes only after decoder proof. Small complete
  banks export transactionally as one ZIP, and previews live only inside the
  current private session. A session-only shortlist collects up to 256 playable
  rows across filters, pages, and banks for one ordered transactional export;
  it contains no audio bytes and never enters a project.
- In Alpha.23, every individual AUSB substream also exposes strict
  pre-encoded XMA1 Replace/Revert. Its channels, sample rate, packet allocation,
  and decoded duration must match exactly. The one shared `cwdloop` allocation
  discloses both owners, and the one Track 3 allocation that crosses `0A`/`0B`
  is split safely by the pack-aware Build path. Whole physical banks are still
  private raw exports rather than editable single sounds.
- Explicitly load a bounded waveform for one playable row through its verified
  session-private PCM16 WAV. Selection never auto-decodes; stale work cancels,
  failures are retryable, and physical/index rows remain ineligible.
- Export the complete 47,814-row Audio surface as one atomic original-XMA1 or
  decoder-verified-WAV ZIP. Its manifest accounts for every success, failure,
  cancellation, and all 39 non-cue bank/index rows marked unsupported.
- Export, replace, preview, and revert all 24 jersey, 24 pants, 24 helmet, and
  24 shoulder targets.
- Export, replace, preview, and revert the 128×128 `digital_font` alpha mask.
- Export, replace, preview, and revert the exact 128×128 single-level BC3
  `draft_logo` in `franchise.iff`; the rest of the logo catalog stays read-only.
- Undo edits, revert the whole project, save/load a retail-free `.apf2k8mod`,
  and build a new complete extracted game folder. First Save names an untitled
  edit set; `Ctrl+S` then fast-saves the protected active target, while
  `Ctrl+Shift+S` creates a copy. Dirty state survives a final zero-edit revert,
  and source/project/close transitions offer Save, Discard, or Cancel. Projects
  may contain only user-authored PNGs, canonical text/rating replacements,
  canonical user-supplied XMA1 packets, and typed retail-free metadata.
- Configure Xenia Canary and Wine, then launch the last complete build with
  isolated storage, content, cache, logs, and Wine-prefix paths.

In Alpha 16 these actions are the authority for capability-card status. The
real Universal Text editor remains Editable; Rosters & Players is Editable for
exact team/player names, 28 semantic base-rating IDs, and all 17 exact player
positions through a fixed dropdown; the exact
`draft_logo` has its own editor binding; Stadium keeps its specialized
Export-only glTF handler; and a generic semantic card without a dedicated APF
handler displays Coming Soon even when its raw assets remain browsable/
exportable in **All Game Assets**.

## Verified product and safety results

### Public release closure

The staged application contains only explicitly named files. Directory
wildcards are unsupported. Its release gate rejects:

- all seven pinned retail hashes;
- APF game filenames (`0A`, `0B`, `1A`, `1B`, `default.xex`, and the system
  update) even before content inspection;
- ISO/XEX/archive/media suffixes and Xbox/media container magic;
- reports, manifests, research exports, decoded audio, screenshots, glTF/GLB,
  preimages, rollback data, emulator state, caches, runtime captures, and build
  output;
- embedded byte arrays/data URIs in JSON;
- `__pycache__`, `.pyc`, symlinks, hardlinks, special files, world-writable
  files, case collisions, and undeclared files.

The sole executable exception is the exact reviewed 56,584-byte Linux
`extract-xiso`, SHA-256
`96e6286d371e47e24474a3b7c89ef5c204ddca9c93c95d5ebcb7bcf1d6eb530f`,
with its exact mandatory license. The 45,434-byte uniform target catalog is
independently size/hash/schema pinned and contains only IDs, allocation sizes,
offsets, and hashes—no pixels, compressed spans, preimages, or other retail
payload.

The APF stage intentionally omits the legacy mixed-game `mod_editor/__init__.py`
and `mod_editor/core/__init__.py`. The runtime gate explicitly proves the
remaining directories import as namespace packages; this avoids silently
pulling the 2K5 product closure into the APF release.

### Source and build safety

- The untouched USA ISO and every file in its extracted boot tree are verified
  through the seven-hash recognition ledger.
- ISO extraction is read-only and includes `$SystemUpdate`; the destructive
  extractor rewrite mode is never used.
- The selected source is never opened for writing.
- Originals are generated into a private cache before an edit is accepted.
- A build always targets a new directory and stages beside that destination.
- Build publication requires the operating system's atomic no-replace directory
  operation. If that guarantee is unavailable, the build fails closed instead
  of falling back to a racy overwrite check.
- Only owned fixed allocations are changed. Everything outside the compiled
  spans is compared to the source, and unchanged siblings are hash checked.
- A failed build removes staging and never publishes a partial destination.
- A successful build contains retail data and must not be redistributed. The
  shareable artifact is the replacement-only `.apf2k8mod` project.
- Large raw exports stream in bounded 8 MiB chunks and publish without replacing
  a destination another process created during export.
- Shareable project metadata is restricted to small, typed target coordinates;
  opaque arrays or payload-like metadata are refused. Duplicate asset IDs,
  duplicate ZIP member names, project symlinks, and conflicting content-addressed
  cache files are also refused.
- Named fast-save binds to the exact single-linked regular project file opened
  or last saved. Missing, symlinked, non-regular, hardlinked, pathname-swapped,
  and externally changed targets fail closed without replacing foreign bytes.
  Project opening validates into a candidate session and compares the file
  identity before and after archive validation before committing it.
- Private replacement-cache entries are hash-checked before reuse. A failed
  project import removes its unpack staging.
- Xenia executables/settings and log destinations are opened without following
  symlinks; a stale temporary settings file is ignored.

### Runtime evidence boundary

- Jersey asset 6 has positive visible runtime evidence and is corroborated in
  the Home/Away editor.
- Pants now has positive visible evidence in the Americans Away Uniform Type
  PANTS leg preview using an unmistakable red/white/blue checker witness.
- All four uniform families and `digital_font` have bounded writer/build
  contracts, but helmet, shoulder, and `digital_font` do not yet have positive
  on-screen visibility proof.
- The bounded `draft_logo` writer is offline-proved and product-wired, but its
  franchise/draft consumer has not yet produced a positive runtime witness.
- The earlier generic roster rebuild was falsified at guest PC `0x84AB1D40`;
  static tracing identified double relocation. The replacement token-preserving
  route visibly consumed `CODEXTEAM` in Logo Selection, Team Summary, and Team
  Select. A one-byte Speed `40` → `99` build also booted and loaded/rendered Dan
  Marino. A later exact-allocation `Marino` → `CODEX` edit visibly rendered in
  both player selection and the Star Card, so bounded player first/last names
  now have their own positive runtime proof. Abbreviations have not inherited
  it, and jersey numbers remain a separate packed-field problem.
- Selector assignment/de-alias experiments have negative or incomplete runtime
  results. The product displays affected shared-team uses and does not promise
  40 independent team banks.
- The private Alpha.23 AUSB candidate booted, selected **Track 12 — Bury Me
  Standing Remix**, and visibly remained in playback for 25 seconds without a
  crash. The completed capture experiment was negative/inconclusive: its
  sustained segment matched neither mutated candidate nor stock Track 12, while
  the self-control established classifier power. This is runtime-partial
  boot/selection/stability evidence; it proves neither modified-audio
  consumption nor stock fallback.
- Xenia is the supported emulator target. Rebuilt ISO output and original Xbox
  360 hardware are untested.

## Coming Soon and why

The action-parity pass specifically downgrades six semantic cards that
do not yet have a dedicated product handler: cross-title model conversion, the
broad uniform-logo catalog, mode/state routing, generic SCNE-to-glTF
conversion, `hi_head` face research, and retained Season/franchise research.
This does not hide their raw resources or remove a working editor: none of
those six had a complete product action. Universal Text remains Editable for
2,410 allocations. In the current packaged checkpoint, Rosters & Players is
Editable through bounded player/team-name, per-attribute rating, and exact
player-position handlers. The position control is a fixed 17-choice semantic
dropdown with individual Revert and project modified state. Every other mapped
roster field retains Preview/Coming Soon status rather than inheriting
permission from a shared container writer.

| Surface | Current status | What is still missing |
| --- | --- | --- |
| Team/player text and identity | Alpha.23 carries forward Alpha.21's 3,191 player-name allocations / 4,482 writable first/last references plus 40 team display names as Editable; all 3,273 allocations / 4,628 mapped references remain browsable; visual and real-source public-product smoke pass | Both abbreviation families still need their own later runtime spot checks; the zero-capacity allocation, mixed/unknown scopes, jersey numbers, and other packed fields remain locked. |
| Player base ratings | Editable, native exact 0–99 Replace/Revert for 28 independently stored fields × 2,254 players | Native source 100 is displayed/revertible but not newly authored. Overall is derived; Gold/Silver/Bronze tier and abilities are separate systems. A player-load proof exists, but a controlled gameplay A/B or numeric consumer screen is still needed to measure semantic effect strength. |
| Player positions | Editable through a fixed semantic dropdown covering all 17 exact codes (QB through DE), with per-player Replace/Revert and modified state | The writer atomically preserves semantic `+0x34` and required mirror `+0x35`; the first changed-position Xenia spot check remains pending. Position edits deliberately do not alter ratings, team membership, tier, abilities, or depth-chart slots. |
| Membership, depth charts, roster capacity | Alpha.23 contains a 32-team × 53-row **planner**; runtime writeback remains Coming Soon | Each populated source team has 42 runtime membership pointers. Rows 43–53 are eleven project-only reserve choices saved in a retail-free `.apf2k8roster`; Build does not apply them. True 53-active-player teams require an emulator-target XEX accessor/direct-consumer patch plus owned side-table storage. Teams 25–32 use populated online-placeholder records whose offline selection ownership remains unproved. |
| Logos and team art | Dedicated `draft_logo` Editable; raw remainder browse/export; broad uniform-logo semantic card Coming Soon | Runtime ownership plus per-family fixed-allocation writers for uniform logos and text logos. |
| Field/end-zone/midfield art | 258-record / 7-family / 125-package semantic browse/export map; Replace locked | Exact team/stadium/selector/material ownership, a bounded writer, and one visible replacement proof. |
| Stadium Studio texture picking | Interactive 3D geometry, surface identity, and same-package preview/export; Replace locked | Runtime material/TXTR ownership. Static proof reaches 116 meshes, 328 draws, 113 materials, and 13 shader families, but finds zero scene-system references among 737 named texture identities. |
| General stadium geometry | Coming Soon | Only narrow fixed-count research writers exist; no product-level runtime visibility proof. |
| Scorebug composition | Preview/export | `digital_font` is editable; remaining consumed textures and composition ownership need runtime proof. |
| Universal text editing | 2,410 of 2,413 TXT/STRG pool allocations editable; one exact allocation visibly proved in Xenia | `MOD BIOGRAPHY` proves outer 1127 / inner 0 / pool 11 and the common writer/build path. Two fallbacks, one zero-capacity STRG allocation, layout geometry, seven executable labels, and resistant non-bank structures stay read-only; other rows do not receive invented screen ownership. |
| Commentary/audio replacement | All 2,261 standalone `AUDO` slots and 45,514 semantic AUSB substreams backed by 45,513 canonical physical ranges support strict target-exact XMA1 Replace/Revert/project/preview/Build. Alpha.28 supports selected PCM16 WAV plus v2 folder/ZIP PCM16 packs with up to 256 supplied WAVs per atomic import through a separately installed native/Wine encoder. | The Track 12 runtime candidate booted and visibly played for 25 seconds, but its capture matched neither mutated candidate nor stock Track 12, so modified-audio causality and stock fallback remain unproved. No encoder ships; real-tool compatibility is untested. FLAC/MP3, mixed-format packs, more than 256 supplied WAVs per transaction, and whole physical-bank replacement remain unsupported. |
| Draft/catch/gameplay presets | Coming Soon | Controlled causal runtime experiments and documented presets. |
| Play editor | Inspector only | PLAY route-node and formation authoring semantics are not decoded sufficiently for safe writes. |
| Mode/state routing and franchise | Coming Soon semantic cards; raw/decoded inspectors remain available | Persistent Coach's Desk ownership, live route proof, and multi-season state routing remain unproved. |
| Generic SCNE/face/model conversion | Coming Soon semantic cards; raw scene and `hi_head` exports remain available | Dedicated product handlers plus general mesh/material/animation import, face ownership, and allocation ownership are unproved. |

## Headless QA policy

All nonvisual work is terminal-only: release checks, module imports, source
hashing, extraction, indexing, exports, project round-trips, and builds. The
runtime checker imports the Qt shell while asserting that import creates no
`QApplication` and opens no window.

Any visual desktop or emulator action must use the isolated virtual display
`DISPLAY=:99` through the designated desktop operator. It must never use the
user's active `:0` display, take the user's pointer, or assume what is visible.
Xenia gets fresh per-test Wine, storage, content, and cache roots so old state
cannot masquerade as a successful result.

## Best next step

The exact-slot AUSB route remains end-to-end in the current Alpha.28 packaged
checkpoint for all 45,514 semantic rows. Alpha.28 can pass one selected WAV or
a v2 pack with up to 256 supplied exact-shape PCM16 WAVs through a separately
installed encoder before applying the same final validation path.
The Track 12 capture experiment is
complete and negative/inconclusive, so do not replay the same ambiguous input.
Use a wholly independently encoded, unmistakable replacement when a usable
XMA1 encoder exists, or trace mixer/routing before another runtime replay. A
later non-soundtrack AUSB spot check must remain bounded. The observed 25-second
selection/playback window proves boot and stability, not authored-audio
consumption or stock fallback. Alpha.28's exact archive identity
belongs in its authoritative adjacent sidecar; this status does not embed a
self-hash or claim final packaged visual QA.
For the roster planner, the single best next experiment is a version-pinned
log-only execution of the completed slot-43 accessor prototype while the stock
42-pointer prefix remains unchanged. Only a positive observe traversal permits
the separately isolated one-player modified run. Later, run one-variable spot
checks for the two abbreviation families rather than
granting them the player-name proof. The best later runtime ratings proof remains a
controlled stock-versus-patched Speed or Catch A/B that measures an effect
size. See the positive
[rating result](../product/APF_PLAYER_RATINGS_TOKEN_PRESERVING_RUNTIME.md),
[team-name result](../product/APF_ROSTER_IDENTITY_TOKEN_PRESERVING_RUNTIME.md),
historical [negative diagnostic](../product/APF_ROSTER_IDENTITY_RUNTIME_NEGATIVE.md),
and the separate
[32-team/53-player feasibility note](../product/APF_32_TEAM_53_ROSTER_FEASIBILITY.md).

For Stadium ownership, do not repeat the Wine-hosted instruction breakpoint
that already failed before guest-state capture. Standalone `AUDO` and addressed
`AUSB` exact-slot replacement do not depend on an encoder when the modder
supplies compatible pre-encoded XMA1. Selected exact-shape PCM16 or a v2 pack
with up to 256 supplied WAVs can use the separately installed encoder bridge;
FLAC/MP3 and mixed-format packs remain unsupported.
The complete 47,814-row audio catalog, atomic cue
export, waveform/playback where decoding verifies, exact per-bank export, and
the private all-19-original-bank bundle remain implemented product actions;
whole-bank replacement is not implied by individual exact-slot editing.

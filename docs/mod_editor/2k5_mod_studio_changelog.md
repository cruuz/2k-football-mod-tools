# 2K5 Mod Studio — Product Changelog

This is the modder-facing record of functionality that is actually present in
runnable builds. A mapped resource is not listed as editable unless its product
writer is connected to Replace, Revert, project save/load, and the composed
build path.

## v1.0 RC29 Project-backed Audio Cue Labels — 2026-07-20

- Added custom titles and multiline notes for every playable standalone cue
  and indexed streaming range. Labels are keyed by stable logical cue ID, so
  shared physical aliases may carry separate human meanings.
- Added immediate title/note search, a **Labeled only** filter, pencil-marked
  table names, original game-label/ID preservation, character counters, and
  per-cue Save/Clear controls in the Audio inspector.
- Added deterministic `audio-annotations.json` project persistence with exact
  manifest filename, size, count, and SHA-256 binding. Annotation-only projects
  are valid; legacy projects remain compatible.
- Added one-action Undo and Revert All coverage plus autosave recovery. Cue
  labels are counted separately from game edits and never enable Build or
  enter the canonical XISO provider document.
- Retained unsaved title/note drafts while browsing, paging, or changing Audio
  filters. Labeled-only controls now appear only for project-backed hosts.
- Carried custom titles, notes, and the preserved game/catalog name into local
  matching and shortlist ZIP manifests; playlists use the custom title while
  stable IDs and canonical payload paths remain unchanged.
- Made project import, mixed Revert All, and its Undo atomic across PNG, WAV,
  text, Stadium, Crib, and cue-label state. Disk-full or final handoff failure
  restores the prior manifest/ledgers and removes the disposable candidate.
- Bounded user metadata to 54,421 logical cues, 120 title characters, 2,000
  note characters, and 16 MiB of UTF-8 text. NUL/unsupported controls,
  Unicode format controls, duplicate JSON keys/IDs, rich-text interpretation,
  malformed metadata, undeclared members, and checksum/size mismatches are
  refused.
- No retail audio, decoded PCM, source path, physical offset, rollback byte, or
  game asset is stored in an annotation or annotation-only project.

## v1.0 RC28 Audio Pack Preview and Apply — 2026-07-20

- Replaced one-click Audio replacement-pack import with an explicit two-step
  **Preview → Apply** workflow. Preview fully validates the folder or ZIP,
  manifest/source binding, baselines, supplied file set, WAV shapes, origin
  authorization, current staged bytes, and shared physical aliases without
  changing the project, manifest, Undo history, replacement tree, or source
  XISO.
- Added a frozen, sanitized preview summary for modders: supplied, would-change,
  already-current, restore-original, unique physical change/restore, linked
  alias, and resulting Modified counts, plus a bounded list of readable change
  labels. An unchanged-only pack succeeds as a preview but offers no Apply.
- Bound confirmation to an opaque session-local token covering the exact pack
  member digest, schema, loaded source, session identity, and monotonic
  project/audio mutation revision. The token is hidden from result
  representation and neither the public preview nor the session retains ZIP
  paths, WAV bytes, private source hashes, or private member hashes.
- Apply reopens the chosen pack, snapshots caller-controlled WAVs privately,
  reruns every validation, verifies the preview token, and only then performs
  the existing single atomic Undoable transaction. A changed valid WAV, source,
  session, or project state is refused and requires a new Preview.
- Added the confirmation dialog's logical-versus-physical counts, explicit
  restore and linked-alias disclosures, first-change labels, Cancel/no-change
  paths, and worker-drain handoff so Preview fully finishes before Apply starts.
  The release candidate remains headless; no audible-runtime claim is added.

## v1.0 RC27 All Playable Audio — 2026-07-20

- Made **All Playable Audio (54,421)** the default Audio scope. Its canonical
  order is domain-prefixed and stable: all 850 standalone `AUDO` rows first,
  followed by all 53,571 indexed streaming ranges. Complete streaming banks
  and opaque raw containers remain in their dedicated scopes because they are
  not individual playable sounds.
- Added combined search, stable paging, family filtering, and one global
  **Modified** filter without wrapping or changing either row type. Search
  reuses the existing standalone/range metadata haystacks instead of retaining
  another 54,421 copies of searchable strings.
- Kept meaning-confidence honest: the 1/152/697 confidence groups remain
  standalone-only and are not partially applied to the mixed scope. Select
  **Standalone sounds** to use them.
- Added bounded matching export for 1–256 mixed results as current playable
  WAVs. Each record keeps its truthful retail-derived or user-replacement label;
  raw `.bin` export remains available only from the dedicated streaming-bank or
  indexed-range scopes.
- Preserved the frozen v4 **all-850 standalone** replacement-pack contract. RC27
  does not claim an all-54,421 template: streaming ranges continue to use
  per-row Replace or the existing 1–256 selected-shortlist replacement pack.
- Closed the release candidate headlessly: the complete cross-title suite
  passes **1090/1090**, the 2K5 slice passes **603/603**, the release-focused
  selection passes **122/122**, and the Audio/Crib/project lifecycle selection
  passes **40/40**. Independent adversarial review reports GO with no P0/P1
  finding. No visible desktop, pointer, audio device, emulator, or external
  player was used.

## v1.0 RC26 Read-only Audio Waveforms — 2026-07-20

- Added an explicit **Load waveform** view for all 850 standalone cues and all
  53,571 playable streaming ranges. It reads the selected sound's private
  current PCM16 WAV, including a staged replacement, without autoplay or any
  project mutation. Whole streaming banks and opaque raw containers remain
  honestly unavailable as single waveforms.
- Kept long sounds bounded: the reader retains at most 640 normalized envelope
  columns and samples no more than 1,024 frames per column. It opens only a
  regular non-link file, detects a WAV that changes during reading, and leaves
  the private WAV byte-for-byte untouched.
- Bound the waveform to the exact source, selection, and current audio content.
  Replace, Revert, batch import, project load, Undo, Revert All, selection
  changes, and source transitions invalidate both stale waveforms and playback,
  even when the logical asset ID remains the same.
- Added **Cancel waveform** with truthful limits: bounded sampling is
  cooperative, while an in-process source decode finishes before its now-stale
  result is discarded. Audio and Crib now share one mutually exclusive worker
  lane; global actions and sibling editors remain fenced until its owner drains,
  while the owning Audio page keeps waveform Cancel reachable.
- Added seven bounded-reader tests and seventeen shell-integration tests for signal
  edges, direct and visible action fences, close refusal, autosave deferral, and
  same-ID invalidation, then expanded the lifecycle matrix for Audio/Crib mutual
  exclusion and source/project/save/recovery/Undo/Revert-All completion order.
  The complete combined headless suite passes **1088/1088**, the current 2K5
  slice passes **601/601**, the release-focused selection passes **107/107**,
  and the final independent review is GO with no P0/P1 finding. No visible
  desktop, audio device, emulator, or external player was used.

## v1.0 RC25 Recoverable Audio Curation — 2026-07-20

- Made Audio shortlist **Clear** reversible. After clearing 1–256 selected
  sounds, the same control becomes **Undo** and restores every standalone cue
  and streaming range in its exact prior order.
- Keeps one deliberately bounded restore snapshot. A successful add/remove
  consumes it, and a successful source load clears it; searches, filters,
  exports, project navigation, and a refused source load do not. Clear/Undo is
  session-only and emits no replacement/project mutations.
- Preserved the 930-pixel Audio-toolbar contract. The compact visible label is
  **Undo**; its accessible name, tooltip, and progress copy carry the restored
  count and behavior. Longer count-bearing labels were measured and rejected
  because they widened the panel.
- Closed a failed-source-load lifecycle bug found during independent review.
  Because source loading commits transactionally, a refused replacement source
  now restores the still-valid old Audio page/actions (or the honest empty Load
  XISO state on a first-load failure) while the invalidated preview stays stopped.
- Six new headless tests cover browser/review Clear, mixed 256-sound exact-order
  restoration, no project mutation, undo expiration, current/pending old-query
  recovery, and first-load refusal. The complete headless/offscreen product
  regression passes **1034/1034**, and the focused Audio/UI/source-bound/
  packaging selection passes **118/118**. No visible GUI, audio device,
  emulator, or external desktop player was launched.

## v1.0 RC24 Applied Audio Search Results — 2026-07-20

- Bound every Audio catalog page to the exact source epoch, search text, scope,
  family, edit status, and meaning-confidence controls that produced it. The
  220 ms typing debounce can no longer leave page-wide actions attached to the
  previous result set.
- Immediately disables and independently guards **Add this page**, **Add all
  matching**, **Export matching audio**, Previous, and Next while a new search
  is pending. The counter says **Updating audio results…** until the refreshed
  page is actually installed.
- Keeps safe selected-row work responsive during that brief update: Play,
  Export, Replace, Revert, and **Add selected sound** still target the exact row
  that remains visibly selected.
- Stops a pending search timer when a filter, scope, Soundtrack quick view, or
  source transition performs an immediate refresh. Shortlist-review pagination
  remains independent and usable.
- Five new offscreen race regressions cover stale page-add, matching export,
  all-matching requery/warnings, pagination/selection stability, and automatic
  timer application; a sixth covers the fast type/erase round trip. The complete
  headless/offscreen product regression passes **1028/1028**, and the focused
  Audio/UI/source-bound/packaging selection passes **112/112**. No visible GUI,
  audio device, emulator, or external desktop player was launched.

## v1.0 RC23 Selection-Bound Audio Preview — 2026-07-20

- Bound every preview request to a monotonically increasing source/selection
  epoch and exact asset ID. A delayed preparation success or error from A can
  no longer act after A → B → A, and a source switch invalidates old callbacks
  even when the new game exposes the same asset ID.
- Centralized all effective Audio selection changes. Refreshing the same row
  preserves current playback; selecting a different row, leaving a result set,
  or resetting the source stops the controlled player and restores **Play**.
- Queued one-click playback for a newly selected row while the old controlled
  process finishes stopping, instead of requiring a second click or racing two
  processes. The queue also drains when the old process reports FailedToStart,
  whose Qt signal path has no later `finished` event.
- Removed the unowned desktop-handler fallback. Playback now uses only
  `ffplay`, `paplay`, or `aplay`, which Mod Studio can stop; if none exists, the
  UI gives an actionable install message. Preparation/start failures clear all
  pending preview state instead of leaving **Preparing…** stuck.
- Source loading invalidates Audio before its worker begins and disables the
  embedded Audio panel for the entire global blocking operation. Five new
  Audio lifecycle tests plus one shell-order test prove these transitions.
- The complete headless/offscreen product regression passes **1022/1022**, and
  the focused Audio/UI/source-bound/packaging selection passes **106/106**. No
  visible GUI, audio device, emulator, or external desktop player was launched.

## v1.0 RC22 Responsive Audio Toolbars — 2026-07-20

- Reflowed the five Audio search/filter controls and seven shortlist controls
  into two deliberate rows instead of two oversized single-row toolbars. Every
  control remains visible; no action moved into an overflow menu.
- Reduced the Audio panel's normal minimum-width hint from 1,442 to 833 pixels.
  A conservative worst-case state—256-result add/review/export labels and a
  full shortlist counter—fits at 930 pixels, within the main window's 932-pixel
  workspace at its supported 1,180-pixel minimum width.
- Added an offscreen geometry regression that pins every grid position, applies
  the longest labels together, and proves all 12 controls are inside the panel,
  non-overlapping, and at least their own minimum usable width.
- Kept Audio behavior unchanged: search debounce, filters, selection, shortlist
  order, exports, replacement state, and Build routes use the same controls and
  signal connections as before.
- The complete headless/offscreen product regression passes **1016/1016**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **100/100**. No visible GUI or emulator was launched for this checkpoint.

## v1.0 RC21 Scrollable Audio Inspector — 2026-07-20

- Made the dense selected-sound inspector vertically scrollable while keeping
  the WAV drop target and Play/Export/Replace/Revert actions pinned below it.
  Long ownership lists can no longer push the actions out of reach.
- Preserved the complete technical truth. Names, exact IDs, format/WAV
  contracts, ownership and alias warnings, shared-slot owner IDs, and the
  all-850 replacement path remain unabridged and wrap without changing their
  copied text.
- Made the title, technical metadata, ownership details, action requirements,
  and pack path selectable by mouse and keyboard, with explicit accessible
  names for assistive technology.
- Reset the inspector to its top whenever the selected row changes, and reduced
  its bounded minimum width from 360 to 320 pixels. This checkpoint fixes the
  detail pane's constrained-height behavior; the separate single-row toolbar
  width is not claimed as solved here.
- The complete headless/offscreen product regression passes **1015/1015**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **99/99**. No visible GUI or emulator was launched for this checkpoint.

## v1.0 RC20 Add All Matching Audio — 2026-07-20

- Added a separate **Add all matching** Audio action beside **Add this page**.
  It collects one complete 1–256-row filtered result across Standalone Audio or
  Playable streaming ranges while preserving canonical order and keeping
  already-selected IDs once.
- Made the critical reviewed-label workflow one action: **Meaning confidence →
  Reviewed labels (152) → Add all matching (152) → Selected shortlist (1–256)**.
  The exported v2 replacement template receives those exact 152 IDs in the
  visible shortlist order.
- Kept the operation atomic and session-only. The current search, scope,
  family, edit status, meaning confidence, stable count/order, row types, and
  unique IDs are rechecked before mutation; an overflow or changed/hostile
  result adds nothing and never touches project replacements.
- Complete streaming banks and raw BANK/ABNK/WBNK containers remain ineligible,
  and results above 256 ask the modder to narrow the filters.
- The complete headless/offscreen product regression passes **1014/1014**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **98/98**. No GUI or emulator was launched for this checkpoint.

## v1.0 RC19 Audio Meaning-Confidence Filter — 2026-07-20

- Added a dedicated **Meaning confidence** filter to Standalone Audio with the
  exact v4 cue-map groups: **Menu Back route (1)**, **Reviewed labels (152)**,
  and **Provisional labels (697)**. This signal no longer has to be inferred
  from warnings or confused with the separate Editable/Modified status filter.
- Used the same public `standalone_runtime_meaning_status` contract for CSV
  generation, catalog-host browsing, and the product facade. Filtered counts,
  pagination, search, family/edit-status combinations, and matching collection
  export therefore resolve the same canonical rows.
- Disabled and reset the filter for streaming banks, indexed AUSB ranges, and
  raw universal containers, where the standalone meaning domain does not apply.
  Shortlist review temporarily disables it without losing the underlying
  standalone selection.
- Preserved the honest boundary: all 850 physical standalone slots remain
  Editable. “Provisional” means the human label/runtime caller is unproved; it
  does not mean the fixed writer target is approximate or unsafe.
- The complete headless/offscreen product regression passes **1009/1009**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **93/93**. No GUI or emulator was launched for this checkpoint.

## v1.0 RC18 In-App Audio Pack Paths — 2026-07-20

- Added an **All-850 replacement pack path** card to every standalone Audio
  detail view. It shows the exact generic v4 destination used by
  `AUDIO-CUE-MAP.csv`, so modders can move from search/playback to authoring
  without manually finding the same row in a spreadsheet.
- Added a selectable path and keyboard-accessible **Copy pack path** action with
  **Ctrl+Shift+C**. Clipboard access occurs only after explicit activation;
  browsing, selecting, filtering, and paging never replace clipboard contents.
- Derived the path from the same canonical catalog order used by v3/v4 export.
  The UI receives only `replacements/NNN__selected-audio.wav`; it does not gain
  physical selectors, offsets, source fingerprints, or other private metadata.
- Kept the boundary obvious: complete streaming banks, indexed AUSB ranges, and
  raw universal containers hide and disable the standalone-only action. Their
  existing selected-shortlist/export workflows are unchanged.
- The complete headless/offscreen product regression passes **1006/1006**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **90/90**. No GUI or emulator was launched for this checkpoint.

## v1.0 RC17 Human-Friendly 850-Sound Cue Map — 2026-07-20

- Added `AUDIO-CUE-MAP.csv` to the default **All standalone sounds (850)**
  authoring hand-off. Each canonical row now connects its generic replacement
  filename to the public Audio-browser ID, display name, family, duration,
  channels, sample rate, exact frame count, edit route, legacy membership, alias
  status, and honest runtime-meaning status. Modders no longer have to manually
  cross-reference 850 raw IDs before authoring WAVs.
- Introduced a dedicated v4 format instead of changing the shipped v3 contract.
  Direct complete exports without the new map still produce byte-identical v3
  packs; v1 legacy, v2 selected, v3 complete, and v4 mapped packs all import.
  The GUI chooses v4 for the one-click all-850 workflow.
- Made the CSV deterministic, UTF-8/LF, single-line, formula-safe, and read-only
  reference metadata. Import verifies its exact manifest path, schema, row
  count, SHA-256, canonical row order, columns, values, and 1/152/697 meaning
  status distribution before any WAV can change the project. Modders can copy
  the CSV outside the pack for personal notes; a changed or reordered in-pack
  map is refused rather than silently trusted.
- Kept the hand-off retail-free: the new map contains no WAVs, decoded PCM,
  physical offsets, source/private audio fingerprints, rollback bytes, or
  originals. The template still binds to the user's whole source XISO, missing
  replacement WAVs still mean “skip,” and all accepted changes remain one
  atomic Undo action.
- The complete headless/offscreen product regression passes **1005/1005**, and
  the focused audio/facade/GUI/packaging selection passes **83/83**. No GUI or
  emulator was launched for this checkpoint.

## v1.0 RC16 Complete 850-Sound Authoring Pack — 2026-07-20

- Made **All standalone sounds (850)** the default batch-authoring choice in
  Audio. One click now exports a complete metadata-only folder or deterministic
  ZIP for Menu Back plus all 849 fixed-AUDO slots; modders can fill only the WAV
  paths they want to change and import all true changes as one Undo action.
- Added a dedicated v3 pack contract instead of changing either existing
  format. The v3 route validates the exact canonical 850-row source order,
  unique logical IDs and underlying physical selectors, one Menu Back row,
  exact PCM16 contracts, the whole-XISO SHA-256 binding, and current-edit
  baselines. Public rows do not expose those physical selectors. Missing
  replacement WAVs mean “skip”; changed guide/manifest/order, unknown or
  duplicate rows, invalid WAVs, stale baselines, and extra archive members fail
  before the project changes.
- Preserved both older workflows. Legacy v1 remains the same frozen ordered
  153-cue format, while selected v2 remains an ordered 1–256-sound pack that can
  mix standalone cues with exact soundtrack, commentary, crowd, stadium, and
  presentation ranges. Whole streaming banks remain excluded from all three.
- Kept hand-off files retail-free by construction. An empty v3 template contains
  only `EDIT-AUDIO.md`, `audio-replacement-pack.json`, and the empty
  `replacements/` directory marker—never original WAVs, decoded audio, game
  offsets, private per-audio PCM fingerprint inventories, originals, or
  rollback bytes. It does include the whole-XISO SHA-256 needed to bind the
  hand-off to the user's own source. The clean 144-file release stage
  independently reproduces the all-850 manifest and reports
  `private_inventory=false` and `retail=false`.
- The complete headless/offscreen product regression passes **1001/1001**, and
  the focused audio/facade/GUI/packaging selection passes **79/79**. RC16 does
  not claim that provisional cue names are semantically correct or that every
  edited slot has been heard in-game; those 697 uncertain rows retain their
  prominent physical-slot/runtime-meaning warning.

## v1.0 RC15 Complete Standalone Audio Editing — 2026-07-20

- Promoted all **850 standalone AUDO sounds** to Editable. Menu Back keeps its
  separate fixed-target route; all 849 other rows use stable outer/chunk IDs,
  exact non-overlapping physical allocations, strict per-row PCM16 shape
  validation, deterministic Xbox IMA encoding, and the unified copied-XISO
  build path.
- Replaced the old hidden lock on 697 alias-related rows with an honest warning:
  the physical slot being changed is exact, but its provisional name, semantic
  cue identity, and runtime selector owner may be unknown. Matching names or
  decoded content do not collapse distinct spans or imply that another slot
  changes.
- Preserved old v1 replacement packs exactly. **Legacy 153-cue pack** still
  resolves only Menu Back plus the original 152 classified rows in the same
  order; **Selected shortlist (1–256)** can now author any of the newly unlocked
  physical slots alongside exact AUSB soundtrack, commentary, stadium, crowd,
  and presentation ranges.
- Updated the capability registry, Audio panel copy/accessibility, product docs,
  runtime closure receipt, and pinned provider closure to report 850 Editable /
  0 Export-only standalone rows. Complete raw streaming banks remain
  Export-only; RC15 does not claim recovered cue names, loops, gain/pan,
  priority, mixer ownership, or audible runtime consumption.
- The complete headless/offscreen product regression passes **993/993**. A
  compatibility regression pins the RC14 ordered 153-ID set to SHA-256
  `156c3a02e4ef27ee1a245a0946a3033575dc3d30872f1664b2adf1dfbd488ecc`;
  the public stage separately proves all 850 modern edit routes while preserving
  the legacy manifest/guide contract.

## v1.0 RC14 Roster Workspace Navigation — 2026-07-20

- Moved the complete current and historical name/number workflow to the place
  modders expect it: **Rosters & Players → Players & Numbers**. The same page
  keeps **Portraits & Faces** one tab away, so a player can be renamed,
  renumbered, and visually updated without jumping to an unrelated category.
- Kept **Text & Team Identity** focused on the universal fixed-allocation text
  browser. No writer, project schema, source allocation, or build behavior
  changed; this checkpoint fixes product navigation and discoverability.
- Split the shared text/roster panel into scoped views. Each sidebar workspace
  now constructs and reloads only its own models instead of processing 23,346
  text rows and 6,522 roster rows twice. The legacy combined view remains
  available to internal callers and tests.
- Preserved source/project reload, Undo, Revert All, autosave, status reporting,
  and Ctrl+F routing across current players, historical players, portraits,
  faces, and universal text. All work and verification remained headless; no
  emulator or visible desktop session was launched.
- The final focused navigation/edit selection passes **44/44**, including real
  Apply operations in both scoped views. The complete headless desktop-tool
  regression passes **992/992**, and independent review returned **GO** after
  the scoped change-refresh path was exercised directly.

## v1.0 RC13 Modified-Range Collection Parity — 2026-07-20

- Fixed the last collection-export mismatch after fixed-range AUSB editing
  shipped. **Export matching audio** and **Export selected WAVs** now include a
  Modified streaming range's staged user-replacement WAV, in order, exactly as
  individual Play and Export WAV already do.
- Kept the retail boundary explicit: an unmodified range is still labeled
  `retail_derived`; complete streaming banks and exact raw-range `.bin` exports
  can never be labeled as user replacements. Collection ZIPs remain private
  listening exports and never enter project, Undo, recovery, or Build state.
- Improved keyboard search routing so the global **Ctrl+F** action discovers the
  visible search field in Text & Team Identity, The Crib, Playbooks, and other
  product workspaces instead of incorrectly reporting that the page has no
  search box.

## v1.0 RC12 Selected Audio-Shortlist Authoring Packs — 2026-07-20

- Added **Selected shortlist (1–256)** beside the existing **All standalone
  cues (153)** replacement-pack mode. A modder can now curate any ordered mix
  of Editable standalone cues and fixed-slot soundtrack, commentary, stadium,
  crowd, or presentation ranges, export one metadata-only folder/ZIP, fill only
  the desired WAV paths, and import all true changes as one Undo action.
- Kept old v1 153-cue packs compatible. New v2 packs preserve the shortlist's
  logical order and exact PCM16 channel/rate/frame contracts. They carry only
  logical IDs, user-replacement baselines, source binding, and disclosed logical
  alias owners—never physical slot IDs, offsets, bank filenames, private source
  fingerprints, original audio, or rollback bytes.
- Reused the shipped fixed-range writer and authorized batch transaction instead
  of adding another encoder. Every supplied WAV crosses exact shape and private
  source-origin checks before commit. Identical files for two logical owners of
  the one shared AUSB slot collapse to one physical edit; divergent files fail
  before the project changes.
- Corrected stale product copy that called individually Editable streaming
  ranges browse/export-only. Complete raw banks remain Export-only: RC12 does
  not claim whole-bank repacking, recovered cue names, loop/gain/pan/priority
  editing, mixer ownership, or in-game audible consumption.
- Kept the listening shortlist broader than the authoring pack without making
  the mismatch mysterious. Playable-but-Export-only standalone sounds can still
  stay in a listening/WAV collection, but Selected-shortlist template export is
  disabled with an exact count and removal instructions until every chosen row
  is Editable.
- Kept the rights boundary honest. The private gates reject exact source PCM and
  unchanged excerpts covered by their deterministic window/anchor rules. They
  cannot prove authorship or classify transformed/re-encoded copyrighted audio;
  mod authors remain responsible for what they use and distribute.
- The final headless/offscreen desktop-tool regression passes **973/973** and
  the focused RC12 catalog/audio/GUI/packaging selection passes **75/75**. A
  clean 144-file public stage passes release → runtime closure → desktop/Bash →
  release, including a source-free ordered standalone+AUSB v2 export/import
  probe and `audio_replacement_pack_v2=selected_mixed` receipt. No source XISO,
  WAV, private audio inventory, GUI, or emulator entered this checkpoint.

## v1.0 RC11 Complete Fixed-Range AUSB Editing — 2026-07-20

- Promoted all **53,571 logical AUSB streaming ranges** to Editable through
  **53,570 exact physical fixed slots**. Replace accepts a canonical authored
  PCM16 WAV with the selected row's exact channel/rate/frame shape, encodes
  Xbox IMA into the unchanged allocation, and composes the resulting one-span
  or pack-seam edit with every other Mod Studio category. The 17 complete raw
  banks remain Export-only; this is not a general bank repacker.
- Added one physical edit state behind logical aliases. The one shared slot
  displays both affected owners; Replace, Modified filtering, Play, WAV export,
  Revert, Undo, Revert All, project save/load, and Build change them together.
  Identical duplicate alias requests collapse to one record, while divergent
  WAVs fail atomically before the project changes.
- Added automatic first-use source-audio preparation. The first Replace,
  standalone batch import, or shared audio-project load can build the complete
  private exact and containment indexes with in-app progress. It normally takes
  about 20–35 minutes once, keeps the source XISO read-only, releases the main
  facade lock while working, and refuses a source/project switch before staging.
- All authored WAV paths now cross the same immutable-byte origin gate when
  staging, saving, loading, building, and independently verifying. Exact source
  PCM and unchanged source excerpts are refused. A shareable `.2k5mod` contains
  only a logical asset ID plus the user's WAV; canonical slots, offsets, source
  fingerprints, private inventories, original audio, and rollback bytes never
  enter it.
- Added the real registry capability
  `nfl2k5.audio.ausb_fixed_range_wav`, bringing the shared registry to **62**
  rows and the NFL 2K5 product catalog to **31**. The init-free unified provider
  pins its exact 60-file execution closure and receives private origin inputs
  only for audio builds; visual-only validation/builds remain unchanged.
- The clean release-stage review contains 144 allowlisted files and passes its
  runtime closure with 46 product modules plus 22 tool modules. It includes no
  XISO, WAV, private inventory, decoded source audio, or other retail payload.
  Headless/offscreen tests cover the complete UI/session/project/provider path;
  no audible runtime cue-identity claim is made until a game spot-check exists.
- Completed one real-source, authored-WAV product-flow proof through Replace,
  Modified playback/export, retail-free project save, fresh-session project
  load, Build, and independent Verify. The one logical edit compiled to one
  physical span; Build and Verify both passed, the 6.30 GB source remained
  byte-for-byte unchanged, and the generated test output was removed afterward.
  This proves the offline product path, not in-game audibility or semantic cue
  ownership.

## Post-RC10 Audio Scale and Project-Bounds Checkpoint — 2026-07-20

- Precomputed the metadata-only Audio search index once per loaded source.
  Real-source searches across 53,571 indexed streaming rows now take roughly
  23–35 ms median instead of rebuilding every row's search text for about
  367–424 ms on each query. Reloading a source replaces the catalog and search
  index together; a focused lifecycle test proves terms from the old catalog
  do not survive.
- Added one shared limit of 25,000 simultaneous visual-plus-audio edits per
  `.2k5mod`, a 1 GiB aggregate replacement-payload limit, and an expanded ZIP
  preflight. Loading rejects excessive declared expansion and insufficient
  staging space before extracting a replacement. Saving uses a descriptor-
  pinned, single-link read for each authored WAV and refuses a project that
  would exceed either its expanded or 2 GiB archive boundary.
- Replaced the unified backend's quadratic span-overlap loop with a sorted,
  adjacent check. A worst-budget 25,004-span synthetic set validates in about
  3.24 ms while retaining the same out-of-order overlap refusal. The release
  gate now also rejects private `derived/` audio-origin cache trees, the exact
  fingerprint schema, and both containment v1/v2 schemas even if a future
  allowlist names or renames them.
- Added the isolated fixed-allocation AUSB codec/span backend and private exact-
  PCM inventory store as internal source slices. They cover 53,570 physical
  streaming slots behind 53,571 visible catalog rows, including one two-owner
  alias and four pack-seam slots. The independently reviewed read-only source
  scanner has now directly decoded all 850 standalone cues and all 53,570
  physical streaming slots, passed a final complete-XISO recheck, and published
  one 13.84 MiB private, metadata-only exact-PCM inventory. A clean second pass
  loaded it without rebuilding. The source XISO and archive cache were not
  modified.
- Added an independently reviewed exact-containment primitive as another
  internal source slice. Quarter-second source windows on a quarter-second grid
  guarantee detection of unchanged, same-shape excerpts at the roughly 500 ms
  bound; short and sparse cues use deterministic nonzero anchors, and only
  all-zero windows are exempt.
- Persisted the approved real-source containment census after a hostile review
  closed directory-swap redirection, concurrent-publication source rechecking,
  and arbitrary owner-label leakage. The read-only scan covered 54,420 cues /
  54,421 logical owners and published 615,244 digest records in a 152,956,258-
  byte private mode-0600 document. It stores no WAV, PCM, encoded sound, source
  path, or game span. A clean reuse load completed without re-decoding streaming
  payloads and repeated the complete source authentication.
- Added the sealed final-Build authorization boundary for all three fixed audio
  routes: Menu Back, standalone AUDO, and indexed AUSB. Both private origin
  checks receive the exact immutable WAV bytes later consumed by the encoder;
  a forged lookalike cannot cross the hand-off. The AUSB compiler emits exactly
  one physical span or one two-pack seam, binds aliases to one slot, deduplicates
  identical alias edits, and rejects divergent ones. Audio projects pass the
  canonical private inventories to both Build and independent Verify, while
  visual-only builds require neither file. Streaming Replace remains hidden
  until the shared session/project/Audio-panel wiring completes; no new runtime
  consumption claim is made here.

## v1.0 RC10 Accessibility and Layout Checkpoint — 2026-07-20

- Advanced the current product version to **v1.0 RC10**. The sidebar release
  label continues to derive from the package version, so the visible product
  name and the version checked by the release tests cannot drift apart.
- Added **Ctrl+F** as a window-wide shortcut for the active workspace's search
  box. It focuses the relevant search field, selects any existing query, and
  reports a short instruction in the operation-status area. Pages without a
  search box point the modder to category navigation instead.
- Added **Ctrl+1** as a window-wide shortcut for the complete modding-category
  sidebar. The category list advertises the shortcut in its tooltip and
  assistive description, so mouse-free navigation is discoverable inside the
  product.
- Added clear keyboard-focus outlines to the category list, asset lists, and
  component trees. Search fields, the current-operation label and progress
  bar, **Build Modded XISO**, and **Launch Latest Build** now expose concise
  accessible names and instructions for assistive software.
- Made the shell more tolerant of larger desktop fonts: the header and footer
  can grow instead of being trapped at one fixed height, while roomier category
  rows, primary controls, spacing, and padding keep the main workflow easier to
  scan and target.
- Added focused headless coverage for shortcut routing, active-page search,
  assistive copy, visible-focus styling, and expandable shell chrome. This
  checkpoint changes product navigation and presentation only; it does not
  claim a new asset writer or runtime game proof. No GUI or emulator was
  launched for the source-and-documentation checkpoint.
- Removed workstation-specific home, mount, workspace, and game-dump paths
  from the public changelog and nine reviewed visual catalogs. Those catalog
  fields now use stable relative provenance labels; selectors, allocations,
  resource hashes, and writer meaning are unchanged. The release gate now
  refuses either known private workstation prefix anywhere in staged UTF-8
  text while continuing to allow unrelated portable absolute-path examples.

## v1.0 RC9 Batch Audio Authoring Checkpoint — 2026-07-19

- Added **Export replacement template** and **Import replacement pack** to the
  Audio workspace for all **153 currently Editable standalone cues**: 152
  fixed-AUDO slots plus Menu Back. The folder/ZIP template contains only a
  canonical JSON manifest, editing guide, and empty `replacements/` directory;
  it exports **zero retail WAVs**.
- Each manifest row gives the stable asset ID, declared filename, writer route,
  and exact PCM16 channel count, sample rate, frame count, and no-metadata
  requirement. Modders add only their authored WAVs at the declared paths;
  missing paths are skipped.
- Import validates the complete manifest/source/current-project baseline,
  duplicate and unknown paths, every supplied WAV, and every exact cue contract
  before staging. All true changes commit as **one Undo action**. An invalid,
  stale, duplicate, unknown, or unchanged-only pack leaves the project exactly
  as it was, and a commit failure restores every touched cue. Batch Undo uses
  the same all-cues transaction: a failure restores every current WAV and the
  session manifest, keeps the Undo action available, and can be retried.
- The project boundary compares decoded PCM against every one of the 850
  standalone source cues, not merely the selected target. Moving cue A's
  source WAV into a same-shaped cue B path is refused at Replace, batch import,
  project save, and project load. Decoded streaming ranges already present in
  the user's private cache are source-verified and covered by the same rule.
- The batch route deliberately rejects streaming soundtrack, commentary,
  stadium, and presentation banks/ranges. Those remain browse/play/export-only
  until cue ownership, loop/mixer semantics, and reversible bank repacking are
  decoded. Per-cue Replace/Revert and replacement-only `.2k5mod` save/build
  remain unchanged.
- Added an output-drive free-space preflight before private build staging.
  A 2K5 build now refuses before creating any temporary file unless the
  selected filesystem can hold one complete XISO plus a 512 MiB safety margin.
  The error reports available space, required space, and the exact shortfall in
  GiB, then tells the modder to free space or choose another drive. The source
  and output stay untouched on refusal. Focused cross-title build-safety tests
  pass **32/32**.
- Closed the batch transaction and retail-sharing boundary under adversarial
  review. Same-contract cross-cue source PCM is refused during Replace, batch
  import, project save, and project load; verified source streaming PCM already
  in the private cache is covered too. Injected second-item failures during
  validation, commit, and Undo preserve the complete session tree, leave no
  hidden `.audio-pack-*` or `.audio-undo-*` files, retain the Undo ledger, and
  can be retried. Template publication and contract reads are descriptor-pinned,
  no-replace, hardlink-refusing, and maximum-plus-one bounded. Import captures
  the exact pre-edit snapshot first, validates that same snapshot against the
  exported baseline, and retains it as Undo state; an injected same-shape
  mutation during snapshot capture is refused before commit. The final
  eight-module dependent gate passes **99/99**; an independent rerun passes
  **93/93** relevant tests plus **16/16** standalone-audio tests.
- RC9 was the headless-tested package for this audio checkpoint; sealed RC8
  remained its previous immutable checkpoint. The exact 136-file stage and
  independent extraction pass release → runtime → release with no retail data,
  private inventory, links, or undeclared files. Packaged docs remain self-hash-free;
  the adjacent `.sha256` sidecar authenticates the portable archive. No GUI or
  emulator was launched while assembling or checking RC9.

## v1.0 RC8 Complete Team Kit Checkpoint — 2026-07-18

- Added **Complete Team Kit** directly to **Uniforms & Equipment**. A modder can
  export any highlighted physical uniform set, or resolve the selected team's
  HOME, AWAY, or paired HOME + AWAY style/variant, as either an editable folder
  or deterministic ZIP.
- Every exported physical set contains all **39 supported components**:
  torso/jersey, sleeve, pants, both live helmet families, jersey/helmet/arm
  digits 0–9, the vertical nameplate atlas, and all three independent Team
  Select cards. Each folder includes exact dimensions, stable labels,
  ownership notes, practical UV limitations, and `EDITING-GUIDE.md`.
- Team Kit import validates the source identity, unchanged manifest/guide,
  complete set inventory, current working baseline, every declared path, every
  PNG, exact dimensions, and decoded RGBA pixels before staging anything. It
  stages only real pixel changes as **one Undo action**; unchanged imports add
  no replacement and no Undo entry. A commit failure restores the prior
  project state.
- The bundle is intentionally source-bound. If the active source or any
  exported working pixels change after export, the modder must export a fresh
  kit. This refuses stale hand-offs instead of overwriting newer edits.
- Team Kit folders/ZIPs are private working exports and may reproduce retail
  artwork from the user's own disc. They must not be distributed. The existing
  `.2k5mod` route remains the shareable format and stores only authored,
  pixel-changed replacements plus logical metadata.
- Per-component Export/Replace/Revert remains intact for small changes. A
  successful Team Kit import enters the same modified badges, autosave,
  project, Revert, Build, and independent output-publication flow as individual
  edits.
- RC8's public allowlist and source-free runtime closure now include the Team
  Kit service explicitly. No retail template, private bundle, source XISO,
  original PNG, or generated preview is packaged.
- The focused Team Kit/session/facade/packaging selection passes **47/47
  tests**, and the complete current cross-title headless suite passes
  **489/489**. This checkpoint was assembled headlessly; no visible GUI or
  emulator was launched and the user's desktop was not touched. Exact release
  counts, archive hash, and extraction-parity receipt are recorded in
  `STATUS.md` and the archive's adjacent checksum sidecar after sealing.
- Post-seal Spark Hands QA passed on isolated `DISPLAY=:99`. A fresh
  `v1.0 RC8 • Xbox Edition` window loaded the recognized XISO and visibly
  presented the 39-component **Complete Team Kit**, paired `HOME + AWAY`
  scope, editable-folder selector, Import/Export actions, private-retail-art
  warning, and unobstructed footer. No clipping, overlap, spacing, padding, or
  alignment defect was found, and the user's active desktop/pointer was never
  used.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC8-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC8-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC8-20260718.tar.gz.sha256`
- Archive size: **9,667,067 bytes**
- SHA-256:
  `17254d4030806e8636c67a9b90cfcee88a7711484d9ab6ef079aba875e569466`
- The stage and independent clean extraction each contain **135 files**, **14
  directories including the root**, **101,871,957 file bytes**, **36
  executables**, and zero links or special files. The tar has **149 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates.
  Runtime closure is **37 product + 22 tool modules**, **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**. The extraction is byte- and
  mode-identical with normalized inventory SHA-256
  `df710e64f5e7f441dfa51908a161425478c0b1c9b210a3b06cc50f0ae924df10`.
- RC7 and RC6 were reverified after sealing RC8 and remain immutable at
  SHA-256 `a4785f363505b3f66e2cb3b16ad04ce48b8194b421308670ac4437bce327f13f`
  and `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`,
  respectively.

## v1.0 RC7 Audio Review Checkpoint — 2026-07-18

- Added a dedicated **Review selected** workspace for the session Audio
  Shortlist. It shows only the curated playable sounds, supports Play/Stop,
  remove, and **Move up / Move down**, and returns to the exact browser scope,
  family, status, search, page, and selected row through **Back to browser**.
  Reordering changes the exported sequence but remains session-only: it does
  not dirty a project, enter Undo/recovery, or affect Build.
- Every multi-WAV Audio collection now includes an ordered `playlist.m3u8`.
  Its relative entries match the exact ZIP member order, so shortlist order is
  immediately playable in ordinary media software. `manifest.json` records
  the playlist path and WAV-record count. Raw-only collections deliberately
  omit a playlist and declare `playlist: null` / `playlist_record_count: 0`.
- Added **Raw Bank Containers** as a fourth Audio scope. It exposes the exact
  nine universal-index containers—three `BANK`, three `ABNK`, and three
  `WBNK`—with search, paging, metadata, and byte-exact local `.bin` export.
  These rows are truthfully Export-only: they cannot Play, Replace, Revert, or
  join the playable shortlist, and they never enter projects, recovery, Undo,
  modified state, or Build. The scope fails closed if the exact nine-row
  inventory is incomplete.
- RC7 changes only local review/export ergonomics. It does not claim decoded
  cue ownership or safe writeback for streamed or raw bank audio.
- The focused RC7 Audio/packaging selection passes **42/42 tests**; the complete
  current cross-title headless suite passes **475/475**. The clean stage passed
  release, runtime closure, source-free registry, desktop-entry, launcher
  syntax, and post-runtime release gates before publication.
- The required new-layout visual inspection remains a separate root-session
  Spark Hands gate; no GUI or emulator was launched while assembling this
  source and package checkpoint. The exact archive receipt is recorded in
  `STATUS.md` and the archive's adjacent checksum sidecar.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC7-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC7-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC7-20260718.tar.gz.sha256`
- Archive size: **9,658,588 bytes**
- SHA-256:
  `a4785f363505b3f66e2cb3b16ad04ce48b8194b421308670ac4437bce327f13f`
- The stage and independent clean extraction each contain **134 files**, **14
  directories including the root**, **101,801,912 file bytes**, **36
  executables**, and zero links or special files. The tar has **148 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates;
  runtime closure remains **36 product + 22 tool modules**, **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**. The extraction is byte- and
  mode-identical with normalized inventory SHA-256
  `e80313e49d9acade03e4dc8668eb4dda0059f6fd3e47320d0f8104e832917031`.
- RC6 was reverified after sealing RC7 and remains immutable at SHA-256
  `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`.

## v1.0 RC6 Audio Shortlist Checkpoint — 2026-07-18

- Added a session-only **Audio Shortlist** for hand-picking standalone AUDO
  sounds and playable streaming ranges across unrelated searches, pages,
  families, and scopes. Selected rows carry a visible `★ Selected` status and
  an ordered **Selected _n_ / 256** count.
- Added **Add/Remove selected sound**, atomic **Add this page**, **Clear**, and
  **Export selected WAVs** actions. Complete streaming banks are deliberately
  excluded because a bank is not one playable cue; its indexed ranges remain
  selectable.
- The exact selected-ID exporter is independent of current browser filters and
  mixes original standalone WAVs, staged replacement WAVs, and decoded
  streaming-range WAVs in selection order. The existing transactional bundle
  manifest records `retail_derived` versus `user_replacement` origin.
- The shortlist survives normal refresh, search/filter/page/scope changes, and
  project loads for the same source. Only a successful new-XISO load clears it.
  It never enters `.2k5mod`, recovery, Undo, modified state, or Build.
- Invalid empty, duplicate, unknown, complete-bank, or over-256 selections fail
  before output. Existing destinations remain untouched, and a failed decode
  still leaves no partial ZIP.
- The focused Audio backend/offscreen-Qt selection passes **18/18 tests**. The
  complete current cross-title desktop-tool suite passes **443/443** with
  `PYTHONDONTWRITEBYTECODE=1` and `QT_QPA_PLATFORM=offscreen`.
- Spark Hands inspected the RC6 Audio workspace on isolated `DISPLAY=:99`. The
  Soundtrack, matching-export, shortlist Add/Remove, Add-page, count, Clear,
  and Export-selected controls are readable and unclipped; the browser/detail
  layout remains usable without touching the user's desktop or mouse.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC6-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC6-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC6-20260718.tar.gz.sha256`
- Archive size: **9,643,071 bytes**
- SHA-256:
  `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`
- The stage and independent extraction each contain **134 files**, **14
  directories including the root**, **101,773,880 file bytes**, **36
  executables**, and zero links or special files. The tar has **148 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates.
  Runtime closure is **36 product + 22 tool modules**, **60 registry
  capabilities**, **11 sections**, and **30 NFL 2K5 capabilities**; extraction
  is byte- and mode-identical.
- RC5 remains immutable. Its sealed SHA-256 is
  `1e8304dd189cd7868c39d03eee6b6d77c04e02e22621ba582c635ec1e3e3d441`,
  and its complete receipt is preserved immediately below.

## v1.0 RC5 Active Project Checkpoint — 2026-07-18

- Added normal document-style project identity: an opened or first-saved
  `.2k5mod` becomes the active project, its name appears in the window title,
  and an asterisk marks changes since the last successful named save/load.
- **Save** / **Ctrl+S** now updates the active project directly. **File → Save
  Project As…** / **Ctrl+Shift+S** owns first-time naming and separately named
  copies. Recovered edit sets remain visibly **Untitled** until named.
- Protected fast-save with an in-memory target fingerprint. A missing target,
  symbolic/hard link, path substitution, or external file change fails closed
  with a Save As instruction; the remembered project, live session, and private
  recovery state stay intact.
- Corrected dirty-state semantics so every authored mutation remains unsaved
  even when it reduces the current replacement count to zero. In particular,
  **saved project → Revert All** shows **No edits • unsaved**, keeps Save and
  the close/source/project data-loss gates active, and leaves Build disabled.
- Added an explicit empty-project route for GUI Save/Save As and private
  recovery. The archive contains only `project.json`, an empty edit list, and
  the existing `user-replacements-only` policy; accidental backend empty saves
  remain rejected by default.
- Added six headless project-document/target-safety tests and extended recovery
  and facade checks. The focused project, recovery, facade, and session
  selection passes 35/35 tests without a visible desktop; the complete current
  desktop-tool suite passes 428/428.
- Spark Hands inspected the clean RC5 candidate on isolated `DISPLAY=:99`.
  **File** visibly exposes **Save Project** (`Ctrl+S`) and **Save Project As…**
  (`Ctrl+Shift+S`); both are correctly disabled in the clean, no-edit state,
  and the complete menu renders without clipped or overlapping text. The check
  did not touch the user's desktop or mouse.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC5-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC5-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC5-20260718.tar.gz.sha256`
- Archive size: **9,639,953 bytes**
- SHA-256:
  `1e8304dd189cd7868c39d03eee6b6d77c04e02e22621ba582c635ec1e3e3d441`
- The tar contains **148 members**. Both the original stage and independent
  clean extraction contain **134 files**, **14 directories including the
  release root** (**13 internal**), **101,750,965 file bytes**, **36 executable
  files**, and **zero links**.
- The original tree and independent clean extraction both passed the
  release/runtime/registry/desktop/bash/post-runtime gates. Runtime closure is
  **36 product + 22 tool modules**; the registry exposes **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**.
- The full desktop-tool suite passes **428/428**. The immutable RC4 checksum
  sidecar was reverified unchanged after the RC5 seal.

## v1.0 RC4 Audio Collections Checkpoint — 2026-07-18

- Added a one-click **Soundtrack & music (136)** view and transactional
  **Export matching audio** for any 1–256 filtered standalone cues, raw banks,
  or indexed streaming ranges. The complete known music view fits the bounded
  route at 136 rows and about 1.22 GiB of decoded PCM before ZIP compression.
- Added a deterministic local-audio manifest with stable catalog IDs, physical
  bank/range coordinates, PCM metadata, payload SHA-256, and explicit
  `user_replacement` versus `retail_derived` origin. The artifact identifies
  itself as local-only and never enters a shareable `.2k5mod` project.
- Bundle creation is all-or-nothing, capped at 256 rows and 2 GiB of payload,
  refuses overwrite/symlink targets, and publishes only after every decode,
  size check, checksum, and manifest entry succeeds. A failed row leaves no
  partial ZIP and does not change edits, Undo, recovery, or Build state.
- Added the **Modified** filter for instant review of staged standalone WAVs.
  Streaming banks/ranges correctly return no Modified rows because their
  replacement route remains disabled.
- Spark Hands checked the final Audio layout on isolated `DISPLAY=:99`. It
  caught Qt consuming the first ampersand as a mnemonic marker; the button now
  visibly reads **Soundtrack & music (136)**, and both filter/action rows,
  browser table, and detail pane remain unclipped.
- The complete cross-title product gate passes 419/419 tests. RC4 is a new
  immutable checkpoint; RC2, RC3, and their checksums remain unchanged.

### Release receipt

- Portable archive: `2K5-Mod-Studio-v1.0-RC4-20260718.tar.gz`
- Size: `9,645,491` bytes
- SHA-256: `acde381520b8b0efb26266977f5e4d657fb478ce91299ce9cd152f03d36b2e22`
- The exact 134-file stage contains `101,736,199` file bytes. Its 36-product /
  22-tool-module runtime closure, 60-row registry, 11 product sections, and
  source-free desktop construction checks passed before archiving and again
  after clean extraction.
- The adjacent `.sha256` sidecar is the authoritative archive checksum.

## v1.0 RC3 Product Checkpoint — 2026-07-18

- Packaged the working-tree advances that followed RC2: complete indexed AUSB
  range browsing/playback/export, dedicated Gameplay and Menus inspectors,
  source-bound autosave/recovery, recent files, and shared Save/Discard/Cancel
  data-loss gates.
- Polished the Audio workspace so all three scopes remain readable at normal
  desktop size. Standalone sounds retain their truthful edit controls; complete
  banks and indexed ranges now use visibly disabled Replace/Revert controls,
  concise ownership summaries, and full technical tooltips.
- Corrected alternating-row colors in the Gameplay and Menus tables, preserved
  literal ampersands in tab labels, and tightened local status copy so no table
  presents a white or misleadingly writable row.
- Added the APF digital-font provider to the exact clean-release closure. This
  fixes a real clean-stage import failure while keeping the 2K5 application
  package source-free and retail-free.
- Ran four current-code visual checks through Spark Hands on the isolated
  `DISPLAY=:99`: recovery/recent files, every Audio scope, the complete
  Gameplay inspector, and both Menus inspector modes. All controls, disabled
  states, tables, tooltips, and status labels rendered without clipping or
  overlap; the isolated QA window and synthetic recovery fixture were removed.
- Passed 404/404 desktop-tool tests headlessly, including both title backends,
  before assembling the non-overwriting RC3 release tree and archive. The
  archive is `2K5-Mod-Studio-v1.0-RC3-20260718.tar.gz` (**9,635,511
  bytes**) with SHA-256
  `69b79986903152102093632c60c3f6ba177dd3c9dd5d615e8f18d9c4e025c548`;
  its adjacent `.sha256` sidecar carries the same checksum.

## Post-RC3 Audio Review — 2026-07-18

- Added a **Modified** Audio status filter so a modder can isolate every staged
  standalone WAV among the 850 indexed cues, then inspect or Revert it without
  paging through untouched sounds. Streaming banks/ranges truthfully return no
  Modified rows because their replacement controls remain disabled.

## Post-RC3 Audio Collections — 2026-07-18

- Added a one-click **Soundtrack & music** view for all 136 exact music ranges
  and a bounded **Export matching audio** action for any 1–256 filtered rows.
  The action packages current standalone WAVs, complete raw banks, or verified
  WAV/raw ranges in one manifest-backed ZIP instead of requiring one export per
  table row.
- Collection export is all-or-nothing, refuses an existing or linked target,
  caps both row count and predicted payload bytes, and publishes the ZIP only
  after every payload and checksum succeeds. A failed decode leaves no partial
  result.
- The manifest distinguishes staged `user_replacement` WAVs from
  `retail_derived` audio. Collection exports remain local-only and structurally
  separate from shareable `.2k5mod` projects, project mutations, Undo, recovery,
  and Build.

## Workspace Recovery and Recent Files — 2026-07-18

- Added immediate background autosave after every connected visual, text,
  roster, Crib, audio, Stadium, Undo, and Revert workflow. Autosave delegates
  to the normal validated `.2k5mod` writer, so it contains user-authored
  replacements and logical metadata only—never source or original game bytes.
- Bound every recovery snapshot to the active source SHA-256 while holding the
  facade session lock. A source switch cannot relabel one game's edit set as
  another game's recovery, and recovery refuses a source-identity mismatch.
- Added a startup recovery choice plus **File → Recover Unsaved Edits**. A
  missing/moved source produces an exact path instruction and keeps the
  replacement-only recovery archive rather than guessing at another dump.
- Added **Save Project / Discard Edits / Cancel** gates before source switches,
  project replacement, and app close. Cancelling or a failed load retains both
  the current session and its recovery snapshot.
- Added private, atomic recent-file state for the last eight XISOs and eight
  named projects, surfaced through File-menu submenus. Recent paths never enter
  shareable projects.
- Added seven focused headless recovery/state/connectivity tests and expanded
  the release allowlist so the recovery module cannot be omitted from the next
  package. The selected 50-test recovery/facade/session/UI-model/packaging
  regression passed without launching a GUI or touching a display.

## Current-Tree Source-Free Preflight — 2026-07-18

- Replaced the stale streaming-audio research boundary with the complete
  registry instruction: “Recover external music/commentary cue identities and
  directories, loop points, gain, pan, priority, runtime routing, and
  reversible rebuild rules before any bank writer.” A focused test requires
  this exact instruction once and refuses the former wording.
- Added the recovery-state module to the clean-stage runtime closure and
  exercised recent-source metadata, source-SHA binding, recovery discovery,
  retail-payload exclusion, and cleanup using synthetic files only.
- Extended the same closure receipt across current all-range Audio coverage and
  the dedicated Gameplay and Menus inspectors. The passing receipt covers 35
  product modules, 22 tool modules, 850 standalone sounds, 17 streaming-bank
  descriptors, and all 53,571 indexed streaming ranges without a display.
- Fixed a preflight defect found by the post-runtime retail scan: module imports
  could leave undeclared `__pycache__` files in an otherwise clean stage. The
  checker now disables bytecode publication before any product/tool import.
- Rebuilt a fresh disposable allowlist-only stage and passed the release gate,
  runtime closure, 60-row source-free registry validation, desktop-entry
  validation, launcher syntax, and the post-runtime release gate. The stage had
  132 files, 13 directories, 101,659,703 bytes, no private inventory, and zero
  retail payloads; its totals stayed identical after runtime probing.
- Passed 317/317 nonvisual 2K5 tests (295 product plus 22 NFL/shared-provider
  integrity cases) and preserved the exact 43-validator plan. GUI/visual QA and
  RC3 packaging remain root-owned follow-up work; neither was performed here.

## Gameplay and Menus Inspector Pass — 2026-07-18

- Replaced the static **Sliders & Gameplay** findings page with a dedicated
  read-only product inspector: all 21 named slider rows, the stock range, all
  17 CPU **Fantasy Draft** position weights, eight observed save containers,
  the save/signature boundary, and five bounded franchise findings are now
  directly browsable.
- Kept the proof boundary in the controls themselves. Fixture slider values are
  labeled as research observations rather than the user's profile; Fantasy
  Draft is not called Franchise Draft; and no preset, executable patch, save
  writer, or out-of-range control is offered.
- Added a specialized **Menus & UI** inspector for the named NFL Main Menu:
  seven initialized rows/transitions, two owned layout relationships, rendering
  boundaries, initial selection, and all three remaining blockers are visible.
- Preserved the existing complete archive-resource browser as **All Raw
  Resources** inside the Menus workspace, and kept the registry capability
  cards/limitations available in both specialized inspectors.
- Added non-overwriting, sanitized JSON and spreadsheet-ready CSV export routes
  in the flagship facade for both inspectors. These reports contain named
  evidence and status metadata, never retail executables, saves, or archive
  bodies.
- Added two small, hash-pinned product snapshots so the inspectors remain
  runnable when private research reports are correctly absent from a release.
  The snapshots contain named metadata only, are covered by the exact
  reviewed-metadata allowlist, and are checked against the proved core outputs
  when the development evidence set is present.
- Added fail-closed model validation for the exact 21/17/seven-row contracts
  plus focused facade and offscreen flagship connectivity tests. All **51**
  selected inspector, facade, existing gameplay/menu core, Qt model, and
  release-manifest tests passed without launching or visually inspecting a GUI
  and without building a package.
- Corrected product documentation to match the current layout: Rosters &
  Players presently owns portrait/live-face textures, while the Current and
  Historical roster forms still share the **Text & Team Identity** workspace.

## Continuous Audio Coverage Pass — 2026-07-18

- Split the Audio tab into **Standalone sounds (850)**, **Streaming banks
  (17)**, and **Indexed streaming ranges (53,571)** so soundtrack, commentary,
  stadium/PA/coach, broadcast, and ambient audio are visible in the dedicated
  editor rather than only as opaque rows in the archive-resource fallback.
- Added exact private-source parsing for all 17 NFL 2K5 `AUSB` descriptors,
  their 16 external `.bin` owners, and all 53,571 indexed ranges.
  The duplicate `cwdloop` descriptors visibly report their shared owner.
- Added searchable family and status filters plus explicit container, ownership,
  export-format, and replacement-status labels. Standalone audio exports as a
  playable WAV; streaming banks retain exact raw `.bin` export, and every
  individual range now supports both its raw `.bin` and decoded PCM16 WAV.
- Completed the main-facade paging contract used by the Audio panel, including
  stable first/last result numbers for cue, bank, and range pages.
- Proved the bank payload codec as Xbox IMA ADPCM: all 53,571 ranges are whole
  descriptor-channel block groups, and a complete 2,183,326,092-byte scan found
  60,647,947 valid physical channel-block headers with zero invalid step indices.
- Added private Play/Stop and PCM16 WAV export for all indexed ranges. Complete
  banks remain raw-only because they contain many cues. Replacement remains
  disabled because cue names, loops/durations, mixer rules, and reversible
  repacking are still unresolved. Raw and decoded retail audio remain local and
  are structurally excluded from shareable `.2k5mod` projects.
- Made the original bounded **Menu Back** replacement route explicit in the
  selected-cue instructions while preserving all 152 additional exact-shape
  standalone writers and 697 alias-safe Export-only rows.
- Live private-cache indexing returned 850 standalone cues, 153 Editable rows,
  17 streaming descriptors, 16 external owners, and 53,571 ranges with the
  source opened read-only. Focused retail-free catalog and panel backend tests
  cover raw-bank and exact-range discovery/export, decoded range playback paths,
  cache-tamper/failed-decode cleanup, search/filter behavior, WAV replacement,
  revert, and overwrite refusal.
- Exercised the largest real range end to end: 8,954,064 encoded bytes became a
  31,836,716-byte stereo WAV in 1.018681 seconds. Python 3.12 uses an optional
  standard-library accelerated path; an explicit test proves the exact fallback
  used when that module is absent.

## v1.0 RC2 UX Refresh — 2026-07-18

- Tightened the desktop shell so more useful content fits without crowding:
  the sidebar, header, footer, browser columns, panels, cards, and preview
  minimums now use one compact spacing rhythm.
- Normalized typography and control sizing around Noto Sans, 34-pixel form
  controls, and 40-pixel primary build/launch actions, with stronger contrast
  and explicit disabled states.
- Made **Build Modded XISO** the clear primary action and renamed the quieter
  emulator action **Launch Latest Build** so the normal workflow reads in the
  order a modder actually uses it.
- Added clear buttons, accessible names, and practical tooltips to search and
  filter controls across the asset browsers. Stadium labels and other internal
  status copy now use modder-facing language.
- Re-ran the complete non-visual 2K5 product suite after the UX refresh: 312
  headless tests passed with no failures, errors, or skips. The release/runtime
  gates are recorded in the release status alongside the final archive hash.
- Published the non-overwriting RC2 runnable tree as
  `2K5-Mod-Studio-v1.0-RC2-20260718/` and portable archive as
  `2K5-Mod-Studio-v1.0-RC2-20260718.tar.gz`. The archive is
  **9,575,103 bytes** with SHA-256
  `6df15767ff766d7eb2b7b87634d79dee495102c74db323067eedc01f796193d7`.
- Independently extracted that archive and reran its retail-free gate,
  runtime-closure probe, desktop-entry validator, launcher syntax check, and
  post-runtime retail-free gate. All passed; the archive contains 126 regular
  allowlisted files, 14 directories, no symlinks or hardlinks, no private
  inventory, and zero retail payloads.

## v1.0 Release Candidate — 2026-07-18

### Product shell and universal coverage

- Completed all 11 sidebar tabs: Uniforms & Equipment, Rosters & Players, Team
  Identity, Field Art & Create-Team Art, Stadiums, Scorebug & Presentation,
  Menus & UI, The Crib, Audio, Sliders & Gameplay, and Playbooks & Plays.
- Connected all 30 NFL 2K5 capability cards to the 60-row cross-title registry.
  Card status renders as **Editable**, **Preview/Export-only**, or **Coming
  Soon** from shared registry state; concrete editor actions remain explicitly
  wired per specialized workflow.
- Kept the archive-resource browser as the fallback home for every resource in
  that index that does not yet have a specialized editor. Raw fallback rows are
  honestly Export-only rather than inheriting a capability status they cannot
  perform.
- Indexed 32,038 specialized visual assets with searchable category browsers,
  previews/thumbnails where supported, stable asset IDs, Export, Modified
  badges, Replace for writable classes, and per-asset Revert.
- Extended the shared session across visual, text, roster, audio, Crib, and
  Stadium edits, including Undo, Revert All, modified counts, and retail-free
  `.2k5mod` project save/load.

### Uniforms, rosters, text, and presentation

- Shipped the complete proved Uniforms & Equipment workflow for jerseys/torsos,
  sleeves, pants, live helmets, digits/nameplates, and separate Team Select
  cards.
- Shipped bounded portrait, live-face, create-team field-art,
  scorebug/presentation, team-identity, player-name, and jersey-number editing.
- Added a dedicated **Current Roster Players** browser/editor inside the shared
  **Text & Team Identity** workspace. Every current player number has a
  searchable row with current/original name and number, status filtering,
  Apply, Revert, and number Export. Primary proved rows are Editable;
  secondary-pool rows remain visibly Preview/Export-only. Rosters & Players
  currently remains the portrait/live-face texture workspace.
- Added Historical Teams coverage for all 75 historical ROST resources and
  3,975 historical players.
- Proved that the current and historical player views cover all 6,522
  jersey-number assets exactly once; no current number is left accessible only
  through an internal catalog.
- Added universal text search across 716 banks and 23,346 strings. Exactly
  20,074 fixed-allocation strings are Editable; the other 3,272 remain
  read-only with a reason.
- Made all four display fields for each ESPN 25th Anniversary moment editable:
  title, historical description, challenge objective, and date. Team selectors,
  scenario state, and unlock conditions remain outside the text writer.

### Stadium Studio and The Crib

- Added Stadium Studio for all 477 indexed scenes, with private lazy glTF/PNG
  derivation, resumable generation, orbit/pan/zoom, surface highlighting, and
  material/texture ownership selection.
- Connected Export/Replace/Revert/project/build for all 23,838 indexed
  fixed-allocation P8 texture occurrences. Multiple edits to one SCNE compose in
  one rebuild instead of overwriting one another.
- Preserved existing Stadium geometry, UVs, materials, collision, archive
  extents, and fixed SCNE allocation. Images that cannot fit the original
  compressed slot fail closed with a modder-facing message.
- Added The Crib browser for all 498 inventoried assets. All 128 Team Photos and
  the exact `room:22 / bar_monitor` screen are Editable, for 129 Editable rows;
  the other 369 are Preview/Export-only.

### Audio, gameplay status, and playbooks

- Added browse/preview/export for all 850 standalone AUDO resources.
- Enabled fixed-contract WAV replacement for 153 resources: the existing
  menu-back cue plus 152 uniquely owned standalone slots. The other 697 remain
  Export-only because duplicate-name/content aliases make runtime cue ownership
  ambiguous.
- Added exact per-row PCM16 validation for channel count, sample rate, frame
  count, and WAV chunk layout. An invalid WAV leaves the project unchanged.
- Corrected the known 17-position Draft table's product label to **Fantasy
  Draft**, not Franchise rookie draft. Private Catching and Fantasy Draft patch
  transports remain experiments and do not appear as finished presets without
  a causal runtime A/B.
- Added the dedicated read-only Gameplay inspector and named Main Menu
  transition inspector described above, including sanitized JSON/CSV export and
  retained capability/limitation views. Neither inspector claims writeback.
- Added the mandated Playbooks & Plays fallback as a structured viewer for 37
  books, 1,533 formations, 9,251 plays, 32,502 assignment chains, 91,833 nodes,
  and 101,761 player-slot references. Selected raw PLAY resources can be
  exported; route drawing/import stays Coming Soon with its findings note.

### Build, rollback, and release safety

- The source XISO is always opened read-only and cannot be selected as a build
  destination.
- Every staged replacement retains a private original for per-asset Revert;
  Undo and Revert All operate across the full project.
- Builds use a temporary output and exclusive final creation. A failed build
  cannot leave a partial/corrupted requested output.
- Shareable `.2k5mod` projects carry only user-authored replacements and logical
  metadata. They do not contain source resource payloads, private originals, or
  compiled XISO spans.
- The clean release-candidate package stage passed with **126 allowlisted
  files**, **101,447,213 bytes**, and **zero retail game bytes/private source
  inventory**.

### v1.0 composed smoke

- One product-flow project staged 19 Tier 1 edits and built them into a new
  XISO. The output changed 1,027,710 bytes and has SHA-256
  `70cd2bc0acc57d358d800cd6c0952c1c89c1c09ee9039d9513e435c58dffa0a6`.
- The source remained read-only and retained SHA-256
  `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`
  before and after the build.
- Headless Spark inspected xemu only on private Xvfb display `:99`. It saw the
  ESPN splash, stable attract sequence, and a clean NFL 2K5 title /
  **Press START** screen with no visible corruption.
- This was a boot-level spot check. The release does not claim that every edited
  asset was individually visited or judged in gameplay. A later isolated
  software-rendered harness retry logged a PFIFO assertion during or after the
  close attempt, so no clean long-duration gameplay claim is attached to it.

### Known limits in v1.0

- The 3,272 non-writable text entries stay visible and read-only because they
  have zero text capacity, selector semantics, or an unproved write contract.
- Secondary roster pools are browsable/exportable. Position codes/labels and
  selected ownership metadata are already decoded in research but are not yet
  surfaced in the product form; ratings, membership, depth charts, and unsafe
  secondary-pool writeback remain Coming Soon.
- Stadium texture editing does not imply arbitrary model import. General
  Stadium/Crib geometry serialization, transforms, collision, and relocation
  remain outside v1.0.
- Only the proved Crib `bar_monitor` electronics surface is writable; the other
  24 electronics-like rows remain export-only pending one-at-a-time ownership
  and fixed-span proof.
- The 697 alias-ambiguous AUDO rows are not routed through the unique-slot
  writer. Complete non-AUDO banks remain raw-only multi-cue containers; their
  53,571 individual ranges are playable/WAV-exportable, but are not writable.
- Catch-strength presets require matched drop-rate sampling. The known Draft
  weights require a Fantasy Draft runtime A/B and do not address the separate
  Franchise rookie-draft scorer.
- Route authoring remains blocked by undecoded coordinates, opcodes, player
  roles, custom-save ownership, and inverse compilation. The read-only PLAY
  inspector ships instead.
- ESPN 25th moment text is editable, while scenario fields and unlock logic
  remain findings-backed Coming Soon.
- xemu is the supported target. Original Xbox hardware is untested.

## Phase 1 Alpha — 2026-07-17

- Shipped the polished Linux desktop shell, source-XISO load/index flow,
  in-app Getting Started page, and searchable Uniforms & Equipment browser.
- Added PNG previews, drag-and-drop replacement, per-asset Revert, Undo, Revert
  All, and modified badges.
- Added end-to-end build of a separate modded XISO and xemu launch detection.
- Added shareable retail-free project files and private original storage.
- Added universal raw inventory browsing so every indexed resource had a
  visible home before specialized v1.0 editors were completed.
- Confirmed the Detroit torso smoke build reached the normal NFL 2K5 title
  screen in xemu.

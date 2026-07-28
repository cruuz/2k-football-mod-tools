# APF 2K8 Mod Studio Changelog

## 0.1.0-alpha.45 — no APF change 2026-07-28

- Version parity only. No APF behaviour changed.

## 0.1.0-alpha.44 — no APF change 2026-07-28

- Version parity only. No APF behaviour changed.

## 0.1.0-alpha.43 — no APF change 2026-07-28

- Version parity only. The 2K5 side fixed a stale on-screen version and three
  capabilities its Uniforms page never rendered; APF behaviour is unchanged.

## 0.1.0-alpha.42 — the PNG importer accepts real PNGs 2026-07-28

- The shared PNG importer demanded colour type 6 at bit depth 8, non-interlaced,
  and refused everything else. Every standard colour type and bit depth is now
  decoded and widened to RGBA internally.

## 0.1.0-alpha.41 — shared registry row count 2026-07-28

- No APF behaviour changed. The shared capability registry gained NFL 2K5's
  general texture lane, so the APF runtime gate's shared row count moved from
  66 to 67. APF's own 34 capabilities are unchanged.

## 0.1.0-alpha.40 — the game partition is found, not guessed 2026-07-28

- **A legally dumped disc could be refused with "does not appear to be a valid
  xbox iso image."** The bundled `extract-xiso` probes exactly four partition
  offsets -- `0`, `0x0FD90000`, `0x02080000`, `0x18300000` -- and rejects the
  image when none of them carries the XDVDFS magic. That is the same defect the
  2K5 source lane was fixed for, hidden inside a vendored binary: a layout
  measured on one machine treated as the only legal layout.
- The disc is now read with the project's own XDVDFS reader first, which
  *searches* sector-aligned positions for the magic and confirms a candidate by
  requiring it at both ends of the header sector plus a root directory that
  fits inside the image. `extract-xiso` remains a fallback, so no layout that
  loaded before can stop loading.
- **A disc for another console is now named instead of called invalid.** The
  report that prompted this was the PlayStation 3 release of the same game,
  named `.iso`; the old message reads as a bad dump, so the reporter re-dumped a
  disc that was fine. ISO 9660 volumes, PS3 discs, STFS packages and ZIP/RAR/7z
  archives are identified by structure and reported by name.
- Only the six files the editor reads are extracted, so the supported USA dump
  now resolves in about 26 seconds and 3.9 GB instead of unpacking the whole
  7.8 GB disc.
- The bundled extractor is no longer resolved before any image is examined, so
  an installation missing it can still open a disc the native reader handles.
- The private extraction cache is published through `platform_compat` rather
  than `os.replace` on a directory -- the POSIX-only idiom behind the RC36
  Windows folder-export failure, in a second place.
- No capability, writer contract or identity ledger changed. The per-file
  ledger (0A/0B/1A/1B and default.xex, by exact size and hash) is still the
  identity check, and all six files come out byte-identical to it.

## 0.1.0-alpha.39 — a disc image is identified by its contents 2026-07-27

- Selecting an APF disc image no longer requires the whole container to hash to
  the project's own rip. The per-file ledger (0A/0B/1A/1B and default.xex, by
  exact size and hash) already ran immediately afterwards and is the stronger
  check; the container gate simply refused legal dumps before it could. The
  container hash is still recorded and still keys the extraction cache.
- No capability, pin or writer contract changed.

## 0.1.0-alpha.38 — generated text is LF on every platform 2026-07-27

- Every shipped module now pins the line ending when it writes text. Text mode
  on Windows rewrites `\n` as `\r\n`, so any file this product generates and
  later hashes or size-checks could not match there. 38 call sites across 29
  files; the shipped surface is at zero unguarded text writes and a test holds
  it there.
- The failure that exposed this was on the 2K5 side, but the defect was
  repo-wide, so the APF writers and reports are covered by the same sweep.
- No capability, pin or writer contract changed. Binary writes were never
  affected.

## 0.1.0-alpha.37 — sibling imports work on installed Windows copies 2026-07-27

- Fixed `ModuleNotFoundError` from the shipped `tools/*.py` on installed Windows
  copies. Those scripts import each other, and the embeddable CPython the
  installer ships defines `sys.path` from a `._pth` file without adding a
  script's own directory the way every ordinary interpreter does.
  `apf_texture_patch` and `apf_roster` were among those affected. Never
  reproducible from the tarball, from source, or in CI — only after installing.
- Each shipped tool now restores its own directory, and the `._pth` lists
  `app\tools` as a second, independent guard. No capability changed.

## 0.1.0-alpha.36 — failed builds clean up after themselves on Windows 2026-07-27

- Fixed cleanup after a failed write. Every writer unlinked the partial output
  while its descriptor was still open, which is correct on Linux and impossible
  on Windows, where the OS refuses to unlink a file anything still holds open.
  The error was swallowed, so a failed build left a stray file behind and the
  *next* build then refused to overwrite it, for no reason the user could see.
- Found by an outside contributor's test, not ours: every test that reaches this
  path needs retail data no CI runner has. `apf_field_art_patch`,
  `apf_logo_patch` and `apf_texture_patch` were all affected.
- No capability, pin or guarantee changed.

## 0.1.0-alpha.35 — the texture writers run on Windows 2026-07-27

- Fixed the crash that made **every APF texture writer unusable on Windows**.
  Field art, team logos, the logo cache, the generic texture writer and uniform
  mips all failed before doing any work with
  `AttributeError: module 'os' has no attribute 'O_CLOEXEC'`. That flag does not
  exist in CPython on Windows, and four writers passed it to `os.open` as a bare
  attribute instead of `getattr(os, "O_CLOEXEC", 0)` — the form 284 other sites
  in the tree already used. Reported by a user against the ordinary "export and
  replace field endzone" flow.
- **No capability changed and no guarantee was weakened.** The registry stays at
  65 capabilities with every ladder position untouched. The flag falling back to
  `0` on Windows costs nothing: PEP 446 makes every descriptor CPython creates
  non-inheritable on every platform, so close-on-exec is the interpreter's
  guarantee, not this flag's. Descriptor ownership, inode-identity checks and
  fail-closed refusals are byte-for-byte what alpha.34 proved.
- Nothing was ever at risk on the affected machines. The failure landed in the
  output reservation, after the read-only preflight and before any output
  existed, so no file was written at all — the refusal dialog's "the original
  game was not modified" understated it.
- Added `tests/mod_editor/test_shipped_tools_posix_only.py`, which needs **no
  retail data**. Every existing test over these writers is gated on extracted
  retail data no CI runner has, which is exactly how a Windows job could report
  parity with Linux and macOS while never executing one `os.open` inside a
  writer. The new file scans both release allowlists for bare POSIX-only
  `os.open` flags and, with those names deleted from `os`, drives every shipped
  writer's real reservation path — asserting the fail-closed refusal still
  refuses for the right reason. Targets come from the allowlists, so a writer
  added later is covered without editing the test.

## 0.1.0-alpha.34 — project-backed Audio cue labels 2026-07-20

- Added the product contract
  `project_metadata_only_stable_logical_cue_id` for all 47,775 playable APF
  cues: 2,261 standalone AUDO sounds plus 45,514 individual AUSB substreams.
  Each stable logical cue ID can own one user-authored custom title of up to 120
  characters and/or multiline note of up to 2,000 characters. Container-only
  AUSB index and physical-bank rows remain ineligible.
- Added **Your cue label & notes**, **Save label**, **Clear**, immediate
  title/note search, and **Labeled only** to the Audio workspace. Original
  catalog identity remains visible; a custom title changes presentation and
  discovery metadata, never the cue coordinate or replacement target.
- Added deterministic `audio-annotations.json` persistence with exact schema,
  count, size, and SHA-256 binding inside `.apf2k8mod`. Annotation-only projects
  are valid. Labels and notes participate in recovery, project load, Undo,
  Clear, and Revert All without becoming buildable audio edits.
- Kept annotations outside the game-build document and modified-asset count.
  They never add a Modified badge, enable Build by themselves, enter an APF
  archive, or authorize audio replacement. The bounded metadata accepts no
  retail audio, decoded PCM, source path, preimage, rollback byte, or packet.
- Carried the custom title, note, and preserved game/catalog name into bounded
  Audio collection export metadata. Playlist display names prefer the custom
  title while stable cue IDs and payload paths remain unchanged.
- Alpha.34 release hashes, final test counts, clean-stage runtime exercise, and
  sealed-package metrics remain pending until the concurrent core and GUI
  implementation freezes. Alpha.33 remains preserved unchanged.

## 0.1.0-alpha.33 — selected-sound Audio drag and drop 2026-07-20

- Added the product contract
  `selected_exact_slot_xma1_or_pcm16_wav` and a visible **Drop .xma or exact
  PCM16 .wav here** target for every individually editable standalone AUDO and
  AUSB substream row.
- Routed `.xma` drops through the same advanced standalone/AUSB exact-slot
  writers used by **Replace with XMA1…**. Routed `.wav` drops through the same
  configured external-encoder bridge and cancellable validation used by
  **Replace from PCM WAV…**. Buttons and drops therefore share one mutation
  path rather than implementing parallel writers.
- Captured the selected row and export identity before starting background
  work. Every Audio mutation/template control disables immediately at PCM,
  direct-XMA1, or replacement-pack submission and returns only after the product
  runner unregisters that worker. Rejected admission is explained instead of
  silently losing an accepted-looking drop or chooser action; failure,
  cancellation, or a stale/unsupported target stages nothing.
- Limited admission to exactly one local regular non-symlink `.xma` or `.wav`.
  Folders, remote URLs, multiple files, and other extensions are refused. The
  drop target does not bundle an encoder, accept FLAC/MP3, bypass exact-slot or
  source-reuse gates, modify the source, or add retail bytes.
- Alpha.33 carries forward Alpha.32's
  `fully_validated_read_only_preview_then_explicit_apply` batch contract.
  Its final stage, clean extraction, runtime/release/desktop/shell gates,
  deterministic rebuild, complete APF suite, combined cross-title suite, and
  independent review pass. Alpha.32 remains preserved unchanged.

## 0.1.0-alpha.32 — validated Audio pack review candidate 2026-07-20

- Replaced the one-click batch-audio import hand-off with the product contract
  `fully_validated_read_only_preview_then_explicit_apply`. **Review replacement
  folder…** and **Review replacement ZIP…** now validate the complete supplied
  pack before presenting an explicit, default-Cancel Apply decision.
- Added a sanitized preview receipt containing only the selected pack path,
  input/count metadata, and an opaque confirmation token. It reports template
  targets, supplied files, would-change, already-current, missing, current
  modified-audio, resulting modified-audio, and validated counts. It exposes no
  audio bytes, decoded source names, source fingerprint inventory, extracted
  ZIP member path, or authored-member digest.
- Bound Apply to the exact reviewed outcome. The private HMAC confirmation
  covers each supplied member hash, each fully validated packet-result hash,
  manifest/baseline identity, loaded-source hash, a private loaded-session
  nonce, and the current project-audio revision. Apply reopens and revalidates
  the folder or ZIP; changed payloads, changed encoder results, a different
  session, or intervening audio edits refuse atomically and require a new
  review.
- Kept review read-only. Preview-created unreferenced packet cache is discarded;
  Cancel stages nothing and adds no Undo action. An unchanged-only pack is a
  successful review with **Apply** unavailable rather than an import error.
  Confirmed real changes still enter the project as exactly one Undo action.
- Routed the review/Apply continuation through the product worker-idle barrier.
  The barrier retains the continuation while any worker is registered and
  releases it only after the preview worker and audio-import lifecycle signals
  drain, so confirmation cannot race a still-busy runner. Existing source/session
  locks, cooperative encoder cancellation, stale-baseline checks, atomic state
  swap, and last-build invalidation remain in their established owners.
- This release changed no audio template schema, runtime dependency, release
  allowlist, encoder policy, or retail-data boundary. Alpha.32 was sealed after
  its complete APF and cross-title suites, clean stage/extraction gates, and
  deterministic rebuild passed; Alpha.31 remains preserved unchanged.

## 0.1.0-alpha.31 — Add-all-matching and safe Audio teardown 2026-07-20

- Added **Add all matching (N)** to the Audio shortlist. It uses the exact
  applied search/kind/role/source query—or the active Soundtrack album—rather
  than only the current 100-row page. Already selected rows are skipped and
  new rows retain stable game-catalog order.
- Kept the 256-sound shortlist boundary atomic. If all new matches would not
  fit, the button and its accessible description show the required and
  remaining counts; activating it explains the limit and adds nothing. A
  successful add clears the one-level Clear/Undo snapshot as one deliberate
  shortlist mutation. It starts no worker, writes no project, and never copies
  audio bytes.
- Cached one exact matching-row result per applied query/model epoch or
  Soundtrack version. Selecting rows and updating shortlist buttons therefore
  do not repeatedly rescan the complete 47,814-row Audio model; changing the
  query, model, or game invalidates the cache.
- Closed source-switch and application-close teardown around request-owned
  Audio readers. A running preview or waveform request is cancelled, its
  worker is allowed to drain, and only then may the loaded session/cache close
  or a replacement source begin indexing. Rapid source selections coalesce to
  the latest request. A late result cannot touch a closed session.
- Preserved blocking build/export safety and Alpha.30's true FFmpeg/ffprobe
  process-group cancellation. Alpha.31 adds no encoder, source audio, retail
  bytes, private source path, project payload, or desktop interaction.

## 0.1.0-alpha.30 — interruptible Audio preview and waveform decode 2026-07-20

- Changed **Play** to **Cancel preview** while APF is preparing a private WAV.
  A click, selected-row change, source/model change, or page transition now
  signals the exact request-owned cancellation token. The button reports
  **Cancelling…** until that worker drains; cancelled and stale success/error
  results are silent and can never start a player for another row.
- Made cancellation reach the actual decoder rather than only suppressing its
  eventual result. Original AUDO, original AUSB substreams, staged standalone
  replacements, and staged streaming replacements all carry the optional
  callback through facade, session, private asset I/O, and exact-slot tools.
  FFmpeg and ffprobe run as new process-group leaders in this path; Cancel or
  timeout sends TERM, drains briefly, escalates to KILL when required, and
  verifies that detached helpers in the owned group are no longer running.
- Added the same owned cancellation to **Load waveform**. During a decode the
  control becomes **Cancel waveform**; selection changes and explicit Cancel
  stop FFmpeg/ffprobe before the bounded PCM envelope reader runs. Waveform
  loading still never autoplays or writes a project edit.
- Preserved transactional preview publication. Cancellable source exports are
  generated in private temporary folders; staged replacements decode through
  hidden sibling WAVs; the session records a receipt only after complete WAV
  validation. Cancellation removes partial/unreceipted output, while an
  already validated cached preview remains intact.
- Closed the existing task-admission race: if another blocking operation owns
  the worker lane, a rejected Play request immediately releases its request
  token and returns to **Play** instead of remaining stuck on a preparation
  label. Old non-cancellable command-line exports retain their established
  direct `subprocess.run` behavior and signatures remain backward compatible.
- This release adds no encoder, retail audio, private source path, project
  payload, or new runtime dependency. All implementation and automated checks
  were terminal-only and headless; authored-audio audibility still requires a
  controller-driven Xenia A/B with the modder's own encoder and audio.

## 0.1.0-alpha.29 — owned Audio browsing lifecycle 2026-07-20

- Added an applied Audio query token covering the decoded model epoch, search,
  record kind, role, source/bank, and page offset. During the 180 ms typing
  delay, Add-this-page, Previous/Next, matching export, replacement-template
  export, and filtered decoded-row export are disabled and guarded at their
  method boundaries. Publishing the matching table applies the token
  atomically. Typing and erasing back to an already displayed query restores
  the exact page and pagination immediately.
- Kept exact selected-row work available during that delay. Play, individual
  Export, Replace/Revert, and Add/Remove-selected own the visible row identity
  instead of interpreting the pending aggregate filters.
- Changed the session-only Audio shortlist **Clear** action into one-level
  **Clear / Undo**. Up to 256 mixed AUDO/AUSB rows restore in exact insertion
  order. Clearing from Review returns to the browser; Undo does not reopen
  Review. The recovery snapshot expires only after a real shortlist mutation
  or successful model/game change, and it never enters a project or starts a
  worker.
- Bound private preview preparation to `(model epoch, row ID, request
  generation)`. A late success cannot start the previously selected sound, and
  a late failure cannot interrupt the current row with a stale dialog. A
  current preparation failure clears ownership, restores **Play**, and remains
  retryable.
- Confirmed the existing source switch is already transactional: failed loads,
  file-picker cancellation, and unsaved-work cancellation preserve the old
  Audio model, page, selection, shortlist, waveform, and running preview. No
  speculative source-load rewrite was added.
- The focused Audio GUI suite passes 26/26. The complete headless APF suite
  passes 466/466 after the lifecycle and packaged-runtime receipt additions.
  No interactive desktop, emulator, private game source, or retail audio was
  used for this release.

## 0.1.0-alpha.28 — batch PCM16 replacement packs 2026-07-20

- Added a second, metadata-only audio replacement-pack contract:
  `apf2k8_mod_studio_audio_replacement_pack/v2`. Choose **Exact PCM16 WAV**
  before creating a folder or ZIP template; its listed payload paths are
  `pcm16/*.wav`. A template can still describe any filtered set, the
  Soundtrack album, the reviewed shortlist, or all 47,775 editable AUDO/AUSB
  rows. It carries target shape and source/project binding only—never original
  audio, decoded source names, an encoder, preimages, or rollback bytes.
- Added project-atomic batch WAV import through the modder's existing,
  separately configured XMA1 encoder. Every supplied WAV must be one exact
  signed little-endian PCM16 RIFF stream with the target's channel count,
  sample rate, and frame count. Import accepts at most 256 supplied WAVs per
  transaction, even when the metadata-only template lists more targets. Folder
  import counts and refuses entry 257 before opening or hashing any WAV bytes;
  ZIP import enforces the same ceiling before payload extraction.
- Kept import automatic and backward compatible. Folder and ZIP import detect
  v1 `xma1/*.xma` versus v2 `pcm16/*.wav` from the exact schema and input
  contract. The v1 writer, generated README, default selection, and
  deterministic ZIP bytes remain unchanged, and legacy v1 imports do not need
  a configured encoder.
- Preserved one final admission path for both pack generations. PCM WAVs are
  copied into private pinned inputs, encoded one at a time, and then cross the
  existing exact allocation, packet, complete-decode, duration, target,
  optimistic-baseline, AUSB alias, and cross-family source-packet gates. Only
  after every supplied sound passes does the full set become one Undo action.
  Encoder failure, validation failure, alias conflict, cancellation, or a
  changed pack removes new unreferenced private work and stages nothing.
- Added explicit **Pre-encoded XMA1** / **Exact PCM16 WAV** controls, format-
  specific folder/ZIP labels, progress and cancellation copy, and copyright
  guidance to the Audio workspace. **Ctrl+F** now focuses the visible enabled
  search field in the current workspace from the shared shell; it does not
  target hidden searches inside inactive tabs.
- Kept the boundary explicit: Mod Studio still ships no XMA1 encoder and had no
  real encoder for compatibility proof. PCM-pack tests use synthetic encoders
  to prove orchestration and validator handoff, not perceptual encoding.
  FLAC/MP3, mixed PCM/XMA packs, more than 256 supplied WAVs per import, and
  whole physical-bank replacement remain unsupported. Authored-audio runtime
  causality remains inconclusive, and the `.apf2k8mod`/Build schema is
  unchanged.
- The focused Alpha.28 product gate passes 115/115 and the complete headless
  APF suite passes 457/457. The sealed release metrics and authoritative
  archive identity are recorded in `APF2K8_STATUS.md` and the adjacent
  `.sha256` sidecar; no interactive desktop or emulator was launched.

## 0.1.0-alpha.27 — selected-sound PCM authoring bridge 2026-07-20

- Added **Export PCM authoring template…** and **Replace from PCM WAV…** to
  every individually editable Audio row: 2,261 standalone AUDO sounds plus
  45,514 semantic AUSB substreams. The exported WAV is exact-length PCM16
  silence derived from the selected slot's channel count, sample rate, and
  declared frame count; it contains no source audio. The success receipt also
  shows the fixed encoded XMA allocation that a WAV header cannot express.
- Added a no-terminal **Configure XMA1 encoder…** dialog for a modder's own
  separately installed tool. Native executables run directly; Windows `.exe`
  tools can use a separately installed Wine executable. Advanced configuration
  accepts one literal argv entry per line with bounded `{input}`, `{output}`,
  `{channels}`, `{sample_rate}`, `{sample_count}`, and `{encoded_size}`
  placeholders. No shell command is accepted or constructed.
- Kept external-tool configuration outside `.apf2k8mod`: resolved encoder/Wine
  paths, literal argv, and a 30–1800 second timeout live only in per-user
  application settings. Deleted/corrupt tools report **Needs attention** rather
  than breaking the Audio page. A 600-second default covers the longest
  soundtrack authoring jobs better than the backend's shorter library default.
- Added cooperative **Cancel PCM encoding**, bounded stderr/output, private
  canonical PCM staging, and full owned-process-group TERM/KILL cleanup on
  success, failure, timeout, cancellation, and exceptions. Independent review
  reproduced and then closed a child-process escape before packaging.
- Preserved one final admission path. External output is untrusted until the
  existing AUDO/AUSB RIFF, exact allocation, packet framing, complete decode,
  duration, shared-owner, target identity, and cross-family exact-source-packet
  checks all pass. Only then does one normal Undo-able edit enter the project.
  **Replace with XMA1…** remains available as the advanced direct route.
- Kept the boundary explicit: Mod Studio ships no encoder; the build environment
  had no real XMA1 encoder for compatibility proof; synthetic fake encoders
  prove process and validator handoff only. FLAC/MP3 and batch PCM input remain
  unsupported. Folder/ZIP batch replacement still accepts finished exact-slot
  XMA1. In-game authored-audio causality remains inconclusive.
- Corrected the roster roadmap with the completed headless result: a valid
  180-second passive slot-43 observe control preserved the source and ended
  `path_not_reached`. Ordinary no-input boot does not exercise the defensive
  roster-builder path, so modified mode stays locked pending a deliberately
  navigated positive observe run. The 0–99 editor already covers all 63,112
  mapped base-rating cells; true 53-player runtime teams remain an emulator-side
  multi-consumer project, not a data-only edit.
- Sealed the exact retail-free allowlist after independent GO review: `104`
  files in `15` directories, `3,297,442` file bytes, `22` executables, `71`
  Python files, and `119` sorted safe tar members. The full APF suite passes
  442/442, the focused release/GUI gate passes 65/65, and the slot-43/census
  suite passes 44/44. Both the stage and a clean extraction pass the 66-module /
  31-capability runtime gate and release audit; deterministic re-archive is
  byte-identical. The adjacent `.sha256` sidecar, not this packaged document,
  is the archive's authoritative identity.

## 0.1.0-alpha.26 — audio ZIP hand-off and accessible shell 2026-07-20

- Added a clear **Editable folder / ZIP hand-off** selector to the Audio batch
  authoring workflow. Either format can describe the current filters, the
  Soundtrack album, the reviewed shortlist, or the complete 47,775-sound
  editable surface. The generated template remains metadata-only: it contains
  target coordinates, exact slot shape, aliases, source binding, and current
  replacement baselines, but no original game audio or source-owned names.
- Added deterministic, non-overwriting ZIP template publication and direct
  edited-ZIP import. ZIP templates put `replacement-pack.json`, `README.md`,
  and `xma1/` at the archive root. The importer accepts normal stored or
  deflated, unencrypted archives and privately materializes their files only
  for the bounded validation/import transaction.
- Kept the Alpha.25 authoring guarantees unchanged across both containers:
  missing XMA1 files are skips, every supplied file crosses exact-slot decode
  and cross-family retail-packet rejection, stale target/alias baselines fail
  before commit, all real changes become one Undo action, and a failed or
  cancelled import changes no project edit. Existing Alpha.25 template folders
  and their original generated README remain accepted.
- Added explicit archive defenses for path traversal, symlinks and special
  entries, encryption, duplicate or case-colliding names, wrapper directories,
  undeclared members, expansion limits, and archive/file identity changes.
  Temporary extraction is private and removed after success or failure.
- Improved the shared shell without changing an editor contract: **Ctrl+1**
  focuses the category sidebar from anywhere, category and asset lists have
  strong keyboard-focus outlines, header/footer chrome can grow for larger
  system fonts, and navigation, operation status/progress, Build, and Launch
  expose descriptive accessibility text. Focused offscreen Qt coverage checks
  both product shells; this is not a visual or screen-reader certification.
- This remains an exact-slot, pre-encoded one-stream RIFF XMA1 workflow—not an
  audio encoder. WAV/FLAC/MP3 input and authored-audio runtime causality remain
  unproved. Alpha.26 was the then-current headless-tested packaged checkpoint;
  Alpha.25 remains the prior sealed retail-free package. The exact allowlisted
  stage and clean extraction pass the retail-free and isolated runtime gates;
  no interactive desktop or emulator was launched.

## 0.1.0-alpha.25 — batch audio authoring checkpoint 2026-07-19

- Added the Audio tab's retail-free **Create replacement template…** and
  **Import replacement folder…** workflow across all 47,775 individually
  editable sounds: 2,261 standalone AUDO slots plus 45,514 semantic AUSB
  substreams. A template may come from the current search/kind/role/source
  filters or the exact reviewed shortlist. It contains only generated target
  IDs, coordinates, exact slot shape, alias ownership, and loaded-source
  binding—never original audio or source-owned sound names.
- Added safe manifest-plus-folder batch admission for already encoded,
  one-stream RIFF XMA1 files. Missing listed files are intentional skips. The
  importer rejects unknown files/rows, repeated identities or filenames,
  edited slot shape, changed source binding, unsafe paths, invalid audio,
  divergent aliases, and unchanged-only packs. Every manifest identity is
  reconciled before packet work; every supplied sound then crosses the existing
  full decode and cross-family source-packet rejection boundary.
- Bound every manifest entry to the selected sound's current replacement-only
  project state, including every disclosed AUSB alias owner. Import checks this
  optimistic target lock before packet work and again immediately before the
  atomic commit. A stale target asks for a fresh template, while unrelated
  project edits do not block useful work. Baselines are canonical hashes and
  carry no private path, replacement bytes, or retail data.
- Made batch mutation atomic at the project level. Validated payloads are
  prepared privately first; the active edit map changes only after the whole
  folder passes. All real changes become one Undo action, while a failure leaves
  both the active edit set and Undo stack untouched. Failed cleanup preserves
  every packet file referenced by either active edits or any Undo snapshot, and
  an advisory progress-callback failure cannot escape after a successful
  commit. The generated README and manifest are bounded private regular files;
  modified or hardlinked contract files are rejected. Existing `.apf2k8mod`
  serialization and Build receive the same typed AUDO/AUSB modifications, so
  their replacement-only and exact-source-byte rejection guarantees remain in
  force.
- Added per-file validation progress and **Cancel replacement import**. The
  cancel request is observed only between complete XMA1 files; a cancelled
  folder changes no project edit, adds no Undo action, preserves the last valid
  Build receipt, and removes only new unreferenced private packet-cache files.
- This is a manifest-and-folder v1 workflow, not a replacement ZIP and not an
  encoder. Ordinary WAV, FLAC, MP3, WMA, xWMA, and XMA2 input still requires a
  distributable XMA1 encoder. The focused audio/build/project closure passes
  **128/128** in the final root rerun. A real-source metadata-only spot check created an AUDO plus
  two-owner `cwdloop` alias template with an empty `xma1/` folder and no source
  titles in the manifest. A clean 101-file staged tree passes the retail-free
  release gate and the runtime import gate at 65 modules / 31 capabilities. No
  GUI or emulator was launched for this headless Alpha.25 checkpoint.
- Advanced Alpha.25 to the then-current packaged checkpoint after an independent
  adversarial GO review. The review reproduced and closed stale-template and
  Undo-owned-payload cleanup failures before release. The final exact
  allowlist contains 101 files; both the stage and an independent clean
  extraction pass the retail-free release gate and the 65-module / 31-capability
  runtime gate. The archive remains deliberately self-hash-free and is
  authenticated by its adjacent checksum sidecar.

## 0.1.0-alpha.24 — headless packaged checkpoint 2026-07-19

- Added an output-drive free-space preflight before hashing or creating a
  private build stage. APF Build now requires room for the complete extracted
  game tree plus a 512 MiB safety margin. A refusal reports available,
  required, and missing GiB in modder-facing language and creates no partial
  output. Tiny shortages are reported in bytes instead of rounding down to
  `0.00 GiB`. The same behavior is implemented for 2K5; focused cross-title
  build-safety tests pass **32/32**.
- Added a fixed **Position (17)** editor for every one of the 2,254 on-disc
  players. The dropdown exposes the exact native codes `0..16` (QB through DE),
  supports individual Apply/Revert and modified badges, persists only the
  user-selected code in `.apf2k8mod`, and composes with player names, team names,
  and all 28 base ratings in one token-preserving ROST Build. The bounded writer
  changes executable-consumed player byte `+0x34` and its required opaque source
  mirror at `+0x35` as one indivisible pair; it refuses a source record whose
  pair already differs. Position edits do not infer team membership, depth-chart
  slots, ratings, Overall, tier, or abilities. Offline writeback and clean
  retail-free packaging pass; the first changed-position Xenia spot check is
  still pending, so the UI and capability registry say that plainly.
- Advanced Alpha.24 to the current headless-tested packaged checkpoint; the
  sealed Alpha.23 archive remains preserved as the previous checkpoint. The
  complete 163-test focused gate passes, as do the retail-free release and
  64-module/31-capability runtime gates on a clean stage and independent
  extraction. The packaged changelog remains deliberately self-hash-free;
  Alpha.24's exact archive identity is authenticated by its adjacent checksum
  sidecar. No GUI or emulator was launched.

## 0.1.0-alpha.23 — previous packaged checkpoint 2026-07-19

- Extended strict pre-encoded RIFF XMA1 Replace/Revert, modified badges, Undo,
  project save/load, replacement preview, and typed Build from the 2,261
  standalone AUDO slots to **all 45,514 semantic AUSB substreams**. They resolve
  to **45,513 canonical physical ranges** across 19 external banks. Physical
  External Bank and AUSB index rows remain private raw containers; authoring is
  deliberately scoped to their individually addressed substreams.
- Added the source-resolved, pack-aware AUSB build compiler. It validates exact
  channels, sample rate, packet allocation, decoded duration, semantic owner
  metadata, the complete cross-domain `0x800`-packet authorization inventory,
  and every individual source pack span. The stereo Track 3 allocation crosses the end of `0A` and start of
  `0B`; Build splits those writes, verifies bytes outside them unchanged, and
  atomically publishes only the complete staged game folder. No descriptor or
  whole-bank repack is performed.
- Closed alias and retail-byte safety. The one `cwdloop` physical allocation has
  two disclosed semantic owners. Identical edits through both IDs deduplicate;
  divergent writes to the same bytes fail before publication. Projects retain
  canonical user packets plus semantic shape/owner fingerprints only—no source
  audio, preimage, source fingerprint, physical coordinate, or descriptor byte.
  Session admission, project load, modified preview, and Build each reject any
  replacement containing one complete `0x800`-byte packet found anywhere in
  either the AUDO or AUSB source inventory, including cross-family transplants.
  A real-source Build scan rejected an 8-bit-mutated Track 12 near-retail
  candidate at packet 0 that the former whole-payload-only gate admitted; the
  scan took 14.13 seconds and peaked at 208,896 KiB RSS. The 40,316 unique whole
  AUSB payload hashes remain an inventory measurement, not the safety boundary.
- Recorded the runtime and decoder boundaries without promoting causality. The
  private candidate booted, selected **Track 12 — Bury Me Standing Remix**, and
  visibly remained in playback for 25 seconds without a crash. The completed
  objective capture experiment was negative/inconclusive: its sustained segment
  matched neither the mutated candidate nor stock Track 12 (best 17-second
  `|NCC|` about `0.031`), distinguishing frames favored neither, and a
  self-control confirmed classifier power. This proves boot/selection/stability,
  neither authored-audio consumption nor stock fallback. FFmpeg 6.1.1 decoded
  18/30 original jukebox stereo/mono sides; all 45,514 targets remain
  addressable, but replacement input must pass the stricter complete decode.
- Added a retail-free **32-team × 53-row roster planner**. Each team shows the 42
  memberships stock APF currently sees plus eleven project-only reserve slots.
  `.apf2k8roster` stores only authored reserve player indices, never the source
  memberships or game bytes, and Build does not apply the reserves. True 53
  runtime players still require a version-pinned XEX consumer/accessor patch and
  owned side-table storage. Cross-domain safety tests pass `4/4`, the focused
  combined audio/build suite passes `25/25`, and the full product suite passes
  **722/722 in 93.739s**.
- Advanced Alpha.23 to the then-current sealed packaged checkpoint; Alpha.22 is
  previous. The `682,202`-byte archive has SHA-256
  `ca1f5ed0f3dab91f373a520e664cbdb59d1f30afc2844e83c3ed76204a039c67`,
  authenticated by its adjacent mode-`0444` sidecar. Stage and independent
  extraction each passed the release and both runtime gates at `96` exact
  allowlisted files; two direct archives and the extraction re-archive were
  byte-identical. The sealed package's own changelog remains deliberately
  self-hash-free; this source entry was updated after sealing.

## 0.1.0-alpha.22 — sealed 2026-07-19

- Added an experimental exact-slot editor for all 2,261 standalone `AUDO`
  resources. Selecting a **Standalone AUDO** row now exposes **Replace with
  XMA1…**, per-sound Revert, the normal modified badge, Undo, project save/load,
  staged-replacement waveform/play preview, and the typed Build path.
- The importer accepts only pre-encoded, one-stream RIFF XMA1. Channel count,
  sample rate, encoded byte length, and decoded sample count must match the
  selected target; encoded data must remain a nonempty `0x800`-byte packet
  multiple. Every packet must use the APF XMA1 metadata/skip contract, and a
  complete FFmpeg error-exit decode must pass before an edit is staged.
- Added a dedicated compiled-span build route instead of exposing arbitrary raw
  offsets. All 2,261 source targets resolve to uncompressed, contiguous,
  non-overlapping `0A` spans. Multiple edits compose with typed whole-entry
  writers, collisions fail closed, every authored span is verified exactly,
  bytes outside the compiled spans must remain source-identical, and the output
  archive is reparsed before success.
- Kept shareable projects replacement-only. They store canonical user-supplied
  raw XMA1 packets under `.xma1-packets` plus bounded target-shape metadata;
  they never store the supplied wrapper, original sound, rollback bytes,
  retail loop metadata, or physical source offsets. At this sealed checkpoint,
  any exact replacement payload matching one of the 2,261 source `AUDO` cues is
  rejected at import and project admission. Alpha.23 supersedes
  this release-era family-local check with the cross-domain packet gate above.
- Did not claim a general audio encoder. WAV, FLAC, MP3, WMA, XMA2, and
  size-changing XMA input remain unsupported because the local distributable
  toolchain has no validated XMA1 encoder. The 45,514 `AUSB` substreams and all
  19 physical multi-cue banks—including both 15-track soundtrack encodings—
  remain browse/play/export-only while their cue-directory/repack semantics are
  unresolved.
- Completed a matched Xenia runtime spot check instead of leaving playback as
  pending. The one-span candidate booted, logged no XMA fault, survived five
  intended Schedule-enter triggers, returned to the Season hub, and closed
  normally; a restored byte-identical stock control followed the same route.
  Timestamp-aligned waveform correlation did not beat random windows, and the
  correctly directed spectral interaction did not beat 160 pseudo-event sets
  (`p=0.155` one-sided). Classification remains **offline-writer-proved;
  runtime partial, audible cue consumption inconclusive**, not runtime-proved.
  See the
  [exact-slot authoring contract and A/B result](../product/APF_AUDO_EXACT_SLOT_XMA1_EDITOR.md).
- Completed isolated-display visual QA against the recognized source. A
  standalone row showed **Replace with XMA1…**, **Revert sound**, and its exact
  54.0 KiB / 22,050 Hz / stereo requirement without clipping. The 15-track
  `jukebox22` view kept replacement disabled and explained that shared AUSB
  banks remain export-only. The final copy now calls exact-slot import an
  advanced workflow, says plainly that ordinary WAV/FLAC does not work yet,
  and explains why soundtrack/commentary Replace is disabled.
- Packaged and sealed Alpha.22 as the then-current retail-free Linux checkpoint.
  The archive is `633,190` bytes with SHA-256
  `f2adf77b9abdeddd1b2c2bf93fd2523a93eb721a192543c7660ba3e49b4578fb`;
  its adjacent mode-`0444` sidecar verifies. Stage and independent extraction
  match at `92` allowlisted files, `15` directories, `2,706,017` file bytes,
  `22` executables, and canonical inventory SHA-256
  `75e647061b379f1970448d85847ed12b8bbbdeb2064b8ff04112dc60036f1629`.
  Both deterministic archives were byte-identical and both trees passed the
  retail-free, 59-module/31-capability runtime, private-source, desktop, Bash,
  and post-runtime gates. Package-facing copies remain deliberately self-hash-
  free; this post-seal source entry and the adjacent sidecar authenticate the
  immutable archive.

## 0.1.0-alpha.21 — 2026-07-19

- Promoted bounded player **First name** and **Last name** replacement into the
  runnable product source. The existing token-preserving ROST route now admits
  3,191 nonempty player-name allocations serving 4,482 writable first/last
  references, alongside the 40 existing team display-name allocations. That is
  3,231 product-editable name allocations in total; the zero-capacity empty
  allocation, both team-abbreviation families, and any mixed or unknown scope
  remain locked.
- Generalized **Replace Name** / **Revert Name**, project load, and Build around
  one centralized fail-closed scope check. Pure player-name aliases may span
  first- and last-name owners, but a mixed team/player allocation cannot inherit
  permission. The earlier team-display-name compatibility route remains intact.
- Added complete local alias disclosure before authoring. The source contains
  429 shared editable player-name allocations, the largest with 23 owners; 61
  are shared across both first- and last-name fields. One replacement changes
  every listed owner together, and the UI reports that explicitly instead of
  silently treating the selected field as independent.
- Kept shareable projects retail-free and replacement-only. A project stores
  authored text plus the existing pool index, limit, owner count, and owner
  fingerprint; it does not persist retail player names, alias-owner lists,
  source strings, ROST records, preimages, physical offsets, or game bytes.
- The runtime basis remains the isolated Xenia `Marino` → `CODEX` proof: **Dan
  CODEX #13 QB** rendered in player selection and **QB #13 DAN CODEX — GOLD
  STAR** rendered on the Star Card without the former startup crash. The
  complete Alpha.21 product suite passes `648/648` in `90.763s`.
- Completed the real-source public product smoke through the same actions a
  modder uses: load the game, replace Dan's last name with `CODEX`, Undo,
  replace, Revert, replace again, save a project, reopen it, Build a separate
  3.7 GB game, and reparse the output. The 989-byte project has SHA-256
  `45902ead474bfd868c88469220076e3cd23a47e7a58c3fa568129e1bb743694e`
  and contains replacement JSON only. The output `0A` has SHA-256
  `0212b638c1cdfa348110e57dbef4af5e0048101ff340202f52fec2021cd54044`,
  exactly matching the runtime-proved candidate; only outer 1126 changed and
  the source remained byte-identical.
- Completed isolated Spark visual QA after the roster-layout UX fix. A fresh
  window showed **Identity & Names** by default with **Base Ratings (28)**
  adjacent; **Replace Player Name**, **Revert Player Name**, and **View 23
  affected fields…** were simultaneously visible with the exact `4/4` limit and no
  clipping or scroll trap. A separate retail-free product-code dialog check
  showed high contrast and all 23 owner rows at once.
- Packaged Alpha.21 as the then-current retail-free Linux checkpoint. Verify the
  archive against its authoritative adjacent `.sha256` sidecar before install.
  Final tree/archive seal details are authenticated by that sidecar and the
  post-seal source `STATUS`; this package-facing changelog deliberately avoids
  embedding its own circular archive hash. Alpha.20 is preserved as the
  previous checkpoint at SHA-256
  `f3f02cbefbbcd5f0890efb889948e2a34487a9f07f0a2900744d44b19da56ef8`.
- Post-seal source receipt: the corrected archive is `607,218` bytes with
  SHA-256
  `35b7d23298ce69639ad7e2a09b24be4838de6066d22963abaf0f387dd3d4e232`;
  its `119`-byte mode-`0444` sidecar verifies, and its tar has `105` safe
  members. Stage and clean extraction match at `90` allowlisted files, `15`
  directories, `2,594,779` file bytes, `22` executables, and canonical inventory
  SHA-256
  `96f74cb24a044368a244e04b843f0bc6c6bb686ef2f8b5c1c0523a0670db7da5`,
  with no links, special/undeclared files, private material, or retail bytes.
  Both trees passed every release/runtime/private-source/desktop/Bash gate, all
  `63` packaged Python files parse, and a second deterministic tar was
  byte-identical.
- An independent audit rejected and deleted the first regenerable candidate
  because its bundled docs still called Alpha.20 current and Alpha.21 pre-seal.
  Only the corrected current-Alpha.21 rebuild was sealed. The packaged copy of
  this changelog remains intentionally self-hash-free; its adjacent sidecar and
  the post-seal source `STATUS` authenticate the exact seal.
- Did not promote team abbreviations, jersey numbers, roster membership, depth
  charts, active-roster capacity, or audio replacement. True 53-active-player
  teams still require an executable consumer/accessor extension rather than a
  larger name allocation.

## 0.1.0-alpha.20 — 2026-07-19

- Turned **Export complete audio catalog…** into a self-describing private
  audio library. Its v2 manifest retains the role, source/bank, format, sample
  rate, channel count, duration, soundtrack pairing, and owned size metadata
  already visible in Mod Studio instead of reducing each cue to coordinates.
- Added deterministic `catalog.csv` with one ordered row for every requested
  semantic item, including failures, unsupported bank/index rows, and rows
  skipped after cancellation. Successful sounds now carry their exact archived
  byte size and SHA-256 in both the JSON and CSV.
- Added ordered `playlist.m3u8` for successful cue payloads and omits it when
  no playable sound succeeds. Playlist entries never include AUSB index rows,
  raw physical banks, failures, or cancelled items. Spreadsheet-formula and
  control-character sanitization applies to the convenience CSV/playlist;
  the source-derived JSON metadata remains the authoritative record.
- Kept the boundary unchanged: the ZIP is private retail-derived output, Track
  01–15 remains honest when artist/title are unknown, original XMA1 may require
  a compatible player, and no encoder, replacement writer, or cue/loop
  ownership is implied.

## 0.1.0-alpha.19 — 2026-07-18

- Added **Export all original banks (19)…** as a separate private audio route.
  It copies every physical external XMA1 `.bin`—including `jukeboxmusic` and
  `jukebox22`—through the already bounded raw-bank reader into one atomically
  published, non-overwriting ZIP. The deterministic manifest records the
  source fingerprint, exact bank name/outer identity/name ID, payload size and
  SHA-256, plus every AUSB descriptor owner and conservative role label.
- Wired the existing cooperative cancellation contract into the actual Audio
  GUI for both the 47,814-row cue catalog and the physical-bank bundle.
  **Cancel audio export** stops between complete sounds or banks; the published
  partial manifest accounts for every skipped item, so no file is truncated
  and cancellation is never reported as an unexplained success.
- Kept the capability boundary explicit. Raw physical banks are multi-cue
  containers, not directly playable sounds; export does not imply XMA1 encode,
  replacement, cue/loop ownership, or a reversible bank writer. Exported ZIPs
  are private retail-derived files and never enter `.apf2k8mod` projects or the
  public application package.

## 0.1.0-alpha.18 — 2026-07-18

- Added **Import ratings sheet…** beside the complete roster export, with
  `Ctrl+Shift+I` as a keyboard shortcut. The v2
  private CSV is bound to the exact loaded-game SHA-256 and contains all 2,254
  players × 28 canonical rating columns. Export now includes the active project
  values, so a modder can round-trip a large work-in-progress roster through
  LibreOffice without losing earlier in-app edits.
- Added a non-mutating review dialog with separate counts for new replacements,
  source reverts, already-matching cells, project conflicts, source conflicts,
  and errors. Wrong-source or edited source-metadata conflicts are never
  overrideable. A sheet that disagrees with an active project edit requires a
  second explicit acknowledgment before Apply.
- Implemented three-way source/current/sheet comparison, stable-file and
  active-edit fingerprints, revalidation immediately before mutation, and one
  atomic batch commit. A complete import creates exactly one Undo action;
  rejected and zero-change imports create none. Native `100` is accepted only
  when preserving or reverting an existing source `100`; authored values stay
  exact `0..99` integers.
- Kept the CSV private and the project retail-free. `.apf2k8mod` stores only
  canonical authored rating payloads and semantic target metadata—not the CSV,
  player names, source values, roster records, or preimages.
- Real-source smoke covered 63,112 cells, Dan Marino Speed `40` → `99`, active-
  project conflict confirmation, one-step Undo, project-ZIP inspection, and an
  unchanged source hash. The supported retail roster's observed values span
  `0..99` and contain no actual `100`; the source-100 compatibility/revert case
  remains covered by the focused synthetic contract test.

## 0.1.0-alpha.17 — 2026-07-18

- Promoted the completed 0–99 ratings slice from source-head wording to the
  packaged product documentation. Getting Started now reports the live
  8 Editable / 6 Preview / 3 Export-only / 14 Coming Soon capability split,
  and the README points to each archive's authoritative checksum sidecar and
  versioned status receipt instead of describing an older package as current.
- Product code is unchanged from the 617/617-tested Alpha 16 ratings build;
  this checkpoint corrects release-facing version/document consistency.

## 0.1.0-alpha.16 — source head, 2026-07-18

- Promoted all 28 mapped per-player **Base Ratings** from exact Preview to
  strict native `0..99` authoring. Each edit is addressed by player index and
  stable attribute ID, stored as a tiny canonical replacement-only JSON
  payload, marked modified, individually revertible, Undo-safe, and included
  in project save/load and transactional Build. No scale conversion, inferred
  Overall, star-tier change, or neighboring-byte write occurs.
- Preserved the engine's distinct native-100 compatibility case. An untouched
  source value of 100 is displayed exactly and can be reverted, while new
  authored values remain deliberately limited to 0..99.
- Added the token-preserving player-rating writer and a disjoint-delta ROST
  compositor. Team display-name edits and rating edits now share outer entry
  1126 safely in one build instead of colliding or rebuilding one change over
  the other. Component manifests authorize only their selected decoded ranges;
  no original values, replacement values, preimages, physical pack offsets, or
  game payload bytes enter a shareable project or public receipt.
- Promoted exact team **Display name** replacement under its live allocation
  limit. Player first/last names and both team abbreviation fields stay visible
  but locked; jersey number, position, membership, depth charts, abilities, and
  Gold/Silver/Bronze tier remain separate unresolved capabilities.
- Replaced the superseded generic H7A rebuild path that crashed at guest PC
  `0x84AB1D40`. A token-preserving `Americans` → `CODEXTEAM` candidate booted
  through first-run construction and rendered the name in Logo Selection, Team
  Summary, and Team Select. A one-byte Dan Marino Speed `40` → `99` candidate
  preserved 284,014 of 284,015 tokens, booted, and loaded/rendered the edited
  player card without the former crash. APF has no numeric ratings screen, so
  the latter proves transport and player-record load—not a measured gameplay
  effect.
- Kept ratings-sheet export as a private, owner-only planning artifact. The
  public `.apf2k8mod` format contains only user-authored semantic deltas and
  retail-free target metadata; it never embeds the source roster or original
  rating values.

## 0.1.0-alpha.15 — source head, 2026-07-18

- Added **Export ratings sheet…** to Rosters & Players. It creates a private,
  wide CSV with all 2,254 on-disc players, identity/position/team context, and
  one stable column for each of the 28 exact base ratings. The export validates
  the complete player index set, native 0..100 values, and canonical field
  order before publishing.
- Ratings sheets are retail-derived local exports, never project payloads. They
  use owner-only permissions, publish atomically, refuse an existing filename,
  and explain plainly that the CSV must stay private. Import/edit remains
  locked with the shared rebuilt-ROST runtime boundary.
- Full-source smoke passed at 2,254 rows, 28 rating columns, indices 0..2253,
  native 100, stock maximum 99, and mode `0600`; the private output was deleted.
  Isolated `DISPLAY=:99` QA found the enabled toolbar action unclipped at
  1480×920 with both roster scroll areas and runtime-lock badges intact.
- Started three bounded crash-isolation tracks for guest PC `0x84AB1D40`:
  static function/register tracing, retail-vs-rebuilt container comparison,
  and a practical guest-state logging route. Each must end with a concrete
  experiment/result before writer exposure changes.

## 0.1.0-alpha.14 — 2026-07-18

- Added a searchable, read-only **Base Ratings** panel for every one of the
  2,254 on-disc player records. It exposes all 28 independent stored bytes: 27
  executable-named attributes plus neutral **Unknown Rating 24**. Values are
  shown exactly on the native 0..100 contract; stock data spans 0..99 and is
  never clipped or rescaled. Semantic JSON/CSV roster export includes the same
  field IDs, labels, values, and record-relative coordinates. Overall,
  abilities, and Gold/Silver/Bronze tier remain explicitly separate. Rating
  replacement stays locked with the shared rebuilt-ROST runtime boundary.
- Added the bounded APF roster identity map and development writer. The
  supported source contains 3,273 owned UTF-16BE allocations, 3,272 nonempty
  offline-writer targets, and 4,628 mapped references (4,508 player fields plus
  120 team fields). Shared allocations retain their alias-owner count. This
  mapping remains available in **Rosters & Players**, but runtime evidence now
  locks replacement as Preview/read-only.
- Completed a clean-controlled runtime experiment. The clean source reached
  the APF title screen, while combined, team-name-only, and player-name-only
  builds all crashed during startup at guest PC `0x84AB1D40`, reading
  `0x0000000270000000`. The identical team/player failure falsifies the current
  ROST replacement transport rather than implicating one authored name.
  New Replace authoring and Build exposure were removed from the public
  capability. A removal-only Revert path remains for legacy development
  projects, and Build refuses until those edits are removed. The offline
  reconstruction backend remains development evidence only. See the
  exact [runtime report](../product/APF_ROSTER_IDENTITY_RUNTIME_NEGATIVE.md).
- Recorded the next roster experiment: instrument guest execution around
  `0x84AB1D40` to capture the invalid object/pointer chain and compare the
  retail decoder's output for one rebuilt H7A block against the project's
  decoded body. If those bodies agree, trace post-load relocation or integrity
  ownership before changing the writer again. The separate
  [32-team/53-player feasibility note](../product/APF_32_TEAM_53_ROSTER_FEASIBILITY.md)
  remains an ambitious capacity study, not evidence that name replacement is
  safe.
- Jersey numbers remain explicitly read-only because the decoded ROST evidence
  contains no consumer-backed jersey-number field. Base ratings are now mapped
  for exact Preview, but their writer, positions, membership, and depth charts
  are not implied by the identity map.
- Added a dedicated **Field Art ownership map** for all 258 live category rows
  across 125 archive packages. Seven exact families make the inventory useful:
  235 endzone textures, four field scenes, four field-radiance textures, six
  divot/weather textures, three practice/field overlays, four practice-related
  scenes, and two penalty animation curves. Search, family filtering, package
  identity, preview, and the existing PNG/scene/raw export routes are wired.
  Replace/Revert stay locked because name and archive co-location do not prove
  a team, stadium, selector, shader, material, or runtime owner.
- Added explicit, cancellable Audio waveform previews. **Load waveform** reuses
  the selected cue's verified session-private WAV and samples PCM16 within a
  fixed memory bound; selection alone never starts a decode or player. Changing
  row/source cancels stale work, errors remain retryable, and AUSB index or
  physical-bank rows never advertise a single-cue waveform.
- Added **Export complete audio catalog…**, the 47,814-row atomic Audio batch
  route for original XMA1 or decoder-verified WAV. All 2,261 standalone cues
  and 45,514 addressed AUSB substreams use the existing verified single-sound
  exporter. The manifest records all 20 AUSB index rows and 19 physical-bank
  rows as unsupported, plus every per-cue failure or cancellation, instead of
  silently dropping rows.
  The final ZIP publishes without replacing an existing destination. This is
  export-only and does not enable Audio replacement.
- Completed the bounded Wine-hosted stadium debugger experiment with a useful
  negative result. Wine intercepted Xenia's host instruction breakpoint before
  a game frame or guest-register capture, so the route did not test
  material-to-TXTR ownership. The exact private debugger change was rolled back.
  The next credible experiment is a logging-instrumented Xenia build or a
  native-Windows guest-debugger capture, not a repeat of the same Wine route.
- Kept the roster identity capability at Preview after its runtime
  falsification. The sealed registry has 31 APF records, split 7 Editable,
  7 Preview, 3 Export-only, and 14 Coming Soon.
- Fixed the tall roster-detail layout found during visual QA: ratings and name
  allocation controls now use an independent vertical scrollbar, roster rows
  say **Mapped names · Runtime locked** instead of Editable, and the workspace
  tab has enough width/padding to render **Roster + Base Ratings** completely.
- Sealed the retail-free Linux package after `588/588` tests, source-free and
  private-source runtime closure, release/install safety, independent
  extraction, deterministic archive reproduction, and isolated `DISPLAY=:99`
  visual QA. The archive contains 84 allowlisted files and has SHA-256
  `b38350de9dbc121c963861db44e2bac2d9caa8595cdd35e39766f2b205203279`.
  The complete receipt is in [STATUS](APF2K8_STATUS.md).

## 0.1.0-alpha.13 — 2026-07-18

- Added a capability-to-action binding layer between the shared registry and
  the APF desktop. Every capability card that remains Editable or Export-only
  now names a real product handler and its supported Preview, Export, Replace,
  and Revert actions. Exact asset editors dispatch through the same binding,
  so a registry classification or a similar asset name cannot fabricate a
  working button.
- Kept **Menus & Text** honestly Editable by binding
  `apf2k8.menus.layouts` to its existing in-place editor for 2,410 of 2,413
  decoded TXT/STRG allocations. Card status no longer depends on an irrelevant
  file-extension input. The three protected structural allocations remain
  read-only under the existing Text Sheet and per-row contracts.
- Downgraded six unbound semantic promises to honest **Coming Soon** cards:
  cross-title model conversion, the broad uniform-logo catalog, mode/state
  routing, generic SCNE-to-glTF conversion, `hi_head` face research, and the
  retained Season/franchise research lane. Their data remains inventoried in
  the appropriate browsers; only the nonexistent dedicated desktop action is
  withheld. The specialized Stadium glTF viewer remains Export-only because it
  does have its own bounded handler.
- Split the exact `franchise.iff` `draft_logo` writer into a dedicated editable
  registry capability. The registry now contains 31 APF capabilities
  and 61 capabilities across both games; the 30 existing NFL 2K5 records are
  unchanged. Their alpha.13 card split is 7 Editable, 7 Preview, 3 Export-only,
  and 14 Coming Soon. The hidden `jersey_06_runtime` record stays a proof alias,
  not a duplicate user-facing editor. The broader APF logo catalog remains
  browse/export only.
- Added explicit disabled-state styling for primary, secondary, utility,
  Build, and Launch controls. Stadium replacement is labeled **Replace
  (locked)**, closing the alpha.12 visual ambiguity where a disabled primary
  button could retain its orange active color.
- Polished Audio selection at the physical-bank boundary. Multi-cue external
  bank rows hide the single-sound Play control, use **Choose a sound to
  shortlist**, and retain a wider/taller technical detail pane for long bank
  ownership and archive coordinates. Exact raw-bank export stays available;
  Play, shortlist, and Replace remain cue-only actions.
- Completed the bounded static stadium-material experiment. The first scene's
  116 mesh nodes resolve through 328 draws to all 113 serialized material
  records and 13 shader families. Scanning 737 unique named texture identities
  found zero static references in the scene-system material data, including no
  reference to the three same-package texture candidates. This is a useful
  negative result: surface-to-TXTR ownership is still unresolved and
  Replace/Revert remain locked.
- Recorded the next stadium experiment precisely: capture one known draw at
  the runtime renderer material handoff, recover the loaded material-array
  base and pixel-shader texture mapping, follow live texture-object pointers,
  and correlate their guest allocations/dimensions with the scene GPU part and
  same-package TXTR allocations.

### Release receipt

- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.13-linux-x86_64/`
- Linux archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.13-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.13-linux-x86_64.tar.gz.sha256`
- Size: `477,068` bytes
- SHA-256:
  `645c021d9d3d0570ed6a307c15a8a06387fb4be3cf20abaf23a70f3bc0b14e9f`
- The release tree and independent clean extraction are path-, mode-, and
  size-identical: `73` files, `14` directories including the root, `2,023,280`
  file bytes, `22` executables, zero symlinks or special files, and `87` tar
  entries. Their shared path/mode/size inventory SHA-256 is
  `6b5c7868c4f39febd889e225ab9f7d6d5e075064bbeccd17bbb0fc9f4ad98cd2`.
- Release validation passed with `73` allowlisted files, `2,023,280` bytes,
  two metadata files, eight install-surface files, all seven retail hashes
  fenced, the reviewed extractor present, and no private data, retail data,
  symlinks, or undeclared files. Runtime validation passed with `50` modules
  and `31` APF capabilities.
- A supported untouched private source resolved `10,464` universal catalog
  items, `96` specialist uniforms, and all `408` uniform/equipment records.
  Registry validation passed at `61` global / `31` APF capabilities, with
  APF cards split 7 Editable, 7 Preview, 3 Export-only, and 14 Coming Soon.
- The complete source suite passed `528/528` tests before sealing.
- Spark Hands inspected fresh Stadium (`0x03800035`) and Audio (`0x04000035`)
  windows on isolated `DISPLAY=:99`. Both showed the exact `Alpha 13` badge.
  Stadium displayed the 116-mesh / 328-draw / 113-material / 13-shader-family /
  737-texture-identity boundary and a gray **Replace (locked)** action. Audio
  displayed all `47,814` semantic rows and the XMA replacement boundary. No
  clipping, overlap, or footer obstruction was found; the user's active desktop
  and pointer were not used.
- The independent extraction is retained at
  `/tmp/apf-alpha13-extract.gZubBi`. The published tree, archive, checksum
  sidecar, and extracted package remain immutable; this exact receipt was added
  only to the source documentation after sealing.

## 0.1.0-alpha.12 — 2026-07-18

- Replaced the generic Stadium asset page with the first honest Stadium Studio.
  It inventories all 93 exact `stadium` SCNE records and prepares a private,
  source-hash-fenced glTF only when the modder opens a scene.
- Added a dependency-free 3D viewer with orbit, pan, zoom, reset, triangle
  sampling, surface picking, and retained glTF mesh/primitive plus APF
  scene-node/source-mesh identity. The first real-source smoke loaded 116
  meshes, 112,158 vertices, and 68,669 source triangles.
- Added same-outer package inspection beside the 3D view. TXTR records use the
  existing private PNG preview/export route and every other related record
  keeps exact raw export. A selected surface never auto-claims a texture:
  material/TXTR ownership is explicitly unresolved and Replace/Revert remain
  disabled.
- Added non-overwriting private 3D Scene ZIP export containing glTF, its binary
  buffer, and a source-bound manifest. Derived caches and exports remain private
  retail-derived outputs and never enter a shareable project or public package.
- Improved workspace tabs with extra leading and horizontal breathing room.
  Audio technical identity now retains a useful minimum height; physical bank
  selection hides Play and labels shortlist actions as single-sound-only, so a
  multi-cue `.bin` cannot visually resemble a playable cue.
- Added eight stadium-focused tests and extended the physical-bank UX test.
  The complete cross-title Mod Studio suite passes `512/512`.

### Release receipt

- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.12-linux-x86_64/`
- Linux archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.12-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.12-linux-x86_64.tar.gz.sha256`
- Size: `462,020` bytes
- SHA-256:
  `2cc7a3178f0afff81ebd402d308b75fbaa272075003ee2630f42c2794c678ccf`
- Stage and independent extraction are identical: `71` files, `14`
  directories including root, `1,976,945` file bytes, `22` executables, zero
  links/special files, and `85` archive members. Their shared path/mode/size
  inventory SHA-256 is
  `120ccb4207026a4bfeedb6fe0af976c7bd4ba51a03102b5016faa579d3a02b6c`.
- Both trees passed retail-free release, 49-module source-free runtime,
  supported private-source runtime, registry, desktop, Bash, and isolated
  installer lifecycle gates. Derived `.gltf`, `.glb`, `.bin`, and `.zip` files
  are structurally excluded.
- Spark Hands verified the 93-scene viewer, first 116-mesh scene, nine-record
  package inspector, and 2048×1024 package preview on isolated `DISPLAY=:99`.
  It also caught that a disabled primary Replace button retained the orange
  ID-specific style. Alpha.12 is immutable; the next build fixes disabled
  primary/secondary/utility/build/launch styling globally. Full detail is in
  `APF2K8_STATUS.md`.

## 0.1.0-alpha.11 — 2026-07-18

- Expanded Uniforms & Equipment from the 96 specialist writer cards to the
  complete 408-record category. **Editable Materials (96)** preserves the four
  bounded writer families; **Additional Assets (312)** adds 275 TXTR, 24
  NumberFont, 11 NameFont, and two SCNE records with scoped type filters,
  100/100/100/12 paging, previews where decoded, and exact export. Archive
  identity excludes the writer targets from the second tab, so no asset is
  hidden or duplicated.
- Added a retail-free 38-row Sliders & Gameplay inspector: all 21 named stock
  sliders plus 17 retained draft-lineage weights. The UI explicitly says that
  current profile values, final catch/drop causality, a live APF draft selector,
  out-of-range safety, and writers are not proved.
- Rebuilt Scorebug & Presentation as three full-height workspaces:
  **Presentation Map** (seven scene components plus the `digital_font`
  boundary), **Digital Font**, and **Raw Presentation Assets**. The semantic map
  ships as a small reviewed metadata projection with no report dependency,
  executable address, retail hash, or game payload.
- Named all 19 physical external XMA1 banks from their 20 exact source-owned
  AUSB descriptor links. They are routed into Audio as `XMA1_BANK` rows and
  include `jukeboxmusic.bin`, `jukebox22.bin`, `lines.bin`, `players.bin`, and
  `teams.bin`; the shared `cwdloop.bin` ownership remains deduplicated.
- Added typed **Export original bank .bin** with exact name/size/owner checks,
  bounded streaming, progress, exclusive atomic publication, source
  preservation, and existing-path/symlink refusal. Physical banks never enable
  Play, Replace, complete-sound ZIP, or shortlist actions; their AUSB substreams
  remain the playable/exportable sounds.
- Corrected playable-row wording to **XMA available · WAV/Play when verified**.
  The source-wide inventory does not falsely generalize a decoder sample into a
  promise that every XMA payload will decode.
- Focused Uniform/Product-Findings and Audio slices pass `14/14` and `52/52`;
  the complete cross-title Mod Studio suite passes `507/507`. A clean untouched
  source resolves 10,464 universal items, 408 uniform records, 47,814 semantic
  Audio rows, 19 physical banks, and 20 descriptor owners.
- No retail game bytes enter the package or a project. Raw `.bin`, XMA, WAV,
  PNG, ZIP, and semantic exports are private outputs from the user's own copy.
  APF audio replacement remains disabled until a validated distributable XMA1
  encoder, cue/loop ownership, and reversible writer all exist.

### Release receipt

- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.11-linux-x86_64/`
- Linux archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.11-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.11-linux-x86_64.tar.gz.sha256`
- Size: `428,574` bytes
- SHA-256:
  `66b7ecbf1d951d2353832ace3750fbcc067959d11e973f985e35cb39eaa7e7fe`
- Stage and independent extraction are byte-, size-, and mode-identical: `68`
  files, `13` directories including the root, `1,840,704` file bytes, `22`
  executables, zero links/special files, and `81` archive members. Their shared
  mode/size inventory SHA-256 is
  `833421de12a6a461d65fbee109dad504604395849ab3ec43a32659118b30f859`.
- Both trees passed retail-free release, 46-module source-free runtime,
  supported private-source runtime (`10,464` universal assets / `96` writer
  uniforms / `408` total uniforms), registry, desktop, all-four-script Bash,
  isolated install/update/uninstall, and repeated post-runtime gates.
- Spark Hands verified the sealed build on isolated `DISPLAY=:99`: the 408-row
  Uniforms split, 38-row Gameplay map, eight-row Scorebug map with 128×128
  digital-font writer, 25 raw presentation assets, 47,814-row Audio inventory,
  and single filtered 776.4 MB `lines.bin` physical bank all rendered. No
  emulator, export/edit, active desktop, or user pointer was used. Minor tab
  leading-glyph/padding and dense-text ellipsis are retained honestly in the
  detailed `APF2K8_STATUS.md` receipt and queued for the next source build.

## 0.1.0-alpha.10 — 2026-07-18

- Added a complete **Review selected** Audio workspace. It displays up to 256
  hand-picked sounds in exact insertion order with local 100-row paging,
  Play/Stop, individual export, remove, Clear, and cross-page **Move up** / 
  **Move down** controls. Reordering changes the exact bundle and
  `playlist.m3u8` order. Returning restores search, kind, role, source/bank,
  page, and selection; last removal, Clear, and model reload exit cleanly.
- Review is decoded-row UI state only. Add-page and matching-filter export are
  disabled while reviewing, and Review/reorder/navigation emit no project,
  modification, or crash-recovery event. The shortlist still contains no audio
  bytes and never enters `.apf2k8mod`.
- Added **Soundtrack album (15)**. It opens the 15 source-owned
  `jukeboxmusic` 48 kHz stereo masters by default and exposes the 15 matching
  `jukebox22` 22.05 kHz mono companions through one selector while preserving
  track number. The view activates only for the exact proved 15-by-15 index,
  duration, channel/rate, pairing-field, and export-identity contract. Artist
  and title stay explicitly **Unknown**; no commercial metadata is guessed.
- Added private **Export Text Sheet** / **Import Text Sheet** actions to the
  Universal Text inspector. Export writes all 2,413 owned TXT/STRG allocations,
  source binding, allocation limits, coordinates, originals, and current
  replacements to a non-overwriting UTF-8 CSV. Import validates the complete
  sheet before staging any row, supports `auto`, `replace`, `revert`, and
  `skip`, and applies every accepted change as one Undo action.
- Text Sheet cells use a required leading apostrophe so spreadsheet programs
  cannot interpret game text as formulas. Imports fail closed on a different
  source hash, changed ownership/coordinates/originals, duplicate or unknown
  targets, protected allocations, NULs, UTF-16 overflow, malformed/linked/
  oversized CSVs, or a late invalid row. Only authored replacement text enters
  project/recovery state.
- A Text Sheet necessarily contains original strings from the user's own game,
  so it is a private editing file—not a shareable project or release artifact.
  `.apf2k8mod` remains replacement-only and the public package remains
  retail-free.
- Headless gates pass `20/20` focused Audio/Text-Sheet tests, `20/20` focused
  recovery tests, and `115/115` APF-pattern tests; the complete cross-title Mod
  Studio suite passes `489/489`.
- The package was created headlessly. Its separate post-seal Spark Hands gate
  then passed on isolated `DISPLAY=:99`: fresh source-ready windows visibly
  showed `Alpha 10 • retail-free`, both Text Sheet actions and allocation-limit
  UI, all shortlist Review/reorder controls, the 15-row stereo Soundtrack
  album, and the switch to the 15-row mono companions. No clipping, overlap,
  spacing collapse, or footer obstruction was found; no emulator or active
  user desktop/pointer was used.

### Release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.10-linux-x86_64/`
- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.10-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.10-linux-x86_64.tar.gz.sha256`
- Size: `412,489` bytes
- SHA-256:
  `c72d53f052fb843d01e259e50fa7628b5b56f21212588c6545757554e4c0fd28`
- Test gates: `20/20` focused Audio/Text-Sheet, `20/20` focused recovery,
  `115/115` APF-pattern, and `489/489` complete cross-title Mod Studio tests.
- Stage and independent extraction are byte-, size-, and mode-identical: `66`
  files, `13` directories including the root, `1,775,875` file bytes, `22`
  executables, zero links/special files, and `79` archive members. Their shared
  mode/size inventory SHA-256 is
  `d0a0cd009f94db5237fc22e1f03c1befeee7612da74c0c01f14b113e1c131ae8`.
- Both trees passed retail-free release, 45-module source-free runtime,
  supported private-source runtime (`10,464` universal assets / `96` uniforms),
  registry, desktop, all-four-script Bash, isolated install/update/uninstall,
  and repeated post-runtime release gates.
- Alpha.9 remains unchanged at
  `046f7463a8eb7a13b78e4a7b53eff2e310a2594e5d4b4526378b8dfc1204b83d`.
- Isolated Spark visual verification passed after the headless seal. The exact
  observed controls and desktop-isolation boundary are recorded in
  `APF2K8_STATUS.md`.

## 0.1.0-alpha.9 — 2026-07-18

- Added normal **Open Recent Game** and **Open Recent Project** menus. APF ISO/
  XISO files and extracted game folders are both remembered, the newest eight
  entries are de-duplicated, missing paths remain visible but disabled with
  their full path in the tooltip, and projects stay disabled until their
  source game is loaded.
- Added source-bound crash recovery. Every authored edit, revert, Undo, and
  Revert All coalesces into a private replacement-only
  `unsaved-recovery.apf2k8mod`; an intentional zero-edit dirty document is
  recoverable too. The autosave is bound to the exact user-selected source path
  and recognized `0A` SHA-256, so an ISO extraction cache can never become the
  remembered source.
- Startup offers **Recover Edits**, **Not Now**, or **Discard Recovery**. The
  File menu also provides **Recover Unsaved Edits**. A recovered document is
  deliberately unnamed and dirty so the user must choose where to save a
  shareable copy. If the source moved, the app names the exact missing ISO or
  extracted folder instead of discarding the safe recovery project.
- Recovery writes serialize with every session mutation, source swap, project
  load/save, and build. In-flight edits coalesce; stale completions cannot be
  labeled as another source; failed source/project switches preserve the live
  dirty document and its recovery; successful Save/Discard cleanup affects only
  the matching source. A postponed recovery for another source is preserved
  rather than overwritten.
- Workspace metadata is a bounded, atomic, mode-`0600` JSON document containing
  paths and hashes only. Recovery uses the same validated `.apf2k8mod` writer as
  normal projects, never a second payload format. Empty and nonempty tests prove
  it contains user replacements/metadata but no retail bytes or preimages.
- The portable launcher now hands its exact validated private state directory
  to the app, including its guarded fallback, so launch diagnostics, recents,
  and recovery cannot silently diverge.
- Playable APF bank and hand-picked Audio ZIPs now include an ordered UTF-8
  `playlist.m3u8`; the manifest declares its path and entry count, and known
  durations are preserved. Original XMA1 and decoder-verified WAV exports retain
  their exact user-selected order. This is a local export from the user's own
  game, never a shareable project payload.
- Headless gates pass `20/20` focused recovery tests and `107/107` APF-pattern
  tests; the complete current cross-title product gate passes `468/468`.
- Spark Hands verified current alpha.9 window `0x09a0002b` at `1480×920` on
  isolated `DISPLAY=:99`. `Alpha 9 • retail-free`, all 14 sidebar categories,
  the complete header/footer, the nine-row File menu, **Open Recent Game** and
  **Open Recent Project** empty-state flyouts, and **Recover Unsaved Edits**
  were readable and unclipped. No recovery dialog appeared without a candidate,
  and the user's active desktop/pointer were never used.
- The exact package and clean-extraction receipts are recorded in
  `APF2K8_STATUS.md` beside the sealed archive checksum.

### Release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.9-linux-x86_64/`
- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.9-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.9-linux-x86_64.tar.gz.sha256`
- Size: `401,795` bytes
- SHA-256:
  `046f7463a8eb7a13b78e4a7b53eff2e310a2594e5d4b4526378b8dfc1204b83d`
- Test gates: `20/20` focused recovery, `107/107` APF-pattern, and
  `468/468` complete current cross-title tests.
- Stage and independent clean extraction are byte-, size-, and mode-identical:
  `65` files, `13` directories including the root, `1,726,822` file bytes,
  `22` executables, zero links/special files, and `78` archive members. Their
  shared mode/size inventory SHA-256 is
  `ffa61522d1a6e13cc30805ea37069d2a4fff7420a68cd7e867334fc8dc8c6d9c`.
- Both trees passed release, source-free and private-source runtime, registry,
  desktop-file, all-four-script Bash, and repeated post-runtime release gates.
  Runtime closure is `44` modules and `30` capabilities; the supported private
  source produced `10,464` universal assets and `96` uniforms with
  `private_source_verified=true`.
- The sealed alpha.8 archive was reverified unchanged at
  `7fe2198bebdf0f0f0c2114358b1174bfbc34507bf93678f559347c99c6f9003a`.

## 0.1.0-alpha.8 — 2026-07-18

- Turned `.apf2k8mod` files into normal active documents. The window title now
  distinguishes `Untitled*`, a dirty named project, and a clean named project;
  document dirty state is independent from the number of active replacements,
  so reverting the final edit leaves a visible, saveable zero-edit change.
- Added File-menu **Save Project** (`Ctrl+S`) and **Save Project As**
  (`Ctrl+Shift+S`). The existing header Save button uses the same dispatch:
  first save asks for a name, while later saves atomically update the exact
  remembered project without reopening the file dialog. A clean named project
  can still use Save As to create a replacement-only copy.
- Added protected expected-target fast-save. Missing, symlinked, non-regular,
  hardlinked, pathname-substituted, or externally changed targets fail closed,
  preserve foreign bytes, and direct the user to Save Project As. Every
  successful save refreshes the in-memory target identity; a stale identity
  cannot be reused.
- Project opening now validates into a candidate session, compares the project
  file identity before and after complete archive validation, and commits the
  new session only if both identities match. Failed project and source loads
  preserve the current path, identity, edits, and dirty state.
- Source switching, project switching, and closing now use a standard
  **Save / Discard Changes / Cancel** gate. Post-save switching and closing wait
  until the save worker has fully unregistered, avoiding a false “operation is
  still running” collision. Successful source replacement clears the active
  project; successful project save/load is clean.
- Audio browsing, playback, local export, filtering, and the alpha.7 shortlist
  remain non-authoring actions and never dirty a project. Audio replacement is
  still not claimed: the XMA1 encoder, cue/loop ownership, and reversible bank
  writer boundaries are unchanged.
- Added `9` focused active-document tests. The combined document/core/safety
  slice passes `36/36`, and the complete current cross-title gate passes
  `443/443`.
- Spark Hands verified source-ready alpha.8 window `0x0860002b` at `1480×920`
  on isolated `DISPLAY=:99`. `Alpha 8 • retail-free`, the source-ready header,
  all `14` sidebar categories, and every header control were readable and
  unclipped. The File menu showed Open Project (`Ctrl+Shift+O`), Save
  (`Ctrl+S`), Save As (`Ctrl+Shift+S`), and Quit (`Ctrl+Q`) without overlap or
  cramped spacing; Save and Save As were correctly disabled for a clean source
  with no active project.

### Release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.8-linux-x86_64/`
- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.8-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.8-linux-x86_64.tar.gz.sha256`
- Size: `392,574` bytes
- SHA-256:
  `7fe2198bebdf0f0f0c2114358b1174bfbc34507bf93678f559347c99c6f9003a`
- Unit gates: `9/9` active-document tests, `36/36` focused
  document/core/safety tests, and `443/443` complete cross-title tests.
- Visual gate: source-ready alpha.8 window `0x0860002b` passed at `1480×920` on
  isolated `DISPLAY=:99`, including the complete File menu and correct clean
  Save/Save As disabled states.
- Stage and independent clean extraction: `65` files, `13` directories
  including the root, `1,675,159` file bytes, `22` executables, and zero links.
  Both passed release, source-free and private-source runtime, registry,
  desktop, all-four-script Bash, and repeated post-runtime release gates.
- The archive has `78` members. Runtime closure is `44` modules and `30`
  capabilities; the supported untouched private source produced `10,464`
  universal assets and `96` uniforms with `private_source_verified=true`.
- The sealed alpha.7 archive was reverified unchanged at
  `e031891a7b610d6462ba05c6053f21a4641e77beb318ac78cb7f77de812b52d7`.
- Recent-project menus and crash-recovery autosave are deliberately deferred to
  alpha.9. Alpha.8 preserves normal explicit Save/Save As behavior and does not
  hide that remaining convenience gap.

## 0.1.0-alpha.7 — 2026-07-18

- Added a session-only **Audio shortlist** for collecting sounds across
  unrelated searches, pages, roles, and banks. Users can add/remove the current
  playable row, add every playable row on the current 100-row page, clear the
  list, and see both an exact `Selected N / 256` counter and row badges.
- **Export selected sounds** reuses the existing transactional bundle writer,
  preserves shortlist order, defaults to original XMA1, offers
  decoder-verified WAV explicitly, and refuses an over-256 page without making
  a partial selection.
- The shortlist contains only in-memory decoded row identities. It clears when
  the loaded model changes and never enters a project or release artifact.
- Added focused offscreen Qt coverage for cross-filter persistence,
  deduplication, page addition, the all-or-nothing 256 cap, model reset, badges,
  ordered forwarding, and the original-XMA default.
- The complete cross-title product gate passes 428/428 tests.
- Spark Hands loaded the current Audio page on isolated `DISPLAY=:99` at
  1480×920. All 47,795 decoded rows were present, and the shortlist heading,
  Add/Remove, Add this page, Clear, `Selected N / 256`, export, matching-export,
  and replacement-boundary controls were readable and unclipped.

### Release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.7-linux-x86_64/`
- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.7-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.7-linux-x86_64.tar.gz.sha256`
- Size: `391,496` bytes
- SHA-256: `e031891a7b610d6462ba05c6053f21a4641e77beb318ac78cb7f77de812b52d7`
- Unit gate: the complete current cross-title product suite passes `428/428`.
- Visual gate: Audio loaded all `47,795` decoded rows at 1480×920 on isolated
  `DISPLAY=:99`; every shortlist control was readable and unclipped.
- The original stage and clean extraction each contain `65` files, `13`
  directories including the root, `1,649,360` file bytes, and `22`
  executables. Both passed release, source-free runtime, private-source runtime,
  registry, desktop-entry, all-four-script Bash syntax, and post-runtime release
  gates.
- Runtime closure is `44` modules and `30` capabilities; the untouched private
  source produced `10,464` universal assets and `96` uniforms with
  `private_source_verified=true`.
- The archive contains `78` members. Stage, archive, and extraction contain no
  symlinks, hardlinked files, caches, retail bytes, or private payloads. The
  sealed alpha.6 archive was reverified unchanged.

## 0.1.0-alpha.6 — 2026-07-18

- Added an explicit **Audio source / bank** filter above the 47,795-row decoded
  catalog. It exposes Standalone AUDO plus every AUSB bank with its playable
  count and stable outer/inner coordinates, so duplicate bank names cannot
  alias each other.
- Search, decoded kind, broad role, and source filters now intersect for paging,
  decoded JSON/CSV export, and **Export matching sounds**. Choosing
  `jukeboxmusic` or `jukebox22` isolates its descriptive bank row and 15
  playable soundtrack entries; the transactional bundle action receives the
  exact 15 export identities.
- Moved the Audio kind/role/source controls onto their own filter row and added
  `Ctrl+Shift+B` to focus the bank selector. This keeps the search/export row
  readable at ordinary laptop widths.
- Spark Hands verified the separate two-row Audio controls on isolated
  `DISPLAY=:99`: search/export, kind, role, source, table, and detail actions
  remain fully readable with no clipping or overlap.
- The complete cross-title product gate passes 419/419 tests. Alpha.6 is a new
  immutable checkpoint; alpha.4, alpha.5, and their checksums remain unchanged.

### Release receipt

- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.6-linux-x86_64.tar.gz`
- Size: `388,619` bytes
- SHA-256: `9710308dc637c7129c35d7e944726f4b3ef3f4274a0cb510c11510ab7230dcae`
- The exact 65-file / 13-directory stage contains `1,633,476` file bytes.
  Its 44-module runtime closure, 30 capabilities, per-user install lifecycle,
  and untouched private-source inventory (10,464 universal assets / 96
  uniforms) passed before archiving and again after clean extraction.
- The adjacent `.sha256` sidecar is the authoritative archive checksum.

## 0.1.0-alpha.5 — 2026-07-18

- Added transactional **Export matching sounds** for any 1–256 playable rows
  selected by the Audio search, record-kind, and role filters. This closes the
  practical bulk-export gap for bounded slices of the 11,797-row `players`,
  31,826-row `lines`, and 1,498-row `teams` speech banks without pretending the
  unresolved XMA1 replacement path is writable.
- Matching bundles may mix AUDO and AUSB substreams, use collision-free numbered
  filenames, include a role/bank/coordinate/rate/channel/duration manifest, and
  publish only after every member succeeds. Original XMA1 is the default;
  verified-WAV mode leaves no partial ZIP if any decode fails.
- Corrected individual Audio export so its default filename/filter is original
  `.xma`, matching the product's documented safe default. WAV remains available
  explicitly after full decoder verification.
- Moved Audio into full-height **Audio Browser** and **Raw Audio Assets** tabs.
  The complete universal raw inventory remains one click away while Play,
  individual export, bank export, filtered export, and the honest replacement
  boundary no longer compete with a second vertical browser for height.
- Spark Hands checked the current build on isolated `DISPLAY=:99`. The broad
  47,795-row view shows filtered export as clearly disabled; its own full-width
  row and the replacement row are fully separated with no clipping or overlap.
  The enabled 1–256 state is covered by the focused offscreen Qt interaction
  test without opening an export dialog on the user's desktop.
- Passed all 72 APF product tests before creating the non-overwriting alpha.5
  package. The archive's adjacent `.sha256` sidecar is the authoritative
  checksum receipt.

### Release receipt

- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.5-linux-x86_64.tar.gz`
- Size: `386,254` bytes
- SHA-256: `05c4e7132167f0167ce71bc7b244fa6c3ca9faa2b75dab7433617f97556515a8`
- All 72 matching APF product tests passed.
- The 65-file stage, its 44-module runtime closure, per-user install/update/
  uninstall lifecycle, and untouched private-source inventory all passed before
  archiving. A clean extraction repeats the same gates before publication.
- The adjacent `.sha256` sidecar is the authoritative archive checksum.

## 0.1.0-alpha.4 — 2026-07-18

- Turned all four decoded English text banks into one bounded text editor.
  Menus & Text now places 2,413 underlying TXT/STRG pool allocations before the
  1,572 TXT reference rows, marks 2,410 allocations Editable, keeps the two
  required `INVALID TEXT` fallbacks and one zero-capacity STRG allocation
  read-only, and shows each allocation's UTF-16 limit plus shared-consumer count
  before Apply. The old TXT-only pool rows are deduplicated rather than shown a
  second time.
- Added individual text Replace/Revert, modified badges, Undo/Revert All,
  canonical user-authored JSON payloads in `.apf2k8mod` projects, and grouped
  build composition when several strings share outer 185, 526, 810, or 1127.
  Relative pointers, H7A compression, IFF/footer structure, and the fixed outer
  sizes are rebuilt without writing the selected source.
- Completed a live untouched-source build proof: `SOUNDTRACK` became
  `MOD MUSIC`, only outer 1127 was compiled, the output was a complete separate
  game folder, and the source hash stayed unchanged. A bounded trace later
  showed that the 2K Beats playlist does not directly consume that allocation,
  so the product does not attach it to that screen or continue blind hunting.
- Closed the universal-text runtime spot check with an unmistakable target:
  outer 1127 / inner 0 / pool 11 changed from `Artist Biography` to
  `MOD BIOGRAPHY`, and Xenia rendered the exact new header on the 2K Beats
  biography page with its body and portrait intact. This proof is limited to
  that allocation; it does not invent screen ownership for the other editable
  TXT/STRG rows.
- Added compact text-detail spacing and keyboard focus shortcuts (`Ctrl+F` for
  decoded search, `Ctrl+Shift+K` for record kind) after isolated Spark QA found
  two minor clips in the first pass.
- Turned the complete APF audio inspector into a modder-facing browser: 2,261
  standalone `AUDO` sounds, 20 `AUSB` bank records, and all 45,514 bank
  substreams remain source-derived and individually exportable. Rows now show
  role, XMA1 format, sample rate, channel count, duration, archive location, and
  actionable export state instead of requiring users to read raw JSON.
- Added conservative role taxonomy and filtering. Exact AUSB bank names drive
  Soundtrack & Music, Commentary & Speech, Stadium PA & Chants, Presentation,
  and Diagnostic & Ambient; standalone names use visibly labeled broad
  heuristics with an unknown fallback. No role label changes write eligibility.
- Paired the 15 `jukeboxmusic` stereo streams with the 15 `jukebox22` mono
  companions by exact source index and matching duration. The UI calls them
  Soundtrack Track 01–15 and explicitly leaves artist/title unknown instead of
  guessing copyrighted track metadata.
- Added Play/Stop through session-private, decoder-verified PCM WAVs. Preview
  names come only from bounded coordinates, symlinks and unreceipted/tampered
  files fail closed, no shell is invoked, and the entire preview directory is
  removed when the loaded-game session closes.
- Added complete-bank ZIP export for AUSB banks containing 1–256 substreams,
  including both 15-track soundtrack banks. Original XMA1 is the safe default;
  verified-WAV mode aborts without publishing a partial ZIP if any decode fails.
- Kept Replace visibly disabled with the exact boundary: the public/local
  toolchain has XMA1 decoders but no validated distributable XMA1 encoder, cue
  and loop ownership is incomplete, and no reversible bank writer exists.
  WMA/xWMA is not treated as an interchangeable encoding.
- Fixed catalog routing that had classified 157 crowd `TXTR`/`SCNE` and related
  visual resources as Audio. They now appear under Stadiums, including when an
  older private catalog cache is loaded; all true 2,261 `AUDO` and 20 `AUSB`
  records remain present.
- Added end-to-end editing for the exact `franchise.iff` inner-117
  `draft_logo`: source-derived 128×128 PNG preview/export, strict RGBA import,
  private original preservation, per-asset Revert/Undo, retail-free project
  persistence, and transactional `0A` build dispatch through the already-proved
  single-level BC3 writer.
- Kept the boundary narrow: no other logo or texture becomes editable, and the
  UI says the writer is offline-proved while franchise/draft runtime
  consumption remains unproved.
- Added JSON and CSV export for every decoded specialized inspector. The export
  follows the current search, kind, and (for audio) role filters, contains decoded rows rather than
  opaque archive bundles, never overwrites a destination, and remains outside
  shareable project/release artifacts.
- Removed the six-card display ceiling so every registry capability is visible.
  Moved all three uniform-selector capabilities to Team Identity alongside the
  1,120-row ownership inspector.
- Replaced ambiguous universal-browser `Export-only` wording with concrete
  action labels such as `PNG when decoded; raw ZIP always`, `Raw parts ZIP
  only`, and `Raw record only`.
- Updated runtime evidence: jersey asset 6 is corroborated in the Home/Away
  editor and pants has a positive Americans Away Uniform Type PANTS checker
  witness. Helmet, shoulder, `digital_font`, and `draft_logo` remain without a
  positive visible consumer proof.
- Added focused headless tests for exact-target gating, project retail-byte
  exclusion, writer dispatch, Revert, capability placement, card visibility,
  export labeling, and filtered semantic JSON/CSV output.
- All 69 matching APF product tests pass. The audio checks include an offscreen
  Qt control pass, metadata/role coverage, preview tamper/symlink/session cleanup,
  and all-or-nothing bank export. A live untouched-source headless audio smoke
  confirmed the exact inventory, paired soundtrack labels, one real private WAV,
  and one complete 15-stream soundtrack-bank ZIP. A separate live smoke
  resolved outer 810 / inner 117, generated the 128×128 RGBA preview, and
  compiled the original PNG through `apf_texture_patch/v1` into the exact
  913,408-byte fixed allocation without changing the source.

This checkpoint packages the universal-text, complete-audio-browser,
`draft_logo`, semantic-export, and capability-routing work above. The sealed
alpha.3 archive remains unchanged.

### Release receipt

- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.4-linux-x86_64.tar.gz`
- Size: `381,325` bytes
- SHA-256: `88fabc7bd1c167a60d6f943f9404366578070e168d3fe5d9d6989519ca3f9b93`
- All 69 matching APF product tests passed.
- The staged folder and a clean archive extraction independently passed the
  exact 65-file retail-free audit, 44-module source-free runtime and installer
  lifecycle, and untouched-source inventory result
  `capabilities=30 universal=10464 uniforms=96`.
- Archive inspection found 65 regular files, 13 directories, exact
  stage/extraction hash and metadata parity, and no links, special members,
  duplicate paths, case collisions, private runtime evidence, or retail game
  data.

## 0.1.0-alpha.3 — 2026-07-18

This checkpoint turns the APF-specific alpha into a directly installable
per-user Linux application and tightens the primary editing workspace without
changing the evidence boundary of any game asset.

- Added a root-level `install.sh`, `uninstall.sh`, and portable
  `APF-2K8-Mod-Studio.sh`, plus a top-level read-me so the extracted release has
  an obvious first action.
- Added a no-root Linux installer that re-runs the retail-free release audit,
  copies only exact allowlisted files, publishes from a sibling staging
  directory, and generates an absolute-path desktop shortcut and command.
- Added authenticated update and uninstall records. Colliding or externally
  changed shortcuts are refused or preserved; uninstall removes only its own
  program files and leaves projects, exports, caches, settings, and emulator
  data alone.
- Improved launcher errors to distinguish missing Python, PyQt5, Pillow, and a
  damaged application folder. State logs now follow `XDG_STATE_HOME`, use
  private permissions, and never require an active display for headless help or
  version checks.
- Extended the release and runtime gates to require and exercise the complete
  install, update, absolute launcher, and uninstall path in an isolated fake
  home directory without opening the GUI.
- Added `--tab` startup deep links for every one of the fourteen product
  categories, while keeping command-line help and version checks headless.
- Tightened the desktop shell's spacing, capability cards, search/filter rows,
  texture list density, footer hierarchy, and button sizing. Capability states
  now pair color with explicit symbols and words, transparent textures preview
  over a runtime-generated checkerboard, and clean assets expose a clearly
  disabled Revert action with a useful explanation.
- Kept Build Game Folder as the primary action and Xenia launch as a secondary
  action, matching the safe source → edit → build → play flow.

### Release receipt

- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.3-linux-x86_64.tar.gz`
- Size: `341,107` bytes
- SHA-256: `b74e2062b542d443c9fbe6fe1fbb8a4bfc9b1aad070aab6ac55226d5b50f592e`
- All 50 APF unit tests and Python compilation passed.
- The staged folder and a clean archive extraction independently passed the
  exact 62-file retail-free release audit, 42-module source-free runtime and
  installer lifecycle, and untouched-source inventory result
  `capabilities=30 universal=10464 uniforms=96`.
- Archive inspection found 62 regular files, 13 directories, exact stage/file
  hash parity, and no symlinks, hardlinks, devices, FIFOs, duplicate paths, or
  case collisions. No retail or private game data is present.
- Isolated visual QA on private Xvfb `:99` found no blocking or major defect in
  the fixed Uniforms screen; the active desktop `:0` was never used.

## 0.1.0-alpha.2 — 2026-07-18

This is the first APF-specific product and release-closure checkpoint. It
separates shippable application code from the retail-heavy research workspace.

### Newly available

- Added read-only recognition for the supported APF 2K8 USA ISO and complete
  extracted game tree, with an exact seven-hash source ledger.
- Added private ISO extraction through one size- and SHA-256-pinned
  `extract-xiso` binary distributed with its exact license.
- Added a live source-derived catalog covering 1,543 outer records, 1,473 IFF
  records, 70 non-IFF records, and 10,394 inner assets. The universal browser
  exposes 10,464 selectable items without shipping its generated catalog.
- Added 30 registry-driven APF capability cards across the complete sidebar.
- Added export/preview routing for textures, raw multipart resources, and all
  2,261 ordinary APF `AUDO` XMA1 resources. WAV export is attempted only when
  the local decoder verifies it.
- Added source-derived specialized inspectors for all 2,254 players, 40 teams,
  31 stadiums, 1,344 roster memberships, 1,572 localization records, one
  playbook with 163 formations/586 plays/4,948 route nodes, five director
  resources with 1,623 instructions, and all 1,120 uniform selector records in
  80 HOME/AWAY banks.
- Added exact export identities and on-demand XMA/decoder-verified WAV routes
  for all 45,514 substreams in APF's 20 `AUSB` banks and 19 external packet
  resources. A live export smoke passed for one `AUDO` resource and one `AUSB`
  substream.
- Added 96 uniform replacement targets: 24 jerseys, 24 pants textures, 24
  helmet mask textures, and 24 shoulder textures.
- Added `digital_font` export and replacement.
- Added strict, modder-facing PNG errors for dimensions, RGBA mode, pants alpha,
  helmet R/G mask transport, and digital-font alpha authoring.
- Added per-asset Revert, project-wide Revert, and Undo in the UI-independent
  session layer.
- Added retail-free `.apf2k8mod` project save/load. Projects contain replacement
  PNGs and metadata only, never original preimages or archive bytes.
- Added a transactional complete-game-directory builder. The source is never
  written, existing outputs are refused, and failed staging is removed before
  publication.
- Added a Linux desktop entry, scalable vector icon, and no-terminal launcher.
  Startup dependency failures use a desktop error dialog when available and
  keep diagnostics in the user's XDG state directory.

### Release safety

- Added an exact-file release allowlist. There are no directory wildcards.
- Added a fail-closed release audit rejecting all seven known retail hashes,
  APF game filenames, ISO/XEX/archive/media extensions, container magic,
  embedded byte arrays, private manifests, reports, exports, glTF, audio,
  screenshots, emulator state, caches, runtime evidence, `__pycache__`,
  symlinks, hardlinks, special files, world-writable files, and undeclared
  paths.
- The only allowed executable is the exact reviewed 56,584-byte Linux
  `extract-xiso`; its SHA-256 and mandatory license are pinned independently.
- Added a source-free runtime closure check that imports every APF product and
  writer module, validates the 30 capability cards, and round-trips a synthetic
  retail-free project without opening a GUI.
- Added an optional private-source runtime mode. With `--source`, it must report
  exactly `capabilities=30 universal=10464 uniforms=96` while keeping generated
  indexes in a temporary private cache.
- Completed the post-alpha core safety review with 30 passing APF tests. The
  hardened routes now stream large exports in bounded chunks, preserve files
  created concurrently at export/project publication time, validate existing
  content-addressed cache entries, reject duplicate project targets and ZIP
  members, constrain project metadata to typed scalar coordinates, remove
  failed import/build staging, refuse builds inside the source tree, and reject
  symlinked projects, emulator executables, and Xenia log destinations.
- Build publication now requires an atomic no-replace directory primitive. A
  platform/filesystem without that guarantee receives a clear refusal rather
  than a racy fallback.

### Honest capability limits

- Jersey asset 6 is the only uniform asset with positive on-screen runtime
  evidence so far. Pants, helmet, shoulder, and `digital_font` are currently
  bounded offline writers, not claimed visual proofs.
- Uniform selector banks are shared. The current 96 editable textures do not
  imply 40 teams each own four unique assets.
- Jersey and shoulder textures have shader/material-mask behavior that is not
  yet fully named. The app exposes channel caveats instead of presenting them
  as ordinary final-color bitmaps.
- APF text banks, roster identity, player names/numbers, team logos, field art,
  Stadium Studio texture ownership, scorebug composition, franchise state, and
  PLAY route semantics remain browse/export or Coming Soon according to the
  capability registry.
- XMA1 export is available; replacement is not. No legally distributable XMA1
  encoder has been integrated.
- The builder publishes an extracted Xenia game folder. Rebuilt ISO output and
  original-hardware support are not claimed.

### Packaging commands

From a fresh stage containing only the APF allowlist entries:

```bash
python3 packaging/check_apf2k8_mod_studio_release.py /path/to/apf-stage
python3 /path/to/apf-stage/packaging/check_apf2k8_mod_studio_runtime.py
python3 /path/to/apf-stage/packaging/check_apf2k8_mod_studio_runtime.py \
  --source /private/path/to/All-Pro-Football-2K8-USA.iso
```

The first two commands require no retail source. The third is an optional
private integration check and never makes the selected source part of the
release.

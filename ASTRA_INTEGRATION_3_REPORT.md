# Astra integration 3

Date: 2026-09-05. Base: `19146ce` on `local/stack-beta-61`. No push.

Momentum, defensive try and the initial corner deep-zone cap are integrated with
the complete beta-61 allocator stack, Build, Gameplay Patches and both release
closures. All four new options default to Retail/off in every preset and remain
labelled experimental/unwitnessed. Both requested real builds passed and their
images were deleted after receipts were saved.

Defensive try implements a temporary diagnostic team tally only. Its retail
box-score row and persistent player, season and franchise category are NOT
implemented. No Xbox or xemu gameplay witness is claimed for any new option.

## Delivery and provenance

The supplied worktree has read-only Git metadata. The initial bundle fetch
failed with `cannot open FETCH_HEAD: Read-only file system`. The authorized
fallback uses writable metadata at `.scratch/integration3/repo/.git`, this same
worktree, and explicit file paths for staging and commits. The files remain in
place; the original branch metadata stays unchanged. Delivery is
`.scratch/integration3.bundle`, based on `19146ce`. The brief, the pre-existing
untracked star fixture, private images, caches and scratch logs are excluded.

The imported sources are Momentum `f56b8ce` from `momentum-build.bundle`, defensive
try `b807489` from `r61b-defensive-2pt-build.bundle`, and zone drop `b363e17` from
`astra/r61b-cb-deep-zone-build`. Their shared-file conflicts were resolved against
the integration-2 implementation, preserving every owner and all existing WIRING
content. The unpublished scratch imports are consolidated with the final
integration so that intermediate conflict resolutions are not delivery states.

A direct explicit-path commit also failed because `index.lock` is read-only;
its output is retained in `.scratch/integration3/git-commit-attempt.log`.
The final consolidated commit uses 54 explicit paths, including this report.
Bundle verification and a fetch into independent scratch metadata are recorded
in `.scratch/integration3/bundle-verify.log`. The fetched commit and tree must
match the delivery commit. No push is performed.

## Allocator capacity and ownership

The complete request union includes the boot logo, relocated kickoff, runtime
scorebug, defensive try, Momentum, zone drop and 200-song read-only music
metadata. `layout()` and `reservations()` produce the following final map.

| Region | Start VA | Raw offset | Capacity | Requested bytes | Alignment bytes | Unused tail |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| RX 1 | `0x14BA000` | `0xB77000` | 4,096 | 4,037 | 27 | 32 |
| RW 1 | `0x14BB000` | `0xB78000` | 4,096 | 3,242 | 6 | 848 |
| RX 2 | `0x14D9000` | `0xB89000` | 4,096 | 2,464 | 0 | 1,632 |
| Music RO | `0x14BC000` | `0xB79000` | 65,536 | 65,536 | 0 | 0 |

| Owner | Code VA | Code bytes | State VA | State bytes |
| --- | --- | ---: | --- | ---: |
| Boot logo | `0x14BA000` | 690 | none | 0 |
| Relocated kickoff | `0x14BA2C0` | 1,939 | `0x14BB000` | 10 |
| Runtime scorebug | `0x14BAA60` | 1,408 | `0x14BB010` | 128 |
| Defensive try | `0x14D9000` | 1,440 | `0x14BB090` | 1,040 |
| Momentum | `0x14D95A0` | 944 | `0x14BB4A0` | 2,064 |
| Initial corner deep-zone cap | `0x14D9950` | 80 | none | 0 |

The 6,501 code bytes require a second RX page. The 3,242 state bytes fit one RW
page. No allocation crosses a page, no state occupies `.text`, and no owner uses
an unreserved address. All existing logo/kickoff/runtime allocations retain their
VAs when the three new owners join that complete request set. Smaller legacy
layouts remain byte-identical. Installed request sets remain immutable; changing
one requires a rebuild from the base. Exact replay is byte-identical.

The fixed music VA and raw offset remain unchanged. The strict byte-granular
absolute/relative reference scan rejected the first thirteen candidate pages
beyond music, including nine encodings at `0x14CC000`. The selected `0x14D9000`
page has zero hits. The virtual gap after music stays unmapped. The file gap is
zero until the separate read-only metadata owner fills it. With overflow, both
metadata-free and metadata-filled files are 12,099,584 bytes; legacy two-page
files remain 12,029,952 bytes.

All 22 retail section descriptor locations and their VA/raw mappings stay fixed.
The existing relocation of section names and counters is retained. The additional
RX descriptor and optional RO descriptor reclaim the old library-table bytes.
All 160 pinned library bytes move from header offsets `0x904..0x9A4` to the
allocator's owned header padding at `0xF60..0x1000`; the three library pointers
move by the same delta. The retired logo area is not used for this metadata.
The version-2 directory is canonically compressed, bounded on decompression,
checks both RX pages together, and pins the relocated library bytes separately.
Section digests, zero initial state, padding and exact owner code remain checked.

Evidence: `.scratch/integration3/capacity.json`, `capacity-final.log`,
`page-search.json`, and both final XBE gate logs. The evidence reports empty
`encoded_references` and `manifest_overlaps` arrays. Both gate classes compose
ALL owners, repeat the complete gate suite in reverse installation order, and
assert byte-identical results. Music remains read-only in both orders.

## Wiring and product decisions

- BuildPlan carries integer `momentum=0`, `momentum_contact=False`,
  `defensive_try=False` and `zone_drop_cap=False`. Availability includes each
  backend and the allocator. New selections imply allocation and use the final
  growth phase, after ordinary executable and resource passes.
- The dispatcher reserves the complete selected union before installing owners.
  Defensive try uses its required adapter; relocated kickoff, runtime scorebug,
  Momentum, zone drop and metadata then fill their owned allocations. Runtime
  resource installation receives the full extra request set. Its paired resource
  receipt survives the later feature pass. The existing outer transactions publish
  only after the complete operation succeeds.
- Both readers and both writer status dictionaries expose Momentum, contact,
  settings, defensive try, zone-drop state and zone-drop settings. Exact replay
  validates the requested configuration; a changed level or foreign bytes refuse.
- Positive Momentum selects native acceleration and disables a newly requested
  legacy ramp. Build and dispatcher receipts record
  `legacy_accel_ramp_disabled_by_momentum_profile`. Already recognized legacy
  source bytes remain supported by the backend. The corrected legacy help acknowledges existing native acceleration and the
  controller-specific scope of the extra envelope.
- Build and Gameplay Patches offer Retail (0), Light (25), Medium (50) and Heavy
  (100), retaining the last positive integer when toggled. An installed unusual
  integer is displayed honestly. Retail clears and disables contact. Selecting
  Momentum clears the legacy checkbox and records the decision in recipe notes.
  The contact explanation appears only when selected. Every new Build caption
  is at most 60 characters; PATCHES retain Retail/Patch controls and honest help.
- Studio capability navigation routes all three new records to Gameplay. The
  release adds four product modules, three capability documents and three handoff
  reports. The reviewed provider closure is 177 files. The shared registry has
  83 records, including 45 NFL 2K5 records. Coverage accounting is 78 covered,
  5 deferred and 53 unique validators. The integrated validator lists 20 suites.

## Final manifest

The manifest generator ran alone after the final product-source edits, then
`packaging/repin.py --apply` reported zero updates. No fingerprinted source was
changed afterward. The command followed integration 2, using the local private
USA executable and XISO:

```sh
PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 \
python3 tools/nfl2k5_cave_oracle.py manifest "$NFL2K5_RETAIL_XBE" \
  --xiso "$NFL2K5_RETAIL_XISO" --work-dir .scratch/oracle-work \
  --json data/nfl2k5_cave_reservations.json
python3 packaging/repin.py --apply
```

The two environment variables denote the supplied local retail files, not
shipped assets. The manifest contains 8,207 reservations, 85 observed XBE writer
calls and 82 source fingerprints, with section digests verified. SHA-256:
`4ae8ae9418617df365199332d7966bbce5254db2e92c90134b1c31abd3c8f4d7`.
It separately records the actual experimental preset and the full dormant-owner
union, including 200-song metadata. Its 21,798,912-byte `stack_image_size` is the
mapped virtual image size, not the file size. Named children come from the final
combined allocation map; all owned-page coverage remains present.

The dormant seven-on-seven practice-book attempt retains the known refusal:
`refused: the practice book is foreign, not retail; refusing`. The experimental
build already recoded that book. This attempt changes no XBE bytes; its executable
owner is recorded, separate recoding suites cover the supported source, and all
presets keep this dormant feature off. Logs: `manifest.log` and
`repin-after-manifest.log` under `.scratch/integration3/`.

## Real build receipts

Both builds used the supplied private USA XISO. The witness adds
`xbe_space=True`, `kickoff_relocated=True`, `scorebug_runtime=True`,
`music_policy="jukebox_menus"`, `music_unlock=True`, `defensive_try=True`,
`zone_drop_cap=True`, `momentum=100` and `momentum_contact=True` to Experimental.
UserList and a personal music library remain unselected. The full 200-song RO
metadata union is separately covered by capacity, manifest and both-order gates.

| Build | Image bytes | XBE bytes | Seconds | Result |
| --- | ---: | ---: | ---: | --- |
| Experimental preset | 6,519,656,448 | 12,029,952 | 132.59 | PASS; image deleted |
| Full opt-in witness | 6,519,726,080 | 12,099,584 | 142.04 | PASS; image deleted |

| Step | Experimental | Witness |
| --- | --- | --- |
| xbe | completed | completed |
| position_pools | applied | applied |
| depth_chart_rows | applied | applied |
| kickoff_alignment | applied | applied |
| depth_roles | applied | applied |
| screen_timing | applied | applied |
| season_2026 | applied | applied |
| team_history | applied | applied |
| prospect_names | applied | applied |
| guardian_cap | applied | applied |
| scorebug_runtime | applied | applied |
| xbe_space and final new owners | not selected as a separate step | applied |

Experimental XBE SHA-256, exactly matching `preset_xbe_sha256`:
`7573bdf75f53ccc10fce4963a731a61f20e2b7066eb5f7c79b4784d6a9443534`.
Witness XBE SHA-256:
`09719fdfb0919b6203e2b07d2a23ee82a8a7a4ac146458e6ec11f4aa77a2cab4`.

All four new feature states are retail in Experimental and applied in the
witness; its Momentum settings read back 100/contact enabled. Both runtime hooks
and paired scorebug resources report applied. The witness has relocated kickoff,
jukebox-menus policy and unlock applied, and legacy acceleration retail, with the
normalization receipt true. Experimental retains the original legacy ramp.

The neutral resource-only scorebug reader reports foreign on the distinct
runtime collection; the dedicated runtime resource reader reports applied.
The retail-only disc-identity check calls the grown output unknown because both
XBE and pack 0 have moved/grown. It is a source eligibility check and does not
claim that these intentionally modified outputs are retail rebuild inputs.
The requested patch and resource postconditions pass independently.

Complete local receipts and inspections: `.scratch/integration3/experimental-receipt.json`,
`witness-receipt.json`, `experimental-summary.json`, `witness-summary.json` and
`real-builds.log`. The summary files record `image_deleted=true`; the two image
paths no longer exist. No rebuilt retail image is committed or distributed.

## Verification and failure accounting

The complete workflow loop ran all 341 standalone files with the `ci.yml`
per-file semantics:
`timeout -k 30 420`, offscreen Qt, disabled update checks and
`PYTHONFAULTHANDLER=1`. The isolated installer clears `PYTHONPATH` with
`env -u PYTHONPATH`; every other file receives the repository root. The
large-evidence sentinel is present, so no lean-checkout file is omitted.

```text
SUMMARY: files=341 passed=337 failed=4 skipped=0 tests=4179
```

The raw output is retained at `.scratch/integration3/ci.log`; individual logs
are under `.scratch/integration3/ci/`. The raw summary includes failures that
were corrected and rerun separately; it is not rewritten to hide them.

| Failed standalone file | Cause and final disposition |
| --- | --- |
| `test_apf_studio_installer.py` | Its source-text assertion still expected 80 shared registry records. Updated to the integrated count of 83. All 16 tests pass with `env -u PYTHONPATH` in `installer-rerun-final.log`. |
| `test_nfl2k5_crib_geometry_writer.py` | Missing developer-only `assets/intermediate/nfl2k5/models/4248_0105_phone.gltf`, the same integration-2 evidence gap. Four tests ran and two errored. This file is in CI's explicit lean-skip list; retained unchanged as the brief permits. |
| `test_product_catalog.py` | Expected IDs and category/global counts omitted the three new records. Added the exact supplied IDs and counts. The first rerun used the wrong namespace for defensive try; corrected it to `nfl2k5.gameplay_tuning_sliders.defensive_try`. All 9 tests pass in `product-catalog-rerun-final.log`; the first rerun log is retained separately. |
| `test_studio_shell_layout_qt.py` | Its exact Gameplay control list omitted the four new options, causing the same assertion to fail in both shell test classes. Updated that list; all 18 standalone tests pass in `shell-layout-rerun-final.log`. |

All three actionable failures have passing reruns. The sole remaining failure
is the permitted missing Crib geometry evidence audit. No file timed out, and no
file was omitted by the lean-checkout branch. The supplied untracked player-star
fixture was present, so its drawing tests ran. No assertion was removed to hide
an integration failure. The fixture-only CI corrections do not change any of
the 82 manifest source fingerprints or either real build output.

The post-manifest ownership checks pass: 24 memory-write tests, 28 cave-reference
tests, 28 cave-oracle tests, 13 allocator tests, 9 zone-drop tests and 7 new
integration tests. They cover both installation orders, full capacity, fixed old
VAs, permissions, metadata relocation, corrupt code/data/header/directory bytes,
reconfiguration refusal, source preservation, all four status dictionaries,
integer UI controls and preset defaults. Logs are `test_*-final.log` plus
`allocator-rerun-final.log` in `.scratch/integration3/`.

The updated registry validation command completed all 20 feature suites, with
its full output retained in `capability-feature-gates.log`:

```text
BETA61_VALIDATION files=20 passed=20 failed=0
```

Earlier integration failures and their resolutions are retained rather than
hidden by a rewritten summary:

| Check or attempt | Cause and disposition |
| --- | --- |
| Git import | Read-only FETCH_HEAD; used the expressly authorized scratch metadata/bundle fallback. |
| Shared-file conflict helper | A greedy conflict-marker expression truncated an intermediate merge; original blobs were restored and shared sections resolved manually. A remaining indentation error was corrected before integration testing. Consolidated delivery excludes these transient states. |
| Initial capacity probes | One RX page overflowed. Initial post-music candidates had encoded references; chose the first zero-hit page. An in-memory probe also retained the old manifest virtual extent; its probe document was corrected before final manifest generation. |
| Header relocation design | The retired logo area already has other beta-61 owners. Library metadata instead uses the allocator's owned directory padding; complete-stack tests verify this placement. |
| Initial zone-drop suite | Old manifest omitted the new owners. Full final regeneration resolves the coverage failure; 9 tests pass. Its old overflow expectation was also updated to prove the complete union fits two RX pages. |
| Gameplay panel fixture | Exact PATCHES key list lacked the four options. Updated expected contract; standalone rerun passes. |
| Beta-61 fixture, including first rerun | Runtime mock did not accept the full-union `extra_requests` argument. Updated mock signature; second rerun passes all 5 tests. |
| Provider integrity | New module closure and byte pins were stale. Reviewed four new roots, updated expected count to 177, repinned; all 7 tests pass. |
| Capability validation, including first rerun | Supplied defensive command was null, Momentum advertised an absent CLI, and new rows/counts were unsorted/stale. Used the working Python-callable backend contract, sorted records and the existing integrated validator. A missing integration report was then created. All 34 tests and full registry validation pass. |
| Initial new integration suite | Corrupt compressed directory leaked a zlib exception; wrapped it as ValueError. Qt application lifetime in the test was too short; retained its reference through cleanup. All 7 tests pass. |
| Post-manifest allocator suite | One older proof fixture still selected only kickoff/runtime while the manifest described all owners. It now requests the full shared union; all 13 tests pass in the retained separate rerun. |
| Initial clean release | Imported reports contained private workstation paths. Replaced them with symbolic source variables and memo names; fresh stages pass without relaxing the release gate. Original failure remains in `release-2k5-initial.log`. |

Both clean release stages pass allowlist staging, release audit, runtime checks
with `PYTHONPATH` cleared, desktop-file validation, launcher syntax checks and a
second release audit. No materialization fallback was needed. Runtime checks
leave no undeclared files behind.

| Product | Declared files | Runtime closure | Result |
| --- | ---: | --- | --- |
| 2K5 Mod Studio | 358 | 123 product modules, 34 tool modules, 83 registry records, 45 NFL capabilities | PASS |
| APF 2K8 Mod Studio | 204 | 102 modules, 37 APF capabilities | PASS |

The 2K5 stage retains all 23 exact reviewed metadata files. The new owners plus
the existing Music closure also import from that clean stage with NumPy,
Capstone and Unicorn blocked and executable PATH empty: 14 modules pass.
Logs: `stage-2k5.log`, `release-2k5.log`, `stage-apf.log`, `release-apf.log`,
`optional-imports.log`, and `release-gates-final.log`, all under
`.scratch/integration3/`. Both new source lines and documentation were checked
for em dashes; none were introduced. Git whitespace checks pass.

## Witness limits

These proofs establish offline transformations, byte ownership, structural
mapping, software behavior and build/resource postconditions. Kernel acceptance
of the extra page, gameplay feel, defensive scoring behavior in game, the corner
cap in live coverage, runtime effects and music playback remain experimental
and unwitnessed. Defensive try still lacks the retail box-score row and saved
statistics category. No feature is promoted to a witnessed preset by this work.

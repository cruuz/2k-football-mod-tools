# Beta 62 owned XBE allocator scale-out

Branch `astra/r62-allocator-scaleout`, base `5f5b504`. **EXPERIMENTAL / UNWITNESSED.**
No network, console emulator, GUI display, audio playback or push was used.
Only this worktree and its scratch directory were written. Retail inputs were
read-only. Unicorn was used only for bounded instruction fixtures.

## Delivered and decisions

The allocator now has **104 KiB RX, 84 KiB RW, and 16 KiB general RO**, plus
one 4 KiB RO directory page and the existing independent 64 KiB music section.
It uses three additional sections with page-granular ownership. It does not
consume a descriptor for every page. All existing beta-61 owner VAs and raw
offsets remain unchanged; no retail section's VA/raw geometry is moved.

`layout`, `status`, `apply`, `reservations`, and `allocation_evidence` support
both legacy formats and v3. `layout` includes every page, intersecting child,
free byte count, and capacity by kind. The new pure `plan` API and CLI reject
invalid, duplicate, misaligned, oversized or over-budget requests before a
build. `install_read_only` provides exact immutable RO writes. Writable state
is initially zero and is never placed in `.text`.

The v3 map is fixed and bounded, generated from the section-run table. It is
not an arbitrary-address allocator. N pages are grouped into permission-correct
sections, with hard per-kind budgets. New requests use only the new sections;
legacy tails and alignment gaps stay reserved. Today's largest contiguous new
request is 96 KiB code, 80 KiB data, or 16 KiB RO. One logical request receives
a contiguous span in the selected layout; page records identify its children.

The default `apply` retains compact legacy output when appropriate. To realize
the v3 capacity planner's map, use **`apply(payload, requests, scaleout=True)`**.
Overflow and new owners combined with shipped owners also select v3 automatically.
An installed request set is immutable. Exact replay verifies the canonical
set; `apply(payload)` remains the existing ensure-allocated no-op. Changing
requests or upgrading a legacy installation requires rebuilding from its base.
Legacy directories decode using their original packing, even when a fresh
build with the same requests would now select v3.

Necessary shared dependencies were updated without changing their features:
`nfl2k5_bump_strength` recognizes and validates v3 geometry before digest repins;
`nfl2k5_music_storage` retains music's VA/raw/content contract with a new
optional descriptor slot; `nfl2k5_scorebug_ingame` accepts the same bounded
extents in its paired resource reader/preflight. The generalized transactional
writer uses one shared accepted-size policy and still validates complete bytes.

No protected implementation file or reservation JSON was edited. The only new
handoff in `WIRING.md` is the exact `image_xbe_extent` size-membership snippet.
No new BuildPlan option, GUI control, preset, or runtime dependency is needed.
The planner is a repository development CLI, not a new application surface.

## PROVED: section and header accounting

The independent local format reader is `tools/xbe_info.py`, including
`IMAGE_HEADER_FIELDS`, `parse_sections`, and the extended header fields at
`0x178..0x184`. The section table stays at raw `0x370` / VA `0x10370`.
There are 28 sections without music and 29 with it, including all 22 retail
sections. `SizeOfHeaders` remains `0x1000`; `.text` still starts at `0x11000`.

| Section | VA range, half open | Raw start | Size | Flags |
| --- | --- | --- | ---: | --- |
| Legacy RX 1 | `0x14BA000..0x14BB000` | `0xB77000` | 4,096 | `0x36` |
| Legacy RW 1 | `0x14BB000..0x14BC000` | `0xB78000` | 4,096 | `0x03` |
| Music, optional | `0x14BC000..0x14CC000` | `0xB79000` | 65,536 | `0x3A` |
| Legacy RX 2 | `0x14D9000..0x14DA000` | `0xB89000` | 4,096 | `0x36` |
| RX pages 3 through 26 | `0x14DA000..0x14F2000` | `0xB8A000` | 98,304 | `0x36` |
| RW pages 2 through 21 | `0x14F2000..0x1506000` | `0xBA2000` | 81,920 | `0x03` |
| RO directory and general storage | `0x1506000..0x150B000` | `0xBB6000` | 20,480 | `0x32` |

The file is **12,300,288 bytes (`0xBBB000`)**; `SizeOfImage` is `0x14FB000`.
Its 52 allocator pages are recorded individually. Music adds 16 separately
owned pages. All unused bytes remain reserved: RX padding is `CC`, RW and
unused RO padding are zero. No new runtime hooks are installed by scale-out.

| Header raw range | Contents / proof |
| --- | --- |
| `0x370..0x840` | Original 22 descriptors at original locations; normalized geometry SHA-256 retained |
| `0x840..0x990` | Six allocator descriptors, 56 bytes each |
| `0x990..0x9C8` | Optional music descriptor; otherwise canonical zero |
| `0x9C8..0xA10` | Canonical zero padding |
| `0xA10..0xCC4` | Existing header code/constants retained byte for byte |
| `0xCC4..0xD88` | Exact 196-byte retail names/shared-counter copy |
| `0xD88..0xDA0` | Prior allocator names/counters retained |
| `0xDA0..0xDD4` | Version envelope, directory VA/raw, SHA-256 directory seal |
| `0xDD4..0xDE0` | Zero padding |
| `0xDE0..0xE34` | Seven 8-byte names and two 16-bit counter words per descriptor |
| `0xE34..0xEA0` | Exact 108-byte debug-string copy from `0x9A4..0xA10` |
| `0xEA0..0xF60` | Zero padding |
| `0xF60..0x1000` | Exact 160-byte library-metadata copy from `0x904..0x9A4` |

The original name/head/tail pointer fields retain all alias relationships,
adjusted by `0x484`. Each new single-page section points head and tail at the
same zero word. Each multi-page section has separate zero head/tail words;
sections meet only at page boundaries, so there is no shared physical page.
Every descriptor includes the existing length-prefixed SHA-1 section digest.
All retail and owned section digests are checked before allocation mutations.

The three debug-string pointers (`0x14C`, `0x150`, `0x154`) are pinned and
rebased into the exact string copy. The existing three library pointers
(`0x164`, `0x168`, `0x16C`) are rebased as before. V3 additionally fixes the
extended **feature-library pointer at `0x178`: `0x10994 -> 0x10FF0`**, with
its count at `0x17C` pinned to one. Its 16-byte record remains identical.
The legacy byte-compatible paths are retained, including their prior handling
of this pointer; the v3 structural proof does not bless that legacy omission.
The certificate, including existing header-based tuning constants, is not moved.

A descriptor per page cannot fit without consuming existing header owners.
The selected larger-section layout ends before the live catch code at `0xA10`,
scorebug constants at `0xA40`, acceleration code, draft code and EDGE constants.
The tests compare this entire header-owner range and all original section
geometry. SPECIAL-first and allocator-first outputs are identical, including
SPECIAL's already-owned expanded `.XTLID` payload and digest.

The external directory uses one owned RO page. It contains a bounded compressed
canonical request document and fixed-width SHA-256 code/RO seals. Fixed-width
seals make planning independent of eventual code-hash compressibility. The
header seals the entire directory; the RO section digest includes it. JSON
inflation is bounded to 32 KiB, requests to 96 total including the boot logo,
and the stored directory to 4 KiB. Corrupt fields, counters, padding, requests,
code, RO content and music descriptors refuse; merely repinning section SHA-1
cannot bless foreign owner content. Music projection validates its descriptor
before clearing its owned slot, including on replay.

## PROVED mapping boundary; raw reference candidates remain visible

The three old allocator pages retain their strict zero byte-granular reference
encoding gate. A conservative scan found no nearby clear 64 KiB run. For the
large new mappings, v3 follows the existing music section's allocation policy:
add loader-owned memory beyond every retail section and the retail image;
never overwrite or certify a retail cave.

The complete bytewise absolute/relative inventory reports **1,081 raw encoding
candidates** into the large v3 sections, and **zero** into the three legacy
pages. They are retained with source, kind and target in `encoded_references`;
`legacy_encoded_references` is separate. A byte pattern is not a rooted runtime
reference. This work does **not** claim zero encoded candidates in the large
sections or a proof that no computed runtime pointer can reach them.

The cave gate still rejects referenced retail cave overwrites and retains the
legacy zero-encoding assertion. Its v3 cases additionally check fresh mapping,
complete page ownership and the disclosed candidate inventory. The oracle's
`unknown` verdict remains unchanged and is never used as an allocation grant.
Metadata relocation is proved structurally through pinned bytes and explicit
format pointers, not by asserting absence of arbitrary computed header pointers.
Actual kernel acceptance, load ordering and gameplay remain UNWITNESSED.

## Beta-62 owner budgets

Future rows are **planning decisions / HYPOTHESIS**, not assembled feature sizes.
The three landed rows are measured requests; integration added them to the budget fixture.
All rows below fit together with the complete existing owner union. Amounts
are bytes; ordinary requests use alignment 16, Senior Bowl heap alignment 4096.
RO amounts cover immutable tables only. No address is assigned by a report
estimate; each feature must submit its actual requests and compile for the
returned addresses.

| Owner (landed rows marked) | RX | RW | General RO |
| --- | ---: | ---: | ---: |
| nfl2k5_roster_storage (landed) | 82 | 0 | 0 |
| nfl2k5_coverage_slider (landed) | 16 | 0 | 0 |
| nfl2k5_scramble_tuning (landed) | 160 | 0 | 0 |
| QB spy runtime | 2,048 | 768 | 0 |
| Native Practice Squad screen | 4,096 | 256 | 0 |
| Abilities phases 1 and 2 | 1,536 | 0 | 0 |
| 128-season calendar | 1,024 | 0 | 2,048 |
| Guardian-cap overlay | 2,048 | 336 | 0 |
| Music playlist | 2,048 | 512 | 1,024 |
| Read-option runtime read | 1,024 | 0 | 0 |
| Screen hooks | 640 | 0 | 0 |
| Senior Bowl, upper code/heap estimates | 16,384 | 65,536 | 0 |
| My Career, provisional reserve | 8,192 | 4,096 | 0 |
| Franchise-2026 rules, provisional reserve | 8,192 | 4,096 | 0 |
| **New-owner total** | **47,490** | **75,600** | **3,072** |

Existing owners use 6,501 RX bytes and 3,242 RW bytes. The directory reserves
4,096 RO bytes, and music retains its separate 65,536-byte section. With every
budget row, the planner reports:

| Kind | Capacity | Requested, including existing owners/directory | Free bytes | Available for more new owners before alignment |
| --- | ---: | ---: | ---: | ---: |
| RX | 106,496 | 53,991 | 52,505 | **50,800** |
| RW | 86,016 | 78,842 | 7,174 | **4,096** |
| General RO plus directory | 20,480 | 7,168 | 13,312 | **13,312** |

“Free” includes reserved alignment holes and legacy tails. “Available” excludes
those holes/tails. The Senior Bowl upper heap budget leaves little RW headroom;
extra caches or state must pass the planner, not silently use another page.

```sh
python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json
python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json --json
```

Input is an array of `[owner, kind, size, align]` rows, or an object containing
only a `requests` array. Kinds are `code`, `data`, `read_only`; owner names use
lowercase letters/digits/underscores. The CLI prints the page map and per-kind
free/available bytes, exits 2 on refusal, and never creates a disc or output
file. The budget input is committed as `tests/fixtures/nfl2k5_allocator_beta62_requests.json`; the full local plan is retained under `.scratch/`.

## Verification and real-disc evidence

All commands ran as standalone unittest scripts. Final cave/manifest checks
used `NFL2K5_CAVE_MANIFEST=.scratch/scaleout-manifest-final.json`; the production
source-drift guard was retained. Qt integration ran with
`QT_QPA_PLATFORM=offscreen`.

| Command | Final result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py` | 23 passed, 45.979 s |
| `python3 tests/mod_editor/test_nfl2k5_xbe_space.py` | 13 passed |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 43 passed, 91.442 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 55 passed, 167.063 s |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed, 56.307 s |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_beta61_allocator_integration.py` | 7 passed |
| `python3 tests/mod_editor/test_nfl2k5_bump_strength.py` | 10 passed, 1 skipped: its separately configured retail extraction absent |
| `python3 tests/mod_editor/test_nfl2k5_boot_logo.py` | 7 passed |
| `python3 tests/mod_editor/test_nfl2k5_music_metadata.py` | 6 passed |
| `python3 tests/mod_editor/test_nfl2k5_music_policy.py` | 8 passed |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py` | 12 passed |
| `python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | 23 passed |
| `python3 tests/mod_editor/test_nfl2k5_depth_chart_rows.py` | 33 passed |
| `python3 tests/mod_editor/test_nfl2k5_momentum.py` | 23 passed |
| `python3 tests/mod_editor/test_nfl2k5_defensive_try.py` | 23 passed |
| `python3 tests/mod_editor/test_nfl2k5_zone_drop.py` | 9 passed |
| `python3 tests/mod_editor/test_nfl2k5_zone_drop_unicorn.py` | 5 passed |

Both XBE gates run the complete existing owner union in forward and reverse
installation order, for both legacy and v3. The scale-out suite also composes a
90 KiB code / 64 KiB state / 1 KiB RO synthetic request with those owners in
both orders. It checks exact replay, changed-request refusal, all descriptor
fields/counters, directory and content corruption, RO immutability, every page
and child in the recorder, and the paired scorebug reader's extent boundary.

The bounded Unicorn test installs two actual instruction sequences through
`install_code`, at RX page 3 (`0x14DA000`) and page 10 (`0x14E1000`). It maps
permissions from the resulting XBE descriptors. Each sequence writes its
sentinel to the named RW allocation, returns to the supplied stop address,
preserves EBX, and consumes exactly the return slot. Runs have a four-instruction
limit. No retail hook calls this synthetic code.

Transactional tests cover retail-to-v3, legacy-to-v3, v3-to-legacy and same-size
writes, neighbor preservation, short payload/directory writes and exact rollback.
Descriptors close before replacement. Synthetic images are about 12 MiB.
Four additional comparisons against the exact original HEAD allocator source
produce byte-identical legacy outputs: logo only, kickoff, the full existing
request set and the original small synthetic request set. Evidence is in
`.scratch/legacy-byte-identity.json`.

The old Momentum/integration capacity expectations were updated because their
formerly overflowing 4 KiB requests now fit. Tests still require refusal beyond
the new limit. A new music-descriptor corruption test first reproduced 20
acceptance failures, then passed after projection/replay validation was fixed;
its red log is `.scratch/music-descriptor-red.log`.

The exact protected snippet was compiled from the existing function into a
scratch test namespace. It accepted a real-retail-derived v3 XBE through the
transactional image writer and rejected a corrupted payload of the same accepted
size. Command: `python3 .scratch/verify-wiring.py`. Protected source was unchanged.
Python compilation and `git diff --check` passed.

The final real-disc command was:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir .scratch --json .scratch/scaleout-manifest-final.json \
  --synthetic-owner-bytes 92160
```

It completed the actual experimental preset build and the existing separate
owner probe, then installed **92,160 synthetic RX bytes** on that real disposable
disc. The synthetic allocation was read back, replayed without image growth,
and removed by restoring the verified normal owner payload. Relocated kickoff
reported applied throughout. The temporary disc was deleted on completion;
no synthetic owner remains on an output disc or in the final manifest's spans.

| Evidence | Result |
| --- | --- |
| Final manifest | 8,263 reservations, 85 observed writer calls, 82 source fingerprints |
| Allocator pages / pages including music | 52 / 68 |
| Final owner-probe XBE SHA-256 | `901e6d11aabef7d7db20a359e2f054ef35a0c5842463bee81a67f92554b024d0` |
| Synthetic 90 KiB owner XBE SHA-256 | `2260260bf9010f835183f4f1b317e3d7d610d57f240675105bf50b6b4a8b35b9` |
| Synthetic disc size / XBE size | 6,324,822,016 / 12,300,288 bytes |
| Section digests, read-back, replay, removal | Passed |
| Source-root fingerprint validation | Passed against final sources |
| Final build wall time / peak RSS | 263.16 s / 1,180,584 KiB |

The existing oracle's owner probe uses its neutral resource path; the manifest
honestly retains `runtime_panel_resources: false`. This is an executable-space
build proof, not a played or fully paired runtime-scorebug witness disc. Its
experimental-preset build separately includes the actual paired scorebug pass.

The final allocation proof command also passed:

```sh
python3 tools/nfl2k5_cave_oracle.py space-proof \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --manifest .scratch/scaleout-manifest-final.json \
  --allocated .scratch/scaled-final.xbe --json .scratch/space-proof-final.json
```

It records every page and child, no retail mapping or foreign-owner overlap,
zero legacy-page encodings and all 1,081 v3 raw candidates. The cave oracle's
28-test suite passed with the generated manifest and its source-drift checks.
Claude must regenerate the protected release JSON during integration; it was
not edited or silently substituted here.

Measured peak RSS was 189,472 KiB for the new suite, 279,028 KiB for the memory
gate, 431,328 KiB for the cave gate and 901,228 KiB for the oracle. The largest
measured process was the 1,180,584 KiB real build, below 2 GiB. No added test or
tool reads a whole disc or archive pack into memory; image transport uses bounded
descriptor reads and the existing build writers. Final logs and receipts are
under `.scratch/`, excluded from the commit.


## Noah's witness list and remaining limits

Nothing below is claimed witnessed. The synthetic owner has no retail hook and
is removed after the build proof. **Relocated kickoff remains the loader/gameplay
witness**, with the complete original implementation and all eleven hooks.

1. After Claude wires the extent snippet and regenerates the protected manifest,
   build a disposable v3 comparison with the normal relocated kickoff enabled.
   Record the exact request list, XBE hash and receipt. Verify boot/logo, title
   screen and entering an exhibition or practice session.
2. Play ordinary kickoffs in both field directions, human and CPU kicking and
   receiving. Check receiving-40 alignment, blockers/returners, approach/flight
   hold, ground/contact release and the next down. Compare touchbacks, end-zone,
   short/out-of-bounds, onside and safety kicks against the existing witness.
3. On the same properly paired feature build, check SPECIAL, scorebug events and
   team logos, momentum/contact, defensive try, zone drops, and music playback.
   Save/reload and repeat a kickoff after another game or mode transition.
4. Record any loader failure, missing logo, memory-pressure symptom or changed
   owner behavior with the exact hash. The bounded third/tenth-page instructions
   establish execution under their mapped permissions, not Xbox boot acceptance.

No virtual gap is reused as a cave. Kernel allocation/commit behavior, early
boot-logo availability, computed references, console memory pressure and all
future owner gameplay remain unproved. Existing defensive-try persistent stat
and other feature limitations are unchanged. This task introduces no feature
preset or claim that an unwired future owner is ready to play.

## Delivery

The explicit-path staging attempt failed because the linked Git metadata is
read-only (`index.lock` could not be created). The authorized fallback uses
`.scratch/allocator-scaleout-commit/.git`, with the original HEAD as parent,
this same worktree and explicit paths for both staging and committing. Delivery
is `.scratch/r62-allocator-scaleout.bundle`, verified against the base commit.
All edited files remain here. The shared branch metadata is untouched.
`ASTRA_BRIEF.md`, `.scratch/`, game bytes and images are excluded. No push.

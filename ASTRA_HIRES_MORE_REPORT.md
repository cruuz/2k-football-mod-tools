# r62 hires-more: family compiler and the limits of the memory proof

2026-09-06. **EXPERIMENTAL / UNWITNESSED.** No game, emulator, GUI, audio,
or network was run. No new XBE patch, cave, allocator owner, or RAM target
was installed. Protected files are untouched; their integration is specified
in [WIRING.md](WIRING.md).

The compiler now covers **2,524 pinned resources** across six families.
The requested statement that these families fit in 64 MiB with a proved
number of MiB of headroom **cannot be established from this static evidence**.
The game constructs a variable residual resource heap. Its initial physical
allocation, startup reservations, context selection and live free blocks
are runtime values. The implementation therefore refuses a modeled overage,
reports smaller selections as `unproved`, and leaves `headroom_bytes` null.
It does not silently convert an address ceiling into a texture allowance.
`xemu-128` stays unavailable for the concrete reasons below.

## What was built

| Family | Total targets | Native raster | 2x input/output raster |
| --- | ---: | --- | --- |
| Current Standard/A helmet art | 64 | 256 x 256, six mips | 512 x 512 |
| Current uniform numbers | 1,920 | 64 x 64/four mips or 32 x 32/three mips | 128 x 128 or 64 x 64 |
| Current clean/mud jerseys | 64 paired TSET resources | 512 x 256, six mips, two palettes | Two authored 1024 x 512 images |
| Created-team midfield art | 126 | 256 x 256, six mips | 512 x 512 |
| Embedded stock midfield art | 348 | 339 at 256 x 256; nine at 512 x 256; six mips | 512 x 512 or 1024 x 512 |
| Scorebug frame and ESPN strip | 2 | 64 x 64 and 128 x 64, one mip | 128 x 128 and 256 x 128 |

Current kits mean all team codes 00 through 31, both H0 and A0. The number
family includes ten jersey, ten helmet and ten arm digit resources for each
of those 64 kits. The helmet target is `helmet00`, used by the audited A
shell/accessories path; it does not expand the separate helmet C art.
The field logo set includes all 42 CT codes and all dry/rain/snow versions.
The complete 477-field-scene census found 438 `center_logo` draws: 348 have
embedded descriptors, 90 bind an external texture; 39 scenes have no such
draw. This scope includes stock NFL midfield art where it is an embedded
`center_logo`. It does not classify every other stadium logo as midfield:
`logo`, `playoff_logo`, `Stadium_logo`, and `stadium_logo` remain excluded.

The three pilot identities and filenames remain valid. New filenames,
exact outer/chunk/name-ID identities, dimensions, stream parameters and
SHA-256 pins are in `nfl2k5_hires_catalog.py`; `catalog` emits all of them.
There are 2,521 new rows plus the three original resources. This is a
compiler and an import convention, not a finished illustrated art pack.
The full acceptance uses generated diagnostic blocks, never retail pixels
as redistributed artwork.

The ordinary TXTR path retains the pilot's output recipe. Rectangular
dimensions are now supported. A jersey has one shared index/mip chain and
two independently authored palettes; an eight-channel median-cut quantizer
chooses common indices and reports joint color error. It refuses more than
8,192 distinct paired colors across the mip chain. It does not reuse clean
colors as a pretend mud image. Both files participate in source-race checks.

An embedded SCNE retains its entire original decoded system and video data,
including vertex buffers, commands, other textures and the unused native
logo raster. Only the selected descriptor's pixel offset, palette offset and
format words change; a 128-byte-aligned new raster is appended. Inspection
restores those three words and checks the complete original baseline hash.
All relative pointers remain at their original offsets. Native-size authored
output also appends a raster: it reduces the 2x cost but does not restore
retail memory use. An original-disc build with Hi-res off is the exact
retail fallback.

The folder loader validates all selected files, retains hashes and paths,
and reloads one raster or pair at a time. Optional family selection is
consistent across pure apply/status, image inspection/build, and budget
preflight. Unknown artwork, incomplete pairs, mixed installs, changed
baselines, changed recipes and unsafe decompression scratch refuse.
Inputs/outputs are each limited to 256 MiB of selected compressed resources;
an outer read is bounded to 32 MiB; rewritten outers total at most 768 MiB.
PNG files are at most 32 MiB; master expansion is at most 64 MiB with a
16-megapixel source cap. Small bounded raster caches avoid repeating work
for identical input sizes without retaining the entire artwork folder.

Image writes still use the existing shared archive layout, grow/shrink
writer and publication transaction. Selected chunks sharing an outer are
rewritten together. Fresh readers verify every outer, file extent, selected
resource and mip before publication. No separate pack writer was introduced.
Without a folder, inspection deliberately reports that it checked only the
legacy three probes. It must not be presented as a complete family scan.

## Consumer evidence: PROVED within the named paths

The inherited common path is `0x245B9` (normalized texture coordinates),
`0x31FA0` (texture address/format binding), `0x323D0`, `0x34DF0` (descriptor
relocation), and `0x44E60` (ordinary resource load). The geometry equation is
`uv = NORMSHORT2(register 6) * shape[+0x30].xy + shape[+0x30].zw`.
There is no texture-dimension factor in that shader equation. The consumer
receipt records the referenced vertices, UV lanes, scales, offsets, bounds
and hashes for every selected draw. This is a bounded static proof, not a
claim of an exhaustive runtime call graph.

| Family | Binder/load evidence | Geometry evidence |
| --- | --- | --- |
| Helmets | `0x8E3F0`, `0x8E9E0`, material/cache tables `0x4EEAF8` and `0x4EF390` | A shell and accessories in `o3c113` lo_body and `o3c115` hi_head |
| Numbers | `0x8E620`, `0x8E910`, `0x8E8D0`, `0x8E4B0`, digit table `0xA86C00` | 42 number draws in lo_body, 30 in hi_body (`o3c114`), 12 in hi_head |
| Jerseys | `0x8EBB0`, `0x8E4B0`, `0x451D0`, `0x45170`, `0x4EEAF8` | Three jersey/neckroll draws in each of lo_body and hi_body |
| External midfield | `0x9C5DE`, `0x4F0090`, inherited TXTR loader | Every `center_logo` draw in all 477 field scenes |
| Embedded midfield | `0x45A20..0x45C9F`, `0x2F140`, `0x34DF0` | Same field census, selected embedded descriptor baseline pinned in full |
| Scorebug | `0xFC1A0`, eleven binding pairs at `0xA95C60` | Nine frame and two ESPN material draws in `o346c78` |

`0x8E910` selects the digit handle from the 12-byte-stride table;
`0x8E8D0` stores the handle at material +0x30 and fixed 4.0/2.0 values at
+0x20/+0x24. It does not read texture width. Jersey binding selects existing
clean/mud handles through the shared material cache. The TSET loader sums
system, video and scratch sizes and relocates both descriptors. The SCNE
loader likewise allocates from wrapper sizes, decodes and relocates its
embedded descriptors. The new compiler's wrapper sizes and scratch are
checked by a fresh decode; the original mip counts are retained.

`nfl2k5_hires_evidence.py` and the inherited consumer pins reject changes to
these audited code/table ranges before an image write. Scene UV hashes are
reproducible audit evidence, not a general runtime guard for arbitrary model
mods. All SCNE targets themselves have complete pinned baselines; unrelated
uniform-model alterations are outside the audited combination. Other XBE
patches may compose outside the pinned ranges.

The complete existing XBE gate union includes the reference/runtime scorebug,
which deliberately changes `0xA95C60`. The other five families' consumer
pins survive that complete union in both installation orders. The Hi-res
scorebug family correctly refuses the changed binding table, including an
ESPN-only selection; accepting it would require a separately audited combined
consumer recipe. The first exploratory all-family union assertion exposed
this existing conflict. The final regression verifies both the five-family
composition and exact scorebug refusal, and WIRING names the restriction.

**Nameplates are deliberately refused.** `0x1C2140`, called from `0x8F800`,
uses NAME glyph pixel offsets and widths, descriptor width and the blitter
at `0x3D0820`. The source atlas is a linear 1024 x 32 texture with a different
format. Scaling only its descriptor would change the pixel-coordinate
meaning. `0x90570` loads `jerseyname%02u` and stores per-player handles at
+0x50. The 22 native generated output surfaces (`o3c164..185`) are 256 x 32,
with 128 system bytes, 11,776 video bytes and 16 scratch bytes each. Their
source hashes and size words are in `reports/hires_player_names.v2.json`.
Scaling that pipeline would require a separate pixel-layout/renderer change.

## Memory: proved allocator shape, unproved live headroom

The read-only Ghidra corpus establishes the following chain. Addresses are
retail virtual addresses, not new allocations:

1. `0x326E0` calls `GlobalMemoryStatus` at `0x3783B0`. That wrapper calls
   `MmQueryStatistics` and converts page counts to bytes by shifting 12.
   Reported total physical memory is used for the extra-RAM branch.
2. The main arena probes `XPhysicalAlloc` from `0x04000000` downward in
   4 KiB steps, frees the successful probe, subtracts `DAT_00A6D324 =
   0x00200000`, aligns to 4 KiB and allocates again. Base and size are stored
   at `0xB018C4` and `0xB018C8`. Its end is clamped to `0x84000000`.
   **62 MiB is an upper bound before startup reservations, not its size.**
3. Startup consumers move the arena markers at `0xB018B0` and `0xB018B4`.
   `0x38FC0` at `0x3907F..0x39092` passes their residual range to `0x48640`
   to initialize heap object `0xB04E24`. Heap base/end and size therefore
   depend on successful allocations and prior consumers.
4. `0x437D0` returns the current resource heap pointer `0xB12034`;
   `0x437E0` sets it. `0x43CC0` selects the default heap and `0x43DB0`
   selects a resource-context heap from context +0x20. Resource loaders
   use this pointer. A universal fixed texture-only heap size is not proved.
5. `0x483D0` rounds `request + 0x80` up to 0x80 and returns block +0x80.
   Free bytes live at heap +0x88; `0x48700` can follow fallback heap +0x8C.
   `0x48760` can release loading scratch later. The model keeps checked
   scratch during loading and accounts for the header/alignment for every
   modeled resource. Fragmentation and the largest free block remain unknown.
6. `0x31FA0` masks a texture address with **0x03FFFFFF**. It is an address
   transform, not a statement that all 64 MiB is available for artwork.

The executable SHA-256 is
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
The read-only source XISO is 6,300,499,968 bytes; its inherited pilot identity
is `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`.
This pass pins individual retail resources and code ranges; it does not
claim a new complete-disc hash run. No retail image or pack copy was made.

### Live-scenario video bytes

This table describes two current shared kit sets for the 22 on-field players,
two selected external midfield textures, one selected stock logo and both
scorebug textures. The two-kit model follows shared handles, so it does not
multiply whole uniform packages by 22. It is a stated scenario, not a proved
upper bound on cache lifetime or all sideline/replay residents.

| Selected video | Native bytes | 2x bytes |
| --- | ---: | ---: |
| Two helmet textures | 176,768 | 700,928 |
| Two clean/mud jersey resources | 353,536 | 1,401,856 |
| Two sets of 30 number textures | 305,920 | 1,039,360 |
| Two external midfield textures | 176,768 | 700,928 |
| One square embedded logo raster | 88,384 | 350,464 |
| One rectangular embedded logo raster, alternative to square | 175,744 | 699,904 |
| Scorebug frame and ESPN strip | 14,336 | 51,200 |
| 22 generated name surfaces, unchanged | 259,072 | 259,072 |

Embedded output **adds** its raster to the complete original scene video
allocation. The rows for those rasters cannot be substituted for the scene
allocation. Palette bytes are included: 1,024 per ordinary texture, two
palettes per jersey. This table is intentionally separate from the resource
allocation model below, which also includes unmodified kit textures, scene
data, resource system objects, loading scratch and allocation headers.

### Preflight allocation model, complete catalog selected at 2x

Each allocation is `align128(system + video + scratch + 128)`. Two worst
current kit packages and two worst primary field scenes are selected by
their respective costs, independently at native/output sizes. The field
pair provides a loading/transition scenario; it is not evidence that only
two field scenes can ever coexist. Unif/NAME records have zero wrapper size
words and use different loaders: their object costs are unknown and are
excluded rather than assigned invented 128-byte allocations.

| Modeled component | Native bytes | 2x bytes, zero output scratch | 2x bytes, actual diagnostic scratch |
| --- | ---: | ---: | ---: |
| Two shared uniform texture sets, including unchanged resources | 5,470,720 | 7,766,528 | 7,774,720 |
| Two primary field scenes, including retained native video | 1,236,480 | 2,516,992 | 2,517,248 |
| Two selected external midfield logos | 177,408 | 701,440 | 701,696 |
| Both scorebug textures | 14,848 | 51,712 | 51,968 |
| 22 generated player name surfaces | 267,520 | 267,520 | 267,520 |
| **Total** | **7,166,976** | **11,304,192** | **11,313,152** |

The native kit/scene baseline includes catalogued original scratch. Selected
external/scorebug native rows use zero scratch as a lower bound. Unselected
kit/scene resources retain native costs in an output model; selected output
scratch is zero before encoding, then replaced by actual inspected scratch
after encoding. This is a sound arithmetic check for the stated scenario,
not an exact observed resident set. The modeled growth before output scratch
is 4,137,216 bytes. The arithmetic remainder to the 65,011,712-byte ceiling
is 53,707,520 bytes, **not available headroom**.

The final diagnostic compile receipt records actual output scratch and the
resulting **11,313,152-byte** allocation model, a 4,146,176-byte modeled
increase. This does not replace the unknown runtime inputs. The 53,698,560
bytes remaining to the ceiling are still not headroom.
`family_subsets` enumerates all 64 whole-family selections: all six families
(2,524 targets) are within this necessary bound. `largest_proved_growth_subset`
is empty, meaning no growth selection has a static whole-game fit certificate,
not that even the retail game is alleged to fail. There is no honest safe-N
subset to auto-enable from this evidence.

Over-budget preflight states required bytes, ceiling and excess bytes and
raises before encoding; the compiled receipt is checked again with actual
scratch before any output transaction. Boundary tests exercise exact equality
and a one-byte overage, including the requirement that the encoder was not
called. A smaller result remains experimental with null headroom. The UI
checkboxes, exact preflight propagation, disabled-overage behavior and plain
captions are documented in WIRING because those files are protected.

### Why xemu-128 remains refused

If the kernel reports more than 64 MiB, `0x326E0` takes a separate branch.
It temporarily reserves contiguous space, then tries a 64 MiB CRT/virtual
allocation and decreases the request in 1 MiB steps on failure. The chain
through `0x1A5A9` and `0x18A4D` reaches `NtAllocateVirtualMemory`; resulting
size/base/end are stored at `0xB018D4/D8/DC` and exposed through
`0xB018B8/BC`. That is not proof that the main GPU-visible contiguous texture
arena or its resource-context heaps expand. The main arena still has its
64 MiB probe limit and `0x84000000` end clamp.

The host's installed xemu BIOS/kernel memory exposure was not executed or
assumed. Even if 128 MiB is reported, the unchanged GPU mask maps physical
`0x04000000` to zero. Removing that mask, moving texture allocations high,
or treating the extra virtual allocation as GPU-addressable would require
additional allocator, GPU and runtime evidence. The backend therefore
refuses `xemu-128`; no override or confirmation enables it.

## Reproduction and validation

Source input for these commands is the user-owned read-only file:
`/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso`.
The Ghidra corpus was read only at
`/home/noah/2k-football-mod-tools/research/functions/nfl2k5`; no main-tree or
other-worktree files were changed. Existing Astra reports and the RC85
changelog were read before extending the pilot.

Every test is a plain standalone unittest invocation. Optional retail tests
give a precise skip when their evidence image is absent. These runs used
the retail evidence and did not skip:

| Command after `python3` | Result |
| --- | --- |
| `tests/mod_editor/test_nfl2k5_hires_pack.py` | 15 passed, 1.832 s, final run |
| `tests/mod_editor/test_nfl2k5_hires_families.py` | 7 passed, 1.230 s, final run |
| `tests/mod_editor/test_nfl2k5_hires_pack_retail.py` | 4 passed, 17.824 s |
| `tests/mod_editor/test_nfl2k5_hires_families_retail.py` (before the additional transaction test) | 3 passed, 59.929 s; peak RSS 194,092 KiB |
| `tests/mod_editor/test_nfl2k5_hires_families_retail.py RetailFamilyTests.test_real_outer_contents_through_bounded_archive_transaction` | 1 passed, 18.277 s; peak RSS 225,208 KiB |
| `tests/mod_editor/test_nfl2k5_hires_families_retail.py RetailFamilyTests.test_consumer_pins_compose_and_scorebug_conflict_refuses_both_orders` | 1 passed, 60.252 s; peak RSS 242,896 KiB |
| `tests/mod_editor/test_nfl2k5_music_banks.py` | 15 passed, 12.102 s |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 63 passed, 174.733 s; peak RSS 297,384 KiB |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 75 passed, 259.355 s; peak RSS 443,156 KiB |

No new executable owner is needed in either gate: this task writes resources,
and both existing complete-owner unions remain green. The synthetic family
transaction test uses the actual archive writer with multiple changed chunks
in one outer, native/2x replay and shrinking, plus a mud-input race which
must preserve the previous output and remove temporary transaction files.
The retail tests hash all 2,524 catalog targets and exercise every distinct
family/dimension/mip layout through native, 2x and re-upgrade. Shared palette
tests include more than 256 authored color pairs and verify nonzero reported
quantization error rather than testing only trivial two-color images.
The additional retail transaction uses complete real outers for all three
formats in a bounded 16 MiB archive fixture, verifies every untouched chunk
and deletes the fixture and output on exit. It does not copy a real archive
pack or full retail disc into memory or onto scratch storage.

Reproducible metadata tools:

```sh
python3 tools/nfl2k5_hires_family_audit.py "$HIRES_RETAIL_IMAGE" \
  --catalog mod_editor/core/nfl2k5_hires_catalog.py \
  --receipt reports/hires_families.v2.json
python3 tools/nfl2k5_hires_consumer_audit.py "$HIRES_RETAIL_IMAGE" \
  --families > reports/hires_consumers.v2.json
python3 tools/nfl2k5_hires_acceptance.py "$HIRES_RETAIL_IMAGE" \
  --receipt reports/hires_compile_all.v2.json
```

Catalog generation and independent regeneration passed with no refused
candidate; the consumer audit completed all 477 field scenes and the four
scorebug/player scenes. The complete 2x run passed all **2,524 targets** in
2,745.870 seconds (45:46 wall time), with peak RSS **236,580 KiB**. Each
target was compiled, independently inspected, and checked for exact baseline
restoration and agreement with the compiler's decoded receipt. All diagnostic
rasters had zero maximum channel error. This says nothing about the color
error of future photographic or otherwise more complex authored inputs.

Selected source spans total 80,424,912 bytes; compiled spans total 85,094,032
bytes, a 4,669,120-byte increase. Both totals are inside the 256 MiB selected
resource bounds. The largest output span is 394,832 bytes. The entire
catalog's decoded output video totals 419,720,832 bytes across many mutually
exclusive teams/fields, not a simultaneous gameplay allocation. The receipt
is metadata only, 14,600,317 bytes; no pixel payload or disc is included.
The long codec run started before the accounting correction for zero-sized
Unif/NAME loader records. Its allocation summary was recalculated against
the final model from the same independently inspected output rows; no codec
output changed or was omitted. All 184 final unittest cases passed.

The capability fragment is
validated by replacing the existing ID in an in-memory registry and sorting
its entries before calling the registry's strict validator.

All six runtime modules also imported from an isolated temporary copy of
the allowlisted Python closure, with the four proposed allowlist additions.
The smoke process used `python3 -I -B`, confirmed module paths were inside
that temporary tree, counted 2,524 assets, checked null headroom and checked
128-target refusal. The 310-file Python stage was deleted. A full release
stage was attempted but could not start because the baseline allowlist names
the absent `reports/assets/nfl2k5_audo_family_labels.json`. This task did not
fabricate unrelated audio metadata or claim the complete release gate passed.

Final checks: strict merged capability schema; the feature's module commands
and evidence files; matching catalog/receipt identities and family counts;
Python parsing; whitespace checks; and explicit protected-path exclusion.
The main drive remained at 101 GiB free and scratch at about 5.7 MiB. Every
synthetic acceptance image and temporary stage was deleted; no full retail
disc or pack copy was created. Delivery uses an explicit-path local commit
on `astra/r62-hires-more`, based on
`b7bac4f2417c81f51cda5e1e60e7bf6053895da5`. Normal Git staging succeeded;
the bundle fallback was unnecessary. `ASTRA_BRIEF.md` and `.scratch/` remain
excluded. Nothing is pushed.

## Noah's witness list and remaining limits

Noah must play the resulting witness copies before any runtime claim changes.
Keep the same authored sources for native/2x comparisons and record the
disc receipt, emulator settings, BIOS/kernel, guest RAM and image hash.

1. All 32 teams, both current home/away kits: Standard/A helmet shells and
   accessories at close-up, gameplay, distant LOD, replay and sideline views.
   Confirm the untouched alternate/C assets do not masquerade as covered.
2. Both team's jersey bodies and neckrolls, clean and muddy; all ten digits
   on body, sleeves/shoulders and helmet paths, including wide/narrow digits,
   two-digit numbers, LOD changes and alpha edges. Player names must remain
   legible at their unchanged native resolution.
3. Every CT midfield code in dry, rain and snow, plus the stock scene
   variants. Include all nine rectangular stock logo resources, fields
   without a center logo, camera movement and seams near midfield.
4. Scorebug frame and ESPN strip: pregame, changing clock/score, possession,
   penalty/timeout states, replay entry/exit, quarter changes and overtime.
   Check atlas boundaries, filtering, transparency and unrelated text.
5. Compare native/2x texture output at xemu rendering scales 1x, 2x and 4x.
   Record actual improvements/artifacts; diagnostic blocks only establish
   offline compiler behavior and are not finished replacement graphics.
6. Complete games, halftime, menus, next-game loads and replay transitions.
   Capture `B018C4/C8`, arena markers, the active `B12034` heap and any
   context/fallback chain, heap base/end/free/+0x88, largest free block and
   allocation failures at each peak. Include models, nontexture residents,
   old/new load overlap and fragmentation when calculating real headroom.
7. Keep 128 MiB disabled. A future investigation must establish actual
   kernel exposure, placement of the extra allocation, texture heap routing
   and GPU address behavior before compiling for that target.

Historical/alternate kits, helmet C, end zones, goal pads, other stadium
logo materials, arbitrary textures, 4x texture output and the nameplate
pixel pipeline remain outside this implementation. The family selection
and budget UI/runtime packaging integration remains a protected-file
handoff, not an implemented UI claim. Whole-game memory fit and visual/runtime
behavior remain unproved; the brief's absolute live-memory certificate is
an explicitly documented gap, not a successful acceptance result.

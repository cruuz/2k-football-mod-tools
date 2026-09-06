# r62 scorebug layout repair and runtime freeze investigation

2026-09-06. **EXPERIMENTAL / UNWITNESSED v8 static and v2 runtime.**

## Root cause and evidence boundary

**The community tester's runtime freeze is not root-caused or fixed by this
revision.** The native collection reader, allocation, decompression,
registration, ordinary name lookup and event-hook simulations below all
terminate. Two real native wait loops can produce an audio-alive freeze when
their completion is withheld; the witness supplies neither a stopped guest
PC nor completion state to distinguish them. Shipping a speculative change
to the hook instructions would not constitute a proved fix. The deliverable
is a measured static repair, bounded transport repairs, substantially stronger
native tests, and a runnable six-profile diagnostic matrix. Runtime defaults
must stay off pending that matrix, as specified in `WIRING.md`.

**PROVED static defects:** the previous preview omitted the game's native
+16 vertical viewport translation and used a 9-pixel approximation for text
objects that initialize their font scales to 2.0. The first made the rendered
bar 16 pixels lower than its preview; the second made the old narrow clock
strip appear more spacious than the native text suggested. The corrected
installed scene and root now project to the reference frame bounds. The
preview consumes installed, decoded geometry and uses larger approximate
glyphs. Negative NORMSHORT coordinates also now use the native asymmetric
normalization; that correction is less than 0.013 pixel, not a twofold scale.

**NOT PROVED:** these defects do not explain the full severe clipping in the
supplied screenshot. The reconstructed, hash-pinned v7 scene projects to
y=397..445 in the bounded native fixture, which does not reproduce a clock
below the screen. No hidden factor of two was found in its mesh, inverse bind
matrices, scene relocation or camera. This remains an explicit discrepancy
requiring an actual v8 gameplay witness. No emulator setting is blamed.

Inputs read first and preserved verbatim:
[tester report](docs/scorebug_ingame/witness_r61b.md) and
[TB at NE screenshot](docs/scorebug_ingame/witness_TB_NE.png). The tester used
`cf349b7`, xemu on macOS Apple silicon, and retried the runtime failure past
the two-launch quirk. The attachment is 1280x1008; the reference is 1280x960.
Its visible bar is approximately x=173..1120, about 74% of image width. The
reference is x=168..1120, also about 74%. Those supplied pixels do not support
halving the frame width. Because its bottom is clipped, the screenshot cannot
establish the bar's complete height or recover the missing render transform.

## Static fix and exact receipts

The reference's long neutral frame rails measure x=168..1120, y=762..858 in
`docs/scorebug_ingame/target_NO_MIA.png`. At 640x480 this is
**[84, 381, 560, 429], 476 by 48 pixels**. The measurement is executable in
`test_nfl2k5_scorebug_projection.py`, rather than a manually asserted target.

Native `0x66670` uses the HUD inset `(40,16)` from `0x4e7f84/0x4e7f80`.
For the game's 720x480 framebuffer, the HUD viewport is `(40,16)..(680,464)`,
640x448 units. The reference comparison explicitly crops active columns
40..680 to 640 columns and retains all 480 rows. The native camera matrix
adds `(40,16)`; this is separate from scene root placement. Therefore the
reference root y=424 requires scene y=408. The XBE uses `(320,408)` now.

| Geometry in the 640x480 comparison | Shipped v7 | v8 |
| --- | --- | --- |
| Scene root | (320, 424) | (320, 408) |
| Native frame bounds | [84.091, 396.999, 559.957, 445.000] | [84.091, 380.999, 559.957, 429.000] |
| Clock strip bounds | [260.997, 421.993, 378.996, 443.000] | [241.002, 406.006, 399.004, 427.000] |
| Down pill width | 112 | 144 |
| Team panel width | 170 each | 150 each |
| Score anchors, relative x | -91, +91 | -101, +101 |

The entire frame sits 35 pixels above the native safe-area bottom and
51 pixels above the framebuffer bottom. Both native direction modes and both
ends of the six-unit pill slide remain inside the safe area. The literal
retail ESPN/NFL logo stays in the fixed atlas. The static treatment adds a
darker, flatter frame, distinct dark score cells with dividers, a wider red
pill and a white clock strip. Team abbreviations retain live native text:
white normally and the existing yellow possession variant. Static timeout
dashes remain decorative; static compilation cannot make them live counters.
The kick-meter margin remains 150 and the lineup insert remains hidden.

The serializer still writes scalar **420** at serialized SHAP `+0x10`, with
bias `(-20,100,-29.5)` at `+0x20`. Native `0x22f90` relocates these to runtime
`+0x1c` and `+0x10` respectively. The vertex shaders' initial MAD is
`normalized_position * scalar + bias`; serialized `+0x14` is not a second
axis scale. Native `0x233c0` / `0x22c00` compose local/world and inverse bind
matrices. Running that path produces no additional factor of two. Wrapper
`+0x14` remains the original overlap-scratch contract, including the SCNE's
16 bytes; it is not a viewport or geometry multiplier.

The actual widescreen camera hook contracts horizontal HUD coordinates by
27/32 and leaves vertical coordinates unchanged. In the un-stretched 640x480
comparison its frame is `[120.952,380.999,522.464,429.000]`. The intended
display stretch of 32/27 cancels that contraction, preserving 4:3 HUD
proportions. This was checked by executing the existing hook at native camera
activation, not by multiplying the preview alone. Live widescreen output
still needs the existing widescreen patch's gameplay witness.

Comparison artifacts, all 640x480:

- [Shipped v7, native projection](docs/scorebug_ingame/before_v7_640x480.png)
- [v8, native projection](docs/scorebug_ingame/after_v8_640x480.png)
- [v8, widest text sample](docs/scorebug_ingame/after_v8_widest_640x480.png)
- [v8 with the native widescreen hook](docs/scorebug_ingame/after_v8_wide_640x480.png)
- [Exact matrices and geometry](docs/scorebug_ingame/projection.json)

Reproduce without a display, emulator or disc build:

```bash
python3 -m tools.nfl2k5_scorebug_projection \
  --pack '/path/to/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --xbe '/path/to/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --output docs/scorebug_ingame
```

The harness executes whole-scene relocation `0x2f140`, native descriptor/name
registration, scorebug setup `0xfccd0`, frame driver `0xfce70`, palette
composition `0x22c00` and camera activation `0x2ac80`. Text anchors use native
`0xfb640`. Startup animation selection, font creation, game predicates and
the render-list boundary are explicit fixture replacements. Glyphs are
approximate; score rotation is settled; depth testing and GPU consumption are
not simulated. The old scene and atlas are reconstructed to their exact v7
hashes before producing the before image. These are evidence about geometry,
not gameplay captures.

### Pinned installation bytes

`docs/scorebug_ingame/fix_receipts.json` contains read-only preflight receipts
from the real retail XISO for the static build and every probe: all owned
XBE fields, resource identities, individual panel hashes, full streamed pack
hashes, resulting XBE hashes, allocation sites and sizes. No real output disc
was created. Per-profile CLI transport was exercised on temporary XDVDFS
fixtures containing the actual retail pack and executable.

| Field/site | Retail bytes | v8 installed bytes |
| --- | --- | --- |
| Position floats, `0x10a40` | `73f7d373e3f7430f` | `0000a0430000cc43` |
| Root x, `0xfcffc` | `d805586d4e00` | `d805400a0100` |
| Root x, `0xfd07b` | `d80568694f00` | `d805400a0100` |
| Root x, `0xfd0eb` | `d805586d4e00` | `d805400a0100` |
| Root y, `0xfd15e` | `d8051c0f4f00` | `d805440a0100` |

Other owned contrast, animation, logo-material and HUD-neighbor fields are
listed in full in the JSON. No retail-referenced cave or runtime data in
`.text` is introduced. The existing header slots, RX/RW allocator owner and
section digest helpers are retained.

| Owned payload | Bytes | SHA-256 after compilation |
| --- | --- | --- |
| Static SCNE span | 4,832 | `cdcf2aa898dd85332e3b872ca73eeae525ca85e9e543f4d07250bf820df16427` |
| Static decoded SCNE | fixed existing allocation | `1b5452ae574029317f8438c059b0662532b41bfb4206af6bdee0b26c6b7a5c14` |
| Runtime binding SCNE span | 4,832 | `6cf59ba561b416b615467b312ecaf4a446d5a473ed17fce86256c5ec88ec96b2` |
| Atlas span | 2,432 | `8771f332aa07a63db1c21d9803455cc4ed5dd7f04fb88d36d571b03f1c7b7cd0` |
| Existing runtime HUD portion | 2,977,184 | `765af4ac443263def3c46b13986dfbf2eefc7ecfd715afd593b829b5d31b9605` |
| Full runtime appendix | 1,393,920 | `5f56ff615439fa8d1f87a833393f29e565873250f523c31134e6f2fae4004c49` |
| Full resulting pack 0 | 195,104,768 | `a1641718c8bf72013df5395b10076c515cf1509e20cc0407afa440f8c7bce886` |

The atlas retains its original 32-byte wrapper and allocation. A 128-color
quantization fits 2,386 encoded bytes in its 2,400-byte compressed-body budget;
the 256-color attempt correctly refuses even with optimal parsing. Native
`0x4dc00` decompression at the actual overlapping source/destination placement
matches host decoding byte for byte for both changed resources.

The runtime **hook instructions are unchanged**. Clean-source CLI preflight
selects the same sites as the witness: RX `0x14ba2c0`, 1,408 bytes; RW
`0x14bb000`, 128 bytes. Code hash at those addresses is
`153641d86041b1bdc6e39c10310fa8e40b930c3edf8439c07a7421e854ce1b96`.

| Hook | Retail call | Installed call |
| --- | --- | --- |
| Setup `0xfce56` | `e845f3ffff` | `e865d43b01` |
| Update `0xfcfa2` | `e819faffff` | `e84bd43b01` |

The clean-source full/hook/neutral/pair XBE is 12,029,952 bytes, hash
`834b36b20e1a65f4200c027a5f26baa45ddf169f8c2cf801b399182718320ac4`.
The static/resources/transport XBE stays 11,948,032 bytes, hash
`630c645f47576502507c08a64dbf32c8f99472e9c1485379279f8524ab0bf883`.
Additional selected owners can select the larger v3 layout and different
sites; the existing union and both composition orders pass the XBE gates.
The original witness's v1 runtime scene and appendix hashes were reproduced
before changing layout, so there is no evidence of a mismatched compiler
version in that witness.

### Writer fixes supporting the matrix

Pack compilation, status, hashing, preview and transport now use descriptor
views with 1 MiB streamed blocks. The compiler retains one owned HUD, its
small index and appendix, not an entire archive. An attempted whole-pack
slice explicitly refuses. Only the small XBE and bounded owned resources are
materialized. Encoded panel caching is limited to 66 team/side sets, with
actual pinned source bytes in the key.

No-hook controls use the existing retail-sized XBE extent with readback; the
general grown-XBE writer deliberately does not accept that size. A later
XBE-only change for an already-reserved owner now leaves the already-installed
pack at its current extent instead of appending it and demanding a nonexistent
resource-change hash. Fault injection covers partial pack writes, both
directory nodes, grown and same-size XBE writes, rollback, unchanged adjacent
files and exact idempotence. Copy publication closes every handle before
`os.replace`. These are offline writer repairs; neither is offered as the
cause of the already-built witness's gameplay freeze.

## Bisect matrix for xemu, approximately one hour

Use the supplied CLI after integration/import of this commit. Start with a
clean retail source, default 4:3 output, TB at NE exhibition, the same game
settings, and no optional widescreen/kickoff/Hi-res/music edits. Each row is a
new build from that source. Do not apply profiles on top of one another.
Old v7/v1 and other profiles intentionally refuse. Generated receipts remain
beside the output as `OUTPUT.scorebug.json`; retain one per run.

| Profile | Runtime hooks | Appended TXTRs | Appendix bytes | Sector growth in pack 0 | Additional native heap bytes |
| --- | --- | --- | --- | --- | --- |
| Static, no runtime flag | no | 0 | 0 | 0 | 0 |
| `transport` | no | 0 | 0 | 0 | 0 |
| `hooks` | yes | 0 | 0 | 0 | 0 |
| `resources` | no | 264 | 1,393,920 | 1,394,688 | 1,419,264 |
| `neutral` | yes | 8 | 42,240 | 43,008 | 43,008 |
| `pair` | yes | 24 | 126,720 | 126,976 | 129,024 |
| `full` | yes | 264 | 1,393,920 | 1,394,688 | 1,419,264 |

All six runtime probes use the same v8 binding scene and pack-tail publication
path. `transport` isolates that common change from hooks and extra textures.
`hooks` runs the real hook binary with absent panels, testing its NULL path;
the side materials are expected to be hidden. `resources` loads the full
appendix but leaves both native call sites untouched. Its panel appearance
is not an acceptance criterion because the binding/visibility hooks are
absent. `neutral` has four timeout variants for each side. `pair` adds TB
(asset `27`) and NE (`16`), all four variants in both orientations; other teams
use neutral fallback. `full` retains all 32 NFL identities plus neutral.

Hook-bearing rows also install the existing grown RX/RW allocation; no-hook
rows retain a retail-sized XBE. A hooks-only failure therefore narrows to the
hook/allocation/XBE-transport lane, not uniquely to one instruction. Texture
heap numbers exclude that executable allocation and other game consumers.
Native material binding can cause resources to be consumed differently by
the GPU, so a resources-only pass does not establish combined runtime safety.

Concrete recipes, with quoted local paths selected by the tester:

```bash
SCOREBUG_SOURCE='/path/to/clean-retail.xiso.iso'
SCOREBUG_OUTPUT='/path/to/disposable/scorebug-test.iso'

# Static v8 control and complete-frame capture first.
python3 -m tools.nfl2k5_scorebug_reference apply "$SCOREBUG_SOURCE" "$SCOREBUG_OUTPUT" --overwrite
python3 -m tools.nfl2k5_scorebug_reference status "$SCOREBUG_OUTPUT"

# Run one profile, boot it, record the result and retain its receipt.
# Repeat this block with hooks, resources, neutral, pair, then full.
SCOREBUG_PROBE=transport
python3 -m tools.nfl2k5_scorebug_reference apply "$SCOREBUG_SOURCE" "$SCOREBUG_OUTPUT" --overwrite --runtime-probe "$SCOREBUG_PROBE"
python3 -m tools.nfl2k5_scorebug_reference status "$SCOREBUG_OUTPUT" --runtime-probe "$SCOREBUG_PROBE"
cp "$SCOREBUG_OUTPUT.scorebug.json" "$SCOREBUG_OUTPUT.$SCOREBUG_PROBE.json"
```

Do not run these commands against the mounted source or reuse a patched
output as the source. Close xemu before replacing its image. Reuse one
disposable output between boots; publication temporarily needs room for both
the previous output and a replacement. Delete the previous disposable output
first if needed to preserve the main-drive 100 GB free-space floor. Each
runtime output grows by roughly 0.2 GB because the pack is relocated; the
1.39 MB appendix is not the full image-growth figure. Build time depends on
disc I/O. Allow about 5 minutes for the static capture, 5 minutes per probe
for entry and a few plays, and the remaining time to repeat the discriminating
case. Record slow loading separately from a persistent freeze.

Interpret the first reproducible split:

| Result | Next inference/action |
| --- | --- |
| Static passes, transport fails | Inspect runtime SCNE binding changes, collection extent lookup and pack relocation; neither hooks nor extra textures are required. |
| Transport passes, hooks fails | Inspect the hook/allocator/XBE-transport lane; obtain the stopped PC and FXSAVE/stack/scene state. |
| Transport passes, resources fails | Extra loading or resource residency is sufficient; compare neutral/pair and collect loader cursor/end, I/O status and heap state. |
| Neutral passes, pair/full fails | Resource-count, particular-resource or GPU pressure hypothesis strengthens; reverse TB/NE and compare a neutral-fallback matchup. This is not yet a proved memory threshold. |
| Hooks and resources pass separately, their combination fails | Inspect setup binding, descriptor lifetime and GPU use, including memory shared with grown executable pages. |
| All clean-source rows pass | Recreate the tester's complete flag/allocator union, adding widescreen and other flags one at a time; the failure may require a composition or mode. |

### Noah's witness list

- Record the exact xemu build, host, game mode, guest output dimensions,
  source identity, selected flags and saved per-profile receipt. Retain the
  earlier two-launch retry as a reported persistent failure, not a reason to
  dismiss a repeated freeze.
- Static v8: capture the entire uncropped 4:3 frame at kickoff and during
  ordinary play, including both score cells, full clock strip and bottom
  margin. Compare to the reference and these native-projection PNGs. Repeat
  with the widescreen patch and its documented display setup. Check both
  possession directions, live yellow abbreviation, 00..99 scores, OT labels,
  long down-and-distance strings, scoring rotation, lineup/replay transitions
  and the raised kick meter.
- For each diagnostic row, record front-end success, entry-to-game success,
  time to first live frame, several plays, return to front end and a second
  game. Run TB at NE and reverse it for `pair`; try another matchup for neutral
  fallback. On the discriminating row, repeat in franchise and exhibition.
- On a runtime row that plays, use timeouts 3..0 on both sides; verify score
  flashes, possession/down/field-position refresh, created-team neutral
  fallback, and play-clock color at 5.0, just below 5, 1 and 0. Check reentry
  and cold boot for stale descriptors or memory growth.
- On a persistent freeze, save xemu's log and stopped guest PC/stack if its
  debugger is available. Useful state: loader busy `0xb09584`, cursor
  `0xb09598/9c`, end `0xb095a0/a4`, heap pointer `[0xb12034]` and its `+0x88`
  free counter, and the object passed in ECX to `0x33660`, especially `+8`.
  This does not require a local Ghidra project. Without a debugger, the first
  pass/fail split, exact build and log are still useful evidence.

## Native runtime investigation

The new standalone native suite uses the actual retail instructions with
bounded host I/O completion events and native allocations. It extends the
earlier fixture, which entered registration through `0x43e30` and did not
execute the asynchronous continuation through `0x43e10` back to the reader.

| Native path | PROVED within the fixture |
| --- | --- |
| `0x43a20` collection reader, `0x438d0` header dispatch | Uses a 64-bit cursor and collection end, not an old fixed TXTR count. Handler tags come from the linked list at `0xb0957c`. |
| `0x44f10 -> 0x44e60 -> 0x437d0 -> 0x48700 -> 0x483d0` | Real TXTR allocation and alignment; native heap at `[0xb12034]`. |
| `0x44df0 -> 0x43e10 -> 0x43d20 -> 0x44da0 -> 0x34df0 -> 0x34c10 -> 0x43a20` | Real completion, relocation, registration and next-header continuation; no nested synchronous fake I/O completion. |
| `0x449e0 -> 0x443d0 -> 0x30c40` | Ordinary collection lookup is finite; `0x30c40` is UTF-16 equality, returning 1/0. Missing resources ultimately return NULL. |
| Setup and update hooks | Bounded missing-name and neutral fallback, native descriptor binding, original calls and stack cleanup, registers/flags and FXSAVE/FXRSTOR state preserved. |

The entire old sequence of 139 wrappers is preserved. It includes five AUSB
wrappers after the last old TXTR; there is no end sentinel to replace. Every
new uncompressed wrapper is 5,280 bytes and advances the ordinary reader.
Sector padding belongs outside the collection's logical end. Index tests
check all 4,323 entries, virtual-to-physical mappings across pack boundaries,
every unchanged old wrapper, and the complete unchanged suffix in bounded
blocks. Outer 346's size changes from 2,977,184 to 4,371,104; later virtual
offsets and the pack-0 sector count shift by 681 sectors. Other packs retain
their physical contents.

Exact native collection results, using the compiled full pack:

| Fixture end | Header/body completion events | Registered TXTRs | Native heap bytes consumed |
| --- | --- | --- | --- |
| Old outer end | 188 | 44 | 678,144 |
| New outer end | 716 | 308 | 2,097,408 |
| Difference | 528 | 264 | 1,419,264 |

Both end exactly at their supplied end, close the fixture collection and
clear `0xb09584`. The largest callback takes 811,219 instructions on an old
compressed resource, below the 1,500,000 bound. All 264 appended descriptors
then exist before the explicit setup invocation and TB/NE bind correctly.
Using the old end instead simply omits the appendix: setup gets NULL and
hides the side materials; name lookup does not wait for a future resource.

With only 1 KiB of heap and a cursor beginning at the appendix, all 264
allocations fail, all 264 header callbacks advance, no TXTR registers, and
the collection still completes. Subsequent setup/update return with NULL
panels. Therefore this particular allocation-failure path does not prove
the proposed memory-pressure spin. Other game allocations and GPU handling
of low memory remain outside that test.

The fixture registers the real TXTR and AUSB handlers; unrelated retail
resource handlers are skipped. It executes compressed TXTR/AUSB loading and
tests the changed SCNE's decompression and complete scene relocation
separately. It seeds the collection end from compiled outer metadata; it
does **not** execute native XDVDFS/VFS opening through
`0x43db0 -> 0x48ef0 -> 0x3a530/0x3ab70`. File I/O submission/close and the
empty next-collection queue are host boundaries. Thus successful continuation
does not prove the console reads the new end, that its OS completes every
request, or that real game setup waits for exactly this collection lifetime.
Special lookup contexts at `+0x10/+0x14` are not covered by the ordinary
collection fixture. Those are remaining investigation boundaries.

The existing 12-test runtime suite covers all asset identities, missing and
created-team fallback, timeout bounds, score-flash decay, down refresh,
scene/visibility guards, invalid delta times and the exact under-five clock
boundary. The update hook calls native `0xfc9c0` once with correct `RET 4`
forwarding. It performs no per-frame allocation or file I/O. Its instructions
were left unchanged because these paths expose no failure.

### Real waits consistent with the symptom, still HYPOTHESIS

`0x432d0` repeatedly calls loader predicate `0x432c0` and event pump `0x38f50`
while the collection busy state is set. Suppressing completion keeps it in
that loop; clearing the state lets it return. Audio on another thread can
continue while this caller waits. A pending request whose completion never
runs is consistent with the witness, but no live request status is supplied.

`0x33660`, reached by render-drain paths including `0x28de0/0x28f40`, polls an
object's `+8` flag and yields through `0x341a0`. Native `0x334e0` sets that
flag and emits a GPU callback packet (`0x81d8c`) carrying callback `0x33410`;
the callback clears `+8`. Withholding completion makes the fixture hit its
instruction bound; clearing the flag permits return. This is a GPU completion
wait, distinct from the collection wait. The fixture does not execute GPU
commands or establish which drain call was active in the tester's game.

Both loops match the broad symptom. Neither can responsibly be declared
the observed hang location without the matrix or a stopped guest trace.

## Resident memory budget and relevance to Hi-res packs

Each new texture is a native 128x32, one-mip P8 TXTR: 4,096 pixel bytes,
1,024 palette bytes and 128 system bytes. The 32-byte wrapper is disk
metadata. Native heap allocation adds its own 128-byte header and rounds to
128 bytes, so `round_up(5,248 + 128, 128) = 5,376` resident heap bytes per
object. There is no compressed overlap scratch for these uncompressed panels.

| Full-set component | Bytes |
| --- | --- |
| Pixels, 264 x 4,096 | 1,081,344 |
| Palettes, 264 x 1,024 | 270,336 |
| Video payload total | 1,351,680 |
| System bodies, 264 x 128 | 33,792 |
| Heap headers/alignment, 264 x 128 | 33,792 |
| **Measured additional native heap occupancy** | **1,419,264 (1.3535 MiB)** |

The appendix is 1,393,920 bytes on disc, or 1,394,688 after sector growth.
Those are distinct figures. All 264 objects load with the HUD even though
setup selects only eight descriptors for the current two teams. Choosing
two teams at runtime does not free the other resident variants. The 8 MiB
heap in the test is an explicit fixture size, not a claimed production HUD
heap size; its total occupancy is not the full game's resource budget.

The retail heap is dynamically sized. Native `0x326e0` probes for the largest
contiguous physical allocation starting at 64 MiB and stepping down by 4 KiB,
then allocates that successful size minus the **2 MiB** reserve at `0xa6d324`.
It aligns the pool and respects the physical cap ending at `0x84000000`.
Working bounds are held at `0xb018b0/0xb018b4`; the remaining engine heap is
initialized at `0xb04e24` through `0x48640` in the startup path at `0x38fc0`.
This is distinct from the XBE virtual-section allocator.

Other startup consumers reduce the available pool. The audio path at
`0x3c960` reserves **4,792,320 bytes** from `0xa70878`, plus its small header
and alignment. Video and other consumers include runtime-configured sizes
such as `0xa6aa08`; its initial file value is not a runtime watermark. The
retail executable therefore does not supply a fixed number of free HUD
megabytes that can certify this feature.

**HYPOTHESIS:** another 1.35 MiB, about 2.1% of nominal 64 MiB, can plausibly
exhaust a nearly full or fragmented pool, particularly alongside other
features. The direct TXTR OOM path above still returns, so that observation
alone cannot establish a hang. The Hi-res work must budget decoded system
and video bytes, all mip levels and palettes, heap headers/alignment and
compressed overlap scratch, then measure actual live headroom and lifetime.
Compressed file growth is not a resident-memory estimate. A reduced probe
that passes while the full set fails is useful evidence, not by itself proof
that the native heap rather than GPU use or a specific resource is responsible.

## Padded-rip tooling decision

The historical `tools/build_softdrink_modpacks60.py` remains a canonical
release-reproduction tool. Its whole-disc size/hash gate proves the exact
baseline layout, padding and length needed for that release comparison.
Source-cache agreement on logical pack and inventory hashes proves a
different, useful property; it does not prove identical whole-disc release
bytes. Its docstring and refusal now explain this and direct padded sources
to Studio Build or the scorebug CLI. The gate was intentionally not weakened.

The tester's 6,300,958,720-byte rip is 458,752 bytes larger than the canonical
6,300,499,968-byte image. The scorebug CLI checks logical XDVDFS extents and
pinned owned resources, not canonical total image length. Its transport
test includes that amount of trailing padding and succeeds. The reported
all-pack source-cache proof remains the tester's evidence; this session did
not independently inspect the tester's separate disc. The historical proof
builder was not run and should not be used for the diagnostic matrix.

## Validation and handoff

All suites were run standalone with plain `python3`, no emulator, display,
audio or network. Retail evidence, Pillow, Capstone and Unicorn are available
here; these runs had no skips. Evidence-dependent tests declare precise skips
when their required local inputs/dependencies are absent. Suite details and
source fingerprints are recorded in `docs/scorebug_ingame/validation.json`.

| Command suffix after `python3` | Result |
| --- | --- |
| `tests/mod_editor/test_nfl2k5_scorebug_ingame.py` | 11 passed |
| `tests/mod_editor/test_nfl2k5_scorebug_runtime.py` | 12 passed |
| `tests/mod_editor/test_nfl2k5_scorebug_resources.py` | 6 passed |
| `tests/mod_editor/test_nfl2k5_scorebug_native.py` | 4 passed |
| `tests/mod_editor/test_nfl2k5_scorebug_projection.py` | 4 passed |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 59 passed |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 71 passed |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` with the private manifest environment below | 28 passed |

Both capability handoff rows pass semantic/schema validation when merged in
memory, and all paths and module commands in those two rows pass file checks.
Full-registry file checking stops at the pre-existing missing
`docs/research/apf_audio.md`; no unrelated evidence was fabricated. Both CLI
help paths, the native PNG generator and Python syntax checks also pass.

The runtime suite peaked at 271,480 KiB RSS, native collection at 206,672 KiB,
and the final resource/transaction suite at 161,220 KiB, all below 2 GiB.
Pack reads are streamed and synthetic acceptance discs are temporary and
deleted on completion/failure. No real disc build was started: main-drive
free space was too close to the 100 GB floor for a 6.3 GB temporary copy.
Only small logs/JSON/helper scripts and the delivery bundle remain in
`.scratch/`, below 200 MB; no pack or disc copy remains there.

The production `data/nfl2k5_cave_reservations.json` is protected and unchanged.
Its default source-drift guard correctly sees the six modified fingerprinted
files. For local manifest validation, `.scratch/check_manifest.py` retained
the released conservative reservation union, reobserved affected XBE writers
in both legacy and complete v3 layouts, checked idempotence and section
digests, and incorporated 530 observed spans. The test command was:

```bash
NFL2K5_CAVE_MANIFEST="$PWD/.scratch/current-cave-manifest.json" \
  python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
```

This is **private XBE ownership revalidation**, not the canonical real-disc
manifest build. Claude must perform the protected regeneration and default
manifest test after wiring; the private candidate must not be copied into
production. No protected dispatcher, GUI, packaging, release, CI, manifest
or allocator-budget file was edited. `WIRING.md` specifies every existing
dispatcher/status/BuildPlan contract, the runtime preset change, exact GUI
wording, allowlist/import requirements and schema-valid capability objects.

The handoff keeps the unresolved gameplay failure prominent. Completion of
offline checks establishes the documented bounded behaviors and exact bytes;
it does not turn the tester's negative runtime witness into a positive one.

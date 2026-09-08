# Equipment textures with an independent mip chain

Base: `45c0544a`, branch `astra/r64-equipment-texture-chain`. Status:
**EXPERIMENTAL / UNWITNESSED**. The writer, Studio service, owned dialog,
project transport, source pins and tests are implemented. The protected Studio
panel and release files require the exact integration in `WIRING.md`; this
branch does not claim a packaged release or a played-game result.

The successful real-file proof imports a new shoe design at an **explicitly
chosen 64 x 64 game size**, with all four levels through 8 x 8. Native-size
independent chains did not fit the sampled retail slots, even for very simple
art. The implementation refuses overflow and never silently shrinks an image
or switches to a single level. Original, half and quarter width/height are
explicit choices. Ordinary imports remain palette-only.

## Plain answer for the community

The named shoes and gloves in a uniform package normally share one set of
image indices, including its smaller distance images. Each named variant has
its own colour palette. That is why the existing importer can recolour a shoe
but cannot give just that shoe a different stripe or logo.

Each variant also has its own texture descriptor. We can point that descriptor
at a separate image and a matching set of smaller images, leaving the original
shared images for the other variants. Every smaller image must use the same
colour table and the game's exact ordering. This importer makes those smaller
images from the authored picture, with transparency taken into account.

The new choice is **Give this glove or shoe its own texture**. It keeps the
other variants, including a separately named dirty version, unchanged. Space
is tight: the complete compressed resource must still fit its original slot.
A smaller game image can fit when the original size cannot, at the cost of
fine detail. The proof here fits a new 64 x 64 cleat design. This changes image
artwork, not the shoe mesh, UV coordinates or a player's equipment selection.

The native CPU code accepts and submits a one-level texture. That does not
prove how it will look at distance on the GPU. We kept a complete chain for
the chosen size instead of offering a one-level shortcut. Close and distant
gameplay still needs Noah's check.

## Retail format and native loader evidence

**PROVED on the bounded retail resources:** the streaming census reviewed
all 634 physical uniform sets, with 1,902 glove/shoe TSET spans. The existing
28,530-row equipment catalog still defines the selectors and retail dimensions.
The new hash-only catalog pins the complete compressed spans, including lower
mips, reference tables, alignment gaps and trailing compressed allocation.
It contains no retail texture pixels or executable bytes.

| TSET chunk | Variants per set | Base size | Levels | Shared index bytes | System bytes | Video bytes |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 6, gloves | 8 | 256 x 128 | 5 | 43,648 | 768 | 51,840 |
| 8, shoes | 6 | 256 x 256 | 6 | 87,360 | 640 | 93,568 |
| 9, second shoe family | 6 | 256 x 256 | 6 | 87,360 | 640 | 93,568 |

Every descriptor's retail pixel offset is zero. Each variant owns a distinct
1,024-byte BGRA palette. The shoe layouts contain 64 bytes of alignment space;
there is no unused video tail large enough for an independent image chain.
The original shared chain and every original gap remain byte-exact in the
decoded output, even when every selected variant receives a private chain.
The compressed representation of the entire TSET necessarily changes.

The first decoded word, `0x0D`, is a **field-relative reference pointer**, not
a mip count or a texture version: `field + signed_word - 1` resolves to `0x0C`.
The word at `+4` is the reference count. Records are `0x24` bytes each. Their
embedded `TXTR` marker is at record `+0x0C`, or decoded
`0x18 + reference_index * 0x24`. Name and descriptor pointers follow that
marker at `+4` and `+8`, using the same field-relative rule.

| Descriptor offset | Meaning used by the native code |
| --- | --- |
| `+0x00` | Opaque native object/root word; retained |
| `+0x04` | Pixel-chain byte offset relative to the video allocation |
| `+0x08` | Palette byte offset relative to the video allocation |
| `+0x0C` | Packed format; P8 is `0x0B` in bits 8..15 |
| `+0x10` | Packed explicit size, zero for these swizzled textures |
| `+0x14` | Native direct-use flag word, retail `0x80000000` |

Packed-format bits 16..19 give the mip count, 20..23 give log2(width), and
24..27 give log2(height). The glove word is `0x07850B29`; the shoe word is
`0x08860B29`. Each level is swizzled separately, then concatenated. Its start
is the descriptor's pixel offset plus all preceding `width * height` sizes.

| Shoe level | Dimensions | Byte offset from chain start |
| ---: | --- | ---: |
| 0 | 256 x 256 | 0 |
| 1 | 128 x 128 | 65,536 |
| 2 | 64 x 64 | 81,920 |
| 3 | 32 x 32 | 86,016 |
| 4 | 16 x 16 | 87,040 |
| 5 | 8 x 8 | 87,296 |

Glove offsets are 0, 32,768, 40,960, 43,008 and 43,520, for levels
256 x 128 through 16 x 8. There is one palette for the complete chain, not
one palette per level.

**PROVED by Ghidra/raw retail disassembly and bounded CPU instruction tests:**

| Address | Evidence and implication |
| --- | --- |
| `0x45300` | Registers the TSET resource handlers |
| `0x45280` | Begins the TSET load using the stored resource length |
| `0x451D0` | Allocates wrapper `system_bytes + video_bytes + overlap_scratch_bytes`; an increased video size is honored |
| `0x45100` | Completion walks the field-relative references at stride `0x24` |
| `0x450B0` -> `0x34DF0` | Each texture callback relocates that descriptor's pixel and palette offsets independently using the video base |
| `0x34C10` | Checks pixel alignment of 128 bytes and palette alignment of 64 bytes; a one-level count is accepted |
| `0x31FA0` | Submits the descriptor's format word unchanged to NV2A method `0x1B04`, with pixel address at `0x1B00` and palette at `0x1B20`; addresses use the native 26-bit masks |
| `0x4DC00` | Native VC-LZ decoder accepts the fallback's 10, 11, 12 and 13-bit streams, including in-place decoding with both allocation guards intact |

The native test maps only the pinned executable's sections, a bounded dummy
heap and a stack. External allocator calls are replaced with size-recording
stubs. It checks allocation, independent/sibling relocation, one/full mip
counts, alignment rejection, GPU command words and lossless decompression.
It does not boot the title, emulate a console, execute a GPU or display a GUI.
Ghidra missed some loader bodies as standalone functions, so their raw retail
instructions were also inspected. Selected decompiler text remains in
`.scratch/loader_functions.c`.

Retail executable SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
The source pin catalog is 145,141 bytes, SHA-256
`cb15ecd9ef3f87f45c3cfc4a7fc583636b236835fbbedec073c50dc45706b0bc`.

**HYPOTHESIS, not a runtime witness:** a one-level descriptor should restrict
sampling to its base image rather than reading neighboring palette/texture
bytes as missing mips. Neither actual distance filtering nor sampler clamp,
bias and material state has been proved here. The implemented route therefore
supplies every level retained by the explicit size choice. The compact
descriptor's normalized UV mapping and increased residency also need gameplay
validation. Native allocation success is not proof of enough free game memory.

## Implementation and refusal contract

`nfl2k5_uniform_equipment_writer.py` allocates private chains at a 128-byte
boundary after all original video bytes. It updates only the selected pixel
pointers and, for an explicit smaller size, the selected packed dimensions
and mip count. The selected palette keeps its original allocation. Unselected
descriptors, names, palettes and decoded pixels at **every** mip are checked
byte-for-byte. Multiple selected variants, including a mix of palette and
private-chain edits, compile in stable reference order into one physical edit.

The existing number-sheet encoder supplies direct-from-base, premultiplied
area-filtered mips and a shared coverage-aware palette. The image is still
supplied at its catalog dimensions. Scale 2 or 4 selects the appropriate
coverage-filtered base and all following levels, with no resizing guess.
The new path tries palette budgets 256, 128, 64, 32 and 16. Protected coverage
and authored colour rules can reject a tier. The existing palette-only path
keeps its prior 256 through 2 colour tiers and prior shared-index projection.

The VC-LZ slot itself never grows. The source distance geometry is tried
first, followed by deduplicated retail-observed 10/11/12-bit alternatives.
Within each geometry, the existing greedy encoder runs first. The added
`nfl2k5_equipment_lz.py` fallback chooses tokens by minimum total bit cost:
9 bits per literal or 17 per match, including the flag bit. It keeps the same
stream grammar and native non-overlapping match rule (`length <= distance`).
Every result is independently decoded and compared with the complete input.
The wrapper scratch size is recalculated with the existing exact in-place
overlap validator, including zero-padding protection.

The optimal search is capped at 50 million candidate comparisons. Package
reads are capped at 32 MiB and decoded TSET allocations at 2 MiB; source pack
hashing streams 16 MiB blocks. A work-limit refusal is a refusal, not a reason
to lower image size or coverage. Single test processes stayed below 2 GiB.
These are implementation bounds, not an asserted safe game-memory budget.

`nfl2k5_equipment_import.py` freezes the PNG and chosen mode, preflights every
currently staged sibling in the same TSET against the shared compression
budget, and only then commits one undoable `StudioSession.replace_batch`.
Failure leaves replacement files, project state, prior authoring master and
Undo unchanged. Temporary candidate PNGs are removed on exit. Source and
output game files are never modified during preflight. Source restoration
removes the selected edit, preflighting any remaining siblings.

An ordinary PNG means palette-only. A private ancillary PNG chunk, `npTC`,
stores a versioned mode, target ID, decoded RGBA digest and explicit scale.
The final uppercase letter marks it unsafe to copy after image editing.
CRC failures, duplicates, wrong targets, stale pixel digests and unsupported
families/sizes are refused. The mode travels with the exact user-authored PNG
through project save/load, existing snapshots and Undo. No second settings
ledger or public project schema change is needed. Equal base pixels with an
explicit private chain can be a real edit because its lower levels and
descriptor ownership differ; equality checks now include mode and size.

The facade and owned dialog are present. The checkbox defaults off and the
size defaults to original; the size chooser is enabled only for an explicitly
selected, reviewed glove/shoe. The plain help explains distance images, the
size/detail tradeoff, additional game memory and the unwitnessed status.
The protected GUI proposal preserves the existing fitted-image and authoring
master workflow. Cancellation starts no task; failed preflight cleans only
the pending master; replay preserves the prior master and does not mark the
workspace dirty. Exact patch and release integration are in `WIRING.md`.
The editing preview remains the full-size authored PNG; build preview
artifacts contain the actual encoded base. The import result states the game
dimensions and any colour approximation.

Receipts include original/replacement span and decoded hashes, requested and
encoded dimensions, mode, descriptor/palette/pixel offsets, every mip's
requested/decoded hash and pixel error, palette quality, compression strategy,
fit attempts, padding, scratch and total native allocation. The final unified
receipt distinguishes palette-only edits from private chains and never claims
runtime visibility. `apply_equipment_span` accepts only the exact before/after
hashes, refuses mixed or foreign bytes, and returns `changed=False` on replay.
The existing disc compositor remains responsible for transactional publication
and full-image boundary validation.

## Space experiment and real-file proof

Appending a native shoe chain costs 87,424 aligned video bytes; a half-size
chain costs 21,888; a quarter-size chain costs 5,504. A native glove chain
costs 43,648, a half-size chain 10,880 and a quarter-size chain 2,688. None of
these costs can come from unused decoded tail space in the reviewed layouts.
Source-slot measurements are in `.scratch/source-slot-budgets.json`.

For Tennessee `28H0` shoe `shoes01`, the existing 54,688-byte slot has only
8 unused compressed bytes. Native-size flat-colour and two-part art still
overflowed; the detailed native-size optimal probe needed 60,312 bytes at
10-bit geometry. A simple compact design needed 54,883 bytes with the tested
greedy encoder, also too large. The lossless optimal parse fit the final
64 x 64 design in 54,163 bytes. These are sample results, not a claim that all
other slots have the same capacity or that every compact image will fit.

The successful proof is reproducible with:

```sh
python3 tests/fixtures/prove_equipment_texture_chain.py \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --set 28H0 --texture shoes01 --scale 4 \
  --output .scratch/real-cleat-proof.json
```

It reads one bounded package, authors an original white stripe/sole with teal
and navy sections and a transparent margin, and requests
`tset:3850:8:0:shoes01`. The input is 256 x 256. The explicit game size is
64 x 64, with 32 x 32, 16 x 16 and 8 x 8 distance levels. All four decoded
levels match the direct coverage-filtered source **exactly**, including alpha;
all five siblings match every one of their six retail levels. The selected
base differs from its corresponding retail level in 12,561 channel values.

| Measured result | Value |
| --- | --- |
| Palette entries | 8, at the first 256-entry budget; zero colour/alpha error |
| Private chain offsets in video | 93,568; 97,664; 98,688; 98,944 |
| System bytes | 640, unchanged |
| Video bytes | 93,568 -> 99,072 |
| Compressed bytes / stored bound | 54,163 / 54,688 |
| Lossless encoder | Optimal token parse, 12-bit distance geometry |
| Zero padding | 525 bytes |
| Exact overlap minimum / allocated scratch | 509 / 528 bytes |
| Total native allocation | 100,240 bytes, an increase of 6,016 including scratch |
| Complete physical TSET span | 54,720 bytes, unchanged |
| Disposable source window | 54,784 bytes, including 32-byte guards on each side |
| Reopened decoded result | Exact; both guards preserved |
| Replay | Exact bytes; `changed=False` |

The small actual source window was written using the production offset writer,
closed, reopened and independently decoded. The read-only retail source span
was reread to confirm its hash. All temporary artwork and window files were
deleted. No ISO, pack copy or persistent retail-art output was created.
The final repeat produced the same output hash in 6.52 seconds, with peak RSS
147,468 KiB as measured by `/usr/bin/time`.

Before span SHA-256:
`499c92c4cf6ee00efdf84c4a241f92d680a96fc41e32e5d97d5b2b3f5b370ba4`.
After span SHA-256:
`6ff4d188fa15f5cd9ed8955d094ba58a90923d8ad7f6d83f5073d3a3720f17fb`.
The complete local receipt is `.scratch/real-cleat-proof.json`; scratch is
intentionally not committed. The fixture recreates the authored design.

The source pin census command was:

```sh
python3 tools/nfl2k5_equipment_chain_census.py \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --output mod_editor/data/nfl2k5_equipment_chain_pins.v1.json
```

It produced 1,902 unique pins and the three exact layout populations above.
Use a new output path when reproducing it; the tool refuses to overwrite.

## Validation

All new tests run standalone with `python3 file.py`, without PYTHONPATH.
Qt tests use `QT_QPA_PLATFORM=offscreen`. Synthetic fixtures exercise actual
parsers, codecs, source guards and Studio transactions; only the external
archive/catalog boundary is substituted. Native tests precisely skip if the
private executable or Unicorn is absent, and reject a present foreign XBE.

| Command | Final result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_equipment_texture_chain.py` | 16 passed |
| `python3 tests/mod_editor/test_nfl2k5_equipment_texture_native.py` | 5 passed; counts 1, 3, 4, 5 and 6 exercised |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_equipment_import.py` | 11 passed |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_equipment_import_wiring.py` | 6 passed; protected patch applied and executed only in memory |
| `PYTHONPATH=.:tools QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_2k5_uniform_equipment_export.py` | 16 run, 12 passed, 4 private-fixture skips |
| `PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_extended_visuals.py` | 9 passed |
| `python3 tests/mod_editor/test_studio_session.py` | 18 passed |
| `python3 tests/mod_editor/test_uniform_bundle_cross_project.py` | 8 passed |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_team_kit_product_integration.py` | 7 passed |
| `PYTHONPATH=.:tools python3 tests/mod_editor/test_providers.py` | 33 passed |
| `python3 tests/mod_editor/test_provider_integrity.py` | 7 passed; exact 237-module execution closure plus source data pins |
| `python3 tests/mod_editor/test_nfl2k5_digit_sheet_quality.py` | 13 run, 12 passed, 1 private-fixture skip |
| `python3 tests/mod_editor/test_audio_annotation_project_archive.py` | 6 passed |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 91 passed; 354.91 s wall, 316,640 KiB peak RSS |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 103 passed; 443.86 s wall, 506,500 KiB peak RSS |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 run, 27 passed, 1 expected baseline error: stale reservation source `mod_editor/core/nfl2k5_espn25_scenarios.py` |

The two XBE gates used `/usr/bin/time` to record elapsed time and peak RSS.
Their complete logs and the other outputs are in `.scratch/`. No XBE owner
was added because this feature edits resource data, not executable code.
The protected cave manifest was not regenerated.

Three older suites in the table need the stated PYTHONPATH because they lack
their own standalone bootstrap. Some existing catalog tests initially lacked
their ignored report inputs. Seven metadata-only reports were copied from
the available read-only evidence tree and the affected tests rerun; no game
art or archive pack was copied. The provider integrity expectations were
updated for the two actual new import dependencies and the new data pin;
hash checks were retained. Initial import, fixture and handoff issues were
fixed before the final results above.
The 115-entry capability registry loads with schema validation and all new
evidence paths present. `git diff --check` and `git apply --check` for the
protected GUI fixture pass. Every named protected file is byte-identical to
HEAD.

## Known limits and Noah's witness list

**UNWITNESSED:** rendered appearance, distant filtering, compact-size UV
behavior, material alpha handling, clean/dirty switching, residency with both
teams, long sessions and compatibility with other texture-memory changes.
The allocation cap is not a measured game heap limit. No single-level option,
mesh modification, UV edit, automatic clean/mud pairing or hi-res integration
is claimed. Only original retail spans matching the catalog can gain a private
chain; the helper's replay gate does not authorize importing an arbitrary
already-modded source disc as retail.

After Claude applies the protected handoff:

1. Load the pinned retail disc, choose Tennessee `28H0`, `shoes01`, and import
   a distinct authored stripe/sole design. Select **Give this glove or shoe
   its own texture** and 64 x 64. Confirm the receipt and preview identify
   that explicit smaller game size in the build artifacts; the Studio editing
   canvas retains the full-size authored picture.
2. Save, reopen, build a separate output, and select a player actually using
   this shoe variant. Check the new design close up, during normal broadcast
   play, and while the camera moves farther away. Look for displaced blocks,
   seams, colour changes, shimmer, disappearing art and alpha fringes.
3. Compare every sibling variant and its separate dirty version. A dirty
   variant is intentionally unchanged unless separately imported. Test wet
   conditions and the clean-to-dirty transition to establish what the game
   selects at runtime.
4. Repeat with a glove (native 256 x 128; explicit compact option 64 x 32),
   checking both hands, close replay and distant play. A fitting shoe slot
   does not guarantee a fitting glove slot; respect preflight refusal.
5. Play with both teams visible, then multiple games and uniform switches.
   Watch for texture loss or load failures as extra private chains consume
   memory. Recheck combinations with any hi-res pack separately.
6. Verify an unchecked import still changes colours only; cancel and a
   deliberate too-detailed overflow leave the prior project intact. Reimport
   the same choice and use Undo/Revert to confirm the intended artwork.

The root filesystem was already around 97 GiB free at the initial check,
below the requested 100 GB headroom. This session performed no disc build.
Scratch contains small logs, source text and JSON, with no retained acceptance
disc or pack copy. Explicit-path staging succeeded in the linked worktree;
delivery uses a normal branch commit, with no bundle fallback or push.
The final pre-delivery filesystem check reported 101 GiB available; the real
proof and research artifacts together occupied about 340 KiB of scratch before
recording delivery metadata.

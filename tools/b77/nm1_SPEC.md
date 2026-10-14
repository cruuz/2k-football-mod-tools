# nm1 technical handoff: controlled-player surnames

This is the initial static audit. The coordinator subsequently authorized atlas
plumbing and a private, mechanically repacked retail placeholder. The current
authoring contract is [nm1_ATLAS_SPEC.md](nm1_ATLAS_SPEC.md), which supersedes the
provisional dimensions and size below. The implementation is in
`mod_editor/core/nfl2k5_indicator_names.py`; live validation remains separate.

## What is established

`nm1_audit.py` reads retail, public v0.6 and the v0.6.1 base directly. It compares
the indicator predicate, collection, default initializer, name/number drawing,
font setup and submission. Those spans are byte-identical across all three
inputs. The projection helper has the same six changed bytes in both mod discs;
the two calls at 0xFA2A1 and 0xFA31E target the widescreen projection wrapper
0x4715A. This is not evidence of a newly introduced v0.6.1 suppression.

The option at 0xE5FF90 has three labels: Name, Number & Position, None. The
initializer at 0x77C84 writes zero, Name, on all three discs. A loaded save may
override that default. This audit does not inspect saved settings.

The actual name draw is 0xF9D00. Value zero selects record+0x14; value one formats
number and position; other values skip drawing. The submission at 0xFA185 calls
it only when the collected flag at packet+0x0C bit 0x20 is set. The collector
at 0x75D90 and its native gates need live tracing before changing visibility.
Byte equality does not prove that the surrounding runtime state is unchanged.
MyCareer lists 0x75D90 as a guard; that listing is not an installed hook there.

Noah's video frames inspected at 30:02 and 30:06 show Williams and Elliott
beside a green defensive controller ring. At 33:18 Slye is below the orange
kicker ring, with several other labels and bars overlapping near the line.
These frames demonstrate surviving name drawing. They do not establish the
saved option, each label's runtime caller, or pre/post-snap behavior in all modes.
The disappearance's cause remains unproved.

## Existing glyphs are insufficient

Source: `data/nfl2k5_scorebug_sprite/template.png`, RGBA, 1536 by 512 pixels;
mapping: `data/nfl2k5_scorebug_sprite/layout.json`; compiled atlas: 256 by 512.
The current provenance is b76-s14 broadcast contour work, not the old
`author_default.py` font-based generator. Do not rerun that generator.

The small and label faces contain digits and whole word fragments, including
GOAL, Inch, es, Down, ST, ND, RD, TH and OT. They have no registered standalone
uppercase text letters. The token T in timeout_tab is a complete TIMEOUT panel,
not a letter T. Splitting word tiles might recover some existing letter pixels,
but even the generous union of their token letters lacks `BFJKMPQUVXYZ`.
Segmentation itself has not been validated. The ESPN wordmark is not a name font.
The older scorebug FONT clones retain retail glyphs and cannot supply the missing
authored letters under the brief's existing-glyph constraint.

Source rectangles below are half-open pixel bounds in the 1536 by 512 sheet.
They are source UV regions, not the compiled atlas's repacked UVs.

| Cell | Source rectangle | Native source size |
| --- | --- | --- |
| label_GOAL | [457, 47, 485, 56] | 28 by 9 |
| label_Inch | [100, 300, 124, 309] | 24 by 9 |
| label_es | [136, 300, 148, 309] | 12 by 9 |
| label_Down | [60, 300, 87, 309] | 27 by 9 |
| label_ST | [532, 47, 541, 56] | 9 by 9 |
| label_ND | [545, 47, 556, 56] | 11 by 9 |
| label_RD | [561, 47, 570, 56] | 9 by 9 |
| label_TH | [574, 47, 583, 56] | 9 by 9 |

## Required Opus art work

Historical proposal only. Use `nm1_ATLAS_SPEC.md` for the implemented 256x128
atlas, 11-pixel cap height, metrics and disc location. The coordinator has
assigned the complete alphabet to the Opus HUD art job; the earlier stop below
no longer blocks technical work or the authorized private placeholder.

The wave's rule 6 says: "When a fix needs new artwork (new textures, logos, fonts
or models), stop at a precise technical spec." Completing arbitrary surnames
requires missing glyphs, so this handoff stops at that boundary.

Proposed deliverables, pending Opus's choice to authorize this extension of the
existing-glyph-only brief:

- `data/nfl2k5_indicator_names/glyphs.png`: transparent RGBA coverage sheet, 512
  by 128 pixels. It should contain individual uppercase A-Z, digits, apostrophe,
  hyphen and period, plus a blank space advance. Reuse existing authored pixels
  where appropriate. Opus owns the missing letter drawing and visual approval.
- `data/nfl2k5_indicator_names/glyphs.json`: per-character half-open pixel
  rectangle, baseline, advance and provenance. A simple proposed allocation is
  16 columns of 32 by 32 cells. Character order is A-Z, 0-9, apostrophe, hyphen,
  period, space. Cell i begins at `(32*(i%16), 32*(i//16))`; unused fourth-row
  cells remain transparent. This is a proposed independent sheet, not a claim
  that spare space exists in the current scorebug atlas.
- Keep white ink in alpha, with at least four clear pixels on each cell edge.
  Supply baseline-aligned glyphs, not a font file. No external fonts or downloads.
  Keep existing scorebug cells and the ESPN wordmark intact.

Mechanical trial parameters: 14 HUD-pixel cap height, white foreground, dark
RGB (16,16,16) outline. Both 1-pixel and 2-pixel eight-neighbor dilation rings
are supplied for comparison at 4x. Fourteen is provisional, based on the roughly
low-30-pixel name height in Noah's 1080p video, not a measured retail capture.
Final size must be measured against retail. Opus chooses the ring and approves
the look. Uppercase presentation is also provisional; case-preserving names
would require a lowercase set and corresponding extra cells.

The offline previews use only the already-authored whole GOAL tile. They are
coverage and outline demonstrations, not player surnames or runtime evidence.

## Work still required after the art boundary

Cold-boot retail, public and base under the shared emulator lock with the pad
guard, private display, config, HDD and EEPROM. Capture all three option values
on offense and defense before and during plays. Trace 0xE5FF90, selected human
entities, the collector's label flag and the name-draw caller in the same frames.
Identify the cause before changing gates. Distinguish CPU/star labels and human
labels, preserve None and Number & Position, and test all human controller slots.

Then implement the common human label path with last-name lookup, bounded text,
native screen projection, the authored atlas and the selected outline. A scoped
native font or sprite resource is needed; the scorebug is a sprite atlas rather
than a drop-in registered FONT. Prove its resource lifetime and memory budget.
Do not globally replace a retail font. Add the Studio build path and native repair
tool with pinned hashes, replay, full-disc scope and Studio equality receipts.

The before/after live matrix, return, two-pad attempt, tests of runtime behavior,
packaging pins for any new runtime modules and actual surname previews remain
unfinished. There is no `nm1_repair.py` because no repair has been implemented.

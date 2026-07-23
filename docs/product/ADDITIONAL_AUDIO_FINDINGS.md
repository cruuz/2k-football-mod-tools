# NFL 2K5 Audio Product Boundary

## Shipped boundary

2K5 Mod Studio can browse, preview, and export all 850 indexed standalone
`AUDO` resources. Replacement is enabled for all 850 physical resources:

- the existing fixed `menu-back_01` route; and
- 849 additional exact physical resources through the unified project builder
  (805 mono and 44 stereo).

Of those 849 generic slots, 697 have duplicate names, equal decoded-content
siblings, or both. Their physical spans are still distinct and non-overlapping,
so authoring one exact outer/chunk target cannot overwrite its sibling. The
current runtime evidence cannot say which in-game event requests every sibling;
Mod Studio therefore enables the exact physical writer while showing a semantic
ownership warning instead of presenting a guessed cue identity as fact.

The current default v4 complete replacement pack covers all 850 standalone
rows in canonical physical order. Its empty authoring hand-off contains only a
guide, metadata manifest, spreadsheet-safe `AUDIO-CUE-MAP.csv`, and empty
replacements directory—never original game audio. The read-only cue map joins
each generic replacement path to its public asset ID, display name, family,
exact WAV contract, product edit route, and honest runtime-meaning status. It
contains no decoded PCM, private fingerprints, physical game offsets, or
rollback bytes, and its hash is checked before import. Old v3 all-850 packs
remain accepted. The legacy v1 pack intentionally remains 153 cues: Menu Back
plus the originally exposed 152 rows, with its frozen membership/order
preserving old packs. A v2 Selected Shortlist pack can contain any ordered
1–256 standalone rows or exact Editable AUSB ranges.

The Audio browser derives the same canonical ordinal for every standalone row
and shows its exact v4 `replacements/NNN__selected-audio.wav` destination in the
detail card. **Copy pack path** (Ctrl+Shift+C) copies only that public relative
path on explicit activation. Streaming banks, indexed AUSB ranges, and opaque
raw containers do not show the standalone-only action.

Meaning confidence is also a first-class standalone filter instead of being
mixed into edit status. Its exact public domain matches the v4 CSV: one Menu
Back route, 152 reviewed labels, and 697 provisional labels. Browse pagination
and matching collection export use the same filter. A provisional row remains
Editable at its exact physical slot; only its human/runtime meaning is unproved.

The Audio shortlist can now consume any complete 1–256-row standalone or
playable-streaming result through **Add all matching**. The action re-queries
the current search, scope, family, edit-status, and meaning-confidence filters,
requires the full canonical result and stable count/order, preserves existing
IDs once, and refuses the whole operation if the combined shortlist would
exceed 256. This makes **Reviewed labels (152) → Add all matching → Selected
shortlist v2** a one-action authoring route without changing project data or
staging replacement bytes.

## Authoring contract

Each Editable resource advertises its own exact WAV requirements in the Audio
tab. A replacement must be a strict RIFF/WAVE file with:

- integer PCM16 little-endian samples;
- the selected resource's exact mono/stereo channel count;
- the selected resource's exact sample rate;
- the selected resource's exact frame count; and
- exactly `fmt ` then `data`, with no metadata chunks.

The 849 additional rows span the sample rates already present in the source
catalog; the tool does not resample or change duration. Human-readable errors
state the required channel count, rate, and frame count for the selected sound.

## What the writer changes

The project stores only the stable asset ID and the user's WAV. During Build,
the tool resolves that logical ID against the metadata-only ownership catalog,
encodes the PCM with the deterministic Xbox IMA ADPCM encoder, and replaces only
the selected resource's existing payload allocation. The following remain
byte-identical:

- the 32-byte resource wrapper header;
- the AUDO system metadata and descriptor;
- the opaque resource tail;
- all archive and XDVDFS extents;
- `default.xbe`; and
- every byte outside the selected payload.

The original XISO is opened read-only. The replacement is composed with visual,
text, roster, Crib, Stadium, scorebug, and other supported edits into one new
XISO. Replace, per-asset Revert, global Revert, Undo, and shareable project
save/load use the existing Studio session path. Shareable projects contain no
retail audio.

## Evidence boundary and next step

Offline fixed-allocation transport is implemented for every physical row;
runtime audibility and semantic cue ownership are not yet claimed. The best
next spot check is the unique frontend resource `menu-appear_01` (`outer 9 /
chunk 33`) in matched stock and replacement runs, followed by one alias-related
family to correlate provisional catalog names with actual runtime consumers.

## Streaming soundtrack, commentary, and stadium banks

The product now also inventories every known `AUSB` streaming descriptor:

- 17 descriptors;
- 16 exact external `.bin` owners (the two `cwdloop` descriptors intentionally
  share one physical bank);
- 53,571 indexed ranges; and
- explicit families for soundtrack/music, commentary/speech, stadium/PA/coach,
  broadcast/presentation, ambient/diagnostic, and unknown future banks.

These rows are searchable in the Audio tab. The complete external bank can be
exported as an exact raw `.bin`, and each of the 53,571 boundary pairs is an
individually searchable, **Editable** range with **Play/Stop**, **Export WAV**,
**Export Raw Range**, **Replace**, and **Revert**. The descriptor provides
22,050 Hz and one/two channels; every range is whole 36-byte-per-channel Xbox
IMA blocks, and each block is decoded as 64 frames. Replace requires a
canonical authored PCM16 WAV with that exact channel/rate/frame shape and writes
only the existing fixed allocation in a new copied XISO.

This does not recover human cue names, loops, gain/pan/priority, or runtime
routing. Whole-bank repacking and duration/routing edits remain disabled. Raw
and source-decoded exports contain retail-derived audio, stay in the user's
private cache/output, never enter shareable projects, and must not be
distributed. A shareable range edit contains only the logical owner ID plus the
user's source-origin-safe WAV.

Standalone and streaming selectors remain distinct. The streaming writer owns
53,570 physical fixed slots behind 53,571 logical rows, including one shared
two-owner alias and four pack-seam writes. The next runtime step is to hear one
clearly authored range in a matched xemu run, then map its cue/loop/mixer owner
without generalizing beyond that evidence.

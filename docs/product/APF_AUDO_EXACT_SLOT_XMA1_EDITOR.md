# APF 2K8 Standalone AUDO Exact-Slot XMA1 Editor

Date: 2026-07-19  
Alpha 28 product refresh: 2026-07-20  
Product state: implemented, offline-proved, and Xenia boot-compatible; audible
consumption of the tested cue remains inconclusive  
Scope: standalone `AUDO` resources only

Alpha 28 carries the exact-slot writer and selected-sound PCM16 bridge forward,
and adds v2 PCM16 folder/ZIP replacement packs. Mod Studio still ships no
encoder: the modder configures a
separately installed tool, directly or as a Windows `.exe` through Wine. The
bridge's synthetic tests prove template/process/validation plumbing only, not
real-encoder compatibility or in-game audibility. Archive identity belongs in
the release's adjacent `.sha256` sidecar, not this report.

## Result

APF 2K8 Mod Studio now has a bounded replacement route for every one of the
game's **2,261 standalone `AUDO` resources**. A modder may import a pre-encoded
RIFF XMA1 file when its stream shape and encoded packet allocation exactly
match the selected sound. Replace, individual Revert, Undo, project save/load,
staged-replacement preview, and Build all use the same typed route.

Alpha 28 can alternatively export an exact-length PCM16 silence template for
one selected sound and accept the edited WAV through a user-configured external
XMA1 encoder. Its output receives no trust: it crosses the identical RIFF,
shape, allocation, packet, complete-decode, duration, alias, and cross-family
source-packet gates before one project edit is staged. The same bridge now
accepts a v2 folder/ZIP pack with up to 256 supplied exact-shape PCM16 WAVs and
stages the complete valid set as one Undo action. Legacy v1 packs still take
finished pre-encoded XMA1. FLAC/MP3 and mixed-format packs remain unsupported.

This remains an **offline-writer result**, now with a completed partial runtime
spot check. A one-span replacement build booted in Xenia, logged no XMA
decoder fault, and survived five executions of the intended Schedule-enter
route. A matched stock control followed the same route. Timestamp-aligned
waveform and spectral tests did not distinguish the authored cue from their
random and shifted controls strongly enough to claim audible consumption.
The capability therefore stays Editable through its bounded offline writer,
not through an invented runtime-audio claim. Alpha.23 carries that writer
forward unchanged while adding the separately bounded AUSB exact-slot route.

Mod Studio is not an encoder and distributes no encoder binary. A modder may
use **Replace with XMA1…** for a finished compatible file or **Replace from PCM
WAV…** after configuring a trusted, legally obtained external encoder. The
second route accepts only an exact-shape PCM16 WAV and still requires the
external result to be a compatible one-stream RIFF XMA1 file.

## What the inventory proves

The selected USA retail source contains:

- 2,261 standalone `AUDO` records distributed across 29 IFF packages;
- 62,513,152 encoded SRAM bytes in 30,524 packets of `0x800` bytes;
- one 44-byte big-endian metadata record paired with each encoded payload;
- uncompressed, physically contiguous payload spans in `0A` for all 2,261
  records; and
- no overlap between those standalone encoded spans.

The product resolves a target by its semantic identity:

```text
apf:audio:audo:<outer-table-index>:<inner-file-index>
```

It reparses the user's current `0A`, requires the target inner resource to be a
standalone `AUDO`, and derives the physical SRAM span from that source. A
project does not store a physical offset and cannot nominate an arbitrary byte
range.

## Exact input contract

Choose **Replace with XMA1…** only on a **Standalone AUDO** row. The supplied
file must satisfy all of these requirements:

1. It is a complete little-endian RIFF/WAVE file with an exact RIFF length,
   one `fmt ` chunk, and one `data` chunk. Ancillary chunks may be present but
   are discarded when the import is canonicalized.
2. Its format tag is XMA1 `0x0165`, its `fmt ` body describes exactly one
   stream, and it declares 16-bit decoded output.
3. Its channel count is one or two and exactly matches the selected target.
4. Its sample rate exactly matches the selected target.
5. Its pseudo-byte rate is internally consistent with that channel/rate shape.
6. Its `data` length exactly equals the target's existing encoded allocation.
   The payload must be nonempty, no larger than 64 MiB, and an exact multiple
   of `0x800` bytes.
7. Every `0x800`-byte packet classifies as XMA1, uses APF's packet metadata
   value `2`, sequence nibble `0`, and packet skip `0`.
8. The replacement decodes completely through FFmpeg with error-exit behavior
   enabled. Its decoded channel count and sample rate must still match, and its
   decoded frame count must be within 127 samples of the target's declared
   sample count. This small tolerance accounts for the XMA packet tail; it is
   not permission for a different-duration sound.
9. The canonical raw replacement payload must not match a complete source
   payload, and no complete `0x800`-byte replacement packet may match any
   packet in either the standalone AUDO or addressed AUSB source inventory.
   Authorization is cross-domain and domain-wide, not limited to the selected
   slot.

Ordinary WMA, xWMA, and XMA2 are different formats and are rejected. A file
with the right extension but the wrong RIFF tag or packet layout is rejected.
Changing only the RIFF wrapper cannot evade validation because the editor
canonicalizes and hashes the raw packet payload.

The selected target's original loop/valid-bit sidecar semantics are used only
to reconstruct an in-memory validation wrapper and to preserve the existing
target contract. They are not copied into the shareable project. The imported
file's ancillary RIFF chunks and wrapper-level loop values are not used to
expand or relocate the target allocation.

## Modder workflow

1. Load the user's own extracted APF 2K8 game in Mod Studio and open **Audio**.
2. Set **Record kind** to **Standalone AUDO**, then search/filter and select a
   sound. The details panel shows the required encoded bytes, sample rate, and
   channel count.
3. Export and preview the original privately if identification is needed.
4. Either prepare a finished user-supplied one-stream RIFF XMA1 file, or choose
   **Export PCM authoring template…**, replace its silence without changing the
   PCM16 channels/rate/frame count, and configure a separately installed XMA1
   encoder. Advanced configuration is one literal argv entry per line and
   never a shell command.
5. Choose **Replace with XMA1…** for the finished file or **Replace from PCM
   WAV…** for the exact template. Validation completes before an edit is
   staged. Wrong-shape PCM, FLAC/WMA/MP3, wrong-size XMA, wrong-rate XMA, bad
   packets, incomplete decode, or exact source-packet reuse produces a
   modder-facing error and no project change.
6. Use **Load waveform** or **Play** to preview the staged replacement. The app
   decodes the project's raw replacement packets through a private temporary
   WAV and checks that cached preview before reuse.
7. Save the `.apf2k8mod` project, use **Build Modded Game**, and test the new
   output in Xenia. The source extraction is never edited.
8. Use **Revert sound**, Undo, or **Revert All** to remove the authored delta.

The completed Xenia spot check proved boot compatibility but not audible cue
consumption, so modders should still treat this advanced route as experimental
even when offline validation succeeds.

## Retail-free project contract

The shareable `.apf2k8mod` archive stores only the canonical raw packets from
the user's supplied replacement under a `.xma1-packets` member. It does not
store the supplied RIFF wrapper, the original sound, a rollback preimage, an
original packet, a source filename, a physical `0A` offset, or retail loop
metadata.

The associated target metadata is limited to:

- outer table index;
- inner file index;
- exact encoded size;
- sample rate;
- channel count;
- declared sample count;
- packet count; and
- writer-schema identifier.

Every save and load validates the target identity and canonical packet shape.
When an audio edit is present, the product builds a complete source inventory
covering whole payloads and every complete `0x800`-byte packet in both audio
domains: 2,261 standalone AUDO slots plus 45,513 canonical AUSB ranges.
Session admission, project load, modified preview, and Build reject an exact
source payload and also reject a replacement containing even one source
packet. This blocks same-family copying, AUDO/AUSB transplants, and a retail
packet hidden inside an otherwise changed payload.

The project remains source-bound through the normal APF project target
fingerprint. A target-shape change, wrong game source, changed payload,
malformed metadata, or protected source hash fails closed before the project is
admitted.

## Build behavior

Audio replacement is represented by the dedicated modification kind
`audo_exact_slot_xma1`. The build service does not expose a generic raw-offset
patch API. Instead it:

1. resolves all requested standalone targets from the selected source in one
   batch;
2. revalidates every stored packet payload against the current target and the
   complete cross-domain payload/packet authorization inventory;
3. records the selected span's SHA-256 from the pinned, currently reparsed
   source as a source guard in the private build receipt;
4. composes disjoint audio spans with the existing typed whole-entry writers;
5. rejects overlapping or contradictory spans;
6. copies to a separate build destination and writes only the compiled spans;
7. verifies every authored span byte-for-byte;
8. verifies that all bytes outside the compiled spans still match the source;
   and
9. reparses the output `0A` before a successful build is reported.

Multiple sound edits inside one outer package are composed without replacing
the whole package from competing snapshots. A failed validation or output
check cannot alter the source and cannot publish a partially verified build as
successful.

The safety gate is not merely theoretical. A bounded real-source Alpha.23
Build rejected an 8-bit-mutated near-retail soundtrack input at replacement
packet 0 even though the older whole-payload-only check admitted it. No source
fingerprint, packet hash, retail byte, preimage, or private path is stored in a
shareable project or public receipt.

## Current boundary

### PCM16 authoring and external XMA1 encoding

The installed FFmpeg toolchain decodes XMA1 but does not provide an XMA1
encoder. Alpha 28 therefore exports target-shaped PCM16 metadata templates and can
invoke a modder-configured external encoder without a shell. The native or
Wine-hosted executable, its literal argv template, and timeout are PC-local
settings and never enter a project or release. The bridge canonicalizes input
privately, bounds and cleans the process group, supports cancellation, and
hands the result to the existing exact-slot validator.

No real XMA1 encoder was available in the build environment. Fake-process tests
prove selected and batch plumbing only. One selected WAV, MP3, FLAC, OGG, M4A,
or other FFmpeg-decodable file is conformed through the current ordinary-audio
route; folder/ZIP packs accept only pre-encoded XMA1 or exact PCM16 WAV.
Mixed-format ordinary-audio packs and more than 256 supplied files per import
remain unsupported, and exact slot fit can still reject otherwise valid XMA1
output. See the
[external encoder guide](../mod_editor/apf2k8_external_xma1_encoder.md).

### AUSB commentary, soundtrack, and music replacement

Alpha.23 separately ships strict exact-slot Replace/Revert/project/preview/
Build for all 45,514 addressed AUSB substreams. They resolve to 45,513
canonical physical ranges across 19 external banks; the one shared `cwdloop`
range discloses both owners, and the one stereo Track 3 range crossing `0A` and
`0B` is split and source-guarded by the pack-aware builder. Descriptor bytes
and whole physical banks are not repacked. Physical-bank and AUSB-index rows
remain descriptive/private raw exports rather than one-sound editors. See the
[AUSB exact-slot contract](APF_AUSB_EXACT_SLOT_FEASIBILITY.md).

The private Alpha.23 Track 12 runtime candidate booted, selected the intended
track, and remained stable, but its completed objective capture was
**negative/inconclusive for modified-stream causality**. The final sustained
segment matched neither the mutated candidate nor decoded stock Track 12. That
proves boot/selection/stability only; it proves neither authored-audio
consumption nor stock fallback.

### Completed Xenia A/B: boot-compatible, acoustic result inconclusive

The bounded runtime experiment used standalone target
`apf:audio:audo:988:41` (`menu-calander-in_01`): 12,288 encoded bytes, mono,
22,050 Hz, and 29,601 declared samples. A sharply different compatible donor,
`apf:audio:audo:54:55` (`rm_vofx_038`), also occupied 12,288 bytes and decoded
to 29,696 samples, within the exact-slot 127-sample tail tolerance. The normal
product builder authored only that target span, verified every other byte
against the source, reparsed the output, and left the source untouched.

The candidate and its restored byte-identical stock control both booted in
Xenia on the isolated display and reached the Season hub. Each run executed
five logged **Schedule enter** events and five matching exits at four-second
intervals. The candidate produced no XMA decoder error, remained interactive,
returned to the hub normally, and closed cleanly. That is positive evidence
for build acceptance and runtime stability.

It is not positive evidence that this exact menu cue was heard:

- Candidate-to-replacement normalized waveform correlation was `0.041206` at
  `+68.9 ms`, below its random-window 95th percentile `0.045585`
  (`p=0.315`, `z=0.503`).
- Stock-to-original correlation was `0.025192` (`p=0.984`).
- Replacement preference was almost identical in candidate and stock:
  `+0.010527` versus `+0.010666`, an interaction of `-0.000138`.
- The log-spectral comparison moved in the predicted direction—candidate
  favored the replacement and stock favored the original—but its interaction
  `+0.111760` did not beat 160 five-event pseudo sets (`p=0.155` one-sided,
  `p=0.311` two-sided, `z=1.141`). Shifted and exit-event controls also drifted.

The written classification is therefore **offline-writer-proved, runtime
partial: boot-compatible; cue consumption inconclusive**. It neither proves
nor falsifies that `menu-calander-in_01` owns the observed transition sound.
A later proof should use a quieter route or disabled soundtrack, 10–20
triggers, and a more distinctive compatible cue. Alpha.22 does not wait on
that repeat.

## Release-wide roster boundary

Alpha.23 also includes a 32-team × 53-row roster **planner**, not a 53-active-
player game writer. Stock APF currently consumes the first 42 membership rows
per populated team. Rows 43–53 are eleven project-only reserve choices saved
without retail roster data, and Build does not apply them. True runtime slots
43–53 still require a version-pinned emulator-target XEX consumer/accessor
patch plus owned side-table storage; teams 25–32 also retain unproved offline
selector ownership.

## Plain-language summary

Think of every sound as a box with a fixed size and label. Mod Studio can give
you an exactly timed silent WAV to paint, then ask an encoder you supply to pack
it. The result still enters the AUDO box—or an addressed AUSB box—only when it
is packed exactly the right way and is exactly the same box size. It rejects
the whole replacement or any exact packet copied from either source-audio
family. The project carries the supplied replacement packets, and the builder
checks that no other box changed.
The edited AUDO game booted and stayed stable, but the recording was too noisy
to prove that the tested menu box was actually the sound heard. The Track 12
AUSB capture likewise proved stability but neither modified playback nor stock
fallback. Alpha.28 can hand one selected exact-shape PCM16 WAV or a v2 pack of
up to 256 supplied WAVs to a separately installed encoder. Real-tool
compatibility and authored-audio consumption remain unproved. One selected
FLAC/MP3/OGG/M4A file is supported through conformance; mixed-format
ordinary-audio packs remain unsupported.

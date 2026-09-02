# Getting audio into NFL 2K5 and APF 2K8

## The short version

**NFL 2K5 is solved.** Drop any ordinary audio file onto a sound in the editor
(mp3, flac, ogg, m4a, wav, at any sample rate) and it is converted and written.
No external encoder, no hand-shaping in an audio editor, nothing to install
beyond FFmpeg. The game's codec is Xbox IMA ADPCM, which is fully documented, so
this product encodes it directly.

**APF 2K8 is solved except for one step that cannot be solved here.** The Xbox
360 stores this game's audio as XMA1, and no open XMA encoder exists: not in
FFmpeg, not anywhere. FFmpeg *decodes* `xma1` and `xma2` and encodes neither.
So APF has two routes:

* **Already have XMA?** Drop the `.xma` in. It is written through unchanged,
  byte for byte. No re-encode, therefore no re-encode artifacts. This is the
  lossless path and it has always existed.
* **Have anything else?** The editor converts your file to the slot's exact PCM
  shape and hands it to an XMA1 encoder *you* configure. It then decodes that
  encoder output and compares it with the authored PCM before staging anything.
  The conversion and artifact gate are ours; the XMA1 encoder is not.

## "Round-tripping introduces weird artifacts because of the proprietary encoder"

This is a real complaint and it deserves a precise answer, because most of it is
usually not the codec's fault.

Four failures get reported as codec damage. None of them are:

| What is heard | Actual cause |
|---|---|
| Plays too slow/fast, pitched wrong | Sample rate not converted. A 44.1 kHz file in a 22.05 kHz slot plays at half speed, an octave down. |
| Harsh, ring-modulated noise | A stereo file written into a mono slot, so L and R interleave into one stream. |
| Quiet, or oddly loud | A channel conversion that changed level. FFmpeg's implicit `-ac` downmix does not even normalise consistently across sample formats: measured on 6.1.1, stereo→mono lands at `(L+R)/2` for `s16le` but `(L+R)/√2` for `f32le`. |
| A click at the end | The file was cut mid-waveform to make it fit, leaving a step discontinuity. |

The converter removes all four. It resamples with soxr at high precision rather
than the default linear resampler, states both channel mixes explicitly instead
of relying on `-ac`, fades briefly into any trim so the cut lands near zero, and
works in float until a single final quantisation so that resampler overshoot is
measured before it can clip. Then it *reports what it did*, so a surprising
result is explainable rather than mysterious.

After encoding, APF also runs an alignment-aware signal gate over the complete
cue. It rejects a collapsed/silent result, wrong rate or pitch, channel swap or
interleave, gross level change, new sustained clipping, excessive DC offset,
and a bad tail/click. The 127-frame alignment search allows ordinary decoder
delay; broad correlation thresholds allow normal lossy XMA reconstruction.
Passing this gate means those gross failures were not detected. It is not a
perceptual claim that the configured encoder sounds transparent.

**The PS3 detail matters.** A modder moving audio from the PS3 build is not
round-tripping XMA at all. PS3 audio is a different codec entirely, so that
path is necessarily decode, then PCM, then re-encode to XMA1. The re-encode is
unavoidable there, and its quality is entirely a property of whichever XMA1
encoder is used. Nothing in this product can change that. Within the 360,
however, XMA to XMA is lossless via the direct `.xma` drop.

## What was measured

The 2K5 chain was run against **every one of the 849 authorable slots**: one
ordinary 48 kHz stereo source file, converted to each slot's exact shape,
validated by the editor's own unmodified strict parser, encoded with the real
Xbox IMA encoder, decoded back and scored.

```
849/849 slots succeeded, 0 failures
signal-to-noise across all slots:  min 32.34 dB   median 32.53 dB   max 39.32 dB
```

For context, typical IMA ADPCM implementations land nearer 20–25 dB. The extra
headroom comes from the encoder searching all 89 candidate start indices per
block and keeping the lowest-error one, rather than carrying the previous
block's index forward. That search is worth about **3 dB** on both tonal and
transient material, measured, so it is kept.

Keeping it used to be expensive: ~11 ms per 64-frame block, about 110 s for a
30-second sound, which no GUI can sit through. ADPCM will not vectorise along
time, because each sample depends on the previous predictor. It vectorises
perfectly along two other axes. The 89 candidates are independent, and so is
every block in the stream, since each block re-seeds from its own first sample. Stepping
`blocks × 89` together makes the whole encode 63 array operations regardless of
length: **~24× faster, byte-identical output**. The tests assert byte equality
against the scalar encoder, not similarity.

The APF signal comparator has synthetic proof for aligned lossy reconstruction
and explicit failures for silence, wrong pitch/rate, swapped channels,
clipping, DC, and a corrupt tail. The actual decoder handoff and fail-closed
session wiring are tested. No legally obtained real XMA1 encoder was available
for a public encode/decode quality benchmark, so the editor does not claim a
measured XMA quality score.

## Moving one privately exported 2K5 line into APF

1. In NFL 2K5, select the proved cue/range and use **Export WAV**. Do not rename
   a raw bank or raw range to `.wav`.
2. In APF, select the exact destination AUDO/AUSB sound and drop that private
   WAV (or choose it in the replacement dialog).
3. The editor conforms the 2K5 PCM to the APF slot's channels, sample rate, and
   exact frame count, then applies headroom and a trim fade when needed.
4. The configured external XMA1 encoder runs privately. Its result must pass
   the APF packet/allocation decoder gate and the encode-to-decode signal gate.
5. Preview the staged decoded WAV before Build. Keep the 2K5 export and APF
   output private unless you have the right to distribute that dialogue.

## What is deliberately not done

* **No encoder is bundled.** For APF the XMA1 encoder stays user-supplied. This
  product never presents FFmpeg as an XMA1 encoder, because it is not one.
* **No unchecked external encode is staged.** The PCM route must decode back
  and pass the signal gate. A failed comparison leaves the edit map and Undo
  history unchanged.
* **A file that is already exact is never touched.** It is passed straight
  through: not re-encoded, not rewritten, not copied. Anyone who prepared a
  precise WAV keeps byte-for-byte control.
* **No validation was relaxed to make this work.** Conversion happens *in front
  of* the existing importers. Whatever it produces then faces every check that
  was there before: link count, RIFF structure, the exact shape match, the
  exact data size, and on APF the full exact-slot XMA1 packet and complete-decode
  contract. A bug in conversion fails closed exactly like a bad hand-made WAV.

## Using it

In either editor: select the sound, then drop a file or use the chooser. If the
file needs converting the status line says so, and hovering it shows exactly
what changed and why.

From the command line:

```sh
python3 tools/game_audio_convert.py input.mp3 output.wav \
    --channels 1 --sample-rate 11025 --frames 10624
```

```
source: mp3 stereo 44100 Hz, 3.03 s
slot:   mono 11025 Hz, 10624 frames (0.96 s)
  - Resampled 44100 Hz -> 11025 Hz (soxr). Without this the sound would play at
    the wrong speed and pitch.
  - Channels 2 -> 1.
  - Source was longer than the slot; trimmed 22451 frames (2.04 s). A short fade
    was applied at the cut so it does not click.
```

## Where the code is

| Piece | File |
|---|---|
| Xbox IMA ADPCM encoder/decoder | `tools/xbox_ima_encoder.py` |
| Any file to exact-shape PCM16 | `tools/game_audio_convert.py` |
| Editor-facing seam | `mod_editor/core/audio_conform.py` |
| 2K5 wiring | `mod_editor/gui/audio_panel_qt.py` |
| APF wiring | `mod_editor/apf_studio/session.py`, `mod_editor/apf_studio/gui.py` |
| Tests | `tests/test_xbox_ima_encoder.py`, `tests/test_game_audio_convert.py`, `tests/mod_editor/test_audio_conform.py` |

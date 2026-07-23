# NFL 2K5 AUSB Xbox IMA decode experiment

Date: 2026-07-18  
Result: **positive; bounded playback/WAV export shipped**

## Question

The AUSB descriptors already owned 53,571 exact ranges in 16 physical external
banks, but the product previously called their codec unresolved. This experiment
tested whether the ranges use the same 36-byte-per-channel, 64-frame Xbox IMA
ADPCM framing already decoded for standalone NFL 2K5 AUDO resources.

The original decoder experiment did not test replacement, cue naming, loop
behavior, mixer state, or runtime selection. The retail XISO was opened
read-only and all outputs were written to temporary/private paths. The later
RC11 product result below separately proves bounded fixed-range replacement and
offline Build/Verify; runtime selection and audibility remain untested.

## Bounded samples

| Role | Stable range | Encoded shape | Decoded shape |
| --- | --- | ---: | ---: |
| Music | `nfl2k5.audio.ausb.o0003.c0218.r00000` (`loadm`, range 0) | 78,912 bytes; 2 channels; 1,096 time blocks | 70,144 stereo frames at 22,050 Hz; 3.181134 s |
| Commentary | `nfl2k5.audio.ausb.o0003.c0213.r07227` (`players`, range 7,227) | 2,664 bytes; 1 channel; 74 blocks | 4,736 mono frames at 22,050 Hz; 0.214785 s |

The music sample was selected as the smallest music range. The commentary
sample was the smallest commentary range. Both decoded without a rejected
header, truncated block, or frame-count discrepancy.

## Exact container relationship

The AUSB body supplies:

- the external `.bin` owner by filename CRC;
- a monotonic start/end table;
- sample rate 22,050 Hz;
- a descriptor word whose complete corpus domain is 1 or 2 and is now proved
  to be channel count; and
- constant word `0x00012000` (still not assigned a stronger semantic name).

Each selected range is headerless encoded audio. Its payload is a sequence of
Xbox IMA time blocks. A time block contains one consecutive 36-byte channel
sub-block per descriptor channel. Each channel sub-block contains a signed
16-bit predictor, a 16-bit step index, and 32 bytes/64 nibbles. The game framing
emits 64 samples: the predictor and the first 63 expanded nibbles; the last
nibble advances decoder state but is not emitted.

No guessed per-range RIFF header is treated as retail truth. Mod Studio decodes
the owned raw span, then writes a new ordinary PCM16 WAV with the descriptor's
channel count/rate and the exactly derived frame count.

## Corpus proof

Metadata geometry passed for all **53,571** descriptor ranges: zero ranges had
a byte length outside `36 * channel_count`, and none was empty.

A streaming scan then read each of the 16 unique physical banks once:

- encoded bytes checked: **2,183,326,092**;
- physical 36-byte channel-block headers checked: **60,647,947**;
- legal step-index domain: 0 through 88;
- invalid step indices: **0**;
- observed maximum step index: **88**;
- all 89 legal step-index values observed; and
- nonzero channel blocks: **60,251,612**.

The descriptor count is 17 because two `cwdloop` descriptors intentionally
share one physical bank. Counting descriptor occurrences instead of unique
physical data adds that bank's 86,938 channel blocks a second time; the codec
scan correctly avoided doing so.

## Independent decoder correlation

FFmpeg's open `adpcm_ima_wav` decoder was used as an independent algorithmic
cross-check. Each raw 36-byte channel sub-block was presented as mono IMA WAV,
FFmpeg's 65th state sample was removed to match Xbox's 64-frame accounting, and
the sub-blocks were regrouped into descriptor-channel time blocks.

| Range | Pearson correlation | SNR | Maximum sample delta |
| --- | ---: | ---: | ---: |
| `loadm` range 0 | 0.999994733544 | 49.756 dB | 85 |
| `players` range 7,227 | 0.999999746971 | 62.702 dB | 21 |

The small nonzero deltas are the known integer-rounding difference between the
two IMA implementations; this was not misreported as byte identity. The product
uses the existing NFL Xbox IMA decoder whose 64-frame accounting and strict
step-index validation were already proved for all 850 standalone AUDO rows.

## Product result

Every indexed range now supports:

- private lazy decode to PCM16 WAV;
- Play/Stop through the existing no-terminal audio helper;
- Export WAV;
- the pre-existing exact Export Raw Range; and
- fixed-allocation Replace/Revert from an exact-shape authored PCM16 WAV; and
- searchable channel, sample-rate, frame-count, duration, family, bank, and
  physical-range metadata.

The product re-derives and verifies the WAV against the current owned range,
stores derived originals only in the private source cache, refuses altered or
incomplete cache pairs, refuses overwrite, and leaves no cache artifact after a
failed header decode. Tests cover valid mono/stereo framing, output round-trip,
tamper refusal, invalid-index cleanup, raw/WAV export separation, and both the
panel host and main Studio facade.

The largest real range was also exercised through the complete product service:
`cribmusic` range 58 decoded 8,954,064 encoded bytes into 7,959,168 stereo
frames (31,836,716 WAV bytes) in 1.018681 seconds on the development host. The
fast path uses Python 3.12's standard-library C decoder with the Xbox nibble and
64-frame adaptation; Python 3.13+ transparently retains the exact pure-Python
reference decoder. A source-free unit test forces that fallback and proves its
PCM remains byte-identical to the established NFL decoder. This optional
acceleration is not a package dependency.

## Still not claimed

- Range numbers are not human cue names.
- Complete banks are not presented as single playable files.
- Loop start/end, gain, pan, priority, and duplicate runtime routes remain
  unresolved.
- No whole-bank repacker, duration-changing writer, or loop/mixer editor exists.
- Fixed-range replacement is offline-proved for all 53,570 physical slots, but
  it preserves the source duration/routing and does not identify a cue by name.
- No in-game runtime selection or replacement behavior is claimed by this
  offline playback/export/fixed-range writer result.
- Raw and decoded retail-derived audio must remain private and must not be
  distributed; shareable `.2k5mod` projects contain neither.

# Madden NFL 09 (PlayStation 2) — the Audio page

Two lanes, on one page, over the 34,046 `SCHl` streams and 301 `BNKl` sound
banks of the user's own `SLUS-21770` disc.  The format they read is written up
in `docs/product/EA_SCHL_FORMAT.md`; this document is what the page *does*,
what each rung rests on, and what still needs a boot.

**Evidence tags on every claim.** **[M]** measured on the owner's retail disc,
read-only; **[S]** sourced; **[A]** assumed and said so.

| | |
|---|---|
| lanes | `madden09ps2.audio.streams` (`offline-writer-proved`), `madden09ps2.audio.banks` (`extract-only`) |
| module | `mod_editor/games/madden09_ps2/audio_lane.py` |
| format | `mod_editor/games/_formats/ea_schl.py` |
| validator | `tools/validate_madden09_ps2_audio.sh` / `.bat` |
| evidence | `docs/product/evidence/madden09_ps2/audio_codec_census.json` |

---

## 1. What the page shows

The catalogue walks six containers through a memory map and reads headers
only — no sound is decoded to list it.  Over the retail disc that is
**11,389 members, 34,046 streams, in 13.4 seconds** [M].  Adding the 301 banks
and their 967 sounds costs another **0.07 s** [M].

Each sound is listed with its container, member, stream index, duration, sample
rate, channel count and codec.  At most 4,000 are offered as targets, and the
two decodable containers are walked first so a capped list still carries every
sound a user can actually hear; the document's per-container totals stay
complete either way.

## 2. Play and Export WAV

289 of the 34,046 streams decode: every stream of `BGM.DAT` and of
`SOUNDDAT.DAT` [M].  All 967 bank sounds are Sony PlayStation ADPCM and the
508 that declare a sample rate decode [M].  A decoded sound is 16-bit PCM in a
plain RIFF/WAVE file.

**33,751 streams do not decode, and the page says why in their own row.**  They
are EA MicroTalk (header codec 4) — every line of speech and commentary on the
disc.  ffmpeg carries no decoder for it and refuses it by name, so a decoder
written here could not be checked against anything.  Their rate, channels and
length are read from the disc; their audio is not.

## 3. Import WAV, and what the writer actually does

The streams lane takes a WAV per sound.  It is mixed to that sound's channel
count and resampled to its rate **by linear interpolation** — plainly, on the
page — re-encoded as EA-XA ADPCM, and it **must fit the bytes the sound already
occupies**.  A longer one is refused naming the byte count it had to fit and
roughly how many seconds do fit; the ISO writer this lane stands on never grows
a file.  The check is arithmetic, not a trial encode: EA-XA's frame is a fixed
15 bytes for 28 samples, so the encoded size is known the moment the WAV is
chosen.

The new stream is written **into the member's own bytes**, and the remainder of
the member's stored length is zero-filled — which is the shape the disc already
has between two streams in one member [M].  Nothing moves: the `TERF` header,
the `DIR1` directory and every other member come through unchanged, and the
build checks that rather than assuming it.

### The preload caches, which are the part that is easy to miss

`GAME.QKL` and `FE.QKL` carry **byte copies** of some container members and of
some container header blocks, and the game loads the copy [M].  An edit to a
carried member that leaves the copy alone is an edit the game never sees.

The measured position for the audio containers [M]:

| container | header copies | member copies | what this lane does |
|---|---:|---:|---|
| `BGM.DAT` | 1 (`FE.QKL`) | 0 | nothing to rewrite; the header copy is checked |
| `SOUNDDAT.DAT` | 1 (`GAME.QKL`) | 41 (`GAME.QKL`) + 4 (`FE.QKL`) | the copy is rewritten with the member |
| `SPCHDATA.DAT` | 1 | 8 | speech; not written |
| `SPCHMAD1.DAT` / `SPCHMAD2.DAT` | 1 each | 1 each | speech; not written |
| `SPCHFEDT.DAT` | 1 (`FE.QKL`) | 2 | speech; not written |

So: **the lane rewrites the cache copy rather than refusing the member.**  Both
caches are parsed from the user's own image, every copy of a changed member is
rewritten with it, and the `.QKL` becomes another same-size replacement handed
to the bounded ISO writer, with its own declared range.  Cache copies are
deduplicated — two entries can share one offset [M] — so an offset another,
untouched member also points at is **refused**, because rewriting it would
corrupt that one.

A build also proves it did not have to touch the header copies: a same-size
replacement leaves the container's header block identical, and the build
compares it before and after rather than trusting that.

The reader was checked against the disc rather than against the table above:
every copy either cache declares of any of the seven audio containers was
compared with the bytes it copies — **5,805 copies, 0 differing** [M], which is
also an independent confirmation of the member offsets this lane computes.

## 4. The independent verifier

`verify` imports neither the writer nor the ISO writer's report beyond the
ranges it declares.  It:

1. refuses a destination whose length differs from the source;
2. streams both images a megabyte at a time and fails on the **first byte
   outside every declared range** that differs;
3. re-opens the destination as a disc in its own right, finds each replaced
   sound **by key**, decodes it with the decoder, and compares it with the
   user's own WAV — resampled and mixed the same way the build did — refusing
   below **30 dB** SNR;
4. re-derives the preload copies **from the destination's own caches**, not from
   the receipt, and fails on a stale member copy or a stale header copy.

## 5. Why the banks stay extract-only

The PS ADPCM encoder exists and round-trips a computed tone at 57 dB, so it is
not the codec that stops a bank writer.  What stops it is that **134 of the 967
sounds carry loop points** (tags `0x86`, `0x87`, `0x89`) whose meaning this
module has not established [M], the PlayStation SPU plays a bank sound from
parameters nobody here has mapped [A], and no rebuilt Madden 09 container has
been booted.  Replacing a looped sound without knowing what the loop tags
address is how a sound effect ends up stuttering in a game nobody here has run.
The row says that, and `check_edit` refuses every value with it.

## 6. Classifications, and why each is the honest rung

**`madden09ps2.audio.streams` — `offline-writer-proved`.**  A destination image
is built from the user's own disc, it keeps the source's exact length, every
changed byte falls inside a declared range, and an independent verifier
re-decodes the replacement and re-checks the caches.  It is **not**
`runtime-proved`, and nothing here pretends otherwise: no rebuilt Madden 09
image has been booted in an emulator or on hardware.  That single missing
witness is the whole distance between this rung and the next.

**`madden09ps2.audio.banks` — `extract-only`.**  It writes WAVs beside a
manifest and never touches the disc; §5 is the reason it will stay there until
the loop tags are decoded.

## 7. What CI proves, on no game data at all

`tools/validate_madden09_ps2_audio.sh` compiles both modules and runs the
game-module conformance harness, which builds a synthetic `SLUS-21770`-shaped
image and drives both lanes end to end on it: **228 of 229 checks pass, 1
skipped** (the skip is the pre-existing `code_patches` lane, whose
classification the shell does not draw an editor for).

The synthetic image carries, all computed here and none of it from a disc:

* a big-endian stereo stream with **no codec tag**, the shape all 47 music
  tracks have;
* a little-endian **version-2** mono stream, the shape 13 retail streams have,
  whose blocks carry their own predictor values;
* a member holding **two streams back to back**, the shape 6,488 of the
  disc's 11,389 stream members have [M];
* two `BNKl` banks, one mono and one stereo;
* a stream declaring the **speech codec**, so the refusal has something real to
  refuse;
* a `QL01` preload cache carrying a header copy and a member copy, so the
  cache-rewriting half of the writer is proved rather than described.

`tests/mod_editor/test_ea_schl.py` (37 tests) holds the format: the tag list
and its `0xFF` escape, both platform tags, a **hand-computed** EA-XA frame and
a **hand-computed** PS ADPCM frame worked out in the test's own comments, the
big-endian rule for verbatim frames, the version-2 difference in both
directions, the bank's own-slot offsets, and encoder round trips above 30 dB
for every channel count, byte order and version the disc uses.
`tests/mod_editor/test_madden09_ps2_audio.py` (42 tests) holds the lanes.

## 8. Measured on the real disc

| | |
|---|---|
| catalogue, six containers, 11,389 members, 34,046 streams | **13.4 s** [M] |
| ffmpeg agreement, streams | **289 of 289 byte-identical**, 670,692,008 PCM samples [M] |
| ffmpeg agreement, bank sounds | **508 of 508 byte-identical**, 33,451,124 PCM samples; the 459 with no declared rate are not compared [M] |
| bank plausibility, 508 sounds | none silent; peak 11,923-32,768 (median 31,175), RMS 2,207-11,170 (median 5,249); 88 sounds touch full scale and the longest saturated run anywhere is 21 samples [M] |
| encoder round trip, computed tone | EA-XA 54.7-58.3 dB, PS ADPCM 57.7 dB [M] |
| encoder round trip, 10 s of a real stream decoded and re-encoded | 106.3 dB (BGM, stereo), 97.2 dB (SOUNDDAT version 3), 57.8 dB (SOUNDDAT version 2), and **bit-exact** on a bank sound [M] |
| how close the re-encoded bytes come to EA's own | 7.7%, 1.6%, 94.9% and 99.6% of bytes identical on those four [M] |
| real-disc build (one BGM stream ← a 10 s computed tone) | 122.5 s, 1,657,339,904 bytes in and out [M] |
| real-disc verify | **PASS**, 47.4 dB, 2 declared ranges, 1 preload copy checked [M] |

The destination image was deleted immediately after the verdict, and the three
real streams and one bank sound exported to measure them were deleted after
their properties were recorded.  Nothing from the disc is in this repository.

## 9. What still needs a boot, and what still needs a decoder

* **A boot.**  Load a rebuilt image in PCSX2 and hear the replaced track.  That
  is the only thing between the streams lane and `runtime-proved`.
* **MicroTalk.**  33,751 streams, and no oracle anywhere in reach to check an
  implementation against.
* **The bank loop tags**, which gate a bank writer.
* **Names.**  `BGM.DAT` names none of its 47 members, so which track is which is
  not established here [A]; nor is which sound a bank belongs to.
* **Six EA-XA streams that declare no sample rate**, and **459 bank sounds**
  that declare none either: they are listed and refused rather than exported at
  an invented rate [M].

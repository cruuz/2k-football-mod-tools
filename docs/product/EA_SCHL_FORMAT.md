# EA `SCHl` audio streams and `BNKl` sound banks, as measured on Madden NFL 09 (PS2)

**Evidence tags on every claim.** **[M]** measured on the owner's retail
Madden NFL 09 (USA) disc (`SLUS-21770`, boot ELF CRC `38014255`, image SHA-256
`b34e8a…6427`), opened read-only; **[S]** sourced from a reference outside this
repository; **[A]** assumed, and said so rather than dressed up.

The reader is `mod_editor/games/_formats/ea_schl.py` (standard library only).
The numbers below come from `mod_editor/games/madden09_ps2/audio_lane.py`
walking the disc; the census they were taken from is
`docs/product/evidence/madden09_ps2/audio_codec_census.json`.

---

## 1. What is on the disc

Six `/DATA` containers hold audio, and every one of them is a plain `TERF`
container with no `COMP` chunk, so its members are stored uncompressed and a
same-size member replacement changes only its own slot [M].

| container | bytes | members holding streams | streams | decodable | speech codec |
|---|---:|---:|---:|---:|---:|
| `BGM.DAT` | 213,950,464 | 47 | 47 | 47 | 0 |
| `SOUNDDAT.DAT` | 181,151,744 | 119 | 248 | 242 | 0 |
| `SPCHFEDT.DAT` | 3,876,816 | 167 | 167 | 0 | 167 |
| `SPCHDATA.DAT` | 136,649,024 | 7,725 | 16,626 | 0 | 16,626 |
| `SPCHMAD1.DAT` | 415,615,296 | 1,212 | 12,475 | 0 | 12,475 |
| `SPCHMAD2.DAT` | 158,743,424 | 2,119 | 4,483 | 0 | 4,483 |
| **total** | | **11,389** | **34,046** | **289** | **33,751** |

[M] on all of it.  "Decodable" means EA-XA ADPCM *and* a declared sample rate;
six more streams are EA-XA but declare no rate, which makes the EA-XA
population **295** and the playable population 289.

`SOUNDDAT.DAT` additionally holds **301 `BNKl` sound banks**, and no other
container on the disc holds one [M].

A container **member** is not a sound: 11,389 members hold 34,046 streams
between them, back to back with zero padding in the gaps [M].  6,488 of those
members hold more than one, and the most any one holds is measured in the
census [M]; `BGM.DAT` is one stream per member, `SPCHMAD1.DAT` averages ten.

---

## 2. The chunk stream

```
SCHl  <u32 size>  platform tag + tag list      the header
SCCl  <u32 size>  <u32 block count>            how many SCDl follow
SCDl  <u32 size>  <block>                      audio, N of them
SCEl  <u32 size>                               end
```

Every chunk's size is a **little-endian** `u32` and counts the 8-byte chunk
header itself [M] — on both platform tags, so the chunk chain is walkable
before the byte order of the *contents* is known.  34,046 of 34,046 streams
walk to an `SCEl`, and in 34,046 of 34,046 the `SCCl` count equals the number
of `SCDl` chunks actually there [M].

---

## 3. The platform-tagged header

`SCHl`'s payload opens with a platform tag, and the tag decides two things [M]:

| tag | bytes at chunk+8 | tag list starts at | block integers |
|---|---|---|---|
| `GSTR` | `47 53 54 52` then 4 more bytes | chunk + 16 | **big-endian** |
| `PT` | `50 54` then `u16` platform, little-endian | chunk + 12 | **little-endian** |

27,886 streams carry `GSTR`; 6,160 carry `PT`, every one of them with platform
code 5 [M].  Code 5 is EA's PlayStation 2 [A]: consistent with the disc, not
proved by it.

**The endianness rule was tested, not assumed.**  For every stream the `SCCl`
block count was read both ways and compared with the blocks actually walked;
the order that agreed was the one the platform tag implies, in **34,046 of
34,046 streams, zero counter-examples** [M].

### The tag list

A flat sequence.  Four tags take no value at all (`0xFC`, `0xFD`, `0xFE`,
`0xFF`); every other tag is followed by a **length byte** and that many
**big-endian** value bytes, and **a length byte of `0xFF` escapes to a 4-byte
big-endian length** [M].  The escape is not a nicety: 527 headers carry a tag
`0x14` blob of 960 to 1,386 bytes, and a parser without the escape mis-reads
every one of them and then mis-reads the rest of the header behind it.

Tags measured across all 34,046 stream headers [M]:

| tag | streams | distinct values | what it is |
|---|---:|---:|---|
| `0x06` | 34,046 | 1 (101) | constant on every stream; role **not established** [A] |
| `0x0B` | 134 | 1 (2) | constant; role **not established** [A] |
| `0x13` | 3,863 | 1 (127) | constant; role **not established** [A] |
| `0x14` | 527 | — | variable-length blob opening with a FourCC (`EMXP` 525, `CNYS` 2), 960 to 1,386 bytes; contents **not established** [A] |
| `0x80` | 33,896 | 2 — 3 on 33,883, 2 on 13 | version [M] — see §5 |
| `0x82` | 282 | 1 (2) | channel count; **absent means 1** [M] |
| `0x84` | 33,487 | 6 | sample rate in Hz [M] |
| `0x85` | 34,046 | 24,334 | sample count, **per channel** [M] |
| `0x8C` | 6,160 | 1 (4) | constant, on exactly the `PT` streams; role **not established** [A] |
| `0xA0` | 33,896 | 2 (4, 10) | codec [M] — see §4 |
| `0xFC` | 1,054 | — | no value; padding between tags [M] |
| `0xFD` | 34,046 | — | no value; opens the info block [M] |
| `0xFF` | 34,046 | — | no value; ends the header [M] |

`0x85` is per channel: a stereo stream's decoded PCM holds `0x85 × channels`
samples, and the per-block sample counts sum to exactly `0x85` in **34,046 of
34,046 streams** [M].  That sum is the strongest single check on the block
parse in this document.

Tags `0x86`, `0x87`, `0x88`, `0x89` and `0x8A` appear only in banks (§7).

---

## 4. The codecs, and which of them is decoded here

| tag `0xA0` | version `0x80` | streams | what it is | decoded? |
|---|---|---:|---|---|
| 4 | 3 | 33,751 | EA MicroTalk, ~10:1 speech [S] | **no** |
| 10 | 3 | 132 | EA-XA ADPCM | yes |
| 10 | 2 | 13 | EA-XA ADPCM, per-block predictor | yes |
| absent | absent | 150 | EA-XA ADPCM | yes |

[M] on the counts and on the assignment of every stream to a row.

**Codec 4 is not decoded here, and the reason is not shyness.**  It carries
**1.706 bits per sample** over all 33,751 of them and 3,317,735,806 samples
[M], which is a roughly 9.4:1 codec, and it is not framed the way EA-XA is.
ffmpeg's `ea` demuxer refuses it **by name** — `stream type; revision2=4 is not
implemented` [M] — so there is no reference decoder anywhere in this project's
reach to check an implementation against.  EA's speech codec of this era is
MicroTalk, and community tooling maps EA codec `0x04` to MicroTalk 10:1 [S].
A codec written blind against no oracle is a claim, not a decoder, so
the lane refuses it with that sentence and the catalogue still carries the
sound's rate, channels and length.

**The 150 streams with no codec tag at all** decode as EA-XA: their frames are
the 15-byte and 61-byte shapes of §5 and they match ffmpeg's `adpcm_ea_r3`
byte for byte (§8) [M].  What the game reads to reach the same conclusion is
**not established** [A]; it may be the platform tag, it may be a default.

---

## 5. The `SCDl` block and the EA-XA frame

A block's payload, in the stream's own byte order [M]:

```
u32   samples in this block (per channel)
u32   data offset, one per channel, counted from (channels + 1) * 4
...   each channel's frames, at those offsets
```

A channel's run is 28-sample frames, and there are two shapes [M]:

* **ADPCM, 15 bytes.**  A control byte — coefficient index in the high nibble,
  `shift = 20 - low nibble` — then 14 bytes of two 4-bit residuals each, **high
  nibble first**.  With `(c1, c2)` from the four-entry table and the two
  previous outputs `s1`, `s2`:

  ```
  next = clip16(((residual << shift) + c1 * s1 + c2 * s2) >> 8)
  ```

  | index | c1 | c2 | frames on this disc |
  |---:|---:|---:|---:|
  | 0 | 0 | 0 | 884,352 |
  | 1 | 240 | 0 | 7,544,099 |
  | 2 | 460 | -208 | 11,064,527 |
  | 3 | 392 | -220 | 4,286,187 |

  The four coefficient pairs are the format's own constants [S]; that **only
  these four indices occur** is measured across every frame of every decodable
  stream [M], and a frame naming a fifth is refused rather than guessed at.

* **Verbatim, 61 bytes.**  Control byte `0xEE`, then two `int16` predictor
  values and 28 `int16` samples.  **These are big-endian whatever the stream's
  byte order is** [M]: the little-endian streams read them big-endian too, and
  reading them the stream's way byte-swaps every sample.  1,695 such frames on
  this disc [M].

The predictor state carries across frames and across blocks, and each channel's
run is padded to an even byte count [M].

### The one thing version 2 changes

Version 2 (tag `0x80` = 2, 13 streams, all in `SOUNDDAT.DAT`) opens **each
channel's run in each block** with two **little-endian** `int16` predictor
values before the first control byte, and does not carry the predictor across
blocks [M].  ffmpeg calls these streams `adpcm_ea_r1`.

This is not a detail that can be skipped: decoding a version-2 stream the
version-3 way walks four bytes off and starts reading coefficient indices the
format does not have — which is exactly how the difference was found here, and
what the refusal in §5 catches.

---

## 6. Sony PlayStation ADPCM

Bank audio is PS ADPCM (VAG): 16 bytes per 28 samples, **962 of 962 sounds
whose length can be derived carry exactly 0.5714 bytes per sample** [M], and
the second byte of every 16-byte frame is the VAG flag byte (0 on 6,260 frames
of the sample measured, 1 on 2) [M].

```
u8    shift in the low nibble, filter in the high nibble
u8    flag
14 x  two 4-bit residuals each, LOW nibble first
```

```
accumulator = trunc((s1 * f0 + s2 * f1) / 64)      # toward zero, not >> 6
emitted     = clip16(((residual << 12) >> shift) + accumulator)
state       = the UNCLIPPED value
```

Both of the last two lines were **derived from ffmpeg's own output rather than
assumed**, and both matter [M]:

* an arithmetic `>> 6` instead of the truncating divide is wrong on **half the
  samples** — 2,001 exact and 1,999 off by one over a 4,000-sample regression,
  against 4,000 of 4,000 exact with truncation;
* keeping the *clipped* value as state is right until a sound saturates, and
  then wrong for as long as the saturation lasts — a real retail sound
  diverged for thousands of samples on that one line.

The filters `(0,0) (60,0) (115,-52) (98,-55) (122,-60)` are the format's own
constants [S], and were re-derived here by solving for them against ffmpeg's
output over 123,088 samples with zero residual error [M].

Stereo frames alternate between channels, one 16-byte frame at a time [M].
**Which channel is the left one is not established** [A]; each channel's own
samples are proved (§8).

---

## 7. The `BNKl` bank

```
0x00  'BNKl'
0x04  u16 version            5 on all 301 banks [M]
0x06  u16 sound count
0x08  u32 header size        = offset of the data region
0x0C  u32 data size          header size + data size == the member's stored size,
0x10  u32 zero                 in 301 of 301 [M]
0x14  u32 x count            one per sound
```

**Each offset is counted from its own slot**, not from the start of the table
[M].  The natural reading finds a header for the first sound and garbage for
every one after it; that is the single rule this format most rewards measuring.
**A slot holding zero is an empty one** — 44 of the 1,011 slots across the 301
banks [M] — and reading zero as an offset lands back inside the table.

Each sound's header is a `PT` platform header (§3) whose tag `0x88` gives the
offset of its audio inside the member; a sound's length is the next sound's
`0x88`, or the end of the member [M].

Measured over the 301 banks [M]:

| | count |
|---|---:|
| banks | 301 |
| sound slots | 1,011 |
| sounds | 967 |
| empty slots | 44 |
| sounds declaring a sample rate (`0x84`) | 508 |
| sounds carrying loop points (`0x86`) | 134 |

The 459 sounds with **no** `0x84` are listed and refused rather than exported
at an invented rate.  Where their rate comes from is **not established** [A],
and it is not simple inheritance from the first sound of the bank: 41 banks
hold exactly one sound and that sound has no rate at all [M].

---

## 8. What the decoders were checked against

ffmpeg 7.0.2 carries the `ea` demuxer with `adpcm_ea_r1/r2/r3` and the `vag`
demuxer with `adpcm_psx`.  Every decodable member of the retail disc was
decoded twice — once by this reader, once by ffmpeg — and compared byte for
byte.  No ffmpeg code was copied; the format above is re-expressed from the
bytes and the headers, and ffmpeg is used only as an oracle.

Two harness details, stated because they change what "compared against ffmpeg"
means:

* ffmpeg's `ea` demuxer **refuses a header with no codec tag**, and it has no
  `0xFF` length escape, so it also refuses the two headers carrying a `0x14`
  blob.  For those streams the header is **re-expressed** — same platform tag,
  same rate, channels, sample count, version and codec — and the `SCCl`,
  `SCDl` and `SCEl` bytes are passed through untouched.  Not one audio byte is
  changed by that.
* ffmpeg has no bank reader, so a bank sound is handed to the `vag` demuxer
  behind a synthesised 48-byte `VAGp` header, and a stereo sound is
  de-interleaved into its two 16-byte-frame runs first so each channel is
  checked on its own.

Results are in §9 of `docs/product/MADDEN09_PS2_AUDIO.md` and in
`docs/product/evidence/madden09_ps2/audio_codec_census.json`.

---

## 9. What this document does not establish

* **MicroTalk.**  33,751 streams — every line of speech and commentary on the
  disc — are catalogued and not decoded [M].
* **What the game does with tags `0x06`, `0x0B`, `0x13`, `0x14` and `0x8C`.**
  Each is constant or opaque here and is recorded, not guessed [A].
* **Which channel of a stereo bank sound is the left one** [A].
* **Where a rateless bank sound's rate comes from** [A].
* **Whether Madden NFL 09 loads a rebuilt container.**  Nothing in this project
  has been booted.  The writer that uses this format is classified
  `offline-writer-proved` for exactly that reason.

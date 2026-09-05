# PS2 Phase 2 — audio: what is on the disc and what a writer would cost

**Target:** ESPN NFL 2K5, PS2, stock `SLUS-20919`.
**Status:** research only. Nothing here is implemented; no writer, no registry row.
**Purpose:** let a later agent implement an `offline-writer-proved` audio row
without re-deriving any of it.

[`PS2_PORT_HANDOFF.md`](PS2_PORT_HANDOFF.md)'s Phase-2 table budgets audio at
**8–12 d** and marks the estimate *unfounded*, on the grounds that "SPU-ADPCM
codec — nothing exists in-repo". That premise was right and the conclusion it
led to was wrong in an interesting way: **the codec is the cheapest part of
this surface.** See §10.

Everything below was measured against the user's own ISO, opened read-only.
Retail-free: this document contains chunk headers, sizes, counts and field
values. **It contains no payload bytes and no decoded audio.** Nothing was
written to disk during the decode checks.

---

## 1. Census — what audio the disc actually holds

| class | count | bytes | where |
|---|---:|---:|---|
| `AUDO` chunks (one-shot samples, payload inline) | **844** | 8,866,224 payload (8.5 MiB) | inside 691 outer VC entries |
| `AUSB` chunks (stream-bank directories, no payload) | **17** | 217,104 total | 4 outer entries (0/3, 0/16, 0/19, 0/374) |
| Raw SPU-ADPCM stream banks (the `.bin` files `AUSB` indexes) | **17** entries → **16** unique banks + 1 orphan | 2,219,021,392 (2.07 GiB) | 17 whole outer entries |
| MPEG-2 Program Stream movies (`.PSS`) | **28** | 383,680,624 | 28 whole outer entries |

The 844 + 17 figures are the ones `PS2_PORT_HANDOFF.md` quotes. The "45
unstructured entries" it also mentions resolve cleanly into the last two rows:
**28 movies + 17 stream banks = 45** (§6).

Total playable one-shot audio is only **896.9 seconds** across the 844 `AUDO`
chunks. The streaming banks are two orders of magnitude larger.

---

## 2. The container is the same one the Xbox lane already knows

Every resource on the PS2 disc sits behind the generic 0x20-byte VC chunk
wrapper that `tools/nfl2k5_ps2_disc_inventory.py` already walks, and it is the
**same wrapper the Xbox tooling parses** (`tools/nfl_txtr.py`'s
`Struct("<4s7I")`). Little-endian on both platforms.

### 2.1 Generic chunk wrapper — 0x20 bytes

| off | width | field | AUDO value | AUSB value |
|---|---|---|---|---|
| 0x00 | 4s | FourCC | `"AUDO"` | `"AUSB"` |
| 0x04 | u32 | `stored_size` | `system_bytes + video_bytes` | whole body |
| 0x08 | u32 | `system_bytes` | 128 / 160 / 192 / 224 | **0** |
| 0x0C | u32 | `video_bytes` | SPU-ADPCM payload length | **0** |
| 0x10 | u32 | compression magic | 0 (never `0xFEEDBEEF`) | 0 |
| 0x14–0x1F | | reserved | 0 | 0 |

Body starts at `chunk + 0x20`. Payload starts at
`chunk + 0x20 + system_bytes`. Next chunk starts at `chunk + 0x20 + stored_size`.

Verified on all 844 AUDO: `stored_size == system_bytes + video_bytes` (so the
**PS2 tail is always 0 bytes** — on Xbox the 36-byte IMA block does not divide
the allocation and a tail survives, e.g. 12 bytes on Menu Back, whereas the
16-byte SPU block divides every PS2 allocation exactly), `wrapper+0x10 == 0`,
and the wrapper's 0x14..0x1F plus the body's first 12 bytes are all zero.

Same slot, both discs, as a worked example — `menu-back_01`:

| | Xbox (`vc_53450030`, outer 3 / chunk 101) | PS2 (`VC_20919`, outer 3 / chunk 99) |
|---|---|---|
| `stored_size` | 3,344 | **3,344** |
| `system_bytes` | 128 | **128** |
| `video_bytes` | 3,204 (89 × 36 IMA) | 3,216 (201 × 16 SPU) |
| tail | 12 | **0** |
| descriptor | `(1, 1, 0x11, 0x35, 3204, 0, 3204, 16000)` | `(1, 1, 0x11, 0x35, 3216, 0, 3216, 16000)` |

Header hex, `menu-back_01` (`espn-ticker_01` differs only in the sizes):

```
AUDO wrapper
00000000  41 55 44 4f 10 0d 00 00 80 00 00 00 90 0c 00 00  |AUDO............|
00000010  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  |................|
          ^magic  ^stored=3344 ^system=128  ^video=3216
```

### 2.2 AUDO body (`system_bytes` long)

```
body+0x00  u32[3]    0
body+0x0C  char[4]   "AUDO"           descriptor tag
body+0x10  u32       17               descriptor type   (844/844)
body+0x14  u32       45 or 77         descriptor pointer, biased: N = 0x13 + value
body+0x18  u32       0
body+0x1C  u32       0
body+0x20  wchar[]   name, UTF-16LE, NUL-terminated, remainder filled with
                     the literal UTF-16 text "PADDING*PADDING*..."
                     field is 32 bytes (732 chunks) or 64 bytes (112 chunks)
body+N     ...       the 8-word sound descriptor, N = 0x20 + name-field length
```

`body+0x14` is the **same field-local relative pointer the Xbox probe uses**
(`tools/nfl_scene_probe.py`: `descriptor_offset = 0x13 + s32(data, 0x14)`).
`0x13 + 45 = 0x40` and `0x13 + 77 = 0x60` — exactly the two observed values of
`N`. The rule ports unchanged.

### 2.3 The 8-word sound descriptor at `body+N` — identical to Xbox

| word | off | PS2 meaning | observed |
|---|---|---|---|
| 0 | N+0x00 | channel count | 1 (806) / 2 (38) |
| 1 | N+0x04 | channel count (duplicate) | equals word 0 on 844/844 |
| 2 | N+0x08 | descriptor/codec word | **17 (`0x11`) on 844/844** |
| 3 | N+0x0C | flags | **53 (`0x35`) mono, 117 (`0x75`) stereo** — bit `0x40` = stereo |
| 4 | N+0x10 | `data_size` | `== video_bytes` on 844/844 |
| 5 | N+0x14 | `data_offset` | **0 on 844/844** |
| 6 | N+0x18 | `per_channel_data_size` | `× channels == data_size` on 844/844 |
| 7 | N+0x1C | **sample rate, Hz** | see §3 |

The Xbox descriptor is word-for-word the same, including `codec_word 0x11` and
`codec_flags 0x35` — **`0x11` is a descriptor type tag, not a codec id**, since
the two platforms carry different codecs behind it. Xbox tooling never named
word 0 or word 3; PS2 resolves both: word 0 is the channel count, and word 3's
bit `0x40` is the stereo flag.

`system_bytes = 0x20 + name_field + 0x40 × channels`, which reproduces all four
observed header sizes exactly:

| name field | mono | stereo |
|---|---|---|
| 32 bytes | **128** (708 chunks) | **192** (24 chunks) |
| 64 bytes | **160** (98 chunks) | **224** (14 chunks) |

For stereo the second 0x40-byte record repeats `per_channel_data_size` and the
sample rate at its +0x00/+0x04 and again at +0x1C; a writer never needs to
touch it (§9).

**No loop points, no gain, no pan** — same absence the Xbox probe recorded.
Looping is expressed inside the codec stream, not in the descriptor (§4).

---

## 3. AUDO sample rates and channel layout

| rate (Hz) | chunks |
|---|---:|
| 11025 | 735 |
| 22050 | 83 |
| 16000 | 15 |
| 14000 | 5 |
| 20000 | 3 |
| 12000 / 15000 / 18000 | 1 each |

Rate is **per slot**, exactly as on Xbox. Durations: min 0.184 s, median
0.843 s, max 16.805 s.

**Stereo `AUDO` is two contiguous per-channel halves, L then R — not
interleaved.** Two independent proofs:

1. The SPU `LOOP_END` flag appears at block `per_channel/16 − 1` **and** at the
   final block, on **38 of 38** stereo chunks and nowhere else. Each half is a
   separately terminated ADPCM chain.
2. Decoded L/R correlation is +0.72 (`draft_whoosh_in1`) and +0.90
   (`table-hum-loop_01`) under the contiguous-halves reading, versus +0.03 and
   +0.21 under a 16-byte interleave reading.

This differs from Xbox, where stereo `AUDO` is channel-major *interleaved*
(36-byte sub-blocks, channel 1 at +0x24). It is the natural PS2 shape: the SPU
plays each channel as its own voice from its own contiguous SPU-RAM run.

---

## 4. Codec — confirmed SPU-ADPCM, five independent ways

The reference is `pcsx2-VR/pcsx2/SPU2/Mixer.cpp`: `XA_decode_block` (:42),
`tbl_XA_Factor` (:33) = `{0,0} {60,0} {115,-52} {98,-55} {122,-60}` in 1/64
units, and `XAFLAG_LOOP_END = 1 << 0`, `XAFLAG_LOOP = 1 << 1`,
`XAFLAG_LOOP_START = 1 << 2` (:17-19).

| evidence | result |
|---|---|
| **Block alignment.** Every `video_bytes` is a multiple of 16 | 844 / 844 |
| **Header validity.** Every block's byte 0: `shift = b & 0xF ≤ 12`, `filter = b >> 4 ≤ 4` | **0 invalid blocks in 554,139** |
| **Flag byte** takes only SPU-legal values | `0x02` (553,257) and `0x03` (882); no other value anywhere |
| **Terminator.** Last block of every chunk carries `LOOP_END\|LOOP` (`0x03`) | **844 / 844** |
| **Round-trip.** Decode with the pcsx2 algorithm, then re-encode with an independent minimum-squared-error search over 5 filters × 13 shifts | `menu-back_01`: **3216 / 3216 bytes byte-identical to retail**. `wipe_01`: 22,513 / 22,528 (99.93%); the one differing block header is a tie between two equally-good `(filter, shift)` pairs and the decoded output is still bit-identical. |

Decoded sanity (in memory; nothing written): RMS −12 to −28 dBFS, peaks
22,152–31,896 of 32,767, **zero clipped samples**, DC ≈ 0, and duration
`payload/16 × 28 / rate` matching the descriptor's rate in every case.

A byte-exact re-encode of a retail sound is the strongest offline confirmation
available: it proves the decoder, the coefficient table, the shift convention,
the nibble order (low nibble first) and the block header layout simultaneously.

**Interior flag `0x02` is `XAFLAG_LOOP` with `LOOP_END` clear**, which pcsx2's
`DecodeSamples` treats as a no-op; 2K5 sets it on every block as a marker.
`LOOP_START` (`0x04`) never appears on the disc, so the voice's `LoopStartA`
stays wherever the engine keyed it on, and the terminal `0x03` sets `ENDX` and
returns there. A replacement should keep that convention.

---

## 5. AUSB — the stream-bank directory

`AUSB` chunks declare `system_bytes = 0` and `video_bytes = 0`; the whole
`stored_size` body is the directory.

```
body+0x00  u32[3]    0
body+0x0C  char[4]   "AUSB"
body+0x10  u32       17            (17/17)
body+0x14  u32       45            (17/17)
body+0x18  u32       0
body+0x1C  u32       0
body+0x20  wchar[16] bank name, UTF-16LE, "PADDING*" filled      (32 bytes)
body+0x40  wchar[32] external stream file name, e.g. "lines.bin" (64 bytes)
body+0x80  u32       range count
body+0x84  u32       id  (nonzero only for lines/players/teams)
body+0x88  u32       channels (1 or 2)
body+0x8C  u32       sample rate — 22050 on all 17
body+0x90  u32       0x0000C000 (49152) — buffer/unit constant, 17/17
body+0x94  u32       0
body+0x98  u32[count+1]  byte boundaries into the external stream
           pad          zero fill to the next 16-byte boundary (4–16 bytes)
```

Header hex, `lines` — offsets are from the **chunk** start, so `body+X` is at
`X + 0x20` here (non-contiguous rows elided):

```
00000000  41 55 53 42 a0 d9 01 00 00 00 00 00 00 00 00 00  |AUSB............|
00000020  00 00 00 00 00 00 00 00 00 00 00 00 41 55 53 42  |............AUSB|
00000030  11 00 00 00 2d 00 00 00 00 00 00 00 00 00 00 00  |....-...........|
00000040  6c 00 69 00 6e 00 65 00 73 00 00 00 50 00 41 00  |l.i.n.e.s...P.A.|
00000060  6c 00 69 00 6e 00 65 00 73 00 2e 00 62 00 69 00  |l.i.n.e.s...b.i.|
000000a0  3d 76 00 00 02 88 c8 26 01 00 00 00 22 56 00 00  |=v.....&...."V..|
000000b0  00 c0 00 00 00 00 00 00 00 00 00 00 e0 82 00 00  |................|
          ^unit 0xC000            ^bnd[0]=0  ^bnd[1]=0x82e0
```

This is the **Xbox AUSB layout, field for field**. `mod_editor/core/
nfl2k5_audio_catalog.py` reads five u32 at 0x80 and the boundary table at 0x98
with `count+1` entries and `boundaries[0] == 0`; every one of those holds on PS2
unchanged, including the 22050 Hz rate and the `channel_word ∈ {1, 2}` rule. The
**only** difference found is the value of `unit_word` at `body+0x90`:
`0x00012000` on Xbox, `0x0000C000` on PS2. Any PS2 catalog builder can be a
near-copy of the Xbox one with that constant re-pinned.

Verified across all 17: `boundaries[0] == 0` (17/17); boundaries strictly
ascending (17/17); every boundary a multiple of 16 (17/17); `boundaries[-1]`
equal to the byte size of exactly one raw outer entry (17/17); zero-filled tail
(17/17).

### The banks

| bank | file | ranges | ch | bank bytes | outer entry |
|---|---|---:|---:|---:|---:|
| lines | lines.bin | 30,269 | 1 | 1,568,883,200 | #4288 |
| players | players.bin | 22,420 | 1 | 212,146,224 | #4291 |
| cutsceneaudio | cutsceneaudio.bin | 278 | 1 | 25,609,024 | #4282 |
| teams | teams.bin | 251 | 1 | 2,791,056 | #4292 |
| animationaudio | animationaudio.bin | 179 | 1 | 11,992,048 | #4277 |
| cribmusic | cribmusic.bin | 59 | 2 | 221,957,504 | #4281 |
| crib22 | crib22.bin | 59 | 1 | 110,978,752 | #4280 |
| overlayaudio | overlayaudio.bin | 16 | 1 | 839,904 | #4290 |
| coacha | coacha.bin | 9 | 2 | 3,074,368 | #4279 |
| wrapupm | wrapupm.bin | 8 | 2 | 20,906,112 | #4293 |
| femusic | femusic.bin | 7 | 2 | 17,842,368 | #4286 |
| halftimeaudio | halftimeaudio.bin | 5 | 1 | 1,489,968 | #4287 |
| drafta | drafta.bin | 4 | 2 | 7,030,016 | #4285 |
| loadm | loadm.bin | 3 | 2 | 2,352,864 | #4289 |
| cwdsurr | cwdsurr.bin | 2 | 2 | 6,358,848 | #4284 |
| cwdloop (×2 descriptors) | cwdloop.bin | 1 | 2 | 3,179,424 | #4283 |

**53,571 logical ranges, 53,570 physical** (the two `cwdloop` descriptors share
one bank). Those are **exactly the Xbox numbers**, and the bank-name set is
identical.

Banks are resolved by the same rule as Xbox:
`zlib.crc32(filename.upper().encode("utf-16le")) & 0xFFFFFFFF` equals the outer
entry's `name_id` — **17 of 17 on PS2**.

---

## 6. The 45 unstructured entries — movies vs streams

Split by first bytes, unambiguously:

| class | count | first bytes | verdict |
|---|---:|---|---|
| MPEG-2 Program Stream | **28** | `00 00 01 BA 44 00 04 00` | PS2 `.PSS` movies — **out of scope** |
| Raw SPU-ADPCM | **17** | `XX 02 …` where `XX & 0xF ≤ 12`, `XX >> 4 ≤ 4` | the stream banks — **in scope** |

The 28 are genuine MPEG-PS: pack start `0x000001BA` with a `0x44` (MPEG-2)
marker, followed by a `0x000001BB` system header, and the first 64 KiB carry
start codes `0xBA` (pack), `0xBB` (system), `0xE0` (video stream 0) and `0xBD`
(private stream 1 — the PSS audio). Total 383,680,624 bytes; every one is
`≡ 4 (mod 2048)`. Replacing their audio means demux/remux of an MPEG program
stream and shares nothing with the SPU-ADPCM lane.

The 17 raw entries validate as SPU-ADPCM throughout: **0 invalid blocks across
2,426,255 sampled blocks** (6 ranges per bank, 1 MiB each) plus the orphan
scanned end to end, and every one of the 53,571 range sizes is a multiple of 16.
The flag byte is `0x02` on every sampled block **and on the true final block of
all 82 sampled ranges** — the streaming path carries **no `LOOP_END` at all**,
relying on the AUSB boundary table for length. That is a real behavioural
difference from `AUDO` and it matters for a streaming writer (§9).

**One orphan.** Entry **#4278** (1,589,712 bytes, 99,357 valid SPU blocks, all
flag `0x02`) is valid SPU-ADPCM but is **not the target of any AUSB boundary
table**, and its `name_id` `0xC03CFD42` did not match the CRC of any of ~230
guessed filenames. 16 named banks + 1 orphan = the 17 raw entries; the byte
accounting closes exactly (2,217,431,680 + 1,589,712 = 2,219,021,392).

---

## 7. Does the Xbox fixed-slot discipline hold on PS2? — **Yes, structurally. No, numerically.**

| question | answer |
|---|---|
| Same container and descriptor? | **Yes** — same 0x20 wrapper, same 8-word descriptor at the same biased pointer, same `codec_word 0x11` / `flags 0x35` |
| Same slot identity scheme (`outer_index`, `chunk_index`)? | **Yes** — 682 `(entry, chunk)` keys are common to both discs, 647 with the same name |
| Same slot **count**? | **No** — Xbox 850, **PS2 844** |
| Same slot **names**? | **Nearly** — every PS2 name exists on Xbox; the 6 extra Xbox names are the surround splits `boofront1/boorear1`, `chantdeffront1/chantdefrear1`, `precheerfront1/precheerrear1`, which PS2 collapses to `boo1/chantdef1/precheer1`. 850 − 6 = 844. |
| Same slot **sizes**? | **`system_bytes`: yes, 154/154** uniquely-named pairs. **`video_bytes`: no, 0/154** — the payload allocation is codec-specific (SPU 16 B / 28 samples vs IMA 36 B / 64 samples, ≈1.6 % larger on PS2). |
| Slots exact and non-overlapping? | **Yes.** All 153 adjacent AUDO pairs inside an entry have gap **0** — chunks are packed back-to-back, **there is no inter-chunk slack**. |
| Any slot crossing a 1 GiB pack seam? | **No AUDO does (0 of 844)** — same as Xbox. **2 of 17 stream banks do** (`crib22` #4280, `lines` #4288), the analogue of Xbox's 4-of-53,570 seam crossings. |
| AUSB range count? | **Identical to Xbox: 53,571 logical / 53,570 physical.** |

So the whole Xbox discipline — exact-slot, bind by `(outer, chunk)`, re-derive
the wrapper before writeback, prove non-overlap, prove nothing else moved —
ports directly. **What does not port is the catalog itself**: PS2 needs its own
generated capacity report, because every `video_bytes` differs.

### The duplicate-name problem is worse on PS2

161 distinct names across 844 chunks. `oclapha_01` and `oclapaa_01` occupy
**340 chunks each** (replicated per stadium scene), five menu sounds appear
twice, and only **154 chunks have a disc-unique name**. Xbox already records
that 697 of 849 slots have duplicate names or equal content and that runtime
selector ownership is *unproved*; PS2 inherits that caveat unchanged. A slot's
physical identity is exact; *which in-game event plays it* is not established
by anything offline.

---

## 8. Encoding — feasible, and exact-slot fitting is easier than on Xbox

### Cost of the encoder

A working stdlib SPU-ADPCM encoder + decoder is **~120 lines** (measured — the
probe under `docs/research/audio/` is that size, including a full decoder
transcribed from `Mixer.cpp`). Per 28-sample block it searches 5 filters × 13
shifts, simulating the decoder exactly and keeping the minimum squared error.

| variant | speed (pure Python, one core) | quality |
|---|---|---|
| exhaustive 5 × 13 | **0.13–0.17× realtime** (≈ 6–8 s CPU per second of audio) | see below |
| 2-shift heuristic (analytic shift bound ± 1) | **0.64–0.78× realtime** (≈ 1.3–1.6 s/s) | within 0.6 dB of exhaustive |

The 65 candidates and the blocks are independent, so the same NumPy trick the
Xbox lane used (`_encode_vectorised`) applies unchanged if speed ever matters.
For a user encoding one sound at a time it does not: the median `AUDO` is
0.84 s long.

Quality on inputs that are *not* already SPU-ADPCM lattice points:

| source | SNR |
|---|---|
| retail decoded, re-encoded | **bit-exact** (999 dB) |
| retail × 0.9 (transient-heavy whoosh) | 20.4–20.7 dB |
| synthetic tone + noise | 31.2–31.8 dB |

The 20 dB figure is a naive round-to-nearest quantiser on a transient-heavy
source; the Xbox IMA encoder gets 32–39 dB, and roughly 3 dB of that came from
its exhaustive start-index search. Expect a production SPU encoder with proper
per-block error search to land in the high 20s to low 30s. **This is a quality
knob, not a feasibility question.**

### Exact-slot fitting: a strict improvement over Xbox

Xbox requires the replacement to be **byte-identical in length**, which forces
an exact frame count (`frames == slot.frame_count`), because 64 frames ⇔
exactly `36 × channels` bytes and there is no legal filler.

PS2 does not have that constraint, because **SPU-ADPCM is self-terminating**.
Measured on `wipe_01` (22,528-byte slot):

```
11,264 bytes of real audio (half the original duration)
     + 704 silent 16-byte blocks
     = 22,528 bytes — the slot exactly
```

Set flag `0x03` (`LOOP_END | LOOP`, the retail convention) on the last real
block and fill the remainder with `00 03 00×14`. The SPU stops at the first
`LOOP_END`, so the filler is never played; the decoded tail is verified pure
silence. The declared `video_bytes` / `data_size` / `per_channel_data_size`
never change, so **no metadata is rewritten**.

**Rule for a PS2 writer:**
`encoded_bytes = ceil(frames / 28) × 16 × channels ≤ per_channel_size × channels`,
i.e. `frames ≤ per_channel_size // 16 × 28`. Equality is achievable; anything
shorter is padded. Longer is refused — there is no slack to grow into (§7:
adjacent-chunk gap 0 on 153 of 153 pairs).

Existing trailing silence in retail payloads is small and not a growth
opportunity: **10,108 of 554,139 blocks (1.82 %)**, 76 chunks have none at all,
max 478 blocks in one chunk.

### What the user supplies

Strict RIFF/WAVE, mirroring `nfl2k5_audo_fixed_slots.py`'s `_parse_wav`:

* `fmt ` then `data` and nothing else (no metadata chunks); chunks tile the file
* format tag 1 (integer PCM), **16-bit**
* `channels == slot.channels` (1 or 2)
* `sample_rate == slot.sample_rate` — **per slot**, one of the eight values in §3
* `frames ≤ per_channel_size // 16 × 28`

For stereo, the writer encodes each channel independently and concatenates
(L then R) — **not** interleaved (§3).

`tools/game_audio_convert.py` already sits in front of the strict parser on the
Xbox side and needs no change: it resamples and mixes to an arbitrary
`--channels/--sample-rate/--frames`, which is exactly this contract.

---

## 9. What an `offline-writer-proved` row needs

Scope the first row to **`AUDO` only**. It is 844 slots, 8.5 MiB, zero pack-seam
crossings, and self-contained. `AUSB` is a separate, larger row (§10).

### 9.1 Components, following `PS2_M1_PLAN.md` §3

| component | path | kind |
|---|---|---|
| Codec | `tools/spu_adpcm.py` | stdlib module: `decode`, `encode`, `block_valid` |
| Catalog builder | `tools/nfl2k5_ps2_audo_capacity_audit.py` | dev-time; reads the user's ISO, emits the capacity report |
| The report | `reports/assets/nfl2k5_ps2_audo_import_capacity.json` | **gitignored**; only its SHA-256 ships |
| Fixed slots | `mod_editor/core/nfl2k5_ps2_audo_fixed_slots.py` | Qt-free; binds a slot, parses the WAV, encodes, refuses |
| Writer | `mod_editor/core/ps2_audio_write_service.py` | Qt-free; produces the new ISO |
| Independent verifier | `tools/nfl2k5_ps2_audio_verify.py` | imports neither of the above |
| Validators | `tools/validate_nfl2k5_ps2_audio.sh` + `.bat` | registry `validation_command` |

### 9.2 Writer interface

```python
def plan_replacement(iso: Path, catalog, requests) -> AudioPlan
    # requests: {slot_id: wav_path}; slot_id = "nfl2k5ps2.audio.audo.o{outer:04d}.c{chunk:04d}"
    # per slot: re-read the live 0x20 wrapper + system buffer from the ISO and
    #   require (stored, system, video, 0,0,0,0) == the catalog's pinned tuple
    #   and the 8-word descriptor == the catalog's pinned tuple
    # parse the WAV against the slot's channels/rate/frame ceiling
    # status: ok | wav_rejected | slot_drifted | too_long

def run_replacement(plan, out_iso: Path) -> AudioReceipt
    # encode -> pad to per_channel_size with silent LOOP_END blocks -> concat channels
    # patch the payload inside the pack file, then
    # ps2_iso9660_writer.replace_files(iso, out_iso, {"/VC_20919/<n>.": patched_pack})
    # receipt: per slot -> outer/chunk, pack path, absolute payload offset,
    #   payload_size, retail payload sha256, new payload sha256, wav sha256,
    #   frames written, pad blocks, encoder version; plus the writer's
    #   declared_ranges block verbatim
```

**One real friction point.** `ps2_iso9660_writer.replace_files` is *whole-file*:
its `_resolve_content` does `path.read_bytes()`, and the VC packs are 1 GiB
each, so one AUDO byte costs a 1 GiB read, a 1 GiB write and 1 GiB of RAM. Its
`declared_ranges` then covers the entire pack extent, which is a much weaker
claim than "these 3,216 bytes changed". Two options:

* **(a) Use it as-is** and let the *audio* verifier make the tight claim, exactly
  as `tools/nfl_audo_wav_xiso_workflow.py` does on Xbox
  (`compare_and_hash(..., allowed)` over the whole image). Zero writer change;
  costs I/O.
* **(b) Add `replace_spans(source, destination, {iso_path: [(offset, bytes)]})`**
  to `ps2_iso9660_writer.py` — bounded in-extent patches that declare exactly
  the ranges written. ~½ day, strictly additive, and it is what every Phase-2
  surface (stadiums, text, playbooks) will want too.

**Recommend (b)**, and note it as a shared Phase-2 dependency rather than an
audio cost.

### 9.3 Independent verifier

`tools/nfl2k5_ps2_audio_verify.py`, importing neither the service nor the
fixed-slot module, given (source ISO, output ISO, receipt, catalog hash):

1. **Nothing outside the declared payload spans changed.** Stream both images
   and require byte equality everywhere except the receipt's payload ranges;
   the count of differing bytes must equal the receipt's claim exactly.
2. **The ISO tree is unchanged.** Re-walk both volumes with
   `ps2_iso9660_verify.walk` and require identical entries, LBAs and lengths —
   nothing relocated, no directory record touched. Also require identical file
   size including trailing slack.
3. **The wrapper and descriptor survived.** Re-read `0x20 + system_bytes` at each
   slot in the output and require it byte-identical to the source. This is what
   makes "no metadata was rewritten" evidence rather than a claim.
4. **The payload is structurally valid SPU-ADPCM.** Every 16-byte block:
   `shift ≤ 12`, `filter ≤ 4`, flag ∈ {0x02, 0x03}; exactly one `LOOP_END` per
   channel run and it is the last block of that run or the terminator of the
   real audio; `len(payload) == per_channel_size × channels`.
5. **The audio is the user's.** Decode each channel back and require it equals
   the encoder's output for the receipt's WAV — re-encoding independently from
   `tools/spu_adpcm.py` and comparing bytes.
6. **`SLUS_209.19` is untouched**, size and SHA-256 pinned before and after.
7. **No receipt entry names a slot absent from the catalog**, and the catalog's
   SHA-256 matches the shipped pin.

Exits non-zero on any violation, naming the slot and the byte offset.

### 9.4 Registry row

`nfl2k5ps2.audio.audo_exact_slot_replace`, `surface: "audio"`,
`classification: "offline-writer-proved"`, `backend.operation: "write"`,
`SURFACE_GAMES["audio"]` widened to include `nfl2k5_ps2`. Per the passivity
review this is a **two-sided atomic** change: the row and the `SURFACE_GAMES`
entry must land in one commit, `validate_registry.py` asserts *equality* of
expected coverage, and every count pin (`71→72` class, `EXPECTED_COVERED_
CAPABILITIES`, `EXPECTED_UNIQUE_VALIDATORS`, the prose strings) moves with it.
Template: `93e1f6a`. Treat it as the watched commit.

`runtime.status: "not-tested"` — and it should stay that way until someone
witnesses a replaced sound in PenguinScreen2, which is a separate step and is
harder here than for textures because of §7's duplicate-name problem.

---

## 10. Revised effort

The plan's **8–12 d, "unfounded"** was the right order of magnitude for the
wrong reason. The codec was assumed to be the risk; it is the cheapest item on
the list. A reference decoder sits in-tree (`pcsx2-VR/pcsx2/SPU2/Mixer.cpp`),
the algorithm is 5 coefficient pairs and a 4-bit quantiser, and a working
encoder round-trips retail bytes exactly at ~120 lines. The expensive part is
the same catalog / claims / registry / verifier machinery every other row pays
for, which is a **port, not research**.

| work package | estimate |
|---|---|
| A. `tools/spu_adpcm.py` — encoder + decoder + tests, byte-exact round-trip oracle over N retail slots | **1 d** |
| B. Catalog builder + capacity report + claim gates (port of `nfl_audo_import_capacity_audit.py`) | **1–1½ d** |
| C. `nfl2k5_ps2_audo_fixed_slots.py` — slot binding, strict WAV parse, encode, pad, refuse, rollback | **1½–2 d** |
| D. `replace_spans` in `ps2_iso9660_writer.py` (shared with every Phase-2 surface) | **½ d** |
| E. Write service + independent verifier + both validators | **1½–2 d** |
| F. Registry row, pins, allowlist, changelog, version-truth bump | **1 d** |
| G. Tests (synthetic ISO fixture; mutate-a-byte-and-fail cases) | **1 d**, partly parallel |

**AUDO lane total: 6–8 implementation days** — modestly *below* the plan's
8–12, and much better founded. No rig time, no emulator; a runtime witness is a
separate ½–1 d plus rig time and is not required for `offline-writer-proved`.

**The AUSB streaming lane is a second row, not part of this one: +4–6 d.** It
carries 53,570 slots instead of 844, 2.07 GiB instead of 8.5 MiB, two banks
that straddle a 1 GiB pack seam (so writes become transactional across pack
files, the same shape as the Xbox `StreamingPackSpan` work), no `LOOP_END`
convention to lean on, and a stereo layout that is a working model rather than a
proof (§11).

Combined, honestly: **10–14 days for both rows**, of which the codec is one.

---

## 11. Open questions

**The biggest one, and it is not a format question: runtime selector
ownership.** 690 of 844 `AUDO` chunks share a name with another chunk —
`oclapha_01` and `oclapaa_01` account for 680 of them, replicated once per
stadium scene entry — leaving only **154 chunks with a disc-unique name**. Every
physical slot is exact and provably non-overlapping, but *which slot a given
in-game event plays* cannot be established offline by anything on this disc. It
is the same wall the Xbox lane documents (`runtime_selector_owner: "unproved"`
on all 849 of its rows), and it is the reason the row stops at
`offline-writer-proved` rather than promising an audible change. A first runtime
witness should therefore target one of the 154 uniquely-named slots — the menu
sounds are the obvious pick.

**Second: stereo layout inside the streaming banks — working model, not
proved.** `AUDO` stereo is settled (contiguous halves, two independent proofs,
§3). For the eight stereo *streaming* banks the evidence is one step weaker.

A first attempt using a spectral-roughness statistic favoured 16-byte block
interleave, but **the mono `lines` bank scored the same way**, so that metric is
confounded: de-interleaving with the wrong predictor state adds low-frequency
drift, which lowers the statistic instead of raising it. Discard that result.

The instrument that does work is a seam test — the ratio of squared first
differences *at* 28-sample block boundaries to those between them. Within one
intact ADPCM chain the ratio is ≈ 1; splicing foreign blocks together puts a
predictor jump at every boundary and drives it up. Measured on all eight stereo
banks plus two mono controls (`docs/research/audio/seam.py`):

| hypothesis | stereo banks (8) | mono controls |
|---|---|---|
| linear / contiguous | **0.92 – 1.04** | 1.04, 1.06 |
| 16-byte interleave | **1.07 – 1.29** (worst on all 8) | 0.95–1.14 |
| 32…2048-byte interleave | 0.93 – 1.24, no hypothesis beats contiguous | — |

So **block interleave is ruled out** at every granularity tested; the ADPCM
chain runs linearly through a range. The remaining candidate is the same shape
`AUDO` uses — **two contiguous per-channel halves, L then R** — which is
consistent with every measurement (all sampled ranges have `size/2 ≡ 0 mod 16`,
and decoding from the midpoint gives ratio ≈ 1) and with how the SPU wants its
data. Two caveats keep it a model rather than a proof: unlike `AUDO` there is no
midpoint `LOOP_END` to point at, and decoded L/R correlation on `femusic`
range 0 is only +0.04 — low for music, though unremarkable for the crowd and
ambience beds that dominate these banks (`cwdsurr`, `cwdloop`), where
decorrelated channels are the point. Confirm by ear before shipping a streaming
writer. **None of this blocks the `AUDO` row.**

Secondary, none blocking:

* **Entry #4278** — 1,589,712 bytes of valid SPU-ADPCM referenced by no AUSB
  directory. Its `name_id` is `0xC03CFD42`; the CRC rule that resolves the other
  16 banks will name it as soon as the right filename is guessed or found in
  `SLUS_209.19`.
* **`body+0x84`** in AUSB is nonzero only for `lines`, `players` and `teams`
  (the three banks with named sub-entries) and is not a CRC of either name.
* **`AUSB` `unit_word`** is `0xC000` on PS2 against `0x12000` on Xbox. It tiles
  neither the ranges nor the banks, so it is a buffer size, not a layout
  constraint — but it is unconfirmed.

---

## 12. Reproducing this

The probes live under the gitignored `docs/research/audio/` in this worktree
(`disc.py` virtual-offset reader, `spu.py` decoder, `survey2.py`,
`verify_layout.py`, `ausb.py`, `stream_probe.py`, `xcompare.py`,
`encode_test.py`, `interleave.py`, `seam.py`). They are throwaway; every number
in this document is reproducible from the stock ISO plus the committed
`inventory_ps2.tsv.gz` / `inventory_xbox.tsv.gz`.

Pack addressing, for anything that needs it: the outer archive is
`/VC_20919/{0..4}.`, at LBAs 14639 / 538927 / 1063215 / 1587503 / 2111791, each
1 GiB except pack 4 (340,113,408 bytes). A virtual offset `v` from the inventory
is `pack = v >> 30`, `iso_byte = PACK_LBA[pack] * 2048 + (v & 0x3FFFFFFF)`.

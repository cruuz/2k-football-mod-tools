# APF 2K8 AUSB exact-slot replacement feasibility

Date: 2026-07-19  
Alpha 28 product refresh: 2026-07-20  
Scope: all APF external `AUSB` substreams, with a detailed paired
`jukeboxmusic` / `jukebox22` soundtrack experiment  
Source policy: the recognized private source was opened read-only; this report
contains metadata and hashes only, not game audio, descriptor bytes, or
preimages.

Product state: the writer remains integrated end to end in the Alpha.28
source/UI checkpoint. Alpha.28 supports selected-sound PCM16 and v2 PCM16
folder/ZIP packs through a separately installed encoder while preserving the
strict exact-slot XMA1 route and byte-compatible v1 packs. This report embeds no
archive hash or size. A packaged release's authoritative identity belongs in
its adjacent `.sha256` sidecar, and packaged visual-QA closure is not claimed
here.

Release-wide roster boundary: Alpha.23's 32-team × 53-row roster surface is a
planner, not a capacity writer. Stock APF consumes the first 42 membership rows
per populated team; rows 43–53 are project-only reserve choices and Build does
not apply them. True runtime slots 43–53 still require a version-pinned
emulator-target XEX consumer/accessor patch plus owned side-table storage, and
teams 25–32 retain unproved offline selector ownership.

## Result

**A bounded exact-slot writer is implemented for every AUSB substream without
repacking an external bank or changing an AUSB descriptor.** The final safe
input is deliberately narrow: one one-stream RIFF XMA1 file whose raw `data`
length, channel count, sample rate, and decoded sample count fit the selected
existing allocation. Alpha 27 can obtain that file either directly as
pre-encoded XMA1 or from one exact PCM16 WAV through a user-configured external
encoder. V2 folder/ZIP import accepts up to 256 supplied exact-shape WAVs as
one atomic transaction. No encoder ships with Mod Studio. FLAC/MP3,
mixed-format packs, more than 256 supplied WAVs per import, and size-changing
XMA remain unsupported.

The completed source experiment established:

- 20 AUSB descriptors and 45,514 semantic substream rows;
- 19 physical external banks and 45,513 canonical physical ranges;
- all 1,144,270,848 source bank bytes are partitioned into nonempty,
  packet-aligned, contiguous ranges, with no partial physical overlaps;
- a full source scan found every packet in every canonical range uses the APF
  XMA1 header contract: XMA1 classification, sequence nibble `0`, metadata `2`,
  and packet skip `0`;
- 40,316 unique whole-payload hashes exist among the 45,513 canonical ranges;
  this is an inventory/topology measurement, not the authorization boundary.
  The product instead inventories every complete `0x800`-byte packet across
  both the 2,261 AUDO slots and all 45,513 canonical AUSB ranges;
- exactly one range has two owners: external outer `717`, offset `0`, length
  `1,470,464`, owned by both `137:8:0` and `659:289:0` (`cwdloop`). Any edit
  affects both owners. Identical alias edits may deduplicate; divergent edits
  must fail;
- 45,512 canonical ranges occupy one physical pack span. One range occupies
  two spans: `jukeboxmusic` substream index `2`—display Track 3—crosses the end
  of `0A` and start of `0B`;
- the largest individual slot is `10,819,584` bytes (`jukeboxmusic` substream
  index `11`, display Track 12).

The offline writer and complete product path are proved. Runtime causality is
not. A private Alpha.23 candidate booted, selected **Track 12 — Bury Me Standing
Remix**, and visibly remained in playback for 25 seconds without a crash.
The completed objective capture experiment was negative/inconclusive for
modified-stream causality. The final sustained segment matched neither the
mutated candidate nor stock Track 12; the best 17-second absolute normalized
cross-correlation was about `0.031`, and candidate-versus-stock distinguishing
frames favored neither meaningfully. A self-control confirmed classifier power.
The observation therefore proves boot/selection/stability only. It proves
neither authored-audio consumption nor stock fallback, and the runtime status
remains partial.

## Ownership and physical banks

Both soundtrack descriptors are in IFF outer `1310`:

| Bank | Descriptor | DRAM part | Header shape | External owner |
|---|---:|---:|---|---|
| `jukeboxmusic` | `1310:21` | offset `5,729,152`, length `256` | 15 entries, 48,000 Hz, layout `5`, 2 channels | `jukeboxmusic.bin`, outer `793`, ID `0x826e3bf9`, 75,575,296 bytes |
| `jukebox22` | `1310:403` | offset `5,728,896`, length `256` | 15 entries, 22,050 Hz, layout `2`, 1 channel | `jukebox22.bin`, outer `958`, ID `0xa018c674`, 27,260,928 bytes |

Physical placement:

- `jukebox22.bin`: `0A @ 1,103,865,856 + 27,260,928`;
- `jukeboxmusic.bin`: `0A @ 1,131,126,784 + 9,723,904`, then
  `0B @ 0 + 65,851,392`;
- `jukebox22.bin` ends exactly where `jukeboxmusic.bin` begins in `0A`;
- neither outer entry overlaps any other outer archive entry;
- every track boundary is a `0x800`-byte XMA packet boundary, and the union of
  the 15 ranges covers each external entry exactly.

The `jukeboxmusic` and `jukebox22` rows pair by substream index. Their duration
floats differ by at most `0.00003814697265625` seconds.

## Per-track exact ranges

`external range` is relative to the named external bank. A physical span is
`pack@offset+length`. Delta is declared samples minus FFmpeg-decoded samples.

| # | seconds stereo / mono | stereo external range | stereo physical span(s) | mono external range | mono physical span | declared samples stereo / mono | FFmpeg 6.1.1 source decode |
|---:|---:|---:|---|---:|---|---:|---|
| 1 | 153.601089 / 153.601089 | 0+3,977,216 | 0A@1,131,126,784+3,977,216 | 0+1,286,144 | 0A@1,103,865,856+1,286,144 | 7,372,852 / 3,386,904 | stereo fails `-xerror`; mono pass Δ+24 |
| 2 | 190.906708 / 190.906708 | 3,977,216+3,323,904 | 0A@1,135,104,000+3,323,904 | 1,286,144+1,587,200 | 0A@1,105,152,000+1,587,200 | 9,163,522 / 4,209,493 | stereo fails `-xerror`; mono pass Δ-43 |
| 3 | 178.541580 / 178.541580 | 7,301,120+3,868,672 | 0A@1,138,427,904+2,422,784<br>0B@0+1,445,888 | 2,873,344+1,544,192 | 0A@1,106,739,200+1,544,192 | 8,569,996 / 3,936,842 | stereo fails `-xerror`; mono pass Δ-54 |
| 4 | 249.916000 / 249.916016 | 11,169,792+5,728,256 | 0B@1,445,888+5,728,256 | 4,417,536+2,101,248 | 0A@1,108,283,392+2,101,248 | 11,995,968 / 5,510,648 | stereo fails `-xerror`; mono pass Δ-8 |
| 5 | 263.483002 / 263.483032 | 16,898,048+5,859,328 | 0B@7,174,144+5,859,328 | 6,518,784+2,103,296 | 0A@1,110,384,640+2,103,296 | 12,647,184 / 5,809,801 | stereo fails `-xerror`; mono pass Δ+9 |
| 6 | 223.669327 / 223.669342 | 22,757,376+5,767,168 | 0B@13,033,472+5,767,168 | 8,622,080+1,943,552 | 0A@1,112,487,936+1,943,552 | 10,736,128 / 4,931,909 | stereo fails `-xerror`; mono pass Δ-59 |
| 7 | 206.264328 / 206.264359 | 28,524,544+4,433,920 | 0B@18,800,640+4,433,920 | 10,565,632+1,765,376 | 0A@1,114,431,488+1,765,376 | 9,900,688 / 4,548,129 | stereo pass Δ+16; mono pass Δ+33 |
| 8 | 146.916962 / 146.916962 | 32,958,464+4,177,920 | 0B@23,234,560+4,177,920 | 12,331,008+1,230,848 | 0A@1,116,196,864+1,230,848 | 7,052,014 / 3,239,519 | stereo pass Δ-18; mono pass Δ-33 |
| 9 | 239.178360 / 239.178360 | 37,136,384+6,320,128 | 0B@27,412,480+6,320,128 | 13,561,856+2,252,800 | 0A@1,117,427,712+2,252,800 | 11,480,561 / 5,273,883 | stereo fails `-xerror`; mono fails `-xerror` |
| 10 | 193.205338 / 193.205353 | 43,456,512+4,597,760 | 0B@33,732,608+4,597,760 | 15,814,656+1,628,160 | 0A@1,119,680,512+1,628,160 | 9,273,856 / 4,260,178 | stereo fails `-xerror`; mono fails `-xerror` |
| 11 | 175.258667 / 175.258682 | 48,054,272+3,196,928 | 0B@38,330,368+3,196,928 | 17,442,816+1,542,144 | 0A@1,121,308,672+1,542,144 | 8,412,416 / 3,864,454 | stereo pass Δ+0; mono pass Δ+6 |
| 12 | 381.823792 / 381.823822 | 51,251,200+10,819,584 | 0B@41,527,296+10,819,584 | 18,984,960+3,164,160 | 0A@1,122,850,816+3,164,160 | 18,327,542 / 8,419,215 | stereo pass Δ-10; mono pass Δ+15 |
| 13 | 206.821335 / 206.821365 | 62,070,784+3,856,384 | 0B@52,346,880+3,856,384 | 22,149,120+1,878,016 | 0A@1,126,014,976+1,878,016 | 9,927,424 / 4,560,411 | stereo fails `-xerror`; mono fails `-xerror` |
| 14 | 120.584541 / 120.584579 | 65,927,168+3,565,568 | 0B@56,203,264+3,565,568 | 24,027,136+1,126,400 | 0A@1,127,892,992+1,126,400 | 5,788,058 / 2,658,890 | stereo pass Δ+26; mono pass Δ-54 |
| 15 | 260.205322 / 260.205353 | 69,492,736+6,082,560 | 0B@59,768,832+6,082,560 | 25,153,536+2,107,392 | 0A@1,129,019,392+2,107,392 | 12,489,855 / 5,737,528 | stereo pass Δ-1; mono pass Δ+56 |

## Duration and loop semantics

Each descriptor has one `(float, packet offset)` boundary per substream plus a
terminal boundary. For substream `i`:

- encoded bytes begin at boundary `i`'s packet offset;
- encoded bytes end at boundary `i+1`'s packet offset, or at the terminal
  boundary for the last substream;
- the duration belongs to the *following* boundary;
- declared samples are `round(duration_float * sample_rate)`;
- boundary zero duplicates Track 1's duration;
- no explicit per-substream loop-start, loop-end, or loop-subframe fields exist
  in the AUSB descriptor;
- the 40 bytes after the terminal boundary are zero in both jukebox
  descriptors.

The writer therefore leaves every descriptor byte unchanged and wraps user
packets with loop values `0/0/0` only in ephemeral validation memory. It does
not claim that higher-level jukebox playback never loops; it only establishes
that loop control is not stored in these per-track descriptor rows.

## Decoder sweep

All 30 source soundtrack sides were wrapped without changing their packets and
decoded using FFmpeg `6.1.1-3ubuntu5`, `-xerror`:

- 18/30 decoded completely;
- every successful decode was within 59 samples of its duration-derived
  declared count;
- 12/30 failed in FFmpeg's XMA1 decoder, despite passing the complete packet
  framing scan and being retail game inputs.

The failures mean FFmpeg 6.1.1 is not a universal decoder for the retail
soundtrack. They do **not** make fixed-range replacement unsafe. The importer
uses a deliberately conservative rule: a *replacement* must decode cleanly
with `-xerror` and land within ±127 samples of the selected declared count.
Some otherwise valid Microsoft-encoded XMA1 inputs may consequently be
rejected until a stronger reference decoder is available.

## Concrete writer contract

Implemented in `tools/apf_ausb_exact_slot.py`:

1. Discover all AUSB descriptors from the user's selected source. No bundled
   coordinate manifest is trusted.
2. Resolve each `(descriptor outer, descriptor inner, substream)` identity to
   `(external outer, range offset, range length)` and one or more physical pack
   spans.
3. Attach every semantic owner to a canonical physical identity. Disclose a
   shared effect when an alias exists.
4. Parse a user-provided RIFF/WAVE XMA1 file. Require one stream, one `fmt `,
   one `data`, 16-bit output, target channels and rate, and an exact target-size
   packet payload.
5. Require every user packet to classify XMA1 with sequence `0`, metadata `2`,
   and skip `0`.
6. Rewrap only in memory with the source-owned duration shape and zero loop
   fields. Run complete `ffmpeg -xerror` decode and require target channels,
   rate, and sample count within ±127.
7. Construct one fingerprint inventory for every complete `0x800`-byte source
   packet in both audio domains. Reject a replacement if any complete packet
   matches either the AUDO or AUSB inventory. This blocks same-family reuse,
   cross-family transplants, and a retail packet hidden inside an otherwise
   changed payload.
8. Store only canonical user `.xma1-packets` plus retail-free JSON metadata.
9. On build, recheck exact size, packet framing, semantic metadata, and the
   complete cross-domain packet gate, then split the payload across its physical spans.
   Every individual physical source span carries its own SHA-256 guard. The
   builder writes only disposable staged pack copies, verifies every changed
   span and all bytes outside them, and publishes the full multi-pack output
   atomically.
10. Merge overlapping writes by physical byte range. Identical writes to the
    same canonical alias may deduplicate; any divergent or partial overlap is
    rejected.

The helper `validate_paired_soundtrack_import` applies the contract to both
jukebox encodings and returns nothing unless both succeed.

## Alpha.23 product integration

- All 45,514 semantic substream rows expose Replace/Revert, modified state,
  Undo, project save/load, replacement preview, and typed Build. The 20 AUSB
  index rows and 19 physical-bank rows remain descriptive/raw-export rows, not
  one-sound editors.
- Session/project admission resolves the selected semantic coordinate against
  the currently loaded source, rechecks target shape and every shared owner,
  and stores only the user's canonical `.xma1-packets` plus a retail-free owner
  fingerprint and target shape. Session admission, project load, and modified
  preview each rebuild or require the complete cross-domain packet inventory and
  reject any replacement containing a source packet from either audio family.
- Build groups all AUSB modifications before writing. The dedicated compiler
  re-resolves the live targets, source-guards every physical span, supports the
  Track 3 `0A`/`0B` split, deduplicates identical aliases, and rejects divergent
  physical overlap before an output directory can publish. Final Build repeats
  the two-family packet authorization rather than trusting session state.
- The build manifest emits one row per semantic modification. Those rows carry
  semantic asset IDs, replacement hashes, target shape, owner disclosure, and
  changed pack names, but no source payload hash, preimage, physical offset,
  external-range coordinate, canonical physical ID, or retail byte.

## Verification

Focused test command:

```bash
python3 -m unittest tests.mod_editor.test_apf_ausb_exact_slot -v
```

Result: **10/10 passed**. This includes the complete 1.144 GB source packet/hash
scan, the `cwdloop` alias, the cross-volume jukebox span, retail-byte rejection,
paired validation, exact write splitting, and divergent-overlap rejection.

Focused product/build command:

```bash
python3 -m unittest -v \
  tests.mod_editor.test_apf_build_ausb_overlays \
  tests.mod_editor.test_apf_build_raw_span_overlays \
  tests.mod_editor.test_apf_ausb_exact_slot \
  tests.mod_editor.test_apf_audo_exact_slot
```

The command above passes **39/39**. The dedicated cross-domain safety suite
passes **4/4**. It proves that an AUSB
source packet cannot enter an AUDO replacement, an AUDO source packet cannot
enter an AUSB replacement, independently authored packets clear both domains,
and the final Build gate repeats the cross-domain check. The focused combined
audio/build suite passes **25/25**, and the complete headless APF source suite
passes **348/348**. The full product suite passes **722/722 in 93.739s**.

A bounded real-source final Build run scanned both source audio domains and
rejected an 8-bit-mutated Track 12 near-retail candidate at replacement packet
0. That candidate had passed the old whole-payload-only check. The scan completed
in 14.13 seconds with 208,896 KiB peak RSS. No candidate bytes, private path, or
hash are included here.

## Remaining work

- Do not replay the same ambiguous Track 12 input. Use a wholly independently
  encoded, unmistakable replacement when a usable XMA1 encoder exists, or trace
  mixer/routing before another runtime replay.
- Runtime spot-check at least one non-soundtrack AUSB family rather than
  generalizing the soundtrack selection/stability result to commentary or PA.
- Runtime-test one legally obtained external XMA1 encoder configuration without
  redistributing it. Alpha 28's selected/v2-template, no-shell process, and
  validator handoff have synthetic proof only; they do not prove real encoder
  compatibility or authored-audio consumption.
- Keep v2 PCM packs bounded to exact listed shapes and 256 supplied WAVs per
  transaction. FLAC/MP3 and mixed-format input remain unsupported.
- This report deliberately leaves Alpha.28 archive size/hash and final
  packaged seal/visual-QA facts to the authoritative adjacent sidecar and
  packaging receipt rather than inventing or duplicating them here.

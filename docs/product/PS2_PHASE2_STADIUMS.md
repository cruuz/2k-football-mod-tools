# Phase 2, PS2 stadiums: bounded geometry editing on `SLUS-20919`

Status: **offline writer built and structurally proved; runtime untested.**
Branch `p2-stadiums`. No registry row is claimed by this work.

---

## Headline: this was not a port

The plan said the PS2 stadium writer was a port of the Xbox one, because "the
PS2 SCNE strides already fell out of the inventory work for free". That is true
of the **table** strides and false of everything below them. The capability
triage reached the same conclusion independently, mid-flight, and it was right:
nothing in this repository had ever read a byte of PS2 vertex payload.

So the first half of this work was research, not porting. The layout was
established empirically against the retail disc and it **differs from Xbox at
every level that matters to a geometry writer**.

| | Xbox (`nfl_stadium_catalog_position_patch.py`) | PS2 (this work) |
|---|---|---|
| shape record | 0x100 bytes | **0x70 bytes** |
| vertex count | `u16` at `+0x4C` | **no such field** — it is the VIF `UNPACK` `NUM` |
| vertex streams | 8 stride/pointer pairs at `+0xC4` / `+0xD4` | **none** |
| position lane | register 0, `FLOAT3`, contiguous run of stride 12 | **`UNPACK V4_32`: strided `FLOAT4`, 12 editable bytes every 16** |
| topology | NV2A push buffer per 0x80-byte submesh record | **VU1 microprogram invoked by `MSCAL`; no index list is decoded** |
| colours / UVs | separate vertex streams | **inline in the same DMA chain** (`V4_5`, `V2_16`) |

What *did* port, unchanged and byte-for-byte: the outer VC pack container, the
`0x20` resource wrapper, the field-local minus-one-biased relative pointer
(`target = field + s32 - 1`), the VC-LZ codec, and — most usefully — the
discipline. "Same count, same topology, only catalogued position lanes may
change, refuse before writing anything" survives the format change intact.

## The PS2 geometry format, as established

Read against `/VC_20919` outer entry 1556, chunk 2, scene `stadium`
(101 shapes, 654 batches, 23,075 vertices), then re-checked per target.

```
scene descriptor  +0x2C  u32 shape count
                  +0x30  s32 -> shape table, stride 0x70

shape             +0x30  3 x f32 bounding-sphere centre  (+0x3C is 1.0)
                  +0x40  s32 -> UTF-16LE shape name
                  +0x4C  f32 bounding-sphere radius
                  +0x68  u32 batch count
                  +0x6C  s32 -> batch table, stride 0x18

batch             +0x00  s32 -> DMA/VIF geometry chain
                  +0x04  u32 byte size of the chain's first DMA packet
                         (agrees for 194 of 1041 targets; meaning unproved,
                          recorded and never relied on)

chain             128-bit DMA tag qwords: a 64-bit tag then two 32-bit VIF
                  codes. The tag's low u16 is QWC; bits 28..30 are the tag id;
                  ids 0 (refe) and 7 (end) terminate. QWC qwords of VIF data
                  follow each tag.

VIF               cmd is byte 3. cmd >= 0x60 is UNPACK, with vn = (cmd >> 2) & 3
                  and vl = cmd & 3 giving the element shape, NUM (byte 2, where
                  0 means 256) the element count, and the low 10 bits of IMM the
                  VU address.

position lane     an UNPACK V4_32 with NUM > 1: NUM elements of four
                  little-endian binary32 (x, y, z, w).
```

A representative batch decodes as `V4_32 num=1` (a constant), `V4_16 num=10`
(a header/index block), `V4_5 num=30` (colours), `V2_16 num=30` (UVs),
`V4_32 num=30` (**positions**), then `MSCAL`.

### Why "these are the positions" is evidence, not a guess

Every one of the **23,075** decoded vertices, across all 1,041 lanes, lies
inside its own shape's declared bounding sphere. The maximum
distance-over-radius over the whole set is **exactly 1.000000**, and **242 of
the 1,041 lanes reach past 0.999** — they touch the surface. The spheres are
tight fits round precisely these points and nothing else. No unrelated lane —
not the colours, not the UVs, not the header block — produces that, and a lane
that failed would be excluded, so the claim is enforced per target rather than
asserted once.

Coverage on that scene: **646 of 654 batches (98.8%)** parse cleanly to a
terminator with every VIF code understood. The 8 refusals are all the same
unknown VIF command `0x3F`; they are excluded, not guessed at.

## The hard part: recompression must fit

An SCNE lives VC-LZ-compressed inside a chunk whose successors begin exactly
`0x20 + stored_size` later, so the rebuilt span must be exactly the size of the
old one. Three nested fixed allocations have to hold at once:

1. **ISO** — `ps2_iso9660_writer.replace_files` writes a file inside the extent
   it already owns, zero-fills the tail and patches the both-endian length in
   place. The image keeps its exact byte length.
2. **Pack** — the rebuilt chunk span is byte-for-byte the same size, so no
   successor chunk moves and no outer entry changes.
3. **Stream** — the VC-LZ body must fit `stored_size` **and** the wrapper's
   `+0x14` in-place-decode scratch word must stay at its retail value.

### The measurement that decided the design

Fifty-three stadium SCNE chunks were decoded off the retail disc and their
spare stored bytes measured:

| | bytes |
|---|---|
| minimum headroom | **0** |
| 25th percentile | 5 |
| median | **8** |
| 75th percentile | 12 |
| maximum | **16** |

The retail packer packed every one of them to within 0-16 bytes of its
allocation, out of ~1.3 MB. **A retail-identical encoder therefore has no room
for any edit at all.**

Two further facts made the solution available rather than inventable:

* `nfl_txtr.compress_vc_lz` reproduces the retail **PS2** stream byte for byte
  (verified on entry 1556 chunk 2: 1,306,541 bytes, `stream_tag=174`,
  `offset_bits=13`, exact match in 12.6 s). The PS2 disc was packed by the same
  packer as the Xbox one. So a no-op is provably free.
* `nfl_vc_lz_fill.compress_optimal` packs the same token format ~1-1.5% tighter
  with an optimal parse, which on a 1.3 MB stream is ~15 kB of recovered room —
  three orders of magnitude more than a position edit needs.

So the writer uses `nfl_vc_lz_fill.rebuild_fixed_span_filled(..., encoder="auto")`
exactly as written: greedy first, optimal only if greedy will not fit, then
trailing matches expanded back into literals so the body still *fills*
`stored_size` and the scratch word never has to move. **Raising that word is
what hung the Xbox attract demo on 2026-09-03**, so this writer never does; the
verifier independently requires the whole `0x20` wrapper to be byte-identical.

If the stream still does not fit, the writer refuses **before the destination
image is created**. That is the pack-level twin of the ISO writer's
fixed-allocation rule, and it is tested.

### How often does an edit actually fit? Sampled, 12 scenes

Because greedy reproduces the retail stream byte for byte, `len(greedy(edited))
- retail_consumed` **is** the edit's cost in bytes, exactly. Twelve stadium
scenes were sampled, each moving every vertex of its largest eligible lane
(51-56 vertices) by +400 on y (medians below are upper medians,
`sorted[n // 2]`; the raw rows are published, so they can be recomputed):

| | bytes |
|---|---|
| edit cost, minimum / median / maximum | 3 / **42** / 182 |
| retail headroom, minimum / median / maximum | 3 / **11** / 13 |
| scenes the retail-identical parse still fits | **3 of 12** |

So for three quarters of the sample the retail parse is not enough, and the
optimal-parse fallback is load-bearing rather than a nicety. It recovers about
one per cent of a ~1 MB stream — roughly 10,000 bytes against a worst sampled
cost of 182 — so every sampled scene is expected to fit, and one is confirmed
end to end below. The raw per-scene rows are in the trial JSON under
`fit_sampling`.

Two smaller facts fell out of that sampling and are worth writing down: the
scenes use both `offset_bits` 12 and 13, so the writer must take the encoder
geometry from the source stream rather than assume one; and cost does not track
vertex count (182 bytes for 53 vertices, 3 bytes for 54), because it depends on
how the new float bytes happen to match the LZ window.

### ⚠ The fill step is the writer's runtime, and it is quadratic

Measured on the trial scene (1,917,856 decoded bytes, `offset_bits` 13):

| stage | time |
|---|---|
| greedy encode, refuses — the edit does not fit | 43 s |
| optimal-parse encode — 1,296,233 bytes, **10,311 spare** | 73 s |
| `fill_stream` expanding those 10,311 bytes back into literals | **tens of minutes** |

`nfl_vc_lz_fill.fill_stream` re-serializes the entire token stream on every
candidate expansion and rebuilds the token list with a slice-concat each time.
Measured on this scene: **961,758 tokens, 1.478 s per `serialize`**, 10,295
bytes to close, and a mean match length of 5.46, so each successful expansion
recovers only about four bytes and roughly **2,600 expansions** are needed —
each one O(n). That is where a one-lane stadium edit spends the overwhelming
majority of its wall clock.

This is a **property of the shared helper, not of this writer**, and nothing
here was changed to work around it — `nfl_vc_lz_fill.py` belongs to the Xbox
lane and is used exactly as written. But anyone putting a progress bar or a GUI
in front of this needs to know that one stadium edit is a tens-of-minutes
operation today, and that making it interactive is an afternoon's work inside
`fill_stream` (track the serialized length incrementally instead of
re-serializing the whole stream) rather than a research problem. The Xbox lane
never hit this because it only ever fills a few bytes; a PS2 stadium starts
10 kB short because the optimal parse is what made it fit at all.

## What shipped

| file | what it is |
|---|---|
| `tools/nfl2k5_ps2_stadium_target_catalog.py` | enumerates stadium scenes, shapes, batches and position lanes; emits `reports/gameplay_tuning/nfl2k5_ps2_stadium_target_catalog.v1.json` |
| `tools/nfl2k5_ps2_stadium_position_patch.py` | stock ISO in, **new** ISO out, through `ps2_iso9660_writer.replace_files` |
| `tools/nfl2k5_ps2_stadium_position_verify.py` | independent; standard library only |
| `tools/validate_nfl2k5_ps2_stadium_position.sh` / `.bat` | deterministic validators, no game data |
| `tests/mod_editor/test_nfl2k5_ps2_stadium_position.py` | 19 synthetic tests |

The recipe format is `nfl2k5_ps2_stadium_position_recipe/v1`: a schema string, a
`{schema, sha256}` pin of the catalogue it was authored against, and a list of
`{target_id, positions}` edits. It carries the user's coordinates and nothing
else. Vertex count is **not** in the recipe — it comes from the pinned
catalogue row, and a mismatch is refused, because on PS2 the count is a VIF
`NUM` field and changing it is a topology change.

### One PS2-specific hazard the catalogue records

Several batch descriptors can point at the **same** DMA chain, so one position
lane is reachable under more than one `target_id`. Of 1041 targets, there are
**890 distinct payload spans**; 274 targets share a span with another (101
spans have 2 targets, 16 have 3, 6 have 4). Each row carries
`payload_span_target_count`, and the writer refuses a recipe that edits two
aliases of one lane. This was found the hard way: the first real-disc trial run
was refused by exactly that check, which is the check working.

## Real-disc trial

Run offline on a copy of the user's own image; the stock ISO was opened
read-only and its digest re-checked afterwards. **No emulator and no hardware
were involved** — the in-game witness is a later step on the rig, not part of
this work.

Full receipts, including every digest and declared byte range, are in
`reports/gameplay_tuning/nfl2k5_ps2_stadium_trial.v1.json`.

**What was edited.** Outer entry 1556, chunk 2 — the scene the catalogue was
generated for. Shape 98, `sideline_home_south`, bounding radius 3,974.5: its
five largest **distinct** position lanes, 250 vertices between them, every
vertex translated `+400` on `y`. Five lanes and not one because anyone editing
a shape would reach for its largest lanes together rather than one in
isolation, and because collapsing the shape's targets down to distinct payload
spans is exactly the alias check that refused the first attempt. What those
lanes are *of* remains unestablished; see below.

| | |
|---|---|
| source | 4,665,081,856 bytes, `f1300699ab445ad0…`, serial `SLUS-20919`, retail boot ELF |
| source after the run | **unchanged**, re-hashed |
| output | 4,665,081,856 bytes, `c3f61cd55f3f8a9c…` — same size, never committed |
| chunk span | 1,306,576 bytes = `0x20` wrapper + 1,306,544 stored |
| decoded scene | 1,917,856 bytes = 686,416 system + 1,231,440 video |
| lanes edited | 5, of 52 / 51 / 49 / 49 / 49 vertices |
| decoded bytes changed | **1,000**, in 250 one-vertex runs — 4 bytes each, because only `y` moved |
| image bytes changed | 1,282,669, every one inside the single declared window |
| `nfl2k5_ps2_stadium_position_verify` | **pass** — `w` preserved, vertex counts and DMA/VIF structure unchanged, decoded result matches the recipe exactly |
| `ps2_iso9660_verify` | **PASS** — 79 entries compared, 3,591,340,024 unchanged bytes compared, 0 slack, extents unmoved |
| wall clock | 17 minutes for the patch; both verifiers together in about a minute |

**The fit was as tight as the sampling said it would be.** The retail stream
consumes 1,306,541 of its 1,306,544 stored bytes — **3 spare**, the minimum of
the twelve sampled scenes. A 250-vertex edit has no chance in three bytes, so
greedy refused and the optimal parse carried it: 1,296,233 bytes, 10,311 spare.
`fill_stream` then put 10,303 of those back as literals and left 8 bytes of
padding, so the body still fills `stored_size`. The `+0x14` scratch word needed
162 bytes against the retail value of 192, so it never had to move, and the
`0x20` wrapper came out byte-identical. This is the load-bearing case, not a
lucky one: had the writer only had the retail parse, it would have refused.

**Where the image actually differs.** The first changed byte is 41 bytes into
the span — the 32-byte wrapper and the 9-byte VC-LZ stream header are
identical — and the last changed byte is the span's last. Everything between is
a re-encoded token stream, which is why 1,000 changed *decoded* bytes cost
1,282,669 changed *image* bytes. That ratio is the honest price of
recompression, and it is why the ISO-level verifier cannot be the thing that
proves the edit was bounded: it sees a megabyte of legitimately changed bytes
inside a declared range. The geometry verifier's decoded-side comparison —
1,000 bytes, 250 runs, every one inside a declared lane, every `w` intact — is
what carries that proof.

**One estimate in this document was pessimistic.** The fill step was projected
at roughly 2,600 expansions recovering about four bytes each. It took **1,444**,
recovering 7.14 bytes each. The shape of the estimate was right and its
magnitude was too gloomy; `fill_stream` still dominates the 17 minutes.

## What is and is not proved

**Proved, offline:**

* the PS2 shape/batch/DMA/VIF layout, on the retail disc, with the
  bounding-sphere check as independent corroboration;
* a same-count position edit round-trips through decode, edit, recompress into
  the fixed span, ISO9660 fixed-allocation write, and independent verification;
* every byte the patched image changes lies inside the owning chunk's fixed
  span; the `0x20` wrapper is byte-identical; the decoded buffers differ only
  in the x/y/z of the declared lanes, with every `w` preserved;
* the refusals fire: changed vertex count, inexact binary32, unauthorised
  target, mismatched catalogue pin, edits spanning two scenes, aliased lanes,
  and a recompression that does not fit — the last leaving no output image.

**Not proved, and not claimed anywhere in the outputs:**

* that any of this is *visible* in game. Nothing has been booted. Every
  `runtime_visibility_proved` and `hardware_visibility_proved` flag is `false`.
* **semantic ownership.** `sideline_home_south` is a name in the file, not a
  demonstrated correspondence to a thing a player sees. Which lane is which
  piece of stadium is unestablished.
* what the `V4_16` header block in each batch means. It is preserved bit-exact,
  which is sufficient for a position-only writer and insufficient for anything
  that wants to change counts.
* the meaning of batch field `+0x04`, and of VIF command `0x3F`.
* that other stadium scenes behave like this one. The catalogue was generated
  for a single scene; the tool will scan all 477 stadium-named SCNEs but that
  has not been run to completion.

## What the row may claim, and what remains

**`offline-writer-proved` is the ceiling, and this branch does not claim even
that** — no registry row is written or edited by this work. The trial above is
the evidence such a claim would rest on, and it is evidence about *bytes and
allocations only*: a scene decoded, five declared lanes moved, the result
recompressed into a fixed span, spliced into a new image, and re-derived by two
independent verifiers.

**Nothing has been on a screen.** No emulator and no console has run this
image. Every `runtime_visibility_proved` and `hardware_visibility_proved` flag
in the catalogue, the patch report, the verifier report and the trial record is
`false`, and no wording anywhere in the outputs says otherwise. A claim about
what a player sees is not merely unproved here — it has not been attempted.

Before the row could carry `offline-writer-proved` honestly:

1. **Catalogue more than one scene.** Run the tool across all 477 stadium
   scenes and check the refusal profile holds. Cheap; not yet done. One scene
   catalogued and one scene trialled is a sample of one.
2. **Semantic ownership for at least a handful of targets**, so a user can be
   offered "raise the upper deck" rather than "move lane
   `nfl2k5ps2/stadium/e1556/c2/s98/b0/l0`". `sideline_home_south` — the shape
   the trial moved — is a name read out of the file, not a demonstrated
   correspondence to a thing anybody has seen.
3. **A decision on the headroom reality.** With 0-16 spare bytes per scene, the
   optimal-parse encoder is not a nicety, it is load-bearing — the trial proved
   that concretely, refusing under greedy at 3 spare bytes and fitting only
   under the optimal parse. Its output is *not* the retail parse. That is a
   different stream shape reaching the console's decoder than any retail disc
   ever contained. It decodes correctly offline, twice, by two independent
   decoders; nobody has watched the console decode one.

Item 3 is the one worth arguing about before shipping, and it is a good reason
to keep this behind text and playbooks in the Phase 2 order — both of which are
byte-size-identical across the two discs and need no recompression at all.

Beyond the offline ceiling, and not a prerequisite for it:

4. **An in-game witness on the rig.** Boot the trial ISO in PCSX2 and look at
   the stadium. That is a *runtime* claim and a different class of evidence
   from anything here. Until it exists the classification cannot honestly
   exceed what the Xbox equivalent claims, and the Xbox one still reads
   `runtime.status: not-tested` after far more work.

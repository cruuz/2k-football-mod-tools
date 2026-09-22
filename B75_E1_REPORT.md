# Job b75-e1: four shoe textures in one shared span, "missed the 54,480-byte span by 272 bytes"

Branch `job/b75-e1` off the beta 75 stack commit `853e88de0`. Reproduced on the retail disc,
then one bounded change in the equipment writer. Nothing here is a witnessed in-game result;
Noah witnesses that.

## The report

Coach Edwards, DM 2026-09-21, beta 74 then 74.1, Windows:

> "Couldn't make the disc. Could not make the disc copy. While compiling project edits: Cannot
> build tset:3702:8:0:shoes01, tset:3702:8:1:shoes01_mud, tset:3702:8:2:shoes04,
> tset:3702:8:3:shoes04_mud / uniform set 11H0 / tset:3702:8:2:shoes04: needs refit: Equipment
> art needs refit: it cannot fit and missed the 54,480-byte span by 276 bytes (54,756 bytes
> required at the smallest measured encoding). ... Build tried every Refit equipment choice and
> none fits beside the other edits in this span (... missed the 54,480-byte span by 272 bytes
> (54,752 bytes required ...)). Revert this item or import simpler art."

## The span, from the retail disc

`tset:3702:8` is uniform set 11H0's shoe TSET: outer entry 3702, chunk 8.

| field | bytes |
| --- | --- |
| complete span (wrapper + stored body) | 54,512 |
| stored body (`stored_size`, the fit budget) | 54,480 |
| retail VC-LZ stream actually consumed | 54,471 |
| retail slack inside the span | 9 |
| wrapper +0x14 overlap scratch | 16 |
| retail stream's exact minimum overlap scratch | 5 |
| system bytes / video bytes | 640 / 93,568 |
| references | 6 (shoes01, shoes01_mud, shoes04, shoes04_mud, shoes09, shoes09_mud) |
| shared index chain (256x256, 6 mips) at pixel offset 0 | 87,360 |
| per-reference palette | 1,024 |

Two facts decide this job. First, all six retail references point at the SAME chain at pixel
offset 0 and own only a palette each, so a shoe and its mud twin are already one index image
with two palettes on the retail disc. Second, the retail stream is packed to within 9 bytes of
its span, so any appended byte has to pay for itself.

## What his import actually asks for

Importing one shoe stages its `_mud` twin as well (`equipment_staging.staging_targets`), and
`shoes01`/`shoes04` are global lookup rows, so each import is staged into every sampled
package: 804 edits across 402 packages, four edits per shoe span. Two shoe imports therefore
fill FOUR references of one 54,480-byte span with ONE artwork, which is exactly the four asset
IDs in his message.

## The cause

`mod_editor/core/nfl2k5_uniform_equipment_writer.py:1375-1387` (at `853e88de0`), the allocation
loop in `_compile_group`: every own-texture reference was given its own 128-byte aligned
append, whatever it contained.

```python
for reference in sorted(independent):
    ...
    start = (video_end + 127) & ~127
    updated_textures[reference] = replace(texture, pixel_offset=start)
    video_end = start + sum(...)
```

Four references carrying identical artwork therefore appended the identical chain four times.
The four copies also sit further apart than the VC-LZ distance window (1,023 bytes at 10
offset bits, 4,095 at 12), so the encoder cannot match a copy against the one before it: each
copy is paid for in full. That is the per-stream floor the brief suspected, and it is the
allocation, not the scratch rule: the measured minimum overlap scratch never exceeded 7 of the
16 bytes the wrapper grants in any measurement below.

## The arithmetic, before and after (retail 11H0 span, budget 54,480)

Four own-texture edits, plain art (solid white, and solid white with one dark sole band). The
"before" column is the same code path with the sharing key forced to one key per reference.

| art | image size | appended bytes before / after | required before | required after |
| --- | --- | --- | --- | --- |
| white | 256 x 256 | 349,696 / 87,424 | 61,578 (proved lower bound, over by 7,098) | 56,691 (over by 2,211) |
| white | 128 x 128 | 87,552 / 21,888 | 56,709 (over by 2,229) | **54,466 fits** (14 pad, min scratch 0) |
| white | 64 x 64 | 22,016 / 5,504 | 54,476 fits (4 spare) | **54,464 fits** (16 pad, min scratch 4) |
| white + sole | 256 x 256 | 349,696 / 87,424 | 61,578 (lower bound, over by 7,098) | 56,837 (over by 2,357) |
| white + sole | 128 x 128 | 87,552 / 21,888 | 56,951 (over by 2,471) | **54,474 fits** (6 pad, min scratch 0) |
| white + sole | 64 x 64 | 22,016 / 5,504 | 54,471 fits (9 spare) | **54,465 fits** (15 pad, min scratch 7) |

Per stream: one aligned copy of the chain is 87,424 bytes at full size, 21,888 at half, 5,504
at quarter. Before the fix the span paid that four times; now it pays once, and every
reference's descriptor points at the one copy. Palettes stay per reference, untouched by this.

## Build's own ladder, on the retail span, before and after

`auto_refit_group` with the four edits at full size, plain art, no clock:

* before: refused after the whole ladder, 31 s, with his wording:
  "Equipment / uniform set 11H0 / tset:3702:8:2:shoes04: needs refit: ... Build tried every
  Refit equipment choice and none fits beside the other edits in this span (Refit could not
  find a fitting colour count or size. ... missed the 54,480-byte span by 15 bytes (54,495
  bytes required at the smallest measured encoding) ...). Revert this item or import simpler
  art." His art missed the same rung by 272 and 276 bytes; mine by 15. Same span, same four
  items, same mechanism.
* after: builds in 14 s, all four refit to 128 x 128 at 2 colours, 54,474 of 54,480 bytes.

The 15-byte miss above is worth naming: it happened while only three of the four had been
refit, because the old ladder refits one item at a time and measures it against the others'
unrefitted full-size art. All four at 64 x 64 measured 54,471 and would have fit.

## The fix

1. `_appended_chain_key` and `_write_appended_chain`
   (`mod_editor/core/nfl2k5_uniform_equipment_writer.py:1342-1372`): the key is exactly what
   the appended bytes depend on (each level's width, height and RGBA digest, or a preserved
   retail chain's own bytes and geometry). The quantizer is a pure function of the levels and
   the colour limit, and one candidate uses one limit for every reference, so equal keys mean
   equal indices at every rung of the ladder.
2. The allocation loop (`:1413-1431`) gives one append per key instead of one per reference,
   and `_write_appended_chain` writes those bytes once, refusing closed if two references
   sharing one offset ever compiled different bytes. This is the retail layout: six retail
   references share the chain at offset 0, so a shoe and its mud twin sharing one appended
   chain is what the disc already does, one offset further along.
3. `refit_items` (`:2194`) and the batching in `auto_refit_group` (`:2285-2300`): own-texture
   items of one span carrying one artwork are refit to ONE choice together. Refitting them one
   at a time measured each against the others' full-size art and landed on 64 x 64 (or on
   nothing); together they land on 128 x 128. `refit_item` is now a one-item call into it, so
   Refit equipment in the Studio is byte-for-byte unchanged.

The retail-loader scratch rule is untouched: `_rebuild_grown_video` still fills the stream into
the window and still refuses anything with `padding > scratch` or
`minimum_vc_lz_overlap_scratch > scratch`. Every fit above keeps the retail scratch word 16 and
the loader guards (`loader_in_place_end_guard`, `loader_in_place_alias_guard`) true.

`mod_editor/core/mod_build.py` and `nfl2k5_throw_tuning.py` were NOT touched, so the cave
manifest does not need regeneration. `packaging/repin.py --apply` moved one pin (the unified
visual provider's digest for the writer) and that is in the commit.

## Does his whole import build now?

The 402 packages behind his two imports hold 66 distinct chunk-8 spans. All 66 were run through
`auto_refit_group` with the same four plain-art edits: 66 built, 0 refused, every one refit to
128 x 128 at 4 colours, 795 s total. Before the fix the 11H0 span refused; the sweep says the
other 65 spans are not hiding a second wall behind it.

## Tests

New, offline, on the synthetic fixture (`tests/mod_editor/test_nfl2k5_equipment_texture_chain.py`):

* `Fixture` now takes `count` and `width`, and `tight_four_stream_fixture` packs a 64x64
  four-reference shoe span the way a retail span is packed (stream + 768 bytes, chain larger
  than the distance window).
* `test_four_streams_carrying_one_artwork_share_one_appended_chain`: four identical own-texture
  edits share one appended chain (one pixel offset, `added_video_bytes` equal to one aligned
  chain), every reference still decodes its own artwork through its own descriptor, and with
  the sharing key forced to one key per reference the same group misses the 1,280-byte span by
  273 bytes (1,553 required). It fails on the pre-fix writer with that exact refusal.

Changed:

* `test_b721_equipment_build_refit.py::test_retail_coach_shoe_and_its_mud_twin_share_one_chain_and_fit`:
  the retail 06H0 shoe plus its mud twin now fit inside the 0.2 s quick check with the Python
  fallback (one shared chain) instead of reporting "fit pending" and fitting only at Build.
  The pending path keeps its synthetic coverage in the same file.
* `test_b70_t1_build_speed.py::test_palette_invariant_floor_stops_all_remaining_rungs`: gives
  its three references three DIFFERENT artworks, so the group really does append three chains,
  which is what the capacity floor is about.
* `test_b74_coach_edwards_gate.py`: new step 4 runs Build's fit and refit over the real 11H0
  span for the four references his import fills, and asserts one shared pixel offset, four
  refits, `stored_size` 54,480, and the loader guards with the retail scratch word unchanged.
  Staging it through the Studio would stage 402 packages, which no release gate can build, so
  the case runs on the real retail span through the real compile path.

Suites run with `python3 -m pytest -q -p no:cacheprovider` (`QT_QPA_PLATFORM=offscreen`):

| suite | result |
| --- | --- |
| test_nfl2k5_equipment_texture_chain, test_b721_equipment_build_refit, test_b70_t1_build_speed, test_b72_equipment_speed, test_b74_vc_lz_fill_lands_in_window, test_b74_equipment_import_defers_to_build | 67 passed, 182 subtests, 67 s |
| test_b69_j1_fit, test_b70_t2_equipment, test_b71_t4_equipment_project, test_b71_t5_project_open, test_nfl2k5_equipment_import, test_nfl2k5_equipment_import_wiring, test_nfl2k5_equipment_scope_wiring, test_nfl2k5_equipment_consumers, test_nfl2k5_equipment_retail_roundtrip, test_nfl2k5_equipment_texture_native, test_2k5_uniform_equipment_export, test_b74_modern_color_refit_cache | 104 passed, 1 skipped, 29 subtests |
| test_b68_a1_audit, test_b70_t2_reporting, test_b70_t2_wiring, test_studio_session, test_nfl2k5_shoe_relief, test_b74_equipment_enums_match_xbe, test_b74_build_receipt_readback, test_b74_speed_gate, test_b75_elbow_options, test_b75_project_arrowhead_source, test_b71_a6_composition, test_b70_a3_integration | 85 passed, 95 subtests |
| test_provider_integrity, test_providers, test_caller_windows_pins (after `packaging/repin.py --apply`) | 60 passed, 13 subtests |

Retail gate, `tools/coach_edwards_gate.sh`, one run at the end: **passed in 251 s** (index 29 s,
11H0 span 13 s, disc build 94 s), 6 GB disc written beside `.scratch` and deleted, no stage left
behind. Its own line for the new case:

```
tset:3702:8:0:shoes01 fitted at 128 x 128, 2 colours; tset:3702:8:1:shoes01_mud fitted at
128 x 128, 2 colours; tset:3702:8:2:shoes04 fitted at 128 x 128, 2 colours;
tset:3702:8:3:shoes04_mud fitted at 128 x 128, 2 colours
```

## What the user sees now

Plain art at full size still does not fit this span (56,691 bytes required against 54,480, with
one shared chain), and it cannot: the retail stream already fills the span to within 9 bytes.
Build no longer refuses it. It refits the four items together, names each one in the receipt
("Build refitted equipment 11H0 / shoes01: fitted at 128 x 128 ..."), and leaves the project's
original art alone. The image is half size rather than quarter size, and nothing about the
retail loader's scratch allowance changed.

## Commit

One commit on `job/b75-e1`, seven files (six changed plus this report), on top of
`853e88de0`, not pushed. A commit cannot carry
its own hash; read it from `git rev-parse job/b75-e1`. `.scratch/` holds the probe scripts and
the 66-span sweep and is not committed.

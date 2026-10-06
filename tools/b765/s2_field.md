These tools author home-field overlays and repair extracted v0.4 bundles. The
reviewed set is ATL9, DEN9, MIA3, PIT9, HOU9, DET9, CLE9, TB9 and WAS9: 75
resources. Other home resources, yard numbers, stadium branding/geometry,
crowds, uniforms and Anniversary/scenario fields retain their original bytes.

The complete reviewed Studio input is the local evidence directory
`/path/to/art_final_s2_was_clean`. Select that art
root for the normal Modern venues/Mercedes-Benz pack build. Native textures
and larger masters are hash-pinned in the ordinary venue manifests. External
art and research remain local evidence; this repository ships their authors,
writer/build steps, frozen repair pins and tests. Do not use the older directory
named `art_final_s2`, or the rejected Washington full-fill packing experiment.


The optional offline Detroit/Washington contour authors need an isolated authoring environment and Inkscape. Install `packaging/requirements-field-authoring.txt` in a separate virtual environment; it pins NumPy 1.26.4, Pillow 11.3.0, SciPy 1.11.4 and OpenCV 4.11.0.86. Studio builds consume the reviewed PNGs and do not require OpenCV, SciPy or Inkscape. This compatible environment reproduces Detroit masters and Washington original native masks/palette classification. Washington contour rendering and final antialias pixels differ from the frozen authoring masters in this compatible environment. Review regenerated Washington paint before replacing those masters.

To recreate the art, run these authors successively with a separate output root
at every step. Every author preserves all unselected source files and emits a
source-scope receipt. Source hashes are enforced; source references, colours
and estimated footprints are in the final root's receipts.

| Step | Tool | Inputs after `--art-root INPUT --out OUTPUT` |
| --- | --- | --- |
| ATL | `s2_author_field.py` | `--wordmark` supplied 2048x429 ATLANTA/FALCONS export |
| DEN/MIA/PIT | `s2_midfield.py prepare-art` | Uses `--source INPUT --output OUTPUT` instead |
| HOU | `s2_author_hou.py` | `--marks` reviewed PNG directory; `--designer-primary` reviewed H photograph |
| DET | `s2_author_det.py` | `--footer` official Detroit footer JPEG; `--lions-svg` exact supplied SVG |
| CLE | `s2_author_cle.py` | `--wordmark-svg` supplied two-line SVG |
| WAS | `s2_author_was.py` | `--wordmark-svg`, `--w-svg`, `--retail-left`, `--retail-right` |
| TB | `s2_author_tb.py` | `--wordmark-svg`, `--flag-svg` |

All paths above are relative to `tools/b765/`. Washington's retail PNG inputs
are its original 256x128 left/right helmet tiles, dumped from the read-only
retail field. Native-size input, supplied paths and reviewed vector traces
replace substitute fonts. The authors compensate for each venue's actual
physical UV mapping and reduce premultiplied masters once to 256x128 panels.
Atlanta uses an 8x master; HOU/DET/CLE/WAS/TB use 4x masters. The normal Studio
colour/weather pipeline quantizes each texture with its own full 256-entry
palette shared across its mip chain. A reduced palette/detail fallback refuses
for the selected repair payloads.

Repair the extracted reviewed bundles, keeping input and output separate:

```bash
python3 tools/b765/s2_repair.py --input /path/to/native_before \
  --output /path/to/native_after --art-root /path/to/art_final_s2_reviewed \
  --retail /path/to/supported/retail.xiso.iso \
  --include-midfield --include-endzones --include-existing-fields
```

The default repairs ATL9 only. `--include-midfield` adds DEN9/MIA3/PIT9;
`--include-endzones` adds HOU9/DET9/CLE9; `--include-existing-fields` adds TB9/WAS9.
The command compiles the selected payloads through the Studio field/colour/
surface steps, checks frozen source and P8 hashes and emits a combined receipt.
The helper scripts provide separate repair/decoder-proof commands. `pin` is a
development operation; integration must consume the committed frozen pins.

| Team | Source opt-in / native ownership |
| --- | --- |
| ATL | Three shared end P8 allocations; eight x/z floats in four private midfield vertices. `native_from_master` and `mercedes_midfield_scale=1.6`; original centre texture/UVs unchanged. |
| DEN/MIA | `add_missing_midfield=true` appends a 256x256 six-mip P8 texture/material/draw. MIA uses its existing afternoon/night placement; only daytime needs repair. Every original record/pixel/palette is preserved. |
| PIT | Same append, after colour/surfaces. Losslessly compresses full `detail_normal`, borrowing 26208 stored bytes inside the field-owned prefix. |
| HOU | `split_shared_endzones=true` appends three end textures and redirects only south material links. Existing geometry remains exact; field size/scratch remain fixed. 4096 unused video bytes protect palette-tail refits. |
| DET/CLE | `split_shared_endzones=true`, `field_prefix_loan=true`: full six independent ends. Losslessly compress full normal, borrowing 20592/28992 stored bytes. |
| TB | Six existing end allocations plus eight private x/z floats. `endzone_turf_from_field=true` uses cleaned same-variant main-field turf without changing the donor. `midfield_scale_xz=[1.49,1.88]`. |
| WAS | Three existing shared ends with `endzone_turf_from_field=true`: clean same-variant main-field turf removes the old donor paint islands while glyph/helmet masters remain exact. A 1680-byte lossless full-normal loan enlarges the stored field allocation; decoded sizes, 16-byte scratch, full normal pixels/mips/palette, stored layer and original suffix offsets/bytes remain exact. Trailing slack keeps the native final DWORD read inside that allocation. |

ATL/TB scales, end-word footprints and north/south assignments are explicitly
estimated from dated photos; they require Noah's moving-camera review. The
native repair changes no draw centre unless the reviewed private-vertex scale
is explicitly selected. Opt-ins are venue-gated, strictly typed and part of
their digest; absent options keep the old writer and digest behaviour.

For PIT/DET/CLE/WAS, ownership is the contiguous prefix ending at the original
`detail_normal` end, not just the field scene. The `detail_layer` stored span is
copied byte for byte at its new position; the normal's full decoded pixels,
palette and mips remain exact. All following Fldd/stadium/city/camera bytes and
offsets remain exact, and total bundle size remains fixed. DET/CLE's source
prepass preserves full detail, restores the ordinary colour pass's original
material links/palette inputs, then applies the final surface pass once. This
prevents unrelated snow palettes and detail-normal textures from changing.
WAS selects its loan during the surface stage after ordinary colour inputs and
the complete ordinary normal have been produced. Its stored field and normal
lengths change by the exact opposite 1680-byte amounts; the original suffix
still begins at the same offset. The rejected full-fill and 1472/1536-byte
trials are not shipping inputs.

Frozen manifests are `s2_repair_manifest.json`, `s2_midfield_pins.json`,
`s2_endzone_pins.json`, `s2_det_endzone_pins.json`, `s2_cle_endzone_pins.json`
and `s2_existing_field_pins.json`. They pin owned compressed spans rather than
whole bundles, allowing s1 to change an independent stadium suffix. Unknown
owned inputs/source pixels/compiled payloads refuse. Outputs are deterministic
and idempotent; existing different output files refuse.

Integration writes only each receipt's owned span into the existing outer
entry. The complete local `disc_file_scope_75.json` lists outer IDs, pack/file/
ISO offsets, sizes and before/after hashes. Only disc files `vc_53450030/8` and
`vc_53450030/9` are touched. These pack files may be shared by other jobs: do
not replace whole bundles or packs. Check the owned before hash immediately
before each splice; use the original scope boundary for loaned prefixes.
The repair itself never opens an ISO for writing.

`s2_native_decoder.prove_chunk` runs the recognized retail XBE decoder offline
under Unicorn, comparing exact output/EAX and native allocation read/write
guards. This supplements Python readback; it is not a gameplay claim. Proofs
cover all nine variants of PIT/HOU/DET/CLE/TB/WAS, including both field and normal
chunks on loan routes. Never weaken the scratch guard to accept a repair.

a1 may reuse `install_overrides`, `mv.resample`, P8 payload compilation and
`outside_digest` for its explicitly owned scenario root, with its own hash and
ownership pins. The home-team CLI intentionally rejects scenario resources.
For read-only mip dumps, actual draw bounds and the all32 before/after sheet,
see [s2_audit.md](s2_audit.md).

Run unittest in a separate process per file:

```bash
python3 tests/mod_editor/test_b765_s2_audit.py
python3 tests/mod_editor/test_b765_s2_midfield.py
python3 tests/mod_editor/test_b765_s2_field_prefix_source.py
python3 tests/mod_editor/test_nfl2k5_modern_venues_2026.py
S2_NATIVE_EVIDENCE=/path/to/s2/evidence python3 tests/mod_editor/test_b765_s2_field.py
S2_NATIVE_EVIDENCE=/path/to/s2/evidence python3 tests/mod_editor/test_b765_s2_endzones.py
S2_NATIVE_EVIDENCE=/path/to/s2/evidence python3 tests/mod_editor/test_b765_s2_existing_fields.py
```

Native tests need the retained `native_before`, ATL `native_after_v3`/
`art_refined`, team-final native folders and compiled source payload folders in
the evidence root. They check exact output, idempotence, foreign-input refusal,
scope, independent stadium edits and source/native pixel agreement. Provider
integrity, packaging, cave reservations and the ordinary build/surface suites
also cover the writer integration. Local previews omit lighting/detail shaders;
private emulator screenshots are review evidence. Noah is the gameplay witness.

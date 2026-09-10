# Importing APFe PS3 texture bundles

The importer reads APFe exports and prepares the Xbox 360 studio's existing
Team Logo and Field Art edits. It transfers decoded pixels, never PS3 archive
offsets, GTF containers, or PS3 compression. The core API and receipt CLI are
available. This beta-64 writer extension needs the Field Art label/preview
handoff in `WIRING.md` before the protected GUI is integrated.

## Export and arrange the files

In APFe, export each selected TXTR subfile with its DDS, GTF and `manifest.json`.
Keep each `selected_subfile_…` directory intact and put the exports under the
team's folder. Export **both** semantic layers. A typical layout is:

```text
NFL Logos/
  Atlanta Falcons/
    selected_subfile_753_0_…/
      000_logo_l1.dds
      000_logo_l1.gtf
      manifest.json
    selected_subfile_753_1_…/
      001_logo_l0.dds
      001_logo_l0.gtf
      manifest.json
    End Zone/
      selected_subfile_948_0_…/
        000_endzone_l0.dds
        000_endzone_l0.gtf
        manifest.json
      selected_subfile_948_1_…/
        001_endzone_l1.dds
        001_endzone_l1.gtf
        manifest.json
```

Choose the ZIP, the enclosing folder, `NFL Logos`, or an individual named team
folder. No ZIP extraction is needed. PNG/PDN sources, stripe variants and other
texture families are listed as ignored inputs. The known Cincinnati, Detroit,
Philadelphia, San Diego and San Francisco folder misspellings are accepted;
receipts retain the original folder spelling and the historical NFL identity.

DDS is authoritative when present. GTF is decoded only when its matching DDS
is absent. A malformed DDS is an error, not permission to substitute its GTF:
the supplied collection contains companions with different pixels. Keep the
desired edits in the DDS files.

## What maps

| Imported family | Required size | Destination and behavior |
| --- | --- | --- |
| `logo_l0` + `logo_l1` | 512 × 512, RGBA | A catalog crest slot, with the existing linked logo-cache build. Both layers and their mip levels are rebuilt. |
| `endzone_l0` + `endzone_l1` | 2048 × 512, RGBA | A retail-pinned Field Art pair: DXT1 (18) or grayscale DXT5A (59). Changed endzones regenerate all eight declared mip levels; exact no-ops retain the original entry. |

The layer **name** determines its role. `000_logo_l1` is the detail layer even
though its numeric index is zero. Crests contain six region masks across the
two layers; the game supplies the palette colors. Identical decoded pairs are
rejected. A missing or mismatched sibling is also rejected. Those pairs appear
in the rejection receipt while other valid pairs remain available. An invalid
manifest, unsafe input path, or wrong image dimensions stops the import.

All 120 manifest rows in the supplied NFL collection match the Xbox archive's
outer entry hash and exactly one semantic TXTR name. This does **not** make the
PS3 numeric entry index portable: hash `0x7ba6e2b0`, shown as PS3 entry 753 in an
export, resolves to Xbox entry 756. A hash identifies the exported library
slot; it does not prove that the NFL folder name identifies the Xbox team
wearing that slot. Default team crests come from the studio's existing team
table. Endzone labels come from `endzone_team_labels()`; an unidentified
endzone keeps its numeric slot label.

Choose another Xbox destination to assign the artwork to a different team.
When a manifest is absent or its hash has no unique compatible match, an
explicit destination is required. Batch rows use one source team and family
per destination; two teams cannot overwrite the same slot. Logo and endzone
destinations are independent because their team ownership is not completely
mapped. There are 24 default APF team crests and a larger library of 118 logo
slots, not 28 independently owned built-in NFL teams.

Alternate subfolders and differing source hashes remain separate variants.
Dallas's `EndZone/Orginal` and `EndZone` cannot both target one slot. Detroit's
two crest packages also stay separate; specify `pair_id` when a team/family
has more than one variant. No timestamp automatically wins.

## Inspect and prepare a batch

From the repository root:

```bash
python3 -m mod_editor.apf_studio.ps3_texture_bundle "NFL Logos Textures.zip" --receipt bundle.json
```

This creates a new JSON receipt containing pair IDs, source manifest rows,
dimensions, source paths and SHA-256 hashes of decoded RGBA pixels. Receipts
contain no image payload. Existing receipt files are never overwritten by the
CLI. To create a destination plan, provide the selected Xbox `0A` and a mapping:

```json
[
  {"team": "Atlanta Falcons", "kind": "logo", "destination": "Americans"},
  {"team": "Atlanta Falcons", "kind": "endzone", "destination": "endzone:6"}
]
```

These are an explicit example assignment, **not** a claim that endzone 6
belongs to the Americans. Use the live list or contact sheets to choose yours.

```bash
python3 -m mod_editor.apf_studio.ps3_texture_bundle "NFL Logos Textures.zip" \
  --index-0a "/path/to/Xbox/game/0A" --mapping mapping.json --receipt plan.json
```

For Python integration, `destination_slots(index_0a)` returns live destinations;
`team_mapping(bundle, slots, rows)` validates a batch; `build_plan(...)` returns
the destination asset ID, semantic layer, RGBA image, source path and receipt
for each texture. `stage_plan(session, plan)` passes paired PNGs into
`replace_helmet_crest_design(..., detail_png=...)` or `replace_field_art(...)`.
It verifies the reviewed pixels and current destinations, reparses temporary
PNGs, and undoes earlier operations if any operation fails. Repeating the
same import replaces the same logical edits rather than multiplying them.
Shared full-shell projects must be reverted before importing these retail
side-decal mask pairs.

Staging is not allocation-fit proof. Use the normal complete-project Build so
the crest package and linked logo cache are both written and independently
verified. Endzones first try the requested pixels with regenerated mips and
safe greedy H7A, then the reviewed optimal H7A helper if the entry overflows.
The optimal helper is available only on supported Linux x86_64 installations;
Windows/macOS continue with safe greedy and the same quality steps.

If the entry still does not fit, the endzone writer snaps each RGB channel to
0 or 255 (threshold 128), **preserving alpha**, and tries compression again.
It then tries 2× and 4× nearest downsampling followed by nearest upscaling to
the unchanged 2048×512 descriptor. Those steps reduce effective top-level
detail to 1024×256 or 512×128. All eight mip levels are regenerated from the
effective image with nearest sampling, which retains region values. Mip
allocation, inactive padding, descriptors, sibling parts and the IFF footer
are preserved. Any remaining overflow refuses output and names the byte overage.

The build's `writer_receipt.quality` lists every attempt, the selected palette
and resolution reduction, and allocation sizes. `targets` reports requested
versus effective/decoded pixel errors and all mip hashes/errors. The reparse
gate independently checks these against the actual rebuilt resource. Every
emitted H7A match is checked for `length <= distance`; decoder round-trip
alone is insufficient for console safety. Other Field Art families retain
their existing base-only limitation. The imported art's in-game appearance
is **UNWITNESSED**.

## Beta 64 endzone coverage and format proof

The supplied collection still has **55 valid pairs**. There are now **117
writer-supported complete endzone destinations**, up from 78. The 39 newly
supported format-59 TXTRs are all `endzone_l1`; they include the destinations
for Chicago, Cleveland, Green Bay, Houston, Indianapolis, Los Angeles Raiders,
New York Giants and New York Jets. The prepared plan grows from **46 to 54
pairs (108 textures)**: 27 crests and 27 endzones. Dallas's `EndZone/Orginal`
remains an alternative to `EndZone` in the same slot, so selecting both would
be a destination conflict. Preparation does not assert that all 54 pairs fit
their independent build allocations; existing crest allocation limits remain.

Format 59 is Xenos **DXT5A**, the scalar/alpha half of BC3: two 8-bit endpoints
and sixteen 3-bit indices in an 8-byte block. These endzone descriptors use
8-in-16 byte order and fetch swizzle `[0,0,0,5]`, displaying the scalar as
`(R,R,R,255)`. They require **grayscale RGB with opaque alpha**; colored or
transparent replacements fail instead of silently converting to luma. This
is different from the digital font's `[5,5,5,0]` white-plus-alpha swizzle.

The 2048×512 base occupies `0x80000` bytes; levels 1–7 occupy `0x30000` bytes
and end at 16×4. Levels 5–7 share the packed tile beginning at `0xAE000`.
The 8-byte-block Xenos addressing is shared with BC1; payload codec and
swizzle remain distinct. All 39 retail entry/base pins and mip transports
are tested. Retail entry 78/l1 decodes and re-encodes unchanged byte-exactly,
with zero decoded channel error. Fixtures contain synthetic bytes only.

Washington now fits at full resolution after RGB endpoint simplification,
with **17,235 bytes spare**. Chicago fits after the same palette step plus
4× top-level reduction, with **2,635 bytes spare**. Chicago l0 mean absolute
RGBA error is 2.8624 (maximum 255); Washington l0 is 0.8846 (maximum 255),
and l1 is 0.2927 (maximum 119). These are measured losses, not lossless imports.

Receipts: [retail format-59 roundtrip](../../reports/ps3_import/format59_retail_roundtrip.json),
[54-pair plan](../../reports/ps3_import/available_staging_plan.json),
[Washington allocation diagnosis](../../reports/ps3_import/washington_allocation_diagnosis.json),
[Chicago rebuilt endzone](../../reports/ps3_import/chicago_endzone_writer.json),
[Washington rebuilt endzone](../../reports/ps3_import/washington_endzone_writer.json).

Washington's old 13,524-byte overflow is reproduced: the same 1,441,792-byte
VRAM block becomes a 150,740-byte active IFF in a 137,216-byte allocation
after safe optimal compression. Both source and imported alpha are uniformly
255, and the old writer preserved the mip bytes exactly. It is a compression
cost from the changed BC1 patterns and their spatial repetition, not a larger
mip chain or alpha noise. Its l0 distinct stored BC1 blocks increase from 650
to 4,733; l1 decreases from 6,337 to 2,146. See the build receipt for the
successful regenerated-mip encoding and any required quality reduction.

## Roster and full-package research

`python3 -m mod_editor.apf_studio.ps3_roster_probe --help` describes a read-only
USERDATA/raw/STFS comparison. The 1993 PS3 roster and Xbox fixtures share a
2,715,908-byte payload, 40 root counts, 332-byte player stride, 384-byte team
stride and a byte-identical 69 × 12-byte playbook-label table at `0x1D31DC`.
Their appearance graphs and counted player memberships parse successfully.
However, 1,344 PS3 nickname pointers resolve to odd addresses; the first is
the player-0 field at `0x268` targeting `0x207A9B`. The existing player text
parser refuses that source. No roster converter is provided.

A future converter should first classify these strings and their ownership,
prove the PS3 pointer/string grammar, then relocate text into valid allocations
while updating **all** references and preserving the player/team graph. It
must account for serialized runtime pointers in root fields 15–18, compare
the user-book region from `0x26D030`, preserve other save state, and pass the
existing independent save verifiers. A container rename cannot establish
those facts. Xbox STFS signing remains an external owner-controlled handoff;
Xenia acceptance needs an actual in-game witness. Franchise USERDATA and the
editor-only season/stat exports are not roster payload substitutes.

`python3 -m mod_editor.apf_studio.ps3_texture_probe --help` describes the full
texture census. It reads the STORED nested game ZIP and walks the compressed
volume members in physical order, without extracting the game. Entry and
decoded-block allocations are bounded at 256 MiB; texture dimensions are
bounded separately. Optional NumPy accelerates the read-only Xbox decoder,
with the existing decoder as fallback. NumPy is not needed by the importer.
The report lists equal, different and uncompared textures separately and
names existing writer ownership where proved.

The PS3 VC TXTR descriptor embeds `CellGcmTexture` at `0x58`. Split resources
store the pixels in their VRAM part. Inline resources use a one-based
self-relative file pointer at `0xA4`; the observed value `0x5D` resolves to
`0x100`. The probe validates the intervening padding instead of assuming the
GPU offset is a file pointer. Non-IFF signatures are read before allocating
entries, so large non-texture resources do not breach the memory bound.

The census compares **base-level decoded RGBA**, matched by outer hash and
inner hash/name. Differences can reflect mod edits, platform artwork, channel
conventions or codec rounding. Without a base PS3 disc they are candidates,
not a proved list of everything the modder changed. Cubemaps/volumes and
unimplemented formats remain explicitly uncompared.

## GTF decoding boundary

The actual APFe files have a 48-byte (`0x30`) header, with pixels beginning at
the offset declared at `0x10`; padded `0x80` headers are also supported. The
big-endian version/size/count words are at `0/4/8`, texture ID/data offset/data
size at `0x0C/0x10/0x14`, and the 24-byte GCM descriptor starts at `0x18`.
Its format, mip count, dimension, cube flag, remap, dimensions, depth,
location, pitch and GPU offset are parsed. The GPU offset is not used as a
file offset. Raw swizzled textures are untwiddled; supported BC1/BC2/BC3 and
raw 8/16/32-bit formats honor channel remapping. Unsupported shapes fail.
The descriptor layout and enum constants are documented by
[PSL1GHT](https://bucanero.github.io/PSL1GHT/struct__gcmTexture.html) and
[RPCS3](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/RSX/gcm_enums.h).

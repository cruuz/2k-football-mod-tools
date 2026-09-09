# Importing APFe PS3 texture bundles

The importer reads APFe exports and prepares the Xbox 360 studio's existing
Team Logo and Field Art edits. It transfers decoded pixels, never PS3 archive
offsets, GTF containers, or PS3 compression. The core API and receipt CLI are
available. The page buttons require the integration described in `WIRING.md`;
they have deliberately not been added to the protected GUI in this branch.

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
| `endzone_l0` + `endzone_l1` | 2048 × 512, RGBA | A pair owned by the existing Field Art writer. Unsupported format-59 slots remain unavailable. The current writer preserves old mip tails. |

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
verified. The existing no-overlap H7A encoders are reused. Some edits can fail
their fixed allocation; that failure must remain a refusal. Field Art's stale
mip limitation remains visible in every plan and the dialog. No new writer
for helmets, uniforms, numbers, banners, or unsupported endzones is introduced.
The imported art's in-game appearance is **UNWITNESSED**.

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

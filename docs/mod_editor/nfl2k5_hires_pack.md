# Hi-res texture families

**EXPERIMENTAL / UNWITNESSED.** The compiler can build 2x artwork for 2,524
pinned retail targets. No preset enables it. The existing Build switch works
with these folders; the additional family checkboxes and budget display are
specified in `WIRING.md` for integration.

**Whole-game memory fit has not been proved.** The budget command refuses a
folder that exceeds the modeled arena ceiling. A smaller result says
`unproved`. Its arithmetic residual is not free memory or safe headroom.
The only experimental target is `xemu-64`; `xemu-128` refuses.

| Family | Targets | Artwork |
| --- | ---: | --- |
| Current Standard/A helmets | 64 | All 32 team codes, both H0/A0 kits, 512 x 512 |
| Uniform numbers | 1,920 | Ten jersey, ten helmet and ten arm digits per current kit; 128 x 128 or 64 x 64 |
| Jerseys | 64 | Paired clean/muddy artwork, each 1024 x 512 |
| Created-team midfield logos | 126 | 42 logo codes in dry/rain/snow, 512 x 512 |
| Stock embedded midfield logos | 348 | Every embedded `center_logo` in the 477 field scenes; 339 at 512 x 512 and nine at 1024 x 512 |
| Scorebug | 2 | Frame atlas 128 x 128 and ESPN strip 256 x 128 |

Use the catalog for the exact names and resource identities:

```sh
python3 -m mod_editor.core.nfl2k5_hires_pack catalog > hires-catalog.json
python3 -m mod_editor.core.nfl2k5_hires_pack catalog --family helmets
```

Put selected files in a `Hi-res` folder. Filenames, including case, assign
targets. Examples: `helmet_01h0.png`, `number_01h0_jersey_7.png`,
`jersey_01h0.png`, `jersey_01h0.mud.png`, `field_ct50r.png`,
`field_o3148.png`, `scorebug_espn.png`. The legacy pilot names remain
`helmet.png` for 00H0, `field_logo.png` for CT33 dry and `scorebug.png` for
the frame. These replace the corresponding longer names in the catalog.

A `.2ktexmaster` can replace any PNG, including either jersey input. Its
native canvas must match the selected asset. The validated 2x preview is
used; a 4x authoring preview is reduced to 2x. Do not supply both extensions
for one input. Jerseys require both clean and `.mud` files and compile them
into one shared index chain with two palettes. Quantization measures both
images together; reduce colors if the pair exceeds 8,192 unique color pairs
across its mips. Every receipt reports the resulting color error.

Unknown PNG/master filenames, incomplete selected jersey pairs, changed
source bytes, mixed retail/authored sets and foreign recipes refuse. Missing
known files are unselected. `--family` can be repeated to select families
within a folder. A malformed *unselected* known family is ignored, but
unknown filenames still refuse to catch misspellings.

```sh
python3 -m mod_editor.core.nfl2k5_hires_pack budget --folder project/Hi-res
python3 -m mod_editor.core.nfl2k5_hires_pack apply retail.iso \
  --folder project/Hi-res --output hires.iso > hires-receipt.json
python3 -m mod_editor.core.nfl2k5_hires_pack status hires.iso \
  --folder project/Hi-res
python3 -m mod_editor.core.nfl2k5_hires_pack apply hires.iso \
  --folder project/Hi-res --scale 1 --output native-art.iso
```

The source, destination and artwork must be separate files. An existing
output requires `--overwrite`. Every archive entry, selected resource and
unrelated named file is independently checked before atomic publication.
The source and previous destination survive exceptions and cancellation.
Keep the receipt and the exact artwork folder for replay or native output.
Change artwork or expand a partially installed selection from the original
retail image. A no-folder inspection checks only the three legacy pilot
probes; it is not a full family scan.

The native mip count is retained. Keep original atlas arrangements, seams
and orientation. A stock scene keeps its original video bytes and appends
an aligned authored logo, changing only that logo descriptor. Consequently
it retains the unused native raster too. Native-size output from this path
still includes an appended native-size authored raster. It reduces the 2x
allocation but does not restore retail memory use or retail artwork. An
original-disc build with the option off is the exact retail fallback.

This pass runs last, after fixed-span texture, stadium and scorebug writers.
Edits to the same selected resource conflict and require a combined authored
input. Embedded field scenes are pinned in full except the owned descriptor
and appended raster, so independently edited scenes refuse. Unrelated
executable edits can compose outside the pinned consumer/allocator ranges.
The existing reference/runtime scorebug changes its binding table and
conflicts with the Hi-res scorebug family, including an ESPN-only selection.
The other five Hi-res families can pass that executable combination.
Archive growth and physical disc growth are reported separately; the shared
writer can retain unused physical space when shrinking.

Files are bounded to 32 MiB each, master expansion to 64 MiB and master
source images to 16 megapixels. Rasters are decoded one at a time. Selected
resource inputs and outputs each have a 256 MiB host bound; each outer is
at most 32 MiB and all rewritten containers at most 768 MiB. These are
compiler process bounds, separate from the guest memory model.

Historical/alternate kits, helmet C, nameplate source atlases, end zones,
goal pads, playoff/sideline/stadium logo materials and arbitrary embedded
textures are outside this catalog. The `center_logo` census does not certify
those other named materials as midfield art. Nameplates need a separate
pixel-coordinate and generated-surface change. There is no 4x texture output,
new executable owner, heap enlargement or 128 MiB support.

Use the exact witness checklist and evidence limits in
`ASTRA_HIRES_MORE_REPORT.md`. Compare native and 2x artwork at xemu rendering
scales 1x, 2x and 4x, complete full games and subsequent loads, and record heap
free space and allocation failures. A boot alone is insufficient.

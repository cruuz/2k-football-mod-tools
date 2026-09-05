# Hi-res pack pilot

**EXPERIMENTAL / UNWITNESSED.** This opt-in build pass installs selected 2x
textures in a copy of an NFL 2K5 USA disc. The normal build keeps native sizes.
No preset enables the pilot. The Build controls are an integration handoff in
`WIRING.md`; the command below works independently now.

Place your artwork in a folder named `Hi-res` beside your project. Select that
folder explicitly when building. Missing filenames mean unselected assets.
Use these exact names, including case:

| File | Authored size | Game target |
| --- | --- | --- |
| `scorebug.png` | 128 x 128 | Retail scorebug frame atlas, `score_buga`, outer 346 / chunk 53 |
| `field_logo.png` | 512 x 512 | Created-team logo code 33, dry weather, `CT33D.IFF` / `center_logo`, outer 384 / chunk 0 |
| `helmet.png` | 512 x 512 | Uniform `00H0.IFF`, `helmet00`, outer 3613 / chunk 11; Standard/A live helmet |

These are three specific assets. The field target is not the stock NFL teams'
embedded midfield art, and the helmet target is not every team's helmet.
Keep the original atlas arrangement and helmet seams when drawing new art.
PNG transparency is retained through the native P8 palette, which can contain
at most 256 colors. The receipt reports any quantization loss. The scorebug
keeps one mip level; the field logo and helmet keep six, ending at 16 x 16 at
2x. Adding mips or changing the atlas layout is outside this pilot.

Instead of a PNG, you can place `scorebug.2ktexmaster`,
`field_logo.2ktexmaster` or `helmet.2ktexmaster` in the folder. Use only one
extension for each target. The bundle must come from NFL 2K5 Studio and have
that target's native canvas size. Its validated master preview, including any
native painting overlay, supplies the artwork. A 4x authoring preview is
reduced once to 2x. The source master and its transform remain unchanged.
The pilot accepts files up to 32 MiB, master archives up to 64 MiB expanded,
and master source images up to 16 megapixels. The filename is an explicit
assignment; receipts also retain the bundle's original asset identity.

From the repository or integrated release root:

```sh
python3 -m mod_editor.core.nfl2k5_hires_pack inspect_image "retail.iso"
python3 -m mod_editor.core.nfl2k5_hires_pack apply "retail.iso" \
  --folder "project/Hi-res" --output "pilot-2x.iso" > "pilot-2x-receipt.json"
python3 -m mod_editor.core.nfl2k5_hires_pack status "pilot-2x.iso" \
  --folder "project/Hi-res"
```

The output must differ from the source, artwork and master files. An existing
destination requires `--overwrite`. The whole build is published only after
every archive entry, selected decoded image and unrelated named file passes
read-back checks. Failures preserve the source and previous destination.
Keep the JSON receipt with your artwork. Without the matching folder,
inspection labels nonretail textures `authored-unverified`.

To return to native sizes while retaining your art:

```sh
python3 -m mod_editor.core.nfl2k5_hires_pack apply "pilot-2x.iso" \
  --folder "project/Hi-res" --scale 1 --output "pilot-native.iso" \
  > "pilot-native-receipt.json"
```

Native output is rendered from the retained authoring raster, then encoded
again. It restores native dimensions and mip counts, not the original retail
art. Rebuild from your original disc with the option off to restore retail
bytes. Shrinking reclaims logical pack space; the inherited writer retains
unused physical image space. Reapplying identical artwork and scale produces
identical bytes without another append. A selected set mixing retail,
authored-native and authored-2x textures refuses. Keep selection and artwork
unchanged for replay/downscale; use a retail source to change artwork or
expand a partially installed selection.

Run this pass after other resource writers. Existing native texture writers
and the reference/runtime scorebug edit the same frame and conflict with
`scorebug.png`; they are not automatically merged. Unselected resources and
unrelated executable patches travel with the copy, and audited consumer code
must retain its pinned bytes.

2x means twice the width and height. The three video allocations total
718,336 bytes, versus 181,888 natively. This is not a measured scene-memory
budget. The only selectable target is `xemu-64`, explicitly experimental;
128 MiB compatibility is unavailable until guest allocation and high-address
GPU handling are proved. No memory or executable patch is installed.

xemu's internal rendering scale is a separate setting. Noah should compare
the native and 2x builds at 1x, 2x and 4x rendering, using the witness list in
`ASTRA_HIRES_PACK_REPORT.md`. Booting alone does not establish correct atlas
sampling, mip behavior, memory headroom or full-game stability.

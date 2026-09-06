# PS2 uniform art — the disc's own textures in, a PCSX2 pack out

> RC86 work package C. Lane `uniforms.art` in `mod_editor/games/nfl2k5_ps2/uniform_art.py`,
> CLI `tools/nfl2k5_ps2_uniform_art.py`, registry row
> `nfl2k5ps2.uniforms.replacement_pack_export`, classification **`extract-only`**.
> Offline-proved, **not witnessed in-game**: see [What is not claimed](#what-is-not-claimed).

## What the lane does

M1 shipped an exporter that writes a PCSX2 replacement pack from an **Xbox**
project: you edit on the Xbox disc, and the shipped map
(`mod_editor/data/nfl2k5-xbox-map.v1.json`) says which PS2 texture your edit
replaces. That leaves out the person who owns the PlayStation 2 disc and wants
to change what is on *it* — the art they are editing lived on a disc the
toolchain never opened.

This lane opens it:

1. **Catalogue.** Open the user's own `SLUS-20919` image read-only, find the
   634 uniform packages by their archive name id, walk each package's TSET and
   TXTR children, and join every texture to team, kit, part, size, pixel
   format, mip count and its PCSX2 replacement filename.
2. **Decode.** TEX0 → unswizzle → CLUT expand → an 8-bit RGBA PNG of level 0.
3. **Edit.** One value per target, kind `png`.
4. **Pack.** Write `textures/SLUS-20919/replacements/<name>.png` plus the
   receipt, through the same export service the Xbox lane uses.
5. **Verify.** Run `tools/nfl2k5_ps2_replacement_pack_verify.py`, which imports
   nothing from the writer.

The disc is opened read-only and is never written. PCSX2 overlays the pack at
draw time; nothing goes back into the image. That is why the row is
`extract-only` and why the *only* output is a folder of PNGs.

## The decode facts this relies on

All of them are `docs/product/PS2_M1_PLAN.md` §4 WP1's, and all of the maths is
`tools/nfl2k5_ps2_texture_map.py`'s — the tool that computed the shipped map's
hashes. The lane adds the inverse permutations *beside* the forward ones in
that same file (`unswizzle8_blocks`, `unswizzle4_blocks`, `level_indices`), so
a decode and an identity cannot disagree about what the bytes are; the map
tool's own self-test proves each one inverts.

| Fact | Where it comes from |
|---|---|
| `TEX0` packs `TBP0/TBW/PSM/TW/TH/TCC/CBP/CPSM/CSM/CSA`; only `PSMT8` (0x13) and `PSMT4` (0x14) are indexed | M1 plan §4 WP1 step 1 |
| The replacement filename is `%llx-%llx-%08x.png`, both 64-bit fields **unpadded**, and `bits = PSM \| TW<<6 \| TH<<10 \| TCC<<14` with **bit 14 set** | M1 plan §4 WP1 steps 1 and 4 |
| `PSMT8` level 0 is 16×16 GS blocks via `columnTable8`; `PSMT4` is 32×16 via `columnTable4`, low nibble first | M1 plan §4 WP1 step 2 |
| A level smaller than one whole block in either direction is *not* blocked; the bytes already are the index rows | `level_bytes` / `level_indices` |
| Three on-disc arrangements occur: `lin` (linear rows), `vram` (the region already is the GS VRAM image), `c32` (a one-shot PSMCT32 upload, one 8 KB page wide) | map tool module docstring |
| A mip chain is **not** always `c32` — 482 pack identities are proved only by the linear path | M1 plan §4 WP1 step 2 |
| The CLUT is 1,024 bytes (`PSMT8`) or 64 (`PSMT4`), taken from the descriptor's `+0x28` override when present, else `CBP·256`; the linear layout applies the CSM1 bits-3↔4 swap, the c32 layout the PSMCT32 VRAM-read permutation, `PSMT4` raw | M1 plan §4 WP1 step 3 |
| PS2 CLUT alpha runs **0..0x80 with 0x80 opaque**; a PNG's runs 0..0xFF, so the decoder scales `min(255, a·255//128)` | GS alpha convention; restated in the tests |

### Which layout a texture actually uses

Nothing on the disc says. The hasher tries every candidate; this lane resolves
it in two steps.

1. **The shipped map decides, where it can.** Every candidate `(level-0, CLUT)`
   route gives a candidate filename. When one of them is in the map, that is the
   route PCSX2's own hash agreed with, and the map's `xbox_asset_id` is the id a
   pack may be attributed to.
2. **A documented rule decides the rest**: a mip chain takes `c32` (then `c32w`,
   `lin`, `vram`), a single level takes `lin` (then `vram`, `c32`), and the CLUT
   is taken in a fixed preference order. **Measured against the 841 textures the
   map proves on the retail disc, the rule picks the same route for 839
   (99.8 %)**; the two it misses are `sleeve00_mud` CLUT choices, where the map
   took the descriptor override and the rule took the c32 copy.

That is good enough to *look at* a texture and not good enough to name a file a
pack claims — so it decides the preview, never the pack.

## What is refused, and why

| Refused | Why |
|---|---|
| A replacement that is not a PNG with a valid IHDR | PCSX2 loads PNGs; the sentence names the size the texture wanted |
| A PNG whose size is neither the texture's size nor a whole-number multiple of it on **both** axes (a 3:2 stretch, 515×256, …) | PCSX2 scales a replacement but cannot change its shape; the sentence names the size it wanted |
| Packing a texture whose identity the shipped map does not prove | The name would be the rule's guess, and a pack that claims a filename nothing proved is a pack that silently does nothing. Export it as a PNG instead |
| A destination that already exists, or the source image as a destination | Every build writes a new file; nothing is overwritten and the disc is never a target |
| A disc image with no uniform packages | It is not an ESPN NFL 2K5 (`SLUS-20919`) resource layout |
| A recipe naming a target the catalogue does not carry, or the same target twice | One texture takes one PNG |

## The pack, and how it is proved

`build` writes two things: the **pack folder**, and an **edits document** at the
build's `destination` naming every texture the user replaced, the asset id the
pack attributes it to, and the digest of the PNG they supplied. The pack folder
is `<destination>.pack/` — the contract's harness treats a build's destination
as a file it can hash, and a replacement pack is a folder, so the receipt is the
destination and the folder sits beside it. The CLI's `pack --destination` names
the same pair; `export_pack()` names the folder directly.

### The verifier's sixth rule now has two shapes

The independent verifier's hard rule is *no receipt entry names a target its
author did not edit* — an unedited texture in a pack is retail pixels leaving
the disc. It needs a third input, and until now that input was an Xbox
`.2k5mod` project. A pack authored from the disc has no project.

So the receipt records `origin`, and the verifier asks for the input that origin
calls for:

| `origin` | Third input | Flag |
|---|---|---|
| `xbox-project` (the default when a receipt has no `origin`, which is every M1 pack) | the `.2k5mod` the pack was exported from | `--project` |
| `disc-native-art` | the edits document written beside the pack | `--edits` |

Neither substitutes for the other: handing a disc-native pack a project, or an
Xbox pack an edits document, downgrades the verdict to `INCOMPLETE` and says
which flag it wanted. **Nothing that was refused before is accepted now** — the
existing rejections are unchanged and the self-test still proves all of them,
plus four new ones (an unknown origin, a receipt entry the edits document omits,
an empty edits list, an edits document relabelled as an Xbox one).

## Team, kit and part names

A texture's package code (`09H0` = package 09, home, variant 0) comes off the
disc exactly: the outer archive keys each entry by the CRC-32 of its logical
name, and the whole `NNH/A V` namespace is enumerable. The *name* of the team
does not come off the disc, so `mod_editor/games/nfl2k5_ps2/uniform_kits.v1.json`
carries selector → abbreviation, team, side and kit for **562 of the 634
packages**, extracted mechanically from the committed
`reports/gameplay_tuning/nfl2k5-xbox-map.unresolved.v1.json` (which the release
does not ship) and pinned to that file's digest; a test rebuilds it and compares.

The 72 packages the table does not name are still catalogued, with their exact
package code, and the catalogue summary counts them rather than guessing a name.

The part comes from the texture's own name on the disc — `jersey00` → torso,
`pants00` → pants, `sleeve00`/`longsleeve01` → sleeve, `helmet00` → helmet,
`jersey_numbers`/`helmet_numbers`/`arm_numbers` → numbers, `names` → nameplate,
`logo` → logo, `socks00` → socks, `glove*`/`shoes*`/`elbowpad*`/`wristband*` →
equipment, `chiclet`/`flipchip`/`splayer` → presentation. A `_mud` suffix is
recorded as a variant, not a different part.

## The numbers, on the owner's retail disc

Measured 2026-09-05 against `ESPN NFL 2K5 (USA)`, content sha256 `f1300699…`,
read-only. Decoded PNGs were written to a scratchpad, looked at, and deleted;
nothing retail is in the repository.

| | |
|---|---|
| Uniform packages found | **634** |
| Textures catalogued | **38,674** (61 per package; every one `PSMT8`) |
| Named teams | **49** (the 32 NFL clubs plus AFC/NFC/NFL, the alumni and Crib squads) |
| Named kits | **560** |
| Packages with no team name in the kit table | **74** (4,514 textures) |
| Textures with **no** computable identity | **0** |
| Textures the shipped map proves, i.e. packable | **841**, across **248** packages and **32** teams |
| Packable by part | torso 300 · sleeve 280 · pants 186 · socks 43 · equipment 28 · helmet 4 |
| Whole-disc catalogue | ~65 s on 8 workers; one package ~1 s |
| Sizes seen | 128×128 (13,314) · 128×64 (12,046) · 256×128 (6,340) · 512×256 (2,536) · 64×64 (2,536) · 256×256 (1,268) · 1024×32 (634) |

Three textures were decoded and looked at as a sanity check: the Detroit Lions
home jersey (map-routed), the New York Jets helmet and the Chicago Bears logo
(both rule-routed). All three are the right art, right colours, right alpha —
the rule route is correct on real art too, which is what the 99.8 % agreement
figure predicts.

A real one-texture pack was written from the disc and both gates passed:
`nfl2k5_ps2_replacement_pack_verify.py --edits` returned `PASS` with all seven
checks true, and `nfl2k5_ps2_replacement_pack_audit.py` reported
`xbox_mapping_ready: true` with no blocking reasons. The pack and every decoded
PNG were deleted afterwards.

## What is **not** claimed

- **No write-back to the disc.** This lane never modifies the user's image. Art
  reaches the game only as a PCSX2 texture replacement, applied by the emulator.
  Writing art into the disc is a different lane and is not started.
- **`extract-only` by registry rule.** The registry binds `runtime-proved` to a
  writer with an edit surface; this is an exporter whose output the emulator
  applies. The same open question the M1 row already records applies here.
- **Unwitnessed.** No frame from this lane's output has been seen in an
  emulator. M1's own runtime witness (2026-09-05, PenguinScreen2 `8226182a`)
  covers packs of the *same shape under the same names*, so the route is not
  novel — but a uniform edited from the PS2 disc has not itself been rendered.
  That witness is the next thing this row needs.
- **Only 841 of 38,674 textures are packable today.** The rest can be exported
  as PNGs and not packed. Widening that means resolving more of the map's TSET
  fan-out, which is the M1 row's own `portme` item, not a decode problem.
- **Level 0 only.** Mip levels are not decoded or written. PCSX2 accepts a
  level-0 replacement and generates the rest.
- **No palette quantisation.** Packs are RGBA; `encode` normalises to 8-bit
  RGBA and does nothing else to the pixels.

## Running it

```
# every uniform texture on the disc, as a retail-free JSON
python tools/nfl2k5_ps2_uniform_art.py catalogue --iso DISC.iso --out catalogue.json

# one team's kit as PNGs (reads that team's packages only)
python tools/nfl2k5_ps2_uniform_art.py export --iso DISC.iso --team DET --out-dir art/

# a pack from an edits document: [{"target": "09H0:1:0:jersey00", "png_path": "mine.png"}]
python tools/nfl2k5_ps2_uniform_art.py pack --iso DISC.iso --edits edits.json \
    --destination mypack.json

# no disc: the synthetic route, end to end
python tools/nfl2k5_ps2_uniform_art.py --selftest
bash tools/validate_nfl2k5_ps2_uniform_art.sh
```

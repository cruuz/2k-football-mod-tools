# beta-35 — RC62 / alpha.67

**Date:** 2026-08-11

**2K5 Mod Studio:** `v1.0-RC62`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.67`

Two APF team-logo fixes, both from bug reports against Beta 34. Nothing in 2K5
changed this release.

## Fixed: the second, smaller logo in the corner of your crest

If you built a team crest and looked at a helmet from certain distances, you saw
your logo with a smaller copy of itself tucked into a corner. Look from further
away and you got the retail logo back, as though the mod had not applied at all.

Both were the same mistake, in how the writer addressed the crest's chain of
smaller copies (its mip levels).

The chain moved from one level to the next by multiplying the level's aligned
width and height. That is not how the Xbox 360's GPU lays them out. Every stored
level starts on a 4096-byte boundary, and — only at two bytes per texel, which
is exactly what a crest is — a 32x32 tile is scattered across 0xC00 bytes of
address space instead of packed into 0x800.

Both errors point the same way, so the shared tile holding the 16x16 and smaller
levels was addressed 0x800 bytes *inside* the 32x32 level. Regenerating the chain
wrote those small levels through the 32x32 one — that is the smaller logo in the
corner — and left the real tail untouched, so the smallest draws kept serving the
retail crest. How much of the 32x32 level is overwritten depends on the artwork:
427 of its 2048 bytes for the image the fix was first derived from, 325 for the
real team crest rebuilt to check it.

The corrected chain accounts for the retail-declared mip length of 0x2C000
exactly, with nothing left over. The old one reached 0x2B000 and explained the
missing page away as padding, which is the clue that was there the whole time.

**If you built a crest with Beta 32, 33 or 34, rebuild it from the same PNG.**
No re-authoring — just Build again.

**Only crests were affected.** The uniform, wordmark, pants, shoulder and helmet
writers all use block-compressed formats at 8 or 16 bytes per block, where both
corrections are no-ops. Their output is unchanged byte for byte, and there is now
a test that says so.

**Xbox 360 only.** This fix is Xenos texture addressing — the 360 GPU's tiling,
its packed-mip layout, its 4096-byte subresource alignment. APF 2K8 on PS3 does
not store its textures that way, and these tools do not read or write the PS3
build at all. If you mod a PS3 copy, nothing here changes it, and a crest that
still looks wrong there is not this bug coming back.

The layout also refuses outright to hand back a chain whose levels share bytes,
so this class of bug fails closed instead of reaching a crest.

## Team Logo can author both crest layers

A crest is not one picture. It is six region masks split across two textures:
`logo_l0` carries regions 0-2 and `logo_l1` carries regions 3-5, and 79 of the
game's 118 crest packages use both.

**Export both layers** could already take a crest apart. Putting one back needed
`tools/apf_logo_patch.py --png --png-l1` at a command line, which meant those 79
packages were effectively read-only inside the app.

**Logos & Team Art → Team Logo → Replace both layers…** now imports the two PNGs
together. Each is sized the way a single import is sized, and both are written
into the `uniform_logo_NN` package and the matching `uniform_logocache` slot by
the same proved writers, in one copied `0A`.

### A single image no longer gets copied into both layers

Dropping one image used to write that same mask to `logo_l0` *and* `logo_l1`,
which selects all six regions and draws your mark once per region in six
different flat colours. One image now goes to `logo_l0` and clears the detail
layer, so the mark is drawn exactly once.

That is what the panel's own export dialog already told you happened, and what a
full project Build already did. The copied-volume Build was the odd one out — so
the same staged image could give you two different crests depending on which
button you pressed.

`tools/apf_logocache_patch.py` gains the `--clear-l1` flag its Python API already
had, so the cache can be told the same thing as the package.

## What is proved, and what is not

The defect was reproduced here before this release shipped. A real team crest
was built twice from a retail disc, once with Beta 34's code and once with this
one, and every level of both was read back out and compared:

| level | size | built with Beta 34 | built with this release |
| --- | --- | --- | --- |
| 0-3 | 512² to 64² | exact | exact |
| 4 | 32² | 325 of 2048 bytes wrong | exact |
| 5-9 | 16² to 1² | byte-identical to retail | exact |

Decoded back to pictures, Beta 34's 32x32 level draws the mark with a second
offset copy of itself, and its 16x16 and smaller levels are the retail logo
pixel for pixel. That is both halves of the report, and they are gone here.

Those levels are not merely present — they are sampled. Xenia's texture fetch
constant for that crest reports `mip_min_level=0`, `mip_max_level=9` and a
`linear` mip filter, so the GPU blends through the whole chain and the levels
Beta 34 left retail were being drawn.

Also checked offline: every level's byte range against every other level's, the
derived chain against the retail-declared allocation exactly, the single-image
treatment clearing the detail layer at all ten levels and rebuilding its chain,
and the two-layer import end to end through to the arguments both writers get.

**Not done: a side-by-side photograph of a helmet in the emulator.** The game
was booted on both builds and reached live play, but the capture is driven by
timed button presses and the two runs did not land on the same screen, so there
is no honest frame-to-frame comparison to show. If you have a crest built with
an earlier beta, rebuilding it and looking at a helmet is still worth doing.

## Credits

Both bugs were reported by **davidhbui**, including the observation that the
artifact tracks zoom level — which is what pointed at the mip chain rather than
the base texture.

## Downloads

| file | bytes | SHA-256 |
| --- | --- | --- |
| `2K5-Mod-Studio-v1.0-RC62-20260811.tar.gz` | 11,032,048 | `96f62e24871f314cdeaed07ccfdb1c8565b3d5c6e78bb6cc9b0e869fba5f94c5` |
| `2K5-Mod-Studio-1.0.0rc62-Setup.exe` | 56,674,441 | `ca3f1041f3cd7158b08e0470ce4d7beb1a80235ecd281c511f45a3e0e5a3cf19` |
| `apf2k8-mod-studio-0.1.0-alpha.67-20260811.tar.gz` | 1,742,447 | `52e8b35b946f854f80cbd68449b0c97d4d236204c8a4eb8cc596440e7c7f876f` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.67-Setup.exe` | 52,638,991 | `0f25f1a8f354938dc4ebe59f3a642d25feb8582f3e716ef8b68f71c1b100bb78` |

Windows installers are self-contained and reproducibly built, but not
code-signed; the installer explains the Windows warning before installation.

These archives are retail-free. They contain no game data of any kind.

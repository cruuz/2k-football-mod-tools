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
wrote those small levels through the 32x32 one, replacing 427 of its 2048 bytes
— that is the smaller logo in the corner — and left the real tail untouched, so
the smallest draws kept serving the retail crest.

The corrected chain accounts for the retail-declared mip length of 0x2C000
exactly, with nothing left over. The old one reached 0x2B000 and explained the
missing page away as padding, which is the clue that was there the whole time.

**If you built a crest with Beta 32, 33 or 34, rebuild it from the same PNG.**
No re-authoring — just Build again.

**Only crests were affected.** The uniform, wordmark, pants, shoulder and helmet
writers all use block-compressed formats at 8 or 16 bytes per block, where both
corrections are no-ops. Their output is unchanged byte for byte, and there is now
a test that says so.

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

## What is not proved

No in-game or emulator witness is claimed for either fix. Both are proved
offline:

- every regenerated level is read back out of the rebuilt tail and compared to
  the level it should be, and every level's byte range is checked against every
  other level's;
- the derived chain is checked against the retail-declared allocation exactly;
- the two-layer import is checked end to end through to the arguments both
  writers receive.

The reported artifact and its disappearance were observed by the reporter on
hardware, not reproduced here. If you have a crest built with an earlier beta,
rebuilding it and looking at a helmet is the confirmation this release wants.

## Credits

Both bugs were reported by **davidhbui**, including the observation that the
artifact tracks zoom level — which is what pointed at the mip chain rather than
the base texture.

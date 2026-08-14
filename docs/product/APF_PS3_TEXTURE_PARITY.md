# APF 2K8 — spec for PS3/Xbox 360 texture-writer parity

**For:** the APF 2K8 Mod Studio maintainer / agent
**Against:** `2k-football-mod-tools` @ Beta 43 (APF `0.1.0-alpha.75`)
**Baseline:** an independent PS3 (BLUS30049) toolchain that writes four families
Mod Studio currently cannot
**Date:** 2026-08-14

## 0. Summary

Four asset families are writable on PS3 and have no Xbox writer. **None of them
needs new format research or a new codec.** Every required encoder already
exists in the tree and is proved against another family. The work is re-targeting
proved machinery at more entries, plus the target-catalog and verification
scaffolding each family needs.

Ordered by cost-to-value:

| # | family | textures | new codec needed? | est. difficulty |
|---|---|---|---|---|
| 1 | `weave_*` | 12 | no — 8_8_8_8 lossless | **lowest** |
| 2 | `dirtmap_*` | 9 | no — BC3 | low |
| 3 | `number_*_color` / `_normal` | 480 | no — DXT1 + DXN | medium |
| 4 | per-team `endzone_l0/l1` | 235 | no — DXT1 | medium (already specced) |

---

## 1. Measured inventory

All figures read from a pristine retail `0A`.

### 1.1 `weave_*` — 12 parts, all in package 659

| property | value |
|---|---|
| dimensions | 64×64 |
| format | **6 (8_8_8_8)** — uncompressed |
| mip levels | 6 |
| parts per texture | 2 (descriptor + payload) |
| package slack | **44,916 bytes** |

Parts: `weave_jersey0`, `weave_pants0`, `weave_pad1`, `weave_leather1`,
`weave_leather2`, `weave_embroidery1`, `weave_embroidery2`, `weave_wristband1`,
`weave_skin_arm`, `weave_skin_head`, `weave_skin_weights_arm`,
`weave_skin_weights_head`.

### 1.2 `dirtmap_*` — 9 parts, also package 659

| part | dimensions | format | mips |
|---|---|---|---|
| `dirtmap_helmet` | 1024×1024 | 20 (DXT4_5) | 8 |
| `dirtmap_jersey0..3` | 512×512 | 20 (DXT4_5) | 7 |
| `dirtmap_pants0..3` | 512×256 | 20 (DXT4_5) | 6 |

### 1.3 `number_*` — 480 textures across 24 packages

| property | value |
|---|---|
| packages | 24 (2, 17, 62, 340, …) — one per team, same slot indexing as uniforms |
| per package | 10 digits × (`_color` + `_normal`) = 20 |
| dimensions | 512×512 |
| `_color` format | **18 (DXT1)** |
| `_normal` format | **49 (DXN)** |
| mip levels | 7 |
| package slack | ~2,859 bytes (package 2) |

### 1.4 Per-team `endzone_l0/l1` — 235 layers

2048×512, format 18 (DXT1). Covered in the earlier Field Art report; included
here for completeness. Outer 6 is already proved writable and is structurally
identical to the other 117 packages.

---

## 2. Every codec already exists

| need | existing implementation | proved against |
|---|---|---|
| 8_8_8_8 encode (lossless) | `apf_field_art_patch.py:688` | `divots` |
| DXT1 / BC1 encode | `apf_field_art_patch.py:589` | `endzone_l0/l1`, `pc_field_goal` |
| BC3 / DXT4_5 encode | uniform transports (`_encode_changed_blocks`) | `jersey_color`, `shoulder_color` |
| **DXN encode** | `apf_helmet_color_transport.encode_dxn:160` | `helmet_color` |
| DXN mip layout | `apf_xenos_dxn_mip_layout` | `helmet_color` |
| H7A repack, token-preserving | `apf_inner.encode_h7a_preserving_tokens` | 10+ writers |
| allocation overflow reporting | `archive_patch.allocation_overflow` | uniforms (Beta 39) |

The DXN row is the one that would otherwise have blocked this: number normal
maps are DXN, and Beta 36 only added DXN *decode* routing. The encoder shipped
with `helmet_color`, so number normals are reachable today.

---

## 3. Per-family requirements

### 3.1 `weave_*` and `dirtmap_*` (package 659)

Do these first. Three things make 659 the cheapest target on the disc:

- **One package.** All 21 textures live in it, so one writer covers both families.
- **44,916 bytes of slack** — roughly 17× a uniform slot. The allocation pressure
  that dominates `jersey_color` and `shoulder_color` is effectively absent, so
  neither a capacity model nor a palette ladder is needed.
- **Three proved writers already target 659** (`pc_field_goal`,
  `Field_Pass_text`, `Stride_number_field`), so the rebuild path, descriptor pad
  preservation and sibling byte-preservation are already exercised.

Requirements:

- Extend `apf_field_art_patch` (or a sibling) to accept these 21 inner parts.
- `weave_*` is uncompressed 8_8_8_8, so the write is lossless and the manifest
  should say so rather than reporting a perceptual metric.
- `dirtmap_*` uses the existing BC3 path with three distinct dimensions; derive
  the layout from the descriptor rather than a table. (Beta 43's sleeve defect —
  a slot contract typed in by hand and wrong by 7× — is the argument.)
- Preserve every other inner part of 659 byte-for-byte, as the existing three
  targets already do.

### 3.2 `number_*_color` / `number_*_normal`

Highest user value: jersey numbers are the most visible unported family.

Requirements:

- A target catalog keyed by team slot, mirroring
  `mod_editor/data/apf2k8_uniform_targets.v1.json` — 24 packages, 20 inner parts
  each. Slot indexing matches the uniform families, so a team's numbers can be
  resolved from the slot it already uses.
- `_color` routes through the DXT1 encoder; `_normal` through `encode_dxn`.
- **Capacity model required.** Package slack is ~2,859 bytes for all 20 textures
  combined, which is tighter per texture than a uniform slot. A staged set of ten
  digits could individually pass and collectively overflow, so the budget must be
  computed **per package, across all staged digits**, not per texture.
- The Beta 39 overflow message should name the digit and the package.
- Digits should be stageable individually; the PS3 workflow replaces subsets
  (one package took all ten, another took only 1, 4 and 7).

### 3.3 Per-team `endzone_l0/l1`

Unchanged from the earlier report: same DXT1 two-layer structure as the proved
outer-6 pair, 235 layers, largest browse-only family in the inventory. The
`apf2k8_endzone_labels.v1.json` map shipped in Beta 39 already solves the
identification half.

---

## 4. Common requirements

1. **No new formats.** If a family needs a codec not in §2, that is a signal the
   descriptor was misread — stop rather than guess.
2. **Derive contracts, don't type them.** Dimensions, mip counts and formats come
   from the descriptor at import time, cross-checked against the importer.
3. **Byte-bounded writes.** Only the targeted inner part changes; descriptor pad,
   packed mip tail and every sibling part stay byte-identical, verified by
   reparsing the rebuilt entry in RAM before it is written.
4. **Capacity before build.** Families in tight packages (`number_*`) need the
   same per-slot budget display uniforms got in Beta 39 — and see §6.
5. **Source volumes are never opened for writing.**

---

## 5. Non-goals

- No runtime claims. Whether a replaced dirtmap or weave is visible in play is
  unproved and should not be asserted.
- No new mask semantics. These families are conventional textures; `weave_*` and
  `dirtmap_*` are detail/wear maps, not region selectors.
- PS3 support is not requested. This is about Xbox reaching what PS3 already does.

---

## 6. Related defect worth folding in

`CAPACITY_FAMILIES = ("shoulder",)` in `uniform_targets.py`, so the Beta 39
capacity display covers shoulders only. `jersey_color` has the same
retail-complexity budget and no warning. Measured across the 24 jersey slots,
retail complexity ranges from **8 to 1,412** unique 4×4 blocks — a 175× spread,
the same shape as the shoulder distribution that motivated the original feature.

Only **2 of 24** slots hold detailed retail art in *both* families (slot 17:
jersey 1,160 / shoulder 1,619; slot 16: 1,033 / 799), which is not discoverable
from the UI today. Extending `CAPACITY_FAMILIES` to jersey — and ideally showing
a combined per-team verdict — is a small change against work already shipped.

---

## 7. Open question

Placing a team on a chosen slot requires the roster field that binds a team to
its uniform/number package. I have verified the roster stores nicknames and
colours directly and is a fixed-size file that cannot carry artwork, but I have
not located that binding. Without it, slot capacity is a constraint to work
around rather than a choice, for numbers as much as for uniforms.

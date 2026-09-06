# Witness-disc recipes — Madden NFL 09 (PlayStation 2)

The recipe files that built four rebuilt disc images on 2026-09-05, one per lane step,
kept here so a later run can reproduce the same edits and so a reader can see exactly what
was asked of each writer.

Every one of the module's eleven writers is `offline-writer-proved`
([`MADDEN09_PS2_MODULE.md`](../../../MADDEN09_PS2_MODULE.md) §7). **These images are the
boot that has never happened.** They were built from the owner's own retail and Deluxe
`SLUS-21770` images, opened read-only; the images themselves are not in this repository
and never will be.

**Retail-free.** A recipe here carries a target key, a synthetic value, and the local
filename of a synthetic artefact. It carries no member payload, no decoded pixel, and no
string read off a disc — with **one declared exception**, in `disc1-03-text.json`: each of
its 102 replacements begins with the sixteen-character story-category tag
`<This Week Game>`, which is how the story engine selects a headline. Dropping it would
make the replacement unselectable, so it is kept, and it is named here rather than passed
over. *That the tag is a selector and not drawn text is an inference, not a measurement.*

---

## The four images

| # | image | sha256 | built from | lanes exercised, in chain order |
|---|---|---|---|---|
| 1 | `madden09-witness-1-databases.iso` | `96d681b2ef80b2824f06ea98f33c082c7b137000d9213cf8007660547d7bd8e7` | retail | `players_rosters.team_databases` → `colors.team_identity` → `menus.text_members` |
| 2 | `madden09-witness-2-art.iso` | `5c22d8ea50284cece5d7afed744d6a91d6197a186fbfafd94be1fe9f5a27678d` | retail | `uniforms.disc_art_writer` → `rosters.face_textures` → `stadiums.textures` → `field_art.textures` → `presentation.ui_textures` |
| 3 | `madden09-witness-3-audio-playbooks-exe.iso` | `3453d4fcd2d638dff4182fb8a0b50857f61391994e6d5608b4c9c16cb9f9eae9` | retail | `audio.streams` → `playbooks.databases` → `gameplay.boot_elf_patches` (disc route) |
| 4 | `madden09-witness-4-deluxe.iso` | `dcbef6f28c2e5122e4f85ce50a97444ba2345527d5dc2fadf1431db0928e7242` | **Deluxe** | `menus.text_members` → `gameplay.boot_elf_patches` (disc route) |

Ten of the module's fourteen rows are exercised; each build's own verifier passed on every
step. Discs 3 and 4 rewrite the boot ELF, so their PCSX2 game CRCs move — `380143A1` and
`0845630B`, against the sources' `38014255` and `084562FF`. **No pnach may be stacked on
either.**

## The recipes

| file | lane | what it asks for |
|---|---|---|
| `disc1-01-roster.json` | `players_rosters.team_databases` | Bears (`DB_TEAMS.DAT` member 0) `PLAY` record 3 → first name `WITNESS`, last name `ROSTER`, jersey 77 |
| `disc1-02-identity.json` | `colors.team_identity` | Bears → `TSNA` `WIT`, primary colour `#00FF00` (written to both copies the lane agrees on) |
| `disc1-03-text.json` | `menus.text_members` | all 102 `<This Week Game>` headline slots of `STRYHDLN.DAT`, each replaced with the tag plus a witness word sized to that slot's own allocation |
| `disc2-01-uniforms.json` | `uniforms.disc_art_writer` | five `UNIFORMS.DAT` textures, one per member (7, 11, 13, 15, 17), each a hard 8-pixel stripe |
| `disc2-01-uniforms.REFUSED-multi-image.json` | — | **the refused variant**: nine textures, five of them different images of member 11. Kept because the refusal is the finding; see below |
| `disc2-02-faces.json` | `rosters.face_textures` | `PLYRFACE.DAT:274:0` → an 8-pixel checker |
| `disc2-03-stadiums.json` | `stadiums.textures` | `STADIUMS.DAT` 697, 764 and 821 → 8-pixel checkers |
| `disc2-04-fieldart.json` | `field_art.textures` | `FIELDART.DAT` 647 and 677 → 8-pixel checkers |
| `disc2-05-ui.json` | `presentation.ui_textures` | `UIS_TMLO.DAT` 1 and 31 → 8-pixel checkers |
| `disc3-01-audio.json` | `audio.streams` | `BGM.DAT:0:0` ← a synthetic 30 s 440 Hz tone gated at 1 Hz |
| `disc3-02-playbooks.json` | `playbooks.databases` | book `GAMEDATA.DAT#67`: one formation → `WITNESS FORM` (in `FORM` and `PBFM`), one set → `WITNESS SET` (in `PBST` and `SETL`) |
| `disc3-03-code-patch.json` | `gameplay.boot_elf_patches` | `playbook_editor_caps` with `plays_cap: 400`, `sets_cap: 130`, delivered on the **disc** route |
| `disc4-01-roster.json` | `players_rosters.team_databases` | Bears `PLAY` record 48 → `WITNESS` / `ROSTER` / 77. *Refused on Deluxe when disc 4 was built; it builds and verifies there now — see below* |
| `disc4-02-identity.json` | `colors.team_identity` | identical to `disc1-02-identity.json`. *Same story* |

`disc4-01-text` does not exist: disc 4 reused `disc1-03-text.json` unchanged, because the
Deluxe `STRYHDLN.DAT` holds the same 102 slots at the same offsets with the same
allocations. Disc 4 likewise reused `disc3-03-code-patch.json`.

## Two refusals, recorded rather than worked around — and both since closed

**1. Both database writers refused the Deluxe image**, with one sentence:

```
/DATA/DB_TEAMS.DAT is 2,559,112 bytes in this image's own directory and carries
2,585,280; a rewrite would have to grow the file, which this lane will not do.
```

The Deluxe rebuild's ISO9660 directory record understates that container by 26,168 bytes.
The refusal is container-level and `DB_TEAMS.DAT` is the only container either lane
writes, so **no** roster row and **no** team identity was writable on the Deluxe disc on
the day disc 4 was built. Reading was never affected: the Deluxe catalogue reads 355
databases, 4,108 tables and 12,550 editable rows in 35.1 s.

**Closed** (`MADDEN09_PS2_GAPS.md` §12). What lies past that record is only trailing
empty members' alignment padding — measured on all six of the image's recorded-short
containers, no member with bytes ends past the record, and the next file starts in the
very next sector — so the rewrite fits inside the record and the record never moves.
Re-run against the same two recipes, on the same image:

| recipe | result |
|---|---|
| `disc4-01-roster.json` | **PASS** · 3 values read back from the destination · 1 database re-parsed with 44 checksum slots all correct · 0 undeclared changed bytes |
| `disc4-02-identity.json` | **PASS** · 8 values read back · 2 databases re-parsed with 470 checksum slots all correct · 0 undeclared changed bytes |

Both images come out 1,846,476,800 bytes, the size of the source; no directory record
moved or was resized; `DB_TEAMS.DAT` keeps its recorded length and its `DATA` chunk's
declared size; its container directory is byte-identical; and the only bytes that differ
are inside the edited record. The counts are in
[`../deluxe-recorded-short-writers.json`](../deluxe-recorded-short-writers.json). The
two recipes are kept as what produced the old sentence **and** as what proves the fix.
The images themselves were deleted after the check, as every witness build is.

This changes §7 item 8 of the module document: four lanes now write into a Deluxe image.
What has still never happened is a **boot** — of either disc.

**2. The uniform verifier refuses two images of one member.**
`disc2-01-uniforms.REFUSED-multi-image.json` names nine textures, five of them images 0,
1, 2, 6 and 13 of `UNIFORMS.DAT` member 11. `plan` and `build` both accepted it — 9 of 9
textures at 100% exact pixels, max channel error 0 — and then `verify` failed:

```
LANE_VERIFY FAIL game=madden09_ps2 lane=uniforms.disc_art_writer — Verification failed:
image 1 of UNIFORMS.DAT member 11 changed and no edit named it.
```

`UniformArtLane._check_one_texture` requires every *other* image of the edited member to
decode unchanged, and it does not exempt the other images the same recipe named. So a
multi-image edit of one member can never verify. The recipe that shipped writes **one
image per member** instead. This is a verifier limitation, not a writer defect — the built
image was correct — and it is a small, specific fix somebody can make later.

## The synthetic artefacts

A recipe names a PNG or a WAV by its local path under the build's scratch directory
(`…/m09-witness-work/png2/…`, `…/wav/…`). Those files are **not** in this repository:
every PNG is painted from colours the texture's own CLUT already carries, so its pixels
are the disc's colours, and a WAV is small but pointless to keep. They are named by digest
so a rebuild can be checked against them, and the rule that made them is written down so
they can be made again:

* **Pattern:** an 8-pixel hard-edged stripe (uniforms) or checker (everything else),
  alternating two colours.
* **The two colours:** read the texture's **whole CLUT** through `mmap_art.read_palette`,
  scale each entry's alpha the way `mmap_art._scale_alpha` does (the PS2 stores 0..128 and
  both `decode_rgba` and `index_rgba` work in 0..255 — a PNG written in the raw space
  misses its own palette entry by the alpha channel alone), keep the entries whose alpha
  is at least three quarters of the most opaque one, and take the pair with the greatest
  sum of absolute RGB differences. Every pixel written is therefore an exact palette
  entry, which is why every art build reports **max channel error 0**.
* **The WAV:** 30 s, 22,050 Hz, stereo, 16-bit PCM; a 440 Hz sine at 0.55 amplitude gated
  0.5 s on / 0.5 s off with 10 ms raised-cosine edges.

| sha256 | file | bytes |
|---|---|---:|
| `c612462eeb89a3cb0578429146bf66e7b68ba2cc602f901a434db37fbe256122` | `png2/faces/PLYRFACE.DAT_274_0.png` | 480 |
| `5918234c85f28fe1832224e47b0f4d37eb0336790ed4db557ad59b2cf6843a57` | `png2/fieldart/FIELDART.DAT_647_0.png` | 475 |
| `628548632d1b4505f234ecbd867af72b31eea3cd33a80e52c106fb8badb41583` | `png2/fieldart/FIELDART.DAT_677_0.png` | 476 |
| `ad5d94d20b1f0b13870f2e6c23354a4b2d91a7fb3fe17d2096b52f986badcbfd` | `png2/stadiums/STADIUMS.DAT_697_0.png` | 479 |
| `ae20373e7bf9b3a527ce084a3d3d334b23b0c435de637f9a8727a9f1a8a85511` | `png2/stadiums/STADIUMS.DAT_764_0.png` | 480 |
| `fc87a594f8298494ba936b7b73629b526172088edb005a04c353ca8bde472305` | `png2/stadiums/STADIUMS.DAT_821_0.png` | 282 |
| `201d7d716d3cf8433282e0d0ea4c8f74536f56a6379aa372719cd8cac885fade` | `png2/ui/UIS_TMLO.DAT_1_0.png` | 265 |
| `bbf176c7bf2d75fe439406846d6f85d930bfa07a99ea01adfe50e8ed084beb44` | `png2/ui/UIS_TMLO.DAT_31_0.png` | 250 |
| `30169e428e813746a0aa0290c506536bef7006d3aae01f183615adc76c3d67a4` | `png2/uniforms/UNIFORMS.DAT_11_2.png` | 1,284 |
| `055cbc6c9a41bac28b7d11f6a30b5de95710439f769581a1fd8f7c512c7dd732` | `png2/uniforms/UNIFORMS.DAT_{7,13,15,17}_6.png` (one file, four names — those four members share a 16-entry CLUT) | 1,251 |
| `023553119baab7847f07975f707ecf2113621dccafc473a62585b92fa3716ebe` | `wav/witness-440hz-1hz-beep.wav` | 2,646,044 |

## Which screen each edit is meant to show on

From `pcsx2-texture-identities.json` in this directory's parent. **Note the frame labels:**
`20260905145305` is *Vikings in the coloured kit, Bears in white*, and `20260905152031` is
*Bears in the coloured kit, Vikings in white* — the reverse of how they are sometimes
quoted. `STADIUMS.DAT:697` and `FIELDART.DAT:647` (the art-pages trial's textures) come
from **152031**; `UIS_TMLO.DAT:1` comes from **145305**.

Which *team* a uniform texture belongs to is still not established: the capture has one
frame per matchup, so a texture drawn in a Bears-Vikings frame narrows to those two teams
and no further — 32 members are attributed identically to both. The owner's report of
which team's jersey changed is the new information.

## What this does not claim

Nothing here says the game loads any of it. Every verifier verdict quoted in the receipts
beside the images is about bytes. Until the owner boots these four discs and reports, every
row stays `offline-writer-proved`.

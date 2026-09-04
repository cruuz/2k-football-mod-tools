# NFL 2K5 ratings and the three style channels

What the 28 rating bytes in a player record are, which three of them are *style* selectors rather
than scalars, how the game reads each one, and what the studio's ★ Rosters page exposes. Everything
below is read out of the retail `default.xbe` and the retail `ROST` resource (2026-09-04 executable
study, `BETA59_RESEARCH_RATINGS_ROSTER_LIMITS_PLAYBOOKS`, sections 1.1–1.3, plus the template work
in `mod_editor/core/nfl2k5_roster_records.py`). Where something is a hypothesis it says so.

Field credit for the record map: Flying Finn (Glen Leskinen) and Bad_AL, re-verified byte for byte
against the retail disc.

## 1. The 28 rating bytes (PROVED)

A player record is 0x54 bytes; the ratings are the run of single bytes at `+0x36..+0x51`. There
are **28** of them, not 27: the Player Card prints 27 labels, and one more (Scramble) has its own
row in the game's roster editor but never appears on the card.

How the map was fixed: the 27 label stubs sit at `0x000E5CC0` (stride `0x10`), the per-position
label list at `.rdata 0x004F5258` is paired element-wise with the value-getter list at
`.rdata 0x004F55B8`, and each getter was disassembled for the displacement it reads. The result was
cross-checked against per-position means over the 1,944 live retail records.

| offset | rating | getter | retail (n = 1,944 live records) |
|---|---|---|---|
| +0x36 | Speed | 0x0E4E40 | 74 distinct values, 22..99 |
| +0x37 | Agility | 0x0E4E90 | 69 distinct, 31..99 |
| +0x38 | Arm Strength | 0x0E5060 | 79 distinct, 3..99 |
| +0x39 | Stamina | 0x0E5180 | 87 distinct, 6..99 |
| +0x3A | Kick Power | 0x0E50C0 | K mean 77, P 73, everyone else 10-20 |
| +0x3B | Durability | 0x0E5240 | 65 distinct, 10..99 |
| +0x3C | Strength | 0x0E4FA0 | 78 distinct, 9..99 |
| +0x3D | Jumping | 0x0E4EE0 | 70 distinct, 10..99 |
| +0x3E | Coverage | 0x0E55A0 | 96 distinct, 1..97 |
| +0x3F | Run Route | 0x0E5360 | 99 distinct, 1..99 |
| +0x40 | Tackle | 0x0E5480 | 93 distinct, 5..99 |
| +0x41 | Break Tackle | 0x0E52A0 | 92 distinct, 1..95 |
| +0x42 | Pass Accuracy | 0x0E5000 | 81 distinct, 2..99 |
| +0x43 | Read Coverage | 0x0E5300 | 75 distinct, 2..99 |
| +0x44 | Catch | 0x0E4F40 | 97 distinct, 1..98 |
| +0x45 | Run Blocking | 0x0E53C0 | 97 distinct, 1..99 |
| +0x46 | Pass Blocking | 0x0E5420 | 97 distinct, 1..99 |
| +0x47 | Secure Ball (Hold On To Ball) | 0x0E51E0 | 97 distinct, 1..99 |
| +0x48 | Pass Rush | 0x0E54E0 | 96 distinct, 1..96 |
| +0x49 | Run Coverage | 0x0E5540 | 95 distinct, 5..99 |
| +0x4A | Kick Accuracy | 0x0E5120 | K 74, P 72, everyone else 11-20 |
| **+0x4B** | **Kicking Style** | 0x0E5780 | **only 1 (×45, every P), 49 (×1,848), 99 (×51, every K)** |
| +0x4C | Leadership | 0x0E56C0 | 89 distinct, 1..99 |
| **+0x4D** | **Power Run Style** | 0x0E5720 | **only 1 (×396), 38 (×1), 50 (×427), 99 (×1,120)** |
| +0x4E | Composure | 0x0E5600 | 81 distinct, 10..99 |
| **+0x4F** | **Scramble (hidden)** | 0x0E4C00 / 0x2D7BB0 / 0x2D82F0 | **5 for nearly every non-QB; 10..97 for QBs; 24 for 29 fast HBs** |
| +0x50 | Consistency | 0x0E5660 | 99 distinct, 1..99 |
| +0x51 | Aggression | 0x0E57E0 | 85 distinct, 1..99 |

Three bytes stand out because retail never varies them freely: their values sit in two or three
buckets. Those are the style channels.

**Scramble is real but hidden.** `+0x4F` appears in no Player Card list, but the game's own roster
editor has a row for it: handlers `0x00344AC0` (display, `movsx eax,[eax+0x4F]`), `0x00344A50`
(increment) and `0x00344A90` (decrement), descriptor `.rdata 0x005647B0`, label string
`"Scramble"` at `0xEAF280`. The neighbouring block is `"Leadership"` reading `+0x4C`, which fixes
the pattern. Injury scaling confirms the numbering: `cb_002D82F0` passes attribute index `0x19` =
25 = `0x4F − 0x36`.

## 2. The three style channels

### 2.1 Power Run Style, `+0x4D` — three states (PROVED)

Retail holds only 1, 50 and 99 (plus one stray 38). By position: CB, FS, SS are all 1; OLB, ILB,
C, G, T, DT, DE are all 99; QB, K, P are all 50; WR 33×1 / 150×50 / 17×99; RB 27×1 / 67×50 /
28×99; FB 4×50 / 75×99; TE 1×50 / 109×99.

The game's own editor decodes it at `0x00344E10`:

```
00344e15  movsx eax, byte ptr [eax+0x4D]
00344e19  cmp  eax, 0x21        ; < 33
00344e1e  mov  eax, 0xEAC834    ; L"Finesse"
00344e24  cmp  eax, 0x42        ; < 66
00344e27  mov  eax, 0xEAC844    ; L"Balanced"
00344e2e  mov  eax, 0xEAC858    ; L"Power"
```

**Thresholds 33 and 66.** The cycler at `0x00344E40` writes exactly 50 / 99 / 1 (reverse cycler
`0x00344E70`, row descriptor `.rdata 0x00562604`, label `"Power Run Style"` at `0xEAEE14`). In
gameplay the byte is consumed as `value × 0.01` through `cb_002E1550` and its siblings — a blend
weight, not a hard table switch — which is why the authors quantised it to three values.

### 2.2 Scramble, `+0x4F` — the parity bit (PROVED) and the mobile family (PROVED)

An exhaustive Capstone scan of all 1,627,635 `.text` instructions for any `and` / `test` / `shr` /
`sar` / `bt` (register or immediate mask) within ten instructions of a byte load at displacements
`0x36..0x51` returns **exactly one hit**:

```
002d9290  push ebp / mov ebp,esp / and esp,~0xF / sub esp,0x34
002d929c  mov  edi, [ebp+8]
002d929f  mov  eax, [edi+0x3C]          ; entity -> the 0x54 roster record
002d92a2  xor  ecx, ecx
002d92a4  mov  cl, byte ptr [eax+0x4F]  ; SCRAMBLE
002d92a7  mov  ebx, 1
002d92b1  and  ecx, ebx                 ; <<<< PARITY
002d92b7  mov  cl, byte ptr [eax+0x4F]  ; again, this time as a 0..1 rating
002d92e2  mov  al, byte ptr [eax+0x37]  ; AGILITY, same normalisation (x 0.01)
```

Decompiled (`d2/002d9290_FUN_002d9290.c`):

```c
bVar3  = record[0x4F];
bVar12 = 0.01f*record[0x4F] + 0.01f*record[0x37] <= 1.5f;     // [0x004E6D0C] = 1.5
uVar8  = direction_octant;                                     // angle >> 13, 0..7
if ((bVar3 & 1) == 0) {
    if (bVar12) set = PTR_PTR_00AD2048[uVar8] + DAT_0052FFE0[bucket]*0x10;   // EVEN, low
    else        set = PTR_PTR_00AD2088[uVar8] + ...;                         // EVEN, high (mobile)
} else          set = PTR_PTR_00AD2068[uVar8] + DAT_0052FFE0[bucket]*0x10;   // ODD
return set + (mirror_bit ? 4 : 0);
```

So the byte is read twice, independently: its **low bit** picks one of three families of eight
directional animation sets (`.data 0x00AD2048 / 0x00AD2068 / 0x00AD2088`), and its **magnitude**,
added to Agility, decides between the two even families (threshold 1.5, i.e. Scramble + Agility
above 150 is the "mobile" family). The three pointer arrays share their odd-index entries
(`0xAD18C8`, `0xAD1828`, `0xAD16E8`, `0xAD1648`) and differ only at 0, 2, 4, 6; each set is a run
of `0x10`-byte records `{clipA, clipB, blendMode, 0}`, and comparing even-low `0xAD1968` with odd
`0xAD1BE8` shows the blend partner is identical (`0x86D444`, `0x86EFE4`, `0x870A08`) and only the
primary clip changes. That is a style swap: same action, different motion.

Which family each retail player lands in (all 1,944 live records):

| family | count | who |
|---|---|---|
| ODD → `0xAD2068` | 1,804 | everyone at the default Scramble = 5, **plus 3 QBs** (Scramble 53, 81, 97) |
| EVEN low → `0xAD2048` | 123 | 91 QBs, the 29 fast HBs (Scramble 24), 1 WR, 2 others |
| EVEN high → `0xAD2088` | 17 | **17 mobile QBs** where Scramble + Agility > 150 |

Among the players who actually reach this code (quarterbacks), ODD is the rare hand-set case: 3 of
111. The Scramble-97 quarterback is Michael Vick; the other two are Rich Gannon and Philip Rivers,
the three unorthodox deliveries in the 2004 league.

**Parity is not handedness.** The editor's own `"Best Hand"` row (label `0xEAEEB8`, descriptor
`.rdata 0x00562AD4`, handlers `0x00345680 / 0x003456A0 / 0x003456E0`) toggles **bit 1 of the dword
at `+0x18`** (`mov ecx,[eax+0x18]; shr ecx,1; and dl,1; … and [eax+0x18],0xFFFFFFFD`). Across all
live records there are 22 left-handers (5 QBs) and the hand bit does not correlate with Scramble
parity: of the 3 odd QBs, one is left-handed and two are right.

**What the animation is — a hypothesis, stated as one.** PROVED: parity picks the clip family in
`FUN_002D9290`, which is called twice from the routine containing `0x002DA797` / `0x002DA8FA`,
reached from `FUN_002D9700`, a large aim/lead routine that takes a target point, walks both teams
measuring distance to it, computes an angle and writes an output angle plus an early-out token
`0xAAA`. HYPOTHESIS (strong, unwitnessed): this is the **throw / release** selector. The cheap
confirmation is a test disc that patches `0x002D92B1` `and ecx,ebx` (`23 CB`) → `xor ecx,ecx`
(`33 C9`) so everyone takes the even branch, and a look at which animation stops varying. That
patch is not implemented in the studio.

### 2.3 Kicking Style, `+0x4B` — a channel retail never varies (consumer UNPROVED)

The game names it: the getter family at `0x0E5780` (and `0x00187AD0` with the injury modifier)
and a Player Card label read KICKING STYLE, and retail holds it at exactly 99 for every kicker,
1 for every punter and 49 for everyone else. But there is **no create/edit-player row** for it (an
exhaustive sweep of `.rdata 0x550000..0x570000` finds the "Scramble" and "Best Hand" rows and no
"Kicking Style" row), and no threshold compare on `+0x4B` exists in `.text` outside the accessor
blocks; it is read as `value × 0.01` via `FUN_00187AD0`. The K = 99 / P = 1 split suggests
soccer-style versus straight-on, but that is a hypothesis. The studio ships the byte as
**EXPERIMENTAL** with the three retail values as presets and promises nothing about what it does.

### 2.4 Survey

| record byte | what it is | selects | exact test | status |
|---|---|---|---|---|
| **+0x4F** Scramble | hidden rating, editor row "Scramble" | animation-set family (8 directional sets of `0x10`-byte blend records) | **`record[0x4F] & 1`** at `0x002D92B1`; plus `0.01·[0x4F] + 0.01·[0x37] <= 1.5` (`[0x004E6D0C]`) | test PROVED; "it is the throw motion" = strong hypothesis |
| **+0x4D** Power Run Style | rating quantised to 1/50/99 | ball-carrier style, as a 0..1 blend weight | UI `< 0x21` Finesse / `< 0x42` Balanced / else Power at `0x00344E19` / `0x00344E24` | PROVED (UI); gameplay = blend weight, no hard switch found |
| **+0x4B** Kicking Style | rating, retail 99/49/1 by position | presumed kick motion | none found outside accessors; read as `value × 0.01` via `FUN_00187AD0` | PROVED it is a style channel retail never varies; consumer UNPROVED |
| +0x18 bit 1 | appearance dword | left/right "Best Hand" | `([rec+0x18]>>1)&1`, toggled `0x003456AF..0x003456D4` | PROVED |
| all other ratings | ordinary | physics / AI scalars | **no bit or parity test exists anywhere in `.text`** | PROVED negative |

Worth saying plainly: **there is no secret parity encoding spread across the ratings.** There is
exactly one, on the hidden Scramble byte, plus two rating bytes whose *names* say STYLE and whose
retail values are quantised into two or three buckets.

## 3. The game's own create-a-player templates (PROVED)

The create-a-player screen fills the 28 bytes from a table at `.rdata 0x005561B8`: 36 records of
`0x74` bytes, each a label pointer and 28 `int32` slots. The record for a player is
`3 × position + variant` (`0x343466..0x34347B`), so the table covers the twelve positions QB, K,
P, WR, CB, FS, SS, HB, FB, TE, OLB, ILB with three variants each — Pocket / Scrambling / Balanced
QB, Speed / Hands / Balanced WR, Cover / Physical / Balanced CB, Finesse / Power / Balanced HB,
Blocking / Catching / Balanced FB, Catching / Blocking / Balanced TE, Run Stop / Coverage / Balanced
OLB and ILB, three identical Kicker and three identical Punter rows — and stops there: C, G, T, DT
and DE have no template.

The only routine that applies it is `FUN_00343460`. It is unrolled — one `mov ecx,[eax+4+4k]` per
slot followed by one `mov byte ptr [record+OFF],cl` — which fixes every slot to a rating byte:

| slot | byte | rating | slot | byte | rating |
|---|---|---|---|---|---|
| 0 | +0x36 | Speed | 14 | +0x40 | Tackle |
| 1 | +0x37 | Agility | 15 | +0x3E | Coverage |
| 2 | +0x42 | Pass Accuracy | 16 | +0x3A | Kick Power |
| 3 | +0x38 | Arm Strength | 17 | +0x4A | Kick Accuracy |
| 4 | +0x43 | Read Coverage | 18 | +0x39 | Stamina |
| 5 | +0x41 | Break Tackle | 19 | +0x3B | Durability |
| 6 | +0x47 | Secure Ball | 20 | +0x4C | Leadership |
| 7 | +0x4D | **Power Run Style** | 21 | +0x4F | **Scramble** |
| 8 | +0x44 | Catch | 22 | +0x4E | Composure |
| 9 | +0x45 | Run Blocking | 23 | +0x3C | Strength |
| 10 | +0x46 | Pass Blocking | 24 | +0x3D | Jumping |
| 11 | +0x3F | Run Route | 25 | +0x4B | **Kicking Style** |
| 12 | +0x49 | Run Coverage | 26 | +0x50 | Consistency |
| 13 | +0x48 | Pass Rush | 27 | +0x51 | Aggression |

Two details matter for anyone reusing the table. A slot of **−1 does not mean "leave alone"**: the
routine loads `bl = 0x4B` once (`mov bl,0x4B` at `0x34349F`) and writes **75** for every −1 slot
(the WR, HB, FB and TE rows carry −1 at slot 25, Kicking Style). Every other value is clamped to
0..100 (`cmp cl,0x64` at `0x3434AE` and its siblings; negatives become 0). The templates confirm
the style readings from a second direction: Pocket / Balanced / Scrambling QB carry Scramble 10 /
50 / 90 and Power Run Style 50 / 50 / 1, and Finesse / Balanced / Power HB carry Power Run Style
1 / 50 / 99. The retail table and the routine are pinned by SHA-256 in
`nfl2k5_roster_records.py` and re-checked by a retail-gated test.

## 4. What the studio exposes

All of this is UI over bytes the ★ Rosters page already round-trips (`+0x36..+0x51`), so nothing
here needs an executable patch.

* **Power Run Style** — a **Finesse / Balanced / Power** segmented control on the Style tab writing
  the game's own 1 / 50 / 99, with the raw byte on a card beneath it (the game reads the byte as a
  blend weight, so intermediate values are legal).
* **Signature release** — a toggle over the **low bit of Scramble** that writes
  `value = (value & ~1) | style` and leaves the magnitude alone; the Scramble slider moves the
  magnitude and preserves the bit (presets Pocket 10 / Balanced 50 / Scrambling 90, the template
  values). The header card names the family the engine would pick (standard / mobile / signature).
* **Kicking Style** — the byte with the three retail values as presets, labelled EXPERIMENTAL.
* **Best Hand** — on the Appearance tab, `+0x18` bit 1, the row the game's own editor toggles.
* **Templates** — the 36 create-a-player templates on the toolbar, the player's three first,
  applied exactly as `FUN_00343460` applies them (−1 → 75, clamp 0..100), read from the loaded
  disc's executable when there is one.
* **Global Attribute Editor** — the style channels are targets and conditions, so a sweep can say
  "every QB with Speed ≥ 80 → signature release" or "every HB with Break Tackle ≥ 75 → Power".
* **OVR** in the grid is the studio's own position-weighted estimate, not the game's overall; the
  game's weights have not been extracted.

Unwitnessed in game: the parity bit's effect has been proved in the code, not watched on the field.

# Madden NFL 09 (PS2) — the executable-patch lane

> Lane `mod_editor/games/madden09_ps2/code_patches.py`
> · capability `madden09ps2.gameplay.executable_patches`
> · classification **`offline-writer-proved`**
> · validator `bash tools/validate_madden09_ps2_code_patches.sh`

**Evidence tags.** **[M]** measured on this box against the executable itself ·
**[S]** sourced from the owner's static-analysis repository · **[A]** assumed.

This lane used to ship the whole interface with every translation refused. It
now carries one real translation — the five `sltiu` immediates that bound the
in-game create-a-playbook editor — and keeps the six unmapped subject areas as
proposals that are still refused by name.

**Nothing here has been booted.** Every claim below is a claim about bytes.

---

## 1. What is translated

One patch, `playbook_editor_caps`, with four parameters and five words.

| parameter | site(s) | shipped cap | what it bounds |
|---|---|---:|---|
| `formations_cap` | PBFM | 20 | formations in one playbook |
| `sets_cap` | PBST **and** SETL | 20 | sets in one playbook (both tables of the same check) |
| `plays_cap` | PBPL | 100 | plays in one playbook |
| `plays_per_set_cap` | the per-set PBPL check | 60 | plays inside one set — a check Madden 2004 did not have |

Each site is one instruction of the form `count + n < IMM`, so the cap is
`IMM − 1` and the translation changes **only the 16-bit immediate**: the
opcode and both register fields are carried through from the word the
executable already holds.

```
replacement = (original & 0xFFFF0000) | ((cap + 1) & 0xFFFF)
```

`sets_cap` drives two words because the editor's `room_for_formation`
predicate tests PBFM, PBST and SETL in one conjunction and needs all three to
have room; PBST and SETL carry the same shipped cap of 20 and are raised
together. That PBST is the *sets* table and SETL the *set-list* table is the
owner's naming **[S]**; what this lane re-derived is that the three checks are
one conjunction and that all three immediates are `21` **[M]**.

**Bounds.** A cap below the one the executable already enforces is refused —
books the disc ships already hold more rows than the editor's cap (78 of 102
books exceed the 100-play cap, 43 exceed the 20-set cap **[S]**), and
shrinking the check would strand them. A cap above **65534** is refused
because `cap + 1` would not fit the 16-bit immediate.

**One honest wrinkle, stated rather than hidden.** `sltiu` **sign-extends** its
16-bit immediate before the unsigned comparison. For any cap up to 32766 the
immediate stays in `0x0000..0x7FFF` and the site enforces literally the number
asked for. From 32767 up, the immediate has its top bit set, sign-extends to a
64-bit value with every high bit set, and the comparison becomes an
unconditional pass — the site stops being a cap at all. Both are allowed (the
second is how a user removes the check outright) and the emitted pnach's own
comment says which happened.

---

## 2. The evidence, site by site

Every word below was read out of the boot ELF and decoded with a
decoder written for this task, not copied from the owner's tools. The ELF read
is the one the lane itself performs: ISO9660 → `SYSTEM.CNF` → the boot file →
ELF32 program headers → `p_offset + (vaddr − p_vaddr)`.

**The executable [M].**

| | |
|---|---|
| boot file | `SLUS_217.70`, serial `SLUS-21770` |
| size | 8,833,384 bytes |
| SHA-256 | `adb400ba49702114876fb3f8e1d2d64dce1b1a57a9d25cd705d74ffcf9f68c4c` |
| PCSX2 CRC | `38014255` |
| zlib CRC-32 | `8CCCDACD` (the value the owner's research pins its addresses against) |
| loadable segments | one `PT_LOAD`: `p_offset` `0x00001000`, `p_vaddr` `0x00100000`, `p_filesz` `0x0085BE28`, `p_memsz` `0x008CD2F0`, flags `RWX` |

The single segment makes `vaddr − file_offset` a constant `0xFF000` across the
whole executable **[M]** — the anchor the owner's `madden09-recon.md` states
**[S]**, here re-derived from the program header rather than assumed.

### 2.1 PBFM — `0x007094A8`

```
007094a0  8FA20000  lw    v0, 0(sp)
007094a4  00511021  addu  v0, v0, s1        ; count + n
007094a8  2C420015  sltiu v0, v0, 21        <== cap 20
007094ac  10400015  beq   v0, zero, 0x00709504
007094b0  3C055453  lui   a1, 0x5453        ; "TSBP" high half -> the next table
```

`original 2C420015` · `disassembly sltiu v0, v0, 21` · file offset `0x0060A4A8` **[M]**

### 2.2 PBST — `0x007094D4`

```
007094cc  8FA20000  lw    v0, 0(sp)
007094d0  00511021  addu  v0, v0, s1
007094d4  2C420015  sltiu v0, v0, 21        <== cap 20
007094d8  1040000A  beq   v0, zero, 0x00709504
007094dc  3C054C54  lui   a1, 0x4C54
007094e4  34A54553  ori   a1, a1, 0x4553    ; 0x4C544553 = "LTES" -> SETL
```

`original 2C420015` · `disassembly sltiu v0, v0, 21` · file offset `0x0060A4D4` **[M]**

The `lui`/`ori` pair after each check builds the next table's 4CC as an
immediate, which is what ties each `sltiu` to the table it bounds: `0x54534250`
= `TSBP` = PBST reversed, `0x4C544553` = `LTES` = SETL reversed **[M]**.

### 2.3 SETL — `0x00709500`

```
007094f8  8FA20000  lw    v0, 0(sp)
007094fc  00511021  addu  v0, v0, s1
00709500  2C520015  sltiu s2, v0, 21        <== cap 20
00709504  0240102D  daddu v0, s2, zero      ; return 1 iff all three passed
```

`original 2C520015` · `disassembly sltiu s2, v0, 21` · file offset `0x0060A500` **[M]**

Note the destination register differs (`s2`, not `v0`) — which is why the
translation preserves the whole word except its low 16 bits rather than
emitting a canned instruction.

### 2.4 PBPL — `0x0070955C`

```
00709554  8FA20000  lw    v0, 0(sp)
00709558  00501021  addu  v0, v0, s0
0070955c  2C510065  sltiu s1, v0, 101       <== cap 100
00709560  0220102D  daddu v0, s1, zero
```

`original 2C510065` · `disassembly sltiu s1, v0, 101` · file offset `0x0060A55C` **[M]**

### 2.5 The per-set play check — `0x006D2890`

```
006d2888  0C1B4558  jal   0x006D1560        ; count(PBPL joined through PBST) + 1
006d288c  00000000  nop
006d2890  2C42003D  sltiu v0, v0, 61        <== cap 60
006d2894  1040005C  beq   v0, zero, 0x006D2A08
```

`original 2C42003D` · `disassembly sltiu v0, v0, 61` · file offset `0x005D3890` **[M]**

This is a different function, a different table join and a different error
message from the four above **[S]**, which is why it gets its own parameter
rather than being folded into `plays_cap`.

### 2.6 The corroborating decode

Two further sites were decoded to confirm the reading of the four in §2.1–2.4,
and are recorded here as evidence rather than shipped as patches **[M]**:

```
007093f0  27BDFFF0  addiu sp, sp, -16       ; room_for_formation(n=1) wrapper
007093f8  0C1C251A  jal   0x00709468
007093fc  24050001  addiu a1, zero, 1       ; delay slot: n = 1

00708dcc  0C1C24FC  jal   0x007093F0        ; the "Add Formation" commit handler
00708dd0  24110002  addiu s1, zero, 2       ; delay slot: PRELOADS error code 2
00708ddc  0012880B  movn  s1, zero, s2      ; room -> 0, else the 2 stands

00708e20  0C1C2504  jal   0x00709410        ; room_for_plays(n=1)
00708e24  24110003  addiu s1, zero, 3       ; delay slot: PRELOADS error code 3
```

Error codes 2 and 3 are the message-table indices of *"there are too many
formations in this playbook."* and *"there are too many plays in this
playbook."* **[S]**. The commit handler pre-loading those exact integers is
what proves these four `sltiu`s are the playbook-editor caps and not some
other conjunction of threes.

### 2.7 Retail vs Deluxe

The community's *Madden NFL 09 Deluxe* rebuild boots the same serial with a
patched executable (PCSX2 CRC `084562FF`, SHA-256
`d1cb5459c589d0dc28c9296c29940eaca161af152ea0b3c9825c012e7588a515`). Both
executables are 8,833,384 bytes and differ in exactly **nine** 32-bit words
**[M]**:

| file offset | vaddr | retail | deluxe |
|---|---|---|---|
| `0x002B25C8` | `0x003B15C8` | `0040202D` | `24040001` |
| `0x00310F58` | `0x0040FF58` | `14500006` | `00000000` |
| `0x004E5FE0` | `0x005E4FE0` | `3C01C1F0` | `3C01C170` |
| `0x0073C024` | `0x0083B024` | `64420008` | `00000000` |
| `0x0073C0AC` | `0x0083B0AC` | `64420008` | `00000000` |
| `0x007ED570` | `0x008EC570` | `C1A00000` | `C1700000` |
| `0x007ED578` | `0x008EC578` | `C1A00000` | `C1700000` |
| `0x007ED57C` | `0x008EC57C` | `C1F00000` | `C1700000` |
| `0x008517CC` | `0x009507CC` | `C1A00000` | `C1700000` |

**None of the nine is at a translated site**, and all five sites hold the same
word in both editions **[M]**:

| site | retail | deluxe | |
|---|---|---|---|
| PBFM `0x007094A8` | `2C420015` | `2C420015` | same |
| PBST `0x007094D4` | `2C420015` | `2C420015` | same |
| SETL `0x00709500` | `2C520015` | `2C520015` | same |
| PBPL `0x0070955C` | `2C510065` | `2C510065` | same |
| per-set `0x006D2890` | `2C42003D` | `2C42003D` | same |

So one recipe translates identically on either disc. The lane still reads the
originals from whichever image the user opened and refuses on any mismatch;
the table above is why that check is expected to pass on both.

The retail executable the owner extracted and the one this lane reads out of
`/mnt/c/Roms/PS2/Madden NFL 09 (USA).iso` are byte-identical — same SHA-256
**[M]** — so the addresses in the owner's research and the addresses this lane
ships are addresses in the same file.

---

## 3. The measured absence of community patches

The shipping standard asks that an executable-patch lane carry *at least the
translations the community already ships, verified against the boot
executable*. For this title that set is **empty**, measured:

* PCSX2's bundled patch archive `resources/patches.zip` holds **4,471**
  entries **[M]**.
* It has **no entry** whose name contains `38014255` (retail) or `084562FF`
  (Deluxe) — the two CRCs PCSX2 keys this title's patches by **[M]**.
* Decompressing and searching every one of the 4,471 files finds **no
  occurrence** of `SLUS-21770` or of the string `Madden NFL 09` **[M]**.

So there is no community patch list for this game to match, and the owner's
own static research is the only source of translations for it. This lane
carries five words more than the community ships, not fewer.

---

## 4. Delivery

Two routes; the pnach is the default and nothing on disc changes.

**`deliver: "pnach"` (default).** `build` emits a PCSX2 patch file naming the
CRC of the executable the words were derived against. `verify` re-parses the
pnach, re-opens the user's image, re-reads every original word, and fails if
the file names a different CRC, declares an address the receipt does not,
misses one, writes a different word, or carries a disabled line.

**`deliver: "disc"`.** The same words are written into `SLUS_217.70` on a
**new** image through the shared fixed-allocation ISO9660 writer
(`tools/ps2_iso9660_writer.py`). This is only sound because a word replacement
never changes the executable's length: the replacement fits the extent the
file already owns exactly, nothing moves, no sector is reallocated, and the
directory record's declared length is rewritten with the value it already had.
`verify` for this route imports none of the writer. It re-opens the
**destination** image through the ISO reader, pulls its boot ELF out
independently, checks each declared word holds its replacement and that the
source held the original, then checks that **every other byte of the
executable** is unchanged, and finally streams both whole images and fails if
any differing byte lies outside a declared four-byte range.

The build declares exactly `4 × (words written)` bytes of the destination
image — the tightest claim available, and the one the conformance harness
checks the change against.

**One consequence worth knowing before choosing the route.** PCSX2's game CRC
is the XOR of every 32-bit word of the executable, so writing the words on disc
*changes it*. Patching the retail image with the four-cap recipe below turns
CRC `38014255` into `380143EF` **[M]**. That is harmless in itself, but it
means a pnach written for the stock CRC will not apply to a patched image, and
the two routes should not be stacked. Pick one.

---

## 5. Classification, and the rule that decides it

**`offline-writer-proved`.**

The registry's own definition
(`mod_editor/capabilities/registry.v1.json`, `classification_definitions`):

> **offline-writer-proved** — *A bounded fail-closed writer and deterministic
> verifier modify a copied user-owned game artifact; runtime visibility may
> remain untested.*

Every clause is met:

* **bounded** — five 32-bit words at fixed addresses, only the low 16 bits of
  each changing;
* **fail-closed** — the plan refuses if any original word is not what the
  recipe expects, if an address is not file-backed, if a cap is out of range,
  if a patch is named twice, if the destination exists, or if the destination
  is the source;
* **deterministic verifier** — `verify` re-derives the whole claim from the
  files alone and fails a tampered pnach and an undeclared image byte;
* **a copied user-owned game artifact** — the on-disc route copies the user's
  image and modifies the executable inside the copy; the source is opened
  read-only;
* **runtime visibility may remain untested** — it is untested, and the row
  says so.

`mod_editor/capabilities/validate_registry.py` then fixes the rest of the row
mechanically: the classification/backend/GUI table requires
`offline-writer-proved` → `backend.operation == "write"` and
`gui.mode == "edit"`, and a classification outside `unknown` /
`unsafe/deferred` requires a `validation_command`. All three are set.

**Why not higher.** `runtime-proved` is defined as *"the exact bounded modified
target was observed in a running title"*, and the validator enforces it with a
hard rule: `runtime-proved` requires `runtime.status == "visible-proved"`,
which in turn requires runtime evidence files. Nothing has been booted, so
that rung is not available and is not claimed.

**Why not lower.** `unknown` is defined as *"the owning data, code, container,
or semantics are not mapped well enough for an editor"*. That was true of this
lane and is no longer: five sites are decoded, the translation arithmetic is
`IMM = cap + 1`, and the verifier passes against the real executable. Leaving
the row `unknown` would keep a working writer hidden and would misstate the
evidence in the other direction.

This puts the row on the same rung as every one of the sibling PS2 module's
offline writers (`nfl2k5ps2.colors.unif_words`, `.menus.text_banks`,
`.players.disc_roster`, `.saves.roster_name_writer`,
`.scripts.director_playbook`, `.stadiums.position_lanes` — all
`offline-writer-proved` / `edit` / `not-tested`).

---

## 6. What this patch does **not** do

The five words are the **editor-side layer only**. They are not, on their own,
a playbook expansion. Three measured reasons:

1. **The shipped tables have no slack.** All **1,944** tables in the disc's
   playbook containers have `record_count == max_records` — every table sized
   exactly to its contents **[S]** (the owner's `madden09-iso-contents.md`
   §6). `max_records` on disc *is* the shipped capacity.

2. **The library takes its capacity from that header, not from any
   immediate.** The table-header loader writes the on-disc `max_records`
   straight into the runtime table object **[M]**:

   ```
   0081a2a4  97A20014  lhu v0, 20(sp)     ; on-disc max_records (+20)
   0081a2a8  A4820042  sh  v0, 66(a0)     ; -> runtime +66, live capacity
   0081a2b0  97A20014  lhu v0, 20(sp)
   0081a2b4  A4620040  sh  v0, 64(v1)     ; -> runtime +64, declared capacity
   0081a2bc  97A20016  lhu v0, 22(sp)     ; on-disc record_count (+22)
   0081a2c0  A4820044  sh  v0, 68(a0)     ; -> runtime +68
   ```

3. **The insert guard then refuses, it does not corrupt.** The library's own
   capacity check, decoded **[M]**:

   ```
   0082a098  96420044  lhu   v0, 68(s2)   ; record_count
   0082a09c  96430042  lhu   v1, 66(s2)   ; capacity
   0082a0a0  0043102B  sltu  v0, v0, v1   ; room iff count < capacity
   0082a0a4  10400005  beq   v0, zero, 0x0082A0BC
   0082a0a8  24020013  addiu v0, zero, 19 ; delay slot: PRELOADS status 19
   0082a0ac  96550044  lhu   s5, 68(s2)
   0082a0b0  26A20001  addiu v0, s5, 1
   0082a0b8  A6420044  sh    v0, 68(s2)   ; room: record_count += 1
   0082a0bc  AFA20004  sw    v0, 4(sp)    ; no room: status 19 goes out
   ```

   The same `addiu v0, zero, 19` pre-load appears at the other guard
   (`0x008178A4` area) **[M]** — the identical idiom the editor uses for its
   own error codes 2 and 3.

**So the expected behaviour of this patch alone is that the editor stops
refusing at 20 and starts being refused one layer lower, with status 19.**
That is a prediction about unbooted code, and it is written here as a
prediction.

### 6.1 Why the second layer is not shipped

It was investigated and deliberately not shipped. The measured reasons:

* **`table_set_capacity` (`0x0082A6A0`) is a subroutine, not an immediate.**
  Decoded whole **[M]**: the new capacity arrives in `a1`
  (`0082a6c4  30B2FFFF  andi s2, a1, 0xFFFF`), the routine (re)allocates and
  then stores it (`0082a760  A6120040  sh s2, 64(s0)` /
  `0082a764  A6120042  sh s2, 66(s0)`). **There is no number in this function
  to raise.**

* **Its callers hand it the capacity they just read out of the table.** All
  six static callers were decoded **[M]**; five of the six supply
  `a1 = lhu 64(base)` — the declared capacity the loader took from the disc:

  | caller | what it passes in `a1` |
  |---|---|
  | `0x00816710` | `s0`, a caller-supplied count |
  | `0x00817898` | `lhu v0, 64(s0)` |
  | `0x008288B0` | `lhu a1, 64(s2)` |
  | `0x0082A05C` | `lhu a1, 64(s2)` |
  | `0x0082AA7C` | `lhu a1, 64(s2)` |
  | `0x0082B054` | `lhu a1, 64(s2)` |

  So raising the runtime capacity means changing what a *caller* supplies,
  which is new code, not a word replacement.

* **The hook site for that new code is not pinned.** The owner's research
  records the database-open path as *located, not fully pinned* — the exact
  instruction a cave would displace was not identified, and closing it needs
  tracing which of nine CRC-consumer call sites sits on the file-open path
  **[S]**.

* **New code cannot be verified here.** A cave is a subroutine somebody has to
  write. Its *original* words (zeros in unused space) would verify trivially;
  its *correctness* would be pure assertion until a boot. Shipping that as a
  "verified translation" is exactly the overclaim this lane exists to avoid.
  Madden 2004's finished equivalent is 123 patch lines around a cave, and none
  of its addresses transfer: 09's runtime struct moved the capacity fields from
  `+108`/`+110`/`+112` to `+64`/`+66`/`+68` **[M, S]**.

* **And it would still not be enough by itself.** With every on-disc table
  packed full, a bigger runtime capacity has nothing to read into it; the
  2004 precedent needed the data side provisioned too. This module has no
  writer for those containers — the `LZH1` codec has no public encoder, which
  is already recorded as the blocker for every other Madden 09 writer.

---

## 7. What still needs a boot, and how the owner witnesses it

Nothing in this lane has been run in an emulator. Two witnesses, in order:

1. **The cap moved.** Load a shipped 20-set playbook in the create-a-playbook
   editor with the pnach active and try to add a **21st set**. Without the
   patch the editor refuses with *"there are too many formations in this
   playbook."* / *"there are too many plays in this playbook."* With it, the
   editor's own check should pass. Recording the message that appears instead
   is the whole result — including if it is the same message, which would mean
   a site was misread.

2. **What stops it next.** The prediction in §6 is that the attempt then fails
   in the library with status 19 rather than adding a row. Whatever actually
   happens is the finding; the prediction is not evidence.

Until (1) is recorded the row stays `offline-writer-proved`. Neither witness
can be produced on this box: no emulator was run here and none will be.

---

## 8. Reproducing the checks

```bash
# the lane's own proof, no game data at all
python3 -m mod_editor.games.madden09_ps2.code_patches --selftest
#   -> CODE_PATCH_SELFTEST PASS patches=7 translations=1 sites=5

# read the five sites out of your own disc
python3 -m mod_editor.games.madden09_ps2.code_patches --source "<your SLUS-21770>.iso"

# plan, build and verify a pnach from a recipe
python3 -m mod_editor.games.madden09_ps2.code_patches \
    --source "<your>.iso" --recipe recipe.json --destination out.pnach

# the whole module, on synthetic sources
bash tools/validate_madden09_ps2_code_patches.sh
python3 -m mod_editor.games conformance --game madden09_ps2
```

A recipe raising the caps to the shipped maxima the owner's census measured
(15 formations already fit under the stock 20; 127 sets and 346 plays do not):

```json
{
  "schema": "madden09_ps2_code_patch_recipe/v1",
  "deliver": "pnach",
  "patches": [
    {
      "patch": "playbook_editor_caps",
      "parameters": {
        "formations_cap": 20,
        "sets_cap": 130,
        "plays_cap": 400,
        "plays_per_set_cap": 60
      }
    }
  ]
}
```

`formations_cap` and `plays_per_set_cap` left at their shipped values write no
word, which is why that recipe emits three lines and not five.

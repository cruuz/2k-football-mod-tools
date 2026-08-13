# APF 2K8 Mod Studio Changelog

## 0.1.0-alpha.73 — no APF changes — 2026-08-13

Beta 41 fixes 2K5's fixed VC-LZ span handling: a texture that will not fit its
retail compressed allocation is now quantized down instead of failing the
build, and every build failure names the edit that caused it. Nothing in APF
changed; the version moves so both products keep shipping from one release, and
the shared update checker identifies this build as `beta-41`.

## 0.1.0-alpha.72 — no APF changes — 2026-08-13

Beta 40 fixes 2K5's Team Kit equipment routing: swapping a sock, glove, shoe,
wristband, elbow pad or long-sleeve texture used to refuse at Build with
`Unknown uniform asset ID`. Nothing in APF changed; the version moves so both
products keep shipping from one release, and the shared update checker
identifies this build as `beta-40`.

## 0.1.0-alpha.71 — Save Project keeps Fine-tune Plays — 2026-08-13

Beta 39 answers three community reports.

**Save Project now saves Fine-tune Plays.** Since the panel shipped in Beta 32
its staged edits lived only in the panel's own memory. Nothing wrote them into
the session, so Save Project produced a file that silently did not contain
them, and reopening that project showed an untouched playbook. Urianus reported
it against alpha.69 and confirmed it was still there in alpha.70.

Every staged change — a play ticked in or out, a tagged slot carried onto
another play, a tagged slot moved — is now one `splb_book_membership`
modification carrying only selectors: an outer entry, a record, and play
indices. Never a byte of the user's SPLB resource. It round-trips through the
project archive with the same canonical-JSON, hash-pinned handling the
assignment-route writer uses, and the main build compiles the whole set into
one rebuilt book, so playbook edits and uniform edits can finally land in the
same volume. Opening a project selects the book its edits belong to instead of
the first in the list. Switching books with work staged now asks, because the
writer compiles one book at a time; it used to discard silently. Reverting one
change proves the rest still compile rather than failing at build time.

**Emptying a formation now leads with what it does in game.** Urianus emptied
the formations without a TE in `O-ManBlock` and watched the CPU line up
personnel packages that book does not contain (00, 10, 01, 12, 11) and one the
game does not ship at all (02), running plays that are not in the book. It
happened whenever the director selected an emptied formation; untouched books
behaved normally. Plays are not bound to formations — he moved an offensive
play into a defensive book and it ran — so a formation that stores nothing does
not make the director skip it, it makes the director call something the book
never listed.

The static facts are unchanged: count `0x84a8ac30` returns 0 and get-nth
`0x84a8bd20` returns null for an empty record, so the four tagged plays cannot
come from it. That was never a proof that the director handles the null well,
and the previous copy read as though it were. The confirmation dialog now opens
with the report, the compile report carries
`empty_record_runtime_safe: False`, and emptying **every** populated formation
in a book is refused outright — that leaves the director nothing at all to
select.

To keep a formation and put TEs on its tagged slots, add those plays and use
**Move tagged slot…**; nothing has been reported against that path.

**The panel's static record moved behind “Research pins”.** All of it still
ships — every address, including the withdrawn candidates — but 11,360
characters of hex no longer word-wrap between the play list and the buttons.

## 0.1.0-alpha.70 — tagged-slot compose, empty formations, title update 1.1 — 2026-08-12

Beta 38 fixes the stock-playbook verifier so a tagged slot can move onto a play
added in the same request (X-43Blitz Bear: play 542 → 560). Fine-tune Plays
gains **Empty this formation…**, which sheds every stored play because
`min(4, 0)` is 0 and leaves the record trailer untouched. The decompressed
executable counts that list at `0x84a8ac30` and returns the nth play at
`0x84a8bd20`; an empty record returns 0/null. Launch copies the hash-pinned
Xbox 360 title update 1.1 LIVE package into this session's isolated Xenia
content folder; the update never shipped for PS3. Automatic WR3→TE package
substitution is not offered: APF MASTER has an 11-byte role permutation at
formation `+0x11`. Role 8 is TE and role 9 is WR (`0x820FC320` / `0x84a9ae68`);
the 11-player builder indexes that map by slot (`0x848605b4`). Swapping those
two map bytes is not runtime-proved. MASTER categories at `+0x44` are
personnel packages (Ace, 5 Wide, Flush); `0x8485bd38` extracts the SPLB
trailer index. `0x84a472d0` is play-type UI, not down; `0x8486ce88` picks a
play from situation word0 / `+0x2BC` (a tab). Eligibility ANDs map-role
masks at `0x820FC380` with a personnel cell (also `0x84862580`);
`0x844dbe00` is `.pdata`, not a script table; `0x84b694a8` stores 1 or 2 to
situation `+8`. `0x84a89ea8` maps a play onto an SPLB record, not a
situation; `+0x1F8` is a play-type filter. `0x848699d8` filters by type
nibble, not down. `0x848699d8` reads the current book from playcall `+0x20`
(global `0x851A2780`); `0x8493d968` registers that object. `0x8485e7f8` has 0 `bl` callers. `0x8466af70` loads `dir_ingame.iff`. `0x8466a818` relocates DRCT pointers (NFL `0x000dc700` analog); `0x8466aae0` walks the relocated fixed table, not the instruction consumer. `0x8466abc0` indexes fixed-record children via `+0x18`; `0x8466af28` indexes strings via `+0x14`. Picker `0x8486ce88` takes the playcall object as `r3` (`0x8470c2c4`). Jump-table `0x8470bf18` takes a small integer mode 0..19 (`0x84712498`); case 2 (`li r3, 2` at `0x847163d4`) is frontend, not CPU down/ytg. Find-by-slot's book singleton is `0x8520CDE0` (init `0x84a139d0`). Shadow `0x84887e18` writes bitmasks to `0x8516C908+0x20`, not a book. Slot `+0` can be type singleton `0x850F1218` (install `0x84ad0048`); init `0x847c6da8` copies live MASTER from `0x84F3F7D8+0x2C` (`0x849fd6a8`) onto type `+0x20`. Helper `0x8486cd80` is UI-only. Setter `0x849fd6c8` is bind/SPLB-select (table `0x851D9660` via `0x849fcf60`), not per-play. `0x849d81d0` is init-stored at `0x84E28670+0x2C94` (0 `bl`). `get_down` lives only in packed property blob `0x84EB0DE4`. Property-get-by-id `0x849c9c90` uses ids 997..999, not down. Relocator `0x8466a994` inlines the instruction directory at `+0x20`. NFL `0x000dca40` is a bitset/float lookup, not an instruction indexer. `dir_ingame.iff` (outer 153) has 1015 instruction records; 1014 begin `0B 00 01 00` then a token at +4 — bytecode, not a C++ vtable. The relocator rewrites only the inline directory words; it does not follow those pointers into record bodies. Packed `lhz +6` getter `0x84ab2010` has 0 `bl` and 0 inbound pointers. DRCT vtable[2] `0x8466ba30` unlinks a list. Byte-stream `0x8466bd38` compares 94/96/97 and 275–330, not instruction tokens. `0x84bcd760` is a string classifier (0 `bl`). 0 `addi 32`/`lwzx`/`lbz 0(record)` consumer. `dir_wrapup.iff` (outer 265) has 96 records, all `0B 00`. Groups are tagged fields (`0B 00` + u16 field + u8), not a VM opcode at +4. vtable[0] `0x8466b8b0` only relocates then walks the fixed table (`bl 0x8466aae0` at `0x8466b8fc`). Packed +0x14/+0x18 indexers have 0 `bl` and 0 inbound pointers. `0x8466af48` is a bounds check (r4 < +0x10), not a type mapper. `0x84b162a8` is an embedded C++ object at +0x20. `lbz`+`cmpwi 11` then 12 is a class-id, not tag `0x0B`. Field ids inside `0B 00` groups are BE u16 `0x0100`/`0x0200`, not 1/2. Nested lead bytes `0x03`..`0x09` appear after those groups. 0 `lhz`+`cmpwi 0x0100` parser (`0x84c381e8` is stack/float). 0 skip-`0B 00` then `lhz`. 0 `lhbrx` in TEXT. `0x84a87b38` is play-type nibble `srwi 28`. `0x84bdfb00` is ASCII Y/I. 0 `cmpwi 0x0B00` in TEXT. `0x848bb1a8` is RTTI class 2 vs 11. `0x8466b660` is a map count vs 256, not field `0x0100`. `0x8466c7f0` is a packed LE f32 (4×lbz, not lwbrx). 0 lis/addi of `0x84EE65C0`. `0x84671838` is C++ vt[2] on r4+0x20, not a property registrar. 0B groups are tag + u8 variant + BE u16 field + u8 (variant 0 is 3589/3621; variants 1–5 use field `0x0200`), not a 2-byte `0B00` tag. `0x84842f48` is RTTI class 3/4/5/6/7/11/12 via +0x14/+4. `0x8476ca80` counts 10×5-byte slots at object +0x13D9. `0x8492bb24` sums 5-byte windows then uses floats. `0x84b0a4c0` compact-int-indexes stride-12 table `0x84EE65A8` (max id `0x35`) then `bctrl` get/set; 0 `cmpwi 11` in those cases. `0x849e7790` copies a 12-byte record (`0xffff` sentinel), not a 0B group. `0x847e2818` is class-id 3/5/6/7/4 via +4, not leftover leads. `0x84abb590` copies 5 bytes with no tag check. `0x84a9d7a0` copies stride-32 floats at +0x1C, not NFL table `0xB73BD0`. NFL `dir_ingame` (outer 4) has 1310 instruction records, all starting `0B`; prefixes `0B 00 01 00` / `01 01` / `01 02` — same tag+variant+u16 encoding as APF. `0x84be2b48` is an ASCII/scanf 0..11 jump, not leftover leads. `0x848777cc` loads one float from `0x84F1A150+0x1C`, not a stride-32 bitset table. `0x84b93b10` reads a 5-byte header with no `0x0B` check; caller `0x84b94258` switches on first byte 0..4. Non-`0B` leftovers are concatenated typed groups: type `0x04` is tag + 4-byte LE float (size 5) on APF and NFL; types `0x05`/`0x06`/`0x07`/`0x08`/`0x09` are 1-byte tags (a following `00` is the terminator type, not a payload); type `0x03` is tag + u8 (size 2). That walk consumes APF ingame 1015/1015 and NFL ingame 1310/1310. `0x849277a8` switches on a presentation byte (cases 4/11 store floats), not those tags. `0x84c4c480` copies 1/2/4/8 bytes with endian swap (`cmplwi` 1/2/4/8 then `lwbrx` for width 4), not a type-4 float reader. `0x84ba2520` walks a stride-12 table in r4 from a packed descriptor (`mulli` 12 + `lbz` +8), not a property `bctrl` registrar. `0x846c2068` compares object +0x62 to 4 then stores 5, not float-group size. `0x8466c890` is a float-expression VM (opcodes 0..12, table `0x8466c91c`, cursor `0x84F1779C`); case 4 is the LE f32 immediate (helper `0x8466c7f0`); case 11 consumes 1 extra byte, not a leftover 0B group. Descriptor slot `0x844dd260`. `0x8477f950` switches on a UI byte 0..12 (cases 5-10 just return). `0x84a37850` loads situation down and ytg together and wraps ytg at 100, not a play picker. `0x848864b0` compares situation word0 to 4 (not down) and playcall+0x38 to 11. `0x84a5eb08` indexes 24-byte tables by type 3/4/8/9/11/12, not leftover. `0x8475b7b0` tweens `0x84D58C70` (`lfs` +0x258, counter +0x25C), not situation ytg. NFL xbe has 0 `add r32,5` within 80 bytes of `cmp al, 0x0B`; the only `.text` sites with both `cmp al,4` and `cmp al,0x0B` within 48 bytes are `0x1138e0` (object +0x35 enum) and killed play-type classifiers `0x133fd1` / `0x27e830`. `0x84a23bd0` cycles situation +0x1F8 through 0..7 (UI play-type filter), not CPU 3rd-and-long. The only PE pointer to picker `0x8486ce88` is its `.pdata` row `0x844e8568` (section `0x844DBE00`), not a `bctrl` dispatch slot. Situation +0x1F8 setter `0x849d36d8` has 0 `bl` and 0 PE pointers. NFL relocator `0x000dc700` returns after fixing +0x14/+0x0c/+0x08 and does not walk instruction bodies. `0x848631d0` is the +0x1F8 getter used by the "Offensive Play calling" widget (`0x845FE7D4`); `0x849d36d8` remains the packed setter (0 `bl`). NFL `0x168ad0` walks a SHAP list at +0x14 (stride 0xC, dword==3), not leftover TLV. The only `lhz` +6 then `addi` 32 is relocator `0x8466a994`. `0x84a2ccd8` reads situation +0x1F8 and +0x2BC (word0==2, filter==0, tab==3), not down/ytg. The only TEXT sites with cmp 4, addi 5, and cmp 11 together are occupancy `0x84961548` and bit-pack `0x849e3a24`, not leftover sizes. Picker-caller neighborhood `0x84814dcc` / `0x84816118` compares situation word0 to 4, not Fourth Down; the addi 5 is `srawi`-3 index math. `0x8485a04c` switches word0 0/1/2/3/4/9 into mode immediates. Real `addi r,r,5` (not `li 5`) plus cmp 4/11 is still not a leftover stream: `0x84869e60` is a 4-wide fill remainder and `0x84a9adcc` is an 11-slot `lbzx` at object+5 beside the role table. `0x84a21298` is a packed UI formatter (0 `bl`) that indexes the seven labels at `0x84E446C8` ("First Down" … "Third and Long" `0x845FD8B4` … "Fourth and Long"); every `lis`/`addi` of its object `0x85212B88` sits in the same `0x84a20xxx` widget cluster, not a CPU picker. `lbz`+`cmplwi` 9 then `bctr` at `0x84911750` / `0x849ecd48` switch object fields, not leftover tags. `0x847d7590` / `0x8480189c` compare playcall `0x851A2780+0x3C` to 3/6, not down. Every TEXT `lis`/`addi` of leftover cursor `0x84F1779C` / `0x84F177AC` sits in expr-VM `0x8466c778`–`0x8466d888`; the VM entry stores r5 to cursor+8 (`0x8466c8dc`). No TEXT site loads situation +0x254 and +0x25C together and yields D&D index 4; lookalikes `0x8499e420` / `0x849a3b58` compare script node +0x10/+0x14. Packed get_ytg `0x84b68cd8` (`lwz r3, +0x25C(r3)`) has 0 `bl` and 0 PE pointers; the situation property blob that holds get_down `0x84ad92e0` has no +0x25C getter. Expr VM `0x8466c890` has only desc slot `0x844dd260` (0 inbound PE ptrs, 0 TEXT `lis`/`addi`). 0 `lwz` +0x20 then `lbz` and cmp 4/11 leftover walk. `0x84879bc0` extracts ytg bit 1, not a D&D index. Packed object get_down `0x84b68cc8` sits next to get_ytg (0 PE ptrs). `0x84ad0348` copies situation +0x254/+0x258/+0x25C onto a stack blob (only PE is `.pdata` `0x844f72b0`); not a D&D index. 0 aligned inbound PE pointers into get_down blob `0x84EB0800`..`0x84EB0F00`. Other TEXT `lwz` +0x254/+0x25C pairs are stack slots, tween `0x8475b7b0`, status query `0x84b694a8`, or a non-situation object where +0x254 is a pointer (`0x84b39458`). TEXT `lis`/`addi` of the blob only hit row base `0x84EB02D0` (packed `0x84ad9f40`: `mulli` r4, 0x1C then `lwz` +4). get_down's row `0x84EB0DD0` is not 0x1C-aligned from that base. 0 `addi` 32 then `lwz` 0 then `lbz` 0(record) leftover walk. 8 `lwz` +0x20 then `lbz` 0 sites are string/ASCII. Only TEXT `lis 0x0B00` is bitmask `0x848ee750` (`li r4, 11`). `0x84b64c88` walks a 4-byte window with UTF-8 extra-byte table `0x844C69C8` (0xC0→1, 0xE0→2, 0xF0→3; 0x0B→0), not leftover sizes. Which play the CPU
calls on 3rd-and-long
remains runtime-unproved (down is object `+0x254` / Third Down = 3 at
`0x848d96e4`; that helper is not a play picker). The shared update checker
identifies this build as `beta-38`.

## 0.1.0-alpha.69 — visible exports and honest playbook wording — 2026-08-12

Beta 37 completes the Beta 36 mask-preview follow-up:

- Preview cache entries retain their display-only alpha explanation across
  cache hits instead of deriving it from already-opaqued pixels.
- Uniform, generic TXTR, and embedded scene-texture PNG exports use the same
  visible display pixels as the preview. The existing encode guard restores
  retail all-zero alpha when an edited image returns through a proved writer.
- A decoded source whose RGBA channels are all zero is identified as an empty
  retail slot, not reported as a decoder failure.
- Playbooks → Fine-tune Plays now describes the stored SPLB membership it edits;
  runtime CPU consumption of an edited list remains unproved. The shared update
  checker identifies this build as `beta-37`.

## 0.1.0-alpha.68 — previews and normal-user Windows builds — 2026-08-11

Beta 36 makes `jersey_color` and `shoulder_color` previews visible when retail
stores their unused alpha channel as all zero. The preview substitutes opaque
alpha only for display, exports the original RGBA, and restores retail zero
alpha before either writer encodes a replacement. DXN (`helmet_color`) errors
now explain that the asset layer owns its separate decoder.

Windows builds no longer depend on administrator-only symbolic links: staged
pack references fall back from symlink to hardlink to a verified copy, and
exports use the platform no-replace publisher so exFAT is supported. The
installer remains per-user; output should be a new writable folder outside
Program Files and the original game folder.

Field Art now makes the full 235-layer stock endzone family discoverable for
browse/export. The focused writer still owns only the two shared outer-6
layers; per-team replacement remains unproved and is labeled that way.

### Fixed: a second, smaller logo in the corner of your crest

- **A regenerated crest wrote one mip level through another.** At some draw
  distances the crest showed your logo with a smaller copy of itself tucked
  into a corner, and at the smallest ones it showed the retail logo as though
  the mod had not applied. Both came from one addressing mistake in the packed
  mip chain, so both are gone.
- The chain advanced each level by the product of its aligned dimensions. Xenos
  starts every stored level on a 4096-byte boundary, and a 32x32 tile of
  two-byte texels is scattered over 0xC00 bytes of address space rather than
  packed into 0x800. The packed tail was therefore addressed 0x800 bytes inside
  the 32x32 level: regenerating the chain overwrote 427 of that level's 2048
  bytes with the 16x16 and smaller levels, and never touched the real tail.
- The corrected chain accounts for the retail-declared mip length of 0x2C000
  exactly, with nothing left over. The old one reached 0x2B000 and explained the
  missing page away as padding.
- Only the crests were affected. The uniform, wordmark and helmet writers use
  block-compressed formats at 8 or 16 bytes per block, where both corrections
  are no-ops; their output is unchanged, byte for byte.
- If you built a crest with alpha.64 through alpha.66, rebuild it from the same
  PNG — no re-authoring, just another Build.
- `derive_layout` now refuses any layout whose levels share bytes, so this
  cannot reach a crest again without failing first.

### Team Logo can author both crest layers

- **Replace both layers…** imports an edited `logo_l0` and `logo_l1` together.
  Export both layers could already take a crest apart; putting one back needed
  `tools/apf_logo_patch.py --png --png-l1` at a terminal, which left the 79 of
  118 packages that use both layers effectively read-only in the app.
- Each image is sized the way a single import is sized, and both are carried
  into the package and the logo cache by the same proved writers.
- **A single image no longer gets copied into `logo_l1`.** The two layers hold
  regions 0-2 and 3-5 of one crest and are not interchangeable, so the same mask
  in both selected all six regions and drew the mark once per region. One image
  now goes to `logo_l0` and clears the detail layer — what the export dialog
  already said happened, and what a full project Build already did. The
  copied-volume Build was the odd one out, so the same staged image could give
  you two different crests depending on which button you pressed.
- `tools/apf_logocache_patch.py` gains the `--clear-l1` flag its Python API
  already had, so the cache can be told the same thing as the package.

## 0.1.0-alpha.65 — the stock CPU playbooks, and a corrected claim — 2026-08-10

### Edit the CPU playbooks themselves

- **Playbooks → Fine-tune Plays now edits the stored membership in the stock
  `SPLB` books.** Each is an on-disc resource of exactly 32,288 bytes holding a
  176-record array; a populated record names a MASTER formation and stores its
  play list. Pick a book, pick a formation, tick plays in and out, build a
  copied `0A`. Runtime CPU consumption of an edited list remains unproved.
- Fifteen books ship: seven offensive (`O-ZoneBlock`, `O-WestCoast`,
  `O-ManBlock`, `O-Shotgun`, `O-TwoBack`, `O-SinglebackAce`,
  `O-Singleback3WR`), four defensive (`X-43Cover2`, `X-43Blitz`, `X-34Base`,
  `X-34ZoneBlitz`) and four unnamed. That is the whole real set — the 36 and 33
  book records in a roster save are labels over these.
- Only the selected record's entry list is rewritten. The record trailer, every
  other record, both tail regions whose meaning is not established, and every
  other byte are preserved, and an independent verifier re-derives every changed
  byte before anything is written.
- Each formation carries four tagged slots whose meaning is unproved, so
  removing one is refused rather than guessed. The panel says which they are.

### Corrected: a claim alpha.64 should not have made

- **alpha.64's Fine-tune Plays described a table it could not prove.** It edited
  MASTER's 0x54-stride bitmap and called it "which plays each formation offers".
  Decoding the `SPLB` books refutes that reading: for MASTER row 147 the books
  give the 3-4 defence "Base, Fan, Razor Left…", while row 147 of that table
  yields "Big Pinch, Big Fan, Big 2 Hard…" — 31 of 51 overlap, rows 147/148/149
  are identical, and coverage across all populated book records is 24–25% with
  no record fully covered. The row index is not the formation index, or the
  relation is not formation-to-play.
- That writer has been removed and `playbook_inventory` now records the relation
  as unidentified. Nothing in the product presents it to a user any more. The
  bytes alpha.64 wrote were bounded and verified; the *description* of them was
  wrong, which by this project's standard is the same defect.

- The shared updater identity is `beta-33`.

## 0.1.0-alpha.64 — two-layer crests, and playbook fine-tuning — 2026-08-10

### The reported crest bug, root-caused

- **One image was being written into both crest layers.** A crest is not one
  picture and not even three masks — it is **six region masks split across two
  textures**. The shader binds `Layer0`/`Layer1` at `s0`/`s1` with a six-entry
  palette and Region0–Region5 weights, so `logo_l0` carries regions 0-2 and
  `logo_l1` carries regions 3-5. Writing your art into both drew it a second
  time in the other three palette colours.
- Measured across all 118 crest packages: **none** have identical layers,
  **79 carry real detail art** in `logo_l1`, and **39 ship a `logo_l1` whose
  RGB is zero with its alpha untouched** — retail's own shape for a crest that
  uses no detail layer.
- One dropped image now goes to `logo_l0` and the detail layer's region masks
  are cleared with its alpha copied through byte-for-byte, so your mark is drawn
  exactly once. To author both layers, use `tools/apf_logo_patch.py --png
  --png-l1`; `--clear-l1` is the new single-image treatment.
- **Export both layers…** saves `logo_l0` and `logo_l1` as separate PNGs, so the
  masks are visible before you edit them.

### Playbooks: fine-tune what a formation offers

- **New Playbooks → Fine-tune Plays.** Pick any of MASTER's 163 formations and
  tick plays in or out of it. APF stores one fixed 74-byte bitmap per formation
  over the book's 586 plays, so each change is a single bit inside a fixed
  allocation: nothing moves, no count changes, the resource keeps its exact byte
  extent, and an independent verifier re-derives every changed byte before a
  copied `0A` is written.
- This is the level below book assignment. The 36 offensive and 33 defensive
  book records in a roster save are **labels**: measured on two real saves they
  resolve to **7 offensive and 4 defensive** actual books (plus user books), so
  reassigning a team from one name to another frequently changes nothing.
- Boundary, stated plainly: this edits the book the game selects plays from.
  Whether the CPU's play-calling reads the same table is **not** proved. The
  stock CPU books are 15 separate on-disc `SPLB` resources; editing those
  directly is not offered yet.

- The shared updater identity is `beta-32`.

## 0.1.0-alpha.63 — browsed rows reach their real editor — 2026-08-10

### Community issue closed

- **`logo_l0 is not an editable PNG slot in this browser` (reported against
  Beta 29 and Beta 30)** — the message was true about the browser and false
  about the product. Every one of the 118 `uniform_logo_NN` crest packages is
  written by **Logos → Team Logo**, and the browser's own search hint pointed
  people straight at those rows. Selecting a row a proved writer owns now offers
  **Edit in Team Logo… / Edit in Uniforms… / Edit in Wordmarks… / Edit in Field
  Art…** instead of a refusal. That button opens the workspace, selects the
  exact slot, and — if you chose or dropped an image in the browser — brings it
  with you already staged. 236 crest layers, 96 uniform materials, 206
  wordmarks, and the six writable field-art textures are covered.
- **The asset notes stopped contradicting the app** — a row a workspace writes
  no longer reads "No validated replacement writer owns this target yet"; it
  names the workspace that owns it. Rows with genuinely no writer say exactly
  that, and still offer raw/parts export.

### Stadium models

- **Editable meshes are a list, not a hunt** — Stadium Studio now carries an
  **Editable meshes** picker holding every catalog-authorized POSITION target in
  the open scene (77 in the proved outer-14 / inner-8 scene). Choosing one
  selects it for Export/Import and highlights it in the 3D view; clicking a
  surface in the view still works and updates the picker. A scene with no
  authorized target says so instead of implying the wrong click.

### Emulator

- **Launch in Xenia never silently grays** — it stays clickable and names the
  one thing that is missing (no build yet, Xenia not configured, or a build
  folder that has since moved). When Xenia is the missing piece, clicking offers
  to choose it there and then, instead of relabelling a dead button.

### Reliability

- A window opened against an already-loaded game no longer fails during
  construction: the shared status/progress footer is built before the pages that
  report into it.
- The asset browser's detail pane can no longer describe a row that is no longer
  selected after a search, which previously let Export act on a stale row.
- The update check refuses to advertise a release older than the running build,
  and reads the highest published beta rather than trusting list order.

- The shared updater identity is `beta-31`.

## 0.1.0-alpha.62 — real-ISO release validation — 2026-08-09

- The shipped ISO recognition, extraction, load, and read-only source path was
  revalidated against a real USA APF 2K8 image in addition to the retail-free
  automated layout-tolerance suite.
- The source remained read-only and no source path, image hash, extracted game
  data, or retail payload is recorded in this public release documentation.
- Linux install and uninstall helpers set `PYTHONDONTWRITEBYTECODE=1` before
  importing installer code, preventing a pre-audit `__pycache__` from making a
  clean release tree fail its own closed-world check.
- The shared updater identity is `beta-30`.
- The bundled Linux `extract-xiso` was rebuilt with its build-host prefix
  removed and stripped; release/runtime pins now cover the 51,336-byte
  privacy-clean ELF.

## 0.1.0-alpha.61 — never-silent-gray + blank-preview fail-closed — 2026-08-09

### Beta 29 refresh

- **Updater identity corrected** — alpha.61 now identifies its release channel
  as `beta-29`, not the stale `beta-22` packaging label, so manual and automatic
  checks no longer offer Beta 29 to an already-current Beta 29 build.

### Community issues closed or honesty-labeled

- **Import / Replace gray with no explanation (Discord class)** — expanded
  never-silent-gray across:
  - Stadium Studio **mesh** Import/Export (disableReason + click-to-explain)
  - Stadium Studio **package** Replace/Export/Revert/Build (locked embeds teach
    surface-ownership wall; POSITION-only mesh lane named in tips)
  - **Wordmarks** Import/Export when game not loaded
  - **AssetBrowser / All Textures** Replace (non-editable rows + Field Art
    browse-export-only locks stay clickable and explain)
  - **UniformStudio** Export/Replace empty state (load/select tip)
  - **digital_font** Export/Replace/Revert when unloaded
  - **Field Art** focused editor Export/Replace/Build/Revert (stage wall)
  - **Team Logo** Export/Replace/Build/Revert/Master (load/stage/profile walls)
  - **Custom Team Appearance** Stage/Revert when unloaded
  - **All Textures empty search** — teaches logo_l0, number_N_color, font_albedo
  - **Equipment Colors Revert** never silent-gray; **roster Open/Save/Assign/Clear** never silent-gray
  - **APF stock playbook routes** Copy/Swap/Revert never silent-gray
  - **Audio Load waveform** never silent-gray (bank/unavailable rows explain)
  - **Text workspace Apply/Revert** never silent-gray — empty selection, UTF-16
    unit limit, no-change, and nothing-staged walls explain on click
  - **Text Sheet Export/Import** never silent-gray (load/loading walls)
  - **Ratings sheet Export/Import** never silent-gray (load/workspace walls)
  - **Custom Team Appearance Write-raw** never silent-gray (project-vs-raw wall)
  - **Player rating / position Apply/Revert** never silent-gray
  - **Bulk audio complete catalog + original banks** never silent-gray (busy/load)
  - **Export matching sounds / Export decoded rows** never silent-gray
  - **Stadium Reset View + Export scene ZIP** never silent-gray
  - **Roster Replace Name / Revert Name** never silent-gray
  - **Audio Play** never silent-gray (bank/unsupported rows explain)
  - **Audio PCM template / Replace from audio / XMA Replace / Revert** never silent-gray
  - **Audio shortlist construction** never silent-gray (toggle/page/match/clear/review/move/export)
  - **Team Logo Place on helmet** never silent-gray under Retail coverage —
    disableReason teaches Full-shell-only placement (coverage-changed path matched)
  - **Helmet logo placement Save** never silent-gray when art is out of canvas —
    status + accept re-validation teach the wall
  - **All Textures / inventory Previous/Next** never silent-gray (first/last/Load walls)
  - **Complete audio Previous/Next + Export decoded rows** never silent-gray; export_rows clears disableReason when query current
  - **XMA1 encoder wizard Save/Test** never silent-gray (path/Wine/tone-test walls)
- **Field Art “Stock NFL endzones” button** — one-click jump to the ≈118 stock
  endzone family in the ownership map + inventory (browse/export only; focused
  editor still owns the six writable base slots). Unloaded state stays clickable
  and teaches Load first.
- **Blank previews / “Preparing preview…” forever** — AssetBrowser, Uniform,
  Wordmark, digital_font, Team Logo crest, Field Art slots, stadium package +
  embedded TXTR fail closed after **45s** with re-select / Export-raw guidance
  (token/generation-scoped so a newer selection cancels the watchdog).
- **Crib drop-parity hang under offscreen tests** — fit-mode `QInputDialog`
  must be mocked; production drop path already offers Contain/Cover/Stretch.
- **PORTME preview errors** — list full supported PNG format set (incl. DXN
  namefont, format-32 cubemap face-0, linear DXT) + re-select guidance.

### Honesty

- Locked Field Art browse rows still **cannot write** stock NFL endzones;
  they only teach the six proved slots wall.
- Stadium package related-outer rows are not surface-owned; only catalog-
  authorized embedded TXTRs are writable offline.
- Freehand routes still not Editable; G1/G2 still offline-bytes only.

## 0.1.0-alpha.60 — nameplate DXN, linear TXTR, package maps, keyboard/UX — 2026-08-08

### Community issues closed or honesty-labeled

- **Nameplate gibberish (font_albedo / font_normal)** — root cause: base-only DXN
  (`packed_mips=False`). All 11 NameFont packages preview on real 0A. Outer IDs:
  114, 283, 504, 538, 609, 640, 937, 956, 963, 1312, 1383.
- **Jersey numbers discoverability** — `number_0_color`…`number_9_color` 512×512;
  All Textures search teaches these names (Titans-style “missing” often catalog;
  tip says not under shoulder material).
- **Save Players teaching** — Face shield/visor label; Play-by-play ID = VO name
  table (G6 “Number 68…” class); G10/G11 2nd-level charge gate honesty
  (offline tier/abilities editable; XEX gate unproved).
- **Equipment Stage never silent-gray** — stays clickable; Load/filter reasons.
- **Linear / rain textures** — untiled uncompressed TXTR (e.g.
  `crowd_shirt_stripe_color_rain`) PNG-preview instead of linear PORTME.
- **Linear DXT** — untiled DXT1/2_3/4_5 TXTR bases PNG-preview (pitch-padded
  block rows); same BC decoders as tiled path.
- **Helmet shell recommended path** — Team Logos UI teaches Full-shell +
  Normal logo with **opaque shell body α255** (names 0x88 translucency defect).
- **General DXT5A** — coach_hair_occlusion / field_radiance / digit atlases
  beyond digital_font 128×128.
- **Cubemap lightmaps** — format-32 face-0 preview (SpecularLightBox class).
- **Import model silent gray** — buttons stay clickable; click explains Load-game.
- **Equipment Colors** — team filter; HOME kit only / AWAY kit only; per-set teaching.
- **Keyboard** — Ctrl+F / Esc clear search / Ctrl+/ hints; studioSearch markers.
- **G1 package map** — formation `+0x0D` 11-byte role map; experimental offline
  export Package-Map Copy (not a runtime fix pack).
- **G2 menu composition** — formation link-table copy writer + experimental export.
- **Playbook browser** — package-map line in inspector; Ace/Dime/Bear ⚠ annotations.

### Honesty

- G1/G2 offline writers prove **bytes only**; runtime gameplay fix unproved.
- Experimental PLAY exports do not stage project edits or mutate source ISO.
- Freehand routes still not Editable.

## 0.1.0-alpha.59 — community texture/import UX, model tooltips, Field Art honesty, playbook flags — 2026-08-07

### Community issues closed or honesty-labeled

- **Import fit chooser** — `fit_slot_image` offers Contain/Cover/Stretch; wordmark combo includes Stretch.
- **G1/G2 RE spike** — shared `playbook_package_rule_spike` + gameplay map addresses (no fake fix pack).
- **Continuation re-verify** — real `extracted/.../0A` logo_l0/l1 format-15 decode+PNG export; logo patch source-read-only with decode-back max error 0.
- **More Xenos PNG previews** — 8, 1_5_5_5, 5_6_5, 8_8 (plus prior 8888 / 4_4_4_4 / DXT family); PORTME lists supported formats.
- **Playbooks** — filter for ⚠ Ace/Dime/Bear community-flagged books only.
- **Field Art blurb** — names ~118 stock NFL endzones vs six writable proved slots.

- **logo_l0 / logo_l1 format 15 (`4_4_4_4`)** — re-verified; regression tests drive
  shipped `apf_inner.decode_txtr_base_rgba` + PNG write without retail bytes
  (`tests/mod_editor/test_apf_xenos_4444_png.py`). Import/swap remains the
  existing logo writer path (beta-27 decode + offline logo patch).
- **Import resize** — Contain / Cover / Stretch via shared `image_fit`; dialog
  and drag/drop share `fit_slot_image`. Stretch mode added for forced non-aspect
  fits; CLI `tools/nfl_fit_image.py` documents it.
- **Import edited model gray without reason** — helmet/player import buttons now
  always carry a tooltip explaining load-required vs same-topology contract
  (`model_export_qt.set_context`).
- **Field Art stock NFL** — focused editor copy states that ≈118 stock endzone
  packages live in the inventory/All Textures browser; only six offline-proved
  base slots are writable. Wall: `docs/product/APF_FIELD_ART_STOCK_NFL_WALL.md`.
- **Playbook Ace/Dime/Bear warnings** — browser annotations only (no fake fix
  pack). Gameplay map: `docs/product/APF_GAMEPLAY_BUG_MAP.md` (G1–G14).
- **§6.1 ledger** — `docs/product/S61_EDITOR_BUG_WALLS.md` fix-or-wall tracker.
- **Facemask / turtleneck** — remains per-team HOME/AWAY Equipment Colors
  (not global); visor is per-player Save Players type, not a uniform tint.

### Honesty

- No freehand route Editable claim. No per-team endzone writer overclaim.
- Writers remain copy-only with independent verifiers.

## 0.1.0-alpha.55 candidate — whole-shell v24, complete wordmarks/save players, roster truth, and release hardening — 2026-08-04

### Team Logo ownership is explicit in the editor

- The Team Logo panel now labels selector-slot-5 crest index `N` as one linked
  write to `uniform_logo_NN.iff` and frontend/Team Select cache entries
  `N_logo_l0`/`N_logo_l1`. Its status chip, selected-slot ownership line, build
  tooltip, and workspace tab tooltip all disclose the coupled write.
- The same UI identifies selector slot 6 as the independent 206-entry
  rectangular **Wordmarks** bank. Team Logo never stretches or squeezes the
  square crest into that family and does not invent a third logo reservoir.
- The wording keeps the evidence boundary visible: the frontend cache path is
  statically mapped, while changed-logo runtime consumption and the scorebug's
  package-versus-cache resolver remain unproved.

### Complete 206-slot rectangular wordmark editor

- **Logos & Team Art → Wordmarks** exposes the complete independently selected
  `uniform_textlogo_00.iff` through `uniform_textlogo_205.iff` family. The
  selector is typed 0–205 and shows current ROST slot-6 team ownership; it does
  not alias the 118 square Team Logo crest slots.
- File selection and drag/drop accept ordinary image dimensions through
  explicit Contain or Cover fitting to 512×128. Transparency is composited onto
  opaque black to match retail BC1 semantics, and the preview displays the
  exact staged pixels. Replace, per-asset Revert, Revert All, Undo, project
  save/load, and normal Build are fully wired.
- The copy-only writer regenerates the complete six-level tiled BC1 mip chain,
  preserves descriptor, footer, inactive packed-tail bytes, and unrelated IFF
  parts, then fits the H7A streams inside the original fixed allocation. The
  independent verifier reopens the copied `0A` and proves that only the selected
  outer package may differ. All 206 retail targets pass bit-exact no-op compile;
  changed-output and whole-volume tests cover the bounded write.
- This is an offline file-transport proof, not a claim that every consumer or
  Xbox 360 hardware has rendered a changed wordmark. A Team Logo crest is never
  silently squeezed into this different rectangular texture family.

### Verified stock assignment-route copy and swap

- **Playbooks & Plays → Assignment Routes** exposes all 586 MASTER plays and
  their 11 player-assignment slots. A modder can copy one stock assignment or
  swap two assignments atomically. The operation copies the donor's exact
  four-byte descriptor and re-encodes the target field-relative pointer to the
  donor's existing game-authored chain; no route node is edited or relocated.
- The compiler reparses the complete source and output, permits changes only in
  the selected eight-byte assignment fields, preserves the fixed 0x2C750 body,
  route-node blob, names, formations, and the newly decoded MSB-first
  formation-to-play membership table. It also preserves the complete distinct
  assignment-chain start set, refusing a one-way copy that would orphan a
  unique chain and directing the user to a balanced swap.
- `.apf2k8mod` files store only MASTER/play/slot selectors in canonical JSON.
  Build resolves all descriptors, relative pointers, names, and nodes from the
  user's recognized source, token-preserves the H7A block inside fixed outer
  180, reparses it independently, and emits a retail-free receipt. Copy, swap,
  Revert, Revert All, Undo, save/load project, and composed Build share that one
  validation path.
- This is exact stock assignment reuse, not freehand route drawing. Waypoint
  coordinates, route-node opcodes/operands, custom-play save ownership, and
  gameplay/runtime behavior are not claimed.

### Complete APFe-compatible save player editor and verified STFS handoff

- **Rosters & Players → Save Players** opens either a raw `Roster.ROS` or a
  hash-tree-verified `CON ` / `LIVE` / `PIRS` package. It exposes 149 exact
  writable player fields: 31 native base fields, 77 boolean ability bits, five
  motion/style fields, jersey number, dual-byte mirrored position, tier, both
  depth values, body/skin/weight, equipment, PBP/photo IDs, player type, years,
  height, and handedness. Packed writes preserve every non-selected bit; whole-
  pound weight deliberately preserves the low nibble shared with abilities.
- All 15 known player UTF-16 fields are available under their existing
  allocation limits. Shared aliases disclose their owner count, every pointer
  remains exact, and receipts store hashes/limits rather than source or
  replacement text. Membership authoring is deliberately swap-only between two
  populated counted slots, preserving all team counts, the complete player
  multiset, global uniqueness, and the native 42-slot capacity.
- Output is always a new raw payload plus a JSON receipt. The verifier rebuilds
  its authorized byte masks from the semantic edits, reparses the complete save,
  and rechecks field values, text ownership, membership invariants, and source
  identity. Cleanup removes only paths exclusively created by that operation;
  an existing destination is never deleted.
- Signed-package authoring is an explicit handoff, not fake signing. The editor
  verifies the STFS hash tree, extracts `Roster.ROS` read-only, writes and
  independently rereads a raw output, then requires external reinjection,
  rehashing, and resigning with the owner's save manager/keyvault. The same
  verified raw-handoff behavior now applies to **Save Assignments**, superseding
  the older inspect-only wording retained later in these historical notes.
- Overall is not written because the complete position formula tables are not
  proved. Active-capacity expansion beyond 42, arbitrary insertion, and
  game/runtime consumption are likewise not claimed.

### Stadium selected-mesh POSITION round trip

- Stadium Studio now exposes 77 catalog-authorized surfaces in the pinned
  outer-14/inner-8 scene instead of leaving the proved writer hidden. A clicked
  authorized surface can export a source-authenticated POSITION plus
  expanded-triangle glTF and import it into a new copied `1A`.
- Import requires the exact source vertex count and expanded triangles, rejects
  object transforms, materials, skins, morphs, animation and every non-POSITION
  attribute, then requires the independent full-volume verifier. The source is
  read-only; UVs, normals, materials, attachments, topology and unrelated bytes
  remain exact.
- Package texture Replace remains separately locked because material/TXTR
  ownership is still unproved. Runtime visibility and rigid attachment are not
  claimed, and the workflow requires no emulator.

### High-resolution helmet-logo authoring masters

- **Save high-resolution authoring master…** is available beside Team Logo
  import after an external Retail or Full-shell import. Its non-overwriting
  `.2ktexmaster` keeps the exact ordinary-art/advanced-mask source, source hash,
  original-to-contain-to-placement geometry, final X/Y, independent
  width/height, rotation, palette/semantic conversion metadata, exact staged
  512x512 game mask, and a direct 2x or 4x authoring render.
- Built-in pixel painting no longer discards an existing master. The exact
  post-import native canvas is retained privately and later changed pixels are
  applied as a verified nearest-neighbour layer over the direct master render.
  A retail-only Edit does not package retail source pixels as user artwork.
- The output is an authoring sidecar. It is not an RPCS3 texture pack, does not
  increase APF's native texture size, and is not embedded in `.apf2k8mod` v1.
  The separate capability boundary is documented in
  `high_resolution_texture_authoring.md`.

### Whole-shell atlas v24 correction

> **Current truth:** this correction supersedes the alpha.53 carrier and visual
> wording retained below as historical release notes. Those older guarded
> convex-hull/carrier passages are not claims about the current v24 route.

- The full-shell implementation now uses the helmet's exact retail high/low UV
  atlas instead of constructing a mask-shaped overlay disk. Shell vertices,
  indices, UVs, and accessory draws remain exact; draw 1 routes from shell
  material 1 to crest material 2, and the old draw-2 overlay becomes in-range
  zero-triangle degenerates.
- The direct helmet placement canvas retains its semantic 512×512 design with
  fixed physical axes: X maps front-to-rear
  shell Z and Y maps top-to-opening-bound shell Y. Moving artwork therefore
  moves it on the helmet instead of being erased by active-bbox normalization.
- The shared route is transactionally safe for every team. All 118 package l0/l1
  pairs compile and reparse in memory before publication. The selected pair
  receives the bilateral shell atlas, the selected menu-cache pair keeps the
  undistorted semantic design, and all other retail pairs are RGBA-preserving
  migrated from their original side-decal placement. The editor creates one new
  0A only after every fixed allocation passes; no Xenia patch is involved.
- The exact atomically published v24 candidate now has a release-safe visual
  receipt at `docs/mod_editor/apf2k8_full_shell_visual_gate.json`. Its
  independent reopen verified all 118 packages / 236 layers, and its
  deterministic high/low renderer produced ten nonempty side, front, rear, and
  crown views. Visual review of both hash-pinned contact sheets passed: the wing
  reads as one authentic shell-spanning Eagles design with coherent bilateral,
  front, rear, and crown coverage, while the low LOD retains its silhouette
  without visible UV smear, gaps, holes, or seam breaks. This is static
  asset-space proof only; runtime/gameplay consumption and Xbox 360 hardware
  behavior remain unproved.

### Native-material full-shell bake (literal BC1 lane)

- The v24 palette-mask route renders through crest material 2, which lacks the
  shell's DXN normal + specular-lightmap path, so whole-shell designs read
  matte. A second import mode, **native material**, instead repaints the
  helmet package's `helmet_color` texture with literal RGB (BC1, full mip
  chain, deterministic opaque encoder) while the shell stays on material 1 —
  one material and one shading path for body and crest, so the design inherits
  the retail metallic response.
- The semantic 512×512 weight mask is composited over the team shell colour
  (midnight green by default, white/silver inks, same AA fringe) into a fully
  opaque literal canvas; the writer refuses any non-255 alpha because the
  retail shell material has no alpha lane. Shell vertices, UVs, the DXN
  normal, and every unrelated texture byte remain retail.
- The lane is fail-closed on the pinned retail helmet entry and texture
  hashes, rebuilds the H7A transport token-preserving, and publishes one new
  copied `0A` per the archive patch contract. Focused gates pin the opaque
  body contract, the weight-to-literal compositing, and source/structure
  refusals.
- Evidence boundary: the literal lane now has a headless in-game Xenia
  witness (kickoff-lineup frame, PHI huddle: opaque midnight-green shells,
  no translucency; interim sideline crops on the Desktop as
  eagles-helmet-ingame-full/-zoom). A replay-cam or 3D-preview close-up is
  pending an interactive session and will be recorded here once captured.
  The palette-mask lane remains the bounded decal route; neither mode claims
  arbitrary source RGB survives literally.

## 0.1.0-alpha.53 candidate — headless crest pipeline, save assignments, roster parity, and model export 2026-08-03

### Team crests and helmet coverage

- **Custom Team Appearance now owns the missing shell-color path for user slots
  32–39.** HOME and AWAY each expose ten ARGB swatches plus exact helmet and
  crest selectors with unproved bytes labeled opaque. The one-click 2017 Eagles
  preset preserves the helmet model and complete opaque helmet tail, selects
  crest 30 with the complete Xenia-proved crest-routing sequence, and uses
  palette index 8 as `FF004C54` midnight green. The routing bytes remain
  individually unnamed.
- Appearance projects carry canonical replacement-only JSON and compose through
  the same fixed-allocation ROST transaction as names, ratings, and positions.
  The writer re-resolves unique pointer ownership, preserves palette metadata,
  token-preserves H7A, and reparses the complete output.
- **The full-shell route is a normal, headless editor build.** Select the fixed
  `front_crown_to_rear_v1` profile and the editor atomically publishes one new
  `0A`; it creates no Xenia patch and never edits `default.xex`. The exact Eagles
  proof build changed only outer entries **171, 213, 1126, 1133, and 1310**:
  cache directory, cache payload, custom-team appearance, selected crest
  package, and shared helmet geometry. The source stayed read-only and every
  other outer entry stayed exact.
- **The accepted carrier is dynamic, deterministic, and capacity-bounded.** The
  project retains the semantic pre-guard 512×512 design. At build time, exact
  64-pixel sampler guards leave a 384-pixel usable interval; the same guarded
  PNG feeds package and cache. A dynamic convex hull from the imported mask
  drives connected high/low shell-native disks, and the independent verifier
  proves every active guarded texel maps exactly once per side. Unsupported
  masks fail before publication with needed/available vertex and index counts.
- **Full-shell imports now separate painted art from APF weight maps.**
  **Normal logo (recommended)** high-quality-contains ordinary art, asks the
  author to confirm shell plus two rendered detail colours, shows a material
  preview and error metrics, then converts to joint-quantized four-bit red/green
  weights. **APF region mask (advanced)** strictly requires the Xenos nibble
  lattice, blue fixed to zero, a one-unit red/green sum, no hidden RGB under alpha zero, and a nonempty
  mask. Neither mode claims arbitrary source RGB survives literally. The
  converted/validated mask is auto-fitted across a clearly labeled
  **FRONT / CROWN → REAR** guide before staging. Dragging changes X/Y directly;
  independent Width, Height, and Rotation fields handle exact adjustments, with
  **Reset** and **Auto-fit front → rear** buttons always available. The result
  is an exact semantic pre-guard 512×512 RGBA mask. Nearest-neighbour placement
  preserve region-mask palette values, and empty or off-canvas art fails closed.
  Reopening the canvas in the same editing session reuses the normalized
  original import plus its last transform, preventing cumulative resampling.
  The superseded one-shot fit checkbox is hidden and disconnected so it cannot
  silently overwrite manual X/Y placement.
- **The Eagles proof mask retains weighted 4-bit antialiasing.** It uses all 16
  Xenos red/green levels, 7,927 antialiased texels, and 1,833 mixed silver/white
  edge texels instead of reducing the feather edge to flat binary regions. The
  package and cache decode back to the same weighted mask and regenerated mip
  chains.
- **Raw logo-cache verification now reaches the right parser.** The composed
  headless build previously dispatched the directory/payload pair as ordinary
  IFF outer entries. It now recognizes only the typed helmet-crest composite,
  verifies the raw pair with `apf_logocache_verify.py`, then performs the normal
  whole-volume changed-span and atomic-publication checks.
- **Accepted custom teams now have a direct raw-save appearance path.** Switch
  the same panel to **Raw Roster Save**, load a raw `Roster.ROS`, and the editor
  maps user-facing IDs 24–31 to ROST slots 32–39 before exposing HOME/AWAY
  palettes and helmet/crest selectors. It writes only a new payload plus
  receipt, SHA-binds the source, revalidates unique aligned pointer ownership,
  restricts each edit to an exact 112-byte union, and independently reopens and
  verifies the result. `CON `, `LIVE`, and `PIRS` STFS packages can now be
  hash-verified and opened directly: the editor can emit an exact extracted
  `Roster.ROS` or a patched raw handoff plus source-bound verification manifest.
  It never writes or labels that raw output as a signed package. External
  reinjection, rehashing, and resigning remain required; LIVE/PIRS private keys
  are unavailable and CON signing needs the owning console's private keyvault.
  No emulator runtime consumption, gameplay visibility, or Xbox 360 hardware
  parity is claimed by this offline path.

- **All 118 crest packages use one complete product path.** The loaded archive
  resolves `uniform_logo_00.iff` through `uniform_logo_117.iff`; built-in teams
  retain source-derived names and the remaining game-library slots stay labeled
  only by index.
- **One staged 512×512 RGBA crest is mirrored everywhere this bounded workflow
  owns:** `logo_l0` and `logo_l1` in the selected package, plus both matching
  uniform-logocache layers. Both package mip tails and both cache mip tails are
  regenerated from the new base. The old l0-only and preserved/stale-mip
  descriptions no longer apply to Team Logo. Field Art remains a separate
  base-level-only writer and does not inherit this claim.
- **The source stays read-only and the output is new.** The package writer feeds
  the cache writer through a private intermediate copy, the final cache stage
  is independently reparsed across all 236 layers, and whole-volume byte checks
  preserve every unrelated package/cache extent.
- **The final Eagles carrier passes the visual gate.** Exact package, cache,
  guard, appearance, geometry, and source-preservation receipts pass offline
  verification. Strict six-view and native high-side static asset-space review
  found a crisp, coherent Eagles wing spanning the front/crown through the rear
  with no holes, clipping, smear, halo, or floating carrier, plus high/low and
  bilateral parity. The high carrier is 21.80×8.52 cm with 258 faces / 161
  welded vertices; the low carrier is 21.80×8.51 cm with 78 faces / 56 welded
  vertices. No Xenia, Wine, emulator, controller, or FIFO participated in this
  proof, and no runtime consumption, gameplay visibility, scorebug/menu
  ownership, or Xbox 360 hardware parity is claimed.

### Raw-save playbook assignments

- **Save Assignments lists all 40 team slots and all 69 named books:** 36
  offense and 33 defense. Both sides are staged explicitly; multiple teams can
  be staged before one new raw save and manifest are written.
- The source is opened read-only and SHA-bound from inspection to write. Output
  alias/overwrite is refused, exact changed bytes are accounted, the result is
  reparsed, the name table and unrelated bytes are checked unchanged, and a
  separate verification pass confirms the output. Synthetic fixtures remain
  green. A private raw-save witness also parsed all 40 teams / 69 books, changed
  slot 32 offense 25→13 and defense 56→32 in exactly two assignment fields /
  three bytes, independently reopened to IDs 13/32 with the book table unchanged,
  and reverse-patched to the byte-exact original.
- **Signed Xbox CON stays inspect-only.** Safe container writeback additionally
  needs extraction, reinjection, STFS rehashing, and resigning; the editor
  refuses rather than creating an invalid container.
- This selects existing books. The separate on-disc **Assignment Routes** tab
  now copies or swaps exact stock descriptor/chain assignments inside
  `playbook_master.iff`; formation membership is decoded for inspection.
  Freehand route nodes, new plays/formations, and DRCT instructions remain
  read-only. Signed-STFS reinjection/rehash/resign and assignment gameplay
  consumption remain unproved. PB means playbook; player PBP is the distinct
  play-by-play announcer identifier.

### Paired stock roster audit

- The RPCS3 and Xenia APFe exports each contain 1,344 rows. Their 169-field
  header describes 177 positions, repeats `RunCoverage`, and leaves eight
  trailing fields unnamed, so the audit disambiguates duplicates and preserves
  the unlabeled positions instead of inventing semantics.
- Every `TeamJerseyBytes` difference is explained by the exact bounded
  RGBA-to-ARGB platform serialization. After that normalization: **1,312
  equivalent, one stock identity variant, 31 randomized Atoms fillers, zero
  unexplained**.
- The stock identity variant is RPCS3 **Mike Haynes** versus Xenia **Mark
  Smith**. Only First, Last, College, DOB, Number, Photo, PBP, and Age differ;
  equipment, ratings, and skills match positionally.

### Helmet and player same-topology POSITION import

- **Uniforms & Equipment → Model Export** exposes exact cards for helmet
  `outer 1310 / inner 128 / helmet_00` (33 meshes) and player
  `outer 1310 / inner 273 / player` (one mesh).
- Each export reads the source archive only and creates new `.gltf`, `.bin`, and
  source-bound v2 `.apf-model.json` files.
- A paired import action now accepts same-count POSITION edits, requires exact
  source expanded triangles, preserves the fourth POSITION component and every
  non-position/skin/attachment byte, rebuilds H7A inside the fixed allocation,
  independently reopens it, and publishes a new `0A` plus receipt.
- Changed topology or vertex count, materials, texture bindings, normals,
  packed tangent/UV data, skin/rig editing, helmet/head attachment authoring,
  animation, collision, SpeedFlex/F7 replacement molds, and runtime visibility
  remain unavailable or unproved.

## 0.1.0-alpha.52: give every team its own uniform, and drop ordinary audio 2026-07-30

### Team Independence

- **Every built-in team can now own its uniform textures.** APF's forty teams
  draw helmets from only **six** textures, socks from six, numbers from seven,
  jerseys from nine. That is why painting a wing on one team's helmet put it on
  other teams too, and why the standing advice was that this was as good as it
  got. A new **Team Independence** tab on Uniforms & Equipment writes a new `0A`
  in which each team points at its own: helmets go 6 to 24, jerseys 9 to 24,
  numbers 7 to 24, socks 6 to 24, pants 11 to 24, shoulders 14 to 24, fonts 7
  to 11. Ninety-five team assignments change in total.
- **The game already had the room.** Twenty-four helmet packages ship and only
  six are referenced; the other eighteen sit complete and unused. Nothing is
  added, teams are simply pointed at slots that were already there.
- **You can now see who shares a texture before painting it.** The tab lists
  every helmet with the teams currently using it by name, and marks unused ones
  as free to take over. Helmet 01 alone is worn by sixteen teams.
- **No artwork is altered and your game is not modified.** Only selector bytes
  change, so helmets look identical until you edit them, and the loaded volume
  is opened read-only while a new one is written.
- The underlying writer is unchanged and still refuses any plan but the frozen
  one it derives from the pinned allocation report. This release exposes it; it
  grants no new write authority. Runtime visibility and Xbox 360 hardware
  acceptance remain unproved, and the panel says so.

### Audio

- **The audio drop target and both choosers now accept ordinary audio files.**
  The product contract becomes `selected_exact_slot_xma1_or_conformed_audio`
  and the target is labeled **Drop .xma or audio file here**. WAV, MP3, FLAC,
  OGG, M4A and similar are converted to the selected slot's exact channel
  count, sample rate and frame count before encoding, so a replacement no
  longer has to be shaped by hand in an audio editor first.
- **A file that already matches the slot exactly is passed through untouched.**
  Not re-encoded, not rewritten, not copied: anyone who prepared a precise WAV
  keeps byte-for-byte control, and the path that shipped before this is
  unchanged.
- **Nothing downstream was relaxed.** Conversion sits in front of the existing
  importer, so whatever it produces still faces the link-count, RIFF-structure,
  five-way shape and exact-data-size checks, then the full exact-slot
  allocation, packet, complete-decode, source-reuse, target and alias contract.
  A file that cannot be converted is handed to the encoder unchanged, so its
  original refusal message is preserved rather than replaced.
- **External XMA1 output is now compared with the authored PCM before it can be
  staged.** The editor decodes the encoder result, searches the decoder's
  bounded 127-frame alignment window, and rejects collapse/silence, wrong
  rate/pitch, channel swap/interleave, gross level changes, new sustained
  clipping, excessive DC, and corrupt tails. Failure reaches neither the exact
  slot writer nor the edit map. Direct pre-encoded `.xma` remains byte-preserved
  and does not pretend to have an unavailable authored-PCM reference.
- **The `.xma` route is unchanged and is still the only one that re-encodes
  nothing.** The Xbox 360 stores this game's audio as XMA1 and no
  redistributable XMA1 encoder exists: FFmpeg decodes `xma1`/`xma2` and
  encodes neither: so the final encode still uses the encoder the user
  configures. Dropping an already-encoded `.xma` remains lossless.
- **Conversion quality is deliberate rather than incidental.** Resampling uses
  soxr at high precision instead of the default resampler; both the mono and
  stereo mixes are stated explicitly, because FFmpeg's implicit `-ac` downmix
  does not normalise consistently across sample formats (measured on 6.1.1:
  `(L+R)/2` for `s16le` but `(L+R)/√2` for `f32le`); the decode stays in float
  so resampler overshoot is measured before it can clip; and a trim fades
  briefly into the cut so it does not click. Every change is reported to the
  user rather than applied silently.
- Requires FFmpeg on `PATH` for conversion only. Without it, exact files still
  work and anything else is refused with an explanation.

## 0.1.0-alpha.51 — the executable answers three open questions 2026-07-30

One session's work, kept as one entry: decrypting `default.xex` settled the rating
labels, closed the crest-rectangle question, and unlocked `endzone_l0`.

### Player ratings

- **All 31 rating bytes are editable, up from 28, and all 27 names now come from
  the executable rather than inference.** `tools/xex_extract_pe.cpp` decrypts
  `default.xex` into its 54 MB loaded image, which contains an **attribute
  descriptor table at `0x820E4D94`** — 27 records of stride `0x60`, each holding
  the UI abbreviation at `+0x00`, the display name at `+0x0C`, and a pointer at
  `+0x18` to that attribute's own setter. The setter's `stb` displacement names
  the byte, decoded from instruction words for all 27 records.
- **The name-to-byte mapping this project already shipped was correct.** All 27
  pairings match. `Pass Read Coverage` is `0xC9`, `Composure` is `0xD5`,
  `Consistency` is `0xD7`, `Kicking Style` is `0xD1`, `Leadership` is `0xD3`,
  `Kick Accuracy` is `0xD0`, `Aggressiveness` is `0xD8`.
- **What is new: `0xBD`, `0xC5` and `0xD2` are now editable fields** instead of
  excluded neighbours, and all four unnamed bytes (`0xBD`, `0xC5`, `0xD2`, `0xD4`)
  carry a neutral label. No descriptor record points at their setters, so the
  game's own UI has no name for them and none is invented. `0xD4` is the odd one
  out — it owns formula slot 24 and a getter but no UI string, which is exactly
  the "hidden rating" earlier notes described. The Base Ratings tab lists 31 rows
  and the private CSV exports 31 columns.
- **An APFe-derived relabelling was applied and then reverted the same day.** Its
  `SFLSettings.csv` row *order* genuinely is the record's byte order (11 slots
  reproduce all 61 stock Gold players exactly across 17 positions, a result that
  stands), but its row *names* are misassigned, and its Attributes panel
  contradicts its own CSV on three passing attributes. Per-position "this profile
  looks like X" reasoning on top of that produced six confident wrong names. The
  write-up keeps the whole path, including the wrong turn:
  `docs/research/apf_rating_slot_settlement.md`.
- **Not every one of the 31 bytes is a 0–99 magnitude, and the writer now knows
  the difference.** Read off the 1,437 stock records with a populated block:
  `Kicking Style` (`0xD1`) holds 49 at every field position with 99 for the 30
  kickers and 1 for the 30 punters, and `0xD2` holds 0 in 1,433 records and 1 in
  2. Both are indices, so an unobserved value is refused in
  `validate_field_value` — at the writer, so the desktop panel, the ratings CSV
  and the CLI are all covered. `Leadership` (`0xD3`, constant 50 everywhere) and
  `Consistency` (`0xD7`, 99 in 1,435 of 1,437) are recorded as constants but
  deliberately *not* blocked: APF shipped them unvaried, so writing them is
  pointless rather than dangerous. Every field carries a `value_domain` and, where
  the set is small, `observed_stock_values`.
- Caveat for anyone parsing an APFe export: `RunCoverage` appears twice in the
  header, the header names 169 of 177 fields, and past the rating block the names
  are shifted off their data — `SpecialTeamDemon` flags 12 quarterbacks and 4
  punters. Only the 31 rating columns are trustworthy, and only positionally.

### Field art

- **`endzone_l0` accepts edits.** It was refused before: forbidding the
  overlapping H7A matches that caused the crest speckle cost the headroom, and
  greedy overran the fixed allocation by 21 bytes at 32x32 and 9 at 8x8. The
  minimum-cost parse recovers ~585 bytes on that block, which is more than the
  shortfall, so the money asset now carries the same 2048x512 DXT1 coverage as
  its sibling. The no-overlap rule did not move. Linux x86-64 releases now ship
  the exact reviewed minimum-cost helper, validated by type, link count,
  permissions, size, SHA-256, and decode round-trip, so users do not need a C
  compiler for this safe fit path.
- **Fixed a quadratic walk in the minimum-cost encoder** that made it unusable on
  the data it exists for. It started each candidate walk at the newest position
  holding a 3-byte key anywhere in the file; the dynamic-programming pass runs
  backwards, so most of that chain sat above the current position and got skipped
  with a bare `continue` that never reached the candidate cap. On texture data one
  key dominates, so the cap bounded nothing: the 1.44 MB endzone block ran past
  six minutes without finishing and looked like a hung test suite. It now records
  the newest *earlier* position per key, so every visited link is a legal
  candidate — **28 seconds** for the same block and the same output.
  `compress_h7a_best`'s subprocess ceiling dropped 900s to 180s so a pathological
  input takes the greedy fallback instead of stalling its caller.
- Measured the real budget, in `docs/research/apf_h7a_allocation_budget.md`: a
  900x220 painted region tolerates **16 distinct 4x4 blocks** with this parse and
  12 with greedy. Flat paint compresses *better* than the art it replaces, so a
  solid wordmark has thousands of bytes spare; gradients and photographic detail
  will not fit at any parse quality, which is a data-entropy ceiling rather than
  an encoder limit.
- `tests/apf_h7a_optimal_is_bounded_test.py` pins the consequence: a 256 KB block
  of one repeated key must encode in under 20 seconds and round-trip. The
  endzone-refusal test now uses an edit that genuinely cannot fit, so the
  fail-closed path stays covered.

### Crest slots

- **The crest editor now offers all 118 of the game's logo slots, up from 24.**
  APF ships `uniform_logo_00.iff` through `uniform_logo_117.iff`. Twenty-four are
  worn by built-in teams; the other ninety-four are the game's own selectable logo
  library — the "swappable options" a modder described cycling through in the
  in-game uniform editor while asking how to get more of their art onto helmets.
- This was a **catalog limit, not a writer limit**. `build_patch` already took
  `entry_index` as an ordinary parameter and consulted `PINNED_ENTRIES` only via
  `.get()`, so unpinned slots were permitted all along; and
  `tools/apf_logocache_patch.py` has always declared `CATALOG_COUNT = 118`, so the
  runtime aggregate catalogues every one. Confirmed by building a real patch
  against the unmapped `uniform_logo_00.iff` (outer entry 363) beside the
  Americans control.
- Slots are **resolved from the user's own archive** by CRC32 of the uppercase
  filename, not from a typed table. The packages are scattered — slot 0 lives at
  outer entry 363 while slot 30 is at 1133 — and a hand-written list of a
  hundred-odd indices is a list someone can get wrong. The picker starts as the
  twenty-four teams and widens once a game is loaded.
- **Library slots are labelled by index, never given invented team names.** That
  they are writable is proved; which picker position a given slot backs in game is
  not, and the label says only what is known.
- Unchanged deliberately: the sixteen absent team *selectors* that alias to
  `uniform_logo_80` and own no art of their own. That is a different question from
  these packages and they stay out.

### When something goes wrong

- **An unexpected error now tells you what happened.** Previously the window
  simply closed: Qt ends the process when an error reaches it and no handler is
  installed, and the editor runs from an icon with no console, so nothing was
  shown anywhere. There is now a message naming the problem, stating that your
  original game files were untouched, and giving the path of a log file to
  attach to a bug report. The editor keeps running. A fault that repeats is
  logged every time but only interrupts once.
- **A game folder or ISO that has been moved or deleted is refused in words.**
  Picking one from a recent list after moving it used to raise a raw system
  error instead of a sentence.
- **Broken and unrelated disc images already refused cleanly, and now say so
  consistently.** An empty file, a partial download, an archive renamed to .iso,
  a folder without `0A`, and a disc for a different game each report what was
  actually wrong rather than failing generically.

### Stadium glTF units

- **Exported stadium glTF now opens at a sane size in Blender.** APF authors
  geometry in centimetres and glTF's unit is the metre, so an unscaled export
  arrived ~100x too large — a stadium spans ~17,759 units, well past Blender's
  default 1000 m clip distance. A modder reported it as "not sure if the gltf is
  loading correctly on blender", with a screenshot of a mesh filling the viewport.
- The conversion is **one root node scaled by 0.01**, not a rewritten buffer.
  `scene.bin` stays byte-identical game data, which the static topology
  conformance spec depends on, and the position writer's recipe still declares
  `coordinate_space` as the const `serialized_scne_object_space` — pre-scaling the
  buffer would have put the export and the writer in different spaces.
- **The trade-off is stated in the file rather than left to be discovered.**
  Anything read out of a viewer is now in metres while a recipe must be in raw
  object space, so `asset.extras.coordinate_contract` records the exact factor and
  says to multiply by `1 / linear_scale`. Both export paths share one contract
  helper so they cannot drift apart, and mesh nodes still carry
  `raw_coordinates: true`.
- Verified on the real stadium scene: one root, all 89 mesh nodes parented to it,
  buffer still reading raw centimetres, and the scaled extent landing in the tens
  of metres. `tests/apf_gltf_units_test.py` pins that the declaration matches what
  the wrapper actually does — metadata claiming a conversion that was not applied
  would be worse than none.
- **Not verified by me:** the Blender round-trip itself. Re-exporting from Blender
  may bake the root scale into vertices, so anyone building a recipe from a
  Blender export should check the magnitudes before trusting them.

### Skeleton / SCNE geometry

- **`tools/apf_scene.py` was attaching every joint's vectors one record late, and
  committed bone values were wrong because of it.** The joint table has no `0x20`
  header: each `0x30` record is
  `[absolute vector][parent-relative vector][name/crc/parent/child/sibling]`. Both
  the old and new models put the name block at the same address, so names, CRCs
  and the child/sibling topology always validated — only the vectors moved, and
  they moved to the *next* record.
- Two things that looked like findings were artifacts of it: "the serializer omits
  the two float4 payloads from the terminal record" (there is no record *count+1*
  to borrow from) and an eight-word table header (actually record 0's two
  vectors). Total table length is identical either way, which is why the bounds
  check never caught it.
- Settled by measurement, not argument. Scoring
  `relative(i) == absolute(i) - absolute(parent(i))` across **1,303 scenes and
  25,615 relations**: the old layout satisfied **9,029 (35.2%)**, the corrected one
  **25,614 (99.996%)**. `player_shadow` 20/20, stadium 47/47. The single exception
  is a retail parent-index anomaly, not a layout problem.
- Published values corrected: `apf_named_head_y` was `46.4520`, which is
  `r_clavicle`; `head` is **63.86804**. `apf_named_right_knee_y` was `-94.96063`,
  which is `r_ankle`; `r_knee_hinge` is **-49.97603**. Neither was hardcoded, so
  fixing the parser fixed them. The skeleton now reads anatomically.
- Corroboration: the recorded note that `0x84B0FB4C` "adds hierarchy record `+0x10`
  XYZ" only makes sense under the corrected layout, where `+0x10` is the
  parent-relative vector.

### Crest / shader interfaces

- **Task #10 is closed: the crest UV transform is pixel-shader constant `c29`.**
  Three `ps_3_0` variants declare it as `ReverseLogoScaleAndOffset`, a single
  `float4`, and all three carry the compiled default `(1, 1, 0, 0)`. It is not in
  any asset, so no texture edit can move it — which is why the crest box never
  responded to art changes.
- **The name points at the mirrored side, but that is not proved.** The constant
  is called *Reverse*, so the shader has a notion of a reversed helmet side and a
  UV transform for it — the obvious way to draw one crest on both sides. Its
  compiled default is identity though, so a mirror only happens if the engine
  overrides `c29` at draw time. Catching that write is task #11; until then no
  claim is made about the "wings are backwards" report.
- **New tool: `tools/apf_xex_shader_interfaces.py`.** Point it at the decrypted
  image from the already-vendored `tools/xex_extract_pe.cpp` and it reports every
  shader constant interface — name, register set, register index, count and
  compiled default. **130 constant tables** are present. It prints an interface
  report only; no shader bytecode or texture bytes are read out.
- **The region-colour scheme is declared outright**, where it had only been
  measured by painting test patterns and reading screenshots. Shader `84E95944`
  binds `RegionMap` next to `Region0Weight`…`Region5Weight` and the same
  `Palette[6]` at `c12`–`c17` as the crest shader, plus `WeaveMap` and three
  wrinkle-normal maps. Six regions, six palette entries, six weights. Seven
  shaders bind a `RegionMap`.
- **Do not patch `c29` by register number.** The crest and cloth shaders are
  register-compatible variants of one material — same `Layer0`/`Layer1` samplers,
  same `Palette` range, same lighting registers — but `c29` is
  `ReverseLogoScaleAndOffset` in one and `WeaveRepeat` in the other (and `c26`,
  `c27`, `c31`, `c36` are likewise reused). A register-global patch would set
  fabric weave repetition to a UV transform. Any executable patch has to be scoped
  to the bound shader.
- Still open (task #11): which engine code writes `c29`, and with what values per
  side. The compiled default is identity, so a mirror is either an engine override
  or happens elsewhere; candidate mirror `float4`s exist in the image but cannot be
  attributed without tracing the writer, so nothing is claimed either way. A
  promising lead: `Layer0` appears as a plain string in the raw `0A` archive with
  H7A-mangled fragments of the same constant names around it, so reflection tables
  exist on the asset side too. If the crest shader is reachable as an asset, editing
  it beats patching the executable outright.

## 0.1.0-alpha.50 — rating-slot research 2026-07-28

> **Superseded by alpha.51:** the predicted shift did not exist. The shipped
> mapping was already correct; APFe's labels are misassigned.


- No behaviour changed. APFe's own `SFLSettings.csv` lists 31 attributes in a
  fixed order that maps 1:1 onto the player record's `0xBA`..`0xD8`, scoring
  0.649 against Star-tier defaults where our current ordering scores 0.436 --
  identically on two independent roster files. Our three unnamed bytes are
  where APFe places PassArmStrength, Aggressiveness and KickStyle. The registry
  is not rewritten until a save-diff confirms it; the write-up states the exact
  prediction that experiment should produce.

## 0.1.0-alpha.49 — draw on the crest in the app 2026-07-28

- **Edit…** on the team-logo panel opens the crest at its exact 512x512 size:
  pencil, eraser, fill, eyedropper, full colour picker with alpha, and zoom to
  16x with a pixel grid. No resize control exists, so the saved result always
  fits. Transparency is drawn over a chequerboard so an accidental hole is
  visible before you build.
- `tools/nfl_fit_image.py` converts images to an exact size from a terminal,
  one file or a whole folder at a time.

## 0.1.0-alpha.48 — helmet crests accept any image 2026-07-28

- **The team-logo panel refused anything that was not already 512x512.** A
  crest pulled from anywhere never is, so helmet-logo work died on that dialog.
  It now offers to resize, keeps the whole shape by padding rather than
  cropping, accepts JPEG and friends as well as PNG, and says exactly what it
  did. Your original file is never modified and the proved writer still gets an
  exact 512x512 RGBA PNG.

## 0.1.0-alpha.47 — no APF change 2026-07-28

- Version parity only. No APF behaviour changed.

## 0.1.0-alpha.46 — no APF change 2026-07-28

- Version parity only. No APF behaviour changed.

## 0.1.0-alpha.45 — no APF change 2026-07-28

- Version parity only. No APF behaviour changed.

## 0.1.0-alpha.44 — no APF change 2026-07-28

- Version parity only. No APF behaviour changed.

## 0.1.0-alpha.43 — no APF change 2026-07-28

- Version parity only. The 2K5 side fixed a stale on-screen version and three
  capabilities its Uniforms page never rendered; APF behaviour is unchanged.

## 0.1.0-alpha.42 — the PNG importer accepts real PNGs 2026-07-28

- The shared PNG importer demanded colour type 6 at bit depth 8, non-interlaced,
  and refused everything else. Every standard colour type and bit depth is now
  decoded and widened to RGBA internally.

## 0.1.0-alpha.41 — shared registry row count 2026-07-28

- No APF behaviour changed. The shared capability registry gained NFL 2K5's
  general texture lane, so the APF runtime gate's shared row count moved from
  66 to 67. APF's own 34 capabilities are unchanged.

## 0.1.0-alpha.40 — the game partition is found, not guessed 2026-07-28

- **A legally dumped disc could be refused with "does not appear to be a valid
  xbox iso image."** The bundled `extract-xiso` probes exactly four partition
  offsets -- `0`, `0x0FD90000`, `0x02080000`, `0x18300000` -- and rejects the
  image when none of them carries the XDVDFS magic. That is the same defect the
  2K5 source lane was fixed for, hidden inside a vendored binary: a layout
  measured on one machine treated as the only legal layout.
- The disc is now read with the project's own XDVDFS reader first, which
  *searches* sector-aligned positions for the magic and confirms a candidate by
  requiring it at both ends of the header sector plus a root directory that
  fits inside the image. `extract-xiso` remains a fallback, so no layout that
  loaded before can stop loading.
- **A disc for another console is now named instead of called invalid.** The
  report that prompted this was the PlayStation 3 release of the same game,
  named `.iso`; the old message reads as a bad dump, so the reporter re-dumped a
  disc that was fine. ISO 9660 volumes, PS3 discs, STFS packages and ZIP/RAR/7z
  archives are identified by structure and reported by name.
- Only the six files the editor reads are extracted, so the supported USA dump
  now resolves in about 26 seconds and 3.9 GB instead of unpacking the whole
  7.8 GB disc.
- The bundled extractor is no longer resolved before any image is examined, so
  an installation missing it can still open a disc the native reader handles.
- The private extraction cache is published through `platform_compat` rather
  than `os.replace` on a directory -- the POSIX-only idiom behind the RC36
  Windows folder-export failure, in a second place.
- No capability, writer contract or identity ledger changed. The per-file
  ledger (0A/0B/1A/1B and default.xex, by exact size and hash) is still the
  identity check, and all six files come out byte-identical to it.

## 0.1.0-alpha.39 — a disc image is identified by its contents 2026-07-27

- Selecting an APF disc image no longer requires the whole container to hash to
  the project's own rip. The per-file ledger (0A/0B/1A/1B and default.xex, by
  exact size and hash) already ran immediately afterwards and is the stronger
  check; the container gate simply refused legal dumps before it could. The
  container hash is still recorded and still keys the extraction cache.
- No capability, pin or writer contract changed.

## 0.1.0-alpha.38 — generated text is LF on every platform 2026-07-27

- Every shipped module now pins the line ending when it writes text. Text mode
  on Windows rewrites `\n` as `\r\n`, so any file this product generates and
  later hashes or size-checks could not match there. 38 call sites across 29
  files; the shipped surface is at zero unguarded text writes and a test holds
  it there.
- The failure that exposed this was on the 2K5 side, but the defect was
  repo-wide, so the APF writers and reports are covered by the same sweep.
- No capability, pin or writer contract changed. Binary writes were never
  affected.

## 0.1.0-alpha.37 — sibling imports work on installed Windows copies 2026-07-27

- Fixed `ModuleNotFoundError` from the shipped `tools/*.py` on installed Windows
  copies. Those scripts import each other, and the embeddable CPython the
  installer ships defines `sys.path` from a `._pth` file without adding a
  script's own directory the way every ordinary interpreter does.
  `apf_texture_patch` and `apf_roster` were among those affected. Never
  reproducible from the tarball, from source, or in CI — only after installing.
- Each shipped tool now restores its own directory, and the `._pth` lists
  `app\tools` as a second, independent guard. No capability changed.

## 0.1.0-alpha.36 — failed builds clean up after themselves on Windows 2026-07-27

- Fixed cleanup after a failed write. Every writer unlinked the partial output
  while its descriptor was still open, which is correct on Linux and impossible
  on Windows, where the OS refuses to unlink a file anything still holds open.
  The error was swallowed, so a failed build left a stray file behind and the
  *next* build then refused to overwrite it, for no reason the user could see.
- Found by an outside contributor's test, not ours: every test that reaches this
  path needs retail data no CI runner has. `apf_field_art_patch`,
  `apf_logo_patch` and `apf_texture_patch` were all affected.
- No capability, pin or guarantee changed.

## 0.1.0-alpha.35 — the texture writers run on Windows 2026-07-27

- Fixed the crash that made **every APF texture writer unusable on Windows**.
  Field art, team logos, the logo cache, the generic texture writer and uniform
  mips all failed before doing any work with
  `AttributeError: module 'os' has no attribute 'O_CLOEXEC'`. That flag does not
  exist in CPython on Windows, and four writers passed it to `os.open` as a bare
  attribute instead of `getattr(os, "O_CLOEXEC", 0)` — the form 284 other sites
  in the tree already used. Reported by a user against the ordinary "export and
  replace field endzone" flow.
- **No capability changed and no guarantee was weakened.** The registry stays at
  65 capabilities with every ladder position untouched. The flag falling back to
  `0` on Windows costs nothing: PEP 446 makes every descriptor CPython creates
  non-inheritable on every platform, so close-on-exec is the interpreter's
  guarantee, not this flag's. Descriptor ownership, inode-identity checks and
  fail-closed refusals are byte-for-byte what alpha.34 proved.
- Nothing was ever at risk on the affected machines. The failure landed in the
  output reservation, after the read-only preflight and before any output
  existed, so no file was written at all — the refusal dialog's "the original
  game was not modified" understated it.
- Added `tests/mod_editor/test_shipped_tools_posix_only.py`, which needs **no
  retail data**. Every existing test over these writers is gated on extracted
  retail data no CI runner has, which is exactly how a Windows job could report
  parity with Linux and macOS while never executing one `os.open` inside a
  writer. The new file scans both release allowlists for bare POSIX-only
  `os.open` flags and, with those names deleted from `os`, drives every shipped
  writer's real reservation path — asserting the fail-closed refusal still
  refuses for the right reason. Targets come from the allowlists, so a writer
  added later is covered without editing the test.

## 0.1.0-alpha.34 — project-backed Audio cue labels 2026-07-20

- Added the product contract
  `project_metadata_only_stable_logical_cue_id` for all 47,775 playable APF
  cues: 2,261 standalone AUDO sounds plus 45,514 individual AUSB substreams.
  Each stable logical cue ID can own one user-authored custom title of up to 120
  characters and/or multiline note of up to 2,000 characters. Container-only
  AUSB index and physical-bank rows remain ineligible.
- Added **Your cue label & notes**, **Save label**, **Clear**, immediate
  title/note search, and **Labeled only** to the Audio workspace. Original
  catalog identity remains visible; a custom title changes presentation and
  discovery metadata, never the cue coordinate or replacement target.
- Added deterministic `audio-annotations.json` persistence with exact schema,
  count, size, and SHA-256 binding inside `.apf2k8mod`. Annotation-only projects
  are valid. Labels and notes participate in recovery, project load, Undo,
  Clear, and Revert All without becoming buildable audio edits.
- Kept annotations outside the game-build document and modified-asset count.
  They never add a Modified badge, enable Build by themselves, enter an APF
  archive, or authorize audio replacement. The bounded metadata accepts no
  retail audio, decoded PCM, source path, preimage, rollback byte, or packet.
- Carried the custom title, note, and preserved game/catalog name into bounded
  Audio collection export metadata. Playlist display names prefer the custom
  title while stable cue IDs and payload paths remain unchanged.
- Alpha.34 release hashes, final test counts, clean-stage runtime exercise, and
  sealed-package metrics remain pending until the concurrent core and GUI
  implementation freezes. Alpha.33 remains preserved unchanged.

## 0.1.0-alpha.33 — selected-sound Audio drag and drop 2026-07-20

- Added the product contract
  `selected_exact_slot_xma1_or_pcm16_wav` and a visible **Drop .xma or exact
  PCM16 .wav here** target for every individually editable standalone AUDO and
  AUSB substream row.
- Routed `.xma` drops through the same advanced standalone/AUSB exact-slot
  writers used by **Replace with XMA1…**. Routed `.wav` drops through the same
  configured external-encoder bridge and cancellable validation used by
  **Replace from PCM WAV…**. Buttons and drops therefore share one mutation
  path rather than implementing parallel writers.
- Captured the selected row and export identity before starting background
  work. Every Audio mutation/template control disables immediately at PCM,
  direct-XMA1, or replacement-pack submission and returns only after the product
  runner unregisters that worker. Rejected admission is explained instead of
  silently losing an accepted-looking drop or chooser action; failure,
  cancellation, or a stale/unsupported target stages nothing.
- Limited admission to exactly one local regular non-symlink `.xma` or `.wav`.
  Folders, remote URLs, multiple files, and other extensions are refused. The
  drop target does not bundle an encoder, accept FLAC/MP3, bypass exact-slot or
  source-reuse gates, modify the source, or add retail bytes.
- Alpha.33 carries forward Alpha.32's
  `fully_validated_read_only_preview_then_explicit_apply` batch contract.
  Its final stage, clean extraction, runtime/release/desktop/shell gates,
  deterministic rebuild, complete APF suite, combined cross-title suite, and
  independent review pass. Alpha.32 remains preserved unchanged.

## 0.1.0-alpha.32 — validated Audio pack review candidate 2026-07-20

- Replaced the one-click batch-audio import hand-off with the product contract
  `fully_validated_read_only_preview_then_explicit_apply`. **Review replacement
  folder…** and **Review replacement ZIP…** now validate the complete supplied
  pack before presenting an explicit, default-Cancel Apply decision.
- Added a sanitized preview receipt containing only the selected pack path,
  input/count metadata, and an opaque confirmation token. It reports template
  targets, supplied files, would-change, already-current, missing, current
  modified-audio, resulting modified-audio, and validated counts. It exposes no
  audio bytes, decoded source names, source fingerprint inventory, extracted
  ZIP member path, or authored-member digest.
- Bound Apply to the exact reviewed outcome. The private HMAC confirmation
  covers each supplied member hash, each fully validated packet-result hash,
  manifest/baseline identity, loaded-source hash, a private loaded-session
  nonce, and the current project-audio revision. Apply reopens and revalidates
  the folder or ZIP; changed payloads, changed encoder results, a different
  session, or intervening audio edits refuse atomically and require a new
  review.
- Kept review read-only. Preview-created unreferenced packet cache is discarded;
  Cancel stages nothing and adds no Undo action. An unchanged-only pack is a
  successful review with **Apply** unavailable rather than an import error.
  Confirmed real changes still enter the project as exactly one Undo action.
- Routed the review/Apply continuation through the product worker-idle barrier.
  The barrier retains the continuation while any worker is registered and
  releases it only after the preview worker and audio-import lifecycle signals
  drain, so confirmation cannot race a still-busy runner. Existing source/session
  locks, cooperative encoder cancellation, stale-baseline checks, atomic state
  swap, and last-build invalidation remain in their established owners.
- This release changed no audio template schema, runtime dependency, release
  allowlist, encoder policy, or retail-data boundary. Alpha.32 was sealed after
  its complete APF and cross-title suites, clean stage/extraction gates, and
  deterministic rebuild passed; Alpha.31 remains preserved unchanged.

## 0.1.0-alpha.31 — Add-all-matching and safe Audio teardown 2026-07-20

- Added **Add all matching (N)** to the Audio shortlist. It uses the exact
  applied search/kind/role/source query—or the active Soundtrack album—rather
  than only the current 100-row page. Already selected rows are skipped and
  new rows retain stable game-catalog order.
- Kept the 256-sound shortlist boundary atomic. If all new matches would not
  fit, the button and its accessible description show the required and
  remaining counts; activating it explains the limit and adds nothing. A
  successful add clears the one-level Clear/Undo snapshot as one deliberate
  shortlist mutation. It starts no worker, writes no project, and never copies
  audio bytes.
- Cached one exact matching-row result per applied query/model epoch or
  Soundtrack version. Selecting rows and updating shortlist buttons therefore
  do not repeatedly rescan the complete 47,814-row Audio model; changing the
  query, model, or game invalidates the cache.
- Closed source-switch and application-close teardown around request-owned
  Audio readers. A running preview or waveform request is cancelled, its
  worker is allowed to drain, and only then may the loaded session/cache close
  or a replacement source begin indexing. Rapid source selections coalesce to
  the latest request. A late result cannot touch a closed session.
- Preserved blocking build/export safety and Alpha.30's true FFmpeg/ffprobe
  process-group cancellation. Alpha.31 adds no encoder, source audio, retail
  bytes, private source path, project payload, or desktop interaction.

## 0.1.0-alpha.30 — interruptible Audio preview and waveform decode 2026-07-20

- Changed **Play** to **Cancel preview** while APF is preparing a private WAV.
  A click, selected-row change, source/model change, or page transition now
  signals the exact request-owned cancellation token. The button reports
  **Cancelling…** until that worker drains; cancelled and stale success/error
  results are silent and can never start a player for another row.
- Made cancellation reach the actual decoder rather than only suppressing its
  eventual result. Original AUDO, original AUSB substreams, staged standalone
  replacements, and staged streaming replacements all carry the optional
  callback through facade, session, private asset I/O, and exact-slot tools.
  FFmpeg and ffprobe run as new process-group leaders in this path; Cancel or
  timeout sends TERM, drains briefly, escalates to KILL when required, and
  verifies that detached helpers in the owned group are no longer running.
- Added the same owned cancellation to **Load waveform**. During a decode the
  control becomes **Cancel waveform**; selection changes and explicit Cancel
  stop FFmpeg/ffprobe before the bounded PCM envelope reader runs. Waveform
  loading still never autoplays or writes a project edit.
- Preserved transactional preview publication. Cancellable source exports are
  generated in private temporary folders; staged replacements decode through
  hidden sibling WAVs; the session records a receipt only after complete WAV
  validation. Cancellation removes partial/unreceipted output, while an
  already validated cached preview remains intact.
- Closed the existing task-admission race: if another blocking operation owns
  the worker lane, a rejected Play request immediately releases its request
  token and returns to **Play** instead of remaining stuck on a preparation
  label. Old non-cancellable command-line exports retain their established
  direct `subprocess.run` behavior and signatures remain backward compatible.
- This release adds no encoder, retail audio, private source path, project
  payload, or new runtime dependency. All implementation and automated checks
  were terminal-only and headless; authored-audio audibility still requires a
  controller-driven Xenia A/B with the modder's own encoder and audio.

## 0.1.0-alpha.29 — owned Audio browsing lifecycle 2026-07-20

- Added an applied Audio query token covering the decoded model epoch, search,
  record kind, role, source/bank, and page offset. During the 180 ms typing
  delay, Add-this-page, Previous/Next, matching export, replacement-template
  export, and filtered decoded-row export are disabled and guarded at their
  method boundaries. Publishing the matching table applies the token
  atomically. Typing and erasing back to an already displayed query restores
  the exact page and pagination immediately.
- Kept exact selected-row work available during that delay. Play, individual
  Export, Replace/Revert, and Add/Remove-selected own the visible row identity
  instead of interpreting the pending aggregate filters.
- Changed the session-only Audio shortlist **Clear** action into one-level
  **Clear / Undo**. Up to 256 mixed AUDO/AUSB rows restore in exact insertion
  order. Clearing from Review returns to the browser; Undo does not reopen
  Review. The recovery snapshot expires only after a real shortlist mutation
  or successful model/game change, and it never enters a project or starts a
  worker.
- Bound private preview preparation to `(model epoch, row ID, request
  generation)`. A late success cannot start the previously selected sound, and
  a late failure cannot interrupt the current row with a stale dialog. A
  current preparation failure clears ownership, restores **Play**, and remains
  retryable.
- Confirmed the existing source switch is already transactional: failed loads,
  file-picker cancellation, and unsaved-work cancellation preserve the old
  Audio model, page, selection, shortlist, waveform, and running preview. No
  speculative source-load rewrite was added.
- The focused Audio GUI suite passes 26/26. The complete headless APF suite
  passes 466/466 after the lifecycle and packaged-runtime receipt additions.
  No interactive desktop, emulator, private game source, or retail audio was
  used for this release.

## 0.1.0-alpha.28 — batch PCM16 replacement packs 2026-07-20

- Added a second, metadata-only audio replacement-pack contract:
  `apf2k8_mod_studio_audio_replacement_pack/v2`. Choose **Exact PCM16 WAV**
  before creating a folder or ZIP template; its listed payload paths are
  `pcm16/*.wav`. A template can still describe any filtered set, the
  Soundtrack album, the reviewed shortlist, or all 47,775 editable AUDO/AUSB
  rows. It carries target shape and source/project binding only—never original
  audio, decoded source names, an encoder, preimages, or rollback bytes.
- Added project-atomic batch WAV import through the modder's existing,
  separately configured XMA1 encoder. Every supplied WAV must be one exact
  signed little-endian PCM16 RIFF stream with the target's channel count,
  sample rate, and frame count. Import accepts at most 256 supplied WAVs per
  transaction, even when the metadata-only template lists more targets. Folder
  import counts and refuses entry 257 before opening or hashing any WAV bytes;
  ZIP import enforces the same ceiling before payload extraction.
- Kept import automatic and backward compatible. Folder and ZIP import detect
  v1 `xma1/*.xma` versus v2 `pcm16/*.wav` from the exact schema and input
  contract. The v1 writer, generated README, default selection, and
  deterministic ZIP bytes remain unchanged, and legacy v1 imports do not need
  a configured encoder.
- Preserved one final admission path for both pack generations. PCM WAVs are
  copied into private pinned inputs, encoded one at a time, and then cross the
  existing exact allocation, packet, complete-decode, duration, target,
  optimistic-baseline, AUSB alias, and cross-family source-packet gates. Only
  after every supplied sound passes does the full set become one Undo action.
  Encoder failure, validation failure, alias conflict, cancellation, or a
  changed pack removes new unreferenced private work and stages nothing.
- Added explicit **Pre-encoded XMA1** / **Exact PCM16 WAV** controls, format-
  specific folder/ZIP labels, progress and cancellation copy, and copyright
  guidance to the Audio workspace. **Ctrl+F** now focuses the visible enabled
  search field in the current workspace from the shared shell; it does not
  target hidden searches inside inactive tabs.
- Kept the boundary explicit: Mod Studio still ships no XMA1 encoder and had no
  real encoder for compatibility proof. PCM-pack tests use synthetic encoders
  to prove orchestration and validator handoff, not perceptual encoding.
  FLAC/MP3, mixed PCM/XMA packs, more than 256 supplied WAVs per import, and
  whole physical-bank replacement remain unsupported. Authored-audio runtime
  causality remains inconclusive, and the `.apf2k8mod`/Build schema is
  unchanged.
- The focused Alpha.28 product gate passes 115/115 and the complete headless
  APF suite passes 457/457. The sealed release metrics and authoritative
  archive identity are recorded in `APF2K8_STATUS.md` and the adjacent
  `.sha256` sidecar; no interactive desktop or emulator was launched.

## 0.1.0-alpha.27 — selected-sound PCM authoring bridge 2026-07-20

- Added **Export PCM authoring template…** and **Replace from PCM WAV…** to
  every individually editable Audio row: 2,261 standalone AUDO sounds plus
  45,514 semantic AUSB substreams. The exported WAV is exact-length PCM16
  silence derived from the selected slot's channel count, sample rate, and
  declared frame count; it contains no source audio. The success receipt also
  shows the fixed encoded XMA allocation that a WAV header cannot express.
- Added a no-terminal **Configure XMA1 encoder…** dialog for a modder's own
  separately installed tool. Native executables run directly; Windows `.exe`
  tools can use a separately installed Wine executable. Advanced configuration
  accepts one literal argv entry per line with bounded `{input}`, `{output}`,
  `{channels}`, `{sample_rate}`, `{sample_count}`, and `{encoded_size}`
  placeholders. No shell command is accepted or constructed.
- Kept external-tool configuration outside `.apf2k8mod`: resolved encoder/Wine
  paths, literal argv, and a 30–1800 second timeout live only in per-user
  application settings. Deleted/corrupt tools report **Needs attention** rather
  than breaking the Audio page. A 600-second default covers the longest
  soundtrack authoring jobs better than the backend's shorter library default.
- Added cooperative **Cancel PCM encoding**, bounded stderr/output, private
  canonical PCM staging, and full owned-process-group TERM/KILL cleanup on
  success, failure, timeout, cancellation, and exceptions. Independent review
  reproduced and then closed a child-process escape before packaging.
- Preserved one final admission path. External output is untrusted until the
  existing AUDO/AUSB RIFF, exact allocation, packet framing, complete decode,
  duration, shared-owner, target identity, and cross-family exact-source-packet
  checks all pass. Only then does one normal Undo-able edit enter the project.
  **Replace with XMA1…** remains available as the advanced direct route.
- Kept the boundary explicit: Mod Studio ships no encoder; the build environment
  had no real XMA1 encoder for compatibility proof; synthetic fake encoders
  prove process and validator handoff only. FLAC/MP3 and batch PCM input remain
  unsupported. Folder/ZIP batch replacement still accepts finished exact-slot
  XMA1. In-game authored-audio causality remains inconclusive.
- Corrected the roster roadmap with the completed headless result: a valid
  180-second passive slot-43 observe control preserved the source and ended
  `path_not_reached`. Ordinary no-input boot does not exercise the defensive
  roster-builder path, so modified mode stays locked pending a deliberately
  navigated positive observe run. The 0–99 editor already covers all 63,112
  mapped base-rating cells; true 53-player runtime teams remain an emulator-side
  multi-consumer project, not a data-only edit.
- Sealed the exact retail-free allowlist after independent GO review: `104`
  files in `15` directories, `3,297,442` file bytes, `22` executables, `71`
  Python files, and `119` sorted safe tar members. The full APF suite passes
  442/442, the focused release/GUI gate passes 65/65, and the slot-43/census
  suite passes 44/44. Both the stage and a clean extraction pass the 66-module /
  31-capability runtime gate and release audit; deterministic re-archive is
  byte-identical. The adjacent `.sha256` sidecar, not this packaged document,
  is the archive's authoritative identity.

## 0.1.0-alpha.26 — audio ZIP hand-off and accessible shell 2026-07-20

- Added a clear **Editable folder / ZIP hand-off** selector to the Audio batch
  authoring workflow. Either format can describe the current filters, the
  Soundtrack album, the reviewed shortlist, or the complete 47,775-sound
  editable surface. The generated template remains metadata-only: it contains
  target coordinates, exact slot shape, aliases, source binding, and current
  replacement baselines, but no original game audio or source-owned names.
- Added deterministic, non-overwriting ZIP template publication and direct
  edited-ZIP import. ZIP templates put `replacement-pack.json`, `README.md`,
  and `xma1/` at the archive root. The importer accepts normal stored or
  deflated, unencrypted archives and privately materializes their files only
  for the bounded validation/import transaction.
- Kept the Alpha.25 authoring guarantees unchanged across both containers:
  missing XMA1 files are skips, every supplied file crosses exact-slot decode
  and cross-family retail-packet rejection, stale target/alias baselines fail
  before commit, all real changes become one Undo action, and a failed or
  cancelled import changes no project edit. Existing Alpha.25 template folders
  and their original generated README remain accepted.
- Added explicit archive defenses for path traversal, symlinks and special
  entries, encryption, duplicate or case-colliding names, wrapper directories,
  undeclared members, expansion limits, and archive/file identity changes.
  Temporary extraction is private and removed after success or failure.
- Improved the shared shell without changing an editor contract: **Ctrl+1**
  focuses the category sidebar from anywhere, category and asset lists have
  strong keyboard-focus outlines, header/footer chrome can grow for larger
  system fonts, and navigation, operation status/progress, Build, and Launch
  expose descriptive accessibility text. Focused offscreen Qt coverage checks
  both product shells; this is not a visual or screen-reader certification.
- This remains an exact-slot, pre-encoded one-stream RIFF XMA1 workflow—not an
  audio encoder. WAV/FLAC/MP3 input and authored-audio runtime causality remain
  unproved. Alpha.26 was the then-current headless-tested packaged checkpoint;
  Alpha.25 remains the prior sealed retail-free package. The exact allowlisted
  stage and clean extraction pass the retail-free and isolated runtime gates;
  no interactive desktop or emulator was launched.

## 0.1.0-alpha.25 — batch audio authoring checkpoint 2026-07-19

- Added the Audio tab's retail-free **Create replacement template…** and
  **Import replacement folder…** workflow across all 47,775 individually
  editable sounds: 2,261 standalone AUDO slots plus 45,514 semantic AUSB
  substreams. A template may come from the current search/kind/role/source
  filters or the exact reviewed shortlist. It contains only generated target
  IDs, coordinates, exact slot shape, alias ownership, and loaded-source
  binding—never original audio or source-owned sound names.
- Added safe manifest-plus-folder batch admission for already encoded,
  one-stream RIFF XMA1 files. Missing listed files are intentional skips. The
  importer rejects unknown files/rows, repeated identities or filenames,
  edited slot shape, changed source binding, unsafe paths, invalid audio,
  divergent aliases, and unchanged-only packs. Every manifest identity is
  reconciled before packet work; every supplied sound then crosses the existing
  full decode and cross-family source-packet rejection boundary.
- Bound every manifest entry to the selected sound's current replacement-only
  project state, including every disclosed AUSB alias owner. Import checks this
  optimistic target lock before packet work and again immediately before the
  atomic commit. A stale target asks for a fresh template, while unrelated
  project edits do not block useful work. Baselines are canonical hashes and
  carry no private path, replacement bytes, or retail data.
- Made batch mutation atomic at the project level. Validated payloads are
  prepared privately first; the active edit map changes only after the whole
  folder passes. All real changes become one Undo action, while a failure leaves
  both the active edit set and Undo stack untouched. Failed cleanup preserves
  every packet file referenced by either active edits or any Undo snapshot, and
  an advisory progress-callback failure cannot escape after a successful
  commit. The generated README and manifest are bounded private regular files;
  modified or hardlinked contract files are rejected. Existing `.apf2k8mod`
  serialization and Build receive the same typed AUDO/AUSB modifications, so
  their replacement-only and exact-source-byte rejection guarantees remain in
  force.
- Added per-file validation progress and **Cancel replacement import**. The
  cancel request is observed only between complete XMA1 files; a cancelled
  folder changes no project edit, adds no Undo action, preserves the last valid
  Build receipt, and removes only new unreferenced private packet-cache files.
- This is a manifest-and-folder v1 workflow, not a replacement ZIP and not an
  encoder. Ordinary WAV, FLAC, MP3, WMA, xWMA, and XMA2 input still requires a
  distributable XMA1 encoder. The focused audio/build/project closure passes
  **128/128** in the final root rerun. A real-source metadata-only spot check created an AUDO plus
  two-owner `cwdloop` alias template with an empty `xma1/` folder and no source
  titles in the manifest. A clean 101-file staged tree passes the retail-free
  release gate and the runtime import gate at 65 modules / 31 capabilities. No
  GUI or emulator was launched for this headless Alpha.25 checkpoint.
- Advanced Alpha.25 to the then-current packaged checkpoint after an independent
  adversarial GO review. The review reproduced and closed stale-template and
  Undo-owned-payload cleanup failures before release. The final exact
  allowlist contains 101 files; both the stage and an independent clean
  extraction pass the retail-free release gate and the 65-module / 31-capability
  runtime gate. The archive remains deliberately self-hash-free and is
  authenticated by its adjacent checksum sidecar.

## 0.1.0-alpha.24 — headless packaged checkpoint 2026-07-19

- Added an output-drive free-space preflight before hashing or creating a
  private build stage. APF Build now requires room for the complete extracted
  game tree plus a 512 MiB safety margin. A refusal reports available,
  required, and missing GiB in modder-facing language and creates no partial
  output. Tiny shortages are reported in bytes instead of rounding down to
  `0.00 GiB`. The same behavior is implemented for 2K5; focused cross-title
  build-safety tests pass **32/32**.
- Added a fixed **Position (17)** editor for every one of the 2,254 on-disc
  players. The dropdown exposes the exact native codes `0..16` (QB through DE),
  supports individual Apply/Revert and modified badges, persists only the
  user-selected code in `.apf2k8mod`, and composes with player names, team names,
  and all 28 base ratings in one token-preserving ROST Build. The bounded writer
  changes executable-consumed player byte `+0x34` and its required opaque source
  mirror at `+0x35` as one indivisible pair; it refuses a source record whose
  pair already differs. Position edits do not infer team membership, depth-chart
  slots, ratings, Overall, tier, or abilities. Offline writeback and clean
  retail-free packaging pass; the first changed-position Xenia spot check is
  still pending, so the UI and capability registry say that plainly.
- Advanced Alpha.24 to the current headless-tested packaged checkpoint; the
  sealed Alpha.23 archive remains preserved as the previous checkpoint. The
  complete 163-test focused gate passes, as do the retail-free release and
  64-module/31-capability runtime gates on a clean stage and independent
  extraction. The packaged changelog remains deliberately self-hash-free;
  Alpha.24's exact archive identity is authenticated by its adjacent checksum
  sidecar. No GUI or emulator was launched.

## 0.1.0-alpha.23 — previous packaged checkpoint 2026-07-19

- Extended strict pre-encoded RIFF XMA1 Replace/Revert, modified badges, Undo,
  project save/load, replacement preview, and typed Build from the 2,261
  standalone AUDO slots to **all 45,514 semantic AUSB substreams**. They resolve
  to **45,513 canonical physical ranges** across 19 external banks. Physical
  External Bank and AUSB index rows remain private raw containers; authoring is
  deliberately scoped to their individually addressed substreams.
- Added the source-resolved, pack-aware AUSB build compiler. It validates exact
  channels, sample rate, packet allocation, decoded duration, semantic owner
  metadata, the complete cross-domain `0x800`-packet authorization inventory,
  and every individual source pack span. The stereo Track 3 allocation crosses the end of `0A` and start of
  `0B`; Build splits those writes, verifies bytes outside them unchanged, and
  atomically publishes only the complete staged game folder. No descriptor or
  whole-bank repack is performed.
- Closed alias and retail-byte safety. The one `cwdloop` physical allocation has
  two disclosed semantic owners. Identical edits through both IDs deduplicate;
  divergent writes to the same bytes fail before publication. Projects retain
  canonical user packets plus semantic shape/owner fingerprints only—no source
  audio, preimage, source fingerprint, physical coordinate, or descriptor byte.
  Session admission, project load, modified preview, and Build each reject any
  replacement containing one complete `0x800`-byte packet found anywhere in
  either the AUDO or AUSB source inventory, including cross-family transplants.
  A real-source Build scan rejected an 8-bit-mutated Track 12 near-retail
  candidate at packet 0 that the former whole-payload-only gate admitted; the
  scan took 14.13 seconds and peaked at 208,896 KiB RSS. The 40,316 unique whole
  AUSB payload hashes remain an inventory measurement, not the safety boundary.
- Recorded the runtime and decoder boundaries without promoting causality. The
  private candidate booted, selected **Track 12 — Bury Me Standing Remix**, and
  visibly remained in playback for 25 seconds without a crash. The completed
  objective capture experiment was negative/inconclusive: its sustained segment
  matched neither the mutated candidate nor stock Track 12 (best 17-second
  `|NCC|` about `0.031`), distinguishing frames favored neither, and a
  self-control confirmed classifier power. This proves boot/selection/stability,
  neither authored-audio consumption nor stock fallback. FFmpeg 6.1.1 decoded
  18/30 original jukebox stereo/mono sides; all 45,514 targets remain
  addressable, but replacement input must pass the stricter complete decode.
- Added a retail-free **32-team × 53-row roster planner**. Each team shows the 42
  memberships stock APF currently sees plus eleven project-only reserve slots.
  `.apf2k8roster` stores only authored reserve player indices, never the source
  memberships or game bytes, and Build does not apply the reserves. True 53
  runtime players still require a version-pinned XEX consumer/accessor patch and
  owned side-table storage. Cross-domain safety tests pass `4/4`, the focused
  combined audio/build suite passes `25/25`, and the full product suite passes
  **722/722 in 93.739s**.
- Advanced Alpha.23 to the then-current sealed packaged checkpoint; Alpha.22 is
  previous. The `682,202`-byte archive has SHA-256
  `ca1f5ed0f3dab91f373a520e664cbdb59d1f30afc2844e83c3ed76204a039c67`,
  authenticated by its adjacent mode-`0444` sidecar. Stage and independent
  extraction each passed the release and both runtime gates at `96` exact
  allowlisted files; two direct archives and the extraction re-archive were
  byte-identical. The sealed package's own changelog remains deliberately
  self-hash-free; this source entry was updated after sealing.

## 0.1.0-alpha.22 — sealed 2026-07-19

- Added an experimental exact-slot editor for all 2,261 standalone `AUDO`
  resources. Selecting a **Standalone AUDO** row now exposes **Replace with
  XMA1…**, per-sound Revert, the normal modified badge, Undo, project save/load,
  staged-replacement waveform/play preview, and the typed Build path.
- The importer accepts only pre-encoded, one-stream RIFF XMA1. Channel count,
  sample rate, encoded byte length, and decoded sample count must match the
  selected target; encoded data must remain a nonempty `0x800`-byte packet
  multiple. Every packet must use the APF XMA1 metadata/skip contract, and a
  complete FFmpeg error-exit decode must pass before an edit is staged.
- Added a dedicated compiled-span build route instead of exposing arbitrary raw
  offsets. All 2,261 source targets resolve to uncompressed, contiguous,
  non-overlapping `0A` spans. Multiple edits compose with typed whole-entry
  writers, collisions fail closed, every authored span is verified exactly,
  bytes outside the compiled spans must remain source-identical, and the output
  archive is reparsed before success.
- Kept shareable projects replacement-only. They store canonical user-supplied
  raw XMA1 packets under `.xma1-packets` plus bounded target-shape metadata;
  they never store the supplied wrapper, original sound, rollback bytes,
  retail loop metadata, or physical source offsets. At this sealed checkpoint,
  any exact replacement payload matching one of the 2,261 source `AUDO` cues is
  rejected at import and project admission. Alpha.23 supersedes
  this release-era family-local check with the cross-domain packet gate above.
- Did not claim a general audio encoder. WAV, FLAC, MP3, WMA, XMA2, and
  size-changing XMA input remain unsupported because the local distributable
  toolchain has no validated XMA1 encoder. The 45,514 `AUSB` substreams and all
  19 physical multi-cue banks—including both 15-track soundtrack encodings—
  remain browse/play/export-only while their cue-directory/repack semantics are
  unresolved.
- Completed a matched Xenia runtime spot check instead of leaving playback as
  pending. The one-span candidate booted, logged no XMA fault, survived five
  intended Schedule-enter triggers, returned to the Season hub, and closed
  normally; a restored byte-identical stock control followed the same route.
  Timestamp-aligned waveform correlation did not beat random windows, and the
  correctly directed spectral interaction did not beat 160 pseudo-event sets
  (`p=0.155` one-sided). Classification remains **offline-writer-proved;
  runtime partial, audible cue consumption inconclusive**, not runtime-proved.
  See the
  [exact-slot authoring contract and A/B result](../product/APF_AUDO_EXACT_SLOT_XMA1_EDITOR.md).
- Completed isolated-display visual QA against the recognized source. A
  standalone row showed **Replace with XMA1…**, **Revert sound**, and its exact
  54.0 KiB / 22,050 Hz / stereo requirement without clipping. The 15-track
  `jukebox22` view kept replacement disabled and explained that shared AUSB
  banks remain export-only. The final copy now calls exact-slot import an
  advanced workflow, says plainly that ordinary WAV/FLAC does not work yet,
  and explains why soundtrack/commentary Replace is disabled.
- Packaged and sealed Alpha.22 as the then-current retail-free Linux checkpoint.
  The archive is `633,190` bytes with SHA-256
  `f2adf77b9abdeddd1b2c2bf93fd2523a93eb721a192543c7660ba3e49b4578fb`;
  its adjacent mode-`0444` sidecar verifies. Stage and independent extraction
  match at `92` allowlisted files, `15` directories, `2,706,017` file bytes,
  `22` executables, and canonical inventory SHA-256
  `75e647061b379f1970448d85847ed12b8bbbdeb2064b8ff04112dc60036f1629`.
  Both deterministic archives were byte-identical and both trees passed the
  retail-free, 59-module/31-capability runtime, private-source, desktop, Bash,
  and post-runtime gates. Package-facing copies remain deliberately self-hash-
  free; this post-seal source entry and the adjacent sidecar authenticate the
  immutable archive.

## 0.1.0-alpha.21 — 2026-07-19

- Promoted bounded player **First name** and **Last name** replacement into the
  runnable product source. The existing token-preserving ROST route now admits
  3,191 nonempty player-name allocations serving 4,482 writable first/last
  references, alongside the 40 existing team display-name allocations. That is
  3,231 product-editable name allocations in total; the zero-capacity empty
  allocation, both team-abbreviation families, and any mixed or unknown scope
  remain locked.
- Generalized **Replace Name** / **Revert Name**, project load, and Build around
  one centralized fail-closed scope check. Pure player-name aliases may span
  first- and last-name owners, but a mixed team/player allocation cannot inherit
  permission. The earlier team-display-name compatibility route remains intact.
- Added complete local alias disclosure before authoring. The source contains
  429 shared editable player-name allocations, the largest with 23 owners; 61
  are shared across both first- and last-name fields. One replacement changes
  every listed owner together, and the UI reports that explicitly instead of
  silently treating the selected field as independent.
- Kept shareable projects retail-free and replacement-only. A project stores
  authored text plus the existing pool index, limit, owner count, and owner
  fingerprint; it does not persist retail player names, alias-owner lists,
  source strings, ROST records, preimages, physical offsets, or game bytes.
- The runtime basis remains the isolated Xenia `Marino` → `CODEX` proof: **Dan
  CODEX #13 QB** rendered in player selection and **QB #13 DAN CODEX — GOLD
  STAR** rendered on the Star Card without the former startup crash. The
  complete Alpha.21 product suite passes `648/648` in `90.763s`.
- Completed the real-source public product smoke through the same actions a
  modder uses: load the game, replace Dan's last name with `CODEX`, Undo,
  replace, Revert, replace again, save a project, reopen it, Build a separate
  3.7 GB game, and reparse the output. The 989-byte project has SHA-256
  `45902ead474bfd868c88469220076e3cd23a47e7a58c3fa568129e1bb743694e`
  and contains replacement JSON only. The output `0A` has SHA-256
  `0212b638c1cdfa348110e57dbef4af5e0048101ff340202f52fec2021cd54044`,
  exactly matching the runtime-proved candidate; only outer 1126 changed and
  the source remained byte-identical.
- Completed isolated-display visual QA after the roster-layout UX fix. A fresh
  window showed **Identity & Names** by default with **Base Ratings (28)**
  adjacent; **Replace Player Name**, **Revert Player Name**, and **View 23
  affected fields…** were simultaneously visible with the exact `4/4` limit and no
  clipping or scroll trap. A separate retail-free product-code dialog check
  showed high contrast and all 23 owner rows at once.
- Packaged Alpha.21 as the then-current retail-free Linux checkpoint. Verify the
  archive against its authoritative adjacent `.sha256` sidecar before install.
  Final tree/archive seal details are authenticated by that sidecar and the
  post-seal source `STATUS`; this package-facing changelog deliberately avoids
  embedding its own circular archive hash. Alpha.20 is preserved as the
  previous checkpoint at SHA-256
  `f3f02cbefbbcd5f0890efb889948e2a34487a9f07f0a2900744d44b19da56ef8`.
- Post-seal source receipt: the corrected archive is `607,218` bytes with
  SHA-256
  `35b7d23298ce69639ad7e2a09b24be4838de6066d22963abaf0f387dd3d4e232`;
  its `119`-byte mode-`0444` sidecar verifies, and its tar has `105` safe
  members. Stage and clean extraction match at `90` allowlisted files, `15`
  directories, `2,594,779` file bytes, `22` executables, and canonical inventory
  SHA-256
  `96f74cb24a044368a244e04b843f0bc6c6bb686ef2f8b5c1c0523a0670db7da5`,
  with no links, special/undeclared files, private material, or retail bytes.
  Both trees passed every release/runtime/private-source/desktop/Bash gate, all
  `63` packaged Python files parse, and a second deterministic tar was
  byte-identical.
- An independent audit rejected and deleted the first regenerable candidate
  because its bundled docs still called Alpha.20 current and Alpha.21 pre-seal.
  Only the corrected current-Alpha.21 rebuild was sealed. The packaged copy of
  this changelog remains intentionally self-hash-free; its adjacent sidecar and
  the post-seal source `STATUS` authenticate the exact seal.
- Did not promote team abbreviations, jersey numbers, roster membership, depth
  charts, active-roster capacity, or audio replacement. True 53-active-player
  teams still require an executable consumer/accessor extension rather than a
  larger name allocation.

## 0.1.0-alpha.20 — 2026-07-19

- Turned **Export complete audio catalog…** into a self-describing private
  audio library. Its v2 manifest retains the role, source/bank, format, sample
  rate, channel count, duration, soundtrack pairing, and owned size metadata
  already visible in Mod Studio instead of reducing each cue to coordinates.
- Added deterministic `catalog.csv` with one ordered row for every requested
  semantic item, including failures, unsupported bank/index rows, and rows
  skipped after cancellation. Successful sounds now carry their exact archived
  byte size and SHA-256 in both the JSON and CSV.
- Added ordered `playlist.m3u8` for successful cue payloads and omits it when
  no playable sound succeeds. Playlist entries never include AUSB index rows,
  raw physical banks, failures, or cancelled items. Spreadsheet-formula and
  control-character sanitization applies to the convenience CSV/playlist;
  the source-derived JSON metadata remains the authoritative record.
- Kept the boundary unchanged: the ZIP is private retail-derived output, Track
  01–15 remains honest when artist/title are unknown, original XMA1 may require
  a compatible player, and no encoder, replacement writer, or cue/loop
  ownership is implied.

## 0.1.0-alpha.19 — 2026-07-18

- Added **Export all original banks (19)…** as a separate private audio route.
  It copies every physical external XMA1 `.bin`—including `jukeboxmusic` and
  `jukebox22`—through the already bounded raw-bank reader into one atomically
  published, non-overwriting ZIP. The deterministic manifest records the
  source fingerprint, exact bank name/outer identity/name ID, payload size and
  SHA-256, plus every AUSB descriptor owner and conservative role label.
- Wired the existing cooperative cancellation contract into the actual Audio
  GUI for both the 47,814-row cue catalog and the physical-bank bundle.
  **Cancel audio export** stops between complete sounds or banks; the published
  partial manifest accounts for every skipped item, so no file is truncated
  and cancellation is never reported as an unexplained success.
- Kept the capability boundary explicit. Raw physical banks are multi-cue
  containers, not directly playable sounds; export does not imply XMA1 encode,
  replacement, cue/loop ownership, or a reversible bank writer. Exported ZIPs
  are private retail-derived files and never enter `.apf2k8mod` projects or the
  public application package.

## 0.1.0-alpha.18 — 2026-07-18

- Added **Import ratings sheet…** beside the complete roster export, with
  `Ctrl+Shift+I` as a keyboard shortcut. The v2
  private CSV is bound to the exact loaded-game SHA-256 and contains all 2,254
  players × 28 canonical rating columns. Export now includes the active project
  values, so a modder can round-trip a large work-in-progress roster through
  LibreOffice without losing earlier in-app edits.
- Added a non-mutating review dialog with separate counts for new replacements,
  source reverts, already-matching cells, project conflicts, source conflicts,
  and errors. Wrong-source or edited source-metadata conflicts are never
  overrideable. A sheet that disagrees with an active project edit requires a
  second explicit acknowledgment before Apply.
- Implemented three-way source/current/sheet comparison, stable-file and
  active-edit fingerprints, revalidation immediately before mutation, and one
  atomic batch commit. A complete import creates exactly one Undo action;
  rejected and zero-change imports create none. Native `100` is accepted only
  when preserving or reverting an existing source `100`; authored values stay
  exact `0..99` integers.
- Kept the CSV private and the project retail-free. `.apf2k8mod` stores only
  canonical authored rating payloads and semantic target metadata—not the CSV,
  player names, source values, roster records, or preimages.
- Real-source smoke covered 63,112 cells, Dan Marino Speed `40` → `99`, active-
  project conflict confirmation, one-step Undo, project-ZIP inspection, and an
  unchanged source hash. The supported retail roster's observed values span
  `0..99` and contain no actual `100`; the source-100 compatibility/revert case
  remains covered by the focused synthetic contract test.

## 0.1.0-alpha.17 — 2026-07-18

- Promoted the completed 0–99 ratings slice from source-head wording to the
  packaged product documentation. Getting Started now reports the live
  8 Editable / 6 Preview / 3 Export-only / 14 Coming Soon capability split,
  and the README points to each archive's authoritative checksum sidecar and
  versioned status receipt instead of describing an older package as current.
- Product code is unchanged from the 617/617-tested Alpha 16 ratings build;
  this checkpoint corrects release-facing version/document consistency.

## 0.1.0-alpha.16 — source head, 2026-07-18

- Promoted all 28 mapped per-player **Base Ratings** from exact Preview to
  strict native `0..99` authoring. Each edit is addressed by player index and
  stable attribute ID, stored as a tiny canonical replacement-only JSON
  payload, marked modified, individually revertible, Undo-safe, and included
  in project save/load and transactional Build. No scale conversion, inferred
  Overall, star-tier change, or neighboring-byte write occurs.
- Preserved the engine's distinct native-100 compatibility case. An untouched
  source value of 100 is displayed exactly and can be reverted, while new
  authored values remain deliberately limited to 0..99.
- Added the token-preserving player-rating writer and a disjoint-delta ROST
  compositor. Team display-name edits and rating edits now share outer entry
  1126 safely in one build instead of colliding or rebuilding one change over
  the other. Component manifests authorize only their selected decoded ranges;
  no original values, replacement values, preimages, physical pack offsets, or
  game payload bytes enter a shareable project or public receipt.
- Promoted exact team **Display name** replacement under its live allocation
  limit. Player first/last names and both team abbreviation fields stay visible
  but locked; jersey number, position, membership, depth charts, abilities, and
  Gold/Silver/Bronze tier remain separate unresolved capabilities.
- Replaced the superseded generic H7A rebuild path that crashed at guest PC
  `0x84AB1D40`. A token-preserving `Americans` → `CODEXTEAM` candidate booted
  through first-run construction and rendered the name in Logo Selection, Team
  Summary, and Team Select. A one-byte Dan Marino Speed `40` → `99` candidate
  preserved 284,014 of 284,015 tokens, booted, and loaded/rendered the edited
  player card without the former crash. APF has no numeric ratings screen, so
  the latter proves transport and player-record load—not a measured gameplay
  effect.
- Kept ratings-sheet export as a private, owner-only planning artifact. The
  public `.apf2k8mod` format contains only user-authored semantic deltas and
  retail-free target metadata; it never embeds the source roster or original
  rating values.

## 0.1.0-alpha.15 — source head, 2026-07-18

- Added **Export ratings sheet…** to Rosters & Players. It creates a private,
  wide CSV with all 2,254 on-disc players, identity/position/team context, and
  one stable column for each of the 28 exact base ratings. The export validates
  the complete player index set, native 0..100 values, and canonical field
  order before publishing.
- Ratings sheets are retail-derived local exports, never project payloads. They
  use owner-only permissions, publish atomically, refuse an existing filename,
  and explain plainly that the CSV must stay private. Import/edit remains
  locked with the shared rebuilt-ROST runtime boundary.
- Full-source smoke passed at 2,254 rows, 28 rating columns, indices 0..2253,
  native 100, stock maximum 99, and mode `0600`; the private output was deleted.
  Isolated `DISPLAY=:99` QA found the enabled toolbar action unclipped at
  1480×920 with both roster scroll areas and runtime-lock badges intact.
- Started three bounded crash-isolation tracks for guest PC `0x84AB1D40`:
  static function/register tracing, retail-vs-rebuilt container comparison,
  and a practical guest-state logging route. Each must end with a concrete
  experiment/result before writer exposure changes.

## 0.1.0-alpha.14 — 2026-07-18

- Added a searchable, read-only **Base Ratings** panel for every one of the
  2,254 on-disc player records. It exposes all 28 independent stored bytes: 27
  executable-named attributes plus neutral **Unknown Rating 24**. Values are
  shown exactly on the native 0..100 contract; stock data spans 0..99 and is
  never clipped or rescaled. Semantic JSON/CSV roster export includes the same
  field IDs, labels, values, and record-relative coordinates. Overall,
  abilities, and Gold/Silver/Bronze tier remain explicitly separate. Rating
  replacement stays locked with the shared rebuilt-ROST runtime boundary.
- Added the bounded APF roster identity map and development writer. The
  supported source contains 3,273 owned UTF-16BE allocations, 3,272 nonempty
  offline-writer targets, and 4,628 mapped references (4,508 player fields plus
  120 team fields). Shared allocations retain their alias-owner count. This
  mapping remains available in **Rosters & Players**, but runtime evidence now
  locks replacement as Preview/read-only.
- Completed a clean-controlled runtime experiment. The clean source reached
  the APF title screen, while combined, team-name-only, and player-name-only
  builds all crashed during startup at guest PC `0x84AB1D40`, reading
  `0x0000000270000000`. The identical team/player failure falsifies the current
  ROST replacement transport rather than implicating one authored name.
  New Replace authoring and Build exposure were removed from the public
  capability. A removal-only Revert path remains for legacy development
  projects, and Build refuses until those edits are removed. The offline
  reconstruction backend remains development evidence only. See the
  exact [runtime report](../product/APF_ROSTER_IDENTITY_RUNTIME_NEGATIVE.md).
- Recorded the next roster experiment: instrument guest execution around
  `0x84AB1D40` to capture the invalid object/pointer chain and compare the
  retail decoder's output for one rebuilt H7A block against the project's
  decoded body. If those bodies agree, trace post-load relocation or integrity
  ownership before changing the writer again. The separate
  [32-team/53-player feasibility note](../product/APF_32_TEAM_53_ROSTER_FEASIBILITY.md)
  remains an ambitious capacity study, not evidence that name replacement is
  safe.
- Jersey numbers remain explicitly read-only because the decoded ROST evidence
  contains no consumer-backed jersey-number field. Base ratings are now mapped
  for exact Preview, but their writer, positions, membership, and depth charts
  are not implied by the identity map.
- Added a dedicated **Field Art ownership map** for all 258 live category rows
  across 125 archive packages. Seven exact families make the inventory useful:
  235 endzone textures, four field scenes, four field-radiance textures, six
  divot/weather textures, three practice/field overlays, four practice-related
  scenes, and two penalty animation curves. Search, family filtering, package
  identity, preview, and the existing PNG/scene/raw export routes are wired.
  Replace/Revert stay locked because name and archive co-location do not prove
  a team, stadium, selector, shader, material, or runtime owner.
- Added explicit, cancellable Audio waveform previews. **Load waveform** reuses
  the selected cue's verified session-private WAV and samples PCM16 within a
  fixed memory bound; selection alone never starts a decode or player. Changing
  row/source cancels stale work, errors remain retryable, and AUSB index or
  physical-bank rows never advertise a single-cue waveform.
- Added **Export complete audio catalog…**, the 47,814-row atomic Audio batch
  route for original XMA1 or decoder-verified WAV. All 2,261 standalone cues
  and 45,514 addressed AUSB substreams use the existing verified single-sound
  exporter. The manifest records all 20 AUSB index rows and 19 physical-bank
  rows as unsupported, plus every per-cue failure or cancellation, instead of
  silently dropping rows.
  The final ZIP publishes without replacing an existing destination. This is
  export-only and does not enable Audio replacement.
- Completed the bounded Wine-hosted stadium debugger experiment with a useful
  negative result. Wine intercepted Xenia's host instruction breakpoint before
  a game frame or guest-register capture, so the route did not test
  material-to-TXTR ownership. The exact private debugger change was rolled back.
  The next credible experiment is a logging-instrumented Xenia build or a
  native-Windows guest-debugger capture, not a repeat of the same Wine route.
- Kept the roster identity capability at Preview after its runtime
  falsification. The sealed registry has 31 APF records, split 7 Editable,
  7 Preview, 3 Export-only, and 14 Coming Soon.
- Fixed the tall roster-detail layout found during visual QA: ratings and name
  allocation controls now use an independent vertical scrollbar, roster rows
  say **Mapped names · Runtime locked** instead of Editable, and the workspace
  tab has enough width/padding to render **Roster + Base Ratings** completely.
- Sealed the retail-free Linux package after `588/588` tests, source-free and
  private-source runtime closure, release/install safety, independent
  extraction, deterministic archive reproduction, and isolated `DISPLAY=:99`
  visual QA. The archive contains 84 allowlisted files and has SHA-256
  `b38350de9dbc121c963861db44e2bac2d9caa8595cdd35e39766f2b205203279`.
  The complete receipt is in [STATUS](APF2K8_STATUS.md).

## 0.1.0-alpha.13 — 2026-07-18

- Added a capability-to-action binding layer between the shared registry and
  the APF desktop. Every capability card that remains Editable or Export-only
  now names a real product handler and its supported Preview, Export, Replace,
  and Revert actions. Exact asset editors dispatch through the same binding,
  so a registry classification or a similar asset name cannot fabricate a
  working button.
- Kept **Menus & Text** honestly Editable by binding
  `apf2k8.menus.layouts` to its existing in-place editor for 2,410 of 2,413
  decoded TXT/STRG allocations. Card status no longer depends on an irrelevant
  file-extension input. The three protected structural allocations remain
  read-only under the existing Text Sheet and per-row contracts.
- Downgraded six unbound semantic promises to honest **Coming Soon** cards:
  cross-title model conversion, the broad uniform-logo catalog, mode/state
  routing, generic SCNE-to-glTF conversion, `hi_head` face research, and the
  retained Season/franchise research lane. Their data remains inventoried in
  the appropriate browsers; only the nonexistent dedicated desktop action is
  withheld. The specialized Stadium glTF viewer remains Export-only because it
  does have its own bounded handler.
- Split the exact `franchise.iff` `draft_logo` writer into a dedicated editable
  registry capability. The registry now contains 31 APF capabilities
  and 61 capabilities across both games; the 30 existing NFL 2K5 records are
  unchanged. Their alpha.13 card split is 7 Editable, 7 Preview, 3 Export-only,
  and 14 Coming Soon. The hidden `jersey_06_runtime` record stays a proof alias,
  not a duplicate user-facing editor. The broader APF logo catalog remains
  browse/export only.
- Added explicit disabled-state styling for primary, secondary, utility,
  Build, and Launch controls. Stadium replacement is labeled **Replace
  (locked)**, closing the alpha.12 visual ambiguity where a disabled primary
  button could retain its orange active color.
- Polished Audio selection at the physical-bank boundary. Multi-cue external
  bank rows hide the single-sound Play control, use **Choose a sound to
  shortlist**, and retain a wider/taller technical detail pane for long bank
  ownership and archive coordinates. Exact raw-bank export stays available;
  Play, shortlist, and Replace remain cue-only actions.
- Completed the bounded static stadium-material experiment. The first scene's
  116 mesh nodes resolve through 328 draws to all 113 serialized material
  records and 13 shader families. Scanning 737 unique named texture identities
  found zero static references in the scene-system material data, including no
  reference to the three same-package texture candidates. This is a useful
  negative result: surface-to-TXTR ownership is still unresolved and
  Replace/Revert remain locked.
- Recorded the next stadium experiment precisely: capture one known draw at
  the runtime renderer material handoff, recover the loaded material-array
  base and pixel-shader texture mapping, follow live texture-object pointers,
  and correlate their guest allocations/dimensions with the scene GPU part and
  same-package TXTR allocations.

### Release receipt

- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.13-linux-x86_64/`
- Linux archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.13-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.13-linux-x86_64.tar.gz.sha256`
- Size: `477,068` bytes
- SHA-256:
  `645c021d9d3d0570ed6a307c15a8a06387fb4be3cf20abaf23a70f3bc0b14e9f`
- The release tree and independent clean extraction are path-, mode-, and
  size-identical: `73` files, `14` directories including the root, `2,023,280`
  file bytes, `22` executables, zero symlinks or special files, and `87` tar
  entries. Their shared path/mode/size inventory SHA-256 is
  `6b5c7868c4f39febd889e225ab9f7d6d5e075064bbeccd17bbb0fc9f4ad98cd2`.
- Release validation passed with `73` allowlisted files, `2,023,280` bytes,
  two metadata files, eight install-surface files, all seven retail hashes
  fenced, the reviewed extractor present, and no private data, retail data,
  symlinks, or undeclared files. Runtime validation passed with `50` modules
  and `31` APF capabilities.
- A supported untouched private source resolved `10,464` universal catalog
  items, `96` specialist uniforms, and all `408` uniform/equipment records.
  Registry validation passed at `61` global / `31` APF capabilities, with
  APF cards split 7 Editable, 7 Preview, 3 Export-only, and 14 Coming Soon.
- The complete source suite passed `528/528` tests before sealing.
- Isolated-display visual QA inspected fresh Stadium (`0x03800035`) and Audio (`0x04000035`)
  windows on isolated `DISPLAY=:99`. Both showed the exact `Alpha 13` badge.
  Stadium displayed the 116-mesh / 328-draw / 113-material / 13-shader-family /
  737-texture-identity boundary and a gray **Replace (locked)** action. Audio
  displayed all `47,814` semantic rows and the XMA replacement boundary. No
  clipping, overlap, or footer obstruction was found; the user's active desktop
  and pointer were not used.
- The independent extraction is retained at
  `/tmp/apf-alpha13-extract.gZubBi`. The published tree, archive, checksum
  sidecar, and extracted package remain immutable; this exact receipt was added
  only to the source documentation after sealing.

## 0.1.0-alpha.12 — 2026-07-18

- Replaced the generic Stadium asset page with the first honest Stadium Studio.
  It inventories all 93 exact `stadium` SCNE records and prepares a private,
  source-hash-fenced glTF only when the modder opens a scene.
- Added a dependency-free 3D viewer with orbit, pan, zoom, reset, triangle
  sampling, surface picking, and retained glTF mesh/primitive plus APF
  scene-node/source-mesh identity. The first real-source smoke loaded 116
  meshes, 112,158 vertices, and 68,669 source triangles.
- Added same-outer package inspection beside the 3D view. TXTR records use the
  existing private PNG preview/export route and every other related record
  keeps exact raw export. A selected surface never auto-claims a texture:
  material/TXTR ownership is explicitly unresolved and Replace/Revert remain
  disabled.
- Added non-overwriting private 3D Scene ZIP export containing glTF, its binary
  buffer, and a source-bound manifest. Derived caches and exports remain private
  retail-derived outputs and never enter a shareable project or public package.
- Improved workspace tabs with extra leading and horizontal breathing room.
  Audio technical identity now retains a useful minimum height; physical bank
  selection hides Play and labels shortlist actions as single-sound-only, so a
  multi-cue `.bin` cannot visually resemble a playable cue.
- Added eight stadium-focused tests and extended the physical-bank UX test.
  The complete cross-title Mod Studio suite passes `512/512`.

### Release receipt

- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.12-linux-x86_64/`
- Linux archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.12-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.12-linux-x86_64.tar.gz.sha256`
- Size: `462,020` bytes
- SHA-256:
  `2cc7a3178f0afff81ebd402d308b75fbaa272075003ee2630f42c2794c678ccf`
- Stage and independent extraction are identical: `71` files, `14`
  directories including root, `1,976,945` file bytes, `22` executables, zero
  links/special files, and `85` archive members. Their shared path/mode/size
  inventory SHA-256 is
  `120ccb4207026a4bfeedb6fe0af976c7bd4ba51a03102b5016faa579d3a02b6c`.
- Both trees passed retail-free release, 49-module source-free runtime,
  supported private-source runtime, registry, desktop, Bash, and isolated
  installer lifecycle gates. Derived `.gltf`, `.glb`, `.bin`, and `.zip` files
  are structurally excluded.
- Isolated-display visual QA verified the 93-scene viewer, first 116-mesh scene, nine-record
  package inspector, and 2048×1024 package preview on isolated `DISPLAY=:99`.
  It also caught that a disabled primary Replace button retained the orange
  ID-specific style. Alpha.12 is immutable; the next build fixes disabled
  primary/secondary/utility/build/launch styling globally. Full detail is in
  `APF2K8_STATUS.md`.

## 0.1.0-alpha.11 — 2026-07-18

- Expanded Uniforms & Equipment from the 96 specialist writer cards to the
  complete 408-record category. **Editable Materials (96)** preserves the four
  bounded writer families; **Additional Assets (312)** adds 275 TXTR, 24
  NumberFont, 11 NameFont, and two SCNE records with scoped type filters,
  100/100/100/12 paging, previews where decoded, and exact export. Archive
  identity excludes the writer targets from the second tab, so no asset is
  hidden or duplicated.
- Added a retail-free 38-row Sliders & Gameplay inspector: all 21 named stock
  sliders plus 17 retained draft-lineage weights. The UI explicitly says that
  current profile values, final catch/drop causality, a live APF draft selector,
  out-of-range safety, and writers are not proved.
- Rebuilt Scorebug & Presentation as three full-height workspaces:
  **Presentation Map** (seven scene components plus the `digital_font`
  boundary), **Digital Font**, and **Raw Presentation Assets**. The semantic map
  ships as a small reviewed metadata projection with no report dependency,
  executable address, retail hash, or game payload.
- Named all 19 physical external XMA1 banks from their 20 exact source-owned
  AUSB descriptor links. They are routed into Audio as `XMA1_BANK` rows and
  include `jukeboxmusic.bin`, `jukebox22.bin`, `lines.bin`, `players.bin`, and
  `teams.bin`; the shared `cwdloop.bin` ownership remains deduplicated.
- Added typed **Export original bank .bin** with exact name/size/owner checks,
  bounded streaming, progress, exclusive atomic publication, source
  preservation, and existing-path/symlink refusal. Physical banks never enable
  Play, Replace, complete-sound ZIP, or shortlist actions; their AUSB substreams
  remain the playable/exportable sounds.
- Corrected playable-row wording to **XMA available · WAV/Play when verified**.
  The source-wide inventory does not falsely generalize a decoder sample into a
  promise that every XMA payload will decode.
- Focused Uniform/Product-Findings and Audio slices pass `14/14` and `52/52`;
  the complete cross-title Mod Studio suite passes `507/507`. A clean untouched
  source resolves 10,464 universal items, 408 uniform records, 47,814 semantic
  Audio rows, 19 physical banks, and 20 descriptor owners.
- No retail game bytes enter the package or a project. Raw `.bin`, XMA, WAV,
  PNG, ZIP, and semantic exports are private outputs from the user's own copy.
  APF audio replacement remains disabled until a validated distributable XMA1
  encoder, cue/loop ownership, and reversible writer all exist.

### Release receipt

- Release tree:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.11-linux-x86_64/`
- Linux archive:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.11-linux-x86_64.tar.gz`
- Checksum sidecar:
  `build/releases/apf2k8-mod-studio-0.1.0-alpha.11-linux-x86_64.tar.gz.sha256`
- Size: `428,574` bytes
- SHA-256:
  `66b7ecbf1d951d2353832ace3750fbcc067959d11e973f985e35cb39eaa7e7fe`
- Stage and independent extraction are byte-, size-, and mode-identical: `68`
  files, `13` directories including the root, `1,840,704` file bytes, `22`
  executables, zero links/special files, and `81` archive members. Their shared
  mode/size inventory SHA-256 is
  `833421de12a6a461d65fbee109dad504604395849ab3ec43a32659118b30f859`.
- Both trees passed retail-free release, 46-module source-free runtime,
  supported private-source runtime (`10,464` universal assets / `96` writer
  uniforms / `408` total uniforms), registry, desktop, all-four-script Bash,
  isolated install/update/uninstall, and repeated post-runtime gates.
- Isolated-display visual QA verified the sealed build on `DISPLAY=:99`: the 408-row
  Uniforms split, 38-row Gameplay map, eight-row Scorebug map with 128×128
  digital-font writer, 25 raw presentation assets, 47,814-row Audio inventory,
  and single filtered 776.4 MB `lines.bin` physical bank all rendered. No
  emulator, export/edit, active desktop, or user pointer was used. Minor tab
  leading-glyph/padding and dense-text ellipsis are retained honestly in the
  detailed `APF2K8_STATUS.md` receipt and queued for the next source build.

## 0.1.0-alpha.10 — 2026-07-18

- Added a complete **Review selected** Audio workspace. It displays up to 256
  hand-picked sounds in exact insertion order with local 100-row paging,
  Play/Stop, individual export, remove, Clear, and cross-page **Move up** / 
  **Move down** controls. Reordering changes the exact bundle and
  `playlist.m3u8` order. Returning restores search, kind, role, source/bank,
  page, and selection; last removal, Clear, and model reload exit cleanly.
- Review is decoded-row UI state only. Add-page and matching-filter export are
  disabled while reviewing, and Review/reorder/navigation emit no project,
  modification, or crash-recovery event. The shortlist still contains no audio
  bytes and never enters `.apf2k8mod`.
- Added **Soundtrack album (15)**. It opens the 15 source-owned
  `jukeboxmusic` 48 kHz stereo masters by default and exposes the 15 matching
  `jukebox22` 22.05 kHz mono companions through one selector while preserving
  track number. The view activates only for the exact proved 15-by-15 index,
  duration, channel/rate, pairing-field, and export-identity contract. Artist
  and title stay explicitly **Unknown**; no commercial metadata is guessed.
- Added private **Export Text Sheet** / **Import Text Sheet** actions to the
  Universal Text inspector. Export writes all 2,413 owned TXT/STRG allocations,
  source binding, allocation limits, coordinates, originals, and current
  replacements to a non-overwriting UTF-8 CSV. Import validates the complete
  sheet before staging any row, supports `auto`, `replace`, `revert`, and
  `skip`, and applies every accepted change as one Undo action.
- Text Sheet cells use a required leading apostrophe so spreadsheet programs
  cannot interpret game text as formulas. Imports fail closed on a different
  source hash, changed ownership/coordinates/originals, duplicate or unknown
  targets, protected allocations, NULs, UTF-16 overflow, malformed/linked/
  oversized CSVs, or a late invalid row. Only authored replacement text enters
  project/recovery state.
- A Text Sheet necessarily contains original strings from the user's own game,
  so it is a private editing file—not a shareable project or release artifact.
  `.apf2k8mod` remains replacement-only and the public package remains
  retail-free.
- Headless gates pass `20/20` focused Audio/Text-Sheet tests, `20/20` focused
  recovery tests, and `115/115` APF-pattern tests; the complete cross-title Mod
  Studio suite passes `489/489`.
- The package was created headlessly. Its separate post-seal visual gate
  then passed on isolated `DISPLAY=:99`: fresh source-ready windows visibly
  showed `Alpha 10 • retail-free`, both Text Sheet actions and allocation-limit
  UI, all shortlist Review/reorder controls, the 15-row stereo Soundtrack
  album, and the switch to the 15-row mono companions. No clipping, overlap,
  spacing collapse, or footer obstruction was found; no emulator or active
  user desktop/pointer was used.

### Release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.10-linux-x86_64/`
- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.10-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.10-linux-x86_64.tar.gz.sha256`
- Size: `412,489` bytes
- SHA-256:
  `c72d53f052fb843d01e259e50fa7628b5b56f21212588c6545757554e4c0fd28`
- Test gates: `20/20` focused Audio/Text-Sheet, `20/20` focused recovery,
  `115/115` APF-pattern, and `489/489` complete cross-title Mod Studio tests.
- Stage and independent extraction are byte-, size-, and mode-identical: `66`
  files, `13` directories including the root, `1,775,875` file bytes, `22`
  executables, zero links/special files, and `79` archive members. Their shared
  mode/size inventory SHA-256 is
  `d0a0cd009f94db5237fc22e1f03c1befeee7612da74c0c01f14b113e1c131ae8`.
- Both trees passed retail-free release, 45-module source-free runtime,
  supported private-source runtime (`10,464` universal assets / `96` uniforms),
  registry, desktop, all-four-script Bash, isolated install/update/uninstall,
  and repeated post-runtime release gates.
- Alpha.9 remains unchanged at
  `046f7463a8eb7a13b78e4a7b53eff2e310a2594e5d4b4526378b8dfc1204b83d`.
- Isolated-display visual verification passed after the headless seal. The exact
  observed controls and desktop-isolation boundary are recorded in
  `APF2K8_STATUS.md`.

## 0.1.0-alpha.9 — 2026-07-18

- Added normal **Open Recent Game** and **Open Recent Project** menus. APF ISO/
  XISO files and extracted game folders are both remembered, the newest eight
  entries are de-duplicated, missing paths remain visible but disabled with
  their full path in the tooltip, and projects stay disabled until their
  source game is loaded.
- Added source-bound crash recovery. Every authored edit, revert, Undo, and
  Revert All coalesces into a private replacement-only
  `unsaved-recovery.apf2k8mod`; an intentional zero-edit dirty document is
  recoverable too. The autosave is bound to the exact user-selected source path
  and recognized `0A` SHA-256, so an ISO extraction cache can never become the
  remembered source.
- Startup offers **Recover Edits**, **Not Now**, or **Discard Recovery**. The
  File menu also provides **Recover Unsaved Edits**. A recovered document is
  deliberately unnamed and dirty so the user must choose where to save a
  shareable copy. If the source moved, the app names the exact missing ISO or
  extracted folder instead of discarding the safe recovery project.
- Recovery writes serialize with every session mutation, source swap, project
  load/save, and build. In-flight edits coalesce; stale completions cannot be
  labeled as another source; failed source/project switches preserve the live
  dirty document and its recovery; successful Save/Discard cleanup affects only
  the matching source. A postponed recovery for another source is preserved
  rather than overwritten.
- Workspace metadata is a bounded, atomic, mode-`0600` JSON document containing
  paths and hashes only. Recovery uses the same validated `.apf2k8mod` writer as
  normal projects, never a second payload format. Empty and nonempty tests prove
  it contains user replacements/metadata but no retail bytes or preimages.
- The portable launcher now hands its exact validated private state directory
  to the app, including its guarded fallback, so launch diagnostics, recents,
  and recovery cannot silently diverge.
- Playable APF bank and hand-picked Audio ZIPs now include an ordered UTF-8
  `playlist.m3u8`; the manifest declares its path and entry count, and known
  durations are preserved. Original XMA1 and decoder-verified WAV exports retain
  their exact user-selected order. This is a local export from the user's own
  game, never a shareable project payload.
- Headless gates pass `20/20` focused recovery tests and `107/107` APF-pattern
  tests; the complete current cross-title product gate passes `468/468`.
- Isolated-display visual QA verified current alpha.9 window `0x09a0002b` at `1480×920` on
  isolated `DISPLAY=:99`. `Alpha 9 • retail-free`, all 14 sidebar categories,
  the complete header/footer, the nine-row File menu, **Open Recent Game** and
  **Open Recent Project** empty-state flyouts, and **Recover Unsaved Edits**
  were readable and unclipped. No recovery dialog appeared without a candidate,
  and the user's active desktop/pointer were never used.
- The exact package and clean-extraction receipts are recorded in
  `APF2K8_STATUS.md` beside the sealed archive checksum.

### Release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.9-linux-x86_64/`
- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.9-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.9-linux-x86_64.tar.gz.sha256`
- Size: `401,795` bytes
- SHA-256:
  `046f7463a8eb7a13b78e4a7b53eff2e310a2594e5d4b4526378b8dfc1204b83d`
- Test gates: `20/20` focused recovery, `107/107` APF-pattern, and
  `468/468` complete current cross-title tests.
- Stage and independent clean extraction are byte-, size-, and mode-identical:
  `65` files, `13` directories including the root, `1,726,822` file bytes,
  `22` executables, zero links/special files, and `78` archive members. Their
  shared mode/size inventory SHA-256 is
  `ffa61522d1a6e13cc30805ea37069d2a4fff7420a68cd7e867334fc8dc8c6d9c`.
- Both trees passed release, source-free and private-source runtime, registry,
  desktop-file, all-four-script Bash, and repeated post-runtime release gates.
  Runtime closure is `44` modules and `30` capabilities; the supported private
  source produced `10,464` universal assets and `96` uniforms with
  `private_source_verified=true`.
- The sealed alpha.8 archive was reverified unchanged at
  `7fe2198bebdf0f0f0c2114358b1174bfbc34507bf93678f559347c99c6f9003a`.

## 0.1.0-alpha.8 — 2026-07-18

- Turned `.apf2k8mod` files into normal active documents. The window title now
  distinguishes `Untitled*`, a dirty named project, and a clean named project;
  document dirty state is independent from the number of active replacements,
  so reverting the final edit leaves a visible, saveable zero-edit change.
- Added File-menu **Save Project** (`Ctrl+S`) and **Save Project As**
  (`Ctrl+Shift+S`). The existing header Save button uses the same dispatch:
  first save asks for a name, while later saves atomically update the exact
  remembered project without reopening the file dialog. A clean named project
  can still use Save As to create a replacement-only copy.
- Added protected expected-target fast-save. Missing, symlinked, non-regular,
  hardlinked, pathname-substituted, or externally changed targets fail closed,
  preserve foreign bytes, and direct the user to Save Project As. Every
  successful save refreshes the in-memory target identity; a stale identity
  cannot be reused.
- Project opening now validates into a candidate session, compares the project
  file identity before and after complete archive validation, and commits the
  new session only if both identities match. Failed project and source loads
  preserve the current path, identity, edits, and dirty state.
- Source switching, project switching, and closing now use a standard
  **Save / Discard Changes / Cancel** gate. Post-save switching and closing wait
  until the save worker has fully unregistered, avoiding a false “operation is
  still running” collision. Successful source replacement clears the active
  project; successful project save/load is clean.
- Audio browsing, playback, local export, filtering, and the alpha.7 shortlist
  remain non-authoring actions and never dirty a project. Audio replacement is
  still not claimed: the XMA1 encoder, cue/loop ownership, and reversible bank
  writer boundaries are unchanged.
- Added `9` focused active-document tests. The combined document/core/safety
  slice passes `36/36`, and the complete current cross-title gate passes
  `443/443`.
- Isolated-display visual QA verified source-ready alpha.8 window `0x0860002b` at `1480×920`
  on isolated `DISPLAY=:99`. `Alpha 8 • retail-free`, the source-ready header,
  all `14` sidebar categories, and every header control were readable and
  unclipped. The File menu showed Open Project (`Ctrl+Shift+O`), Save
  (`Ctrl+S`), Save As (`Ctrl+Shift+S`), and Quit (`Ctrl+Q`) without overlap or
  cramped spacing; Save and Save As were correctly disabled for a clean source
  with no active project.

### Release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.8-linux-x86_64/`
- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.8-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.8-linux-x86_64.tar.gz.sha256`
- Size: `392,574` bytes
- SHA-256:
  `7fe2198bebdf0f0f0c2114358b1174bfbc34507bf93678f559347c99c6f9003a`
- Unit gates: `9/9` active-document tests, `36/36` focused
  document/core/safety tests, and `443/443` complete cross-title tests.
- Visual gate: source-ready alpha.8 window `0x0860002b` passed at `1480×920` on
  isolated `DISPLAY=:99`, including the complete File menu and correct clean
  Save/Save As disabled states.
- Stage and independent clean extraction: `65` files, `13` directories
  including the root, `1,675,159` file bytes, `22` executables, and zero links.
  Both passed release, source-free and private-source runtime, registry,
  desktop, all-four-script Bash, and repeated post-runtime release gates.
- The archive has `78` members. Runtime closure is `44` modules and `30`
  capabilities; the supported untouched private source produced `10,464`
  universal assets and `96` uniforms with `private_source_verified=true`.
- The sealed alpha.7 archive was reverified unchanged at
  `e031891a7b610d6462ba05c6053f21a4641e77beb318ac78cb7f77de812b52d7`.
- Recent-project menus and crash-recovery autosave are deliberately deferred to
  alpha.9. Alpha.8 preserves normal explicit Save/Save As behavior and does not
  hide that remaining convenience gap.

## 0.1.0-alpha.7 — 2026-07-18

- Added a session-only **Audio shortlist** for collecting sounds across
  unrelated searches, pages, roles, and banks. Users can add/remove the current
  playable row, add every playable row on the current 100-row page, clear the
  list, and see both an exact `Selected N / 256` counter and row badges.
- **Export selected sounds** reuses the existing transactional bundle writer,
  preserves shortlist order, defaults to original XMA1, offers
  decoder-verified WAV explicitly, and refuses an over-256 page without making
  a partial selection.
- The shortlist contains only in-memory decoded row identities. It clears when
  the loaded model changes and never enters a project or release artifact.
- Added focused offscreen Qt coverage for cross-filter persistence,
  deduplication, page addition, the all-or-nothing 256 cap, model reset, badges,
  ordered forwarding, and the original-XMA default.
- The complete cross-title product gate passes 428/428 tests.
- Isolated-display visual QA loaded the current Audio page on `DISPLAY=:99` at
  1480×920. All 47,795 decoded rows were present, and the shortlist heading,
  Add/Remove, Add this page, Clear, `Selected N / 256`, export, matching-export,
  and replacement-boundary controls were readable and unclipped.

### Release receipt

- Release tree: `build/releases/apf2k8-mod-studio-0.1.0-alpha.7-linux-x86_64/`
- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.7-linux-x86_64.tar.gz`
- Checksum sidecar: `build/releases/apf2k8-mod-studio-0.1.0-alpha.7-linux-x86_64.tar.gz.sha256`
- Size: `391,496` bytes
- SHA-256: `e031891a7b610d6462ba05c6053f21a4641e77beb318ac78cb7f77de812b52d7`
- Unit gate: the complete current cross-title product suite passes `428/428`.
- Visual gate: Audio loaded all `47,795` decoded rows at 1480×920 on isolated
  `DISPLAY=:99`; every shortlist control was readable and unclipped.
- The original stage and clean extraction each contain `65` files, `13`
  directories including the root, `1,649,360` file bytes, and `22`
  executables. Both passed release, source-free runtime, private-source runtime,
  registry, desktop-entry, all-four-script Bash syntax, and post-runtime release
  gates.
- Runtime closure is `44` modules and `30` capabilities; the untouched private
  source produced `10,464` universal assets and `96` uniforms with
  `private_source_verified=true`.
- The archive contains `78` members. Stage, archive, and extraction contain no
  symlinks, hardlinked files, caches, retail bytes, or private payloads. The
  sealed alpha.6 archive was reverified unchanged.

## 0.1.0-alpha.6 — 2026-07-18

- Added an explicit **Audio source / bank** filter above the 47,795-row decoded
  catalog. It exposes Standalone AUDO plus every AUSB bank with its playable
  count and stable outer/inner coordinates, so duplicate bank names cannot
  alias each other.
- Search, decoded kind, broad role, and source filters now intersect for paging,
  decoded JSON/CSV export, and **Export matching sounds**. Choosing
  `jukeboxmusic` or `jukebox22` isolates its descriptive bank row and 15
  playable soundtrack entries; the transactional bundle action receives the
  exact 15 export identities.
- Moved the Audio kind/role/source controls onto their own filter row and added
  `Ctrl+Shift+B` to focus the bank selector. This keeps the search/export row
  readable at ordinary laptop widths.
- Isolated-display visual QA verified the separate two-row Audio controls on
  `DISPLAY=:99`: search/export, kind, role, source, table, and detail actions
  remain fully readable with no clipping or overlap.
- The complete cross-title product gate passes 419/419 tests. Alpha.6 is a new
  immutable checkpoint; alpha.4, alpha.5, and their checksums remain unchanged.

### Release receipt

- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.6-linux-x86_64.tar.gz`
- Size: `388,619` bytes
- SHA-256: `9710308dc637c7129c35d7e944726f4b3ef3f4274a0cb510c11510ab7230dcae`
- The exact 65-file / 13-directory stage contains `1,633,476` file bytes.
  Its 44-module runtime closure, 30 capabilities, per-user install lifecycle,
  and untouched private-source inventory (10,464 universal assets / 96
  uniforms) passed before archiving and again after clean extraction.
- The adjacent `.sha256` sidecar is the authoritative archive checksum.

## 0.1.0-alpha.5 — 2026-07-18

- Added transactional **Export matching sounds** for any 1–256 playable rows
  selected by the Audio search, record-kind, and role filters. This closes the
  practical bulk-export gap for bounded slices of the 11,797-row `players`,
  31,826-row `lines`, and 1,498-row `teams` speech banks without pretending the
  unresolved XMA1 replacement path is writable.
- Matching bundles may mix AUDO and AUSB substreams, use collision-free numbered
  filenames, include a role/bank/coordinate/rate/channel/duration manifest, and
  publish only after every member succeeds. Original XMA1 is the default;
  verified-WAV mode leaves no partial ZIP if any decode fails.
- Corrected individual Audio export so its default filename/filter is original
  `.xma`, matching the product's documented safe default. WAV remains available
  explicitly after full decoder verification.
- Moved Audio into full-height **Audio Browser** and **Raw Audio Assets** tabs.
  The complete universal raw inventory remains one click away while Play,
  individual export, bank export, filtered export, and the honest replacement
  boundary no longer compete with a second vertical browser for height.
- Isolated-display visual QA checked the current build on `DISPLAY=:99`. The broad
  47,795-row view shows filtered export as clearly disabled; its own full-width
  row and the replacement row are fully separated with no clipping or overlap.
  The enabled 1–256 state is covered by the focused offscreen Qt interaction
  test without opening an export dialog on the user's desktop.
- Passed all 72 APF product tests before creating the non-overwriting alpha.5
  package. The archive's adjacent `.sha256` sidecar is the authoritative
  checksum receipt.

### Release receipt

- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.5-linux-x86_64.tar.gz`
- Size: `386,254` bytes
- SHA-256: `05c4e7132167f0167ce71bc7b244fa6c3ca9faa2b75dab7433617f97556515a8`
- All 72 matching APF product tests passed.
- The 65-file stage, its 44-module runtime closure, per-user install/update/
  uninstall lifecycle, and untouched private-source inventory all passed before
  archiving. A clean extraction repeats the same gates before publication.
- The adjacent `.sha256` sidecar is the authoritative archive checksum.

## 0.1.0-alpha.4 — 2026-07-18

- Turned all four decoded English text banks into one bounded text editor.
  Menus & Text now places 2,413 underlying TXT/STRG pool allocations before the
  1,572 TXT reference rows, marks 2,410 allocations Editable, keeps the two
  required `INVALID TEXT` fallbacks and one zero-capacity STRG allocation
  read-only, and shows each allocation's UTF-16 limit plus shared-consumer count
  before Apply. The old TXT-only pool rows are deduplicated rather than shown a
  second time.
- Added individual text Replace/Revert, modified badges, Undo/Revert All,
  canonical user-authored JSON payloads in `.apf2k8mod` projects, and grouped
  build composition when several strings share outer 185, 526, 810, or 1127.
  Relative pointers, H7A compression, IFF/footer structure, and the fixed outer
  sizes are rebuilt without writing the selected source.
- Completed a live untouched-source build proof: `SOUNDTRACK` became
  `MOD MUSIC`, only outer 1127 was compiled, the output was a complete separate
  game folder, and the source hash stayed unchanged. A bounded trace later
  showed that the 2K Beats playlist does not directly consume that allocation,
  so the product does not attach it to that screen or continue blind hunting.
- Closed the universal-text runtime spot check with an unmistakable target:
  outer 1127 / inner 0 / pool 11 changed from `Artist Biography` to
  `MOD BIOGRAPHY`, and Xenia rendered the exact new header on the 2K Beats
  biography page with its body and portrait intact. This proof is limited to
  that allocation; it does not invent screen ownership for the other editable
  TXT/STRG rows.
- Added compact text-detail spacing and keyboard focus shortcuts (`Ctrl+F` for
  decoded search, `Ctrl+Shift+K` for record kind) after isolated-display QA found
  two minor clips in the first pass.
- Turned the complete APF audio inspector into a modder-facing browser: 2,261
  standalone `AUDO` sounds, 20 `AUSB` bank records, and all 45,514 bank
  substreams remain source-derived and individually exportable. Rows now show
  role, XMA1 format, sample rate, channel count, duration, archive location, and
  actionable export state instead of requiring users to read raw JSON.
- Added conservative role taxonomy and filtering. Exact AUSB bank names drive
  Soundtrack & Music, Commentary & Speech, Stadium PA & Chants, Presentation,
  and Diagnostic & Ambient; standalone names use visibly labeled broad
  heuristics with an unknown fallback. No role label changes write eligibility.
- Paired the 15 `jukeboxmusic` stereo streams with the 15 `jukebox22` mono
  companions by exact source index and matching duration. The UI calls them
  Soundtrack Track 01–15 and explicitly leaves artist/title unknown instead of
  guessing copyrighted track metadata.
- Added Play/Stop through session-private, decoder-verified PCM WAVs. Preview
  names come only from bounded coordinates, symlinks and unreceipted/tampered
  files fail closed, no shell is invoked, and the entire preview directory is
  removed when the loaded-game session closes.
- Added complete-bank ZIP export for AUSB banks containing 1–256 substreams,
  including both 15-track soundtrack banks. Original XMA1 is the safe default;
  verified-WAV mode aborts without publishing a partial ZIP if any decode fails.
- Kept Replace visibly disabled with the exact boundary: the public/local
  toolchain has XMA1 decoders but no validated distributable XMA1 encoder, cue
  and loop ownership is incomplete, and no reversible bank writer exists.
  WMA/xWMA is not treated as an interchangeable encoding.
- Fixed catalog routing that had classified 157 crowd `TXTR`/`SCNE` and related
  visual resources as Audio. They now appear under Stadiums, including when an
  older private catalog cache is loaded; all true 2,261 `AUDO` and 20 `AUSB`
  records remain present.
- Added end-to-end editing for the exact `franchise.iff` inner-117
  `draft_logo`: source-derived 128×128 PNG preview/export, strict RGBA import,
  private original preservation, per-asset Revert/Undo, retail-free project
  persistence, and transactional `0A` build dispatch through the already-proved
  single-level BC3 writer.
- Kept the boundary narrow: no other logo or texture becomes editable, and the
  UI says the writer is offline-proved while franchise/draft runtime
  consumption remains unproved.
- Added JSON and CSV export for every decoded specialized inspector. The export
  follows the current search, kind, and (for audio) role filters, contains decoded rows rather than
  opaque archive bundles, never overwrites a destination, and remains outside
  shareable project/release artifacts.
- Removed the six-card display ceiling so every registry capability is visible.
  Moved all three uniform-selector capabilities to Team Identity alongside the
  1,120-row ownership inspector.
- Replaced ambiguous universal-browser `Export-only` wording with concrete
  action labels such as `PNG when decoded; raw ZIP always`, `Raw parts ZIP
  only`, and `Raw record only`.
- Updated runtime evidence: jersey asset 6 is corroborated in the Home/Away
  editor and pants has a positive Americans Away Uniform Type PANTS checker
  witness. Helmet, shoulder, `digital_font`, and `draft_logo` remain without a
  positive visible consumer proof.
- Added focused headless tests for exact-target gating, project retail-byte
  exclusion, writer dispatch, Revert, capability placement, card visibility,
  export labeling, and filtered semantic JSON/CSV output.
- All 69 matching APF product tests pass. The audio checks include an offscreen
  Qt control pass, metadata/role coverage, preview tamper/symlink/session cleanup,
  and all-or-nothing bank export. A live untouched-source headless audio smoke
  confirmed the exact inventory, paired soundtrack labels, one real private WAV,
  and one complete 15-stream soundtrack-bank ZIP. A separate live smoke
  resolved outer 810 / inner 117, generated the 128×128 RGBA preview, and
  compiled the original PNG through `apf_texture_patch/v1` into the exact
  913,408-byte fixed allocation without changing the source.

This checkpoint packages the universal-text, complete-audio-browser,
`draft_logo`, semantic-export, and capability-routing work above. The sealed
alpha.3 archive remains unchanged.

### Release receipt

- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.4-linux-x86_64.tar.gz`
- Size: `381,325` bytes
- SHA-256: `88fabc7bd1c167a60d6f943f9404366578070e168d3fe5d9d6989519ca3f9b93`
- All 69 matching APF product tests passed.
- The staged folder and a clean archive extraction independently passed the
  exact 65-file retail-free audit, 44-module source-free runtime and installer
  lifecycle, and untouched-source inventory result
  `capabilities=30 universal=10464 uniforms=96`.
- Archive inspection found 65 regular files, 13 directories, exact
  stage/extraction hash and metadata parity, and no links, special members,
  duplicate paths, case collisions, private runtime evidence, or retail game
  data.

## 0.1.0-alpha.3 — 2026-07-18

This checkpoint turns the APF-specific alpha into a directly installable
per-user Linux application and tightens the primary editing workspace without
changing the evidence boundary of any game asset.

- Added a root-level `install.sh`, `uninstall.sh`, and portable
  `APF-2K8-Mod-Studio.sh`, plus a top-level read-me so the extracted release has
  an obvious first action.
- Added a no-root Linux installer that re-runs the retail-free release audit,
  copies only exact allowlisted files, publishes from a sibling staging
  directory, and generates an absolute-path desktop shortcut and command.
- Added authenticated update and uninstall records. Colliding or externally
  changed shortcuts are refused or preserved; uninstall removes only its own
  program files and leaves projects, exports, caches, settings, and emulator
  data alone.
- Improved launcher errors to distinguish missing Python, PyQt5, Pillow, and a
  damaged application folder. State logs now follow `XDG_STATE_HOME`, use
  private permissions, and never require an active display for headless help or
  version checks.
- Extended the release and runtime gates to require and exercise the complete
  install, update, absolute launcher, and uninstall path in an isolated fake
  home directory without opening the GUI.
- Added `--tab` startup deep links for every one of the fourteen product
  categories, while keeping command-line help and version checks headless.
- Tightened the desktop shell's spacing, capability cards, search/filter rows,
  texture list density, footer hierarchy, and button sizing. Capability states
  now pair color with explicit symbols and words, transparent textures preview
  over a runtime-generated checkerboard, and clean assets expose a clearly
  disabled Revert action with a useful explanation.
- Kept Build Game Folder as the primary action and Xenia launch as a secondary
  action, matching the safe source → edit → build → play flow.

### Release receipt

- Linux archive: `build/releases/apf2k8-mod-studio-0.1.0-alpha.3-linux-x86_64.tar.gz`
- Size: `341,107` bytes
- SHA-256: `b74e2062b542d443c9fbe6fe1fbb8a4bfc9b1aad070aab6ac55226d5b50f592e`
- All 50 APF unit tests and Python compilation passed.
- The staged folder and a clean archive extraction independently passed the
  exact 62-file retail-free release audit, 42-module source-free runtime and
  installer lifecycle, and untouched-source inventory result
  `capabilities=30 universal=10464 uniforms=96`.
- Archive inspection found 62 regular files, 13 directories, exact stage/file
  hash parity, and no symlinks, hardlinks, devices, FIFOs, duplicate paths, or
  case collisions. No retail or private game data is present.
- Isolated visual QA on private Xvfb `:99` found no blocking or major defect in
  the fixed Uniforms screen; the active desktop `:0` was never used.

## 0.1.0-alpha.2 — 2026-07-18

This is the first APF-specific product and release-closure checkpoint. It
separates shippable application code from the retail-heavy research workspace.

### Newly available

- Added read-only recognition for the supported APF 2K8 USA ISO and complete
  extracted game tree, with an exact seven-hash source ledger.
- Added private ISO extraction through one size- and SHA-256-pinned
  `extract-xiso` binary distributed with its exact license.
- Added a live source-derived catalog covering 1,543 outer records, 1,473 IFF
  records, 70 non-IFF records, and 10,394 inner assets. The universal browser
  exposes 10,464 selectable items without shipping its generated catalog.
- Added 30 registry-driven APF capability cards across the complete sidebar.
- Added export/preview routing for textures, raw multipart resources, and all
  2,261 ordinary APF `AUDO` XMA1 resources. WAV export is attempted only when
  the local decoder verifies it.
- Added source-derived specialized inspectors for all 2,254 players, 40 teams,
  31 stadiums, 1,344 roster memberships, 1,572 localization records, one
  playbook with 163 formations/586 plays/4,948 route nodes, five director
  resources with 1,623 instructions, and all 1,120 uniform selector records in
  80 HOME/AWAY banks.
- Added exact export identities and on-demand XMA/decoder-verified WAV routes
  for all 45,514 substreams in APF's 20 `AUSB` banks and 19 external packet
  resources. A live export smoke passed for one `AUDO` resource and one `AUSB`
  substream.
- Added 96 uniform replacement targets: 24 jerseys, 24 pants textures, 24
  helmet mask textures, and 24 shoulder textures.
- Added `digital_font` export and replacement.
- Added strict, modder-facing PNG errors for dimensions, RGBA mode, pants alpha,
  helmet R/G mask transport, and digital-font alpha authoring.
- Added per-asset Revert, project-wide Revert, and Undo in the UI-independent
  session layer.
- Added retail-free `.apf2k8mod` project save/load. Projects contain replacement
  PNGs and metadata only, never original preimages or archive bytes.
- Added a transactional complete-game-directory builder. The source is never
  written, existing outputs are refused, and failed staging is removed before
  publication.
- Added a Linux desktop entry, scalable vector icon, and no-terminal launcher.
  Startup dependency failures use a desktop error dialog when available and
  keep diagnostics in the user's XDG state directory.

### Release safety

- Added an exact-file release allowlist. There are no directory wildcards.
- Added a fail-closed release audit rejecting all seven known retail hashes,
  APF game filenames, ISO/XEX/archive/media extensions, container magic,
  embedded byte arrays, private manifests, reports, exports, glTF, audio,
  screenshots, emulator state, caches, runtime evidence, `__pycache__`,
  symlinks, hardlinks, special files, world-writable files, and undeclared
  paths.
- The only allowed executable is the exact reviewed 51,336-byte Linux
  `extract-xiso`; its SHA-256 and mandatory license are pinned independently.
- Added a source-free runtime closure check that imports every APF product and
  writer module, validates the 30 capability cards, and round-trips a synthetic
  retail-free project without opening a GUI.
- Added an optional private-source runtime mode. With `--source`, it must report
  exactly `capabilities=30 universal=10464 uniforms=96` while keeping generated
  indexes in a temporary private cache.
- Completed the post-alpha core safety review with 30 passing APF tests. The
  hardened routes now stream large exports in bounded chunks, preserve files
  created concurrently at export/project publication time, validate existing
  content-addressed cache entries, reject duplicate project targets and ZIP
  members, constrain project metadata to typed scalar coordinates, remove
  failed import/build staging, refuse builds inside the source tree, and reject
  symlinked projects, emulator executables, and Xenia log destinations.
- Build publication now requires an atomic no-replace directory primitive. A
  platform/filesystem without that guarantee receives a clear refusal rather
  than a racy fallback.

### Honest capability limits

- Jersey asset 6 is the only uniform asset with positive on-screen runtime
  evidence so far. Pants, helmet, shoulder, and `digital_font` are currently
  bounded offline writers, not claimed visual proofs.
- Uniform selector banks are shared. The current 96 editable textures do not
  imply 40 teams each own four unique assets.
- Jersey and shoulder textures have shader/material-mask behavior that is not
  yet fully named. The app exposes channel caveats instead of presenting them
  as ordinary final-color bitmaps.
- APF text banks, roster identity, player names/numbers, team logos, field art,
  Stadium Studio texture ownership, scorebug composition, franchise state, and
  PLAY route semantics remain browse/export or Coming Soon according to the
  capability registry.
- XMA1 export is available; replacement is not. No legally distributable XMA1
  encoder has been integrated.
- The builder publishes an extracted Xenia game folder. Rebuilt ISO output and
  original-hardware support are not claimed.

### Packaging commands

From a fresh stage containing only the APF allowlist entries:

```bash
python3 packaging/check_apf2k8_mod_studio_release.py /path/to/apf-stage
python3 /path/to/apf-stage/packaging/check_apf2k8_mod_studio_runtime.py
python3 /path/to/apf-stage/packaging/check_apf2k8_mod_studio_runtime.py \
  --source /private/path/to/All-Pro-Football-2K8-USA.iso
```

The first two commands require no retail source. The third is an optional
private integration check and never makes the selected source part of the
release.

# PS2 executable patches — the pipeline, and the interface that exists today

> **Status 2026-09-05.** The interface is built and proved on a synthetic ELF
> (`mod_editor/games/nfl2k5_ps2/code_patches.py`, 13 tests + the conformance harness).
> **Zero of the host's 21 executable patches is translated to MIPS.** Every `translation()`
> refuses with the reason. This document says what exists, what the PS2 side needs, what the
> owner's earlier pnach work transfers, what filling in one patch costs, and the exact steps a
> future PR takes. Nothing here claims a patch works on PS2.

## 1. Why

The host ships gameplay patches that rewrite x86 code in the Xbox executable — Catching and
Interception sliders that decide the outcome, an acceleration ramp, realistic CPU drafts, modern
kicking and overtime rules, NFL-rate penalties, the Far camera, Free Practice in Franchise, and
so on. PS2 users play the same game through PCSX2 / PenguinScreen2 and want the same changes.
Each one is a MIPS EE change in the boot ELF `SLUS_209.19`, and **no Xbox address transfers**:
the repository's own rule (`docs/product/PS2_PORT_HANDOFF.md` route (d);
`mod_editor/data/nfl2k5_gameplay_inspection.v1.json`, `xbox_address_reuse_allowed: false`).
Translating is research. The interface is engineering, and it is done.

## 2. What exists on the Xbox side

- **The semantic catalogue**: `PATCHES` (18 rows of `(key, title, explanation)`) and
  `TEXT_PATCHES` (2) in `mod_editor/gui/gameplay_patches_panel_qt.py`, with `STRING_TOGGLES`
  (`penalties` → `"nfl"`, `prospect_names` → `"modern"`, `uniform_choice` → `"choice"`) and
  `NEEDS_IMAGE`; the throw-tuning parameters (`max_deep_yards` 55–100, `arc` 0–1,
  `realistic_flight`, `arc_by_distance`) in `mod_editor/core/nfl2k5_throw_tuning.py`.
- **The applier**: `mod_editor/core/mod_build.py` (`BuildPlan` flags, `inspect`, `build`);
  `nfl2k5_throw_tuning._apply_all` dispatches each flag to a module exposing
  `status(payload) → "retail" | "applied" | "foreign"` and `apply(payload) → (bytes, receipt)`.
- **How a site is stored**: a tuple `(label, va, retail_bytes, patched_bytes)`
  (`mod_editor/core/nfl2k5_rdata_sites.py`); sites are found by pinned retail bytes and the
  section table, refused as `foreign` when the bytes are not there, and the section digest is
  re-pinned after the write. The whole-executable digest (`RETAIL_XBE_SHA256` in
  `nfl2k5_bump_strength.py`) is advisory; the per-site pin is the gate.
- **Sharing**: `.2k5patch` (`mod_editor/core/modpack.py`) carries partition-relative byte runs
  with `expected_sha256` / `new_sha256` per run; the applier refuses unless every run matches
  before writing; `nfl2k5_disc_identity.can_take_a_byte_run_patch` keeps repacks out.
- **Registry**: the executable-patch lane has **no rows of its own**; the gameplay surfaces
  carry read-only or deferred Xbox rows (`nfl2k5.gameplay_tuning_sliders.rating_view`
  read-only-mapped, `nfl2k5.cpu_ai_draft.logic` read-only-mapped,
  `nfl2k5.catching_drops.behavior` unsafe/deferred).

## 3. What the PS2 side needs

1. **Identity.** Serial `SLUS-20919`, boot file `SLUS_209.19` (ELF32 little-endian MIPS,
   several `PT_LOAD` segments, one of them zero-filled `.bss`), the retail digest the registry
   already pins for the game, and PCSX2's game CRC `42F9D5AF` — the XOR of every 32-bit
   little-endian word of the ELF (`pcsx2/Elfheader.cpp`, `ElfObject::GetCRC`), which is how
   PCSX2 names the per-game patch file. All identities, no bytes.
2. **A per-patch MIPS mapping**: for each host patch, the EE addresses, the original words and
   the replacement words in `SLUS_209.19`, derived by locating the same *intent* in the MIPS
   build (never by arithmetic on Xbox addresses).
3. **Delivery, pnach first.** A `.pnach` under PCSX2's `patches/` (or PenguinScreen2's) named
   `<CRC>.pnach` applies the words at load time; nothing on the disc changes, exactly as
   textures ship as a replacement pack. On-disc delivery — the same words written into the ELF
   on a copy of the disc through the fixed-allocation ISO9660 writer — is the optional second
   route; a `.bss` address can only ever be patched at run time.
4. **Verification** that reads nothing from the writer: the pnach's CRC is the ELF's, every
   address lies in a file-backed segment, every original word matches, nothing else is
   declared.

## 4. The interface that exists

Contract (`mod_editor/games/contract.py`, part of `vc_game_module/v1`):

- `CodePatch(patch_id, title, surface, parameters, host_site, note)` — a host patch as the
  host catalogues it. `host_site` names the executable, its pinned digest, the flag, the
  catalogue module and the applier — never an address or a byte.
- `MipsWord(address, original, replacement)`, `MipsPatch(patch_id, words, elf_identity,
  parameters, note)`.
- `CodePatchLane` = `Lane` + `patches()`, `translation(patch_id, parameters)`,
  `emit_pnach(patches, crc)`, `verify_pnach(text, source, expected)`.
- `Receipt.artifacts` — a lane that writes a file declares it the way a fixed-allocation lane
  declares byte ranges; the harness checks the digest and tampers with the file.

Shared format package `mod_editor/games/_formats/ps2_elf`: ELF32 program headers, EE address →
file offset (refusing `.bss` and outside), `pcsx2_crc`, a strict pnach emitter/parser, the boot
ELF read from the user's ISO through `tools/ps2_iso9660.py`, a synthetic ELF builder.

The lane `mod_editor/games/nfl2k5_ps2/code_patches.py` (`Ps2CodePatchLane`):

| method | today |
|---|---|
| `patches()` | the 21 host patches, read from the panel's literal tuples without importing Qt |
| `translation(id, params)` | `Refusal`: "*id* is not mapped to MIPS yet: no SLUS_209.19 site has been located for it …" |
| `build_catalogue(iso)` | reads the boot ELF: serial, boot file, sha256, PCSX2 CRC, `retail`, segments; one target per host patch, labelled "not mapped to MIPS yet" |
| `check_edit` | parameters for an unmapped patch → the refusal; hand-authored `mips` words → validated |
| `compose_recipe` / `plan` | `nfl2k5_ps2_code_patch_recipe/v1`; every word checked against the user's ELF |
| `build` | writes `<name>.pnach` exclusively; artifact receipt |
| `verify` / `verify_pnach` | independent re-parse and re-read; fails on every lie the tests enumerate |
| `synthetic_source` / `conformance_edits` | a synthetic ELF in a synthetic ISO; hand-authored words |

Recipe (`nfl2k5_ps2_code_patch_recipe/v1`; addresses below are the **synthetic** ELF's):

```json
{"schema": "nfl2k5_ps2_code_patch_recipe/v1",
 "patches": [
   {"patch": "catch_slider", "parameters": {"enabled": true}},
   {"patch": "accel_ramp", "note": "hand-authored while the translation is proved",
    "mips": [{"address": "0x00100008", "original": "0x24020001", "replacement": "0x24020002"}]}
 ]}
```

The first entry is refused today (no translation); the second is planned, emitted and verified.
Emitted pnach (grammar PCSX2 reads and the owner's `bake_pnach.py` accepts — `word`, not
`extended`):

```
gametitle=ESPN NFL 2K5 (SLUS-20919) (CRC <pcsx2 crc of the ELF>)
comment=accel_ramp: hand-authored while the translation is proved
patch=1,EE,00100008,word,24020002
```

Command line: `python -m mod_editor.games.nfl2k5_ps2.code_patches --list | --crc <iso> |
--selftest | --source <iso> --destination <out.pnach> --recipe <recipe.json>`. `--crc` reads
the user's own ISO read-only and prints the ELF identity; on the retail disc it must print
`42F9D5AF`.

**Registration rule.** The lane joins `GAME.lanes` when its registry row is in the module's
fragment (section 8). Until then it is `CODE_PATCH_LANE`, covered by
`tests/mod_editor/test_games_ps2_code_patches.py` and its validators
`validate_code_patches.sh/.bat`, and it never appears as a capability the module claims.

## 5. Prior work that transfers (read-only; cited, not copied)

The owner's `nfl-online-revival` repository built the reverse direction — PS2 pnach → Xbox
XBE — for the online-revival patch. Direction reversed, most of its discipline transfers:

| there | role | what transfers here |
|---|---|---|
| `tools/bake_pnach.py` | parse a pnach and bake words into the ELF | the strict grammar (`patch=<0\|1>,EE,<addr>,word,<value>`; metadata keys; `[Section]` skipped; any other line refused; IOP/`byte`/`short`/`extended` refused); placement via program headers with `file-backed / bss / outside`; the on-disc delivery route when it is wanted |
| `tools/whichbin.py` | identify a binary from its own bytes | `pcsx2_crc` (word XOR) kept distinct from zlib CRC-32; provenance of a CRC (logged/shipped/derived); per-image segment and code-range registry — the shape our `elf_identity` should grow into |
| `tools/pnach_to_xbox.py`, `patches/xbox/site-map.json` | translate over a *reviewed map*, never discover | the per-site record: intent `{kind, value}`, stock and patched words with disassembly, status, evidence, doc — the schema our `TRANSLATIONS` entries and their evidence files should follow |
| `docs/pnach-to-xbe-pipeline.md` | the method | byte-level transcoding is impossible; recover *intent at a place*; cross-architecture function matching on **data anchors** (a 4-char immediate, an allocation size, a struct stride); edit kinds: **nop-out AUTOMATIC, immediate change ASSISTED, data word ASSISTED (and split), pointer/handle REFUSE**; instruction-level LOCATE is unproven |
| `tools/asm_r5900.py`, `docs/mips-assembler-requirements.md` | assemble R5900 through an oracle (keystone / binutils), never by hand | authoring replacement words and caves |
| `tools/verify_playbook_patch.py`, `verify_patch_core.py` | an independent verifier that re-derives every stock word | the check list: form, words present, stock words, cave extent, decode, built image, no collateral |
| `tools/patch_iso_elf.py` | put a baked ELF back into the disc, same size only | the on-disc route (we would use `tools/ps2_iso9660_writer.py` instead) |
| `docs/specs/boot-dnas.md`, `patches/42F9D5AF.pnach` | one proved SLUS-20919 site (the DNAS gate) | proof that the pipeline reached the real disc once |
| `pcsx2-VR/pcsx2/Patch.cpp`, `Patch.h`, `Elfheader.cpp` | PCSX2's pnach grammar and CRC | what PenguinScreen2 accepts; the CRC definition; `pcsx2/VR/CameraDriver.cpp` shows an in-emulator R5900 cave + trampoline pattern for a runtime-only delivery |

`nfl-online-revival` has no license file; nothing was copied, only cited. The Madden-side
toolkit there does not transfer (Visual Concepts engine, not Tiburon).

## 6. The honest effort shape

Per patch, in order: **locate** the intent in `SLUS_209.19` (disassembly plus data anchors —
the throw-tuning curves are `(x, y)` float tables with known values, the strongest anchors;
`catch_slider` is a 48-byte x86 cave plus a hook, the weakest); **classify** the edit kind (a
constant or a table is ASSISTED, a nop-out AUTOMATIC, anything through a pointer REFUSE until the
pointee maps); **author** the words (a table edit is words; a cave needs free file-backed
space in the ELF and an assembled R5900 body); **prove** them — hand-authored recipe → pnach →
`verify` → a runtime witness in PenguinScreen2 (a controlled before/after, as the M1 texture
witness was done); **encode** the translation as `TRANSLATIONS[patch_id]` with its evidence
file. Estimates: a table patch 1–2 days, a constant patch 2–3, a cave patch 5+ and possibly
refused. Twenty-one patches; the data-table ones first. It is going to be slow, and every step
is visible in the registry row's classification.

## 7. Filling in one patch — the steps a future PR takes

1. Pick the patch from `python -m mod_editor.games.nfl2k5_ps2.code_patches --list`.
2. Locate its site(s) in the user's own `SLUS_209.19` (never in a committed file); record
   the evidence as a site map in the style of `site-map.json` — intent, stock and patched
   words, disassembly, how it was found — under `docs/product/` with addresses **only** in the
   evidence file the row cites, never in code that ships.
3. Prove it by hand first: a recipe with `"mips": [...]`, `--source <iso> --destination
   x.pnach --recipe r.json`, then the witness in PenguinScreen2.
4. Add `TRANSLATIONS["<patch_id>"] = translator` in `code_patches.py` — a function from the
   host's parameters to `MipsWord`s (a table patch encodes the parameters into the words; a
   boolean patch returns fixed words) — and a test that the translator reproduces the
   hand-proved words and refuses out-of-range parameters.
5. `check_edit` and `build_catalogue` then report the patch as translated automatically;
   `translations_available` counts it.
6. Move the row (section 8) one rung: `offline-writer-proved` once the verifier passes on the
   real disc (`operation write`, `gui edit`, still hidden), `runtime-proved` once witnessed.
   Every rung change is a registry commit through `tools/registry_add_rows.py`'s successor
   for edits, and `python -m mod_editor.games fragments nfl2k5_ps2 --write`.
7. When enough patches are translated to be worth a window, the Disc Studio grows a tab that
   lists only translated patches; until then no UI claims anything.

## 8. The registry row — for the maintainer to apply

Classification `unknown` (the sites are not mapped), which the validator binds to
`backend.operation "none"` and `gui.mode "deferred"` with `expose false`; `runtime.status`
`not-applicable`. Surface **`gameplay_tuning_sliders`**: the host's executable patches are
overwhelmingly gameplay behaviour (catch and interception odds, acceleration, CPU drafting and
free agency, kicking and overtime rules, penalties, progression, returners, the camera), which is
what that surface names; the two text-changing patches (`edge_rename`, `scheme_labels`) already
have a PS2 route through the text-banks lane, and franchise/menu-flow patches would get rows on
their own surfaces when they are mapped. The surface is not yet PS2-covered, so the row lands
with `--widen gameplay_tuning_sliders`.

```json
{
  "backend": {"command": null, "module": null, "operation": "none"},
  "classification": "unknown",
  "evidence": ["docs/product/PS2_CODE_PATCH_PIPELINE.md"],
  "game": "nfl2k5_ps2",
  "gui": {
    "default_enabled": false,
    "expose": false,
    "mode": "deferred",
    "reason": "Nothing is translatable today: none of the host's 21 executable patches has a located site in SLUS_209.19, and no Xbox address transfers to the MIPS build. The lane's interface, pnach emitter and independent verifier exist and are proved on a synthetic ELF; the row moves off unknown one patch at a time as translations are proved, and no window lists a patch before then."
  },
  "id": "nfl2k5ps2.gameplay.executable_patches",
  "input_constraints": [
    "No host patch is translated to MIPS yet; every translation is refused with the reason, and nothing here changes a disc or an emulator until one is.",
    "Delivery is pnach-first: a PCSX2 / PenguinScreen2 .pnach named by the ELF's game CRC, applied at load time; on-disc ELF patching through the fixed-allocation ISO writer is a later, optional second route, and a .bss address can never be delivered on disc.",
    "A recipe may carry hand-authored MIPS words for maintainers; every word is checked against the user's own boot ELF (file-backed address, original word as expected) before a pnach is written, and the pnach is re-parsed and re-verified independently afterwards.",
    "The boot ELF is read from the user's own ISO read-only; its serial, digest and PCSX2 CRC are reported; a synthetic or modified ELF is never called retail."
  ],
  "portme": [
    "Locate each host patch's intent in SLUS_209.19 by data anchors and disassembly, never by Xbox address arithmetic; record the site map as evidence.",
    "Classify each edit (nop-out, immediate, data table, pointer) and author the MIPS words through an assembler oracle; hand-prove them as a pnach, then witness them in PenguinScreen2.",
    "Encode each proved translation as TRANSLATIONS[patch_id] in mod_editor/games/nfl2k5_ps2/code_patches.py with its test; move this row one rung per proof.",
    "Add the on-disc delivery through tools/ps2_iso9660_writer.py once a translation is runtime-proved and a user asks for real hardware."
  ],
  "public_distribution": {
    "game_data": "never-bundle-retail-data",
    "mod_payload": "none-until-safe",
    "rule": "Ship the lane, the shared ELF/pnach package, the validators and this document; no address of retail code ships in code, and no pnach ships until a translation is proved. User-authored recipes and the pnach files built from them stay with the user.",
    "tooling": "source-and-schemas-only"
  },
  "runtime": {
    "evidence": [],
    "scope": "Not applicable: no translation exists, so nothing has been applied in an emulator or on hardware. The synthetic-ELF proof covers the pnach emitter and verifier only.",
    "status": "not-applicable"
  },
  "selectors": {
    "fields": [
      {"allowed": "one of the host's executable patch ids (python -m mod_editor.games.nfl2k5_ps2.code_patches --list)", "name": "patch", "required": true},
      {"allowed": "the host's parameter names and ranges for that patch", "name": "parameters", "required": false},
      {"allowed": "hand-authored words {address, original, replacement}, maintainers only, checked against the user's ELF", "name": "mips", "required": false}
    ],
    "notes": "One recipe entry delivers one host patch; a translated patch takes parameters, an untranslated one is refused unless hand-authored words are supplied. Selectors name intent and words, never Xbox addresses."
  },
  "source_container": {
    "format": "ELF32 little-endian MIPS boot executable SLUS_209.19 inside the ISO9660 image; delivered as a PCSX2 .pnach keyed by the ELF's game CRC",
    "hash_pins": [
      "e8c3ba9a3224d567e3abb50c91e9d6fdd9820138226c05e525f9dbf34a47d8aa",
      "f1300699ab445ad04b1e27f6e2df87f7a4d1d080d06c7d73499e1be9618a4ebe"
    ],
    "resource": "32-bit words at EE virtual addresses in the boot ELF; 0 of the host's 21 executable patches mapped",
    "retail_file": "User-owned ESPN NFL 2K5 (USA) PlayStation 2 ISO, SLUS-20919 NTSC-U v1.01"
  },
  "summary": "Deliver the host's Xbox gameplay executable patches to the PlayStation 2 release as PCSX2 / PenguinScreen2 pnach files built from MIPS words checked against the user's own SLUS_209.19. The interface, the pnach emitter and the independent verifier exist and are proved on a synthetic ELF; no host patch is translated yet, so every translation is refused with the reason.",
  "surface": "gameplay_tuning_sliders",
  "title": "NFL 2K5 (PS2) executable patches (pnach-first; nothing mapped yet)",
  "validation_command": "bash mod_editor/games/nfl2k5_ps2/validate_code_patches.sh"
}
```

Apply (from the repository root; the row JSON saved as `rows/nfl2k5ps2.gameplay.executable_patches.json`):

```bash
python3 tools/registry_add_rows.py --game nfl2k5_ps2 \
    --row rows/nfl2k5ps2.gameplay.executable_patches.json \
    --widen gameplay_tuning_sliders \
    --module mod_editor.games.nfl2k5_ps2.code_patches --module mod_editor.games._formats.ps2_elf
python -m mod_editor.games fragments nfl2k5_ps2 --write     # the lane joins GAME.lanes; pins lanes_on_contract 1 -> 2
python3 mod_editor/capabilities/validate_registry.py --skip-file-checks
python -m mod_editor.games conformance --game nfl2k5_ps2
```

Counts the tool moves: rows +1, covered unchanged (`unknown` is not covered), unique validators +1.

## 9. What is deliberately not built

No tab, no menu entry, no window: nothing lists a patch as available. No on-disc delivery. No
translation. No real-disc run is recorded here; `--crc` against the owner's own ISO is the
one-line read-only check that the identity constants in this lane match the disc
(`42F9D5AF`), and it belongs in the PR that lands the first translation.

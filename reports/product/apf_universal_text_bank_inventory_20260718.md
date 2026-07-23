# APF 2K8 Mod Studio — complete archive string-bank inventory

Date: 2026-07-18

## Product result

The bounded text provider now owns every resource whose archive type is either
`TXT loc system` or `STRG`. The complete four-volume directory contains exactly
four such banks: two of each type. All four are indexed as individual pool
allocations, exportable as text, and writable under one fixed-allocation
contract. No recognized `TXT loc system` or `STRG` bank remains hidden or
preview-only.

| Archive resource | Type | Records | Pool allocations | Editable | Read-only |
| --- | --- | ---: | ---: | ---: | ---: |
| Outer 185 / inner 20, `artist_bio_english` | `STRG` | 13 | 13 | 13 | 0 |
| Outer 526 / inner 0, `credits_English` | `TXT loc system` | 747 | 742 | 741 | 1 |
| Outer 810 / inner 87, `strings` | `STRG` | 1,492 | 1,106 | 1,105 | 1 |
| Outer 1127 / inner 0, `English` | `TXT loc system` | 825 | 552 | 551 | 1 |
| **Total** |  | **3,077** | **2,413** | **2,410** | **3** |

The two localization pool-zero fallback sentinels remain read-only. The global
STRG bank also has one referenced empty allocation whose original capacity is
zero UTF-16 code units; it cannot safely hold user text and remains read-only.
Those are structural limits, not missing writer work.

## Writer contract

- Stable selector: `apf:text-pool:<outer>:<inner>:<pool>`.
- Replacement limit: the original allocation's UTF-16BE code-unit capacity.
- Embedded NUL values are rejected. Non-BMP characters consume two units.
- Shared strings are edited once at their underlying allocation and update all
  referring records; the inventory reports the exact reference count.
- Record IDs, record order, pool order, control rows, inner-file offsets, block
  decoded lengths, outer extents, and the name footer remain fixed.
- A shorter STRG replacement compacts the pool, rebuilds every relative
  pointer, and turns the released bytes into a zero trailer so the decoded part
  remains exactly its original length.
- STRG lives in shared H7A blocks. The writer recompresses the complete owning
  block, rebuilds all IFF block offsets, then proves that only the selected
  STRG inner part changed. It uses a denser bounded H7A search because both
  outer allocations are tighter than ordinary texture containers.
- The source archive is opened read-only. A successful compile returns one
  fixed-size outer-entry replacement in memory. Receipts contain coordinates,
  sizes, counts, and hashes only—never retail strings, retail bytes, or user
  replacement bytes.

## Completed live experiments

The complete inventory against the untouched USA archive found 2,413 pool
allocations: 2,410 editable and three structurally read-only. Source-free tests
cover both formats, aliases, exact-size pointer rebuilding, surrogate-pair
limits, zero-capacity refusal, fallback refusal, and hashes-only receipts.

One user-authored `MOD` replacement was independently compiled in each STRG
bank:

- Outer 185 remained exactly 552,960 bytes. Its 43,136-byte STRG part reparsed
  byte-stably and every unrelated inner part retained its original hash.
- Outer 810 remained exactly 913,408 bytes. Its 160,384-byte STRG part reparsed
  byte-stably and every unrelated inner part retained its original hash.
- The source `0A` SHA-256 was identical before and after both experiments.

The global STRG edit also passed the real Mod Studio path: Replace, retail-free
`.apf2k8mod` save, compile, complete separate-game build, changed-entry reparse,
outside-entry byte comparison, and atomic publication. The 961-byte project
contained one JSON replacement plus its manifest and declared that it contains
no original game bytes. The separate built game is private retail-derived data
and must never enter a release package.

## What this does not claim

This closes the archive resources explicitly typed as localization/string
banks; it does not claim that every textual concept in the game uses those
four formats. `ROST`, `CRED`, `LAYT`, font/kerning resources, executable
literals, and numeric resource selectors use different grammars and must stay
in their own capability lanes. Treating their incidental names or printable
bytes as STRG allocations would be unsafe.

- `ROST`: player/team identity needs its own field-aware writer.
- `CRED`: typed credit/event data is not binary-compatible with either bank
  grammar; keep it browsable until its record ownership is mapped.
- `LAYT`, `FONT`, and `KERN`: layout and glyph data are not universal prose.
- Direct executable labels: outside the archive and subject to a separate
  emulator-only bounded-literal route.

The best next universal-text step is to inventory proven user-facing string
fields inside those structured types one format at a time, while keeping this
four-bank provider unchanged and fail-closed.

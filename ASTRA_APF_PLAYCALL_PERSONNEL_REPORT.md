# APF CPU play calling and personnel — 2026-09-09

Branch: `astra/apf-playcall-personnel`. Runtime status of every new lever:
**UNWITNESSED**. No emulator, game, display, audio, or network game download
was used. Retail inputs were opened read-only. Reconstructed images and
generated patches stayed outside the repository. The instruction words below
are the brief's requested, selected static evidence; no executable, resource,
save, or decompressed retail payload is included.

## Result and correction to the prior premise

The earlier “both” Queens experiment did **not** remove every Queens category
reference from the records. Its three repointed records retained bit 6 in
trailer word B. A traced game normalization routine rebuilds the book mask
from primary categories **and word B**, and can therefore put Queens back in
the advertised categories. This is an **A_PROVEN conditional producer**, not
proof that it executed during the reported 3/27 failures. That causal step
remains **UNKNOWN** without a runtime witness.

There is no four-entry formation descriptor table at the proposed loop.
`0x8486CF5C` retries a category choice four times. The ordinary CPU path then
calls weighted picker `0x8486B2D0`; only its last-resort path calls
`0x848699D8`, with subtype -1. The new hook at `0x84869B20` consequently cannot
be described as a general CPU third-and-long fix. It is a bounded, assembled
**pass-fetch experiment at every down**, including user calls. Its main CPU
weighted path and untyped emergency fetch are unaffected.

Delivered code:

* `mod_editor/core/apf2k8_audibles.py`: minimum same-record audible tag moves,
  metadata classification, before/after census, existing H7A writer and
  independent reparse gates, and a JSON recipe/receipt CLI.
* `mod_editor/core/apf2k8_playcall_patch.py`: BASE and TU 1.1 SHA-pinned patch
  generator, 716-byte PPC cave, independent Capstone/branch verification,
  atomic TOML export and exact TOML reparse.
* `mod_editor/core/apf2k8_splb_writer.py`: compile and independent verifier
  guards; 28-category personnel availability before/after; secondary-mask
  normalization warnings, hidden records, duplicate formation resolution,
  and stale cached-play diagnostics.
* `mod_editor/apf_studio/playbook_playcall_qt.py`: tested standalone panel with
  book preview, audible staging, personnel table, and patch export. Protected
  GUI integration is deliberately left to the exact `WIRING.md` additions.
* `tools/apf_playcall_audit.py`: reproducible retail census and fully offline,
  hash-checked LIVE/STFS → XEXP delta → TU flat-image reconstruction.
* `docs/research/apf_playcall_receipt.json`: compact per-record before/after
  counts, audible selectors, per-book personnel tables, hashes and proofs.

The panel is implemented and tested offscreen; it is **not yet registered or
rendered by the protected main GUI**. `WIRING.md` and the proposed capability
fragment specify that remaining integrator work. No protected file was edited.

## Job 1: evidence grades and research coverage

**A_PROVEN** means the named data or instruction is present in the pinned
image and implements the stated operation. **B_INFERENCE** means its proposed
relationship to the reported game behavior needs an additional observation.
**UNKNOWN** is not promoted to either grade. Static ability, runtime reachability
in a particular game mode, and observed personnel on the field are separate.

All BASE addresses use **file offset = VA − 0x82000000**, never PE raw section
offsets. BASE SHA-256 is
`cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`.
Signed `lis`/`addi` address construction matters: the subtype UI table is at
`0x84DBB2A8`, the substitution table at `0x84E6CAC0`, and the role ladder at
`0x820B9080`. The earlier broad “.data cave” description is also corrected:
the chosen reservation is zero **.text alignment padding**.

### The Queens mask can be regenerated from the supposedly removed records

The private historical kit is
`/home/noah/.codex-tmp/franchise-2026-08-28/agentF/`. Its `build_witness3.py`
uses `TrailerReplace(130,2,4,3)`, `(130,9,16,3)`, `(130,14,26,3)` and manually
clears the book mask's bit 6. Trailer replacement adds category 3 to word B;
it does not clear category 6. The actual `witness3_splb130_body.bin` SHA-256 is
`01a0bda3635ba969de52579df3e93578dc11015439d77e06d48868edc4f9358d`.

| Object | Recorded result | Grade |
| --- | --- | --- |
| Repointed records 2, 9, 14 | Primary category 3; formation IDs 4, 16, 26; word B still includes category 6 | A_PROVEN |
| Stored post-edit book mask | `0x0400000B`, categories 0, 1, 3, 26 | A_PROVEN |
| OR of populated primary categories and secondary memberships | `0x0400004B`, restores Queens/category 6 | A_PROVEN |
| Normalizer `0x84A8C790` | Clears category, formation and play caches, compacts records, rebuilds masks from records, and repairs tags | A_PROVEN |
| Why Queens occurred in 3/27 reported calls | Normalizer execution or another producer during those calls | UNKNOWN |

At `0x84A8CB6C` the normalizer reads primary word A; at `0x84A8CBB0`,
`0x84A8CC00`, `0x84A8CC4C`, `0x84A8CC90` it reads secondary word B and folds
all 32 bits back into `book+0x7E04`. Its eight direct callers in the scanned
text are `84A47880`, `84A48898`, `84A8D2A4`, `84A8D728`, `84A8D87C`,
`84A8DBAC`, `84A8F038`, `84A8F15C`; the first two are book-edit menu paths,
the others book mutation helpers. An on-load invocation during that CPU
witness was **not** established. If the mask and **both** category fields
really exclude Queens, this normalizer cannot invent category 6.

The new receipt exposes `normalization_restores_category_indices`. This is a
useful third control to inspect before another personnel experiment. No new
word-B clearing editor is shipped: the brief's requested writers are audible
tags, the code patch, and compile guards; removing category supply deserves
an explicitly reviewed normalization/cache update rather than an OR-only
trailer operation pretending to remove it.

### Retry selector, situation input, and special cases

`0x8486CF78` increments a retry counter from -1 through 3. The counter is
never passed to `0x8486C930` or used to index a descriptor. C930 consumes a
MASTER formation pointer or null. Formation `+4 >> 26` dispatches to offense,
defense or special-team logic. With null formation it reads manager
`0x851A2780+0x34` (mode). The tables at `0x8486C980` (13 entries) and
`0x8486CA0C` (4 entries) contain **code addresses**, not formation/category
descriptors. C930 returns a MASTER **category** pointer.

Hardcoded row requests are punt 17, generic special row 25, kickoff 21,
onside 22, and field goal 19. `0x8486AEB0` still walks the book's advertised
categories (`84A89B40`/`84A89C30`), checks record word-B membership via
`84A8A330`, and weights the candidates with `84869318`/`84863388`.
There is no proved independent literal Queens/default formation table here.

The traced `0x84815608` wrapper sets r4 to `0x85158350+0x10`, an **output
staging object**. The picker saves that pointer in r23 and writes category at
`+0`, formation at `+4`, play at `+0xC`. Following r4 does not reveal live
down or yards-to-go. The separate global `0x84F3F8F8` supplies `+0x2BC` tab
and `+0x1F8` UI play subtype. Neither is a formation/category index.

Practice controls at `84A37524..53C` and `84A37850..87C` expose candidate
down/yard fields `+0x254`/`+0x25C` on that UI global. Live manager `+0x6C`
leads to a state whose `+4` is compared with 4 (`8486BF20`); vector/float
readers use `+0x10`, `+0x18`, `+0x20`, `+0x28`. A subtraction and absolute
value at `84868D98..DA0` plausibly measures distance. **B_INFERENCE:** down
and distance representations. **UNKNOWN:** their units, live possession
ownership and freshness at this fetch. The cave does not test these fields.

`84A3CEC8` provides a separate mode-9 override: it reads a pointer at
`0x85214608+0x118` and the object's row byte `+6`, excluding row 13. This is
an **A_PROVEN non-record row request**. Its specific CPU-game ownership is
UNKNOWN, and the subsequent category selection still uses the book.

Special cached formations are real, but their origin was traced. State
`playcall+0xC` holds `+0x50/+0x54` special formation/category, `+0x58/+0x5C`
offensive Hail Mary formation/category, and `+0x60/+0x64` defensive Hail Mary
formation/category. Constructor `84864CA8` walks this book's plays and
formations using `84A89E08`/`84A89EA8`, detects flags 0x400, 0x8002 and
0x8000, and derives categories with `84A8C5B0`. It is not a separate default
formation catalog. Picker `D008`/`D01C` reads the cached forms; the common
temporary pair `+0x680` play / `+0x684` formation transports a special choice.
“Safety Kick” lookup (`8486BD4C`) goes through `84A8B5C8`, which searches the
book's contiguous record prefix. The kickoff and Hail Mary D strings likewise
do not establish an independent offensive “Hail Mary 01” producer.

**B_INFERENCE:** a cache initialized before an in-memory edit could retain an
old formation. **UNKNOWN:** whether that happened in the historical test.
Cold-loaded record/mask exclusion is not disproved by a cache populated from
the same edited records. Two-minute/goal-line policy can request a row; no
separate down/distance `.rdata` formation descriptor array was found in the
traced paths. This is a bounded negative finding, not a whole-program proof
that no indirect/default provider exists.

### Category, formation, lineup and Subs are different objects

MASTER has 28 categories (base `+0x44`, stride 16), 163 formations
(base `+0x244`, stride 184), and 586 plays (base `+0x80C4`, stride 100).
`84A8C5B0` maps a formation pointer through the **first** matching SPLB
record and loads its primary category. `84A8A258` and formation iteration
stop at the **first empty record**. `84A89EA8` is the next-formation iterator,
not a chosen-entry-to-record mapping as the older document said.

`84A8B438` tests the book category mask then compares MASTER category `+4 &
63` with the requested **row**. It does not itself inspect record word B;
`84A8A330` does that membership check. Category ID and row are not
interchangeable: Load/category 26 and category 0 share row 0, for example.
The offensive fallback ladder is the six signed deltas **+1, -1, +2, -2,
+3, -3**, clamped to rows 0..10 (defense 11..16), not a monotonically
“lighter personnel” list. Stock Ace's lack of Straight/category 7 is a useful
availability observation, not proof of a specific later lineup.

Lineup builder `84860020` receives **r4 = category**, r5 = formation. Its
`848605B4` load reads the category's 11 role bytes beginning at `+5`, not
the formation's `+5`. `8485E768` stores slot role/depth, and `847B2DA0`
resolves roster players. Compatibility helper `84A9BFD8` also consumes the
category row and counts back roles through `84A9AD08`. The owned writer's
research comments have corrections at the top; older static notes are not
silently promoted to runtime proof.

Subs supplies an independent way to put a different player role in a slot
without changing the category label. `book+0x7998` contains **256 packed
32-bit entries**, scanned by `84A8ACE8..AD68`, with at most 12 matches.
Bits 12..13 select scope; bits 2..11 hold the category or formation selector.
`847B2E60` requests category scope 1, `847B2E8C` formation scope 2. A mode-1
global override at `0x84D5CED0` merges via `84A9B010`.

`84A9B158` additionally uses a **12-entry, 8-byte (count, pointer) table** at
`0x84E6CAC0`. The two caller preset selectors select offensive back/receiver
groups or defensive groups, with -1 meaning no preset. The stock entries
contain 13 packed substitutions total (one entry has two); they include
same-role depth changes, a back-role change, and defensive changes.
They do **not** contain an automatic TE-to-WR preset. The TE preset is role
8/depth 0 to role 8/depth 1. The generic executor `84A9B2D0` handles operation
kind from bits 30..31, source bits 22..29, target bits 14..21, reversal bit
1; kind 1 is slot-indexed, other kinds compare packed role bytes. Role low
five bits and depth high three bits are consumed at `847B2F3C`/`847B2F50`.

**A_PROVEN:** a supplied slot/role override can replace a TE role with a WR
role while the category and formation remain unchanged. This can yield zero
TE personnel even if no zero-TE category is advertised. It does **not** prove
an absent MASTER formation ID was selected. **UNKNOWN:** actual active Subs,
depth/package inputs and branch execution in the reported CPU games. Across
the 15 stock books, the simple direct role-8-to-non-8 check found zero entries;
that limited check does not prove every reverse/slot-indexed combination safe.

The normalizer also processes two tail arrays at `book+0x7970` and `+0x7984`,
each **five 4-byte items** (formation byte, opaque byte, play u16). It validates
them against rebuilt formation/play masks. These are additional stored
formation selectors, not the alleged four descriptors; their selection in
the live CPU path remains UNKNOWN. Their opaque byte is not assigned a name.
Repair fallback `84A8CE64` calls `84A8B880` with a static **row priority list**
at `820FC298`: 4,3,5,6,7,8,9,10,2,1,0,17,19,25 (14 signed words, terminal
25). The second tail uses `820FC2D0`: 13,14,15,12,11,16,18,20,25 (9 words).
`84A9AE28` reads the first row; `84A9AE30` finds the previous row and reads
the following one; `84A9AE58` tests row validity. **A_PROVEN:** these are
repair priorities, not down/distance descriptors or MASTER formation IDs.
`84A8B508`/`B538` still resolve the row through the book mask; `84A8B90C`
checks the candidate formation's word B. They cannot by themselves advertise
a genuinely absent category, although they can request Queens's row 7.

### Exhaustiveness boundary and next decisive witness

The instruction appendix enumerates all **11 direct branches to 84860020**
found in the scanned text, and their argument provenance. Direct category
arguments exist in UI/dialog wrappers and cached objects; the graph is not
closed for every virtual/indirect upstream caller. A multiplication-by-184
scan found 28 sites, listed below, including record iterators, MASTER accessors,
edit paths and the two tail arrays. A `lis`/add/load cross-reference scan and
the descriptor, special-cache, row, Subs and builder call chains were inspected.
This is not an assertion that every formation/category load in all 54 MB,
including computed addressing or VMX code, has been exhaustively classified.

The brief's demand for an unconditional identification of **the** producer
responsible for 3/27 cannot honestly be met by this static evidence. The
precise unresolved edge is execution of `84A8C790` (or cached/override paths)
between book load and the final `84860020` call. The next witness should
capture book mask, selected record word A/B, chosen category/formation, active
Subs and final 11 roles at that boundary, and record whether C790 ran.
Repeat with primary **and secondary** Queens membership removed and caches
recomputed in a controlled copy. That distinguishes category resurrection,
stale formation cache and role substitution; a formation name alone does not.

## Job 2: audible fixer, guards and personnel receipts

The three proved CPU tags are **Y=0,1,2**. Urianus's 2026-09-05 21:50 report
describes four preset audibles and mostly run choices; this implementation
does not pretend that proves a fourth CPU tag writer. It preserves Y=3 unless
that is the only same-record source of a missing kind. The initializer at
`84864BF4..BFC` skips an already-present requested tag; its fill loop is not
proof that the CPU actually selects every authored audible in game.

Metadata classification uses MASTER play `+4 >> 28` as family (0 offense),
and `+8 & 0xA` equal to 8 for run or 2 for pass. Ambiguous flags are unknown;
special/defensive families are not mistaken for runs. No play-name heuristics
are used. A deterministic swap keeps at least one audible of the other kind,
prefers an ordinary donor, preserves X/play IDs/order/trailers, and uses the
existing TagMove writer. It never borrows a play from another record.

| Outer | CPU book | Records | Balanced before | Balanced after | Tag moves | Impossible records |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 130 | O-ManBlock | 23 | 3 | 23 | 20 | none |
| 259 | O-TwoBack | 25 | 3 | 25 | 22 | none |
| 369 | O-SinglebackAce | 17 | 0 | 13 | 13 | 8, 9, 10, 13 |
| 767 | O-Singleback3WR | 27 | 0 | 27 | 27 | none |
| 891 | O-WestCoast | 22 | 0 | 22 | 22 | none |
| 943 | O-ZoneBlock | 17 | 4 | 17 | 13 | none |
| 1411 | O-Shotgun | 23 | 0 | 15 | 15 | 13 through 20 |
| **Total** | | **154** | **10** | **142** | **132** | **12 pass-only** |

All **142/142 eligible records** balance. The 12 others have no run in their
own entries, so the requested universal guarantee is impossible without
violating the same-record constraint. Replanning every output yields zero
moves. The tag changes alter exactly **264 SPLB bytes** in total.

All seven rebuilt entries occupy their original **2,048-byte allocations**.
Each passed independent SPLB reparse, exact H7A decode equality and an
independent descriptor walk asserting **length <= distance** for every
backreference. Counts of checked matches by book: 320, 334, 239, 266, 235,
236, 263. Per-record before/after run/pass/unknown/special counts and tag-to-play
IDs are in the compact receipt; full local JSON is `/tmp/astra-audit.json`.

The compile and independent verification gates refuse newly introduced:

1. Emptying both known stock twins: Ace 62/63 or Quads 69/70.
2. Removing all ordinary plays from a previously ordinary-bearing record
   while leaving only tags. Legitimate pre-existing short retail records are
   accepted; audible moves do not make them newly unsafe.
3. Empty records hiding previously reachable or newly populated later
   records. The runtime's first-empty sentinel makes holes materially unsafe.
4. Loss of all reachable, word-B-compatible formation supply for a previously
   answerable advertised category. Errors name the category and row.

These are conservative edit guards backed by code and the community's
reported failures, not a new in-game proof of every hang mechanism. Clearing
a trailing record can still succeed if it does not lose category supply or
empty both twins. Existing defects are reported without making unrelated
tag edits impossible.

The before/after availability table reports all 28 categories, their distinct
rows, mask advertisement, first-resolvable member records, primary records,
ordinary play counts and stock TE roles. It also reports hidden/duplicate
records, hypothetical mask regeneration and cached plays missing from records
or records missing from the cached play union. It does not silently rewrite
`+0x7DB0`; existing membership edits can leave that cache stale. Audible-only
changes preserve membership, and no cache mismatch appeared in these seven
retail results. All 15 retail books had contiguous populated prefixes.

| Book | Advertised category IDs (unchanged) | Answerable rows (unchanged) |
| --- | --- | --- |
| 130 / 259 / 891 | 0,1,3,6,26 | 0,2,4,7 |
| 369 | 0,1,2,8 | 0,2,3,9 |
| 767 | 2,5,8 | 3,6,9 |
| 943 | 0,2,3,5,8 | 0,3,4,6,9 |
| 1411 | 0,1,2,3,5,6,7,8,9 | 0,2,3,4,6,7,8,9,10 |

The panel stages through the existing facade and selector-only project
payloads. It refuses to replace a selected book's pre-existing staged edits;
it shows their compiled result and asks the product user to build or revert
that book before balancing. Other books' edits survive through
`replace_outer`. This conservative choice avoids incorrect composition of
tag moves with removals because the existing writer orders moves before
membership removals. Source/generation and staged-change snapshots are
rechecked immediately before staging. No new build provider is needed.

## Assembled pass-fetch TE experiment

At the hook, r24 is family, r27 subtype, r28 candidate count, r29 book, r30
optional MASTER formation pointer. The array at original SP+0x50 contains
**MASTER play pointers**, not SPLB entries. The original code has already
filtered and reservoir-sampled at most 40 candidates; no preference can
recover eligible plays absent from that buffer.

The cave admits only family 0, subtypes 2/3/4 and counts 1..40. It validates
the book/MASTER pointers, retail layout counts, candidate range/alignment and
pass flags. It scans the 176-record contiguous prefix, matching the optional
formation filter, primary category and word-B/book-mask membership, then
checks the category's actual 11 MASTER role bytes for TE role 8 and searches
up to 84 entries for that play. Stable matches go into a private 40-pointer
temporary array. Only a completed, nonempty preferred set commits a compacted
prefix and smaller r28 count. Zero matches or a malformed candidate preserve
the full original buffer/count. Later resolver choices, shared plays,
duplicate formation records and Subs can still produce a lineup without a
TE. This is preferred eligibility, not a forced lineup.

A new 0x200-byte stack frame uses a 64-bit backchain and 64-bit GPR saves.
r0, r3..r12, r14..r23 and CR are preserved. r28 changes only on a successful
compaction. The displaced `lis r11,0x8506` is replayed before return. LR, CTR,
XER, FPR and VMX state are untouched. No extra RNG call is introduced; the
original `rand()%count` selection runs afterward. Worst-case scan cost and
actual game performance remain UNWITNESSED.

| Identity | BASE | TU 1.1 |
| --- | --- | --- |
| Flat image bytes | 54,001,664 | 54,001,664 |
| Flat image SHA-256 | `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf` | `65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457` |
| Xenia module hash | `5447E5428AA2D52A` | `CEA825F7C2012F5A` |
| Hook | `84869B20` | `8486A820` |
| Original word | `3D608506` | `3D608506` |
| Authored hook branch | `484A44E0` | `484A37E0` |
| Fetch span SHA-256 | `63cb56f27978d22cf5193451f1da41368f1c16db3cfc69738e381c94d4cd51b9` | `d0994a6daf4d6e43c2210940e4cd67a22886d4261688a9d19b372e426e866561` |
| Cave SHA-256 | `3eb4432906753a6f1944123a7d70477747ae051ff114714f7585a0ac3ccd1db8` | `b1fd90d6fd5caf274aaccf68dd6e5684c0cfbaef14c44ceb1029c058c53f9a68` |

The cave occupies `84D0E000..84D0E2CB` (716 bytes, 179 instructions).
The entire reserved range `84D0E000..84D0EFFF` must be zero before patching;
its 4,096 zero bytes hash to
`ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7`.
Capstone decodes every instruction; 34 direct branches have independently
computed, checked destinations. No indirect/linking/absolute branch is
accepted, and the payload must equal the reviewed assembler output. Whole
image SHA, complete fetch span, original hook and zero reservation are all
checked, including synthetic negative tests.

The franchise example declares a broad `84D09100..84D10000` reservation even
though its current actual writes leave this page empty. **WIRING integration
must allocate E000..EFFF to this patch explicitly** and exclude any overlapping
owner; do not assume independent zero-at-source checks detect combined TOML
conflicts. No other worktree or allocator was changed.

### TU reconstruction and module hash verification

The pinned LIVE package SHA-256 is
`5f71cdf4ec679f8e33fd95e02ff2b67981fbf918d4d03a2099576734c5cfb42b`.
Its `default.xexp` is 776,192 bytes, SHA-256
`14e272063536656d2aae9b4743fdcebb927566722dc1e2f34fe75029e1e8ada6`.
It is a delta, not a standalone executable. `tools/apf_playcall_audit.py`
reconstructs it using the installed local Xenia source's existing mspack
decompressor, a small authored memory adapter, and cryptography. It verifies
the STFS hash tree (191 data blocks), source identity/signature digest, 12
delta block SHA-1 hashes and 3,779 delta records, then pins the entire result.
It does **not** claim to authenticate an RSA signature.

The existing roster STFS helper incorrectly treats a LIVE **parent hash
table** status as a data-block allocation status at
`tools/apf_stfs_roster_extract.py`'s `_level_zero_table`. The private adapter
relaxes only that status check, only for the exact pinned package, retaining
the top/parent/data hashes. The general roster reader is unchanged.

To reproduce Xenia's module identity, hashing must happen after its 334
kernel import thunks are resolved. The tool mirrors
`src/xenia/cpu/xex_module.cc::SetupLibraryImports` and
`src/xenia/kernel/user_module.cc::CalculateHash` using the existing local
source. It reproduces the already-known BASE hash before accepting the TU
hash. A raw XXH3 of the unprocessed flat code would give the wrong identity.
The TU fetch is relocated by +0xD00 and verified in full, including its
relocated RNG call. Neither Xenia nor a game was executed.

## Validation and reproduction

Current environment: Python 3; PyQt5 offscreen; Capstone **5.0.7**. Synthetic
tests contain authored structures/instructions, never retail fixtures. The
instruction test interpreter executes only this leaf cave over synthetic
RAM; it is not a launched game or console emulator.

```text
python3 tests/mod_editor/test_apf_playcall_patch.py
Ran 11 tests in 1.673s — OK

python3 tests/mod_editor/test_apf_cpu_audibles.py
Ran 18 tests in 2.646s — OK

python3 tests/mod_editor/test_apf_splb_tag_reassignment.py
Ran 86 tests in 1.403s — OK (skipped=5)

python3 tests/mod_editor/test_apf_splb_writer.py
Ran 22 tests in 0.187s — OK

PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_splb_add_multiple_formations.py
Ran 14 tests in 0.301s — OK

python3 tests/apf_h7a_no_overlap_test.py
Ran 4 tests in 17.479s — OK (skipped=1)
```

The new retail audible test checks all seven books when the precise local
retail path exists (or `APF_RETAIL_0A` names it), otherwise raises a precise
SkipTest. Existing skips remain existing optional paths. The two touched
legacy test scripts gained repository-root bootstrapping so they run with
plain `python3`, as CI requires. Four formerly permissive clearing tests now
cover the guarded transitions and safe trailing clear.

Tests cover stable compaction on BASE/TU, zero preference, all 40 slots,
subtype/family boundaries, malformed candidate after a provisional match,
full 84-entry/176-record limits, first-empty termination, category/mask/form
filters, null pointers, 64-bit GPR and CR preservation, immutable book/MASTER,
branch corruption, production SHA rejection, occupied caves and idempotent
atomic TOML export. Audible tests cover metadata, minimality, impossible
records, tag 3, category vs row, secondary-mask regeneration, duplicates,
all guard transitions, reparse tampering and stale panel plans.

The full retail/TU audit was run with:

```bash
python3 tools/apf_playcall_audit.py \
  --index '/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A' \
  --base-image /home/noah/.codex-tmp/franchise-2026-08-28/apf.pe \
  --report /tmp/astra-audit.json \
  --compact-report docs/research/apf_playcall_receipt.json \
  --patch-dir /tmp/astra-playcall-patches \
  --base-xex '/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/default.xex' \
  --tu-package '/home/noah/Desktop/2K5-8 Editors/discord-export-2026-08-21/urianus-nognow/attachments/1537136446190788658_0_TU_1A58207_0000008000000.0000000000082' \
  --xenia-source /home/noah/.codex-tmp/xenia-slot43-build \
  --tu-output /tmp/astra-audit-tu-v2.pe
```

```text
130 O-ManBlock: 3 -> 23 / 23 balanced, 20 moves, 0 impossible; allocation=2048; H7A/reparse/no-overlap/idempotence PASS
259 O-TwoBack: 3 -> 25 / 25 balanced, 22 moves, 0 impossible; allocation=2048; H7A/reparse/no-overlap/idempotence PASS
369 O-SinglebackAce: 0 -> 13 / 17 balanced, 13 moves, 4 impossible; allocation=2048; H7A/reparse/no-overlap/idempotence PASS
767 O-Singleback3WR: 0 -> 27 / 27 balanced, 27 moves, 0 impossible; allocation=2048; H7A/reparse/no-overlap/idempotence PASS
891 O-WestCoast: 0 -> 22 / 22 balanced, 22 moves, 0 impossible; allocation=2048; H7A/reparse/no-overlap/idempotence PASS
943 O-ZoneBlock: 4 -> 17 / 17 balanced, 13 moves, 0 impossible; allocation=2048; H7A/reparse/no-overlap/idempotence PASS
1411 O-Shotgun: 0 -> 15 / 23 balanced, 15 moves, 8 impossible; allocation=2048; H7A/reparse/no-overlap/idempotence PASS
TU reconstruction: 12 block hashes, 3779 deltas, BASE/TU Xenia identities PASS
Derived receipt: /tmp/astra-audit.json
```

Choose a **new** outside-repository `--tu-output` on a later run. Without TU
arguments the same tool produces the census and BASE patch only. The compact
receipt is reparsed and compared with its structured source before writing.
Generated authored patch files are
`/tmp/astra-playcall-patches/54540807-base-pass-fetch-te.patch.toml` and
`/tmp/astra-playcall-patches/54540807-tu-1-1-pass-fetch-te.patch.toml`.

Independent exports, with no game-file writes:

```bash
python3 -m mod_editor.core.apf2k8_playcall_patch --image /home/noah/.codex-tmp/franchise-2026-08-28/apf.pe --output /tmp/astra-base.patch.toml
python3 -m mod_editor.core.apf2k8_playcall_patch --image /tmp/astra-audit-tu-v2.pe --output /tmp/astra-tu.patch.toml
python3 -m mod_editor.core.apf2k8_audibles --index '/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A' --outer 130
```

These command outputs are metadata/recipes; the audible module's binary
rebuild remains in memory or the existing studio Build path. The patch can
be disabled by removing its exported TOML or setting `is_enabled = false`.
No push was performed.

## Exact authored cave bytes

The BASE image receives hook word `484A44E0` at `84869B20` and the following big-endian words. Addresses are byte addresses; each group is four bytes.

```text
84D0E000: F821FE01 F8010008 F8610010 F8810018
84D0E010: F8A10020 F8C10028 F8E10030 F9010038
84D0E020: F9210040 F9410048 F9610050 F9810058
84D0E030: F9C10060 F9E10068 FA010070 FA210078
84D0E040: FA410080 FA610088 FA810090 FAA10098
84D0E050: FAC100A0 FAE100A8 7C000026 900100C0
84D0E060: 2B180000 409A0200 2B1B0002 419801F8
84D0E070: 2B1B0004 419901F0 2B1C0001 419801E8
84D0E080: 2B1C0028 419901E0 2B1D0000 419A01D8
84D0E090: 81FD7E0C 2B0F0000 419A01CC 806F003C
84D0E0A0: 2B03001C 409A01C0 806F0034 2B0300A3
84D0E0B0: 409A01B4 806F0038 2B03024A 409A01A8
84D0E0C0: 39C10250 3E0F0001 3A1080C4 823D7E04
84D0E0D0: 3A400000 3A600000 5643103A 7E8E182E
84D0E0E0: 7F148040 41980180 7C70A050 38800064
84D0E0F0: 7EA32396 2B15024A 4098016C 1C950064
84D0E100: 7F032040 409A0160 80740004 5463273E
84D0E110: 2B030000 409A0150 80740008 7063000A
84D0E120: 2B030002 409A0140 3ADD0070 3AE00000
84D0E130: A0760000 546305BE 2B0303FF 419A00E8
84D0E140: 807600A8 5464463E 2B0400A3 40980118
84D0E150: 2B1E0000 419A0018 1C8400B8 7C847A14
84D0E160: 38840244 7F04F040 409A0098 54647E7E
84D0E170: 2B04001C 409800F0 38A00001 7CA52030
84D0E180: 7CA68838 2B060000 419A0078 80D600AC
84D0E190: 7CA63038 2B060000 419A0068 54842036
84D0E1A0: 7C847A14 38840049 38A0000B 88C40000
84D0E1B0: 54C606FE 2B060008 419A0018 38840001
84D0E1C0: 38A5FFFF 2B050000 409AFFE4 48000034
84D0E1D0: 7EC4B378 38A00054 A0C40000 54C605BE
84D0E1E0: 2B0603FF 419A001C 7F06A840 419A0028
84D0E1F0: 38840002 38A5FFFF 2B050000 409AFFDC
84D0E200: 3AD600B0 3AF70001 2B1700B0 4198FF24
84D0E210: 48000014 5663103A 38810100 7E84192E
84D0E220: 3A730001 3A520001 7F12E040 4198FEAC
84D0E230: 2B130000 419A0030 38600000 38810100
84D0E240: 7DC57378 80C40000 90C50000 38840004
84D0E250: 38A50004 38630001 7F039840 4198FFE8
84D0E260: 7E7C9B78 800100C0 7C0FF120 E8010008
84D0E270: E8610010 E8810018 E8A10020 E8C10028
84D0E280: E8E10030 E9010038 E9210040 E9410048
84D0E290: E9610050 E9810058 E9C10060 E9E10068
84D0E2A0: EA010070 EA210078 EA410080 EA610088
84D0E2B0: EA810090 EAA10098 EAC100A0 EAE100A8
84D0E2C0: E8210000 3D608506 4BB5B85C
```

The TU image receives hook word `484A37E0` at `8486A820`. Its first 712 cave bytes are exactly the same; replace only the final word at `84D0E2C8` with `4BB5C55C` to return to `8486A824`. Both complete byte strings are SHA-pinned in the table above. These 179 instructions are authored patch code, not a retail dump.

## Instruction appendix: selected BASE evidence

All rows are A_PROVEN for the displayed instruction/operation only; causal and mode-specific grades remain as stated above. Regenerate with `python3 tools/apf_playcall_static_evidence.py --image <pinned-apf.pe>`.

### Retry, category dispatch and actual CPU path

| VA | BE word | Capstone decode | Meaning / limit |
| --- | --- | --- | --- |
| `8486CF74` | `7FC3F378` | `mr r3, r30` | Formation/null argument to category chooser |
| `8486CF78` | `3B390001` | `addi r25, r25, 1` | Increment retry ordinal (not a descriptor index) |
| `8486CF84` | `4BFFF9AD` | `bl 0x8486c930` | Call category chooser |
| `8486D084` | `2F190003` | `cmpwi cr6, r25, 3` | Last retry ordinal 3 |
| `8486D088` | `4198FEE8` | `blt cr6, 0x8486cf70` | Retry branch |
| `8486C958` | `817E0004` | `lwz r11, 4(r30)` | Formation family word |
| `8486C95C` | `7D6BD670` | `srawi r11, r11, 0x1a` | Family shift by 26 |
| `8486C9E4` | `817D0034` | `lwz r11, 0x34(r29)` | Manager mode +0x34 |
| `8486C9B4` | `3BE00011` | `li r31, 0x11` | Punt row 17 |
| `8486C9DC` | `3BE00019` | `li r31, 0x19` | Generic special row 25 |
| `8486CA1C` | `3BE00015` | `li r31, 0x15` | Kickoff row 21 |
| `8486CA44` | `3BE00016` | `li r31, 0x16` | Onside row 22 |
| `8486CA70` | `3BE00013` | `li r31, 0x13` | Field-goal row 19 |
| `8486CAB8` | `4BFFE3F9` | `bl 0x8486aeb0` | Book-bound category chooser |
| `8486CF94` | `897F0004` | `lbz r11, 4(r31)` | Returned category's row byte +4 |
| `8486D05C` | `4BFFE275` | `bl 0x8486b2d0` | Ordinary CPU weighted play picker |
| `8486D08C` | `38C0FFFF` | `li r6, -1` | Emergency fetch subtype -1 |
| `8486D09C` | `4BFFC93D` | `bl 0x848699d8` | Emergency whole-book fetch |

### Output pointer, UI fields and live-state candidates

| VA | BE word | Capstone decode | Meaning / limit |
| --- | --- | --- | --- |
| `84815608` | `3D608516` | `lis r11, -0x7aea` | Output-global high half |
| `8481560C` | `396B8350` | `addi r11, r11, -0x7cb0` | Output-global signed low half |
| `84815664` | `388B0010` | `addi r4, r11, 0x10` | r4 points at output staging +0x10 |
| `8481566C` | `4805781C` | `b 0x8486ce88` | Tail branch to picker |
| `8486CEA0` | `7C972378` | `mr r23, r4` | Preserve output pointer in r23 |
| `8486CEC4` | `814B02BC` | `lwz r10, 0x2bc(r11)` | UI tab +0x2BC |
| `8486CEDC` | `814B01F8` | `lwz r10, 0x1f8(r11)` | UI subtype +0x1F8 |
| `8486D0B8` | `93F70000` | `stw r31, 0(r23)` | Write output category |
| `8486D0C0` | `93D70004` | `stw r30, 4(r23)` | Write output formation |
| `8486D0C4` | `93B7000C` | `stw r29, 0xc(r23)` | Write output play |
| `84A3752C` | `814B0254` | `lwz r10, 0x254(r11)` | Practice candidate down +0x254 |
| `84A37858` | `812B0254` | `lwz r9, 0x254(r11)` | Practice candidate down +0x254 |
| `84A3785C` | `814B025C` | `lwz r10, 0x25c(r11)` | Practice candidate distance +0x25C |
| `8486BF1C` | `815E006C` | `lwz r10, 0x6c(r30)` | Live state pointer +0x6C |
| `8486BF20` | `816A0004` | `lwz r11, 4(r10)` | Live state field +4 |
| `8486BF24` | `2F0B0004` | `cmpwi cr6, r11, 4` | Compare that field with 4; down meaning remains inference |
| `84868D8C` | `C1AB0018` | `lfs f13, 0x18(r11)` | Live state float +0x18 |
| `84868D90` | `C00B0028` | `lfs f0, 0x28(r11)` | Live state float +0x28 |
| `84868D98` | `EC006828` | `fsubs f0, f0, f13` | Distance-like subtraction, live units not proved |
| `84868DA0` | `FC000210` | `fabs f0, f0` | Absolute value |
| `84A3CED8` | `2F0A0009` | `cmpwi cr6, r10, 9` | Mode-9 override gate |
| `84A3CEF4` | `816B0118` | `lwz r11, 0x118(r11)` | Override object pointer +0x118 |
| `84A3CF00` | `896B0006` | `lbz r11, 6(r11)` | Override object's requested row +6 |

### Reverse lookup, secondary mask and regeneration

| VA | BE word | Capstone decode | Meaning / limit |
| --- | --- | --- | --- |
| `84A8A2B8` | `A1230000` | `lhz r9, 0(r3)` | First entry of candidate record |
| `84A8A2C0` | `2B0903FF` | `cmplwi cr6, r9, 0x3ff` | First-empty sentinel |
| `84A8A2C4` | `419A0020` | `beq cr6, 0x84a8a2e4` | Return null at first empty |
| `84A8A2C8` | `892300A8` | `lbz r9, 0xa8(r3)` | Record formation index byte |
| `84A8C5C4` | `4BFFDC95` | `bl 0x84a8a258` | Reverse lookup through first matching record |
| `84A8C5C8` | `816300A8` | `lwz r11, 0xa8(r3)` | Primary trailer word A |
| `84A8C5D0` | `556B9D76` | `rlwinm r11, r11, 0x13, 0x15, 0x1b` | Primary category multiplied by 16 |
| `84A8C5D8` | `3BEB0044` | `addi r31, r11, 0x44` | MASTER category base +0x44 |
| `84A8A398` | `816300AC` | `lwz r11, 0xac(r3)` | Secondary category membership word B |
| `84A8C7C0` | `39797E04` | `addi r11, r25, 0x7e04` | Normalizer addresses category cache +0x7E04 |
| `84A8C800` | `39797D98` | `addi r11, r25, 0x7d98` | Normalizer addresses formation cache +0x7D98 |
| `84A8C83C` | `39797DB0` | `addi r11, r25, 0x7db0` | Normalizer addresses play cache +0x7DB0 |
| `84A8CB6C` | `81670118` | `lwz r11, 0x118(r7)` | Read populated primary word A |
| `84A8CBA0` | `7D6AC92E` | `stwx r11, r10, r25` | Store accumulated primary category mask |
| `84A8CBB0` | `8167011C` | `lwz r11, 0x11c(r7)` | Read word B, first unrolled bit |
| `84A8CBF0` | `7D4BC92E` | `stwx r10, r11, r25` | OR secondary membership into book mask |
| `84A8CC00` | `8167011C` | `lwz r11, 0x11c(r7)` | Read word B, second unrolled bit |
| `84A8CC4C` | `8167011C` | `lwz r11, 0x11c(r7)` | Read word B, third unrolled bit |
| `84A8CC90` | `8127011C` | `lwz r9, 0x11c(r7)` | Read word B, fourth unrolled bit |
| `84A8CCD0` | `2F0B0020` | `cmpwi cr6, r11, 0x20` | All 32 secondary category bits |
| `84A8CCD4` | `4198FED0` | `blt cr6, 0x84a8cba4` | Continue secondary-mask folding |
| `84A8CD00` | `3BF97970` | `addi r31, r25, 0x7970` | First tail array +0x7970 |
| `84A8CD0C` | `3BA00005` | `li r29, 5` | Five items in tail array |
| `84A8CD34` | `897F0000` | `lbz r11, 0(r31)` | Stored formation byte in tail item |
| `84A8CD6C` | `A15F0002` | `lhz r10, 2(r31)` | Stored play u16 in tail item |
| `84A8CE64` | `4BFFEA1D` | `bl 0x84a8b880` | Repair from static row priorities through current book |
| `84A8CF50` | `3BB97984` | `addi r29, r25, 0x7984` | Second five-item tail array +0x7984 |
| `84A9AE28` | `80630000` | `lwz r3, 0(r3)` | Static priority list's first row |
| `84A9AE4C` | `80630004` | `lwz r3, 4(r3)` | Static priority list's next row |
| `84A9AE58` | `21630018` | `subfic r11, r3, 0x18` | Priority row validity helper |
| `84A8B508` | `4BFFFF31` | `bl 0x84a8b438` | Resolve priority row through book category mask |
| `84A8B90C` | `4BFFEA25` | `bl 0x84a8a330` | Require candidate formation word-B compatibility |

### Special formation caches and their book-bound initialization

| VA | BE word | Capstone decode | Meaning / limit |
| --- | --- | --- | --- |
| `84864D9C` | `4822506D` | `bl 0x84a89e08` | First formation from current book |
| `84864E7C` | `93FC0050` | `stw r31, 0x50(r28)` | Cache special formation +0x50 |
| `84864E84` | `4822772D` | `bl 0x84a8c5b0` | Resolve its primary category from SPLB |
| `84864E88` | `907C0054` | `stw r3, 0x54(r28)` | Cache category +0x54 |
| `84864E94` | `93FC0058` | `stw r31, 0x58(r28)` | Cache offensive Hail Mary formation +0x58 |
| `84864E9C` | `48227715` | `bl 0x84a8c5b0` | Resolve offensive Hail Mary category from SPLB |
| `84864EA0` | `907C005C` | `stw r3, 0x5c(r28)` | Cache category +0x5C |
| `84864EAC` | `93FC0060` | `stw r31, 0x60(r28)` | Cache defensive Hail Mary formation +0x60 |
| `84864EB4` | `482276FD` | `bl 0x84a8c5b0` | Resolve defensive Hail Mary category from SPLB |
| `84864EB8` | `907C0064` | `stw r3, 0x64(r28)` | Cache category +0x64 |
| `84864EC4` | `48224FE5` | `bl 0x84a89ea8` | Next formation iterator |
| `8486D008` | `83CB0058` | `lwz r30, 0x58(r11)` | Read cached offensive special formation |
| `8486D01C` | `83CB0060` | `lwz r30, 0x60(r11)` | Read cached defensive special formation |
| `8486BD4C` | `388BBAFC` | `addi r4, r11, -0x4504` | Safety Kick name lookup argument |
| `8486BE1C` | `808A0058` | `lwz r4, 0x58(r10)` | Read cached formation +0x58 |
| `8486BE20` | `909F0684` | `stw r4, 0x684(r31)` | Store temporary formation +0x684 |
| `8486BE30` | `907F0680` | `stw r3, 0x680(r31)` | Store temporary play +0x680 |
| `8486D068` | `83DB0684` | `lwz r30, 0x684(r27)` | Consume temporary formation +0x684 |
| `8486BE74` | `808B0050` | `lwz r4, 0x50(r11)` | Read cached special formation +0x50 |

### Lineup role bytes and substitution inputs

| VA | BE word | Capstone decode | Meaning / limit |
| --- | --- | --- | --- |
| `848605AC` | `3BB90005` | `addi r29, r25, 5` | Category role-byte base +5 |
| `848605B4` | `7D5DF0AE` | `lbzx r10, r29, r30` | Read category role byte for slot |
| `848605C0` | `554506FE` | `clrlwi r5, r10, 0x1b` | Role low five bits |
| `848605CC` | `4BFFE19D` | `bl 0x8485e768` | Assign role to lineup slot |
| `848608F8` | `809C0000` | `lwz r4, 0(r28)` | Wrapper reads category from caller object +0 |
| `84860900` | `80BC0004` | `lwz r5, 4(r28)` | Wrapper reads formation from caller object +4 |
| `84A2734C` | `83DF004C` | `lwz r30, 0x4c(r31)` | UI preview reads cached category from object +0x4C |
| `84A8ACE8` | `39437998` | `addi r10, r3, 0x7998` | Book substitution array +0x7998 |
| `84A8ACEC` | `38E00100` | `li r7, 0x100` | 256 packed entries |
| `84A8ACF0` | `816A0000` | `lwz r11, 0(r10)` | Packed substitution word |
| `84A8ACF4` | `5566A7BE` | `rlwinm r6, r11, 0x14, 0x1e, 0x1f` | Scope bits 12..13 |
| `84A8AD00` | `5566F5BE` | `rlwinm r6, r11, 0x1e, 0x16, 0x1f` | Selector bits 2..11 |
| `84A8AD0C` | `2F08000C` | `cmpwi cr6, r8, 0xc` | At most 12 matching overrides |
| `847B2E54` | `38800001` | `li r4, 1` | Category scope 1 |
| `847B2E60` | `482D7E29` | `bl 0x84a8ac88` | Collect category-scoped substitutions |
| `847B2E80` | `38800002` | `li r4, 2` | Formation scope 2 |
| `847B2E8C` | `482D7DFD` | `bl 0x84a8ac88` | Collect formation-scoped substitutions |
| `847B2EBC` | `388BCED0` | `addi r4, r11, -0x3130` | Global override table signed low half |
| `847B2EC4` | `482E814D` | `bl 0x84a9b010` | Merge global overrides |
| `84A9B1D8` | `89630004` | `lbz r11, 4(r3)` | Category row selects preset family |
| `84A9B2F4` | `556A17BE` | `srwi r10, r11, 0x1e` | Packed operation kind |
| `84A9B314` | `556A563E` | `rlwinm r10, r11, 0xa, 0x18, 0x1f` | Packed source role/slot bits 22..29 |
| `84A9B324` | `5563963E` | `rlwinm r3, r11, 0x12, 0x18, 0x1f` | Packed target role/slot bits 14..21 |
| `84A9B32C` | `556507BC` | `rlwinm r5, r11, 0, 0x1e, 0x1e` | Reversal bit 1 |
| `847B2F3C` | `547D06FE` | `clrlwi r29, r3, 0x1b` | Resolve role low five bits |
| `847B2F50` | `547FDF7E` | `rlwinm r31, r3, 0x1b, 0x1d, 0x1f` | Resolve depth high three bits |
| `847B2FEC` | `4BFFF9FD` | `bl 0x847b29e8` | Resolve roster player |

### Fetch, classifiers and audible initialization

| VA | BE word | Capstone decode | Meaning / limit |
| --- | --- | --- | --- |
| `848699E4` | `7CDB3378` | `mr r27, r6` | r27 = subtype argument |
| `848699E8` | `83A30020` | `lwz r29, 0x20(r3)` | r29 = current book |
| `848699EC` | `7C982378` | `mr r24, r4` | r24 = family argument |
| `848699F0` | `7CBE2B78` | `mr r30, r5` | r30 = optional formation argument |
| `84869AA4` | `2F1C0028` | `cmpwi cr6, r28, 0x28` | 40-candidate capacity |
| `84869AAC` | `93F90000` | `stw r31, 0(r25)` | Append MASTER play pointer |
| `84869B20` | `3D608506` | `lis r11, -0x7afa` | Displaced hook instruction |
| `84869B28` | `482D4D31` | `bl 0x84b3e858` | Existing RNG call |
| `84869B34` | `7D2AE396` | `divwu r9, r10, r28` | Existing divide by candidate count |
| `848682E0` | `4BFFCE79` | `bl 0x84865158` | Pass subtype 2 classifier |
| `848682F8` | `4BFFCE61` | `bl 0x84865158` | Pass subtype 3 classifier |
| `84868310` | `4BFFCE49` | `bl 0x84865158` | Pass subtype 4 classifier |
| `84865180` | `815F0008` | `lwz r10, 8(r31)` | Pass classifier metadata load |
| `8486518C` | `554B07BC` | `rlwinm r11, r10, 0, 0x1e, 0x1e` | Pass flag bit 1 |
| `8486519C` | `409A0018` | `bne cr6, 0x848651b4` | Pass flag decision |
| `84865078` | `817F0008` | `lwz r11, 8(r31)` | Run classifier metadata load |
| `8486507C` | `556B0738` | `rlwinm r11, r11, 0, 0x1c, 0x1c` | Run flag bit 3 |
| `84865084` | `409A000C` | `bne cr6, 0x84865090` | Run flag decision |
| `84864BF4` | `556BB77E` | `rlwinm r11, r11, 0x16, 0x1d, 0x1f` | Extract existing audible tag |
| `84864BF8` | `7F0BE000` | `cmpw cr6, r11, r28` | Compare requested tag |
| `84864BFC` | `419A0084` | `beq cr6, 0x84864c80` | Skip filling an already present tag |

### Complete direct builder-call census in 84630000..84D10000

| VA | BE word | Decode | Category / formation provenance |
| --- | --- | --- | --- |
| `848608AC` | `4BFFF775` | `bl 0x84860020` | Row resolver: book-advertised category; null formation |
| `84860910` | `4BFFF711` | `bl 0x84860020` | Caller state object +0 category, +4 formation; upstream ownership not closed |
| `84861338` | `4BFFECE9` | `bl 0x84860020` | Field-goal row 19 through book row lookup; special formation |
| `84862530` | `4BFFDAF1` | `bl 0x84860020` | Existing formation iterator then primary category resolver |
| `84868024` | `4BFF7FFD` | `bl 0x84860020` | First current-book formation then primary category resolver |
| `84868104` | `4BFF7F1D` | `bl 0x84860020` | Selected formation then primary category resolver |
| `84868174` | `4BFF7EAD` | `bl 0x84860020` | Next formation then primary category resolver |
| `84A273A8` | `4BE38C79` | `bl 0x84860020` | UI preview: cached object +0x4C category or record resolution; virtual formation getter |
| `84A2748C` | `4BE38B95` | `bl 0x84860020` | Second build in the same UI preview path |
| `84A98FB0` | `4BDC7071` | `bl 0x84860020` | Dialog wrapper takes category argument unless formation supplies record category |
| `84A992BC` | `4BDC6D65` | `bl 0x84860020` | Second dialog wrapper; same conditional category argument |

Normalizer direct callers (8): `84A47880`, `84A48898`, `84A8D2A4`, `84A8D728`, `84A8D87C`, `84A8DBAC`, `84A8F038`, `84A8F15C`.

Formation-stride mulli sites (28): `8492AAA8`, `8492CB70`, `8492CC48`, `8492CC6C`, `8492D058`, `8492D148`, `84A13E9C`, `84A143D0`, `84A1447C`, `84A14D80`, `84A853D8`, `84A89840`, `84A89AB4`, `84A89E48`, `84A89E98`, `84A89F28`, `84A89FC8`, `84A8A26C`, `84A8B1E4`, `84A8B604`, `84A8B69C`, `84A8B8DC`, `84A8BA2C`, `84A8CDA8`, `84A8CF00`, `84A8CFD0`, `84A8D0D4`, `84A8D964`.

These scans enumerate these instruction encodings; computed or indirect references require separate tracing.

### Dispatch tables are code pointers

`8486C980` (13 BE code-address entries): `8486C9DC`, `8486C9DC`, `8486C9DC`, `8486C9DC`, `8486CAC4`, `8486CAC4`, `8486CAC4`, `8486CAC4`, `8486C9BC`, `8486CAC4`, `8486C9B4`, `8486CAC4`, `8486CA70`.

`8486CA0C` (4 BE code-address entries): `8486CA1C`, `8486CA24`, `8486CA60`, `8486CA80`.


## Final artifact checks

```text
PROPOSED_REGISTRY_MERGE_PASS rows=2; protected registry unchanged
AUDIBLE_CLI_RECIPE_REPARSE_PASS moves=20 balanced=23/23
ARTIFACT_REVIEW_PASS cave=716 bytes; proposed registry=2 rows; census=154 records; original WIRING prefix preserved; protected files unchanged
python3 -m py_compile [the six new/changed product and research modules] — exit 0
git diff --check — exit 0
```

Both independent patch CLI exports reported `toml_reparsed: true`, 179
instructions, 34 verified branches and `status: unwitnessed`. Their output
SHA-256 values are BASE
`930a117a2a648f9896a8e431413341804002326fccc64a12f1875f935d4f86ac` and TU
`e7f51ea31344e583ed84fd5d3f86449d402be56a6903107fa9efb64e3afe1c62`.
The standalone audible suite also passed its final rerun (18 tests, 2.797s),
and the patch suite passed its module-invocation check (11 tests, 1.615s).
The compact receipt is 40,635 bytes of selectors/counts/hashes. Its explicit
path is included despite the repository's broad `research/` ignore rule;
no other ignored or supplied context file is part of this change.

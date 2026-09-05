# Depth locks: final SPECIAL layout follow-up

2026-09-05. The final SPECIAL layout is accepted, both XBE gates pass, and
the standalone depth-lock suite actually executes: **22 tests, no skips**.
All five validation suites total **98 passing tests**. No game, GUI, audio,
or full-system emulator was launched; runtime evidence is bounded Unicorn
instruction execution with read-only executable pages.

## Recognition and unchanged executable behavior

`nfl2k5_depth_locks._context` now asks the existing rows owner to validate
the complete coordinated layout. Retail and pools-only images use the retail
table/bench arm. SPECIAL uses the 46-record table at **0xEE3000**, the extended
read-only `.XTLID` storage, and its exact bench arm. Both use **stride 11**.
This validates the table, storage headers/padding, reader instructions,
counts, chain test, and whole bench block together. Simply accepting either
bench byte string would have accepted mixed installations.

Removed the lock module's `sites(stride=11/13)` choice and the inference
that stride 11 means the retail bench/swap. `sites(layout="retail")` and
`sites("special")` now choose the correct shared swap test:
`test eax,eax` for retail, `test al,1` for SPECIAL. Updated the cave gate's
old `sites(13)` call and both obsolete assembly comments. The side-field
shift of **13 bits** is unrelated and remains unchanged. The earlier
`ASTRA_DEPTH_LOCKS_REPORT.md` is historical; this report supersedes its
stride-13/expanded-layout descriptions.

`read_any()` reports `layout: retail|special` and `stride: 11`; `status()`
reports the lock installation state separately. A fresh apply receipt also
reports the layout. Mixed/foreign layouts, partial lock installs, and
obsolete stride-13 inputs refuse before allocating the output buffer.

Measured against the pinned retail XBE:

| Input | Bench | Locks before / after | Changed bytes | Growth from locks |
|---|---|---|---:|---:|
| Retail | Retail | retail / applied | 926 | 0 |
| Modern positions + pools | Retail | retail / applied | 926 | 0 |
| Pools + final SPECIAL | SPECIAL | retail / applied | 926 | 0 |

All embedded `RETAIL_*` and `PATCHED_*` machine-code constants, lock masks,
and allocation constants match the original commit. The six rewrites and
their padding stay in their existing allocations; only section 0's digest
is repinned. The `.S` changes are comments only. GNU as/ld/objcopy reproduces
all six embedded instruction blocks. No cave, absolute runtime variable,
or executable allocation was added. Persistent storage is still player
record **+0x52 bits 0–4**, preserving bits 5–7 and all of +0x53.

The pure patch API still performs no file I/O. No dispatcher, build preset,
binary descriptor handling, or Windows `O_BINARY` code was edited. Private
retail inputs were opened read-only; no disc image was rewritten.

## Bench return-address proof

Capstone disassembles the actual `rows.RETAIL_BENCH` and `rows.bench_bytes()`
and checks their direct calls to **0x243790** against the comparisons embedded
in the compactor:

| Arm | Call VA | Encoded call | Return VA | Chain selection |
|---|---:|---|---:|---|
| Retail side | 0x244452 | `e8 39 f3 ff ff` | **0x244457** | Side bit 1 |
| Retail rank | 0x244471 | `e8 1a f3 ff ff` | **0x244476** | Rank bit 0 |
| Final SPECIAL | 0x24445F | `e8 2c f3 ff ff` | **0x244464** | Saved EAX & 1 |

The SPECIAL return pin therefore **did not move**. That arm loads the chain
from `0xEE3044 + 0x48 * (unit * 11 + slot)`, pushes it at **0x24442B**, calls
confirmation at **0x244435**, and pops it into EAX at **0x24443C**. Thus the
compactor still receives the encoded chain, including **4** for GADGET/PWR.
No pin or machine-code update is needed.

The execution tests enter the real bench arm, rather than only synthesizing
its caller stack. They observe each actual compactor return address and
SPECIAL's EAX value. Across both lock orders and all three practice states,
they execute LT/RT and all nine SPECIAL role rows, with selection at actual
row 7, cancellation above row 7, and confirmed promotion above row 7:
**234 arm executions**, including **78 confirmed promotions followed by the
whole weekly sorter**. The new preference survives, the other chain's lock
survives, and unrelated player bytes remain intact. Normal selection and
cancellation neither call the compactor nor mutate the team/players.

Additional bounded checks execute swaps for chains **0–4**, both patch
orders, and practice off/squad/squad+reserves. Twelve staging executions
cover retail/SPECIAL, both lock orders, and practice modes 0, 2, and 3:
locked reserve records reach the disposable practice copies, their lock/star
bytes survive, training keeps the active-only count, and source rosters are
byte-identical. Existing full weekly sorts, returner identities, native
removal, maximum-capacity teams, and confirmation tests still pass.

## Standalone tests and commands

The old file ended after the last test method: it lacked an
`if __name__ == "__main__": unittest.main()` entry point. Directly running
that file only defined classes and exited successfully without running
tests. Added the entry point. Capstone **5.0.7** and Unicorn **2.1.4** were
available; no dependency or retail-data skips occurred.

Retail SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Input: `/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe`.

| Command | Result |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_depth_locks.py -v` | 22 passed, 83.988 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py -v` | 8 passed, 9.457 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py -v` | 9 passed, 18.159 s |
| `python3 -m unittest discover -s tests -p 'nfl2k5_depth_chart_rows_test.py' -v` | 23 passed, 38.418 s |
| `python3 -m unittest discover -s tests/mod_editor -p 'test_nfl2k5_practice*.py' -v` | 36 passed, 30.051 s |
| `python3 packaging/repin.py` | 0 pin updates needed |
| `git diff --check` | Clean |

The gates retain their existing apply composition, including reserves after
locks. The only follow-up change to either gate is replacing its obsolete
`sites(13)` argument with `sites("special")`. Separate lock composition
tests cover locks first and last relative to rows and practice patches,
as well as both returner-fix orders. Resulting XBEs are byte-identical across
orders, idempotent, and have valid section digests; lock writes touch only
their six owned spans and the section digest.

## Checkout discrepancy and delivery limitation

The supplied checkout actually started at **c92f873**, one commit before
the brief's stated beta-61 prerequisite **e6784e70f185567899b4256a4b8ef492dd96c7dd**.
It had no practice-reserves module or dispatcher wiring for depth locks.
The local stack reference initially pointed to e6784e70. A fast-forward
failed because shared Git metadata is mounted read-only:

```text
fatal: update_ref failed for ref 'ORIG_HEAD': cannot lock ref 'ORIG_HEAD':
Unable to create '/home/noah/2k-football-mod-tools/.git/worktrees/astra-depth-locks/ORIG_HEAD.lock':
Read-only file system
```

Decision: materialize that existing prerequisite commit's seven paths in
this worktree, without altering the protected Git metadata. They match its
blobs exactly, except the follow-up cave-gate argument. They are prerequisite
changes, not additions in the follow-up commit:

- `mod_editor/core/nfl2k5_franchise_practice.py`
- `mod_editor/core/nfl2k5_practice_reserves.py`
- `tests/mod_editor/test_nfl2k5_franchise_practice.py`
- `tests/mod_editor/test_nfl2k5_practice_reserves.py`
- `tests/mod_editor/test_xbe_patch_cave_references.py`
- `tests/mod_editor/test_xbe_patch_memory_writes.py`
- `tools/ps_section/evidence.py`

The dispatcher wiring described in the brief exists in the sibling beta-61
worktree. As an extra read-only smoke check, loaded that dispatcher source
into an isolated Python module using this worktree's patched dependencies.
Its SHA-256 was
`0ecd58e753bd18570715ce0031bb1c9dde8adcbca5515146a1d25eb8a340ee21`.
Starting with the pools prerequisite, its actual `_apply_all` successfully
composed SPECIAL → practice squad → locks → practice reserves with
`depth_locks=True`, and replay was byte-identical with already-applied
receipts. Neither worktree's dispatcher was edited.

Since the original branch/index cannot be written in this session, delivery
uses a separate writable Git database at
`/tmp/astra-depth-locks-followup.git`, branch **astra/depth-locks**, parent
**e6784e70**. Source edits and validation stayed in this worktree. The commit
stages and commits these five explicit paths only:

- `ASTRA_DEPTH_LOCKS_FOLLOWUP.md`
- `docs/mod_editor/nfl2k5_depth_locks.S`
- `mod_editor/core/nfl2k5_depth_locks.py`
- `tests/mod_editor/test_nfl2k5_depth_locks.py`
- `tests/mod_editor/test_xbe_patch_cave_references.py`

`ASTRA_DEPTH_LOCKS_FOLLOWUP.patch` is the portable format-patch export of
that commit. The original shared branch remains at c92f873; updating it
requires a session with writable Git metadata. No push was performed, and
the original untracked `ASTRA_BRIEF.md` remains outside the commit.

The brief's witnessed SPECIAL boot is not a witness of depth-lock gameplay.
Full controller, save/reload, and on-field lifecycle acceptance remains
outside this bounded instruction proof, as in the original delivery.

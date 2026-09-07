# MyCareer mode 3

EXPERIMENTAL / UNWITNESSED. Native CPU fixtures are evidence of the named
boundaries, not evidence that Noah has played this mode.

## M2a checkpoint: shared game completion

PROVED: generic MyCareer and Franchise Auto Save compose in either installation
order, retain exact receipts, and replay unchanged. Each owner first validates
the other owner's complete installation before accepting its exact shared
function edits. No arbitrary context bytes or partial installations are accepted.

The native played-result dispatcher commits through `1356C0/134140`, MyCareer's
`C5D9E` hook settles its award, and Auto Save's existing `C5DA9` hook queues the
save. Native postgame and week handling return to the Apartment. Two quiet
Apartment frames then enter Auto Save's appended `career_complete` callback
with ECX = manager and EDX = the owned Apartment descriptor. It reuses the
cached-slot transaction and existing retry suppression. No save occurs in the
per-frame player binder or while the live scene exists. The exact callable and
protected product changes are recorded in WIRING.md.

The original 1,027-byte Auto Save runtime prefix and its relocation records are
unchanged. Its code is now 1,170 / 1,536 bytes. MyCareer's machine code is 7,042
bytes; code plus immutable content is 7,918 bytes, leaving 257 bytes before its
format seal in the existing 8,192-byte RX allocation. RW remains 4,096 bytes.

PROVED by the bounded shared callback fixture: successful native save once;
missing slot; allocation, deletion, creation, write and commit failure;
deferral for a live scene, busy storage or a child screen; return after two
quiet frames; no repeated transaction or notice on repeated frames. The
fixture substitutes the played-stat providers and uses an inactive career
footer. It proves this completion ABI, not a completed career match or real
played statistics. Those are M2b requirements.

Validation, all standalone with plain `python3`:

| Command suffix | Result |
| --- | --- |
| `tests/mod_editor/test_nfl2k5_franchise_autosave.py` | 7 passed, 9.034 s |
| `tests/mod_editor/test_nfl2k5_franchise_autosave_unicorn.py` | 15 passed, 8.363 s |
| `tests/mod_editor/test_nfl2k5_my_career_generic_build.py` | 5 passed, 9.780 s |
| `tests/mod_editor/test_nfl2k5_my_career_completion.py` | 6 passed, 26.934 s |
| `tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 101 passed, 629.957 s |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 83 passed, 805.111 s |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 99 passed, 929.594 s |
| `tools/nfl2k5_franchise_autosave_assemble.py --check` | Passed |
| `tools/mycareer_mode/build_runtime.py --check` | Passed |

`tools/nfl2k5_cave_oracle.py manifest` against the pinned retail XBE and XISO
wrote `.scratch/m2a-manifest.json`: 10,629 reservations from 123 observed XBE
writer calls. The two disposable oracle builds used its TemporaryDirectory
under `/tmp` and were deleted. Root free space after the run was 108,439,990,272
bytes. The protected release manifest was not changed. `git diff --check`
passed. The capability fragment test now replaces existing fragment IDs before
validating the merged registry, retaining its schema and file closure checks.

The blocking M2a checks above passed before M2b implementation began;
`.scratch/M2A_DONE` records that checkpoint.

## Integration observation

The brief describes the M2 product dispatcher as already wired. This checkout
still dispatches the setup-based legacy owner and requires a setup in the
protected build path. WIRING.md specifies the correction. This session does
not edit those protected files or claim that the current product UI selects
the generic mode.

## Remaining milestone work at this checkpoint

M2b played statistics and off-field progression, explicit next-fixture routing,
and M3 remain in progress. No M3 completion or played witness is claimed.

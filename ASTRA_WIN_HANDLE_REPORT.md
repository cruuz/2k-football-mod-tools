The Windows replacement failure came from `OuterImage._fd` in
`tools/nfl2k5_playbook_position_recode.py`, opened during **export recipe
recognition**, before `apply_in_place` began. The fix closes that descriptor
immediately when construction fails. Work is on `astra/win-handle`, based on
`89938fa`; no push is part of this work.

`OuterImage._open_image()` opens the disc at line 290 (formerly 281), parses
XDVDFS, then requires `vc_53450030/0` at line 294. The SPECIAL fixture has only
`default.xbe` and `next.bin`, so that requirement raises `RecodeError`.
Construction has not completed: the `with OuterImage(...)` callers never reach
`__enter__`, and Python therefore never calls `__exit__`. Previously neither
the constructor nor a destructor closed the raw integer descriptor on this
path. Garbage collection could not release it.

The callers are `modpack.recognise_recipe()`'s roster-record, team-history,
and prospect-name probes. Roster and team-history recognition each fail on
the base image and are caught by the optional recognition blocks. Prospect
recognition's `image_status()` catches its missing-resource error and returns
`foreign`, so both base and patched probes run. That accounts for **three
leaked base-image descriptors and one patched-image descriptor**. The existing
lock tests used `recipe=False`, which missed this path.

Before changing production code, I ran the original
`GrowingSpecialPackTests.test_special_round_trip_and_raw_partition` inside
the existing `windows_file_locks()` context, starting before export. It failed
at `modpack.py:144`, `os.replace(part, target)`, reached through
`_apply_modular` at line 1856, with:

```text
PermissionError: simulated WinError 5: file is open: .../base.iso
Still-open image descriptors: ['base.iso', 'base.iso', 'base.iso', 'patched.iso']
```

This reproduced the reported commit failure on Linux despite the existing
20-attempt retry. The subsequently strengthened test also failed before the
fix, directly after export, identifying all four leaked descriptors.

The exact new close is **`os.close(self._fd)` at
`tools/nfl2k5_playbook_position_recode.py:264`**, followed by `self._fd = None`
at line 265. The constructor now catches `BaseException` around both opening
and table parsing, closes any acquired descriptor, and re-raises. This also
handles malformed tables and interruption during construction. Construction
only reads, including when `writable=True`, so this cleanup closes directly
without the normal writable-session `fsync`. Successful instances retain
their existing context-manager lifetime. The descriptor is closed before
recipe recognition catches the error, before export returns, and therefore
before any subsequent in-place replacement.

The other candidates in the brief were audited:

| Candidate | Ownership and close before commit |
| --- | --- |
| Loaded modpack / ZIP members | `Pack.close()` closes every cached member stream and clears the cache (`modpack.py:656`). Their `ZipFile` wrappers already use `with`; closing the last member releases the retained archive file. `_member()` / `read_asset()` and `load()` use scoped ZIP readers. The export's final `load(out)` validates the manifest without caching a member stream. |
| `modpack_ops.check()` / `execute()` | No host-path `open`, `os.open`, or `Path.open` calls. Views and payload callbacks retain descriptor integers / pack references, without duplicating image handles. |
| Apply source and destination | The format-2 destination closes at `modpack.py:1848` on success, or line 1842 before failed-output cleanup. The source closes in `finally` at line 1850, then `pack.close()` runs at line 1853. |
| Final source verification | Its reopened source descriptor closes in `finally` at `modpack.py:1782`. Only path metadata is checked afterward; no image or pack is reopened before `_atomic_replace`. |
| SPECIAL image writer | `nfl2k5_depth_chart_storage.write_image_xbe()` uses the supplied descriptor throughout. XDVDFS parsing and positional I/O also use that descriptor, with no additional image handle. |

No transaction rewrite was needed: format-2 in-place apply already copies
into `.part`, grows and verifies that copy, closes its handles, rehashes the
current source, and commits by replacement. The source-change guard, failed
operation cleanup, preservation of verified `.part` after commit refusal,
and `_atomic_replace` retry are unchanged. `O_BINARY` remains present in
both `OuterImage._open_image()` and `modpack._open()` (`modpack.py:167`).

The existing SPECIAL test now tracks handles from export through copy/raw
partition checks and in-place apply, asserts no handles remain immediately
after export and after apply, and retains every previous byte, size,
directory, neighbour-file, and recipe assertion. A separate malformed-table
regression retains the constructor's exception traceback and checks that
`os.fstat(fd)` fails with `EBADF` in both read-only and writable modes, with
image bytes unchanged. Both modes failed before the fix and pass afterward.

Validation completed:

| Command / check | Result |
| --- | --- |
| `PYTHONPATH="$PWD" python3 tests/mod_editor/test_modpack.py` | 36 tests, all pass |
| `PYTHONPATH="$PWD" python3 tests/nfl2k5_playbook_position_recode_test.py` | 19 tests, all pass |
| `PYTHONPATH="$PWD" python3 tests/mod_editor/test_nfl2k5_roster_records.py` | 108 tests, OK with one existing skip |
| `PYTHONPATH="$PWD" python3 tests/mod_editor/test_nfl2k5_team_history.py` | 19 tests, all pass |
| `PYTHONPATH="$PWD" python3 tests/mod_editor/test_nfl2k5_prospect_names.py` | 21 tests, all pass |
| All three `GrowingSpecialPackTests` with `os.pread` and `os.pwrite` patched to `None` | Pass using the Windows seek/read/write fallbacks, including lock tracking in the round-trip test |
| `python3 packaging/repin.py` | Exit 0; would apply 0 pin updates |
| `python3 packaging/repin.py --apply` | Exit 0; applied 0 pin updates |
| `git diff --check` | Clean |

These results are Linux execution with Windows lock emulation and positional
I/O fallback coverage, not a native Windows CI result. A local Wine attempt
terminated with exit 159 before Python started, so it provides no additional
Windows validation. No test was skipped or weakened by this change.

The explicit commit scope is this report,
`tools/nfl2k5_playbook_position_recode.py`,
`tests/nfl2k5_playbook_position_recode_test.py`, and
`tests/mod_editor/test_modpack.py`. The supplied untracked `ASTRA_BRIEF.md`
is left as supplied.

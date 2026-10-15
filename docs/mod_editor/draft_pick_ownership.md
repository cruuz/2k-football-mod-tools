# New-franchise draft-pick ownership

A roster-edits document can carry `draft_pick_ownership`, with schema
`2k5_mod_studio_draft_picks/v1`, `base_season`, ISO `as_of`, and exactly 448
`picks`. Each row names `year`, `round`, `original_team`, `owner`, `status`,
HTTPS `sources`, and an explicit `resolution`. The two years must be
`base_season + 1` and `base_season + 2`. Original-team/round/year identities
must be unique. Team codes use the modern league's native 0..31 club order.

The final Studio build stage applies the directive after the executable's
starting season and other features have been installed. A different calendar,
foreign initialization context, altered owner code, or different already
installed table refuses. Reapplying the identical table changes zero bytes.
No dated ownership data is bundled in the editor.

The native reset in `FUN_0013ee10` writes each original club index into seven
rounds at `0xE3C0B4` and `0xE3C194`. Each bank is 224 bytes. Its only recorded
direct caller is new-franchise setup `FUN_00148cc0`. A five-byte CALL at
`0x13EF89`, immediately after that reset, installs the supplied owner table.
The helper preserves registers and flags, checks franchise mode 2, copies
112 dwords, then executes the displaced MOV before returning. It occupies a
544-byte late allocation, including the 448-byte immutable table. Existing
allocations do not move. Context hashes guard the reset, draft consumer and
annual rollover; the ordinary XBE section/allocator seals also validate.

Calendar mapping follows the season being played, not the UI's relative
"this year" pick label: the first draft after the 2026 regular season is in
spring 2027. Bank zero is that upcoming draft; bank one is 2028. Native
`FUN_003254d0` consumes bank zero. After the draft, `FUN_0031e430` copies bank
one to bank zero and restores original owners in bank one. Thus 2028 survives
the first rollover, and the newly available 2029 bank starts with native
ownership. The trade screen's `0x3482E0` and `0x348360` routines enumerate both
banks, encoding the second bank with an additional 500. No draft, trade, save,
load or rollover routine is patched.

Unpublished conditions and better/worse-pick obligations cannot be represented
by owner bytes. Data authors must mark `conditional_projection` or
`unconfirmed` and explain the fixed starting choice. These conditions are not
reevaluated against simulated results. Compensatory picks and a third future
year do not fit this representation. Existing franchise saves remain native
and do not receive the initialization data. A future save migration could
change the serialized banks, but must handle the current season and any trades
already made in that save; this feature does not provide that migration.

Validation: `tests/mod_editor/test_nfl2k5_draft_picks.py` tests complete table
validation and the generated x86 helper. With `B77_RO1_XBE` and
`B77_RO1_PICKS`, it also executes the real reset path, all 32 clubs' native
trade-screen enumerators, and two real rollover calls under Unicorn. It checks
register/flag preservation, foreign-input refusal, the complete XBE byte
scope, unchanged existing allocations, idempotence and equality with Studio's
final build stage. Unicorn is an optional test dependency, not a runtime
dependency. Native execution is not a claim of live emulator verification.

`tools/b77/ro1_repair.py --picks-plan TABLE.json` uses the same writer on the
pinned candidate disc. `--virtual` hashes the entire projected disc and records
the byte scope without copying or writing it. The combined roster/pick receipt
also records both plan hashes, XBE hashes and replay checks.

MyCareer guards the whole franchise initializer. Its hash view normalizes the
pick hook only when the complete pick owner validates. A corrupt hook, code
block or allocator seal remains foreign. This is a validator compatibility
change; it adds no further executable edits.

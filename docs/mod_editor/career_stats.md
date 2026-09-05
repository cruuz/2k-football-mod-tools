# Career-stat CSV import (standalone backend)

`mod_editor.core.nfl2k5_career_stats` reads and writes verified direct counters
in the version-17 disc ROST. It does not download statistics, infer missing
values, patch the XBE, or change the source file. The build integration must run
after reclassification and `nfl2k5_team_history`, using their resulting body.

## CLI

Run from the repository root. All output paths must be new files in existing
directories; source files and existing outputs are never overwritten.

```sh
python3 tools/nfl2k5_career_stats.py inspect roster-body.bin
python3 tools/nfl2k5_career_stats.py export roster-body.bin --output career.csv
python3 tools/nfl2k5_career_stats.py import roster-body.bin career.csv --output edited-body.bin --receipt career-receipt.json
```

Input is a bare `0x90F60`-byte disc ROST body or its `0x90F80`-byte wrapped
resource. Wrapped input retains its original 32-byte wrapper on output.
`--image` reads entry 5 from a supported disc image/extraction read-only and
outputs a bare body; it never repacks an image. Runtime save containers are
deliberately refused: their different framing and signing belong to the
separate save codec/container lane.

## Source and identity contract

CSV columns, in export order:

```text
player_pool,player_index,first_name,last_name,birth_date,record_sha256,season,phase,stat,value,source,source_sha256,source_player_id,occurrence,expected_word
```

Required columns are `first_name`, `last_name`, `birth_date`, `season`, `stat`,
`value`, `source`, and `source_sha256`. Other columns may be omitted when their
constraints do not apply. Unknown/duplicate columns are errors. Dates use
`YYYY-MM-DD`; SHA-256 pins use 64 lowercase hexadecimal characters.

- Supply a unique full name plus birth date within `primary` or `secondary`.
  An optional zero-based `player_index` must also match that identity.
- Without a birth date, require the exact pool/index, name, and
  `record_sha256`. Name-only matching is never accepted. Suffixes and
  punctuation are not discarded.
- A record pin hashes the 84-byte player record with only the history-pointer
  dword at `+0x2C` zeroed. Repacking alone does not invalidate it; other player
  edits may require a fresh export.
- `source` identifies the external source and `source_sha256` pins the supplied
  source artifact. `source_player_id` preserves an optional provider ID. The
  importer records these assertions; it does not authenticate an external
  source or silently map provider IDs to game records.
- Empty `value` means missing: skip without changing the destination. Numeric
  zero is an explicit write. Invalid/nonfinite/fractional-out-of-unit values
  are refused. A receipt reports missing rows separately.
- `phase` is `regular` (default) or `postseason`; they are separate counters.
  A non-games counter requires an existing games entry in the same season and
  phase, or a games row in the same import batch.

Retail contains duplicate live counters for some identical player/season/stat
keys. Export includes zero-based `occurrence` and an eight-hex-digit
`expected_word` pin so each can be edited independently. An ambiguous import
without these is refused. A stale pin is refused unless that exact occurrence
already has the requested value and unchanged flags, allowing idempotent
reapplication. Re-export before undoing or making a different subsequent edit.

## Seasons and supported values

The default roster epoch is 2004, whose completed history ends in 2003.
For a player with completed-history count `count` at player `+0x24`,
`slot = count - (base_year - season)`. Imports require `0 <= slot < count <= 31`.
`--base-year 2005` permits a completed 2004 row only when that is genuinely the
input roster's epoch. It does not advance the roster or invent more slots.
No season after 2004 is accepted by this version.

`FIELDS` in the backend is the canonical machine-readable field table. Supported
families are games, rushing, passing, receiving, tackles/sacks/interceptions/
forced fumbles, interception returns, extra points, punting, and field-goal
distance buckets. Yard fields allow signed values. Other direct counters are
nonnegative, with raw values bounded to the retail signed-16-bit getter.

`defensive_sacks` uses display units: `7.5` writes raw 15. Quarter sacks are
invalid. Field-goal made/attempted buckets are `1_29`, `30_39`, `40_49`, and
`50_plus`, for example `field_goals_made_40_49`. Aggregate field goals,
percentages, passer rating and averages are derived, not direct writable
fields. Import their underlying counters instead. Do not split an aggregate
into invented distance buckets.

Evidence locations in the pinned retail XBE are the selector/field table at
`0xA8A51C + 28*selector`, historical getter `0x14EF20`, sack expression
`0xA8B918` and its 0.5 factor at `0x4E4184`. The retail regression checks these
bytes against the executable SHA-256 before trusting the field mapping.

## Losslessness and shared capacity

Raw decode/encode preserves every byte. CSV exports only supported live,
non-folded counters in representable completed seasons; unknown, deleted,
folded and out-of-range words remain in the original body and are not erased
by a CSV import. Import always needs that original body, not just the CSV.

All rows and space are validated before returning new bytes. Existing counters
keep their position and flags; additions go at their player's stream head.
Only stream words, history pointers and the root's used-count dword may change.
Every requested value and resulting stream is decoded back and checked.
Shared, overlapping, gapped or unowned stream layouts are not repacked.

The retail pool has 50,000 dwords, 36,866 used and 13,134 free. The existing
retail team-history pass uses 42,612, leaving 7,388 before additional counters.
The receipt reports actual before/after usage, not a fixed assumed budget.
Use `--reserved-tail-words N` for other features occupying the pool tail;
new allocation also refuses any nonzero previously unused byte. This is not a
global allocator: callers must declare other consumers, including zero-filled
reserved space. Overflow returns an error without modifying the source.

The CLI validates the binary and receipt destinations before writing. They
are separate new files, not an atomic two-file filesystem transaction: a late
I/O failure can leave the valid binary without its receipt. The backend itself
is copy-only and transactional; callers control final installation.

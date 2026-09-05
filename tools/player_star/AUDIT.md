# Star runtime span audit

Input: pinned USA retail XBE SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Full machine-readable result:
[`nfl2k5_star_fix_cave_audit.json`](../../reports/gameplay_tuning/nfl2k5_star_fix_cave_audit.json).

These are whole unreferenced retail routines or portions bounded by their
original ends, **not blank padding caves**. The preceding routine terminates
before each start; no external explicit reference enters any selected byte,
including the entry. Internal branches belonging entirely to the displaced
routine are removed with it. Retail-byte SHA-256 pins cover every byte of
each complete replacement span in `nfl2k5_player_star.CAVE_PINS`.

| Span, half open | Previous termination | Following code unchanged |
| --- | --- | --- |
| `0x372D40–0x372DB6` | tail jump at `0x372D31`, followed by NOPs | starts after selected routine's tail jump |
| `0x3DDD50–0x3DDDA3` | return at `0x3DDD4A`, then INT3s | trailing INT3s and next routine |
| `0x38B0D0–0x38B123` | return at `0x38B0CD`, then INT3s | trailing INT3s and next routine |
| `0x2C9110–0x2C917A` | `ret 0x10` at `0x2C9108`, then NOPs | following alignment and routine at `0x2C9180` |
| `0x31E650–0x31E6A4` | return at `0x31E645`, then NOPs | trailing alignment and next routine |

`audit.py` checks the existing oracle legacy references and every unaligned
dword in all file-backed sections and the XBE header. It additionally
decodes 1,627,635 `.text` instructions/data items and checks direct branches,
calls and short branches. It includes exact cave entries, unlike an
interior-only cave-reference test. No external explicit reference was found.
Neighboring instruction boundaries were manually inspected on retail.

The current manifest SHA-256 is
`146fc65bcffbeaffaeadb2b94fdfc02128126bcf8aec53573215592ab3e15545`.
It has no ownership overlap with any selected span. The audit loads ownership
without `source_root`, explicitly records the drift of the two changed star
modules, and never presents those fingerprints as current. The draw regression
also builds the actual existing patch stack in memory and compares both
application orders, including kickoff/practice/roster-pool patches.

## Conservative oracle result

The full bounded oracle analyzed 250,000 instructions and 2,782,776 references.
The instruction budget was exhausted; the 6,000,000-reference budget was not.
There were 176,300 unresolved observations, including computed/indirect
accesses and decode failures. Every selected span is `unknown`, none
`reserved` or `reachable`. **This is not an oracle certificate of freedom.**
The negative explicit-reference scan and local boundary inspection are the
evidence used for this choice; unresolved indirect/computed paths remain a
static-analysis limitation.

The oracle's sole external bytewise candidate is source `0x2C9195` targeting
`0x2C9173`. At an established instruction boundary, retail `0x2C9194` is
`cmp eax, 0x0052DC74` (five bytes). The `0x74` byte at `0x2C9195` is its
immediate, not a short conditional branch. Actual neighboring branches at
`0x2C9192` and `0x2C9199` target `0x2C919B` and `0x2C919F`, outside the
replacement. All other candidate witnesses originate inside the displaced
span or are unresolved global observations. The raw result is retained.

## Reproduction

```sh
python3 tools/player_star/audit.py --oracle --output /tmp/star-cave-audit.json
python3 tools/player_star/build_runtime.py --check
python3 tests/mod_editor/test_nfl2k5_player_star_draw.py
python3 tests/mod_editor/test_xbe_patch_memory_writes.py
python3 tests/mod_editor/test_xbe_patch_cave_references.py
```

The new emulation fixture protects the entire `.text` section against writes
while executing the new path. Its scratch material/coordinates and saved
registers are on the stack; only immutable geometry is stored in `.text`.
The existing mandatory memory and cave-reference gates both pass. Claude
must regenerate the manifest after integration as described in
[`WIRING_STAR.md`](../../WIRING_STAR.md); no reservation metadata was edited
to hide an overlap or stale-source result.

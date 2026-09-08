# r62 defensive try box score, 2026-09-06

**EXPERIMENTAL / UNWITNESSED.** Implemented the native defensive-conversion
box-score row, player-card season column, saved player season/career category
used by completed franchise games, player points and event-banner strings.
Also repaired offensive failed-attempt accounting for defensive scores. The
existing continuation, scoring, kickoff ownership, try safety and CPU return
override remain composed under the existing default-off `defensive_try` flag.
This supersedes the missing-stat findings in `ASTRA_DEFENSIVE_TRY_REPORT.md`.
No console/gameplay witness is claimed.

Base: `f371972`, branch `astra/r62-defensive-try-boxscore`. Decisions followed
`ASTRA_BRIEF.md`, the shipped RC85 changelog, the existing Astra reports,
`DEFENSIVE_2PT_RESEARCH_2026-09-05.md` section 3 and the team-column research.
The other worktree/corpus was read-only. No protected implementation file,
release manifest, disc, PLAY or ROST resource was modified.

## Implementation and native evidence

### The category and its lifetime

The new public stat ID is `0x4000`. Only that ID is intercepted in the native
player (`0xCB240`) and team (`0xCB2D0`) readers. Existing IDs retain their
displaced instructions, registers, flags and stack. The current-game team
value sums its native inline roster's player values. These are counts, not
points; the player-points calculation at `0x24FFCB` separately adds twice the
defensive count, preserving the existing offensive calculations.

Current counts use native encoded roster IDs from `0xBBAA0`, validated by
decoding at `0xBBA60` and comparing the complete player pointer. Credit follows
the committed scoring snapshot's actor at `+0x35C`, then its live roster record
at `actor+0x3C`. Only the defensive return subtype 5 is credited; safeties,
offensive conversions, ordinary outcomes and missing/invalid actors are not.

The existing 1,040 RW bytes now contain:

| Offset | Meaning |
| --- | --- |
| 0..511 | 256 unsigned 16-bit player counts; low 15 bits count, high bit successful season merge |
| 512..1023 | 128 replacement records: 23-bit absolute drive identity, 8-bit actor ID, and one bit recording an original two-point attempt |
| 1024, 1028 | Team diagnostic projections |
| 1032 | Projection version/commit marker, 0 or 2 |
| 1036..1039 | Reserved zero bytes |

Replaying the same drive removes its prior player credit before applying the
new result. Reassigning the scorer moves the credit; replacing a score with a
failure removes it. Reusing a ring slot for a different absolute drive retains
older totals, fixing the old 128-drive loss. A 130-drive native fixture proves
65 credits per team, including replay after wrap. The stat-commit epilogue at
`0x1EEA96` rebuilds the projections from counters and never increments them.
Native new-game/stat initialization at `0x1ECAF0`, also used by the simulator,
zeros the entire allocation. The simulator does not invent new defensive
conversions from stale played-game counts.

### Field 59 is unused and handled by the native saved stream

**PROVED for the pinned USA executable and retail ROST:**

- None of the 183 native 28-byte descriptors at `0xA8A510` maps field 59.
- The postgame sum, conditional-count and threshold tables at
  `0x4FC528..0x4FC7F0` do not write field 59.
- None of the 36,866 used words in the retail roster history pool contains
  field 59, including deleted words. The test streams only the 593,792-byte
  ROST resource through the existing archive reader and checks the existing
  pool-and-pointer fingerprint.
- `0xAA26C0[59]` is the native sum rule within its 87-entry folding table.
  The existing TEAM category 87 remains independent.

The saved representation is the existing `player+0x2C` dword stream into
`[0xB72918]+0x44`: bits 0..15 signed value, 16..22 field, 23..27 slot,
28 deleted, 29 postseason class, 30 folded history, 31 end of stream.
**Correction to the early research memo:** bit 28 means deleted; setting it
would hide the entry. This implementation delegates encoding to retail.

The per-player postgame merge hook at `0x1336B2` reads the live source in EBP
and persistent target in EDI, adds the count through the native current-slot
reader `0x14EF00` and writer `0x14F430`, and marks the live count merged only
if the writer succeeds. The displaced class reset and continuation are
retained. Regular season and postseason inherit the native class selector.
Full x87 and SSE state is preserved around the added call through aligned
FXSAVE/FXRSTOR; the bounded test includes a nonempty x87 stack and all XMMs.
Counts and each saved slot saturate at 32,767, matching signed native storage.

Banks 0..7 read live game counts; 8/9 read career history; 10/11 read the
current slot; 12..26 use the native years-ago reader `0x14EF20`. Odd banks 9
and 11 include an unmerged live contribution, resolving the franchise record
through native `0xCA810`. After a successful merge the same live count remains
visible in the game but is not added to career/current season twice. Missing
exhibition history returns its live contribution without inventing a record.

Native tests execute the real writer, current/years-ago/career readers,
`0x14EFE0` fold-and-compact path, deletion, and regular/postseason filtering.
They serialize the whole bounded roster object through `0xC0730` and reload
it through `0xC0500` in a fresh Unicorn instance at a different address with
zero owned counters. Player/team/pool pointer relocation and the history
bytes survive; season/career readers return the saved counts. Only the
post-load team/cache setup calls `0x10E9D0` and `0x10E990` are stubbed at that
engine boundary. This is native roster serialization evidence, not execution
of Xbox storage APIs or a played franchise-save witness.

### Native presentation and failed attempts

The box-score table at `0xAED668` is cloned into owned RO storage, preserving
all 38 original rows and adding row 39, `Defensive 2pt Conversions`, integer
format, ID `0x4000`. `0x363690` returns 39; the three native label/ID/format
loads point into the clone. The actual `0x3636B0` reader and string formatter
return the expected home/away strings for the added row.

All six Player Card stats sheets gain a `D2PT` column with the full category
name in its description. The descriptor carries `0x40EA` because both retail
callbacks subtract `0xEA` from extended IDs. Each complete list header,
original column order and zero terminator is copied to owned RO. Two variants
retain the optional TEAM column; the `0x320B90` entry selects the recognized
retail/applied TEAM layout and writes only the native writable list-pointer
fields. No adjacent native descriptor is overwritten. Applying TEAM before
or after the extension produces identical XBE bytes. Native `0x320C60` finds
the season and Total row even when this is the only nonzero category, and
`0x320430` returns its float value. Offensive-line cards have no retail stats
sheet and retain that behavior.

The gamecast/play-event banner has its own classifier at `0xEC471` and label
consumer at `0xEBD35`. Scored tries select event 15, `DEFENSIVE 2PT RETURN`, or
16, `SAFETY ON TRY (+1)`, and set the actual beneficiary team. All 15 ordinary
labels remain unchanged. The existing period/game-over override at `0xEC4A5`
is retained. Native tests cover both drive teams, touchdown outcomes 1/6,
all three custom try subtypes, and the banner's real UTF-16 copy and epilogue.
The old play-by-play suffix path and numerical scoring-summary consumers also
remain tested. This does not claim that a graphical scorebug was rendered.

Six narrow wrappers at `0x1EEA1E/0x1EEA2A` and
`0x250D2F/0x250D3B/0x250D51/0x250D5D` preserve the offense's failed two-point
attempt when custom packed subtypes represent a defensive return or safety.
They distinguish a failed kick using the committed original-play metadata.
The native attempt reader and commit branches execute in a matrix of both
teams, both touchdown outcomes, returns/safeties and kick/two-point tries.
They do not reuse made offensive conversions as the new category.

### CPU scope

The earlier report's concrete end-zone wait gap was already fixed by the
`0x2E3786` wrapper. Its complete carrier transition at `0x2E36F0` still selects
`0x2E2DA0` with heading 0/0x8000 for CPU defenders in both directions; human
fixtures retain retail behavior. Added negative tests require phase 3,
defensive possession, the actual ball holder and CPU control. Other phases,
including an unknown phase, follow retail. There is no evidence justifying
another AI rewrite. Later navigation, pursuit, animation and possession
changes remain explicit gameplay hypotheses from the prior report.

## Allocation, refusal and composition

The original owner keeps 1,440 RX and 1,040 RW bytes, at frozen legacy
positions. Extension owner `nfl2k5_defensive_try_stats` reserves 2,048 RX
(1,122 used instruction bytes) and 4,096 RO, aligned to 16, with **zero new
RW**. The brief explicitly requests scale-out but gives no separate planned
defensive-stat row. Decision: add only these RX/RO rows and preserve every
other budget. The committed full-budget fixture passes with 49,728 RX,
4,096 RW and 8,704 RO bytes available to new owners before alignment.
No allocator geometry or other owner's request size was changed. XBE size
is 12,300,288 bytes.

`status`/`apply` validate all original/installed hook bytes, normalized context
fingerprints, native descriptor/merge/fold tables, TEAM compatibility, owned
RX/RO contents, initial RW data, allocator directory and section digests.
Mixed/foreign inputs fail before mutation, including partial extension
installs. Exact idempotence and complete instruction boundaries are tested.
Section digests are regenerated through the existing helpers. Data stays out
of `.text`; immutable tables use the named RO child. The tests protect RX and
the new RO allocation against runtime writes in Unicorn.

Both XBE gates compose every landed owner in forward/reverse order and
automatic/explicit scale-out. The manifest builder uses the existing single
writer transaction, recording both named owners and all four children.
Old applied discs without this child refuse and require a rebuild from base.

## Verification

Pinned private XBE SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Every suite below was run standalone with plain Python 3; private evidence,
Capstone and Unicorn skips are explicit. No suite skipped here.

| Command | Final result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_defensive_try.py` | 23 passed, 49.512 s |
| `python3 tests/mod_editor/test_nfl2k5_defensive_try_stats.py` | 21 passed, 19.646 s |
| `python3 tests/mod_editor/test_nfl2k5_defensive_try_manifest.py` | 3 passed, 4.200 s |
| `NFL2K5_CAVE_MANIFEST=.scratch/defensive-try/manifest.json python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 59 passed, 164.908 s; peak RSS 295,204 KiB |
| `NFL2K5_CAVE_MANIFEST=.scratch/defensive-try/manifest.json python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 71 passed, 245.308 s; peak RSS 480,828 KiB |
| `NFL2K5_CAVE_MANIFEST=.scratch/defensive-try/manifest.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed, 71.956 s; peak RSS 910,864 KiB |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | PASS, 36 requests, all planned budgets fit |
| `python3 -m mod_editor.core.nfl2k5_defensive_try status <retail-default.xbe>` | retail, experimental true, runtime_witnessed false |

**205 tests passed.** Every Unicorn entry has a 20,000-instruction bound and
uses small synthetic objects with real retail instructions. Full gameplay
`0x1EDC60` is not run end to end; the new stat epilogue, attempt branches,
committed-history path, season hook and native readers/writers are bounded
separately. Stubbed engine callbacks are identified in the fixtures. No full
disc or archive pack was loaded into RAM. The largest measured process was
under 1 GiB, below the 2 GB limit.

The replacement capability passes full-registry structural validation and
its own backend, validator and evidence file checks. Full-registry file-check
mode stops on the pre-existing missing `docs/research/apf_audio.md` in the
first, unrelated capability; the canonical registry is unchanged. Integration
must restore that evidence before claiming the entire registry file gate.
`git diff --check` also passed.

The production manifest is protected and intentionally unchanged. The scratch
projection was created with:

```text
python3 tests/mod_editor/test_nfl2k5_defensive_try_manifest.py --write-projection .scratch/defensive-try/manifest.json
```

It observes the real allocator and changed writer through Recorder, replaces
old grown child addresses with the new complete union, and inherits other
reservations only after checking their source fingerprints. It refuses an
unrelated changed source, and its result still passes the normal source-drift
guard. The JSON explicitly marks inherited disc steps and no new disc build.
These gates are bounded XBE evidence; Claude must regenerate the canonical
disc-build manifest after protected integration. Main-drive free space was
102 GB, so a disposable 6.3 GB disc would breach Noah's 100 GB floor. No disc
build was started. Scratch contains only notes, logs, JSON and research/test
scripts, well below 200 MB.

## Known limits and Noah's witness list

**Implemented save boundary:** completed-game player season/career history,
including the player records in a franchise roster. **Not implemented:**
serialization of the owned current-game counts/attempt metadata in suspended
saves, and a new field in archived per-game franchise box-score records.
Reloading a suspended game is unsupported for this new stat. Historical team
totals are sums over current roster membership, not a permanent team ledger
across trades. The new column is on existing Player Cards; this does not add
a League Leaders sorting category or an offensive-line stats sheet.

Native slots and live counts saturate at 32,767. Replacement identity covers
2^23 absolute drive numbers; no claim is made for counter overflow or drive
identity wrap beyond those limits. Stat-pool exhaustion remains the native
writer's allocation/folding policy. A failed write does not mark the count
merged; there is no new save-pool expansion. Gameplay review/penalty rollback
outside the committed replacement path has not been witnessed.

Noah should use a freshly rebuilt disposable witness disc, recording the
build hash/options, teams, quarter/time, possession changes and screenshots:

1. Interception, fumble recovery and blocked PAT returns, with each defense
   in each field direction. Score +2; TD team still kicks off. A run ending
   short scores nothing. Include a second possession change before the score.
2. Give a CPU defender possession in its own end zone and in the field. It
   should attempt the return, navigate pursuit and cross the correct goal
   line. Compare human possession, ordinary kickoffs/punts and ordinary plays.
3. Try safeties for each beneficiary, including blocked kicks out of the end
   zone and an intentional-bat/impetus case. Score +1, correct kickoff team,
   safety banner, and no defensive-conversion count.
4. Open the actual game box score after one return and after two different
   defenders score. Check the new row, both teams, scorer attribution and
   player points (+2 each). Offensive made conversions remain unchanged and
   the unsuccessful original two-point attempt remains counted. Compare a
   blocked PAT return, which must not create a two-point attempt.
5. Inspect the scorebug, quarter/drive summary, play-by-play suffix and native
   event banner together. Check the correct team, text width, navigation and
   unmodified ordinary labels. Narration may still use retail wording.
6. Finish a franchise game, inspect the scorer's D2PT/current season/Total
   values, save, exit and reload. Repeat a second game and verify addition.
   Check a regular-season game and a playoff game separately. Advance a
   season and verify the prior-year value; compare TEAM-column on/off and
   each of the six supported position sheets. Check unrelated stats too.
7. Exercise replay, review reversal, accepted penalties and retries. A
   canceled score must not persist and an accepted retry must credit once.
   Test quarter/game expiration and overtime, both kick-rule settings and
   relocated kickoff on/off. Confirm period/game-over banners still win.
8. Check a played game followed by a simulated game and a new exhibition:
   no old count should leak. Record suspended-save and archived-game behavior
   as the known unsupported cases above, not as successful persistence proof.

All defaults remain off. `WIRING.md` gives the exact dispatcher/BuildPlan/UI,
allowlist, closure, capability replacement and manifest regeneration handoff.

## Delivery

Explicit-path staging succeeded in the supplied worktree, so delivery uses a
direct commit on `astra/r62-defensive-try-boxscore`. The 12 named source,
test, fixture, capability and report/handoff files are the complete change.
`ASTRA_BRIEF.md`, `.scratch/`, generated executables and retail resources are
excluded. No push was performed and no bundle fallback was needed.

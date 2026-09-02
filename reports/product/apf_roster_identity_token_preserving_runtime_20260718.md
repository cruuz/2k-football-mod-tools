# APF 2K8 token-preserving roster-identity runtime receipt — 2026-07-18

## Completed experiment

**Positive.** A team-only `roster/ROST` candidate built with the
retail-token-preserving H7A encoder booted through APF's fresh-profile path,
visibly rendered the injected built-in team name `CODEXTEAM` on Logo Selection
and Team Summary, reached a stable Team Select screen, and exited cleanly.

This experiment closes the runtime blocker for the bounded built-in team
display-name route. It supersedes the broad interpretation of the earlier
generic-rebuild negative while preserving that negative as a valid historical
control. It does not runtime-prove player names or any non-name roster field.

## Pinned environment

- Project root: `/media/noah/Storage/for codex 1.0`
- Emulator: Xenia Canary `canary_experimental@6e5b8324f`, built 2026-07-08
- Title ID: `54540807`
- Emulator configuration SHA-256:
  `921e4c13d648c25cb7e01ee96e38a4ad8c8c7dcf80879211ee37d2a5865cf04f`
- Isolated graphical session: `DISPLAY=:99`
- Persistent roots:
  `.codex-tmp/apf-four-family-runtime-sdl/runtime-roster-token-preserving-alpha15/{storage,content,cache}`
- Initial Xenia log reported `ProfileManager: Found 0 Profiles`, proving the
  run entered the clean first-run path rather than reusing an old team profile.
- All visual inspection and controller operation ran in the isolated graphical
  session; the operator's live desktop was not touched.

## Source and candidate receipt

| Property | Value |
| --- | --- |
| Untouched source | `extracted/All-Pro Football 2K8 (USA)/0A` |
| Source `0A` SHA-256 before and after | `dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e` |
| Candidate game | `.codex-tmp/apf-roster-team-only-token-preserving-alpha15` |
| Candidate `0A` size | 1,140,850,688 bytes |
| Candidate `0A` SHA-256 | `4c51030bcb1ea6a47d618ffa89d6a66da1d86183650d8591980989028cb0a37d` |
| Build receipt | `.codex-tmp/apf-roster-team-only-token-preserving-alpha15/.apf2k8-mod-studio-build.json` |
| Build-receipt SHA-256 | `8785e966eaf4e96d8061defa1f3ebe62b074f8579f5f04d1ab53ca9a049bd2aa` |
| Build-receipt size | 1,568 bytes |
| Changed outer entry | index 1,126, `roster/ROST` |
| Rebuilt outer-entry size | 436,224 bytes |
| Rebuilt outer-entry SHA-256 | `cb38227effc8b1cd27452e1ed9b4e4df008fb0f915cfec0e3c6a59da2c4d0451` |
| Stable target | `apf:roster-name:4776`, `team:0:display_name` |
| Authored value | `Americans` → `CODEXTEAM` |

The target is the 20-byte decoded allocation at `0x21C564..0x21C578`.
Both source and replacement use nine UTF-16BE code units plus the existing
terminator. Exactly nine decoded bytes changed because the high bytes of these
ASCII code units remained zero. No pointer, count, record, membership field,
reserved-workspace byte, or other string allocation changed.

The build receipt records:

- source opened read-only and `source_modified: false`;
- distinct source/output inodes;
- atomic output publication;
- all bytes outside the one changed outer entry identical;
- all unchanged sibling files matching the source; and
- the rebuilt entry reparsing successfully.

## Transport comparison

The semantic edit is identical to the earlier failed team-only control. The
transport is the only intended causal change.

| Property | Failed generic candidate | Successful token-preserving candidate |
| --- | ---: | ---: |
| Decoded body bytes changed | 9 | 9 |
| H7A strategy | Fresh greedy parse of all 2,294,304 decoded bytes | Replay retail tokens; repair intersecting tokens only |
| Retail token count | 284,015 | 284,015 |
| Retail tokens preserved semantically | Not preserved as a contract | 284,004 |
| Retail tokens split or replaced | Whole stream regenerated | 11 |
| H7A payload size | 434,269 | 435,246 |
| Delta from retail payload | -956 | +21 |
| IFF file length | 434,373 | 435,350 |
| Outer-entry size | 436,224 | 436,224 |
| Entry SHA-256 | `a7dca20498b5179f85d5509c50e47ccf04f41d570d26652071ee9b3f5fbca960` | `cb38227effc8b1cd27452e1ed9b4e4df008fb0f915cfec0e3c6a59da2c4d0451` |
| Runtime | Crash at `0x84AB1D40` | Boot, visible consumption, clean exit |

The successful entry hash exactly matches the team-only token-preserving
candidate predicted by the prior forensic comparison. This connects the
offline token analysis to the exact bytes consumed in the positive runtime.

## Runtime transcript

1. The private launcher started the candidate from a separate game directory
   with new storage/content/cache roots.
2. Xenia loaded `GAME:\default.xex`, title ID `54540807`, and initialized a
   new controller in slot 0.
3. The game rendered the normal demo/Did You Know presentation without the
   generic candidate's intro-time access violation.
4. START entered the first-run profile screen. The flow continued through
   profile naming and Team Create.
5. At Logo Selection, the built-in team name rendered as `CODEXTEAM`.
6. At Team Summary, `CODEXTEAM` rendered again, proving repeat consumption
   after advancing the first-run flow.
7. The run reached a stable Team Select screen with `CODEXTEAM` present.
8. Xenia was closed cleanly. The final log line was `Cheap-skate exit!`; no
   `Access Violation` record or crash dialog occurred.

## Evidence chain

All captures are 5.000 seconds long.

| Exact evidence path | Bytes | SHA-256 | Proved observation |
| --- | ---: | --- | --- |
| `/home/noah/backbreaker-research/evidence/live-captures/apf-roster-token-preserving-team-name-consumption-20260718.mp4` | 545,906 | `f8b14cd8df3e17586297f758aeb19d7ada54b3876e7e8fdc047557c21ff81bf9` | Logo Selection visibly renders `CODEXTEAM`. |
| `/home/noah/backbreaker-research/evidence/live-captures/apf-roster-team-summary-codexteam-20260718.mp4` | 204,641 | `ec1cd8ee93d6cf0d8248cf35b199f1fc7b361dabf9080c41a43d5160a55d8c8b` | Team Summary visibly renders `CODEXTEAM`. |
| `/home/noah/backbreaker-research/evidence/live-captures/apf-roster-team-select-codexteam-20260718.mp4` | 205,384 | `b8fa43e02396fd3d9e2363134ff63c26d8d3ab02b3478b9063fa1c95c0610e52` | Stable Team Select reached with the changed team identity consumed. |

The Xenia log is:

- path: `.codex-tmp/apf-four-family-runtime-sdl/logs/xenia-roster-team-only-token-preserving-alpha15.log`;
- size: 121,494 bytes, 1,860 lines;
- SHA-256: `f9c991c704cc265f5b3adbdef529a6f7d15c8a42400e22220c6ba9555cc67621`;
- build banner at line 1: `canary_experimental@6e5b8324f`;
- title ID at line 216: `54540807`; and
- clean terminal record at line 1,860: `Cheap-skate exit!`.

The routine Xenia warnings and unimplemented-host messages in the log did not
produce a guest crash. The discriminating negative signature—guest PC
`0x84AB1D40` plus access violation at host `0x0000000270000000`—is absent.

## A/B conclusion

The old team-only and new team-only builds have the same target, same replacement
text, same fixed decoded allocation, same outer entry, same emulator commit,
and same pinned configuration. The meaningful implementation difference is
generic full-stream retokenization versus retail-token-preserving local repair.
The former crashes consistently; the latter boots and renders the authored
value repeatedly. This is sufficient runtime evidence to retire the generic
compressor for `ROST` and accept the token-preserving route for bounded team
display-name writes.

It does not establish that the guest rejected every syntactically possible
generic H7A stream. It establishes the product-relevant fact that the local,
minimal-transport route works and the previous route must not be used.

## Remaining boundary

Runtime proof applies only to one built-in team display name. It does not prove:

- a player first/last name through the token-preserving route;
- team abbreviations or secondary abbreviations;
- aliased allocations with multiple semantic owners;
- jersey numbers, ratings, positions, abilities, membership, or depth charts;
- roster-count or team-count expansion; or
- original Xbox 360 hardware behavior.

The next bounded experiment is a player-only token-preserving build with a
known screen-level consumer. It should reuse this exact environment and compare
only the changed entry and rendered value.

## Rollback and cleanup receipt

After capture:

- Xenia exited cleanly and no Xenia/controller-injection process remained;
- `.codex-tmp/apf-four-family-runtime-sdl/control.fifo` was absent;
- the private launcher was restored byte-for-byte to SHA-256
  `724708e07c90fe49a90a5b3005aa5648053c2ad3effe4c84e6397eb483bd46aa`;
- the sealed Alpha 14 release tree/archive/sidecar were not modified; and
- the candidate remains private because its complete game directory contains
  user-owned retail bytes and is not a distributable artifact.

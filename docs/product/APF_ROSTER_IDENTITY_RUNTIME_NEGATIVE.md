# APF 2K8 roster-name runtime result: historical generic-transport negative

Date: 2026-07-18  
Current status: **Superseded for token-preserving team display-name edits**

## Classification

This document preserves the negative control for the original generic rebuilt
`ROST` transport. It is not the current conclusion for all roster-name edits.
A subsequent team-only build using the repaired retail-token-preserving H7A
route booted, visibly rendered `CODEXTEAM` on multiple screens, reached Team
Select, and exited cleanly. See the
[positive runtime report](APF_ROSTER_IDENTITY_TOKEN_PRESERVING_RUNTIME.md).

The historical negative remains important because it proves the generic greedy
whole-stream compressor must never be used for `ROST` authoring.

## Historical controlled replay

All four historical runs used the same user-owned source, Xenia Canary build,
pinned configuration, and separate empty persistent-state roots.

| Build | Only authored change | Historical runtime observation |
| --- | --- | --- |
| Clean control | None | Reached the normal APF title screen. |
| Combined generic rebuild | One team display name and one player last name | Crashed during the 2K/Visual Concepts intro. |
| Team-only generic rebuild | One legal same-allocation team display name | Same crash. |
| Player-only generic rebuild | One legal same-allocation player last name | Same crash. |

Every generic changed build stopped at the exact same guest failure:

```text
Thread Handle: 0xF8000028
PC: 0x84AB1D40
Access Violation: read at 0x0000000270000000
```

The clean control ruled out the source/emulator path. The two single-edit runs
ruled out one particular string or one identity family as the common cause.
The shared changed component was the generic rebuilt `roster/ROST` transport.

## What was subsequently isolated

The semantic roster bodies were correct: the team-only candidate changed nine
decoded UTF-16BE bytes and no pointer, table, count, record, or unrelated string.
The defect was transport amplification. The generic compressor regenerated the
entire H7A stream, changed about 412,821 comparable payload bytes, and moved the
IFF footer 956 bytes for that nine-byte edit.

A static trace showed that the crashing guest entered ROST table-5 fixup with
an already-absolute pointer and applied relocation again. A token-preserving
encoder then removed the amplification: it retained 284,004 of 284,015 retail
tokens, repaired only 11, and grew the payload by just 21 bytes. That exact
candidate booted and visibly consumed the edited team name.

## Current product boundary

| Capability | Current evidence |
| --- | --- |
| Generic rebuilt `ROST` transport | Runtime-falsified; retired. |
| Token-preserving built-in team display name | Runtime-positive for one bounded field. |
| Token-preserving player name | Offline-proved; runtime consumption not yet tested. |
| Team abbreviations/secondary abbreviations | Offline mapped; no repaired-route runtime proof yet. |
| Jersey numbers, membership, depth charts, roster capacity | Separate capability lanes; not unlocked. |

The product may expose a team display-name writer only when its facade and build
pipeline force this token-preserving route and enforce the original allocation
limit. The historical generic encoder must remain unreachable. Player-name
Replace should stay Preview until a player-only repaired build visibly renders
the authored value.

## What this negative still proves

It proves that passing the project's own decoder is not sufficient runtime
evidence and that broad compressed-transport rewrites can break a correct
decoded graph. It also remains the A side of a strong causal comparison:
same field and same authored value, generic transport crashes; token-preserving
transport boots and consumes the value.

It no longer supports the claims that fixed-allocation roster-name replacement
is generally impossible, that every changed `ROST` crashes, or that team
display names must remain permanently read-only.

## Distribution boundary

The source game is opened read-only and every experimental output is a separate
copied game. A built game contains retail data and is never distributable.
Shareable Mod Studio projects contain only user-authored replacement text and
metadata, never the original `ROST`, source strings, preimages, or physical
offsets.

## Related reports

- [Current token-preserving positive](APF_ROSTER_IDENTITY_TOKEN_PRESERVING_RUNTIME.md)
- [Bounded roster identity writer](APF_ROSTER_IDENTITY_WRITER.md)
- [Static trace of the generic crash](APF_ROSTER_CRASH_STATIC_TRACE.md)

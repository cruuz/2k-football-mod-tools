# APF 2K8 token-preserving player-rating runtime result

Date: 2026-07-18  
Classification: **Runtime-positive for transport and edited-player record load**  
Behavioral status: **Direct numeric/gameplay effect not yet proved**

## Result

A bounded `roster/ROST` build changed Dan Marino's stored **Speed** base rating
from `40` to `99`. The decoded semantic diff was exactly one byte. The
token-preserving H7A compiler retained 284,014 of the source stream's 284,015
tokens and repaired only the token intersecting that byte.

The complete candidate booted normally in Xenia. It passed the title and
fresh-profile screens, entered Team Create, opened Gold Player selection, and
selected Dan Marino. His player card and 3D presentation rendered normally.
The earlier generic-ROST crash at guest PC `0x84AB1D40` did not recur.

This is positive runtime evidence that the repaired archive route can carry a
one-byte rating edit and that the game can load, select, and render the edited
player record. It is not yet proof that Speed-dependent gameplay consumed the
new value: APF's Star Card displays biography and ability information, not the
underlying numeric base ratings, so there was no numeric `99` to read directly
from that screen.

## Controlled edit

| Property | Value |
| --- | --- |
| Stable target | Player record 788, `speed` |
| Player used for the spot check | Dan Marino |
| Record-relative rating byte | `+0xBA` |
| Stored value | `40` → `99` |
| Decoded bytes changed | 1 |
| Source H7A tokens | 284,015 |
| Tokens preserved | 284,014 |
| Tokens repaired | 1 |
| Rebuilt outer allocation | 436,224 bytes, unchanged |

The replacement remained within the native one-byte `0..100` setter contract
and the product's default `0..99` modder-facing policy. No scaling, tier
conversion, inferred Overall value, or adjacent unknown field was involved.

## Runtime path

The spot check used Xenia Canary `canary_experimental@6e5b8324f` in an isolated
`DISPLAY=:99` session. It did not touch the operator's live desktop. The path
observed was:

1. normal title startup;
2. a fresh no-profile prompt;
3. Team Create;
4. Gold Player selection;
5. selection of Dan Marino; and
6. stable rendering of his player card and presentation.

The emulator log ended with a normal `Cheap-skate exit!` record. It contained
neither the old `0x84AB1D40` guest-PC signature nor its associated access
violation.

One private evidence capture records the successful selection and render:

| Evidence basename | Bytes | SHA-256 |
| --- | ---: | --- |
| `apf-marino-speed99-token-preserving-runtime-20260718.mp4` | 734,146 | `113de8c9d5f2547e88c024a0333910c21be7cdb1993da9f4aba2db807f4f45a1` |

The capture is an audit artifact and is not distributed with Mod Studio.

## What this proves

- A semantic player/rating identifier can resolve to the intended fixed byte.
- A one-byte `40` → `99` decoded edit can be compiled without retokenizing the
  rest of the roster.
- The fixed outer allocation can be rebuilt while preserving 284,014 of
  284,015 H7A tokens.
- The resulting complete game can boot through the fresh-profile route.
- APF can load, select, and render the modified player record without the
  historical generic-compressor crash.

## What this does not prove

- The Star Card did not display a numeric Speed value, so it did not visually
  prove `99` as a number.
- No timed sprint, controlled play, or stock-versus-patched gameplay A/B was
  performed. A Speed consumer and effect size remain unmeasured.
- Values `0`, `50`, and native `100` were not runtime-tested by this experiment.
- Other ratings share the mapped byte/setter pattern but were not each tested
  in Xenia.
- Overall, abilities, Gold/Silver/Bronze tier, fatigue/injury modifiers,
  created-player saves, team membership, and roster capacity remain separate
  systems.
- Original Xbox 360 hardware was not tested.

## Product boundary

The result removes the repaired `ROST` transport as the blocker for bounded
base-rating writes. A product writer must still enforce all of these rules:

1. address edits by semantic player and rating IDs, never user-entered offsets;
2. accept `0..99` by default and label native `100` as an advanced maximum;
3. change only the selected decoded rating bytes;
4. compile through the token-preserving H7A route;
5. retain the source game read-only and publish a separate build atomically;
6. store only user-authored semantic edits in shareable projects; and
7. keep the distinction between **runtime-load proved** and **gameplay-effect
   proved** visible until a controlled field test closes it.

The full candidate contains the user's retail game and is private. Neither it,
the rebuilt roster entry, source hashes, preimages, nor rollback bytes belong
in a release or shareable project.

## Best next proof

Run a controlled stock-versus-patched sprint or repeated deep-route test with
the same player and conditions. A measurable Speed-dependent difference would
promote the result from transport/player-load proof to gameplay-consumer proof.
If an internal ratings screen is recovered first, use it to spot-check `0`,
`50`, `99`, and native `100` without replacing the gameplay A/B.

## Related documents

- [True 0–99 base-rating map](APF_TRUE_099_PLAYER_RATINGS.md)
- [Token-preserving roster-name runtime proof](APF_ROSTER_IDENTITY_TOKEN_PRESERVING_RUNTIME.md)
- [Historical generic-transport negative](APF_ROSTER_IDENTITY_RUNTIME_NEGATIVE.md)
- [Static trace of the historical crash](APF_ROSTER_CRASH_STATIC_TRACE.md)


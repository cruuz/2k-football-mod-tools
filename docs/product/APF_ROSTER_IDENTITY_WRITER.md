# APF 2K8 bounded roster identity writer

## Current classification

The repaired writer is **runtime-positive for one built-in team display-name
edit**. It preserves the retail H7A token stream and rebuilds only tokens whose
decoded spans intersect authored bytes. The exact team-only candidate booted,
rendered `CODEXTEAM` on Logo Selection and Team Summary, reached stable Team
Select, and exited cleanly in Xenia.

The evidence is intentionally family-specific:

- built-in team display name: runtime-proved for one bounded allocation;
- player first/last name: mapped and offline-proved, but the repaired transport
  has not yet been visually consumed at runtime;
- team abbreviations and secondary abbreviations: mapped and offline-proved,
  but not yet runtime-proved through the repaired route; and
- jersey numbers: read-only/unmapped as a consumer-backed field.

## Offline mapping boundary

The live APF roster maps 4,628 proved identity-field references:

- 4,508 player first-name/last-name references across 2,254 player records; and
- 120 team display-name, abbreviation, and secondary-abbreviation references
  across 40 team records.

Those references resolve to 3,273 underlying UTF-16BE allocations. The writer
can address exactly 3,272 nonempty allocations; one zero-capacity empty
allocation is structurally read-only. Aliasing is real and common: when
multiple mapped fields point to one allocation, the inventory exposes the
complete known owner count and a stable owner fingerprint.

The writer never relocates a roster pointer or grows a string. A replacement
must fit the allocation's source-derived UTF-16 character limit. It writes the
new text, a terminator, and zero fill through the remainder of that same span.
Every changed field is therefore an in-place decoded-body edit.

## Retail-token-preserving H7A transport

The original implementation passed the complete 2,294,304-byte decoded roster
to a generic greedy H7A compressor. A nine-byte team-name edit consequently
changed about 412,821 comparable compressed bytes and shifted the footer 956
bytes. That generic route was self-consistent offline but crashed at startup in
all three changed Xenia controls. It is retired and must never be reintroduced.

The current encoder parses the retail payload into its original literals and
matches, walks them in decoded order, and handles each token as follows:

1. If the token's decoded span is unchanged, emit the retail token exactly.
2. If an authored byte invalidates a literal, emit the changed literal at the
   same decoded position.
3. If an authored byte intersects a match, split only that match into a bounded
   sequence that reproduces the intended decoded span.
4. Preserve every later retail token whose source and output semantics still
   agree.

For `Americans` → `CODEXTEAM`, this strategy preserved 284,004 of 284,015 retail
tokens and split or replaced 11. The payload grew from 435,225 to 435,246 bytes,
the rebuilt file remained inside the original 436,224-byte outer allocation,
and the independent parser decoded exactly the intended body.

No-op builds return the exact source entry. A changed build reports the retail
token count, tokens preserved semantically, tokens split/replaced, output token
count, compressed size, file length, and fixed-allocation validation in its
private compiler receipt.

## Validation and failure behavior

Before returning a changed entry, the writer requires all of the following:

- every replacement fits its original UTF-16 allocation;
- the source owner fingerprint and allocation facts still match;
- all relative-pointer bytes remain bit-exact;
- the H7A stream decodes to the intended body;
- the rebuilt IFF reparses without warnings;
- the footer and unrelated inner parts remain unchanged;
- the output fits the original fixed outer allocation; and
- a second semantic roster parse resolves every edited allocation to its
  requested value.

Overflow, source drift, owner drift, an unrelated decoded-byte change, an H7A
round-trip mismatch, an IFF warning, semantic parse failure, or allocation
growth fails closed before a build can be published.

## Runtime proof

The controlled positive used the same team-only authored value as the historical
failed build and changed only the transport implementation.

| Build | H7A behavior | Runtime result |
| --- | --- | --- |
| Historical team-only control | Fresh greedy parse of the entire roster | Crashed at guest `0x84AB1D40`. |
| Repaired team-only candidate | 284,004 retail tokens preserved; 11 locally repaired | Booted, rendered `CODEXTEAM` repeatedly, reached Team Select, clean exit. |

The positive run traversed a fresh-profile first-run flow, so the observed text
was not supplied by a reused saved profile. It rendered on both Logo Selection
and Team Summary before the stable Team Select observation.

This proves the built-in team display-name consumer and the repaired on-disc
transport together. It does not automatically prove all other mapped identity
owners.

## Product contract

Team display-name replacement is eligible for a bounded Editable surface once
the product facade guarantees that every such build uses this encoder. The UI
must show the exact per-allocation character limit, reject growth in plain
language, preserve individual/project-wide Revert, and keep the source read-only.

Player first/last names and untested team abbreviation families should remain
Preview until a repaired-route runtime spot check proves their consumers. A
legacy project made with the retired generic route may be opened, but it must be
recompiled through the current token-preserving writer rather than replaying a
stored rebuilt entry.

## Distribution contract

The shareable project representation contains only canonical user-authored text
and four small target facts: pool index, character limit, known owner count,
and owner fingerprint. It contains no source text, source preimage, rebuilt
roster bytes, or physical offset.

The user's source game is opened read-only, and Build publishes a separate game
directory atomically. A built game necessarily contains the user's retail data
and must not be distributed. Mod Studio, its templates, and shareable projects
must contain zero retail bytes.

## Jersey-number boundary

No APF jersey-number writer is exposed. The decoded on-disc roster evidence maps
names, positions, biography fields, teams, stadiums, and membership pointers,
but it does not identify a consumer-backed jersey-number field. A packed byte is
not promoted merely because a value resembles a uniform number.

The best next jersey-number experiment remains a controlled one-variable
save/profile comparison: change one player's displayed number, locate the exact
packed field, and trace an executable accessor that consumes it. Until ownership
and consumer evidence agree, jersey numbers remain explicitly read-only.

## Best next identity proof

Build one player-only candidate with the token-preserving route, boot with the
completed private profile, navigate to a roster/player screen that renders the
selected player, and capture the changed name. This is a bounded runtime proof,
not another offline hardening pass.

## Related product documents

- [Token-preserving runtime proof](APF_ROSTER_IDENTITY_TOKEN_PRESERVING_RUNTIME.md)
- [Historical generic-transport negative](APF_ROSTER_IDENTITY_RUNTIME_NEGATIVE.md)
- [Static trace of the historical crash](APF_ROSTER_CRASH_STATIC_TRACE.md)
- [32-team and 53-player feasibility](APF_32_TEAM_53_ROSTER_FEASIBILITY.md)
- [APF Mod Studio Getting Started](../mod_editor/apf2k8_mod_studio_getting_started.md)

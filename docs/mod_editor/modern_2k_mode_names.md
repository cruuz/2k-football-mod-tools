# Modern 2K mode names

EXPERIMENTAL / UNWITNESSED. The naming option uses **Play Now**, **MyNFL**, and
**MyPlayer** for the existing Quick Game, Franchise, and player creation menus.
MyNFL is Noah's chosen NFL adaptation. It is not a claim that 2K sells an NFL
mode under that name. Names do not change the rules or add a card mode.

Text & Team Identity has a **Modern mode names** page showing every discovered
replacement, its original value, exact output, location, and text limit.
The Build option caption is **Modern 2K mode names (MyNFL, MyPlayer, Play Now)**.
Basic and Advanced leave it off. Experimental may enable it only when the entire
mapping, including the MyCareer text contract, passes the fixed-span validator.
A foreign source or conflicting manual text edit refuses the build.

The standalone preview is implemented in this branch. Shared Build/Studio
integration is assigned to Claude in the last modern-naming section of
`WIRING.md`; until that wiring is applied, the page explicitly says that its
mapping preview is not connected to the source or Build selection.

## Names kept and choices made

Practice, Tournament, Season, Coach's Desk, The Crib, and Crib Credits keep
their names. Player statistics and User Career Milestones remain distinct from
MyCareer. The Crib is already a period-appropriate 2K hub. Coach's Desk is the
hub inside MyNFL. Internal identifiers such as `FRANCHISE1`, asset filenames,
and generic mentions of an NFL franchise in trivia and simulated news are
preserved. Load/save type numbers and saved filenames are preserved.

**Team Create / Create Team stays as authored.** This is the chosen default.
An optional future label could be **Team Builder**, after checking both titles'
spans. **MyTeam is not enabled**: in NBA 2K it describes card collection and team
building, and renaming an ordinary team creator would imply mechanics absent
here. Only an explicit new naming decision should add that mapping.

## Offline 2K naming research

This is recalled naming knowledge, as requested, with no network verification.
Exact platform/edition availability is not independently certified. The following
is naming guidance, not evidence of NFL 2K5's screen behavior.

| Family / term | Meaning and capitalization | Honest NFL 2K5 mapping |
|---|---|---|
| NBA 2K26 MyCAREER | Individual player career, commonly written MyCAREER in marketing | The separate new career feature is MyCareer; this pass does not create it |
| NBA MyPLAYER | Created player identity/customization used by the career ecosystem | Create Player and Player Create become MyPlayer, without suggesting progression was added |
| NBA MyTEAM | Card collection and fantasy team mode | No mapping to Create Team |
| NBA MyNBA / MyNBA Eras | Franchise simulation, with Eras as historical starting contexts; successor family to MyLEAGUE and earlier MyGM, not evidence those names vanished everywhere | Franchise becomes MyNFL by Noah's decision; no invented Eras selector |
| MyGM / MyLEAGUE | Management and league simulation branding; MyGM is also used by WWE and has distinct implementations | Neither replaces MyNFL |
| NBA Play Now | Immediate match/exhibition family | Quick Game becomes Play Now |
| The City / Neighborhood | Social/play hubs, with branding varying by platform and release | Keep The Crib and Coach's Desk; no city or online hub is added |
| MyPOINTS | Player progression points, not a game mode or ordinary spendable currency | No mapping; Crib Credits remains the currency label |
| Seasons / Season | Live progression seasons versus an actual sports season; meanings depend on context | Keep Season; no live service pass is implied |
| WWE 2K25 | MyRISE is its story/career brand; MyGM is management; MyFACTION is its card mode; Universe is sandbox booking; The Island is a hub on supported platforms | Do not transplant wrestling brands or call every 2K career MyCAREER |
| PGA TOUR 2K25 | MyCAREER and MyPLAYER are appropriate career/avatar brands | Supports the MyCareer/MyPlayer convention; no card-mode implication |
| TopSpin 2K25 | MyCAREER, MyPLAYER, MyPLAYER Tour, and 2K Tour distinguish career/avatar and online competition; Exhibition is not universally called Play Now across 2K games | Use only the career/avatar analogy, not a tennis tour label |

The shipped text follows Noah's requested mixed case **MyCareer**, **MyPlayer**,
**MyNFL**, and **Play Now**. Marketing's MyCAREER/MyPLAYER/MyTEAM uppercase
suffixes are not an instruction to uppercase all NFL labels. Never mechanically
capitalize ordinary words such as a player's career statistics.

## Editing the versioned mapping

Edit only `desired` and `fallbacks` in
`data/nfl2k5_modern_naming_2k.json`. The source strings, locations, IDs, allocations,
wrapper/section pins and mapping version are protected by a separate structural
hash. Changing a location or version requires a reviewed code revision, not a
silent relocation through user JSON.

For each row the writer tries `desired`, then the listed `fallbacks` in order.
All candidates must preserve controller, formatting and link placeholders in
order. UTF-16 code units are counted, including both halves of a surrogate pair;
the limit excludes the terminating NUL. Every unused byte is zero-filled.
Nothing is truncated, expanded into adjacent space, or silently skipped.
All 24 default replacements fit their full spelling, so their fallback lists
are empty. For example, a user can request a long Play Now label with
`"fallbacks": ["Play Now", "Play"]`. An exhausted list refuses the whole pass
and disables Experimental preset admission.

Changing the JSON after building creates a different installation definition.
An older different output is foreign to it. Rebuild from the original source,
or restore using the exact manifest that wrote the previous output. Receipts
include the mapping version and canonical manifest SHA-256.

## Backend and restoration

```sh
python3 -m mod_editor.core.nfl2k5_modern_naming check
python3 -m mod_editor.core.nfl2k5_modern_naming preview
python3 -m mod_editor.core.nfl2k5_modern_naming preview /path/to/source.iso
python3 -m mod_editor.core.nfl2k5_modern_naming status /path/to/build-copy.iso
python3 -m mod_editor.core.nfl2k5_modern_naming apply /path/to/build-copy.iso --receipt /path/to/names-receipt.json
python3 -m mod_editor.core.nfl2k5_modern_naming apply /path/to/build-copy.iso --disable --original /path/to/original.iso
```

Apply writes in place to a **disposable build copy**. Use the existing Build
copy/publish transaction for final output. The standalone adapter preflights
both the XBE and archive resource, reads back all writes, and rolls back on an
ordinary write/readback failure. It is not power-loss atomic. It never reads a
whole retail disc or pack into memory and resolves relocated XDVDFS packs.

`status(payload)` / `apply(payload)` accept bounded XBE or full Crib STRG bytes.
`apply(payload, enabled=False, original=original_payload)` restores the source's
owned spans and recomputes the XBE string-section digest. Unrelated edits are
preserved. `apply_to_image(..., include_xbe=False)` is exclusively the Build
final DATA pass after its XBE dispatcher has applied the other half.

Turning the option off removes facade overrides and rebuilds from the original
source; it does not stage retail values as manual project edits. If the selected
source is itself named, disabling must require the retained original source.
The pure and image restoration APIs require it explicitly.

## MyCareer coordination

No MyCareer module or retail MyCareer row exists in this branch. The JSON
contains two owner-bound text contracts, `menu_row` and `screen_title`, with
proposed source spelling `My Career` and output `MyCareer`. These are **not
retail text-bank IDs**. The MyCareer session owns all descriptors, callbacks,
allocations and reachability. It calls:

```python
from mod_editor.core.nfl2k5_modern_naming import career_text
menu_bytes = career_text("menu_row", allocation_bytes=20)
title_bytes = career_text("screen_title", allocation_bytes=20)
```

Each needs at least 18 bytes for the default spelling and terminator. The
20-byte contract is the size of `My Career` plus its terminator; it is reserved
by that owner, never borrowed from a retail mode. MyCareer remains the new
feature's name even when the optional retail-mode renaming is off. Both jobs
must use the same immutable manifest snapshot during a build.

## Evidence boundary

The exhaustive changed-string table and every discovered static lookup reference
are first in `ASTRA_MODERN_NAMING_REPORT.md`. The 716-bank / 20,074-editable-string
catalogue was audited, but the key menu labels live outside those banks in
XBE section `.string_`. The pass changes 23 literals there plus one Crib STRG
allocation. Generic franchise nouns are deliberately excluded.

Source addresses, lookup IDs and fixed spans are proved offline. Screen roles
inferred from text/descriptor structure are labelled accordingly. No emulator,
GUI display, audio, game boot or played witness was used. In particular,
complete dynamic screen routing, pause/load labels, texture-baked ESPN overlays,
font rendering and clipping require Noah's witnesses. Renaming text does not
rewrite recorded commentary or raster art.

# Team backfield roles

The optional `hback_roles` roster-edits directive assigns an H-back depth role
to selected teams. It requires the complete modern position pools. It runs
after the final roster refresh and optional new-franchise pick initialization.

This uses one existing position, enum 8. The shared category is **FB / H-back**,
abbreviated **F/H**. A selected team's depth slot reads **H-B**, with header
**H-BACK**. Other teams retain **FB**. **HB** continues to mean halfback.
There is no second FA category, draft quota, player record or saved position ID.
An authored H-back replaces the player's previous TE assignment; it must not
also appear in the TE depth chain. Positions, depth ranks and memberships belong
in the accompanying guarded roster refresh, not in the label directive.

The team mask contains decisions for all 32 NFL clubs. Every row needs `team`,
`role` (`FB`, `H-B` or `unconfirmed`), HTTPS `sources`, and a nonempty `resolution`.
The document schema is `2k5_mod_studio_hback/v1`, with an ISO `as_of` date.
Unconfirmed decisions preserve the original depth label. Source confidence and
player identity can be retained as additional row fields. These are authored
team roles, not an automatic inference from a TE or holder depth-chart label.

The native slot getter at `243AE0` and header tail at `243E2C` use the current
depth team's asset ID and NFL-kind guard. Only the offense enum-8 record gets
an immutable alternate view. The shared unit table is never rewritten, so
switching teams cannot leak one team's label into another. Null, historic and
out-of-range teams retain the native record. Team roles remain fixed across
franchise years; player trades do not invent new position IDs or alter the mask.
The asset ID at team `+118` is a 16-bit field. Franchise initialization writes
its own index into the adjacent `+11A` word; reading a 32-bit asset ID would
silently disable labels for most franchise teams. Tests cover both packed
records and actual native saved-franchise team records.

Shared position names, plural selectors and CAP templates use the common
category. Existing count/getter pairs, draft quotas, auto-depth, roster
transactions and MyCareer keep their native position semantics. CAP template
ratings are unchanged. Player cards describe the shared position category;
they do not claim that every enum-8 player is personally an H-back.

The helper has a fixed 1,024-byte slot in the allocator directory page. With
tap burst and draft picks also present, 2,016 contiguous bytes remain for the
sealed metadata. Existing feature addresses and XBE size stay fixed; inactive
slots remain zero and allocator-owned. Earlier ordinary-pool installations
still validate and replay unchanged. The section stays read-only and gains
execute permission for the named helpers.

Installation checks the allocator seal, modern pools, exact FB record, both
reader prefixes, every pointer/hook site and the complete helper implementation.
Foreign or partial installs are refused. Replaying the same mask changes no
bytes. Installing a different mask requires rebuilding from the source image.

The roster refresh also repairs disjoint unused CAP placeholder name pairs
inside the existing name pool. Native creation requires an exclusive 68-byte
pair of adjacent 34-byte names. This preserves the creator's bounds and alias
guards instead of bypassing a “Roster is full” refusal.

Full-season testing also exposed zero-length contracts on records brought from
the unsigned pool onto owned rosters. Native IR payroll divides by the original
contract length. The refresh therefore requires a nonzero length for every
owned player. Optional `contract_initializations` rows supply all five native
contract fields plus a source and modeling rule. They initialize only an empty
zero-value, zero-remaining contract and preserve every existing nonzero term,
including later edits on replay. The dated pack uses the existing economy
pipeline's one-year minimum accounting model, explicitly labeled as a modeled
placeholder rather than an observed NFL contract. `ro1_contract_probe.py`
demonstrates the native IR fault, repair, and failing undo on separate instances.

`test_nfl2k5_hback.py` runs public schema tests and opt-in native checks with
`B77_RO1_XBE`, `B77_RO1_HBACK` and `B77_RO1_BODY`. The first input is the integrated
base executable before this owner. `ro1_hback_probe.py` runs the longer native
season/rollover/draft route from an installed XBE and roster. `ro1_hback_paths.py`
checks actual roster transactions and all-team auto-depth using a fresh native
save. These are CPU tests with declared hardware/rendering boundaries, not
screenshots or a witnessed console session.

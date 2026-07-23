# Draft AI findings for 2K5 Mod Studio

Status: bounded static experiment completed; runtime A/B still pending  
Date: 2026-07-18

## Product conclusion

The known seventeen-position weight table is a **Fantasy Draft CPU-priority
table**. It must not be presented as a fix for the Franchise rookie draft.
The Franchise draft problem remains a separate Coming Soon capability until
its own selector/scoring routine is located and tested.

2K5 Mod Studio may eventually expose the proved table as an emulator-only
experimental control named **Fantasy Draft CPU priorities**. It must retain
that exact scope in the UI. A preset based on this table cannot honestly be
called “Franchise Draft variety” or be claimed to change rookie-draft picks.

## Why the table is classified this way

The retail USA `default.xbe` contains seventeen little-endian floats at virtual
address `0x00589588` (file offset `0x0057EAA8`). The position order is QB, K,
P, WR, CB, FS, SS, RB, FB, TE, OLB, ILB, C, G, T, DT, and DE.

The complete executable contains exactly two direct references to the table:

- `0x0036EEFA`; and
- `0x0036EF22`.

Both references are inside the same position-priority builder beginning at
`0x0036EE70`. That builder counts the current roster by the seventeen position
codes, combines the table value with roster deficit and best-available-player
evaluation, and sorts the positions. Its only recovered caller is the player
selector at `0x0036F0A0`; that selector is in turn called by the draft action at
`0x0036F830`.

This whole state-machine cluster owns the Fantasy Draft presentation. The
adjacent executable strings include `Fantasy Draft`, `Draft round %u`,
`Fantasy Draft Round %d`, `Automatically finish all remaining Draft Picks for
all selected teams?`, and `Quitting will reset all unsaved data. Cancel the
draft?`. The action at `0x0036F830` advances that state, adds the selected
player, and opens the next selection step.

The executable also contains a separate Franchise offseason surface with
strings such as `NFL Draft`, `Draft Candidates`, `Let the Front Office handle
the Draft.`, `Take me to the NFL Draft.`, and `Rookie Signing Period`. No
direct reference from that surface reaches the seventeen-float table, and the
table has no third reference that could belong to a separate rookie-draft
scorer.

This is stronger than a name-based guess: it is an exhaustive literal-reference
result for the entire retail executable plus a closed caller chain for the two
references that do exist. It does not prove that two wholly different routines
could never share downstream helpers indirectly, but it falsifies the current
product idea that this table itself is an established Franchise-draft control.

## Safe product state

- Fantasy Draft table: Preview now; emulator-only experimental writer may be
  added after one headless xemu A/B.
- Franchise rookie-draft variety: Coming Soon.
- Original-Xbox hardware: unsupported for executable patches.
- Shareable project representation: preset identifier or seventeen user-chosen
  floats only. It must never contain the retail table bytes, an XBE section
  digest, an original executable span, or any other retail preimage.

Changing the table modifies the XBE `.rdata` section. A build must recompute
that section's internal SHA-1 and will necessarily invalidate the retail RSA
signature. This route is acceptable only for the explicitly supported xemu
target. The source XISO remains read-only and every build goes to a newly
created output.

## Completed runtime-control build

A bounded writer now builds an extreme **Special Teams Control** XISO for the
pending A/B. It changes the K and P weights to `100.0f` and all other position
weights to `0.01f`, refreshes the `.rdata` section digest, and writes only a
new copied XISO. This deliberately unrealistic distribution is an experimental
witness: if the known table controls CPU Fantasy Draft selection at runtime,
the effect should be obvious and easy to distinguish from normal variance.

The full 6,300,499,968-byte build and comparison completed successfully:

- source SHA-256 before and after:
  `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`;
- output SHA-256:
  `11a2f1e894140134d7d8a0dcaa5731fb103dff776c32f053d6c816d8d6cdc530`;
- physically different XISO bytes, including the refreshed digest: 88;
- XDVDFS tree and extents: identical to source;
- source modified: no; and
- xemu/runtime effect: not yet claimed.

The private receipt and experimental XISO are test inputs, not release
payloads. The writer contains addresses, weights, format logic, and hashes; it
does not contain the retail table body, XBE section, or any other stock game
payload.

## Best next experiment

First run the prepared extreme control headlessly: compare stock and patched
Fantasy Draft CPU picks and confirm or falsify the expected K/P position shift.
In the same patched build, run a Franchise rookie draft. If its distribution
does not move, that supplies the runtime negative paired with the static
boundary above.

Then locate the actual Franchise scorer by tracing the Front Office auto-draft
route while watching candidate position (`player +0x35`), overall/evaluation
reads, roster-needs counts, and the final selected-player pointer. A successful
trace should yield a distinct bounded constant table or scoring function. Only
that newly owned target should become the requested Franchise Draft variety
preset.

## What this experiment deliberately did not do

It did not launch xemu, claim a Fantasy Draft or Franchise runtime effect, or
repeat the already-passed archive validators. The copied-XISO transport now
exists, but the result remains a useful negative product decision: the known
table cannot currently ship under the Franchise feature name the user
originally requested.

# Retail rules in Create a Play

EXPERIMENTAL / UNWITNESSED. Rules copy the game's existing per-player
instructions. They do not add a new AI algorithm.

Choose a source book and a formation in Create a Play. On the assignments page,
open **Rules library**. Choose a named preset or search any play in the loaded
book. The table shows all eleven assignments, every declared node, its plain
English description, opcode, flags and exact eight bytes. Both branches of a
condition remain visible. Change the book on the first wizard page to inspect
another of the 37 books. Unlinked plays are inspectable but cannot supply a
bundle because their personnel cannot be established.

Choose **All assignments**, **Offensive line**, or **Active defense**. You can
uncheck individual positions. Transfers, following assignments, synchronized
conditions and defensive exchanges must stay together; automatic scopes include
their linked players, and an incomplete manual selection refuses. The center's
snap names the quarterback but does not force copying his whole assignment.

Press **Apply selected rules**. Exact native position and depth-ordinal codes
must match the target formation. Friendly player references are remapped;
opponent selectors and decision-node indices retain their meaning. Partial
bundles must agree with the target's offense/defense family, run/pass/play-action
class and defensive front/coverage component. The entire combined play passes
the existing validator and synchronization checks before it becomes active.

Copied chains appear in the assignment preview. Use **Reset copied rules** to
return to the original drawing controls. Copied read order is read-only at
finalization so zero values and other retail choices are preserved. Finish by
choosing replacements and staging the ordinary project/pack build. Renaming,
adding a record, changing its menu or moving a chain naturally changes resource
bytes. An unchanged donor chain reuses its existing pointer and costs no nodes.
Changed chains consume the same fixed pool as other authored assignments.

**Combo Inside Zone is defensive.** Its library preset copies reactive coverage
exchanges, including their paired defenders. It is not an offensive-line combo
blocking preset. No play named **Inside Zone Read** or **Slide protection** was
found in the 37 retail books. The library provides genuine Inside Zone, Outside
Zone, Power, Counter, Draw, Screen, Cover 3, Cover 2 Man, fire-zone, pass-set and
native speed-option donors where the selected book contains them. Automatic
protection slides and live blocking-target coordination remain runtime code.
The separate authored Zone read/RPO experiments retain their existing controls
and evidence limits.

The **Info** tab works without retail assets. Search its 47 topics for format
offsets, all 29 opcodes and current codec parameters, the rule vocabulary,
defense/spy/option findings, practice-book and pack workflows, or capacity limits.
Links display local report text inside the read-only panel. The JSON reference
is `docs/mod_editor/play_rules.json`; parameter schemas come directly from
`nfl2k5_play_codec.py` to avoid a second implementation. Historical reports can
contain superseded scope claims, which the current topics identify.

## Reproducing the evidence offline

Run from the repository root. These commands read individual PLAY resources;
they do not read a whole archive or disc into memory and do not write the game.

```sh
python3 -m mod_editor.core.nfl2k5_play_rules reference
python3 -m mod_editor.core.nfl2k5_play_rules catalog --image '/path/to/extracted/game' --book ATL
python3 -m mod_editor.core.nfl2k5_play_rules inspect --image '/path/to/extracted/game' --book ATL --play 28 --formation 23
python3 tools/nfl2k5_play_rules_research.py --image '/path/to/extracted/game' --xbe '/path/to/extracted/game/default.xbe' --corpus '/path/to/research/functions/nfl2k5' > /tmp/play_rules_audit.json
```

The complete audit includes all twelve representative plays, every slot's
descriptor, raw node bytes, decoded operands, branch flags, source hashes and
byte-for-byte whole-resource round-trip receipts. Keep that extracted data
local. Committed presets contain selectors and explanations, never copied node
payloads. The committed evidence manifest contains counts, hashes, source
locations and callback coverage; it can be reviewed without distributing the
underlying retail scripts or decompiler bodies.

The programmatic path is `extract_bundle` -> `apply_bundle` ->
`compile_application`. Bundles are bound to their source book/body hash. Applying
them to a different book or a stale loaded source refuses. Extract again from
that book instead. Normalized compiler requests and packs store the explicit
flags of changed assignments; schema v3 is required for those flags. User-created
project/pack exports can contain copied assignment operands, so they are local
user artifacts, not assets to include in Studio releases.

The exact round-trip case replaces the source play with its own complete rules,
without changing name, flags, geometry or links. The rules wrapper explicitly
allows that no-op after all writer checks. Ordinary writer calls still reject
no-op clones. See [the research report](../../ASTRA_PLAY_RULES_REPORT.md) for
static proof, remaining hypotheses, test results and Noah's gameplay witness list.

# Native match coverage and the SOFTDRINK experiments

**EXPERIMENTAL / UNWITNESSED.** The complete [census and picture table](census.md)
contains **59 defensive play records in 105 formation menus**. All **37 books,
9,251 plays, 3,332 defensive plays and 91,833 pool nodes** were decoded and
validated. The [JSON](census.json) records every source hash, defender, parameter
and formation; the [CSV](census.csv) is suitable for a spreadsheet or community post.

53 plays have reciprocal man/zone exchanges. Six have nonreciprocal partner
slots and are included with warnings. No defensive play in this corpus uses
`0x1A`; ordinary man flags, cushions and zone landmarks are not counted as match
rules. This is a complete census of explicit PLAY continuations, not a claim
to enumerate every receiver decision in the game's general coverage AI.

## What the Ravens play does

![Ravens Zone Double Steal](BAL-p014-f25.png)

BAL **3-4**, **Zone Double Steal**, play 14, formation 25:

| Defender | Initial rule | Change |
| --- | --- | --- |
| CB2, slot 9 | Man on the right-side native target | At the predicted deep boundary, signal FS slot 7 and take a zone at X +15, depth 12 yards. |
| FS, slot 7 | Zone landmark at X +15, depth 15 yards | Consume the signal and change to man coverage. |
| CB, slot 10 | Man on the left-side native target | At the predicted deep boundary, signal SS slot 8 and take a zone at X -15, depth 12 yards. |
| SS, slot 8 | Zone landmark at X -15, depth 15 yards | Consume the signal and change to man coverage. |

The native predicate uses **position plus 0.2 seconds of velocity**, requires
the receiver to be beyond the defender and at least **15 yards downfield**, and
accounts for field direction. It does not read a route called Streak. Another
route reaching that boundary can qualify. The expert's description is therefore
supported by the decoded data and native consumer, with a more general geometric
trigger. His reported observation is supplied evidence; no new play test was
witnessed during this work.

Both **man-to-zone** and **zone-to-man** vocabulary is present. These are the two
sides of one exchange mechanism, not proof of independent complete modern
man-match and zone-match systems.

## Native evidence and anomalous calls

`0x001A2E70` reads man operands 4 (boundary), 5 (friendly partner) and 6
(transition), evaluates `0x0019FA10`, and signals `0x00BE4D00[partner]`.
`0x001A5090` consumes a defender's signal and selects its zone operand 6
continuation. The two initializers `0x001A5BC0` and `0x001A6220` load that
transition into runtime state at `+0xA8`. A terminal man node with operand 7 set
and transition 0 does not arm this exchange: 382 such defensive assignments
were excluded. The corpus has no unclassified defensive chain shapes.

The boundary table at `0x0050A4C8` is the identity table 0 through 15. Mask 7
tests the deep boundary. Masks 13 and 14 test opposite lateral crossings past
the defender and the midpoint to a native reference player; they do not test
depth. They are geometric tests, not a numbered receiver's modern release key.
Normal ball/play-state gates and native target pickup still apply; transitions
can also exit through `0x001A05B0`. These are not unconditional scripted swaps.

The [evidence manifest](evidence.json) pins the retail XBE, complete native
function spans, available Ghidra blocks and decoded constants. Static dataflow
and hashes are proved. No emulator or native execution was used in this session.

**Combo Strong Zone** has a partner mismatch in CHI p27, CIN p3, JAX p31,
KC p27, TEN p28 and WAS p35. The man-to-zone corner in slot 9 signals slot 0,
while the apparent zone-to-man partner is in slot 4 and names slot 9. This is
proved in the stored assignment slots; its live effect is unproved. These calls
remain in the census, with all eleven applicable formation pictures. Their
retail bytes are preserved, and they are not offered as safe reciprocal bundles.

## Install and author

In **Playbooks > Install Playbook Pack**, select
[`softdrink_match_coverage.2k5book`](../../../data/playbooks/softdrink_match_coverage.2k5book),
review the five replacements and choose a book. The existing Build **Playbook
packs** file picker accepts the same file. The source recipe is BAL Nickel;
retargeting resolves native personnel and fronts in all 37 books. OAK,
reference and TEN use 4-3 because too few Nickel destinations remain after
reserving the modern defense pack and every stock exchange. Editor and PRACTICE
append five calls, preserving every drill. All other books replace five records.
Shared formation menus may display those same replaced records; the preview and
compiler enumerate the affected menus.

In **Create a Play > Rules library**, the new named entries **Match: vertical
handoff** and **Match: inside-break exchange** resolve from decoded assignments,
even when a play is renamed. Select complete pairs. The existing source hash,
personnel mapping, explicit node flags, compiler and menu guards remain in use.
The **Info** tab explains the census, parameters, anomalies and modern limitations.

| Authored call | Native combination | Modern limitation | Picture |
| --- | --- | --- | --- |
| SD C3 Rip Match EXP | Right corner/underneath inside-break exchange; three deep destinations and fixed rotation. | No automatic strength or #2 vertical key; full Rip rules unproved. | [Art](sd-match-00.png) |
| SD C3 Liz Match EXP | Left corner/underneath inside-break exchange; opposite fixed rotation. | No automatic strength or #2 vertical key; full Liz rules unproved. | [Art](sd-match-01.png) |
| SD Quarters Match EXP | Two outside vertical handoffs to safeties; outer quarter destinations. | Safeties do not independently read #2. Full quarters-match unproved. | [Art](sd-match-02.png) |
| SD Two Read EXP | Inside-breaking outside targets transfer to safeties; corners take the flats. | No Palms #2-out key. This is an exchange experiment, not complete Palms. | [Art](sd-match-03.png) |
| SD One Robber EXP | Five man assignments, one deep safety, shallow middle zone and four rushers. | Robber pickup uses the existing zone AI. No new recognition policy. | [Art](sd-match-04.png) |

The pack adds **122 nodes / 976 bytes** and uses the existing fixed resource and
name pool. No executable code, runtime memory, settings flag or new allocation
is needed. Full modern Rip/Liz, quarters and Palms rules are **not implemented**
by relabeling these experiments. Their missing keys are deliberate, documented
limits of the native rules established here.

## Reproduce without a display or network

Replace `<retail-tree>` with your read-only extracted game directory. All reads
seek individual resources; no disc image or archive pack is loaded into RAM.

```sh
QT_QPA_PLATFORM=offscreen python3 -m mod_editor.core.nfl2k5_match_coverage census --image '<retail-tree>' --output .scratch/match-gallery --render
python3 -m mod_editor.core.nfl2k5_match_coverage pack --image '<retail-tree>' --team BAL --output .scratch/softdrink_match_coverage.2k5book
python3 tools/nfl2k5_playbook_pack.py check data/playbooks/softdrink_match_coverage.2k5book --image '<retail-tree>' --all-books --retarget --json .scratch/match-all-books.json
python3 -m mod_editor.core.nfl2k5_match_coverage evidence --xbe '<retail-tree>/default.xbe' --corpus '<ghidra-root>' --output .scratch/match-evidence.json
python3 tests/mod_editor/test_nfl2k5_match_coverage.py
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_match_coverage_qt.py
```

PNG images use the Studio's existing FieldScene and play codec, a compatible
front named in each image, and all eleven defenders. Cyan handoff arrows are
explanatory annotations. Both assignment phases are drawn together; this does
not predict an actor trajectory or a gameplay frame. Different linked formations
get separate pictures because personnel and starting positions can differ.

Noah's required witness matrix and exact validation results are in
[`ASTRA_MATCH_COVERAGE_REPORT.md`](../../../ASTRA_MATCH_COVERAGE_REPORT.md).

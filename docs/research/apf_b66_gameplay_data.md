# APF beta 66 gameplay/data findings

Evidence is `reports/apf_b66_gameplay_witness.json`, produced read-only by
`tools/apf_b66_gameplay_witness.py`. PROVED means reparsed bytes or the stated
static instruction/data relationship. No in-game result has been witnessed.

## 26. Ulf the White: formation changes retain personnel

Ulf reported “with the original personnel” after I Jacks -> Singleback Quads.
The previous writer selected the destination primary category, but ORed its bit
into word B, retaining the original category's membership. For Jacks -> Quads,
word B therefore became 0x101 rather than 0x100. The record could still advertise
Jacks even though its formation and primary category said Quads.

PROVED: fifteen retail SPLBs contain 209 populated records and 127 distinct
formation indices. The proposed universal function from formation to one primary
category is **false on retail**. Formation 72 and 78 each have categories 2
(two records) and 5 (one); formation 120 has categories 3 and 6 (two each).
Nineteen primary categories disagree with MASTER's formation default. Thirty-seven
records have multiple word-B bits. It would be incorrect to rewrite every
untouched retail record to one bit or reject every retail alternative.

The implemented rule uses the observed primary-category set for a destination,
ordered by occurrence count and then category number. A requested category in
that set remains valid; otherwise the first is selected. Formations absent from
the CPU census use their MASTER default. Tests regenerate all 163 entries of this
table from the pinned MASTER and fifteen book readers. Every moved/new record
gets a single destination bit in word B. Untouched retail records retain their
original bytes. A deliberate same-formation package-only override remains an
advanced operation, with an experimental warning.

| Workspace/writer | Actual formation operation | Result |
| --- | --- | --- |
| CPU audibles balancing, `apf2k8_audibles` | Reassigns tags within existing records | No formation or personnel move to normalize |
| Fine-tune Plays, `TrailerReplace` | Changes record formation/category, or creates a record | Destination primary category; word B becomes exactly `1 << category`; before/after receipt |
| Design Plays / Formations | Existing MASTER replacements preserve personnel/slot contracts; an appended CPU row clones a donor | New row discards donor secondary bits; reparses against the new MASTER; receipt includes old/new category and word B |
| Assignment-route clone | Changes assignment chains and can clone a book | SPLB record formations stay unchanged; a book clone preserves the body except its label |

Runtime consumers explain why word B matters, without proving the reported
lineup on hardware: the normalizer at `0x84A8C790` rebuilds category membership;
`0x84A8A330` consumes the record mask; `0x84A8B438` searches a book personnel row;
`0x84860020` builds personnel from CATEGORY role bytes. `apf2k8_playcall_patch`
and `personnel_availability` operate on this book supply. Subs is downstream;
changing Subs does not fix a record still advertising its old category.

PROVED replay: each of 209 populated records was independently moved to Quads
(69), or to Jacks (9) when already Quads. 171 moves compiled and independently
reparsed, with a valid destination primary and one destination word-B bit.
Thirty-eight were refused by the existing last-reachable-package guard. Every
populated record in each accepted result has a primary permitted for its
formation; unchanged multi-bit retail records are deliberately retained.
Synthetic tests cover stale UI/recipe categories, forged reintroduction of old
word-B bits, multiple additions and a designer donor with secondary membership.

HYPOTHESIS: this stale membership caused Ulf's particular on-field substitution.
That needs the hardware witness below. The existing guard can refuse a move that
would strand another category; the editor must explain that refusal, not erase
the required book row.

## 27. Aszemple: PS3/.ROS player and uniform import

Aszemple asked to “update the uniforms and players based off roster file”.
PROVED correction to the triage premise: `ps3_roster_convert.convert` already
preserved selector records while converting the source object graph. It did not
copy only players. This change verifies the selector graph explicitly and adds
appearance review/retention and a detailed receipt.

The supplied PS3 USERDATA and Xbox Roster.ROS have the same table positions,
counts and strides:

| Table | Purpose | Offset | Count | Stride |
| --- | --- | ---: | ---: | ---: |
| 4 | Teams | 753784 | 40 | 384 |
| 15 | Palette flags | 1953336 | 266 | 2 |
| 16 | Palette records | 1953868 | 266 | 48 |
| 17 | Selector records | 1966636 | 3724 | 8 |
| 19 | Team appearance configurations | 1997760 | 40 | 152 |

Team `+0xBC` resolves a configuration. Its first 28 self-relative pointers are
two fourteen-selector banks; `+0x70/+0x74` resolve the two palettes. Eleven
selector slots have proved family meanings: 2 glove, 3 helmet, 4 jersey, 5 crest,
6 wordmark, 7 font, 8 number, 9 pants, 10 shoe, 11 shoulder, 12 sock. Slots
0/1/13 and bytes 1..7 of each selector are preserved, without invented semantics.
Byte 0 selects the family asset index. The root's serialized runtime addresses
for these tables are not file offsets; the converter's bounded adjacent-table
layout derives their true spans. Both platforms use `target = field + stored - 1`.

PS3 palette bytes rotate from RGBA to Xbox ARGB through the existing converter.
The stored palette has ten colour entries plus metadata; that is not proof that
all ten or any particular six are bound to a wordmark shader.

The panel's **Also apply team appearance (40 teams)** starts unchecked. Checking
it imports source appearance. Leaving it unchecked requires selecting a raw Xbox
roster as the appearance baseline. That path copies the baseline's selectors,
palettes and palette flags through the destination graph, preserving the PS3
player records, teams, book assignments and converted text. Conflicting aliased
destinations are refused. The normalizer reparses all team selectors and checks
retained palette hashes. The receipt lists all 28 selectors per team, before/after
asset indices, opaque-record change flags and palette hashes. If no Xbox baseline
is supplied, “before” means the input PS3 selector; it is not a comparison against
an imaginary current Xbox roster.

PROVED synthetic tests independently change both banks' eleven known selectors,
retain Xbox appearance while keeping a differing PS3 player jersey number, and
refuse bad pointers/missing baselines. The real fixture proof verifies matching
table layout, all 1,120 selector records and retention. This is raw decrypted PS3
USERDATA or PS3-layout `.ROS`, not an STFS importer. Referenced custom texture
files are not embedded in the roster and require the existing texture import.
Runtime roster loading and uniform appearance remain UNWITNESSED.

## 28. Aszemple: wordmark regions

Aszemple observed “all letters have 3 colors”. PROVED: all 206 hash-pinned
`uniform_textlogo` packages reparse as two storage blocks and exactly one
`textlogo_color` TXTR, 512x128, opaque BC1/DXT1, six mips. The two blocks are
metadata and texture storage, **not two mask layers**. The rectangular wordmark
is selector slot 6; the square crest is slot 5 and has `logo_l0` plus `logo_l1`.
The crest region tools treat RGB as region weights, not literal paint colours.

The current wordmark authoring contract has three RGB channels and no second
mask binding. Six independent region weights cannot be supplied by merely
turning up a count in this contract. BC1 itself can encode many discrete RGB
colours; it is not a file-format theorem that a game could never interpret six
IDs from it. No such alternate decoder/shader binding has been proved here.
Likewise, adding another TXTR to the package would not prove that the game uses
it. No six-region writer is exported.

HYPOTHESIS: selector tail bytes might encode palette choices. Inventory labels
them opaque and this investigation did not establish a wordmark-specific
consumer mapping each RGB channel to one of the six user-visible team colours.
A “choose any three of six” editor would therefore promise unproved semantics.

The implemented bounded alternative is a permutation of the existing three
channels before the existing PNG/BC1/mip pipeline. All six permutations preserve
alpha and pixel channel sums in synthetic tests; an actual prepared PNG is
reopened to prove channel order. Identity is the default. The preview can show
which channel takes which source mask. This does not change palette-slot binding.
Use the paired crest editor for six-region crest art; it does not turn a crest
into a rectangular wordmark. The page hook and explanatory text are in WIRING.md.

## 29 section 4. davidhbui: field overlay opacity

The attachment said “no writer for field material opacity”. PROVED on all four
retail entries: count at scene `+0x30`, material table pointer at `+0x38`, stride
`0x28`, constants pointer at material `+0x20`, signed one-based self-relative
pointers. Crucial refinement: that last pointer addresses a command payload,
not the tint directly. The white tint is at payload `+0x70`, except material 1
at `+0x100`; alpha is the fourth big-endian float. A writer treating the constants
pointer itself as the tint would corrupt commands.

| Outer | Scene bytes | Materials | Table | Five overlays to 0.25: H7A growth | Free allocation bytes afterward |
| --- | ---: | ---: | --- | ---: | ---: |
| 53 | 3514368 | 15 | 0xDF0 | 32 | 868 |
| 252 | 3473408 | 14 | 0xCE0 | 32 | 992 |
| 578 | 3514368 | 15 | 0xDF0 | 32 | 346 |
| 1333 | 3575808 | 16 | 0xDF0 | 32 | 65 |

The reported 24–25-byte growth was not universal: setting exactly these five
materials to 0.25 produced 32 bytes in each entry. The writer measures actual
space and fails closed; it never assumes the reported growth.

A bounded scene-node reparse confirms the draw-record stride `0x30` and the
material-index word at `+0x20`: `A_grass_color` references [1,0], `B_ticks` [2],
`C_chalk_lines` [3,2,3], `D_graphic_overlays` [4,5,6,7,8,9], `E_Outside_grass`
[10,11], `F_detail` [12], identically in all four scenes. Thus material 2 is
shared by ticks and some chalk draws. Overlay material 6 uses a different shader
(`0x01503AA7`) and does not carry the supported tint at the same payload offset;
it is deliberately not exposed. The requested editable overlay set is 4,5,7,8,9.
The field/endzone role assignment within grass draws is the reported semantic
label, not a new captured rendering proof.

The writer pins material/shader identities, payload ordering and command header,
validates finite alpha 0..1 and RGB (1,1,1), then permits only the chosen four-byte
alpha words. It independently reparses the scene, token-preserves H7A, rejects
every overlapping match (`length > distance`), preserves the footer and free
allocation extent, and reparses the full block/file ownership. Tests cover bad
pointers, unknown materials, NaN/out-of-range alpha, unauthorized changes,
nonzero allocation tails, idempotence and composition. The normal Build test
preserves another writer's scene byte while applying alpha in the same IFF.

ADVANCED, off by default. Source/staged scalar preview, Stage, Revert, Undo,
portable scalar-only projects and build receipt exist. WIRING.md connects the
independent widget to job C's Field Art page. Rendering remains UNWITNESSED.

## 31. Urianus Magnus Ursulinus / Aszemple: Deep Threat release glitch

Urianus described “a momentary glitch in DT's animation”. The Discord comparison
identifies left Route God, middle Deep Threat, right Possession, with speed,
agility and route ratings set to zero. The inspected `17_02`, `17_03`, `17_04`
frames are not a controlled trace of normal-stat animation selection. Aszemple's
no-ability baseline was not tested in that comparison; Urianus separately
reported no-ability and Possession alike on PS3.

PROVED on base flat PE SHA-256
`cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`:

- DT is player byte 26 bit 7, getter `0x84744C50`: load word +0x18, extract bit 15.
  Possession is byte 41 bit 2, getter `0x84745490`: load +0x28, extract bit 18.
- The dispatch table is `0x820FEFC8 + id*16`, getter/setter/name/description.
  DT id 17's getter is at `0x820FF0D8`, name “Deep Threat” at `0x8461BB18`;
  Possession id 16's getter is at `0x820FF0C8`, name at `0x8461BA78`.
  Dispatcher `0x84AB4A18` indexes by `id << 4` and calls through the pointer.
- Property wrappers `0x8499BBE8` (DT) and `0x8499BB90` (Possession) call the
  dispatcher and produce 0/1 floating values. These are not animation selectors.
- In function `0x847ECF20` (0x424 bytes), `0x847ED318` loads the DT word,
  `0x847ED31C` masks it, and `0x847ED324` skips to `0x847ED334` if clear.
  With the preceding `r27 != 0` condition and DT set, `0x847ED330` adds 0.05 to f1.
  The constant at `0x82003740` is the single-precision representation of 0.05.
- In function `0x84873580` (0xFFC bytes), DT's word load/mask/branch are
  `0x848742D0/D4/DC`. With the ability set, state `[r27+0x40] == 4`, and signed
  separation greater than f22, `0x84874324` adds 0.05 to f31. The adjacent
  Possession block begins `0x84874264`, checks its own bit and state, and uses a
  different separation threshold/direction before the 0.05 add at `0x848742CC`.
  These observed writes affect evaluation scores; they do not select an
  animation clip at the inspected branch sites.

TU flat PE SHA-256
`65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457`
has unique normalized instruction-shape matches at functions `0x847EDBC0` and
`0x84874290`, with DT loads `0x847EDFB8` and `0x84874FE0`. Relocated referenced
code/data equivalence is not implied by normalized matching.

HYPOTHESIS / OPEN: the causal snap/release animation site has not been isolated,
and PS3 behavior cannot be proved from the Xbox executable. These are exact
ability consumers, not a claimed exact glitch site. Disabling the getter or
removing both scoring bonuses would remove intended DT effects without proving
a release repair. No optional patch or Export patch hook was created. The next
useful evidence is a controlled hardware capture with normal ratings and the
same receiver/route/alignment, followed by a trace of the animation request
consuming the DT property value. An animation-only, title-update-compatible
patch remains contingent on that evidence.

# APF-3: exclusion limits, O-ManBlock transport and the final lineup

## Status and scope

**Independent per-situation exclusion is not implemented.** The proposed
data-only levers cannot encode it in the proved native format. Membership is
per personnel category, and the ordinary offensive distance curve has a
positive tail. All eight encodable rating values have positive weight. Changing
those fields cannot make one of the 23 labels an independent stored list.

**PROVED** below means executed native instructions or exact byte comparisons.
The match state and player depth chart are explicit harness inputs. Every
in-game result, and the cause of any particular observed match, is
**UNWITNESSED**. No executable patch is installed or emitted by this work.

## 1. What the data can exclude

SPLB record `0x70 + n*0xB0` stores formation/primary/rating word A at `+0xA8`
and category-membership word B at `+0xAC`. The three ratings occupy three bits
each at shifts 14, 11 and 8, so the complete encoded domain is 0 through 7.

| Proposed edit | Native result | Independent situation exclusion? |
| --- | --- | --- |
| Change ratings | Positive category/formation weights, including raw 0 and 7 | No |
| Clear one membership bit | Removes that category/formation pair for every query | No |
| Clear word B | Removes the formation from ordinary membership for every query | No |
| Change primary and membership to another offensive category | Changes requested personnel; the formation remains an ordinary candidate across queries | No |
| Clear derived advertised categories at `+0x7E04` | Native normalization rebuilds the cache | No |

The tests execute `84869058` on BASE and TU 1.1 for all eight constant-rating
triples across all 23 queries, plus all 512 mixed triples in both distance
interpolation arms. They compare every returned weight with the model. The
interpolator combines positive endpoints; there is no hidden negative or zero
rating code to select. All 4,832 native/model comparisons pass; the minimum
observed weight is `0.10000000149011612`.

The category gate at `8486AEB0` reads MASTER category rows and a positive
offensive distance curve (`820C88A8`). A far-away category is downweighted,
not excluded. `848693F8` applies shared membership and primary preference;
neither field contains a situation identifier. The native tests move an
isolated formation 14 among categories 3, 6 and 7, normalize it, then execute
all 23 ordinary category/formation queries on both images. They also capture
the full call tuples. The fourth-down and two-point labels are ordinary
scrimmage proxies: the full caller can take its actual kick branch instead.
Those branches are retained in the evidence, not replaced by the harness.

For a non-singleton counterexample, clearing formation 14's word B leaves
Queens formations 2 and 24 in the native category-6 formation buffer in every
query, while formation 14 disappears from every one. It is a genuine
membership exclusion with a shared scope.

Some labels are aliases even before considering shared memberships: Openers,
1st and 10 and Sudden change supply identical inputs. After negative play and
2nd and 11+ also supply identical inputs. No deterministic data edit can
distinguish identical selector inputs and unchanged RNG/history state.

**HYPOTHESIS / required new design:** independently editable situation lists
need a new native filter and persistent per-book exclusion storage. The filter
must receive a defined live situation key, filter categories as well as
formations, and define an empty-draw fallback. The 23 overlapping query labels
also need explicit matching/precedence rules and live inputs for their
currently unmodeled event/clock semantics. Reassigning a membership bit to a
label, or displaying a shared removal as a local one, does not provide that
contract. This work adds neither a speculative format nor such a control.

## 2. Straight for the three Queens formations

The named reproduction starts with O-ManBlock, adds Gun: Straight (formation
133, category 7) using O-Shotgun's 25 stored play IDs, then removes the three
Queens formations: I Spread (2), Strong I Spread (14), Weak I Spread (24).

| Stage | Token-preserving IFF bytes | Final IFF bytes | Allocation |
| --- | ---: | ---: | ---: |
| Add Straight | 1,639 | 1,639 | 2,048 |
| Remove 2 | 2,027 | 2,027 | 2,048 |
| Remove 14 | 2,054 | 1,526 | 2,048 |
| Remove 24 | 2,019 | 2,019 | 2,048 |

APF-2's existing portable refit handles the intermediate overflow. The final
allocation SHA-256 is
`5b8d650fbb16d5448d4bad0062977373932ff7aa6027ffc7bdd50dffe7c19efc`.
It decodes exactly to body SHA-256
`8feb01162777475a7c537ef12375b942615ea0e56e8eb1802d9a3e8fca407742`.

Fine-tune permits a manually chosen list of 1–84 plays. A second regression
uses authored play IDs 0–83 with the same formation edit. Its final old stream
requires 2,275 bytes; the portable refit needs 1,634, leaving 414 bytes.
Both regressions disable the optional native compressor and verify every
decoded byte, surviving record, IFF file descriptor, footer and zero-filled
allocation tail. The original archive remains unchanged.

**Limit:** the screenshot records 2,417 bytes but does not disclose the selected
play IDs or project recipe. That exact historical payload is not reconstructed
by these measurements. The named formation edit and an overflowing 84-play
variant are reproduced; neither needs container growth with APF-2's refit.

## 3. A later producer can select zero TE-depth players

The new witness completes the ordinary call with the output address pointing
at the real current-call structure, `TEAM+4`. It executes through the function
return, including `8486D0CC..D0D8`, and checks the formation and play stores at
`TEAM+0x70`, `+0x68` and `+0x6C` against that tuple.

The next bounded call starts at the native lineup phase `84859820`. That
routine reads the same manager's current call and reaches:

| Step | BASE | TU 1.1 |
| --- | --- | --- |
| Current-call lineup phase | `84859820` | `8485A4C0` |
| Category/formation wrapper | `848608B8` | `84861558` |
| Eleven-player builder | `84860020` | `84860CC0` |
| Substitution and depth request builder | `847B2DA0` | `847B3878` |
| Player provider, including alternative positions | `847B29E8` | `847B34C0` |
| Slot assignment | `8485E768` | `8485F408` |

The witness stops at `84859958` / `8485A5F8`, after the full offensive wrapper
and builder return, before processing the other team. It bridges two native
phase calls with unchanged current-call bytes; it does not execute the whole
match scheduler. The explicit-output arm avoids the default-output arm's
separate play-notification routine `8488DAB0`.

For third-and-8 at midfield, the edited book returns category 7 and formation
133. MASTER requests one TE at slot 6. With one TE-depth entry, native code
selects that player. With the TE depth list empty, the same call tuple still
requests a TE, but the native provider tries position 3 (TE), then position 2
(FB) and supplies the FB-depth player. The final eleven player pointers contain
no TE-depth player. The selector, substitution routines, depth/provider loops,
eligibility checks and assignment loop all execute natively.

Twelve final-lineup cases cover BASE/TU, TE present/absent and RNG fractions
0.25/0.5/0.75. At 0.5 the tuple is `(7, 133, 122)`. Four more cases extend the
original APF-2 edit (formation 14 reassigned to category 7, formations 2 and 24
removed). Its tuple `(7, 14, 114)` produces the same TE-to-FB fallback on both
images. Each lineup phase executes roughly 74,000–76,000 native instructions.
The native role-to-depth tables at `820B3D30` / `820B3D40` map TE role 8 to
depth position 3 and FB role 11 to depth position 2; the witness checks those
native table entries before executing the provider.

The selected call's role byte at output `+0x34`, and the primary-package role
byte at `+0x35`, both still say TE. Actual player selection is at `+0x44`.
Therefore a one-TE category or one TE role byte does not prove a TE player was
selected. CPU Play Calling now labels its count **Requested TEs** and explains
the empty-depth-list fallback.

**Fixture limits:** the depth chart and healthy player objects are synthetic,
with 32 players when a TE exists and 31 when it does not. Only the two equipment
refresh leaves are replaced (`847C1728`, `847C16D0`; TU `847C2348`, `847C22F0`).
They supply no category, formation, role or player-selection result. RNG and
kicker range remain the existing explicit selector inputs. Saved USER overlays,
real roster availability, injuries/fatigue, later match phases and displayed
players are not reconstructed. The fallback is **PROVED**; attribution of an
observed match to this fallback remains **HYPOTHESIS / UNWITNESSED**.

## Reproduce

Use the pinned owned BASE XEX, TU 1.1 package and APF archive locations supported
by the existing native suite. Missing inputs cause precise optional skips;
the APF-3 delivery records whether those inputs were actually available.

```sh
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_playcall_research_native.py
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_b71_situations.py
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_playcalling_editor_qt.py
```

The instrument is `tools/apf_b71_situation_probe.py`. It writes no game data or
images. Input identities remain pinned by the native suite. Detailed command
exits, timings and test output are in the APF-3 delivery report and ledger.

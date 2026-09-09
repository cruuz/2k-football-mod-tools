# APF 2K8 independent books — Astra, 2026-09-09

Implemented and verified offline: name-based offensive book cloning, a per-team
Book Identity receipt, three authored scheme recipes, and a standalone Qt
review/build panel. A local combined game contains **12 independently addressable
CPU offensive resources**: the seven originals plus five clones. Five teams are
assigned to those clones without sharing them. This is **not an in-game witness**.

The four supposedly unnamed SPLBs are USER-d, global-d, USER-o, and global-o.
The supplied ROS files serialize **eight combined O/D user books**, separate from
the two UA/UB working buffers. The WR depth flip and CPU situational personnel
control remain UNKNOWN. No executable patch was necessary for the data experiment.

Protected Studio/registry/release files were left for the integrating owner, as
the supplied context requires. [WIRING.md](WIRING.md#astra-book-identity-2026-09-09)
contains exact integration code. The CLI is usable now; the new panel is
implemented and tested but is not yet on the protected navigation surface.
The capability rows are a validated merge fragment, not an installed registry.
No push, emulator, display session, audio, or network fetch was performed.

## Evidence standard and inputs

- **A_PROVEN** means byte-checked serialization, instructions, allocation,
  independent reparse, or full comparison under the stated inputs. It does not
  mean observed CPU behavior.
- **B_INFERENCE** identifies a connection supported by the static endpoints
  whose complete intervening dispatch or runtime conditions were not established.
- **UNKNOWN / UNWITNESSED** identifies an actual remaining boundary.

Read the supplied brief, context, both memory notes, the August 17 mechanism and
update documents, the August 23 follow-up, and the complete September 5 transcript.
Earlier notes disagree about personnel causality; the August 29 negative witness
in the current context takes precedence over the optimistic August 17 update.
Aszemple, September 5 at 10:42, asks for “CPU AI and preset NFL scheme playbooks.”
Urianus, September 5 at 21:50, reports the same-formation audible limitation and
mostly-run presets. Those statements motivate the recipes; they are not proof
that these changes alter audible frequency or permit cross-formation audibles.
The earlier “fully separate” clone request is quoted in the brief without an
exact DM day; this report does not invent a more precise attribution.

Static executable input: the **flat** PE at
`/home/noah/.codex-tmp/franchise-2026-08-28/apf.pe`, 54,001,664 bytes,
SHA-256 `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`.
Every VA below maps to `VA - 0x82000000`; PE section raw offsets were not used.
The copied helper was used only in temporary research files. The reproducible
[probe](tools/apf_book_resolution_probe.py) does not depend on that private helper.
It pins the whole PE and reads 181 selected instruction words, nine UTF-16
strings, and the CRC table. [resolution.json](reports/apf_book_unlock/resolution.json)
contains every selected address, instruction word, disassembly, all 69 label
tuples, all fifteen resource identities, and both save censuses. Its instruction
words total 724 bytes; no game body or compressed payload is distributed.

Retail inputs were the extracted Xbox 360 game under
`/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/`
and `/home/noah/Downloads/apfe/{Roster.ROS,Roster2.ROS}`. They were read only.
The local spreadsheet has play lists, but its readable workbook XML does not
contain the quoted 0x26D030/0x210880 anchors. Those anchors are treated as the
supplied research note, not independently attributed to cells in that workbook.

## Job 1: label → resource → live book

### Serialized labels and relocation — A_PROVEN

Disc ROST is filename ID `0xBCEFFD46`, stock outer 1126, one `roster/ROST`
resource, decoded length 2,294,304. Root[4] supplies 40 teams at `0xB8074`,
stride `0x180`. Team `+0xE0/+0xE4` selects offense/defense labels. Root[11]
supplies 69 labels at `0x1D31D8`, stride 12. Each record is name pointer,
type pointer, and side word. Pointers are signed field-relative displacements
with a one-based encoding: `target = field + signed_word - 1`.
The side words in this input are `00000000` and `01000000`; counts are 36 O/33 D.
Raw ROS offsets for these same tables are four bytes later.

| Address | Word | Established operation |
|---|---|---|
| `84750F84` | `4bffe9cd` | ROST load calls `8474F950` |
| `8474F96C` | `4bffc71d` | Calls root relocator `8474C088` |
| `8474C438` | `3b7f005c` | Address of root[11] pointer field |
| `8474C45C` | `817f0058` | Reads root[11] count |
| `8474C478` | `4bff1039` | Calls label relocator `8473D4B0` |
| `8474C484` | `3bbd000c` | Advances exactly 12 bytes |
| `8473D4B0` | `81630000` | Reads label name pointer |
| `8473D4C8`, `D4CC` | `7d6b1a14`, `396bffff` | Adds field address, subtracts one |
| `8473D4D4`, `D4D8` | `39630004`, `814b0000` | Reads type pointer at +4 |
| `8473D4EC`, `D4F0` | `7d4a5a14`, `394affff` | Relocates type using its own field |
| `8473D554` | `3940000c` | Serializer declares 12-byte record |
| `8473D564`, `D568` | `806b0004`, `83cb0000` | Sizes the type and name strings |
| `8474C210`, `C21C` | `48006bf9`, `3bbd0180` | Team relocation, stride 384 |
| `84752F1C`, `2F40` | `396300e0`, `396300e4` | Relocates team book fields |

`84747C78` returns root[11]'s count; `84747C90` bounds-checks the label
index and computes `labels + index*12`. `8473D500` performs inverse relocation.
`8473D590` copies all 12 record bytes and serializes both strings. The resolver
below chooses the O/D pointer from its caller's boolean; it does not use the
serialized side word to hash a book. The complete menu-side filtering consumer
of that side word was not established, and is not needed by this writer: side
bytes and the name string stay unchanged.

### Type string and request — A_PROVEN endpoints; dispatch boundary stated

`849D6208(r3 = match side, r4 = offense)` selects the current team through
`84682730` or `84682798`. The caller-side convention is called home/away below;
the exact on-screen presentation for every mode is UNWITNESSED.

`849D6238 / 625C: 83bf00e0` reads the team's offensive label.
`849D6268: 83bf00e4` reads its defensive label. A non-null override from
`849FD608/618/628/638` takes precedence. At `849D6490` the override's type is
read; at `849D64B4: 817d0004` the default team's label type is read.
`849D64B8: 91610050` places that string in the formatter arguments;
`849D64C8: 38800040` supplies a 64-unit output bound;
`849D64E4: 4818f61d` calls `84B65B00` with template **`{0}-spb.iff`** at
`845F1764`. The output is at `851D13D8`.

For example, `O-WestCoast` becomes `O-WestCoast-spb.iff`. There is no table
of fifteen SPLB outer ordinals or header-name comparison in this function.
The display name at label +0 is distinct from the type at +4.

Home O wrapper `849D81D0` calls the resolver at `849D820C`, checks that its
result is nonempty, constructs request group `0x279F5352`, and calls
`8468DA70` at `849D8268: 4bcb5809` with filename in r6.
Other wrappers request home D (`0x047DD950`, call `849D8360`), away O
(`0xF016FD53`, `849D8458`), and away D (`0xA15F1953`). These are request-group
identities, not archive filename IDs.

`8468DB14 → 8468D7D0 → 84B698B8` constructs a generic request.
`8468D824: 7f68db78` forwards the filename in r8; `84B698DC` saves it;
`84B69908 / 69924` pass it to `84B68D48`, which copies UTF-16 into request
**+0x50**, bounded to 0x100 units. Request **+0x4C is the group value**, not
the filename pointer. The worker passes +0x50 as r5 at `84B69504` and invokes
the resource object's vtable +8 at `84B69548: 4e800421`.

**B_INFERENCE:** that asynchronous resource dispatch reaches the archive-open
implementation below. The filename is proved through the enqueue/worker edge,
and the archive's lookup/geometry are independently proved. This pass did not
resolve every concrete vtable object and IFF heap-allocation call between them.
Do not describe that omitted dispatch as a fully reconstructed call graph.

### Archive lookup and allocation — A_PROVEN

Archive open `84B919E8` calls `84B91300` at `84B91A50: 4bfff8b1`.
With an empty archive path prefix, lookup calls `84B21020` at
`84B9138C: 4bf8fc95`. With a prefix it joins the path and calls the byte-string
variant `84B210A0` at `84B91380`. Both fold ASCII a–z to uppercase.
`84B21054: 396bffe0` subtracts 0x20 from lowercase characters.
The 256-word table at `844C4DB8` exactly matches reflected CRC32 polynomial
`0xEDB88320`; initial/final XOR are all ones. For these ASCII filenames this is
`zlib.crc32(filename.encode('ascii').upper())`. It is not the CRC of UTF-16 bytes.

`84B91390: 817c0010` reads header entry count; `91398: 390bffff` sets the
upper binary-search index to count−1; `913A4: 80fc0014` reads the directory
pointer. `913BC / 913C0` multiply the midpoint by 12; `913C4: 7d4a382e`
reads its hash; `913C8: 7f035040` compares **unsigned**. The returned row
supplies block-scaled resource offset and size to the archive file object.

The archive constructor checks magic `AA00B3BF` at `84B91640..64C`, reads
entry count at `91654` and pack count at `9165C`, allocates space derived
from **12 × entry count** plus pack metadata (`91660/668/67C`), and calls
its allocator callback at `916B4: 4e800421`. The allocation is stored at
object +0x220 (`916BC: 907f0220`). `91708` installs the entry-table pointer;
`91750..768` reads exactly count×12 directory bytes. No fixed 1543/15 bound
is embedded in these operations. The specific heap implementation behind
the callback remains UNKNOWN; it is not needed to reserve pack bytes offline.

The separate request pool at `8468D5F8` reads a configured count at manager
`+0x80300` (`8468D618: 7d23582e`), searches request objects of stride
`0x288` (`D644: 396b0288`), and returns a free object. This is a generic
request pool, not fifteen preallocated team playbooks. Its configured live
capacity was not recovered. Selecting a different filename does not itself
request twelve simultaneous books.

### All fifteen actual resources — A_PROVEN

Every row below was found by the CRC of `<header-name>-spb.iff` and reparsed
as one `spb/SPLB` IFF. Each decoded body is 32,288 bytes, each allocation 2048.
All fifteen source H7A streams have zero length-greater-than-distance matches.

| Stock outer | Header name | Filename CRC32 | Populated records | Memberships |
|---:|---|---|---:|---:|
| 130 | O-ManBlock | 1569CB3C | 23 | 507 |
| 134 | X-43Cover2 | 161999DE | 4 | 116 |
| 259 | O-TwoBack | 2A9D1104 | 25 | 599 |
| 293 | USER-d | 2F551CF1 | 6 | 180 |
| 369 | O-SinglebackAce | 3D357833 | 17 | 764 |
| 618 | X-34Base | 663CC76E | 4 | 185 |
| 656 | global-d | 6C4EBF6F | 5 | 24 |
| 767 | O-Singleback3WR | 7D9F9D2B | 27 | 1674 |
| 891 | O-WestCoast | 95B17E5C | 22 | 1159 |
| 943 | O-ZoneBlock | 9CC47B00 | 17 | 505 |
| 957 | X-43Blitz | A0062F65 | 5 | 191 |
| 1037 | USER-o | AD00822C | 20 | 258 |
| 1405 | X-34ZoneBlitz | E949846D | 4 | 218 |
| 1411 | O-Shotgun | EA0DA03B | 23 | 809 |
| 1439 | global-o | EE1B21B2 | 7 | 23 |

This is 7 CPU O + 4 CPU D + 2 USER templates + 2 global supplements,
209 populated records total. `STOCK_BOOKS` now names all fifteen correctly.

`global-o-spb.iff` at `845F20C4` is requested at `849D80B0` under group
`3D6371C8`; `global-d-spb.iff` at `845F20E8` is requested at `849D8160`
under `AAB1A840`. `849D4198`/`41F0` retrieve these, then `84A8D740` is
called to merge them into both match books (`41B4`, `41C8`, `420C`, `4220`).
Thus these resources have actual load/merge consumers; “unused/unnamed” was wrong.

At match binding, `849D4080` retrieves home offense's inner `spb` ID
`25757699`, then `849D4090` calls `849FD6C8` to store the pointer at
`84F3F7D8+0x2C`. Home D is retrieved at `40CC` and merged at `40E8`.
Away O is bound at `4118` through `849FD6D8` to +0x30, with away D merged
at `4170`. MASTER is installed at book +0x7E0C. These are two loaded
**combined match books**, with shared global additions. Offline O-resource
independence does not imply isolation from those additions or mode overrides.

### USER templates, eight saved books, and two working buffers

**A_PROVEN:** initializer `84AE8948` loads `user-o-spb.iff` from `84626010`
and `user-d-spb.iff` from `846260A4` (requests `84AE89E8`, `84AE8A28`).
It retrieves their `spb` bodies at `84AE8AA0` and `84AE8AD0`, copies the O
body to a temporary book, and merges D via `84AE8B0C: 4bfa4c35 → 84A8D740`.
At `84AE8B14: 617ff100` the loop bound is `0x3F100`; `8B58: 3b397e20`
advances by `0x7E20`, stopping at `8B5C/8B60`. Since
`0x3F100 = 8 × 0x7E20`, it initializes eight complete combined slots at
`0x8523F6F0+0x10`. This proves a real eight-slot serialized bank, not eight
offensive labels pointing to one template.

| Address | Word | Save linkage |
|---|---|---|
| `84AE8938`, `893C` | `3c600003`, `6063f100` | Serialized bank size 0x3F100 |
| `84750FD4`, `0FD8` | `917e0000`, `3bde0004` | Writes roster extent then advances past its prefix |
| `84750FE8` | `483f4d01` | Copies serialized roster extent |
| `84750FFC`, `1000` | `7c6bf214`, `48397bf9` | Tail address → bank serializer `84AE8BF8` |
| `84AE8C1C`, `8C24`, `8C28` | `60a5f100`, `388b0010`, `4805d0c1` | Copies bank+0x10, length 0x3F100, to save |
| `84751028`, `102C` | `83e30000`, `3ba30004` | Reads extent and roster base on load |
| `847510A0`, `10A4` | `7c7fea14`, `48397b9d` | Passes extent+base to `84AE8C40` |
| `84AE8C68`, `8C70`, `8C74` | `60a5f100`, `387f0010`, `4805d075` | Restores 0x3F100 bytes into the bank |
| `84AE8F9C`, `8FA0` | `817f00d0`, `2f0b0002` | Team type 2 takes saved-book path |
| `84AE8FAC`, `8FBC`, `8FC4` | `4bc62add`, `1d437e20`, `396b0010` | Team ordinal → bank slot at +0x10+ordinal×0x7E20 |

`8474BA88` computes the team's ordinal among matching team types.
The slot getter does not add a ninth-slot allocation check or storage extension.
Extending it would overlap other state and is outside this implementation.

Both ROS files are 2,715,908 bytes (`0x297104`). Their first u32 is
`0x258000`, so the bank starts at `0x258004` and consumes the file tail exactly.
Slot bases are `258004, 25FE24, 267C44, 26FA64, 277884, 27F6A4, 2874C4,
28F2E4`. All eight in each supplied save are identical default combined books:
26 populated records / 438 memberships. Records 0..19 exactly equal USER-o's
20 records, records 20..25 exactly equal USER-d's six records, and mask
`0x3DEF = 0x1EF | 0x3C00`. Slot SHA-256 is
`852813e81b1e2de5044903aa8fa05260f99eea7735f6bdb84a7683e651db22a4`.
These are defaults, not evidence of eight distinct user-authored contents.

The quoted `0x26D030` is **inside saved slot 2, record 121, entry-area byte 76**
for these files, not the bank start. The `0x210880..0x210DC0` anchors are inside
the serialized roster extent, before the bank. Their proposed sixteen-entry
meaning remains UNKNOWN; they cannot establish sixteen SPLB books in these saves.

Separately, `849FCF60` computes `851D9660 + index*0x7E20`
(`3d60851e, 1d437e20, 396b9660, 7c6a5a14`). Resolver special cases compare
override types **UA/UB**, not USER-o/USER-d, and pass index 0/1 at
`849D6294`/`639C`. They test buffer +0x7E10, bind an active buffer directly,
and return an empty filename to suppress the disc request. Other paths
populate working data through the user editor, including `%s-spb.iff` at
`84618F30` and request `84A8F5BC`.
`84A8F278`/`84A8F2D0` copy one 0x7E20 working book out/in; no direct callers
were found, and their inbound pointer words were unwind-table entries.
These leaf copies do not prove save linkage; the `84751000/10A4` chain above does.
How every eight-slot selection reaches every UA/UB/mode override remains
**UNKNOWN**. Eight serialized combined slots and two resolver working indices
are proved; live menu availability and CPU use remain **UNWITNESSED**.

## Job 2: decision, writer, identity, and proof

Chosen path: reuse an unused offensive label's existing name as a new type.
For label 20, retain the name `Panthers`, redirect its +4 type pointer to the
same existing UTF-16 string as +0, append `Panthers-spb.iff`, and assign a team
to that label. This needs neither a guessed string pool nor a code cave.
It preserves all 69 labels, both side values, every string, and all table counts.

The allocator principles from `nfl2k5_xbe_space.py` were reused: explicit
ownership, fixed old locations, reserved metadata space, deterministic requests,
and verified bounds. Its XBE section/cave format was not used for APF archives.
The four APF packs are contiguous; all payload allocations cover the virtual
range from `0x5000` through 3,873,511,424 with no holes/overlaps. The only
leading slack is between directory end `0x48AC` and first payload `0x5000`.
The writer uses checked-zero slack only for new 12-byte directory rows and
**appends new 2048-byte allocations to 1B**. It does not call zeros inside an
existing allocation “free space.”

The seven original CPU O resources are retained and remain assigned. The
example adds five, rather than merely adding one to seven:

| APF team slot/name | Reused label ID/name | Donor | New hash | New outer |
|---|---|---|---|---:|
| 5 Cyclones | 5 Browns | O-ZoneBlock | 98AD8730 | 916 |
| 7 Firebirds | 7 Cardinals | O-Singleback3WR | 5A33C3E7 | 545 |
| 10 Iron Men | 10 Colts | O-Shotgun | 327FA6D8 | 314 |
| 11 Knights | 11 Cowboys | O-SinglebackAce | A07E91AD | 964 |
| 20 Sharks | 20 Panthers | O-WestCoast | 2B746640 | 268 |

NFL label names are not the stock APF team display names. The Panthers label's
new type no longer shares Bears' O-WestCoast resource. At stock startup Bears
is used by team slots 1 and 20; the example moves only slot 20.
In the combined build Browns/Colts copy the already-applied Wide Zone and
Spread-to-Run donors, respectively. Their resource bodies remain name-only
clones of those donors. The other clones copy unchanged donors.

Proof in [clone-build.json](reports/apf_book_unlock/clone-build.json):

- Directory 1543 → 1548 entries; 60 checked-zero metadata bytes consumed;
  10,240 bytes appended to 1B. All original resource offsets and sizes stay fixed.
- Disc ROST changes exactly **13 bytes within ten authorized four-byte pointer
  fields**. Decoded extent and all string bytes are unchanged. Rebuilt ROST
  occupies 435,437/436,224 bytes, leaving 787.
- Each decoded clone is byte-identical to its donor except header name allocation
  `0x30..0x68`; all 176 record structures and both tail regions match exactly.
  IFF transport naturally changes with compressed name bytes and lengths.
- Each rebuilt IFF is independently reparsed and decoded. H7A overlap count is
  zero, and each clone fits the donor's 2048-byte allocation.
- Full copied-archive comparison accounts for every original byte outside the
  authorized directory/ROST spans, exact output bytes inside them, and all new
  clones. Recompiling the same requests adds zero resources and changes no binding.
- The combined retail→presets→clones comparison checks **3,873,048,576 untouched
  original pack bytes**. All 38,408,192 executable bytes compare equal; XEX SHA-256
  is `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f`.
  See [combined-comparison.json](reports/apf_book_unlock/combined-comparison.json).

The new core modules locate resources by filename ID. Sorting inserted directory
rows changes old **outer ordinals**; existing Studio editors frequently use those
ordinals and retail fingerprints. Therefore normal project edits and presets
come first, clone finalization last. Do not reopen the expanded folder through
the existing fixed-ordinal edit paths. This release slice provides a new-folder
finalizer, not a rewrite of every Studio selector or project format.

Book Identity lists all 80 team/side assignments, label ID/name, type, resolved
resource, and every other team sharing that type. Compile, preset, and clone
receipts include it. Raw-save assignment receipts now include it with an explicit
**stock reference only / archive not inspected** status. Unknown types are not
invented as resolved resources. Normal Studio build receipts need the exact
protected-file insertion in WIRING.md to inspect the final composed ROST.
The label-type count of 13 offensive in the combined receipt includes USER-o;
the independent CPU O resource count is twelve.

Malformed schemas, bool-as-index values, duplicate JSON keys/targets, shared
clone labels, wrong-side labels, unsupported names, hash collisions, occupied
directory slack, allocation overflow, overlapping H7A matches, and altered output
bytes are refused. Existing output paths/symlinks and source-overlapping paths
are refused. A failed writer removes only the new destination it created.

### Formation versus book

A label selects a type/resource. A stored book record selects a MASTER formation
and carries a separate personnel category/membership mask. The formation's
slot-role permutation and alignment geometry are separate again. The known row
fallback and chosen-play record paths can produce different personnel outcomes.
Panel text and the getting-started explanation now reflect that distinction.
The August 29 both-edits witness still had 3/27 zero-TE formations; no fix for
the residual producer is claimed. The bounded pass reused the August 23 WR
investigation and checked whether the newly traced binding supplied a depth-order
lever; it did not. **O-Shotgun WR1↔WR4 and WR2↔WR3 remain UNKNOWN.**

## Job 3: authored scheme recipes

Recipes are authored selections of existing MASTER play IDs/names, formation
IDs/names, desired retained memberships, and desired tag 0..3 destinations.
They do not alter MASTER, add formations/plays, write opaque X bits, or change
record trailers/package masks. Tags 0..2 have the established audible writer;
slot 3 is retained and reassigned structurally, without claiming that it is a
fourth runtime-written audible. Each dependent tag swap is passed separately
through the existing SPLB writer, then removals are compiled after retained
tag holders are established. This avoids the batch writer's source-ID sorting
changing the meaning of dependent swaps. Every step reparses and final validation
independently checks desired membership, order, tags, trailers, and all other bytes.

| Recipe | Target | Changed records | Selected distinct plays | Memberships before→after in changed records | Changed bytes | Active IFF / allocation |
|---|---|---:|---:|---:|---:|---:|
| [Wide Zone](data/apf2k8/scheme_presets/wide-zone.json) | O-ZoneBlock | 13 | 30 | 471→263 | 820 | 1035/2048 |
| [Spread-to-Run](data/apf2k8/scheme_presets/spread-to-run.json) | O-Shotgun | 21 | 37 | 784→302 | 1391 | 1432/2048 |
| [Pro Power](data/apf2k8/scheme_presets/pro-power.json) | O-ManBlock | 20 | 26 | 451→284 | 783 | 1750/2048 |

Wide Zone keeps outside-zone/cutback/bounce runs, existing PA/rollouts, quick
outlets and screens in records 0..12, preserving four fallback records.
Spread-to-Run selects the existing Gun run/quick-pass/PA/screen menu in records
0..20. It leaves I Jokers and I Jacks at 21/22 intact: O-Shotgun's 23 populated
records are **not all Gun**. Empty-Gun records retain pass options; there is no
claim of a new post-snap run/pass decision, true RPO, or new blocking behavior.
Pro Power uses I/Strong I/Weak I power, iso, and existing deep PA, with quick
outlets where a short-yardage record lacks deep PA. Gun fallback records 18..20
stay intact. No record is emptied, including Flip counterparts.

[preset-build.json](reports/apf_book_unlock/preset-build.json) lists every one
of the **54 changed records**, its formation, old/new counts, every removed play
ID, and all before/after tags. It also includes source/output hashes, transport
fit and zero-overlap proof, and one complete team identity table. Membership
occurrences are not distinct plays or predicted call frequencies. Preset source
name/ID checks refuse a different MASTER catalog or a missing selected play.
All three repeat applications produce byte-identical bodies and zero further
record changes. CPU scheme resemblance/frequencies are **UNWITNESSED**.

## Reproduction and local build

Commands run from this worktree. Shell variables below are task-specific.

```bash
APF_INDEX='/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A'
APF_PE='/home/noah/.codex-tmp/franchise-2026-08-28/apf.pe'
APF_WORK=/tmp/astra-book-c_5_qyqf

python3 tools/apf_book_resolution_probe.py --pe "$APF_PE" --source "$APF_INDEX" \
  --save /home/noah/Downloads/apfe/Roster.ROS \
  --save /home/noah/Downloads/apfe/Roster2.ROS \
  --receipt "$APF_WORK/resolution-evidence.json"
# Pinned 181 instructions; matched 15 book filename hashes; inspected 2 saves. Runtime UNWITNESSED.

python3 tools/apf_book_unlock.py preset --source "$APF_INDEX" \
  --preset wide-zone --preset spread-to-run --preset pro-power \
  --output "$APF_WORK/presets-game" --receipt "$APF_WORK/presets-receipt.json"
python3 tools/apf_book_unlock.py clone --source "$APF_WORK/presets-game/0A" \
  --requests data/apf2k8/book_clone_example.json \
  --output "$APF_WORK/12-offense-game" --receipt "$APF_WORK/clone-receipt.json"
```

Both builders printed Copying 0A/0B/1A/1B, then their verification stage, and
exited 0. Their receipts contain the counts above. Use fresh destinations to
repeat these commands; existing paths are deliberately refused. Omit `--output`
to compile/review only. `identity --source <0A>` prints the identity table alone.
All game bytes remain in the temporary build directories, outside the repository.
The local combined launch file is
`/tmp/astra-book-c_5_qyqf/12-offense-game/default.xex`; it has not been launched.
Complete JSON receipts are beside the local outputs; committed receipts omit
duplicate tables/full ordinal maps and record the complete receipts' hashes.

The direct comparison used `compare_untouched_packs(retail, combined, allowed)`
with directory `0..20480`, ROST `47699968..48136192`, O-ManBlock
`929345536..929347584`, O-Shotgun `929347584..929349632`, and O-ZoneBlock
`929357824..929359872`, then `compare_executable(retail_root, combined_root)`.
That produced the committed combined-comparison receipt.

### Validation results

Final test commands/results are recorded in the validation addendum below.
Initial direct runs of three pre-existing suites failed import discovery without
`PYTHONPATH=.`. The suites changed in this work now add the repository root for
plain standalone execution. Two older assertions then failed because they
expected eleven named resources and the superseded personnel explanation; those
were corrected to the newly proved names/category-plus-fallback model.

## Remaining witness and integration boundaries

- Apply WIRING.md before claiming the feature is registered, rendered, packaged,
  or available through the normal Studio build/navigation. No protected release
  gates were weakened. The data-only CLI and independent panel tests are proved.
- Use the base XEX and a fresh/default roster context when witnessing the example;
  loading an existing ROS can override disc label/type/assignment data. Raw-save
  pointer binding is supported in core and tested, but no automatic save
  reinjection/resigning or save-plus-pack clone workflow is exposed here.
- Check that the clone's resource is actually opened, compare Sharks/Panthers
  against a team still using Bears/O-WestCoast, and observe CPU calls before
  claiming consumption. The static result does not remove global supplements,
  director behavior, user-team bank selection, or practice overrides.
- The TU 1.1 image was not reconstructed. No code patch targets either image;
  **TU compatibility is UNKNOWN**, not presumed from the unchanged executable.
- A broader authoring flow that directly edits clones after finalization requires
  changing all affected outer-index selectors and source fingerprints. This pass
  deliberately finalizes after existing edits, with a full old→new ordinal map
  in the local receipt. WR depth flips and the residual CPU personnel producer
  remain separate research tasks.

## Validation addendum

All commands below ran from this worktree with exit status 0. No game was
launched. The core suite includes malformed/duplicate JSON, ASCII case-folding
traps, two-volume synthetic allocation/ROST writes, name-only clone verification,
occupied metadata slack and hash collisions, output tampering/cleanup,
length-greater-than-distance H7A rejection despite a successful local decode,
dependent tag swaps, recipe idempotence, and source/review invalidation.

| Exact command | unittest output |
|---|---|
| `python3 tests/mod_editor/test_apf_book_unlock.py` | `Ran 19 tests in 23.475s` / `OK` |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_book_identity_qt.py` | `Ran 3 tests in 0.031s` / `OK` |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_save_playbook_assignments_gui.py` | `Ran 8 tests in 0.943s` / `OK` |
| `python3 tests/mod_editor/test_apf_splb_writer.py` | `Ran 22 tests in 0.120s` / `OK` |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_splb_tag_reassignment.py` | `Ran 86 tests in 1.040s` / `OK (skipped=5)` |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_splb_add_multiple_formations.py` | `Ran 14 tests in 0.250s` / `OK` |
| `python3 tests/mod_editor/test_apf_book_unlock_retail.py` | `Ran 0 tests in 0.000s` / `OK (skipped=1)` |

The legacy tag suite's five skipped cases use its existing local PE/disc path
gates. The new retail class deliberately skips when `APF_BOOK_RETAIL_INDEX` is
absent, with the message `Set APF_BOOK_RETAIL_INDEX to an existing user-owned
input; no retail bytes are bundled`. Supplying the explicit local inputs ran
all five of its cases:

```bash
APF_BOOK_RETAIL_INDEX='/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A' \
APF_BOOK_FLAT_PE='/home/noah/.codex-tmp/franchise-2026-08-28/apf.pe' \
APF_BOOK_RAW_SAVE='/home/noah/Downloads/apfe/Roster.ROS' \
python3 tests/mod_editor/test_apf_book_unlock_retail.py
```

```text
.....
----------------------------------------------------------------------
Ran 5 tests in 8.092s

OK
```

The registry validator recognizes module-style test commands; the initial
fragment's direct `tests/...` spelling was rejected at
`validate_registry.py:237` (`validation_command: no local module`). The fragment
now uses `python3 -m tests.mod_editor.test_apf_book_unlock`, which also ran
successfully (18 cases before the final source-roster regression was added).
The complete base registry plus the three rows was validated with file checks
and canonical serialization, without editing the protected registry:

```bash
python3 - <<'PY'
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from mod_editor.capabilities.validate_registry import validate_data
registry = json.loads(Path('mod_editor/capabilities/registry.v1.json').read_text())
fragment = json.loads(Path('data/apf2k8/book_capabilities.fragment.json').read_text())
registry['capabilities'] = sorted(registry['capabilities'] + fragment, key=lambda x: x['id'])
validate_data(registry)
with tempfile.TemporaryDirectory(prefix='astra-registry-') as directory:
    merged = Path(directory) / 'registry.v1.json'
    merged.write_text(json.dumps(registry, indent=2, sort_keys=True) + '\n')
    subprocess.run([sys.executable, 'mod_editor/capabilities/validate_registry.py',
                    '--registry', str(merged)], check=True)
PY
```

Output: `MOD_CAPABILITY_REGISTRY_VALIDATION_PASS
schema=vc_mod_capability_registry/v1 games=3 surfaces=21 capabilities=127`.
The unchanged APF release checker's `_validate_text` and
`_validate_structured_text` also passed on 20 deliverable files (two root
documents, nine JSON files, nine Python files),
printing `ASTRA_OWNED_TEXT_JSON_PAYLOAD_PASS files=20`. This checks text, JSON,
NUL bytes and embedded payload patterns; it does not substitute for the full
protected release/runtime integration gate. `git diff --check` exited 0 with
no output.

The final source guard pins the entire compiled ROST allocation. It refuses a
changed source before creating a destination and checks again during output
verification, even when rebinding the changed pointer fields would coincidentally
produce the same output. The full final verifier was rerun against the existing
local combined build after this guard was added:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from mod_editor.core.apf2k8_book_clone import compile_unlock, requests_from_json, verify_unlock
work = Path('/tmp/astra-book-c_5_qyqf')
requests = requests_from_json(Path('data/apf2k8/book_clone_example.json').read_bytes())
plan = compile_unlock(work / 'presets-game/0A', requests)
verification = verify_unlock(plan, work / '12-offense-game/0A')
print('ASTRA_FINAL_CLONE_VERIFICATION_PASS ' + json.dumps(verification, sort_keys=True))
PY
```

```text
ASTRA_FINAL_CLONE_VERIFICATION_PASS {"clone_count_added": 5, "directory_roster_clones_and_label_resources_reparsed": true, "executable": {"byte_identical": true, "bytes_compared": 38408192, "present": true, "sha256": "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"}, "idempotent_reapply": true, "runtime_status": "UNWITNESSED", "untouched_pack_bytes_compared": 3873054720}
```

The four committed receipt projections retain their original complete receipt
hashes from the actual builds/probe. The final guard changes validation only;
it produces the same directory, ROST, and clone payloads, as the rerun proves.

The final staged audit checked all 28 deliverable paths with those same text/JSON
validators, parsed all 16 Python files, and confirmed zero protected-file or
supplied-context edits: `ASTRA_STAGED_DELIVERABLE_PASS files=28 python_syntax=16
protected_edits=0`. `git diff --cached --check` also exited 0 without output.

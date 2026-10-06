# APF 2K8 VIP payload and metadata field map

This is Xbox 360 All-Pro Football 2K8 evidence from job d4. The original-Xbox
NFL 2K5 HMAC/signing implementation is unrelated. Urianus supplied an intact
Xenia loose `.USR` payload and metadata sidecar, rather than a signed STFS
package. The 20,456-byte size is the game's native serialized size, and the
first word is a generated profile identifier. It is not a checksum.

The reader is `tools/apf_vip_dump.py`. It reads a raw `.USR`, an exported Xenia
directory containing exactly one `.USR`, or a signed STFS saved-game package
containing one `.USR`. STFS SHA-1 metadata/tree/data checks use the established
read-only extractor. RSA signatures are never authenticated or replaced.

```sh
python3 tools/apf_vip_dump.py /path/to/exported/vip --output /path/to/new/vip.json
python3 tools/apf_vip_dump.py /path/to/Main.USR --header /path/to/Main.USR.header
python3 tools/apf_vip_dump.py /path/to/exported.con --member Main.USR
```

The tool creates new output only; existing paths are refused. Each dump retains
all payload bytes, all sidecar bytes and every four-byte scalar view. UTF-16
names stop at the first NUL while retaining stale bytes after it. Non-finite
float interpretations are strings so the output remains strict JSON. Reading
and dumping do not establish a game-load or gameplay witness.

## Evidence boundary

PROVED_NATIVE means actual retail BASE instruction flow or a literal native
getter/copy contract. Native record transport was executed with the repository's
bounded PPC32 machine; `memcpy` is the explicitly recorded ABI boundary. It is
not Xenia execution. The supplementary copier and inverse copier use unchanged
raw bytes. No signature operation occurs within this enumerated transport
family. Async filesystem/XContent creation and profile merging are outside
that execution.

The BASE flat PE used for these traces has SHA-256
`cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`,
image base `0x82000000`. The serializer receipt and disassembly are private
job evidence under `/home/noah/2k-worktrees/.b765-scratch/d4/`:
`vip_serializer_native.json`, `vip_serializer_disassembly.txt`, and
`vip_signature_report.md`. The 13 native cases cover actual and synthetic
full-payload round trips into slots 0, 7, 8 and 11, canaries, untouched bank
records and refusal boundaries.

## Raw `.USR` layout

All numeric native fields below are big-endian. Extents are half-open.

| Save offset/extent | Type/size | Meaning | Evidence/status |
|---|---|---|---|
| `0x0000` | u32 | profile identifier; nonzero random-generated value | PROVED_NATIVE: getter `84765678`, setter `84765680`, create `8476CCF0..8476CCFC`, clone `8476CDC4..8476CDD4`; ID lookup `84764158` |
| `0x0004..0x0024` | 16 UTF-16BE units / 32 bytes | displayed profile name allocation | PROVED_NATIVE: getter `84765730`, bounded setter `84765750`, create `8476CCE0..8476CCEC` and clone `8476CDE0..8476CDEC` |
| `0x0024` | float32 | **UNKNOWN meaning** | PROVED_NATIVE type/offset: getter/setter `84765760/84765768`; no behavior label supplied |
| `0x0028` | u32 | **UNKNOWN meaning** | PROVED_NATIVE type/offset: getter/setter `84765770/84765778`; no behavior label supplied |
| `0x002C..0x1410` | opaque except named cells below | **UNKNOWN meanings outside named statistics below** | Allocation proved; other per-field identities unproved |
| `0x0000..0x1410` | `0x1410` bytes | complete primary profile record | PROVED_NATIVE save `847655B0` from `85065D90 + slot*1410`; load `847641C0` copies inverse |
| `0x1410..0x4FE8` | `0x3BD8` bytes | complete supplementary profile record | PROVED_NATIVE size `84AE4DD0`; save copy `84AE4DD8` from `84EB2D48 + slot*3BD8`; inverse load `84AE4DF0` |
| whole payload | `0x4FE8` / 20,456 bytes | one primary plus one supplementary VIP record | PROVED_NATIVE serialized size `84765588` adds `1410` and `3BD8` |

Normal loaded slots are 0..7. Some copy routes permit extra slots 8..11 with a
flag. Slot -1 resolves the active profile for saving, or searches free ordinary
slots for loading. Those are runtime bank indices, not per-team identifiers.

Profile creation reads the 55-entry random-state ring at `852BA0D0` through
`84B3E938`; it does not read profile bytes to make the identifier. Native load
and save preserve the first word. Treating it as a checksum and replacing it
would change profile identity and could affect duplicate-profile rules.

The file-save handler obtains native size and calls `847655B0` to populate the
payload. It passes unchanged pointer/length, file offset zero and file type 3
through `8469A3B8`, `846798D0`, and queued operation 9 in `84678ED0`. UTF-16
`USR` at `84504E54` identifies the extension. Async dispatch and kernel
container creation remain unexecuted in the bounded transport probe.

## Named native VIP statistics

The native UI table at `821042C0..82104810` associates display labels with
formatter functions. The following cells have a direct primary-record load
inside that formatter. This establishes the stored field's UI meaning and
type, without guessing from values. It does not establish a CPU tendency
consumer or the field's update/merge contract. Raw float values are dumped
without reproducing the formatter's unit conversion.

| Offset | Native type | Native display statistic | Formatter / direct load |
|---|---|---|---|
| `0x1068` | u32be | Points | `0x84765a00` / `0x84765a1c` |
| `0x1078` | u32be | Points Allowed | `0x84765c08` / `0x84765c24` |
| `0x1088` | u32be | First Downs | `0x84765e10` / `0x84765e2c` |
| `0x108C` | u32be | Carries | `0x84765e98` / `0x84765eb4` |
| `0x1094` | u32be | Pass Attempts | `0x84765fa0` / `0x84765fbc` |
| `0x1098` | u32be | Completions | `0x84766028` / `0x84766044` |
| `0x109C` | float32be | Completion % | `0x847660b0` / `0x847660c4` |
| `0x10A0` | u32be | Touchdowns Rushing | `0x84766140` / `0x8476615c` |
| `0x10A4` | u32be | Touchdowns Passing | `0x847661c8` / `0x847661e4` |
| `0x10A8` | u32be | Kick Return Touchdowns | `0x84766250` / `0x8476626c` |
| `0x10AC` | u32be | Punt Return Touchdowns | `0x847662d8` / `0x847662f4` |
| `0x10B0` | u32be | Interception Touchdowns | `0x84766360` / `0x8476637c` |
| `0x10B4` | u32be | Fumble Touchdowns | `0x847663e8` / `0x84766404` |
| `0x10B8` | u32be | Tackles | `0x84766470` / `0x8476648c` |
| `0x10BC` | u32be | Interceptions | `0x847664f8` / `0x84766514` |
| `0x10C0` | u32be | Sacks | `0x84766580` / `0x8476659c` |
| `0x10C4` | u32be | Defensive Touchdowns | `0x84766608` / `0x84766624` |
| `0x10C8` | u32be | 3rd Down Conversion Attempts | `0x84766690` / `0x847666ac` |
| `0x10CC` | u32be | 3rd Down Conversions | `0x84766718` / `0x84766734` |
| `0x10D0` | float32be | 3rd Down Conversion % | `0x847667a0` / `0x847667b4` |
| `0x10D4` | u32be | 4th Down Conversion Attempts | `0x84766830` / `0x8476684c` |
| `0x10D8` | u32be | 4th Down Conversions | `0x847668b8` / `0x847668d4` |
| `0x10DC` | float32be | 4th Down Conversion % | `0x84766940` / `0x84766954` |
| `0x10E0` | u32be | Redzone Possessions | `0x847669d0` / `0x847669ec` |
| `0x10E4` | u32be | Redzone Field Goals | `0x84766a58` / `0x84766a74` |
| `0x10E8` | u32be | Redzone Touchdowns | `0x84766ae0` / `0x84766afc` |
| `0x10EC` | float32be | Redzone Scoring % | `0x84766b68` / `0x84766b7c` |
| `0x10F0` | u32be | Redzone Stands | `0x84766bf8` / `0x84766c14` |
| `0x10F4` | u32be | Redzone Field Goals Allowed | `0x84766c80` / `0x84766c9c` |
| `0x10F8` | u32be | Redzone Touchdowns Allowed | `0x84766d08` / `0x84766d24` |
| `0x10FC` | float32be | Redzone Scoring % Allowed | `0x84766d90` / `0x84766da4` |
| `0x1100` | u32be | Extra Point Attempts | `0x84766e20` / `0x84766e3c` |
| `0x1104` | u32be | Extra Point Conversions | `0x84766ea8` / `0x84766ec4` |
| `0x1108` | u32be | 2pt Conversion Attempts | `0x84766f30` / `0x84766f4c` |
| `0x110C` | u32be | 2pt Conversions | `0x84766fb8` / `0x84766fd4` |
| `0x1110` | float32be | 2pt Conversion % | `0x84767040` / `0x84767054` |
| `0x1114` | u32be | Running Plays | `0x847670d0` / `0x847670ec` |
| `0x1118` | u32be | Pass Plays | `0x84767158` / `0x84767174` |
| `0x111C` | u32be | Carries Outside Left | `0x847671e0` / `0x847671fc` |
| `0x1120` | u32be | Carries Inside Left | `0x84767268` / `0x84767284` |
| `0x1124` | u32be | Carries Inside Right | `0x847672f0` / `0x8476730c` |
| `0x1128` | u32be | Carries Outside Right | `0x84767378` / `0x84767394` |
| `0x113C` | u32be | Pass Attempts Left | `0x84767600` / `0x8476761c` |
| `0x1140` | u32be | Pass Attempts Middle | `0x84767688` / `0x847676a4` |
| `0x1144` | u32be | Pass Attempts Right | `0x84767710` / `0x8476772c` |
| `0x1148` | u32be | Pass Attempts Left Short | `0x84767798` / `0x847677b4` |
| `0x114C` | u32be | Pass Attempts Middle Short | `0x84767820` / `0x8476783c` |
| `0x1150` | u32be | Pass Attempts Right Short | `0x847678a8` / `0x847678c4` |
| `0x1154` | u32be | Pass Attempts Left Medium | `0x84767930` / `0x8476794c` |
| `0x1158` | u32be | Pass Attempts Middle Medium | `0x847679b8` / `0x847679d4` |
| `0x115C` | u32be | Pass Attempts Right Medium | `0x84767a40` / `0x84767a5c` |
| `0x1160` | u32be | Pass Attempts Left Deep | `0x84767ac8` / `0x84767ae4` |
| `0x1164` | u32be | Pass Attempts Middle Deep | `0x84767b50` / `0x84767b6c` |
| `0x1168` | u32be | Pass Attempts Right Deep | `0x84767bd8` / `0x84767bf4` |
| `0x116C` | u32be | Completions Left | `0x84767c60` / `0x84767c7c` |
| `0x1170` | u32be | Completions Middle | `0x84767ce8` / `0x84767d04` |
| `0x1174` | u32be | Completions Right | `0x84767d70` / `0x84767d8c` |
| `0x1178` | u32be | Completions Left Short | `0x84767df8` / `0x84767e14` |
| `0x117C` | u32be | Completions Middle Short | `0x84767e80` / `0x84767e9c` |
| `0x1180` | u32be | Completions Right Short | `0x84767f08` / `0x84767f24` |
| `0x1184` | u32be | Completions Left Medium | `0x84767f90` / `0x84767fac` |
| `0x1188` | u32be | Completions Middle Medium | `0x84768018` / `0x84768034` |
| `0x118C` | u32be | Completions Right Medium | `0x847680a0` / `0x847680bc` |
| `0x1190` | u32be | Completions Left Deep | `0x84768128` / `0x84768144` |
| `0x1194` | u32be | Completions Middle Deep | `0x847681b0` / `0x847681cc` |
| `0x1198` | u32be | Completions Right Deep | `0x84768238` / `0x84768254` |
| `0x119C` | u32be | Punt Returns | `0x847682c0` / `0x847682dc` |
| `0x11A4` | u32be | Kick Returns | `0x847683c8` / `0x847683e4` |
| `0x11AC` | u32be | Penalties | `0x847684d0` / `0x847684ec` |
| `0x11B0` | u32be | Yards Penalized | `0x84768558` / `0x84768574` |
| `0x11B4` | u32be | Turnovers | `0x847685e0` / `0x847685fc` |
| `0x11B8` | u32be | Points Off Turnovers | `0x84768668` / `0x84768684` |
| `0x11BC` | u32be | Punts | `0x847686f0` / `0x8476870c` |
| `0x11C0` | u32be | Punts Inside 20 Yard Line | `0x84768778` / `0x84768794` |
| `0x11D4` | u32be | Most Consecutive Games Rushing TD | `0x84768a00` / `0x84768a1c` |
| `0x11D8` | u32be | Most Consecutive Games Passing TD | `0x84768a88` / `0x84768aa4` |

76 stored cells have direct label/load evidence. Computed or helper-based
formatters such as total/rushing/passing yards and record highs remain
**UNMAPPED**; their labels alone do not establish a byte offset. Motion
event-update rules, formation identifiers and play identifiers remain **UNKNOWN**.
The dump retains their complete underlying bytes and alternate numeric views.

The evidence table includes label-pointer and table-entry addresses in each
dumped named field. Its generation receipt is the private
`vip_ui_stat_fields.json` under the d4 scratch directory.

## Native UI tendency summaries

The supplementary context getter `84AE7258` returns the selected record's
supplementary base plus `0x1228`. Its save offset is therefore `0x2638`.
The native VIP viewer initializer `84A6B920` resolves a selected primary record
through `8476DC10`, finds its bank slot through `847644D8`, then gets this
supplementary context. This is a separate UI evidence chain from the primary
label/formatter table above.

The Motion, Audible, Formation Shifts and O-Line Adjustments category-0 UI
percentages are now mapped. Their source cells are float32BE. Component names
below describe their roles in these UI formulas only. Event units, accumulation
and merge rules, and all CPU behavior effects remain **UNKNOWN**.

| Save offset | UI formula role | Native float load |
|---|---|---|
| `0x3A28` | Motion ratio numerator | `84A6C5F4`, context+`13F0` |
| `0x39AC` | Motion ratio denominator | `84A6C5D8`, context+`1374` |
| `0x2748` | Audible numerator component | `84A6C6DC`, context+`110` |
| `0x276C` | Audible numerator component | `84A6C6E0`, context+`134` |
| `0x2740` | Audible denominator component | `84A6C6BC`, context+`108` |
| `0x2764` | Audible denominator component; Formation Shifts and O-Line Adjustments denominator | `84A6C6B8/C730/C798`, context+`12C` |
| `0x2770` | Formation Shifts numerator | `84A6C74C`, context+`138` |
| `0x2774` | O-Line Adjustments numerator component | `84A6C7B4`, context+`13C` |
| `0x2778` | O-Line Adjustments numerator component | `84A6C7B8`, context+`140` |
| `0x277C` | O-Line Adjustments numerator component | `84A6C7C4`, context+`144` |

Audible sums `276C + 2748` for its numerator and `2764 + 2740` for its
denominator, with float32 rounding at each addition. O-Line Adjustments sums
`float32(2778 + 2774) + 277C`, again rounding the second addition to float32.
Formation Shifts and Motion each use their two individual cells.

The initializer converts numerator and denominator floats to signed int32 by
truncating toward zero (`fctiwz`). It uses zero if the denominator integer is
not positive. Otherwise it converts both integers back to float32 and divides
with float32 rounding. The category-0 value formatter multiplies that ratio by
100 with float32 rounding, then truncates to signed int32 and uses `%d%%`.
Thus a fractional stored pair such as 5.9/10.9 produces 50%, and a denominator
of 0.5 produces 0%. The reader reproduces this arithmetic within finite int32
conversion bounds and default nearest float32 rounding; unsupported conversions
remain explicit, with all raw bytes preserved.

| UI label | Initializer ratio/store PCs | Label address | Value formatter PCs |
|---|---|---|---|
| Motion | `84A6C62C/C638`, UI+`70` | `84613FA0` | `84A6EA18/EA38/EA4C` |
| Audible | `84A6C71C/C72C`, UI+`74` | `84613FE8` | `84A6EB84/EBA4/EBB8` |
| Formation Shifts | `84A6C784/C794`, UI+`7C` | `84614080` | `84A6ED20/ED30/ED40` |
| O-Line Adjustments | `84A6C7FC/C808`, UI+`80` | `846140A4` | `84A6ED84/ED94/EDA4` |

The private `vip_motion_native.json` receipt has 12 passing bounded native UI
cases, including actual supplied bytes for all four displays and Motion zero,
negative and fractional denominator cases. Its SHA-256 is
`6013412faaee32c98cae4296341eb5252cd617595a60641a8a114eb7e5128c6b`.
Native bank-slot and context getters execute; selected-profile lookup and
stdlib string formatting are explicit boundaries. This is offline native
evidence, with no emulator or full-game UI witness.

The two Motion inputs are not certified as "number of motions" and "total
plays", and the resulting percentage is not certified as a CPU motion
probability. These four UI percentages are readable; their controls remain
read-only until the event updater and CPU consumers are established.

## Structural views with unproved meanings

These offsets are useful research windows in the supplied save. Outside the
mapped native statistics and UI ratio input roles above, they are not validated field boundaries or
tendency names. The reader always labels alternate numeric views
`UNKNOWN_FIELD_TYPES_AND_MEANINGS`.

| Window | Observed structure | Remaining proof |
|---|---|---|
| `0x1068..0x13D0` | native UI statistics plus remaining unmapped words | Named direct fields above are proved; types and meanings of remaining words are unknown |
| `0x1414..0x1498` | 33 adjacent u32 values set to 1 in both archived fresh and supplied saves | Flags versus weights versus counters; semantic identity |
| `0x2610..0x2638` | two sequences 0,1,2,3,4 | Their runtime consumers and semantic identities |
| `0x263C..0x27B8` | mapped UI components plus mostly nonnegative integer-valued float32 interpretations | Types and labels of remaining fields; every event-update contract |
| `0x27C0..0x3AEC` | Motion UI inputs plus packed opaque byte structure | Other record sizes, indices, field packing and consumers |
| `0x3AEC..0x3CE8` | mostly nonnegative integer-valued float32 interpretations | Type and statistic labels |
| `0x3F00..0x4F00` | candidate 128 rows at stride `0x20`, each starting with two float-looking words then small integers/bytes | **HYPOTHESIS only:** row allocation/type/identity not proved; no formation/play names assigned |
| `0x4F00..0x4FE8` | many small u16-looking values and an opaque tail | Field widths, counter identities and consumers |

Archived B1 profile captures independently have the same total native size.
They have very sparse supplementary content, while the supplied profile has
substantial content across these windows. That comparison supports accumulated
state being present; it does not establish CPU behavior controls, formation
usage or play usage. Native UI evidence, rather than this byte distribution,
establishes the four display formulas above. No behavior label is promoted
from a plausible value distribution.

## Xenia sidecar layout

The 328-byte sidecar matches `XCONTENT_AGGREGATE_DATA`, whose base is the
308-byte `XCONTENT_DATA`. This layout is supported by the primary
[Xenia source](https://github.com/xenia-project/xenia/blob/95a5c3ee250f80c3b9d139658649d9ffb6db3eec/src/xenia/kernel/xam/content_manager.h).
That source establishes the metadata structure, not the identity or behavior
of Urianus's particular Xenia Edge binary. The pinned file SHA-256 is
`896ac73a10a02fd5acf32b3295a189fb503530f1feb8ece7b4b75e5f4748beac`.

| Header offset/extent | Field | Status |
|---|---|---|
| `0x000..0x004` | device ID, u32BE | PROVED_XENIA_SOURCE |
| `0x004..0x008` | content type, u32BE; 1 = saved game | PROVED_XENIA_SOURCE |
| `0x008..0x108` | display name, 128 UTF-16BE units | PROVED_XENIA_SOURCE |
| `0x108..0x132` | filename allocation, 42 bytes | PROVED_XENIA_SOURCE; bounded ASCII view |
| `0x132..0x134` | padding | Preserve even if nonzero |
| `0x134..0x13C` | unnamed 64-bit field | **UNKNOWN meaning**; upstream also leaves it unnamed; do not certify it as XUID |
| `0x13C..0x140` | alignment padding | Preserve |
| `0x140..0x144` | title ID, u32BE; APF is `54540807` | PROVED_XENIA_SOURCE plus supplied metadata |
| `0x144..0x148` | tail padding | Preserve; extension-looking bytes here are padding, not another filename |

The sidecar has no STFS RSA certificate/signature storage. It cannot be used
as a real-console signature. A real Xbox package needs an independent outer
STFS extraction/hash/signature route. Existing repo rehashing repairs SHA-1
integrity and preserves RSA bytes; it does not re-sign modified content.

## Writer boundary and next captures

No writer ships here. The reader establishes exact transport and known identity
fields, but the tendency field meanings and complete lifecycle merging remain
unproved. A name-only editor would not implement CPU tendencies. Console
re-signing also requires the owner's complete exported package and external
save-manager/keyvault route, which are absent.

To label counters without guessing, capture the same profile twice around a
short controlled practice sequence: fixed offense/formation/play, a known
number of snaps and motions, then save. Record whether each snap used a motion,
audible or formation change; include an unchanged-state re-save to isolate
volatile fields. The native field-updater/consumer trace must agree with the
save delta before a field is named or made writable. A real-Xbox export is
useful only as the complete `.USR` CON/STFS package.

CPU attachment research is separate: see
[apf_vip_cpu_design.md](apf_vip_cpu_design.md). Bank loading and a CPU-side
lookup are necessary evidence, but do not establish every profile tendency
consumer or automatic CPU motion.

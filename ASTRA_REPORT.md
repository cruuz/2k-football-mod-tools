# b72-a3: saved book types, PS3 season probe, logo timings

This job implements a confirmed raw-save label-type action and records two
offline probes. No emulator, hardware, visible GUI or game load was used.
The saved-book behavior is **UNWITNESSED**. No season converter is built.

## Delivery and base

The supplied worktree actually started at `6944f5626`, a beta-72 integration
commit, on `astra/b73-a3-apf-aszemple`, despite the brief naming `088e3f41`.
The three changed production files were identical between those revisions.
The shared Git directory is outside the writable roots. Delivery therefore
uses `.scratch/b72-a3.git`, branch `b72-a3`, based directly on `088e3f41`.
Only explicit job paths are committed there. The bundle is
`.scratch/astra-b72-a3.bundle`. Existing unrelated worktree content is retained.
The bundle's changelog contains this job's additions over the requested base;
the working changelog also retains the supplied newer integration's entries.

## Saved label book type

The request says "write the playbook into a .Ros file". Save Assignments now
offers **Write a label's book type** after a raw save has been loaded. It asks
for the label, the already built game's `0A`, a type from that side of its ROST,
and a new output filename. A final confirmation names both types, every team
sharing the label, game folder, destination and the UNWITNESSED test steps.
The confirmation defaults to No. Staged team assignments must be written and
reloaded first; signed sources require extraction to a raw roster first.

`rewrite_save_label_type` in `apf2k8_book_identity.py` uses the same one-based
relative pointer as the reader and disc clone binder: `label + 4` points to
an existing immutable UTF-16BE string. The dossier's "13-byte edit" is not the
write contract: one four-byte pointer is the entire allowed span, and actual
changed bytes depend on the pointer values. Interned shared type strings are
never overwritten. All 40 team assignments, all other labels, all string bytes
and the file length remain unchanged.

The source must be the known 2,715,908-byte Xbox layout and pass the existing
strict roster verification. Missing string-pool names refuse: this is the
disc clone binder's existing-name behavior, not a new string allocator.
Clones named after existing saved label/team names are supported. If a renamed
disc clone's type is absent from an older roster's string pool, this action
cannot bind it. New names need a separate allocation proof.

The service checks the source hash again before writing, resolves the installed
SPLB by CRC32 of uppercase ASCII `<type>-spb.iff`, checks its decoded header
name and same-side disc assignment, then exclusively creates the output and
JSON receipt. Binary file descriptors include `O_BINARY` where supported.
It rereads both files and independently derives the allowed edit from the
original source; any unrelated byte change or altered receipt fails.
Existing output/receipt files are never replaced. Failure removes only new
files from this operation. All new path handling uses `Path` and `tempfile`.

Fixture evidence is in `reports/b72_a3/save_label_type.json`:

- Source SHA256: `85fdf0d82360294463ff6d7396d7bfc84ed175f0a40573cf3249ad12cc4263f1`.
- Label 0, `49ers`: `O-ZoneBlock` to `49ers`; pointer at `0x1D31E0`,
  string at `0x21E9D0`, only byte `0x1D31E3` differs.
- Filename `49ers-spb.iff`, CRC32 `0x48DCB6D2`.
- Output SHA256: `84eae373a0d64423c523db454a9ddcf8333982c06fe91967f2b252c48dcf1167`.
- Strict readers accept 2,254 players, 1,386 memberships and 69 labels.
  Team slots 5, 6, 12, 14, 15 and 23 already use that label.
- Restoring the original type produces the exact original bytes. The source
  file remains unchanged. A generated two-resource built archive proves the
  real CRC lookup, IFF decode, SPLB header check and raw-save service handoff.

Experimental, explicit action; no preset enables it. The protected registry
and release allowlist follow-up is specified in `WIRING.md`.

### Required player witness

1. Keep the source roster and use a game folder already containing the clone.
2. Write the saved label type with the new action. Load the new roster in that
   same built game, using the owner's reinjection/rehash/resign process where
   the platform requires a container.
3. Select an affected team and check a distinctive clone formation/play.
   Check an unaffected team as a control. Record game build and title update.
4. Save, exit, reload and check that same distinctive formation/play again.
   Record the clone name, team slot and output hash, plus any USER/UA/UB or
   mode override. This is required before an in-game claim.

## Read-only PS3 season probe

Source: supplied `BLUS30049-FXG-21/USERDATA`, SHA256
`9a11b3a9ac73e63fd6f8c547ed431fe30dc6562f5ad443ec8c8a667f51043bbb`.
The local September-4 roster bundle contains the exact same USERDATA hash.
`USERDATA.bak1` is not treated as another decrypted sample.

The dossier's size arithmetic is correct, but **the extra 70,448 bytes are
not an appended block after a roster starting at zero**. They split as follows:

| File range, end exclusive | Bytes | Evidence |
| --- | ---: | --- |
| `0x000000..0x000350` | 848 | 212 big-endian words, 140 are 0/1; 53 decode as floats between 0.1 and 1. Settings/flags interpretation is provisional. |
| `0x000350..0x297454` | 2,715,908 | All 40 roster counts match. Existing structural reader accepts this exact slice with unchanged relative offsets and strides. |
| `0x297454..0x2A8434` | 69,600 | Season trailer: team slots, sentinel/default arrays, roster-related indices and packed calendar records. 53,131 zero bytes and 12,389 FF bytes. |

The whole payload and the first 2,715,908 bytes both fail the strict structural
reader at root table 0 and the label reader at the first string pointer.
Slicing at `0x350` makes the structural and label readers pass, including all
69 labels. The strict player reader still refuses: player 176 appears in more
than one counted membership slot. This is a content/reader-invariant issue;
neither deleting memberships nor relaxing the check is authorized by the probe.

The embedded roster has 42,914 string references, 7,643 allocations, 207 odd
allocations and 658 interior references. Its string pool starts at absolute
`0x1F5A88`, with the usual relative pool offset `0x1F5738`.

### Extra-data map

All offsets below are absolute USERDATA offsets. Counts and pattern assertions
are reproducible with `tools/apf_b72_season_probe.py`. Meanings are separated
from the measured structure.

| Offset / extent | Measured structure | Interpretation and limits |
| --- | --- | --- |
| `0x297454` onward | Small scalar header, mixed flags and FF sentinels. | Season control state; exact field meanings unknown. |
| `0x297624..0x297654` | 24 big-endian uint16 values: 0, 1, 32, 3..23. | Team-slot list, replacing stock slot 2 with custom slot 32. League participation is inferred from the roster domain. |
| `0x29E99C..0x29EB1C` | 48 identical 8-byte sentinel/default records. | Opaque table. |
| `0x29EDB0..0x29F260` | 100 identical 12-byte sentinel/default records. | Opaque table; earlier records differ. |
| `0x29F264..0x29FFE4` | 864 uint32 values of `0x0000FFFF`. | Fixed empty-ID arena; 864 = 24 x 36, but dimensions/semantics are unproved. |
| `0x2A0034..0x2A1C54` | 600 identical 12-byte records containing sentinel IDs/default bytes. | Opaque state/statistics candidate, not a proved stats layout. |
| `0x2A1CB0..0x2A1E90` | 120 uint32 values of `0x0000FFFF`. | Another fixed empty-ID arena. |
| `0x2A1E90` | uint32 count 1,990. | Count matches the following non-sentinel entries exactly. |
| `0x2A1E94..0x2A4D1E` | 5,957 uint16 entries: 1,990 unique descending IDs, range 2,988..5,956, then 3,967 `0xFFFF` entries. | Capacity equals roster root table 10's count. Likely available/free record IDs; table 10's precise semantics remain unknown. |
| `0x2A4D1E..0x2A7C54` | Zero-filled region. | Opaque reserved/empty state; not safe conversion scratch. |
| `0x2A7C54` | uint32 count 19. | Count of following weekly records. |
| `0x2A7C58..0x2A7DD4` | 19 records x 20 bytes. First uint16 is a packed date; word +4 is 2 in every row. | Decoding day as low 5 bits, month as next 4 bits + 1 gives weekly Sept 5 through Jan 9. Year bits change 7 to 8 at January; epoch and other fields are unproved. |
| `0x2A8428`, `0x2A8430` | Final uint32 scalars are both 199. | Their meaning is unknown. |

This map does not identify every byte as schedules, standings or statistics.
One decrypted season snapshot cannot establish those semantics. It establishes
an embedded roster plus separate season state, with exact verified boundaries
and concrete index/calendar structures.

### Applicability of the four roster-converter difference classes

1. **Root runtime fields 15..18:** present at absolute `0x3D0..0x3E8`, with PS3
   values `51E11488`, `51E1177C`, `51E14A3C`, `51E1BF7C`. Successive deltas are
   756, 12,992 and 30,016 bytes: each exceeds the serialized preceding table
   size by 224. Do not assume the roster converter's Xbox base-plus-file-offset
   values are valid for season allocations. An Xbox season reference is needed.
2. **Palette rotation:** embedded structure detects PS3; 2,640 discriminating
   colours have alpha last and none alpha first. The same 266 x 10 palette
   layout exists, so RGBA to ARGB remains relevant, with neutral colours not
   counted as discriminating votes.
3. **Runtime blocks/banks:** the eight-word block is at absolute `0x230574`.
   Eight BLPS magics are at `0x258360`, `0x260180`, `0x267FA0`, `0x26FDC0`,
   `0x277BE0`, `0x27FA00`, `0x287820`, `0x28F640`, all spaced 32,288 bytes.
   They match the ordinary roster's eight bank positions plus `0x350`.
   The existing converter scans from relative `0x26D030` and handles the last
   five plus the trailing header. The first three are outside that scan;
   blindly broadening it to all eight is not proved. Other season runtime
   addresses or checksums in opaque fields also remain unclassified.
4. **Odd/interior strings:** present in this edited fixture. Existing repair
   logic is a starting point, but repair plus membership-policy decisions and
   strict season verification need separate proof. No repaired file is emitted.

**Feasibility: L.** The embedded graph makes a converter plausible. Required
next evidence is a decrypted Xbox season save at a comparable state, paired
before/after fixtures for one game/week progression, stable mappings for every
opaque trailer region, runtime-address treatment, integrity/container rules,
and strict season readers. Then output must round-trip and be loaded by a
player. This job does not build or promise that converter.

## PS3 logo import timings

The request says "very slow to import and build the logos from the PS3 Bundle".
The supplied screenshot shows slot 96 using greedy H7A, a 71,137-byte budget
and 52,823 used. The screenshot does not identify its source art. The supplied
README says the September-11 ZIP was unavailable; the separate local fixture
`NFL Logos Textures.zip` is 13 MB, SHA256
`57d7d4a9916cafbc654846ab21514e0e95cccfea73003867c07dc33a36a411d3`.
It has 27 accepted logo pairs and five rejected pairs across all artwork kinds.
The timing uses the Raiders pair from the supplied matchup scenario and retail
Xbox slot 96, outer 884. That fixture slot has a **54,753-byte** art budget,
so this is a bounded reproduction of the path, not the screenshot's exact build.

Linux x86_64, Python 3.12.3, 32 logical CPUs, native H7A helper enabled.
One cold process and subsequent in-process cache reuses, with instrumentation:

| Phase | Seconds |
| --- | ---: |
| ZIP read/decode, cold | 6.7569 |
| ZIP read/decode again | 6.5234 |
| Destination slot discovery | 0.9335 |
| Preflight all 27 logo pairs, cold | 133.8528 |
| Preflight all pairs, warm | 12.2330 |
| Plan selected slot | 0.0040 |
| Stage slot 96, real session and PNG readback | 12.5980 |
| Compile/reparse slot 96 after preflight | 1.8358 |
| Compile again, package cache reuse | 0.0259 |

The selected Raiders art reaches the two-shade greedy step: 50,261 compressed
art bytes, total package 55,296 bytes. Both compile passes have identical
SHA256 `1eac2f87cf93b79049d47dee1a4ee4464596fb389010453dd89334eaeb001dea`.
This is cache parity evidence, not a new performance improvement.

Instrumented summed worker time is 1,733.54 seconds in optimal H7A, 119.56 in
verification, 35.63 in source decode, 23.15 in mips, 23.11 in region masks,
and 12.45 in greedy H7A. Worker seconds overlap and must not be added to wall
time. The dominant cold cost is the fit ladder across layouts/minimum budgets.
Warm preflight still builds source templates and staging repeats validation.

No production performance patch is made: a correct cross-session stream or
template cache needs content/layout/policy keys, bounded persistence,
invalidation, corrupt-cache handling and byte-parity checks across restarts.
That is speed-job work, rather than an obvious isolated one-file correction.
Other follow-ups: measure selected-slot-only preflight versus all-slot UI
choices, cache verified template decoding, and profile ZIP decompression again.
Full game-folder copying, linked logo-cache compilation, Windows/macOS timing
and rendering are excluded. No overall Build-time claim is made.

## Validation

Standalone commands run in the worktree:

```text
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_save_label_type.py
  9 tests, OK, including the fixture ROS and generated built archive.
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_save_playbook_assignments_gui.py
  8 tests, OK.
PYTHONPATH=. python3 tests/test_apf_save_playbook_assignments.py
  10 tests, OK.
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_book_identity_qt.py
  7 tests, OK.
PYTHONPATH=. python3 tests/mod_editor/test_apf_book_unlock.py
  19 tests, OK.
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_ps3_roster_convert.py
  13 tests, OK.
python3 packaging/repin.py --apply
  applied 0 pin update(s).
```

Reproduce metadata probes with new report paths:

```text
python3 tools/apf_b72_season_probe.py inputs/aszemple/2k8-ideas_b9010ac3_3.zip --report reports/b72_a3/season_probe-new.json
  SEASON_PROBE_PASS offset=0x350 prefix=848 trailer=69600 banks=8 converter=no
python3 tools/apf_b72_logo_benchmark.py --bundle "<local NFL Logos Textures.zip>" --index "<retail Xbox game>/0A" --report reports/b72_a3/logo_timings-new.json
```

`tools/apf_h7a_optimal` remains mode 0755. No retail binary, generated save,
game volume or artwork is added to the delivery. Reports contain metadata only.
Season/franchise feature requests, VIP and auto-subs remain outside this job.

PROVED: bo's gameplay loader keeps Zone Read at 155 and RPO at 157, while 48 is PA Z Slant; v4's buffer-relative diagnostic can be overwritten with another actor's 48, but attributing Noah's live 48 to that defect remains HYPOTHESIS.

# Read option v5

EXPERIMENTAL / UNWITNESSED. Noah witnessed the v4 snap hook and `READ miss 48`
on bo, with no handoff. He has not witnessed v5. This change stays within the
existing **2048 RX / 256 RW / 88 RO** reservation and **two-record, 64-byte**
intent table. Normal code occupies 2048 bytes; diagnostic code occupies 1876
bytes. No allocator budget was increased.

## Identity finding and the decision taken

The required demonstration that native play 48 is Zone Read could not honestly
be produced: the actual bo resource and executed gameplay loader contradict
it. V5 implements the brief's permitted alternative, resolving the paired
resource index from the loaded play pointer and its fingerprints. It does not
install an invented `155 -> 48` conversion.

The read-only evidence is the exact bo image named in the brief:

- Image size: 6,324,822,016 bytes.
- XBE SHA-256: `18c467fbed452f358d059766bebb424b87068da432aa9f002c132235c2bc6d10`.
- MIN SHA-256: `c8eaf4057de5b280b7fd1423fa574c13a3d2bb471167a18a7e9f20b121356cf0`.
- Installed table SHA-256: `fb0d3d290771ef6f6653dc4f6edc50a6c25de4a3555a47a11f264066d205064c`.

Only the XDVDFS directory, bounded default.xbe and fixed 78,768-byte MIN entry
were read. No whole image or archive pack was loaded into RAM or copied.

PROVED by disassembly and bounded native execution:

1. `0x161E30`, used by the old tests, loads the custom-playbook editor's fixed
   buffers. Those tests supplied the play descriptor and post-snap condition
   node. They did not establish gameplay menu enumeration.
2. The gameplay loader `0xE0D90` relocates the actual PLAY header and records
   and calls the native validators. The new fixture executes it, including
   validation, at two independent heap-like addresses. It preserves indices.
   `team+0x20` is the loaded book pointer; `book+0x60` is its play array.
3. The native menu accessor `0xE13F0` follows a formation's packed link,
   masks it with `0x1FF`, and returns the corresponding 96-byte play record.
   On bo's I Jokers menu the zero-based entries 6, 7 and 10 select resource
   155, 157 and 48 respectively. The entire formation link list is replayed.
4. The native assignment selector `0x1CEAC0` and assignment/node-initializer
   prefix `0x1CE600..0x1CE642` retain the selected record's exact descriptor.
   They do not turn 155 into 48. Selection is an explicit fixture input; this
   is not a replay of the complete visual play-call interface.
5. The exact, SHA-pinned bo v4 lookup uses hardcoded editor-buffer addresses
   and stores its quotient into diagnostic state **before** the caller checks
   the snap QB. Executing that old lookup first for the paired QB at 155,
   then for another slot-zero actor at 48, changes the displayed-number field
   to 48 while the recorded snap QB remains unchanged. The second lookup
   misses. The old HUD number therefore cannot establish the selected QB's
   resource identity.

HYPOTHESIS: an editor-buffer address assumption, contamination by a later
slot-zero condition actor, or an unobserved path through another book loader
explains the actual live miss. No memory capture from Noah's session exists
in the supplied evidence, so those alternatives cannot be distinguished.
The old v4 RPO/Gun numbers consequently cannot be predicted honestly from
that HUD number alone.

V5 follows the selected actor's team book pointer. It bounds and aligns the
QB descriptor against that header's play array, then matches the book name,
play name and five-node QB/back script fingerprints. The record offset is
used to report the **final paired resource index**, rather than to guess the
live table's enumeration. A synthetic relocation of the Zone Read record to
live slot 48 still resolves and displays resource 155. That permutation is a
robustness test, not a claimed reproduction of Noah's live memory.

`nfl2k5_play_intents.certify_read_identities` checks every play in each final
compiler view, including unpaired plays, and refuses duplicate fingerprints.
The final receipt records the unique match, number of plays checked, identity
model and diagnostic index. Existing final-resource SHA-256, personnel,
descriptor and node checks remain in place. A unique moved play compiles to
its new final resource index; an original-slot match with an identical clone
elsewhere now refuses.

| Paired recipe | V5 READ number | Gameplay loader index in bounded replay |
| --- | ---: | ---: |
| MIN I Jokers Zone Read | 155 | 155 |
| MIN I Jokers RPO | 157 | 157 |
| Separately authored Gun Zone Read | 134 | 134 |
| Separately authored Gun RPO | 31 | 31 |

The bo image contains the I Jokers recipes. Its resources 134 and 31 are
ordinary calls, not the new Gun recipes. Gun predictions come from a separate
real compiler/pool/role/final-pairing replay. Four reads cannot fit this owner;
build the I and Gun witness cases as separate two-record tables.

## Native control behavior

The scheduler starts the paired native GIVE/TAKE path on the first update
after the QB receives the snap and reaches the authored condition. The native
animation event performs ownership transfer; the patch contains no ball-owner
assignment. The diagnostic shows `snap` while awaiting reception and `pend`
once the cancelable native exchange starts.

PROVED in the pinned native code: the center's snap initializer
`0x30C2B0 -> 0x9FF80 -> 0x9FE50 -> 0xB6F30` sets phase 14 and invokes the snap
hook before the separate ball-transfer event `0x30B8D0`. The QB's native
receive callback can advance to condition node 2 while the ball remains on
the center or in flight. V5 keeps that condition pending without starting
movement or consuming a choice until the QB owns the ball. The regression
executes the receive initializer/callback and native condition-cache reset,
supplies delayed arrival through native detach/attach calls, then runs frames
through a completed handoff. Both variants and all four I/Gun recipes pass.
The natural snap animation and flight timing remain witness requirements.

- **No new input:** native approach, paired handoff animation and exchange
  event give the ball to the back. Continuing to hold the snap button also
  gives; it is not an implicit keep.
- **Keep:** release Xbox A after snapping, then press A again while the QB
  still holds the ball. Native animation transitions invoke both participants'
  destructors, the back takes its native release/fake branch, and the QB
  enters native carry. Human stick priority resumes immediately.
- **Pitch:** Xbox **Black** pulls and pitches to the paired back, on either
  read recipe. The native opcode-19 initializer receives kind 1 in this QB's
  decoded operand cache and emits lateral command `0x4E`. Shared PLAY bytes
  remain immutable.
- **RPO pass:** Xbox **X** or the named receiver button pulls and enters the
  native pass path. Receiver readiness is checked. The native initializer
  consumes the queued receiver once and emits command `0x42` in the tested
  B-receiver case. An unready receiver leaves the handoff pending.
- Simultaneous presses prioritize Black, then RPO pass, then a fresh A keep.
  These are physical Xbox button names; use the emulator/controller mapping.
  Native packet conversion separately proves the A/B/X/Black masks. Hardware
  polling and the later game-input copy are outside that bounded proof.

Human cancellation lasts until native exchange, including a delayed mesh
past one second. CPU evaluation retains its one-second fallback, bounded
snap-assignment search, unblocked edge selection and three-sample confidence.
A close crash pitches, a wider crash keeps, and a wide/uncertain read gives;
a ready RPO receiver supplies the CPU pass alternative. The diagnostic's
CPU-give policy is explicitly retained to fit its text path in the same
reservation. Use the normal variant to witness CPU reads.

Only the snap QB and matching back assignment may be controlled. Phase,
roster, QB/back descriptor, controller and clock changes stop the scoped
override; ownership changes after mesh start also stop it. Before reception,
the native condition remains pending. Duplicate clock samples do not consume
a new choice. The
exchange hook rejects a queued give event after an explicit keep/pass/pitch,
so it cannot steal the ball after cancellation. When scope ends without a
cancellation it leaves the retail event alone. Native reset clears the entire
256-byte state. The condition hook cannot reenter GIVE after a decision.

No input suppresses human forward-run priority while native GIVE steers toward
the back. Its approach may produce nonzero native movement toward the mesh;
that is required for the handoff. It is not proof of natural locomotion or
contact behavior.

The option pack is regenerated through `option_pack`/`save_pack` as recipe
version 1.0.2. Only its version and control text change; no PLAY scripts change.
Real compiler, pool recode, depth-role and final pairing paths were rerun.
HELP_TEXT, play-card notice and the existing capability object describe the
new controls and retain the experimental/unwitnessed label.

## Native replay scope and safety

The frame fixture executes the retail per-frame dispatcher, both participant
callbacks, interpreter advancement and operand decoder, GIVE/TAKE and
carry/pitch/pass initializers, native animation transition and both paired
animation destructors. Supplied approach poses reach the real paired
`0x531A08` animation. A supplied exchange event executes native detach and
attach routines `0xDDCA0 -> 0x26A4C0` and `0xDDCD0 -> 0x26A4A0` exactly once.
After supplied animation completion, the dispatcher advances the back from
TAKE to the carry node and runs native carry callback `0x2E3800`, preserving
back ownership and producing movement. Natural completion timing remains
outside the fixture.
Early and already-animated cancellations both reject a subsequent stale give
event. The real FONT4 path submits glyph vertices with the shared FONT and
floating-point state preserved.

Explicit fixture inputs/boundaries: actor list and poses, receive-snap or
condition entry, delayed ball arrival, controller/clock samples, task storage,
collision-free approach poses,
exchange-event delivery, neutral locomotion clip initialization, animation
asset loading, CPU downfield runner AI after KEEP initialization, aiming
result, font residency and GPU calls. No test boots the game or renders a
frame. These proofs do not establish natural event timing, visible blending,
contact behavior, ball flight, pass release/catch, lateral catch, live input
routing, or that a v5 witness disc has been played. The earlier hold-window
and EDGE-icon tests were replaced by the new full-frame controls, lifecycle,
identity, snapshot-edge, native input-mask and ABI tests; no obsolete control
expectation is silently retained.

Status/apply still check owner contents, all hook spans, immutable tables,
zero initial RW state, allocator seal and section digests before installation.
New native dependencies are pinned. Complete abilities and defensive-try
owners are validated before normalizing their shared animation/carry hooks;
this validation also runs when the screen owner checks read-option
requirements. The unused QB Spy rush/man initializer stores are outside the
read participant's dependency slices. The screen/read shared pass initializer
keeps its existing mutual validation. Unknown or partial neighbors refuse.

## Validation

Final standalone results and measured process memory are recorded below.
Logs and hash/trace receipts live in
`.scratch/read-option-v5/`; that directory is intentionally not committed.

Each test file runs with plain `python3 tests/mod_editor/<file>.py`, wrapped
in `/usr/bin/time -v`. Qt uses `QT_QPA_PLATFORM=offscreen`. The optional trace
variables are `NFL2K5_READ_OPTION_FRAME_TRACE`,
`NFL2K5_READ_OPTION_V5_TRACE` and `NFL2K5_READ_OPTION_V5_IDENTITY`; all outputs
are JSON under the scratch directory.

| Standalone file | Result | Maximum RSS, KiB |
| --- | --- | ---: |
| `test_nfl2k5_read_option_runtime.py` | 13 passed | 166704 |
| `test_nfl2k5_read_option_unicorn.py` | 6 passed | 117656 |
| `test_nfl2k5_read_option_controls.py` | 9 passed | 226800 |
| `test_nfl2k5_read_option_frames.py` | 10 passed | 228372 |
| `test_nfl2k5_read_option_diagnostic.py` | 17 passed | 280796 |
| `test_nfl2k5_read_option.py` | 15 passed | 97080 |
| `test_nfl2k5_read_option_qt.py` | 7 passed | 121200 |
| `test_nfl2k5_play_intents.py` | 20 passed | 59020 |
| `test_nfl2k5_play_intents_build.py` | 3 passed, 2 skipped | 149140 |
| `test_nfl2k5_read_option_diagnostic_manifest.py` | 2 passed | 270460 |
| `test_nfl2k5_owner_pairwise_composition.py` | 115 passed | 192744 |
| `test_nfl2k5_cave_oracle.py` | 28 passed | 908384 |
| `test_nfl2k5_screen_hooks_manifest.py` | 3 passed | 133152 |
| `test_nfl2k5_defensive_try_manifest.py` | 3 passed | 158740 |
| `test_nfl2k5_my_career_manifest.py` | 3 passed | 139180 |
| `test_nfl2k5_music_playlist_manifest.py` | 2 passed | 131312 |
| `test_xbe_patch_cave_references.py` | 107 passed | 537120 |
| `test_xbe_patch_memory_writes.py` | 95 passed | 343100 |

The two skips are the explicitly enabled full-disc build cases
(`NFL2K5_PAIRING_REAL_BUILD=1` was not set). The bounded real-disc PLAY reader,
37-book pool/depth-role pass, final pairing and active read/spy table
installation in that suite all passed. No read image was copied. The
reproducible assembler check is included in the runtime suite. The added
missing-Capstone skip path was also checked with Capstone absent from the
gate fixture.

Scratch manifest generation used:

```sh
NFL2K5_READ_OPTION_V5_MANIFEST=.scratch/read-option-v5/manifest.json \
  /usr/bin/time -v python3 tests/mod_editor/test_nfl2k5_read_option_diagnostic_manifest.py
```

All 18 standalone suites completed: **458 passed, 2 opt-in skips**.
Both XBE gates passed with the full owner union and both installation orders.
The largest measured process used 908,384 KiB RSS, below 2 GB.

Both XBE gates, the oracle and the four related manifest suites use
`NFL2K5_CAVE_MANIFEST="$PWD/.scratch/read-option-v5/manifest.json"` with the
standalone command pattern above. Pairwise runs without a manifest override.

The pairwise suite covers 104 distinct pairs in both orders across its 15
entries, plus 11 existing shared-guard regressions. Additional read-runtime
tests cover both normal and diagnostic variants with abilities, defensive
try and screen hooks, including refusal of incomplete neighbors.

The observed scratch manifest is SHA-256
`b3dedacb7f4af1897013041aebc7f972095c2f24cb77a6087fd473f18cac5987`.
It records 105 writer calls, 60 writers with changed bytes, 10,993 reservation
spans and 147 source fingerprints. Its composed XBE SHA-256 is
`77003327135c66599cc8bbc67c01bda2c2ae0134c3090c437a7fad3d30efdebc`.
The final compiler's two-record table exactly matches bo's table hash above;
the new lookup changes how that identity is recognized in loaded memory.

The updated capability passed the registry schema check and all of its own
file references and dotted module commands. The unrelated full-registry file
check stops at the baseline's missing `docs/research/apf_audio.md`; this task
does not claim that wider check passed. The exact temporary validation command and its script source are retained in
`.scratch/read-option-v5/capability-validation.json`; the script called
`validate_registry.validate_data` and checked this entry's paths and dotted
module commands.

The scratch cave manifest is explicitly a bounded XBE projection, not a new
disc-build manifest. It observes the real current gate writers and final PLAY
compiler, retains historical disc-only evidence, verifies unchanged Build XBE
IO AST against the historical source pin, refuses unrelated source drift, and
retains normal source fingerprint enforcement. The release manifest remains
protected and must be regenerated by Claude after integration.

During validation, shared abilities/defensive-try hook checks and the screen
owner's call into the read dependency checker exposed real composition
failures. They were fixed by validating complete neighbors before restoring
their retail bytes for dependency hashing. The scratch observer also exposed
the historic-team adapter's captured function alias; it now observes the
actual first write and requires nonzero observations from each changed owner.
No refusal or ownership check was weakened to make these pass.

## Noah's witness list

Use a clean diagnostic v5 build with the final paired MIN I Jokers table.
The expected number is the resource index, not the old v4 number 48.

1. Call Zone Read. After snap, photograph `READ 155 snap` then
   `READ 155 pend` when the QB receives the snap and starts the handoff. The
   snap phase may last less than a visible frame. Record
   the QB/back animation independently of the line. A paired play showing
   `miss` is still a failed live identity test; preserve the complete line.
2. Give with no new input, then repeat while holding A from the snap. Both
   should show `READ 155 give` at native exchange, with the ball visibly in
   the back's hands and the back carrying. Check that the QB approaches the
   back rather than starting an independent forward run.
3. Release A, then press it early and midway through the visible mesh.
   Expect `READ 155 keep`, QB possession, the back releasing/faking, and
   immediate stick control. Repeat with neutral and forward stick.
4. Press mapped Xbox Black early and during the paired animation. Expect
   `READ 155 pitch`, a visible lateral, and a back catch/carry. Watch for a
   canceled handoff event moving the ball again or stuck participant links.
5. Call RPO. Expect `READ 157 pend`. No new input should give. Repeat with
   X and the named receiver separately during the mesh: `READ 157 pass`,
   visible pull, native throw/release and receiver catch attempt. Exercise an
   unavailable receiver and a delayed mesh. Holding A alone must give.
6. Repeat after a timeout, audible/new play, controller change, tackle,
   possession change and repeated snaps. The line should reset; an old choice
   must not affect the next play or any unpaired call.
7. On a separately paired Gun build repeat these controls with numbers 134
   and 31. During a shotgun snap in flight, expect `snap`, followed by `pend`
   when the ball reaches the QB. Exercise both field directions and mapped
   controller layouts.
8. On a normal v5 build, witness CPU crash/keep, close crash/pitch,
   wide/give, replacement/blocked edge and ready/unready RPO cases. The human
   diagnostic deliberately defaults CPU reads to give.

Known unresolved requirements: the exact runtime state that produced Noah's
old live 48 is not recoverable from the supplied witness; natural animated
cancellation, lateral reception, pass release and back carry remain live
witness requirements. No v5 game/disc witness or production manifest rebuild
is claimed. These gaps are documented rather than replaced with a fabricated
mapping or synthetic gameplay claim.

## Integration and delivery

`WIRING.md` specifies the dispatcher tuple/kwargs, four status dictionaries,
BuildPlan/defaults/deferral/final pairing, PATCHES help and NEEDS_IMAGE,
40-character Build caption, allowlist, runtime closure, existing capability
entry and seventh hook. All protected files and unrelated owner modules stay
unchanged. No network, game boot, GUI display or audio was used. No disc copy
was built; scratch remains below 200 MB.

The explicit-path `git add -- <21 paths>` was rejected because the worktree's
Git metadata is read-only (`index.lock` could not be created). Delivery uses
the brief's authorized bundle fallback, `.scratch/astra-read-option-v5.bundle`,
with base `be99b324f34d536c625efcba7e7ea5d4f104fd2b` and branch
`astra/r65-read-option-v5`. A temporary Git directory stages and commits only
the 21 paths in `.scratch/read-option-v5/commit-paths.json`. The bundle is
verified and imported into a fresh temporary object database, with every
committed file checked against this worktree. Temporary Git directories are
removed. The final response and scratch delivery receipt record the commit
ID. Worktree files remain in place; the original branch is not advanced.
`ASTRA_BRIEF.md` and `.scratch/` are excluded from the commit. No push is
performed.

# Public mod editor capability roadmap

## Product boundary

The near-term product is a public, Linux-friendly mod editor for user-owned
copies of ESPN NFL 2K5 (original Xbox) and All-Pro Football 2K8 (Xbox 360).
It is **not** a native-PC port and does not need full game decompilation before
it can be useful.

The editor should:

1. fingerprint the user's exact supported retail input;
2. expose only operations enabled by
   [`registry.v1.json`](registry.v1.json);
3. preview the pixels or data that the encoder will actually store;
4. create a separate game copy with exclusive-output safeguards;
5. run the capability's validator; and
6. save a canonical mod project/recipe that another user can apply to their
   own matching retail copy.

The public download may include source code, schemas, field dictionaries,
project JSON, patch recipes, and original user-created art. It must not bundle
an XISO, XBE/XEX, archive volume, extracted retail texture/model/audio, save,
profile, firmware, key, emulator, or prebuilt copyrighted game image.

## What the status labels mean

| Status | GUI behavior | Claim boundary |
|---|---|---|
| `runtime-proved` | Edit, but only for the exact recorded selector | A changed target was visibly observed in a running title. This never generalizes to sibling assets. |
| `offline-writer-proved` | Edit | A copied game artifact is rebuilt and independently verified. Visibility may still be untested. |
| `extract-only` | Export | Standard local output such as PNG, WAV, or glTF exists; there is no game importer. |
| `read-only-mapped` | View | The parser/ownership map is useful, but mutation stays disabled. |
| `unknown` | Hidden/deferred | The owning format or semantics are not mapped. |
| `unsafe/deferred` | Hidden/deferred | Relevant evidence exists, but a writer could corrupt data, break integrity, or misrepresent behavior. |

“Runtime-proved” is deliberately narrow. APF jersey asset 6 is visible in the
Americans Home Jersey Editor; that does not prove all 24 jerseys, pants,
helmets, numbers, or gameplay cameras. NFL Detroit current-away torso art is
visible on live players at coin toss; that does not prove every uniform family,
Team Select card, team, style, or original hardware. The NFL `group36` result
likewise proves only one exact `s42nd.iff` expanded-wall diagnostic in xemu
0.8.135. A separate `upper_deck` writer now proves 12-to-8/4 source-subset
changed-count output offline, but not runtime visibility. Neither result proves
edited glTF import, original hardware, a retail-signed executable chain, or a
distribution/production path, so both capabilities remain hidden.

## Current modding ceiling

| Surface | NFL 2K5 Xbox | APF 2K8 Xbox 360 |
|---|---|---|
| Uniforms | General fixed-span copied-XISO writer; 3,170 audited torso/pants/sleeve/helmet targets are physically independent despite equal-content aliases; one exact live-torso runtime proof | All 24 jersey-color, pants-color, two-channel helmet-color, and shoulder-color assets have separate copied-`0A` writers; a hidden deterministic all-family ROST plan and fixed two-byte Assassins helmet witness are independently writable offline, jersey asset 6 has exact runtime proof, and helmet selector/runtime plus channel semantics remain unproved |
| Logos/cards | Team Select uniform/helmet cards have a copied-XISO writer | Uniform logos/text logos can be cataloged and sampled; no writer |
| Colors | Narrow fixed-size `Unif` packed-color writer; visible semantics incomplete | Uniform selectors remain view-only in the GUI; fixed byte-0 writers preserve the seven opaque bytes, while arbitrary assignment and runtime consumption remain unproved |
| Players/rosters | Same-allocation player names and masked jersey number have a copied-XISO writer | Players, teams, stadiums, and memberships mapped read-only |
| Portraits/faces | Roster portraits and live `f/h/n` face textures have copied-XISO writers; `s` SHAP head geometry does not | `hi_head` position geometry exports for research; no face texture/geometry writer |
| Models/SCNE/SHAP | Static SCNE position/topology exports to glTF; hidden writers now cover a 75-target same-count `FLOAT3` dispatcher, the pinned group36 four-position/four-native-quad footprint, and one `upper_deck` 12-to-8/4 synchronized source-subset count path. Only the exact `s42nd.iff` group36 expanded-wall diagnostic has xemu visibility; `upper_deck` remains offline-only, and neither result proves edited glTF import, original hardware, semantic ownership, or production/distribution readiness | Static SCNE position/topology exports to glTF; a hidden 77-target same-count BE `FLOAT32x3` dispatcher and pinned node17 four-BE16-strip permutation writer are offline-proved; no Xenia visibility or changed-count writer exists |
| Stadiums/fields | Create-team field art has a writer; stadium geometry exports, while the fixed-footprint group36 writer remains hidden despite exact pinned xemu diagnostic visibility because semantic ownership, the other catalog targets, changed counts, original hardware, signed-chain handling, and a production/distribution path remain unproved | Stadium geometry and ROST venue metadata export/view; the node17 position and topology writers remain fixed-footprint and hidden with no semantic-ownership or runtime proof |
| Menus/presentation | Three scorebug/font P8 textures have a composed copied-XISO writer; `score_buga` and `shield_espn` have exact xemu visibility proofs. Seven Main labels have a bounded copied-XBE experiment, but required digest repair invalidates the retail RSA signature, so label editing remains non-dispatchable | The shared alpha-only 128x128 `digital_font` now has a canonical typed recipe/provider and independently verified copied-`0A` writer. Its global consumers and runtime visibility remain unproved; layout/state/scorebug geometry and seven direct UTF-16BE Main labels remain read-only, with no verified PE-to-retail-XEX transport. |
| Audio | All 850 standalone AUDO records export to WAV; the exact `menu-back_01` slot now has a canonical typed recipe/provider, copied-XISO writer, and independent full-image verifier. Runtime audibility is untested, and generic effects and banks remain blocked | Standalone AUDO and indexed AUSB XMA1 export paths exist; no encoder/writer |
| Saves | Read-only FATX inventory covers eight real containers and exact `Settings1`/`Franchise1` slider fields; the 20-byte `EXTRA` signature owner is proved, but signing and changed-save reload are not | Disabled: no complete Xbox 360 save/profile container/integrity model |
| Schedules/franchise | Read-only feasibility map proves fantasy-draft ownership, the salary-cap enforcement gate, the exact Super Bowl season-index fallback, and one real `Franchise1` container/settings prefix; trade valuation, contract serialization, the intended post-year-five venue policy, and all writers remain unproved | Retained Season/franchise ownership is mapped, but a standalone playable franchise is not proved |
| Scripts/config/playbooks | DRCT and PLAY are structural read-only viewers | DRCT and PLAY are structural read-only viewers |

The strongest public first release is therefore an NFL 2K5 copied-XISO visual,
scorebug, and one-fixed-cue audio builder plus typed APF jersey, pants, helmet,
shoulder-color, and shared digital-font workflows and a broad
read-only/extraction browser.
That is already materially beyond emulator texture interception: these writers
modify the actual disc/archive resources and build user-owned game copies.

The NFL executable and archive proofs in this workspace target the original
Xbox release, not the PS2 disc used by PCSX2. The exact NTSC-U PCSX2 target is
now pinned as `SLUS-20919` version 1.01 with boot ELF `SLUS_209.19`, but no
matching ISO, ELF, save, or texture dump is locally present. A PCSX2 fix must
start from that independently recovered MIPS ELF and same-revision controlled
saves; Xbox virtual addresses and XISO spans are not portable patch offsets.

## Advanced gameplay and cross-title requests

These features are explicit registry surfaces so they cannot be accidentally
advertised as ordinary roster or model edits.

| Request | Current state | Can be an emulator/original-game mod without a native port? | Why it is still hard |
|---|---|---|---|
| Expanded gameplay sliders/tuning | Both games' exact 21 stock controls, 0..1 range, and 0.025 step are inspectable; NFL additionally has exact observed `Settings1`/`Franchise1` fields and values, while all writing/expanded values remain disabled | Often yes | One-variable serializer/load-precedence tests and platform-backed NFL save signing are still required; global tuning and difficulty may also live in executable code. |
| Catching/drop behavior | Unsafe/deferred in both games | Probably yes | Final outcomes may combine player ratings, global tuning, timing, defender contact, animation state, and code branches. A single “catch” byte would be an unsafe guess. |
| CPU AI and draft logic | NFL's exact 17-position fantasy-draft weights and ranking algorithm are inspect-only; an in-memory probe proves payload-only edits break `.rdata`, while digest repair changes the RSA-signed header. APF's matching table remains orphan/lineage evidence and deferred | Probably yes, if the executable/security lane is explicit | Requires an authorized XBE/XEX execution policy, deterministic scenarios, state/save inputs, version-pinned patching, and runtime proof. |
| NFL franchise limits | Xbox salary-cap enforcement has exact static watchpoints; the Super Bowl selector maps indices 0–4 to five stadium keys and every index ≥5 to `s45`; one real `Franchise1` container is inventoried, but trade valuation and contract fields remain unowned. PS2 `SLUS-20919` is identified but its ISO/ELF/save fixtures are absent | Probably yes, but the PS2 owners must be recovered separately | Requires one-variable contract saves with platform-backed signatures, a CPU-generated trade trace, an explicitly chosen post-index-4 venue policy, exact executable ownership, and deterministic year 5/6 runtime comparison. |
| Scorebug/presentation | NFL frame/ESPN/font textures are writable; `score_buga` and `shield_espn` are separately runtime-visible, while NFL `digital_font` was not visibly exercised in one no-input route. APF's shared alpha-only `digital_font` has a bounded copied-`0A` writer and full-volume verifier, but no runtime proof; geometry and behavior remain read-only | Mostly yes | Layout, scene, animation, team identity, shared-font consumers, and state bindings still need serializers or executable ownership before broader editing. |
| Mode/state routing | State graphs are read-only | Yes | Adding routes means executable pointer/code changes plus resource lifecycle, mode globals, returns, and integrity handling. |
| APF franchise restoration | Substantial retained code/assets, no proved playable hidden mode | Potentially | Requires initializer ownership, mode state, schedule/franchise data, save/load, week/offseason/draft transitions, UI routes, and a complete lifecycle test. |
| Cross-title franchise/mode port | Not implemented | In principle, but much larger than a data mod | Matching names/layouts do not make data or code ABI-compatible. It needs explicit schema translation and significant reimplementation or binary patching. |
| NFL-to-APF stadium/player/model conversion | Both titles export static positions/topology and each has one hidden, pinned four-vertex same-count position writer; conversion and general import do not exist | Yes in principle | Needs target catalogs, coordinates, transforms, all vertex attributes, UVs, materials, skin palettes, skeletons, SHAP/morphs, animation, collision, LODs, topology/archive serialization, and runtime proof. |

A native Linux port is not required for most of those ideas. Data writers and
even some executable patches can target the original games under an emulator or
compatible hardware. However, executable-changing features cross a different
risk boundary from asset editing:

- NFL XBE edits need a tested unsigned/rehashed/integrity workflow and exact
  version pinning.
- APF XEX edits need a tested loader/signature/integrity policy and exact
  PowerPC patch ownership.
- Emulator-only feasibility is not the same as original-hardware support.
- A native port becomes necessary only if the goal is to replace the platform
  runtime/engine itself or reimplement systems too invasive for a maintainable
  game patch.

## Release sequence

### R0 — capability browser

- Load the registry strictly and fail closed on unknown schema versions.
- Identify both supported retail inputs by SHA-256.
- Show every surface, proof level, exact selector boundary, validation command,
  runtime status, and `PORTME` blocker.
- Keep `unknown` and `unsafe/deferred` actions hidden or visibly disabled.

### R1 — NFL 2K5 visual mod builder

- Wrap the existing canonical visual-mod project format.
- Add pickers/previews for torso, sleeve, pants, live helmets, digits,
  nameplate atlas, Team Select cards, live face textures, create-team field
  art, and same-allocation team identity.
- Add the separate bounded player-name/jersey-number and roster-portrait
  workflows.
- Build exactly one new XISO and run independent verification before declaring
  success.
- Keep fixed `menu-back_01` audio as its own typed project: accept only the
  exact 16 kHz/5,696-frame PCM contract, build a separate new XISO, and report
  runtime audibility as untested until a matched capture exists.

### R2 — APF jersey editor

- Show all 24 jersey assets and every team/bank that selects each asset.
- Preview all nine decoded mip levels.
- Warn that the current BC3 encoder is proof-quality and that complex images
  may fail the fixed-allocation check.
- Create a new `0A` next to copied sibling files; never overwrite the source.

### R3 — extraction workbench

- Provide local PNG/WAV/glTF export for mapped texture, audio, and scene data.
- Mark outputs as derived from user-owned game files and exclude them from
  public mod packages by default.
- Preserve exact provenance so an edited asset can later be joined to a future
  writer without filename guessing.

### R4 — next data writers

Prioritize high-value features that can remain data-only. The proved APF
shoulder-color writer and the one fixed NFL `menu-back_01` writer are now
integrated through pinned typed recipes, providers, and independent verifiers.
The APF shared digital-font writer is integrated through the same boundary,
with its alpha-only contract and global-consumer warning retained; the
remaining sequence is:

1. runtime-witness the pinned APF node17 output; preserve the exact diagnostic-
   only boundary of the completed NFL group36 xemu witness; then runtime-witness
   the now offline-proved NFL `upper_deck` 8/4 source-subset outputs and close
   bounds/culling ownership before any typed-provider exposure;
2. additional bounded NFL effects plus APF audio only after production encoders,
   per-cue ownership, and fixed-allocation proofs;
3. broader safe NFL roster/team fields and APF fixed-size ROST fields; and
4. stock-stadium branding before attempting geometry replacement; and
5. NFL stock-range settings only after one-variable save pairs, copied-HDD
   transactions, platform-backed `EXTRA` signing, and clean reload proof.

### R5 — round-trip models

- Treat the validated NFL/APF machine-readable SCNE serializer specifications
  as the normative source; keep evidence ledgers and prose subordinate to them.
- Preserve the byte-identical no-op and independent changed-span guarantees of
  the pinned NFL stadium/group36 and APF stadium/polySurface19930 position and
  topology witnesses, including NFL's exact one-span XISO transport and exact
  pinned `s42nd.iff` xemu diagnostic visibility; do not generalize that one
  wall witness to other targets, changed counts, edited glTF, original
  hardware, a retail-signed chain, or production/distribution readiness.
- Finish transforms, UVs, normals, materials, texture links, skinning,
  skeletons, SHAP/morphs, animation, collision, and LOD semantics.
- Define a versioned neutral scene model rather than translating raw glTF by
  ad hoc field copying.
- Implement same-title import first; only then build NFL-to-APF conversion.
- Require archive-size and runtime verification for each asset class.

### R6 — executable and mode mods

- Treat gameplay tuning, catch/drop logic, CPU AI, scorebug state wiring,
  mode routing, and franchise restoration as version-pinned executable-patch
  projects.
- Keep code patches separate from data/asset projects in the GUI and manifest.
- Require reversible patches, exact before-byte hashes, integrity/loading
  handling, no external copyrighted bytes, and deterministic runtime tests.

## Gate for every new editor feature

A capability is not public-editable until its registry record can truthfully
name all of the following:

- exact supported retail identity;
- source container/resource owner;
- complete selector and input constraints;
- deterministic backend command;
- independent validation command;
- fixed-size, allocation, pointer, compression, and integrity rules;
- exact runtime status without generalization;
- every remaining `PORTME`; and
- a distribution rule that requires the user to supply their own game.

Run the registry gate with:

```bash
bash mod_editor/capabilities/validate.sh
```

The validator uses only Python's standard library, checks every referenced
backend/evidence/validator file, enforces complete surface coverage for both
games, rejects unsafe GUI exposure, and verifies canonical deterministic JSON.
It does not execute every referenced validator. Run the exhaustive evidence
gate separately with:

```bash
tools/validate_all_mod_editor_capabilities.sh
```

That runner executes every distinct non-null registry `validation_command`
once, attributes shared commands to all covered capability rows, and fails if
any validator exits nonzero or times out. Its optional v3 receipt must be
published outside the repository snapshot tree. The Linux publisher uses
anonymous `O_TMPFILE` storage and one no-replace `/proc/self/fd` hard-link
commit through a pinned root-to-parent directory-descriptor chain; it never
path-unlinks the destination after commit. A post-commit failure or interrupt
may leave a complete receipt without the runner's success marker, and an
authorized directory writer can replace it after the final point-in-time
check. The receipt pins the fixed execution environment and launchers; records
every audited host-command lookup leaf,
symlink chain, lstat identity, and resolved executable; and records deterministic
control/evidence manifests. The control plane is rechecked around every
validator, and timeout teardown covers surviving members of the validator's
original process group. Deliberately detached `setsid` work remains outside that
group and is forbidden by the trusted validator contract. Deferred rows remain
explicit rather than being counted as tested writers. Shared libraries and
subprocesses internally selected by the captured compiler/build/media/JDK tools
remain a trusted host boundary rather than a recursively hermetic claim. Bulk
retail/build/emulator inputs remain under each focused validator's hash
contract, and boundary snapshots are drift detection rather than a claim of
immutable filesystem isolation.

# Public mod editor scaffold

This editor turns the reverse-engineering results into a safe, release-oriented
project format. It is **not** a generic hex editor. Typed providers can now
dispatch the reviewed NFL 2K5 unified visual-mod, composed scorebug, and fixed
`menu-back_01` audio backends plus the APF 2K8 jersey-, pants-, helmet-, and
shoulder-color writers and the shared alpha-only `digital_font` writer. These
are eight typed routes; every other writer remains unavailable until it
receives its own fixed provider. Two
catalog-backed SCNE same-count position
writers, one pinned NFL same-footprint native-geometry writer, and one pinned
APF same-footprint native-topology writer are proved offline but deliberately
remain hidden and have no GUI provider.
Hash-pinned,
named read-only inspectors now expose uniform-sharing ownership, both games'
stock sliders and draft evidence, NFL franchise limits, and Main Menu routing
without exposing executable addresses or turning research rows into writers.

## Distribution boundary

- The application, schemas, research metadata, and future patch recipes may be
  distributed.
- Retail executables, disc sectors, extracted textures/models/audio, and built
  game images are never bundled.
- Each user selects a legally obtained NFL 2K5 or APF 2K8 source locally.
- Source inspection opens files read-only and matches exact SHA-256 fingerprints.
- Output creation always targets a new path. Existing files, directories, and
  even broken destination symlinks are refused.
- **Create Unmodified Source Copy** still makes only a verified staging copy.
- **Typed Build + Independent Verify** is a separate, explicitly confirmed
  operation described below. It writes only new paths and never turns a generic
  queue entry into an implicit patch.
- The APF jersey PNG export is a separate read-only operation. Its retail-
  derived PNGs stay local, are marked accordingly in provenance, and are not
  part of a distributable mod package.

Here, “independent verify” means a separate verification invocation that
reconstructs and checks the promised output boundary; it does not always mean
algorithmically independent code. The unified NFL visual and scorebug routes
use verify subcommands in the same reviewed top-level closure. The four APF
uniform verifier entries are separate but share low-level archive/layout
helpers with their writers. Those common-mode semantic limits remain explicit
even though process separation, executable provenance, and full-output checks
are enforced.

## Architecture

`mod_editor/core/` contains a GUI-independent project model, strict project JSON
loader, read-only source inspector, capability adapter, replacement queue,
exclusive copy writer, typed provider orchestrator, safe canonical recipe
generators, a fixed three-input adapter to the APF jersey exporter, and
sanitized report adapters for mapped gameplay/menu/uniform data. A
future Qt, web, or console UI can use the same core without importing Tkinter.

`mod_editor/project.schema.json` is the public v1 project-file contract.

`mod_editor/gui/tkinter_app.py` is the dependency-light shell. Tkinter 8.6 is
available in the current Linux environment and is part of standard Python on
many Linux, macOS, and Windows installations. PyQt5 is also installed locally,
but the preview deliberately does not make that third-party package a public
runtime dependency.

The research-owned canonical registry is
`mod_editor/capabilities/registry.v1.json`. The editor validates it through its
pinned v1 contract and fails closed on malformed records. A two-row embedded
sample exists only so UI development remains possible before the canonical file
is present; `--require-registry` disables that fallback.

The canonical registry spans all 19 surfaces for both games. Its validation
gate derives current classification and exposure totals directly from the
canonical JSON instead of treating a prose snapshot as authoritative. Exposed
edit rows identify a user-authored file type, while only fixed typed providers
own actual build dispatch. The two catalog-backed position rows and pinned
same-footprint geometry/topology rows remain hidden and have no provider.
Other writer-proof rows are intentionally
kept out of the generic file queue when they are hidden proof-boundary
duplicates, fixed/narrow experiments, or require a future structured
roster/color editor.
Run the registry validator below to report its current canonical byte length,
SHA-256, and classification totals.

## Capability and Advanced views

Every row is derived from the canonical registry:

- `PROVED`: runtime-proved or offline-writer-proved.
- `READ ONLY`: extraction or mapping is proved, but replacement is not.
- `PORTME`: unknown or unsafe/deferred.

The normal browser shows exposed, non-experimental features. **Show Advanced /
Experimental / PORTME** adds gameplay sliders, catching/drops, CPU and draft AI,
read-only/deferred scorebug work, mode routing, franchise restoration, and
cross-title model conversion. The proved NFL scorebug texture and fixed
menu-back audio providers remain in the normal browser. Selecting a row shows
platform and retail signature pins,
container constraints, named selectors, runtime status, validator, distribution
rule, and every PORTME note. These advanced entries do not gain edit controls
merely by appearing.

A replacement can enter the queue only when all of these registry claims agree:

1. classification is `runtime-proved` or `offline-writer-proved`;
2. backend operation is `write` with a pinned local module and command;
3. GUI contract is exposed `edit` mode; and
4. the accepted input format can be identified.

The generic queue accepts named targets, not addresses. Values beginning with
`0x` or containing `offset` are rejected. **Apply Queue — PORTME** remains
disabled: generic queue rows never become commands. Supported typed providers
use separate imported, schema-checked recipe bindings.

The selected capability also controls the standalone export action. **Export APF
Jersey PNGs…** is enabled only for
`apf2k8.uniforms.jersey_00_23`; selecting any other row disables it. This
action is independent of the replacement queue and typed build controls.

For allowlisted mapped rows, **Inspect Mapped Data…** opens a scrollable,
read-only JSON view inside the GUI. The dispatcher is keyed by capability ID:
it can show the 21 named stock sliders, NFL/APF draft-priority status, all five
NFL franchise-limit targets, the named NFL/APF Main Menu route, or exact
uniform-sharing owners. The NFL save row additionally shows a sanitized eight-
container inventory, observed `Settings1`/`Franchise1` slider values, and the
20-byte signature boundary without FATX locations, payload bytes, or signature
material. It accepts only game names, bounded asset indices, and canonical
uniform selectors. Unsupported rows keep the button disabled.

Main Menu inspection also distinguishes labels from localization. NFL's seven
rows use fixed direct UTF-16LE XBE slots; APF's use direct UTF-16BE XEX/PE
slots. A structural NFL copied-XBE label experiment exists, but repairing the
section digest invalidates the retail RSA signature, so it is not a typed
writer. APF has no verified PE-to-XEX rebuild lane. Neither route can be
renamed by inventing STRG/TXT IDs.

The underlying NFL save analyzer is a separate strict read-only tool. It proves
the actual FATX container shape and exact observed slider fields, but it does
not modify `SAVEGAME.DAT`, generate `EXTRA`, extract platform keys, or claim a
changed-save reload. A writer remains gated on one-variable fixtures,
platform-backed signing, copied-HDD transactions, and independent game reload.

The franchise inspector also carries a separate PCSX2 fixture gate. It names
the target (`SLUS-20919`, disc 1.01, ELF `SLUS_209.19`) and reports the current
absence of a matching PS2 disc, ELF, save marker, and texture dump. It never
reuses Xbox executable addresses as MIPS/PCSX2 patch coordinates.

## Usable typed provider: NFL 2K5 unified visual project

The NFL dispatchable capability is `nfl2k5.uniforms.all_visual`, through provider
`nfl2k5-unified-visual-v1`. The current registry authorizes eleven bounded edit
families: torso, sleeve, pants, live helmet, live number/nameplate, Team Select,
live face, create-team field art, team identity, player roster, and player
portrait. Exact recipe fields and limits are documented in
[`nfl2k5_unified_visual_mod_project.md`](../research/nfl2k5_unified_visual_mod_project.md).

Current GUI workflow:

1. Create an NFL 2K5 editor project and select the retail XISO.
2. Run **Hash / Recognize**. Typed dispatch requires exact SHA-256
   `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`.
3. Select **NFL 2K5 unified visual mod project** in the capability browser and
   choose **Import Typed Recipe / Project…**. This imports canonical
   `nfl2k5_visual_mod_project/v1` JSON; the GUI does not yet generate/edit that
   recipe internally.
4. Choose a new output XISO path. The provider derives
   `<output>.vcmod-manifest.json` and `<output>.vcmod-artifacts`; all three must
   be absent and have existing non-symlink parent directories.
5. **Typed Validate** rechecks the recognized retail source, validates canonical
   recipe JSON, and runs the backend's schema/input-pin validator without
   building an image.
6. **Typed Build + Independent Verify** repeats preflight, validates, creates
   the copied XISO through the backend's own exclusive writer, then starts a
   separate `verify` invocation. Success is shown only if that verifier
   reconstructs every expected span and proves all bytes outside the union,
   XDVDFS layout, and `default.xbe` unchanged.

The provider never evaluates the registry's command string. It requires the
registry classification, complete backend object (including that descriptive
command), sole source hash pin, and complete selector-field list to equal the
reviewed contract. Its subcommand, options, and option order come from an
in-code allowlist and are passed as an argument vector with `shell=False` and
closed stdin. Provider subprocesses receive a fixed minimal environment rather
than inheriting `LD_*`, `PYTHON*`, credentials, or user tool configuration.
Before the backend starts, the provider descriptor-reads and
SHA-256 checks the exact 32-file recursive local import closure, refuses
symlinks and hardlinked files, and copies those verified bytes into a private
temporary execution tree. Python runs the staged entry module and staged local
imports, so a workspace pathname replacement after hashing cannot select the
executed bytes. Preflight also requires the exact recognized-source
fingerprint, kind, selected/inspected path identity, current read-only source
hash, canonical recipe header, and exclusive-output conditions. The backend
itself uses `O_EXCL`; a race that creates an output after preflight therefore
fails rather than overwrites.

This is offline writer/transport proof, not a blanket runtime claim. Only the
separately documented Detroit away torso probe has positive runtime visibility.
No emulator is launched by the editor.

## Usable typed provider: NFL 2K5 scorebug textures

`nfl2k5.scorebug_presentation.inventory` dispatches through provider
`nfl2k5-scorebug-v1`. One canonical project can compose any one to three unique
targets into the same new XISO:

| Target | Required PNG | Known scope |
| --- | ---: | --- |
| `score_buga` | 64×64 RGBA | Field frame/corner atlas used by nine material bindings |
| `shield_espn` | 128×64 RGBA | ESPN strip used by two material bindings |
| `digital_font` | 128×128 RGBA | Shared digit atlas which can affect UI outside the scorebug |

The GUI's **Create Typed Recipe…** dialog accepts only these named targets,
validates exact stored dimensions/mode, pins each PNG by size and SHA-256, and
exclusively creates canonical `nfl2k5_scorebug_mod_project/v1` JSON. It supplies
the complete immutable retail/source-pin object internally; users cannot enter
archive names, offsets, compression controls, or replacement bytes. Existing
recipe paths and broken symlinks are refused. **Import Typed Recipe / Project…**
remains available for a recipe received from another mod author.

The provider re-hashes the exact retail XISO and descriptor-pins the scorebug
recipe schema plus the backend's exact nine-file recursive local import
closure. It refuses symlinked or hardlinked pinned files and runs freshly
verified module bytes from a private staged tree, then invokes fixed
`validate`, `build`, and `verify` argument vectors with `shell=False`. The
builder composes the selected fixed P8/VC-LZ spans into one exclusive copied
XISO. The verifier reruns the importers, rebuilds the complete allowed-byte
union, compares all 6.3 GB, verifies XDVDFS and `default.xbe`, and reconstructs
the preview/report artifacts before accepting the build manifest.

The transport is proved for all three targets. Runtime visibility is narrower:
separate solid-magenta `score_buga` and solid-cyan `shield_espn` replacements
are visibly proved on the live field HUD in xemu demo gameplay. A separate
magenta `digital_font` run booted, but the shared atlas was not visibly
exercised in its no-input field-HUD/lower-third frame; visibility and global
side effects therefore remain unproved. The writer still does not serialize SCNE geometry,
move/resize elements, alter team/clock/down data, change visibility/timing, or
write APF's Xenon scorebug resources.

## Usable typed provider: NFL 2K5 fixed menu-back audio

`nfl2k5.audio.menu_back_wav` dispatches through provider
`nfl2k5-menu-back-audio-v1`. This is deliberately one named cue, not a generic
`AUDO` or bank editor. Its canonical `nfl2k5_menu_back_audio_recipe/v1` recipe
contains only a purpose, the fixed target `menu-back_01`, a user-authored WAV
path, and that WAV's size and SHA-256. Recipe creation rejects symlinks,
metadata chunks, non-PCM data, and every WAV except mono PCM16LE at exactly
16,000 Hz and 5,696 frames.

The GUI's **Create Typed Recipe…** action collects the purpose and strict WAV;
it exposes no archive index, chunk selector, byte offset, codec control, or
retail payload. The equivalent display-free command is:

```bash
python3 -m mod_editor --create-nfl-menu-back-audio-recipe my-menu-back.json \
  --purpose "Replace the fixed menu-back cue" --audio-wav menu-back.wav
```

After the editor recognizes the pinned 6,300,499,968-byte retail XISO, the
provider re-hashes it read-only and requires the exact registry backend object,
classification, selector, extension, and sole source pin. It descriptor-reads
and hash-pins five single-link files: the writer and its sole local dependency,
the verifier and its sole local dependency, plus the recipe schema. The two
complete code closures are packaged separately as deterministic ZIP_STORED
zipapps in anonymous Linux memfds, sealed against write/grow/shrink, and run
from `/proc/<provider-pid>/fd/<fd>` with `python -I -B -S`, cwd `/`, closed
stdin, `shell=False`, and the fixed minimal environment. Repository imports
cannot replace the sealed execution bytes after hashing. Its fixed argument
vectors encode exactly 89 Xbox IMA ADPCM blocks into the existing 3,204-byte
payload allocation, create a new
layout-identical XISO and manifest, then independently parse and scan both
complete images. Verification accepts only the expected fixed payload changes
and creates a new metadata-only `verification.json` artifact; every output path
must be absent.

That proves fixed-size codec transport and copied-XISO integrity only. The
replacement has not been heard in a running title, the selecting runtime owner
is not proved, and no sibling effect, music, crowd, PA, or commentary bank is
authorized. The exact boundary and next experiments are documented in
[`audio_modding_compatibility.md`](../research/audio_modding_compatibility.md).

## Usable typed provider: APF 2K8 jersey colors 00–23

The APF dispatchable capability is `apf2k8.uniforms.jersey_00_23`, through
provider `apf2k8-jersey-color-v1`. It accepts only canonical
`apf2k8_jersey_color_recipe/v1` JSON with these three fields:

```json
{
  "asset_index": 6,
  "png": "/home/user/mod-art/jersey.png",
  "schema": "apf2k8_jersey_color_recipe/v1"
}
```

`asset_index` is an integer from 0 through 23. It is resolved through the
hash-pinned jersey-family catalog; the recipe cannot contain command-line
arguments, raw offsets, archive indices, or allocation sizes. `png` may be
absolute or recipe-relative, but must name a regular non-symlink PNG stored as
exact 1024×1024 RGBA. The public JSON contract is
[`apf_jersey_recipe.schema.json`](../../mod_editor/apf_jersey_recipe.schema.json).

The same capability now has a read-only authoring export. **Export APF Jersey PNGs…**
collects only the user-owned retail `0A`, an integer asset index in
`0..23`, and a new absent output-directory path. The catalog—not the user—owns
the archive entry, inner file, offset, allocation, codec, and nine-level Xenos
layout. Export runs on the background job thread and restores the selected
capability's actions after success or failure. A successful new directory has
the 1024×1024 editable base PNG, previews for mip levels 0 through 8, and
`provenance.json`; the completion dialog reports that provenance path. The
provenance re-hashes the source before and after, records that the archive was
opened read-only and never written, and labels selector uses only as `bank 0`
or `bank 1`. Home/away orientation remains explicitly unproved.

Current GUI workflow:

1. Create an APF 2K8 project, select the user-owned retail `0A` file, and run
   **Hash / Recognize**. Dispatch requires SHA-256
   `dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e`.
2. Select **APF jersey PNG writer**. **Create Typed Recipe…** asks for asset
   `0..23`, validates an exact 1024×1024 stored-RGBA PNG, exclusively creates
   canonical JSON, and imports it. **Import Typed Recipe / Project…** accepts an
   already-authored canonical recipe. Both use the same typed-binding path.
3. Choose a new output `0A` path. The editor derives
   `<output>.vcmod-manifest.json` and `<output>.vcmod-artifacts`; output,
   manifest, and artifact directory must all be absent, mutually distinct, and
   outside the source/recipe/PNG paths.
4. **Typed Validate** rechecks canonical JSON plus the PNG's regular-file
   identity, dimensions, mode, and decode without writing game data.
5. **Typed Build + Independent Verify** re-hashes the exact retail `0A`, invokes
   `tools/apf_jersey_family_patch.py` through fixed argv and `shell=False`, and
   creates a new copied `0A` plus manifest. It then starts the separate
   `tools/apf_jersey_family_verify.py` process.
6. The verifier independently checks the selected catalog/outer entry,
   manifest, decoded nine-level BC3 texture against the PNG-derived mip chain,
   source/output equality outside the fixed target span, output hash, and a
   second source hash/identity check. Only hashes and metrics are written to the
   new artifact directory.

The provider pins the exact registry classification, module, sole retail hash,
selector contract, recipe-schema SHA-256, and every file in the writer and
verifier's seven-file recursive local import closure. The four APF uniform
providers use the same descriptor-read/private-stage boundary; their exact
jersey, pants, helmet, and shoulder closure sizes are 7, 8, 7, and 8 files.
Pinned modules, schemas, recipes, PNGs, and sources must be singly linked as
well as regular non-symlinks. The registry command is descriptive and is never
executed. Runtime visibility is not upgraded by this provider: transport is
proved for all 24 assets, while positive runtime evidence remains separately
scoped to asset 6.

## Usable typed provider: APF 2K8 pants colors 00–23

`apf2k8.uniforms.pants_color_00_23` dispatches through provider
`apf2k8-pants-color-v1`. Its canonical
`apf2k8_pants_color_recipe/v1` document contains only `schema`, an integer
`asset_index` in `0..23`, and a PNG path. The public contract is
[`apf_pants_recipe.schema.json`](../../mod_editor/apf_pants_recipe.schema.json).
Raw offsets, outer indices, allocation sizes, codec controls, and extra fields
are refused.

The GUI's **Create Typed Recipe…** flow requires an exact opaque 512x512 RGBA
PNG. It rejects any transparent pixel because the bounded writer implements
only DXT1 opaque four-color mode. The same canonical recipe can instead be
created headlessly or imported from another mod author. All routes bind the
recipe to this capability only; they do not enable generic queued commands.

After the user selects and recognizes the pinned retail `0A`, chooses a new
output path, and imports or creates the recipe:

1. **Typed Validate** rechecks the exact registry contract, pins the writer,
   independent verifier, and recipe-schema file by SHA-256, opens the source
   read-only, and validates canonical JSON plus PNG identity, dimensions,
   stored mode, decode, and full opacity.
2. **Typed Build + Independent Verify** invokes
   `tools/apf_pants_family_patch.py` using fixed argv, closed stdin, and
   `shell=False`. It creates only a new copied `0A` and manifest.
3. A separate `tools/apf_pants_family_verify.py verify` process resolves the
   recipe again, reparses the copied H7A/IFF, independently decodes all eight
   BC1 levels, proves inactive mip bytes and all three normal maps unchanged,
   and compares the source/output bytes outside the selected fixed allocation.
4. Verification creates a new exclusive artifact directory containing only
   sorted JSON hashes and error metrics—never game or replacement bytes.

Physical pants assets are genuinely shared: only 11 of the 24 assets are
selected by the retail ROST, across 80 team/bank uses. The recipe selects a
physical asset and therefore affects every listed owner; it does not redirect
selectors or promise a private per-team texture. The writer and verifier prove
offline transport for all 24 assets. Runtime visibility is not proved, and the
deterministic proof-quality DXT1 compressor is not presented as a production
art compressor.

## Usable typed provider: APF 2K8 helmet two-channel assets 00–23

`apf2k8.uniforms.helmet_color_00_23` dispatches through provider
`apf2k8-helmet-color-v1`. Its canonical
`apf2k8_helmet_color_recipe/v1` document contains only `schema`, integer
`asset_index` in `0..23`, and a PNG path. The public contract is
[`apf_helmet_recipe.schema.json`](../../mod_editor/apf_helmet_recipe.schema.json).
No recipe field can name raw offsets, archive entries, codecs, channel
semantics, or command-line arguments.

The PNG contract is intentionally narrower than the jersey and pants paths:
exact 256x1024 stored RGBA, arbitrary R/G data, every B sample equal to zero,
and every A sample equal to 255. The resource name is `helmet_color`, but the
runtime meanings of R and G are not proved. The GUI, recipe creator, provider,
and independent verifier therefore present them only as raw stored channels;
they do not call them paint, diffuse color, a material mask, or normals.

After source recognition and exclusive output selection:

1. **Create Typed Recipe…** and the headless creator reject nonzero B,
   non-255 A, the wrong stored mode or dimensions, symlinks, extra fields, and
   indices outside `0..23`.
2. **Typed Validate** rechecks canonical JSON and the complete raw-channel PNG
   contract. The provider hash-pins the writer, separate verifier, schema,
   sole retail `0A`, exact registry backend, and selector contract.
3. **Typed Build + Independent Verify** runs
   `tools/apf_helmet_family_patch.py` with fixed argv, closed stdin, and
   `shell=False`, creating a new copied `0A` and manifest only.
4. A separate `tools/apf_helmet_family_verify.py verify` process resolves the
   recipe again, reparses the copied H7A/IFF, independently decodes all seven
   DXN levels, and proves `helmet_normal`, both DRAM descriptors, the footer,
   inactive mip bytes, and everything outside the selected allocation remain
   unchanged.
5. The verifier exclusively creates the requested artifact directory with one
   canonical JSON report containing hashes and error metrics only. It contains
   no retail, compressed, decoded, or replacement image bytes.

Only six physical helmet assets are selected by the retail ROST and every one
is shared; asset 16 has 34 team/bank owners. This provider edits the selected
physical asset and warns through the named sharing inspector. It neither
redirects selectors nor provides per-team de-aliasing. Offline transport is
proved for all 24 assets, but changed-helmet runtime visibility and both R/G
channel meanings remain unproved.

## Usable typed provider: APF 2K8 shoulder colors 00–23

`apf2k8.uniforms.shoulder_color_00_23` dispatches through provider
`apf2k8-shoulder-color-v1`. **Create Typed Recipe…** and the headless creator
emit canonical `apf2k8_shoulder_color_recipe/v1` JSON for one named asset index
in `0..23` and one exact 1024x1024 RGBA shoulder-color PNG. The provider
hash-pins the recipe schema, copy-only writer, separate verifier, sole retail
`0A`, exact registry backend, and selector contract.

**Typed Validate** independently parses the canonical recipe and PNG. **Typed
Build + Independent Verify** then runs `tools/apf_shoulder_family_patch.py`
with fixed argv, closed stdin, and `shell=False`, creating only a new copied
`0A` and manifest. A separate `tools/apf_shoulder_family_verify.py verify`
process reparses the copied archive and all nine tiled BC3 levels, including
the packed tail. It proves that the complete DRAM block, region map, two
sideline textures, inactive mip bytes, footer, paired shoulder-normal package,
and every byte outside the selected allocation remain exact. The verifier
exclusively creates a hash/metrics-only artifact directory; every overflow,
existing output, symlink, or input/output alias is refused.

Selector slot 11 is genuinely shared. Fourteen physical assets serve 80
team/bank rows, and asset 8 has 36 owners. The named GUI/CLI inspector lists
that fan-out before editing without exposing selector offsets or implying a
selector writer. The provider changes the shared physical color asset only.
Runtime visibility, production BC3 quality, shoulder-normal semantics, and
per-team de-aliasing remain unproved.

The machine-readable APF uniform texture specification freezes the outer
archive, IFF, H7A, TXTR, Xenos transport, per-slot mip/allocation, strict PNG,
preservation, selector-sharing, and claim boundaries without retail pixels.
The canonical document is
[`apf2k8_uniform_texture_formats.v2.json`](../../reports/specs/apf2k8_uniform_texture_formats.v2.json);
the earlier three-family v1 remains immutable.
`tools/validate_apf_uniform_texture_format_spec.sh` independently refuses
drift in every pinned family report.

## Usable typed provider: APF 2K8 shared digital font

`apf2k8.scorebug_presentation.digital_font` dispatches through provider
`apf2k8-digital-font-v1`. **Create Typed Recipe…** and the headless creator
emit canonical `apf2k8_digital_font_recipe/v1` JSON for one exact 128x128 RGBA
PNG. Every RGB sample must be solid-white RGB; only the PNG's 8-bit alpha plane
is stored. The recipe records the PNG size and SHA-256 plus an independent
alpha-plane SHA-256. It contains no archive offsets or executable addresses.

The capability scope is deliberately `shared-global-ui`, not a field-scorebug
claim. Before recipe creation the GUI presents an explicit warning that the
texture can affect unknown menus, overlays, replays, or other consumers. The
provider retains that warning during validation and build rather than
presenting this as a scorebug-only edit.

**Typed Validate** independently parses the canonical recipe, rejects
duplicate/noncanonical JSON, and rechecks the PNG contract and both content
pins. **Typed Build + Independent Verify** runs
`tools/apf_digital_font_patch.py` with fixed argv, closed stdin, and
`shell=False`. The provider hash-pins its recipe schema, format specification,
writer, independent verifier, layout/transport/DXT5A/archive modules, canonical
registry backend, and the sole supported retail `0A` revision. Every pinned
path must remain safely workspace-relative beneath non-symlink directories and
name a bounded single-link regular file. The eight-file Python closure is
copied from the verified descriptor bytes into a private staged tree before
each validate/build/verify process, eliminating repository pathname
substitution after hashing.

The writer rebuilds the complete 46,637,056-byte decoded VRAM block inside
`global.iff` and creates only a new copied `0A` plus manifest. A separate
`tools/apf_digital_font_verify.py verify` process proves the source/output
boundary, stored DRAM/SRAM, footer, decoded VRAM outside the target, all 750
unrelated logical parts, and volume bytes outside the fixed outer allocation.
It exclusively creates a hash/metrics-only artifact directory; existing
outputs, aliases, symlinks, nonwhite RGB, wrong dimensions, or malformed alpha
contracts fail closed.

The route's runtime visibility is not proved, nor are the full set of global
consumers, Xenia/hardware behavior, or production perceptual encoder quality.
The current encoder is retained as an inspectable offline transport proof, not
advertised as a production art compressor.

Still `PORTME` for dispatch:

- every still-unmapped APF uniform family and any ROST selector/allocation
  writer needed for per-team texture de-aliasing;
- generic individual queue entries outside the imported unified recipe;
- audio outside the one fixed NFL `menu-back_01` cue, plus general model,
  stadium-geometry, schedule/save, and other extract/mapped surfaces without a
  typed writer provider; both catalog-backed
  SCNE position dispatchers plus the pinned NFL geometry and APF topology
  same-footprint writers remain hidden CLI proof rows; and
- all gameplay sliders, drops, CPU/draft AI, APF presentation outside the
  shared `digital_font`, scorebug
  geometry/behavior, mode routing,
  franchise restoration, and cross-title conversion research rows.

## Run and test

From the repository root:

```bash
python3 -m mod_editor --check-registry --require-registry
python3 -m unittest discover -s tests/mod_editor -p 'test_*.py' -v
python3 -m unittest -v tests/apf_jersey_family_verify_test.py
tools/validate_mod_editor_scaffold.sh
tools/validate_all_mod_editor_capabilities.sh
tools/validate_apf_jersey_family_export.sh
tools/validate_apf_jersey_typed_provider.sh
tools/validate_apf_pants_typed_provider.sh
tools/validate_apf_helmet_family_patch.sh
tools/validate_apf_helmet_typed_provider.sh
tools/validate_apf_shoulder_family_patch.sh
tools/validate_apf_shoulder_typed_provider.sh
tools/validate_apf_digital_font_typed_provider.sh
tools/validate_apf_uniform_texture_format_spec.sh
tools/validate_apf_scne_static_format_spec.sh
tools/validate_apf_stadium_static_position_patch.sh
tools/validate_apf_stadium_static_target_catalog.sh
tools/validate_apf_stadium_catalog_position_patch.sh
tools/validate_apf_stadium_node17_topology.sh
tools/validate_nfl_scne_static_format_spec.sh
tools/validate_nfl_stadium_group36_position_patch.sh
tools/validate_nfl_stadium_static_target_catalog.sh
tools/validate_nfl_stadium_catalog_position_patch.sh
tools/validate_static_topology_conformance_spec.sh
tools/validate_nfl_stadium_group36_geometry_patch.sh
tools/validate_nfl_upper_deck_changed_count_spec.sh
tools/validate_nfl_stadium_group36_geometry_xiso.sh
tools/validate_nfl_group36_xemu_runtime_result_v2.sh
tools/validate_nfl2k5_scorebug_typed_provider.sh
tools/validate_nfl_menu_back_audio_modding.sh
tools/validate_mod_editor_gameplay_inspection.sh
tools/validate_mod_editor_presentation_inspection.sh
tools/validate_nfl2k5_xbox_save_inventory.sh
tools/validate_nfl2k5_ps2_fixture_audit.sh
tools/validate_main_menu_named_inspector.sh
tools/validate_nfl_main_menu_label_patch.sh
python3 -m mod_editor
```

The registry and scaffold gates check structure, exposure policy, provider
routing, and focused tests. `validate_all_mod_editor_capabilities.sh` is the
exhaustive evidence gate: it derives a plan from the canonical registry and
runs each unique non-null `validation_command` once. Shared validators are
credited to every capability that names them; only `unknown` or
`unsafe/deferred` rows may remain without an executable validator. The runner
accepts `--report /absolute/NEW.json` for an atomic, exclusive-create,
mode-`0600` v3 receipt; that new path must be outside the repository snapshot
tree so publication cannot invalidate the manifest it records. The Linux v3
publisher writes and fsyncs anonymous `O_TMPFILE` storage, then commits it with
one no-replace `/proc/self/fd` hard link through a root-to-parent pinned
descriptor chain. It never path-unlinks a destination after that commit. A
post-link failure or interrupt can therefore leave a complete receipt even
though the runner does not print its success marker; consumers must require the
marker as well as validate the receipt. The v3 receipt records this publication
contract, the fixed scrubbed environment, timeout, pinned launchers, every audited
host command directly used by the 42-validator shell closure and its repository
tools, each command's PATH lookup leaf and complete symlink chain, the resolved
executable bytes and lstat identity, the registry/runner/schema root of trust,
all validator results, and deterministic
control/evidence file manifests. The small control manifest is checked around
every validator and the larger evidence manifest across the complete run.
Retail images, build trees, emulator disks, and other excluded bulk artifacts
remain authenticated by the focused validators that consume them. Timeout
cleanup addresses the validator's complete original process group even when its
leader exits before a TERM-ignoring descendant. A validator that deliberately
creates a new session with `setsid` has crossed the runner's process-group
boundary; the fixed, snapshotted validator set is trusted not to detach work.
These boundary snapshots detect ordinary drift; they do not claim filesystem
isolation against a hostile dependency swap-and-restore occurring wholly
between two checks. Publication rechecks every pinned directory component and
the final leaf after the directory fsync, but that remains a point-in-time
claim: a writer authorized to modify the report directory can later replace or
remove the receipt. Shared libraries and subprocesses internally selected by a
captured compiler, `make`, `cmake`, media tool, or JDK remain part of the trusted
system-tool boundary; the receipt does not claim recursively hermetic host
execution. The runner also refuses shell syntax, unreviewed launchers,
symlinked or hard-linked control files, unsafe report ancestry, and validation
paths outside `tools/`.

The editor tests use tiny synthetic files, mocks, and fake/recording
providers. They
do not launch xemu/Xenia, modify a retail input, or build/copy a game-sized
image. They cover source hashing, recognition, project round trips, schema
rejection, queue gates, raw-offset rejection, byte-identical staging output,
overwrite/symlink refusal, fixed argv construction, provider allowlisting,
stage ordering, build-failure verify suppression, provider-binding
persistence/replacement, post-job capability-action restoration, and exclusive
canonical recipe generation for the simple workflows across both games. The
provider-integrity tests additionally derive each external backend's recursive
local import closure, verify all closure/schema hashes, reject hardlinks,
exercise exact unified authorization and source-record identity, and prove a
private execution bundle continues to run the hashed bytes after the original
workspace module and dependency paths are replaced. The
fixed NFL audio tests additionally enforce its exact PCM shape, content pins,
fixed writer/verifier argument vectors, provider/module fail-closed behavior,
and metadata-only verification receipt without creating a retail-sized copy.
The APF digital-font tests likewise enforce its exact alpha-only PNG contract,
canonical content-pinned recipe, shared-global warning, fixed writer/verifier
argument vectors, all owning-module pins, independent parser boundary, and
hash/metrics-only artifact receipt. They reject nonwhite RGB, wrong dimensions,
malformed alpha content, source drift, and output collisions.
The focused editor export tests
mock the APF backend while checking fixed inputs, absent-output refusal,
display-free GUI gating, background dispatch, provenance reporting, and the
absence of raw selector arguments. They also cover report hash/size pins,
named-only gameplay/menu queries, negative APF draft ownership, sanitized
franchise output, uniform-owner prompts, and GUI inspector dispatch. Separate
APF backend-verifier tests use
tiny copy spans, a synthetic nine-level texture, and one in-memory retail jersey
entry; they never create a retail-sized output copy.

The read-only export and recipe creators are available without a display:

```bash
python3 -m mod_editor --export-apf-jersey new-jersey-export \
  --source-0a "/games/All-Pro Football 2K8 (USA)/0A" --asset-index 6

python3 -m mod_editor --create-apf-jersey-recipe my-jersey.json \
  --asset-index 6 --jersey-png jersey.png

python3 -m mod_editor --create-apf-pants-recipe my-pants.json \
  --asset-index 13 --pants-png pants-opaque.png

python3 -m mod_editor --create-apf-helmet-recipe my-helmet.json \
  --asset-index 16 --helmet-png helmet-rg-data.png

python3 -m mod_editor --create-apf-shoulder-recipe my-shoulder.json \
  --asset-index 8 --shoulder-png shoulder-color.png

python3 -m mod_editor --create-apf-digital-font-recipe my-apf-font.json \
  --apf-digital-font-png white-rgb-alpha-font.png

python3 -m mod_editor --create-nfl-scorebug-recipe my-scorebug.json \
  --score-buga-png frame.png --shield-espn-png espn.png \
  --digital-font-png digits.png

python3 -m mod_editor --create-nfl-menu-back-audio-recipe my-menu-back.json \
  --purpose "Replace the fixed menu-back cue" --audio-wav menu-back.wav

python3 -m mod_editor --inspect-nfl-uniform-sharing 10H5
python3 -m mod_editor --inspect-apf-jersey-sharing 23
python3 -m mod_editor --inspect-apf-pants-sharing 13
python3 -m mod_editor --inspect-apf-helmet-sharing 16
python3 -m mod_editor --inspect-apf-shoulder-sharing 8
python3 -m mod_editor --inspect-gameplay-sliders nfl2k5
python3 -m mod_editor --inspect-gameplay-sliders apf2k8
python3 -m mod_editor --inspect-draft-priority nfl2k5
python3 -m mod_editor --inspect-draft-priority apf2k8
python3 -m mod_editor --inspect-nfl-franchise-limit all
python3 -m mod_editor --inspect-nfl-save-inventory
python3 -m mod_editor --inspect-main-menu nfl2k5
python3 -m mod_editor --inspect-main-menu apf2k8
```

The inspection commands are read-only and named. Uniform queries expose exact
affected owners; NFL equal-content selectors have independent fixed XISO spans,
while APF jersey, pants, helmet, and shoulder assets are genuinely shared. APF jersey
selectors now have a fail-closed, independently verified offline CLI remap writer; it remains
hidden from the production GUI until a matched runtime witness. The one exact
deterministic 24-built-in plan for all eleven filename-owned families now also
has a fail-closed offline writer and separate verifier, but it remains hidden,
admits no arbitrary family recipe, and has no non-jersey runtime witness.
Gameplay, save, and menu queries deliberately remove raw offsets,
return the underlying report identity, and distinguish mapped evidence from a
safe writer.

## Next implementation boundary

The simple APF jersey, pants, helmet two-channel, shoulder-color, NFL scorebug,
and fixed NFL menu-back audio workflows now generate canonical recipes
inside the GUI and CLI, the APF jersey workflow exports the proved jersey plus all
nine mip previews with selector provenance, and mapped gameplay/menu evidence
is directly inspectable. APF shoulder editing also retains its exact shared-
owner inspector and warning boundary. The machine-readable NFL/APF SCNE
specifications now back catalog dispatchers for 75 NFL and 77 APF stadium-SCNE
targets with second-target byte proofs. NFL `group36` also has a pinned same-
footprint four-position/four-index native-quad loop and a proved one-span copied-
XISO transport. A later exact control/expanded diagnostic selected
`s42nd.iff` in xemu 0.8.135 and made its independently verified authored wall
visibly affect rendering. That runtime proof is intentionally limited to the
pinned diagnostic: it is not pixel-aligned, has no GPU trace, modifies XBE
routing without preserving the retail RSA-signed chain, and proves neither
original hardware nor production/distribution readiness. APF node17 has a
separate pinned four-BE16 native-strip permutation writer. NFL
`upper_deck` now has a machine-readable changed-count boundary and in-memory
count-4/count-8 fixed-span probes, but no changed-count archive writer or
verifier. Counts for every shipping writer, materials, and attributes remain
fixed. The next mesh boundary is the APF node17 runtime witness and then a
separately verified NFL source-vertex-subset count writer without inventing
opaque attributes. The current mesh writers—including the runtime-proved but
diagnostic-only NFL row—remain hidden CLI proofs, not editor providers. New
providers should
still be added one at a time. A provider may be enabled only when it has fixed
arguments, exact source and schema gates, exclusive output ownership, and an
independent verifier; the generic queue will not become an arbitrary command
runner.

## Existing backend reconnaissance

The first scaffold inspected the local Python entry points without running a
game or modifying a retail source. The following backend families already use
copy-only destinations and are candidates for future typed adapters:

| Game | Surface | Existing entry point shape |
|---|---|---|
| NFL 2K5 | jersey, pants, sleeves | source XISO + named team/side/variant + PNG + new XISO/manifest/preview |
| NFL 2K5 | Team Select cards | source XISO + bounded JSON plan + new XISO/manifest/preview |
| NFL 2K5 | live helmet textures | source XISO + bounded JSON plan + new XISO/manifest/preview |
| NFL 2K5 | live face textures | source XISO + bounded JSON plan + new XISO/manifest/preview |
| NFL 2K5 | player portraits | source XISO + bounded JSON plan + new XISO/manifest/preview |
| NFL 2K5 | create-team field art | source XISO + bounded JSON plan + new XISO/manifest/preview |
| NFL 2K5 | live numbers/nameplates | source XISO + bounded JSON plan + new XISO/manifest/preview |
| NFL 2K5 | catalog stadium positions | user-owned archive index + one of 75 catalog target IDs + exact-count positions + new copied volume 9/manifest; hidden, no typed provider |
| NFL 2K5 | pinned stadium/group36 same-footprint geometry | user-owned archive index + four positions/four native-quad IDs + new copied volume 9/manifest, followed by an exact one-span layout-identical copied-XISO transport; one exact xemu diagnostic is visibly proved, but the path remains hidden with no typed provider or production/distribution claim |
| APF 2K8 | jersey family | user-owned volume `0A` + catalog asset index + PNG + new entry/volume/manifest |
| APF 2K8 | proved jersey mip chain | user-owned volume `0A` + 1024×1024 RGBA PNG + new entry/volume/manifest |
| APF 2K8 | catalog stadium positions | complete user-owned four-pack directory + one of 77 catalog target IDs + exact-count positions + new copied `1A`/manifest; hidden, no typed provider |
| APF 2K8 | pinned stadium/node17 same-footprint topology | complete user-owned four-pack directory + one four-ID BE16 strip permutation + new copied `1A`/manifest; hidden, no typed provider |

This inventory does not upgrade any feature's proof level. In particular,
offline byte-accurate writing and emulator-visible runtime proof remain
separate registry classifications. The GUI follows the registry, not this
table.

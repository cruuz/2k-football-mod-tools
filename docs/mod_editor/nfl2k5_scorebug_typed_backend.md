# NFL 2K5 typed scorebug backend

`tools/nfl2k5_scorebug_mod_project.py` is the canonical backend for composing
the proved NFL 2K5 scorebug texture edits into one XISO copy. The public editor
dispatches it only through typed provider `nfl2k5-scorebug-v1`; the backend
itself remains GUI-independent.

## Supported targets

| Project target | Exact PNG size | Scope |
| --- | ---: | --- |
| `score_buga` | 64×64 | Field-scorebug frame/corner atlas; nine compiled material bindings use it. |
| `shield_espn` | 128×64 | ESPN strip; two compiled field-scorebug bindings use it. |
| `digital_font` | 128×128 | Shared/global font atlas; edits can affect UI outside the field scorebug. |

A project contains one to three edits. A target can occur at most once. The
backend intentionally has no user-controlled offsets, archive names, texture
formats, swizzle modes, compression settings, or replacement span paths.

## Canonical recipe

The formal JSON Schema is
[`reports/assets/nfl2k5_scorebug_mod_project.schema.json`](../../reports/assets/nfl2k5_scorebug_mod_project.schema.json).
The executable validator additionally requires byte-for-byte canonical JSON:
two-space indentation, sorted object keys, one trailing newline, no extra
fields, and no duplicate target selectors.

Each edit pins a regular, non-symlink PNG by path, byte size, and SHA-256. The
top-level `source` object pins the retail XISO, `default.xbe`, extracted pack 0,
and scorebug audit. The checked-in three-target example is
[`reports/assets/nfl2k5_scorebug_mod_project_example.json`](../../reports/assets/nfl2k5_scorebug_mod_project_example.json).

Validate the schema, PNG pins, exact dimensions, fixed-span compression fit,
and strict round trip:

```sh
python3 tools/nfl2k5_scorebug_mod_project.py validate \
  --project reports/assets/nfl2k5_scorebug_mod_project_example.json
```

## Build one copy with all selected edits

Every output path must be absent. The retail XISO is opened read-only. The
builder exclusively creates one full copy, writes every selected fixed TXTR
span into it, then performs a byte-for-byte full-image comparison against the
retail source.

```sh
python3 tools/nfl2k5_scorebug_mod_project.py build \
  --project my-scorebug-project.json \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --output-xiso build/my-scorebug.xiso.iso \
  --manifest build/my-scorebug.build.json \
  --artifact-dir build/my-scorebug-artifacts
```

The artifact directory contains only reconstructed preview PNGs and import
reports. Replacement game spans are not exported as distributable sidecars.
The manifest records the exact union of allowed differences, XDVDFS identity,
unchanged `default.xbe`, inputs, output identity, and safety claims.

## Independent verification

```sh
python3 tools/nfl2k5_scorebug_mod_project.py verify \
  --project my-scorebug-project.json \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --output-xiso build/my-scorebug.xiso.iso \
  --manifest build/my-scorebug.build.json \
  --artifact-dir build/my-scorebug-artifacts
```

Verification does not obtain targets, offsets, spans, or artifact hashes from
the build manifest. It rereads the canonical recipe, repins the PNGs, reruns
the strict importers, binds their audit-owned offsets to the pinned retail
XISO, reconstructs the complete changed-byte union, compares all 6.3 GB, and
reconstructs every artifact. Only after that does it require the manifest to
equal the independently reconstructed proof. A forged manifest, PNG, symlink,
extra artifact, changed output byte, non-retail source, or path alias fails.

## Public editor provider

Capability `nfl2k5.scorebug_presentation.inventory` is mapped to
`Nfl2k5ScorebugProvider`. The provider never executes the registry command
string. It pins the backend module hash, exact retail XISO fingerprint and
size, canonical source-pin object, target selector contract, PNG size/hash and
regular-file identities, and three absent output paths. It constructs fixed
argument vectors with `shell=False` for `validate`, `build`, and `verify`.

In the GUI, create an NFL 2K5 project, hash/recognize the retail XISO, select
**NFL 2K5 scorebug texture editor**, import canonical
`nfl2k5_scorebug_mod_project/v1` JSON, choose a new output XISO, then run
**Typed Validate** or **Typed Build + Independent Verify**. The provider never
turns the generic named-asset queue into a command and never launches xemu.

## Worked

- All three strict PNG importers pass the canonical example.
- Multi-target spans are non-overlapping and can be composed into one copy.
- The retained single-target XISO proof still passes its independent full-disc
  verifier: exactly 2,169 changed bytes and every byte outside the target set
  identical.
- Unit tests cover canonical encoding, target uniqueness, source-pin forgery,
  PNG-pin forgery, symlink refusal, artifact reconstruction, and changed-byte
  ledger helpers.

## Failed or unproved

- `score_buga` and `shield_espn` have separate positive xemu demo-gameplay
  proofs. Those exact results do not prove SCNE behavior or other contexts.
- A changed magenta `digital_font` candidate booted, but one no-input frame
  containing the field HUD and offense lower third had zero magenta diagnostic
  pixels. The shared atlas is writable but its visible consumer route and
  global side effects remain unproved; this is not evidence that it is dead.
- This backend does not serialize `score_bug` SCNE geometry and does not move,
  resize, recolor, or restyle scorebug layout elements.
- This NFL backend does not write APF 2K8 DXT5A textures or SCNE packages.

## Blocking / PORTME

- `PORTME(runtime)`: locate a menu or other route that visibly exercises
  `digital_font` and inspect its global side effects. The bounded positive
  results are documented in
  [`nfl_scorebug_xemu_runtime.md`](../research/nfl_scorebug_xemu_runtime.md) and
  [`nfl_scorebug_shield_xemu_runtime.md`](../research/nfl_scorebug_shield_xemu_runtime.md);
  the route-specific negative result is in
  [`nfl_scorebug_font_xemu_runtime.md`](../research/nfl_scorebug_font_xemu_runtime.md).
- `PORTME(NFL SCNE 346:78)`: implement a validated SCNE serializer before
  attempting geometry/layout edits.
- `PORTME(behavior)`: compiled scorebug timing, visibility, and presentation
  behavior require separately audited executable patches; this texture backend
  must not guess those fields.

Run the non-destructive backend validator with:

```sh
tools/validate_nfl2k5_scorebug_mod_project.sh
```

# High-resolution texture authoring: exact capability boundary

## What is supported

The editors can preserve a user's original full-resolution image without
changing it, store a deterministic Photoshop-style placement transform, compile
an exact native-size RGBA PNG, and render a 2x or 4x authoring preview directly
from the original. The portable `.2ktexmaster` bundle implemented in
`mod_editor/core/texture_master.py` contains:

- `master.source`: the exact imported bytes, including the original image
  encoding and full pixel dimensions;
- `manifest.json`: asset/editor identity, source hashes, native dimensions,
  placement centre, independent width/height, rotation, and sampling mode;
- `native.png`: the only image intended to cross an existing proved game
  texture writer;
- `native-before-editor.png` (only after in-app pixel painting): the exact
  native canvas immediately after the external import, used to identify the
  user's later native-pixel edits without replacing the full-resolution source;
- `preview-4x.png` (or `preview-2x.png`): an authoring preview rendered from the
  full-resolution master, never an enlargement of `native.png`. After in-app
  pixel painting, only changed native pixels are overlaid with nearest-neighbour
  semantics; untouched pixels remain the direct master render.

The native target remains exact. A 512x512 APF crest still compiles to 512x512;
a 64x64 NFL 2K5 texture still compiles to 64x64. The 4x preview keeps source
detail available for future compilers and makes transform review less jagged,
but it does not make the current disc texture 4x larger.

For ordinary literal-colour textures, the bundle can render `native.png`
itself. For game-specific compilation, pass the already validated native PNG as
`compiled_native_png`. That is the correct route for APF's full-shell helmet
design: the preserved master can be a normal painted logo, while `native.png`
is the separately confirmed 512x512 semantic red/green region mask. The
manifest labels this `supplied-game-compiled` and labels the 4x image
`authoring-preview-only`; it never presents literal painted colours as the
bytes the APF shader consumes.

Full-shell designs must also carry an opaque shell body: every zero-RGB texel
needs alpha 255. The retail 8/15 crest transport sentinel (alpha `0x88`)
belongs to the bounded side-decal lane; left on the routed full-shell surface
it renders the shell semi-transparent in game. The writer and the GUI both
normalize and validate this contract, and the bake receipt records
`opaque_shell_body_contract`.

Archives never overwrite an existing destination, reject links and undeclared
ZIP members, bound compressed and expanded sizes, hash every payload, and
re-render the high-resolution preview on load to prove the source and transform
still agree. They contain user artwork and derived output only, not a retail
original or game image.

## Editor wiring and exact coverage

Both editors show **Save high-resolution authoring master…** next to the
relevant import controls. It is enabled only after that asset received an
external import in the current session. The import is copied immediately to a
private, bounded session snapshot, so changing or deleting the original file
afterward cannot silently change the bundle. Those temporary snapshots are
removed on re-import, Revert, source/project switch, or editor close.

APF 2K8 supports this action in **Team logo — helmet crest** for Retail and
Full-shell coverage. The archive retains ordinary painted art or an advanced
region-mask original, the exact original-to-contain-to-placement transform,
palette/semantic conversion metadata, final X/Y, independent width/height and
rotation, and the exact staged 512x512 semantic mask. The painted 4x preview is
authoring output; `native.png` is still the semantic image consumed by the
proved Xbox 360 writer. In-app pixel edits retain the original master and are
recorded as a native-canvas raster layer instead of discarding or pretending to
reverse those edits.

NFL 2K5 supports the action in the shared **Extended Visual** browsers:
Portraits & Faces, Create-a-Team Field Art, Scorebug Presentation, and All
Textures (`p8_texture` and `uniform_equipment_texture`). File-dialog and drop
imports share the same resize/convert path. Exact-size JPEGs and non-RGBA PNGs
are converted to RGBA PNG only after confirmation; the supplied file stays
unchanged. The archive receives the exact original bytes, the exact Lanczos
scale/cover crop or pass-through metadata, and the session's exact staged
native PNG. In-app painting over an imported master records the same explicit
native-pixel edit layer used by APF.

The action is not presented on 2K5 surfaces whose current controller does not
retain both the exact external source and a composable final transform: the
Uniform Sets component browser, Stadium specialist, Team Kit batch workflow,
and project-loaded replacements. This is a data-integrity boundary, not a
claim that those formats cannot eventually support masters.

Both current project formats intentionally contain only exact native
replacements. Loading a `.2k5mod` or `.apf2k8mod` therefore cannot reconstruct a
full-resolution source. `.2ktexmaster` is the explicit, non-overwriting
portable sidecar; adding it to either project requires a separately versioned
project migration rather than undeclared archive members. A built-in edit made
only from retail source pixels does not enable authoring-master export, because
that would package source-derived game art as if it were user-authored.

## RPCS3 and 4x rendering

RPCS3 export is intentionally unavailable. In the official RPCS3 source
snapshot audited for this work, the video configuration exposes **Use GPU
texture scaling** and **Resolution Scale**, but it exposes no supported custom
texture replacement/dump contract or replacement filename scheme
([official `system_config.h`, pinned commit](https://github.com/RPCS3/rpcs3/blob/a6d07c0e55b908d706614701670329ebf73aa4c8/rpcs3/Emu/system_config.h#L140-L166)).
The official settings enumeration likewise contains GPU texture scaling and
resolution scale, not a texture-pack interface
([official `emu_settings_type.h`, pinned commit](https://github.com/RPCS3/rpcs3/blob/a6d07c0e55b908d706614701670329ebf73aa4c8/rpcs3/rpcs3qt/emu_settings_type.h#L72-L90)).

Resolution scale increases the resolution of rendered geometry/framebuffers;
it does not replace a game's source texture with the 4x preview. In addition,
this repository's APF writer and texture catalogs are source-proved against the
Xbox 360 `0A` volume. They do not contain a proved PS3 APF texture identity,
hash, RSX upload, or replacement-name mapping. Producing an RPCS3 folder today
would therefore be invented output. `require_rpcs3_texture_replacement_export`
fails with that exact explanation instead.

An RPCS3 exporter can become editable only after both boundaries exist:

1. an official RPCS3 custom-texture replacement contract with stable naming;
2. a local, source-derived APF PS3 mapping that identifies every intended
   texture consumer, including menu logos separately from in-game helmet art.

Until then, use the 4x file for authoring/inspection and `native.png` for the
existing proved Xbox/Xbox 360 game writer.

# APF 2K8 logo-surface ownership

Research date: 2026-08-03  
Scope: static archive/XEX ownership and the current Mod Studio write contract.
No emulator, controller, FIFO, or game runtime was used for this audit.

## Result

The reported separate menu logo was already found. APF stores the same
512×512 crest in two independent places, and the current **Team Logo** action
edits both of them in one copied `0A`:

1. the selected `uniform_logo_NN.iff` package, inner `logo_l0` and `logo_l1`;
2. the separately loaded `uniform_logocache` aggregate, entries
   `NN_logo_l0` and `NN_logo_l1`.

The second owner is the frontend path. XEX function `0x8467C978` loads
`uniform_logocache.iff`. Function `0x84688690` formats `logo%s` and resolves it
in the frontend `LOGOS` group; the existing static research identifies this as
the Team Select logo grid. Mod Studio's cache writer regenerates every mip for
both matching layers and its independent verifier reopens the final copied
volume.

This is a static ownership and file-transport proof. It does not claim that a
changed logo was observed in a running game or on Xbox 360 hardware.

## Editor ownership labels

The **Team Logo** panel now names the relationship directly for the selected
crest index `N`:

- selector slot 5 links `uniform_logo_NN.iff` `logo_l0`/`logo_l1` to
  `uniform_logocache` entries `N_logo_l0`/`N_logo_l1`;
- one Team Logo build co-writes that package and the statically mapped
  frontend/Team Select cache pair;
- selector slot 6 independently selects a rectangular
  `uniform_textlogo_00..205.iff` wordmark in the **Wordmarks** tab.

The panel never squeezes the square crest into a wordmark or invents another
menu-logo reservoir. Its ownership line also retains the proof boundary:
the frontend cache path is statically mapped, but changed-logo runtime
consumption and the scorebug's package-versus-cache resolver remain unproved.

The in-game scorebug is a separate dynamic-consumer boundary. Its
`scorebug_team_logos` scene has two logo quads, two exact dynamic logo samplers,
and no embedded TXTR; all six sibling scorebug scenes' draw/material texture
routes are also closed. Static evidence does not yet distinguish whether those
two samplers receive `uniform_logo_NN` or `uniform_logocache` at runtime. Team
Logo writes both candidate reservoirs atomically, so there is no uncovered
third logo asset, but the final package-versus-cache resolver is not claimed.

## The three separate APF logo domains

| Domain | Exact storage | Current editor action | Proved meaning |
|---|---|---:|---|
| Team/helmet crest package | `uniform_logo_00.iff` through `uniform_logo_117.iff`; `logo_l0` + `logo_l1`; 512×512 Xenos `4_4_4_4` with packed mips | Yes | Team crest catalog and helmet-composite source |
| Frontend crest cache | outer 171 `uniform_logocache.iff` directory + outer 213 `uniform_logocache.cdf` payload; 118 × `{N_logo_l0,N_logo_l1}` | Yes | Statically mapped frontend `LOGOS` / Team Select cache path |
| Text wordmark | `uniform_textlogo_00.iff` through `uniform_textlogo_205.iff`; inner `textlogo_color`; 512×128 opaque DXT1 with packed mips | Yes — Wordmarks | Independently selected uniform text-wordmark family; not a duplicate square crest |

The 206 text wordmarks are selected by ROST uniform-selector slot 6. The 118
square crests use slot 5. They are separate catalogs and their indices do not
generally match. Automatically squeezing a square crest into the wordmark
would corrupt the intended aspect and would not be a truthful menu-logo fix.
The dedicated **Wordmarks** action owns all 206 indices. It accepts ordinary
art through explicit Contain or Cover fitting, flattens transparency to opaque
black, emits exact 512×128 RGBA input, rebuilds all six BC1 mip levels inside
the selected package's fixed allocation, and independently verifies the final
copied volume. This proves bounded file transport; the exact rendered consumer
and runtime appearance remain separate open evidence boundaries.

No separately named APF equivalent of NFL 2K5's standalone `unif_*`/`helm_*`
Team Select cards is proved by this audit. `frontend.iff` does contain unrelated
logo-like resources such as `fantasy_sport_logo` and `random_outer`; their
names and category are not evidence that they are per-team crest owners.

## Exact Americans / Philadelphia ownership

The built-in Americans (`PHI`, team index 0) select the same values in both
uniform banks:

- selector slot 5: crest asset 30;
- selector slot 6: text-wordmark asset 8.

The crest package is `uniform_logo_30.iff`, outer 1133, physical `0A` offset
`0x0AF59800`, fixed allocation 122,880 bytes. Its inner file order is
`logo_l1` at index 0 and `logo_l0` at index 1; the writer resolves names rather
than assuming that order.

Catalog 30's frontend-cache entries are:

| Cache name | Directory descriptor index | Aggregate slot | Payload VRAM stream |
|---|---:|---:|---:|
| `30_logo_l0` | 171 | 96 | `0x727208`, stored length `0x14941` |
| `30_logo_l1` | 178 | 97 | `0x7749D9`, stored length `0x0915A` |

The cache directory is outer 171 at physical `0A` offset `0x032C1800`; its
payload is outer 213 at `0x3DF15800`. The current Team Logo action passes the
same authored PNG to the package and cache writers, writes both l0/l1 layers,
and refuses the whole action if either writer or the independent cache verifier
fails.

The separate Americans wordmark is `uniform_textlogo_08.iff`, outer 906 at
physical `0A` offset `0x0A986000`, inner index 0 `textlogo_color`. It is
512×128 opaque DXT1, with a 32,768-byte base allocation and a 32,768-byte
packed-mip allocation. Team Logo intentionally does not edit it; **Wordmarks**
does, without changing crest package 30 or either crest-cache layer.

## NFL 2K5 comparison

NFL 2K5 really does have separate menu imagery: 1,902 standalone `unif_*` and
`helm_*` Team Select cards, distinct from live jersey and helmet textures. The
2K5 editor already includes the three relevant cards in each 39-component Team
Kit, and its unified visual writer also exposes the full 1,902-card catalog.
Changing a live uniform does not silently repaint those cards.

## Evidence

- `reports/assets/apf_uniform_inventory.json`: all 118 crest packages, all 206
  text-wordmark packages, both selector banks, and all 236 cache entries.
- `docs/research/apf_uniforms.md`: exact filename templates, ROST selector
  slots, formats, dimensions, and cache grammar.
- `docs/research/apf_helmet_surfaces.md`: frontend cache loader and `LOGOS`
  group / `logo%s` Team Select ownership.
- `tools/apf_logo_patch.py`, `tools/apf_logocache_patch.py`, and
  `tools/apf_logocache_verify.py`: the current composed copied-volume transport.
- `tools/apf_textlogo_patch.py` and `tools/apf_textlogo_verify.py`: typed
  206-slot fixed-allocation writer and independent whole-volume verifier.
- `tests/mod_editor/test_apf_team_logo_gui.py`: one Team Logo action dispatches
  package write, cache write, then independent cache verification.
- `tests/mod_editor/test_apf_textlogo_writer.py` and
  `tests/mod_editor/test_apf_textlogo_gui.py`: all-target no-op identity,
  changed-mip, whole-volume, project/build, Revert, and desktop routing coverage.

# APF 2K8 four-family runtime experiment — 2026-07-18

## Result

This bounded Xenia experiment produced **positive runtime consumption evidence
for the public jersey and pants writers** and **no positive evidence yet for
the helmet or shoulder writers**.

The negative observations are not treated as proof that helmet or shoulder
replacement is impossible. They show only that the chosen fixtures were not
visibly consumed in the inspected Americans Logo Selection and Team Package
Editor routes.

| Family | Target | Runtime result | Exact observation |
| --- | --- | --- | --- |
| Jersey | `uniform_jersey_06.iff`, outer 875 | **Positive** | Americans Home and Away Jersey Editor mannequins showed an unmistakable asymmetric pink/off-white checker treatment and distorted number/hem treatment. |
| Pants | `uniform_pants_06.iff`, outer 633 | **Positive** | With `PANTS` highlighted under Edit Away Uniform Type, the leg preview showed an unmistakable red/white/blue checker/plaid pattern. |
| Helmet | `uniform_helmet_01.iff`, outer 181 | **Not proved** | Logo Selection, Logo Editor, and Accessories Editor helmet thumbnails remained an ordinary solid-blue Americans helmet; the expected red/green mask grid was not visible. A dedicated close helmet consumer was not reached. |
| Shoulder | `uniform_shoulder_05.iff`, outer 198 | **Not proved** | With `SHOULDERS` highlighted, no high-contrast RGBA grid distinct from the modified jersey was visible. The shoulder region continued the jersey treatment. |

## Controlled inputs

The private, non-release fixtures were:

| File | SHA-256 |
| --- | --- |
| `jersey-06-asymmetric.png` | `6bd285526a9fb0f063b4938c9ab1a907d1c72eca2f23dec48ac3f1061810c436` |
| `pants-06-quadrants.png` | `cf0bbd8f925f167f8ff9a5ea32ce221de58faae598550965f38bff4176206ddc` |
| `helmet-01-rg-masks.png` | `a53a7e0c0cdbcf8740e886e4f33fd018bb2f9a563d6cdef91d3eaae55853640f` |
| `shoulder-05-material-grid.png` | `2fb434f1b947ff9456df5fac088dcbd6f0dd0c303d26223f42e90f4381cca06d` |

The replacement-only private project SHA-256 was
`b802cfa96c0f1561c5ac51854fa5ee7d442242a2c0bd93703458845505cd0bee`.
It contains no originals or complete retail resources.

The product build changed exactly outer entries `875`, `633`, `181`, and
`198`. Its built `0A` SHA-256 was
`90d9b723acf38401fd31acb11a5ac981546cb616486079a33a0c3dfd6f9d8fad`.
The untouched source `0A` remained
`dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e`
before and after the build.

## Runtime procedure

All desktop and emulator interaction was delegated to Spark on the isolated
Xvfb display `:99`; the user's active desktop and pointer were never used.
Xenia Canary ran with a fresh Wine prefix, storage, content, cache, and a
private virtual Xbox 360 controller.

The successful navigation path was:

1. Title `START`; accept the default `Player1` name.
2. Team Create: add default Gold Player 1 Dan Marino.
3. `START`, then `A`, to auto-select remaining All-Pro players.
4. `START` to enter Fill Roster; `START` again to accept Balanced.
5. Stop first at Logo Selection and inspect Americans HOME/AWAY thumbnails.
6. Accept Americans, move down three rows, and open Edit Team Package.
7. Inspect Home Jersey and Away Jersey Editors.
8. Open Edit Away Uniform Type, then inspect `SHOULDERS` and `PANTS` rows.
9. Inspect the Logo and Accessories helmet views without saving a package.

Logo Selection thumbnails did not expose the jersey fixture even though the
larger Home/Away Jersey Editor did. Therefore Logo Selection alone is an
insufficient negative test for these material textures.

## Product implications

- Promote the pants writer from offline-only to **runtime-proved** for the
  Americans Away Uniform Type preview.
- Retain the jersey writer's existing runtime-proved status and add this second
  asset/editor route as independent corroboration.
- Keep helmet and shoulder as **Editable (offline writer)** without claiming
  positive runtime visibility.
- The authoring guide must treat jersey alpha and shoulder/helmet channels as
  material inputs, not literal final screen colors.

## Next bounded experiments

1. Helmet: reach or create a dedicated close helmet consumer, then compare
   stock against two low-frequency fixtures: all-red versus all-green masks.
   Large constant channel deltas are less vulnerable to thumbnail filtering
   than an exhaustive fine grid.
2. Shoulder: keep the jersey stock, patch only shoulder 05, select several
   shoulder style cells, and test constant R/G/B/A extremes one channel at a
   time. This separates shoulder material response from jersey overlap.
3. If either editor route remains inconclusive, use one short full-body
   gameplay/uniform-code preview rather than inferring from small package
   thumbnails.

These are two targeted causal tests, not a reason to repeat the already-passed
offline writer, project, build, or source-safety validation.

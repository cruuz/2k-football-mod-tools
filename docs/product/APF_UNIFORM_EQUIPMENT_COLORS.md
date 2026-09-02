# APF 2K8 all-team uniform equipment colors

Status: exact offline ROST writer proved on the private retail source; runtime
gameplay spot check remains separate.

The Uniforms & Equipment → Equipment Colors panel edits every team slot `0..39`.
HOME and AWAY independently select one of that bank's ten existing palette
colors for:

- the facemask bar: selector slot 3, byte 6;
- players whose turtleneck choice is Team: selector slot 0, byte 2.

Each dropdown shows the palette index, a stable label, the current `#RRGGBB`
value, and a swatch. Values are limited to `0..9`. Visors remain the per-player
None/Clear/Dark choice in Save Players; no per-uniform visor-tint field is
claimed.

The writer resolves team → config → palette/selector pointers from the source,
requires aligned records and unique ownership across all 40 configs, and changes
at most four individual bytes per team. Both complete `0x30` palettes—including
opaque metadata at `+0x28..+0x2F`—and every nonselected selector byte remain
bit-exact. A source-value edit returns the original compressed entry verbatim.

Projects contain only canonical replacement JSON with the four selector indices.
The build composes this component with roster names, ratings, positions, and
custom-team appearance. If custom-team appearance and equipment colors select
the same team, the compositor refuses their overlapping selector ownership
instead of silently choosing one edit.

This game-0A feature does not widen raw-save support. Raw Roster.ROS appearance
writes remain limited to user-team slots `32..39`.

Focused checks:

```bash
python3 -m unittest -v \
  tests.mod_editor.test_apf_uniform_equipment_colors \
  tests.mod_editor.test_apf_uniform_equipment_colors_gui
```

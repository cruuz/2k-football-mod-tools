# ESPN Anniversary authoring

EXPERIMENTAL / UNWITNESSED. Noah supplies the historical player content.

The backend and new `Espn25Panel` are implemented. Mounting the panel in the
protected Rosters tab and adding the Studio build pass are the exact handoff
in `WIRING.md`. The command line works without that integration.

The 50 scenario sides use 35 shared historic files. Editing a file changes
every moment using it and that historic team outside Anniversary mode. It does
not edit the live NFL roster. Years select historic rosters; they are not merely
labels. Private copies for otherwise shared moments are deferred.

## Work with an existing moment

Use a user-owned USA Xbox image or an extracted game folder for `source`.
A loose `vc_53450030` folder or its `0` index is also accepted for inspection.
All indices in JSON and commands are **zero-based**; the panel displays 1..25.

```sh
python3 -m mod_editor.core.nfl2k5_espn25_scenarios inspect source.iso
python3 -m mod_editor.core.nfl2k5_espn25_scenarios export-csv source.iso 0 away away.csv
python3 -m mod_editor.core.nfl2k5_espn25_scenarios plan source.iso edits.json espn25-plan.json
python3 -m mod_editor.core.nfl2k5_espn25_scenarios status source.iso espn25-plan.json
python3 -m mod_editor.core.nfl2k5_espn25_scenarios build source.iso espn25-plan.json output.iso
```

`build` requires a new output file, streams through a temporary directory on the
output filesystem, verifies the result and publishes it with `os.replace` after
closing handles. It preserves the source and requires at least 100 GB remaining
free after copying. No full-size disc or pack is read into memory. Studio's
`apply_to_image` is a final pass on its own disposable output copy; discard that
copy on I/O failure. The low-level pass does not promise power-loss atomicity.

Example `edits.json`, containing only authored setup and a sparse CSV import:

```json
{
  "schema": "nfl2k5.espn25.edits.v1",
  "moments": [
    {"moment": 0, "setup": {"home_score": 14, "away_score": 17, "clock_seconds": 290}}
  ],
  "rosters": [
    {"moment": 0, "side": "away", "shared_resource": true,
     "csv": "pool,index,jersey\nprimary,0,12\n"}
  ]
}
```

Embed CSV text rather than a machine-specific path. In Python, use
`json.dumps({... "csv": Path("away.csv").read_text(encoding="utf-8-sig")})`.
The panel imports CSV files directly. Its grid uses the existing Rosters codec,
shows all 53 players, preserves pending edits across shared selections, and
validates before saving a build plan. The shared-use checkbox enables editing.

CSV requires `pool,index`, with `primary` and 0..52, and can contain any subset
of the exported columns. No name-based identity fallback is permitted. Missing
columns or empty cells leave their fields unchanged. Duplicate players/columns,
extra cells, invalid values and unsupported columns refuse the entire import.
Names must fit the existing pool; shortened allocations remain reusable after
reopening. Numeric fields use the existing codec. Ratings are 0..100, jersey
numbers 0..99, and position/appearance names or codes are those the Rosters codec
already accepts. Importing multiple files into one panel selection merges their
supported fields.

| CSV columns | Support |
|---|---|
| `pool,index` | Required read-only identity |
| `first,last,jersey,position` | Existing 53 player records |
| `years_pro,height,weight,hand` | Existing roster codec; inches/pounds for measurements |
| All 28 exported rating columns | 0..100, using existing field names |
| `skin,face,body,dreads,eye_black,helmet,face_mask,face_shield,mouthpiece,turtleneck,sleeves,neck_roll` | Existing appearance codec |
| `left_glove,right_glove,left_wrist,right_wrist,left_elbow,right_elbow,left_shoe,right_shoe` | Existing equipment codec |
| College, membership, contracts, birthday, abilities, guardian cap, unknown bits | Excluded from this contextual importer |

College is deliberately excluded: historic player +00 is an index imported
through the main college table, not the normal disc college pointer.

## Scenario JSON fields

`data/nfl2k5_espn25_authoring.schema.json` describes the two authoring schemas.
The backend additionally checks source layouts, allocations and name/year
pairs. JSON files and saved plans are capped at 2 MiB; CSV at 256 KiB. Duplicate
JSON keys, booleans used as numbers and nonfinite numbers are rejected.

A fixed edit has `moment` and optional `text`, `teams`, `setup`,
`conditions_from_moment`. At most 25 unique moment edits and 75 distinct historic
resource imports are accepted. Two imports of the same shared file refuse.

`text` accepts `title,description,objective,date`. Each stays within its original
UTF-16 allocation including the terminator. Shortening zero-fills the tail and
does not reduce the allocation on reopen. Selectors use their own existing
allocations, so a longer replacement can refuse even if its roster exists.

`teams` has optional `away` and `home`, each with `selector` and `year`. Both
must resolve together to one of the 75 descriptors reported by `inspect`.
Uniform selections remain those of the source moment. A team change therefore
needs a kit witness. CSV imports in a combined document bind to its **final**
selectors. The panel refuses changing a team underneath an already staged roster;
save the team edits, build and reload before editing that team's players.

| Setup field | Accepted values / units |
|---|---|
| `stadium_index` | Integer 0..30, conservative Anniversary authoring range; main ROST has 82 entries |
| `human_side,possession_side` | 0 away, 1 home |
| `away_score,home_score` | Starting scoreboard values, 0..99 |
| `away_historical_score,home_historical_score` | Historical final-score display, 0..99; not completion targets |
| `quarter_index` | 0..3, meaning first through fourth quarter |
| `ball_yards` | -49..49 from midfield; positive is the away half |
| `yards_to_gain` | Positive 0.01..99 yards |
| `down` | 0 kickoff, 1..4 ordinary downs |
| `clock_seconds` | 0..900 seconds, finite |
| `away_timeouts,home_timeouts` | Integers 0..3 |

These bounds describe the encoding. They do not certify that every combination
makes a sensible football situation. Down/possession/ball placement need a play
witness. Source conditions can be copied with `conditions_from_moment: 0..24`.
This copies the complete +60..+68 weather/environment/signed-input bundle without
claiming unknown enum names or temperature units. It does not copy uniforms.

Completion compares the human side's final score against the opponent's in the
ordinary Anniversary mode. Objective prose and historical final-score text do
not define custom executable win conditions. This editor does not create new
objective rules.

## Research authoring beyond 25

Use `schema: "nfl2k5.espn25.research.v1"` and `append: [...]`. Each appended row
requires `template` (0..24), all four `text` fields, both `teams`, and **every**
`setup` field listed above. `conditions_from_moment` is optional. The template
retains the source uniform choices and opaque fields. Append 1..7 rows, keeping
all original ordinals. A five-row append produces a 30-row experiment.

```sh
python3 -m mod_editor.core.nfl2k5_espn25_scenarios research-check source.iso draft.json
```

The command validates and reports count, size and digest, with `installable:
false`. It does not emit a disc-installable resource. The Python
`Catalog.research_table` returns bounded test bytes for native experiments.
It moves the string pool, recalculates all six biased pointers, updates body and
wrapper counts, and pads the body to a 16-byte resource boundary. Other outer-22
siblings are outside that returned first chunk and must be preserved by any
future collection writer.

The native tests cover 30 relocations, accessor results, menu-count and caption
callbacks, exact inverse serialization, in-memory completion and reward masks.
Full menu paging and serialized profile persistence remain unproved. The
production writer accepts only 25 moments and never writes the XBE or profile.
More than 32 also needs a versioned save representation; bit 32 aliases bit 0.

## Plans, receipts and compatibility

`prepare` returns `nfl2k5.espn25.plan.v1`: each resource has its outer identity,
size, complete before/after SHA-256 and exact byte ranges. Outer 22 is included
even when unchanged, to pin roster bindings. Main historic descriptor content is
also pinned. Every resource must be entirely before or entirely after; mixed,
stale, foreign and protected-field changes refuse before the first write.
Repeated application of the same plan is a no-write success.

`data/nfl2k5_espn25_layout.json` contains structural metadata and masked hashes,
not retail player or scenario text. Its guards preserve wrappers, siblings,
table geometry, team pointer lists, college indices, unknown player bits and
unowned pools. Recognized player fields and names remain editable. The source's
main roster must retain the supported wrapper/table geometry: version-18 roster
arena growth and other historic reclassification/layout changes are not claimed
compatible. Build from a matching source or refuse; do not bypass pins.

These resources are uncompressed. No `nfl_vc_lz_fill` call is needed for this
fixed-span writer. A compressed or foreign variant refuses. Any future compressed
replacement must use that refitter and retain wrapper +14.

Plans include before-byte preimages and are local build artifacts. They can
contain portions of source text; distribute the authoring JSON/CSV and tooling,
not plans containing retail preimages or generated game resources.

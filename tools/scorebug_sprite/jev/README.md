# Scorebug replication workbench

Status: diagnostic foundation. The disc-o dark-label reproduction gate is
unresolved. The production template, layout and runtime remain unchanged.
The accent JSON is a review candidate, not the active layout source.

All measurements and arithmetic run in Python. Jev receives text only.
Every live decision is retained in `reports/b72_s3/jev_calls.jsonl`.
The job has a $3 cap checked against both its receipts and the shared usage log.

The five modules are `miner.py`, `layout_search.py`, `accents.py`, `judge.py`,
and `rubric.py`. `descriptors.py` supplies measurements; `session.py` handles
receipts, budgeting and the outside-sandbox SDK boundary.

Examples from the repository root:

```text
python tools/scorebug_sprite/render.py --away LIONS --home RAIDERS --state 1st_and_10 --aspect 16:9
python tools/scorebug_sprite/render.py --all-teams --output teams.png
python tools/scorebug_sprite/compare_ingame.py capture.png --away LIONS --home RAIDERS --state 1st_and_10
python tools/scorebug_sprite/native.py --output submission.json
python tools/scorebug_sprite/jev/miner.py --frames FRAMES --output pilot --limit 200
```

Preview requires the pinned retail input and the existing Pillow, NumPy,
Unicorn and Capstone dependencies. It reports a failed calibration gate in
its JSON and terminal output. It must not be used as an acceptance preview.
Named states can be replaced by a JSON state, including exact score, clock,
down, distance and possession. A screenshot with an unknown state cannot
establish an engine cause.

The 200-frame MCP pilot is stratified across the every-tenth-frame subset.
It uses ESPN glyph masks already in the project. Connected or ambiguous text
is rejected. Banner templates, clock-state inference and reliable absence
representatives still need work; the pilot is not a complete state taxonomy.
The full run is deliberately not sent through MCP. After improving those
measurements, the integrator can run the following with the TypeSafe SDK and
`TYPESAFE_API_KEY` configured:

```text
python tools/scorebug_sprite/jev/replay.py --frames FRAMES --report reports/b72_s3
```

That command samples every tenth frame, retains each response, resumes from
its answer journal, clusters accepted representatives, and checks the shared
budget before every request. No service key is stored in the repository.

Screenshot comparison saves a `jev_request`. Submit it through MCP, then use
`--jev-response RESPONSE.json`, or run `--jev-live` with the SDK outside the
sandbox. Suggested keys are inspection targets. They are never automatic edits.

The 32 NFL accent candidates use the supplied authoritative
`data/nfl2k5_scorebug_sprite/team_colors_official_2026.json`. Code excludes
logo-detail-only colours from large fills and retains source citations and
shade disputes. Extra roster slots use the pinned retail table at `0x4E7FE0`.
Two user slots and five teams absent from that table use an explicitly marked
neutral fallback. Historical teams inherit their asset-code palette. Each
colour is an exact source colour or a documented RGB lighter/darker variant;
code requires white-text contrast of at least 4.5. Wash uses the wing colour.
Disagreements, low Jev confidence and low-confidence source shades go to the
review list and swatch sheet. The source palette's shade choices are supplied
research, not independent web verification by this tool.
The existing runtime still supports 32 team logos and a neutral fallback.

Layout search accepts an evaluator that renders a candidate and returns
measured residuals plus readability checks. It only keeps strict objective
improvements at adequate confidence. Its random control uses the same trial
count. Search refuses to start until calibration is verified; there is no
claimed search curve or post-fix rubric result for this job.

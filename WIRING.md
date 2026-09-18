# b72-s1 integration

The requested Studio/Build option is wired in this branch, including the supporting Build panel, project settings and Studio shell connections. No GUI insertion is left to the integrator. The existing scorebug capability remains EXPERIMENTAL; no registry row is added and the registry count stays unchanged.

The protected capability registry needs this update to the existing row `nfl2k5.scorebug_presentation.runtime` in `mod_editor/capabilities/registry.v1.json`. This is a concrete replacement for its summary and an additional selector entry:

```json
{
  "summary": "The SD sprite cut provides a larger readable down label and quarter/play clock, cells pre-filtered to their 16:9 HUD footprint, team-coloured rims, measured wing ramps and logo placement, a glossy possession plate, white scores, a separator and a dark pointer. ESPN NFL is the default watermark, with MNF only for franchise Monday night; always MNF and off are available. One quad swaps UVs through the calendar-aware weekday site. The 47-quad, 35-resource design still appends 323,808 bytes. Native CPU execution and software raster proofs cover both aspects; in-game appearance remains UNWITNESSED and the sprite feature stays off in every preset.",
  "selector_to_append": {
    "name": "scorebug_watermark",
    "allowed": "auto (default): NFL with MNF on franchise Monday night; mnf: always MNF; off: no watermark",
    "required": false
  },
  "evidence_to_append": [
    "reports/b72_s1/residuals.json",
    "reports/b72_s1/label_sweep.json",
    "reports/b72_s1/native_sequence.json",
    "reports/b72_s1/watermark_native.json",
    "tests/mod_editor/test_nfl2k5_scorebug_sd.py",
    "tests/mod_editor/test_nfl2k5_scorebug_watermark.py"
  ]
}
```

Remove the obsolete “light notch” and “standard glyph ink within one HUD pixel” statements in that row's proof scope. The larger SD cap intentionally differs from broadcast proportions. Preserve the `not-tested` witness status.

Regenerate `data/nfl2k5_cave_reservations.json` after integration, as required by ASTRA_CONTEXT.md. The owner still reserves exactly 4,096 RX bytes and does not move allocation boundaries. Its internal instructions and source fingerprints changed. This protected manifest was not rewritten from stale observations. The full disposable-disc manifest build belongs on the integration scratch volume; this sandbox permits writes only in the worktree and temporary directory.

`packaging/repin.py --apply` refreshes source fingerprints, including `mod_editor/core/providers.py` and existing packaging pins. No release version constants were changed. The measurement and authoring tools need not be added to the release allowlist; builds use only the shipped PNG/JSON and existing compiler/runtime modules.

The shared Git metadata is read-only. Commits and branch `b72-s1` therefore live in `.scratch/b72-s1.git`, using the original object database read-only. Fetch the verified `.scratch/astra-b72-s1.bundle`; it contains the delivery branch based on 088e3f41.

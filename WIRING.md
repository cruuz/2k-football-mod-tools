# b72-s1 integration

The requested Studio/Build option is wired in this branch, including the supporting Build panel, project settings and Studio shell connections. No GUI insertion is left to the integrator. The existing scorebug capability remains EXPERIMENTAL; no registry row is added and the registry count stays unchanged.

The protected capability registry needs this update to the existing row `nfl2k5.scorebug_presentation.runtime` in `mod_editor/capabilities/registry.v1.json`. The executable integration edit appears below.

Remove the obsolete “light notch” and “standard glyph ink within one HUD pixel” statements in that row's proof scope. The larger SD cap intentionally differs from broadcast proportions. Preserve the `not-tested` witness status.

Regenerate `data/nfl2k5_cave_reservations.json` after integration, as required by ASTRA_CONTEXT.md. The owner still reserves exactly 4,096 RX bytes and does not move allocation boundaries. Its internal instructions and source fingerprints changed. This protected manifest was not rewritten from stale observations. The full disposable-disc manifest build belongs on the integration scratch volume; this sandbox permits writes only in the worktree and temporary directory.

`packaging/repin.py --apply` refreshes source fingerprints, including `mod_editor/core/providers.py` and existing packaging pins. No release version constants were changed. The measurement and authoring tools need not be added to the release allowlist; builds use only the shipped PNG/JSON and existing compiler/runtime modules.

The branch's oracle run uses a separate freshly observed pure-XBE manifest. `reports/b72_s1/observe_gate_manifest.py` records the complete scaleout safety-gate fixture and checks every changed byte is attributed. Its metadata is retained in `reports/b72_s1/gate_manifest.json`; no executable bytes are saved. The oracle's disc/resource-build check explicitly skips with this manifest. This does not replace the integration release-manifest regeneration.

The reviewed PNG catalog has the new atlas's exact byte count and hash. In the protected `packaging/check_2k5_mod_studio_release.py`, at the module-level constant immediately after `SCOREBUG_TEMPLATE_PNG_CATALOG`, replace the old catalog digest with this line:

```python
SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "8c69221862b16a928172048f9043588b356738dd1c0b26cee1a98f50ca96cc39"
```

`PYTHONPATH=. python3 reports/b72_s1/prove_release_pin.py` runs the full five-test template-release file with only that exact constant substituted in memory. It verifies the checker stays byte-for-byte unchanged on disk. This proves the pending edit, including catalog tamper and arbitrary-PNG refusal. The plain template-release test remains blocked by the old protected pin until integration applies it. Its initial failing output is preserved in `reports/b72_s1/logs/previous_test_nfl2k5_scorebug_template_release.log`. After the edit, run `PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_scorebug_template_release.py` directly.

The shared Git metadata is read-only. Commits and branch `b72-s1` therefore live in `.scratch/b72-s1.git`, using the original object database read-only. Fetch the verified `.scratch/astra-b72-s1.bundle`; it contains the delivery branch based on 088e3f41.

The exact registry edit can be applied at integration with this script from the repo root. It changes the existing row only and is idempotent. Review the resulting JSON diff before the registry checks.

```python
from pathlib import Path
import json
path = Path("mod_editor/capabilities/registry.v1.json")
data = json.loads(path.read_text())
# The registry root's capabilities list contains the existing entry.
rows = data if isinstance(data, list) else data["capabilities"]
row = next(item for item in rows if item["id"] == "nfl2k5.scorebug_presentation.runtime")
row["summary"] = (
    "The SD sprite cut provides a larger down label, quarter and play clock, "
    "team-coloured wash and rims, measured wing ramps and logo placement, a glossy "
    "plate, white scores, a separator and a dark pointer. ESPN NFL is the default "
    "watermark, with MNF only for franchise Monday night. Always MNF and off are "
    "available. One quad swaps UVs through the calendar-aware weekday site. "
    "The 47-quad, 35-resource design appends 323,808 bytes. Native CPU execution "
    "and software raster proofs cover both aspects; in-game appearance remains "
    "UNWITNESSED and the feature stays off in every preset."
)
row["runtime"]["scope"] = (
    "Native collection loading and read-back verify the enlarged scene and atlas. "
    "Native retail getters, the down binding/slide gate and retained event "
    "callbacks execute in bounded fixtures. All measured static colours and "
    "geometry pass at 6 RGB units and 1 HUD pixel. The deliberately larger SD "
    "text is documented as incompatible with exact broadcast cap and digit "
    "dimensions. The 16:9 label has 12 ink scanlines, 2.654-pixel effective "
    "stems and no skipped digit texel columns. Auto watermark tests execute "
    "the weekday site with and without the extended calendar. Native CPU "
    "execution and software rasterization do not prove GPU or played-game appearance."
)
fields = row["selectors"]["fields"]
fields[:] = [field for field in fields if field["name"] != "scorebug_watermark"]
fields.append({"name": "scorebug_watermark", "allowed": "auto (default), mnf, off", "required": False})
for evidence in (
    "reports/b72_s1/residuals.json", "reports/b72_s1/label_sweep.json",
    "reports/b72_s1/native_sequence.json", "reports/b72_s1/watermark_native.json",
    "tests/mod_editor/test_nfl2k5_scorebug_sd.py",
    "tests/mod_editor/test_nfl2k5_scorebug_watermark.py",
):
    if evidence not in row["runtime"]["evidence"]:
        row["runtime"]["evidence"].append(evidence)
path.write_text(json.dumps(data, indent=2) + "\n", newline="\n")
```

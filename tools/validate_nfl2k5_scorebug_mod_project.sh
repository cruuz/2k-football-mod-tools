#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT

project='reports/assets/nfl2k5_scorebug_mod_project_example.json'
schema='reports/assets/nfl2k5_scorebug_mod_project.schema.json'
source='ESPN NFL 2K5 (USA).xiso.iso'
index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
audit='reports/assets/scorebug_presentation_audit.json'

before_source="$(sha256sum "$source" | cut -d' ' -f1)"
before_index="$(sha256sum "$index" | cut -d' ' -f1)"
before_xbe="$(sha256sum "$xbe" | cut -d' ' -f1)"
before_audit="$(sha256sum "$audit" | cut -d' ' -f1)"

python3 -m py_compile tools/nfl2k5_scorebug_mod_project.py
python3 tests/nfl2k5_scorebug_mod_project_test.py
jsonschema -i "$project" "$schema"
python3 tools/nfl2k5_scorebug_mod_project.py validate --project "$project" \
  >"$temporary/validate.json"

if python3 tools/nfl2k5_scorebug_mod_project.py validate \
    --project "$project" --index "$index" >/dev/null 2>&1; then
  echo "typed scorebug backend accepted an arbitrary index argument" >&2
  exit 1
fi

if python3 tools/nfl2k5_scorebug_mod_project.py build \
    --project "$project" --source-xiso "$source" --output-xiso "$source" \
    --manifest "$temporary/alias.json" \
    --artifact-dir "$temporary/alias-artifacts" >/dev/null 2>&1; then
  echo "typed scorebug backend accepted source overwrite" >&2
  exit 1
fi

# Real-disc verifier gate without retaining another 6.3 GB image. This older
# single-target proof uses the same strict importer, retail pins, XDVDFS parser,
# and full-image outside-union comparison as the typed composer.
python3 tools/nfl_scorebug_xiso_verify.py \
  --source-xiso "$source" \
  --output-xiso \
    build/nfl2k5-scorebug-workflow-20260712/ESPN-NFL-2K5-scorebug-magenta.xiso.iso \
  --manifest build/nfl2k5-scorebug-workflow-20260712/workflow.json \
  --preview build/nfl2k5-scorebug-workflow-20260712/preview.png \
  --target score_buga \
  --png reports/assets/nfl2k5_scorebug_fixtures/score_buga_diagnostic.png

PYTHONPATH=tools python3 - "$temporary/validate.json" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

from nfl_scorebug_png_import import canonical_json

result = json.loads(Path(sys.argv[1]).read_text())
assert result["schema"] == "nfl2k5_scorebug_mod_project/v1"
assert result["edit_count"] == 3
assert result["targets"] == ["score_buga", "shield_espn", "digital_font"]
assert result["strict_importers_passed"] is True
assert result["source_pins_valid"] is True

project = Path("reports/assets/nfl2k5_scorebug_mod_project_example.json")
schema = Path("reports/assets/nfl2k5_scorebug_mod_project.schema.json")
for path in (project, schema):
    payload = path.read_bytes()
    assert payload == canonical_json(json.loads(payload))
assert hashlib.sha256(project.read_bytes()).hexdigest() == \
    "b658dce48bde48e8130890dd78a8ce060623f4e63c1b4bdb926beb5433f243d7"
assert hashlib.sha256(schema.read_bytes()).hexdigest() == \
    "2e213dc7448f34f40da2f9ab4cc2a1ccd9b4412390939411c12f231d11d81277"

tool = Path("tools/nfl2k5_scorebug_mod_project.py").read_text()
assert "--index" not in tool and "--audit" not in tool and "--offset" not in tool
assert "build_import(" in tool
assert "common.compare_and_hash(" in tool
assert "manifest_value == expected" in tool

doc = Path("docs/mod_editor/nfl2k5_scorebug_typed_backend.md").read_text().lower()
for phrase in ("one to three", "at most once", "all 6.3 gb",
               "does not obtain targets", "portme(runtime)",
               "global side effects"):
    assert phrase in " ".join(doc.split()), phrase
PY

after_source="$(sha256sum "$source" | cut -d' ' -f1)"
after_index="$(sha256sum "$index" | cut -d' ' -f1)"
after_xbe="$(sha256sum "$xbe" | cut -d' ' -f1)"
after_audit="$(sha256sum "$audit" | cut -d' ' -f1)"

test "$before_source" = "$after_source"
test "$before_index" = "$after_index"
test "$before_xbe" = "$after_xbe"
test "$before_audit" = "$after_audit"

echo "NFL2K5_SCOREBUG_MOD_PROJECT_VALIDATION_PASS targets=3 schema=canonical pins=strict union=synthetic real_xiso_gate=2169 runtime=false originals_unchanged=yes"

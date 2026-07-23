#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

source_0a='extracted/All-Pro Football 2K8 (USA)/0A'
temporary="$(mktemp -d /tmp/apf-jersey-typed-provider.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
before="$(sha256sum "$source_0a" | cut -d' ' -f1)"

export PYTHONDONTWRITEBYTECODE=1
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  mod_editor/core/providers.py \
  mod_editor/core/apf_export.py \
  mod_editor/core/controller.py \
  mod_editor/gui/tkinter_app.py \
  tools/apf_jersey_family_verify.py \
  tests/mod_editor/test_providers.py \
  tests/mod_editor/test_apf_export.py \
  tests/mod_editor/test_gui.py \
  tests/apf_jersey_family_verify_test.py

python3 -m mod_editor --check-registry --require-registry
python3 -m unittest discover -s tests/mod_editor -p 'test_*.py' -v
python3 -m unittest -v tests/apf_jersey_family_verify_test.py

python3 - "$temporary" <<'PY'
import json
from pathlib import Path
import sys
from PIL import Image

root = Path(sys.argv[1])
png = root / "user-jersey.png"
Image.new("RGBA", (1024, 1024), (7, 19, 31, 255)).save(png)
recipe = {
    "schema": "apf2k8_jersey_color_recipe/v1",
    "asset_index": 23,
    "png": str(png),
}
(root / "recipe.json").write_text(
    json.dumps(recipe, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

python3 tools/apf_jersey_family_verify.py validate-recipe \
  --recipe "$temporary/recipe.json" >"$temporary/recipe-report.json"

python3 - "$temporary/recipe-report.json" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text())
assert report["schema"] == "apf2k8_jersey_color_recipe/v1"
assert report["recipe_valid"] is True
assert report["asset_index"] == 23
assert report["png_dimensions"] == [1024, 1024]
assert report["png_mode"] == "RGBA"
PY

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.model import GameId
from mod_editor.core.providers import (
    Apf2k8JerseyColorProvider,
    ProviderOrchestrator,
)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

provider = Apf2k8JerseyColorProvider()
assert provider.backend_module_sha256 == sha(provider.backend_module)
assert provider.verifier_module_sha256 == sha(provider.verifier_module)
assert provider.recipe_schema_file_sha256 == sha(provider.recipe_schema_file)

registry = CapabilityRegistryLoader().load(allow_sample_fallback=False)
capability = registry.get("apf2k8.uniforms.jersey_00_23")
assert capability.game == GameId.APF2K8
assert capability.classification == Classification.OFFLINE_WRITER_PROVED
assert capability.raw["backend"]["module"] == provider.backend_module
assert capability.raw["source_container"]["hash_pins"] == [provider.source_sha256]
assert capability.raw["selectors"]["fields"] == [
    {"allowed": "0..23", "name": "asset_index", "required": True}
]
orchestrator = ProviderOrchestrator(registry)
assert orchestrator.provider_id("nfl2k5.uniforms.all_visual") == "nfl2k5-unified-visual-v1"
assert orchestrator.provider_id("nfl2k5.scorebug_presentation.inventory") == \
    "nfl2k5-scorebug-v1"
assert orchestrator.provider_id(capability.capability_id) == provider.provider_id

schema = json.loads(Path(provider.recipe_schema_file).read_text())
assert schema["additionalProperties"] is False
assert schema["properties"]["asset_index"] == {
    "maximum": 23, "minimum": 0, "type": "integer"
}

doc = Path("docs/mod_editor/public_editor_scaffold.md").read_text()
for phrase in (
    "Typed providers can now",
    "apf2k8-jersey-color-v1",
    "apf2k8_jersey_color_recipe/v1",
    "Create Typed Recipe…",
    "Export APF Jersey PNGs…",
    "--export-apf-jersey",
    "bank 0",
    "provenance.json",
    "source/output equality outside the fixed target span",
    "never executed",
):
    assert phrase in doc, phrase
PY

if find "$temporary" -type f -size +100M -print -quit | grep -q .; then
  echo 'retail-sized unit-test output unexpectedly exists' >&2
  exit 1
fi

after="$(sha256sum "$source_0a" | cut -d' ' -f1)"
test "$before" = 'dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
test "$after" = "$before"

echo 'APF_JERSEY_TYPED_PROVIDER_VALIDATION_PASS recipe_schema=v1 assets=24 gui_providers=5 editor_tests=84 read_only_export=true verifier_tests=4 fixed_argv=true shell=false retail_sized_test_copy=false originals_unchanged=yes'

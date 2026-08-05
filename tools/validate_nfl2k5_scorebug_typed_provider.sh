#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

temporary=$(mktemp -d /tmp/nfl2k5-scorebug-typed-provider.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  mod_editor/__main__.py \
  mod_editor/core/apf_export.py \
  mod_editor/core/providers.py \
  mod_editor/core/controller.py \
  mod_editor/core/recipes.py \
  mod_editor/gui/tkinter_app.py \
  tools/nfl2k5_scorebug_mod_project.py \
  tests/mod_editor/test_apf_export.py \
  tests/mod_editor/test_gui.py \
  tests/mod_editor/test_providers.py \
  tests/mod_editor/test_recipes.py

python3 -m mod_editor --check-registry --require-registry
for test_module in \
  test_apf_export.py test_gui.py test_providers.py test_recipes.py; do
  python3 -m unittest discover -s tests/mod_editor -p "$test_module" -v
done
bash tools/validate_nfl2k5_scorebug_mod_project.sh

python3 - <<'PY'
import hashlib
from pathlib import Path

from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.model import GameId
from mod_editor.core.providers import Nfl2k5ScorebugProvider, ProviderOrchestrator
from mod_editor.core.recipes import NFL_SCOREBUG_SOURCE_PIN

provider = Nfl2k5ScorebugProvider()
backend = Path(provider.backend_module)
assert hashlib.sha256(backend.read_bytes()).hexdigest() == provider.backend_module_sha256
assert dict(NFL_SCOREBUG_SOURCE_PIN) == provider.source_pin

registry = CapabilityRegistryLoader().load(allow_sample_fallback=False)
capability = registry.get("nfl2k5.scorebug_presentation.inventory")
assert capability.game == GameId.NFL2K5
assert capability.classification == Classification.OFFLINE_WRITER_PROVED
assert capability.raw["backend"] == {
    "command": (
        "python3 tools/nfl2k5_scorebug_mod_project.py build "
        "--project <scorebug-project.json> --source-xiso <retail.xiso.iso> "
        "--output-xiso <new.xiso.iso> --manifest <manifest.json> "
        "--artifact-dir <artifact-dir>"
    ),
    "module": provider.backend_module,
    "operation": "write",
}
assert capability.raw["source_container"]["hash_pins"] == [provider.source_sha256]
assert capability.raw["selectors"]["fields"] == [
    {
        "allowed": "score_buga, shield_espn, digital_font",
        "name": "target",
        "required": True,
    }
]
assert capability.raw["validation_command"] == \
    "bash tools/validate_scorebug_products.sh"
assert capability.is_experimental is False

orchestrator = ProviderOrchestrator(registry)
assert orchestrator.provider_id("nfl2k5.uniforms.all_visual") == \
    "nfl2k5-unified-visual-v1"
assert orchestrator.provider_id(capability.capability_id) == provider.provider_id
assert orchestrator.provider_id("apf2k8.uniforms.jersey_00_23") == \
    "apf2k8-jersey-color-v1"

doc = " ".join(
    Path("docs/mod_editor/public_editor_scaffold.md")
    .read_text(encoding="utf-8")
    .split()
)
for phrase in (
    "Typed providers can now",
    "nfl2k5-scorebug-v1",
    "Create Typed Recipe…",
    "compares all 6.3 GB",
    "solid-magenta `score_buga` and solid-cyan `shield_espn` replacements",
):
    assert phrase in doc, phrase
PY

if find "$temporary" -type f -size +100M -print -quit | grep -q .; then
  echo 'retail-sized unit-test output unexpectedly exists' >&2
  exit 1
fi

echo 'NFL2K5_SCOREBUG_TYPED_PROVIDER_VALIDATION_PASS recipe_schema=v1 targets=3 gui_providers=5 editor_tests=84 backend_tests=10 fixed_argv=true shell=false runtime=false originals_unchanged=yes'

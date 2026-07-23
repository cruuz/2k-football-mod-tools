#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d /tmp/apf-shoulder-typed-provider.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
source_0a='extracted/All-Pro Football 2K8 (USA)/0A'
before="$(sha256sum "$source_0a" | cut -d' ' -f1)"

export PYTHONDONTWRITEBYTECODE=1
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  mod_editor/core/recipes.py \
  mod_editor/core/providers.py \
  mod_editor/core/controller.py \
  mod_editor/gui/tkinter_app.py \
  tools/apf_shoulder_family_verify.py \
  tests/mod_editor/test_recipes.py \
  tests/mod_editor/test_providers.py \
  tests/mod_editor/test_gui.py

python3 -m mod_editor --check-registry --require-registry
help="$(python3 -m mod_editor --help)"
rg -q -- '--create-apf-shoulder-recipe OUTPUT.json' <<<"$help"
rg -q -- '--shoulder-png SHOULDER_PNG' <<<"$help"
python3 -m unittest -v \
  tests.mod_editor.test_recipes \
  tests.mod_editor.test_providers \
  tests.mod_editor.test_gui \
  tests.mod_editor.test_uniform_sharing

# This creates one copied retail-sized 0A in a temporary directory and runs
# both the legacy independent verifier and canonical recipe/artifact route.
bash tools/validate_apf_shoulder_family_patch.sh

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.model import GameId
from mod_editor.core.providers import Apf2k8ShoulderColorProvider, ProviderOrchestrator


def sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


provider = Apf2k8ShoulderColorProvider()
assert provider.backend_module_sha256 == sha(provider.backend_module)
assert provider.verifier_module_sha256 == sha(provider.verifier_module)
assert provider.recipe_schema_file_sha256 == sha(provider.recipe_schema_file)
assert provider.png_dimensions == (1024, 1024)
assert provider.png_fully_opaque is False

registry = CapabilityRegistryLoader().load(allow_sample_fallback=False)
capability = registry.get("apf2k8.uniforms.shoulder_color_00_23")
assert capability.game == GameId.APF2K8
assert capability.classification == Classification.OFFLINE_WRITER_PROVED
assert capability.raw["backend"] == {
    "command": capability.raw["backend"]["command"],
    "module": provider.backend_module,
    "operation": "write",
}
assert capability.raw["gui"]["default_enabled"] is True
assert capability.raw["gui"]["expose"] is True
assert capability.raw["gui"]["mode"] == "edit"
assert capability.raw["source_container"]["hash_pins"] == [provider.source_sha256]
assert capability.raw["selectors"]["fields"] == [
    {"allowed": "0..23", "name": "asset_index", "required": True}
]
assert capability.raw["validation_command"] == \
    "bash tools/validate_apf_shoulder_typed_provider.sh"
assert ProviderOrchestrator(registry).provider_id(capability.capability_id) == \
    provider.provider_id

schema = json.loads(Path(provider.recipe_schema_file).read_text(encoding="utf-8"))
assert schema["additionalProperties"] is False
assert schema["properties"]["schema"]["const"] == provider.recipe_schema
assert schema["properties"]["asset_index"] == {
    "maximum": 23, "minimum": 0, "type": "integer"
}

docs = (
    Path("docs/mod_editor/public_editor_scaffold.md").read_text(encoding="utf-8")
    + Path("docs/research/apf_shoulder_family_patch.md").read_text(encoding="utf-8")
)
for phrase in (
    "apf2k8-shoulder-color-v1",
    "apf2k8_shoulder_color_recipe/v1",
    "1024x1024 RGBA",
    "Typed Build + Independent Verify",
    "hash/metrics-only artifact directory",
    "paired shoulder-normal",
    "runtime visibility",
):
    assert phrase in docs, phrase
PY

after="$(sha256sum "$source_0a" | cut -d' ' -f1)"
test "$before" = 'dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
test "$after" = "$before"

echo 'APF_SHOULDER_TYPED_PROVIDER_VALIDATION_PASS recipe_schema=v1 assets=24 dimensions=1024x1024 rgba=true gui_provider=true fixed_argv=true shell=false independent_verify=true artifacts=hashes-metrics-only shared_selectors=true paired_normal_preserved=true production_bc3=false runtime_visibility=false originals_unchanged=yes'

#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d /tmp/apf-pants-typed-provider.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
source_0a='extracted/All-Pro Football 2K8 (USA)/0A'
before="$(sha256sum "$source_0a" | cut -d' ' -f1)"

export PYTHONDONTWRITEBYTECODE=1
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  mod_editor/core/recipes.py \
  mod_editor/core/providers.py \
  mod_editor/core/controller.py \
  mod_editor/gui/tkinter_app.py \
  tools/apf_pants_family_verify.py \
  tests/mod_editor/test_recipes.py \
  tests/mod_editor/test_providers.py \
  tests/mod_editor/test_gui.py

python3 -m mod_editor --check-registry --require-registry
help="$(python3 -m mod_editor --help)"
rg -q -- '--create-apf-pants-recipe OUTPUT.json' <<<"$help"
rg -q -- '--pants-png PANTS_PNG' <<<"$help"
python3 -m unittest discover -s tests/mod_editor -p 'test_*.py' -v

# The underlying family gate creates one copied 0A, then exercises both the
# legacy independent verifier and the typed recipe/artifact route against it.
bash tools/validate_apf_pants_family_patch.sh

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.model import GameId
from mod_editor.core.providers import Apf2k8PantsColorProvider, ProviderOrchestrator

def sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

provider = Apf2k8PantsColorProvider()
assert provider.backend_module_sha256 == sha(provider.backend_module)
assert provider.verifier_module_sha256 == sha(provider.verifier_module)
assert provider.recipe_schema_file_sha256 == sha(provider.recipe_schema_file)
assert provider.png_dimensions == (512, 512)
assert provider.png_fully_opaque is True

registry = CapabilityRegistryLoader().load(allow_sample_fallback=False)
capability = registry.get("apf2k8.uniforms.pants_color_00_23")
assert capability.game == GameId.APF2K8
assert capability.classification == Classification.OFFLINE_WRITER_PROVED
assert capability.raw["backend"]["module"] == provider.backend_module
assert capability.raw["backend"]["operation"] == "write"
assert capability.raw["gui"] == {
    "default_enabled": True,
    "expose": True,
    "mode": "edit",
    "reason": capability.raw["gui"]["reason"],
}
assert capability.raw["source_container"]["hash_pins"] == [provider.source_sha256]
assert capability.raw["selectors"]["fields"] == [
    {"allowed": "0..23", "name": "asset_index", "required": True}
]
orchestrator = ProviderOrchestrator(registry)
assert orchestrator.provider_id(capability.capability_id) == provider.provider_id

schema = json.loads(Path(provider.recipe_schema_file).read_text(encoding="utf-8"))
assert schema["additionalProperties"] is False
assert schema["properties"]["schema"]["const"] == provider.recipe_schema
assert schema["properties"]["asset_index"] == {
    "maximum": 23, "minimum": 0, "type": "integer"
}

doc = Path("docs/mod_editor/public_editor_scaffold.md").read_text(encoding="utf-8")
research = Path("docs/research/apf_pants_family_patch.md").read_text(encoding="utf-8")
for phrase in (
    "apf2k8-pants-color-v1",
    "apf2k8_pants_color_recipe/v1",
    "opaque 512x512 RGBA",
    "Typed Build + Independent Verify",
    "runtime visibility is not proved",
):
    assert phrase in doc + research, phrase
PY

after="$(sha256sum "$source_0a" | cut -d' ' -f1)"
test "$before" = 'dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
test "$after" = "$before"

echo 'APF_PANTS_TYPED_PROVIDER_VALIDATION_PASS recipe_schema=v1 assets=24 dimensions=512x512 opaque=true gui_provider=true fixed_argv=true shell=false independent_verify=true artifacts=hashes-only runtime_visibility=false originals_unchanged=yes'

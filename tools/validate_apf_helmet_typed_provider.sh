#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d /tmp/apf-helmet-typed-provider.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
source_0a='extracted/All-Pro Football 2K8 (USA)/0A'
before="$(sha256sum "$source_0a" | cut -d' ' -f1)"

export PYTHONDONTWRITEBYTECODE=1
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  mod_editor/core/recipes.py \
  mod_editor/core/providers.py \
  mod_editor/core/controller.py \
  mod_editor/gui/tkinter_app.py \
  tools/apf_helmet_family_verify.py \
  tests/mod_editor/test_recipes.py \
  tests/mod_editor/test_providers.py \
  tests/mod_editor/test_gui.py

python3 -m mod_editor --check-registry --require-registry
help="$(python3 -m mod_editor --help)"
rg -q -- '--create-apf-helmet-recipe OUTPUT.json' <<<"$help"
rg -q -- '--helmet-png HELMET_PNG' <<<"$help"
for test_module in test_recipes.py test_providers.py test_gui.py; do
  python3 -m unittest discover -s tests/mod_editor -p "$test_module" -v
done

# The family gate now covers both the legacy verifier and the canonical
# recipe/artifact interface against the same copied retail-sized output.
bash tools/validate_apf_helmet_family_patch.sh

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.model import GameId
from mod_editor.core.providers import Apf2k8HelmetColorProvider, ProviderOrchestrator

def sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

provider = Apf2k8HelmetColorProvider()
assert provider.backend_module_sha256 == sha(provider.backend_module)
assert provider.verifier_module_sha256 == sha(provider.verifier_module)
assert provider.recipe_schema_file_sha256 == sha(provider.recipe_schema_file)
assert provider.png_dimensions == (256, 1024)
assert provider.png_fully_opaque is True
assert provider.png_blue_zero is True
assert provider.channels_semantics_named is False

registry = CapabilityRegistryLoader().load(allow_sample_fallback=False)
capability = registry.get("apf2k8.uniforms.helmet_color_00_23")
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
assert ProviderOrchestrator(registry).provider_id(capability.capability_id) == provider.provider_id

schema = json.loads(Path(provider.recipe_schema_file).read_text(encoding="utf-8"))
assert schema["additionalProperties"] is False
assert schema["properties"]["schema"]["const"] == provider.recipe_schema
assert schema["properties"]["asset_index"] == {
    "maximum": 23, "minimum": 0, "type": "integer"
}

docs = (
    Path("docs/mod_editor/public_editor_scaffold.md").read_text(encoding="utf-8")
    + Path("docs/research/apf_helmet_family_patch.md").read_text(encoding="utf-8")
)
for phrase in (
    "apf2k8-helmet-color-v1",
    "apf2k8_helmet_color_recipe/v1",
    "exact 256x1024 stored RGBA",
    "R/G data",
    "B sample equal to zero",
    "A sample equal to 255",
    "runtime visibility",
):
    assert phrase in docs, phrase
PY

after="$(sha256sum "$source_0a" | cut -d' ' -f1)"
test "$before" = 'dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
test "$after" = "$before"

echo 'APF_HELMET_TYPED_PROVIDER_VALIDATION_PASS recipe_schema=v1 assets=24 dimensions=256x1024 rgba_contract=raw-rg-b0-a255 gui_provider=true fixed_argv=true shell=false independent_verify=true artifacts=hashes-metrics-only runtime_visibility=false channel_semantics_named=false originals_unchanged=yes'

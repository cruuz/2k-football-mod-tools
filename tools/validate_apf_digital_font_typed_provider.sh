#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d /tmp/apf-digital-font-typed-provider.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
source_0a='extracted/All-Pro Football 2K8 (USA)/0A'
before="$(sha256sum "$source_0a" | cut -d' ' -f1)"

export PYTHONDONTWRITEBYTECODE=1
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  mod_editor/core/apf_digital_font.py \
  mod_editor/core/apf_digital_font_provider.py \
  mod_editor/core/providers.py \
  mod_editor/core/controller.py \
  mod_editor/__main__.py \
  mod_editor/gui/tkinter_app.py \
  tools/apf_digital_font_verify.py \
  tests/mod_editor/test_apf_digital_font.py \
  tests/mod_editor/test_providers.py \
  tests/mod_editor/test_gui.py

python3 -m mod_editor --check-registry --require-registry
help="$(python3 -m mod_editor --help)"
rg -q -- '--create-apf-digital-font-recipe OUTPUT.json' <<<"$help"
rg -q -- '--apf-digital-font-png APF_DIGITAL_FONT_PNG' <<<"$help"
python3 -m unittest -v \
  tests.mod_editor.test_apf_digital_font \
  tests.mod_editor.test_providers \
  tests.mod_editor.test_gui \
  tests.mod_editor.test_presentation_inspection

# Regenerate the pinned format/roundtrip evidence, then exercise the canonical
# recipe, copied 0A writer, and typed metadata-only verifier artifact route.
bash tools/validate_apf_digital_font_patch.sh

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

from mod_editor.core.apf_digital_font import (
    APF_DIGITAL_FONT_RECIPE_SCHEMA,
    APF_DIGITAL_FONT_SCOPE,
    APF_DIGITAL_FONT_STORED_CHANNEL,
    APF_DIGITAL_FONT_TARGET,
)
from mod_editor.core.apf_digital_font_provider import Apf2k8DigitalFontProvider
from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.model import GameId
from mod_editor.core.providers import ProviderOrchestrator


provider = Apf2k8DigitalFontProvider()
for relative, expected in provider.module_pins.items():
    assert hashlib.sha256(Path(relative).read_bytes()).hexdigest() == expected, relative

registry = CapabilityRegistryLoader().load(allow_sample_fallback=False)
capability = registry.get("apf2k8.scorebug_presentation.digital_font")
assert capability.game == GameId.APF2K8
assert capability.classification == Classification.OFFLINE_WRITER_PROVED
assert capability.raw["backend"]["module"] == provider.backend_module
assert capability.raw["backend"]["operation"] == "write"
assert capability.raw["gui"]["default_enabled"] is True
assert capability.raw["gui"]["expose"] is True
assert capability.raw["gui"]["mode"] == "edit"
assert capability.raw["source_container"]["hash_pins"] == [provider.source_sha256]
assert capability.raw["selectors"]["fields"] == [{
    "allowed": "digital_font only", "name": "target", "required": True,
}]
assert capability.raw["validation_command"] == \
    "bash tools/validate_apf_digital_font_typed_provider.sh"
assert ProviderOrchestrator(registry).provider_id(capability.capability_id) == \
    provider.provider_id

schema = json.loads(Path(provider.recipe_schema_file).read_text(encoding="utf-8"))
assert schema["additionalProperties"] is False
assert schema["properties"]["schema"]["const"] == APF_DIGITAL_FONT_RECIPE_SCHEMA
assert schema["properties"]["target"]["const"] == APF_DIGITAL_FONT_TARGET
assert schema["properties"]["scope"]["const"] == APF_DIGITAL_FONT_SCOPE
assert schema["properties"]["stored_channel"]["const"] == \
    APF_DIGITAL_FONT_STORED_CHANNEL

docs = (
    Path("docs/mod_editor/public_editor_scaffold.md").read_text(encoding="utf-8")
    + Path("docs/research/apf_digital_font_patch.md").read_text(encoding="utf-8")
    + Path("README.md").read_text(encoding="utf-8")
)
for phrase in (
    "apf2k8-digital-font-v1",
    "apf2k8_digital_font_recipe/v1",
    "shared-global-ui",
    "solid-white RGB",
    "alpha plane",
    "hash/metrics-only artifact",
    "single-link",
    "staged closure",
    "750 unrelated",
    "runtime visibility is not proved",
    "production",
):
    assert phrase in docs, phrase
PY

after="$(sha256sum "$source_0a" | cut -d' ' -f1)"
test "$before" = 'dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
test "$after" = "$before"

echo 'APF_DIGITAL_FONT_TYPED_PROVIDER_VALIDATION_PASS recipe_schema=v1 target=digital_font dimensions=128x128 rgb=white stored_channel=alpha gui_provider=true fixed_argv=true shell=false modules_pinned=10 single_link=true staged_closure=true independent_verify=true artifacts=hashes-metrics-only shared_global=true field_only=false production_dxt5a=false runtime_visibility=false originals_unchanged=yes'

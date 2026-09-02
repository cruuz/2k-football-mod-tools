#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

python3 -m py_compile \
  mod_editor/core/nfl_audio.py \
  mod_editor/core/nfl_audio_provider.py \
  tools/nfl_audo_wav_xiso_workflow.py \
  tools/nfl_audo_wav_xiso_verify.py \
  tools/nfl_uniform_color_xiso_direct_patch.py \
  tools/nfl_team_identity_xiso_verify.py
python3 -m unittest -v tests/mod_editor/test_nfl_audio.py
python3 -m unittest -v \
  tests.mod_editor.test_providers.ProviderTests.test_subprocess_runner_forces_argv_mode_closed_stdin_and_no_shell

python3 - <<'PY'
import fcntl
import hashlib
from pathlib import Path
import os
import stat
import struct
import sys

root = Path.cwd()
sys.path.insert(0, os.fspath(root / "tools"))

import nfl_audo_wav_xiso_workflow as writer
from mod_editor.core.capabilities import CapabilityRegistryLoader
from mod_editor.core.nfl_audio_provider import Nfl2k5MenuBackAudioProvider
from mod_editor.core.providers import ProviderOrchestrator, ProviderStage

pack = root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
with pack.open("rb") as stream:
    stream.seek(writer.OUTER_PACK_OFFSET + writer.CHUNK_OFFSET)
    wrapper = stream.read(writer.WRAPPER_SIZE)
writer.validate_retail_wrapper(wrapper)

samples = tuple(
    max(-32768, min(32767, ((index * 977) % 65536) - 32768))
    for index in range(writer.FRAME_COUNT)
)
encoded_a = writer.encode_xbox_ima(samples)
encoded_b = writer.encode_xbox_ima(samples)
decoded = writer.decode_xbox_ima(encoded_a)
assert encoded_a == encoded_b
assert len(encoded_a) == writer.PAYLOAD_SIZE == 3204
assert len(decoded) == writer.FRAME_COUNT == 5696
assert writer.quality(samples, decoded)["block_predictor_samples_exact"] is True
retail_payload = wrapper[
    writer.HEADER_SIZE + writer.SYSTEM_SIZE:
    writer.HEADER_SIZE + writer.SYSTEM_SIZE + writer.PAYLOAD_SIZE
]
assert encoded_a != retail_payload

registry = CapabilityRegistryLoader().load(allow_sample_fallback=False)
capability = registry.get("nfl2k5.audio.menu_back_wav")
assert capability.classification.value == "offline-writer-proved"
assert capability.raw["backend"]["module"] == Nfl2k5MenuBackAudioProvider.backend_module
providers = ProviderOrchestrator(registry)
assert providers.provider_id(capability.capability_id) == (
    Nfl2k5MenuBackAudioProvider.provider_id
)

provider = Nfl2k5MenuBackAudioProvider(workspace=root)
pins = {
    provider.backend_module: provider.backend_module_sha256,
    provider.writer_dependency_module: provider.writer_dependency_module_sha256,
    provider.verifier_module: provider.verifier_module_sha256,
    provider.verifier_dependency_module: provider.verifier_dependency_module_sha256,
    provider.recipe_schema_file: provider.recipe_schema_file_sha256,
}
for relative, expected in pins.items():
    path = root / relative
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
    assert info.st_nlink == 1
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected

required_seals = (
    fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL |
    fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_WRITE
)
for label, members, expected_names in (
    (
        "writer",
        provider._writer_members(),
        {"__main__.py", "nfl_uniform_color_xiso_direct_patch.py"},
    ),
    (
        "verifier",
        provider._verifier_members(),
        {"__main__.py", "nfl_team_identity_xiso_verify.py"},
    ),
):
    payloads = provider._load_closure(members)
    assert set(payloads) == expected_names
    with provider._sealed_zipapp(members, label) as module:
        descriptor = os.open(module.path, os.O_RDONLY)
        try:
            assert fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & required_seals == required_seals
        finally:
            os.close(descriptor)
        with module.pin_for_exec(
            ProviderStage.VALIDATE, lambda _event: None
        ) as pinned:
            result = provider._run(
                (
                    sys.executable,
                    "-I",
                    "-B",
                    "-S",
                    os.fspath(pinned.path),
                    "--help",
                ),
                ProviderStage.VALIDATE,
                lambda _event: None,
            )
        assert result.returncode == 0 and "usage:" in result.stdout
        assert result.argv[1:4] == ("-I", "-B", "-S")
        assert result.argv[4].startswith(f"/proc/{os.getpid()}/fd/")

compatibility = root / "reports/assets/audio_modding_compatibility.json"
import json
report = json.loads(compatibility.read_text(encoding="utf-8"))
assert report["claims"]["nfl_one_fixed_slot_wav_import_available"] is True
assert report["claims"]["nfl_generic_audo_import_available"] is False
assert report["claims"]["runtime_visibility_tested"] is False
PY

bash tools/validate_audio_modding_compatibility.sh

echo "NFL2K5_MENU_BACK_AUDIO_MODDING_VALIDATION_PASS target=outer_3_chunk_101_menu-back_01 provider=typed sealed_closure=true single_link_pins=true isolated_python=true site_imports=false copied_xiso=true independent_full_image_verifier=true runtime=false generic_audio=false retail_sized_test_copy=false"

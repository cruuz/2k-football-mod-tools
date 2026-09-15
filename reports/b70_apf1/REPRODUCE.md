# Reproduce APF-1 offline measurements

Run from the APF-1 worktree. No emulator or network is used. Temporary fixtures
are generated artwork and tiny archives; owned retail inputs are read-only.
The original `before_no_helper.json` was measured before writer edits using a
top-level wrapper that set `apf_field_art_patch._optimal_binary = lambda: None`
in parent and spawn children. The following equivalent reference loader also
works after integration. `environment.json` records the base and reference hashes.

## Save the beta-69 reference

```sh
python3 - <<'PY'
from pathlib import Path
import subprocess, tempfile
reference = Path(tempfile.mkdtemp(prefix='apf-b70-reference-'))
base = '665b1cb6^'
for path in ('tools/apf_logo_patch.py', 'tools/apf_logocache_patch.py',
             'tools/apf_h7a_optimal', 'mod_editor/apf_studio/ps3_texture_bundle.py'):
    (reference / Path(path).name).write_bytes(subprocess.check_output(['git', 'show', f'{base}:{path}']))
(reference / 'apf_h7a_optimal').chmod(0o755)
print(reference)
PY
```

Save this as `reference_runner.py` in that printed temporary directory. Run
it from the repository root with `PYTHONPATH=.:tools`. Module loading must
happen outside the `__main__` guard so spawn workers receive the same reference.

```python
from pathlib import Path
import importlib.util
import sys
sys.path[:0] = [str(Path.cwd()), str(Path.cwd() / 'tools')]
import apf_field_art_patch
apf_field_art_patch._optimal_binary = lambda: None
import mod_editor.apf_studio
for name, filename in (
    ('apf_logo_patch', 'apf_logo_patch.py'),
    ('apf_logocache_patch', 'apf_logocache_patch.py'),
    ('mod_editor.apf_studio.ps3_texture_bundle', 'ps3_texture_bundle.py'),
):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if name.startswith('mod_editor.'):
        mod_editor.apf_studio.ps3_texture_bundle = module
import apf_ps3_speed_benchmark as benchmark
if __name__ == '__main__':
    benchmark.main()
```

Use the printed reference directory for `REFERENCE` below. Keep native and
portable policies distinct; the measured portable default has
`APF_H7A_PYTHON_OPTIMAL` unset.

```sh
PYTHONPATH=.:tools QT_QPA_PLATFORM=offscreen python3 REFERENCE/reference_runner.py --disable-helper --parallel --include-cache --counts 1 32 --report before.json
PYTHONPATH=.:tools QT_QPA_PLATFORM=offscreen python3 tools/apf_ps3_speed_benchmark.py --disable-helper --parallel --include-cache --counts 1 32 --report after.json
PYTHONPATH=.:tools QT_QPA_PLATFORM=offscreen python3 REFERENCE/reference_runner.py --disable-helper --parallel --include-cache --counts 32 --repeat-inputs 1 --report before-repeated.json
PYTHONPATH=.:tools QT_QPA_PLATFORM=offscreen python3 tools/apf_ps3_speed_benchmark.py --disable-helper --parallel --include-cache --counts 32 --repeat-inputs 1 --report after-repeated.json
PYTHONPATH=.:tools QT_QPA_PLATFORM=offscreen python3 tools/apf_ps3_speed_benchmark.py --parallel --include-cache --counts 1 32 --report after-native.json
PYTHONPATH=.:tools python3 tools/apf_ps3_byte_parity.py --reference-writer REFERENCE/apf_logo_patch.py --reference-cache REFERENCE/apf_logocache_patch.py --reference-helper REFERENCE/apf_h7a_optimal --report retail-parity.json
```

For each pair of completed reports, require the same full count list and compare
`packages` (including every fit receipt), `output_pack_sha256` and
`linked_cache_sha256` in every run. Compare `after-native.json` against the
committed J10 `reports/b69_j10/after_complete.json` using the same fields.
Do not compare partially written reports; the benchmark saves each completed
count incrementally. The retail parity tool asserts whole-package equality.

The native-disabled command affects parent and spawn workers; its JSON records
the selected policy. `--repeat-inputs 1` repeats both independent layers across
32 destinations, never copies l0 into l1. Delete the temporary reference directory
afterwards. Do not distribute any retail build or scratch output.

## Offscreen walkthrough replay

```sh
QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tools/apf_gui_replay_offscreen.py --book-identity-screenshots docs/mod_editor/apf2k8_book_identity --receipt reports/b70_apf1/book_identity_replay.json
```

This focused replay uses the owned default source, or `--source <game-folder>`.
It checks the actual worker, staging and project reopen; it does not launch Xenia.
Regenerating the reviewed images requires updating their exact pins in both
packaging gates using the instructions in `WIRING.md`.

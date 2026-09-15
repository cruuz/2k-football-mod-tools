# Beta 70 A2 verification reproduction

Run the command stored in each `results.json` row as a standalone process from the repository root.
The common environment is `QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tools`.
No emulator or audio playback is used.

- `standalone/results.json`: every suite named by T1/T3/APF-1 and the A2 brief, including the three Music suites without scoped delegation.
- `gameplay-final/results.json`: complete Gameplay suite after updating its old generic help assertion to the exact T3 wording.
- `closure-final/results.json`: complete provider integrity, older registry audit and phase1 packaging suites after extending the provider closure and count.
- `registry-consumers-final/results.json`: complete catalog suite with the new uniform capability and exact counts.
- `wiring-readback/results.json`: actual completion consumers and the jersey reader/state transitions.
- `digit-before/results.json` and `digit-candidate/results.json`: the same eleven standalone digit/importer suites before and after the exact optional T1 insertion. Both have the same three missing-private-input failures. The candidate was reverted; final encoder and visual-project bytes equal their before-candidate copies.
- `gates/apf-stage.json`: commands, full outputs, and exact source/size/hash of four existing reviewed extractor artifacts used only in the temporary stage. The stage was removed.

APF staging copies every regular file in `packaging/apf2k8-release-allowlist.txt`, then runs:

```sh
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python3 <stage>/packaging/check_apf2k8_mod_studio_release.py <stage>
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen python3 <stage>/packaging/check_apf2k8_mod_studio_runtime.py
```

The checker intentionally requires a staged tree. The bare release-check command needs a `release_root` argument; the runtime check in the development root refuses `extracted/`. Neither refusal was suppressed. A copy of the complete APF installer suite was also run standalone in a hydrated source stage after the gates. Its own package fixtures copy only allowlisted files. Two subprocess checks disable user-site packages and cannot import this host's user-installed `capstone`; the exact output is retained in `gates/installer-hydrated.log`.

The direct registry check is:

```sh
python3 -m mod_editor.capabilities.validate_registry --skip-file-checks
```

`packaging/repin.py --apply` ran after edits and last before each writer commit. `git diff --check` and the staged diff check are required. The 128 scorebug/scorebar code, data, tool and test files in `protected-files.json` must remain byte-identical to `8b4e3dbf`.

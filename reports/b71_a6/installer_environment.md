# Installer retry environment

The first installer run used the private interpreter for the parent process, but `_launcher_python()` resolves `python3` from `PATH` for its isolated child processes. Those children used `/usr/bin/python3` with `PYTHONNOUSERSITE=1`, so the installed user-site Capstone was unavailable.

The successful rerun prepended `<worktree>/.scratch/test-python/bin` to the inherited `PATH` and ran:

```sh
env -u PYTHONPATH python3 tests/mod_editor/test_apf_studio_installer.py
```

`reports/b71_apf5/prepare_test_python.py` created that private environment from the installed, pinned Capstone 5.0.7 with system site packages. Its file hashes are retained in `prepare-test-python.log`. Both isolated launcher probes now use this same dependency environment. No product source, test assertion, or system installation changed. The original failure log and corrected log are both retained; the latest ledger entry is the corrected result.

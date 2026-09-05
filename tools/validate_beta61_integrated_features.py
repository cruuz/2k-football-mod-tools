#!/usr/bin/env python3
"""Run the standalone offline gates for the integrated beta-61 capabilities."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "test_nfl2k5_animation.py",
    "test_nfl2k5_xbe_space.py",
    "test_nfl2k5_guardian_cap.py",
    "test_nfl2k5_music_banks.py",
    "test_nfl2k5_music_metadata.py",
    "test_nfl2k5_music_acceptance.py",
    "test_music_service.py",
    "test_nfl2k5_music_build.py",
    "test_nfl2k5_music_policy.py",
    "test_nfl2k5_season_cap.py",
    "test_nfl2k5_scorebug_runtime.py",
    "test_nfl2k5_scorebug_resources.py",
    "test_nfl2k5_screen_timing.py",
    "test_nfl2k5_read_option.py",
    "test_beta61_integration.py",
)


def main():
    environment = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen",
                       MOD_STUDIO_NO_UPDATE_CHECK="1")
    failed = []
    for name in TESTS:
        try:
            result = subprocess.run([sys.executable, str(ROOT / "tests/mod_editor" / name)],
                                    cwd=ROOT, env=environment, timeout=420, check=False)
            passed = result.returncode == 0
        except subprocess.TimeoutExpired:
            passed = False
        if not passed:
            failed.append(name)
        print(f"{'PASS' if passed else 'FAIL'} {name}", flush=True)
    print(f"BETA61_VALIDATION files={len(TESTS)} passed={len(TESTS)-len(failed)} failed={len(failed)}", flush=True)
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())

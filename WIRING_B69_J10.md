# Beta 69 J10 integration

Registry rows added: **0**. No capability, preset, game-code or STFS change.
The APF studio files are owned by this job. No protected implementation file
was edited. The helper remains mode **0755**, with the same exact-file acceptance
rules. Its original optimal mode is byte-identical; the added greedy mode is
checked against the historical Python parse, including candidate limits and ties.

The new binary requires these two protected packaging pin updates after review.
Do not change any executable acceptance conditions or allowlist entries. The
source and binary already have APF release allowlist entries.

In `packaging/check_apf2k8_mod_studio_release.py`, module constants immediately
after `REVIEWED_H7A_BINARY = "tools/apf_h7a_optimal"`, replace the size/hash with:

```python
REVIEWED_H7A_BINARY_SIZE = 18_568
REVIEWED_H7A_BINARY_SHA256 = (
    "d081d19c0078f768d2cb935732c910945c55d372dd9e1cc2b3e16ef9cfcf86a0"
)
```

In `packaging/check_apf2k8_mod_studio_runtime.py`, module constants immediately
after `H7A_ENCODER = ROOT / "tools/apf_h7a_optimal"`, replace the size/hash with:

```python
H7A_ENCODER_SIZE = 18_568
H7A_ENCODER_SHA256 = (
    "d081d19c0078f768d2cb935732c910945c55d372dd9e1cc2b3e16ef9cfcf86a0"
)
```

The owned `tools/apf_field_art_patch.py` predicate already carries these exact
pins. Reproduce the artifact with:

```sh
cc -O3 -std=c99 -Wall -Wextra -Werror -s tools/apf_h7a_optimal.c -o /tmp/apf_h7a_optimal
```

This command describes the measured Linux build, not a cross-platform build
promise. The fallback is pure Python and does not require a compiler.

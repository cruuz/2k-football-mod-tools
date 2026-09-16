Implemented Linux update staging, local-runtime preservation, launch checks,
startup acknowledgement and automatic rollback. Windows installer handoff is
unchanged. The hotfix tag is `beta-71.1` and is recognized by beta 69/70/71.

146 tests and both products' staged release/runtime gates passed. The original
runtime-loss failure and the fixed real-payload update were reproduced headlessly.
The exact reported SteamOS session remains UNWITNESSED; the raw beta 70 tarball's
old detector hides Update now because it contains shipped tests.

Branch: `astra/b71-u1-linux-update`, private Git directory `.scratch/private.git`.
Bundle: `.scratch/astra-b71-u1.bundle`. Base: `02bbadd1`.
Evidence, limits, commands, timings and exits: `ASTRA_REPORT.md` and `reports/b71_u1/`.
No push or emulator. Existing local-runtime installs should install the hotfix
manually; an old updater cannot acquire these safeguards before its first update.

ASTRA_DONE

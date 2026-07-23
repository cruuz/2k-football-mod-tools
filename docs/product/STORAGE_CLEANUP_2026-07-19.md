# Storage cleanup receipt — 2026-07-19

## Outcome

- Target filesystem: `/dev/sda1`, mounted at `/media/noah/Storage`.
- Before: effectively **0 bytes available** (`100%` in `df`'s rounded view).
- Immediate verification: **274 GiB available**, **85% used**.
- Settled verification after delayed block reclamation: **281 GiB
  available**, **84% used**.
- Removed: **96 files**, totaling **297,265,838,080 bytes**
  (**276.85 GiB**).

## What was removed

Only large, reproducible outputs under these three generated-work roots were
eligible:

- `for codex 1.0/build`
- `for codex 1.0/.codex-tmp`
- `.codex-tmp` at the Storage-drive root

The deleted files were generated NFL 2K5 modded XISOs, duplicated APF game
package chunks used by runtime/build experiments, and large extracted package
copies inside temporary proof directories. The cleanup retained each small
workflow JSON, audit record, checksum, log, source patch, and release archive,
so the deleted game-sized outputs can be rebuilt from the protected originals.

## Explicitly protected

- Original/source game dumps and the canonical extracted source trees.
- All source code, uncommitted Xenia census-hook work, tools, tests, and docs.
- All sealed release archives, including APF Alpha.23 and 2K5 RC8.
- The Giants GIMP export bundle and replacement/project data.
- Screenshots, logs, manifests, research receipts, and the unique APF Track 12
  capture WAV.
- `/media/noah/Storage/Projects`, `.compress_scratch`, `.etv-dl`, OBS
  recordings, Steam, and every unrelated personal/media project.

## Recovery note

The files were deleted directly rather than moved to Trash, so they are not
recoverable from the desktop Trash. They were selected specifically because
they are derived build/runtime outputs and can be regenerated from the retained
source dumps, code, and workflow receipts. No user-authored source asset was
removed.

## Post-seal follow-up — 2026-07-20

After the corrected 2K5 RC9 and APF Alpha.25 archives passed clean extraction,
runtime, retail-free, and deterministic re-archive checks, 13 superseded
staging, extraction, review, and stale-package directories were deleted from
`/home/noah/.codex-tmp`. They totaled **855,613,719 bytes** (about **816 MiB**).
These were generated copies only and are not recoverable; the sealed releases,
original dumps, projects, replacement assets, source code, and receipts remain.
The Storage drive then reported **294,034,956,288 bytes available** (about
**274 GiB**, **85% used**).

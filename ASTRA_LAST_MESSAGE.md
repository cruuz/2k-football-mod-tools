Implemented on `astra/b71-t4-project-load-equipment-fit` from `e2f5c6e6`.

- Projects retain unfitting equipment with its exact “needs refit” message.
- Normal/mud checks preserve fitting variants; optimal encoding precedes a compressed-size miss.
- Build offers one-click colour/size refitting with measured results and Undo.
- Reproduced the real 22H2 boundary: greedy 6,785 bytes, optimal 6,764 bytes, capacity 6,784 bytes. The generated beta 69/70 regression isolates the stripe palette floor.
- 31 standalone suites passed, 362 cases, no final skips. No emulator or push. In-game appearance and the original unavailable project remain UNWITNESSED.

Implementation commits: `e67a097f`, `b96f6791`.
Full evidence: [ASTRA_REPORT.md](ASTRA_REPORT.md).
Delivery: [.scratch/astra-b71-t4.bundle](.scratch/astra-b71-t4.bundle).
The sandbox makes shared Git metadata read-only; explicit-path commits live in `.scratch/t4.git` and the bundle.

ASTRA_DONE

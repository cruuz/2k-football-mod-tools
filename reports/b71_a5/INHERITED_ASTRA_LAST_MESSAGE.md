Integrated scorebug v2 wings and capsule fonts with colour v2.1 on `astra/b71-a5-scorebug-integrate` in `.scratch/private.git`.

All 14 standalone test programs passed, with five existing legacy-case skips in the font suite. Strict registry validation passed after restoring missing local evidence files. XBE gates passed: 119 memory-write tests and 131 cave-reference tests.

The detached combined disc build was attempted with Advanced and all four requested options enabled. The session mounts `/home/noah/2K5 Mod Studio Builds` read-only, so the access check failed before creating a disc or deleting anything. No disc option read-back is claimed. Run `bash reports/b71_a5/launch_testdisc71.sh` once that directory is writable.

Delivery: `.scratch/astra-b71-a5.bundle`, `ASTRA_REPORT.md`, and `reports/b71_a5/` with the builder, pin recipe, previews, and validation evidence. No push. No emulator launch.

ASTRA_DONE

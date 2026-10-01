# DESIGN: xc compact disc delivery, 2026-09-28

**PROVED OFFLINE:** Work started at `9de33371` on `job/b76-xc`. This checkout and the main repository had no `AGENTS.md`; the parent `/home/noah/AGENTS.md`, project index, and task brief were read. The existing untracked `ASTRA_BRIEF_XC.md` is excluded from delivery. Shared Git metadata is read-only, so delivery uses the authorized private Git and verified bundle route.

**PROVED OFFLINE:** Candidate D's 19 files total **5,924,337,664 bytes**. The standalone compact copy is **5,924,454,400 bytes**, down from **8,012,931,072 bytes**. It saves **2,088,476,672 bytes (26.06%)**, leaving **116,736 bytes** for the reserved prefix, volume descriptor, directories, and alignment. Every file's SHA-256 matches. See [per-file evidence](evidence/candidate-D-compaction.json).

**PROVED OFFLINE:** The append behavior is explicit in [historic_styles.rewrite_archive](../mod_editor/core/nfl2k5_historic_styles.py): changed packs are written starting at the old image end, then directory nodes are switched. It preserves old extents for rollback. [music_archive.write_named](../mod_editor/core/nfl2k5_music_archive.py) also appends grown named files, and [depth_chart_storage.write_image_xbe](../mod_editor/core/nfl2k5_depth_chart_storage.py) relocates a grown executable. These writers correctly address their new files, but previously no unconditional final pass reclaimed abandoned extents.

**PROVED OFFLINE:** [intro_videos._geometry](../mod_editor/core/nfl2k5_intro_videos.py) already compacts during the optional intro trim. It preserves current physical order, runs only when that option actually changes resources, and precedes the custom intro pass. It is not a general final repack switch that was accidentally disabled. Candidate D's inspection reports `custom_intro=custom` and `trim_intro_videos=foreign`; those states are unchanged by this work.

**DESIGN:** [xdvdfs_compact.py](../mod_editor/core/xdvdfs_compact.py) walks and snapshots bounded directory metadata, rejects malformed or overlapping extents before writing, and assigns new contiguous extents. It retains directory tree links, names, attributes, sizes, timestamp and other descriptor bytes, changing only physical start sectors and the root sector. The output is an extracted game partition at offset zero. Directories precede files, extents align to 2,048 bytes, and final length aligns to 65,536 bytes. The alignment agrees with the locally vendored extract-xiso constants `XISO_SECTOR_SIZE` and `XISO_FILE_MODULUS`. Unallocated sectors and file-sector suffixes are zeroed.

**PROVED OFFLINE:** The pinned USA retail source's physical file order is `update.xbe`, `default.xbe`, `dashupdate.xbe`, then packs `9 5 3 1 0 2 4 7 6 8 D B A C E F`. The new writer uses these names as ordering keys, never as fixed read addresses. All actual reads come from the input's own directory. Candidate D's grown archives and executable return to these original slots.

**DESIGN:** For other file inventories, private builds use the original source's physical order. The standalone command preserves physical order by default and accepts `--order-from ORIGINAL.iso` to restore a known earlier order. Unknown additional files follow the known files in source order. The outer archive and its virtual offsets are not rebuilt: all 19 named file payloads remain identical.

**DESIGN:** [mod_build](../mod_editor/core/mod_build.py) calls `finish_private` after all content writers, including custom/trimmed intro video, and before the final stock-book, named-preview and native play-scoring publication gates. This also covers composed project builds. Compaction is unconditional for disc outputs and has no opt-in toggle. Its evidence is recorded in `disc_compaction`; existing content-step ordering remains intact. The existing final output hash updates `result.image_size` and `result.image_sha256` so earlier intermediate hashes cannot masquerade as the finished image's hash.

**DESIGN:** Private builds rearrange their existing disposable image. A move runs only when its destination does not overwrite another unread source. Partial moves also protect the unread remainder of their own source. Whole self-overlaps copy in the appropriate direction. Cycles use at most a 1 MiB saved prefix, which opens a gap that subsequent moves drain. Copies use 1 MiB buffers and no disk scratch. File hashes are verified before and after. A failure discards the build's private stage before the existing publication boundary, preserving the source and any previous published output.

**DESIGN:** The implementation uses standard Python binary streams, seek, read, write, truncate and fsync. It creates no worker pool and has no dependency on Linux reflinks, hole punching, memfd, mmap or external repackers. Windows publication uses the existing platform compatibility helper after writer handles close. macOS and Windows native execution were not performed; portability is a design claim, with the no-`os.pread` fallback exercised offline.

**PROVED OFFLINE:** The standalone operation took **43.00 seconds** and peaked at **29,728 KiB RSS**. It created one streamed output, not extracted archives or an additional full image. See [resource measurement](evidence/standalone-resources.txt).

**PROVED OFFLINE:** The [standalone command](../tools/xdvdfs_compact.py) opens the input `rb`, refuses an existing output or sidecar, verifies all output payload hashes and directory metadata, then publishes without replacement. It carries the existing `.colour-lighting.json`, `.venues-2026.json`, and `.surfaces.json` receipts, whose resource pins do not depend on disc offsets. Both the module and command are on the [release allowlist](../packaging/release-allowlist.txt); [allowlist check](evidence/package-check.json).

**DESIGN:** Regenerate the proof copy with this command after applying the delivery:

```bash
python3 tools/xdvdfs_compact.py \
  '/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 candidate D 2026-09-28.xiso.iso' \
  '/media/noah/Storage/.b76-research/xc/astra-build/candidate-D-compact.xiso.iso' \
  --report '/media/noah/Storage/.b76-research/xc/astra-build/recreated-proof.json'
```

**PROVED OFFLINE:** Main's independent read-only directory walker and the vendored `extract-xiso -l` both find all 19 files and the same payload total. See [main walker](evidence/main-directory-walk.txt) and [extract-xiso listing](evidence/extract-xiso-list.log). Main's generic script prints `C` and `D` column labels; for this invocation they mean original D and compacted D, respectively. The Studio's parser independently agrees with the compactor's directory walk. `music_archive.Disc(..., descriptors=())` accepts both images' pack and outer-archive geometry.

**PROVED OFFLINE:** Full `mod_build.inspect(..., screen_timing="D")` reports **180 top-level fields** on both discs. Every status, setting, retail size/content pin and identity classification matches. Comparison excludes only the disc path, `disc_identity.image_size`, and each identity file's physical `offset` and `at_retail_offset` flag. Raw [source](evidence/source-inspection.json) and [compact](evidence/compact-inspection.json) reports retain these fields; [geometry differences](evidence/inspection-geometry.json) document them and [remaining differences](evidence/inspection-differences.json) is empty. The initial strict comparison correctly exposed geometry changes; the resumed verification uses those same completed inspections and explicitly scopes the exclusions.

**PROVED OFFLINE:** Anniversary rosters, extra moments, named previews, era rules, historic stock books, modern venues and modern surfaces all read `applied` before and after. D's pre-existing generic disc identity remains `unknown`, with the same reason about grown retail file sizes, and its pre-existing `foreign` option readings remain unchanged. This work does not relabel those existing statuses.

**PROVED OFFLINE:** The finished compact disc passes the builder's actual native play-scoring gate: **69 books, zero faults**. Every per-book result equals D's original published build receipt, including resource and executable hashes and native call coverage. Both archive readers find **4,451 outer entries** and **5,851,289,600 virtual archive bytes**. [Complete disc proof](evidence/disc-proof.json), [verification log](evidence/disc-verification.log).

**PROVED OFFLINE:** D's whole-image SHA-256 still matches its published build receipt: `449a3b90f0b4f7733bfd5589c132510265f4ee2f092e738777b811e4134de680`. The compact copy's SHA-256 is `36cd074774d5a8f62abe55a5aedf24d296276f79ccfd3d6644bdd2c8a6a2159f`. No file in `/media/noah/Storage/2K5 Discs/` was opened for writing, moved or deleted.

**PROVED OFFLINE:** Final tests passed **100 tests and 83 subtests**, with one optional repository-local retail fixture skipped. The focused run covers middle-file growth through the actual append writer, contiguous output, byte identity, retail/reference ordering, move cycles, partial and overlapping moves, buffer boundaries, 35 deterministic permutations, raw partition selection, a directory below the header, nested/empty/non-ASCII entries, malformed metadata, alias/output refusal, copied status receipts, no-`os.pread` fallback, and failed publication preserving existing outputs. Existing build, service and composition regressions also pass. [Summary](evidence/tests-summary.json), [focused run](evidence/focused-tests-final.log), [build regression run](evidence/build-regressions-final.log). Python compilation, shell syntax and `git diff --check` passed.

**PROVED OFFLINE:** The actual private-build mover ran on a full copy of D's original 8,012,931,072-byte layout and produced the **same complete image SHA-256 as the standalone command**. All per-file hashes passed again. It used **zero disk scratch** and needed **zero saved cycle bytes** on this particular layout; the synthetic cycle test exercises the 1 MiB cycle buffer separately. The complete private proof, including copying D and hashing, took **95.42 seconds** and peaked at **43,096 KiB RSS**. [Private-build proof](evidence/private-build-proof.json), [resource measurement](evidence/private-build-resources.txt), [log](evidence/private-build.log).

**PROVED OFFLINE:** The temporary disc and its three copied status sidecars were deleted after both proofs. Cleanup left **114,196,725,760 bytes free on NVMe**, above the 100 GB floor, and **20,820,230,144 bytes free on Storage**. No heavy process pool was launched, and no xemu, push or tag command was run. [Cleanup evidence](evidence/cleanup.json).

**DESIGN:** [prove_disc.py](prove_disc.py) repeats the status and archive checks, runs the builder's actual native play-scoring gate, and hashes the whole input against D's published build receipt. [prove_private.py](prove_private.py) subsequently removes the verified standalone copy, copies D read-only to the same authorized temporary output, runs the actual private mover, requires a byte-identical whole-image result, then deletes that image and its copied sidecars. The two temporary full images never coexist.

**DESIGN:** Main's follow-up is [lab_main.sh](lab_main.sh). It first hashes the recreated copy against the offline proof. It takes the shared lab lock and boots one headless emulator at a time through the existing Xvfb harness and read-only DVD mount. The first case selects Chiefs at Falcons, loading the new Mercedes-Benz venue. The second selects Anniversary moment 50, captures its preview, reads mode and book names, and watches the loaded field. Main must confirm a rendered play and advancing game clock in both cases. A script exit alone is not acceptance. Astra did not execute this script or launch xemu.

**INFERRED:** Restored retail file order should retain useful DVD seek locality, and the resulting image is smaller than the known 6,300,499,968-byte retail XISO. No physical DVD burn, Xbox hardware boot, seek benchmark or rendered gameplay is claimed by this offline job.

**DESIGN:** Delivery is a pathspec-only commit with the requested `Co-Authored-By` trailer, based directly on `9de33371`, bundled under `/media/noah/Storage/.b76-research/xc/astra-build/xc.bundle`. Main can verify and fetch that local bundle, then cherry-pick its `job/b76-xc` head. No push or tag is part of this delivery.

**DESIGN:** From main's intended checkout, import the verified local commit with:

```bash
git bundle verify /media/noah/Storage/.b76-research/xc/astra-build/xc.bundle
git fetch /media/noah/Storage/.b76-research/xc/astra-build/xc.bundle refs/heads/job/b76-xc
git cherry-pick FETCH_HEAD
```

**DESIGN:** After recreating the proof copy, run the lab follow-up with:

```bash
XC_DISC='/media/noah/Storage/.b76-research/xc/astra-build/candidate-D-compact.xiso.iso' \
  bash xc/lab_main.sh
```

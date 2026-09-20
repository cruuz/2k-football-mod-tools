# b74-v1: retail video inventory and safe boot trim

All game behavior remains UNWITNESSED. This report covers read-only retail inspection, bounded native x86 execution and synthetic archive transactions. No emulator, GUI display, audio playback, retail edit or release step was used.

The September 18 presentation report is incorrect about the movie inventory. The USA archive has **30 CRI Sofdec MPEG program streams**, totaling **1,037,568,000 bytes**. Four are boot movies, 23 are Crib reels, and three are menu promotion/training movies. `.mov` is a resource name suffix, not a QuickTime container. FFprobe identifies MPEG-1 video and ADX ADPCM audio (48,000 Hz, stereo) in all 30. The seven non-Crib streams are 640x480; the 23 Crib streams are 256x144. The native header reader compares `SofdecStream` at VA `0xEBD6B4`.

Inputs: XBE SHA-256 `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`; ISO SHA-256 `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`, 6,300,499,968 bytes. Every movie was hashed independently through the extracted archive and through the ISO; all matched. [inventory.json](reports/b74-v1/inventory.json) contains every SHA-256, resource ID, pack seam, exact ISO byte offset, named file and FFprobe result.

Inventory scope: all 4,323 indexed outer entries and all named ISO files were inspected. Exactly 30 outer headers start with the MPEG pack signature `00 00 01 BA`; all resolve by CRC32 of the uppercase UTF-16LE resource name. No loose video file exists. These are complete raw outer streams, with no inner chunk ID. The known scene/resource containers remain a separate asset class, not video streams. This is a format-aware outer inventory and native-consumer census, not a claim that arbitrary compressed bytes were exhaustively recognized as every conceivable codec.

| Movie resource | Outer / CRC ID | Exact bytes | Pack:offset (+ length if split) | ISO byte offset(s) | Scope / caller | Hypothetical payload saving with 2,048-byte marker |
| --- | --- | ---: | --- | --- | --- | ---: |
| espn_videogames.mov | 4293 / 0xef47f2a2 | 3,973,120 | D:25114624 +3973120 | 4179243008 | boot/publisher / 0x74bce | 3,971,072 |
| vc.mov | 4294 / 0xadb25e4f | 5,425,152 | D:29087744 +5425152 | 4183216128 | boot/publisher / 0x74bce | 5,423,104 |
| espn_game_sound.mov | 4295 / 0xf7e8601f | 3,256,320 | D:34512896 +3256320 | 4188641280 | boot/publisher / 0x74bce | 3,254,272 |
| intro.mov | 4296 / 0xda93a0c6 | 50,241,536 | D:37769216 +50241536 | 4191897600 | boot/publisher / 0x74bce | 50,239,488 |
| all_games.mov | 4297 / 0x30487606 | 96,962,560 | D:88010752 +96962560 | 4242139136 | menu promotion/tutorial / 0x363501 | 96,960,512 |
| crib_100percent.mov | 4298 / 0x176c9e5e | 8,337,408 | D:184973312 +8337408 | 4339101696 | Crib reel / 0x272a94 | 8,335,360 |
| crib_berman.mov | 4299 / 0x5ce79069 | 23,930,880 | D:193310720 +23930880 | 4347439104 | Crib reel / 0x272a94 | 23,928,832 |
| crib_celectra.mov | 4300 / 0xd44e8353 | 25,511,936 | D:217241600 +25511936 | 4371369984 | Crib reel / 0x272a94 | 25,509,888 |
| crib_darquette.mov | 4301 / 0x26e70ca3 | 16,470,016 | D:242753536 +16470016 | 4396881920 | Crib reel / 0x272a94 | 16,467,968 |
| crib_fflex.mov | 4302 / 0x7ca59ad7 | 21,512,192 | D:259223552 +21512192 | 4413351936 | Crib reel / 0x272a94 | 21,510,144 |
| crib_jkennedy.mov | 4303 / 0x6c142e93 | 22,644,736 | D:280735744 +22644736 | 4434864128 | Crib reel / 0x272a94 | 22,642,688 |
| crib_nfl2k.mov | 4304 / 0xf7bf664b | 34,668,544 | D:303380480 +5754880; E:0 +28913664 | 4457508864; 5546938368 | Crib reel / 0x272a94 | 34,666,496 |
| crib_nfl2k1.mov | 4305 / 0xf27c8912 | 26,591,232 | E:28913664 +26591232 | 5575852032 | Crib reel / 0x272a94 | 26,589,184 |
| crib_nfl2k2.mov | 4306 / 0x194b3211 | 28,805,120 | E:55504896 +28805120 | 5602443264 | Crib reel / 0x272a94 | 28,803,072 |
| crib_nfl2k3.mov | 4307 / 0xf689592f | 47,966,208 | E:84310016 +47966208 | 5631248384 | Crib reel / 0x272a94 | 47,964,160 |
| crib_nfl2k4.mov | 4308 / 0x14554256 | 18,558,976 | E:132276224 +18558976 | 5679214592 | Crib reel / 0x272a94 | 18,556,928 |
| crib_sc1.mov | 4309 / 0x4f4e79cb | 13,410,304 | E:150835200 +13410304 | 5697773568 | Crib reel / 0x272a94 | 13,408,256 |
| crib_sc10.mov | 4310 / 0xab35cf63 | 14,424,064 | E:164245504 +14424064 | 5711183872 | Crib reel / 0x272a94 | 14,422,016 |
| crib_sc2.mov | 4311 / 0xa479c2c8 | 12,095,488 | E:178669568 +12095488 | 5725607936 | Crib reel / 0x272a94 | 12,093,440 |
| crib_sc3.mov | 4312 / 0x4bbba9f6 | 6,963,200 | E:190765056 +6963200 | 5737703424 | Crib reel / 0x272a94 | 6,961,152 |
| crib_sc4.mov | 4313 / 0xa967b28f | 12,697,600 | E:197728256 +12697600 | 5744666624 | Crib reel / 0x272a94 | 12,695,552 |
| crib_sc5.mov | 4314 / 0x46a5d9b1 | 6,318,080 | E:210425856 +6318080 | 5757364224 | Crib reel / 0x272a94 | 6,316,032 |
| crib_sc6.mov | 4315 / 0xad9262b2 | 9,363,456 | E:216743936 +9363456 | 5763682304 | Crib reel / 0x272a94 | 9,361,408 |
| crib_sc7.mov | 4316 / 0x4250098c | 7,239,680 | E:226107392 +7239680 | 5773045760 | Crib reel / 0x272a94 | 7,237,632 |
| crib_sc8.mov | 4317 / 0xb35b5201 | 13,692,928 | E:233347072 +13692928 | 5780285440 | Crib reel / 0x272a94 | 13,690,880 |
| crib_sc9.mov | 4318 / 0x5c99393f | 13,568,000 | E:247040000 +13568000 | 5793978368 | Crib reel / 0x272a94 | 13,565,952 |
| crib_steveo.mov | 4319 / 0xc6277bd8 | 25,849,856 | E:260608000 +25849856 | 5807546368 | Crib reel / 0x272a94 | 25,847,808 |
| crib_towens.mov | 4320 / 0xc343351f | 6,549,504 | E:286457856 +6549504 | 5833396224 | Crib reel / 0x272a94 | 6,547,456 |
| tips_defense.mov | 4321 / 0xed854239 | 191,178,752 | E:293007360 +8806400; F:0 +182372352 | 5839945728; 5848752128 | menu promotion/tutorial / 0x3634de | 191,176,704 |
| tips_offense.mov | 4322 / 0xc21784b3 | 269,361,152 | F:182372352 +269361152 | 6031124480 | menu promotion/tutorial / 0x3634be | 269,359,104 |

The savings column is a payload/sector equivalent, not an applied cut for the protected 26 streams. No Crib, training or promotional movie is selected. Simply zeroing bytes in place frees zero physical image bytes. Deleting an index row is unsupported because stable outer ordinals must survive. Physical savings require updating archive lengths/offsets, XDVDFS extents and truncating the separate output. All stream lengths and the retained markers are 2,048-byte multiples, so per-stream sector savings equal the stated payload reductions; placement gaps are reported separately.

Boot and publisher path: `0x748A0` initializes the frontend. `0x74180` displays the legal/Sega TXTR screens using the first two name/duration rows at `0x4E9720`; `0xF5D60` requests TXTR, not a movie. Then the loop `0x74BBB..0x74BE3` traverses rows `0x4E9730..0x4E9748` and calls `0x178150` at `0x74BCE`: ESPN Videogames, VC, ESPN Game Sound, intro. The new ten-byte sequence at `0x74BBB` calls the original pending-work barrier `0x432D0`, then jumps to the existing clock reset at `0x74BE3`. The barrier waits for `[0xB09584]` to clear, pumping `0x38F50` as retail does; skipping movies must preserve this startup dependency. It allocates no new code/data, bypasses the movie opener entirely, and preserves the earlier screens and later initialization.

Crib path: the 23 names in the resource-pointer table at `0x519C60` are selected at `0x272A6F`, opened at `0x272A94` through `0x3CBBF0`, and updated by `0x272A60`. The shared player and this consumer are byte-identical after the boot patch. Outer 4266 is **crib_intro.iff**, whose SCNE `intro` is requested at `0x276932` with type SCNE at `0x276937`. It is not the 50,241,536-byte boot intro movie.

Menu promotion/training: `tips_offense` is played by `0x3634B0` (call `0x3634BE`), `tips_defense` by `0x3634D0` (call `0x3634DE`), and `all_games` by `0x3634F0` (call `0x363501`). Function pointers are at `0x540730`, `0x540764`, `0x540798`, in the menu records including Offensive Training, Defensive Training and ESPN VIDEOGAMES. These use the same `0x178150` player, but are not boot-loop rows. All are preserved.

Attract/demo: no separate attract movie is identified. Across every file-backed XBE section, the only near-call sites of `0x178150` are the boot call and those three menu calls; there is no stored absolute pointer to that function. `0x3CBBF0` is called only by that shared player and the Crib consumer. The Demo Mode text is drawn at `0x63DEF..0x63DF9` by the gameplay HUD. The census supports a real-time demo rather than a separate indexed attract stream; it does not establish every possible runtime state or generated indirect call.

In-game: Berman remains SCNE `bermanintro`, outer 21/chunk 0 (643,872 stored bytes), and the studio remains SCNE `sc_studio`, outer 8/chunk 2 (427,136 stored bytes). The halftime/postgame director/scene resources are not the Crib Berman movie. No in-game resource is changed. Every one of the other 4,319 outer entries is hash-verified by the trim writer, including outer 21, GAMEDATA 346, and all 26 protected movies.

Native loader evidence and limits

`tests/nfl2k5_movie_native.py` maps the retail XBE with read-only executable memory and runs the real list registration (`0x3CBBF0`), asynchronous header callbacks (`0x3CB8B0`, `0x3CB750`), pump/state machine (`0x3CD120`), sizing functions and cleanup (`0x3CCF90`). Host services provide named-file open/read completion, clock, close and allocation failure. The real pre-play readiness barrier at `0x432D0` executes. Ordinary header cases start with its pending-work counter zero; a separate native skip case starts at two and verifies both pump completions before the continuation. `0x38FB0` redirects the native global record at `0xB04E24` to zeroed scratch memory. The host pump at `0x38CD0` delivers queued read callbacks and then executes native `0x3CD120`. Read completion advances the file position by the completed byte count; out-of-bounds reads fail. These are explicit harness preconditions, not proof of the lower archive file service or whole startup readiness. The callbacks see the actual retail stream headers. No MPEG frame decoder, audio device, GPU or whole game is run.

| Intervention | Offline result | Bound / consequence |
| --- | --- | --- |
| Missing resource in named-file service | All 30 names finish header failure, unlink the context and return 0 through the shared player. | No allocation request; boot return 0 advances to the next row. Does not prove a physically deleted index row is safe. |
| 2,048-byte nonmovie marker | All 30 names fail after reads at offsets 32 and 2,080, close/unlink, return 0. | No allocation request. This relies on the service rejecting a read beyond the declared resource extent; no full disc boot claimed. |
| Valid retail header | All 30 reach native size calculation after five bounded 128-byte reads. | Allocation is deliberately failed at the host boundary so native cleanup can be executed without starting the decoder. |
| Crib missing/marker using its own consumer | All 23 choices take state 1 to state 6 and pop the screen after failure, with no playback allocation. | Both cases are run through `0x272A60` and its real callback, with unrelated screen calls `0x26DA50`, `0x2712F0`, `0x2716A0` stubbed and the screen-pop service observed. Not an authorization to cut them. |
| Boot skip installed | Native loop slice takes the existing continuation with zero player calls. | The native pending-work barrier completes before the skip; no selected marker is opened. Retail return 0 or 1 visits all four rows; return 2 ends the loop after the first row. |
| Input skip | Native input gate accepts either bit `0x10` or `0x100` of mask `0x110`, sets the skip result, consumes input. | `0x1784F7..0x178534`, after the per-movie minimum time; all four boot rows have zero minimum time. Completion converts the skip result to return 2. |
| Native playback completion | The completion slice calls free at `0x17868C` and closes context at `0x178698` before returning. | Confirms buffer lifetime in the code; no playback timing or console peak measured. |

The shared player waits on readiness at `0x1781E0`, and on movie state 3 at `0x178670`; it does not wait for the original archive length or a fixed movie duration. The header callbacks request 128-byte blocks. A valid, shorter Sofdec stream still needs proper headers/decoder termination; arbitrary MPEG end bytes or a fabricated tiny valid video have not been proved. The implemented marker is deliberately not a playable stub. The boot branch makes its loader behavior irrelevant to the selected option.

For Crib playback, the existing consumer has a separate input mask `0x220` at `0x272B0A`, stops via `0x3CC020` at `0x272B20`, waits for state 3, and uses its normal cleanup path. That input path is statically mapped; only missing/marker cleanup was executed for the Crib in this job. Promotion/training movies retain the shared input/termination logic. No hang/skip statement here is an in-game observation.

Disc and memory budgets

| Quantity | Bytes |
| --- | ---: |
| Four retail boot movie payloads | 62,896,128 |
| Four retained markers | 8,192 |
| Net archive/sector saving | 62,887,936 |
| Separate retail placement-gap saving | 14,336 |
| Planned physical ISO saving | 62,902,272 |
| Planned output ISO size | 6,237,597,696 |
| Native boot movie allocation request, each, sequential | 10,171,344 |
| Each Crib stream through the shared player, header allocation request | 3,138,000 |
| New patch runtime allocation | 0 |
| Credit to GAMEDATA append ceiling | 0 |
| Current GAMEDATA append ceiling | 400,000 |
| Current scorebug usage (job input) | 325,216 |
| Remaining GAMEDATA allowance | 74,784 |

The cut helps disc space and avoids transient boot playback requests. It does **not** establish additional memory headroom at the later Berman peak. The 10,171,344 figure is an executed native allocation request, not measured live heap residency, fragmentation, total boot peak, or a four-times larger saving. Movies are played sequentially and free their buffer before returning. The code and data of the movie library are still mapped. No allocator limit is increased and no GAMEDATA byte is removed or appended. The 2K28 blocker remains the later memory ceiling.

Practical disc equivalents using the conservative 62,887,936 payload bytes: **944** 256x256 P8 base images with a 1,024-byte palette (66,560 bytes each); **711** with all nine unpadded mip levels plus palette (88,405 bytes each); or **2,535.16 seconds / 42.25 minutes** of 22,050 Hz stereo Xbox IMA ADPCM at 72 bytes per 64 stereo frames. As 48 kHz stereo 16-bit PCM it is **327.54 seconds**. The current jukebox writer requires stereo `cribmusic` plus mono `crib22` twins (`nfl2k5_music_banks.py:_project`), at 108 bytes per 64 frames together: the same budget holds **1,690.11 seconds / 28.17 minutes** of that paired payload. These exclude wrappers, alignment and codec metadata, and are storage equivalents, not promises that all assets can be resident. A separately loaded resource collection up to about 60 MiB could fit on disc, but it still needs a loader/lifetime design. This option neither creates a seventeenth physical archive volume nor proves a second simultaneously resident presentation pack.

Implementation and reproduction

Build exposes **Trim intro videos**, default OFF in the dataclass, all three presets and project settings. It is a Build-only, image-only option. It applies last inside the existing disposable build transaction. The retail movie SHA-256s, IDs, lengths, boot-loop/table/player guards and XBE section seals are checked; foreign payloads, mixed markers and markers without the skip refuse. The XBE patch is idempotent. Rebuilding an already cut image yields the same bytes with zero additional saving.

The existing archive writer can shrink only the final physical volume. Combining the older 417 MB Crib cut with this 60 MiB cut would exhaust that volume, so selecting both refuses before copying; an already Crib-cut source also refuses if its final volume is too small. Repartitioning all 16 volumes is outside this change. The XBE patches themselves compose in both orders.

Archive rebuild uses streaming I/O, preserves every outer ID, compacts output file extents, updates the final pack length and truncates the output. Readback hashes all retained resources and unrelated files before publication. Report fields separate payload savings, placement gaps, actual physical savings and zero GAMEDATA memory credit. Windows uses binary open flags, closed handles before `os.replace`, and `tempfile`; synthetic transactions pass the project non-POSIX shim.

```text
python3 tools/nfl2k5_movie_inventory.py <retail-extracted-game-folder> <retail.iso> --json inventory.json
python3 -m mod_editor.core.nfl2k5_intro_videos plan <retail.iso>
python3 -m mod_editor.core.nfl2k5_intro_videos rebuild <retail.iso> <separate-output.iso>
python3 tests/mod_editor/test_nfl2k5_intro_videos.py
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_build_panel_qt.py
```

[retail_plan.json](reports/b74-v1/retail_plan.json) is a read-only plan, **not a full retail rebuild receipt**. Actual shrink, all-resource verification, idempotence, publication/failure cleanup, source preservation and non-POSIX equality were exercised on a bounded synthetic 16-volume XISO with the pinned retail XBE read at test time. Retail bytes are never committed. [native.json](reports/b74-v1/native.json) records the 90 header/failure cases; further boot-loop, controller, Crib-consumer and cleanup assertions live in the test suite.

The primary worktree Git metadata is read-only. The `b74-v1` commit and incremental bundle use independent Git metadata under `.scratch/b74-v1/git`, an alternate read-only object store, and this same working tree. Base is `origin/main` at `6944f5626b17f2ec6c1b56d854c0d00ecc55cc9e`. No other checkout is edited.

Validation and integration limits

The final focused feature suite passes 14 tests, including all 90 movie header/failure cases, all 46 Crib-consumer failure cases, the native boot loop and controller gate, cleanup, 32-owner composition in both orders, source preservation, replay, rollback and non-POSIX file I/O. The existing Build suite passes 13 tests, Build panel 16, Build plan UI coverage seven, saved MyCareer/Build settings ten, beta-62 Build integration eight, and provider integrity eight. These are 76 passed tests across the seven focused suites; final suite outputs are recorded in the validation receipt.

The full memory-write gate passes all 119 tests. The full cave-reference gate passes all 131 tests. Those existing full-stack fixtures do not include this new owner; its ten-byte hook is independently checked against all 32 matrix owners in both orders and through the native barrier/skip tests. The full oracle suite completes 29 tests with 27 passes and exactly the same two source-drift errors. The two source-fingerprint oracle assertions separately reproduce `stale reservation source: mod_editor/core/mod_build.py; regenerate manifest` at `mod_editor/core/nfl2k5_cave_oracle.py:217`. The unchanged manifest hash is `4fff3467479f70680f6743d9d45fec40264bda97148e07ed324be4153b663c33`. Its Build fingerprint matches the base (`c386188cf46d7179318629b0c9e473496eaf2d4f1fb74f24d6d5ed21419ea7b8`), while this implementation hashes to `9d1471d7b282fd1154754c7b64e11cd1680082908a327958ff2a4b631f7c7233`. No other pinned source drifts. The job explicitly forbids regeneration, so these assertions are not reported as passed.

[WIRING_B74_V1.md](WIRING_B74_V1.md) supplies the protected packaging entry, a schema- and validator-checked capability row, and the future recorder integration for the ten-byte hook. Those integration actions were not performed. The direct source Build option is implemented and tested; this job performs no release or packaged-app acceptance.

**PROVED OFFLINE: pb-heap report, 2026-09-25**

PROVED OFFLINE: The loaded books add **zero main-heap bytes compared with retail in the native match-loading path**. They occupy two fixed executable buffers. More seriously, the supplied crash is reproducible as a play-scoring table-index fault, with no allocation involved. The saved fault is a read at `0x281607` from `0xE70C5F90`, not a resource read into NULL. Sources: [live-books.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/live-books.json), [books.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/books.json), [fault.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/fault.json), [fault-controls.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/fault-controls.json).

PROVED OFFLINE: This analysis used the supplied RAM copies, the retail executable and archive, the lab build receipt, and the current packs at `a7ebef06e6e41bfec26447726c4b1ac5459320a1` on `job/b76-pb3`. File paths, sizes and SHA-256 hashes are in [source-manifest.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/source-manifest.json). No xemu, push, production-code edit or pack edit was performed. Analysis programs and binary scratch outputs are under `/media/noah/Storage/.b76-research/pb/astra-build/heap/`; the repository deliverable is this report.

DESIGN: Labels here mean: **PROVED OFFLINE** is a direct file/snapshot measurement, execution of the game's instructions under Unicorn, or arithmetic over those measurements; **INFERRED** is an interpretation or counterfactual; **DESIGN** is a proposed next step. Reading a saved RAM copy does not claim a new witnessed game run. All byte counts below are decimal; main-heap block totals include the allocator header and alignment. Buffer payload, occupied pool content and allocation charge are distinguished.

PROVED OFFLINE: The requested scanner was run as follows. Its heap counts are independently reconciled by the complete block inventory. Sources: [watch-scan.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/watch-scan.json), [all-blocks.csv](/media/noah/Storage/.b76-research/pb/astra-build/heap/all-blocks.csv), [inventory.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/inventory.json).

```bash
python3 /media/noah/Storage/.b76-research/k1/harness/r4_ramscan.py   /media/noah/Storage/.b76-research/main/stall-pb3/watch-end.bin   --blocks   --json /media/noah/Storage/.b76-research/pb/astra-build/heap/watch-scan.json
```

PROVED OFFLINE: Main heap `0xB04E24` spans `0x81214100..0x8314D500`: **32,740,352 bytes**, with **32,609,280 used in 662 blocks** and **131,072 free in one block**. The copy contains **134,217,728 physical bytes**, but the title reports **67,108,864 bytes of managed physical memory** and the kernel accounts for **16,384 pages**. The extra-region pointers are zero. Source: [watch-scan.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/watch-scan.json).

PROVED OFFLINE: At the coin toss the same heap had **665 used blocks**, **32,613,888 used bytes**, and **126,464 free bytes**. The end copy has **4,608 fewer used bytes and three fewer blocks**. Sources: [cointoss-scan.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/cointoss-scan.json), [watch-scan.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/watch-scan.json). INFERRED: These endpoints provide no evidence of net heap growth during the captured interval; they cannot rule out a temporary peak between copies.

PROVED OFFLINE: Native `0x84EB0` asks for the largest available main-heap allocation minus `0x20000`, then manages at most `0x180000` of that reservation. The end copy's requested in-game size is **1,470,080 bytes**, charged as **1,470,208 bytes** including its header. Thus a nearly full main heap with roughly **128 KiB** left is expected from the reservation policy itself. Sources: [observations.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/observations.json), [native disassembly](/media/noah/Storage/.b76-research/pb/astra-build/heap/offline-disassembly.txt).

PROVED OFFLINE: Resource attribution follows the actual loader structures: collection head `[0xB09578]`; each collection's next pointer at `+0`, UTF-16 name at `+8`, resource list at `+0xC`, stream-cache pointer at `+0x10`, indexed-bank pointer at `+0x14`, and owning heap at `+0x20`. Resource nodes have next at `+0`, FourCC at `+0xC`, name pointer at `+0x10`, object at `+0x14`, and constructor/destructor at `+0x18/+0x1C`. Native `0x43D20` confirms list registration. Multiple texture roots inside one TSET allocation count as one block. Sources: [attribute.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/attribute.py), [cache_probe.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/cache_probe.py), [offline-disassembly.txt](/media/noah/Storage/.b76-research/pb/astra-build/heap/offline-disassembly.txt), and the existing [native loader fixture](/home/noah/2k-worktrees/b76-x2/tests/mod_editor/test_nfl2k5_scorebug_native.py).

PROVED OFFLINE: The following partition accounts for **all 662 blocks and all 32,609,280 used bytes exactly once**. Named ordinary collections account for **557 blocks / 20,341,120 bytes**. The semantic roles of the frame workspace and audio streaming slab remain INFERRED, while their pointers and sizes are measured. **30 blocks / 284,672 bytes remain semantically unclassified**, with their addresses and available global references retained in the CSV; they have not been assigned guessed asset names. Sources: [inventory.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/inventory.json), [all-blocks.csv](/media/noah/Storage/.b76-research/pb/astra-build/heap/all-blocks.csv), [global-refs.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/global-refs.json).

| Attribution | Blocks | Charged bytes | Evidence label |
| --- | ---: | ---: | --- |
| GLOBAL | 224 | 4,871,424 | PROVED OFFLINE |
| player render instances | 1 | 4,486,528 | PROVED OFFLINE |
| GAMEDATA | 174 | 3,043,840 | PROVED OFFLINE |
| CROWDHOME | 32 | 2,856,576 | PROVED OFFLINE |
| AWAY | 53 | 2,730,368 | PROVED OFFLINE |
| HOME | 53 | 2,730,368 | PROVED OFFLINE |
| STADIUM | 13 | 2,715,776 | PROVED OFFLINE |
| frame workspace | 1 | 1,474,816 | PROVED OFFLINE bytes; INFERRED role |
| in-game reservation | 1 | 1,470,208 | PROVED OFFLINE |
| cs subheap | 1 | 1,343,616 | PROVED OFFLINE |
| faces | 6 | 1,042,304 | PROVED OFFLINE |
| animation caches | 48 | 856,192 | PROVED OFFLINE |
| roster | 1 | 594,048 | PROVED OFFLINE |
| audio streaming slab | 1 | 589,952 | PROVED OFFLINE bytes; INFERRED role |
| DIRECTOR | 1 | 505,728 | PROVED OFFLINE |
| COACHAWAY | 2 | 353,536 | PROVED OFFLINE |
| COACHHOME | 2 | 353,536 | PROVED OFFLINE |
| unclassified | 30 | 284,672 | PROVED OFFLINE |
| CROWDAWAY | 3 | 179,968 | PROVED OFFLINE |
| portraits and mini | 6 | 113,792 | PROVED OFFLINE |
| audio bank indexes | 9 | 12,032 | PROVED OFFLINE |
| Total | 662 | 32,609,280 | PROVED OFFLINE |

PROVED OFFLINE: Selected largest allocations and asset-specific anchors follow. Addresses are block headers; user data begins at `+0x80`. The CSV supplies every remaining block and linked resource name. Sources: [all-blocks.csv](/media/noah/Storage/.b76-research/pb/astra-build/heap/all-blocks.csv), [caches.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/caches.json), [offline-disassembly.txt](/media/noah/Storage/.b76-research/pb/astra-build/heap/offline-disassembly.txt).

| Header address | Charged bytes | Attribution and pointer evidence | Evidence label |
| --- | ---: | --- | --- |
| `0x82b48180` | 4,486,528 | lo_body / hi_body / hi_head render-instance pool; [0xb65278] = 0x82b48200; allocation 0x90e5c and scene copies 0x90ebc.. | PROVED OFFLINE |
| `0x822cb000` | 1,656,960 | STADIUM / SCNE stadium | PROVED OFFLINE |
| `0x829dc900` | 1,474,816 | frame/render capture workspace; [0xacb0c0] = 0x829dc980; allocation 0x28492d; dimensions from 0x35510 | INFERRED |
| `0x82fc6600` | 1,470,208 | in-game block; [0xb61614] = 0x82fc6680; native 0x84eb0 | PROVED OFFLINE |
| `0x8195f780` | 1,343,616 | cs control structure and subheap; [0xb9e230] = 0x8195f800; subheap control 0x8195ff80 | PROVED OFFLINE |
| `0x812a6180` | 1,016,704 | FaceTextures slots; 0x812a5200 slots -> 0x812a6200 | PROVED OFFLINE |
| `0x825aff00` | 699,136 | HOME / TXTR bump_jersey | PROVED OFFLINE |
| `0x82670000` | 699,136 | HOME / TXTR bump_pants | PROVED OFFLINE |
| `0x8284a880` | 699,136 | AWAY / TXTR bump_jersey | PROVED OFFLINE |
| `0x8290a980` | 699,136 | AWAY / TXTR bump_pants | PROVED OFFLINE |
| `0x81214100` | 594,048 | ROST arena; [0xb72804] = 0x81214180 | PROVED OFFLINE |
| `0x818ce400` | 589,952 | eight audio stream buffers; [0xa8be14] = 0x818ce480; 0x12000 * 8 bytes; allocation 0xd0fa0..0xd0fc6 -> 0x3fec0 | INFERRED |
| `0x81848e00` | 505,728 | DIRECTOR / DRCT director | PROVED OFFLINE |
| `0x8164f000` | 461,824 | GLOBAL / SCNE hi_head | PROVED OFFLINE |
| `0x82210580` | 460,672 | STADIUM / SCNE field | PROVED OFFLINE |
| `0x814ffd00` | 393,472 | GLOBAL / TXTR diffusemap | PROVED OFFLINE |
| `0x8155fe00` | 393,472 | GLOBAL / TXTR specularmap | PROVED OFFLINE |
| `0x81e55380` | 132,352 | GAMEDATA / TXTR score_buga | PROVED OFFLINE |

PROVED OFFLINE: HOME and AWAY each have **53 allocations / 2,730,368 bytes**, almost entirely textures. Each includes separate **699,136-byte** `bump_jersey` and `bump_pants` blocks, **177,152-byte** clean/mud jersey and pants sets, and an **88,704-byte** helmet. The **4,486,528-byte** block is allocated at `0x90E5C`, stored in `[0xB65278]`, and populated with instances of `lo_body`, `hi_body` and `hi_head`. It is player rendering state, not a PLAY node pool. Source: [all-blocks.csv](/media/noah/Storage/.b76-research/pb/astra-build/heap/all-blocks.csv), [offline-disassembly.txt](/media/noah/Storage/.b76-research/pb/astra-build/heap/offline-disassembly.txt).

PROVED OFFLINE: STADIUM totals **2,715,776 bytes**: scene resources **2,247,424**, textures **468,096**, and `Fldd` **256**. Its named `stadium` scene alone is **1,656,960 bytes**; the `field` scene is **460,672 bytes**. GAMEDATA totals **3,043,840 bytes**, including scenes **1,529,856**, textures **1,120,768**, markers **177,408**, and seven `SMCD` resources totaling **173,056**. This collection contains HUD assets such as `score_buga`, `scorepanel`, play-clock/play-call graphics and the ticker, along with non-HUD resources. Therefore its whole total is not presented as a HUD-only cost. GLOBAL contains another **456,320 bytes of FONT allocations**. Source: resource type/name lists in [attribution.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/attribution.json) and block charges in [all-blocks.csv](/media/noah/Storage/.b76-research/pb/astra-build/heap/all-blocks.csv).

PROVED OFFLINE: FaceTextures has **23 slots** of **43,904 bytes**, in a **1,016,704-byte** allocation after slot bookkeeping and allocator overhead. FaceShapes has **23 slots** of **512 bytes**, in **18,688 bytes**. Including their contexts and indexes, faces total **1,042,304 bytes**. The animation-cache contexts and indexes plus their slot pools total **856,192 bytes**, including CELEBRATE **154,880**, WIPE **124,800**, and OVERLAY **116,736** for those pools alone. They are fixed resident caches, not one allocation for each play in a book. Source: [caches.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/caches.json), [inventory.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/inventory.json); cache layout also documented in [R4, section 1.6](</home/noah/Desktop/2K5-8 Editors/bigger-game-research/R4_game_side.md>).

PROVED OFFLINE: Audio-associated ordinary resources include GLOBAL AUSB descriptors **217,088 bytes** and AUDO **2,560**, plus GAMEDATA AUSB **2,560** and AUDO **4,096**. The named indexed banks `QB_at_line`, `sfx_safe` and `sfx_game`, including their table blocks at `+0xB0`, total **12,032 bytes**. Source: [attribution.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/attribution.json), [inventory.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/inventory.py), [all-blocks.csv](/media/noah/Storage/.b76-research/pb/astra-build/heap/all-blocks.csv). INFERRED: The separate **589,952-byte** slab is audio streaming storage: `[0xA8BE14]` points to it, the native allocator at `0xD0FA0` sizes it by **eight times 0x12000 bytes**, and the consumer manages stream slots. This label is supported by the audio allocation path but is not a named resource-list match. Source: [offline-disassembly.txt](/media/noah/Storage/.b76-research/pb/astra-build/heap/offline-disassembly.txt).

PROVED OFFLINE: These are main-heap costs only. The graphics arena is **48,713,728 bytes**, of which **704,768** are carved from the bottom and **15,268,516** from the top before the main heap, with **92 bytes** of main-heap boundary alignment. Source: [watch-scan.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/watch-scan.json). INFERRED: Main-heap audio descriptors do not represent all audio RAM; R4's arena map identifies separate DSOUND storage, display lists and frame surfaces outside this heap. Source: [R4, sections 1.3 and 1.9](</home/noah/Desktop/2K5-8 Editors/bigger-game-research/R4_game_side.md>).

PROVED OFFLINE: **No main-heap block belongs to either resident PLAY book.** `PLYBOOKHOME` at `0xB33EE8` points to `0xB75A40`, whose book name is NYG. `PLYBOOKAWAY` at `0xB33F0C` points to `0xB88DD0`, whose name is DAL. Both addresses are in executable data, below the main heap. Native slot getter `0xE2F10` returns `0xB75A40 + slot * 0x13390`. The PLAY loader `0x166610` selects these fixed buffers for native loading modes **1 and 2**; its different mode-zero path calls the heap allocator. Sources: [attribution.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/attribution.json), [live-books.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/live-books.json), [offline-disassembly.txt](/media/noah/Storage/.b76-research/pb/astra-build/heap/offline-disassembly.txt).

PROVED OFFLINE: The exact comparison below uses retail archive resources and the **books actually recovered from the failed snapshot**, rather than substituting a newer compilation. Each book body is **78,736 bytes**; the usual uncompressed resource adds a **32-byte** wrapper for **78,768 bytes**. Both loaded slots together reserve **157,472 executable-data bytes** in retail and in this run. There is no larger decompressed body or compression staging buffer in the tested PLAY path. Sources: [books.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/books.json), [live-books.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/live-books.json), [book_probe.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/book_probe.py), [live_books.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/live_books.py).

| Measurement | NYG retail | NYG snapshot | DAL retail | DAL snapshot | Evidence label |
| --- | ---: | ---: | ---: | ---: | --- |
| Body / fixed slot bytes | 78,736 | 78,736 | 78,736 | 78,736 | PROVED OFFLINE |
| Standard wrapper plus body | 78,768 | 78,768 | 78,768 | 78,768 | PROVED OFFLINE |
| Main-heap charge in match loader | 0 | 0 | 0 | 0 | PROVED OFFLINE |
| Plays | 269 | 269 | 269 | 269 | PROVED OFFLINE |
| Formations | 43 | 43 | 41 | 41 | PROVED OFFLINE |
| Personnel categories | 22 | 22 | 24 | 24 | PROVED OFFLINE |
| Used nodes | 2,609 | 2,948 | 2,674 | 3,249 | PROVED OFFLINE |
| Used node-content bytes | 20,872 | 23,584 | 21,392 | 25,992 | PROVED OFFLINE |
| Declared UTF-16 name-pool bytes | 8,882 | 9,560 | 8,744 | 10,212 | PROVED OFFLINE |

PROVED OFFLINE: NYG uses **2,712 more node-content bytes and 678 more name bytes**; DAL uses **4,600 more node-content bytes and 1,468 more name bytes**. Those increases consume previously available bytes inside the same fixed buffers. Node capacity remains **3,500 nodes / 28,000 bytes**; the name area remains **11,088 bytes**. The fixed play table holds **270 records of 96 bytes**, or **25,920 bytes**, and both teams use **269 records**. Sources: preceding measured comparison; constants in [PLAY inspector](/home/noah/2k-worktrees/b76-x2/mod_editor/core/nfl2k5_playbook_inspector.py) and [formation/play writer](/home/noah/2k-worktrees/b76-x2/mod_editor/core/nfl2k5_formation_play_writer.py).

PROVED OFFLINE: The lab build's defense-stage counts were NYG **2,870** and DAL **3,171** nodes. The later `kickoff_returns` step changes the node-count byte at resource offset **96**, from `0x36` to `0x84` for NYG and `0x63` to `0xB1` for DAL, adding **78 nodes each**. This accounts for the snapshot counts. Source: [lab-kickoff-receipts.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/lab-kickoff-receipts.json) extracted from [lab 3 build receipt](/media/noah/Storage/.b76-research/pb/lab/pb-lab3.xiso.build.json). The current phase-4 pack-only composition has the same **2,870 / 3,171 node counts**, but **9,584 / 10,224 name bytes**; these are kept separate from the actual crash inputs. Source: [books.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/books.json).

PROVED OFFLINE: All **64 current packs** compose into **32 team PLAY resources**, not 64 simultaneous resident books. The native experiment ran every retail and current-authored resource in both native match-loading slots: **128 loads**, each reading **78,736 bytes**, with **zero heap delta and zero calls to observed allocator entries** `0x48700`, `0x48730`, `0x483D0`. The two recovered snapshot books added **four more loads** with the same result. The initializer `0xE0D90` relocates pointers and calls the native play validator; it does not allocate expanded per-play structures. All **8,460 play records** per retail/authored league pass through the initializer in this experiment. Sources: [books.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/books.json), [book-probe.log](/media/noah/Storage/.b76-research/pb/astra-build/heap/book-probe.log), [live-books.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/live-books.json), [offline-disassembly.txt](/media/noah/Storage/.b76-research/pb/astra-build/heap/offline-disassembly.txt).

PROVED OFFLINE: Fixture boundaries are explicit: native mode selection, slot selection, resource registration, heap, book initialization and validation execute; file completion is supplied at `0xECD90`, and scheduling the next unrelated resource at `0x43A20` is suppressed. A zero-count roster saved-audible list is supplied. Snapshot serialization runs native `0x161A70`, then restores the fixed resource-link header from retail before reloading because the serializer only relocates book fields. Its output hashes are reconstructed snapshots, not claimed disc hashes. Sources: [book_probe.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/book_probe.py), [live_books.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/live_books.py).

INFERRED: These measurements rule out a resident-book heap-footprint increase as the explanation for this crash. They do not prove that different selected plays can never change later animation, audio or cutscene activity. That behavioral question requires different evidence from the loader. The lab-2 full-game control supplied in the job is therefore useful, but it does not establish an allocation failure or a larger PLAY allocation in lab 3.

PROVED OFFLINE: **The crash's saved exception contradicts the proposed NULL-read signature.** At `0xD006677C`, the exception record is `C0000005, 0, 0, 00281607, 2, 0, E70C5F90`: an access violation from a read at `0x281607`, targeting `0xE70C5F90`. The same instruction address appears in the supplied [gdb samples](/media/noah/Storage/.b76-research/main/stall-pb3/gdb-capture.txt). Native instruction `0x281607` is `fld dword ptr [eax*4 + 0xC5D4C0]`. Source: [fault.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/fault.json), [offline-disassembly.txt](/media/noah/Storage/.b76-research/pb/astra-build/heap/offline-disassembly.txt).

PROVED OFFLINE: Replaying native `0x2815F0` with the saved Dallas play at `0xB8FB2C`, index **153**, name **17 Inside Zone**, and argument **3** recovered from caller frame `0xD006686C+0x10`, reproduces the exact fault without any instruction stubs. Native `0x281300` finds opcode `0x16`; the operand evaluation returns **-1**, converted to `0xFFFFFFFF` at `0x281343`. The lookup at `0x51C980` consequently reads the preceding word `0x3991A2B4`; using that as the next index gives `(0x3991A2B4 * 4 + 0xC5D4C0) mod 2^32 = 0xE70C5F90`. Sources: [fault_probe.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/fault_probe.py), [fault.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/fault.json), [observations.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/observations.json).

PROVED OFFLINE: Replacing only the Dallas book with the current authored native-loaded book reproduces the same read; replacing it with retail at the same play index returns without a fault. The retail call at that index is a control, not a claim that its play semantics are identical. The fault functions' bytes match the retail executable. Sources: [fault-controls.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/fault-controls.json), [fault_controls.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/fault_controls.py), [fault-code-identity.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/fault-code-identity.json), [offline-disassembly.txt](/media/noah/Storage/.b76-research/pb/astra-build/heap/offline-disassembly.txt).

PROVED OFFLINE: The resource worker's destination is **nonzero**, `[0xA7D364] = 0xB09550`, and its request size is **32 bytes**. The currently selected resource heap, `[0xB12034] = 0x8195FF80`, has **1,341,312 bytes free in one block**. `[0xB09584] = 1` establishes only that the loader is busy at this snapshot. Sources: [observations.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/observations.json), [watch-scan.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/watch-scan.json). INFERRED: This is a reproducible book/scoring compatibility defect, not demonstrated main-heap exhaustion. The earlier Berman failure mechanism should not be assigned from bugcheck `0x1E` and loader-busy alone.

DESIGN: Follow up on the opcode operand and its native scoring-domain contract, starting with this exact Dallas call and then sweeping authored run calls. Extend validation to the consumer that failed. The current syntactic/native-load checks accepted these records but do not cover this scoring case. No fix is built here because this job authorizes a footprint analysis, and asks for proposals rather than a new book build.

INFERRED: **K128 would provide useful capacity, but it would not repair the reproduced fault.** The estimates below hold the recorded asset workload constant and assume K128 successfully activates on a machine configured for the expanded memory. They are not a claim that this full game was rerun successfully. Inputs: [observations.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/observations.json), [watch-scan.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/watch-scan.json), [K1 product notes](</home/noah/Desktop/2K5-8 Editors/K1_EXTRA_HEAP_2026-09-23.md>), and [saved K128-early layout](/media/noah/Storage/.b76-research/k1/runs/k1u2e-fp-rams/r4-summary.json).

| Configuration | Estimated main-heap capacity | Estimated free at this workload | Evidence label |
| --- | ---: | ---: | --- |
| Recorded 64 MB run | 32,740,352 | 131,072 | PROVED OFFLINE measurement |
| `k128_memory` alone, late form | 32,740,352 | roughly 131,072 | INFERRED; unchanged main arena and no roster move/cap |
| `k128_memory` + `k128_roster_heap` | 32,740,352 | 622,336 | INFERRED; roster moved, in-game cap enabled |
| All three, adding `k128_early` | 48,645,120 | 16,527,104 | INFERRED; saved early-layout capacity applied to this workload |

PROVED OFFLINE: The snapshot's ROST payload is **593,920 bytes**, charged as **594,048**. The K1 cap is a **1,572,864-byte request**, charged as **1,572,992**, which is **102,784 bytes more** than this run's **1,470,208-byte** reservation. Arithmetic for the late estimate is `131,072 + 594,048 - 102,784 = 622,336`. Sources: [observations.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/observations.json), [all-blocks.csv](/media/noah/Storage/.b76-research/pb/astra-build/heap/all-blocks.csv), [K1 cap and roster relocation](</home/noah/Desktop/2K5-8 Editors/K1_EXTRA_HEAP_2026-09-23.md>).

PROVED OFFLINE: K1's saved early run has graphics arena **64,618,496 bytes**, bottom carve-out **704,768**, top carve-out **15,268,516**, and main heap **48,645,120**. Its main-heap gain over this snapshot is **15,904,768 bytes**. Arithmetic gives `622,336 + 15,904,768 = 16,527,104`, approximately **15.76 MiB**. Source: [K1 early saved summary](/media/noah/Storage/.b76-research/k1/runs/k1u2e-fp-rams/r4-summary.json), [watch-scan.json](/media/noah/Storage/.b76-research/pb/astra-build/heap/watch-scan.json). INFERRED: This uses the measured composed early layout, rather than adding the notes' rounded retail-to-early gain to a different executable layout.

INFERRED: The late combination covers the measured resident workload with about **0.59 MiB** left; the early combination leaves about **15.76 MiB**. Those are aggregate estimates, not promises of one allocation of that size. Startup placement, fragmentation, executable-page layout and later requests can alter usable contiguous space. The cap matters: without it, the native in-game reservation absorbs newly available main-heap room again. Neither estimate changes the invalid scoring address, which lies outside these heaps.

PROVED OFFLINE: **There is no measured book heap cost to recover by shortening names or sharing nodes.** The existing complete-offense compiler already interns identical whole chains and identical names in `repack`. Source: [complete-offense pool rebuilding](/home/noah/2k-worktrees/b76-x2/mod_editor/core/nfl2k5_complete_offense.py:70), plus the native zero-allocation receipts above.

DESIGN: A final compaction pass after defense and kickoff composition could remove dead chains and merge further exact duplicate names/chains without dropping plays. Shorter display names or carefully validated suffix sharing could create more authoring capacity. The game format still reserves the same fixed slot, so these proposals have **zero expected main-heap saving**. No compacted books or compiler changes were built. Any claim of further byte savings requires a separate measurement, and changing the fixed slot layout would require loader/serializer changes rather than a pack-only edit.

DESIGN: Prioritize the reproduced scoring-domain defect. Treat K128 with the roster move and cap as additional memory capacity for the wider production composition, separately from correcting this particular crash.

PROVED OFFLINE: Reproduction programs are [attribute.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/attribute.py), [cache_probe.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/cache_probe.py), [refs.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/refs.py), [inventory.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/inventory.py), [book_probe.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/book_probe.py), [live_books.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/live_books.py), [fault_probe.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/fault_probe.py) and [fault_controls.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/fault_controls.py); their shared snapshot reader is [explore.py](/media/noah/Storage/.b76-research/pb/astra-build/heap/explore.py). The entire block inventory is [all-blocks.csv](/media/noah/Storage/.b76-research/pb/astra-build/heap/all-blocks.csv). Binary resource extracts remain in Storage scratch. The evidence covers offline loading, snapshot ownership and the isolated scoring fault; it does not constitute a full-game certification.

1. PROVED OFFLINE: The report and reproducible receipts identify the saved failure.
2. PROVED OFFLINE: Main heap: 32,740,352 bytes; 32,609,280 used; 131,072 free.
3. PROVED OFFLINE: All 662 used blocks reconcile exactly in `all-blocks.csv`.
4. PROVED OFFLINE: Named resource collections account for 20,341,120 bytes.
5. PROVED OFFLINE: The largest block is 4,486,528 bytes of player rendering instances.
6. PROVED OFFLINE: Each team kit collection costs 2,730,368 bytes.
7. PROVED OFFLINE: NYG and DAL PLAY bodies each reserve 78,736 executable-data bytes.
8. PROVED OFFLINE: Both resident PLAY books together charge zero main-heap bytes.
9. PROVED OFFLINE: All 128 retail/current-authored native loads allocate zero heap bytes.
10. PROVED OFFLINE: Four native loads of recovered snapshot books give the same result.
11. PROVED OFFLINE: Dallas `17 Inside Zone` reproduces the saved scoring-table fault.
12. PROVED OFFLINE: The saved resource-read destination is nonzero.
13. INFERRED: K128 late with roster move/cap leaves about 622,336 bytes free.
14. INFERRED: Adding K128 early leaves about 16,527,104 bytes; the scoring defect remains.
15. DESIGN: Fix the scoring contract next; pool compaction offers authoring room, not heap savings.
ASTRA_DONE

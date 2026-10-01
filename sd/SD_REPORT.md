# PROVED OFFLINE: Candidate D stall, completed read and cyclic lineup iterator

**DESIGN:** SD investigation, 2026-09-28, based on `job/b76-sd` at `9de33371`. Labels cover the paragraph, table or code block they introduce. `PROVED OFFLINE` means inspected bytes, source, supplied capture, or native offline replay. `INFERRED` identifies causal interpretation beyond those observations. `DESIGN` identifies proposals and validation requirements. Offline replay is not an in-game witness.

**PROVED OFFLINE:** The retained read succeeded. The CPU is selecting a lineup, repeatedly visiting the same five linebackers. The captured selection loop rejects all five and never reaches exhaustion. Native position kinds 14 and 15 resolve to the same linebacker lists; the next-candidate iterator treats them as separate pools and restarts an exhausted list. The failure is in `0xE8410`, called repeatedly at `0x1894B3`, not in the DVD path. [Request](evidence/request.json), [native replay](evidence/native-replay.json).

**INFERRED:** This cycle explains the frozen game and unconsumed resource completion. Compaction cannot eliminate this code/data defect. It can change timing and whether a run reaches the triggering lineup and fatigue state. A clean compacted run would not establish a repair.

## The purported in-flight read

**PROVED OFFLINE:** These fields come from `watch-end.bin`, decoded through guest page tables with CR3 `0xF000`, and independently checked against D's directory using the repository XDVDFS parser. Disc base is zero. [Directory](evidence/directory.json), [kernel objects](evidence/kernel-objects.txt), [request verification](evidence/request.json).

| Field | Value |
| --- | --- |
| UTF-16 filename at `0xA7D30C` | `VC_53450030\4` |
| Native handle | `0x54` |
| Archive start | sector `947,481`, byte `1,940,441,088` |
| Archive length | `313,178,112` bytes |
| File offset, qword at `0xA7D358` | `0x0000000002171000`, decimal `35,065,856` |
| Length at `0xA7D360` | `0x20`, 32 bytes |
| Destination at `0xA7D364` | `0x00B09550`, non-null |
| Absolute disc offset | `1,940,441,088 + 35,065,856 = 1,975,506,944` |
| Absolute disc sector | `964,603`, sector aligned |
| Worker state at `0xA7D300` | `1`, idle/suspend branch |
| Worker result at `0xA7D368` | `0`, success |
| Higher-level resource busy at `0xB09584` | `1` |
| Next file offset in game handle cache | `0x02171020`, offset plus 32 |

**PROVED OFFLINE:** The game cache entry at `0xA7CA00` supplies handle `0x54`. Kernel `ObReferenceObjectByHandle` at `0x80020524` uses helper `0x80021579`; the table reached through `0x8003ABCC` has entry `+0x54 = 0xD006DC98`. That FILE_OBJECT points to FCB `0xD006DC48`, whose sector and size match archive `4`. FILE_OBJECT final status is zero, current offset is `0x02171020`, and its event is signalled. The values at `0xA7D34C` and `0xA7D350` are not handle and length: they lie beyond the terminated filename within its storage. Their earlier provenance is not needed to decode this request. [Handle decode](evidence/kernel-handle.txt), [worker disassembly](evidence/initial-disassembly.txt).

**PROVED OFFLINE:** All 32 destination bytes equal D's bytes at the absolute offset above: `41424e4bc01a0000000000000000000000000000000000000000000000000000`. They begin `ABNK`, followed by dword `0x1AC0`. This operation neither targets a large disc offset nor lacks its returned data.

**PROVED OFFLINE:** The worker reads through `0x4D630 -> 0x4AF70 -> 0x1D8D2`, the NtReadFile wrapper. Success at `0x4D708` stores result zero. Completion around `0x4D889` restores state 1 and calls `0x3A4F0`. State 1 reaches `0x4D837`, then `0x4B910` and the SuspendThread wrapper. `0x3A4F0` writes request result `+0x20` and completion-node state `+8 = 3`. The captured node `0xA7DBA0`, reached through `[0xA7D370+0x5C]`, has state 3, callback `0x4C020`, request `0xA767F8`, and success result zero. I/O has completed; higher-level completion work remains queued. [Worker follow-up](evidence/loader-followup.txt), [completion](evidence/completion-disassembly.txt), [completion setter](evidence/eligibility.txt).

**INFERRED:** Resource busy remains set because gameplay cannot return from lineup construction to service the completion. That flag alone was insufficient evidence of outstanding kernel I/O. This differs from the Berman null-destination kernel bugcheck in the memory note.

## What `0x222230` does and where progress stops

**PROVED OFFLINE:** `0x222230` waits on nothing. Its entire function is a formation-slot mask getter:

```asm
00222230  imul ecx, ecx, 0xB
00222233  add  ecx, edx
00222235  mov  eax, [ecx*4+0xAC26B8]
0022223C  and  eax, 0x7FFFF
00222241  ret
```

**PROVED OFFLINE:** The first two supplied gdb samples already show different candidates: stack words at `0xD0046A40` and `0xD0046A74` change from `0xB31624` to `0xB31480`. Later samples in the same file stop in helpers `0xE7570` and `0xE7554`. A repeated EIP did not establish a blocked instruction. Source: `/media/noah/Storage/.b76-research/main/stall-candD/gdb-capture.txt`, hashed in [verification](evidence/verification.json).

**PROVED OFFLINE:** The selection is slot 6 of descriptor `0xB7F40C`, formation row 13, roster `0xB336F4`, tier 1. Slot byte `0x2E` encodes kind 14 and rank 1. Its mask at `0xAC290C`, after the getter's mask, is `0xC000`, allowing kinds 14 and 15. The kind-14 fallback row at `0x4F5E60` begins `14,15,17,16,13,...`. Kind 14's pair at `0x4F59A0` and kind 15's at `0x4F59A8` are both `(17,18)`. Lists 15 and 16 are empty; list 18 holds player IDs `[28,25,24,30,31]`. Every player there has roster enum 11, mapping to kind 14. [Players/slot](evidence/players-and-slot.txt), [selection](evidence/selection-loop.txt).

**PROVED OFFLINE:** The alias is explicitly installed by `olb_kind_lists` in [the position-pools module](../mod_editor/core/nfl2k5_position_pools.py): retail kind 15's `(15,16)` becomes `(17,18)`. The module also maps the retired OLB enum to kind 14. The next-candidate fallback traversal does not deduplicate these now-identical pools.

**PROVED OFFLINE:** In `0xE8410`, `0xE8473..0xE8484` derives the current player's kind; `0xE84E0..0xE84F1` finds that kind in the fallback sequence. After the last kind-14 candidate, `0xE86FE..0xE870E` advances to kind 15; `0xE8620` resolves it to the same list. The already-passed-current flag then permits returning an earlier player from the alias list. Next invocation identifies that player as kind 14 again, restarting traversal. The caller takes the non-null result at `0x1894B8..0x1894C5` back to `0x1893E0`. There is no visited-player guard or exhaustion bound. [Full iterator](evidence/iterator-disassembly.txt), [caller](evidence/selection-loop.txt).

**PROVED OFFLINE:** Unicorn execution of captured instructions and memory, with no mocked game callees, reproduces this cycle three consecutive times:

```text
0xB31624 Jack Kelly
  -> 0xB31678 Zaire Barnes
  -> 0xB3157C Tremaine Edmunds
  -> 0xB31480 Micah McFadden
  -> 0xB3142C Arvell Reese
  -> 0xB31624 Jack Kelly
```

**PROVED OFFLINE:** Replaying the actual caller from `0x1893E0`, with its captured stack at `0xD0046A88`, repeats those candidates without reaching either return. The captured counter is `0x89792BF7`, but it is not a retry limit. `[ESP+0x24]` is zero, so counter wrap cannot enable conditional player reuse. Rejections are below. [Native replay](evidence/native-replay.json), [fatigue](evidence/fatigue.json), [stack](evidence/iterator-disassembly.txt).

| Candidate | Rejection |
| --- | --- |
| Jack Kelly | Inactive, energy `0.6971361`; fatigue eligibility returns zero |
| Zaire Barnes | Inactive, energy `0.5275465`; fatigue eligibility returns zero |
| Tremaine Edmunds | Already assigned to lineup slot 4 |
| Micah McFadden | Inactive, energy `0.7693037`; fatigue eligibility returns zero |
| Arvell Reese | Already assigned to lineup slot 5 |

**PROVED OFFLINE:** Native `0x188440` rejects the three inactive players through `0x18856D`. Their status bits are zero; inactive threshold is `16 / 20 = 0.8`, above their energy. Edmunds and Reese pass eligibility but fail the caller's earlier duplicate check. The never-exhausted iterator prevents the outer routine's normal tier relaxation. [Eligibility code](evidence/eligibility.txt), [threshold constants](evidence/source-verification.json).

## Kernel and xemu disc limits

**PROVED OFFLINE:** D has `8,012,931,072` bytes and `3,912,564` sectors. Kernel CD-ROM capacity at `0x800361A8` is the qword `0x00000001DD9BA000`, exactly D's full length. Mounted XDVDFS extension `0xD00082E0` has the same 64-bit length and sector count `0x3BB374`. There is no truncated 32-bit byte capacity. [Request receipt](evidence/request.json), [initialization](evidence/capacity-initialization.txt).

**PROVED OFFLINE:** The XDVDFS descriptor supplies root-directory sector and byte length, not a fixed game-partition byte ceiling. D's descriptor is at sector 32; root fields are sector 33 and length 108. Mounted capacity comes from the drive. CD-ROM capacity code at `0x80025618` decodes READ CAPACITY's last LBA, adds one, multiplies by `0x800`, and stores both result halves. XDVDFS initialization at `0x8002AC08` uses `shld` and `shl` for its 64-bit length. [Parser](../tools/nfl_audo_wav_xiso_verify.py), [directory](evidence/directory.json), [capacity code](evidence/cdrom-capacity.txt).

**PROVED OFFLINE:** Relevant kernel behavior, including [directory extent validation](evidence/kernel-read-disassembly.txt):

| Location | Operation |
| --- | --- |
| `0x8002B717`, directory validation | Requires start sector and rounded extent within volume sectors; invalid extent returns `0xC0000032` |
| `0x8002B430`, XDVDFS read | Ordinary files have 32-bit relative offsets/sizes; nonzero high relative offset reaches EOF handling |
| `0x8002B51E`, `0x8002B55D` | Sector multiplication yields `EDX:EAX`; `add` plus `adc` includes relative offset without losing the high word |
| `0x80025D9A`, CD-ROM dispatch | Checks alignment and 64-bit read end against full capacity |
| `0x80025DCF..0x80025DE6` | Past-capacity read completes with `0xC000000D` |
| `0x8002DE40` | Shifts 64-bit byte address by 11 into sector units |
| `0x80025CA0`, packet path | Caps transfer at `0x20000` bytes; emits READ(10), opcode `0x28`, with full 32-bit big-endian LBA |

**PROVED OFFLINE:** Native offline dispatch replay, stubbing only external queue/completion effects, produced these results. This validates dispatch math, not host disk transfer. [Boundary receipt](evidence/cdrom-boundary-replay.json), [sector math](evidence/kernel-sector-math.txt), [CD-ROM path](evidence/cdrom-path.txt).

| Byte offset | Length | Result |
| --- | --- | --- |
| `8,012,929,024` | `2,048` | Queues last sector `3,912,563`, status `0x103` |
| `8,012,931,072` | `2,048` | Completes `0xC000000D`, no queue |
| `4,294,967,296` | `2,048` | Queues sector `2,097,152`, status `0x103` |
| `2,147,481,600` | `4,096` | Queues sector `1,048,575`, crossing 2 GiB |

**PROVED OFFLINE:** The requested xemu checkout is sparse. HEAD `f9b14039e5bb56ae2d8f028e31e7cc19f13f7e12` records `hw/ide/atapi.c` as blob `a42b7485218614b4f236925e776739cb7ca3d510`. The existing file `/home/noah/xemu-2k5-edition/src/xemu-0.8.136-2k5ed/hw/ide/atapi.c` has that exact Git hash. Inspection used identical source without populating the requested checkout. This verifies source identity, not main's installed flatpak executable revision. [Source verification](evidence/source-verification.json).

**PROVED OFFLINE:** In that source, `cmd_read` at line 980 compares LBA and end LBA against `s->nb_sectors >> 2`, the image's 2048-byte sector count. Out-of-range requests call `ide_atapi_cmd_error(... ILLEGAL_REQUEST, ASC_LOGICAL_BLOCK_OOR)`. That function assigns `READY_STAT | ERR_STAT`, stops transfer and raises the IDE IRQ, rather than leaving BUSY set. Synchronous reads at line 102 cast LBA to `int64_t` before shifting by 11; asynchronous/DMA paths also widen before converting units. READ CAPACITY at line 1150 and DVD structure reporting at line 480 use the image's sector count. These paths contain no 2 GiB, 4 GiB or approximately 7 GB byte ceiling.

**PROVED OFFLINE:** The mounted extent limit here is EOF at `8,012,931,072` bytes: a read must end at or before it. The retained read is far below that limit. XDVDFS's 32-bit sector field and READ(10)'s 32-bit LBA do not impose a 4 GB image limit. Separately, the inspected xemu PIO/DMA entry points accept signed `int lba` and assert `0 <= lba`; starting LBA `2^31` exceeds that signed range, corresponding to 4 TiB. Per-file XDVDFS lengths are independently 32-bit.

**DESIGN:** Do not impose a guessed 7 GB or 4 GB image cap as this stall's fix. Validate every directory/file extent with checked wide arithmetic against final sectors, reject unrepresentable fields, and prevent overflow of the kernel's `file_length + 0x7FF` rounding; a conservative per-file cap is `0xFFFFF800`. A conservative image cap for this inspected xemu code is `(2^31 - 1) * 2048 = 4,398,046,509,056` bytes, also avoiding signed rollover on the final sector increment. This is a source-derived guard, not a certified practical maximum. Physical-media targets need their own established capacity bound; real-drive capacity was not certified here.

## Compaction, candidate C, and repair scope

**PROVED OFFLINE:** High extents exist: `3` starts at `6,319,216,640`, `B` at `6,953,203,712`, `F` at `7,710,914,560`, and `0` at `7,818,858,496`. All fit D's length; `F` is not last. Compaction reduces `8,012,931,072` to `5,924,454,400` bytes. Main's `compact-proof.json` records identical files. Independently, D and compacted D have identical full XBE SHA-256: `f69ee7a3c4fb5e7a6eea50fe6ae0ece740a7f4e72efa85df507145dd85f96b44`. [Directory](evidence/directory.json), [candidate comparison](evidence/candidate-comparison.json).

**PROVED OFFLINE:** C's full XBE differs, but the compared iterator, selection caller, kind-14/15 list pairs, fallback table, and `0x222230` getter are byte-identical across C, D and compacted D. C therefore contains the same affected code and mappings. The supplied task says C completed without nudges; that is supplied provenance, not a new witness by SD.

**INFERRED:** D exposed a latent one-pool iterator defect. Which content change or timing difference produced this particular fatigue/lineup state is unestablished. Compaction cannot fully prevent it while preserving those bytes and mappings. No completed compact-versus-original result had been supplied at report close; the readable compact watcher only recorded cointoss. Diagnosis does not depend on that pending A/B.

**PROVED OFFLINE:** Three isolated in-memory interventions terminate the captured iterator and caller: restore kind 15's retail `(15,16)` pair; clear bit 15 only in this slot mask; or apply the iterator proposal below. Each changes Kelly/Barnes/Edmunds/... to Kelly/Barnes/null and reaches caller return `0x1894D6`. These are causal experiments, not shipped fixes. [Replay](evidence/native-replay.json).

**DESIGN:** Preserve the unified LB pool and repair iteration semantics: visit each physical pool once, preserve primary-slot ranking, and return exhaustion so existing tier relaxation runs. Globally restoring the retail mapping would undermine the feature; changing one mask covers one instance. Audit other aliases, kind-15 primary slots, empty/all-rejected pools, and mixed/legacy OLB rosters before selecting a general patch.

**PROVED OFFLINE:** A captured-case proposal occupies 46 existing bytes at `0xE8539` and `0xE8600`. It extends both non-primary fallback checks, which skip kinds 3 and 4, to skip alias kind 15 too. [Expected/replacement bytes](evidence/repair-proposal.json). With only these changes in Unicorn memory, the native outer lineup routine reaches `0x18A7A7` after 18,617 instructions, fills slot 6 with McFadden through the relaxed path, and produces 11 distinct non-null players. Captured unmodified code remains in the cycle.

**DESIGN:** Treat those bytes as a concrete repair experiment, not a general production patch. Proof covers the captured kind-14 slot and enclosing routine, not every alias ordering, package, roster or kind-15 primary slot. No production module, builder, disc or XBE was modified. SD delivers diagnosis, repair design and evidence. Integration requires the cases above and main's in-game validation. Compaction remains useful independently for storage and layout.

## Verification and handoff

**PROVED OFFLINE:** The consolidated assertion run verified handle/FCB/directory agreement, completed request, destination bytes, full capacity, repeated cycles, all three interventions and the proposed repair's complete lineup. It recomputed D's full SHA-256 as `449a3b90f0b4f7733bfd5589c132510265f4ee2f092e738777b811e4134de680`; device, inode, size, modification time and change time stayed unchanged during the run. [Assertion log](evidence/verification.log), [input/harness hashes](evidence/verification.json).

**DESIGN:** Reproduce with `PYTHONDONTWRITEBYTECODE=1 python3 /media/noah/Storage/.b76-research/sd/astra-build/verify_sd.py`. Hashed helpers and proposal bytes are in that allowed research directory. They read supplied RAM/disc and write `sd/evidence`, using Capstone and Unicorn. Large inputs and experimental Python stay out of the report commit. The separate CD-ROM experiment's limited stubs are identified above.

**PROVED OFFLINE:** The attempted Jev evidence-label audit returned an approval-policy error before execution. No Jev judgment was obtained. Report claims were checked directly against the saved receipts; the blocked tool result is preserved in [jev-audit.json](evidence/jev-audit.json).

**PROVED OFFLINE:** SD launched no xemu, used no process pool, and wrote no disc or other worktree. Shared Git metadata lies outside the writable roots, so delivery uses private Git and a verified bundle in `/media/noah/Storage/.b76-research/sd/astra-build`. Only `sd` is included; pre-existing `ASTRA_BRIEF_SD.md` is excluded. No push or tag is part of delivery.

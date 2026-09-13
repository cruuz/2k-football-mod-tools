# APF roster STFS rehash boundary, beta 69 J8

**Xenia only; a real console will reject this package.** The writer preserves
the original signature bytes. It neither verifies nor replaces the RSA
signature. Hash repair does not provide a valid signature for modified content.

PROVED offline: fixed-size replacement of the existing Roster.ROS allocation,
active SHA-1 tree repair, metadata hash repair, unchanged signature/license
bytes, and independent extraction of the replacement. HYPOTHESIS: discovery
and loading of that output by a user's Xenia build. Every emulator/game outcome
is UNWITNESSED. No emulator, network, console, or private save was used here.

## Format and bounds

The existing `tests/test_apf_save_custom_team_appearance.py::synthetic_stfs`
fixture is the known package used for the round trip. It is generated entirely
from synthetic bytes with an intentionally invalid signature. Its former
contiguous file had end-of-chain in every hash entry; the fixture now also
populates next pointers because the audited Xenia reader follows those pointers.

| Region | Meaning and write policy |
|---|---|
| `0x000..0x003` | CON, LIVE, or PIRS magic, preserved |
| `0x004..0x22B` | signature/certificate storage, preserved and never certified |
| `0x22C..0x32B` | sixteen licenses, preserved |
| `0x32C..0x33F` | SHA-1 over metadata from `0x344` to the rounded header end |
| `0x340..0x343` | big-endian header size, preserved; round up to 4096 for first table |
| `0x344`, `0x360` | require saved-game content type 1 and APF title ID `54540807`, preserved |
| `0x379..0x39C` | STFS descriptor; only top hash `0x381..0x394` changes |
| `0x37B` | bit 0: single table copy; bit 1: active root copy |
| `0x37C..0x380` | little-endian file-table count and 24-bit start block |
| `0x395..0x39C` | big-endian allocated/free block counts, preserved |
| `0x39D`, `0x3A9` | data-file count and filesystem type; require single-file STFS |
| hash block | 170 entries, each 20-byte SHA-1 plus four bytes of state/next pointer; total block 4096 bytes |
| leaf entry | SHA-1 of the complete 4096-byte data block, including unchanged file-tail padding |
| parent entry | SHA-1 of the complete active child table; bit `0x40` in state selects secondary copy |

For logical block `b`, copies `c` (1 or 2), physical data block is
`b + (floor(b/170)+1)*c`, plus `(floor(b/28900)+1)*c` when `b >= 170`.
The extractor previously shifted the accumulated physical address on two-copy
packages and used a physical value in the higher-level calculation. Both are
fixed. The writer handles at most two hash levels and 128 MiB packages, refuses
multi-file containers, overlapping file/directory allocations, bad hashes,
invalid chains, sparse/out-of-order directories, changed lengths, and ambiguous Xenia level boundaries at
exactly 170 or 28900 allocated blocks. The raw output route remains available.

Only changed roster blocks have their leaf digest rewritten, then their active
parent table digests, then the descriptor top hash, then the metadata hash.
Inactive table copies, pointers, file sizes, other files, and every other header
byte stay identical. Verification reparses hashes and allocations and compares
the entire package to the allowed replacement to catch mutations even in the
unhashed signature area.

## Local Xenia source audit

Read-only tree: `/home/noah/.codex-tmp/xenia-slot43-build`, git revision
`d09cae8d8374324048ef603d48a9c1696b39d552`. Exact file bytes, rather than a claim
about every Xenia version, pin this finding:

| File under `src/xenia/vfs/devices/` | SHA-256 |
|---|---|
| `xcontent_container_device.cc` | `21ca059098c8c93fa7e0a26016ca24196d3ba3e45f29f97675887524ddde6c14` |
| `xcontent_devices/stfs_container_device.cc` | `0dad581748c15cc0db9d9b5c399077a1f49c6bb461729c01523579a0b6ff5202` |
| `stfs_xbox.h` | `47ed398b7267615542ea0f9036a6cf79fd6ed66db367caf39f4f64b6e0aeda4c` |

PROVED from these pinned source bytes: `ReadContainerHeader` at line 131 reads
the header, and `ReadHeaderAndVerify` at line 182 checks length, successful read,
and `is_magic_valid()`. It performs no cryptographic signature or metadata hash
verification. The misleading comment “check signature” means no RSA check in
the executable statements. `StfsContainerDevice::Read/ReadEntry` (lines 55/111)
use hash entries for chain traversal, without comparing stored SHA-1 values.
`BlockToOffset` at line 179 supplies the independently modeled geometry.
`GetBlockHash` at line 283 selects active copies. `stfs_xbox.h` defines the
0x344-byte header, 0x93D6-byte metadata, 0x24-byte volume descriptor, and
0x18-byte hash entry. Rehashing still keeps format integrity even though this
reader does not enforce the digests.

`tests/mod_editor/test_apf_stfs_roster_rehash.py` checks the file pins when the
local tree exists, round-trips the known synthetic roster package across both
table-copy layouts and fragmented chains, and compares payloads using a
separate Python translation of Xenia traversal. That translation is an offline
model, not native Xenia execution or a game-load witness. Shipping captions
therefore retain HYPOTHESIS/UNWITNESSED for full loading.

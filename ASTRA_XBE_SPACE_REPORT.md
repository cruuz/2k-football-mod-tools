# r61 XBE space report, 2026-09-05

Implemented on `astra/r61-xbe-space`. EXPERIMENTAL/UNWITNESSED, default off.
No network, console emulator, GUI, audio or push was used. Retail inputs were
read only. The full manifest build used a disposable image in this worktree's
`.scratch/`; that image was removed by the builder's temporary-directory cleanup.

## What was built

- `nfl2k5_xbe_space.py`: deterministic `layout`, `status` (retail/applied/foreign),
  `apply(payload, requests) -> (bytes, receipt)`, `reservations`, owner-scoped
  `install_code`, and `allocation_evidence`. Requests are owner/kind/size/align
  tuples, sorted canonically. Alignment is a power of two, sizes/capacities are
  bounded, duplicates and changed allocation sets refuse. Replays retain VAs.
- Two new section descriptors, preserving every existing section's VA/raw
  geometry. Code is preloaded and read only; data is preloaded, writable and
  initially all zero. No runtime variable is placed in `.text`.
- `nfl2k5_dynamic_kickoff_relocated.py`: the complete 1,939-byte dynamic kickoff,
  its ten state bytes and all eleven hooks relocated. This is the actual
  kickoff implementation, not a canary. It inherits the installed kickoff's
  settings, or accepts validated settings on retail input.
- Generalized transactional disc growth, recognition, rollback and same-size
  replay in `nfl2k5_depth_chart_storage.py`.
- Manifest recording of parent pages and named children, including zero data
  and the transferred boot logo; CLI `space-proof`.
- Protected-file integration is specified in `WIRING.md`. The protected
  dispatcher, BuildPlan, GUI, release allowlist, runtime checker and reservation
  JSON remain unchanged here.
- Two complete capability handoff objects are in
  `docs/mod_editor/nfl2k5_xbe_space_capabilities.json`; both validate against
  the registry's existing capability subschema. No runtime registry was edited.

The existing SPECIAL code retains eleven-record unit stride and uses a new
live table pointer. The inherited depth-lock gate incorrectly used stride 13
to recognize its bench/swap changes, so both required gates failed before the
allocator ran. The small depth-lock correction selects that exact code variant
from SPECIAL's live table pointer while reporting the actual physical stride.
Its existing 16-test suite now runs standalone and passes. The kickoff and
oracle test files also now set their repository import path for plain Python.

## PROVED: structural section strategy and header accounting

The authoritative local format reader is
[`tools/xbe_info.py`](tools/xbe_info.py), `IMAGE_HEADER_FIELDS` and
`Xbe.parse_sections`. It reads the image fields at:

| Offset | Field | Result |
| --- | --- | --- |
| `0x104` | ImageBase | retained `0x10000` |
| `0x108` | SizeOfHeaders | `0xCC4` retail or `0xF82` old logo relocation becomes `0x1000` |
| `0x10C` | SizeOfImage | becomes `0x014AC000` |
| `0x11C` | section count | 22 becomes 24 |
| `0x120` | section table VA | retained `0x10370` |
| `0x170`, `0x174` | logo VA and byte count | named code-page allocation, unchanged 690-byte bitmap |

Each descriptor is `<9I20s>`, 56 bytes: flags +0, VA +4, virtual size +8,
raw offset +12, raw size +16, name VA +20, reference count +24, head/tail
shared-page counter addresses +28/+32, and section digest +36. Shared-page
counters are 16-bit words, as shown by the retail two-byte pointer spacing.

Simply appending descriptors would overwrite names/counters. Simply changing
`.XTLID` flags would change SPECIAL's permissions. The selected strategy is:

| Header file range, half open | Ownership/action |
| --- | --- |
| `0x370..0x840` | 22 original descriptors stay at the same addresses |
| `0x840..0x8B0` | two new descriptors, including their digests |
| `0x8B0..0x904` | unoverwritten original metadata suffix stays byte identical |
| `0xCC4..0xD88` | exact 196-byte copy of old `0x840..0x904` names/counters |
| `0xD88..0xD98` | `.ASTRAc\0` and `.ASTRAd\0` names |
| `0xD98..0xDA0` | two zero 16-bit counters, with zero padding words |
| `0xDA0..0x1000` | bounded canonical allocation directory and code seal |

The 66 original name/head/tail pointer fields are adjusted by `0x484`; their
alias relationships, every name, initial reference count, flags, VA/raw bounds
and all 22 section digests are retained (except SPECIAL's independently owned
size/digest changes when it is applied). Both head/tail pointers for each new
single-page section name that page's same counter. There are no shared pages
between either new section and any existing section.

This uses only the first header page, ending exactly at `.text`'s `0x11000`
start; no retail section moves. Retail metadata SHA-256 is
`155d094c9592c93f1fd7ce1eb635667d8b88e92cfd46d6e77659e7ae7dd4a252`.
Normalized 22-descriptor geometry SHA-256 is
`904d5748e0650b7627e1d9d77d926088f4cd43749b481455b1803fdc53acd243`.
The implementation pins both rather than accepting merely zero-looking space.

The first composed gate revealed that the old boot-logo patch already owns
`0x10CD0..0x10F82`. Before repurposing that storage, the allocator copies the
**same** 690-byte bitmap into the mandatory named `nfl2k5_boot_logo` allocation
in the new read-only code page, updates the logo pointer and retains the old
bitmap's 1,700-pixel decode. It accepts only the known retail or old relocated
bitmap/header state. Both orders with boot-logo repair produce identical bytes.
The logo's new loader availability remains a separate runtime uncertainty below.

A supplementary Capstone linear scan found no decoded absolute memory operand
into the moved metadata. Its one immediate hit was `sub edi,0x10840` at
`0x160BD3`; this is not proof of absence of computed pointers. The relocation
proof rests on the format's explicit descriptor pointers, retained section
addresses, exact original metadata copy and preserved aliasing. It does not
claim a complete kernel or dynamically computed-reference proof.

## PROVED: page selection, allocations and SPECIAL composition

A byte-granular scan of the pinned USA retail headers and every raw section
checked every little-endian absolute word and all relative call/jump/conditional
transfer encodings, including rel8. Operand-size-overridden near rel16 transfers
truncate EIP below these addresses. No page pair between the SPECIAL tail and
16 MiB met this conservative encoding condition. The first passing pair in the
search is the fixed pair below:

| Region | VA range | Raw range | Flags |
| --- | --- | --- | --- |
| code | `0x014BA000..0x014BB000` | `0xB77000..0xB78000` | `0x36`: preload, executable, head/tail read only |
| data | `0x014BB000..0x014BC000` | `0xB78000..0xB79000` | `0x03`: writable, preload |

Neither section sets inserted-file `0x8`. The data section omits executable
`0x4`; this describes its XBE flag, not a claim of hardware NX enforcement.
The independent local mapping model is
[`XbeImage.runtime_writable`](mod_editor/core/nfl2k5_cave_oracle.py), and the
bounded CPU test maps the header and each preloaded section from these fields.

With `relocated.REQUESTS`, the named allocations are:

| Owner | Kind | VA | Bytes | Alignment |
| --- | --- | --- | --- | --- |
| `nfl2k5_boot_logo` | code/immutable bitmap | `0x014BA000` | 690 | 16 |
| `nfl2k5_dynamic_kickoff_relocated` | code | `0x014BA2C0` | 1939 | 16 |
| `nfl2k5_dynamic_kickoff_relocated` | data | `0x014BB000` | 10 | 4 |

All unused bytes remain owned by `nfl2k5_xbe_space`; code padding is INT3 and
data is zero. No oracle `unknown` becomes `free`. The directory records named
requests and a SHA-256 code seal. Headers, metadata, sizes, padding, owner
boundaries, all-zero data and all section digests are validated before mutation.
Filled code can only replay identically; changing settings/owners needs a rebuild.

The final XBE is **12,029,952 bytes**, `0xB79000`: 81,920 bytes beyond retail and
8,192 beyond SPECIAL alone. Physical raw growth leaves a virtual gap before the
new pages. The allocator does not silently use that gap as another allocation.
Each kind has one 4096-byte page; code capacity includes the boot bitmap.
The 608-byte metadata directory independently bounds the number/name length of
requests. Exhaustion refuses rather than selecting an unproved next page.

SPECIAL's entire `0xB63000..0xB77000` raw region is byte identical to the
SPECIAL-only output, including original `.XTLID` data, extension padding and
46 records. Its `0x3A` flags, live table at `0xEE3000`, virtual/raw sizes and
section digest remain unchanged by allocation. Name/counter pointer fields in
its descriptor move with the other descriptors. Applying SPECIAL before or
after allocation/relocation yields exactly the same whole XBE.

The fresh-allocation proof passed against both the supplied retail reservation
manifest and the new generated manifest. It allows established parent/child
ownership and rejects every other overlapping owner. As with the existing
SPECIAL proof, register-synthesized addresses and external effects are outside
this static encoding proof.

## PROVED: kickoff equivalence and bounded execution

The existing kickoff assembler now accepts a code base and two state spans;
its defaults produce the unchanged beta-60 instruction stream. The relocated
version invokes that same generator. Assembler fixups handle internal branches,
relative calls to retail routines and each displaced-instruction continuation.
The eleven hooks enter the new code. The old cave remains byte identical to
its input, whether it contained the prior kickoff or retail bytes.

Capstone decodes every byte of both 1,939-byte allocations. After normalizing
only the code/state addresses, every instruction ID, length, operand type,
operand width, register, memory addressing mode and target is identical. Every
changed byte belongs to an encoded displacement or immediate.

The bounded header-mapped Unicorn reset witness runs the real retargeted hook,
new code, data-page write and original displaced load, then an explicit RET
stub at the exact retail continuation. In 30 instructions or fewer it writes
only `(0x014BB000, 1 byte, 0)`, leaves the old storage page unchanged, restores
EIP to the supplied return address, advances ESP by four, preserves EBX/EFLAGS
and loads the expected EAX value. Code is mapped read/execute and data read/write.

A second bounded fixture executes the retail target/clamp readers for all
11 kicking slots in both directions through the relocated hooks. Coverage stays
at its intended target before launch; coverage/blockers hold after launch and
release on landing-zone ground contact. The entire old shared state page stays
unchanged. Unrelated scene/heading callbacks remain explicit fixture stubs.

## Test commands and final results

All tests are unittest scripts, independent of pytest. Missing private retail,
Capstone or Unicorn inputs have precise skip reasons. Final runs:

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_xbe_space.py` | 12 passed |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 9 passed |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 10 passed |
| `python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | 23 passed |
| `python3 tests/nfl2k5_depth_chart_rows_test.py` | 23 passed |
| `python3 tests/mod_editor/test_nfl2k5_depth_locks.py` | 16 passed |
| `python3 tests/mod_editor/test_nfl2k5_boot_logo.py` | 7 passed |
| `NFL2K5_CAVE_MANIFEST=.scratch/xbe_space_manifest.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed |

The optional manifest environment variable selects newly generated private
evidence for this test, retaining the production source-drift guard. The
protected shipped JSON is deliberately not regenerated here and remains stale
relative to this branch. A default retail oracle check against it must refuse
until Claude performs the documented regeneration.

The space suite includes a synthetic XDVDFS round trip, a real-retail-XBE
round trip in a small disposable image, SPECIAL-to-grown and same-size
composition writes, neighbouring-file preservation, and injected short writes
at the payload and directory stages. Rollback restores exact image bytes and
length. All file descriptors close before replace.

The following full retail-XISO build also passed:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir .scratch --json .scratch/xbe_space_manifest.json
python3 tools/nfl2k5_cave_oracle.py space-proof \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --manifest .scratch/xbe_space_manifest.json --json .scratch/space_proof.json
```

It recorded **3,267 reservations from 35 observed XBE writer calls**, verified
all section digests and read back the grown XBE from the appended disc extent.
The final composed XBE SHA-256 was
`d083d0855a19c448bba22e13b729fd7d3d6bb81de67cd69fb6d459902ccde7ee`.
Loading that generated manifest with the real source-root fingerprint guard
also passed. The proof reports zero retail encodings and zero foreign overlaps.
Generated evidence and proprietary output bytes are excluded from the commit.

## HYPOTHESIS and known gaps

**Actual kernel/xemu loading is not PROVED.** The available local format reader,
existing mapper and bounded CPU model support the section strategy, but no
kernel/xemu section-loader source was available in the permitted inputs. The
brief forbids network and emulator runs. Consequently this report cannot claim
a source-backed proof of the real kernel's complete mapping/load order, nor a
boot witness. In particular, availability of the boot bitmap in a newly
preloaded section when the kernel draws it is an explicit unresolved dependency.
A kernel that needs it before preloading could reject or misrender the boot.

The new SizeOfImage also spans a virtual gap; real loader allocation/commit
behavior and memory pressure are unmeasured. Header RSA signatures are not
recreated; the existing length-prefixed section digest helper is used. This
inherits the patched-XBE boot environment's existing signature requirements.

Noah has not confirmed SPECIAL's loader-growth boot in this session. Neither
SPECIAL nor the two-section growth is called witnessed. Static code equivalence
and the bounded fixtures do not prove all gameplay paths, save behavior or
boot animation. The protected dispatcher/UI integration is a concrete handoff,
not an installed user-facing flag in this branch.

## Noah's witness list

1. Confirm the SPECIAL-only comparison disc boots and its SPECIAL tab displays
   and scrolls correctly. Record that result independently.
2. Build a disposable experimental comparison disc with `xbe_space` on and
   `kickoff_relocated` off. Verify boot/logo, title screen and a normal game.
3. Build with both flags, the existing dynamic kickoff settings and the existing
   kickoff book alignment. Verify boot again. On normal kickoffs in both field
   directions, check that coverage lines up at the receiving 40, setup blockers
   remain in their intended zone, and both deep returners stay correctly placed.
4. Confirm coverage/setup players finish lining up, hold during approach and
   flight, then release on ground or player contact. Play the return through
   the next down. Repeat human/CPU kicking and receiving.
5. Check direct end-zone touchback, landing-zone then end-zone, short/out-of-bounds,
   onside and safety kicks against the existing kickoff build. Confirm custom
   touchback/probability settings still match.
6. Open SPECIAL and the practice/reserve/depth screens on that same composed
   disc, play another kickoff, save and reload. Record any boot, logo, memory,
   screen or kickoff regression with the exact receipt/XBE hash.

No result on that list is claimed here. If boot/preload fails, preserve the
comparison and investigate the actual loader before enabling the preset for
regular use.

## Commit delivery

The required explicit-path `git add` was attempted in the worktree and refused:
its linked Git metadata is on a read-only filesystem (`index.lock` could not be
created). Following the brief's explicit fallback, the same branch commit is
prepared using isolated Git metadata under `.scratch/xbe-space.git`, with the
original HEAD as its parent, and exported as `.scratch/xbe-space.bundle`.
The shared branch ref remains untouched. All edited files remain in place.
Neither `ASTRA_BRIEF.md` nor `.scratch/` is included in the commit; no push occurs.

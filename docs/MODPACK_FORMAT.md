# `.2k5patch` formats and operation registry

## Format 3: finished SOFTDRINK game files (Beta 76)

Format 3 is a separate file-content contract. Formats 1 and 2 remain unchanged.
Format 2 cannot express this install through its existing envelope: its checked
image-size chain, directory-field addresses and before sectors require the
author's partition layout. A compact result applied to arbitrarily repacked
inputs would violate those invariants. Format 3 resolves every input by XDVDFS
path and content hash and writes a new compact image. Old readers safely reject
`format: 3`; they must never interpret these rows as image-offset operations.

The ZIP64 container retains `kind: "2k5patch"`, `game: "nfl2k5-xbox"`, an empty
`payload.bin`, and `manifest.json` (at most 16 MiB). The required
`file_contract` is `"source-copy-v1"` and `min_reader_version` is **4**.
Earlier, unpublished Format 3 packs are refused with a re-export diagnostic.
Earlier Format 3 readers refuse the new reader requirement before installation.
Formats 1 and 2 retain their existing compatibility behavior.
ZIP central-directory metadata is bounded to 16 MiB and 24,098 entries before
it is materialized by the ZIP reader.
The `files` table records every finished file, including unchanged and empty
files. Each row carries a case-folded path, `before` and `after` objects with
exact byte size and SHA-256, the compact output `offset`, and one of:

* `copy`: before and after identities are identical; read the user's file.
* `runs`: edits and optional growth/shrinkage, with a streamed `operations/NNNN.bin` member.
  Each record is little-endian `<QI32s32s>`: file-relative offset, literal
  length, SHA-256 of the intersecting retail span, SHA-256 of the new span, then literal
  bytes. Records are ascending, nonoverlapping and at most 1 MiB each. Bytes
  between records come from the user's verified file. Appended spans use the
  empty SHA-256 when wholly beyond retail EOF; every growth byte must be
  covered by a literal or source-copy record. Shrinkage retains only the declared
  output prefix. The literal member may be empty.
  An optional `copies` member descriptor references `operations/NNNN-copies-GGGG.bin`.
  Its records are little-endian `<QQI32s32s>`: output file offset, **source file
  offset**, length, SHA-256 of the intersecting original destination span, and
  SHA-256 of the referenced source span (also the resulting output span).
  Copy records contain no literal bytes. Source offsets can be any byte offset
  within the **original retail file**, including beyond a shortened output's
  end. An optional `cross_copies` list contains additional copy-member descriptors
  with the same `member`, `length`, `sha256` and `compressed_bytes` fields, plus
  `source_path`: a case-folded disc path in the manifest's verified file inventory.
  Each such member uses the identical record encoding, with its source offsets
  relative to that named file. Source paths may not repeat within one row;
  the row's own path uses `copies`. Missing or unverified source paths refuse.
  Copies always read the immutable input, so swaps and moves do not depend
  on output order. Lengths are positive and at most 1 MiB, and the whole source
  span must exist. Each member is sorted by output offset; merging all streams
  must give nonoverlapping output spans. Gaps read the same-offset source bytes.

`replace` is no longer an accepted Format 3 mode. The exporter never chooses a
complete replacement, even if it would compress better. Cross-file references
are necessary for E: a supplemental audit found another 532,692,992 literal
bytes matching other retail files after same-file exclusion alone. In particular,
retail `/f` supplies large spans to finished `/e` and `/d`.

Every member, including `copies`, has its own uncompressed `length` and `sha256`.
Export builds a shared index of every complete 4 KiB window in **every retail
file**, at 512-byte source alignment, including windows crossing 1 MiB read boundaries.
This alignment follows the measured shifted content in SOFTDRINK E. Every
changed output 4 KiB grain is looked up in that index. A BLAKE2b-96 lookup key
narrows candidates; byte equality, never that key alone, authorizes a copy.
All offsets sharing a key remain candidates. Adjacent literals and contiguous
source copies coalesce separately within 1 MiB windows. Identical same-offset
grains remain implicit source copies. No stored literal 4 KiB grain can equal
an indexed window in any source file; final partial grains and shorter common sequences
are outside this exclusion guarantee. This is a measured byte-content rule,
not a claim about ownership or uniqueness of every smaller byte sequence.
Growth and shrinkage retain full before/after file identities.
`full_copy_bytes`, `full_deflated_bytes` and payload `compressed_bytes` report
the per-file baselines. `literal_bytes`, `source_copy_bytes` and
`source_copy_records` describe the encoding; these informational counts do not
replace reconstruction validation. Inspect/export receipts give their totals, actual ZIP
size and separately measured embedded-source contribution.

`metadata` holds base64-encoded bounded XDVDFS descriptor/directory records
from the finished disc, with relocated output pointers. Metadata plus aligned
file extents must tile a compact output without overlaps or gaps, starting at
sector 32. The prefix, sector padding and final 32-sector alignment are zero.
Source file offsets, padding, timestamps, directory layout and video prefix
are not input identities. All required source files must match; harmless extra
files are ignored. Missing, duplicate, cyclic, overlapping, out-of-bounds or
content-modified inputs refuse. The inherited partition locator supports known
raw offsets and scans the first 1 GiB for other sector-aligned partitions.

Export currently requires the finished disc to retain the base's file set.
It pins the retail USA executable when authoring a release. Other USA file
revision adapters, added/deleted finished files, and PS2 installs are outside
this version. `result.sha256` is the author's whole-image digest for comparison,
not an input gate. Repacking normalizes unused bytes, so a noncompact author's
image can have a different container hash while every game file is identical.

Check verifies source-file identities and replays changed files, checking both
members, span hashes, bounds, ordering and the resulting file SHA-256.
Apply opens the source read-only, verifies all required files, then writes a
unique temporary sibling in 1 MiB blocks. It verifies reconstructed file hashes,
reparses the written XDVDFS tree, reads every output file back for SHA-256, and
hashes the whole output. Only then, after closing all image and ZIP handles,
does it atomically rename. Source timestamps/size/descriptor identity must stay
stable during installation. Source/output and pack/output aliases are refused,
including hard links. In-place application is forbidden. Failed or cancelled
transactions remove their temporary files and preserve existing destinations.
Space is checked for one full output image, even where zero blocks stay sparse.
An existing destination needs that much additional free space until commit.
There are no extracted game files or compiler caches on this path.

`assets/` carries streamed editable sources and their SHA-256s, up to 20,000
members and 8 GiB total. The source manifest contains the effective frozen
preset/overrides, a portable league-project JSON and its referenced PNGs, the
roster, playbooks, intro, venue-art directories and official marks directory
when supplied by the recipe. Exact original recipe/project documents are also
retained. `@pack/assets/...` references are resolved into the user's extraction
folder. No pack-supplied code is executed. Unavailable authoring sources refuse
export rather than silently producing a recipe with missing assets.

For a separate source download, `--sources-out FILE.2k5sources` writes a ZIP with
`sources.json` (`softdrink_source_bundle/v1`) and the same hashed asset records.
The main patch pins this whole optional file by size and SHA-256 and still
includes the frozen recipe. A wrong companion file refuses extraction.
`Customize SOFTDRINK 2K28…` extracts and resolves sources, loads the Build
controls, and supplies the league project to the full Studio builder. Users
can adjust Build options, omit league artwork, or use **Choose SOFTDRINK league
artwork…** to select families or individual edits and save a separate project.
Customization is a full authoring build, with its existing resource/time costs;
the fast finished-byte installation always installs the complete frozen release.
The full build is not run by pack export, check, extraction or install.

Release authoring, from the checkout root:

```sh
python tools/nfl2k5_modpack.py export-files --base RETAIL.xiso.iso --patched FINISHED.xiso.iso --out SOFTDRINK-2K28.2k5patch --recipe FROZEN_RECIPE.json --json
python tools/nfl2k5_modpack.py check SOFTDRINK-2K28.2k5patch --image MY_DISC.iso
python tools/nfl2k5_modpack.py apply SOFTDRINK-2K28.2k5patch --source MY_DISC.iso --out SOFTDRINK-2K28.xiso.iso --json
python tools/nfl2k5_modpack.py extract SOFTDRINK-2K28.2k5patch --out editable-sources --customize
```

For recipes frozen before the 42-image marks boundary, supply `--marks-pack DIR`
with the complete current marks pack. A recipe pointing to the older five-image
folder, including G's initial frozen recipe, needs this override too. All 42
reviewed sources are validated before export. These private packs contain finished
game-derived bytes and marks; keep all packs, source bundles and disc images
outside Git. See `docs/official_marks_pack.md`.

The following sections document legacy formats 1 and 2.

Format 2 carries ordered, typed operations. Same-size exports continue to write
format 1 by default; pass `format_version=2` to opt in. Loading, checking,
applying, extracting assets, and recognising recipes support both versions.

## Container and compatibility

Both formats are deflated ZIP archives (ordinary ZIP magic, `PK`); the manifest
identifies `kind: "2k5patch"` and `game: "nfl2k5-xbox"`. Format 2 supports ZIP64.
It adds these manifest fields:

```json
{
  "format": 2,
  "min_reader_version": 2,
  "op_registry_version": 1,
  "base": {"size": 6300499968, "partition_base": 0, "sha256": "…"},
  "result": {"size": 6312521728, "sha256": "…"},
  "ops": ["ordered operation objects described below"]
}
```

`op_registry_version` versions the registry/envelope contract, not its population.
Adding an operation does not change the container format or registry contract.
Each installed handler declares its own `min_reader_version`; the exporter takes
the maximum across the operations used. The reader computes its supported version
from its installed, trusted registry. A manifest cannot understate its handlers'
requirements. An unknown format, reader requirement, operation ID, operation
version, or registry contract refuses with **“this mod needs a newer Mod Studio.”**

Already distributed format-1 readers cannot be retroactively changed: their
existing `unsupported patch format 2` refusal remains safe, but does not have the
new wording. This reader accepts their old packs unchanged. Format 1 retains its
original run and payload limits and partition-relative application behaviour.

Format 2's legacy `payload.bin` member is empty, with length 0 and the SHA-256 of
empty bytes. Actual data lives in `operations/<safe-name>.bin`, independently
sized and hashed. Files are streamed in blocks; there is no 256 MiB operation or
aggregate payload ceiling. XDVDFS itself has uint32 sector and file-length fields.
The 16 MiB manifest bound and existing asset resource limits remain parser/resource
safeguards, not limitations on the size of an appended image. Payload members may
be referenced more than once, with the same declared identity. Duplicate ZIP
member names are refused. A pack never supplies executable handler code.

`assets/`, their SHA-256 checks, recipe metadata, and embedded `.2k5mod` sources
retain their existing behaviour. `.2k5mod` is a replacement-source project archive,
not another extension for a finished disc patch; its own schema is unchanged.
There was no HMAC/signature on the modpack archive to migrate. Existing XBE section
digests are transported unchanged. SPECIAL validates its versioned loader storage
layout; current gameplay recognizers remain the responsibility of gameplay writers.

## Operation envelope

Every operation contains:

| Field | Meaning |
| --- | --- |
| `type`, `name`, `version` | Integer registry ID, matching name, handler payload version |
| `before_size`, `after_size` | Image bytes from the game partition to EOF, immediately before/after this operation |
| `payload.member` | Safe `operations/*.bin` ZIP member |
| `payload.length`, `payload.sha256` | Exact uncompressed payload identity |

Image sizes form a checked chain. Byte offsets and sectors are relative to the
game partition. A raw dump with a sector-aligned video prefix works when its game
partition-to-EOF shape matches the author's shape. Format 2 refuses an unrelated
extra/missing tail; appending at a different EOF would produce a different layout.
Format 1 keeps its existing, more permissive run-only container-size behaviour.

| ID | Name | Version | Implemented behaviour |
| --- | --- | --- | --- |
| 0 | `byte_runs` | 1 | Sorted, nonoverlapping runs within this operation; original `replace` run fields and before/after SHA-256s; concatenated new bytes |
| 1 | `xbe_grow` | 1 | Recognised retail-storage → SPECIAL-storage transition; append full XBE and repoint `default.xbe` via checked file-growth spans |
| 2 | `file_replace` | 1 | Resolve a named file through XDVDFS and replace its existing, same-size extent |
| 3 | `file_grow` | 1, 2 | Append a larger named file and repoint its directory sector/length; version 2 also carries retained intermediate allocations before that file |
| 4 | `file_add` | reserved | Contract/design below; currently refuses as an unknown operation |
| 5 | `file_shrink` | 1 | Replace a named file with a shorter nonempty payload at its existing sector, update its directory length, retain the physical image size and unused allocation bytes |

Separate operations may overlap, including replacing the same bytes or growing
an already grown file. Before hashes refer to the intermediate result of the
preceding operations. An individual `byte_runs` operation cannot overlap itself.

Named-file operations additionally contain `path`, `directory_offset` (the
sector/length field, relative to the partition), and `before` / `after` objects
with `sector`, `size`, and `sha256`. The name must resolve to the declared field
and extent; offsets alone are insufficient. `file_grow` appends the *complete*
replacement, leaves the old allocation untouched, and zero-fills only the alignment
gap. It cannot overwrite the next disc file. A shorter explicitly named file
exports as `file_shrink` (ID 5). Shrink cannot relocate a file, truncate the ISO,
or modify the bytes after its new declared end. Before/after hashes and nested
directory resolution are verified as for replacement/growth. Version-2 readers
without handler 5 refuse it as an unknown operation. ID 4 stays reserved.

### Chained growth and retained allocations

Each newly exported growth records explicit partition-relative sector accounting:

```json
"append": {"sector": 3076416, "file_sector_offset": 5870}
```

`append.sector` must equal `ceil(before_size / 2048)`, where `before_size`
is the image end **after every preceding operation**. `after.sector` must equal
`append.sector + append.file_sector_offset`. `after_size` is exactly
`after.sector * 2048 + after.size`; the next operation starts with that size.
Named paths are deduplicated case-insensitively and emitted in physical append
order, independently of the caller's list order.

Version 1 has zero `file_sector_offset`, retaining its original full-file payload
and zero alignment gap. Old version-1 packs may omit `append`; their accounting
is derived by the same original rule. `xbe_grow` remains version 1 and still
uses its strict SPECIAL validator and storage writer. `file_shrink` is unchanged.

Version 2 of **operation 3** handles a build that superseded an earlier appended
allocation. For example, Experimental appends SPECIAL, then the logo pack, then
the larger owned-page XBE. Its final directory points only to the last two files,
but the earlier SPECIAL bytes must survive a byte-identical reproduction.
The next named growth owns those retained bytes explicitly: its payload spans
`append.sector * 2048` through `after_size`. The prefix has
`file_sector_offset * 2048` bytes and the final `after.size` bytes are the named
file. The payload SHA-256 covers the entire append, including the prefix;
`after.sha256` independently covers the named file, and `before.sha256` still
covers its input extent after preceding operations. Prefixes are streamed, never
materialized as an image-sized padding buffer. Only the sub-sector alignment gap
before `append.sector` is implicitly zero-filled. Unaccounted trailing bytes and
nonzero implicit alignment bytes still refuse export.

The container stays format 2, registry version 1, **min_reader_version 2**.
Beta-60/61 readers already reject unknown operation versions before copying or
writing with **“this mod needs a newer Mod Studio: file_grow version 2”**.
They cannot silently misapply this addition, so a reader-version bump is
unnecessary. Ordinary contiguous chains continue exporting operation version 1
and remain usable by those readers. Frozen synthetic packs produced by both
shipped exporters cover format 1 Basic and format 2 SPECIAL Advanced in
`tests/fixtures/modpack_legacy/`; their ZIP identities and applied bytes are pinned.

`xbe_grow` uses that same envelope plus strict SPECIAL storage validation: old
XBE length `0xB65000`, new length `0xB77000`, recognised original final-section
storage, and `storage.state(new_xbe) == "applied"`. This checks the section's
location, size, loader permissions, retained retail content and unused padding.
The operation describes loader allocation, not a particular gameplay revision.
Requiring the current `rows.status` broke packs from the original Beta 60 and
Beta 61 writers when later gameplay row and pool layouts changed.

Execution uses the common checked file-growth spans and the same final byte,
hash and directory-extent verification. The gameplay builder's
`write_image_xbe` keeps its current-layout recognizer. Its
`image_file_node(read, partition, image_size, path)` resolver remains shared by
the builder and projected checker, including nested file paths. Frozen original
writer outputs and invalid-storage refusal tests cover this compatibility boundary.

## Export, check, and transactional apply

Automatic export detects only SPECIAL growth. Other named file changes require
`file_operations=["path/in/disc"]`. All other image-length changes are refused.
The exporter removes the named operations' owned fields/extents from the ordinary
run diff, creates `byte_runs` first, and follows with named allocations in their
physical append order. Earlier in-place edits to the old XBE allocation travel in
`byte_runs`; the `xbe_grow.before` hash describes that intermediate XBE.

Export simulates the entire operation list and compares its result against the
entire author image in blocks. Consequently, an unexplained tail, alignment byte,
relocation, file addition/removal, or operation effect is refused. This verification
also applies to the explicit operation-authoring API below.

`check()` verifies payloads, then executes handlers against a read-only projected
view (original descriptor plus lazy replacement spans). No image copy or mutation
is needed. Every operation verifies its input after its predecessors' projected
writes. If the forward plan fails, checking compares the composed final writes
and named-file resolution to recognise an already-applied pack, including when
later operations overwrite earlier ones. A mixed/intermediate format-2 state is
`mismatch`, with the first failing operation and reason. Legacy format-1 partial
state behaviour stays unchanged. The `counts` and `runs` report members retain
raw per-run diagnostics; `state` / `explanation` cover the complete operation list.

Copy application prechecks before creating `.part`, copies the source, rechecks
operations on that copy, executes them in order, and reads back each operation's
writes and expected-after hashes. SPECIAL additionally verifies its full payload
and directory extent through the original storage helper. The composed result
size/writes are checked before rename. With hashing enabled (the default), an
exact author base must produce the author's full result SHA-256; otherwise the
copy is discarded. Partition-prefixed variants retain their own untouched prefix.

For format 2, `apply_in_place()` uses the same copy/verify/atomic-rename transaction.
It requires room for another image and replaces the path's inode; other hard links
keep their original bytes. Write failure leaves the existing image unchanged.
Format 1 retains its original direct in-place writer. Both paths use binary file
descriptors on Windows. Inputs must remain stable during a build/export/apply;
size and descriptor timestamps are rechecked across transactional copies.
Before an in-place commit, the current source path is reopened and its size and
SHA-256 must match the bytes copied into the transaction. This avoids comparing
path-stat metadata with descriptor metadata, which can differ on Windows.
Path metadata is compared with path metadata before and after this read to
detect a replacement during verification.
This final check adds one streamed source read. All image descriptors and cached
pack payload streams are closed before `os.replace`, including the existing-pack
alias probe during export. `check()` and format-2 apply release cached payload
streams on failure too; a supplied `Pack` remains reusable and reopens them lazily.
An operation or write failure deletes the incomplete `.part`; a source change
detected at the final check or a failed atomic replacement preserves the fully
verified `.part` and leaves the destination untouched by the transaction.

## Authoring and extending

```python
# Existing named file already replaced or appended by a trusted studio writer:
modpack.export(base, built, output, {"name": "New crowd audio"},
               file_operations=["audio/crowd.bin"])

# Explicit operation composition (payload values may be bytes or local Paths):
modpack.export(base, built, output, {"name": "My feature"},
               patch_operations=[op_a, op_b],
               operation_payloads={"operations/a.bin": source_a,
                                   "operations/b.bin": source_b})
```

Implement a trusted handler in `modpack_ops.py` (or a shipped module imported
there) and call `register(unused_id, Handler)`. Never reuse an ID. Declare `name`,
`version`, and `min_reader_version`. Implement:

1. `validate(op, before_partition_size, payload)` — reject malformed fields,
   impossible extents, and conflicting expected identities.
2. `plan(op, view, pack, verify)` — when `verify=True`, verify input through
   `view.read` / `view.digest`; append lazy `Span`s via `view.put`, and update
   `view.size` if necessary. Always validate output payload semantics. When false,
   describe deterministic final writes without requiring the original bytes.
3. Optional `execute(op, pack, descriptor, spans)` — call an existing specialised
   writer; otherwise the dispatcher streams the planned spans.
4. `verify_written(op, actual_view)` — verify per-operation expected-after hashes
   and structure immediately after writing.
5. Optional `verify_final(op, projected_view, actual_view)` — compare final
   structural resolution after the whole list, allowing later operations to
   supersede this operation's intermediate state.

Handlers must plan deterministic bounded reads/writes; a handler requiring a
truncate must express `view.size` and perform the corresponding truncate in its
executor. The dispatcher is unchanged when handlers are added. Recipe operation
names remain a separate, descriptive namespace and can already carry arbitrary
parameters and asset references.

### `file_add` design (reserved ID 4)

Adding a file is materially different from replacing a directory node. A safe
implementation must carry the absent target path, parent path, parent-directory
before length/hash, a complete rebuilt parent-directory payload and after hash,
the new file payload/after hash, and the parent owner field's before/after identity.
Append the new file and rebuilt parent directory in sector order; update only the
parent's owner entry (or root sector/length in the volume descriptor). Preserve
all existing nodes/attributes/extents, build valid bounded AVL links, and reject
casefold collisions, cycles, overlapping metadata, and invalid names. Verify the
entire parent listing and every affected owner edge in the projected view and by
read-back. Because parent directories can themselves be relocated, the handler
must resolve their owner by path and compose with prior operations.

That directory allocator is not a cheap or already-proven helper in this tree.
It is deliberately a reserved, fail-closed operation, with no unsafe placeholder
implementation. Implementing it requires a new handler, not format 3. The same
extension path accommodates file deletion, image shrink/repack, or future studio
operations without imposing a new container revision.

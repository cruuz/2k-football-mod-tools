# `.2k5patch` formats and operation registry

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
digests and the SPECIAL storage/rows validators are retained.

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
| 1 | `xbe_grow` | 1 | Recognised retail-storage → SPECIAL-storage transition; append full XBE and repoint `default.xbe` via the existing storage writer |
| 2 | `file_replace` | 1 | Resolve a named file through XDVDFS and replace its existing, same-size extent |
| 3 | `file_grow` | 1 | Resolve a named file, append its larger replacement at the next sector after EOF, then repoint that file's directory sector/length |
| 4 | `file_add` | reserved | Contract/design below; currently refuses as an unknown operation |

Separate operations may overlap, including replacing the same bytes or growing
an already grown file. Before hashes refer to the intermediate result of the
preceding operations. An individual `byte_runs` operation cannot overlap itself.

Named-file operations additionally contain `path`, `directory_offset` (the
sector/length field, relative to the partition), and `before` / `after` objects
with `sector`, `size`, and `sha256`. The name must resolve to the declared field
and extent; offsets alone are insufficient. `file_grow` appends the *complete*
replacement, leaves the old allocation untouched, and zero-fills only the alignment
gap. It cannot overwrite the next disc file. Shrinking/repacking is not inferred
by the current exporter; it can be represented by a future registered handler.

`xbe_grow` uses that same envelope plus strict SPECIAL validation: old XBE length
`0xB65000`, new length `0xB77000`, recognised original final-section storage,
and `rows.status(new_xbe) == "applied"`. Execution calls
`nfl2k5_depth_chart_storage.write_image_xbe` directly. Its extracted
`image_file_node(read, partition, image_size, path)` resolver is shared by the
writer and the projected checker, including nested file paths.

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
source identity, size, and timestamps are rechecked across transactional copies.

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

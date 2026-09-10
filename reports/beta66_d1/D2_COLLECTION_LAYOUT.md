# D1 collection contract for D2 integration

This is a coordination handoff. No message was sent outside this worktree, and
no emulator was started. Entering/playing the formerly overfilled Incite #2
collection remains UNWITNESSED. This change does not assume that freeze is fixed.

`nfl2k5_music_metadata.identities(n)` retains the first 59 `(collection, song)`
pairs exactly. Additional rows use `(18 + (index-59)//256, (index-59)%256)`.
The public Add songs lane allows 134 additions (193 jukebox rows plus seven
unchanged menu songs); the existing lower-level library codec supports 400
jukebox rows, so it can use two new collections. No retail group loses a row.

`MSONGS2\0` contains a little-endian JSON byte length and an ASCII JSON document
with `songs` and `collection_name`. UTF-16 song strings follow, then 16-byte
aligned contiguous per-collection song arrays. Song records remain four u32s:
logical bank index, title pointer, artist pointer, duration pointer. Added
collection names follow those arrays, then the aligned native collection table
as the final `32 * collection_count` bytes. Its address is
`storage.VA + storage.PREFIX + len(data) - 32 * collection_count`.
The name defaults to `My songs`; the second is `<name> (2)`.

The table copies all first 24 bytes of each of the 18 original collection rows,
including their original title/artwork identifier and bank pointers, enabled flag and
purchase ID. Each row's final two u32s are its song count and contiguous array
pointer. Added rows have their own title pointer and reuse the existing collection_17
artwork identifier at `0xE92D1C` (row +4 is an asset name, not description text),
cribmusic/crib22 pointers `0xE92A34` / `0xE92A48`, enabled=1, purchase ID=0.
Both the strings and new table are in the existing sealed allocator-owned
read-only music section. No runtime data is placed in `.text` and no cave is added.
The original table's count/pointer fields are still updated for compatibility
with the existing policy verifier.

`nfl2k5_music_collections.SITES` pins 51 complete instructions in
`0x27F410..0x280189`: the 22 native table displacements and 29 immediate/LEA
on-disc collection boundaries. Boundaries become 19 or 20, and subtraction of
that boundary still maps subsequent indices to the original Xbox soundtrack
APIs. No stack offset that happens to equal 18 is changed. Table references were
located by a bytewise scan of the retail executable mappings and decoded at
instruction boundaries. The writer changes only these checked instruction
fields. D2 should compose any freeze fix touching these functions against these
sites, preserving before/after recognition, rather than overwrite them blindly.

`collection_table()` reparses the final native table. Metadata status verifies
the sealed payload, all original collection count/pointer fields, and every
accessor instruction. Existing MSONGS1 libraries remain readable and idempotent;
rebuild from the original disc to migrate their old grouping. Existing Xbox
soundtrack profile indices are shifted by the added collection count; previously
saved custom Xbox soundtrack selections need a game witness/reselection on a
new library disc. Retail on-disc song identities do not shift.

`nfl2k5_music_policy.apply` calls the metadata owner's `refresh_policy`
to re-seal the copied retail purchase headers when the existing unlock option
changes them. (The implementation lives in metadata; policy calls it.) Both
policy/library orders produce identical bytes in the regression test. The
playlist owner's full-function guards normalize only the verified metadata
accessors before checking their original pins. Its separate runtime hooks stay
under the playlist owner's checks.

PROVED offline: synthetic identity grouping; actual native count/name/count-
per-collection accessors; 200-item native list construction, reconstruction,
lookup, scrolling, metadata reads and profile serialization; source ownership,
section digests, foreign-data refusal, idempotence, and policy composition.
UNWITNESSED: jukebox collection entry, artwork display, actual audio playback,
Xbox soundtrack coexistence, and D2's reported freeze.

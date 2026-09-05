# Runtime save ROST codec

`mod_editor.core.nfl2k5_save_rost` implements bounded read/modify/write for
runtime version 0 and disc version 17 framing. It preserves all unknown bytes,
including the container's prefix/suffix and unused arena bytes. It never
changes a signature or writes a file itself.

```python
from mod_editor.core import nfl2k5_save_rost as rost

document, container = rost.load_save("input.zip")  # existing HMAC check required
original = document.to_bytes()                  # identical to SAVEGAME.DAT
document.edit_player("primary", 0, {"speed": 88})
container.write("new-edited-copy.zip", document.to_bytes())
```

`load_save` returns `(SaveRost, SaveContainer)`, not the legacy GUI's
`RosterDocument`. The existing container layer verifies the original EXTRA,
then re-signs a new copy when explicitly asked to write. No signing key,
authentication policy, or existing loader is modified by this module.

For bytes already in memory, use `decode(payload)` / `encode(document)`.
`decode(..., preamble=offset)` selects a known inner preamble explicitly;
otherwise exactly one structurally valid supported resource must be found
within the first 64 KiB. Inputs are capped at 32 MiB. A wrapped resource's
declared size bounds every parsed reference. Unknown or ambiguous framing is
an error, not a request to reinterpret the version number.

## Offset domains

| Location | Real version-0 fixtures, file-relative | Disc resource, resource-relative |
|---|---:|---:|
| Outer ROST wrapper | `0x2E0` | `0x00` |
| Inner preamble | `0x300` | `0x20` |
| Inner ROST magic | `0x30C` | `0x2C` |
| Version | `0x310`: 0 | `0x30`: 17 |
| Root | `0x320` | `0x60` |
| Resource end, exclusive | `0x91320` | `0x90F80` |

The root-pointer field is inner-preamble `+0x14`. Relocated references use
`target = field_address + signed_i32 - 1`; zero is null. Version 0 has a
`0x20`-byte inner header and `0x91000`-byte runtime arena in the preserved
fixtures. Disc version 17 has a `0x40`-byte inner header. It is unsafe to feed a
version-0 payload to a version-17 decoder by changing its version byte.

The codec exposes player records, team membership, typed root-table ranges,
and lossless history words. `edit_player` validates the whole batch of existing
integer fields before applying it. Pointer mutations are refused; name-pool
growth, depth reordering, team creation, and a full franchise schema are not
implemented here. Existing pointer/record bytes remain unchanged on a no-op.

Tests include independent generated frames and both local signed runtime
saves. The real tests pin input hashes, round-trip exactly, change only the
chosen rating byte, re-sign/reload a disposable copy through the existing
container API, and verify source files/EXTRA remain untouched. See
`tests/fixtures/nfl2k5_save_rost/README.md` for fixture configuration. Missing
private evidence gets an explicit skip; a bad hash or signature is a failure.

These tests prove parsing and serialization on those fixtures, not gameplay
acceptance or all franchise variants. A separately identified franchise save
is still needed before claiming franchise coverage.

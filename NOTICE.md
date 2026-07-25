# NOTICE

## Scope of the licence

**IMPORTANT: The [MIT licence](LICENSE) covers the modding tools and their
original source code only. It grants no rights to any game, game data,
trademarks, or other intellectual property owned by SEGA, Visual Concepts, 2K,
Take-Two Interactive, the NFL, NFL Players Inc., or any other rights holder. You
must supply your own legally obtained copy of any game you mod.**

That paragraph previously lived at the bottom of the `LICENSE` file. It has been
moved here unchanged so that `LICENSE` contains the MIT text and nothing else,
which is what licence scanners — including GitHub's — need in order to identify
the project as MIT. Moving it changes no terms: the MIT grant and the paragraph
above both apply exactly as they did before.

## What these tools ship, and what they do not

These editors contain **no game data**. No ISO, no extracted game files, no
textures, audio, screenshots or rollback bytes are included in this repository
or in any published release archive. Both release archives are built from an
explicit allowlist and pass an automated **retail-free gate** that fails closed
if a game byte, decoded pixel, decoded audio sample, private path or undeclared
file appears in them.

The tools read a copy of a disc image or extracted folder that **you** supply,
and they only ever write to a **copy**. Your original disc image is never
modified.

## Third-party components

| Component | Where | Licence |
| --- | --- | --- |
| [XboxDev/extract-xiso](https://github.com/XboxDev/extract-xiso) 2.7.1 (`b72e5b6`) | `tools/vendor/extract-xiso/` — bundled as Linux ELF and Windows PE builds in the APF release archive | see `tools/vendor/extract-xiso/LICENSE.TXT` |

Build commands, toolchain and exact hashes for both bundled binaries are
recorded in `tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md`, so the
bytes can be reproduced rather than trusted.

## Trademarks

*ESPN NFL 2K5*, *All-Pro Football 2K8*, and all related names, logos and marks
are the property of their respective owners. This project is not affiliated with,
endorsed by, or sponsored by any of them. Game names are used only to identify
which game a tool operates on.

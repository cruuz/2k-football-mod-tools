"""Which NFL Blitz 2002 disc this is: the shared PS2 identifier, given this game's identity.

Nothing here is game-specific but the identity it is handed, which is why it is
four lines: :class:`mod_editor.games._formats.ps2_disc.Ps2DiscIdentifier` reads
the ISO9660 volume, ``SYSTEM.CNF`` and the boot ELF, and says whether the serial
and the executable digest are the ones this game recognises.
"""

from __future__ import annotations

from mod_editor.games._formats.ps2_disc import Ps2DiscIdentifier

__all__ = ["Ps2DiscIdentifier"]

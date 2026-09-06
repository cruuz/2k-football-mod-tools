"""Shared lane bases that two games on the same stack instantiate.

``_formats`` holds the **formats**: a reader that knows a container and nothing
about a game.  This package holds the layer above -- the **lane shapes** two
games on the same stack would otherwise write twice: how a record edit becomes
a plan, a build and an independent verdict; how a texture member is exported
and put back; how a string slot is measured and rewritten in place.

Nothing here is a game either.  Discovery skips underscore-prefixed
directories, and a base takes everything game-specific as data:

* a **disc-access module** (:class:`Discs` below) -- the game's own
  ``containers`` module, which knows which ``/DATA`` files matter, how large a
  container this module will hold, and what a synthetic source looks like;
* the lane's **identity** -- capability id, lane id, surface, page, title, and
  the three schema strings its documents carry;
* a **field map** or a **container list** -- what this game's schema actually
  offers, which is the half that never ports.

A base never imports a game and a game never imports another game.  See
``contract.SHARED_FORMATS_PACKAGE`` and ``AGENTS.md``.

Why the split is worth having: Madden NFL 09 and NCAA Football 09 are two
Tiburon discs of the same generation.  Every container format is the same --
``TERF`` containers, ``LZH1`` and ``RLE1`` codecs, EA ``TDB`` databases with
four CRC-32/MPEG-2 slots, ``MMAP`` textures, ``QL01`` preload caches -- and
**no schema table is**.  So the code that walks a container, plans a bounded
write, rebuilds the caches it disturbed and re-derives the result from the
destination's own bytes is one implementation; the code that says *which*
fields an editor offers is per game, per table, and stays in the game.

**Retail-free**, like everything else here: names, offsets, lengths, counts and
digests.  A base builds the bytes its own tests look at.

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Protocol, Sequence, Tuple


class Discs(Protocol):
    """What a lane base needs of a game's own ``containers`` module.

    Every game module already has these; the protocol writes down which ones a
    shared base is entitled to use, so a change to one game's ``containers``
    that breaks a base fails at the base's own tests rather than at a lane's.
    """

    #: ``"/DATA"`` on every disc measured so far, and read from the module
    #: rather than spelled in the base.
    DATA_DIRECTORY: str
    #: The game's own refusal type, so a base's sentence reads as the game's.
    DiscError: type

    def open_disc(self, path: Path) -> Any: ...

    def data_files(self, image: Any) -> Sequence[Any]: ...

    def read_file(self, image: Any, entry: Any, *, limit: Optional[int] = ...) -> bytes: ...

    def load_container(self, image: Any, name: str, **kwargs: Any) -> Any: ...

    def open_for_rewrite(self, image: Any, entry: Any, **kwargs: Any) -> Any: ...

    def member_uncached(self, container: Any, index: int) -> bytes: ...

    def preload_names(self, image: Any) -> Any: ...

    def preload_copies(self, image: Any, **kwargs: Any) -> Any: ...


__all__ = ["Discs"]

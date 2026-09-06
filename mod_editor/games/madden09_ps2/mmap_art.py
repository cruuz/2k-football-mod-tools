"""Compatibility import: ``MMAP`` now lives in the shared format package.

The ``MMAP`` decoder was written here because Madden NFL 09 was the first
module that needed it.  It is not a Madden fact: every EA Tiburon PlayStation 2
disc measured carries the same wrapper, and
``docs/owner/scoping/READINESS_SUMMARY.md`` records the decoder drawing
13,053 of 13,802 sampled ``MMAP`` members across ten discs.  While it sat in a
game package no other game could reach it -- ``mod_editor/games/_formats``'s own
rule is that *a game imports a format package; it never imports another game* --
so NCAA Football 09's texture row was filed ``read-only-mapped`` for want of an
import, not for want of a decoder.

The implementation now lives in :mod:`mod_editor.games._formats.mmap_art` and
every game may import it.  This module re-exports it unchanged so that code
written against the old path keeps working; it adds nothing and decides
nothing.  New code should import the format package directly::

    from mod_editor.games._formats import mmap_art

The two underscore-prefixed helpers are re-exported by name because callers in
this repository use them: ``_scale_alpha`` and ``_unscale_alpha`` convert
between the PS2's 0..128 alpha scale and 0..255.
"""

from __future__ import annotations

from mod_editor.games._formats.mmap_art import *  # noqa: F401,F403
from mod_editor.games._formats.mmap_art import __all__ as _SHARED_ALL
from mod_editor.games._formats.mmap_art import _scale_alpha, _unscale_alpha  # noqa: F401

__all__ = list(_SHARED_ALL)

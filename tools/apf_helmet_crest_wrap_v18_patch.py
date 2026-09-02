#!/usr/bin/env python3
"""Compatibility alias for the promoted public helmet crest wrap backend.

V18 is no longer a parallel candidate implementation.  The editor-facing
``apf_helmet_crest_wrap_patch`` module owns the pinned algorithm and contract.
"""

from __future__ import annotations

import apf_helmet_crest_wrap_patch as _public
from apf_helmet_crest_wrap_patch import *  # noqa: F401,F403


# Retain the old research module's namespace escape hatch without retaining a
# second implementation.  New callers should import the public module.
v17 = _public


def __getattr__(name: str):
    return getattr(_public, name)


if __name__ == "__main__":
    raise SystemExit(_public.main())

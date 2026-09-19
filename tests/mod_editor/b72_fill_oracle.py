"""Unmodified rc97 fixed-span filler for byte identity tests."""
from nfl_vc_lz_fill import *
import nfl_txtr as t

def fill_stream(stream: bytes, decoded: bytes, stored_size: int, *, slack: int) -> tuple[bytes, int]:
    """Expand trailing matches into literals until len(stream) >= stored_size - slack (and <= stored)."""

    output_size, tag, offset_bits, tokens = parse_tokens(stream)
    toks = expand_tokens(tokens, decoded)
    expanded = 0
    current = serialize(output_size, tag, offset_bits, [tk[:3] if tk[0] == "M" else tk[:2] for tk in toks])
    if len(current) > stored_size:
        raise t.TxtrError("compressed stream already exceeds the stored body")
    # Expand from the START of the stream: every later token then sits further into the stored body,
    # which loosens the forward in-place constraint (output endpoint below the next unread byte)
    # for the whole tail.  Expanding at the end would tighten it exactly where it is tightest.
    idx = 0
    while len(current) < stored_size - slack and idx < len(toks):
        tk = toks[idx]
        if tk[0] == "M":
            _m, _d, ln, pos = tk
            literals = [("L", decoded[pos + k], pos + k) for k in range(ln)]
            trial = toks[:idx] + literals + toks[idx + 1:]
            trial_bytes = serialize(output_size, tag, offset_bits, [x[:3] if x[0] == "M" else x[:2] for x in trial])
            if len(trial_bytes) <= stored_size:
                toks = trial
                current = trial_bytes
                expanded += 1
                idx += ln          # skip the literals just inserted
                continue
            # too long to expand within the span: leave it and look further on
        idx += 1
    return current, expanded

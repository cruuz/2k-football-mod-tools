#!/usr/bin/env python3
"""Refit a decoded NFL 2K5 resource into its fixed compressed span WITHOUT touching the wrapper.

``nfl_txtr.rebuild_compressed_chunk_fixed_span`` recompresses and, when the new stream is shorter
than the stored body, zero-pads it and raises wrapper word +0x14 (the in-place decode scratch)
to cover the padding.  The retail loader reads the stored body at
``base + decoded_size + scratch - stored_size`` and decodes forward, so a scratch word far above
retail moves the body outside anything the retail game ever loaded; on 2026-09-03 the attract
demo hung on a resource load with scratch words raised from 0x10 to 0xB0 and 0x60 to 0x7B0.

This module keeps the wrapper byte-identical: after compressing, trailing match tokens are
expanded back into literals until the stream fills the stored body (padding <= the retail scratch
allowance), and the in-place constraint is re-checked against the retail scratch value.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import nfl_txtr as t  # noqa: E402


@dataclass(frozen=True)
class FillInfo:
    stored_size: int
    compressed_bytes: int
    filled_bytes: int
    padding_bytes: int
    matches_expanded: int
    scratch_bytes: int
    exact_minimum_scratch: int
    wrapper_identical: bool


def parse_tokens(stream: bytes) -> tuple[int, int, int, list]:
    """-> (output_size, tag, offset_bits, tokens) with tokens ('L', byte) or ('M', distance, length)."""

    output_size, tag = struct.unpack_from("<II", stream, 0)
    offset_bits = stream[8]
    dmask = (1 << offset_bits) - 1
    lmask = (1 << (16 - offset_bits)) - 1
    src, flags, mask, dst, tokens = 10, stream[9], 1, 0, []
    while dst < output_size:
        if flags & mask:
            code = struct.unpack_from("<H", stream, src)[0]
            src += 2
            d, ln = code & dmask, ((code >> offset_bits) & lmask) + 3
            tokens.append(("M", d, ln))
            dst += ln
        else:
            tokens.append(("L", stream[src]))
            src += 1
            dst += 1
        mask = (mask << 1) & 0xFF
        if mask == 0 and dst < output_size:
            flags = stream[src]
            src += 1
            mask = 1
    return output_size, tag, offset_bits, tokens


def serialize(output_size: int, tag: int, offset_bits: int, tokens: list) -> bytes:
    out = bytearray(struct.pack("<II", output_size, tag) + bytes([offset_bits]))
    i = 0
    while i < len(tokens):
        group = tokens[i: i + 8]
        flags = 0
        body = bytearray()
        for k, tok in enumerate(group):
            if tok[0] == "M":
                flags |= 1 << k
                body += struct.pack("<H", tok[1] | ((tok[2] - 3) << offset_bits))
            else:
                body.append(tok[1])
        out.append(flags)
        out += body
        i += 8
    return bytes(out)


def expand_tokens(tokens: list, decoded: bytes) -> list:
    """Attach output offsets so a match can be expanded into its literal bytes."""

    pos = 0
    out = []
    for tok in tokens:
        if tok[0] == "M":
            out.append(("M", tok[1], tok[2], pos))
            pos += tok[2]
        else:
            out.append(("L", tok[1], pos))
            pos += 1
    return out


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


def compress_optimal(decoded: bytes, *, stream_tag: int, offset_bits: int, chain_limit: int = 256) -> bytes:
    """Optimal-parse VC-LZ encoder: the same token format as the retail packer, fewer bytes.

    The game's packer (and ``nfl_txtr.compress_vc_lz``, which reproduces it to the byte) is
    greedy: at every position it takes the longest match it can see.  That is not the cheapest
    parse.  A flag bit costs 1/8 byte, a literal one byte, a match two bytes, so a short match
    followed by a long one often beats a long match followed by literals.  This encoder scores
    every parse with exact token costs and keeps the cheapest, which on the shipped scenes saves
    roughly one to three percent -- the headroom an edited model needs to fit back into its
    retail span, since the retail streams were packed to within a few bytes of it.

    Match candidates come from a hash chain over three-byte keys, most recent first, capped at
    ``chain_limit`` per position; a longer chain finds slightly better matches more slowly.
    Matches never overlap their source (the title's decoder copies backwards), exactly like the
    greedy encoder, and the result is verified by the ported retail decoder before use.
    """

    n = len(decoded)
    if n == 0:
        raise t.TxtrError("VC-LZ cannot encode an empty output buffer")
    length_bits = 16 - offset_bits
    max_distance = (1 << offset_bits) - 1
    max_length = ((1 << length_bits) - 1) + 3
    MIN = 3
    src = decoded
    # longest usable match at every position (length, distance)
    best_len = [0] * n
    best_dist = [0] * n
    chains: dict[int, list[int]] = {}
    for i in range(n - MIN + 1):
        key = src[i] | (src[i + 1] << 8) | (src[i + 2] << 16)
        chain = chains.get(key)
        if chain:
            cutoff = i - max_distance
            blen = 0
            bdist = 0
            seen = 0
            for c in reversed(chain):
                if c < cutoff:
                    break
                seen += 1
                if seen > chain_limit:
                    break
                d = i - c
                if d < MIN:
                    continue
                limit = min(max_length, n - i, d)
                if limit <= blen:
                    continue
                L = MIN
                while L < limit and src[c + L] == src[i + L]:
                    L += 1
                if L > blen:
                    blen, bdist = L, d
                    if blen == max_length:
                        break
            if blen >= MIN:
                best_len[i] = blen
                best_dist[i] = bdist
            # prune the chain to the window every so often
            if len(chain) > 4096 and chain[-1] - chain[0] > 2 * max_distance:
                del chain[: len(chain) // 2]
            chain.append(i)
        else:
            chains[key] = [i]
    # backward dynamic programme in eighth-bytes: literal 9, match 17
    INF = 1 << 60
    cost = [0] * (n + 1)
    choice = [1] * (n + 1)          # length consumed at i (1 = literal)
    for i in range(n - 1, -1, -1):
        c = cost[i + 1] + 9
        ch = 1
        m = best_len[i]
        if m >= MIN:
            for L in range(MIN, m + 1):
                v = cost[i + L] + 17
                if v < c:
                    c, ch = v, L
        cost[i], choice[i] = c, ch
    tokens: list = []
    i = 0
    while i < n:
        L = choice[i]
        if L == 1:
            tokens.append(("L", src[i]))
        else:
            tokens.append(("M", best_dist[i], L))
        i += L
    stream = serialize(n, stream_tag, offset_bits, tokens)
    back, info = t.decompress_vc_lz(stream, n)
    if back != decoded or info.consumed_bytes != len(stream):
        raise t.TxtrError("optimal VC-LZ encoder failed its round-trip check")
    return stream


def rebuild_fixed_span_filled(template_span: bytes, decoded: bytes, *, max_candidate_comparisons: int = 50_000_000,
                              encoder: str = "greedy") -> tuple[bytes, FillInfo]:
    """Like nfl_txtr.rebuild_compressed_chunk_fixed_span, but the wrapper (incl. +0x14) stays retail.

    ``encoder="greedy"`` reproduces the retail packer; ``"optimal"`` uses :func:`compress_optimal`,
    which packs tighter and is what lets an edited resource fit its retail span; ``"auto"`` tries
    greedy first and falls back to optimal only when greedy does not fit.
    """

    fields = t.HEADER.unpack_from(template_span)
    raw_kind, stored_size, system_bytes, video_bytes, magic, scratch, r0, r1 = fields
    if magic != t.COMPRESSED_SENTINEL:
        raise t.TxtrError("template is not a compressed span")
    if len(decoded) != system_bytes + video_bytes:
        raise t.TxtrError("decoded size does not match the wrapper")
    chunk = t.parse_chunks(template_span, allow_trailing=True)[0]
    _tdec, tinfo = t.decode_chunk(template_span, chunk)
    tstream = template_span[t.HEADER.size: t.HEADER.size + tinfo.consumed_bytes]
    _osz, tag = struct.unpack_from("<II", tstream, 0)
    offset_bits = tstream[8]
    if encoder not in ("greedy", "optimal", "auto"):
        raise t.TxtrError(f"unknown VC-LZ encoder {encoder!r}")
    compressed = None
    if encoder in ("greedy", "auto"):
        try:
            compressed, _ = t.compress_vc_lz(decoded, stream_tag=tag, offset_bits=offset_bits, max_encoded_size=stored_size,
                                             max_candidate_comparisons=max_candidate_comparisons, verify_roundtrip=True)
        except t.TxtrError:
            if encoder == "greedy":
                raise
    if compressed is None:
        compressed = compress_optimal(decoded, stream_tag=tag, offset_bits=offset_bits)
        if len(compressed) > stored_size:
            raise t.TxtrError(f"VC-LZ stream needs {len(compressed)} bytes, more than the {stored_size}-byte stored body "
                              "even with optimal parsing")
    filled, expanded = fill_stream(compressed, decoded, stored_size, slack=min(scratch, 16))
    padding = stored_size - len(filled)
    exact_min = t.minimum_vc_lz_overlap_scratch(filled, stored_size, len(decoded))
    if padding > scratch or exact_min > scratch:
        raise t.TxtrError(f"cannot keep the retail scratch word: padding {padding}, needs {exact_min}, retail {scratch}")
    rebuilt = template_span[: t.HEADER.size] + filled + bytes(padding)
    back, binfo = t.decode_chunk(rebuilt, chunk)
    if back != decoded or len(rebuilt) != len(template_span) or binfo.consumed_bytes != len(filled):
        raise t.TxtrError("filled span failed independent decode verification")
    info = FillInfo(stored_size=stored_size, compressed_bytes=len(compressed), filled_bytes=len(filled),
                    padding_bytes=padding, matches_expanded=expanded, scratch_bytes=scratch,
                    exact_minimum_scratch=exact_min, wrapper_identical=rebuilt[: t.HEADER.size] == template_span[: t.HEADER.size])
    return rebuilt, info


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("template_span")
    ap.add_argument("decoded")
    ap.add_argument("out_span")
    args = ap.parse_args()
    span, info = rebuild_fixed_span_filled(Path(args.template_span).read_bytes(), Path(args.decoded).read_bytes())
    Path(args.out_span).write_bytes(span)
    print(info, hashlib.sha256(span).hexdigest()[:16])

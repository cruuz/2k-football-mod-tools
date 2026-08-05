/* Minimum-cost H7A encoder.
 *
 * The greedy encoder in the Python writers takes the longest legal match at
 * every position. That is not the cheapest overall parse: a shorter match now
 * often leaves a much longer one available immediately after. The no-overlap
 * rule makes the gap wider, because clamping a match to its distance turns many
 * long matches into short ones and greedy has no way to trade.
 *
 * It matters because APF's allocations are fixed and tight. endzone_l0 gives
 * 110,592 bytes where retail uses 110,320, and a painted rectangle scatters
 * through the Xenos tiling rather than staying local, so any edit costs a few
 * hundred compressed bytes. Greedy lands 21 bytes over; that is the whole reason
 * this exists.
 *
 * The parse is a backward shortest path. cost[i] is the fewest output bits
 * needed to encode data[i..end); each position takes the cheaper of a literal
 * (8 bits + 1 descriptor bit) or any legal match (16 bits + 1 descriptor bit).
 * Both carry the same descriptor bit, so counting in bits keeps the comparison
 * honest rather than rounding a byte away.
 *
 * Match candidates come from 3-byte hash chains, the same window the decoder
 * allows, and are never emitted with length > distance.
 *
 *   apf_h7a_optimal <shift> < raw > encoded
 *
 * Exit status is non-zero on any malformed input, so a caller can fall back to
 * the Python encoder rather than trust a partial stream.
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HASH_BITS 16
#define HASH_SIZE (1 << HASH_BITS)
#define NO_POS (-1)

/* Candidates examined per position. Beyond a few hundred the parse stops
 * improving on real texture data, and the cost is linear in this number. */
#define MAX_CANDIDATES 512

static uint32_t hash3(const uint8_t *p) {
    return (uint32_t)((p[0] << 16 | p[1] << 8 | p[2]) * 2654435761u) >> (32 - HASH_BITS);
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "usage: apf_h7a_optimal <shift>  (raw on stdin)\n");
        return 2;
    }
    int shift = atoi(argv[1]);
    if (shift < 1 || shift > 15) {
        fprintf(stderr, "invalid shift %d\n", shift);
        return 2;
    }
    const int max_distance = (1 << shift) - 1;
    const int max_length = ((1 << (16 - shift)) - 1) + 3;

    size_t capacity = 1 << 20, size = 0;
    uint8_t *data = malloc(capacity);
    if (!data) return 3;
    for (;;) {
        if (size == capacity) {
            capacity *= 2;
            uint8_t *grown = realloc(data, capacity);
            if (!grown) { free(data); return 3; }
            data = grown;
        }
        size_t got = fread(data + size, 1, capacity - size, stdin);
        if (got == 0) break;
        size += got;
    }
    if (size == 0) { free(data); return 0; }
    const int32_t n = (int32_t)size;

    /* Forward pass: hash chains over every 3-byte key.
     *
     * cand[i] is the newest position STRICTLY BEFORE i sharing i's 3-byte key,
     * recorded before i itself is inserted.  Walking cand[i] then prev[...]
     * therefore visits only legal candidates, nearest first.
     *
     * Taking head[hash] directly instead would start at the LAST occurrence in
     * the whole file and force the backward pass to skip every position above i
     * before reaching a usable one.  Those skips are not candidates, so they do
     * not count against MAX_CANDIDATES and the walk is unbounded: on texture
     * data, where one key such as three zero bytes covers a large share of all
     * positions, that is quadratic and takes minutes on a few hundred KB. */
    int32_t *head = malloc(sizeof(int32_t) * HASH_SIZE);
    int32_t *prev = malloc(sizeof(int32_t) * (size_t)n);
    int32_t *cand = malloc(sizeof(int32_t) * (size_t)n);
    if (!head || !prev || !cand) {
        free(data); free(head); free(prev); free(cand); return 3;
    }
    for (int32_t i = 0; i < HASH_SIZE; i++) head[i] = NO_POS;
    for (int32_t i = 0; i < n; i++) cand[i] = NO_POS;
    for (int32_t i = 0; i + 2 < n; i++) {
        uint32_t h = hash3(data + i);
        cand[i] = head[h];
        prev[i] = head[h];
        head[h] = i;
    }

    /* Backward pass: cost in bits, plus the chosen (length, distance). */
    uint32_t *cost = malloc(sizeof(uint32_t) * (size_t)(n + 1));
    uint16_t *best_len = malloc(sizeof(uint16_t) * (size_t)(n + 1));
    uint16_t *best_dist = malloc(sizeof(uint16_t) * (size_t)(n + 1));
    if (!cost || !best_len || !best_dist) {
        free(data); free(head); free(prev); free(cand);
        free(cost); free(best_len); free(best_dist);
        return 3;
    }
    cost[n] = 0;
    for (int32_t i = n - 1; i >= 0; i--) {
        uint32_t cheapest = 9 + cost[i + 1];   /* literal: 8 bits + descriptor */
        uint16_t chosen_len = 0, chosen_dist = 0;
        if (i + 3 <= n) {
            int candidates = 0;
            for (int32_t candidate = cand[i];
                 candidate != NO_POS && candidate >= i - max_distance;
                 candidate = prev[candidate]) {
                int32_t distance = i - candidate;
                int32_t limit = max_length;
                if (limit > n - i) limit = (int32_t)(n - i);
                if (limit > distance) limit = distance;   /* never overlap */
                if (limit < 3) { if (++candidates >= MAX_CANDIDATES) break; continue; }
                int32_t length = 0;
                while (length < limit && data[candidate + length] == data[i + length]) {
                    length++;
                }
                /* Try the full match and two shorter cuts: a shorter match here
                 * sometimes exposes a much longer one immediately after. */
                int32_t trials[3] = { length, length - 1, length / 2 };
                for (int t = 0; t < 3; t++) {
                    int32_t trial = trials[t];
                    if (trial < 3) continue;
                    uint32_t total = 17 + cost[i + trial];  /* 16 bits + descriptor */
                    if (total < cheapest) {
                        cheapest = total;
                        chosen_len = (uint16_t)trial;
                        chosen_dist = (uint16_t)distance;
                    }
                }
                if (++candidates >= MAX_CANDIDATES) break;
            }
        }
        cost[i] = cheapest;
        best_len[i] = chosen_len;
        best_dist[i] = chosen_dist;
    }

    /* Emit the chosen parse in the descriptor-byte framing the decoder expects. */
    size_t out_capacity = size + (size / 4) + 64, out_size = 0;
    uint8_t *out = malloc(out_capacity);
    if (!out) {
        free(data); free(head); free(prev); free(cand);
        free(cost); free(best_len); free(best_dist);
        return 3;
    }
    int32_t at = 0;
    while (at < n) {
        if (out_size + 24 > out_capacity) {
            out_capacity *= 2;
            uint8_t *grown = realloc(out, out_capacity);
            if (!grown) { free(out); return 3; }
            out = grown;
        }
        size_t descriptor_at = out_size++;
        uint8_t descriptor = 0;
        for (int bit = 0; bit < 8 && at < n; bit++) {
            uint16_t length = best_len[at];
            if (length >= 3) {
                uint16_t distance = best_dist[at];
                uint32_t word = ((uint32_t)(length - 3) << shift) | distance;
                descriptor |= (uint8_t)(1u << bit);
                out[out_size++] = (uint8_t)(word >> 8);
                out[out_size++] = (uint8_t)(word & 0xFF);
                at += length;
            } else {
                out[out_size++] = data[at++];
            }
        }
        out[descriptor_at] = descriptor;
    }

    if (fwrite(out, 1, out_size, stdout) != out_size) {
        fprintf(stderr, "short write\n");
        return 4;
    }
    free(data); free(head); free(prev); free(cand);
    free(cost); free(best_len); free(best_dist); free(out);
    return 0;
}

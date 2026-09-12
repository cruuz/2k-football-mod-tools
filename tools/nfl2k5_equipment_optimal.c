/* Exact VC-LZ optimal parse, matching nfl2k5_equipment_lz.py tie breaking.
 * Build: cc -O3 -std=c99 -Wall -Wextra -Werror -o nfl2k5_equipment_optimal nfl2k5_equipment_optimal.c
 * Protocol: args count, tag, offset_bits, max_output, max_comparisons;
 * raw input on stdin, encoded stream on stdout. Exit 2 means bounds/search/fit
 * refusal; the caller falls back to the original Python encoder in all cases.
 * Each candidate chain is bounded by the format's 8191-byte maximum window.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static unsigned key3(const unsigned char *p) {
    return ((unsigned)p[0] * 251u + (unsigned)p[1] * 31u + p[2]) & 65535u;
}
static void put32(unsigned char *p, uint32_t v) {
    for (unsigned i = 0; i < 4; ++i) p[i] = (unsigned char)(v >> (8 * i));
}
int main(int argc, char **argv) {
    if (argc != 6) return 2;
    uint64_t arg[5];
    for (int i = 0; i < 5; ++i) {
        char *end = NULL;
        arg[i] = strtoull(argv[i + 1], &end, 10);
        if (!*argv[i + 1] || *end || argv[i + 1][0] == '-') return 2;
    }
    if (!arg[0] || arg[0] > 2097152 || arg[1] > UINT32_MAX ||
        arg[2] < 10 || arg[2] > 13 || arg[3] < 10 || arg[3] > 4194304 || !arg[4]) return 2;
    unsigned n = (unsigned)arg[0], bits = (unsigned)arg[2];
    unsigned max_distance = (1u << bits) - 1, max_length = (1u << (16 - bits)) + 2;
    unsigned char *src = malloc(n), *lengths = calloc(n, 1), *choices = calloc(n, 1);
    unsigned char *out = malloc((size_t)arg[3]);
    uint16_t *distances = calloc(n, sizeof(*distances));
    uint32_t *costs = calloc((size_t)n + 1, sizeof(*costs));
    int32_t *previous = malloc((size_t)n * sizeof(*previous));
    int32_t *heads = malloc(65536 * sizeof(*heads));
    int status = 2;
    if (!src || !lengths || !choices || !out || !distances || !costs || !previous || !heads) goto done;
#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    if (fread(src, 1, n, stdin) != n || fgetc(stdin) != EOF) goto done;
    for (unsigned i = 0; i < 65536; ++i) heads[i] = -1;
    uint64_t comparisons = 0;
    for (unsigned pos = 0; pos + 2 < n; ++pos) {
        unsigned key = key3(src + pos), best = 2, distance = 0;
        unsigned upper = n - pos < max_length ? n - pos : max_length;
        for (int32_t prev = heads[key]; prev >= 0; prev = previous[prev]) {
            unsigned d = pos - (unsigned)prev;
            if (d > max_distance) break;
            /* Hash collisions are not candidates in the Python 3-byte map. */
            if (memcmp(src + pos, src + prev, 3) != 0) continue;
            if (++comparisons > arg[4]) goto done;
            unsigned limit = upper < d ? upper : d;
            if (limit <= best || memcmp(src + pos, src + prev, best + 1) != 0) continue;
            unsigned len = best + 1;
            while (len < limit && src[pos + len] == src[prev + len]) ++len;
            best = len; distance = d;
            if (best == upper) break;
        }
        if (best >= 3) { lengths[pos] = (unsigned char)best; distances[pos] = (uint16_t)distance; }
        previous[pos] = heads[key]; heads[key] = (int32_t)pos;
    }
    for (unsigned pos = n; pos-- > 0;) {
        uint32_t cost = 9 + costs[pos + 1];
        unsigned choice = 1;
        for (unsigned len = 3; len <= lengths[pos]; ++len) {
            uint32_t candidate = 17 + costs[pos + len];
            if (candidate < cost) { cost = candidate; choice = len; }
        }
        costs[pos] = cost; choices[pos] = (unsigned char)choice;
    }
    unsigned required = 9 + (costs[0] + 7) / 8;
    if (required > arg[3]) goto done;
    put32(out, n); put32(out + 4, (uint32_t)arg[1]); out[8] = (unsigned char)bits;
    unsigned cursor = 9, pos = 0;
    while (pos < n) {
        unsigned flag = cursor++;
        out[flag] = 0;
        for (unsigned bit = 0; bit < 8 && pos < n; ++bit) {
            unsigned len = choices[pos];
            if (len == 1) out[cursor++] = src[pos];
            else {
                unsigned token = distances[pos] | ((len - 3) << bits);
                out[flag] |= (unsigned char)(1u << bit);
                out[cursor++] = (unsigned char)token;
                out[cursor++] = (unsigned char)(token >> 8);
            }
            pos += len;
        }
    }
    if (cursor != required || fwrite(out, 1, cursor, stdout) != cursor || fflush(stdout)) goto done;
    status = 0;
done:
    free(src); free(lengths); free(choices); free(out); free(distances);
    free(costs); free(previous); free(heads);
    return status;
}

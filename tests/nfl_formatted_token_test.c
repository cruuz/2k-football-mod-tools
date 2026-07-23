#include "recovered/nfl2k5/formatted_token.h"

#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int expect(int condition, const char *message)
{
    if (condition) {
        return 0;
    }
    fprintf(stderr, "NFL formatted-token test: %s\n", message);
    return 1;
}

static uint32_t float_bits(float value)
{
    uint32_t result = 0U;
    memcpy(&result, &value, sizeof(result));
    return result;
}

static int compare_tsv(const char *path)
{
    FILE *stream = fopen(path, "r");
    if (stream == NULL) {
        fprintf(stderr, "NFL formatted-token test: could not open %s\n", path);
        return 1;
    }
    char line[1024];
    if (fgets(line, sizeof(line), stream) == NULL ||
        strstr(line, "index\trecord_va\tname_pointer\tname\t") != line) {
        fclose(stream);
        fprintf(stderr, "NFL formatted-token test: TSV header differs\n");
        return 1;
    }
    int failures = 0;
    size_t rows = 0U;
    while (fgets(line, sizeof(line), stream) != NULL) {
        size_t index = 0U;
        char name[64];
        uint32_t slot = 0U;
        uint32_t flags = 0U;
        uint32_t bits[6] = {0U};
        const int fields = sscanf(
            line,
            "%zu\t%*[^\t]\t%*[^\t]\t%63[^\t]\t%" SCNu32
            "\t%*f\t%*f\t%*f\t%*f\t%*f\t%*f\t%" SCNu32
            "\t%" SCNx32 "\t%" SCNx32 "\t%" SCNx32
            "\t%" SCNx32 "\t%" SCNx32 "\t%" SCNx32,
            &index, name, &slot, &flags, &bits[0], &bits[1], &bits[2],
            &bits[3], &bits[4], &bits[5]);
        const VcNflFormattedToken *token = vc_nfl_formatted_token_at(rows);
        if (fields != 10 || index != rows || token == NULL ||
            strcmp(name, token->name) != 0 || slot != token->texture_slot ||
            flags != token->flags || bits[0] != float_bits(token->u0) ||
            bits[1] != float_bits(token->v0) ||
            bits[2] != float_bits(token->u1) ||
            bits[3] != float_bits(token->v1) ||
            bits[4] != float_bits(token->height_scale) ||
            bits[5] != float_bits(token->width_over_height)) {
            fprintf(stderr,
                    "NFL formatted-token test: TSV/native mismatch at row %zu\n",
                    rows);
            ++failures;
        }
        ++rows;
    }
    fclose(stream);
    if (rows != vc_nfl_formatted_token_count()) {
        fprintf(stderr,
                "NFL formatted-token test: TSV rows=%zu native rows=%zu\n",
                rows, vc_nfl_formatted_token_count());
        ++failures;
    }
    return failures;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s nfl_formatted_tokens.tsv\n", argv[0]);
        return 2;
    }
    int failures = 0;
    failures += compare_tsv(argv[1]);
    size_t consumed = 99U;
    failures += expect(vc_nfl_formatted_token_count() == 57U,
                       "serialized token count differs");
    const VcNflFormattedToken *tm = vc_nfl_formatted_token_at(40U);
    failures += expect(tm != NULL && strcmp(tm->name, "TM") == 0 &&
                           tm->texture_slot == 9U && tm->u0 == 0.0f &&
                           tm->v0 == 0.0f && tm->u1 == 1.0f &&
                           tm->v1 == 1.0f && tm->height_scale == 1.0f &&
                           tm->width_over_height == 1.0f && tm->flags == 1U,
                       "TM table record differs");
    failures += expect(vc_nfl_formatted_token_match_ascii("|TM|", &consumed) ==
                               40 &&
                           consumed == 4U,
                       "uppercase TM did not match");
    failures += expect(vc_nfl_formatted_token_match_ascii("|tm|tail", &consumed) ==
                               40 &&
                           consumed == 4U,
                       "case-insensitive TM did not match");
    failures += expect(
        vc_nfl_formatted_token_match_ascii("|M_PRIMARY|", &consumed) == 45 &&
            consumed == 11U,
        "M_PRIMARY did not match");
    failures += expect(
        vc_nfl_formatted_token_match_ascii("TM", &consumed) == -1 &&
            consumed == 0U &&
            vc_nfl_formatted_token_match_ascii("|TM", &consumed) == -1 &&
            consumed == 0U &&
            vc_nfl_formatted_token_match_ascii("|UNKNOWN|", &consumed) == -1 &&
            consumed == 0U,
        "invalid tokens were not bounded");
    failures += expect(vc_nfl_formatted_token_height(tm, 25.0f) == 25 &&
                           vc_nfl_formatted_token_width(tm, 25.0f) == 25,
                       "TM extent differs");
    const VcNflFormattedToken *yellow = vc_nfl_formatted_token_at(34U);
    failures += expect(vc_nfl_formatted_token_height(yellow, 25.9f) == 25 &&
                           vc_nfl_formatted_token_width(yellow, 25.9f) == 51,
                       "CVTTSS2SI extent behavior differs");
    failures += expect(vc_nfl_formatted_token_height(NULL, 25.0f) == 0 &&
                           vc_nfl_formatted_token_width(tm, -1.0f) == 0 &&
                           vc_nfl_formatted_token_height(tm, NAN) == 0 &&
                           vc_nfl_formatted_token_at(57U) == NULL,
                       "invalid extent/table inputs were not rejected");
    if (failures != 0) {
        return 1;
    }
    printf("NFL_FORMATTED_TOKEN_NATIVE_PASS tokens=57 tm_index=40 "
           "tm_slot=9 tm_extent=25 casefold=ascii\n");
    return 0;
}

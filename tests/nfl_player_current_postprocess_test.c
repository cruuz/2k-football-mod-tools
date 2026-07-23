#include "recovered/nfl2k5/player_current_postprocess.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static void identity(float matrix[16], float x, float y, float z)
{
    size_t lane;
    for (lane = 0; lane < 16u; ++lane) {
        matrix[lane] = 0.0f;
    }
    matrix[0] = 1.0f;
    matrix[5] = 1.0f;
    matrix[10] = 1.0f;
    matrix[15] = 1.0f;
    matrix[12] = x;
    matrix[13] = y;
    matrix[14] = z;
}

static int near(float actual, float expected)
{
    return fabsf(actual - expected) <= 1.0e-5f;
}

static int require_matrix_scale(
    const float matrix[16], float sx, float sy, float sz,
    float tx, float ty, float tz)
{
    return near(matrix[0], sx) && near(matrix[5], sy) &&
        near(matrix[10], sz) && near(matrix[12], tx) &&
        near(matrix[13], ty) && near(matrix[14], tz) &&
        near(matrix[15], 1.0f);
}

int main(void)
{
    VcNflPlayerScaleTables tables;
    VcNflPlayerCurrentMatrices matrices;
    VcNflPlayerCurrentMatrices original;
    float vectors[VC_NFL_PLAYER_LOW_MATRIX_COUNT][4];
    VcNflPlayerCurrentPostprocessStatus status;
    size_t profile;
    size_t index;

    memset(&tables, 0, sizeof(tables));
    memset(vectors, 0, sizeof(vectors));
    for (index = 0; index < VC_NFL_PLAYER_LOW_MATRIX_COUNT; ++index) {
        vectors[index][0] = 1.0f;
    }
    for (profile = 0; profile < VC_NFL_PLAYER_SCALE_PROFILE_COUNT; ++profile) {
        tables.profiles[profile].reference = 150.0f;
        for (index = 0; index < VC_NFL_PLAYER_LOW_MATRIX_COUNT; ++index) {
            tables.profiles[profile].lower[index] = 2.0f + (float)profile;
            tables.profiles[profile].upper[index] = 2.0f + (float)profile;
        }
    }
    for (index = 0; index < VC_NFL_PLAYER_HIGH_MATRIX_COUNT; ++index) {
        tables.high_source[index] = 0u;
        identity(matrices.high[index], 0.0f, 0.0f, 0.0f);
    }
    identity(matrices.high[7], 3.0f, 4.0f, 5.0f);
    for (index = 0; index < VC_NFL_PLAYER_LOW_MATRIX_COUNT; ++index) {
        identity(matrices.low[index], 0.0f, 0.0f, 0.0f);
    }
    original = matrices;

    status = vc_nfl_player_current_postprocess(
        0u, 0u, 0u, false, &vectors[0][0], &tables, &matrices);
    if (status != VC_NFL_PLAYER_CURRENT_POSTPROCESS_OK ||
            memcmp(&matrices, &original, sizeof(matrices)) != 0) {
        fprintf(stderr, "zero-mask mutation\n");
        return 1;
    }

    status = vc_nfl_player_current_postprocess(
        0u, 0u, 1u, false, &vectors[0][0], &tables, &matrices);
    if (status != VC_NFL_PLAYER_CURRENT_POSTPROCESS_OK ||
            !require_matrix_scale(matrices.low[0], 1.0f, 2.0f, 2.0f, 0.0f, 0.0f, 0.0f) ||
            !require_matrix_scale(matrices.low[1], 1.0f, 1.0f, 1.0f, 0.0f, 0.0f, 0.0f) ||
            !require_matrix_scale(matrices.high[0], 1.0f, 2.0f, 2.0f, 0.0f, 0.0f, 0.0f) ||
            !require_matrix_scale(matrices.high[7], 1.0f, 2.0f, 2.0f, 3.0f, 4.0f, 5.0f)) {
        fprintf(stderr, "axis/pivot scale mismatch\n");
        return 1;
    }

    for (index = 0; index < VC_NFL_PLAYER_LOW_MATRIX_COUNT; ++index) {
        identity(matrices.low[index], 0.0f, 0.0f, 0.0f);
    }
    tables.profiles[0].lower[12] = 1.0f;
    tables.profiles[0].upper[12] = 1.0f;
    status = vc_nfl_player_current_postprocess(
        0u, 0u, UINT32_C(0x1000), true, &vectors[0][0], &tables, &matrices);
    if (status != VC_NFL_PLAYER_CURRENT_POSTPROCESS_OK ||
            !require_matrix_scale(
                matrices.low[12], 0x1.e66666p+0f, 0x1.e66666p+0f,
                0x1.e66666p+0f, 0.0f, 0.0f, 0.0f)) {
        fprintf(stderr, "conditional matrix-12 scale mismatch\n");
        return 1;
    }

    /* Select profile 2, interpolate channel 6 halfway from 1 to 3, and
       prove that the 62-byte schedule gates high matrices by low mask bit. */
    for (index = 0; index < VC_NFL_PLAYER_LOW_MATRIX_COUNT; ++index) {
        identity(matrices.low[index], 0.0f, 0.0f, 0.0f);
    }
    for (index = 0; index < VC_NFL_PLAYER_HIGH_MATRIX_COUNT; ++index) {
        identity(matrices.high[index], 0.0f, 0.0f, 0.0f);
        tables.high_source[index] = 24u;
    }
    identity(matrices.high[7], 3.0f, 4.0f, 5.0f);
    tables.high_source[7] = 6u;
    tables.profiles[2].reference = 150.0f;
    tables.profiles[2].multiplier = 0.01f;
    tables.profiles[2].lower[6] = 1.0f;
    tables.profiles[2].upper[6] = 3.0f;
    status = vc_nfl_player_current_postprocess(
        UINT32_C(2) << 3u, 50u, UINT32_C(1) << 6u, false,
        &vectors[0][0], &tables, &matrices);
    if (status != VC_NFL_PLAYER_CURRENT_POSTPROCESS_OK ||
            !require_matrix_scale(
                matrices.low[6], 1.0f, 2.0f, 2.0f, 0.0f, 0.0f, 0.0f) ||
            !require_matrix_scale(
                matrices.low[0], 1.0f, 1.0f, 1.0f, 0.0f, 0.0f, 0.0f) ||
            !require_matrix_scale(
                matrices.high[7], 1.0f, 2.0f, 2.0f, 3.0f, 4.0f, 5.0f) ||
            !require_matrix_scale(
                matrices.high[0], 1.0f, 1.0f, 1.0f, 0.0f, 0.0f, 0.0f)) {
        fprintf(stderr, "profile interpolation/schedule mismatch\n");
        return 1;
    }

    status = vc_nfl_player_current_postprocess(
        0u, 0u, 0u, false, NULL, &tables, &matrices);
    if (status != VC_NFL_PLAYER_CURRENT_POSTPROCESS_BAD_ARGUMENT) {
        fprintf(stderr, "bad argument status mismatch\n");
        return 1;
    }
    original = matrices;
    tables.high_source[0] = VC_NFL_PLAYER_LOW_MATRIX_COUNT;
    status = vc_nfl_player_current_postprocess(
        0u, 0u, UINT32_C(0x01ffffff), false,
        &vectors[0][0], &tables, &matrices);
    if (status != VC_NFL_PLAYER_CURRENT_POSTPROCESS_BAD_SCHEDULE ||
            memcmp(&matrices, &original, sizeof(matrices)) != 0) {
        fprintf(stderr, "bad schedule status/mutation mismatch\n");
        return 1;
    }
    if (strcmp(
            vc_nfl_player_current_postprocess_status_name(status),
            "bad_schedule") != 0) {
        fprintf(stderr, "status name mismatch\n");
        return 1;
    }

    puts("NFL_PLAYER_CURRENT_POSTPROCESS_TEST_PASS");
    return 0;
}

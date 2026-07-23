#include "recovered/nfl2k5/player_current_postprocess.h"

#include <math.h>
#include <stddef.h>

static void vc_matrix_multiply(
    float destination[16], const float left[16], const float right[16])
{
    float output[16];
    size_t row;
    size_t column;

    for (row = 0; row < 4u; ++row) {
        for (column = 0; column < 4u; ++column) {
            output[row * 4u + column] =
                left[row * 4u] * right[column] +
                left[row * 4u + 1u] * right[4u + column] +
                left[row * 4u + 2u] * right[8u + column] +
                left[row * 4u + 3u] * right[12u + column];
        }
    }
    for (row = 0; row < 16u; ++row) {
        destination[row] = output[row];
    }
}

static void vc_axis_perpendicular_scale(
    float matrix[16], const float axis[4], float scale)
{
    const float delta = 1.0f - scale;
    const float x = axis[0];
    const float y = axis[1];
    const float z = axis[2];

    matrix[0] = x * x * delta + scale;
    matrix[1] = y * x * delta;
    matrix[2] = z * x * delta;
    matrix[3] = 0.0f;
    matrix[4] = y * x * delta;
    matrix[5] = y * y * delta + scale;
    matrix[6] = y * z * delta;
    matrix[7] = 0.0f;
    matrix[8] = z * x * delta;
    matrix[9] = y * z * delta;
    matrix[10] = z * z * delta + scale;
    matrix[11] = 0.0f;
    matrix[12] = 0.0f;
    matrix[13] = 0.0f;
    matrix[14] = 0.0f;
    matrix[15] = 1.0f;
}

static void vc_transform_xyz(
    float output[4], const float matrix[16], const float vector[4])
{
    const float x = vector[0];
    const float y = vector[1];
    const float z = vector[2];

    output[0] = matrix[8] * z + x * matrix[0] + matrix[4] * y;
    output[1] = matrix[9] * z + matrix[1] * x + matrix[5] * y;
    output[2] = matrix[10] * z + matrix[2] * x + matrix[6] * y;
    output[3] = matrix[11] * z + matrix[3] * x + matrix[7] * y;
}

static void vc_normalize4(float output[4], const float input[4])
{
    const float squared =
        input[3] * input[3] + input[2] * input[2] +
        input[1] * input[1] + input[0] * input[0];
    float inverse;
    size_t lane;

    if (squared == 0.0f) {
        for (lane = 0; lane < 4u; ++lane) {
            output[lane] = 0.0f;
        }
        return;
    }

    /* PORTME: 0x0008D630 uses the Xbox SSE rsqrt seed plus one Newton step.
       sqrtf preserves the recovered value-level equation but not every bit. */
    inverse = 1.0f / sqrtf(squared);
    for (lane = 0; lane < 4u; ++lane) {
        output[lane] = input[lane] * inverse;
    }
}

static void vc_pretranslate(float matrix[16], float x, float y, float z)
{
    matrix[12] = matrix[8] * z + x * matrix[0] + matrix[4] * y + matrix[12];
    matrix[13] = matrix[9] * z + matrix[5] * y + matrix[1] * x + matrix[13];
    matrix[14] = matrix[10] * z + matrix[6] * y + matrix[2] * x + matrix[14];
}

static float vc_profile_scale(
    const VcNflPlayerScaleProfile *profile, size_t channel, float parameter)
{
    const float lower = profile->lower[channel];
    const float upper = profile->upper[channel];
    return (upper - lower) * parameter + lower;
}

VcNflPlayerCurrentPostprocessStatus vc_nfl_player_current_postprocess(
    uint32_t player_field_18,
    uint8_t player_field_2a,
    uint32_t update_mask,
    bool special_global_nonzero,
    const float *skeleton_vectors,
    const VcNflPlayerScaleTables *tables,
    VcNflPlayerCurrentMatrices *matrices)
{
    const uint32_t profile_index = (player_field_18 >> 3u) & 3u;
    const VcNflPlayerScaleProfile *profile;
    float scalar = (float)((uint32_t)player_field_2a + 150u);
    float parameter;
    size_t index;

    if (skeleton_vectors == NULL || tables == NULL || matrices == NULL) {
        return VC_NFL_PLAYER_CURRENT_POSTPROCESS_BAD_ARGUMENT;
    }
    for (index = 0; index < VC_NFL_PLAYER_HIGH_MATRIX_COUNT; ++index) {
        if (tables->high_source[index] >= VC_NFL_PLAYER_LOW_MATRIX_COUNT) {
            return VC_NFL_PLAYER_CURRENT_POSTPROCESS_BAD_SCHEDULE;
        }
    }

    if (450.0f <= scalar) {
        scalar = 450.0f;
    }
    else if (scalar <= 150.0f) {
        scalar = 150.0f;
    }
    profile = &tables->profiles[profile_index];
    parameter = (scalar - profile->reference) * profile->multiplier;

    for (index = 0; index < VC_NFL_PLAYER_LOW_MATRIX_COUNT; ++index) {
        float axial_scale[16];
        const float scale = vc_profile_scale(profile, index, parameter);

        if ((update_mask & (UINT32_C(1) << index)) == 0u) {
            continue;
        }
        vc_axis_perpendicular_scale(
            axial_scale, &skeleton_vectors[index * 4u], scale);
        vc_matrix_multiply(matrices->low[index], axial_scale, matrices->low[index]);
    }

    for (index = 0; index < VC_NFL_PLAYER_HIGH_MATRIX_COUNT; ++index) {
        const size_t source = tables->high_source[index];
        float transformed_axis[4];
        float normalized_axis[4];
        float pivot_scale[16];
        float x;
        float y;
        float z;
        float scale;

        if ((update_mask & (UINT32_C(1) << source)) == 0u) {
            continue;
        }
        scale = vc_profile_scale(profile, source, parameter);
        vc_transform_xyz(
            transformed_axis, matrices->high[index],
            &skeleton_vectors[source * 4u]);
        vc_normalize4(normalized_axis, transformed_axis);
        vc_axis_perpendicular_scale(pivot_scale, normalized_axis, scale);

        x = matrices->high[index][12];
        y = matrices->high[index][13];
        z = matrices->high[index][14];
        vc_pretranslate(pivot_scale, -x, -y, -z);
        pivot_scale[12] += x;
        pivot_scale[13] += y;
        pivot_scale[14] += z;
        vc_matrix_multiply(
            matrices->high[index], matrices->high[index], pivot_scale);
    }

    if (special_global_nonzero && (update_mask & UINT32_C(0x1000)) != 0u) {
        static const size_t basis_lanes[9] = {
            0u, 1u, 2u, 4u, 5u, 6u, 8u, 9u, 10u
        };
        const float factor = 0x1.e66666p+0f;
        for (index = 0; index < 9u; ++index) {
            const size_t lane = basis_lanes[index];
            matrices->low[12][lane] *= factor;
        }
    }
    return VC_NFL_PLAYER_CURRENT_POSTPROCESS_OK;
}

const char *vc_nfl_player_current_postprocess_status_name(
    VcNflPlayerCurrentPostprocessStatus status)
{
    switch (status) {
    case VC_NFL_PLAYER_CURRENT_POSTPROCESS_OK:
        return "ok";
    case VC_NFL_PLAYER_CURRENT_POSTPROCESS_BAD_ARGUMENT:
        return "bad_argument";
    case VC_NFL_PLAYER_CURRENT_POSTPROCESS_BAD_SCHEDULE:
        return "bad_schedule";
    default:
        return "unknown";
    }
}

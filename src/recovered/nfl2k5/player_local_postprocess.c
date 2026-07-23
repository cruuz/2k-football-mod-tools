#include "recovered/nfl2k5/player_local_postprocess.h"

#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define VC_LOCAL_CONSTANT_BASE UINT32_C(0x004ef8e0)

static const uint8_t vc_title_low_to_high[VC_NFL_PLAYER_LOW_MATRIX_COUNT] = {
    0u, 1u, 2u, 3u, 4u, 13u, 14u, 15u, 16u, 26u, 27u, 28u, 29u,
    30u, 31u, 32u, UINT8_C(0xff), 37u, 44u, 45u, 46u,
    UINT8_C(0xff), 51u, 58u, 59u
};

static const char *const vc_low_names[VC_NFL_PLAYER_LOW_MATRIX_COUNT] = {
    "root", "lfemur", "ltibia", "lfoot", "ltoes", "rfemur",
    "rtibia", "rfoot", "rtoes", "waist", "thorax", "neck", "head",
    "lcollar", "lhumerus", "lelbow", "lwrist", "lhand", "rcollar",
    "rhumerus", "relbow", "rwrist", "rhand", "lshoulderpad",
    "rshoulderpad"
};

static const char *const vc_high_names[VC_NFL_PLAYER_HIGH_MATRIX_COUNT] = {
    "root", "lfemur", "ltibia", "lfoot", "ltoes",
    "l_kneepad_muscle", "l_calf_muscle", "l_knee_hinge",
    "l_quad_center_muscle", "l_femur_twist_0", "l_femur_twist_50",
    "l_gluteus_muscle", "l_stripe_muscle", "rfemur", "rtibia",
    "rfoot", "rtoes", "r_kneepad_muscle", "r_calf_muscle",
    "r_knee_hinge", "r_quad_center_muscle", "r_femur_twist_0",
    "r_femur_twist_50", "r_gluteus_muscle", "r_stripe_muscle", "groin",
    "waist", "thorax", "neck", "head", "lcollar", "lhumerus",
    "lelbow", "l_forearm_twist_25", "l_forearm_twist_50",
    "l_forearm_twist_75", "l_forearm_twist_100", "lhand",
    "l_arm_hinge_muscle", "l_arm_hinge_muscle_2", "l_ulna_muscle",
    "l_triceps_muscle", "l_radius_muscle", "l_biceps_muscle", "rcollar",
    "rhumerus", "relbow", "r_forearm_twist_25", "r_forearm_twist_50",
    "r_forearm_twist_75", "r_forearm_twist_100", "rhand",
    "r_biceps_muscle", "r_triceps_muscle", "r_ulna_muscle",
    "r_radius_muscle", "r_arm_hinge_muscle", "r_arm_hinge_muscle_2",
    "lshoulderpad", "rshoulderpad", "r_gluteus_muscle_2",
    "l_gluteus_muscle_2"
};

static const float *vc_constant(
    const VcNflPlayerLocalPostprocessTables *tables, uint32_t address)
{
    return &tables->local_constants[(address - VC_LOCAL_CONSTANT_BASE) / 4u];
}

static float vc_c(
    const VcNflPlayerLocalPostprocessTables *tables, uint32_t address)
{
    return *vc_constant(tables, address);
}

static void vc_trace(
    VcNflPlayer92140TraceCallback observer, void *user_data,
    uint32_t sequence, uint32_t address)
{
    if (observer != NULL) {
        observer(user_data, sequence, address);
    }
}

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
    memcpy(destination, output, sizeof(output));
}

static float vc_length4(const float value[4])
{
    return sqrtf(
        value[0] * value[0] + value[1] * value[1] +
        value[2] * value[2] + value[3] * value[3]);
}

static void vc_normalize4(float output[4], const float input[4])
{
    const float squared =
        input[0] * input[0] + input[1] * input[1] +
        input[2] * input[2] + input[3] * input[3];
    float inverse;

    if (squared == 0.0f) {
        memset(output, 0, 4u * sizeof(float));
        return;
    }
    /* PORTME(0x0008D630): value-equivalent sqrtf path, not Xbox rsqrt bits. */
    inverse = 1.0f / sqrtf(squared);
    output[0] = input[0] * inverse;
    output[1] = input[1] * inverse;
    output[2] = input[2] * inverse;
    output[3] = input[3] * inverse;
}

static void vc_cross4(float output[4], const float left[4], const float right[4])
{
    output[0] = left[1] * right[2] - left[2] * right[1];
    output[1] = left[2] * right[0] - left[0] * right[2];
    output[2] = left[0] * right[1] - left[1] * right[0];
    output[3] = 0.0f;
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

static void vc_axis_rotation(
    float output[16], const float axis[4], float sine, float cosine)
{
    const float delta = 1.0f - cosine;
    const float x = axis[0];
    const float y = axis[1];
    const float z = axis[2];
    output[0] = x * x * delta + cosine;
    output[1] = sine * z + y * x * delta;
    output[2] = z * x * delta - sine * y;
    output[3] = 0.0f;
    output[4] = y * x * delta - sine * z;
    output[5] = y * y * delta + cosine;
    output[6] = sine * x + z * y * delta;
    output[7] = 0.0f;
    output[8] = sine * y + z * x * delta;
    output[9] = z * y * delta - sine * x;
    output[10] = z * z * delta + cosine;
    output[11] = 0.0f;
    output[12] = 0.0f;
    output[13] = 0.0f;
    output[14] = 0.0f;
    output[15] = 1.0f;
}

static void vc_axis_scale(float output[16], const float axis[4], float scale)
{
    const float delta = scale - 1.0f;
    const float x = axis[0];
    const float y = axis[1];
    const float z = axis[2];
    output[0] = x * x * delta + 1.0f;
    output[1] = y * x * delta;
    output[2] = z * x * delta;
    output[3] = 0.0f;
    output[4] = y * x * delta;
    output[5] = y * y * delta + 1.0f;
    output[6] = y * z * delta;
    output[7] = 0.0f;
    output[8] = z * x * delta;
    output[9] = y * z * delta;
    output[10] = z * z * delta + 1.0f;
    output[11] = 0.0f;
    output[12] = 0.0f;
    output[13] = 0.0f;
    output[14] = 0.0f;
    output[15] = 1.0f;
}

static void vc_axis_two_scale(
    float output[16], const float axis[4], float parallel, float perpendicular)
{
    const float delta = parallel - perpendicular;
    const float x = axis[0];
    const float y = axis[1];
    const float z = axis[2];
    output[0] = x * x * delta + perpendicular;
    output[1] = y * x * delta;
    output[2] = x * z * delta;
    output[3] = 0.0f;
    output[4] = y * x * delta;
    output[5] = y * y * delta + perpendicular;
    output[6] = y * z * delta;
    output[7] = 0.0f;
    output[8] = x * z * delta;
    output[9] = y * z * delta;
    output[10] = z * z * delta + perpendicular;
    output[11] = 0.0f;
    output[12] = 0.0f;
    output[13] = 0.0f;
    output[14] = 0.0f;
    output[15] = 1.0f;
}

static void vc_scale_columns(float matrix[16], float x, float y, float z)
{
    size_t row;
    for (row = 0; row < 4u; ++row) {
        matrix[row * 4u] *= x;
        matrix[row * 4u + 1u] *= y;
        matrix[row * 4u + 2u] *= z;
    }
}

static int32_t vc_truncate_i32(float value)
{
    if (!isfinite(value) || value >= 2147483648.0f || value < -2147483648.0f) {
        return INT32_MIN;
    }
    return (int32_t)truncf(value);
}

static int32_t vc_angle_units(
    const VcNflPlayerLocalPostprocessTables *tables, float first, float second)
{
    int32_t sign = -1;
    int32_t quadrant = 0x4000;
    float ratio;
    float numerator;
    float denominator;
    int32_t result;

    if (second < 0.0f) {
        second = -second;
        sign = 0;
    }
    if (first < 0.0f) {
        first = -first;
        sign = ~sign;
        quadrant = -0x4000;
    }
    if (second > first) {
        ratio = first / second;
        quadrant += ((sign ^ 0x4000) - sign);
        sign = ~sign;
    }
    else {
        if (first == 0.0f) {
            return 0;
        }
        ratio = second / first;
    }
    numerator =
        (tables->angle_coefficients[5] * ratio +
         tables->angle_coefficients[4]) * ratio +
        tables->angle_coefficients[3];
    denominator =
        ((ratio * tables->angle_coefficients[2] +
          tables->angle_coefficients[1]) * ratio +
         tables->angle_coefficients[0]) * ratio + 1.0f;
    result = vc_truncate_i32(numerator / denominator + 0.5f);
    return ((result ^ sign) - sign) + quadrant;
}

static void vc_angle_lut_rotation(
    float output[16], const float axis[4], int32_t angle,
    const VcNflPlayerLocalPostprocessTables *tables)
{
    const uint32_t angle16 = (uint32_t)angle & UINT32_C(0xffff);
    const uint32_t cosine_angle = (angle16 + UINT32_C(0x4000)) & UINT32_C(0xffff);
    const size_t sine_index = (size_t)(angle16 >> 8u) * 2u;
    const size_t cosine_index = (size_t)(cosine_angle >> 8u) * 2u;
    const float sine =
        (float)angle16 * tables->angle_lut[sine_index + 1u] +
        tables->angle_lut[sine_index];
    const float cosine =
        (float)cosine_angle * tables->angle_lut[cosine_index + 1u] +
        tables->angle_lut[cosine_index];
    vc_axis_rotation(output, axis, sine, cosine);
}

static void vc_project_sine_cosine(
    const float matrix[16], const float axis[4],
    const VcNflPlayerLocalPostprocessTables *tables,
    float *sine_out, float *cosine_out)
{
    float perpendicular[4] = {-axis[1], axis[0], 0.0f, 0.0f};
    float transformed[4];
    float projected[4];
    float inverse_a;
    float inverse_b;
    float dot;
    float cosine;
    float sine;
    float orientation;

    vc_transform_xyz(transformed, matrix, perpendicular);
    dot = transformed[0] * axis[0] + transformed[1] * axis[1] +
        transformed[2] * axis[2] + transformed[3] * axis[3];
    projected[0] = transformed[0] - dot * axis[0];
    projected[1] = transformed[1] - dot * axis[1];
    projected[2] = transformed[2] - dot * axis[2];
    projected[3] = transformed[3] - dot * axis[3];
    inverse_a = 1.0f / sqrtf(
        perpendicular[0] * perpendicular[0] +
        perpendicular[1] * perpendicular[1]);
    inverse_b = 1.0f / sqrtf(
        projected[0] * projected[0] + projected[1] * projected[1] +
        projected[2] * projected[2] + projected[3] * projected[3]);
    cosine =
        (projected[0] * perpendicular[0] +
         projected[1] * perpendicular[1]) * inverse_a * inverse_b;
    if (cosine > 1.0f) {
        cosine = 1.0f;
    }
    else if (cosine <= tables->projection_lower_clamp) {
        cosine = -1.0f;
    }
    sine = sqrtf(1.0f - cosine * cosine);
    orientation =
        (projected[1] * perpendicular[0] -
         perpendicular[1] * projected[0]) * axis[2] +
        (projected[2] * perpendicular[1] - projected[1] * 0.0f) * axis[0] +
        (projected[0] * 0.0f - projected[2] * perpendicular[0]) * axis[1] +
        axis[3] * 0.0f;
    if (orientation < 0.0f) {
        sine = -sine;
    }
    *sine_out = sine;
    *cosine_out = cosine;
}

static void vc_basis_a(
    float output[16], const float second[4], const float primary[4])
{
    float cross[4];
    float normalized[4];
    vc_cross4(cross, primary, second);
    vc_normalize4(normalized, cross);
    output[0] = normalized[0];
    output[1] = normalized[1];
    output[2] = normalized[2];
    output[3] = 0.0f;
    output[4] = primary[0];
    output[5] = primary[1];
    output[6] = primary[2];
    output[7] = 0.0f;
    output[8] = normalized[1] * primary[2] - normalized[2] * primary[1];
    output[9] = normalized[2] * primary[0] - normalized[0] * primary[2];
    output[10] = normalized[0] * primary[1] - normalized[1] * primary[0];
    output[11] = 0.0f;
    output[12] = 0.0f;
    output[13] = 0.0f;
    output[14] = 0.0f;
    output[15] = 1.0f;
}

static void vc_basis_b(
    float output[16], const float second[4], const float primary[4])
{
    float cross[4];
    float normalized[4];
    vc_cross4(cross, primary, second);
    vc_normalize4(normalized, cross);
    output[0] = normalized[0];
    output[1] = primary[0];
    output[2] = normalized[1] * primary[2] - normalized[2] * primary[1];
    output[3] = 0.0f;
    output[4] = normalized[1];
    output[5] = primary[1];
    output[6] = normalized[2] * primary[0] - normalized[0] * primary[2];
    output[7] = 0.0f;
    output[8] = normalized[2];
    output[9] = primary[2];
    output[10] = normalized[0] * primary[1] - normalized[1] * primary[0];
    output[11] = 0.0f;
    output[12] = 0.0f;
    output[13] = 0.0f;
    output[14] = 0.0f;
    output[15] = 1.0f;
}

static void vc_align_ratio(
    float destination[16], const float value[4],
    const float seed[4], const float other[4])
{
    const float seed_length = vc_length4(seed);
    const float value_length = vc_length4(value);
    float seed_normalized[4];
    float value_normalized[4];
    float scratch[16];
    size_t lane;
    for (lane = 0; lane < 4u; ++lane) {
        seed_normalized[lane] = seed[lane] / seed_length;
        value_normalized[lane] = value[lane] / value_length;
    }
    vc_basis_b(destination, other, seed_normalized);
    vc_scale_columns(destination, 1.0f, value_length / seed_length, 1.0f);
    vc_basis_a(scratch, other, value_normalized);
    vc_matrix_multiply(destination, destination, scratch);
}

static void vc_align_vectors(
    float destination[16], const float seed[4], const float target[4])
{
    const float seed_length = vc_length4(seed);
    const float target_length = vc_length4(target);
    float seed_normalized[4];
    float target_normalized[4];
    float cross[4];
    float axis[4];
    float rotation[16];
    float cosine;
    float sine;
    size_t lane;
    for (lane = 0; lane < 4u; ++lane) {
        seed_normalized[lane] = seed[lane] / seed_length;
        target_normalized[lane] = target[lane] / target_length;
    }
    vc_axis_scale(destination, seed_normalized, target_length / seed_length);
    cosine =
        target_normalized[0] * seed_normalized[0] +
        target_normalized[1] * seed_normalized[1] +
        target_normalized[2] * seed_normalized[2] +
        target_normalized[3] * seed_normalized[3];
    vc_cross4(cross, seed_normalized, target_normalized);
    sine = vc_length4(cross);
    for (lane = 0; lane < 4u; ++lane) {
        axis[lane] = cross[lane] / sine;
    }
    vc_axis_rotation(rotation, axis, sine, cosine);
    vc_matrix_multiply(destination, destination, rotation);
}

static void vc_compose_nonuniform(
    float destination[16], const float value[4],
    const float seed[4], const float other[4],
    float x_scale, float y_scale, float z_scale)
{
    const float seed_length = vc_length4(seed);
    const float value_length = vc_length4(value);
    float seed_normalized[4];
    float value_normalized[4];
    float scratch[16];
    size_t lane;
    for (lane = 0; lane < 4u; ++lane) {
        seed_normalized[lane] = seed[lane] / seed_length;
        value_normalized[lane] = value[lane] / value_length;
    }
    vc_basis_b(destination, other, seed_normalized);
    vc_scale_columns(destination, x_scale, y_scale, z_scale);
    vc_basis_a(scratch, other, value_normalized);
    vc_matrix_multiply(destination, destination, scratch);
}

static void vc_add4(float value[4], const float addend[4])
{
    value[0] += addend[0];
    value[1] += addend[1];
    value[2] += addend[2];
    value[3] += addend[3];
}

static void vc_sub4(float value[4], const float subtrahend[4])
{
    value[0] -= subtrahend[0];
    value[1] -= subtrahend[1];
    value[2] -= subtrahend[2];
    value[3] -= subtrahend[3];
}

static float vc_dot4(const float left[4], const float right[4])
{
    return left[0] * right[0] + left[1] * right[1] +
        left[2] * right[2] + left[3] * right[3];
}

static int vc_tables_valid(const VcNflPlayerLocalPostprocessTables *tables)
{
    if (tables == NULL) {
        return 0;
    }
    return memcmp(
        tables->low_to_high, vc_title_low_to_high,
        sizeof(vc_title_low_to_high)) == 0;
}

VcNflPlayerLocalPostprocessStatus vc_nfl_player_local_postprocess_92140(
    const float skeleton_vectors[VC_NFL_PLAYER_LOW_MATRIX_COUNT][4],
    const VcNflPlayerLocalPostprocessTables *tables,
    VcNflPlayerLocalMatrices *matrices,
    VcNflPlayer92140TraceCallback observer,
    void *observer_user_data)
{
    float temporary[16];
    float vector[4];
    float vector2[4];
    float axis[4];
    float sine;
    float cosine;
    float angle;
    float left_leg_angle;
    float right_leg_angle;
    float left_forearm_angle;
    float right_forearm_angle;
    float blend;
    int32_t angle_units;
    size_t index;

    if (skeleton_vectors == NULL || matrices == NULL || tables == NULL) {
        return VC_NFL_PLAYER_LOCAL_POSTPROCESS_BAD_ARGUMENT;
    }
    if (!vc_tables_valid(tables)) {
        return VC_NFL_PLAYER_LOCAL_POSTPROCESS_BAD_TABLES;
    }

    for (index = 0; index < VC_NFL_PLAYER_LOW_MATRIX_COUNT; ++index) {
        const uint8_t high_index = tables->low_to_high[index];
        if (high_index != UINT8_C(0xff)) {
            memcpy(matrices->high[high_index], matrices->low[index],
                sizeof(matrices->high[high_index]));
        }
    }

    vc_trace(observer, observer_user_data, 1u, UINT32_C(0x000921c8));
    vc_matrix_multiply(matrices->high[37], matrices->high[37], matrices->low[16]);
    vc_trace(observer, observer_user_data, 2u, UINT32_C(0x000921dc));
    vc_matrix_multiply(matrices->high[51], matrices->high[51], matrices->low[21]);

    vc_trace(observer, observer_user_data, 3u, UINT32_C(0x000921f7));
    vc_project_sine_cosine(matrices->high[3], vc_constant(tables, 0x004efde0u), tables, &sine, &cosine);
    vc_trace(observer, observer_user_data, 4u, UINT32_C(0x00092206));
    angle = (float)vc_angle_units(tables, sine, cosine);
    vc_trace(observer, observer_user_data, 5u, UINT32_C(0x00092252));
    vc_axis_two_scale(matrices->high[6], skeleton_vectors[2],
        1.0f - angle * vc_c(tables, 0x004efe4cu),
        1.0f + angle * vc_c(tables, 0x004efe50u));

    vc_trace(observer, observer_user_data, 6u, UINT32_C(0x0009226d));
    vc_project_sine_cosine(matrices->high[15], vc_constant(tables, 0x004efdd0u), tables, &sine, &cosine);
    vc_trace(observer, observer_user_data, 7u, UINT32_C(0x0009227c));
    angle = (float)vc_angle_units(tables, sine, cosine);
    vc_trace(observer, observer_user_data, 8u, UINT32_C(0x000922cc));
    vc_axis_two_scale(matrices->high[18], skeleton_vectors[6],
        1.0f - angle * vc_c(tables, 0x004efe4cu),
        1.0f + angle * vc_c(tables, 0x004efe50u));

    vc_cross4(vector, skeleton_vectors[1], skeleton_vectors[2]);
    vc_trace(observer, observer_user_data, 9u, UINT32_C(0x00092335));
    vc_normalize4(axis, vector);
    vc_trace(observer, observer_user_data, 10u, UINT32_C(0x0009234f));
    vc_project_sine_cosine(matrices->high[2], axis, tables, &sine, &cosine);
    vc_trace(observer, observer_user_data, 11u, UINT32_C(0x0009235e));
    left_leg_angle = (float)vc_angle_units(tables, sine, cosine);
    vc_trace(observer, observer_user_data, 12u, UINT32_C(0x0009238b));
    angle_units = vc_truncate_i32(left_leg_angle * vc_c(tables, 0x004efe48u));
    vc_trace(observer, observer_user_data, 13u, UINT32_C(0x00092397));
    vc_angle_lut_rotation(matrices->high[5], axis, angle_units, tables);
    vc_trace(observer, observer_user_data, 14u, UINT32_C(0x000923be));
    vc_axis_scale(temporary, vc_constant(tables, 0x004efdc0u),
        1.0f - left_leg_angle * vc_c(tables, 0x004efe44u));
    vc_trace(observer, observer_user_data, 15u, UINT32_C(0x000923ca));
    vc_matrix_multiply(matrices->high[5], temporary, matrices->high[5]);
    vc_trace(observer, observer_user_data, 16u, UINT32_C(0x000923e3));
    angle_units = vc_truncate_i32(left_leg_angle * tables->angle_scale);
    vc_trace(observer, observer_user_data, 17u, UINT32_C(0x000923ef));
    vc_angle_lut_rotation(matrices->high[7], axis, angle_units, tables);
    vc_trace(observer, observer_user_data, 18u, UINT32_C(0x00092416));
    vc_axis_scale(temporary, vc_constant(tables, 0x004efdb0u),
        1.0f + left_leg_angle * vc_c(tables, 0x004efe50u));
    vc_trace(observer, observer_user_data, 19u, UINT32_C(0x00092422));
    vc_matrix_multiply(matrices->high[7], temporary, matrices->high[7]);

    vc_cross4(vector, skeleton_vectors[5], skeleton_vectors[6]);
    vc_trace(observer, observer_user_data, 20u, UINT32_C(0x00092490));
    vc_normalize4(axis, vector);
    vc_trace(observer, observer_user_data, 21u, UINT32_C(0x000924aa));
    vc_project_sine_cosine(matrices->high[14], axis, tables, &sine, &cosine);
    vc_trace(observer, observer_user_data, 22u, UINT32_C(0x000924b9));
    right_leg_angle = (float)vc_angle_units(tables, sine, cosine);
    vc_trace(observer, observer_user_data, 23u, UINT32_C(0x000924e6));
    angle_units = vc_truncate_i32(right_leg_angle * vc_c(tables, 0x004efe48u));
    vc_trace(observer, observer_user_data, 24u, UINT32_C(0x000924f2));
    vc_angle_lut_rotation(matrices->high[17], axis, angle_units, tables);
    vc_trace(observer, observer_user_data, 25u, UINT32_C(0x00092519));
    vc_axis_scale(temporary, vc_constant(tables, 0x004efda0u),
        1.0f - right_leg_angle * vc_c(tables, 0x004efe44u));
    vc_trace(observer, observer_user_data, 26u, UINT32_C(0x00092525));
    vc_matrix_multiply(matrices->high[17], temporary, matrices->high[17]);
    vc_trace(observer, observer_user_data, 27u, UINT32_C(0x0009253e));
    angle_units = vc_truncate_i32(right_leg_angle * tables->angle_scale);
    vc_trace(observer, observer_user_data, 28u, UINT32_C(0x0009254a));
    vc_angle_lut_rotation(matrices->high[19], axis, angle_units, tables);
    vc_trace(observer, observer_user_data, 29u, UINT32_C(0x00092571));
    vc_axis_scale(temporary, vc_constant(tables, 0x004efd90u),
        1.0f + right_leg_angle * vc_c(tables, 0x004efe50u));
    vc_trace(observer, observer_user_data, 30u, UINT32_C(0x0009257d));
    vc_matrix_multiply(matrices->high[19], temporary, matrices->high[19]);

    vc_trace(observer, observer_user_data, 31u, UINT32_C(0x00092592));
    vc_project_sine_cosine(matrices->high[1], skeleton_vectors[1], tables, &sine, &cosine);
    vc_trace(observer, observer_user_data, 32u, UINT32_C(0x000925ac));
    vc_axis_rotation(temporary, skeleton_vectors[1], -sine, cosine);
    vc_trace(observer, observer_user_data, 33u, UINT32_C(0x000925bf));
    vc_matrix_multiply(matrices->high[9], temporary, matrices->high[1]);
    vc_trace(observer, observer_user_data, 34u, UINT32_C(0x000925fe));
    angle = sqrtf((1.0f - cosine) * 0.5f);
    if (sine < 0.0f) {
        angle = -angle;
    }
    vc_trace(observer, observer_user_data, 35u, UINT32_C(0x00092624));
    cosine = sqrtf(cosine * 0.5f + 0.5f);
    vc_trace(observer, observer_user_data, 36u, UINT32_C(0x0009263f));
    vc_axis_rotation(matrices->high[10], skeleton_vectors[1], angle, cosine);

    vc_trace(observer, observer_user_data, 37u, UINT32_C(0x00092659));
    vc_project_sine_cosine(matrices->high[13], skeleton_vectors[5], tables, &sine, &cosine);
    vc_trace(observer, observer_user_data, 38u, UINT32_C(0x00092673));
    vc_axis_rotation(temporary, skeleton_vectors[5], -sine, cosine);
    vc_trace(observer, observer_user_data, 39u, UINT32_C(0x00092683));
    vc_matrix_multiply(matrices->high[21], temporary, matrices->high[13]);
    vc_trace(observer, observer_user_data, 40u, UINT32_C(0x000926c2));
    angle = sqrtf((1.0f - cosine) * 0.5f);
    if (sine < 0.0f) {
        angle = -angle;
    }
    vc_trace(observer, observer_user_data, 41u, UINT32_C(0x000926e8));
    cosine = sqrtf(cosine * 0.5f + 0.5f);
    vc_trace(observer, observer_user_data, 42u, UINT32_C(0x00092703));
    vc_axis_rotation(matrices->high[22], skeleton_vectors[5], angle, cosine);

    vc_trace(observer, observer_user_data, 43u, UINT32_C(0x00092717));
    vc_transform_xyz(vector, matrices->high[10], vc_constant(tables, 0x004efd80u));
    vc_add4(vector, vc_constant(tables, 0x004efd70u));
    vc_trace(observer, observer_user_data, 44u, UINT32_C(0x00092762));
    vc_transform_xyz(vector, matrices->high[9], vector);
    vc_add4(vector, vc_constant(tables, 0x004efd60u));
    vc_trace(observer, observer_user_data, 45u, UINT32_C(0x000927b4));
    vc_align_ratio(matrices->high[8], vector,
        vc_constant(tables, 0x004efd50u), vc_constant(tables, 0x004efd40u));
    vc_trace(observer, observer_user_data, 46u, UINT32_C(0x000927c8));
    vc_transform_xyz(vector, matrices->high[7], vc_constant(tables, 0x004efd30u));
    vc_add4(vector, vc_constant(tables, 0x004efd20u));
    vc_trace(observer, observer_user_data, 47u, UINT32_C(0x00092810));
    vc_transform_xyz(vector, matrices->high[1], vector);
    vc_add4(vector, vc_constant(tables, 0x004efd10u));
    vc_trace(observer, observer_user_data, 48u, UINT32_C(0x0009285c));
    vc_align_vectors(matrices->high[12], vc_constant(tables, 0x004efd00u), vector);

    vc_trace(observer, observer_user_data, 49u, UINT32_C(0x00092870));
    vc_transform_xyz(vector, matrices->high[22], vc_constant(tables, 0x004efcf0u));
    vc_add4(vector, vc_constant(tables, 0x004efce0u));
    vc_trace(observer, observer_user_data, 50u, UINT32_C(0x000928bb));
    vc_transform_xyz(vector, matrices->high[21], vector);
    vc_add4(vector, vc_constant(tables, 0x004efcd0u));
    vc_trace(observer, observer_user_data, 51u, UINT32_C(0x0009290d));
    vc_align_ratio(matrices->high[20], vector,
        vc_constant(tables, 0x004efcc0u), vc_constant(tables, 0x004efcb0u));
    vc_trace(observer, observer_user_data, 52u, UINT32_C(0x00092921));
    vc_transform_xyz(vector, matrices->high[19], vc_constant(tables, 0x004efca0u));
    vc_add4(vector, vc_constant(tables, 0x004efc90u));
    vc_trace(observer, observer_user_data, 53u, UINT32_C(0x0009296c));
    vc_transform_xyz(vector, matrices->high[13], vector);
    vc_add4(vector, vc_constant(tables, 0x004efc80u));
    vc_trace(observer, observer_user_data, 54u, UINT32_C(0x000929b8));
    vc_align_vectors(matrices->high[24], vc_constant(tables, 0x004efc70u), vector);

    vc_trace(observer, observer_user_data, 55u, UINT32_C(0x000929c9));
    vc_transform_xyz(vector, matrices->high[1], vc_constant(tables, 0x004efc60u));
    vc_add4(vector, vc_constant(tables, 0x004efc50u));
    vc_trace(observer, observer_user_data, 56u, UINT32_C(0x00092a15));
    vc_transform_xyz(vector2, matrices->high[13], vc_constant(tables, 0x004efc40u));
    vc_add4(vector2, vc_constant(tables, 0x004efc30u));
    vc_trace(observer, observer_user_data, 57u, UINT32_C(0x00092a79));
    vc_axis_scale(matrices->high[11], vc_constant(tables, 0x004efc20u),
        1.0f - (vector[1] * vc_c(tables, 0x004efe40u) + vc_c(tables, 0x004efe3cu)));
    vc_trace(observer, observer_user_data, 58u, UINT32_C(0x00092a92));
    angle_units = vc_truncate_i32(vector[1] * vc_c(tables, 0x004efe38u) + vc_c(tables, 0x004efe34u));
    vc_trace(observer, observer_user_data, 59u, UINT32_C(0x00092aa1));
    vc_angle_lut_rotation(temporary, vc_constant(tables, 0x004efc10u), angle_units, tables);
    vc_trace(observer, observer_user_data, 60u, UINT32_C(0x00092aaf));
    vc_matrix_multiply(matrices->high[11], matrices->high[11], temporary);
    vc_trace(observer, observer_user_data, 61u, UINT32_C(0x00092adb));
    vc_axis_scale(matrices->high[61], vc_constant(tables, 0x004efc00u),
        1.0f - (vector[1] * vc_c(tables, 0x004efe30u) + vc_c(tables, 0x004efe2cu)));
    vc_trace(observer, observer_user_data, 62u, UINT32_C(0x00092af4));
    angle_units = vc_truncate_i32(vector[1] * vc_c(tables, 0x004efe28u) + vc_c(tables, 0x004efe24u));
    vc_trace(observer, observer_user_data, 63u, UINT32_C(0x00092b03));
    vc_angle_lut_rotation(temporary, vc_constant(tables, 0x004efbf0u), angle_units, tables);
    vc_trace(observer, observer_user_data, 64u, UINT32_C(0x00092b11));
    vc_matrix_multiply(matrices->high[61], matrices->high[61], temporary);
    vc_trace(observer, observer_user_data, 65u, UINT32_C(0x00092b3d));
    vc_axis_scale(matrices->high[23], vc_constant(tables, 0x004efbe0u),
        1.0f - (vector2[1] * vc_c(tables, 0x004efe40u) + vc_c(tables, 0x004efe3cu)));
    vc_trace(observer, observer_user_data, 66u, UINT32_C(0x00092b56));
    angle_units = vc_truncate_i32(vector2[1] * vc_c(tables, 0x004efe38u) + vc_c(tables, 0x004efe34u));
    vc_trace(observer, observer_user_data, 67u, UINT32_C(0x00092b65));
    vc_angle_lut_rotation(temporary, vc_constant(tables, 0x004efbd0u), angle_units, tables);
    vc_trace(observer, observer_user_data, 68u, UINT32_C(0x00092b73));
    vc_matrix_multiply(matrices->high[23], matrices->high[23], temporary);
    vc_trace(observer, observer_user_data, 69u, UINT32_C(0x00092b9f));
    vc_axis_scale(matrices->high[60], vc_constant(tables, 0x004efbc0u),
        1.0f - (vector2[1] * vc_c(tables, 0x004efe30u) + vc_c(tables, 0x004efe2cu)));
    vc_trace(observer, observer_user_data, 70u, UINT32_C(0x00092bb8));
    angle_units = vc_truncate_i32(vector2[1] * vc_c(tables, 0x004efe28u) + vc_c(tables, 0x004efe24u));
    vc_trace(observer, observer_user_data, 71u, UINT32_C(0x00092bc7));
    vc_angle_lut_rotation(temporary, vc_constant(tables, 0x004efbb0u), angle_units, tables);
    vc_trace(observer, observer_user_data, 72u, UINT32_C(0x00092bd5));
    vc_matrix_multiply(matrices->high[60], matrices->high[60], temporary);

    vc_trace(observer, observer_user_data, 73u, UINT32_C(0x00092bea));
    vc_basis_b(matrices->high[25], vc_constant(tables, 0x004efb90u), vc_constant(tables, 0x004efba0u));
    vc_trace(observer, observer_user_data, 74u, UINT32_C(0x00092c1e));
    vc_scale_columns(matrices->high[25], 1.0f,
        1.0f - (vector[1] + vc_c(tables, 0x004efe20u) + vector2[1]) * vc_c(tables, 0x004efe40u), 1.0f);
    vector[0] += vector2[0];
    vector[1] += vector2[1];
    vector[2] += vector2[2];
    vector[3] += vector2[3];
    vc_trace(observer, observer_user_data, 75u, UINT32_C(0x00092c5b));
    vc_normalize4(vector2, vector);
    vc_trace(observer, observer_user_data, 76u, UINT32_C(0x00092c6e));
    vc_basis_a(temporary, vc_constant(tables, 0x004efb80u), vector2);
    vc_trace(observer, observer_user_data, 77u, UINT32_C(0x00092c80));
    vc_matrix_multiply(matrices->high[25], matrices->high[25], temporary);

    vc_trace(observer, observer_user_data, 78u, UINT32_C(0x00092ca0));
    vc_project_sine_cosine(matrices->high[37], skeleton_vectors[15], tables, &sine, &cosine);
    vc_trace(observer, observer_user_data, 79u, UINT32_C(0x00092cbe));
    cosine = sqrtf(cosine * 0.5f + 0.5f);
    vc_trace(observer, observer_user_data, 80u, UINT32_C(0x00092d01));
    sine = sqrtf((1.0f - cosine) * 0.5f) * (sine < 0.0f ? -1.0f : 1.0f);
    vc_trace(observer, observer_user_data, 81u, UINT32_C(0x00092d27));
    cosine = sqrtf(cosine * 0.5f + 0.5f);
    vc_trace(observer, observer_user_data, 82u, UINT32_C(0x00092d3a));
    left_forearm_angle = (float)vc_angle_units(tables, sine, cosine);
    vc_trace(observer, observer_user_data, 83u, UINT32_C(0x00092d67));
    vc_axis_rotation(matrices->high[33], skeleton_vectors[15], sine, cosine);
    memcpy(matrices->high[34], matrices->high[33], sizeof(matrices->high[34]));
    memcpy(matrices->high[35], matrices->high[33], sizeof(matrices->high[35]));
    memcpy(matrices->high[36], matrices->high[33], sizeof(matrices->high[36]));

    vc_trace(observer, observer_user_data, 84u, UINT32_C(0x00092df3));
    vc_project_sine_cosine(matrices->high[51], skeleton_vectors[20], tables, &sine, &cosine);
    vc_trace(observer, observer_user_data, 85u, UINT32_C(0x00092e11));
    cosine = sqrtf(cosine * 0.5f + 0.5f);
    vc_trace(observer, observer_user_data, 86u, UINT32_C(0x00092e54));
    sine = sqrtf((1.0f - cosine) * 0.5f) * (sine < 0.0f ? -1.0f : 1.0f);
    vc_trace(observer, observer_user_data, 87u, UINT32_C(0x00092e7a));
    cosine = sqrtf(cosine * 0.5f + 0.5f);
    vc_trace(observer, observer_user_data, 88u, UINT32_C(0x00092e8d));
    right_forearm_angle = (float)vc_angle_units(tables, sine, cosine);
    vc_trace(observer, observer_user_data, 89u, UINT32_C(0x00092eb8));
    vc_axis_rotation(matrices->high[47], skeleton_vectors[20], sine, cosine);
    memcpy(matrices->high[48], matrices->high[47], sizeof(matrices->high[48]));
    memcpy(matrices->high[49], matrices->high[47], sizeof(matrices->high[49]));
    memcpy(matrices->high[50], matrices->high[47], sizeof(matrices->high[50]));

    vc_trace(observer, observer_user_data, 90u, UINT32_C(0x00092f33));
    vc_transform_xyz(vector, matrices->high[33], vc_constant(tables, 0x004efb70u));
    vc_add4(vector, vc_constant(tables, 0x004efb60u));
    vc_trace(observer, observer_user_data, 91u, UINT32_C(0x00092f7e));
    vc_transform_xyz(vector, matrices->high[32], vector);
    vc_add4(vector, vc_constant(tables, 0x004efb50u));
    vc_trace(observer, observer_user_data, 92u, UINT32_C(0x00092fca));
    vc_align_vectors(matrices->high[42], vc_constant(tables, 0x004efb40u), vector);
    vc_trace(observer, observer_user_data, 93u, UINT32_C(0x00092fde));
    vc_transform_xyz(vector, matrices->high[33], vc_constant(tables, 0x004efb30u));
    vc_add4(vector, vc_constant(tables, 0x004efb20u));
    vc_trace(observer, observer_user_data, 94u, UINT32_C(0x00093029));
    vc_transform_xyz(vector, matrices->high[32], vector);
    vc_add4(vector, vc_constant(tables, 0x004efb10u));
    vc_trace(observer, observer_user_data, 95u, UINT32_C(0x00093075));
    vc_align_vectors(matrices->high[40], vc_constant(tables, 0x004efb00u), vector);
    vc_trace(observer, observer_user_data, 96u, UINT32_C(0x00093089));
    vc_transform_xyz(vector, matrices->high[47], vc_constant(tables, 0x004efaf0u));
    vc_add4(vector, vc_constant(tables, 0x004efae0u));
    vc_trace(observer, observer_user_data, 97u, UINT32_C(0x000930d4));
    vc_transform_xyz(vector, matrices->high[46], vector);
    vc_add4(vector, vc_constant(tables, 0x004efad0u));
    vc_trace(observer, observer_user_data, 98u, UINT32_C(0x00093120));
    vc_align_vectors(matrices->high[55], vc_constant(tables, 0x004efac0u), vector);
    vc_trace(observer, observer_user_data, 99u, UINT32_C(0x00093134));
    vc_transform_xyz(vector, matrices->high[47], vc_constant(tables, 0x004efab0u));
    vc_add4(vector, vc_constant(tables, 0x004efaa0u));
    vc_trace(observer, observer_user_data, 100u, UINT32_C(0x0009317f));
    vc_transform_xyz(vector, matrices->high[46], vector);
    vc_add4(vector, vc_constant(tables, 0x004efa90u));
    vc_trace(observer, observer_user_data, 101u, UINT32_C(0x000931cb));
    vc_align_vectors(matrices->high[54], vc_constant(tables, 0x004efa80u), vector);

    vc_trace(observer, observer_user_data, 102u, UINT32_C(0x000931df));
    vc_transform_xyz(vector, matrices->high[32], vc_constant(tables, 0x004efa70u));
    vc_add4(vector, vc_constant(tables, 0x004efa60u));
    vc_sub4(vector, vc_constant(tables, 0x004efa50u));
    angle = vc_dot4(vector, vc_constant(tables, 0x004efa40u)) * vc_c(tables, 0x004efe1cu);
    vc_trace(observer, observer_user_data, 103u, UINT32_C(0x0009329c));
    vc_axis_scale(matrices->high[41], vc_constant(tables, 0x004efa30u), angle);
    vc_trace(observer, observer_user_data, 104u, UINT32_C(0x000932b0));
    vc_transform_xyz(vector, matrices->high[46], vc_constant(tables, 0x004efa20u));
    vc_add4(vector, vc_constant(tables, 0x004efa10u));
    vc_sub4(vector, vc_constant(tables, 0x004efa00u));
    angle = vc_dot4(vector, vc_constant(tables, 0x004ef9f0u)) * vc_c(tables, 0x004efe18u);
    vc_trace(observer, observer_user_data, 105u, UINT32_C(0x0009336d));
    vc_axis_scale(matrices->high[53], vc_constant(tables, 0x004ef9e0u), angle);

    vc_cross4(vector, skeleton_vectors[14], skeleton_vectors[15]);
    vc_trace(observer, observer_user_data, 106u, UINT32_C(0x000933f0));
    vc_normalize4(axis, vector);
    vc_trace(observer, observer_user_data, 107u, UINT32_C(0x0009340a));
    vc_project_sine_cosine(matrices->high[32], axis, tables, &sine, &cosine);
    vc_trace(observer, observer_user_data, 108u, UINT32_C(0x00093419));
    angle = (float)vc_angle_units(tables, sine, cosine);
    vc_trace(observer, observer_user_data, 109u, UINT32_C(0x00093452));
    angle_units = vc_truncate_i32(angle * vc_c(tables, 0x004efe14u) + left_forearm_angle * tables->blend_scale);
    vc_trace(observer, observer_user_data, 110u, UINT32_C(0x0009345d));
    vc_angle_lut_rotation(matrices->high[38], vc_constant(tables, 0x004ef9d0u), angle_units, tables);
    vc_trace(observer, observer_user_data, 111u, UINT32_C(0x00093483));
    vc_axis_scale(matrices->high[39], vc_constant(tables, 0x004ef9c0u),
        1.0f - angle * vc_c(tables, 0x004efe10u));
    vc_trace(observer, observer_user_data, 112u, UINT32_C(0x000934a2));
    angle_units = vc_truncate_i32(angle * vc_c(tables, 0x004efe08u) + left_forearm_angle * vc_c(tables, 0x004efe0cu));
    vc_trace(observer, observer_user_data, 113u, UINT32_C(0x000934b1));
    vc_angle_lut_rotation(temporary, vc_constant(tables, 0x004ef9b0u), angle_units, tables);
    vc_trace(observer, observer_user_data, 114u, UINT32_C(0x000934bf));
    vc_matrix_multiply(matrices->high[39], matrices->high[39], temporary);
    vc_trace(observer, observer_user_data, 115u, UINT32_C(0x000934d3));
    vc_transform_xyz(vector, matrices->high[38], vc_constant(tables, 0x004ef9a0u));
    vc_add4(vector, vc_constant(tables, 0x004ef990u));
    vc_sub4(vector, vc_constant(tables, 0x004ef980u));
    blend = angle * vc_c(tables, 0x004efe00u) + left_forearm_angle * vc_c(tables, 0x004efe04u);
    vc_trace(observer, observer_user_data, 116u, UINT32_C(0x000935af));
    vc_compose_nonuniform(matrices->high[43], vector,
        vc_constant(tables, 0x004ef970u), vc_constant(tables, 0x004ef960u),
        blend * tables->blend_scale + 1.0f, 1.0f - blend * 0.5f, blend + 1.0f);

    vc_cross4(vector, skeleton_vectors[19], skeleton_vectors[20]);
    vc_trace(observer, observer_user_data, 117u, UINT32_C(0x0009362b));
    vc_normalize4(axis, vector);
    vc_trace(observer, observer_user_data, 118u, UINT32_C(0x00093645));
    vc_project_sine_cosine(matrices->high[46], axis, tables, &sine, &cosine);
    vc_trace(observer, observer_user_data, 119u, UINT32_C(0x00093654));
    angle = (float)vc_angle_units(tables, sine, cosine);
    vc_trace(observer, observer_user_data, 120u, UINT32_C(0x0009368d));
    angle_units = vc_truncate_i32(angle * vc_c(tables, 0x004efe14u) + right_forearm_angle * tables->blend_scale);
    vc_trace(observer, observer_user_data, 121u, UINT32_C(0x0009369a));
    vc_angle_lut_rotation(matrices->high[56], vc_constant(tables, 0x004ef950u), angle_units, tables);
    vc_trace(observer, observer_user_data, 122u, UINT32_C(0x000936c0));
    vc_axis_scale(matrices->high[57], vc_constant(tables, 0x004ef940u),
        1.0f - angle * vc_c(tables, 0x004efe10u));
    vc_trace(observer, observer_user_data, 123u, UINT32_C(0x000936df));
    angle_units = vc_truncate_i32(angle * vc_c(tables, 0x004efe08u) + right_forearm_angle * vc_c(tables, 0x004efe0cu));
    vc_trace(observer, observer_user_data, 124u, UINT32_C(0x000936ee));
    vc_angle_lut_rotation(temporary, vc_constant(tables, 0x004ef930u), angle_units, tables);
    vc_trace(observer, observer_user_data, 125u, UINT32_C(0x000936fc));
    vc_matrix_multiply(matrices->high[57], matrices->high[57], temporary);
    vc_trace(observer, observer_user_data, 126u, UINT32_C(0x0009370c));
    vc_transform_xyz(vector, matrices->high[56], vc_constant(tables, 0x004ef920u));
    vc_add4(vector, vc_constant(tables, 0x004ef910u));
    vc_sub4(vector, vc_constant(tables, 0x004ef900u));
    blend = angle * vc_c(tables, 0x004efe44u) + right_forearm_angle * vc_c(tables, 0x004efe04u);
    vc_trace(observer, observer_user_data, 127u, UINT32_C(0x000937e8));
    vc_compose_nonuniform(matrices->high[52], vector,
        vc_constant(tables, 0x004ef8f0u), vc_constant(tables, 0x004ef8e0u),
        blend * tables->blend_scale + 1.0f, 1.0f - blend * 0.5f, blend + 1.0f);

    return VC_NFL_PLAYER_LOCAL_POSTPROCESS_OK;
}

const char *vc_nfl_player_local_postprocess_status_name(
    VcNflPlayerLocalPostprocessStatus status)
{
    switch (status) {
    case VC_NFL_PLAYER_LOCAL_POSTPROCESS_OK:
        return "ok";
    case VC_NFL_PLAYER_LOCAL_POSTPROCESS_BAD_ARGUMENT:
        return "bad_argument";
    case VC_NFL_PLAYER_LOCAL_POSTPROCESS_BAD_TABLES:
        return "bad_tables";
    default:
        return "unknown";
    }
}

const char *vc_nfl_player_low_matrix_name(size_t index)
{
    return index < VC_NFL_PLAYER_LOW_MATRIX_COUNT ? vc_low_names[index] : NULL;
}

const char *vc_nfl_player_high_matrix_name(size_t index)
{
    return index < VC_NFL_PLAYER_HIGH_MATRIX_COUNT ? vc_high_names[index] : NULL;
}

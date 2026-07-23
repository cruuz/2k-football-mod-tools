#include "recovered/nfl2k5/quaternion_interpolation.h"

#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

typedef struct FixedSineEntry {
    uint32_t base_bits;
    uint32_t slope_bits;
} FixedSineEntry;

static const FixedSineEntry fixed_sine_table[256] = {
#include "quaternion_interpolation_table.inc"
};

static float float_from_bits(uint32_t bits)
{
    float value = 0.0f;
    memcpy(&value, &bits, sizeof(value));
    return value;
}

static long double fixed_sine(uint16_t angle)
{
    const FixedSineEntry *entry = &fixed_sine_table[(size_t)(angle >> 8)];
    const long double base = (long double)float_from_bits(entry->base_bits);
    const long double slope = (long double)float_from_bits(entry->slope_bits);
    return (long double)angle * slope + base;
}

static int32_t fixed_angle_units(float value)
{
    if (value < -1.0f) {
        return INT32_C(0x8000);
    }
    if (value > 1.0f) {
        return 0;
    }

    const bool negative = value < 0.0f;
    long double work = (long double)(negative ? -value : value);
    const bool transformed = work > 0.5L;
    if (transformed) {
        /* 0x00020C47..0x00020C5B stores the radicand as f32 and calls an
           SSE SQRTSS leaf before resuming x87 evaluation. */
        volatile float radicand = (float)((1.0L - work) * 0.5L);
        work = (long double)sqrtf(radicand);
    }

    const long double denominator_constant_0 =
        (long double)float_from_bits(UINT32_C(0x3F65AE43));
    const long double denominator_constant_1 =
        (long double)float_from_bits(UINT32_C(0x3E23B485));
    const long double denominator_constant_2 =
        (long double)float_from_bits(UINT32_C(0x3DFD9DFB));
    const long double numerator_constant_0 =
        (long double)float_from_bits(UINT32_C(0x3B514270));
    const long double numerator_constant_1 =
        (long double)float_from_bits(UINT32_C(0x4622F7E2));
    const long double numerator_constant_2 =
        (long double)float_from_bits(UINT32_C(0xC612150C));

    const long double numerator =
        (numerator_constant_2 * work + numerator_constant_1) * work +
        numerator_constant_0;
    const long double denominator =
        ((work * denominator_constant_2 - denominator_constant_1) * work -
         denominator_constant_0) *
            work +
        1.0L;
    const long double approximation = numerator / denominator;
    long double angle = transformed ? approximation + approximation :
                                      16384.0L - approximation;
    if (negative) {
        angle = 32768.0L - angle;
    }

    /* 0x000213F4..0x00021403 adds 0.5, stores f32, then CVTTSS2SI. */
    volatile float stored = (float)(angle + 0.5L);
    return (int32_t)truncf(stored);
}

static int32_t rounded_step(int32_t theta_units, float t)
{
    const long double product = (long double)theta_units * (long double)t;
    if (!isfinite(product)) {
        return INT32_MIN;
    }
    const long double adjusted =
        product >= 0.0L ? product + 0.5L : product - 0.5L;
    volatile float stored = (float)adjusted;
    if (!isfinite(stored) || stored >= 2147483648.0f ||
        stored < -2147483648.0f) {
        return INT32_MIN;
    }
    return (int32_t)truncf(stored);
}

VcNflQuaternionInterpolationStatus
vc_nfl_quaternion_interpolate_portable(
    float destination[4],
    const float left[4],
    const float right[4],
    float t,
    VcNflQuaternionInterpolationInfo *info)
{
    if (destination == NULL || left == NULL || right == NULL) {
        return VC_NFL_QUATERNION_INTERPOLATION_BAD_ARGUMENT;
    }

    long double dot = (long double)left[0] * (long double)right[0];
    dot += (long double)left[1] * (long double)right[1];
    dot += (long double)left[2] * (long double)right[2];
    dot += (long double)left[3] * (long double)right[3];
    const bool negate_right = dot < 0.0L;
    const long double absolute_dot = negate_right ? -dot : dot;
    volatile float stored_absolute_dot = (float)absolute_dot;

    VcNflQuaternionInterpolationBranch branch;
    int32_t theta_units = -1;
    int32_t step_units = -1;
    long double left_weight;
    long double right_weight;
    const long double threshold =
        (long double)float_from_bits(UINT32_C(0x3F7FF2E5));

    /* The x87 unordered comparison also reaches the linear target. */
    if (!isfinite(absolute_dot) || absolute_dot > threshold) {
        branch = VC_NFL_QUATERNION_INTERPOLATION_LINEAR;
        left_weight = 1.0L - (long double)t;
        right_weight = (long double)t;
    } else {
        branch = VC_NFL_QUATERNION_INTERPOLATION_FIXED_SLERP;
        theta_units = fixed_angle_units(stored_absolute_dot);
        step_units = rounded_step(theta_units, t);
        const long double inverse_denominator =
            1.0L / fixed_sine((uint16_t)(uint32_t)theta_units);
        left_weight =
            fixed_sine((uint16_t)((uint32_t)theta_units -
                                  (uint32_t)step_units)) *
            inverse_denominator;
        right_weight = fixed_sine((uint16_t)(uint32_t)step_units) *
                       inverse_denominator;
    }
    if (negate_right) {
        right_weight = -right_weight;
    }

    for (size_t lane = 0; lane < 4U; ++lane) {
        const long double blended =
            right_weight * (long double)right[lane] +
            left_weight * (long double)left[lane];
        destination[lane] = (float)blended;
    }

    if (info != NULL) {
        info->branch = branch;
        info->shortest_path_negated = negate_right;
        info->theta_units = theta_units;
        info->step_units = step_units;
        info->left_weight = (float)left_weight;
        info->right_weight = (float)right_weight;
    }
    return VC_NFL_QUATERNION_INTERPOLATION_OK;
}

const char *vc_nfl_quaternion_interpolation_status_name(
    VcNflQuaternionInterpolationStatus status)
{
    switch (status) {
    case VC_NFL_QUATERNION_INTERPOLATION_OK: return "ok";
    case VC_NFL_QUATERNION_INTERPOLATION_BAD_ARGUMENT: return "bad-argument";
    default: return "unknown";
    }
}

bool vc_nfl_quaternion_interpolation_is_xbox_x87_bit_exact(void)
{
    return false;
}

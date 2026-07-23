#include "recovered/nfl2k5/quaternion_interpolation.h"

#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;

static void expect_true(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "NFL quaternion interpolation: %s\n", message);
        ++failures;
    }
}

static void expect_near(float actual, float expected, float tolerance,
                        const char *message)
{
    if (!isfinite(actual) || fabsf(actual - expected) > tolerance) {
        fprintf(stderr,
                "NFL quaternion interpolation: %s (%.9g != %.9g)\n",
                message, actual, expected);
        ++failures;
    }
}

static void expect_lanes(const float actual[4], const float expected[4],
                         float tolerance, const char *message)
{
    for (size_t lane = 0; lane < 4U; ++lane) {
        if (!isfinite(actual[lane]) ||
            fabsf(actual[lane] - expected[lane]) > tolerance) {
            fprintf(stderr,
                    "NFL quaternion interpolation: %s lane %zu "
                    "(%.9g != %.9g)\n",
                    message, lane, actual[lane], expected[lane]);
            ++failures;
        }
    }
}

static void linear_and_shortest_path_tests(void)
{
    static const float identity[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    static const float antipodal[4] = {-1.0f, 0.0f, 0.0f, 0.0f};
    float output[4] = {0.0f};
    VcNflQuaternionInterpolationInfo info;

    expect_true(vc_nfl_quaternion_interpolate_portable(
                    output, identity, identity, 0.37f, &info) ==
                    VC_NFL_QUATERNION_INTERPOLATION_OK,
                "identity interpolation failed");
    expect_lanes(output, identity, 0.0f, "identity output mismatch");
    expect_true(info.branch == VC_NFL_QUATERNION_INTERPOLATION_LINEAR &&
                    !info.shortest_path_negated && info.theta_units == -1 &&
                    info.step_units == -1,
                "identity did not take the strict linear fallback");

    expect_true(vc_nfl_quaternion_interpolate_portable(
                    output, identity, antipodal, 0.37f, &info) ==
                    VC_NFL_QUATERNION_INTERPOLATION_OK,
                "antipodal interpolation failed");
    expect_lanes(output, identity, 0.0f, "antipodal shortest path mismatch");
    expect_true(info.branch == VC_NFL_QUATERNION_INTERPOLATION_LINEAR &&
                    info.shortest_path_negated,
                "antipodal input did not negate only the right weight");
    expect_near(info.left_weight, 0.629999995f, 0.0000001f,
                "linear left weight mismatch");
    expect_near(info.right_weight, -0.370000005f, 0.0000001f,
                "linear negated right weight mismatch");
}

static void fixed_branch_tests(void)
{
    static const float left[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    static const float right[4] = {0.0f, 1.0f, 0.0f, 0.0f};
    static const float half_expected[4] = {
        0.707107127f, 0.707107127f, 0.0f, 0.0f,
    };
    static const float negative_expected[4] = {
        0.923879385f, -0.382683039f, 0.0f, 0.0f,
    };
    static const float high_expected[4] = {
        -0.382683039f, 0.923879385f, 0.0f, 0.0f,
    };
    float output[4] = {0.0f};
    VcNflQuaternionInterpolationInfo info;

    vc_nfl_quaternion_interpolate_portable(output, left, right, 0.5f, &info);
    expect_lanes(output, half_expected, 0.0000005f,
                 "orthogonal half interpolation mismatch");
    expect_true(info.branch == VC_NFL_QUATERNION_INTERPOLATION_FIXED_SLERP &&
                    info.theta_units == 16384 && info.step_units == 8192,
                "orthogonal fixed-angle metadata mismatch");

    vc_nfl_quaternion_interpolate_portable(output, left, right, -0.25f, &info);
    expect_lanes(output, negative_expected, 0.0000005f,
                 "negative extrapolation mismatch");
    expect_true(info.step_units == -4096,
                "negative step did not round and wrap like the XBE");

    vc_nfl_quaternion_interpolate_portable(output, left, right, 1.25f, &info);
    expect_lanes(output, high_expected, 0.0000005f,
                 "high extrapolation mismatch");
    expect_true(info.step_units == 20480,
                "high extrapolation step mismatch");
}

static void threshold_and_alias_tests(void)
{
    static const float left[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    const float threshold = 0x1.ffe5cap-1f;
    const float above = nextafterf(threshold, INFINITY);
    float equal_right[4] = {
        threshold,
        sqrtf(1.0f - threshold * threshold),
        0.0f,
        0.0f,
    };
    float above_right[4] = {
        above,
        sqrtf(1.0f - above * above),
        0.0f,
        0.0f,
    };
    static const float equal_expected[4] = {
        0.999922574f, 0.0100469105f, 0.0f, 0.0f,
    };
    float output[4] = {0.0f};
    VcNflQuaternionInterpolationInfo info;

    vc_nfl_quaternion_interpolate_portable(
        output, left, equal_right, 0.5f, &info);
    expect_true(info.branch == VC_NFL_QUATERNION_INTERPOLATION_FIXED_SLERP &&
                    info.theta_units == 209 && info.step_units == 105,
                "threshold equality did not remain on the fixed branch");
    expect_lanes(output, equal_expected, 0.000001f,
                 "threshold equality output mismatch");

    vc_nfl_quaternion_interpolate_portable(
        output, left, above_right, 0.5f, &info);
    expect_true(info.branch == VC_NFL_QUATERNION_INTERPOLATION_LINEAR,
                "next float above threshold did not take linear fallback");

    float aliased[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    vc_nfl_quaternion_interpolate_portable(
        aliased, aliased, equal_right, 0.5f, NULL);
    expect_lanes(aliased, equal_expected, 0.000001f,
                 "destination==left alias mismatch");

    memcpy(aliased, equal_right, sizeof(aliased));
    vc_nfl_quaternion_interpolate_portable(
        aliased, left, aliased, 0.5f, NULL);
    expect_lanes(aliased, equal_expected, 0.000001f,
                 "destination==right alias mismatch");
}

static void failure_tests(void)
{
    static const float identity[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    float output[4] = {0.0f};
    expect_true(vc_nfl_quaternion_interpolate_portable(
                    NULL, identity, identity, 0.0f, NULL) ==
                    VC_NFL_QUATERNION_INTERPOLATION_BAD_ARGUMENT,
                "null destination was accepted");
    expect_true(vc_nfl_quaternion_interpolate_portable(
                    output, NULL, identity, 0.0f, NULL) ==
                    VC_NFL_QUATERNION_INTERPOLATION_BAD_ARGUMENT,
                "null left input was accepted");
    expect_true(vc_nfl_quaternion_interpolate_portable(
                    output, identity, NULL, 0.0f, NULL) ==
                    VC_NFL_QUATERNION_INTERPOLATION_BAD_ARGUMENT,
                "null right input was accepted");
    expect_true(strcmp(vc_nfl_quaternion_interpolation_status_name(
                           VC_NFL_QUATERNION_INTERPOLATION_BAD_ARGUMENT),
                       "bad-argument") == 0,
                "status name mismatch");
    expect_true(!vc_nfl_quaternion_interpolation_is_xbox_x87_bit_exact(),
                "portable implementation falsely claims XBE x87 bit identity");
}

int main(void)
{
    linear_and_shortest_path_tests();
    fixed_branch_tests();
    threshold_and_alias_tests();
    failure_tests();
    if (failures != 0) {
        fprintf(stderr,
                "NFL_QUATERNION_INTERPOLATION_NATIVE_FAIL failures=%d\n",
                failures);
        return 1;
    }
    puts("NFL_QUATERNION_INTERPOLATION_NATIVE_PASS vectors=9 callers=7");
    return 0;
}

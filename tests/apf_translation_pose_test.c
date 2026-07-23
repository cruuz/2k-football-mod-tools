#include "recovered/apf2k8/translation_pose.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;

static uint32_t float_bits(float value)
{
    uint32_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static void expect_true(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "APF translation pose: %s\n", message);
        ++failures;
    }
}

static void expect_near(float actual, float expected, float tolerance,
                        const char *message)
{
    if (!isfinite(actual) || fabsf(actual - expected) > tolerance) {
        fprintf(stderr, "APF translation pose: %s (%.9g != %.9g)\n",
                message, actual, expected);
        ++failures;
    }
}

static void shipped_vector_test(void)
{
    static const uint8_t encoded[8] = {
        0x0F, 0xFB, 0x3C, 0xFF, 0xD4, 0x50, 0x04, 0x3B,
    };
    VcApfMode1Translation value;
    expect_true(vc_apf_mode1_translation_decode_be(encoded, &value) ==
                    VC_APF_PACKED_POSE_OK,
                "shipped unit did not decode");
    expect_true(value.packed_components[0] == 1083 &&
                    value.packed_components[1] == -699 &&
                    value.packed_components[2] == -1220,
                "signed component extraction mismatch");
    expect_near(value.lanes[0], 1.0576171875f, 0.0f,
                "lane 0 scale mismatch");
    expect_near(value.lanes[1], -0.6826171875f, 0.0f,
                "lane 1 scale mismatch");
    expect_near(value.lanes[2], -1.19140625f, 0.0f,
                "lane 2 scale mismatch");
    expect_true(float_bits(value.lanes[3]) == UINT32_C(0),
                "lane 3 is not positive zero");

    const uint32_t before[4] = {
        float_bits(value.lanes[0]), float_bits(value.lanes[1]),
        float_bits(value.lanes[2]), float_bits(value.lanes[3]),
    };
    vc_apf_mode1_translation_apply_mirror(&value);
    expect_true(float_bits(value.lanes[0]) ==
                    (before[0] ^ UINT32_C(0x80000000)),
                "mirror did not flip lane 0");
    expect_true(float_bits(value.lanes[1]) == before[1] &&
                    float_bits(value.lanes[2]) == before[2] &&
                    float_bits(value.lanes[3]) == before[3],
                "mirror changed lanes 1 through 3");
}

static void interpolation_test(void)
{
    static const uint8_t a[8] = {
        0x0F, 0xFB, 0x3C, 0xFF, 0xD4, 0x50, 0x04, 0x3B,
    };
    static const uint8_t b[8] = {
        0x0F, 0xFB, 0x41, 0xFF, 0xD5, 0x10, 0x04, 0x84,
    };
    VcApfMode1Translation value;
    expect_true(vc_apf_mode1_translation_lerp(a, b, 0.25f, false, &value) ==
                    VC_APF_PACKED_POSE_OK,
                "pair interpolation failed");
    expect_near(value.lanes[0], 1.075439453125f, 0.0f,
                "interpolated lane 0 mismatch");
    expect_near(value.lanes[1], -0.6796875f, 0.0f,
                "interpolated lane 1 mismatch");
    expect_near(value.lanes[2], -1.190185546875f, 0.0f,
                "interpolated lane 2 mismatch");
    expect_true(float_bits(value.lanes[3]) == UINT32_C(0),
                "interpolated lane 3 is not zero");
    expect_true(vc_apf_mode1_translation_lerp(a, b, 0.25f, true, &value) ==
                    VC_APF_PACKED_POSE_OK,
                "mirrored pair interpolation failed");
    expect_near(value.lanes[0], -1.075439453125f, 0.0f,
                "mirrored interpolated lane 0 mismatch");
}

static void failure_test(void)
{
    static const uint8_t zero[8] = {0};
    VcApfMode1Translation value;
    expect_true(vc_apf_mode1_translation_decode_be(NULL, &value) ==
                    VC_APF_PACKED_POSE_BAD_ARGUMENT,
                "null encoded input was accepted");
    expect_true(vc_apf_mode1_translation_decode_be(zero, NULL) ==
                    VC_APF_PACKED_POSE_BAD_ARGUMENT,
                "null decode output was accepted");
    expect_true(vc_apf_mode1_translation_lerp(zero, zero, 0.5f, false, NULL) ==
                    VC_APF_PACKED_POSE_BAD_ARGUMENT,
                "null lerp output was accepted");
    expect_true(!vc_apf_mode1_translation_lerp_is_xenon_bit_exact(),
                "portable interpolation falsely claims Xenon bit identity");
    vc_apf_mode1_translation_apply_mirror(NULL);
}

int main(void)
{
    shipped_vector_test();
    interpolation_test();
    failure_test();
    if (failures != 0) {
        fprintf(stderr, "APF_TRANSLATION_POSE_NATIVE_FAIL failures=%d\n",
                failures);
        return 1;
    }
    puts("APF_TRANSLATION_POSE_NATIVE_PASS vectors=2 mirror_lane=0");
    return 0;
}

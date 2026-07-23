#include "recovered/apf2k8/packed_pose.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;

static void expect_true(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "APF packed pose: %s\n", message);
        ++failures;
    }
}

static void expect_near(float actual, float expected, float tolerance,
                        const char *message)
{
    if (!isfinite(actual) || fabsf(actual - expected) > tolerance) {
        fprintf(stderr, "APF packed pose: %s (%.9g != %.9g)\n",
                message, actual, expected);
        ++failures;
    }
}

static uint32_t float_bits(float value)
{
    uint32_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static void selector_zero_tests(void)
{
    for (uint8_t selector = 0; selector < 16U; ++selector) {
        uint8_t encoded[8] = {0};
        encoded[0] = (uint8_t)(selector << 4);
        VcApfMode0Pose pose;
        expect_true(vc_apf_mode0_decode_be_portable(encoded, &pose) ==
                        VC_APF_PACKED_POSE_OK,
                    "zero selector vector did not decode");
        expect_true(pose.selector == selector, "selector was not retained");
        for (size_t lane = 0; lane < 4; ++lane) {
            const size_t missing_lane =
                (size_t)(3U - (uint8_t)(selector & 3U));
            const float expected = lane == missing_lane ? 1.0f : 0.0f;
            expect_true(float_bits(pose.lanes[lane]) == float_bits(expected),
                        "zero selector rotation mismatch");
        }
        expect_true(float_bits(pose.ideal_radicand) ==
                        float_bits(1.0f),
                    "zero vector radicand mismatch");
    }
}

static void corpus_vector_test(void)
{
    static const uint8_t encoded[8] = {
        0x35, 0xFE, 0x34, 0xAB, 0x9A, 0x94, 0xEB, 0x57,
    };
    VcApfMode0Pose pose;
    expect_true(vc_apf_mode0_decode_be_portable(encoded, &pose) ==
                    VC_APF_PACKED_POSE_OK,
                "maximum shipped vector did not decode");
    expect_true(pose.selector == 3U, "maximum vector selector mismatch");
    expect_true(pose.packed_components[0] == 322391 &&
                    pose.packed_components[1] == -345687 &&
                    pose.packed_components[2] == 392756,
                "maximum vector signed components mismatch");
    expect_near(pose.lanes[0], 0.538674055f, 0.000001f,
                "maximum vector reconstructed lane mismatch");
    expect_near(pose.lanes[1], 0.441968024f, 0.000001f,
                "maximum vector component 0 mismatch");
    expect_near(pose.lanes[2], -0.473904669f, 0.000001f,
                "maximum vector component 1 mismatch");
    expect_near(pose.lanes[3], 0.538431883f, 0.000001f,
                "maximum vector component 2 mismatch");
    expect_near(pose.ideal_radicand, 0.290169738f, 0.000001f,
                "maximum vector radicand mismatch");
    float norm = 0.0f;
    for (size_t lane = 0; lane < 4; ++lane) {
        norm += pose.lanes[lane] * pose.lanes[lane];
    }
    expect_near(norm, 1.0f, 0.000002f, "decoded pose is not unit length");

    const uint32_t before[4] = {
        float_bits(pose.lanes[0]), float_bits(pose.lanes[1]),
        float_bits(pose.lanes[2]), float_bits(pose.lanes[3]),
    };
    vc_apf_mode0_apply_mirror(&pose);
    expect_true(float_bits(pose.lanes[0]) == before[0] &&
                    float_bits(pose.lanes[1]) == before[1],
                "mirror changed lanes 0/1");
    expect_true(float_bits(pose.lanes[2]) ==
                        (before[2] ^ UINT32_C(0x80000000)) &&
                    float_bits(pose.lanes[3]) ==
                        (before[3] ^ UINT32_C(0x80000000)),
                "mirror did not XOR sign bits in lanes 2/3");
}

static void failure_tests(void)
{
    static const uint8_t negative_radicand[8] = {
        0x07, 0xFF, 0xFF, 0x7F, 0xFF, 0xF7, 0xFF, 0xFF,
    };
    VcApfMode0Pose pose = {.selector = 99U};
    expect_true(vc_apf_mode0_decode_be_portable(NULL, &pose) ==
                    VC_APF_PACKED_POSE_BAD_ARGUMENT,
                "null input was accepted");
    expect_true(vc_apf_mode0_decode_be_portable(negative_radicand, NULL) ==
                    VC_APF_PACKED_POSE_BAD_ARGUMENT,
                "null output was accepted");
    expect_true(vc_apf_mode0_decode_be_portable(negative_radicand, &pose) ==
                    VC_APF_PACKED_POSE_NEGATIVE_RADICAND,
                "negative radicand was accepted");
    expect_true(pose.selector == 99U,
                "failed decode modified the destination");
    expect_true(strcmp(vc_apf_packed_pose_status_name(
                           VC_APF_PACKED_POSE_NEGATIVE_RADICAND),
                       "negative-radicand") == 0,
                "status name mismatch");
    expect_true(!vc_apf_mode0_decoder_is_xenon_bit_exact(),
                "portable decoder falsely claims Xenon bit identity");
    vc_apf_mode0_apply_mirror(NULL);
}

int main(void)
{
    selector_zero_tests();
    corpus_vector_test();
    failure_tests();
    if (failures != 0) {
        fprintf(stderr, "APF_PACKED_POSE_NATIVE_FAIL failures=%d\n", failures);
        return 1;
    }
    puts("APF_PACKED_POSE_NATIVE_PASS vectors=17 mirror_lanes=2/3");
    return 0;
}

#include "recovered/nfl2k5/packed_pose.h"

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;

static void expect_true(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "NFL packed pose: %s\n", message);
        ++failures;
    }
}

static void expect_near(float actual, float expected, float tolerance,
                        const char *message)
{
    if (!isfinite(actual) || fabsf(actual - expected) > tolerance) {
        fprintf(stderr, "NFL packed pose: %s (%.9g != %.9g)\n",
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

static void omitted_component_tests(void)
{
    for (uint8_t omitted = 0; omitted < 4U; ++omitted) {
        const uint32_t word = ((uint32_t)omitted << 30) |
                              (UINT32_C(512) << 20) |
                              (UINT32_C(512) << 10) |
                              UINT32_C(512);
        const uint8_t encoded[4] = {
            (uint8_t)word,
            (uint8_t)(word >> 8),
            (uint8_t)(word >> 16),
            (uint8_t)(word >> 24),
        };
        VcNflPackedPose pose;
        expect_true(vc_nfl_packed_pose_decode_le_portable(encoded, &pose) ==
                        VC_NFL_PACKED_POSE_OK,
                    "zero stored-components vector did not decode");
        expect_true(pose.omitted_component == omitted,
                    "omitted component was not retained");
        for (size_t lane = 0; lane < 4; ++lane) {
            const float expected = lane == (size_t)omitted ? 1.0f : 0.0f;
            expect_true(float_bits(pose.lanes[lane]) == float_bits(expected),
                        "omitted-component placement mismatch");
        }
        expect_true(pose.packed_components[0] == 0 &&
                        pose.packed_components[1] == 0 &&
                        pose.packed_components[2] == 0,
                    "biased zero components were not decoded as zero");
        expect_true(float_bits(pose.ideal_radicand) == float_bits(1.0f),
                    "identity radicand mismatch");
    }
}

static void corpus_vector_test(void)
{
    /* Maximum three-square-sum main-stream word from r64cheerleader03. */
    static const uint8_t encoded[4] = {0x8F, 0xE0, 0x52, 0xF7};
    VcNflPackedPose pose;
    expect_true(vc_nfl_packed_pose_decode_le_portable(encoded, &pose) ==
                    VC_NFL_PACKED_POSE_OK,
                "maximum shipped vector did not decode");
    expect_true(pose.omitted_component == 3U,
                "maximum vector omitted component mismatch");
    expect_true(pose.packed_components[0] == 373 &&
                    pose.packed_components[1] == -328 &&
                    pose.packed_components[2] == -369,
                "maximum vector quantized components mismatch");
    expect_near(pose.lanes[0], 0.516146436f, 0.000001f,
                "maximum vector component 0 mismatch");
    expect_near(pose.lanes[1], -0.453876759f, 0.000001f,
                "maximum vector component 1 mismatch");
    expect_near(pose.lanes[2], -0.510611354f, 0.000001f,
                "maximum vector component 2 mismatch");
    expect_near(pose.lanes[3], 0.516589575f, 0.000001f,
                "maximum vector reconstructed component mismatch");
    expect_near(pose.ideal_radicand, 0.266864789f, 0.000001f,
                "maximum vector radicand mismatch");
    float norm = 0.0f;
    for (size_t lane = 0; lane < 4; ++lane) {
        norm += pose.lanes[lane] * pose.lanes[lane];
    }
    expect_near(norm, 1.0f, 0.000002f,
                "decoded pose is not unit length");

    const uint32_t before[4] = {
        float_bits(pose.lanes[0]), float_bits(pose.lanes[1]),
        float_bits(pose.lanes[2]), float_bits(pose.lanes[3]),
    };
    vc_nfl_packed_pose_apply_mirror(&pose);
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
    static const uint8_t negative_radicand[4] = {0, 0, 0, 0};
    VcNflPackedPose pose = {.omitted_component = 99U};
    expect_true(vc_nfl_packed_pose_decode_le_portable(NULL, &pose) ==
                    VC_NFL_PACKED_POSE_BAD_ARGUMENT,
                "null input was accepted");
    expect_true(vc_nfl_packed_pose_decode_le_portable(negative_radicand, NULL) ==
                    VC_NFL_PACKED_POSE_BAD_ARGUMENT,
                "null output was accepted");
    expect_true(vc_nfl_packed_pose_decode_le_portable(negative_radicand, &pose) ==
                    VC_NFL_PACKED_POSE_NEGATIVE_RADICAND,
                "negative radicand was accepted");
    expect_true(pose.omitted_component == 99U,
                "failed decode modified the destination");
    expect_true(strcmp(vc_nfl_packed_pose_status_name(
                           VC_NFL_PACKED_POSE_NEGATIVE_RADICAND),
                       "negative-radicand") == 0,
                "status name mismatch");
    expect_true(!vc_nfl_packed_pose_decoder_is_xbox_x87_bit_exact(),
                "portable decoder falsely claims original x87 bit identity");
    VcNflPackedPose poses[2];
    size_t failed_index = 88U;
    expect_true(vc_nfl_packed_pose_decode_many_le_portable(
                    negative_radicand, 1U, poses, &failed_index) ==
                    VC_NFL_PACKED_POSE_NEGATIVE_RADICAND &&
                    failed_index == 0U,
                "batch decoder did not report its first rejected record");
    expect_true(vc_nfl_packed_pose_decode_many_le_portable(
                    NULL, 1U, poses, &failed_index) ==
                    VC_NFL_PACKED_POSE_BAD_ARGUMENT,
                "batch decoder accepted a null input");
    vc_nfl_packed_pose_apply_mirror(NULL);
}

int main(void)
{
    omitted_component_tests();
    corpus_vector_test();
    failure_tests();
    if (failures != 0) {
        fprintf(stderr, "NFL_PACKED_POSE_NATIVE_FAIL failures=%d\n", failures);
        return 1;
    }
    puts("NFL_PACKED_POSE_NATIVE_PASS vectors=5 mirror_lanes=2/3");
    return 0;
}

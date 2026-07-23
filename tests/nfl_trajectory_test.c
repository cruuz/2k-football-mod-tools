#include "recovered/nfl2k5/trajectory.h"

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;

static void expect_true(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "NFL trajectory: %s\n", message);
        ++failures;
    }
}

static uint32_t float_bits(float value)
{
    uint32_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static void record_tests(void)
{
    static const uint8_t encoded[8] = {
        0xFF, 0x7F, 0x00, 0x80, 0xD2, 0x04, 0x2E, 0xFB,
    };
    VcNflTrajectorySample sample;
    expect_true(vc_nfl_trajectory_decode_record_le(encoded, 8U, &sample) ==
                    VC_NFL_TRAJECTORY_OK,
                "eight-byte record did not decode");
    expect_true(sample.packed_lanes[0] == 32767 &&
                    sample.packed_lanes[1] == -32768 &&
                    sample.packed_lanes[2] == 1234 &&
                    sample.packed_lanes[3] == -1234,
                "signed little-endian lanes differ");
    expect_true(float_bits(sample.lanes[0]) == float_bits(4095.875f) &&
                    float_bits(sample.lanes[1]) == float_bits(-4096.0f) &&
                    float_bits(sample.lanes[2]) == float_bits(154.25f),
                "one-eighth scale differs");
    expect_true(sample.has_yaw_like && sample.yaw_like == -9872,
                "fourth-lane shift differs");

    const uint32_t lane0 = float_bits(sample.lanes[0]);
    vc_nfl_trajectory_apply_mirror(&sample);
    expect_true(float_bits(sample.lanes[0]) ==
                    (lane0 ^ UINT32_C(0x80000000)) &&
                    sample.yaw_like == 9872,
                "mirror operation differs");

    expect_true(vc_nfl_trajectory_decode_record_le(encoded, 6U, &sample) ==
                    VC_NFL_TRAJECTORY_OK,
                "six-byte record did not decode");
    expect_true(!sample.has_yaw_like && sample.packed_lanes[3] == 0 &&
                    sample.yaw_like == 0,
                "compact record invented a fourth lane");
}

static void failure_tests(void)
{
    static const uint8_t encoded[8] = {0};
    VcNflTrajectorySample sample = {.yaw_like = 123};
    expect_true(vc_nfl_trajectory_decode_record_le(NULL, 8U, &sample) ==
                    VC_NFL_TRAJECTORY_BAD_ARGUMENT,
                "null record was accepted");
    expect_true(vc_nfl_trajectory_decode_record_le(encoded, 7U, &sample) ==
                    VC_NFL_TRAJECTORY_BAD_STRIDE,
                "invalid stride was accepted");
    expect_true(sample.yaw_like == 123,
                "failed record decode modified destination");
    size_t failed = 42U;
    expect_true(vc_nfl_trajectory_decode_many_le(
                    encoded, 7U, 1U, &sample, &failed) ==
                    VC_NFL_TRAJECTORY_BAD_STRIDE,
                "batch decoder accepted an invalid stride");
    expect_true(strcmp(vc_nfl_trajectory_status_name(
                           VC_NFL_TRAJECTORY_BAD_STRIDE),
                       "bad-stride") == 0,
                "status name mismatch");
    vc_nfl_trajectory_apply_mirror(NULL);
}

int main(void)
{
    record_tests();
    failure_tests();
    if (failures != 0) {
        fprintf(stderr, "NFL_TRAJECTORY_NATIVE_FAIL failures=%d\n", failures);
        return 1;
    }
    puts("NFL_TRAJECTORY_NATIVE_PASS strides=6/8 mirror_lane=0");
    return 0;
}

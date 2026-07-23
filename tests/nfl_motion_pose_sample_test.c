#include "recovered/nfl2k5/motion_pose_sample.h"

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;

static void expect_true(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "NFL motion pose sample: %s\n", message);
        ++failures;
    }
}

static uint32_t float_bits(float value)
{
    uint32_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static void interpolation_and_clamp_tests(void)
{
    /* Two one-channel frames: [1,0,0,0] then [0,1,0,0]. */
    static const uint8_t packed[8] = {
        0x00, 0x02, 0x08, 0x20,
        0x00, 0x02, 0x08, 0x60,
    };
    const VcNflMotionPoseClipView clip = {
        .packed_frames = packed,
        .packed_frame_bytes = sizeof(packed),
        .frame_count = 2,
        .packed_poses_per_frame = 1,
        .sample_rate = 1,
        .time_scale = 1.0f,
    };
    float output[4] = {0.0f};
    VcNflMotionPoseSampleInfo info;
    expect_true(vc_nfl_motion_pose_sample_channel_clamped(
                    &clip, 0.5f, 0U, NULL, false, output, &info) ==
                    VC_NFL_MOTION_POSE_SAMPLE_OK,
                "mid-frame sample failed");
    expect_true(fabsf(output[0] - 0.707107127f) < 0.000001f &&
                    fabsf(output[1] - 0.707107127f) < 0.000001f &&
                    output[2] == 0.0f && output[3] == 0.0f,
                "mid-frame interpolation differs");
    expect_true(info.left_frame == 0U && info.right_frame == 1U &&
                    info.interpolation_t == 0.5f && info.packed_index == 0 &&
                    info.interpolation.branch ==
                        VC_NFL_QUATERNION_INTERPOLATION_FIXED_SLERP,
                "mid-frame metadata differs");

    expect_true(vc_nfl_motion_pose_sample_channel_clamped(
                    &clip, 2.0f, 0U, NULL, false, output, &info) ==
                    VC_NFL_MOTION_POSE_SAMPLE_OK,
                "final-frame clamp failed");
    expect_true(output[0] == 0.0f && output[1] == 1.0f &&
                    info.left_frame == 1U && info.right_frame == 1U &&
                    info.interpolation_t == 0.0f,
                "final-frame clamp differs");
}

static void map_and_mirror_tests(void)
{
    /* Frame is [0,0,1,0], with missing scalar-vector lane 2. */
    static const uint8_t packed[4] = {0x00, 0x02, 0x08, 0xA0};
    int8_t map[64];
    memset(map, -1, sizeof(map));
    map[6] = 0;
    map[7] = 0;
    const VcNflMotionPoseClipView clip = {
        .packed_frames = packed,
        .packed_frame_bytes = sizeof(packed),
        .frame_count = 1,
        .packed_poses_per_frame = 1,
        .sample_rate = 15,
        .time_scale = 1.0f,
    };
    float output[4] = {9.0f, 9.0f, 9.0f, 9.0f};
    VcNflMotionPoseSampleInfo info;
    expect_true(vc_nfl_motion_pose_sample_channel_clamped(
                    &clip, 0.0f, 3U, map, true, output, &info) ==
                    VC_NFL_MOTION_POSE_SAMPLE_OK,
                "mapped mirrored sample failed");
    expect_true(float_bits(output[0]) == float_bits(0.0f) &&
                    float_bits(output[1]) == float_bits(0.0f) &&
                    float_bits(output[2]) == float_bits(-1.0f) &&
                    float_bits(output[3]) == float_bits(-0.0f),
                "mapped mirror sign bits differ");
    expect_true(info.logical_channel == 3U && info.packed_index == 0 &&
                    info.mirrored,
                "mapped mirror metadata differs");

    const uint32_t before = float_bits(output[0]);
    expect_true(vc_nfl_motion_pose_sample_channel_clamped(
                    &clip, 0.0f, 4U, map, false, output, NULL) ==
                    VC_NFL_MOTION_POSE_SAMPLE_CHANNEL_DISABLED,
                "disabled channel was sampled");
    expect_true(float_bits(output[0]) == before,
                "disabled sample modified output");
}

static void title_policy_tests(void)
{
    static const uint8_t packed[8] = {
        0x00, 0x02, 0x08, 0x20,
        0x00, 0x02, 0x08, 0xA0,
    };
    VcNflMotionPoseClipView clip = {
        .packed_frames = packed,
        .packed_frame_bytes = sizeof(packed),
        .frame_count = 2,
        .packed_poses_per_frame = 1,
        .sample_rate = 1,
        .time_scale = 1.0f,
        .flags = 1U,
        .duration_seconds = 1.0f,
    };
    float output[4] = {0.0f};
    VcNflMotionPoseTitleSampleInfo info;
    expect_true(vc_nfl_motion_pose_sample_channel_title_policy(
                    &clip, 3.5f, 0U, NULL, output, &info) ==
                    VC_NFL_MOTION_POSE_SAMPLE_OK,
                "looping title-policy sample failed");
    expect_true(info.completed_loops == 3U &&
                    info.normalized_seconds == 0.5f &&
                    info.pose.frame_coordinate == 0.5f,
                "looping title-policy metadata differs");
    expect_true(output[0] > 0.707f && output[2] > 0.707f,
                "looping title-policy interpolation differs");

    clip.flags = 4U;
    expect_true(vc_nfl_motion_pose_sample_channel_title_policy(
                    &clip, 3.5f, 0U, NULL, output, &info) ==
                    VC_NFL_MOTION_POSE_SAMPLE_OK,
                "nonlooping mirrored title-policy sample failed");
    expect_true(info.completed_loops == 0U &&
                    info.normalized_seconds == 3.5f &&
                    info.pose.left_frame == 1U &&
                    info.pose.right_frame == 1U &&
                    float_bits(output[2]) == float_bits(-1.0f),
                "nonlooping clamp/mirror policy differs");

    clip.flags = 1U;
    clip.duration_seconds = 0.0f;
    expect_true(vc_nfl_motion_pose_sample_channel_title_policy(
                    &clip, 1.0f, 0U, NULL, output, NULL) ==
                    VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP,
                "looping clip with zero duration was accepted");
}

static void failure_tests(void)
{
    static const uint8_t packed[4] = {0x00, 0x02, 0x08, 0x20};
    VcNflMotionPoseClipView clip = {
        .packed_frames = packed,
        .packed_frame_bytes = sizeof(packed),
        .frame_count = 1,
        .packed_poses_per_frame = 1,
        .sample_rate = 15,
        .time_scale = 1.0f,
    };
    float output[4] = {0.0f};
    expect_true(vc_nfl_motion_pose_sample_channel_clamped(
                    NULL, 0.0f, 0U, NULL, false, output, NULL) ==
                    VC_NFL_MOTION_POSE_SAMPLE_BAD_ARGUMENT,
                "null clip was accepted");
    expect_true(vc_nfl_motion_pose_sample_channel_clamped(
                    &clip, 0.0f, 32U, NULL, false, output, NULL) ==
                    VC_NFL_MOTION_POSE_SAMPLE_BAD_ARGUMENT,
                "logical channel 32 was accepted");
    expect_true(vc_nfl_motion_pose_sample_channel_clamped(
                    &clip, -0.1f, 0U, NULL, false, output, NULL) ==
                    VC_NFL_MOTION_POSE_SAMPLE_BAD_TIME,
                "negative time was accepted");
    clip.packed_frame_bytes = 3U;
    expect_true(vc_nfl_motion_pose_sample_channel_clamped(
                    &clip, 0.0f, 0U, NULL, false, output, NULL) ==
                    VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP,
                "truncated clip was accepted");
    expect_true(strcmp(vc_nfl_motion_pose_sample_status_name(
                           VC_NFL_MOTION_POSE_SAMPLE_CHANNEL_DISABLED),
                       "channel-disabled") == 0,
                "status name mismatch");
}

int main(void)
{
    interpolation_and_clamp_tests();
    map_and_mirror_tests();
    title_policy_tests();
    failure_tests();
    if (failures != 0) {
        fprintf(stderr, "NFL_MOTION_POSE_SAMPLE_NATIVE_FAIL failures=%d\n",
                failures);
        return 1;
    }
    puts("NFL_MOTION_POSE_SAMPLE_NATIVE_PASS decode_map_interp_mirror_loop=1");
    return 0;
}

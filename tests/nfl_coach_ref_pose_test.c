#include "recovered/nfl2k5/coach_ref_pose.h"

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int failures = 0;

static void expect_true(bool condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "NFL coach/ref pose: %s\n", message);
        ++failures;
    }
}

static bool quaternion_near(const float left[4], const float right[4],
                            float tolerance)
{
    float direct = 0.0f;
    float negated = 0.0f;
    for (size_t index = 0U; index < 4U; ++index) {
        direct = fmaxf(direct, fabsf(left[index] - right[index]));
        negated = fmaxf(negated, fabsf(left[index] + right[index]));
    }
    return fminf(direct, negated) <= tolerance;
}

static void axis_angle(const float axis[3], float angle_radians,
                       float output[4])
{
    const float length = sqrtf(axis[0] * axis[0] + axis[1] * axis[1] +
                               axis[2] * axis[2]);
    const float half = angle_radians * 0.5f;
    const float scale = sinf(half) / length;
    output[0] = cosf(half);
    output[1] = axis[0] * scale;
    output[2] = axis[1] * scale;
    output[3] = axis[2] * scale;
}

static void exact_map_and_axis_tests(void)
{
    static const int8_t expected_first_50[50] = {
         0,  0,  1,  5,  2,  6,  3,  7,  4,  8,
         5,  1,  6,  2,  7,  3,  8,  4,  9,  9,
        10, 10, 11, 11, 12, 12, 13, 17, 14, 18,
        -1, -1, 15, 19, -1, -1, 16, 20, 17, 13,
        18, 14, -1, -1, 19, 15, -1, -1, 20, 16,
    };
    expect_true(memcmp(vc_nfl_coach_ref_pose_shared_channel_map,
                       expected_first_50, sizeof(expected_first_50)) == 0,
                "shared signed map differs");
    for (size_t index = 50U;
         index < VC_NFL_COACH_REF_POSE_CHANNEL_MAP_BYTES; ++index) {
        expect_true(vc_nfl_coach_ref_pose_shared_channel_map[index] == 0,
                    "XBE map padding is not zero");
    }
    expect_true(vc_nfl_coach_ref_pose_twist_bind_axes[0][0] ==
                        0x1.9966d0p+3f &&
                    vc_nfl_coach_ref_pose_twist_bind_axes[0][1] ==
                        -0x1.7dba46p+1f &&
                    vc_nfl_coach_ref_pose_twist_bind_axes[0][2] ==
                        0x1.a8fa40p+2f &&
                    vc_nfl_coach_ref_pose_twist_bind_axes[1][0] ==
                        -0x1.998ea0p+3f &&
                    vc_nfl_coach_ref_pose_twist_bind_axes[1][1] ==
                        -0x1.7dcf04p+1f &&
                    vc_nfl_coach_ref_pose_twist_bind_axes[1][2] ==
                        0x1.a87854p+2f,
                "twist bind-axis bits differ");
}

static void callback_tests(void)
{
    VcNflCoachRefLocalPose pose;
    for (size_t channel = 0U;
         channel < VC_NFL_COACH_REF_POSE_CHANNEL_COUNT; ++channel) {
        pose.scalar_first[channel][0] = 1.0f;
        pose.scalar_first[channel][1] = (float)channel * 0.001f;
        pose.scalar_first[channel][2] = (float)channel * -0.002f;
        pose.scalar_first[channel][3] = (float)channel * 0.003f;
    }
    const float retained[4] = {
        pose.scalar_first[10][0], pose.scalar_first[10][1],
        pose.scalar_first[10][2], pose.scalar_first[10][3],
    };
    const float pi = 3.14159265358979323846f;
    float left_source[4];
    float right_source[4];
    axis_angle(vc_nfl_coach_ref_pose_twist_bind_axes[0],
               100.0f * pi / 180.0f, left_source);
    axis_angle(vc_nfl_coach_ref_pose_twist_bind_axes[1],
               -76.0f * pi / 180.0f, right_source);
    memcpy(pose.scalar_first[VC_NFL_COACH_REF_POSE_LEFT_HUMERUS],
           left_source, sizeof(left_source));
    memcpy(pose.scalar_first[VC_NFL_COACH_REF_POSE_RIGHT_HUMERUS],
           right_source, sizeof(right_source));

    expect_true(vc_nfl_coach_ref_pose_complete_disabled_channels(&pose) ==
                    VC_NFL_COACH_REF_POSE_OK,
                "pure-twist callback failed");
    float expected_left_half[4];
    float expected_right_half[4];
    axis_angle(vc_nfl_coach_ref_pose_twist_bind_axes[0],
               50.0f * pi / 180.0f, expected_left_half);
    axis_angle(vc_nfl_coach_ref_pose_twist_bind_axes[1],
               -38.0f * pi / 180.0f, expected_right_half);
    expect_true(quaternion_near(
                    pose.scalar_first[VC_NFL_COACH_REF_POSE_LEFT_TWIST],
                    expected_left_half, 0.000001f),
                "left synthesized half twist differs");
    expect_true(quaternion_near(
                    pose.scalar_first[VC_NFL_COACH_REF_POSE_LEFT_HUMERUS],
                    expected_left_half, 0.000001f),
                "left adjusted humerus differs");
    expect_true(quaternion_near(
                    pose.scalar_first[VC_NFL_COACH_REF_POSE_RIGHT_TWIST],
                    expected_right_half, 0.000001f),
                "right synthesized half twist differs");
    expect_true(quaternion_near(
                    pose.scalar_first[VC_NFL_COACH_REF_POSE_RIGHT_HUMERUS],
                    expected_right_half, 0.000001f),
                "right adjusted humerus differs");
    static const float identity[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    expect_true(memcmp(
                    pose.scalar_first[VC_NFL_COACH_REF_POSE_LEFT_WRIST],
                    identity, sizeof(identity)) == 0 &&
                    memcmp(
                        pose.scalar_first[VC_NFL_COACH_REF_POSE_RIGHT_WRIST],
                        identity, sizeof(identity)) == 0,
                "wrist identity writes differ");
    expect_true(memcmp(pose.scalar_first[10], retained, sizeof(retained)) == 0,
                "callback changed an unrelated channel");

    VcNflCoachRefLocalPose invalid = pose;
    invalid.scalar_first[VC_NFL_COACH_REF_POSE_LEFT_HUMERUS][0] = NAN;
    const VcNflCoachRefLocalPose before = invalid;
    expect_true(vc_nfl_coach_ref_pose_complete_disabled_channels(&invalid) ==
                    VC_NFL_COACH_REF_POSE_TWIST_FAILED,
                "non-finite humerus was accepted");
    expect_true(memcmp(&invalid, &before, sizeof(invalid)) == 0,
                "failed callback was not transactional");
}

static void sampler_tests(void)
{
    uint8_t packed[2U * VC_NFL_COACH_REF_POSE_PACKED_CHANNEL_COUNT * 4U];
    static const uint8_t identity_word[4] = {0x00, 0x02, 0x08, 0x20};
    for (size_t offset = 0U; offset < sizeof(packed); offset += 4U) {
        memcpy(packed + offset, identity_word, sizeof(identity_word));
    }
    VcNflMotionPoseClipView clip = {
        .packed_frames = packed,
        .packed_frame_bytes = sizeof(packed),
        .frame_count = 2U,
        .packed_poses_per_frame =
            (uint8_t)VC_NFL_COACH_REF_POSE_PACKED_CHANNEL_COUNT,
        .sample_rate = 1U,
        .time_scale = 1.0f,
        .flags = 0U,
        .duration_seconds = 1.0f,
    };
    VcNflCoachRefLocalPose pose;
    memset(&pose, 0xA5, sizeof(pose));
    VcNflCoachRefPoseInfo info;
    expect_true(vc_nfl_coach_ref_pose_sample_clamped(
                    &clip, 0.5f, false, &pose, &info) ==
                    VC_NFL_COACH_REF_POSE_OK,
                "21-channel composed sample failed");
    expect_true(info.sample_status == VC_NFL_MOTION_POSE_SAMPLE_OK &&
                    info.failed_logical_channel == UINT8_MAX &&
                    !info.mirrored && info.normalized_seconds == 0.5f &&
                    info.completed_loops == 0U,
                "composed sample metadata differs");
    for (size_t channel = 0U;
         channel < VC_NFL_COACH_REF_POSE_CHANNEL_COUNT; ++channel) {
        expect_true(fabsf(pose.scalar_first[channel][0] - 1.0f) < 0.000001f &&
                        fabsf(pose.scalar_first[channel][1]) < 0.000001f &&
                        fabsf(pose.scalar_first[channel][2]) < 0.000001f &&
                        fabsf(pose.scalar_first[channel][3]) < 0.000001f,
                    "identity clip did not produce an identity local slot");
    }

    clip.flags = 5U;
    expect_true(vc_nfl_coach_ref_pose_sample_title_policy(
                    &clip, 3.5f, &pose, &info) ==
                    VC_NFL_COACH_REF_POSE_OK,
                "looped/mirrored title sample failed");
    expect_true(info.mirrored && info.normalized_seconds == 0.5f &&
                    info.completed_loops == 3U,
                "title-policy metadata differs");

    clip.packed_frame_bytes = sizeof(packed) - 1U;
    const VcNflCoachRefLocalPose before = pose;
    expect_true(vc_nfl_coach_ref_pose_sample_clamped(
                    &clip, 0.0f, false, &pose, &info) ==
                    VC_NFL_COACH_REF_POSE_SAMPLE_FAILED &&
                    info.sample_status == VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP &&
                    info.failed_logical_channel == 0U,
                "truncated clip error was not propagated");
    expect_true(memcmp(&pose, &before, sizeof(pose)) == 0,
                "failed sample modified destination pose");

    clip.packed_frame_bytes = sizeof(packed);
    clip.packed_poses_per_frame = 23U;
    expect_true(vc_nfl_coach_ref_pose_sample_clamped(
                    &clip, 0.0f, false, &pose, &info) ==
                    VC_NFL_COACH_REF_POSE_SAMPLE_FAILED &&
                    info.sample_status == VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP,
                "non-21-channel clip was accepted");
}

static void gltf_and_failure_tests(void)
{
    float quaternion[4] = {0.75f, 0.25f, -0.5f, 0.375f};
    vc_nfl_coach_ref_quaternion_to_gltf_xyzw(quaternion, quaternion);
    expect_true(quaternion[0] == 0.25f && quaternion[1] == -0.5f &&
                    quaternion[2] == 0.375f && quaternion[3] == 0.75f,
                "aliased glTF component reorder differs");

    VcNflCoachRefLocalPose source;
    for (size_t channel = 0U;
         channel < VC_NFL_COACH_REF_POSE_CHANNEL_COUNT; ++channel) {
        source.scalar_first[channel][0] = (float)channel + 0.0f;
        source.scalar_first[channel][1] = (float)channel + 0.1f;
        source.scalar_first[channel][2] = (float)channel + 0.2f;
        source.scalar_first[channel][3] = (float)channel + 0.3f;
    }
    VcNflCoachRefGltfPose output;
    vc_nfl_coach_ref_pose_to_gltf_xyzw(&source, &output);
    expect_true(output.xyzw[24][0] == source.scalar_first[24][1] &&
                    output.xyzw[24][1] == source.scalar_first[24][2] &&
                    output.xyzw[24][2] == source.scalar_first[24][3] &&
                    output.xyzw[24][3] == source.scalar_first[24][0],
                "whole-pose glTF reorder differs");
    expect_true(vc_nfl_coach_ref_pose_complete_disabled_channels(NULL) ==
                    VC_NFL_COACH_REF_POSE_BAD_ARGUMENT,
                "null callback pose was accepted");
    expect_true(vc_nfl_coach_ref_pose_sample_clamped(
                    NULL, 0.0f, false, &source, NULL) ==
                    VC_NFL_COACH_REF_POSE_BAD_ARGUMENT,
                "null clip was accepted");
    expect_true(strcmp(vc_nfl_coach_ref_pose_status_name(
                           VC_NFL_COACH_REF_POSE_TWIST_FAILED),
                       "twist-failed") == 0,
                "status name differs");
    expect_true(!vc_nfl_coach_ref_pose_twist_is_xbox_bit_exact(),
                "portable twist path claims Xbox bit identity");
}

int main(void)
{
    exact_map_and_axis_tests();
    callback_tests();
    sampler_tests();
    gltf_and_failure_tests();
    if (failures != 0) {
        fprintf(stderr, "NFL_COACH_REF_POSE_NATIVE_FAIL failures=%d\n",
                failures);
        return 1;
    }
    puts("NFL_COACH_REF_POSE_NATIVE_PASS channels=25 packed=21 disabled=4");
    return 0;
}

#include "recovered/nfl2k5/player_pose.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int failures;

static void expect_true(int condition, const char *message)
{
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        ++failures;
    }
}

static void normalize3(const float axis[3], double output[3])
{
    const double x = (double)axis[0];
    const double y = (double)axis[1];
    const double z = (double)axis[2];
    const double length = sqrt(x * x + y * y + z * z);
    output[0] = x / length;
    output[1] = y / length;
    output[2] = z / length;
}

static void axis_angle(const float axis[3], double radians, float output[4])
{
    double unit[3];
    normalize3(axis, unit);
    const double sine = sin(radians * 0.5);
    output[0] = (float)cos(radians * 0.5);
    output[1] = (float)(unit[0] * sine);
    output[2] = (float)(unit[1] * sine);
    output[3] = (float)(unit[2] * sine);
}

static void hamilton(const float left[4], const float right[4],
                     float output[4])
{
    const double lw = (double)left[0];
    const double lx = (double)left[1];
    const double ly = (double)left[2];
    const double lz = (double)left[3];
    const double rw = (double)right[0];
    const double rx = (double)right[1];
    const double ry = (double)right[2];
    const double rz = (double)right[3];
    output[0] = (float)(lw * rw - (lx * rx + ly * ry + lz * rz));
    output[1] = (float)(lw * rx + lx * rw + ly * rz - lz * ry);
    output[2] = (float)(lw * ry - lx * rz + ly * rw + lz * rx);
    output[3] = (float)(lw * rz + lx * ry - ly * rx + lz * rw);
}

static int quaternion_near(const float left[4], const float right[4],
                           float tolerance)
{
    float direct = 0.0f;
    float negated = 0.0f;
    for (size_t lane = 0U; lane < 4U; ++lane) {
        direct = fmaxf(direct, fabsf(left[lane] - right[lane]));
        negated = fmaxf(negated, fabsf(left[lane] + right[lane]));
    }
    return fminf(direct, negated) <= tolerance;
}

static void exact_map_and_axis_tests(void)
{
    static const int8_t expected_map[64] = {
         0,  0,  1,  5,  2,  6,  3,  7,  4,  8,
         5,  1,  6,  2,  7,  3,  8,  4,  9,  9,
        10, 10, 11, 11, 12, 12, 13, 17, 14, 18,
        15, 19, -1, -1, 16, 20, 17, 13, 18, 14,
        19, 15, -1, -1, 20, 16, 21, 22, 22, 21,
         0,  0,  0,  0,  0,  0,  0,  0,  0,  0,
         0,  0,  0,  0,
    };
    expect_true(memcmp(vc_nfl_player_pose_channel_map, expected_map,
                       sizeof(expected_map)) == 0,
                "player signed channel map differs");

    static const uint32_t expected_axis_bits[2][3] = {
        {UINT32_C(0x410face0), UINT32_C(0xbeb8a406), UINT32_C(0x40d16da0)},
        {UINT32_C(0xc10f9f2e), UINT32_C(0xbeb8b701), UINT32_C(0x40d190e9)},
    };
    uint32_t actual_axis_bits[2][3];
    memcpy(actual_axis_bits, vc_nfl_player_pose_hand_bind_axes,
           sizeof(actual_axis_bits));
    expect_true(memcmp(actual_axis_bits, expected_axis_bits,
                       sizeof(expected_axis_bits)) == 0,
                "player hand bind-axis bits differ");
}

static void callback_tests(void)
{
    VcNflPlayerLocalPose pose;
    memset(&pose, 0, sizeof(pose));
    for (size_t channel = 0U; channel < VC_NFL_PLAYER_POSE_CHANNEL_COUNT;
         ++channel) {
        pose.scalar_first[channel][0] = 1.0f;
    }
    const float retained[4] = {0.7f, 0.1f, -0.2f, 0.3f};
    memcpy(pose.scalar_first[10], retained, sizeof(retained));

    float left_source[4];
    float right_source[4];
    axis_angle(vc_nfl_player_pose_hand_bind_axes[VC_NFL_PLAYER_POSE_LEFT],
               0.83, left_source);
    axis_angle(vc_nfl_player_pose_hand_bind_axes[VC_NFL_PLAYER_POSE_RIGHT],
               -1.17, right_source);
    memcpy(pose.scalar_first[VC_NFL_PLAYER_POSE_LEFT_HAND], left_source,
           sizeof(left_source));
    memcpy(pose.scalar_first[VC_NFL_PLAYER_POSE_RIGHT_HAND], right_source,
           sizeof(right_source));

    expect_true(vc_nfl_player_pose_complete_disabled_channels(&pose) ==
                    VC_NFL_PLAYER_POSE_OK,
                "player twist callback failed");
    expect_true(quaternion_near(
                    pose.scalar_first[VC_NFL_PLAYER_POSE_LEFT_WRIST],
                    left_source, 0.000001f),
                "left full twist differs for a pure twist");
    expect_true(quaternion_near(
                    pose.scalar_first[VC_NFL_PLAYER_POSE_RIGHT_WRIST],
                    right_source, 0.000001f),
                "right full twist differs for a pure twist");
    static const float identity[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    expect_true(quaternion_near(
                    pose.scalar_first[VC_NFL_PLAYER_POSE_LEFT_HAND], identity,
                    0.000001f),
                "left hand retained pure twist");
    expect_true(quaternion_near(
                    pose.scalar_first[VC_NFL_PLAYER_POSE_RIGHT_HAND], identity,
                    0.000001f),
                "right hand retained pure twist");
    expect_true(memcmp(pose.scalar_first[10], retained, sizeof(retained)) == 0,
                "callback changed an unrelated player channel");

    /* A swing followed by twist must recompose as wrist * adjusted hand. */
    float swing[4];
    static const float swing_axis[3] = {0.37f, -0.59f, 0.71f};
    axis_angle(swing_axis, 0.44, swing);
    axis_angle(vc_nfl_player_pose_hand_bind_axes[VC_NFL_PLAYER_POSE_LEFT],
               -0.76, left_source);
    float mixed[4];
    hamilton(swing, left_source, mixed);
    memcpy(pose.scalar_first[VC_NFL_PLAYER_POSE_LEFT_HAND], mixed,
           sizeof(mixed));
    memcpy(pose.scalar_first[VC_NFL_PLAYER_POSE_RIGHT_HAND], identity,
           sizeof(identity));
    expect_true(vc_nfl_player_pose_complete_disabled_channels(&pose) ==
                    VC_NFL_PLAYER_POSE_OK,
                "mixed player twist callback failed");
    float recomposed[4];
    hamilton(pose.scalar_first[VC_NFL_PLAYER_POSE_LEFT_WRIST],
             pose.scalar_first[VC_NFL_PLAYER_POSE_LEFT_HAND], recomposed);
    expect_true(quaternion_near(recomposed, mixed, 0.000002f),
                "wrist/hand result does not recompose sampled hand");

    VcNflPlayerLocalPose invalid = pose;
    invalid.scalar_first[VC_NFL_PLAYER_POSE_LEFT_HAND][0] = NAN;
    const VcNflPlayerLocalPose before = invalid;
    expect_true(vc_nfl_player_pose_complete_disabled_channels(&invalid) ==
                    VC_NFL_PLAYER_POSE_TWIST_FAILED,
                "non-finite player hand was accepted");
    expect_true(memcmp(&invalid, &before, sizeof(invalid)) == 0,
                "failed player callback was not transactional");
}

static void sampler_tests(void)
{
    uint8_t packed[2U * VC_NFL_PLAYER_POSE_PACKED_CHANNEL_COUNT * 4U];
    static const uint8_t identity_word[4] = {0x00, 0x02, 0x08, 0x20};
    for (size_t offset = 0U; offset < sizeof(packed); offset += 4U) {
        memcpy(packed + offset, identity_word, sizeof(identity_word));
    }
    VcNflMotionPoseClipView clip = {
        .packed_frames = packed,
        .packed_frame_bytes = sizeof(packed),
        .frame_count = 2U,
        .packed_poses_per_frame =
            (uint8_t)VC_NFL_PLAYER_POSE_PACKED_CHANNEL_COUNT,
        .sample_rate = 1U,
        .time_scale = 1.0f,
        .flags = 0U,
        .duration_seconds = 1.0f,
    };
    VcNflPlayerLocalPose pose;
    memset(&pose, 0xA5, sizeof(pose));
    VcNflPlayerPoseInfo info;
    expect_true(vc_nfl_player_pose_sample_clamped(
                    &clip, 0.5f, false, &pose, &info) ==
                    VC_NFL_PLAYER_POSE_OK,
                "23-channel player sample failed");
    expect_true(info.sample_status == VC_NFL_MOTION_POSE_SAMPLE_OK &&
                    info.failed_logical_channel == UINT8_MAX &&
                    !info.mirrored && info.normalized_seconds == 0.5f &&
                    info.completed_loops == 0U,
                "player sample metadata differs");
    for (size_t channel = 0U; channel < VC_NFL_PLAYER_POSE_CHANNEL_COUNT;
         ++channel) {
        expect_true(fabsf(pose.scalar_first[channel][0] - 1.0f) < 0.000001f &&
                        fabsf(pose.scalar_first[channel][1]) < 0.000001f &&
                        fabsf(pose.scalar_first[channel][2]) < 0.000001f &&
                        fabsf(pose.scalar_first[channel][3]) < 0.000001f,
                    "identity player clip did not yield identity local pose");
    }

    clip.flags = 5U;
    expect_true(vc_nfl_player_pose_sample_title_policy(
                    &clip, 3.5f, &pose, &info) == VC_NFL_PLAYER_POSE_OK,
                "looped/mirrored player sample failed");
    expect_true(info.mirrored && info.normalized_seconds == 0.5f &&
                    info.completed_loops == 3U,
                "player title-policy metadata differs");

    clip.packed_frame_bytes = sizeof(packed) - 1U;
    const VcNflPlayerLocalPose before = pose;
    expect_true(vc_nfl_player_pose_sample_clamped(
                    &clip, 0.0f, false, &pose, &info) ==
                    VC_NFL_PLAYER_POSE_SAMPLE_FAILED &&
                    info.sample_status == VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP &&
                    info.failed_logical_channel == 0U,
                "truncated player clip error was not propagated");
    expect_true(memcmp(&pose, &before, sizeof(pose)) == 0,
                "failed player sample modified its destination");

    clip.packed_frame_bytes = sizeof(packed);
    clip.packed_poses_per_frame = 21U;
    expect_true(vc_nfl_player_pose_sample_clamped(
                    &clip, 0.0f, false, &pose, &info) ==
                    VC_NFL_PLAYER_POSE_SAMPLE_FAILED &&
                    info.sample_status == VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP,
                "non-23-channel player clip was accepted");
}

static void gltf_and_failure_tests(void)
{
    float quaternion[4] = {0.75f, 0.25f, -0.5f, 0.375f};
    vc_nfl_player_quaternion_to_gltf_xyzw(quaternion, quaternion);
    expect_true(quaternion[0] == 0.25f && quaternion[1] == -0.5f &&
                    quaternion[2] == 0.375f && quaternion[3] == 0.75f,
                "aliased player glTF component reorder differs");

    VcNflPlayerLocalPose source;
    for (size_t channel = 0U; channel < VC_NFL_PLAYER_POSE_CHANNEL_COUNT;
         ++channel) {
        source.scalar_first[channel][0] = (float)channel + 0.0f;
        source.scalar_first[channel][1] = (float)channel + 0.1f;
        source.scalar_first[channel][2] = (float)channel + 0.2f;
        source.scalar_first[channel][3] = (float)channel + 0.3f;
    }
    VcNflPlayerGltfPose output;
    vc_nfl_player_pose_to_gltf_xyzw(&source, &output);
    expect_true(output.xyzw[24][0] == source.scalar_first[24][1] &&
                    output.xyzw[24][1] == source.scalar_first[24][2] &&
                    output.xyzw[24][2] == source.scalar_first[24][3] &&
                    output.xyzw[24][3] == source.scalar_first[24][0],
                "whole player pose glTF reorder differs");
    expect_true(vc_nfl_player_pose_complete_disabled_channels(NULL) ==
                    VC_NFL_PLAYER_POSE_BAD_ARGUMENT,
                "null player callback pose was accepted");
    expect_true(vc_nfl_player_pose_sample_clamped(
                    NULL, 0.0f, false, &source, NULL) ==
                    VC_NFL_PLAYER_POSE_BAD_ARGUMENT,
                "null player clip was accepted");
    expect_true(strcmp(vc_nfl_player_pose_status_name(
                           VC_NFL_PLAYER_POSE_TWIST_FAILED),
                       "twist-failed") == 0,
                "player status name differs");
    expect_true(!vc_nfl_player_pose_twist_is_xbox_bit_exact(),
                "portable player twist path claims Xbox bit identity");
}

int main(void)
{
    exact_map_and_axis_tests();
    callback_tests();
    sampler_tests();
    gltf_and_failure_tests();
    if (failures != 0) {
        fprintf(stderr, "NFL_PLAYER_POSE_NATIVE_FAIL failures=%d\n", failures);
        return 1;
    }
    puts("NFL_PLAYER_POSE_NATIVE_PASS channels=25 packed=23 disabled=2");
    return 0;
}

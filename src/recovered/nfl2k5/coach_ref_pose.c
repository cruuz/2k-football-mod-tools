#include "recovered/nfl2k5/coach_ref_pose.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

const int8_t vc_nfl_coach_ref_pose_shared_channel_map[
    VC_NFL_COACH_REF_POSE_CHANNEL_MAP_BYTES] = {
     0,  0,  1,  5,  2,  6,  3,  7,  4,  8,
     5,  1,  6,  2,  7,  3,  8,  4,  9,  9,
    10, 10, 11, 11, 12, 12, 13, 17, 14, 18,
    -1, -1, 15, 19, -1, -1, 16, 20, 17, 13,
    18, 14, -1, -1, 19, 15, -1, -1, 20, 16,
     0,  0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,
};

const float vc_nfl_coach_ref_pose_twist_bind_axes[2][3] = {
    {0x1.9966d0p+3f, -0x1.7dba46p+1f, 0x1.a8fa40p+2f},
    {-0x1.998ea0p+3f, -0x1.7dcf04p+1f, 0x1.a87854p+2f},
};

static void set_info(VcNflCoachRefPoseInfo *info,
                     VcNflMotionPoseSampleStatus sample_status,
                     uint8_t failed_logical_channel,
                     bool mirrored,
                     float normalized_seconds,
                     uint32_t completed_loops)
{
    if (info != NULL) {
        *info = (VcNflCoachRefPoseInfo) {
            .sample_status = sample_status,
            .failed_logical_channel = failed_logical_channel,
            .mirrored = mirrored,
            .normalized_seconds = normalized_seconds,
            .completed_loops = completed_loops,
        };
    }
}

static void quaternion_multiply(const double left[4], const double right[4],
                                double output[4])
{
    output[0] = left[0] * right[0] -
                (left[1] * right[1] + left[2] * right[2] +
                 left[3] * right[3]);
    output[1] = left[0] * right[1] + left[1] * right[0] +
                left[2] * right[3] - left[3] * right[2];
    output[2] = left[0] * right[2] - left[1] * right[3] +
                left[2] * right[0] + left[3] * right[1];
    output[3] = left[0] * right[3] + left[1] * right[2] -
                left[2] * right[1] + left[3] * right[0];
}

static void rotate_vector(const double quaternion[4], const double vector[3],
                          double output[3])
{
    const double pure[4] = {0.0, vector[0], vector[1], vector[2]};
    const double conjugate[4] = {
        quaternion[0], -quaternion[1], -quaternion[2], -quaternion[3],
    };
    double first[4];
    double rotated[4];
    quaternion_multiply(quaternion, pure, first);
    quaternion_multiply(first, conjugate, rotated);
    output[0] = rotated[1];
    output[1] = rotated[2];
    output[2] = rotated[3];
}

static double dot3(const double left[3], const double right[3])
{
    return left[0] * right[0] + left[1] * right[1] +
           left[2] * right[2];
}

static void cross3(const double left[3], const double right[3],
                   double output[3])
{
    output[0] = left[1] * right[2] - left[2] * right[1];
    output[1] = left[2] * right[0] - left[0] * right[2];
    output[2] = left[0] * right[1] - left[1] * right[0];
}

static bool half_twist(const float bind_axis[3], const float source[4],
                       float output[4])
{
    double bind[3];
    double quaternion[4];
    for (size_t index = 0; index < 3U; ++index) {
        bind[index] = (double)bind_axis[index];
    }
    for (size_t index = 0; index < 4U; ++index) {
        if (!isfinite(source[index])) {
            return false;
        }
        quaternion[index] = (double)source[index];
    }

    const double norm_squared = dot3(bind, bind);
    if (!isfinite(norm_squared) || !(norm_squared > 0.0)) {
        return false;
    }
    const double perpendicular[3] = {
        bind[0] == 0.0 && bind[1] == 0.0 ? 1.0 : -bind[1],
        bind[0] == 0.0 && bind[1] == 0.0 ? 0.0 : bind[0],
        0.0,
    };
    double rotated[3];
    rotate_vector(quaternion, perpendicular, rotated);
    const double projection_scale = dot3(rotated, bind) / norm_squared;
    const double projected[3] = {
        rotated[0] - bind[0] * projection_scale,
        rotated[1] - bind[1] * projection_scale,
        rotated[2] - bind[2] * projection_scale,
    };
    const double projected_squared = dot3(projected, projected);
    const double perpendicular_squared = dot3(perpendicular, perpendicular);
    if (!isfinite(projected_squared) || !isfinite(perpendicular_squared) ||
        !(projected_squared > 0.0) || !(perpendicular_squared > 0.0)) {
        return false;
    }

    double cosine = dot3(perpendicular, projected) /
                    sqrt(perpendicular_squared * projected_squared);
    if (!isfinite(cosine)) {
        return false;
    }
    if (cosine < -1.0) {
        cosine = -1.0;
    } else if (cosine > 1.0) {
        cosine = 1.0;
    }

    double signed_inverse_axis_length = 1.0 / sqrt(norm_squared);
    double crossing[3];
    cross3(perpendicular, projected, crossing);
    if (dot3(crossing, bind) < 0.0) {
        signed_inverse_axis_length = -signed_inverse_axis_length;
    }
    const double full_half_cosine = sqrt((1.0 + cosine) * 0.5);
    const double scalar = sqrt((1.0 + full_half_cosine) * 0.5);
    const double vector_scale =
        sqrt((1.0 - full_half_cosine) * 0.5) *
        signed_inverse_axis_length;
    const double result[4] = {
        scalar,
        bind[0] * vector_scale,
        bind[1] * vector_scale,
        bind[2] * vector_scale,
    };
    for (size_t index = 0; index < 4U; ++index) {
        if (!isfinite(result[index])) {
            return false;
        }
        output[index] = (float)result[index];
    }
    return true;
}

static void adjusted_humerus(const float source[4], const float half[4],
                             float output[4])
{
    double source_double[4];
    const double conjugate[4] = {
        (double)half[0], -(double)half[1], -(double)half[2],
        -(double)half[3],
    };
    for (size_t index = 0; index < 4U; ++index) {
        source_double[index] = (double)source[index];
    }
    double result[4];
    quaternion_multiply(source_double, conjugate, result);
    for (size_t index = 0; index < 4U; ++index) {
        output[index] = (float)result[index];
    }
}

VcNflCoachRefPoseStatus vc_nfl_coach_ref_pose_complete_disabled_channels(
    VcNflCoachRefLocalPose *pose)
{
    if (pose == NULL) {
        return VC_NFL_COACH_REF_POSE_BAD_ARGUMENT;
    }

    float left_half[4];
    float right_half[4];
    if (!half_twist(
            vc_nfl_coach_ref_pose_twist_bind_axes[VC_NFL_COACH_REF_POSE_LEFT],
            pose->scalar_first[VC_NFL_COACH_REF_POSE_LEFT_HUMERUS],
            left_half) ||
        !half_twist(
            vc_nfl_coach_ref_pose_twist_bind_axes[VC_NFL_COACH_REF_POSE_RIGHT],
            pose->scalar_first[VC_NFL_COACH_REF_POSE_RIGHT_HUMERUS],
            right_half)) {
        return VC_NFL_COACH_REF_POSE_TWIST_FAILED;
    }

    float left_adjusted[4];
    float right_adjusted[4];
    adjusted_humerus(
        pose->scalar_first[VC_NFL_COACH_REF_POSE_LEFT_HUMERUS], left_half,
        left_adjusted);
    adjusted_humerus(
        pose->scalar_first[VC_NFL_COACH_REF_POSE_RIGHT_HUMERUS], right_half,
        right_adjusted);
    static const float identity[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    memcpy(pose->scalar_first[VC_NFL_COACH_REF_POSE_LEFT_HUMERUS],
           left_adjusted, sizeof(left_adjusted));
    memcpy(pose->scalar_first[VC_NFL_COACH_REF_POSE_LEFT_TWIST],
           left_half, sizeof(left_half));
    memcpy(pose->scalar_first[VC_NFL_COACH_REF_POSE_LEFT_WRIST],
           identity, sizeof(identity));
    memcpy(pose->scalar_first[VC_NFL_COACH_REF_POSE_RIGHT_HUMERUS],
           right_adjusted, sizeof(right_adjusted));
    memcpy(pose->scalar_first[VC_NFL_COACH_REF_POSE_RIGHT_TWIST],
           right_half, sizeof(right_half));
    memcpy(pose->scalar_first[VC_NFL_COACH_REF_POSE_RIGHT_WRIST],
           identity, sizeof(identity));
    return VC_NFL_COACH_REF_POSE_OK;
}

static VcNflCoachRefPoseStatus finish_sampled_pose(
    VcNflCoachRefLocalPose *candidate,
    VcNflCoachRefLocalPose *pose,
    VcNflCoachRefPoseInfo *info,
    bool mirrored,
    float normalized_seconds,
    uint32_t completed_loops)
{
    const VcNflCoachRefPoseStatus status =
        vc_nfl_coach_ref_pose_complete_disabled_channels(candidate);
    if (status != VC_NFL_COACH_REF_POSE_OK) {
        set_info(info, VC_NFL_MOTION_POSE_SAMPLE_OK,
                 UINT8_MAX, mirrored,
                 normalized_seconds, completed_loops);
        return status;
    }
    *pose = *candidate;
    set_info(info, VC_NFL_MOTION_POSE_SAMPLE_OK, UINT8_MAX, mirrored,
             normalized_seconds, completed_loops);
    return VC_NFL_COACH_REF_POSE_OK;
}

VcNflCoachRefPoseStatus vc_nfl_coach_ref_pose_sample_clamped(
    const VcNflMotionPoseClipView *clip,
    float seconds,
    bool mirrored,
    VcNflCoachRefLocalPose *pose,
    VcNflCoachRefPoseInfo *info)
{
    if (clip == NULL || pose == NULL) {
        set_info(info, VC_NFL_MOTION_POSE_SAMPLE_BAD_ARGUMENT, UINT8_MAX,
                 mirrored, seconds, 0U);
        return VC_NFL_COACH_REF_POSE_BAD_ARGUMENT;
    }
    if (clip->packed_poses_per_frame !=
        (uint8_t)VC_NFL_COACH_REF_POSE_PACKED_CHANNEL_COUNT) {
        set_info(info, VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP, 0U, mirrored,
                 seconds, 0U);
        return VC_NFL_COACH_REF_POSE_SAMPLE_FAILED;
    }
    VcNflCoachRefLocalPose candidate = {{{0.0f}}};
    for (uint8_t logical = 0U;
         logical < (uint8_t)VC_NFL_COACH_REF_POSE_CHANNEL_COUNT; ++logical) {
        const int8_t packed_index =
            vc_nfl_coach_ref_pose_shared_channel_map[
                (size_t)logical * 2U + (mirrored ? 1U : 0U)];
        if (packed_index < 0) {
            continue;
        }
        const VcNflMotionPoseSampleStatus status =
            vc_nfl_motion_pose_sample_channel_clamped(
                clip, seconds, logical,
                vc_nfl_coach_ref_pose_shared_channel_map, mirrored,
                candidate.scalar_first[logical], NULL);
        if (status != VC_NFL_MOTION_POSE_SAMPLE_OK) {
            set_info(info, status, logical, mirrored, seconds, 0U);
            return VC_NFL_COACH_REF_POSE_SAMPLE_FAILED;
        }
    }
    return finish_sampled_pose(&candidate, pose, info, mirrored, seconds, 0U);
}

VcNflCoachRefPoseStatus vc_nfl_coach_ref_pose_sample_title_policy(
    const VcNflMotionPoseClipView *clip,
    float seconds,
    VcNflCoachRefLocalPose *pose,
    VcNflCoachRefPoseInfo *info)
{
    if (clip == NULL || pose == NULL) {
        set_info(info, VC_NFL_MOTION_POSE_SAMPLE_BAD_ARGUMENT, UINT8_MAX,
                 false, seconds, 0U);
        return VC_NFL_COACH_REF_POSE_BAD_ARGUMENT;
    }
    if (clip->packed_poses_per_frame !=
        (uint8_t)VC_NFL_COACH_REF_POSE_PACKED_CHANNEL_COUNT) {
        set_info(info, VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP, 0U,
                 (clip->flags & UINT8_C(4)) != 0U, seconds, 0U);
        return VC_NFL_COACH_REF_POSE_SAMPLE_FAILED;
    }

    VcNflCoachRefLocalPose candidate = {{{0.0f}}};
    VcNflMotionPoseTitleSampleInfo first_info;
    const VcNflMotionPoseSampleStatus first_status =
        vc_nfl_motion_pose_sample_channel_title_policy(
            clip, seconds, 0U, vc_nfl_coach_ref_pose_shared_channel_map,
            candidate.scalar_first[0], &first_info);
    if (first_status != VC_NFL_MOTION_POSE_SAMPLE_OK) {
        set_info(info, first_status, 0U, (clip->flags & UINT8_C(4)) != 0U,
                 seconds, 0U);
        return VC_NFL_COACH_REF_POSE_SAMPLE_FAILED;
    }
    const bool mirrored = first_info.pose.mirrored;
    for (uint8_t logical = 1U;
         logical < (uint8_t)VC_NFL_COACH_REF_POSE_CHANNEL_COUNT; ++logical) {
        const int8_t packed_index =
            vc_nfl_coach_ref_pose_shared_channel_map[
                (size_t)logical * 2U + (mirrored ? 1U : 0U)];
        if (packed_index < 0) {
            continue;
        }
        const VcNflMotionPoseSampleStatus status =
            vc_nfl_motion_pose_sample_channel_clamped(
                clip, first_info.normalized_seconds, logical,
                vc_nfl_coach_ref_pose_shared_channel_map, mirrored,
                candidate.scalar_first[logical], NULL);
        if (status != VC_NFL_MOTION_POSE_SAMPLE_OK) {
            set_info(info, status, logical, mirrored,
                     first_info.normalized_seconds, first_info.completed_loops);
            return VC_NFL_COACH_REF_POSE_SAMPLE_FAILED;
        }
    }
    return finish_sampled_pose(
        &candidate, pose, info, mirrored, first_info.normalized_seconds,
        first_info.completed_loops);
}

void vc_nfl_coach_ref_quaternion_to_gltf_xyzw(
    const float scalar_first[4], float xyzw[4])
{
    if (scalar_first == NULL || xyzw == NULL) {
        return;
    }
    const float w = scalar_first[0];
    const float x = scalar_first[1];
    const float y = scalar_first[2];
    const float z = scalar_first[3];
    xyzw[0] = x;
    xyzw[1] = y;
    xyzw[2] = z;
    xyzw[3] = w;
}

void vc_nfl_coach_ref_pose_to_gltf_xyzw(
    const VcNflCoachRefLocalPose *pose, VcNflCoachRefGltfPose *gltf_pose)
{
    if (pose == NULL || gltf_pose == NULL) {
        return;
    }
    for (size_t channel = 0U;
         channel < VC_NFL_COACH_REF_POSE_CHANNEL_COUNT; ++channel) {
        vc_nfl_coach_ref_quaternion_to_gltf_xyzw(
            pose->scalar_first[channel], gltf_pose->xyzw[channel]);
    }
}

const char *vc_nfl_coach_ref_pose_status_name(VcNflCoachRefPoseStatus status)
{
    switch (status) {
    case VC_NFL_COACH_REF_POSE_OK: return "ok";
    case VC_NFL_COACH_REF_POSE_BAD_ARGUMENT: return "bad-argument";
    case VC_NFL_COACH_REF_POSE_SAMPLE_FAILED: return "sample-failed";
    case VC_NFL_COACH_REF_POSE_TWIST_FAILED: return "twist-failed";
    default: return "unknown";
    }
}

bool vc_nfl_coach_ref_pose_twist_is_xbox_bit_exact(void)
{
    return false;
}

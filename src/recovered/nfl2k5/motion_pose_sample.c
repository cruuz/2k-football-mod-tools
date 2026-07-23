#include "recovered/nfl2k5/motion_pose_sample.h"

#include "recovered/nfl2k5/packed_pose.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

static bool validate_clip(const VcNflMotionPoseClipView *clip)
{
    if (clip == NULL || clip->packed_frames == NULL ||
        clip->frame_count == 0U || clip->packed_poses_per_frame == 0U ||
        clip->packed_poses_per_frame > 32U || clip->sample_rate == 0U ||
        !isfinite(clip->time_scale) || !(clip->time_scale > 0.0f)) {
        return false;
    }
    const size_t count = (size_t)clip->frame_count *
                         (size_t)clip->packed_poses_per_frame;
    return count <= SIZE_MAX / 4U && clip->packed_frame_bytes >= count * 4U;
}

static const uint8_t *packed_at(const VcNflMotionPoseClipView *clip,
                                uint16_t frame,
                                uint8_t packed_index)
{
    const size_t index = (size_t)frame *
                             (size_t)clip->packed_poses_per_frame +
                         (size_t)packed_index;
    return clip->packed_frames + index * 4U;
}

VcNflMotionPoseSampleStatus
vc_nfl_motion_pose_sample_channel_clamped(
    const VcNflMotionPoseClipView *clip,
    float seconds,
    uint8_t logical_channel,
    const int8_t channel_map_pairs[64],
    bool mirrored,
    float output_lanes[4],
    VcNflMotionPoseSampleInfo *info)
{
    if (clip == NULL || output_lanes == NULL || logical_channel >= 32U) {
        return VC_NFL_MOTION_POSE_SAMPLE_BAD_ARGUMENT;
    }
    if (!validate_clip(clip)) {
        return VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP;
    }
    if (!isfinite(seconds) || seconds < 0.0f) {
        return VC_NFL_MOTION_POSE_SAMPLE_BAD_TIME;
    }

    const int8_t packed_index = channel_map_pairs == NULL
                                    ? (int8_t)logical_channel
                                    : channel_map_pairs[
                                          (size_t)logical_channel * 2U +
                                          (mirrored ? 1U : 0U)];
    if (packed_index < 0) {
        return VC_NFL_MOTION_POSE_SAMPLE_CHANNEL_DISABLED;
    }
    if ((uint8_t)packed_index >= clip->packed_poses_per_frame) {
        return VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP;
    }

    const float coordinate =
        (float)clip->sample_rate * seconds * clip->time_scale;
    if (!isfinite(coordinate) || coordinate < 0.0f) {
        return VC_NFL_MOTION_POSE_SAMPLE_BAD_TIME;
    }
    const uint16_t final_frame = (uint16_t)(clip->frame_count - 1U);
    uint16_t left_frame = final_frame;
    uint16_t right_frame = final_frame;
    float interpolation_t = 0.0f;
    if (coordinate < (float)final_frame) {
        left_frame = (uint16_t)floorf(coordinate);
        right_frame = (uint16_t)(left_frame + 1U);
        interpolation_t = coordinate - (float)left_frame;
    }

    VcNflPackedPose left;
    VcNflPackedPose right;
    if (vc_nfl_packed_pose_decode_le_portable(
            packed_at(clip, left_frame, (uint8_t)packed_index), &left) !=
            VC_NFL_PACKED_POSE_OK ||
        vc_nfl_packed_pose_decode_le_portable(
            packed_at(clip, right_frame, (uint8_t)packed_index), &right) !=
            VC_NFL_PACKED_POSE_OK) {
        return VC_NFL_MOTION_POSE_SAMPLE_PACKED_DECODE_FAILED;
    }

    float sampled[4];
    VcNflQuaternionInterpolationInfo interpolation = {
        .branch = VC_NFL_QUATERNION_INTERPOLATION_LINEAR,
        .theta_units = -1,
        .step_units = -1,
        .left_weight = 1.0f,
        .right_weight = 0.0f,
    };
    if (left_frame == right_frame) {
        memcpy(sampled, left.lanes, sizeof(sampled));
    } else if (vc_nfl_quaternion_interpolate_portable(
                   sampled, left.lanes, right.lanes, interpolation_t,
                   &interpolation) != VC_NFL_QUATERNION_INTERPOLATION_OK) {
        return VC_NFL_MOTION_POSE_SAMPLE_INTERPOLATION_FAILED;
    }

    if (mirrored) {
        VcNflPackedPose mirrored_pose = {.lanes = {
            sampled[0], sampled[1], sampled[2], sampled[3],
        }};
        vc_nfl_packed_pose_apply_mirror(&mirrored_pose);
        memcpy(sampled, mirrored_pose.lanes, sizeof(sampled));
    }
    memcpy(output_lanes, sampled, sizeof(sampled));

    if (info != NULL) {
        *info = (VcNflMotionPoseSampleInfo) {
            .frame_coordinate = coordinate,
            .interpolation_t = interpolation_t,
            .left_frame = left_frame,
            .right_frame = right_frame,
            .logical_channel = logical_channel,
            .packed_index = packed_index,
            .mirrored = mirrored,
            .interpolation = interpolation,
        };
    }
    return VC_NFL_MOTION_POSE_SAMPLE_OK;
}

VcNflMotionPoseSampleStatus
vc_nfl_motion_pose_sample_channel_title_policy(
    const VcNflMotionPoseClipView *clip,
    float seconds,
    uint8_t logical_channel,
    const int8_t channel_map_pairs[64],
    float output_lanes[4],
    VcNflMotionPoseTitleSampleInfo *info)
{
    if (clip == NULL) {
        return VC_NFL_MOTION_POSE_SAMPLE_BAD_ARGUMENT;
    }
    if (!isfinite(seconds) || seconds < 0.0f) {
        return VC_NFL_MOTION_POSE_SAMPLE_BAD_TIME;
    }

    float normalized_seconds = seconds;
    uint32_t completed_loops = 0U;
    if ((clip->flags & UINT8_C(1)) != 0U) {
        if (!isfinite(clip->duration_seconds) ||
            !(clip->duration_seconds > 0.0f)) {
            return VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP;
        }
        while (clip->duration_seconds <= normalized_seconds) {
            normalized_seconds -= clip->duration_seconds;
            if (completed_loops == UINT32_MAX) {
                return VC_NFL_MOTION_POSE_SAMPLE_BAD_TIME;
            }
            ++completed_loops;
        }
    }

    VcNflMotionPoseSampleInfo pose_info;
    const VcNflMotionPoseSampleStatus status =
        vc_nfl_motion_pose_sample_channel_clamped(
            clip, normalized_seconds, logical_channel, channel_map_pairs,
            (clip->flags & UINT8_C(4)) != 0U, output_lanes,
            info == NULL ? NULL : &pose_info);
    if (status != VC_NFL_MOTION_POSE_SAMPLE_OK) {
        return status;
    }
    if (info != NULL) {
        *info = (VcNflMotionPoseTitleSampleInfo) {
            .pose = pose_info,
            .normalized_seconds = normalized_seconds,
            .completed_loops = completed_loops,
        };
    }
    return VC_NFL_MOTION_POSE_SAMPLE_OK;
}

const char *vc_nfl_motion_pose_sample_status_name(
    VcNflMotionPoseSampleStatus status)
{
    switch (status) {
    case VC_NFL_MOTION_POSE_SAMPLE_OK: return "ok";
    case VC_NFL_MOTION_POSE_SAMPLE_BAD_ARGUMENT: return "bad-argument";
    case VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP: return "bad-clip";
    case VC_NFL_MOTION_POSE_SAMPLE_BAD_TIME: return "bad-time";
    case VC_NFL_MOTION_POSE_SAMPLE_CHANNEL_DISABLED: return "channel-disabled";
    case VC_NFL_MOTION_POSE_SAMPLE_PACKED_DECODE_FAILED: return "packed-decode-failed";
    case VC_NFL_MOTION_POSE_SAMPLE_INTERPOLATION_FAILED: return "interpolation-failed";
    default: return "unknown";
    }
}

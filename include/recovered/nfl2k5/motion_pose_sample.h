#ifndef VC_RECOVERED_NFL2K5_MOTION_POSE_SAMPLE_H
#define VC_RECOVERED_NFL2K5_MOTION_POSE_SAMPLE_H

#include "recovered/nfl2k5/quaternion_interpolation.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum VcNflMotionPoseSampleStatus {
    VC_NFL_MOTION_POSE_SAMPLE_OK = 0,
    VC_NFL_MOTION_POSE_SAMPLE_BAD_ARGUMENT = 1,
    VC_NFL_MOTION_POSE_SAMPLE_BAD_CLIP = 2,
    VC_NFL_MOTION_POSE_SAMPLE_BAD_TIME = 3,
    VC_NFL_MOTION_POSE_SAMPLE_CHANNEL_DISABLED = 4,
    VC_NFL_MOTION_POSE_SAMPLE_PACKED_DECODE_FAILED = 5,
    VC_NFL_MOTION_POSE_SAMPLE_INTERPOLATION_FAILED = 6
} VcNflMotionPoseSampleStatus;

typedef struct VcNflMotionPoseClipView {
    const uint8_t *packed_frames;
    size_t packed_frame_bytes;
    uint16_t frame_count;
    uint8_t packed_poses_per_frame;
    uint8_t sample_rate;
    float time_scale;
    uint8_t flags;
    float duration_seconds;
} VcNflMotionPoseClipView;

typedef struct VcNflMotionPoseSampleInfo {
    float frame_coordinate;
    float interpolation_t;
    uint16_t left_frame;
    uint16_t right_frame;
    uint8_t logical_channel;
    int8_t packed_index;
    bool mirrored;
    VcNflQuaternionInterpolationInfo interpolation;
} VcNflMotionPoseSampleInfo;

typedef struct VcNflMotionPoseTitleSampleInfo {
    VcNflMotionPoseSampleInfo pose;
    float normalized_seconds;
    uint32_t completed_loops;
} VcNflMotionPoseTitleSampleInfo;

/* Compose the proved NFL 2K5 paths at 0x000DF700, 0x000DF8B0,
   0x000DF9B0, 0x000DED10, and 0x003CA270 for one logical channel.

   Time is clamped to the final frame, matching 0x000DF8B0 once upstream title
   code has selected a nonnegative clip time. A null channel_map_pairs selects
   the executable identity map. Otherwise it is 32 adjacent signed-byte
   [normal, mirrored] pairs; -1 disables a channel. Mirroring selects the
   second map byte and flips numbered output lanes 2/3 after interpolation.

   Transform/rest/axis/root contracts are proved by separate modules and
   reports. PORTME: keep this leaf sampler independent of skeleton ownership
   and caller-specific external-root/loop composition. */
VcNflMotionPoseSampleStatus
vc_nfl_motion_pose_sample_channel_clamped(
    const VcNflMotionPoseClipView *clip,
    float seconds,
    uint8_t logical_channel,
    const int8_t channel_map_pairs[64],
    bool mirrored,
    float output_lanes[4],
    VcNflMotionPoseSampleInfo *info);

/* Apply the title's leaf-controller policy before sampling. Functions
   0x0031B2E0 and 0x0031B4E0 repeatedly subtract root +0x14 duration whenever
   root flag bit 0 is set and the stored time reaches/exceeds that duration.
   Without bit 0, the time reaches the low-level final-frame clamp unchanged.
   Root flag bit 2 selects the mirrored channel-map byte and output signs.

   The original uses x87 intermediate state and stores the updated controller
   time as f32. This portable implementation preserves the repeated f32
   subtraction topology but does not claim x87 bit identity. */
VcNflMotionPoseSampleStatus
vc_nfl_motion_pose_sample_channel_title_policy(
    const VcNflMotionPoseClipView *clip,
    float seconds,
    uint8_t logical_channel,
    const int8_t channel_map_pairs[64],
    float output_lanes[4],
    VcNflMotionPoseTitleSampleInfo *info);

const char *vc_nfl_motion_pose_sample_status_name(
    VcNflMotionPoseSampleStatus status);

#endif

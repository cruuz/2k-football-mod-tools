#ifndef VC_RECOVERED_NFL2K5_PLAYER_POSE_H
#define VC_RECOVERED_NFL2K5_PLAYER_POSE_H

#include "recovered/nfl2k5/motion_pose_sample.h"

#include <stdbool.h>
#include <stdint.h>

#define VC_NFL_PLAYER_POSE_CHANNEL_COUNT 25U
#define VC_NFL_PLAYER_POSE_PACKED_CHANNEL_COUNT 23U
#define VC_NFL_PLAYER_POSE_CHANNEL_MAP_BYTES 64U

typedef enum VcNflPlayerPoseChannel {
    VC_NFL_PLAYER_POSE_ROOT = 0,
    VC_NFL_PLAYER_POSE_LEFT_WRIST = 16,
    VC_NFL_PLAYER_POSE_LEFT_HAND = 17,
    VC_NFL_PLAYER_POSE_RIGHT_WRIST = 21,
    VC_NFL_PLAYER_POSE_RIGHT_HAND = 22
} VcNflPlayerPoseChannel;

typedef enum VcNflPlayerPoseSide {
    VC_NFL_PLAYER_POSE_LEFT = 0,
    VC_NFL_PLAYER_POSE_RIGHT = 1
} VcNflPlayerPoseSide;

typedef enum VcNflPlayerPoseStatus {
    VC_NFL_PLAYER_POSE_OK = 0,
    VC_NFL_PLAYER_POSE_BAD_ARGUMENT = 1,
    VC_NFL_PLAYER_POSE_SAMPLE_FAILED = 2,
    VC_NFL_PLAYER_POSE_TWIST_FAILED = 3
} VcNflPlayerPoseStatus;

typedef struct VcNflPlayerLocalPose {
    /* NFL 2K5 runtime order is scalar-first [w,x,y,z]. */
    float scalar_first[VC_NFL_PLAYER_POSE_CHANNEL_COUNT][4];
} VcNflPlayerLocalPose;

typedef struct VcNflPlayerGltfPose {
    /* glTF rotation accessor order is [x,y,z,w]. */
    float xyzw[VC_NFL_PLAYER_POSE_CHANNEL_COUNT][4];
} VcNflPlayerGltfPose;

typedef struct VcNflPlayerPoseInfo {
    VcNflMotionPoseSampleStatus sample_status;
    /* UINT8_MAX means no packed-channel failure (including twist failure). */
    uint8_t failed_logical_channel;
    bool mirrored;
    float normalized_seconds;
    uint32_t completed_loops;
} VcNflPlayerPoseInfo;

/* Exact 50 signed bytes at default.xbe:0x0051CD70 followed by the executable's
   proved fourteen-byte zero tail. */
extern const int8_t vc_nfl_player_pose_channel_map[
    VC_NFL_PLAYER_POSE_CHANNEL_MAP_BYTES];

/* Serialized transform +0x50.xyz for LO_res/lhand and LO_res/rhand. Runtime
   setup 0x00090570 copies these vectors into player twist records 1 and 2. */
extern const float vc_nfl_player_pose_hand_bind_axes[2][3];

/* Reproduce 0x00091890 -> 0x000901E0 for both disabled map slots. The full
   signed twist extracted from lhand/rhand is written to lwrist/rwrist, then
   each hand becomes conjugate(full_twist) * sampled_hand. Other slots are
   retained verbatim. The update is transactional on error. */
VcNflPlayerPoseStatus vc_nfl_player_pose_complete_disabled_channels(
    VcNflPlayerLocalPose *pose);

/* Sample all 23 enabled packed channels through the recovered composed
   sampler, then complete the two disabled wrist channels. */
VcNflPlayerPoseStatus vc_nfl_player_pose_sample_clamped(
    const VcNflMotionPoseClipView *clip,
    float seconds,
    bool mirrored,
    VcNflPlayerLocalPose *pose,
    VcNflPlayerPoseInfo *info);

/* Apply the recovered title loop/mirror policy once, sample at the resulting
   time, and complete the local player pose. */
VcNflPlayerPoseStatus vc_nfl_player_pose_sample_title_policy(
    const VcNflMotionPoseClipView *clip,
    float seconds,
    VcNflPlayerLocalPose *pose,
    VcNflPlayerPoseInfo *info);

void vc_nfl_player_quaternion_to_gltf_xyzw(
    const float scalar_first[4], float xyzw[4]);
void vc_nfl_player_pose_to_gltf_xyzw(
    const VcNflPlayerLocalPose *pose, VcNflPlayerGltfPose *gltf_pose);

const char *vc_nfl_player_pose_status_name(VcNflPlayerPoseStatus status);

/* The equations are value-equivalent portable C, not an emulator for the
   original Xbox x87/SSE reciprocal-square-root and spill behavior. */
bool vc_nfl_player_pose_twist_is_xbox_bit_exact(void);

/* PORTME: emulate 0x001C2530's x87/SSE rounding only if bit-identical Xbox
   replay becomes a requirement; this native path intentionally reports that
   it is not bit exact. */

#endif

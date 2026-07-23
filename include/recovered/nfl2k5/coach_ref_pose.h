#ifndef VC_RECOVERED_NFL2K5_COACH_REF_POSE_H
#define VC_RECOVERED_NFL2K5_COACH_REF_POSE_H

#include "recovered/nfl2k5/motion_pose_sample.h"

#include <stdbool.h>
#include <stdint.h>

#define VC_NFL_COACH_REF_POSE_CHANNEL_COUNT 25U
#define VC_NFL_COACH_REF_POSE_PACKED_CHANNEL_COUNT 21U
#define VC_NFL_COACH_REF_POSE_CHANNEL_MAP_BYTES 64U

typedef enum VcNflCoachRefPoseChannel {
    VC_NFL_COACH_REF_POSE_ROOT = 0,
    VC_NFL_COACH_REF_POSE_LEFT_HUMERUS = 14,
    VC_NFL_COACH_REF_POSE_LEFT_TWIST = 15,
    VC_NFL_COACH_REF_POSE_LEFT_WRIST = 17,
    VC_NFL_COACH_REF_POSE_RIGHT_HUMERUS = 20,
    VC_NFL_COACH_REF_POSE_RIGHT_TWIST = 21,
    VC_NFL_COACH_REF_POSE_RIGHT_WRIST = 23
} VcNflCoachRefPoseChannel;

typedef enum VcNflCoachRefPoseSide {
    VC_NFL_COACH_REF_POSE_LEFT = 0,
    VC_NFL_COACH_REF_POSE_RIGHT = 1
} VcNflCoachRefPoseSide;

typedef enum VcNflCoachRefPoseStatus {
    VC_NFL_COACH_REF_POSE_OK = 0,
    VC_NFL_COACH_REF_POSE_BAD_ARGUMENT = 1,
    VC_NFL_COACH_REF_POSE_SAMPLE_FAILED = 2,
    VC_NFL_COACH_REF_POSE_TWIST_FAILED = 3
} VcNflCoachRefPoseStatus;

typedef struct VcNflCoachRefLocalPose {
    /* NFL 2K5 runtime order is scalar-first [w,x,y,z]. */
    float scalar_first[VC_NFL_COACH_REF_POSE_CHANNEL_COUNT][4];
} VcNflCoachRefLocalPose;

typedef struct VcNflCoachRefGltfPose {
    /* glTF rotation accessor order is [x,y,z,w]. */
    float xyzw[VC_NFL_COACH_REF_POSE_CHANNEL_COUNT][4];
} VcNflCoachRefGltfPose;

typedef struct VcNflCoachRefPoseInfo {
    VcNflMotionPoseSampleStatus sample_status;
    /* UINT8_MAX means no packed-channel failure (including twist failure). */
    uint8_t failed_logical_channel;
    bool mirrored;
    float normalized_seconds;
    uint32_t completed_loops;
} VcNflCoachRefPoseInfo;

/* Exact 64 bytes at default.xbe:0x0051D010. Only entries 0..49 are read by
   this fixed 25-slot path; bytes 50..63 are the executable's zero padding. */
extern const int8_t vc_nfl_coach_ref_pose_shared_channel_map[
    VC_NFL_COACH_REF_POSE_CHANNEL_MAP_BYTES];

/* Serialized transform +0x50.xyz for ltwist and rtwist. These f32 values are
   identical in ref_high, ref_low, coachBodyGrp1, and coachLodGrp1. */
extern const float vc_nfl_coach_ref_pose_twist_bind_axes[2][3];

/* Complete the four disabled signed-map slots exactly as the active coach and
   referee callbacks do: synthesize half twists at slots 15/21 from humeri
   14/20, right-multiply each humerus by the conjugate half twist, and write
   scalar-first identity at wrists 17/23. Other slots are retained verbatim.

   The update is transactional: pose is unchanged when an error is returned. */
VcNflCoachRefPoseStatus vc_nfl_coach_ref_pose_complete_disabled_channels(
    VcNflCoachRefLocalPose *pose);

/* Sample all 21 enabled packed channels through the existing recovered
   composed sampler, then run the proved coach/referee callback above. */
VcNflCoachRefPoseStatus vc_nfl_coach_ref_pose_sample_clamped(
    const VcNflMotionPoseClipView *clip,
    float seconds,
    bool mirrored,
    VcNflCoachRefLocalPose *pose,
    VcNflCoachRefPoseInfo *info);

/* Apply the recovered title loop/mirror policy once, sample the remaining
   channels at that normalized time, and complete the local pose. */
VcNflCoachRefPoseStatus vc_nfl_coach_ref_pose_sample_title_policy(
    const VcNflMotionPoseClipView *clip,
    float seconds,
    VcNflCoachRefLocalPose *pose,
    VcNflCoachRefPoseInfo *info);

/* Retain the proved XYZ axes and reorder only [w,x,y,z] -> [x,y,z,w]. Exact
   source/destination aliasing is supported by the single-quaternion helper. */
void vc_nfl_coach_ref_quaternion_to_gltf_xyzw(
    const float scalar_first[4], float xyzw[4]);
void vc_nfl_coach_ref_pose_to_gltf_xyzw(
    const VcNflCoachRefLocalPose *pose, VcNflCoachRefGltfPose *gltf_pose);

const char *vc_nfl_coach_ref_pose_status_name(VcNflCoachRefPoseStatus status);

/* The equations are value-equivalent portable C, not an emulator for the
   original Xbox x87/SSE reciprocal-square-root and spill behavior. */
bool vc_nfl_coach_ref_pose_twist_is_xbox_bit_exact(void);

/* PORTME: emulate 0x001C2870's x87/SSE rounding only if bit-identical Xbox
   replay becomes a requirement; this native path intentionally exposes its
   non-bit-exact status instead of making a false equivalence claim. */

#endif

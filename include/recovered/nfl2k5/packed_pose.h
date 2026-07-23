#ifndef VC_RECOVERED_NFL2K5_PACKED_POSE_H
#define VC_RECOVERED_NFL2K5_PACKED_POSE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum VcNflPackedPoseStatus {
    VC_NFL_PACKED_POSE_OK = 0,
    VC_NFL_PACKED_POSE_BAD_ARGUMENT = 1,
    VC_NFL_PACKED_POSE_NEGATIVE_RADICAND = 2
} VcNflPackedPoseStatus;

typedef struct VcNflPackedPose {
    float lanes[4];
    int16_t packed_components[3];
    float ideal_radicand;
    uint8_t omitted_component;
} VcNflPackedPose;

/* Portable implementation of NFL 2K5 default.xbe:0x000DED10. The archive
   record is a little-endian uint32. Bits 30..31 select the positive component
   reconstructed from sqrt(1-dot(stored, stored)).

   PORTME at 0x000DEB00: reproduce the original Xbox x87 helper and its
   intermediate rounding when bit-exact replay is required. */
VcNflPackedPoseStatus
vc_nfl_packed_pose_decode_le_portable(const uint8_t encoded[4],
                                      VcNflPackedPose *pose);

/* Decode adjacent four-byte archive records. On failure, earlier poses are
   valid and failed_index receives the first rejected record when non-null. */
VcNflPackedPoseStatus
vc_nfl_packed_pose_decode_many_le_portable(const uint8_t *encoded,
                                           size_t pose_count,
                                           VcNflPackedPose *poses,
                                           size_t *failed_index);

/* NFL 2K5 default.xbe:0x000DF814..0x000DF821 negates numbered output lanes
   2 and 3 on the mirrored mapped-sampler path. Axis names remain deliberately
   unassigned until the transform convention is proved. */
void vc_nfl_packed_pose_apply_mirror(VcNflPackedPose *pose);

const char *vc_nfl_packed_pose_status_name(VcNflPackedPoseStatus status);
bool vc_nfl_packed_pose_decoder_is_xbox_x87_bit_exact(void);

#endif

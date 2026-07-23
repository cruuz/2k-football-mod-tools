#ifndef VC_RECOVERED_NFL2K5_TRAJECTORY_H
#define VC_RECOVERED_NFL2K5_TRAJECTORY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum VcNflTrajectoryStatus {
    VC_NFL_TRAJECTORY_OK = 0,
    VC_NFL_TRAJECTORY_BAD_ARGUMENT = 1,
    VC_NFL_TRAJECTORY_BAD_STRIDE = 2
} VcNflTrajectoryStatus;

typedef struct VcNflTrajectorySample {
    float lanes[3];
    int16_t packed_lanes[4];
    int32_t yaw_like;
    bool has_yaw_like;
} VcNflTrajectorySample;

/* Portable record decode for NFL 2K5 default.xbe:0x000DEE30. A six-byte
   record has three signed little-endian shorts; an eight-byte record adds the
   fourth integer consumed as signed_short << 3. Spatial axis names remain
   deliberately unassigned. */
VcNflTrajectoryStatus
vc_nfl_trajectory_decode_record_le(const uint8_t *encoded,
                                   size_t stride,
                                   VcNflTrajectorySample *sample);

VcNflTrajectoryStatus
vc_nfl_trajectory_decode_many_le(const uint8_t *encoded,
                                 size_t stride,
                                 size_t sample_count,
                                 VcNflTrajectorySample *samples,
                                 size_t *failed_index);

/* default.xbe:0x000DF41D..0x000DF430 mirrors numbered lane 0 and the
   yaw-like integer. PORTME: name the lane only after coordinate proof. */
void vc_nfl_trajectory_apply_mirror(VcNflTrajectorySample *sample);

const char *vc_nfl_trajectory_status_name(VcNflTrajectoryStatus status);

#endif

#ifndef VC_RECOVERED_APF2K8_PACKED_POSE_H
#define VC_RECOVERED_APF2K8_PACKED_POSE_H

#include <stdbool.h>
#include <stdint.h>

typedef enum VcApfPackedPoseStatus {
    VC_APF_PACKED_POSE_OK = 0,
    VC_APF_PACKED_POSE_BAD_ARGUMENT = 1,
    VC_APF_PACKED_POSE_NEGATIVE_RADICAND = 2
} VcApfPackedPoseStatus;

typedef struct VcApfMode0Pose {
    float lanes[4];
    int32_t packed_components[3];
    float ideal_radicand;
    uint8_t selector;
} VcApfMode0Pose;

/* Portable implementation of APF default.xex:0x84638450. It reconstructs
   the same ideal quaternion value, but sqrtf is not bit-identical to Xenon's
   vrsqrtefp plus one Newton-Raphson refinement.

   PORTME at 0x846384A8: emulate Xenon vrsqrtefp and VMX rounding when
   bit-exact replay is required. */
VcApfPackedPoseStatus
vc_apf_mode0_decode_be_portable(const uint8_t encoded[8],
                                VcApfMode0Pose *pose);

/* APF default.xex:0x8463A46C/0x8463A684 flips the float sign bit in numbered
   output lanes 2 and 3 for the mode-0 mirrored path. Axis names remain
   deliberately unassigned. */
void vc_apf_mode0_apply_mirror(VcApfMode0Pose *pose);

const char *vc_apf_packed_pose_status_name(VcApfPackedPoseStatus status);
bool vc_apf_mode0_decoder_is_xenon_bit_exact(void);

#endif

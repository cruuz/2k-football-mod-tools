#ifndef VC_RECOVERED_APF2K8_TRANSLATION_POSE_H
#define VC_RECOVERED_APF2K8_TRANSLATION_POSE_H

#include <stdbool.h>
#include <stdint.h>

#include "recovered/apf2k8/packed_pose.h"

typedef struct VcApfMode1Translation {
    /* Instruction-numbered lanes.  Lane 3 is exactly +0.0f.  Spatial axis
       names are deliberately withheld until the APF coordinate contract is
       proved. */
    float lanes[4];
    int32_t packed_components[3];
} VcApfMode1Translation;

/* Portable recovery of the mode-1 unit body in APF default.xex at
   0x8463A52C..0x8463A598.  Each big-endian 8-byte record carries three
   signed 20-bit components scaled by exactly 1/1024; the high nibble is not
   a translation component and is zero in every shipped mode-1 record. */
VcApfPackedPoseStatus
vc_apf_mode1_translation_decode_be(const uint8_t encoded[8],
                                   VcApfMode1Translation *translation);

/* APF default.xex:0x8463A594 XORs the mirror mask after interpolation.  The
   mask built at 0x8463A440..0x8463A470 changes numbered lane 0 only. */
void vc_apf_mode1_translation_apply_mirror(
    VcApfMode1Translation *translation);

/* Implements the title's value equation a + (b-a)*fraction.  Portable C is
   not claimed bit-identical to Xenon VMX multiply-add rounding. */
VcApfPackedPoseStatus
vc_apf_mode1_translation_lerp(const uint8_t encoded_a[8],
                              const uint8_t encoded_b[8],
                              float fraction,
                              bool mirror,
                              VcApfMode1Translation *translation);

bool vc_apf_mode1_translation_lerp_is_xenon_bit_exact(void);

#endif

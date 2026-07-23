#include "recovered/apf2k8/translation_pose.h"

#include <stddef.h>
#include <string.h>

static uint64_t read_be64(const uint8_t encoded[8])
{
    uint64_t value = 0;
    for (size_t index = 0; index < 8; ++index) {
        value = (value << 8) | (uint64_t)encoded[index];
    }
    return value;
}

static int32_t sign_extend_20(uint32_t value)
{
    value &= UINT32_C(0x000FFFFF);
    return (int32_t)value -
           ((value & UINT32_C(0x00080000)) != 0 ? INT32_C(0x00100000) : 0);
}

static float flip_float_sign(float value)
{
    uint32_t bits = 0;
    memcpy(&bits, &value, sizeof(bits));
    bits ^= UINT32_C(0x80000000);
    memcpy(&value, &bits, sizeof(value));
    return value;
}

VcApfPackedPoseStatus
vc_apf_mode1_translation_decode_be(const uint8_t encoded[8],
                                   VcApfMode1Translation *translation)
{
    if (encoded == NULL || translation == NULL) {
        return VC_APF_PACKED_POSE_BAD_ARGUMENT;
    }

    const uint64_t word = read_be64(encoded);
    VcApfMode1Translation decoded = {
        .packed_components = {
            sign_extend_20((uint32_t)word),
            sign_extend_20((uint32_t)(word >> 20)),
            sign_extend_20((uint32_t)(word >> 40)),
        },
    };
    for (size_t lane = 0; lane < 3; ++lane) {
        /* vslw by 12 followed by vcfsx ...,22 is exactly p / 2^10. */
        decoded.lanes[lane] = (float)decoded.packed_components[lane] /
                              1024.0f;
    }
    decoded.lanes[3] = 0.0f;
    *translation = decoded;
    return VC_APF_PACKED_POSE_OK;
}

void vc_apf_mode1_translation_apply_mirror(
    VcApfMode1Translation *translation)
{
    if (translation == NULL) {
        return;
    }
    translation->lanes[0] = flip_float_sign(translation->lanes[0]);
}

VcApfPackedPoseStatus
vc_apf_mode1_translation_lerp(const uint8_t encoded_a[8],
                              const uint8_t encoded_b[8],
                              float fraction,
                              bool mirror,
                              VcApfMode1Translation *translation)
{
    if (translation == NULL) {
        return VC_APF_PACKED_POSE_BAD_ARGUMENT;
    }
    VcApfMode1Translation a;
    VcApfMode1Translation b;
    VcApfPackedPoseStatus status =
        vc_apf_mode1_translation_decode_be(encoded_a, &a);
    if (status != VC_APF_PACKED_POSE_OK) {
        return status;
    }
    status = vc_apf_mode1_translation_decode_be(encoded_b, &b);
    if (status != VC_APF_PACKED_POSE_OK) {
        return status;
    }

    VcApfMode1Translation result = a;
    for (size_t lane = 0; lane < 4; ++lane) {
        result.lanes[lane] =
            a.lanes[lane] + (b.lanes[lane] - a.lanes[lane]) * fraction;
    }
    if (mirror) {
        vc_apf_mode1_translation_apply_mirror(&result);
    }
    *translation = result;
    return VC_APF_PACKED_POSE_OK;
}

bool vc_apf_mode1_translation_lerp_is_xenon_bit_exact(void)
{
    return false;
}

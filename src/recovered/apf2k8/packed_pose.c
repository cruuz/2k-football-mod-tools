#include "recovered/apf2k8/packed_pose.h"

#include <math.h>
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
vc_apf_mode0_decode_be_portable(const uint8_t encoded[8],
                                VcApfMode0Pose *pose)
{
    if (encoded == NULL || pose == NULL) {
        return VC_APF_PACKED_POSE_BAD_ARGUMENT;
    }

    const uint64_t word = read_be64(encoded);
    const uint8_t selector = (uint8_t)((word >> 60) & UINT64_C(0xF));

    const int32_t packed[3] = {
        sign_extend_20((uint32_t)word),
        sign_extend_20((uint32_t)(word >> 20)),
        sign_extend_20((uint32_t)(word >> 40)),
    };
    const float scale = 23.0f / 16777216.0f;
    const float component0 = (float)packed[0] * scale;
    const float component1 = (float)packed[1] * scale;
    const float component2 = (float)packed[2] * scale;
    const float radicand =
        1.0f - (component0 * component0 + component1 * component1 +
                component2 * component2);
    if (!(radicand >= 0.0f) || !isfinite(radicand)) {
        return VC_APF_PACKED_POSE_NEGATIVE_RADICAND;
    }

    const float stored[4] = {
        component0,
        component1,
        component2,
        sqrtf(radicand),
    };
    VcApfMode0Pose decoded = {
        .packed_components = {packed[0], packed[1], packed[2]},
        .ideal_radicand = radicand,
        .selector = selector,
    };
    const size_t rotation = (size_t)(selector & 3U);
    for (size_t lane = 0; lane < 4; ++lane) {
        decoded.lanes[lane] = stored[(lane + rotation) & 3U];
    }
    *pose = decoded;
    return VC_APF_PACKED_POSE_OK;
}

void vc_apf_mode0_apply_mirror(VcApfMode0Pose *pose)
{
    if (pose == NULL) {
        return;
    }
    pose->lanes[2] = flip_float_sign(pose->lanes[2]);
    pose->lanes[3] = flip_float_sign(pose->lanes[3]);
}

const char *vc_apf_packed_pose_status_name(VcApfPackedPoseStatus status)
{
    switch (status) {
    case VC_APF_PACKED_POSE_OK: return "ok";
    case VC_APF_PACKED_POSE_BAD_ARGUMENT: return "bad-argument";
    case VC_APF_PACKED_POSE_NEGATIVE_RADICAND: return "negative-radicand";
    default: return "unknown";
    }
}

bool vc_apf_mode0_decoder_is_xenon_bit_exact(void)
{
    return false;
}

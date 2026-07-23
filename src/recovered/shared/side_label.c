#include "recovered/shared/side_label.h"

uint32_t vc_side_code_nfl2k5(uint32_t packed_field)
{
    return packed_field & UINT32_C(0x1f);
}

uint32_t vc_side_code_apf2k8(uint32_t packed_field)
{
    return packed_field >> 27U;
}

const char *vc_side_label(uint32_t normalized_code)
{
    switch (normalized_code) {
    case 1U:
    case 2U:
        return "left side";
    case 3U:
    case 4U:
    case 5U:
    case 6U:
        return "up middle";
    case 7U:
    case 8U:
        return "right side";
    default:
        return "unknown";
    }
}

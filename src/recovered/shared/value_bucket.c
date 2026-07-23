#include "recovered/shared/value_bucket.h"

uint32_t vc_signed_position_bucket(int32_t value)
{
    if (value < -11) {
        return 0U;
    }
    if (value < 11) {
        return 1U;
    }
    return 2U;
}

uint32_t vc_paired_code_bucket(uint32_t value)
{
    switch (value) {
    case 3U:
    case 4U:
        return 1U;
    case 5U:
    case 6U:
        return 2U;
    case 7U:
    case 8U:
        return 3U;
    default:
        return 0U;
    }
}

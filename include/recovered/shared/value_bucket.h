#ifndef VC_RECOVERED_SHARED_VALUE_BUCKET_H
#define VC_RECOVERED_SHARED_VALUE_BUCKET_H

#include <stdint.h>

/* NFL 2K5 0x001EC750 / APF 2K8 0x84960538. */
uint32_t vc_signed_position_bucket(int32_t value);

/* NFL 2K5 0x001EC770 / APF 2K8 0x84960588. */
uint32_t vc_paired_code_bucket(uint32_t value);

#endif

#ifndef VC_RECOVERED_SHARED_SIDE_LABEL_H
#define VC_RECOVERED_SHARED_SIDE_LABEL_H

#include <stdint.h>

/*
 * Normalized recovery of NFL 2K5 0x000BB8D0 and APF 2K8 0x848A4DB8.
 * The title adapters accept the packed u32 stored at object offset +0x10.
 */
uint32_t vc_side_code_nfl2k5(uint32_t packed_field);
uint32_t vc_side_code_apf2k8(uint32_t packed_field);
const char *vc_side_label(uint32_t normalized_code);

#endif

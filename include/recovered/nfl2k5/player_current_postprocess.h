#ifndef VC_RECOVERED_NFL2K5_PLAYER_CURRENT_POSTPROCESS_H
#define VC_RECOVERED_NFL2K5_PLAYER_CURRENT_POSTPROCESS_H

#include <stdbool.h>
#include <stdint.h>

#define VC_NFL_PLAYER_LOW_MATRIX_COUNT 25u
#define VC_NFL_PLAYER_HIGH_MATRIX_COUNT 62u
#define VC_NFL_PLAYER_SCALE_PROFILE_COUNT 4u

typedef enum VcNflPlayerCurrentPostprocessStatus {
    VC_NFL_PLAYER_CURRENT_POSTPROCESS_OK = 0,
    VC_NFL_PLAYER_CURRENT_POSTPROCESS_BAD_ARGUMENT = 1,
    VC_NFL_PLAYER_CURRENT_POSTPROCESS_BAD_SCHEDULE = 2
} VcNflPlayerCurrentPostprocessStatus;

typedef struct VcNflPlayerScaleProfile {
    float reference;
    float multiplier;
    float lower[VC_NFL_PLAYER_LOW_MATRIX_COUNT];
    float upper[VC_NFL_PLAYER_LOW_MATRIX_COUNT];
} VcNflPlayerScaleProfile;

typedef struct VcNflPlayerScaleTables {
    VcNflPlayerScaleProfile profiles[VC_NFL_PLAYER_SCALE_PROFILE_COUNT];
    uint8_t high_source[VC_NFL_PLAYER_HIGH_MATRIX_COUNT];
} VcNflPlayerScaleTables;

typedef struct VcNflPlayerCurrentMatrices {
    float low[VC_NFL_PLAYER_LOW_MATRIX_COUNT][16];
    float high[VC_NFL_PLAYER_HIGH_MATRIX_COUNT][16];
} VcNflPlayerCurrentMatrices;

/* Portable semantic subset of NFL 2K5 function 0x00093850.

   player_field_18 and player_field_2a are intentionally offset labels: no
   independent object-schema evidence yet proves human-facing field names.
   The function selects profile ((player_field_18 >> 3) & 3), derives the
   scalar float(player_field_2a + 150), and applies the exact 25/62 loop and
   mask topology documented in nfl_player_postprocess.json.

   skeleton_vectors points to 25 contiguous four-float records (100 floats)
   in exact shipped SKEL/LO_res channel order.

   Matrices are row-major and use the title's row-vector convention. The low
   loop computes axial_scale * low[i]. The high loop computes
   high[j] * (T(-p) * axial_scale * T(p)), where p is high[j]'s translation.

   PORTME: the original 0x00091AC0 normalization uses the Xbox SSE rsqrt seed
   refined by one Newton step. This implementation uses sqrtf and therefore
   claims value-level portability, not bit identity for arbitrary inputs.
   PORTME: preserve the original x87 store boundaries if a bit-exact replay
   oracle becomes available. */
VcNflPlayerCurrentPostprocessStatus vc_nfl_player_current_postprocess(
    uint32_t player_field_18,
    uint8_t player_field_2a,
    uint32_t update_mask,
    bool special_global_nonzero,
    const float *skeleton_vectors,
    const VcNflPlayerScaleTables *tables,
    VcNflPlayerCurrentMatrices *matrices);

const char *vc_nfl_player_current_postprocess_status_name(
    VcNflPlayerCurrentPostprocessStatus status);

#endif

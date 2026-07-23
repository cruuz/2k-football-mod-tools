#ifndef VC_RECOVERED_NFL2K5_FORMATTED_TOKEN_H
#define VC_RECOVERED_NFL2K5_FORMATTED_TOKEN_H

#include <stddef.h>
#include <stdint.h>

typedef struct VcNflFormattedToken {
    const char *name;
    uint32_t texture_slot;
    float u0;
    float v0;
    float u1;
    float v1;
    float height_scale;
    float width_over_height;
    uint32_t flags;
} VcNflFormattedToken;

size_t vc_nfl_formatted_token_count(void);
const VcNflFormattedToken *vc_nfl_formatted_token_at(size_t index);

/* Mirrors the bounded, ASCII-token portion of XBE helper 0x000EEF80. The
 * match is case-insensitive for a-z exactly like 0x00030BE0. On success,
 * consumed receives the complete |TOKEN| byte count and the return value is
 * the 0-based serialized table index. */
int vc_nfl_formatted_token_match_ascii(const char *text, size_t *consumed);

/* Mirrors 0x000EEF60 and 0x000EEF30 through CVTTSS2SI at 0x000EE8F0 for
 * finite, non-negative host values. */
int vc_nfl_formatted_token_height(const VcNflFormattedToken *token,
                                  float font_height);
int vc_nfl_formatted_token_width(const VcNflFormattedToken *token,
                                 float font_height);

#endif

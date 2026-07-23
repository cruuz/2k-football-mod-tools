#include "recovered/nfl2k5/formatted_token.h"

#include <limits.h>
#include <math.h>
#include <string.h>

static const VcNflFormattedToken tokens[] = {
    {"CROSS", 0, 0.0f, 0.0f, 0.25f, 0.25f, 1.5f, 1.0f, 0},
    {"TRIANGLE", 0, 0.25f, 0.0f, 0.5f, 0.25f, 1.5f, 1.0f, 0},
    {"SQUARE", 0, 0.5f, 0.0f, 0.75f, 0.25f, 1.5f, 1.0f, 0},
    {"CIRCLE", 0, 0.75f, 0.0f, 1.0f, 0.25f, 1.5f, 1.0f, 0},
    {"START", 0, 0.0f, 0.25f, 0.25f, 0.5f, 1.5f, 1.0f, 0},
    {"SELECT", 0, 0.25f, 0.25f, 0.5f, 0.5f, 1.5f, 1.0f, 0},
    {"ANALOG", 0, 0.5f, 0.25f, 0.75f, 0.5f, 1.5f, 1.0f, 0},
    {"WARNING", 0, 0.75f, 0.25f, 1.0f, 0.5f, 1.5f, 1.0f, 0},
    {"L1", 0, 0.0f, 0.5f, 0.25f, 0.75f, 1.5f, 1.0f, 0},
    {"R1", 0, 0.25f, 0.5f, 0.5f, 0.75f, 1.5f, 1.0f, 0},
    {"L2", 0, 0.5f, 0.5f, 0.75f, 0.75f, 1.5f, 1.0f, 0},
    {"R2", 0, 0.75f, 0.5f, 1.0f, 0.75f, 1.5f, 1.0f, 0},
    {"DPAD", 0, 0.0f, 0.75f, 0.25f, 1.0f, 1.5f, 1.0f, 0},
    {"L3", 0, 0.25f, 0.75f, 0.5f, 1.0f, 1.5f, 1.0f, 0},
    {"R3", 0, 0.5f, 0.75f, 0.75f, 1.0f, 1.5f, 1.0f, 0},
    {"RANALOG", 0, 0x1.83fe5cp-1f, 0.75f, 1.0f, 1.0f, 1.5f, 1.0f, 0},
    {"LANALOGUP", 1, 0.0f, 0.0f, 0.25f, 0.25f, 1.5f, 1.0f, 0},
    {"LANALOGDOWN", 1, 0.25f, 0.0f, 0.5f, 0.25f, 1.5f, 1.0f, 0},
    {"LANALOGLEFT", 1, 0.0f, 0.25f, 0.25f, 0.5f, 1.5f, 1.0f, 0},
    {"LANALOGRIGHT", 1, 0.25f, 0.25f, 0.5f, 0.5f, 1.5f, 1.0f, 0},
    {"RANALOGUP", 1, 0.5f, 0.0f, 0.75f, 0.25f, 1.5f, 1.0f, 0},
    {"RANALOGDOWN", 1, 0.75f, 0.0f, 1.0f, 0.25f, 1.5f, 1.0f, 0},
    {"RANALOGLEFT", 1, 0.5f, 0.25f, 0.75f, 0.5f, 1.5f, 1.0f, 0},
    {"RANALOGRIGHT", 1, 0.75f, 0.25f, 1.0f, 0.5f, 1.5f, 1.0f, 0},
    {"RANALOGUPLEFT", 1, 0.5f, 0.5f, 0.75f, 0.75f, 1.5f, 1.0f, 0},
    {"RANALOGUPRIGHT", 1, 0.75f, 0.5f, 1.0f, 0.75f, 1.5f, 1.0f, 0},
    {"RANALOGDOWNLEFT", 1, 0.5f, 0.75f, 0.75f, 1.0f, 1.5f, 1.0f, 0},
    {"RANALOGDOWNRIGHT", 1, 0.75f, 0.75f, 1.0f, 1.0f, 1.5f, 1.0f, 0},
    {"DPADUP", 1, 0.0f, 0.5f, 0.25f, 0.75f, 1.5f, 1.0f, 0},
    {"DPADDOWN", 1, 0.25f, 0.5f, 0.5f, 0.75f, 1.5f, 1.0f, 0},
    {"DPADLEFT", 1, 0.0f, 0.75f, 0.25f, 1.0f, 1.5f, 1.0f, 0},
    {"DPADRIGHT", 1, 0.25f, 0.75f, 0.5f, 1.0f, 1.5f, 1.0f, 0},
    {"COMBRED", 2, 0.0f, 0.0f, 1.0f, 1.0f, 1.0f, 1.0f, 0},
    {"COMBGREEN", 3, 0.0f, 0.0f, 1.0f, 1.0f, 1.0f, 1.0f, 0},
    {"COMBYELLOW", 4, 0.0f, 0.0f, 1.0f, 1.0f, 1.0f, 2.0f, 0},
    {"DRAFTUP", 5, 0.0f, 0.0f, 1.0f, 1.0f, 1.0f, 1.0f, 0},
    {"DRAFTRIGHT", 6, 0.0f, 0.0f, 1.0f, 1.0f, 1.0f, 1.0f, 0},
    {"DRAFTLEFT", 7, 0.0f, 0.0f, 1.0f, 1.0f, 1.0f, 1.0f, 0},
    {"DRAFTDOWN", 8, 0.0f, 0.0f, 1.0f, 1.0f, 1.0f, 1.0f, 0},
    {"REG", 11, 0.0f, 0.0f, 1.0f, 1.0f, 0.8f, 1.0f, 1},
    {"TM", 9, 0.0f, 0.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1},
    {"BULLET", 10, 0.0f, 0.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1},
    {"BOX", 12, 0.0f, 0.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1},
    {"M_HELP", 0, 0.5f, 0.0f, 0.75f, 0.25f, 1.5f, 1.0f, 0},
    {"M_BACK", 0, 0.75f, 0.0f, 1.0f, 0.25f, 1.5f, 1.0f, 0},
    {"M_PRIMARY", 0, 0.0f, 0.0f, 0.25f, 0.25f, 1.5f, 1.0f, 0},
    {"M_SECONDARY", 0, 0.25f, 0.0f, 0.5f, 0.25f, 1.5f, 1.0f, 0},
    {"M_LINK", 0, 0.5f, 0.75f, 0.75f, 1.0f, 1.5f, 1.0f, 0},
    {"M_ADVANCE", 0, 0.0f, 0.25f, 0.25f, 0.5f, 1.5f, 1.0f, 0},
    {"M_NEXTPAGE", 0, 0.25f, 0.5f, 0.5f, 0.75f, 1.5f, 1.0f, 0},
    {"M_PREVPAGE", 0, 0.0f, 0.5f, 0.25f, 0.75f, 1.5f, 1.0f, 0},
    {"M_NEXTSUBPAGE", 0, 0.75f, 0.5f, 1.0f, 0.75f, 1.5f, 1.0f, 0},
    {"M_PREVSUBPAGE", 0, 0.5f, 0.5f, 0.75f, 0.75f, 1.5f, 1.0f, 0},
    {"M_LEFTANALOG", 0, 0.5f, 0.25f, 0.75f, 0.5f, 1.5f, 1.0f, 0},
    {"M_RIGHTANALOG", 0, 0.75f, 0.75f, 1.0f, 1.0f, 1.5f, 1.0f, 0},
    {"M_LEFTSTICK", 0, 0.25f, 0.75f, 0.5f, 1.0f, 1.5f, 1.0f, 0},
    {"M_RIGHTSTICK", 0, 0.5f, 0.75f, 0.75f, 1.0f, 1.5f, 1.0f, 0},
};

size_t vc_nfl_formatted_token_count(void)
{
    return sizeof(tokens) / sizeof(tokens[0]);
}

const VcNflFormattedToken *vc_nfl_formatted_token_at(size_t index)
{
    return index < vc_nfl_formatted_token_count() ? &tokens[index] : NULL;
}

static unsigned char ascii_upper(unsigned char value)
{
    return value >= (unsigned char)'a' && value <= (unsigned char)'z'
               ? (unsigned char)(value - (unsigned char)'a' +
                                 (unsigned char)'A')
               : value;
}

int vc_nfl_formatted_token_match_ascii(const char *text, size_t *consumed)
{
    if (consumed != NULL) {
        *consumed = 0U;
    }
    if (text == NULL || text[0] != '|') {
        return -1;
    }
    for (size_t index = 0U; index < vc_nfl_formatted_token_count(); ++index) {
        const size_t length = strlen(tokens[index].name);
        size_t offset = 0U;
        while (offset < length && text[offset + 1U] != '\0' &&
               ascii_upper((unsigned char)text[offset + 1U]) ==
                   (unsigned char)tokens[index].name[offset]) {
            ++offset;
        }
        if (offset == length && text[length + 1U] == '|') {
            if (consumed != NULL) {
                *consumed = length + 2U;
            }
            return (int)index;
        }
    }
    return -1;
}

static int checked_truncate(float value)
{
    /* PORTME(0x000EE8F0): CVTTSS2SI returns 0x80000000 for NaN/out-of-range;
       the native seam rejects those host-only inputs instead of exposing an
       ambiguous sentinel as a drawable size. Shipped token metrics are all
       finite and positive. */
    if (!isfinite(value) || value < 0.0f || value >= 2147483648.0f) {
        return 0;
    }
    return (int)value;
}

int vc_nfl_formatted_token_height(const VcNflFormattedToken *token,
                                  float font_height)
{
    if (token == NULL || !isfinite(font_height) || font_height < 0.0f) {
        return 0;
    }
    const float value = token->height_scale * font_height;
    return checked_truncate(value);
}

int vc_nfl_formatted_token_width(const VcNflFormattedToken *token,
                                 float font_height)
{
    if (token == NULL || !isfinite(font_height) || font_height < 0.0f) {
        return 0;
    }
    const float value =
        token->height_scale * font_height * token->width_over_height;
    return checked_truncate(value);
}

#include "port/bitmap_font_metrics.h"

#include <errno.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void set_error(char *error, size_t capacity, const char *format, ...)
{
    if (error == NULL || capacity == 0U) {
        return;
    }
    va_list arguments;
    va_start(arguments, format);
    (void)vsnprintf(error, capacity, format, arguments);
    va_end(arguments);
}

static bool parse_int(const char *text, int base, int *value)
{
    if (text == NULL || text[0] == '\0' || value == NULL) {
        return false;
    }
    errno = 0;
    char *end = NULL;
    const long parsed = strtol(text, &end, base);
    if (errno == ERANGE || end == text || *end != '\0' ||
        parsed < INT_MIN || parsed > INT_MAX) {
        return false;
    }
    *value = (int)parsed;
    return true;
}

static bool parse_codepoint(const char *text, uint32_t *value)
{
    if (text == NULL || text[0] == '\0' || value == NULL ||
        text[0] == '-') {
        return false;
    }
    errno = 0;
    char *end = NULL;
    const unsigned long parsed = strtoul(text, &end, 0);
    if (errno == ERANGE || end == text || *end != '\0' ||
        parsed > UINT32_C(0x10FFFF)) {
        return false;
    }
    *value = (uint32_t)parsed;
    return true;
}

static size_t split_tabs(char *line, char **fields, size_t capacity)
{
    size_t count = 0U;
    char *cursor = line;
    for (;;) {
        if (count >= capacity) {
            return capacity + 1U;
        }
        fields[count++] = cursor;
        char *tab = strchr(cursor, '\t');
        if (tab == NULL) {
            return count;
        }
        *tab = '\0';
        cursor = tab + 1;
    }
}

static bool parse_glyph(char *line, VcBitmapGlyph *glyph)
{
    char *fields[10];
    const size_t count = split_tabs(line, fields, 10U);
    return count == 10U &&
           parse_codepoint(fields[0], &glyph->codepoint) &&
           parse_int(fields[1], 10, &glyph->advance) &&
           parse_int(fields[2], 10, &glyph->left) &&
           parse_int(fields[3], 10, &glyph->top) &&
           parse_int(fields[4], 10, &glyph->right) &&
           parse_int(fields[5], 10, &glyph->bottom) &&
           parse_int(fields[6], 10, &glyph->atlas_left) &&
           parse_int(fields[7], 10, &glyph->atlas_top) &&
           parse_int(fields[8], 10, &glyph->atlas_right) &&
           parse_int(fields[9], 10, &glyph->atlas_bottom);
}

static bool parse_metadata(char *line, const char *name, int *value)
{
    const size_t length = strlen(name);
    return strncmp(line, name, length) == 0 && line[length] == '=' &&
           parse_int(line + length + 1U, 10, value);
}

static bool validate_metrics(VcBitmapFontMetrics *metrics, char *error,
                             size_t error_capacity)
{
    if (metrics->atlas_width <= 0 || metrics->atlas_width > 16384 ||
        metrics->atlas_height <= 0 || metrics->atlas_height > 16384 ||
        metrics->line_advance <= 0 || metrics->space_advance <= 0) {
        set_error(error, error_capacity,
                  "invalid atlas or advance metadata");
        return false;
    }
    if (metrics->glyph_count == 0U) {
        set_error(error, error_capacity, "metrics contain no glyphs");
        return false;
    }
    bool has_fallback = false;
    for (size_t index = 0U; index < metrics->glyph_count; ++index) {
        const VcBitmapGlyph *glyph = &metrics->glyphs[index];
        if (index > 0U &&
            glyph->codepoint <= metrics->glyphs[index - 1U].codepoint) {
            set_error(error, error_capacity,
                      "glyph codepoints are not strictly increasing at row %zu",
                      index + 1U);
            return false;
        }
        if (glyph->advance <= 0 || glyph->right <= glyph->left ||
            glyph->bottom <= glyph->top || glyph->atlas_left < 0 ||
            glyph->atlas_top < 0 ||
            glyph->atlas_right > metrics->atlas_width ||
            glyph->atlas_bottom > metrics->atlas_height ||
            glyph->atlas_right <= glyph->atlas_left ||
            glyph->atlas_bottom <= glyph->atlas_top) {
            set_error(error, error_capacity,
                      "invalid geometry for U+%04X", glyph->codepoint);
            return false;
        }
        if (glyph->right - glyph->left !=
                glyph->atlas_right - glyph->atlas_left ||
            glyph->bottom - glyph->top !=
                glyph->atlas_bottom - glyph->atlas_top) {
            set_error(error, error_capacity,
                      "quad/atlas span mismatch for U+%04X",
                      glyph->codepoint);
            return false;
        }
        has_fallback = has_fallback || glyph->codepoint == (uint32_t)'?';
    }
    if (!has_fallback) {
        set_error(error, error_capacity,
                  "metrics must contain the '?' fallback glyph");
        return false;
    }
    metrics->minimum_codepoint = metrics->glyphs[0].codepoint;
    metrics->maximum_codepoint =
        metrics->glyphs[metrics->glyph_count - 1U].codepoint;
    return true;
}

bool vc_bitmap_font_metrics_load(VcBitmapFontMetrics *metrics,
                                 const char *path, char *error,
                                 size_t error_capacity)
{
    if (error != NULL && error_capacity > 0U) {
        error[0] = '\0';
    }
    if (metrics == NULL || path == NULL || path[0] == '\0') {
        set_error(error, error_capacity, "invalid metrics arguments");
        return false;
    }
    FILE *stream = fopen(path, "rb");
    if (stream == NULL) {
        set_error(error, error_capacity, "could not open %s", path);
        return false;
    }

    VcBitmapFontMetrics candidate;
    memset(&candidate, 0, sizeof(candidate));
    bool schema_seen = false;
    bool representation_seen = false;
    bool header_seen = false;
    unsigned long line_number = 0UL;
    char line[512];
    while (fgets(line, sizeof(line), stream) != NULL) {
        ++line_number;
        const size_t length = strlen(line);
        if (length == sizeof(line) - 1U && line[length - 1U] != '\n' &&
            !feof(stream)) {
            set_error(error, error_capacity, "line %lu is too long",
                      line_number);
            fclose(stream);
            return false;
        }
        line[strcspn(line, "\r\n")] = '\0';
        if (line[0] == '\0') {
            continue;
        }
        if (line[0] == '#') {
            schema_seen = schema_seen ||
                strcmp(line, "# schema=" VC_BITMAP_FONT_METRICS_SCHEMA) == 0;
            representation_seen = representation_seen ||
                strcmp(line,
                       "# representation=recovered_host_representation") == 0;
            continue;
        }
        if (strcmp(line,
                   "codepoint\tadvance\tleft\ttop\tright\tbottom\t"
                   "atlas_left\tatlas_top\tatlas_right\tatlas_bottom") == 0) {
            header_seen = true;
            continue;
        }
        if (parse_metadata(line, "atlas_width", &candidate.atlas_width) ||
            parse_metadata(line, "atlas_height", &candidate.atlas_height) ||
            parse_metadata(line, "line_advance", &candidate.line_advance) ||
            parse_metadata(line, "space_advance", &candidate.space_advance)) {
            continue;
        }
        if (!header_seen) {
            set_error(error, error_capacity,
                      "line %lu appears before the glyph header", line_number);
            fclose(stream);
            return false;
        }
        if (candidate.glyph_count >= VC_BITMAP_FONT_MAX_GLYPHS ||
            !parse_glyph(line, &candidate.glyphs[candidate.glyph_count])) {
            set_error(error, error_capacity,
                      "invalid glyph row at line %lu", line_number);
            fclose(stream);
            return false;
        }
        ++candidate.glyph_count;
    }
    const bool read_ok = !ferror(stream);
    fclose(stream);
    if (!read_ok) {
        set_error(error, error_capacity, "could not read %s", path);
        return false;
    }
    if (!schema_seen || !representation_seen || !header_seen) {
        set_error(error, error_capacity,
                  "missing schema, representation boundary, or glyph header");
        return false;
    }
    if (!validate_metrics(&candidate, error, error_capacity)) {
        return false;
    }
    *metrics = candidate;
    return true;
}

const VcBitmapGlyph *vc_bitmap_font_glyph(
    const VcBitmapFontMetrics *metrics, uint32_t codepoint)
{
    if (metrics == NULL || metrics->glyph_count == 0U) {
        return NULL;
    }
    size_t first = 0U;
    size_t after_last = metrics->glyph_count;
    while (first < after_last) {
        const size_t middle = first + (after_last - first) / 2U;
        if (metrics->glyphs[middle].codepoint < codepoint) {
            first = middle + 1U;
        } else {
            after_last = middle;
        }
    }
    return first < metrics->glyph_count &&
                   metrics->glyphs[first].codepoint == codepoint
               ? &metrics->glyphs[first]
               : NULL;
}

float vc_bitmap_font_measure_ascii(const VcBitmapFontMetrics *metrics,
                                   const char *text, float scale)
{
    if (metrics == NULL || text == NULL || scale <= 0.0f) {
        return 0.0f;
    }
    const VcBitmapGlyph *fallback =
        vc_bitmap_font_glyph(metrics, (uint32_t)'?');
    float line_width = 0.0f;
    float maximum_width = 0.0f;
    for (const unsigned char *cursor = (const unsigned char *)text;
         *cursor != 0U; ++cursor) {
        if (*cursor == (unsigned char)'\n') {
            if (line_width > maximum_width) {
                maximum_width = line_width;
            }
            line_width = 0.0f;
        } else if (*cursor == (unsigned char)' ') {
            line_width += (float)metrics->space_advance * scale;
        } else if (*cursor == (unsigned char)'\t') {
            line_width += (float)(metrics->space_advance * 4) * scale;
        } else {
            const VcBitmapGlyph *glyph =
                vc_bitmap_font_glyph(metrics, (uint32_t)*cursor);
            if (glyph == NULL) {
                glyph = fallback;
            }
            if (glyph != NULL) {
                line_width += (float)glyph->advance * scale;
            }
        }
    }
    return line_width > maximum_width ? line_width : maximum_width;
}

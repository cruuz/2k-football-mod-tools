#include "port/png_texture.h"

#include <png.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static bool load_png_rgba(const char *path, unsigned char **pixels_out,
                          int *width_out, int *height_out)
{
    static const size_t max_decoded_bytes = 256U * 1024U * 1024U;
    if (path == NULL || pixels_out == NULL || width_out == NULL ||
        height_out == NULL) {
        return false;
    }
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        return false;
    }

    unsigned char signature[8];
    if (fread(signature, 1, sizeof(signature), file) != sizeof(signature) ||
        png_sig_cmp(signature, 0, sizeof(signature)) != 0) {
        fclose(file);
        return false;
    }

    png_structp png = png_create_read_struct(PNG_LIBPNG_VER_STRING, NULL, NULL,
                                             NULL);
    png_infop info = png != NULL ? png_create_info_struct(png) : NULL;
    if (png == NULL || info == NULL) {
        png_destroy_read_struct(&png, &info, NULL);
        fclose(file);
        return false;
    }

    /* libpng reports errors with longjmp. These locals must be volatile so
       their post-allocation values remain defined in the cleanup branch. */
    unsigned char *volatile pixels = NULL;
    png_bytep *volatile rows = NULL;
    if (setjmp(png_jmpbuf(png)) != 0) {
        free(rows);
        free(pixels);
        png_destroy_read_struct(&png, &info, NULL);
        fclose(file);
        return false;
    }

    png_init_io(png, file);
    png_set_sig_bytes(png, (int)sizeof(signature));
    png_read_info(png, info);

    png_uint_32 width = png_get_image_width(png, info);
    png_uint_32 height = png_get_image_height(png, info);
    const int color_type = png_get_color_type(png, info);
    const int bit_depth = png_get_bit_depth(png, info);

    if (bit_depth == 16) {
        png_set_strip_16(png);
    }
    if (color_type == PNG_COLOR_TYPE_PALETTE) {
        png_set_palette_to_rgb(png);
    }
    if (color_type == PNG_COLOR_TYPE_GRAY && bit_depth < 8) {
        png_set_expand_gray_1_2_4_to_8(png);
    }
    const bool has_transparency =
        png_get_valid(png, info, PNG_INFO_tRNS) != 0;
    if (has_transparency) {
        png_set_tRNS_to_alpha(png);
    }
    if (color_type == PNG_COLOR_TYPE_GRAY ||
        color_type == PNG_COLOR_TYPE_GRAY_ALPHA) {
        png_set_gray_to_rgb(png);
    }
    if ((color_type & PNG_COLOR_MASK_ALPHA) == 0 && !has_transparency) {
        png_set_add_alpha(png, 0xff, PNG_FILLER_AFTER);
    }

    (void)png_set_interlace_handling(png);
    png_read_update_info(png, info);
    const png_size_t row_bytes = png_get_rowbytes(png, info);
    const size_t expected_row_bytes = (size_t)width * 4U;
    if (width == 0 || height == 0 || width > 16384 || height > 16384 ||
        row_bytes != expected_row_bytes ||
        expected_row_bytes > max_decoded_bytes / (size_t)height) {
        png_error(png, "unsupported PNG dimensions");
    }

    pixels = malloc(expected_row_bytes * (size_t)height);
    rows = malloc(sizeof(*rows) * (size_t)height);
    if (pixels == NULL || rows == NULL) {
        png_error(png, "out of memory");
    }
    for (png_uint_32 y = 0; y < height; ++y) {
        rows[y] = pixels + y * row_bytes;
    }
    png_read_image(png, rows);
    png_read_end(png, NULL);

    free(rows);
    png_destroy_read_struct(&png, &info, NULL);
    fclose(file);

    *pixels_out = (unsigned char *)pixels;
    *width_out = (int)width;
    *height_out = (int)height;
    return true;
}

bool vc_png_texture_load(VcPngTexture *texture, const char *path)
{
    if (texture == NULL || path == NULL ||
        strlen(path) >= sizeof(texture->source_path)) {
        return false;
    }

    unsigned char *pixels = NULL;
    int width = 0;
    int height = 0;
    if (!load_png_rgba(path, &pixels, &width, &height)) {
        fprintf(stderr, "texture: could not load PNG %s\n", path);
        return false;
    }

    GLuint id = 0;
    glGenTextures(1, &id);
    if (id == 0) {
        free(pixels);
        fprintf(stderr, "texture: OpenGL could not allocate %s\n", path);
        return false;
    }
    while (glGetError() != GL_NO_ERROR) {
    }
    glBindTexture(GL_TEXTURE_2D, id);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_SRGB8_ALPHA8, width, height, 0, GL_RGBA,
                 GL_UNSIGNED_BYTE, pixels);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
    free(pixels);
    const GLenum upload_error = glGetError();
    if (upload_error != GL_NO_ERROR) {
        fprintf(stderr, "texture: OpenGL upload failed for %s (0x%04x)\n",
                path, (unsigned)upload_error);
        glDeleteTextures(1, &id);
        return false;
    }

    if (texture->id != 0) {
        glDeleteTextures(1, &texture->id);
    }
    struct stat status;
    texture->id = id;
    texture->width = width;
    texture->height = height;
    if (stat(path, &status) == 0) {
        texture->modified_time = status.st_mtim;
        texture->source_size = status.st_size;
        texture->source_device = status.st_dev;
        texture->source_inode = status.st_ino;
    } else {
        texture->modified_time.tv_sec = 0;
        texture->modified_time.tv_nsec = 0;
        texture->source_size = 0;
        texture->source_device = 0;
        texture->source_inode = 0;
    }
    snprintf(texture->source_path, sizeof(texture->source_path), "%s", path);
    fprintf(stderr, "texture: loaded %s (%dx%d)\n", path, width, height);
    return true;
}

bool vc_png_texture_reload_if_changed(VcPngTexture *texture)
{
    if (texture == NULL || texture->source_path[0] == '\0') {
        return false;
    }
    struct stat status;
    if (stat(texture->source_path, &status) != 0 ||
        (status.st_mtim.tv_sec == texture->modified_time.tv_sec &&
         status.st_mtim.tv_nsec == texture->modified_time.tv_nsec &&
         status.st_size == texture->source_size &&
         status.st_dev == texture->source_device &&
         status.st_ino == texture->source_inode)) {
        return false;
    }
    return vc_png_texture_load(texture, texture->source_path);
}

bool vc_png_write_framebuffer(const char *path, int width, int height)
{
    if (path == NULL || width <= 0 || height <= 0) {
        return false;
    }
    const size_t row_bytes = (size_t)width * 4U;
    if ((size_t)height > SIZE_MAX / row_bytes) {
        return false;
    }
    unsigned char *pixels = malloc(row_bytes * (size_t)height);
    png_bytep *rows = malloc(sizeof(*rows) * (size_t)height);
    if (pixels == NULL || rows == NULL) {
        free(rows);
        free(pixels);
        return false;
    }
    /* Hidden, uncapped contexts may still have transient UI draws queued. */
    glFinish();
    while (glGetError() != GL_NO_ERROR) {
    }
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    glPixelStorei(GL_PACK_ALIGNMENT, 4);
    if (glGetError() != GL_NO_ERROR) {
        free(rows);
        free(pixels);
        return false;
    }
    for (int y = 0; y < height; ++y) {
        rows[y] = pixels + (size_t)(height - 1 - y) * row_bytes;
    }

    FILE *file = fopen(path, "wb");
    if (file == NULL) {
        free(rows);
        free(pixels);
        return false;
    }
    png_structp png = png_create_write_struct(PNG_LIBPNG_VER_STRING, NULL, NULL,
                                              NULL);
    png_infop info = png != NULL ? png_create_info_struct(png) : NULL;
    bool ok = png != NULL && info != NULL;
    if (ok && setjmp(png_jmpbuf(png)) == 0) {
        png_init_io(png, file);
        png_set_IHDR(png, info, (png_uint_32)width, (png_uint_32)height, 8,
                     PNG_COLOR_TYPE_RGBA, PNG_INTERLACE_NONE,
                     PNG_COMPRESSION_TYPE_DEFAULT, PNG_FILTER_TYPE_DEFAULT);
        png_write_info(png, info);
        png_write_image(png, rows);
        png_write_end(png, NULL);
    } else {
        ok = false;
    }
    png_destroy_write_struct(&png, &info);
    fclose(file);
    free(rows);
    free(pixels);
    if (ok) {
        fprintf(stderr, "screenshot: wrote %s (%dx%d)\n", path, width, height);
    }
    return ok;
}

void vc_png_texture_destroy(VcPngTexture *texture)
{
    if (texture == NULL) {
        return;
    }
    if (texture->id != 0) {
        glDeleteTextures(1, &texture->id);
    }
    memset(texture, 0, sizeof(*texture));
}

#ifndef VC_PORT_PNG_TEXTURE_H
#define VC_PORT_PNG_TEXTURE_H

#include <GL/glew.h>
#include <stdbool.h>
#include <sys/types.h>
#include <time.h>

typedef struct VcPngTexture {
    GLuint id;
    int width;
    int height;
    struct timespec modified_time;
    off_t source_size;
    dev_t source_device;
    ino_t source_inode;
    char source_path[4096];
} VcPngTexture;

bool vc_png_texture_load(VcPngTexture *texture, const char *path);
bool vc_png_texture_reload_if_changed(VcPngTexture *texture);
bool vc_png_write_framebuffer(const char *path, int width, int height);
void vc_png_texture_destroy(VcPngTexture *texture);

#endif

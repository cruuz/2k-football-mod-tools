#ifndef VC_PORT_UI_RENDERER_H
#define VC_PORT_UI_RENDERER_H

#include <GL/glew.h>
#include <stdbool.h>

typedef struct VcUiRenderer {
    GLuint program;
    GLuint vao;
    GLuint vbo;
    GLint screen_uniform;
    GLint textured_uniform;
    int width;
    int height;
} VcUiRenderer;

bool vc_ui_init(VcUiRenderer *renderer, int width, int height);
void vc_ui_resize(VcUiRenderer *renderer, int width, int height);
void vc_ui_begin(VcUiRenderer *renderer, float r, float g, float b, float a);
void vc_ui_resume(VcUiRenderer *renderer);
void vc_ui_rect(VcUiRenderer *renderer, float x, float y, float w, float h,
                float r, float g, float b, float a);
void vc_ui_texture(VcUiRenderer *renderer, GLuint texture, float x, float y,
                   float w, float h, float alpha);
void vc_ui_texture_region(VcUiRenderer *renderer, GLuint texture,
                          float x, float y, float w, float h,
                          float u0, float v0, float u1, float v1,
                          float r, float g, float b, float a);
void vc_ui_text(VcUiRenderer *renderer, const char *text, float x, float y,
                float scale, float r, float g, float b, float a);
void vc_ui_destroy(VcUiRenderer *renderer);

#endif

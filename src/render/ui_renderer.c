#include "port/ui_renderer.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct UiVertex {
    float x;
    float y;
    float u;
    float v;
    float r;
    float g;
    float b;
    float a;
} UiVertex;

static const char *vertex_shader_source =
    "#version 330 core\n"
    "layout(location=0) in vec2 a_position;\n"
    "layout(location=1) in vec2 a_uv;\n"
    "layout(location=2) in vec4 a_color;\n"
    "uniform vec2 u_screen;\n"
    "out vec2 v_uv;\n"
    "out vec4 v_color;\n"
    "void main() {\n"
    "  vec2 p = vec2((a_position.x / u_screen.x) * 2.0 - 1.0,\n"
    "                1.0 - (a_position.y / u_screen.y) * 2.0);\n"
    "  gl_Position = vec4(p, 0.0, 1.0);\n"
    "  v_uv = a_uv;\n"
    "  v_color = a_color;\n"
    "}\n";

static const char *fragment_shader_source =
    "#version 330 core\n"
    "in vec2 v_uv;\n"
    "in vec4 v_color;\n"
    "uniform sampler2D u_texture;\n"
    "uniform int u_textured;\n"
    "out vec4 frag_color;\n"
    "void main() {\n"
    "  vec4 texel = u_textured != 0 ? texture(u_texture, v_uv) : vec4(1.0);\n"
    "  frag_color = v_color * texel;\n"
    "}\n";

static GLuint compile_shader(GLenum type, const char *source)
{
    GLuint shader = glCreateShader(type);
    glShaderSource(shader, 1, &source, NULL);
    glCompileShader(shader);
    GLint ok = GL_FALSE;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (ok != GL_TRUE) {
        char log[2048];
        glGetShaderInfoLog(shader, sizeof(log), NULL, log);
        fprintf(stderr, "OpenGL shader compilation failed: %s\n", log);
        glDeleteShader(shader);
        return 0;
    }
    return shader;
}

static GLuint link_program(void)
{
    GLuint vertex = compile_shader(GL_VERTEX_SHADER, vertex_shader_source);
    GLuint fragment = compile_shader(GL_FRAGMENT_SHADER, fragment_shader_source);
    if (vertex == 0 || fragment == 0) {
        glDeleteShader(vertex);
        glDeleteShader(fragment);
        return 0;
    }
    GLuint program = glCreateProgram();
    glAttachShader(program, vertex);
    glAttachShader(program, fragment);
    glLinkProgram(program);
    glDeleteShader(vertex);
    glDeleteShader(fragment);
    GLint ok = GL_FALSE;
    glGetProgramiv(program, GL_LINK_STATUS, &ok);
    if (ok != GL_TRUE) {
        char log[2048];
        glGetProgramInfoLog(program, sizeof(log), NULL, log);
        fprintf(stderr, "OpenGL program link failed: %s\n", log);
        glDeleteProgram(program);
        return 0;
    }
    return program;
}

bool vc_ui_init(VcUiRenderer *renderer, int width, int height)
{
    if (renderer == NULL || width <= 0 || height <= 0) {
        return false;
    }
    memset(renderer, 0, sizeof(*renderer));
    renderer->program = link_program();
    if (renderer->program == 0) {
        return false;
    }
    renderer->width = width;
    renderer->height = height;
    renderer->screen_uniform = glGetUniformLocation(renderer->program, "u_screen");
    renderer->textured_uniform = glGetUniformLocation(renderer->program,
                                                       "u_textured");
    if (renderer->screen_uniform < 0 || renderer->textured_uniform < 0) {
        fprintf(stderr, "OpenGL program is missing required UI uniforms\n");
        vc_ui_destroy(renderer);
        return false;
    }

    glGenVertexArrays(1, &renderer->vao);
    glGenBuffers(1, &renderer->vbo);
    if (renderer->vao == 0 || renderer->vbo == 0) {
        fprintf(stderr, "OpenGL could not allocate UI vertex objects\n");
        vc_ui_destroy(renderer);
        return false;
    }
    glBindVertexArray(renderer->vao);
    glBindBuffer(GL_ARRAY_BUFFER, renderer->vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(UiVertex) * 6, NULL, GL_DYNAMIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, sizeof(UiVertex),
                          (void *)offsetof(UiVertex, x));
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, sizeof(UiVertex),
                          (void *)offsetof(UiVertex, u));
    glEnableVertexAttribArray(2);
    glVertexAttribPointer(2, 4, GL_FLOAT, GL_FALSE, sizeof(UiVertex),
                          (void *)offsetof(UiVertex, r));
    glBindVertexArray(0);

    glUseProgram(renderer->program);
    glUniform1i(glGetUniformLocation(renderer->program, "u_texture"), 0);
    return true;
}

void vc_ui_resize(VcUiRenderer *renderer, int width, int height)
{
    if (renderer != NULL && width > 0 && height > 0) {
        renderer->width = width;
        renderer->height = height;
    }
}

void vc_ui_begin(VcUiRenderer *renderer, float r, float g, float b, float a)
{
    glViewport(0, 0, renderer->width, renderer->height);
    glDisable(GL_DEPTH_TEST);
    glEnable(GL_FRAMEBUFFER_SRGB);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glClearColor(r, g, b, a);
    glClear(GL_COLOR_BUFFER_BIT);
    glUseProgram(renderer->program);
    glUniform2f(renderer->screen_uniform, (float)renderer->width,
                (float)renderer->height);
    glBindVertexArray(renderer->vao);
}

void vc_ui_resume(VcUiRenderer *renderer)
{
    if (renderer == NULL) {
        return;
    }
    glViewport(0, 0, renderer->width, renderer->height);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_SCISSOR_TEST);
    glEnable(GL_FRAMEBUFFER_SRGB);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glUseProgram(renderer->program);
    glUniform2f(renderer->screen_uniform, (float)renderer->width,
                (float)renderer->height);
    glBindVertexArray(renderer->vao);
}

static void draw_quad(VcUiRenderer *renderer, GLuint texture, bool textured,
                      float x, float y, float w, float h, float u0, float v0,
                      float u1, float v1, float r, float g, float b, float a)
{
    const UiVertex vertices[6] = {
        {x,     y,     u0, v0, r, g, b, a},
        {x + w, y,     u1, v0, r, g, b, a},
        {x + w, y + h, u1, v1, r, g, b, a},
        {x,     y,     u0, v0, r, g, b, a},
        {x + w, y + h, u1, v1, r, g, b, a},
        {x,     y + h, u0, v1, r, g, b, a}
    };
    glUniform1i(renderer->textured_uniform, textured ? 1 : 0);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, textured ? texture : 0);
    glBindBuffer(GL_ARRAY_BUFFER, renderer->vbo);
    /* Orphan the tiny transient buffer so queued draws never observe a later
       quad's data during uncapped smoke tests. */
    glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STREAM_DRAW);
    glDrawArrays(GL_TRIANGLES, 0, 6);
}

void vc_ui_rect(VcUiRenderer *renderer, float x, float y, float w, float h,
                float r, float g, float b, float a)
{
    draw_quad(renderer, 0, false, x, y, w, h, 0.0f, 0.0f, 1.0f, 1.0f,
              r, g, b, a);
}

void vc_ui_texture(VcUiRenderer *renderer, GLuint texture, float x, float y,
                   float w, float h, float alpha)
{
    if (texture != 0) {
        draw_quad(renderer, texture, true, x, y, w, h,
                  0.0f, 0.0f, 1.0f, 1.0f,
                  1.0f, 1.0f, 1.0f, alpha);
    }
}

void vc_ui_texture_region(VcUiRenderer *renderer, GLuint texture,
                          float x, float y, float w, float h,
                          float u0, float v0, float u1, float v1,
                          float r, float g, float b, float a)
{
    if (renderer == NULL || texture == 0 || w <= 0.0f || h <= 0.0f ||
        u0 < 0.0f || v0 < 0.0f || u1 > 1.0f || v1 > 1.0f ||
        u1 <= u0 || v1 <= v0) {
        return;
    }
    draw_quad(renderer, texture, true, x, y, w, h, u0, v0, u1, v1,
              r, g, b, a);
}

static void glyph_rows(char ch, uint8_t rows[7])
{
    memset(rows, 0, 7);
#define GLYPH(a,b,c,d,e,f,g) do { rows[0]=a; rows[1]=b; rows[2]=c; rows[3]=d; rows[4]=e; rows[5]=f; rows[6]=g; } while (0)
    switch (ch) {
    case 'A': GLYPH(14,17,17,31,17,17,17); break;
    case 'B': GLYPH(30,17,17,30,17,17,30); break;
    case 'C': GLYPH(14,17,16,16,16,17,14); break;
    case 'D': GLYPH(30,17,17,17,17,17,30); break;
    case 'E': GLYPH(31,16,16,30,16,16,31); break;
    case 'F': GLYPH(31,16,16,30,16,16,16); break;
    case 'G': GLYPH(14,17,16,23,17,17,15); break;
    case 'H': GLYPH(17,17,17,31,17,17,17); break;
    case 'I': GLYPH(31,4,4,4,4,4,31); break;
    case 'J': GLYPH(7,2,2,2,18,18,12); break;
    case 'K': GLYPH(17,18,20,24,20,18,17); break;
    case 'L': GLYPH(16,16,16,16,16,16,31); break;
    case 'M': GLYPH(17,27,21,21,17,17,17); break;
    case 'N': GLYPH(17,25,21,19,17,17,17); break;
    case 'O': GLYPH(14,17,17,17,17,17,14); break;
    case 'P': GLYPH(30,17,17,30,16,16,16); break;
    case 'Q': GLYPH(14,17,17,17,21,18,13); break;
    case 'R': GLYPH(30,17,17,30,20,18,17); break;
    case 'S': GLYPH(15,16,16,14,1,1,30); break;
    case 'T': GLYPH(31,4,4,4,4,4,4); break;
    case 'U': GLYPH(17,17,17,17,17,17,14); break;
    case 'V': GLYPH(17,17,17,17,17,10,4); break;
    case 'W': GLYPH(17,17,17,21,21,21,10); break;
    case 'X': GLYPH(17,17,10,4,10,17,17); break;
    case 'Y': GLYPH(17,17,10,4,4,4,4); break;
    case 'Z': GLYPH(31,1,2,4,8,16,31); break;
    case '0': GLYPH(14,17,19,21,25,17,14); break;
    case '1': GLYPH(4,12,4,4,4,4,14); break;
    case '2': GLYPH(14,17,1,2,4,8,31); break;
    case '3': GLYPH(30,1,1,14,1,1,30); break;
    case '4': GLYPH(2,6,10,18,31,2,2); break;
    case '5': GLYPH(31,16,16,30,1,1,30); break;
    case '6': GLYPH(14,16,16,30,17,17,14); break;
    case '7': GLYPH(31,1,2,4,8,8,8); break;
    case '8': GLYPH(14,17,17,14,17,17,14); break;
    case '9': GLYPH(14,17,17,15,1,1,14); break;
    case ':': GLYPH(0,4,4,0,4,4,0); break;
    case '.': GLYPH(0,0,0,0,0,12,12); break;
    case '-': GLYPH(0,0,0,31,0,0,0); break;
    case '/': GLYPH(1,2,2,4,8,8,16); break;
    case '>': GLYPH(16,8,4,2,4,8,16); break;
    case '|': GLYPH(4,4,4,4,4,4,4); break;
    case '_': GLYPH(0,0,0,0,0,0,31); break;
    default: break;
    }
#undef GLYPH
}

void vc_ui_text(VcUiRenderer *renderer, const char *text, float x, float y,
                float scale, float r, float g, float b, float a)
{
    if (text == NULL || scale <= 0.0f) {
        return;
    }
    const float origin_x = x;
    for (const char *cursor = text; *cursor != '\0'; ++cursor) {
        char ch = *cursor;
        if (ch == '\n') {
            x = origin_x;
            y += scale * 9.0f;
            continue;
        }
        if (ch >= 'a' && ch <= 'z') {
            ch = (char)(ch - 'a' + 'A');
        }
        uint8_t rows[7];
        glyph_rows(ch, rows);
        for (int row = 0; row < 7; ++row) {
            for (int column = 0; column < 5; ++column) {
                if ((rows[row] & (1U << (4 - column))) != 0) {
                    vc_ui_rect(renderer, x + (float)column * scale,
                               y + (float)row * scale, scale, scale,
                               r, g, b, a);
                }
            }
        }
        x += scale * 6.0f;
    }
}

void vc_ui_destroy(VcUiRenderer *renderer)
{
    if (renderer == NULL) {
        return;
    }
    glDeleteBuffers(1, &renderer->vbo);
    glDeleteVertexArrays(1, &renderer->vao);
    glDeleteProgram(renderer->program);
    memset(renderer, 0, sizeof(*renderer));
}

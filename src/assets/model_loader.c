#include "port/model_loader.h"
#include "port/model_animation.h"

#include <GL/glew.h>
#include <assimp/cimport.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *model_vertex_shader =
    "#version 330 core\n"
    "layout(location=0) in vec3 a_position;\n"
    "layout(location=1) in vec3 a_normal;\n"
    "uniform vec3 u_center;\n"
    "uniform float u_radius;\n"
    "uniform float u_angle;\n"
    "uniform float u_aspect;\n"
    "out vec3 v_normal;\n"
    "void main() {\n"
    "  vec3 p = (a_position - u_center) / max(u_radius, 0.00001);\n"
    "  float c = cos(u_angle);\n"
    "  float s = sin(u_angle);\n"
    "  mat3 turn = mat3(c, 0.0, -s, 0.0, 1.0, 0.0, s, 0.0, c);\n"
    "  p = turn * p;\n"
    "  v_normal = turn * a_normal;\n"
    "  gl_Position = vec4(p.x * 0.84 / max(u_aspect, 0.01),\n"
    "                     p.y * 0.84, p.z * 0.20, 1.0);\n"
    "}\n";

static const char *model_fragment_shader =
    "#version 330 core\n"
    "in vec3 v_normal;\n"
    "out vec4 frag_color;\n"
    "void main() {\n"
    "  vec3 n = normalize(v_normal);\n"
    "  float light = 0.32 + 0.68 * abs(dot(n, normalize(vec3(0.35, 0.7, 1.0))));\n"
    "  vec3 base = mix(vec3(0.12, 0.38, 0.72), vec3(0.95, 0.28, 0.06),\n"
    "                  clamp(n.y * 0.5 + 0.5, 0.0, 1.0));\n"
    "  frag_color = vec4(base * light, 1.0);\n"
    "}\n";

static GLuint compile_shader(GLenum type, const char *source)
{
    const GLuint shader = glCreateShader(type);
    glShaderSource(shader, 1, &source, NULL);
    glCompileShader(shader);
    GLint ok = GL_FALSE;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (ok != GL_TRUE) {
        char log[2048];
        glGetShaderInfoLog(shader, (GLsizei)sizeof(log), NULL, log);
        fprintf(stderr, "model: OpenGL shader compilation failed: %s\n", log);
        glDeleteShader(shader);
        return 0;
    }
    return shader;
}

static GLuint link_program(void)
{
    const GLuint vertex = compile_shader(GL_VERTEX_SHADER,
                                         model_vertex_shader);
    const GLuint fragment = compile_shader(GL_FRAGMENT_SHADER,
                                           model_fragment_shader);
    if (vertex == 0 || fragment == 0) {
        glDeleteShader(vertex);
        glDeleteShader(fragment);
        return 0;
    }
    const GLuint program = glCreateProgram();
    glAttachShader(program, vertex);
    glAttachShader(program, fragment);
    glLinkProgram(program);
    glDeleteShader(vertex);
    glDeleteShader(fragment);
    GLint ok = GL_FALSE;
    glGetProgramiv(program, GL_LINK_STATUS, &ok);
    if (ok != GL_TRUE) {
        char log[2048];
        glGetProgramInfoLog(program, (GLsizei)sizeof(log), NULL, log);
        fprintf(stderr, "model: OpenGL program link failed: %s\n", log);
        glDeleteProgram(program);
        return 0;
    }
    return program;
}

static bool checked_model_sizes(const struct aiScene *scene,
                                size_t *vertex_count, size_t *index_count)
{
    size_t vertices = 0;
    size_t indices = 0;
    for (unsigned int mesh_index = 0; mesh_index < scene->mNumMeshes;
         ++mesh_index) {
        const struct aiMesh *mesh = scene->mMeshes[mesh_index];
        if (SIZE_MAX - vertices < mesh->mNumVertices) {
            return false;
        }
        vertices += mesh->mNumVertices;
        for (unsigned int face_index = 0; face_index < mesh->mNumFaces;
             ++face_index) {
            const struct aiFace *face = &mesh->mFaces[face_index];
            if (face->mNumIndices != 3U ||
                SIZE_MAX - indices < face->mNumIndices) {
                return false;
            }
            indices += face->mNumIndices;
        }
    }
    if (vertices == 0 || indices == 0 || vertices > UINT32_MAX ||
        indices > (size_t)INT_MAX ||
        vertices > SIZE_MAX / sizeof(VcModelVertex) ||
        indices > SIZE_MAX / sizeof(uint32_t)) {
        return false;
    }
    *vertex_count = vertices;
    *index_count = indices;
    return true;
}

static bool upload_model(VcModel *model)
{
    size_t vertex_count = 0;
    size_t index_count = 0;
    if (!checked_model_sizes(model->scene, &vertex_count, &index_count)) {
        fprintf(stderr, "model: no bounded triangle geometry is available\n");
        return false;
    }

    VcModelVertex *vertices = malloc(vertex_count * sizeof(*vertices));
    uint32_t *indices = malloc(index_count * sizeof(*indices));
    if (vertices == NULL || indices == NULL) {
        fprintf(stderr, "model: host allocation failed\n");
        free(vertices);
        free(indices);
        return false;
    }

    float minimum[3] = {FLT_MAX, FLT_MAX, FLT_MAX};
    float maximum[3] = {-FLT_MAX, -FLT_MAX, -FLT_MAX};
    size_t vertex_cursor = 0;
    size_t index_cursor = 0;
    for (unsigned int mesh_index = 0;
         mesh_index < model->scene->mNumMeshes; ++mesh_index) {
        const struct aiMesh *mesh = model->scene->mMeshes[mesh_index];
        const size_t base_vertex = vertex_cursor;
        for (unsigned int i = 0; i < mesh->mNumVertices; ++i) {
            const struct aiVector3D position = mesh->mVertices[i];
            const struct aiVector3D normal =
                mesh->mNormals != NULL
                    ? mesh->mNormals[i]
                    : (struct aiVector3D){0.0f, 0.0f, 1.0f};
            vertices[vertex_cursor] = (VcModelVertex){
                {position.x, position.y, position.z},
                {normal.x, normal.y, normal.z}
            };
            for (size_t axis = 0; axis < 3; ++axis) {
                const float value = vertices[vertex_cursor].position[axis];
                minimum[axis] = fminf(minimum[axis], value);
                maximum[axis] = fmaxf(maximum[axis], value);
            }
            ++vertex_cursor;
        }
        for (unsigned int face_index = 0; face_index < mesh->mNumFaces;
             ++face_index) {
            const struct aiFace *face = &mesh->mFaces[face_index];
            for (unsigned int i = 0; i < face->mNumIndices; ++i) {
                if (face->mIndices[i] >= mesh->mNumVertices) {
                    fprintf(stderr, "model: Assimp returned an invalid index\n");
                    free(vertices);
                    free(indices);
                    return false;
                }
                const size_t value = base_vertex + face->mIndices[i];
                if (value >= vertex_count) {
                    fprintf(stderr, "model: Assimp returned an invalid index\n");
                    free(vertices);
                    free(indices);
                    return false;
                }
                indices[index_cursor++] = (uint32_t)value;
            }
        }
    }

    model->runtime = vc_model_runtime_create(model->scene, vertices,
                                             vertex_count);
    if (model->runtime == NULL ||
        !vc_model_runtime_deform(model->runtime, 0.0f, vertices,
                                 vertex_count)) {
        fprintf(stderr,
                "model: could not prepare bounded scene transforms/skinning\n");
        free(vertices);
        free(indices);
        return false;
    }
    model->bone_count = vc_model_runtime_bone_count(model->runtime);
    model->bone_weight_count =
        vc_model_runtime_weight_count(model->runtime);
    model->cpu_skinning_ready = model->bone_count != 0U;

    minimum[0] = minimum[1] = minimum[2] = FLT_MAX;
    maximum[0] = maximum[1] = maximum[2] = -FLT_MAX;
    for (size_t i = 0; i < vertex_count; ++i) {
        for (size_t axis = 0; axis < 3U; ++axis) {
            const float value = vertices[i].position[axis];
            minimum[axis] = fminf(minimum[axis], value);
            maximum[axis] = fmaxf(maximum[axis], value);
        }
    }
    for (size_t axis = 0; axis < 3; ++axis) {
        model->center[axis] = (minimum[axis] + maximum[axis]) * 0.5f;
    }
    float radius_squared = 0.0f;
    for (size_t i = 0; i < vertex_count; ++i) {
        float distance_squared = 0.0f;
        for (size_t axis = 0; axis < 3; ++axis) {
            const float delta = vertices[i].position[axis] -
                                model->center[axis];
            distance_squared += delta * delta;
        }
        radius_squared = fmaxf(radius_squared, distance_squared);
    }
    model->radius = sqrtf(radius_squared);
    if (!(model->radius > 0.0f) || !isfinite(model->radius)) {
        model->radius = 1.0f;
    }

    model->program = link_program();
    if (model->program == 0) {
        free(vertices);
        free(indices);
        return false;
    }
    glGenVertexArrays(1, &model->vao);
    glGenBuffers(1, &model->vbo);
    glGenBuffers(1, &model->ebo);
    if (model->vao == 0 || model->vbo == 0 || model->ebo == 0) {
        fprintf(stderr, "model: OpenGL object allocation failed\n");
        free(vertices);
        free(indices);
        return false;
    }
    glBindVertexArray(model->vao);
    glBindBuffer(GL_ARRAY_BUFFER, model->vbo);
    glBufferData(GL_ARRAY_BUFFER,
                 (GLsizeiptr)(vertex_count * sizeof(*vertices)), vertices,
                 vc_model_runtime_is_animated(model->runtime)
                     ? GL_DYNAMIC_DRAW
                     : GL_STATIC_DRAW);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, model->ebo);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER,
                 (GLsizeiptr)(index_count * sizeof(*indices)), indices,
                 GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE,
                          (GLsizei)sizeof(VcModelVertex),
                          (void *)offsetof(VcModelVertex, position));
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE,
                          (GLsizei)sizeof(VcModelVertex),
                          (void *)offsetof(VcModelVertex, normal));
    glBindVertexArray(0);
    free(vertices);
    free(indices);

    model->index_count = (int)index_count;
    model->vertex_count = vertex_count;
    fprintf(stderr, "model: uploaded %zu vertices and %zu triangle indices\n",
            vertex_count, index_count);
    if (model->bone_count != 0U || model->animation_count != 0U) {
        fprintf(stderr,
                "model: CPU scene evaluator ready (%zu bones, %zu weights, "
                "%zu animations)\n",
                model->bone_count, model->bone_weight_count,
                model->animation_count);
    }
    return glGetError() == GL_NO_ERROR;
}

bool vc_model_load(VcModel *model, const char *path)
{
    if (model == NULL || path == NULL ||
        strlen(path) >= sizeof(model->source_path)) {
        return false;
    }

    vc_model_release(model);
    const unsigned int flags = aiProcess_Triangulate |
                               aiProcess_JoinIdenticalVertices |
                               aiProcess_GenSmoothNormals |
                               aiProcess_ImproveCacheLocality |
                               aiProcess_ValidateDataStructure;
    const struct aiScene *scene = aiImportFile(path, flags);
    if (scene == NULL) {
        fprintf(stderr, "model: could not load %s: %s\n", path,
                aiGetErrorString());
        return false;
    }

    model->scene = scene;
    model->mesh_count = scene->mNumMeshes;
    model->material_count = scene->mNumMaterials;
    model->animation_count = scene->mNumAnimations;
    snprintf(model->source_path, sizeof(model->source_path), "%s", path);

    fprintf(stderr,
            "model: loaded %s (%zu meshes, %zu materials, %zu animations)\n",
            path, model->mesh_count, model->material_count,
            model->animation_count);
    if (!upload_model(model)) {
        fprintf(stderr, "model: could not upload bounded preview geometry\n");
        vc_model_release(model);
        return false;
    }

    /* Standard node transforms and the first imported glTF animation are
       evaluated by the host CPU path. PORTME: bind recovered title motion,
       materials/textures, morph targets, animation selection/graphs, and
       title-specific coordinate conventions without guessed semantics. */
    return true;
}

void vc_model_render_preview(VcModel *model, int drawable_width,
                             int drawable_height, int x, int y, int width,
                             int height, float animation_seconds,
                             float angle_radians)
{
    if (model == NULL || model->program == 0 || model->vao == 0 ||
        model->index_count <= 0 || drawable_width <= 0 ||
        drawable_height <= 0 || x < 0 || y < 0 || width <= 0 || height <= 0 ||
        x + width > drawable_width || y + height > drawable_height) {
        return;
    }
    if (vc_model_runtime_is_animated(model->runtime)) {
        VcModelVertex *vertices =
            malloc(model->vertex_count * sizeof(*vertices));
        if (vertices != NULL &&
            vc_model_runtime_deform(model->runtime, animation_seconds,
                                    vertices, model->vertex_count)) {
            glBindBuffer(GL_ARRAY_BUFFER, model->vbo);
            glBufferSubData(
                GL_ARRAY_BUFFER, 0,
                (GLsizeiptr)(model->vertex_count * sizeof(*vertices)),
                vertices);
            glBindBuffer(GL_ARRAY_BUFFER, 0);
        } else {
            fprintf(stderr,
                    "model: animated CPU skinning update failed at %.6f s\n",
                    (double)animation_seconds);
        }
        free(vertices);
    }
    const int viewport_y = drawable_height - y - height;
    glEnable(GL_SCISSOR_TEST);
    glScissor(x, viewport_y, width, height);
    glViewport(x, viewport_y, width, height);
    glClear(GL_DEPTH_BUFFER_BIT);
    glDisable(GL_BLEND);
    glEnable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glUseProgram(model->program);
    glUniform3fv(glGetUniformLocation(model->program, "u_center"), 1,
                 model->center);
    glUniform1f(glGetUniformLocation(model->program, "u_radius"),
                model->radius);
    glUniform1f(glGetUniformLocation(model->program, "u_angle"),
                angle_radians);
    glUniform1f(glGetUniformLocation(model->program, "u_aspect"),
                (float)width / (float)height);
    glBindVertexArray(model->vao);
    glDrawElements(GL_TRIANGLES, model->index_count, GL_UNSIGNED_INT, NULL);
    glBindVertexArray(0);
}

void vc_model_release(VcModel *model)
{
    if (model == NULL) {
        return;
    }
    glDeleteBuffers(1, &model->ebo);
    glDeleteBuffers(1, &model->vbo);
    glDeleteVertexArrays(1, &model->vao);
    glDeleteProgram(model->program);
    vc_model_runtime_release(model->runtime);
    if (model->scene != NULL) {
        aiReleaseImport(model->scene);
    }
    memset(model, 0, sizeof(*model));
}

#include "port/model_animation.h"

#include <assimp/cimport.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static int fail(const char *message)
{
    fprintf(stderr, "NFL_REFEREE_ANIMATION_RUNTIME_FAIL: %s\n", message);
    return EXIT_FAILURE;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        return fail("expected one animated referee glTF path");
    }
    const unsigned int flags = aiProcess_Triangulate |
                               aiProcess_JoinIdenticalVertices |
                               aiProcess_GenSmoothNormals |
                               aiProcess_ValidateDataStructure;
    const struct aiScene *scene = aiImportFile(argv[1], flags);
    if (scene == NULL) {
        fprintf(stderr, "Assimp: %s\n", aiGetErrorString());
        return fail("animated referee import failed");
    }
    if (scene->mNumAnimations != 1U || scene->mAnimations == NULL ||
        scene->mAnimations[0] == NULL ||
        scene->mAnimations[0]->mNumChannels != 50U ||
        fabs(scene->mAnimations[0]->mTicksPerSecond - 1000.0) > 1.0e-9 ||
        fabs(scene->mAnimations[0]->mDuration - 2966.6669921875) > 1.0e-6 ||
        scene->mNumMeshes == 0U || scene->mMeshes == NULL) {
        aiReleaseImport(scene);
        return fail("unexpected imported animation structure");
    }

    size_t vertex_count = 0U;
    for (unsigned int mesh_index = 0U;
         mesh_index < scene->mNumMeshes; ++mesh_index) {
        const struct aiMesh *mesh = scene->mMeshes[mesh_index];
        if (mesh == NULL || mesh->mVertices == NULL ||
            mesh->mNormals == NULL ||
            SIZE_MAX - vertex_count < (size_t)mesh->mNumVertices) {
            aiReleaseImport(scene);
            return fail("invalid imported mesh vertex stream");
        }
        vertex_count += (size_t)mesh->mNumVertices;
    }
    if (vertex_count == 0U ||
        vertex_count > SIZE_MAX / sizeof(VcModelVertex)) {
        aiReleaseImport(scene);
        return fail("invalid total vertex count");
    }

    VcModelVertex *source = malloc(vertex_count * sizeof(*source));
    VcModelVertex *at_start = malloc(vertex_count * sizeof(*at_start));
    VcModelVertex *at_probe = malloc(vertex_count * sizeof(*at_probe));
    if (source == NULL || at_start == NULL || at_probe == NULL) {
        free(at_probe);
        free(at_start);
        free(source);
        aiReleaseImport(scene);
        return fail("vertex allocation failed");
    }

    size_t cursor = 0U;
    for (unsigned int mesh_index = 0U;
         mesh_index < scene->mNumMeshes; ++mesh_index) {
        const struct aiMesh *mesh = scene->mMeshes[mesh_index];
        for (unsigned int vertex = 0U;
             vertex < mesh->mNumVertices; ++vertex) {
            source[cursor] = (VcModelVertex) {
                {mesh->mVertices[vertex].x, mesh->mVertices[vertex].y,
                 mesh->mVertices[vertex].z},
                {mesh->mNormals[vertex].x, mesh->mNormals[vertex].y,
                 mesh->mNormals[vertex].z},
            };
            ++cursor;
        }
    }

    VcModelRuntime *runtime =
        vc_model_runtime_create(scene, source, vertex_count);
    const size_t bone_count = vc_model_runtime_bone_count(runtime);
    const size_t weight_count = vc_model_runtime_weight_count(runtime);
    if (runtime == NULL || !vc_model_runtime_is_animated(runtime) ||
        bone_count == 0U || weight_count == 0U ||
        !vc_model_runtime_deform(runtime, 0.0f, at_start, vertex_count) ||
        !vc_model_runtime_deform(runtime, 1.5f, at_probe, vertex_count)) {
        vc_model_runtime_release(runtime);
        free(at_probe);
        free(at_start);
        free(source);
        aiReleaseImport(scene);
        return fail("title-derived deformation evaluation failed");
    }

    size_t moved_vertices = 0U;
    float maximum_delta_squared = 0.0f;
    for (size_t vertex = 0U; vertex < vertex_count; ++vertex) {
        const float dx = at_probe[vertex].position[0] -
                         at_start[vertex].position[0];
        const float dy = at_probe[vertex].position[1] -
                         at_start[vertex].position[1];
        const float dz = at_probe[vertex].position[2] -
                         at_start[vertex].position[2];
        const float delta_squared = dx * dx + dy * dy + dz * dz;
        if (!isfinite(delta_squared) ||
            !isfinite(at_probe[vertex].normal[0]) ||
            !isfinite(at_probe[vertex].normal[1]) ||
            !isfinite(at_probe[vertex].normal[2])) {
            vc_model_runtime_release(runtime);
            free(at_probe);
            free(at_start);
            free(source);
            aiReleaseImport(scene);
            return fail("deformed vertex is not finite");
        }
        if (delta_squared > 1.0e-10f) {
            ++moved_vertices;
        }
        if (delta_squared > maximum_delta_squared) {
            maximum_delta_squared = delta_squared;
        }
    }
    if (scene->mNumMeshes != 12U || vertex_count != 1375U ||
        bone_count != 300U || weight_count != 2006U ||
        moved_vertices != vertex_count || maximum_delta_squared <= 0.36f ||
        maximum_delta_squared >= 0.49f) {
        vc_model_runtime_release(runtime);
        free(at_probe);
        free(at_start);
        free(source);
        aiReleaseImport(scene);
        return fail("canonical animation deformation contract differs");
    }

    printf("NFL_REFEREE_ANIMATION_RUNTIME_PASS "
           "meshes=%u vertices=%zu bones=%zu weights=%zu channels=50 moved=%zu "
           "max_delta=%.9g\n",
           scene->mNumMeshes, vertex_count, bone_count, weight_count,
           moved_vertices, (double)sqrtf(maximum_delta_squared));
    vc_model_runtime_release(runtime);
    free(at_probe);
    free(at_start);
    free(source);
    aiReleaseImport(scene);
    return EXIT_SUCCESS;
}

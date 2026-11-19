#include "port/model_animation.h"

#include <assimp/types.h>
#include <assimp/anim.h>
#include <assimp/cimport.h>
#include <assimp/mesh.h>
#include <assimp/scene.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct VcModelInfluence {
    uint32_t bone_index;
    float weight;
} VcModelInfluence;

typedef struct VcModelBone {
    const struct aiNode *node;
    struct aiMatrix4x4 offset;
} VcModelBone;

struct VcModelRuntime {
    const struct aiScene *scene;
    VcModelVertex *source_vertices;
    size_t vertex_count;
    size_t mesh_count;
    size_t node_count;
    size_t bone_count;
    size_t weight_count;
    size_t *mesh_vertex_base;
    size_t *mesh_bone_base;
    uint32_t *vertex_mesh_index;
    size_t *weight_offsets;
    VcModelInfluence *weights;
    VcModelBone *bones;
    const struct aiNode **nodes;
    const struct aiNode **mesh_nodes;
    struct aiMatrix4x4 *global_matrices;
    struct aiMatrix4x4 *bone_matrices;
    struct aiMatrix4x4 inverse_root;
};

static bool checked_add_size(size_t left, size_t right, size_t *result)
{
    if (SIZE_MAX - left < right) {
        return false;
    }
    *result = left + right;
    return true;
}

static bool matrix_is_finite(const struct aiMatrix4x4 *matrix)
{
    return isfinite(matrix->a1) && isfinite(matrix->a2) &&
           isfinite(matrix->a3) && isfinite(matrix->a4) &&
           isfinite(matrix->b1) && isfinite(matrix->b2) &&
           isfinite(matrix->b3) && isfinite(matrix->b4) &&
           isfinite(matrix->c1) && isfinite(matrix->c2) &&
           isfinite(matrix->c3) && isfinite(matrix->c4) &&
           isfinite(matrix->d1) && isfinite(matrix->d2) &&
           isfinite(matrix->d3) && isfinite(matrix->d4);
}

static bool count_nodes(const struct aiNode *node, unsigned int depth,
                        size_t *count)
{
    if (node == NULL || depth > 4096U || *count == SIZE_MAX) {
        return false;
    }
    ++*count;
    if (node->mNumChildren != 0U && node->mChildren == NULL) {
        return false;
    }
    for (unsigned int i = 0; i < node->mNumChildren; ++i) {
        if (!count_nodes(node->mChildren[i], depth + 1U, count)) {
            return false;
        }
    }
    return true;
}

static bool string_matches(const struct aiString *left,
                           const struct aiString *right)
{
    return left->length == right->length &&
           left->length < MAXLEN &&
           memcmp(left->data, right->data, left->length) == 0;
}

static void find_named_nodes(const struct aiNode *node,
                             const struct aiString *name,
                             const struct aiNode **match,
                             size_t *match_count)
{
    if (string_matches(&node->mName, name)) {
        *match = node;
        ++*match_count;
    }
    for (unsigned int i = 0; i < node->mNumChildren; ++i) {
        find_named_nodes(node->mChildren[i], name, match, match_count);
    }
}

static bool flatten_nodes(VcModelRuntime *runtime,
                          const struct aiNode *node, size_t *cursor)
{
    if (*cursor >= runtime->node_count) {
        return false;
    }
    runtime->nodes[(*cursor)++] = node;
    if (node->mNumMeshes != 0U && node->mMeshes == NULL) {
        return false;
    }
    for (unsigned int i = 0; i < node->mNumMeshes; ++i) {
        const unsigned int mesh_index = node->mMeshes[i];
        if (mesh_index >= runtime->mesh_count) {
            return false;
        }
        if (runtime->mesh_nodes[mesh_index] != NULL &&
            runtime->mesh_nodes[mesh_index] != node) {
            fprintf(stderr,
                    "model: PORTME: instanced mesh %u has multiple nodes; "
                    "the bounded preview requires one node per mesh\n",
                    mesh_index);
            return false;
        }
        runtime->mesh_nodes[mesh_index] = node;
    }
    for (unsigned int i = 0; i < node->mNumChildren; ++i) {
        if (!flatten_nodes(runtime, node->mChildren[i], cursor)) {
            return false;
        }
    }
    return true;
}

static size_t node_index(const VcModelRuntime *runtime,
                         const struct aiNode *node)
{
    for (size_t i = 0; i < runtime->node_count; ++i) {
        if (runtime->nodes[i] == node) {
            return i;
        }
    }
    return SIZE_MAX;
}

static const struct aiNodeAnim *find_channel(
    const struct aiAnimation *animation, const struct aiString *node_name)
{
    if (animation == NULL || animation->mChannels == NULL) {
        return NULL;
    }
    for (unsigned int i = 0; i < animation->mNumChannels; ++i) {
        const struct aiNodeAnim *channel = animation->mChannels[i];
        if (channel != NULL && string_matches(&channel->mNodeName, node_name)) {
            return channel;
        }
    }
    return NULL;
}

static struct aiVector3D sample_vector(const struct aiVectorKey *keys,
                                       unsigned int count, double tick,
                                       struct aiVector3D fallback)
{
    if (keys == NULL || count == 0U) {
        return fallback;
    }
    if (count == 1U || tick <= keys[0].mTime) {
        return keys[0].mValue;
    }
    for (unsigned int i = 0; i + 1U < count; ++i) {
        const double first = keys[i].mTime;
        const double second = keys[i + 1U].mTime;
        if (tick <= second) {
            const double span = second - first;
            double factor = span > 0.0 ? (tick - first) / span : 0.0;
            factor = fmax(0.0, fmin(1.0, factor));
            return (struct aiVector3D){
                (float)((1.0 - factor) * keys[i].mValue.x +
                        factor * keys[i + 1U].mValue.x),
                (float)((1.0 - factor) * keys[i].mValue.y +
                        factor * keys[i + 1U].mValue.y),
                (float)((1.0 - factor) * keys[i].mValue.z +
                        factor * keys[i + 1U].mValue.z)};
        }
    }
    return keys[count - 1U].mValue;
}

static struct aiQuaternion sample_quaternion(const struct aiQuatKey *keys,
                                             unsigned int count, double tick,
                                             struct aiQuaternion fallback)
{
    if (keys == NULL || count == 0U) {
        return fallback;
    }
    if (count == 1U || tick <= keys[0].mTime) {
        return keys[0].mValue;
    }
    for (unsigned int i = 0; i + 1U < count; ++i) {
        const double first = keys[i].mTime;
        const double second = keys[i + 1U].mTime;
        if (tick <= second) {
            const double span = second - first;
            double factor = span > 0.0 ? (tick - first) / span : 0.0;
            factor = fmax(0.0, fmin(1.0, factor));
            struct aiQuaternion result;
            aiQuaternionInterpolate(&result, &keys[i].mValue,
                                    &keys[i + 1U].mValue, (float)factor);
            aiQuaternionNormalize(&result);
            return result;
        }
    }
    return keys[count - 1U].mValue;
}

static struct aiMatrix4x4 sampled_local_matrix(
    const struct aiNode *node, const struct aiNodeAnim *channel, double tick)
{
    if (channel == NULL) {
        return node->mTransformation;
    }
    struct aiVector3D bind_scale;
    struct aiQuaternion bind_rotation;
    struct aiVector3D bind_position;
    aiDecomposeMatrix(&node->mTransformation, &bind_scale, &bind_rotation,
                      &bind_position);
    const struct aiVector3D scale =
        sample_vector(channel->mScalingKeys, channel->mNumScalingKeys, tick,
                      bind_scale);
    const struct aiQuaternion rotation = sample_quaternion(
        channel->mRotationKeys, channel->mNumRotationKeys, tick,
        bind_rotation);
    const struct aiVector3D position = sample_vector(
        channel->mPositionKeys, channel->mNumPositionKeys, tick,
        bind_position);
    struct aiMatrix4x4 local;
    aiMatrix4FromScalingQuaternionPosition(&local, &scale, &rotation,
                                           &position);
    return local;
}

static bool evaluate_node(VcModelRuntime *runtime,
                          const struct aiNode *node,
                          const struct aiMatrix4x4 *parent_global,
                          const struct aiAnimation *animation, double tick,
                          unsigned int depth)
{
    if (depth > 4096U) {
        return false;
    }
    const size_t index = node_index(runtime, node);
    if (index == SIZE_MAX) {
        return false;
    }
    const struct aiNodeAnim *channel =
        find_channel(animation, &node->mName);
    runtime->global_matrices[index] =
        sampled_local_matrix(node, channel, tick);
    if (parent_global != NULL) {
        struct aiMatrix4x4 combined = *parent_global;
        aiMultiplyMatrix4(&combined, &runtime->global_matrices[index]);
        runtime->global_matrices[index] = combined;
    }
    if (!matrix_is_finite(&runtime->global_matrices[index])) {
        return false;
    }
    for (unsigned int i = 0; i < node->mNumChildren; ++i) {
        if (!evaluate_node(runtime, node->mChildren[i],
                           &runtime->global_matrices[index], animation, tick,
                           depth + 1U)) {
            return false;
        }
    }
    return true;
}

static bool evaluate_hierarchy(VcModelRuntime *runtime,
                               float animation_seconds)
{
    const struct aiAnimation *animation = NULL;
    double tick = 0.0;
    if (runtime->scene->mNumAnimations != 0U) {
        animation = runtime->scene->mAnimations[0];
        if (animation == NULL) {
            return false;
        }
        const double ticks_per_second = animation->mTicksPerSecond > 0.0
                                            ? animation->mTicksPerSecond
                                            : 25.0;
        tick = (double)animation_seconds * ticks_per_second;
        if (animation->mDuration > 0.0) {
            tick = fmod(tick, animation->mDuration);
            if (tick < 0.0) {
                tick += animation->mDuration;
            }
        }
    }
    return isfinite(tick) &&
           evaluate_node(runtime, runtime->scene->mRootNode, NULL, animation,
                         tick, 0U);
}

static bool normal_transform(const struct aiMatrix4x4 *matrix,
                             const float source[3], float output[3])
{
    struct aiMatrix3x3 normal_matrix;
    aiMatrix3FromMatrix4(&normal_matrix, matrix);
    const float determinant = aiMatrix3Determinant(&normal_matrix);
    if (!isfinite(determinant) || fabsf(determinant) <= FLT_EPSILON) {
        return false;
    }
    aiMatrix3Inverse(&normal_matrix);
    aiTransposeMatrix3(&normal_matrix);
    struct aiVector3D normal = {source[0], source[1], source[2]};
    aiTransformVecByMatrix3(&normal, &normal_matrix);
    if (!isfinite(normal.x) || !isfinite(normal.y) || !isfinite(normal.z)) {
        return false;
    }
    output[0] = normal.x;
    output[1] = normal.y;
    output[2] = normal.z;
    return true;
}

static bool transformed_vertex(const struct aiMatrix4x4 *matrix,
                               const VcModelVertex *source,
                               VcModelVertex *output)
{
    struct aiVector3D position = {source->position[0], source->position[1],
                                  source->position[2]};
    aiTransformVecByMatrix4(&position, matrix);
    output->position[0] = position.x;
    output->position[1] = position.y;
    output->position[2] = position.z;
    return isfinite(position.x) && isfinite(position.y) &&
           isfinite(position.z) &&
           normal_transform(matrix, source->normal, output->normal);
}

static bool prepare_bone_matrices(VcModelRuntime *runtime)
{
    for (size_t i = 0; i < runtime->bone_count; ++i) {
        const size_t index = node_index(runtime, runtime->bones[i].node);
        if (index == SIZE_MAX) {
            return false;
        }
        struct aiMatrix4x4 matrix = runtime->inverse_root;
        aiMultiplyMatrix4(&matrix, &runtime->global_matrices[index]);
        aiMultiplyMatrix4(&matrix, &runtime->bones[i].offset);
        if (!matrix_is_finite(&matrix)) {
            return false;
        }
        runtime->bone_matrices[i] = matrix;
    }
    return true;
}

bool vc_model_runtime_deform(VcModelRuntime *runtime,
                             float animation_seconds,
                             VcModelVertex *output_vertices,
                             size_t output_vertex_count)
{
    if (runtime == NULL || output_vertices == NULL ||
        output_vertex_count != runtime->vertex_count ||
        !isfinite(animation_seconds) ||
        !evaluate_hierarchy(runtime, animation_seconds) ||
        !prepare_bone_matrices(runtime)) {
        return false;
    }

    for (size_t vertex = 0; vertex < runtime->vertex_count; ++vertex) {
        const size_t weight_first = runtime->weight_offsets[vertex];
        const size_t weight_end = runtime->weight_offsets[vertex + 1U];
        if (weight_first == weight_end) {
            const uint32_t mesh_index = runtime->vertex_mesh_index[vertex];
            if (mesh_index >= runtime->mesh_count) {
                return false;
            }
            const struct aiNode *mesh_node = runtime->mesh_nodes[mesh_index];
            if (mesh_node == NULL) {
                mesh_node = runtime->scene->mRootNode;
            }
            const size_t mesh_node_index = node_index(runtime, mesh_node);
            if (mesh_node_index == SIZE_MAX) {
                return false;
            }
            struct aiMatrix4x4 matrix = runtime->inverse_root;
            aiMultiplyMatrix4(&matrix,
                              &runtime->global_matrices[mesh_node_index]);
            if (!transformed_vertex(&matrix, &runtime->source_vertices[vertex],
                                    &output_vertices[vertex])) {
                return false;
            }
            continue;
        }

        VcModelVertex result = {{0.0f, 0.0f, 0.0f},
                                {0.0f, 0.0f, 0.0f}};
        for (size_t weight_index = weight_first;
             weight_index < weight_end; ++weight_index) {
            const VcModelInfluence influence =
                runtime->weights[weight_index];
            if (influence.bone_index >= runtime->bone_count) {
                return false;
            }
            VcModelVertex transformed;
            if (!transformed_vertex(
                    &runtime->bone_matrices[influence.bone_index],
                    &runtime->source_vertices[vertex], &transformed)) {
                return false;
            }
            for (size_t axis = 0; axis < 3U; ++axis) {
                result.position[axis] +=
                    transformed.position[axis] * influence.weight;
                result.normal[axis] +=
                    transformed.normal[axis] * influence.weight;
            }
        }
        const float normal_length =
            sqrtf(result.normal[0] * result.normal[0] +
                  result.normal[1] * result.normal[1] +
                  result.normal[2] * result.normal[2]);
        if (!(normal_length > FLT_EPSILON) || !isfinite(normal_length)) {
            result.normal[0] = runtime->source_vertices[vertex].normal[0];
            result.normal[1] = runtime->source_vertices[vertex].normal[1];
            result.normal[2] = runtime->source_vertices[vertex].normal[2];
        } else {
            result.normal[0] /= normal_length;
            result.normal[1] /= normal_length;
            result.normal[2] /= normal_length;
        }
        if (!isfinite(result.position[0]) || !isfinite(result.position[1]) ||
            !isfinite(result.position[2])) {
            return false;
        }
        output_vertices[vertex] = result;
    }
    return true;
}

static bool build_mesh_offsets(VcModelRuntime *runtime)
{
    size_t vertex_total = 0;
    size_t bone_total = 0;
    size_t weight_total = 0;
    for (size_t mesh_index = 0; mesh_index < runtime->mesh_count;
         ++mesh_index) {
        const struct aiMesh *mesh = runtime->scene->mMeshes[mesh_index];
        if (mesh == NULL ||
            !checked_add_size(vertex_total, mesh->mNumVertices,
                              &vertex_total) ||
            !checked_add_size(bone_total, mesh->mNumBones, &bone_total)) {
            return false;
        }
        runtime->mesh_vertex_base[mesh_index + 1U] = vertex_total;
        runtime->mesh_bone_base[mesh_index] = bone_total - mesh->mNumBones;
        if (mesh->mNumBones != 0U && mesh->mBones == NULL) {
            return false;
        }
        for (unsigned int bone_index = 0; bone_index < mesh->mNumBones;
             ++bone_index) {
            const struct aiBone *bone = mesh->mBones[bone_index];
            if (bone == NULL ||
                !checked_add_size(weight_total, bone->mNumWeights,
                                  &weight_total)) {
                return false;
            }
        }
    }
    runtime->mesh_bone_base[runtime->mesh_count] = bone_total;
    if (vertex_total != runtime->vertex_count || bone_total > UINT32_MAX) {
        return false;
    }
    runtime->bone_count = bone_total;
    runtime->weight_count = weight_total;
    return true;
}

static bool populate_bones_and_weights(VcModelRuntime *runtime)
{
    size_t *weight_counts = calloc(runtime->vertex_count,
                                   sizeof(*weight_counts));
    size_t *write_cursors = calloc(runtime->vertex_count,
                                   sizeof(*write_cursors));
    if (weight_counts == NULL || write_cursors == NULL) {
        free(weight_counts);
        free(write_cursors);
        return false;
    }

    for (size_t mesh_index = 0; mesh_index < runtime->mesh_count;
         ++mesh_index) {
        const struct aiMesh *mesh = runtime->scene->mMeshes[mesh_index];
        const size_t vertex_base = runtime->mesh_vertex_base[mesh_index];
        const size_t bone_base = runtime->mesh_bone_base[mesh_index];
        for (unsigned int bone_index = 0; bone_index < mesh->mNumBones;
             ++bone_index) {
            const struct aiBone *bone = mesh->mBones[bone_index];
            const size_t global_bone = bone_base + bone_index;
            const struct aiNode *match = NULL;
            size_t match_count = 0;
            find_named_nodes(runtime->scene->mRootNode, &bone->mName, &match,
                             &match_count);
            if (match_count != 1U || match == NULL ||
                !matrix_is_finite(&bone->mOffsetMatrix)) {
                fprintf(stderr,
                        "model: bone '%.*s' has %zu matching scene nodes\n",
                        (int)bone->mName.length, bone->mName.data,
                        match_count);
                free(weight_counts);
                free(write_cursors);
                return false;
            }
            runtime->bones[global_bone] =
                (VcModelBone){match, bone->mOffsetMatrix};
            if (bone->mNumWeights != 0U && bone->mWeights == NULL) {
                free(weight_counts);
                free(write_cursors);
                return false;
            }
            for (unsigned int weight_index = 0;
                 weight_index < bone->mNumWeights; ++weight_index) {
                const struct aiVertexWeight weight = bone->mWeights[weight_index];
                if (weight.mVertexId >= mesh->mNumVertices ||
                    !(weight.mWeight >= 0.0f) ||
                    !isfinite(weight.mWeight)) {
                    free(weight_counts);
                    free(write_cursors);
                    return false;
                }
                const size_t vertex = vertex_base + weight.mVertexId;
                if (weight_counts[vertex] == SIZE_MAX) {
                    free(weight_counts);
                    free(write_cursors);
                    return false;
                }
                ++weight_counts[vertex];
            }
        }
    }

    runtime->weight_offsets[0] = 0;
    for (size_t vertex = 0; vertex < runtime->vertex_count; ++vertex) {
        if (!checked_add_size(runtime->weight_offsets[vertex],
                              weight_counts[vertex],
                              &runtime->weight_offsets[vertex + 1U])) {
            free(weight_counts);
            free(write_cursors);
            return false;
        }
        write_cursors[vertex] = runtime->weight_offsets[vertex];
    }
    if (runtime->weight_offsets[runtime->vertex_count] !=
        runtime->weight_count) {
        free(weight_counts);
        free(write_cursors);
        return false;
    }

    for (size_t mesh_index = 0; mesh_index < runtime->mesh_count;
         ++mesh_index) {
        const struct aiMesh *mesh = runtime->scene->mMeshes[mesh_index];
        const size_t vertex_base = runtime->mesh_vertex_base[mesh_index];
        const size_t bone_base = runtime->mesh_bone_base[mesh_index];
        for (unsigned int bone_index = 0; bone_index < mesh->mNumBones;
             ++bone_index) {
            const struct aiBone *bone = mesh->mBones[bone_index];
            for (unsigned int weight_index = 0;
                 weight_index < bone->mNumWeights; ++weight_index) {
                const struct aiVertexWeight weight = bone->mWeights[weight_index];
                const size_t vertex = vertex_base + weight.mVertexId;
                const size_t output = write_cursors[vertex]++;
                runtime->weights[output] = (VcModelInfluence){
                    (uint32_t)(bone_base + bone_index), weight.mWeight};
            }
        }
    }

    for (size_t vertex = 0; vertex < runtime->vertex_count; ++vertex) {
        double sum = 0.0;
        for (size_t i = runtime->weight_offsets[vertex];
             i < runtime->weight_offsets[vertex + 1U]; ++i) {
            sum += runtime->weights[i].weight;
        }
        if (runtime->weight_offsets[vertex] !=
            runtime->weight_offsets[vertex + 1U]) {
            if (!(sum > 0.0) || !isfinite(sum)) {
                free(weight_counts);
                free(write_cursors);
                return false;
            }
            for (size_t i = runtime->weight_offsets[vertex];
                 i < runtime->weight_offsets[vertex + 1U]; ++i) {
                runtime->weights[i].weight =
                    (float)((double)runtime->weights[i].weight / sum);
            }
        }
    }

    free(weight_counts);
    free(write_cursors);
    return true;
}

VcModelRuntime *vc_model_runtime_create(const struct aiScene *scene,
                                        const VcModelVertex *source_vertices,
                                        size_t vertex_count)
{
    if (scene == NULL || scene->mRootNode == NULL ||
        (scene->mNumMeshes != 0U && scene->mMeshes == NULL) ||
        source_vertices == NULL || vertex_count == 0U) {
        return NULL;
    }
    VcModelRuntime *runtime = calloc(1, sizeof(*runtime));
    if (runtime == NULL) {
        return NULL;
    }
    runtime->scene = scene;
    runtime->vertex_count = vertex_count;
    runtime->mesh_count = scene->mNumMeshes;
    if (!count_nodes(scene->mRootNode, 0U, &runtime->node_count) ||
        runtime->node_count == 0U) {
        vc_model_runtime_release(runtime);
        return NULL;
    }

    runtime->source_vertices = malloc(vertex_count * sizeof(*source_vertices));
    runtime->mesh_vertex_base = calloc(runtime->mesh_count + 1U,
                                       sizeof(*runtime->mesh_vertex_base));
    runtime->mesh_bone_base = calloc(runtime->mesh_count + 1U,
                                     sizeof(*runtime->mesh_bone_base));
    runtime->vertex_mesh_index = malloc(vertex_count *
                                        sizeof(*runtime->vertex_mesh_index));
    runtime->weight_offsets = calloc(vertex_count + 1U,
                                     sizeof(*runtime->weight_offsets));
    runtime->nodes = calloc(runtime->node_count, sizeof(*runtime->nodes));
    runtime->mesh_nodes = calloc(runtime->mesh_count,
                                 sizeof(*runtime->mesh_nodes));
    runtime->global_matrices = calloc(runtime->node_count,
                                      sizeof(*runtime->global_matrices));
    if (runtime->source_vertices == NULL ||
        runtime->mesh_vertex_base == NULL ||
        runtime->mesh_bone_base == NULL ||
        runtime->vertex_mesh_index == NULL ||
        runtime->weight_offsets == NULL || runtime->nodes == NULL ||
        runtime->mesh_nodes == NULL || runtime->global_matrices == NULL) {
        vc_model_runtime_release(runtime);
        return NULL;
    }
    memcpy(runtime->source_vertices, source_vertices,
           vertex_count * sizeof(*source_vertices));

    size_t node_cursor = 0;
    if (!flatten_nodes(runtime, scene->mRootNode, &node_cursor) ||
        node_cursor != runtime->node_count || !build_mesh_offsets(runtime)) {
        vc_model_runtime_release(runtime);
        return NULL;
    }
    for (size_t mesh_index = 0; mesh_index < runtime->mesh_count;
         ++mesh_index) {
        for (size_t vertex = runtime->mesh_vertex_base[mesh_index];
             vertex < runtime->mesh_vertex_base[mesh_index + 1U]; ++vertex) {
            runtime->vertex_mesh_index[vertex] = (uint32_t)mesh_index;
        }
    }

    if (runtime->bone_count != 0U) {
        runtime->bones = calloc(runtime->bone_count, sizeof(*runtime->bones));
        runtime->bone_matrices = calloc(runtime->bone_count,
                                        sizeof(*runtime->bone_matrices));
    }
    if (runtime->weight_count != 0U) {
        runtime->weights = calloc(runtime->weight_count,
                                  sizeof(*runtime->weights));
    }
    if ((runtime->bone_count != 0U &&
         (runtime->bones == NULL || runtime->bone_matrices == NULL)) ||
        (runtime->weight_count != 0U && runtime->weights == NULL) ||
        !populate_bones_and_weights(runtime)) {
        vc_model_runtime_release(runtime);
        return NULL;
    }

    runtime->inverse_root = scene->mRootNode->mTransformation;
    const float determinant = aiMatrix4Determinant(&runtime->inverse_root);
    if (!isfinite(determinant) || fabsf(determinant) <= FLT_EPSILON) {
        vc_model_runtime_release(runtime);
        return NULL;
    }
    aiMatrix4Inverse(&runtime->inverse_root);
    if (!matrix_is_finite(&runtime->inverse_root)) {
        vc_model_runtime_release(runtime);
        return NULL;
    }
    if (scene->mNumAnimations > 1U) {
        fprintf(stderr,
                "model: PORTME: %u animations imported; preview evaluates "
                "animation 0 only\n",
                scene->mNumAnimations);
    }
    return runtime;
}

size_t vc_model_runtime_bone_count(const VcModelRuntime *runtime)
{
    return runtime != NULL ? runtime->bone_count : 0U;
}

size_t vc_model_runtime_weight_count(const VcModelRuntime *runtime)
{
    return runtime != NULL ? runtime->weight_count : 0U;
}

bool vc_model_runtime_is_animated(const VcModelRuntime *runtime)
{
    return runtime != NULL && runtime->scene->mNumAnimations != 0U;
}

void vc_model_runtime_release(VcModelRuntime *runtime)
{
    if (runtime == NULL) {
        return;
    }
    free(runtime->source_vertices);
    free(runtime->mesh_vertex_base);
    free(runtime->mesh_bone_base);
    free(runtime->vertex_mesh_index);
    free(runtime->weight_offsets);
    free(runtime->weights);
    free(runtime->bones);
    free(runtime->nodes);
    free(runtime->mesh_nodes);
    free(runtime->global_matrices);
    free(runtime->bone_matrices);
    free(runtime);
}

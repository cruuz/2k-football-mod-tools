#include <assimp/Importer.hpp>
#include <assimp/postprocess.h>
#include <assimp/scene.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

namespace {

[[noreturn]] void fail(const std::string &message) {
    std::cerr << "APF_PLAYER_SHADOW_SURFACE_ASSIMP_FAIL " << message << '\n';
    std::exit(1);
}

void require(bool condition, const std::string &message) {
    if (!condition) fail(message);
}

} // namespace

int main(int argc, char **argv) {
    if (argc != 2) {
        std::cerr << "usage: " << argv[0] << " player_shadow_surface.gltf\n";
        return 2;
    }
    Assimp::Importer importer;
    const aiScene *scene = importer.ReadFile(
        argv[1], aiProcess_ValidateDataStructure | aiProcess_Triangulate);
    if (scene == nullptr) fail(importer.GetErrorString());
    require(scene->mNumMeshes == 1, "expected one mesh");
    const aiMesh *mesh = scene->mMeshes[0];
    require(mesh->mNumVertices == 351, "expected 351 vertices");
    require(mesh->mNumFaces == 306, "expected 306 triangles");
    require(mesh->HasNormals(), "NORMAL was not imported");
    require(mesh->HasTextureCoords(0), "TEXCOORD_0 was not imported");
    require(mesh->mNumUVComponents[0] == 2, "TEXCOORD_0 is not two-dimensional");
    require(!mesh->HasTangentsAndBitangents(),
            "unproved tangent/handedness was unexpectedly emitted");
    require(mesh->mNumBones == 21, "skin joints were not retained");

    float min_u = mesh->mTextureCoords[0][0].x;
    float max_u = min_u;
    float min_v = mesh->mTextureCoords[0][0].y;
    float max_v = min_v;
    for (unsigned index = 0; index < mesh->mNumVertices; ++index) {
        const aiVector3D &normal = mesh->mNormals[index];
        const float length = std::sqrt(normal.x * normal.x + normal.y * normal.y +
                                       normal.z * normal.z);
        require(std::abs(length - 1.0f) < 0.001f, "normal is not unit length");
        const aiVector3D &uv = mesh->mTextureCoords[0][index];
        min_u = std::min(min_u, uv.x);
        max_u = std::max(max_u, uv.x);
        min_v = std::min(min_v, uv.y);
        max_v = std::max(max_v, uv.y);
    }
    require(std::abs(min_u - 0.0628070906f) < 1e-6f, "minimum U changed");
    require(std::abs(max_u - 1.62755215f) < 1e-6f, "maximum U changed");
    // Assimp presents glTF V as 1-sourceV.  Validate that documented importer
    // convention explicitly; the binary-level validator checks source V.
    require(std::abs(min_v - (-0.0000305176f)) < 1e-6f,
            "Assimp-converted minimum V changed");
    require(std::abs(max_v - 1.62752157f) < 1e-6f,
            "Assimp-converted maximum V changed");

    std::cout << "APF_PLAYER_SHADOW_SURFACE_ASSIMP_PASS "
                 "vertices=351 triangles=306 normals=351 uv0=351 joints=21 "
                 "material_binding=withheld\n";
    return 0;
}

// Minimal XEX2 payload extractor for reverse-engineering reports.
//
// This intentionally stops before XenonRecomp patches import thunks, so the
// resulting PE memory image still contains the original import ordinal words.
// It reuses XenonRecomp's pinned XEX structures, tiny-AES and libmspack LZX
// implementation already vendored in this workspace.

#include <aes.hpp>
#include <TinySHA1.hpp>

#include "xex.h"
#include "xex_patcher.h"

#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <string>
#include <vector>

namespace {

bool readFile(const std::string& path, std::vector<uint8_t>& data) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        return false;
    }
    data.assign(std::istreambuf_iterator<char>(stream),
                std::istreambuf_iterator<char>());
    return stream.good() || stream.eof();
}

bool writeFile(const std::string& path, const uint8_t* data, size_t size) {
    std::ofstream stream(path, std::ios::binary | std::ios::trunc);
    stream.write(reinterpret_cast<const char*>(data),
                 static_cast<std::streamsize>(size));
    return stream.good();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: xex_extract_pe INPUT.xex OUTPUT.pe\n";
        return 2;
    }

    std::vector<uint8_t> module;
    if (!readFile(argv[1], module) || module.size() < sizeof(Xex2Header)) {
        std::cerr << "could not read input\n";
        return 3;
    }

    const auto* header = reinterpret_cast<const Xex2Header*>(module.data());
    if (header->magic != 0x58455832U) {
        std::cerr << "input is not XEX2\n";
        return 4;
    }
    if (header->headerSize > module.size() ||
        header->securityOffset + sizeof(Xex2SecurityInfo) > module.size()) {
        std::cerr << "XEX2 header offsets are out of range\n";
        return 5;
    }

    const auto* security = reinterpret_cast<const Xex2SecurityInfo*>(
        module.data() + header->securityOffset);
    const auto* format = reinterpret_cast<const Xex2OptFileFormatInfo*>(
        getOptHeaderPtr(module.data(), XEX_HEADER_FILE_FORMAT_INFO));
    if (format == nullptr) {
        std::cerr << "XEX2 has no file-format optional header\n";
        return 6;
    }
    if (format->compressionType != XEX_COMPRESSION_NORMAL) {
        std::cerr << "only normal LZX compression is supported by this tool\n";
        return 7;
    }

    const size_t payloadSize = module.size() - header->headerSize;
    std::vector<uint8_t> payload(payloadSize);
    std::memcpy(payload.data(), module.data() + header->headerSize, payloadSize);

    if (format->encryptionType == XEX_ENCRYPTION_NORMAL) {
        std::array<uint8_t, 16> sessionKey{};
        std::memcpy(sessionKey.data(), security->aesKey, sessionKey.size());

        AES_ctx context;
        AES_init_ctx_iv(&context, Xex2RetailKey, AESBlankIV);
        AES_CBC_decrypt_buffer(&context, sessionKey.data(), sessionKey.size());
        AES_init_ctx_iv(&context, sessionKey.data(), AESBlankIV);
        AES_CBC_decrypt_buffer(&context, payload.data(), payload.size());
    } else if (format->encryptionType != XEX_ENCRYPTION_NONE) {
        std::cerr << "unsupported XEX2 encryption type\n";
        return 8;
    }

    const auto* normal = reinterpret_cast<const Xex2FileNormalCompressionInfo*>(
        format + 1);
    const Xex2CompressedBlockInfo* block = &normal->firstBlock;
    const uint8_t* cursor = payload.data();
    const uint8_t* payloadEnd = payload.data() + payload.size();
    std::vector<uint8_t> lzx;
    sha1::SHA1 sha;
    size_t blockCount = 0;
    size_t chunkCount = 0;

    while (block->blockSize != 0) {
        const size_t blockSize = block->blockSize;
        if (blockSize < sizeof(Xex2CompressedBlockInfo) ||
            cursor + blockSize > payloadEnd) {
            std::cerr << "compressed block is out of range\n";
            return 9;
        }

        std::array<uint8_t, 20> digest{};
        sha.reset();
        sha.processBytes(cursor, blockSize);
        sha.finalize(digest.data());
        if (std::memcmp(digest.data(), block->blockHash, digest.size()) != 0) {
            std::cerr << "compressed block SHA-1 mismatch at block "
                      << blockCount << "\n";
            return 10;
        }

        const uint8_t* nextBlockBytes = cursor;
        const uint8_t* chunk = cursor + sizeof(Xex2CompressedBlockInfo);
        const uint8_t* blockEnd = cursor + blockSize;
        while (true) {
            if (chunk + 2 > blockEnd) {
                std::cerr << "truncated LZX chunk length\n";
                return 11;
            }
            const size_t chunkSize =
                (static_cast<size_t>(chunk[0]) << 8) | chunk[1];
            chunk += 2;
            if (chunkSize == 0) {
                break;
            }
            if (chunk + chunkSize > blockEnd) {
                std::cerr << "LZX chunk is out of range\n";
                return 12;
            }
            lzx.insert(lzx.end(), chunk, chunk + chunkSize);
            chunk += chunkSize;
            ++chunkCount;
        }

        cursor = blockEnd;
        block = reinterpret_cast<const Xex2CompressedBlockInfo*>(nextBlockBytes);
        ++blockCount;
    }

    std::vector<uint8_t> image(security->imageSize);
    const int lzxResult = lzxDecompress(
        lzx.data(), lzx.size(), image.data(), image.size(),
        normal->windowSize, nullptr, 0);
    if (lzxResult != 0) {
        std::cerr << "libmspack LZX decompression failed with code "
                  << lzxResult << "\n";
        return 13;
    }
    if (image.size() < 2 || image[0] != 'M' || image[1] != 'Z') {
        std::cerr << "decompressed image does not begin with MZ\n";
        return 14;
    }
    if (!writeFile(argv[2], image.data(), image.size())) {
        std::cerr << "could not write output\n";
        return 15;
    }

    std::cout << "blocks=" << blockCount << " chunks=" << chunkCount
              << " lzx_bytes=" << lzx.size()
              << " image_bytes=" << image.size()
              << " window_size=" << static_cast<uint32_t>(normal->windowSize)
              << "\n";
    return 0;
}

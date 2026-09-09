// Thin offline adapter to an independently installed XenonUtils XexPatcher.
// Contains no retail code, keys, or payload. See ASTRA_REPORT.md for build/pins.
// Pass fresh, external scratch output paths: PE output, patched header output.
#include "xex_patcher.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

static std::vector<uint8_t> read(const char* p) {
    std::ifstream f(p, std::ios::binary);
    if (!f) throw std::runtime_error("cannot open input");
    return {std::istreambuf_iterator<char>(f), {}};
}

static uint32_t be32(const std::vector<uint8_t>& data, size_t offset) {
    if (offset > data.size() || data.size() - offset < 4) throw std::runtime_error("truncated XEX field");
    return uint32_t(data[offset]) << 24 | uint32_t(data[offset + 1]) << 16 |
           uint32_t(data[offset + 2]) << 8 | data[offset + 3];
}

int main(int argc, char** argv) {
    try {
        if (argc != 5) throw std::runtime_error("usage: apply base.xex default.xexp scratch.pe scratch.header");
        for (int i : {3, 4}) {
            if (std::filesystem::exists(argv[i])) throw std::runtime_error("output must be fresh");
        }
        if (std::filesystem::absolute(argv[3]) == std::filesystem::absolute(argv[4]))
            throw std::runtime_error("outputs must differ");
        auto base = read(argv[1]), patch = read(argv[2]);
        if (base.size() != 38408192 || patch.size() != 776192)
            throw std::runtime_error("unexpected APF input sizes; verify SHA-256 pins before calling");
        std::vector<uint8_t> out;
        auto result = XexPatcher::apply(base.data(), base.size(), patch.data(), patch.size(), out, false);
        if (result != XexPatcher::Result::Success) throw std::runtime_error("XEX delta application failed");
        if (be32(out, 0) != 0x58455832) throw std::runtime_error("invalid patched XEX header");
        uint32_t so = be32(out, 0x10), ho = be32(out, 8);
        if (uint64_t(so) + 0x184 > ho) throw std::runtime_error("invalid security range");
        uint32_t size = be32(out, so + 4);
        if (uint64_t(ho) + size > out.size() || size != 54001664) throw std::runtime_error("invalid PE range");
        std::ofstream pe(argv[3], std::ios::binary), header(argv[4], std::ios::binary);
        pe.write(reinterpret_cast<const char*>(out.data() + ho), size);
        header.write(reinterpret_cast<const char*>(out.data()), ho);
        pe.close(); header.close();
        if (!pe || !header) throw std::runtime_error("output write failed");
        std::cout << "delta_result=success header_size=" << ho << " image_size=" << size << '\n';
        return 0;
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}

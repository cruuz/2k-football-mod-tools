// Decode selected APF retail XEX addresses through the vendored XenonRecomp
// image loader and PowerPC/VMX128 opcode table.
//
// Usage:
//   apf_xex_opcode_site_dump default.xex 0x8463847C 0x8465FB38 ...
//
// The output is deterministic TSV. The XEX is decrypted/decompressed only in
// memory; this tool never writes or modifies the source executable.

#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>

#include "disasm.h"
#include "file.h"
#include "image.h"

namespace {

std::string hex32(std::uint32_t value) {
    std::ostringstream stream;
    stream << "0x" << std::uppercase << std::hex << std::setfill('0')
           << std::setw(8) << value;
    return stream.str();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: apf_xex_opcode_site_dump XEX ADDRESS...\n";
        return 2;
    }

    const auto module = LoadFile(std::filesystem::path(argv[1]));
    if (module.empty()) {
        std::cerr << "cannot read XEX\n";
        return 2;
    }
    auto image = Image::ParseImage(module.data(), module.size());
    if (!image.data) {
        std::cerr << "cannot load XEX image\n";
        return 1;
    }

    std::cout << "address\traw\tmnemonic\toperands";
    for (int index = 0; index < 8; ++index) {
        std::cout << "\toperand" << index;
    }
    std::cout << '\n';

    for (int argument = 2; argument < argc; ++argument) {
        char* end = nullptr;
        const auto parsed = std::strtoull(argv[argument], &end, 0);
        if (!end || *end != '\0' || parsed > UINT32_MAX) {
            std::cerr << "invalid address: " << argv[argument] << '\n';
            return 2;
        }
        const auto address = static_cast<std::uint32_t>(parsed);
        ppc_insn instruction{};
        if (ppc::Disassemble(image.Find(address), address, instruction) != 4 ||
            !instruction.opcode) {
            std::cerr << "cannot decode " << hex32(address) << '\n';
            return 1;
        }
        std::cout << hex32(address) << '\t' << hex32(instruction.instruction)
                  << '\t' << instruction.opcode->name << '\t'
                  << instruction.op_str;
        for (std::uint32_t operand : instruction.operands) {
            std::cout << '\t' << operand;
        }
        std::cout << '\n';
    }
    return 0;
}

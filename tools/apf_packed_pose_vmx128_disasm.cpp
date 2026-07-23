// Decode raw PowerPC/Xenon instruction words emitted by the focused Ghidra trace.
//
// This intentionally delegates opcode identification to the vendored
// XenonRecomp disassembler, whose table includes the Xbox 360 VMX128 extension
// that stock Ghidra currently truncates.  Input lines must contain either:
//
//   RAW32 0x84638450 0x39600008
//   0x84638450 raw=0x39600008
//
// Output is a deterministic TSV suitable for byte-for-byte validation.

#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <regex>
#include <sstream>
#include <string>

#include "disasm.h"

namespace {

std::string hex32(std::uint32_t value) {
    std::ostringstream stream;
    stream << "0x" << std::uppercase << std::hex << std::setfill('0')
           << std::setw(8) << value;
    return stream.str();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: apf_packed_pose_vmx128_disasm TRACE OUTPUT_TSV\n";
        return 2;
    }

    std::ifstream input(argv[1]);
    if (!input) {
        std::cerr << "cannot read " << argv[1] << "\n";
        return 2;
    }
    std::ofstream output(argv[2]);
    if (!output) {
        std::cerr << "cannot write " << argv[2] << "\n";
        return 2;
    }

    const std::regex canonical(
        R"(^RAW32 (0x[0-9A-Fa-f]{8}) (0x[0-9A-Fa-f]{8})$)");
    const std::regex probe(
        R"(^(0x[0-9A-Fa-f]{8}) raw=(0x[0-9A-Fa-f]{8})$)");
    output << "address\traw\tmnemonic\toperands\topcode_id\n";

    std::string line;
    std::size_t count = 0;
    while (std::getline(input, line)) {
        std::smatch match;
        if (!std::regex_match(line, match, canonical) &&
            !std::regex_match(line, match, probe)) {
            continue;
        }
        const auto address = static_cast<std::uint32_t>(
            std::stoul(match[1].str(), nullptr, 16));
        const auto raw = static_cast<std::uint32_t>(
            std::stoul(match[2].str(), nullptr, 16));
        const std::uint8_t bytes[4] = {
            static_cast<std::uint8_t>(raw >> 24),
            static_cast<std::uint8_t>(raw >> 16),
            static_cast<std::uint8_t>(raw >> 8),
            static_cast<std::uint8_t>(raw),
        };
        ppc_insn instruction{};
        const int decoded = ppc::Disassemble(bytes, sizeof(bytes), address, instruction);
        if (decoded != 4) {
            std::cerr << "could not decode " << hex32(address) << "\n";
            return 1;
        }
        const char* mnemonic = instruction.opcode ? instruction.opcode->name : ".long";
        const int opcode_id = instruction.opcode ? instruction.opcode->id : 0;
        output << hex32(address) << '\t' << hex32(raw) << '\t' << mnemonic << '\t'
               << instruction.op_str << '\t' << opcode_id << '\n';
        ++count;
    }
    if (count == 0) {
        std::cerr << "trace contained no RAW32 records\n";
        return 1;
    }
    std::cout << "APF_PACKED_POSE_VMX128_DISASM_COMPLETE instructions=" << count << "\n";
    return 0;
}

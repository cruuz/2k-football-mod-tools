// Read the two Newton-refinement constants used by APF 2K8's scalar frsqrte
// sites from the decrypted in-memory XEX image. The source XEX is read-only.

#include <bit>
#include <cstdint>
#include <filesystem>
#include <iomanip>
#include <iostream>

#include "file.h"
#include "image.h"

namespace {

constexpr std::uint32_t kAddresses[] = {0x82000A80, 0x82000B18};

std::uint32_t LoadBigEndian32(const void* source) {
  const auto* bytes = static_cast<const std::uint8_t*>(source);
  return (static_cast<std::uint32_t>(bytes[0]) << 24) |
         (static_cast<std::uint32_t>(bytes[1]) << 16) |
         (static_cast<std::uint32_t>(bytes[2]) << 8) |
         static_cast<std::uint32_t>(bytes[3]);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "usage: apf_frsqrte_xex_evidence default.xex\n";
    return 2;
  }
  const auto module = LoadFile(std::filesystem::path(argv[1]));
  if (module.empty()) {
    std::cerr << "cannot read XEX\n";
    return 2;
  }
  const auto image = Image::ParseImage(module.data(), module.size());
  if (!image.data) {
    std::cerr << "cannot load XEX image\n";
    return 1;
  }

  std::cout << "address\traw_be\tfloat32\trole\n";
  for (std::size_t index = 0; index < std::size(kAddresses); ++index) {
    const std::uint32_t address = kAddresses[index];
    const std::uint32_t bits = LoadBigEndian32(image.Find(address));
    const float value = std::bit_cast<float>(bits);
    std::cout << "0x" << std::uppercase << std::hex << std::setfill('0')
              << std::setw(8) << address << "\t0x" << std::setw(8) << bits
              << std::dec << "\t" << value << "\t"
              << (index == 0 ? "half_input" : "newton_three_halves")
              << "\n";
  }
  return 0;
}

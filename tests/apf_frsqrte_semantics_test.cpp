// Differential and numerical tests for APF 2K8's scalar PowerPC frsqrte sites.
//
// This deliberately keeps three models separate:
//   * CandidateValue is the clean value-only helper proposed for XenonRecomp.
//   * XeniaX64Reference follows Xenia Canary 6e5b832's x64 helper control flow.
//   * XeniaA64Reference follows the same release's A64 PpcFrsqrte helper.
//
// None of these models claims FPSCR or enabled-exception behavior.

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>

namespace {

constexpr std::uint64_t kSign = UINT64_C(0x8000000000000000);
constexpr std::uint64_t kExponent = UINT64_C(0x7FF0000000000000);
constexpr std::uint64_t kMantissa = UINT64_C(0x000FFFFFFFFFFFFF);
constexpr std::uint64_t kQuiet = UINT64_C(0x0008000000000000);
constexpr std::uint64_t kCanonicalQNaN = UINT64_C(0x7FF8000000000000);
constexpr std::uint8_t kEstimateTable[16] = {
    241, 216, 192, 168, 152, 136, 128, 112,
    96,  76,  60,  48,  32,  24,  16,  8,
};

[[noreturn]] void Fail(const char* message) {
  std::fprintf(stderr, "APF_FRSQRTE_TEST_FAIL %s\n", message);
  std::exit(1);
}

std::uint64_t CandidateValue(std::uint64_t bits, bool non_ieee) {
  const bool negative = (bits & kSign) != 0;
  std::uint32_t exponent = static_cast<std::uint32_t>((bits >> 52) & 0x7FF);
  std::uint64_t mantissa = bits & kMantissa;

  if (exponent == 0x7FF && mantissa != 0) {
    return bits | kQuiet;
  }
  if (exponent == 0 && mantissa == 0) {
    return (bits & kSign) | kExponent;
  }
  if (exponent == 0x7FF && !negative) {
    return 0;
  }
  if (non_ieee && exponent == 0) {
    return (bits & kSign) | kExponent;
  }
  if (negative) {
    return kCanonicalQNaN;
  }

  std::int32_t effective_exponent = static_cast<std::int32_t>(exponent);
  std::uint64_t normalized_mantissa = mantissa;
  if (exponent == 0) {
    const int leading_zeroes = __builtin_clzll(mantissa);
    normalized_mantissa = mantissa << (leading_zeroes - 11);
    effective_exponent = 12 - leading_zeroes;
  }

  const std::uint32_t top_three =
      static_cast<std::uint32_t>((normalized_mantissa >> 49) & 7);
  const std::uint32_t index =
      ((((static_cast<std::uint32_t>(effective_exponent) & 1) << 3) |
        top_three) ^
       8);
  const std::int32_t unbiased = effective_exponent - 1023;
  const std::int32_t half = unbiased >> 1;
  const std::uint32_t result_exponent =
      static_cast<std::uint32_t>(1022 - half);
  return (static_cast<std::uint64_t>(result_exponent) << 52) |
         (static_cast<std::uint64_t>(kEstimateTable[index]) << 44);
}

// Source-level transcription of the decision order in
// X64HelperEmitter::EmitFrsqrteHelper at Xenia Canary 6e5b832.
std::uint64_t XeniaX64Reference(std::uint64_t bits, bool non_ieee) {
  const std::uint64_t magnitude = bits & ~kSign;
  const std::uint64_t mantissa = bits & kMantissa;
  const std::uint32_t exponent =
      static_cast<std::uint32_t>((bits >> 52) & 0x7FF);

  if (non_ieee && exponent == 0 && mantissa != 0) {
    return (bits & kSign) | kExponent;
  }
  if (magnitude == 0) {
    return (bits & kSign) | kExponent;
  }
  if (exponent == 0x7FF) {
    if (bits == kExponent) {
      return 0;
    }
    if (mantissa != 0) {
      return bits | kCanonicalQNaN;
    }
    return kCanonicalQNaN;
  }
  if ((bits & kSign) != 0) {
    return kCanonicalQNaN;
  }

  std::int32_t effective_exponent = static_cast<std::int32_t>(exponent);
  std::uint64_t normalized_mantissa = mantissa;
  if (exponent == 0) {
    const int leading_zeroes = __builtin_clzll(mantissa);
    normalized_mantissa = mantissa << (leading_zeroes - 11);
    effective_exponent = 12 - leading_zeroes;
  }
  std::uint32_t index =
      ((static_cast<std::uint32_t>(effective_exponent) & 1) << 3) |
      static_cast<std::uint32_t>((normalized_mantissa >> 49) & 7);
  index ^= 8;
  const std::int32_t result_exponent =
      1022 - ((effective_exponent - 1023) >> 1);
  return (static_cast<std::uint64_t>(result_exponent) << 52) |
         (static_cast<std::uint64_t>(kEstimateTable[index]) << 44);
}

// Xenia's pinned A64 helper is integer-only and does not consult the backend's
// NonIEEE flag. This wrapper makes that omission explicit.
std::uint64_t XeniaA64Reference(std::uint64_t bits) {
  return CandidateValue(bits, false);
}

struct KnownVector {
  std::uint64_t input;
  std::uint64_t output;
  std::uint32_t record_cr;
};

// Exact checked-in expectations from Xenia's instr__gen_frsqrte.s at commit
// 6e5b8324f4101464de0f8c2334edb03cac8826c4. The repository history identifies
// them as generated tests and contains a native PowerPC runner; this is strong
// provenance, but not a dense arbitrary-input Xenon hardware capture.
constexpr KnownVector kKnownVectors[] = {
    {UINT64_C(0x0000000000000000), UINT64_C(0x7FF0000000000000),
     UINT32_C(0x08000000)},
    {UINT64_C(0x8000000000000000), UINT64_C(0xFFF0000000000000),
     UINT32_C(0x08000000)},
    {UINT64_C(0x0000000000000001), UINT64_C(0x617F100000000000), 0},
    {UINT64_C(0x000FFFFFFFFFFFFF), UINT64_C(0x5FE0800000000000), 0},
    {UINT64_C(0x3FF0000000000000), UINT64_C(0x3FEF100000000000), 0},
    {UINT64_C(0xBFF0000000000000), UINT64_C(0x7FF8000000000000),
     UINT32_C(0x0A000000)},
    {UINT64_C(0xC1E0000000000000), UINT64_C(0x7FF8000000000000),
     UINT32_C(0x0A000000)},
    {UINT64_C(0x41DFFFFFFFC00000), UINT64_C(0x3EF7000000000000), 0},
    {UINT64_C(0x7FF0000000000000), UINT64_C(0x0000000000000000), 0},
    {UINT64_C(0xFFF0000000000000), UINT64_C(0x7FF8000000000000),
     UINT32_C(0x0A000000)},
    {UINT64_C(0xFFF8000000000000), UINT64_C(0xFFF8000000000000), 0},
    {UINT64_C(0xFFF4000000000000), UINT64_C(0xFFFC000000000000),
     UINT32_C(0x0A000000)},
};

constexpr KnownVector kLegacyVectors[] = {
    {UINT64_C(0x4010000000000000), UINT64_C(0x3FDF100000000000), 0},
    {UINT64_C(0x4030000000000000), UINT64_C(0x3FCF100000000000), 0},
    {UINT64_C(0x3FF0000000000000), UINT64_C(0x3FEF100000000000), 0},
    {UINT64_C(0x4022000000000000), UINT64_C(0x3FD4C00000000000), 0},
};

float MulSingle(float a, float b) {
  volatile float result = a * b;
  return result;
}

float NegativeMultiplySubtractSingle(float a, float b, float c) {
  volatile float result = std::fma(-a, b, c);
  return result;
}

float RefineLikeApf(float input, float seed, int rounds) {
  const float half_input = MulSingle(input, 0.5f);
  for (int round = 0; round < rounds; ++round) {
    const float product = MulSingle(half_input, seed);
    const float correction =
        NegativeMultiplySubtractSingle(product, seed, 1.5f);
    seed = MulSingle(correction, seed);
  }
  return seed;
}

std::uint32_t UlpDistance(std::uint32_t a, std::uint32_t b) {
  return a > b ? a - b : b - a;
}

}  // namespace

int main() {
  std::uint64_t known_mismatches = 0;
  for (const KnownVector& vector : kKnownVectors) {
    if (CandidateValue(vector.input, false) != vector.output ||
        XeniaX64Reference(vector.input, false) != vector.output ||
        XeniaA64Reference(vector.input) != vector.output) {
      ++known_mismatches;
    }
  }
  std::uint64_t legacy_mismatches = 0;
  for (const KnownVector& vector : kLegacyVectors) {
    if (CandidateValue(vector.input, false) != vector.output) {
      ++legacy_mismatches;
    }
  }
  if (known_mismatches != 0 || legacy_mismatches != 0) {
    Fail("checked-in Xenia vector mismatch");
  }

  // Mix structured boundary values with a deterministic pseudorandom corpus.
  std::uint64_t differential_cases = 0;
  std::uint64_t ieee_x64_mismatches = 0;
  std::uint64_t ieee_a64_mismatches = 0;
  auto CheckDifferential = [&](std::uint64_t bits) {
    const std::uint64_t candidate = CandidateValue(bits, false);
    ieee_x64_mismatches += candidate != XeniaX64Reference(bits, false);
    ieee_a64_mismatches += candidate != XeniaA64Reference(bits);
    ++differential_cases;
  };
  for (std::uint32_t exponent = 0; exponent <= 0x7FF; ++exponent) {
    for (std::uint32_t top = 0; top < 8; ++top) {
      const std::uint64_t base =
          (static_cast<std::uint64_t>(exponent) << 52) |
          (static_cast<std::uint64_t>(top) << 49);
      CheckDifferential(base);
      CheckDifferential(base | ((UINT64_C(1) << 49) - 1));
      CheckDifferential(base | kSign);
      CheckDifferential(base | ((UINT64_C(1) << 49) - 1) | kSign);
    }
  }
  std::uint64_t random_state = UINT64_C(0xD1B54A32D192ED03);
  constexpr std::uint64_t kRandomCases = 2000000;
  for (std::uint64_t index = 0; index < kRandomCases; ++index) {
    random_state ^= random_state >> 12;
    random_state ^= random_state << 25;
    random_state ^= random_state >> 27;
    CheckDifferential(random_state * UINT64_C(0x2545F4914F6CDD1D));
  }
  if (ieee_x64_mismatches != 0 || ieee_a64_mismatches != 0) {
    Fail("candidate differs from a pinned Xenia IEEE value path");
  }

  constexpr std::uint64_t kSubnormalMantissas[] = {
      1,
      2,
      3,
      UINT64_C(0x0000000000010),
      UINT64_C(0x0000000010000),
      UINT64_C(0x0000100000000),
      UINT64_C(0x0008000000000),
      UINT64_C(0x000FFFFFFFFFFFFF),
  };
  std::uint64_t non_ieee_subnormal_cases = 0;
  std::uint64_t non_ieee_x64_a64_divergences = 0;
  for (std::uint64_t mantissa : kSubnormalMantissas) {
    for (std::uint64_t sign : {UINT64_C(0), kSign}) {
      const std::uint64_t bits = sign | mantissa;
      const std::uint64_t x64 = XeniaX64Reference(bits, true);
      const std::uint64_t a64 = XeniaA64Reference(bits);
      if (CandidateValue(bits, true) != x64) {
        Fail("candidate non-IEEE path differs from pinned Xenia x64");
      }
      non_ieee_x64_a64_divergences += x64 != a64;
      ++non_ieee_subnormal_cases;
    }
  }
  if (non_ieee_x64_a64_divergences != non_ieee_subnormal_cases) {
    Fail("expected Xenia cross-backend non-IEEE divergence not observed");
  }

  // The table depends only on exponent parity and the top three mantissa bits.
  // Therefore both ends of its 16 buckets are sufficient to establish the
  // positive-normal relative-error maximum for the value table.
  std::uint64_t bucket_endpoints = 0;
  double maximum_raw_relative_error = 0.0;
  for (std::uint32_t exponent : {UINT32_C(1022), UINT32_C(1023)}) {
    for (std::uint32_t top = 0; top < 8; ++top) {
      const std::uint64_t low =
          (static_cast<std::uint64_t>(exponent) << 52) |
          (static_cast<std::uint64_t>(top) << 49);
      const std::uint64_t high = low | ((UINT64_C(1) << 49) - 1);
      for (std::uint64_t bits : {low, high}) {
        const double input = std::bit_cast<double>(bits);
        const double estimate =
            std::bit_cast<double>(CandidateValue(bits, false));
        const double exact = 1.0 / std::sqrt(input);
        maximum_raw_relative_error =
            std::max(maximum_raw_relative_error,
                     std::abs(estimate - exact) / exact);
        ++bucket_endpoints;
      }
    }
  }
  if (maximum_raw_relative_error > (1.0 / 32.0) + 1e-15) {
    Fail("estimate violates the architectural one-part-in-32 bound");
  }

  // APF's 28 sites round the seed to float and perform two Newton corrections.
  // Exercise every exponent with all top 16 fraction bits plus a deterministic
  // seven-bit tail. This does not claim exhaustive float coverage.
  std::uint64_t refinement_cases = 0;
  std::uint64_t one_round_seed_path_mismatches = 0;
  std::uint64_t two_round_seed_path_mismatches = 0;
  std::uint64_t one_round_exact_result_mismatches = 0;
  std::uint64_t two_round_exact_result_mismatches = 0;
  std::uint32_t one_round_seed_path_max_ulp = 0;
  std::uint32_t two_round_seed_path_max_ulp = 0;
  std::uint32_t one_round_exact_result_max_ulp = 0;
  std::uint32_t two_round_exact_result_max_ulp = 0;
  double one_round_max_relative_error = 0.0;
  double two_round_max_relative_error = 0.0;
  for (std::uint32_t exponent = 1; exponent < 255; ++exponent) {
    for (std::uint32_t fraction_top = 0; fraction_top < (1U << 16);
         ++fraction_top) {
      const std::uint32_t input_bits =
          (exponent << 23) | (fraction_top << 7) |
          ((fraction_top * UINT32_C(0x9E3779B9)) >> 25);
      const float input = std::bit_cast<float>(input_bits);
      const double input_double = static_cast<double>(input);
      const std::uint64_t input_double_bits =
          std::bit_cast<std::uint64_t>(input_double);
      const float table_seed = static_cast<float>(
          std::bit_cast<double>(CandidateValue(input_double_bits, false)));
      const float exact_seed =
          static_cast<float>(1.0 / std::sqrt(input_double));
      const float table_one = RefineLikeApf(input, table_seed, 1);
      const float exact_one = RefineLikeApf(input, exact_seed, 1);
      const float table_two = RefineLikeApf(input, table_seed, 2);
      const float exact_two = RefineLikeApf(input, exact_seed, 2);
      const float correctly_rounded =
          static_cast<float>(1.0 / std::sqrt(input_double));

      const std::uint32_t table_one_bits =
          std::bit_cast<std::uint32_t>(table_one);
      const std::uint32_t exact_one_bits =
          std::bit_cast<std::uint32_t>(exact_one);
      const std::uint32_t table_two_bits =
          std::bit_cast<std::uint32_t>(table_two);
      const std::uint32_t exact_two_bits =
          std::bit_cast<std::uint32_t>(exact_two);
      const std::uint32_t rounded_bits =
          std::bit_cast<std::uint32_t>(correctly_rounded);

      const std::uint32_t one_seed_ulp =
          UlpDistance(table_one_bits, exact_one_bits);
      const std::uint32_t two_seed_ulp =
          UlpDistance(table_two_bits, exact_two_bits);
      const std::uint32_t one_exact_ulp =
          UlpDistance(table_one_bits, rounded_bits);
      const std::uint32_t two_exact_ulp =
          UlpDistance(table_two_bits, rounded_bits);
      one_round_seed_path_mismatches += one_seed_ulp != 0;
      two_round_seed_path_mismatches += two_seed_ulp != 0;
      one_round_exact_result_mismatches += one_exact_ulp != 0;
      two_round_exact_result_mismatches += two_exact_ulp != 0;
      one_round_seed_path_max_ulp =
          std::max(one_round_seed_path_max_ulp, one_seed_ulp);
      two_round_seed_path_max_ulp =
          std::max(two_round_seed_path_max_ulp, two_seed_ulp);
      one_round_exact_result_max_ulp =
          std::max(one_round_exact_result_max_ulp, one_exact_ulp);
      two_round_exact_result_max_ulp =
          std::max(two_round_exact_result_max_ulp, two_exact_ulp);
      one_round_max_relative_error =
          std::max(one_round_max_relative_error,
                   std::abs(static_cast<double>(table_one) *
                                std::sqrt(input_double) -
                            1.0));
      two_round_max_relative_error =
          std::max(two_round_max_relative_error,
                   std::abs(static_cast<double>(table_two) *
                                std::sqrt(input_double) -
                            1.0));
      ++refinement_cases;
    }
  }

  std::cout << std::setprecision(17);
  std::cout << "{\n"
            << "  \"schema\": \"apf2k8_frsqrte_differential/v1\",\n"
            << "  \"known_vector_count\": " << std::size(kKnownVectors)
            << ",\n"
            << "  \"known_vector_mismatches\": " << known_mismatches
            << ",\n"
            << "  \"legacy_vector_count\": " << std::size(kLegacyVectors)
            << ",\n"
            << "  \"legacy_vector_mismatches\": " << legacy_mismatches
            << ",\n"
            << "  \"source_differential_cases\": " << differential_cases
            << ",\n"
            << "  \"ieee_x64_mismatches\": " << ieee_x64_mismatches
            << ",\n"
            << "  \"ieee_a64_mismatches\": " << ieee_a64_mismatches
            << ",\n"
            << "  \"non_ieee_subnormal_cases\": "
            << non_ieee_subnormal_cases << ",\n"
            << "  \"non_ieee_x64_a64_divergences\": "
            << non_ieee_x64_a64_divergences << ",\n"
            << "  \"normal_bucket_endpoint_count\": " << bucket_endpoints
            << ",\n"
            << "  \"maximum_raw_relative_error\": "
            << maximum_raw_relative_error << ",\n"
            << "  \"architectural_relative_error_bound\": " << (1.0 / 32.0)
            << ",\n"
            << "  \"refinement_corpus_count\": " << refinement_cases << ",\n"
            << "  \"one_round_seed_path_mismatch_count\": "
            << one_round_seed_path_mismatches << ",\n"
            << "  \"one_round_seed_path_max_ulp\": "
            << one_round_seed_path_max_ulp << ",\n"
            << "  \"two_round_seed_path_mismatch_count\": "
            << two_round_seed_path_mismatches << ",\n"
            << "  \"two_round_seed_path_max_ulp\": "
            << two_round_seed_path_max_ulp << ",\n"
            << "  \"one_round_exact_result_mismatch_count\": "
            << one_round_exact_result_mismatches << ",\n"
            << "  \"one_round_exact_result_max_ulp\": "
            << one_round_exact_result_max_ulp << ",\n"
            << "  \"two_round_exact_result_mismatch_count\": "
            << two_round_exact_result_mismatches << ",\n"
            << "  \"two_round_exact_result_max_ulp\": "
            << two_round_exact_result_max_ulp << ",\n"
            << "  \"one_round_max_relative_error\": "
            << one_round_max_relative_error << ",\n"
            << "  \"two_round_max_relative_error\": "
            << two_round_max_relative_error << "\n"
            << "}\n";
  return 0;
}

// Emit focused read-only evidence for the APF 2K8 SingleMoCap packed-pose path.
// Stock Ghidra truncates several Xenon VMX128 opcodes; every raw word is also
// emitted for deterministic decoding by the vendored XenonRecomp table.
// @category Xbox360.APF2K8

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class ApfPackedPoseDecoderTrace extends GhidraScript {
    private static final long[][] RAW_RANGES = {
        { 0x84638450L, 0x846385A8L }, // packed-unit decoder and small variants
        { 0x846385A8L, 0x8463871CL }, // quaternion interpolation helper
        { 0x846394D0L, 0x84639894L }, // frame sampling / unit-output helpers
        { 0x8463A320L, 0x8463A9C8L }, // aggregate pose sampler wrapper/body
        { 0x847C1438L, 0x847C14E0L }, // concrete pose-output caller
        { 0x847C9428L, 0x847C94BCL }, // second concrete pose-output caller
        { 0x84AD12C0L, 0x84AD138CL }, // concrete single-unit decode caller
    };

    private static final long[] FOCUSED_FUNCTIONS = {
        0x84638450L,
        0x846394D0L,
        0x84639670L,
        0x84639790L,
        0x84639838L,
        0x8463A320L,
        0x847C1438L,
        0x847C9428L,
        0x84AD12C0L,
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String addr(Address value) {
        return value == null ? "" : hex(value.getUnsignedOffset());
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<String> referencesTo(Address target) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            values.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        values.sort(String::compareTo);
        return values;
    }

    private Function createBody(long start, long end, String name) throws Exception {
        Address first = address(start);
        Address last = address(end);
        for (Address cursor = first; cursor.compareTo(last) <= 0; cursor = cursor.add(4)) {
            if (currentProgram.getListing().getInstructionAt(cursor) == null) disassemble(cursor);
        }
        Function function = currentProgram.getFunctionManager().getFunctionAt(first);
        if (function != null) return function;
        return currentProgram.getListing().createFunction(
            name, first, new AddressSet(first, last), SourceType.ANALYSIS);
    }

    private List<Function> sorted(Set<Function> functions) {
        List<Function> result = new ArrayList<>(functions);
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
    }

    private void writeFloatConstant(BufferedWriter output, long value, String label)
            throws Exception {
        long raw = Integer.toUnsignedLong(currentProgram.getMemory().getInt(address(value)));
        float decoded = Float.intBitsToFloat((int)raw);
        output.write("CONST_FLOAT " + hex(value) + " raw=" + hex(raw) +
            " float=" + Float.toString(decoded) + " hex=" + Float.toHexString(decoded) +
            " label=" + label + "\n");
    }

    private void writeInstructionProvedPseudoC(BufferedWriter pseudo) throws Exception {
        pseudo.write("/*\n");
        pseudo.write(" * Instruction-proved portable pseudocode for the mode-0 path.\n");
        pseudo.write(" * Component names are deliberately lane0..lane3, not bone axes.\n");
        pseudo.write(" */\n");
        pseudo.write("typedef struct { float lane[4]; } ApfPose4;\n\n");
        pseudo.write("static int32_t apf_sign_extend_20(uint32_t value) {\n");
        pseudo.write("    value &= 0xFFFFF;\n");
        pseudo.write("    return (int32_t)(value << 12) >> 12;\n");
        pseudo.write("}\n\n");
        pseudo.write("static float xenos_vrsqrtefp(float value);\n");
        pseudo.write("// Symbolic single-instruction helpers: vmadd(a,b,c)=a*b+c; vnmsub(a,b,c)=c-a*b.\n");
        pseudo.write("static float xenos_vmaddfp(float left, float right, float addend);\n");
        pseudo.write("static float xenos_vnmsubfp(float left, float right, float addend);\n");
        pseudo.write("// PORTME at 0x846384A8 and 0x84638610: model the Xenon estimate\n");
        pseudo.write("// instruction if bit-exact replay, rather than numerical equivalence, is required.\n\n");
        pseudo.write("static float apf_refined_rsqrt(float value) {\n");
        pseudo.write("    float estimate = xenos_vrsqrtefp(value);\n");
        pseudo.write("    float half_value = 0.5f * value;\n");
        pseudo.write("    float estimate_squared = estimate * estimate;\n");
        pseudo.write("    float correction = xenos_vnmsubfp(half_value, estimate_squared, 0.5f);\n");
        pseudo.write("    return xenos_vmaddfp(estimate, correction, estimate);\n");
        pseudo.write("}\n\n");
        pseudo.write("static float apf_acos_polynomial_0x82000BF0(float x) {\n");
        pseudo.write("    float high = xenos_vmaddfp(x, bitcast_float(0xBAA57A2C),\n");
        pseudo.write("                           bitcast_float(0x3BDA90C5));\n");
        pseudo.write("    float low = xenos_vmaddfp(x, bitcast_float(0xBD4D8392),\n");
        pseudo.write("                          bitcast_float(0x3DB63A9E));\n");
        pseudo.write("    high = xenos_vmaddfp(x, high, bitcast_float(0xBC8BFC66));\n");
        pseudo.write("    low = xenos_vmaddfp(x, low, bitcast_float(0xBE5BBFCA));\n");
        pseudo.write("    high = xenos_vmaddfp(x, high, bitcast_float(0x3CFD10F8));\n");
        pseudo.write("    low = xenos_vmaddfp(x, low, bitcast_float(0x3FC90FDA));\n");
        pseudo.write("    float one_minus_x = 1.0f - x;\n");
        pseudo.write("    float root = one_minus_x == 0.0f ? 0.0f :\n");
        pseudo.write("                 one_minus_x * apf_refined_rsqrt(one_minus_x);\n");
        pseudo.write("    return root * xenos_vmaddfp((x * x) * (x * x), high, low);\n");
        pseudo.write("}\n\n");
        pseudo.write("static float apf_sin_polynomial_0x82000C10(float angle) {\n");
        pseudo.write("    bool use_cosine = angle >= bitcast_float(0x3FC90FDB);\n");
        pseudo.write("    float x = angle - (use_cosine ? bitcast_float(0x3FC90FDB) : 0.0f);\n");
        pseudo.write("    float x2 = x * x;\n");
        pseudo.write("    float sine_tail = xenos_vmaddfp(x2, bitcast_float(0xB94C8C6E),\n");
        pseudo.write("                                 bitcast_float(0x3C088342));\n");
        pseudo.write("    sine_tail = xenos_vmaddfp(x2, sine_tail, bitcast_float(0xBE2AAAA1));\n");
        pseudo.write("    float sine = xenos_vmaddfp(x2 * x, sine_tail, x);\n");
        pseudo.write("    float cosine_tail = xenos_vmaddfp(x2, bitcast_float(0xBAB24993),\n");
        pseudo.write("                                   bitcast_float(0x3D2AA036));\n");
        pseudo.write("    cosine_tail = xenos_vmaddfp(x2, cosine_tail, bitcast_float(0xBEFFFFDF));\n");
        pseudo.write("    float cosine = xenos_vmaddfp(x2, cosine_tail, 1.0f);\n");
        pseudo.write("    return use_cosine ? cosine : sine;\n");
        pseudo.write("}\n\n");
        pseudo.write("static ApfPose4 apf_decode_mode0_be(const uint8_t packed[8]) {\n");
        pseudo.write("    uint64_t bits = load_be64(packed);\n");
        pseudo.write("    uint32_t selector4 = (uint32_t)(bits >> 60);\n");
        pseudo.write("    float scale = 23.0f / 16777216.0f;\n");
        pseudo.write("    float stored[4];\n");
        pseudo.write("    stored[0] = (float)apf_sign_extend_20((uint32_t)(bits >> 0)) * scale;\n");
        pseudo.write("    stored[1] = (float)apf_sign_extend_20((uint32_t)(bits >> 20)) * scale;\n");
        pseudo.write("    stored[2] = (float)apf_sign_extend_20((uint32_t)(bits >> 40)) * scale;\n");
        pseudo.write("    float radicand = 1.0f - (stored[0] * stored[0] +\n");
        pseudo.write("                              stored[1] * stored[1] +\n");
        pseudo.write("                              stored[2] * stored[2]);\n");
        pseudo.write("    stored[3] = radicand * apf_refined_rsqrt(radicand);\n");
        pseudo.write("    uint32_t rotate = selector4 & 3;\n");
        pseudo.write("    ApfPose4 result;\n");
        pseudo.write("    for (uint32_t lane = 0; lane < 4; ++lane)\n");
        pseudo.write("        result.lane[lane] = stored[(lane + rotate) & 3];\n");
        pseudo.write("    return result;\n");
        pseudo.write("}\n\n");
        pseudo.write("static ApfPose4 apf_interpolate_mode0(ApfPose4 left, ApfPose4 right, float t) {\n");
        pseudo.write("    float dot = dot4(left, right);\n");
        pseudo.write("    if (signbit(dot)) right = xor_float_sign_bit_all_lanes(right);\n");
        pseudo.write("    float x = min(abs(dot), 1.0f);\n");
        pseudo.write("    float theta = apf_acos_polynomial_0x82000BF0(x);\n");
        pseudo.write("    float inv_sin_theta = apf_refined_rsqrt(1.0f - x * x);\n");
        pseudo.write("    float right_weight = apf_sin_polynomial_0x82000C10(t * theta) * inv_sin_theta;\n");
        pseudo.write("    float left_weight = apf_sin_polynomial_0x82000C10((1.0f - t) * theta) *\n");
        pseudo.write("                        inv_sin_theta;\n");
        pseudo.write("    bool linear = x >= bitcast_float(0x3F7FF2E5);\n");
        pseudo.write("    right_weight = linear ? t : right_weight;\n");
        pseudo.write("    left_weight = linear ? (1.0f - t) : left_weight;\n");
        pseudo.write("    return add4(mul4s(left, left_weight), mul4s(right, right_weight));\n");
        pseudo.write("}\n\n");
        pseudo.write("static void apf_sample_mode0(const ApfRoot *root, float seconds,\n");
        pseudo.write("                            uint32_t logical_mask, const int8_t *map3,\n");
        pseudo.write("                            ApfPose4 *output) {\n");
        pseudo.write("    uint32_t flags = root->flags_be;\n");
        pseudo.write("    uint32_t rate = (flags >> 9) & 0xFF;\n");
        pseudo.write("    uint32_t units_per_frame = ((flags >> 22) & 31) + ((flags >> 27) & 31);\n");
        pseudo.write("    float frame_coordinate = rate * (seconds * root->time_scale);\n");
        pseudo.write("    uint32_t frame0, frame1; float fraction;\n");
        pseudo.write("    if (frame_coordinate >= (float)(root->sample_count - 1)) {\n");
        pseudo.write("        frame0 = frame1 = root->sample_count - 1; fraction = 0.0f;\n");
        pseudo.write("    } else {\n");
        pseudo.write("        frame0 = (int32_t)trunc_toward_zero(frame_coordinate);\n");
        pseudo.write("        frame1 = frame0 + 1; fraction = frame_coordinate - (float)frame0;\n");
        pseudo.write("    }\n");
        pseudo.write("    uint32_t mirror = (flags >> 6) & 1;\n");
        pseudo.write("    for (uint32_t logical = 0; logical_mask; ++logical, logical_mask >>= 1, ++output) {\n");
        pseudo.write("        if (!(logical_mask & 1)) continue;\n");
        pseudo.write("        uint8_t mode = (uint8_t)map3[logical * 3 + 0];\n");
        pseudo.write("        int32_t packed_index = map3[logical * 3 + 1 + mirror];\n");
        pseudo.write("        if (packed_index < 0) continue;\n");
        pseudo.write("        if (mode != 0) {\n");
        pseudo.write("            // PORTME at 0x8463A4F0: map mode 2 is outside this proof.\n");
        pseudo.write("            // PORTME at 0x8463A52C: map mode 1 is outside this proof.\n");
        pseudo.write("            continue;\n");
        pseudo.write("        }\n");
        pseudo.write("        const uint8_t *a = root->packed_pose +\n");
        pseudo.write("            ((uint64_t)frame0 * units_per_frame + packed_index) * 8;\n");
        pseudo.write("        const uint8_t *b = root->packed_pose +\n");
        pseudo.write("            ((uint64_t)frame1 * units_per_frame + packed_index) * 8;\n");
        pseudo.write("        *output = apf_interpolate_mode0(apf_decode_mode0_be(a),\n");
        pseudo.write("                                        apf_decode_mode0_be(b), fraction);\n");
        pseudo.write("        if (mirror) *output = xor_float_sign_lanes_2_and_3(*output);\n");
        pseudo.write("        // PORTME at 0x8463A46C and 0x8463A684: bind lanes 2 and 3 to\n");
        pseudo.write("        // named skeleton axes only after the coordinate convention is proved.\n");
        pseudo.write("    }\n");
        pseudo.write("}\n\n");
    }

    private void writeRawRange(BufferedWriter output, long first, long afterLast)
            throws Exception {
        output.write("RAW_RANGE " + hex(first) + " " + hex(afterLast) + "\n");
        Memory memory = currentProgram.getMemory();
        for (long value = first; value < afterLast; value += 4) {
            Address cursor = address(value);
            long raw = Integer.toUnsignedLong(memory.getInt(cursor));
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            output.write("RAW32 " + hex(value) + " " + hex(raw) + "\n");
            output.write("GHIDRA " + hex(value) + " " +
                (instruction == null ? "<no instruction>" : instruction.toString()) + "\n");
        }
    }

    private String safeReason(DecompileResults result) {
        String reason = result.isTimedOut() ? "timed out after 90 seconds" : result.getErrorMessage();
        if (reason == null || reason.isEmpty()) reason = "no decompiler diagnostic";
        return reason.replace('\n', ' ').replace('\r', ' ');
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfPackedPoseDecoderTrace.java OUTPUT_DIRECTORY");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!"217eea6084c3d03f0f1143802b1f5636".equalsIgnoreCase(executableMd5) &&
            !"c6f5639ac4c428682db0362947a223d8".equalsIgnoreCase(executableMd5) &&
            !"5370d49a9542d60c0345391e4e4aa656".equalsIgnoreCase(executableMd5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + executableMd5);
        }
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }

        Set<Function> functions = new LinkedHashSet<>();
        for (long value : FOCUSED_FUNCTIONS) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
            if (function != null) functions.add(function);
        }
        long[][] transientBodies = {
            { 0x8463846CL, 0x846384CCL },
            { 0x846384D0L, 0x84638504L },
            { 0x84638508L, 0x8463853CL },
            { 0x84638540L, 0x84638574L },
            { 0x84638578L, 0x84638580L },
            { 0x84638588L, 0x846385A4L },
            { 0x846385A8L, 0x84638718L },
            { 0x8463A328L, 0x8463A9C7L },
        };
        String[] transientNames = {
            "PackedUnitDecoder_Continuation",
            "PackedVariant_0x846384D0",
            "PackedVariant_0x84638508",
            "PackedVariant_0x84638540",
            "PackedCopy8_0x84638578",
            "PackedLoad8_0x84638588",
            "QuaternionInterpolation_0x846385A8",
            "AggregatePoseSampler_Body",
        };
        for (int index = 0; index < transientBodies.length; index++) {
            Function function = createBody(
                transientBodies[index][0], transientBodies[index][1], transientNames[index]);
            if (function != null) functions.add(function);
        }

        File traceFile = new File(output, "packed_pose_decoder_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("APF 2K8 SingleMoCap packed-pose focused static trace\n");
            trace.write("Program MD5: " + executableMd5 + "\n");
            trace.write("Program name: " + currentProgram.getName() + "\n");
            trace.write("Program language: " + currentProgram.getLanguageID() + "\n");
            trace.write("Constraint: VMX128 raw words require the vendored XenonRecomp decoder.\n\n");

            trace.write("FOCUSED_FUNCTION_REFERENCES\n");
            for (long value : FOCUSED_FUNCTIONS) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
                trace.write(hex(value) + " " + functionName(function) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
            }
            trace.write("\nDEFAULT_CHANNEL_MAP\n");
            byte[] map = new byte[96];
            currentProgram.getMemory().getBytes(address(0x82000B30L), map);
            for (int index = 0; index < map.length; index += 3) {
                trace.write(String.format(
                    "MAP %d %d %d %d\n", index / 3, map[index] & 0xFF,
                    map[index + 1] & 0xFF, map[index + 2] & 0xFF));
            }
            trace.write("\nINTERPOLATION_CONSTANTS\n");
            String[] constantLabels = {
                "acos_x7", "acos_x6", "acos_x5", "acos_x4",
                "acos_x3", "acos_x2", "acos_x1", "acos_x0",
                "sin_x7", "sin_x5", "sin_x3", "half_pi",
                "cos_x6", "cos_x4", "cos_x2", "linear_threshold",
            };
            for (int index = 0; index < constantLabels.length; index++) {
                writeFloatConstant(trace, 0x82000BF0L + index * 4L, constantLabels[index]);
            }
            writeFloatConstant(trace, 0x820009A0L, "clamped_frame_fraction");
            trace.write("\nRAW_INSTRUCTIONS\n");
            for (long[] range : RAW_RANGES) writeRawRange(trace, range[0], range[1]);
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(output, "packed_pose_decoder_focused_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* APF packed-pose focused Ghidra pseudo-C. */\n");
            pseudo.write("/* VMX128 truncation is retained explicitly; see the raw-word TSV. */\n\n");
            writeInstructionProvedPseudoC(pseudo);
            for (Function function : sorted(functions)) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " references=" +
                    String.join(";", referencesTo(function.getEntryPoint())) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                String code = null;
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    code = result.getDecompiledFunction().getC();
                    pseudo.write(code);
                }
                else {
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; " + safeReason(result) + "\n");
                }
                if (code != null && (code.contains("halt_baddata") ||
                                     code.contains("bad instruction data"))) {
                    pseudo.write("// PORTME: Ghidra truncated VMX128 function at " + hex(value) +
                        "; recover semantics from the exact RAW32/VMX128 trace.\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("APF_PACKED_POSE_GHIDRA_TRACE_COMPLETE functions=" + functions.size());
    }
}

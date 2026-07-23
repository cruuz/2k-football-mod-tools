// Emit focused APF 2K8 pose-config construction/installation evidence.
// @category Xbox360.APF2K8

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfPoseConfigBuilderTrace extends GhidraScript {
    private static final String EXPECTED_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private String addr(Address value) {
        return value == null ? "" : hex(value.getUnsignedOffset());
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<String> referencesTo(long target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(
            address(target));
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            result.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        Collections.sort(result);
        return result;
    }

    private List<String> rawPointerHits(long target) throws Exception {
        byte[] needle = new byte[] {
            (byte)(target >>> 24), (byte)(target >>> 16),
            (byte)(target >>> 8), (byte)target
        };
        List<String> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(
                    cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                if ((hit.getUnsignedOffset() & 3L) == 0) {
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(hit);
                    result.add(addr(hit) + "(" + block.getName() + "," +
                        functionName(owner) + ")");
                }
                cursor = hit.add(1);
            }
        }
        Collections.sort(result);
        return result;
    }

    /*
     * Recover direct lis/addi or lis/ori construction of one 32-bit address.
     * The eight-instruction window is deliberately reported as raw evidence;
     * it is not a general PPC data-flow claim.
     */
    private List<String> materializations(long target) throws Exception {
        List<String> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        long wanted = target & 0xffffffffL;
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized() || !block.isExecute()) continue;
            long first = (block.getStart().getUnsignedOffset() + 3L) & ~3L;
            long last = block.getEnd().getUnsignedOffset();
            for (long value = first; value + 3 <= last; value += 4) {
                long raw = Integer.toUnsignedLong(memory.getInt(address(value)));
                int opcode = (int)(raw >>> 26);
                int ra = (int)((raw >>> 16) & 31);
                if (opcode != 15 || ra != 0) continue; // lis == addis rt,0,simm
                int baseRegister = (int)((raw >>> 21) & 31);
                long high = ((long)(short)(raw & 0xffffL) << 16) & 0xffffffffL;
                for (int distance = 1; distance <= 8; distance++) {
                    long site = value + distance * 4L;
                    if (site + 3 > last) break;
                    long next = Integer.toUnsignedLong(memory.getInt(address(site)));
                    int nextOpcode = (int)(next >>> 26);
                    long computed = -1;
                    String kind = "";
                    if (nextOpcode == 14 && ((next >>> 16) & 31) == baseRegister) {
                        computed = (high + (short)(next & 0xffffL)) & 0xffffffffL;
                        kind = "lis/addi";
                    }
                    else if (nextOpcode == 24 && ((next >>> 21) & 31) == baseRegister) {
                        computed = (high | (next & 0xffffL)) & 0xffffffffL;
                        kind = "lis/ori";
                    }
                    if (computed == wanted) {
                        result.add(hex(value) + "->" + hex(site) + "(" + kind + ")");
                    }
                }
            }
        }
        Collections.sort(result);
        return result;
    }

    private void writeRawSpan(
            BufferedWriter output, String name, long first, long afterLast) throws Exception {
        output.write("SPAN " + name + " " + hex(first) + " " + hex(afterLast) + "\n");
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
        output.write("END_SPAN " + name + "\n");
    }

    private void writeReferenceEvidence(BufferedWriter output, long target) throws Exception {
        List<String> references = referencesTo(target);
        List<String> pointers = rawPointerHits(target);
        List<String> constructions = materializations(target);
        output.write("TARGET " + hex(target) + " refs=" + references.size() +
            " raw_aligned_pointer_hits=" + pointers.size() +
            " materializations=" + constructions.size() + "\n");
        for (String value : references) output.write("TARGET_REF " + hex(target) + " " + value + "\n");
        for (String value : pointers) output.write("TARGET_POINTER " + hex(target) + " " + value + "\n");
        for (String value : constructions) {
            output.write("TARGET_MATERIALIZATION " + hex(target) + " " + value + "\n");
        }
    }

    private void decompileOne(
            BufferedWriter output, DecompInterface decompiler, long entry) throws Exception {
        Function function = currentProgram.getFunctionManager().getFunctionAt(address(entry));
        output.write("/* " + hex(entry) + ":" +
            (function == null ? "missing" : function.getName()) + " refs=" +
            String.join(";", referencesTo(entry)) + " */\n");
        if (function == null) {
            output.write("// PORTME at " + hex(entry) +
                ": no exact function exists in the canonical analysis.\n\n");
            return;
        }
        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
        if (result != null && result.decompileCompleted()) {
            output.write(result.getDecompiledFunction().getC());
        }
        else {
            output.write("// PORTME at " + hex(entry) +
                ": Ghidra decompilation failed; retain the RAW32 span.\n");
        }
        output.write("\n\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfPoseConfigBuilderTrace.java OUTPUT_DIRECTORY");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!EXPECTED_MD5.equalsIgnoreCase(executableMd5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + executableMd5);
        }
        File outputDirectory = new File(args[0]);
        if (!outputDirectory.isDirectory() && !outputDirectory.mkdirs()) {
            throw new IllegalStateException("cannot create " + outputDirectory);
        }

        Memory memory = currentProgram.getMemory();
        File traceFile = new File(outputDirectory, "pose_config_builder_trace.txt");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(traceFile))) {
            output.write("APF 2K8 runtime pose-config builder/installer trace\n");
            output.write("Program MD5: " + executableMd5 + "\n");
            output.write("Program name: " + currentProgram.getName() + "\n");
            output.write("Program language: " + currentProgram.getLanguageID() + "\n\n");

            output.write("MAIN_STATIC_TABLES\n");
            for (int index = 0; index < 25; index++) {
                long base = 0x820fc510L + index * 3L;
                output.write("MAIN_MAP3 " + index + " " + memory.getByte(address(base)) + " " +
                    memory.getByte(address(base + 1)) + " " +
                    memory.getByte(address(base + 2)) + "\n");
            }
            for (int index = 0; index < 22; index++) {
                long base = 0x820fc55cL + index * 2L;
                output.write("MAIN_MAP2 " + index + " " + memory.getByte(address(base)) + " " +
                    memory.getByte(address(base + 1)) + " " +
                    (index < 21 ? "semantic" : "record_or_alignment_unproved") + "\n");
            }
            output.write("MAIN_MAP2_EXTENT 0x820FC55C 0x820FC588 bytes=44\n");

            output.write("\nSECONDARY_DIRECT_TABLE\n");
            for (int index = 0; index < 24; index++) {
                long base = 0x821006f0L + index * 3L;
                output.write("SECONDARY_MAP3 " + index + " " +
                    memory.getByte(address(base)) + " " + memory.getByte(address(base + 1)) +
                    " " + memory.getByte(address(base + 2)) + "\n");
            }
            output.write("SECONDARY_MAP3_EXTENT 0x821006F0 0x82100738 bytes=72\n");

            output.write("\nSTATIC_ACCESSOR_RETURNS\n");
            output.write("ACCESSOR 0x84AA4190 return=0x820FC510 role=main_map3\n");
            output.write("ACCESSOR 0x84AA41A0 return=0x820FC55C role=main_map2\n");
            output.write("ACCESSOR 0x84AA41B0 return=0x820FC588 role=float_table\n");
            output.write("ACCESSOR 0x84AA41C0 return=0x01F9FF80 role=mask_value_a\n");
            output.write("ACCESSOR 0x84AA41D0 return=0x0006007F role=mask_value_b\n");
            output.write("ACCESSOR 0x84AA41E0 return=0x00000000 role=zero_value\n");
            output.write("ACCESSOR 0x84AA41E8 return=unchanged role=noop\n");
            output.write("ACCESSOR 0x84AA41F0 return=void role=scale_nine_pose_floats\n");

            output.write("\nDIRECT_INSTALLER_SEARCH\n");
            long[] targets = {
                0x820fc510L, 0x820fc55cL, 0x820fc588L,
                0x84aa4190L, 0x84aa41a0L, 0x84aa41b0L,
                0x84aa41c0L, 0x84aa41d0L, 0x84aa41e0L,
                0x84aa41e8L, 0x84aa41f0L
            };
            for (long target : targets) writeReferenceEvidence(output, target);
            output.write("DIRECT_MAIN_MAP3_INSTALLER_COUNT 0\n");
            output.write("DIRECT_MAIN_MAP3_INSTALLER_LIMIT " +
                "indirect_runtime_dispatch_or_external_installation_not_excluded\n");

            output.write("\nRAW_EVIDENCE\n");
            writeRawSpan(output, "consumer_config_a", 0x847c1438L, 0x847c14e0L);
            writeRawSpan(output, "consumer_config_b", 0x847c9428L, 0x847c94bcL);
            writeRawSpan(output, "pose_storage_pointer", 0x847c0c20L, 0x847c0c54L);
            writeRawSpan(output, "static_map2_index_lookup", 0x84877698L, 0x84877758L);
            writeRawSpan(output, "static_map2_pair9_lookup", 0x84925bdcL, 0x84925d04L);
            writeRawSpan(output, "config_matrix_call", 0x84926064L, 0x84926078L);
            writeRawSpan(output, "dynamic_record_sample", 0x8497b88cL, 0x8497b944L);
            writeRawSpan(output, "dynamic_record_stride", 0x8497ba60L, 0x8497ba74L);
            writeRawSpan(output, "dynamic_record_destroy", 0x8497d590L, 0x8497d604L);
            writeRawSpan(output, "matrix_pool_allocator", 0x84aa4070L, 0x84aa4124L);
            writeRawSpan(output, "static_accessor_family", 0x84aa4190L, 0x84aa4288L);
            writeRawSpan(output, "secondary_hardcoded_config", 0x84ac1668L, 0x84ac1760L);
        }

        File pseudoFile = new File(outputDirectory,
            "pose_config_builder_focused_pseudo_c.c");
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (BufferedWriter output = new BufferedWriter(new FileWriter(pseudoFile))) {
            output.write("/* APF 2K8 pose-config builder/installer focused pseudo-C. */\n\n");
            decompileOne(output, decompiler, 0x847c1438L);
            decompileOne(output, decompiler, 0x847c9428L);
            decompileOne(output, decompiler, 0x84aa4070L);
            decompileOne(output, decompiler, 0x8472af58L);
            output.write("/* Exact leaf accessors, reconstructed from RAW32. */\n");
            output.write("const unsigned char *apf_player_map3(void) { return (const unsigned char *)0x820FC510; }\n");
            output.write("const signed char *apf_player_map2(void) { return (const signed char *)0x820FC55C; }\n");
            output.write("const float *apf_player_pose_scales(void) { return (const float *)0x820FC588; }\n");
            output.write("unsigned apf_player_mask_a(void) { return 0x01F9FF80u; }\n");
            output.write("unsigned apf_player_mask_b(void) { return 0x0006007Fu; }\n");
            output.write("unsigned apf_player_zero(void) { return 0; }\n\n");
            output.write("// PORTME at 0x8497B7B0: shared-save recovery is still required for compilable pseudo-C; RAW32 proves the 0x40-byte dynamic record contract.\n");
            output.write("// PORTME at 0x84AC1668: shared-save/VMX recovery is still required; RAW32 proves direct maps 0x821006F0 and 0x82100738.\n");
            output.write("// PORTME at 0x847C1470/0x847C14A4: no direct retail-XEX installer for main map3/map2 was recovered.\n");
            output.write("// PORTME at 0x820FC55C: bind matrix rows to named SCNE bones only after an installer or runtime capture proves ownership.\n");
        }
        decompiler.dispose();
    }
}

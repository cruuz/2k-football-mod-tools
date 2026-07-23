// Emit focused ownership evidence for APF 2K8's 0x2c-byte animation registry.
// @category VisualConcepts.Animation

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class Apf2k6AnimationRuntimeTrace extends GhidraScript {
    private static final String EXPECTED_MD5 = "217eea6084c3d03f0f1143802b1f5636";
    private static final long TABLE_FIRST = 0x84D75500L;
    private static final long TABLE_AFTER_LAST = 0x84DB4850L;
    private static final int RECORD_SIZE = 0x2c;
    private static final int RECORD_COUNT = 5884;

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

    private String blockName(Address target) {
        MemoryBlock block = currentProgram.getMemory().getBlock(target);
        if (block == null) return "UNMAPPED";
        return block.getName() + "(execute=" + block.isExecute() + ")";
    }

    private List<String> referencesTo(long target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(address(target));
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

    private List<String> rawAlignedPointerHits(long target) throws Exception {
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
                Address hit = memory.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
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

    private String utf16be(long first, int maximumUnits) throws Exception {
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < maximumUnits; index++) {
            int code = Short.toUnsignedInt(currentProgram.getMemory().getShort(
                address(first + index * 2L)));
            if (code == 0) return result.toString();
            if (code < 0x20 || code > 0x7e) {
                return "<non-ascii-utf16>";
            }
            result.append((char)code);
        }
        return "<unterminated>";
    }

    private void writeTarget(BufferedWriter output, long target) throws Exception {
        List<String> references = referencesTo(target);
        List<String> pointers = rawAlignedPointerHits(target);
        output.write("TARGET " + hex(target) + " block=" + blockName(address(target)) +
            " refs=" + references.size() + " raw_aligned_pointer_hits=" + pointers.size() + "\n");
        for (String value : references) output.write("TARGET_REF " + hex(target) + " " + value + "\n");
        for (String value : pointers) output.write("TARGET_POINTER " + hex(target) + " " + value + "\n");
    }

    private void writeRecord(BufferedWriter output, long record) throws Exception {
        Memory memory = currentProgram.getMemory();
        output.write("RECORD " + hex(record) + " index=" + ((record - TABLE_FIRST) / RECORD_SIZE) + "\n");
        for (int offset = 0; offset < RECORD_SIZE; offset += 4) {
            long value = Integer.toUnsignedLong(memory.getInt(address(record + offset)));
            output.write("FIELD +" + String.format("0x%02X", offset) + "=" + hex(value));
            if (offset <= 8 && value != 0) output.write(" text=" + utf16be(value, 128));
            output.write("\n");
        }
    }

    private List<String> instructionReferencesInto(long first, long afterLast) {
        List<String> result = new ArrayList<>();
        InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            Reference[] references = currentProgram.getReferenceManager().getReferencesFrom(
                instruction.getAddress());
            for (Reference reference : references) {
                long target = reference.getToAddress().getUnsignedOffset();
                if (target < first || target >= afterLast) continue;
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                    instruction.getAddress());
                result.add(addr(instruction.getAddress()) + "->" + hex(target) + "(" +
                    reference.getReferenceType() + "," + functionName(owner) + "," +
                    instruction.toString() + ")");
            }
        }
        Collections.sort(result);
        return result;
    }

    /*
     * Follow one constant GPR from lis through addi/ori operations until the
     * listing says that GPR is overwritten or control flow stops falling
     * through. This is deliberately not a general PPC data-flow proof.
     */
    private List<String> classicMaterializationsInto(long first, long afterLast)
            throws Exception {
        List<String> result = new ArrayList<>();
        Set<String> unique = new HashSet<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized() || !block.isExecute()) continue;
            long start = (block.getStart().getUnsignedOffset() + 3L) & ~3L;
            long end = block.getEnd().getUnsignedOffset();
            for (long site = start; site + 3 <= end; site += 4) {
                long raw = Integer.toUnsignedLong(memory.getInt(address(site)));
                if ((raw >>> 26) != 15 || ((raw >>> 16) & 31) != 0) continue;
                int register = (int)((raw >>> 21) & 31);
                Register tracked = currentProgram.getRegister("r" + register);
                if (tracked == null) continue;
                long constant = ((long)(short)(raw & 0xffffL) << 16) & 0xffffffffL;
                for (int distance = 1; distance <= 12; distance++) {
                    long lowSite = site + distance * 4L;
                    if (lowSite + 3 > end) break;
                    Address lowAddress = address(lowSite);
                    Instruction instruction = currentProgram.getListing().getInstructionAt(lowAddress);
                    if (instruction == null) {
                        disassemble(lowAddress);
                        instruction = currentProgram.getListing().getInstructionAt(lowAddress);
                    }
                    if (instruction == null) break;
                    long lowRaw = Integer.toUnsignedLong(memory.getInt(address(lowSite)));
                    int opcode = (int)(lowRaw >>> 26);
                    long computed = -1;
                    String kind = "";
                    boolean trackedWriteHandled = false;
                    if (opcode == 14 && ((lowRaw >>> 16) & 31) == register) {
                        computed = (constant + (short)(lowRaw & 0xffffL)) & 0xffffffffL;
                        kind = "lis/addi";
                        if (((lowRaw >>> 21) & 31) == register) {
                            constant = computed;
                            trackedWriteHandled = true;
                        }
                    }
                    else if (opcode == 24 && ((lowRaw >>> 21) & 31) == register) {
                        computed = (constant | (lowRaw & 0xffffL)) & 0xffffffffL;
                        kind = "lis/ori";
                        if (((lowRaw >>> 16) & 31) == register) {
                            constant = computed;
                            trackedWriteHandled = true;
                        }
                    }
                    if (computed >= first && computed < afterLast) {
                        Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                            address(site));
                        String value = hex(site) + "->" + hex(lowSite) + "=" + hex(computed) +
                            "(" + kind + "," + functionName(owner) + ")";
                        if (unique.add(value)) result.add(value);
                    }
                    boolean overwrote = false;
                    for (Object object : instruction.getResultObjects()) {
                        if (object instanceof Register && ((Register)object).getName().equals(
                                tracked.getName())) {
                            overwrote = true;
                        }
                    }
                    if (overwrote && !trackedWriteHandled) break;
                    if (!instruction.getFlowType().isFallthrough()) break;
                }
            }
        }
        Collections.sort(result);
        return result;
    }

    private void writePseudo(
            BufferedWriter output, DecompInterface decompiler, long entry) throws Exception {
        Function function = currentProgram.getFunctionManager().getFunctionAt(address(entry));
        output.write("/* " + hex(entry) + ":" +
            (function == null ? "missing" : function.getName()) + " refs=" +
            String.join(";", referencesTo(entry)) + " */\n");
        if (function == null) {
            output.write("// PORTME: no saved Ghidra function boundary at " + hex(entry) + ".\n\n");
            return;
        }
        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
        if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
            output.write(result.getDecompiledFunction().getC());
        }
        else {
            output.write("// PORTME: could not decompile function at " + hex(entry) + "; " +
                result.getErrorMessage() + "\n");
        }
        output.write("\n");
    }

    private Function rebuildSelectorArrayBody() throws Exception {
        Address first = address(0x848AEB80L);
        Address last = address(0x848AEC0FL);
        Function existing = currentProgram.getFunctionManager().getFunctionContaining(first);
        if (existing != null) return existing;
        for (Address cursor = first; cursor.compareTo(last) <= 0; cursor = cursor.add(4)) {
            if (currentProgram.getListing().getInstructionAt(cursor) == null) disassemble(cursor);
        }
        return currentProgram.getListing().createFunction(
            "APF_AnimationSelectorArrayInit_Body", first,
            new AddressSet(first, last), SourceType.ANALYSIS);
    }

    private void writeRawSpan(
            BufferedWriter output, long first, long afterLast) throws Exception {
        output.write("RAW_SPAN " + hex(first) + ".." + hex(afterLast) + "\n");
        for (long value = first; value < afterLast; value += 4) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            output.write(hex(value) + " raw=" + hex(Integer.toUnsignedLong(
                currentProgram.getMemory().getInt(cursor))) + " instruction=" +
                (instruction == null ? "<none>" : instruction.toString()) + "\n");
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: Apf2k6AnimationRuntimeTrace.java OUTPUT_DIRECTORY");
        }
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!EXPECTED_MD5.equals(md5)) throw new IllegalStateException("unexpected APF MD5 " + md5);
        if (TABLE_FIRST + (long)RECORD_COUNT * RECORD_SIZE != TABLE_AFTER_LAST) {
            throw new IllegalStateException("animation table constants disagree");
        }

        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }
        File traceFile = new File(directory, "apf_2k6_animation_runtime_ghidra_trace.txt");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(traceFile))) {
            output.write("APF 2K8 2K6-tagged animation registry read-only trace\n");
            output.write("Program MD5: " + md5 + "\n");
            output.write("Program name: " + currentProgram.getName() + "\n");
            output.write("Program language: " + currentProgram.getLanguageID() + "\n");
            output.write("Table: " + hex(TABLE_FIRST) + ".." + hex(TABLE_AFTER_LAST) +
                " record_size=0x2C record_count=5884\n\n");

            output.write("FOCUSED_RECORDS\n");
            writeRecord(output, TABLE_FIRST);
            writeRecord(output, 0x84D7E6C0L);
            writeRecord(output, 0x84D7E6ECL);
            writeRecord(output, 0x84DB4824L);
            output.write("TRAILER " + hex(TABLE_AFTER_LAST) + "=" +
                hex(Integer.toUnsignedLong(currentProgram.getMemory().getInt(
                    address(TABLE_AFTER_LAST)))) + "\n");
            output.write("TRAILER " + hex(TABLE_AFTER_LAST + 4) + "=" +
                hex(Integer.toUnsignedLong(currentProgram.getMemory().getInt(
                    address(TABLE_AFTER_LAST + 4)))) + "\n\n");

            output.write("FOCUSED_TARGETS\n");
            for (long target : new long[] {
                    TABLE_FIRST, 0x84D7E6C0L, 0x84D7E6C4L, TABLE_AFTER_LAST,
                    TABLE_AFTER_LAST + 4, 0x84548A9CL, 0x8409BB00L, 0x8409C820L,
                    0x84DBC89CL, 0x84DBC8ACL, 0x84DBC768L, 0x84DBC5DCL,
                    0x820BE2FCL, 0x820BE30CL, 0x84DEB6A0L, 0x848AF560L}) {
                writeTarget(output, target);
            }

            output.write("\nCODE_REFERENCES_INTO_TABLE\n");
            List<String> references = instructionReferencesInto(TABLE_FIRST, TABLE_AFTER_LAST);
            output.write("CODE_REFERENCE_COUNT " + references.size() + "\n");
            for (String value : references) output.write("CODE_REFERENCE " + value + "\n");

            output.write("\nCLASSIC_MATERIALIZATIONS_INTO_TABLE_OR_TRAILER\n");
            List<String> materializations = classicMaterializationsInto(
                TABLE_FIRST, TABLE_AFTER_LAST + 8);
            output.write("CLASSIC_MATERIALIZATION_COUNT " + materializations.size() + "\n");
            for (String value : materializations) {
                output.write("CLASSIC_MATERIALIZATION " + value + "\n");
            }

            long[][] linkedRanges = {
                {0x84DBC5CCL, 0x84DBCA00L},
                {0x84DEB650L, 0x84DEB750L}
            };
            output.write("\nLINKED_PAYLOAD_CONFIG_CODE_OWNERSHIP\n");
            for (long[] range : linkedRanges) {
                List<String> linkedReferences = instructionReferencesInto(range[0], range[1]);
                List<String> linkedMaterializations = classicMaterializationsInto(range[0], range[1]);
                output.write("LINKED_RANGE " + hex(range[0]) + ".." + hex(range[1]) +
                    " code_refs=" + linkedReferences.size() + " materializations=" +
                    linkedMaterializations.size() + "\n");
                for (String value : linkedReferences) output.write("LINKED_CODE_REF " + value + "\n");
                for (String value : linkedMaterializations) {
                    output.write("LINKED_MATERIALIZATION " + value + "\n");
                }
            }
            output.write("\nSELECTOR_ARRAY_HELPER_RAW\n");
            writeRawSpan(output, 0x848AEB78L, 0x848AEC10L);
            output.write("\nMASTER_LOOKUP_CALLS_RAW\n");
            writeRawSpan(output, 0x848FD440L, 0x848FD478L);
            writeRawSpan(output, 0x848FDBE8L, 0x848FDC20L);
            writeRawSpan(output, 0x848FDF58L, 0x848FDFA0L);
        }

        rebuildSelectorArrayBody();
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler open failed");
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(
                directory, "apf_2k6_animation_runtime_ghidra_pseudo_c.c")))) {
            output.write("/* APF 2K8 2K6 animation payload/config focused pseudo-C. */\n\n");
            output.write("/* The saved 0x848AEB78 function stops at the shared-save branch; " +
                "the transient read-only body begins at +8. */\n");
            writePseudo(output, decompiler, 0x848AEB80L);
            writePseudo(output, decompiler, 0x848AF560L);
            writePseudo(output, decompiler, 0x848EA3B0L);
            writePseudo(output, decompiler, 0x848FD398L);
            output.write("// PORTME(0x848AEB78): recover the shared-save wrapper and the " +
                "0x848AEB80 inner loop that Ghidra truncates at 0x84B0C970; the RAW32 " +
                "span is authoritative.\n");
            output.write("// PORTME(0x848FDC0C/0x848FDF80): create exact caller " +
                "boundaries and exclude indirect callers before making a complete selector-" +
                "reachability claim.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("APF_2K6_ANIMATION_RUNTIME_TRACE_COMPLETE table_records=5884");
    }
}

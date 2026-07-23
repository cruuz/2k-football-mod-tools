// Read-only focused trace for the NFL 2K5 celebration live-record owner/type.
// @category VisualConcepts.NFL

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class NflCelebrationLiveRecordOwnershipTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x000A05F0L,
        0x000A1A60L,
        0x000B8330L,
        0x000B8390L,
        0x000B83C0L,
        0x000B8400L,
        0x000B8420L,
        0x000B8480L,
        0x000B84F0L,
        0x000B85C0L,
        0x00142390L,
        0x0017C0E0L,
        0x0017C3C0L,
        0x0018D6D0L,
        0x0018EC40L,
        0x001ABF30L,
        0x001CF250L,
        0x0020F0D0L,
        0x0020F220L,
        0x0020F230L,
        0x0022DFB0L,
        0x0022DFD0L,
        0x0022DFF0L,
        0x0022E010L,
        0x0022E030L,
        0x0022E050L,
        0x0022E2D0L,
        0x002DDD90L,
        0x002DDB10L,
        0x002DDDB0L,
        0x002DE170L,
        0x002DE300L,
        0x002DE620L,
        0x002DE7A0L,
        0x002DE800L,
        0x002DE9C0L,
        0x00369650L,
        0x00369690L,
        0x00369AC0L,
        0x00530170L,
        0x00AABEF8L
    };

    private static final long[] RAW_FUNCTIONS_WITHOUT_SAVED_BOUNDARIES = {
        0x0018D6D0L,
        0x001ABF30L,
        0x002DDB10L,
        0x002DE170L,
        0x002DE7A0L,
        0x002DE800L,
        0x002DE9C0L,
        0x00369AC0L
    };

    private static final long[][] WINDOWS = {
        { 0x000A05F0L, 0x000A0620L },
        { 0x000A1A50L, 0x000A1A90L },
        { 0x000B8330L, 0x000B8620L },
        { 0x00142370L, 0x001423A5L },
        { 0x0017C0E0L, 0x0017C186L },
        { 0x0017C3C0L, 0x0017C3F1L },
        { 0x0018D6D0L, 0x0018D830L },
        { 0x0018EC40L, 0x0018EC9EL },
        { 0x00185EDBL, 0x00185FB1L },
        { 0x0019E87BL, 0x0019E8ADL },
        { 0x001A01BAL, 0x001A01DDL },
        { 0x001A5EB0L, 0x001A5F19L },
        { 0x001ABF30L, 0x001AC00FL },
        { 0x001CF250L, 0x001CF2D2L },
        { 0x001D009BL, 0x001D00BBL },
        { 0x0020F0D0L, 0x0020F29FL },
        { 0x0022DFA0L, 0x0022E060L },
        { 0x0022E2D0L, 0x0022E397L },
        { 0x002DDB10L, 0x002DDCB8L },
        { 0x002DDD30L, 0x002DDDBCL },
        { 0x002DE170L, 0x002DE2F5L },
        { 0x002DE300L, 0x002DE42AL },
        { 0x002DE620L, 0x002DE75DL },
        { 0x002DE7A0L, 0x002DE921L },
        { 0x002DE9C0L, 0x002DE9FDL },
        { 0x00369620L, 0x0036969AL },
        { 0x00369AC0L, 0x00369B1EL }
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace()
            .getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" +
            function.getName();
    }

    private List<String> referencesTo(Address target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager()
            .getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager()
                .getFunctionContaining(reference.getFromAddress());
            result.add(hex(reference.getFromAddress().getUnsignedOffset()) +
                "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private void ensureDisassembled(long first, long last) throws Exception {
        Address cursor = address(first);
        Address limit = address(last);
        while (cursor.compareTo(limit) <= 0) {
            Instruction instruction = currentProgram.getListing()
                .getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            cursor = instruction == null ? cursor.add(1) :
                instruction.getMaxAddress().add(1);
        }
    }

    private void writeInstructionRange(BufferedWriter output, long first,
            long last) throws Exception {
        ensureDisassembled(first, last);
        output.write("RANGE " + hex(first) + ".." + hex(last) + "\n");
        InstructionIterator iterator = currentProgram.getListing()
            .getInstructions(address(first), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            long value = instruction.getAddress().getUnsignedOffset();
            if (Long.compareUnsigned(value, last) > 0) break;
            Function owner = currentProgram.getFunctionManager()
                .getFunctionContaining(instruction.getAddress());
            output.write(hex(value) + " " + instruction + " owner=" +
                functionName(owner) + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) +
                "\n");
        }
        output.write("\n");
    }

    private void writeBytes(BufferedWriter output, long first, int length)
            throws Exception {
        Memory memory = currentProgram.getMemory();
        byte[] bytes = new byte[length];
        int read = memory.getBytes(address(first), bytes);
        if (read != length) {
            throw new IllegalStateException("short read at " + hex(first));
        }
        StringBuilder builder = new StringBuilder();
        for (byte value : bytes) {
            builder.append(String.format("%02x", value & 0xff));
        }
        output.write(hex(first) + " length=" + length + " bytes=" +
            builder + "\n");
    }

    private void addFocusedFunction(Set<Function> functions, long value) {
        Address target = address(value);
        Function direct = currentProgram.getFunctionManager()
            .getFunctionAt(target);
        if (direct != null) functions.add(direct);
    }

    private void writeStateWord34DirectWriteScan(BufferedWriter output)
            throws Exception {
        output.write("STATE_WORD_0X34_DIRECT_WRITE_SCAN\n");
        int matches = 0;
        InstructionIterator iterator = currentProgram.getListing()
            .getInstructions(true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            String text = instruction.toString().toLowerCase();
            int comma = text.indexOf(',');
            String destination = comma < 0 ? text : text.substring(0, comma);
            if (!text.startsWith("mov ") ||
                    !destination.contains(" + 0x1c]") ||
                    !text.substring(comma + 1).trim().equals("0x34")) continue;
            Function owner = currentProgram.getFunctionManager()
                .getFunctionContaining(instruction.getAddress());
            output.write(hex(instruction.getAddress().getUnsignedOffset()) +
                " " + instruction + " owner=" + functionName(owner) +
                "\n");
            matches++;
        }
        output.write("matches=" + matches + "\n");
        output.write("\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflCelebrationLiveRecordOwnershipTrace.java OUTPUT_DIRECTORY");
        }
        if (!"444064a9ec984dd29d2c05a43f5c96e8".equalsIgnoreCase(
                currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected NFL 2K5 executable");
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        for (long[] window : WINDOWS) ensureDisassembled(window[0], window[1]);

        Set<Function> functions = new LinkedHashSet<>();
        for (long value : FOCUSED) addFocusedFunction(functions, value);

        File traceFile = new File(directory,
            "nfl_celebration_live_record_ownership_trace.txt");
        try (BufferedWriter output = new BufferedWriter(
                new FileWriter(traceFile))) {
            output.write("NFL 2K5 celebration live-record ownership trace\n");
            output.write("Program MD5: " +
                currentProgram.getExecutableMD5() + "\n\n");
            output.write("FOCUSED_REFERENCES\n");
            for (long value : FOCUSED) {
                Function direct = currentProgram.getFunctionManager()
                    .getFunctionAt(address(value));
                Function containing = currentProgram.getFunctionManager()
                    .getFunctionContaining(address(value));
                output.write(hex(value) + " direct=" + functionName(direct) +
                    " containing=" + functionName(containing) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
            }
            output.write("\nPINNED_BYTES\n");
            writeBytes(output, 0x00AABEF8L, 0x274);
            writeBytes(output, 0x002DE7E4L, 0x14);
            writeBytes(output, 0x00530170L, 0x14);
            writeBytes(output, 0x0022E388L, 0x14);
            writeBytes(output, 0x0050CFE0L, 0x0c);
            writeBytes(output, 0x005858D0L, 37 * 8);
            writeBytes(output, 0x00708188L, 0x34);
            writeBytes(output, 0x00706B38L, 0x04);
            output.write("\n");
            writeStateWord34DirectWriteScan(output);
            output.write("\nINSTRUCTION_WINDOWS\n");
            for (long[] window : WINDOWS) {
                writeInstructionRange(output, window[0], window[1]);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory,
            "nfl_celebration_live_record_ownership_pseudo_c.c");
        try (BufferedWriter output = new BufferedWriter(
                new FileWriter(pseudoFile))) {
            output.write("/* NFL 2K5 celebration live-record ownership pseudo-C */\n\n");
            for (long value : RAW_FUNCTIONS_WITHOUT_SAVED_BOUNDARIES) {
                if (currentProgram.getFunctionManager().getFunctionAt(address(value)) == null) {
                    output.write("// PORTME: no saved Ghidra function boundary at " +
                        hex(value) + "; exact instructions are preserved in the focused trace.\n");
                }
            }
            output.write("\n");
            for (Function function : functions) {
                output.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(
                    function, 90, monitor);
                if (result.decompileCompleted() &&
                        result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                }
                else {
                    output.write("// PORTME: could not decompile function at " +
                        hex(function.getEntryPoint().getUnsignedOffset()) +
                        "\n");
                }
                output.write("\n\n");
            }
        }
        decompiler.dispose();
        println("NFL_CELEBRATION_LIVE_RECORD_OWNERSHIP_TRACE_COMPLETE functions=" +
            functions.size());
    }
}

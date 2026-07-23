// Emit focused static evidence for NFL 2K5 quaternion interpolation.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.security.MessageDigest;
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

public class NflQuaternionInterpolationTrace extends GhidraScript {
    private static final long TARGET = 0x003CA270L;
    private static final long[] FOCUSED = {
        0x00020B20L, 0x00020BC0L, 0x00020C00L, 0x00021390L,
        0x003C9D10L, 0x003C9D80L, TARGET,
        0x0005CC20L, 0x000DF450L, 0x000DF6A0L, 0x000DF700L,
        0x001C71D0L, 0x001CCFA0L, 0x001DF430L
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" + function.getName();
    }

    private List<Reference> referencesTo(long target) {
        List<Reference> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(
            address(target));
        while (iterator.hasNext()) result.add(iterator.next());
        result.sort(Comparator.comparing(Reference::getFromAddress));
        return result;
    }

    private String referenceList(long target) {
        List<String> result = new ArrayList<>();
        for (Reference reference : referencesTo(target)) {
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            result.add(hex(reference.getFromAddress().getUnsignedOffset()) + "(" +
                functionName(owner) + "," + reference.getReferenceType() + ")");
        }
        return String.join(";", result);
    }

    private void writeInstructions(BufferedWriter output, long first, long afterLast)
            throws Exception {
        Address cursor = address(first);
        Address limit = address(afterLast);
        while (cursor.compareTo(limit) < 0) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                output.write(hex(cursor.getUnsignedOffset()) + " <no instruction>\n");
                cursor = cursor.add(1);
            }
            else {
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(cursor);
                output.write(hex(cursor.getUnsignedOffset()) + " " + instruction +
                    " owner=" + functionName(owner) + " refs=" +
                    referenceList(cursor.getUnsignedOffset()) + "\n");
                cursor = instruction.getMaxAddress().add(1);
            }
        }
    }

    private void writeCallerSites(BufferedWriter output) throws Exception {
        for (Reference reference : referencesTo(TARGET)) {
            Address call = reference.getFromAddress();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(call);
            output.write("CALL_SITE " + hex(call.getUnsignedOffset()) + " owner=" +
                functionName(owner) + " type=" + reference.getReferenceType() + "\n");
            Instruction cursor = currentProgram.getListing().getInstructionAt(call);
            for (int i = 0; i < 6 && cursor != null; i++) {
                Instruction prior = currentProgram.getListing().getInstructionBefore(
                    cursor.getAddress());
                if (prior == null) break;
                cursor = prior;
            }
            for (int i = 0; i < 11 && cursor != null; i++) {
                output.write("  " + hex(cursor.getAddress().getUnsignedOffset()) + " " +
                    cursor + "\n");
                cursor = currentProgram.getListing().getInstructionAfter(cursor.getAddress());
            }
        }
    }

    private byte[] bytes(long first, int length) throws Exception {
        byte[] result = new byte[length];
        int read = currentProgram.getMemory().getBytes(address(first), result);
        if (read != length) throw new IllegalStateException("short read at " + hex(first));
        return result;
    }

    private String byteHex(byte[] values) {
        StringBuilder builder = new StringBuilder();
        for (byte value : values) builder.append(String.format("%02x", value & 0xff));
        return builder.toString();
    }

    private String sha256(byte[] values) throws Exception {
        return byteHex(MessageDigest.getInstance("SHA-256").digest(values));
    }

    private void writeBytes(BufferedWriter output, long first, int length) throws Exception {
        byte[] values = bytes(first, length);
        output.write(hex(first) + " length=" + length + " bytes=" + byteHex(values) + "\n");
    }

    private void writeTableSummary(BufferedWriter output) throws Exception {
        byte[] table = bytes(0x004E53E8L, 0x800);
        output.write("0x004E53E8 length=2048 entries=256 sha256=" + sha256(table) + "\n");
        int[] selected = {0, 1, 63, 64, 65, 127, 128, 191, 192, 193, 254, 255};
        Memory memory = currentProgram.getMemory();
        for (int index : selected) {
            long item = 0x004E53E8L + index * 8L;
            int base = memory.getInt(address(item));
            int slope = memory.getInt(address(item + 4));
            output.write(String.format(
                "table[%03d] va=%s base_raw=0x%08X slope_raw=0x%08X%n",
                index, hex(item), base, slope));
        }
    }

    private Function createFocusedBody(long firstValue, long lastValue, String name)
            throws Exception {
        Address first = address(firstValue);
        Address last = address(lastValue);
        Function function = currentProgram.getFunctionManager().getFunctionAt(first);
        if (function != null) return function;
        for (Address cursor = first; cursor.compareTo(last) <= 0;) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            cursor = instruction == null ? cursor.add(1) :
                instruction.getMaxAddress().add(1);
        }
        return currentProgram.getListing().createFunction(
            name, first, new AddressSet(first, last), SourceType.ANALYSIS);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflQuaternionInterpolationTrace.java OUTPUT_DIRECTORY");
        }
        if (!"444064a9ec984dd29d2c05a43f5c96e8".equalsIgnoreCase(
                currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected NFL 2K5 executable MD5 " +
                currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        // The table evaluator is an unreferenced leaf in the saved project. Create an exact
        // transient boundary so the read-only run can retain pseudo-C as well as instructions.
        createFocusedBody(0x003C9D80L, 0x003C9DA3L, "nfl_fixed_sine_table_eval");

        Set<Function> functions = new LinkedHashSet<>();
        List<Long> missingFunctions = new ArrayList<>();
        File traceFile = new File(directory, "nfl_quaternion_interpolation_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("NFL 2K5 quaternion interpolation focused static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n\n");

            trace.write("ANGLE_APPROXIMATION_AND_CONVERSION\n");
            writeInstructions(trace, 0x00020B20L, 0x00020B29L);
            writeInstructions(trace, 0x00020BC0L, 0x00020BD9L);
            writeInstructions(trace, 0x00020C00L, 0x00020C9BL);
            writeInstructions(trace, 0x00021390L, 0x00021407L);

            trace.write("\nFIXED_CONVERSION_AND_TABLE_EVALUATOR\n");
            writeInstructions(trace, 0x003C9D10L, 0x003C9D19L);
            writeInstructions(trace, 0x003C9D80L, 0x003C9DA4L);

            trace.write("\nQUATERNION_INTERPOLATION\n");
            writeInstructions(trace, TARGET, 0x003CA3CFL);

            trace.write("\nCALLER_SITES\n");
            writeCallerSites(trace);

            trace.write("\nCONSTANT_BYTES\n");
            writeBytes(trace, 0x004E4180L, 0x20);
            writeBytes(trace, 0x004F24E8L, 4);
            writeBytes(trace, 0x004E5BE8L, 0x9C);

            trace.write("\nSINE_TABLE\n");
            writeTableSummary(trace);

            trace.write("\nKEY_REFERENCES\n");
            long[] targets = {
                0x00020B20L, 0x00020C00L, 0x00021390L, 0x003C9D10L,
                0x003C9D80L, TARGET, 0x004F24E8L
            };
            for (long target : targets) {
                trace.write(hex(target) + " refs=" + referenceList(target) + "\n");
            }

            trace.write("\nFOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(
                    address(value));
                trace.write(hex(value) + " " + functionName(function) + " refs=" +
                    referenceList(value) + "\n");
                if (function != null) functions.add(function);
                else missingFunctions.add(value);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory,
            "nfl_quaternion_interpolation_focused_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* NFL 2K5 quaternion interpolation focused pseudo-C. */\n\n");
            for (long value : missingFunctions) {
                pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                    "; Ghidra has no saved function boundary; exact instructions are " +
                    "retained in nfl_quaternion_interpolation_trace.txt.\n");
            }
            if (!missingFunctions.isEmpty()) pseudo.write("\n");
            for (Function function : functions) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 60 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_QUATERNION_INTERPOLATION_TRACE_COMPLETE functions=" +
            functions.size() + " missing=" + missingFunctions.size());
    }
}

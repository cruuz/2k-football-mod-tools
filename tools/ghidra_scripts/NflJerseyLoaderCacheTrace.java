// Focused, read-only trace of NFL 2K5's TSET registration and load callback.
// @category Xbox.NFL2K5

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
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class NflJerseyLoaderCacheTrace extends GhidraScript {
    private static final String EXPECTED_MD5 = "444064a9ec984dd29d2c05a43f5c96e8";
    private static final long CALLBACK = 0x00045280L;
    private static final long[] FOCUSED = {
        0x000436A0L, 0x00043F50L, 0x000449E0L,
        0x00045100L, 0x000451D0L, CALLBACK, 0x00045300L,
        0x00048700L, 0x00048FF0L, 0x000615A0L, 0x00062BE0L
    };
    private static final long[] GLOBALS = {
        0x00B0957CL,
        0x00B120F4L, 0x00B12108L,
        0x00B1211CL, 0x00B12120L, 0x00B12128L, 0x00B1212CL,
        0x00B12130L, 0x00B12134L, 0x00B12138L,
        0x00B30710L, 0x00B30730L, 0x00B65428L
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private String hex(Address value) {
        return value == null ? "" : hex(value.getUnsignedOffset());
    }

    private String functionName(Function function) {
        return function == null ? "none" : hex(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<String> referencesTo(Address target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            result.add(hex(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private List<String> referencesFrom(Function function) {
        Set<String> result = new LinkedHashSet<>();
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            for (Reference reference : instruction.getReferencesFrom()) {
                Address target = reference.getToAddress();
                if (target == null) continue;
                Function callee = currentProgram.getFunctionManager().getFunctionAt(target);
                if (callee != null) {
                    result.add(hex(instruction.getAddress()) + "->" + functionName(callee) +
                        "(" + reference.getReferenceType() + ")");
                }
            }
        }
        return new ArrayList<>(result);
    }

    private String bytes(long value, int count) throws Exception {
        byte[] data = new byte[count];
        int read = currentProgram.getMemory().getBytes(address(value), data);
        if (read != count) throw new IllegalStateException("short read at " + hex(value));
        StringBuilder output = new StringBuilder();
        for (byte item : data) output.append(String.format("%02x", item & 0xff));
        return output.toString();
    }

    private long u32(long value) throws Exception {
        return Integer.toUnsignedLong(currentProgram.getMemory().getInt(address(value)));
    }

    private Function createExactBoundary(long firstValue, long lastValue, String name)
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
            cursor = instruction == null ? cursor.add(1) : instruction.getMaxAddress().add(1);
        }
        function = currentProgram.getListing().createFunction(
            name, first, new AddressSet(first, last), SourceType.ANALYSIS);
        if (function == null) throw new IllegalStateException("cannot create " + name);
        return function;
    }

    private void writeInstructions(BufferedWriter output, Function function) throws Exception {
        output.write("FUNCTION " + functionName(function) + " body=" + function.getBody() +
            " incoming=" + String.join(";", referencesTo(function.getEntryPoint())) +
            " outgoing=" + String.join(";", referencesFrom(function)) + "\n");
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            output.write(hex(instruction.getAddress()) + " " + instruction + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) + "\n");
        }
        output.write("\n");
    }

    private void writeWindow(BufferedWriter output, long first, long afterLast)
            throws Exception {
        output.write("WINDOW " + hex(first) + ".." + hex(afterLast) + "\n");
        Address cursor = address(first);
        Address limit = address(afterLast);
        while (cursor.compareTo(limit) < 0) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                output.write(hex(cursor) + " DB " + bytes(cursor.getUnsignedOffset(), 1) + "\n");
                cursor = cursor.add(1);
            }
            else {
                output.write(hex(cursor) + " " + instruction + "\n");
                cursor = instruction.getMaxAddress().add(1);
            }
        }
        output.write("\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException(
            "usage: NflJerseyLoaderCacheTrace.java OUTPUT_DIRECTORY");
        if (!EXPECTED_MD5.equalsIgnoreCase(currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected NFL 2K5 executable MD5 " +
                currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        createExactBoundary(0x00045100L, 0x000451CDL, "nfl_tset_finish_callback");
        createExactBoundary(CALLBACK, 0x000452F4L, "nfl_tset_load_callback");
        List<Function> functions = new ArrayList<>();
        for (long value : FOCUSED) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
            if (function == null) throw new IllegalStateException("missing function " + hex(value));
            functions.add(function);
        }
        functions.sort(Comparator.comparing(Function::getEntryPoint));

        try (BufferedWriter output = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_jersey_loader_cache_trace.txt")))) {
            output.write("NFL 2K5 TSET loader/cache focused static trace\n");
            output.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            output.write("Transient callback boundary: 0x00045280..0x000452F4\n\n");

            output.write("GLOBAL_REFERENCES\n");
            for (long value : GLOBALS) {
                output.write(hex(value) + " u32=" + hex(u32(value)) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
            }
            output.write("\nCALLBACK_BYTES\n");
            output.write(hex(CALLBACK) + " length=117 bytes=" + bytes(CALLBACK, 117) + "\n\n");

            writeWindow(output, 0x000450E0L, 0x000451D0L);
            writeWindow(output, 0x00063240L, 0x000632B0L);
            for (Function function : functions) writeInstructions(output, function);
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_jersey_loader_cache_pseudo_c.c")))) {
            output.write("/* NFL 2K5 TSET loader/cache focused pseudo-C. */\n\n");
            for (Function function : functions) {
                output.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 180, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 180 seconds" :
                        result.getErrorMessage();
                    output.write("// PORTME: could not decompile function at " +
                        hex(function.getEntryPoint()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                output.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_JERSEY_LOADER_CACHE_TRACE_COMPLETE functions=" + functions.size());
    }
}

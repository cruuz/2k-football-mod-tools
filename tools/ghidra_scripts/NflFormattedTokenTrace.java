// Read-only focused trace for NFL 2K5 pipe-delimited inline text tokens.
// @category VisualConcepts.NFL

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.LinkedHashSet;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;

public class NflFormattedTokenTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x00030A60L,
        0x00030BE0L,
        0x000449E0L,
        0x000469B0L,
        0x00046A20L,
        0x00046AF0L,
        0x00046B00L,
        0x00046B40L,
        0x00049390L,
        0x000EE8F0L,
        0x000EEDB0L,
        0x000EEF30L,
        0x000EEF60L,
        0x000EEF80L,
        0x000EF5A0L,
        0x000EFC40L,
        0x000F1D50L
    };

    private static final long[][] RAW_WINDOWS = {
        { 0x000EEDB0L, 0x000EF03DL },
        { 0x000EF5A0L, 0x000EF831L },
        { 0x000EFC40L, 0x000EFD5AL },
        { 0x000F1D50L, 0x000F1F1DL }
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

    private void writeFunction(BufferedWriter output, Function function)
            throws Exception {
        output.write("FUNCTION " + functionName(function) + " body=" +
            function.getBody() + "\n");
        InstructionIterator iterator = currentProgram.getListing()
            .getInstructions(function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            output.write(hex(instruction.getAddress().getUnsignedOffset()) +
                " " + instruction + "\n");
        }
        output.write("\n");
    }

    private void writeRange(BufferedWriter output, long first, long last)
            throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(last) + "\n");
        Address cursor = address(first);
        Address limit = address(last);
        while (cursor.compareTo(limit) <= 0) {
            Instruction instruction = currentProgram.getListing()
                .getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing()
                    .getInstructionAt(cursor);
            }
            cursor = instruction == null ? cursor.add(1) :
                instruction.getMaxAddress().add(1);
        }
        InstructionIterator iterator = currentProgram.getListing()
            .getInstructions(address(first), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            long value = instruction.getAddress().getUnsignedOffset();
            if (Long.compareUnsigned(value, last) > 0) break;
            output.write(hex(value) + " " + instruction + " owner=" +
                functionName(currentProgram.getFunctionManager()
                    .getFunctionContaining(instruction.getAddress())) + "\n");
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

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflFormattedTokenTrace.java OUTPUT_DIRECTORY");
        }
        if (!"444064a9ec984dd29d2c05a43f5c96e8".equalsIgnoreCase(
                currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected NFL 2K5 executable");
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        Set<Function> functions = new LinkedHashSet<>();
        File traceFile = new File(directory,
            "nfl_formatted_token_trace.txt");
        try (BufferedWriter output = new BufferedWriter(
                new FileWriter(traceFile))) {
            output.write("NFL 2K5 formatted inline-token trace\n");
            output.write("Program MD5: " +
                currentProgram.getExecutableMD5() + "\n\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager()
                    .getFunctionAt(address(value));
                output.write(hex(value) + " " + functionName(function) + "\n");
                if (function != null) functions.add(function);
            }
            output.write("\nSTATIC_TABLES\n");
            writeBytes(output, 0x00A91100L, 57 * 0x24);
            writeBytes(output, 0x00A90804L, 13 * 4);
            output.write("\nFUNCTIONS\n");
            for (Function function : functions) {
                writeFunction(output, function);
            }
            output.write("RAW_WINDOWS\n");
            for (long[] window : RAW_WINDOWS) {
                writeRange(output, window[0], window[1]);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory,
            "nfl_formatted_token_pseudo_c.c");
        try (BufferedWriter output = new BufferedWriter(
                new FileWriter(pseudoFile))) {
            output.write("/* NFL 2K5 formatted inline-token pseudo-C */\n\n");
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
                        hex(function.getEntryPoint().getUnsignedOffset()) + "\n");
                }
                output.write("\n\n");
            }
        }
        decompiler.dispose();
        println("NFL_FORMATTED_TOKEN_TRACE_COMPLETE functions=" +
            functions.size());
    }
}

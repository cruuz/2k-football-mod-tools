// Read-only focused trace for NFL 2K5 celebration selector producers.
// @category VisualConcepts.NFL

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
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

public class NflCelebrationSelectorProducerTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x00070870L,
        0x00077280L,
        0x0013F770L,
        0x00142380L,
        0x00142390L,
        0x00191CE0L,
        0x00191D30L,
        0x001B6B50L,
        0x002DE300L,
        0x002DE9C0L
    };

    private static final long[][] CALLER_WINDOWS = {
        { 0x0018D640L, 0x0018D8A0L },
        { 0x001ABF30L, 0x001AC00FL },
        { 0x00191D20L, 0x00191DA0L },
        { 0x00212AC0L, 0x00212C40L },
        { 0x002DE170L, 0x002DE310L },
        { 0x002DE760L, 0x002DE930L }
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

    private void writeFunctionInstructions(BufferedWriter output,
            Function function) throws Exception {
        output.write("FUNCTION " + functionName(function) + " body=" +
            function.getBody() + "\n");
        InstructionIterator instructions = currentProgram.getListing()
            .getInstructions(function.getBody(), true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            output.write(hex(instruction.getAddress().getUnsignedOffset()) +
                " " + instruction + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) +
                "\n");
        }
        output.write("\n");
    }

    private void writeInstructionRange(BufferedWriter output, long first,
            long last) throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(last) + "\n");
        Address cursor = address(first);
        Address limit = address(last);
        while (cursor.compareTo(limit) <= 0) {
            Instruction existing = currentProgram.getListing()
                .getInstructionAt(cursor);
            if (existing == null) {
                disassemble(cursor);
                existing = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (existing == null) {
                cursor = cursor.add(1);
            }
            else {
                cursor = existing.getMaxAddress().add(1);
            }
        }
        InstructionIterator instructions = currentProgram.getListing()
            .getInstructions(address(first), true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
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
            throw new IllegalStateException("short memory read at " +
                hex(first));
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
                "usage: NflCelebrationSelectorProducerTrace.java OUTPUT_DIRECTORY");
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
            "nfl_celebration_selector_producer_trace.txt");
        try (BufferedWriter output = new BufferedWriter(
                new FileWriter(traceFile))) {
            output.write("NFL 2K5 celebration selector producer trace\n");
            output.write("Program MD5: " +
                currentProgram.getExecutableMD5() + "\n\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager()
                    .getFunctionAt(address(value));
                output.write(hex(value) + " " + functionName(function) +
                    " refs=" + String.join(";", referencesTo(address(value))) +
                    "\n");
                if (function != null) functions.add(function);
            }
            output.write("\nSTATIC_FALLBACK_TABLES\n");
            writeBytes(output, 0x00BE50D0L, 0x100);
            writeBytes(output, 0x0050CFC8L, 37 * 12);
            writeBytes(output, 0x00AABEF8L, 0x274);
            output.write("\nFULL_FUNCTION_INSTRUCTIONS\n");
            for (Function function : functions) {
                writeFunctionInstructions(output, function);
            }
            output.write("CALLER_WINDOWS\n");
            for (long[] window : CALLER_WINDOWS) {
                writeInstructionRange(output, window[0], window[1]);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory,
            "nfl_celebration_selector_producer_pseudo_c.c");
        try (BufferedWriter output = new BufferedWriter(
                new FileWriter(pseudoFile))) {
            output.write("/* NFL 2K5 celebration selector producer pseudo-C */\n\n");
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
        println("NFL_CELEBRATION_SELECTOR_PRODUCER_TRACE_COMPLETE functions=" +
            functions.size());
    }
}

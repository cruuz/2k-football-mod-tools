// Read-only ownership trace for NFL 2K5 main-menu mode, selection, and draw coordinates.
// @category VisualConcepts.NFL

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
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class NflMainMenuLiveStateTrace extends GhidraScript {
    private static final int REFERENCE_LIMIT = 64;

    private static final long[] FOCUS = {
        0x0006BEF0L, 0x0006BFD0L, 0x0006C080L,
        0x0006E2D0L, 0x0006E2E0L, 0x0006E390L, 0x0006E400L,
        0x0006E4E0L, 0x0006E630L, 0x0006F260L,
        0x000F2810L, 0x000F2F00L, 0x000F2F70L, 0x000F37E0L, 0x000F3CD0L,
        0x000F3D60L, 0x000F3E90L,
        0x00143720L, 0x00143A00L, 0x00143DE0L,
        0x0014FB10L, 0x0014FB40L, 0x0014FB70L, 0x0014FC30L,
        0x0014FC50L, 0x0014FC60L, 0x0014FCD0L, 0x0014FDA0L,
        0x0014FF70L, 0x0014FF80L, 0x00150020L, 0x00150260L,
        0x00046920L, 0x00046A00L, 0x00046A70L, 0x00046B60L,
        0x00046200L, 0x00046310L,
        0x00046420L, 0x00046DF0L, 0x00047420L,
        0x0002CA70L, 0x0002D2A0L, 0x000F0140L, 0x000F1D50L,
        0x00192090L, 0x002ACB40L, 0x002C8950L, 0x002C8960L, 0x00327A90L
    };

    private static final long[][] RANGES = {
        // Saved function 0x0006bfd0 ends at the indirect jump; retain its
        // category targets and inline table as an explicit raw-code range.
        {0x0006BFD0L, 0x0006C07CL},
        // The main callback is a serialized function pointer but has no saved
        // Ghidra function boundary in the pinned project.
        {0x000F3E90L, 0x000F3F76L},
        // Retain the constructor's exact tail jump; the saved body has a gap
        // immediately before it that would otherwise look like inline data.
        {0x0014FF80L, 0x00150020L},
        // These action callbacks likewise remain deliberately boundary-less.
        {0x00192070L, 0x00192140L},
        {0x00327A70L, 0x00327B40L},
        // The default mode draw and selection hooks are one-byte RET stubs.
        {0x002C8950L, 0x002C8961L}
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String hex(Address value) {
        return value == null ? "none" : hex(value.getUnsignedOffset());
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return hex(function.getEntryPoint()) + ":" + function.getName();
    }

    private String section(Address value) {
        MemoryBlock block = currentProgram.getMemory().getBlock(value);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private String bytes(Instruction instruction) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : instruction.getBytes()) {
            if (result.length() != 0) result.append(' ');
            result.append(String.format("%02X", value & 0xff));
        }
        return result.toString();
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
        if (result.size() > REFERENCE_LIMIT) {
            int total = result.size();
            result = new ArrayList<>(result.subList(0, REFERENCE_LIMIT));
            result.add("TRUNCATED(total=" + total + ")");
        }
        return result;
    }

    private void writeTarget(BufferedWriter output, long value, Set<Function> functions)
            throws Exception {
        Address target = address(value);
        Function at = currentProgram.getFunctionManager().getFunctionAt(target);
        Function owner = currentProgram.getFunctionManager().getFunctionContaining(target);
        if (owner != null) functions.add(owner);
        output.write(hex(value) + " section=" + section(target) +
            " function_at=" + functionName(at) + " owner=" + functionName(owner) +
            " refs=" + String.join(";", referencesTo(target)) + "\n");
    }

    private void writeRange(BufferedWriter output, long first, long afterLast,
            Set<Function> functions) throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(afterLast - 1) + "\n");
        long value = first;
        while (value < afterLast) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                output.write(hex(value) + " <no instruction> // PORTME: inline data or " +
                    "decoder rejected the bytes\n");
                value++;
                continue;
            }
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                instruction.getAddress());
            if (owner != null) functions.add(owner);
            output.write(hex(value) + " " + bytes(instruction) + " " + instruction +
                " owner=" + functionName(owner) + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) + "\n");
            value = instruction.getMaxAddress().getUnsignedOffset() + 1;
        }
        output.write("\n");
    }

    private void writeFunction(BufferedWriter output, Function function) throws Exception {
        output.write("FUNCTION " + functionName(function) + " body=" +
            function.getBody() + "\n");
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            output.write(hex(instruction.getAddress()) + " " + bytes(instruction) + " " +
                instruction + " owner=" + functionName(function) + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) + "\n");
        }
        output.write("\n");
    }

    private void writeBytes(BufferedWriter output, long first, int count) throws Exception {
        byte[] data = new byte[count];
        Memory memory = currentProgram.getMemory();
        int read = memory.getBytes(address(first), data);
        if (read != count) throw new IllegalStateException("short read at " + hex(first));
        StringBuilder text = new StringBuilder();
        for (byte value : data) text.append(String.format("%02x", value & 0xff));
        output.write(hex(first) + " length=" + count + " bytes=" + text + "\n");
    }

    private void writeA7cInstructions(BufferedWriter output, Set<Function> functions)
            throws Exception {
        output.write("A7C_INSTRUCTIONS\n");
        InstructionIterator iterator = currentProgram.getListing().getInstructions(true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            String rendered = instruction.toString().toLowerCase();
            if (!rendered.contains("0xa7c")) continue;
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                instruction.getAddress());
            long value = instruction.getAddress().getUnsignedOffset();
            if (owner != null && 0x0014FB00L <= value && value < 0x00150300L) {
                functions.add(owner);
            }
            output.write(hex(instruction.getAddress()) + " " + bytes(instruction) + " " +
                instruction + " owner=" + functionName(owner) + "\n");
        }
        output.write("\n");
    }

    private List<Function> sorted(Set<Function> functions) {
        List<Function> result = new ArrayList<>(functions);
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflMainMenuLiveStateTrace.java OUTPUT_DIRECTORY");
        }
        if (!"444064a9ec984dd29d2c05a43f5c96e8".equalsIgnoreCase(
                currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected NFL 2K5 executable");
        }
        // The saved project split the five-byte tail jump at 0x00150015 into
        // overlapping data/instructions. Re-decode only this transient range;
        // headless -readOnly discards it with every other script-side change.
        clearListing(address(0x00150015L), address(0x00150019L));
        disassemble(address(0x00150015L));
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }
        Set<Function> functions = new LinkedHashSet<>();
        File traceFile = new File(directory, "nfl_main_menu_live_state_trace.txt");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(traceFile))) {
            output.write("NFL 2K5 main-menu live-state and coordinate trace\n");
            output.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            output.write("Read-only transient disassembly; saved project is not modified.\n\n");
            output.write("FOCUS\n");
            for (long value : FOCUS) writeTarget(output, value, functions);
            output.write("\nSTATIC_BYTES\n");
            writeBytes(output, 0x00515660L, 0x2c);
            writeBytes(output, 0x00515490L, 0x30);
            writeBytes(output, 0x005154C0L, 0x16c);
            writeBytes(output, 0x00509A30L, 0x30);
            writeBytes(output, 0x0015023CL, 0x14);
            writeBytes(output, 0x0006C05CL, 0x20);
            writeBytes(output, 0x004FF250L, 0x10);
            output.write("\n");
            writeA7cInstructions(output, functions);
            output.write("FOCUS_FUNCTION_INSTRUCTIONS\n");
            for (Function function : sorted(functions)) writeFunction(output, function);
            output.write("MANUAL_RANGES\n");
            for (long[] range : RANGES) writeRange(output, range[0], range[1], functions);
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory, "nfl_main_menu_live_state_pseudo_c.c");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(pseudoFile))) {
            output.write("/* NFL 2K5 main-menu live-state saved-boundary pseudo-C. */\n\n");
            for (long value : FOCUS) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
                if (function == null) {
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                        address(value));
                    if (owner == null) {
                        output.write("// PORTME: could not decompile function at " + hex(value) +
                            "; Ghidra has no saved function boundary at this entry.\n");
                    }
                    else {
                        output.write("// NOTE: " + hex(value) + " is a non-entry block owned by " +
                            functionName(owner) + "; its owner is decompiled below.\n");
                    }
                }
            }
            output.write("\n");
            for (Function function : sorted(functions)) {
                output.write("/* " + functionName(function) + " body=" +
                    function.getBody() + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 90 seconds" :
                        result.getErrorMessage();
                    output.write("// PORTME: could not decompile function at " +
                        hex(function.getEntryPoint()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                output.write("\n\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_MAIN_MENU_LIVE_STATE_TRACE_COMPLETE functions=" + functions.size());
    }
}

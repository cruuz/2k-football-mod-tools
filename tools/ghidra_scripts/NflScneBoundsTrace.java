// Emit focused NFL 2K5 SCNE node, visibility, and bounds-consumer evidence.
// @category Xbox.NFL2K5

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
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class NflScneBoundsTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x00021520L, 0x000215A0L, 0x00021630L, 0x000217F0L,
        0x00021860L, 0x00022F90L, 0x000233C0L, 0x00023750L,
        0x00023760L, 0x000243D0L,
        0x0002ADB0L, 0x0002ADC0L, 0x0002AF70L, 0x00031110L
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

    private List<String> referencesTo(Address target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            result.add(hex(reference.getFromAddress().getUnsignedOffset()) + "(" +
                functionName(owner) + "," + reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private void writeFunction(BufferedWriter output, Function function) throws Exception {
        output.write("\nFUNCTION " + functionName(function) + "\n");
        output.write("REFERENCES " + String.join(";", referencesTo(function.getEntryPoint())) + "\n");
        Instruction instruction = currentProgram.getListing().getInstructionAt(
            function.getEntryPoint());
        while (instruction != null && function.getBody().contains(instruction.getAddress())) {
            output.write(hex(instruction.getAddress().getUnsignedOffset()) + " " + instruction +
                " refs=" + String.join(";", referencesTo(instruction.getAddress())) + "\n");
            instruction = instruction.getNext();
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: NflScneBoundsTrace.java OUTPUT_DIRECTORY");
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

        Set<Function> functions = new LinkedHashSet<>();
        for (long value : FOCUSED) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
            if (function == null) throw new IllegalStateException("no function at " + hex(value));
            functions.add(function);
        }

        try (BufferedWriter trace = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_scne_bounds_trace.txt")))) {
            trace.write("NFL 2K5 SCNE node/bounds focused trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            for (Function function : functions) writeFunction(trace, function);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_scne_bounds_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 SCNE node/bounds focused pseudo-C. */\n\n");
            for (Function function : functions) {
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                pseudo.write("/* " + functionName(function) + " */\n");
                if (!result.decompileCompleted()) {
                    pseudo.write("// PORTME: could not decompile " + functionName(function) + "\n\n");
                } else {
                    pseudo.write(result.getDecompiledFunction().getC());
                    pseudo.write("\n\n");
                }
            }
        } finally {
            decompiler.dispose();
        }
    }
}

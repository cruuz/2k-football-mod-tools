// Trace NFL 2K5 LAYT relocation, traversal, transform, and runtime draw gate.
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
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Nfl2k5LayoutTrace extends GhidraScript {
    private static final long[] FOCUS = {
        0x000379A0L, // affine translation composition
        0x00143290L, // event callback transform/context preparation
        0x00143450L, // callback table at layout runtime +0x0c
        0x00143510L, // phase-filtered callback table at runtime +0x10
        0x00143600L, // callback table at runtime +0x14
        0x00143660L, // callback table at runtime +0x18
        0x00143720L, // type-0 render path consumes +0x10/+0x14/+0x18
        0x00143A00L, // record traversal and type-2 child-layout recursion
        0x00143C30L, // recursive layout runtime-state propagation
        0x00143C80L, // record lookup by +0x0c identifier
        0x00143CE0L, // type-0 progress/timing update
        0x00143EA0L, // runtime record resolution
        0x00143FC0L, // resolved object getter
        0x00143FE0L, // type-0 runtime draw-gate setter at +0x38
        0x00144000L, // four-word +0x10 vector setter
        0x00144020L, // +0x10 vector accessor
        0x001690B0L, // LAYT relocator (embedded callback, no function required)
        0x00169160L, // LAYT load callback
        0x001691A0L  // LAYT registration
    };

    private static final long[][] RANGES = {
        {0x000379A0L, 0x00037A00L},
        {0x00143290L, 0x0014371DL},
        {0x00143720L, 0x00144063L},
        {0x001690B0L, 0x001691B4L}
    };

    // This address begins "main_menu_sub", not a standalone "main_menu".
    private static final long MAIN_MENU_SUB_PREFIX_UTF16 = 0x00E8B1E0L;
    private static final long MAIN_NAVI_UTF16 = 0x00E9D4A8L;

    private String addr(Address address) {
        return address == null ? "" : String.format("0x%08X", address.getUnsignedOffset());
    }

    private String functionName(Function function) {
        return function == null ? "none" : addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private String section(Address address) {
        MemoryBlock block = currentProgram.getMemory().getBlock(address);
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
            result.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
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
            throw new IllegalArgumentException("usage: Nfl2k5LayoutTrace.java OUTPUT_DIRECTORY");
        }
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }
        Set<Function> functions = new LinkedHashSet<>();
        File traceFile = new File(output, "layout_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("NFL 2K5 LAYT focused static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("Program language: " + currentProgram.getLanguageID() + "\n");
            trace.write("Constraint: main-menu strings inside serialized resources are not " +
                "called code unless an executable reference exists.\n\n");
            for (long value : FOCUS) {
                Address address = toAddr(value);
                Function function = currentProgram.getFunctionManager().getFunctionContaining(address);
                if (function != null) functions.add(function);
                trace.write(addr(address) + " section=" + section(address) + " owner=" +
                    functionName(function) + " refs=" + String.join(";", referencesTo(address)) +
                    "\n");
            }
            trace.write("\nMAIN_MENU_SERIALIZED_STRINGS\n");
            for (long value : new long[] {MAIN_MENU_SUB_PREFIX_UTF16, MAIN_NAVI_UTF16}) {
                Address address = toAddr(value);
                trace.write(addr(address) + " section=" + section(address) + " refs=" +
                    String.join(";", referencesTo(address)) + "\n");
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(output, "layout_focused_pseudo_c.c");
        File disassemblyFile = new File(output, "layout_focused_disassembly.txt");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile));
             BufferedWriter disassembly = new BufferedWriter(new FileWriter(disassemblyFile))) {
            pseudo.write("/* NFL 2K5 LAYT focused pseudo-C; unknown fields stay raw. */\n\n");
            disassembly.write("NFL 2K5 LAYT exact evidence ranges\n\n");
            for (long[] range : RANGES) {
                Address start = toAddr(range[0]);
                Address end = toAddr(range[1]);
                disassembly.write(addr(start) + "-" + addr(end) + "\n");
                disassembly.write("RAW_BYTES\n");
                long length = range[1] - range[0] + 1;
                for (long offset = 0; offset < length; offset += 16) {
                    int count = (int)Math.min(16, length - offset);
                    byte[] raw = new byte[count];
                    currentProgram.getMemory().getBytes(start.add(offset), raw);
                    StringBuilder rawText = new StringBuilder();
                    for (byte value : raw) {
                        if (rawText.length() != 0) rawText.append(' ');
                        rawText.append(String.format("%02X", value & 0xff));
                    }
                    disassembly.write(addr(start.add(offset)) + "  " + rawText + "\n");
                }
                disassembly.write("DEFINED_INSTRUCTIONS\n");
                InstructionIterator iterator = currentProgram.getListing().getInstructions(
                    new AddressSet(start, end), true);
                while (iterator.hasNext()) {
                    Instruction instruction = iterator.next();
                    disassembly.write(addr(instruction.getAddress()) + "  " +
                        bytes(instruction) + "  " + instruction + "\n");
                }
                disassembly.write("\n");
            }
            for (Function function : sorted(functions)) {
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 30 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        addr(function.getEntryPoint()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL2K5_LAYOUT_TRACE_COMPLETE functions=" + functions.size());
    }
}

// Trace NFL 2K5 ROST loading, relocation, and fixed-stride consumers.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
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
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Nfl2k5RosterTrace extends GhidraScript {
    private static final long ROST_SCALAR = 0x54534F52L;

    private static final long[] FOCUS = {
        0x000BFEA0L, 0x000BFED0L, 0x000BFF00L, 0x000BFF50L,
        0x000C0010L, 0x000C0500L, 0x000C0730L, 0x000C09B0L,
        0x000C1030L, 0x000C1E30L, 0x000C1F00L, 0x000C1F50L,
        0x000C2040L, 0x000C2180L,
        0x000E5E70L, 0x000E5EB0L,
        0x00196FE0L, 0x00197000L,
        0x002415C0L, 0x00241610L,
        0x002418C0L, 0x00241A20L,
        0x00241E60L, 0x00241EB0L,
        0x002421D0L, 0x002421E0L,
        0x00242340L, 0x00242360L,
        0x002425F0L, 0x00242630L,
        0x002A7200L, 0x002A7360L,
        0x002D1740L, 0x002D17B0L
    };

    private static final long[] GLOBALS = {
        0x00B72804L, 0x00B72808L, 0x00B7280CL, 0x00B72918L
    };

    private String addr(Address address) {
        if (address == null) return "";
        return address.isMemoryAddress()
            ? String.format("0x%08X", address.getUnsignedOffset()) : address.toString();
    }

    private String section(Address address) {
        MemoryBlock block = currentProgram.getMemory().getBlock(address);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<Function> sorted(Set<Function> functions) {
        List<Function> result = new ArrayList<>(functions);
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
    }

    private String relations(Set<Function> functions) {
        List<String> result = new ArrayList<>();
        for (Function function : sorted(functions)) result.add(functionName(function));
        return String.join(";", result);
    }

    private List<Address> findBytes(byte[] needle) throws Exception {
        List<Address> hits = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                hits.add(hit);
                cursor = hit.add(1);
            }
        }
        return hits;
    }

    private void writeReferences(BufferedWriter output, Address target) throws Exception {
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        int count = 0;
        List<String> lines = new ArrayList<>();
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            lines.add(addr(reference.getFromAddress()) + " type=" + reference.getReferenceType() +
                " owner=" + functionName(owner));
            count++;
        }
        output.write("TARGET " + addr(target) + " section=" + section(target) +
            " reference_count=" + count + "\n");
        for (String line : lines) output.write("  " + line + "\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: Nfl2k5RosterTrace.java OUTPUT_DIRECTORY");
        }
        File outputDirectory = new File(args[0]);
        if (!outputDirectory.isDirectory() && !outputDirectory.mkdirs()) {
            throw new IllegalStateException("cannot create " + outputDirectory);
        }
        File traceFile = new File(outputDirectory, "roster_trace.txt");
        File pseudoFile = new File(outputDirectory, "roster_focused_pseudo_c.c");
        File disassemblyFile = new File(outputDirectory, "roster_focused_disassembly.txt");
        Set<Function> functions = new LinkedHashSet<>();

        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("NFL 2K5 ROST static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("Constraint: names below describe statically proved operations, not a source-perfect reconstruction.\n\n");

            List<Address> rawHits = findBytes("ROST".getBytes(StandardCharsets.US_ASCII));
            trace.write("RAW_ROST count=" + rawHits.size() + "\n");
            for (Address hit : rawHits) {
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(hit);
                if (owner != null) functions.add(owner);
                trace.write(addr(hit) + " section=" + section(hit) +
                    " containing=" + functionName(owner) + "\n");
            }

            trace.write("\nSCALAR_ROST\n");
            int scalarCount = 0;
            InstructionIterator all = currentProgram.getListing().getInstructions(true);
            while (all.hasNext()) {
                Instruction instruction = all.next();
                for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                    for (Object object : instruction.getOpObjects(operand)) {
                        if (!(object instanceof Scalar)) continue;
                        if (((Scalar)object).getUnsignedValue() != ROST_SCALAR) continue;
                        Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                            instruction.getAddress());
                        if (owner != null) functions.add(owner);
                        trace.write(addr(instruction.getAddress()) + " " + instruction +
                            " owner=" + functionName(owner) + "\n");
                        scalarCount++;
                    }
                }
            }
            trace.write("SCALAR_ROST_COUNT=" + scalarCount + "\n\n");

            trace.write("FOCUS_FUNCTIONS\n");
            for (long value : FOCUS) {
                Address address = toAddr(value);
                Function function = currentProgram.getFunctionManager().getFunctionAt(address);
                if (function == null) {
                    trace.write(addr(address) + " MISSING\n");
                    continue;
                }
                functions.add(function);
                trace.write(functionName(function) + " section=" + section(address) +
                    " callers=" + relations(function.getCallingFunctions(monitor)) +
                    " callees=" + relations(function.getCalledFunctions(monitor)) + "\n");
            }

            trace.write("\nENTRY_AND_GLOBAL_REFERENCES\n");
            writeReferences(trace, toAddr(0x000C2040L));
            writeReferences(trace, toAddr(0x000C2180L));
            for (long value : GLOBALS) writeReferences(trace, toAddr(value));
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile));
             BufferedWriter disassembly = new BufferedWriter(new FileWriter(disassemblyFile))) {
            pseudo.write("/* NFL 2K5 ROST focused pseudo-C; types and semantic names remain provisional. */\n\n");
            disassembly.write("NFL 2K5 ROST focused disassembly\n\n");
            for (Function function : sorted(functions)) {
                pseudo.write("/* " + functionName(function) +
                    " callers=" + relations(function.getCallingFunctions(monitor)) +
                    " callees=" + relations(function.getCalledFunctions(monitor)) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 30 seconds" : result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        addr(function.getEntryPoint()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");

                disassembly.write(functionName(function) + "\n");
                InstructionIterator instructions = currentProgram.getListing().getInstructions(
                    function.getBody(), true);
                while (instructions.hasNext()) {
                    Instruction instruction = instructions.next();
                    disassembly.write(addr(instruction.getAddress()) + "  " + instruction + "\n");
                }
                disassembly.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL2K5_ROSTER_TRACE_COMPLETE functions=" + functions.size());
    }
}

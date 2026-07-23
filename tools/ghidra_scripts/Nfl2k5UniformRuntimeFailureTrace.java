// Read-only trace for NFL 2K5 uniform-resource loading and archive integrity.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
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
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Nfl2k5UniformRuntimeFailureTrace extends GhidraScript {
    private static byte[] utf16le(String value) {
        byte[] text = value.getBytes(StandardCharsets.UTF_16LE);
        byte[] terminated = new byte[text.length + 2];
        System.arraycopy(text, 0, terminated, 0, text.length);
        return terminated;
    }

    private String addr(Address address) {
        return address == null ? "" : String.format("0x%08X", address.getUnsignedOffset());
    }

    private String fn(Function function) {
        return function == null ? "none" : addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<Address> find(byte[] needle) throws Exception {
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

    private static byte[] pointerBytes(Address address) {
        long value = address.getUnsignedOffset();
        return new byte[] {
            (byte)value, (byte)(value >>> 8), (byte)(value >>> 16), (byte)(value >>> 24),
        };
    }

    private void collectRelations(Set<Function> functions, Function owner) throws Exception {
        if (owner == null || !functions.add(owner)) return;
        functions.addAll(owner.getCallingFunctions(monitor));
        functions.addAll(owner.getCalledFunctions(monitor));
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("usage: SCRIPT OUTPUT_DIRECTORY");
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }
        File traceFile = new File(directory, "trace.txt");
        File pseudoFile = new File(directory, "pseudo_c.c");
        Set<Function> functions = new LinkedHashSet<>();

        String[] labels = {"VC_53450030", "D:\\"};
        byte[][] needles = {utf16le(labels[0]), utf16le(labels[1])};
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("NFL 2K5 uniform runtime-failure static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("Read-only: string xrefs plus one-hop owners; no inferred integrity field.\n\n");
            for (int index = 0; index < needles.length; index++) {
                List<Address> hits = find(needles[index]);
                trace.write("UTF16LE " + labels[index] + " hits=" + hits.size() + "\n");
                for (Address hit : hits) {
                    trace.write("  hit " + addr(hit) + "\n");
                    ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(hit);
                    while (refs.hasNext()) {
                        Reference reference = refs.next();
                        Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                            reference.getFromAddress());
                        trace.write("    ref " + addr(reference.getFromAddress()) +
                            " type=" + reference.getReferenceType() + " owner=" + fn(owner) + "\n");
                        collectRelations(functions, owner);
                    }
                    // The saved project does not define every UTF-16 item as a
                    // string, so immediate operands may lack formal xrefs.
                    // Preserve every in-memory little-endian address literal too.
                    for (Address literal : find(pointerBytes(hit))) {
                        Function owner = currentProgram.getFunctionManager().getFunctionContaining(literal);
                        trace.write("    address_literal " + addr(literal) +
                            " owner=" + fn(owner) + "\n");
                        collectRelations(functions, owner);
                    }
                }
                trace.write("\n");
            }

            // Fixed anchors required to reason about the actual edited bytes.
            long[] anchors = {
                0x00038570L, 0x000385D0L, 0x00038650L,
                0x00041930L, 0x00042210L, 0x00042450L, 0x00042820L,
                0x00043D20L, 0x000449E0L, 0x0007BB40L,
                0x00078D40L, 0x00078DD0L, 0x0008E3F0L,
                0x0008E430L, 0x0008E470L, 0x0008E850L,
                0x0008E860L, 0x0008E9E0L, 0x0008EFA0L,
                0x00090570L, 0x00166420L, 0x00166450L,
                0x00166490L, 0x0029C300L, 0x0029C590L,
            };
            for (long value : anchors) {
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(toAddr(value));
                if (owner != null) functions.add(owner);
                trace.write("ANCHOR " + String.format("0x%08X", value) + " owner=" + fn(owner) + "\n");
            }

            List<Function> ordered = new ArrayList<>(functions);
            ordered.removeIf(function -> function == null);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));
            trace.write("\nFUNCTIONS count=" + ordered.size() + "\n");
            for (Function function : ordered) {
                List<String> callers = new ArrayList<>();
                for (Function caller : function.getCallingFunctions(monitor)) callers.add(fn(caller));
                callers.sort(String::compareTo);
                List<String> callees = new ArrayList<>();
                for (Function callee : function.getCalledFunctions(monitor)) callees.add(fn(callee));
                callees.sort(String::compareTo);
                trace.write(fn(function) + " callers=" + String.join(";", callers) +
                    " callees=" + String.join(";", callees) + "\n");
            }

            DecompInterface decompiler = new DecompInterface();
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("decompiler could not open program");
            }
            try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
                pseudo.write("/* NFL 2K5 uniform runtime-failure focused pseudo-C. */\n\n");
                for (Function function : ordered) {
                    pseudo.write("/* " + fn(function) + " */\n");
                    DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                    if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                        pseudo.write(result.getDecompiledFunction().getC());
                    } else {
                        pseudo.write("// PORTME: decompilation failed: " +
                            result.getErrorMessage().replace('\n', ' ').replace('\r', ' ') + "\n");
                    }
                    pseudo.write("\n");
                }
            } finally {
                decompiler.dispose();
            }
        }
        println("NFL2K5_UNIFORM_RUNTIME_FAILURE_TRACE_COMPLETE");
    }
}

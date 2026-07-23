// Emit focused static evidence for the NFL 2K5 referee penalty-clip owner.
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
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class NflRefClipOwnershipTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x001685B0L, 0x001685E0L,
        0x001FA140L, 0x001FA240L, 0x001FA350L,
        0x001FB0B0L, 0x001FB1A0L, 0x001FB250L, 0x001FB3E0L,
        0x001FBB90L, 0x001FBE50L, 0x001FC590L, 0x001FC5F0L,
        0x001FC710L, 0x001FCFA0L, 0x00210DF0L,
        0x00217EB0L,
        0x002405F0L, 0x00240670L, 0x002406E0L, 0x00240750L,
        0x002407D0L, 0x002408A0L,
        0x002D6B70L, 0x0031C180L,
        0x00096590L, 0x00096600L, 0x00096A80L, 0x00096B20L,
        0x0012F670L, 0x00130150L
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

    private void writeInstructions(BufferedWriter output, long first, long afterLast)
            throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(afterLast - 1) + "\n");
        Address cursor = address(first);
        Address limit = address(afterLast);
        while (cursor.compareTo(limit) < 0) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                output.write(hex(cursor.getUnsignedOffset()) +
                    " <no instruction> // PORTME: inline data or missing boundary\n");
                cursor = cursor.add(1);
            }
            else {
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(cursor);
                output.write(hex(cursor.getUnsignedOffset()) + " " + instruction +
                    " owner=" + functionName(owner) + " refs=" +
                    String.join(";", referencesTo(cursor)) + "\n");
                cursor = instruction.getMaxAddress().add(1);
            }
        }
    }

    private void writeBytes(BufferedWriter output, long first, int length) throws Exception {
        Memory memory = currentProgram.getMemory();
        byte[] bytes = new byte[length];
        int read = memory.getBytes(address(first), bytes);
        if (read != length) throw new IllegalStateException("short memory read at " + hex(first));
        StringBuilder builder = new StringBuilder();
        for (byte value : bytes) builder.append(String.format("%02x", value & 0xff));
        output.write(hex(first) + " length=" + length + " bytes=" + builder + "\n");
    }

    private void writeReferences(BufferedWriter output, long target) throws Exception {
        output.write(hex(target) + " refs=" +
            String.join(";", referencesTo(address(target))) + "\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflRefClipOwnershipTrace.java OUTPUT_DIRECTORY");
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
        List<Long> missingFunctions = new ArrayList<>();
        File traceFile = new File(directory, "nfl_ref_clip_ownership_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("NFL 2K5 referee penalty-clip ownership focused static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n\n");

            trace.write("SELECTOR_AND_LOOKUP\n");
            writeInstructions(trace, 0x001685B0L, 0x00168660L);
            writeInstructions(trace, 0x002405F0L, 0x00240970L);

            trace.write("\nPENALTY_ACTOR_SELECTION_AND_STATE\n");
            writeInstructions(trace, 0x001FA140L, 0x001FA3A0L);
            writeInstructions(trace, 0x001FB0B0L, 0x001FB400L);
            writeInstructions(trace, 0x001FBB90L, 0x001FBED0L);
            writeInstructions(trace, 0x001FC590L, 0x001FC650L);
            writeInstructions(trace, 0x001FC710L, 0x001FC7B0L);
            writeInstructions(trace, 0x001FCFA0L, 0x001FD080L);
            writeInstructions(trace, 0x00210DF0L, 0x00210EC0L);

            trace.write("\nREFEREE_POOL_INITIALIZER\n");
            writeInstructions(trace, 0x00096590L, 0x00096B50L);
            writeInstructions(trace, 0x00217EB0L, 0x00217F20L);

            trace.write("\nCONTROLLER_HANDOFF\n");
            writeInstructions(trace, 0x002D6B70L, 0x002D6CC0L);

            trace.write("\nTYPE4_CORROBORATION\n");
            writeInstructions(trace, 0x0012F7A0L, 0x0012F9F2L);

            trace.write("\nSTATIC_BYTES\n");
            writeBytes(trace, 0x00513F28L, 0x138);
            writeBytes(trace, 0x00514060L, 0x14);
            writeBytes(trace, 0x0051D010L, 50);
            writeBytes(trace, 0x00E65CBCL, 0x20);
            writeBytes(trace, 0x00E65CCCL, 0x20);
            writeBytes(trace, 0x00E65DD0L, 0x20);
            writeBytes(trace, 0x00E87F78L, 0x80);
            writeBytes(trace, 0x00E887B0L, 0x20);

            trace.write("\nKEY_REFERENCES\n");
            long[] referenceTargets = {
                0x001685B0L, 0x001685E0L,
                0x001FA140L, 0x001FA240L, 0x001FA350L,
                0x001FB1A0L, 0x001FB3E0L, 0x001FBB90L, 0x001FBE50L,
                0x001FC590L, 0x001FC5F0L, 0x001FC710L,
                0x001FCFA0L, 0x00210DF0L,
                0x00217EB0L,
                0x00240750L, 0x002407D0L, 0x002408A0L,
                0x002D6B70L, 0x0031C180L,
                0x00096590L, 0x00096600L, 0x00096A80L, 0x00096B20L,
                0x0012F670L, 0x00130150L,
                0x00513F28L, 0x00513F5CL, 0x00514060L,
                0x0051D010L, 0x00E60274L, 0x00E887B0L, 0x00E87FB8L
            };
            for (long target : referenceTargets) writeReferences(trace, target);

            trace.write("\nFOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(
                    address(value));
                trace.write(hex(value) + " " + functionName(function) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
                if (function != null) functions.add(function);
                else missingFunctions.add(value);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory,
            "nfl_ref_clip_ownership_focused_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* NFL 2K5 referee penalty-clip ownership focused pseudo-C. */\n\n");
            for (long value : missingFunctions) {
                pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                    "; Ghidra has no saved function boundary; exact instructions are " +
                    "retained in nfl_ref_clip_ownership_trace.txt.\n");
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
        println("NFL_REF_CLIP_OWNERSHIP_TRACE_COMPLETE functions=" + functions.size() +
            " missing=" + missingFunctions.size());
    }
}

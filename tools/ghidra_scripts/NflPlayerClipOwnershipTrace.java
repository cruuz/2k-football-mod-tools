// Read-only Ghidra evidence pass for one NFL 2K5 player celebration clip.

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
import ghidra.app.util.PseudoDisassembler;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class NflPlayerClipOwnershipTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x001685B0L, 0x001685E0L,
        0x001B6B50L, 0x001B6C70L, 0x001B7460L,
        0x001B7A90L, 0x001B80D0L,
        0x00217D00L, 0x00217E10L, 0x00218010L, 0x002180D0L,
        0x002CC570L, 0x002D6B70L,
        0x002DDB10L, 0x002DE170L, 0x002DE9C0L,
        0x0031BEB0L, 0x0031C180L,
        0x0011A7C0L, 0x0028E360L, 0x001DFAA0L,
        0x00090570L, 0x00091890L, 0x000918D0L,
        0x00092140L, 0x00093800L, 0x00093850L,
        0x0002EB70L, 0x000233C0L, 0x00022C00L,
        0x00021860L, 0x000243D0L, 0x00037EB0L, 0x003CA3D0L
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
        PseudoDisassembler pseudo = new PseudoDisassembler(currentProgram);
        while (cursor.compareTo(limit) < 0) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                pseudo.disassemble(cursor);
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
                "usage: NflPlayerClipOwnershipTrace.java OUTPUT_DIRECTORY");
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
        File traceFile = new File(directory, "nfl_player_clip_ownership_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("NFL 2K5 player celebration-clip ownership focused static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n\n");

            trace.write("CELEBRATION_SELECTION_ACQUIRE_AND_PLAY\n");
            writeInstructions(trace, 0x001685B0L, 0x00168660L);
            writeInstructions(trace, 0x001B6B50L, 0x001B6CA0L);
            writeInstructions(trace, 0x001B7460L, 0x001B7920L);
            writeInstructions(trace, 0x001B7A90L, 0x001B7C00L);
            writeInstructions(trace, 0x001B80D0L, 0x001B8200L);
            writeInstructions(trace, 0x002DDAF0L, 0x002DE220L);
            writeInstructions(trace, 0x002DE9C0L, 0x002DEA40L);

            trace.write("\nPLAYER_CONTROLLER_AND_MAP\n");
            writeInstructions(trace, 0x00217D00L, 0x00218150L);
            writeInstructions(trace, 0x002CC570L, 0x002CC640L);
            writeInstructions(trace, 0x002D6B70L, 0x002D6CC0L);
            writeInstructions(trace, 0x0031BEB0L, 0x0031C480L);

            trace.write("\nGAMEPLAY_PLAYER_POSE_HIERARCHY_AND_RENDER\n");
            writeInstructions(trace, 0x0011A7C0L, 0x0011A8E7L);
            writeInstructions(trace, 0x0028E360L, 0x0028E9EBL);
            writeInstructions(trace, 0x001DFAA0L, 0x001DFB40L);
            writeInstructions(trace, 0x00090570L, 0x00090690L);
            writeInstructions(trace, 0x00090FD0L, 0x00091040L);
            writeInstructions(trace, 0x00091890L, 0x00091920L);
            writeInstructions(trace, 0x00092140L, 0x00092210L);
            writeInstructions(trace, 0x000937D0L, 0x00093850L);
            writeInstructions(trace, 0x00093850L, 0x00093B40L);
            writeInstructions(trace, 0x0002EB70L, 0x0002EB80L);
            writeInstructions(trace, 0x000233C0L, 0x00023480L);
            writeInstructions(trace, 0x00021860L, 0x000218C3L);
            writeInstructions(trace, 0x00022C00L, 0x00022E20L);
            writeInstructions(trace, 0x000243D0L, 0x00024480L);
            writeInstructions(trace, 0x00037EB0L, 0x00037F40L);

            trace.write("\nSTATIC_BYTES\n");
            writeBytes(trace, 0x0050CFC8L, 37 * 12);
            writeBytes(trace, 0x0051CD70L, 50);
            writeBytes(trace, 0x00E8470CL, 0x20);
            writeBytes(trace, 0x00E8480CL, 0x40);
            writeBytes(trace, 0x00E63E60L, 0x20);

            trace.write("\nKEY_REFERENCES\n");
            long[] targets = {
                0x001685B0L, 0x001685E0L,
                0x001B6B50L, 0x001B6C70L, 0x001B7460L,
                0x001B7A90L, 0x001B80D0L,
                0x00217E10L, 0x00218010L, 0x002180D0L,
                0x002CC570L, 0x002D6B70L, 0x002DE9C0L,
                0x0011A7C0L, 0x0028E360L, 0x001DFAA0L,
                0x00091890L, 0x00092140L, 0x00093800L, 0x00093850L,
                0x000233C0L, 0x00022C00L,
                0x0050CFC8L, 0x0051CD70L,
                0x00BE50C0L, 0x00BE50C4L, 0x00BE50CCL,
                0x00E60268L, 0x00E8470CL, 0x00E8480CL,
                0x00E63E60L, 0x00E63E70L
            };
            for (long target : targets) writeReferences(trace, target);

            trace.write("\nFOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
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
            "nfl_player_clip_ownership_focused_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* NFL 2K5 player celebration-clip ownership focused pseudo-C. */\n\n");
            for (long value : missingFunctions) {
                pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                    "; Ghidra has no saved function boundary; exact instructions are " +
                    "retained in nfl_player_clip_ownership_trace.txt.\n");
            }
            if (!missingFunctions.isEmpty()) pseudo.write("\n");
            for (Function function : functions) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 90 seconds" :
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
        println("NFL_PLAYER_CLIP_OWNERSHIP_TRACE_COMPLETE functions=" + functions.size() +
            " missing=" + missingFunctions.size());
    }
}

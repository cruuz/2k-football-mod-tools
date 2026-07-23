// Emit focused static evidence for the NFL 2K5 SMCD runtime sampler.
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

public class NflMotionSamplerTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        0x001685B0L, 0x001685E0L, 0x001B6B50L, 0x001B6C70L,
        0x002406C0L, 0x002406E0L, 0x00240750L, 0x002407D0L,
        0x002408A0L, 0x00240970L,
        0x000DED10L, 0x000DEE30L, 0x000DF030L, 0x000DF0D0L, 0x000DF180L,
        0x000DF220L, 0x000DF2F0L, 0x000DF3D0L, 0x000DF450L,
        0x000DF6A0L, 0x000DF700L, 0x000DF8B0L, 0x000DF9B0L,
        0x000DFA50L, 0x000DFB40L, 0x000DFC70L,
        0x0031B190L, 0x0031B1C0L, 0x0031B2E0L, 0x0031B4E0L,
        0x0031B910L, 0x0031BAC0L, 0x0031BD40L, 0x0031BEB0L,
        0x0031C0D0L, 0x0031C180L
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
        Address cursor = address(first);
        Address limit = address(afterLast);
        while (cursor.compareTo(limit) < 0) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                output.write(hex(cursor.getUnsignedOffset()) + " <no instruction>\n");
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
                "usage: NflMotionSamplerTrace.java OUTPUT_DIRECTORY");
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
        File traceFile = new File(directory, "nfl_motion_sampler_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("NFL 2K5 SMCD runtime sampler focused static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n\n");

            trace.write("LOOKUP_CALLERS_AND_PLAY_SETUP\n");
            writeInstructions(trace, 0x001685B0L, 0x00168660L);
            writeInstructions(trace, 0x001B6B50L, 0x001B6CA0L);
            writeInstructions(trace, 0x002406C0L, 0x00240980L);

            trace.write("\nPACKED_ROOT_SAMPLERS\n");
            writeInstructions(trace, 0x000DED10L, 0x000DFE30L);

            trace.write("\nCONTROLLER_AND_CHANNEL_ITERATION\n");
            writeInstructions(trace, 0x0031B190L, 0x0031C480L);

            trace.write("\nCONSTANTS_AND_STATIC_DEFAULT_ROOT\n");
            writeBytes(trace, 0x004EEA18L, 4);
            writeBytes(trace, 0x004F24A0L, 64);
            writeBytes(trace, 0x004F24E0L, 12);
            writeBytes(trace, 0x007B2060L, 8);
            writeBytes(trace, 0x007B2CFCL, 0x34);

            trace.write("\nKEY_REFERENCES\n");
            long[] referenceTargets = {
                0x001685B0L, 0x001685E0L,
                0x00BE50C4L, 0x00C16BD4L, 0x00C16BF4L,
                0x004EEA18L, 0x004F24E0L, 0x004F24E4L, 0x007B2CFCL
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
        File pseudoFile = new File(directory, "nfl_motion_sampler_focused_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* NFL 2K5 SMCD runtime sampler focused pseudo-C. */\n\n");
            for (long value : missingFunctions) {
                pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                    "; Ghidra has no saved function boundary; exact instructions are " +
                    "retained in nfl_motion_sampler_trace.txt.\n");
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
        println("NFL_MOTION_SAMPLER_TRACE_COMPLETE functions=" + functions.size() +
            " missing=" + missingFunctions.size());
    }
}

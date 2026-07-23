// Emit instruction-complete NFL 2K5 player matrix-postprocess evidence.
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

public class NflPlayerPostprocessTrace extends GhidraScript {
    private static final long[] FOCUSED = {
        // Direct arithmetic/matrix helpers and their one-hop dependencies.
        0x00020B20L, 0x000210B0L, 0x00031110L,
        0x000379A0L, 0x00037A10L, 0x00037AF0L, 0x00037BA0L,
        0x000384A0L,
        0x0008D550L, 0x0008D610L, 0x0008D630L,
        0x0008D8C0L, 0x0008D9D0L,
        0x00090250L, 0x00090320L,
        0x00091A60L, 0x00091AC0L, 0x00091B70L, 0x00091C80L,
        0x00091D90L, 0x00091E70L, 0x00091F60L,
        // Target postprocessors and their wrapper.
        0x00092140L, 0x00093800L, 0x00093850L,
        // Every recovered direct function caller of either target/wrapper.
        0x0005C530L, 0x0012F670L, 0x001D2B40L, 0x001DFAA0L,
        0x0025C740L, 0x0028E360L, 0x00343220L, 0x0035B520L
    };

    private static final long[][] RAW_RANGES = {
        {0x00092140L, 0x000937F5L},
        {0x00093800L, 0x00093848L},
        {0x00093850L, 0x00093B38L},
        // Ghidra omits this recovered switch arm from 0x0012F670's body.
        {0x0012F970L, 0x0012F9BEL}
    };

    private static final long[][] DATA_RANGES = {
        // 256 fixed-angle sine/cosine interpolation pairs used by 0x000384A0.
        {0x004E53E8L, 0x004E5BE7L},
        // Rational signed-angle coefficients and clamp used by 0x000210B0/0x00090320.
        {0x004E5C4CL, 0x004E5C63L},
        {0x004E5C7CL, 0x004E5C7FL},
        // Four 0xd0-byte scalar-profile records consumed by 0x00093850.
        {0x004EF018L, 0x004EF357L},
        // 62-entry pivot-adjustment channel schedule.
        {0x004EF898L, 0x004EF8D5L},
        // Contiguous matrix/vector constants consumed by 0x00092140.
        {0x004EF8E0L, 0x004EFE5BL},
        // Isolated constants used by the two targets/helpers.
        {0x004E4180L, 0x004E4187L},
        {0x004E419CL, 0x004E419FL},
        {0x004E696CL, 0x004E696FL},
        {0x004E6D5CL, 0x004E6D5FL},
        {0x004E88E4L, 0x004E88E7L}
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

    private byte[] rawBytes(long start, int size) throws Exception {
        byte[] data = new byte[size];
        int read = currentProgram.getMemory().getBytes(address(start), data);
        if (read != size) throw new IllegalStateException("short read at " + hex(start));
        return data;
    }

    private String bytes(long start, int size) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : rawBytes(start, size)) {
            result.append(String.format("%02x", value & 0xff));
        }
        return result.toString();
    }

    private void writeInstruction(BufferedWriter output, Instruction instruction)
            throws Exception {
        Function owner = currentProgram.getFunctionManager().getFunctionContaining(
            instruction.getAddress());
        output.write(hex(instruction.getAddress().getUnsignedOffset()) + " " + instruction +
            " owner=" + functionName(owner) + " refs=" +
            String.join(";", referencesTo(instruction.getAddress())) + "\n");
    }

    private void writeFunctionInstructions(BufferedWriter output, Function function)
            throws Exception {
        Instruction instruction = currentProgram.getListing().getInstructionAt(
            function.getEntryPoint());
        while (instruction != null && function.getBody().contains(instruction.getAddress())) {
            writeInstruction(output, instruction);
            instruction = instruction.getNext();
        }
    }

    private void writeRawRange(BufferedWriter output, long start, long end) throws Exception {
        output.write("RANGE " + hex(start) + ".." + hex(end) + " bytes=" +
            bytes(start, (int)(end - start + 1)) + "\n");
        Instruction instruction = currentProgram.getListing().getInstructionAt(address(start));
        if (instruction == null) {
            instruction = currentProgram.getListing().getInstructionAfter(address(start));
        }
        while (instruction != null &&
                instruction.getAddress().getUnsignedOffset() <= end) {
            writeInstruction(output, instruction);
            instruction = instruction.getNext();
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: NflPlayerPostprocessTrace.java OUTPUT_DIRECTORY");
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
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_player_postprocess_trace.txt")))) {
            trace.write("NFL 2K5 player matrix postprocess focused trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n\n");
            trace.write("FOCUSED_FUNCTION_REFERENCES\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(
                    address(value));
                trace.write(hex(value) + " " + functionName(function) + " refs=" +
                    String.join(";", referencesTo(address(value))) + "\n");
                if (function == null) {
                    throw new IllegalStateException(
                        "missing focused function boundary at " + hex(value));
                }
                functions.add(function);
            }

            trace.write("\nRAW_CONTIGUOUS_RANGES\n");
            for (long[] range : RAW_RANGES) {
                trace.write("\n");
                writeRawRange(trace, range[0], range[1]);
            }

            trace.write("\nRAW_DATA_RANGES\n");
            for (long[] range : DATA_RANGES) {
                trace.write("DATA " + hex(range[0]) + ".." + hex(range[1]) + " bytes=" +
                    bytes(range[0], (int)(range[1] - range[0] + 1)) + "\n");
            }

            trace.write("\nFOCUSED_FUNCTION_INSTRUCTIONS\n");
            for (Function function : functions) {
                trace.write("\nFUNCTION " + functionName(function) + "\n");
                writeFunctionInstructions(trace, function);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(
                new File(directory, "nfl_player_postprocess_focused_pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 player matrix postprocess focused pseudo-C. */\n\n");
            for (Function function : functions) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 300, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 300 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
            pseudo.write("// PORTME: translate every 0x00092140 call group to structured portable C while preserving its exact ordering and float32 store boundaries.\n");
            pseudo.write("// PORTME: reproduce Xbox SSE rsqrt seed behavior in 0x0008D630 if bit-identical current-matrix output is required; the portable subset uses sqrtf semantics.\n");
            pseudo.write("// PORTME: identify player-context +0x18 bits 3..4 and +0x2A from independent object-schema evidence; offsets and arithmetic are proved, labels are not.\n");
            pseudo.write("// PORTME: make the 0x00091D90/0x00091E70/0x00091F60 scratch workspace reentrant instead of copying the original globals at 0x00B65110..0x00B6526F.\n");
            pseudo.write("// PORTME: keep player animation export disabled until 0x00092140 is value-equivalently implemented and validated with runtime captures.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("NFL_PLAYER_POSTPROCESS_TRACE_COMPLETE functions=" + functions.size());
    }
}

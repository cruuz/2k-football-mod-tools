// Read-only trace for APF 2K8's shipped but apparently orphaned Sound Test state.
// @category VisualConcepts.APF.CutContent

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
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfAudioTestRemnantTrace extends GhidraScript {
    private static final String EXPECTED_MD5 = "217eea6084c3d03f0f1143802b1f5636";
    private static final long OPTIONS_DESCRIPTOR = 0x820F4578L;
    private static final long SOUND_TEST_DESCRIPTOR = 0x82006870L;
    private static final long[] FOCUSED = {
        0x846A0528L,
        0x846A05C0L,
        0x846A0B48L,
    };
    private static final long[] EVIDENCE = {
        OPTIONS_DESCRIPTOR,
        0x84E57D80L,
        SOUND_TEST_DESCRIPTOR,
        0x82006850L,
        0x845064E8L,
        0x84506500L,
        0x8450651CL,
        0x84D23228L,
        0x846F2590L,
        0x846A0528L,
        0x846A05C0L,
        0x846A0B48L,
    };
    private static final long[][] TRANSIENT_RANGES = {
        {0x846A05C0L, 0x846A0810L},
        {0x846A0B48L, 0x846A1028L},
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

    private long u32(long value) throws Exception {
        return Integer.toUnsignedLong(currentProgram.getMemory().getInt(address(value)));
    }

    private String utf16be(long value, int maximum) throws Exception {
        if (value == 0 || !currentProgram.getMemory().contains(address(value))) return "";
        Memory memory = currentProgram.getMemory();
        StringBuilder result = new StringBuilder();
        for (int index = 0; index < maximum; index++) {
            Address cursor = address(value + index * 2L);
            int code = ((memory.getByte(cursor) & 0xff) << 8) |
                (memory.getByte(cursor.add(1)) & 0xff);
            if (code == 0) return result.toString();
            if (code >= 0x20 && code < 0x7f) result.append((char)code);
            else result.append(String.format("\\u%04X", code));
        }
        return result.toString();
    }

    private String owner(Address value) {
        Function function = currentProgram.getFunctionManager().getFunctionContaining(value);
        if (function == null) return "none";
        return hex(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<String> referencesTo(long value) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager()
            .getReferencesTo(address(value));
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            result.add(hex(reference.getFromAddress()) + "(" +
                owner(reference.getFromAddress()) + "," +
                reference.getReferenceType() + "," + reference.getSource() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private void writeFunction(BufferedWriter output, Function function) throws Exception {
        output.write("FUNCTION " + hex(function.getEntryPoint()) + ":" +
            function.getName() + " body=" + function.getBody() + "\n");
        InstructionIterator iterator = currentProgram.getListing()
            .getInstructions(function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            List<String> outgoing = new ArrayList<>();
            for (Reference reference : instruction.getReferencesFrom()) {
                outgoing.add(reference.getReferenceType() + ":" +
                    hex(reference.getToAddress()));
            }
            output.write(hex(instruction.getAddress()) + " " + instruction +
                " outgoing=" + String.join(";", outgoing) + "\n");
        }
        output.write("\n");
    }

    private void writeRange(BufferedWriter output, long first, long afterLast)
            throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(afterLast - 4) + "\n");
        long value = first;
        while (value < afterLast) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                // Transient listing-only disassembly; -readOnly discards it.
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                output.write(hex(value) + " undecoded_word=" +
                    hex(u32(value)) + "\n");
                value += 4;
                continue;
            }
            List<String> outgoing = new ArrayList<>();
            for (Reference reference : instruction.getReferencesFrom()) {
                outgoing.add(reference.getReferenceType() + ":" +
                    hex(reference.getToAddress()));
            }
            output.write(hex(instruction.getAddress()) + " " + instruction +
                " owner=" + owner(instruction.getAddress()) +
                " outgoing=" + String.join(";", outgoing) + "\n");
            value = instruction.getMaxAddress().getUnsignedOffset() + 1;
        }
        output.write("\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfAudioTestRemnantTrace.java OUTPUT_DIRECTORY");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected APF executable MD5 " +
                currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        Set<Function> functions = new LinkedHashSet<>();
        File traceFile = new File(directory, "apf_audio_test_remnant_trace.txt");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(traceFile))) {
            output.write("APF 2K8 Sound Test remnant trace\n");
            output.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            output.write("Saved project opened read-only.\n\n");

            output.write("OPTIONS_DESCRIPTOR\n");
            output.write("address=" + hex(OPTIONS_DESCRIPTOR) +
                " title=" + utf16be(u32(OPTIONS_DESCRIPTOR), 96) +
                " rows=" + hex(u32(OPTIONS_DESCRIPTOR + 0x1c)) +
                " count=" + u32(OPTIONS_DESCRIPTOR + 0x3c) + "\n");
            long rowBase = u32(OPTIONS_DESCRIPTOR + 0x1c);
            long rowCount = u32(OPTIONS_DESCRIPTOR + 0x3c);
            for (int index = 0; index < rowCount; index++) {
                long row = rowBase + index * 0x60L;
                long target = u32(row + 8);
                output.write("row=" + index + " address=" + hex(row) +
                    " type=" + u32(row) + " label=" + utf16be(u32(row + 4), 96) +
                    " target=" + hex(target) + " target_title=" +
                    (target == 0 ? "" : utf16be(u32(target), 96)) + "\n");
            }

            output.write("\nSOUND_TEST_DESCRIPTOR\n");
            output.write("address=" + hex(SOUND_TEST_DESCRIPTOR) +
                " title=" + utf16be(u32(SOUND_TEST_DESCRIPTOR), 96) +
                " transition=" + utf16be(u32(SOUND_TEST_DESCRIPTOR + 4), 96) +
                " event_table=" + hex(u32(SOUND_TEST_DESCRIPTOR + 8)) +
                " default_callback=" + hex(u32(SOUND_TEST_DESCRIPTOR + 0x0c)) +
                " layout=" + utf16be(u32(SOUND_TEST_DESCRIPTOR + 0x2c), 96) +
                " context=" + hex(u32(SOUND_TEST_DESCRIPTOR + 0x34)) + "\n");
            long eventTable = u32(SOUND_TEST_DESCRIPTOR + 8);
            for (int index = 0; index < 16; index++) {
                long event = u32(eventTable + index * 8L);
                long action = u32(eventTable + index * 8L + 4);
                output.write("event=" + event + " action=" + hex(action));
                if (event != 0 && action != 0) {
                    output.write(" type=" + u32(action) +
                        " callback_04=" + hex(u32(action + 4)));
                }
                output.write("\n");
                if (event == 0) break;
            }

            output.write("\nSAVED_ANALYSIS_REFERENCES\n");
            output.write("Zero counts here are not absence proof: the saved APF project " +
                "does not materialize all data/TOC references. The deterministic PE scan " +
                "is authoritative for exact absolute-pointer counts.\n");
            for (long value : EVIDENCE) {
                List<String> references = referencesTo(value);
                output.write(hex(value) + " refs=" + references.size() + " " +
                    String.join(";", references) + "\n");
            }

            output.write("\nFOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED) {
                Function function = currentProgram.getFunctionManager()
                    .getFunctionAt(address(value));
                if (function == null) {
                    output.write(hex(value) + " missing_saved_boundary\n");
                }
                else {
                    functions.add(function);
                    writeFunction(output, function);
                }
            }
            output.write("TRANSIENT_EXACT_RANGES\n");
            for (long[] range : TRANSIENT_RANGES) {
                writeRange(output, range[0], range[1]);
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory, "apf_audio_test_remnant_pseudo_c.c");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(pseudoFile))) {
            output.write("/* APF 2K8 Sound Test remnant pseudo-C. */\n\n");
            List<Function> ordered = new ArrayList<>(functions);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));
            for (Function function : ordered) {
                output.write("/* " + hex(function.getEntryPoint()) + ":" +
                    function.getName() + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 180, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 180 seconds" :
                        result.getErrorMessage();
                    output.write("// PORTME: could not decompile function at " +
                        hex(function.getEntryPoint()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                output.write("\n\n");
            }
            output.write("// PORTME: no runtime route or rendered Sound Test screen is claimed.\n");
            output.write("// PORTME: Ghidra's saved boundaries at 0x846A05C0 and " +
                "0x846A0B48 stop after save-helper prologues; use the exact transient " +
                "ranges/static-recompiler output until those boundaries are repaired.\n");
        }
        finally {
            decompiler.dispose();
        }
        println("APF_AUDIO_TEST_REMNANT_TRACE_COMPLETE functions=" + functions.size());
    }
}

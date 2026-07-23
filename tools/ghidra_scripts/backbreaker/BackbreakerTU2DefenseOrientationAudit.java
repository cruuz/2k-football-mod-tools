// Recovered Backbreaker Ghidra script.
//
// This source was reconstructed by CFR-decompiling the compiled .class
// artifact left in the Ghidra OSGi bundle cache; the original .java was not
// retained. Decompiler artifacts have been corrected and the script compiles
// cleanly against the vendored Ghidra 12.1.2 API plus the XEXLoaderWV
// extension (javac --release 21, zero errors). Run it only against a
// Backbreaker XEX whose MD5 matches EXPECTED_MD5 below.

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.LinkedHashSet;
import java.util.Set;

public class BackbreakerTU2DefenseOrientationAudit
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";
    private static final Range[] RANGES = new Range[]{new Range(2183175288L, 2183175996L, "shared_camera_activation_and_subject_binding"), new Range(2184678096L, 2184682368L, "ready_registration_constructor_activation_update"), new Range(2183490944L, 2183493184L, "cornerback_constructor_activation_update"), new Range(2185279360L, 2185283520L, "zoning_helpers_constructor_activation_update"), new Range(2183176000L, 2183176480L, "shared_camera_subject_and_derived_state"), new Range(2183178936L, 2183179692L, "shared_camera_target_activation_dispatch"), new Range(2184414272L, 2184414352L, "ready_context_to_team_axis_object"), new Range(2185266384L, 2185266720L, "ready_selector_helper")};
    private static final long[] SEEDS = new long[]{2184678096L, 2184678200L, 2184679216L, 2184679760L, 2184679840L, 2184680880L, 2183491024L, 2183491344L, 2183491424L, 2183491752L, 2185279368L, 2185279632L, 2185279968L, 2185280928L, 2185281008L, 2185281792L, 2183175416L, 2183176000L, 2183176208L, 2183178936L, 2185266464L, 2184414280L};

    private Address address(long value) {
        return this.currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xFFFFFFFFL);
    }

    private String bytes(Address start, int count) throws Exception {
        byte[] data = new byte[count];
        int read = this.currentProgram.getMemory().getBytes(start, data);
        if (read != count) {
            throw new IllegalStateException("short read at " + String.valueOf(start));
        }
        StringBuilder output = new StringBuilder();
        for (byte item : data) {
            output.append(String.format("%02X", item & 0xFF));
        }
        return output.toString();
    }

    private Function owner(long value) {
        return this.currentProgram.getFunctionManager().getFunctionContaining(this.address(value));
    }

    private void writeRange(BufferedWriter output, Range range) throws Exception {
        output.write("RANGE " + range.label + " " + this.hex(range.first) + ".." + this.hex(range.last) + "\n");
        for (long value = range.first; value <= range.last; value += 4L) {
            Address cursor = this.address(value);
            Instruction instruction = this.currentProgram.getListing().getInstructionAt(cursor);
            String rendered = instruction == null ? "<UNDEFINED_XENON_WORD>" : instruction.toString().replace('\t', ' ');
            StringBuilder refs = new StringBuilder();
            if (instruction != null) {
                for (Reference reference : instruction.getReferencesFrom()) {
                    refs.append(refs.length() == 0 ? " refs=" : ";");
                    refs.append(reference.getReferenceType()).append("->").append(reference.getToAddress());
                }
            }
            output.write(this.hex(value) + " " + this.bytes(cursor, 4) + " " + rendered + String.valueOf(refs) + "\n");
        }
        output.write("\n");
    }

    private Set<Function> seedFunctions() {
        LinkedHashSet<Function> functions = new LinkedHashSet<Function>();
        for (long seed : SEEDS) {
            Function function = this.owner(seed);
            if (function == null) continue;
            functions.add(function);
        }
        return functions;
    }

    /*
     * WARNING - Removed try catching itself - possible behaviour change.
     */
    private void writeFunctions(BufferedWriter output, Set<Function> functions) throws Exception {
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(this.currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try {
            for (Function function : functions) {
                output.write("/* " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 180, this.monitor);
                output.write("/* completed=" + result.decompileCompleted() + " timed_out=" + result.isTimedOut() + " error=" + result.getErrorMessage().replace('\n', ' ') + " */\n");
                if (result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                } else {
                    output.write("// No pseudo-C produced.\n");
                }
                output.write("\n\n");
            }
        }
        finally {
            decompiler.dispose();
        }
    }

    protected void run() throws Exception {
        String[] args = this.getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: BackbreakerTU2DefenseOrientationAudit.java OUTPUT_DIRECTORY");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected TU2 XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(directory));
        }
        Set<Function> functions = this.seedFunctions();
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_defense_orientation_assembly.txt")))) {
            output.write("Backbreaker TU2 defense-orientation bounded assembly\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n");
            output.write("script_mode=read_only_no_database_edits\n\n");
            for (Range range : RANGES) {
                this.writeRange(output, range);
            }
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_defense_orientation_pseudo_c.c")))) {
            output.write("/* Backbreaker TU2 defense-orientation bounded pseudo-C. */\n\n");
            this.writeFunctions(output, functions);
        }
        this.println("BACKBREAKER_TU2_DEFENSE_ORIENTATION_AUDIT_COMPLETE output=" + String.valueOf(directory));
    }

    private static final class Range {
        final long first;
        final long last;
        final String label;

        Range(long first, long last, String label) {
            this.first = first;
            this.last = last;
            this.label = label;
        }
    }
}


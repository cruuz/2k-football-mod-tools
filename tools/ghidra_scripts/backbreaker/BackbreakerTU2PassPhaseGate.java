// Recovered Backbreaker Ghidra script.
//
// This source was reconstructed by CFR-decompiling the compiled .class
// artifact left in the Ghidra OSGi bundle cache; the original .java was not
// retained. Decompiler artifacts have been corrected and the script compiles
// cleanly against the vendored Ghidra 12.1.2 API plus the XEXLoaderWV
// extension (javac --release 21, zero errors). Run it only against a
// Backbreaker XEX whose MD5 matches EXPECTED_MD5 below.

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;

public class BackbreakerTU2PassPhaseGate
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";

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

    private void dumpRange(BufferedWriter output, long first, long last, String label) throws Exception {
        output.write("RANGE " + label + " " + this.hex(first) + ".." + this.hex(last) + "\n");
        for (long value = first; value <= last; value += 4L) {
            Address at = this.address(value);
            Instruction instruction = this.currentProgram.getListing().getInstructionAt(at);
            Function owner = this.currentProgram.getFunctionManager().getFunctionContaining(at);
            output.write(this.hex(value) + " " + this.bytes(at, 4) + " " + (instruction == null ? "<UNDEFINED_XENON_WORD>" : instruction.toString().replace('\t', ' ')) + " owner=" + (String)(owner == null ? "none" : owner.getName() + "@" + this.hex(owner.getEntryPoint().getUnsignedOffset())) + "\n");
        }
        output.write("\n");
    }

    protected void run() throws Exception {
        String[] args = this.getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: BackbreakerTU2PassPhaseGate.java OUTPUT_DIRECTORY");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected TU2 XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(directory));
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_pass_phase_gate_assembly.txt")))) {
            output.write("Backbreaker TU2 Pass-camera phase-gate assembly\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n\n");
            output.write("FUNCTION_BOUNDARIES\n");
            FunctionIterator functions = this.currentProgram.getFunctionManager().getFunctions(this.address(2184302080L), true);
            for (int index = 0; index < 16 && functions.hasNext(); ++index) {
                Function function = (Function)functions.next();
                output.write(function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + "\n");
            }
            output.write("\n");
            this.dumpRange(output, 2184302152L, 2184303540L, "pass_ctor_and_activation");
            this.dumpRange(output, 2184303544L, 2184305664L, "pass_update_and_tail");
        }
        this.println("BACKBREAKER_TU2_PASS_PHASE_GATE_COMPLETE output=" + String.valueOf(directory));
    }
}


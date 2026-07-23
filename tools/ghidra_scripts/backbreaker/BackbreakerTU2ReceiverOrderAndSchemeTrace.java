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
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;

public class BackbreakerTU2ReceiverOrderAndSchemeTrace
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";

    private Address address(long value) {
        return this.currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xFFFFFFFFL);
    }

    private long word(long value) throws Exception {
        return Integer.toUnsignedLong(this.currentProgram.getMemory().getInt(this.address(value)));
    }

    private Function owner(long value) {
        return this.currentProgram.getFunctionManager().getFunctionContaining(this.address(value));
    }

    private String ownerText(long value) {
        Function function = this.owner(value);
        return function == null ? "no_function" : function.getName() + "@" + String.valueOf(function.getEntryPoint());
    }

    private long branchTarget(long source, long instruction) {
        int displacement = (int)(instruction & 0x3FFFFFCL);
        if ((displacement & 0x2000000) != 0) {
            displacement |= 0xFC000000;
        }
        if ((instruction & 2L) != 0L) {
            return Integer.toUnsignedLong(displacement);
        }
        return source + (long)displacement & 0xFFFFFFFFL;
    }

    private void writeTargetAudit(BufferedWriter output, long target) throws Exception {
        output.write("TARGET " + this.hex(target) + " owner=" + this.ownerText(target) + "\n");
        ReferenceIterator references = this.currentProgram.getReferenceManager().getReferencesTo(this.address(target));
        int referenceCount = 0;
        while (references.hasNext()) {
            Reference reference = references.next();
            long source = reference.getFromAddress().getUnsignedOffset();
            output.write("  ghidra_ref=" + this.hex(source) + " type=" + String.valueOf(reference.getReferenceType()) + " owner=" + this.ownerText(source) + "\n");
            ++referenceCount;
        }
        int branchCount = 0;
        int pointerCount = 0;
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            long first = block.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = block.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            for (long source = first; source <= last; source += 4L) {
                long candidate;
                try {
                    candidate = this.word(source);
                }
                catch (Exception exception) {
                    continue;
                }
                if (candidate == target) {
                    output.write("  aligned_pointer=" + this.hex(source) + " block=" + block.getName() + " executable=" + block.isExecute() + "\n");
                    ++pointerCount;
                }
                if (candidate >>> 26 != 18L || this.branchTarget(source, candidate) != target) continue;
                output.write("  direct_branch=" + this.hex(source) + " word=" + this.hex(candidate) + " lk=" + (candidate & 1L) + " owner=" + this.ownerText(source) + "\n");
                ++branchCount;
            }
        }
        output.write("  reference_count=" + referenceCount + " branch_count=" + branchCount + " pointer_count=" + pointerCount + "\n\n");
    }

    private void writeFieldAudit(BufferedWriter output, int displacement) throws Exception {
        output.write("D_FORM_FIELD displacement=+" + String.format("0x%03X", displacement) + "\n");
        int count = 0;
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            if (!block.isExecute()) continue;
            long first = block.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = block.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            for (long source = first; source <= last; source += 4L) {
                long candidate;
                try {
                    candidate = this.word(source);
                }
                catch (Exception exception) {
                    continue;
                }
                int opcode = (int)(candidate >>> 26);
                if ((candidate & 0xFFFFL) != (long)displacement || opcode != 32 && opcode != 34 && opcode != 36 && opcode != 38 && opcode != 48 && opcode != 50 && opcode != 52 && opcode != 54) continue;
                Instruction instruction = this.currentProgram.getListing().getInstructionAt(this.address(source));
                output.write("  at=" + this.hex(source) + " word=" + this.hex(candidate) + " instruction=" + (instruction == null ? "<none>" : instruction.toString()) + " owner=" + this.ownerText(source) + "\n");
                ++count;
            }
        }
        output.write("  count=" + count + "\n\n");
    }

    /*
     * WARNING - Removed try catching itself - possible behaviour change.
     */
    private void writeFunction(BufferedWriter output, long seed) throws Exception {
        Function function = this.owner(seed);
        if (function == null) {
            output.write("FUNCTION seed=" + this.hex(seed) + " <missing>\n\n");
            return;
        }
        output.write("FUNCTION seed=" + this.hex(seed) + " " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + "\n");
        for (Instruction instruction = this.currentProgram.getListing().getInstructionAt(function.getEntryPoint()); instruction != null && function.getBody().contains(instruction.getAddress()); instruction = instruction.getNext()) {
            output.write("  " + String.valueOf(instruction.getAddress()) + " " + instruction.toString() + "\n");
        }
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(this.currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try {
            DecompileResults result = decompiler.decompileFunction(function, 300, this.monitor);
            output.write("DECOMPILE completed=" + result.decompileCompleted() + " error=" + result.getErrorMessage().replace('\n', ' ') + "\n");
            if (result.getDecompiledFunction() != null) {
                output.write(result.getDecompiledFunction().getC());
            }
        }
        finally {
            decompiler.dispose();
        }
        output.write("\n\n");
    }

    protected void run() throws Exception {
        String[] args = this.getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: BackbreakerTU2ReceiverOrderAndSchemeTrace.java OUTPUT_FILE");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected TU2 MD5 " + this.currentProgram.getExecutableMD5());
        }
        File outputFile = new File(args[0]);
        File parent = outputFile.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(parent));
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(outputFile));){
            output.write("Backbreaker TU2 receiver-order and scheme trace\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n");
            output.write("script_mode=read_only_no_database_edits\n\n");
            this.writeTargetAudit(output, 2184614784L);
            this.writeTargetAudit(output, 2184623328L);
            this.writeTargetAudit(output, 2184573504L);
            this.writeTargetAudit(output, 2187705224L);
            this.writeTargetAudit(output, 2183593200L);
            this.writeTargetAudit(output, 2183475856L);
            this.writeFieldAudit(output, 1264);
            this.writeFieldAudit(output, 1268);
            this.writeFieldAudit(output, 1344);
            this.writeFieldAudit(output, 1348);
            this.writeFieldAudit(output, 1360);
            this.writeFieldAudit(output, 1424);
            this.writeFunction(output, 2184623844L);
            this.writeFunction(output, 2184466692L);
            this.writeFunction(output, 2184475024L);
            this.writeFunction(output, 2184614784L);
            this.writeFunction(output, 2184573504L);
            this.writeFunction(output, 2184486624L);
            this.writeFunction(output, 2183475856L);
            this.writeFunction(output, 2183593200L);
            this.writeFunction(output, 2182764832L);
        }
        this.println("BACKBREAKER_TU2_RECEIVER_ORDER_SCHEME_TRACE_COMPLETE output=" + String.valueOf(outputFile));
    }
}


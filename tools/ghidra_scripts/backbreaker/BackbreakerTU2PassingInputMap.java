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

public class BackbreakerTU2PassingInputMap
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";
    private static final long[] CALLBACKS = new long[]{2183430856L, 2183430960L, 2183431064L, 2183431168L, 2183431272L, 2183431288L, 2183431312L, 2183431336L, 2183431360L, 2183431384L, 2183431400L, 2183431416L, 2183431432L, 2183431448L, 2183431464L, 2183431480L, 2183431496L, 2183431512L, 2183431528L, 2183431544L, 2183431560L, 2183431576L};

    private Address address(long value) {
        return this.currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xFFFFFFFFL);
    }

    private long word(long value) throws Exception {
        return Integer.toUnsignedLong(this.currentProgram.getMemory().getInt(this.address(value)));
    }

    private Function owner(Address source) {
        return this.currentProgram.getFunctionManager().getFunctionContaining(source);
    }

    private String ownerText(Address source) {
        Function function = this.owner(source);
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

    private void writeReferences(BufferedWriter output, long target) throws Exception {
        Address destination = this.address(target);
        output.write("TARGET " + this.hex(target) + "\n");
        ReferenceIterator references = this.currentProgram.getReferenceManager().getReferencesTo(destination);
        int count = 0;
        while (references.hasNext()) {
            Reference reference = references.next();
            output.write("  reference from=" + String.valueOf(reference.getFromAddress()) + " type=" + String.valueOf(reference.getReferenceType()) + " owner=" + this.ownerText(reference.getFromAddress()) + "\n");
            ++count;
        }
        output.write("  reference_count=" + count + "\n");
        int directBranches = 0;
        int alignedPointers = 0;
        int relativeWords = 0;
        int materializations = 0;
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            long first = block.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = block.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            for (long source = first; source <= last; source += 4L) {
                long signed;
                long relative;
                long candidate;
                try {
                    candidate = this.word(source);
                }
                catch (Exception exception) {
                    continue;
                }
                if (candidate == target) {
                    output.write("  aligned_pointer=" + this.hex(source) + " block=" + block.getName() + " executable=" + block.isExecute() + "\n");
                    ++alignedPointers;
                }
                if (candidate >>> 26 == 18L && this.branchTarget(source, candidate) == target) {
                    output.write("  direct_branch=" + this.hex(source) + " word=" + this.hex(candidate) + " lk=" + (candidate & 1L) + " owner=" + this.ownerText(this.address(source)) + "\n");
                    ++directBranches;
                }
                if (candidate >>> 26 == 15L && (candidate >>> 16 & 0x1FL) == 0L) {
                    int register = (int)(candidate >>> 21 & 0x1FL);
                    short high = (short)(candidate & 0xFFFFL);
                    for (int step = 1; step <= 8 && source + (long)step * 4L <= last; ++step) {
                        long second = this.word(source + (long)step * 4L);
                        int opcode = (int)(second >>> 26);
                        int rt = (int)(second >>> 21 & 0x1FL);
                        int ra = (int)(second >>> 16 & 0x1FL);
                        long formed = -1L;
                        if (opcode == 14 && rt == register && ra == register) {
                            formed = ((long)high << 16) + (long)((short)(second & 0xFFFFL)) & 0xFFFFFFFFL;
                        } else if (opcode == 24 && rt == register && ra == register) {
                            formed = ((long)high << 16 | second & 0xFFFFL) & 0xFFFFFFFFL;
                        }
                        if (formed != target) continue;
                        output.write("  materialization=" + this.hex(source) + " second=" + this.hex(source + (long)step * 4L) + " owner=" + this.ownerText(this.address(source)) + "\n");
                        ++materializations;
                    }
                }
                if ((relative = source + (signed = (long)((int)candidate)) & 0xFFFFFFFFL) != target) continue;
                output.write("  relative_word=" + this.hex(source) + " word=" + this.hex(candidate) + " block=" + block.getName() + "\n");
                ++relativeWords;
            }
        }
        output.write("  direct_branch_count=" + directBranches + " aligned_pointer_count=" + alignedPointers + " relative_word_count=" + relativeWords + " materialization_count=" + materializations + "\n\n");
    }

    private void writeWindow(BufferedWriter output, long start, int words) throws Exception {
        output.write("WINDOW " + this.hex(start) + " words=" + words + "\n");
        for (int index = 0; index < words; ++index) {
            long value = start + (long)index * 4L;
            Instruction instruction = this.currentProgram.getListing().getInstructionAt(this.address(value));
            output.write("  " + this.hex(value) + " " + this.hex(this.word(value)) + " " + (instruction == null ? "<no_instruction>" : instruction.toString()) + "\n");
        }
        output.write("\n");
    }

    private void writeInputDescriptors(BufferedWriter output) throws Exception {
        String[] labels = new String[]{"DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT", "A", "B", "X", "Y", "START", "BACK", "LEFT_THUMB", "RIGHT_THUMB", "LEFT_SHOULDER", "RIGHT_SHOULDER"};
        long table = 2181573680L;
        output.write("INPUT_DESCRIPTOR_TABLE base=" + this.hex(table) + " record_bytes=12 records=28 layout={id,type,mask}\n");
        for (int index = 0; index < 28; ++index) {
            long record = table + (long)index * 12L;
            long id = this.word(record);
            long type = this.word(record + 4L);
            long mask = this.word(record + 8L);
            String label = index < labels.length ? labels[index] : "NON_DIGITAL_AXIS";
            output.write("  record=" + this.hex(record) + " id=" + id + " type=" + type + " mask=" + this.hex(mask) + " label=" + label + "\n");
        }
        output.write("\n");
    }

    /*
     * WARNING - Removed try catching itself - possible behaviour change.
     */
    private void writeFunction(BufferedWriter output, long entry) throws Exception {
        Function function = this.currentProgram.getFunctionManager().getFunctionAt(this.address(entry));
        if (function == null) {
            output.write("FUNCTION " + this.hex(entry) + " <missing>\n\n");
            return;
        }
        output.write("FUNCTION " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + "\n");
        for (Instruction instruction = this.currentProgram.getListing().getInstructionAt(function.getEntryPoint()); instruction != null && function.getBody().contains(instruction.getAddress()); instruction = instruction.getNext()) {
            output.write("  " + String.valueOf(instruction.getAddress()) + " " + instruction.toString() + "\n");
        }
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(this.currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try {
            DecompileResults result = decompiler.decompileFunction(function, 180, this.monitor);
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
            throw new IllegalArgumentException("usage: BackbreakerTU2PassingInputMap.java OUTPUT_FILE");
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
            output.write("Backbreaker TU2 passing input-map trace\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n");
            output.write("script_mode=read_only_no_database_edits\n\n");
            this.writeInputDescriptors(output);
            for (long callback : CALLBACKS) {
                this.writeReferences(output, callback);
            }
            this.writeWindow(output, 2183430840L, 188);
            this.writeFunction(output, 2183442152L);
            this.writeFunction(output, 2187549136L);
            this.writeFunction(output, 2187548336L);
            this.writeFunction(output, 2187548608L);
            this.writeFunction(output, 2187553608L);
            this.writeFunction(output, 2187551592L);
            this.writeFunction(output, 2187552960L);
            this.writeFunction(output, 2187553920L);
            this.writeFunction(output, 2187553856L);
        }
        this.println("BACKBREAKER_TU2_PASSING_INPUT_MAP_COMPLETE output=" + String.valueOf(outputFile));
    }
}


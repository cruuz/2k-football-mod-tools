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
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class BackbreakerTU2PassingFeasibility
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";
    private static final Range[] RAW_RANGES = new Range[]{new Range(2183430784L, 2183431456L, "controller_face_button_edge_and_hold_updates"), new Range(2183476208L, 2183476384L, "controller_scheme_store_unowned"), new Range(2184013824L, 2184014864L, "game_controller_camera_catalog_initializers"), new Range(2184579808L, 2184580000L, "receiver_cycle_helpers"), new Range(2184680880L, 2184682016L, "ready_camera_update_body")};
    private static final Probe[] STRING_PROBES = new Probe[]{new Probe(2183430856L, "face-button channel 0 hold callback"), new Probe(2183430960L, "face-button channel 2 hold callback"), new Probe(2183431064L, "face-button channel 1 hold callback"), new Probe(2183431168L, "face-button channel 3 hold callback"), new Probe(2183431288L, "face-button channel 3 release callback"), new Probe(2183431312L, "face-button channel 2 release callback"), new Probe(2183431336L, "face-button channel 0 release callback"), new Probe(2183431360L, "face-button channel 1 release callback"), new Probe(2183431384L, "receiver cycle negative input callback"), new Probe(2183431400L, "receiver cycle positive input callback"), new Probe(2191331340L, "controller scheme enum pointer table base"), new Probe(2191331344L, "GESTURES enum pointer entry"), new Probe(2191331348L, "FACE_BUTTONS enum pointer entry"), new Probe(2181274124L, "Backbreaker Default (Lazy)"), new Probe(2181274252L, "Focus on Receiver (Left Trigger)"), new Probe(2181274288L, "Select Receiver (Right Stick Left/Right)"), new Probe(2181184768L, "Switch Throw Target"), new Probe(2181259488L, "FACE_BUTTONS controller scheme enum"), new Probe(2181259504L, "GESTURES controller scheme enum"), new Probe(2181223508L, "THROW_BULLET action enum"), new Probe(2181223524L, "THROW_BOMB action enum"), new Probe(2181193788L, "IDEAL TARGET HIGHLIGHTING debug toggle"), new Probe(2181193904L, "RECEIVER READY FLASH debug toggle"), new Probe(2181193956L, "DRAW TARGETS debug toggle"), new Probe(2181195312L, "QB FREE STICKY TARGET debug toggle"), new Probe(2181257876L, "RECEIVER_HIGHLIGHTING state name"), new Probe(2181266464L, "WIDE_RECEIVER_5 role"), new Probe(2181266480L, "WIDE_RECEIVER_4 role"), new Probe(2181266496L, "WIDE_RECEIVER_3 role"), new Probe(2181266512L, "WIDE_RECEIVER_2 role"), new Probe(2181266528L, "WIDE_RECEIVER_1 role"), new Probe(2181287944L, "OKtoPass receiver-choice diagnostic"), new Probe(2181288040L, "Receiver In Position diagnostic"), new Probe(2181156076L, "Ball::CalculateThrowPath"), new Probe(2181342492L, "kPacketMessage_Game_ControllerScheme")};
    private static final long[] CODE_PROBES = new long[]{2190843252L, 2183146160L, 2183897464L, 2183897824L, 2184486624L, 2183457968L, 2182764832L, 2183593200L, 2184480560L, 2185300816L, 2183430856L, 2183432096L, 2183441032L, 2184573416L, 2184579840L, 2184579920L, 2184970560L, 2184680880L, 2183351608L, 2183352712L, 2183158104L, 2183158480L, 2184303080L, 2184303544L, 2183159176L, 2183159640L, 2185279368L, 2185279632L, 2183378272L};

    private Address address(long value) {
        return this.currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xFFFFFFFFL);
    }

    private long word(long value) throws Exception {
        return Integer.toUnsignedLong(this.currentProgram.getMemory().getInt(this.address(value)));
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

    private long directBranchTarget(long from, long instruction) {
        int displacement = (int)(instruction & 0x3FFFFFCL);
        if ((displacement & 0x2000000) != 0) {
            displacement |= 0xFC000000;
        }
        if ((instruction & 2L) != 0L) {
            return Integer.toUnsignedLong(displacement);
        }
        return from + (long)displacement & 0xFFFFFFFFL;
    }

    private Function owner(long source) {
        return this.currentProgram.getFunctionManager().getFunctionContaining(this.address(source));
    }

    private String ownerText(long source) {
        Function function = this.owner(source);
        return function == null ? "no_function" : function.getName() + "@" + this.hex(function.getEntryPoint().getUnsignedOffset());
    }

    private List<Long> materializations(long target) throws Exception {
        ArrayList<Long> found = new ArrayList<Long>();
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            if (!block.isExecute()) continue;
            long first = block.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = block.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            long source = first;
            while (source + 24L <= last) {
                block9: {
                    long firstWord;
                    try {
                        firstWord = this.word(source);
                    }
                    catch (Exception exception) {
                        break block9;
                    }
                    if (firstWord >>> 26 == 15L && (firstWord >>> 16 & 0x1FL) == 0L) {
                        int baseRegister = (int)(firstWord >>> 21 & 0x1FL);
                        short high = (short)(firstWord & 0xFFFFL);
                        for (int step = 1; step <= 6; ++step) {
                            long secondAddress = source + (long)step * 4L;
                            long secondWord = this.word(secondAddress);
                            int opcode = (int)(secondWord >>> 26);
                            int firstRegister = (int)(secondWord >>> 21 & 0x1FL);
                            int secondRegister = (int)(secondWord >>> 16 & 0x1FL);
                            long formed = -1L;
                            if (opcode == 14 && secondRegister == baseRegister) {
                                formed = ((long)high << 16) + (long)((short)(secondWord & 0xFFFFL)) & 0xFFFFFFFFL;
                            } else if (opcode == 24 && firstRegister == baseRegister) {
                                formed = ((long)high << 16 | secondWord & 0xFFFFL) & 0xFFFFFFFFL;
                            }
                            if (formed != target) continue;
                            found.add(source);
                        }
                    }
                }
                source += 4L;
            }
        }
        return found;
    }

    private List<Long> alignedPointers(long target) throws Exception {
        ArrayList<Long> found = new ArrayList<Long>();
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            long first = block.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = block.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            for (long source = first; source <= last; source += 4L) {
                try {
                    if (this.word(source) != target) continue;
                    found.add(source);
                    continue;
                }
                catch (Exception exception) {
                    // empty catch block
                }
            }
        }
        return found;
    }

    private List<Long> dFormAccesses(long target) throws Exception {
        ArrayList<Long> found = new ArrayList<Long>();
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            if (!block.isExecute()) continue;
            long first = block.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = block.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            long source = first;
            while (source + 48L <= last) {
                block6: {
                    long firstWord;
                    try {
                        firstWord = this.word(source);
                    }
                    catch (Exception exception) {
                        break block6;
                    }
                    if (firstWord >>> 26 == 15L && (firstWord >>> 16 & 0x1FL) == 0L) {
                        int baseRegister = (int)(firstWord >>> 21 & 0x1FL);
                        short high = (short)(firstWord & 0xFFFFL);
                        for (int step = 1; step <= 12; ++step) {
                            long formed;
                            long accessAddress = source + (long)step * 4L;
                            long accessWord = this.word(accessAddress);
                            int opcode = (int)(accessWord >>> 26);
                            int ra = (int)(accessWord >>> 16 & 0x1FL);
                            if (ra != baseRegister || opcode == 15 || (opcode < 32 || opcode > 55) && opcode != 14 || (formed = ((long)high << 16) + (long)((short)(accessWord & 0xFFFFL)) & 0xFFFFFFFFL) != target) continue;
                            found.add(accessAddress);
                        }
                    }
                }
                source += 4L;
            }
        }
        return found;
    }

    private Set<Function> seedFunctions() {
        LinkedHashSet<Function> functions = new LinkedHashSet<Function>();
        for (long probe : CODE_PROBES) {
            Function function = this.owner(probe);
            if (function == null) continue;
            functions.add(function);
        }
        return functions;
    }

    private void writeFieldAccesses(BufferedWriter output, int displacement) throws Exception {
        output.write("FIELD_ACCESSES displacement=" + String.format("0x%04X", displacement) + "\n");
        int count = 0;
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            if (!block.isExecute()) continue;
            long first = block.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = block.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            for (long source = first; source <= last; source += 4L) {
                long instruction;
                try {
                    instruction = this.word(source);
                }
                catch (Exception exception) {
                    continue;
                }
                int opcode = (int)(instruction >>> 26);
                if (opcode != 32 && opcode != 34 && opcode != 36 && opcode != 38 || (instruction & 0xFFFFL) != ((long)displacement & 0xFFFFL)) continue;
                output.write("  at=" + this.hex(source) + " word=" + this.hex(instruction) + " opcode=" + opcode + " owner=" + this.ownerText(source) + "\n");
                ++count;
            }
        }
        output.write("  count=" + count + "\n\n");
    }

    private Set<Function> callers(Set<Function> seeds) throws Exception {
        LinkedHashSet<Long> targets = new LinkedHashSet<Long>();
        for (Function function : seeds) {
            targets.add(function.getEntryPoint().getUnsignedOffset());
        }
        LinkedHashSet<Function> result = new LinkedHashSet<Function>();
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            if (!block.isExecute()) continue;
            long first = block.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = block.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            for (long source = first; source <= last; source += 4L) {
                Function function;
                long instruction;
                try {
                    instruction = this.word(source);
                }
                catch (Exception exception) {
                    continue;
                }
                if (instruction >>> 26 != 18L || (instruction & 1L) == 0L || !targets.contains(this.directBranchTarget(source, instruction)) || (function = this.owner(source)) == null) continue;
                result.add(function);
            }
        }
        return result;
    }

    private void writeFunctionAssembly(BufferedWriter output, Function function) throws Exception {
        int count;
        output.write("FUNCTION " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + "\n");
        Instruction instruction = this.currentProgram.getListing().getInstructionAt(function.getEntryPoint());
        for (count = 0; instruction != null && function.getBody().contains(instruction.getAddress()) && count < 2400; instruction = instruction.getNext(), ++count) {
            ArrayList<String> references = new ArrayList<String>();
            for (Reference reference : instruction.getReferencesFrom()) {
                references.add(String.valueOf(reference.getReferenceType()) + "->" + String.valueOf(reference.getToAddress()));
            }
            output.write("  " + String.valueOf(instruction.getAddress()) + " " + this.bytes(instruction.getAddress(), instruction.getLength()) + " " + instruction.toString().replace('\t', ' ') + (String)(references.isEmpty() ? "" : " refs=" + String.join(";", references)) + "\n");
        }
        if (count >= 2400) {
            output.write("  <TRUNCATED>\n");
        }
        output.write("\n");
    }

    private void writeRawRange(BufferedWriter output, Range range) throws Exception {
        output.write("RANGE " + range.label + " " + this.hex(range.first) + ".." + this.hex(range.last) + "\n");
        for (long value = range.first; value <= range.last; value += 4L) {
            Instruction instruction = this.currentProgram.getListing().getInstructionAt(this.address(value));
            output.write("  " + this.hex(value) + " " + this.bytes(this.address(value), 4) + " " + (instruction == null ? "<UNDEFINED_XENON_WORD>" : instruction.toString().replace('\t', ' ')) + "\n");
        }
        output.write("\n");
    }

    /*
     * WARNING - Removed try catching itself - possible behaviour change.
     */
    private void writeDecompilation(BufferedWriter output, Set<Function> functions) throws Exception {
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
            throw new IllegalArgumentException("usage: BackbreakerTU2PassingFeasibility.java OUTPUT_DIRECTORY");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected TU2 XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(directory));
        }
        Set<Function> functions = this.seedFunctions();
        functions.addAll(this.callers(functions));
        for (Probe probe : STRING_PROBES) {
            for (long source : this.materializations(probe.address)) {
                Function function = this.owner(source);
                if (function == null) continue;
                functions.add(function);
            }
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_passing_feasibility_facts.txt")))) {
            output.write("Backbreaker TU2 conventional-passing feasibility facts\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n");
            output.write("script_mode=read_only_no_database_edits\n\n");
            for (Probe probe : STRING_PROBES) {
                output.write("STRING " + probe.label + " " + this.hex(probe.address) + "\n");
                List<Long> formed = this.materializations(probe.address);
                for (long source : formed) {
                    output.write("  code_materialization=" + this.hex(source) + " owner=" + this.ownerText(source) + "\n");
                }
                List<Long> pointers = this.alignedPointers(probe.address);
                for (long source : pointers) {
                    output.write("  aligned_pointer=" + this.hex(source) + " executable_block=" + this.currentProgram.getMemory().getBlock(this.address(source)).isExecute() + "\n");
                }
                List<Long> accesses = this.dFormAccesses(probe.address);
                for (long source : accesses) {
                    output.write("  dform_access=" + this.hex(source) + " word=" + this.hex(this.word(source)) + " owner=" + this.ownerText(source) + "\n");
                }
                output.write("  materialization_count=" + formed.size() + " pointer_count=" + pointers.size() + " dform_count=" + accesses.size() + "\n\n");
            }
            output.write("FUNCTION_SEEDS_AND_CALLERS count=" + functions.size() + "\n");
            for (Function function : functions) {
                output.write("  " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + "\n");
            }
            output.write("\nCONTROLLER_SCHEME_AND_THROW_INPUT_FIELDS\n");
            this.writeFieldAccesses(output, 1424);
            this.writeFieldAccesses(output, 1664);
            this.writeFieldAccesses(output, 1668);
            this.writeFieldAccesses(output, 1344);
            this.writeFieldAccesses(output, 1348);
            this.writeFieldAccesses(output, 1360);
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_passing_feasibility_assembly.txt")))) {
            output.write("Backbreaker TU2 conventional-passing bounded assembly\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n\n");
            for (Range range : RAW_RANGES) {
                this.writeRawRange(output, range);
            }
            for (Function function : functions) {
                this.writeFunctionAssembly(output, function);
            }
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_passing_feasibility_pseudo_c.c")))) {
            output.write("/* Backbreaker TU2 conventional-passing bounded pseudo-C. */\n\n");
            this.writeDecompilation(output, functions);
        }
        this.println("BACKBREAKER_TU2_PASSING_FEASIBILITY_COMPLETE output=" + String.valueOf(directory));
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

    private static final class Probe {
        final long address;
        final String label;

        Probe(long address, String label) {
            this.address = address;
            this.label = label;
        }
    }
}


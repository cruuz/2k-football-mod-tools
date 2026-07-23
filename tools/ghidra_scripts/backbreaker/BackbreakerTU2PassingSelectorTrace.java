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
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class BackbreakerTU2PassingSelectorTrace
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";
    private static final long[] DATA_TARGETS = new long[]{2191331344L, 2191331348L, 2191338120L, 2191338124L, 2191332316L, 2191312640L, 2191312680L, 2191312780L};
    private static final long[] STRING_TARGETS = new long[]{2181184628L, 2181125152L, 2181125224L, 2181184768L, 2181274252L, 2181274288L};
    private static final int[] INPUT_FIELDS = new int[]{1424, 1656, 1657, 1660, 1661, 1662, 1664, 1666, 1668, 1670, 1673, 1675, 1677, 1683};
    private static final long[] CODE_SEEDS = new long[]{2183457968L, 2183456464L, 2183458984L, 2183459752L, 2183440520L, 2184486624L, 2184579840L, 2184579920L, 2184573416L, 2184480832L, 2183476344L, 2183593300L, 2184013892L, 2184014568L, 2184014768L};

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

    private String cString(long value, int cap) {
        StringBuilder result = new StringBuilder();
        try {
            int item;
            for (int index = 0; index < cap && (item = this.currentProgram.getMemory().getByte(this.address(value + (long)index)) & 0xFF) != 0; ++index) {
                if (item < 32 || item > 126) {
                    return "";
                }
                result.append((char)item);
            }
        }
        catch (Exception exception) {
            return "";
        }
        return result.toString();
    }

    private Function owner(long source) {
        return this.currentProgram.getFunctionManager().getFunctionContaining(this.address(source));
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
                            long second = this.word(source + (long)step * 4L);
                            int opcode = (int)(second >>> 26);
                            int rt = (int)(second >>> 21 & 0x1FL);
                            int ra = (int)(second >>> 16 & 0x1FL);
                            long formed = -1L;
                            if (opcode == 14 && ra == baseRegister) {
                                formed = ((long)high << 16) + (long)((short)(second & 0xFFFFL)) & 0xFFFFFFFFL;
                            } else if (opcode == 24 && rt == baseRegister) {
                                formed = ((long)high << 16 | second & 0xFFFFL) & 0xFFFFFFFFL;
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

    private Map<Integer, List<Long>> fieldAccesses() throws Exception {
        LinkedHashMap<Integer, List<Long>> result = new LinkedHashMap<Integer, List<Long>>();
        for (int field : INPUT_FIELDS) {
            result.put(field, new ArrayList());
        }
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
                if (opcode != 32 && opcode != 34 && opcode != 36 && opcode != 38) continue;
                int displacement = (int)(instruction & 0xFFFFL);
                for (int field : INPUT_FIELDS) {
                    if (displacement != (field & 0xFFFF)) continue;
                    ((List)result.get(field)).add(source);
                }
            }
        }
        return result;
    }

    private void addOwner(Set<Function> functions, long source) {
        Function function = this.owner(source);
        if (function != null) {
            functions.add(function);
        }
    }

    private void addDirectCallers(Set<Function> functions, Set<Long> targets) throws Exception {
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
                if (instruction >>> 26 != 18L || (instruction & 1L) == 0L || !targets.contains(this.directBranchTarget(source, instruction))) continue;
                this.addOwner(functions, source);
            }
        }
    }

    private void writeFunctionAssembly(BufferedWriter output, Function function) throws Exception {
        int count;
        output.write("FUNCTION " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + "\n");
        Instruction instruction = this.currentProgram.getListing().getInstructionAt(function.getEntryPoint());
        for (count = 0; instruction != null && function.getBody().contains(instruction.getAddress()) && count < 2600; instruction = instruction.getNext(), ++count) {
            ArrayList<String> references = new ArrayList<String>();
            for (Reference reference : instruction.getReferencesFrom()) {
                references.add(String.valueOf(reference.getReferenceType()) + "->" + String.valueOf(reference.getToAddress()));
            }
            output.write("  " + String.valueOf(instruction.getAddress()) + " " + this.bytes(instruction.getAddress(), instruction.getLength()) + " " + instruction.toString().replace('\t', ' ') + (String)(references.isEmpty() ? "" : " refs=" + String.join(";", references)) + "\n");
        }
        if (count >= 2600) {
            output.write("  <TRUNCATED>\n");
        }
        output.write("\n");
    }

    private void writeRawWindow(BufferedWriter output, long start, int instructionCount) throws Exception {
        output.write("RAW_WINDOW " + this.hex(start) + " count=" + instructionCount + "\n");
        Instruction instruction = this.currentProgram.getListing().getInstructionAt(this.address(start));
        if (instruction == null) {
            output.write("  <NO_LISTING_INSTRUCTION>\n\n");
            return;
        }
        for (int index = 0; instruction != null && index < instructionCount; instruction = instruction.getNext(), ++index) {
            ArrayList<String> references = new ArrayList<String>();
            for (Reference reference : instruction.getReferencesFrom()) {
                references.add(String.valueOf(reference.getReferenceType()) + "->" + String.valueOf(reference.getToAddress()));
            }
            output.write("  " + String.valueOf(instruction.getAddress()) + " " + this.bytes(instruction.getAddress(), instruction.getLength()) + " " + instruction.toString().replace('\t', ' ') + (String)(references.isEmpty() ? "" : " refs=" + String.join(";", references)) + "\n");
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
            throw new IllegalArgumentException("usage: BackbreakerTU2PassingSelectorTrace.java OUTPUT_DIRECTORY");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected TU2 XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(directory));
        }
        Map<Integer, List<Long>> fields = this.fieldAccesses();
        LinkedHashSet<Function> functions = new LinkedHashSet<Function>();
        long[] object = CODE_SEEDS;
        int n = object.length;
        for (int object2 = 0; object2 < n; ++object2) {
            long seed = object[object2];
            this.addOwner(functions, seed);
        }
        for (List<Long> accesses : fields.values()) {
            for (long source : accesses) {
                this.addOwner(functions, source);
            }
        }
        for (long target : DATA_TARGETS) {
            for (long source : this.materializations(target)) {
                this.addOwner(functions, source);
            }
        }
        for (long target : STRING_TARGETS) {
            for (long source : this.materializations(target)) {
                this.addOwner(functions, source);
            }
        }
        LinkedHashSet<Long> linkedHashSet = new LinkedHashSet<Long>();
        for (long seed : CODE_SEEDS) {
            Function function = this.owner(seed);
            if (function == null) continue;
            linkedHashSet.add(function.getEntryPoint().getUnsignedOffset());
        }
        this.addDirectCallers(functions, linkedHashSet);
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_passing_selector_facts.txt")))) {
            output.write("Backbreaker TU2 passing-selector trace\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n");
            output.write("script_mode=read_only_no_database_edits\n\n");
            output.write("ENUM_AND_ACTION_POINTER_CELLS\n");
            for (long target : DATA_TARGETS) {
                long value = this.word(target);
                output.write("  cell=" + this.hex(target) + " value=" + this.hex(value) + " ascii=\"" + this.cString(value, 120) + "\"\n");
                for (long source : this.materializations(target)) {
                    output.write("    materialized_at=" + this.hex(source) + " owner=" + this.ownerText(source) + "\n");
                }
            }
            output.write("\nENUM_TABLE_WINDOW_829D0FC0_829D1060\n");
            for (long location = 2191331264L; location < 2191331424L; location += 4L) {
                long value = this.word(location);
                String text = this.cString(value, 80);
                output.write("  " + this.hex(location) + " " + this.hex(value) + (String)(text.isEmpty() ? "" : " -> \"" + text + "\"") + "\n");
            }
            output.write("\nPASSING_UI_STRING_REFERENCES\n");
            for (long target : STRING_TARGETS) {
                output.write("STRING " + this.hex(target) + " ascii=\"" + this.cString(target, 160) + "\"\n");
                for (long source : this.materializations(target)) {
                    output.write("  materialized_at=" + this.hex(source) + " owner=" + this.ownerText(source) + "\n");
                }
            }
            output.write("\nINPUT_FIELD_ACCESSES\n");
            Iterator object2 = fields.entrySet().iterator();
            while (object2.hasNext()) {
                Map.Entry entry = (Map.Entry)object2.next();
                output.write("FIELD +" + String.format("0x%03X", entry.getKey()) + " count=" + ((List)entry.getValue()).size() + "\n");
                Iterator iterator = ((List)entry.getValue()).iterator();
                while (iterator.hasNext()) {
                    long source = (Long)iterator.next();
                    output.write("  at=" + this.hex(source) + " word=" + this.hex(this.word(source)) + " owner=" + this.ownerText(source) + "\n");
                }
            }
            output.write("\nBOUNDED_FUNCTIONS count=" + functions.size() + "\n");
            for (Function function : functions) {
                output.write("  " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + "\n");
            }
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_passing_selector_assembly.txt")))) {
            output.write("Backbreaker TU2 passing-selector bounded assembly\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n\n");
            for (Function function : functions) {
                this.writeFunctionAssembly(output, function);
            }
            this.writeRawWindow(output, 2184579840L, 48);
            this.writeRawWindow(output, 2184579920L, 48);
            this.writeRawWindow(output, 2183476208L, 96);
            this.writeRawWindow(output, 2183479152L, 48);
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_passing_selector_pseudo_c.c")))) {
            output.write("/* Backbreaker TU2 passing-selector bounded pseudo-C. */\n\n");
            this.writeDecompilation(output, functions);
        }
        this.println("BACKBREAKER_TU2_PASSING_SELECTOR_TRACE_COMPLETE output=" + String.valueOf(directory));
    }
}


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
import java.util.Iterator;

public class BackbreakerTU2ReceiverIconHudAudit
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";
    private static final long[] CODE_TARGETS = new long[]{2184970560L, 2184973536L, 2184973736L, 2184412712L, 2184573416L, 2184579840L, 2184579920L, 2184614088L, 2184614784L, 2184486624L, 2182828536L, 2183479152L, 2184657984L, 2184968792L, 2184969032L, 2184969608L, 2184970320L, 2184970400L, 2183505352L};
    private static final long[] BUTTON_HANDLE_GLOBALS = new long[]{2192368760L, 2192368776L, 2192368780L, 2192368784L, 2192368788L};
    private static final long[] RECEIVE_CIRCLE_GLOBALS = new long[]{2194124484L, 2194124488L, 2194124492L, 2194124496L, 2191386848L};
    private static final long[] STRING_TARGETS = new long[]{2181184628L, 2181184368L, 2181412152L, 2181412216L, 2181412244L, 2181399112L, 2181131824L, 2181132000L, 2181132044L, 2181132088L, 2181132132L, 2181266464L, 2181266480L, 2181266496L, 2181266512L, 2181266528L, 2181372124L, 2181372140L, 2181372156L, 2181372172L, 2181372188L, 2181808648L, 2181808668L, 2181808688L, 2181808708L, 2181257876L, 2181193956L, 2181193904L, 2181193788L, 2181193768L};
    private static final long[][] DEBUG_TOGGLE_RECORDS = new long[][]{{2191312636L, 102L}, {2191312676L, 104L}, {2191312776L, 109L}, {2191312796L, 110L}};
    private static final long[][] DEBUG_GLOBAL_RECORDS = new long[][]{{2191310616L, 1L}, {2191310656L, 3L}};
    private static final long[] DEBUG_TOGGLE_RUNTIME_BYTES = new long[]{2192920753L, 2192920755L, 2192920854L, 2192920856L, 2192920861L, 2192920862L};

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

    private long directBranchTarget(long from, long instruction) {
        int displacement = (int)(instruction & 0x3FFFFFCL);
        if ((displacement & 0x2000000) != 0) {
            displacement |= 0xFC000000;
        }
        return (instruction & 2L) != 0L ? Integer.toUnsignedLong(displacement) : from + (long)displacement & 0xFFFFFFFFL;
    }

    private Function owner(long value) {
        return this.currentProgram.getFunctionManager().getFunctionContaining(this.address(value));
    }

    private String ownerText(long value) {
        Function function = this.owner(value);
        return function == null ? "none" : function.getName() + "@" + this.hex(function.getEntryPoint().getUnsignedOffset());
    }

    private List<Long> materializations(long target) throws Exception {
        ArrayList<Long> found = new ArrayList<Long>();
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            if (!block.isExecute()) continue;
            long first = block.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = block.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            long source = first;
            while (source + 28L <= last) {
                block9: {
                    long firstWord;
                    try {
                        firstWord = this.word(source);
                    }
                    catch (Exception exception) {
                        break block9;
                    }
                    if (firstWord >>> 26 == 15L && (firstWord >>> 16 & 0x1FL) == 0L) {
                        int register = (int)(firstWord >>> 21 & 0x1FL);
                        short high = (short)(firstWord & 0xFFFFL);
                        for (int step = 1; step <= 7; ++step) {
                            long second = this.word(source + (long)step * 4L);
                            int opcode = (int)(second >>> 26);
                            int rt = (int)(second >>> 21 & 0x1FL);
                            int ra = (int)(second >>> 16 & 0x1FL);
                            long formed = -1L;
                            if (opcode == 14 && ra == register) {
                                formed = ((long)high << 16) + (long)((short)(second & 0xFFFFL)) & 0xFFFFFFFFL;
                            } else if (opcode == 24 && rt == register) {
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

    private List<Long> directCallers(long target) throws Exception {
        ArrayList<Long> found = new ArrayList<Long>();
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
                if (instruction >>> 26 != 18L || (instruction & 1L) == 0L || this.directBranchTarget(source, instruction) != target) continue;
                found.add(source);
            }
        }
        return found;
    }

    private List<Long> immediateR3Callers(long target, int immediate) throws Exception {
        ArrayList<Long> found = new ArrayList<Long>();
        long wanted = 0x38600000L | (long)immediate & 0xFFFFL;
        block0: for (long caller : this.directCallers(target)) {
            for (int step = 1; step <= 8; ++step) {
                long source = caller - (long)step * 4L;
                if (this.word(source) != wanted) continue;
                found.add(caller);
                continue block0;
            }
        }
        return found;
    }

    private List<Long> fieldAccesses(int displacement) throws Exception {
        ArrayList<Long> found = new ArrayList<Long>();
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
                if (opcode < 32 || opcode > 55 || (short)(instruction & 0xFFFFL) != (short)displacement) continue;
                found.add(source);
            }
        }
        return found;
    }

    private List<Long> fieldImmediateMentions(int displacement) throws Exception {
        ArrayList<Long> found = new ArrayList<Long>();
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
                if ((instruction & 0xFFFFL) != ((long)displacement & 0xFFFFL) || opcode != 14 && opcode != 15 && opcode != 24 && opcode != 25 && (opcode < 32 || opcode > 55)) continue;
                found.add(source);
            }
        }
        return found;
    }

    private List<Long> globalDFormReferences(long target) throws Exception {
        LinkedHashSet<Long> found = new LinkedHashSet<Long>();
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
                        int register = (int)(firstWord >>> 21 & 0x1FL);
                        short high = (short)(firstWord & 0xFFFFL);
                        for (int step = 1; step <= 12; ++step) {
                            long formed;
                            long access = source + (long)step * 4L;
                            long second = this.word(access);
                            int opcode = (int)(second >>> 26);
                            int ra = (int)(second >>> 16 & 0x1FL);
                            if (opcode < 32 || opcode > 55 || ra != register || (formed = ((long)high << 16) + (long)((short)(second & 0xFFFFL)) & 0xFFFFFFFFL) != target) continue;
                            found.add(access);
                        }
                    }
                }
                source += 4L;
            }
        }
        return new ArrayList<Long>(found);
    }

    private void dumpFunction(BufferedWriter output, Function function) throws Exception {
        output.write("FUNCTION " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + "\n");
        Instruction instruction = this.currentProgram.getListing().getInstructionAt(function.getEntryPoint());
        for (int count = 0; instruction != null && function.getBody().contains(instruction.getAddress()) && count < 3200; instruction = instruction.getNext(), ++count) {
            ArrayList<String> refs = new ArrayList<String>();
            for (Reference reference : instruction.getReferencesFrom()) {
                refs.add(String.valueOf(reference.getReferenceType()) + "->" + String.valueOf(reference.getToAddress()));
            }
            output.write("  " + String.valueOf(instruction.getAddress()) + " " + this.bytes(instruction.getAddress(), instruction.getLength()) + " " + instruction.toString().replace('\t', ' ') + (String)(refs.isEmpty() ? "" : " refs=" + String.join((CharSequence)";", refs)) + "\n");
        }
        output.write("\n");
    }

    private void dumpRaw(BufferedWriter output, long first, long last, String label) throws Exception {
        output.write("RAW " + label + " " + this.hex(first) + ".." + this.hex(last) + "\n");
        for (long value = first; value <= last; value += 4L) {
            Instruction instruction = this.currentProgram.getListing().getInstructionAt(this.address(value));
            output.write("  " + this.hex(value) + " " + this.bytes(this.address(value), 4) + " " + (instruction == null ? "<UNDEFINED_XENON_WORD>" : instruction.toString().replace('\t', ' ')) + " owner=" + this.ownerText(value) + "\n");
        }
        output.write("\n");
    }

    /*
     * WARNING - Removed try catching itself - possible behaviour change.
     */
    protected void run() throws Exception {
        Iterator source52;
        Iterator function;
        Function function2;
        long source2;
        int n;
        Iterator function3;
        String[] args = this.getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: BackbreakerTU2ReceiverIconHudAudit.java OUTPUT_DIRECTORY");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected TU2 XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(directory));
        }
        LinkedHashSet<Function> functions = new LinkedHashSet<Function>();
        for (long target : CODE_TARGETS) {
            Function codeOwner = this.owner(target);
            if (codeOwner == null) continue;
            functions.add(codeOwner);
        }
        long[] lArray = STRING_TARGETS;
        int n2 = lArray.length;
        for (n = 0; n < n2; ++n) {
            long target;
            target = lArray[n];
            function3 = this.materializations(target).iterator();
            while (function3.hasNext()) {
                long source22 = (Long)function3.next();
                Function function22 = this.owner(source22);
                if (function22 == null) continue;
                functions.add(function22);
            }
        }
        for (long source3 : this.fieldAccesses(8176)) {
            Function function4 = this.owner(source3);
            if (function4 == null) continue;
            functions.add(function4);
        }
        for (long target : BUTTON_HANDLE_GLOBALS) {
            function3 = this.globalDFormReferences(target).iterator();
            while (function3.hasNext()) {
                source2 = (Long)function3.next();
                function2 = this.owner(source2);
                if (function2 == null) continue;
                functions.add(function2);
            }
        }
        for (long target : RECEIVE_CIRCLE_GLOBALS) {
            function3 = this.globalDFormReferences(target).iterator();
            while (function3.hasNext()) {
                source2 = (Long)function3.next();
                function2 = this.owner(source2);
                if (function2 == null) continue;
                functions.add(function2);
            }
        }
        long[][] lArray2 = DEBUG_TOGGLE_RECORDS;
        int source3 = lArray2.length;
        for (n = 0; n < source3; ++n) {
            long[] record = lArray2[n];
            for (long source4 : this.immediateR3Callers(2183505352L, (int)record[1])) {
                Function toggleOwner = this.owner(source4);
                if (toggleOwner == null) continue;
                functions.add(toggleOwner);
            }
        }
        for (long directCaller : this.directCallers(2184614088L)) {
            Function function5 = this.owner(directCaller);
            if (function5 == null) continue;
            functions.add(function5);
        }
        for (long target : DEBUG_TOGGLE_RUNTIME_BYTES) {
            for (long runtimeRef : this.globalDFormReferences(target)) {
                function2 = this.owner(runtimeRef);
                if (function2 == null) continue;
                functions.add(function2);
            }
        }
        try (BufferedWriter bufferedWriter = new BufferedWriter(new FileWriter(new File(directory, "tu2_receiver_icon_hud_facts.txt")))) {
            Instruction instruction;
            bufferedWriter.write("Backbreaker TU2 receiver-icon/HUD audit\n");
            bufferedWriter.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n");
            bufferedWriter.write("script_mode=read_only_no_database_edits\n\n");
            bufferedWriter.write("CODE_TARGETS\n");
            for (long target : CODE_TARGETS) {
                Function function6 = this.owner(target);
                bufferedWriter.write("  target=" + this.hex(target) + " owner=" + this.ownerText(target) + "\n");
                function = this.directCallers(target).iterator();
                while (function.hasNext()) {
                    long caller = (Long)function.next();
                    bufferedWriter.write("    caller=" + this.hex(caller) + " owner=" + this.ownerText(caller) + " word=" + this.hex(this.word(caller)) + "\n");
                }
            }
            bufferedWriter.write("\nSTRINGS_AND_REFERENCES\n");
            for (long target : STRING_TARGETS) {
                bufferedWriter.write("  string=" + this.hex(target) + " ascii=\"" + this.cString(target, 180) + "\"\n");
                for (long source6 : this.materializations(target)) {
                    bufferedWriter.write("    materialized=" + this.hex(source6) + " owner=" + this.ownerText(source6) + "\n");
                }
                for (long source4 : this.alignedPointers(target)) {
                    bufferedWriter.write("    pointer_cell=" + this.hex(source4) + " owner=" + this.ownerText(source4) + "\n");
                }
            }
            bufferedWriter.write("\nENTITY_FIELD_ACCESSES displacement=0x1FF0\n");
            source52 = this.fieldAccesses(8176).iterator();
            while (source52.hasNext()) {
                long source7 = (Long)source52.next();
                Instruction instruction2 = this.currentProgram.getListing().getInstructionAt(this.address(source7));
                bufferedWriter.write("  access=" + this.hex(source7) + " owner=" + this.ownerText(source7) + " word=" + this.hex(this.word(source7)) + " instruction=\"" + (instruction2 == null ? "<UNDEFINED_XENON_WORD>" : instruction2.toString().replace('\t', ' ')) + "\"\n");
            }
            bufferedWriter.write("\nENTITY_FIELD_IMMEDIATE_MENTIONS low16=0x1FF0\n");
            source52 = this.fieldImmediateMentions(8176).iterator();
            while (source52.hasNext()) {
                long source8 = (Long)source52.next();
                Instruction instruction3 = this.currentProgram.getListing().getInstructionAt(this.address(source8));
                bufferedWriter.write("  mention=" + this.hex(source8) + " owner=" + this.ownerText(source8) + " word=" + this.hex(this.word(source8)) + " instruction=\"" + (instruction3 == null ? "<UNDEFINED_XENON_WORD>" : instruction3.toString().replace('\t', ' ')) + "\"\n");
            }
            for (int displacement : new int[]{1496, 1500}) {
                bufferedWriter.write("\nPLAYER_HIGHLIGHT_STYLE_FIELD_ACCESSES displacement=" + this.hex(displacement) + "\n");
                for (long source9 : this.fieldAccesses((int)displacement)) {
                    Instruction instruction4 = this.currentProgram.getListing().getInstructionAt(this.address(source9));
                    bufferedWriter.write("  access=" + this.hex(source9) + " owner=" + this.ownerText(source9) + " word=" + this.hex(this.word(source9)) + " instruction=\"" + (instruction4 == null ? "<UNDEFINED_XENON_WORD>" : instruction4.toString().replace('\t', ' ')) + "\"\n");
                }
            }
            bufferedWriter.write("\nBUTTON_HANDLE_GLOBAL_REFERENCES\n");
            for (long target : BUTTON_HANDLE_GLOBALS) {
                bufferedWriter.write("  global=" + this.hex(target) + "\n");
                for (long source10 : this.globalDFormReferences(target)) {
                    instruction = this.currentProgram.getListing().getInstructionAt(this.address(source10));
                    bufferedWriter.write("    access=" + this.hex(source10) + " owner=" + this.ownerText(source10) + " word=" + this.hex(this.word(source10)) + " instruction=\"" + (instruction == null ? "<UNDEFINED_XENON_WORD>" : instruction.toString().replace('\t', ' ')) + "\"\n");
                }
            }
            bufferedWriter.write("\nRECEIVE_CIRCLE_GLOBAL_REFERENCES\n");
            for (long target : RECEIVE_CIRCLE_GLOBALS) {
                bufferedWriter.write("  global=" + this.hex(target) + "\n");
                for (long source11 : this.globalDFormReferences(target)) {
                    instruction = this.currentProgram.getListing().getInstructionAt(this.address(source11));
                    bufferedWriter.write("    access=" + this.hex(source11) + " owner=" + this.ownerText(source11) + " word=" + this.hex(this.word(source11)) + " instruction=\"" + (instruction == null ? "<UNDEFINED_XENON_WORD>" : instruction.toString().replace('\t', ' ')) + "\"\n");
                }
            }
            bufferedWriter.write("\nPLAYER_DEBUG_TOGGLE_RECORDS\n");
            for (long[] record : DEBUG_TOGGLE_RECORDS) {
                long start = record[0];
                int identifier = (int)record[1];
                bufferedWriter.write("  record=" + this.hex((long)start) + " category=" + this.hex(this.word((long)start)) + " category_ascii=\"" + this.cString(this.word((long)start), 100) + "\" name=" + this.hex(this.word((long)(start + 4L))) + " name_ascii=\"" + this.cString(this.word((long)(start + 4L)), 100) + "\" callback_or_storage=" + this.hex(this.word((long)(start + 8L))) + " id=" + this.hex(this.word((long)(start + 12L))) + " expected_id=" + this.hex(identifier) + " default_byte=" + (this.currentProgram.getMemory().getByte(this.address((long)(start + 16L))) & 0xFF) + "\n");
                for (long caller : this.immediateR3Callers(2183505352L, identifier)) {
                    bufferedWriter.write("    getter_call=" + this.hex(caller) + " owner=" + this.ownerText(caller) + "\n");
                }
            }
            bufferedWriter.write("\nPLAYER_DEBUG_GLOBAL_RECORDS\n");
            for (long[] record : DEBUG_GLOBAL_RECORDS) {
                long start = record[0];
                int identifier = (int)record[1];
                bufferedWriter.write("  record=" + this.hex((long)start) + " category=" + this.hex(this.word((long)start)) + " category_ascii=\"" + this.cString(this.word((long)start), 100) + "\" name=" + this.hex(this.word((long)(start + 4L))) + " name_ascii=\"" + this.cString(this.word((long)(start + 4L)), 180) + "\" callback_or_storage=" + this.hex(this.word((long)(start + 8L))) + " id=" + this.hex(this.word((long)(start + 12L))) + " expected_id=" + this.hex(identifier) + " default_byte=" + (this.currentProgram.getMemory().getByte(this.address((long)(start + 16L))) & 0xFF) + "\n");
            }
            bufferedWriter.write("\nPLAYER_DEBUG_RUNTIME_BYTE_REFERENCES\n");
            for (long target : DEBUG_TOGGLE_RUNTIME_BYTES) {
                bufferedWriter.write("  global=" + this.hex(target) + " image_byte=" + (this.currentProgram.getMemory().getByte(this.address(target)) & 0xFF) + "\n");
                for (long source12 : this.globalDFormReferences(target)) {
                    Instruction instruction5 = this.currentProgram.getListing().getInstructionAt(this.address(source12));
                    bufferedWriter.write("    access=" + this.hex(source12) + " owner=" + this.ownerText(source12) + " word=" + this.hex(this.word(source12)) + " instruction=\"" + (instruction5 == null ? "<UNDEFINED_XENON_WORD>" : instruction5.toString().replace('\t', ' ')) + "\"\n");
                }
            }
        }
        try (BufferedWriter bufferedWriter = new BufferedWriter(new FileWriter(new File(directory, "tu2_receiver_icon_hud_assembly.txt")))) {
            bufferedWriter.write("Backbreaker TU2 receiver-icon/HUD assembly\n");
            bufferedWriter.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n\n");
            source52 = functions.iterator();
            while (source52.hasNext()) {
                Function function7 = (Function)source52.next();
                this.dumpFunction(bufferedWriter, function7);
            }
            this.dumpRaw(bufferedWriter, 2183479104L, 2183479328L, "hud_path_raw_window");
            this.dumpRaw(bufferedWriter, 2184973440L, 2184974848L, "hud_dispatch_raw_window");
            this.dumpRaw(bufferedWriter, 2184412672L, 2184412960L, "entity_highlight_raw_window");
            this.dumpRaw(bufferedWriter, 2184657920L, 2184658176L, "icon_switch_receiver_raw_window");
            this.dumpRaw(bufferedWriter, 2184968992L, 2184970320L, "receive_circle_pass_fx_raw_window");
            this.dumpRaw(bufferedWriter, 2184971088L, 2184971520L, "receive_circle_update_raw_window");
            this.dumpRaw(bufferedWriter, 2184384640L, 2184385056L, "wide_receiver_name_ladder_raw_window");
            this.dumpRaw(bufferedWriter, 2191310616L, 2191310675L, "global_debug_gate_records");
            this.dumpRaw(bufferedWriter, 2191312636L, 2191312815L, "player_debug_toggle_records");
            this.dumpRaw(bufferedWriter, 2183505352L, 2183505440L, "player_debug_indexed_getter");
            this.dumpRaw(bufferedWriter, 2184473216L, 2184474320L, "entity_init_highlight_zero_a");
            this.dumpRaw(bufferedWriter, 2184475008L, 2184478224L, "entity_init_highlight_zero_b");
            this.dumpRaw(bufferedWriter, 2184614016L, 2184614780L, "player_highlight_update_raw_window");
            this.dumpRaw(bufferedWriter, 2184621504L, 2184624480L, "receiver_ready_flash_callers_raw_window");
            this.dumpRaw(bufferedWriter, 2185249104L, 2185249136L, "stock_timestep_scalar_getter");
        }
        DecompInterface decompInterface = new DecompInterface();
        if (!decompInterface.openProgram(this.currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_receiver_icon_hud_pseudo_c.c")))) {
            output.write("/* Backbreaker TU2 receiver-icon/HUD pseudo-C. */\n\n");
            for (Function function8 : functions) {
                output.write("/* " + function8.getName() + " " + String.valueOf(function8.getEntryPoint()) + ".." + String.valueOf(function8.getBody().getMaxAddress()) + " */\n");
                DecompileResults result = decompInterface.decompileFunction(function8, 180, this.monitor);
                output.write("/* completed=" + result.decompileCompleted() + " error=" + result.getErrorMessage().replace('\n', ' ') + " */\n");
                if (result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                }
                output.write("\n\n");
            }
        }
        finally {
            decompInterface.dispose();
        }
        this.println("BACKBREAKER_TU2_RECEIVER_ICON_HUD_AUDIT_COMPLETE output=" + String.valueOf(directory));
    }
}


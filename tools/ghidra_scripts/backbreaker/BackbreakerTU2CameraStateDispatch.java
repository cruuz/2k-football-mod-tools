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
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.Iterator;

public class BackbreakerTU2CameraStateDispatch
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";
    private static final Range[] RANGES = new Range[]{new Range(2183178936L, 2183179692L, "shared_camera_target_and_activation_dispatch"), new Range(2183354744L, 2183355412L, "camera_current_owner_resolver_and_registration"), new Range(2183355968L, 2183356652L, "camera_packet_owners_and_mode_reset"), new Range(2183357008L, 2183358396L, "camera_event_and_transition_dispatch"), new Range(2183358400L, 2183358496L, "debug_camera_mode_remap"), new Range(2183363504L, 2183363872L, "camera_mode_request"), new Range(2183365832L, 2183366204L, "camera_director_selection"), new Range(2183367136L, 2183372524L, "camera_catalog_constructor"), new Range(2183372768L, 2183373356L, "definitive_packet_owner_and_copy"), new Range(2183373360L, 2183374016L, "camera_to_packet_builder"), new Range(2183374592L, 2183374920L, "camera_director_update_and_early_packet"), new Range(2183377464L, 2183377712L, "camera_controller_transition_packet_update")};
    private static final NamedAddress[] KEY_TARGETS = new NamedAddress[]{new NamedAddress(2183354424L, "packet_copier"), new NamedAddress(2183354896L, "current_camera_owner_resolver"), new NamedAddress(2183355144L, "camera_registration_and_initial_packet"), new NamedAddress(2183365832L, "camera_director_selection"), new NamedAddress(2183367136L, "camera_catalog_constructor"), new NamedAddress(2183372768L, "definitive_packet_owner_and_copy"), new NamedAddress(2183373360L, "camera_to_packet_builder"), new NamedAddress(2183374592L, "camera_director_update"), new NamedAddress(2183175296L, "camera_active_request_writer"), new NamedAddress(2183175312L, "shared_camera_fov_getter")};
    private static final NamedAddress[] KNOWN_VTABLES = new NamedAddress[]{new NamedAddress(2181400604L, "QB"), new NamedAddress(2181400708L, "Ready"), new NamedAddress(2181363092L, "Pass"), new NamedAddress(2181417644L, "Tackle"), new NamedAddress(2181156756L, "BallLock")};
    private static final NamedAddress[] CAMERA_STRINGS = new NamedAddress[]{new NamedAddress(2181179008L, "GroundQBFace Camera"), new NamedAddress(2181179028L, "GroundQBBack Camera"), new NamedAddress(2181179048L, "SideLine Camera"), new NamedAddress(2181179064L, "Wide Camera"), new NamedAddress(2181179076L, "Sky Camera"), new NamedAddress(2181179088L, "Zoning Camera"), new NamedAddress(2181179104L, "Loose Ball Camera"), new NamedAddress(2181179124L, "Timeout Camera"), new NamedAddress(2181179140L, "Pause Camera"), new NamedAddress(2181179156L, "Jumbotron Camera"), new NamedAddress(2181179176L, "End Of Play Camera"), new NamedAddress(2181179196L, "Kick Return Upfield Camera"), new NamedAddress(2181179224L, "Kick Return Sideline Camera"), new NamedAddress(2181179252L, "Kick Return Camera"), new NamedAddress(2181179272L, "Kicking Camera"), new NamedAddress(2181179288L, "OutOfAction Camera"), new NamedAddress(2181179308L, "Test Camera"), new NamedAddress(2181179320L, "Tackling Camera"), new NamedAddress(2181179336L, "Tackle Camera"), new NamedAddress(2181179352L, "TV Camera"), new NamedAddress(2181179364L, "Replay Camera"), new NamedAddress(2181179380L, "Free Flight Camera"), new NamedAddress(0x82022808L, "Debug Camera"), new NamedAddress(2181179416L, "Cinematic Camera"), new NamedAddress(2181179436L, "Charge Camera"), new NamedAddress(2181179452L, "Chase Camera"), new NamedAddress(2181179468L, "Play Start Camera"), new NamedAddress(2181179488L, "Overview Camera"), new NamedAddress(2181179504L, "Focus Camera"), new NamedAddress(0x82022880L, "Player Switch Camera"), new NamedAddress(2181179544L, "Turn Camera"), new NamedAddress(2181179556L, "Cut Turn Camera"), new NamedAddress(2181179572L, "Catch Camera"), new NamedAddress(2181179588L, "Pitch Camera"), new NamedAddress(2181179604L, "Pass Camera"), new NamedAddress(2181179616L, "Showboat Camera"), new NamedAddress(2181179632L, "Intercepted Camera"), new NamedAddress(2181179652L, "Interception Camera"), new NamedAddress(2181179672L, "FieldGoalPlayer Camera"), new NamedAddress(2181179696L, "FieldGoalGoalPost Camera"), new NamedAddress(2181179724L, "Endzone Camera"), new NamedAddress(2181179740L, "Celebration Camera"), new NamedAddress(2181179760L, "FairCatch Camera"), new NamedAddress(2181179780L, "CornerBack Camera"), new NamedAddress(2181179800L, "Wide Receiver Camera"), new NamedAddress(2181179824L, "Ball Lock Camera"), new NamedAddress(2181179844L, "Multiplayer Bullet Camera"), new NamedAddress(2181179872L, "Evasion Camera"), new NamedAddress(2181179888L, "Ready Camera"), new NamedAddress(2181179904L, "QB Camera")};

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

    private long word(long value) throws Exception {
        return Integer.toUnsignedLong(this.currentProgram.getMemory().getInt(this.address(value)));
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
        if (function == null) {
            return "no_function";
        }
        return function.getName() + "@" + this.hex(function.getEntryPoint().getUnsignedOffset());
    }

    private boolean executable(Address cursor) {
        MemoryBlock block = this.currentProgram.getMemory().getBlock(cursor);
        return block != null && block.isExecute();
    }

    private void writeRange(BufferedWriter output, Range range) throws Exception {
        output.write("RANGE " + range.label + " " + this.hex(range.first) + ".." + this.hex(range.last) + "\n");
        for (long value = range.first; value <= range.last; value += 4L) {
            Address cursor = this.address(value);
            Instruction instruction = this.currentProgram.getListing().getInstructionAt(cursor);
            String rendered = instruction == null ? "<UNDEFINED_XENON_WORD>" : instruction.toString().replace('\t', ' ');
            ArrayList<String> references = new ArrayList<String>();
            if (instruction != null) {
                for (Reference reference : instruction.getReferencesFrom()) {
                    references.add(String.valueOf(reference.getReferenceType()) + "->" + String.valueOf(reference.getToAddress()));
                }
            }
            output.write(this.hex(value) + " " + this.bytes(cursor, 4) + " " + rendered + (String)(references.isEmpty() ? "" : " refs=" + String.join(";", references)) + "\n");
        }
        output.write("\n");
    }

    private void writeRawBranchReferences(BufferedWriter output, NamedAddress target) throws Exception {
        output.write("TARGET " + target.label + " " + this.hex(target.address) + "\n");
        LinkedHashSet<Long> found = new LinkedHashSet<Long>();
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
                if (instruction >>> 26 != 18L || this.directBranchTarget(source, instruction) != target.address) continue;
                found.add(source);
                output.write("  from=" + this.hex(source) + " word=" + this.hex(instruction) + " lk=" + (instruction & 1L) + " owner=" + this.ownerText(source) + "\n");
            }
        }
        output.write("  count=" + found.size() + "\n\n");
    }

    private void writeGhidraReferences(BufferedWriter output, NamedAddress target) throws Exception {
        output.write("GHIDRA_REFERENCES " + target.label + " " + this.hex(target.address) + "\n");
        ReferenceIterator references = this.currentProgram.getReferenceManager().getReferencesTo(this.address(target.address));
        int count = 0;
        while (references.hasNext()) {
            Reference reference = references.next();
            ++count;
            output.write("  type=" + String.valueOf(reference.getReferenceType()) + " from=" + String.valueOf(reference.getFromAddress()) + " owner=" + this.ownerText(reference.getFromAddress().getUnsignedOffset()) + "\n");
        }
        output.write("  count=" + count + "\n\n");
    }

    private void writeMaterializations(BufferedWriter output, NamedAddress target) throws Exception {
        output.write("MATERIALIZATIONS " + target.label + " " + this.hex(target.address) + "\n");
        int count = 0;
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            if (!block.isExecute()) continue;
            long first = block.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = block.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            long source = first;
            while (source + 24L <= last) {
                block10: {
                    long firstWord;
                    try {
                        firstWord = this.word(source);
                    }
                    catch (Exception exception) {
                        break block10;
                    }
                    if (firstWord >>> 26 == 15L) {
                        int baseRegister = (int)(firstWord >>> 21 & 0x1FL);
                        int base = (int)(firstWord >>> 16 & 0x1FL);
                        if (base == 0) {
                            short high = (short)(firstWord & 0xFFFFL);
                            for (int step = 1; step <= 6; ++step) {
                                long secondAddress = source + (long)step * 4L;
                                long secondWord = this.word(secondAddress);
                                int opcode = (int)(secondWord >>> 26);
                                int rtOrRs = (int)(secondWord >>> 21 & 0x1FL);
                                int ra = (int)(secondWord >>> 16 & 0x1FL);
                                long formed = -1L;
                                if (opcode == 14 && ra == baseRegister) {
                                    formed = ((long)high << 16) + (long)((short)(secondWord & 0xFFFFL)) & 0xFFFFFFFFL;
                                } else if (opcode == 24 && rtOrRs == baseRegister) {
                                    formed = ((long)high << 16 | secondWord & 0xFFFFL) & 0xFFFFFFFFL;
                                }
                                if (formed != target.address) continue;
                                ++count;
                                output.write("  lis=" + this.hex(source) + ":" + this.hex(firstWord) + " complete=" + this.hex(secondAddress) + ":" + this.hex(secondWord) + " base_r=" + baseRegister + " output_r=" + (opcode == 14 ? rtOrRs : ra) + " owner=" + this.ownerText(source) + "\n");
                            }
                        }
                    }
                }
                source += 4L;
            }
        }
        output.write("  count=" + count + "\n\n");
    }

    private void writeVtable(BufferedWriter output, NamedAddress table) throws Exception {
        output.write("VTABLE " + table.label + " " + this.hex(table.address) + " preword=" + this.hex(this.word(table.address - 4L)) + "\n");
        for (int slot = 0; slot < 18; ++slot) {
            long slotAddress = table.address + (long)slot * 4L;
            long target = this.word(slotAddress);
            output.write(String.format("  +0x%02X %s executable=%s owner=%s\n", slot * 4, this.hex(target), this.executable(this.address(target)), this.ownerText(target)));
        }
        output.write("\n");
    }

    private void writeDFormAccesses(BufferedWriter output, int displacement, boolean storesOnly) throws Exception {
        output.write("D_FORM_ACCESSES displacement=" + String.format("0x%04X", displacement) + " stores_only=" + storesOnly + "\n");
        int count = 0;
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
                int opcode = (int)(instruction >>> 26);
                if (!storesOnly ? opcode != 32 && opcode != 36 : opcode != 36) continue;
                if ((instruction & 0xFFFFL) != ((long)displacement & 0xFFFFL) || (function = this.owner(source)) == null) continue;
                int valueRegister = (int)(instruction >>> 21 & 0x1FL);
                int baseRegister = (int)(instruction >>> 16 & 0x1FL);
                output.write("  at=" + this.hex(source) + " word=" + this.hex(instruction) + " op=" + (opcode == 36 ? "stw" : "lwz") + " value_r=" + valueRegister + " base_r=" + baseRegister + " owner=" + this.ownerText(source) + "\n");
                ++count;
            }
        }
        output.write("  count=" + count + "\n\n");
    }

    private void writeFunction(BufferedWriter output, Function function, int limit) throws Exception {
        int count;
        output.write("FUNCTION " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + "\n");
        Instruction instruction = this.currentProgram.getListing().getInstructionAt(function.getEntryPoint());
        for (count = 0; instruction != null && function.getBody().contains(instruction.getAddress()) && count < limit; instruction = instruction.getNext(), ++count) {
            output.write("  " + String.valueOf(instruction.getAddress()) + " " + this.bytes(instruction.getAddress(), instruction.getLength()) + " " + instruction.toString().replace('\t', ' ') + "\n");
        }
        if (count >= limit) {
            output.write("  <TRUNCATED>\n");
        }
        output.write("\n");
    }

    private Set<Function> keyCallerFunctions() throws Exception {
        LinkedHashSet<Function> callers = new LinkedHashSet<Function>();
        LinkedHashSet<Long> targetSet = new LinkedHashSet<Long>();
        for (NamedAddress namedAddress : KEY_TARGETS) {
            targetSet.add(namedAddress.address);
        }
        for (MemoryBlock namedAddress : this.currentProgram.getMemory().getBlocks()) {
            if (!namedAddress.isExecute()) continue;
            long first = namedAddress.getStart().getUnsignedOffset() + 3L & 0xFFFFFFFFFFFFFFFCL;
            long last = namedAddress.getEnd().getUnsignedOffset() & 0xFFFFFFFFFFFFFFFCL;
            for (long source = first; source <= last; source += 4L) {
                Function function;
                long instruction;
                try {
                    instruction = this.word(source);
                }
                catch (Exception exception) {
                    continue;
                }
                if (instruction >>> 26 != 18L || (instruction & 1L) == 0L || !targetSet.contains(this.directBranchTarget(source, instruction)) || (function = this.owner(source)) == null) continue;
                callers.add(function);
            }
        }
        return callers;
    }

    /*
     * WARNING - Removed try catching itself - possible behaviour change.
     */
    private void writeDecompilation(BufferedWriter output, long[] entries) throws Exception {
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(this.currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try {
            LinkedHashSet<Function> functions = new LinkedHashSet<Function>();
            for (long entry : entries) {
                Function function = this.currentProgram.getFunctionManager().getFunctionContaining(this.address(entry));
                if (function == null) continue;
                functions.add(function);
            }
            functions.addAll(this.keyCallerFunctions());
            Iterator object = functions.iterator();
            while (object.hasNext()) {
                Function function = (Function)object.next();
                output.write("/* " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 180, this.monitor);
                output.write("/* completed=" + result.decompileCompleted() + " timed_out=" + result.isTimedOut() + " error=" + result.getErrorMessage().replace('\n', ' ') + " */\n");
                if (result.getDecompiledFunction() == null) {
                    output.write("// No pseudo-C produced.\n\n");
                    continue;
                }
                output.write(result.getDecompiledFunction().getC());
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
            throw new IllegalArgumentException("usage: BackbreakerTU2CameraStateDispatch.java OUTPUT_DIRECTORY");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected TU2 XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(directory));
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_camera_state_dispatch_facts.txt")))) {
            output.write("Backbreaker TU2 camera state-dispatch facts\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n");
            output.write("script_mode=read_only_no_database_edits\n\n");
            output.write("DIRECT_BRANCH_REFERENCES\n");
            for (NamedAddress target : KEY_TARGETS) {
                this.writeRawBranchReferences(output, target);
            }
            output.write("GHIDRA_REFERENCE_INDEX\n");
            for (NamedAddress target : KEY_TARGETS) {
                this.writeGhidraReferences(output, target);
            }
            output.write("KNOWN_CAMERA_VTABLES\n");
            for (NamedAddress table : KNOWN_VTABLES) {
                this.writeVtable(output, table);
                this.writeMaterializations(output, table);
            }
            output.write("CAMERA_PUBLIC_NAME_MATERIALIZATIONS\n");
            for (NamedAddress name : CAMERA_STRINGS) {
                this.writeMaterializations(output, name);
            }
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_camera_state_dispatch_assembly.txt")))) {
            output.write("Backbreaker TU2 bounded camera state-dispatch assembly\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n\n");
            for (Range range : RANGES) {
                this.writeRange(output, range);
            }
            output.write("KEY_CALLER_FUNCTIONS\n");
            for (Function function : this.keyCallerFunctions()) {
                this.writeFunction(output, function, 1600);
            }
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_camera_state_dispatch_pseudo_c.c")))) {
            output.write("/* Backbreaker TU2 bounded camera state-dispatch pseudo-C. */\n\n");
            this.writeDecompilation(output, new long[]{2183178936L, 2183354744L, 2183354896L, 2183355144L, 2183355968L, 2183356224L, 2183356560L, 2183356648L, 2183357008L, 2183358096L, 2183358240L, 2183358400L, 2183363504L, 2183365832L, 2183366208L, 2183366576L, 2183367136L, 2183372768L, 2183373360L, 2183374592L, 2183374824L, 2183377464L, 2184180816L, 2185270656L});
        }
        this.println("BACKBREAKER_TU2_CAMERA_STATE_DISPATCH_COMPLETE output=" + String.valueOf(directory));
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

    private static final class NamedAddress {
        final long address;
        final String label;

        NamedAddress(long address, String label) {
            this.address = address;
            this.label = label;
        }
    }
}


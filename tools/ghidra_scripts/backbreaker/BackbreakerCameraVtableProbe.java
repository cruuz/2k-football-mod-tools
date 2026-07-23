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
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.Iterator;

public class BackbreakerCameraVtableProbe
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";

    private Address address(long value) {
        return this.currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private long word(long value) throws Exception {
        return Integer.toUnsignedLong(this.currentProgram.getMemory().getInt(this.address(value)));
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xFFFFFFFFL);
    }

    private void printReferences(long target, Set<Function> owners) {
        this.println("REFERENCES " + this.hex(target));
        ReferenceIterator references = this.currentProgram.getReferenceManager().getReferencesTo(this.address(target));
        while (references.hasNext()) {
            Reference reference = references.next();
            Function owner = this.currentProgram.getFunctionManager().getFunctionContaining(reference.getFromAddress());
            if (owner != null) {
                owners.add(owner);
            }
            this.println("  " + String.valueOf(reference.getReferenceType()) + " from=" + String.valueOf(reference.getFromAddress()) + " owner=" + (String)(owner == null ? "none" : owner.getName() + "@" + String.valueOf(owner.getEntryPoint())));
        }
    }

    private void printFunction(Function function) throws Exception {
        int count;
        this.println("FUNCTION " + function.getName() + " " + String.valueOf(function.getEntryPoint()) + ".." + String.valueOf(function.getBody().getMaxAddress()));
        Instruction instruction = this.currentProgram.getListing().getInstructionAt(function.getEntryPoint());
        if (instruction == null) {
            this.disassemble(function.getEntryPoint());
            instruction = this.currentProgram.getListing().getInstructionAt(function.getEntryPoint());
        }
        for (count = 0; instruction != null && function.getBody().contains(instruction.getAddress()) && count < 1200; instruction = instruction.getNext(), ++count) {
            this.println("  " + String.valueOf(instruction.getAddress()) + " " + instruction.toString().replace('\t', ' '));
        }
        if (count >= 1200) {
            this.println("  <TRUNCATED>");
        }
    }

    private void printRange(long first, long last, String label) throws Exception {
        this.println("RANGE " + label + " " + this.hex(first) + ".." + this.hex(last));
        for (long value = first; value <= last; value += 4L) {
            Address cursor = this.address(value);
            Instruction instruction = this.currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                this.disassemble(cursor);
                instruction = this.currentProgram.getListing().getInstructionAt(cursor);
            }
            this.println("  " + String.valueOf(cursor) + " " + this.hex(this.word(value)) + " " + (instruction == null ? "<UNDEFINED>" : instruction.toString().replace('\t', ' ')));
        }
    }

    private void printString(String text, Set<Function> owners) throws Exception {
        Address found;
        Memory memory = this.currentProgram.getMemory();
        byte[] bytes = (text + "\u0000").getBytes(StandardCharsets.US_ASCII);
        Address cursor = memory.getMinAddress();
        this.println("STRING " + text);
        while (cursor != null && (found = memory.findBytes(cursor, bytes, null, true, this.monitor)) != null) {
            this.println("  at=" + String.valueOf(found));
            ReferenceIterator references = this.currentProgram.getReferenceManager().getReferencesTo(found);
            while (references.hasNext()) {
                Reference reference = references.next();
                Function owner = this.currentProgram.getFunctionManager().getFunctionContaining(reference.getFromAddress());
                if (owner != null) {
                    owners.add(owner);
                }
                this.println("    " + String.valueOf(reference.getReferenceType()) + " from=" + String.valueOf(reference.getFromAddress()) + " owner=" + (String)(owner == null ? "none" : owner.getName() + "@" + String.valueOf(owner.getEntryPoint())));
            }
            cursor = found.next();
        }
    }

    protected void run() throws Exception {
        Function function;
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected TU2 XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        long[] vtables = new long[]{2181400708L, 2181363092L, 2181417644L};
        String[] names = new String[]{"Ready Camera", "Pass Camera", "Tackle Camera"};
        LinkedHashSet<Function> owners = new LinkedHashSet<Function>();
        for (int tableIndex = 0; tableIndex < vtables.length; ++tableIndex) {
            long vtable = vtables[tableIndex];
            this.println("VTABLE " + names[tableIndex] + " " + this.hex(vtable) + " typeinfo_preword=" + this.hex(this.word(vtable - 4L)));
            this.printReferences(vtable, owners);
            for (int slot = 0; slot < 18; ++slot) {
                long target = this.word(vtable + (long)slot * 4L);
                this.println(String.format("  +0x%02X %s", slot * 4, this.hex(target)));
                if (slot != 0 && slot != 12 && slot != 13 && slot != 15) continue;
                function = this.currentProgram.getFunctionManager().getFunctionContaining(this.address(target));
                if (function != null) {
                    owners.add(function);
                }
                this.printReferences(target, owners);
            }
            this.printString(names[tableIndex], owners);
        }
        long[] boundedTargets = new long[]{2184679224L, 2184679840L, 2184680880L, 2184678096L, 2184303000L, 2184303544L, 2184303080L, 2185075968L, 2185078040L, 2185079984L};
        for (long target : boundedTargets) {
            function = this.currentProgram.getFunctionManager().getFunctionContaining(this.address(target));
            if (function == null) {
                throw new IllegalStateException("no function at " + this.hex(target));
            }
            owners.add(function);
        }
        this.println("BOUNDED_OWNER_FUNCTIONS count=" + owners.size());
        Iterator object = owners.iterator();
        while (object.hasNext()) {
            Function owner = (Function)object.next();
            this.printFunction(owner);
        }
        this.printRange(2183175416L, 2183176128L, "shared_activation_config_probe");
        this.printRange(2183177368L, 2183178932L, "shared_per_frame_probe");
        this.printRange(2183374592L, 2183374920L, "camera_director_dispatch_probe");
        this.printRange(2183372768L, 2183374016L, "final_camera_controller_probe");
        this.printRange(2184023232L, 2184023584L, "shared_camera_vector_accessors_probe");
        this.printRange(2185074944L, 2185075964L, "tackle_camera_constructor_probe");
        this.printRange(2184302080L, 2184303996L, "pass_camera_probe");
        this.printRange(2185078040L, 2185079980L, "tackle_camera_per_frame_probe");
        this.printRange(2185079984L, 2185080192L, "tackle_camera_activation_probe");
        this.printRange(2184680120L, 2184680876L, "ready_camera_interpolator_full_pdata");
        this.printRange(2184680880L, 2184682804L, "ready_camera_per_frame_full_pdata");
        this.println("BACKBREAKER_CAMERA_VTABLE_PROBE_COMPLETE");
    }
}


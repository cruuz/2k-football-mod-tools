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
import ghidra.program.model.address.AddressSetView;
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
import java.util.List;

public class BackbreakerTU2TackleDefineAudit
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";
    private static final long[] FOCUS_FUNCTIONS = new long[]{2183358400L, 2183358472L, 2183360012L, 2183360588L, 2183363504L, 2183466208L, 2185075552L, 2185078040L, 2185079984L, 2187208752L};

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

    private Function function(long value) {
        Function result = this.currentProgram.getFunctionManager().getFunctionAt(this.address(value));
        if (result == null) {
            result = this.currentProgram.getFunctionManager().getFunctionContaining(this.address(value));
        }
        return result;
    }

    private String owner(long value) {
        Function result = this.function(value);
        if (result == null) {
            return "NONE";
        }
        return result.getName() + "@" + String.valueOf(result.getEntryPoint());
    }

    private Instruction instruction(long value) throws Exception {
        Address cursor = this.address(value);
        Instruction result = this.currentProgram.getListing().getInstructionAt(cursor);
        if (result == null) {
            this.disassemble(cursor);
            result = this.currentProgram.getListing().getInstructionAt(cursor);
        }
        return result;
    }

    private String rendered(long value) throws Exception {
        Instruction item = this.instruction(value);
        return item == null ? "<UNDEFINED_XENON_WORD>" : item.toString().replace('\t', ' ');
    }

    private List<Long> displacement8BAccesses() throws Exception {
        ArrayList<Long> result = new ArrayList<Long>();
        for (MemoryBlock block : this.currentProgram.getMemory().getBlocks()) {
            if (!block.isExecute()) continue;
            long first = block.getStart().getUnsignedOffset();
            long last = block.getEnd().getUnsignedOffset();
            for (long value = first; value <= last - 3L; value += 4L) {
                int base;
                long item;
                try {
                    item = this.word(value);
                }
                catch (Exception ignored) {
                    continue;
                }
                int opcode = (int)(item >>> 26);
                if ((item & 0xFFFFL) != 139L || opcode < 32 || opcode > 55 || (base = (int)(item >>> 16 & 0x1FL)) == 1) continue;
                result.add(value);
            }
        }
        return result;
    }

    private void writeContext(BufferedWriter output, long center, int before, int after) throws Exception {
        output.write("CONTEXT center=" + this.hex(center) + " owner=" + this.owner(center) + "\n");
        for (long value = center - (long)before * 4L; value <= center + (long)after * 4L; value += 4L) {
            if (!this.currentProgram.getMemory().contains(this.address(value))) continue;
            output.write(this.hex(value) + " " + this.bytes(this.address(value), 4) + " " + this.rendered(value));
            if (value == center) {
                output.write("  <==");
            }
            output.write("\n");
        }
        output.write("\n");
    }

    private void writeFunctionAssembly(BufferedWriter output, Function function) throws Exception {
        if (function == null) {
            return;
        }
        AddressSetView body = function.getBody();
        output.write("FUNCTION " + function.getName() + " entry=" + String.valueOf(function.getEntryPoint()) + " min=" + String.valueOf(body.getMinAddress()) + " max=" + String.valueOf(body.getMaxAddress()) + "\n");
        for (Address cursor = body.getMinAddress(); cursor != null && cursor.compareTo(body.getMaxAddress()) <= 0; cursor = cursor.addNoWrap(4L)) {
            if (!body.contains(cursor)) continue;
            long value = cursor.getUnsignedOffset();
            output.write(this.hex(value) + " " + this.bytes(cursor, 4) + " " + this.rendered(value) + "\n");
        }
        output.write("\n");
    }

    private void writeFunctionDecompile(BufferedWriter output, DecompInterface decompiler, Function function) throws Exception {
        if (function == null) {
            return;
        }
        output.write("FUNCTION " + function.getName() + " entry=" + String.valueOf(function.getEntryPoint()) + "\n");
        DecompileResults result = decompiler.decompileFunction(function, 180, this.monitor);
        if (!result.decompileCompleted()) {
            output.write("<DECOMPILE FAILED: " + result.getErrorMessage() + ">\n\n");
            return;
        }
        output.write(result.getDecompiledFunction().getC());
        output.write("\n\n");
    }

    private void writeFacts(BufferedWriter output, List<Long> accesses) throws Exception {
        output.write("Backbreaker TU2 Tackle53 define/flag audit\n");
        output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n\n");
        output.write("PIN define23_policy_table 0x82022595 " + this.bytes(this.address(2181178773L), 1) + "\n");
        output.write("PIN define23_object_table 0x820225EC " + this.bytes(this.address(2181178860L), 2) + "\n");
        output.write("PIN define36_policy_table 0x820225A2 " + this.bytes(this.address(2181178786L), 1) + "\n");
        output.write("PIN define36_object_table 0x82022606 " + this.bytes(this.address(2181178886L), 2) + "\n");
        output.write("PIN tackle_vtable 0x8205CAAC " + this.bytes(this.address(2181417644L), 4) + "\n");
        output.write("PIN tackle_type_store 0x823D9B84 " + this.bytes(this.address(2185075588L), 4) + "\n\n");
        output.write("D_FORM_DISPLACEMENT_0x8B_EXECUTABLE_ACCESSES count=" + accesses.size() + "\n");
        Iterator<Long> iterator = accesses.iterator();
        while (iterator.hasNext()) {
            long value = iterator.next();
            long item = this.word(value);
            int opcode = (int)(item >>> 26);
            int target = (int)(item >>> 21 & 0x1FL);
            int base = (int)(item >>> 16 & 0x1FL);
            output.write("  at=" + this.hex(value) + " word=" + this.hex(item) + " opcode=" + opcode + " rt_rs=r" + target + " base=r" + base + " owner=" + this.owner(value) + " text=" + this.rendered(value) + "\n");
        }
        output.write("\nFOCUS_FUNCTIONS\n");
        for (long value : FOCUS_FUNCTIONS) {
            output.write("  requested=" + this.hex((long)value) + " owner=" + this.owner((long)value) + "\n");
        }
        Function writer = this.function(2187208752L);
        if (writer != null) {
            output.write("\nDIRECT_XREFS_TO_0x825E2830_OWNER entry=" + String.valueOf(writer.getEntryPoint()) + "\n");
            for (Reference reference : this.collectReferencesTo(writer.getEntryPoint())) {
                output.write("  from=" + String.valueOf(reference.getFromAddress()) + " type=" + String.valueOf(reference.getReferenceType()) + "\n");
            }
        }
    }

    private Iterable<Reference> collectReferencesTo(Address target) {
        ArrayList<Reference> result = new ArrayList<Reference>();
        for (Reference reference : this.currentProgram.getReferenceManager().getReferencesTo(target)) {
            result.add(reference);
        }
        return result;
    }

    protected void run() throws Exception {
        String[] args = this.getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: BackbreakerTU2TackleDefineAudit.java OUTPUT_DIRECTORY");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected Backbreaker TU2 XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(directory));
        }
        List<Long> accesses = this.displacement8BAccesses();
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_tackle_define_facts.txt")))) {
            this.writeFacts(output, accesses);
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_tackle_define_flag_contexts.txt")))) {
            for (long value : accesses) {
                this.writeContext(output, value, 10, 18);
            }
        }
        LinkedHashMap<Long, Function> functions = new LinkedHashMap<Long, Function>();
        for (long value : FOCUS_FUNCTIONS) {
            Function item = this.function((long)value);
            if (item == null) continue;
            functions.put(item.getEntryPoint().getUnsignedOffset(), item);
        }
        for (long value : accesses) {
            Function item = this.function(value);
            if (item == null) continue;
            functions.put(item.getEntryPoint().getUnsignedOffset(), item);
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_tackle_define_assembly.txt")))) {
            for (Function item : functions.values()) {
                this.writeFunctionAssembly(output, item);
            }
        }
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(this.currentProgram);
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_tackle_define_decompile.c")))) {
            for (Function item : functions.values()) {
                this.writeFunctionDecompile(output, decompiler, item);
            }
        }
        decompiler.dispose();
        this.println("WROTE " + directory.getAbsolutePath());
    }
}


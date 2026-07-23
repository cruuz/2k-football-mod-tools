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
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.SourceType;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Iterator;

public class BackbreakerCameraDispatchTrace
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4d425702e7cbfeec805e73511cb4b69f";
    private static final Boundary[] BOUNDARIES = new Boundary[]{new Boundary(2183364600L, 2183369984L, "bb_camera_catalog_constructor"), new Boundary(2184650696L, 2184651060L, "bb_qb_camera_constructor"), new Boundary(2183582200L, 2183582384L, "bb_free_flight_camera_constructor"), new Boundary(2184835312L, 2184835496L, "bb_replay_camera_constructor"), new Boundary(2185210256L, 2185210424L, "bb_tv_camera_constructor"), new Boundary(2183156224L, 2183156508L, "bb_ball_lock_camera_constructor")};
    private static final long[][] ANALYSIS_NOP_SUBSTITUTIONS = new long[][]{{2183364820L, 467666804L}, {2183365132L, 335436231L}};
    private static final long[] RETURNING_PROLOGUE_HELPERS = new long[]{2190345104L};

    private Address address(long value) {
        return this.currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xFFFFFFFFL);
    }

    private String hex(Address value) {
        return value == null ? "none" : this.hex(value.getUnsignedOffset());
    }

    private String bytes(Address start, int count) throws Exception {
        byte[] data = new byte[count];
        int read = this.currentProgram.getMemory().getBytes(start, data);
        if (read != count) {
            throw new IllegalStateException("short read at " + this.hex(start));
        }
        StringBuilder output = new StringBuilder();
        for (byte item : data) {
            output.append(String.format("%02X", item & 0xFF));
        }
        return output.toString();
    }

    private Function rebuild(Boundary boundary) throws Exception {
        Function function;
        Address first = this.address(boundary.first);
        Address last = this.address(boundary.last);
        ArrayList<Address> remove = new ArrayList<Address>();
        Function containing = this.currentProgram.getFunctionManager().getFunctionContaining(first);
        if (containing != null) {
            remove.add(containing.getEntryPoint());
        }
        FunctionIterator iterator = this.currentProgram.getFunctionManager().getFunctions(first, true);
        while (iterator.hasNext() && (function = (Function)iterator.next()).getEntryPoint().compareTo(last) <= 0) {
            if (remove.contains(function.getEntryPoint())) continue;
            remove.add(function.getEntryPoint());
        }
        for (Address entry : remove) {
            this.currentProgram.getFunctionManager().removeFunction(entry);
        }
        this.clearListing(first, last);
        Address cursor = first;
        while (cursor.compareTo(last) <= 0) {
            this.disassemble(cursor);
            cursor = cursor.add(4L);
        }
        function = this.currentProgram.getListing().createFunction(boundary.name, first, (AddressSetView)new AddressSet(first, last), SourceType.ANALYSIS);
        if (function == null) {
            throw new IllegalStateException("cannot create " + boundary.name);
        }
        return function;
    }

    private void applyDecompilerRecovery() throws Exception {
        for (long helperAddress : RETURNING_PROLOGUE_HELPERS) {
            Function helper = this.currentProgram.getFunctionManager().getFunctionAt(this.address(helperAddress));
            if (helper == null) {
                throw new IllegalStateException("missing prologue helper " + this.hex(helperAddress));
            }
            helper.setNoReturn(false);
        }
        for (long[] substitution : ANALYSIS_NOP_SUBSTITUTIONS) {
            Address target = this.address(substitution[0]);
            long actual = Integer.toUnsignedLong(this.currentProgram.getMemory().getInt(target));
            if (actual != substitution[1] && actual != 0x60000000L) {
                throw new IllegalStateException("unexpected word at " + this.hex(target) + ": " + this.hex(actual));
            }
            if (actual == 0x60000000L) continue;
            this.clearListing(target, target.add(3L));
            this.currentProgram.getMemory().setBytes(target, new byte[]{96, 0, 0, 0});
        }
    }

    private void writeAssembly(BufferedWriter output, Function function) throws Exception {
        output.write("FUNCTION " + function.getName() + " " + this.hex(function.getEntryPoint()) + ".." + this.hex(function.getBody().getMaxAddress()) + "\n");
        Address cursor = function.getEntryPoint();
        while (cursor.compareTo(function.getBody().getMaxAddress()) <= 0) {
            Instruction instruction = this.currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                output.write(this.hex(cursor) + " " + this.bytes(cursor, 4) + " <UNDEFINED>\n");
            } else {
                ArrayList<String> references = new ArrayList<String>();
                for (Reference reference : instruction.getReferencesFrom()) {
                    references.add(String.valueOf(reference.getReferenceType()) + "->" + this.hex(reference.getToAddress()));
                }
                output.write(this.hex(instruction.getAddress()) + " " + this.bytes(instruction.getAddress(), instruction.getLength()) + " " + instruction.toString().replace('\t', ' ') + (String)(references.isEmpty() ? "" : " refs=" + String.join(";", references)) + "\n");
            }
            cursor = cursor.add(4L);
        }
        output.write("\n");
    }

    protected void run() throws Exception {
        String[] args = this.getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: BackbreakerCameraDispatchTrace.java OUTPUT_DIRECTORY");
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected Backbreaker XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(directory));
        }
        this.applyDecompilerRecovery();
        ArrayList<Function> functions = new ArrayList<Function>();
        for (Boundary boundary : BOUNDARIES) {
            functions.add(this.rebuild(boundary));
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu0_camera_dispatch_assembly.txt")))) {
            output.write("Backbreaker TU0 bounded camera-dispatch assembly\n");
            output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n\n");
            output.write("ANALYSIS_ONLY_RECOVERY\n");
            for (long[] substitution : ANALYSIS_NOP_SUBSTITUTIONS) {
                output.write(this.hex(substitution[0]) + " original=" + this.hex(substitution[1]) + " analysis_word=0x60000000\n");
            }
            output.write("\n");
            Iterator object = functions.iterator();
            while (object.hasNext()) {
                Function function = (Function)object.next();
                this.writeAssembly(output, function);
            }
        }
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(this.currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu0_camera_dispatch_pseudo_c.c")))) {
            output.write("/* Backbreaker TU0 bounded camera-dispatch pseudo-C. */\n\n");
            for (Function function : functions) {
                output.write("/* " + function.getName() + " " + this.hex(function.getEntryPoint()) + " */\n");
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
        decompiler.dispose();
        this.println("BACKBREAKER_CAMERA_DISPATCH_TRACE_COMPLETE output=" + String.valueOf(directory));
    }

    private static final class Boundary {
        final long first;
        final long last;
        final String name;

        Boundary(long first, long last, String name) {
            this.first = first;
            this.last = last;
            this.name = name;
        }
    }
}


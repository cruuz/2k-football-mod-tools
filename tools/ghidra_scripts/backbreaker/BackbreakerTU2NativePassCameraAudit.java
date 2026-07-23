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
import ghidra.program.model.symbol.Reference;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;

public class BackbreakerTU2NativePassCameraAudit
extends GhidraScript {
    private static final String EXPECTED_MD5 = "4260a495ab98c6c3608b801628ea2200";
    private static final Camera[] CAMERAS = new Camera[]{new Camera("Bomb", 4, 2183157624L, 2181156644L), new Camera("BallLock", 5, 2183159272L, 2181156756L), new Camera("Block", 6, 2183339408L, 2181177436L), new Camera("Bullet", 7, 2183351184L, 2181178380L), new Camera("Catch", 8, 2183377912L, 2181180116L), new Camera("Chase", 9, 2183388312L, 2181180564L), new Camera("MultiplayerBall", 37, 2184152728L, 2181338612L), new Camera("Pass", 39, 2184302232L, 2181363092L), new Camera("WideReceiver", 58, 2185278976L, 2181433476L)};
    private static final Range[] RAW_RANGES = new Range[]{new Range("Bomb_constructor_full", 2183157624L, 2183158020L), new Range("Bomb_activation_full", 2183158104L, 2183158476L), new Range("Bomb_update_full", 2183158480L, 2183159168L), new Range("BallLock_constructor_full", 2183159272L, 2183159556L), new Range("BallLock_update_full", 2183159640L, 2183161812L), new Range("Block_constructor_full", 2183339408L, 2183339908L), new Range("Block_activation_full", 2183339992L, 2183340252L), new Range("Block_update_full", 2183340256L, 2183342304L), new Range("Bullet_constructor_full", 2183351184L, 2183351524L), new Range("Bullet_activation_full", 2183351608L, 2183351764L), new Range("Bullet_update_full", 2183352712L, 2183354664L), new Range("Catch_constructor_full", 2183377912L, 2183378184L), new Range("Catch_update_full", 2183378272L, 2183378508L), new Range("Chase_constructor_full", 2183388312L, 2183388480L), new Range("Chase_activation_full", 2183388488L, 2183388644L), new Range("Chase_update_full", 2183388648L, 2183389052L), new Range("MultiplayerBall_constructor_full", 2184152728L, 2184152996L), new Range("MultiplayerBall_update_full", 2184153080L, 2184153228L), new Range("Pass_constructor_full", 2184302232L, 2184302996L), new Range("Pass_activation_full", 2184303080L, 2184303540L), new Range("Pass_update_and_helpers_full", 2184303544L, 2184307156L), new Range("WideReceiver_constructor_full", 2185278976L, 2185279284L), new Range("WideReceiver_activation_full", 2185279368L, 2185279628L), new Range("WideReceiver_update_full", 2185279632L, 2185279876L), new Range("shared_transform_offset", 2183179504L, 2183179559L), new Range("shared_camera_target_builder", 2183179560L, 2183179708L), new Range("camera_base_constructor", 2183176256L, 2183177172L), new Range("camera_generic_context_setter", 2183178936L, 2183179500L), new Range("Bomb_scalar_helper", 2183157272L, 2183157383L), new Range("Bullet_FOV_provider", 2183357992L, 2183358031L), new Range("Pass_attachment_resolver", 2185266816L, 2185266943L), new Range("Pass_selector", 2185266464L, 2185266559L), new Range("Pass_context_scalar_getter", 2184430480L, 2184430639L), new Range("Pass_context_state_test", 2184479424L, 2184479615L), new Range("Pass_controller_flag_helper", 2184066896L, 2184067055L), new Range("WideReceiver_target_smoother", 2185278416L, 2185278972L)};

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

    private Function function(long entry) {
        Function result = this.currentProgram.getFunctionManager().getFunctionAt(this.address(entry));
        if (result == null) {
            result = this.currentProgram.getFunctionManager().getFunctionContaining(this.address(entry));
        }
        return result;
    }

    private void validate() throws Exception {
        if (!EXPECTED_MD5.equalsIgnoreCase(this.currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected Backbreaker TU2 XEX MD5 " + this.currentProgram.getExecutableMD5());
        }
        for (Camera camera : CAMERAS) {
            if (this.word(camera.vtable + 4L) != 2183177368L) {
                throw new IllegalStateException(camera.name + " vtable lacks shared update wrapper");
            }
            if (this.word(camera.vtable + 68L) == 2183175312L) continue;
            throw new IllegalStateException(camera.name + " vtable lacks +0x104 FOV getter");
        }
    }

    private void writeFunctionAssembly(BufferedWriter output, String label, long entry) throws Exception {
        Function function = this.function(entry);
        if (function == null) {
            output.write("FUNCTION " + label + " " + this.hex(entry) + " owner=NONE\n\n");
            return;
        }
        AddressSetView body = function.getBody();
        output.write("FUNCTION " + label + " requested=" + this.hex(entry) + " entry=" + String.valueOf(function.getEntryPoint()) + " min=" + String.valueOf(body.getMinAddress()) + " max=" + String.valueOf(body.getMaxAddress()) + "\n");
        for (Address cursor = body.getMinAddress(); cursor != null && cursor.compareTo(body.getMaxAddress()) <= 0; cursor = cursor.addNoWrap(4L)) {
            Instruction instruction;
            if (!body.contains(cursor)) continue;
            if (this.currentProgram.getListing().getInstructionAt(cursor) == null) {
                this.disassemble(cursor);
            }
            String rendered = (instruction = this.currentProgram.getListing().getInstructionAt(cursor)) == null ? "<UNDEFINED_XENON_WORD>" : instruction.toString().replace('\t', ' ');
            ArrayList<String> references = new ArrayList<String>();
            if (instruction != null) {
                for (Reference reference : instruction.getReferencesFrom()) {
                    references.add(String.valueOf(reference.getReferenceType()) + "->" + String.valueOf(reference.getToAddress()));
                }
            }
            output.write(this.hex(cursor.getUnsignedOffset()) + " " + this.bytes(cursor, 4) + " " + rendered + (String)(references.isEmpty() ? "" : " refs=" + String.join(";", references)) + "\n");
        }
        output.write("\n");
    }

    private void writeRawRange(BufferedWriter output, Range range) throws Exception {
        output.write("RANGE " + range.name + " " + this.hex(range.first) + ".." + this.hex(range.last) + "\n");
        for (long value = range.first; value <= range.last; value += 4L) {
            Instruction instruction;
            Address cursor = this.address(value);
            if (this.currentProgram.getListing().getInstructionAt(cursor) == null) {
                this.disassemble(cursor);
            }
            String rendered = (instruction = this.currentProgram.getListing().getInstructionAt(cursor)) == null ? "<UNDEFINED_XENON_WORD>" : instruction.toString().replace('\t', ' ');
            output.write(this.hex(value) + " " + this.bytes(cursor, 4) + " " + rendered + "\n");
        }
        output.write("\n");
    }

    private void writeDecompile(BufferedWriter output, DecompInterface decompiler, String label, long entry) throws Exception {
        Function function = this.function(entry);
        output.write("FUNCTION " + label + " requested=" + this.hex(entry) + "\n");
        if (function == null) {
            output.write("<NO FUNCTION>\n\n");
            return;
        }
        DecompileResults result = decompiler.decompileFunction(function, 120, this.monitor);
        if (!result.decompileCompleted()) {
            output.write("<DECOMPILE FAILED: " + result.getErrorMessage() + ">\n\n");
            return;
        }
        output.write(result.getDecompiledFunction().getC());
        output.write("\n\n");
    }

    private void writeFacts(BufferedWriter output) throws Exception {
        output.write("Backbreaker TU2 native pass/run camera audit\n");
        output.write("source_xex_md5=" + this.currentProgram.getExecutableMD5() + "\n\n");
        for (Camera camera : CAMERAS) {
            output.write("CAMERA " + camera.name + " type=" + camera.type + " ctor=" + this.hex(camera.ctor) + " vtable=" + this.hex(camera.vtable) + "\n");
            for (int slot = 0; slot <= 68; slot += 4) {
                output.write(String.format("  +0x%02X %s\n", slot, this.hex(this.word(camera.vtable + (long)slot))));
            }
            output.write("\n");
        }
        output.write("CAVE start=0x8297E454 end_exclusive=0x8297E600 bytes=428\n");
        output.write("  predecessor=0x8297E450 word=0x4E800020\n");
        output.write("  successor=0x8297E600 word=0xFBC1FFF0\n");
    }

    protected void run() throws Exception {
        String[] args = this.getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: BackbreakerTU2NativePassCameraAudit.java OUTPUT_DIRECTORY");
        }
        this.validate();
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + String.valueOf(directory));
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_native_pass_camera_facts.txt")))) {
            this.writeFacts(output);
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_native_pass_camera_assembly.txt")))) {
            for (Camera camera : CAMERAS) {
                this.writeFunctionAssembly(output, camera.name + "_constructor", camera.ctor);
                this.writeFunctionAssembly(output, camera.name + "_update", this.word(camera.vtable + 48L));
                this.writeFunctionAssembly(output, camera.name + "_activation", this.word(camera.vtable + 52L));
            }
        }
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_native_pass_camera_raw_ranges.txt")))) {
            for (Range range : RAW_RANGES) {
                this.writeRawRange(output, range);
            }
        }
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(this.currentProgram);
        try (BufferedWriter output = new BufferedWriter(new FileWriter(new File(directory, "tu2_native_pass_camera_decompile.c")))) {
            for (Camera camera : CAMERAS) {
                this.writeDecompile(output, decompiler, camera.name + "_constructor", camera.ctor);
                this.writeDecompile(output, decompiler, camera.name + "_update", this.word(camera.vtable + 48L));
                this.writeDecompile(output, decompiler, camera.name + "_activation", this.word(camera.vtable + 52L));
            }
        }
        decompiler.dispose();
        this.println("WROTE " + directory.getAbsolutePath());
    }

    private static final class Camera {
        final String name;
        final int type;
        final long ctor;
        final long vtable;

        Camera(String name, int type, long ctor, long vtable) {
            this.name = name;
            this.type = type;
            this.ctor = ctor;
            this.vtable = vtable;
        }
    }

    private static final class Range {
        final String name;
        final long first;
        final long last;

        Range(String name, long first, long last) {
            this.name = name;
            this.first = first;
            this.last = last;
        }
    }
}


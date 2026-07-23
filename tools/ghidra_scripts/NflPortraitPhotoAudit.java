// Read-only bounded ownership trace for NFL 2K5 portrait/photo strings.
// @category VisualConcepts.NFL

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class NflPortraitPhotoAudit extends GhidraScript {
    private static final String NFL_MD5 = "444064a9ec984dd29d2c05a43f5c96e8";
    private static final String[] TEXT = {
        "Portrait.iff", "portrait.iff", "portrait%d", "portrait.cdf",
        "nophoto", "z_playerPhoto", "dc_playercard_photo_player2",
        "WRAPUP_PORTRAIT", "show_multi_player_photo_focus",
        "position_photos_qb", "player_photo_a1", "player_photo_b1",
        "team_photo", "team_photo_p01", "foam_finger", "sign_street",
        "collection_00", "%s_%02d", "%02u_%s", "%02u_%s_%02d"
    };
    private static final long[] FOCUS = {
        0x000E7140L, 0x000E7170L, 0x000E71E0L,
        0x0015EF00L, 0x0015F020L, 0x0015F0B0L
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private String owner(Function function) {
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" + function.getName();
    }

    private String section(Address value) {
        MemoryBlock block = currentProgram.getMemory().getBlock(value);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private byte[] utf16z(String value) {
        byte[] raw = (value + "\0").getBytes(StandardCharsets.UTF_16LE);
        return raw;
    }

    private List<Address> find(byte[] needle) throws Exception {
        List<Address> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                result.add(hit);
                cursor = hit.add(1);
            }
        }
        result.sort(Comparator.naturalOrder());
        return result;
    }

    private byte[] pointerBytes(long value) {
        return new byte[] {(byte)value, (byte)(value >>> 8),
            (byte)(value >>> 16), (byte)(value >>> 24)};
    }

    private Function ensureFunction(long value) throws Exception {
        Address entry = address(value);
        Function function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function != null) return function;
        disassemble(entry);
        createFunction(entry, null);
        function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function == null) throw new IllegalStateException("cannot create " + hex(value));
        return function;
    }

    private List<String> references(Address target, Set<Function> functions) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function function = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            if (function != null) functions.add(function);
            values.add(hex(reference.getFromAddress().getUnsignedOffset()) + "(" +
                owner(function) + "," + reference.getReferenceType() + ")");
        }
        Collections.sort(values);
        return values;
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException(
            "usage: NflPortraitPhotoAudit.java OUTPUT_DIRECTORY");
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!NFL_MD5.equals(md5)) throw new IllegalStateException("unexpected NFL MD5 " + md5);
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }
        File traceFile = new File(directory, "nfl_portrait_photo_audit_trace.txt");
        File pseudoFile = new File(directory, "nfl_portrait_photo_audit_pseudo_c.c");
        Set<Function> functions = new LinkedHashSet<>();
        try (BufferedWriter output = new BufferedWriter(new FileWriter(traceFile))) {
            output.write("NFL 2K5 portrait/photo bounded read-only trace\n");
            output.write("MD5 " + md5 + "\n\n");
            for (String value : TEXT) {
                List<Address> hits = find(utf16z(value));
                output.write("TEXT " + value + " hits=" + hits.size() + "\n");
                for (Address hit : hits) {
                    List<String> direct = references(hit, functions);
                    List<Address> pointers = find(pointerBytes(hit.getUnsignedOffset()));
                    output.write("  HIT " + hex(hit.getUnsignedOffset()) + " section=" +
                        section(hit) + " refs=" + String.join(";", direct) + "\n");
                    for (Address pointer : pointers) {
                        Function function = currentProgram.getFunctionManager().getFunctionContaining(pointer);
                        if (function != null) functions.add(function);
                        output.write("    PTR " + hex(pointer.getUnsignedOffset()) + " section=" +
                            section(pointer) + " owner=" + owner(function) + " refs=" +
                            String.join(";", references(pointer, functions)) + "\n");
                    }
                }
                output.write("\n");
            }
            output.write("FOCUS_FUNCTIONS\n");
            for (long value : FOCUS) {
                Function function = ensureFunction(value);
                functions.add(function);
                List<String> incoming = references(function.getEntryPoint(), functions);
                output.write("  " + owner(function) + " incoming=" +
                    String.join(";", incoming) + "\n");
            }
            output.write("\n");
            List<Function> ordered = new ArrayList<>(functions);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));
            output.write("OWNER_COUNT " + ordered.size() + "\n\n");
            for (Function function : ordered) {
                output.write("FUNCTION " + owner(function) + " body=" + function.getBody() + "\n");
                InstructionIterator iterator = currentProgram.getListing().getInstructions(
                    function.getBody(), true);
                while (iterator.hasNext()) {
                    Instruction instruction = iterator.next();
                    output.write(hex(instruction.getAddress().getUnsignedOffset()) + " " +
                        instruction.toString() + "\n");
                }
                output.write("\n");
            }
        }
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (BufferedWriter output = new BufferedWriter(new FileWriter(pseudoFile))) {
            List<Function> ordered = new ArrayList<>(functions);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));
            for (Function function : ordered) {
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                output.write("/* " + owner(function) + " body=" + function.getBody() + " */\n");
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                } else {
                    output.write("/* DECOMPILE FAILED: " + result.getErrorMessage() + " */\n");
                }
                output.write("\n\n");
            }
        } finally {
            decompiler.dispose();
        }
        println("Wrote " + traceFile + " and " + pseudoFile);
    }
}

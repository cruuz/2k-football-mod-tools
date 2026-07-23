// Emit read-only APF 2K8 evidence for player_shadow surface/material ownership.
// @category Xbox360.APF2K8

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfPlayerShadowSurfaceMaterialTrace extends GhidraScript {
    private static final String EXPECTED_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    // These spans are deliberately narrow.  Some renderer bodies are displaced
    // from the tiny .pdata functions Ghidra created, so paired RAW32 is the
    // authority for those spans and pseudo-C below states only proved fields.
    private static final long[][] RAW_RANGES = {
        { 0x849CF280L, 0x849CF340L }, // instance -> node/material-array wrapper
        { 0x84AA4728L, 0x84AA4774L }, // exact SCNE/player_shadow lookup/owner
        { 0x84B107A4L, 0x84B108E8L }, // draw +0x20 -> material slot * 0xf0
        { 0x84B14640L, 0x84B149F8L }, // vertex/pixel shader selection
        { 0x84B14DA0L, 0x84B14F80L }, // one texture/sampler fetch binding
        { 0x84B14F80L, 0x84B14FF4L }, // eight shader texture-map entries
        { 0x84B15488L, 0x84B15B80L }, // material apply and texture records
        { 0x84B47790L, 0x84B47834L }, // render caller -> material apply
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String addr(Address value) {
        return value == null ? "" : hex(value.getUnsignedOffset());
    }

    private String functionName(Function function) {
        return function == null ? "none" : addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<String> referencesTo(long target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(address(target));
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(reference.getFromAddress());
            result.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private String rangeSha256(long first, long afterLast) throws Exception {
        byte[] bytes = new byte[(int)(afterLast - first)];
        currentProgram.getMemory().getBytes(address(first), bytes);
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder result = new StringBuilder();
        for (byte value : digest) result.append(String.format("%02x", value & 0xff));
        return result.toString();
    }

    private void writeRawRange(BufferedWriter output, long first, long afterLast) throws Exception {
        output.write("RAW_RANGE " + hex(first) + " " + hex(afterLast) + " bytes=" +
            (afterLast - first) + " sha256=" + rangeSha256(first, afterLast) + "\n");
        Memory memory = currentProgram.getMemory();
        for (long value = first; value < afterLast; value += 4) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            output.write("RAW32 " + hex(value) + " " +
                hex(Integer.toUnsignedLong(memory.getInt(cursor))) + "\n");
            output.write("GHIDRA " + hex(value) + " " +
                (instruction == null ? "<no instruction>" : instruction.toString()) + "\n");
        }
    }

    private String decompile(long entry, DecompInterface decompiler) {
        Function function = currentProgram.getFunctionManager().getFunctionAt(address(entry));
        if (function == null) {
            return "// PORTME at " + hex(entry) + ": Ghidra has no function at this entry.\n";
        }
        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
        if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
            return "/* " + functionName(function) + " */\n" + result.getDecompiledFunction().getC();
        }
        String reason = result.isTimedOut() ? "timed out" : result.getErrorMessage();
        if (reason == null || reason.isEmpty()) reason = "no diagnostic";
        return "// PORTME at " + hex(entry) + ": Ghidra decompile failed: " +
            reason.replace('\n', ' ').replace('\r', ' ') + "\n";
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfPlayerShadowSurfaceMaterialTrace.java OUTPUT_DIRECTORY");
        }
        String md5 = currentProgram.getExecutableMD5();
        if (!EXPECTED_MD5.equalsIgnoreCase(md5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + md5);
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        File traceFile = new File(directory, "player_shadow_surface_material_trace.txt");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(traceFile))) {
            output.write("APF 2K8 selected SCNE/player_shadow surface/material trace\n");
            output.write("Program MD5: " + md5 + "\n");
            output.write("Program name: " + currentProgram.getName() + "\n");
            output.write("Program language: " + currentProgram.getLanguageID() + "\n\n");
            output.write("REFERENCES\n");
            long[] targets = {
                0x849CF280L, 0x84AA4728L, 0x84B10630L, 0x84B10B98L,
                0x84B14640L, 0x84B147A0L, 0x84B149F8L, 0x84B14DA0L,
                0x84B14F80L, 0x84B15488L, 0x84B28EA0L, 0x84B47790L,
            };
            for (long target : targets) {
                output.write("TARGET " + hex(target) + " refs=" +
                    String.join(";", referencesTo(target)) + "\n");
            }
            output.write("\nRAW_INSTRUCTIONS\n");
            for (long[] range : RAW_RANGES) writeRawRange(output, range[0], range[1]);
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory, "player_shadow_surface_material_pseudo_c.c");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(pseudoFile))) {
            output.write("/* APF 2K8 selected SCNE/player_shadow surface/material pseudo-C. */\n");
            output.write("/* Paired RAW32 is authoritative for displaced renderer bodies. */\n\n");
            output.write("/* Recovered contract from 0x84B107A4:\n");
            output.write("   draw = scene_draw_table[draw_index];\n");
            output.write("   material = instance_material_base + draw->material_slot_at_0x20 * 0xf0;\n");
            output.write("   The selected draw record stores material_slot_at_0x20 = 0. */\n\n");
            output.write("/* Recovered contract from 0x84B15488:\n");
            output.write("   select vertex shader from material+0x0c and pixel shader from material+0x10;\n");
            output.write("   if pixel_shader->texture_map_at_0x8c exists, iterate eight entries;\n");
            output.write("   each mapping byte n != 8 selects material texture record\n");
            output.write("     material + 0x50 + 0x14*n;\n");
            output.write("   record+0 is the texture object unless record+0x0c has its high bit set;\n");
            output.write("   0x84B14DA0 binds the selected texture/sampler fetch state.\n");
            output.write("   This proves indirection and record layout, not the live resource identity. */\n\n");
            output.write("/* Recovered contract from 0x849CF280:\n");
            output.write("   0x84B10B98(instance+0x68, instance+0x74, instance+0x7c,\n");
            output.write("              instance+0x80, 0);\n");
            output.write("   Therefore the material array is instance-owned and external to the\n");
            output.write("   selected SCNE node bytes. */\n\n");
            output.write(decompile(0x849CF280L, decompiler));
            output.write("\n\n");
            output.write(decompile(0x84B47790L, decompiler));
            output.write("\n\n");
            output.write("// PORTME at 0x84B15488: capture the selected player_shadow instance material array at instance+0x7c and pixel-shader mapping at shader+0x8c to map BaseMap, NormalMap, GlossOcclusionMap, GroundShadowSampler, and SpecularLightmapSampler to concrete TXTR objects or render targets.\n");
            output.write("// PORTME at 0x84B14DA0 -> 0x84B28EA0: name and prove the exact Xenos sampler filter/address bitfields from runtime material texture record +0x0c and adjacent words before recreating sampler state.\n");
            output.write("// PORTME at 0x84AA4728: no static TXTR ID occurs in selected SCNE/player_shadow; do not assign name-only global.iff texture candidates without a live pointer trace.\n");
        } finally {
            decompiler.dispose();
        }
        println("APF_PLAYER_SHADOW_SURFACE_MATERIAL_TRACE_COMPLETE ranges=" + RAW_RANGES.length);
    }
}

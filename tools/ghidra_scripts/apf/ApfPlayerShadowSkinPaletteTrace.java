// Emit read-only APF 2K8 evidence for the selected player_shadow skin path.
// @category Xbox360.APF2K8

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class ApfPlayerShadowSkinPaletteTrace extends GhidraScript {
    private static final String EXPECTED_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    // Only instruction-proved spans in the selected sample -> current-global ->
    // inverse-bind palette -> render-packet path are retained here.
    private static final long[][] RAW_RANGES = {
        { 0x84A11B58L, 0x84A11D88L }, // selected sampler through current globals
        { 0x84A12EF0L, 0x84A130E0L }, // slot current/local matrix ownership
        { 0x84AA4288L, 0x84AA4348L }, // hierarchy wrapper and postprocess
        { 0x84AA4728L, 0x84AA4774L }, // exact player_shadow resource assignment
        { 0x84B0E7F0L, 0x84B0E8C0L }, // exact inverse-bind palette builder
        { 0x84B0FA88L, 0x84B0FBF4L }, // exact current-global hierarchy builder
        { 0x84B10438L, 0x84B1054CL }, // palette descriptor allocation and builder call
        { 0x84B10630L, 0x84B10994L }, // palette descriptor into queued packet +0x28
        { 0x84B10998L, 0x84B10B48L }, // alternate queue path, same packet +0x28
        { 0x84B10B48L, 0x84B10BE4L }, // public palette-build/queue wrappers
        { 0x84B24C88L, 0x84B24CE0L }, // constant-upload command callback
        { 0x84B27510L, 0x84B27AD0L }, // exact descriptor/constant upload helper
        { 0x84B27AD0L, 0x84B27B78L }, // exact queued vertex-stream setup helper
        { 0x84B2BDD0L, 0x84B2BF6CL }, // vertex-declaration state transition
        { 0x84B2D4A8L, 0x84B2D604L }, // draw consumer loading queued packet +0x28
    };

    private static final long[] FOCUSED_FUNCTIONS = {
        0x84A11B58L, 0x84A12EF0L, 0x84AA4288L, 0x84AA42A8L,
        0x84B0E7F0L, 0x84B0FA88L, 0x84B10438L, 0x84B10630L,
        0x84B10998L, 0x84B10B48L, 0x84B10B98L, 0x84B24C88L,
        0x84B27510L, 0x84B27AD0L, 0x84B2BDD0L, 0x84B2D4A8L,
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

    private Function createBody(long start, long end, String name) throws Exception {
        Address first = address(start);
        Address last = address(end);
        for (Address cursor = first; cursor.compareTo(last) <= 0; cursor = cursor.add(4)) {
            if (currentProgram.getListing().getInstructionAt(cursor) == null) disassemble(cursor);
        }
        Function function = currentProgram.getFunctionManager().getFunctionAt(first);
        if (function != null) return function;
        function = currentProgram.getFunctionManager().getFunctionContaining(first);
        if (function != null) return function;
        return currentProgram.getListing().createFunction(
            name, first, new AddressSet(first, last), SourceType.ANALYSIS);
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
            long raw = Integer.toUnsignedLong(memory.getInt(cursor));
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            output.write("RAW32 " + hex(value) + " " + hex(raw) + "\n");
            output.write("GHIDRA " + hex(value) + " " +
                (instruction == null ? "<no instruction>" : instruction.toString()) + "\n");
        }
    }

    private String safeReason(DecompileResults result) {
        String reason = result == null ? "null result" :
            (result.isTimedOut() ? "timed out" : result.getErrorMessage());
        if (reason == null || reason.isEmpty()) reason = "no diagnostic";
        return reason.replace('\n', ' ').replace('\r', ' ');
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfPlayerShadowSkinPaletteTrace.java OUTPUT_DIRECTORY");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!EXPECTED_MD5.equalsIgnoreCase(executableMd5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + executableMd5);
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        Set<Function> functions = new LinkedHashSet<>();
        for (long value : FOCUSED_FUNCTIONS) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
            if (function != null) functions.add(function);
        }
        Function consumer = createBody(0x84A11B58L, 0x84A11D87L,
            "PlayerShadowSampleHierarchy_0x84A11B58");
        if (consumer != null) functions.add(consumer);
        Function update = createBody(0x84A12EF0L, 0x84A130DFL,
            "FrontendShadowSlotUpdate_0x84A12EF0");
        if (update != null) functions.add(update);
        Function palette = createBody(0x84B0E7F0L, 0x84B0E8BCL,
            "BuildSkinPalette_0x84B0E7F0");
        if (palette != null) functions.add(palette);
        Function globals = createBody(0x84B0FA88L, 0x84B0FBF0L,
            "BuildCurrentGlobals_0x84B0FA88");
        if (globals != null) functions.add(globals);
        Function allocation = createBody(0x84B10438L, 0x84B10548L,
            "AllocateAndBuildSkinPalette_0x84B10438");
        if (allocation != null) functions.add(allocation);
        Function queue = createBody(0x84B10630L, 0x84B10990L,
            "QueueSceneDrawWithPalette_0x84B10630");
        if (queue != null) functions.add(queue);
        Function alternateQueue = createBody(0x84B10998L, 0x84B10B44L,
            "QueueSceneDrawWithPaletteAlternate_0x84B10998");
        if (alternateQueue != null) functions.add(alternateQueue);
        Function wrapper = createBody(0x84B10B48L, 0x84B10B90L,
            "BuildPaletteAndQueueScene_0x84B10B48");
        if (wrapper != null) functions.add(wrapper);
        Function upload = currentProgram.getFunctionManager().getFunctionAt(address(0x84B27510L));
        if (upload != null) functions.add(upload);
        Function uploadCallback = currentProgram.getFunctionManager().getFunctionAt(address(0x84B24C88L));
        if (uploadCallback != null) functions.add(uploadCallback);
        Function streams = currentProgram.getFunctionManager().getFunctionAt(address(0x84B27AD0L));
        if (streams != null) functions.add(streams);
        Function shaderState = currentProgram.getFunctionManager().getFunctionAt(address(0x84B2BDD0L));
        if (shaderState != null) functions.add(shaderState);
        Function draw = createBody(0x84B2D4A8L, 0x84B2D600L,
            "ConsumeSceneDrawPacket_0x84B2D4A8");
        if (draw != null) functions.add(draw);

        File traceFile = new File(directory, "player_shadow_skin_palette_trace.txt");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(traceFile))) {
            output.write("APF 2K8 selected SCNE/player_shadow skin-palette trace\n");
            output.write("Program MD5: " + executableMd5 + "\n");
            output.write("Program name: " + currentProgram.getName() + "\n");
            output.write("Program language: " + currentProgram.getLanguageID() + "\n\n");

            output.write("REFERENCES\n");
            long[] targets = {
                0x84A11B58L, 0x84A12EF0L, 0x84AA4288L,
                0x84AA4728L, 0x84B0E7F0L, 0x84B0FA88L,
                0x84B10438L, 0x84B10630L, 0x84B10998L,
                0x84B10B48L, 0x84B10B98L, 0x84B24C88L,
                0x84B27510L, 0x84B27AD0L, 0x84B2BDD0L, 0x84B2D4A8L,
                0x851FFD80L, 0x8522E170L,
            };
            for (long target : targets) {
                output.write("TARGET " + hex(target) + " refs=" +
                    String.join(";", referencesTo(target)) + "\n");
            }
            output.write("\nRAW_INSTRUCTIONS\n");
            for (long[] range : RAW_RANGES) writeRawRange(output, range[0], range[1]);
        }

        List<Function> sorted = new ArrayList<>(functions);
        sorted.sort(Comparator.comparing(Function::getEntryPoint));
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory, "player_shadow_skin_palette_focused_pseudo_c.c");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(pseudoFile))) {
            output.write("/* APF 2K8 selected SCNE/player_shadow skin-palette pseudo-C. */\n");
            output.write("/* Paired RAW32 is authoritative for VMX128 and displaced .pdata bodies. */\n\n");
            output.write("/* Recovered contract from 0x84B0E7F0:\n");
            output.write("   for joint j in [0, scene->count):\n");
            output.write("     b = scene->hierarchy[j].bind_global_xyz;\n");
            output.write("     M = current_global[j];\n");
            output.write("     skin_row = T(-b) * M;\n");
            output.write("     palette[j*3+0..2] = first three columns of skin_row;\n");
            output.write("   The loop advances hierarchy by 0x30, M by 0x40, and output by 0x30;\n");
            output.write("   therefore palette order is direct hierarchy order with no remap. */\n\n");
            for (Function function : sorted) {
                output.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                } else {
                    output.write("// PORTME at " + addr(function.getEntryPoint()) +
                        ": Ghidra decompile failed: " + safeReason(result) + "\n");
                }
                output.write("\n\n");
            }
            output.write("/* 0x84B10438 emits an E3000000/count/48/data descriptor and calls\n");
            output.write("   0x84B0E7F0. 0x84B10714 and 0x84B10A58 store that descriptor at\n");
            output.write("   queued draw packet +0x28; 0x84B2D4EC loads packet +0x28 and calls\n");
            output.write("   generic descriptor uploader 0x84B27510. The E3000000 descriptor supplies\n");
            output.write("   count=21, width=3 float4, stride=48, and the direct palette pointer. */\n");
            output.write("// PORTME at 0x84B24C88 -> 0x84BA45B8: assign the official XDK/Xenos symbol name to the final constant-write helper; the direct 63-float4 data/count handoff is instruction-proved.\n");
            output.write("// PORTME before 0x84B27AD0: find the earlier GPU-buffer creation instruction that converts SCNE stream flag 0x40000000 to Xenos k8in32. 0x84B27AD0 binds the resulting stream stride/pointer but does not read that flag. The exported one-hot JOINTS/WEIGHTS result is invariant across the three live shader lanes.\n");
        } finally {
            decompiler.dispose();
        }
        println("APF_PLAYER_SHADOW_SKIN_PALETTE_TRACE_COMPLETE functions=" + sorted.size());
    }
}

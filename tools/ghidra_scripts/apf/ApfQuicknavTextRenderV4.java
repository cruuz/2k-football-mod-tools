// Emit exact read-only evidence from APF quicknav label providers into the text backend.
// @category VisualConcepts.Menu

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
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
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfQuicknavTextRenderV4 extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final long[][] RANGES = {
        {0x84692918L, 0x846929F4L}, // generic render-state application.
        {0x846929F8L, 0x84692B0CL}, // generic material/style preparation.
        {0x84692B10L, 0x84692BD0L}, // active run-string width query.
        {0x84692BE0L, 0x84693194L}, // generic run renderer; no provider-buffer read.
        {0x84693198L, 0x84693220L}, // proposed output handoff; incoming r4 is discarded.
        {0x84693288L, 0x8469337CL}, // render-run state copier/finalizer precursor.
        {0x84693380L, 0x846933BCL}, // run state finalizer.
        {0x846E64B0L, 0x846E64C0L}, // active string-object to UTF-16 scratch adapter.
        {0x846E64C0L, 0x846E66F0L}, // markup/string callback dispatcher.
        {0x846E6E58L, 0x846E6EB8L}, // normal font/string measurement wrapper.
        {0x846E6EB8L, 0x846E6F0CL}, // generic render-state submission candidate.
        {0x846E90D8L, 0x846E91B8L}, // text positioning/measurement helper.
        {0x846E91B8L, 0x846E91FCL}, // generic scalar/layout helper.
        {0x846E9360L, 0x846E9368L}, // constant-return helper used by special material.
        {0x846E9368L, 0x846E9510L}, // UTF-16 width/classification walk.
        {0x846E9510L, 0x846EA134L}, // first lower text/glyph render backend.
        {0x846EA138L, 0x846EAC74L}, // second lower text/glyph render backend.
        {0x846EAC78L, 0x846EAEB0L}, // text render-state wrapper into 0x846E9510.
        {0x846EAEB0L, 0x846EAF1CL}, // generic repeated-run draw wrapper.
        {0x846EB080L, 0x846EB314L}, // text wrapper into 0x846EA138.
        {0x846EB318L, 0x846EB33CL}, // generic renderer property query wrapper.
        {0x846EB3A8L, 0x846EB41CL}, // generic repeated-run draw wrapper.
        {0x846EEFD0L, 0x846EF1D0L}, // type-0 post-draw callback/material path.
        {0x846EF1D0L, 0x846EF634L}, // type-0 layout record draw/text backend.
        {0x846EF638L, 0x846EF7A0L}, // recursive layout traversal and type dispatch.
        {0x846F4E38L, 0x846F5054L}, // template_quicknav setup callback candidate.
        {0x846F5058L, 0x846F5194L}, // template_quicknav update/teardown callback candidate.
        {0x846F5198L, 0x846F52B4L}, // proved quicknav label provider.
        {0x84762610L, 0x8476284CL}, // reference-counted string to UTF-16 adapter.
        {0x847628E8L, 0x847629A8L}, // reference-counted string assignment.
        {0x84B1B700L, 0x84B1B794L}, // dynamic vertex writer begin.
        {0x84B1B848L, 0x84B1B970L}, // vertex attributes, vertex writes, finalization.
        {0x84B2AE80L, 0x84B2AEC8L}, // GPU command-buffer packet writer.
        {0x84B2D400L, 0x84B2D4A4L}, // command-buffer draw commit.
        {0x84B32850L, 0x84B32980L}, // alternate render queue/command path.
        {0x84B43498L, 0x84B434DCL}, // bounded UTF-16 copy.
        {0x84B47838L, 0x84B478F0L}, // render queue/command submission path.
        {0x84B48470L, 0x84B48520L}, // dynamic vertex writer allocation/setup.
        {0x84B48520L, 0x84B485E0L}, // dynamic vertex writer final submit.
        {0x84B646C0L, 0x84B64780L}, // formatter string argument writer.
        {0x84B65B00L, 0x84B65B70L}  // bounded UTF-16 formatter wrapper.
    };

    private static final long[] FOCUS = {
        0x84692918L, 0x846929F8L, 0x84692B10L, 0x84692BE0L,
        0x84693198L, 0x84693288L, 0x84693380L,
        0x846E64B0L, 0x846E64C0L, 0x846E6E58L, 0x846E6EB8L,
        0x846E90D8L, 0x846E91B8L,
        0x846E9360L, 0x846E9368L, 0x846E9510L, 0x846EA138L,
        0x846EAC78L, 0x846EAEB0L, 0x846EB080L, 0x846EB318L, 0x846EB3A8L,
        0x846EEFD0L, 0x846EF1D0L, 0x846EF638L, 0x846EF7A0L,
        0x846F4E38L, 0x846F5058L, 0x846F5198L,
        0x84762610L, 0x847628E8L,
        0x84B1B700L, 0x84B1B848L, 0x84B1B8E0L, 0x84B1B928L,
        0x84B1B960L, 0x84B2AE80L, 0x84B2D400L, 0x84B32850L,
        0x84B43498L, 0x84B646C0L, 0x84B65B00L
    };

    private static final long[] STATIC_TARGETS = {
        0x84D302C8L, 0x84D30328L, 0x84D30400L, 0x84D30458L,
        0x845210B8L, 0x84521154L,
        0x844E0A18L, 0x844E0AF0L, 0x844E0B20L, 0x844E0B38L,
        0x844E0B48L, 0x844E0CF8L, 0x844E0D00L, 0x844E0D08L,
        0x844E10C8L, 0x844E10D0L, 0x844E10D8L, 0x844FAC20L,
        0x84D22EC0L, 0x84D22F00L, 0x85008DA8L, 0x85009FB0L,
        0x8500C060L
    };

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" + function.getName();
    }

    private String bytes(Instruction instruction) throws Exception {
        StringBuilder result = new StringBuilder();
        for (byte value : instruction.getBytes()) {
            if (result.length() != 0) result.append(' ');
            result.append(String.format("%02X", value & 0xff));
        }
        return result.toString();
    }

    private String section(Address value) {
        MemoryBlock block = currentProgram.getMemory().getBlock(value);
        return block == null ? "UNMAPPED" : block.getName();
    }

    private List<String> referencesTo(Address target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            result.add(hex(reference.getFromAddress().getUnsignedOffset()) + "(" +
                functionName(owner) + "," + reference.getReferenceType() + ")");
        }
        result.sort(String::compareTo);
        return result;
    }

    private void writeTarget(BufferedWriter output, long value, Set<Function> functions)
            throws Exception {
        Address target = address(value);
        Function at = currentProgram.getFunctionManager().getFunctionAt(target);
        Function owner = currentProgram.getFunctionManager().getFunctionContaining(target);
        if (owner != null) functions.add(owner);
        output.write(hex(value) + " section=" + section(target) +
            " function_at=" + functionName(at) + " owner=" + functionName(owner) +
            " refs=" + String.join(";", referencesTo(target)) + "\n");
    }

    private void writeRange(BufferedWriter output, long first, long afterLast,
            Set<Function> functions) throws Exception {
        output.write("RANGE " + hex(first) + ".." + hex(afterLast - 1) + "\n");
        long value = first;
        while (value < afterLast) {
            Address cursor = address(value);
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                // Transient only: analyzeHeadless is invoked with -readOnly.
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                output.write(hex(value) + " <no instruction> // PORTME: inline data or " +
                    "decoder rejected the bytes\n");
                value += 4;
                continue;
            }
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(cursor);
            if (owner != null) functions.add(owner);
            output.write(hex(value) + " " + bytes(instruction) + " " + instruction +
                " owner=" + functionName(owner) + " refs=" +
                String.join(";", referencesTo(cursor)) + "\n");
            value = instruction.getMaxAddress().getUnsignedOffset() + 1;
        }
        output.write("\n");
    }

    private void writeBytes(BufferedWriter output, long first, int count) throws Exception {
        byte[] data = new byte[count];
        Memory memory = currentProgram.getMemory();
        int read = memory.getBytes(address(first), data);
        if (read != count) throw new IllegalStateException("short read at " + hex(first));
        StringBuilder result = new StringBuilder();
        for (byte value : data) result.append(String.format("%02x", value & 0xff));
        output.write(hex(first) + " length=" + count + " bytes=" + result + "\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfQuicknavTextRenderV4.java OUTPUT_DIRECTORY");
        }
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!APF_MD5.equals(md5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + md5);
        }
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }
        Set<Function> functions = new LinkedHashSet<>();

        File traceFile = new File(directory, "apf_quicknav_text_render_v4_trace.txt");
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("APF 2K8 quicknav text-render read-only v4 trace\n");
            trace.write("Program MD5: " + md5 + "\n");
            trace.write("Transient disassembly is discarded by -readOnly; no saved project " +
                "or executable byte is changed.\n\n");
            trace.write("FOCUS\n");
            for (long value : FOCUS) writeTarget(trace, value, functions);
            trace.write("\nSTATIC_TARGETS\n");
            for (long value : STATIC_TARGETS) writeTarget(trace, value, functions);
            trace.write("\nSTATIC_BYTES\n");
            writeBytes(trace, 0x844E0CF8L, 0x20);
            writeBytes(trace, 0x844E10C0L, 0x20);
            writeBytes(trace, 0x844E10D0L, 0x18);
            writeBytes(trace, 0x844FAC18L, 0x18);
            writeBytes(trace, 0x845210B8L, 0x20);
            writeBytes(trace, 0x84D302C8L, 0x120);
            writeBytes(trace, 0x84D30400L, 0x6C);
            trace.write("\nINSTRUCTIONS\n");
            for (long[] range : RANGES) writeRange(trace, range[0], range[1], functions);
            trace.write("POST_DISASSEMBLY_REFERENCES\n");
            for (long value : FOCUS) writeTarget(trace, value, functions);
        }

        List<Function> sorted = new ArrayList<>(functions);
        sorted.sort(Comparator.comparing(Function::getEntryPoint));
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(directory, "apf_quicknav_text_render_v4_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* Saved-boundary APF quicknav text pseudo-C; truncated PDATA " +
                "boundaries are not represented as complete decompilations. */\n\n");
            for (long value : FOCUS) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(
                    address(value));
                if (function == null) {
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; Ghidra has no saved function boundary.\n");
                }
            }
            pseudo.write("\n");
            for (Function function : sorted) {
                pseudo.write("/* " + functionName(function) + " body=" +
                    hex(function.getBody().getMinAddress().getUnsignedOffset()) + ".." +
                    hex(function.getBody().getMaxAddress().getUnsignedOffset()) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 60 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        hex(function.getEntryPoint().getUnsignedOffset()) + "; " +
                        reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("APF_QUICKNAV_TEXT_RENDER_V4_TRACE_COMPLETE saved_functions=" +
            functions.size());
    }
}

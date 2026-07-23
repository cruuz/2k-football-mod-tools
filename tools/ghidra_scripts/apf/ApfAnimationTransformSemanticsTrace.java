// Emit read-only APF 2K8 evidence for the exact frontend animation transform path.
// The raw words remain authoritative where stock Ghidra cannot decode VMX128.
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

public class ApfAnimationTransformSemanticsTrace extends GhidraScript {
    private static final long[][] RAW_RANGES = {
        { 0x84638450L, 0x846384D0L }, // mode-0 decode output ordering
        { 0x84638720L, 0x846389A0L }, // complete signed-short root sampler
        { 0x84639260L, 0x84639390L }, // mirrored sample and interval/delta wrappers
        { 0x846394D0L, 0x84639618L }, // quaternion/translation -> local matrix
        { 0x84A11B58L, 0x84A11D88L }, // exact frontend clip consumer through tail restore
        { 0x84AA4100L, 0x84AA42C8L }, // frontend static getters/wrappers
        { 0x84B0FA88L, 0x84B0FBF4L }, // hierarchy application
        { 0x84B44D40L, 0x84B44E90L }, // yaw-table matrix helper through blr
    };

    private static final long[] FOCUSED_FUNCTIONS = {
        0x84638450L,
        0x84638720L,
        0x84639260L,
        0x846392C8L,
        0x846394D0L,
        0x84A11B58L,
        0x84AA4138L,
        0x84AA4190L,
        0x84AA41A0L,
        0x84AA41C0L,
        0x84AA41D0L,
        0x84AA41E0L,
        0x84AA41E8L,
        0x84AA41F0L,
        0x84AA4288L,
        0x84B0FA88L,
        0x84B44D90L,
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
        if (function == null) return "none";
        return addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private Function createBody(long start, long end, String name) throws Exception {
        Address first = address(start);
        Address last = address(end);
        for (Address cursor = first; cursor.compareTo(last) <= 0; cursor = cursor.add(4)) {
            if (currentProgram.getListing().getInstructionAt(cursor) == null) disassemble(cursor);
        }
        Function function = currentProgram.getFunctionManager().getFunctionAt(first);
        if (function != null) return function;
        return currentProgram.getListing().createFunction(
            name, first, new AddressSet(first, last), SourceType.ANALYSIS);
    }

    private List<String> referencesTo(long target) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(address(target));
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            values.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        values.sort(String::compareTo);
        return values;
    }

    private String rangeSha256(long first, long afterLast) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] bytes = new byte[(int)(afterLast - first)];
        currentProgram.getMemory().getBytes(address(first), bytes);
        byte[] value = digest.digest(bytes);
        StringBuilder text = new StringBuilder();
        for (byte item : value) text.append(String.format("%02x", item & 0xff));
        return text.toString();
    }

    private void writeRawRange(BufferedWriter output, long first, long afterLast)
            throws Exception {
        output.write("RAW_RANGE " + hex(first) + " " + hex(afterLast) +
            " bytes=" + (afterLast - first) + " sha256=" + rangeSha256(first, afterLast) + "\n");
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
        String reason = result.isTimedOut() ? "timed out" : result.getErrorMessage();
        if (reason == null || reason.isEmpty()) reason = "no diagnostic";
        return reason.replace('\n', ' ').replace('\r', ' ');
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfAnimationTransformSemanticsTrace.java OUTPUT_DIRECTORY");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!"217eea6084c3d03f0f1143802b1f5636".equalsIgnoreCase(executableMd5)) {
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
        Function displacedConsumer = createBody(
            0x84A11B58L, 0x84A11D87L, "FrontendShadowAnimationConsumer_0x84A11B58");
        if (displacedConsumer != null) functions.add(displacedConsumer);
        Function scaleLocal = createBody(
            0x84AA41F0L, 0x84AA4284L, "ScaleFrontendRootMatrix3x3_0x84AA41F0");
        if (scaleLocal != null) functions.add(scaleLocal);

        File traceFile = new File(directory, "animation_transform_semantics_trace.txt");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(traceFile))) {
            output.write("APF 2K8 exact frontend animation transform semantics trace\n");
            output.write("Program MD5: " + executableMd5 + "\n");
            output.write("Program name: " + currentProgram.getName() + "\n");
            output.write("Program language: " + currentProgram.getLanguageID() + "\n");
            output.write("Constraint: raw XEX words are authoritative for truncated VMX128.\n\n");
            output.write("FOCUSED_FUNCTIONS\n");
            for (long value : FOCUSED_FUNCTIONS) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
                output.write(hex(value) + " " + functionName(function) + " refs=" +
                    String.join(";", referencesTo(value)) + "\n");
            }
            output.write("\nCONSTANTS\n");
            long[] constants = {
                0x820009A0L, 0x820009A4L, 0x82000A80L, 0x82000C30L,
                0x820FE120L,
                0x820B5390L, 0x820FC510L, 0x820FC55CL,
            };
            for (long value : constants) {
                long raw = Integer.toUnsignedLong(currentProgram.getMemory().getInt(address(value)));
                output.write("CONST32 " + hex(value) + " " + hex(raw) +
                    " float=" + Float.toString(Float.intBitsToFloat((int)raw)) +
                    " refs=" + String.join(";", referencesTo(value)) + "\n");
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
        File pseudoFile = new File(directory, "animation_transform_semantics_focused_pseudo_c.c");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(pseudoFile))) {
            output.write("/* APF 2K8 exact frontend animation transform semantics pseudo-C. */\n");
            output.write("/* Consult the paired RAW32 trace for every VMX128 operation. */\n\n");
            for (Function function : sorted) {
                output.write("/* " + functionName(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    output.write(result.getDecompiledFunction().getC());
                } else {
                    output.write("// PORTME at " + addr(function.getEntryPoint()) +
                        ": Ghidra decompile failed: " + safeReason(result) + "\n");
                }
                output.write("\n\n");
            }
            output.write("// PORTME at 0x846384A8 and 0x84638610: preserve Xenon estimate/VMX rounding only for bit-exact replay.\n");
            output.write("// PORTME at 0x84A11B58: recreate full structured source from the authoritative displaced RAW32 span.\n");
            output.write("// PORTME after 0x84B0FA88: this trace does not claim player_shadow palette/inverse-bind semantics.\n");
        } finally {
            decompiler.dispose();
        }
        println("APF_ANIMATION_TRANSFORM_SEMANTICS_TRACE_COMPLETE functions=" + sorted.size());
    }
}

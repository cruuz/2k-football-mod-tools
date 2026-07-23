// Emit focused static evidence for APF 2K8 SingleMoCap and BoneScaleMap.
// @category Xbox360.APF2K8

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
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class ApfMoCapTrace extends GhidraScript {
    private static final long SINGLE_MOCAP_HASH = 0x60900D71L;
    private static final long BONE_SCALE_MAP_HASH = 0x1BBFAB40L;
    private static final long CDAN_HASH = 0xA7701F00L;
    private static final long MRKS_HASH = 0xC6ED33A2L;

    private static final long[] FOCUSED_FUNCTIONS = {
        0x84636CE8L, // four fixed + optional variable pointer load relocator
        0x84636DE8L, // inverse four fixed + optional variable pointer relocator
        0x84638720L, // bounded vector-track linear sampler
        0x846389A8L, // terminated event stream range query
        0x84638C18L, // next event of requested low-byte ID
        0x84638CC8L, // next event regardless of ID
        0x84638D68L, // previous-event search
        0x84638E18L, // packed scalar/angular sampler
        0x84638F88L, // packed scalar sampler
        0x84639260L, // mirrored vector sample wrapper
        0x846392C8L, // vector interval/delta wrapper
        0x8463AE48L, // root-track phase/velocity consumer
        0x8463B778L, // typed SingleMoCap lookup wrapper
        0x84659638L, // BoneScaleMap inverse pointer helper
        0x846596B0L, // BoneScaleMap load pointer helper
        0x846597C0L, // registered BoneScaleMap load callback
        0x84659810L, // registered BoneScaleMap inverse callback
        0x84659B88L, // registered BoneScaleMap destructor callback
        0x84979058L, // registered CDAN load callback (separate resource layout)
        0x84979100L, // registered CDAN inverse callback
        0x849791B0L, // registered CDAN destructor callback
        0x848CED68L, // concrete marker IDs + scalar sample consumer
        0x848E2860L, // concrete marker IDs + vector interval consumer
        0x84A12158L, // animation playback entry used with looked-up resource
        0x84A619E8L  // concrete typed SingleMoCap lookup and playback caller
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

    private long raw32(long value) throws Exception {
        return Integer.toUnsignedLong(currentProgram.getMemory().getInt(address(value)));
    }

    private void writeWord(BufferedWriter report, long value, String label) throws Exception {
        report.write(hex(value) + " raw=" + hex(raw32(value)) + " label=" + label + "\n");
    }

    private List<Address> findBytes(long value) throws Exception {
        byte[] needle = new byte[] {
            (byte)(value >>> 24), (byte)(value >>> 16),
            (byte)(value >>> 8), (byte)value
        };
        List<Address> hits = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(
                    cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                hits.add(hit);
                cursor = hit.add(1);
            }
        }
        return hits;
    }

    private List<String> referencesTo(Address target, Set<Function> candidates) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
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

    private void writeWindow(
            BufferedWriter report, Address center, Set<Function> candidates) throws Exception {
        Memory memory = currentProgram.getMemory();
        Address first = center.subtract(0x20);
        Address last = center.add(0x40);
        for (Address cursor = first; cursor.compareTo(last) <= 0; cursor = cursor.add(4)) {
            if (!memory.contains(cursor)) continue;
            long raw = Integer.toUnsignedLong(memory.getInt(cursor));
            report.write(addr(cursor) + " raw=" + hex(raw) + " refs=" +
                String.join(";", referencesTo(cursor, candidates)) + "\n");
        }
    }

    private List<Function> sorted(Set<Function> functions) {
        List<Function> result = new ArrayList<>(functions);
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
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

    private void writeInstructions(BufferedWriter report, long first, long afterLast)
            throws Exception {
        for (Address cursor = address(first); cursor.compareTo(address(afterLast)) < 0;
                cursor = cursor.add(4)) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            report.write(addr(cursor) + " " +
                (instruction == null ? "<no instruction>" : instruction.toString()) + "\n");
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: ApfMoCapTrace.java OUTPUT_DIRECTORY");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!"217eea6084c3d03f0f1143802b1f5636".equalsIgnoreCase(executableMd5) &&
            !"c6f5639ac4c428682db0362947a223d8".equalsIgnoreCase(executableMd5) &&
            !"5370d49a9542d60c0345391e4e4aa656".equalsIgnoreCase(executableMd5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + executableMd5);
        }
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }

        Set<Function> candidates = new LinkedHashSet<>();
        for (long value : FOCUSED_FUNCTIONS) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
            if (function != null) candidates.add(function);
        }
        Function aggregateLoad = createBody(
            0x8463B010L, 0x8463B08BL, "MoCapAggregateLoad_Body");
        Function aggregateInverse = createBody(
            0x8463B098L, 0x8463B107L, "MoCapAggregateInverse_Body");
        Function inverseRelocator = createBody(
            0x84636DE8L, 0x84636EB7L, "SingleMoCapInverseRelocator");
        if (aggregateLoad != null) candidates.add(aggregateLoad);
        if (aggregateInverse != null) candidates.add(aggregateInverse);
        if (inverseRelocator != null) candidates.add(inverseRelocator);

        long[] hashes = {
            SINGLE_MOCAP_HASH, BONE_SCALE_MAP_HASH, CDAN_HASH, MRKS_HASH,
            0xFE2226BAL // CRC32("hand_pose"), used by compact mirror alias
        };
        File traceFile = new File(output, "mocap_trace.txt");
        try (BufferedWriter report = new BufferedWriter(new FileWriter(traceFile))) {
            report.write("APF 2K8 SingleMoCap/BoneScaleMap focused static trace\n");
            report.write("Program MD5: " + executableMd5 + "\n");
            report.write("Program name: " + currentProgram.getName() + "\n");
            report.write("Program language: " + currentProgram.getLanguageID() + "\n");
            report.write("Constraint: CDAN/MRKS are binding candidates, not assumed motion codecs.\n\n");

            report.write("RUNTIME_CONSTANTS_AND_REGISTRY\n");
            writeWord(report, 0x82000BD0L, "event fixed-point scale float=" +
                Float.intBitsToFloat((int)raw32(0x82000BD0L)));
            writeWord(report, 0x82000C30L, "root sample int16 scale float=" +
                Float.intBitsToFloat((int)raw32(0x82000C30L)));
            writeWord(report, 0x82000C44L, "SingleMoCap typed lookup hash");
            writeWord(report, 0x84D11080L, "SingleMoCap runtime registry vptr");
            writeWord(report, 0x84D11084L, "SingleMoCap runtime registry hash");
            writeWord(report, 0x82005EE8L, "compact alias type hash");
            writeWord(report, 0x82005EECL, "compact alias name CRC32 hand_pose_mirror");
            writeWord(report, 0x82005EF0L, "compact alias target CRC32 hand_pose");
            writeWord(report, 0x82003854L, "BoneScaleMap descriptor type hash");
            writeWord(report, 0x82003858L, "BoneScaleMap load callback");
            writeWord(report, 0x8200385CL, "BoneScaleMap inverse callback");
            writeWord(report, 0x82003860L, "BoneScaleMap destructor callback");
            writeWord(report, 0x84D19138L, "BoneScaleMap runtime registry vptr");
            writeWord(report, 0x84D1913CL, "BoneScaleMap runtime registry hash");
            writeWord(report, 0x820D2AF8L, "crowd SingleMoCap type hash");
            writeWord(report, 0x820D2B70L, "CDAN type hash table value");
            writeWord(report, 0x84E20590L, "CDAN runtime registry callback-table pointer");
            writeWord(report, 0x84E20594L, "CDAN runtime registry hash");
            writeWord(report, 0x820D2C00L, "CDAN load callback");
            writeWord(report, 0x820D2C04L, "CDAN inverse callback");
            writeWord(report, 0x820D2C08L, "CDAN destructor callback");
            report.write("\n");

            for (long hash : hashes) {
                List<Address> hits = findBytes(hash);
                report.write("HASH " + hex(hash) + " raw_hits=" + hits.size() + "\n");
                for (Address hit : hits) {
                    MemoryBlock block = currentProgram.getMemory().getBlock(hit);
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(hit);
                    if (owner != null) candidates.add(owner);
                    report.write(addr(hit) + " block=" +
                        (block == null ? "none" : block.getName()) + " owner=" +
                        functionName(owner) + " refs=" +
                        String.join(";", referencesTo(hit, candidates)) + "\n");
                    writeWindow(report, hit, candidates);
                }
                report.write("\n");
            }

            report.write("FOCUSED_FUNCTION_REFERENCES\n");
            for (long value : FOCUSED_FUNCTIONS) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
                report.write(hex(value) + " " + functionName(function) + " refs=" +
                    String.join(";", referencesTo(address(value), candidates)) + "\n");
            }

            report.write("\nHASH_IMMEDIATE_HITS\n");
            InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                boolean matched = false;
                for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                    for (Object object : instruction.getOpObjects(operand)) {
                        if (!(object instanceof Scalar)) continue;
                        long value = ((Scalar)object).getUnsignedValue();
                        for (long hash : hashes) {
                            if (value == hash || value == (hash >>> 16) ||
                                value == (hash & 0xFFFFL)) matched = true;
                        }
                    }
                }
                if (!matched) continue;
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                    instruction.getAddress());
                report.write(addr(instruction.getAddress()) + " instruction=" + instruction +
                    " owner=" + functionName(owner) + "\n");
            }

            report.write("\nSINGLE_MOCAP_RELOCATOR_DISASSEMBLY\n");
            writeInstructions(report, 0x84636CE8L, 0x84636EB8L);
            report.write("\nMOCAP_AGGREGATE_WRAPPER_DISASSEMBLY\n");
            writeInstructions(report, 0x8463B008L, 0x8463B108L);
            report.write("\nCROWD_SINGLE_MOCAP_LOOKUP_DISASSEMBLY\n");
            writeInstructions(report, 0x84975E60L, 0x84975F20L);

            report.write("\nCANDIDATE_FUNCTIONS count=" + candidates.size() + "\n");
            for (Function function : sorted(candidates)) {
                report.write(functionName(function) + "\n");
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(output, "mocap_focused_pseudo_c.c");
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* APF 2K8 mocap focused pseudo-C; unknown fields remain unnamed. */\n\n");
            for (Function function : sorted(candidates)) {
                long value = function.getEntryPoint().getUnsignedOffset();
                pseudo.write("/* " + functionName(function) + " references=" +
                    String.join(";", referencesTo(function.getEntryPoint(), candidates)) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 90 seconds" :
                        result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " + hex(value) +
                        "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("APF_MOCAP_TRACE_COMPLETE candidates=" + candidates.size());
    }
}

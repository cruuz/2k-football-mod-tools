// Trace APF 2K8 packed-pose logical records into matrix-map consumers.
// @category Xbox360.APF2K8

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
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
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class ApfPoseBoneBindingTrace extends GhidraScript {
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
                Address hit = memory.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                hits.add(hit);
                cursor = hit.add(1);
            }
        }
        return hits;
    }

    private List<String> referencesTo(Address target) {
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

    private void writeInstructions(BufferedWriter output, long first, long afterLast)
            throws Exception {
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

    private Function createBody(long firstValue, long lastValue, String name) throws Exception {
        Address first = address(firstValue);
        Address last = address(lastValue);
        Function containing = currentProgram.getFunctionManager().getFunctionContaining(first);
        if (containing != null && !containing.getEntryPoint().equals(first)) {
            currentProgram.getFunctionManager().removeFunction(containing.getEntryPoint());
        }
        for (Address cursor = first; cursor.compareTo(last) <= 0; cursor = cursor.add(4)) {
            if (currentProgram.getListing().getInstructionAt(cursor) == null) disassemble(cursor);
        }
        Function function = currentProgram.getFunctionManager().getFunctionAt(first);
        if (function != null) return function;
        return currentProgram.getListing().createFunction(
            name, first, new AddressSet(first, last), SourceType.ANALYSIS);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "usage: ApfPoseBoneBindingTrace.java OUTPUT_DIRECTORY");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!"217eea6084c3d03f0f1143802b1f5636".equalsIgnoreCase(executableMd5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + executableMd5);
        }
        File outputDirectory = new File(args[0]);
        if (!outputDirectory.isDirectory() && !outputDirectory.mkdirs()) {
            throw new IllegalStateException("cannot create " + outputDirectory);
        }

        long[] sharedHelpers = {
            0x84BD6DCCL, 0x84BD6DD0L, 0x84BD6DD4L, 0x84BD6DD8L,
            0x84BD6DDCL, 0x84BD6DE0L, 0x84BD6DE4L, 0x84BD6DE8L,
            0x84BD6DECL, 0x84BD7390L, 0x84BD766CL
        };
        for (long value : sharedHelpers) {
            Function helper = currentProgram.getFunctionManager().getFunctionAt(address(value));
            if (helper != null) helper.setNoReturn(false);
        }

        Set<Function> focused = new LinkedHashSet<>();
        long[][] bodies = {
            { 0x84639A40L, 0x84639E0CL },
            { 0x84639E18L, 0x8463A16CL },
            { 0x8463A178L, 0x8463A1E4L },
            { 0x8463A1F0L, 0x8463A31CL },
            { 0x8463A9D0L, 0x8463AC64L },
            { 0x8463B468L, 0x8463B54CL },
            { 0x847C1268L, 0x847C1434L },
            { 0x847C1438L, 0x847C14DCL },
            { 0x847C1598L, 0x847C16CCL },
            { 0x847C18E0L, 0x847C1994L },
            { 0x847C19A0L, 0x847C1A9CL },
            { 0x847C1F58L, 0x847C2244L },
            { 0x847C4D68L, 0x847C5014L },
            { 0x847C9428L, 0x847C94B8L },
            { 0x84877698L, 0x84877834L },
            { 0x849259F0L, 0x8492613CL },
            { 0x84AA4190L, 0x84AA4198L },
            { 0x84AA41B0L, 0x84AA41B8L },
        };
        for (long[] body : bodies) {
            Function function = createBody(body[0], body[1],
                "PoseBinding_" + Long.toHexString(body[0]));
            if (function != null) focused.add(function);
        }
        long[] adjacentFunctions = {
            0x84639898L, 0x84639A38L, 0x84639E10L, 0x8463A170L,
            0x8463A1E8L, 0x8463A870L, 0x8463A9C8L, 0x8463AC68L,
            0x8463B460L, 0x8463B550L, 0x8463B7D8L,
            0x847C0B68L, 0x847C0D28L, 0x847C0E10L, 0x847C1260L,
            0x847C14E0L, 0x847C1590L, 0x847C16D0L, 0x847C1738L,
            0x847C18D8L, 0x847C1998L, 0x847C1AA0L
            , 0x8497B7B0L, 0x84AC1668L, 0x847BACA8L, 0x847BAF88L,
            0x847BB0F8L, 0x847C9878L, 0x847C98E8L, 0x84973FF0L,
            0x8497D158L, 0x846394D0L, 0x8463A320L,
            0x84AA4190L, 0x84AA41A0L, 0x84AA41B0L,
            0x84A9D420L
        };
        for (long value : adjacentFunctions) {
            Function function = currentProgram.getFunctionManager().getFunctionAt(address(value));
            if (function != null) focused.add(function);
        }
        File traceFile = new File(outputDirectory, "pose_bone_binding_trace.txt");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(traceFile))) {
            output.write("APF 2K8 packed-pose to matrix-map binding trace\n");
            output.write("Program MD5: " + executableMd5 + "\n");
            output.write("Program name: " + currentProgram.getName() + "\n");
            output.write("Program language: " + currentProgram.getLanguageID() + "\n\n");

            output.write("DEFAULT_MATRIX_MAP_0x82000B90\n");
            Memory memory = currentProgram.getMemory();
            for (int index = 0; index < 32; index++) {
                int first = memory.getByte(address(0x82000B90L + index * 2L));
                int second = memory.getByte(address(0x82000B91L + index * 2L));
                output.write("MATRIX_MAP " + index + " " + first + " " + second + "\n");
            }

            output.write("\nPOINTER_SEARCHES\n");
            long[] pointers = {
                0x847C1438L, 0x847C9428L, 0x846394D0L, 0x8463A320L,
                0x82000B90L, 0x820D2638L, 0x820FC510L, 0x820FC55CL,
                0x820FC588L, 0x820FC628L, 0x820FE600L, 0x84AA4190L,
                0x84AA41A0L, 0x84AA41B0L
            };
            for (long pointer : pointers) {
                List<Address> hits = findBytes(pointer);
                output.write("POINTER " + hex(pointer) + " hits=" + hits.size() + " refs=" +
                    String.join(";", referencesTo(address(pointer))) + "\n");
                for (Address hit : hits) {
                    MemoryBlock block = memory.getBlock(hit);
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(hit);
                    output.write("HIT " + addr(hit) + " block=" +
                        (block == null ? "none" : block.getName()) + " owner=" +
                        functionName(owner) + " refs=" + String.join(";", referencesTo(hit)) +
                        "\n");
                    for (long value = hit.getUnsignedOffset() - 0x20;
                            value <= hit.getUnsignedOffset() + 0x40; value += 4) {
                        Address cursor = address(value);
                        if (!memory.contains(cursor)) continue;
                        output.write("WINDOW " + hex(value) + " " +
                            hex(Integer.toUnsignedLong(memory.getInt(cursor))) + " refs=" +
                            String.join(";", referencesTo(cursor)) + "\n");
                    }
                }
            }

            output.write("\nBONE_HASH_SEARCHES\n");
            long[][] boneHashes = {
                { 0xBB538070L, 0 }, { 0x9F2B20BBL, 1 }, { 0x2FD2B90AL, 2 },
                { 0xB21AB9F9L, 3 }, { 0x56ADB276L, 4 }, { 0x598EE88EL, 5 },
                { 0x18335E99L, 6 }, { 0x5733871BL, 7 }, { 0x614C55E5L, 8 },
                { 0xC192B32DL, 9 }, { 0xA21CCAF5L, 10 }, { 0xF53DC400L, 11 },
                { 0xE98022AAL, 12 }, { 0x2D38325DL, 13 },
                { 0xBF9AEFB2L, 14 }, { 0x2693BE08L, 15 }, { 0x51948E9EL, 16 },
                { 0x08AC0254L, 17 }, { 0x91A553EEL, 18 }, { 0xE6A26378L, 19 },
                { 0x0AEABC0DL, 20 }, { 0x93E3EDB7L, 21 }, { 0xE4E4DD21L, 22 },
                { 0x0B28D63AL, 23 }, { 0x92218780L, 24 }, { 0xE526B716L, 25 },
                { 0x0E67C0BFL, 26 }, { 0x976E9105L, 27 }, { 0xE069A193L, 28 },
                { 0x887B0821L, 34 }, { 0x1172599BL, 35 }, { 0x6675690DL, 36 },
                { 0x31CBB30FL, 37 }, { 0xA8C2E2B5L, 38 }, { 0xDFC5D223L, 39 },
                { 0x338D0D56L, 40 }, { 0xAA845CECL, 41 }, { 0xDD836C7AL, 42 },
                { 0x324F6761L, 43 }, { 0xAB4636DBL, 44 }, { 0xDC41064DL, 45 },
                { 0x370071E4L, 46 }, { 0xAE09205EL, 47 }, { 0xD90E10C8L, 48 }
            };
            Map<Long, List<Address>> boneHits = new LinkedHashMap<>();
            List<String> bindingPointers = new ArrayList<>();
            for (long[] item : boneHashes) boneHits.put(item[0], new ArrayList<>());
            for (MemoryBlock block : memory.getBlocks()) {
                if (!block.isInitialized()) continue;
                long first = (block.getStart().getUnsignedOffset() + 3L) & ~3L;
                long last = block.getEnd().getUnsignedOffset();
                for (long value = first; value + 3 <= last; value += 4) {
                    long raw = Integer.toUnsignedLong(memory.getInt(address(value)));
                    List<Address> matches = boneHits.get(raw);
                    if (matches != null) matches.add(address(value));
                    if ((raw >= 0x820FC500L && raw < 0x820FC700L) ||
                        (raw >= 0x820FE5B0L && raw < 0x820FE700L)) {
                        bindingPointers.add(hex(value) + "->" + hex(raw));
                    }
                }
            }
            for (String bindingPointer : bindingPointers) {
                output.write("BINDING_POINTER " + bindingPointer + "\n");
            }
            output.write("BINDING_POINTER_COUNT " + bindingPointers.size() + "\n");
            for (long[] item : boneHashes) {
                List<Address> hits = boneHits.get(item[0]);
                output.write("BONE_HASH lores_index=" + item[1] + " hash=" + hex(item[0]) +
                    " hits=" + hits.size() + "\n");
                for (Address hit : hits) {
                    MemoryBlock hitBlock = memory.getBlock(hit);
                    output.write("BONE_HASH_HIT " + addr(hit) + " block=" +
                        (hitBlock == null ? "none" : hitBlock.getName()) + " owner=" +
                        functionName(currentProgram.getFunctionManager().getFunctionContaining(hit)) +
                        " refs=" + String.join(";", referencesTo(hit)) + "\n");
                    for (long value = hit.getUnsignedOffset() - 0x20;
                            value <= hit.getUnsignedOffset() + 0x20; value += 4) {
                        if (!memory.contains(address(value))) continue;
                        output.write("BONE_HASH_WINDOW " + addr(hit) + " " + hex(value) + " " +
                            hex(Integer.toUnsignedLong(memory.getInt(address(value)))) + "\n");
                    }
                }
            }
            output.write("BONE_TABLE_NEARBY_REFERENCES\n");
            long[][] tableWindows = {
                { 0x820D2538L, 0x820D27B0L },
                { 0x820FC528L, 0x820FC7A0L },
                { 0x820FE500L, 0x820FE780L }
            };
            for (long[] window : tableWindows) {
                for (long value = window[0]; value < window[1]; value += 4) {
                    List<String> refs = referencesTo(address(value));
                    if (!refs.isEmpty()) {
                        output.write("BONE_TABLE_REF " + hex(value) + " refs=" +
                            String.join(";", refs) + "\n");
                    }
                }
            }
            output.write("BONE_BINDING_DATA_RANGES\n");
            long[][] bindingRanges = {
                { 0x820FC500L, 0x820FC700L },
                { 0x820FE5B0L, 0x820FE700L }
            };
            for (long[] range : bindingRanges) {
                output.write("BINDING_RANGE " + hex(range[0]) + " " + hex(range[1]) + "\n");
                for (long value = range[0]; value < range[1]; value += 4) {
                    output.write("BINDING_WORD " + hex(value) + " " +
                        hex(Integer.toUnsignedLong(memory.getInt(address(value)))) + "\n");
                }
            }

            output.write("STATIC_POSE_BLOCK\n");
            output.write("STATIC_GETTER 0x84AA4190 target=0x820FC510 refs=" +
                String.join(";", referencesTo(address(0x84AA4190L))) + "\n");
            output.write("STATIC_GETTER 0x84AA41A0 target=0x820FC55C refs=" +
                String.join(";", referencesTo(address(0x84AA41A0L))) + "\n");
            output.write("STATIC_GETTER 0x84AA41B0 target=0x820FC588 refs=" +
                String.join(";", referencesTo(address(0x84AA41B0L))) + "\n");
            for (int index = 0; index < 25; index++) {
                long base = 0x820FC510L + index * 3L;
                output.write("STATIC_MAP3 " + index + " " +
                    Byte.toUnsignedInt(memory.getByte(address(base))) + " " +
                    memory.getByte(address(base + 1)) + " " +
                    memory.getByte(address(base + 2)) + "\n");
            }
            for (int index = 0; index < 22; index++) {
                long base = 0x820FC55CL + index * 2L;
                output.write("STATIC_MAP2_BYTES " + index + " " +
                    memory.getByte(address(base)) + " " +
                    memory.getByte(address(base + 1)) + "\n");
            }
            output.write("STATIC_MAP2_EXTENT 0x820FC55C 0x820FC588 bytes=44 " +
                "record21_status=record_or_alignment_unproved\n");
            for (int index = 0; index < 15; index++) {
                long base = 0x820FC628L + index * 8L;
                output.write("STATIC_FINGER_PAIR " + index + " " +
                    hex(Integer.toUnsignedLong(memory.getInt(address(base)))) + " " +
                    hex(Integer.toUnsignedLong(memory.getInt(address(base + 4))) ) + "\n");
            }
            output.write("STATIC_SKELETON_HASH player_lo=" +
                hex(Integer.toUnsignedLong(memory.getInt(address(0x820FC6A0L)))) +
                " player=" +
                hex(Integer.toUnsignedLong(memory.getInt(address(0x820FC6A4L)))) + "\n");

            output.write("\nSTATIC_CONFIG_CANDIDATES\n");
            int staticConfigCount = 0;
            for (MemoryBlock block : memory.getBlocks()) {
                if (!block.isInitialized() || block.isExecute()) continue;
                long first = (block.getStart().getUnsignedOffset() + 3L) & ~3L;
                long last = block.getEnd().getUnsignedOffset();
                for (long base = first; base + 0x47 <= last; base += 4) {
                    long count = Integer.toUnsignedLong(memory.getInt(address(base + 0x1C)));
                    if (count == 0 || count > 128) continue;
                    long map3 = Integer.toUnsignedLong(memory.getInt(address(base + 0x24)));
                    long map2 = Integer.toUnsignedLong(memory.getInt(address(base + 0x28)));
                    if (!memory.contains(address(map3)) || !memory.contains(address(map2))) continue;
                    long active = (Integer.toUnsignedLong(memory.getInt(address(base + 4))) |
                        Integer.toUnsignedLong(memory.getInt(address(base + 8)))) &
                        ~Integer.toUnsignedLong(memory.getInt(address(base + 0x0C)));
                    active &= 0xFFFFFFFFL;
                    if (active == 0) continue;
                    int logicalCount = 64 - Long.numberOfLeadingZeros(active);
                    if (logicalCount > 32) continue;
                    boolean valid3 = true;
                    boolean valid2 = true;
                    boolean nonzero3 = false;
                    boolean nonzero2 = false;
                    for (int index = 0; index < logicalCount; index++) {
                        int mode = Byte.toUnsignedInt(memory.getByte(address(map3 + index * 3L)));
                        int normal = memory.getByte(address(map3 + index * 3L + 1));
                        int mirror = memory.getByte(address(map3 + index * 3L + 2));
                        if (mode > 2 || normal < -1 || normal > 31 ||
                            mirror < -1 || mirror > 31) valid3 = false;
                        if (mode != 0 || normal != 0 || mirror != 0) nonzero3 = true;
                    }
                    for (int index = 0; index < count; index++) {
                        int rotation = memory.getByte(address(map2 + index * 2L));
                        int translation = memory.getByte(address(map2 + index * 2L + 1));
                        if (rotation < -1 || rotation > 31 ||
                            translation < -1 || translation > 31) valid2 = false;
                        if (rotation != 0 || translation != 0) nonzero2 = true;
                    }
                    if (!valid3 || !valid2 || !nonzero3 || !nonzero2) continue;
                    long callback = Integer.toUnsignedLong(memory.getInt(address(base + 0x44)));
                    if (callback != 0) {
                        MemoryBlock callbackBlock = memory.getBlock(address(callback));
                        if (callbackBlock == null || !callbackBlock.isExecute()) continue;
                    }
                    staticConfigCount++;
                    output.write("STATIC_CONFIG " + hex(base) + " block=" + block.getName() +
                        " mask4=" + hex(Integer.toUnsignedLong(memory.getInt(address(base + 4)))) +
                        " mask8=" + hex(Integer.toUnsignedLong(memory.getInt(address(base + 8)))) +
                        " maskC=" + hex(Integer.toUnsignedLong(memory.getInt(address(base + 0x0C)))) +
                        " active=" + hex(active) + " count=" + count + " map3=" + hex(map3) +
                        " map2=" + hex(map2) + " callback=" + hex(callback) + "\n");
                    for (int index = 0; index < logicalCount; index++) {
                        output.write("STATIC_BINDING " + hex(base) + " " + index + " " +
                            Byte.toUnsignedInt(memory.getByte(address(map3 + index * 3L))) + " " +
                            memory.getByte(address(map3 + index * 3L + 1)) + " " +
                            memory.getByte(address(map3 + index * 3L + 2)) + " " +
                            (index < count ? memory.getByte(address(map2 + index * 2L)) : -128) + " " +
                            (index < count ? memory.getByte(address(map2 + index * 2L + 1)) : -128) + "\n");
                    }
                }
            }
            output.write("STATIC_CONFIG_COUNT " + staticConfigCount + "\n");

            output.write("\nBONE_TABLE_IMMEDIATE_HITS\n");
            output.write("\nSTRUCT_OFFSET_CANDIDATES\n");
            int[] offsets = { 0x04, 0x08, 0x0C, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x44 };
            Map<Function, Set<Integer>> functionOffsets = new LinkedHashMap<>();
            Map<Function, List<String>> functionInstructions = new LinkedHashMap<>();
            InstructionIterator allInstructions = currentProgram.getListing().getInstructions(true);
            while (allInstructions.hasNext()) {
                Instruction instruction = allInstructions.next();
                String rendered = instruction.toString().toLowerCase();
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                    instruction.getAddress());
                if (owner == null) continue;
                if (rendered.contains("0x2638") || rendered.contains("0x39d8") ||
                    rendered.contains("0x1a00")) {
                    output.write("TABLE_IMMEDIATE " + addr(instruction.getAddress()) + " " +
                        instruction + " owner=" + functionName(owner) + "\n");
                }
                for (int offset : offsets) {
                    String marker = "0x" + Integer.toHexString(offset) + "(";
                    if (!rendered.contains(marker)) continue;
                    functionOffsets.computeIfAbsent(owner, ignored -> new LinkedHashSet<>()).add(offset);
                    functionInstructions.computeIfAbsent(owner, ignored -> new ArrayList<>()).add(
                        addr(instruction.getAddress()) + " " + instruction.toString());
                }
            }
            List<Function> offsetFunctions = new ArrayList<>(functionOffsets.keySet());
            offsetFunctions.sort(Comparator.comparing(Function::getEntryPoint));
            for (Function function : offsetFunctions) {
                Set<Integer> found = functionOffsets.get(function);
                if (!(found.contains(0x24) && found.contains(0x28))) continue;
                List<String> encoded = new ArrayList<>();
                for (int offset : found) encoded.add(String.format("+0x%02X", offset));
                output.write("OFFSET_FUNCTION " + functionName(function) + " offsets=" +
                    String.join(",", encoded) + " refs=" +
                    String.join(";", referencesTo(function.getEntryPoint())) + "\n");
                for (String instruction : functionInstructions.get(function)) {
                    output.write("OFFSET_INSN " + instruction + "\n");
                }
            }

            output.write("\nKNOWN_CALLERS\n");
            long[] callsites = {
                0x847C14ACL, 0x847C1FD0L, 0x847C4F78L, 0x847C949CL,
                0x8497B924L, 0x84AC16F4L, 0x847C1478L, 0x847C1F9CL,
                0x847C9468L, 0x8497B8E8L, 0x84AC16B8L
            };
            for (long callsite : callsites) {
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                    address(callsite));
                output.write("CALLSITE " + hex(callsite) + " owner=" + functionName(owner) +
                    "\n");
            }

            output.write("\nRAW_MATRIX_EXPANSION\n");
            writeInstructions(output, 0x846394D0L, 0x84639618L);
            output.write("\nRAW_CONCRETE_CALLERS\n");
            writeInstructions(output, 0x847C1438L, 0x847C14E0L);
            writeInstructions(output, 0x847C9428L, 0x847C94BCL);
            output.write("\nRAW_CALLER_REGION_CONSTRUCTORS\n");
            writeInstructions(output, 0x847C0B68L, 0x847C0D28L);
            writeInstructions(output, 0x847C0E10L, 0x847C1260L);
            output.write("\nRAW_ADJACENT_MOCAP_HELPERS\n");
            writeInstructions(output, 0x84639898L, 0x8463A320L);
            writeInstructions(output, 0x8463A870L, 0x8463B008L);
            output.write("\nRAW_FINGER_TABLE_CONSUMER\n");
            writeInstructions(output, 0x84973FF0L, 0x84974138L);
            output.write("\nRAW_STATIC_BLOCK_REFERENCES\n");
            writeInstructions(output, 0x84AA4140L, 0x84AA41E0L);
            writeInstructions(output, 0x84A9D420L, 0x84A9D480L);
            writeInstructions(output, 0x84877698L, 0x84877838L);
            writeInstructions(output, 0x849259F0L, 0x84926140L);
        }


        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        File pseudoFile = new File(outputDirectory, "pose_bone_binding_focused_pseudo_c.c");
        List<Function> sorted = new ArrayList<>(focused);
        sorted.sort(Comparator.comparing(Function::getEntryPoint));
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* APF 2K8 packed-pose/bone-binding focused pseudo-C. */\n\n");
            for (Function function : sorted) {
                pseudo.write("/* " + functionName(function) + " references=" +
                    String.join(";", referencesTo(function.getEntryPoint())) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out" : result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " +
                        addr(function.getEntryPoint()) + "; " + reason.replace('\n', ' ') + "\n");
                }
                long entry = function.getEntryPoint().getUnsignedOffset();
                if (entry == 0x846394D0L) {
                    pseudo.write("// PORTME at 0x846394D0: Ghidra does not lift the " +
                        "VMX128 matrix body completely; use the RAW32 trace.\n");
                }
                if (entry == 0x8463A320L) {
                    pseudo.write("// PORTME at 0x8463A4F0/0x8463A52C: sampler modes " +
                        "2 and 1 remain unresolved.\n");
                }
                if (entry == 0x84877698L || entry == 0x849259F0L ||
                    entry == 0x84973FF0L) {
                    pseudo.write("// PORTME: Ghidra collapsed this shared-save/VMX " +
                        "function; the address-bounded RAW32 trace is authoritative.\n");
                }
                pseudo.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("APF_POSE_BONE_BINDING_TRACE_COMPLETE");
    }
}

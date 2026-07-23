// Emit focused read-only evidence for APF 2K8's MANU/manual.iff handler.
// @category Xbox360.APF2K8

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.nio.charset.StandardCharsets;
import java.util.zip.CRC32;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfManualRemnantTrace extends GhidraScript {
    private static final long MANU_HASH = 0x4C997FFBL;
    private static final long STATIC_WINDOW_START = 0x820080F0L;
    private static final long STATIC_WINDOW_END = 0x82008160L;
    private static final long STATIC_HASH_ADDRESS = 0x82008108L;
    private static final long REGISTERED_CALLBACK = 0x846B02B8L;
    private static final long SIBLING_CALLBACK = 0x846B02A8L;
    private static final long RUNTIME_WINDOW_START = 0x84D22EA0L;
    private static final long RUNTIME_WINDOW_END = 0x84D22EC0L;
    private static final long RUNTIME_HASH_ADDRESS = 0x84D22EA4L;
    private static final long INITIALIZER_SLOT = 0x820081E8L;
    private static final long MANUAL_PACKAGE_STRING = 0x8450D6E8L;
    private static final long PAGE_TABLE = 0x84D25440L;
    private static final int PAGE_COUNT = 15;

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

    private List<String> referencesTo(Address target) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            values.add(hex(reference.getFromAddress().getUnsignedOffset()) + "(" +
                functionName(owner) + "," + reference.getReferenceType() + ")");
        }
        values.sort(String::compareTo);
        return values;
    }

    private Set<Function> referenceOwners(Address target) {
        Set<Function> owners = new LinkedHashSet<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            if (owner != null) owners.add(owner);
        }
        return owners;
    }

    private Function ensureFunction(long value) throws Exception {
        Address entry = address(value);
        Function function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function != null) return function;
        disassemble(entry);
        createFunction(entry, null);
        function = currentProgram.getFunctionManager().getFunctionAt(entry);
        if (function == null) {
            throw new IllegalStateException("could not create function at " + hex(value));
        }
        return function;
    }

    private String asciiWord(long raw) {
        StringBuilder result = new StringBuilder();
        for (int shift = 24; shift >= 0; shift -= 8) {
            int value = (int)((raw >>> shift) & 0xff);
            result.append(value >= 0x20 && value <= 0x7e ? (char)value : '.');
        }
        return result.toString();
    }

    private void writeWindow(BufferedWriter writer, Memory memory, long start, long end)
            throws Exception {
        for (long value = start; value < end; value += 4) {
            Address slot = address(value);
            long raw = Integer.toUnsignedLong(memory.getInt(slot));
            writer.write(hex(value) + " raw=" + hex(raw) + " ascii=" + asciiWord(raw) +
                " refs=" + String.join(";", referencesTo(slot)) + "\n");
        }
    }

    private void writeInstructions(BufferedWriter writer, Function function) throws Exception {
        writer.write("FUNCTION " + functionName(function) + " body=" +
            function.getBody().toString() + " refs=" +
            String.join(";", referencesTo(function.getEntryPoint())) + "\n");
        InstructionIterator iterator = currentProgram.getListing().getInstructions(
            function.getBody(), true);
        while (iterator.hasNext()) {
            Instruction instruction = iterator.next();
            writer.write(hex(instruction.getAddress().getUnsignedOffset()) + " " +
                instruction.toString() + " refs=" +
                String.join(";", referencesTo(instruction.getAddress())) + "\n");
        }
        writer.write("\n");
    }

    private void writeRawInstructions(BufferedWriter writer, long start, long end)
            throws Exception {
        Address cursor = address(start);
        Address limit = address(end);
        while (cursor.compareTo(limit) < 0) {
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            if (instruction == null) {
                writer.write(hex(cursor.getUnsignedOffset()) + " <no instruction>\n");
                cursor = cursor.add(4);
            }
            else {
                writer.write(hex(cursor.getUnsignedOffset()) + " " + instruction.toString() +
                    " refs=" + String.join(";", referencesTo(cursor)) + "\n");
                cursor = instruction.getMaxAddress().add(1);
            }
        }
    }

    private String readUtf16be(Memory memory, long value) throws Exception {
        StringBuilder result = new StringBuilder();
        Address cursor = address(value);
        for (int count = 0; count < 4096; count++) {
            int character = Short.toUnsignedInt(memory.getShort(cursor));
            if (character == 0) return result.toString();
            result.append((char)character);
            cursor = cursor.add(2);
        }
        throw new IllegalStateException("unterminated UTF-16BE at " + hex(value));
    }

    private long asciiCrc32(String value) {
        CRC32 crc = new CRC32();
        crc.update(value.getBytes(StandardCharsets.US_ASCII));
        return crc.getValue();
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: ApfManualRemnantTrace.java OUTPUT_FILE");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!"217eea6084c3d03f0f1143802b1f5636".equalsIgnoreCase(executableMd5) &&
            !"c6f5639ac4c428682db0362947a223d8".equalsIgnoreCase(executableMd5) &&
            !"5370d49a9542d60c0345391e4e4aa656".equalsIgnoreCase(executableMd5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + executableMd5);
        }
        Memory memory = currentProgram.getMemory();
        long staticHash = Integer.toUnsignedLong(memory.getInt(address(STATIC_HASH_ADDRESS)));
        long runtimeHash = Integer.toUnsignedLong(memory.getInt(address(RUNTIME_HASH_ADDRESS)));
        if (staticHash != MANU_HASH || runtimeHash != MANU_HASH) {
            throw new IllegalStateException(
                "MANU hash witnesses changed: " + hex(staticHash) + " / " + hex(runtimeHash));
        }
        long initializer = Integer.toUnsignedLong(memory.getInt(address(INITIALIZER_SLOT)));
        if (initializer != 0x846B0320L) {
            throw new IllegalStateException("manual initializer slot changed: " + hex(initializer));
        }
        if (!"manual.iff".equals(readUtf16be(memory, MANUAL_PACKAGE_STRING))) {
            throw new IllegalStateException("manual package string changed");
        }

        Set<Function> focused = new LinkedHashSet<>();
        focused.add(ensureFunction(REGISTERED_CALLBACK));
        focused.add(ensureFunction(SIBLING_CALLBACK));
        focused.add(ensureFunction(0x846B0320L));
        focused.addAll(referenceOwners(address(STATIC_HASH_ADDRESS)));
        focused.addAll(referenceOwners(address(REGISTERED_CALLBACK)));
        focused.addAll(referenceOwners(address(RUNTIME_WINDOW_START)));
        focused.addAll(referenceOwners(address(RUNTIME_HASH_ADDRESS)));

        List<Function> sorted = new ArrayList<>(focused);
        sorted.sort((left, right) -> left.getEntryPoint().compareTo(right.getEntryPoint()));
        File output = new File(args[0]);
        File parent = output.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + parent);
        }
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(output))) {
            writer.write("APF 2K8 MANU/manual.iff focused static trace\n");
            writer.write("Program MD5: " + executableMd5 + "\n");
            writer.write("Program name: " + currentProgram.getName() + "\n");
            writer.write("Program language: " + currentProgram.getLanguageID() + "\n");
            writer.write("Constraint: MANU handler presence does not prove menu reachability.\n\n");
            writer.write("MANU_HASH_WITNESSES\n");
            writer.write(hex(STATIC_HASH_ADDRESS) + " value=" + hex(staticHash) +
                " expected=CRC32(MANU) refs=" +
                String.join(";", referencesTo(address(STATIC_HASH_ADDRESS))) + "\n");
            writer.write(hex(RUNTIME_HASH_ADDRESS) + " value=" + hex(runtimeHash) +
                " expected=CRC32(MANU) refs=" +
                String.join(";", referencesTo(address(RUNTIME_HASH_ADDRESS))) + "\n\n");
            writer.write("STATIC_DESCRIPTOR_WINDOW\n");
            writeWindow(writer, memory, STATIC_WINDOW_START, 0x82008240L);
            writer.write("\nRUNTIME_NODE_WINDOW\n");
            writeWindow(writer, memory, RUNTIME_WINDOW_START, RUNTIME_WINDOW_END);
            writer.write("\nCOMPILED_MANUAL_INITIALIZER\n");
            writer.write(hex(INITIALIZER_SLOT) + " raw=" + hex(initializer) +
                " function=0x846B0320 refs=" +
                String.join(";", referencesTo(address(INITIALIZER_SLOT))) + "\n");
            writer.write(hex(MANUAL_PACKAGE_STRING) + " string=" +
                readUtf16be(memory, MANUAL_PACKAGE_STRING) + " refs=" +
                String.join(";", referencesTo(address(MANUAL_PACKAGE_STRING))) + "\n");
            writer.write("page_count=" + PAGE_COUNT + " table=" + hex(PAGE_TABLE) + "\n");
            for (int index = 0; index < PAGE_COUNT; index++) {
                long titlePointer = Integer.toUnsignedLong(memory.getInt(
                    address(PAGE_TABLE + index * 8L)));
                long pagePointer = Integer.toUnsignedLong(memory.getInt(
                    address(PAGE_TABLE + index * 8L + 4)));
                String title = readUtf16be(memory, titlePointer);
                String page = readUtf16be(memory, pagePointer);
                writer.write(String.format(
                    "page=%d title_ptr=%s title=%s page_ptr=%s resource=%s crc32=%s\n",
                    index + 1, hex(titlePointer), title, hex(pagePointer), page,
                    hex(asciiCrc32(page))));
            }
            writer.write("\nFOCUSED_FUNCTION_DISASSEMBLY\n");
            for (Function function : sorted) writeInstructions(writer, function);
            writer.write("MANU_HASH_REFERENCE_DISASSEMBLY\n");
            writeRawInstructions(writer, 0x846AF7B0L, 0x846AFC88L);
            writer.write("\n");

            DecompInterface decompiler = new DecompInterface();
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("decompiler could not open program");
            }
            try {
                writer.write("FOCUSED_PSEUDO_C\n");
                for (Function function : sorted) {
                    writer.write("/* " + functionName(function) + " */\n");
                    DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                    if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                        writer.write(result.getDecompiledFunction().getC());
                    }
                    else {
                        String reason = result.isTimedOut() ? "timed out after 60 seconds" :
                            result.getErrorMessage();
                        writer.write("// PORTME: could not decompile function at " +
                            hex(function.getEntryPoint().getUnsignedOffset()) + "; " +
                            reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                    }
                    writer.write("\n");
                }
            }
            finally {
                decompiler.dispose();
            }
        }
        println("APF_MANUAL_REMNANT_TRACE_COMPLETE functions=" + sorted.size());
    }
}

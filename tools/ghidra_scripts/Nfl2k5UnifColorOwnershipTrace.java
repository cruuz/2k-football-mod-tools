// Read-only, address-led trace for NFL 2K5 Unif packed-color ownership.
// @category Xbox.NFL2K5

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
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Nfl2k5UnifColorOwnershipTrace extends GhidraScript {
    private String addr(Address address) {
        return address == null ? "" : String.format("0x%08X", address.getUnsignedOffset());
    }

    private String fn(Function function) {
        return function == null ? "none" : addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private Function containing(long value) {
        return currentProgram.getFunctionManager().getFunctionContaining(toAddr(value));
    }

    private String refsTo(Address target) {
        List<String> values = new ArrayList<>();
        ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(target);
        while (refs.hasNext()) {
            Reference ref = refs.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            values.add(addr(ref.getFromAddress()) + "(" + fn(owner) + "," + ref.getReferenceType() + ")");
        }
        values.sort(String::compareTo);
        return String.join(";", values);
    }

    private String bytes(Address address, int count) throws Exception {
        byte[] data = new byte[count];
        currentProgram.getMemory().getBytes(address, data);
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < data.length; i++) {
            if (i != 0) out.append(' ');
            out.append(String.format("%02X", data[i] & 0xff));
        }
        return out.toString();
    }

    private String utf16(Address address, int maxChars) throws Exception {
        Memory memory = currentProgram.getMemory();
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < maxChars; i++) {
            int lo = memory.getByte(address.add(i * 2L)) & 0xff;
            int hi = memory.getByte(address.add(i * 2L + 1)) & 0xff;
            int ch = lo | (hi << 8);
            if (ch == 0) break;
            if (ch >= 0x20 && ch < 0x7f) out.append((char)ch);
            else out.append(String.format("\\u%04X", ch));
        }
        return out.toString();
    }

    private long u32(Address address) throws Exception {
        Memory memory = currentProgram.getMemory();
        return (memory.getByte(address) & 0xffL) |
            ((memory.getByte(address.add(1)) & 0xffL) << 8) |
            ((memory.getByte(address.add(2)) & 0xffL) << 16) |
            ((memory.getByte(address.add(3)) & 0xffL) << 24);
    }

    private String pointerText(long value) throws Exception {
        if (value == 0 || !currentProgram.getMemory().contains(toAddr(value))) return "";
        return utf16(toAddr(value), 80);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("usage: SCRIPT OUTPUT_DIRECTORY");
        File directory = new File(args[0]);
        if (!directory.isDirectory() && !directory.mkdirs()) {
            throw new IllegalStateException("cannot create " + directory);
        }

        long[] anchors = {
            0x00064710L, 0x0007BB40L, 0x00078D40L, 0x00078DD0L,
            0x0008E3F0L, 0x0008E430L, 0x0008E470L, 0x0008E4B0L,
            0x0008E620L, 0x0008E7D0L, 0x0008E830L, 0x0008E840L,
            0x0008E850L, 0x0008E860L, 0x0008E870L, 0x0008E880L,
            0x0008E910L, 0x0008E9E0L, 0x0008EFA0L, 0x0008F800L,
            0x0008F930L, 0x0008FAD0L, 0x0008FD90L, 0x00090570L,
            0x00091900L,
        };
        long[] globals = {
            0x00B652B0L, 0x00B652D4L, 0x00B6531CL, 0x00B65428L,
            0x00B65440L, 0x00B65508L, 0x00B65520L, 0x00B65594L,
            0x00B655A4L, 0x00B65B08L,
        };
        long[] strings = {
            0x00E632D8L, 0x00E632ECL, 0x00E63300L, 0x00E63314L,
            0x00E63334L, 0x00E6334CL,
            0x00E63358L, 0x00E63368L, 0x00E63374L, 0x00E6337CL, 0x00E63384L,
            0x00E6339CL, 0x00E633C4L, 0x00E633E4L, 0x00E633F4L,
            0x00E63404L, 0x00E63424L, 0x00E655C4L, 0x00E655E0L,
        };

        Set<Function> functions = new LinkedHashSet<>();
        try (BufferedWriter trace = new BufferedWriter(new FileWriter(new File(directory, "trace.txt")))) {
            trace.write("NFL 2K5 Unif packed-color ownership trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("Read-only saved-project analysis; addresses are loaded XBE virtual addresses.\n\n");

            trace.write("ANCHORS\n");
            for (long value : anchors) {
                Address address = toAddr(value);
                Function function = containing(value);
                if (function != null) functions.add(function);
                trace.write(addr(address) + " owner=" + fn(function) + " refs=" + refsTo(address) + "\n");
            }

            trace.write("\nGLOBALS\n");
            for (long value : globals) {
                Address address = toAddr(value);
                trace.write(addr(address) + " bytes=" + bytes(address, 32) + " refs=" + refsTo(address) + "\n");
            }

            trace.write("\nUTF16_CANDIDATES\n");
            for (long value : strings) {
                Address address = toAddr(value);
                trace.write(addr(address) + " text=" + utf16(address, 64) + " bytes=" + bytes(address, 32) +
                    " refs=" + refsTo(address) + "\n");
            }

            trace.write("\nMATERIAL_NAME_POINTER_TABLE 0x004EEE68..0x004EEF5C\n");
            int materialIndex = 0;
            for (long value = 0x004EEE68L; value <= 0x004EEF5CL; value += 4, materialIndex++) {
                long pointer = u32(toAddr(value));
                trace.write(String.format("index=%02d slot=0x%08X pointer=0x%08X text=%s\n",
                    materialIndex, value, pointer, pointerText(pointer)));
            }

            long[][] pointerTables = {
                {0x004EEAC0L, 8}, {0x004EEAE0L, 5}, {0x004EEFA0L, 4},
                {0x00A86D68L, 4}, {0x00A86E48L, 9},
            };
            trace.write("\nOTHER_POINTER_TABLES\n");
            for (long[] table : pointerTables) {
                trace.write(String.format("table=0x%08X count=%d\n", table[0], table[1]));
                for (int index = 0; index < table[1]; index++) {
                    long slot = table[0] + index * 4L;
                    long pointer = u32(toAddr(slot));
                    trace.write(String.format("  index=%02d slot=0x%08X value=0x%08X text=%s\n",
                        index, slot, pointer, pointerText(pointer)));
                }
            }

            trace.write("\nUNIFORM_ROUTING_DWORDS\n");
            for (long value = 0x004EF360L; value < 0x004EF500L; value += 4) {
                trace.write(String.format("0x%08X=0x%08X\n", value, u32(toAddr(value))));
            }
            for (long value = 0x004EF7E0L; value < 0x004EF900L; value += 4) {
                trace.write(String.format("0x%08X=0x%08X\n", value, u32(toAddr(value))));
            }
            long[] constants = {0x004E4180L, 0x004E4184L, 0x004E4194L, 0x004E419CL, 0x004EDB54L};
            trace.write("\nPACKED_COLOR_CONSTANTS\n");
            for (long value : constants) {
                long bits = u32(toAddr(value));
                trace.write(String.format("0x%08X=0x%08X float=%s\n", value, bits,
                    Float.toString(Float.intBitsToFloat((int)bits))));
            }

            // Include direct callers/callees of the ownership path so the call
            // conditions and final record consumers are not inferred from one
            // decompiler expression alone.
            List<Function> seed = new ArrayList<>(functions);
            for (Function function : seed) {
                functions.addAll(function.getCallingFunctions(monitor));
                functions.addAll(function.getCalledFunctions(monitor));
            }
            List<Function> ordered = new ArrayList<>(functions);
            ordered.removeIf(f -> f == null);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));

            trace.write("\nFUNCTION_RELATIONS count=" + ordered.size() + "\n");
            for (Function function : ordered) {
                List<String> callers = new ArrayList<>();
                for (Function caller : function.getCallingFunctions(monitor)) callers.add(fn(caller));
                callers.sort(String::compareTo);
                List<String> callees = new ArrayList<>();
                for (Function callee : function.getCalledFunctions(monitor)) callees.add(fn(callee));
                callees.sort(String::compareTo);
                trace.write(fn(function) + " callers=" + String.join(";", callers) +
                    " callees=" + String.join(";", callees) + "\n");
            }

            trace.write("\nFOCUSED_DISASSEMBLY\n");
            for (long value : anchors) {
                Function function = containing(value);
                trace.write("\n== " + String.format("0x%08X", value) + " owner=" + fn(function) + " ==\n");
                if (function == null) {
                    trace.write("PORTME: no containing function in the saved analysis\n");
                    continue;
                }
                InstructionIterator instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
                while (instructions.hasNext()) {
                    Instruction instruction = instructions.next();
                    trace.write(addr(instruction.getAddress()) + " " + instruction + " refs=" +
                        refsTo(instruction.getAddress()) + "\n");
                }
            }
        }

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(new File(directory, "pseudo_c.c")))) {
            pseudo.write("/* NFL 2K5 Unif packed-color ownership focused pseudo-C. */\n\n");
            List<Function> ordered = new ArrayList<>(functions);
            ordered.removeIf(f -> f == null);
            ordered.sort(Comparator.comparing(Function::getEntryPoint));
            for (Function function : ordered) {
                pseudo.write("/* " + fn(function) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 90, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                } else {
                    pseudo.write("// PORTME: could not decompile function at " + addr(function.getEntryPoint()) +
                        ": " + result.getErrorMessage().replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");
            }
        } finally {
            decompiler.dispose();
        }
        println("NFL2K5_UNIF_COLOR_OWNERSHIP_TRACE_COMPLETE");
    }
}

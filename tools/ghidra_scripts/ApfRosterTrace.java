// Emit focused static evidence for the APF 2K8 ROST resource.
// @category Xbox360.APF2K8

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfRosterTrace extends GhidraScript {
    private static final long[] FUNCTIONS = {
        0x847467E8L, // player count accessor
        0x84746800L, // player index -> record, stride 0x14c
        0x84746BB0L, // root table 2 accessor, stride 0xfa4
        0x84746DD0L, // root table 3 reverse accessor, stride 0x24
        0x84746F60L, // team count accessor
        0x84746F78L, // team index -> record, stride 0x180
        0x8474B828L, // searches populated team records
        0x8474F950L, // post-load setup and final root pointer fixups
        0x84750EF8L, // DRAM/ROST load callback
        0x84752C98L, // 0x24 stadium-record serialization evidence
        0x84753508L, // 0x180 team-record string serialization evidence
        0x84A4A400L, // All Pro appearance/MVP text consumer
        0x84A4A5B8L, // league MVP year-string consumer
        0x84A4A638L, // championship year-string consumers
        0x84A4A768L, // championship MVP year-string consumer
        0x84A4A7E8L, // Hall of Fame year consumer
        0x84A4A858L, // first/last/nickname consumer
        0x84A7ADA8L, // nickname display consumer
        0x84AB3E58L, // player record size and owned-name strings
        0x84AB3FA0L, // player position-label accessor
        0x84AB9840L  // team roster pointer/count loop
    };

    private static final Map<String, Long> POSITION_TABLES = new LinkedHashMap<>();
    static {
        POSITION_TABLES.put("table_820FEB90", 0x820FEB90L);
        POSITION_TABLES.put("table_820FEBD8", 0x820FEBD8L);
        POSITION_TABLES.put("table_820FEC20", 0x820FEC20L);
    }

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

    private String utf16(Address start) throws Exception {
        Memory memory = currentProgram.getMemory();
        StringBuilder result = new StringBuilder();
        Address cursor = start;
        for (int i = 0; i < 4096; i++) {
            int value = Short.toUnsignedInt(memory.getShort(cursor));
            if (value == 0) return result.toString();
            result.append((char)value);
            cursor = cursor.add(2);
        }
        throw new IllegalStateException("unterminated UTF-16 string at " + start);
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

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: ApfRosterTrace.java OUTPUT_DIRECTORY");
        }
        File output = new File(args[0]);
        if (!output.isDirectory() && !output.mkdirs()) {
            throw new IllegalStateException("cannot create " + output);
        }

        File traceFile = new File(output, "roster_trace.txt");
        File pseudoFile = new File(output, "roster_focused_pseudo_c.c");
        Memory memory = currentProgram.getMemory();

        try (BufferedWriter trace = new BufferedWriter(new FileWriter(traceFile))) {
            trace.write("APF 2K8 ROST focused static trace\n");
            trace.write("Program MD5: " + currentProgram.getExecutableMD5() + "\n");
            trace.write("Program language: " + currentProgram.getLanguageID() + "\n");
            trace.write("Constraint: labels below are executable strings or direct consumers; unknown fields remain unknown.\n\n");

            trace.write("POSITION_LABEL_TABLES\n");
            for (Map.Entry<String, Long> table : POSITION_TABLES.entrySet()) {
                Address tableAddress = address(table.getValue());
                trace.write(table.getKey() + " address=" + hex(table.getValue()) + "\n");
                for (int i = 0; i < 18; i++) {
                    Address slot = tableAddress.add(i * 4L);
                    long raw = Integer.toUnsignedLong(memory.getInt(slot));
                    if (raw == 0) {
                        trace.write(String.format("  %02d slot=%s raw=%s target=null value=<terminator>\n",
                            i, hex(slot.getUnsignedOffset()), hex(raw)));
                    }
                    else {
                        Address target = address(raw);
                        trace.write(String.format("  %02d slot=%s raw=%s target=%s value=%s\n",
                            i, hex(slot.getUnsignedOffset()), hex(raw), hex(target.getUnsignedOffset()),
                            utf16(target)));
                    }
                }
            }

            trace.write("\nFUNCTION_REFERENCES\n");
            for (long value : FUNCTIONS) {
                Address entry = address(value);
                Function function = currentProgram.getFunctionManager().getFunctionAt(entry);
                trace.write(hex(value) + " " + functionName(function) +
                    " refs=" + String.join(";", referencesTo(entry)) + "\n");
            }

            trace.write("\nROST_CALLBACK_REGISTRATION_WINDOW\n");
            Address registration = address(0x82017D40L);
            for (int offset = 0; offset < 0x60; offset += 4) {
                Address slot = registration.add(offset);
                long raw = Integer.toUnsignedLong(memory.getInt(slot));
                StringBuilder ascii = new StringBuilder();
                for (int shift = 24; shift >= 0; shift -= 8) {
                    int value = (int)((raw >>> shift) & 0xff);
                    ascii.append(value >= 0x20 && value <= 0x7e ? (char)value : '.');
                }
                trace.write(String.format("%s raw=%s ascii=%s refs=%s\n",
                    hex(slot.getUnsignedOffset()), hex(raw), ascii,
                    String.join(";", referencesTo(slot))));
            }
        }

        List<Long> sorted = new ArrayList<>();
        for (long value : FUNCTIONS) sorted.add(value);
        sorted.sort(Long::compareUnsigned);
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            pseudo.write("/* APF 2K8 ROST focused pseudo-C. Field names remain evidence-limited. */\n\n");
            for (long value : sorted) {
                Address entry = address(value);
                Function function = currentProgram.getFunctionManager().getFunctionAt(entry);
                if (function == null) {
                    pseudo.write("// PORTME: no Ghidra function at " + hex(value) + "\n\n");
                    continue;
                }
                pseudo.write("/* " + functionName(function) + " references=" +
                    String.join(";", referencesTo(entry)) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 30 seconds" :
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
        println("APF_ROSTER_TRACE_COMPLETE functions=" + FUNCTIONS.length);
    }
}

// Read-only focused trace for APF gameplay-slider and fantasy-draft constants.
// @category VisualConcepts.Gameplay

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfGameplayTuningTrace extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final long[] TARGETS = {
        0x820F4B70L, // 17-float NFL/APF fantasy-draft position-priority table
        0x84E4B088L, // offline Difficulty Settings rows
        0x84E4C7C8L, // online Difficulty Settings rows
        0x84F3F9C0L, // Human Catching editable setting
        0x84F3F9E4L, // CPU Catching editable setting
        0x84F3FC44L, // Human Catching synchronized runtime copy
        0x84F3FC20L, // CPU Catching synchronized runtime copy
        0x8470A578L, // 21-float settings exporter
        0x8470A630L, // 21-float settings importer
        0x84680058L, // retained fantasy-draft cluster first proved function
        0x84681A88L  // retained fantasy-draft cluster last proved function
    };

    private Address at(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hx(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private String refs(long value) {
        List<String> rows = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(at(value));
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(reference.getFromAddress());
            rows.add(hx(reference.getFromAddress().getUnsignedOffset()) + ":" +
                reference.getReferenceType() + ":" +
                (owner == null ? "none" : hx(owner.getEntryPoint().getUnsignedOffset())));
        }
        Collections.sort(rows);
        return String.join(";", rows);
    }

    private String exactFullwords(long value) throws Exception {
        byte[] needle = {
            (byte)(value >>> 24), (byte)(value >>> 16),
            (byte)(value >>> 8), (byte)value
        };
        List<String> rows = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                if ((hit.getUnsignedOffset() & 3L) == 0) {
                    rows.add(hx(hit.getUnsignedOffset()) + ":" + block.getName());
                }
                cursor = hit.add(1);
            }
        }
        Collections.sort(rows);
        return String.join(";", rows);
    }

    @Override
    public void run() throws Exception {
        if (!APF_MD5.equalsIgnoreCase(currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("unexpected APF executable MD5");
        }
        if (getScriptArgs().length != 1) {
            throw new IllegalArgumentException("usage: ApfGameplayTuningTrace.java OUTPUT");
        }
        File output = new File(getScriptArgs()[0]);
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(output))) {
            writer.write("schema=vc_apf_gameplay_tuning_trace/v1\n");
            writer.write("program_md5=" + currentProgram.getExecutableMD5() + "\n");
            for (long target : TARGETS) {
                writer.write("target=" + hx(target) +
                    " refs=" + refs(target) +
                    " fullwords=" + exactFullwords(target) + "\n");
            }
        }
        println("APF_GAMEPLAY_TUNING_TRACE_OK " + output.getAbsolutePath());
    }
}

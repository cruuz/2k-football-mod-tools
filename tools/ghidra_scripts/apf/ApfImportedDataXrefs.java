// Emit read-only APF imported-kernel-data slot and direct-xref evidence.
// @category VisualConcepts.StaticRecomp

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfImportedDataXrefs extends GhidraScript {
    private static final String APF_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private static final String[] NAMES = {
        "ExLoadedCommandLine",
        "XexExecutableModuleHandle",
        "KeTimeStampBundle",
        "ExTimerObjectType",
        "ExSemaphoreObjectType",
        "ExEventObjectType",
        "VdHSIOCalibrationLock",
        "VdGpuClockInMHz",
        "XboxKrnlVersion",
        "ExThreadObjectType",
        "VdGlobalDevice",
        "KeCertMonitorData",
        "KeDebugMonitorData",
    };

    private static final long[] SLOTS = {
        0x82000744L,
        0x820007ACL,
        0x820007CCL,
        0x8200080CL,
        0x8200081CL,
        0x82000828L,
        0x82000870L,
        0x82000888L,
        0x820008BCL,
        0x820008D8L,
        0x82000938L,
        0x8200093CL,
        0x82000940L,
    };

    private String hex(long value) {
        return String.format("0x%08X", value);
    }

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String owner(Address value) {
        Function function = currentProgram.getFunctionManager().getFunctionContaining(value);
        if (function == null) return "none";
        return hex(function.getEntryPoint().getUnsignedOffset()) + ":" + function.getName();
    }

    private String instruction(Address value) {
        Instruction found = currentProgram.getListing().getInstructionAt(value);
        return found == null ? "none" : found.toString().replace('\t', ' ');
    }

    private List<String> referencesTo(Address target) {
        List<String> values = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(target);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Address from = reference.getFromAddress();
            values.add(hex(from.getUnsignedOffset()) + ":" + owner(from) + ":" +
                reference.getReferenceType() + ":" + instruction(from));
        }
        values.sort(String::compareTo);
        return values;
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: ApfImportedDataXrefs.java OUTPUT_FILE");
        }
        String md5 = currentProgram.getExecutableMD5().toLowerCase();
        if (!APF_MD5.equals(md5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + md5);
        }
        if (NAMES.length != SLOTS.length) {
            throw new IllegalStateException("imported-data name/address table mismatch");
        }

        File outputFile = new File(args[0]);
        File parent = outputFile.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            throw new IllegalStateException("cannot create " + parent);
        }

        try (BufferedWriter output = new BufferedWriter(new FileWriter(outputFile))) {
            output.write("slot\tname\traw_be32\txref_count\txrefs\n");
            for (int index = 0; index < SLOTS.length; ++index) {
                Address slot = address(SLOTS[index]);
                long raw = Integer.toUnsignedLong(currentProgram.getMemory().getInt(slot));
                List<String> references = referencesTo(slot);
                output.write(hex(SLOTS[index]) + "\t" + NAMES[index] + "\t" +
                    hex(raw) + "\t" + references.size() + "\t" +
                    String.join(";", references) + "\n");
            }
        }
    }
}

// Decompile the statically justified NFL 2K5 TXTR registration/load call chain.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

public class Nfl2k5TxtrFocusedDecompile extends GhidraScript {
    private static final long[] TARGETS = {
        0x000436A0L, 0x00043720L, 0x000437D0L,
        0x00043E10L, 0x00043E30L, 0x00043E50L, 0x00043E70L,
        0x00044BB0L, 0x00044C10L, 0x00044DF0L, 0x00044E60L,
        0x00044F10L, 0x00044FC0L, 0x00045000L, 0x00045020L, 0x00045070L,
        0x00048700L, 0x00048730L, 0x00048760L, 0x00048FF0L,
        0x0004DBB0L, 0x0004DC00L, 0x00034DF0L, 0x00034910L
    };

    private String addr(Address address) {
        return address.isMemoryAddress() ? String.format("0x%08X", address.getUnsignedOffset()) : address.toString();
    }

    private String name(Function function) {
        if (function == null) return "none";
        String ns = function.getParentNamespace() == null || function.getParentNamespace().isGlobal() ?
            "" : function.getParentNamespace().getName(true) + "::";
        return addr(function.getEntryPoint()) + ":" + ns + function.getName();
    }

    private String relations(Set<Function> functions) {
        List<Function> sorted = new ArrayList<>(functions);
        sorted.sort(Comparator.comparing(Function::getEntryPoint));
        List<String> values = new ArrayList<>();
        for (Function function : sorted) values.add(name(function));
        return String.join(";", values);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) throw new IllegalArgumentException("usage: Nfl2k5TxtrFocusedDecompile.java OUTPUT_DIRECTORY");
        File out = new File(args[0]);
        if (!out.isDirectory() && !out.mkdirs()) throw new IllegalStateException("cannot create " + out);
        File pseudoFile = new File(out, "txtr_focused_pseudo_c.c");
        File disassemblyFile = new File(out, "txtr_focused_disassembly.txt");

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) throw new IllegalStateException("decompiler could not open program");
        int found = 0;
        int missed = 0;
        try (BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile));
             BufferedWriter disassembly = new BufferedWriter(new FileWriter(disassemblyFile))) {
            pseudo.write("/* NFL 2K5 focused TXTR load chain. Recovered types/names are provisional. */\n\n");
            for (long target : TARGETS) {
                Address address = toAddr(target);
                Function function = currentProgram.getFunctionManager().getFunctionAt(address);
                if (function == null) function = currentProgram.getFunctionManager().getFunctionContaining(address);
                if (function == null) {
                    String message = "PORTME: no recovered function contains " + String.format("0x%08X", target) +
                        "; inspect/disassemble this target manually.";
                    pseudo.write("// " + message + "\n\n");
                    disassembly.write(message + "\n\n");
                    missed++;
                    continue;
                }
                found++;
                pseudo.write("/* requested=" + String.format("0x%08X", target) + " function=" + name(function) +
                    " range=" + addr(function.getBody().getMinAddress()) + "-" + addr(function.getBody().getMaxAddress()) +
                    " callers=" + relations(function.getCallingFunctions(monitor)) +
                    " callees=" + relations(function.getCalledFunctions(monitor)) + " */\n");
                DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    pseudo.write(result.getDecompiledFunction().getC());
                }
                else {
                    String reason = result.isTimedOut() ? "timed out after 30 seconds" : result.getErrorMessage();
                    pseudo.write("// PORTME: could not decompile function at " + addr(function.getEntryPoint()) +
                        "; " + reason.replace('\n', ' ').replace('\r', ' ') + "\n");
                }
                pseudo.write("\n");

                disassembly.write("requested=" + String.format("0x%08X", target) + " function=" + name(function) +
                    " callers=" + relations(function.getCallingFunctions(monitor)) +
                    " callees=" + relations(function.getCalledFunctions(monitor)) + "\n");
                InstructionIterator instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
                while (instructions.hasNext()) {
                    Instruction instruction = instructions.next();
                    disassembly.write(addr(instruction.getAddress()) + "  " + instruction + "\n");
                }
                disassembly.write("\n");
            }
        }
        finally {
            decompiler.dispose();
        }
        println("NFL2K5_TXTR_FOCUSED_COMPLETE found=" + found + " missed=" + missed);
    }
}

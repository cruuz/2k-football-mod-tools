// Walk out from the uniform filename-template function toward whatever draws a
// team crest onto a helmet.
//
// 0x849D6BD0 is the function tools/apf_uniform_inventory.py already relies on:
// it holds the twelve UTF-16BE uniform filename templates ("uniform_logo_%02d.iff"
// and siblings) and maps selector slots onto them. Everything that loads a
// per-team uniform asset therefore passes through it or its callers.
//
// The crest is composited into the helmet surface by game code rather than
// sampled by the helmet material, so the rectangle it is drawn into lives on
// that path. This prints the template function and its call graph neighbourhood
// so the compositing routine can be identified.
//
// @category APF

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class ApfUniformLoadChain extends GhidraScript {

    private static final long TEMPLATE_FUNCTION = 0x849d6bd0L;
    private static final int MAX_DECOMPILE = 10;

    @Override
    public void run() throws Exception {
        Function root = getFunctionAt(toAddr(TEMPLATE_FUNCTION));
        if (root == null) {
            println("no function at 0x849d6bd0");
            return;
        }
        println("root: " + root.getName() + " @ " + root.getEntryPoint());

        Set<Function> callers = root.getCallingFunctions(monitor);
        println("direct callers: " + callers.size());
        for (Function caller : callers) {
            println("  " + caller.getName() + " @ " + caller.getEntryPoint()
                + "  (called by " + caller.getCallingFunctions(monitor).size() + ")");
        }

        Set<Function> callees = root.getCalledFunctions(monitor);
        println("direct callees: " + callees.size());
        for (Function callee : callees) {
            println("  " + callee.getName() + " @ " + callee.getEntryPoint());
        }

        List<Function> toRead = new ArrayList<>();
        toRead.add(root);
        toRead.addAll(callers);

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try {
            int read = 0;
            for (Function fn : new LinkedHashSet<>(toRead)) {
                if (read++ >= MAX_DECOMPILE) {
                    println("");
                    println("(stopping after " + MAX_DECOMPILE + " functions)");
                    break;
                }
                println("");
                println("======== " + fn.getName() + " @ " + fn.getEntryPoint());
                DecompileResults results = decompiler.decompileFunction(fn, 180, monitor);
                if (results != null && results.decompileCompleted()) {
                    println(results.getDecompiledFunction().getC());
                } else {
                    println("  (decompilation failed)");
                }
            }
        } finally {
            decompiler.dispose();
        }
        println("APF uniform load chain complete");
    }
}

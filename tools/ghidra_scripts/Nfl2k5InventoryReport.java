// Export deterministic inventory data from the persistent NFL 2K5 Ghidra project.
// @category Xbox.NFL2K5

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

public class Nfl2k5InventoryReport extends GhidraScript {
    private static final Set<String> SDK_NAMESPACES = Set.of(
        "D3D8", "DSOUND", "XAPILIB", "XGRAPHC", "XONLINES",
        "XONLINE", "XNET", "XVOICE", "VOICMAIL", "WMADEC",
        "XPP", "DOLBY", "LIBCMT", "XBOXKRNL", "xboxkrnl.exe"
    );

    private static String q(String value) {
        if (value == null) return "\"\"";
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"")
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\"";
    }

    private static String clean(String value) {
        if (value == null) return "";
        return value.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ');
    }

    private static String hex(Address address) {
        return String.format("0x%08X", address.getUnsignedOffset());
    }

    private static String namespace(Symbol symbol) {
        return symbol.getParentNamespace() == null ? "" : symbol.getParentNamespace().getName(true);
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("usage: Nfl2k5InventoryReport.java OUTPUT_DIRECTORY");
        }
        File out = new File(args[0]);
        if (!out.isDirectory()) throw new IllegalArgumentException("output directory does not exist: " + out);

        Memory memory = currentProgram.getMemory();
        MemoryBlock xtlid = memory.getBlock(".XTLID");
        Set<Long> xtlidAddresses = new HashSet<>();
        File xtlidFile = new File(out, "xtlid_records.tsv");
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(xtlidFile))) {
            writer.write("record_address\tid\ttarget_address\ttarget_symbols\n");
            if (xtlid != null) {
                for (Address record = xtlid.getStart(); record.compareTo(xtlid.getEnd()) <= 0; record = record.add(8)) {
                    if (record.add(7).compareTo(xtlid.getEnd()) > 0) break;
                    long id = Integer.toUnsignedLong(memory.getInt(record));
                    long target = Integer.toUnsignedLong(memory.getInt(record.add(4)));
                    if (id == 0 || target == 0) continue;
                    xtlidAddresses.add(target);
                    Address targetAddress = toAddr(target);
                    List<String> names = new ArrayList<>();
                    Symbol[] at = currentProgram.getSymbolTable().getSymbols(targetAddress);
                    for (Symbol symbol : at) {
                        names.add(namespace(symbol) + "::" + symbol.getName());
                    }
                    names.sort(String::compareTo);
                    writer.write(hex(record) + "\t" + String.format("0x%08X", id) + "\t" +
                        String.format("0x%08X", target) + "\t" + clean(String.join(";", names)) + "\n");
                }
            }
        }

        List<Symbol> sdkSymbols = new ArrayList<>();
        SymbolIterator symbols = currentProgram.getSymbolTable().getAllSymbols(true);
        while (symbols.hasNext()) {
            Symbol symbol = symbols.next();
            String ns = namespace(symbol);
            String root = ns.contains("::") ? ns.substring(0, ns.indexOf("::")) : ns;
            if (SDK_NAMESPACES.contains(root)) sdkSymbols.add(symbol);
        }
        sdkSymbols.sort((left, right) -> {
            int byAddress = left.getAddress().compareTo(right.getAddress());
            return byAddress != 0 ? byAddress : left.getName().compareTo(right.getName());
        });
        File sdkFile = new File(out, "sdk_symbols.tsv");
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(sdkFile))) {
            writer.write("address\tname\tnamespace\tsource\tprimary\tfunction_at\txtlid_target\n");
            for (Symbol symbol : sdkSymbols) {
                Function function = currentProgram.getFunctionManager().getFunctionAt(symbol.getAddress());
                writer.write(hex(symbol.getAddress()) + "\t" + clean(symbol.getName()) + "\t" +
                    clean(namespace(symbol)) + "\t" + symbol.getSource() + "\t" + symbol.isPrimary() + "\t" +
                    (function == null ? "" : clean(function.getName())) + "\t" +
                    xtlidAddresses.contains(symbol.getAddress().getUnsignedOffset()) + "\n");
            }
        }

        long functions = 0;
        long sdkFunctions = 0;
        long xtlidFunctions = 0;
        long externalFunctions = 0;
        long thunks = 0;
        for (Function function : currentProgram.getFunctionManager().getFunctions(true)) {
            functions++;
            if (function.isThunk()) thunks++;
            if (xtlidAddresses.contains(function.getEntryPoint().getUnsignedOffset())) xtlidFunctions++;
            String ns = function.getParentNamespace() == null ? "" : function.getParentNamespace().getName(true);
            String root = ns.contains("::") ? ns.substring(0, ns.indexOf("::")) : ns;
            boolean sdk = SDK_NAMESPACES.contains(root);
            if (!sdk) {
                Symbol[] at = currentProgram.getSymbolTable().getSymbols(function.getEntryPoint());
                for (Symbol symbol : at) {
                    String sns = namespace(symbol);
                    String sroot = sns.contains("::") ? sns.substring(0, sns.indexOf("::")) : sns;
                    if (SDK_NAMESPACES.contains(sroot)) { sdk = true; break; }
                }
            }
            if (sdk) sdkFunctions++;
        }
        FunctionIterator externalIterator =
            currentProgram.getFunctionManager().getExternalFunctions();
        while (externalIterator.hasNext()) {
            externalIterator.next();
            externalFunctions++;
        }

        File summary = new File(out, "analysis_summary.json");
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(summary))) {
            writer.write("{\n");
            writer.write("  \"program_name\": " + q(currentProgram.getName()) + ",\n");
            writer.write("  \"executable_path\": " + q(currentProgram.getExecutablePath()) + ",\n");
            writer.write("  \"executable_format\": " + q(currentProgram.getExecutableFormat()) + ",\n");
            writer.write("  \"md5\": " + q(currentProgram.getExecutableMD5()) + ",\n");
            writer.write("  \"sha256\": " + q(currentProgram.getExecutableSHA256()) + ",\n");
            writer.write("  \"language_id\": " + q(currentProgram.getLanguageID().toString()) + ",\n");
            writer.write("  \"compiler_spec_id\": " + q(currentProgram.getCompilerSpec().getCompilerSpecID().toString()) + ",\n");
            writer.write("  \"image_base\": " + q(currentProgram.getImageBase().toString()) + ",\n");
            writer.write("  \"function_count\": " + functions + ",\n");
            writer.write("  \"sdk_flagged_function_count\": " + sdkFunctions + ",\n");
            writer.write("  \"non_sdk_function_count\": " + (functions - sdkFunctions) + ",\n");
            writer.write("  \"external_function_count\": " + externalFunctions + ",\n");
            writer.write("  \"thunk_function_count\": " + thunks + ",\n");
            writer.write("  \"xtlid_record_count\": " + xtlidAddresses.size() + ",\n");
            writer.write("  \"xtlid_target_function_count\": " + xtlidFunctions + ",\n");
            writer.write("  \"sdk_namespace_symbol_count\": " + sdkSymbols.size() + "\n");
            writer.write("}\n");
        }
        println("NFL2K5_INVENTORY_COMPLETE functions=" + functions + " sdk_flagged=" + sdkFunctions +
            " xtlid_targets=" + xtlidAddresses.size() + " sdk_symbols=" + sdkSymbols.size());
    }
}

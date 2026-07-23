// Export a resumable shard of the NFL 2K5 function ledger and Ghidra pseudo-C.
// This script is read-only with respect to the loaded program.
// @category Xbox.NFL2K5

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressRange;
import ghidra.program.model.address.AddressRangeIterator;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.ExternalReference;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

public class Nfl2k5FunctionExport extends GhidraScript {
    private static final int MAX_RELATIONS = 32;
    private static final int MAX_STRING_REFS = 8;
    private static final int MAX_STRING_CHARS = 160;
    private static final Set<String> SDK_NAMESPACES = Set.of(
        "D3D8", "DSOUND", "XAPILIB", "XGRAPHC", "XONLINES",
        "XONLINE", "XNET", "XVOICE", "VOICMAIL", "WMADEC",
        "XPP", "DOLBY", "LIBCMT", "XBOXKRNL", "xboxkrnl.exe"
    );
    private static final Set<String> EMBEDDED_LIBRARY_SECTIONS = Set.of(
        "D3D", "DSOUND", "WMADEC", "XGRPH", "XNET", "XONLINE",
        "XPP", "DOLBY", "XON_RD", "dspimage"
    );

    private Map<Long, List<String>> xbsdbByAddress;
    private Set<Long> xtlidAddresses;
    private Set<String> sharedStrings;
    private Map<Address, String> kernelImportSlots;

    private static String clean(String value) {
        if (value == null) return "";
        return value.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ');
    }

    private static String cComment(String value) {
        if (value == null) return "";
        return value.replace("*/", "* /").replace('\r', ' ').replace('\n', ' ');
    }

    private static String json(String value) {
        if (value == null) return "\"\"";
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"")
            .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\"";
    }

    private String addr(Address address) {
        if (address == null) return "";
        if (address.isMemoryAddress()) {
            return String.format("0x%08X", address.getUnsignedOffset());
        }
        return address.toString();
    }

    private String namespace(Function function) {
        if (function.getParentNamespace() == null || function.getParentNamespace().isGlobal()) return "Global";
        return function.getParentNamespace().getName(true);
    }

    private String qualified(Function function) {
        String ns = namespace(function);
        return "Global".equals(ns) ? function.getName() : ns + "::" + function.getName();
    }

    private String namespaceRoot(String namespace) {
        if (namespace == null) return "";
        int split = namespace.indexOf("::");
        return split < 0 ? namespace : namespace.substring(0, split);
    }

    private Map<Long, List<String>> readXbsdb(File file) throws Exception {
        Map<Long, List<String>> result = new HashMap<>();
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) {
                int split = line.lastIndexOf(" = 0x");
                if (split <= 0) continue;
                String name = line.substring(0, split).trim();
                long address = Long.parseUnsignedLong(line.substring(split + 5).trim(), 16);
                result.computeIfAbsent(address, unused -> new ArrayList<>()).add(name);
            }
        }
        for (List<String> names : result.values()) Collections.sort(names);
        return result;
    }

    private Set<String> readSharedStrings(File file) throws Exception {
        Set<String> result = new HashSet<>();
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line = reader.readLine();
            while ((line = reader.readLine()) != null) {
                String[] fields = line.split("\\t", 4);
                if (fields.length >= 2) result.add(fields[1].toLowerCase(Locale.ROOT));
            }
        }
        return result;
    }

    private Set<Long> readXtlidTargets() throws Exception {
        Set<Long> result = new HashSet<>();
        MemoryBlock xtlid = currentProgram.getMemory().getBlock(".XTLID");
        if (xtlid == null) return result;
        for (Address record = xtlid.getStart(); record.compareTo(xtlid.getEnd()) <= 0; record = record.add(8)) {
            if (record.add(7).compareTo(xtlid.getEnd()) > 0) break;
            long id = Integer.toUnsignedLong(currentProgram.getMemory().getInt(record));
            long target = Integer.toUnsignedLong(currentProgram.getMemory().getInt(record.add(4)));
            if (id != 0 && target != 0) result.add(target);
        }
        return result;
    }

    private Map<Address, String> readKernelImportSlots() {
        Map<Address, String> result = new HashMap<>();
        ReferenceIterator references = currentProgram.getReferenceManager().getExternalReferences();
        while (references.hasNext()) {
            Reference reference = references.next();
            if (!(reference instanceof ExternalReference)) continue;
            ExternalReference external = (ExternalReference) reference;
            if ("xboxkrnl.exe".equalsIgnoreCase(external.getLibraryName())) {
                result.put(reference.getFromAddress(), external.getLabel());
            }
        }
        return result;
    }

    private List<Function> allFunctions() {
        LinkedHashMap<String, Function> unique = new LinkedHashMap<>();
        FunctionIterator internal = currentProgram.getFunctionManager().getFunctions(true);
        while (internal.hasNext()) {
            Function function = internal.next();
            unique.put(function.getEntryPoint().toString(), function);
        }
        FunctionIterator external = currentProgram.getFunctionManager().getExternalFunctions();
        while (external.hasNext()) {
            Function function = external.next();
            unique.put(function.getEntryPoint().toString(), function);
        }
        List<Function> result = new ArrayList<>(unique.values());
        result.sort((left, right) -> {
            if (left.isExternal() != right.isExternal()) return left.isExternal() ? 1 : -1;
            return left.getEntryPoint().compareTo(right.getEntryPoint());
        });
        return result;
    }

    private String bodyRanges(Function function) {
        List<String> ranges = new ArrayList<>();
        AddressRangeIterator iterator = function.getBody().getAddressRanges(true);
        while (iterator.hasNext()) {
            AddressRange range = iterator.next();
            ranges.add(addr(range.getMinAddress()) + "-" + addr(range.getMaxAddress()));
        }
        return String.join(",", ranges);
    }

    private List<String> relationNames(Set<Function> relations) {
        List<Function> functions = new ArrayList<>(relations);
        functions.sort(Comparator.comparing(Function::getEntryPoint));
        List<String> names = new ArrayList<>();
        for (Function function : functions) {
            if (names.size() == MAX_RELATIONS) break;
            names.add(addr(function.getEntryPoint()) + ":" + qualified(function));
        }
        return names;
    }

    private static class StringRefs {
        int directCount;
        int sharedCount;
        List<String> direct = new ArrayList<>();
        List<String> shared = new ArrayList<>();
    }

    private String stringValue(Data data) {
        Object value = data.getValue();
        String text = value == null ? data.getDefaultValueRepresentation() : value.toString();
        text = clean(text);
        if (text.length() > MAX_STRING_CHARS) text = text.substring(0, MAX_STRING_CHARS) + "...";
        return text;
    }

    private StringRefs referencedStrings(Function function) {
        StringRefs result = new StringRefs();
        Set<Address> seen = new HashSet<>();
        InstructionIterator instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            for (Reference reference : instruction.getReferencesFrom()) {
                Address target = reference.getToAddress();
                if (target == null || !target.isMemoryAddress()) continue;
                Data data = currentProgram.getListing().getDataContaining(target);
                if (data == null || !data.hasStringValue() || !seen.add(data.getAddress())) continue;
                String value = stringValue(data);
                String item = addr(data.getAddress()) + "=" + value;
                result.directCount++;
                if (result.direct.size() < MAX_STRING_REFS) result.direct.add(item);
                if (sharedStrings.contains(value.toLowerCase(Locale.ROOT))) {
                    result.sharedCount++;
                    if (result.shared.size() < MAX_STRING_REFS) result.shared.add(item);
                }
            }
        }
        return result;
    }

    private List<String> kernelImportsCalled(Function function) {
        Set<String> names = new LinkedHashSet<>();
        InstructionIterator instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
        while (instructions.hasNext()) {
            Instruction instruction = instructions.next();
            for (Reference reference : instruction.getReferencesFrom()) {
                String name = kernelImportSlots.get(reference.getToAddress());
                if (name != null) names.add(name);
            }
        }
        List<String> result = new ArrayList<>(names);
        Collections.sort(result);
        if (result.size() > MAX_RELATIONS) return new ArrayList<>(result.subList(0, MAX_RELATIONS));
        return result;
    }

    private String functionSection(Function function) {
        if (function.isExternal()) return "EXTERNAL";
        MemoryBlock block = currentProgram.getMemory().getBlock(function.getEntryPoint());
        return block == null ? "UNMAPPED" : block.getName();
    }

    private static class Classification {
        String name;
        String evidence;
        boolean gameCodeCandidate;
        String sdkStatus;
    }

    private Classification classify(Function function, String section, List<String> xbsdbNames, boolean xtlid) {
        Classification result = new Classification();
        String ns = namespace(function);
        boolean sdkNamespace = SDK_NAMESPACES.contains(namespaceRoot(ns));
        List<String> statuses = new ArrayList<>();
        if (!xbsdbNames.isEmpty()) statuses.add("XbSymbolDatabase_exact_address");
        if (xtlid) statuses.add("XTLID_exact_target");
        if (sdkNamespace) statuses.add("SDK_namespace_label");
        if (EMBEDDED_LIBRARY_SECTIONS.contains(section)) statuses.add("linked_library_section");
        result.sdkStatus = statuses.isEmpty() ? "none" : String.join(";", statuses);

        if (function.isExternal()) {
            String library = function.getExternalLocation() == null ? "" : function.getExternalLocation().getLibraryName();
            result.name = "platform_import";
            result.evidence = "Ghidra external function; library=" + library;
        }
        else if (!xbsdbNames.isEmpty()) {
            result.name = "sdk_library_signature_candidate";
            result.evidence = "exact address emitted by XbSymbolDatabase v3.1.160: " + String.join(";", xbsdbNames);
        }
        else if (xtlid) {
            result.name = "sdk_library_xtlid_candidate";
            result.evidence = "entry address is an exact target in the executable's .XTLID table";
        }
        else if (sdkNamespace) {
            result.name = "sdk_library_namespace_candidate";
            result.evidence = "function carries an analyzer-applied SDK namespace label: " + ns;
        }
        else if (EMBEDDED_LIBRARY_SECTIONS.contains(section)) {
            result.name = "embedded_library_unmatched";
            result.evidence = "function entry lies in linked library section " + section + " but has no exact XbSymbolDatabase/XTLID match";
        }
        else if (".text".equals(section)) {
            result.name = "game_or_engine_candidate";
            result.evidence = "unmatched function in main .text; no source symbol proves a narrower subsystem";
            result.gameCodeCandidate = true;
        }
        else {
            result.name = "recovered_non_text_candidate";
            result.evidence = "Ghidra recovered a function in section " + section + "; classification remains unverified";
        }
        return result;
    }

    private String portme(String status, Function function, int timeout, String detail) {
        String at = addr(function.getEntryPoint());
        if ("timeout".equals(status)) {
            return "PORTME: Ghidra decompilation timed out after " + timeout +
                " seconds for function at " + at + "; inspect its x86 disassembly, repair flow/data boundaries, and retry.";
        }
        if ("cancelled".equals(status)) {
            return "PORTME: decompilation was cancelled for function at " + at +
                "; rerun this shard and inspect the function manually if cancellation repeats.";
        }
        return "PORTME: could not decompile function at " + at + "; Ghidra reported: " + clean(detail) +
            ". Inspect x86 disassembly and inline data/control-flow boundaries manually.";
    }

    private String manualRecovery(Function function) {
        if (!function.getEntryPoint().isMemoryAddress() ||
            function.getEntryPoint().getUnsignedOffset() != 0x00115850L) return null;
        return String.join("\n",
            "/*",
            " * Manual control-flow reconstruction for the sole genuine function that",
            " * Ghidra's full C action timed out on at both 5 and 60 seconds.",
            " * Evidence: hard_functions/disassembly_and_pcode.txt.",
            " * The record size, array bounds, shifts, and copies below are exact.",
            " * Names/types and the implicit-register ABI adapters remain provisional.",
            " */",
            "typedef struct NFL2K5_00115850_record {",
            "    unsigned char key[0x18];",
            "    unsigned char payload[0x48];",
            "} NFL2K5_00115850_record;",
            "",
            "void FUN_00115850(void *source, unsigned int key_argument)",
            "{",
            "    unsigned char key[0x18];",
            "    unsigned char *manager;",
            "    NFL2K5_00115850_record *four_record_set;",
            "    NFL2K5_00115850_record *two_record_set;",
            "    unsigned int slot;",
            "",
            "    manager = (unsigned char *)FUN_000c5c00() + 0x35f0;",
            "    four_record_set = (NFL2K5_00115850_record *)(manager + 0xd8);",
            "    two_record_set = (NFL2K5_00115850_record *)(manager + 0x258);",
            "",
            "    /* PORTME: FUN_00113ca0 receives key_argument, 1.0f, 1 on the stack",
            "       and writes the six-dword key through implicit EBX=&key while source",
            "       remains in ESI. Implement this as an explicit ABI adapter on Linux. */",
            "    manual_FUN_00113ca0_build_key(key, source, key_argument, 1.0f, 1);",
            "",
            "    for (slot = 0; slot < 4; ++slot) {",
            "        if (FUN_00113f60(&four_record_set[slot], key) != 0) break;",
            "    }",
            "    if (slot != 4) {",
            "        if (slot < 3) {",
            "            memmove(&four_record_set[slot + 1], &four_record_set[slot],",
            "                    (3 - slot) * sizeof(*four_record_set));",
            "        }",
            "        memcpy(four_record_set[slot].key, key, sizeof(key));",
            "        /* PORTME: original FUN_00115410 takes source in ESI and the",
            "           destination record in EDI; expose both arguments explicitly. */",
            "        manual_FUN_00115410_fill(source, &four_record_set[slot]);",
            "    }",
            "",
            "    if (FUN_000e6740(source) != 0) {",
            "        for (slot = 0; slot < 2; ++slot) {",
            "            if (FUN_00113f60(&two_record_set[slot], key) != 0) break;",
            "        }",
            "        if (slot != 2) {",
            "            if (slot < 1) {",
            "                memmove(&two_record_set[slot + 1], &two_record_set[slot],",
            "                        (1 - slot) * sizeof(*two_record_set));",
            "            }",
            "            memcpy(two_record_set[slot].key, key, sizeof(key));",
            "            manual_FUN_00115410_fill(source, &two_record_set[slot]);",
            "        }",
            "    }",
            "}",
            "");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 6) {
            throw new IllegalArgumentException(
                "usage: Nfl2k5FunctionExport.java OUTPUT_ROOT XBSDB_FILE COMMON_STRINGS_TSV START END_EXCLUSIVE TIMEOUT_SECONDS");
        }
        File root = new File(args[0]);
        File xbsdbFile = new File(args[1]);
        File commonStringsFile = new File(args[2]);
        int requestedStart = Integer.parseInt(args[3]);
        int requestedEnd = Integer.parseInt(args[4]);
        int timeout = Integer.parseInt(args[5]);
        if (timeout <= 0) throw new IllegalArgumentException("timeout must be positive");

        File ledgerDirectory = new File(root, "ledger_shards");
        File pseudoDirectory = new File(root, "pseudo_c");
        File manifestDirectory = new File(root, "manifests");
        if (!ledgerDirectory.isDirectory() && !ledgerDirectory.mkdirs()) throw new IllegalStateException("cannot create " + ledgerDirectory);
        if (!pseudoDirectory.isDirectory() && !pseudoDirectory.mkdirs()) throw new IllegalStateException("cannot create " + pseudoDirectory);
        if (!manifestDirectory.isDirectory() && !manifestDirectory.mkdirs()) throw new IllegalStateException("cannot create " + manifestDirectory);

        xbsdbByAddress = readXbsdb(xbsdbFile);
        xtlidAddresses = readXtlidTargets();
        sharedStrings = readSharedStrings(commonStringsFile);
        kernelImportSlots = readKernelImportSlots();
        List<Function> functions = allFunctions();
        int start = Math.max(0, requestedStart);
        int end = Math.min(functions.size(), requestedEnd);
        if (start >= end) throw new IllegalArgumentException("empty range " + start + ".." + end + " for " + functions.size() + " functions");

        String stem = String.format("shard_%06d_%06d", start, end - 1);
        File ledgerFile = new File(ledgerDirectory, stem + ".tsv");
        File pseudoFile = new File(pseudoDirectory, stem + ".c");
        File manifestFile = new File(manifestDirectory, stem + ".json");
        int successes = 0;
        int timeouts = 0;
        int errors = 0;
        int manualRecoveries = 0;
        int externals = 0;
        int gameCandidates = 0;
        long beginNanos = System.nanoTime();

        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) throw new IllegalStateException("decompiler could not open program");
        try (BufferedWriter ledger = new BufferedWriter(new FileWriter(ledgerFile));
             BufferedWriter pseudo = new BufferedWriter(new FileWriter(pseudoFile))) {
            ledger.write("index\taddress\tend\tsize\tbody_ranges\tsection\tname\tnamespace\tname_source\tprototype\tsignature_source\tcalling_convention\texternal\tthunk\timport_status\tkernel_imports_called\txbsdb_signature\txbsdb_names\txtlid_target\tsdk_status\tgame_code_candidate\tcaller_count\tcallers\tcallee_count\tcallees\tdirect_string_ref_count\tdirect_strings\tcross_title_string_ref_count\tcross_title_strings\tclassification\tclassification_evidence\tdecompile_status\tdecompile_seconds\tportme\tpseudo_c_file\n");
            pseudo.write("/* NFL 2K5 Ghidra pseudo-C shard " + start + ".." + (end - 1) +
                ". Analysis aid only; recovered types and names are provisional. */\n\n");

            for (int index = start; index < end; index++) {
                monitor.checkCancelled();
                Function function = functions.get(index);
                long addressValue = function.getEntryPoint().isMemoryAddress() ?
                    function.getEntryPoint().getUnsignedOffset() : -1;
                List<String> xbsdbNames = xbsdbByAddress.getOrDefault(addressValue, Collections.emptyList());
                boolean xtlid = xtlidAddresses.contains(addressValue);
                String section = functionSection(function);
                Classification classification = classify(function, section, xbsdbNames, xtlid);
                if (classification.gameCodeCandidate) gameCandidates++;

                Set<Function> calling = function.getCallingFunctions(monitor);
                Set<Function> called = function.getCalledFunctions(monitor);
                List<String> callers = relationNames(calling);
                List<String> callees = relationNames(called);
                List<String> importsCalled = function.isExternal() ? Collections.emptyList() : kernelImportsCalled(function);
                StringRefs strings = function.isExternal() ? new StringRefs() : referencedStrings(function);

                String status;
                String code = "";
                String detail = "";
                String portme = "";
                long decompileStart = System.nanoTime();
                if (function.isExternal()) {
                    status = "not_applicable_external";
                    externals++;
                }
                else {
                    String manualCode = manualRecovery(function);
                    if (manualCode != null) {
                        status = "manual_recovery_from_disassembly";
                        code = manualCode;
                        portme = "PORTME: automated Ghidra C decompilation timed out after both 5 and 60 seconds for function at " +
                            addr(function.getEntryPoint()) + "; the emitted manual control-flow reconstruction covers every instruction, " +
                            "but a human must validate the implicit EBX/ESI/EDI helper ABI and provisional record types before porting.";
                        manualRecoveries++;
                    }
                    else {
                    try {
                        DecompileResults result = decompiler.decompileFunction(function, timeout, monitor);
                        detail = result.getErrorMessage();
                        if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                            status = "success";
                            code = result.getDecompiledFunction().getC();
                            successes++;
                        }
                        else if (result.isTimedOut()) {
                            status = "timeout";
                            portme = portme(status, function, timeout, detail);
                            timeouts++;
                        }
                        else if (result.isCancelled()) {
                            status = "cancelled";
                            portme = portme(status, function, timeout, detail);
                            errors++;
                        }
                        else {
                            status = "error";
                            portme = portme(status, function, timeout, detail);
                            errors++;
                        }
                    }
                    catch (Throwable throwable) {
                        status = "exception";
                        detail = throwable.getClass().getName() + ": " + throwable.getMessage();
                        portme = portme(status, function, timeout, detail);
                        errors++;
                    }
                    }
                }
                double seconds = (System.nanoTime() - decompileStart) / 1_000_000_000.0;

                String importStatus = function.isExternal() ? "external_import" :
                    (importsCalled.isEmpty() ? "none_observed" : "calls_xboxkrnl_imports");
                Address bodyEnd = function.getBody().getMaxAddress();
                long bodySize = function.getBody().getNumAddresses();
                String convention = function.getCallingConventionName();

                ledger.write(index + "\t" + addr(function.getEntryPoint()) + "\t" + addr(bodyEnd) + "\t" + bodySize + "\t" +
                    clean(bodyRanges(function)) + "\t" + clean(section) + "\t" + clean(function.getName()) + "\t" +
                    clean(namespace(function)) + "\t" + function.getSymbol().getSource() + "\t" +
                    clean(function.getPrototypeString(true, true)) + "\t" + function.getSignatureSource() + "\t" +
                    clean(convention) + "\t" + function.isExternal() + "\t" + function.isThunk() + "\t" +
                    importStatus + "\t" + clean(String.join(";", importsCalled)) + "\t" + !xbsdbNames.isEmpty() + "\t" +
                    clean(String.join(";", xbsdbNames)) + "\t" + xtlid + "\t" + clean(classification.sdkStatus) + "\t" +
                    classification.gameCodeCandidate + "\t" + calling.size() + "\t" + clean(String.join(";", callers)) + "\t" +
                    called.size() + "\t" + clean(String.join(";", callees)) + "\t" + strings.directCount + "\t" +
                    clean(String.join(";", strings.direct)) + "\t" + strings.sharedCount + "\t" +
                    clean(String.join(";", strings.shared)) + "\t" + classification.name + "\t" +
                    clean(classification.evidence) + "\t" + status + "\t" + String.format(Locale.ROOT, "%.6f", seconds) + "\t" +
                    clean(portme) + "\t" + "pseudo_c/" + pseudoFile.getName() + "\n");

                pseudo.write("/*\n * index: " + index + "\n * address: " + addr(function.getEntryPoint()) +
                    "\n * range: " + cComment(bodyRanges(function)) + "\n * section: " + cComment(section) +
                    "\n * symbol: " + cComment(qualified(function)) + "\n * classification: " + classification.name +
                    "\n * evidence: " + cComment(classification.evidence) + "\n * callers: " + cComment(String.join(";", callers)) +
                    "\n * callees: " + cComment(String.join(";", callees)) + "\n * kernel imports: " +
                    cComment(String.join(";", importsCalled)) + "\n * direct strings: " + cComment(String.join(";", strings.direct)) +
                    "\n * cross-title strings: " + cComment(String.join(";", strings.shared)) + "\n */\n");
                if ("success".equals(status) || "manual_recovery_from_disassembly".equals(status)) {
                    pseudo.write(code);
                    if (!code.endsWith("\n")) pseudo.write("\n");
                }
                else if (function.isExternal()) {
                    pseudo.write("/* External declaration recovered by Ghidra: " +
                        cComment(function.getPrototypeString(true, true)) + " */\n");
                }
                else {
                    pseudo.write("// " + cComment(portme) + "\n");
                }
                pseudo.write("\n");
                ledger.flush();
                pseudo.flush();
                if ((index - start + 1) % 64 == 0 || index + 1 == end) {
                    println("NFL2K5_EXPORT_PROGRESS index=" + (index + 1) + "/" + functions.size() +
                        " shard=" + start + ".." + (end - 1) + " success=" + successes +
                        " manual=" + manualRecoveries + " timeout=" + timeouts +
                        " error=" + errors + " external=" + externals);
                }
            }
        }
        finally {
            decompiler.dispose();
        }

        double elapsed = (System.nanoTime() - beginNanos) / 1_000_000_000.0;
        try (BufferedWriter manifest = new BufferedWriter(new FileWriter(manifestFile))) {
            manifest.write("{\n");
            manifest.write("  \"program\": " + json(currentProgram.getName()) + ",\n");
            manifest.write("  \"program_md5\": " + json(currentProgram.getExecutableMD5()) + ",\n");
            manifest.write("  \"total_recovered_functions\": " + functions.size() + ",\n");
            manifest.write("  \"start_index\": " + start + ",\n");
            manifest.write("  \"end_index_exclusive\": " + end + ",\n");
            manifest.write("  \"row_count\": " + (end - start) + ",\n");
            manifest.write("  \"decompile_timeout_seconds\": " + timeout + ",\n");
            manifest.write("  \"decompile_success_count\": " + successes + ",\n");
            manifest.write("  \"decompile_timeout_count\": " + timeouts + ",\n");
            manifest.write("  \"decompile_error_count\": " + errors + ",\n");
            manifest.write("  \"manual_recovery_count\": " + manualRecoveries + ",\n");
            manifest.write("  \"external_count\": " + externals + ",\n");
            manifest.write("  \"game_or_engine_candidate_count\": " + gameCandidates + ",\n");
            manifest.write("  \"xbsdb_input_candidate_count\": 651,\n");
            manifest.write("  \"elapsed_seconds\": " + String.format(Locale.ROOT, "%.6f", elapsed) + ",\n");
            manifest.write("  \"ledger\": " + json("ledger_shards/" + ledgerFile.getName()) + ",\n");
            manifest.write("  \"pseudo_c\": " + json("pseudo_c/" + pseudoFile.getName()) + "\n");
            manifest.write("}\n");
        }
        println("NFL2K5_EXPORT_COMPLETE range=" + start + ".." + (end - 1) + " total=" + functions.size() +
            " success=" + successes + " manual=" + manualRecoveries +
            " timeout=" + timeouts + " error=" + errors + " external=" + externals);
    }
}

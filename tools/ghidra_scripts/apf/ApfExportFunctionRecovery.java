// Export an exhaustive, sharded APF 2K8 function ledger and Ghidra pseudo-C.
// @category Xbox.APF2K8

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.time.Instant;
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
import java.util.TreeMap;
import java.util.regex.Pattern;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.decompiler.DecompiledFunction;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressIterator;
import ghidra.program.model.address.AddressRange;
import ghidra.program.model.address.AddressRangeIterator;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Namespace;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.program.model.symbol.SourceType;

/**
 * Run only against the canonical XEXLoaderWV program named {@code default.xex}.
 *
 * Arguments:
 *   OUTPUT_DIRECTORY IMPORTS_TSV WARNINGS_FILE COMMON_STRINGS_TSV [TIMEOUT_SECONDS]
 *
 * The script deliberately does not rename, retype, or otherwise mutate the program.
 * Headless reproduction should additionally pass {@code -readOnly -noanalysis}.
 */
public class ApfExportFunctionRecovery extends GhidraScript {
    private static final String EXPECTED_PROGRAM_NAME = "default.xex";
    private static final String EXPECTED_FORMAT = "XEX Loader by Warranty Voider";
    private static final String EXPECTED_MD5 = "217eea6084c3d03f0f1143802b1f5636";
    private static final String EXPECTED_LANGUAGE = "PowerPC:BE:64:A2ALT-32addr";
    private static final long EXPECTED_ENTRY = 0x84BE9D08L;
    private static final long APF_IMAGE_BASE = 0x82000000L;
    private static final int EXPECTED_FUNCTIONS = 21347;
    private static final int EXPECTED_PDATA = 18472;
    private static final int EXPECTED_IMPORT_THUNKS = 334;
    private static final int EXPECTED_WARNINGS = 33;
    private static final int LEDGER_SHARD_SIZE = 512;
    private static final int PSEUDOC_SHARD_SIZE = 256;
    private static final int MAX_DIRECT_STRINGS = 32;

    private static final Pattern DEFAULT_NAME =
        Pattern.compile("(?:FUN|Function|LAB|SUB|thunk_FUN)_[0-9A-Fa-f]+(?:_.*)?");
    private static final Pattern XDK_NAME = Pattern.compile(
        "(?:D3D|XG|XAudio|X3DAudio|Xapi|Xam|XNet|XOnline|Xex|XMP|Rtl|Nt|Ke|Kf|Mm|Ex|Ob|Vd|Xe)[A-Z0-9_].*");
    private static final Pattern HELPER_NAME = Pattern.compile(
        "(?:__.*|_save.*|_rest.*|_ftol.*|memcpy|memmove|memset|memcmp|strlen|strcmp|strcpy|strncpy|malloc|calloc|realloc|free|operator.*)");

    private static final class ImportInfo {
        String library;
        String version;
        long referenceAddress;
        long thunkAddress;
        long rawWord;
        int hint;
        int ordinal;
        String name;
    }

    private static final class PdataInfo {
        int index;
        long metadata;
    }

    private static final class CrossString {
        String value;
        String encoding;
        double score;
    }

    private static final class DirectString {
        long address;
        String value;
        String source;
        String encoding;
        boolean crossTitle;
    }

    private static final class StringRefs {
        List<DirectString> kept = new ArrayList<>();
        int total;
    }

    private static final class Classification {
        String value;
        String evidence;
    }

    private static final class TextShardWriter implements AutoCloseable {
        private BufferedWriter writer;
        private File file;

        void open(File next, String header) throws Exception {
            close();
            file = next;
            writer = new BufferedWriter(new FileWriter(next), 1024 * 1024);
            writer.write(header);
        }

        String relativeTo(File root) {
            return root.toPath().relativize(file.toPath()).toString().replace(File.separatorChar, '/');
        }

        void write(String text) throws Exception {
            writer.write(text);
        }

        void flush() throws Exception {
            if (writer != null) {
                writer.flush();
            }
        }

        @Override
        public void close() throws Exception {
            if (writer != null) {
                writer.flush();
                writer.close();
                writer = null;
            }
        }
    }

    private static String json(String value) {
        if (value == null) {
            return "null";
        }
        StringBuilder out = new StringBuilder(value.length() + 16).append('"');
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '\\': out.append("\\\\"); break;
                case '"': out.append("\\\""); break;
                case '\b': out.append("\\b"); break;
                case '\f': out.append("\\f"); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 0x20 || c == 0x7f) {
                        out.append(String.format("\\u%04x", (int)c));
                    }
                    else {
                        out.append(c);
                    }
            }
        }
        return out.append('"').toString();
    }

    private static String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private static long parseHex(String text) {
        String value = text.trim();
        if (value.startsWith("0x") || value.startsWith("0X")) {
            value = value.substring(2);
        }
        return Long.parseUnsignedLong(value, 16);
    }

    private static String sanitizeMessage(String text) {
        if (text == null || text.isBlank()) {
            return "no diagnostic supplied by Ghidra";
        }
        return text.replace('\r', ' ').replace('\n', ' ').replaceAll("\\s+", " ").trim();
    }

    private static String commentSafe(String text) {
        return text.replace("*/", "* /");
    }

    private static int countOccurrences(String text, String needle) {
        if (text == null || needle.isEmpty()) {
            return 0;
        }
        int count = 0;
        int offset = 0;
        while ((offset = text.indexOf(needle, offset)) >= 0) {
            count++;
            offset += needle.length();
        }
        return count;
    }

    private static int hardPseudoCWarningCount(String text) {
        return countOccurrences(text, "Control flow encountered bad instruction data") +
            countOccurrences(text, "Bad instruction - Truncating control flow here") +
            countOccurrences(text, "Could not recover jumptable");
    }

    private static void requireDirectory(File directory) {
        if (directory.isDirectory()) {
            return;
        }
        if (!directory.mkdirs()) {
            throw new IllegalArgumentException("could not create directory: " + directory);
        }
    }

    private static Map<Long, ImportInfo> readImports(File file) throws Exception {
        Map<Long, ImportInfo> result = new HashMap<>();
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line = reader.readLine();
            if (line == null || !line.startsWith("library\t")) {
                throw new IllegalArgumentException("unexpected APF imports TSV header: " + file);
            }
            while ((line = reader.readLine()) != null) {
                String[] fields = line.split("\\t", -1);
                if (fields.length != 8 || fields[3].isBlank()) {
                    continue; // The 13 imported data exports do not represent functions.
                }
                ImportInfo info = new ImportInfo();
                info.library = fields[0];
                info.version = fields[1];
                info.referenceAddress = parseHex(fields[2]);
                info.thunkAddress = parseHex(fields[3]);
                info.rawWord = parseHex(fields[4]);
                info.hint = Integer.parseInt(fields[5]);
                info.ordinal = Integer.parseInt(fields[6]);
                info.name = fields[7];
                if (result.put(info.thunkAddress, info) != null) {
                    throw new IllegalStateException("duplicate import thunk: " + hex(info.thunkAddress));
                }
            }
        }
        return result;
    }

    private static Set<Long> readWarnings(File file) throws Exception {
        Set<Long> result = new LinkedHashSet<>();
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) {
                line = line.trim();
                if (!line.isEmpty()) {
                    result.add(parseHex(line));
                }
            }
        }
        return result;
    }

    private static Map<Long, CrossString> readCrossStrings(File file) throws Exception {
        Map<Long, CrossString> result = new HashMap<>();
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line = reader.readLine();
            if (line == null || !line.startsWith("score\tstring\t")) {
                throw new IllegalArgumentException("unexpected common-strings TSV header: " + file);
            }
            while ((line = reader.readLine()) != null) {
                String[] fields = line.split("\\t", -1);
                if (fields.length != 4) {
                    throw new IllegalArgumentException("malformed common-strings TSV row: " + line);
                }
                double score = Double.parseDouble(fields[0]);
                for (String item : fields[3].split(",")) {
                    int colon = item.indexOf(':');
                    if (colon <= 0) {
                        continue;
                    }
                    long address = APF_IMAGE_BASE + parseHex(item.substring(0, colon));
                    CrossString value = new CrossString();
                    value.value = fields[1];
                    value.encoding = item.substring(colon + 1);
                    value.score = score;
                    CrossString old = result.get(address);
                    if (old == null || value.score > old.score) {
                        result.put(address, value);
                    }
                }
            }
        }
        return result;
    }

    private Map<Long, PdataInfo> readPdata() throws Exception {
        Memory memory = currentProgram.getMemory();
        MemoryBlock block = memory.getBlock(".pdata");
        if (block == null || block.getSize() % 8 != 0) {
            throw new IllegalStateException("canonical .pdata block is missing or malformed");
        }
        Map<Long, PdataInfo> result = new HashMap<>();
        Address cursor = block.getStart();
        int count = (int)(block.getSize() / 8);
        for (int i = 0; i < count; i++) {
            long start = Integer.toUnsignedLong(memory.getInt(cursor));
            long metadata = Integer.toUnsignedLong(memory.getInt(cursor.add(4)));
            PdataInfo info = new PdataInfo();
            info.index = i;
            info.metadata = metadata;
            if (result.put(start, info) != null) {
                throw new IllegalStateException("duplicate .pdata function start: " + hex(start));
            }
            cursor = cursor.add(8);
        }
        return result;
    }

    private static List<Function> sortedFunctions(FunctionIterator iterator) {
        List<Function> result = new ArrayList<>();
        while (iterator.hasNext()) {
            result.add(iterator.next());
        }
        result.sort(Comparator.comparing(Function::getEntryPoint));
        return result;
    }

    private static List<Long> relatedAddresses(Set<Function> functions) {
        List<Long> result = new ArrayList<>(functions.size());
        for (Function function : functions) {
            if (function != null && function.getEntryPoint() != null) {
                result.add(function.getEntryPoint().getUnsignedOffset());
            }
        }
        Collections.sort(result);
        return result;
    }

    private StringRefs directStringReferences(
            Function function, Map<Long, CrossString> crossStrings) throws Exception {
        StringRefs result = new StringRefs();
        ReferenceManager references = currentProgram.getReferenceManager();
        Listing listing = currentProgram.getListing();
        Set<Long> seen = new HashSet<>();
        AddressIterator sources = references.getReferenceSourceIterator(function.getBody(), true);
        while (sources.hasNext()) {
            Address from = sources.next();
            for (Reference reference : references.getReferencesFrom(from)) {
                Address to = reference.getToAddress();
                if (to == null || !to.isMemoryAddress()) {
                    continue;
                }
                long target = to.getUnsignedOffset();
                if (!seen.add(target)) {
                    continue;
                }
                CrossString cross = crossStrings.get(target);
                DirectString item = null;
                if (cross != null) {
                    item = new DirectString();
                    item.address = target;
                    item.value = cross.value;
                    item.source = "reports/cross_title/common_strings.tsv";
                    item.encoding = cross.encoding;
                    item.crossTitle = true;
                }
                else {
                    Data data = listing.getDefinedDataAt(to);
                    if (data == null) {
                        data = listing.getDataContaining(to);
                    }
                    if (data != null && data.hasStringValue()) {
                        Object value = data.getValue();
                        if (value instanceof String) {
                            item = new DirectString();
                            item.address = target;
                            item.value = (String)value;
                            item.source = "ghidra_defined_data";
                            item.encoding = data.getDataType().getName();
                            item.crossTitle = false;
                        }
                    }
                }
                if (item != null) {
                    result.total++;
                    if (result.kept.size() < MAX_DIRECT_STRINGS) {
                        result.kept.add(item);
                    }
                }
            }
        }
        result.kept.sort(Comparator.comparingLong(item -> item.address));
        return result;
    }

    private static Classification classify(
            Function function, ImportInfo imported, boolean isEntry, SourceType source) {
        Classification result = new Classification();
        String name = function.getName();
        if (imported != null) {
            result.value = "import";
            result.evidence = "exact XEX import thunk: " + imported.library + "!" +
                imported.name + " ordinal " + imported.ordinal + " at " + hex(imported.thunkAddress);
        }
        else if (isEntry) {
            result.value = "game";
            result.evidence = "verified XEX optional-header entry point";
        }
        else if (source != SourceType.DEFAULT && XDK_NAME.matcher(name).matches()) {
            result.value = "XDK";
            result.evidence = "non-default recovered symbol name matches a documented XDK/API family: " + name;
        }
        else if (function.isThunk()) {
            Function target = function.getThunkedFunction(true);
            result.value = "helper";
            result.evidence = "Ghidra marks Function.isThunk()" +
                (target == null ? "" : " to " + hex(target.getEntryPoint().getUnsignedOffset()));
        }
        else if (source != SourceType.DEFAULT && HELPER_NAME.matcher(name).matches()) {
            result.value = "helper";
            result.evidence = "non-default recovered symbol name matches a compiler/C-runtime helper family: " + name;
        }
        else if (source != SourceType.DEFAULT && !DEFAULT_NAME.matcher(name).matches()) {
            result.value = "game";
            result.evidence = "non-default internal symbol supplied by loader/analysis: " + name;
        }
        else {
            result.value = "unresolved";
            result.evidence = "no recovered ownership signature; could be Visual Concepts game code, statically linked XDK/runtime, or stripped middleware";
        }
        return result;
    }

    private static String addressArray(List<Long> addresses) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < addresses.size(); i++) {
            if (i != 0) {
                out.append(',');
            }
            out.append(json(hex(addresses.get(i))));
        }
        return out.append(']').toString();
    }

    private static String rangesJson(AddressSetView body) {
        StringBuilder out = new StringBuilder("[");
        AddressRangeIterator ranges = body.getAddressRanges(true);
        boolean first = true;
        while (ranges.hasNext()) {
            AddressRange range = ranges.next();
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append("{\"start\":").append(json(hex(range.getMinAddress().getUnsignedOffset())))
                .append(",\"end_inclusive\":").append(json(hex(range.getMaxAddress().getUnsignedOffset())))
                .append(",\"size\":").append(range.getLength()).append('}');
        }
        return out.append(']').toString();
    }

    private static String stringsJson(StringRefs refs) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < refs.kept.size(); i++) {
            DirectString item = refs.kept.get(i);
            if (i != 0) {
                out.append(',');
            }
            out.append("{\"address\":").append(json(hex(item.address)))
                .append(",\"value\":").append(json(item.value))
                .append(",\"source\":").append(json(item.source))
                .append(",\"encoding\":").append(json(item.encoding))
                .append(",\"cross_title_exact\":").append(item.crossTitle).append('}');
        }
        return out.append(']').toString();
    }

    private static String importJson(ImportInfo info) {
        if (info == null) {
            return "null";
        }
        return "{\"library\":" + json(info.library) +
            ",\"library_version\":" + json(info.version) +
            ",\"reference_address\":" + json(hex(info.referenceAddress)) +
            ",\"thunk_address\":" + json(hex(info.thunkAddress)) +
            ",\"raw_word\":" + json(hex(info.rawWord)) +
            ",\"hint\":" + info.hint +
            ",\"ordinal\":" + info.ordinal +
            ",\"name\":" + json(info.name) + "}";
    }

    private static String makePortme(
            long address, String status, String diagnostic, List<Long> knownWarnings,
            int pseudoCWarningCount, int hardPseudoCWarningCount, int timeout) {
        boolean hasKnownWarning = knownWarnings != null && !knownWarnings.isEmpty();
        if (status.startsWith("success") && !hasKnownWarning && hardPseudoCWarningCount == 0 &&
                (diagnostic == null || diagnostic.isBlank())) {
            return null;
        }
        if ("timeout".equals(status)) {
            return "// PORTME: could not decompile function at " + hex(address) +
                "; Ghidra timed out after " + timeout + " seconds. Manually recover PPC/A2 control flow.";
        }
        if (!status.startsWith("success")) {
            return "// PORTME: could not decompile function at " + hex(address) +
                "; Ghidra status=" + status + ": " + sanitizeMessage(diagnostic) +
                ". Manually recover the function from the PPC listing and inline data.";
        }
        if (hasKnownWarning) {
            return "// PORTME: function at " + hex(address) +
                " contains or owns recorded APF Ghidra warning address(es) " +
                humanAddressList(knownWarnings) + ". Review unsupported A2/VMX " +
                "instruction or computed-target recovery before treating this pseudo-C as authoritative" +
                (hardPseudoCWarningCount == 0 ? "" : "; emitted pseudo-C also contains " +
                    hardPseudoCWarningCount + " hard control-flow warning(s)") +
                ((diagnostic == null || diagnostic.isBlank()) ? "." : ": " + sanitizeMessage(diagnostic));
        }
        if (hardPseudoCWarningCount != 0) {
            return "// PORTME: Ghidra emitted pseudo-C for function at " + hex(address) +
                " with " + hardPseudoCWarningCount + " hard bad-instruction/jumptable warning(s) " +
                "out of " + pseudoCWarningCount + " total pseudo-C warning comment(s). Recover the " +
                "truncated PPC/A2 control flow manually before porting.";
        }
        return "// PORTME: Ghidra produced pseudo-C for function at " + hex(address) +
            " with diagnostic: " + sanitizeMessage(diagnostic) + ". Review before porting.";
    }

    private void validateProgram(
            List<Function> functions, Map<Long, PdataInfo> pdata,
            Map<Long, ImportInfo> imports, Set<Long> warnings) {
        if (!EXPECTED_PROGRAM_NAME.equals(currentProgram.getName())) {
            throw new IllegalStateException("wrong Ghidra program: " + currentProgram.getName() +
                "; process /default.xex, never /apf2k8_default.pe");
        }
        if (!EXPECTED_FORMAT.equals(currentProgram.getExecutableFormat())) {
            throw new IllegalStateException("wrong executable format: " + currentProgram.getExecutableFormat());
        }
        if (!EXPECTED_MD5.equalsIgnoreCase(currentProgram.getExecutableMD5())) {
            throw new IllegalStateException("wrong executable MD5: " + currentProgram.getExecutableMD5());
        }
        if (!EXPECTED_LANGUAGE.equals(currentProgram.getLanguageID().toString())) {
            throw new IllegalStateException("wrong language: " + currentProgram.getLanguageID());
        }
        if (functions.size() != EXPECTED_FUNCTIONS) {
            throw new IllegalStateException("expected " + EXPECTED_FUNCTIONS +
                " functions, found " + functions.size());
        }
        if (pdata.size() != EXPECTED_PDATA) {
            throw new IllegalStateException("expected " + EXPECTED_PDATA +
                " .pdata starts, found " + pdata.size());
        }
        if (imports.size() != EXPECTED_IMPORT_THUNKS) {
            throw new IllegalStateException("expected " + EXPECTED_IMPORT_THUNKS +
                " import thunks, found " + imports.size());
        }
        if (warnings.size() != EXPECTED_WARNINGS) {
            throw new IllegalStateException("expected " + EXPECTED_WARNINGS +
                " warning addresses, found " + warnings.size());
        }
        Set<Long> entries = new HashSet<>();
        for (Function function : functions) {
            entries.add(function.getEntryPoint().getUnsignedOffset());
        }
        if (!entries.contains(EXPECTED_ENTRY)) {
            throw new IllegalStateException("verified XEX entry function is missing");
        }
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 4 || args.length > 5) {
            throw new IllegalArgumentException(
                "usage: ApfExportFunctionRecovery.java OUTPUT_DIRECTORY IMPORTS_TSV " +
                "WARNINGS_FILE COMMON_STRINGS_TSV [TIMEOUT_SECONDS]");
        }
        File output = new File(args[0]).getCanonicalFile();
        File importsFile = new File(args[1]).getCanonicalFile();
        File warningsFile = new File(args[2]).getCanonicalFile();
        File crossStringsFile = new File(args[3]).getCanonicalFile();
        int timeout = args.length == 5 ? Integer.parseInt(args[4]) : 20;
        if (timeout < 1 || timeout > 300) {
            throw new IllegalArgumentException("timeout must be from 1 through 300 seconds");
        }

        requireDirectory(output);
        File ledgerDirectory = new File(output, "ledger");
        File pseudoDirectory = new File(output, "pseudo_c");
        requireDirectory(ledgerDirectory);
        requireDirectory(pseudoDirectory);

        FunctionManager manager = currentProgram.getFunctionManager();
        List<Function> functions = sortedFunctions(manager.getFunctions(true));
        Map<Long, PdataInfo> pdata = readPdata();
        Map<Long, ImportInfo> imports = readImports(importsFile);
        Set<Long> warnings = readWarnings(warningsFile);
        Map<Long, CrossString> crossStrings = readCrossStrings(crossStringsFile);
        validateProgram(functions, pdata, imports, warnings);

        Set<Long> functionEntries = new HashSet<>();
        for (Function function : functions) {
            functionEntries.add(function.getEntryPoint().getUnsignedOffset());
        }
        List<Long> pdataStartsWithoutFunctions = new ArrayList<>();
        int functionsWithPdata = 0;
        for (Map.Entry<Long, PdataInfo> entry : pdata.entrySet()) {
            if (functionEntries.contains(entry.getKey())) {
                functionsWithPdata++;
            }
            else {
                pdataStartsWithoutFunctions.add(entry.getKey());
            }
        }
        Collections.sort(pdataStartsWithoutFunctions);
        File missingPdataFile = new File(output, "pdata_starts_without_functions.tsv");
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(missingPdataFile))) {
            writer.write("address\tpdata_index\tpdata_metadata\tportme\n");
            for (long address : pdataStartsWithoutFunctions) {
                PdataInfo info = pdata.get(address);
                String text = "// PORTME: .pdata runtime-function record at " + hex(address) +
                    " has no exact function in the final Ghidra analysis; recreate or split the " +
                    "function manually before decompiling it.";
                writer.write(hex(address) + "\t" + info.index + "\t" + hex(info.metadata) +
                    "\t" + text + "\n");
            }
        }
        List<Long> importThunksWithoutFunctions = new ArrayList<>();
        int functionsThatAreImportThunks = 0;
        for (long address : imports.keySet()) {
            if (functionEntries.contains(address)) {
                functionsThatAreImportThunks++;
            }
            else {
                importThunksWithoutFunctions.add(address);
            }
        }
        Collections.sort(importThunksWithoutFunctions);
        File missingImportsFile = new File(output, "import_thunks_without_functions.tsv");
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(missingImportsFile))) {
            writer.write("thunk_address\tlibrary\tordinal\tname\treference_address\tportme\n");
            for (long address : importThunksWithoutFunctions) {
                ImportInfo info = imports.get(address);
                String text = "// PORTME: XEX import thunk " + info.library + "!" + info.name +
                    " at " + hex(address) + " has no exact function in the final Ghidra analysis; " +
                    "restore the thunk boundary or map callers directly to the Linux API shim.";
                writer.write(hex(address) + "\t" + info.library + "\t" + info.ordinal + "\t" +
                    info.name + "\t" + hex(info.referenceAddress) + "\t" + text + "\n");
            }
        }

        Map<Long, List<Long>> warningsByFunction = new HashMap<>();
        Map<Long, Long> warningOwner = new TreeMap<>();
        List<Long> warningsWithoutFunction = new ArrayList<>();
        for (long warning : warnings) {
            Address warningAddress = currentProgram.getAddressFactory().getDefaultAddressSpace()
                .getAddress(warning);
            Function owner = manager.getFunctionAt(warningAddress);
            if (owner == null) {
                owner = manager.getFunctionContaining(warningAddress);
            }
            if (owner == null) {
                warningsWithoutFunction.add(warning);
            }
            else {
                long ownerAddress = owner.getEntryPoint().getUnsignedOffset();
                warningOwner.put(warning, ownerAddress);
                warningsByFunction.computeIfAbsent(ownerAddress, unused -> new ArrayList<>()).add(warning);
            }
        }
        for (List<Long> functionWarnings : warningsByFunction.values()) {
            Collections.sort(functionWarnings);
        }
        Collections.sort(warningsWithoutFunction);
        File knownWarningsFile = new File(output, "known_warnings.tsv");
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(knownWarningsFile))) {
            writer.write("warning_address\texact_function_entry\towner_function_address\tportme\n");
            for (long warning : warnings) {
                Long owner = warningOwner.get(warning);
                boolean exact = owner != null && owner.longValue() == warning;
                String text = "// PORTME: recorded APF Ghidra analysis/decompiler warning at " +
                    hex(warning) + "; manually review unsupported A2/VMX instruction decoding, " +
                    "computed targets, and inline data.";
                writer.write(hex(warning) + "\t" + exact + "\t" +
                    (owner == null ? "" : hex(owner)) + "\t" + text + "\n");
            }
        }

        println("APF_EXPORT_BEGIN functions=" + functions.size() + " pdata=" + pdata.size() +
            " functions_with_pdata=" + functionsWithPdata +
            " pdata_without_functions=" + pdataStartsWithoutFunctions.size() +
            " imports=" + imports.size() + " functions_that_are_imports=" +
            functionsThatAreImportThunks + " imports_without_functions=" +
            importThunksWithoutFunctions.size() + " warnings=" + warnings.size() +
            " warnings_assigned=" + warningOwner.size() + " warnings_unassigned=" +
            warningsWithoutFunction.size() +
            " cross_string_addresses=" + crossStrings.size() + " timeout=" + timeout);

        File portmeFile = new File(output, "portme.tsv");
        BufferedWriter portmeWriter = new BufferedWriter(new FileWriter(portmeFile), 256 * 1024);
        portmeWriter.write("address\tdecompile_status\tknown_warning\ttext\n");
        int portmeCount = 0;
        for (long address : pdataStartsWithoutFunctions) {
            String text = "// PORTME: .pdata runtime-function record at " + hex(address) +
                " has no exact function in the final Ghidra analysis; recreate or split the " +
                "function manually before decompiling it.";
            portmeWriter.write(hex(address) + "\tdisplaced_pdata\tfalse\t" + text + "\n");
            portmeCount++;
        }
        for (long address : importThunksWithoutFunctions) {
            ImportInfo info = imports.get(address);
            String text = "// PORTME: XEX import thunk " + info.library + "!" + info.name +
                " at " + hex(address) + " has no exact function in the final Ghidra analysis; " +
                "restore the thunk boundary or map callers directly to the Linux API shim.";
            portmeWriter.write(hex(address) + "\tdisplaced_import_thunk\tfalse\t" + text + "\n");
            portmeCount++;
        }
        for (long warning : warnings) {
            String text = "// PORTME: recorded APF Ghidra analysis/decompiler warning at " +
                hex(warning) + "; manually review unsupported A2/VMX instruction decoding, " +
                "computed targets, and inline data.";
            portmeWriter.write(hex(warning) + "\tknown_analysis_warning\ttrue\t" + text + "\n");
            portmeCount++;
        }

        DecompInterface decompiler = new DecompInterface();
        DecompileOptions options = new DecompileOptions();
        options.grabFromProgram(currentProgram);
        decompiler.setOptions(options);
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("Ghidra decompiler could not open canonical /default.xex");
        }

        TextShardWriter ledger = new TextShardWriter();
        TextShardWriter pseudo = new TextShardWriter();
        Map<String, Integer> statusCounts = new TreeMap<>();
        Map<String, Integer> classificationCounts = new TreeMap<>();
        List<String> ledgerFiles = new ArrayList<>();
        List<String> pseudoFiles = new ArrayList<>();
        Set<Long> exported = new HashSet<>();
        Set<Long> warningExported = new HashSet<>();
        int functionPortmeCount = 0;
        int directStringFunctions = 0;
        int crossStringFunctions = 0;
        int functionsWithPseudoCWarnings = 0;
        int functionsWithHardPseudoCWarnings = 0;
        int totalPseudoCWarnings = 0;
        int totalHardPseudoCWarnings = 0;
        long started = System.nanoTime();

        try {
            for (int index = 0; index < functions.size(); index++) {
                monitor.checkCancelled();
                Function function = functions.get(index);
                long address = function.getEntryPoint().getUnsignedOffset();
                if (!exported.add(address)) {
                    throw new IllegalStateException("duplicate function entry during export: " + hex(address));
                }

                if (index % LEDGER_SHARD_SIZE == 0) {
                    int end = Math.min(functions.size() - 1, index + LEDGER_SHARD_SIZE - 1);
                    File file = new File(ledgerDirectory,
                        String.format("apf2k8_functions_%05d_%05d.jsonl", index, end));
                    ledger.open(file, "");
                    ledgerFiles.add(output.toPath().relativize(file.toPath()).toString().replace(File.separatorChar, '/'));
                }
                if (index % PSEUDOC_SHARD_SIZE == 0) {
                    int end = Math.min(functions.size() - 1, index + PSEUDOC_SHARD_SIZE - 1);
                    File file = new File(pseudoDirectory,
                        String.format("apf2k8_pseudoc_%05d_%05d.c", index, end));
                    pseudo.open(file,
                        "/* Ghidra pseudo-C for canonical APF 2K8 /default.xex.\n" +
                        " * This is reverse-engineering output, not directly compilable source.\n" +
                        " * Every function has either pseudo-C or an explicit PORTME record.\n */\n\n");
                    pseudoFiles.add(output.toPath().relativize(file.toPath()).toString().replace(File.separatorChar, '/'));
                }

                ImportInfo imported = imports.get(address);
                PdataInfo pdataInfo = pdata.get(address);
                boolean isEntry = address == EXPECTED_ENTRY;
                List<Long> functionWarnings = warningsByFunction.get(address);
                if (functionWarnings == null) {
                    functionWarnings = Collections.emptyList();
                }
                boolean knownWarning = !functionWarnings.isEmpty();
                boolean exactWarningEntry = warnings.contains(address);
                warningExported.addAll(functionWarnings);
                SourceType nameSource = function.getSymbol().getSource();
                Classification classification = classify(function, imported, isEntry, nameSource);

                List<Long> callers = relatedAddresses(function.getCallingFunctions(monitor));
                List<Long> callees = relatedAddresses(function.getCalledFunctions(monitor));
                StringRefs stringRefs = directStringReferences(function, crossStrings);
                if (stringRefs.total != 0) {
                    directStringFunctions++;
                    for (DirectString item : stringRefs.kept) {
                        if (item.crossTitle) {
                            crossStringFunctions++;
                            break;
                        }
                    }
                }

                DecompileResults results = null;
                DecompiledFunction decompiled = null;
                String c = null;
                String diagnostic = null;
                String status;
                int pseudoCWarningCount = 0;
                int hardPseudoCWarningCount = 0;
                try {
                    results = decompiler.decompileFunction(function, timeout, monitor);
                    diagnostic = results.getErrorMessage();
                    if (results.decompileCompleted()) {
                        decompiled = results.getDecompiledFunction();
                    }
                    if (results.isTimedOut()) {
                        status = "timeout";
                    }
                    else if (results.isCancelled()) {
                        status = "cancelled";
                    }
                    else if (results.failedToStart()) {
                        status = "startup_failure";
                    }
                    else if (!results.decompileCompleted()) {
                        status = "error";
                    }
                    else if (decompiled == null || decompiled.getC() == null) {
                        status = "no_c_output";
                    }
                    else {
                        c = decompiled.getC();
                        pseudoCWarningCount = countOccurrences(c, "/* WARNING:");
                        hardPseudoCWarningCount = hardPseudoCWarningCount(c);
                        if (knownWarning) {
                            status = "success_with_known_warning";
                        }
                        else if (hardPseudoCWarningCount != 0) {
                            status = "success_with_hard_pseudoc_warning";
                        }
                        else if (diagnostic != null && !diagnostic.isBlank()) {
                            status = "success_with_diagnostic";
                        }
                        else {
                            status = "success";
                        }
                    }
                }
                catch (Exception exception) {
                    status = "exception";
                    diagnostic = exception.getClass().getName() + ": " + exception.getMessage();
                }

                if (pseudoCWarningCount != 0) {
                    functionsWithPseudoCWarnings++;
                    totalPseudoCWarnings += pseudoCWarningCount;
                }
                if (hardPseudoCWarningCount != 0) {
                    functionsWithHardPseudoCWarnings++;
                    totalHardPseudoCWarnings += hardPseudoCWarningCount;
                }

                String portme = makePortme(address, status, diagnostic, functionWarnings,
                    pseudoCWarningCount, hardPseudoCWarningCount, timeout);
                if (portme != null) {
                    portmeCount++;
                    functionPortmeCount++;
                    portmeWriter.write(hex(address) + "\t" + status + "\t" + knownWarning + "\t" +
                        portme.replace('\t', ' ').replace('\r', ' ').replace('\n', ' ') + "\n");
                }

                statusCounts.merge(status, 1, Integer::sum);
                classificationCounts.merge(classification.value, 1, Integer::sum);

                AddressSetView body = function.getBody();
                Address min = body.getMinAddress();
                Address max = body.getMaxAddress();
                String namespace = function.getParentNamespace() == null ? "" :
                    function.getParentNamespace().getName(true);
                Function thunkTarget = function.isThunk() ? function.getThunkedFunction(true) : null;
                String pseudoFile = pseudo.relativeTo(output);

                StringBuilder row = new StringBuilder(2048);
                row.append("{\"index\":").append(index)
                    .append(",\"address\":").append(json(hex(address)))
                    .append(",\"size\":").append(body.getNumAddresses())
                    .append(",\"range_start\":").append(json(min == null ? null : hex(min.getUnsignedOffset())))
                    .append(",\"range_end_inclusive\":").append(json(max == null ? null : hex(max.getUnsignedOffset())))
                    .append(",\"body_ranges\":").append(rangesJson(body))
                    .append(",\"name\":").append(json(function.getName()))
                    .append(",\"qualified_name\":").append(json(function.getName(true)))
                    .append(",\"namespace\":").append(json(namespace))
                    .append(",\"name_source\":").append(json(nameSource.toString()))
                    .append(",\"is_entry\":").append(isEntry)
                    .append(",\"is_external_entry_point\":")
                    .append(currentProgram.getSymbolTable().isExternalEntryPoint(function.getEntryPoint()))
                    .append(",\"is_pdata\":").append(pdataInfo != null)
                    .append(",\"pdata_index\":").append(pdataInfo == null ? "null" : Integer.toString(pdataInfo.index))
                    .append(",\"pdata_metadata\":").append(pdataInfo == null ? "null" : json(hex(pdataInfo.metadata)))
                    .append(",\"is_import\":").append(imported != null)
                    .append(",\"import\":").append(importJson(imported))
                    .append(",\"ghidra_is_thunk\":").append(function.isThunk())
                    .append(",\"thunk_target\":")
                    .append(thunkTarget == null ? "null" : json(hex(thunkTarget.getEntryPoint().getUnsignedOffset())))
                    .append(",\"caller_count\":").append(callers.size())
                    .append(",\"callers\":").append(addressArray(callers))
                    .append(",\"callee_count\":").append(callees.size())
                    .append(",\"callees\":").append(addressArray(callees))
                    .append(",\"direct_string_reference_count\":").append(stringRefs.total)
                    .append(",\"direct_string_references_truncated\":")
                    .append(stringRefs.total > stringRefs.kept.size())
                    .append(",\"direct_string_references\":").append(stringsJson(stringRefs))
                    .append(",\"classification\":").append(json(classification.value))
                    .append(",\"classification_evidence\":").append(json(classification.evidence))
                    .append(",\"decompile_status\":").append(json(status))
                    .append(",\"decompiler_diagnostic\":").append(json(diagnostic))
                    .append(",\"pseudo_c_warning_count\":").append(pseudoCWarningCount)
                    .append(",\"hard_pseudo_c_warning_count\":").append(hardPseudoCWarningCount)
                    .append(",\"known_warning_address\":").append(knownWarning)
                    .append(",\"known_warning_exact_entry\":").append(exactWarningEntry)
                    .append(",\"known_warning_addresses\":").append(addressArray(functionWarnings))
                    .append(",\"portme\":").append(json(portme))
                    .append(",\"pseudo_c_shard\":").append(json(pseudoFile))
                    .append("}\n");
                ledger.write(row.toString());

                pseudo.write("/* APF2K8_FUNCTION " + hex(address) + "\n" +
                    " * index: " + index + "\n" +
                    " * range: " + (min == null ? "none" : hex(min.getUnsignedOffset())) + "-" +
                        (max == null ? "none" : hex(max.getUnsignedOffset())) + "\n" +
                    " * size: " + body.getNumAddresses() + "\n" +
                    " * name: " + commentSafe(function.getName(true)) + "\n" +
                    " * namespace: " + commentSafe(namespace) + "\n" +
                    " * pdata: " + (pdataInfo != null) + "\n" +
                    " * import: " + (imported == null ? "false" :
                        imported.library + "!" + imported.name + " ordinal " + imported.ordinal) + "\n" +
                    " * classification: " + classification.value + " -- " +
                        commentSafe(classification.evidence) + "\n" +
                    " * decompile_status: " + status + "\n" +
                    " * pseudo_c_warning_count: " + pseudoCWarningCount + "\n" +
                    " * hard_pseudo_c_warning_count: " + hardPseudoCWarningCount + "\n" +
                    " * known_warning_addresses: " + humanAddressList(functionWarnings) + "\n" +
                    " */\n");
                if (portme != null) {
                    pseudo.write(portme + "\n");
                }
                if (c != null) {
                    pseudo.write(c);
                    if (!c.endsWith("\n")) {
                        pseudo.write("\n");
                    }
                }
                pseudo.write("\n/* APF2K8_END_FUNCTION " + hex(address) + " */\n\n");

                if ((index + 1) % 50 == 0 || index + 1 == functions.size()) {
                    ledger.flush();
                    pseudo.flush();
                    portmeWriter.flush();
                }
                if ((index + 1) % 100 == 0 || index + 1 == functions.size()) {
                    double elapsed = (System.nanoTime() - started) / 1_000_000_000.0;
                    println(String.format(Locale.ROOT,
                        "APF_EXPORT_PROGRESS %d/%d %.1f%% elapsed=%.1fs rate=%.2f_functions_per_second",
                        index + 1, functions.size(), (index + 1) * 100.0 / functions.size(),
                        elapsed, (index + 1) / Math.max(0.001, elapsed)));
                }
                if ((index + 1) % PSEUDOC_SHARD_SIZE == 0) {
                    decompiler.flushCache();
                }
            }
        }
        finally {
            try { ledger.close(); } catch (Exception ignored) { }
            try { pseudo.close(); } catch (Exception ignored) { }
            try { portmeWriter.flush(); portmeWriter.close(); } catch (Exception ignored) { }
            decompiler.dispose();
        }

        if (exported.size() != functions.size()) {
            throw new IllegalStateException("exported set is incomplete: " + exported.size());
        }
        double elapsed = (System.nanoTime() - started) / 1_000_000_000.0;
        File manifest = new File(output, "manifest.json");
        try (BufferedWriter writer = new BufferedWriter(new FileWriter(manifest))) {
            writer.write("{\n");
            writer.write("  \"schema_version\": 1,\n");
            writer.write("  \"generated_utc\": " + json(Instant.now().toString()) + ",\n");
            writer.write("  \"program_path\": \"/default.xex\",\n");
            writer.write("  \"program_name\": " + json(currentProgram.getName()) + ",\n");
            writer.write("  \"executable_format\": " + json(currentProgram.getExecutableFormat()) + ",\n");
            writer.write("  \"executable_md5\": " + json(currentProgram.getExecutableMD5()) + ",\n");
            writer.write("  \"language_id\": " + json(currentProgram.getLanguageID().toString()) + ",\n");
            writer.write("  \"decompile_timeout_seconds\": " + timeout + ",\n");
            writer.write("  \"function_count\": " + functions.size() + ",\n");
            writer.write("  \"exported_function_count\": " + exported.size() + ",\n");
            writer.write("  \"pdata_record_count\": " + pdata.size() + ",\n");
            writer.write("  \"functions_with_pdata_count\": " + functionsWithPdata + ",\n");
            writer.write("  \"pdata_starts_without_function_count\": " +
                pdataStartsWithoutFunctions.size() + ",\n");
            writer.write("  \"import_thunk_count\": " + imports.size() + ",\n");
            writer.write("  \"functions_that_are_import_thunks_count\": " +
                functionsThatAreImportThunks + ",\n");
            writer.write("  \"import_thunks_without_function_count\": " +
                importThunksWithoutFunctions.size() + ",\n");
            writer.write("  \"known_warning_count\": " + warnings.size() + ",\n");
            writer.write("  \"known_warning_assigned_to_function_count\": " +
                warningExported.size() + ",\n");
            writer.write("  \"known_warning_without_function_count\": " +
                warningsWithoutFunction.size() + ",\n");
            writer.write("  \"portme_count\": " + portmeCount + ",\n");
            writer.write("  \"function_portme_count\": " + functionPortmeCount + ",\n");
            writer.write("  \"non_function_portme_count\": " +
                (portmeCount - functionPortmeCount) + ",\n");
            writer.write("  \"functions_with_direct_strings\": " + directStringFunctions + ",\n");
            writer.write("  \"functions_with_cross_title_exact_strings\": " + crossStringFunctions + ",\n");
            writer.write("  \"functions_with_pseudo_c_warnings\": " +
                functionsWithPseudoCWarnings + ",\n");
            writer.write("  \"functions_with_hard_pseudo_c_warnings\": " +
                functionsWithHardPseudoCWarnings + ",\n");
            writer.write("  \"total_pseudo_c_warning_comments\": " + totalPseudoCWarnings + ",\n");
            writer.write("  \"total_hard_pseudo_c_warning_comments\": " +
                totalHardPseudoCWarnings + ",\n");
            writer.write("  \"max_direct_strings_per_function\": " + MAX_DIRECT_STRINGS + ",\n");
            writer.write(String.format(Locale.ROOT, "  \"elapsed_seconds\": %.3f,\n", elapsed));
            writer.write("  \"complete\": true,\n");
            writer.write("  \"decompile_status_counts\": " + mapJson(statusCounts) + ",\n");
            writer.write("  \"classification_counts\": " + mapJson(classificationCounts) + ",\n");
            writer.write("  \"ledger_schema\": {\n");
            writer.write("    \"format\": \"JSON Lines; one row per function, ordered by entry address\",\n");
            writer.write("    \"address_and_range\": \"address, size, range_start, range_end_inclusive, body_ranges\",\n");
            writer.write("    \"identity\": \"name, qualified_name, namespace, name_source\",\n");
            writer.write("    \"statuses\": \"entry, external-entry, pdata, import, thunk, classification, decompile, warning, PORTME\",\n");
            writer.write("    \"relationships\": \"sorted caller/callee entry-address arrays and bounded direct string references\"\n");
            writer.write("  },\n");
            writer.write("  \"ledger_shard_size\": " + LEDGER_SHARD_SIZE + ",\n");
            writer.write("  \"pseudo_c_shard_size\": " + PSEUDOC_SHARD_SIZE + ",\n");
            writer.write("  \"ledger_files\": " + stringArray(ledgerFiles) + ",\n");
            writer.write("  \"pseudo_c_files\": " + stringArray(pseudoFiles) + ",\n");
            writer.write("  \"portme_file\": \"portme.tsv\",\n");
            writer.write("  \"pdata_starts_without_functions_file\": " +
                "\"pdata_starts_without_functions.tsv\",\n");
            writer.write("  \"import_thunks_without_functions_file\": " +
                "\"import_thunks_without_functions.tsv\",\n");
            writer.write("  \"known_warnings_file\": \"known_warnings.tsv\"\n");
            writer.write("}\n");
        }
        println(String.format(Locale.ROOT,
            "APF_EXPORT_COMPLETE functions=%d portme=%d elapsed=%.1fs manifest=%s",
            exported.size(), portmeCount, elapsed, manifest));
    }

    private static String mapJson(Map<String, Integer> values) {
        StringBuilder out = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Integer> entry : values.entrySet()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(json(entry.getKey())).append(':').append(entry.getValue());
        }
        return out.append('}').toString();
    }

    private static String stringArray(List<String> values) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < values.size(); i++) {
            if (i != 0) {
                out.append(',');
            }
            out.append(json(values.get(i)));
        }
        return out.append(']').toString();
    }

    private static String humanAddressList(List<Long> values) {
        if (values == null || values.isEmpty()) {
            return "none";
        }
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < values.size(); i++) {
            if (i != 0) {
                out.append(", ");
            }
            out.append(hex(values.get(i)));
        }
        return out.append(']').toString();
    }
}

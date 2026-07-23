// Emit read-only evidence for the remaining APF SingleMoCap-to-SCNE binding gap.
// @category Xbox360.APF2K8

import java.io.BufferedWriter;
import java.io.BufferedReader;
import java.io.File;
import java.io.FileWriter;
import java.io.FileReader;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ApfAnimationBindingGapTrace extends GhidraScript {
    private static final String EXPECTED_MD5 = "217eea6084c3d03f0f1143802b1f5636";

    private Address address(long value) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(value);
    }

    private String hex(long value) {
        return String.format("0x%08X", value & 0xffffffffL);
    }

    private String addr(Address value) {
        return value == null ? "" : hex(value.getUnsignedOffset());
    }

    private String functionName(Function function) {
        if (function == null) return "none";
        return addr(function.getEntryPoint()) + ":" + function.getName();
    }

    private List<String> referencesTo(long target) {
        List<String> result = new ArrayList<>();
        ReferenceIterator iterator = currentProgram.getReferenceManager().getReferencesTo(address(target));
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                reference.getFromAddress());
            result.add(addr(reference.getFromAddress()) + "(" + functionName(owner) + "," +
                reference.getReferenceType() + ")");
        }
        Collections.sort(result);
        return result;
    }

    private void writeReferences(BufferedWriter output, long target, String role) throws Exception {
        List<String> references = referencesTo(target);
        output.write("TARGET " + hex(target) + " role=" + role + " refs=" +
            references.size() + "\n");
        for (String reference : references) {
            output.write("TARGET_REF " + hex(target) + " " + reference + "\n");
        }
    }

    private List<String> rawAlignedHits(long target) throws Exception {
        byte[] needle = new byte[] {
            (byte)(target >>> 24), (byte)(target >>> 16),
            (byte)(target >>> 8), (byte)target
        };
        List<String> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address cursor = block.getStart();
            while (cursor.compareTo(block.getEnd()) <= 0) {
                Address hit = memory.findBytes(cursor, block.getEnd(), needle, null, true, monitor);
                if (hit == null) break;
                if ((hit.getUnsignedOffset() & 3L) == 0) {
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(hit);
                    result.add(addr(hit) + "(" + block.getName() + "," +
                        functionName(owner) + ")");
                }
                cursor = hit.add(1);
            }
        }
        Collections.sort(result);
        return result;
    }

    private List<String> materializations(long target) throws Exception {
        List<String> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        long wanted = target & 0xffffffffL;
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized() || !block.isExecute()) continue;
            long first = (block.getStart().getUnsignedOffset() + 3L) & ~3L;
            long last = block.getEnd().getUnsignedOffset();
            for (long value = first; value + 3 <= last; value += 4) {
                long raw = Integer.toUnsignedLong(memory.getInt(address(value)));
                int opcode = (int)(raw >>> 26);
                int ra = (int)((raw >>> 16) & 31);
                if (opcode != 15 || ra != 0) continue;
                int baseRegister = (int)((raw >>> 21) & 31);
                long high = ((long)(short)(raw & 0xffffL) << 16) & 0xffffffffL;
                for (int distance = 1; distance <= 8; distance++) {
                    long site = value + distance * 4L;
                    if (site + 3 > last) break;
                    long next = Integer.toUnsignedLong(memory.getInt(address(site)));
                    int nextOpcode = (int)(next >>> 26);
                    long computed = -1;
                    String kind = "";
                    if (nextOpcode == 14 && ((next >>> 16) & 31) == baseRegister) {
                        computed = (high + (short)(next & 0xffffL)) & 0xffffffffL;
                        kind = "lis/addi";
                    }
                    else if (nextOpcode == 24 && ((next >>> 21) & 31) == baseRegister) {
                        computed = (high | (next & 0xffffL)) & 0xffffffffL;
                        kind = "lis/ori";
                    }
                    if (computed == wanted) {
                        Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                            address(site));
                        result.add(hex(value) + "->" + hex(site) + "(" + kind + "," +
                            functionName(owner) + ")");
                    }
                }
            }
        }
        Collections.sort(result);
        return result;
    }

    private void writeClipHashScan(BufferedWriter output, File tsv) throws Exception {
        output.write("CLIP_HASH_SCAN\n");
        List<String> names = new ArrayList<>();
        List<Long> hashes = new ArrayList<>();
        try (BufferedReader input = new BufferedReader(new FileReader(tsv))) {
            String header = input.readLine();
            if (header == null) throw new IllegalStateException("empty mocap TSV " + tsv);
            String[] columns = header.split("\\t", -1);
            int nameColumn = -1;
            int hashColumn = -1;
            for (int index = 0; index < columns.length; index++) {
                if (columns[index].equals("name")) nameColumn = index;
                if (columns[index].equals("name_crc32")) hashColumn = index;
            }
            if (nameColumn < 0 || hashColumn < 0) {
                throw new IllegalStateException("mocap TSV lacks name/name_crc32 columns");
            }
            String line;
            while ((line = input.readLine()) != null) {
                String[] values = line.split("\\t", -1);
                if (values.length <= Math.max(nameColumn, hashColumn)) {
                    throw new IllegalStateException("short mocap TSV row " + line);
                }
                names.add(values[nameColumn]);
                hashes.add(Long.parseUnsignedLong(values[hashColumn].substring(2), 16));
            }
        }
        Map<Long, Integer> indexByHash = new HashMap<>();
        List<List<String>> hits = new ArrayList<>();
        List<List<String>> constructions = new ArrayList<>();
        for (int index = 0; index < hashes.size(); index++) {
            if (indexByHash.put(hashes.get(index), index) != null) {
                throw new IllegalStateException("duplicate mocap hash " + hex(hashes.get(index)));
            }
            hits.add(new ArrayList<>());
            constructions.add(new ArrayList<>());
        }

        Memory memory = currentProgram.getMemory();
        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized()) continue;
            long first = (block.getStart().getUnsignedOffset() + 3L) & ~3L;
            long last = block.getEnd().getUnsignedOffset();
            for (long value = first; value + 3 <= last; value += 4) {
                long raw = Integer.toUnsignedLong(memory.getInt(address(value)));
                Integer index = indexByHash.get(raw);
                if (index == null) continue;
                Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                    address(value));
                hits.get(index).add(hex(value) + "(" + block.getName() + "," +
                    functionName(owner) + ")");
            }
        }

        for (MemoryBlock block : memory.getBlocks()) {
            if (!block.isInitialized() || !block.isExecute()) continue;
            long first = (block.getStart().getUnsignedOffset() + 3L) & ~3L;
            long last = block.getEnd().getUnsignedOffset();
            for (long value = first; value + 3 <= last; value += 4) {
                long raw = Integer.toUnsignedLong(memory.getInt(address(value)));
                int opcode = (int)(raw >>> 26);
                int ra = (int)((raw >>> 16) & 31);
                if (opcode != 15 || ra != 0) continue;
                int baseRegister = (int)((raw >>> 21) & 31);
                long high = ((long)(short)(raw & 0xffffL) << 16) & 0xffffffffL;
                for (int distance = 1; distance <= 8; distance++) {
                    long site = value + distance * 4L;
                    if (site + 3 > last) break;
                    long next = Integer.toUnsignedLong(memory.getInt(address(site)));
                    int nextOpcode = (int)(next >>> 26);
                    long computed = -1;
                    String kind = "";
                    if (nextOpcode == 14 && ((next >>> 16) & 31) == baseRegister) {
                        computed = (high + (short)(next & 0xffffL)) & 0xffffffffL;
                        kind = "lis/addi";
                    }
                    else if (nextOpcode == 24 && ((next >>> 21) & 31) == baseRegister) {
                        computed = (high | (next & 0xffffL)) & 0xffffffffL;
                        kind = "lis/ori";
                    }
                    Integer index = indexByHash.get(computed);
                    if (index == null) continue;
                    Function owner = currentProgram.getFunctionManager().getFunctionContaining(
                        address(site));
                    constructions.get(index).add(hex(value) + "->" + hex(site) + "(" +
                        kind + "," + functionName(owner) + ")");
                }
            }
        }

        for (int index = 0; index < hashes.size(); index++) {
            Collections.sort(hits.get(index));
            Collections.sort(constructions.get(index));
            output.write("CLIP_HASH " + names.get(index) + " " + hex(hashes.get(index)) +
                " raw_hits=" + hits.get(index).size() + " materializations=" +
                constructions.get(index).size() + "\n");
            for (String hit : hits.get(index)) {
                output.write("CLIP_HASH_RAW " + names.get(index) + " " +
                    hex(hashes.get(index)) + " " + hit + "\n");
            }
            for (String construction : constructions.get(index)) {
                output.write("CLIP_HASH_MATERIALIZATION " + names.get(index) + " " +
                    hex(hashes.get(index)) + " " + construction + "\n");
            }
        }
        output.write("CLIP_HASH_COUNT " + names.size() + "\n\n");
    }

    private void writeRawSpan(
            BufferedWriter output, String name, long first, long afterLast) throws Exception {
        output.write("SPAN " + name + " " + hex(first) + " " + hex(afterLast) + "\n");
        Memory memory = currentProgram.getMemory();
        for (long value = first; value < afterLast; value += 4) {
            Address cursor = address(value);
            long raw = Integer.toUnsignedLong(memory.getInt(cursor));
            Instruction instruction = currentProgram.getListing().getInstructionAt(cursor);
            if (instruction == null) {
                disassemble(cursor);
                instruction = currentProgram.getListing().getInstructionAt(cursor);
            }
            output.write("RAW32 " + hex(value) + " " + hex(raw) + "\n");
            output.write("GHIDRA " + hex(value) + " " +
                (instruction == null ? "<no instruction>" : instruction.toString()) + "\n");
        }
        output.write("END_SPAN " + name + "\n");
    }

    private void decompileOne(
            BufferedWriter output, DecompInterface decompiler, long entry) throws Exception {
        Function function = currentProgram.getFunctionManager().getFunctionAt(address(entry));
        output.write("/* " + hex(entry) + ":" +
            (function == null ? "missing" : function.getName()) + " refs=" +
            String.join(";", referencesTo(entry)) + " */\n");
        if (function == null) {
            output.write("// PORTME at " + hex(entry) +
                ": no exact function exists in the canonical analysis.\n\n");
            return;
        }
        DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
        if (result != null && result.decompileCompleted()) {
            output.write(result.getDecompiledFunction().getC());
        }
        else {
            output.write("// PORTME at " + hex(entry) +
                ": Ghidra decompilation failed; retain the RAW32 span.\n");
        }
        output.write("\n\n");
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "usage: ApfAnimationBindingGapTrace.java OUTPUT_DIRECTORY APF_MOCAP_TSV");
        }
        String executableMd5 = currentProgram.getExecutableMD5();
        if (!EXPECTED_MD5.equalsIgnoreCase(executableMd5)) {
            throw new IllegalStateException("unexpected APF executable MD5 " + executableMd5);
        }
        File outputDirectory = new File(args[0]);
        if (!outputDirectory.isDirectory() && !outputDirectory.mkdirs()) {
            throw new IllegalStateException("cannot create " + outputDirectory);
        }
        File mocapTsv = new File(args[1]);
        if (!mocapTsv.isFile()) {
            throw new IllegalStateException("missing mocap TSV " + mocapTsv);
        }

        File traceFile = new File(outputDirectory, "animation_binding_gap_trace.txt");
        try (BufferedWriter output = new BufferedWriter(new FileWriter(traceFile))) {
            output.write("APF 2K8 SingleMoCap-to-SCNE binding gap trace\n");
            output.write("Program MD5: " + executableMd5 + "\n");
            output.write("Program name: " + currentProgram.getName() + "\n");
            output.write("Program language: " + currentProgram.getLanguageID() + "\n\n");

            writeClipHashScan(output, mocapTsv);

            Memory memory = currentProgram.getMemory();
            boolean map3Equal = true;
            for (int index = 0; index < 23 * 3; ++index) {
                map3Equal &= memory.getByte(address(0x820fc510L + index)) ==
                    memory.getByte(address(0x821006f0L + index));
            }
            boolean map2Equal = true;
            output.write("STATIC_TABLE_JOIN\n");
            for (int row = 0; row < 21; ++row) {
                int mainRotation = memory.getByte(address(0x820fc55cL + row * 2L));
                int mainTranslation = memory.getByte(address(0x820fc55dL + row * 2L));
                int secondaryRotation = memory.getByte(address(0x82100738L + row * 2L));
                int secondaryTranslation = memory.getByte(address(0x82100739L + row * 2L));
                map2Equal &= mainRotation == secondaryRotation &&
                    mainTranslation == secondaryTranslation;
                output.write("MAP2_ROW " + row + " " + mainRotation + " " +
                    mainTranslation + " " + secondaryRotation + " " +
                    secondaryTranslation + "\n");
            }
            output.write("MAIN_SECONDARY_MAP3_FIRST23_EQUAL " + map3Equal + "\n");
            output.write("MAIN_SECONDARY_MAP2_FIRST21_EQUAL " + map2Equal + "\n\n");

            output.write("REFERENCES\n");
            writeReferences(output, 0x8522e170L, "runtime_hierarchy_object_pointer");
            writeReferences(output, 0x84aa4288L, "hierarchy_wrapper");
            writeReferences(output, 0x84b0fa88L, "vmx_hierarchy_apply_entry");
            writeReferences(output, 0x84b0fbf8L, "vmx_hierarchy_apply_thunk");
            writeReferences(output, 0x820b5390L, "identity_external_root_matrix");
            writeReferences(output, 0x84aa4348L, "helmet_lo_lookup_accessor");
            writeReferences(output, 0x850dec60L, "runtime_owner_or_callback_table");
            writeReferences(output, 0x84b16398L, "typed_resource_lookup");
            writeReferences(output, 0x84b194a0L, "resource_to_runtime_object");
            writeReferences(output, 0x84b0fc08L, "hierarchy_record_pointer_accessor");
            writeReferences(output, 0x84a12158L, "frontend_slot_clip_assignment");
            writeReferences(output, 0x84a121d0L, "frontend_exact_clip_selector_pdata_entry");
            writeReferences(output, 0x84a619e8L, "frontend_fallback_clip_assignment");
            writeReferences(output, 0x84a62278L, "frontend_character_animation_controller");
            writeReferences(output, 0x84a11b58L, "frontend_slot_pose_sample_and_apply_pdata_entry");
            writeReferences(output, 0x84aa4430L, "frontend_scene_and_player_shadow_setup_pdata_entry");
            writeReferences(output, 0x851ffdd4L, "frontend_slot_zero_clip_pointer");
            writeReferences(output, 0x852008c4L, "frontend_slot_one_clip_pointer");

            output.write("\nRAW_EVIDENCE\n");
            writeRawSpan(output, "single_mocap_type_hash", 0x820dbd00L, 0x820dbd04L);
            writeRawSpan(output, "mode1_translation", 0x8463a52cL, 0x8463a59cL);
            writeRawSpan(output, "logical_pose_to_local_matrices", 0x846394d0L, 0x84639618L);
            writeRawSpan(output, "sample_expand_apply", 0x847c1438L, 0x847c14e0L);
            writeRawSpan(output, "hierarchy_wrapper", 0x84aa4288L, 0x84aa42a4L);
            // Ghidra truncates this VMX128 body at +0x0c.  The raw span through
            // the real blr is authoritative and is decoded by XenonRecomp in
            // the companion validator.
            writeRawSpan(output, "vmx_hierarchy_apply", 0x84b0fa88L, 0x84b0fbf4L);
            writeRawSpan(output, "hierarchy_object_accessor", 0x84aa4348L, 0x84aa4380L);
            writeRawSpan(output, "consumer_constructor", 0x847c14e0L, 0x847c158cL);
            // The .pdata start at 0x84AA4430 is displaced in the stock
            // analysis.  These two spans preserve the base-register setup and
            // the exact SCNE/player_shadow lookup, object conversion, and
            // global assignment at base +0x0c20 (0x8522E170).
            writeRawSpan(output, "player_shadow_init_prologue", 0x84aa4430L, 0x84aa4474L);
            writeRawSpan(output, "player_shadow_global_assignment", 0x84aa4728L, 0x84aa4774L);
            // Stock Ghidra terminates the 0x84A121D0 function after its shared
            // save stub.  The raw body proves the exact SingleMoCap selector,
            // including mc002f_lg, and the final call that assigns the returned
            // resource to a frontend animation slot.
            writeRawSpan(output, "selected_clip_selector", 0x84a121d0L, 0x84a123d0L);
            writeRawSpan(output, "frontend_slot_clip_assignment", 0x84a12158L, 0x84a121d0L);
            writeRawSpan(output, "frontend_fallback_clip_assignment", 0x84a619e8L, 0x84a61b18L);
            writeRawSpan(output, "frontend_character_animation_controller", 0x84a62278L, 0x84a62408L);
            writeRawSpan(output, "frontend_slot_animation_update", 0x84a12ef0L, 0x84a130e0L);
            writeRawSpan(output, "frontend_slot_pose_sample_and_apply", 0x84a11b58L, 0x84a11d98L);
            writeRawSpan(output, "static_identity_and_neighbor", 0x820b5390L, 0x820b54d0L);
        }

        File pseudoFile = new File(outputDirectory,
            "animation_binding_gap_focused_pseudo_c.c");
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (BufferedWriter output = new BufferedWriter(new FileWriter(pseudoFile))) {
            output.write("/* APF 2K8 SingleMoCap-to-SCNE binding-gap focused pseudo-C. */\n\n");
            decompileOne(output, decompiler, 0x847c1438L);
            decompileOne(output, decompiler, 0x84aa4288L);
            decompileOne(output, decompiler, 0x84b0fa88L);
            decompileOne(output, decompiler, 0x84aa4348L);
            decompileOne(output, decompiler, 0x847c14e0L);
            decompileOne(output, decompiler, 0x84aa4430L);
            decompileOne(output, decompiler, 0x84a12158L);
            decompileOne(output, decompiler, 0x84a121d0L);
            decompileOne(output, decompiler, 0x84a11b58L);
            decompileOne(output, decompiler, 0x84a619e8L);
            decompileOne(output, decompiler, 0x84a62278L);
            output.write("/* Instruction-bounded recovery for the displaced 0x84AA4430 initializer:\n");
            output.write("   base = 0x8522D550;\n");
            output.write("   resource = typed_lookup(0xE26C9B5D [SCNE], 0xEA7614F3 [player_shadow]);\n");
            output.write("   if (resource != 0) base[0x0C20/4] = resource_to_runtime_object(resource);\n");
            output.write("   Thus *(void **)0x8522E170 is the runtime player_shadow hierarchy object. */\n\n");
            output.write("/* Instruction-bounded frontend binding at displaced 0x84A121D0/0x84A11B58:\n");
            output.write("   controller 0x84A62394 calls selector(slot=1, selector=2, 0, 0);\n");
            output.write("   if ((slot_object->u32_10 >> 30) & 3) is 2 or 3, selector hash 0x5C6B1BF8 names mnu_stn_01_070130_01_lg;\n");
            output.write("   0x84A12368 performs the SingleMoCap lookup and 0x84A123C0 stores it at slot +0x54;\n");
            output.write("   0x84A11B8C reloads that clip, 0x84A11C10 samples it with main map3, 0x84A11C30 expands 21 rows with main map2, and 0x84A11D60 applies player_shadow. */\n\n");
            output.write("// PORTME at 0x84B0FA88..0x84B0FBF0: stock Ghidra truncates the VMX128 hierarchy loop; use the RAW32/XenonRecomp trace.\n");
            output.write("// PORTME at 0x84AA4430: recreate the displaced .pdata function before claiming complete structured pseudo-C; the focused RAW32 proves only the player_shadow assignment path.\n");
            output.write("// PORTME at 0x84A121D0..0x84A123CC: stock Ghidra truncates the selector at its shared-save stub; recover the switch structure from the authoritative RAW32 span before native translation.\n");
            output.write("// PORTME at 0x84A11B58..0x84A11D84: stock Ghidra has no function at this displaced .pdata start; recreate the selector-to-main-map-to-player_shadow sample/apply body from RAW32 before native translation.\n");
            output.write("// PORTME at 0x846394D0..0x84639614: map numbered quaternion lanes and matrix convention to standard glTF XYZW without inference.\n");
        }
        decompiler.dispose();
    }
}

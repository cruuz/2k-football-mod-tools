"""Dependency-light Tkinter shell for the UI-independent editor core."""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

from ..core.apf_digital_font import create_apf_digital_font_recipe
from ..core.apf_export import (
    APF_JERSEY_EXPORT_CAPABILITY_ID,
    export_apf_jersey,
)
from ..core.capabilities import Capability
from ..core.controller import IssueLevel, ModEditorController
from ..core.errors import ModEditorError
from ..core.gameplay_inspection import (
    inspect_draft_priority,
    inspect_gameplay_sliders,
    inspect_nfl_franchise_limit,
    inspect_nfl_save_inventory,
)
from ..core.menu_modes import inspect_main_menu
from ..core.nfl_audio import create_nfl_menu_back_audio_recipe
from ..core.presentation_inspection import inspect_apf_scorebug_presentation
from ..core.model import GameId, LogEntry
from ..core.recipes import (
    ScorebugRecipeEdit,
    create_apf_helmet_recipe,
    create_apf_jersey_recipe,
    create_apf_pants_recipe,
    create_apf_shoulder_recipe,
    create_nfl_scorebug_recipe,
)
from ..core.uniform_sharing import (
    inspect_apf_helmet_sharing,
    inspect_apf_jersey_sharing,
    inspect_apf_pants_sharing,
    inspect_apf_shoulder_sharing,
    inspect_nfl_uniform_sharing,
)


APF_PANTS_CAPABILITY_ID = "apf2k8.uniforms.pants_color_00_23"
APF_HELMET_CAPABILITY_ID = "apf2k8.uniforms.helmet_color_00_23"
APF_SHOULDER_CAPABILITY_ID = "apf2k8.uniforms.shoulder_color_00_23"
APF_DIGITAL_FONT_CAPABILITY_ID = "apf2k8.scorebug_presentation.digital_font"
NFL_MENU_BACK_AUDIO_CAPABILITY_ID = "nfl2k5.audio.menu_back_wav"

RECIPE_CREATOR_CAPABILITIES = frozenset(
    {
        "nfl2k5.scorebug_presentation.inventory",
        NFL_MENU_BACK_AUDIO_CAPABILITY_ID,
        APF_JERSEY_EXPORT_CAPABILITY_ID,
        APF_PANTS_CAPABILITY_ID,
        APF_HELMET_CAPABILITY_ID,
        APF_SHOULDER_CAPABILITY_ID,
        APF_DIGITAL_FONT_CAPABILITY_ID,
    }
)

MAPPED_DATA_INSPECTORS = frozenset(
    {
        "apf2k8.cpu_ai_draft.logic",
        "apf2k8.gameplay_tuning_sliders.roster_view",
        "apf2k8.menus.layouts",
        "apf2k8.mode_state_routing.state_graph",
        "apf2k8.scorebug_presentation.inventory",
        APF_DIGITAL_FONT_CAPABILITY_ID,
        "apf2k8.uniforms.jersey_00_23",
        APF_PANTS_CAPABILITY_ID,
        APF_HELMET_CAPABILITY_ID,
        APF_SHOULDER_CAPABILITY_ID,
        "apf2k8.uniforms.catalog",
        "nfl2k5.cpu_ai_draft.logic",
        "nfl2k5.gameplay_tuning_sliders.rating_view",
        "nfl2k5.menus.layouts",
        "nfl2k5.mode_state_routing.state_graph",
        "nfl2k5.schedules_franchise.database",
        "nfl2k5.saves.dashboard",
        "nfl2k5.uniforms.all_visual",
    }
)


class ModEditorApp:
    def __init__(self, root: tk.Tk, controller: ModEditorController | None = None):
        self.root = root
        self.root.title("VC Football Mod Project Editor — Research Preview")
        self.root.geometry("1180x820")
        self.root.minsize(900, 650)
        self.controller = controller or ModEditorController()
        self.controller.log_listener = self._on_log
        self._jobs: queue.Queue[tuple[str, Any, Callable[[Any], None] | None]] = queue.Queue()
        self._busy = False
        self._capability_by_row: dict[str, Capability] = {}
        self._make_menu()
        self._make_widgets()
        self._set_project_controls(False)
        self.root.after(100, self._poll_jobs)

    def _make_menu(self) -> None:
        menu = tk.Menu(self.root)
        project = tk.Menu(menu, tearoff=False)
        project.add_command(label="New Project…", command=self._new_project)
        project.add_command(label="Open Project…", command=self._open_project)
        project.add_separator()
        project.add_command(label="Save", command=self._save_project)
        project.add_command(label="Save As…", command=lambda: self._save_project(save_as=True))
        project.add_separator()
        project.add_command(label="Quit", command=self.root.destroy)
        menu.add_cascade(label="Project", menu=project)
        self.root.config(menu=menu)

    def _make_widgets(self) -> None:
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill="both", expand=True)

        self.project_label = ttk.Label(
            outer, text="No project open", font=("TkDefaultFont", 12, "bold")
        )
        self.project_label.pack(anchor="w", pady=(0, 6))

        source = ttk.LabelFrame(outer, text="1. User-owned source (read-only inspection)", padding=6)
        source.pack(fill="x")
        self.source_var = tk.StringVar()
        ttk.Entry(source, textvariable=self.source_var).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.source_file_button = ttk.Button(source, text="Select File…", command=self._choose_source_file)
        self.source_file_button.grid(row=0, column=1, padx=2)
        self.source_dir_button = ttk.Button(source, text="Select Extracted Folder…", command=self._choose_source_dir)
        self.source_dir_button.grid(row=0, column=2, padx=2)
        self.inspect_button = ttk.Button(source, text="Hash / Recognize", command=self._inspect_source)
        self.inspect_button.grid(row=0, column=3, padx=(2, 0))
        self.source_status = ttk.Label(source, text="No source inspected", foreground="#555")
        self.source_status.grid(row=1, column=0, columnspan=4, sticky="w", pady=(5, 0))
        source.columnconfigure(0, weight=1)

        capabilities_frame = ttk.LabelFrame(
            outer, text="2. Capability browser — research status controls available actions", padding=6
        )
        capabilities_frame.pack(fill="both", expand=True, pady=7)
        toolbar = ttk.Frame(capabilities_frame)
        toolbar.pack(fill="x", pady=(0, 5))
        self.advanced_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar,
            text="Show Advanced / Experimental / PORTME",
            variable=self.advanced_var,
            command=self._refresh_capabilities,
        ).pack(side="left")
        ttk.Label(
            toolbar,
            text="PROVED = reviewed writer  •  READ ONLY = inspect/export  •  PORTME = unavailable",
            foreground="#555",
        ).pack(side="right")

        panes = ttk.Panedwindow(capabilities_frame, orient="horizontal")
        panes.pack(fill="both", expand=True)
        browser = ttk.Frame(panes)
        detail = ttk.Frame(panes)
        panes.add(browser, weight=3)
        panes.add(detail, weight=2)

        self.capability_tree = ttk.Treeview(
            browser,
            columns=("badge", "category", "title"),
            show="headings",
            selectmode="browse",
            height=12,
        )
        self.capability_tree.heading("badge", text="Badge")
        self.capability_tree.heading("category", text="Surface")
        self.capability_tree.heading("title", text="Capability")
        self.capability_tree.column("badge", width=90, stretch=False)
        self.capability_tree.column("category", width=170, stretch=False)
        self.capability_tree.column("title", width=330)
        self.capability_tree.tag_configure("PROVED", foreground="#176b2c")
        self.capability_tree.tag_configure("READ ONLY", foreground="#225ca8")
        self.capability_tree.tag_configure("PORTME", foreground="#9a3f20")
        scroll = ttk.Scrollbar(browser, command=self.capability_tree.yview)
        self.capability_tree.configure(yscrollcommand=scroll.set)
        self.capability_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.capability_tree.bind("<<TreeviewSelect>>", self._show_capability)

        self.detail_text = tk.Text(detail, wrap="word", height=15, state="disabled", padx=6, pady=4)
        detail_scroll = ttk.Scrollbar(detail, command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scroll.set)
        self.detail_text.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

        queue_frame = ttk.LabelFrame(
            outer, text="3. Selected capability actions and replacement queue", padding=6
        )
        queue_frame.pack(fill="x")
        queue_buttons = ttk.Frame(queue_frame)
        queue_buttons.pack(side="right", fill="y", padx=(6, 0))
        self.add_button = ttk.Button(queue_buttons, text="Queue Replacement…", command=self._queue_replacement)
        self.add_button.pack(fill="x")
        self.provider_import_button = ttk.Button(
            queue_buttons,
            text="Import Typed Recipe / Project…",
            command=self._import_provider_project,
        )
        self.provider_import_button.pack(fill="x", pady=(4, 0))
        self.provider_recipe_button = ttk.Button(
            queue_buttons,
            text="Create Typed Recipe…",
            command=self._create_provider_recipe,
        )
        self.provider_recipe_button.pack(fill="x", pady=(4, 0))
        self.apf_export_button = ttk.Button(
            queue_buttons,
            text="Export APF Jersey PNGs…",
            command=self._export_apf_jersey,
        )
        self.apf_export_button.pack(fill="x", pady=(4, 0))
        self.mapped_inspect_button = ttk.Button(
            queue_buttons,
            text="Inspect Mapped Data…",
            command=self._inspect_mapped_data,
        )
        self.mapped_inspect_button.pack(fill="x", pady=(4, 0))
        self.remove_button = ttk.Button(queue_buttons, text="Remove Selected", command=self._remove_replacement)
        self.remove_button.pack(fill="x", pady=4)
        self.apply_button = ttk.Button(queue_buttons, text="Apply Queue — PORTME", state="disabled")
        self.apply_button.pack(fill="x")
        self.queue_tree = ttk.Treeview(
            queue_frame,
            columns=("capability", "target", "file"),
            show="headings",
            height=4,
        )
        for column, title, width in (
            ("capability", "Capability", 260),
            ("target", "Named target", 180),
            ("file", "User-authored replacement", 420),
        ):
            self.queue_tree.heading(column, text=title)
            self.queue_tree.column(column, width=width)
        self.queue_tree.pack(fill="x", expand=True)

        output = ttk.LabelFrame(outer, text="4. Copy-only output, typed build, and validation", padding=6)
        output.pack(fill="x", pady=7)
        self.output_var = tk.StringVar()
        ttk.Entry(output, textvariable=self.output_var).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.output_button = ttk.Button(output, text="Choose New Output…", command=self._choose_output)
        self.output_button.grid(row=0, column=1, padx=2)
        self.validate_button = ttk.Button(output, text="Validate Editor Project", command=self._validate)
        self.validate_button.grid(row=0, column=2, padx=2)
        self.copy_button = ttk.Button(output, text="Create Unmodified Source Copy", command=self._create_copy)
        self.copy_button.grid(row=0, column=3, padx=(2, 0))
        self.provider_validate_button = ttk.Button(
            output, text="Typed Validate", command=self._validate_provider
        )
        self.provider_validate_button.grid(row=1, column=2, padx=2, pady=(5, 0), sticky="ew")
        self.provider_build_button = ttk.Button(
            output, text="Typed Build + Independent Verify", command=self._build_provider
        )
        self.provider_build_button.grid(row=1, column=3, padx=(2, 0), pady=(5, 0), sticky="ew")
        self.output_note = ttk.Label(
            output,
            text=(
                "Never overwrites or bundles retail data. Typed Build is allowlisted only for the "
                "reviewed NFL visual, scorebug, and fixed audio providers plus APF jersey, pants, helmet, shoulder, and shared digital-font providers."
            ),
            foreground="#555",
        )
        self.output_note.grid(row=2, column=0, columnspan=4, sticky="w", pady=(5, 0))
        output.columnconfigure(0, weight=1)

        log_frame = ttk.LabelFrame(outer, text="Validation / build log", padding=4)
        log_frame.pack(fill="both")
        self.log_text = tk.Text(log_frame, height=7, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(outer, textvariable=self.status_var, relief="sunken", anchor="w").pack(fill="x", pady=(6, 0))

        self._project_widgets = [
            self.source_file_button,
            self.source_dir_button,
            self.inspect_button,
            self.output_button,
            self.validate_button,
            self.copy_button,
            self.provider_import_button,
            self.provider_recipe_button,
            self.apf_export_button,
            self.mapped_inspect_button,
            self.provider_validate_button,
            self.provider_build_button,
            self.capability_tree,
            self.queue_tree,
        ]

    def _new_project(self) -> None:
        selection = NewProjectDialog(self.root).show()
        if selection is None:
            return
        name, game = selection
        try:
            self.controller.create_project(name, game)
            self._refresh_project()
        except ModEditorError as exc:
            self._show_error(exc)

    def _open_project(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open mod project",
            filetypes=(("VC mod project", "*.vcmod.json"), ("JSON", "*.json"), ("All files", "*")),
        )
        if not path:
            return
        try:
            self.controller.open_project(Path(path))
            self._refresh_project()
        except ModEditorError as exc:
            self._show_error(exc)

    def _save_project(self, save_as: bool = False) -> None:
        project = self.controller.project
        if project is None:
            self._show_error(ModEditorError("Create or open a project first"))
            return
        path: Path | None = None
        if save_as or not project.project_path:
            selected = filedialog.asksaveasfilename(
                parent=self.root,
                title="Save mod project",
                defaultextension=".vcmod.json",
                filetypes=(("VC mod project", "*.vcmod.json"), ("JSON", "*.json")),
            )
            if not selected:
                return
            path = Path(selected)
        try:
            if self.output_var.get().strip():
                self.controller.set_output_path(Path(self.output_var.get()))
            self.controller.save_project(path)
            self._refresh_project_label()
        except ModEditorError as exc:
            self._show_error(exc)

    def _choose_source_file(self) -> None:
        selected = filedialog.askopenfilename(parent=self.root, title="Select user-owned game source")
        if selected:
            self.source_var.set(selected)

    def _choose_source_dir(self) -> None:
        selected = filedialog.askdirectory(parent=self.root, title="Select extracted game folder")
        if selected:
            self.source_var.set(selected)

    def _inspect_source(self) -> None:
        if not self.source_var.get().strip():
            self._show_error(ModEditorError("Choose a source first"))
            return
        self._start_job(
            "Hashing source read-only…",
            lambda: self.controller.select_source(Path(self.source_var.get())),
            lambda record: self._after_source(record),
        )

    def _after_source(self, record) -> None:
        label = "RECOGNIZED" if record.recognized else "UNRECOGNIZED"
        self.source_status.config(
            text=f"{label} • {record.kind} • {record.size:,} bytes • SHA-256 {record.sha256}",
            foreground="#176b2c" if record.recognized else "#9a3f20",
        )

    def _choose_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="Choose a new output path (existing paths are refused)",
        )
        if selected:
            self.output_var.set(selected)
            try:
                self.controller.set_output_path(Path(selected))
            except ModEditorError as exc:
                self._show_error(exc)

    def _refresh_project(self) -> None:
        project = self.controller.project
        self._set_project_controls(project is not None)
        if project is None:
            return
        self.source_var.set(project.source.selected_path if project.source else "")
        self.output_var.set(project.output_path)
        if project.source:
            self._after_source(project.source)
        else:
            self.source_status.config(text="No source inspected", foreground="#555")
        self._refresh_project_label()
        self._refresh_capabilities()
        self._refresh_queue()
        self._refresh_log()

    def _refresh_project_label(self) -> None:
        project = self.controller.project
        if not project:
            self.project_label.config(text="No project open")
            return
        marker = " *" if project.dirty else ""
        self.project_label.config(text=f"{project.name}{marker} — {project.game.display_name}")

    def _refresh_capabilities(self) -> None:
        self.capability_tree.delete(*self.capability_tree.get_children())
        self._capability_by_row.clear()
        if self.controller.project is None:
            return
        show_advanced = self.advanced_var.get()
        for capability in self.controller.capabilities_for_project():
            exposed = capability.raw["gui"].get("expose") is True
            if not show_advanced and (capability.is_experimental or not exposed):
                continue
            row = self.capability_tree.insert(
                "",
                "end",
                values=(capability.badge, capability.category, capability.title),
                tags=(capability.badge,),
            )
            self._capability_by_row[row] = capability

    def _show_capability(self, _event=None) -> None:
        selected = self.capability_tree.selection()
        capability = self._capability_by_row.get(selected[0]) if selected else None
        provider_supported = bool(
            capability and self.controller.provider_supported(capability.capability_id)
        )
        self.add_button.config(
            state=(
                "normal"
                if capability and capability.can_queue_replacement and not provider_supported
                else "disabled"
            )
        )
        self.provider_import_button.config(
            state="normal" if provider_supported else "disabled"
        )
        self.provider_recipe_button.config(
            state=(
                "normal"
                if provider_supported
                and capability.capability_id in RECIPE_CREATOR_CAPABILITIES
                else "disabled"
            )
        )
        self.apf_export_button.config(
            state=(
                "normal"
                if capability
                and capability.capability_id == APF_JERSEY_EXPORT_CAPABILITY_ID
                else "disabled"
            )
        )
        self.mapped_inspect_button.config(
            state=(
                "normal"
                if capability and capability.capability_id in MAPPED_DATA_INSPECTORS
                else "disabled"
            )
        )
        if not capability:
            self._set_detail("")
            return
        raw = capability.raw
        source = raw["source_container"]
        runtime = raw["runtime"]
        backend = raw["backend"]
        gui = raw["gui"]
        game_meta = self.controller.registry.game_metadata.get(capability.game, {})
        identity = game_meta.get("retail_identity", {})
        lines = [
            f"{capability.badge} — {capability.classification.value}",
            "",
            capability.title,
            capability.summary,
            "",
            f"Platform: {game_meta.get('platform', 'See registry')}",
            f"Public input: {game_meta.get('public_input', 'User-owned source only')}",
            f"Executable signature: {identity.get('executable_sha256', 'not pinned')}",
            f"Content signature: {identity.get('content_sha256', 'not pinned')}",
            "",
            f"Container: {source.get('format')} / {source.get('retail_file')}",
            f"Resource: {source.get('resource')}",
            f"Capability hash pins: {', '.join(source.get('hash_pins', [])) or 'none'}",
            f"Backend: {backend.get('operation')} • {backend.get('module') or 'none'}",
            f"GUI mode: {gui.get('mode')} • {gui.get('reason')}",
            f"Runtime: {runtime.get('status')} • {runtime.get('scope')}",
            "",
            "Input constraints:",
            *[f"  • {item}" for item in raw.get("input_constraints", [])],
            "",
            f"Selectors: {raw.get('selectors', {}).get('notes', '')}",
            "",
            "PORTME / limits:",
            *[f"  • {item}" for item in raw.get("portme", [])],
            "",
            f"Distribution: {raw.get('public_distribution', {}).get('rule', '')}",
            f"Validator: {raw.get('validation_command') or 'none'}",
            (
                "Typed provider: "
                + (
                    self.controller.providers.provider_id(capability.capability_id)
                    if provider_supported
                    else "not allowlisted"
                )
            ),
        ]
        if not capability.can_queue_replacement:
            lines.extend(("", "No replacement action is exposed for this capability."))
        self._set_detail("\n".join(str(line) for line in lines))

    def _import_provider_project(self) -> None:
        selected = self.capability_tree.selection()
        capability = self._capability_by_row.get(selected[0]) if selected else None
        if not capability or not self.controller.provider_supported(capability.capability_id):
            self._show_error(ModEditorError("Select an allowlisted typed-provider capability"))
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title=f"Import canonical typed recipe/project for {capability.title}",
            filetypes=(("Typed JSON", "*.json"), ("All files", "*")),
        )
        if not path:
            return
        try:
            self.controller.import_provider_project(capability.capability_id, Path(path))
            self._refresh_queue()
            self._refresh_project_label()
        except ModEditorError as exc:
            self._show_error(exc)

    def _create_provider_recipe(self) -> None:
        selected = self.capability_tree.selection()
        capability = self._capability_by_row.get(selected[0]) if selected else None
        if (
            not capability
            or capability.capability_id not in RECIPE_CREATOR_CAPABILITIES
            or not self.controller.provider_supported(capability.capability_id)
        ):
            self._show_error(ModEditorError("Select a supported typed recipe capability"))
            return
        try:
            if capability.capability_id == APF_DIGITAL_FONT_CAPABILITY_ID:
                confirmed = messagebox.askyesno(
                    "Shared APF digital_font scope",
                    (
                        "digital_font is one shared global UI alpha texture, not a "
                        "field-scorebug-only asset. Which screens consume it and its "
                        "runtime visibility are not proved. The bounded DXT5A encoder "
                        "is proof-quality, not a production perceptual encoder.\n\n"
                        "Create an alpha-only recipe anyway?"
                    ),
                    parent=self.root,
                )
                if not confirmed:
                    return
                png = filedialog.askopenfilename(
                    parent=self.root,
                    title=(
                        "Choose exact 128x128 RGBA APF digital_font PNG "
                        "(RGB solid white; alpha stored)"
                    ),
                    filetypes=(("PNG image", "*.png"), ("All files", "*")),
                )
                if not png:
                    return
                output = filedialog.asksaveasfilename(
                    parent=self.root,
                    title="Create new shared APF digital_font recipe",
                    defaultextension=".json",
                    initialfile="apf2k8-digital-font.json",
                    filetypes=(("Typed JSON", "*.json"),),
                )
                if not output:
                    return
                recipe = create_apf_digital_font_recipe(
                    output=Path(output), png=Path(png)
                )
            elif capability.capability_id == NFL_MENU_BACK_AUDIO_CAPABILITY_ID:
                purpose = simpledialog.askstring(
                    "NFL menu-back audio recipe",
                    "Describe this fixed menu-back_01 audio mod:",
                    parent=self.root,
                    initialvalue="User-authored NFL 2K5 menu-back audio project.",
                )
                if not purpose:
                    return
                wav = filedialog.askopenfilename(
                    parent=self.root,
                    title=(
                        "Choose strict mono PCM16LE 16000 Hz, "
                        "5696-frame menu-back WAV"
                    ),
                    filetypes=(("WAV audio", "*.wav"), ("All files", "*")),
                )
                if not wav:
                    return
                output = filedialog.asksaveasfilename(
                    parent=self.root,
                    title="Create new fixed-target NFL menu-back audio recipe",
                    defaultextension=".json",
                    initialfile="nfl2k5-menu-back-audio.json",
                    filetypes=(("Typed JSON", "*.json"),),
                )
                if not output:
                    return
                recipe = create_nfl_menu_back_audio_recipe(
                    output=Path(output), purpose=purpose, wav=Path(wav)
                )
            elif capability.capability_id == APF_JERSEY_EXPORT_CAPABILITY_ID:
                asset_index = simpledialog.askinteger(
                    "APF jersey asset",
                    "Asset index (0 through 23):",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=23,
                )
                if asset_index is None:
                    return
                png = filedialog.askopenfilename(
                    parent=self.root,
                    title="Choose exact 1024x1024 RGBA jersey PNG",
                    filetypes=(("PNG image", "*.png"), ("All files", "*")),
                )
                if not png:
                    return
                output = filedialog.asksaveasfilename(
                    parent=self.root,
                    title="Create new APF jersey recipe",
                    defaultextension=".json",
                    initialfile=f"apf2k8-jersey-{asset_index:02d}.json",
                    filetypes=(("Typed JSON", "*.json"),),
                )
                if not output:
                    return
                recipe = create_apf_jersey_recipe(
                    output=Path(output), asset_index=asset_index, png=Path(png)
                )
            elif capability.capability_id == APF_PANTS_CAPABILITY_ID:
                asset_index = simpledialog.askinteger(
                    "APF pants asset",
                    "Asset index (0 through 23):",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=23,
                )
                if asset_index is None:
                    return
                png = filedialog.askopenfilename(
                    parent=self.root,
                    title="Choose exact opaque 512x512 RGBA pants PNG",
                    filetypes=(("PNG image", "*.png"), ("All files", "*")),
                )
                if not png:
                    return
                output = filedialog.asksaveasfilename(
                    parent=self.root,
                    title="Create new APF pants recipe",
                    defaultextension=".json",
                    initialfile=f"apf2k8-pants-{asset_index:02d}.json",
                    filetypes=(("Typed JSON", "*.json"),),
                )
                if not output:
                    return
                recipe = create_apf_pants_recipe(
                    output=Path(output), asset_index=asset_index, png=Path(png)
                )
            elif capability.capability_id == APF_HELMET_CAPABILITY_ID:
                asset_index = simpledialog.askinteger(
                    "APF helmet asset",
                    "Asset index (0 through 23):",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=23,
                )
                if asset_index is None:
                    return
                png = filedialog.askopenfilename(
                    parent=self.root,
                    title=(
                        "Choose exact 256x1024 RGBA helmet PNG "
                        "(R/G data, B=0, A=255)"
                    ),
                    filetypes=(("PNG image", "*.png"), ("All files", "*")),
                )
                if not png:
                    return
                output = filedialog.asksaveasfilename(
                    parent=self.root,
                    title="Create new APF helmet two-channel recipe",
                    defaultextension=".json",
                    initialfile=f"apf2k8-helmet-{asset_index:02d}.json",
                    filetypes=(("Typed JSON", "*.json"),),
                )
                if not output:
                    return
                recipe = create_apf_helmet_recipe(
                    output=Path(output), asset_index=asset_index, png=Path(png)
                )
            elif capability.capability_id == APF_SHOULDER_CAPABILITY_ID:
                asset_index = simpledialog.askinteger(
                    "APF shoulder-color asset",
                    "Asset index (0 through 23):",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=23,
                )
                if asset_index is None:
                    return
                png = filedialog.askopenfilename(
                    parent=self.root,
                    title="Choose exact 1024x1024 RGBA shoulder-color PNG",
                    filetypes=(("PNG image", "*.png"), ("All files", "*")),
                )
                if not png:
                    return
                output = filedialog.asksaveasfilename(
                    parent=self.root,
                    title="Create new APF shoulder-color recipe",
                    defaultextension=".json",
                    initialfile=f"apf2k8-shoulder-{asset_index:02d}.json",
                    filetypes=(("Typed JSON", "*.json"),),
                )
                if not output:
                    return
                recipe = create_apf_shoulder_recipe(
                    output=Path(output), asset_index=asset_index, png=Path(png)
                )
            else:
                selection = ScorebugRecipeDialog(self.root).show()
                if selection is None:
                    return
                purpose, edits = selection
                output = filedialog.asksaveasfilename(
                    parent=self.root,
                    title="Create new NFL 2K5 scorebug recipe",
                    defaultextension=".json",
                    initialfile="nfl2k5-scorebug.json",
                    filetypes=(("Typed JSON", "*.json"),),
                )
                if not output:
                    return
                recipe = create_nfl_scorebug_recipe(
                    output=Path(output), purpose=purpose, edits=edits
                )
            self.controller.import_provider_project(capability.capability_id, recipe)
            self._refresh_queue()
            self._refresh_project_label()
            messagebox.showinfo(
                "Typed recipe created",
                f"Created and imported:\n{recipe}",
                parent=self.root,
            )
        except (ModEditorError, OSError) as exc:
            self._show_error(exc)

    def _export_apf_jersey(self) -> None:
        selected = self.capability_tree.selection()
        capability = self._capability_by_row.get(selected[0]) if selected else None
        if (
            not capability
            or capability.capability_id != APF_JERSEY_EXPORT_CAPABILITY_ID
        ):
            self._show_error(ModEditorError("Select the APF jersey PNG writer capability"))
            return
        source = filedialog.askopenfilename(
            parent=self.root,
            title="Select user-owned pinned retail APF 0A (read only)",
        )
        if not source:
            return
        asset_index = simpledialog.askinteger(
            "APF jersey export",
            "Asset index (0 through 23):",
            parent=self.root,
            minvalue=0,
            maxvalue=23,
        )
        if asset_index is None:
            return
        output_dir = filedialog.asksaveasfilename(
            parent=self.root,
            title="Choose a new absent APF jersey export directory",
            initialfile=f"apf2k8-jersey-{asset_index:02d}-export",
        )
        if not output_dir:
            return
        self._start_job(
            f"Exporting APF jersey asset {asset_index} read-only…",
            lambda: export_apf_jersey(
                source_0a=Path(source),
                asset_index=asset_index,
                output_dir=Path(output_dir),
            ),
            lambda result: messagebox.showinfo(
                "APF jersey export complete",
                (
                    f"Created {result.file_count} files for asset {result.asset_index}.\n\n"
                    f"Provenance: {result.provenance}\n\n"
                    "The retail 0A was opened read-only and no archive bytes were written. "
                    "Selector provenance labels banks only as bank 0 and bank 1; "
                    "home/away orientation is not claimed."
                ),
                parent=self.root,
            ),
        )

    def _inspect_mapped_data(self) -> None:
        selected = self.capability_tree.selection()
        capability = self._capability_by_row.get(selected[0]) if selected else None
        if not capability or capability.capability_id not in MAPPED_DATA_INSPECTORS:
            self._show_error(ModEditorError("Select a capability with a named data inspector"))
            return
        capability_id = capability.capability_id
        try:
            if capability_id == "nfl2k5.gameplay_tuning_sliders.rating_view":
                result = inspect_gameplay_sliders("nfl2k5")
            elif capability_id == "apf2k8.gameplay_tuning_sliders.roster_view":
                result = inspect_gameplay_sliders("apf2k8")
            elif capability_id == "nfl2k5.cpu_ai_draft.logic":
                result = inspect_draft_priority("nfl2k5")
            elif capability_id == "apf2k8.cpu_ai_draft.logic":
                result = inspect_draft_priority("apf2k8")
            elif capability_id == "nfl2k5.schedules_franchise.database":
                result = inspect_nfl_franchise_limit("all")
            elif capability_id == "nfl2k5.saves.dashboard":
                result = inspect_nfl_save_inventory()
            elif capability_id in {
                "nfl2k5.menus.layouts",
                "nfl2k5.mode_state_routing.state_graph",
            }:
                result = inspect_main_menu("nfl2k5")
            elif capability_id in {
                "apf2k8.menus.layouts",
                "apf2k8.mode_state_routing.state_graph",
            }:
                result = inspect_main_menu("apf2k8")
            elif capability_id in {
                "apf2k8.scorebug_presentation.inventory",
                APF_DIGITAL_FONT_CAPABILITY_ID,
            }:
                result = inspect_apf_scorebug_presentation()
            elif capability_id == "nfl2k5.uniforms.all_visual":
                selector = simpledialog.askstring(
                    "NFL uniform sharing",
                    "Named uniform selector (for example 09A0):",
                    parent=self.root,
                )
                if not selector:
                    return
                result = inspect_nfl_uniform_sharing(selector)
            elif capability_id == "apf2k8.uniforms.jersey_00_23":
                asset_index = simpledialog.askinteger(
                    "APF jersey sharing",
                    "Jersey asset index (0 through 23):",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=23,
                )
                if asset_index is None:
                    return
                result = inspect_apf_jersey_sharing(asset_index)
            elif capability_id == APF_PANTS_CAPABILITY_ID:
                asset_index = simpledialog.askinteger(
                    "APF pants sharing",
                    "Pants asset index (0 through 23):",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=23,
                )
                if asset_index is None:
                    return
                result = inspect_apf_pants_sharing(asset_index)
            elif capability_id == APF_HELMET_CAPABILITY_ID:
                asset_index = simpledialog.askinteger(
                    "APF helmet sharing",
                    "Helmet asset index (0 through 23):",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=23,
                )
                if asset_index is None:
                    return
                result = inspect_apf_helmet_sharing(asset_index)
            elif capability_id == APF_SHOULDER_CAPABILITY_ID:
                asset_index = simpledialog.askinteger(
                    "APF shoulder sharing",
                    "Shoulder asset index (0 through 23):",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=23,
                )
                if asset_index is None:
                    return
                result = inspect_apf_shoulder_sharing(asset_index)
            elif capability_id == "apf2k8.uniforms.catalog":
                family = simpledialog.askstring(
                    "APF uniform sharing",
                    "Mapped family to inspect (pants, helmet, or shoulder):",
                    parent=self.root,
                )
                if family is None:
                    return
                family = family.strip().lower()
                if family not in {"pants", "helmet", "shoulder"}:
                    raise ModEditorError(
                        "APF uniform family must be pants, helmet, or shoulder"
                    )
                asset_index = simpledialog.askinteger(
                    f"APF {family} sharing",
                    f"{family.title()} asset index (0 through 23):",
                    parent=self.root,
                    minvalue=0,
                    maxvalue=23,
                )
                if asset_index is None:
                    return
                if family == "pants":
                    result = inspect_apf_pants_sharing(asset_index)
                elif family == "helmet":
                    result = inspect_apf_helmet_sharing(asset_index)
                else:
                    result = inspect_apf_shoulder_sharing(asset_index)
            else:  # fail closed if the allowlist and dispatcher ever diverge
                raise ModEditorError("No named inspector is bound to this capability")
        except (ModEditorError, OSError) as exc:
            self._show_error(exc)
            return
        self._show_inspection_result(capability.title, result)

    def _show_inspection_result(self, title: str, result: dict[str, object]) -> None:
        window = tk.Toplevel(self.root)
        window.title(f"Mapped data — {title}")
        window.geometry("860x680")
        frame = ttk.Frame(window, padding=8)
        frame.pack(fill="both", expand=True)
        text_widget = tk.Text(frame, wrap="none", padx=6, pady=4)
        vertical = ttk.Scrollbar(frame, orient="vertical", command=text_widget.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=text_widget.xview)
        text_widget.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )
        text_widget.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        ttk.Button(frame, text="Close", command=window.destroy).grid(
            row=2, column=0, columnspan=2, pady=(8, 0)
        )
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text_widget.insert("1.0", json.dumps(result, indent=2, sort_keys=True))
        text_widget.config(state="disabled")

    def _set_detail(self, text: str) -> None:
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.config(state="disabled")

    def _queue_replacement(self) -> None:
        selected = self.capability_tree.selection()
        capability = self._capability_by_row.get(selected[0]) if selected else None
        if not capability or not capability.can_queue_replacement:
            self._show_error(ModEditorError("Select a PROVED writer capability first"))
            return
        extensions = " ".join(f"*{item}" for item in capability.accepted_extensions)
        replacement = filedialog.askopenfilename(
            parent=self.root,
            title=f"Choose user-authored input for {capability.title}",
            filetypes=(("Accepted input", extensions), ("All files", "*")),
        )
        if not replacement:
            return
        selector_notes = capability.raw.get("selectors", {}).get("notes", "")
        target = simpledialog.askstring(
            "Named target",
            f"Enter a named asset target (never a raw offset):\n{selector_notes}",
            parent=self.root,
        )
        if not target:
            return
        try:
            self.controller.enqueue_replacement(capability.capability_id, Path(replacement), target)
            self._refresh_queue()
            self._refresh_project_label()
        except ModEditorError as exc:
            self._show_error(exc)

    def _remove_replacement(self) -> None:
        selected = self.queue_tree.selection()
        if not selected:
            return
        try:
            self.controller.remove_replacement(selected[0])
            self._refresh_queue()
        except ModEditorError as exc:
            self._show_error(exc)

    def _refresh_queue(self) -> None:
        self.queue_tree.delete(*self.queue_tree.get_children())
        project = self.controller.project
        if not project:
            return
        for item in project.replacements:
            self.queue_tree.insert(
                "",
                "end",
                iid=item.item_id,
                values=(item.capability_id, item.target_id, item.replacement_path),
            )
        self._refresh_provider_buttons()

    def _refresh_provider_buttons(self) -> None:
        enabled = False
        if self.controller.project is not None and not self._busy:
            try:
                enabled = self.controller.typed_provider_binding() is not None
            except ModEditorError:
                enabled = False
        state = "normal" if enabled else "disabled"
        self.provider_validate_button.config(state=state)
        self.provider_build_button.config(state=state)

    def _validate(self) -> None:
        try:
            if self.output_var.get().strip():
                self.controller.set_output_path(Path(self.output_var.get()))
            issues = self.controller.validate_project()
            summary = "\n".join(f"{item.level.value}: {item.message}" for item in issues)
            if any(item.level == IssueLevel.ERROR for item in issues):
                messagebox.showerror("Validation", summary, parent=self.root)
            else:
                messagebox.showinfo("Validation", summary, parent=self.root)
            self._refresh_log()
        except ModEditorError as exc:
            self._show_error(exc)

    def _create_copy(self) -> None:
        try:
            if self.output_var.get().strip():
                self.controller.set_output_path(Path(self.output_var.get()))
        except ModEditorError as exc:
            self._show_error(exc)
            return
        self._start_job(
            "Creating exclusive unmodified source copy…",
            self.controller.create_staging_copy,
            lambda result: messagebox.showinfo(
                "Source copy complete",
                f"Verified {result.bytes_copied:,} bytes.\n\n{result.note}",
                parent=self.root,
            ),
        )

    def _validate_provider(self) -> None:
        try:
            if self.output_var.get().strip():
                self.controller.set_output_path(Path(self.output_var.get()))
            self.controller.typed_provider_request()
        except ModEditorError as exc:
            self._show_error(exc)
            return
        self._start_job(
            "Typed provider preflight…",
            lambda: self.controller.validate_typed_provider(self._on_provider_event),
            lambda _result: messagebox.showinfo(
                "Typed validation passed",
                (
                    "Typed recipe/project schema and user-authored inputs passed the "
                    "validator. No game image was built."
                ),
                parent=self.root,
            ),
        )

    def _build_provider(self) -> None:
        try:
            if self.output_var.get().strip():
                self.controller.set_output_path(Path(self.output_var.get()))
            request = self.controller.typed_provider_request()
        except ModEditorError as exc:
            self._show_error(exc)
            return
        confirmed = messagebox.askyesno(
            "Build copied game output",
            (
                "This will read and re-hash your selected retail source, create a new copied "
                "output, then run a separate verifier. Existing paths are refused.\n\n"
                f"Output: {request.output_xiso}\n"
                f"Manifest: {request.manifest}\n"
                f"Artifacts: {request.artifact_dir}\n\n"
                "Continue?"
            ),
            parent=self.root,
        )
        if not confirmed:
            return
        self._start_job(
            "Typed build preflight…",
            lambda: self.controller.build_typed_provider(self._on_provider_event),
            lambda result: messagebox.showinfo(
                "Typed build verified",
                (
                    "The copied output was built and independently verified successfully.\n\n"
                    f"Output: {request.output_xiso}\n"
                    f"Manifest: {request.manifest}\n"
                    f"Artifacts: {request.artifact_dir}\n"
                    f"Provider: {result.provider_id}"
                ),
                parent=self.root,
            ),
        )

    def _on_log(self, _entry: LogEntry) -> None:
        self._jobs.put(("log", _entry, None))

    def _on_provider_event(self, event) -> None:
        self._jobs.put(("provider_event", event, None))

    def _refresh_log(self) -> None:
        project = self.controller.project
        rows = project.log if project else []
        text = "\n".join(f"[{row.timestamp}] {row.level}: {row.message}" for row in rows)
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", text)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _start_job(
        self, label: str, function: Callable[[], Any], success: Callable[[Any], None] | None
    ) -> None:
        if self._busy:
            return
        self._busy = True
        self.status_var.set(label)
        self._set_project_controls(False)

        def worker() -> None:
            try:
                self._jobs.put(("success", function(), success))
            except BaseException as exc:
                self._jobs.put(("error", exc, None))

        threading.Thread(target=worker, name="mod-editor-job", daemon=True).start()

    def _poll_jobs(self) -> None:
        try:
            kind, payload, callback = self._jobs.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_jobs)
            return
        if kind == "log":
            self._refresh_log()
            self.root.after(50, self._poll_jobs)
            return
        if kind == "provider_event":
            self.status_var.set(f"{payload.stage.value}: {payload.message}")
            self._refresh_log()
            self.root.after(50, self._poll_jobs)
            return
        self._busy = False
        self._set_project_controls(self.controller.project is not None)
        if kind == "error":
            self._show_error(payload)
            self.status_var.set("Operation failed")
        else:
            if callback:
                callback(payload)
            self.status_var.set("Ready")
        self._refresh_project_label()
        self._refresh_log()
        self.root.after(100, self._poll_jobs)

    def _set_project_controls(self, enabled: bool) -> None:
        state = "normal" if enabled and not self._busy else "disabled"
        for widget in getattr(self, "_project_widgets", []):
            widget.config(state=state)
        self.add_button.config(state="disabled")
        self.provider_import_button.config(state="disabled")
        self.provider_recipe_button.config(state="disabled")
        self.apf_export_button.config(state="disabled")
        self.remove_button.config(state=state)
        if enabled and not self._busy:
            self._refresh_provider_buttons()
            # Background jobs temporarily disable every project action. Restore
            # selection-dependent queue/provider/recipe gates on the Tk thread
            # instead of requiring the user to change rows and select this one
            # again after hashing, validation, a build, or an error.
            self._show_capability()

    def _show_error(self, error: BaseException) -> None:
        messagebox.showerror("Mod editor", str(error), parent=self.root)


def main() -> int:
    root = tk.Tk()
    ModEditorApp(root)
    root.mainloop()
    return 0


class NewProjectDialog:
    def __init__(self, parent: tk.Tk):
        self.parent = parent
        self.result: tuple[str, GameId] | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("New Mod Project")
        self.window.resizable(False, False)
        self.window.transient(parent)
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Project name").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar()
        name = ttk.Entry(body, textvariable=self.name_var, width=44)
        name.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 9))
        ttk.Label(body, text="Game / platform").grid(row=2, column=0, sticky="w")
        self.display_to_game = {item.display_name: item for item in GameId}
        self.game_var = tk.StringVar(value=GameId.NFL2K5.display_name)
        ttk.Combobox(
            body,
            textvariable=self.game_var,
            values=list(self.display_to_game),
            state="readonly",
            width=42,
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 12))
        ttk.Button(body, text="Cancel", command=self.window.destroy).grid(row=4, column=0, sticky="e", padx=3)
        ttk.Button(body, text="Create Project", command=self._accept).grid(row=4, column=1, sticky="e")
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        self.window.bind("<Return>", lambda _event: self._accept())
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        name.focus_set()

    def _accept(self) -> None:
        cleaned = self.name_var.get().strip()
        if not cleaned:
            messagebox.showerror("New project", "Project name cannot be empty", parent=self.window)
            return
        self.result = (cleaned, self.display_to_game[self.game_var.get()])
        self.window.destroy()

    def show(self) -> tuple[str, GameId] | None:
        self.window.grab_set()
        self.parent.wait_window(self.window)
        return self.result


class ScorebugRecipeDialog:
    """Collect named PNGs only; the recipe core performs all validation."""

    TARGETS = (
        ("score_buga", "64x64 field frame/corner atlas"),
        ("shield_espn", "128x64 ESPN strip"),
        ("digital_font", "128x128 shared/global digit atlas"),
    )

    def __init__(self, parent: tk.Tk):
        self.parent = parent
        self.result: tuple[str, list[ScorebugRecipeEdit]] | None = None
        self.window = tk.Toplevel(parent)
        self.window.title("Create NFL 2K5 Scorebug Recipe")
        self.window.resizable(True, False)
        self.window.transient(parent)
        body = ttk.Frame(self.window, padding=12)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Purpose / description").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        self.purpose_var = tk.StringVar(
            value="User-authored NFL 2K5 scorebug texture project."
        )
        purpose = ttk.Entry(body, textvariable=self.purpose_var, width=78)
        purpose.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(2, 10))

        self.path_vars: dict[str, tk.StringVar] = {}
        for index, (target, description) in enumerate(self.TARGETS, start=2):
            ttk.Label(body, text=f"{target} — {description}").grid(
                row=index, column=0, sticky="w", padx=(0, 6), pady=3
            )
            variable = tk.StringVar()
            self.path_vars[target] = variable
            ttk.Entry(body, textvariable=variable, width=48).grid(
                row=index, column=1, sticky="ew", pady=3
            )
            ttk.Button(
                body,
                text="Choose PNG…",
                command=lambda name=target: self._choose_png(name),
            ).grid(row=index, column=2, sticky="ew", padx=(6, 0), pady=3)

        note_row = 2 + len(self.TARGETS)
        ttk.Label(
            body,
            text=(
                "Choose one to three exact RGBA PNGs. digital_font is global UI art, "
                "not scorebug-local. Existing recipe files are never overwritten."
            ),
            foreground="#555",
            wraplength=720,
        ).grid(row=note_row, column=0, columnspan=3, sticky="w", pady=(8, 10))
        buttons = ttk.Frame(body)
        buttons.grid(row=note_row + 1, column=0, columnspan=3, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.window.destroy).pack(
            side="left", padx=3
        )
        ttk.Button(buttons, text="Continue…", command=self._accept).pack(side="left")
        body.columnconfigure(1, weight=1)
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        purpose.focus_set()

    def _choose_png(self, target: str) -> None:
        path = filedialog.askopenfilename(
            parent=self.window,
            title=f"Choose {target} PNG",
            filetypes=(("PNG image", "*.png"), ("All files", "*")),
        )
        if path:
            self.path_vars[target].set(path)

    def _accept(self) -> None:
        purpose = self.purpose_var.get().strip()
        edits = [
            ScorebugRecipeEdit(target, Path(self.path_vars[target].get().strip()))
            for target, _description in self.TARGETS
            if self.path_vars[target].get().strip()
        ]
        if not purpose:
            messagebox.showerror(
                "Scorebug recipe", "Purpose cannot be empty", parent=self.window
            )
            return
        if not edits:
            messagebox.showerror(
                "Scorebug recipe",
                "Choose at least one scorebug PNG",
                parent=self.window,
            )
            return
        self.result = (purpose, edits)
        self.window.destroy()

    def show(self) -> tuple[str, list[ScorebugRecipeEdit]] | None:
        self.window.grab_set()
        self.parent.wait_window(self.window)
        return self.result


if __name__ == "__main__":
    raise SystemExit(main())

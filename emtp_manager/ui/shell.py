"""Tkinter workbench shell for managed EMTP projects."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

from emtp_manager.devices.generation import GenerationDevice, GenerationDeviceCatalog
from emtp_manager.integration.session import EmtpSession
from emtp_manager.operational_scenarios import (
    OperationalScenarioChange,
    OperationalScenarioManager,
    OperationalScenarioRecord,
)
from emtp_manager.workspace.manager import ManagedProject, WorkspaceManager


COLORS = {
    "background": "#e8edf1",
    "sidebar": "#314757",
    "surface": "#f8fafb",
    "surface_active": "#d9e4eb",
    "border": "#b8c6cf",
    "text": "#263a48",
    "muted": "#5f7381",
    "accent": "#087fbe",
    "accent_dark": "#06699e",
    "action": "#4b6d82",
    "cyan": "#2397bd",
    "success": "#3b9f76",
    "warning": "#e59a2c",
}


class MainWindow:
    """Project overview; later workbench tools share this visual shell."""

    def __init__(
        self,
        root: tk.Tk,
        session_factory: Callable[[], EmtpSession] = EmtpSession,
        workspace: WorkspaceManager | None = None,
    ) -> None:
        self.root = root
        self._session_factory = session_factory
        self._project_sessions: dict[str, EmtpSession] = {}
        self._workspace = workspace or WorkspaceManager()
        self._projects: dict[str, ManagedProject] = {}
        self._generation_devices: dict[str, GenerationDevice] = {}
        self._scenario_rows: dict[str, dict[str, Any]] = {}
        self._scenario_drafts: dict[str, dict[str, str]] = {}
        self._scenario_sort_column = "object"
        self._scenario_sort_reverse = False
        self._scenario_zone_filter = tk.StringVar(value="All Zones")
        self._scenario_technology_filter = tk.StringVar(value="All Technologies")
        self._scenario_object_filter = tk.StringVar()
        self._scenario_editor: ttk.Entry | ttk.Combobox | None = None
        self._project_design_paths: dict[str, Path] = {}
        self._scenario_project_choice = tk.StringVar()
        self._scenario_project_ids: dict[str, str] = {}
        self._status = tk.StringVar(value="Preparing managed workspace...")
        self._selection_detail = tk.StringVar(value="Select a project to inspect its workspace.")

        self._apply_theme()
        self._build_window()
        self._load_workspace()

    def _apply_theme(self) -> None:
        self.root.title("EMTP Data Manager")
        self.root.minsize(1050, 650)
        self.root.configure(background=COLORS["background"])

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=COLORS["background"])
        style.configure("Sidebar.TFrame", background=COLORS["sidebar"])
        style.configure("BrandRail.TFrame", background=COLORS["accent"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Title.TLabel", background=COLORS["background"], foreground=COLORS["text"], font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=COLORS["background"], foreground=COLORS["muted"], font=("Segoe UI", 10))
        style.configure("SidebarTitle.TLabel", background=COLORS["sidebar"], foreground=COLORS["text"], font=("Segoe UI", 17, "bold"))
        style.configure("SidebarLabel.TLabel", background=COLORS["sidebar"], foreground="#d7e4eb", font=("Segoe UI", 9))
        style.configure("BrandSub.TLabel", background=COLORS["sidebar"], foreground=COLORS["cyan"], font=("Segoe UI", 8, "bold"))
        style.configure("CardTitle.TLabel", background=COLORS["surface"], foreground=COLORS["text"], font=("Segoe UI", 11, "bold"))
        style.configure("CardText.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=COLORS["background"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("Nav.TButton", background=COLORS["sidebar"], foreground="#f1f6f8", borderwidth=0, padding=(16, 10), anchor="w")
        style.map("Nav.TButton", background=[("active", COLORS["surface_active"])], foreground=[("active", COLORS["text"]), ("!disabled", "#f1f6f8")])
        style.configure("Primary.TButton", background=COLORS["accent_dark"], foreground=COLORS["text"], borderwidth=0, padding=(14, 9), font=("Segoe UI", 9, "bold"))
        style.map("Primary.TButton", background=[("active", COLORS["accent"])], foreground=[("!disabled", "#ffffff"), ("disabled", "#e0e9ee")])
        style.configure("Action.TButton", background=COLORS["action"], foreground="#ffffff", borderwidth=0, padding=(12, 8))
        style.map("Action.TButton", background=[("active", "#39596d")], foreground=[("!disabled", "#ffffff"), ("disabled", "#dbe5ea")])
        style.configure("Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"], foreground=COLORS["text"], borderwidth=1, relief="solid", bordercolor="#bac8d1", lightcolor="#dbe3e8", darkcolor="#aebdc7", rowheight=34, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=COLORS["sidebar"], foreground="#f1f6f8", relief="solid", borderwidth=1, font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", COLORS["surface_active"])], foreground=[("selected", COLORS["text"])])

    def _build_window(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame")
        shell.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        shell.columnconfigure(2, weight=1)
        shell.rowconfigure(0, weight=1)

        self._build_sidebar(shell)
        self._build_project_overview(shell)
        self._build_generation_devices(shell)
        self._build_operational_scenario_manager(shell)

    def _build_sidebar(self, shell: ttk.Frame) -> None:
        sidebar = ttk.Frame(shell, style="Sidebar.TFrame", padding=(14, 22))
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)

        ttk.Label(sidebar, text="POWER SYSTEM WORKBENCH", style="BrandSub.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(sidebar, text="DATA MANAGER", style="SidebarLabel.TLabel").grid(row=1, column=0, pady=(2, 26), sticky="w")

        ttk.Button(sidebar, text="Projects", style="Nav.TButton", command=self._show_projects).grid(row=2, column=0, pady=2, sticky="ew")
        ttk.Button(sidebar, text="Operational Scenario Manager", style="Nav.TButton", command=self._show_operational_scenarios).grid(row=3, column=0, pady=(12, 2), sticky="ew")

        ttk.Frame(shell, style="BrandRail.TFrame", width=4).grid(row=0, column=1, sticky="ns")

    def _build_project_overview(self, shell: ttk.Frame) -> None:
        content = ttk.Frame(shell, style="App.TFrame", padding=(30, 26))
        self._project_content = content
        content.grid(row=0, column=2, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(4, weight=1)

        ttk.Label(content, text="Power System Data Manager", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            content,
            text="Managed projects, device chains and operational scenarios for EMTP studies.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, pady=(4, 20), sticky="w")

        actions = ttk.Frame(content, style="App.TFrame")
        actions.grid(row=2, column=0, pady=(0, 16), sticky="ew")
        self.import_button = ttk.Button(actions, text="Import ECF", style="Primary.TButton", command=self.open_design_dialog)
        self.import_button.grid(row=0, column=0, sticky="w")
        self.open_project_button = ttk.Button(actions, text="Open", style="Action.TButton", command=self.open_selected_project, state="disabled")
        self.open_project_button.grid(row=0, column=1, padx=(8, 0), sticky="w")
        self.rename_project_button = ttk.Button(actions, text="Edit Project", style="Action.TButton", command=self.rename_selected_project, state="disabled")
        self.rename_project_button.grid(row=0, column=2, padx=(8, 0), sticky="w")
        self.rename_design_button = ttk.Button(actions, text="Rename ECF", style="Action.TButton", command=self.rename_selected_design, state="disabled")
        self.rename_design_button.grid(row=0, column=3, padx=(8, 0), sticky="w")
        self.description_button = ttk.Button(actions, text="Description", style="Action.TButton", command=self.edit_selected_description, state="disabled")
        self.description_button.grid(row=0, column=4, padx=(8, 0), sticky="w")
        self.promote_button = ttk.Button(actions, text="Working → Baseline", style="Action.TButton", command=self.promote_selected_working, state="disabled")
        self.promote_button.grid(row=1, column=0, pady=(8, 0), sticky="w")
        self.export_button = ttk.Button(actions, text="Export", style="Action.TButton", command=self.export_selected_project, state="disabled")
        self.export_button.grid(row=1, column=1, padx=(8, 0), pady=(8, 0), sticky="w")
        self.cache_button = ttk.Button(actions, text="Clear Cache", style="Action.TButton", command=self.clear_selected_cache, state="disabled")
        self.cache_button.grid(row=1, column=2, padx=(8, 0), pady=(8, 0), sticky="w")
        self.archive_button = ttk.Button(actions, text="Archive (Does Not Delete)", style="Action.TButton", command=self.archive_selected_project, state="disabled")
        self.archive_button.grid(row=1, column=3, padx=(8, 0), pady=(8, 0), sticky="w")

        self.project_tree = ttk.Treeview(content, columns=("name", "description", "design", "last_opened"), show="headings", height=12)
        self.project_tree.heading("name", text="PROJECT")
        self.project_tree.heading("description", text="DESCRIPTION")
        self.project_tree.heading("design", text="WORKING ECF")
        self.project_tree.heading("last_opened", text="LAST OPENED")
        self.project_tree.column("name", width=200, anchor="w")
        self.project_tree.column("description", width=300, anchor="w")
        self.project_tree.column("design", width=280, anchor="w")
        self.project_tree.column("last_opened", width=175, anchor="w")
        self.project_tree.grid(row=3, column=0, sticky="nsew")
        self.project_tree.bind("<<TreeviewSelect>>", self._on_project_select)
        self.project_tree.bind("<Double-1>", lambda _event: self.open_selected_project())

        detail = ttk.Frame(content, style="Surface.TFrame", padding=16)
        detail.grid(row=4, column=0, pady=(16, 0), sticky="ew")
        ttk.Label(detail, text="Selected Project", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(detail, textvariable=self._selection_detail, style="CardText.TLabel", justify="left").grid(row=1, column=0, pady=(7, 0), sticky="w")

        status_line = ttk.Frame(content, style="App.TFrame")
        status_line.grid(row=5, column=0, pady=(18, 0), sticky="ew")
        self.workspace_label = ttk.Label(status_line, text="Workspace: loading...", style="Status.TLabel")
        self.workspace_label.grid(row=0, column=0, sticky="w")
        ttk.Label(status_line, textvariable=self._status, style="Status.TLabel").grid(row=0, column=1, sticky="e")
        status_line.columnconfigure(0, weight=1)

    def _show_projects(self) -> None:
        self._device_content.grid_remove()
        self._scenario_content.grid_remove()
        self._project_content.grid()
        self._status.set("Project overview active.")

    def _build_generation_devices(self, shell: ttk.Frame) -> None:
        content = ttk.Frame(shell, style="App.TFrame", padding=(30, 26))
        self._device_content = content
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)

        ttk.Label(content, text="Devices — Generation", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            content,
            text=(
                "Generation object chains in the open working design. "
                "The upper template and internal model are listed without editing either one."
            ),
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, pady=(4, 20), sticky="w")
        actions = ttk.Frame(content, style="App.TFrame")
        actions.grid(row=2, column=0, pady=(0, 16), sticky="ew")
        ttk.Button(
            actions,
            text="Discover Generation",
            style="Primary.TButton",
            command=self.discover_generation_devices,
        ).grid(row=0, column=0, sticky="w")

        self.device_tree = ttk.Treeview(
            content,
            columns=("kind", "template", "internal_model", "internal_type"),
            show="headings",
            height=12,
        )
        self.device_tree.heading("kind", text="TYPE")
        self.device_tree.heading("template", text="UPPER TEMPLATE")
        self.device_tree.heading("internal_model", text="INTERNAL MODEL")
        self.device_tree.heading("internal_type", text="INTERNAL LIBTYPE")
        self.device_tree.column("kind", width=150, anchor="w")
        self.device_tree.column("template", width=210, anchor="w")
        self.device_tree.column("internal_model", width=260, anchor="w")
        self.device_tree.column("internal_type", width=250, anchor="w")
        self.device_tree.grid(row=3, column=0, sticky="nsew")
        self.device_tree.bind("<<TreeviewSelect>>", self._on_generation_device_select)
        self._device_detail = tk.StringVar(
            value="Open a working project and select Discover Generation."
        )
        detail = ttk.Frame(content, style="Surface.TFrame", padding=16)
        detail.grid(row=4, column=0, pady=(16, 0), sticky="ew")
        ttk.Label(detail, text="Generation Device Object", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(detail, textvariable=self._device_detail, style="CardText.TLabel", justify="left").grid(
            row=1, column=0, pady=(7, 0), sticky="w"
        )

    def _build_operational_scenario_manager(self, shell: ttk.Frame) -> None:
        content = ttk.Frame(shell, style="App.TFrame", padding=(30, 26))
        self._scenario_content = content
        content.columnconfigure(0, weight=1)
        content.rowconfigure(4, weight=1)

        ttk.Label(content, text="Operational Scenario Manager", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            content,
            text=(
                "Scenario and operating-point masks hosted by upper template objects. "
                "The XMLDataGrids layer is separate from internal device management."
            ),
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, pady=(4, 20), sticky="w")

        actions = ttk.Frame(content, style="App.TFrame")
        actions.grid(row=2, column=0, pady=(0, 16), sticky="ew")
        ttk.Label(actions, text="Target Project", style="Subtitle.TLabel").grid(
            row=0, column=0, padx=(0, 8), sticky="w"
        )
        self.scenario_project_selector = ttk.Combobox(
            actions,
            textvariable=self._scenario_project_choice,
            state="readonly",
            width=34,
        )
        self.scenario_project_selector.grid(row=0, column=1, sticky="w")
        self.scenario_project_selector.bind(
            "<<ComboboxSelected>>", self._on_scenario_project_selected
        )
        ttk.Button(
            actions,
            text="Open Working Design",
            style="Action.TButton",
            command=self.open_scenario_project,
        ).grid(row=0, column=2, padx=(8, 0), sticky="w")
        ttk.Button(
            actions,
            text="Load Scenario Values",
            style="Primary.TButton",
            command=self.load_scenario_values,
        ).grid(row=0, column=3, padx=(8, 0), sticky="w")
        actions.columnconfigure(6, weight=1)
        commit_actions = ttk.Frame(actions, style="App.TFrame")
        commit_actions.grid(row=0, column=7, sticky="e")
        self.apply_scenario_button = ttk.Button(
            commit_actions,
            text="Apply Scenario Changes",
            style="Primary.TButton",
            command=self.apply_scenario_changes,
            state="disabled",
        )
        self.apply_scenario_button.grid(row=0, column=0, sticky="e")
        self.discard_scenario_button = ttk.Button(
            commit_actions,
            text="Discard Draft",
            style="Action.TButton",
            command=self.discard_scenario_draft,
            state="disabled",
        )
        self.discard_scenario_button.grid(row=0, column=1, padx=(8, 0), sticky="e")
        ttk.Label(actions, text="Zone", style="Subtitle.TLabel").grid(
            row=1, column=0, pady=(10, 0), sticky="w"
        )
        self.scenario_zone_selector = ttk.Combobox(
            actions,
            textvariable=self._scenario_zone_filter,
            state="readonly",
            width=18,
        )
        self.scenario_zone_selector.grid(row=1, column=1, pady=(10, 0), sticky="w")
        self.scenario_zone_selector.bind("<<ComboboxSelected>>", self._on_scenario_filter_change)
        ttk.Label(actions, text="Technology", style="Subtitle.TLabel").grid(
            row=1, column=2, padx=(12, 8), pady=(10, 0), sticky="w"
        )
        self.scenario_technology_selector = ttk.Combobox(
            actions,
            textvariable=self._scenario_technology_filter,
            state="readonly",
            width=18,
            values=(
                "All Technologies",
                "Photovoltaic",
                "Wind",
                "BESS",
                "DER",
                "Synchronous",
            ),
        )
        self.scenario_technology_selector.grid(row=1, column=3, pady=(10, 0), sticky="w")
        self.scenario_technology_selector.bind(
            "<<ComboboxSelected>>", self._on_scenario_filter_change
        )
        ttk.Label(actions, text="Object", style="Subtitle.TLabel").grid(
            row=1, column=4, padx=(12, 8), pady=(10, 0), sticky="w"
        )
        self.scenario_object_filter = ttk.Entry(
            actions, textvariable=self._scenario_object_filter, width=22
        )
        self.scenario_object_filter.grid(row=1, column=5, pady=(10, 0), sticky="w")
        self.scenario_object_filter.bind("<KeyRelease>", self._on_scenario_filter_change)
        self._scenario_project_state = tk.StringVar(value="Select a target project.")
        ttk.Label(content, textvariable=self._scenario_project_state, style="Status.TLabel").grid(
            row=3, column=0, pady=(0, 8), sticky="w"
        )

        self.scenario_tree = ttk.Treeview(
            content,
            columns=(
                "object",
                "zone",
                "technology",
                "status",
                "active_power",
                "reactive_power",
                "voltage_setpoint",
                "bus_type",
            ),
            show="headings",
            height=12,
        )
        headings = {
            "object": "Object",
            "zone": "Zone",
            "technology": "Technology",
            "status": "Status",
            "active_power": "Active Power [MW]",
            "reactive_power": "Reactive Power [MVAr]",
            "voltage_setpoint": "Voltage Setpoint [pu]",
            "bus_type": "Bus Type",
        }
        for column, heading in headings.items():
            self.scenario_tree.heading(
                column,
                text=heading,
                anchor="w" if column == "object" else "center",
                command=lambda selected_column=column: self._sort_scenario_rows(
                    selected_column
                ),
            )
        self.scenario_tree.column("object", width=160, anchor="w")
        self.scenario_tree.column("zone", width=110, anchor="center")
        self.scenario_tree.column("technology", width=125, anchor="center")
        self.scenario_tree.column("status", width=80, anchor="center")
        self.scenario_tree.column("active_power", width=140, anchor="center")
        self.scenario_tree.column("reactive_power", width=155, anchor="center")
        self.scenario_tree.column("voltage_setpoint", width=150, anchor="center")
        self.scenario_tree.column("bus_type", width=100, anchor="center")
        self.scenario_tree.grid(row=4, column=0, sticky="nsew")
        self.scenario_tree.tag_configure("even", background="#f8fafb")
        self.scenario_tree.tag_configure("odd", background="#eef3f6")
        self.scenario_tree.bind("<<TreeviewSelect>>", self._on_scenario_value_select)
        self.scenario_tree.bind("<Double-1>", self._edit_scenario_cell)

        self._scenario_detail = tk.StringVar(
            value="Select a project, open its working design, then load scenario values."
        )
        detail = ttk.Frame(content, style="Surface.TFrame", padding=16)
        detail.grid(row=5, column=0, pady=(16, 0), sticky="ew")
        ttk.Label(detail, text="Operational Scenario Value", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            detail,
            textvariable=self._scenario_detail,
            style="CardText.TLabel",
            justify="left",
        ).grid(row=1, column=0, pady=(7, 0), sticky="w")

    def _show_generation_devices(self) -> None:
        self._project_content.grid_remove()
        self._scenario_content.grid_remove()
        self._device_content.grid(row=0, column=2, sticky="nsew")
        if not self._project_sessions:
            self._status.set("Open a working design before discovering its generation devices.")
        else:
            self._status.set("Devices / Generation: read-only object-chain inventory.")

    def _show_operational_scenarios(self) -> None:
        self._project_content.grid_remove()
        self._device_content.grid_remove()
        self._scenario_content.grid(row=0, column=2, sticky="nsew")
        if not self._project_sessions:
            self._status.set("Select a target project and open its working design.")
        else:
            self._status.set("Operational Scenario Manager: XMLDataGrids masks in read-only mode.")

    def _show_unavailable(self, feature: str) -> None:
        self._status.set(f"{feature} will be enabled as the workbench grows.")

    def _load_workspace(self) -> None:
        try:
            self._workspace.initialize()
            self.workspace_label.config(text=f"Workspace: {self._workspace.root}")
            self._refresh_projects()
            self._status.set("Workspace ready. Import or select a project.")
        except Exception as exc:
            self.workspace_label.config(text=f"Workspace unavailable: {self._workspace.root}")
            self._status.set("Workspace initialization failed.")
            self.import_button.state(("disabled",))
            messagebox.showerror("Workspace", str(exc), parent=self.root)

    def _refresh_projects(self, select_project_id: str | None = None) -> None:
        for item_id in self.project_tree.get_children():
            self.project_tree.delete(item_id)
        projects = self._workspace.list_projects()
        self._projects = {project.id: project for project in projects}
        self._refresh_scenario_project_choices()
        for project in projects:
            self.project_tree.insert(
                "",
                "end",
                iid=project.id,
                values=(
                    project.name,
                    project.description.replace("\n", " ") or "—",
                    project.design_relative_path,
                    project.last_opened_at or "Never",
                ),
            )
        self._clear_selection()
        if select_project_id in self._projects:
            self.project_tree.selection_set(select_project_id)
            self.project_tree.focus(select_project_id)
            self._on_project_select(None)

    def _refresh_scenario_project_choices(self) -> None:
        current_project_id = self._scenario_project_ids.get(
            self._scenario_project_choice.get()
        )
        choices: dict[str, str] = {}
        for project in self._projects.values():
            choices[f"{project.name}  [{project.id[-8:]}]"] = project.id
        self._scenario_project_ids = choices
        self.scenario_project_selector.configure(values=tuple(choices))
        selected_choice = next(
            (choice for choice, project_id in choices.items() if project_id == current_project_id),
            "",
        )
        self._scenario_project_choice.set(selected_choice)
        self._update_scenario_project_state()

    def _selected_scenario_project(self) -> ManagedProject | None:
        project_id = self._scenario_project_ids.get(self._scenario_project_choice.get())
        return self._projects.get(project_id) if project_id else None

    def _on_scenario_project_selected(self, _event: object) -> None:
        self._scenario_rows = {}
        self._scenario_drafts = {}
        self._set_scenario_draft_state()
        self._render_scenario_rows()
        self._scenario_detail.set(
            "Open the selected working design, then load scenario values."
        )
        self._update_scenario_project_state()

    def _update_scenario_project_state(self) -> None:
        project = self._selected_scenario_project()
        if project is None:
            self._scenario_project_state.set("Select a target project.")
            return
        session = self._project_sessions.get(project.id)
        if session is not None and session.is_connected:
            self._scenario_project_state.set(
                f"Working design open for {project.name}. Scenario values are ready to load."
            )
        else:
            self._scenario_project_state.set(
                f"{project.name} is not open. Use Open Working Design first."
            )

    def open_scenario_project(self) -> None:
        project = self._selected_scenario_project()
        if project is None:
            messagebox.showinfo(
                "Open Working Design",
                "Select a target project first.",
                parent=self.root,
            )
            return
        self._open_project(project, load_scenario_values=True)
        self._update_scenario_project_state()

    def _clear_selection(self) -> None:
        self._selection_detail.set("Select a project to inspect its workspace.")
        for button in self._selection_buttons():
            button.state(("disabled",))

    def _selected_project(self) -> ManagedProject | None:
        selected = self.project_tree.selection()
        return self._projects.get(selected[0]) if selected else None

    def _on_project_select(self, _event: object) -> None:
        project = self._selected_project()
        if project is None:
            self._clear_selection()
            return
        project_directory = self._workspace.project_directory(project)
        description = project.description or "No description."
        self._selection_detail.set(
            f"Description: {description}\n"
            f"Baseline: {project_directory / 'baseline'}\n"
            f"Working: {project_directory / 'working'}\n"
            f"Runs: {project_directory / 'runs'}   Cache: {project_directory / 'cache'}"
        )
        for button in self._selection_buttons():
            button.state(("!disabled",))

    def _selection_buttons(self) -> tuple[ttk.Button, ...]:
        return (
            self.open_project_button,
            self.rename_project_button,
            self.rename_design_button,
            self.description_button,
            self.promote_button,
            self.export_button,
            self.cache_button,
            self.archive_button,
        )

    def open_design_dialog(self) -> None:
        selected_path = filedialog.askopenfilename(parent=self.root, title="Import EMTP Design", filetypes=[("EMTP Design", "*.ecf")])
        if selected_path:
            self._import_design(Path(selected_path))

    def _import_design(self, path: Path) -> None:
        self.import_button.state(("disabled",))
        self._status.set("Importing the selected ECF into the workspace...")
        self.root.update_idletasks()
        try:
            project = self._workspace.import_design(path)
        except Exception as exc:
            self._status.set("The design could not be imported.")
            messagebox.showerror("Import Design", str(exc), parent=self.root)
            return
        finally:
            self.import_button.state(("!disabled",))
        self._refresh_projects(project.id)
        self._status.set("Project imported. Open it explicitly when ready.")

    def open_selected_project(self) -> None:
        project = self._selected_project()
        if project is not None:
            self._open_project(project)

    def _open_project(
        self,
        project: ManagedProject,
        load_scenario_values: bool = False,
    ) -> None:
        self._status.set("Starting EMTP and opening the working design...")
        self.root.update_idletasks()
        try:
            working_design_path = self._workspace.working_design_path(project)
            session = self._project_sessions.get(project.id)
            if session is None:
                session = self._session_factory()
                self._project_sessions[project.id] = session
            opened_path = session.open_design(working_design_path)
        except Exception as exc:
            self._status.set("The project could not be opened.")
            messagebox.showerror("Open Project", str(exc), parent=self.root)
            return
        self._project_design_paths[project.id] = opened_path
        self._status.set(f"Open: {opened_path.name}")
        self._refresh_projects(project.id)
        if load_scenario_values:
            self.load_scenario_values()

    def discover_generation_devices(self) -> None:
        """Read generation object chains from the currently open working ECF."""
        project = self._selected_scenario_project()
        session = self._project_sessions.get(project.id) if project is not None else None
        if session is None or not session.is_connected:
            messagebox.showinfo(
                "Discover Generation",
                "Open a project first. Devices are read from the working design currently open in EMTP.",
                parent=self.root,
            )
            return
        self._status.set("Discovering generation devices...")
        self.root.update_idletasks()
        try:
            devices = GenerationDeviceCatalog(session.emtp_object).discover()
        except Exception as exc:
            self._status.set("Generation devices could not be discovered.")
            messagebox.showerror("Discover Generation", str(exc), parent=self.root)
            return

        for item_id in self.device_tree.get_children():
            self.device_tree.delete(item_id)
        self._generation_devices = {}
        for index, device in enumerate(devices):
            item_id = f"generation-device-{index}"
            self._generation_devices[item_id] = device
            self.device_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    device.kind.value,
                    device.template_name,
                    device.internal_model_name,
                    device.internal_model_lib_type,
                ),
            )
        self._device_detail.set(
            "Select a generation object to inspect its device chain."
            if devices
            else "No generation templates were recognized in this design."
        )
        self._status.set(f"{len(devices)} generation device(s) discovered.")

    def _on_generation_device_select(self, _event: object) -> None:
        selected = self.device_tree.selection()
        device = self._generation_devices.get(selected[0]) if selected else None
        if device is None:
            return
        self._device_detail.set(
            f"Python object: {device.kind.value}\n"
            f"Upper template: {device.template_name} ({device.template_lib_type})\n"
            f"Internal model reference: {device.internal_model_name} ({device.internal_model_lib_type})\n"
            f"Internal reference path: {device.internal_model_path}\n"
            "Current scope: device recognition only; no editing of the template or internal model."
        )

    def load_scenario_values(self) -> None:
        """Load recognized settable values from a selected project's XML mask."""
        project = self._selected_scenario_project()
        if project is None:
            messagebox.showinfo(
                "Load Scenario Values",
                "Select a target project first.",
                parent=self.root,
            )
            return
        session = self._project_sessions.get(project.id)
        if session is None or not session.is_connected:
            messagebox.showinfo(
                "Load Scenario Values",
                "Open this project's working design before loading scenario values.",
                parent=self.root,
            )
            return
        self._status.set(f"Loading scenario values for {project.name}...")
        self.root.update_idletasks()
        try:
            records = OperationalScenarioManager(session.emtp_object).load_generation_records()
        except Exception as exc:
            self._status.set("Scenario values could not be loaded.")
            messagebox.showerror("Load Scenario Values", str(exc), parent=self.root)
            return

        self._scenario_rows = {}
        parameter_columns = {
            "in_service": "status",
            "p_setpoint": "active_power",
            "q_setpoint": "reactive_power",
            "v_setpoint": "voltage_setpoint",
            "bus_type": "bus_type",
        }
        for index, record in enumerate(records):
            row = {
                "object": record.mask.mask_host_name,
                "zone": record.zone,
                "technology": record.mask.kind.value,
                "status": "",
                "active_power": "",
                "reactive_power": "",
                "voltage_setpoint": "",
                "bus_type": "",
            }
            for parameter, value in record.values.items():
                row[parameter_columns[parameter]] = value
            row["record"] = record
            row["original"] = {
                key: str(value)
                for key, value in row.items()
                if key not in {"record", "original"}
            }
            item_id = f"scenario-row-{index}"
            self._scenario_rows[item_id] = row
        zones = sorted({str(row["zone"]) for row in self._scenario_rows.values()})
        self.scenario_zone_selector.configure(values=("All Zones", *zones))
        if self._scenario_zone_filter.get() not in {"All Zones", *zones}:
            self._scenario_zone_filter.set("All Zones")
        self._scenario_drafts = {}
        self._set_scenario_draft_state()
        self._render_scenario_rows()
        self._scenario_detail.set(
            "Select an object to inspect its XMLDataGrids scenario source."
            if records
            else "No recognized settable generation values were found in this design."
        )
        self._status.set(f"{len(records)} scenario object(s) loaded for {project.name}.")

    def _on_scenario_filter_change(self, _event: object | None = None) -> None:
        self._render_scenario_rows()

    def _sort_scenario_rows(self, column: str) -> None:
        if self._scenario_sort_column == column:
            self._scenario_sort_reverse = not self._scenario_sort_reverse
        else:
            self._scenario_sort_column = column
            self._scenario_sort_reverse = False
        self._render_scenario_rows()

    def _render_scenario_rows(self) -> None:
        for item_id in self.scenario_tree.get_children():
            self.scenario_tree.delete(item_id)
        zone_filter = self._scenario_zone_filter.get()
        technology_filter = self._scenario_technology_filter.get()
        object_filter = self._scenario_object_filter.get().casefold().strip()
        item_ids = [
            item_id
            for item_id, row in self._scenario_rows.items()
            if (zone_filter == "All Zones" or row["zone"] == zone_filter)
            and (
                technology_filter == "All Technologies"
                or row["technology"] == technology_filter
            )
            and (not object_filter or object_filter in row["object"].casefold())
        ]
        item_ids.sort(
            key=lambda item_id: self._scenario_sort_key(
                self._scenario_rows[item_id], self._scenario_sort_column
            ),
            reverse=self._scenario_sort_reverse,
        )
        for index, item_id in enumerate(item_ids):
            row = self._scenario_rows[item_id]
            self.scenario_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    row["object"],
                    row["zone"],
                    row["technology"],
                    row["status"],
                    row["active_power"],
                    row["reactive_power"],
                    row["voltage_setpoint"],
                    row["bus_type"],
                ),
                tags=("even" if index % 2 == 0 else "odd",),
            )

    @staticmethod
    def _scenario_sort_key(row: dict[str, Any], column: str) -> tuple[int, Any]:
        value = str(row[column]).strip()
        if column in {"status", "active_power", "reactive_power", "voltage_setpoint", "bus_type"}:
            bus_type_values = {"PQ": 1.0, "PV": 2.0, "SLACK": 3.0}
            try:
                return (0, float(bus_type_values.get(value.upper(), value)))
            except ValueError:
                return (1, value.casefold())
        return (0, value.casefold())

    def _edit_scenario_cell(self, event: tk.Event[tk.Misc]) -> None:
        item_id = self.scenario_tree.identify_row(event.y)
        column = self.scenario_tree.identify_column(event.x)
        if not item_id or not column:
            return
        column_id = str(self.scenario_tree.column(column, "id"))
        editable_columns = {
            "zone",
            "status",
            "active_power",
            "reactive_power",
            "voltage_setpoint",
            "bus_type",
        }
        row = self._scenario_rows.get(item_id)
        if row is None or column_id not in editable_columns:
            return
        if column_id in {"voltage_setpoint", "bus_type"} and row["technology"] != "Synchronous":
            return
        if self._scenario_editor is not None:
            self._scenario_editor.destroy()
        bounding_box = self.scenario_tree.bbox(item_id, column)
        if not bounding_box:
            return
        x, y, width, height = bounding_box
        if column_id == "status":
            editor: ttk.Entry | ttk.Combobox = ttk.Combobox(
                self.scenario_tree, values=("0", "1"), state="readonly"
            )
        elif column_id == "bus_type":
            editor = ttk.Combobox(
                self.scenario_tree,
                values=("PQ", "PV", "Slack", "1", "2", "3"),
                state="readonly",
            )
        else:
            editor = ttk.Entry(self.scenario_tree)
        if isinstance(editor, ttk.Combobox):
            editor.set(str(row[column_id]))
        else:
            editor.insert(0, str(row[column_id]))
        editor.place(x=x, y=y, width=width, height=height)
        self._scenario_editor = editor

        def commit(_event: object | None = None) -> None:
            new_value = editor.get().strip()
            editor.destroy()
            self._scenario_editor = None
            if new_value == row["original"][column_id]:
                self._scenario_drafts.get(item_id, {}).pop(column_id, None)
            else:
                self._scenario_drafts.setdefault(item_id, {})[column_id] = new_value
            if item_id in self._scenario_drafts and not self._scenario_drafts[item_id]:
                del self._scenario_drafts[item_id]
            row[column_id] = new_value
            self._set_scenario_draft_state()
            self._render_scenario_rows()

        editor.bind("<Return>", commit)
        editor.bind("<FocusOut>", commit)
        editor.focus_set()

    def _set_scenario_draft_state(self) -> None:
        state = "!disabled" if self._scenario_drafts else "disabled"
        self.apply_scenario_button.state((state,))
        self.discard_scenario_button.state((state,))

    def discard_scenario_draft(self) -> None:
        if not self._scenario_drafts:
            return
        for row in self._scenario_rows.values():
            for column, value in row["original"].items():
                row[column] = value
        self._scenario_drafts = {}
        self._set_scenario_draft_state()
        self._render_scenario_rows()
        self._status.set("Scenario draft discarded.")

    def apply_scenario_changes(self) -> None:
        project = self._selected_scenario_project()
        if project is None or not self._scenario_drafts:
            return
        session = self._project_sessions.get(project.id)
        if session is None or not session.is_connected:
            messagebox.showwarning(
                "Apply Scenario Changes",
                "The target project's working design is not open.",
                parent=self.root,
            )
            return
        parameter_columns = {
            "status": "in_service",
            "active_power": "p_setpoint",
            "reactive_power": "q_setpoint",
            "voltage_setpoint": "v_setpoint",
            "bus_type": "bus_type",
        }
        changes: list[OperationalScenarioChange] = []
        for item_id, draft in self._scenario_drafts.items():
            row = self._scenario_rows[item_id]
            parameter_values = {
                parameter_columns[column]: value
                for column, value in draft.items()
                if column in parameter_columns
            }
            changes.append(
                OperationalScenarioChange(
                    record=row["record"],
                    parameter_values=parameter_values,
                    zone=draft.get("zone"),
                )
            )
        try:
            OperationalScenarioManager(session.emtp_object).apply_generation_changes(changes)
        except Exception as exc:
            messagebox.showerror("Apply Scenario Changes", str(exc), parent=self.root)
            return
        self._status.set(f"Scenario changes applied to {len(changes)} object(s).")
        self.load_scenario_values()

    def _on_scenario_value_select(self, _event: object) -> None:
        selected = self.scenario_tree.selection()
        row = self._scenario_rows.get(selected[0]) if selected else None
        if row is None:
            return
        self._scenario_detail.set(
            f"Object: {row['object']} ({row['technology']})\n"
            "Source: upper-template XMLDataGrids\n"
            "Current scope: read-only; no scenario value has been changed."
        )

    def rename_selected_project(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        name = simpledialog.askstring(
            "Edit Project",
            "Visible project name:",
            initialvalue=project.name,
            parent=self.root,
        )
        if name is None:
            return
        try:
            updated_project = self._workspace.rename_project(project, name)
        except Exception as exc:
            messagebox.showerror("Edit Project", str(exc), parent=self.root)
            return
        self._refresh_projects(updated_project.id)
        self._status.set("Project name updated.")

    def rename_selected_design(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        if self._project_is_open(project):
            messagebox.showwarning(
                "Rename ECF",
                "Close this design in EMTP before renaming its managed ECF.",
                parent=self.root,
            )
            return
        filename = simpledialog.askstring(
            "Rename ECF",
            "New ECF name (.ecf):",
            initialvalue=Path(project.design_relative_path).name,
            parent=self.root,
        )
        if filename is None:
            return
        try:
            updated_project = self._workspace.rename_design(project, filename)
        except Exception as exc:
            messagebox.showerror("Rename ECF", str(exc), parent=self.root)
            return
        self._refresh_projects(updated_project.id)
        self._status.set("ECF renamed in baseline and working.")

    def edit_selected_description(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Project Description")
        dialog.configure(background=COLORS["surface"])
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        ttk.Label(dialog, text="Comment or description", style="CardTitle.TLabel").grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")
        editor = tk.Text(
            dialog,
            width=68,
            height=9,
            background=COLORS["background"],
            foreground=COLORS["text"],
            insertbackground=COLORS["text"],
            relief="flat",
            padx=10,
            pady=8,
            wrap="word",
        )
        editor.grid(row=1, column=0, padx=16, sticky="nsew")
        editor.insert("1.0", project.description)

        actions = ttk.Frame(dialog, style="Surface.TFrame")
        actions.grid(row=2, column=0, padx=16, pady=16, sticky="e")

        def save() -> None:
            try:
                updated_project = self._workspace.update_description(
                    project, editor.get("1.0", "end-1c")
                )
            except Exception as exc:
                messagebox.showerror("Description", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._refresh_projects(updated_project.id)
            self._status.set("Description updated.")

        ttk.Button(actions, text="Cancel", style="Action.TButton", command=dialog.destroy).grid(row=0, column=0)
        ttk.Button(actions, text="Save", style="Primary.TButton", command=save).grid(row=0, column=1, padx=(8, 0))
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        editor.focus_set()

    def promote_selected_working(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        if self._project_is_open(project):
            messagebox.showwarning(
                "Working to Baseline",
                "Save and close this design in EMTP before updating baseline.",
                parent=self.root,
            )
            return
        approved = messagebox.askyesno(
            "Working to Baseline",
            "Baseline will be completely replaced by the working copy.\n\n"
            "The original source will not be modified. Continue?",
            parent=self.root,
        )
        if not approved:
            return
        try:
            self._workspace.promote_working_to_baseline(project)
        except Exception as exc:
            messagebox.showerror("Working to Baseline", str(exc), parent=self.root)
            return
        self._status.set("Baseline updated from working.")

    def export_selected_project(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        response = messagebox.askyesnocancel(
            "Export Project",
            "Export baseline?\n\nYes: baseline\nNo: working\nCancel: do not export",
            parent=self.root,
        )
        if response is None:
            return
        source = "baseline" if response else "working"
        destination = filedialog.askdirectory(
            parent=self.root,
            title=f"Destination folder for {source} export",
            mustexist=True,
        )
        if not destination:
            return
        try:
            exported_path = self._workspace.export_project(project, source, destination)
        except Exception as exc:
            messagebox.showerror("Export Project", str(exc), parent=self.root)
            return
        self._status.set(f"Exported {source}: {exported_path}")

    def clear_selected_cache(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        if messagebox.askyesno("Clear Cache", f"Clear only regenerable cache files for '{project.name}'?", parent=self.root):
            self._workspace.clear_cache(project)
            self._status.set(f"Cache cleared for {project.name}.")

    def archive_selected_project(self) -> None:
        project = self._selected_project()
        if project is None:
            return
        if self._project_is_open(project):
            messagebox.showwarning("Archive Project", "The selected project is open in EMTP.", parent=self.root)
            return
        if messagebox.askyesno("Archive Project", f"Archive '{project.name}'? It remains recoverable in the workspace archive folder.", parent=self.root):
            self._workspace.archive_project(project)
            self._refresh_projects()
            self._status.set(f"Project archived: {project.name}.")

    def _project_is_open(self, project: ManagedProject) -> bool:
        design_path = self._project_design_paths.get(project.id)
        if design_path is None:
            return False
        return design_path.is_relative_to(self._workspace.project_directory(project))

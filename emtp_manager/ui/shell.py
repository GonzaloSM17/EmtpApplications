"""Tkinter workbench shell for managed EMTP projects."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

from emtp_manager.devices.generation import (
    BessParameterReader,
    FormDataFormatError,
    GenerationDevice,
    GenerationDeviceCatalog,
    GenerationKind,
    GenerationSummaryReader,
    PhotovoltaicParameterReader,
    SynchronousParameterReader,
)
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
        self._generation_capacities: dict[str, str] = {}
        self._device_scope = "generation"
        self._generation_zone_filter = tk.StringVar(value="All Zones")
        self._generation_object_filter = tk.StringVar()
        self._generation_project_choice = tk.StringVar()
        self._generation_project_ids: dict[str, str] = {}
        self._generation_sort_column = "technology"
        self._generation_sort_reverse = False
        self._generation_grid_lines: list[ttk.Separator] = []
        self._generation_grid_refresh_pending = False
        self._scenario_rows: dict[str, dict[str, Any]] = {}
        self._scenario_drafts: dict[str, dict[str, str]] = {}
        self._scenario_sort_column = "object"
        self._scenario_sort_reverse = False
        self._scenario_zone_filter = tk.StringVar(value="All Zones")
        self._scenario_technology_filter = tk.StringVar(value="All Technologies")
        self._scenario_object_filter = tk.StringVar()
        self._scenario_editor: ttk.Entry | ttk.Combobox | None = None
        self._scenario_active_cell: tuple[str, str] | None = None
        self._scenario_grid_lines: list[ttk.Separator] = []
        self._scenario_grid_refresh_pending = False
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
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = max(1120, screen_width - 20)
        window_height = max(700, screen_height - 70)
        offset_x = max(0, (screen_width - window_width) // 2)
        offset_y = max(0, (screen_height - window_height) // 2)
        self.root.geometry(f"{window_width}x{window_height}+{offset_x}+{offset_y}")
        self.root.minsize(1120, 700)
        self.root.configure(background=COLORS["background"])

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=COLORS["background"])
        style.configure("Sidebar.TFrame", background=COLORS["sidebar"])
        style.configure("BrandRail.TFrame", background=COLORS["accent"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Title.TLabel", background=COLORS["background"], foreground=COLORS["text"], font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=COLORS["background"], foreground=COLORS["muted"], font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=COLORS["background"], foreground=COLORS["accent_dark"], font=("Segoe UI", 10, "bold"))
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
        style.configure("ScenarioGrid.TSeparator", background="#c8d3da")
        style.configure("DeviceGrid.TSeparator", background="#c8d3da")
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

        ttk.Label(sidebar, text="Power System Workbench", style="BrandSub.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(sidebar, text="Data Manager", style="SidebarLabel.TLabel").grid(row=1, column=0, pady=(2, 26), sticky="w")

        ttk.Button(sidebar, text="Projects", style="Nav.TButton", command=self._show_projects).grid(row=2, column=0, pady=2, sticky="ew")
        ttk.Label(sidebar, text="Operational Scenario Manager", style="SidebarLabel.TLabel").grid(row=3, column=0, pady=(20, 3), sticky="w")
        ttk.Button(sidebar, text="Generation", style="Nav.TButton", command=self._show_operational_scenarios).grid(row=4, column=0, pady=2, sticky="ew")
        ttk.Label(sidebar, text="Devices", style="SidebarLabel.TLabel").grid(row=5, column=0, pady=(20, 3), sticky="w")
        ttk.Button(sidebar, text="Generation", style="Nav.TButton", command=self._show_generation_devices).grid(row=6, column=0, pady=2, sticky="ew")
        ttk.Button(sidebar, text="Storage", style="Nav.TButton", command=self._show_storage_devices).grid(row=7, column=0, pady=2, sticky="ew")

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
        self.project_tree.heading("name", text="Project")
        self.project_tree.heading("description", text="Description")
        self.project_tree.heading("design", text="Working ECF")
        self.project_tree.heading("last_opened", text="Last Opened")
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
        content.rowconfigure(5, weight=1)

        self._device_title = tk.StringVar(value="Devices")
        self._device_section = tk.StringVar(value="Generation")
        self._device_subtitle = tk.StringVar(
            value=(
                "Photovoltaic, Wind, DER, and Synchronous chains in the open working design. "
                "Object provides context; Unit Object is the parameter source."
            )
        )
        self._device_discovery_label = tk.StringVar(value="Discover Generation")
        self._device_detail_title = tk.StringVar(value="Generation Device Chain")
        ttk.Label(content, textvariable=self._device_title, style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(content, textvariable=self._device_section, style="Section.TLabel").grid(
            row=1, column=0, pady=(3, 0), sticky="w"
        )
        ttk.Label(
            content,
            textvariable=self._device_subtitle,
            style="Subtitle.TLabel",
        ).grid(row=2, column=0, pady=(4, 20), sticky="w")
        actions = ttk.Frame(content, style="App.TFrame")
        actions.grid(row=3, column=0, pady=(0, 16), sticky="ew")
        ttk.Label(actions, text="Target Project", style="Subtitle.TLabel").grid(
            row=0, column=0, padx=(0, 8), sticky="w"
        )
        self.generation_project_selector = ttk.Combobox(
            actions,
            textvariable=self._generation_project_choice,
            state="readonly",
            width=34,
        )
        self.generation_project_selector.grid(row=0, column=1, sticky="w")
        self.generation_project_selector.bind(
            "<<ComboboxSelected>>", self._on_generation_project_selected
        )
        ttk.Button(
            actions,
            text="Open Working Design",
            style="Action.TButton",
            command=self.open_generation_project,
        ).grid(row=0, column=2, padx=(8, 0), sticky="w")
        ttk.Button(
            actions,
            textvariable=self._device_discovery_label,
            style="Primary.TButton",
            command=self.discover_generation_devices,
        ).grid(row=0, column=3, padx=(8, 0), sticky="w")
        ttk.Button(
            actions,
            text="Save Working Design",
            style="Action.TButton",
            command=self.save_generation_project,
        ).grid(row=0, column=4, padx=(8, 0), sticky="w")
        ttk.Label(actions, text="Zone", style="Subtitle.TLabel").grid(
            row=1, column=0, pady=(10, 0), sticky="w"
        )
        self.generation_zone_selector = ttk.Combobox(
            actions,
            textvariable=self._generation_zone_filter,
            state="readonly",
            width=18,
            values=("All Zones",),
        )
        self.generation_zone_selector.grid(row=1, column=1, pady=(10, 0), sticky="w")
        self.generation_zone_selector.bind(
            "<<ComboboxSelected>>", self._on_generation_filter_change
        )
        ttk.Label(actions, text="Object", style="Subtitle.TLabel").grid(
            row=1, column=2, padx=(12, 8), pady=(10, 0), sticky="w"
        )
        self.generation_object_filter = ttk.Entry(
            actions, textvariable=self._generation_object_filter, width=24
        )
        self.generation_object_filter.grid(row=1, column=3, pady=(10, 0), sticky="w")
        self.generation_object_filter.bind("<KeyRelease>", self._on_generation_filter_change)
        ttk.Button(
            actions,
            text="Auto Fit Columns",
            style="Action.TButton",
            command=self.auto_fit_generation_columns,
        ).grid(row=1, column=4, padx=(12, 0), pady=(10, 0), sticky="w")
        self.inspect_pv_parameters_button = ttk.Button(
            actions,
            text="Inspect Parameters",
            style="Primary.TButton",
            command=self.inspect_device_parameters,
            state="disabled",
        )
        self.inspect_pv_parameters_button.grid(
            row=1, column=5, padx=(8, 0), pady=(10, 0), sticky="w"
        )
        self._generation_project_state = tk.StringVar(value="Select a target project.")
        ttk.Label(content, textvariable=self._generation_project_state, style="Status.TLabel").grid(
            row=4, column=0, pady=(0, 8), sticky="w"
        )

        self.device_tree = ttk.Treeview(
            content,
            columns=("object", "unit_object", "technology", "capacity", "inertia_h", "inertia_gvas", "zone"),
            show="headings",
            height=12,
        )
        generation_headings = {
            "object": "Object",
            "unit_object": "Unit Object",
            "technology": "Technology",
            "capacity": "Capacity [MVA]",
            "inertia_h": "H [s]",
            "inertia_gvas": "Inertia [GVA·s]",
            "zone": "Zone",
        }
        for column, heading in generation_headings.items():
            self.device_tree.heading(
                column,
                text=heading,
                anchor="w" if column in {"object", "unit_object"} else "center",
                command=lambda selected_column=column: self._sort_generation_devices(
                    selected_column
                ),
            )
        self.device_tree.column("object", width=190, anchor="w")
        self.device_tree.column("unit_object", width=210, anchor="w")
        self.device_tree.column("technology", width=130, anchor="center")
        self.device_tree.column("capacity", width=130, anchor="center")
        self.device_tree.column("inertia_h", width=95, anchor="center")
        self.device_tree.column("inertia_gvas", width=145, anchor="center")
        self.device_tree.column("zone", width=110, anchor="center")
        self.device_tree.grid(row=5, column=0, sticky="nsew")
        self.device_tree.tag_configure("even", background="#f8fafb")
        self.device_tree.tag_configure("odd", background="#eef3f6")
        self.device_tree.bind("<<TreeviewSelect>>", self._on_generation_device_select)
        self.device_tree.bind("<Configure>", self._queue_generation_grid_lines)
        self._device_detail = tk.StringVar(
            value="Open a working project and select Discover Generation."
        )
        detail = ttk.Frame(content, style="Surface.TFrame", padding=16)
        detail.grid(row=6, column=0, pady=(16, 0), sticky="ew")
        ttk.Label(detail, textvariable=self._device_detail_title, style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(detail, textvariable=self._device_detail, style="CardText.TLabel", justify="left").grid(
            row=1, column=0, pady=(7, 0), sticky="w"
        )

    def _build_operational_scenario_manager(self, shell: ttk.Frame) -> None:
        content = ttk.Frame(shell, style="App.TFrame", padding=(30, 26))
        self._scenario_content = content
        content.columnconfigure(0, weight=1)
        content.rowconfigure(5, weight=1)

        ttk.Label(content, text="Operational Scenario Manager", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(content, text="Generation", style="Section.TLabel").grid(
            row=1, column=0, pady=(3, 0), sticky="w"
        )
        ttk.Label(
            content,
            text=(
                "Scenario and operating-point masks hosted by upper template objects. "
                "The XMLDataGrids layer is separate from internal device management."
            ),
            style="Subtitle.TLabel",
        ).grid(row=2, column=0, pady=(4, 20), sticky="w")

        actions = ttk.Frame(content, style="App.TFrame")
        actions.grid(row=3, column=0, pady=(0, 16), sticky="ew")
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
        ttk.Button(
            actions,
            text="Save Working Design",
            style="Action.TButton",
            command=self.save_scenario_project,
        ).grid(row=0, column=4, padx=(8, 0), sticky="w")
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
        ttk.Button(
            actions,
            text="Auto Fit Columns",
            style="Action.TButton",
            command=self.auto_fit_scenario_columns,
        ).grid(row=1, column=7, pady=(10, 0), sticky="e")
        self._scenario_project_state = tk.StringVar(value="Select a target project.")
        ttk.Label(content, textvariable=self._scenario_project_state, style="Status.TLabel").grid(
            row=4, column=0, pady=(0, 8), sticky="w"
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
        self.scenario_tree.grid(row=5, column=0, sticky="nsew")
        self.scenario_tree.tag_configure("even", background="#f8fafb")
        self.scenario_tree.tag_configure("odd", background="#eef3f6")
        self.scenario_tree.bind("<<TreeviewSelect>>", self._on_scenario_value_select)
        self.scenario_tree.bind("<Button-1>", self._select_scenario_cell, add="+")
        self.scenario_tree.bind("<Double-1>", self._edit_scenario_cell)
        self.scenario_tree.bind("<Control-c>", self._copy_scenario_cell)
        self.scenario_tree.bind("<Control-C>", self._copy_scenario_cell)
        self.scenario_tree.bind("<Control-v>", self._paste_scenario_cells)
        self.scenario_tree.bind("<Control-V>", self._paste_scenario_cells)
        self.scenario_tree.bind("<Configure>", self._queue_scenario_grid_lines)

        self._scenario_detail = tk.StringVar(
            value="Select a project, open its working design, then load scenario values."
        )
        detail = ttk.Frame(content, style="Surface.TFrame", padding=16)
        detail.grid(row=6, column=0, pady=(16, 0), sticky="ew")
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
        self._configure_device_scope("generation")
        self._project_content.grid_remove()
        self._scenario_content.grid_remove()
        self._device_content.grid(row=0, column=2, sticky="nsew")
        if not self._project_sessions:
            self._status.set("Open a working design before discovering its generation devices.")
        else:
            self._status.set("Devices / Generation: read-only object-chain inventory.")

    def _show_storage_devices(self) -> None:
        self._configure_device_scope("storage")
        self._project_content.grid_remove()
        self._scenario_content.grid_remove()
        self._device_content.grid(row=0, column=2, sticky="nsew")
        if not self._project_sessions:
            self._status.set("Open a working design before discovering storage devices.")
        else:
            self._status.set("Devices / Storage: read-only BESS chain inventory.")

    def _configure_device_scope(self, scope: str) -> None:
        if scope not in {"generation", "storage"}:
            raise ValueError(f"Unknown device scope: {scope}")
        if self._device_scope == scope:
            return
        self._device_scope = scope
        if scope == "generation":
            self._device_section.set("Generation")
            self._device_subtitle.set(
                "Photovoltaic, Wind, DER, and Synchronous chains in the open working design. "
                "Object provides context; Unit Object is the parameter source."
            )
            self._device_discovery_label.set("Discover Generation")
            self._device_detail_title.set("Generation Device Chain")
        else:
            self._device_section.set("Storage")
            self._device_subtitle.set(
                "BESS chains in the open working design. Object provides context; "
                "Unit Object will be mapped to Inverter3P parameters separately."
            )
            self._device_discovery_label.set("Discover Storage")
            self._device_detail_title.set("Storage Device Chain")
        self._generation_devices = {}
        self._generation_capacities = {}
        self._generation_zone_filter.set("All Zones")
        self._generation_object_filter.set("")
        self.generation_zone_selector.configure(values=("All Zones",))
        self._device_detail.set("Open a working project and select discovery.")
        self._render_generation_devices()

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
        self._refresh_generation_project_choices()
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

    def _refresh_generation_project_choices(self) -> None:
        current_project_id = self._generation_project_ids.get(
            self._generation_project_choice.get()
        )
        choices = {
            f"{project.name}  [{project.id[-8:]}]": project.id
            for project in self._projects.values()
        }
        self._generation_project_ids = choices
        self.generation_project_selector.configure(values=tuple(choices))
        selected_choice = next(
            (choice for choice, project_id in choices.items() if project_id == current_project_id),
            "",
        )
        self._generation_project_choice.set(selected_choice)
        self._update_generation_project_state()

    def _selected_generation_project(self) -> ManagedProject | None:
        project_id = self._generation_project_ids.get(self._generation_project_choice.get())
        return self._projects.get(project_id) if project_id else None

    def _on_generation_project_selected(self, _event: object) -> None:
        self._generation_devices = {}
        self._generation_capacities = {}
        self.inspect_pv_parameters_button.state(("disabled",))
        self._render_generation_devices()
        self._device_detail.set(
            f"Open the selected working design, then discover {self._device_section.get().casefold()} chains."
        )
        self._update_generation_project_state()

    def _update_generation_project_state(self) -> None:
        project = self._selected_generation_project()
        if project is None:
            self._generation_project_state.set("Select a target project.")
            return
        session = self._project_sessions.get(project.id)
        if session is not None and session.is_connected:
            self._generation_project_state.set(
                f"Working design open for {project.name}. Generation chains are ready to discover."
            )
        else:
            self._generation_project_state.set(
                f"{project.name} is not open. Use Open Working Design first."
            )

    def open_generation_project(self) -> None:
        project = self._selected_generation_project()
        if project is None:
            messagebox.showinfo(
                "Open Working Design", "Select a target project first.", parent=self.root
            )
            return
        self._open_project(project)
        self._update_generation_project_state()
        session = self._project_sessions.get(project.id)
        if session is not None and session.is_connected:
            self.discover_generation_devices()

    def save_generation_project(self) -> None:
        self._save_working_design(self._selected_generation_project())

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

    def save_scenario_project(self) -> None:
        self._save_working_design(self._selected_scenario_project())

    def _save_working_design(self, project: ManagedProject | None) -> None:
        if project is None:
            messagebox.showinfo(
                "Save Working Design", "Select a target project first.", parent=self.root
            )
            return
        session = self._project_sessions.get(project.id)
        if session is None or not session.is_connected:
            messagebox.showinfo(
                "Save Working Design",
                "Open this project's working design before saving.",
                parent=self.root,
            )
            return
        try:
            saved_path = session.save_design()
        except Exception as exc:
            messagebox.showerror("Save Working Design", str(exc), parent=self.root)
            return
        self._status.set(f"Working design saved: {saved_path.name}")

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
        """Read the selected Devices inventory from the open working ECF."""
        project = self._selected_generation_project()
        session = self._project_sessions.get(project.id) if project is not None else None
        if session is None or not session.is_connected:
            messagebox.showinfo(
                self._device_discovery_label.get(),
                "Open a project first. Devices are read from the working design currently open in EMTP.",
                parent=self.root,
            )
            return
        self._status.set(f"Discovering {self._device_section.get().casefold()} devices...")
        self.root.update_idletasks()
        try:
            devices = GenerationDeviceCatalog(session.emtp_object).discover()
        except Exception as exc:
            self._status.set("Devices could not be discovered.")
            messagebox.showerror(self._device_discovery_label.get(), str(exc), parent=self.root)
            return

        self._generation_devices = {}
        self._generation_capacities = {}
        summary_reader = GenerationSummaryReader()
        allowed_kinds = (
            {
                GenerationKind.PHOTOVOLTAIC,
                GenerationKind.WIND,
                GenerationKind.DER,
                GenerationKind.SYNCHRONOUS,
            }
            if self._device_scope == "generation"
            else {GenerationKind.BESS}
        )
        for index, device in enumerate(devices):
            if device.kind not in allowed_kinds:
                continue
            item_id = f"generation-device-{index}"
            self._generation_devices[item_id] = device
            summary = summary_reader.read(device)
            self._generation_capacities[item_id] = (
                self._format_capacity(summary.capacity_mva)
                if summary.capacity_mva is not None
                else ""
            )
        zones = sorted({device.zone for device in self._generation_devices.values()})
        self.generation_zone_selector.configure(values=("All Zones", *zones))
        if self._generation_zone_filter.get() not in {"All Zones", *zones}:
            self._generation_zone_filter.set("All Zones")
        self._render_generation_devices()
        self._device_detail.set(
            f"Select a {self._device_section.get().casefold()} object to inspect its device chain."
            if self._generation_devices
            else f"No {self._device_section.get().casefold()} templates were recognized in this design."
        )
        self._status.set(
            f"{len(self._generation_devices)} {self._device_section.get().casefold()} device chain(s) discovered."
        )
        self.auto_fit_generation_columns()

    def _on_generation_filter_change(self, _event: object | None = None) -> None:
        self._render_generation_devices()

    def _render_generation_devices(self) -> None:
        for item_id in self.device_tree.get_children():
            self.device_tree.delete(item_id)
        self.inspect_pv_parameters_button.state(("disabled",))
        zone_filter = self._generation_zone_filter.get()
        object_filter = self._generation_object_filter.get().casefold().strip()
        matching_items = [
            (item_id, device)
            for item_id, device in self._generation_devices.items()
            if (zone_filter == "All Zones" or device.zone == zone_filter)
            and (not object_filter or object_filter in device.template_name.casefold())
        ]
        matching_items.sort(
            key=lambda item: self._generation_sort_key(
                item[0], item[1], self._generation_sort_column
            ),
            reverse=self._generation_sort_reverse,
        )
        for index, (item_id, device) in enumerate(matching_items):
            self.device_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    device.template_name,
                    device.internal_model_name,
                    device.kind.value,
                    self._generation_capacities.get(item_id, ""),
                    "",
                    "",
                    device.zone,
                ),
                tags=("even" if index % 2 == 0 else "odd",),
            )
        self._queue_generation_grid_lines()

    @staticmethod
    def _format_capacity(value: float) -> str:
        return f"{value:,.2f}"

    def _generation_sort_key(
        self, item_id: str, device: GenerationDevice, column: str
    ) -> tuple[int, float | str]:
        values = {
            "technology": device.kind.value,
            "object": device.template_name,
            "unit_object": device.internal_model_name,
            "capacity": self._generation_capacities.get(item_id, ""),
            "inertia_h": "",
            "inertia_gvas": "",
            "zone": device.zone,
        }
        value = values[column]
        if column == "capacity":
            try:
                return (0, float(value.replace(",", "")))
            except ValueError:
                return (1, value.casefold())
        return (0, value.casefold())

    def _sort_generation_devices(self, column: str) -> None:
        if self._generation_sort_column == column:
            self._generation_sort_reverse = not self._generation_sort_reverse
        else:
            self._generation_sort_column = column
            self._generation_sort_reverse = False
        self._render_generation_devices()

    def auto_fit_generation_columns(self) -> None:
        """Fit Generation columns to the currently visible device chains."""
        measurement_font = tkfont.Font(family="Segoe UI", size=9)
        for column in self.device_tree["columns"]:
            widest = measurement_font.measure(
                str(self.device_tree.heading(column, "text"))
            )
            for item_id in self.device_tree.get_children():
                values = self.device_tree.item(item_id, "values")
                column_index = self.device_tree["columns"].index(column)
                widest = max(widest, measurement_font.measure(str(values[column_index])))
            self.device_tree.column(column, width=min(max(widest + 28, 90), 300))
        self._queue_generation_grid_lines()

    def _queue_generation_grid_lines(self, _event: object | None = None) -> None:
        if self._generation_grid_refresh_pending:
            return
        self._generation_grid_refresh_pending = True
        self.device_tree.after_idle(self._refresh_generation_grid_lines)

    def _refresh_generation_grid_lines(self) -> None:
        self._generation_grid_refresh_pending = False
        for line in self._generation_grid_lines:
            line.destroy()
        self._generation_grid_lines = []
        if not self.device_tree.winfo_ismapped():
            return
        width = self.device_tree.winfo_width()
        height = self.device_tree.winfo_height()
        if width <= 1 or height <= 1:
            return
        position = 0
        for column in self.device_tree["columns"][:-1]:
            position += int(self.device_tree.column(column, "width"))
            line = ttk.Separator(
                self.device_tree, orient="vertical", style="DeviceGrid.TSeparator"
            )
            line.place(x=position - 1, y=0, height=height)
            self._generation_grid_lines.append(line)
        for item_id in self.device_tree.get_children():
            bounding_box = self.device_tree.bbox(item_id, "#1")
            if not bounding_box:
                continue
            _x, y, _row_width, row_height = bounding_box
            line = ttk.Separator(
                self.device_tree, orient="horizontal", style="DeviceGrid.TSeparator"
            )
            line.place(x=0, y=y + row_height - 1, width=width)
            self._generation_grid_lines.append(line)

    def _on_generation_device_select(self, _event: object) -> None:
        selected = self.device_tree.selection()
        device = self._generation_devices.get(selected[0]) if selected else None
        if device is None:
            self.inspect_pv_parameters_button.state(("disabled",))
            return
        self.inspect_pv_parameters_button.state(
            ("!disabled",)
            if device.kind
            in {
                GenerationKind.PHOTOVOLTAIC,
                GenerationKind.BESS,
                GenerationKind.SYNCHRONOUS,
            }
            else ("disabled",)
        )
        capacity = self._generation_capacities.get(selected[0], "")
        capacity_detail = (
            f"Capacity: {capacity} MVA" if capacity else "Capacity: Not Available"
        )
        self._device_detail.set(
            f"Technology: {device.kind.value}\n"
            f"Zone (Object): {device.zone or 'Not Set'}\n"
            f"{capacity_detail}\n"
            f"Object: {device.template_name} ({device.template_lib_type})\n"
            f"Unit Object: {device.internal_model_name} ({device.internal_model_lib_type})\n"
            f"Chain: {device.internal_model_path}\n"
            "Current scope: discovery only. Parameters will be read from Unit Object."
        )

    def inspect_device_parameters(self) -> None:
        selected = self.device_tree.selection()
        device = self._generation_devices.get(selected[0]) if selected else None
        if device is None:
            messagebox.showinfo(
                "Inspect Parameters",
                "Select a supported device first.",
                parent=self.root,
            )
            return
        readers = {
            GenerationKind.PHOTOVOLTAIC: PhotovoltaicParameterReader,
            GenerationKind.BESS: BessParameterReader,
            GenerationKind.SYNCHRONOUS: SynchronousParameterReader,
        }
        reader_type = readers.get(device.kind)
        if reader_type is None:
            messagebox.showinfo(
                "Inspect Parameters",
                f"{device.kind.value} does not have a parameter adapter yet.",
                parent=self.root,
            )
            return
        try:
            parameter_set = reader_type().read(device)
        except FormDataFormatError as exc:
            messagebox.showerror("Inspect Parameters", str(exc), parent=self.root)
            return
        except Exception as exc:
            messagebox.showerror("Inspect Parameters", str(exc), parent=self.root)
            return
        self._show_device_parameter_dialog(device, parameter_set)

    def _show_device_parameter_dialog(self, device: GenerationDevice, parameter_set: Any) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(f"{device.kind.value} Parameters - {device.internal_model_name}")
        dialog.configure(background=COLORS["background"])
        dialog.transient(self.root)
        dialog.geometry("940x690")
        dialog.minsize(760, 540)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(4, weight=1)

        ttk.Label(dialog, text=f"{device.kind.value} Parameters", style="Title.TLabel").grid(
            row=0, column=0, padx=22, pady=(20, 0), sticky="w"
        )
        ttk.Label(
            dialog,
            text=(
                f"Unit Object: {device.internal_model_name}  |  "
                f"{len(parameter_set.all_parameters)} parameters  |  Read Only"
            ),
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, padx=22, pady=(4, 16), sticky="w")

        summary = ttk.Frame(dialog, style="Surface.TFrame", padding=12)
        summary.grid(row=2, column=0, padx=22, sticky="ew")
        summary.columnconfigure(0, weight=1)
        ttk.Label(summary, text="Summary Parameters", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        summary_text = "  •  ".join(
            f"{parameter.key}: {parameter.value}"
            for parameter in parameter_set.summary_parameters
        ) or "No configured summary parameters were found in FormData."
        ttk.Label(
            summary,
            text=summary_text,
            style="CardText.TLabel",
            justify="left",
            wraplength=850,
        ).grid(row=1, column=0, pady=(7, 0), sticky="w")

        toolbar = ttk.Frame(dialog, style="App.TFrame")
        toolbar.grid(row=3, column=0, padx=22, pady=(16, 8), sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        ttk.Label(toolbar, text="Search", style="Subtitle.TLabel").grid(
            row=0, column=0, padx=(0, 8), sticky="w"
        )
        search_value = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=search_value, width=36)
        search_entry.grid(row=0, column=1, sticky="w")

        table = ttk.Treeview(
            dialog,
            columns=("parameter", "value", "source", "access"),
            show="headings",
        )
        for column, heading, width in (
            ("parameter", "Parameter", 290),
            ("value", "Value", 300),
            ("source", "Source", 130),
            ("access", "Access", 130),
        ):
            table.heading(column, text=heading)
            table.column(column, width=width, anchor="w")
        table.grid(row=4, column=0, padx=22, pady=(0, 14), sticky="nsew")
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=table.yview)
        scrollbar.grid(row=4, column=1, pady=(0, 14), sticky="ns")
        table.configure(yscrollcommand=scrollbar.set)
        table.tag_configure("even", background="#f8fafb")
        table.tag_configure("odd", background="#eef3f6")

        def render_parameters(*_args: object) -> None:
            for item_id in table.get_children():
                table.delete(item_id)
            needle = search_value.get().casefold().strip()
            matching = [
                parameter
                for parameter in parameter_set.all_parameters
                if not needle
                or needle in parameter.key.casefold()
                or needle in parameter.value.casefold()
            ]
            for index, parameter in enumerate(matching):
                table.insert(
                    "",
                    "end",
                    values=(
                        parameter.key,
                        parameter.value,
                        getattr(parameter, "source", "FormData"),
                        "Read Only",
                    ),
                    tags=("even" if index % 2 == 0 else "odd",),
                )

        search_value.trace_add("write", render_parameters)
        render_parameters()
        ttk.Button(
            dialog, text="Close", style="Action.TButton", command=dialog.destroy
        ).grid(row=5, column=0, padx=22, pady=(0, 18), sticky="e")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.update_idletasks()
        dialog.lift()
        dialog.focus_force()
        search_entry.focus_set()

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
                column = parameter_columns[parameter]
                row[column] = (
                    self._format_bus_type(value) if column == "bus_type" else value
                )
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
        self.auto_fit_scenario_columns()
        self._scenario_detail.set(
            "Select an object to inspect its XMLDataGrids scenario source."
            if records
            else "No recognized settable generation values were found in this design."
        )
        self._status.set(f"{len(records)} scenario object(s) loaded for {project.name}.")

    def _on_scenario_filter_change(self, _event: object | None = None) -> None:
        self._render_scenario_rows()

    @staticmethod
    def _format_bus_type(value: str) -> str:
        return {"1": "PQ (1)", "2": "PV (2)", "3": "Slack (3)"}.get(
            str(value).strip(), str(value)
        )

    def _sort_scenario_rows(self, column: str) -> None:
        if self._scenario_sort_column == column:
            self._scenario_sort_reverse = not self._scenario_sort_reverse
        else:
            self._scenario_sort_column = column
            self._scenario_sort_reverse = False
        self._render_scenario_rows()

    def auto_fit_scenario_columns(self) -> None:
        """Fit columns to loaded values while retaining an engineering-friendly cap."""
        measurement_font = tkfont.Font(family="Segoe UI", size=9)
        for column in self.scenario_tree["columns"]:
            widest = measurement_font.measure(
                str(self.scenario_tree.heading(column, "text"))
            )
            for row in self._scenario_rows.values():
                widest = max(widest, measurement_font.measure(str(row[column])))
            self.scenario_tree.column(column, width=min(max(widest + 28, 80), 280))
        self._queue_scenario_grid_lines()

    def _queue_scenario_grid_lines(self, _event: object | None = None) -> None:
        if self._scenario_grid_refresh_pending:
            return
        self._scenario_grid_refresh_pending = True
        self.scenario_tree.after_idle(self._refresh_scenario_grid_lines)

    def _refresh_scenario_grid_lines(self) -> None:
        self._scenario_grid_refresh_pending = False
        for line in self._scenario_grid_lines:
            line.destroy()
        self._scenario_grid_lines = []
        if not self.scenario_tree.winfo_ismapped():
            return
        width = self.scenario_tree.winfo_width()
        height = self.scenario_tree.winfo_height()
        if width <= 1 or height <= 1:
            return

        position = 0
        for column in self.scenario_tree["columns"][:-1]:
            position += int(self.scenario_tree.column(column, "width"))
            line = ttk.Separator(
                self.scenario_tree, orient="vertical", style="ScenarioGrid.TSeparator"
            )
            line.place(x=position - 1, y=0, height=height)
            self._scenario_grid_lines.append(line)
        for item_id in self.scenario_tree.get_children():
            bounding_box = self.scenario_tree.bbox(item_id, "#1")
            if not bounding_box:
                continue
            _x, y, _row_width, row_height = bounding_box
            line = ttk.Separator(
                self.scenario_tree, orient="horizontal", style="ScenarioGrid.TSeparator"
            )
            line.place(x=0, y=y + row_height - 1, width=width)
            self._scenario_grid_lines.append(line)

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
        self._queue_scenario_grid_lines()

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

    @staticmethod
    def _scenario_cell_is_editable(row: dict[str, Any], column: str) -> bool:
        editable_columns = {
            "zone",
            "status",
            "active_power",
            "reactive_power",
            "voltage_setpoint",
            "bus_type",
        }
        if column not in editable_columns:
            return False
        return not (
            column in {"voltage_setpoint", "bus_type"}
            and row["technology"] != "Synchronous"
        )

    def _select_scenario_cell(self, event: tk.Event[tk.Misc]) -> None:
        item_id = self.scenario_tree.identify_row(event.y)
        tree_column = self.scenario_tree.identify_column(event.x)
        if not item_id or not tree_column:
            self._scenario_active_cell = None
            return
        column_id = str(self.scenario_tree.column(tree_column, "id"))
        self._scenario_active_cell = (item_id, column_id)

    def _copy_scenario_cell(self, _event: object | None = None) -> str:
        if self._scenario_active_cell is None:
            self._status.set("Select a scenario cell before copying.")
            return "break"
        item_id, column = self._scenario_active_cell
        row = self._scenario_rows.get(item_id)
        if row is None:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(str(row[column]))
        self._status.set(f"Copied {column.replace('_', ' ')} to clipboard.")
        return "break"

    def _stage_scenario_value(self, item_id: str, column: str, value: str) -> bool:
        row = self._scenario_rows.get(item_id)
        if row is None or not self._scenario_cell_is_editable(row, column):
            return False
        value = value.strip()
        if value == row["original"][column]:
            self._scenario_drafts.get(item_id, {}).pop(column, None)
        else:
            self._scenario_drafts.setdefault(item_id, {})[column] = value
        if item_id in self._scenario_drafts and not self._scenario_drafts[item_id]:
            del self._scenario_drafts[item_id]
        row[column] = value
        return True

    def _paste_scenario_cells(self, _event: object | None = None) -> str:
        if self._scenario_active_cell is None:
            self._status.set("Select the destination scenario cell before pasting.")
            return "break"
        try:
            clipboard_text = self.root.clipboard_get()
        except tk.TclError:
            self._status.set("Clipboard does not contain text to paste.")
            return "break"
        clipboard_rows = clipboard_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if clipboard_rows and clipboard_rows[-1] == "":
            clipboard_rows.pop()
        matrix = [line.split("\t") for line in clipboard_rows]
        if not matrix:
            return "break"

        start_item_id, start_column = self._scenario_active_cell
        visible_item_ids = list(self.scenario_tree.get_children())
        columns = list(self.scenario_tree["columns"])
        try:
            start_row_index = visible_item_ids.index(start_item_id)
            start_column_index = columns.index(start_column)
        except ValueError:
            self._status.set("The destination cell is no longer visible.")
            return "break"

        staged_count = 0
        if len(matrix) == 1 and len(matrix[0]) == 1 and len(self.scenario_tree.selection()) > 1:
            for item_id in self.scenario_tree.selection():
                staged_count += self._stage_scenario_value(item_id, start_column, matrix[0][0])
        else:
            for row_offset, values in enumerate(matrix):
                destination_row_index = start_row_index + row_offset
                if destination_row_index >= len(visible_item_ids):
                    break
                for column_offset, value in enumerate(values):
                    destination_column_index = start_column_index + column_offset
                    if destination_column_index >= len(columns):
                        break
                    staged_count += self._stage_scenario_value(
                        visible_item_ids[destination_row_index],
                        columns[destination_column_index],
                        value,
                    )
        if staged_count:
            self._set_scenario_draft_state()
            self._render_scenario_rows()
            self._status.set(
                f"Pasted {staged_count} editable scenario value(s) into the draft."
            )
        else:
            self._status.set("No editable scenario cells were available for the pasted values.")
        return "break"

    def _edit_scenario_cell(self, event: tk.Event[tk.Misc]) -> None:
        item_id = self.scenario_tree.identify_row(event.y)
        column = self.scenario_tree.identify_column(event.x)
        if not item_id or not column:
            return
        column_id = str(self.scenario_tree.column(column, "id"))
        row = self._scenario_rows.get(item_id)
        if row is None or not self._scenario_cell_is_editable(row, column_id):
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
                values=("PQ (1)", "PV (2)", "Slack (3)"),
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
            self._stage_scenario_value(item_id, column_id, new_value)
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
        self._status.set(
            f"Scenario changes applied to {len(changes)} object(s). Save Working Design to persist them."
        )
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

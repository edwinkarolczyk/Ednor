# Plik: gui_cutting.py
# Wersja: 0.9.0
from __future__ import annotations

import csv
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Dict, List, Optional

from core.cutting_models import CutItem
from core.cutting_optimizer import optimize_cutting
from core.cutting_reports import generate_cutting_report_html
from core.cutting_storage import (
    accept_cutting_calculation,
    add_remnant,
    add_stock_bar,
    get_cutting_debug_paths,
    list_cutting_calculations,
    load_cutting_calculation,
    load_cutting_settings,
    load_materials,
    material_label,
    load_stock_bars,
    save_cutting_calculation,
    save_cut_result,
    save_cut_job,
    log_stock_move,
    update_cutting_setting,
    upsert_material,
)
from core.cutting_units import (
    clamp_saw_angle,
    format_mm,
    parse_length_to_mm,
    validate_saw_angle,
)

APP_NAME = "Ednor"
APP_SUBTITLE = "www.ednor.pl Program i firma dla Ciebie"

STRATEGY_LABELS = {
    "balanced": "Warsztatowy balans",
    "min_waste": "Minimalny odpad",
    "min_bars": "Najmniej sztang",
    "min_cuts": "Najmniej cięć",
}

STRATEGY_BY_LABEL = {label: key for key, label in STRATEGY_LABELS.items()}


def strategy_label_to_key(value: str) -> str:
    value = str(value or "").strip()
    if value in STRATEGY_BY_LABEL:
        return STRATEGY_BY_LABEL[value]
    if value in STRATEGY_LABELS:
        return value
    return "balanced"


MAT_COLUMNS = ("display",)
CUT_COLUMNS = ("material", "length", "angle_l", "angle_r", "qty", "label")
RESULT_COLUMNS = ("bar", "source", "cuts", "waste", "usage")
CALC_COLUMNS = ("id", "created", "status", "job", "bars", "usage")

DARK_BG = "#08080A"
PANEL_BG = "#121217"
PANEL_2 = "#191920"
RED = "#B11226"
RED_HOT = "#E3263A"
TEXT = "#F2F2F2"
MUTED = "#A7A7A7"
GRID = "#303038"
GREEN = "#37B36B"
YELLOW = "#E0B84D"


def _fmt_num(value: Any) -> str:
    try:
        f = float(value)
        return f"{f:g}"
    except Exception:
        return str(value)


def _cut_mark(angle: float, side: str) -> str:
    """Tekstowy symbol kąta.

    0     -> |
    +45   -> /
    -45   -> \\
    """
    try:
        angle = float(angle)
    except Exception:
        angle = 0.0

    if abs(angle) < 0.001:
        return "|"
    if angle > 0:
        return "/"
    return "\\"


def _cut_text(length: Any, angle_l: Any, angle_r: Any) -> str:
    return (
        f"{_cut_mark(float(angle_l or 0), 'L')}"
        f"{format_mm(float(length or 0))}"
        f"{_cut_mark(float(angle_r or 0), 'R')}"
    )


def _apply_cutting_theme(root: tk.Misc) -> None:
    """Lokalny ciemny motyw dla modułu rozkroju.

    Nie miesza w globalnym ui_theme WM. To jest bezpieczniejsze na tym etapie.
    """
    try:
        root.configure(bg=DARK_BG)
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure("Cut.TFrame", background=DARK_BG)
    style.configure("Cut.Panel.TFrame", background=PANEL_BG)
    style.configure("Cut.TLabel", background=DARK_BG, foreground=TEXT, font=("Segoe UI", 10))
    style.configure("Cut.Title.TLabel", background=DARK_BG, foreground=RED_HOT, font=("Segoe UI", 18, "bold"))
    style.configure("Cut.Subtitle.TLabel", background=PANEL_BG, foreground=TEXT, font=("Segoe UI", 12, "bold"))
    style.configure("Cut.Muted.TLabel", background=DARK_BG, foreground=MUTED, font=("Segoe UI", 9))
    style.configure("Cut.TButton", background=PANEL_2, foreground=TEXT, padding=(10, 6), borderwidth=1)
    style.map(
        "Cut.TButton",
        background=[("active", RED), ("pressed", RED_HOT)],
        foreground=[("active", TEXT), ("pressed", TEXT)],
    )
    style.configure("Cut.Red.TButton", background=RED, foreground=TEXT, padding=(12, 7), borderwidth=1)
    style.map(
        "Cut.Red.TButton",
        background=[("active", RED_HOT), ("pressed", "#ff4055")],
        foreground=[("active", TEXT), ("pressed", TEXT)],
    )
    style.configure(
        "Cut.Treeview",
        background="#0D0D11",
        fieldbackground="#0D0D11",
        foreground=TEXT,
        rowheight=30,
        bordercolor=GRID,
        lightcolor=GRID,
        darkcolor=GRID,
        font=("Segoe UI", 10),
    )
    style.configure(
        "Cut.Treeview.Heading",
        background=RED,
        foreground=TEXT,
        font=("Segoe UI", 10, "bold"),
        padding=(6, 6),
    )
    style.map(
        "Cut.Treeview",
        background=[("selected", RED)],
        foreground=[("selected", TEXT)],
    )
    style.configure(
        "Cut.TEntry",
        fieldbackground="#0D0D11",
        foreground=TEXT,
        insertcolor=TEXT,
        bordercolor=GRID,
    )


class CuttingFrame(ttk.Frame):
    """Panel rozkroju profili/sztang/prętów.

    Wersja 0.2:
    - czarno-czerwony motyw lokalny,
    - pełniejszy, czytelniejszy układ,
    - graficzny podgląd sztang i kątów,
    - większe kontrolki pod warsztat.
    """

    def __init__(self, master, config: Optional[Dict[str, Any]] = None):
        _apply_cutting_theme(master.winfo_toplevel())
        super().__init__(master, padding=(12, 12, 12, 12), style="Cut.TFrame")
        self.config_obj = config or {}
        self._last_result = None
        self._last_result_dict: Optional[Dict[str, Any]] = None
        self._materials: List[Dict[str, Any]] = []
        self._material_labels: Dict[str, str] = {}
        self._settings: Dict[str, Any] = load_cutting_settings()
        self.var_tablet = tk.BooleanVar(value=False)
        self._build_ui()
        self._refresh_materials()
        self._refresh_calculations()
        self._refresh_stock_info()

    def _build_ui(self) -> None:
        header = ttk.Frame(self, style="Cut.TFrame")
        header.pack(fill="x", pady=(0, 10))

        title_box = ttk.Frame(header, style="Cut.TFrame")
        title_box.pack(side="left", padx=(0, 18))
        ttk.Label(title_box, text=f"{APP_NAME.upper()} — {APP_SUBTITLE}", style="Cut.Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Rozkrój / cięcie", style="Cut.Muted.TLabel").pack(anchor="w")

        ttk.Label(header, text="Zlecenie:", style="Cut.TLabel").pack(side="left")
        self.var_job = tk.StringVar(value="ROZKROJ-TEST")
        ttk.Entry(header, textvariable=self.var_job, width=24, style="Cut.TEntry").pack(side="left", padx=(5, 14))

        ttk.Label(header, text="Rzaz [mm]:", style="Cut.TLabel").pack(side="left")
        self.var_kerf = tk.StringVar(value="2.5")
        ttk.Entry(header, textvariable=self.var_kerf, width=8, style="Cut.TEntry").pack(side="left", padx=(5, 14))

        ttk.Label(header, text="Min. odpad [mm]:", style="Cut.TLabel").pack(side="left")
        self.var_min_offcut = tk.StringVar(value="300")
        ttk.Entry(header, textvariable=self.var_min_offcut, width=9, style="Cut.TEntry").pack(side="left", padx=(5, 14))

        ttk.Label(header, text="Strategia:", style="Cut.TLabel").pack(side="left")
        self.var_strategy = tk.StringVar(value=STRATEGY_LABELS["balanced"])
        self.cbo_strategy = ttk.Combobox(
            header,
            textvariable=self.var_strategy,
            values=list(STRATEGY_LABELS.values()),
            width=22,
            state="readonly",
        )
        self.cbo_strategy.pack(side="left", padx=(5, 14))

        ttk.Checkbutton(
            header,
            text="Tryb tablet",
            variable=self.var_tablet,
            command=self._apply_tablet_mode,
        ).pack(side="left", padx=(0, 12))

        ttk.Button(header, text="Ścieżki", command=self._show_paths, style="Cut.TButton").pack(side="right")

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main, padding=(0, 0, 10, 0), style="Cut.TFrame")
        right = ttk.Frame(main, padding=(10, 0, 0, 0), style="Cut.TFrame")
        main.add(left, weight=2)
        main.add(right, weight=3)

        self._build_materials(left)
        self._build_cut_list(left)
        self._build_calculations(left)
        self._build_result_and_preview(right)
        self._build_footer()

    def _panel_title(self, parent, text: str) -> None:
        box = ttk.Frame(parent, style="Cut.Panel.TFrame")
        box.pack(fill="x", pady=(0, 6))
        ttk.Label(box, text=text, style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)

    def _build_materials(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Baza surowców", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)
        ttk.Button(top, text="+ Surowiec", command=self._add_material_dialog, style="Cut.Red.TButton").pack(side="right", padx=(6, 8))
        ttk.Button(top, text="+ DODAJ STAN", command=self._add_stock_dialog, style="Cut.TButton").pack(side="right", padx=(6, 6))
        ttk.Button(top, text="+ DODAJ ODPAD", command=self._add_remnant_dialog, style="Cut.TButton").pack(side="right", padx=(6, 6))
        ttk.Button(top, text="Edytuj", command=self._edit_selected_material, style="Cut.TButton").pack(side="right")

        self.tree_materials = ttk.Treeview(
            parent,
            columns=MAT_COLUMNS,
            show="headings",
            selectmode="browse",
            height=6,
            style="Cut.Treeview",
        )
        self.tree_materials.pack(fill="x", expand=False, pady=(0, 10))
        self.tree_materials.heading("display", text="Surowiec")
        self.tree_materials.column("display", width=380, anchor="w")
        self.tree_materials.bind("<Double-1>", lambda _e: self._edit_selected_material())

    def _refresh_materials(self) -> None:
        self._materials = [m for m in load_materials() if m.get("aktywny", True)]
        self._material_labels = {material_label(m): m["material_id"] for m in self._materials}
        if hasattr(self, "tree_materials"):
            for iid in self.tree_materials.get_children():
                self.tree_materials.delete(iid)
            for m in self._materials:
                name = str(m.get("display_name") or m.get("nazwa") or "")
                stock_mb = float(m.get("stock_mb", 0) or 0)
                label = f"{name} (stan {stock_mb:g} mb)"
                self.tree_materials.insert(
                    "",
                    "end",
                    iid=m.get("material_id"),
                    values=(label,),
                )


    def _add_stock_dialog(self):
        sel = self.tree_materials.selection()
        if not sel:
            messagebox.showwarning("Magazyn", "Wybierz surowiec")
            return

        material_id = sel[0]

        val = simpledialog.askstring(
            "Dodaj stan",
            "Podaj długość (np. 12000mm lub 12m):",
        )
        if not val:
            return

        try:
            mm = parse_length_to_mm(val)
            add_stock_bar(material_id, "bar", mm, 1)
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
            return

        self._refresh_materials()

    def _add_remnant_dialog(self):
        sel = self.tree_materials.selection()
        if not sel:
            messagebox.showwarning("Magazyn", "Wybierz surowiec")
            return

        material_id = sel[0]

        val = simpledialog.askstring(
            "Dodaj odpad",
            "Podaj długość odpadu (np. 1200mm):",
        )
        if not val:
            return

        try:
            mm = parse_length_to_mm(val)
            add_remnant(material_id, mm, 1)
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
            return

        self._refresh_materials()

    def _build_cut_list(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Lista do cięcia", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)

        ttk.Button(top, text="+ DODAJ ELEMENT DO CIĘCIA", command=self._add_cut_row_dialog, style="Cut.Red.TButton").pack(side="right", padx=(6, 8))
        ttk.Button(top, text="Edytuj", command=self._edit_selected_cut, style="Cut.TButton").pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Duplikuj", command=self._duplicate_selected_cut, style="Cut.TButton").pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Usuń", command=self._delete_selected_cut, style="Cut.TButton").pack(side="right")

        tools = ttk.Frame(parent, style="Cut.TFrame")
        tools.pack(fill="x", pady=(0, 6))
        ttk.Button(tools, text="Import CSV", command=self._import_cuts_csv, style="Cut.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(tools, text="Eksport CSV", command=self._export_cuts_csv, style="Cut.TButton").pack(side="left", padx=(0, 6))
        ttk.Label(
            tools,
            text="CSV kolumny: material_id,length_mm,angle_left,angle_right,qty,label",
            style="Cut.Muted.TLabel",
        ).pack(side="left", padx=(8, 0))

        self.tree_cuts = ttk.Treeview(
            parent,
            columns=CUT_COLUMNS,
            show="headings",
            selectmode="browse",
            height=14,
            style="Cut.Treeview",
        )
        self.tree_cuts.pack(fill="both", expand=False)

        labels = {
            "material": "Materiał ID",
            "length": "Długość",
            "angle_l": "Kąt L",
            "angle_r": "Kąt P",
            "qty": "Ilość",
            "label": "Opis",
        }
        widths = {
            "material": 170,
            "length": 85,
            "angle_l": 70,
            "angle_r": 70,
            "qty": 55,
            "label": 180,
        }
        for col in CUT_COLUMNS:
            self.tree_cuts.heading(col, text=labels[col])
            self.tree_cuts.column(col, width=widths[col], anchor="w")

        helper = tk.Text(
            parent,
            height=7,
            bg=PANEL_BG,
            fg=MUTED,
            insertbackground=TEXT,
            relief="flat",
            wrap="word",
            font=("Consolas", 10),
        )
        helper.pack(fill="x", pady=(10, 0))
        helper.insert(
            "1.0",
            "Legenda kątów:\n"
            "  |1500 mm (1.5 m)|  = cięcie proste 0° / 0°\n"
            "  /1500 mm (1.5 m)\\  = 45° / -45° — ukos jak romb/trapez\n\n"
            "Na tym etapie długość = wymiar do odmierzenia na pile.\n"
            "Piła: zakres -60° do 60°. Znak kąta oznacza stronę ukosu.",
        )
        helper.configure(state="disabled")

        self.tree_cuts.bind("<Double-1>", lambda _e: self._edit_selected_cut())

    def _build_result_and_preview(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(0, 6))

        ttk.Label(top, text="Wynik + podgląd sztang", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)

        ttk.Button(top, text="OBLICZ", command=self._calculate, style="Cut.Red.TButton").pack(side="right", padx=(6, 8))
        ttk.Button(top, text="Zapisz wynik", command=self._save_last_result, style="Cut.TButton").pack(side="right")

        self.tree_result = ttk.Treeview(
            parent,
            columns=RESULT_COLUMNS,
            show="headings",
            selectmode="browse",
            height=8,
            style="Cut.Treeview",
        )
        self.tree_result.pack(fill="x", expand=False)

        labels = {
            "bar": "Sztanga",
            "source": "Źródło",
            "cuts": "Cięcia tekstowo",
            "waste": "Odpad",
            "usage": "Użycie",
        }
        widths = {
            "bar": 180,
            "source": 85,
            "cuts": 520,
            "waste": 100,
            "usage": 80,
        }
        for col in RESULT_COLUMNS:
            self.tree_result.heading(col, text=labels[col])
            self.tree_result.column(col, width=widths[col], anchor="w")
        self.tree_result.tag_configure("usage_good", foreground=GREEN)
        self.tree_result.tag_configure("usage_mid", foreground=YELLOW)
        self.tree_result.tag_configure("usage_bad", foreground=RED_HOT)

        preview_box = ttk.Frame(parent, style="Cut.Panel.TFrame")
        preview_box.pack(fill="both", expand=True, pady=(10, 0))

        ttk.Label(preview_box, text="Graficzny podgląd cięcia", style="Cut.Subtitle.TLabel").pack(anchor="w", padx=10, pady=(8, 0))

        self.canvas = tk.Canvas(
            preview_box,
            bg="#09090C",
            highlightthickness=1,
            highlightbackground=GRID,
            height=300,
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        self.txt_summary = tk.Text(
            parent,
            height=7,
            bg="#0D0D11",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            wrap="word",
            font=("Consolas", 10),
        )
        self.txt_summary.pack(fill="x", pady=(10, 0))

    def _build_calculations(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(10, 6))
        ttk.Label(top, text="Lista kalkulacji cięcia", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)
        ttk.Button(top, text="Odśwież", command=self._refresh_calculations, style="Cut.TButton").pack(side="right", padx=(6, 8))
        ttk.Button(top, text="Wczytaj", command=self._load_selected_calculation, style="Cut.TButton").pack(side="right")

        self.tree_calculations = ttk.Treeview(
            parent,
            columns=CALC_COLUMNS,
            show="headings",
            selectmode="browse",
            height=6,
            style="Cut.Treeview",
        )
        self.tree_calculations.pack(fill="x", expand=False)
        labels = {
            "id": "ID",
            "created": "Data",
            "status": "Status",
            "job": "Zlecenie",
            "bars": "Szt.",
            "usage": "%",
        }
        widths = {
            "id": 130,
            "created": 125,
            "status": 80,
            "job": 120,
            "bars": 45,
            "usage": 50,
        }
        for col in CALC_COLUMNS:
            self.tree_calculations.heading(col, text=labels[col])
            self.tree_calculations.column(col, width=widths[col], anchor="w")
        self.tree_calculations.bind("<Double-1>", lambda _e: self._load_selected_calculation())

    def _refresh_calculations(self) -> None:
        if not hasattr(self, "tree_calculations"):
            return
        for iid in self.tree_calculations.get_children():
            self.tree_calculations.delete(iid)
        for row in list_cutting_calculations():
            self.tree_calculations.insert(
                "",
                "end",
                values=(
                    row.get("calculation_id", ""),
                    row.get("created_at", ""),
                    row.get("status", ""),
                    row.get("job_id", ""),
                    row.get("bars_count", 0),
                    row.get("usage_percent", 0),
                ),
            )

    def _build_footer(self) -> None:
        footer = ttk.Frame(self, style="Cut.TFrame")
        footer.pack(fill="x", pady=(10, 0))

        self.var_stock_info = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.var_stock_info, style="Cut.TLabel").pack(side="left")

        ttk.Button(
            footer,
            text="Akceptuj kalkulację / zdejmij stan",
            command=self._accept_last_result,
            style="Cut.Red.TButton",
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            footer,
            text="Etykiety CSV",
            command=self._export_labels_csv,
            style="Cut.TButton",
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            footer,
            text="Raport HTML",
            command=self._export_html_report,
            style="Cut.TButton",
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            footer,
            text="Eksport CNC CSV",
            command=self._export_cnc_csv,
            style="Cut.TButton",
        ).pack(side="right", padx=(6, 0))

        ttk.Button(
            footer,
            text="Dodaj sztangę do stock_bars",
            command=self._add_stock_bar_dialog,
            style="Cut.Red.TButton",
        ).pack(side="right")

        ttk.Button(
            footer,
            text="Odśwież stan",
            command=self._refresh_stock_info,
            style="Cut.TButton",
        ).pack(side="right", padx=(0, 6))

    def _insert_cut_row(
        self,
        material_id: str,
        length_mm: float,
        angle_left: float,
        angle_right: float,
        qty: int,
        label: str,
    ) -> None:
        self.tree_cuts.insert(
            "",
            "end",
            values=(
                material_id,
                format_mm(float(length_mm)),
                f"{clamp_saw_angle(float(angle_left)):g}",
                f"{clamp_saw_angle(float(angle_right)):g}",
                str(int(qty)),
                label,
            ),
        )
        if material_id:
            self._remember_last_material(material_id)

    def _remember_last_material(self, material_id: str) -> None:
        material_id = str(material_id or "").strip()
        if not material_id:
            return
        self._settings["last_material_id"] = material_id
        update_cutting_setting("last_material_id", material_id)

    def _apply_tablet_mode(self) -> None:
        style = ttk.Style(self.winfo_toplevel())
        if self.var_tablet.get():
            style.configure("Cut.Treeview", rowheight=42, font=("Segoe UI", 14))
            style.configure("Cut.Treeview.Heading", font=("Segoe UI", 13, "bold"), padding=(8, 8))
            style.configure("Cut.TButton", font=("Segoe UI", 13), padding=(14, 9))
            style.configure("Cut.Red.TButton", font=("Segoe UI", 13, "bold"), padding=(16, 10))
            style.configure("Cut.TLabel", font=("Segoe UI", 12))
        else:
            style.configure("Cut.Treeview", rowheight=30, font=("Segoe UI", 10))
            style.configure("Cut.Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=(6, 6))
            style.configure("Cut.TButton", font=("Segoe UI", 10), padding=(10, 6))
            style.configure("Cut.Red.TButton", font=("Segoe UI", 10, "bold"), padding=(12, 7))
            style.configure("Cut.TLabel", font=("Segoe UI", 10))

    def _selected_material_id(self) -> str:
        sel = getattr(self, "tree_materials", None).selection() if hasattr(self, "tree_materials") else []
        if sel:
            values = self.tree_materials.item(sel[0], "values")
            return str(values[0]).strip()
        last_mid = str(self._settings.get("last_material_id", "")).strip()
        if last_mid:
            return last_mid
        return self._materials[0]["material_id"] if self._materials else ""

    def _get_material_row(self, material_id: str) -> Optional[Dict[str, Any]]:
        for row in self._materials:
            if str(row.get("material_id", "")).strip() == material_id:
                return row
        return None

    def _add_material_dialog(self) -> None:
        dialog = _MaterialDialog(self)
        self.wait_window(dialog.win)
        if dialog.result:
            upsert_material(dialog.result)
            self._refresh_materials()

    def _edit_selected_material(self) -> None:
        material_id = self._selected_material_id()
        row = self._get_material_row(material_id)
        if not row:
            return
        dialog = _MaterialDialog(self, row)
        self.wait_window(dialog.win)
        if dialog.result:
            upsert_material(dialog.result)
            self._refresh_materials()

    def _read_cut_items(self) -> List[CutItem]:
        items: List[CutItem] = []
        for iid in self.tree_cuts.get_children():
            values = self.tree_cuts.item(iid, "values")
            try:
                items.append(
                    CutItem(
                        material_id=str(values[0]).strip(),
                        length_mm=parse_length_to_mm(str(values[1])),
                        angle_left=validate_saw_angle(float(str(values[2]).replace(",", "."))),
                        angle_right=validate_saw_angle(float(str(values[3]).replace(",", "."))),
                        qty=int(values[4]),
                        label=str(values[5]).strip(),
                    )
                )
            except Exception:
                continue
        return items

    def _validate_angles_or_warn(self, items: List[CutItem]) -> bool:
        for item in items:
            validate_saw_angle(item.angle_left)
            validate_saw_angle(item.angle_right)
        return True

    def _calculate(self) -> None:
        items = self._read_cut_items()
        if not items:
            messagebox.showwarning("Rozkrój", "Brak poprawnych pozycji do cięcia.")
            return

        try:
            self._validate_angles_or_warn(items)
        except Exception as exc:
            messagebox.showerror("Rozkrój", f"{exc}\n\nPiła obsługuje tylko kąty -60° do 60°.")
            return

        stock = load_stock_bars()
        if not stock:
            messagebox.showwarning(
                "Rozkrój",
                "Brak sztang/odpadów w data/magazyn/stock_bars.json.\n"
                "Dodaj sztangę przyciskiem na dole.",
            )
            return

        try:
            saw_kerf = float(self.var_kerf.get().replace(",", "."))
            min_offcut = float(self.var_min_offcut.get().replace(",", "."))
        except Exception:
            messagebox.showerror("Rozkrój", "Rzaz i minimalny odpad muszą być liczbami.")
            return

        strategy_key = strategy_label_to_key(self.var_strategy.get())
        result = optimize_cutting(
            job_id=self.var_job.get().strip() or "ROZKROJ",
            items=items,
            stock_bars=stock,
            saw_kerf_mm=saw_kerf,
            min_reusable_offcut_mm=min_offcut,
            strategy=strategy_key,
        )
        self._last_result = result
        self._last_result_dict = result.to_dict()
        self._render_result(self._last_result_dict)
        calc_id = self.var_job.get().strip() or f"KALK-{int(__import__('time').time())}"
        self._last_result_dict["status"] = "draft"
        self._last_result_dict["calculation_id"] = calc_id

        payload = {
            "job_id": self.var_job.get().strip() or "ROZKROJ",
            "saw_kerf_mm": saw_kerf,
            "min_reusable_offcut_mm": min_offcut,
            "strategy": strategy_key,
            "items": [item.to_dict() for item in items],
        }
        try:
            save_cut_job(payload["job_id"], payload)
            save_cutting_calculation(payload["job_id"], payload, self._last_result_dict)
            self._refresh_calculations()
        except Exception:
            pass

    def _render_result(self, data: Dict[str, Any]) -> None:
        for iid in self.tree_result.get_children():
            self.tree_result.delete(iid)

        def _usage_tag(value: float) -> str:
            if value >= 85:
                return "usage_good"
            if value >= 70:
                return "usage_mid"
            return "usage_bad"

        for idx, bar in enumerate(data.get("bars_used", []), start=1):
            cuts_txt = self._bar_cuts_text(bar)
            used = float(bar.get("used_mm", 0) or 0)
            length = float(bar.get("bar_length_mm", 0) or 0)
            usage_val = (used / length * 100) if length else 0.0
            usage = f"{usage_val:.1f}%" if length else "-"
            self.tree_result.insert(
                "",
                "end",
                values=(
                    f'{idx}. {bar.get("material_id", "")} / {format_mm(length)}',
                    bar.get("source", ""),
                    cuts_txt,
                    format_mm(float(bar.get("waste_mm", 0) or 0)),
                    usage,
                ),
                tags=(_usage_tag(usage_val),),
            )

        self._draw_preview(data)
        self._render_summary(data)

    def _bar_cuts_text(self, bar: Dict[str, Any]) -> str:
        cuts = bar.get("cuts", [])
        chunks = []
        for cut in cuts:
            chunks.append(
                _cut_text(
                    cut.get("length_mm", 0),
                    cut.get("angle_left", 0),
                    cut.get("angle_right", 0),
                )
            )
        waste = float(bar.get("waste_mm", 0) or 0)
        if waste > 0:
            chunks.append(f"odpad {format_mm(waste)}")
        return " -- ".join(chunks)

    def _render_summary(self, data: Dict[str, Any]) -> None:
        summary = data.get("summary", {})
        missing = data.get("missing", [])
        strategy = strategy_label_to_key(str(data.get("strategy") or self.var_strategy.get() or "balanced"))
        strategy_txt = STRATEGY_LABELS.get(strategy, strategy)
        lines = [
            "PODSUMOWANIE",
            "------------",
            f"Strategia:            {strategy_txt}",
            f"Sztang użytych:       {summary.get('bars_count', 0)}",
            f"Materiał łącznie:     {format_mm(float(summary.get('total_length_mm', 0) or 0))}",
            f"Zużycie:              {format_mm(float(summary.get('total_used_mm', 0) or 0))}",
            f"Odpad:                {format_mm(float(summary.get('total_waste_mm', 0) or 0))}",
            f"Wykorzystanie:        {summary.get('usage_percent', 0)}%",
        ]
        if missing:
            lines.append("")
            lines.append("BRAKI")
            lines.append("-----")
            for row in missing:
                lines.append(
                    f"- {row.get('material_id')} / {format_mm(float(row.get('length_mm', 0) or 0))} / {row.get('label', '')}"
                )

        self.txt_summary.configure(state="normal")
        self.txt_summary.delete("1.0", "end")
        self.txt_summary.insert("1.0", "\n".join(lines))
        self.txt_summary.configure(state="disabled")

    def _draw_preview(self, data: Dict[str, Any]) -> None:
        self.canvas.delete("all")
        bars = data.get("bars_used", [])

        width = max(800, self.canvas.winfo_width())
        row_h = 72
        left = 130
        right = 30
        top = 32
        usable_w = max(300, width - left - right)

        if not bars:
            self.canvas.create_text(
                20,
                20,
                text="Brak wyniku. Kliknij OBLICZ.",
                anchor="nw",
                fill=MUTED,
                font=("Segoe UI", 12),
            )
            return

        needed_height = top + len(bars) * row_h + 40
        self.canvas.configure(scrollregion=(0, 0, width, needed_height), height=min(360, needed_height))

        for idx, bar in enumerate(bars, start=1):
            y = top + (idx - 1) * row_h
            bar_len = float(bar.get("bar_length_mm", 0) or 0)
            if bar_len <= 0:
                continue

            x0 = left
            x1 = left + usable_w
            bar_y0 = y + 18
            bar_y1 = y + 42

            label = f'{idx}. {bar.get("material_id", "")} / {format_mm(bar_len)}'
            self.canvas.create_text(10, y + 24, text=label, anchor="w", fill=TEXT, font=("Segoe UI", 9, "bold"))

            self.canvas.create_rectangle(x0, bar_y0, x1, bar_y1, fill="#1A1A22", outline=GRID)

            cursor = x0
            cuts = bar.get("cuts", [])
            kerf = float(data.get("saw_kerf_mm", 0) or 0)

            for cut_idx, cut in enumerate(cuts):
                length = float(cut.get("length_mm", 0) or 0)
                seg_w = max(4, usable_w * length / bar_len)
                seg_x0 = cursor
                seg_x1 = min(x1, seg_x0 + seg_w)
                if seg_x1 <= seg_x0:
                    continue

                # Minimalna przerwa wizualna, żeby segmenty się nie zlewały/nakładały.
                draw_x0 = seg_x0 + 1
                draw_x1 = seg_x1 - 1
                if draw_x1 <= draw_x0:
                    draw_x0 = seg_x0
                    draw_x1 = seg_x1

                self.canvas.create_rectangle(draw_x0, bar_y0, draw_x1, bar_y1, fill="#2A1016", outline=RED)
                self._draw_angle_mark(draw_x0, bar_y0, bar_y1, float(cut.get("angle_left", 0) or 0), left_side=True)
                self._draw_angle_mark(draw_x1, bar_y0, bar_y1, float(cut.get("angle_right", 0) or 0), left_side=False)

                text = _cut_text(length, cut.get("angle_left", 0), cut.get("angle_right", 0))
                if seg_w > 75:
                    self.canvas.create_text(
                        (draw_x0 + draw_x1) / 2,
                        bar_y0 - 8,
                        text=text,
                        fill=TEXT,
                        font=("Consolas", 8, "bold"),
                    )

                # Rzaz jako czerwona kreska między detalami.
                cursor = seg_x1
                if cut_idx < len(cuts) - 1 and kerf > 0:
                    kerf_w = max(1, usable_w * kerf / bar_len)
                    kerf_x0 = cursor
                    kerf_x1 = min(x1, cursor + kerf_w)
                    self.canvas.create_rectangle(
                        kerf_x0,
                        bar_y0 - 3,
                        kerf_x1,
                        bar_y1 + 3,
                        fill=RED_HOT,
                        outline=RED_HOT,
                    )
                    cursor += kerf_w

            waste = float(bar.get("waste_mm", 0) or 0)
            if waste > 0:
                waste_x0 = max(cursor, x0)
                self.canvas.create_rectangle(waste_x0, bar_y0, x1, bar_y1, fill="#202026", outline=GRID)
                if x1 - waste_x0 > 55:
                    self.canvas.create_text(
                        (waste_x0 + x1) / 2,
                        bar_y1 + 13,
                        text=f"odpad {format_mm(waste)}",
                        fill=YELLOW,
                        font=("Segoe UI", 8),
                    )

            usage = float(bar.get("used_mm", 0) or 0) / bar_len * 100 if bar_len else 0
            self.canvas.create_text(
                x1,
                y + 5,
                text=f"{usage:.1f}%",
                anchor="e",
                fill=GREEN if usage >= 80 else YELLOW,
                font=("Segoe UI", 9, "bold"),
            )

    def _draw_angle_mark(self, x: float, y0: float, y1: float, angle: float, left_side: bool) -> None:
        """Rysuje symbol cięcia na końcu segmentu.

        0° jako pionowa kreska.
        Kąt 1–60° jako ukośnik.
        """
        angle = clamp_saw_angle(float(angle or 0))
        if abs(angle) < 0.001:
            self.canvas.create_line(x, y0 - 4, x, y1 + 4, fill=TEXT, width=2)
            return

        if angle > 0:
            self.canvas.create_line(x - 8, y1 + 5, x + 8, y0 - 5, fill=RED_HOT, width=3)
        else:
            self.canvas.create_line(x - 8, y0 - 5, x + 8, y1 + 5, fill=RED_HOT, width=3)
        self.canvas.create_text(
            x,
            y0 - 13,
            text=f"{angle:g}°",
            fill=RED_HOT,
            font=("Segoe UI", 7, "bold"),
        )

    def _save_last_result(self) -> None:
        if self._last_result is None:
            messagebox.showwarning("Rozkrój", "Najpierw kliknij OBLICZ.")
            return
        data = self._last_result.to_dict()
        try:
            path = save_cut_result(data.get("job_id", "ROZKROJ"), data)
        except Exception as exc:
            messagebox.showerror("Rozkrój", f"Nie udało się zapisać wyniku:\n{exc}")
            return
        messagebox.showinfo("Rozkrój", f"Zapisano wynik:\n{path}")

    def _refresh_stock_info(self) -> None:
        stock = load_stock_bars()
        by_mat: Dict[str, int] = {}
        by_len: Dict[str, List[str]] = {}
        for bar in stock:
            by_mat[bar.material_id] = by_mat.get(bar.material_id, 0) + int(bar.qty)
            by_len.setdefault(bar.material_id, []).append(f"{format_mm(bar.length_mm)} x{bar.qty}")

        if not by_mat:
            self.var_stock_info.set("Brak danych stock_bars.json — dodaj pierwszą sztangę.")
            return

        chunks = []
        for mat in sorted(by_mat):
            chunks.append(f"{mat}: {', '.join(by_len.get(mat, []))}")
        self.var_stock_info.set("STAN: " + " | ".join(chunks))

    def _delete_selected_cut(self) -> None:
        sel = self.tree_cuts.selection()
        if not sel:
            return
        self.tree_cuts.delete(sel[0])

    def _duplicate_selected_cut(self) -> None:
        sel = self.tree_cuts.selection()
        if not sel:
            messagebox.showinfo("Rozkrój", "Zaznacz pozycję do zduplikowania.")
            return
        values = list(self.tree_cuts.item(sel[0], "values"))
        if not values:
            return
        self.tree_cuts.insert("", "end", values=values)
        self._remember_last_material(str(values[0]))

    def _cut_rows_for_csv(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for iid in self.tree_cuts.get_children():
            values = self.tree_cuts.item(iid, "values")
            if not values:
                continue
            try:
                rows.append(
                    {
                        "material_id": str(values[0]).strip(),
                        "length_mm": f"{parse_length_to_mm(str(values[1])):g}",
                        "angle_left": str(values[2]),
                        "angle_right": str(values[3]),
                        "qty": str(values[4]),
                        "label": str(values[5]) if len(values) > 5 else "",
                    }
                )
            except Exception:
                continue
        return rows

    def _import_cuts_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Import listy cięć CSV",
            filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")],
        )
        if not path:
            return
        imported = 0
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    material_id = str(row.get("material_id") or row.get("material") or "").strip()
                    length_raw = row.get("length_mm") or row.get("length") or row.get("dlugosc") or ""
                    angle_l = row.get("angle_left") or row.get("angle_l") or row.get("kat_l") or 0
                    angle_r = row.get("angle_right") or row.get("angle_r") or row.get("kat_p") or 0
                    qty = row.get("qty") or row.get("ilosc") or 1
                    label = row.get("label") or row.get("opis") or ""
                    length_mm = parse_length_to_mm(str(length_raw))
                    a_l = validate_saw_angle(float(str(angle_l).replace(",", ".")))
                    a_r = validate_saw_angle(float(str(angle_r).replace(",", ".")))
                    self._insert_cut_row(material_id, length_mm, a_l, a_r, int(qty), str(label))
                    imported += 1
        except Exception as exc:
            messagebox.showerror("Import CSV", f"Nie udało się zaimportować CSV:\n{exc}")
            return
        messagebox.showinfo("Import CSV", f"Zaimportowano pozycji: {imported}")

    def _export_cuts_csv(self) -> None:
        rows = self._cut_rows_for_csv()
        if not rows:
            messagebox.showinfo("Eksport CSV", "Brak pozycji do eksportu.")
            return
        path = filedialog.asksaveasfilename(
            title="Eksport listy cięć CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["material_id", "length_mm", "angle_left", "angle_right", "qty", "label"],
                )
                writer.writeheader()
                writer.writerows(rows)
        except Exception as exc:
            messagebox.showerror("Eksport CSV", f"Nie udało się zapisać CSV:\n{exc}")
            return
        messagebox.showinfo("Eksport CSV", f"Zapisano:\n{path}")


    def _export_cnc_csv(self) -> None:
        if not self._last_result_dict:
            messagebox.showwarning("Eksport CNC CSV", "Najpierw oblicz albo wczytaj kalkulację.")
            return

        path = filedialog.asksaveasfilename(
            title="Eksport CNC CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["job_id","bar_no","material_id","bar_source","bar_length_mm","length_mm","angle_left","angle_right","qty","label"])
                for bar_no, bar in enumerate(self._last_result_dict.get("bars_used", []), start=1):
                    for cut in bar.get("cuts", []):
                        writer.writerow([self.var_job.get(),bar_no,bar.get("material_id", ""),bar.get("source", ""),bar.get("bar_length_mm", ""),cut.get("length_mm", ""),float(cut.get("angle_left", 0) or 0),float(cut.get("angle_right", 0) or 0),1,cut.get("label", "")])
        except Exception as exc:
            messagebox.showerror("Eksport CNC CSV", f"Nie udało się zapisać CNC CSV:\n{exc}")
            return

        messagebox.showinfo("Eksport CNC CSV", f"Zapisano:\n{path}")

    def _edit_selected_cut(self) -> None:
        sel = self.tree_cuts.selection()
        if not sel:
            return
        values = self.tree_cuts.item(sel[0], "values")
        data = {
            "material_id": values[0],
            "length_mm": parse_length_to_mm(str(values[1])),
            "angle_left": values[2],
            "angle_right": values[3],
            "qty": values[4],
            "label": values[5],
        }
        dialog = _CutRowDialog(self, data)
        self.wait_window(dialog.win)
        if dialog.result:
            self.tree_cuts.item(
                sel[0],
                values=(
                    dialog.result["material_id"],
                    format_mm(dialog.result["length_mm"]),
                    f'{dialog.result["angle_left"]:g}',
                    f'{dialog.result["angle_right"]:g}',
                    str(int(dialog.result["qty"])),
                    dialog.result["label"],
                ),
            )
            self._remember_last_material(dialog.result["material_id"])

    def _add_cut_row_dialog(self) -> None:
        dialog = _CutRowDialog(self, {"material_id": self._selected_material_id()})
        self.wait_window(dialog.win)
        if dialog.result:
            self._insert_cut_row(**dialog.result)

    def _add_stock_bar_dialog(self) -> None:
        dialog = _StockBarDialog(self)
        self.wait_window(dialog.win)
        if not dialog.result:
            return
        try:
            add_stock_bar(**dialog.result)
        except Exception as exc:
            messagebox.showerror("Rozkrój", f"Nie udało się dodać sztangi:\n{exc}")
            return
        self._refresh_stock_info()
        self._refresh_materials()

    def _accept_last_result(self) -> None:
        if not self._last_result_dict:
            messagebox.showwarning("Rozkrój", "Najpierw oblicz albo wczytaj kalkulację.")
            return
        if self._last_result_dict.get("accepted_at"):
            messagebox.showinfo("Rozkrój", "Ta kalkulacja jest już zaakceptowana.")
            return
        job_id = self._last_result_dict.get("calculation_id") or self._last_result_dict.get("job_id") or self.var_job.get()
        if not messagebox.askyesno(
            "Akceptuj kalkulację",
            "Zaakceptować kalkulację i zmniejszyć stan surowców w magazynie?\n\n"
            "Tej operacji na razie nie cofamy automatycznie.",
        ):
            return
        try:
            accept_cutting_calculation(job_id, self._last_result_dict)
        except Exception as exc:
            messagebox.showerror("Rozkrój", f"Nie udało się zaakceptować kalkulacji:\n{exc}")
            return
        min_offcut = float(self.var_min_offcut.get())
        for bar in self._last_result_dict.get("bars_used", []):
            if not isinstance(bar, dict):
                continue
            waste = float(bar.get("waste_mm", 0) or 0)
            material = str(bar.get("material_id", "")).strip()
            if not material or waste <= 0:
                continue
            if waste >= min_offcut:
                add_remnant(material, waste)
            else:
                log_stock_move(
                    {
                        "type": "scrap",
                        "material_id": material,
                        "length_mm": waste,
                    }
                )
        messagebox.showinfo("Rozkrój", "Zaktualizowano magazyn + odpady.")
        self._refresh_stock_info()
        self._refresh_materials()
        self._refresh_calculations()

    def _export_labels_csv(self) -> None:
        if not self._last_result_dict:
            messagebox.showwarning("Etykiety CSV", "Najpierw oblicz albo wczytaj kalkulację.")
            return

        path = filedialog.asksaveasfilename(
            title="Eksport etykiet CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["job", "material", "length_mm", "angle_left", "angle_right", "label"])
                for bar in self._last_result_dict.get("bars_used", []):
                    for cut in bar.get("cuts", []):
                        writer.writerow(
                            [
                                self.var_job.get(),
                                bar.get("material_id", ""),
                                cut.get("length_mm", ""),
                                cut.get("angle_left", ""),
                                cut.get("angle_right", ""),
                                cut.get("label", ""),
                            ]
                        )
        except Exception as exc:
            messagebox.showerror("Etykiety CSV", f"Nie udało się zapisać etykiet:\n{exc}")
            return

        messagebox.showinfo("Etykiety CSV", f"Zapisano:\n{path}")

    def _export_html_report(self) -> None:
        if not self._last_result_dict:
            messagebox.showwarning("Raport HTML", "Najpierw oblicz albo wczytaj kalkulację.")
            return

        path = filedialog.asksaveasfilename(
            title="Eksport raportu HTML",
            defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("Wszystkie pliki", "*.*")],
        )
        if not path:
            return

        try:
            html = generate_cutting_report_html(self._last_result_dict)
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as exc:
            messagebox.showerror("Raport HTML", f"Nie udało się zapisać raportu:\n{exc}")
            return

        messagebox.showinfo("Raport HTML", f"Zapisano:\n{path}")

    def _load_selected_calculation(self) -> None:
        sel = self.tree_calculations.selection()
        if not sel:
            return
        values = self.tree_calculations.item(sel[0], "values")
        calc_id = str(values[0]).strip()
        data = load_cutting_calculation(calc_id)
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        job = data.get("job") if isinstance(data.get("job"), dict) else {}
        if not result:
            return
        self.var_job.set(str(job.get("job_id") or result.get("job_id") or calc_id))
        if result.get("strategy"):
            key = strategy_label_to_key(str(result.get("strategy")))
            self.var_strategy.set(STRATEGY_LABELS.get(key, key))
        self._last_result_dict = result
        self._render_result(result)

    def _show_paths(self) -> None:
        paths = get_cutting_debug_paths()
        messagebox.showinfo(
            "Ścieżki rozkroju",
            "\n".join([f"{key}: {value}" for key, value in paths.items()]),
        )


class _MaterialDialog:
    def __init__(self, parent, row: Optional[Dict[str, Any]] = None):
        row = row or {}
        self.result = None
        self.win = tk.Toplevel(parent)
        self.win.title("Surowiec")
        self.win.transient(parent.winfo_toplevel())
        self.win.grab_set()
        _apply_cutting_theme(self.win)

        self.v_id = tk.StringVar(value=str(row.get("material_id", "")))
        self.v_typ = tk.StringVar(value=str(row.get("typ", "profil")))
        self.v_nazwa = tk.StringVar(value=str(row.get("nazwa", "")))
        self.v_rozmiar = tk.StringVar(value=str(row.get("rozmiar", "")))
        self.v_len = tk.StringVar(value=format_mm(float(row.get("domyslna_dlugosc_mm", 6000) or 6000)))
        self.v_active = tk.BooleanVar(value=bool(row.get("aktywny", True)))
        self.v_uwagi = tk.StringVar(value=str(row.get("uwagi", "")))

        fields = [
            ("ID, np. profil_40x30x2", self.v_id),
            ("Typ, np. profil/rura/pret/plaskownik", self.v_typ),
            ("Nazwa", self.v_nazwa),
            ("Rozmiar, np. 40x30x2 albo fi 30", self.v_rozmiar),
            ("Długość sztangi [mm/cm/m]", self.v_len),
            ("Uwagi", self.v_uwagi),
        ]
        for i, (label, var) in enumerate(fields):
            ttk.Label(self.win, text=label, style="Cut.TLabel").grid(row=i, column=0, padx=10, pady=6, sticky="w")
            ttk.Entry(self.win, textvariable=var, width=36, style="Cut.TEntry").grid(row=i, column=1, padx=10, pady=6, sticky="ew")
        ttk.Checkbutton(self.win, text="Aktywny", variable=self.v_active).grid(row=len(fields), column=1, sticky="w", padx=10)
        btns = ttk.Frame(self.win, style="Cut.TFrame")
        btns.grid(row=len(fields) + 1, column=0, columnspan=2, pady=(10, 10))
        ttk.Button(btns, text="OK", command=self._ok, style="Cut.Red.TButton").pack(side="left", padx=5)
        ttk.Button(btns, text="Anuluj", command=self.win.destroy, style="Cut.TButton").pack(side="left", padx=5)

    def _ok(self) -> None:
        try:
            self.result = {
                "material_id": self.v_id.get().strip(),
                "typ": self.v_typ.get().strip(),
                "nazwa": self.v_nazwa.get().strip(),
                "rozmiar": self.v_rozmiar.get().strip(),
                "domyslna_dlugosc_mm": parse_length_to_mm(self.v_len.get()),
                "aktywny": bool(self.v_active.get()),
                "uwagi": self.v_uwagi.get().strip(),
            }
        except Exception:
            messagebox.showerror("Surowiec", "Sprawdź dane surowca.")
            return
        self.win.destroy()


class _CutRowDialog:
    def __init__(self, parent, row: Optional[Dict[str, Any]] = None):
        row = row or {}
        self.result = None
        self.win = tk.Toplevel(parent)
        self.win.title("Dodaj pozycję cięcia")
        self.win.transient(parent.winfo_toplevel())
        self.win.grab_set()
        _apply_cutting_theme(self.win)

        self.parent = parent
        self.v_material = tk.StringVar(value=str(row.get("material_id", parent._selected_material_id() if hasattr(parent, "_selected_material_id") else "")))
        self.v_length = tk.StringVar(value=format_mm(float(row.get("length_mm", 1500) or 1500)))
        self.v_angle_l = tk.StringVar(value=str(row.get("angle_left", "45")))
        self.v_angle_r = tk.StringVar(value=str(row.get("angle_right", "-45")))
        self.v_qty = tk.StringVar(value=str(row.get("qty", "1")))
        self.v_label = tk.StringVar(value=str(row.get("label", "")))

        material_values = []
        if hasattr(parent, "_materials"):
            material_values = [material_label(m) for m in parent._materials]
        self._label_to_id = {material_label(m): m["material_id"] for m in getattr(parent, "_materials", [])}

        ttk.Label(self.win, text="Materiał", style="Cut.TLabel").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.cbo_material = ttk.Combobox(self.win, textvariable=self.v_material, values=material_values, width=42)
        self.cbo_material.grid(row=0, column=1, padx=10, pady=6, sticky="ew")
        for label, mid in self._label_to_id.items():
            if mid == self.v_material.get():
                self.v_material.set(label)
                break

        fields = [
            ("Długość [mm/cm/m]", self.v_length),
            ("Kąt L [-60 do 60°]", self.v_angle_l),
            ("Kąt P [-60 do 60°]", self.v_angle_r),
            ("Ilość", self.v_qty),
            ("Opis", self.v_label),
        ]
        for idx, (label, var) in enumerate(fields, start=1):
            ttk.Label(self.win, text=label, style="Cut.TLabel").grid(row=idx, column=0, padx=10, pady=6, sticky="w")
            ttk.Entry(self.win, textvariable=var, width=30, style="Cut.TEntry").grid(row=idx, column=1, padx=10, pady=6, sticky="ew")

        btns = ttk.Frame(self.win, style="Cut.TFrame")
        btns.grid(row=len(fields) + 1, column=0, columnspan=2, pady=(10, 10))
        ttk.Button(btns, text="OK", command=self._ok, style="Cut.Red.TButton").pack(side="left", padx=5)
        ttk.Button(btns, text="Anuluj", command=self.win.destroy, style="Cut.TButton").pack(side="left", padx=5)

    def _ok(self) -> None:
        try:
            material = self.v_material.get().strip()
            material = self._label_to_id.get(material, material)
            self.result = {
                "material_id": material,
                "length_mm": parse_length_to_mm(self.v_length.get()),
                "angle_left": validate_saw_angle(float(self.v_angle_l.get().replace(",", "."))),
                "angle_right": validate_saw_angle(float(self.v_angle_r.get().replace(",", "."))),
                "qty": int(self.v_qty.get()),
                "label": self.v_label.get().strip(),
            }
        except Exception:
            messagebox.showerror("Rozkrój", "Sprawdź liczby w formularzu.")
            return
        self.win.destroy()


class _StockBarDialog:
    def __init__(self, parent):
        self.result = None
        self.win = tk.Toplevel(parent)
        self.win.title("Dodaj sztangę")
        self.win.transient(parent.winfo_toplevel())
        self.win.grab_set()
        _apply_cutting_theme(self.win)

        self.v_material = tk.StringVar(value="profil_40x40x2")
        self.v_name = tk.StringVar(value="Profil 40x40x2")
        self.v_length = tk.StringVar(value="6000mm")
        self.v_qty = tk.StringVar(value="1")
        self.v_location = tk.StringVar(value="")

        fields = [
            ("Materiał ID", self.v_material),
            ("Nazwa", self.v_name),
            ("Długość sztangi [mm/cm/m]", self.v_length),
            ("Ilość", self.v_qty),
            ("Lokalizacja", self.v_location),
        ]
        for row, (label, var) in enumerate(fields):
            ttk.Label(self.win, text=label, style="Cut.TLabel").grid(row=row, column=0, padx=10, pady=6, sticky="w")
            ttk.Entry(self.win, textvariable=var, width=32, style="Cut.TEntry").grid(row=row, column=1, padx=10, pady=6, sticky="ew")

        btns = ttk.Frame(self.win, style="Cut.TFrame")
        btns.grid(row=len(fields), column=0, columnspan=2, pady=(10, 10))
        ttk.Button(btns, text="OK", command=self._ok, style="Cut.Red.TButton").pack(side="left", padx=5)
        ttk.Button(btns, text="Anuluj", command=self.win.destroy, style="Cut.TButton").pack(side="left", padx=5)

    def _ok(self) -> None:
        try:
            self.result = {
                "material_id": self.v_material.get().strip(),
                "name": self.v_name.get().strip(),
                "length_mm": parse_length_to_mm(self.v_length.get()),
                "qty": int(self.v_qty.get()),
                "location": self.v_location.get().strip(),
            }
        except Exception:
            messagebox.showerror("Rozkrój", "Sprawdź liczby w formularzu.")
            return
        self.win.destroy()


class CuttingWindow:
    def __init__(self, master, config: Optional[Dict[str, Any]] = None):
        self.win = tk.Toplevel(master)
        self.win.title(f"{APP_NAME} — Rozkrój / cięcie")
        self.win.geometry("1400x850")
        self.win.minsize(1100, 700)
        _apply_cutting_theme(self.win)

        try:
            self.win.state("zoomed")
        except Exception:
            try:
                self.win.attributes("-zoomed", True)
            except Exception:
                pass

        frame = CuttingFrame(self.win, config=config or {})
        frame.pack(fill="both", expand=True)
        self.win.transient(master)


def open_window(parent, config=None, *args, **kwargs):
    return CuttingWindow(parent, config=config or {})


def open_panel_cutting(parent, root=None, app=None, notebook=None, *args, **kwargs):
    """Publiczne API podobne do innych modułów WM."""
    cfg = kwargs.get("config")
    if not isinstance(cfg, dict):
        maybe = getattr(parent, "config", None)
        cfg = maybe if isinstance(maybe, dict) else {}

    container = kwargs.get("container") or notebook
    if container is None:
        for name in ("content", "main_frame", "body", "container"):
            maybe = getattr(parent, name, None)
            if maybe is not None:
                container = maybe
                break
    if container is None:
        container = parent

    try:
        if hasattr(container, "add") and hasattr(container, "tabs"):
            frame = CuttingFrame(container, config=cfg)
            container.add(frame, text=f"{APP_NAME} — Rozkrój")
            container.select(frame)
            return frame
    except Exception:
        pass

    old = getattr(parent, "_cutting_embed", None)
    if isinstance(old, tk.Widget) and old.winfo_exists():
        try:
            old.destroy()
        except Exception:
            pass

    frame = CuttingFrame(container, config=cfg)
    frame.pack(fill="both", expand=True)
    parent._cutting_embed = frame
    return frame


if __name__ == "__main__":
    root = tk.Tk()
    root.title(f"{APP_NAME} — Rozkrój / cięcie")
    root.geometry("1400x850")
    _apply_cutting_theme(root)
    try:
        root.state("zoomed")
    except Exception:
        pass
    frame = CuttingFrame(root)
    frame.pack(fill="both", expand=True)
    root.mainloop()

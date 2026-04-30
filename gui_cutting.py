# Plik: gui_cutting.py
# Wersja: 1.1.1 - skalowanie okien i zakładek
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
    load_cutting_stock_raw,
    load_stock_bars,
    save_cutting_calculation,
    save_cut_result,
    save_cut_job,
    log_stock_move,
    update_cutting_setting,
    upsert_material,
    deactivate_material,
    build_material_display_name,
    material_size_from_dims,
    save_transport,
    next_transport_id,
    load_transports_raw,
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
STOCK_COLUMNS = ("kind", "material", "length", "qty", "total_mb", "price", "value", "transport", "location")
TRANSPORT_COLUMNS = ("id", "created", "supplier", "lines", "mb", "net", "gross", "cost")
TRANSPORT_LINE_COLUMNS = ("material", "length", "qty", "mb", "price", "value")
NEEDS_COLUMNS = ("material", "need", "stock", "missing", "suggestion")

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

DEFAULT_KERF_MM = 2.5
DEFAULT_MIN_OFFCUT_MM = 300
DEFAULT_STRATEGY = "balanced"
DEFAULT_JOB_ID = "ROZKROJ"
DEFAULT_CUT_LENGTH_MM = 1500
DEFAULT_CUT_ANGLE_LEFT = 0
DEFAULT_CUT_ANGLE_RIGHT = 0
DEFAULT_CUT_QTY = 1
DEFAULT_WINDOW_GEOMETRY = "1280x820"
DEFAULT_WINDOW_MINSIZE = (1100, 700)
DEFAULT_DIALOG_MINSIZE = (520, 360)
DEFAULT_TRANSPORT_DIALOG_GEOMETRY = "980x680"
DEFAULT_MATERIAL_DIALOG_GEOMETRY = "620x520"


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


def _operator_cut_shape(angle_l: Any, angle_r: Any) -> str:
    """Zwraca prosty symbol ukosu dla operatora.

    Przykłady:
      0 / 0      -> |---|
      45 / -45   -> /---\
      -45 / 45   -> \\---/
      45 / 45    -> /---/
    """

    return f"{_cut_mark(float(angle_l or 0), 'L')}---{_cut_mark(float(angle_r or 0), 'R')}"


def _machine_angle_value(angle: Any) -> float:
    """Kąt technologiczny do porównywania i przyszłego CNC.

    Teraz operator czyta go z karty i ustawia ręcznie.
    Później ta sama wartość może iść do eksportu maszyny.
    """

    try:
        return round(float(angle or 0), 3)
    except Exception:
        return 0.0


def _angles_compatible(a: Any, b: Any, tolerance: float = 0.001) -> bool:
    """Czy dwa sąsiednie kąty mogą tworzyć jedno wspólne cięcie."""

    return abs(_machine_angle_value(a) - _machine_angle_value(b)) <= tolerance


def _flip_cut_for_operator(cut: Dict[str, Any]) -> Dict[str, Any]:
    """Odwraca detal na potrzeby mapy operatora.

    Nie zmienia danych źródłowych optymalizacji. To jest tylko wariant
    ułożenia na mapie/kolejności cięcia.
    """

    out = dict(cut)
    out["angle_left"], out["angle_right"] = cut.get("angle_right", 0), cut.get("angle_left", 0)
    out["_operator_flipped"] = not bool(cut.get("_operator_flipped", False))
    return out


def _pick_orientation_for_previous(prev_right_angle: Any, cut: Dict[str, Any]) -> Dict[str, Any]:
    """Dobiera orientację detalu, żeby wspólny kąt pasował do poprzedniego.

    Preferencja:
    1. zostaw jak jest, jeśli lewy kąt pasuje do prawego kąta poprzedniego,
    2. odwróć detal, jeśli wtedy pasuje,
    3. zostaw jak jest i mapa pokaże `!!!`.
    """

    if prev_right_angle is None:
        return dict(cut)

    normal = dict(cut)
    if _angles_compatible(prev_right_angle, normal.get("angle_left", 0)):
        return normal

    flipped = _flip_cut_for_operator(cut)
    if _angles_compatible(prev_right_angle, flipped.get("angle_left", 0)):
        return flipped

    return normal


def _operator_piece_shape_for_map(cut: Dict[str, Any]) -> str:
    """Skrócony symbol detalu na mapie całej sztangi."""

    left = _cut_mark(_machine_angle_value(cut.get("angle_left", 0)), "L")
    right = _cut_mark(_machine_angle_value(cut.get("angle_right", 0)), "R")
    try:
        length = float(cut.get("length_mm", 0) or 0)
    except Exception:
        length = 0

    # Prosty kompromis: dłuższy detal dostaje więcej kresek, ale bez robienia tasiemca.
    dash_count = max(3, min(10, int(round(length / 500.0)) if length else 4))
    return f"{left}{'-' * dash_count}{right}"


def _operator_join_token(left_angle: Any, right_angle: Any) -> str:
    """Łącznik między sąsiednimi detalami.

    Zgodne kąty = jedno wspólne cięcie.
    Niezgodne kąty = ostrzeżenie technologiczne, nie udajemy normalnego `/\\`.
    """

    if _angles_compatible(left_angle, right_angle):
        mark = _cut_mark(_machine_angle_value(left_angle), "R")
        if mark == "\\":
            return " \\\\ "
        if mark == "/":
            return " // "
        return " || "
    return " !!! "


def _operator_bar_map_text(bar: Dict[str, Any]) -> tuple[str, List[str], List[Dict[str, Any]]]:
    """Buduje technologiczną mapę całej sztangi.

    Zwraca:
    - tekst mapy,
    - ostrzeżenia,
    - listę detali w orientacji pokazanej na mapie
    """

    cuts = [dict(c) for c in (bar.get("cuts", []) or []) if isinstance(c, dict)]
    if not cuts:
        return "| ODPAD |", [], []

    oriented: List[Dict[str, Any]] = []
    warnings: List[str] = []
    prev_right = None
    for idx, cut in enumerate(cuts, start=1):
        chosen = _pick_orientation_for_previous(prev_right, cut)
        if prev_right is not None and not _angles_compatible(prev_right, chosen.get("angle_left", 0)):
            warnings.append(
                f"Detal {idx - 1} → {idx}: niezgodne kąty "
                f"{_machine_angle_value(prev_right):g}° / {_machine_angle_value(chosen.get('angle_left', 0)):g}°"
            )
        oriented.append(chosen)
        prev_right = chosen.get("angle_right", 0)

    parts: List[str] = ["| "]
    for idx, cut in enumerate(oriented):
        if idx > 0:
            previous = oriented[idx - 1]
            parts.append(_operator_join_token(previous.get("angle_right", 0), cut.get("angle_left", 0)))
        parts.append(_operator_piece_shape_for_map(cut))

    waste = float(bar.get("waste_mm", 0) or 0)
    if waste > 0:
        parts.append(f" | ODPAD {format_mm(waste)} |")
    else:
        parts.append(" |")

    return "".join(parts), warnings, oriented


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
    style.configure(
        "Cut.TNotebook",
        background=DARK_BG,
        borderwidth=0,
    )
    style.configure(
        "Cut.TNotebook.Tab",
        background=PANEL_2,
        foreground=TEXT,
        padding=(16, 8),
        font=("Segoe UI", 10, "bold"),
    )
    style.map(
        "Cut.TNotebook.Tab",
        background=[("selected", RED), ("active", PANEL_BG)],
        foreground=[("selected", TEXT), ("active", TEXT)],
    )


def _setup_window_geometry(root: tk.Misc) -> None:
    """Ustawia sensowny rozmiar głównego okna."""
    try:
        top = root.winfo_toplevel()
        top.geometry(DEFAULT_WINDOW_GEOMETRY)
        top.minsize(*DEFAULT_WINDOW_MINSIZE)
        try:
            top.state("zoomed")
        except Exception:
            pass
    except Exception:
        pass


def _make_tab_grid(tab: tk.Misc) -> None:
    """Przygotowuje zakładkę do skalowania na pełne okno."""
    try:
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
    except Exception:
        pass


def _setup_dialog_window(win: tk.Toplevel, geometry: str, minsize: tuple[int, int] = DEFAULT_DIALOG_MINSIZE) -> None:
    """Wspólny setup dialogów: rozmiar, skalowanie, minimalny rozmiar."""
    try:
        win.geometry(geometry)
        win.minsize(*minsize)
        win.resizable(True, True)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
    except Exception:
        pass


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
        _setup_window_geometry(master.winfo_toplevel())
        super().__init__(master, padding=(12, 12, 12, 12), style="Cut.TFrame")
        self.config_obj = config or {}
        self._last_result = None
        self._last_result_dict: Optional[Dict[str, Any]] = None
        self._materials: List[Dict[str, Any]] = []
        self._material_label_to_id: Dict[str, str] = {}
        self._settings: Dict[str, Any] = load_cutting_settings()
        self.var_tablet = tk.BooleanVar(value=False)
        self._resize_after_id = None
        self._last_cut_length_mm = float(self._settings.get("last_cut_length_mm", DEFAULT_CUT_LENGTH_MM) or DEFAULT_CUT_LENGTH_MM)
        self._last_cut_angle_left = float(self._settings.get("last_cut_angle_left", DEFAULT_CUT_ANGLE_LEFT) or DEFAULT_CUT_ANGLE_LEFT)
        self._last_cut_angle_right = float(self._settings.get("last_cut_angle_right", DEFAULT_CUT_ANGLE_RIGHT) or DEFAULT_CUT_ANGLE_RIGHT)
        self._build_ui()
        self._refresh_materials()
        self._refresh_calculations()
        self._refresh_stock_info()
        self.master = master.winfo_toplevel()
        self.master.bind("<Configure>", self._on_window_resize)

    def _build_ui(self) -> None:
        header = ttk.Frame(self, style="Cut.TFrame")
        header.pack(fill="x", pady=(0, 10))

        title_box = ttk.Frame(header, style="Cut.TFrame")
        title_box.pack(side="left", padx=(0, 18))
        ttk.Label(title_box, text=f"{APP_NAME.upper()} — {APP_SUBTITLE}", style="Cut.Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Rozkrój / cięcie", style="Cut.Muted.TLabel").pack(anchor="w")

        ttk.Label(header, text="Zlecenie:", style="Cut.TLabel").pack(side="left", padx=(20, 5))
        self.var_job = tk.StringVar(value=DEFAULT_JOB_ID)
        ttk.Entry(header, textvariable=self.var_job, width=24, style="Cut.TEntry").pack(side="left", padx=(5, 14))

        ttk.Label(header, text="Rzaz [mm]:", style="Cut.TLabel").pack(side="left")
        self.var_kerf = tk.StringVar(value=f"{DEFAULT_KERF_MM:g}")
        ttk.Entry(header, textvariable=self.var_kerf, width=8, style="Cut.TEntry").pack(side="left", padx=(5, 14))

        ttk.Label(header, text="Min. odpad [mm]:", style="Cut.TLabel").pack(side="left")
        self.var_min_offcut = tk.StringVar(value=f"{DEFAULT_MIN_OFFCUT_MM:g}")
        ttk.Entry(header, textvariable=self.var_min_offcut, width=9, style="Cut.TEntry").pack(side="left", padx=(5, 14))

        ttk.Label(header, text="Strategia:", style="Cut.TLabel").pack(side="left")
        self.var_strategy = tk.StringVar(value=STRATEGY_LABELS[DEFAULT_STRATEGY])
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

        self.tabs = ttk.Notebook(self, style="Cut.TNotebook")
        self.tabs.pack(fill="both", expand=True)

        tab_start = ttk.Frame(self.tabs, padding=(8, 8, 8, 8), style="Cut.TFrame")
        tab_cutting = ttk.Frame(self.tabs, padding=(10, 10, 10, 10), style="Cut.TFrame")
        tab_materials = ttk.Frame(self.tabs, padding=(10, 10, 10, 10), style="Cut.TFrame")
        tab_stock = ttk.Frame(self.tabs, padding=(10, 10, 10, 10), style="Cut.TFrame")
        tab_transports = ttk.Frame(self.tabs, padding=(10, 10, 10, 10), style="Cut.TFrame")
        tab_needs = ttk.Frame(self.tabs, padding=(10, 10, 10, 10), style="Cut.TFrame")
        tab_settings = ttk.Frame(self.tabs, padding=(10, 10, 10, 10), style="Cut.TFrame")

        for tab in (tab_start, tab_cutting, tab_materials, tab_stock, tab_transports, tab_needs, tab_settings):
            _make_tab_grid(tab)

        self.tabs.add(tab_start, text="Start")
        self.tabs.add(tab_cutting, text="Rozkrój")
        self.tabs.add(tab_materials, text="Surowce")
        self.tabs.add(tab_stock, text="Magazyn")
        self.tabs.add(tab_transports, text="Transporty")
        self.tabs.add(tab_needs, text="Zapotrzebowanie")
        self.tabs.add(tab_settings, text="Ustawienia")

        self._build_start_tab(tab_start)

        main = ttk.Panedwindow(tab_cutting, orient="horizontal")
        main.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(main, padding=(0, 0, 10, 0), style="Cut.TFrame")
        right = ttk.Frame(main, padding=(10, 0, 0, 0), style="Cut.TFrame")
        main.add(left, weight=2)
        main.add(right, weight=3)

        self._build_cut_list(left)
        self._build_calculations(left)
        self._build_result_and_preview(right)

        self._build_materials(tab_materials)
        self._build_stock_tab(tab_stock)
        self._build_transports_tab(tab_transports)
        self._build_needs_tab(tab_needs)
        self._build_settings_tab(tab_settings)
        self._build_footer()

    def _select_tab_by_text(self, text: str) -> None:
        if not hasattr(self, "tabs"):
            return
        for tab_id in self.tabs.tabs():
            if self.tabs.tab(tab_id, "text") == text:
                self.tabs.select(tab_id)
                return

    def _build_start_tab(self, parent) -> None:
        box = ttk.Frame(parent, style="Cut.Panel.TFrame")
        box.pack(fill="both", expand=True, padx=0, pady=0)

        ttk.Label(
            box,
            text="EDNOR — pulpit",
            style="Cut.Title.TLabel",
        ).pack(anchor="w", padx=14, pady=(14, 4))

        ttk.Label(
            box,
            text="Szybki start programu. Dane dalej są portable w folderze Ednor_data obok programu.",
            style="Cut.Muted.TLabel",
        ).pack(anchor="w", padx=14, pady=(0, 14))

        actions = ttk.Frame(box, style="Cut.Panel.TFrame")
        actions.pack(anchor="w", padx=14, pady=8)

        ttk.Button(
            actions,
            text="Nowe cięcie / Rozkrój",
            command=lambda: self._select_tab_by_text("Rozkrój"),
            style="Cut.Red.TButton",
        ).grid(row=0, column=0, padx=6, pady=6, sticky="ew")

        ttk.Button(
            actions,
            text="Dodaj transport",
            command=lambda: (self._select_tab_by_text("Transporty"), self._add_transport_dialog()),
            style="Cut.Red.TButton",
        ).grid(row=0, column=1, padx=6, pady=6, sticky="ew")

        ttk.Button(
            actions,
            text="Dodaj surowiec",
            command=lambda: (self._select_tab_by_text("Surowce"), self._add_material_dialog()),
            style="Cut.TButton",
        ).grid(row=1, column=0, padx=6, pady=6, sticky="ew")

        ttk.Button(
            actions,
            text="Magazyn",
            command=lambda: self._select_tab_by_text("Magazyn"),
            style="Cut.TButton",
        ).grid(row=1, column=1, padx=6, pady=6, sticky="ew")

        ttk.Button(
            actions,
            text="Ustawienia / ścieżki",
            command=lambda: self._select_tab_by_text("Ustawienia"),
            style="Cut.TButton",
        ).grid(row=2, column=0, padx=6, pady=6, sticky="ew")

        ttk.Button(
            actions,
            text="Pokaż ścieżki danych",
            command=self._show_paths,
            style="Cut.TButton",
        ).grid(row=2, column=1, padx=6, pady=6, sticky="ew")

        for col in (0, 1):
            actions.columnconfigure(col, weight=1)

        info = tk.Text(
            box,
            height=9,
            bg="#0D0D11",
            fg=MUTED,
            insertbackground=TEXT,
            relief="flat",
            wrap="word",
            font=("Consolas", 10),
        )
        info.pack(fill="x", padx=14, pady=(16, 14))
        info.insert(
            "1.0",
            "Układ roboczy:\n"
            "  • Rozkrój — lista cięcia, wynik, podgląd, karta operatora\n"
            "  • Surowce — definicje profili/rur/prętów/płaskowników\n"
            "  • Magazyn — stan, odpady, później wartość i FIFO\n"
            "  • Transporty — przyjęcia materiału, cena/mb, dostawca\n"
            "  • Zapotrzebowanie — braki materiałowe z aktualnej listy cięć\n"
            "  • Ustawienia — VAT/netto/brutto, ścieżki portable, parametry\n",
        )
        info.configure(state="disabled")

    def _build_stock_tab(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Magazyn", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)
        ttk.Button(top, text="+ DODAJ STAN", command=self._add_stock_dialog, style="Cut.TButton").pack(side="right", padx=(6, 8))
        ttk.Button(top, text="+ DODAJ ODPAD", command=self._add_remnant_dialog, style="Cut.TButton").pack(side="right", padx=(6, 6))
        ttk.Button(
            top,
            text="Odśwież",
            command=lambda: (self._refresh_materials(), self._refresh_stock_info(), self._refresh_stock_table_if_exists()),
            style="Cut.TButton",
        ).pack(side="right")

        self.lbl_stock_summary = ttk.Label(
            parent,
            text="Stan magazynu: -",
            style="Cut.Title.TLabel",
        )
        self.lbl_stock_summary.pack(fill="x", pady=(0, 8))

        self.tree_stock = ttk.Treeview(
            parent,
            columns=STOCK_COLUMNS,
            show="headings",
            selectmode="browse",
            height=18,
            style="Cut.Treeview",
        )
        self.tree_stock.pack(fill="both", expand=True)

        labels = {
            "kind": "Typ",
            "material": "Surowiec",
            "length": "Długość",
            "qty": "Ilość",
            "total_mb": "Razem mb",
            "price": "Cena/mb",
            "value": "Wartość N/B",
            "transport": "Transport / linia",
            "location": "Lokalizacja",
        }
        widths = {
            "kind": 80,
            "material": 220,
            "length": 95,
            "qty": 65,
            "total_mb": 90,
            "price": 90,
            "value": 130,
            "transport": 160,
            "location": 120,
        }
        for col in STOCK_COLUMNS:
            self.tree_stock.heading(col, text=labels[col])
            self.tree_stock.column(col, width=widths[col], anchor="w")

        self.tree_stock.tag_configure("bar", foreground=TEXT)
        self.tree_stock.tag_configure("offcut", foreground=YELLOW)

    def _stock_material_name(self, material_id: str) -> str:
        material_id = str(material_id or "").strip()
        for row in getattr(self, "_materials", []):
            if str(row.get("material_id", "")).strip() == material_id:
                return str(row.get("display_name") or row.get("nazwa") or material_id)
        return material_id

    def _stock_row_values(self, row: Dict[str, Any], kind: str) -> tuple:
        material_id = str(row.get("material_id", "") or "").strip()
        length_mm = float(row.get("length_mm", 0) or 0)
        qty = int(row.get("qty", 0) or 0)
        total_mb = (length_mm * qty) / 1000.0
        price_per_m = float(row.get("price_per_m", 0) or 0)
        vat_percent = float(row.get("vat_percent", 0) or 0)
        price_mode = str(row.get("price_mode", "") or "").strip().lower()

        value = round(total_mb * price_per_m, 2)
        vat_mul = 1.0 + vat_percent / 100.0
        if price_mode == "brutto":
            gross = value
            net = round(value / vat_mul, 2) if vat_mul else value
        else:
            net = value
            gross = round(value * vat_mul, 2)

        transport_id = str(row.get("transport_id", "") or "").strip()
        line_id = str(row.get("line_id", "") or "").strip()
        transport_txt = " / ".join(part for part in (transport_id, line_id) if part) or "-"

        return (
            "Odpad" if kind == "offcut" else "Sztanga",
            self._stock_material_name(material_id),
            f"{length_mm:g} mm",
            str(qty),
            f"{total_mb:g}",
            f"{price_per_m:.2f} {price_mode or ''}".strip(),
            f"{net:.2f} / {gross:.2f}",
            transport_txt,
            str(row.get("location", "") or "-"),
        )

    def _refresh_stock_table(self) -> None:
        if not hasattr(self, "tree_stock"):
            return

        for iid in self.tree_stock.get_children():
            self.tree_stock.delete(iid)

        stock = load_cutting_stock_raw()
        total_mb = 0.0
        total_net = 0.0
        total_gross = 0.0

        def _calc_value(row: Dict[str, Any]) -> tuple[float, float, float]:
            length_mm = float(row.get("length_mm", 0) or 0)
            qty = int(row.get("qty", 0) or 0)
            mb = (length_mm * qty) / 1000.0
            price = float(row.get("price_per_m", 0) or 0)
            vat = float(row.get("vat_percent", 0) or 0)
            mode = str(row.get("price_mode", "") or "").strip().lower()
            value = round(mb * price, 2)
            vat_mul = 1.0 + vat / 100.0
            if mode == "brutto":
                gross = value
                net = round(value / vat_mul, 2) if vat_mul else value
            else:
                net = value
                gross = round(value * vat_mul, 2)
            return mb, net, gross

        for kind, bucket_name in (("bar", "bars"), ("offcut", "offs")):
            rows = stock.get(bucket_name, [])
            if not isinstance(rows, list):
                continue
            for idx, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                qty = int(row.get("qty", 0) or 0)
                if qty <= 0:
                    continue
                mb, net, gross = _calc_value(row)
                total_mb += mb
                total_net += net
                total_gross += gross
                iid = f"{bucket_name}_{idx}_{str(row.get('id') or '')}"
                self.tree_stock.insert(
                    "",
                    "end",
                    iid=iid,
                    values=self._stock_row_values(row, kind),
                    tags=(kind,),
                )

        if hasattr(self, "lbl_stock_summary"):
            self.lbl_stock_summary.configure(
                text=f"Stan magazynu: {total_mb:g} mb | wartość netto {total_net:.2f} zł | brutto {total_gross:.2f} zł"
            )

    def _build_transports_tab(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Transporty", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)
        ttk.Button(top, text="+ DODAJ TRANSPORT", command=self._add_transport_dialog, style="Cut.Red.TButton").pack(side="right", padx=(6, 8))
        ttk.Button(top, text="Odśwież", command=self._refresh_transports_table, style="Cut.TButton").pack(side="right", padx=(6, 6))

        self.tree_transports = ttk.Treeview(
            parent,
            columns=TRANSPORT_COLUMNS,
            show="headings",
            selectmode="browse",
            height=10,
            style="Cut.Treeview",
        )
        self.tree_transports.pack(fill="both", expand=True, pady=(0, 10))

        transport_labels = {
            "id": "Nr",
            "created": "Data",
            "supplier": "Firma",
            "lines": "Pozycji",
            "mb": "Razem mb",
            "net": "Netto",
            "gross": "Brutto",
            "cost": "Transport",
        }
        transport_widths = {
            "id": 110,
            "created": 145,
            "supplier": 180,
            "lines": 70,
            "mb": 90,
            "net": 90,
            "gross": 90,
            "cost": 90,
        }
        for col in TRANSPORT_COLUMNS:
            self.tree_transports.heading(col, text=transport_labels[col])
            self.tree_transports.column(col, width=transport_widths[col], anchor="w")

        ttk.Label(parent, text="Pozycje transportu", style="Cut.Subtitle.TLabel").pack(anchor="w", pady=(4, 6))

        self.tree_transport_lines = ttk.Treeview(
            parent,
            columns=TRANSPORT_LINE_COLUMNS,
            show="headings",
            selectmode="browse",
            height=8,
            style="Cut.Treeview",
        )
        self.tree_transport_lines.pack(fill="both", expand=True)

        line_labels = {
            "material": "Surowiec",
            "length": "Sztanga",
            "qty": "Ilość",
            "mb": "Razem mb",
            "price": "Cena/mb",
            "value": "Netto / Brutto",
        }
        line_widths = {
            "material": 260,
            "length": 90,
            "qty": 70,
            "mb": 90,
            "price": 90,
            "value": 130,
        }
        for col in TRANSPORT_LINE_COLUMNS:
            self.tree_transport_lines.heading(col, text=line_labels[col])
            self.tree_transport_lines.column(col, width=line_widths[col], anchor="w")

        self.tree_transports.bind("<<TreeviewSelect>>", lambda _e: self._on_transport_selected())
        self._refresh_transports_table()

    def _refresh_transports_table(self) -> None:
        if not hasattr(self, "tree_transports"):
            return
        for iid in self.tree_transports.get_children():
            self.tree_transports.delete(iid)
        if hasattr(self, "tree_transport_lines"):
            for iid in self.tree_transport_lines.get_children():
                self.tree_transport_lines.delete(iid)

        data = load_transports_raw()
        transports = data.get("transports", [])
        if not isinstance(transports, list):
            transports = []
        for idx, transport in enumerate(reversed(transports)):
            if not isinstance(transport, dict):
                continue
            tid = str(transport.get("transport_id", f"TR-{idx:06d}"))
            lines = transport.get("lines", [])
            if not isinstance(lines, list):
                lines = []
            total_mb = 0.0
            total_net = 0.0
            total_gross = 0.0
            for line in lines:
                if not isinstance(line, dict):
                    continue
                total_mb += float(line.get("total_length_m", line.get("total_length_mm", 0) / 1000.0) or 0)
                total_net += float(line.get("line_total_net", 0) or 0)
                total_gross += float(line.get("line_total_gross", 0) or 0)
            iid = f"transport_{idx}_{tid}"
            self.tree_transports.insert(
                "",
                "end",
                iid=iid,
                values=(
                    tid,
                    str(transport.get("created_at", "")),
                    str(transport.get("supplier", "") or "-"),
                    str(len(lines)),
                    f"{total_mb:g}",
                    f"{total_net:.2f}",
                    f"{total_gross:.2f}",
                    f"{float(transport.get('transport_cost', 0) or 0):.2f}",
                ),
                tags=(tid,),
            )

    def _on_transport_selected(self) -> None:
        if not hasattr(self, "tree_transports") or not hasattr(self, "tree_transport_lines"):
            return
        for iid in self.tree_transport_lines.get_children():
            self.tree_transport_lines.delete(iid)
        sel = self.tree_transports.selection()
        if not sel:
            return
        values = self.tree_transports.item(sel[0], "values")
        if not values:
            return
        selected_tid = str(values[0])
        data = load_transports_raw()
        for transport in data.get("transports", []):
            if str(transport.get("transport_id", "")) != selected_tid:
                continue
            for idx, line in enumerate(transport.get("lines", []) or []):
                if not isinstance(line, dict):
                    continue
                length = float(line.get("bar_length_mm", 0) or 0)
                qty = int(line.get("qty", 0) or 0)
                total_m = float(line.get("total_length_m", (length * qty) / 1000.0) or 0)
                self.tree_transport_lines.insert(
                    "",
                    "end",
                    iid=f"{selected_tid}_line_{idx}",
                    values=(
                        str(line.get("material_display") or line.get("material_id") or "-"),
                        f"{length:g} mm",
                        str(qty),
                        f"{total_m:g}",
                        f"{float(line.get('price_per_m', 0) or 0):.2f}",
                        f"{float(line.get('line_total_net', 0) or 0):.2f} / {float(line.get('line_total_gross', 0) or 0):.2f}",
                    ),
                )
            break

    def _build_settings_tab(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Ustawienia", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)
        ttk.Button(top, text="Pokaż ścieżki", command=self._show_paths, style="Cut.TButton").pack(side="right", padx=(6, 8))

        form = ttk.Frame(parent, style="Cut.Panel.TFrame")
        form.pack(fill="x", pady=(0, 10))

        settings = load_cutting_settings()
        self.var_set_price_mode = tk.StringVar(value=str(settings.get("price_mode", "netto") or "netto"))
        self.var_set_vat = tk.StringVar(value=str(settings.get("vat_percent", 23) or 23))
        self.var_set_kerf = tk.StringVar(value=str(settings.get("default_kerf_mm", self.var_kerf.get() or DEFAULT_KERF_MM)))
        self.var_set_min_offcut = tk.StringVar(value=str(settings.get("default_min_offcut_mm", self.var_min_offcut.get() or DEFAULT_MIN_OFFCUT_MM)))
        self.var_set_bar_length = tk.StringVar(value=str(settings.get("default_bar_length_mm", 6000) or 6000))
        self.var_set_show_meters = tk.BooleanVar(value=bool(settings.get("show_meters_hint", True)))
        self.var_set_tablet = tk.BooleanVar(value=bool(settings.get("tablet_mode", False)))

        ttk.Label(form, text="Tryb cen", style="Cut.TLabel").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        ttk.Combobox(form, textvariable=self.var_set_price_mode, values=("netto", "brutto"), width=14, state="readonly").grid(row=0, column=1, padx=10, pady=6, sticky="w")
        ttk.Label(form, text="VAT [%]", style="Cut.TLabel").grid(row=0, column=2, padx=10, pady=6, sticky="w")
        ttk.Entry(form, textvariable=self.var_set_vat, width=12, style="Cut.TEntry").grid(row=0, column=3, padx=10, pady=6, sticky="w")
        ttk.Label(form, text="Rzaz piły [mm]", style="Cut.TLabel").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        ttk.Entry(form, textvariable=self.var_set_kerf, width=12, style="Cut.TEntry").grid(row=1, column=1, padx=10, pady=6, sticky="w")
        ttk.Label(form, text="Minimalny odpad [mm]", style="Cut.TLabel").grid(row=1, column=2, padx=10, pady=6, sticky="w")
        ttk.Entry(form, textvariable=self.var_set_min_offcut, width=12, style="Cut.TEntry").grid(row=1, column=3, padx=10, pady=6, sticky="w")
        ttk.Label(form, text="Domyślna długość sztangi [mm]", style="Cut.TLabel").grid(row=2, column=0, padx=10, pady=6, sticky="w")
        ttk.Entry(form, textvariable=self.var_set_bar_length, width=12, style="Cut.TEntry").grid(row=2, column=1, padx=10, pady=6, sticky="w")
        ttk.Checkbutton(form, text="Tryb tablet", variable=self.var_set_tablet).grid(row=2, column=2, padx=10, pady=6, sticky="w")
        ttk.Checkbutton(form, text="Pokazuj metry w podpowiedziach", variable=self.var_set_show_meters).grid(row=2, column=3, padx=10, pady=6, sticky="w")
        ttk.Button(form, text="ZAPISZ USTAWIENIA", command=self._save_settings_from_tab, style="Cut.Red.TButton").grid(row=3, column=0, columnspan=2, padx=10, pady=(12, 10), sticky="w")

        paths = get_cutting_debug_paths()
        path_box = tk.Text(parent, height=9, bg="#0D0D11", fg=MUTED, insertbackground=TEXT, relief="flat", wrap="word", font=("Consolas", 10))
        path_box.pack(fill="both", expand=True)
        path_box.insert("1.0", "Ścieżki portable / dane programu:\n\n" + "\n".join(f"{k}: {v}" for k, v in paths.items()))
        path_box.configure(state="disabled")

    def _save_settings_from_tab(self) -> None:
        try:
            price_mode = self.var_set_price_mode.get().strip().lower()
            if price_mode not in ("netto", "brutto"):
                price_mode = "netto"
            vat = float(str(self.var_set_vat.get()).replace(",", "."))
            kerf = float(str(self.var_set_kerf.get()).replace(",", "."))
            min_offcut = float(str(self.var_set_min_offcut.get()).replace(",", "."))
            bar_length = float(str(self.var_set_bar_length.get()).replace(",", "."))
            if vat < 0 or kerf < 0 or min_offcut < 0 or bar_length <= 0:
                raise ValueError("Nieprawidłowe wartości ustawień.")
        except Exception as exc:
            messagebox.showerror("Ustawienia", str(exc))
            return
        update_cutting_setting("price_mode", price_mode)
        update_cutting_setting("vat_percent", vat)
        update_cutting_setting("default_kerf_mm", kerf)
        update_cutting_setting("default_min_offcut_mm", min_offcut)
        update_cutting_setting("default_bar_length_mm", bar_length)
        update_cutting_setting("show_meters_hint", bool(self.var_set_show_meters.get()))
        update_cutting_setting("tablet_mode", bool(self.var_set_tablet.get()))
        self._settings = load_cutting_settings()
        self.var_kerf.set(f"{kerf:g}")
        self.var_min_offcut.set(f"{min_offcut:g}")
        self.var_tablet.set(bool(self.var_set_tablet.get()))
        self._apply_tablet_mode()
        messagebox.showinfo("Ustawienia", "Ustawienia zapisane.")

    def _build_needs_tab(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Zapotrzebowanie", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)
        ttk.Button(top, text="PRZELICZ BRAKI", command=self._refresh_needs_table, style="Cut.Red.TButton").pack(side="right", padx=(6, 8))
        self.lbl_needs_summary = ttk.Label(parent, text="Zapotrzebowanie: przelicz z aktualnej listy cięć.", style="Cut.Title.TLabel")
        self.lbl_needs_summary.pack(fill="x", pady=(0, 8))
        self.tree_needs = ttk.Treeview(parent, columns=NEEDS_COLUMNS, show="headings", selectmode="browse", height=18, style="Cut.Treeview")
        self.tree_needs.pack(fill="both", expand=True)
        labels = {"material": "Surowiec", "need": "Potrzeba", "stock": "Jest", "missing": "Brakuje", "suggestion": "Sugerowany zakup"}
        for col in NEEDS_COLUMNS:
            self.tree_needs.heading(col, text=labels[col])
            self.tree_needs.column(col, width=180, anchor="w")
        self.tree_needs.tag_configure("ok", foreground=GREEN)
        self.tree_needs.tag_configure("missing", foreground=YELLOW)

    def _calculate_needs_from_current_cuts(self) -> List[Dict[str, Any]]:
        materials_by_id = {str(m.get("material_id", "")): m for m in self._materials}
        need_mm_by_material: Dict[str, float] = {}
        for item in self._read_cut_items():
            material_id = str(item.material_id or "").strip()
            if material_id:
                need_mm_by_material[material_id] = need_mm_by_material.get(material_id, 0.0) + float(item.length_mm or 0) * int(item.qty or 1)
        default_bar_mm = float(self._settings.get("default_bar_length_mm", 6000) or 6000)
        rows: List[Dict[str, Any]] = []
        for material_id, need_mm in sorted(need_mm_by_material.items()):
            material = materials_by_id.get(material_id, {})
            stock_mb = float(material.get("stock_mb", 0) or 0)
            missing_mm = max(0.0, need_mm - (stock_mb * 1000.0))
            missing_bars = int((missing_mm + default_bar_mm - 1) // default_bar_mm) if missing_mm > 0 else 0
            rows.append({"material_id": material_id, "display": str(material.get("display_name") or material.get("nazwa") or material_id), "need_mb": need_mm / 1000.0, "stock_mb": stock_mb, "missing_mb": missing_mm / 1000.0, "suggestion": "-" if missing_bars <= 0 else f"{missing_bars} szt. po {default_bar_mm:g} mm"})
        return rows

    def _refresh_needs_table(self) -> None:
        for iid in self.tree_needs.get_children():
            self.tree_needs.delete(iid)
        rows = self._calculate_needs_from_current_cuts()
        missing_count = 0
        missing_total = 0.0
        for idx, row in enumerate(rows):
            missing = float(row.get("missing_mb", 0) or 0)
            if missing > 0:
                missing_count += 1
                missing_total += missing
            self.tree_needs.insert("", "end", iid=f"need_{idx}_{row.get('material_id')}", values=(row.get("display", "-"), f"{float(row.get('need_mb', 0) or 0):g} mb", f"{float(row.get('stock_mb', 0) or 0):g} mb", f"{missing:g} mb", row.get("suggestion", "-")), tags=("missing" if missing > 0 else "ok",))
        if not rows:
            text = "Zapotrzebowanie: lista cięć jest pusta."
        elif missing_count:
            text = f"Braki: {missing_count} surowców | razem {missing_total:g} mb do domówienia"
        else:
            text = "Braki: brak — magazyn pokrywa aktualną listę cięć."
        self.lbl_needs_summary.configure(text=text)

    def _panel_title(self, parent, text: str) -> None:
        box = ttk.Frame(parent, style="Cut.Panel.TFrame")
        box.pack(fill="x", pady=(0, 6))
        ttk.Label(box, text=text, style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)

    def _build_materials(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Baza surowców", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)
        ttk.Button(top, text="+ Surowiec", command=self._add_material_dialog, style="Cut.Red.TButton").pack(side="right", padx=(6, 8))
        ttk.Button(top, text="+ TRANSPORT", command=self._add_transport_dialog, style="Cut.Red.TButton").pack(side="right", padx=(6, 6))
        ttk.Button(top, text="+ DODAJ STAN", command=self._add_stock_dialog, style="Cut.TButton").pack(side="right", padx=(6, 6))
        ttk.Button(top, text="+ DODAJ ODPAD", command=self._add_remnant_dialog, style="Cut.TButton").pack(side="right", padx=(6, 6))
        ttk.Button(top, text="Usuń", command=self._delete_selected_material, style="Cut.TButton").pack(side="right", padx=(0, 6))
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
        self._materials = [m for m in load_materials() if bool(m.get("aktywny", True))]
        self._material_label_to_id = {material_label(m): m["material_id"] for m in self._materials}
        if hasattr(self, "tree_materials"):
            for iid in self.tree_materials.get_children():
                self.tree_materials.delete(iid)
            for m in self._materials:
                display_label = material_label(m)
                self.tree_materials.insert("", "end", iid=m["material_id"], values=(display_label,))
        self._refresh_stock_table_if_exists()


    def _add_stock_dialog(self):
        sel = self.tree_materials.selection()
        if not sel:
            messagebox.showwarning("Magazyn", "Wybierz surowiec")
            return

        material_id = sel[0]

        val = simpledialog.askstring(
            "Dodaj stan magazynowy",
            "Podaj długość w mm (np. 6000)\nIlość po spacji (np. 6000 4):",
            initialvalue="6000",
        )
        if not val:
            return

        try:
            parts = str(val).strip().split()
            length_mm = parse_length_to_mm(parts[0])
            qty = int(parts[1]) if len(parts) > 1 else 1
            add_stock_bar(material_id=material_id, length_mm=length_mm, qty=qty)
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
            return

        self._refresh_materials()
        self._refresh_stock_info()
        self._refresh_stock_table_if_exists()

    def _add_remnant_dialog(self):
        sel = self.tree_materials.selection()
        if not sel:
            messagebox.showwarning("Magazyn", "Wybierz surowiec")
            return

        material_id = sel[0]

        val = simpledialog.askstring(
            "Dodaj odpad użytkowy",
            "Podaj długość odpadu w mm (np. 1200):",
            initialvalue="1200",
        )
        if not val:
            return

        try:
            mm = parse_length_to_mm(val)
            add_remnant(material_id, mm, qty=1)
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
            return

        self._refresh_materials()
        self._refresh_stock_info()
        self._refresh_stock_table_if_exists()

    def _refresh_stock_table_if_exists(self) -> None:
        """Odśwież tabelę magazynu, jeśli zakładka/widok magazynu już istnieje."""
        refresh = getattr(self, "_refresh_stock_table", None)
        if callable(refresh):
            refresh()

    def _operator_steps(self, data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Buduje listę kroków cięcia dla operatora z ostatniego wyniku.

        Nie zmienia algorytmu ani kolejności optymalizacji.
        To jest tylko czytelna karta pracy.
        """

        data = data or self._last_result_dict or {}
        steps: List[Dict[str, Any]] = []
        global_step = 1

        for bar_no, bar in enumerate(data.get("bars_used", []) or [], start=1):
            material_id = str(bar.get("material_id", "")).strip()
            source = str(bar.get("source", "")).strip()
            bar_length = float(bar.get("bar_length_mm", 0) or 0)
            waste = float(bar.get("waste_mm", 0) or 0)

            for local_step, cut in enumerate(bar.get("cuts", []) or [], start=1):
                length_mm = float(cut.get("length_mm", 0) or 0)
                angle_l = float(cut.get("angle_left", 0) or 0)
                angle_r = float(cut.get("angle_right", 0) or 0)
                label = str(cut.get("label", "") or "").strip()

                steps.append(
                    {
                        "global_step": global_step,
                        "bar_no": bar_no,
                        "local_step": local_step,
                        "material_id": material_id,
                        "material": self._display_material(material_id),
                        "source": source,
                        "bar_length_mm": bar_length,
                        "length_mm": length_mm,
                        "angle_left": angle_l,
                        "angle_right": angle_r,
                        "shape": _operator_cut_shape(angle_l, angle_r),
                        "label": label,
                        "waste_mm": waste,
                    }
                )
                global_step += 1

        return steps

    def _operator_card_text(self, data: Optional[Dict[str, Any]] = None) -> str:
        data = data or self._last_result_dict or {}
        job_id = str(data.get("job_id") or self.var_job.get() or DEFAULT_JOB_ID)
        bars = data.get("bars_used", []) or []

        lines: List[str] = []
        lines.append("EDNOR — KARTA CIĘCIA / OPERATOR")
        lines.append(f"Zlecenie: {job_id}")
        lines.append("=" * 72)

        if not bars:
            lines.append("Brak obliczonego wyniku.")
            return "\n".join(lines)

        for bar_no, bar in enumerate(bars, start=1):
            material_id = str(bar.get("material_id", "")).strip()
            material = self._display_material(material_id)
            source = str(bar.get("source", "") or "").strip()
            bar_length = float(bar.get("bar_length_mm", 0) or 0)
            waste = float(bar.get("waste_mm", 0) or 0)
            map_text, map_warnings, oriented_cuts = _operator_bar_map_text(bar)

            lines.append("")
            lines.append(
                f"SZTANGA {bar_no}: {material} | {format_mm(bar_length)} | źródło: {source or '-'}"
            )
            lines.append(f"MAPA: {map_text}")
            if map_warnings:
                lines.append("UWAGA: !!! oznacza niezgodne kąty sąsiednich detali — nie robić jako jedno wspólne cięcie.")
                for warning in map_warnings:
                    lines.append(f"  - {warning}")
            lines.append("-" * 72)

            source_cuts = bar.get("cuts", []) or []
            for local_step, cut in enumerate(source_cuts, start=1):
                length_mm = float(cut.get("length_mm", 0) or 0)
                angle_l = float(cut.get("angle_left", 0) or 0)
                angle_r = float(cut.get("angle_right", 0) or 0)
                label = str(cut.get("label", "") or "").strip()
                shape = _operator_cut_shape(angle_l, angle_r)
                oriented = oriented_cuts[local_step - 1] if local_step - 1 < len(oriented_cuts) else cut
                flip_note = " | OBRÓĆ DETAL NA MAPIE" if oriented.get("_operator_flipped") else ""
                label_txt = f" | {label}" if label else ""
                lines.append(
                    f"{local_step:>2}. {length_mm:g} mm   {shape:<5}   "
                    f"{angle_l:g}° / {angle_r:g}°{flip_note}{label_txt}"
                )

            lines.append(f"ODPAD: {format_mm(waste)}")

        return "\n".join(lines)

    def _render_operator_card(self, data: Optional[Dict[str, Any]] = None) -> None:
        if not hasattr(self, "txt_operator_card"):
            return
        self.txt_operator_card.configure(state="normal")
        self.txt_operator_card.delete("1.0", "end")
        self.txt_operator_card.insert("1.0", self._operator_card_text(data))
        self.txt_operator_card.configure(state="disabled")

    def _export_operator_card_csv(self) -> None:
        if not self._last_result_dict:
            messagebox.showwarning("Karta operatora", "Najpierw oblicz albo wczytaj kalkulację.")
            return

        path = filedialog.asksaveasfilename(
            title="Eksport karty operatora CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Wszystkie pliki", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "job_id",
                        "bar_no",
                        "step_no",
                        "material",
                        "source",
                        "bar_length_mm",
                        "length_mm",
                        "shape",
                        "angle_left",
                        "angle_right",
                        "label",
                        "waste_mm",
                    ]
                )
                job_id = str(self._last_result_dict.get("job_id") or self.var_job.get() or DEFAULT_JOB_ID)
                for step in self._operator_steps(self._last_result_dict):
                    writer.writerow(
                        [
                            job_id,
                            step["bar_no"],
                            step["local_step"],
                            step["material"],
                            step["source"],
                            f'{float(step["bar_length_mm"]):g}',
                            f'{float(step["length_mm"]):g}',
                            step["shape"],
                            f'{float(step["angle_left"]):g}',
                            f'{float(step["angle_right"]):g}',
                            step["label"],
                            f'{float(step["waste_mm"]):g}',
                        ]
                    )
        except Exception as exc:
            messagebox.showerror("Karta operatora", f"Nie udało się zapisać CSV:\n{exc}")
            return

        messagebox.showinfo("Karta operatora", f"Zapisano:\n{path}")

    def _export_operator_card_html(self) -> None:
        if not self._last_result_dict:
            messagebox.showwarning("Karta operatora", "Najpierw oblicz albo wczytaj kalkulację.")
            return

        path = filedialog.asksaveasfilename(
            title="Eksport karty operatora HTML",
            defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("Wszystkie pliki", "*.*")],
        )
        if not path:
            return

        text = self._operator_card_text(self._last_result_dict)
        safe = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        html = f"""<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <title>Ednor - Karta operatora</title>
  <style>
    body {{
      font-family: Consolas, monospace;
      margin: 24px;
      background: #fff;
      color: #111;
    }}
    pre {{
      font-size: 16px;
      line-height: 1.45;
      white-space: pre-wrap;
    }}
  </style>
</head>
<body>
<pre>{safe}</pre>
</body>
</html>
"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as exc:
            messagebox.showerror("Karta operatora", f"Nie udało się zapisać HTML:\n{exc}")
            return

        messagebox.showinfo("Karta operatora", f"Zapisano:\n{path}")

    def _build_cut_list(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Lista do cięcia", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)

        # Przyciski akcji - bardziej przejrzysty układ
        actions = ttk.Frame(top, style="Cut.TFrame")
        actions.pack(side="right", padx=5)
        ttk.Button(actions, text="+ DODAJ", command=self._add_cut_row_dialog, style="Cut.Red.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="Edytuj", command=self._edit_selected_cut, style="Cut.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="Duplikuj", command=self._duplicate_selected_cut, style="Cut.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="Sortuj ↓", command=self._sort_cuts_longest_first, style="Cut.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="Wyczyść", command=self._clear_cuts, style="Cut.TButton").pack(side="left", padx=3)
        ttk.Button(actions, text="Usuń", command=self._delete_selected_cut, style="Cut.TButton").pack(side="left", padx=3)

        # Narzędzia CSV
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
        self.tree_cuts.pack(fill="both", expand=True)

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


        operator_box = ttk.Frame(parent, style="Cut.Panel.TFrame")
        operator_box.pack(fill="both", expand=True, pady=(10, 0))

        operator_header = ttk.Frame(operator_box, style="Cut.Panel.TFrame")
        operator_header.pack(fill="x", padx=10, pady=(8, 0))

        ttk.Label(
            operator_header,
            text="Karta operatora",
            style="Cut.Subtitle.TLabel",
        ).pack(side="left")

        ttk.Button(
            operator_header,
            text="Eksport karty CSV",
            command=self._export_operator_card_csv,
            style="Cut.TButton",
        ).pack(side="right", padx=(6, 0))

        ttk.Button(
            operator_header,
            text="Eksport karty HTML",
            command=self._export_operator_card_html,
            style="Cut.TButton",
        ).pack(side="right", padx=(6, 0))

        self.txt_operator_card = tk.Text(
            operator_box,
            height=12,
            bg="#0D0D11",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            wrap="none",
            font=("Consolas", 12),
        )
        self.txt_operator_card.pack(fill="both", expand=True, padx=10, pady=10)

    def _on_window_resize(self, _event=None) -> None:
        """Opóźnione przerysowanie preview po zmianie rozmiaru okna."""
        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(120, self._redraw_preview)

    def _redraw_preview(self) -> None:
        self._resize_after_id = None
        if self._last_result_dict:
            self._draw_preview(self._last_result_dict)

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

        self._last_cut_length_mm = float(length_mm)
        self._last_cut_angle_left = float(angle_left)
        self._last_cut_angle_right = float(angle_right)
        update_cutting_setting("last_cut_length_mm", self._last_cut_length_mm)
        update_cutting_setting("last_cut_angle_left", self._last_cut_angle_left)
        update_cutting_setting("last_cut_angle_right", self._last_cut_angle_right)

    def _remember_last_material(self, material_id: str) -> None:
        material_id = str(material_id or "").strip()
        if not material_id:
            return
        self._settings["last_material_id"] = material_id
        update_cutting_setting("last_material_id", material_id)

    def _sort_cuts_longest_first(self) -> None:
        """Sortuje listę cięć malejąco po długości, zachowując wartości wierszy."""
        rows = []
        for iid in self.tree_cuts.get_children():
            values = self.tree_cuts.item(iid, "values")
            try:
                length = parse_length_to_mm(str(values[1]))
            except Exception:
                length = 0.0
            rows.append((length, values))

        if not rows:
            return

        rows.sort(key=lambda row: row[0], reverse=True)

        for iid in self.tree_cuts.get_children():
            self.tree_cuts.delete(iid)

        for _length, values in rows:
            self.tree_cuts.insert("", "end", values=values)

    def _required_material_mm(self, items: List[CutItem]) -> Dict[str, float]:
        required: Dict[str, float] = {}
        for item in items:
            required[item.material_id] = required.get(item.material_id, 0.0) + float(item.length_mm) * int(item.qty)
        return required

    def _available_material_mm(self) -> Dict[str, float]:
        available: Dict[str, float] = {}
        for bar in load_stock_bars():
            available[bar.material_id] = available.get(bar.material_id, 0.0) + float(bar.length_mm) * int(bar.qty)
        return available

    def _warn_if_stock_shortage(self, items: List[CutItem]) -> bool:
        """Prosta walidacja przed obliczeniem: długość wymagana vs dostępna.

        To nie zastępuje optymalizatora, ale szybko łapie oczywiste braki.
        """
        required = self._required_material_mm(items)
        available = self._available_material_mm()
        shortages = []
        ok_lines = []

        for material_id, req_mm in sorted(required.items()):
            av_mm = available.get(material_id, 0.0)
            display = self._display_material(material_id)
            if av_mm + 0.001 < req_mm:
                shortages.append(f"- {display}: potrzeba {format_mm(req_mm)}, dostępne {format_mm(av_mm)}")
            else:
                ok_lines.append(f"- {display}: potrzeba {format_mm(req_mm)}, dostępne {format_mm(av_mm)}")

        if not shortages:
            return True

        msg = (
            "Wykryto możliwy brak materiału:\n\n"
            + "\n".join(shortages)
            + "\n\nTo jest kontrola orientacyjna. Optymalizator i tak może próbować liczyć.\n"
            "Kontynuować obliczenie?"
        )
        return messagebox.askyesno("Brak materiału", msg)

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
        if sel and hasattr(self, "_material_label_to_id"):
            return sel[0]
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
            try:
                upsert_material(dialog.result)
            except Exception as exc:
                messagebox.showerror("Surowiec", f"Nie udało się zapisać surowca:\n{exc}")
                return
            self._refresh_materials()
            self._refresh_stock_info()

    def _edit_selected_material(self) -> None:
        material_id = self._selected_material_id()
        row = self._get_material_row(material_id)
        if not row:
            return
        dialog = _MaterialDialog(self, row)
        self.wait_window(dialog.win)
        if dialog.result:
            try:
                upsert_material(dialog.result)
            except Exception as exc:
                messagebox.showerror("Surowiec", f"Nie udało się zapisać surowca:\n{exc}")
                return
            self._refresh_materials()
            self._refresh_stock_info()

    def _delete_selected_material(self) -> None:
        material_id = self._selected_material_id()
        if not material_id:
            messagebox.showwarning("Surowiec", "Wybierz surowiec do usunięcia.")
            return
        row = self._get_material_row(material_id)
        label = str(row.get("display_name") or row.get("nazwa") or material_id) if row else material_id
        ok = messagebox.askyesno(
            "Usuń surowiec",
            f"Ukryć surowiec z listy?\n\n{label}\n\nHistoria transportów i kalkulacji zostanie zachowana.",
        )
        if not ok:
            return
        try:
            deactivate_material(material_id)
        except Exception as exc:
            messagebox.showerror("Surowiec", f"Nie udało się usunąć surowca:\n{exc}")
            return
        self._refresh_materials()
        self._refresh_stock_info()

    def _add_transport_dialog(self) -> None:
        self._refresh_materials()
        if not self._materials:
            messagebox.showwarning("Transport", "Najpierw dodaj przynajmniej jeden surowiec.")
            return
        dialog = _TransportDialog(self)
        self.wait_window(dialog.win)
        if not dialog.result:
            return
        transport = save_transport(dialog.result)
        self._refresh_materials()
        self._refresh_stock_info()
        self._refresh_stock_table_if_exists()
        self._refresh_transports_table_if_exists()
        messagebox.showinfo("Transport", f"Zapisano transport:\n{transport.get('transport_id')}")

    def _refresh_transports_table_if_exists(self) -> None:
        refresh = getattr(self, "_refresh_transports_table", None)
        if callable(refresh):
            refresh()

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

        if not self._warn_if_stock_shortage(items):
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
            job_id=self.var_job.get().strip() or DEFAULT_JOB_ID,
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
            "job_id": self.var_job.get().strip() or DEFAULT_JOB_ID,
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
        self._render_operator_card(data)
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
        self.canvas.bind("<Configure>", self._on_window_resize)

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

    def _display_material(self, material_id: str) -> str:
        """Czytelna nazwa surowca bez technicznego ID, jeśli istnieje w bazie."""
        for row in getattr(self, "_materials", []):
            if str(row.get("material_id", "")).strip() == str(material_id).strip():
                return str(row.get("display_name") or row.get("nazwa") or material_id)
        return str(material_id)

    def _delete_selected_cut(self) -> None:
        sel = self.tree_cuts.selection()
        if not sel:
            return
        self.tree_cuts.delete(sel[0])

    def _clear_cuts(self) -> None:
        if not self.tree_cuts.get_children():
            return
        if messagebox.askyesno("Wyczyść listę", "Na pewno wyczyścić całą listę cięć?"):
            for iid in self.tree_cuts.get_children():
                self.tree_cuts.delete(iid)
            messagebox.showinfo("Wyczyść listę", "Lista cięć została wyczyszczona.")

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
        raw_length = str(values[1])
        raw_mm = raw_length.split("mm", 1)[0].strip()
        try:
            length_mm = float(raw_mm)
        except Exception:
            messagebox.showerror("Błąd", f"Nieprawidłowa długość:\n{values[1]}")
            return

        data = {
            "material_id": values[0],
            "length_mm": length_mm,
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
        self._render_operator_card(result)

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
        _setup_dialog_window(self.win, DEFAULT_MATERIAL_DIALOG_GEOMETRY, (560, 460))

        self._material_id = str(row.get("material_id", "")).strip()
        self.v_typ = tk.StringVar(value=str(row.get("typ", "profil") or "profil"))

        wymiary = row.get("wymiary") if isinstance(row.get("wymiary"), dict) else {}
        rozmiar = str(row.get("rozmiar", "") or "").strip()
        parsed = self._parse_existing_dims(str(row.get("typ", "profil")), rozmiar)

        self.v_a = tk.StringVar(value=str(wymiary.get("a", parsed.get("a", "")) or ""))
        self.v_b = tk.StringVar(value=str(wymiary.get("b", parsed.get("b", "")) or ""))
        self.v_c = tk.StringVar(value=str(wymiary.get("c", parsed.get("c", "")) or ""))
        self.v_len = tk.StringVar(value=format_mm(float(row.get("domyslna_dlugosc_mm", 6000) or 6000)))
        self.v_active = tk.BooleanVar(value=bool(row.get("aktywny", True)))
        self.v_uwagi = tk.StringVar(value=str(row.get("uwagi", "")))
        self.v_preview = tk.StringVar(value="")
        self.v_hint = tk.StringVar(value="")

        ttk.Label(self.win, text="Rodzaj surowca", style="Cut.TLabel").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.cbo_typ = ttk.Combobox(
            self.win,
            textvariable=self.v_typ,
            values=("profil", "rura", "pręt", "płaskownik"),
            width=34,
        )
        self.cbo_typ.grid(row=0, column=1, padx=10, pady=6, sticky="ew")
        ttk.Label(
            self.win,
            text="Możesz wpisać własny rodzaj, np. kątownik.",
            style="Cut.Muted.TLabel",
        ).grid(row=1, column=1, padx=10, pady=(0, 6), sticky="w")

        ttk.Label(self.win, text="Wymiary", style="Cut.Subtitle.TLabel").grid(
            row=2, column=0, columnspan=2, padx=10, pady=(10, 4), sticky="w"
        )

        self.lbl_a = ttk.Label(self.win, text="A", style="Cut.TLabel")
        self.lbl_a.grid(row=3, column=0, padx=10, pady=6, sticky="w")
        ttk.Entry(self.win, textvariable=self.v_a, width=36, style="Cut.TEntry").grid(row=3, column=1, padx=10, pady=6, sticky="ew")

        self.lbl_b = ttk.Label(self.win, text="B", style="Cut.TLabel")
        self.lbl_b.grid(row=4, column=0, padx=10, pady=6, sticky="w")
        ttk.Entry(self.win, textvariable=self.v_b, width=36, style="Cut.TEntry").grid(row=4, column=1, padx=10, pady=6, sticky="ew")

        self.lbl_c = ttk.Label(self.win, text="C / ścianka", style="Cut.TLabel")
        self.lbl_c.grid(row=5, column=0, padx=10, pady=6, sticky="w")
        ttk.Entry(self.win, textvariable=self.v_c, width=36, style="Cut.TEntry").grid(row=5, column=1, padx=10, pady=6, sticky="ew")

        ttk.Label(self.win, textvariable=self.v_hint, style="Cut.Muted.TLabel").grid(
            row=6, column=0, columnspan=2, padx=10, pady=(0, 8), sticky="w"
        )

        ttk.Label(self.win, text="Podgląd surowca", style="Cut.TLabel").grid(row=7, column=0, padx=10, pady=6, sticky="w")
        ttk.Label(self.win, textvariable=self.v_preview, style="Cut.Title.TLabel").grid(row=7, column=1, padx=10, pady=6, sticky="w")

        ttk.Label(self.win, text="Domyślna długość sztangi [mm]", style="Cut.TLabel").grid(row=8, column=0, padx=10, pady=6, sticky="w")
        ttk.Entry(self.win, textvariable=self.v_len, width=36, style="Cut.TEntry").grid(row=8, column=1, padx=10, pady=6, sticky="ew")

        ttk.Label(self.win, text="Uwagi do surowca", style="Cut.TLabel").grid(row=9, column=0, padx=10, pady=6, sticky="w")
        ttk.Entry(self.win, textvariable=self.v_uwagi, width=36, style="Cut.TEntry").grid(row=9, column=1, padx=10, pady=6, sticky="ew")

        ttk.Checkbutton(self.win, text="Aktywny", variable=self.v_active).grid(row=10, column=1, sticky="w", padx=10)

        for var in (self.v_typ, self.v_a, self.v_b, self.v_c):
            var.trace_add("write", lambda *_: self._update_preview())
        self.cbo_typ.bind("<<ComboboxSelected>>", lambda _e: self._update_preview())
        self._update_preview()

        btns = ttk.Frame(self.win, style="Cut.TFrame")
        btns.grid(row=11, column=0, columnspan=2, pady=(10, 10))
        ttk.Button(btns, text="OK", command=self._ok, style="Cut.Red.TButton").pack(side="left", padx=5)
        ttk.Button(btns, text="Anuluj", command=self.win.destroy, style="Cut.TButton").pack(side="left", padx=5)
        self.win.columnconfigure(1, weight=1)

    def _parse_existing_dims(self, typ: str, rozmiar: str) -> Dict[str, str]:
        typ_norm = str(typ or "").strip().lower()
        text = str(rozmiar or "").strip().lower().replace(" ", "")
        out = {"a": "", "b": "", "c": ""}
        if not text:
            return out

        if typ_norm == "rura":
            text = text.replace("fi", "")
            parts = [p for p in text.split("x") if p]
            if len(parts) >= 1:
                out["a"] = parts[0]
            if len(parts) >= 2:
                out["b"] = parts[1]
            return out

        if typ_norm in ("pret", "pręt"):
            out["a"] = text.replace("fi", "")
            return out

        parts = [p for p in text.split("x") if p]
        if len(parts) >= 1:
            out["a"] = parts[0]
        if len(parts) >= 2:
            out["b"] = parts[1]
        if len(parts) >= 3:
            out["c"] = parts[2]
        return out

    def _dimension_payload(self) -> Dict[str, str]:
        return {
            "a": self.v_a.get().strip(),
            "b": self.v_b.get().strip(),
            "c": self.v_c.get().strip(),
        }

    def _current_size(self) -> str:
        dims = self._dimension_payload()
        return material_size_from_dims(
            self.v_typ.get().strip(),
            dims.get("a", ""),
            dims.get("b", ""),
            dims.get("c", ""),
        )

    def _update_preview(self) -> None:
        typ = self.v_typ.get().strip()
        typ_norm = typ.lower()

        if typ_norm in ("profil", "profil zamknięty", "profil_zamkniety"):
            self.lbl_a.configure(text="A / szerokość profilu")
            self.lbl_b.configure(text="B / wysokość profilu")
            self.lbl_c.configure(text="C / ścianka")
            self.v_hint.set("Profil: A x B x C, np. 40 x 30 x 2")
        elif typ_norm == "rura":
            self.lbl_a.configure(text="A / średnica fi")
            self.lbl_b.configure(text="B / ścianka")
            self.lbl_c.configure(text="C / nieużywane")
            self.v_hint.set("Rura: fi A x B, np. fi30 x 2")
        elif typ_norm in ("pret", "pręt"):
            self.lbl_a.configure(text="A / średnica fi")
            self.lbl_b.configure(text="B / nieużywane")
            self.lbl_c.configure(text="C / nieużywane")
            self.v_hint.set("Pręt: fi A, np. fi12")
        elif typ_norm in ("plaskownik", "płaskownik"):
            self.lbl_a.configure(text="A / szerokość")
            self.lbl_b.configure(text="B / grubość")
            self.lbl_c.configure(text="C / nieużywane")
            self.v_hint.set("Płaskownik: A x B, np. 50 x 5")
        else:
            self.lbl_a.configure(text="A / wymiar 1")
            self.lbl_b.configure(text="B / wymiar 2")
            self.lbl_c.configure(text="C / wymiar 3")
            self.v_hint.set("Własny rodzaj: wpisz potrzebne wymiary A/B/C.")

        size = self._current_size()
        self.v_preview.set(build_material_display_name(typ, size) if size else typ)

    def _ok(self) -> None:
        try:
            typ = self.v_typ.get().strip()
            dims = self._dimension_payload()
            rozmiar = self._current_size()
            display = build_material_display_name(typ, rozmiar)
            if not typ:
                raise ValueError("Rodzaj surowca jest wymagany.")
            if not rozmiar:
                raise ValueError("Wymiary surowca są wymagane.")
            self.result = {
                "material_id": self._material_id,
                "typ": typ,
                "display_name": display,
                "nazwa": display,
                "rozmiar": rozmiar,
                "wymiary": dims,
                "domyslna_dlugosc_mm": parse_length_to_mm(self.v_len.get()),
                "aktywny": bool(self.v_active.get()),
                "uwagi": self.v_uwagi.get().strip(),
            }
        except Exception as exc:
            messagebox.showerror("Surowiec", str(exc))
            return
        self.win.destroy()


class _TransportDialog:
    def __init__(self, parent):
        self.parent = parent
        self.result = None
        self.lines: List[Dict[str, Any]] = []

        self.win = tk.Toplevel(parent)
        self.win.title("Dodaj transport")
        self.win.transient(parent.winfo_toplevel())
        self.win.grab_set()
        _apply_cutting_theme(self.win)
        _setup_dialog_window(self.win, DEFAULT_TRANSPORT_DIALOG_GEOMETRY, (880, 600))

        self.v_transport_id = tk.StringVar(value=next_transport_id())
        self.v_supplier = tk.StringVar(value="")
        self.v_transport_cost = tk.StringVar(value="0")
        self.v_price_mode = tk.StringVar(value=str(parent._settings.get("price_mode", "netto") or "netto"))
        self.v_vat = tk.StringVar(value=str(parent._settings.get("vat_percent", 23) or 23))

        self._material_by_label: Dict[str, Dict[str, Any]] = {}
        self._typ_values = sorted(
            {
                str(m.get("typ", "")).strip()
                for m in parent._materials
                if str(m.get("typ", "")).strip()
            }
        )

        ttk.Label(
            self.win,
            text="Transport / przyjęcie materiału",
            style="Cut.Title.TLabel",
        ).grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 12), sticky="w")

        ttk.Label(self.win, text="Nr transportu", style="Cut.TLabel").grid(
            row=1, column=0, padx=10, pady=6, sticky="w"
        )
        ttk.Entry(
            self.win,
            textvariable=self.v_transport_id,
            width=18,
            style="Cut.TEntry",
            state="readonly",
        ).grid(row=1, column=1, padx=10, pady=6, sticky="w")

        ttk.Label(self.win, text="Firma / dostawca", style="Cut.TLabel").grid(
            row=1, column=2, padx=10, pady=6, sticky="w"
        )
        ttk.Entry(self.win, textvariable=self.v_supplier, width=28, style="Cut.TEntry").grid(
            row=1, column=3, padx=10, pady=6, sticky="ew"
        )

        ttk.Label(self.win, text="Koszt transportu [zł]", style="Cut.TLabel").grid(
            row=2, column=0, padx=10, pady=6, sticky="w"
        )
        ttk.Entry(
            self.win,
            textvariable=self.v_transport_cost,
            width=18,
            style="Cut.TEntry",
        ).grid(row=2, column=1, padx=10, pady=6, sticky="w")

        ttk.Label(self.win, text="Ceny", style="Cut.TLabel").grid(
            row=2, column=2, padx=10, pady=6, sticky="w"
        )
        ttk.Combobox(
            self.win,
            textvariable=self.v_price_mode,
            values=("netto", "brutto"),
            width=10,
            state="readonly",
        ).grid(row=2, column=3, padx=10, pady=6, sticky="w")

        ttk.Label(self.win, text="VAT [%]", style="Cut.TLabel").grid(
            row=3, column=0, padx=10, pady=6, sticky="w"
        )
        ttk.Entry(self.win, textvariable=self.v_vat, width=18, style="Cut.TEntry").grid(
            row=3, column=1, padx=10, pady=6, sticky="w"
        )

        add_box = ttk.Frame(self.win, style="Cut.Panel.TFrame")
        add_box.grid(row=4, column=0, columnspan=4, padx=10, pady=(12, 8), sticky="ew")

        self.v_typ = tk.StringVar(value=self._typ_values[0] if self._typ_values else "")
        self.v_material = tk.StringVar(value="")
        self.v_length = tk.StringVar(value="6000")
        self.v_qty = tk.StringVar(value="1")
        self.v_price = tk.StringVar(value="0")
        self.v_preview = tk.StringVar(value="")

        ttk.Label(add_box, text="Rodzaj", style="Cut.TLabel").grid(
            row=0, column=0, padx=8, pady=6, sticky="w"
        )
        self.cbo_typ = ttk.Combobox(
            add_box,
            textvariable=self.v_typ,
            values=self._typ_values,
            width=14,
            state="readonly",
        )
        self.cbo_typ.grid(row=0, column=1, padx=8, pady=6, sticky="w")

        ttk.Label(add_box, text="Wymiar / surowiec", style="Cut.TLabel").grid(
            row=0, column=2, padx=8, pady=6, sticky="w"
        )
        self.cbo_material = ttk.Combobox(
            add_box,
            textvariable=self.v_material,
            values=(),
            width=34,
            state="readonly",
        )
        self.cbo_material.grid(row=0, column=3, padx=8, pady=6, sticky="ew")

        def _safe_open_material_combo(_event):
            try:
                self.cbo_material.after(10, lambda: self.cbo_material.event_generate("<Alt-Down>"))
            except Exception:
                pass

        self.cbo_material.bind("<Button-1>", _safe_open_material_combo)

        ttk.Label(add_box, text="Długość lagi [mm]", style="Cut.TLabel").grid(
            row=1, column=0, padx=8, pady=6, sticky="w"
        )
        ttk.Entry(add_box, textvariable=self.v_length, width=14, style="Cut.TEntry").grid(
            row=1, column=1, padx=8, pady=6, sticky="w"
        )

        ttk.Label(add_box, text="Ilość lag", style="Cut.TLabel").grid(
            row=1, column=2, padx=8, pady=6, sticky="w"
        )
        ttk.Entry(add_box, textvariable=self.v_qty, width=10, style="Cut.TEntry").grid(
            row=1, column=3, padx=8, pady=6, sticky="w"
        )

        ttk.Label(add_box, text="Cena za metr", style="Cut.TLabel").grid(
            row=2, column=0, padx=8, pady=6, sticky="w"
        )
        ttk.Entry(add_box, textvariable=self.v_price, width=14, style="Cut.TEntry").grid(
            row=2, column=1, padx=8, pady=6, sticky="w"
        )
        ttk.Label(add_box, textvariable=self.v_preview, style="Cut.Muted.TLabel").grid(
            row=2, column=2, columnspan=2, padx=8, pady=6, sticky="w"
        )

        ttk.Button(
            add_box,
            text="+ Dodaj pozycję",
            command=self._add_line,
            style="Cut.Red.TButton",
        ).grid(row=3, column=0, columnspan=2, padx=8, pady=(8, 10), sticky="w")
        ttk.Button(
            add_box,
            text="Usuń pozycję",
            command=self._delete_selected_line,
            style="Cut.TButton",
        ).grid(row=3, column=2, padx=8, pady=(8, 10), sticky="w")

        self.tree = ttk.Treeview(
            self.win,
            columns=("material", "length", "qty", "total", "price", "value"),
            show="headings",
            height=9,
            style="Cut.Treeview",
        )
        self.tree.grid(row=5, column=0, columnspan=4, padx=10, pady=8, sticky="nsew")

        labels = {
            "material": "Surowiec",
            "length": "Laga",
            "qty": "Ilość",
            "total": "Razem",
            "price": "Cena/mb",
            "value": "Wartość",
        }
        widths = {
            "material": 220,
            "length": 95,
            "qty": 70,
            "total": 110,
            "price": 90,
            "value": 100,
        }
        for col in ("material", "length", "qty", "total", "price", "value"):
            self.tree.heading(col, text=labels[col])
            self.tree.column(col, width=widths[col], anchor="w")

        self.v_summary = tk.StringVar(value="Razem: 0 mb | netto 0 zł | brutto 0 zł")
        ttk.Label(self.win, textvariable=self.v_summary, style="Cut.Title.TLabel").grid(
            row=6, column=0, columnspan=4, padx=10, pady=(6, 10), sticky="w"
        )

        buttons = ttk.Frame(self.win, style="Cut.TFrame")
        buttons.grid(row=7, column=0, columnspan=4, pady=(8, 12))
        ttk.Button(
            buttons,
            text="ZAPISZ TRANSPORT",
            command=self._ok,
            style="Cut.Red.TButton",
        ).pack(side="left", padx=5)
        ttk.Button(buttons, text="Anuluj", command=self.win.destroy, style="Cut.TButton").pack(
            side="left", padx=5
        )

        self.cbo_typ.bind("<<ComboboxSelected>>", lambda _e: self._refresh_material_options())
        for var in (self.v_length, self.v_qty, self.v_price):
            var.trace_add("write", lambda *_: self._update_line_preview())

        self._refresh_material_options()
        self._update_line_preview()
        self.win.columnconfigure(3, weight=1)
        self.win.rowconfigure(5, weight=1)

    def _refresh_material_options(self) -> None:
        typ = self.v_typ.get().strip()
        labels: List[str] = []
        self._material_by_label = {}
        for m in self.parent._materials:
            if str(m.get("typ", "")).strip() != typ:
                continue
            label = str(m.get("display_name") or m.get("nazwa") or m.get("material_id"))
            labels.append(label)
            self._material_by_label[label] = m
        self.cbo_material.configure(values=labels)
        self.v_material.set(labels[0] if labels else "")
        self._update_line_preview()

    def _numbers(self) -> tuple[float, int, float]:
        length = parse_length_to_mm(self.v_length.get())
        qty = int(self.v_qty.get() or 0)
        price = float(str(self.v_price.get() or "0").replace(",", "."))
        return length, qty, price

    def _update_line_preview(self) -> None:
        try:
            length, qty, price = self._numbers()
            total_mm = length * qty
            total_m = total_mm / 1000.0
            value = total_m * price
            self.v_preview.set(f"{length:g} mm × {qty} = {total_mm:g} mm ({total_m:g} mb) | {value:.2f} zł")
        except Exception:
            self.v_preview.set("")

    def _line_totals_for_display(self, total_m: float, price: float) -> tuple[float, float]:
        mode = self.v_price_mode.get().strip().lower()
        try:
            vat = float(str(self.v_vat.get() or "0").replace(",", "."))
        except Exception:
            vat = 0.0
        value = round(total_m * price, 2)
        if mode == "brutto":
            gross = value
            net = round(value / (1.0 + vat / 100.0), 2) if vat else value
        else:
            net = value
            gross = round(value * (1.0 + vat / 100.0), 2)
        return net, gross

    def _add_line(self) -> None:
        material_label_txt = self.v_material.get().strip()
        material = self._material_by_label.get(material_label_txt)
        if not material:
            messagebox.showwarning("Transport", "Wybierz surowiec z listy.")
            return
        try:
            length, qty, price = self._numbers()
            if length <= 0:
                raise ValueError("Długość lagi musi być > 0.")
            if qty <= 0:
                raise ValueError("Ilość lag musi być > 0.")
            if price < 0:
                raise ValueError("Cena za metr nie może być ujemna.")
        except Exception as exc:
            messagebox.showerror("Transport", str(exc))
            return

        total_mm = length * qty
        total_m = total_mm / 1000.0
        net, gross = self._line_totals_for_display(total_m, price)
        line = {
            "material_id": material.get("material_id"),
            "material_display": material_label_txt,
            "bar_length_mm": length,
            "qty": qty,
            "price_per_m": price,
            "total_length_mm": total_mm,
            "total_length_m": total_m,
            "line_total_net": net,
            "line_total_gross": gross,
        }
        self.lines.append(line)
        self.tree.insert(
            "",
            "end",
            values=(
                material_label_txt,
                f"{length:g} mm",
                str(qty),
                f"{total_m:g} mb",
                f"{price:.2f}",
                f"{net:.2f} / {gross:.2f}",
            ),
        )
        self._refresh_summary()

    def _delete_selected_line(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        all_iids = list(self.tree.get_children())
        idx = all_iids.index(sel[0])
        self.tree.delete(sel[0])
        if 0 <= idx < len(self.lines):
            self.lines.pop(idx)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        total_m = sum(float(line.get("total_length_m", 0) or 0) for line in self.lines)
        net = sum(float(line.get("line_total_net", 0) or 0) for line in self.lines)
        gross = sum(float(line.get("line_total_gross", 0) or 0) for line in self.lines)
        try:
            transport_cost = float(str(self.v_transport_cost.get() or "0").replace(",", "."))
        except Exception:
            transport_cost = 0.0
        self.v_summary.set(
            f"Razem: {total_m:g} mb | netto {net:.2f} zł | brutto {gross:.2f} zł | transport {transport_cost:.2f} zł"
        )

    def _ok(self) -> None:
        if not self.lines:
            messagebox.showwarning("Transport", "Dodaj przynajmniej jedną pozycję transportu.")
            return
        try:
            transport_cost = float(str(self.v_transport_cost.get() or "0").replace(",", "."))
            vat = float(str(self.v_vat.get() or "23").replace(",", "."))
        except Exception:
            messagebox.showerror("Transport", "Koszt transportu i VAT muszą być liczbami.")
            return

        self.result = {
            "supplier": self.v_supplier.get().strip(),
            "transport_cost": transport_cost,
            "price_mode": self.v_price_mode.get().strip().lower() or "netto",
            "vat_percent": vat,
            "lines": list(self.lines),
        }
        update_cutting_setting("price_mode", self.result["price_mode"])
        update_cutting_setting("vat_percent", vat)
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
        _setup_dialog_window(self.win, "620x430", (560, 380))

        self.parent = parent
        last_len = float(getattr(parent, "_last_cut_length_mm", DEFAULT_CUT_LENGTH_MM) or DEFAULT_CUT_LENGTH_MM)
        last_ang_l = float(getattr(parent, "_last_cut_angle_left", DEFAULT_CUT_ANGLE_LEFT) or DEFAULT_CUT_ANGLE_LEFT)
        last_ang_r = float(getattr(parent, "_last_cut_angle_right", DEFAULT_CUT_ANGLE_RIGHT) or DEFAULT_CUT_ANGLE_RIGHT)
        self.v_material = tk.StringVar(value=str(row.get("material_id", parent._selected_material_id() if hasattr(parent, "_selected_material_id") else "")))
        self.v_length = tk.StringVar(value=str(_fmt_num(row.get("length_mm", last_len))))
        self.v_angle_l = tk.StringVar(value=str(_fmt_num(row.get("angle_left", last_ang_l))))
        self.v_angle_r = tk.StringVar(value=str(_fmt_num(row.get("angle_right", last_ang_r))))
        self.v_qty = tk.StringVar(value=str(row.get("qty", "1")))
        self.v_label = tk.StringVar(value=str(row.get("label", "")))

        def _open_combobox_safely(combo: ttk.Combobox) -> None:
            """Bezpiecznie otwiera listę ttk.Combobox bez generowania eventów klawiatury.

            Nie używamy event_generate("<Down>") ani event_generate("<Alt-Down>"),
            bo na Windows/Tk potrafi to wywołać cichy błąd bez tracebacka.
            """
            try:
                combo.tk.call("ttk::combobox::Post", str(combo))
            except Exception:
                pass

        material_values = []
        if hasattr(parent, "_materials"):
            material_values = [material_label(m) for m in parent._materials]
        self._label_to_id = parent._material_label_to_id if hasattr(parent, "_material_label_to_id") else {}

        ttk.Label(self.win, text="Surowiec", style="Cut.TLabel").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        material_pick = ttk.Frame(self.win, style="Cut.TFrame")
        material_pick.grid(row=0, column=1, padx=10, pady=6, sticky="ew")
        material_pick.columnconfigure(0, weight=1)
        self.cbo_material = ttk.Combobox(
            material_pick,
            values=material_values,
            width=42,
            state="readonly",
        )
        self.cbo_material.set(self.v_material.get())
        self.cbo_material.grid(row=0, column=0, sticky="ew")
        for label, mid in self._label_to_id.items():
            if mid == self.v_material.get():
                self.cbo_material.set(label)
                break
        # Nie bindować FocusIn/Button-1 do event_generate.
        # Native readonly combobox jest stabilniejszy; dodatkowy przycisk tylko otwiera listę.
        ttk.Button(
            material_pick,
            text="▼",
            width=3,
            command=lambda: _open_combobox_safely(self.cbo_material),
            style="Cut.TButton",
        ).grid(row=0, column=1, padx=(4, 0), sticky="e")

        fields = [
            ("Długość [mm]", self.v_length),
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
        ttk.Label(
            self.win,
            text=(
                "Podpowiedź: długość i kąty startują z ostatnio dodanej pozycji. "
                "Możesz zostawić puste, wtedy zostaną użyte ostatnie wartości."
            ),
            style="Cut.Muted.TLabel",
            wraplength=420,
        ).grid(row=len(fields) + 2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="w")

    def _ok(self) -> None:
        try:
            material = self.cbo_material.get().strip()
            material = self._label_to_id.get(material, material)
            length_raw = self.v_length.get().strip()
            angle_l_raw = self.v_angle_l.get().strip()
            angle_r_raw = self.v_angle_r.get().strip()

            last_len = float(getattr(self.parent, "_last_cut_length_mm", DEFAULT_CUT_LENGTH_MM) or DEFAULT_CUT_LENGTH_MM)
            last_ang_l = float(getattr(self.parent, "_last_cut_angle_left", DEFAULT_CUT_ANGLE_LEFT) or DEFAULT_CUT_ANGLE_LEFT)
            last_ang_r = float(getattr(self.parent, "_last_cut_angle_right", DEFAULT_CUT_ANGLE_RIGHT) or DEFAULT_CUT_ANGLE_RIGHT)
            self.result = {
                "material_id": material,
                "length_mm": parse_length_to_mm(length_raw) if length_raw else last_len,
                "angle_left": validate_saw_angle(float(angle_l_raw.replace(",", "."))) if angle_l_raw else last_ang_l,
                "angle_right": validate_saw_angle(float(angle_r_raw.replace(",", "."))) if angle_r_raw else last_ang_r,
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
    _setup_window_geometry(root)
    _apply_cutting_theme(root)
    frame = CuttingFrame(root)
    frame.pack(fill="both", expand=True)
    root.mainloop()

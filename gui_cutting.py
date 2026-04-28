from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

from core.cutting_models import CutItem
from core.cutting_optimizer import optimize_cutting
from core.cutting_storage import (
    add_stock_bar,
    get_cutting_debug_paths,
    load_stock_bars,
    save_cut_result,
    save_cut_job,
)

CUT_COLUMNS = ("material", "length", "angle_l", "angle_r", "qty", "label")
RESULT_COLUMNS = ("bar", "source", "cuts", "waste", "usage")

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
    -45   -> \
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
    return f"{_cut_mark(float(angle_l or 0), 'L')}{_fmt_num(length)}{_cut_mark(float(angle_r or 0), 'R')}"


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
        self._build_ui()
        self._refresh_stock_info()

    def _build_ui(self) -> None:
        header = ttk.Frame(self, style="Cut.TFrame")
        header.pack(fill="x", pady=(0, 10))

        ttk.Label(header, text="ROZKRÓJ / CIĘCIE", style="Cut.Title.TLabel").pack(side="left", padx=(0, 18))

        ttk.Label(header, text="Zlecenie:", style="Cut.TLabel").pack(side="left")
        self.var_job = tk.StringVar(value="ROZKROJ-TEST")
        ttk.Entry(header, textvariable=self.var_job, width=24, style="Cut.TEntry").pack(side="left", padx=(5, 14))

        ttk.Label(header, text="Rzaz [mm]:", style="Cut.TLabel").pack(side="left")
        self.var_kerf = tk.StringVar(value="2.5")
        ttk.Entry(header, textvariable=self.var_kerf, width=8, style="Cut.TEntry").pack(side="left", padx=(5, 14))

        ttk.Label(header, text="Min. odpad [mm]:", style="Cut.TLabel").pack(side="left")
        self.var_min_offcut = tk.StringVar(value="300")
        ttk.Entry(header, textvariable=self.var_min_offcut, width=9, style="Cut.TEntry").pack(side="left", padx=(5, 14))

        ttk.Button(header, text="Ścieżki", command=self._show_paths, style="Cut.TButton").pack(side="right")

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main, padding=(0, 0, 10, 0), style="Cut.TFrame")
        right = ttk.Frame(main, padding=(10, 0, 0, 0), style="Cut.TFrame")
        main.add(left, weight=1)
        main.add(right, weight=2)

        self._build_cut_list(left)
        self._build_result_and_preview(right)
        self._build_footer()

    def _panel_title(self, parent, text: str) -> None:
        box = ttk.Frame(parent, style="Cut.Panel.TFrame")
        box.pack(fill="x", pady=(0, 6))
        ttk.Label(box, text=text, style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)

    def _build_cut_list(self, parent) -> None:
        top = ttk.Frame(parent, style="Cut.Panel.TFrame")
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Lista do cięcia", style="Cut.Subtitle.TLabel").pack(side="left", padx=10, pady=8)

        ttk.Button(top, text="+ Dodaj", command=self._add_cut_row_dialog, style="Cut.Red.TButton").pack(side="right", padx=(6, 8))
        ttk.Button(top, text="Usuń", command=self._delete_selected_cut, style="Cut.TButton").pack(side="right")

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
            "  |1500|  = cięcie proste 0° / 0°\n"
            "  /1500\\ = lewy +45°, prawy -45°\n"
            "  \\1500/ = lewy -45°, prawy +45°\n\n"
            "Na tym etapie długość = wymiar do odmierzenia na pile.\n"
            "Kąty są pokazane dla operatora i podglądu.",
        )
        helper.configure(state="disabled")

        self._insert_cut_row("profil_40x40x2", 1500, 45, -45, 3, "przykład ramy")
        self._insert_cut_row("profil_40x40x2", 850, 0, 0, 2, "poprzeczka")

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

    def _build_footer(self) -> None:
        footer = ttk.Frame(self, style="Cut.TFrame")
        footer.pack(fill="x", pady=(10, 0))

        self.var_stock_info = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.var_stock_info, style="Cut.TLabel").pack(side="left")

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
                f"{float(length_mm):g}",
                f"{float(angle_left):g}",
                f"{float(angle_right):g}",
                str(int(qty)),
                label,
            ),
        )

    def _read_cut_items(self) -> List[CutItem]:
        items: List[CutItem] = []
        for iid in self.tree_cuts.get_children():
            values = self.tree_cuts.item(iid, "values")
            try:
                items.append(
                    CutItem(
                        material_id=str(values[0]).strip(),
                        length_mm=float(str(values[1]).replace(",", ".")),
                        angle_left=float(str(values[2]).replace(",", ".")),
                        angle_right=float(str(values[3]).replace(",", ".")),
                        qty=int(values[4]),
                        label=str(values[5]).strip(),
                    )
                )
            except Exception:
                continue
        return items

    def _calculate(self) -> None:
        items = self._read_cut_items()
        if not items:
            messagebox.showwarning("Rozkrój", "Brak poprawnych pozycji do cięcia.")
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

        result = optimize_cutting(
            job_id=self.var_job.get().strip() or "ROZKROJ",
            items=items,
            stock_bars=stock,
            saw_kerf_mm=saw_kerf,
            min_reusable_offcut_mm=min_offcut,
        )
        self._last_result = result
        self._last_result_dict = result.to_dict()
        self._render_result(self._last_result_dict)

        payload = {
            "job_id": self.var_job.get().strip() or "ROZKROJ",
            "saw_kerf_mm": saw_kerf,
            "min_reusable_offcut_mm": min_offcut,
            "items": [item.to_dict() for item in items],
        }
        try:
            save_cut_job(payload["job_id"], payload)
        except Exception:
            pass

    def _render_result(self, data: Dict[str, Any]) -> None:
        for iid in self.tree_result.get_children():
            self.tree_result.delete(iid)

        for idx, bar in enumerate(data.get("bars_used", []), start=1):
            cuts_txt = self._bar_cuts_text(bar)
            used = float(bar.get("used_mm", 0) or 0)
            length = float(bar.get("bar_length_mm", 0) or 0)
            usage = f"{(used / length * 100):.1f}%" if length else "-"
            self.tree_result.insert(
                "",
                "end",
                values=(
                    f'{idx}. {bar.get("material_id", "")} / {length:g} mm',
                    bar.get("source", ""),
                    cuts_txt,
                    f'{float(bar.get("waste_mm", 0) or 0):g} mm',
                    usage,
                ),
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
            chunks.append(f"odpad {waste:g}")
        return " -- ".join(chunks)

    def _render_summary(self, data: Dict[str, Any]) -> None:
        summary = data.get("summary", {})
        missing = data.get("missing", [])
        lines = [
            "PODSUMOWANIE",
            "------------",
            f"Sztang użytych:       {summary.get('bars_count', 0)}",
            f"Materiał łącznie:     {summary.get('total_length_mm', 0)} mm",
            f"Zużycie:              {summary.get('total_used_mm', 0)} mm",
            f"Odpad:                {summary.get('total_waste_mm', 0)} mm",
            f"Wykorzystanie:        {summary.get('usage_percent', 0)}%",
        ]
        if missing:
            lines.append("")
            lines.append("BRAKI")
            lines.append("-----")
            for row in missing:
                lines.append(
                    f"- {row.get('material_id')} / {row.get('length_mm')} mm / {row.get('label', '')}"
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

            label = f'{idx}. {bar.get("material_id", "")} / {bar_len:g} mm'
            self.canvas.create_text(10, y + 24, text=label, anchor="w", fill=TEXT, font=("Segoe UI", 9, "bold"))

            self.canvas.create_rectangle(x0, bar_y0, x1, bar_y1, fill="#1A1A22", outline=GRID)

            cursor = x0
            cuts = bar.get("cuts", [])
            kerf = float(data.get("saw_kerf_mm", 0) or 0)

            for cut_idx, cut in enumerate(cuts):
                length = float(cut.get("length_mm", 0) or 0)
                seg_w = max(2, usable_w * length / bar_len)
                seg_x0 = cursor
                seg_x1 = min(x1, cursor + seg_w)

                self.canvas.create_rectangle(seg_x0, bar_y0, seg_x1, bar_y1, fill="#2A1016", outline=RED)
                self._draw_angle_mark(seg_x0, bar_y0, bar_y1, float(cut.get("angle_left", 0) or 0), left_side=True)
                self._draw_angle_mark(seg_x1, bar_y0, bar_y1, float(cut.get("angle_right", 0) or 0), left_side=False)

                text = _cut_text(length, cut.get("angle_left", 0), cut.get("angle_right", 0))
                if seg_w > 45:
                    self.canvas.create_text(
                        (seg_x0 + seg_x1) / 2,
                        bar_y0 - 8,
                        text=text,
                        fill=TEXT,
                        font=("Consolas", 9, "bold"),
                    )

                # Rzaz jako czerwona kreska między detalami.
                cursor = seg_x1
                if cut_idx < len(cuts) - 1 and kerf > 0:
                    kerf_w = max(2, usable_w * kerf / bar_len)
                    self.canvas.create_rectangle(cursor, bar_y0 - 3, cursor + kerf_w, bar_y1 + 3, fill=RED_HOT, outline=RED_HOT)
                    cursor += kerf_w

            waste = float(bar.get("waste_mm", 0) or 0)
            if waste > 0:
                waste_x0 = max(cursor, x0)
                self.canvas.create_rectangle(waste_x0, bar_y0, x1, bar_y1, fill="#202026", outline=GRID)
                if x1 - waste_x0 > 55:
                    self.canvas.create_text(
                        (waste_x0 + x1) / 2,
                        bar_y1 + 13,
                        text=f"odpad {waste:g} mm",
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
        Kąt dodatni/ujemny jako ukośnik.
        """
        if abs(angle) < 0.001:
            self.canvas.create_line(x, y0 - 4, x, y1 + 4, fill=TEXT, width=2)
            return

        if angle > 0:
            self.canvas.create_line(x - 8, y1 + 5, x + 8, y0 - 5, fill=RED_HOT, width=3)
        else:
            self.canvas.create_line(x - 8, y0 - 5, x + 8, y1 + 5, fill=RED_HOT, width=3)

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
            by_len.setdefault(bar.material_id, []).append(f"{bar.length_mm:g}mm x{bar.qty}")

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

    def _add_cut_row_dialog(self) -> None:
        dialog = _CutRowDialog(self)
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

    def _show_paths(self) -> None:
        paths = get_cutting_debug_paths()
        messagebox.showinfo(
            "Ścieżki rozkroju",
            "\n".join([f"{key}: {value}" for key, value in paths.items()]),
        )


class _CutRowDialog:
    def __init__(self, parent):
        self.result = None
        self.win = tk.Toplevel(parent)
        self.win.title("Dodaj pozycję cięcia")
        self.win.transient(parent.winfo_toplevel())
        self.win.grab_set()
        _apply_cutting_theme(self.win)

        self.v_material = tk.StringVar(value="profil_40x40x2")
        self.v_length = tk.StringVar(value="1500")
        self.v_angle_l = tk.StringVar(value="45")
        self.v_angle_r = tk.StringVar(value="-45")
        self.v_qty = tk.StringVar(value="1")
        self.v_label = tk.StringVar(value="")

        fields = [
            ("Materiał ID", self.v_material),
            ("Długość [mm]", self.v_length),
            ("Kąt L", self.v_angle_l),
            ("Kąt P", self.v_angle_r),
            ("Ilość", self.v_qty),
            ("Opis", self.v_label),
        ]
        for row, (label, var) in enumerate(fields):
            ttk.Label(self.win, text=label, style="Cut.TLabel").grid(row=row, column=0, padx=10, pady=6, sticky="w")
            ttk.Entry(self.win, textvariable=var, width=30, style="Cut.TEntry").grid(row=row, column=1, padx=10, pady=6, sticky="ew")

        btns = ttk.Frame(self.win, style="Cut.TFrame")
        btns.grid(row=len(fields), column=0, columnspan=2, pady=(10, 10))
        ttk.Button(btns, text="OK", command=self._ok, style="Cut.Red.TButton").pack(side="left", padx=5)
        ttk.Button(btns, text="Anuluj", command=self.win.destroy, style="Cut.TButton").pack(side="left", padx=5)

    def _ok(self) -> None:
        try:
            self.result = {
                "material_id": self.v_material.get().strip(),
                "length_mm": float(self.v_length.get().replace(",", ".")),
                "angle_left": float(self.v_angle_l.get().replace(",", ".")),
                "angle_right": float(self.v_angle_r.get().replace(",", ".")),
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
        self.v_length = tk.StringVar(value="6000")
        self.v_qty = tk.StringVar(value="1")
        self.v_location = tk.StringVar(value="")

        fields = [
            ("Materiał ID", self.v_material),
            ("Nazwa", self.v_name),
            ("Długość sztangi [mm]", self.v_length),
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
                "length_mm": float(self.v_length.get().replace(",", ".")),
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
        self.win.title("Rozkrój / cięcie")
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
            container.add(frame, text="Rozkrój")
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
    root.title("Rozkrój / cięcie")
    root.geometry("1400x850")
    _apply_cutting_theme(root)
    try:
        root.state("zoomed")
    except Exception:
        pass
    frame = CuttingFrame(root)
    frame.pack(fill="both", expand=True)
    root.mainloop()

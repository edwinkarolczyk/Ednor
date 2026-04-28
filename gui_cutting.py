# Plik: gui_cutting.py
# Wersja: 0.1.0
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

try:
    from ui_theme import apply_theme_safe as apply_theme
except Exception:  # pragma: no cover

    def apply_theme(_widget):
        return None


CUT_COLUMNS = ("material", "length", "angle_l", "angle_r", "qty", "label")
RESULT_COLUMNS = ("bar", "source", "cuts", "waste", "usage")


class CuttingFrame(ttk.Frame):
    """Panel rozkroju profili/sztang/prętów.

    Wersja 0.1:
    - ręczne wpisywanie listy cięcia,
    - ręczne dodawanie sztang do pliku stock_bars.json,
    - optymalizacja best-fit,
    - zapis job/result do ROOT/data/rozkrój.
    """

    def __init__(self, master, config: Optional[Dict[str, Any]] = None):
        super().__init__(master, padding=(8, 8, 8, 8), style="WM.TFrame")
        self.config_obj = config or {}
        self._last_result = None
        self._build_ui()
        self._refresh_stock_info()

    def _build_ui(self) -> None:
        header = ttk.Frame(self, style="WM.TFrame")
        header.pack(fill="x", pady=(0, 8))

        ttk.Label(header, text="Rozkrój / cięcie", style="WM.TLabel").pack(
            side="left", padx=(0, 12)
        )

        ttk.Label(header, text="Zlecenie:", style="WM.TLabel").pack(side="left")
        self.var_job = tk.StringVar(value="ROZKROJ-TEST")
        ttk.Entry(header, textvariable=self.var_job, width=22).pack(
            side="left", padx=(4, 12)
        )

        ttk.Label(header, text="Rzaz piły [mm]:", style="WM.TLabel").pack(side="left")
        self.var_kerf = tk.StringVar(value="2.5")
        ttk.Entry(header, textvariable=self.var_kerf, width=7).pack(
            side="left", padx=(4, 12)
        )

        ttk.Label(header, text="Min. odpad [mm]:", style="WM.TLabel").pack(side="left")
        self.var_min_offcut = tk.StringVar(value="300")
        ttk.Entry(header, textvariable=self.var_min_offcut, width=8).pack(
            side="left", padx=(4, 12)
        )

        ttk.Button(
            header,
            text="Ścieżki",
            command=self._show_paths,
            style="WM.Side.TButton",
        ).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, padding=(0, 0, 8, 0), style="WM.TFrame")
        right = ttk.Frame(body, padding=(8, 0, 0, 0), style="WM.TFrame")
        body.add(left, weight=1)
        body.add(right, weight=1)

        self._build_cut_list(left)
        self._build_result(right)
        self._build_footer()

    def _build_cut_list(self, parent) -> None:
        top = ttk.Frame(parent, style="WM.TFrame")
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Lista do cięcia", style="WM.TLabel").pack(side="left")

        ttk.Button(
            top,
            text="Dodaj pozycję",
            command=self._add_cut_row_dialog,
            style="WM.Side.TButton",
        ).pack(side="right")
        ttk.Button(
            top,
            text="Usuń",
            command=self._delete_selected_cut,
            style="WM.Side.TButton",
        ).pack(side="right", padx=(0, 6))

        self.tree_cuts = ttk.Treeview(
            parent,
            columns=CUT_COLUMNS,
            show="headings",
            selectmode="browse",
            height=18,
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
            "material": 150,
            "length": 90,
            "angle_l": 70,
            "angle_r": 70,
            "qty": 60,
            "label": 180,
        }
        for col in CUT_COLUMNS:
            self.tree_cuts.heading(col, text=labels[col])
            self.tree_cuts.column(col, width=widths[col], anchor="w")

        # Przykład na start, żeby ekran nie wyglądał jak świeżo wyczyszczony stół.
        self._insert_cut_row("profil_40x40x2", 500, 45, -45, 2, "rama krótka")
        self._insert_cut_row("profil_40x40x2", 1000, 45, -45, 2, "rama długa")

    def _build_result(self, parent) -> None:
        top = ttk.Frame(parent, style="WM.TFrame")
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Wynik optymalizacji", style="WM.TLabel").pack(side="left")

        ttk.Button(
            top,
            text="Oblicz",
            command=self._calculate,
            style="WM.Side.TButton",
        ).pack(side="right")
        ttk.Button(
            top,
            text="Zapisz wynik",
            command=self._save_last_result,
            style="WM.Side.TButton",
        ).pack(side="right", padx=(0, 6))

        self.tree_result = ttk.Treeview(
            parent,
            columns=RESULT_COLUMNS,
            show="headings",
            selectmode="browse",
            height=18,
        )
        self.tree_result.pack(fill="both", expand=True)

        labels = {
            "bar": "Sztanga",
            "source": "Źródło",
            "cuts": "Cięcia",
            "waste": "Odpad",
            "usage": "Użycie",
        }
        widths = {
            "bar": 130,
            "source": 80,
            "cuts": 360,
            "waste": 90,
            "usage": 80,
        }
        for col in RESULT_COLUMNS:
            self.tree_result.heading(col, text=labels[col])
            self.tree_result.column(col, width=widths[col], anchor="w")

        self.txt_summary = tk.Text(parent, height=7, wrap="word")
        self.txt_summary.pack(fill="x", pady=(8, 0))

    def _build_footer(self) -> None:
        footer = ttk.Frame(self, style="WM.TFrame")
        footer.pack(fill="x", pady=(8, 0))

        self.var_stock_info = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.var_stock_info, style="WM.TLabel").pack(
            side="left"
        )

        ttk.Button(
            footer,
            text="Dodaj sztangę do stock_bars",
            command=self._add_stock_bar_dialog,
            style="WM.Side.TButton",
        ).pack(side="right")

        ttk.Button(
            footer,
            text="Odśwież stan",
            command=self._refresh_stock_info,
            style="WM.Side.TButton",
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
                        length_mm=float(values[1]),
                        angle_left=float(values[2]),
                        angle_right=float(values[3]),
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
        self._render_result(result.to_dict())

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
            cuts_txt = " | ".join(
                [
                    f'{cut.get("length_mm"):g} ({cut.get("angle_left"):g}/{cut.get("angle_right"):g}) {cut.get("label", "")}'.strip()
                    for cut in bar.get("cuts", [])
                ]
            )
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

        summary = data.get("summary", {})
        missing = data.get("missing", [])
        lines = [
            f"Sztang użytych: {summary.get('bars_count', 0)}",
            f"Materiał łącznie: {summary.get('total_length_mm', 0)} mm",
            f"Zużycie: {summary.get('total_used_mm', 0)} mm",
            f"Odpad: {summary.get('total_waste_mm', 0)} mm",
            f"Wykorzystanie: {summary.get('usage_percent', 0)}%",
        ]
        if missing:
            lines.append("")
            lines.append("BRAKI:")
            for row in missing:
                lines.append(
                    f"- {row.get('material_id')} / {row.get('length_mm')} mm / {row.get('label', '')}"
                )

        self.txt_summary.delete("1.0", "end")
        self.txt_summary.insert("1.0", "\n".join(lines))

    def _save_last_result(self) -> None:
        if self._last_result is None:
            messagebox.showwarning("Rozkrój", "Najpierw kliknij Oblicz.")
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
        for bar in stock:
            by_mat[bar.material_id] = by_mat.get(bar.material_id, 0) + int(bar.qty)
        if not by_mat:
            self.var_stock_info.set("Brak danych stock_bars.json")
            return
        txt = " | ".join([f"{mat}: {qty} szt." for mat, qty in sorted(by_mat.items())])
        self.var_stock_info.set(txt)

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
        apply_theme(self.win)

        self.v_material = tk.StringVar(value="profil_40x40x2")
        self.v_length = tk.StringVar(value="1000")
        self.v_angle_l = tk.StringVar(value="0")
        self.v_angle_r = tk.StringVar(value="0")
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
            ttk.Label(self.win, text=label).grid(row=row, column=0, padx=8, pady=5, sticky="w")
            ttk.Entry(self.win, textvariable=var, width=28).grid(
                row=row, column=1, padx=8, pady=5, sticky="ew"
            )

        btns = ttk.Frame(self.win)
        btns.grid(row=len(fields), column=0, columnspan=2, pady=(8, 8))
        ttk.Button(btns, text="OK", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Anuluj", command=self.win.destroy).pack(side="left", padx=4)

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
        apply_theme(self.win)

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
            ttk.Label(self.win, text=label).grid(row=row, column=0, padx=8, pady=5, sticky="w")
            ttk.Entry(self.win, textvariable=var, width=30).grid(
                row=row, column=1, padx=8, pady=5, sticky="ew"
            )

        btns = ttk.Frame(self.win)
        btns.grid(row=len(fields), column=0, columnspan=2, pady=(8, 8))
        ttk.Button(btns, text="OK", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Anuluj", command=self.win.destroy).pack(side="left", padx=4)

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
        self.win.geometry("1180x720")
        self.win.minsize(980, 560)
        apply_theme(self.win)
        frame = CuttingFrame(self.win, config=config or {})
        frame.pack(fill="both", expand=True)
        self.win.transient(master)


def open_window(parent, config=None, *args, **kwargs):
    return CuttingWindow(parent, config=config or {})


def open_panel_cutting(parent, root=None, app=None, notebook=None, *args, **kwargs):
    """Publiczne API podobne do innych modułów WM.

    Można osadzić w kontenerze albo otworzyć jako panel w notebooku.
    """

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
    root.title("Test Rozkrój")
    root.geometry("1180x720")
    frame = CuttingFrame(root)
    frame.pack(fill="both", expand=True)
    root.mainloop()

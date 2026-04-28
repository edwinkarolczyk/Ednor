# Plik: core/cutting_optimizer.py
# Wersja: 0.1.0
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from core.cutting_models import (
    CutItem,
    CuttingResult,
    PlannedCut,
    StockBar,
    UsedBar,
    expand_cut_items,
)


def _expanded_bars(stock_bars: Iterable[StockBar]) -> List[StockBar]:
    out: List[StockBar] = []
    for bar in stock_bars:
        if not bar.material_id or bar.length_mm <= 0:
            continue
        qty = max(0, int(bar.qty))
        for idx in range(qty):
            out.append(
                StockBar(
                    material_id=bar.material_id,
                    length_mm=float(bar.length_mm),
                    qty=1,
                    source=bar.source,
                    id=bar.id or f"{bar.material_id}_{bar.length_mm:g}_{idx + 1}",
                    name=bar.name,
                    location=bar.location,
                )
            )

    # Najpierw odpady, potem pełne sztangi, w ramach grupy krótsze przed dłuższymi.
    # Dzięki temu program naturalnie zjada resztki, zanim ruszy pełną sztangę.
    out.sort(key=lambda b: (0 if b.source == "offcut" else 1, b.length_mm))
    return out


def _cut_cost(cuts_count_before: int, saw_kerf_mm: float) -> float:
    """Rzaz między kolejnymi detalami.

    Uproszczenie warsztatowe:
    - pierwszy detal na sztandze nie dodaje rzazu przed sobą,
    - każdy kolejny detal dodaje saw_kerf_mm.
    """

    return saw_kerf_mm if cuts_count_before > 0 else 0.0


def _remaining_after_add(bar: UsedBar, item: CutItem, saw_kerf_mm: float) -> float:
    extra = item.length_mm + _cut_cost(len(bar.cuts), saw_kerf_mm)
    return bar.bar_length_mm - bar.used_mm - extra


def _add_cut_to_bar(bar: UsedBar, item: CutItem, saw_kerf_mm: float) -> None:
    extra = item.length_mm + _cut_cost(len(bar.cuts), saw_kerf_mm)
    bar.cuts.append(PlannedCut.from_item(item))
    bar.used_mm = round(bar.used_mm + extra, 3)
    bar.waste_mm = round(max(0.0, bar.bar_length_mm - bar.used_mm), 3)


def _material_groups(items: List[CutItem]) -> Dict[str, List[CutItem]]:
    grouped: Dict[str, List[CutItem]] = defaultdict(list)
    for item in items:
        grouped[item.material_id].append(item)
    return dict(grouped)


def optimize_cutting(
    *,
    job_id: str,
    items: List[CutItem],
    stock_bars: List[StockBar],
    saw_kerf_mm: float = 2.5,
    min_reusable_offcut_mm: float = 300.0,
) -> CuttingResult:
    """Optymalizacja rozkroju metodą best-fit decreasing.

    To nie jest solver matematyczny typu MILP, tylko szybki algorytm warsztatowy:
    - sortuje detale od najdłuższych,
    - najpierw próbuje dopchać istniejące otwarte sztangi,
    - jeśli nie pasuje, bierze kolejną sztangę z magazynu,
    - preferuje odpady użytkowe przed pełnymi sztangami.
    """

    saw_kerf_mm = max(0.0, float(saw_kerf_mm or 0))
    min_reusable_offcut_mm = max(0.0, float(min_reusable_offcut_mm or 0))

    result = CuttingResult(
        job_id=job_id,
        saw_kerf_mm=saw_kerf_mm,
        min_reusable_offcut_mm=min_reusable_offcut_mm,
    )

    expanded_items = expand_cut_items(items)
    grouped_items = _material_groups(expanded_items)

    available_by_material: Dict[str, List[StockBar]] = defaultdict(list)
    for bar in _expanded_bars(stock_bars):
        available_by_material[bar.material_id].append(bar)

    for material_id, mat_items in grouped_items.items():
        open_bars: List[UsedBar] = []
        available = available_by_material.get(material_id, [])

        for item in mat_items:
            best_idx = -1
            best_remaining = None

            # 1. Spróbuj dołożyć do już otwartych sztang.
            for idx, used_bar in enumerate(open_bars):
                remaining = _remaining_after_add(used_bar, item, saw_kerf_mm)
                if remaining < -0.0001:
                    continue
                if best_remaining is None or remaining < best_remaining:
                    best_idx = idx
                    best_remaining = remaining

            if best_idx >= 0:
                _add_cut_to_bar(open_bars[best_idx], item, saw_kerf_mm)
                continue

            # 2. Otwórz nową sztangę/odpad.
            selected_pos = -1
            selected_remaining = None
            for idx, bar in enumerate(available):
                remaining = bar.length_mm - item.length_mm
                if remaining < -0.0001:
                    continue
                if selected_remaining is None or remaining < selected_remaining:
                    selected_pos = idx
                    selected_remaining = remaining

            if selected_pos < 0:
                result.missing.append(
                    {
                        "material_id": item.material_id,
                        "length_mm": item.length_mm,
                        "angle_left": item.angle_left,
                        "angle_right": item.angle_right,
                        "label": item.label,
                        "reason": "brak dostępnej sztangi/odpadu o wymaganej długości",
                    }
                )
                continue

            source_bar = available.pop(selected_pos)
            used_bar = UsedBar(
                material_id=source_bar.material_id,
                bar_length_mm=source_bar.length_mm,
                source=source_bar.source,
                source_id=source_bar.id,
                cuts=[],
                used_mm=0.0,
                waste_mm=source_bar.length_mm,
            )
            _add_cut_to_bar(used_bar, item, saw_kerf_mm)
            open_bars.append(used_bar)

        result.bars_used.extend(open_bars)

    # Stabilny porządek wyniku: materiał, źródło, długość.
    result.bars_used.sort(
        key=lambda b: (
            b.material_id,
            0 if b.source == "offcut" else 1,
            b.bar_length_mm,
            b.source_id,
        )
    )
    return result


def summarize_missing_material(result: CuttingResult) -> List[Tuple[str, int]]:
    """Zwraca prostą listę braków: [(material_id, liczba_detali_nieobsłużonych)]."""

    bucket: Dict[str, int] = defaultdict(int)
    for row in result.missing:
        bucket[str(row.get("material_id", ""))] += 1
    return sorted(bucket.items(), key=lambda x: x[0])

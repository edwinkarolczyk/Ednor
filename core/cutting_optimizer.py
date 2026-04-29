# Plik: core/cutting_optimizer.py
# Wersja: 0.2.0
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

VALID_STRATEGIES = {
    "balanced",
    "min_waste",
    "min_bars",
    "min_cuts",
}

REMNANT_SOURCES = {"offcut", "remnant", "REMNANT"}


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

    # Najpierw odpady/remnanty, potem pełne sztangi, w ramach grupy krótsze przed dłuższymi.
    # Dzięki temu program naturalnie zjada resztki, zanim ruszy pełną sztangę.
    out.sort(key=lambda b: (0 if b.source in REMNANT_SOURCES else 1, b.length_mm))
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


def _source_rank(source: str) -> int:
    """Niższy wynik = większy priorytet.

    Remnanty/odpady mają pierwszeństwo, bo celem jest czyszczenie odpadów
    zanim program ruszy nową pełną sztangę.
    """

    return 0 if source in REMNANT_SOURCES else 1


def _score_open_bar(
    *,
    bar: UsedBar,
    item: CutItem,
    saw_kerf_mm: float,
    strategy: str,
) -> tuple:
    """Zwraca score dla dołożenia detalu do już otwartej sztangi.

    Mniejszy tuple = lepszy wybór.
    """

    remaining = _remaining_after_add(bar, item, saw_kerf_mm)
    if remaining < -0.0001:
        return (10**9,)

    cuts_count = len(bar.cuts)
    source = _source_rank(bar.source)

    if strategy == "min_waste":
        return (remaining, source, cuts_count)

    if strategy == "min_bars":
        # Najpierw używaj już otwartych sztang, potem patrz na odpad.
        return (0, source, remaining, cuts_count)

    if strategy == "min_cuts":
        # Mniej pozycji na jednej sztandze = prostszy plan cięcia.
        # Nadal nie marnujemy skrajnie materiału, więc remaining jest drugim kryterium.
        return (cuts_count, remaining, source)

    # balanced: rozsądny kompromis warsztatowy.
    # Czyści odpady, ale nie tworzy absurdalnie słabego wykorzystania.
    return (source, remaining + cuts_count * 25.0, cuts_count)


def _score_new_bar(
    *,
    bar: StockBar,
    item: CutItem,
    strategy: str,
) -> tuple:
    """Zwraca score dla otwarcia nowej sztangi/odpadu."""

    remaining = float(bar.length_mm) - float(item.length_mm)
    if remaining < -0.0001:
        return (10**9,)

    source = _source_rank(bar.source)

    if strategy == "min_waste":
        return (remaining, source, bar.length_mm)

    if strategy == "min_bars":
        # Gdy trzeba otworzyć nową sztangę, wybierz możliwie ciasną.
        return (source, remaining, bar.length_mm)

    if strategy == "min_cuts":
        # Prostszy plan: preferuj pełniejsze, większe sztangi, mniej mikro-odpadów.
        return (source, 0 if source == 1 else 1, remaining)

    # balanced
    return (source, remaining, bar.length_mm)


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
    strategy: str = "balanced",
) -> CuttingResult:
    """Optymalizacja rozkroju metodą best-fit decreasing.

    To nie jest solver matematyczny typu MILP, tylko szybki algorytm warsztatowy:
    - sortuje detale od najdłuższych,
    - najpierw próbuje dopchać istniejące otwarte sztangi,
    - jeśli nie pasuje, bierze kolejną sztangę z magazynu,
    - preferuje odpady użytkowe przed pełnymi sztangami.

    Strategie:
    - balanced: tryb domyślny, warsztatowy kompromis,
    - min_waste: minimalizuje odpad,
    - min_bars: minimalizuje liczbę otwieranych sztang,
    - min_cuts: upraszcza plan cięcia.
    """

    saw_kerf_mm = max(0.0, float(saw_kerf_mm or 0))
    min_reusable_offcut_mm = max(0.0, float(min_reusable_offcut_mm or 0))
    strategy = str(strategy or "balanced").strip()
    if strategy not in VALID_STRATEGIES:
        strategy = "balanced"

    result = CuttingResult(
        job_id=job_id,
        saw_kerf_mm=saw_kerf_mm,
        min_reusable_offcut_mm=min_reusable_offcut_mm,
    )
    result.strategy = strategy  # dynamiczne pole, trafia do debug/GUI jeśli ktoś odczyta obiekt

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
            best_score = None

            # 1. Spróbuj dołożyć do już otwartych sztang.
            for idx, used_bar in enumerate(open_bars):
                score = _score_open_bar(
                    bar=used_bar,
                    item=item,
                    saw_kerf_mm=saw_kerf_mm,
                    strategy=strategy,
                )
                if score[0] >= 10**9:
                    continue
                if best_score is None or score < best_score:
                    best_idx = idx
                    best_score = score

            if best_idx >= 0:
                _add_cut_to_bar(open_bars[best_idx], item, saw_kerf_mm)
                continue

            # 2. Otwórz nową sztangę/odpad.
            selected_pos = -1
            selected_score = None
            for idx, bar in enumerate(available):
                score = _score_new_bar(bar=bar, item=item, strategy=strategy)
                if score[0] >= 10**9:
                    continue
                if selected_score is None or score < selected_score:
                    selected_pos = idx
                    selected_score = score

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
            _source_rank(b.source),
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

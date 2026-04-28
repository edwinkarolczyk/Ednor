# Plik: core/cutting_models.py
# Wersja: 0.1.0
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal


SourceType = Literal["stock", "offcut"]


@dataclass
class CutItem:
    """Pojedyncza pozycja listy cięcia.

    length_mm oznacza wymiar do odmierzenia na pile.
    Kąty są informacją technologiczną dla operatora.
    Na tym etapie NIE przeliczamy geometrii profilu przy 45 stopniach.
    """

    material_id: str
    length_mm: float
    angle_left: float = 0.0
    angle_right: float = 0.0
    qty: int = 1
    label: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CutItem":
        return cls(
            material_id=str(data.get("material_id", "")).strip(),
            length_mm=float(data.get("length_mm", 0) or 0),
            angle_left=float(data.get("angle_left", 0) or 0),
            angle_right=float(data.get("angle_right", 0) or 0),
            qty=int(data.get("qty", 1) or 1),
            label=str(data.get("label", "")).strip(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StockBar:
    """Sztanga pełna albo odpad użytkowy."""

    material_id: str
    length_mm: float
    qty: int = 1
    source: SourceType = "stock"
    id: str = ""
    name: str = ""
    location: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any], source: SourceType = "stock") -> "StockBar":
        material_id = str(data.get("material_id") or data.get("id") or "").strip()
        name = str(data.get("name") or data.get("nazwa") or "").strip()
        length = (
            data.get("length_mm")
            or data.get("dlugosc_mm")
            or data.get("bar_length_mm")
            or 0
        )
        qty = data.get("qty", data.get("ilosc", 1))
        return cls(
            material_id=material_id,
            length_mm=float(length or 0),
            qty=int(qty or 1),
            source=source,
            id=str(data.get("id", "")).strip(),
            name=name,
            location=str(data.get("location") or data.get("lokalizacja") or "").strip(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlannedCut:
    material_id: str
    length_mm: float
    angle_left: float = 0.0
    angle_right: float = 0.0
    label: str = ""

    @classmethod
    def from_item(cls, item: CutItem) -> "PlannedCut":
        return cls(
            material_id=item.material_id,
            length_mm=item.length_mm,
            angle_left=item.angle_left,
            angle_right=item.angle_right,
            label=item.label,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UsedBar:
    material_id: str
    bar_length_mm: float
    source: SourceType = "stock"
    source_id: str = ""
    cuts: List[PlannedCut] = field(default_factory=list)
    used_mm: float = 0.0
    waste_mm: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["cuts"] = [cut.to_dict() for cut in self.cuts]
        return data


@dataclass
class CuttingResult:
    job_id: str
    saw_kerf_mm: float
    min_reusable_offcut_mm: float
    bars_used: List[UsedBar] = field(default_factory=list)
    missing: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        total_waste = sum(bar.waste_mm for bar in self.bars_used)
        total_length = sum(bar.bar_length_mm for bar in self.bars_used)
        total_used = sum(bar.used_mm for bar in self.bars_used)
        usage_percent = round((total_used / total_length * 100), 2) if total_length else 0.0

        return {
            "job_id": self.job_id,
            "saw_kerf_mm": self.saw_kerf_mm,
            "min_reusable_offcut_mm": self.min_reusable_offcut_mm,
            "bars_used": [bar.to_dict() for bar in self.bars_used],
            "missing": self.missing,
            "summary": {
                "bars_count": len(self.bars_used),
                "total_length_mm": round(total_length, 3),
                "total_used_mm": round(total_used, 3),
                "total_waste_mm": round(total_waste, 3),
                "usage_percent": usage_percent,
            },
        }


def expand_cut_items(items: List[CutItem]) -> List[CutItem]:
    """Rozbija pozycje z qty na pojedyncze sztuki i sortuje od najdłuższych."""

    expanded: List[CutItem] = []
    for item in items:
        if not item.material_id:
            continue
        if item.length_mm <= 0:
            continue
        qty = max(0, int(item.qty))
        for _ in range(qty):
            expanded.append(
                CutItem(
                    material_id=item.material_id,
                    length_mm=float(item.length_mm),
                    angle_left=float(item.angle_left),
                    angle_right=float(item.angle_right),
                    qty=1,
                    label=item.label,
                )
            )
    expanded.sort(key=lambda x: x.length_mm, reverse=True)
    return expanded

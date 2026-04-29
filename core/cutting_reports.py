from __future__ import annotations

from html import escape
from typing import Any, Dict


def generate_cutting_report_html(result: Dict[str, Any]) -> str:
    job_id = str(result.get("job_id", "")).strip() or "ROZKROJ"
    strategy = str(result.get("strategy", "")).strip()
    summary = result.get("summary", {}) or {}
    bars = result.get("bars_used", []) or []

    rows = []
    for idx, bar in enumerate(bars, start=1):
        cuts = bar.get("cuts", []) or []
        cuts_text = "<br>".join(
            f"{escape(str(c.get('length_mm', 0)))} mm "
            f"({escape(str(c.get('angle_left', 0)))}°/{escape(str(c.get('angle_right', 0)))}°) "
            f"{escape(str(c.get('label', '') or ''))}"
            for c in cuts
        )
        rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{escape(str(bar.get('material_id', '')))}</td>"
            f"<td>{escape(str(bar.get('source', '')))}</td>"
            f"<td>{escape(str(bar.get('bar_length_mm', 0)))}</td>"
            f"<td>{escape(str(bar.get('used_mm', 0)))}</td>"
            f"<td>{escape(str(bar.get('waste_mm', 0)))}</td>"
            f"<td>{cuts_text}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <title>Raport rozkroju - {escape(job_id)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f3f3; }}
    .muted {{ color: #666; }}
  </style>
</head>
<body>
  <h1>Raport rozkroju</h1>
  <p><strong>Zlecenie:</strong> {escape(job_id)}</p>
  <p><strong>Strategia:</strong> {escape(strategy)}</p>
  <p>
    <strong>Sztangi:</strong> {escape(str(summary.get('bars_count', len(bars))))} |
    <strong>Odpad [mm]:</strong> {escape(str(summary.get('total_waste_mm', 0)))} |
    <strong>Wykorzystanie [%]:</strong> {escape(str(summary.get('usage_percent', 0)))}
  </p>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Materiał</th>
        <th>Źródło</th>
        <th>Długość [mm]</th>
        <th>Użyte [mm]</th>
        <th>Odpad [mm]</th>
        <th>Cięcia</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  <p class="muted">Wygenerowano z EDNOR / Rozkrój.</p>
</body>
</html>
"""

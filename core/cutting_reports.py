from typing import Any, Dict


def generate_cutting_report_html(data: Dict[str, Any]) -> str:
    summary = data.get("summary", {})
    bars = data.get("bars_used", [])

    rows = ""
    for bar in bars:
        rows += f"<tr><td>{bar.get('material_id')}</td><td>{bar.get('bar_length_mm')}</td><td>{bar.get('waste_mm')}</td></tr>"

    html = f"""
    <html>
    <body style='font-family: Arial;'>
    <h2>Raport rozkroju</h2>
    <p>Strategia: {data.get('strategy')}</p>
    <p>Sztangi: {summary.get('bars_count')}</p>
    <p>Odpad: {summary.get('total_waste_mm')} mm</p>

    <table border='1' cellpadding='5'>
    <tr><th>Materiał</th><th>Długość</th><th>Odpad</th></tr>
    {rows}
    </table>
    </body>
    </html>
    """
    return html

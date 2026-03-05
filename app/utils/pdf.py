from datetime import datetime
from io import BytesIO


def _safe(value: str | None) -> str:
    return value or "-"


def build_quote_pdf(order, quote, lines) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    doc_no = getattr(order, "order_no", None) or getattr(order, "quote_no", "-")
    client_name = getattr(order, "client_name", None) or getattr(order, "customer_name", None)
    address = getattr(order, "address", None) or getattr(order, "site_address_text", None)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(40, y, "EDNOR – Wycena")

    pdf.setFont("Helvetica", 11)
    y -= 28
    pdf.drawString(40, y, f"Dokument: {doc_no} / v{quote.version_no}")
    y -= 16
    pdf.drawString(40, y, f"Klient: {_safe(client_name)}")
    y -= 16
    pdf.drawString(40, y, f"Adres: {_safe(address)}")

    y -= 28
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "Nazwa")
    pdf.drawString(270, y, "j.m.")
    pdf.drawRightString(360, y, "Ilość")
    pdf.drawRightString(455, y, "Cena")
    pdf.drawRightString(550, y, "Wartość")
    y -= 8
    pdf.line(40, y, width - 40, y)

    pdf.setFont("Helvetica", 10)
    for line in lines:
        y -= 18
        if y < 120:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica", 10)
        pdf.drawString(40, y, str(line.name))
        pdf.drawString(270, y, str(line.unit))
        pdf.drawRightString(360, y, f"{line.qty:.2f}")
        pdf.drawRightString(455, y, f"{line.unit_price:.2f} zł")
        pdf.drawRightString(550, y, f"{line.total_price:.2f} zł")

    y -= 24
    pdf.line(40, y, width - 40, y)
    y -= 18
    pdf.drawRightString(550, y, f"Subtotal netto: {quote.subtotal_net:.2f} zł")
    y -= 16
    pdf.drawRightString(550, y, f"Marża: {quote.margin_percent:.2f}%")
    y -= 18
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawRightString(550, y, f"Total netto: {quote.total_net:.2f} zł")

    pdf.setFont("Helvetica", 10)
    if quote.warranty_days is not None:
        y -= 20
        pdf.drawString(40, y, f"Gwarancja: {quote.warranty_days} dni")

    y -= 16
    pdf.drawString(40, y, f"Data wygenerowania: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()

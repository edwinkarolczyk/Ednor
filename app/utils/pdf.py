from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

FONT_NAME = "Helvetica"


def _safe_text(value: str | None) -> str:
    return value or "-"


def generate_quote_pdf(quote, order, lines) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    pdf.setFont(FONT_NAME, 16)
    pdf.drawString(40, y, "EDNOR - Wycena")

    y -= 30
    pdf.setFont(FONT_NAME, 11)
    pdf.drawString(40, y, f"Nr zlecenia: {order.order_no}")
    y -= 16
    pdf.drawString(40, y, f"Klient: {_safe_text(order.client_name)}")
    y -= 16
    pdf.drawString(40, y, f"Adres: {_safe_text(order.address)}")

    y -= 30
    pdf.setFont(FONT_NAME, 10)
    pdf.drawString(40, y, "Pozycje")
    y -= 16
    pdf.drawString(40, y, "Nazwa")
    pdf.drawString(280, y, "Ilość")
    pdf.drawString(360, y, "Cena jedn.")
    pdf.drawString(460, y, "Wartość")
    y -= 10
    pdf.line(40, y, width - 40, y)

    for line in lines:
        y -= 16
        if y < 120:
            pdf.showPage()
            y = height - 50
            pdf.setFont(FONT_NAME, 10)
        pdf.drawString(40, y, str(line.name))
        pdf.drawRightString(330, y, f"{line.qty:.2f} {line.unit}")
        pdf.drawRightString(430, y, f"{line.unit_price:.2f} zł")
        pdf.drawRightString(550, y, f"{line.total_price:.2f} zł")

    y -= 30
    pdf.line(40, y, width - 40, y)
    y -= 18
    pdf.drawRightString(550, y, f"Subtotal netto: {quote.subtotal_net:.2f} zł")
    y -= 16
    pdf.drawRightString(550, y, f"Marża: {quote.margin_percent:.2f}%")
    y -= 16
    pdf.setFont(FONT_NAME, 12)
    pdf.drawRightString(550, y, f"Suma netto: {quote.total_net:.2f} zł")
    y -= 20
    pdf.setFont(FONT_NAME, 10)
    warranty = f"{quote.warranty_days} dni" if quote.warranty_days is not None else "-"
    pdf.drawString(40, y, f"Gwarancja: {warranty}")
    y -= 16
    pdf.drawString(40, y, f"Data: {datetime.now().strftime('%Y-%m-%d')}")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()

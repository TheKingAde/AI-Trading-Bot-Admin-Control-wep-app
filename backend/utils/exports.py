from io import BytesIO
from datetime import datetime

from quart import send_file
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from openpyxl import Workbook


async def generate_pdf_statement(account_summary: dict, trades: list):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, "Trading Statement")

    c.setFont("Helvetica", 12)
    y = height - 100
    for k, v in account_summary.items():
        c.drawString(72, y, f"{k}: {v}")
        y -= 16

    y -= 16
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Trades:")
    y -= 16
    c.setFont("Helvetica", 10)
    for t in trades[:40]:  # limit to avoid overflow
        c.drawString(72, y, f"{t.get('pair')} result: {t.get('result')} closed: {t.get('closed_at')}")
        y -= 12
        if y < 72:
            c.showPage()
            y = height - 72

    c.showPage()
    c.save()
    buffer.seek(0)
    return await send_file(buffer, mimetype='application/pdf', download_name=f'statement_{datetime.utcnow().date()}.pdf')


async def generate_xls_statement(account_summary: dict, trades: list):
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"

    ws.append(["Account Summary"])
    for k, v in account_summary.items():
        ws.append([k, v])

    ws.append([])
    ws.append(["Trades"])
    ws.append(["Pair", "Result", "Opened", "Closed", "AI Confidence"]) 
    for t in trades:
        ws.append([
            t.get('pair'), t.get('result'), t.get('opened_at'), t.get('closed_at'), t.get('ai_confidence')
        ])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return await send_file(bio, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', download_name=f'statement_{datetime.utcnow().date()}.xlsx')
